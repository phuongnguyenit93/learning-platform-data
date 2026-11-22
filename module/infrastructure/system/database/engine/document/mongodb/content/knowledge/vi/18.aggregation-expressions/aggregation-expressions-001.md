# Tham chiếu trường, biến hệ thống và phạm vi biến với $let trong MongoDB

Trong **MongoDB Aggregation Framework**, các biểu thức có thể lấy dữ liệu từ field của document đang xử lý, đọc **biến hệ thống** hoặc dùng **biến cục bộ** được khai báo bởi một toán tử. Cú pháp chỉ khác nhau một ký tự nhưng ý nghĩa thay đổi hoàn toàn:

- **"$status"** là một *field path*, lấy giá trị field status trong ngữ cảnh document hiện hành.
- **"$$ROOT"** là tham chiếu tới biến hệ thống ROOT, mang document được đưa vào biểu thức ở stage hiện tại.
- **"$$item.price"** là field price của giá trị biến item, thường được tạo trong $map hoặc $filter.
- **$let** đặt tên cho các kết quả trung gian, cho phép biểu thức bên trong **in** dùng chúng qua cú pháp **$$tenBien**.

Hiểu đúng các tham chiếu này giúp tránh lỗi dữ liệu sai, biến chưa được định nghĩa, dùng nhầm document gốc với phần tử mảng, và nhầm phạm vi biến khi xây dựng aggregation pipeline nhiều lớp.

Bài học tập trung vào **tham chiếu trường, biến hệ thống và phạm vi biến với $let**, đồng thời minh họa cách các khái niệm đó phối hợp với **$project**, **$set**, **$map**, **$filter**, **$reduce**, **$lookup** và **$expr**.

## 1. Phân biệt field path và variable reference

Giả sử một document được lưu như sau:

~~~javascript
{
  _id: "O-1001",
  customerId: "C-01",
  status: "PAID",
  shipping: {
    city: "HCM",
    fee: NumberDecimal("15000.00")
  },
  items: [
    {
      sku: "BOOK-01",
      quantity: 2,
      unitPrice: NumberDecimal("100000.00")
    }
  ]
}
~~~

Trong aggregation expression, có thể tham chiếu:

| Biểu thức | Nguồn dữ liệu |
| --- | --- |
| **"$status"** | Field status của document hiện hành |
| **"$shipping.city"** | Field city trong embedded document shipping |
| **"$$ROOT"** | Toàn bộ document đầu vào theo ngữ cảnh của stage |
| **"$$ROOT.status"** | Field status của document ROOT |
| **"$$CURRENT.status"** | Field status của document CURRENT |
| **"$$item"** | Giá trị biến item đã được khai báo ở phạm vi thích hợp |
| **"$$item.unitPrice"** | Field unitPrice thuộc document giữ trong biến item |
| **{ $literal: "$status" }** | Chuỗi nguyên văn "$status" |

Cú pháp **một dấu $** biểu thị *field path* khi giá trị là chuỗi expression; cú pháp **hai dấu $$** biểu thị *variable reference*. Hai cách không thể hoán đổi.

Ví dụ:

~~~javascript
{
  $map: {
    input: "$items",
    as: "item",
    in: "$$item.unitPrice"
  }
}
~~~

Biến **item** do $map tạo ra cho từng phần tử. Thay **$$item.unitPrice** bằng **$item.unitPrice** sẽ khiến MongoDB tìm field path **item.unitPrice** trên document của ngữ cảnh hiện hành, thay vì đọc biến phần tử array.

### 1.1. Aggregation expression khác JavaScript

Trong mongosh, chuỗi "$status" có thể được truyền tới MongoDB như một phần của pipeline:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      state: "$status"
    }
  }
]);
~~~

MongoDB server diễn giải chuỗi đó thành tham chiếu field. Trái lại:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      state: {
        $literal: "$status"
      }
    }
  }
]);
~~~

sẽ tạo field state chứa **chuỗi literal "$status"**, không phải giá trị PAID/PENDING từ document.

Người viết JavaScript tạo ra object mô tả pipeline, còn MongoDB **đánh giá aggregation expressions ở server**. Biến JavaScript của mongosh không tự trở thành biến aggregation của MongoDB.

## 2. Chuẩn bị bộ dữ liệu thực hành

Sử dụng mongosh và database riêng **aggregation_variables_lab**. Lệnh drop trong ví dụ chỉ được chạy ở môi trường thử nghiệm vì nó xóa toàn bộ collection.

~~~javascript
use aggregation_variables_lab

db.orders.drop();

db.orders.insertMany([
  {
    _id: "O-1001",
    customerId: "C-01",
    status: "PAID",
    createdAt: ISODate("2026-11-01T09:00:00Z"),
    discountRate: NumberDecimal("0.10"),
    shippingFee: NumberDecimal("15000.00"),
    shipping: { city: "HCM", method: "STANDARD" },
    items: [
      {
        sku: "BOOK-01",
        quantity: 2,
        unitPrice: NumberDecimal("100000.00")
      },
      {
        sku: "PEN-01",
        quantity: 1,
        unitPrice: NumberDecimal("50000.00")
      }
    ]
  },
  {
    _id: "O-1002",
    customerId: "C-02",
    status: "PENDING",
    createdAt: ISODate("2026-11-02T10:00:00Z"),
    discountRate: NumberDecimal("0.00"),
    shippingFee: NumberDecimal("0.00"),
    shipping: { city: "HN", method: "PICKUP" },
    items: [
      {
        sku: "BOOK-02",
        quantity: 1,
        unitPrice: NumberDecimal("300000.00")
      }
    ]
  },
  {
    _id: "O-1003",
    customerId: "C-01",
    status: "PAID",
    createdAt: ISODate("2026-11-03T11:00:00Z"),
    discountRate: NumberDecimal("0.05"),
    shippingFee: NumberDecimal("12000.00"),
    shipping: { city: "DN", method: "STANDARD" },
    items: [
      {
        sku: "PEN-02",
        quantity: 3,
        unitPrice: NumberDecimal("40000.00")
      }
    ]
  },
  {
    _id: "O-1004",
    customerId: "C-03",
    status: "DRAFT",
    createdAt: ISODate("2026-11-04T12:00:00Z"),
    discountRate: NumberDecimal("0.00"),
    shippingFee: NumberDecimal("0.00"),
    shipping: { city: "HCM", method: "STANDARD" },
    items: []
  }
]);

db.customers.drop();

db.customers.insertMany([
  { _id: "C-01", name: "Nguyễn An", tier: "GOLD" },
  { _id: "C-02", name: "Trần Bình", tier: "STANDARD" },
  { _id: "C-03", name: "Lê Chi", tier: "STANDARD" }
]);
~~~

Với dữ liệu trên, tổng tiền đơn hàng được xác định bằng:

~~~text
gross = tổng của (quantity × unitPrice) cho mỗi item
discountAmount = gross × discountRate
payable = gross - discountAmount + shippingFee
~~~

Kết quả mong đợi khi chưa có dữ liệu phát sinh khác:

| Order | gross | discountAmount | shippingFee | payable |
| --- | ---: | ---: | ---: | ---: |
| O-1001 | 250.000 | 25.000 | 15.000 | 240.000 |
| O-1002 | 300.000 | 0 | 0 | 300.000 |
| O-1003 | 120.000 | 6.000 | 12.000 | 126.000 |
| O-1004 | 0 | 0 | 0 | 0 |

Các ví dụ tính tiền dùng **NumberDecimal** để minh họa kiểu Decimal128. Trong ứng dụng thật cần thống nhất quy tắc làm tròn, tiền tệ và các ràng buộc nghiệp vụ.

## 3. Tham chiếu field bằng dấu $

