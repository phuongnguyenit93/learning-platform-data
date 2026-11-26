# Truy cập phần tử, cắt danh sách và tạo dãy giá trị trong Cypher

## Mục tiêu bài học

Trong Neo4j, dữ liệu được mô hình hóa dưới dạng **property graph** gồm node, relationship và property. Bên cạnh việc đi qua các quan hệ, Cypher còn thường xuyên xử lý **list** (danh sách) chứa giá trị, node, relationship hoặc map. Danh sách xuất hiện khi ứng dụng gửi tham số cho truy vấn, khi `collect()` gom nhiều hàng, khi `nodes(path)` lấy các node trên đường đi, hoặc khi cần tạo một dãy số bằng `range()`.

Trong chương **Danh sách và luồng dữ liệu** của module `DATABASE_ENGINE_GRAPH_NEO4J`, bài này tập trung vào ba thao tác:

1. **Truy cập phần tử theo vị trí** bằng `list[index]`.
2. **Cắt danh sách thành danh sách con** bằng `list[start..end]`.
3. **Tạo dãy số nguyên** bằng `range(start, end[, step])`, sau đó dùng dãy số trong biểu thức hoặc kết hợp với `UNWIND`.

Sau bài học, bạn có thể xác định đúng chỉ số từ 0, chỉ số âm, ranh giới cắt không bao gồm phần tử cuối; xử lý danh sách rỗng hoặc `null`; áp dụng các thao tác này để lấy vài kết quả đầu, đánh số hàng và phân tích đường đi trong đồ thị Neo4j.

## 1. Danh sách và vị trí phần tử

Danh sách Cypher được viết bằng cặp ngoặc vuông. Ví dụ:

~~~cypher
WITH ['Neo4j', 'Cypher', 'Java Driver', 'Spring Data Neo4j'] AS topics
RETURN topics, size(topics) AS topicCount;
~~~

`size(topics)` trả về `4` vì danh sách có bốn phần tử. Mỗi phần tử có một vị trí (index) bắt đầu từ **0**:

~~~text
topics = ['Neo4j', 'Cypher', 'Java Driver', 'Spring Data Neo4j']
vị trí:      0        1           2                 3
vị trí âm:  -4       -3          -2                -1
~~~

Một danh sách có `n` phần tử có chỉ số không âm hợp lệ từ `0` đến `n - 1`. Chỉ số âm đếm ngược từ cuối: `-1` là phần tử cuối, `-2` là phần tử kế cuối.

Không phải danh sách nào cũng là property lưu trong cơ sở dữ liệu. **Giá trị list được tạo trong truy vấn** có thể chứa map, node hoặc relationship. Trong khi đó, **property của node/relationship** chỉ lưu được những kiểu dữ liệu mà mô hình property Neo4j cho phép, chẳng hạn mảng giá trị đơn giản; không thể lưu tùy ý danh sách node hay map làm property.

## 2. Truy cập một phần tử bằng `list[index]`

Cú pháp:

~~~cypher
listExpression[indexExpression]
~~~

Kết quả là **một phần tử**, không phải một danh sách con. Cả biểu thức danh sách lẫn biểu thức chỉ số đều có thể đến từ biến đã tạo trong truy vấn.

~~~cypher
WITH ['Neo4j', 'Cypher', 'Java Driver', 'Spring Data Neo4j'] AS topics
RETURN
  topics[0]  AS firstTopic,
  topics[2]  AS thirdTopic,
  topics[-1] AS lastTopic,
  topics[-2] AS nextToLastTopic;
~~~

| Cột trả về | Giá trị |
| --- | --- |
| `firstTopic` | `Neo4j` |
| `thirdTopic` | `Java Driver` |
| `lastTopic` | `Spring Data Neo4j` |
| `nextToLastTopic` | `Java Driver` |

### Chỉ số vượt phạm vi

Truy cập vị trí không tồn tại trả về `null`:

~~~cypher
WITH ['A', 'B', 'C'] AS letters
RETURN
  letters[2]  AS validIndex,
  letters[3]  AS beyondEnd,
  letters[-4] AS beforeStart;
~~~

Kết quả: `validIndex = 'C'`; `beyondEnd` và `beforeStart` đều là `null`. Vì vậy, thao tác đọc một phần tử bằng chỉ số trong Cypher không tự động làm truy vấn thất bại chỉ vì chỉ số vượt phạm vi.

