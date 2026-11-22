# Thiết kế document, validator và các truy vấn nghiệp vụ chính trong MongoDB

## 1. Đề bài thực hành tổng hợp

Bài này xây dựng một cơ sở dữ liệu **quản lý đơn hàng đa tenant**. Mỗi tenant là một cửa hàng; khách hàng, catalog sản phẩm và đơn hàng phải được truy vấn trong đúng phạm vi tenant. Ứng dụng cần lưu sản phẩm và giá đã chốt trong đơn, tìm đơn theo mã, liệt kê theo trạng thái, xem lịch sử khách, tìm đơn chứa SKU, báo cáo doanh thu, cập nhật trạng thái và giữ tồn kho an toàn.

Các thành phần cần hoàn thành:

1. Thiết kế ba collections `customers`, `products`, `orders`.
2. Lựa chọn **embed** thông tin line item và snapshot giá, **reference** đến catalog/customer.
3. Tạo `$jsonSchema` validator kiểm tra BSON type, field bắt buộc, enum và giới hạn array.
4. Tạo bộ dữ liệu mẫu với **7 đơn hàng** thuộc tenants A/B và expected results rõ ràng.
5. Thiết kế unique/compound/multikey indexes theo query matrix.
6. Viết truy vấn `find`, `countDocuments`, `distinct`, aggregation, `$lookup`, paging và `explain`.
7. Bảo vệ concurrent writes bằng unique index, atomic conditional update, version và transaction khi cần.
8. Kiểm chứng schema validation và phân biệt điều kiện DB đảm bảo được với domain logic.
9. Viết test cases, checklist hiệu năng/bảo mật và kế hoạch migration.

**Quy tắc:** toàn bộ lệnh `drop()`, `collMod`, thay schema, seed data và cập nhật trong bài chỉ chạy trên **lab được phép**. Không sử dụng production URI hoặc database đang chứa dữ liệu thật.

### 1.1. Yêu cầu nghiệp vụ

| Use case | Filter chính | Kết quả | Đặc tính |
| --- | --- | --- | --- |
| Mở đơn theo mã | tenantId + orderNo | Một đơn | Unique |
| Danh sách PAID | tenantId + status | Trang mới nhất | Sort ổn định |
| Lịch sử khách | tenantId + customerId | Nhiều đơn | Không lộ tenant |
| Đơn có SKU | tenantId + items.sku | Nhiều đơn | Multikey |
| Đơn theo ngày | tenantId + createdAt range | Nhiều đơn | UTC boundary |
| Doanh thu | tenantId + trạng thái thanh toán | Số Decimal128 | Aggregation |
| Top SKU | tenantId + trạng thái | Units/amount | Unwind/group |
| Chuyển trạng thái | tenant + ID + version | Modified count | Atomicity |
| Giữ tồn kho | tenantId + sku + stock | Modified count | Không âm |
| Đặt hàng | Mã/stock/price | Order mới | Idempotency |

### 1.2. Bất biến cần bảo vệ

- `(tenantId, orderNo)` không được trùng.
- Mỗi đơn phải có ít nhất một line item; quantity là số nguyên dương.
- Tiền phải lưu bằng Decimal128, không lẫn `double`/`string`.
- `total` phải bằng tổng `lineTotal` (trong mô hình lab không có tax/shipping/discount).
- `lineTotal = unitPrice × quantity`.
- `status` chỉ thuộc `DRAFT`, `PLACED`, `PAID`, `SHIPPED`, `CANCELLED`.
- Workflow không được nhảy trạng thái vô lý.
- Đơn phải lưu giá **tại thời điểm mua**, độc lập với giá catalog hiện tại.
- Trừ stock không được đưa số lượng kho xuống âm.
- Request user A không được đọc, sửa hoặc xóa dữ liệu B.
- Client retry phải không tạo nhiều đơn cùng một request nghiệp vụ.

Không có một tính năng duy nhất giải quyết toàn bộ: `$jsonSchema` kiểm tra cấu trúc, index unique kiểm tra trùng, atomic update/transaction kiểm tra concurrency và **service/authorization** kiểm tra business workflow.

---

## 2. Mô hình dữ liệu và quyết định embed/reference

```text
order_design_lab
│
├── customers
│     _id, tenantId, displayName, email, createdAt
│
├── products
│     _id, tenantId, sku, name, currentPrice, stock, active
│
└── orders
      _id, tenantId, orderNo, schemaVersion, version
      status, currency, total, createdAt, updatedAt
      customer { customerId, displayName }  <-- snapshot
      items [
          { sku, name, quantity, unitPrice, lineTotal }
      ]                                     <-- snapshot
      shipping { city }
      payment { method, paidAt }             <-- optional
      tags, note                             <-- optional
```

### 2.1. Tại sao embed items?

Khi mở một đơn, ứng dụng phải thấy **tên hàng, số lượng và giá lúc khách đặt**. Nếu chỉ giữ `productId`, mỗi lần đọc cần lấy giá hiện tại hoặc join rồi có thể hiển thị sai lịch sử.

Nhờ embed, một lần đọc order lấy được toàn bộ details, và cập nhật nhiều fields trong **cùng document** có atomicity ở cấp document.

Giới hạn: array dài không giới hạn gây document growth và có thể chạm mức **16 MiB** của một BSON document. Vì vậy lab giới hạn 20 items/order; production cần điều chỉnh theo business và profile thực.

### 2.2. Tại sao reference product/customer?

Catalog `products` là source of truth cho giá hiện tại và tồn kho. `customers` lưu thông tin khách hiện tại. Order chỉ lưu những trường cần cho snapshot/historical record.

Ví dụ giá HEAD tenant A thay từ 89.90 thành 95.00:

- `products.currentPrice`: 95.00.
- `orders.items.unitPrice` của đơn cũ: **vẫn 89.90**.

Đây là denormalization **có chủ đích**, không phải duplication tùy tiện.

### 2.3. Khi nào không nên embed?

- Array phát triển không giới hạn, cần phân trang thành phần con.
- Phần tử được sửa độc lập với tần suất cao.
- Quan hệ many-to-many phức tạp cần tra cứu nhiều hướng.
- Đối tượng tham chiếu có kích thước quá lớn hoặc chứa PII không nên copy.
- Nhu cầu analytics khác hẳn OLTP.

Có thể dùng `$lookup` cho admin/reporting nhưng không bắt buộc join trong hot path.

---

## 3. Chọn BSON types

| Trường | BSON type | Trong Java | Ghi chú |
| --- | --- | --- | --- |
| `_id`, `tenantId`, `orderNo`, `sku` | `string` | `String` | Mã nghiệp vụ |
| `schemaVersion`, `version`, `quantity`, `stock` | `int` | `int`/`Integer` | 32-bit integer |
| `unitPrice`, `lineTotal`, `total`, `currentPrice` | `decimal` | `BigDecimal` | Tiền chính xác |
| `createdAt`, `updatedAt`, `paidAt` | `date` | `Instant`/`Date` | Thời điểm UTC |
| `active` | `bool` | `boolean` | Cờ |
| `items`, `tags` | `array` | `List` | Các phần tử có schema |
| `customer`, `shipping`, `payment` | `object` | Embedded classes/records | Nhóm fields |

Ví dụ đúng:

```javascript
{
  quantity: NumberInt(2),
  unitPrice: NumberDecimal("89.90"),
  createdAt: ISODate("2026-10-20T08:00:00Z")
}
```

Không tự thay `NumberDecimal("89.90")` bằng JavaScript `89.90`, vì sau này phép tính tiền có thể bị sai số binary floating-point. Trong Java, dùng `new BigDecimal("89.90")` và rounding policy rõ.

`Date` trong BSON là milliseconds UTC; để lọc một ngày ở `Asia/Ho_Chi_Minh` phải chuyển ranh giới ngày địa phương sang UTC **trước** khi query.

---

## 4. Tạo database và collections lab

Chạy các đoạn sau trong **mongosh**. Không chạy `drop()` trên môi trường ngoài lab.

```javascript
var lab = db.getSiblingDB("order_design_lab");

lab.orders.drop();
lab.products.drop();
lab.customers.drop();
```

Lệnh `drop()` có thể trả `false` nếu collection chưa tồn tại, không có nghĩa hệ thống lỗi. Quan trọng là phải xác minh **MongoDB URI/host đang là test**.

### 4.1. Validator chính: orders

