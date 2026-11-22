# Chuyển đổi object với $objectToArray, $arrayToObject và $mergeObjects trong MongoDB

## 1. Vì sao cần chuyển đổi object trong aggregation?

MongoDB lưu dữ liệu dưới dạng **document BSON**. Trong một document, object thường được dùng để biểu diễn một tập thuộc tính có tên. Ví dụ:

~~~javascript
{
  _id: "SKU-001",
  name: "Wireless Mouse",
  stockByWarehouse: {
    HN: 7,
    HCM: 12,
    DN: 3
  }
}
~~~

Đối với ứng dụng, **stockByWarehouse** là một bản đồ từ mã kho đến số lượng tồn:

~~~text
HN  -> 7
HCM -> 12
DN  -> 3
~~~

Khi số lượng kho hoặc tên thuộc tính thay đổi theo từng document, ứng dụng không thể viết trước một biểu thức cho mọi khóa có thể xuất hiện. Những nhu cầu phổ biến gồm:

1. **Duyệt tất cả cặp key/value** để tính tổng hoặc lọc thuộc tính động.
2. **Biến mảng cặp key/value thành object** để tạo document dễ truy cập.
3. **Ghép các object cấu hình** theo thứ tự ưu tiên mặc định → tenant → request.
4. **Biến đổi hoặc đổi tên khóa** mà không phải biết trước danh sách khóa.
5. **Chuẩn hóa dữ liệu** trước khi xuất báo cáo, chuyển sang DTO hoặc cập nhật theo quy tắc mới.

MongoDB cung cấp ba biểu thức aggregation đặc biệt hữu ích:

| Expression | Đầu vào chính | Đầu ra | Công dụng |
|---|---|---|---|
| **$objectToArray** | Object/document | Array các object **{k, v}** | Biến các field của object thành phần tử để xử lý bằng toán tử mảng. |
| **$arrayToObject** | Array các cặp **[k, v]** hoặc object **{k, v}** | Object/document | Dựng lại object từ danh sách key/value. |
| **$mergeObjects** | Một hoặc nhiều object | Object/document hợp nhất | Kết hợp field, giải quyết khóa trùng theo thứ tự ưu tiên. |

Sơ đồ tư duy:

~~~text
Object:
  {HN:7, HCM:12}
       |
       | $objectToArray
       v
Array:
  [{k:"HN",v:7}, {k:"HCM",v:12}]
       |
       | $filter / $map / $concatArrays ...
       v
Array:
  [{k:"HN",v:7}, {k:"HCM",v:12}, {k:"total",v:19}]
       |
       | $arrayToObject
       v
Object:
  {HN:7, HCM:12, total:19}

Object A + Object B
       |
       | $mergeObjects
       v
Object kết hợp
~~~

**Điểm khác biệt:** đây là **aggregation expressions**, không phải ba pipeline stages độc lập. Chúng được đặt bên trong các stages như **$project**, **$set/$addFields**, **$replaceRoot/$replaceWith**, hoặc trong các ngữ cảnh khác có hỗ trợ expression. Riêng **$mergeObjects** còn có dạng **accumulator** trong một số grouping stages.

## 2. Chuẩn bị dữ liệu thực hành

Trong **mongosh**, dùng một database thử nghiệm riêng:

~~~javascript
use aggregation_object_lab
~~~

Thêm các sản phẩm có tập mã kho khác nhau:

~~~javascript
db.products.insertMany([
  {
    _id: "SKU-001",
    tenantId: "T1",
    name: "Wireless Mouse",
    status: "ACTIVE",
    stockByWarehouse: {
      HN: NumberInt(7),
      HCM: NumberInt(12),
      DN: NumberInt(3)
    },
    attributes: {
      color: "black",
      warrantyMonths: NumberInt(12),
      wireless: true
    }
  },
  {
    _id: "SKU-002",
    tenantId: "T1",
    name: "Mechanical Keyboard",
    status: "ACTIVE",
    stockByWarehouse: {
      HCM: NumberInt(4),
      CT: NumberInt(6)
    },
    attributes: {
      color: "white",
      switchType: "linear"
    }
  },
  {
    _id: "SKU-003",
    tenantId: "T1",
    name: "27-inch Monitor",
    status: "DRAFT",
    stockByWarehouse: {},
    attributes: {
      resolution: {
        width: NumberInt(2560),
        height: NumberInt(1440)
      },
      refreshRate: NumberInt(144)
    }
  },
  {
    _id: "SKU-004",
    tenantId: "T1",
    name: "USB Hub",
    status: "ACTIVE",
    attributes: null
  },
  {
    _id: "SKU-005",
    tenantId: "T2",
    name: "Laptop Stand",
    status: "ACTIVE",
    stockByWarehouse: {
      HN: NumberInt(10)
    },
    attributes: {
      color: "silver"
    }
  }
]);
~~~

**Lưu ý:** lệnh **insertMany** chỉ nên chạy một lần trên collection mới. Nếu chạy lại với cùng **_id**, MongoDB trả lỗi duplicate key. Các ví dụ dưới đây chủ yếu dùng aggregation đọc, không xóa dữ liệu nguồn.

Chúng ta có năm document:

| _id | tenant | Kho | Điểm cần chú ý |
|---|---|---|---|
| SKU-001 | T1 | HN, HCM, DN | Có ba cặp key/value. |
| SKU-002 | T1 | HCM, CT | Các khóa không trùng hoàn toàn với SKU-001. |
| SKU-003 | T1 | Mảng khóa rỗng trong object **{}** | Test object rỗng và object lồng nhau. |
| SKU-004 | T1 | Field stockByWarehouse **missing** | Kiểm tra field thiếu và attributes null. |
| SKU-005 | T2 | HN | Kiểm tra lọc tenant. |

Hai khái niệm phải tách rõ:

- **Object** như **{HN: 7, HCM: 12}**: key nằm ở **tên field**.
- **Array các cặp** như **[{k:"HN",v:7},{k:"HCM",v:12}]**: key nằm trong **giá trị field k** của từng phần tử.

Biến đổi giữa hai dạng này tạo cơ hội dùng **$map**, **$filter**, **$sum**, **$reduce** và các expressions của aggregation.

## 3. $objectToArray: từ object sang mảng {k, v}

### 3.1. Cú pháp

~~~javascript
{
  $objectToArray: <objectExpression>
}
~~~

**objectExpression** phải trả về một document/object BSON hợp lệ. Kết quả là một array có phần tử với hai field:

- **k:** tên field nguồn, ở dạng string.
- **v:** giá trị của field nguồn, giữ kiểu BSON tương ứng.

Ví dụ:

~~~javascript
{
  HN: 7,
  HCM: 12,
  DN: 3
}
~~~

trở thành:

~~~javascript
[
  { k: "HN", v: 7 },
  { k: "HCM", v: 12 },
  { k: "DN", v: 3 }
]
~~~

### 3.2. Đưa expression vào $project

~~~javascript
db.products.aggregate([
  {
    $match: {
      _id: "SKU-001"
    }
  },
  {
    $project: {
      _id: 1,
      warehouses: {
        $objectToArray: "$stockByWarehouse"
      }
    }
  }
]);
~~~

Kết quả minh họa:

~~~javascript
{
  _id: "SKU-001",
  warehouses: [
    { k: "HN", v: 7 },
    { k: "HCM", v: 12 },
    { k: "DN", v: 3 }
  ]
}
~~~

**$project** là pipeline stage, còn **$objectToArray** là expression bên trong stage đó. Expression này **không nhân số document**: một product đi vào $project vẫn cho một product đi ra, chỉ thay cấu trúc field warehouses.

### 3.3. Có thể dùng $set để giữ field gốc

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $set: {
      warehousePairs: {
        $objectToArray: "$stockByWarehouse"
      }
    }
  }
]);
~~~

Khác với ví dụ chỉ project, stage **$set** giữ các field nguồn khác và thêm **warehousePairs**. Sau stage này, document kết quả chứa **cả stockByWarehouse dạng object** và **warehousePairs dạng array**.

**$set** trong **aggregate()** là stage xử lý kết quả trung gian; nó không tự ghi document trở lại collection. Cần phân biệt với **$set** trong updateOne hoặc update pipeline có tác dụng ghi.

### 3.4. $objectToArray chỉ xử lý một cấp field

Xét document SKU-003:

~~~javascript
{
  attributes: {
    resolution: {
      width: 2560,
      height: 1440
    },
    refreshRate: 144
  }
}
~~~

Truy vấn:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-003" } },
  {
    $project: {
      _id: 0,
      attributePairs: {
        $objectToArray: "$attributes"
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  attributePairs: [
    {
      k: "resolution",
      v: {
        width: 2560,
        height: 1440
      }
    },
    {
      k: "refreshRate",
      v: 144
    }
  ]
}
~~~

**$objectToArray không chuyển đổi đệ quy mọi object lồng nhau**. Nó chỉ biến **các field ở cấp trực tiếp của object đầu vào** thành các phần tử {k, v}; field resolution vẫn có giá trị **v là một embedded document**.

Nếu cần xử lý các field con của resolution, phải truy cập object đó và gọi biểu thức chuyển đổi tương ứng ở cấp đó, hoặc thiết kế cách duyệt cấu trúc lồng nhau riêng.

### 3.5. Trường hợp object rỗng

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-003" } },
  {
    $project: {
      warehouses: {
        $objectToArray: "$stockByWarehouse"
      }
    }
  }
]);
~~~

Vì **stockByWarehouse: {}**, biểu thức trả về:

~~~javascript
{
  _id: "SKU-003",
  warehouses: []
}
~~~

Một object không có field sẽ được chuyển thành array không có phần tử. **Đừng nhầm object rỗng {} với null hoặc missing**, vì cách xử lý tiếp theo có thể khác nhau.

### 3.6. Field missing hoặc null

Với field đầu vào **null** hoặc **missing**, **$objectToArray** trả về **null**. Ví dụ SKU-004 không có stockByWarehouse:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-004" } },
  {
    $project: {
      warehousePairs: {
        $objectToArray: "$stockByWarehouse"
      }
    }
  }
]);
~~~

Kết quả biểu thức warehousePairs là **null**, không phải array rỗng. Nếu downstream cần luôn nhận một array để **$map/$filter/$size** hoạt động ổn định, cung cấp object mặc định bằng **$ifNull**:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-004" } },
  {
    $project: {
      warehousePairs: {
        $objectToArray: {
          $ifNull: [
            "$stockByWarehouse",
            {}
          ]
        }
      }
    }
  }
]);
~~~

Lúc này **warehousePairs = []**. Quy tắc này chỉ xử lý **null/missing**; nếu stockByWarehouse là string hoặc number, **$objectToArray** vẫn có thể lỗi vì đầu vào không phải object.

## 4. Làm việc với các cặp key/value bằng $filter, $map và $sum

Chuyển sang mảng không phải mục tiêu cuối cùng. Lợi ích lớn nhất là có thể dùng **array expressions** để xử lý một tập field động.

