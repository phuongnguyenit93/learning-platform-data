# Document đa hình và biểu diễn các biến thể nghiệp vụ trong MongoDB

## 1. Vì sao một collection có thể chứa nhiều dạng document?

Trong cơ sở dữ liệu quan hệ, một bảng thường được định nghĩa bằng tập cột chung cho tất cả bản ghi. MongoDB lưu dữ liệu thành **document BSON** và không bắt buộc mọi document trong cùng collection phải có cấu trúc giống hệt nhau. Đặc tính này cho phép biểu diễn những thực thể **cùng thuộc một khái niệm nghiệp vụ** nhưng mang các thuộc tính khác nhau theo từng biến thể.

Ví dụ một hệ thống bán hàng cung cấp ba loại sản phẩm:

- **Hàng vật lý (PHYSICAL):** cần trọng lượng, mã SKU kho và phương thức vận chuyển.
- **Hàng số (DIGITAL):** cần mã tài nguyên số, giấy phép sử dụng và giới hạn lượt tải.
- **Gói thuê bao (SUBSCRIPTION):** cần mã gói, chu kỳ thanh toán và số ngày dùng thử.

Cả ba đều có **mã sản phẩm**, **tên**, **trạng thái**, **giá** và **đơn vị tiền tệ**. Tuy nhiên, bắt từng document mang mọi trường của cả ba loại sẽ tạo nhiều giá trị null và làm mờ quy tắc nghiệp vụ.

**Document đa hình (polymorphic document)** là cách tổ chức một hoặc nhiều kiểu document khác nhau dưới một giao diện nghiệp vụ chung. Trong MongoDB, một dạng triển khai phổ biến được gọi là **Polymorphic Pattern**: các document có cấu trúc khác nhau được lưu trong **cùng một collection**, thường kèm **discriminator field** để xác định biến thể.

### 1.1. Hai ví dụ cùng collection

Document hàng vật lý:

~~~javascript
{
  _id: ObjectId("64b000000000000000000001"),
  tenantId: "SHOP-A",
  productCode: "KEYBOARD-01",
  kind: "PHYSICAL",
  name: "Mechanical Keyboard",
  status: "ACTIVE",
  price: {
    amount: NumberDecimal("1299000.00"),
    currency: "VND"
  },
  details: {
    inventorySku: "SKU-KB-001",
    weightGrams: NumberInt(850),
    shippingClass: "STANDARD"
  },
  schemaVersion: NumberInt(1)
}
~~~

Document hàng số:

~~~javascript
{
  _id: ObjectId("64b000000000000000000002"),
  tenantId: "SHOP-A",
  productCode: "EBOOK-MONGO-01",
  kind: "DIGITAL",
  name: "MongoDB E-book",
  status: "ACTIVE",
  price: {
    amount: NumberDecimal("99000.00"),
    currency: "VND"
  },
  details: {
    assetId: "ASSET-MONGO-PDF",
    licenseType: "PERSONAL",
    maxDownloads: NumberInt(3)
  },
  schemaVersion: NumberInt(1)
}
~~~

Hai document chia sẻ **các trường chung** nhưng nội dung **details** khác nhau theo **kind**. MongoDB chấp nhận điều này, song ứng dụng phải quản lý quy tắc để document vẫn hợp lệ.

### 1.2. Khi nào nên nghĩ đến document đa hình?

Hãy đặt ba câu hỏi:

1. Các biến thể có thực sự thuộc **cùng một thực thể nghiệp vụ** hay chỉ trông giống nhau về tên?
2. Ứng dụng có thường **tìm kiếm, phân trang, hiển thị, cấp quyền hoặc báo cáo chung** cho mọi biến thể không?
3. Mỗi biến thể có một số trường/quy tắc riêng nhưng vẫn chia sẻ **vòng đời, danh tính và quan hệ** ở mức hợp lý không?

Nếu cả ba câu trả lời đều là có, một collection đa hình thường đáng cân nhắc. Nếu các loại thực thể có vòng đời, phân quyền, tải truy vấn và index hoàn toàn khác nhau, các collection riêng có thể tốt hơn.

## 2. Tư duy mô hình hóa: chung ở đâu, khác ở đâu?

### 2.1. Tách phần invariant khỏi phần variant

Một thiết kế rõ ràng bắt đầu bằng cách xác định:

- **Identity:** sản phẩm có mã duy nhất trong phạm vi nào? Ví dụ cặp **tenantId + productCode**.
- **Invariants chung:** tất cả sản phẩm phải có tên, trạng thái, giá và mã tiền tệ; hoặc những bất biến khác theo domain.
- **Discriminator:** trường **kind** có danh sách giá trị được kiểm soát.
- **Variant payload:** các thuộc tính chỉ có ý nghĩa với từng **kind**, đặt trong **details**.
- **Schema version:** phiên bản biểu diễn để chuyển đổi an toàn khi nghiệp vụ tiến hóa.

~~~text
Collection: products
|
+-- Common identity and lifecycle
|   +-- _id
|   +-- tenantId
|   +-- productCode
|   +-- name
|   +-- status
|   +-- price
|   +-- schemaVersion
|
+-- kind: discriminator
|   |
|   +-- PHYSICAL
|   |     +-- details.inventorySku
|   |     +-- details.weightGrams
|   |     +-- details.shippingClass
|   |
|   +-- DIGITAL
|   |     +-- details.assetId
|   |     +-- details.licenseType
|   |     +-- details.maxDownloads
|   |
|   +-- SUBSCRIPTION
|         +-- details.planCode
|         +-- details.billingInterval
|         +-- details.trialDays
~~~

Với cấu trúc này, client có thể lấy danh sách chung từ **products**, sau đó dùng **kind** để quyết định cách hiển thị/truy cập dữ liệu biến thể.

### 2.2. Discriminator là một phần của hợp đồng dữ liệu

Ví dụ:

~~~javascript
kind: "PHYSICAL"
~~~

Không nên suy luận loại từ việc tồn tại một field ngẫu nhiên:

~~~javascript
if (doc.details.weightGrams) {
  // Cách suy luận mong manh: giá trị 0 và trường thiếu dễ gây hiểu sai.
}
~~~

Một discriminator rõ ràng giúp:

- **Query:** lọc đúng biến thể bằng **{ kind: "PHYSICAL" }**.
- **Mapping:** Java/Node.js biết tạo loại đối tượng miền nào.
- **Validation:** áp dụng những yêu cầu bắt buộc riêng của biến thể.
- **Indexing:** tạo index cho truy vấn chuyên biệt từng loại.
- **Migration:** biết document thuộc phiên bản/biến thể nào khi nâng cấp cấu trúc.

Giá trị discriminator phải có ý nghĩa nghiệp vụ ổn định. Nếu đổi **DIGITAL** thành **DOWNLOAD** chỉ vì thay đổi tên giao diện, toàn bộ query, validator, dữ liệu cũ và consumer khác có thể bị ảnh hưởng.

### 2.3. Phân biệt discriminator với schemaVersion

