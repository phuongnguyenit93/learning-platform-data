# reduce() trong Cypher: tích lũy giá trị từ danh sách

## Mục tiêu bài học

Trong Neo4j, dữ liệu được tổ chức theo mô hình **property graph**, gồm node, relationship và property. Truy vấn Cypher thường trả về nhiều hàng hoặc tạo ra các **danh sách** từ dữ liệu liên kết: danh sách sản phẩm của đơn hàng, các node trên một đường đi, các relationship thuộc một hành trình hoặc các bản ghi được ứng dụng Java truyền vào.

Ở chương **Danh sách và luồng dữ liệu** của module `DATABASE_ENGINE_GRAPH_NEO4J`, hàm `reduce()` giúp **duyệt lần lượt các phần tử của một danh sách và cập nhật một giá trị tích lũy**. Giá trị đó có thể là số, chuỗi, list hoặc map. Đây là kỹ thuật hữu ích để tính tổng tiền, tổng quãng đường, trạng thái gộp hoặc xây dựng một kết quả phức hợp từ các phần tử liên kết.

Sau bài này, bạn có thể:

- Đọc và viết biểu thức `reduce(acc = initial, item IN items | expression)`.
- Giải thích vai trò của **giá trị khởi tạo**, **biến tích lũy** và **biến phần tử** ở từng bước.
- Dùng `reduce()` để cộng, nhân, ghép chuỗi và xây dựng map tích lũy.
- Xử lý danh sách rỗng, danh sách `null`, phần tử `null` và dữ liệu đầu vào thiếu thuộc tính.
- Kết hợp `reduce()` với `collect()`, `WITH`, list comprehension, `nodes(path)` và `relationships(path)`.
- Phân biệt tích lũy **phần tử của một list** với các hàm tổng hợp **trên nhiều hàng Cypher** như `sum()` và `count()`.

## 1. reduce() là gì?

Hình dung một giỏ hàng có ba đơn giá đã tính thành tiền từng dòng: `[200000, 50000, 150000]`. Để tính tổng, ứng dụng có thể bắt đầu từ 0 rồi lần lượt cộng từng số:

~~~text
Giá trị ban đầu:                  0
Gặp phần tử 200000:       0 + 200000 = 200000
Gặp phần tử  50000:  200000 + 50000 = 250000
Gặp phần tử 150000:  250000 + 150000 = 400000
Kết quả cuối:                 400000
~~~

Biểu thức Cypher tương ứng:

~~~cypher
RETURN reduce(total = 0, amount IN [200000, 50000, 150000] |
              total + amount) AS orderTotal;
~~~

Kết quả: **một hàng**, cột `orderTotal = 400000`.

Điểm quan trọng là `reduce()` hoạt động trên **một danh sách đã có**, trả về **một giá trị kết quả**. Nó không tự biến mỗi phần tử thành hàng như `UNWIND` và cũng không tự cập nhật node hoặc relationship trong cơ sở dữ liệu.

## 2. Cú pháp và mô hình tích lũy

Cú pháp:

~~~cypher
reduce(accumulator = initialValue,
       element IN listExpression |
       updateExpression)
~~~

| Thành phần | Vai trò |
| --- | --- |
| `accumulator` | Biến chứa kết quả tích lũy của những phần tử đã xử lý |
| `initialValue` | Giá trị ban đầu, dùng trước khi đọc phần tử đầu tiên |
| `element` | Biến đại diện cho phần tử đang được xét |
| `listExpression` | Biểu thức trả về một list |
| `updateExpression` | Công thức tạo giá trị tích lũy mới từ giá trị cũ và phần tử hiện tại |

Ví dụ đơn giản nhất:

~~~cypher
WITH [2, 4, 6] AS numbers
RETURN reduce(acc = 0, n IN numbers | acc + n) AS total;
~~~

Diễn tiến:

| Bước | `n` | `acc` trước bước | `acc` sau bước |
| --- | ---: | ---: | ---: |
| Khởi tạo | — | — | 0 |
| 1 | 2 | 0 | 2 |
| 2 | 4 | 2 | 6 |
| 3 | 6 | 6 | 12 |

Kết quả cuối là `12`. Ở mỗi bước, biểu thức bên phải dấu `|` được đánh giá để tạo giá trị tích lũy **mới**. Biến `acc` và `n` chỉ là tên trong phạm vi biểu thức `reduce()`; bạn có thể đặt tên dễ hiểu hơn theo nghiệp vụ.

