# Kết hợp collection bằng $lookup và pipeline truy vấn con trong MongoDB

## 1. Khi một màn hình cần dữ liệu từ nhiều collection

MongoDB thường khuyến khích thiết kế document theo nhu cầu đọc: những dữ liệu có vòng đời gắn chặt và thường được đọc cùng nhau có thể được nhúng trong một document. Tuy nhiên, không phải quan hệ nào cũng phù hợp để nhúng. Một khách hàng có thể có hàng nghìn đơn hàng; đơn hàng có vòng đời, quyền truy cập và tần suất cập nhật khác hồ sơ khách hàng. Lúc đó, việc lưu **customers** và **orders** thành hai collection có thể hợp lý hơn.

Giả sử ứng dụng cần hiển thị:

- Tên khách hàng.
- Số đơn đã thanh toán của khách.
- Tổng giá trị các đơn đã thanh toán.
- Hai đơn đã thanh toán gần nhất.

Nếu chỉ đọc collection customers, ta chưa có dữ liệu đơn hàng. Nếu chỉ đọc orders, ta chưa có thông tin tên khách. **$lookup** trong aggregation pipeline giúp lấy dữ liệu từ một collection khác và gắn kết quả vào từng document đi qua pipeline.

Ví dụ cơ bản:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "orders"
    }
  }
]);
~~~

Về mặt ý tưởng, MongoDB lấy **customerCode** từ mỗi customer, tìm các order có **customerCode** tương ứng, rồi thêm một **Array orders** vào document khách hàng.

Tuy nhiên, nếu customerCode chỉ duy nhất **trong từng tenant**, phép nối đơn giản trên customerCode có thể kéo dữ liệu từ tenant khác. Ngoài ra, lấy **toàn bộ** orders chỉ để đếm hoặc tính tổng vừa tốn tài nguyên vừa dễ tạo mảng kết quả quá lớn. Những tình huống này là lý do cần dùng **$lookup với pipeline truy vấn con**.

### Sau bài này, bạn sẽ làm được

1. Viết **$lookup** dạng equality join bằng **localField/foreignField**.
2. Hiểu tính chất **left outer join**, kết quả Array và document không có bản ghi liên quan.
3. Viết **correlated subquery** bằng **let**, **$$variable**, **$match** và **$expr**.
4. Kết hợp điều kiện equality, range, status và sort bên trong **pipeline** của $lookup.
5. Chỉ trả những field cần thiết hoặc tổng hợp bên trong subquery bằng **$group**.
6. Dùng **$unwind**, **$size**, **$arrayElemAt**, **$ifNull** đúng với kết quả join.
7. Đọc **explain** và thiết kế index cho collection được lookup.
8. Tránh các lỗi bảo mật multi-tenant, nhân bản dữ liệu, tăng cardinality và vượt giới hạn document.

> Ví dụ chạy bằng **mongosh**, dùng database lab riêng **mongo_lookup_lab**. Bài học phân biệt rõ phép nối đơn giản và phép nối có điều kiện trên nhiều trường; không giả định MongoDB luôn tối ưu tương đương một cơ sở dữ liệu quan hệ với SQL JOIN.

## 2. $lookup hoạt động như thế nào?

### 2.1. Collection đầu vào và collection được nối

Trong pipeline:

~~~javascript
db.customers.aggregate([
  {
    $lookup: {
      from: "orders",
      localField: "customerCode",
      foreignField: "customerCode",
      as: "matchedOrders"
    }
  }
]);
~~~

**customers** là collection đầu vào của aggregate; **orders** là collection được truy vấn bởi $lookup.

| Thuộc tính | Vai trò |
| --- | --- |
| **from** | Tên collection sẽ lấy dữ liệu liên quan, trong cùng database của aggregation theo cú pháp thông thường |
| **localField** | Trường trong document đang đi qua pipeline |
| **foreignField** | Trường trong document thuộc collection ở **from** |
| **as** | Tên field Array dùng để lưu các document tìm thấy |

Kết quả mỗi customer có dạng:

~~~javascript
{
  _id: "cust-001",
  customerCode: "C001",
  name: "An",
  matchedOrders: [
    { _id: "ord-001", customerCode: "C001", amount: NumberDecimal("100.00") },
    { _id: "ord-002", customerCode: "C001", amount: NumberDecimal("50.00") }
  ]
}
~~~

Các trường của order trong ví dụ minh họa đã được lược bớt để dễ đọc. Khi dùng $lookup đơn giản mà không có projection bên trong, kết quả nối thường là **toàn bộ các document order khớp**.

### 2.2. Vì sao gọi là left outer join?

$lookup giữ lại document đầu vào **ngay cả khi không tìm thấy document tương ứng ở collection đích**. Khi không có kết quả, field trong **as** là Array rỗng.

~~~javascript
{
  _id: "cust-003",
  customerCode: "C003",
  name: "Chi",
  matchedOrders: []
}
~~~

Tính chất này gần với **left outer join** của SQL, nhưng kết quả MongoDB được **nhúng thành Array**, không tự nhân mỗi bản ghi cha thành nhiều dòng ở đầu ra như một SELECT JOIN thông thường.

Nếu muốn biểu diễn mỗi cặp customer–order thành một document riêng, có thể dùng **$unwind** sau $lookup. Khi unwind mà không giữ empty array, những customer không có order sẽ biến mất khỏi kết quả. Điều này tương tự chuyển từ phép nối giữ mọi bản ghi trái sang dạng chỉ còn các cặp có khớp.

### 2.3. Hai kiểu $lookup

**Dạng 1 — Equality join đơn giản**:

~~~javascript
{
  $lookup: {
    from: "orders",
    localField: "customerCode",
    foreignField: "customerCode",
    as: "orders"
  }
}
~~~

**Dạng 2 — Join với subpipeline và biến tương quan**:

~~~javascript
{
  $lookup: {
    from: "orders",
    let: {
      outerCode: "$customerCode",
      outerTenant: "$tenantId"
    },
    pipeline: [
      {
        $match: {
          $expr: {
            $and: [
              { $eq: ["$customerCode", "$$outerCode"] },
              { $eq: ["$tenantId", "$$outerTenant"] }
            ]
          }
        }
      }
    ],
    as: "orders"
  }
}
~~~

Subpipeline là một aggregation pipeline **chạy trên collection được lookup** trong bối cảnh của document đầu vào. Biến từ document bên ngoài được khai báo ở **let** và tham chiếu bằng hai dấu đô la **$$** trong biểu thức của pipeline con.

## 3. Chuẩn bị bộ dữ liệu lab có thể chạy lại

Bộ dữ liệu cố ý có **customerCode C001 xuất hiện ở hai tenant khác nhau**, để phép join đơn giản trên customerCode bộc lộ lỗi nối nhầm tenant.

### 3.1. Thiết kế dữ liệu

Collection **lab_customers**:

| _id | tenantId | customerCode | name | Ghi chú |
| --- | --- | --- | --- | --- |
| cust-001 | t001 | C001 | An | Có đơn hàng |
| cust-002 | t001 | C002 | Bình | Có đơn hàng |
| cust-003 | t001 | C003 | Chi | Không có đơn |
| cust-004 | t002 | C001 | Dung | **Trùng customerCode với tenant t001** |
| cust-005 | t002 | C004 | Em | Có một đơn pending |
| cust-006 | t001 | C005 | Hà | Không có đơn |

Collection **lab_orders** có 12 order. Các document nối với customer bằng **cặp tenantId/customerCode**, không phải customerCode đơn lẻ.

### 3.2. Script mongosh seed dữ liệu

