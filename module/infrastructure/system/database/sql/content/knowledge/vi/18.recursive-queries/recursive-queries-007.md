# Phát hiện chu trình và tránh lặp vô hạn

Truy vấn đệ quy trong SQL rất hữu ích khi dữ liệu có cấu trúc **phân cấp** hoặc **đồ thị**: tìm toàn bộ nhân viên cấp dưới một quản lý, liệt kê danh mục con, duyệt các phụ thuộc của một gói phần mềm, lần theo quan hệ giới thiệu, hoặc xác định những nút có thể đi tới từ một nút ban đầu.

Tuy nhiên, dữ liệu không phải lúc nào cũng là một cây hoàn hảo. Một danh mục có thể vô tình trỏ về danh mục cha; một nhân viên có thể được gán quản lý theo vòng; hoặc một đồ thị hoàn toàn hợp lệ về nghiệp vụ có thể chứa đường đi quay lại nút trước đó. Nếu mỗi bước đệ quy lại sinh thêm hàng và không có điều kiện phát hiện chu trình, truy vấn có thể **chạy mãi, tiêu tốn tài nguyên hoặc bị hệ quản trị hủy do vượt giới hạn**.

Bài học thuộc **Database SQL → Truy vấn đệ quy → Phát hiện chu trình và tránh lặp vô hạn**. Nội dung giải thích cách nhận diện chu trình theo **đường đi đang duyệt**, cách dùng mảng ghi lại nút đã đi qua, cách dùng mệnh đề `CYCLE` của PostgreSQL, vai trò và giới hạn của `UNION`, cách áp đặt giới hạn độ sâu như một lớp bảo vệ, cùng những khác biệt cần nhớ giữa các hệ quản trị SQL.

Ví dụ thực hành chủ yếu dùng **PostgreSQL**. Các đoạn cố ý mô tả truy vấn nguy hiểm được đánh dấu rõ và không cần chạy.

## 1. Từ truy vấn đệ quy đến nguy cơ lặp vô hạn

Một CTE đệ quy dùng cú pháp `WITH RECURSIVE` trong PostgreSQL:

```sql
WITH RECURSIVE cte_name AS (
    -- Phần khởi tạo (anchor)
    SELECT ...

    UNION ALL

    -- Phần đệ quy: tham chiếu cte_name
    SELECT ...
    FROM some_table AS t
    JOIN cte_name AS r
      ON ...
    WHERE ...
)
SELECT ...
FROM cte_name;
```

Hiểu theo ba phần:

1. **Anchor:** tạo các hàng bắt đầu, ví dụ nút gốc `1`.
2. **Recursive term:** từ các hàng đã có ở vòng trước, tìm các hàng tiếp theo.
3. **Điều kiện dừng:** không còn hàng mới để tiếp tục, hoặc một quy tắc có chủ đích ngăn mở rộng tiếp.

Không có `WHERE` trong phần đệ quy không nhất thiết gây vô hạn; nếu quan hệ nguồn có điểm cuối, cuối cùng sẽ không còn hàng mới. Nhưng nếu tồn tại một vòng có thể đi mãi, `UNION ALL` liên tục tạo những lần ghé thăm mới.

### Chu trình là gì?

Xem mỗi bản ghi quan hệ như một cạnh có hướng `from_node → to_node`:

```text
1 → 2 → 4 → 5
    ↑       │
    └───────┘
```

Từ nút 2 có thể đi:

```text
2 → 4 → 5 → 2 → 4 → 5 → 2 → ...
```

Đường đi đã quay lại nút `2`. Đó là một **chu trình** (*cycle*).

Một dạng đặc biệt là **self-loop**:

```text
6 → 6 → 6 → ...
```

Cũng có thể gặp chu trình gồm nhiều nút hơn. Nếu phần đệ quy cứ tiếp tục đi theo cạnh đã tạo chu trình, số bước không có điểm kết thúc tự nhiên.

### Chu trình khác với đi tới cùng nút qua hai đường khác nhau

Xem cấu trúc:

```text
    1
   / \
  2   3
   \ /
    4
```

Hai đường `1→2→4` và `1→3→4` gặp nhau ở nút `4`. Đây là **hội tụ** (*convergence*), không phải chu trình trên từng đường, vì chưa đường nào quay lại nút đã xuất hiện trước đó trong **chính đường đó**.

Sự phân biệt rất quan trọng:

- **Phát hiện chu trình theo đường đi:** nút kế tiếp đã nằm trong chuỗi nút của đường hiện tại chưa?
- **Khử trùng toàn cục:** một nút đã từng xuất hiện ở bất cứ đường đi nào chưa?

Hai câu hỏi dùng trong những bài toán khác nhau. Nếu cần liệt kê tất cả **đường đi đơn** (*simple paths*, không lặp lại nút), không được loại bỏ một đường hợp lệ chỉ vì một đường khác cũng đi qua nút đó.

## 2. Tạo đồ thị thực hành có chu trình và đường hội tụ

Trong PostgreSQL, hãy tạo **bảng tạm** sau trong một phiên kết nối thực hành. Bảng tạm tồn tại trong phiên; nếu đã có bảng cùng tên, hãy dùng phiên mới hoặc chọn tên khác trước khi chạy lại.

```sql
CREATE TEMP TABLE graph_edges_228 (
    edge_id   INTEGER PRIMARY KEY,
    from_node INTEGER NOT NULL,
    to_node   INTEGER NOT NULL
);

INSERT INTO graph_edges_228 (edge_id, from_node, to_node)
VALUES
    (1,  1, 2),
    (2,  1, 3),
    (3,  2, 4),
    (4,  3, 4),
    (5,  4, 5),
    (6,  5, 2),
    (7,  3, 6),
    (8,  6, 6),
    (9,  5, 7),
    (10, 8, 9),
    (11, 9, 8);

SELECT edge_id, from_node, to_node
FROM graph_edges_228
ORDER BY edge_id;
```

Đồ thị có thể hình dung:

```text
         ┌───────────────┐
         │               ▼
         │       1 ──→ 2 ──→ 4 ──→ 5 ──→ 7
         │       │          ▲      │
         │       └──→ 3 ───┘      │
         │            │           │
         └────────────┼───────────┘
                      ▼
                      6 ↺

         8 ──→ 9
         ↑     │
         └─────┘
```

Các đặc điểm có chủ đích:

| Cạnh hoặc đường | Vai trò |
| --- | --- |
| `1→2→4→5→2` | Chu trình ba nút `2,4,5` |
| `6→6` | Chu trình tự quay về chính nút `6` |
| `1→2→4` và `1→3→4` | Hai đường khác nhau đi tới `4`, chưa phải chu trình |
| `5→7` | Nhánh kết thúc bình thường |
| `8→9→8` | Chu trình ở thành phần **không đi tới được từ nút gốc 1** |

Nếu bắt đầu duyệt từ nút 1, có thể đi tới các nút `1,2,3,4,5,6,7`. Hai nút `8,9` không có đường đi từ nút 1 và không xuất hiện trong kết quả duyệt bắt đầu tại 1.

Điều này còn nhắc rằng **không phát hiện chu trình từ một gốc không chứng minh toàn bộ đồ thị không có chu trình**.

## 3. Một truy vấn đệ quy không an toàn trông như thế nào?

Xem cấu trúc minh họa sau:

```sql
-- NGUY HIỂM: KHÔNG CHẠY TRÊN ĐỒ THỊ CÓ CHU TRÌNH.
-- Không có kiểm tra nút đã đi qua và không có giới hạn độ sâu.
--
-- WITH RECURSIVE walk(node_id) AS (
--     SELECT 1
--     UNION ALL
--     SELECT e.to_node
--     FROM walk AS w
--     JOIN graph_edges_228 AS e
--       ON e.from_node = w.node_id
-- )
-- SELECT * FROM walk;
```

Từ 1, truy vấn có thể sinh `2` và `3`; từ 2 sinh 4; từ 4 sinh 5; từ 5 lại sinh 2. Các bước đệ quy tiếp tục lặp lại.

Trong PostgreSQL, đệ quy này không tự nhận diện “đã thấy nút 2 rồi” khi dùng `UNION ALL`. Không nên xem `LIMIT` ở ngoài là biện pháp bảo vệ hoàn chỉnh: việc có thể trả sớm hay không còn phụ thuộc kế hoạch, `ORDER BY`, `JOIN` ngoài, tổng hợp và cách client lấy dữ liệu. Trên nhiều DBMS, một truy vấn như vậy có thể bị giới hạn đệ quy của hệ thống; điều đó là cơ chế bảo vệ, **không phải thuật toán xử lý chu trình đúng**.