### Không phải vòng lặp ghi dữ liệu

`reduce()` là **biểu thức**, tương tự cách dùng `size()` hoặc `coalesce()`. Nó có thể xuất hiện trong `WITH`, `RETURN` hoặc nằm bên trong biểu thức lớn hơn:

~~~cypher
WITH [100, 200, 300] AS values
WITH values, reduce(sum = 0, x IN values | sum + x) AS total
RETURN total, size(values) AS numberOfValues;
~~~

Mệnh đề `WITH` chuyển tiếp giá trị `total` sang bước sau. Truy vấn trả `total = 600` và `numberOfValues = 3`; không có thao tác `SET`, `CREATE` hay `MERGE` được thực hiện.

## 3. Giá trị khởi tạo quyết định ý nghĩa phép tích lũy

### Tính tổng: khởi tạo bằng 0

~~~cypher
WITH [5, 8, 12] AS quantities
RETURN reduce(total = 0, q IN quantities | total + q) AS quantityTotal;
~~~

Kết quả là `25`.

### Tính tích: khởi tạo bằng 1

~~~cypher
WITH [2, 3, 4] AS factors
RETURN reduce(product = 1, x IN factors | product * x) AS result;
~~~

Kết quả là `24`. Nếu khởi tạo tích bằng 0, mọi bước nhân tiếp theo vẫn bằng 0; vì thế giá trị ban đầu phải phù hợp với phép toán.

### Ghép chuỗi: khởi tạo bằng chuỗi rỗng

~~~cypher
WITH ['Neo', '4', 'j'] AS parts
RETURN reduce(textValue = '', part IN parts |
              textValue + part) AS productName;
~~~

Kết quả là `'Neo4j'`. Phép ghép chuỗi **phụ thuộc thứ tự** các phần tử: đổi vị trí các chuỗi có thể tạo tên khác.

### Kết quả không nhất thiết là một số

~~~cypher
WITH [2, 4, 6] AS numbers
RETURN reduce(
  state = {count: 0, total: 0},
  n IN numbers |
  {
    count: state.count + 1,
    total: state.total + n
  }
) AS summary;
~~~

Map đầu ra:

~~~text
summary = {
  count: 3,
  total: 12
}
~~~

Mỗi bước tạo **map mới** từ map tích lũy cũ. Đây là cách tính nhiều chỉ số trong một lượt duyệt list; biểu thức không sửa map gốc và không ghi thay đổi lên graph.

## 4. Danh sách rỗng, null và dữ liệu thiếu

Các trường hợp này rất quan trọng khi danh sách được tạo từ `OPTIONAL MATCH` hoặc được Java Driver truyền qua query parameters.

### List rỗng trả giá trị khởi tạo

~~~cypher
WITH [] AS amounts
RETURN
  reduce(total = 0, x IN amounts | total + x) AS sumOfEmpty,
  reduce(product = 1, x IN amounts | product * x) AS productOfEmpty;
~~~

Kết quả là `sumOfEmpty = 0` và `productOfEmpty = 1`. Không có phần tử để duyệt, nên `reduce()` giữ nguyên `initialValue`.

### List đầu vào bằng null

Nếu **cả danh sách** là `null`, kết quả `reduce()` là `null`:

~~~cypher
WITH null AS amounts
RETURN
  reduce(total = 0, x IN amounts | total + x) AS directResult,
  reduce(total = 0, x IN coalesce(amounts, []) | total + x)
    AS defaultToEmpty;
~~~

`directResult = null`, còn `defaultToEmpty = 0`. Dùng `coalesce(amounts, [])` khi nghiệp vụ hiểu “chưa có list” tương đương “list không có phần tử”; hai trường hợp có thể mang ý nghĩa khác nhau trong một API.

### Một phần tử null có thể làm hỏng phép tích lũy

~~~cypher
WITH [10, null, 20] AS amounts
RETURN reduce(total = 0, x IN amounts | total + x) AS result;
~~~

Ở bước gặp `null`, `total + null` bằng `null`. Các bước cộng tiếp theo vẫn trả `null`, nên kết quả cuối không còn là `30`.

Nếu quy tắc nghiệp vụ là **bỏ qua phần tử thiếu**, có thể dùng `CASE`:

~~~cypher
WITH [10, null, 20] AS amounts
RETURN reduce(
  total = 0,
  x IN amounts |
  CASE
    WHEN x IS NULL THEN total
    ELSE total + x
  END
) AS totalIgnoringNull;
~~~

Kết quả: `totalIgnoringNull = 30`. Cách khác là lọc list trước:

~~~cypher
WITH [10, null, 20] AS amounts
WITH [x IN amounts WHERE x IS NOT NULL] AS validAmounts
RETURN reduce(total = 0, x IN validAmounts | total + x) AS total;
~~~

Ví dụ cũng trả `30`. Tuy nhiên, **không nên tự ý coi dữ liệu bị thiếu là 0** trong những bài toán như tính cước, tồn kho hoặc thanh toán. Khi thiếu đơn giá là lỗi dữ liệu, ứng dụng cần xác thực và từ chối bản ghi thay vì âm thầm bỏ qua.

### Phân biệt kiểm tra rỗng và phần tử null

| List đầu vào | Biểu thức cộng trực tiếp với `initialValue = 0` | Ghi chú |
| --- | --- | --- |
| `[]` | `0` | Không duyệt phần tử nào |
| `[5, 10]` | `15` | Hai lần cộng |
| `[5, null, 10]` | `null` | Giá trị tích lũy trở thành `null` |
| `null` | `null` | Danh sách đầu vào không có giá trị |
| `coalesce(null, [])` | `0` | Chủ động dùng list rỗng thay thế |

## 5. Ví dụ thực tế: tổng giá trị đơn hàng

Một đơn hàng có nhiều dòng sản phẩm. Mỗi dòng lưu `sku`, `quantity` và `unitPrice` dưới dạng map. Dữ liệu thử:

~~~cypher
WITH {
  id: 'O01',
  items: [
    {sku: 'P01', quantity: 2, unitPrice: 120000},
    {sku: 'P02', quantity: 1, unitPrice: 90000},
    {sku: 'P03', quantity: 3, unitPrice: 30000}
  ]
} AS orderData
RETURN
  orderData.id AS orderId,
  reduce(
    total = 0,
    item IN orderData.items |
    total + item.quantity * item.unitPrice
  ) AS orderTotal;
~~~

Kết quả `orderId = 'O01'` và `orderTotal = 420000`:

~~~text
P01: 2 * 120000 = 240000
P02: 1 *  90000 =  90000
P03: 3 *  30000 =  90000
Tổng:               420000
~~~

Ví dụ chạy độc lập, không cần tạo node `Order` hay `Product`. Điều này giúp kiểm tra logic tính tổng trước khi đưa biểu thức vào truy vấn đồ thị.

### Tính nhiều chỉ số cùng lúc

Nếu ngoài số tiền còn cần tổng số lượng và số dòng:

~~~cypher
WITH [
  {sku: 'P01', quantity: 2, unitPrice: 120000},
  {sku: 'P02', quantity: 1, unitPrice: 90000},
  {sku: 'P03', quantity: 3, unitPrice: 30000}
] AS items
RETURN reduce(
  s = {lineCount: 0, quantity: 0, amount: 0},
  item IN items |
  {
    lineCount: s.lineCount + 1,
    quantity: s.quantity + item.quantity,
    amount: s.amount + item.quantity * item.unitPrice
  }
) AS orderSummary;
~~~

Kết quả:

~~~text
{
  lineCount: 3,
  quantity: 6,
  amount: 420000
}
~~~

`lineCount` đếm số phần tử của list, **không đếm số SKU duy nhất**. Nếu một SKU xuất hiện hai dòng, nó vẫn đóng góp hai lượt. Điều này có thể đúng với dữ liệu chứa nhiều lô hàng hoặc mức giá khác nhau.

### Chuẩn hóa list tùy chọn

Khi ứng dụng có thể không gửi `items`, có thể viết:

~~~cypher
WITH {id: 'O02', items: null} AS orderData
WITH orderData.id AS orderId,
     coalesce(orderData.items, []) AS items
RETURN orderId,
       reduce(total = 0, item IN items |
              total + item.quantity * item.unitPrice) AS orderTotal;
~~~

Kết quả `O02` có `orderTotal = 0` theo quy ước của ví dụ. Trong hệ thống thực, cần phân biệt **đơn hợp lệ nhưng không có dòng hàng** với **đơn thiếu dữ liệu do lỗi đồng bộ** trước khi mặc định tổng bằng 0.