### 3.1. Field top-level

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      orderStatus: "$status",
      customer: "$customerId"
    }
  }
]);
~~~

Trong một $project stage:

- **_id: 1** là cách yêu cầu giữ field _id.
- **orderStatus: "$status"** là expression lấy field status.
- **customer: "$customerId"** là expression lấy field customerId.

Không nên coi giá trị 1 của projection và chuỗi "$status" là cùng một loại cú pháp.

### 3.2. Field lồng nhau

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      city: "$shipping.city",
      deliveryMethod: "$shipping.method"
    }
  }
]);
~~~

Dấu chấm trong **"$shipping.city"** biểu diễn đi vào document con shipping và lấy field city.

### 3.3. Field nằm trong array

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      quantities: "$items.quantity",
      prices: "$items.unitPrice"
    }
  }
]);
~~~

Với O-1001, những expression này có thể tạo danh sách quantities **[2, 1]** và prices tương ứng. Tuy nhiên, danh sách prices **không** phải tổng tiền từng dòng; để tính quantity × unitPrice cần một biểu thức ứng với từng phần tử, chẳng hạn **$map** hoặc **$reduce**.

### 3.4. Field thiếu khác field có null

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      noteOrDefault: {
        $ifNull: [
          "$note",
          "Không có ghi chú"
        ]
      }
    }
  }
]);
~~~

**$ifNull** hữu ích khi field thiếu hoặc có null. Nhưng nó không tự xử lý mọi loại dữ liệu sai kiểu. Ví dụ một field đáng lẽ là array nhưng lại là string vẫn có thể gây lỗi cho các toán tử yêu cầu array.

## 4. Biến dùng hai dấu $$

Biến được tham chiếu như sau:

~~~text
$$name
$$name.child
$$name.child.deepField
~~~

Phần **name** phải tương ứng với một biến được khai báo hợp lệ hoặc biến hệ thống có sẵn.

Các nguồn khai báo biến phổ biến:

- **$let.vars** tạo biến trong biểu thức in.
- **$map.as** tạo biến cho phần tử array trong in.
- **$filter.as** tạo biến cho phần tử array trong cond.
- **$reduce** có hai biến ngữ cảnh **$$value** và **$$this**.
- **$lookup.let** tạo biến để pipeline ở collection được join sử dụng.
- Tùy chọn **let** của một số lệnh aggregation cho phép truyền biến cấp command.
- **$$ROOT**, **$$CURRENT**, **$$NOW**, **$$REMOVE** là các biến hệ thống với ngữ nghĩa riêng.

Ví dụ, tên biến được khai báo không có hai dấu dollar:

~~~javascript
{
  $map: {
    input: "$items",
    as: "line",
    in: "$$line.sku"
  }
}
~~~

**as: "line"** định nghĩa biến. **"$$line.sku"** là cách sử dụng biến.

### 4.1. Biến không tự tồn tại

~~~javascript
db.orders.aggregate([
  {
    $project: {
      result: "$$unknownVariable"
    }
  }
]);
~~~

Nếu **unknownVariable** không được khai báo ở scope hợp lệ, MongoDB có thể báo lỗi **Use of undefined variable**.

### 4.2. Tên biến nên rõ nghĩa

Tên do người dùng khai báo tuân theo quy tắc đặt tên biến MongoDB, thông thường bắt đầu bằng chữ ASCII thường hoặc ký tự phi ASCII hợp lệ; có thể có chữ, số, dấu gạch dưới theo quy tắc được hỗ trợ.

Nên dùng tên như **line**, **gross**, **taxRate**, **customerKey** thay vì tên quá ngắn trong pipeline lồng sâu. Tránh đặt tên dễ nhầm với **ROOT**, **CURRENT**, **NOW** và các biến hệ thống.

## 5. $$ROOT: document trong ngữ cảnh stage

**$$ROOT** tham chiếu document hiện là root của biểu thức ở stage đang thực thi.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      originalAtThisStage: "$$ROOT"
    }
  }
]);
~~~

Ở stage này, **originalAtThisStage** có thể chứa một bản của document order được đưa vào $project.

Tuy nhiên, **ROOT không bảo đảm là document nguyên thủy của toàn bộ pipeline**. Sau các stage làm thay đổi cấu trúc như $project, $set, $replaceRoot hoặc $unwind, document đi vào stage tiếp theo có thể đã khác.

Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      status: 1
    }
  },
  {
    $project: {
      currentRoot: "$$ROOT"
    }
  }
]);
~~~

Ở $project thứ hai, ROOT là document được tạo từ projection thứ nhất, không tự khôi phục customerId, shipping hoặc items đã bị loại.

### 5.1. $$ROOT bên trong $map

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      lines: {
        $map: {
          input: "$items",
          as: "item",
          in: {
            statusOfOrder: "$$ROOT.status",
            skuOfItem: "$$item.sku",
            quantityOfItem: "$$item.quantity"
          }
        }
      }
    }
  }
]);
~~~

Hai biến có ngữ cảnh khác nhau:

~~~text
$$ROOT.status   -> status của order tại stage
$$item.sku      -> sku của phần tử items đang duyệt
~~~

Đây là lý do dùng đúng **$$item** thay vì **$item** đặc biệt quan trọng trong biểu thức lồng.

## 6. $$CURRENT: điểm bắt đầu cho tham chiếu field

Trong nhiều expression thông thường:

~~~text
"$status"
~~~

tương đương tham chiếu:

~~~text
"$$CURRENT.status"
~~~

khi **CURRENT** trỏ đến document hiện hành.

Ví dụ:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      fieldStatus: "$status",
      currentStatus: "$$CURRENT.status",
      rootStatus: "$$ROOT.status"
    }
  }
]);
~~~

Ở ngữ cảnh này, ba field kết quả có cùng status.

**CURRENT và ROOT không đồng nghĩa về khái niệm.** CURRENT là ngữ cảnh được dùng để diễn giải đường dẫn bắt đầu bằng một dấu $, và MongoDB có cơ chế thay đổi ngữ cảnh CURRENT trong các biểu thức thích hợp. ROOT là root document theo stage hiện tại. Không nên giả định hai biến phải luôn cùng một giá trị trong mọi ngữ cảnh.

## 7. Tổng quan biến hệ thống

Các biến hệ thống thường gặp:

| Biến | Ý nghĩa | Trường hợp dùng |
| --- | --- | --- |
| **$$ROOT** | Root document trong stage hiện tại | $project, $group, biểu thức lồng |
| **$$CURRENT** | Ngữ cảnh hiện hành cho $field | Biểu thức đọc field |
| **$$NOW** | Giá trị ngày giờ hiện tại kiểu BSON Date, ổn định trong cùng pipeline | Thời gian, ngày đến hạn |
| **$$CLUSTER_TIME** | Cluster time kiểu BSON Timestamp khi được hỗ trợ | Ngữ cảnh cluster |
| **$$REMOVE** | Giá trị đặc biệt để loại field output trong ngữ cảnh phù hợp | $project, $addFields/$set |
| **$$KEEP** | Giữ document/subtree | $redact |
| **$$PRUNE** | Loại document/subtree | $redact |
| **$$DESCEND** | Xử lý tiếp cấu trúc con | $redact |
| **$$SEARCH_META** | Metadata tìm kiếm từ tính năng Search khi được hỗ trợ | MongoDB Search/Atlas Search |
| **$$USER_ROLES** | Role của người dùng hiện hành trong môi trường/phiên bản hỗ trợ | Một số policy/redaction |

Một số biến phụ thuộc **phiên bản MongoDB, loại deployment và stage**. Chẳng hạn, $$CLUSTER_TIME có ý nghĩa cluster và không phải phép thay thế cho BSON Date; $$SEARCH_META phụ thuộc vào tính năng Search.

## 8. $$NOW trong tính toán ngày giờ