**Mục tiêu của giải pháp:** ngay tại bước sinh nút kế tiếp, phải biết nút đó có tạo chu trình trên đường hiện tại không và quyết định **đánh dấu** hoặc **không mở rộng** nó.

## 4. Cách chủ động: lưu đường đi đã duyệt bằng mảng PostgreSQL

Một chiến lược trực quan là giữ thêm một cột `path` chứa các nút đã đi qua trên **đường hiện tại**.

Quy tắc:

1. Anchor từ nút 1 có `path = [1]`.
2. Khi đi từ nút hiện tại `u` sang nút `v`, kiểm tra **`v` đã nằm trong `path` chưa**.
3. Nếu chưa: nối `v` vào cuối `path` và tiếp tục đệ quy.
4. Nếu đã: đây là cạnh **đóng chu trình**; có thể đánh dấu hàng đó và dừng mở rộng đường.

Trong PostgreSQL, có thể dùng:

- `ARRAY[1]::INTEGER[]` để tạo mảng ban đầu.
- `path || next_node` để nối thêm một phần tử.
- `next_node = ANY(path)` để kiểm tra phần tử đã có trong mảng.
- `depth + 1` để theo dõi độ sâu.

### 4.1. Vừa phát hiện vừa đánh dấu chu trình

```sql
WITH RECURSIVE walk(node_id, depth, path, is_cycle) AS (
    SELECT
        1::INTEGER             AS node_id,
        0::INTEGER             AS depth,
        ARRAY[1]::INTEGER[]    AS path,
        FALSE                  AS is_cycle

    UNION ALL

    SELECT
        e.to_node,
        w.depth + 1,
        w.path || e.to_node,
        e.to_node = ANY(w.path) AS is_cycle
    FROM walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
    WHERE NOT w.is_cycle
)
SELECT node_id, depth, path, is_cycle
FROM walk
ORDER BY path;
```

**Phần quan trọng nằm ở hai chỗ:**

```sql
e.to_node = ANY(w.path)
```

nhận diện việc nút kế tiếp đã xuất hiện trong đường trước đó, còn:

```sql
WHERE NOT w.is_cycle
```

ngăn **mở rộng từ một hàng đã được đánh dấu chu trình**. Một hàng đóng chu trình vẫn được xuất ra để phục vụ chẩn đoán, nhưng không tạo thêm hậu duệ.

Một số đường tiêu biểu:

| `path` | `is_cycle` | Diễn giải |
| --- | --- | --- |
| `{1}` | false | Bắt đầu ở gốc |
| `{1,2,4,5,2}` | true | Quay lại nút 2 |
| `{1,3,6,6}` | true | Self-loop tại nút 6 |
| `{1,3,4,5,2}` | false | Chưa lặp nút trên đường này, dù nút 2 có ở đường khác |
| `{1,3,4,5,2,4}` | true | Quay lại nút 4 trong chính đường hiện tại |
| `{1,2,4,5,7}` | false | Đường kết thúc bình thường |

Lưu ý: kết quả có thể có **nhiều hàng mang cùng `node_id`** nếu những đường khác nhau dẫn tới nút đó. Ví dụ nút 4 có đường `1→2→4` và `1→3→4`; cả hai có thể được giữ vì đây là hai đường riêng.

### 4.2. Vì sao phải kiểm tra đường của từng hàng, không dùng một danh sách toàn cục?

Giả sử một đường đã tới nút 4 qua `1→2→4`. Sau đó đường khác `1→3→4` đi tới 4. Nếu mục tiêu là liệt kê **tất cả đường đi**, đường thứ hai vẫn hợp lệ và không được đánh dấu chu trình chỉ vì nút 4 từng xuất hiện ở một nhánh khác.

Điều kiện:

```sql
e.to_node = ANY(w.path)
```

được tính bằng `w.path` của **hàng đang mở rộng**, do đó phản ánh đúng câu hỏi “đường này đã gặp nút đó chưa?”.

### 4.3. Dùng cột trạng thái để báo lỗi dữ liệu

Nếu bài toán quản lý danh mục yêu cầu cấu trúc thực sự phải là cây, một hàng `is_cycle = TRUE` là dấu hiệu dữ liệu sai cần được điều tra.

```sql
WITH RECURSIVE walk(node_id, depth, path, is_cycle) AS (
    SELECT 1, 0, ARRAY[1]::INTEGER[], FALSE
    UNION ALL
    SELECT
        e.to_node,
        w.depth + 1,
        w.path || e.to_node,
        e.to_node = ANY(w.path)
    FROM walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
    WHERE NOT w.is_cycle
)
SELECT node_id, depth, path
FROM walk
WHERE is_cycle
ORDER BY path;
```

Truy vấn trên phát hiện các đường từ nút 1 đóng chu trình, chẳng hạn `{1,2,4,5,2}` và `{1,3,6,6}`.

Đừng hiểu “dừng khi gặp chu trình” là “chu trình đã được sửa”. CTE chỉ tránh đi mãi và cung cấp bằng chứng để người sở hữu dữ liệu xử lý quan hệ sai, nếu chu trình là không hợp lệ theo nghiệp vụ.

## 5. Biến thể: loại bỏ cạnh gây chu trình ngay trước khi sinh hàng

Nếu bạn chỉ muốn duyệt các đường không lặp nút và **không cần hiển thị cạnh đóng chu trình**, có thể lọc ở phần recursive term:

```sql
WITH RECURSIVE simple_paths(node_id, depth, path) AS (
    SELECT
        1::INTEGER,
        0::INTEGER,
        ARRAY[1]::INTEGER[]

    UNION ALL

    SELECT
        e.to_node,
        s.depth + 1,
        s.path || e.to_node
    FROM simple_paths AS s
    JOIN graph_edges_228 AS e
      ON e.from_node = s.node_id
    WHERE NOT (e.to_node = ANY(s.path))
)
SELECT node_id, depth, path
FROM simple_paths
ORDER BY path;
```

Khác biệt chính:

| Chiến lược | Hàng đóng chu trình | Có tiếp tục mở rộng chu trình? | Dùng khi |
| --- | --- | --- | --- |
| Tạo `is_cycle` rồi `WHERE NOT w.is_cycle` ở vòng kế tiếp | Có, mang `is_cycle = TRUE` | Không | Muốn **phát hiện và báo** đường tạo chu trình |
| `WHERE NOT (e.to_node = ANY(s.path))` ngay khi mở rộng | Không | Không | Muốn **chỉ lấy các đường đơn** không lặp nút |

Cả hai đều tránh lặp vô hạn khi `node_id` là định danh xác định và phép kiểm tra đường đi được viết đúng.

### 5.1. Trường hợp node_id có thể NULL

Trong bảng mẫu, `from_node` và `to_node` có ràng buộc `NOT NULL`. Điều này giúp biểu thức:

```sql
e.to_node = ANY(s.path)
```

hoạt động theo kết quả TRUE/FALSE rõ ràng cho các nút. Nếu định danh nút có thể `NULL`, logic ba giá trị có thể khiến phép kiểm tra là UNKNOWN; `NOT UNKNOWN` vẫn UNKNOWN, và `WHERE` sẽ loại cạnh theo một cách không hẳn phản ánh ý nghĩa nghiệp vụ.

Với cấu trúc cây/đồ thị, nên dùng **định danh nút không NULL** khi có thể. Nếu cần hỗ trợ giá trị thiếu, phải định nghĩa rõ có coi hai `NULL` là cùng nút hay không và chọn cách so sánh thích hợp.

### 5.2. Mảng đường đi không phải vô hạn

Theo dõi `path` làm tăng chiều dài hàng ở mỗi bước. Với đồ thị rất sâu hoặc nhiều nhánh, số đường đơn có thể cực lớn dù không có chu trình. Đây là chi phí cần cân nhắc; phát hiện chu trình giải quyết **lặp vô hạn do quay lại nút**, nhưng không bảo đảm truy vấn luôn nhỏ hoặc nhanh.

## 6. Cách gọn hơn trong PostgreSQL: mệnh đề CYCLE

Từ **PostgreSQL 14**, truy vấn CTE đệ quy hỗ trợ mệnh đề `CYCLE` để hệ quản trị tự theo dõi đường đi và đánh dấu khi gặp lại giá trị khóa chu trình.