## 6. reduce() kết hợp WITH, collect() và các hàng truy vấn

Cypher xử lý một luồng hàng qua các mệnh đề như `MATCH`, `WITH` và `RETURN`. `collect()` là hàm **tổng hợp các hàng thành list**, còn `reduce()` xử lý **các phần tử đã nằm trong list đó**.

~~~text
Hàng Cypher:       O01, 240000       O01, 90000       O01, 90000
                         |                |                |
                         +----- collect(amount) ------------+
                                           |
                         O01, [240000, 90000, 90000]
                                           |
                         reduce(total = 0, amount IN list ...)
                                           |
                                O01, 420000
~~~

Ví dụ gom theo đơn hàng từ danh sách dòng dữ liệu:

~~~cypher
UNWIND [
  {orderId: 'O01', quantity: 2, unitPrice: 120000},
  {orderId: 'O01', quantity: 1, unitPrice: 90000},
  {orderId: 'O02', quantity: 3, unitPrice: 30000}
] AS line
WITH line.orderId AS orderId,
     collect(line) AS lines
RETURN
  orderId,
  reduce(total = 0, item IN lines |
         total + item.quantity * item.unitPrice) AS amount
ORDER BY orderId;
~~~

| orderId | amount |
| --- | ---: |
| O01 | 330000 |
| O02 | 90000 |

`WITH line.orderId AS orderId, collect(line) AS lines` nhóm các hàng theo `orderId`. Sau đó `reduce()` tính tổng riêng cho list của từng nhóm. Đây là ví dụ có ý nghĩa khi ứng dụng thực sự cần giữ và xử lý danh sách `lines` ở bước giữa.

### Khi nào nên dùng sum() thay vì reduce()?

Nếu mục tiêu duy nhất là tính tổng ngay trên những hàng dòng sản phẩm, `sum()` gọn và thường hiệu quả hơn vì không cần tạo một list trung gian:

~~~cypher
UNWIND [
  {orderId: 'O01', quantity: 2, unitPrice: 120000},
  {orderId: 'O01', quantity: 1, unitPrice: 90000},
  {orderId: 'O02', quantity: 3, unitPrice: 30000}
] AS line
RETURN
  line.orderId AS orderId,
  sum(line.quantity * line.unitPrice) AS amount
ORDER BY orderId;
~~~

Kết quả cũng là `O01 = 330000` và `O02 = 90000`.

| Tiêu chí | `reduce()` | `sum()` |
| --- | --- | --- |
| Đầu vào tự nhiên | Một giá trị **list** | Nhiều **hàng Cypher** |
| Kết quả | Giá trị theo công thức cập nhật tùy ý | Tổng giá trị số, bỏ qua giá trị `null` |
| Trạng thái tích lũy | Tự định nghĩa, có thể là số, chuỗi, map, list | Do hàm tổng hợp quản lý |
| Thứ tự các phần tử | Có thể ảnh hưởng kết quả, ví dụ ghép chuỗi | Không có ý nghĩa nghiệp vụ cho phép cộng |
| Bài toán phù hợp | Tổng tùy biến, cập nhật nhiều trường, thao tác trên path/list | Cộng các giá trị số trực tiếp từ hàng |

**Chọn `sum()` khi chỉ cần cộng các hàng.** Chọn `reduce()` khi nguồn đầu vào **đã là list** hoặc phép tích lũy cần trạng thái và công thức linh hoạt hơn phép tổng hợp thông thường.

## 7. reduce() trên relationship của một đường đi

Trong graph Neo4j, `relationships(path)` trả về list relationship theo thứ tự chúng xuất hiện trên đường đi. Có thể dùng `reduce()` để cộng trọng số của từng cạnh.

Giả sử mô hình:

~~~text
(:Location {id: 'A'})
   -[:ROAD {distanceKm: 8.5}]->
(:Location {id: 'B'})
   -[:ROAD {distanceKm: 3.0}]->
(:Location {id: 'C'})
~~~

Tổng quãng đường của path `A → B → C` là `11.5 km`.

Truy vấn trên graph đã có:

~~~cypher
MATCH p = (origin:Location {id: $originId})
          -[:ROAD*1..4]->
          (destination:Location {id: $destinationId})
