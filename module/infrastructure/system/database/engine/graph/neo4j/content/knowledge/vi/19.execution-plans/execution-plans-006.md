# Phát hiện CartesianProduct, Eager, Sort và tập trung gian lớn trong kế hoạch thực thi Neo4j

## 1. Mục tiêu: tìm phần thực sự tiêu tốn tài nguyên

Trong Neo4j, một câu Cypher mô tả **mẫu đồ thị cần tìm**, không mô tả từng bước vật lý để tìm nó. Query planner lựa chọn một **execution plan** gồm các toán tử (*operator*) như `NodeIndexSeek`, `Expand(All)`, `Filter`, `CartesianProduct`, `Eager` và `Sort`. Hiệu năng phụ thuộc lớn vào lượng dữ liệu đi **qua các toán tử trung gian**, chứ không chỉ vào số dòng ở kết quả cuối.

Ví dụ ứng dụng muốn trả về 10 sản phẩm được xem nhiều nhất. Truy vấn có `LIMIT 10` nhưng có thể phải mở rộng hàng triệu relationship, gom nhóm và sắp xếp một tập lớn trước khi trả về 10 dòng. Nếu chỉ nhìn thời gian chạy hoặc 10 dòng đầu ra, ta bỏ lỡ nguyên nhân chính.

Bài này tập trung vào bốn dấu hiệu trong kế hoạch thực thi:

| Dấu hiệu | Tác động thường gặp | Câu hỏi chẩn đoán |
| --- | --- | --- |
| `CartesianProduct` | Nhân mỗi dòng của tập bên trái với mọi dòng của tập bên phải | Hai nhánh có thực sự cần kết hợp mọi cặp? |
| `Eager` | Buộc phần trước hoàn tất và giữ dữ liệu trung gian trước khi tiếp tục | Có xung đột đọc/ghi khiến planner cần rào chắn ngữ nghĩa? |
| `Sort` | Sắp xếp tập dòng, thường phải giữ toàn bộ đầu vào cần sắp xếp | Có thể thu nhỏ đầu vào, dùng `Top` hoặc tận dụng thứ tự index? |
| Tập trung gian lớn | Tăng `Rows`, `DB Hits`, bộ nhớ hoặc số phép xử lý ở nhánh sau | Dòng dữ liệu phình ra chính xác tại toán tử nào? |

**Không phải cứ thấy một trong các operator này là truy vấn sai.** Mục tiêu là xác định chúng có cần thiết, dữ liệu đi qua lớn đến đâu, và có thể giảm chi phí **mà giữ nguyên ý nghĩa kết quả** hay không.

## 2. Dùng `EXPLAIN` và `PROFILE` đúng cách

### 2.1. Khác biệt giữa kế hoạch dự kiến và kết quả đo

```cypher
EXPLAIN
MATCH (p:Product)
WHERE p.active = true
RETURN p.name;
```

`EXPLAIN` cho biết **kế hoạch dự kiến**, không thực thi câu Cypher và không ghi dữ liệu. Đây là lựa chọn đầu tiên khi kiểm tra truy vấn lạ hoặc truy vấn có `SET`, `CREATE`, `MERGE`, `DELETE`.

```cypher
PROFILE
MATCH (p:Product)
WHERE p.active = true
RETURN p.name;
```

`PROFILE` **thực thi thật** câu Cypher, rồi ghi lại số dòng, lần truy cập dữ liệu và các thống kê hiệu năng. Với truy vấn ghi, `PROFILE` **có thể thay đổi đồ thị**. Chỉ chạy trên môi trường hoặc giao dịch có chủ đích; ưu tiên `EXPLAIN` trước khi quyết định profiling truy vấn ghi.

`PROFILE` cũng có overhead, nên đo trong điều kiện phù hợp, dùng dữ liệu và tham số đại diện thay vì kết luận từ một lần chạy.

### 2.2. Đọc các cột then chốt

| Cột/thành phần | Ý nghĩa | Cách đọc khi tìm điểm nghẽn |
| --- | --- | --- |
| `Operator` | Bước thực thi, ví dụ `Expand(All)` hoặc `Sort` | Xác định kiểu công việc đang diễn ra |
| `Details` | Node/relationship, điều kiện, biểu thức hoặc chỉ mục được dùng | Kiểm tra có quét đúng label, type, property và hướng quan hệ không |
| `Estimated Rows` | Số dòng planner **ước lượng** tại operator | So với `Rows` để tìm vùng dự đoán sai; không xem là số đo thực |
| `Rows` | Số dòng operator **thực tế sinh ra** khi chạy `PROFILE` | Tìm nơi số dòng tăng mạnh rồi mới bị lọc hoặc gom lại |
| `DB Hits` | Thống kê lượt truy cập tầng lưu trữ | Lớn bất thường có thể do scan, lặp lại seek hoặc mở rộng quan hệ tốn kém |
| `Memory (Bytes)` | Đỉnh bộ nhớ được theo dõi cho operator | Đặc biệt chú ý `Sort`, `Eager` và nhóm aggregate/join |
| `Ordered by` | Thứ tự mà một operator bảo đảm cho dòng đầu ra | Giúp phát hiện có thể tránh `Sort` bổ sung hay không |
| `Page Cache Hits/Misses` | Lần đọc trang trong cache/không có trong cache, khi runtime/edition cung cấp | So sánh trong điều kiện cache tương đương |
| `Time (ms)`, `Pipeline` | Thời gian và pipeline thực thi khi được báo cáo | Có thể tính cho cả pipeline được fuse; không mặc định là thời gian riêng lẻ của một operator |