Một expression thường gặp là kiểm tra thời gian đơn hàng đã tồn tại:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      createdAt: 1,
      observedAt: "$$NOW",
      ageMillis: {
        $subtract: [
          "$$NOW",
          "$createdAt"
        ]
      }
    }
  }
]);
~~~

Trừ hai giá trị BSON Date trả khoảng cách thời gian theo mili giây.

### 8.1. $$NOW ổn định trong một lần chạy pipeline

MongoDB giữ giá trị **$$NOW** nhất quán xuyên suốt các stage và document của một lần thực thi pipeline theo cơ chế hỗ trợ tương ứng. Nó không được tính lại tùy ý cho mỗi document.

~~~javascript
db.orders.aggregate([
  {
    $set: {
      observedAt: "$$NOW"
    }
  },
  {
    $project: {
      observedAt: 1,
      samePipelineNow: "$$NOW"
    }
  }
]);
~~~

Trong một lần chạy pipeline, hai field trên lấy từ cùng giá trị NOW.

### 8.2. $$NOW khác new Date() ở mongosh

~~~javascript
const timestampFromClient = new Date();
~~~

Dòng này được đánh giá trong môi trường JavaScript của mongosh, trước khi giá trị được truyền vào server. Trái lại, **"$$NOW"** được server giải nghĩa như biến hệ thống trong aggregation expression.

Khi cần một thời điểm cố định do nghiệp vụ chọn, ví dụ cutoff cuối tháng, có thể truyền một BSON Date cố định thay vì phụ thuộc NOW. Phải xác định rõ nguồn thời gian và múi giờ.

### 8.3. $dateDiff và timezone

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      daysOld: {
        $dateDiff: {
          startDate: "$createdAt",
          endDate: "$$NOW",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      }
    }
  }
]);
~~~

$dateDiff đếm theo quy tắc của đơn vị ngày và múi giờ, không luôn tương đương chia mili giây cho 86.400.000. Trong ứng dụng thực, cần chọn đúng đơn vị và timezone cho nghiệp vụ.

## 9. $$REMOVE: bỏ field có điều kiện

**$$REMOVE** là một giá trị đặc biệt, có thể dùng để yêu cầu loại một field khỏi kết quả của các stage hỗ trợ.

Ví dụ chỉ hiện thông tin shipping cho đơn PAID:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      shippingWhenPaid: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "$shipping",
          "$$REMOVE"
        ]
      }
    }
  }
]);
~~~

Với đơn PAID, trường **shippingWhenPaid** xuất hiện. Với đơn PENDING/DRAFT, trường đó bị loại khỏi kết quả, **không phải bị gán null**.

### 9.1. So sánh REMOVE và null

~~~javascript
// Gán null khi điều kiện sai:
{
  $cond: [
    { $eq: ["$status", "PAID"] },
    "$shipping",
    null
  ]
}
~~~

Cách này giữ field output với giá trị null. Dùng **"$$REMOVE"** để loại field khi đó mới là ý định.

### 9.2. Dùng trong update pipeline

~~~javascript
db.orders.updateOne(
  { _id: "O-1004" },
  [
    {
      $set: {
        optionalNote: {
          $cond: [
            { $eq: ["$status", "PAID"] },
            "Đã thanh toán",
            "$$REMOVE"
          ]
        }
      }
    }
  ]
);
~~~

Ở đây **$set** là aggregation stage trong một **update pipeline** (đối số là array). Nó khác **$set update operator** trong update document thông thường. Dấu $$REMOVE là expression được đánh giá bởi server.

## 10. Các biến liên quan $redact và cluster

Trong **$redact**, các giá trị hệ thống sau điều khiển cách xử lý cây document:

~~~text
$$KEEP     -> giữ nhánh hiện tại
$$PRUNE    -> loại nhánh hiện tại
$$DESCEND  -> đánh giá sâu vào các nhánh con
~~~

Ví dụ minh họa hình thức:

~~~javascript
db.records.aggregate([
  {
    $redact: {
      $cond: [
        { $eq: ["$accessLevel", "PUBLIC"] },
        "$$KEEP",
        "$$DESCEND"
      ]
    }
  }
]);
~~~

Đoạn này **không phải chính sách bảo mật hoàn chỉnh**. Cần định nghĩa rõ cách xử lý dữ liệu không có nhãn, tầng quyền truy cập và các trường hợp thiếu field trước khi dùng $redact để kiểm soát thông tin.

**$$CLUSTER_TIME** có kiểu BSON Timestamp và ý nghĩa trong điều phối cluster. Nếu cần tính tuổi đơn hàng, hiển thị lịch hoặc ngày quá hạn, **$$NOW** và BSON Date thông thường phù hợp hơn; không nên dùng $$CLUSTER_TIME thay trực tiếp cho Date.

## 11. Toán tử $let: cú pháp và mục đích

**$let là một expression operator**, không phải một stage độc lập của aggregation pipeline.

Cú pháp:

~~~javascript
{
  $let: {
    vars: {
      variableA: expressionA,
      variableB: expressionB
    },
    in: expressionUsingVariables
  }
}
~~~

Trong đó:

- **vars** là document khai báo biến cục bộ và biểu thức tính giá trị.
- **in** là biểu thức có thể đọc những biến đã khai báo bằng **$$variableA** và **$$variableB**.
- Scope của biến được giới hạn trong expression **in** của $let tương ứng.
- Các expression gán biến trong **vars** được đánh giá trong **phạm vi bên ngoài $let**, không phải trong phạm vi mà các biến cùng cấp vừa khai báo.

Ví dụ đơn giản:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      result: {
        $let: {
          vars: {
            base: 120,
            bonus: 30
          },
          in: {
            $add: [
              "$$base",
              "$$bonus"
            ]
          }
        }
      }
    }
  }
]);
~~~

Mỗi document có result = **150**.

### 11.1. Không thể đặt $let trực tiếp làm stage

Sai:

~~~javascript
db.orders.aggregate([
  {
    $let: {
      vars: { x: 1 },
      in: "$$x"
    }
  }
]);
~~~

Pipeline ngoài cùng cần stage hợp lệ. Cách đúng là đặt $let trong một expression:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      value: {
        $let: {
          vars: { x: 1 },
          in: "$$x"
        }
      }
    }
  }
]);
~~~

### 11.2. Tại sao dùng $let?

$let hữu ích khi biểu thức:

- Có nhiều giá trị trung gian cần đặt tên rõ nghĩa.
- Cần dùng lại một giá trị trong nhiều nhánh của expression **in**.
- Dễ bị nhầm giữa field path và biến phần tử array.
- Có nhiều bước tính toán cần tổ chức theo phạm vi.
- Cần biểu diễn logic có tên rõ ràng để người bảo trì đọc được.

$let không phải công cụ tự động tăng tốc mọi pipeline. Hiệu quả vẫn phụ thuộc dữ liệu, phép tính và optimizer của MongoDB.

## 12. Quy tắc quan trọng: vars cùng cấp không tham chiếu nhau

Xét:

~~~javascript
{
  $let: {
    vars: {
      low: 10,
      high: "$$low"
    },
    in: {
      $add: [
        "$$low",
        "$$high"
      ]
    }
  }
}
~~~

Thoạt nhìn có thể tưởng **high = low = 10**, và kết quả = 20. Cách hiểu này **không đúng**.

Trong phần khai báo **vars**, expression **"$$low"** của biến high nhìn vào **phạm vi bên ngoài $let**. Nó **không** đọc biến low đang được khai báo cạnh nó trong cùng vars.

Nếu bên ngoài không có low, phép tính có thể báo lỗi biến không được xác định. Nếu ngoài scope có low, high đọc giá trị đó.

### 12.1. Cách đúng: lồng thêm $let