WITH p, [r IN relationships(p) | r.distanceKm] AS segments
WHERE all(km IN segments WHERE km IS NOT NULL)
WITH
  p,
  reduce(totalKm = 0.0, km IN segments |
         totalKm + km) AS distanceKm
RETURN
  [n IN nodes(p) | n.id] AS locationIds,
  size(relationships(p)) AS hopCount,
  distanceKm
ORDER BY distanceKm ASC, hopCount ASC
LIMIT 3;
~~~

Giải thích:

1. `MATCH p = ...` tìm các đường đi có từ một đến bốn relationship `ROAD` theo hướng được chỉ định.
2. `relationships(p)` tạo danh sách relationship trên mỗi đường đi; comprehension lấy danh sách độ dài `segments`.
3. `all(km IN segments WHERE km IS NOT NULL)` loại path thiếu dữ liệu quãng đường, tránh coi cạnh chưa có trọng số là 0 km.
4. `reduce(totalKm = 0.0, km IN segments | totalKm + km)` cộng lần lượt độ dài từng đoạn.
5. `ORDER BY ... LIMIT 3` chọn tối đa ba đường đi có tổng quãng đường nhỏ nhất **trong những path mà truy vấn đã tìm được**.

Truy vấn này chỉ minh họa tính trọng số **sau khi đã tìm path với giới hạn bốn cạnh**. Nó không tự bảo đảm tìm được đường ngắn nhất toàn đồ thị nếu đường tối ưu có hơn bốn cạnh; việc liệt kê mọi path có thể tốn nhiều tài nguyên. Với bài toán đường đi có trọng số trên graph lớn, cân nhắc thuật toán và công cụ đường đi thích hợp như Neo4j Graph Data Science sau khi xác định yêu cầu.

### reduce() trong công thức đường đi

Bạn cũng có thể trả về riêng tổng trọng số trong một projection:

~~~cypher
MATCH p = (a:Location {id: $originId})-[:ROAD*1..4]->
          (b:Location {id: $destinationId})
WITH p, relationships(p) AS roads
WHERE all(r IN roads WHERE r.distanceKm IS NOT NULL)
RETURN {
  route: [n IN nodes(p) | n.id],
  distanceKm: reduce(
    total = 0.0,
    road IN roads |
    total + road.distanceKm
  )
} AS routeSummary;
~~~

Map kết quả có hai trường `route` và `distanceKm`. Kết hợp như vậy hữu ích khi API Java chỉ cần một map có các chỉ số tổng hợp cho mỗi đường đi.

## 8. Tích lũy có thứ tự: chuỗi và trạng thái

Phần lớn các phép cộng số không phụ thuộc thứ tự, nhưng **ghép chuỗi** hoặc phép cập nhật trạng thái có thể phụ thuộc thứ tự.

~~~cypher
WITH ['A', 'B', 'C'] AS stops
RETURN reduce(label = '', stop IN stops |
              CASE
                WHEN label = '' THEN stop
                ELSE label + ' -> ' + stop
              END) AS routeLabel;
~~~

Kết quả: `'A -> B -> C'`. Nếu list đầu vào là `['C', 'A', 'B']`, nhãn cũng đổi theo.

### Khác nhau giữa thứ tự list và thứ tự hàng

Một list literal như `['A','B','C']` có thứ tự phần tử rõ ràng. Nhưng khi list được tạo bằng `collect()` từ nhiều hàng đồ thị, cần **sắp xếp hàng trước mệnh đề collect** nếu thứ tự quan trọng:

~~~cypher
MATCH (o:Order {id: $orderId})-[:HAS_EVENT]->(e:OrderEvent)
WITH e
ORDER BY e.occurredAt ASC, e.id ASC
WITH collect(e.type) AS eventTypes
RETURN reduce(
  summary = '',
  eventType IN eventTypes |
  CASE
    WHEN summary = '' THEN eventType
    ELSE summary + ' -> ' + eventType
  END
) AS eventHistory;
~~~

Ví dụ giả định graph có các node `OrderEvent` với `occurredAt`, `id`, `type`. Hai khóa sắp xếp giúp xác định thứ tự các sự kiện trước khi ghép thành chuỗi; nếu thời điểm giống nhau mà không có khóa phụ, thứ tự có thể không ổn định.

### Tích lũy một map trạng thái