Ví dụ cùng đồ thị:

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER

    UNION ALL

    SELECT e.to_node, w.depth + 1
    FROM walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
)
CYCLE node_id SET is_cycle USING path_nodes
SELECT node_id, depth, is_cycle, path_nodes
FROM walk
ORDER BY path_nodes;
```

Cú pháp cốt lõi:

```sql
CYCLE node_id SET is_cycle USING path_nodes
```

Ý nghĩa:

- `node_id`: cột làm **khóa phát hiện chu trình**.
- `is_cycle`: cột đánh dấu **đã quay lại giá trị khóa có trên đường hiện tại hay chưa**.
- `path_nodes`: cột đường đi được hệ quản trị bổ sung để theo dõi chuỗi giá trị khóa.

PostgreSQL tự thêm logic theo dõi đường đi và ngăn mở rộng vô hạn từ hàng đã xác định là chu trình. Giống cách tự viết mảng, **hàng đóng chu trình có thể xuất hiện** với `is_cycle = TRUE` để bạn nhận diện, nhưng không bị mở rộng mãi.

### 6.1. Chỉ lấy hàng không đóng chu trình

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER
    UNION ALL
    SELECT e.to_node, w.depth + 1
    FROM walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
)
CYCLE node_id SET is_cycle USING path_nodes
SELECT node_id, depth
FROM walk
WHERE NOT is_cycle
ORDER BY depth, node_id;
```

Điều kiện `WHERE NOT is_cycle` ở truy vấn cuối **loại khỏi kết quả hiển thị** những hàng đóng chu trình. Nó không phải điều kiện duy nhất bảo vệ đệ quy: cơ chế `CYCLE` đã làm việc ngăn tiếp tục mở rộng chu trình bên trong CTE.

### 6.2. Chọn khóa chu trình đúng với danh tính trạng thái

Giả sử dữ liệu đa tenant dùng cặp `(tenant_id, node_id)`. Hai nút có cùng `node_id` nhưng thuộc hai tenant khác nhau không nhất thiết là một nút. Khi đó, trong PostgreSQL có thể chỉ định nhiều cột:

```sql
-- Minh họa cú pháp PostgreSQL cho khóa phát hiện chu trình ghép
CYCLE tenant_id, node_id SET is_cycle USING path_nodes
```

Điều kiện cơ bản: **khóa dùng phát hiện chu trình phải nhận diện đúng một trạng thái mà việc quay lại trạng thái đó được xem là lặp**.

Nếu một bản ghi có thể được duyệt ở nhiều **trạng thái hợp lệ** khác nhau (ví dụ cùng vị trí nhưng khác chế độ di chuyển), chỉ dùng `node_id` có thể dừng quá sớm. Ngược lại, đưa cả `depth` vào khóa chu trình là sai cho mục tiêu phát hiện lặp theo nút, vì mỗi lần quay lại nút ở độ sâu mới có `depth` khác, nên có thể không bao giờ bị đánh dấu như cùng khóa.

### 6.3. Chọn giữa CYCLE và mảng tự quản

| Tiêu chí | `CYCLE` của PostgreSQL | Mảng đường đi và `ANY` |
| --- | --- | --- |
| Độ gọn | Gọn, thể hiện ý định trực tiếp | Cần tự khai báo `path` và `is_cycle` |
| Đánh dấu chu trình | Tự tạo cột flag | Tự viết logic so sánh |
| Tùy biến biểu diễn đường đi | Có những quy tắc do DBMS quyết định | Chủ động chọn kiểu và cách lưu |
| Tính di chuyển | Không có cú pháp y hệt trên mọi DBMS | Mảng PostgreSQL cũng không phổ quát; ý tưởng có thể chuyển sang kiểu khác |
| Phát hiện lặp theo nhiều cột | Có thể liệt kê nhiều cột khóa | Có thể lưu khóa ghép dưới dạng cấu trúc tương ứng |
| Độ phức tạp truy vấn | Vẫn phụ thuộc số đường/hàng được sinh | Cũng phụ thuộc độ sâu và số đường |

`CYCLE` làm cách viết rõ ràng hơn, nhưng **không thay thế việc chọn gốc, chọn khóa danh tính, đặt quy tắc nghiệp vụ và kiểm soát khối lượng kết quả**.

## 7. CYCLE so với UNION và UNION ALL

Một lỗi tư duy khác là: “Đổi `UNION ALL` sang `UNION` thì tự động hết mọi chu trình.”

Điều này **chỉ đúng trong một số dạng truy vấn đặc biệt**.

### 7.1. Khi chỉ cần tập nút có thể đi tới: UNION có thể dừng

`UNION` (không có `ALL`) loại các hàng trùng nhau trong kết quả đệ quy. Nếu CTE chỉ giữ **một cột node_id**, số nút hữu hạn và mỗi nút chỉ cần xuất hiện một lần, có thể viết:

```sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 1::INTEGER

    UNION

    SELECT e.to_node
    FROM reachable AS r
    JOIN graph_edges_228 AS e
      ON e.from_node = r.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
```

Kết quả: các nút **1, 2, 3, 4, 5, 6, 7** — mỗi nút một lần.

Tại sao kết thúc dù có `2→4→5→2` và `6→6`?

- Khi vòng đệ quy sinh lại một hàng `(node_id=2)` đã có, `UNION` loại bản sao.
- Khi không còn **nút mới** nào được thêm, không còn hàng để mở rộng và truy vấn dừng.
- Số lượng trạng thái `node_id` trong đồ thị là hữu hạn.

Cách này hợp lý nếu mục tiêu là **reachability**: xác định các nút nào đi tới được từ gốc, không cần danh sách từng đường hoặc thông tin phát hiện cụ thể chu trình.

### 7.2. UNION không bảo vệ nếu hàng còn chứa depth hoặc path thay đổi

Xét ví dụ có giới hạn độ sâu để chạy an toàn:

```sql
WITH RECURSIVE visit(node_id, depth) AS (
    SELECT 1::INTEGER, 0::INTEGER

    UNION

    SELECT e.to_node, v.depth + 1
    FROM visit AS v
    JOIN graph_edges_228 AS e
      ON e.from_node = v.node_id
    WHERE v.depth < 5
)
SELECT node_id, depth
FROM visit
ORDER BY depth, node_id;
```

Mặc dù dùng `UNION`, cùng một `node_id` ở **các độ sâu khác nhau** là các hàng khác nhau:

```text
(2, 1)  khác  (2, 4)
(4, 2)  khác  (4, 5)
```

Nếu bỏ điều kiện `WHERE v.depth < 5` trong ví dụ này, chu trình có thể tạo các hàng mới với `depth` ngày càng lớn, khiến `UNION` không loại được chúng chỉ dựa trên so sánh toàn hàng.

Cột `path` còn rõ hơn: mỗi lần đi quanh vòng sẽ tạo một mảng dài hơn, nên toàn bộ hàng khác nhau. Khi cần giữ đường đi hoặc độ sâu, hãy dùng **logic phát hiện chu trình thực sự**.

### 7.3. UNION có thể làm mất đường đi hợp lệ

Với hai đường `1→2→4` và `1→3→4`, truy vấn chỉ giữ `node_id` và dùng `UNION` sẽ trả nút `4` một lần. Điều đó đúng nếu bạn hỏi “4 có đi tới được không?”, nhưng không đủ nếu bạn hỏi “có những đường nào đi từ 1 đến 4?”.

**Chọn chiến lược theo bài toán:**

| Mục tiêu | Cách thường hợp lý |
| --- | --- |
| Danh sách các nút đạt được, không cần đường đi | CTE `UNION` chỉ chứa định danh nút |
| Liệt kê mọi đường không lặp nút | `UNION ALL` + cột `path` + kiểm tra nút đã có trên đường |
| Chẩn đoán những cạnh tạo chu trình | `CYCLE` hoặc cột `is_cycle` chủ động |
| Chỉ cần biết có ít nhất một chu trình trong miền duyệt | Dùng flag chu trình và rút ra kết quả bằng tổng hợp/`EXISTS` |
| Duyệt đồ thị rất lớn | Cần chiến lược riêng về khối lượng kết quả, index, giới hạn và mô hình dữ liệu |

## 8. Giới hạn độ sâu là một lớp bảo vệ, không phải bằng chứng hết chu trình