Tuy nhiên, `null` ở kết quả không cho biết ngay nguyên nhân là **danh sách rỗng**, **chỉ số ngoài phạm vi**, **phần tử thật sự bằng null** hay **giá trị danh sách đầu vào bằng null**. Khi các trường hợp đó có ý nghĩa nghiệp vụ khác nhau, hãy kiểm tra dữ liệu trước.

~~~cypher
WITH [] AS items
RETURN
  size(items) AS itemCount,
  items[0] AS firstItem,
  coalesce(items[0], 'KHONG_CO') AS firstOrFallback;
~~~

Kết quả là `itemCount = 0`, `firstItem = null`, `firstOrFallback = 'KHONG_CO'`. `coalesce(x, fallback)` lấy giá trị dự phòng nếu `x` bằng `null`; với phần tử `null` thực sự, nó cũng chọn dự phòng.

### Truy cập phần tử an toàn khi đầu vào tùy chọn

Giả sử một map từ ứng dụng có thể không chứa trường `tags`:

~~~cypher
WITH {id: 'C01', tags: null} AS customerInput
WITH
  customerInput.id AS customerId,
  coalesce(customerInput.tags, []) AS tags
RETURN
  customerId,
  size(tags) AS tagCount,
  CASE
    WHEN size(tags) > 0 THEN tags[0]
    ELSE 'CHUA_CO_NHAN'
  END AS firstTag;
~~~

`coalesce(..., [])` chuẩn hóa giá trị danh sách bị thiếu thành danh sách rỗng. `CASE` thể hiện rõ quyết định nghiệp vụ khi không có nhãn, thay vì dựa vào `null` rồi đoán nguyên nhân.

### So sánh với `head()` và `last()`

Cypher cũng có các hàm lấy phần tử đầu/cuối:

~~~cypher
WITH [10, 20, 30] AS amounts
RETURN
  amounts[0] AS firstByIndex,
  head(amounts) AS firstByFunction,
  amounts[-1] AS lastByIndex,
  last(amounts) AS lastByFunction;
~~~

Hai cách lấy đầu và hai cách lấy cuối cho kết quả tương ứng `10` và `30`. Dùng cú pháp chỉ số khi cần **vị trí bất kỳ**; dùng `head()`/`last()` khi ý định “đầu/cuối” cần nổi bật.

## 3. Cắt danh sách bằng `list[start..end]`

Nếu `list[index]` lấy **một phần tử**, cú pháp sau tạo **một danh sách con**:

~~~cypher
listExpression[startIndex..endIndex]
~~~

Quy tắc quan trọng:

- `startIndex` **được lấy** vào lát cắt (inclusive).
- `endIndex` **không được lấy** vào lát cắt (exclusive).
- Có thể bỏ trống `startIndex` để bắt đầu từ đầu, hoặc bỏ trống `endIndex` để lấy đến hết.
- Có thể dùng chỉ số âm tính từ cuối danh sách.
- Nếu điểm bắt đầu và điểm kết thúc trùng nhau, lát cắt là danh sách rỗng `[]`.

Xét danh sách năm phần tử:

~~~cypher
WITH ['A', 'B', 'C', 'D', 'E'] AS letters
RETURN
  letters[1..4]   AS middle,
  letters[..3]    AS firstThree,
  letters[2..]    AS fromThird,
  letters[-2..]   AS lastTwo,
  letters[..-1]   AS exceptLast,
  letters[2..2]   AS emptySlice;
~~~

| Biểu thức | Kết quả | Giải thích |
| --- | --- | --- |
| `letters[1..4]` | `['B', 'C', 'D']` | Vị trí 1, 2, 3; không lấy vị trí 4 |
| `letters[..3]` | `['A', 'B', 'C']` | Bỏ đầu, bắt đầu từ 0 |
| `letters[2..]` | `['C', 'D', 'E']` | Lấy từ vị trí 2 đến hết |
| `letters[-2..]` | `['D', 'E']` | Lấy hai phần tử cuối |
| `letters[..-1]` | `['A', 'B', 'C', 'D']` | Không lấy phần tử cuối |
| `letters[2..2]` | `[]` | Bắt đầu bằng điểm kết thúc |

Đối với `letters[-3..-1]`, điểm bắt đầu là `C` còn điểm kết thúc là vị trí `E` nhưng **không bao gồm E**, nên kết quả là `['C', 'D']`.