Ví dụ tính số dư sau các thay đổi số tiền và giá trị số dư nhỏ nhất đã từng gặp:

~~~cypher
WITH [-100, 200, -50] AS changes
RETURN reduce(
  s = {balance: 0, minimumBalance: 0},
  delta IN changes |
  {
    balance: s.balance + delta,
    minimumBalance: CASE
      WHEN s.balance + delta < s.minimumBalance
        THEN s.balance + delta
      ELSE s.minimumBalance
    END
  }
) AS balanceSummary;
~~~

Diễn tiến: số dư `0 → -100 → 100 → 50`. Kết quả:

~~~text
{
  balance: 50,
  minimumBalance: -100
}
~~~

Điểm đáng chú ý là mỗi bước có thể phụ thuộc **trạng thái tích lũy của bước trước**. Vì vậy biểu thức này phù hợp hơn việc tính riêng `sum(changes)` khi cần theo dõi cả số dư tối thiểu trong suốt chuỗi giao dịch.

## 9. reduce() với list, list comprehension và hàm khác

### Tạo một list kết quả bằng accumulator

Có thể dùng một list làm giá trị tích lũy:

~~~cypher
WITH [1, 2, 3] AS numbers
RETURN reduce(
  squares = [],
  n IN numbers |
  squares + [n * n]
) AS squaredValues;
~~~

Kết quả `[1, 4, 9]`. Tuy nhiên, khi chỉ biến đổi từng phần tử độc lập, **list comprehension** diễn đạt ý định đơn giản hơn:

~~~cypher
WITH [1, 2, 3] AS numbers
RETURN [n IN numbers | n * n] AS squaredValues;
~~~

Hai cách cùng kết quả. Cách `reduce()` dùng `squares + [n * n]` có thể tạo nhiều list trung gian khi danh sách lớn; tránh dùng chỉ để sao chép hoặc ánh xạ dữ liệu nếu comprehension đã đủ.

### Kết hợp lọc rồi tích lũy

Cho danh sách đơn hàng, chỉ tính tiền của đơn đã thanh toán:

~~~cypher
WITH [
  {id: 'O01', status: 'PAID', amount: 200000},
  {id: 'O02', status: 'PENDING', amount: 50000},
  {id: 'O03', status: 'PAID', amount: 80000}
] AS orders
WITH [o IN orders WHERE o.status = 'PAID'] AS paidOrders
RETURN reduce(
  total = 0,
  o IN paidOrders |
  total + o.amount
) AS paidTotal;
~~~

Kết quả: `paidTotal = 280000`.

Có thể tích hợp điều kiện vào `reduce()`:

~~~cypher
WITH [
  {status: 'PAID', amount: 200000},
  {status: 'PENDING', amount: 50000},
  {status: 'PAID', amount: 80000}
] AS orders
RETURN reduce(
  total = 0,
  o IN orders |
  CASE
    WHEN o.status = 'PAID' THEN total + o.amount
    ELSE total
  END
) AS paidTotal;
~~~

Cách thứ hai không cần tạo list lọc trung gian, nhưng biểu thức tích lũy trở nên dài hơn. Hãy chọn cách rõ ràng với yêu cầu nghiệp vụ, đồng thời kiểm tra `null` và kiểu dữ liệu của `amount` trước khi tính.

## 10. Truyền dữ liệu từ Java Driver và Spring Data Neo4j

Trong ứng dụng Java, có thể gửi một danh sách map làm tham số `$items` rồi tính tổng bằng Cypher. Điều này phù hợp khi muốn trả kết quả thống nhất với truy vấn đồ thị trong cùng một lớp truy cập dữ liệu.

Truy vấn tham số:

~~~cypher
WITH coalesce($items, []) AS items
RETURN reduce(
  total = 0,
  item IN items |
  total + item.quantity * item.unitPrice
) AS amount;
~~~

Ví dụ Java Driver (giả định `driver` đã được khởi tạo và quản lý vòng đời):

~~~java
List<Map<String, Object>> items = List.of(
    Map.of("quantity", 2, "unitPrice", 120_000L),
    Map.of("quantity", 1, "unitPrice", 90_000L)
);

String query = """
    WITH coalesce($items, []) AS items
    RETURN reduce(
      total = 0,
      item IN items |
      total + item.quantity * item.unitPrice
    ) AS amount
    """;