| Field | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| **kind** | Đây là **loại nghiệp vụ** nào? | PHYSICAL, DIGITAL, SUBSCRIPTION |
| **schemaVersion** | Document này đang dùng **phiên bản cấu trúc** nào? | 1, 2 |
| **status** | Thực thể hiện ở **trạng thái vòng đời** nào? | DRAFT, ACTIVE, ARCHIVED |

Một sản phẩm DIGITAL ở **schemaVersion = 1** và sản phẩm DIGITAL ở **schemaVersion = 2** vẫn là cùng một loại nghiệp vụ; khác biệt là cấu trúc lưu trữ. Còn chuyển từ PHYSICAL sang DIGITAL thường là thay đổi bản chất nghiệp vụ, không phải chỉ nâng phiên bản schema.

## 3. Ví dụ hoàn chỉnh: ba biến thể sản phẩm

Những ví dụ sau sử dụng cú pháp **mongosh**. Các helper **ObjectId**, **NumberInt**, **NumberDecimal** và **ISODate** tạo kiểu BSON cụ thể; đây không phải JSON thuần.

~~~javascript
use polymorphic_shop

db.products.insertMany([
  {
    tenantId: "SHOP-A",
    productCode: "KEYBOARD-01",
    kind: "PHYSICAL",
    name: "Mechanical Keyboard",
    status: "ACTIVE",
    price: {
      amount: NumberDecimal("1299000.00"),
      currency: "VND"
    },
    details: {
      inventorySku: "SKU-KB-001",
      weightGrams: NumberInt(850),
      shippingClass: "STANDARD"
    },
    schemaVersion: NumberInt(1),
    createdAt: ISODate("2026-01-10T08:00:00Z")
  },
  {
    tenantId: "SHOP-A",
    productCode: "EBOOK-MONGO-01",
    kind: "DIGITAL",
    name: "MongoDB E-book",
    status: "ACTIVE",
    price: {
      amount: NumberDecimal("99000.00"),
      currency: "VND"
    },
    details: {
      assetId: "ASSET-MONGO-PDF",
      licenseType: "PERSONAL",
      maxDownloads: NumberInt(3)
    },
    schemaVersion: NumberInt(1),
    createdAt: ISODate("2026-01-12T08:00:00Z")
  },
  {
    tenantId: "SHOP-A",
    productCode: "PRO-MONTHLY",
    kind: "SUBSCRIPTION",
    name: "Pro Monthly",
    status: "ACTIVE",
    price: {
      amount: NumberDecimal("199000.00"),
      currency: "VND"
    },
    details: {
      planCode: "PRO",
      billingInterval: "MONTH",
      trialDays: NumberInt(14)
    },
    schemaVersion: NumberInt(1),
    createdAt: ISODate("2026-01-15T08:00:00Z")
  }
]);
~~~

### 3.1. Vì sao không đưa mọi thuộc tính lên cùng cấp?

Một cách lưu khác có thể là:

~~~javascript
{
  productCode: "EBOOK-MONGO-01",
  kind: "DIGITAL",
  name: "MongoDB E-book",
  weightGrams: null,
  shippingClass: null,
  assetId: "ASSET-MONGO-PDF",
  licenseType: "PERSONAL",
  planCode: null,
  billingInterval: null
}
~~~

Thiết kế dạng phẳng vẫn **hợp lệ trong MongoDB**. Nhưng khi số biến thể tăng, document có thể chứa rất nhiều field không có nghĩa, còn validator và DTO khó phân biệt **field vắng mặt**, **null có chủ đích** và **giá trị không hợp lệ**.

Đặt phần riêng trong **details** giúp người đọc thấy rõ ranh giới. Tuy nhiên không nên áp dụng cứng nhắc: nếu thuộc tính chuyên biệt thường xuyên được query chéo và nằm ở nhiều biến thể với cùng semantics, giữ nó ở vùng chung có thể hợp lý hơn.

### 3.2. Có phải mọi document cùng collection đều nên có cùng schema?

**Không.** MongoDB cho phép cấu trúc linh hoạt; điều cần ổn định là **hợp đồng nghiệp vụ**. Nếu các biến thể được mô hình hóa chủ đích, việc khác nhau về field là tính năng. Nếu mỗi lần deploy lại vô tình tạo field sai tên, kiểu khác nhau hoặc biến thể không rõ ràng, đó là **schema drift** cần kiểm soát.

Ví dụ sai:

~~~javascript
{ kind: "PHYSICAL", details: { weightGram: "850" } }
{ kind: "PHYSICAL", details: { weightGrams: NumberInt(850) } }
~~~

Hai document có thể cùng lưu thành công khi không có validator, nhưng code lọc theo **details.weightGrams** sẽ bỏ sót document thứ nhất. **Schema flexibility** không tự bảo đảm tính nhất quán.

## 4. Các mô hình đa hình thường gặp

### 4.1. Single collection + discriminator + details

Đây là phương án đang dùng trong ví dụ:

~~~text
products
├── { kind: PHYSICAL, details: {...} }
├── { kind: DIGITAL, details: {...} }
└── { kind: SUBSCRIPTION, details: {...} }
~~~

**Ưu điểm:** tìm kiếm chung, phân trang chung, danh tính và vòng đời chung, dễ chia sẻ các field/index cơ bản. **Nhược điểm:** collection có nhiều shapes, mỗi loại cần validation và index tương ứng.

### 4.2. Single collection + biến thể ở top level

~~~javascript
{
  productCode: "KEYBOARD-01",
  kind: "PHYSICAL",
  name: "Mechanical Keyboard",
  inventorySku: "SKU-KB-001",
  weightGrams: NumberInt(850)
}
~~~

Phù hợp khi biến thể nhỏ, số thuộc tính riêng ít và query truy cập trực tiếp rất thường xuyên. Trade-off là field riêng không còn được gom trong một namespace dễ nhận biết. Không có luật MongoDB bắt buộc phải dùng **details**; điều quan trọng là tổ chức nhất quán và có thể kiểm soát.

### 4.3. Separate collections theo từng biến thể

~~~text
physical_products
digital_products
subscription_products
~~~

Mỗi collection có validator/index riêng. Phương án này hữu ích khi mỗi loại có workload, retention, quyền truy cập, số lượng record hoặc mô hình vòng đời độc lập.

Đổi lại, truy vấn **“mọi sản phẩm ACTIVE của SHOP-A”** phải đi qua nhiều collection, thường cần logic hợp nhất ở ứng dụng hoặc aggregation **$unionWith** nếu phù hợp. Việc đảm bảo một **productCode** duy nhất xuyên các collection cũng khó hơn so với unique index trong một collection.

### 4.4. Common collection + các collection chi tiết

~~~text
products
  { _id, tenantId, productCode, kind, name, status, price }

physical_product_details
  { productId, weightGrams, inventorySku, shippingClass }

digital_product_details
  { productId, assetId, licenseType, maxDownloads }
~~~

Giải pháp này tách dữ liệu chung/riêng và cho phép các loại có chính sách lưu trữ khác nhau. Nhưng cần **join bằng $lookup hoặc nhiều lượt đọc**, quản lý ràng buộc tham chiếu bằng ứng dụng và có thể cần transaction cho thay đổi liên collection.

