# Kiểm tra document lồng nhau, mảng và phần tử mảng trong MongoDB

## 1. Bài toán và mục tiêu

MongoDB lưu dữ liệu theo document BSON. Document có thể chứa object lồng nhau, mảng giá trị đơn giản, mảng object và nhiều tầng lồng nhau. Sự linh hoạt này giúp mô hình dữ liệu phù hợp nghiệp vụ, nhưng cũng tạo nguy cơ lưu dữ liệu thiếu trường, nhầm kiểu hoặc sai cấu trúc.

Ví dụ một đơn hàng có thể lưu chung thông tin khách hàng, địa chỉ giao hàng và các dòng hàng:

~~~javascript
{
  _id: "ord-001",
  customer: {
    customerId: "C001",
    contact: { email: "lan@example.test" }
  },
  shipping: {
    address: { city: "Hà Nội", street: "12 Phố Huế" }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(2),
      unitPrice: NumberDecimal("19.90"),
      labels: ["new", "gift"]
    }
  ]
}
~~~

Nếu không có ràng buộc, MongoDB có thể chấp nhận các biến thể như `customer: "Lan"`, `lines: "BOOK-01"` hoặc một dòng hàng thiếu `sku`. Khi ứng dụng đọc dữ liệu, những document này có thể gây lỗi hoặc làm sai phép tính.

**Schema validation** cho phép đặt quy tắc ở cấp collection. Khi ghi document, MongoDB kiểm tra cấu trúc và kiểu dữ liệu theo `validator`; tùy chế độ được cấu hình, nó từ chối thao tác ghi không hợp lệ hoặc ghi nhận cảnh báo.

Trong bài học thuộc chương **Schema validation** của **Database Engine Document MongoDB**, chúng ta sẽ:

- Định nghĩa cấu trúc document lồng nhau bằng `$jsonSchema`, `properties` và `required`.
- Kiểm tra mảng bằng `bsonType: "array"`, `items`, `minItems`, `maxItems` và `uniqueItems`.
- Ràng buộc **từng phần tử** của mảng object, kể cả các thuộc tính bên trong phần tử.
- Phân biệt trường bị thiếu, giá trị `null`, object rỗng và mảng rỗng.
- Thử các thao tác `insertOne`, `updateOne`, `$push` hợp lệ hoặc bị từ chối.
- Xem validator hiện tại, thay đổi validator với `collMod` và quan sát trong MongoDB Compass.
- Hiểu giới hạn của schema validation, đặc biệt là tính duy nhất theo một trường bên trong mảng.

Mọi thao tác ghi trong ví dụ sử dụng database thực hành riêng `schema_validation_lab`. Không chạy phần tạo/sửa validator lên collection sản xuất khi chưa đối chiếu dữ liệu cũ và quy trình triển khai.

## 2. Schema validation hoạt động tại đâu?

Một collection có thể được tạo kèm tùy chọn `validator`:

~~~javascript
db.createCollection("collectionName", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      properties: {
        // Định nghĩa trường cần kiểm tra
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Luồng xử lý cơ bản:

~~~text
Client (mongosh, Compass, Java Driver, Spring Data MongoDB)
                           |
                           v
                   Gửi lệnh ghi dữ liệu
                           |
                           v
                  MongoDB kiểm tra validator
                      /              \
                Hợp lệ              Không hợp lệ
                   |                     |
                   v                     v
             Cho phép ghi        error: từ chối ghi
                                 warn: ghi và cảnh báo
~~~

Validator được thực thi ở server, nên cùng một quy tắc áp dụng khi ghi từ nhiều client. Tuy nhiên, ứng dụng vẫn nên kiểm tra dữ liệu đầu vào để trả thông báo thân thiện và đảm bảo các quy tắc nghiệp vụ rộng hơn phạm vi của schema.

Các thành phần quan trọng:

| Thành phần | Công dụng |
|---|---|
| `validator` | Chứa điều kiện document phải thỏa khi ghi |
| `$jsonSchema` | Mô tả cấu trúc document bằng tập từ khóa JSON Schema được MongoDB hỗ trợ và mở rộng BSON |
| `bsonType` | Kiểm tra kiểu BSON: `object`, `array`, `string`, `int`, `long`, `decimal`, ... |
| `properties` | Định nghĩa quy tắc cho các trường con của object |
| `required` | Chỉ định tên trường bắt buộc xuất hiện trong object |
| `items` | Định nghĩa quy tắc cho phần tử của mảng |
| `validationLevel` | Xác định phạm vi document được kiểm tra khi cập nhật |
| `validationAction` | Xác định phản ứng khi gặp document vi phạm |

MongoDB hỗ trợ **một tập con** của JSON Schema cùng các mở rộng cho BSON. Không nên giả định mọi từ khóa có trong một thư viện JSON Schema nói chung đều được MongoDB hiểu theo cùng cách. Ví dụ `bsonType` là từ khóa quan trọng riêng cho dữ liệu BSON.

### 2.1. Nhìn dữ liệu như một cây cấu trúc

~~~text
order (object)
├── _id (string)
├── customer (object)
│   ├── customerId (string)
│   └── contact (object)
│       ├── email (string)
│       └── phone (string, tùy chọn)
├── shipping (object)
│   └── address (object)
│       ├── city (string)
│       └── street (string)
└── lines (array)
    ├── [0] (object)
    │   ├── sku (string)
    │   ├── quantity (int)
    │   ├── unitPrice (decimal)
    │   └── labels (array)
    │       ├── [0] (string)
    │       └── [1] (string)
    └── [1] (object)
        └── Các trường theo cùng quy tắc items
~~~

Với mỗi tầng object, ta cần đặt `bsonType: "object"`, `properties` và nếu cần `required`. Với mỗi tầng array, ta đặt `bsonType: "array"` rồi dùng `items` để mô tả cấu trúc **mỗi phần tử**.

## 3. Quy tắc cơ bản: object, properties và required

### 3.1. Trường lồng nhau

Xét một schema chỉ có thông tin khách hàng:

~~~javascript
const customerSchema = {
  bsonType: "object",
  required: ["customerId", "contact"],
  properties: {
    customerId: {
      bsonType: "string",
      minLength: 1
    },
    contact: {
      bsonType: "object",
      required: ["email"],
      properties: {
        email: {
          bsonType: "string",
          minLength: 3
        },
        phone: {
          bsonType: "string"
        }
      }
    }
  }
};
~~~

Ở đây:

- `customerId` và `contact` phải tồn tại trong object `customer`.
- `contact` phải là object, không thể là chuỗi hoặc mảng.
- Bên trong `contact`, `email` bắt buộc; `phone` là trường tùy chọn.
- `email` phải là chuỗi. `minLength: 3` chỉ kiểm tra chiều dài tối thiểu; nó không thay thế kiểm tra địa chỉ email đầy đủ.

**`required` chỉ yêu cầu trường có mặt.** Nó không tự bảo đảm giá trị khác `null`, không bảo đảm đúng kiểu hay không rỗng. Nếu muốn loại bỏ `null` thì phải khai báo kiểu phù hợp, chẳng hạn `bsonType: "string"`.

### 3.2. Khi nào schema của object lồng nhau được áp dụng?

Giả sử schema cha viết:

~~~javascript
{
  bsonType: "object",
  properties: {
    customer: customerSchema
  }
}
~~~

Schema này ràng buộc cấu trúc `customer` **nếu trường đó xuất hiện**, nhưng chưa bắt buộc document phải có `customer`.

Muốn chắc chắn document luôn có trường này:

~~~javascript
{
  bsonType: "object",
  required: ["customer"],
  properties: {
    customer: customerSchema
  }
}
~~~

Tương tự, muốn bắt buộc `customer.contact.email` thì cần hoàn chỉnh đường đi:

1. Document gốc bắt buộc có `customer`.
2. Schema `customer` bắt buộc có `contact`.
3. Schema `contact` bắt buộc có `email`.
4. `bsonType` tại mỗi tầng phải đúng kiểu kỳ vọng.

Không thể chỉ thêm chuỗi `"customer.contact.email"` vào `required` của document gốc để thay thế toàn bộ các tầng như trên.

### 3.3. Trường không khai báo và additionalProperties

Theo mặc định, object có thể chứa thêm các trường không được liệt kê trong `properties`. Muốn khóa cấu trúc ở một tầng, dùng:

~~~javascript
{
  bsonType: "object",
  required: ["name"],
  additionalProperties: false,
  properties: {
    name: { bsonType: "string" }
  }
}
~~~

Ví dụ này chấp nhận `{name:"An"}` nhưng từ chối `{name:"An",age:25}`.

**Cảnh báo ở tầng gốc:** MongoDB thường có trường `_id`. Nếu đặt `additionalProperties: false` ở document gốc thì phải khai báo `_id` trong `properties`, kể cả khi nó không nằm trong `required`:

~~~javascript
{
  bsonType: "object",
  additionalProperties: false,
  properties: {
    _id: { bsonType: ["objectId", "string"] },
    name: { bsonType: "string" }
  }
}
~~~

Nếu bỏ qua `_id`, một document MongoDB hợp lệ về mặt nghiệp vụ vẫn có thể bị từ chối vì trường `_id` bị coi là “không được phép”.

## 4. Kiểm tra mảng và phần tử mảng

### 4.1. Phân biệt kiểm tra mảng và kiểm tra từng phần tử

~~~javascript
{
  bsonType: "array"
}
~~~

Chỉ kiểm tra trường là một mảng; các phần tử có thể thuộc nhiều kiểu khác nhau. Để bắt buộc mảng chuỗi:

~~~javascript
{
  bsonType: "array",
  items: {
    bsonType: "string"
  }
}
~~~

Kết quả mong đợi:

| Giá trị | Kết quả |
|---|---|
| `["new", "gift"]` | Hợp lệ |
| `[]` | Hợp lệ nếu không đặt `minItems` |
| `["new", 42]` | Không hợp lệ: có phần tử không phải string |
| `"new"` | Không hợp lệ: bản thân trường không phải array |
| `null` | Không hợp lệ nếu chỉ cho phép `bsonType: "array"` |

`items` áp dụng với **mọi phần tử**. Một mảng 100 phần tử, chỉ một phần tử sai kiểu, cũng vi phạm schema.

### 4.2. Ràng buộc số lượng phần tử

~~~javascript
{
  bsonType: "array",
  minItems: 1,
  maxItems: 20,
  items: { bsonType: "string" }
}
~~~

- `minItems: 1` loại bỏ mảng rỗng.
- `maxItems: 20` giới hạn tối đa 20 phần tử.
- Cả hai kiểm tra **độ dài mảng**, không kiểm tra độ dài chuỗi bên trong.

Nếu cần chuỗi mỗi phần tử dài ít nhất ba ký tự, đặt `minLength` ở schema trong `items`:

~~~javascript
{
  bsonType: "array",
  minItems: 1,
  items: {
    bsonType: "string",
    minLength: 3
  }
}
~~~

### 4.3. Mảng object

Đây là dạng thường gặp của danh sách dòng hàng:

~~~javascript
{
  bsonType: "array",
  minItems: 1,
  items: {
    bsonType: "object",
    required: ["sku", "quantity"],
    properties: {
      sku: {
        bsonType: "string",
        minLength: 1
      },
      quantity: {
        bsonType: "int",
        minimum: 1
      }
    }
  }
}
~~~

Mỗi phần tử phải là object, có hai trường bắt buộc và `quantity` thuộc kiểu BSON Int32, không nhỏ hơn `1`.

Chỉ viết `required: ["sku", "quantity"]` tại document gốc sẽ không ràng buộc các phần tử trong mảng. Phải đặt `required` **bên trong schema của `items`**.

### 4.4. uniqueItems không phải unique theo một thuộc tính

~~~javascript
{
  bsonType: "array",
  uniqueItems: true,
  items: {
    bsonType: "string"
  }
}
~~~

Với mảng chuỗi, `uniqueItems: true` ngăn giá trị chuỗi trùng nhau theo phép so sánh phần tử của schema. Với mảng object, tính duy nhất áp dụng cho **toàn phần tử**, không tự hiểu rằng giá trị của một trường như `sku` phải duy nhất.

Ví dụ:

~~~javascript
[
  { sku: "A", quantity: 1 },
  { sku: "A", quantity: 2 }
]
~~~

Hai object không giống hệt nhau, nên không thể trông chờ `uniqueItems: true` để cấm trùng `sku`. Muốn cấm trùng theo khóa nghiệp vụ, có thể kiểm tra ở tầng ứng dụng hoặc thiết kế lại thành collection con với unique compound index phù hợp. Một unique multikey index không bảo đảm cấm hai phần tử có cùng khóa trong **cùng một document** theo cách nhiều người thường suy đoán.

## 5. Tạo collection có validator nhiều tầng

Trong `mongosh`, chọn database thực hành:

~~~javascript
use schema_validation_lab
~~~

Định nghĩa schema dùng lại cho collection `ordersValidated`:

~~~javascript
const orderSchema = {
  bsonType: "object",
  required: ["customer", "shipping", "lines"],
  properties: {
    _id: {
      bsonType: ["objectId", "string"]
    },

    customer: {
      bsonType: "object",
      required: ["customerId", "contact"],
      properties: {
        customerId: {
          bsonType: "string",
          minLength: 1
        },
        contact: {
          bsonType: "object",
          required: ["email"],
          properties: {
            email: {
              bsonType: "string",
              minLength: 3,
              pattern: "^[^@ ]+@[^@ ]+\\.[^@ ]+$"
            },
            phone: {
              bsonType: "string"
            }
          }
        }
      }
    },

    shipping: {
      bsonType: "object",
      required: ["address"],
      properties: {
        address: {
          bsonType: "object",
          required: ["city", "street"],
          properties: {
            city: {
              bsonType: "string",
              minLength: 1
            },
            street: {
              bsonType: "string",
              minLength: 1
            },
            postalCode: {
              bsonType: "string"
            }
          }
        }
      }
    },

    lines: {
      bsonType: "array",
      minItems: 1,
      maxItems: 100,
      items: {
        bsonType: "object",
        required: ["sku", "quantity", "unitPrice"],
        properties: {
          sku: {
            bsonType: "string",
            minLength: 1
          },
          quantity: {
            bsonType: "int",
            minimum: 1
          },
          unitPrice: {
            bsonType: "decimal",
            minimum: NumberDecimal("0")
          },
          labels: {
            bsonType: "array",
            uniqueItems: true,
            items: {
              bsonType: "string",
              minLength: 1
            }
          }
        }
      }
    }
  }
};
~~~

Các lớp kiểm tra:

1. Document gốc là `object`; `customer`, `shipping` và `lines` bắt buộc.
2. `customer.contact` là object và cần có `email` kiểu string.
3. `shipping.address` là object và cần có `city`, `street`.
4. `lines` là array có **1 đến 100 phần tử**.
5. Mỗi phần tử `lines[i]` phải là object có `sku` string không rỗng, `quantity` Int32 ≥ 1 và `unitPrice` Decimal128 ≥ 0.
6. Nếu phần tử có `labels`, trường đó phải là mảng chuỗi không rỗng, không có phần tử trùng hoàn toàn.

Ví dụ dùng `NumberDecimal("0")` cho giá trị ngưỡng so sánh tương ứng với trường tiền dạng Decimal128. Biểu thức `pattern` chỉ minh họa ràng buộc hình thức chuỗi email cơ bản; hệ thống thật nên có kiểm tra và xác minh email riêng.

Tạo collection nếu chưa có:

~~~javascript
if (db.getCollectionInfos({ name: "ordersValidated" }).length === 0) {
  db.createCollection("ordersValidated", {
    validator: {
      $jsonSchema: orderSchema
    },
    validationLevel: "strict",
    validationAction: "error"
  });
}
~~~

Việc kiểm tra tồn tại ở đây giúp tránh lỗi “collection already exists” khi chạy lại bài. **Nếu collection đã tồn tại với một validator khác, đoạn `if` không tự cập nhật validator**; cách xem và cập nhật cấu hình được trình bày ở mục 10.

### 5.1. Bảng ánh xạ từ yêu cầu sang vị trí schema

| Yêu cầu nghiệp vụ | Vị trí khai báo | Quy tắc |
|---|---|---|
| Đơn hàng phải có khách hàng | Schema gốc | `required: ["customer", ...]` |
| Khách hàng phải có thông tin liên hệ | `properties.customer` | `required: ["contact", ...]` |
| Liên hệ phải có email | `properties.customer.properties.contact` | `required: ["email"]` |
| Địa chỉ giao hàng phải có thành phố | `shipping → address` | `required: ["city", ...]` |
| Đơn hàng có ít nhất một dòng hàng | `properties.lines` | `bsonType:"array", minItems:1` |
| Mỗi dòng hàng có số lượng ≥ 1 | `properties.lines.items.properties.quantity` | `bsonType:"int", minimum:1` |
| Mỗi dòng hàng có giá Decimal128 | `properties.lines.items.properties.unitPrice` | `bsonType:"decimal"` |
| Mỗi nhãn là chuỗi | `lines.items.properties.labels.items` | `bsonType:"string"` |

Cách đọc từ gốc xuống từng tầng giúp tránh đặt nhầm `required` hoặc `items` ở vị trí chỉ kiểm tra “vỏ” của document.

## 6. Chèn document hợp lệ

Chèn một đơn hàng đáp ứng toàn bộ các điều kiện:

~~~javascript
db.ordersValidated.insertOne({
  _id: "ord-001",
  customer: {
    customerId: "C001",
    contact: {
      email: "lan@example.test",
      phone: "0900000000"
    }
  },
  shipping: {
    address: {
      city: "Hà Nội",
      street: "12 Phố Huế",
      postalCode: "100000"
    }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(2),
      unitPrice: NumberDecimal("19.90"),
      labels: ["new", "gift"]
    },
    {
      sku: "BOOK-02",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("10.50")
    }
  ]
});
~~~

Nếu collection được tạo như mục 5 và chưa có `_id: "ord-001"`, kết quả thường có `acknowledged: true` và `insertedId: "ord-001"`.

Quan sát:

~~~javascript
db.ordersValidated.findOne({ _id: "ord-001" });
db.ordersValidated.countDocuments({});
~~~

Trong document thứ hai của mảng `lines`, trường `labels` không xuất hiện nhưng vẫn hợp lệ, vì `labels` chỉ là trường **tùy chọn**. Nếu không muốn cho phép thiếu `labels`, cần thêm tên trường đó vào `required` của schema **từng phần tử**.

Nếu chạy lại `insertOne` y hệt, sẽ gặp lỗi duplicate `_id`. Điều đó không liên quan đến schema validation. Để lặp lại bài, dùng một `_id` mới hoặc thay đổi document bằng `updateOne`.

## 7. Các ví dụ vi phạm validator

Khi `validationAction: "error"`, lệnh ghi document không hợp lệ thường thất bại với lỗi **Document failed validation**, mã lỗi MongoDB thường là **121**. Nội dung chi tiết có thể nằm trong `errInfo.details`, tùy server và driver.

Các ví dụ tiếp theo **được thiết kế để thất bại**. Chạy từng lệnh riêng trong môi trường bài học; nếu shell ném exception, hãy đọc lỗi rồi tiếp tục ví dụ sau. Mỗi đoạn dùng một `_id` khác nhau để dễ phân biệt.

### 7.1. Thiếu object bắt buộc ở gốc

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-missing-shipping",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("5.00")
    }
  ]
});
~~~