try (Session session = driver.session()) {
    long amount = session.executeRead(tx ->
        tx.run(query, Values.parameters("items", items))
          .single()
          .get("amount")
          .asLong()
    );

    // amount = 330000
}
~~~

Các import thông dụng gồm `java.util.List`, `java.util.Map` và các kiểu `Session`/`Values` từ `org.neo4j.driver`. Đoạn mã chỉ minh họa việc đọc kết quả dạng số nguyên. Ứng dụng cần xác thực phần tử của list là map đúng cấu trúc, `quantity` không âm, `unitPrice` có kiểu số phù hợp và xử lý lỗi truy vấn/transaction theo yêu cầu.

Với **Spring Data Neo4j**, có thể đặt biểu thức tương tự trong một câu truy vấn `@Query` tùy chỉnh; kiểu trả về và cách bind tham số phụ thuộc repository và cấu hình mapping. `reduce()` không tự biến thành cơ chế cập nhật entity, cũng không thay thế các validation của tầng ứng dụng.

### Nên tính ở Cypher hay Java?

Tùy mục đích:

- Nếu dữ liệu **đã ở trong Neo4j**, tính kết quả ngay trong Cypher có thể giảm lượng dữ liệu phải gửi tới ứng dụng.
- Nếu dữ liệu **chỉ nằm trong Java** và không cần truy vấn graph, tính trực tiếp trong Java có thể đơn giản hơn việc gửi dữ liệu sang database để cộng.
- Với tiền tệ cần độ chính xác và quy tắc làm tròn, hãy dùng mô hình số tiền thích hợp (chẳng hạn số nguyên ở đơn vị tiền nhỏ nhất) và kiểm soát giới hạn số; không mặc định kiểu số thực là phù hợp cho mọi nghiệp vụ.

## 11. Lỗi thường gặp, hiệu năng và giới hạn

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Tổng sai khi list rỗng | Giá trị khởi tạo không phù hợp | Cộng bắt đầu từ 0, nhân bắt đầu từ 1 |
| Kết quả bất ngờ là `null` | List bằng `null` hoặc phần tử `null` lan truyền qua phép toán | Kiểm tra dữ liệu, dùng `coalesce()` hoặc `CASE` theo quy tắc nghiệp vụ |
| `reduce()` báo lỗi kiểu | Phần tử có kiểu không phù hợp với phép cộng/nhân | Xác thực map và kiểu số trước truy vấn |
| Tổng tiền bị nhân đôi | List chứa dòng trùng do `MATCH` mở rộng nhiều quan hệ | Kiểm tra mỗi hàng đại diện điều gì; nhóm và loại trùng nếu nghiệp vụ cho phép |
| Chuỗi tích lũy sai thứ tự | List tạo bởi `collect()` thiếu sắp xếp | `ORDER BY` trước khi `collect()` |
| Query dùng nhiều bộ nhớ | `collect()` tạo list lớn chỉ để `reduce()` | Cân nhắc `sum()`/hàm tổng hợp trực tiếp trên hàng |
| Tích lũy list chậm | Nối list mới ở mọi lần lặp | Dùng list comprehension cho phép lọc/ánh xạ đơn giản |
| Tưởng `reduce()` ghi lên graph | Biểu thức chỉ tính giá trị | Dùng mệnh đề ghi `SET`/`MERGE`/`CREATE` riêng nếu thực sự cần thay đổi graph |
| Đường đi có trọng số bị đánh giá sai | Thuộc tính trọng số thiếu hoặc liệt kê path chưa đủ | Xác thực trọng số và chọn giải pháp tìm đường phù hợp |

Một số nguyên tắc để truy vấn ổn định:

1. **Chọn accumulator tối thiểu:** chỉ giữ những trường thật sự cần trong quá trình tính toán.
2. **Xác định đơn vị của số:** số lượng, tiền, quãng đường và thời gian không thể cộng tùy tiện nếu đơn vị khác nhau.
3. **Kiểm soát `null` ngay từ đầu:** đặc biệt với list được gửi từ API hoặc từ quan hệ tùy chọn.
4. **Không gom list khi không cần:** `sum()`, `avg()` hoặc `count()` thường diễn đạt tốt hơn phép tổng hợp cơ bản trên nhiều hàng.
5. **Kiểm tra kế hoạch truy vấn:** dùng `EXPLAIN` để xem kế hoạch; `PROFILE` trên dữ liệu thử để xem số hàng và chi phí, nhất là trước `collect()` hoặc phép mở rộng path.