~~~javascript
db.orders.aggregate([
  {
    $project: {
      example: {
        $let: {
          vars: {
            low: 10
          },
          in: {
            $let: {
              vars: {
                high: {
                  $multiply: [
                    "$$low",
                    2
                  ]
                }
              },
              in: {
                $add: [
                  "$$low",
                  "$$high"
                ]
              }
            }
          }
        }
      }
    }
  }
]);
~~~

$let ngoài tạo low = 10. Khi $let trong khai báo high, biến **$$low** đã có sẵn ở scope ngoài của nó. Do đó high = 20 và kết quả = 30.

### 12.2. Không xem vars là script tuần tự

Đừng diễn giải:

~~~javascript
vars: {
  x: 10,
  y: "$$x"
}
~~~

như JavaScript:

~~~javascript
let x = 10;
let y = x;
~~~

Vị trí trước/sau của key trong vars **không tạo quan hệ phụ thuộc tuần tự**. Muốn một biến dựa vào biến khác, phải tổ chức scope phù hợp.

## 13. Scope lồng nhau và shadowing

Một $let nằm bên trong **in** của $let khác có thể đọc các biến thuộc scope ngoài.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      example: {
        $let: {
          vars: {
            base: 100
          },
          in: {
            $let: {
              vars: {
                extra: 25
              },
              in: {
                $add: [
                  "$$base",
                  "$$extra"
                ]
              }
            }
          }
        }
      }
    }
  }
]);
~~~

Kết quả example = **125**.

### 13.1. Biến cùng tên ở scope trong che biến ngoài

~~~javascript
db.orders.aggregate([
  {
    $project: {
      example: {
        $let: {
          vars: {
            rate: 2
          },
          in: {
            $let: {
              vars: {
                rate: 5
              },
              in: "$$rate"
            }
          }
        }
      }
    }
  }
]);
~~~

Expression trong dùng rate = 5 của scope gần nhất, không dùng rate = 2 của scope ngoài. Hiện tượng này gọi là **shadowing**.

### 13.2. Biểu thức vars của scope trong vẫn đọc được biến ngoài

~~~javascript
db.orders.aggregate([
  {
    $project: {
      example: {
        $let: {
          vars: {
            amount: 100
          },
          in: {
            $let: {
              vars: {
                amount: {
                  $add: [
                    "$$amount",
                    20
                  ]
                }
              },
              in: "$$amount"
            }
          }
        }
      }
    }
  }
]);
~~~

Trong **vars** của $let trong, $$amount đọc amount = 100 của scope ngoài. Trong **in** của $let trong, $$amount đọc biến mới = 120.

Vì vậy kết quả = **120**, không phải phép tham chiếu đệ quy vô hạn.

### 13.3. Biến không tồn tại ở expression anh em

~~~javascript
db.orders.aggregate([
  {
    $project: {
      first: {
        $let: {
          vars: {
            temporary: 7
          },
          in: "$$temporary"
        }
      },
      second: "$$temporary"
    }
  }
]);
~~~

Field second ở **ngoài** $let tạo temporary. Nếu temporary không được khai báo ở phạm vi khác, expression second không hợp lệ vì biến chưa được định nghĩa.

Để nhiều field đầu ra cùng dùng một giá trị, có thể tính trước bằng **$set stage**, sau đó tham chiếu field ở các stage kế tiếp; hoặc tạo một object duy nhất bên trong expression in của $let.

## 14. $let khác $set stage

$let tạo **biến cục bộ trong expression**. Ngược lại, $set stage tạo **field trong document của pipeline**.

Ví dụ tạo gross bằng $set:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      gross: {
        $sum: {
          $map: {
            input: "$items",
            as: "line",
            in: {
              $multiply: [
                "$$line.quantity",
                "$$line.unitPrice"
              ]
            }
          }
        }
      }
    }
  },
  {
    $project: {
      _id: 1,
      gross: 1,
      discounted: {
        $multiply: [
          "$gross",
          {
            $subtract: [
              NumberDecimal("1"),
              "$discountRate"
            ]
          }
        ]
      }
    }
  }
]);
~~~

Stage thứ hai dùng **"$gross"**, vì gross đã trở thành field của document đầu vào stage đó. Không dùng **"$$gross"** trừ khi một biến tên gross được khai báo.

### 14.1. Field tạo trong cùng $set không sẵn cho field anh em

Ví dụ không nên kỳ vọng:

~~~javascript
{
  $set: {
    gross: {
      $sum: "$lineTotals"
    },
    net: {
      $multiply: [
        "$gross",
        NumberDecimal("0.9")
      ]
    }
  }
}
~~~

là cách để field net chắc chắn đọc gross vừa tạo. Các expression trong cùng stage được đánh giá dựa trên document đầu vào stage đó. Hãy dùng hai stage, hoặc $let lồng nhau, khi một phép tính phụ thuộc kết quả của phép tính khác.

~~~javascript
[
  {
    $set: {
      gross: {
        $sum: "$lineTotals"
      }
    }
  },
  {
    $set: {
      net: {
        $multiply: [
          "$gross",
          NumberDecimal("0.9")
        ]
      }
    }
  }
]
~~~

Ví dụ này giả định lineTotals là array số có sẵn trong document trước stage đầu.

## 15. Tính tiền đơn hàng bằng $let

Từ dữ liệu mẫu, có thể tính gross, discountRate và shippingFee trong cùng expression:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      status: 1,
      payable: {
        $let: {
          vars: {
            gross: {
              $sum: {
                $map: {
                  input: "$items",
                  as: "line",
                  in: {
                    $multiply: [
                      "$$line.quantity",
                      "$$line.unitPrice"
                    ]
                  }
                }
              }
            },
            rate: {
              $ifNull: [
                "$discountRate",
                NumberDecimal("0")
              ]
            },
            fee: {
              $ifNull: [
                "$shippingFee",
                NumberDecimal("0")
              ]
            }
          },
          in: {
            $add: [
              {
                $multiply: [
                  "$$gross",
                  {
                    $subtract: [
                      NumberDecimal("1"),
                      "$$rate"
                    ]
                  }
                ]
              },
              "$$fee"
            ]
          }
        }
      }
    }
  }
]);
~~~

Ở đây các biến gross, rate, fee **độc lập** với nhau trong vars:

- gross tính từ array items.
- rate tính từ discountRate.
- fee tính từ shippingFee.

Phần in có thể dùng cả ba vì chúng được khai báo cùng scope. Công thức: **gross × (1 - rate) + fee**.

### 15.1. Cần biến discountAmount dựa trên gross thì lồng scope

Không nên viết hai biến **gross** và **discountAmount** cùng cấp rồi dùng $$gross trong expression gán discountAmount. Thay vào đó:

~~~javascript
{
  $let: {
    vars: {
      gross: {
        $sum: "$lineTotals"
      }
    },
    in: {
      $let: {
        vars: {
          discountAmount: {
            $multiply: [
              "$$gross",
              "$discountRate"
            ]
          }
        },
        in: {
          gross: "$$gross",
          discountAmount: "$$discountAmount",
          afterDiscount: {
            $subtract: [
              "$$gross",
              "$$discountAmount"
            ]
          }
        }
      }
    }
  }
}
~~~

Biểu thức trên giả định có array lineTotals trước đó. Trong dữ liệu mẫu của bài, có thể thay phần gross bằng **$sum + $map** như ví dụ đầu mục.

## 16. $map: biến dành cho từng phần tử array

**$map** áp dụng một expression cho từng phần tử mảng:

~~~javascript
{
  $map: {
    input: arrayExpression,
    as: "item",
    in: itemExpression
  }
}
~~~