Chạy nguyên khối:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_lookup_lab");
  const customers = lab.getCollection("lab_customers");
  const orders = lab.getCollection("lab_orders");
  const tag = "lookup-join-v1";

  // Chỉ dọn dữ liệu bài học, không drop collection/database.
  customers.deleteMany({ dataset: tag });
  orders.deleteMany({ dataset: tag });

  customers.insertMany([
    {
      _id: "cust-001", dataset: tag, tenantId: "t001",
      customerCode: "C001", name: "An", tier: "bronze"
    },
    {
      _id: "cust-002", dataset: tag, tenantId: "t001",
      customerCode: "C002", name: "Bình", tier: "gold"
    },
    {
      _id: "cust-003", dataset: tag, tenantId: "t001",
      customerCode: "C003", name: "Chi", tier: "silver"
    },
    {
      _id: "cust-004", dataset: tag, tenantId: "t002",
      customerCode: "C001", name: "Dung", tier: "gold"
    },
    {
      _id: "cust-005", dataset: tag, tenantId: "t002",
      customerCode: "C004", name: "Em", tier: "bronze"
    },
    {
      _id: "cust-006", dataset: tag, tenantId: "t001",
      customerCode: "C005", name: "Hà", tier: "silver"
    }
  ]);

  const orderRows = [
    // id, tenant, customerCode, status, amount, day, items
    ["ord-001", "t001", "C001", "paid",      "100.00",  1, ["A"]],
    ["ord-002", "t001", "C001", "pending",    "50.00",  2, ["B"]],
    ["ord-003", "t001", "C002", "paid",      "200.00",  3, ["A", "C"]],
    ["ord-004", "t001", "C002", "refunded",   "75.00",  4, ["D"]],
    ["ord-005", "t002", "C001", "paid",      "300.00",  5, ["E"]],
    ["ord-006", "t002", "C004", "pending",   "125.00",  6, ["A"]],
    ["ord-007", "t002", "C001", "paid",       "25.00",  7, ["B"]],
    // Một order không có customer tương ứng: dữ liệu mồ côi có chủ đích.
    ["ord-008", "t001", "MISSING", "paid",    "30.00",  8, ["Z"]],
    ["ord-009", "t001", "C001", "paid",      "150.00",  9, ["A"]],
    ["ord-010", "t001", "C002", "paid",      "150.00", 10, ["C"]],
    ["ord-011", "t002", "C001", "cancelled",  "90.00", 11, ["E"]],
    ["ord-012", "t001", "C002", "pending",    "20.00", 12, ["B"]]
  ];

  orders.insertMany(
    orderRows.map(([id, tenant, code, status, amount, day, skus]) => ({
      _id: id,
      dataset: tag,
      tenantId: tenant,
      customerCode: code,
      status: status,
      amount: NumberDecimal(amount),
      createdAt: new Date(Date.UTC(2026, 0, day, 8, 0, 0)),
      items: skus.map(sku => ({
        sku: sku,
        quantity: NumberInt(1)
      }))
    }))
  );

  // Index hỗ trợ tìm customer theo tenant và mã nghiệp vụ.
  customers.createIndex(
    { dataset: 1, tenantId: 1, customerCode: 1 },
    { name: "ux_lab_customer_code_per_tenant", unique: true }
  );

  // Index trên collection đích của các ví dụ $lookup.
  orders.createIndex(
    {
      dataset: 1, tenantId: 1, customerCode: 1,
      status: 1, createdAt: -1, _id: 1
    },
    { name: "ix_lab_order_join_status_time" }
  );

  // Index đơn cho ví dụ chỉ nối bằng customerCode.
  orders.createIndex(
    { customerCode: 1 },
    { name: "ix_lab_order_code_only" }
  );

  printjson({
    customers: customers.countDocuments({ dataset: tag }),
    orders: orders.countDocuments({ dataset: tag }),
    t001Orders: orders.countDocuments({
      dataset: tag, tenantId: "t001"
    }),
    t002Orders: orders.countDocuments({
      dataset: tag, tenantId: "t002"
    })
  });
})();
~~~

**Kết quả mong đợi:** **6 customers**, **12 orders**, trong đó **8 orders thuộc t001**, **4 orders thuộc t002**. Dữ liệu có ID cố định. Sau khi thực hành thay đổi document, chạy lại script seed để khôi phục trạng thái.

**Lưu ý:** script xóa rồi insert lại theo nhãn dataset, nhưng không thuộc transaction; chỉ dùng trong môi trường lab riêng. Index unique trong lab được định nghĩa để kiểm tra sự duy nhất của **(dataset, tenantId, customerCode)** và sẽ ảnh hưởng tới mọi document tương ứng trong cùng collection.

### 3.3. Các kết quả tham chiếu

| Customer | Tenant | Tổng order đúng tenant | Order paid | Tổng paid |
| --- | --- | ---: | ---: | ---: |
| An / C001 | t001 | 3 | 2 | 250.00 |
| Bình / C002 | t001 | 4 | 2 | 350.00 |
| Chi / C003 | t001 | 0 | 0 | 0.00 |
| Dung / C001 | t002 | 3 | 2 | 325.00 |
| Em / C004 | t002 | 1 | 0 | 0.00 |
| Hà / C005 | t001 | 0 | 0 | 0.00 |

Order **ord-008** không nối được tới customer nào vì customerCode MISSING không tồn tại ở t001. Nó vẫn là document hợp lệ trong collection orders theo dữ liệu lab và có thể được phát hiện bằng một phép $lookup theo chiều orders → customers.

## 4. Equality join đơn giản: localField và foreignField