**Kỳ vọng:** Bị từ chối vì thiếu `shipping` ở document gốc.

### 7.2. Có object nhưng thiếu trường sâu bên trong

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-missing-email",
  customer: {
    customerId: "C002",
    contact: {}
  },
  shipping: {
    address: {
      city: "Huế",
      street: "1 Trần Hưng Đạo"
    }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("5.00")
    }
  ]
});
~~~

**Kỳ vọng:** Bị từ chối vì `customer.contact.email` là trường `required` trong object `contact`.

### 7.3. Object lồng nhau sai kiểu

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-address-type",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  shipping: {
    address: "Huế"
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("5.00")
    }
  ]
});
~~~

**Kỳ vọng:** Bị từ chối vì `shipping.address` phải là `object`, không phải `string`.

### 7.4. Mảng rỗng

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-empty-lines",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  shipping: {
    address: {
      city: "Huế",
      street: "1 Trần Hưng Đạo"
    }
  },
  lines: []
});
~~~

**Kỳ vọng:** Bị từ chối do `minItems: 1` tại `lines`.

### 7.5. Một phần tử của mảng sai kiểu

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-array-element",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  shipping: {
    address: {
      city: "Huế",
      street: "1 Trần Hưng Đạo"
    }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("5.00")
    },
    "BOOK-02"
  ]
});
~~~