Hai lưu ý:

- `Memory (Bytes)` trên một dòng là **đỉnh theo operator**, không phải tổng bộ nhớ truy vấn. Không cộng tùy tiện các đỉnh đó; xem thêm số liệu bộ nhớ tổng ở phần chân kế hoạch nếu có.
- Kế hoạch có thể khác theo phiên bản Neo4j, runtime, index, thống kê graph và tham số. Không nên yêu cầu tên/toán tử xuất hiện **giống tuyệt đối** giữa hai môi trường.

### 2.3. Đọc sơ đồ theo luồng dữ liệu

Kế hoạch hiển thị dưới dạng cây, luồng bản ghi đi từ các **leaf operator** (scan/seek ở phía dưới) lên `ProduceResults` ở phía trên. Ví dụ minh họa, không phải bản kế hoạch cố định:

```text
+ProduceResults              10 rows
 |
 +Top                        10 rows
  |
  +Projection               5,000 rows
   |
   +Filter                  5,000 rows
    |
    +Expand(All)            80,000 rows
     |
     +NodeIndexSeek            1 row
```

Nút thắt có thể nằm ở bước `Expand(All)` sinh 80.000 dòng, dù kết quả chỉ có 10 dòng. Các con số ở đây chỉ minh họa cách đọc; hãy lấy số đo từ `PROFILE` của truy vấn cụ thể.

Trình tự phân tích hiệu quả:

1. Bắt đầu ở `ProduceResults`, xem kết quả cuối có bao nhiêu dòng.
2. Lần theo xuống các nhánh để tìm bước mà `Rows` đột ngột tăng mạnh, hoặc `DB Hits`/bộ nhớ cao.
3. Xác định nguyên nhân: nối hai tập độc lập, quét rộng, duyệt quan hệ quá nhiều cấp, gom nhóm hay sắp xếp quá muộn.
4. Đề xuất cách giảm dữ liệu **trước điểm nghẽn** rồi chạy lại `PROFILE` với cùng dữ liệu, tham số và điều kiện tải.

## 3. Phát hiện `CartesianProduct`

### 3.1. Vì sao toán tử này dễ gây bùng nổ dòng?

`CartesianProduct` kết hợp **mọi dòng của nhánh trái với mọi dòng của nhánh phải**. Nếu hai nhánh có lần lượt \(N\) và \(M\) dòng, số tổ hợp đầu ra có thể tới \(N \times M\).

| Số dòng bên trái | Số dòng bên phải | Số cặp sinh ra |
| ---: | ---: | ---: |
| 10 | 20 | 200 |
| 1.000 | 5.000 | 5.000.000 |
| 50.000 | 100.000 | 5.000.000.000 |

Ví dụ hai mẫu graph độc lập:

```cypher
EXPLAIN
MATCH (u:AppUser), (p:Product)
RETURN u.id AS userId, p.id AS productId;
```

Không có quan hệ hoặc điều kiện nối `u` và `p`. Về ngữ nghĩa, truy vấn **đòi hỏi mọi cặp user-product**, nên planner có thể chọn `CartesianProduct`. Việc chỉ thêm `LIMIT 10` cuối truy vấn không biến toàn bộ yêu cầu thành truy vấn quan hệ có điều kiện; các operator chặn như `Sort`/aggregate có thể vẫn phải xử lý tập lớn.

**Dấu hiệu từ plan:** tìm `CartesianProduct` có `Rows` lớn; lần theo hai nhánh con để thấy số dòng đầu vào và lý do chúng không liên kết. Cũng có thể xuất hiện các dạng join/nested loops khác gây nhân số dòng, dù không mang đúng tên `CartesianProduct`.

### 3.2. Sửa từ mô hình truy vấn

Nếu nghiệp vụ cần **sản phẩm mà một người đã xem**, viết rõ relationship:

```cypher
PROFILE
MATCH (u:AppUser {id: $userId})-[:VIEWED]->(p:Product)
WHERE p.active = true
RETURN p.id, p.name;
```