### 4.1. Phép nối cơ bản

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        localField: "customerCode",
        foreignField: "customerCode",
        as: "joinedOrders"
      }
    },
    {
      $project: {
        _id: 1,
        name: 1,
        customerCode: 1,
        joinedCount: { $size: "$joinedOrders" },
        orderIds: "$joinedOrders._id"
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Kết quả quan trọng:

| Customer t001 | joinedCount với **customerCode đơn lẻ** | Số đúng theo tenant |
| --- | ---: | ---: |
| An / C001 | **6** | **3** |
| Bình / C002 | 4 | 4 |
| Chi / C003 | 0 | 0 |
| Hà / C005 | 0 | 0 |

An nhận **6** order vì C001 xuất hiện ở cả t001 (ord-001, ord-002, ord-009) và t002 (ord-005, ord-007, ord-011). Đây là **lỗi join logic và có thể là lỗi bảo mật**: collection đầu vào được lọc tenant t001 không có nghĩa collection được lookup cũng tự giới hạn tenant t001.

### 4.2. Khi nào equality join đủ?

Dạng **localField/foreignField** phù hợp khi:

- Khóa dùng để nối đủ duy nhất hoặc đủ chính xác ở toàn tập dữ liệu cần xét.
- Không cần áp nhiều điều kiện kết hợp từ document ngoài.
- Tập document liên quan có kích thước hợp lý.
- Việc trả toàn bộ document đích là cần thiết và không gây kết quả quá lớn.

Ví dụ nếu orders lưu **customerId** chính là **_id toàn cục duy nhất** của customers, phép nối:

~~~javascript
{
  $lookup: {
    from: "lab_customers",
    localField: "customerId",
    foreignField: "_id",
    as: "customer"
  }
}
~~~

thường rõ nghĩa hơn nối bằng mã hiển thị có khả năng trùng giữa tenant. Trong lab, orders dùng customerCode để minh họa sự cần thiết của khóa nối ghép.

### 4.3. Field thiếu hoặc null trong equality join

Với dạng equality join, MongoDB có quy tắc coi **localField thiếu** như giá trị null khi so khớp, và **foreignField thiếu** cũng có thể được coi là null. Điều này có thể khiến document thiếu khóa nối liên kết với những document cũng thiếu khóa hoặc có null, dẫn đến kết quả bất ngờ.

Không nên dùng $lookup equality trên những trường có thể null/missing mà không phân tích dữ liệu. Nếu quan hệ chỉ hợp lệ khi mã tồn tại và đúng kiểu, thêm điều kiện lọc và validation thích hợp ở dữ liệu đầu vào và phía collection đích.

## 5. Correlated subquery: let, $$variable và $expr

### 5.1. Biến tương quan là gì?

Một **correlated subquery** sử dụng giá trị từ document bên ngoài để lọc dữ liệu của collection đích. Trong $lookup:

- **let** khai báo biến từ document đầu vào.
- **$$variableName** tham chiếu biến đó trong pipeline con.
- **$expr** cho phép $match so sánh các **aggregation expressions**, gồm field của order và biến tương quan.

Ví dụ chính xác cho hệ multi-tenant:

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: {
          code: "$customerCode",
          tenant: "$tenantId"
        },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              $expr: {
                $and: [
                  { $eq: ["$customerCode", "$$code"] },
                  { $eq: ["$tenantId", "$$tenant"] }
                ]
              }
            }
          },
          { $project: { _id: 1, status: 1, amount: 1 } }
        ],
        as: "orders"
      }
    },
    {
      $project: {
        _id: 1,
        name: 1,
        customerCode: 1,
        orderCount: { $size: "$orders" },
        orderIds: "$orders._id"
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

**Kết quả mong đợi:** An **3** order, Bình **4**, Chi **0**, Hà **0**. Khách ở t001 không nhận order của t002 dù customerCode trùng.

### 5.2. Cách đọc từng phần

~~~javascript
let: {
  code: "$customerCode",
  tenant: "$tenantId"
}
~~~

Ở đây **"$customerCode"** và **"$tenantId"** là field path trong customer hiện tại; **code** và **tenant** là tên biến cho pipeline con.

Bên trong pipeline:

~~~javascript
{
  $eq: ["$customerCode", "$$code"]
}
~~~

Vế trái **"$customerCode"** là field của **order**. Vế phải **"$$code"** là giá trị đến từ **customer đang xử lý**.

Tương tự:

~~~javascript
{
  $eq: ["$tenantId", "$$tenant"]
}
~~~

so sánh tenant của order với tenant của customer.

**Một dấu $** biểu diễn field path trong biểu thức; **hai dấu $$** biểu diễn biến của aggregation. Nhầm chúng sẽ làm truy vấn sai nghĩa hoặc lỗi cú pháp.

### 5.3. Vì sao phải dùng $expr trong $match?

Trong subpipeline, bộ lọc query thông thường:

~~~javascript
{ $match: { status: "paid" } }
~~~

có thể so sánh với hằng **"paid"** mà không cần $expr.

Nhưng nếu so sánh với biến outer:

~~~javascript
{
  $match: {
    $expr: {
      $eq: ["$customerCode", "$$code"]
    }
  }
}
~~~

cần $expr để đánh giá hai toán hạng như biểu thức. Viết **{customerCode: "$$code"}** trong query predicate thông thường không mang đúng nghĩa so sánh với biến như mong muốn.

Một nguyên tắc hữu ích: **điều kiện hằng dùng query predicate thông thường nếu có thể; điều kiện phụ thuộc let dùng $expr**. Cách này cũng có thể giúp bộ tối ưu áp index thuận lợi hơn đối với những phần của bộ lọc.

## 6. Kết hợp equality join với pipeline

### 6.1. Vì sao dùng cả localField/foreignField và pipeline?

Từ MongoDB 5.0, dạng **concise correlated subquery** cho phép dùng **localField/foreignField** cùng **pipeline** để biểu diễn phần equality join cơ bản rồi thêm các điều kiện khác.

Ví dụ:

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        localField: "customerCode",
        foreignField: "customerCode",
        let: { tenant: "$tenantId" },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              status: "paid",
              $expr: {
                $eq: ["$tenantId", "$$tenant"]
              }
            }
          },
          { $project: { _id: 1, amount: 1, createdAt: 1 } }
        ],
        as: "paidOrders"
      }
    },
    {
      $project: {
        _id: 1,
        name: 1,
        paidCount: { $size: "$paidOrders" },
        paidOrderIds: "$paidOrders._id"
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Kết quả t001:

| Customer | paidCount |
| --- | ---: |
| An | 2 |
| Bình | 2 |
| Chi | 0 |
| Hà | 0 |

Trong truy vấn này:

- localField/foreignField nối theo customerCode.
- Biến tenant ở **let** ngăn nối sai tenant.
- **status: "paid"** là filter hằng bên trong subpipeline.
- **$project** chỉ giữ field cần cho báo cáo.

**Lưu ý phiên bản:** Nếu cần tương thích một MongoDB phiên bản cũ không hỗ trợ cấu trúc dùng localField/foreignField cùng pipeline, dùng dạng **let + pipeline + $expr** đầy đủ ở mục 5. Trước khi dùng cú pháp mới trong ứng dụng, đối chiếu phiên bản server triển khai.

### 6.2. Khi nào dùng dạng nào?

| Tình huống | Lựa chọn hợp lý |
| --- | --- |
| Nối qua một khóa ổn định, không lọc gì thêm | localField/foreignField |
| Nối qua một khóa rồi thêm status, range, projection | Equality join + pipeline nếu server hỗ trợ |
| Nối theo nhiều field tương quan như tenant + mã | let + $expr; hoặc equality join + pipeline cho các điều kiện bổ sung |
| Cần tổng hợp trong collection đích | $lookup có pipeline chứa $group |
| Cần một vài document mới nhất | $lookup pipeline với $sort + $limit + $project |
| Cần phát hiện không có bản ghi liên quan | $lookup rồi $size/$match hoặc join theo chiều ngược |

**Không cần chọn cú pháp phức tạp nhất** khi một equality join theo _id đã đủ. Nhưng cũng không được dùng dạng quá đơn giản khi khóa nối không duy nhất hoặc có yêu cầu bảo mật/phân vùng.

## 7. Chỉ lấy đơn đã thanh toán và hai đơn mới nhất

Một màn hình khách hàng thường không cần tất cả order; nó chỉ cần **hai đơn mới nhất** và vài trường ngắn gọn. $lookup pipeline có thể lọc, sort, limit và project ngay trong collection đích.

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: {
          code: "$customerCode",
          tenant: "$tenantId"
        },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              status: "paid",
              $expr: {
                $and: [
                  { $eq: ["$customerCode", "$$code"] },
                  { $eq: ["$tenantId", "$$tenant"] }
                ]
              }
            }
          },
          { $sort: { createdAt: -1, _id: 1 } },
          { $limit: 2 },
          {
            $project: {
              _id: 1,
              amount: 1,
              createdAt: 1
            }
          }
        ],
        as: "recentPaidOrders"
      }
    },
    {
      $project: {
        _id: 1,
        name: 1,
        recentPaidOrders: 1
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Kết quả mong đợi:

- **An:** ord-009 (150.00) rồi ord-001 (100.00).
- **Bình:** ord-010 (150.00) rồi ord-003 (200.00).
- **Chi và Hà:** Array recentPaidOrders rỗng.

**$sort trước $limit** cần thiết để “hai đơn mới nhất” có nghĩa xác định. Ở đây createdAt giảm dần và _id tăng dần làm khóa phụ cho trường hợp nhiều order có cùng thời điểm; nếu chỉ limit mà không sort, không có cam kết hai order được chọn là mới nhất.

### 7.1. Phân biệt limit trong subpipeline và limit ngoài

Đặt:

~~~javascript
{ $limit: 2 }
~~~

**bên trong $lookup.pipeline** nghĩa là **tối đa hai order cho mỗi customer** khi subquery được thực hiện trong từng ngữ cảnh outer document.

Đặt:

~~~javascript
{ $limit: 2 }
~~~

**sau $lookup ở pipeline chính** nghĩa là chỉ trả tối đa hai **customer** (hoặc hai document hiện có ở pipeline chính), không giới hạn riêng số order trong mỗi Array.

Hai vị trí này tạo ngữ nghĩa và lượng công việc rất khác nhau.

### 7.2. Không giới hạn trước khi xác định tập đúng

Nếu subpipeline làm:

~~~javascript
{ $limit: 2 },
{ $match: { status: "paid" } }
~~~

thì bạn chỉ xét hai order đầu bất kỳ rồi mới lọc paid; có thể loại mất các order paid hợp lệ nằm sau chúng. Trình tự thông thường để lấy hai order paid mới nhất là:

~~~text
$match theo tenant, customer, status
    ->
$sort createdAt DESC
    ->
$limit 2
    ->
$project các field cần thiết
~~~

Trong thực tế, bộ tối ưu có thể sắp xếp lại một số phép biến đổi khi an toàn; nhưng người viết pipeline phải bảo đảm **ngữ nghĩa mong muốn** trước khi dựa vào tối ưu của server.

## 8. Tổng hợp trong pipeline con: không kéo cả mảng orders ra ngoài

### 8.1. Khi chỉ cần số lượng và tổng tiền

Nếu yêu cầu là “số đơn paid và tổng amount paid theo khách”, kéo toàn bộ order về rồi dùng $size/$sum trên Array sẽ tiêu tốn bộ nhớ và có thể tạo document lớn.

Ta có thể để **$group ngay bên trong $lookup.pipeline**:

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: {
          code: "$customerCode",
          tenant: "$tenantId"
        },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              status: "paid",
              $expr: {
                $and: [
                  { $eq: ["$customerCode", "$$code"] },
                  { $eq: ["$tenantId", "$$tenant"] }
                ]
              }
            }
          },
          {
            $group: {
              _id: null,
              paidCount: { $sum: 1 },
              paidTotal: { $sum: "$amount" },
              newestPaidAt: { $max: "$createdAt" }
            }
          },
          { $project: { _id: 0 } }
        ],
        as: "paidSummaryArray"
      }
    },
    {
      $set: {
        paidSummary: {
          $ifNull: [
            { $arrayElemAt: ["$paidSummaryArray", 0] },
            {
              paidCount: 0,
              paidTotal: NumberDecimal("0.00"),
              newestPaidAt: null
            }
          ]
        }
      }
    },
    {
      $project: {
        _id: 1,
        name: 1,
        paidSummary: 1
      }
    },
    { $sort: { _id: 1 } }
  ]).toArray();