### 4.1. Tính tổng tồn kho từ những khóa không biết trước

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "T1"
    }
  },
  {
    $set: {
      warehousePairs: {
        $objectToArray: {
          $ifNull: [
            "$stockByWarehouse",
            {}
          ]
        }
      }
    }
  },
  {
    $set: {
      totalStock: {
        $sum: "$warehousePairs.v"
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      totalStock: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả dự kiến:

~~~javascript
[
  { _id: "SKU-001", name: "Wireless Mouse", totalStock: 22 },
  { _id: "SKU-002", name: "Mechanical Keyboard", totalStock: 10 },
  { _id: "SKU-003", name: "27-inch Monitor", totalStock: 0 },
  { _id: "SKU-004", name: "USB Hub", totalStock: 0 }
]
~~~

Giải thích:

1. **$objectToArray** biến stockByWarehouse thành các phần tử {k,v}.
2. **"$warehousePairs.v"** lấy các giá trị v từ mảng object.
3. **$sum** ở vị trí expression trong **$set** tính tổng các giá trị số.
4. **$project** chỉ trả các field cần cho báo cáo.

Đây là **expression $sum trên một mảng của từng document**, không phải accumulator **$sum trong $group** cộng qua nhiều document.

Nếu warehousePairs chứa giá trị không phải số, semantics cộng số cần được xem kỹ; không nên im lặng coi dữ liệu sai kiểu là tồn kho hợp lệ. Dùng schema validation hoặc kiểm tra kiểu đầu vào.

### 4.2. Lọc chỉ các kho còn hàng

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 1,
      availableWarehouses: {
        $filter: {
          input: {
            $objectToArray: "$stockByWarehouse"
          },
          as: "warehouse",
          cond: {
            $gt: [
              "$$warehouse.v",
              0
            ]
          }
        }
      }
    }
  }
]);
~~~

Kết quả là array các cặp có **v > 0**. Trong dữ liệu SKU-001, cả ba kho đều có hàng.

**$$warehouse** là biến của **$filter**, đại diện cho một phần tử của mảng. **$$warehouse.v** là số lượng của phần tử đó. Nó khác **"$stockByWarehouse"**, là field path của document gốc.

### 4.3. Lấy chỉ danh sách mã kho

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-002" } },
  {
    $project: {
      _id: 0,
      warehouseCodes: {
        $map: {
          input: {
            $objectToArray: "$stockByWarehouse"
          },
          as: "pair",
          in: "$$pair.k"
        }
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  warehouseCodes: ["HCM", "CT"]
}
~~~

Mỗi phần tử nguồn có **k** và **v**, nhưng **$map** chỉ lấy **k**. Cách này hữu ích cho báo cáo hoặc kiểm tra các thuộc tính động đã được lưu.

### 4.4. Tính số kho có tồn kho dương

~~~javascript
db.products.aggregate([
  {
    $set: {
      activeWarehouseCount: {
        $size: {
          $filter: {
            input: {
              $objectToArray: {
                $ifNull: ["$stockByWarehouse", {}]
              }
            },
            as: "pair",
            cond: {
              $gt: ["$$pair.v", 0]
            }
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      activeWarehouseCount: 1
    }
  }
]);
~~~

Kết quả dự kiến:

| _id | Số kho có tồn kho dương |
|---|---:|
| SKU-001 | 3 |
| SKU-002 | 2 |
| SKU-003 | 0 |
| SKU-004 | 0 |
| SKU-005 | 1 |

Một document vào pipeline vẫn là một document ra. **$objectToArray**, **$filter** và **$size** đều là expressions, không làm nhân số document như **$unwind stage**.

### 4.5. Khi nào cần $unwind sau $objectToArray?

Nếu muốn một dòng báo cáo **cho mỗi kho**, dùng **$unwind**:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "T1"
    }
  },
  {
    $set: {
      warehousePairs: {
        $objectToArray: {
          $ifNull: ["$stockByWarehouse", {}]
        }
      }
    }
  },
  { $unwind: "$warehousePairs" },
  {
    $project: {
      _id: 0,
      sku: "$_id",
      warehouse: "$warehousePairs.k",
      stock: "$warehousePairs.v"
    }
  },
  {
    $sort: {
      sku: 1,
      warehouse: 1
    }
  }
]);
~~~

Kết quả theo dữ liệu T1:

~~~javascript
[
  { sku: "SKU-001", warehouse: "DN", stock: 3 },
  { sku: "SKU-001", warehouse: "HCM", stock: 12 },
  { sku: "SKU-001", warehouse: "HN", stock: 7 },
  { sku: "SKU-002", warehouse: "CT", stock: 6 },
  { sku: "SKU-002", warehouse: "HCM", stock: 4 }
]
~~~

**$unwind** thay đổi cardinality: SKU-001 tạo ba document kết quả, SKU-002 tạo hai, SKU-003 và SKU-004 có array rỗng sau bước chuyển nên không tạo dòng. Muốn giữ các product không có kho, cần xem tùy chọn **preserveNullAndEmptyArrays** và xử lý output phù hợp.

## 5. $arrayToObject: từ mảng cặp thành object

### 5.1. Cú pháp

~~~javascript
{
  $arrayToObject: <arrayExpression>
}
~~~

**arrayExpression** phải trả về một mảng theo **một trong hai dạng**:

1. **Array các array hai phần tử:** phần tử thứ nhất là tên field, phần tử thứ hai là giá trị.
2. **Array các object có field k và v:** k là tên field, v là giá trị.

### 5.2. Dạng mảng hai phần tử [key, value]

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 0,
      labels: {
        $arrayToObject: {
          $literal: [
            ["zoneA", "HN"],
            ["zoneB", "HCM"],
            ["zoneC", "DN"]
          ]
        }
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  labels: {
    zoneA: "HN",
    zoneB: "HCM",
    zoneC: "DN"
  }
}
~~~

**$literal** giúp biểu diễn toàn bộ mảng nguồn như dữ liệu hằng rõ ràng. Trong nhiều ngữ cảnh, một array literal hợp lệ cũng được biểu diễn trực tiếp, nhưng dùng $literal hữu ích khi muốn tránh diễn giải các giá trị đặc biệt bắt đầu bằng ký tự **$**.

### 5.3. Dạng mảng object {k, v}

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 0,
      flags: {
        $arrayToObject: {
          $literal: [
            { k: "ready", v: true },
            { k: "mode", v: "ONLINE" },
            { k: "attempts", v: 3 }
          ]
        }
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  flags: {
    ready: true,
    mode: "ONLINE",
    attempts: 3
  }
}
~~~

Hai biểu diễn mảng khác nhau nhưng cùng tạo một BSON document. Với dữ liệu từ **$objectToArray**, dạng **{k, v}** thuận tiện nhất vì không cần đổi cấu trúc thêm.

### 5.4. Mảng rỗng và null

**$arrayToObject: []** trả một object rỗng **{}**.

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-003" } },
  {
    $project: {
      _id: 1,
      objectAgain: {
        $arrayToObject: {
          $objectToArray: "$stockByWarehouse"
        }
      }
    }
  }
]);
~~~

Vì stockByWarehouse là **{}**, kết quả **objectAgain** cũng là **{}**.

Nếu đầu vào của **$arrayToObject** là **null** hoặc **missing**, biểu thức trả **null**. Do đó khi cần một object trong output, có thể cung cấp mảng mặc định:

~~~javascript
{
  $arrayToObject: {
    $ifNull: [
      "$pairs",
      []
    ]
  }
}
~~~

**$ifNull** chỉ thay null/missing, không tự biến một array sai cấu trúc thành array hợp lệ.

### 5.5. Lỗi khi phần tử không đúng định dạng

Ví dụ dưới đây có phần tử không phải mảng hai giá trị hoặc object k/v:

~~~javascript
// Ví dụ sai định dạng:
{
  $arrayToObject: {
    $literal: [
      ["color", "red", "unexpected"],
      ["size", "M"]
    ]
  }
}
~~~

MongoDB có thể báo lỗi vì array ba phần tử không đúng contract.

Một số nguyên tắc kiểm tra:

- **k phải là tên field dạng string** trong ngữ cảnh được MongoDB hỗ trợ.
- Mảng hai phần tử phải **có đúng hai phần tử**.
- Dạng object phải có **k** và **v** theo yêu cầu.
- Không dùng mảng chứa raw number/string rồi mong MongoDB tự suy ra key.
- Không truyền array lớn không kiểm soát; object kết quả vẫn chịu giới hạn BSON document.

## 6. Khóa trùng trong $arrayToObject: giá trị cuối cùng thắng

Giả sử dữ liệu nguồn chứa hai cặp cùng tên **color**:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 0,
      result: {
        $arrayToObject: {
          $literal: [
            { k: "color", v: "black" },
            { k: "size", v: "M" },
            { k: "color", v: "white" }
          ]
        }
      }
    }
  }
]);
~~~

Trong các phiên bản MongoDB hiện đại, kết quả là:

~~~javascript
{
  result: {
    color: "white",
    size: "M"
  }
}
~~~

**Giá trị của khóa trùng xuất hiện cuối cùng sẽ được sử dụng.** Không có hai field **color** độc lập trong object kết quả theo cách ứng dụng thường mong muốn.

Điều này hữu ích để áp dụng **ưu tiên theo thứ tự**, nhưng cũng là một rủi ro nếu input có duplicate key ngoài ý muốn. Với những hệ thống cần từ chối duplicate thay vì ghi đè, phải kiểm tra trước khi gọi **$arrayToObject**.

### 6.1. Vì sao cần phân biệt duplicate key với duplicate value?

~~~javascript
[
  { k: "color", v: "red" },
  { k: "size", v: "red" }
]
~~~

Hai **v** đều là "red" nhưng **k khác nhau**, vì vậy object kết quả chứa cả color và size.

~~~javascript
[
  { k: "color", v: "red" },
  { k: "color", v: "blue" }
]
~~~

Hai **k** trùng, nên lần xuất hiện sau ghi đè giá trị cũ. **$arrayToObject** không xử lý như một multimap cho phép nhiều giá trị cùng tên field.

### 6.2. Thứ tự array mang ý nghĩa ưu tiên

~~~text
[{k:"theme",v:"light"}, {k:"theme",v:"dark"}]
                  |
                  v
         {theme:"dark"}
~~~

Đảo thứ tự:

~~~text
[{k:"theme",v:"dark"}, {k:"theme",v:"light"}]
                  |
                  v
         {theme:"light"}
~~~

Nếu nguồn dữ liệu không bảo đảm thứ tự, đừng dùng **last-wins** như một quy tắc nghiệp vụ không được định nghĩa. Hãy sắp xếp rõ hoặc chọn một giá trị theo tiêu chí xác định trước.

## 7. Kết hợp $objectToArray và $arrayToObject để biến đổi tên field

Đây là một mẫu rất thường gặp:

~~~text
object
  -> $objectToArray
  -> $map hoặc $filter
  -> $arrayToObject
  -> object mới
~~~

### 7.1. Thêm prefix vào mọi tên field

Ví dụ muốn biến:

~~~javascript
{
  color: "black",
  warrantyMonths: 12,
  wireless: true
}
~~~

thành:

~~~javascript
{
  attr_color: "black",
  attr_warrantyMonths: 12,
  attr_wireless: true
}
~~~

Pipeline:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 1,
      renamedAttributes: {
        $arrayToObject: {
          $map: {
            input: {
              $objectToArray: "$attributes"
            },
            as: "pair",
            in: {
              k: {
                $concat: [
                  "attr_",
                  "$$pair.k"
                ]
              },
              v: "$$pair.v"
            }
          }
        }
      }
    }
  }
]);
~~~

Phân tích:

1. **$objectToArray** chuyển attributes thành mảng {k,v}.
2. **$map** đi qua từng phần tử, tính tên mới bằng **$concat**.
3. Giữ nguyên **v** và thay **k**.
4. **$arrayToObject** tạo object với các tên field mới.

Với **attributes:null** ở SKU-004, cần thêm **$ifNull** để objectToArray nhận object mặc định. Ví dụ này chỉ chạy trên SKU-001 nên không gặp trường hợp đó.

### 7.2. Xóa một số field của object động

Giả sử object **attributes** chứa thông tin nội bộ **internalNote** mà client không được xem. Có thể lọc theo tên khóa:

~~~javascript
db.products.aggregate([
  {
    $project: {
      name: 1,
      publicAttributes: {
        $arrayToObject: {
          $filter: {
            input: {
              $objectToArray: {
                $ifNull: ["$attributes", {}]
              }
            },
            as: "pair",
            cond: {
              $ne: [
                "$$pair.k",
                "internalNote"
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

Mọi cặp ngoại trừ key internalNote được đưa trở lại object. Với dữ liệu mẫu hiện tại không có internalNote, output bằng các attributes nguồn.

**Cảnh báo bảo mật:** chỉ loại một tên field không tự đảm bảo mọi thông tin nhạy cảm đều được ẩn. Với dữ liệu có khóa động do user nhập, nên dùng **allowlist các field được phép xuất** khi dữ liệu chứa nhiều loại thông tin nhạy cảm, và bảo vệ dữ liệu ở schema/authorization.

### 7.3. Chỉ giữ các khóa có prefix được phép

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      filtered: {
        $arrayToObject: {
          $filter: {
            input: {
              $objectToArray: {
                $ifNull: ["$attributes", {}]
              }
            },
            as: "pair",
            cond: {
              $regexMatch: {
                input: "$$pair.k",
                regex: "^public_"
              }
            }
          }
        }
      }
    }
  }
]);
~~~

**$regexMatch** là aggregation expression trả boolean. Nó kiểm tra tên key, không kiểm tra giá trị v. Nếu không có key bắt đầu public_, object kết quả là **{}**.

Regex nên được khai báo cố định hoặc được kiểm soát từ cấu hình tin cậy; không cho người dùng gửi biểu thức regex tùy ý không có giới hạn.

### 7.4. Chuyển kiểu của giá trị trong khi đổi key

Giả sử mọi tồn kho phải được biểu diễn là string trong một báo cáo JSON:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      _id: 0,
      stockAsText: {
        $arrayToObject: {
          $map: {
            input: {
              $objectToArray: "$stockByWarehouse"
            },
            as: "pair",
            in: {
              k: "$$pair.k",
              v: {
                $toString: "$$pair.v"
              }
            }
          }
        }
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  stockAsText: {
    HN: "7",
    HCM: "12",
    DN: "3"
  }
}
~~~

Đây là một **representation dành cho output**, không nên ghi đè stock số trong database bằng string nếu ứng dụng còn cần cộng/trừ chính xác. Chuyển đổi kiểu là quyết định thuộc schema/contract.

## 8. Từ array các thuộc tính động sang object

Không phải mọi dữ liệu đều bắt đầu từ object. Một số API hoặc dữ liệu nhập vào lưu thuộc tính dưới dạng array:

~~~javascript
{
  _id: "IMPORT-001",
  properties: [
    { name: "color", value: "black" },
    { name: "size", value: "M" },
    { name: "weightKg", value: 1.25 }
  ]
}
~~~

### 8.1. Dùng $map tạo k/v rồi $arrayToObject

Tạo một collection lab riêng:

~~~javascript
db.import_rows.insertOne({
  _id: "IMPORT-001",
  properties: [
    { name: "color", value: "black" },
    { name: "size", value: "M" },
    { name: "weightKg", value: 1.25 }
  ]
});
~~~

Pipeline:

~~~javascript
db.import_rows.aggregate([
  {
    $project: {
      _id: 1,
      propertiesAsObject: {
        $arrayToObject: {
          $map: {
            input: "$properties",
            as: "property",
            in: {
              k: "$$property.name",
              v: "$$property.value"
            }
          }
        }
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  _id: "IMPORT-001",
  propertiesAsObject: {
    color: "black",
    size: "M",
    weightKg: 1.25
  }
}
~~~

Ở đây **properties** có dạng {name,value}; vì vậy cần **$map** để chuyển thành {k,v}, rồi mới dùng **$arrayToObject**.

### 8.2. Khi properties missing hoặc null

~~~javascript
{
  $arrayToObject: {
    $map: {
      input: {
        $ifNull: ["$properties", []]
      },
      as: "property",
      in: {
        k: "$$property.name",
        v: "$$property.value"
      }
    }
  }
}
~~~

Nếu không có properties, **$ifNull** đưa vào mảng rỗng; **$map** trả []; **$arrayToObject** trả {}.

### 8.3. Nếu một name xuất hiện hai lần

~~~javascript
properties: [
  { name: "color", value: "black" },
  { name: "color", value: "white" }
]
~~~

**$arrayToObject** giữ **white** theo quy tắc last-wins. Nếu domain yêu cầu lưu mọi lựa chọn của một tên field, định dạng object không phù hợp làm nguồn dữ liệu duy nhất; có thể cần giữ dạng array hoặc mô hình multivalued.

### 8.4. Kiểm soát chất lượng đầu vào

Trước khi dùng tên thuộc tính do client cung cấp làm field name của MongoDB:

- Kiểm tra **name là string hợp lệ**.
- Giới hạn độ dài tên và số lượng attributes.
- Chỉ cho phép ký tự theo chính sách nghiệp vụ.
- Không cho phép tên reserved như **_id**, **tenantId**, **permissions** nếu đầu ra sẽ được merge vào document gốc.
- Có chính sách rõ ràng với duplicate names.
- Không nhận raw aggregation expression từ client thay cho một danh sách tên/giá trị.
- Cân nhắc rủi ro field name chứa dấu chấm, dấu **$** hoặc byte null và các hạn chế của query/update/index theo phiên bản MongoDB.

**MongoDB hỗ trợ tên field đặc biệt trong một số ngữ cảnh/version**, nhưng việc cho phép chúng tùy ý không đồng nghĩa mọi driver, index, export format hoặc thao tác dotted path đều xử lý thuận lợi. API nhập liệu thông thường nên dùng naming policy rõ ràng.

## 9. $mergeObjects: hợp nhất nhiều object

### 9.1. Cú pháp biểu thức

~~~javascript
{
  $mergeObjects: [
    <objectExpression1>,
    <objectExpression2>,
    ...
  ]
}
~~~

Trong ngữ cảnh expression, **$mergeObjects** hợp nhất các object đầu vào để tạo **một object mới**. Nó đi từ trái sang phải.

Nếu field xuất hiện nhiều lần, giá trị từ **object xuất hiện sau cùng** ghi đè giá trị trước đó.

Ví dụ:

~~~javascript
{
  $mergeObjects: [
    { theme: "light", alerts: true },
    { theme: "dark" },
    { locale: "vi-VN" }
  ]
}
~~~

Kết quả:

~~~javascript
{
  theme: "dark",
  alerts: true,
  locale: "vi-VN"
}
~~~

**theme** từ object thứ hai ghi đè giá trị ở object đầu, còn **alerts** được giữ lại vì các object phía sau không định nghĩa lại field này.

### 9.2. Thực hành với defaults và overrides

Tạo dữ liệu:

~~~javascript
db.app_settings.insertOne({
  _id: "SETTINGS-001",
  tenantId: "T1",
  defaults: {
    theme: "light",
    locale: "en-US",
    alertsEnabled: true
  },
  overrides: {
    theme: "dark",
    locale: "vi-VN"
  }
});
~~~

Tính cấu hình:

~~~javascript
db.app_settings.aggregate([
  { $match: { _id: "SETTINGS-001" } },
  {
    $project: {
      _id: 0,
      effectiveSettings: {
        $mergeObjects: [
          "$defaults",
          "$overrides"
        ]
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  effectiveSettings: {
    theme: "dark",
    locale: "vi-VN",
    alertsEnabled: true
  }
}
~~~

**$mergeObjects** có thể đọc field path trong từng document, không yêu cầu các object luôn được viết inline trong pipeline.

### 9.3. Ba tầng cấu hình: system → tenant → request

~~~javascript
db.app_settings.aggregate([
  { $match: { _id: "SETTINGS-001" } },
  {
    $project: {
      effectiveSettings: {
        $mergeObjects: [
          { theme: "light", locale: "en-US", pageSize: 20 },
          "$overrides",
          { pageSize: 50 }
        ]
      }
    }
  }
]);
~~~

Thứ tự này quy định:

~~~text
System defaults    (ưu tiên thấp)
      |
      v
Tenant overrides
      |
      v
Request overrides  (ưu tiên cao)
~~~

Field **pageSize** cuối cùng bằng 50, theme/locale lấy từ tenant override nếu có.

Trong thực tế, **request overrides** phải được validate/allowlist, vì không nên cho client ghi đè các field như permission, securityMode hoặc tenantId chỉ bằng một object tự do.

### 9.4. $mergeObjects bỏ qua operand null

~~~javascript
{
  $mergeObjects: [
    { a: 1 },
    null,
    { b: 2 }
  ]
}
~~~

Kết quả:

~~~javascript
{ a: 1, b: 2 }
~~~

Nếu **mọi operand** đều null:

~~~javascript
{
  $mergeObjects: [null, null]
}
~~~

thì kết quả là **{}**.

Vì vậy phép merge trong trường hợp cấu hình tùy chọn có thể hoạt động khi một số object không tồn tại:

~~~javascript
{
  $mergeObjects: [
    "$defaults",
    "$overrides"
  ]
}
~~~

Nếu một field không có hoặc null, MongoDB bỏ qua operand null tương ứng. **Tuy nhiên**, nếu operand là string hoặc array không phải dạng hỗ trợ trong vị trí đó, không nên giả định nó bị bỏ qua như null; có thể báo lỗi kiểu.

### 9.5. Operand null khác với field value null

Đây là khác biệt cực kỳ quan trọng:

~~~javascript
{
  $mergeObjects: [
    { a: 1, b: 2 },
    { b: null }
  ]
}
~~~

Kết quả:

~~~javascript
{ a: 1, b: null }
~~~

**Object {b:null} không phải một operand null.** Nó là object hợp lệ chứa field b, và **b:null ghi đè b:2**.

Nếu nghiệp vụ muốn “null nghĩa là không override”, phải **lọc những field có giá trị null khỏi object override** trước khi merge, hoặc dùng chính sách xử lý khác. Không thể chỉ dựa vào quy tắc “mergeObjects bỏ qua null operands”.

## 10. $mergeObjects chỉ merge nông, không merge đệ quy

Xét hai cấu hình:

~~~javascript
const defaults = {
  theme: "light",
  limits: {
    perDay: 100,
    perHour: 10
  }
};

const override = {
  limits: {
    perDay: 20
  }
};
~~~

Nếu merge:

~~~javascript
{
  $mergeObjects: [
    { limits: { perDay: 100, perHour: 10 } },
    { limits: { perDay: 20 } }
  ]
}
~~~

Kết quả là:

~~~javascript
{
  limits: {
    perDay: 20
  }
}
~~~

Field **limits** ở object thứ hai ghi đè **toàn bộ object limits** ở object thứ nhất. **perHour:10 bị mất**. **$mergeObjects không thực hiện deep merge đệ quy**.

### 10.1. Cách merge sâu có chủ đích ở một cấp xác định

Nếu biết trước cấu trúc **limits**, có thể merge riêng object con:

~~~javascript
db.app_settings.insertOne({
  _id: "SETTINGS-NESTED",
  defaults: {
    theme: "light",
    limits: {
      perDay: 100,
      perHour: 10
    }
  },
  overrides: {
    limits: {
      perDay: 20
    }
  }
});
~~~

Pipeline:

~~~javascript
db.app_settings.aggregate([
  { $match: { _id: "SETTINGS-NESTED" } },
  {
    $project: {
      _id: 0,
      effectiveSettings: {
        $mergeObjects: [
          "$defaults",
          "$overrides",
          {
            limits: {
              $mergeObjects: [
                "$defaults.limits",
                "$overrides.limits"
              ]
            }
          }
        ]
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  effectiveSettings: {
    theme: "light",
    limits: {
      perDay: 20,
      perHour: 10
    }
  }
}
~~~

Giải thích: object thứ ba trong **$mergeObjects bên ngoài** ghi đè field limits bằng kết quả của **$mergeObjects bên trong**, nơi perDay được override nhưng perHour được giữ.

Mẫu này chỉ thực hiện deep merge cho field **limits** đã được chỉ định; không phải một thuật toán deep merge tổng quát ở mọi cấp. Nếu cấu trúc tùy ý rất sâu, cần thiết kế schema/logic rõ ràng hơn.

### 10.2. Đừng nhầm $mergeObjects với $set của update

Một update:

~~~javascript
db.app_settings.updateOne(
  { _id: "SETTINGS-NESTED" },
  {
    $set: {
      "defaults.limits.perDay": 50
    }
  }
);
~~~

nhắm tới **một field lồng nhau cụ thể**. Trong khi **$mergeObjects** dùng trên một object limits sẽ tạo object hợp nhất theo cấp trực tiếp của limits. Hai công cụ giải quyết vấn đề khác nhau.

## 11. Dùng $mergeObjects với $replaceRoot và $replaceWith

### 11.1. Bổ sung mặc định cho document mà không xóa field gốc

Giả sử có collection **events**:

~~~javascript
db.events.insertMany([
  {
    _id: "EV-001",
    type: "LOGIN",
    severity: "INFO"
  },
  {
    _id: "EV-002",
    type: "PAYMENT",
    severity: "ERROR",
    source: "billing"
  }
]);
~~~

Muốn mọi document đầu ra có **source** mặc định **"unknown"** và **processed:false**, nhưng giữ các field thật nếu đã được lưu:

~~~javascript
db.events.aggregate([
  {
    $replaceRoot: {
      newRoot: {
        $mergeObjects: [
          {
            source: "unknown",
            processed: false
          },
          "$$ROOT"
        ]
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả:

~~~javascript
[
  {
    _id: "EV-001",
    type: "LOGIN",
    severity: "INFO",
    source: "unknown",
    processed: false
  },
  {
    _id: "EV-002",
    type: "PAYMENT",
    severity: "ERROR",
    source: "billing",
    processed: false
  }
]
~~~

**$$ROOT** là document đầu vào của stage hiện tại. Đặt **$$ROOT sau object defaults** để field thực tế có quyền ghi đè defaults.

### 11.2. Đảo thứ tự gây ghi đè khác

~~~javascript
{
  $replaceRoot: {
    newRoot: {
      $mergeObjects: [
        "$$ROOT",
        { source: "unknown" }
      ]
    }
  }
}
~~~

Ở đây mọi document đầu ra sẽ có **source:"unknown"**, kể cả EV-002 vốn có source:"billing". Lý do là object mặc định đã được đặt **cuối cùng**, trở thành override cao nhất.

**Thứ tự operand là một phần của business rule**, không chỉ là cách viết.

### 11.3. $replaceRoot và $replaceWith khác gì?

**$replaceRoot**:

~~~javascript
{
  $replaceRoot: {
    newRoot: {
      $mergeObjects: [
        { status: "UNKNOWN" },
        "$$ROOT"
      ]
    }
  }
}
~~~

**$replaceWith**:

~~~javascript
{
  $replaceWith: {
    $mergeObjects: [
      { status: "UNKNOWN" },
      "$$ROOT"
    ]
  }
}
~~~

Hai stages có mục tiêu thay document hiện tại bằng một document mới, với syntax khác nhau. **$mergeObjects** đóng vai trò expression tính document mới; **$replaceRoot/$replaceWith** mới là stage thực hiện thay root.

### 11.4. Bảo đảm field _id khi thay root

Trong một pipeline đọc thông thường, output có thể không cần _id. Nhưng nếu dùng **$replaceRoot** để chuẩn bị ghi qua **$merge/$out**, hoặc muốn giữ liên kết với document nguồn, cần chủ động bảo tồn _id:

~~~javascript
{
  $replaceRoot: {
    newRoot: {
      $mergeObjects: [
        { _id: "$_id", status: "UNKNOWN" },
        "$$ROOT"
      ]
    }
  }
}
~~~

Nếu user cung cấp object override chứa **_id** và được merge sau cùng, nó có thể thay _id của output; khi ghi lại vào collection, điều này có thể gây xung đột hoặc sai identity. Đừng merge raw user object vào root của document có quyền ghi.

## 12. $mergeObjects có dạng accumulator trong $group

Đây là một nguồn nhầm lẫn vì **cùng tên** nhưng cú pháp theo ngữ cảnh khác nhau.

### 12.1. Expression mode: merge nhiều object của một document

~~~javascript
{
  $project: {
    merged: {
      $mergeObjects: [
        "$defaults",
        "$overrides"
      ]
    }
  }
}
~~~

Đây là expression nhận các object của **một document** và trả ra một object mới.

### 12.2. Accumulator mode: merge object từ nhiều document trong một nhóm

Giả sử mỗi công đoạn của một job ghi một phần metrics:

~~~javascript
db.job_metrics.insertMany([
  {
    _id: "M1",
    jobId: "JOB-1",
    step: "PARSE",
    metrics: {
      received: NumberInt(120),
      parsed: NumberInt(118)
    }
  },
  {
    _id: "M2",
    jobId: "JOB-1",
    step: "VALIDATE",
    metrics: {
      valid: NumberInt(110),
      rejected: NumberInt(8)
    }
  },
  {
    _id: "M3",
    jobId: "JOB-1",
    step: "WRITE",
    metrics: {
      inserted: NumberInt(110)
    }
  },
  {
    _id: "M4",
    jobId: "JOB-2",
    step: "PARSE",
    metrics: {
      received: NumberInt(30)
    }
  }
]);
~~~

Mong muốn một document thống kê cho mỗi job:

~~~javascript
db.job_metrics.aggregate([
  {
    $group: {
      _id: "$jobId",
      mergedMetrics: {
        $mergeObjects: "$metrics"
      }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả dự kiến về giá trị:

~~~javascript
[
  {
    _id: "JOB-1",
    mergedMetrics: {
      received: 120,
      parsed: 118,
      valid: 110,
      rejected: 8,
      inserted: 110
    }
  },
  {
    _id: "JOB-2",
    mergedMetrics: {
      received: 30
    }
  }
]
~~~

**$group** là stage, còn **$mergeObjects: "$metrics"** là **accumulator** ghép metrics của nhiều document thuộc một nhóm.

### 12.3. Sự khác nhau về cú pháp

| Ngữ cảnh | Dạng sử dụng |
|---|---|
| **Expression mode** trong **$project/$set/$replaceRoot** | **{$mergeObjects: ["$defaults","$overrides"]}** |
| **Accumulator mode** trong **$group** | **{$mergeObjects: "$metrics"}** |
| Expression mode với một field chứa array các object | **{$mergeObjects: "$listOfObjects"}** (khi expression được giải nghĩa theo dạng array cần merge) |

Ở dạng accumulator, toán tử xử lý object từ **các document trong nhóm**. Ở dạng expression, toán tử xử lý các object được trả về bởi expression của **document hiện tại**.

### 12.4. Cẩn trọng với field trùng trong các document được group

Giả sử một job có hai metrics documents:

~~~javascript
{ jobId: "JOB-1", metrics: { count: 10 } }
{ jobId: "JOB-1", metrics: { count: 20 } }
~~~

**$mergeObjects accumulator không cộng 10 + 20**. Nó tạo object có field count từ lần merge cuối tương ứng với luồng thực thi.

Nếu business rule cần **cộng số đếm**, dùng **$sum** hoặc một quy trình aggregation có ý nghĩa về đơn vị dữ liệu. Nếu cần chọn **phiên bản metrics mới nhất**, định nghĩa thứ tự/thời điểm rõ ràng và xử lý trùng theo một chiến lược được kiểm soát, không dựa vào thứ tự kết quả group ngẫu nhiên.

Trong ví dụ job_metrics đầu tiên, mỗi step ghi **những tên field khác nhau**, nên kết quả không phụ thuộc xung đột giữa các field metrics.

### 12.5. $mergeObjects không thay thế mọi accumulator

~~~javascript
// Không tự cộng các giá trị cùng key:
{ $mergeObjects: "$metrics" }
~~~

Khác với:

~~~javascript
// Cộng một field số qua nhiều document:
{ $sum: "$metrics.received" }
~~~

Chọn accumulator dựa vào ý nghĩa nghiệp vụ:

- **Gộp các field khác tên:** $mergeObjects.
- **Cộng giá trị số:** $sum.
- **Tính trung bình:** $avg.
- **Giữ các giá trị thành array:** $push.
- **Lấy tập giá trị phân biệt:** $addToSet.
- **Chọn giá trị đầu/cuối theo thứ tự có chủ đích:** $first/$last với quy tắc sắp xếp phù hợp.

## 13. $mergeObjects có thể nhận một array các object ở expression mode

Không bắt buộc phải viết trước số object cần merge. Giả sử document có:

~~~javascript
{
  _id: "DOC-1",
  patches: [
    { a: 1 },
    { b: 2 },
    { a: 3 }
  ]
}
~~~

Khi field **patches** là array các BSON documents, có thể sử dụng:

~~~javascript
db.patch_batches.insertOne({
  _id: "DOC-1",
  patches: [
    { a: 1 },
    { b: 2 },
    { a: 3 }
  ]
});

db.patch_batches.aggregate([
  {
    $project: {
      _id: 1,
      result: {
        $mergeObjects: "$patches"
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  _id: "DOC-1",
  result: {
    a: 3,
    b: 2
  }
}
~~~

Trong expression mode, **$mergeObjects** có thể nhận một expression trả về **array các document cần merge**, không chỉ một danh sách operand được viết trực tiếp. Nếu cần xây dựng array bằng **$map/$filter**, phải bảo đảm các phần tử là object phù hợp.

Điều này khác với accumulator trong $group, nơi mỗi document nguồn cung cấp một object để hợp nhất.

## 14. Bài toán tổng hợp: thêm field total vào object tồn kho động

Đây là một mẫu kết hợp đủ ba expressions theo một bài toán cụ thể.

### 14.1. Yêu cầu

Từ document:

~~~javascript
{
  _id: "SKU-001",
  stockByWarehouse: {
    HN: 7,
    HCM: 12,
    DN: 3
  }
}
~~~

muốn tạo object:

~~~javascript
{
  HN: 7,
  HCM: 12,
  DN: 3,
  total: 22
}
~~~

Không biết trước mã kho, nên không thể cộng cố định **$stockByWarehouse.HN + $stockByWarehouse.HCM + ...**.

### 14.2. Pipeline theo từng bước

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "T1",
      status: "ACTIVE"
    }
  },
  {
    $set: {
      stockPairs: {
        $objectToArray: {
          $ifNull: [
            "$stockByWarehouse",
            {}
          ]
        }
      }
    }
  },
  {
    $set: {
      stockPairs: {
        $concatArrays: [
          "$stockPairs",
          [
            {
              k: "total",
              v: {
                $sum: "$stockPairs.v"
              }
            }
          ]
        ]
      }
    }
  },
  {
    $set: {
      stockWithTotal: {
        $arrayToObject: "$stockPairs"
      }
    }
  },
  {
    $project: {
      _id: 1,
      name: 1,
      stockWithTotal: 1
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Kết quả dự kiến:

~~~javascript
[
  {
    _id: "SKU-001",
    name: "Wireless Mouse",
    stockWithTotal: {
      HN: 7,
      HCM: 12,
      DN: 3,
      total: 22
    }
  },
  {
    _id: "SKU-002",
    name: "Mechanical Keyboard",
    stockWithTotal: {
      HCM: 4,
      CT: 6,
      total: 10
    }
  },
  {
    _id: "SKU-004",
    name: "USB Hub",
    stockWithTotal: {
      total: 0
    }
  }
]
~~~

SKU-003 bị loại do status DRAFT. SKU-005 bị loại do thuộc tenant T2.

### 14.3. Theo dõi shape qua các stage

~~~text
stockByWarehouse:
  {HN:7,HCM:12,DN:3}
          |
          | $objectToArray
          v
stockPairs:
  [{k:"HN",v:7},{k:"HCM",v:12},{k:"DN",v:3}]
          |
          | $sum + $concatArrays
          v
stockPairs:
  [..., {k:"total",v:22}]
          |
          | $arrayToObject
          v
stockWithTotal:
  {HN:7,HCM:12,DN:3,total:22}
~~~

Trong pipeline này **$set là stage**, còn **$objectToArray**, **$concatArrays**, **$sum** và **$arrayToObject** là expressions.

### 14.4. Cảnh báo về key total

Nếu một document có **mã kho thật là "total"**, tên key này sẽ xung đột với field tổng vừa thêm. Vì cặp **{k:"total",v:...}** được append cuối mảng, **$arrayToObject** sẽ dùng giá trị tính tổng và ghi đè tồn kho của kho thật tên total.

Để tránh, thiết kế output an toàn hơn:

~~~javascript
{
  stockByWarehouse: {
    HN: 7,
    HCM: 12,
    DN: 3
  },
  totalStock: 22
}
~~~

Đặt **totalStock** ở field riêng bên ngoài bản đồ kho nếu code kho là dữ liệu mở. Ví dụ thêm total vào map chỉ nên dùng khi **"total" là tên reserved** và dữ liệu đầu vào không được dùng tên đó.

## 15. Bài toán tổng hợp: ghép cấu hình mặc định với thuộc tính tùy chọn

Giả sử một sản phẩm có thuộc tính:

~~~javascript
{
  attributes: {
    color: "black",
    wireless: true
  }
}
~~~

Ứng dụng muốn tạo output đầy đủ:

~~~javascript
{
  color: "black",
  wireless: true,
  warrantyMonths: 12,
  countryOfOrigin: "UNKNOWN"
}
~~~

### 15.1. Dùng $mergeObjects để bổ sung mặc định

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      name: 1,
      normalizedAttributes: {
        $mergeObjects: [
          {
            warrantyMonths: 12,
            countryOfOrigin: "UNKNOWN"
          },
          "$attributes"
        ]
      }
    }
  }
]);
~~~

Nếu **attributes** có **warrantyMonths** riêng, giá trị đó được ưu tiên. Nếu attributes **null** như SKU-004, operand null bị bỏ qua và kết quả chỉ chứa defaults.

### 15.2. Khi giá trị null cần hiểu là “chưa có”

Nếu attributes có:

~~~javascript
{
  warrantyMonths: null
}
~~~

thì kết quả merge sẽ có **warrantyMonths:null**, vì field value null ghi đè default 12.

Nếu domain muốn **null được thay bằng default**, phải có bước xử lý riêng:

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      warrantyMonths: {
        $ifNull: [
          "$attributes.warrantyMonths",
          12
        ]
      }
    }
  }
]);
~~~

Trong dữ liệu cấu hình có nhiều key động, muốn bỏ mọi field null trước merge có thể kết hợp **$objectToArray → $filter → $arrayToObject**, rồi mới **$mergeObjects**.

Ví dụ:

~~~javascript
db.products.aggregate([
  {
    $set: {
      nonNullAttributes: {
        $arrayToObject: {
          $filter: {
            input: {
              $objectToArray: {
                $ifNull: ["$attributes", {}]
              }
            },
            as: "pair",
            cond: {
              $ne: ["$$pair.v", null]
            }
          }
        }
      }
    }
  },
  {
    $set: {
      normalizedAttributes: {
        $mergeObjects: [
          {
            warrantyMonths: 12,
            countryOfOrigin: "UNKNOWN"
          },
          "$nonNullAttributes"
        ]
      }
    }
  },
  {
    $project: {
      _id: 1,
      normalizedAttributes: 1
    }
  }
]);
~~~

**Quy tắc loại null** phải được quyết định rõ: trong một số miền nghiệp vụ, null biểu diễn “người dùng cố ý xóa giá trị” thay vì “chưa cung cấp”, nên không thể luôn bỏ qua.

## 16. Kết hợp $objectToArray với $group để thống kê khóa động

Giả sử cần biết **mỗi kho có bao nhiêu sản phẩm còn tồn và tổng tồn bao nhiêu**, chỉ xét SHOP T1.

### 16.1. Pipeline

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "T1",
      status: "ACTIVE"
    }
  },
  {
    $set: {
      warehousePairs: {
        $objectToArray: {
          $ifNull: ["$stockByWarehouse", {}]
        }
      }
    }
  },
  { $unwind: "$warehousePairs" },
  {
    $group: {
      _id: "$warehousePairs.k",
      totalUnits: {
        $sum: "$warehousePairs.v"
      },
      productCount: {
        $sum: 1
      }
    }
  },
  {
    $project: {
      _id: 0,
      warehouse: "$_id",
      totalUnits: 1,
      productCount: 1
    }
  },
  { $sort: { warehouse: 1 } }
]);
~~~

Kết quả:

~~~javascript
[
  { warehouse: "CT", totalUnits: 6, productCount: 1 },
  { warehouse: "DN", totalUnits: 3, productCount: 1 },
  { warehouse: "HCM", totalUnits: 16, productCount: 2 },
  { warehouse: "HN", totalUnits: 7, productCount: 1 }
]
~~~

Lưu ý:

- **$objectToArray** chuyển từng object kho thành mảng cặp.
- **$unwind** tạo một document cho mỗi cặp.
- **$group** gom theo **k** (mã kho), cộng **v** (số lượng).
- **$sum: 1** đếm **số dòng kho** trong dữ liệu trung gian, không phải tự động distinct products nếu một sản phẩm có nhiều record cùng kho trong nguồn.

Trong mô hình object kho, một mã kho không thể xuất hiện hai lần như hai key độc lập theo cách dùng thông thường, nên productCount ở ví dụ này cũng chính là số sản phẩm có field kho đó.

### 16.2. Khi nào nên lưu kho thành array từ đầu?

Nếu mỗi warehouse cần nhiều thuộc tính:

~~~javascript
stock: [
  {
    warehouseId: "HN",
    available: 7,
    reserved: 2,
    lastUpdatedAt: ISODate("2026-07-01T10:00:00Z")
  },
  {
    warehouseId: "HCM",
    available: 12,
    reserved: 1,
    lastUpdatedAt: ISODate("2026-07-01T11:00:00Z")
  }
]
~~~

thì dùng array of embedded documents có thể phù hợp hơn một object với khóa động, nhất là khi:

- thường query theo warehouseId;
- cần nhiều field cho mỗi kho;
- cần index rõ ràng theo các field con;
- cần cập nhật từng phần tử theo điều kiện với **arrayFilters**.

**$objectToArray** giúp thao tác với dynamic object nhưng không có nghĩa **dynamic object luôn là data model tối ưu**.

## 17. Object lồng nhau và giới hạn không đệ quy

### 17.1. Chuyển riêng một object con

Xét:

~~~javascript
{
  attributes: {
    resolution: {
      width: 2560,
      height: 1440
    },
    refreshRate: 144
  }
}
~~~

Muốn chuyển riêng resolution:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-003" } },
  {
    $project: {
      _id: 0,
      resolutionPairs: {
        $objectToArray: "$attributes.resolution"
      }
    }
  }
]);
~~~

Kết quả:

~~~javascript
{
  resolutionPairs: [
    { k: "width", v: 2560 },
    { k: "height", v: 1440 }
  ]
}
~~~

Người viết query phải **chỉ định object con** cần chuyển đổi. **$objectToArray: "$attributes"** ở cấp cha không tự chuyển width và height thành các cặp riêng.

### 17.2. $mergeObjects lồng nhau phải chỉ rõ field

~~~javascript
{
  $mergeObjects: [
    "$defaults",
    "$overrides",
    {
      resolution: {
        $mergeObjects: [
          "$defaults.resolution",
          "$overrides.resolution"
        ]
      }
    }
  ]
}
~~~

Pattern này thực hiện merge sâu **một cấp cụ thể**. Nếu cấu trúc có nhiều object tùy ý ở mọi độ sâu, một giải pháp biểu thức cố định trở nên khó bảo trì. Có thể cần model chuẩn hóa hoặc một bước xử lý ngoài database có quy tắc rõ ràng.

### 17.3. Khi object có key chứa dấu chấm

Document BSON hiện đại có một số khả năng lưu field names đặc biệt trong các phiên bản được hỗ trợ, nhưng **đường dẫn "a.b"** trong nhiều API thường được hiểu là field b nằm dưới a, không phải literal key "a.b".

Khi cần thao tác với field name đặc biệt ở database, MongoDB có **$getField** và **$setField** trong những phiên bản thích hợp. Với input do người dùng cung cấp, cách đơn giản và an toàn hơn trong đa số API là **giới hạn tên key**, ví dụ chỉ cho phép chữ, số và dấu gạch dưới với một prefix đã quy định.

Không dùng raw key từ client làm operator/field path không qua kiểm tra.

## 18. Đầu vào sai kiểu, thiếu field và giá trị BSON

### 18.1. Bảng so sánh hành vi

| Đầu vào | $objectToArray | $arrayToObject | $mergeObjects |
|---|---|---|---|
| Object hợp lệ | Trả array **{k,v}**. | Không đúng kiểu đầu vào trực tiếp; cần array. | Merge object. |
| Object rỗng **{}** | Trả **[]**. | Không đúng kiểu đầu vào. | Có thể tham gia merge, không thêm field. |
| Array **[]** | Không đúng kiểu đầu vào. | Trả **{}**. | Trong expression mode có thể diễn giải là array object rỗng theo dạng operand được hỗ trợ. |
| **null/missing** | Trả **null**. | Trả **null**. | Bỏ qua operand null; nếu tất cả null trả **{}**. |
| String/number bất kỳ | Không phải object nên có thể lỗi. | Không phải array hợp lệ nên có thể lỗi. | Không phải document hợp lệ nên có thể lỗi. |

**Chú ý:** $mergeObjects có nhiều dạng operand tùy ngữ cảnh (mảng các object, array các expressions hoặc accumulator trong group); bảng trên nêu behavior chính. Không áp dụng “array []” như thể đó luôn là một object hợp lệ trong mọi vị trí cú pháp.

### 18.2. Dùng $type để phát hiện dữ liệu sai schema

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      attributesType: {
        $type: "$attributes"
      },
      stockType: {
        $type: "$stockByWarehouse"
      }
    }
  }
]);
~~~

Kết quả có thể gồm **"object"**, **"null"**, **"missing"**, **"array"** hoặc các type khác. Ví dụ SKU-004 có attributes null và stockByWarehouse missing.

### 18.3. $ifNull không sửa được sai kiểu khác null

~~~javascript
{
  $objectToArray: {
    $ifNull: ["$attributes", {}]
  }
}
~~~

Nếu attributes là string **"oops"**, $ifNull giữ string đó, khiến **$objectToArray** nhận input sai kiểu.

Nếu cần xử lý dữ liệu legacy có nhiều kiểu, có thể kiểm tra:

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 1,
      attributePairs: {
        $cond: [
          {
            $eq: [
              { $type: "$attributes" },
              "object"
            ]
          },
          {
            $objectToArray: "$attributes"
          },
          []
        ]
      }
    }
  }
]);
~~~

Trong ứng dụng thật, **silently converting bad input to []** có thể che giấu lỗi dữ liệu. Đôi khi nên báo lỗi, ghi metric hoặc di chuyển document cần sửa thay vì âm thầm bỏ qua.

### 18.4. Giá trị v giữ kiểu dữ liệu nguồn

Khi $objectToArray chuyển:

~~~javascript
{
  number: NumberInt(12),
  createdAt: ISODate("2026-07-01T10:00:00Z"),
  active: true,
  nested: { a: 1 }
}
~~~

thành array:

~~~javascript
[
  { k: "number", v: NumberInt(12) },
  { k: "createdAt", v: ISODate("2026-07-01T10:00:00Z") },
  { k: "active", v: true },
  { k: "nested", v: { a: 1 } }
]
~~~

thì **v không tự chuyển thành string**. Khi $arrayToObject dựng lại, các giá trị BSON có thể được giữ theo kiểu vốn có, trừ khi pipeline có các expression chuyển đổi như **$toString**, **$toInt**, **$toDecimal**.

Không dùng **JSON.stringify** hoặc số ký tự JSON để suy ra kích thước BSON hay type của giá trị.

## 19. Cập nhật document với aggregation pipeline

Ba expressions không chỉ phục vụ pipeline đọc. MongoDB hỗ trợ **update bằng một aggregation pipeline** với một tập stages được phép.

### 19.1. Ví dụ ghi tổng tồn kho vào document

~~~javascript
db.products.updateOne(
  { _id: "SKU-001" },
  [
    {
      $set: {
        totalStock: {
          $sum: {
            $map: {
              input: {
                $objectToArray: {
                  $ifNull: ["$stockByWarehouse", {}]
                }
              },
              as: "pair",
              in: "$$pair.v"
            }
          }
        }
      }
    }
  ]
);
~~~

Khác với **aggregate()**, updateOne với một mảng stages **thực sự ghi field totalStock** của document khớp nếu thao tác thành công. Vì một document được cập nhật trong một operation, MongoDB áp dụng tính nguyên tử ở cấp document tương ứng.

### 19.2. Merge cấu hình trong update pipeline

~~~javascript
db.app_settings.updateOne(
  { _id: "SETTINGS-001" },
  [
    {
      $set: {
        effectiveSettings: {
          $mergeObjects: [
            "$defaults",
            "$overrides"
          ]
        }
      }
    }
  ]
);
~~~

Lệnh ghi effectiveSettings vào document. Không nhầm lẫn:

- **$set** ở đây là **stage được phép trong update pipeline**;
- **$mergeObjects** là expression tính object mới;
- Đây không phải một lệnh **aggregate() chỉ đọc**.

### 19.3. Không đưa mọi aggregation stage vào update pipeline

Update pipeline chỉ cho phép một nhóm stages phục vụ biến đổi document, chẳng hạn **$set/$addFields**, **$project/$unset** và **$replaceRoot/$replaceWith** theo tài liệu MongoDB. Không thể tự do đặt **$group** hoặc **$lookup** vào update pipeline rồi kỳ vọng MongoDB chấp nhận.

Khi nghiệp vụ cần tổng hợp nhiều document rồi ghi ra collection khác, phải cân nhắc **$merge/$out** trong aggregation theo các quy tắc và quyền riêng, hoặc một workflow backend được kiểm soát.

### 19.4. Không dùng expression để bypass authorization

Nếu application nhận danh sách dynamic keys từ người dùng rồi ghi lại qua **$arrayToObject/$mergeObjects**, phải bảo vệ **_id**, **tenantId**, **ownerId**, **roles**, **permissions** và các field hệ thống. Tên field do client cung cấp không được phép tự động trở thành quyền sửa toàn bộ document.

Tạo object đích từ những field đã xác minh hoặc chỉ merge vào **một namespace thuộc tính giới hạn** như **customAttributes**, không merge raw user input vào **$$ROOT** của document quan trọng.

## 20. Java Sync Driver: dùng BSON để xây object expressions

MongoDB Java Sync Driver dùng **List<Bson>** làm pipeline. Có thể dùng **Aggregates** builders hoặc tạo **org.bson.Document** cho những biểu thức lồng nhau.

### 20.1. $objectToArray + $sum bằng Java

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;
import org.bson.conversions.Bson;

import java.util.List;

public final class StockReport {
    public static void run(MongoDatabase database) {
        MongoCollection<Document> products =
                database.getCollection("products");

        Bson match = new Document(
                "$match",
                new Document("tenantId", "T1")
        );

        Bson toPairs = new Document(
                "$set",
                new Document(
                        "warehousePairs",
                        new Document(
                                "$objectToArray",
                                new Document(
                                        "$ifNull",
                                        List.of(
                                                "$stockByWarehouse",
                                                new Document()
                                        )
                                )
                        )
                )
        );

        Bson sumStock = new Document(
                "$set",
                new Document(
                        "totalStock",
                        new Document("$sum", "$warehousePairs.v")
                )
        );

        Bson project = new Document(
                "$project",
                new Document("_id", 1)
                        .append("name", 1)
                        .append("totalStock", 1)
        );

        List<Bson> pipeline = List.of(
                match,
                toPairs,
                sumStock,
                project
        );

        for (Document row : products.aggregate(pipeline)) {
            System.out.println(row.toJson());
        }
    }
}
~~~

Phân tích Java:

- **new Document("$match", ...)** là một stage.
- **new Document("$set", ...)** là stage.
- **new Document("$objectToArray", ...)** là expression.
- **new Document("$ifNull", ...)** là expression phụ.
- **new Document("$sum", ...)** là expression tính tổng trên mảng giá trị của một document.

Chú ý phân biệt **org.bson.Document** của driver với Java **Document** khác trong ứng dụng. Khi chuyển dữ liệu báo cáo vào DTO, phải xem loại BSON của các giá trị số và dữ liệu lồng nhau.

### 20.2. $arrayToObject trong Java

~~~java
import org.bson.Document;
import org.bson.conversions.Bson;
import java.util.List;

Bson project = new Document(
        "$project",
        new Document(
                "attributesObject",
                new Document(
                        "$arrayToObject",
                        new Document(
                                "$map",
                                new Document("input", "$properties")
                                        .append("as", "prop")
                                        .append(
                                                "in",
                                                new Document(
                                                        "k",
                                                        "$$prop.name"
                                                ).append(
                                                        "v",
                                                        "$$prop.value"
                                                )
                                        )
                        )
                )
        )
);
~~~

Ví dụ tương ứng với collection **import_rows** có field properties dạng array. Tên **"$$prop.name"** phải được viết nguyên văn để MongoDB hiểu là biến bên trong $map, không phải đường dẫn của Java object.

### 20.3. $mergeObjects trong Java

~~~java
Bson mergeDefaults = new Document(
        "$project",
        new Document(
                "effectiveSettings",
                new Document(
                        "$mergeObjects",
                        List.of(
                                new Document(
                                        "theme",
                                        "light"
                                ).append(
                                        "pageSize",
                                        20
                                ),
                                "$overrides"
                        )
                )
        )
);
~~~

Operand **Document defaults** đi trước **"$overrides"** nên override của document có quyền ưu tiên cao hơn.

### 20.4. Dùng cursor thay vì nạp mọi kết quả vào RAM

~~~java
for (Document row : products.aggregate(pipeline)) {
    processResult(row);
}
~~~

Với báo cáo lớn, xử lý từng document từ cursor có thể tránh materialize toàn bộ kết quả ở client. Tuy nhiên **$group/$sort** là các stage có thể cần nhiều bộ nhớ và thời gian phía server; dùng cursor không làm chi phí tính toán trên server tự biến mất.

## 21. Spring Data MongoDB: AggregationOperation và MongoTemplate

Spring Data MongoDB cung cấp **Aggregation**, **AggregationOperation**, **MongoTemplate** và mapping entity. Có thể dùng builders cho những stage đơn giản hoặc **custom AggregationOperation** để viết chính xác các MongoDB expressions phức tạp.

### 21.1. Ví dụ custom stage cho $objectToArray

~~~java
import java.util.List;

import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.aggregation.Aggregation;
import org.springframework.data.mongodb.core.aggregation.AggregationOperation;
import org.springframework.data.mongodb.core.aggregation.AggregationResults;
import org.springframework.data.mongodb.core.query.Criteria;

public final class StockReportService {
    private final MongoTemplate mongoTemplate;

    public StockReportService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public List<Document> stockTotals() {
        AggregationOperation toPairs = context ->
                new Document(
                        "$set",
                        new Document(
                                "pairs",
                                new Document(
                                        "$objectToArray",
                                        new Document(
                                                "$ifNull",
                                                List.of(
                                                        "$stockByWarehouse",
                                                        new Document()
                                                )
                                        )
                                )
                        )
                );

        AggregationOperation sumStock = context ->
                new Document(
                        "$set",
                        new Document(
                                "totalStock",
                                new Document("$sum", "$pairs.v")
                        )
                );

        Aggregation aggregation = Aggregation.newAggregation(
                Aggregation.match(
                        Criteria.where("tenantId").is("T1")
                ),
                toPairs,
                sumStock,
                Aggregation.project(
                        "name",
                        "totalStock"
                )
        );

        AggregationResults<Document> results =
                mongoTemplate.aggregate(
                        aggregation,
                        "products",
                        Document.class
                );

        return results.getMappedResults();
    }
}
~~~

Đoạn code minh họa các pipeline stages; **$objectToArray** và **$sum** là expressions nằm trong các **$set stages**.

### 21.2. Cẩn thận khi dùng custom BSON và entity mapping

**Custom AggregationOperation** tạo raw BSON theo **field names thực tế trên MongoDB**. Nếu entity Java có **@Field("stock_by_warehouse")** nhưng code raw stage truy cập **"$stockByWarehouse"**, query có thể không đọc được field như mong đợi.

Trong hệ thống dùng custom converters hoặc annotation, hãy:

1. Kiểm tra tên BSON field thực tế.
2. Dùng builder/mapping context phù hợp hoặc ánh xạ field tường minh.
3. Không đoán kiểu đầu ra khi giá trị v có Decimal128, Date hoặc embedded document.
4. Chọn DTO riêng cho output aggregation khi shape không còn giống entity đầu vào.

### 21.3. Tạo expression $mergeObjects trong custom stage

~~~java
AggregationOperation mergeSettings = context ->
        new Document(
                "$project",
                new Document(
                        "effectiveSettings",
                        new Document(
                                "$mergeObjects",
                                List.of(
                                        "$defaults",
                                        "$overrides"
                                )
                        )
                )
        );
~~~

Stage này có thể được đưa vào **Aggregation.newAggregation(...)** và chạy với MongoTemplate. Nếu defaults/overrides là raw object fields, schema/mapper phải lưu chúng đúng BSON type.

### 21.4. Khi nào ưu tiên builder và khi nào raw BSON?

| Cách | Ưu điểm | Lưu ý |
|---|---|---|
| **Aggregation builders** | Dễ đọc, hỗ trợ mapping và refactor trong Java. | Không phải mọi operator mới đều có cùng API ở mọi phiên bản Spring Data. |
| **Custom AggregationOperation / raw Document** | Biểu diễn trực tiếp syntax MongoDB, linh hoạt với expression mới. | Cần quản lý field names, mapping, lỗi gõ và version compatibility. |
| **Pipeline tách thành method nhỏ** | Kiểm soát shape của từng stage, tái sử dụng. | Phải giữ rõ hợp đồng đầu vào/đầu ra của mỗi method. |

Với logic chuyển đổi động phức tạp, nên dùng các hàm xây **Bson/Document expression** có tên rõ ràng hơn là tạo một biểu thức lồng nhau hàng chục cấp trong controller.

## 22. Hiệu năng, kích thước và index

### 22.1. Ba expressions không tự tạo index trên key động

Ví dụ:

~~~javascript
db.products.aggregate([
  {
    $set: {
      pairs: {
        $objectToArray: "$attributes"
      }
    }
  },
  {
    $match: {
      "pairs.k": "color"
    }
  }
]);
~~~

**pairs** là field được tính trong pipeline, không tồn tại như một field lưu sẵn trong document nguồn. Index thường trên một field gốc không tự biến mọi giá trị của **pairs.k** thành các khóa index có thể dùng như một index vật lý trên output được tính.

Nếu ứng dụng thường xuyên query một thuộc tính cụ thể, cân nhắc:

- Query trực tiếp theo **attributes.color** và tạo index phù hợp;
- Dùng **wildcard index** trong những trường hợp field động phù hợp;
- Thiết kế mảng **{name,value}** với multikey index khi pattern truy vấn theo thuộc tính;
- Tái cấu trúc dữ liệu thành collection thuộc tính riêng nếu kích thước/tần suất truy cập đòi hỏi.

Đừng coi $objectToArray là cách thay thế không tốn chi phí cho một chiến lược indexing.

### 22.2. $match nên đặt sớm khi có thể

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "T1",
      status: "ACTIVE"
    }
  },
  {
    $set: {
      pairs: {
        $objectToArray: {
          $ifNull: ["$attributes", {}]
        }
      }
    }
  }
]);
~~~

Nếu có index phù hợp theo tenant/status, **$match** sớm có thể giảm số document cần biến đổi.

Ngược lại, nếu $match phụ thuộc vào field vừa tính, nó phải chạy sau stage tạo field (trừ khi optimizer có phép biến đổi hợp lệ). Cần phân biệt **điều kiện truy vấn nguồn** và **điều kiện trên kết quả được tính**.

### 22.3. Object có rất nhiều khóa

Một object chứa hàng chục nghìn key khi chuyển bằng **$objectToArray** sẽ thành mảng có tương ứng nhiều phần tử {k,v}, có thêm overhead của field k/v và cấu trúc array.

Hệ quả:

- Kết quả trung gian có thể lớn hơn document gốc.
- **$unwind** có thể tạo rất nhiều document trung gian.
- **$arrayToObject** dựng object lớn có thể vượt giới hạn kích thước BSON.
- **$mergeObjects** với nhiều operand lớn tiêu tốn CPU/memory.
- Các stage blocking như **$group/$sort** có thêm áp lực bộ nhớ.

MongoDB có giới hạn kích thước BSON document thông dụng **16 MiB**, và một số aggregation stages có các giới hạn bộ nhớ/spill riêng. Không dùng một pipeline chuyển đổi object để hợp nhất tùy ý hàng triệu cặp vào một document.

### 22.4. $group accumulator và memory

~~~javascript
db.job_metrics.aggregate([
  {
    $group: {
      _id: "$jobId",
      mergedMetrics: {
        $mergeObjects: "$metrics"
      }
    }
  }
]);
~~~

Nếu mỗi job có rất nhiều metrics keys độc nhất, **mergedMetrics** có thể phình to. **allowDiskUse** không xóa giới hạn kích thước cuối cùng của BSON document.

Khi lượng key quá lớn, cân nhắc trả về nhiều documents, group theo cấp nhỏ hơn hoặc lưu thống kê đã tổng hợp bằng schema chuyên biệt.

### 22.5. Dùng explain để quan sát kế hoạch

~~~javascript
db.products.explain("executionStats").aggregate([
  { $match: { tenantId: "T1", status: "ACTIVE" } },
  {
    $set: {
      warehousePairs: {
        $objectToArray: {
          $ifNull: ["$stockByWarehouse", {}]
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      totalStock: {
        $sum: "$warehousePairs.v"
      }
    }
  }
]);
~~~

Quan sát query plan, số documents/keys examined, output cardinality và các chỉ số khác tùy phiên bản/engine. Với collection lab chỉ vài document, planner có thể chọn collection scan; không thể kết luận về hiệu năng production chỉ từ một dataset rất nhỏ.

### 22.6. Khi nào tính ở server và khi nào tính ở ứng dụng?

Tính trong MongoDB aggregation phù hợp khi:

- cần lọc/summarize dữ liệu ngay gần nơi lưu;
- chỉ trả một số trường đã được xử lý thay vì truyền object lớn;
- muốn tái sử dụng biểu thức trong pipeline báo cáo;
- chuyển đổi tương đối ngắn và có thể đo rõ chi phí.

Tính trong Java phù hợp khi:

- dữ liệu đã được lấy về vì một nghiệp vụ khác;
- thuật toán deep merge phức tạp hoặc nhiều quy tắc domain;
- cần kiểm tra kiểu/tên khóa nghiêm ngặt;
- việc dựng BSON expression quá phức tạp, khó bảo trì hơn code typed.

Không có lựa chọn tối ưu chung; phải xét độ lớn dữ liệu, mạng, index, chi phí server và khả năng bảo trì.

## 23. Bảo vệ hệ thống khi tên field là dữ liệu động

### 23.1. Tên field không chỉ là một chuỗi vô hại

Khi một mảng người dùng gửi được biến thành object bằng **$arrayToObject**, các giá trị **k** trở thành tên field thật. Nếu sau đó được merge vào document:

~~~javascript
{
  $mergeObjects: [
    "$$ROOT",
    "$userAttributes"
  ]
}
~~~

thì userAttributes có thể ghi đè những field quan trọng nếu không có kiểm soát.

Ví dụ userAttributes:

~~~javascript
{
  tenantId: "OTHER-TENANT",
  role: "ADMIN"
}
~~~

Nếu merge vào root không có whitelist, output có thể bị thay tenantId hoặc role. Nếu pipeline được dùng trong thao tác ghi, hậu quả có thể là lỗi phân quyền hoặc dữ liệu bị hỏng.

### 23.2. Thiết kế namespace riêng cho custom attributes

Thay vì merge vào **$$ROOT**, đặt kết quả ở field **customAttributes**:

~~~javascript
db.import_rows.aggregate([
  {
    $project: {
      _id: 1,
      customAttributes: {
        $arrayToObject: {
          $map: {
            input: {
              $ifNull: ["$properties", []]
            },
            as: "property",
            in: {
              k: "$$property.name",
              v: "$$property.value"
            }
          }
        }
      }
    }
  }
]);
~~~

Trong API thực tế, cần validate **name/value** trước khi ghi, giới hạn tên, kích thước, số phần tử và duplicate keys. **Namespace riêng** giúp giảm phạm vi tác động nhưng không thay thế kiểm tra quyền và schema.

### 23.3. Không cho client gửi pipeline tùy ý

Ứng dụng không nên lấy một raw array aggregation stages do client gửi rồi chạy trực tiếp, vì có thể:

- gây truy vấn tốn tài nguyên;
- lộ dữ liệu không thuộc tenant;
- thay đổi shape khiến downstream xử lý sai;
- dùng stage ghi như **$merge/$out** khi quyền cho phép;
- vượt giới hạn kích thước và thời gian.

Hãy nhận các input nghiệp vụ như **selectedKeys, filters, sourceMap** dưới dạng DTO, kiểm tra allowlist rồi tự tạo pipeline từ những operator được phép.

## 24. So sánh nhanh ba expressions

| Tiêu chí | $objectToArray | $arrayToObject | $mergeObjects |
|---|---|---|---|
| Đầu vào | Một object. | Một array cặp key/value. | Nhiều object hoặc array object theo dạng expression; có dạng accumulator. |
| Đầu ra | Array các **{k,v}**. | Một object. | Một object. |
| Công dụng chính | Duyệt khóa động. | Dựng lại khóa động. | Ghép cấu hình, defaults, fragments. |
| Có merge đệ quy? | Không áp dụng; chỉ cấp field trực tiếp. | Không, dựng field ở một cấp. | **Không**, merge nông. |
| Xử lý null | Trả null nếu input null/missing. | Trả null nếu input null/missing. | Bỏ qua null operands; all-null trả {}. |
| Object/mảng rỗng | **{} → []**. | **[] → {}**. | Object rỗng không thêm field. |
| Duplicate keys | Không tạo key trùng mới từ object nguồn theo mô hình thông thường. | Last-wins trong phiên bản hiện đại. | Last operand wins. |
| Dùng trong $project/$set? | Có. | Có. | Có. |
| Dùng như accumulator trong $group? | Không. | Không. | **Có**. |
| Rủi ro | Array lớn, field sai kiểu. | Key không hợp lệ, trùng key, data injection. | Ghi đè field, null overwrite, nested object bị thay toàn bộ. |

### 24.1. Khi chọn expression

~~~text
“Cần duyệt tất cả key của object, không biết trước tên key”
    -> $objectToArray

“Có các cặp {k,v}, muốn dựng lại object”
    -> $arrayToObject

“Cần defaults + overrides theo thứ tự”
    -> $mergeObjects

“Cần đổi tên hoặc lọc key động”
    -> $objectToArray + $map/$filter + $arrayToObject

“Cần gom nhiều object từ nhiều record cùng nhóm”
    -> $group + $mergeObjects accumulator

“Cần deep merge tùy ý mọi cấp”
    -> Không mặc định giao cho $mergeObjects;
       thiết kế quy tắc merge theo từng cấp hoặc xử lý riêng.
~~~

## 25. Những lỗi thường gặp

### 25.1. Dùng $objectToArray như một stage riêng

**Sai:**

~~~javascript
db.products.aggregate([
  { $objectToArray: "$attributes" }
]);
~~~

**$objectToArray** là expression, không phải stage. **Đúng:**

~~~javascript
db.products.aggregate([
  {
    $project: {
      attributePairs: {
        $objectToArray: "$attributes"
      }
    }
  }
]);
~~~

### 25.2. Nghĩ $objectToArray đi xuyên mọi object lồng nhau

Với **{resolution:{width:2560,height:1440}}**, nó chỉ tạo một cặp **{k:"resolution",v:{...}}**. Muốn chuyển resolution, phải chỉ rõ object con.

### 25.3. Đưa array sai format vào $arrayToObject

**Sai:**

~~~javascript
[
  { name: "color", value: "red" }
]
~~~

Đây không phải array **{k,v}**. Hãy dùng **$map** để đổi thành **{k:"color",v:"red"}** trước khi dựng object.

### 25.4. Không tính đến duplicate keys

Hai cặp có cùng k không tạo multimap. **Giá trị cuối thắng**. Nếu không muốn ghi đè, validate trước hoặc chọn representation khác.

### 25.5. Đặt defaults sau overrides

~~~javascript
{
  $mergeObjects: [
    "$overrides",
    "$defaults"
  ]
}
~~~

Trong thứ tự này, **defaults ghi đè những field trùng của overrides**. Muốn override thắng, dùng **[defaults, overrides]**.

### 25.6. Nghĩ null field không ghi đè

**$mergeObjects bỏ qua operand null**, nhưng object **{x:null}** vẫn ghi đè field x. Muốn null có nghĩa “không có override”, phải xử lý field null.

### 25.7. Mong $mergeObjects deep merge nested object

**{limits:{perDay:20}}** ghi đè toàn bộ field limits cũ khi cùng key. Muốn giữ perHour, merge riêng object limits.

### 25.8. Trộn accumulator và expression syntax

Trong **$group**:

~~~javascript
{
  $group: {
    _id: "$jobId",
    combined: {
      $mergeObjects: "$metrics"
    }
  }
}
~~~

Đây là accumulator trên nhiều documents. Trong **$project**, **$mergeObjects** trên một danh sách object là expression. Không suy ra cùng một ngữ cảnh thực thi chỉ vì tên toán tử giống nhau.

### 25.9. Dùng $unwind khi chỉ cần tổng trong từng document

Muốn tính tổng kho của **mỗi product**, có thể dùng **$objectToArray + $sum** mà không unwind. Nếu unwind rồi group phải xử lý document không có kho và giữ đúng grouping key, dễ phức tạp hơn.

### 25.10. Ghi đè khóa hệ thống khi merge

Đừng merge raw attributes vào **$$ROOT** nếu có thể chứa **_id/tenantId/permissions**. Dùng whitelist và namespace dành riêng cho custom data.

### 25.11. Tưởng pipeline đọc sẽ ghi vào collection

~~~javascript
db.products.aggregate([
  {
    $set: {
      totalStock: 22
    }
  }
]);
~~~

Nó chỉ thay output của **aggregate**. Nếu muốn lưu, dùng update pipeline hoặc workflow ghi có kiểm soát.

### 25.12. Quên đo kích thước output BSON

Một object hoặc array trung gian quá lớn có thể vượt giới hạn document đầu ra hoặc giới hạn bộ nhớ của stage. Không nên dựng một document “mọi attribute của toàn collection” chỉ vì $mergeObjects cho phép ghép các object.

## 26. Bài thực hành

### Bài 1 — Đọc kho dưới dạng array

Từ SKU-001, trả về **warehousePairs**:

~~~javascript
db.products.aggregate([
  { $match: { _id: "SKU-001" } },
  {
    $project: {
      warehousePairs: {
        $objectToArray: "$stockByWarehouse"
      }
    }
  }
]);
~~~

Đối chiếu output có ba cặp **HN, HCM, DN**.

### Bài 2 — Tính tổng tồn kho không cần biết mã kho

Dùng **$objectToArray** và **$sum** để tính totalStock cho T1. Kết quả kỳ vọng SKU-001 = 22, SKU-002 = 10, SKU-003 = 0, SKU-004 = 0.

### Bài 3 — Lấy các kho có hàng

Dùng **$filter** trên array {k,v} để chỉ giữ cặp có **v > 0**. Nếu một mã kho có v = 0, nó có được trả về không?

### Bài 4 — Chuyển array {name,value} thành object

Từ document IMPORT-001 trong collection import_rows, tạo **propertiesAsObject** có color, size và weightKg. Gợi ý dùng **$map** và **$arrayToObject**.

### Bài 5 — Đổi tên mọi key

Tạo output **attr_color**, **attr_warrantyMonths**, **attr_wireless** từ attributes của SKU-001 mà không hardcode từng field. Gợi ý:

~~~text
$objectToArray -> $map với $concat -> $arrayToObject
~~~

### Bài 6 — Xóa một key nội bộ

Tạo document thử nghiệm có attributes:

~~~javascript
{
  color: "black",
  internalNote: "do-not-publish",
  size: "M"
}
~~~

Dùng **$filter** để loại key internalNote rồi dựng object public. Nêu vì sao với hệ thống nhiều loại dữ liệu nhạy cảm nên ưu tiên allowlist thay vì chỉ denylist một key.

### Bài 7 — Merge defaults và overrides

Cho:

~~~javascript
defaults: {
  theme: "light",
  locale: "en-US"
}

overrides: {
  theme: "dark"
}
~~~

Dùng **$mergeObjects** tạo object có theme dark và locale en-US. Đảo thứ tự hai operands và giải thích sự thay đổi.

### Bài 8 — Quan sát null operand khác null value

Tính kết quả:

~~~javascript
{ $mergeObjects: [ { x: 1 }, null ] }
{ $mergeObjects: [ { x: 1 }, { x: null } ] }
~~~

Vì sao kết quả không giống nhau?

### Bài 9 — Merge object lồng nhau

Cho:

~~~javascript
defaults: {
  limits: { perDay: 100, perHour: 10 }
}

overrides: {
  limits: { perDay: 20 }
}
~~~

Dự đoán kết quả của **$mergeObjects trực tiếp**. Sau đó viết biểu thức **$mergeObjects lồng nhau** để giữ perHour = 10.

### Bài 10 — $mergeObjects accumulator

Trên collection job_metrics, group theo jobId và merge các object metrics. Giải thích vì sao nó không cộng trường trùng theo mặc định.

### Bài 11 — Kết quả theo kho

Sử dụng **$objectToArray + $unwind + $group** để tính tổng số lượng theo từng warehouse. Đối chiếu T1: CT = 6, DN = 3, HCM = 16, HN = 7.

### Bài 12 — Xử lý field sai kiểu

Chèn một document thử nghiệm có attributes là string **"invalid"**. Quan sát sự khác nhau giữa:

~~~javascript
{ $objectToArray: { $ifNull: ["$attributes", {}] } }
~~~

và cách dùng **$type + $cond** để chỉ chuyển khi attributes là object. Thảo luận khi nào nên báo lỗi thay vì âm thầm thay bằng array rỗng.

### Bài 13 — API nhận dynamic key

Một API nhận properties:

~~~json
[
  {"name": "color", "value": "black"},
  {"name": "tenantId", "value": "ATTACKER"}
]
~~~

Thiết kế quy tắc validate để chỉ ghi customAttributes, không để tên tenantId của người dùng ghi đè field hệ thống.

### Bài 14 — Java và Spring Data

Viết pipeline Java tạo **totalStock** từ stockByWarehouse và in kết quả. Dùng một implementation với **org.bson.Document**, một implementation với **MongoTemplate**. Phân biệt Java **List<Bson> pipeline stages** với các **BSON expression Documents**.

## 27. Câu hỏi ôn tập

1. **$objectToArray** nhận kiểu dữ liệu gì và trả kiểu gì?
2. Trong output của **$objectToArray**, hai field **k** và **v** đại diện cho điều gì?
3. **$objectToArray** có tự chuyển mọi object lồng nhau thành các cặp k/v hay không?
4. Kết quả của **$objectToArray: {}** là gì?
5. Khi input là null/missing, **$objectToArray** xử lý như thế nào?
6. **$arrayToObject** chấp nhận hai dạng phần tử array nào?
7. Vì sao **[{name:"color",value:"red"}]** cần xử lý trước khi truyền vào $arrayToObject?
8. **$arrayToObject** làm gì khi mảng có hai phần tử cùng k?
9. **$arrayToObject: []** có trả một object rỗng không?
10. **$mergeObjects** quyết định thứ tự ưu tiên field trùng như thế nào?
11. Operand null khác object có field null ở điểm nào?
12. **$mergeObjects** có deep merge nested objects không?
13. Khi nào dùng **$mergeObjects accumulator trong $group** thay vì expression trong $project?
14. Tại sao **$mergeObjects** không thay thế **$sum** cho dữ liệu metrics có field số trùng nhau?
15. Để đổi tên mọi key động trong attributes, có thể kết hợp những expressions nào?
16. Khi nào nên dùng **$unwind** sau **$objectToArray**?
17. Với input object kho không có field, vì sao **$ifNull: ["$stockByWarehouse", {}]** hữu ích?
18. Tại sao **$mergeObjects** với raw user attributes có thể gây rủi ro bảo mật?
19. Cần làm gì nếu một field name được tạo từ k chứa dấu chấm hoặc ký tự **$**?
20. Một aggregation có **$set** thay đổi collection nguồn không?
21. Làm sao quan sát MongoDB có phải xử lý quá nhiều document trước khi biến đổi dynamic object?
22. Khi nào mô hình **array of {name,value}** phù hợp hơn object có dynamic keys?

## 28. Tổng kết

Ba biểu thức này tạo nên một nhóm công cụ mạnh để xử lý document có **cấu trúc field động**:

~~~text
$objectToArray
    Object -> [{k, v}, ...]
    Dùng để duyệt, lọc, đổi tên và tính trên key động.

$arrayToObject
    [{k, v}, ...] hoặc [[key, value], ...] -> Object
    Dùng để dựng lại object sau khi biến đổi array.
    Key trùng: giá trị cuối thắng.

$mergeObjects
    Object A + Object B + ... -> Object mới
    Dùng cho defaults/overrides, hợp nhất object fragments.
    Field trùng: operand sau thắng.
    Null operand được bỏ qua, field có value null vẫn ghi đè.
    Không thực hiện deep merge tự động.
~~~

Để sử dụng đúng:

1. **Phân biệt stage và expression:** $project/$set/$group là stages; $objectToArray/$arrayToObject/$mergeObjects tính giá trị bên trong các stage. **$mergeObjects** còn có dạng accumulator khi group.
2. **Chọn mô hình dữ liệu hợp lý:** dynamic object thuận tiện cho map đơn giản; array of objects thuận tiện cho thông tin phong phú và truy vấn theo thuộc tính.
3. **Kiểm tra kiểu đầu vào:** object, array, null, missing và string không thể tráo đổi tùy ý.
4. **Cẩn thận với thứ tự:** last-wins của $arrayToObject và $mergeObjects có thể quyết định kết quả nghiệp vụ.
5. **Không kỳ vọng deep merge:** muốn giữ field nested chưa bị override, phải xử lý rõ cấp object tương ứng.
6. **Chặn key không hợp lệ hoặc nhạy cảm:** dynamic field names cần validation, namespace riêng và quyền truy cập.
7. **Kiểm soát kích thước:** chuyển object lớn thành array, unwind và group có thể tăng đáng kể lượng dữ liệu trung gian.
8. **Đo trên workload thật:** đặt filter có index phù hợp trước các phép biến đổi khi semantics cho phép; sử dụng explain và metrics.

### Tài liệu chính thức

- [MongoDB $objectToArray](https://www.mongodb.com/docs/manual/reference/operator/aggregation/objectToArray/) — cấu trúc **{k,v}**, giới hạn không đệ quy.
- [MongoDB $arrayToObject](https://www.mongodb.com/docs/manual/reference/operator/aggregation/arrayToObject/) — hai dạng đầu vào, mảng rỗng, duplicate keys.
- [MongoDB $mergeObjects (expression)](https://www.mongodb.com/docs/manual/reference/expression/mergeobjects/) — merge nhiều objects, null operands và thứ tự ưu tiên.
- [MongoDB $mergeObjects (accumulator)](https://www.mongodb.com/docs/manual/reference/operator/aggregation/mergeObjects/) — ghép objects qua nhiều documents trong grouping stages.
- [MongoDB $map](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/) và [$filter](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/) — biến đổi và lọc phần tử mảng.
- [MongoDB $replaceRoot](https://www.mongodb.com/docs/manual/reference/operator/aggregation/replaceRoot/) — thay document root bằng expression.
- [MongoDB $getField](https://www.mongodb.com/docs/manual/reference/operator/aggregation/getField/) và [$setField](https://www.mongodb.com/docs/manual/reference/operator/aggregation/setField/) — làm việc với field names đặc biệt ở những phiên bản hỗ trợ.
- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) và [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/) — luồng stage và giới hạn tài nguyên.
- [MongoDB Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — xây aggregation pipeline bằng Java.
- [Spring Data MongoDB Aggregation Framework](https://docs.spring.io/spring-data/mongodb/reference/mongodb/aggregation-framework.html) — aggregation với MongoTemplate và Java mapping.

Khi gặp một object có tập key không cố định, hãy đặt câu hỏi: **“Cần duyệt key, tạo key mới hay ghép các object?”**. Dùng **$objectToArray** để biến khóa thành dữ liệu có thể duyệt, dùng **$arrayToObject** để dựng lại cấu trúc, và dùng **$mergeObjects** để định nghĩa rõ ưu tiên giữa những nguồn dữ liệu. Kết hợp ba expressions đúng ngữ cảnh giúp pipeline MongoDB vừa linh hoạt vừa có thể giải thích, kiểm thử và vận hành an toàn.