```javascript
lab.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "schemaVersion", "version",
        "tenantId", "orderNo", "customer", "items",
        "total", "currency", "status",
        "createdAt", "updatedAt", "shipping"
      ],
      additionalProperties: false,
      properties: {
        _id: {
          bsonType: "string",
          minLength: 1
        },
        _class: {
          bsonType: "string"
        },
        schemaVersion: {
          bsonType: "int",
          minimum: 1,
          maximum: 1
        },
        version: {
          bsonType: "int",
          minimum: 1
        },
        tenantId: {
          bsonType: "string",
          minLength: 1
        },
        orderNo: {
          bsonType: "string",
          minLength: 1
        },
        customer: {
          bsonType: "object",
          required: ["customerId", "displayName"],
          additionalProperties: false,
          properties: {
            customerId: { bsonType: "string", minLength: 1 },
            displayName: { bsonType: "string", minLength: 1 }
          }
        },
        items: {
          bsonType: "array",
          minItems: 1,
          maxItems: 20,
          items: {
            bsonType: "object",
            required: [
              "sku", "name", "quantity",
              "unitPrice", "lineTotal"
            ],
            additionalProperties: false,
            properties: {
              sku: { bsonType: "string", minLength: 1 },
              name: { bsonType: "string", minLength: 1 },
              quantity: {
                bsonType: "int",
                minimum: 1
              },
              unitPrice: {
                bsonType: "decimal",
                minimum: NumberDecimal("0")
              },
              lineTotal: {
                bsonType: "decimal",
                minimum: NumberDecimal("0")
              }
            }
          }
        },
        total: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        currency: {
          enum: ["USD"]
        },
        status: {
          enum: [
            "DRAFT", "PLACED", "PAID",
            "SHIPPED", "CANCELLED"
          ]
        },
        createdAt: { bsonType: "date" },
        updatedAt: { bsonType: "date" },
        shipping: {
          bsonType: "object",
          required: ["city"],
          additionalProperties: false,
          properties: {
            city: { bsonType: "string", minLength: 1 }
          }
        },
        payment: {
          bsonType: "object",
          required: ["method", "paidAt"],
          additionalProperties: false,
          properties: {
            method: {
              enum: ["CARD", "CASH", "BANK_TRANSFER"]
            },
            paidAt: { bsonType: "date" }
          }
        },
        tags: {
          bsonType: "array",
          maxItems: 10,
          items: { bsonType: "string" }
        },
        note: {
          bsonType: ["string", "null"]
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

### 4.2. Giải thích validator

| Keyword | Điều kiện |
| --- | --- |
| `required` | Field phải tồn tại |
| `bsonType` | Kiểu BSON phải đúng |
| `enum` | Chỉ cho phép một tập giá trị |
| `minItems`/`maxItems` | Giới hạn array |
| `minimum` | Số không nhỏ hơn ngưỡng |
| `additionalProperties:false` | Không chấp nhận field ngoài schema |
| `validationLevel:"strict"` | Validate các writes được kiểm tra |
| `validationAction:"error"` | Từ chối writes không hợp lệ |

Một số lưu ý:

- `_id` phải có trong `properties` khi dùng `additionalProperties:false`.
- `_class` được phép như string để phục vụ Spring Data type mapping mặc định. Nếu framework ghi `_class` trong **embedded objects**, nested validator cũng cần phù hợp; team có thể dùng custom type mapper hoặc cấu hình alias và integration test.
- `schemaVersion` mô tả **version của schema**, còn `version` bảo vệ cập nhật đồng thời.
- `items` là array các **documents**, mỗi phần tử bắt buộc `sku/name/quantity/unitPrice/lineTotal`.
- `payment` là optional, nhưng nếu đã có payment thì cần `method` và `paidAt`.
- Enum `currency=["USD"]` cố ý giới hạn bài lab. Production nhiều currencies cần mở rộng và dùng policy kế toán rõ.

**Giới hạn:** `$jsonSchema` ở đây **không kiểm tra** `total == sum(lineTotal)`, `lineTotal == price × quantity`, customer/product reference tồn tại, tenant authorization hoặc trạng thái chuyển hợp lệ. Đó là domain/transaction logic, không phải schema shape.

---

## 5. Validators cho products và customers

### 5.1. Products

```javascript
lab.createCollection("products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "sku", "name",
        "currentPrice", "stock", "active"
      ],
      additionalProperties: false,
      properties: {
        _id: { bsonType: "string" },
        _class: { bsonType: "string" },
        tenantId: { bsonType: "string", minLength: 1 },
        sku: { bsonType: "string", minLength: 1 },
        name: { bsonType: "string", minLength: 1 },
        currentPrice: {
          bsonType: "decimal",
          minimum: NumberDecimal("0")
        },
        stock: {
          bsonType: "int",
          minimum: 0
        },
        active: { bsonType: "bool" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

`stock` không âm theo validator nhưng để chống hai requests đồng thời cần **atomic stock update** có predicate.

### 5.2. Customers

```javascript
lab.createCollection("customers", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "_id", "tenantId", "displayName",
        "email", "createdAt"
      ],
      additionalProperties: false,
      properties: {
        _id: { bsonType: "string" },
        _class: { bsonType: "string" },
        tenantId: { bsonType: "string", minLength: 1 },
        displayName: { bsonType: "string", minLength: 1 },
        email: { bsonType: "string", minLength: 3 },
        createdAt: { bsonType: "date" }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
```

Email được normalize/lowercase và kiểm tra bằng ứng dụng. `minLength:3` không phải email validation chuẩn. Nếu muốn uniqueness case-insensitive, thiết kế collation hoặc canonical field và index tương ứng.

### 5.3. Xác nhận server đã lưu validator

```javascript
lab.getCollectionInfos({ name: "orders" });
lab.getCollectionInfos({ name: "products" });
lab.getCollectionInfos({ name: "customers" });
```

Kết quả cho biết các collection options thực. Chỉ nhìn source code có lệnh `createCollection` chưa chứng minh validator đang tồn tại trên đúng database.

---

## 6. Seed catalogs

Chạy sau khi đã tạo các collections.

### 6.1. Products: giá khác nhau giữa tenants

```javascript
lab.products.insertMany([
  {
    _id: "A-PHEAD", tenantId: "A", sku: "HEAD",
    name: "Tai nghe",
    currentPrice: NumberDecimal("89.90"),
    stock: NumberInt(12),
    active: true
  },
  {
    _id: "A-PCABLE", tenantId: "A", sku: "CABLE",
    name: "Cáp",
    currentPrice: NumberDecimal("9.50"),
    stock: NumberInt(50),
    active: true
  },
  {
    _id: "A-PMOUSE", tenantId: "A", sku: "MOUSE",
    name: "Chuột",
    currentPrice: NumberDecimal("24.00"),
    stock: NumberInt(30),
    active: true
  },
  {
    _id: "B-PHEAD", tenantId: "B", sku: "HEAD",
    name: "Tai nghe",
    currentPrice: NumberDecimal("99.90"),
    stock: NumberInt(20),
    active: true
  },
  {
    _id: "B-PCABLE", tenantId: "B", sku: "CABLE",
    name: "Cáp",
    currentPrice: NumberDecimal("11.50"),
    stock: NumberInt(25),
    active: true
  }
]);
```

`sku="HEAD"` ở hai tenants là hợp lệ; định danh business catalog là `(tenantId,sku)`.

### 6.2. Customers

```javascript
lab.customers.insertMany([
  {
    _id: "A-C01", tenantId: "A",
    displayName: "Ngọc", email: "ngoc@example.test",
    createdAt: ISODate("2026-10-01T08:00:00Z")
  },
  {
    _id: "A-C02", tenantId: "A",
    displayName: "Minh", email: "minh@example.test",
    createdAt: ISODate("2026-10-02T08:00:00Z")
  },
  {
    _id: "B-C01", tenantId: "B",
    displayName: "Lan", email: "lan@example.test",
    createdAt: ISODate("2026-10-01T09:00:00Z")
  },
  {
    _id: "B-C02", tenantId: "B",
    displayName: "Hải", email: "hai@example.test",
    createdAt: ISODate("2026-10-03T09:00:00Z")
  }
]);

lab.products.countDocuments({});  // 5
lab.customers.countDocuments({}); // 4
```

Dùng domain `.test` để không nhầm với email thật.

---

## 7. Seed 7 orders

### 7.1. Đơn của tenant A

```javascript
lab.orders.insertMany([
  {
    _id: "A-O1001",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-001",
    customer: { customerId: "A-C01", displayName: "Ngọc" },
    items: [
      {
        sku: "HEAD", name: "Tai nghe",
        quantity: NumberInt(2),
        unitPrice: NumberDecimal("89.90"),
        lineTotal: NumberDecimal("179.80")
      },
      {
        sku: "CABLE", name: "Cáp",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("9.50"),
        lineTotal: NumberDecimal("9.50")
      }
    ],
    total: NumberDecimal("189.30"),
    currency: "USD",
    status: "PLACED",
    createdAt: ISODate("2026-10-20T08:00:00Z"),
    updatedAt: ISODate("2026-10-20T08:00:00Z"),
    shipping: { city: "Hà Nội" },
    tags: ["priority"]
  },
  {
    _id: "A-O1002",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-002",
    customer: { customerId: "A-C02", displayName: "Minh" },
    items: [
      {
        sku: "MOUSE", name: "Chuột",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("24.00"),
        lineTotal: NumberDecimal("24.00")
      },
      {
        sku: "CABLE", name: "Cáp",
        quantity: NumberInt(2),
        unitPrice: NumberDecimal("9.50"),
        lineTotal: NumberDecimal("19.00")
      }
    ],
    total: NumberDecimal("43.00"),
    currency: "USD",
    status: "PAID",
    createdAt: ISODate("2026-10-21T08:00:00Z"),
    updatedAt: ISODate("2026-10-21T10:00:00Z"),
    shipping: { city: "Đà Nẵng" },
    payment: {
      method: "CARD",
      paidAt: ISODate("2026-10-21T10:00:00Z")
    }
  },
  {
    _id: "A-O1003",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-003",
    customer: { customerId: "A-C01", displayName: "Ngọc" },
    items: [
      {
        sku: "HEAD", name: "Tai nghe",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("89.90"),
        lineTotal: NumberDecimal("89.90")
      }
    ],
    total: NumberDecimal("89.90"),
    currency: "USD",
    status: "SHIPPED",
    createdAt: ISODate("2026-10-23T08:00:00Z"),
    updatedAt: ISODate("2026-10-24T11:00:00Z"),
    shipping: { city: "Hà Nội" },
    payment: {
      method: "BANK_TRANSFER",
      paidAt: ISODate("2026-10-23T10:00:00Z")
    }
  },
  {
    _id: "A-O1004",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-004",
    customer: { customerId: "A-C02", displayName: "Minh" },
    items: [
      {
        sku: "CABLE", name: "Cáp",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("9.50"),
        lineTotal: NumberDecimal("9.50")
      }
    ],
    total: NumberDecimal("9.50"),
    currency: "USD",
    status: "CANCELLED",
    createdAt: ISODate("2026-10-24T08:00:00Z"),
    updatedAt: ISODate("2026-10-24T10:00:00Z"),
    shipping: { city: "Hải Phòng" },
    note: "Khách hủy trước thanh toán"
  },
  {
    _id: "A-O1005",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-005",
    customer: { customerId: "A-C01", displayName: "Ngọc" },
    items: [
      {
        sku: "CABLE", name: "Cáp",
        quantity: NumberInt(3),
        unitPrice: NumberDecimal("9.50"),
        lineTotal: NumberDecimal("28.50")
      }
    ],
    total: NumberDecimal("28.50"),
    currency: "USD",
    status: "PAID",
    createdAt: ISODate("2026-10-25T08:00:00Z"),
    updatedAt: ISODate("2026-10-25T09:00:00Z"),
    shipping: { city: "Hà Nội" },
    payment: {
      method: "CASH",
      paidAt: ISODate("2026-10-25T09:00:00Z")
    }
  }
]);
```

### 7.2. Đơn của tenant B

```javascript
lab.orders.insertMany([
  {
    _id: "B-O2001",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "B",
    orderNo: "BO-001",
    customer: { customerId: "B-C01", displayName: "Lan" },
    items: [
      {
        sku: "HEAD", name: "Tai nghe",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("99.90"),
        lineTotal: NumberDecimal("99.90")
      }
    ],
    total: NumberDecimal("99.90"),
    currency: "USD",
    status: "PAID",
    createdAt: ISODate("2026-10-22T08:00:00Z"),
    updatedAt: ISODate("2026-10-22T11:00:00Z"),
    shipping: { city: "TP. Hồ Chí Minh" },
    payment: {
      method: "CARD",
      paidAt: ISODate("2026-10-22T11:00:00Z")
    }
  },
  {
    _id: "B-O2002",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "B",
    orderNo: "BO-002",
    customer: { customerId: "B-C02", displayName: "Hải" },
    items: [
      {
        sku: "CABLE", name: "Cáp",
        quantity: NumberInt(2),
        unitPrice: NumberDecimal("11.50"),
        lineTotal: NumberDecimal("23.00")
      }
    ],
    total: NumberDecimal("23.00"),
    currency: "USD",
    status: "PLACED",
    createdAt: ISODate("2026-10-26T08:00:00Z"),
    updatedAt: ISODate("2026-10-26T08:00:00Z"),
    shipping: { city: "Cần Thơ" }
  }
]);
```

### 7.3. Bảng baseline

| ID | Tenant | Status | Customer | Total USD |
| --- | --- | --- | --- | ---: |
| A-O1001 | A | PLACED | A-C01 | 189.30 |
| A-O1002 | A | PAID | A-C02 | 43.00 |
| A-O1003 | A | SHIPPED | A-C01 | 89.90 |
| A-O1004 | A | CANCELLED | A-C02 | 9.50 |
| A-O1005 | A | PAID | A-C01 | 28.50 |
| B-O2001 | B | PAID | B-C01 | 99.90 |
| B-O2002 | B | PLACED | B-C02 | 23.00 |

```javascript
lab.orders.countDocuments({});                // 7
lab.orders.countDocuments({ tenantId: "A" }); // 5
lab.orders.countDocuments({ tenantId: "B" }); // 2
lab.orders.countDocuments({
  tenantId: "A",
  status: "PAID"
}); // 2
```

Nếu chạy các bài tập update, insert hoặc transaction phía sau, **baseline này sẽ thay đổi**. Khi đối chiếu lại hãy reset/reseed đúng collections lab.

---

## 8. Indexes cho workload quan trọng

### 8.1. Order lookup unique

```javascript
lab.orders.createIndex(
  { tenantId: 1, orderNo: 1 },
  {
    name: "uq_tenant_orderNo",
    unique: true
  }
);
```

### 8.2. Danh sách theo status/time

```javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1,
    _id: -1
  },
  { name: "ix_tenant_status_time_id" }
);
```

### 8.3. Lịch sử khách

```javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    "customer.customerId": 1,
    createdAt: -1,
    _id: -1
  },
  { name: "ix_tenant_customer_time_id" }
);
```

### 8.4. SKU trong array

```javascript
lab.orders.createIndex(
  {
    tenantId: 1,
    "items.sku": 1,
    createdAt: -1
  },
  { name: "ix_tenant_items_sku_time" }
);
```

Đây là **multikey index** vì `items` là array. Một document có thể tạo nhiều index entries; có giới hạn khi compound index bao gồm nhiều array paths. Cần đo write amplification và thực tế sort plan.

### 8.5. Catalog uniqueness

```javascript
lab.products.createIndex(
  { tenantId: 1, sku: 1 },
  { name: "uq_tenant_sku", unique: true }
);

lab.customers.createIndex(
  { tenantId: 1, email: 1 },
  { name: "uq_tenant_email", unique: true }
);
```

Trong lab email lowercase. Với yêu cầu không phân biệt hoa/thường, cần canonical key hoặc collation/unique index tương ứng; MongoDB không tự chuẩn hóa email.

### 8.6. Kiểm tra indexes thực tế

```javascript
lab.orders.getIndexes();
lab.products.getIndexes();
lab.customers.getIndexes();
```

**Index được khai báo không đồng nghĩa đã tạo thành công**: unique index có thể thất bại vì dữ liệu cũ trùng. Một index cũng không tự được MongoDB dùng cho mọi query; đọc `explain`.

---

## 9. Truy vấn 1: tìm một đơn theo mã

```javascript
lab.orders.findOne({
  tenantId: "A",
  orderNo: "AO-001"
});
```

Kỳ vọng `_id="A-O1001"`.

Vì unique business key chỉ đúng **trong tenant**, không truy vấn `{orderNo:"AO-001"}` từ API mà bỏ tenant. Tenant phải lấy từ authenticated principal/authorization layer, không tin client tự chọn.

Tìm theo `_id` cũng nên có tenant scope ở tầng nghiệp vụ:

```javascript
lab.orders.findOne({
  _id: "A-O1001",
  tenantId: "A"
});
```

---

## 10. Truy vấn 2: danh sách PAID với projection

```javascript
lab.orders.find(
  {
    tenantId: "A",
    status: "PAID"
  },
  {
    _id: 1,
    orderNo: 1,
    status: 1,
    total: 1,
    "customer.displayName": 1,
    createdAt: 1
  }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.toArray();
```

Kỳ vọng:

1. A-O1005, total 28.50.
2. A-O1002, total 43.00.

Vì sao projection? List view không cần full items, payment hay shipping; giảm network và memory. **Không save lại partial entity** như thể nó chứa đủ fields.

Thêm `_id` vào sort để làm tie-breaker khi nhiều orders có cùng `createdAt`.

Index tương ứng: `ix_tenant_status_time_id`.

---

## 11. Truy vấn 3: lịch sử của một khách hàng

```javascript
lab.orders.find({
  tenantId: "A",
  "customer.customerId": "A-C01"
})
.sort({ createdAt: -1, _id: -1 })
.toArray();
```

Kỳ vọng theo thứ tự mới nhất:

1. A-O1005.
2. A-O1003.
3. A-O1001.

`customer.displayName` trong order là snapshot lịch sử. Nếu tên customer hiện tại đổi, dữ liệu order cũ không tự thay; UX chọn snapshot hay tên hiện tại theo yêu cầu.

Index: `{tenantId:1,"customer.customerId":1,createdAt:-1,_id:-1}`.

---

## 12. Truy vấn 4: khoảng thời gian

Tìm đơn tenant A từ 21/10/2026 đến **trước** 25/10/2026 theo UTC:

```javascript
lab.orders.find({
  tenantId: "A",
  createdAt: {
    $gte: ISODate("2026-10-21T00:00:00Z"),
    $lt: ISODate("2026-10-25T00:00:00Z")
  }
})
.sort({ createdAt: 1, _id: 1 })
.toArray();
```

Kỳ vọng: A-O1002, A-O1003, A-O1004.

Dùng khoảng `[from, to)` vì boundary rõ, không cần giả định “23:59:59.999”. Với business timezone Việt Nam, chuyển local day boundaries sang UTC trước khi query.

**Lưu ý index:** `{tenantId:1,status:1,createdAt:-1}` không phải lúc nào hỗ trợ date-only query hiệu quả vì thiếu predicate trên `status`. Nếu query date-only là hot path, cân nhắc index `{tenantId:1,createdAt:-1,_id:-1}` và đo Explain.

---

## 13. Truy vấn 5: tìm order chứa SKU

```javascript
lab.orders.find({
  tenantId: "A",
  "items.sku": "CABLE"
}, {
  _id: 1,
  orderNo: 1,
  items: 1
})
.sort({ createdAt: -1 })
.toArray();
```

Kỳ vọng tập IDs: A-O1001, A-O1002, A-O1004, A-O1005.

### 13.1. `$elemMatch` khi cần cùng phần tử

Tìm order có một line item `sku="CABLE"` và `quantity>=3`:

```javascript
lab.orders.find({
  tenantId: "A",
  items: {
    $elemMatch: {
      sku: "CABLE",
      quantity: { $gte: NumberInt(3) }
    }
  }
}).toArray();
```

Kỳ vọng **A-O1005**.

Hai điều kiện độc lập `"items.sku":"CABLE"` và `"items.quantity":{$gte:3}` **có thể match hai phần tử khác nhau** trong cùng array. `$elemMatch` bảo đảm cùng một phần tử.

---

## 14. Truy vấn 6: count và status distribution

### 14.1. Count nhanh cho một filter

```javascript
lab.orders.countDocuments({
  tenantId: "A",
  status: "PAID"
});
// 2
```

Không cần tải list về Java rồi gọi `size()`.

### 14.2. Phân bố số đơn theo status

```javascript
lab.orders.aggregate([
  { $match: { tenantId: "A" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1, _id: 1 } }
]).toArray();
```

Kỳ vọng tenant A:

| Status | Count |
| --- | ---: |
| PAID | 2 |
| CANCELLED | 1 |
| PLACED | 1 |
| SHIPPED | 1 |

### 14.3. Distinct status

```javascript
lab.orders.distinct("status", {
  tenantId: "A"
});
```

Danh sách có bốn trạng thái trên, nhưng thứ tự trả về không phải business contract.

---

## 15. Truy vấn 7: doanh thu theo tenant

**Định nghĩa cho lab:** đơn có trạng thái `PAID` hoặc `SHIPPED` được tính vào “doanh thu đã thanh toán”. Đây không mặc định là cách hạch toán production khi có refunds/chargebacks/taxes.

### 15.1. Tenant A

```javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "A",
      status: { $in: ["PAID", "SHIPPED"] }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      orders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  }
]).toArray();
```

Kỳ vọng:

- 3 orders: A-O1002, A-O1003, A-O1005.
- `revenue = NumberDecimal("161.40")`.
- Phép tính: 43.00 + 89.90 + 28.50 = 161.40.

### 15.2. Tất cả tenants, chỉ dành cho admin có quyền

```javascript
lab.orders.aggregate([
  {
    $match: {
      status: { $in: ["PAID", "SHIPPED"] }
    }
  },
  {
    $group: {
      _id: "$tenantId",
      orders: { $sum: 1 },
      revenue: { $sum: "$total" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

| Tenant | Orders | Revenue USD |
| --- | ---: | ---: |
| A | 3 | 161.40 |
| B | 1 | 99.90 |

Tổng là **261.30**. Multi-tenant user bình thường không được truy vấn global data nếu chưa được cấp quyền.

---

## 16. Truy vấn 8: top SKU đã bán

Dùng `$unwind` để chuyển mỗi line item thành pipeline record, sau đó nhóm theo SKU:

```javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "A",
      status: { $in: ["PAID", "SHIPPED"] }
    }
  },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$items.sku",
      units: { $sum: "$items.quantity" },
      grossLineValue: { $sum: "$items.lineTotal" }
    }
  },
  { $sort: { units: -1, _id: 1 } }
]).toArray();
```

Kỳ vọng:

| SKU | Units | Gross line USD |
| --- | ---: | ---: |
| CABLE | 5 | 47.50 |
| HEAD | 1 | 89.90 |
| MOUSE | 1 | 24.00 |

CABLE: A-O1002 có 2, A-O1005 có 3. A-O1001 còn PLACED, A-O1004 CANCELLED nên không tính.

### 16.1. Với dữ liệu cực lớn

`$unwind` tạo nhiều intermediate records. Dashboard refresh liên tục trên hàng triệu đơn có thể cần pre-aggregation hoặc materialized reports thay vì chạy full scan mỗi request. Phải kiểm thử correctness khi có refunds, cancellations và updates.

---

## 17. Truy vấn 9: doanh thu theo ngày thanh toán

```javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "A",
      status: { $in: ["PAID", "SHIPPED"] },
      "payment.paidAt": { $type: "date" }
    }
  },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$payment.paidAt",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      revenue: { $sum: "$total" },
      count: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