Không nên tách detail ra collection khác chỉ vì muốn mô phỏng bảng quan hệ. Nếu detail được đọc gần như mọi lần cùng sản phẩm và kích thước nhỏ, **embedding** trong document thường giúp thao tác đơn giản và có tính nguyên tử ở cấp một document.

### 4.5. Mixed pattern: biến thể có trường lớn/ngoại lệ

Nếu chỉ một số sản phẩm DIGITAL có hàng nghìn bản ghi lượt tải, không nên nhúng một array tăng vô hạn vào **details**:

~~~javascript
{
  kind: "DIGITAL",
  details: {
    assetId: "ASSET-123",
    // Không nên lưu toàn bộ lịch sử download ngày càng lớn ở đây.
    downloads: [ /* không giới hạn */ ]
  }
}
~~~

Các lượt tải nên nằm ở collection sự kiện riêng, ví dụ **download_events**, được liên kết bằng **productId**. MongoDB có giới hạn kích thước document BSON **16 MiB**; array tăng không kiểm soát gây tốn RAM, I/O và cập nhật.

## 5. Truy vấn document đa hình

### 5.1. Tìm kiếm chung cho mọi biến thể

~~~javascript
db.products.find(
  {
    tenantId: "SHOP-A",
    status: "ACTIVE"
  },
  {
    _id: 1,
    productCode: 1,
    kind: 1,
    name: 1,
    price: 1
  }
).sort({ productCode: 1 });
~~~

Đây là lợi ích cốt lõi của **cùng một collection**: truy vấn danh sách sản phẩm chung không cần hợp nhất nhiều nguồn dữ liệu.

### 5.2. Truy vấn riêng một biến thể

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "PHYSICAL",
  "details.weightGrams": { $gte: 500 }
});
~~~

Với sản phẩm số:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "DIGITAL",
  "details.licenseType": "PERSONAL"
});
~~~

Với thuê bao:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "SUBSCRIPTION",
  "details.billingInterval": "MONTH"
});
~~~

Lọc bằng **kind** tạo hợp đồng rõ: truy vấn một field riêng chỉ có nghĩa đối với đúng biến thể. MongoDB vẫn có thể tìm theo field con mà không nêu **kind**, nhưng việc nêu loại thường giúp code dễ hiểu và tạo điều kiện cho partial index tương ứng.

### 5.3. Lọc field chỉ tồn tại ở một biến thể

~~~javascript
db.products.find({
  "details.assetId": { $exists: true }
});
~~~

**$exists: true** tìm document có field đó, kể cả trường hợp giá trị bằng **null**. Nếu muốn tìm giá trị khác null cần thêm điều kiện phù hợp. Không nên dùng **$exists** để suy ra chính xác loại sản phẩm nếu **kind** đã là discriminator chính thức.

### 5.4. Tổng hợp thống kê chung theo kind

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "SHOP-A",
      status: "ACTIVE"
    }
  },
  {
    $group: {
      _id: "$kind",
      numberOfProducts: { $sum: 1 }
    }
  },
  {
    $sort: { _id: 1 }
  }
]);
~~~

Kết quả minh họa:

~~~javascript
[
  { _id: "DIGITAL", numberOfProducts: 1 },
  { _id: "PHYSICAL", numberOfProducts: 1 },
  { _id: "SUBSCRIPTION", numberOfProducts: 1 }
]
~~~

Không nên tự động cộng **price.amount** của tất cả biến thể rồi gọi đó là doanh thu: giá sản phẩm vật lý có thể tính theo món, hàng số theo license, thuê bao theo chu kỳ. **Cùng kiểu dữ liệu kỹ thuật không có nghĩa cùng đơn vị đo nghiệp vụ**.

### 5.5. Trả ra một trường trình bày chung bằng $switch

~~~javascript
db.products.aggregate([
  { $match: { tenantId: "SHOP-A", status: "ACTIVE" } },
  {
    $project: {
      _id: 0,
      productCode: 1,
      name: 1,
      kind: 1,
      fulfillmentLabel: {
        $switch: {
          branches: [
            {
              case: { $eq: ["$kind", "PHYSICAL"] },
              then: "Requires shipping"
            },
            {
              case: { $eq: ["$kind", "DIGITAL"] },
              then: "Digital delivery"
            },
            {
              case: { $eq: ["$kind", "SUBSCRIPTION"] },
              then: "Recurring access"
            }
          ],
          default: "Unknown product kind"
        }
      }
    }
  }
]);
~~~

Aggregation có thể giúp chuẩn hóa dữ liệu để hiển thị, nhưng các quy tắc nghiệp vụ phức tạp và quyền truy cập vẫn nên được kiểm soát ở lớp ứng dụng/phù hợp domain.

## 6. Thiết lập validator theo từng biến thể

MongoDB cho phép gắn **schema validation** cho collection thông qua **$jsonSchema**. Có thể kết hợp các ràng buộc chung với **oneOf** để đảm bảo document thuộc chính xác một biến thể được khai báo.

Ví dụ tạo collection từ đầu (chỉ chạy nếu **products** chưa tồn tại):

~~~javascript
use polymorphic_shop

db.createCollection("products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "productCode",
        "kind",
        "name",
        "status",
        "price",
        "details",
        "schemaVersion"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        productCode: { bsonType: "string" },
        kind: {
          enum: ["PHYSICAL", "DIGITAL", "SUBSCRIPTION"]
        },
        name: { bsonType: "string" },
        status: {
          enum: ["DRAFT", "ACTIVE", "ARCHIVED"]
        },
        schemaVersion: {
          bsonType: "int",
          minimum: 1
        },
        price: {
          bsonType: "object",
          required: ["amount", "currency"],
          properties: {
            amount: { bsonType: "decimal" },
            currency: { bsonType: "string" }
          }
        },
        details: { bsonType: "object" }
      },
      oneOf: [
        {
          properties: {
            kind: { enum: ["PHYSICAL"] },
            details: {
              bsonType: "object",
              required: [
                "inventorySku",
                "weightGrams",
                "shippingClass"
              ],
              properties: {
                inventorySku: { bsonType: "string" },
                weightGrams: { bsonType: "int", minimum: 1 },
                shippingClass: {
                  enum: ["STANDARD", "FRAGILE"]
                }
              }
            }
          }
        },
        {
          properties: {
            kind: { enum: ["DIGITAL"] },
            details: {
              bsonType: "object",
              required: [
                "assetId",
                "licenseType",
                "maxDownloads"
              ],
              properties: {
                assetId: { bsonType: "string" },
                licenseType: {
                  enum: ["PERSONAL", "TEAM"]
                },
                maxDownloads: { bsonType: "int", minimum: 1 }
              }
            }
          }
        },
        {
          properties: {
            kind: { enum: ["SUBSCRIPTION"] },
            details: {
              bsonType: "object",
              required: [
                "planCode",
                "billingInterval",
                "trialDays"
              ],
              properties: {
                planCode: { bsonType: "string" },
                billingInterval: { enum: ["MONTH", "YEAR"] },
                trialDays: { bsonType: "int", minimum: 0 }
              }
            }
          }
        }
      ]
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