Ví dụ tính tiền mỗi dòng:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      lineTotals: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            sku: "$$line.sku",
            amount: {
              $multiply: [
                "$$line.quantity",
                "$$line.unitPrice"
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

Trong in:

- **$$line** là phần tử đang xử lý.
- **$$line.sku** đọc sku của phần tử đó.
- **$$line.quantity** và **$$line.unitPrice** phục vụ phép nhân.

### 16.1. Dùng $$this khi không khai báo as

~~~javascript
db.orders.aggregate([
  {
    $project: {
      lineTotals: {
        $map: {
          input: "$items",
          in: {
            $multiply: [
              "$$this.quantity",
              "$$this.unitPrice"
            ]
          }
        }
      }
    }
  }
]);
~~~

**$$this** là biến phần tử mặc định trong $map khi không dùng as.

Với biểu thức nhiều vòng lặp lồng nhau, đặt tên **as** rõ ràng thường giúp tránh nhầm $$this thuộc vòng nào.

### 16.2. $map lồng nhau

Giả sử document có groups, mỗi group có members:

~~~javascript
{
  groups: [
    {
      groupName: "A",
      members: [
        { userId: "U-1", score: 8 },
        { userId: "U-2", score: 9 }
      ]
    }
  ]
}
~~~

Có thể diễn đạt:

~~~javascript
{
  $map: {
    input: "$groups",
    as: "group",
    in: {
      name: "$$group.groupName",
      scores: {
        $map: {
          input: "$$group.members",
          as: "member",
          in: {
            userId: "$$member.userId",
            score: "$$member.score"
          }
        }
      }
    }
  }
}
~~~

Expression in của vòng trong có thể đọc cả $$member và $$group. $$member thuộc scope vòng trong, $$group thuộc scope vòng ngoài.

## 17. $let bên trong $map

$let thường được đặt ở **in** của $map để mỗi phần tử có những biến tính toán riêng.

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      itemsWithTax: {
        $map: {
          input: "$items",
          as: "item",
          in: {
            $let: {
              vars: {
                subtotal: {
                  $multiply: [
                    "$$item.quantity",
                    "$$item.unitPrice"
                  ]
                },
                taxRate: NumberDecimal("0.08")
              },
              in: {
                sku: "$$item.sku",
                subtotal: "$$subtotal",
                taxAmount: {
                  $multiply: [
                    "$$subtotal",
                    "$$taxRate"
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
~~~

Phạm vi:

~~~text
Document order
    |
    v
$map tạo biến item cho một phần tử
    |
    v
$let có quyền đọc $$item khi tính vars
    |
    v
$let.in dùng $$item, $$subtotal, $$taxRate
    |
    v
Trả một object cho phần tử hiện tại
~~~

Các expression gán subtotal và taxRate trong cùng vars không phụ thuộc nhau nên cấu trúc này hợp lệ.

### 17.1. $let ngoài $map

Khi có một tỷ lệ chung cho mọi phần tử của cùng document:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      amountsWithTax: {
        $let: {
          vars: {
            commonRate: NumberDecimal("0.08")
          },
          in: {
            $map: {
              input: "$items",
              as: "item",
              in: {
                $multiply: [
                  "$$item.quantity",
                  "$$item.unitPrice",
                  {
                    $add: [
                      NumberDecimal("1"),
                      "$$commonRate"
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
]);
~~~

$$commonRate tồn tại trong toàn bộ expression in của $let ngoài, nên $map bên trong có thể đọc nó.

## 18. $filter: biến trong điều kiện lọc array

**$filter** chọn những phần tử array thỏa điều kiện:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      largeQuantityLines: {
        $filter: {
          input: "$items",
          as: "line",
          cond: {
            $gte: [
              "$$line.quantity",
              2
            ]
          }
        }
      }
    }
  }
]);
~~~

Với O-1001, chỉ item có quantity = 2 được giữ. Với O-1002, quantity = 1 nên array kết quả rỗng.

### 18.1. $filter kết hợp $let

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      expensiveItems: {
        $let: {
          vars: {
            minimumPrice: NumberDecimal("80000.00")
          },
          in: {
            $filter: {
              input: "$items",
              as: "item",
              cond: {
                $gte: [
                  "$$item.unitPrice",
                  "$$minimumPrice"
                ]
              }
            }
          }
        }
      }
    }
  }
]);
~~~

Biến minimumPrice đến từ scope ngoài $filter; item đến từ $filter.as.

### 18.2. Khi input thiếu hoặc null

~~~javascript
{
  $filter: {
    input: {
      $ifNull: [
        "$items",
        []
      ]
    },
    as: "item",
    cond: {
      $gte: ["$$item.quantity", 2]
    }
  }
}
~~~

Dùng $ifNull khi items có thể null hoặc không tồn tại. Nếu items là string hay document sai kiểu thay vì array, cần schema validation hoặc chuyển đổi riêng, không mặc định $ifNull tự sửa mọi trường hợp.

## 19. $reduce: $$value và $$this

**$reduce** duyệt array và tích lũy một giá trị. Trong expression **in**, toán tử cung cấp:

- **$$value:** giá trị tích lũy hiện tại.
- **$$this:** phần tử đang xử lý.

Ví dụ tính gross:

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      gross: {
        $reduce: {
          input: "$items",
          initialValue: NumberDecimal("0"),
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.quantity",
                  "$$this.unitPrice"
                ]
              }
            ]
          }
        }
      }
    }
  }
]);
~~~

Với O-1001:

~~~text
Ban đầu:
  $$value = 0

Lượt 1:
  $$this = BOOK-01 (2 × 100000)
  $$value mới = 0 + 200000 = 200000

Lượt 2:
  $$this = PEN-01 (1 × 50000)
  $$value mới = 200000 + 50000 = 250000

Kết quả:
  gross = 250000
~~~

Với O-1004 có items rỗng, reduce trả về **initialValue = 0**.

### 19.1. Accumulator là document

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      summary: {
        $reduce: {
          input: "$items",
          initialValue: {
            lineCount: 0,
            gross: NumberDecimal("0")
          },
          in: {
            lineCount: {
              $add: [
                "$$value.lineCount",
                1
              ]
            },
            gross: {
              $add: [
                "$$value.gross",
                {
                  $multiply: [
                    "$$this.quantity",
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
~~~

$$value.lineCount và $$value.gross là tham chiếu **field bên trong biến accumulator**. Chúng không phải field path trực tiếp của document order.

### 19.2. So sánh $map + $sum với $reduce

Cả hai có thể tính tổng tiền:

~~~text
$map: tạo danh sách amount của từng item
$sum: cộng danh sách đó
~~~

hoặc:

~~~text
$reduce: cộng dồn trực tiếp qua $$value và $$this
~~~

$map + $sum dễ đọc khi công thức đơn giản. $reduce thích hợp hơn nếu accumulator gồm nhiều field hoặc phép tích lũy phức tạp. Hai cách có chi phí khác nhau tùy dữ liệu và engine; nên lựa chọn theo tính rõ ràng và yêu cầu thật.

## 20. $lookup.let: phạm vi biến giữa hai collection

Trong **$lookup dạng pipeline**, thuộc tính **let** đặt tên các giá trị lấy từ document **bên ngoài**, cho pipeline của collection được join tham chiếu.

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      let: {
        customerKey: "$customerId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $eq: [
                "$_id",
                "$$customerKey"
              ]
            }
          }
        },
        {
          $project: {
            _id: 1,
            name: 1,
            tier: 1
          }
        }
      ],
      as: "customer"
    }
  }
]);
~~~

Giải thích ngữ cảnh:

~~~text
orders document bên ngoài:
  customerId = "C-01"

$lookup.let:
  customerKey = "$customerId"

customers document bên trong:
  _id = "C-01"

$match + $expr:
  "$_id"          -> _id của customer hiện hành
  "$$customerKey" -> biến đã lấy từ order bên ngoài