### Cẩn thận với “đến phần tử thứ N”

Để lấy **ba phần tử đầu**, dùng `letters[..3]`, không phải `letters[..2]`. Lát cắt kết thúc tại vị trí `3` nhưng không lấy phần tử ở vị trí đó.

~~~text
Vị trí:         0    1    2    3    4
Danh sách:      A    B    C    D    E
letters[1..4]:      [B   C    D]   (bỏ E)
letters[..3]:  [A    B    C]       (bỏ D, E)
~~~

Phép cắt **không thay đổi danh sách ban đầu**; nó trả về một giá trị danh sách mới để đưa sang bước kế tiếp.

### Dùng biến để tính ranh giới

Trong ứng dụng, số phần tử cần lấy thường là tham số:

~~~cypher
WITH
  ['O01', 'O02', 'O03', 'O04', 'O05'] AS orderIds,
  1 AS startIndex,
  2 AS pageSize
RETURN
  orderIds[startIndex..startIndex + pageSize] AS selectedOrders;
~~~

Kết quả: `selectedOrders = ['O02', 'O03']`. Ở đây `startIndex = 1` và `pageSize = 2`; ranh giới kết thúc là `3`, nên chọn các vị trí 1 và 2.

Việc cắt một danh sách đã có trong bộ nhớ **không giống** giới hạn số hàng ở câu truy vấn gốc. Nếu trước đó `collect()` đã gom rất nhiều node thành một danh sách lớn, `list[..10]` chỉ chọn phần cần dùng **sau khi danh sách đã được tạo**. Khi chỉ cần 10 hàng, có thể giảm dữ liệu từ sớm bằng `ORDER BY` và `LIMIT` đúng vị trí trước khi `collect()`.

## 4. Tạo dãy số nguyên bằng `range()`

`range()` là hàm Cypher tạo **danh sách số nguyên liên tiếp theo bước nhảy**:

~~~cypher
range(start, end)
range(start, end, step)
~~~

Trong dãy `range()`, **điểm kết thúc được tính vào kết quả nếu có thể đi tới bằng bước nhảy**. Điều này khác với `endIndex` trong lát cắt `list[start..end]`.

~~~cypher
RETURN
  range(0, 4) AS zeroToFour,
  range(1, 9, 2) AS oddNumbers,
  range(10, 4, -3) AS descending;
~~~

| Biểu thức | Kết quả |
| --- | --- |
| `range(0, 4)` | `[0, 1, 2, 3, 4]` |
| `range(1, 9, 2)` | `[1, 3, 5, 7, 9]` |
| `range(10, 4, -3)` | `[10, 7, 4]` |
| `range(0, 5, 2)` | `[0, 2, 4]` |

Nếu không truyền `step`, bước nhảy mặc định là `1`. Khi đếm lùi, truyền bước âm, ví dụ `-1` hoặc `-3`. Bước nhảy `0` không hợp lệ. Để tránh dãy rỗng do đi sai hướng, hãy dùng bước dương khi tăng và bước âm khi giảm.

`range()` trả về **một danh sách**, không tự sinh ra nhiều hàng. Điều này dễ thấy ở ví dụ:

~~~cypher
WITH range(1, 5) AS sequence
RETURN sequence, size(sequence) AS numberOfValues;
~~~

Kết quả là **một hàng** chứa `sequence = [1, 2, 3, 4, 5]` và `numberOfValues = 5`.

### Biến dãy số thành hàng bằng `UNWIND`

Muốn thực hiện một phép tính cho từng số, kết hợp `range()` với `UNWIND`:

~~~cypher
UNWIND range(1, 5) AS n
RETURN n, n * n AS square
ORDER BY n;
~~~

| n | square |
| ---: | ---: |
| 1 | 1 |
| 2 | 4 |
| 3 | 9 |
| 4 | 16 |
| 5 | 25 |

Lúc này mỗi phần tử trong dãy sinh một hàng. `ORDER BY` giúp kết quả được trình bày đúng thứ tự; không nên dựa vào thứ tự mặc định của các hàng sau `UNWIND`.

### Tạo dãy để làm list comprehension

List comprehension là cách biến đổi giá trị **ngay trong một danh sách**:

~~~cypher
WITH range(1, 6) AS numbers
RETURN
  [n IN numbers | n * n] AS squares,
  [n IN numbers WHERE n % 2 = 0 | n] AS evenNumbers;
~~~

Kết quả:

- `squares = [1, 4, 9, 16, 25, 36]`;
- `evenNumbers = [2, 4, 6]`.

So sánh: `UNWIND` mở danh sách thành **nhiều hàng**; list comprehension trả về **một danh sách đã lọc hoặc biến đổi**. Hãy chọn dựa trên dữ liệu mà mệnh đề tiếp theo cần.

## 5. Kết hợp chỉ số và range để đánh số phần tử

Giả sử danh sách SKU đã được sắp theo thứ tự mà ứng dụng muốn hiển thị:

~~~cypher
WITH ['P01', 'P02', 'P03'] AS skus
WITH
  skus,
  CASE
    WHEN size(skus) = 0 THEN []
    ELSE range(0, size(skus) - 1)
  END AS indexes
UNWIND indexes AS i
RETURN
  i AS zeroBasedIndex,
  i + 1 AS displayPosition,
  skus[i] AS sku
ORDER BY zeroBasedIndex;
~~~

| zeroBasedIndex | displayPosition | sku |
| ---: | ---: | --- |
| 0 | 1 | P01 |
| 1 | 2 | P02 |
| 2 | 3 | P03 |

Mô hình này có ba bước: tạo các chỉ số hợp lệ, mở danh sách chỉ số bằng `UNWIND`, rồi truy cập phần tử `skus[i]`. `CASE` xử lý danh sách rỗng bằng cách tạo `[]` thay vì tự tính một khoảng chỉ số không phù hợp.

> Lưu ý: nếu chỉ cần lấy từng SKU mà không cần biết vị trí, `UNWIND skus AS sku` là đủ. Việc tạo thêm `range()` và truy cập lại danh sách chỉ hữu ích khi **chỉ số** cũng là dữ liệu cần xuất hoặc cần tính toán.

### Đánh số từ đầu vào có map

Khi dữ liệu ứng dụng có thứ tự quan trọng, cách rõ ràng nhất thường là truyền kèm trường `position`:

~~~cypher
UNWIND [
  {position: 2, sku: 'P03'},
  {position: 0, sku: 'P01'},
  {position: 1, sku: 'P02'}
] AS row
RETURN row.position AS position, row.sku AS sku
ORDER BY position;
~~~

Kết quả `P01`, `P02`, `P03` được xác định bằng `ORDER BY position`. Điều này tránh dựa vào thứ tự mà `UNWIND` có thể không bảo đảm khi mở danh sách.

## 6. Áp dụng vào node, relationship và đường đi Neo4j

List trong Cypher không chỉ chứa chuỗi hoặc số. Khi tìm một đường đi (path), các hàm `nodes(p)` và `relationships(p)` trả về danh sách node và relationship trên đường đi đó.

Giả sử đồ thị có cấu trúc:

~~~text
(:Person {id: 'U01'})-[:KNOWS]->(:Person)-[:KNOWS]->(:Person)
~~~

Truy vấn sau minh họa cách lấy đầu, cuối và các node trung gian của đường đi:

~~~cypher
MATCH p = (a:Person {id: $personId})-[:KNOWS*1..3]->(b:Person)
WITH p, nodes(p) AS pathNodes, relationships(p) AS pathRels
RETURN
  pathNodes[0] AS startPerson,
  pathNodes[-1] AS endPerson,
  pathNodes[1..-1] AS intermediatePeople,
  size(pathNodes) AS nodeCount,
  size(pathRels) AS relationshipCount;
~~~

Nếu một đường đi gồm ba node `A → B → C`, thì `pathNodes = [A, B, C]`, `pathNodes[0] = A`, `pathNodes[-1] = C` và `pathNodes[1..-1] = [B]`. Số relationship là hai.

Đây là ví dụ **truy vấn trên đồ thị có sẵn**: phải tồn tại những node `Person`, relationship `KNOWS` tương ứng và tham số `$personId` mới có hàng kết quả. Không cần thay đổi cấu trúc graph để hiểu phép truy cập hay cắt danh sách; chúng hoạt động trên list do `nodes(p)` trả về.

### Lấy một số phần tử đầu từ kết quả collect

Một trường hợp khác là danh sách đơn hàng được gom theo khách:

~~~cypher
MATCH (c:Customer {id: $customerId})-[:PLACED]->(o:Order)
WITH o
ORDER BY o.createdAt DESC, o.id ASC
WITH collect(o.id) AS orderedOrderIds
RETURN
  orderedOrderIds[0] AS newestOrderId,
  orderedOrderIds[..3] AS threeNewestOrderIds,
  size(orderedOrderIds) AS totalOrders;
~~~

`ORDER BY o.createdAt DESC, o.id ASC` xác định thứ tự đầu vào cho `collect()` ở mệnh đề kế tiếp: đơn mới nhất nằm đầu danh sách, còn `o.id` là khóa phụ khi có thời điểm bằng nhau. `orderedOrderIds[..3]` lấy tối đa ba mã đầu tiên.

**Phân biệt hai mục đích**:

- Muốn **tổng số đơn** và **ba mã đầu** trong cùng một hàng: `collect()` rồi cắt danh sách thể hiện đúng ý nghĩa.
- Chỉ muốn **ba node đơn mới nhất**: cân nhắc `ORDER BY ... LIMIT 3` trước khi gom danh sách để giảm lượng dữ liệu cần giữ. Khi giới hạn trước `collect()`, `totalOrders` không còn là tổng số đơn gốc nếu chỉ đếm các hàng đã bị giới hạn.

## 7. Cắt danh sách để phân trang: đúng thứ tự, đúng chi phí

Với một danh sách kết quả đã được ứng dụng chuẩn hóa thứ tự, có thể cắt theo trang:

~~~cypher
WITH
  ['O01', 'O02', 'O03', 'O04', 'O05', 'O06', 'O07'] AS orderedIds,
  1 AS page,
  3 AS pageSize
WITH orderedIds, page * pageSize AS offset, pageSize
RETURN orderedIds[offset..offset + pageSize] AS pageIds;
~~~

Quy ước `page` bắt đầu từ 0; `page = 1` là trang thứ hai. Trong ví dụ, `offset = 3` và `pageIds = ['O04', 'O05', 'O06']`.

Ứng dụng cần xác thực `page >= 0`, `pageSize > 0` và giới hạn kích thước trang trước khi đưa vào truy vấn. Nếu `orderedIds` được tạo bởi `collect()` từ nhiều kết quả đồ thị, hãy bảo đảm luồng đầu vào được sắp xếp rõ ràng trước khi gom.

Với tập dữ liệu lớn, phân trang ngay trên **hàng kết quả Cypher** thường hiệu quả hơn việc `collect()` tất cả:

~~~cypher
MATCH (o:Order)
WITH o
ORDER BY o.createdAt DESC, o.id ASC
SKIP $offset
LIMIT $pageSize
RETURN o.id AS orderId, o.createdAt AS createdAt
ORDER BY createdAt DESC, orderId ASC;
~~~

`SKIP`/`LIMIT` giới hạn các **hàng** cần đi tiếp; lát cắt `[start..end]` chỉ cắt một **giá trị danh sách đã tồn tại**. Cả hai cần thứ tự xác định nếu dùng để phân trang. Trong hệ thống có lượng dữ liệu lớn hoặc liên tục thay đổi, có thể cân nhắc phân trang theo khóa (keyset pagination) thay cho `SKIP` quá sâu.

## 8. Những lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Lấy sai phần tử đầu/ cuối | Nhầm danh sách bắt đầu từ chỉ số 1 | Ghi nhớ chỉ số đầu là `0`, cuối là `-1` |
| Cắt ba phần tử nhưng chỉ nhận hai | Nhầm ranh giới cuối của `[start..end]` là bao gồm | `items[..3]` lấy các vị trí `0, 1, 2` |
| `range(0, 3)` có bốn số | `range()` bao gồm điểm kết thúc nếu đến được | Phân biệt `range(0, 3)` với `items[0..3]` |
| Truy cập ngoài phạm vi ra `null` | Danh sách quá ngắn hoặc chỉ số sai | Kiểm tra `size(list)`, dùng `CASE`/`coalesce()` đúng mục đích |
| Danh sách con không đúng thứ tự nghiệp vụ | Danh sách gốc từ `collect()` chưa có thứ tự xác định | `ORDER BY` ở bước tạo luồng trước `collect()` |
| Dùng `UNWIND range(...)` làm truy vấn phình to | Dãy sinh quá nhiều phần tử, mỗi phần tử tạo một hàng | Giới hạn tham số đầu vào; xét số hàng và bộ nhớ trước khi tạo dãy |
| Phân trang bằng lát cắt chậm với dữ liệu lớn | Tạo toàn bộ danh sách trước rồi mới cắt | Dùng `ORDER BY` + `SKIP`/`LIMIT` trên hàng, hoặc keyset pagination |
| Tạo vị trí bằng `range(0, size(xs) - 1)` khi list rỗng | Không có chỉ số hợp lệ trong danh sách rỗng | Xử lý `size(xs) = 0` bằng `CASE` trước khi tạo dãy |