~~~

Giải thích:

1. Mỗi customer kích hoạt việc tìm đúng các order paid trong cùng tenant.
2. **$group: {_id:null}** tạo tối đa **một document thống kê** cho mỗi customer.
3. **as** của $lookup **luôn là Array** nên paidSummaryArray hoặc chứa một object thống kê, hoặc là Array rỗng.
4. **$arrayElemAt(..., 0)** lấy phần tử đầu; nếu không có phần tử, **$ifNull** cung cấp đối tượng mặc định.
5. **$project** loại mảng trung gian, trả chỉ thống kê cần thiết.

Kết quả logic:

| Customer | paidCount | paidTotal | newestPaidAt |
| --- | ---: | ---: | --- |
| An | 2 | 250.00 | 2026-01-09 |
| Bình | 2 | 350.00 | 2026-01-10 |
| Chi | 0 | 0.00 | null |
| Hà | 0 | 0.00 | null |

Để bảng dễ đọc, ngày được hiển thị ở dạng YYYY-MM-DD; BSON Date thật vẫn có đầy đủ thời gian và múi giờ. Với ứng dụng thực, định nghĩa **doanh thu** phải rõ: paid có được tính, refunded có bị trừ, tiền tệ có được quy đổi hay không.

### 8.2. Vì sao $group không trả một hàng count=0 khi không có dữ liệu?

Khi pipeline con không có order phù hợp, **$group không có document đầu vào nên không tạo document kết quả**. Vì vậy paidSummaryArray là **[]**, không phải **[{paidCount:0}]**. Nếu ứng dụng muốn luôn có object thống kê, phải xử lý Array rỗng như ví dụ bằng $arrayElemAt + $ifNull hoặc một cấu trúc tương đương.

### 8.3. So sánh kéo dữ liệu ra ngoài với tổng hợp tại nguồn

| Cách làm | Lợi ích | Rủi ro |
| --- | --- | --- |
| Lookup toàn bộ orders, tính ở ứng dụng | Đơn giản để thử nghiệm, có đủ chi tiết | Dữ liệu truyền lớn; mảng kết quả có thể rất dài |
| Lookup với $project | Giảm kích thước mỗi order được trả | Vẫn có thể có hàng nghìn order trong Array |
| Lookup với $sort + $limit | Phù hợp màn hình chỉ cần vài record mới nhất | Không đủ để tính tổng của mọi order nếu chỉ giữ vài record |
| Lookup với $group | Trả số lượng/tổng/min/max nhỏ gọn | Có chi phí group; phải xử lý nhóm không có dữ liệu |
| Tạo read model/tổng hợp sẵn | Hiệu quả nếu dashboard truy cập rất thường xuyên | Phải đồng bộ khi order thay đổi; có độ trễ/nhất quán cần thiết kế |

Đừng lấy 2 order gần nhất rồi tính “tổng tiền mọi order”: **limit thay đổi tập dữ liệu được cộng**. Nếu giao diện cần cả danh sách 2 order và tổng mọi order, có thể dùng hai phép $lookup riêng có mục đích rõ, hoặc một pipeline con dùng **$facet** khi phù hợp.

## 9. Nhiều phép tính trong một subpipeline bằng $facet

Ví dụ mỗi customer cần **tổng paid** và **hai order paid mới nhất**:

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001",
        customerCode: "C001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: {
          code: "$customerCode",
          tenant: "$tenantId"
        },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              status: "paid",
              $expr: {
                $and: [
                  { $eq: ["$customerCode", "$$code"] },
                  { $eq: ["$tenantId", "$$tenant"] }
                ]
              }
            }
          },
          {
            $facet: {
              totals: [
                {
                  $group: {
                    _id: null,
                    count: { $sum: 1 },
                    amount: { $sum: "$amount" }
                  }
                },
                { $project: { _id: 0 } }
              ],
              latest: [
                { $sort: { createdAt: -1, _id: 1 } },
                { $limit: 2 },
                { $project: { _id: 1, amount: 1, createdAt: 1 } }
              ]
            }
          }
        ],
        as: "details"
      }
    },
    {
      $project: {
        _id: 0,
        name: 1,
        details: 1
      }
    }
  ]).toArray();
~~~

Với An, bên trong details có một document chứa:

~~~text
totals = [{count: 2, amount: Decimal128(250.00)}]
latest = [ord-009, ord-001] với các field được chọn
~~~

Lưu ý **$facet** xuất ra một document chứa các Array theo từng nhánh, nên $lookup vẫn đặt document đó trong Array **details**. Có thể thêm $set/$project để chuyển về object thuận tiện cho API.

Sử dụng $facet khi cần nhiều loại thống kê từ cùng tập order đã được lọc, nhưng phải nhớ giới hạn tài nguyên của aggregation và kích thước document kết quả. Không mặc định $facet nhanh hơn hai $lookup độc lập ở mọi phiên bản hay mọi workload; cần đo.

## 10. $unwind sau $lookup: từ mảng liên kết thành từng dòng

### 10.1. Mỗi cặp customer–order là một document đầu ra

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: { tenant: "$tenantId", code: "$customerCode" },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              $expr: {
                $and: [
                  { $eq: ["$tenantId", "$$tenant"] },
                  { $eq: ["$customerCode", "$$code"] }
                ]
              }
            }
          },
          { $project: { _id: 1, status: 1, amount: 1 } }
        ],
        as: "orders"
      }
    },
    { $unwind: "$orders" },
    {
      $project: {
        _id: 0,
        customer: "$name",
        orderId: "$orders._id",
        status: "$orders.status",
        amount: "$orders.amount"
      }
    },
    { $sort: { customer: 1, orderId: 1 } }
  ]).toArray();