Câu này chỉ lấy sản phẩm có cạnh `VIEWED` xuất phát từ user mục tiêu. Một unique constraint hoặc range index cho `AppUser.id` giúp planner có khả năng bắt đầu từ một node chọn lọc. Một lookup index trên label `AppUser` **không thay thế** index giá trị `id` khi truy vấn tìm theo property.

Nếu mục tiêu là nối hai nhóm theo **khóa nghiệp vụ**, cần viết điều kiện thực sự:

```cypher
MATCH (u:AppUser)
MATCH (a:UserAudit)
WHERE u.id = a.userId
RETURN u.id, a.createdAt;
```

Ở đây join theo property mang nghĩa khác với quan hệ graph; planner có thể dùng hash join/seek hoặc phương án khác. Cần kiểm tra index và plan thực tế để chọn cách hiệu quả. Không tự ý thay thành relationship nếu graph chưa chứa relationship tương ứng.

### 3.3. Khi Cartesian product là chủ ý

Một số bài toán cần tạo tất cả tổ hợp (ma trận thử nghiệm, lịch kết hợp, cặp ứng viên). Khi đó:

- Chọn phạm vi đầu vào đủ nhỏ, lọc trước khi tạo tích Descartes.
- Đánh giá \(N \times M\) trước khi chạy toàn bộ.
- Chọn chiến lược phân trang/batch và giới hạn tài nguyên phù hợp với nghiệp vụ.
- Không coi xóa `CartesianProduct` bằng mọi giá là mục tiêu: **đúng kết quả** là ưu tiên trước, sau đó mới tối ưu.

## 4. Phát hiện và hiểu đúng `Eager`

### 4.1. `Eager` là rào chắn dữ liệu, thường bảo vệ ngữ nghĩa

Nhiều operator Neo4j có thể **truyền dòng dần** sang bước tiếp theo. Ngược lại, `Eager` yêu cầu các bước trước hoàn tất, thu gom các dòng liên quan, rồi mới cho bước sau xử lý. Điều này có thể tăng bộ nhớ và độ trễ nhận dòng đầu tiên.

Vì sao planner chèn `Eager`? Một truy vấn có thể vừa **đọc graph** vừa **sửa chính cấu trúc/thuộc tính đang ảnh hưởng tới phần đọc**. Nếu sửa trong lúc đang quét, câu truy vấn có nguy cơ quan sát lại phần tử mới hoặc bỏ sót phần tử, khiến kết quả khác ý nghĩa Cypher mong muốn. `Eager` tách hai giai đoạn để bảo toàn ngữ nghĩa.

Ví dụ chỉ **kiểm tra kế hoạch**, không làm thay đổi dữ liệu:

```cypher
EXPLAIN
MATCH (p:DemoProduct)
CREATE (:DemoProduct {id: p.id + 1000});
```

Truy vấn đọc các node mang label `DemoProduct` rồi tạo thêm node cùng label. Đây là một tình huống có khả năng phát sinh xung đột đọc/ghi, khiến planner dùng rào chắn như `Eager`. Toán tử cụ thể **phụ thuộc plan/phiên bản**, nên kiểm tra thay vì khẳng định mọi lần đều phải xuất hiện.

**Không thực thi `PROFILE` ví dụ trên một cách tùy tiện**: `PROFILE` sẽ tạo node thật, có thể gây trùng khóa `id` khi chạy lặp. Với câu lệnh cập nhật, dùng `EXPLAIN` trước; thử `PROFILE` trong database thực hành có kiểm soát nếu thật sự cần số đo.

### 4.2. Cách đánh giá có đáng lo không

Trong `PROFILE` của một truy vấn ghi đã được chuẩn bị an toàn, xem:

- Có bao nhiêu `Rows` đi vào `Eager`? 50 dòng hay hàng triệu dòng?
- `Memory (Bytes)` tại operator và **đỉnh bộ nhớ toàn truy vấn** là bao nhiêu?
- Dữ liệu đã được lọc bằng khóa, label, type, thời gian… trước `Eager` chưa?
- Cần giữ mọi dòng cùng một transaction để bảo đảm tính nguyên tử không?

Không nhầm `Eager` với `EagerAggregation`. `EagerAggregation` là toán tử **gom nhóm/tổng hợp** với đặc điểm cần giữ trạng thái tính toán, có thể tốn bộ nhớ theo số nhóm; còn `Eager` thường phục vụ việc tách các phần kế hoạch để đảm bảo ngữ nghĩa đọc/ghi. Dù đều có khả năng gây áp lực bộ nhớ, **nguyên nhân và cách sửa khác nhau**.

### 4.3. Cách giảm áp lực từ `Eager`