~~~

### 20.1. Vì sao $match trong lookup dùng $expr?

Muốn so sánh một field với biến aggregation bên trong query filter của $match, cần **$expr**:

~~~javascript
{
  $match: {
    $expr: {
      $eq: [
        "$_id",
        "$$customerKey"
      ]
    }
  }
}
~~~

Nếu viết:

~~~javascript
{
  $match: {
    _id: "$$customerKey"
  }
}
~~~

không nên hiểu giá trị string đó như phép so sánh expression với biến. $match filter và aggregation expression có cách diễn giải khác nhau; $expr là cách phù hợp để sử dụng biểu thức trong điều kiện.

### 20.2. Dấu $ và $$ trong lookup

- **"$customerId"** trong let lấy field ở **order document bên ngoài**.
- **"$_id"** trong pipeline lấy field ở **customer document bên trong**.
- **"$$customerKey"** trong pipeline lấy biến do let cung cấp.

Đây là một trong những trường hợp dễ nhầm scope nhất khi dùng MongoDB aggregation.

### 20.3. $lookup.let khác toán tử $let

Toán tử $let:

~~~javascript
{
  $let: {
    vars: { x: "$field" },
    in: "$$x"
  }
}
~~~

Tùy chọn $lookup.let:

~~~javascript
{
  $lookup: {
    from: "customers",
    let: {
      x: "$customerId"
    },
    pipeline: [
      {
        $match: {
          $expr: {
            $eq: [
              "$_id",
              "$$x"
            ]
          }
        }
      }
    ],
    as: "joined"
  }
}
~~~

Hai cấu trúc đều cung cấp biến, nhưng **$lookup.let không có cặp vars/in** như $let expression.

### 20.4. Index khi dùng $lookup với $expr

MongoDB có thể dùng index trên collection được join trong một số phép so sánh $expr với giá trị let phù hợp. Nhưng có các hạn chế, đặc biệt khi giá trị let thiếu/rỗng và với multikey index. Không nên cho rằng mọi $lookup dùng $expr đều hiệu quả nhờ index. Với dữ liệu lớn cần xem explain và index trên collection được join.

## 21. Biến cấp lệnh aggregate và biến cục bộ

Một số phiên bản MongoDB hỗ trợ tùy chọn **let** của aggregation command, cho phép khai báo biến dùng bởi các expression của pipeline.

~~~javascript
db.orders.aggregate(
  [
    {
      $match: {
        $expr: {
          $gte: [
            "$createdAt",
            "$$cutoff"
          ]
        }
      }
    },
    {
      $project: {
        _id: 1,
        createdAt: 1,
        windowStart: "$$cutoff"
      }
    }
  ],
  {
    let: {
      cutoff: ISODate("2026-11-01T00:00:00Z")
    }
  }
);
~~~

Biến **cutoff** được truyền ở options của aggregate command, nên pipeline có thể tham chiếu **$$cutoff**.

### 21.1. Biến JavaScript không tự thành biến MongoDB

~~~javascript
const cutoff = ISODate("2026-11-01T00:00:00Z");
~~~

Dòng này chỉ định nghĩa biến trong mongosh. Nếu pipeline string có **"$$cutoff"**, server vẫn cần biến aggregation tên cutoff được truyền/khai báo đúng cách. Không nên nhầm biến client và biến server.

### 21.2. So sánh hai kiểu let

| Tiêu chí | Aggregate command let | Toán tử $let |
| --- | --- | --- |
| Vị trí | Options của aggregate command | Bên trong expression |
| Cú pháp | **let: { name: value }** | **$let: { vars: { ... }, in: ... }** |
| Phạm vi | Expression trong pipeline theo khả năng hỗ trợ | Expression in của chính $let |
| Tham chiếu | **$$name** | **$$name** |
| Mục đích | Tham số hóa một lần chạy | Tạo giá trị trung gian cục bộ |

Nếu một scope trong khai báo lại cùng tên biến, cần áp dụng quy tắc **shadowing** như mục 13.

## 22. $let trong $group

$let có thể được dùng bên trong biểu thức tính khóa nhóm hoặc biểu thức của accumulator khi phù hợp. Ví dụ phân loại đơn hàng theo gross đã tính:

~~~javascript
db.orders.aggregate([
  {
    $set: {
      gross: {
        $reduce: {
          input: "$items",
          initialValue: NumberDecimal("0"),
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.quantity",
                  "$$this.unitPrice"
                ]
              }
            ]
          }
        }
      }
    }
  },
  {
    $group: {
      _id: {
        $let: {
          vars: {
            largeOrder: {
              $gte: [
                "$gross",
                NumberDecimal("200000")
              ]
            }
          },
          in: {
            $cond: [
              "$$largeOrder",
              "LARGE",
              "SMALL"
            ]
          }
        }
      },
      count: { $sum: 1 },
      totalGross: { $sum: "$gross" }
    }
  }
]);
~~~

Ở $group:

- **_id** là **khóa nhóm** do expression tính ra, không mặc nhiên là field _id gốc.
- **$$largeOrder** chỉ tồn tại trong expression in của $let tạo khóa nhóm.
- **count** và **totalGross** là những accumulator riêng, không tự nhìn thấy $$largeOrder từ expression anh em.

Nếu cần tái sử dụng kết quả phân loại ở nhiều nơi, có thể tạo field phân loại bằng $set stage trước khi group.

## 23. String literal bắt đầu bằng dấu $ và field name đặc biệt

### 23.1. Dùng $literal khi chuỗi bắt đầu bằng $

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      literalText: {
        $literal: "$VIP"
      }
    }
  }
]);
~~~

Kết quả literalText chứa chuỗi **"$VIP"**.

Nếu viết:

~~~javascript
{
  $let: {
    vars: {
      label: "$VIP"
    },
    in: "$$label"
  }
}
~~~

biến label lại đọc field VIP, không lưu nguyên văn "$VIP". Cần bọc bằng $literal:

~~~javascript
{
  $let: {
    vars: {
      label: {
        $literal: "$VIP"
      }
    },
    in: "$$label"
  }
}
~~~

### 23.2. Field name thực sự chứa dấu chấm

Đường dẫn **"$price.usd"** thường được hiểu là field usd nằm trong embedded document price. Nhưng nếu document có **field top-level tên nguyên văn "price.usd"**, đây là một trường hợp khác.

Ở các phiên bản hỗ trợ, có thể dùng **$getField**:

~~~javascript
{
  $getField: {
    field: "price.usd",
    input: "$$ROOT"
  }
}
~~~

Với field name bắt đầu bằng dấu dollar, có thể cần **$literal** để biểu thị tên field nguyên văn. Không nên dùng dot notation cho field name đặc biệt khi ý định là truy cập tên literal.

## 24. Null, missing và kiểu dữ liệu

Các expression tham chiếu biến không tự sửa dữ liệu sai kiểu. Khi dữ liệu có thể thiếu:

~~~javascript
{
  $let: {
    vars: {
      rate: {
        $ifNull: [
          "$discountRate",
          NumberDecimal("0")
        ]
      },
      fee: {
        $ifNull: [
          "$shippingFee",
          NumberDecimal("0")
        ]
      }
    },
    in: {
      $add: [
        "$$fee",
        {
          $multiply: [
            NumberDecimal("100"),
            "$$rate"
          ]
        }
      ]
    }
  }
}
~~~

**$ifNull** xử lý null/missing. Nếu discountRate được lưu dạng string "0.10", cần xem xét chuyển sang Decimal128 theo quy tắc nghiệp vụ.

Ví dụ chuyển kiểu có fallback:

~~~javascript
{
  $convert: {
    input: "$discountRate",
    to: "decimal",
    onError: NumberDecimal("0"),
    onNull: NumberDecimal("0")
  }
}
~~~