~~~

Từ t001, có **7 order gắn với customer hiện có**: An 3 và Bình 4. Chi và Hà không có order nên bị loại khi $unwind mặc định. Order ord-008 có mã MISSING nên cũng không xuất hiện khi nối từ customers.

### 10.2. Giữ lại customer không có order

Đặt:

~~~javascript
{
  $unwind: {
    path: "$orders",
    preserveNullAndEmptyArrays: true
  }
}
~~~

Với tùy chọn này, customer có Array orders rỗng **vẫn được giữ** trong pipeline đầu ra. Field **orders** của các document đó có thể bị thiếu ở kết quả unwind; nên dùng **$ifNull** khi tạo projection hiển thị:

~~~javascript
{
  $project: {
    name: 1,
    orderId: {
      $ifNull: ["$orders._id", null]
    }
  }
}
~~~

Nếu thay đoạn $unwind mặc định trong ví dụ trước bằng preserveNullAndEmptyArrays, sẽ có **9 document kết quả**: 7 cặp customer–order và 2 customer không có order.

### 10.3. $unwind có thể nhân số dòng và làm tổng sai

Nếu một customer có 100 orders, sau $unwind nó có thể trở thành 100 document. Sau đó:

~~~javascript
{ $group: { _id: "$tenantId", count: { $sum: 1 } } }
~~~

đếm **số dòng sau unwind**, không còn là số customer. Muốn đếm customer độc lập, hãy group theo customer trước hoặc dùng **$addToSet** trên ID khách rồi tính số phần tử, cân nhắc kích thước tập và khả năng tối ưu.

Tương tự, nếu mỗi customer có trường **creditLimit**, sau unwind mà cộng creditLimit sẽ cộng lặp theo số order. Đây là lỗi thay đổi **độ hạt dữ liệu** (granularity) thường gặp khi join rồi group.

### 10.4. Lọc ngay trong subpipeline hay sau $unwind?

Ví dụ:

~~~text
Phương án A:
  $lookup tất cả orders -> $unwind -> $match status paid

Phương án B:
  $lookup chỉ orders paid -> $unwind
~~~

Hai cách có thể trả cùng các cặp có order paid nếu không giữ customer không có order, nhưng **chi phí và semantics khi giữ hàng rỗng có thể khác**. B thường giảm mảng trung gian và cho foreign index cơ hội lọc sớm.

Nếu cần hiển thị cả khách không có đơn paid, đặt điều kiện **status paid bên trong $lookup.pipeline**, sau đó dùng **preserveNullAndEmptyArrays:true**. Nếu lọc status paid **sau khi unwind** bằng $match, các customer không có paid order có thể biến mất.

## 11. Đảo chiều $lookup để tìm order mồ côi

Từ customers → orders, những order không có customer tham chiếu sẽ không xuất hiện. Muốn phát hiện document liên kết thiếu, bắt đầu từ **orders** rồi $lookup sang customers.

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_orders")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_customers",
        let: {
          tenant: "$tenantId",
          code: "$customerCode"
        },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              $expr: {
                $and: [
                  { $eq: ["$tenantId", "$$tenant"] },
                  { $eq: ["$customerCode", "$$code"] }
                ]
              }
            }
          },
          { $project: { _id: 1, name: 1 } }
        ],
        as: "matchingCustomers"
      }
    },
    {
      $match: {
        matchingCustomers: { $size: 0 }
      }
    },
    {
      $project: {
        _id: 1,
        tenantId: 1,
        customerCode: 1,
        amount: 1
      }
    }
  ]).toArray();
~~~

**Kết quả mong đợi:** chỉ **ord-008**, thuộc t001 và có customerCode **MISSING**.

Đây là một dạng **anti-join**: giữ những document bên trái không tìm thấy document tương ứng bên phải.

### 11.1. $lookup không tự kiểm tra foreign key

MongoDB không mặc nhiên từ chối insert order có customerCode không tồn tại, chỉ vì ứng dụng thường dùng $lookup để đọc thông tin khách. Nếu cần bảo đảm quan hệ, phải có quy trình ở tầng ứng dụng, transaction phù hợp hoặc mô hình dữ liệu khác.

Tìm thấy order mồ côi không có nghĩa nó nên bị xóa: có thể customer đã được ẩn danh, chuyển hệ thống hoặc tham chiếu bị sai. Nên điều tra nguyên nhân và chính sách giữ dữ liệu trước khi sửa.

## 12. Phạm vi biến trong pipeline con và những lỗi cú pháp

### 12.1. Biến chỉ có ý nghĩa trong ngữ cảnh được khai báo

~~~javascript
{
  $lookup: {
    from: "lab_orders",
    let: { outerCode: "$customerCode" },
    pipeline: [
      {
        $match: {
          $expr: {
            $eq: ["$customerCode", "$$outerCode"]
          }
        }
      }
    ],
    as: "orders"
  }
}
~~~

**$$outerCode** là giá trị của customer từ pipeline ngoài, không phải field tên outerCode trên order.

Nếu không cần khai báo biến, hãy dùng localField/foreignField để join đơn giản hơn. Tránh tạo nhiều biến không dùng vì nó làm câu truy vấn khó đọc.

### 12.2. $expr không bắt buộc cho mọi stage trong pipeline con

Trong một subpipeline, bạn có thể dùng biến $$ ở nơi nhận aggregation expression. Ví dụ:

~~~javascript
{
  $project: {
    _id: 1,
    amount: 1,
    sourceCustomerCode: "$$outerCode"
  }
}
~~~

Ở **$project**, giá trị field mới được đánh giá bằng expression nên có thể dùng **$$outerCode** trực tiếp. Nhưng trong **$match** kiểu query predicate, dùng **$expr** để so sánh với biến.

### 12.3. Nhiều mức $lookup lồng nhau

Một subpipeline có thể chứa những stage khác được hỗ trợ, kể cả một số phép $lookup lồng nhau theo khả năng của server. Tuy vậy, mỗi mức lồng có thể tăng số lần tìm kiếm và độ khó của query plan. Khi dữ liệu có ba hoặc bốn quan hệ cần đọc liên tiếp, cân nhắc:

- Đổi chiều truy vấn để bắt đầu từ tập nhỏ và chọn lọc.
- Dùng projection để giảm dữ liệu trung gian.
- Nhúng dữ liệu ổn định hoặc denormalize một số trường thường đọc.
- Tạo read model/tổng hợp riêng cho trang quan trọng.
- Kiểm tra semantics biến ngoài/bên trong và giới hạn phiên bản trước khi dùng.

Không nên tái tạo một cây JOIN nhiều tầng chỉ vì mọi thành phần đều có thể được nối bằng $lookup.

## 13. Index và hiệu năng của $lookup

### 13.1. Index trên foreign collection quan trọng

Một phép $lookup equality:

~~~javascript
{
  $lookup: {
    from: "lab_orders",
    localField: "customerCode",
    foreignField: "customerCode",
    as: "orders"
  }
}
~~~

có thể cần tìm order theo customerCode cho **mỗi customer đầu vào**. Index trên **foreignField** thường giúp tránh quét toàn bộ collection orders cho mỗi lần tìm. Lab có **ix_lab_order_code_only** để minh họa trường hợp này.

Với correlated subquery đúng tenant:

~~~javascript
{
  $match: {
    dataset: "lookup-join-v1",
    status: "paid",
    $expr: {
      $and: [
        { $eq: ["$tenantId", "$$tenant"] },
        { $eq: ["$customerCode", "$$code"] }
      ]
    }
  }
}
~~~

compound index ứng viên trên orders là:

~~~javascript
{
  dataset: 1,
  tenantId: 1,
  customerCode: 1,
  status: 1,
  createdAt: -1,
  _id: 1
}
~~~