Ngay cả khi có cơ chế phát hiện chu trình, một truy vấn có thể mở rộng quá sâu hoặc sinh quá nhiều đường hợp lệ. Một rào chắn thực tế là **giới hạn độ sâu**.

```sql
WITH RECURSIVE limited_walk(node_id, depth, path) AS (
    SELECT 1::INTEGER, 0::INTEGER, ARRAY[1]::INTEGER[]

    UNION ALL

    SELECT e.to_node,
           w.depth + 1,
           w.path || e.to_node
    FROM limited_walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
    WHERE w.depth < 4
      AND NOT (e.to_node = ANY(w.path))
)
SELECT node_id, depth, path
FROM limited_walk
ORDER BY depth, path;
```

Cách hiểu `WHERE w.depth < 4`:

- Anchor ở độ sâu `0`.
- Hàng ở độ sâu 0, 1, 2, 3 có thể sinh hàng kế tiếp.
- Hàng sinh ra ở độ sâu **4** không còn được mở rộng.
- Kết quả có độ sâu từ 0 đến **4 cạnh** kể từ gốc.

Giới hạn này là một **hợp đồng kết quả**: truy vấn chỉ duyệt tối đa bốn bước. Nó có thể bỏ sót những nút hợp lệ ở độ sâu lớn hơn.

### Vì sao không chỉ dùng giới hạn độ sâu?

Một chu trình có chiều dài 3 sẽ được “cắt” ở độ sâu 4, nhưng truy vấn không chỉ ra vì sao một đường dừng: do đến lá, do gặp chu trình hay do chạm giới hạn. Nếu chỉ có giới hạn độ sâu, đường lặp nút vẫn có thể xuất hiện trong kết quả.

Vì vậy, khi cần cả tính đúng đắn và ổn định:

- Dùng **cycle detection** để không đi lại nút theo quy tắc đã định.
- Có thể thêm **depth limit** để giới hạn phạm vi nghiệp vụ.
- Nếu chạm giới hạn, cần thể hiện điều đó bằng thông tin riêng thay vì ngầm hiểu kết quả đầy đủ.

### Theo dõi việc chạm giới hạn

Ví dụ trả thêm nhãn cho các hàng tại độ sâu tối đa:

```sql
WITH RECURSIVE limited_walk(node_id, depth, path) AS (
    SELECT 1, 0, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_node, w.depth + 1, w.path || e.to_node
    FROM limited_walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
    WHERE w.depth < 4
      AND NOT (e.to_node = ANY(w.path))
)
SELECT
    node_id,
    depth,
    path,
    CASE WHEN depth = 4 THEN 'at_depth_limit'
         ELSE 'within_limit'
    END AS depth_status
FROM limited_walk
ORDER BY depth, path;
```

Cột `depth_status` chỉ nói hàng **ở độ sâu giới hạn**, không khẳng định còn đường để đi tiếp. Muốn xác định có cạnh tiếp tục hợp lệ nhưng bị giới hạn, phải kiểm tra riêng những cạnh kế tiếp và đối chiếu với `path`.

## 9. Cơ chế bảo vệ về tài nguyên của DBMS

Các DBMS thường có khả năng giới hạn thời gian chạy, số bước đệ quy hoặc tài nguyên để ngăn một truy vấn sai làm ảnh hưởng hệ thống. Chúng **không thay thế giải thuật dừng đúng**.

### PostgreSQL: statement_timeout

Trong một phiên thực hành, có thể dùng timeout cục bộ cho transaction:

```sql
BEGIN;

SET LOCAL statement_timeout = '3s';

-- Đặt một truy vấn đệ quy đã có bảo vệ phù hợp ở đây.
WITH RECURSIVE reachable(node_id) AS (
    SELECT 1::INTEGER
    UNION
    SELECT e.to_node
    FROM reachable AS r
    JOIN graph_edges_228 AS e
      ON e.from_node = r.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;

ROLLBACK;
```

`statement_timeout` giúp hủy câu lệnh vượt thời gian cấu hình; nó **không kết luận kết quả đã đầy đủ hay chu trình đã được xử lý**. Giá trị `3s` chỉ là minh họa cho môi trường học; trên môi trường thật, chính sách timeout phụ thuộc loại truy vấn và yêu cầu vận hành.

Đừng chủ ý chạy truy vấn vô hạn để “thử timeout”. Có thể kiểm tra cơ chế phát hiện chu trình bằng dữ liệu mẫu và các truy vấn đã bảo vệ.

### SQL Server và các DBMS khác

SQL Server hỗ trợ `MAXRECURSION` để kiểm soát số mức đệ quy trong một số truy vấn, ví dụ:

```sql
-- Ví dụ cú pháp SQL Server, không chạy trên PostgreSQL:
-- SELECT ...
-- FROM recursive_cte
-- OPTION (MAXRECURSION 100);
```

Khi vượt mức cho phép, truy vấn có thể bị dừng bằng lỗi. Đây là **bộ chặn tài nguyên**, không phải một cách xác nhận “không có chu trình”. Không nên tắt giới hạn nếu không có lý do và cơ chế phòng vệ khác.

MySQL và một số hệ khác có giới hạn số vòng hoặc cấu hình liên quan đệ quy; tên tham số, mức mặc định và cú pháp thay đổi theo phiên bản. Cần kiểm tra tài liệu của môi trường đang sử dụng.

### LIMIT ở SELECT cuối không phải bảo vệ đáng tin cậy

Một số truy vấn PostgreSQL đơn giản có thể chỉ lấy số hàng cần thiết từ một CTE đệ quy khi `SELECT` cuối dùng `LIMIT`. Nhưng đó **không phải cam kết** rằng mọi cấu trúc truy vấn đều tránh được đệ quy vô hạn: `ORDER BY`, `JOIN`, `GROUP BY` hoặc các bước tiêu thụ toàn bộ kết quả có thể yêu cầu sinh nhiều hơn.

Không nên xem:

```sql
SELECT ...
FROM recursive_cte
LIMIT 100;
```

là cơ chế phát hiện chu trình. Hãy kiểm tra lặp ngay trong phần đệ quy hoặc dùng `CYCLE`, rồi áp dụng các giới hạn truy vấn ngoài khi cần.

## 10. Phát hiện chu trình trong nhiều thành phần của đồ thị

Truy vấn bắt đầu từ `node_id = 1` chỉ kiểm tra những đường **đi tới được từ nút 1**. Nó không đi tới thành phần gồm 8 và 9:

```text
8 → 9 → 8
```

Do vậy nếu câu hỏi là “**toàn bộ đồ thị có chu trình không?**”, chỉ đi từ nút 1 là chưa đủ.

### Duyệt từ nhiều gốc được chọn

Ví dụ duyệt từ hai gốc 1 và 8, đồng thời ghi rõ đường nào thuộc gốc nào:

```sql
WITH RECURSIVE walk(root_id, node_id, depth, path, is_cycle) AS (
    SELECT
        r.root_id,
        r.root_id AS node_id,
        0,
        ARRAY[r.root_id]::INTEGER[],
        FALSE
    FROM (VALUES (1), (8)) AS r(root_id)

    UNION ALL

    SELECT
        w.root_id,
        e.to_node,
        w.depth + 1,
        w.path || e.to_node,
        e.to_node = ANY(w.path)
    FROM walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
    WHERE NOT w.is_cycle
)
SELECT root_id, node_id, path
FROM walk
WHERE is_cycle
ORDER BY root_id, path;
```

Kết quả sẽ có các đường đóng chu trình từ gốc 1 và đường `{8,9,8}` từ gốc 8.

Cột `root_id` phục vụ **nhãn nguồn của đường đi**; kiểm tra lặp phải dựa trên `path` thuộc **đường đang mở rộng**, không dựa trên một danh sách nút đã thấy của gốc khác.

### Duyệt từ mọi nút có thể xuất hiện

Để khảo sát toàn bộ đồ thị có hướng, bạn có thể tạo danh sách nút từ hai cột cạnh:

```sql
WITH all_nodes AS (
    SELECT from_node AS node_id FROM graph_edges_228
    UNION
    SELECT to_node AS node_id FROM graph_edges_228
)
SELECT node_id
FROM all_nodes
ORDER BY node_id;
```

Tập nút có thể làm tập anchor cho các truy vấn phát hiện chu trình từ từng nút. Tuy nhiên, số đường đơn trong một đồ thị lớn có thể tăng rất nhanh; duyệt toàn bộ đường từ mọi nút thường **đắt đỏ**. Một hệ thống lớn có thể cần thuật toán đồ thị hoặc mô hình dữ liệu phù hợp hơn để tìm các thành phần liên thông mạnh và chu trình.