**Kỳ vọng:** Bị từ chối vì phần tử `lines[1]` là chuỗi; schema `items` yêu cầu **mọi phần tử** là object.

### 7.6. Phần tử là object nhưng sai trường

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-quantity",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  shipping: {
    address: {
      city: "Huế",
      street: "1 Trần Hưng Đạo"
    }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(0),
      unitPrice: NumberDecimal("5.00")
    }
  ]
});
~~~

**Kỳ vọng:** Bị từ chối vì `quantity` là Int32 nhưng vi phạm `minimum: 1`.

Những giá trị như `"2"` (string), `NumberLong("2")` (Int64) hay `2.5` (Double) cũng không phù hợp nếu schema yêu cầu chính xác `bsonType: "int"`. Việc một số có thể đọc được như số nguyên không có nghĩa nó đã mang đúng kiểu BSON.

### 7.7. Mảng lồng trong phần tử có giá trị lặp

~~~javascript
db.ordersValidated.insertOne({
  _id: "bad-duplicate-label",
  customer: {
    customerId: "C002",
    contact: { email: "an@example.test" }
  },
  shipping: {
    address: {
      city: "Huế",
      street: "1 Trần Hưng Đạo"
    }
  },
  lines: [
    {
      sku: "BOOK-01",
      quantity: NumberInt(1),
      unitPrice: NumberDecimal("5.00"),
      labels: ["gift", "gift"]
    }
  ]
});
~~~

**Kỳ vọng:** Bị từ chối vì `labels` có `uniqueItems: true`.

### 7.8. Giá trị null và trường không tồn tại

Hai tình huống khác nhau:

~~~javascript
// A: Không có contact.email
contact: {}

// B: Có email nhưng giá trị null
contact: { email: null }
~~~

Trường hợp A vi phạm `required: ["email"]`. Trường hợp B đáp ứng điều kiện **có tên trường** nhưng vi phạm `bsonType: "string"` của email. Nếu nghiệp vụ chấp nhận null, có thể dùng `bsonType: ["string", "null"]`, nhưng việc chấp nhận null phải là lựa chọn có chủ đích.

Đối với mảng, `lines: null` không phải mảng rỗng; nó vi phạm `bsonType: "array"`. Một mảng rỗng `[]` thì đúng kiểu array nhưng vẫn vi phạm `minItems: 1`.

### 7.9. Bảng tổng hợp lỗi

| Dữ liệu không hợp lệ | Điều kiện bị vi phạm | Tầng cần sửa |
|---|---|---|
| Không có `customer` | `required` tại document gốc | Gốc |
| `customer: "Lan"` | `bsonType: "object"` | `customer` |
| Không có `contact.email` | `required` tại `contact` | `contact` |
| `shipping.address: []` | `bsonType: "object"` | `shipping.address` |
| `lines: []` | `minItems: 1` | `lines` |
| `lines: "BOOK-01"` | `bsonType: "array"` | `lines` |
| `lines: ["BOOK-01"]` | `items.bsonType: "object"` | Từng phần tử |
| Một dòng hàng thiếu `sku` | `items.required` | Từng object trong mảng |
| `quantity: NumberInt(0)` | `minimum: 1` | Trường trong phần tử |
| `labels: ["a", "a"]` | `uniqueItems: true` | Mảng con |
| `labels: ["a", 42]` | `items.bsonType: "string"` | Phần tử mảng con |

## 8. Validator áp dụng với update và $push như thế nào?

Schema validation không chỉ hoạt động khi `insertOne`. Khi một update dẫn tới document vi phạm và chế độ strict/error đang bật, server cũng có thể từ chối update.

### 8.1. Cập nhật object lồng nhau hợp lệ

Trên document `ord-001` đã chèn ở mục 6:

~~~javascript
db.ordersValidated.updateOne(
  { _id: "ord-001" },
  {
    $set: {
      "shipping.address.city": "Đà Nẵng",
      "customer.contact.phone": "0911111111"
    }
  }
);
~~~

Hai trường mới phù hợp schema; update thành công nếu document còn tồn tại và tài khoản có quyền ghi.