**Cẩn trọng:** Trả về zero khi chuyển kiểu lỗi có thể che giấu dữ liệu hỏng. Trong nhiều nghiệp vụ, lỗi chuyển đổi cần được ghi log hoặc chặn ghi thay vì âm thầm thay bằng zero.

### 24.1. Array thiếu trong $map và $reduce

~~~javascript
{
  $reduce: {
    input: {
      $ifNull: [
        "$items",
        []
      ]
    },
    initialValue: NumberDecimal("0"),
    in: {
      $add: [
        "$$value",
        {
          $multiply: [
            "$$this.quantity",
            "$$this.unitPrice"
          ]
        }
      ]
    }
  }
}
~~~

Nếu items là null/missing, expression sử dụng array rỗng. Nhưng nếu items là string, cần schema validation hoặc logic chuyển đổi kiểu khác.

## 25. Java Sync Driver: xây biểu thức $let

MongoDB Java Sync Driver có thể biểu diễn aggregation expression bằng **Document** và các cấu trúc BSON.

Ví dụ dưới đây minh họa $let với những field giả định **grossAmount** và **discountRate** đã lưu ở document. Bộ dữ liệu thực hành đầu bài chưa có grossAmount sẵn; mục tiêu ở đây là cấu trúc API Java.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

import java.util.Arrays;

public class AggregationLetExample {

    public static void main(String[] args) {
        try (MongoClient client =
                MongoClients.create("mongodb://localhost:27017")) {

            MongoDatabase db =
                    client.getDatabase("aggregation_variables_lab");

            MongoCollection<Document> orders =
                    db.getCollection("orders");

            Document vars = new Document("gross", "$grossAmount")
                    .append("rate", "$discountRate");

            Document oneMinusRate = new Document(
                    "$subtract",
                    Arrays.asList(1, "$$rate")
            );

            Document netExpression = new Document(
                    "$multiply",
                    Arrays.asList("$$gross", oneMinusRate)
            );

            Document let = new Document("$let",
                    new Document("vars", vars)
                            .append("in", netExpression)
            );

            Document project = new Document("$project",
                    new Document("_id", 1)
                            .append("netAmount", let)
            );

            orders.aggregate(Arrays.asList(project))
                    .forEach(doc -> System.out.println(doc.toJson()));
        }
    }
}
~~~

Với ứng dụng tính tiền thật, cần thống nhất kiểu **Decimal128** cho những giá trị tham gia phép toán thay vì trộn số nguyên/double không kiểm soát.

### 25.1. Phân biệt biến Java và biến MongoDB

~~~java
String fieldReference = "$grossAmount";
~~~

Đây là biến của chương trình Java, chỉ được dùng khi tạo BSON command.

~~~javascript
{
  $let: {
    vars: {
      gross: "$grossAmount"
    },
    in: "$$gross"
  }
}
~~~

Đây là khai báo biến **gross trên server** trong MongoDB expression. String **"$$gross"** được server đánh giá theo phạm vi của $let, chứ không phải một biến Java.

### 25.2. Quan sát BSON command trước khi chạy

~~~java
System.out.println(project.toJson());
~~~

Việc nhìn cấu trúc BSON giúp phát hiện các lỗi như:

- Dùng nhầm "$field" và "$$variable".
- Đặt vars hoặc in sai cấp.
- Đưa $let lên cấp stage thay vì đặt trong expression.
- Thiếu $literal với string bắt đầu bằng dấu dollar.
- Tham chiếu một biến ngoài phạm vi.

Không ghi log dữ liệu khách hàng nhạy cảm khi chưa có biện pháp bảo vệ log phù hợp.

## 26. Tối ưu biểu thức và khả năng bảo trì

### 26.1. $let không tồn tại qua nhiều stage

Biến trong $let chỉ sống trong expression **in**. Muốn dùng giá trị ở nhiều stage, hãy tạo field bằng $set, dùng ở stage tiếp theo và có thể $unset trước khi trả kết quả.

### 26.2. $let không thay thế index

~~~javascript
db.orders.aggregate([
  {
    $project: {
      x: {
        $let: {
          vars: {
            state: "$status"
          },
          in: "$$state"
        }
      }
    }
  }
]);
~~~

Việc đặt tên biến state không giúp MongoDB tự dùng index cho truy vấn lọc status. Nếu cần lấy đơn PAID, đặt $match thích hợp:

~~~javascript
db.orders.aggregate([
  {
    $match: {
      status: "PAID"
    }
  },
  {
    $project: {
      status: 1
    }
  }
]);
~~~

Cấu trúc pipeline, index, tính chọn lọc và plan vẫn là yếu tố quan trọng cho hiệu năng.

### 26.3. Không lồng scope quá sâu nếu không cần

Một expression có 5–6 lớp $let lồng nhau có thể khó bảo trì. Khi phép tính có nhiều bước phụ thuộc nhau, cân nhắc:

- Chia thành các stage $set có tên field tạm dễ hiểu.
- Dùng $let ở phạm vi nhỏ, chỉ cho biến thật sự cục bộ.
- Đặt tên biến thể hiện nghiệp vụ.
- Giữ cùng một kiểu số khi tính tiền.
- Sử dụng $project cuối để trả đúng field mong muốn.

Tính rõ ràng thường giúp giảm lỗi thực tế nhiều hơn việc rút gọn vài dòng pipeline.

## 27. Các lỗi phổ biến

| Sai lầm | Cách hiểu đúng |
| --- | --- |
| Dùng **"$item.sku"** để đọc biến của $map | Phải dùng **"$$item.sku"** |
| **$$anything** tự tồn tại | Biến phải được khai báo trong scope hoặc là biến hệ thống |
| **$$ROOT** luôn là document nguyên gốc của toàn pipeline | ROOT thuộc ngữ cảnh document đầu vào stage hiện hành |
| **$$CURRENT** và **$$ROOT** luôn hoàn toàn giống nhau | CURRENT là ngữ cảnh field path; ROOT là root ở stage |
| Viết **"$VIP"** để trả chuỗi nguyên văn "$VIP" | Dùng **$literal** |
| Hai biến trong cùng vars của $let có thể khai báo phụ thuộc tuần tự | Mỗi expression khai báo nhìn scope **bên ngoài $let** |
| Biến tạo trong $let sử dụng được ở field anh em ngoài let | Chỉ in của $let được dùng biến đó |
| $let là pipeline stage | $let là **expression operator** |
| $set stage tạo gross và net cùng cấp, net luôn đọc gross mới | Tạo gross ở stage trước hoặc lồng scope đúng |
| $map tự cho field path **$sku** trỏ vào phần tử array | Dùng **$$item.sku** hoặc **$$this.sku** |
| $$this/$$value là những biến toàn cục | Chúng do toán tử như $map/$reduce cung cấp trong scope riêng |
| $lookup.let có vars/in như $let | $lookup.let là cấu trúc riêng |
| Trong $lookup, so sánh **_id: "$$key"** tự là expression | Dùng **$expr** trong $match khi cần so sánh với biến |
| $$NOW được tính lại với mỗi document | NOW ổn định trong một lần chạy pipeline |
| $$REMOVE tương đương null | REMOVE loại field; null là một value |
| $ifNull xử lý được mọi kiểu BSON sai | Nó xử lý null/missing; sai kiểu cần xử lý riêng |
| Dùng $let thì aggregation tự nhanh hơn | Hiệu năng còn phụ thuộc query plan và workload |

## 28. Bài thực hành

Các bài tập dùng database và collection đã tạo ở mục 2.

### Bài 1: so sánh field, CURRENT và ROOT

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      viaField: "$status",
      viaCurrent: "$$CURRENT.status",
      viaRoot: "$$ROOT.status",
      city: "$shipping.city"
    }
  }
]);
~~~