1. **Giảm đầu vào**: xác định node/relationship theo khóa và các điều kiện chọn lọc trước thao tác ghi. Kiểm tra planner có push predicate xuống sớm hay không.
2. **Tách các thao tác không cần trộn**: ví dụ tạo node trước, tạo relationship sau, khi tính nhất quán nghiệp vụ cho phép. Mỗi bước cần được quản lý transaction phù hợp.
3. **Xử lý lô có kiểm soát** khi dữ liệu quá lớn: thiết kế batch nhỏ, idempotent, theo dõi tiến độ và đảm bảo có thể chạy lại. `CALL { ... } IN TRANSACTIONS` có thể commit từng batch và phải được chạy ở chế độ implicit transaction; nó **không đảm bảo nguyên tử cho toàn bộ các batch**.
4. **Chấp nhận `Eager` khi bắt buộc cho tính đúng đắn**. Không tìm cách ép planner bỏ rào chắn chỉ để làm plan trông ngắn hơn.

Đặc biệt, mệnh đề `WITH` **không tự động đồng nghĩa** với việc materialize toàn bộ dữ liệu. Planner quyết định operator thực tế; chỉ `EXPLAIN`/`PROFILE` mới cho thấy có rào chắn hay không.

## 5. Phát hiện `Sort` và các bước chặn dòng khác

### 5.1. `Sort` thường phải giữ toàn bộ đầu vào cần sắp xếp

```cypher
PROFILE
MATCH (p:Product)
RETURN p.id, p.price
ORDER BY p.price DESC;
```

Nếu không có đường truy cập phù hợp để tạo sẵn thứ tự, kế hoạch có thể chứa `Sort`. Với nhiều dòng, việc giữ dữ liệu để sắp xếp làm tăng bộ nhớ và thời gian chờ trước khi có kết quả.

Khi đọc plan:

- Tìm `Sort` và cột `Details` để biết **sort theo biểu thức nào**.
- Xem `Rows`/`Memory (Bytes)` tại `Sort` và ở nhánh đưa dữ liệu vào nó.
- Xác định tại sao trước đó có quá nhiều dòng: scan, join hay mở rộng relationship.
- Phân biệt việc phải sắp xếp toàn bộ kết quả với chỉ lấy **top N**.

### 5.2. `ORDER BY` đi cùng `LIMIT` có thể tạo `Top`

```cypher
PROFILE
MATCH (p:Product)
RETURN p.id, p.price
ORDER BY p.price DESC
LIMIT 10;
```

Planner có thể dùng `Top` hoặc `PartialTop` để chỉ giữ những ứng viên tốt nhất thay vì sắp xếp và giữ toàn bộ dữ liệu. Điều này thường giảm bộ nhớ của bước sắp xếp, **nhưng không đảm bảo giảm số dòng đầu vào phải quét**: để biết 10 sản phẩm có giá cao nhất, không có đường truy cập theo thứ tự thì vẫn có thể phải đọc nhiều sản phẩm.

`LIMIT` không phải “thuốc giải” cho mọi `Sort`. Nếu `ORDER BY` nằm sau phép gom nhóm lớn, vẫn phải tạo các nhóm trước khi chọn top. Nếu kết quả cần phân trang sâu bằng `SKIP` lớn, chi phí xử lý cũng có thể tăng; cân nhắc phân trang theo con trỏ/khóa có thứ tự ổn định khi phù hợp.

### 5.3. Tận dụng index trả về thứ tự

Với truy vấn thường xuyên lọc và sắp theo một property:

```cypher
CREATE RANGE INDEX product_price_idx IF NOT EXISTS
FOR (p:Product)
ON (p.price);
```

Sau khi index `ONLINE`, thử:

```cypher
EXPLAIN
MATCH (p:Product)
WHERE p.price >= $minPrice
RETURN p.id, p.price
ORDER BY p.price ASC
LIMIT 10;
```

Một range index phù hợp **có thể** giúp planner lấy dữ liệu đã được sắp thứ tự theo `price`, làm giảm nhu cầu `Sort` riêng. Kết quả phụ thuộc predicate, hướng sắp xếp, chỉ mục, runtime và đánh giá chi phí; không suy luận “có index là hết `Sort`”.

Quan sát trong plan: operator tìm kiếm index, cột `Ordered by` và sự hiện diện của `Sort`/`Top`. Với nhiều trường sort, cần xem xét composite index và thứ tự khóa thích hợp. Không tạo index hàng loạt mà chưa đo truy vấn thực tế và chi phí cập nhật index.

## 6. Tập trung gian lớn ngay cả khi không có ba operator trên

### 6.1. Nguồn gây nhân dòng: mở rộng nhiều bước

Ví dụ tìm “bạn của bạn” trong social graph:

```cypher
PROFILE
MATCH (u:AppUser {id: $userId})-[:FOLLOWS]->(f:AppUser)
      -[:FOLLOWS]->(suggested:AppUser)
RETURN suggested.id AS candidateId;
```

Nếu người đầu theo dõi 1.000 user và trung bình mỗi user đó theo dõi 500 user, số **đường đi dài hai bước** có thể lên đến hàng trăm nghìn, kể cả nhiều đường đi trỏ tới cùng một `suggested`. Ở kế hoạch có thể thấy `Expand(All)`, `Apply` hoặc các toán tử duyệt quan hệ với `Rows` tăng rất nhanh.