Một quy tắc đáng nhớ: **“không tìm thấy chu trình trong những đường đã duyệt” khác với “không có chu trình ở bất kỳ đâu trong dữ liệu”**.

## 11. Chu trình trong cây tổ chức và phân cấp danh mục

Không phải hệ thống nào cũng có bảng cạnh riêng. Một mô hình phân cấp thông thường là bảng tự tham chiếu:

```text
employees
├── employee_id   (khóa nhân viên)
└── manager_id    (khóa quản lý)
```

Phần đệ quy để tìm cấp dưới của nhân viên gốc `employee_id = 10` có thể trông như:

```sql
-- Minh họa mô hình khi có bảng employees(employee_id, manager_id).
WITH RECURSIVE subordinates(employee_id, depth) AS (
    SELECT employee_id, 0
    FROM employees
    WHERE employee_id = 10

    UNION ALL

    SELECT e.employee_id, s.depth + 1
    FROM employees AS e
    JOIN subordinates AS s
      ON e.manager_id = s.employee_id
)
CYCLE employee_id SET is_cycle USING path
SELECT employee_id, depth, is_cycle
FROM subordinates;
```

Nếu dữ liệu sai khiến nhân viên A quản lý B, B quản lý C và C quản lý A, mệnh đề `CYCLE` sẽ đánh dấu đường quay lại một employee_id đã xuất hiện.

### Khi dữ liệu phải thực sự là cây

Đối với cây tổ chức, chu trình thường là **vi phạm nghiệp vụ**:

- Một người không nên quản lý trực tiếp chính mình.
- Không nên có đường quản lý quay về nhân viên xuất phát.
- Quy tắc mỗi nhân viên có tối đa một quản lý trực tiếp không tự ngăn được chu trình dài hơn một cạnh.
- Foreign key chỉ bảo đảm quản lý được tham chiếu tồn tại (nếu có), không tự chứng minh toàn bộ chuỗi quản lý không có vòng.

Có thể đặt ràng buộc chống tự tham chiếu trực tiếp:

```sql
-- Ý tưởng về ràng buộc bổ sung vào schema:
-- CHECK (manager_id IS NULL OR manager_id <> employee_id)
```

Nhưng điều kiện này chỉ bắt được **self-loop**. Nó không bắt vòng A→B→C→A. Muốn chặn vòng dài có thể cần quy trình kiểm tra khi ghi dữ liệu, logic transaction phù hợp, hoặc mô hình khác hỗ trợ duy trì tính không chu trình.

CTE phát hiện chu trình rất hữu ích để **kiểm tra dữ liệu hiện có**, không thay thế việc bảo đảm ràng buộc lúc cập nhật.

## 12. Phân biệt đường đi, nút duy nhất và chu trình

Một CTE đệ quy có thể phục vụ nhiều loại kết quả; chọn loại sai dễ làm sai báo cáo.

### 12.1. Mỗi đường một hàng

Nếu lưu `path`, nút 4 được trả qua hai đường:

```text
{1,2,4}
{1,3,4}
```

Đó là **hai đường hợp lệ**. Nếu người dùng muốn tất cả cách đi từ 1 tới 4, phải giữ cả hai.

### 12.2. Mỗi nút một hàng

Nếu chỉ muốn biết nút 4 có thể đi tới được hay không, `UNION` trên `node_id` là đủ, và hai đường có thể được gộp thành một nút 4.

### 12.3. Một hàng trên mỗi cạnh đóng chu trình

Với `is_cycle` hoặc `CYCLE`, có thể trả các hàng mà nút kế tiếp đã nằm trong đường trước đó. Một chu trình trong đồ thị có thể được phát hiện theo **nhiều đường** và được báo nhiều lần.

Ví dụ các đường:

```text
{1,2,4,5,2}
{1,3,4,5,2,4}
```

đều biểu thị việc gặp lại một nút khi duyệt, nhưng không có nghĩa hệ thống tồn tại hai “lỗi nghiệp vụ” độc lập. Nếu mục tiêu là **liệt kê các chu trình duy nhất**, cần định nghĩa thế nào là hai chu trình tương đương (đổi điểm bắt đầu, đảo hướng nếu đồ thị vô hướng, cùng tập cạnh hay cùng chuỗi cạnh) và chuẩn hóa kết quả. `SELECT DISTINCT node_id` không giải quyết đầy đủ bài toán đó.

## 13. Khóa ghép và các trạng thái có thể lặp

Một “nút” trong bài toán ứng dụng có thể được định danh bằng nhiều cột. Ví dụ mô hình đa tenant:

```text
tenant_id | node_id
----------+--------
T1        | 5
T2        | 5
```

Hai hàng trên là hai nút khác nhau. Nếu chỉ ghi `node_id` vào `path`, hệ thống có thể phát hiện **chu trình giả** khi đi qua hai tenant, hoặc ngược lại viết sai điều kiện cạnh.

Trong PostgreSQL, `CYCLE` có thể xét nhiều trường:

```sql
-- Minh họa cú pháp khi CTE có đủ hai cột này:
CYCLE tenant_id, node_id SET is_cycle USING path_nodes
```

Với cách tự quản, có thể lưu **khóa ghép** theo thứ tự, ví dụ một mảng các giá trị cấu trúc `ROW(tenant_id,node_id)` của PostgreSQL. Tuy nhiên, các kiểu composite, cast và so sánh mảng trở nên phức tạp hơn; khi không cần tùy biến sâu, `CYCLE` thường dễ đọc hơn.

### Trạng thái không chỉ là node_id

Trong một quy trình có trạng thái như “đang kiểm tra”, “đã xác minh”, “đang hoàn tiền”, quay lại cùng mã bước chưa chắc là vòng vô hạn nếu trạng thái được cập nhật và có số trạng thái hữu hạn.

Hãy xác định **thế nào là trạng thái đã lặp** theo ý nghĩa nghiệp vụ. Đối với một đồ thị quan hệ thuần, ID nút thường đủ. Đối với một máy trạng thái, có thể cần cặp `(node_id, phase)`. Nhưng không nên thêm trường luôn thay đổi như `depth` chỉ để làm khóa duy nhất, vì như vậy sẽ phá cơ chế phát hiện chu trình.

## 14. Những rủi ro khác dù đã có phát hiện chu trình

### 14.1. Bùng nổ số đường hợp lệ

Một đồ thị phân nhánh mạnh có thể có số **đường đơn** rất lớn. Cycle detection bảo đảm không đi vô hạn quanh cùng nút trên một đường, nhưng không làm số đường giảm xuống còn nhỏ.

Ví dụ một đồ thị có nhiều lớp, mỗi lớp có nhiều lựa chọn kết nối, có thể sinh rất nhiều tổ hợp đường khác nhau mà không lặp nút.

Khi ứng dụng chỉ cần số nút có thể tới, hãy dùng truy vấn trả **tập nút duy nhất** thay vì liệt kê mọi đường. Khi chỉ cần tìm một đường phù hợp, hãy chọn thuật toán hoặc giới hạn tìm kiếm phù hợp với mục tiêu.

### 14.2. Chạy vòng lặp theo dữ liệu thay đổi

Trong một hệ thống nhiều người dùng, quan hệ đồ thị có thể đang được cập nhật trong lúc báo cáo chạy. Ngữ nghĩa snapshot và mức cô lập transaction của DBMS quyết định những thay đổi nào truy vấn nhìn thấy.

Một truy vấn phát hiện chu trình ở thời điểm này không tự bảo đảm rằng cấu trúc sẽ không thay đổi sau khi truy vấn kết thúc. Nếu cần **chặn cập nhật tạo vòng**, phải thiết kế kiểm tra trong luồng ghi và kiểm soát cạnh tranh thích hợp.

### 14.3. Kết quả không có thứ tự duyệt được bảo đảm

PostgreSQL có thể cho bạn quan sát các kết quả đệ quy theo một dạng thứ tự ở một số kế hoạch, nhưng **không nên dựa vào thứ tự trả hàng không có `ORDER BY`** để suy ra đường đi nào được duyệt trước.

Ví dụ:

```sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 1::INTEGER
    UNION
    SELECT e.to_node
    FROM reachable AS r
    JOIN graph_edges_228 AS e
      ON e.from_node = r.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
```