`$dateTrunc` được hỗ trợ từ MongoDB 5.0. Dùng timezone nghiệp vụ để không chia sai ngày đối với các payment gần 00:00 giờ Việt Nam.

Production doanh thu kế toán cần mô hình hóa **payment events/refunds/settlements**; trạng thái đơn là một proxy đơn giản trong lab, không phải sổ cái.

---

## 18. Truy vấn 10: `$lookup` customer hiện tại

Order có snapshot customer name; admin muốn xem email hiện tại:

```javascript
lab.orders.aggregate([
  {
    $match: {
      tenantId: "A",
      _id: "A-O1001"
    }
  },
  {
    $lookup: {
      from: "customers",
      let: {
        cid: "$customer.customerId",
        tid: "$tenantId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$cid"] },
                { $eq: ["$tenantId", "$$tid"] }
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            displayName: 1,
            email: 1
          }
        }
      ],
      as: "currentCustomer"
    }
  },
  {
    $project: {
      orderNo: 1,
      customer: 1,
      currentCustomer: 1,
      total: 1
    }
  }
]).toArray();
```

Không join chỉ theo customer ID rồi bỏ `tenantId` nếu hệ thống dùng IDs có thể trùng tenant hoặc security policy yêu cầu isolation. Đọc `currentCustomer` chỉ ở endpoint đã được phép xem email.