**Đọc quy tắc của ví dụ:**

1. Mọi document cần có các trường chung, giá phải lưu ở dạng BSON **Decimal128**.
2. Giá trị **kind** phải nằm trong tập đã khai báo.
3. **oneOf** yêu cầu document khớp đúng một nhánh. Vì mỗi nhánh giới hạn **kind** khác nhau, điều kiện nhánh không chồng lấn.
4. Với **PHYSICAL**, **details.weightGrams** phải là BSON Int32 lớn hơn hoặc bằng 1; các loại khác có bộ trường bắt buộc riêng.
5. **validationAction: "error"** yêu cầu từ chối thao tác ghi vi phạm validator. **validationLevel: "strict"** áp dụng kiểm tra cho insert và update thông thường.

**Lưu ý:** schema mẫu không khai báo **additionalProperties: false**, nên nó vẫn cho phép những field chưa bị cấm. Muốn chặn trường không mong muốn cần ràng buộc cụ thể ở cấp document/details, nhưng việc khóa quá chặt có thể cản trở tiến hóa schema. Chọn độ nghiêm ngặt dựa vào rủi ro nghiệp vụ.

### 6.1. Kết hợp validator với quy tắc ở ứng dụng

JSON Schema kiểm tra được **cấu trúc, kiểu, tập enum, một số miền giá trị**. Nó không thay thế toàn bộ logic nghiệp vụ. Ví dụ:

- Một SKU kho có thực sự tồn tại ở inventory service không?
- Một digital asset có đang được cấp phép phân phối không?
- Một mã gói thuê bao có hợp lệ với tenant và thị trường hiện tại không?
- Giá VND có phù hợp chính sách làm tròn/thuế của hệ thống không?

Các quy tắc trên đòi hỏi dữ liệu liên quan và logic ở domain/service. Dùng MongoDB validator như một hàng rào bảo vệ **hình dạng dữ liệu**, kết hợp kiểm soát nghiệp vụ ở ứng dụng.

### 6.2. Không thay đổi validator production mà bỏ qua document cũ

Khi cập nhật validator bằng **collMod**, không nên cho rằng các document cũ tự động được sửa. Document không hợp lệ có thể tiếp tục tồn tại từ trước và gây lỗi khi được cập nhật. Trước khi siết validator:

1. Kiểm tra dữ liệu đang lưu và phân loại cấu trúc hiện tại.
2. Xác định đường migration cho các bản ghi không hợp lệ.
3. Triển khai code đọc được dữ liệu cũ lẫn mới.
4. Sửa dữ liệu theo từng lô, theo dõi lỗi.
5. Sau khi đạt điều kiện, mới siết rule cho write path.

Một schema validator **đúng với code mới** chưa chắc tương thích tức thời với cả dữ liệu trong lịch sử.

## 7. Index cho truy vấn chung và truy vấn theo biến thể

Một collection đa hình có thể phục vụ nhiều loại truy vấn. Thiết kế index dựa trên **query pattern thực tế**, không tạo index riêng cho mọi field chỉ vì chúng tồn tại.

### 7.1. Unique index cho định danh nghiệp vụ chung

Nếu trong mỗi tenant, **productCode** phải duy nhất giữa tất cả biến thể:

~~~javascript
db.products.createIndex(
  { tenantId: 1, productCode: 1 },
  { unique: true, name: "uq_tenant_product_code" }
);
~~~

Điều này ngăn SHOP-A tạo sản phẩm PHYSICAL và DIGITAL trùng cùng **productCode**. Unique index chung hữu ích khi các biến thể thật sự chia sẻ **một không gian danh tính**.

Nếu hệ thống dùng **sharded collection**, unique index còn phải tuân theo những giới hạn liên quan đến shard key. Không giả định index bất kỳ sẽ tạo được hoặc bảo đảm uniqueness toàn cluster nếu không xét shard key.

### 7.2. Index cho danh sách chung

~~~javascript
db.products.createIndex(
  { tenantId: 1, status: 1, productCode: 1 },
  { name: "ix_tenant_status_code" }
);
~~~

Index này có thể giúp truy vấn lọc **tenantId**, **status** và sắp theo **productCode** ở ví dụ trước. Lợi ích cụ thể phải được kiểm tra bằng **explain**, vì query planner phụ thuộc thống kê, dữ liệu và projection.

### 7.3. Compound index cho một biến thể

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    kind: 1,
    "details.weightGrams": 1
  },
  { name: "ix_physical_weight" }
);
~~~

Phù hợp khi thường query hàng vật lý theo trọng lượng. Tuy nhiên index sẽ có entry tương ứng cho nhiều document thuộc biến thể khác, ngay cả khi field trọng lượng không tồn tại. Một lựa chọn khác là **partial index**.

### 7.4. Partial index cho một biến thể

~~~javascript
db.products.createIndex(
  {
    tenantId: 1,
    "details.weightGrams": 1
  },
  {
    name: "ix_physical_weight_partial",
    partialFilterExpression: { kind: "PHYSICAL" }
  }
);
~~~

Index chỉ chứa những document thỏa **kind = PHYSICAL**. Ứng dụng nên query rõ **kind**:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "PHYSICAL",
  "details.weightGrams": { $gte: 500 }
});
~~~

MongoDB chỉ sử dụng partial index khi query có điều kiện phù hợp để việc sử dụng index không làm thiếu kết quả. Query không giới hạn loại có thể không được hưởng lợi. Kiểm tra:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "PHYSICAL",
  "details.weightGrams": { $gte: 500 }
}).explain("executionStats");
~~~

### 7.5. Đừng tạo tất cả index mẫu cùng lúc ở production

Các index mẫu ở trên minh họa những phương án **khác nhau**. Mỗi index có chi phí:

- Dung lượng đĩa và cache;
- Công việc cập nhật index trong mỗi write;
- Chi phí xây dựng index khi collection lớn;
- Thời gian giám sát và bảo trì lâu dài.

Đo query thực tế, xem **explain** và lựa chọn tập index vừa đủ. Không nên tạo cả compound index đầy đủ và partial index gần như trùng công dụng nếu chưa có bằng chứng.

## 8. Mapping sang Java: biểu diễn polymorphism trong code

Trong Java, đa hình thường được biểu diễn bằng interface, abstract class, sealed interface hoặc một tập DTO cụ thể. Điểm quan trọng là **mã hóa discriminator một cách chủ động**, không phó mặc việc suy ra kiểu cho tên field.

### 8.1. Một mô hình domain bằng sealed interface và record

Ví dụ Java 21:

~~~java
public sealed interface ProductDetails
        permits PhysicalDetails, DigitalDetails, SubscriptionDetails {
}

public record PhysicalDetails(
        String inventorySku,
        int weightGrams,
        String shippingClass
) implements ProductDetails {
}

public record DigitalDetails(
        String assetId,
        String licenseType,
        int maxDownloads
) implements ProductDetails {
}

public record SubscriptionDetails(
        String planCode,
        String billingInterval,
        int trialDays
) implements ProductDetails {
}
~~~

Ba kiểu **Details** là các biến thể miền rõ ràng. Lớp khác chịu trách nhiệm chuyển đổi document từ MongoDB sang domain type phù hợp.