Nếu nghiệp vụ chỉ cần **các ứng viên duy nhất**:

```cypher
MATCH (u:AppUser {id: $userId})-[:FOLLOWS]->(:AppUser)
      -[:FOLLOWS]->(suggested:AppUser)
WHERE suggested <> u
RETURN DISTINCT suggested.id AS candidateId;
```

`DISTINCT` giúp bỏ trùng kết quả, nhưng nếu đặt **sau** quá trình mở rộng khổng lồ, nó không làm biến mất chi phí tạo những đường đi trước đó. Nó còn có thể yêu cầu operator `Distinct`, `OrderedDistinct` hoặc aggregation giữ trạng thái. Vì vậy cần tối ưu điểm bắt đầu, phạm vi relationship và điều kiện lọc sớm.

### 6.2. `collect()` và aggregation trên tập lớn

Xét truy vấn:

```cypher
MATCH (u:AppUser)-[:VIEWED]->(p:Product)
WITH u, collect(p) AS viewedProducts
RETURN u.id, size(viewedProducts) AS viewedCount;
```

`collect(p)` có thể tích lũy nhiều node cho mỗi user, trong khi mục tiêu chỉ cần **đếm**. Một cách viết nhẹ hơn về dữ liệu trung gian:

```cypher
MATCH (u:AppUser)-[:VIEWED]->(p:Product)
RETURN u.id AS userId, count(p) AS viewedCount;
```

Hai câu trả cùng số lượt xem theo user khi mỗi relationship `VIEWED` tương ứng một lượt cần đếm. Nếu dữ liệu cho phép nhiều cạnh `VIEWED` tới cùng một product nhưng nghiệp vụ muốn **số sản phẩm khác nhau**, cần `count(DISTINCT p)`. Đổi `collect` thành `count` làm giảm nhu cầu giữ danh sách node, nhưng aggregation vẫn phải duy trì trạng thái theo nhóm.

### 6.3. Dấu hiệu ước lượng cardinality sai

Nếu `Estimated Rows` rất nhỏ mà `Rows` thực tế rất lớn tại một `Expand` hoặc join, planner có thể chọn chiến lược kém hiệu quả vì thống kê hoặc mô hình ước lượng chưa phản ánh dữ liệu:

- Đầu vào có các node “hub” với degree cao bất thường.
- Predicate khó ước lượng hoặc phân bố giá trị property bị lệch.
- Không chỉ rõ label và relationship type, khiến planner kém thông tin.
- Có index nhưng predicate không dùng được index, hoặc index chưa phù hợp với mẫu truy vấn.

Đừng hiểu mọi chênh lệch `Estimated Rows` và `Rows` là lỗi của Neo4j. Đây là hai loại thông tin khác nhau, và planner phải ước lượng trước khi chạy. Lần theo **toán tử đầu tiên có độ lệch tăng mạnh**, rồi kiểm tra dữ liệu/mô hình/index/tham số tương ứng.

### 6.4. Checklist các phép có thể phình trung gian

| Mẫu truy vấn / operator | Vì sao có thể đắt | Câu hỏi tối ưu |
| --- | --- | --- |
| `CartesianProduct` / join hai tập rộng | Nhân tổ hợp dòng | Có điều kiện nối/relationship thực sự không? |
| `Expand(All)` nhiều hop | Fan-out tăng theo mỗi bước và degree | Có thể bắt đầu từ node chọn lọc hơn, giới hạn hop/type không? |
| Variable-length pattern không giới hạn | Không gian path có thể rất lớn | Có upper bound nghiệp vụ? Có cần toàn bộ path không? |
| `EagerAggregation`, `Distinct` | Cần giữ trạng thái nhóm/khử trùng | Đầu vào có thể giảm trước không, chỉ cần count thay vì collect không? |
| `Sort`, `Top` | Xếp hạng trên tập ứng viên | Có `LIMIT`, index order, hoặc điều kiện lọc sớm không? |
| `UNWIND` danh sách lớn + match lặp | Mỗi item có thể kích hoạt quét/seek | Có thể batch, giảm item hoặc thay đổi cách lookup không? |
| `OPTIONAL MATCH` nhiều nhánh | Có thể tạo nhiều tổ hợp khi mỗi nhánh trả nhiều hàng | Có đang nhân số quan hệ giữa các nhánh độc lập không? |

**Chú ý:** đặt `LIMIT` cuối cùng có thể giảm kết quả truyền về client nhưng **không chắc** giảm các thao tác ở phía trước. Ưu tiên làm nhỏ dữ liệu tại chính chỗ nó bắt đầu phình ra.

## 7. Bài thực hành có thể chạy trong database thử nghiệm