`customer.displayName` snapshot và `currentCustomer.displayName` hiện tại **không bắt buộc giống nhau**.

---

## 19. Pagination: skip/limit và keyset

### 19.1. Offset paging

```javascript
lab.orders.find({ tenantId: "A" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(0)
  .limit(2)
  .toArray();
```

Trang đầu: A-O1005, A-O1004.

```javascript
lab.orders.find({ tenantId: "A" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(2)
  .limit(2)
  .toArray();
```

Trang thứ hai: A-O1003, A-O1002.

### 19.2. Vì sao không dùng offset sâu mãi?

`skip(100000)` có thể phải đi qua nhiều records. Insert/delete trong lúc paging có thể khiến một document xuất hiện hai lần hoặc bị bỏ qua.

### 19.3. Keyset paging

Sau trang đầu, last order là A-O1004 (`2026-10-24T08:00:00Z`). Truy vấn tiếp:

```javascript
var lastTime = ISODate("2026-10-24T08:00:00Z");
var lastId = "A-O1004";

lab.orders.find({
  tenantId: "A",
  $or: [
    { createdAt: { $lt: lastTime } },
    {
      createdAt: lastTime,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(2)
.toArray();
```

Kỳ vọng: A-O1003, A-O1002.

Với API, cursor nên được **ký/kiểm tra tenant/filter/sort** để client không thay đổi tùy tiện nhằm truy cập dữ liệu trái phép.