### 8.2. Đọc theo discriminator bằng Java Sync Driver

Đoạn mã dưới đây minh họa phần mapping; giả sử code đã tìm được **org.bson.Document** từ collection:

~~~java
import org.bson.Document;

public final class ProductDetailsMapper {

    public static ProductDetails fromMongo(Document product) {
        String kind = product.getString("kind");
        Document details = product.get("details", Document.class);

        if (kind == null || details == null) {
            throw new IllegalArgumentException(
                    "Product kind and details are required"
            );
        }

        return switch (kind) {
            case "PHYSICAL" -> new PhysicalDetails(
                    details.getString("inventorySku"),
                    details.getInteger("weightGrams"),
                    details.getString("shippingClass")
            );
            case "DIGITAL" -> new DigitalDetails(
                    details.getString("assetId"),
                    details.getString("licenseType"),
                    details.getInteger("maxDownloads")
            );
            case "SUBSCRIPTION" -> new SubscriptionDetails(
                    details.getString("planCode"),
                    details.getString("billingInterval"),
                    details.getInteger("trialDays")
            );
            default -> throw new IllegalArgumentException(
                    "Unsupported product kind: " + kind
            );
        };
    }
}
~~~

Một Java application dùng cùng collection có thể đọc:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;

// database được khởi tạo sẵn qua MongoClient.
MongoCollection<Document> products =
        database.getCollection("products");

Document stored = products.find(and(
        eq("tenantId", "SHOP-A"),
        eq("productCode", "EBOOK-MONGO-01")
)).first();

if (stored != null) {
    ProductDetails details = ProductDetailsMapper.fromMongo(stored);
    System.out.println(details);
}
~~~

Phần mapping trên minh họa **phân nhánh đúng theo kind**, chưa phải một mapper production hoàn chỉnh: code thực tế còn phải kiểm tra **schemaVersion**, kiểu dữ liệu chính xác, null, giá trị enum, quyền của tenant và phản hồi lỗi. Java **getInteger** sẽ không tự mang semantics như **Decimal128** hay **Int64**; cần giữ type Java/BSON đúng với từng field.

### 8.3. Dùng Spring Data MongoDB

Trong Spring Data, có thể chọn:

1. Một **document persistence model** chung chứa **kind** và **details**, sau đó mapping thủ công sang các domain variant.
2. Một **class hierarchy** với type metadata của Spring Data MongoDB (chẳng hạn **_class** hoặc alias) để converter chọn subtype.
3. Một **custom converter** hoặc cơ chế mapping chuyên biệt nếu không muốn phụ thuộc vào Java class name/type hint trong tài liệu lưu trữ.

Ví dụ persistence model chung:

~~~java
import org.bson.Document;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;

@org.springframework.data.mongodb.core.mapping.Document(
        collection = "products"
)
public class ProductDocument {
    @Id
    private ObjectId id;

    private String tenantId;
    private String productCode;
    private String kind;
    private String name;
    private Document details;
    private int schemaVersion;

    // Constructor, getters, setters...
}
~~~

Đây là **bản phác họa** persistence model; ứng dụng thực tế cần bổ sung **price**, **status** và **createdAt** theo hợp đồng dữ liệu, kiểm soát trường và converter tương ứng.

**Lưu ý về _class:** metadata type của Spring Data giúp deserialize subtype trong hệ Spring Data, nhưng không nên xem tên lớp Java là **discriminator nghiệp vụ** ổn định khi dữ liệu được dùng bởi Node.js, Python, batch jobs và các service khác. Trường **kind** nên là một hợp đồng độc lập nếu hệ thống chia sẻ dữ liệu qua nhiều ngôn ngữ.

### 8.4. Không dùng mapper “đoán kiểu”

Tránh:

~~~java
// Không nên quyết định loại chỉ từ sự xuất hiện của field.
if (details.containsKey("weightGrams")) {
    // assume PHYSICAL
} else if (details.containsKey("assetId")) {
    // assume DIGITAL
} else {
    // assume SUBSCRIPTION
}
~~~

Khi schema thêm field mới hoặc document bị lỗi, suy luận này có thể âm thầm tạo sai subtype. **kind** phải được đối chiếu với payload và validator. Với kind chưa hỗ trợ, hãy xử lý theo chính sách rõ ràng (từ chối, giữ raw payload để đọc tương thích hoặc gửi vào hàng chờ xử lý), không mặc định là biến thể bất kỳ.

## 9. Cập nhật document đa hình và bảo toàn bất biến

### 9.1. Cập nhật field chung

~~~javascript
db.products.updateOne(
  {
    tenantId: "SHOP-A",
    productCode: "EBOOK-MONGO-01",
    status: "ACTIVE"
  },
  {
    $set: {
      name: "MongoDB E-book, Second Edition"
    }
  }
);
~~~

MongoDB bảo đảm **atomicity ở cấp một document** đối với thao tác update thích hợp. Khi cập nhật các field chung và field biến thể trong cùng document, không cần transaction nhiều document chỉ để đảm bảo thay đổi đó mang tính nguyên tử.

### 9.2. Cập nhật field riêng của một variant

~~~javascript
db.products.updateOne(
  {
    tenantId: "SHOP-A",
    productCode: "EBOOK-MONGO-01",
    kind: "DIGITAL"
  },
  {
    $set: {
      "details.maxDownloads": NumberInt(5)
    }
  }
);
~~~

Điều kiện **kind: "DIGITAL"** ngăn việc vô tình cập nhật **maxDownloads** lên một product PHYSICAL cùng **productCode** (hoặc document dữ liệu không hợp lệ).

### 9.3. Có nên đổi kind tại chỗ?

Ví dụ:

~~~javascript
// Cảnh báo: chỉ đổi discriminator là chưa đủ.
db.products.updateOne(
  { productCode: "KEYBOARD-01" },
  { $set: { kind: "DIGITAL" } }
);
~~~

Thao tác này làm document tự mâu thuẫn: kind DIGITAL nhưng **details** vẫn chứa thông tin cân nặng/kho. Validator **oneOf** có thể từ chối vì thiếu field DIGITAL bắt buộc.

Nếu nghiệp vụ thực sự cho phép chuyển loại, cần cập nhật **kind** và toàn bộ payload mới **cùng một thao tác nguyên tử**, đồng thời xử lý hệ quả ở inventory, fulfillment, quyền sử dụng và những quan hệ ngoài document. Trong nhiều miền nghiệp vụ, **đổi bản chất sản phẩm** nên được mô hình hóa như tạo sản phẩm/version mới thay vì cập nhật một field đơn giản.

### 9.4. Kiểm soát cập nhật đồng thời

Nếu hai request sửa cùng document, atomicity không tự ngăn **lost update** ở cấp nghiệp vụ. Có thể sử dụng optimistic locking thông qua **version** chuyên trách:

~~~javascript
db.products.updateOne(
  {
    tenantId: "SHOP-A",
    productCode: "EBOOK-MONGO-01",
    revision: NumberInt(3)
  },
  {
    $set: { "details.maxDownloads": NumberInt(10) },
    $inc: { revision: 1 }
  }
);
~~~