Để quan sát rõ tác động, tạo một lượng nhỏ dữ liệu demo. Chỉ chạy trên **database thử nghiệm**; không dùng các nhãn demo này để mô phỏng môi trường production đang có dữ liệu thật.

### 7.1. Tạo dữ liệu mẫu idempotent

```cypher
CREATE CONSTRAINT demo_user_id_unique IF NOT EXISTS
FOR (u:DemoUser)
REQUIRE u.id IS UNIQUE;
```

```cypher
CREATE CONSTRAINT demo_product_id_unique IF NOT EXISTS
FOR (p:DemoProduct)
REQUIRE p.id IS UNIQUE;
```

```cypher
UNWIND range(1, 120) AS id
MERGE (u:DemoUser {id: id})
ON CREATE SET u.active = (id % 2 = 0);
```

```cypher
UNWIND range(1, 60) AS id
MERGE (p:DemoProduct {id: id})
ON CREATE SET p.price = id * 10000;
```

```cypher
MATCH (u:DemoUser {id: 1})
MATCH (p:DemoProduct)
WHERE p.id <= 5
MERGE (u)-[:VIEWED]->(p);
```

Nếu database demo ban đầu chưa chứa các label này, tập mẫu có 120 `DemoUser`, 60 `DemoProduct` và 5 relationship `VIEWED`. Dùng `MERGE` và uniqueness constraint để việc chạy lại không tự tạo thêm bản sao tương ứng.

### 7.2. Quan sát Cartesian product

```cypher
PROFILE
MATCH (u:DemoUser), (p:DemoProduct)
RETURN sum(u.id + p.id) AS checksum;
```

Phần `RETURN` chỉ có **một dòng tổng hợp**, nhưng việc kết hợp hai tập theo yêu cầu có thể đi qua **120 × 60 = 7.200 cặp** nếu chỉ có dữ liệu demo. Hãy tìm `CartesianProduct` và `Rows` của operator đó; số cuối không thể hiện toàn bộ chi phí trung gian.

Đối chiếu với truy vấn có relationship cụ thể:

```cypher
PROFILE
MATCH (u:DemoUser {id: 1})-[:VIEWED]->(p:DemoProduct)
RETURN u.id AS userId, p.id AS productId;
```

Truy vấn thứ hai chỉ tìm năm quan hệ theo dữ liệu demo. Hai câu **khác yêu cầu nghiệp vụ**, nên so sánh để hiểu cách biểu diễn điều kiện quan hệ ảnh hưởng tới cardinality, không phải thay thế máy móc mọi cross join.

### 7.3. Quan sát `Sort` và `Top`

```cypher
PROFILE
MATCH (p:DemoProduct)
RETURN p.id AS productId, p.price AS price
ORDER BY p.price DESC;
```

Sau đó:

```cypher
PROFILE
MATCH (p:DemoProduct)
RETURN p.id AS productId, p.price AS price
ORDER BY p.price DESC
LIMIT 5;
```

Ghi lại toán tử `Sort`/`Top` (hoặc phương án khác mà planner thực tế chọn), `Rows`, `DB Hits` và `Memory (Bytes)`. Số liệu trên tập nhỏ chỉ phục vụ minh họa; hãy nhân rộng có kiểm soát nếu cần nghiên cứu hành vi dữ liệu lớn.

### 7.4. Quan sát tình huống có khả năng cần `Eager`

```cypher
EXPLAIN
MATCH (p:DemoProduct)
CREATE (:DemoProduct {id: p.id + 1000});
```

Tìm `Eager` trong plan nếu planner chèn rào chắn. **Không chạy `PROFILE` ở bước này khi chưa chủ động cho phép thay đổi dữ liệu**; `EXPLAIN` đủ để xem kế hoạch dự kiến. Nếu phiên bản/runtime không hiển thị `Eager`, ghi nhận khác biệt thay vì ép khẳng định nó phải có.

### 7.5. Đo tập trung gian do aggregation

```cypher
PROFILE
MATCH (u:DemoUser)
OPTIONAL MATCH (u)-[:VIEWED]->(p:DemoProduct)
RETURN u.id AS userId, count(p) AS viewedCount;
```

Đối chiếu với:

```cypher
PROFILE
MATCH (u:DemoUser)
OPTIONAL MATCH (u)-[:VIEWED]->(p:DemoProduct)
WITH u, collect(p) AS products
RETURN u.id AS userId, size(products) AS viewedCount;
```

Cả hai có thể biểu diễn cùng số lượng trong dữ liệu demo, nhưng cách giữ giá trị trung gian khác nhau. Tìm operator aggregation, `Rows` và bộ nhớ được báo cáo. Lưu ý `collect(null)` không thêm null vào danh sách trong ngữ nghĩa Cypher; với `OPTIONAL MATCH` không có product, kết quả đếm kỳ vọng là 0.