Thứ tự này đặt những điều kiện equality thường dùng trước, rồi đến createdAt phục vụ lọc/sort theo thời gian. Tuy nhiên, **không thể khẳng định mọi phép so sánh $expr đều luôn dùng index**. Phải kiểm chứng trên phiên bản và dữ liệu thực.

### 13.2. Khi nào $expr có thể dùng index?

Trong pipeline của $lookup, các toán tử **$eq, $lt, $lte, $gt, $gte** trong **$expr** có thể tận dụng index trên collection đích trong những trường hợp được hỗ trợ, đặc biệt khi phép so sánh là **field với giá trị hằng trong ngữ cảnh subquery**.

Biến **$$code/$$tenant** được lấy từ document ngoài có thể được coi là giá trị ràng buộc cho lần thực hiện subquery, nhưng không nên suy luận rằng mọi dạng expression phức tạp đều sargable.

Những lưu ý về giới hạn:

- So sánh **hai field từ cùng document đích** thường không nhận được lợi ích index như so sánh field với hằng.
- Nếu biến **let** giải quyết thành giá trị rỗng hoặc missing, khả năng sử dụng index có thể bị hạn chế.
- Với các so sánh $expr được nêu trong tài liệu $lookup, **multikey index** không được dùng cho những phép so sánh này theo cùng cách B-tree index scalar thông thường.
- Một số điều kiện còn có hạn chế với **partial/sparse index**, phiên bản server và hình dạng pipeline.
- Thứ tự stage, filter, sort và distribution của dữ liệu ảnh hưởng kế hoạch thực tế.

Nếu customerCode chỉ là String scalar và không null, lập index foreign theo khóa phù hợp thường đơn giản hơn so với xây biểu thức chuyển đổi phức tạp trong $expr. Đừng đưa **$toString** lên đường dẫn khóa của foreign field một cách tùy tiện nếu điều đó làm mất khả năng dùng index.

### 13.3. $match trước $lookup giúp giảm số lượt join

So sánh hai pipeline:

~~~javascript
// A: join toàn bộ customers rồi mới lọc một tenant.
[
  { $lookup: { from: "lab_orders", localField: "customerCode",
               foreignField: "customerCode", as: "orders" } },
  { $match: { tenantId: "t001" } }
]

// B: lọc customers trước khi join.
[
  { $match: { tenantId: "t001" } },
  { $lookup: { from: "lab_orders", localField: "customerCode",
               foreignField: "customerCode", as: "orders" } }
]
~~~

Với workload lớn, mô hình B có thể giảm số document đầu vào đi đến $lookup. MongoDB có thể tối ưu và tái sắp xếp một số stage an toàn, nhưng **viết $match đầu vào rõ ràng trước $lookup** giúp người đọc thấy phạm vi và đảm bảo không dựa vào optimizer để “đoán” filter bảo mật.

**Tuy nhiên**, $match outer tenant **không thay thế** điều kiện tenant **bên trong join**. Tình huống C001 của hai tenant trong lab cho thấy vì sao cần cả hai.

### 13.4. Dùng projection/limit, nhưng hiểu cái giá của chúng

Một $lookup tìm hàng nghìn order và trả nguyên document có thể phát sinh:

- Nhiều lần đọc index key và document.
- Mảng kết quả lớn trong từng customer.
- Chi phí network/serialization lớn khi trả toàn bộ mảng cho API.
- Vượt giới hạn BSON document đầu ra nếu Array quá lớn.

Vì vậy:

- **$match** chính xác để bỏ order không cần.
- **$project** chỉ giữ những field sử dụng.
- **$sort + $limit** khi chỉ cần một vài order mới nhất.
- **$group** khi chỉ cần count/sum/avg/min/max.
- **Phân trang trực tiếp collection orders** khi người dùng cần xem lịch sử dài.

Không dùng $lookup để tải toàn bộ quan hệ một-nhiều chỉ vì ứng dụng cần một **paidCount**.

## 14. Đọc explain cho pipeline có $lookup

### 14.1. Ví dụ thực hành

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_customers")
  .explain("executionStats")
  .aggregate([
    {
      $match: {
        dataset: "lookup-join-v1",
        tenantId: "t001"
      }
    },
    {
      $lookup: {
        from: "lab_orders",
        let: { tenant: "$tenantId", code: "$customerCode" },
        pipeline: [
          {
            $match: {
              dataset: "lookup-join-v1",
              status: "paid",
              $expr: {
                $and: [
                  { $eq: ["$tenantId", "$$tenant"] },
                  { $eq: ["$customerCode", "$$code"] }
                ]
              }
            }
          },
          { $project: { _id: 1, amount: 1 } }
        ],
        as: "paidOrders"
      }
    },
    {
      $project: {
        name: 1,
        paidCount: { $size: "$paidOrders" }
      }
    }
  ]);
~~~

Các con số/stage xuất hiện có thể khác theo phiên bản MongoDB và query engine. Khi kết quả cung cấp thống kê cho $lookup, hãy quan sát:

| Chỉ số/khái niệm | Câu hỏi cần trả lời |
| --- | --- |
| **nReturned** | Có bao nhiêu outer document được trả sau các stage? |
| **totalDocsExamined** | Có đọc quá nhiều document ở nguồn hoặc đích? |
| **totalKeysExamined** | Có phải duyệt nhiều index key? |
| **indexesUsed** | Foreign collection đã dùng index nào, khi thông tin này xuất hiện? |
| **collectionScans** | Có phải quét collection bên trong lookup không? |
| **IXSCAN / COLLSCAN** | Nguồn dữ liệu đang được truy cập qua index hay quét? |
| **executionTimeMillisEstimate** | Ước lượng theo stage nếu explain có cung cấp |
| **FETCH, SORT** | Có phải đọc document/sort ngoài index? |

Đừng khẳng định một $lookup “đã được index hóa” chỉ vì outer collection có IXSCAN; **foreign collection** cũng phải được xem xét. Tương tự, index trên order không tự bảo đảm truy vấn tốt nếu outer pipeline đưa hàng triệu customers vào join.

### 14.2. MongoDB có thể tối ưu $lookup với $unwind

Trong một số trường hợp, optimizer có thể tối ưu chuỗi:

~~~javascript
{
  $lookup: {
    from: "lab_orders",
    localField: "customerCode",
    foreignField: "customerCode",
    as: "orders"
  }
},
{ $unwind: "$orders" },
{ $match: { "orders.status": "paid" } }
~~~

bằng cách kết hợp một số thao tác vào quá trình lookup để giảm dữ liệu trung gian. Chi tiết optimizer thay đổi theo phiên bản và điều kiện pipeline. **Không lấy tối ưu này làm lý do bỏ điều kiện tenant trong join**, và vẫn nên viết pipeline rõ ràng để đảm bảo semantics, nhất là khi dùng preserveNullAndEmptyArrays.

### 14.3. Chế độ SBE và những thay đổi phiên bản

Một số phiên bản MongoDB có thể chạy một số phép equality $lookup bằng **slot-based execution engine (SBE)** với stage/kế hoạch tương ứng, nhưng không phải mọi dạng pipeline subquery đều được hỗ trợ theo cùng cách. Khi truy vấn có subpipeline, sharding hoặc các đặc điểm khác, optimizer có thể chọn cơ chế khác.

Khi nâng cấp MongoDB, so sánh **query plan, latency thực tế và số key/doc được duyệt**, thay vì cố nhận diện hiệu quả từ một tên stage cố định.

## 15. Ranh giới, giới hạn và khác biệt với JOIN của SQL

### 15.1. $lookup luôn tạo Array

Ngay cả khi foreignField là unique và chỉ có một document khớp, **as** vẫn là Array chứa tối đa một object. Nếu ứng dụng cần object:

~~~javascript
{
  $set: {
    customer: { $arrayElemAt: ["$customerMatches", 0] }
  }
}
~~~