### 8.2. Cập nhật khiến object lồng nhau vi phạm

~~~javascript
db.ordersValidated.updateOne(
  { _id: "ord-001" },
  {
    $set: {
      "shipping.address": "Đà Nẵng"
    }
  }
);
~~~

**Kỳ vọng:** Bị từ chối vì `shipping.address` sẽ thành chuỗi. MongoDB kiểm tra document sau cập nhật theo quy tắc đang áp dụng. Không nên hiểu rằng `$set` ở một đường dẫn sâu sẽ bỏ qua validator của object cha.

Tương tự, dùng `$unset` xóa `customer.contact.email` sẽ vi phạm trường `required` nếu validator strict/error.

### 8.3. Thêm phần tử hợp lệ vào mảng

~~~javascript
db.ordersValidated.updateOne(
  { _id: "ord-001" },
  {
    $push: {
      lines: {
        sku: "BOOK-03",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("12.00"),
        labels: ["promo"]
      }
    }
  }
);
~~~

Điều này hợp lệ khi tổng số phần tử chưa vượt `maxItems: 100`.

### 8.4. Thêm phần tử sai bằng $push

~~~javascript
db.ordersValidated.updateOne(
  { _id: "ord-001" },
  {
    $push: {
      lines: {
        sku: "BOOK-04",
        quantity: NumberInt(-1),
        unitPrice: NumberDecimal("12.00")
      }
    }
  }
);
~~~

**Kỳ vọng:** Bị từ chối vì phần tử mới vi phạm `minimum: 1` tại `lines.items.properties.quantity`. Phần tử không hợp lệ sẽ không được thêm vào document khi thao tác thất bại.

### 8.5. Vượt quá maxItems

Với mảng có `maxItems: 100`, dù từng phần tử đều đúng cấu trúc, document sau update vẫn không hợp lệ nếu `lines` có 101 phần tử. Điều này cho thấy hai nhóm quy tắc kiểm soát độc lập:

- Quy tắc của **mảng**: độ dài, tính duy nhất.
- Quy tắc của **phần tử**: kiểu và nội dung từng object.

Với dữ liệu lớn hoặc cập nhật mảng thường xuyên, còn cần cân nhắc kích thước document tối đa của MongoDB và mô hình dữ liệu; schema validation không thay thế việc thiết kế quan hệ/collection phù hợp.

## 9. Sử dụng các ràng buộc nâng cao đúng tầng

### 9.1. Mảng object có additionalProperties: false

Giả sử mỗi dòng hàng chỉ được chứa `sku`, `quantity` và `unitPrice`:

~~~javascript
const strictLineItemSchema = {
  bsonType: "object",
  required: ["sku", "quantity", "unitPrice"],
  additionalProperties: false,
  properties: {
    sku: { bsonType: "string", minLength: 1 },
    quantity: { bsonType: "int", minimum: 1 },
    unitPrice: {
      bsonType: "decimal",
      minimum: NumberDecimal("0")
    }
  }
};
~~~

Nếu đặt schema này ở `lines.items`, document có phần tử chứa thêm `discountCode` sẽ bị từ chối. Trong schema mục 5, `additionalProperties` chưa bị khóa, nên trường mới có thể được thêm vào nếu không vi phạm quy tắc khác.

Khóa toàn bộ trường có thể hữu ích khi cần hợp đồng dữ liệu rất chặt, nhưng cũng làm việc mở rộng schema phức tạp hơn. Cần biết trước hệ thống nào đang ghi những trường tùy chọn hay thông tin mở rộng.

### 9.2. Mảng hai chiều

MongoDB hỗ trợ schema lồng nhiều tầng. Ví dụ một ma trận gồm các hàng, mỗi hàng có đúng ba số nguyên Int32:

~~~javascript
const matrixSchema = {
  bsonType: "array",
  minItems: 1,
  items: {
    bsonType: "array",
    minItems: 3,
    maxItems: 3,
    items: { bsonType: "int" }
  }
};
~~~

Giá trị hợp lệ:

~~~javascript
[
  [NumberInt(1), NumberInt(2), NumberInt(3)],
  [NumberInt(4), NumberInt(5), NumberInt(6)]
]
~~~

Giá trị không hợp lệ:

~~~javascript
[
  [NumberInt(1), NumberInt(2)],
  [NumberInt(3), "4", NumberInt(5)]
]
~~~

Hàng đầu chỉ có hai phần tử; hàng thứ hai có chuỗi `"4"`. Các quy tắc `minItems`, `maxItems` và `items` ở từng cấp được áp dụng tương ứng.

### 9.3. Mảng cho phép nhiều kiểu phần tử

Nếu nghiệp vụ thật sự cho phép cả chuỗi và số nguyên trong mảng:

~~~javascript
{
  bsonType: "array",
  items: {
    bsonType: ["string", "int"]
  }
}
~~~

Dùng union type có chủ đích, tránh cấu hình quá rộng làm mất ý nghĩa của validator. Với một danh sách `lines` đại diện dòng hàng, nên giữ mọi phần tử cùng một kiểu object.

### 9.4. Ràng buộc giá trị và định dạng

Ngoài kiểu, có thể thêm:

- `minLength` / `maxLength` cho chuỗi.
- `pattern` cho biểu thức chính quy kiểm tra chuỗi.
- `minimum` / `maximum` cho giá trị số.
- `enum` cho tập giá trị cho phép.
- `minItems` / `maxItems` cho số phần tử mảng.

Ví dụ ràng buộc trạng thái của từng dòng:

~~~javascript
{
  bsonType: "string",
  enum: ["NEW", "RESERVED", "SHIPPED"]
}
~~~

MongoDB không tự **trim**, chuyển chữ hoa/chữ thường hoặc ép kiểu đầu vào để “cứu” một giá trị sai schema. Ứng dụng phải chuẩn hóa trước khi ghi nếu đó là yêu cầu.

## 10. Đọc và thay đổi validator đã tạo

### 10.1. Xem metadata collection

~~~javascript
use schema_validation_lab

db.getCollectionInfos({ name: "ordersValidated" });
~~~

Lấy riêng cấu hình:

~~~javascript
const info = db.getCollectionInfos({ name: "ordersValidated" })[0];