Giải thích vì sao ba cách lấy status giống nhau trong ví dụ, và vì sao $$ROOT sau một stage $project không còn mọi field gốc.

### Bài 2: literal

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      evaluated: "$status",
      literalText: {
        $literal: "$status"
      }
    }
  }
]);
~~~

Hãy chỉ ra sự khác biệt giữa giá trị của **evaluated** và **literalText**.

### Bài 3: $let đơn giản

~~~javascript
db.orders.aggregate([
  {
    $project: {
      answer: {
        $let: {
          vars: {
            a: 5,
            b: 7
          },
          in: {
            $multiply: [
              "$$a",
              "$$b"
            ]
          }
        }
      }
    }
  }
]);
~~~

Kết quả answer = **35**. Hãy giải thích vì sao tên khai báo trong vars không mang hai dấu dollar, còn tham chiếu trong in thì có.

### Bài 4: phát hiện lỗi scope

~~~javascript
{
  $let: {
    vars: {
      a: 10,
      b: {
        $multiply: [
          "$$a",
          3
        ]
      }
    },
    in: {
      $add: [
        "$$a",
        "$$b"
      ]
    }
  }
}
~~~

Giải thích tại sao b không tự bằng 30. Viết lại bằng **$let lồng nhau** để kết quả = 40.

### Bài 5: $map tạo lineTotals

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      lines: {
        $map: {
          input: "$items",
          as: "line",
          in: {
            sku: "$$line.sku",
            amount: {
              $multiply: [
                "$$line.quantity",
                "$$line.unitPrice"
              ]
            }
          }
        }
      }
    }
  }
]);
~~~

Với O-1001, xác định amount của BOOK-01 và PEN-01. Sau đó thay **$$line.unitPrice** bằng **$line.unitPrice** và giải thích vì sao không còn đọc đúng phần tử array.

### Bài 6: $filter kết hợp biến

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      selected: {
        $let: {
          vars: {
            threshold: NumberDecimal("80000")
          },
          in: {
            $filter: {
              input: "$items",
              as: "item",
              cond: {
                $gte: [
                  "$$item.unitPrice",
                  "$$threshold"
                ]
              }
            }
          }
        }
      }
    }
  }
]);
~~~

Hãy xác định threshold thuộc phạm vi nào và biến item thuộc phạm vi nào.

### Bài 7: $reduce tích lũy document

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      summary: {
        $reduce: {
          input: "$items",
          initialValue: {
            count: 0,
            gross: NumberDecimal("0")
          },
          in: {
            count: {
              $add: [
                "$$value.count",
                1
              ]
            },
            gross: {
              $add: [
                "$$value.gross",
                {
                  $multiply: [
                    "$$this.quantity",
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
~~~

Trả lời:

1. $$value chứa gì ở lượt đầu?
2. $$this thay đổi khi nào?
3. Vì sao O-1004 cho count = 0 và gross = 0?
4. Nếu muốn tổng quantity thay vì số dòng items, cần sửa phần count thế nào?

### Bài 8: $lookup let và $expr

~~~javascript
db.orders.aggregate([
  {
    $lookup: {
      from: "customers",
      let: {
        customerKey: "$customerId"
      },
      pipeline: [
        {
          $match: {
            $expr: {
              $eq: [
                "$_id",
                "$$customerKey"
              ]
            }
          }
        }
      ],
      as: "customerInfo"
    }
  }
]);
~~~

Phân tích từng nguồn giá trị: **"$customerId"** của order, **"$_id"** của customer, **"$$customerKey"** từ biến lookup.

### Bài 9: NOW và REMOVE

~~~javascript
db.orders.aggregate([
  {
    $project: {
      _id: 1,
      observedAt: "$$NOW",
      paidLabel: {
        $cond: [
          { $eq: ["$status", "PAID"] },
          "Đã thanh toán",
          "$$REMOVE"
        ]
      }
    }
  }
]);
~~~

Giải thích vì sao paidLabel biến mất ở những đơn chưa PAID thay vì xuất hiện với null.

### Bài 10: tính tiền nhiều bước

Hãy tự xây dựng pipeline từ các items và discountRate, tính:

1. gross = tổng quantity × unitPrice.
2. discountAmount = gross × discountRate.
3. net = gross - discountAmount.
4. payable = net + shippingFee.

Ràng buộc: **discountAmount phải đọc gross từ scope hợp lệ**, không khai báo cả hai cùng cấp vars rồi tham chiếu sai.

Một hướng:

~~~text
$let ngoài:
    khai báo gross
       |
       v
$let trong:
    khai báo discountAmount từ $$gross
       |
       v
in:
    tạo object chứa gross, discountAmount, net và payable
~~~

Kết quả mong đợi của O-1001 là gross **250.000**, discountAmount **25.000**, net **225.000**, payable **240.000**.

### Bài 11: biến command so với biến mongosh

~~~javascript
const cutoff = ISODate("2026-11-02T00:00:00Z");
~~~

Viết hai phiên bản:

- Truyền trực tiếp giá trị cutoff từ JavaScript vào pipeline khi tạo command.
- Khai báo **let: { cutoff: ... }** trong options của aggregate command rồi dùng **"$$cutoff"** ở pipeline.

Giải thích vì sao **const cutoff** ở mongosh không tự làm server hiểu **$$cutoff**.

## 29. Nguyên tắc ghi nhớ

Khi đọc một aggregation expression, cần tự trả lời:

1. **Giá trị này đọc từ field hay biến?** Một dấu $ cho field path, hai dấu $$ cho biến.
2. **Nguồn document là gì?** $$ROOT, $$CURRENT, phần tử $map, phần tử $filter hay document bên trong $lookup?
3. **Biến được khai báo tại đâu?** $let.vars, $map.as, $lookup.let hay biến hệ thống?
4. **Phạm vi còn hiệu lực không?** Một biến $let chỉ sống trong in; biến cùng cấp trong vars không nhìn thấy nhau.
5. **Dữ liệu là biểu thức hay literal?** Chuỗi bắt đầu bằng $ cần $literal nếu muốn giữ nguyên.
6. **Toán tử xử lý null, missing và kiểu BSON thế nào?** Không mặc định mọi schema đều sạch.

Quy tắc quan trọng nhất của **$let**:

> **Khai báo biến trong vars để dùng trong in; nếu một biến mới phụ thuộc một biến mới khác, hãy lồng thêm $let hoặc chia stage.** Đừng suy luận vars được thực thi tuần tự từ trên xuống.

Hiểu được lexical scope của các biến là nền tảng để xây dựng aggregation pipelines phức tạp mà vẫn đúng dữ liệu, dễ đọc và dễ bảo trì.

## Tài liệu tham khảo

- [MongoDB Manual — Aggregation Variables](https://www.mongodb.com/docs/manual/reference/aggregation-variables/)
- [MongoDB Manual — $let](https://www.mongodb.com/docs/manual/reference/operator/aggregation/let/)
- [MongoDB Manual — $map](https://www.mongodb.com/docs/manual/reference/operator/aggregation/map/)
- [MongoDB Manual — $filter](https://www.mongodb.com/docs/manual/reference/operator/aggregation/filter/)
- [MongoDB Manual — $reduce](https://www.mongodb.com/docs/manual/reference/operator/aggregation/reduce/)
- [MongoDB Manual — $lookup](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/)
- [MongoDB Manual — $expr](https://www.mongodb.com/docs/manual/reference/operator/query/expr/)
- [MongoDB Manual — $literal](https://www.mongodb.com/docs/manual/reference/operator/aggregation/literal/)
- [MongoDB Manual — $getField](https://www.mongodb.com/docs/manual/reference/operator/aggregation/getField/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