phải xử lý Array rỗng bằng $ifNull nếu cần một object/null rõ ràng. Không nên giả định rằng unique index sẽ khiến $lookup tự trả object.

### 15.2. $lookup không phải full outer join

$lookup giữ document của collection đầu vào và gắn thông tin khớp từ collection đích. Nó không tự trả những document **chỉ có ở collection đích** mà không có document bên ngoài tương ứng.

Để tìm order mồ côi, phải đảo chiều như mục 11. Nếu cần báo cáo dạng full outer join theo hai nguồn, cần thiết kế pipeline khác (ví dụ kết hợp thêm nhánh dữ liệu thích hợp); không coi một $lookup đơn là full outer join.

### 15.3. Hai collection phải ở phạm vi database phù hợp

Trong cú pháp $lookup thông thường, **from** là tên collection trong cùng database đang chạy aggregation. Không thể chỉ đặt chuỗi **"otherDatabase.collection"** vào from rồi coi đó là một phép join cross-database được hỗ trợ giống SQL.

Nếu dữ liệu ở database/cluster khác, hãy cân nhắc thay đổi mô hình truy cập, tích hợp ở tầng ứng dụng, sao chép read model hoặc giải pháp chuyên biệt thay vì giả định $lookup trực tiếp làm được mọi quan hệ.

### 15.4. Sharding và phiên bản MongoDB

Từ **MongoDB 5.1**, $lookup hỗ trợ collection **from** được sharding theo những điều kiện triển khai được tài liệu mô tả. Một $lookup qua shard có thể phải đọc dữ liệu trên nhiều shard nếu điều kiện không cho phép định tuyến hiệu quả. Khi thiết kế production cần kiểm tra:

- Phiên bản server và khả năng dùng $lookup với sharded foreign collection.
- Shard key và điều kiện định tuyến/độ chọn lọc.
- Dữ liệu cùng tenant có được phân bố thuận lợi hay không.
- Tải mạng giữa các shard, tài nguyên merger và latency.
- Giới hạn riêng khi dùng transaction và các pipeline phức tạp.

Không mặc định kết quả lab trên standalone/replica set tương đương hiệu năng của sharded cluster.

### 15.5. Không dùng $out hoặc $merge trong $lookup.pipeline

Pipeline con của $lookup **không được chứa $out hoặc $merge**. Một phép $lookup phục vụ **đọc và kết hợp dữ liệu**, không phải chỗ để ghi trực tiếp kết quả con sang collection khác.

Với một số phiên bản/tính năng, pipeline con có thể có **$search** hoặc **$searchMeta** ở vị trí đầu tiên theo điều kiện được hỗ trợ; đây là trường hợp đặc biệt và không thay đổi nguyên tắc không dùng $out/$merge trong $lookup.

Nếu cần tạo materialized view/read model, hãy thiết kế một aggregation/job tổng hợp ở cấp phù hợp và cân nhắc cách đồng bộ dữ liệu.

### 15.6. Giới hạn kích thước kết quả

MongoDB có giới hạn **16 MiB cho một BSON document**. $lookup gắn một Array lớn vào mỗi document đầu vào; nếu mảng kết quả quá lớn, document trung gian hoặc cuối pipeline có thể vượt giới hạn hoặc tốn nhiều bộ nhớ.

**allowDiskUse** trong aggregation giúp một số stage có thể spill ra đĩa theo điều kiện hỗ trợ, nhưng **không biến document BSON 30 MiB thành hợp lệ**. Đây là lý do nên group/project/limit từ subquery và phân trang khi quan hệ một-nhiều có số phần tử lớn.

## 16. Thiết kế theo hướng truy vấn thực tế

### 16.1. Khi nào nên nhúng thay vì $lookup?

Giả sử customer luôn hiển thị **tên người liên hệ** và **địa chỉ giao hàng mặc định**, hai thuộc tính thay đổi ít và thuộc cùng vòng đời với customer. Nhúng vào customer có thể giảm join khi đọc.

Ngược lại, orders thường:

- Có thể tăng không giới hạn theo thời gian.
- Có trạng thái độc lập, cập nhật nhiều.
- Cần tìm kiếm/sort/phân trang riêng.
- Có retention và audit khác customer.

Vì vậy, tách orders rồi dùng query riêng hoặc $lookup khi cần thống kê có thể phù hợp hơn. Không có quy tắc “luôn dùng $lookup” hoặc “luôn embed”; chọn theo **cardinality, access patterns, vòng đời dữ liệu và tần suất cập nhật**.

### 16.2. Nếu màn hình chỉ cần danh sách orders của một customer

Thay vì bắt đầu từ customers rồi $lookup để lấy hàng trăm orders, khi customer đã được xác thực:

~~~javascript
db.getSiblingDB("mongo_lookup_lab")
  .getCollection("lab_orders")
  .find({
    dataset: "lookup-join-v1",
    tenantId: "t001",
    customerCode: "C001"
  })
  .sort({ createdAt: -1, _id: 1 })
  .limit(10)
  .toArray();
~~~

Truy vấn trực tiếp trên orders thường đơn giản và dễ phân trang hơn khi cần một danh sách dài. Có thể đọc metadata customer bằng một query riêng theo _id/cặp khóa, hoặc snapshot tên khách phù hợp trong order nếu đó là yêu cầu audit.

### 16.3. Nếu dashboard cần số liệu cập nhật mỗi giây

Một dashboard hiển thị paidCount và paidTotal của hàng triệu customer mỗi lần tải có thể tạo rất nhiều subquery. Các phương án nên cân nhắc:

- Lọc/page customers trước khi lookup nếu chỉ hiển thị một trang, và yêu cầu xếp hạng không phụ thuộc dữ liệu join.
- Tổng hợp orders theo customer trong một pipeline **bắt đầu từ orders** rồi join metadata customer.
- Duy trì **summary collection** theo tenant/customer với cơ chế cập nhật đáng tin cậy.
- Tính trước theo batch nếu dữ liệu không cần thời gian thực.

Nếu màn hình xếp hạng theo **paidTotal**, không được limit customers trước khi tính paidTotal rồi nghĩ đó là top khách toàn hệ thống. Đúng thứ tự ngữ nghĩa là tính metric cần xếp hạng trên tập đầy đủ thích hợp, sau đó sort và limit.

## 17. Các lỗi phổ biến và cách xử lý

| Lỗi / hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Customer t001 có order của t002 | Join chỉ dùng customerCode, không ràng buộc tenant | Join theo cặp tenant/customerCode; xác thực tenant ở cả hai phía |
| $lookup trả Array rỗng | Không có document đích khớp hoặc sai kiểu khóa | Kiểm tra khóa, tenant, dữ liệu mồ côi và điều kiện lọc |
| $lookup trả mảng dù chỉ có một customer | Semantics của $lookup luôn tạo Array | Dùng $arrayElemAt + $ifNull hoặc $unwind phù hợp |
| Không đọc được biến outer trong $match | Dùng $code thay vì $$code, hoặc thiếu $expr | Khai báo let và so sánh trong $expr |
| Lấy sai hai đơn mới nhất | $limit trước $sort hoặc không có thứ tự | Đặt $match, $sort rồi $limit trong subpipeline |
| Tổng tiền chỉ gồm hai đơn mới nhất | $limit đã làm nhỏ tập trước $group | Group trên tập paid đầy đủ hoặc tách hai nhánh |
| Mọi customer không có order biến mất | $unwind mặc định loại Array rỗng | Dùng preserveNullAndEmptyArrays nếu cần giữ |
| Đếm customer bị nhân lên sau $unwind | Mỗi order tạo thêm một document đầu ra | Xác định granularity trước khi $group |
| $lookup quá chậm dù outer có index | Foreign collection thiếu index phù hợp | Đo kế hoạch và bổ sung index trên foreign keys/filter |
| $expr không dùng index như kỳ vọng | Biểu thức phức tạp, field-to-field, multikey hoặc biến null | Kiểm tra giới hạn $expr và explain; chuẩn hóa khóa |
| Tạo mảng orders vượt kích thước | Nối quan hệ một-nhiều không giới hạn | Lọc, group, project, limit hoặc phân trang orders trực tiếp |
| Lấy chỉ số paidTotal sai nghĩa | Cộng cả pending/refunded hoặc tiền nhiều loại | Định nghĩa metric nghiệp vụ trước khi join/group |
| Query nối String với ObjectId không khớp | BSON types của khóa khác nhau | Lưu khóa cùng kiểu, migration nếu cần |
| Dữ liệu missing/null nối bất ngờ | Equality join coi khóa missing giống null trong trường hợp tương ứng | Kiểm tra khóa hợp lệ trước join |
| Cố $lookup sang database khác bằng tên ghép | from thông thường không nhận namespace database khác | Thiết kế lại cách truy cập/tập hợp dữ liệu |
| Dùng $out/$merge trong subpipeline bị lỗi | Stage ghi không được dùng trong $lookup.pipeline | Di chuyển write pipeline ra tác vụ riêng |
| Index tốt trên lab nhưng chậm ở production | Cardinality, phân bố và workload khác | Đo explain, tải và index trên dữ liệu đại diện |