Khi cần đánh giá hiệu năng, sử dụng `EXPLAIN` để xem kế hoạch dự kiến và `PROFILE` để quan sát số hàng thực tế qua từng toán tử trên dữ liệu thử. Không mặc định rằng việc viết ngắn gọn bằng cú pháp lát cắt sẽ giảm số node đã được đọc ở các bước trước đó.

## 9. Bài thực hành

### Bài 1 — Lấy phần tử và cắt danh sách

Cho danh sách `['A', 'B', 'C', 'D', 'E', 'F']`. Hãy trả về:

1. Phần tử đầu, phần tử cuối.
2. Ba phần tử từ vị trí 1, tức `['B', 'C', 'D']`.
3. Danh sách không có hai phần tử cuối.

Lời giải tham khảo:

~~~cypher
WITH ['A', 'B', 'C', 'D', 'E', 'F'] AS letters
RETURN
  letters[0] AS firstValue,
  letters[-1] AS lastValue,
  letters[1..4] AS threeFromSecond,
  letters[..-2] AS withoutLastTwo;
~~~

Kết quả lần lượt là `'A'`, `'F'`, `['B', 'C', 'D']` và `['A', 'B', 'C', 'D']`.

### Bài 2 — Tạo dãy và đánh số bản ghi

Cho `products = ['P10', 'P20', 'P30', 'P40']`. Hãy trả về bốn hàng với `position` bắt đầu từ 1 và `sku` tương ứng.

~~~cypher
WITH ['P10', 'P20', 'P30', 'P40'] AS products
UNWIND range(0, size(products) - 1) AS i
RETURN i + 1 AS position, products[i] AS sku
ORDER BY position;
~~~

Kết quả kỳ vọng: `(1, 'P10')`, `(2, 'P20')`, `(3, 'P30')` và `(4, 'P40')`. Ở ví dụ này, danh sách đã biết có bốn phần tử; nếu nhận danh sách bất kỳ từ ứng dụng, cần áp dụng cách xử lý danh sách rỗng ở phần 5.

### Bài 3 — Tự kiểm tra ranh giới

Cho `items = [10, 20, 30, 40]`, hãy tự dự đoán kết quả của:

~~~cypher
WITH [10, 20, 30, 40] AS items
RETURN
  items[-1] AS a,
  items[1..3] AS b,
  items[..-1] AS c,
  range(1, 4, 2) AS d;
~~~

Đáp án: `a = 40`; `b = [20, 30]`; `c = [10, 20, 30]`; `d = [1, 3]`. Giá trị `4` không xuất hiện trong `d` vì bước nhảy 2 từ 1 đi qua 1, 3 rồi vượt quá điểm kết thúc 4.

## Ghi nhớ

Cypher cung cấp ba cách làm việc với vị trí trong danh sách:

- `list[index]` lấy **một phần tử**; chỉ số bắt đầu từ 0, chỉ số âm đếm từ cuối; vượt phạm vi trả về `null`.
- `list[start..end]` tạo **danh sách con**; lấy vị trí bắt đầu nhưng **không lấy vị trí kết thúc**.
- `range(start, end[, step])` tạo **dãy số nguyên**; điểm kết thúc được tính vào dãy nếu bước nhảy đi đến đó.

Khi kết hợp với `WITH`, `collect()`, `UNWIND` và các hàm danh sách đường đi như `nodes(p)`, những thao tác này giúp truy vấn property graph Neo4j gọn, dễ kiểm soát hơn. Luôn xác định thứ tự đầu vào, kích thước danh sách và ý nghĩa của vị trí trước khi dùng chỉ số hoặc cắt danh sách trong luồng dữ liệu.