Đây là ví dụ điều kiện: document phải **đã có revision = 3**. Code cần kiểm tra **matchedCount** để biết update được áp dụng hay bị xung đột và phản hồi phù hợp. **revision** để kiểm soát cạnh tranh ghi không cùng ý nghĩa với **schemaVersion**, vốn mô tả phiên bản cấu trúc dữ liệu.

## 10. Tiến hóa schema khi số biến thể tăng

Một ưu điểm của document model là có thể thêm biến thể mà không cần thêm hàng loạt cột null cho document cũ. Nhưng điều này **không xóa bỏ nhu cầu migration và tương thích**.

### 10.1. Ví dụ thêm một biến thể mới

Giả sử hệ thống bổ sung **BUNDLE** (gói nhiều sản phẩm) có **details.items** chứa mã và số lượng. Các thay đổi cần xem xét:

- API/DTO và domain model có nhận **kind = BUNDLE** không?
- MongoDB **validator** đã có nhánh BUNDLE chưa?
- Các màn hình hiển thị, báo cáo, đặt hàng và cấp quyền có xử lý kind mới không?
- Index cho truy vấn BUNDLE có cần thiết không?
- Các consumer cũ sẽ làm gì khi gặp unknown kind?

Nếu chỉ thêm một document **BUNDLE** mà code cũ vẫn **default -> SUBSCRIPTION**, dữ liệu sẽ bị hiểu sai. Thêm biến thể là **thay đổi hợp đồng nghiệp vụ**, dù database không yêu cầu ALTER TABLE.

### 10.2. Ví dụ phiên bản schema của DIGITAL

Phiên bản 1:

~~~javascript
{
  kind: "DIGITAL",
  schemaVersion: NumberInt(1),
  details: {
    assetId: "ASSET-MONGO-PDF",
    licenseType: "PERSONAL",
    maxDownloads: NumberInt(3)
  }
}
~~~

Phiên bản 2 bổ sung **deliveryMethod**:

~~~javascript
{
  kind: "DIGITAL",
  schemaVersion: NumberInt(2),
  details: {
    assetId: "ASSET-MONGO-PDF",
    licenseType: "PERSONAL",
    maxDownloads: NumberInt(3),
    deliveryMethod: "SECURE_LINK"
  }
}
~~~

Một phương án triển khai an toàn:

1. **Đọc được cả v1 và v2:** code mới chấp nhận document cũ và đưa ra behavior được định nghĩa cho thiếu **deliveryMethod**.
2. **Ghi v2 cho document mới:** lúc này code cũ có thể chưa hiểu, nên phải xác định thứ tự nâng cấp consumer.
3. **Migration dữ liệu cũ theo lô:** chuyển từng document, có marker/version rõ.
4. **Theo dõi tiến độ:** đo số document còn ở từng schemaVersion.
5. **Siết validator và bỏ đường đọc v1** khi toàn bộ thành phần phụ thuộc đã sẵn sàng.

Ví dụ migration minh họa sau khi code và validator đã hỗ trợ schema mới:

~~~javascript
db.products.updateMany(
  {
    kind: "DIGITAL",
    schemaVersion: NumberInt(1),
    "details.deliveryMethod": { $exists: false }
  },
  {
    $set: {
      schemaVersion: NumberInt(2),
      "details.deliveryMethod": "SECURE_LINK"
    }
  }
);
~~~

Trong production, cần kiểm tra cả tenant, batch size, khả năng rollback, ghi đồng thời và audit trước khi chạy migration diện rộng. Nếu một phần document có semantics khác (ví dụ không thể cấp secure link), không được điền default thiếu căn cứ.

### 10.3. Schema version không nhất thiết tăng khi thêm mọi field

Nếu thêm một field **optional** tương thích ngược, một số hệ thống vẫn giữ version. Nếu thay đổi ý nghĩa hoặc cấu trúc mà consumer cũ không thể hiểu, việc tăng version giúp diễn đạt ranh giới tương thích. Cần có quy tắc nhất quán theo tổ chức, không dùng version như số đếm mọi lần deploy.

## 11. Chọn ranh giới collection dựa trên cách truy cập

MongoDB khuyến khích mô hình hóa quanh **workload và access patterns**. Document đa hình phù hợp khi nhiều biến thể thực sự được truy cập như một tập thực thể chung, nhưng sẽ gây chi phí nếu buộc những domain khác nhau chia sẻ collection.

| Yếu tố | Cùng một collection đa hình | Collection riêng từng loại |
|---|---|---|
| Danh sách/tìm kiếm chung | Thuận tiện, một truy vấn/index chung. | Cần hợp nhất kết quả từ nhiều nguồn. |
| Identity toàn bộ loại | Có thể dùng unique index chung. | Cần cơ chế bên ngoài để duy trì identity xuyên collection. |
| Schema validation | Có thể dùng oneOf/anyOf và phân nhánh theo kind. | Validator từng collection thường đơn giản hơn. |
| Index chuyên biệt | Có thể tạo compound/partial index nhưng cần cân đối. | Mỗi collection quản lý index độc lập. |
| Quy mô/tốc độ tăng | Nhiều workload chia sẻ tài nguyên cùng collection. | Dễ phân tách vận hành/retention/workload theo loại. |
| Permission/retention | Phải lọc và kiểm soát ở ứng dụng; một số chính sách khó tách. | Có thể phân chia quyền/vòng đời dễ hơn. |
| Thêm biến thể mới | Cần cập nhật discriminator, schema, consumer. | Có thể tạo collection mới nhưng cần xử lý truy vấn tổng hợp. |
| Giao dịch cập nhật chung + riêng | Một document có thể được update nguyên tử. | Nếu lưu ở nhiều collection, có thể cần transaction. |

### 11.1. Lưu cùng collection khi nào?

Ví dụ một hệ thống thương mại có trang **Catalog**, tìm kiếm chung, chính sách giá và trạng thái bán chung. Các biến thể PHYSICAL/DIGITAL/SUBSCRIPTION đều được xem là **Product**. Dùng một collection **products** thường tự nhiên nếu detail của từng loại có kích thước phù hợp.

### 11.2. Tách collection khi nào?

Ví dụ **audit logs**, **billing invoices** và **catalog products** có chung vài field như tenantId, createdAt, status nhưng không cùng khái niệm nghiệp vụ. Không nên nhét chúng vào một collection chỉ vì cùng có các field đó.

Ngay cả khi cùng khái niệm, một biến thể có thể có lưu lượng ghi khổng lồ, retention ngắn hoặc dữ liệu nhạy cảm cần kiểm soát riêng. Nếu mọi API của biến thể đó đều đi theo đường riêng, lợi ích của một collection chung có thể không còn lớn.

## 12. Đa hình và mô hình hóa sự kiện nghiệp vụ

Một tình huống khác ngoài sản phẩm là **business event**. Ví dụ một collection **order_events** có các biến thể:

~~~javascript
{
  eventId: "EV-1001",
  aggregateId: "ORDER-9001",
  eventType: "ORDER_CREATED",
  occurredAt: ISODate("2026-02-01T10:00:00Z"),
  payload: {
    customerId: "CUS-01",
    totalAmount: NumberDecimal("320000.00")
  },
  schemaVersion: NumberInt(1)
}
~~~

~~~javascript
{
  eventId: "EV-1002",
  aggregateId: "ORDER-9001",
  eventType: "PAYMENT_CAPTURED",
  occurredAt: ISODate("2026-02-01T10:05:00Z"),
  payload: {
    paymentId: "PAY-01",
    capturedAmount: NumberDecimal("320000.00")
  },
  schemaVersion: NumberInt(1)
}
~~~

Ở đây **eventType** chính là discriminator. Các sự kiện chia sẻ metadata chung nhưng mỗi **payload** khác nhau. Pattern này giúp lưu/đọc lịch sử nhiều loại sự kiện bằng một nguồn chung.

Tuy nhiên phải phân biệt:

- **Document thực thể đa hình:** biểu diễn trạng thái hiện tại của một product/order.
- **Document sự kiện đa hình:** biểu diễn một sự kiện đã xảy ra tại một thời điểm.

Event thường cần nguyên tắc bất biến, thứ tự, idempotency và retention riêng. Không nên coi event document và current-state document là cùng một loại chỉ vì cả hai có discriminator.

## 13. Đa hình trong hệ thống multi-tenant và sharded cluster

Nếu mọi document có **tenantId**, API nên giới hạn thao tác theo tenant hiện tại:

~~~javascript
db.products.find({
  tenantId: "SHOP-A",
  kind: "DIGITAL"
});
~~~

Không dựa vào việc người dùng tự gửi tenantId hợp lệ; server phải xác định tenant từ ngữ cảnh xác thực/ủy quyền và kiểm tra quyền truy cập.

Trong sharded cluster, việc chọn **shard key** nên dựa trên phân bố dữ liệu, truy vấn và tải thực tế. Dù mỗi document có **kind**, shard key không nhất thiết phải chứa **kind**. Nếu một loại sản phẩm chiếm phần lớn lượt ghi, phân vùng chỉ theo kind có thể tạo hotspot hoặc phân bố kém.

Những cân nhắc:

1. **Các trường chung** như tenantId/productCode thường dễ hỗ trợ truy vấn của nhiều loại hơn trường chỉ có ở một biến thể.
2. **Unique indexes** trên sharded collection phải tương thích quy tắc shard key; kiểm tra trước khi cam kết uniqueness toàn hệ thống.
3. **Partial index** và index field riêng cần được thiết kế phù hợp query planner; không giả định mọi sharding/index combination đều được hỗ trợ.
4. Một tenant hoặc biến thể quá lớn có thể làm lệch workload dù collection có nhiều shard.
5. Sharding không chữa được một document quá lớn hoặc một array không giới hạn.

Các quyết định shard key có chi phí thay đổi cao, vì vậy nên đánh giá từ dữ liệu và truy vấn đo được thay vì từ mô hình class Java.

## 14. Lỗi thiết kế phổ biến

### 14.1. Không có discriminator rõ ràng

Nếu chỉ kiểm tra sự tồn tại của field, code khó phân biệt document lỗi và biến thể hợp lệ. **Giải pháp:** dùng **kind** có enum rõ ràng và validator gắn shape với kind.

### 14.2. Dùng quá nhiều giá trị null

Document có hàng chục field chỉ có ý nghĩa cho những loại khác gây khó bảo trì. **Giải pháp:** đặt các field biến thể trong payload tương ứng hoặc cân nhắc tách collection nếu khác biệt quá lớn.

### 14.3. Coi thiếu field là giá trị mặc định hợp lệ

**trialDays** thiếu không đương nhiên bằng 0; **maxDownloads** thiếu không đương nhiên là không giới hạn. Default phải là **quy tắc nghiệp vụ rõ ràng**, có version nếu cần.

### 14.4. Có kind nhưng payload không khớp

Ví dụ **kind = DIGITAL** nhưng lại chỉ có **weightGrams**. **Giải pháp:** validator theo biến thể, mapping fail fast và kiểm tra input trước khi ghi.

### 14.5. Đổi kind mà không chuyển dữ liệu

Thay **kind** nhưng để lại toàn bộ cấu trúc cũ có thể phá invariants. **Giải pháp:** coi đổi variant là một operation nghiệp vụ, không phải một field update đơn lẻ.

### 14.6. Phân tích số liệu chung sai đơn vị

Giá một món hàng và giá thuê bao theo tháng đều là decimal, nhưng cộng chúng như cùng một đơn vị có thể vô nghĩa. **Giải pháp:** chuẩn hóa đo lường theo domain, phân nhóm theo kind/billingInterval trước khi báo cáo.

### 14.7. Lưu metadata class Java làm hợp đồng liên dịch vụ

Nếu discriminator chỉ là tên class trong **_class**, việc rename package hoặc đổi ngôn ngữ service có thể gây phụ thuộc không mong muốn. **Giải pháp:** dùng mã **kind** nghiệp vụ ổn định khi dữ liệu cần trao đổi xuyên công nghệ.

### 14.8. Tràn document vì nhúng lịch sử tăng mãi

Các trường **history**, **downloads** hoặc **events** không giới hạn có thể làm document lớn và cập nhật tốn kém. **Giải pháp:** tách dữ liệu tăng không giới hạn sang collection riêng, giữ trong document thông tin cần đọc cùng aggregate.

### 14.9. Không lập kế hoạch cho unknown variant

Consumer cũ có thể thấy kind mới sau một deploy. **Giải pháp:** phát hành theo thứ tự tương thích, kiểm soát unknown kind và migration, không ép thành một subtype mặc định.

### 14.10. Tạo index cho mọi field của mọi biến thể

Index dư tăng chi phí ghi và dung lượng. **Giải pháp:** dựa trên query pattern, dùng compound/partial index khi phù hợp và kiểm tra **explain**.

## 15. Bài thực hành: xây dựng catalog đa hình

Mục tiêu là thực hành kiến trúc, truy vấn và bảo vệ dữ liệu trên database dành riêng cho lab.

### Bước 1 — Tạo collection với các bản ghi đa hình

Trong mongosh, chọn database **polymorphic_shop** và chạy ví dụ **insertMany** ở Mục 3. Có thể tạo **validator** trước khi insert bằng lệnh ở Mục 6; nếu collection đã được tạo, dùng database/collection thử nghiệm khác hoặc quy trình **collMod** tương ứng.

### Bước 2 — Tìm mọi loại sản phẩm

~~~javascript
db.products.find(
  { tenantId: "SHOP-A", status: "ACTIVE" },
  { _id: 0, productCode: 1, kind: 1, name: 1 }
);
~~~

Kỳ vọng có cả ba loại product, khác nhau về **kind**.

### Bước 3 — Tìm riêng sản phẩm số

~~~javascript
db.products.find(
  { tenantId: "SHOP-A", kind: "DIGITAL" },
  { _id: 0, productCode: 1, "details.assetId": 1 }
);
~~~

Kết quả chỉ cần field đặc trưng của biến thể DIGITAL.