`reduce()` duyệt toàn bộ những phần tử của list được cung cấp; không có cơ chế `break` để tự dừng sớm giống một vòng lặp Java. Với bài toán tìm kiếm điều kiện tồn tại, `any()`, `all()` hoặc các biểu thức điều kiện khác có thể phù hợp hơn việc dùng accumulator thủ công.

## 12. Bài thực hành

### Bài 1 — Tính giai thừa bằng range() và reduce()

Cho `n = 5`, hãy tính `5! = 1 × 2 × 3 × 4 × 5`:

~~~cypher
WITH 5 AS n
RETURN reduce(product = 1, x IN range(1, n) |
              product * x) AS factorial;
~~~

Kết quả: `factorial = 120`.

**Tự kiểm tra:** tại sao khởi tạo `product = 1`? Vì 1 là phần tử trung hòa của phép nhân; khởi tạo 0 sẽ làm kết quả luôn bằng 0. Với `n = 0`, cần xác định rõ trường hợp biên theo quy ước toán học `0! = 1`, ví dụ dùng `CASE WHEN n = 0 THEN 1 ELSE reduce(...) END`.

### Bài 2 — Tổng giá trị giỏ hàng và tổng số lượng

Cho ba dòng hàng, hãy tạo map kết quả gồm `itemCount`, `quantityTotal` và `amountTotal`:

~~~cypher
WITH [
  {sku: 'P01', quantity: 2, unitPrice: 100000},
  {sku: 'P02', quantity: 1, unitPrice: 80000},
  {sku: 'P03', quantity: 4, unitPrice: 20000}
] AS items
RETURN reduce(
  s = {itemCount: 0, quantityTotal: 0, amountTotal: 0},
  item IN items |
  {
    itemCount: s.itemCount + 1,
    quantityTotal: s.quantityTotal + item.quantity,
    amountTotal: s.amountTotal + item.quantity * item.unitPrice
  }
) AS summary;
~~~

Kết quả kỳ vọng:

~~~text
{
  itemCount: 3,
  quantityTotal: 7,
  amountTotal: 360000
}
~~~

### Bài 3 — Xử lý giá trị null có chủ đích

List đầu vào là `[5, null, 10, 15]`. Viết một biểu thức `reduce()` bỏ qua phần tử `null` và trả về tổng:

~~~cypher
WITH [5, null, 10, 15] AS numbers
RETURN reduce(
  total = 0,
  n IN numbers |
  CASE WHEN n IS NULL THEN total ELSE total + n END
) AS sumWithoutNull;
~~~

Kết quả: `sumWithoutNull = 30`.

### Bài 4 — Chọn công cụ phù hợp

Cho một truy vấn graph trả từng dòng `Order-[:CONTAINS]->Product`. Nếu chỉ cần tổng tiền của mỗi đơn, lựa chọn nào dễ hiểu và tiết kiệm list trung gian hơn?

~~~cypher
MATCH (o:Order)-[line:CONTAINS]->(p:Product)
RETURN
  o.id AS orderId,
  sum(line.quantity * p.price) AS totalAmount
ORDER BY orderId;
~~~

Đáp án: `sum()` phù hợp vì dữ liệu đang ở dạng nhiều hàng và chỉ cần cộng số. Khi đã có list được truyền vào hoặc cần trạng thái tích lũy phức tạp, mới cân nhắc `reduce()`.

## Ghi nhớ

`reduce()` trong Cypher là phép **tích lũy từ trái sang phải trên các phần tử của một list**:

~~~cypher
reduce(acc = initialValue, item IN sourceList |
       expressionUsing(acc, item))
~~~

Nó trả **một giá trị cuối** có thể là số, chuỗi, list hoặc map; giá trị khởi tạo quyết định kết quả khi danh sách rỗng. Hãy xử lý `null`, chọn đúng kiểu dữ liệu và kiểm soát thứ tự khi phép tích lũy phụ thuộc vị trí. Khi làm việc với Neo4j, `reduce()` đặc biệt hữu ích cho list từ `collect()` hoặc `relationships(path)`; nhưng với phép cộng trực tiếp trên nhiều hàng, `sum()` thường đơn giản và tiết kiệm hơn.