`ORDER BY node_id` chỉ quy định **thứ tự hiển thị cuối cùng**, không xác nhận thuật toán nội bộ đang thực thi theo thứ tự nút tăng dần.

### 14.4. COUNT và SUM có thể phóng đại do nhiều đường

Nếu một nút xuất hiện theo nhiều đường, `COUNT(*)` trên tập kết quả đường đi có thể đếm **lượt ghé thăm**, không phải **số nút duy nhất**. Tương tự, nối giá trị doanh thu vào các đường rồi `SUM` có thể nhân bản doanh thu.

Phải xác định cấp độ của mỗi hàng: **một nút**, **một đường**, **một cạnh**, hay **một lần đi tới nút**. Có thể cần `COUNT(DISTINCT node_id)` nếu muốn đếm nút, nhưng việc dùng `DISTINCT` không thể tự sửa một logic chọn đường không đúng.

## 15. Chẩn đoán chu trình bằng cột trạng thái rõ ràng

Khi một báo cáo cần phân biệt “hết cạnh”, “gặp chu trình” và “bị cắt do độ sâu”, nên giữ các cột trạng thái tách biệt.

Ví dụ mô phỏng phân loại hàng trong một truy vấn có phát hiện chu trình và giới hạn độ sâu:

```sql
WITH RECURSIVE walk(node_id, depth, path, is_cycle) AS (
    SELECT 1, 0, ARRAY[1]::INTEGER[], FALSE

    UNION ALL

    SELECT
        e.to_node,
        w.depth + 1,
        w.path || e.to_node,
        e.to_node = ANY(w.path)
    FROM walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
    WHERE NOT w.is_cycle
      AND w.depth < 6
)
SELECT
    w.node_id,
    w.depth,
    w.path,
    CASE
        WHEN w.is_cycle THEN 'cycle_detected'
        WHEN w.depth = 6 THEN 'depth_limit_reached'
        WHEN NOT EXISTS (
            SELECT 1
            FROM graph_edges_228 AS e
            WHERE e.from_node = w.node_id
        ) THEN 'leaf'
        ELSE 'expandable_or_exhausted'
    END AS visit_status
FROM walk AS w
ORDER BY w.path;
```

Cột `visit_status` trong ví dụ có tính chất **chẩn đoán ở cấp hàng**:

- `cycle_detected`: hàng này đóng chu trình, không mở rộng tiếp.
- `depth_limit_reached`: hàng đang ở giới hạn; chưa khẳng định còn cạnh hợp lệ để đi.
- `leaf`: nút không có cạnh đi ra trong bảng cạnh mẫu.
- `expandable_or_exhausted`: nút không thuộc ba nhóm trên, có thể có cạnh dẫn tới trạng thái đã đi qua hoặc các đường đã được xử lý.

Đây không phải một máy trạng thái hoàn chỉnh cho mọi hệ thống đồ thị. Nếu cần trạng thái “không còn cạnh **hợp lệ chưa thăm**”, phải kiểm tra các cạnh theo `path` của chính hàng hiện tại.

## 16. Thực hành kiểm tra từng phần thay vì chạy truy vấn không giới hạn

Một quy trình thực hành an toàn:

1. **Đọc các cạnh nguồn** để biết hướng quan hệ và khóa định danh:
   `SELECT from_node, to_node FROM graph_edges_228`.
2. **Bắt đầu từ một gốc nhỏ**, ví dụ nút 1, với mảng `path` hoặc `CYCLE` ngay từ đầu.
3. **Giữ `depth`** để thấy số bước.
4. **Ghi lại `is_cycle` hoặc các đường đóng vòng** để chẩn đoán.
5. **Thêm giới hạn độ sâu** nếu phạm vi nghiệp vụ chỉ cho phép số bước nhất định.
6. **Phân biệt kết quả có đường lặp** với kết quả các đường đơn.
7. **Chạy thử trên dữ liệu có self-loop và chu trình dài hơn một cạnh**.
8. **Chạy thử trên dữ liệu có hội tụ không chu trình** để bảo đảm không phát hiện nhầm.
9. **Quan sát kế hoạch và tài nguyên trên dữ liệu lớn**, không suy từ bộ dữ liệu vài hàng.
10. **Chọn đầu ra phù hợp**: nút duy nhất, mọi đường hợp lệ hay danh sách cạnh lỗi.

Đừng dùng một truy vấn không có điều kiện dừng để “kiểm tra xem có vòng hay không”. Chính hành vi đó tạo ra nguy cơ cần phòng tránh.

## 17. Hiệu năng và chỉ mục

Một CTE đệ quy duyệt cạnh thường lặp lại phép nối:

```sql
JOIN graph_edges_228 AS e
  ON e.from_node = w.node_id
```

Với dữ liệu lớn, một chỉ mục trên cột **điểm xuất phát của cạnh** có thể giúp tra các cạnh kế tiếp:

```sql
-- Ví dụ hướng chỉ mục cho PostgreSQL.
-- Không bắt buộc tạo khi học với bảng mẫu rất nhỏ.
CREATE INDEX ON graph_edges_228 (from_node);
```

Nếu có nhiều điều kiện, ví dụ `tenant_id` và `from_node`, có thể cân nhắc chỉ mục ghép theo mẫu truy vấn thực tế.

Tuy nhiên, hiệu năng phụ thuộc nhiều yếu tố:

- Số cạnh đi ra trung bình của mỗi nút.
- Độ sâu đường đi.
- Có chu trình và hội tụ nhiều đường hay không.
- Có cần giữ `path`/`depth` hoặc chỉ cần tập nút duy nhất.
- Có giới hạn số gốc, loại quan hệ hoặc thời điểm hiệu lực không.
- Chi phí so sánh `ANY(path)` tăng theo độ dài đường.
- Khả năng tối ưu CTE và kiểu chỉ mục của DBMS.

Trong PostgreSQL, `EXPLAIN` có thể giúp xem kế hoạch dự kiến:

```sql
EXPLAIN
WITH RECURSIVE reachable(node_id) AS (
    SELECT 1::INTEGER
    UNION
    SELECT e.to_node
    FROM reachable AS r
    JOIN graph_edges_228 AS e
      ON e.from_node = r.node_id
)
SELECT *
FROM reachable;
```

Ở dữ liệu rất nhỏ, quét tuần tự có thể là lựa chọn hiệu quả; không nên mặc định nó là dấu hiệu phải tạo thêm index.

**Quan trọng:** dù index làm tìm cạnh nhanh hơn, nó không sửa được truy vấn thiếu kiểm tra chu trình. Tối ưu hóa phải đến sau khi truy vấn đúng về ngữ nghĩa.

## 18. Khác biệt giữa PostgreSQL, SQL Server, MySQL, SQLite và Oracle

| Hệ quản trị | Cơ chế truy vấn đệ quy | Phòng tránh/đánh dấu chu trình |
| --- | --- | --- |
| **PostgreSQL** | `WITH RECURSIVE` | Có thể tự giữ `path` bằng mảng; PostgreSQL 14+ hỗ trợ `CYCLE ... SET ... USING ...` |
| **SQL Server** | CTE đệ quy với `WITH` và các quy tắc riêng, thường nối bằng `UNION ALL` | Không có cú pháp PostgreSQL `CYCLE` tương đương trong CTE thông thường; có thể tự giữ đường đi và dùng `OPTION (MAXRECURSION n)` như giới hạn bảo vệ |
| **MySQL 8+** | `WITH RECURSIVE` ở phiên bản phù hợp | Thường tự theo dõi đường đi bằng JSON hoặc chuỗi mã hóa có kiểm soát; có giới hạn đệ quy theo cấu hình/phiên bản |
| **SQLite** | `WITH RECURSIVE` | `UNION` có thể khử nút trùng khi chỉ giữ ID; có thể quản lý đường đi bằng biểu thức chuỗi hoặc cấu trúc bổ trợ; không dùng trực tiếp mảng PostgreSQL |
| **Oracle Database** | Recursive subquery factoring hoặc `CONNECT BY` tùy dạng truy vấn | Có cơ chế đánh dấu chu trình `CYCLE` trong cú pháp đệ quy của Oracle, và `NOCYCLE`/`CONNECT_BY_ISCYCLE` trong các truy vấn phân cấp thích hợp |

Không nên **sao chép nguyên**:

```sql
CYCLE node_id SET is_cycle USING path_nodes
```