### Bước 4 — Quan sát kiểu BSON

~~~javascript
db.products.aggregate([
  {
    $project: {
      _id: 0,
      kind: 1,
      amountType: { $type: "$price.amount" },
      weightType: { $type: "$details.weightGrams" },
      maxDownloadsType: { $type: "$details.maxDownloads" }
    }
  }
]);
~~~

Một field không có ở biến thể tương ứng sẽ có kết quả type như **missing** khi dùng **$type** dạng biểu thức aggregation. Điều này giúp quan sát rằng collection có nhiều shape khác nhau nhưng các trường chung vẫn được lưu với kiểu thống nhất.

### Bước 5 — Thử một document sai biến thể

Nếu validator Mục 6 đã được tạo, thử:

~~~javascript
db.products.insertOne({
  tenantId: "SHOP-A",
  productCode: "INVALID-01",
  kind: "DIGITAL",
  name: "Invalid digital product",
  status: "ACTIVE",
  price: {
    amount: NumberDecimal("100.00"),
    currency: "VND"
  },
  details: {
    weightGrams: NumberInt(500)
  },
  schemaVersion: NumberInt(1)
});
~~~

Document dùng kind DIGITAL nhưng không có **assetId**, **licenseType**, **maxDownloads**. Với validator **strict/error** phù hợp, MongoDB từ chối thao tác vì vi phạm schema.

### Bước 6 — Quan sát index trước khi quyết định

Tạo một index phù hợp với một query trong lab:

~~~javascript
db.products.createIndex(
  { tenantId: 1, status: 1, productCode: 1 }
);

db.products.find({
  tenantId: "SHOP-A",
  status: "ACTIVE"
}).sort({ productCode: 1 }).explain("executionStats");
~~~

Trên tập dữ liệu rất nhỏ, MongoDB có thể lựa chọn **collection scan** hoặc kế hoạch khác vì chi phí thấp; không nên kết luận index tốt/xấu chỉ từ vài bản ghi. Hãy hiểu query shape, sau đó đánh giá trên workload có đại diện.

### Bước 7 — Thêm một biến thể mới trên giấy

Thiết kế biến thể **SERVICE** với các field **durationMinutes**, **serviceLocationType** và **bookingWindowDays**. Hãy tự xác định:

- Danh tính, field chung và field riêng;
- Giá trị discriminator;
- Validator branch cần thêm;
- Cách mapper Java nhận subtype;
- Truy vấn/index cần thiết;
- Tương thích với consumer chưa biết SERVICE;
- Liệu SERVICE thực sự thuộc cùng collection **products** không.

Đây là bài tập kiểm tra thiết kế domain, không cần vội tạo thêm document production.

## 16. Câu hỏi ôn tập

1. Vì sao document khác nhau về cấu trúc có thể cùng nằm trong một MongoDB collection mà vẫn hợp lệ?
2. **Polymorphic Pattern** khác với việc collection bị **schema drift** không kiểm soát ở đâu?
3. Vai trò của **kind**, **schemaVersion** và **status** khác nhau thế nào?
4. Vì sao nên gom thuộc tính biến thể vào **details** trong ví dụ catalog? Khi nào không cần làm vậy?
5. Validator **oneOf** giúp ràng buộc những điều gì khi collection có ba loại sản phẩm?
6. **Partial index** theo kind có lợi ích gì, và vì sao query thiếu điều kiện kind có thể không dùng được index đó?
7. Khi Java code nhận **kind** chưa hỗ trợ, điều gì có thể xảy ra nếu mapper dùng nhánh **default** trả một subtype bất kỳ?
8. Vì sao không nên tự động đổi kind từ PHYSICAL sang DIGITAL bằng một lệnh **$set** đơn giản?
9. Trong những trường hợp nào nên tách các biến thể thành collection riêng?
10. Vì sao **price.amount** cùng kiểu Decimal128 vẫn có thể không cộng được trực tiếp giữa PHYSICAL và SUBSCRIPTION?
11. Khi thêm biến thể BUNDLE, phải nâng cấp những thành phần nào ngoài cấu trúc lưu trữ?
12. MongoDB bảo đảm atomicity ở cấp document giúp gì khi cập nhật một product có nhiều field chung và field riêng?

## 17. Ghi nhớ khi chọn cách biểu diễn biến thể nghiệp vụ

Một mô hình document đa hình có hiệu quả khi:

1. **Cùng một identity/vòng đời:** các biến thể thực sự là các phiên bản của cùng khái niệm nghiệp vụ.
2. **Discriminator rõ ràng:** kind có giá trị ổn định, không suy ra từ tên field hoặc tên class.
3. **Các invariant chung nhất quán:** field chung có cấu trúc và nghĩa thống nhất.
4. **Variant payload có ranh giới:** field riêng được tổ chức dễ hiểu, ví dụ **details**.
5. **Validation và mapping theo kind:** dữ liệu sai shape bị nhận diện sớm.
6. **Query/index phản ánh workload:** phân biệt truy vấn chung với truy vấn đặc trưng của từng loại.
7. **Schema evolution có kế hoạch:** consumer cũ, migration và validator phối hợp theo version.
8. **Kích thước document có giới hạn:** tách lịch sử/array tăng vô hạn và dữ liệu không được đọc cùng aggregate.

~~~text
                    Business concept: Product
                                |
                Common identity / common fields
                                |
                    Discriminator: kind
                                |
             +------------------+------------------+
             |                  |                  |
          PHYSICAL            DIGITAL         SUBSCRIPTION
             |                  |                  |
          details             details            details
       shipping/stock      asset/license      plan/billing
             |                  |                  |
             +------------------+------------------+
                                |
                   Shared products collection
                                |
                   Validation + indexes + mapper
~~~

**Document đa hình không đơn giản là “MongoDB cho phép các field khác nhau”.** Giá trị của pattern nằm ở việc đưa các biến thể có liên quan vào một cấu trúc có chung danh tính và cách truy cập, nhưng vẫn giữ được đặc điểm riêng với một hợp đồng dữ liệu có thể kiểm soát.

### Tài liệu MongoDB để đọc tiếp

- [Polymorphic Data Pattern](https://www.mongodb.com/docs/manual/data-modeling/design-patterns/polymorphic-data/polymorphic-schema-pattern/) — các trường hợp dùng dữ liệu đa hình.
- [Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/) — mô hình document dựa trên workload.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — ràng buộc dữ liệu khi schema linh hoạt.
- [Specify JSON Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/specify-json-schema/) — sử dụng **$jsonSchema**.
- [Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/) — index chỉ cho tập document thỏa filter.
- [MongoDB Java Driver](https://www.mongodb.com/docs/drivers/java/sync/current/) — mapping/đọc/ghi document ở tầng Java.

Khi phát triển một module Java hoặc Spring Boot dùng MongoDB, hãy bắt đầu từ **nghiệp vụ và access patterns**, sau đó quyết định biến thể nào thuộc cùng aggregate và collection. Lớp Java, schema validation và index nên được thiết kế để phản ánh quyết định đó, thay vì làm theo cấu trúc các class có sẵn rồi ép MongoDB phải giống chúng.