## 8. Quy trình tối ưu từ bằng chứng

Một vòng cải thiện an toàn có thể thực hiện như sau:

1. **Xác định truy vấn và mục tiêu**: đầu vào, kết quả nghiệp vụ, database, bản Neo4j, dữ liệu/độ lớn, các tham số điển hình; lưu lại query và kết quả mẫu.
2. **Chạy `EXPLAIN`**: đọc plan trước, phát hiện những toán tử có nguy cơ lớn; không chạy `PROFILE` cho truy vấn ghi nếu chưa chuẩn bị.
3. **Chạy `PROFILE` an toàn**: dùng truy vấn đọc hoặc bản thử nghiệm có kiểm soát; ghi `Rows`, `Estimated Rows`, `DB Hits`, memory, thời gian, toán tử đặc biệt.
4. **Khoanh vùng nguyên nhân**: mỗi lần chọn một vấn đề (ví dụ cross join hoặc `Sort` lớn). Xác định tại sao dữ liệu đi vào toán tử đó lớn.
5. **Thay đổi có căn cứ**: thêm điều kiện quan hệ thực, lọc sớm, áp dụng index phù hợp, chỉ giữ những trường cần thiết, giảm aggregation/list hoặc chia lô khi nghiệp vụ cho phép.
6. **Xác minh tính đúng**: so sánh kết quả và tính nhất quán trước/sau, kể cả trường hợp dữ liệu rỗng, trùng, NULL và phân trang.
7. **Đo lại công bằng**: dùng cùng dữ liệu, tham số, điều kiện cache và tải tương đương; so cả tổng DB Hits và các điểm phình intermediate thay vì chỉ thời gian chạy một lần.

Ví dụ ghi nhận trước/sau:

| Chỉ số | Trước | Sau | Đánh giá |
| --- | ---: | ---: | --- |
| Rows tại điểm nhân lớn nhất | 1.000.000 | 4.000 | Giảm tổ hợp trung gian |
| Tổng DB Hits | 2.500.000 | 15.000 | Ít công việc tầng lưu trữ |
| Peak memory (nếu được báo cáo) | 180 MB | 12 MB | Bớt áp lực bộ nhớ |
| Dòng kết quả đúng nghiệp vụ | 10 | 10 | **Phải giữ đúng nội dung**, không chỉ số lượng |

Các con số trong bảng hoàn toàn **giả định để minh họa cách báo cáo**, không phải benchmark Neo4j hay kỳ vọng cho một hệ thống cụ thể.

## 9. Phân tích plan từ Java Driver và Spring Data Neo4j

Khi triển khai Java, có thể truy cập kế hoạch qua `ResultSummary`. Trong **Neo4j Java Driver 6.2 trở lên**, tài liệu hiện hành cung cấp `queryPlan()` và `queryProfile()`; trong một số phiên bản cũ hơn API tương ứng là `plan()` và `profile()`. Cần dùng API đúng với **phiên bản dependency thực tế**.

Ví dụ Java Driver 6.2+ với truy vấn đọc có `PROFILE`:

```java
import java.util.Map;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.QueryConfig;

public class InspectCypherPlan {
    public static void main(String[] args) {
        try (Driver driver = GraphDatabase.driver(
                "neo4j://localhost:7687",
                AuthTokens.basic("neo4j", "change-me"))) {

            var outcome = driver.executableQuery("""
                PROFILE
                MATCH (u:DemoUser {id: $id})-[:VIEWED]->(p:DemoProduct)
                WHERE p.price >= $minPrice
                RETURN p.id AS productId, p.price AS price
                ORDER BY p.price DESC
                LIMIT 5
                """)
                .withParameters(Map.of("id", 1, "minPrice", 10000))
                .withConfig(
                    QueryConfig.builder().withDatabase("neo4j").build()
                )
                .execute();

            System.out.println("Số dòng kết quả: " + outcome.records().size());
            outcome.summary().queryProfile().ifPresentOrElse(
                profile -> System.out.println(
                    profile.arguments().get("string-representation")
                ),
                () -> System.out.println("Không có thông tin PROFILE")
            );
        }
    }
}
```

Đoạn mã dùng password minh họa; trong ứng dụng thật hãy lấy thông tin đăng nhập qua cấu hình/secrets. `PROFILE` chạy query thật, ở đây chỉ đọc dữ liệu. Đối với `EXPLAIN`, dùng prefix `EXPLAIN` và `summary().queryPlan()` thay vì `queryProfile()`. Với Driver phiên bản cũ, điều chỉnh các method theo API tương ứng.

Trong **Spring Data Neo4j**, các repository/`Neo4jClient` thuận tiện cho nghiệp vụ, nhưng lời gọi repository thông thường không hiển thị trực tiếp cây operator. Khi cần điều tra hiệu năng:

- Lấy Cypher thực tế phát sinh từ ứng dụng (và bộ tham số đại diện), tránh chỉ đo query “ước đoán” khác với query runtime.
- Chạy `EXPLAIN`/`PROFILE` ở môi trường và database phù hợp hoặc dùng Driver để nhận `ResultSummary`.
- Đối chiếu relationship mapping, số hop, độ chọn lọc property, index/constraint và sự xuất hiện của `CartesianProduct`, `Eager` hoặc `Sort`.
- Không chạy `PROFILE` truy vấn ghi để chẩn đoán trực tiếp trên dữ liệu quan trọng nếu chưa chủ động chấp nhận thao tác ghi đó.

## 10. Những kết luận sai thường gặp

| Kết luận vội vàng | Điều cần kiểm tra |
| --- | --- |
| “Có `CartesianProduct` là luôn sai.” | Nghiệp vụ có yêu cầu mọi tổ hợp hay không; kích thước thực tế của hai nhánh |
| “Thêm `LIMIT 10` chắc chắn chỉ xử lý 10 dòng.” | `Sort`/aggregation/expansion đã xử lý bao nhiêu dòng trước `LIMIT` |
| “`Eager` là lỗi, cần xóa.” | Có xung đột đọc/ghi buộc phải chặn để bảo toàn ngữ nghĩa không |
| “`WITH` luôn materialize tập trung gian.” | Plan có operator chặn thực tế nào, và nó giữ bao nhiêu dữ liệu |
| “Kết quả 1 dòng thì truy vấn nhẹ.” | `Rows` ở nhánh trước aggregate/`ProduceResults` |
| “Có index thì `Sort` tự biến mất.” | Index có phù hợp điều kiện và thứ tự `ORDER BY` không; planner chọn gì |
| “`DB Hits` bằng số dòng.” | Đây là thước đo lượt truy cập dữ liệu, không phải cardinality |
| “`Estimated Rows` là số bản ghi đã xử lý.” | Chỉ `PROFILE` mới cho `Rows` thực tế |
| “Bộ nhớ của query bằng tổng cột `Memory (Bytes)`.” | Cần xem đỉnh bộ nhớ toàn query; operator peak không cộng trực tiếp |
| “`PROFILE` chỉ mô phỏng câu lệnh.” | `PROFILE` thực thi thật, bao gồm các cập nhật của query ghi |
| “`DISTINCT` cuối query sẽ loại bỏ chi phí mở rộng trước đó.” | Chi phí sinh tập lớn đã xảy ra; `DISTINCT` có thể tạo thêm bước giữ trạng thái |

## 11. Tự kiểm tra

1. Một query `MATCH (a:A), (b:B) RETURN count(*)` trả về một số duy nhất. Nếu `A` có 5.000 node và `B` có 2.000 node, plan có thể phải xử lý bao nhiêu tổ hợp? Có cần trả từng cặp mới mắc chi phí đó không?
2. Vì sao `Eager` có thể xuất hiện ở câu Cypher vừa đọc vừa cập nhật cùng nhóm node? Khi nào chia transaction thành nhiều batch là **không phù hợp**?
3. Sự khác biệt giữa `Sort` và `Top` là gì? Vì sao `LIMIT` không nhất thiết giảm số lần đọc dữ liệu?
4. Nếu `Estimated Rows` là 10 nhưng `Rows` là 800.000 tại `Expand(All)`, nên điều tra vị trí nào trong graph và truy vấn?
5. Cần đối chiếu những chỉ số và điều kiện nào để kết luận thay đổi Cypher đã cải thiện hiệu năng **và** không làm sai kết quả?

**Tiêu chí đạt:** người học mở và đọc được plan bằng `EXPLAIN`/`PROFILE`; xác định nơi số dòng phình to; giải thích đúng vai trò của `CartesianProduct`, `Eager` và `Sort`; đề xuất cách sửa có căn cứ; và xác minh tính đúng cùng mức tiêu thụ tài nguyên sau khi tối ưu.

## Tài liệu tham khảo chính thức

- [Neo4j Cypher Manual — Understanding query plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): cấu trúc plan, `Estimated Rows`, `Rows`, `DB Hits`, memory và cách đọc operator.
- [Neo4j Cypher Manual — Operators in detail](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/operators/operators-detail/): `CartesianProduct`, `Eager`, `Sort`, `Top`, aggregation và traversal.
- [Neo4j Cypher Manual — Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/query-tuning/): planner, runtime, tối ưu và các tùy chọn lập kế hoạch.
- [Neo4j Cypher Manual — Basic query tuning example](https://neo4j.com/docs/cypher-manual/current/appendix/tutorials/basic-query-tuning/): ví dụ minh họa thay đổi query và đọc plan.
- [Neo4j Java Driver Manual — Explore the query execution summary](https://neo4j.com/docs/java-manual/current/result-summary/): `ResultSummary`, `queryPlan()`/`queryProfile()` và kết quả profiling trong Java.