## 18. Bài tập thực hành

### Bài 1 — Nhận diện left outer join

Từ lab, dùng $lookup đơn giản nối customers với orders theo customerCode. Đếm số order của các customer t001. Vì sao **An** có **6 kết quả** thay vì **3**? Hai tenant có cùng customerCode ảnh hưởng thế nào đến dữ liệu và bảo mật?

### Bài 2 — Viết correlated subquery an toàn

Viết $lookup dùng **let** chứa tenantId và customerCode, kết hợp **$expr/$and/$eq** để chỉ lấy order cùng tenant và cùng customer. Đặt $project trong subpipeline để chỉ trả _id/status/amount. Kết quả số order đúng của An, Bình, Chi và Hà là bao nhiêu?

### Bài 3 — So sánh hai cú pháp

Viết lại bài 2 bằng dạng **localField/foreignField + let + pipeline**. Phân biệt phần equality join và điều kiện tenant trong pipeline. Nêu yêu cầu phiên bản MongoDB khi dùng concise correlated subquery.

### Bài 4 — Hai đơn paid gần nhất

Với mỗi customer của t001, lấy tối đa hai paid order mới nhất, sort theo createdAt giảm dần và có khóa phụ _id. Dự đoán ID của An và Bình. Vì sao limit trước match/sort làm kết quả sai?

### Bài 5 — Tổng hợp ngay trong subpipeline

Viết $lookup tính paidCount, paidTotal và newestPaidAt bằng $group, sau đó đưa Array kết quả về một object paidSummary. Xử lý customer không có đơn bằng paidCount=0, paidTotal=0.00 và newestPaidAt=null.

### Bài 6 — Kết hợp thống kê và danh sách

Dùng $facet bên trong $lookup để có:

1. Tổng số order paid và tổng amount paid.
2. Hai order paid gần nhất.

Vì sao $lookup.as và $facet tạo các lớp Array lồng nhau? Viết projection gọn để API sử dụng.

### Bài 7 — $unwind và cardinality

Thực hiện join đúng tenant trên t001 rồi $unwind. Đếm tổng document trước và sau unwind. Bật preserveNullAndEmptyArrays và nêu sự khác biệt. Khi nào document không có order nên được giữ lại?

### Bài 8 — Anti-join

Bắt đầu từ orders t001, $lookup sang customers theo tenant/customerCode, sau đó dùng $match trên Array rỗng để tìm order mồ côi. Vì sao kết quả là **ord-008**, và tại sao không nên tự xóa order đó ngay?

### Bài 9 — Đọc explain cho foreign collection

Thử query:

~~~javascript
{
  $lookup: {
    from: "lab_orders",
    let: { tenant: "$tenantId", code: "$customerCode" },
    pipeline: [
      {
        $match: {
          dataset: "lookup-join-v1",
          status: "paid",
          $expr: {
            $and: [
              { $eq: ["$tenantId", "$$tenant"] },
              { $eq: ["$customerCode", "$$code"] }
            ]
          }
        }
      }
    ],
    as: "paidOrders"
  }
}
~~~

Đặt stage này trong một pipeline hoàn chỉnh và dùng explain("executionStats"). Quan sát các trường về IXSCAN/COLLSCAN, indexesUsed (nếu có), totalKeysExamined, totalDocsExamined, nReturned. Giải thích vì sao chỉ thấy IXSCAN ở outer collection chưa chứng minh foreign collection có index phù hợp.

### Bài 10 — Quyết định giữa lookup và query trực tiếp

Một khách có 500.000 đơn, màn hình chỉ hiển thị 20 đơn mới nhất. Đề xuất cấu trúc truy vấn; giải thích vì sao không nên $lookup toàn bộ 500.000 đơn để lấy trang đầu. Nêu index và tiêu chí phân trang tương ứng.

### Bài 11 — Thiết kế top customers

Màn hình cần **top 10 customer có paidTotal cao nhất** trong tenant t001. Vì sao không thể limit 10 customers trước rồi mới tính paidTotal để bảo đảm đúng top 10? Đề xuất pipeline bắt đầu từ orders, group theo tenant/customerCode, sort paidTotal và join customer metadata ở giai đoạn thích hợp.

### Bài 12 — Thiết kế quyền truy cập

Một API nhận tenantId từ request và thực hiện lookup dựa vào customerCode. Hãy nêu cách ràng buộc tenant từ context đã xác thực, không tin trực tiếp giá trị tenantId do client tự gửi, và cách bảo đảm foreign pipeline cũng giới hạn đúng tenant.

### Bài 13 — Ngăn dữ liệu khổng lồ

Giả sử lookup một customer có 300.000 orders rồi trả nguyên Array trong response. Hãy phân tích rủi ro về 16 MiB BSON document, RAM, mạng và latency. Viết một thiết kế thay thế gồm summary nhỏ gọn và endpoint phân trang chi tiết.

### Bài 14 — Kiểu khóa không đồng nhất

Collection A lưu customerId dạng ObjectId, collection B lưu customerId dạng String. Dự đoán điều gì xảy ra với equality $lookup. Nêu hướng sửa ở schema/migration và những nguy cơ khi chèn $toString/$toObjectId vào điều kiện join thay vì chuẩn hóa dữ liệu.

## 19. Tài liệu tham khảo MongoDB

- MongoDB Manual — [$lookup Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/).
- MongoDB Manual — [$expr Aggregation Expression](https://www.mongodb.com/docs/manual/reference/operator/query/expr/).
- MongoDB Manual — [$match Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/).
- MongoDB Manual — [$project Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/).
- MongoDB Manual — [$group Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/group/).
- MongoDB Manual — [$unwind Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/unwind/).
- MongoDB Manual — [$facet Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/facet/).
- MongoDB Manual — [Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/).
- MongoDB Manual — [Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/).

**Điều cần nhớ:** **$lookup** gắn kết quả từ collection khác thành **Array** và mặc định giữ document đầu vào không có bản ghi khớp. Dạng **localField/foreignField** phù hợp cho equality join đơn giản; **let + pipeline + $expr** cho phép viết correlated subquery theo nhiều điều kiện, đặc biệt quan trọng khi khóa chỉ duy nhất trong một tenant. Hãy **lọc đúng tenant ở cả hai phía, chỉ lấy field/record cần thiết, group khi chỉ cần số liệu và kiểm tra index trên foreign collection**. Mỗi $lookup nên phục vụ một nhu cầu đọc rõ ràng, không trở thành cách kéo vô hạn dữ liệu quan hệ vào một document kết quả.