### 19.4. Index cho tenant + createdAt

Có thể cần:

```javascript
lab.orders.createIndex(
  { tenantId: 1, createdAt: -1, _id: -1 },
  { name: "ix_tenant_time_id" }
);
```

Không tự tạo trên production nếu chưa đo workload; mỗi index tăng write overhead.

---

## 20. Kiểm chứng validator với dữ liệu sai

Chạy những ví dụ sau **trong lab**, sau khi đã seed dữ liệu. Dùng bản sao và đổi `_id`/`orderNo` để tránh lỗi duplicate vô tình che lỗi validation.

### 20.1. Quantity sai BSON type

```javascript
var badQty = lab.orders.findOne({ _id: "A-O1001" });
badQty._id = "BAD-QTY";
badQty.orderNo = "BAD-QTY";
badQty.items[0].quantity = "2"; // string, không phải int32

try {
  lab.orders.insertOne(badQty);
  print("Unexpected: invalid document accepted");
} catch (e) {
  print("Expected validation error: " + e.message);
}
```

### 20.2. Total dùng double thay Decimal128

```javascript
var badTotal = lab.orders.findOne({ _id: "A-O1001" });
badTotal._id = "BAD-TOTAL";
badTotal.orderNo = "BAD-TOTAL";
badTotal.total = 189.30;

try {
  lab.orders.insertOne(badTotal);
  print("Unexpected: double accepted");
} catch (e) {
  print("Expected decimal type error: " + e.message);
}
```

### 20.3. Thiếu fields bắt buộc

```javascript
try {
  lab.orders.insertOne({
    _id: "BAD-MISSING",
    tenantId: "A",
    orderNo: "BAD-003"
  });
} catch (e) {
  print("Expected required-fields error: " + e.message);
}
```

### 20.4. Status ngoài enum

```javascript
var badStatus = lab.orders.findOne({ _id: "A-O1001" });
badStatus._id = "BAD-STATUS";
badStatus.orderNo = "BAD-STATUS";
badStatus.status = "UNKNOWN";

try {
  lab.orders.insertOne(badStatus);
} catch (e) {
  print("Expected enum error: " + e.message);
}
```

MongoDB thường báo `DocumentValidationFailure` (code 121), với details tùy version. Không ghi nguyên invalid documents chứa PII vào log công khai.

### 20.5. Xác nhận không có document BAD

```javascript
lab.orders.countDocuments({ _id: /^BAD-/ });
// 0 nếu mọi write invalid đều bị từ chối
```

---

## 21. Giới hạn của JSON Schema: total có thể sai phép cộng

Bản sao:

```javascript
var wrongMath = lab.orders.findOne({ _id: "A-O1001" });
wrongMath._id = "MATH-WRONG";
wrongMath.orderNo = "MATH-WRONG";
wrongMath.total = NumberDecimal("1.00");
```

Dù số tiền sai, validator ở bài vẫn có thể **chấp nhận** document này vì `total` vẫn là Decimal128 không âm.

**Không insert vào fixture chính** nếu muốn giữ expected revenues.

### 21.1. Kiểm tra ở domain service

Pseudo-code Java:

```java
BigDecimal sum = items.stream()
    .map(item ->
        item.unitPrice()
            .multiply(BigDecimal.valueOf(item.quantity()))
    )
    .reduce(BigDecimal.ZERO, BigDecimal::add);

if (sum.compareTo(order.total()) != 0) {
    throw new IllegalArgumentException("Order total mismatch");
}
```

Với tax/discount/shipping, formula và rounding phải được định nghĩa theo business/currency.

### 21.2. Kiểm tra dữ liệu đã lưu bằng aggregation

```javascript
lab.orders.aggregate([
  {
    $project: {
      total: 1,
      recomputed: {
        $reduce: {
          input: "$items",
          initialValue: NumberDecimal("0"),
          in: {
            $add: ["$$value", "$$this.lineTotal"]
          }
        }
      }
    }
  },
  {
    $match: {
      $expr: { $ne: ["$total", "$recomputed"] }
    }
  }
]).toArray();
```

Với 7 orders gốc, kỳ vọng **mảng rỗng**. Đây là data audit có thể tốn tài nguyên trên collection lớn, không phải endpoint OLTP nên gọi mỗi request.

---

## 22. Unique index và idempotency

### 22.1. Thử duplicate orderNo

```javascript
var dup = lab.orders.findOne({ _id: "A-O1001" });
dup._id = "A-O-DUP";
// orderNo vẫn "AO-001" trong tenant A.

try {
  lab.orders.insertOne(dup);
  print("Unexpected: duplicate accepted");
} catch (e) {
  print("Expected duplicate error: " + e.code);
}
```

Kỳ vọng `E11000 duplicate key` do index `uq_tenant_orderNo`.

### 22.2. Precheck exists không đủ

Hai requests có thể cùng thấy `exists=false` rồi insert. Unique index mới là ràng buộc cuối tại database.

Idempotency cần thêm business key/request ID, đặc biệt khi client retry sau network timeout. Khi thấy duplicate, ứng dụng phải xác định đó là retry hợp lệ hay một request khác dùng trùng mã, tránh trả dữ liệu của user khác.

### 22.3. `$setOnInsert` và upsert

Một phương án idempotent create có thể dùng `upsert` với `$setOnInsert`, nhưng filter phải scoped theo tenant/business key và kết quả `upsertedId`/`matchedCount` phải được kiểm tra. Không dùng upsert khiến retry ghi đè đơn đã đặt.

---

## 23. Cập nhật trạng thái với filter và version

**Lệnh này làm thay đổi baseline**. Chỉ chạy sau các truy vấn đọc hoặc reset/reseed khi muốn so expected revenues cũ.

```javascript
var result = lab.orders.updateOne(
  {
    _id: "A-O1001",
    tenantId: "A",
    status: "PLACED",
    version: NumberInt(1)
  },
  {
    $set: {
      status: "PAID",
      payment: {
        method: "CARD",
        paidAt: ISODate("2026-10-27T10:00:00Z")
      },
      updatedAt: ISODate("2026-10-27T10:00:00Z")
    },
    $inc: { version: NumberInt(1) }
  }
);

printjson({
  matched: result.matchedCount,
  modified: result.modifiedCount
});
```

Lần đầu kỳ vọng `matched=1, modified=1`. Lần hai với `version=1` kỳ vọng `matched=0`.

- `_id` xác định order.
- `tenantId` bảo vệ phạm vi tenant.
- `status` chặn transition từ trạng thái khác.
- `version` giảm nguy cơ lost update.

Validator có thể biết `"PAID"` hợp lệ theo enum nhưng **không biết** `CANCELLED → PAID` có bị cấm; state machine/domain service cần đảm bảo workflow.

---

## 24. Cập nhật tồn kho atomically

Giữ 2 HEAD của tenant A nếu còn đủ:

```javascript
var stockResult = lab.products.updateOne(
  {
    tenantId: "A",
    sku: "HEAD",
    active: true,
    stock: { $gte: NumberInt(2) }
  },
  {
    $inc: { stock: NumberInt(-2) }
  }
);

printjson({
  matched: stockResult.matchedCount,
  modified: stockResult.modifiedCount
});
```

Khi stock dưới 2, update không match. Predicate và `$inc` là atomic trên **một product document**.

**Không làm read-check-write hai bước không atomic**: hai clients có thể cùng đọc stock=1 rồi cả hai quyết định bán.

### 24.1. Giới hạn single-document atomicity

Một order có nhiều SKUs đòi trừ nhiều product documents và insert order. Đây là nhiều writes, không tự atomic với nhau. Cần transaction trên MongoDB topology hỗ trợ, hoặc reservation/saga/compensation strategy khi business cho phép eventual consistency.

---

## 25. Transaction: trừ stock và tạo order

Đoạn `mongosh` sau **chỉ dùng trên replica set/sharded deployment hỗ trợ transactions**, không dùng standalone MongoDB nếu cần multi-document atomicity.

Chạy trong lab, với bộ dữ liệu gốc:

```javascript
var session = db.getMongo().startSession();
var txDb = session.getDatabase("order_design_lab");

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  var stock = txDb.products.updateOne(
    {
      tenantId: "A",
      sku: "HEAD",
      active: true,
      stock: { $gte: NumberInt(1) }
    },
    { $inc: { stock: NumberInt(-1) } }
  );

  if (stock.modifiedCount !== 1) {
    throw new Error("Insufficient stock");
  }

  var now = new Date();

  txDb.orders.insertOne({
    _id: "A-O1006",
    schemaVersion: NumberInt(1),
    version: NumberInt(1),
    tenantId: "A",
    orderNo: "AO-006",
    customer: {
      customerId: "A-C01",
      displayName: "Ngọc"
    },
    items: [
      {
        sku: "HEAD",
        name: "Tai nghe",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("89.90"),
        lineTotal: NumberDecimal("89.90")
      }
    ],
    total: NumberDecimal("89.90"),
    currency: "USD",
    status: "PLACED",
    createdAt: now,
    updatedAt: now,
    shipping: { city: "Hà Nội" }
  });

  session.commitTransaction();
  print("Transaction committed");
} catch (e) {
  try {
    session.abortTransaction();
  } catch (abortError) {
    print("Transaction outcome needs investigation");
  }
  print("Transaction failed: " + e.message);
} finally {
  session.endSession();
}
```

### 25.1. Tại sao `modifiedCount` quan trọng?

Nếu update stock không match vì hết hàng, nó không nhất thiết ném exception. Nếu code tiếp tục insert order, sẽ tạo đơn không có reservation. Vì vậy phải kiểm tra `modifiedCount`.

### 25.2. Transaction không giải quyết external payment

MongoDB transaction không bao trùm payment gateway. Với thanh toán từ hệ thống ngoài, cần idempotent external calls, outbox/saga và xử lý retries/ambiguous commit outcomes theo business policy.

### 25.3. Không chạy lại mù quáng

Thực hiện lại cùng `AO-006` có thể ném duplicate key. Phải thiết kế retry/idempotency và không được trừ stock lần thứ hai.

---

## 26. Validation modes và `collMod`

### 26.1. `validationAction`

- `error`: document sai bị từ chối.
- `warn`: ghi warning nhưng vẫn cho phép write theo semantics MongoDB.
- Một số bản MongoDB có thêm `errorAndLog` theo phiên bản/edition; đối chiếu tài liệu trước khi dùng.

### 26.2. `validationLevel`

- `strict`: validate mọi inserts và updates thuộc phạm vi kiểm tra.
- `moderate`: hỗ trợ migration legacy theo semantics đặc biệt với existing invalid documents.

Không bật `warn`/`moderate` trên production chỉ để giấu schema errors.

### 26.3. Thử trong lab

```javascript
lab.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "warn"
});
```

Khôi phục chế độ chặn:

```javascript
lab.runCommand({
  collMod: "orders",
  validationLevel: "strict",
  validationAction: "error"
});
```

Hai lệnh giữ validator hiện tại, chỉ đổi policy. Để thay đổi schema khi thêm fields hoặc statuses, `collMod` cần validator mới tương thích và migration plan.

### 26.4. `bypassDocumentValidation` không phải giải pháp lâu dài

Driver có thể hỗ trợ bypass với quyền phù hợp; việc này làm mất một tầng bảo vệ. Chỉ dùng trong migrations được kiểm soát, ghi lại exceptions và audit.

---

## 27. `explain("executionStats")`: index được dùng hay chưa?

### 27.1. Lookup theo mã

```javascript
lab.orders.find({
  tenantId: "A",
  orderNo: "AO-001"
}).explain("executionStats");
```

### 27.2. List PAID

```javascript
lab.orders.find({
  tenantId: "A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.explain("executionStats");
```

### 27.3. Lịch sử khách

```javascript
lab.orders.find({
  tenantId: "A",
  "customer.customerId": "A-C01"
})
.sort({ createdAt: -1, _id: -1 })
.explain("executionStats");
```

### 27.4. SKU

```javascript
lab.orders.find({
  tenantId: "A",
  "items.sku": "CABLE"
}).explain("executionStats");
```

### 27.5. Đọc output

| Thông số/stage | Ý nghĩa |
| --- | --- |
| `winningPlan` | Execution plan optimizer chọn |
| `IXSCAN` | Có quét index |
| `COLLSCAN` | Quét collection |
| `FETCH` | Cần lấy document sau index |
| `SORT` | Có sort stage riêng |
| `nReturned` | Số records trả |
| `totalKeysExamined` | Số index keys examined |
| `totalDocsExamined` | Số documents examined |
| `executionTimeMillis` | Thời gian một lần Explain |

**Không assert IXSCAN tuyệt đối trên 7 documents.** Planner có thể chọn COLLSCAN vì dataset quá nhỏ. Index tồn tại (`getIndexes`) và index được dùng (`explain`) là hai bằng chứng khác nhau.

### 27.6. Query targeting và overhead

Ví dụ một query quét 200.000 documents để trả 20 orders có tỷ lệ 10.000 docs examined/result: đáng điều tra query/index/projection.

Cũng cần đo write overhead vì mỗi index bổ sung phải được cập nhật khi insert/update, đặc biệt multikey trên `items`.

---

## 28. Kiểm tra BSON types và dữ liệu legacy

### 28.1. `$type` audit

```javascript
lab.orders.aggregate([
  {
    $project: {
      orderNo: 1,
      totalType: { $type: "$total" },
      createdType: { $type: "$createdAt" },
      itemsType: { $type: "$items" },
      versionType: { $type: "$version" }
    }
  },
  { $sort: { _id: 1 } }
]).toArray();
```

Kỳ vọng các types `decimal`, `date`, `array`, `int` trên fixture.

### 28.2. Tìm missing required fields

```javascript
lab.orders.find({
  $or: [
    { tenantId: { $exists: false } },
    { orderNo: { $exists: false } },
    { items: { $exists: false } },
    { total: { $exists: false } }
  ]
}).toArray();
```

Kỳ vọng rỗng với fixture valid. Dữ liệu được ghi **trước khi validator có hiệu lực** hoặc có quyền bypass có thể chứa legacy fields/types khác.

### 28.3. Null khác missing

```javascript
lab.orders.find({ note: null });
```

MongoDB equality với null thường khớp cả documents missing field `note` lẫn explicit null. Dùng:

```javascript
lab.orders.find({ note: { $exists: false } });

lab.orders.find({ note: { $type: "null" } });
```

khi business cần phân biệt.

---

## 29. Multi-tenancy: đừng nhầm filter với authorization

Validator đòi `tenantId` là string **không đồng nghĩa** user được phép đọc tenant đó. Service phải xác thực principal và lấy tenantId từ quyền đã kiểm chứng.

### 29.1. OR sai có thể lộ dữ liệu

Sai:

```javascript
{
  $or: [
    { tenantId: "A", status: "PAID" },
    { total: { $gte: NumberDecimal("100") } }
  ]
}
```

Nhánh thứ hai có thể match dữ liệu B.

Đúng:

```javascript
{
  tenantId: "A",
  $or: [
    { status: "PAID" },
    { total: { $gte: NumberDecimal("100") } }
  ]
}
```

### 29.2. Cần tenant scope cả trên writes và lookups

Đưa tenant vào filters của `updateOne`, `deleteOne`, queries, aggregations và `$lookup`. Không dựa vào quy ước ID có prefix tenant làm cơ chế phân quyền duy nhất.

### 29.3. API data minimization

Không trả toàn bộ shipping/payment/email qua list endpoint. Projection và DTO giảm dữ liệu; authorization xác định ai được xem trường nào.

---

## 30. Java/Spring Data MongoDB mapping

Một entity có thể khai báo:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders")
public class OrderEntity {
    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private String orderNo;

    @Field(targetType = FieldType.DECIMAL128)
    private BigDecimal total;

    private String status;
    private Instant createdAt;
    private Instant updatedAt;

    private Integer version;
    private Integer schemaVersion;

    private CustomerSnapshot customer;
    private List<LineItem> items;