if (info) {
  printjson(info.options.validator);
  print("validationLevel: " + info.options.validationLevel);
  print("validationAction: " + info.options.validationAction);
}
~~~

`getCollectionInfos()` trả metadata. Nếu `validator` chưa được cấu hình hoặc tài khoản không đủ quyền để xem, thông tin có thể thiếu/không trả về như mong đợi.

### 10.2. Điều chỉnh bằng collMod

Một collection đã tồn tại không thể được cập nhật bằng cách gọi lại `createCollection`. Lệnh `collMod` dùng để thay đổi cấu hình hỗ trợ:

~~~javascript
db.runCommand({
  collMod: "ordersValidated",
  validator: {
    $jsonSchema: orderSchema
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Đây là ví dụ **áp dụng lại cùng schema** để minh họa cú pháp. Khi thay đổi schema thực tế, phải đối chiếu dữ liệu hiện có, client đang ghi và kế hoạch triển khai. Thay một trường từ optional thành required có thể làm update trên document cũ bị lỗi.

Lưu ý `orderSchema` là biến được định nghĩa tại mục 5 trong cùng phiên `mongosh`. Nếu mở phiên mới, cần khai báo biến lại hoặc nhập schema đầy đủ trước khi gọi `collMod`.

### 10.3. strict và moderate

Hai mức `validationLevel` thường dùng:

| Mức | Ý nghĩa |
|---|---|
| `strict` | Áp dụng validator cho mọi insert và update chịu kiểm tra; giá trị mặc định khi bật validation |
| `moderate` | Kiểm tra insert mới và update trên document hiện hữu đang hợp lệ; không bắt buộc sửa ngay những document cũ vốn đã không hợp lệ |

`moderate` có thể hữu ích khi chuyển tiếp collection cũ nhiều dữ liệu bẩn. Tuy nhiên, nó cũng cho phép một số cập nhật trên document đã không hợp lệ tiếp tục diễn ra, nên không nên coi moderate là cách thay thế bước dọn dữ liệu.

### 10.4. error và warn

| Chế độ | Khi document không hợp lệ |
|---|---|
| `validationAction: "error"` | Từ chối thao tác ghi vi phạm |
| `validationAction: "warn"` | Cho phép ghi nhưng phát cảnh báo theo cơ chế logging của server |

Trong giai đoạn đánh giá dữ liệu cũ, có thể bắt đầu bằng `warn` để phát hiện luồng ghi không phù hợp trước khi chuyển sang `error`. Cần có nơi thu thập và giám sát cảnh báo; đừng mặc định client sẽ luôn nhận một lỗi khi server chỉ đang ở chế độ warn.

MongoDB có cơ chế cho phép một số thao tác dùng `bypassDocumentValidation` **khi tài khoản có quyền tương ứng**. Đây là khả năng dành cho hoạt động quản trị/nhập liệu có kiểm soát, không nên dùng trong logic ứng dụng thông thường để bỏ qua validator.

### 10.5. Validator mới và dữ liệu đã tồn tại

Thêm validator vào một collection có dữ liệu sẵn **không có nghĩa MongoDB tự quét, sửa hoặc xóa mọi document cũ vi phạm**. Những document cũ có thể vẫn tồn tại; cách các update tiếp theo bị kiểm tra phụ thuộc `validationLevel`.

Muốn triển khai an toàn:

1. Khảo sát dữ liệu cũ, xác định trường thiếu, sai kiểu và phần tử mảng không hợp lệ.
2. Sửa hoặc lập kế hoạch xử lý dữ liệu vi phạm.
3. Chọn chế độ phù hợp để quan sát đường ghi.
4. Cập nhật validator.
5. Theo dõi lỗi ghi và cảnh báo; chuyển sang strict/error khi có thể.

## 11. Tìm document không khớp một schema

`$jsonSchema` cũng có thể xuất hiện trong biểu thức truy vấn để đối chiếu document với schema. Ví dụ trên một collection lịch sử:

~~~javascript
db.legacyOrders.find({
  $nor: [
    { $jsonSchema: orderSchema }
  ]
});
~~~

Điều kiện trên tìm các document **không thỏa** `orderSchema`. Nó hữu ích khi khảo sát dữ liệu cần chuẩn hóa trước khi bật validation ở mức chặt.

Nếu collection `legacyOrders` chưa tồn tại, lệnh có thể chỉ trả về tập rỗng; ví dụ này minh họa mẫu truy vấn. Có thể dùng chính schema `orderSchema` trong `$jsonSchema` để giữ nhất quán giữa bước kiểm tra và validator dự định.

Để biết kiểu thật của một trường phức hợp, có thể dùng aggregation:

~~~javascript
db.ordersValidated.aggregate([
  {
    $project: {
      customerType: { $type: "$customer" },
      contactType: { $type: "$customer.contact" },
      linesType: { $type: "$lines" },
      lineCount: {
        $cond: [
          { $isArray: "$lines" },
          { $size: "$lines" },
          null
        ]
      }
    }
  }
]);
~~~

Trước khi sửa dữ liệu hàng loạt, cần định nghĩa hành vi cho từng loại sai: bỏ qua, sửa tự động khi không mơ hồ, hoặc yêu cầu rà soát thủ công. Chẳng hạn một `quantity` lưu `"2"` có thể chuyển thành Int32 nếu định dạng hợp lệ, nhưng `"2.5"` hoặc `"hai"` cần quy tắc nghiệp vụ rõ.

## 12. Tìm lỗi validation từ phản hồi ghi

Khi một lệnh insert/update bị từ chối, mongosh/driver thường trả lỗi có mã và thông tin như `Document failed validation`. Thực hiện một ví dụ bắt lỗi:

~~~javascript
try {
  db.ordersValidated.insertOne({
    _id: "bad-catch-example",
    customer: {
      customerId: "C099",
      contact: {}
    },
    shipping: {
      address: {
        city: "Hà Nội",
        street: "10 Tràng Tiền"
      }
    },
    lines: [
      {
        sku: "BOOK-01",
        quantity: NumberInt(1),
        unitPrice: NumberDecimal("5.00")
      }
    ]
  });

  print("Đã ghi thành công");
} catch (error) {
  print("Code: " + error.code);
  print("Message: " + error.message);

  if (error.errInfo) {
    printjson(error.errInfo);
  }
}
~~~

Với cấu hình strict/error, kết quả mong đợi là lỗi do thiếu `customer.contact.email`. Tùy phiên bản MongoDB, cấu trúc `errInfo.details` có thể nêu schema keyword bị vi phạm, đường dẫn hoặc chi tiết phần tử. Không nên viết chương trình dựa cứng vào nguyên văn thông báo lỗi vì định dạng có thể thay đổi.

Trong ứng dụng Java/Spring Data MongoDB, lỗi server có thể được driver hoặc tầng truy cập dữ liệu bọc trong exception khác. Xử lý lỗi nên phân biệt **sai đầu vào** với **lỗi hạ tầng**, đồng thời không ghi toàn bộ document chứa dữ liệu nhạy cảm vào log.

### 12.1. Phân biệt lỗi validation với lỗi khác

| Lỗi | Ý nghĩa |
|---|---|
| `Document failed validation`, thường mã 121 | Document không đáp ứng validator trong chế độ từ chối |
| `E11000 duplicate key` | Trùng giá trị index unique, thường là `_id` |
| `not authorized` | Tài khoản không đủ quyền thực hiện thao tác |
| `NamespaceExists` | Tạo collection đã tồn tại |
| Lỗi BSON/serialization ở client | Dữ liệu không thể được chuyển thành BSON hợp lệ trước khi gửi |
| Lỗi mạng hoặc timeout | Chưa chắc server đã chấp nhận hay từ chối thao tác; cần kiểm tra trạng thái theo ngữ cảnh |

Validator không thay thế **unique index**, phân quyền hoặc bảo đảm giao dịch. Mỗi cơ chế xử lý một nhóm quy tắc khác nhau.

## 13. MongoDB Compass và schema validation

MongoDB Compass cung cấp giao diện để xem document và một số thiết lập collection; các chức năng chính xác phụ thuộc phiên bản Compass và quyền server.

Các bước thực hành:

1. Kết nối đến server đang chứa database `schema_validation_lab`.
2. Mở collection `ordersValidated` và xem tab **Documents**.
3. Lọc bằng `{"_id":"ord-001"}` để quan sát trường `customer`, `shipping` và `lines`. Chuyển giữa dạng Tree/JSON nếu phiên bản hỗ trợ.
4. Mở khu vực **Validation** hoặc cấu hình collection nếu có, đọc validator đang áp dụng. Đối chiếu với `db.getCollectionInfos({name:"ordersValidated"})` từ mongosh.
5. Thử tạo một document có `lines: []` bằng chức năng Insert Document trong Compass, với đầy đủ các trường khác. Với strict/error, thao tác dự kiến bị từ chối.
6. Chỉnh sửa một phần tử `lines` để `quantity` thành số không hợp lệ hoặc sai kiểu, rồi lưu; validator sẽ được áp dụng khi ghi.
7. Phục hồi hoặc tạo dữ liệu hợp lệ và xác nhận document lưu được.

Khi nhập dữ liệu JSON vào Compass, chú ý **kiểu BSON**. `unitPrice` trong schema yêu cầu Decimal128, nên không thể giả định số JSON thông thường `19.90` được nhập thành Decimal128. Trong giao diện hỗ trợ Extended JSON, biểu diễn kiểu số thập phân có thể là:

~~~json
{
  "unitPrice": { "$numberDecimal": "19.90" }
}
~~~

Trong `mongosh`, dùng constructor rõ ràng `NumberDecimal("19.90")`. Tương tự, muốn bảo đảm số lượng là Int32, dùng `NumberInt(2)` trong shell hoặc typed editor tương ứng trong Compass.

Nếu Compass chưa hiện thông báo validation chi tiết hoặc không có khu vực cấu hình ở phiên bản đang dùng, dùng `mongosh` để xem `options.validator` và chạy các ví dụ ghi. Hai client tuân theo cùng validator vì server là nơi kiểm tra.

## 14. Những giới hạn cần biết

### 14.1. Schema hợp lệ chưa chắc nghiệp vụ hợp lệ

Schema ở mục 5 xác nhận một dòng có `unitPrice` không âm và `quantity` dương. Nó chưa chứng minh rằng SKU tồn tại trong catalog, giá đang có hiệu lực, khách hàng có quyền mua hàng hoặc tổng tiền bằng tổng các dòng.

Những ràng buộc liên đối tượng hay phụ thuộc trạng thái hệ thống nên được xử lý trong logic ứng dụng, transaction hoặc thiết kế dữ liệu phù hợp.

### 14.2. Kiểm tra mảng không đồng nghĩa xác thực tính duy nhất theo khóa

`uniqueItems` ngăn phần tử trùng hoàn toàn theo cách so sánh. Với mảng object, nó **không** tự áp dụng unique theo `sku`. Nếu nghiệp vụ yêu cầu mỗi SKU chỉ xuất hiện một lần trong đơn, ứng dụng có thể chuẩn hóa danh sách theo SKU trước khi ghi hoặc sử dụng mô hình riêng cho dòng hàng.

### 14.3. Schema có thể quá chặt khi dữ liệu thay đổi

Ví dụ giới hạn `maxItems: 100` có thể không phù hợp với đơn hàng bán sỉ; `bsonType: "int"` có thể không tương thích driver đang gửi số lượng ở kiểu Int64. Cần thống nhất hợp đồng dữ liệu giữa client, driver, backend và MongoDB trước khi áp dụng.

### 14.4. Kiểm tra schema có chi phí

Validator chạy khi ghi nên schema sâu, nhiều phần tử mảng và điều kiện phức tạp có thể làm tăng chi phí xử lý. Chi phí này thường xứng đáng để bảo đảm tính toàn vẹn dữ liệu, nhưng cần đo trên workload thực, nhất là với array rất lớn và tần suất update cao.

### 14.5. Schema không tự sửa dữ liệu

Validator không tự chuyển chuỗi `"2"` thành Int32, không tự gán `default` như nhiều hệ thống ORM, và không tự loại bỏ trường dư. Cần chuẩn hóa đầu vào hoặc thực hiện migration có kiểm soát.

### 14.6. Giới hạn kích thước document vẫn tồn tại

Một document BSON MongoDB có giới hạn kích thước tối đa. Dù mảng `lines` thỏa `items` và `maxItems`, việc nhồi quá nhiều dữ liệu vào một document có thể gây vấn đề thiết kế, chi phí cập nhật hoặc giới hạn kích thước. Khi tập phần tử tăng không có giới hạn nghiệp vụ, hãy cân nhắc tách thành collection riêng.

## 15. Bài thực hành tổng hợp

Thực hiện trong database `schema_validation_lab` với collection `ordersValidated`:

1. Định nghĩa `orderSchema` ở mục 5 và tạo collection bằng `db.createCollection`.
2. Chèn document `ord-001` hợp lệ; chạy `findOne` để xem dữ liệu.
3. Thử thiếu `customer`, thiếu `customer.contact.email` và thay `shipping.address` bằng string. Ghi nhận các điều kiện bị vi phạm.
4. Thử `lines: []`, `lines: "BOOK-01"`, rồi mảng chứa một phần tử string. So sánh lỗi ở cấp mảng và lỗi ở cấp phần tử.
5. Thử `quantity: NumberInt(0)` và `quantity: "2"` trong phần tử; giải thích `minimum` và `bsonType` khác nhau thế nào.
6. Thử `labels: ["gift","gift"]`; giải thích tại sao `uniqueItems` hợp lý cho mảng nhãn, nhưng không bảo đảm SKU duy nhất trong mảng dòng hàng.
7. Thực hiện update `shipping.address.city` hợp lệ, rồi thử update cả `shipping.address` thành string.
8. Thêm phần tử `lines` hợp lệ bằng `$push`, sau đó thử thêm phần tử có `quantity` âm.
9. Đọc metadata bằng `db.getCollectionInfos`, xác nhận `validator`, `validationLevel` và `validationAction`.
10. Quan sát collection trong Compass; thử một thao tác ghi vi phạm schema và đối chiếu kết quả với mongosh.

Các lệnh đối chiếu nhanh:

~~~javascript
use schema_validation_lab

db.getCollectionInfos({ name: "ordersValidated" });

db.ordersValidated.findOne({ _id: "ord-001" });

db.ordersValidated.aggregate([
  {
    $project: {
      _id: 1,
      customerType: { $type: "$customer" },
      shippingType: { $type: "$shipping" },
      linesType: { $type: "$lines" },
      lineCount: { $size: "$lines" }
    }
  }
]);
~~~

Lưu ý lệnh `$size` ở cuối giả định document hợp lệ có `lines` là mảng. Khi khảo sát dữ liệu cũ chưa chuẩn hóa, nên kiểm tra `$isArray` trước khi gọi `$size` như ví dụ ở mục 11.

### Câu hỏi kiểm tra

**Câu 1.** Một schema khai báo `properties.customer.contact.properties.email` nhưng không khai báo `required` ở bất kỳ tầng nào. Document hoàn toàn thiếu `customer` có bị từ chối không?

*Gợi ý đáp án:* Không, chỉ `properties` không tự bắt buộc trường hiện diện. Muốn yêu cầu email bắt buộc phải có các `required` tương ứng ở từng tầng của đường dẫn.

**Câu 2.** `{ bsonType: "array", minItems: 1 }` có bảo đảm mọi phần tử là object không?

*Gợi ý đáp án:* Không. Nó kiểm tra kiểu mảng và số lượng; cần `items: { bsonType: "object" }` để kiểm tra phần tử.

**Câu 3.** Vì sao `lines[0].quantity` dùng `NumberLong("2")` có thể bị từ chối dù giá trị là số nguyên 2?

*Gợi ý đáp án:* Schema yêu cầu BSON `int` (Int32), còn `NumberLong` tạo `long` (Int64). Kiểu BSON không giống nhau.

**Câu 4.** Đặt `uniqueItems: true` trong mảng object có bảo đảm mọi `sku` chỉ xuất hiện một lần không?

*Gợi ý đáp án:* Không. Quy tắc này so sánh cả phần tử, không phải duy nhất một trường bên trong object.

**Câu 5.** Vì sao không nên thêm `additionalProperties: false` ở document gốc mà bỏ qua `_id`?

*Gợi ý đáp án:* MongoDB lưu trường `_id`; nếu schema không cho phép trường này, document có thể bị từ chối vì `_id` bị coi là trường dư.

**Câu 6.** Thay đổi validator sang strict/error có tự xóa các document cũ sai schema không?

*Gợi ý đáp án:* Không. Cần chủ động khảo sát và xử lý dữ liệu tồn tại, rồi kiểm soát các thao tác ghi về sau theo chế độ validation.

## 16. Nguyên tắc ghi nhớ

- **Đối với object:** dùng `bsonType: "object"`, `properties` và `required` ở đúng tầng.
- **Đối với array:** dùng `bsonType: "array"`; thêm `minItems`/`maxItems` nếu cần kiểm soát số lượng.
- **Đối với phần tử array:** dùng `items`; đặt `bsonType`, `required` và `properties` bên trong khi phần tử là object.
- **Đối với mảng lồng nhau:** lặp lại mô hình `items` ở mỗi tầng; validator có thể đi sâu nhiều cấp.
- **Đối với null/missing:** `required` kiểm tra sự hiện diện, `bsonType` kiểm tra kiểu; mảng rỗng khác mảng thiếu và khác `null`.
- **Đối với tính duy nhất:** `uniqueItems` kiểm tra phần tử; không nhầm với unique theo thuộc tính trong mảng object.
- **Đối với cập nhật:** validator cũng kiểm tra kết quả của `$set`, `$unset`, `$push` khi chế độ kiểm tra tương ứng được bật.
- **Đối với dữ liệu hiện có:** đọc metadata, khảo sát document sai schema và triển khai validator có kế hoạch. Không giả định việc bật validator tự sửa dữ liệu cũ.
- **Đối với client:** mongosh, Compass và Java Driver cùng chịu validator trên server, nhưng cần truyền đúng kiểu BSON để không bị từ chối.

Thiết kế schema validation theo đúng cây cấu trúc BSON giúp collection giữ được tính nhất quán ngay cả khi document chứa nhiều tầng object và mảng. Khi các quy tắc được đặt ở đúng vị trí, mỗi document được kiểm tra không chỉ ở cấu trúc tổng thể mà cả ở từng phần tử và trường sâu bên trong, tạo nền tảng đáng tin cậy cho truy vấn và xử lý nghiệp vụ.