sang mọi DBMS rồi giả định sẽ hoạt động. Cú pháp đánh dấu, kiểu đường đi và giới hạn đệ quy khác nhau theo sản phẩm.

### Cẩn trọng khi dùng chuỗi thay cho mảng

Một số hệ không hỗ trợ mảng trong CTE theo cách PostgreSQL, nên người viết lưu đường đi thành chuỗi như:

```text
|1|2|4|5|
```

Khi kiểm tra đã xuất hiện nút 2, phải tìm **mã được bao bởi dấu phân cách** (ví dụ `|2|`), không chỉ tìm chuỗi `2`, vì mã 12 cũng chứa ký tự 2. Ngoài ra còn có vấn đề:

- ID có thể chứa chính dấu phân cách, cần escape hoặc mã hóa không mơ hồ.
- Độ dài chuỗi có thể vượt kiểu dữ liệu hoặc giới hạn của CTE.
- Phép nối chuỗi và hàm tìm chuỗi khác nhau giữa DBMS.
- Với khóa nhiều trường, cần mã hóa từng phần tránh va chạm.
- Một số collation so sánh chuỗi không phân biệt hoa/thường hoặc ký tự theo cách không mong muốn.

Vì vậy nên ưu tiên kiểu dữ liệu có cấu trúc khi DBMS hỗ trợ, hoặc định nghĩa chuẩn hóa chuỗi một cách cẩn thận thay vì ghép tùy ý.

## 19. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Truy vấn đệ quy chạy quá lâu hoặc bị hủy | `UNION ALL` đi quanh chu trình mà không dừng | Dùng `path`/`ANY`, `CYCLE` hoặc chiến lược duyệt nút duy nhất phù hợp |
| Đã đổi sang `UNION` nhưng vẫn sinh thêm hàng | `depth` hoặc `path` thay đổi nên toàn bộ hàng không trùng | Phát hiện nút lặp theo khóa đúng, không dựa vào khử trùng toàn hàng |
| Nút 4 xuất hiện hai lần | Có hai đường hợp lệ 1→2→4 và 1→3→4 | Xác định cần mọi đường hay chỉ tập nút duy nhất |
| Chỉ thấy một nút 4 nhưng muốn tất cả đường | `UNION` đã gộp hàng theo node ID | Giữ `path` và kiểm tra chu trình theo đường |
| Không thấy chu trình 8→9→8 | Chỉ bắt đầu từ nút 1, không tới được thành phần 8–9 | Duyệt thêm gốc hoặc thiết kế kiểm tra toàn đồ thị |
| Không phát hiện self-loop | Chỉ kiểm tra vòng có từ hai cạnh trở lên | Kiểm tra nút kế tiếp đã có trong `path`, gồm cả nút hiện tại |
| Đánh dấu chu trình sai giữa hai tenant | Chỉ dùng `node_id` làm khóa | Dùng đủ khóa ghép `(tenant_id,node_id)` |
| CTE `CYCLE` trả cả hàng lặp | Hàng đóng chu trình được đánh dấu để báo cáo | Lọc `WHERE NOT is_cycle` ở `SELECT` cuối nếu muốn bỏ chúng |
| Giới hạn độ sâu làm thiếu kết quả | Có đường hợp lệ dài hơn giới hạn | Báo rõ kết quả bị cắt, chọn giới hạn đúng nghiệp vụ |
| `LIMIT 100` không ngăn truy vấn nặng | Cấp truy vấn ngoài có thể phải xử lý nhiều hàng trước khi giới hạn | Đặt điều kiện dừng ngay trong đệ quy |
| Truy vấn vẫn rất lớn dù không có vòng | Số đường đơn có thể bùng nổ | Chỉ duyệt tập nút khi không cần đường, chọn thuật toán phù hợp |
| Tính `COUNT(*)` trên kết quả nhiều đường lớn hơn số nút | Một nút được ghé từ nhiều đường | Xác định cấp độ hàng và đếm đúng đối tượng |
| Dùng chuỗi path phát hiện sai mã | Tìm chuỗi con gây nhầm ID 2 với 12 | Dùng mảng/JSON hoặc mã hóa phân cách an toàn |
| CTE có `CYCLE` nhưng ghi dữ liệu vẫn tạo vòng | Truy vấn chỉ phát hiện vòng khi đọc | Thiết kế ràng buộc và kiểm tra trong quy trình cập nhật |

## 20. Bài tập tự luyện

Các bài tập sau dùng bảng tạm `graph_edges_228` của mục 2, chạy trên PostgreSQL. Hãy tự dự đoán ý nghĩa kết quả trước khi đọc lời giải.

### Bài 1. Nhận diện các chu trình

Từ dữ liệu cạnh, chỉ ra:

- Một chu trình có ít nhất hai nút có thể đi tới từ gốc 1.
- Một self-loop.
- Một chu trình không đi tới được từ gốc 1.

### Bài 2. Truy vấn tập nút đạt được

Viết `WITH RECURSIVE` chỉ có một cột `node_id` và dùng `UNION` để tìm mọi nút đi tới được từ gốc 1, mỗi nút một lần.

Dự đoán danh sách nút.

### Bài 3. Tự quản path

Viết CTE giữ `node_id`, `depth`, `path`. Chỉ đi sang nút kế tiếp nếu nút đó **chưa có trong path**. Truy vấn có trả đường `{1,2,4,5,2}` không? Vì sao?

### Bài 4. Đánh dấu hàng đóng chu trình

Thêm `is_cycle` vào bài 3, cho phép sinh một hàng đánh dấu khi nút kế tiếp đã có trên đường, nhưng **không mở rộng** hàng đó.

Hãy tìm đường đóng chu trình tại nút 6.

### Bài 5. Dùng CYCLE của PostgreSQL

Viết lại bài 4 bằng `CYCLE node_id SET is_cycle USING path_nodes`. Chỉ chọn hàng có `is_cycle = TRUE` ở câu `SELECT` cuối.

### Bài 6. UNION không cứu được truy vấn có depth thay đổi

Viết CTE có các cột `(node_id, depth)`, dùng `UNION` và **giới hạn độ sâu bằng 5**. Tìm một `node_id` xuất hiện ở nhiều `depth` khác nhau và giải thích vì sao `UNION` không gộp chúng.

### Bài 7. Phân biệt hội tụ và chu trình

Giải thích vì sao `{1,2,4}` và `{1,3,4}` đều hợp lệ, nhưng `{1,2,4,5,2}` là đường đóng chu trình.

### Bài 8. Giới hạn độ sâu

Viết truy vấn chỉ đi tối đa **ba cạnh** từ gốc 1, đồng thời không lặp nút trên cùng đường. Độ sâu của anchor và các nút cuối được tính thế nào?

### Bài 9. Kiểm tra thành phần không liên thông

Duyệt từ gốc 8 để phát hiện đường đóng chu trình. So sánh với kết quả từ gốc 1.

### Bài 10. Phân biệt nút và lượt ghé

Viết hai câu:

1. Đếm số nút duy nhất đi tới được từ 1.
2. Đếm số hàng của kết quả duyệt có `path` và kiểm tra chu trình.

Giải thích vì sao hai phép đếm có thể khác nhau.

### Bài 11. Khóa ghép

Một hệ đa tenant có hai nút `(T1,5)` và `(T2,5)`. Bạn sẽ dùng khóa nào ở `CYCLE`? Vì sao không dùng một mình `node_id` hoặc đưa thêm `depth` vào khóa?

### Bài 12. Bảo vệ môi trường thực tế

Đề xuất một chính sách để ngăn chu trình gây lỗi trong hệ thống danh mục: kiểm tra ở thời điểm ghi dữ liệu, phát hiện trong truy vấn đọc, giới hạn tài nguyên và xử lý báo cáo lỗi. Giải thích vì sao chỉ dùng timeout là chưa đủ.

## 21. Gợi ý lời giải

### Bài 1

- Chu trình từ gốc 1: `2→4→5→2`.
- Self-loop: `6→6`.
- Chu trình ngoài vùng đi tới từ gốc 1: `8→9→8`.

### Bài 2

```sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 1::INTEGER
    UNION
    SELECT e.to_node
    FROM reachable AS r
    JOIN graph_edges_228 AS e
      ON e.from_node = r.node_id
)
SELECT node_id
FROM reachable
ORDER BY node_id;
```

Kết quả `1,2,3,4,5,6,7`.

### Bài 3