    // Các trường shipping/payment và constructors,
    // getters/setters được bổ sung theo model thực.
}
```

**Quan trọng:** embedded `LineItem.unitPrice` và `LineItem.lineTotal` cũng cần mapping Decimal128. Vì validator `additionalProperties:false`, phải kiểm tra `_class` ở root và nested types từ Spring Data; custom conversions/type mapper phải tương thích schema.

### 30.1. Repository methods

```java
public interface OrderRepository
        extends MongoRepository<OrderEntity, String> {

    Optional<OrderEntity> findByTenantIdAndOrderNo(
        String tenantId,
        String orderNo
    );

    Page<OrderEntity> findByTenantIdAndStatus(
        String tenantId,
        String status,
        Pageable pageable
    );

    List<OrderEntity>
    findByTenantIdAndCustomer_CustomerIdOrderByCreatedAtDesc(
        String tenantId,
        String customerId
    );
}
```

Các embedded classes/properties và imports phải được tạo đầy đủ theo project.

### 30.2. `@Version` và optimistic locking

Spring Data có `@Version`, nhưng đừng trộn tự tăng version bằng raw `$inc` với repository `save()` nếu chưa hiểu semantics. Dùng acknowledged write concern và integration test stale update.

### 30.3. `Page` có thể thêm count query

Nếu UI chỉ cần “Tải thêm”, `Slice` hoặc keyset có thể tránh count tổng. Với các collections lớn, tránh `findAll()` không giới hạn.

### 30.4. Đọc raw BSON trong integration test

`MongoTemplate.findById` trả mapped object nhưng có thể che kiểu BSON thực. Để kiểm tra Decimal128:

```java
var raw = mongoTemplate.getDb()
    .getCollection("orders")
    .find(new Document("_id", "A-O1001"))
    .first();

assertThat(raw.get("total"))
    .isInstanceOf(org.bson.types.Decimal128.class);
```

Đây là ví dụ trong test có `mongoTemplate`, AssertJ và `org.bson.Document` imports phù hợp. Mock repository không xác minh `$jsonSchema`, unique indexes hay raw BSON.

---

## 31. Business flow đặt hàng hợp lý

```text
POST /orders
     |
     v
Xác thực user -> xác định tenantId
     |
     v
Kiểm tra request, item limit, quantity
     |
     v
Đọc catalog theo tenantId + SKU
     |
     v
Kiểm tra active, stock, currency
     |
     v
Tính price snapshots và line totals bằng BigDecimal
     |
     v
Tạo idempotency key/orderNo
     |
     v
Transaction / reservation workflow
  - atomic stock decrement
  - insert order
     |
     v