```sql
WITH RECURSIVE simple_paths(node_id, depth, path) AS (
    SELECT 1, 0, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_node, s.depth + 1, s.path || e.to_node
    FROM simple_paths AS s
    JOIN graph_edges_228 AS e
      ON e.from_node = s.node_id
    WHERE NOT (e.to_node = ANY(s.path))
)
SELECT node_id, depth, path
FROM simple_paths
ORDER BY path;
```

Đường `{1,2,4,5,2}` bị chặn khi thử thêm nút 2 lần thứ hai, vì `2 = ANY({1,2,4,5})` là TRUE.

### Bài 4

```sql
WITH RECURSIVE walk(node_id, depth, path, is_cycle) AS (
    SELECT 1, 0, ARRAY[1]::INTEGER[], FALSE
    UNION ALL
    SELECT
        e.to_node,
        w.depth + 1,
        w.path || e.to_node,
        e.to_node = ANY(w.path)
    FROM walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
    WHERE NOT w.is_cycle
)
SELECT node_id, path, is_cycle
FROM walk
WHERE is_cycle
ORDER BY path;
```

Một hàng báo chu trình self-loop có `path = {1,3,6,6}`.

### Bài 5

```sql
WITH RECURSIVE walk(node_id, depth) AS (
    SELECT 1, 0
    UNION ALL
    SELECT e.to_node, w.depth + 1
    FROM walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
)
CYCLE node_id SET is_cycle USING path_nodes
SELECT node_id, depth, path_nodes
FROM walk
WHERE is_cycle
ORDER BY path_nodes;
```

Mệnh đề `CYCLE` tự ghi trạng thái đường đi và ngăn tiếp tục mở rộng sau hàng đóng vòng.

### Bài 6

```sql
WITH RECURSIVE visit(node_id, depth) AS (
    SELECT 1, 0
    UNION
    SELECT e.to_node, v.depth + 1
    FROM visit AS v
    JOIN graph_edges_228 AS e
      ON e.from_node = v.node_id
    WHERE v.depth < 5
)
SELECT node_id, depth
FROM visit
ORDER BY depth, node_id;
```

Nút `2` xuất hiện ở độ sâu `1` qua `1→2` và độ sâu `4` qua `1→2→4→5→2`. Hai hàng `(2,1)` và `(2,4)` khác nhau, nên `UNION` không loại cả hai.

### Bài 7

`{1,2,4}` và `{1,3,4}` là hai đường không lặp nút, dù đều kết thúc tại 4. `{1,2,4,5,2}` quay lại 2 đã xuất hiện trong cùng đường, nên đóng một chu trình.

### Bài 8

```sql
WITH RECURSIVE walk(node_id, depth, path) AS (
    SELECT 1, 0, ARRAY[1]::INTEGER[]
    UNION ALL
    SELECT e.to_node, w.depth + 1, w.path || e.to_node
    FROM walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
    WHERE w.depth < 3
      AND NOT (e.to_node = ANY(w.path))
)
SELECT node_id, depth, path
FROM walk
ORDER BY depth, path;
```

Anchor có độ sâu 0; mỗi cạnh tăng độ sâu 1; hàng ở độ sâu 3 không được mở rộng tiếp.

### Bài 9

```sql
WITH RECURSIVE walk(node_id, path, is_cycle) AS (
    SELECT 8, ARRAY[8]::INTEGER[], FALSE
    UNION ALL
    SELECT e.to_node, w.path || e.to_node,
           e.to_node = ANY(w.path)
    FROM walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
    WHERE NOT w.is_cycle
)
SELECT path
FROM walk
WHERE is_cycle;
```

Kết quả có `{8,9,8}`. Truy vấn từ gốc 1 không thấy chu trình này vì không đi tới 8 hoặc 9.

### Bài 10

Đếm nút duy nhất:

```sql
WITH RECURSIVE reachable(node_id) AS (
    SELECT 1
    UNION
    SELECT e.to_node
    FROM reachable AS r
    JOIN graph_edges_228 AS e
      ON e.from_node = r.node_id
)
SELECT COUNT(*) AS reachable_nodes
FROM reachable;
```

Kết quả `7`.

Đếm hàng gồm cả các đường đóng chu trình:

```sql
WITH RECURSIVE walk(node_id, depth, path, is_cycle) AS (
    SELECT 1, 0, ARRAY[1]::INTEGER[], FALSE
    UNION ALL
    SELECT e.to_node, w.depth + 1,
           w.path || e.to_node,
           e.to_node = ANY(w.path)
    FROM walk AS w
    JOIN graph_edges_228 AS e
      ON e.from_node = w.node_id
    WHERE NOT w.is_cycle
)
SELECT COUNT(*) AS visit_rows,
       COUNT(*) FILTER (WHERE is_cycle) AS cycle_closing_rows
FROM walk;
```

Kết quả có thể có nhiều hơn 7 hàng vì cùng nút có các đường đi khác nhau và hàng đóng chu trình cũng được giữ. Hai phép đếm có **đơn vị đo khác nhau**: nút duy nhất và lượt xuất hiện trong các đường.

### Bài 11

Dùng `CYCLE tenant_id, node_id SET is_cycle USING path_nodes` khi danh tính nút là cặp tenant/nút. Không dùng một mình ID khi nhiều tenant có cùng số ID. Không thêm `depth` vì độ sâu thay đổi mỗi lần quay lại và làm mất khả năng nhận diện trạng thái đã lặp.

### Bài 12

Một giải pháp nhiều lớp có thể gồm:

- Thiết kế khóa/ràng buộc để loại các quan hệ bất hợp lệ đơn giản (như tự trỏ chính mình).
- Kiểm tra chu trình khi thêm hoặc đổi cạnh, trong transaction và có chiến lược kiểm soát cạnh tranh thích hợp.
- Khi đọc, sử dụng `CYCLE` hoặc `path` để báo đường đóng vòng thay vì chạy không giới hạn.
- Có giới hạn độ sâu/tài nguyên và timeout thích hợp, cùng khả năng hủy truy vấn.
- Ghi lại thông tin lỗi đủ để xác định cạnh hoặc đường gây chu trình; không tự ý xóa dữ liệu khi chưa xác nhận ý nghĩa nghiệp vụ.
- Theo dõi số lượng đường/hàng sinh ra để phát hiện tình trạng bùng nổ kết quả dù không có chu trình.

Timeout chỉ dừng tác hại sau một thời gian, **không tạo ra kết quả đầy đủ hoặc sửa cấu trúc sai**.

## 22. Tổng kết và lựa chọn chiến lược

Truy vấn đệ quy an toàn không chỉ cần cú pháp `WITH RECURSIVE`; nó cần một quy tắc giải thích **khi nào một trạng thái được phép tiếp tục**. Hãy chọn theo mục tiêu:

| Bạn muốn biết gì? | Hướng xử lý |
| --- | --- |
| Nút nào có thể đạt được từ một gốc? | Giữ tập `node_id` và dùng `UNION` để loại các nút đã có, khi định danh trạng thái hữu hạn |
| Có những đường nào không lặp nút? | Giữ mảng `path` và chặn nút kế tiếp đã xuất hiện trên đường |
| Đường nào tạo ra chu trình? | Giữ `is_cycle` hoặc dùng `CYCLE` của PostgreSQL |
| Cần kiểm tra cả thành phần không liên thông? | Chọn đủ gốc hoặc thiết kế thuật toán kiểm tra toàn đồ thị |
| Có cần giữ đường đi sâu vô hạn theo nghiệp vụ không? | Thường không; định nghĩa độ sâu/tài nguyên tối đa và cách báo kết quả bị cắt |
| Đang xử lý cây dữ liệu không được phép có vòng? | Kết hợp phòng ngừa lúc ghi, phát hiện khi đọc và cơ chế báo dữ liệu sai |

**Điểm cốt lõi:** `UNION ALL` không nhớ nút đã đi qua; `UNION` chỉ khử các **hàng trùng nhau hoàn toàn**; còn cycle detection phải dựa trên **định danh trạng thái đã xuất hiện trong chính đường đang duyệt**. PostgreSQL cho phép viết rõ quy tắc này bằng mảng và `ANY` hoặc bằng mệnh đề `CYCLE`. Kết hợp cách phát hiện đúng với giới hạn tài nguyên phù hợp sẽ giúp truy vấn đệ quy đáng tin cậy hơn, tránh lặp vô hạn và không đánh đồng hội tụ hợp lệ với chu trình thực sự.