Trả order ID và trạng thái
```

Không tin client tự gửi `unitPrice=0.01` hoặc `total=0.01` mà bỏ qua pricing policy. **Server tính total** dựa trên catalog và negotiated pricing hợp lệ.

### 31.1. Payment gateway ngoài database

MongoDB transaction không làm external payment gateway atomic. Dùng idempotent payment operations, event/outbox và reconciliation theo thiết kế của dự án.

### 31.2. Dữ liệu đã bán cần snapshot

Update catalog giá/name không được làm thay lịch sử order. Đây là lý do line items embed cả `sku`, `name`, `unitPrice`.

---

## 32. Kế hoạch nâng schema v2

Business muốn thêm `discount`, `refunds`, status `RETURNED` và nhiều currencies.

Quy trình **expand–migrate–contract**:

1. Đo dữ liệu v1, kiểu BSON và số documents.
2. Thiết kế v2 với field/type/default rõ.
3. Triển khai code đọc được v1/v2.
4. Mở validator có kế hoạch tương thích; không buộc tất cả documents cũ sai ngay.
5. Triển khai writers cho v2.
6. Backfill theo batches có checkpoint và idempotency.
7. Kiểm tra money calculations và query outputs.
8. Tạo/rebuild index theo workload mới.
9. Siết validator lại khi migration hoàn tất.
10. Theo dõi validation failures, latency và rollback.

`schemaVersion` không tự động migrate dữ liệu. Trên production không dùng `collMod` như một thử nghiệm vô chủ.

---

## 33. Ma trận kiểm thử

| Contract | Điều kiện | Kỳ vọng |
| --- | --- | --- |
| Fixtures | Baseline | 7 orders |
| Tenants | A/B | 5 / 2 |
| OrderNo | A/AO-001 | A-O1001 |
| PAID list | A | A-O1005, A-O1002 |
| Customer history | A-C01 | A-O1005,1003,1001 |
| Date range | A, 21/10–25/10 UTC | A-O1002,1003,1004 |
| SKU CABLE | A | A-O1001,1002,1004,1005 |
| `$elemMatch` qty≥3 | A, CABLE | A-O1005 |
| Completed orders | A PAID+SHIPPED | 3 |
| Revenue | A | 161.40 |
| Revenue | B | 99.90 |
| Units CABLE | A completed | 5 |
| Quantity string | BAD-QTY | Validation failure |
| Total double | BAD-TOTAL | Validation failure |
| Missing fields | BAD-MISSING | Validation failure |
| Status UNKNOWN | BAD-STATUS | Validation failure |
| Duplicate orderNo | A/AO-001 | Duplicate key |
| Versioned update | A-O1001 version 1 | First update 1, retry 0 |
| Insufficient stock | stock dưới quantity | matchedCount 0 |
| Cross-tenant read | User A/record B | Forbidden/no result |
| Index definitions | Catalog | Key order/options đúng |
| Explain | Query list/detail | Plan/scan metrics được ghi nhận |

### 33.1. Vì sao phải test MongoDB thật?

Mock repository không thực hiện BSON conversion, `$jsonSchema`, unique index, atomic update hay transaction. Dùng integration tests trên MongoDB test instance hoặc Testcontainers/MongoDB replica set khi kiểm tra transactions.

### 33.2. Không assert IXSCAN cứng trên 7 orders

Với tiny dataset, optimizer có thể chọn COLLSCAN hợp lý. Bài test phải phân biệt correctness, index existence và performance benchmark trên corpus đủ lớn.

---

## 34. Các lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Insert bị code 121 | Sai BSON type/required/enum | Đọc validator, raw BSON, sửa data |
| `additionalProperties:false` từ chối `_id` | Quên `_id` trong properties | Cho phép `_id` |
| Java insert bị từ chối do `_class` | Type mapper thêm metadata | Mapping/validator tương thích |
| BigDecimal thành double | Converter sai hoặc đi qua JavaScript Number | Decimal128 mapping, raw `$type` |
| `orderNo` trùng | Không có/đã va unique index | Unique index và idempotency |
| Total sai nhưng validation pass | Schema chưa kiểm tra cross-field math | Domain validation và audit |
| Có stock âm/race | Read-check-write tách bước | Atomic predicate + `$inc` |
| Order tạo nhưng stock chưa trừ | Nhiều writes không atomic | Transaction/reservation workflow |
| Status nhảy không hợp lệ | Enum không biết state machine | Guarded update + service |
| Tenant A đọc được B | Thiếu authorization/tenant scope | Principal-derived tenant + test |
| Query có index vẫn chậm | Index không khớp filter/sort, dữ liệu lớn | Explain, selectivity, projection |
| `findAll()` quá nhiều docs | Không có pagination | Limit/keyset/stream |
| `$lookup` leak email | Không giới hạn quyền/tenant | Tenant-scoped join, auth |
| Revenue sai ngày | Group theo UTC thay timezone nghiệp vụ | `$dateTrunc` timezone |
| Schema mới phá update legacy | Siết `required` quá sớm | Expand–migrate–contract |
| Mock test pass nhưng write fail | Mock không chạy database | Integration tests |

---

## 35. Bài tập thực hành

### Bài 1 — Embed vs reference

Vì sao line items nằm trong order còn product catalog nằm collection riêng? Nêu hai lợi ích và hai giới hạn.

### Bài 2 — Giá lịch sử

Catalog HEAD A tăng giá 89.90 → 95.00. `A-O1001.items[0].unitPrice` có đổi không?

**Đáp án:** Không; đó là snapshot.

### Bài 3 — Decimal128

Vì sao dùng `NumberDecimal("19.99")` thay JavaScript number `19.99` khi lưu tiền?

### Bài 4 — BSON Date

Một đơn có timestamp UTC. Làm sao lọc theo “ngày hôm qua tại Việt Nam” mà không sai ranh giới ngày?

### Bài 5 — Required

Liệt kê năm required fields của orders và giải thích lý do.

### Bài 6 — `additionalProperties`

Điều gì xảy ra nếu validator `additionalProperties:false` nhưng không khai báo `_id`?

### Bài 7 — `_class`

Vì sao Spring Data có thể bị validator chặn dù object Java hợp lệ?

### Bài 8 — Item count

Cách từ chối `items:[]` và `items` có 21 phần tử?

**Đáp án:** `minItems:1` và `maxItems:20`.

### Bài 9 — Quantity

Quantity là string `"2"` có hợp lệ với `bsonType:"int"` không?

**Đáp án:** Không.

### Bài 10 — Status enum

Tạo document status `"REFUNDED"` và giải thích validation failure.

### Bài 11 — Math invariant

Vì sao validator lab có thể chấp nhận `total:NumberDecimal("1")` dù items cộng thành 189.30?

### Bài 12 — Unique business key

Viết index không cho trùng `(tenantId,orderNo)`.

### Bài 13 — Race condition

Vì sao `existsByTenantIdAndOrderNo` không bảo vệ uniqueness khi có concurrent requests?

### Bài 14 — Order lookup

Viết query lấy tenant A, orderNo `"AO-002"`.

### Bài 15 — Status list

Tìm PAID A, sort `createdAt DESC, _id DESC`, limit 20; expected order IDs?

**Đáp án:** A-O1005, A-O1002.

### Bài 16 — Customer history

Tìm các đơn A của khách A-C01 mới nhất trước.

### Bài 17 — Time range

Dùng `$gte`/`$lt` lấy orders A trong khoảng 21/10–25/10 UTC.

### Bài 18 — Array SKU

Tìm orders A chứa SKU CABLE.

### Bài 19 — `$elemMatch`

Tìm cùng phần tử có CABLE và quantity >=3. Giải thích khác hai điều kiện dot notation độc lập.

### Bài 20 — Count

PAID tenant A có bao nhiêu đơn?

**Đáp án:** 2.

### Bài 21 — Revenue

Tính revenue của A với status PAID/SHIPPED.

**Đáp án:** 161.40 USD.

### Bài 22 — Global reporting

Tính revenue A/B và nêu vì sao không cho tenant user chạy global aggregation không được phép.

### Bài 23 — Top SKU

Sku nào có units cao nhất trong đơn A đã thanh toán?

**Đáp án:** CABLE, 5 units.

### Bài 24 — `$lookup`

Viết `$lookup` lấy customer hiện tại, match cả customer ID và tenantId.

### Bài 25 — Projection

Vì sao list endpoint không cần tải `items`, shipping và payment?

### Bài 26 — Keyset pagination

Viết query lấy trang tiếp theo sau A-O1004 với sort descending `(createdAt,_id)`.

### Bài 27 — Stock

Nếu stock còn 1 nhưng khách cần 2, atomic update có predicate `$gte:2` trả gì?

**Đáp án:** `matchedCount=0`.

### Bài 28 — Version

Vì sao status update nên filter cả status cũ và version cũ?

### Bài 29 — Transaction

Nếu stock update thành công nhưng order insert bị duplicate, transaction cần làm gì?

### Bài 30 — `collMod`

Viết lệnh đổi action sang `warn` trong lab rồi khôi phục `error`.

### Bài 31 — Explain

Xem `totalKeysExamined`, `totalDocsExamined`, `nReturned` và winning plan cho lookup theo orderNo.

### Bài 32 — Index prefix

Vì sao index `(tenantId,status,createdAt)` có thể không tối ưu date-only query?

### Bài 33 — Tiny dataset

Vì sao MongoDB có thể chọn COLLSCAN dù index đã tồn tại trên 7 orders?

### Bài 34 — Tenant OR

Đưa tenant filter ra ngoài hai nhánh `$or` để ngăn lộ dữ liệu.

### Bài 35 — Spring Data

Chọn annotation để Java `BigDecimal total` được lưu BSON Decimal128 và kiểm tra bằng raw `Document`.

### Bài 36 — Schema drift

Sản phẩm cũ lưu price dạng double, schema mới yêu cầu decimal. Lên kế hoạch chuyển dữ liệu an toàn.

### Bài 37 — Partial entity

Vì sao không nên đọc projection thiếu fields rồi gọi repository `save()`?

### Bài 38 — Idempotency

Thiết kế cơ chế tránh trừ stock hai lần khi client retry do không nhận được phản hồi commit.

### Bài 39 — Dashboard large-scale

Báo cáo SKU chạy rất chậm trên 100 triệu đơn. Nêu chiến lược indexes, benchmark và pre-aggregation.

### Bài 40 — Đồ án cuối

Thiết kế bốn API `POST /orders`, `GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/pay`. Báo cáo đầy đủ: document model, validators, unique/indexes, tenant authorization, state machine, transaction/idempotency, query matrix, integration tests, Explain và migration plan.

---

## 36. Checklist trước production

### Data model

- [ ] Embed/reference được chọn theo query patterns.
- [ ] Line-item price/name snapshots là contract có chủ đích.
- [ ] Array có giới hạn, BSON document dưới 16 MiB.
- [ ] Money dùng Decimal128/BigDecimal, currency/rounding rõ.
- [ ] Date dùng BSON Date, timezone boundaries chuẩn.
- [ ] Schema version và optimistic version có mục đích khác nhau.

### Validation

- [ ] `$jsonSchema` đã tồn tại trong collection options.
- [ ] Required, enum, nested objects, int/decimal/date types được kiểm tra.
- [ ] `_id`/`_class` phù hợp `additionalProperties`.
- [ ] Domain service tính lại total, không tin client.
- [ ] State transition/reference integrity kiểm tra ngoài validator.
- [ ] Có kế hoạch migration trước khi siết schema.

### Index/query

- [ ] Unique `(tenantId,orderNo)`, `(tenantId,sku)`, `(tenantId,email)`.
- [ ] Có index phù hợp list status/time, customer history.
- [ ] Multikey index chỉ tạo khi workload yêu cầu.
- [ ] Pagination/sort có tie-breaker.
- [ ] Có projection cho list endpoints.
- [ ] Đọc Explain để xác minh query plans.
- [ ] Đo write overhead của indexes.

### Concurrency/security

- [ ] Tenant scope lấy từ authenticated principal.
- [ ] Queries, updates, deletes và lookups có tenant guard.
- [ ] Unique violations/idempotency được xử lý.
- [ ] Stock update có atomic predicate.
- [ ] Multi-document operation có transaction hoặc compensation.
- [ ] Payment ngoài MongoDB transaction có workflow riêng.
- [ ] Không expose raw PII/payment details trong API/logs.

### Operations

- [ ] Có integration tests trên MongoDB thật.
- [ ] Có backups, migrations, rollback và monitoring.
- [ ] Không chạy `drop`/`collMod` lab trên production.
- [ ] Đo p95/p99, CPU/IOPS, pool waits, slow queries.
- [ ] Có audit/reconciliation cho payment/refund/cancellation.
- [ ] Không dựa vào dataset 7 đơn để kết luận performance production.

---

## 37. Tổng kết

Một thiết kế MongoDB document tốt phải phục vụ **các truy vấn nghiệp vụ thật** chứ không chỉ trông giống JSON đẹp:

1. **Embed** thông tin thường đọc cùng order và giá lịch sử; **reference** tới product/customer hiện tại.
2. Dùng **BSON types rõ ràng**: Decimal128 cho tiền, Date cho thời gian, int cho quantity/stock.
3. Dùng **`$jsonSchema` validator** kiểm tra shape, required fields, enum, nested arrays và type.
4. Không nhầm validator với mọi invariant: **tính toán total, state transitions, authorization và referential integrity** thuộc domain service.
5. Dùng **unique index** để bảo vệ business key khi concurrent requests xảy ra.
6. Thiết kế **compound indexes theo filter và sort**, không tạo index tùy tiện.
7. Viết **OLTP queries có tenant scope**, projection và pagination ổn định.
8. Dùng aggregation cho doanh thu/SKU với định nghĩa nghiệp vụ minh bạch.
9. Dùng **atomic conditional update hoặc transaction** để giữ stock/order consistency.
10. Đọc **raw BSON, index catalog và Explain**, viết integration tests và chuẩn bị schema migration.

**Kết quả mong muốn:** một bộ collections, validators, sample data, truy vấn và test contracts có thể tái lập, kiểm chứng và phát triển thành hệ thống thực tế an toàn.

### Tài liệu MongoDB chính thức

- [MongoDB Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/) — design theo access patterns.
- [Embedded Data vs References](https://www.mongodb.com/docs/manual/data-modeling/concepts/embedding-vs-references/) — embed/reference trade-offs.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — validator và database contract.
- [Specify JSON Schema](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — `$jsonSchema` examples.
- [JSON Schema Operator](https://www.mongodb.com/docs/manual/reference/operator/query/jsonSchema/) — BSON types/keywords.
- [Modify Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/update-schema-validation/) — `collMod` và migration.
- [BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — Decimal128/Date/int.
- [MongoDB Indexes](https://www.mongodb.com/docs/manual/indexes/) — indexes và operational trade-offs.
- [Compound Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-compound/) — key order.
- [Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/) — arrays.
- [Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness.
- [Query Operators](https://www.mongodb.com/docs/manual/reference/operator/query/) — filter, `$elemMatch`, `$exists`, `$type`.
- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — group/unwind/lookup/dateTrunc.
- [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/) — execution statistics.
- [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — single-document atomicity.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document behavior.
- [Spring Data MongoDB Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html) — Java/BSON mapping.
- [Spring Data Query Methods](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html) — repositories and paging.
