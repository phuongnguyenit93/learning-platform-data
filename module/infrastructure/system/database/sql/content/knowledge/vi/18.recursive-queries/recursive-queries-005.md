# Tính lũy kế theo quan hệ đệ quy và cấu trúc thành phần

Trong **Database SQL**, dữ liệu có cấu trúc phân cấp không chỉ dùng để hiển thị cây thư mục hoặc sơ đồ tổ chức. Nhiều bài toán cần **tính toán xuyên qua nhiều cấp quan hệ**: một thành phẩm cần bao nhiêu linh kiện, một bộ phận có tổng chi phí của mọi bộ phận con là bao nhiêu, hoặc một nút trong hệ thống có bao nhiêu tài nguyên nằm trong toàn bộ cấu trúc bên dưới nó.

Ví dụ điển hình là **định mức nguyên vật liệu (Bill of Materials — BOM)**. Một chiếc xe đạp cần 2 bánh xe; mỗi bánh xe cần 20 chiếc căm. Vì vậy, 1 xe đạp cần **2 × 20 = 40 chiếc căm**. Nếu cùng loại ốc vít còn dùng ở khung và ở cấp lắp ráp cuối, ta phải **cộng số lượng đi đến linh kiện đó qua từng nhánh** chứ không thể đếm tên linh kiện một lần rồi bỏ qua các đường đi còn lại.

Truy vấn đệ quy trong SQL, thường được viết bằng **`WITH RECURSIVE`**, cho phép:

1. Xác định thành phẩm hoặc nút gốc cần tính.
2. Đi lần lượt từ cha xuống con qua mọi cấp.
3. **Mang theo giá trị lũy kế** từ cấp trước, chẳng hạn tích số lượng theo đường đi.
4. Tổng hợp kết quả theo mã linh kiện hoặc theo mã thành phẩm.
5. Kiểm soát chu trình, chiều sâu và dữ liệu không hợp lệ để tránh phép tính sai hoặc không kết thúc.

Bài học tập trung vào kỹ thuật **tính lũy kế dọc đường đi và tổng hợp trên đồ thị thành phần**, phân biệt với cộng dồn theo thứ tự hàng bằng hàm cửa sổ. Các ví dụ chạy được trong **PostgreSQL**, đồng thời chỉ rõ cách điều chỉnh sang MySQL/MariaDB, SQL Server, SQLite và Oracle.

## 1. Quan hệ cha–con và cấu trúc thành phần

Một BOM có thể được lưu bằng hai bảng:

- `parts`: danh mục linh kiện, bộ phận và thành phẩm.
- `bom_edges`: mỗi dòng biểu thị một quan hệ **bộ phận cha cần bao nhiêu đơn vị của bộ phận con**.

Ví dụ:

```text
Xe đạp (100)
├── Bánh xe (200) × 2
│   ├── Lốp (210) × 1
│   ├── Vành (220) × 1
│   ├── Căm (230) × 20
│   └── Ốc (500) × 4
├── Khung (300) × 1
│   └── Ốc (500) × 2
├── Bàn đạp (400) × 2
├── Tay lái (600) × 1
└── Ốc (500) × 4
```

Ký hiệu `× n` ngay cạnh một nhánh là **số lượng con trên một đơn vị cha trực tiếp**, không phải số lượng của con trên toàn bộ chiếc xe.

Với **1 xe đạp**:

| Đường đi | Phép tính | Số lượng cần |
| --- | --- | ---: |
| Xe đạp → Bánh xe | `2` | 2 bánh xe |
| Xe đạp → Bánh xe → Lốp | `2 × 1` | 2 lốp |
| Xe đạp → Bánh xe → Vành | `2 × 1` | 2 vành |
| Xe đạp → Bánh xe → Căm | `2 × 20` | 40 căm |
| Xe đạp → Bánh xe → Ốc | `2 × 4` | 8 ốc |
| Xe đạp → Khung → Ốc | `1 × 2` | 2 ốc |
| Xe đạp → Ốc trực tiếp | `4` | 4 ốc |

Tổng số ốc là:

\[
8 + 2 + 4 = 14.
\]

Có **ba đường đi** dẫn đến linh kiện ốc, nhưng cần **14 đơn vị** ốc. Đây là khác biệt giữa **đếm số nút**, **đếm số đường đi** và **tính số lượng vật tư cần thiết**.

### Cây, DAG và đồ thị có chu trình

Một cấu trúc thành phần không nhất thiết là cây thuần túy:

| Cấu trúc | Đặc điểm | Hệ quả đối với SQL |
| --- | --- | --- |
| Cây (tree) | Mỗi nút con có tối đa một cha trong cấu trúc đang xét | Mỗi nút thường chỉ có một đường đi từ gốc |
| Đồ thị có hướng không chu trình (DAG) | Một linh kiện có thể được nhiều bộ phận cha sử dụng | Cùng một mã linh kiện xuất hiện qua nhiều đường đi và cần cộng dồn |
| Đồ thị có chu trình | Có đường đi quay lại nút đã gặp, ví dụ A → B → A | Truy vấn đệ quy có thể lặp vô hạn hoặc lặp đến giới hạn của engine |

Ví dụ ốc `500` được dùng ở nhiều cấp, nên cấu trúc BOM là một **DAG** theo mã linh kiện, không phải cây trong đó mỗi mã chỉ được xuất hiện một lần.

**Nguyên tắc thiết kế:** lưu mỗi quan hệ cha–con cùng **hệ số số lượng**; để SQL đi qua các đường đi và tính toán. Không cố lưu sẵn một “tổng số lượng cho mọi thành phẩm” trên chính dòng linh kiện nếu một linh kiện được nhiều thành phẩm dùng với hệ số khác nhau.

## 2. Mô hình dữ liệu và ý nghĩa của số lượng

Một bảng quan hệ BOM có thể chứa các cột:

| Cột | Ý nghĩa |
| --- | --- |
| `parent_part_id` | Mã bộ phận/thiết bị được lắp ráp |
| `child_part_id` | Mã vật tư hoặc cụm thành phần được sử dụng |
| `qty_per_parent` | Số đơn vị con cần cho **một đơn vị cha** |
| `effective_from`, `effective_to` (nếu có) | Khoảng hiệu lực của một phiên bản cấu trúc |
| `revision` (nếu có) | Phiên bản định mức |
| `scrap_rate` (nếu có) | Tỷ lệ hao hụt, cần quy tắc tính riêng |

Trong bài thực hành, ta dùng khóa chính tổng hợp `(parent_part_id, child_part_id)` để mỗi cặp cha–con chỉ xuất hiện một lần. Điều này phù hợp với mô hình giản lược khi không có nhiều vị trí lắp ráp, biến thể hoặc dòng BOM khác nhau dùng cùng một mã con.

Nếu hệ thống thật cho phép **cùng một linh kiện xuất hiện trên hai dòng khác nhau của một cha** (ví dụ hai vị trí gá lắp), cần một khóa dòng BOM riêng hoặc cột `line_no` trong khóa; không xóa trùng dữ liệu chỉ vì `parent_part_id` và `child_part_id` giống nhau.

### Đừng nhầm số lượng trực tiếp với số lượng lũy kế

Giả sử:

```text
A --(3)--> B --(4)--> C
```

- `3` là số B cần cho một A.
- `4` là số C cần cho một B.
- Số C cần cho một A là `3 × 4 = 12`.

Nếu tiếp tục `C --(5)--> D` thì số D cần cho một A là:

\[
3 \times 4 \times 5 = 60.
\]

Ta không lấy `3 + 4 + 5 = 12` để tính D. **Phép nhân** được sử dụng khi đi xuống một đường đi; **phép cộng** được sử dụng để gộp số lượng từ các đường đi khác nhau dẫn đến cùng một linh kiện.

## 3. Công thức lũy kế theo đường đi và theo linh kiện

Gọi:

- `r` là mã thành phẩm gốc.
- `p = (r \rightarrow v_1 \rightarrow \cdots \rightarrow v_k)` là một đường đi từ gốc đến linh kiện `v_k`.
- `q(u,v)` là số lượng `v` cần cho một đơn vị `u` trên cạnh cha–con.
- `Q(p)` là số lượng lũy kế của linh kiện ở cuối đường đi `p` khi sản xuất **một** thành phẩm gốc.

Khi đó:

\[
Q(p) = \prod_{(u,v)\in p} q(u,v).
\]

Quy ước tại nút gốc, đường đi chưa đi qua cạnh nào có tích bằng `1`.

Nếu linh kiện `x` có nhiều đường đi khác nhau từ `r`, số lượng cần cho **một thành phẩm** là:

\[
Q_r(x) =
\sum_{\substack{p:\,r\leadsto x}} Q(p).
\]

Trong đó tổng chạy qua **mọi đường đi hợp lệ từ gốc đến linh kiện x**. Với ốc trong ví dụ:

\[
Q_{100}(500) = (2\times4) + (1\times2) + 4 = 14.
\]

Với căm:

\[
Q_{100}(230) = 2\times20 = 40.
\]

Nếu một đơn sản xuất cần `N` xe đạp, số lượng vật tư tương ứng thường là:

\[
Q_{r,N}(x) = N \times Q_r(x).
\]

Ví dụ 10 xe cần 140 ốc và 400 căm, nếu cấu trúc, định mức và quy tắc hao hụt không thay đổi.

**Không dùng phép tổng hợp `SUM(qty_per_parent)` trực tiếp trên bảng BOM** để thay cho công thức trên: tổng đó cộng các **hệ số ở các cấp khác nhau**, trong khi chúng phải được nhân theo đường đi trước khi cộng giữa các nhánh.

## 4. Cú pháp đệ quy: anchor, recursive member và điều kiện dừng

Trên PostgreSQL, dạng tổng quát là:

```sql
WITH RECURSIVE expansion AS (
    -- 1. Anchor: bắt đầu tại nút gốc.
    SELECT
        root.part_id,
        1::numeric AS required_qty,
        0::integer AS depth
    FROM parts AS root
    WHERE root.part_id = 100

    UNION ALL

    -- 2. Recursive member: đi từ cha hiện tại đến con.
    SELECT
        link.child_part_id,
        e.required_qty * link.qty_per_parent,
        e.depth + 1
    FROM expansion AS e
    JOIN bom_edges AS link
      ON link.parent_part_id = e.part_id

    -- 3. Ví dụ giới hạn an toàn chiều sâu:
    WHERE e.depth < 20
)
SELECT part_id, required_qty, depth
FROM expansion;
```

Ở trên, `parts` và `bom_edges` chỉ là tên khái niệm. Phần thực hành sẽ tạo bảng thật `sql226_parts` và `sql226_bom`.

**Ba thành phần cốt lõi:**

1. **Anchor (truy vấn gốc):** chọn thành phẩm `100`; `required_qty = 1` vì đang tính cho một thành phẩm; `depth = 0`.
2. **Recursive member (bước đệ quy):** lấy mỗi dòng đang duyệt, tìm các con trực tiếp của nó, **nhân** số lượng lũy kế hiện tại với hệ số của cạnh, tăng chiều sâu thêm 1.
3. **Điều kiện kết thúc:** khi không còn quan hệ cha–con hợp lệ để mở rộng, không có dòng đệ quy mới. Có thể kèm giới hạn chiều sâu và cơ chế kiểm tra chu trình.

### Vì sao dùng UNION ALL?

Vì **mỗi đường đi tạo ra một đóng góp số lượng**. Nếu cùng linh kiện được sử dụng qua hai nhánh, cần giữ cả hai dòng để cộng đúng ở cuối.

`UNION ALL` giữ các dòng lặp; `UNION` sẽ tìm và loại các dòng trùng theo cột kết quả, có thể làm mất đóng góp hợp lệ và không phải cơ chế giải quyết chu trình đáng tin cậy.

Đặc biệt, nếu chỉ SELECT `part_id` mà bỏ các cột số lượng, độ sâu và đường đi, `UNION` có thể trộn những lần xuất hiện cùng linh kiện vào một dòng duy nhất — **sai cho nhu cầu định mức vật tư**.

### Kiểu dữ liệu của cột đệ quy

Các cột do anchor và recursive member trả về phải có kiểu tương thích theo quy tắc DBMS. Trong PostgreSQL, `1::numeric` làm cho `required_qty` mang kiểu `numeric` thay vì chỉ dùng phép nhân integer dễ tràn khi cây sâu.

Nếu số lượng chỉ là số nguyên nhỏ, `INTEGER` có thể đủ; nhưng khi có số lượng lớn, hệ số hao hụt hoặc định mức phân số, cần thiết kế kiểu `NUMERIC/DECIMAL` và độ chính xác phù hợp. Trong nhiều dialect, **kiểu của anchor quyết định/giới hạn kiểu kết quả của CTE**, vì vậy chuyển kiểu rõ ràng ngay ở anchor rất quan trọng.

## 5. Tạo dữ liệu BOM đầy đủ trên PostgreSQL

Chúng ta dùng hai bảng thực hành với tiền tố `sql226_`. Toàn bộ ví dụ ở các phần tiếp theo có thể chạy trên PostgreSQL sau khi tạo bảng và chèn dữ liệu dưới đây.

### 5.1. Bảng linh kiện

```sql
CREATE TABLE sql226_parts (
    part_id          INTEGER PRIMARY KEY,
    part_name        VARCHAR(100) NOT NULL,
    direct_unit_cost NUMERIC(12,2) NOT NULL DEFAULT 0
        CHECK (direct_unit_cost >= 0)
);
```

`direct_unit_cost` được định nghĩa là **chi phí trực tiếp của một đơn vị nút đó, chưa gồm chi phí các thành phần con**. Chúng ta sẽ cộng chi phí của mọi nút trên các đường đi để có tổng chi phí của một thành phẩm.

Đây là **chi phí trực tiếp**, không phải giá bán hay giá vốn đã cộng sẵn toàn bộ cấp dưới. Phân biệt này giúp tránh tính một bộ phận hai lần.

### 5.2. Bảng liên kết thành phần

```sql
CREATE TABLE sql226_bom (
    parent_part_id INTEGER NOT NULL
        REFERENCES sql226_parts(part_id),
    child_part_id  INTEGER NOT NULL
        REFERENCES sql226_parts(part_id),
    qty_per_parent INTEGER NOT NULL
        CHECK (qty_per_parent > 0),

    PRIMARY KEY (parent_part_id, child_part_id),
    CHECK (parent_part_id <> child_part_id)
);
```

Ràng buộc `CHECK (parent_part_id <> child_part_id)` ngăn **vòng lặp trực tiếp** `A → A`, nhưng **không ngăn vòng lặp dài** như `A → B → C → A`. Việc kiểm tra chu trình đầy đủ cần logic bổ sung.

`qty_per_parent > 0` cũng là lựa chọn của mô hình BOM lắp ráp đơn giản. Nếu bài toán có số lượng bằng 0, số âm để biểu diễn hàng trả lại hoặc định mức phân số, phải thiết kế ngữ nghĩa và ràng buộc riêng; không nên tùy tiện áp dụng cùng công thức mà không xét ý nghĩa.

### 5.3. Danh mục sản phẩm và chi phí

```sql
INSERT INTO sql226_parts
    (part_id, part_name, direct_unit_cost)
VALUES
    (100, 'Xe đạp',       0.00),
    (200, 'Bánh xe',      0.00),
    (210, 'Lốp',         40.00),
    (220, 'Vành',        60.00),
    (230, 'Căm',          3.00),
    (300, 'Khung',      150.00),
    (400, 'Bàn đạp',     20.00),
    (500, 'Ốc',           2.00),
    (600, 'Tay lái',     35.00),
    (900, 'Xe đạp mini',  0.00);
```

Ở ví dụ này:

- `Xe đạp` và `Bánh xe` có **chi phí trực tiếp = 0**, vì toàn bộ chi phí của chúng đến từ các thành phần con.
- `Khung` có chi phí trực tiếp `150` **và vẫn có con là Ốc**. Vì vậy, “có chi phí trực tiếp” **không đồng nghĩa** “nút lá”.
- `Xe đạp mini` sẽ dùng chung nhiều thành phần với xe đạp thường, minh họa truy vấn nhiều gốc.

Đơn vị tiền tệ trong bài là **đơn vị chi phí giả định**, không quy đổi ra một loại tiền thật cụ thể.

### 5.4. Định nghĩa quan hệ cha–con

```sql
INSERT INTO sql226_bom
    (parent_part_id, child_part_id, qty_per_parent)
VALUES
    -- Xe đạp thường:
    (100, 200,  2),  -- 2 bánh xe
    (100, 300,  1),  -- 1 khung
    (100, 400,  2),  -- 2 bàn đạp
    (100, 600,  1),  -- 1 tay lái
    (100, 500,  4),  -- 4 ốc ở cấp lắp ráp chính

    -- Một bánh xe:
    (200, 210,  1),  -- 1 lốp
    (200, 220,  1),  -- 1 vành
    (200, 230, 20),  -- 20 căm
    (200, 500,  4),  -- 4 ốc

    -- Một khung:
    (300, 500,  2),  -- 2 ốc

    -- Xe đạp mini: dùng chung bánh, khung, bàn đạp;
    -- không có tay lái riêng trong ví dụ đơn giản này.
    (900, 200,  2),
    (900, 300,  1),
    (900, 400,  2),
    (900, 500,  2);
```

Số dòng dự kiến:

```sql
SELECT COUNT(*) AS part_count FROM sql226_parts;
SELECT COUNT(*) AS bom_edge_count FROM sql226_bom;
```

Kết quả lần lượt là **10 nút linh kiện/thành phẩm** và **14 quan hệ cha–con**.

## 6. Duyệt BOM và nhân số lượng theo từng cấp

Đầu tiên, hãy xem từng **đường đi** từ xe đạp `100`. Truy vấn dưới đây có thêm `visited_ids` để theo dõi các nút đã đi qua **trên chính đường đi hiện tại**, đồng thời giới hạn chiều sâu để bảo vệ khỏi cấu trúc lỗi.

```sql
-- PostgreSQL:
WITH RECURSIVE explosion AS (
    SELECT
        p.part_id,
        p.part_name,
        0::integer AS depth,
        1::numeric AS required_qty,
        ARRAY[p.part_id] AS visited_ids
    FROM sql226_parts AS p
    WHERE p.part_id = 100

    UNION ALL

    SELECT
        child.part_id,
        child.part_name,
        e.depth + 1,
        e.required_qty * b.qty_per_parent,
        e.visited_ids || child.part_id
    FROM explosion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.part_id
    JOIN sql226_parts AS child
      ON child.part_id = b.child_part_id
    WHERE e.depth < 20
      AND NOT (child.part_id = ANY(e.visited_ids))
)
SELECT
    depth,
    array_to_string(visited_ids, ' > ') AS path,
    part_id,
    part_name,
    required_qty
FROM explosion
ORDER BY visited_ids;
```

Các dòng quan trọng cần thấy:

| Đường đi | depth | part_id | required_qty |
| --- | ---: | ---: | ---: |
| `100` | 0 | 100 | 1 |
| `100 > 200` | 1 | 200 | 2 |
| `100 > 200 > 210` | 2 | 210 | 2 |
| `100 > 200 > 220` | 2 | 220 | 2 |
| `100 > 200 > 230` | 2 | 230 | 40 |
| `100 > 200 > 500` | 2 | 500 | 8 |
| `100 > 300` | 1 | 300 | 1 |
| `100 > 300 > 500` | 2 | 500 | 2 |
| `100 > 400` | 1 | 400 | 2 |
| `100 > 500` | 1 | 500 | 4 |
| `100 > 600` | 1 | 600 | 1 |

Với bộ dữ liệu mẫu, CTE có **11 dòng đường đi**, bao gồm gốc. Linh kiện `500` xuất hiện **3 lần** vì có ba đường đi. Điều đó **đúng**; ta sẽ cộng chúng ở bước kế tiếp.

### Cách cập nhật accumulator trong từng bước

Giả sử đang đứng ở dòng:

```text
part_id = 200 (Bánh xe)
required_qty = 2
depth = 1
visited_ids = [100, 200]
```

Khi đi theo cạnh `200 → 230` có `qty_per_parent = 20`, recursive member tạo:

```text
part_id = 230 (Căm)
required_qty = 2 * 20 = 40
depth = 2
visited_ids = [100, 200, 230]
```

Khi đi theo cạnh `200 → 500` có số lượng 4, nó tạo:

```text
part_id = 500 (Ốc)
required_qty = 2 * 4 = 8
depth = 2
visited_ids = [100, 200, 500]
```

Cùng linh kiện ốc còn có các dòng qua khung và nhánh trực tiếp từ xe. **Không gộp chúng khi đệ quy đang đi từng đường đi**.

### Path được dùng để làm gì?

`visited_ids` có hai mục đích:

1. **Hiển thị đường đi** giúp giải thích nguồn gốc một số lượng lũy kế.
2. **Phát hiện lần lặp nút trên một đường đi** để không mở rộng vòng lặp vô hạn.

Điều kiện:

```sql
AND NOT (child.part_id = ANY(e.visited_ids))
```

chỉ chặn một nút nếu nó **đã có trên đường đi hiện tại**. Nó **không** chặn linh kiện `500` xuất hiện qua đường đi khác. Đó là điều bắt buộc khi cấu trúc là DAG.

**Lưu ý quan trọng:** điều kiện trên **bỏ qua cạnh tạo chu trình**, vì vậy truy vấn định mức có thể kết thúc mà không báo rõ rằng dữ liệu có chu trình. Trong hệ thống thật, cần có truy vấn **kiểm tra và cảnh báo cấu trúc lỗi** riêng (mục 13), không xem “query chạy xong” là bằng chứng BOM hợp lệ.

## 7. Cộng lũy kế khi cùng linh kiện xuất hiện nhiều nhánh

Sau khi nhân hệ số dọc từng đường đi, bước tiếp theo là **`GROUP BY part_id` và `SUM(required_qty)`**.

```sql
-- PostgreSQL: tổng số lượng mỗi linh kiện cho 1 xe đạp.
WITH RECURSIVE explosion AS (
    SELECT
        part_id,
        1::numeric AS required_qty,
        0 AS depth,
        ARRAY[part_id] AS visited_ids
    FROM sql226_parts
    WHERE part_id = 100

    UNION ALL

    SELECT
        b.child_part_id,
        e.required_qty * b.qty_per_parent,
        e.depth + 1,
        e.visited_ids || b.child_part_id
    FROM explosion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.part_id
    WHERE e.depth < 20
      AND NOT (b.child_part_id = ANY(e.visited_ids))
)
SELECT
    e.part_id,
    p.part_name,
    SUM(e.required_qty) AS total_required_qty
FROM explosion AS e
JOIN sql226_parts AS p
  ON p.part_id = e.part_id
WHERE e.depth > 0  -- loại nút gốc khỏi danh sách vật tư con
GROUP BY e.part_id, p.part_name
ORDER BY e.part_id;
```

Kết quả:

| part_id | part_name | total_required_qty |
| ---: | --- | ---: |
| 200 | Bánh xe | 2 |
| 210 | Lốp | 2 |
| 220 | Vành | 2 |
| 230 | Căm | 40 |
| 300 | Khung | 1 |
| 400 | Bàn đạp | 2 |
| 500 | Ốc | 14 |
| 600 | Tay lái | 1 |

Có **8 mã linh kiện/con** khác nhau, nhưng CTE gốc có **10 dòng sau khi loại gốc**, vì ốc xuất hiện qua nhiều nhánh. Sau `GROUP BY`, các đóng góp của ốc được cộng:

\[
14 = 8 + 2 + 4.
\]

### Vì sao không dùng COUNT(*)?

`COUNT(*)` của nhóm ốc sẽ trả **3** vì có ba dòng đường đi đến ốc. Nó không trả **14 ốc**. Muốn tính nhu cầu vật tư, dùng `SUM(required_qty)`.

### Vì sao không dùng DISTINCT?

`SELECT DISTINCT part_id` chỉ cho ta biết rằng có dùng **mã ốc 500**, không biết số lượng cần. Thậm chí `SUM(DISTINCT required_qty)` cũng không đúng về nguyên tắc: nếu hai đường đi khác nhau cùng cần `4` chiếc ốc, phép `SUM(DISTINCT ...)` chỉ cộng `4` **một lần**, làm thiếu số lượng.

Cần nhớ:

- **`COUNT(*)`:** số dòng đường đi xuất hiện trong nhóm.
- **`COUNT(DISTINCT part_id)`:** số mã linh kiện khác nhau.
- **`SUM(required_qty)`:** tổng số lượng vật tư từ mọi đường đi.

Đây là ba đại lượng khác nhau.

## 8. Tính tổng chi phí thành phẩm từ chi phí trực tiếp

Giả sử chi phí trực tiếp của linh kiện `p` là `cost(p)`. Nếu mỗi đường đi mang số lượng `Q(path)`, đóng góp chi phí tại cuối đường đi là:

\[
\text{pathCost} = Q(\text{path}) \times \text{directUnitCost}(p).
\]

Tổng chi phí cho **một thành phẩm gốc** là:

\[
\text{Cost(root)}
=
\sum_{\text{mọi dòng đường đi, kể cả gốc}}
Q(\text{path})\times\text{directUnitCost}(\text{node}).
\]

Công thức đúng khi **directUnitCost chỉ chứa chi phí trực tiếp tại nút đó, chưa cộng giá trị bộ phận con**. Với bảng mẫu, root và wheel có direct cost 0; khung có direct cost 150 dù khung còn có ốc phía dưới.

### Truy vấn chi phí đóng góp theo linh kiện

```sql
-- PostgreSQL:
WITH RECURSIVE explosion AS (
    SELECT
        part_id,
        1::numeric AS required_qty,
        ARRAY[part_id] AS visited_ids,
        0 AS depth
    FROM sql226_parts
    WHERE part_id = 100

    UNION ALL

    SELECT
        b.child_part_id,
        e.required_qty * b.qty_per_parent,
        e.visited_ids || b.child_part_id,
        e.depth + 1
    FROM explosion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.part_id
    WHERE e.depth < 20
      AND NOT (b.child_part_id = ANY(e.visited_ids))
)
SELECT
    p.part_id,
    p.part_name,
    SUM(e.required_qty) AS total_required_qty,
    p.direct_unit_cost,
    SUM(e.required_qty * p.direct_unit_cost) AS contributed_cost
FROM explosion AS e
JOIN sql226_parts AS p
  ON p.part_id = e.part_id
GROUP BY p.part_id, p.part_name, p.direct_unit_cost
ORDER BY p.part_id;
```

Ở đây **không loại nút gốc**: nếu sau này thành phẩm có thêm **chi phí lắp ráp trực tiếp** ở chính nút gốc, nó cũng phải được tính. Bộ dữ liệu hiện tại có chi phí trực tiếp của gốc bằng 0.

Kết quả chi phí quan trọng:

| Mã | Linh kiện | Số lượng lũy kế | Giá trực tiếp/đơn vị | Đóng góp |
| ---: | --- | ---: | ---: | ---: |
| 100 | Xe đạp | 1 | 0 | 0 |
| 200 | Bánh xe | 2 | 0 | 0 |
| 210 | Lốp | 2 | 40 | 80 |
| 220 | Vành | 2 | 60 | 120 |
| 230 | Căm | 40 | 3 | 120 |
| 300 | Khung | 1 | 150 | 150 |
| 400 | Bàn đạp | 2 | 20 | 40 |
| 500 | Ốc | 14 | 2 | 28 |
| 600 | Tay lái | 1 | 35 | 35 |
| **Tổng** | | | | **573** |

### Truy vấn chỉ lấy một tổng tiền

```sql
WITH RECURSIVE explosion AS (
    SELECT
        part_id,
        1::numeric AS required_qty,
        ARRAY[part_id] AS visited_ids,
        0 AS depth
    FROM sql226_parts
    WHERE part_id = 100

    UNION ALL

    SELECT
        b.child_part_id,
        e.required_qty * b.qty_per_parent,
        e.visited_ids || b.child_part_id,
        e.depth + 1
    FROM explosion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.part_id
    WHERE e.depth < 20
      AND NOT (b.child_part_id = ANY(e.visited_ids))
)
SELECT
    SUM(e.required_qty * p.direct_unit_cost) AS cost_per_bicycle
FROM explosion AS e
JOIN sql226_parts AS p
  ON p.part_id = e.part_id;
```

Trên dữ liệu mẫu, `cost_per_bicycle = 573.00`.

### Kiểm tra bằng phép tính thủ công

```text
2 lốp        × 40  =  80
2 vành       × 60  = 120
40 căm       ×  3  = 120
1 khung      ×150  = 150
2 bàn đạp    × 20  =  40
14 ốc        ×  2  =  28
1 tay lái    × 35  =  35
-------------------------
Tổng                  573
```

Với một chiếc xe, chi phí hai bánh xe cũng có thể tính theo **một bánh**:

```text
1 bánh xe: 1 lốp 40 + 1 vành 60 + 20 căm 60 + 4 ốc 8 = 168
2 bánh xe: 2 × 168 = 336

Phần còn lại:
Khung trực tiếp 150 + 2 ốc khung 4
+ 2 bàn đạp 40 + 1 tay lái 35 + 4 ốc gốc 8
= 237

Tổng: 336 + 237 = 573
```

Hai cách kiểm tra cho cùng kết quả vì các hệ số được nhân đúng theo đường đi rồi cộng tất cả chi phí trực tiếp.

## 9. Chi phí trực tiếp khác chi phí đã gồm linh kiện con

Đây là một lỗi dữ liệu có thể gây sai số lớn hơn lỗi cú pháp SQL.

Giả sử một bánh xe **có giá thành hoàn chỉnh 168**, đã bao gồm lốp, vành, căm và ốc. Nếu ghi `direct_unit_cost = 168` cho bánh xe mà vẫn duyệt và cộng tiếp chi phí của tất cả con, SQL sẽ **tính trùng toàn bộ thành phần của bánh xe**.

Hai mô hình giá thành khác nhau:

| Mô hình | Giá trị lưu trên node Bánh xe | Có cộng chi phí con? |
| --- | --- | --- |
| **Chi phí trực tiếp từng node** | Chỉ chi phí riêng của công đoạn bánh xe, ví dụ 0 hoặc tiền công lắp bánh | Có, cộng tất cả node và con |
| **Giá hoàn chỉnh một cụm** | 168 đã gồm lốp/vành/căm/ốc | Không cộng lại các thành phần con của cụm đó khi dùng giá hoàn chỉnh |

Nếu mua nguyên cụm bánh xe từ nhà cung cấp với giá 168 và **không xuất kho từng vật tư bên trong**, có thể xem bánh xe là một **lá đối với cấu hình chi phí/sản xuất đang xét**. Nếu lắp bánh tại xưởng từ vật tư con, tính theo vật tư và chi phí công đoạn.

**Không thể tự suy ra chính sách này từ cấu trúc cha–con.** Cần biết cột chi phí có nghĩa là `direct_unit_cost` hay `rolled_up_unit_cost`, và BOM có được “mở” tại nút đó hay không.

### Nếu chỉ tính chi phí ở lá thì sao?

Một số hệ lưu giá chỉ ở **các node không có con**. Khi đó có thể lọc node lá bằng `NOT EXISTS`. Nhưng **bảng thực hành này không tuân hoàn toàn quy tắc ấy**: khung `300` có chi phí 150 và có con là ốc.

Nếu chỉ cộng các node lá, bạn sẽ bỏ mất **150 tiền khung**. Vì vậy, truy vấn ở mục 8 cố ý cộng **chi phí trực tiếp của mọi node**, không chỉ lá.

## 10. Nhu cầu cho nhiều thành phẩm: thêm root_id

Bài toán thực tế thường có nhiều sản phẩm cùng dùng một bộ phận. Ta có thể đưa **mã gốc** vào CTE để biết một dòng lũy kế thuộc thành phẩm nào.

Trong dữ liệu mẫu:

- `100` là **Xe đạp**.
- `900` là **Xe đạp mini**.

Cả hai cùng dùng bánh xe, khung, bàn đạp và ốc; cấu trúc mini không có tay lái, đồng thời chỉ dùng hai ốc trực tiếp ở cấp gốc.

```sql
-- PostgreSQL: tính giá thành cho cả hai sản phẩm.
WITH RECURSIVE explosion AS (
    SELECT
        p.part_id AS root_part_id,
        p.part_id AS current_part_id,
        1::numeric AS required_qty,
        0 AS depth,
        ARRAY[p.part_id] AS visited_ids
    FROM sql226_parts AS p
    WHERE p.part_id IN (100, 900)

    UNION ALL

    SELECT
        e.root_part_id,
        b.child_part_id,
        e.required_qty * b.qty_per_parent,
        e.depth + 1,
        e.visited_ids || b.child_part_id
    FROM explosion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.current_part_id
    WHERE e.depth < 20
      AND NOT (b.child_part_id = ANY(e.visited_ids))
)
SELECT
    e.root_part_id,
    root.part_name AS product_name,
    SUM(e.required_qty * component.direct_unit_cost)
        AS cost_per_finished_unit
FROM explosion AS e
JOIN sql226_parts AS root
  ON root.part_id = e.root_part_id
JOIN sql226_parts AS component
  ON component.part_id = e.current_part_id
GROUP BY e.root_part_id, root.part_name
ORDER BY e.root_part_id;
```

Kết quả:

| root_part_id | product_name | cost_per_finished_unit |
| ---: | --- | ---: |
| 100 | Xe đạp | **573.00** |
| 900 | Xe đạp mini | **534.00** |

### Phân tích giá xe mini

```text
2 bánh xe hoàn chỉnh theo công thức trực tiếp: 2 × 168 = 336
1 khung: 150 + 2 ốc × 2 = 154
2 bàn đạp × 20 = 40
2 ốc cấp gốc × 2 = 4
Tổng: 336 + 154 + 40 + 4 = 534
```

Báo cáo nhiều sản phẩm phải nhóm **theo root_part_id**. Nếu bỏ cột gốc khỏi `GROUP BY`, nhu cầu của xe thường và xe mini sẽ bị cộng lẫn, không còn thể hiện “một sản phẩm cần bao nhiêu”.

### Tổng số lượng một linh kiện theo từng sản phẩm

```sql
WITH RECURSIVE explosion AS (
    SELECT
        part_id AS root_part_id,
        part_id AS current_part_id,
        1::numeric AS required_qty,
        0 AS depth,
        ARRAY[part_id] AS visited_ids
    FROM sql226_parts
    WHERE part_id IN (100, 900)

    UNION ALL

    SELECT
        e.root_part_id,
        b.child_part_id,
        e.required_qty * b.qty_per_parent,
        e.depth + 1,
        e.visited_ids || b.child_part_id
    FROM explosion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.current_part_id
    WHERE e.depth < 20
      AND NOT (b.child_part_id = ANY(e.visited_ids))
)
SELECT
    root_part_id,
    current_part_id AS component_id,
    SUM(required_qty) AS qty_per_finished_unit
FROM explosion
WHERE depth > 0
GROUP BY root_part_id, current_part_id
ORDER BY root_part_id, current_part_id;
```

Với ốc `500`:

| root_part_id | component_id | qty_per_finished_unit |
| ---: | ---: | ---: |
| 100 | 500 | 14 |
| 900 | 500 | 12 |

Cả hai đều dùng chung mã ốc, nhưng **định mức khác nhau**.

## 11. Từ định mức mỗi thành phẩm đến nhu cầu cho một đơn sản xuất

Giả sử xưởng nhận:

| Thành phẩm | Số lượng đặt làm |
| --- | ---: |
| Xe đạp thường (100) | 10 |
| Xe đạp mini (900) | 5 |

Nhu cầu ốc:

\[
10 \times 14 + 5 \times 12 = 200.
\]

Nhu cầu căm:

\[
10 \times 40 + 5 \times 40 = 600.
\]

Trong SQL, có thể tạo danh sách số lượng sản xuất rồi **đưa số lượng đó vào anchor**. Khi đó `required_qty` tại nút gốc không còn là 1, mà là số đơn vị thành phẩm được yêu cầu.

```sql
-- PostgreSQL: danh sách đơn sản xuất minh họa dùng VALUES.
WITH RECURSIVE
production_plan(root_part_id, finished_qty) AS (
    VALUES
        (100, 10::numeric),
        (900,  5::numeric)
),
explosion AS (
    SELECT
        plan.root_part_id,
        plan.root_part_id AS current_part_id,
        plan.finished_qty AS required_qty,
        0 AS depth,
        ARRAY[plan.root_part_id] AS visited_ids
    FROM production_plan AS plan

    UNION ALL

    SELECT
        e.root_part_id,
        b.child_part_id,
        e.required_qty * b.qty_per_parent,
        e.depth + 1,
        e.visited_ids || b.child_part_id
    FROM explosion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.current_part_id
    WHERE e.depth < 20
      AND NOT (b.child_part_id = ANY(e.visited_ids))
)
SELECT
    e.current_part_id AS component_id,
    p.part_name,
    SUM(e.required_qty) AS total_for_production_plan
FROM explosion AS e
JOIN sql226_parts AS p
  ON p.part_id = e.current_part_id
WHERE e.depth > 0
GROUP BY e.current_part_id, p.part_name
ORDER BY e.current_part_id;
```

Trong kết quả:

- `Căm (230) = 600`.
- `Ốc (500) = 200`.
- `Bánh xe (200) = 30`.
- `Lốp (210) = 30`.
- `Vành (220) = 30`.
- `Bàn đạp (400) = 30`.
- `Tay lái (600) = 10`.

Khi đơn sản xuất có **nhiều dòng riêng cho cùng root**, ví dụ hai lệnh đều đặt xe thường, cần quyết định có **gộp `finished_qty` theo root trước** hay giữ mã lệnh sản xuất để theo dõi nguồn gốc nhu cầu. Nếu muốn báo cáo theo từng đơn, hãy mang theo `production_order_id` trong CTE và nhóm theo ID đơn phù hợp.

### Tổng chi phí kế hoạch sản xuất

Tổng chi phí theo giá hiện tại của bảng mẫu:

\[
10\times573 + 5\times534 = 8400.
\]

Có thể thay phần SELECT cuối bằng:

```sql
SELECT
    SUM(e.required_qty * p.direct_unit_cost)
        AS total_production_plan_cost
FROM explosion AS e
JOIN sql226_parts AS p
  ON p.part_id = e.current_part_id;
```

Đoạn cuối là **SELECT thay thế** trong cùng khối `WITH RECURSIVE ...` ở ví dụ phía trên, không phải câu SQL độc lập khi chạy tách riêng. Kết quả kỳ vọng là **8400.00**.

## 12. Tính giá thành đơn vị của mọi cụm lắp ráp

Đến đây ta đã tính cho các gốc `100` và `900`. Nếu cần báo cáo **giá hoàn chỉnh của bất kỳ cụm nào**, ví dụ một bánh xe, ta có thể bắt đầu một đường đi tại **mỗi linh kiện** rồi tính tất cả phần chi phí bên dưới nó.

Đây là cách viết dễ hiểu cho khái niệm **roll-up cost**:

```sql
-- PostgreSQL: giá hoàn chỉnh của từng cụm, tính từ mọi chi phí trực tiếp.
WITH RECURSIVE expansion AS (
    SELECT
        p.part_id AS assembly_id,
        p.part_id AS current_part_id,
        1::numeric AS multiplier,
        0 AS depth,
        ARRAY[p.part_id] AS visited_ids
    FROM sql226_parts AS p

    UNION ALL

    SELECT
        e.assembly_id,
        b.child_part_id,
        e.multiplier * b.qty_per_parent,
        e.depth + 1,
        e.visited_ids || b.child_part_id
    FROM expansion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.current_part_id
    WHERE e.depth < 20
      AND NOT (b.child_part_id = ANY(e.visited_ids))
)
SELECT
    assembly.part_id,
    assembly.part_name,
    SUM(e.multiplier * component.direct_unit_cost)
        AS rolled_up_unit_cost
FROM expansion AS e
JOIN sql226_parts AS assembly
  ON assembly.part_id = e.assembly_id
JOIN sql226_parts AS component
  ON component.part_id = e.current_part_id
GROUP BY assembly.part_id, assembly.part_name
ORDER BY assembly.part_id;
```

Một số kết quả:

| assembly_id | Tên | rolled_up_unit_cost |
| ---: | --- | ---: |
| 100 | Xe đạp | **573.00** |
| 200 | Bánh xe | **168.00** |
| 300 | Khung | **154.00** |
| 500 | Ốc | **2.00** |
| 900 | Xe đạp mini | **534.00** |

### “Tính cho mỗi cụm” khác “cộng tất cả giá cụm”

`rolled_up_unit_cost` của bánh xe đã chứa chi phí lốp, vành, căm và ốc. `rolled_up_unit_cost` của xe đạp đã chứa chi phí **hai bánh xe**. Vì vậy, **không lấy giá xe đạp 573 rồi cộng thêm giá bánh xe 168**: đó là cộng lại phần đã nằm trong giá xe.

Bảng `rolled_up_unit_cost` hữu ích khi cần tra giá một cụm theo định mức hiện hành, nhưng giá của các cụm **có quan hệ tổ tiên–hậu duệ** không phải những phần tử chi phí độc lập có thể cộng tùy ý.

### Chi phí tính cho tất cả gốc có thể lớn

Với một BOM lớn có nhiều cụm tái sử dụng, bắt đầu từ **mọi node** khiến nhiều đường đi được tính lặp lại. Truy vấn trên thích hợp để hiểu kỹ thuật hoặc tính theo batch có giới hạn; sản xuất quy mô lớn có thể cần lưu kết quả roll-up theo phiên bản BOM, tính tăng dần khi thay đổi cấu trúc, hoặc sử dụng chiến lược xử lý DAG được tối ưu hóa.

## 13. Một cách nhìn khác: truyền chi phí từ linh kiện lên các tổ tiên

Các ví dụ trước **đi từ gốc xuống con**, mang theo tích số lượng. Có thể tiếp cận từ **chi phí trực tiếp của từng nút**, rồi đi **ngược từ con lên cha** để phân bổ đóng góp cho mọi cụm tổ tiên.

Cách này làm rõ ý tưởng “tính lũy kế lên cấp trên”:

```sql
-- PostgreSQL: chỉ bắt đầu từ nút có chi phí trực tiếp > 0.
WITH RECURSIVE contributions AS (
    SELECT
        p.part_id AS cost_source_id,
        p.part_id AS assembly_id,
        1::numeric AS multiplier,
        ARRAY[p.part_id] AS visited_ids,
        0 AS depth
    FROM sql226_parts AS p
    WHERE p.direct_unit_cost > 0

    UNION ALL

    SELECT
        e.cost_source_id,
        b.parent_part_id AS assembly_id,
        e.multiplier * b.qty_per_parent,
        e.visited_ids || b.parent_part_id,
        e.depth + 1
    FROM contributions AS e
    JOIN sql226_bom AS b
      ON b.child_part_id = e.assembly_id
    WHERE e.depth < 20
      AND NOT (b.parent_part_id = ANY(e.visited_ids))
)
SELECT
    a.part_id AS assembly_id,
    a.part_name,
    COALESCE(
        SUM(e.multiplier * source.direct_unit_cost),
        0
    ) AS rolled_up_unit_cost
FROM sql226_parts AS a
LEFT JOIN contributions AS e
  ON e.assembly_id = a.part_id
LEFT JOIN sql226_parts AS source
  ON source.part_id = e.cost_source_id
GROUP BY a.part_id, a.part_name
ORDER BY a.part_id;
```

Giải thích theo một dòng nguồn là **căm `230`, chi phí trực tiếp 3**:

1. Ở chính căm, multiplier = 1 ⇒ đóng góp `1 × 3 = 3` cho một căm.
2. Đi từ căm lên bánh xe theo cạnh `200 → 230` có hệ số 20 ⇒ một bánh xe nhận `20 × 3 = 60` tiền căm.
3. Đi từ bánh xe lên xe thường theo cạnh `100 → 200` có hệ số 2 ⇒ một xe thường nhận `2 × 20 × 3 = 120` tiền căm.
4. Đi từ bánh xe lên xe mini theo `900 → 200` cũng có hệ số 2 ⇒ một xe mini nhận `120` tiền căm.

Cả hai hướng đều dùng **tích hệ số trên đường đi**; hướng đi quyết định **cột ID nào được giữ cố định**:

- Top-down: giữ `root_part_id`, đi tới `current_part_id`.
- Bottom-up: giữ `cost_source_id`, đi tới các `assembly_id` tổ tiên.

Kết quả roll-up với dữ liệu hợp lệ phải phù hợp với cách tính từ trên xuống. Đây là hai cách mô hình hóa cùng công thức, không phải hai công thức giá thành khác nhau.

**Lưu ý:** bảng `contributions` có thể không có dòng cho một cụm hoàn toàn không có nguồn chi phí dương; `LEFT JOIN` và `COALESCE(...,0)` giúp báo cáo vẫn hiển thị cụm đó với 0 theo quy ước chi phí hiện tại.

## 14. Cách tính “cộng dồn” của BOM khác running total bằng window function

Trong SQL, “lũy kế” còn có một nghĩa khác: **cộng dồn theo thứ tự dòng** như doanh thu ngày 1, ngày 2, ngày 3. Công cụ thường dùng là:

```sql
SUM(amount) OVER (
    ORDER BY event_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Đây là **running total theo thứ tự**, không tự lần theo quan hệ cha–con.

| Nhu cầu | Cơ chế chính | Ví dụ |
| --- | --- | --- |
| Nhân số lượng qua nhiều cấp cha–con | Recursive CTE mang accumulator | 2 bánh × 20 căm = 40 căm/xe |
| Cộng đóng góp từ nhiều đường đi đến cùng linh kiện | `GROUP BY` + `SUM(required_qty)` sau recursive CTE | 8 + 2 + 4 = 14 ốc |
| Cộng chi phí trực tiếp của mọi node thuộc một cụm | Đệ quy mở cấu trúc + `SUM(qty × direct_cost)` | 573/xe |
| Cộng dồn giá trị của các dòng đã được sắp xếp | Window `SUM(...) OVER (ORDER BY ...)` | Doanh thu tích lũy theo ngày |

Hai kỹ thuật có thể kết hợp. Ví dụ sau khi “nổ” BOM thành các dòng chi phí theo đường đi, ta muốn xem **tổng chi phí đã cộng đến mỗi dòng trong thứ tự đường đi**:

```sql
-- PostgreSQL: minh họa running total trên kết quả đã duyệt BOM.
WITH RECURSIVE expansion AS (
    SELECT
        part_id,
        1::numeric AS required_qty,
        ARRAY[part_id] AS path_ids,
        0 AS depth
    FROM sql226_parts
    WHERE part_id = 100

    UNION ALL

    SELECT
        b.child_part_id,
        e.required_qty * b.qty_per_parent,
        e.path_ids || b.child_part_id,
        e.depth + 1
    FROM expansion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.part_id
    WHERE e.depth < 20
      AND NOT (b.child_part_id = ANY(e.path_ids))
),
cost_rows AS (
    SELECT
        e.path_ids,
        e.part_id,
        e.required_qty * p.direct_unit_cost AS contributed_cost
    FROM expansion AS e
    JOIN sql226_parts AS p
      ON p.part_id = e.part_id
)
SELECT
    array_to_string(path_ids, ' > ') AS path,
    part_id,
    contributed_cost,
    SUM(contributed_cost) OVER (
        ORDER BY path_ids
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_cost
FROM cost_rows
ORDER BY path_ids;
```

`running_cost` có thể kết thúc ở 573 khi duyệt đủ mọi đóng góp, nhưng **giá trị trung gian phụ thuộc vào thứ tự `path_ids` mà ta chọn để trình bày**. Nó không có nghĩa “tổng giá thành của cây con tại node hiện tại”.

Nếu mục tiêu là giá của **mỗi cụm con**, dùng phương pháp roll-up ở mục 12/13, không nhầm với `SUM(...) OVER (...)` sắp xếp các dòng.

## 15. Chu trình: kiểm tra cấu trúc trước khi tin kết quả

BOM hợp lệ thường **không được có chu trình**. Ví dụ:

```text
Xe đạp (100)
    ↓
Bánh xe (200)
    ↓
Căm (230)
    ↓
Xe đạp (100)   ← chu trình sai
```

Không thể định nghĩa nhu cầu vật tư hữu hạn bằng công thức sản xuất thông thường nếu một chiếc xe cần bánh, bánh cần căm, rồi căm lại cần xe. Một recursive CTE không có điều kiện chống chu trình có thể lặp rất lâu, gặp giới hạn recursion của DBMS hoặc tăng số lượng khổng lồ.

### 15.1. Phát hiện chu trình thay vì im lặng bỏ qua

Ví dụ PostgreSQL dưới đây **cố ý tạo dòng đánh dấu chu trình**, rồi ngừng mở rộng nhánh sau khi gặp chu trình. Khác với câu ở mục 6, nó cho biết **đường đi nào có vấn đề**.

```sql
-- PostgreSQL: kiểm tra chu trình trong cấu trúc từ một gốc.
WITH RECURSIVE walk AS (
    SELECT
        p.part_id,
        ARRAY[p.part_id] AS visited_ids,
        0 AS depth,
        false AS is_cycle
    FROM sql226_parts AS p
    WHERE p.part_id = 100

    UNION ALL

    SELECT
        b.child_part_id,
        w.visited_ids || b.child_part_id,
        w.depth + 1,
        b.child_part_id = ANY(w.visited_ids) AS is_cycle
    FROM walk AS w
    JOIN sql226_bom AS b
      ON b.parent_part_id = w.part_id
    WHERE NOT w.is_cycle
      AND w.depth < 20
)
SELECT
    array_to_string(visited_ids, ' > ') AS cycle_path,
    depth
FROM walk
WHERE is_cycle
ORDER BY visited_ids;
```

Trên dữ liệu mẫu, truy vấn trả **0 dòng**, vì các cạnh đã chèn không tạo chu trình.

### 15.2. Thử nghiệm thêm chu trình rồi ROLLBACK

Chỉ thử trong **database thực hành do bạn quản lý**:

```sql
BEGIN;

-- Sai nghiệp vụ: Căm lại chứa Xe đạp.
INSERT INTO sql226_bom
    (parent_part_id, child_part_id, qty_per_parent)
VALUES (230, 100, 1);

-- Chạy lại truy vấn kiểm tra chu trình ở mục 15.1.
-- Nó sẽ nhận diện đường đi 100 > 200 > 230 > 100.

ROLLBACK;
```

Sau `ROLLBACK`, cạnh `230 → 100` bị hủy và cấu trúc trở lại hợp lệ.

**Giới hạn chiều sâu `depth < 20` chỉ là cơ chế an toàn**, không tự xác thực toàn bộ BOM. Nếu có một cấu trúc hợp lệ sâu hơn 20 cấp, phép tính bị cắt ngắn và thiếu vật tư. Nếu chu trình chỉ bộc lộ ở độ sâu lớn hơn giới hạn, câu kiểm tra cũng có thể **không phát hiện**. Hệ thống cần ràng buộc dữ liệu, chính sách chiều sâu có căn cứ và quy trình phát hiện chu trình đầy đủ.

### 15.3. Kiểm tra tất cả gốc hoặc mọi nút

Nếu chỉ bắt đầu từ `100`, truy vấn phát hiện những chu trình **có thể đi tới từ 100**. Chu trình ở một thành phẩm khác hoặc một cụm chưa được lắp vào `100` sẽ không được nhìn thấy.

Để kiểm tra toàn bộ mô hình, có thể chạy một truy vấn khởi đầu từ **mọi node**, hoặc kiểm tra DAG bằng logic chuyên dụng ở tầng dịch vụ khi thêm/sửa quan hệ. Điều này có thể tạo nhiều đường đi và tốn tài nguyên trên BOM lớn; chọn quy trình kiểm định thích hợp thay vì dùng một câu SQL chưa giới hạn trên dữ liệu sản xuất.

Một số DBMS cung cấp cú pháp `CYCLE` hay cơ chế dò vòng lặp riêng trong recursive query; khả năng hỗ trợ khác nhau theo phiên bản.

## 16. Không dùng “visited toàn cục” để loại các linh kiện dùng chung

Có một sự khác biệt quan trọng giữa **tránh chu trình** và **tránh duyệt một nút nhiều lần**.

Trong thuật toán tìm đường đi/đệ quy thông thường, người viết có thể muốn đánh dấu “đã thấy node 500 rồi thì không duyệt node 500 lần nữa”. Điều đó phù hợp cho bài toán **đếm số node phân biệt**, nhưng **sai** với BOM cần tổng số lượng linh kiện.

Ví dụ:

```text
100 → 200 → 500 : 8 ốc
100 → 300 → 500 : 2 ốc
100 → 500       : 4 ốc
```

Nếu giữ một tập `visited_part_ids` **dùng chung cho toàn bộ các nhánh**, sau khi thấy ốc lần đầu, bạn có thể chặn hai lần sau và báo thiếu số ốc.

Trong `WITH RECURSIVE` của bài, `visited_ids` được **mang theo trên từng dòng đường đi**, nên:

- Ốc được chấp nhận ở ba đường đi khác nhau.
- Chỉ đường đi **quay lại chính ID đã xuất hiện trong cùng đường đó** mới bị coi là chu trình.
- `UNION ALL` giữ đủ mọi đóng góp, `GROUP BY` sau cùng cộng chúng.

**Nếu một node xuất hiện nhiều lần trong kết quả vì có nhiều tổ tiên/đường đi**, đó chưa chắc là lỗi dữ liệu. Hãy kiểm tra ý nghĩa các đường đi và số lượng nhân, thay vì loại trùng một cách máy móc.

## 17. Nút lá, nút trung gian và hàng mua ngoài

Trong BOM, người ta thường phân biệt:

- **Nút trung gian/cụm lắp ráp**: có ít nhất một cạnh đi tới con.
- **Nút lá**: không có cạnh con trong BOM được xét.
- **Hàng mua ngoài**: một vật tư hoặc cụm được mua từ bên ngoài, có thể được xem là lá trong một phương án sản xuất nhưng là nút có con trong một phương án khác.

Để liệt kê các node lá dưới xe đạp `100`:

```sql
WITH RECURSIVE expansion AS (
    SELECT
        part_id,
        1::numeric AS required_qty,
        ARRAY[part_id] AS visited_ids,
        0 AS depth
    FROM sql226_parts
    WHERE part_id = 100

    UNION ALL

    SELECT
        b.child_part_id,
        e.required_qty * b.qty_per_parent,
        e.visited_ids || b.child_part_id,
        e.depth + 1
    FROM expansion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.part_id
    WHERE e.depth < 20
      AND NOT (b.child_part_id = ANY(e.visited_ids))
)
SELECT
    e.part_id,
    p.part_name,
    SUM(e.required_qty) AS total_leaf_qty
FROM expansion AS e
JOIN sql226_parts AS p
  ON p.part_id = e.part_id
WHERE NOT EXISTS (
    SELECT 1
    FROM sql226_bom AS b
    WHERE b.parent_part_id = e.part_id
)
GROUP BY e.part_id, p.part_name
ORDER BY e.part_id;
```

Kết quả bao gồm `Lốp`, `Vành`, `Căm`, `Bàn đạp`, `Ốc`, `Tay lái`. **Khung không phải nút lá** vì có quan hệ tới ốc, dù khung có chi phí trực tiếp 150.

### Số lượng ở lá không đủ để tính mọi loại chi phí

Nếu danh mục chỉ lưu giá trực tiếp của hàng mua ngoài ở lá, tổng chi phí lá có thể đại diện cho giá vật tư. Nhưng nếu các node trung gian có **công lắp ráp trực tiếp** hoặc chi phí gia công riêng, báo cáo leaf-only sẽ bỏ mất phần đó.

Trong bảng mẫu, lấy tổng chi phí **chỉ của lá** sẽ làm thiếu 150 tiền khung. Do đó phải xác định rõ một báo cáo đang hỏi:

- “Cần mua bao nhiêu linh kiện lá?”
- “Cần bao nhiêu cụm ở mọi cấp để lắp ráp?”
- “Chi phí nguyên vật liệu mua ngoài là bao nhiêu?”
- “Tổng chi phí trực tiếp của cả quy trình là bao nhiêu?”

Bốn câu hỏi liên quan cùng một BOM nhưng **không nhất thiết dùng cùng phép lọc node trước khi SUM**.

## 18. BOM theo phiên bản và ngày hiệu lực

Trong thực tế, một mã thành phẩm có thể có **nhiều phiên bản cấu trúc**:

- Trước ngày 01/06, một cụm dùng 4 ốc.
- Từ ngày 01/06, nhà máy đổi thiết kế, cần 6 ốc.
- Một số đơn sản xuất đã duyệt vẫn phải dùng BOM cũ.
- Cùng sản phẩm có nhiều cấu hình theo nhà máy, thị trường hoặc khách hàng.

Nếu bảng BOM lưu cả lịch sử quan hệ, recursive CTE phải biết **phiên bản áp dụng cho từng cạnh**. Truy vấn dùng toàn bộ các dòng lịch sử mà không lọc sẽ có thể **nhân số lượng sai**.

### Ví dụ mô hình có hiệu lực

Một thiết kế có thể mở rộng:

```sql
-- Ví dụ khung mô hình, không chạy trên bảng sql226_bom đã tạo.
CREATE TABLE bom_versioned (
    bom_line_id    BIGINT PRIMARY KEY,
    parent_part_id INTEGER NOT NULL,
    child_part_id  INTEGER NOT NULL,
    qty_per_parent NUMERIC(18,6) NOT NULL,
    valid_from     DATE NOT NULL,
    valid_to       DATE,
    revision_code  VARCHAR(30) NOT NULL
);
```

Khi tính BOM tại ngày `:as_of_date`, cần lọc quan hệ có hiệu lực, ví dụ:

```sql
-- Mẫu điều kiện; :as_of_date là tham số do ứng dụng bind.
WHERE b.valid_from <= :as_of_date
  AND (b.valid_to IS NULL OR :as_of_date < b.valid_to)
```

Đây là quy ước khoảng **`[valid_from, valid_to)`**: đầu khoảng được tính, cuối khoảng không được tính. Ứng dụng phải thống nhất cách hiểu ngày hiệu lực và xử lý dòng phiên bản chồng lấn.

**Quan trọng:** nếu chỉ lọc ở anchor nhưng recursive member vẫn đọc mọi phiên bản cạnh, kết quả cấp sâu sẽ trộn các định mức thuộc các phiên bản khác nhau. Cần áp dụng quy tắc hiệu lực **cho mọi cạnh được đi qua**, hoặc tạo một tập BOM hiệu lực đã chọn trước rồi đệ quy trên chính tập đó.

### Đơn vị đo và tỷ lệ hao hụt

Bảng ví dụ dùng số lượng nguyên và cùng đơn vị. Dữ liệu thật có thể dùng `kg`, `m`, `cái`, `lít`, và hệ số chuyển đổi giữa đơn vị của cha–con.

Nếu một cạnh có hệ số hao hụt `s`, số lượng cần không nhất thiết chỉ bằng `q` mà có thể phụ thuộc công thức của nghiệp vụ. Ví dụ một quy tắc đơn giản là nhân `q/(1-s)` khi `0 <= s < 1`, nhưng cách tính thực tế có thể cần làm tròn theo cấp phát hoặc theo lô. **Không tự đưa hao hụt vào `qty_per_parent` mà không thống nhất định nghĩa.**

## 19. Giới hạn số lượng, overflow và làm tròn

Trong truy vấn đệ quy, hệ số được **nhân ở mỗi cấp**, nên số có thể tăng rất nhanh.

Ví dụ một cấu trúc sâu 10 cấp, mỗi cạnh có hệ số 100:

\[
100^{10} = 10^{20}.
\]

Giá trị này vượt giới hạn của nhiều kiểu số nguyên 32-bit và 64-bit. Nếu dùng kiểu số quá nhỏ, kết quả có thể lỗi tràn hoặc sai theo cách xử lý của DBMS.

### Chọn NUMERIC/DECIMAL phù hợp

Ở PostgreSQL, `1::numeric` cho phép số lượng lũy kế dùng kiểu `numeric` linh hoạt. Tuy nhiên, điều đó **không** loại bỏ mọi giới hạn thực tế về thời gian, bộ nhớ và số chữ số có thể xử lý.

Ở SQL Server, MySQL/MariaDB và Oracle, `DECIMAL(p,s)` hoặc `NUMBER` có các quy tắc về precision/scale khác nhau; kết quả của phép nhân có thể cần `CAST` tường minh về kiểu chung ở mỗi lần đệ quy.

Nếu số lượng vật tư là phân số, ví dụ `0.25 kg` mỗi cụm, phép nhân nên dùng số thập phân chính xác thay vì số thực dấu phẩy động khi yêu cầu sai số chặt.

### Đừng làm tròn quá sớm

Giả sử một cấp cần `0.333 kg` và có 3 cấp/cụm liên quan. Nếu làm tròn mỗi bước về số nguyên trước khi nhân và cộng, số lượng có thể sai đáng kể.

Nên phân biệt:

1. **Số lượng lý thuyết:** tích các hệ số định mức với độ chính xác đủ cao.
2. **Số lượng xuất kho:** áp dụng quy tắc đóng gói, cắt, làm tròn theo **cấp vật tư hoặc lệnh sản xuất**.
3. **Số lượng mua:** thêm tồn kho, hao hụt, số lượng đặt tối thiểu và đơn vị mua hàng.

`ROUND` có thể phù hợp tại bước cuối hoặc theo quy tắc nghiệp vụ được định nghĩa. Không mặc nhiên `ROUND(required_qty)` trong từng recursive member.

## 20. NULL và dữ liệu thiếu trong tính lũy kế

Trong bảng mẫu, `qty_per_parent` là `NOT NULL` và lớn hơn 0; `direct_unit_cost` cũng là `NOT NULL`. Những ràng buộc này giúp công thức đơn giản và hạn chế kết quả không rõ nghĩa.

Nếu dữ liệu thật cho phép `NULL`:

```sql
e.required_qty * b.qty_per_parent
```

sẽ thường trả `NULL` khi `b.qty_per_parent IS NULL`. Các cấp sâu hơn có thể tiếp tục mang `NULL`. Đến khi `SUM`, SQL **bỏ qua giá trị NULL**, nên tổng tiền hoặc tổng số lượng có thể bị **thiếu mà không có thông báo rõ ràng**.

### COALESCE không luôn là giải pháp đúng

Ví dụ:

```sql
COALESCE(b.qty_per_parent, 1)
```

đang giả định **thiếu định mức nghĩa là cần đúng một đơn vị**. Đó có thể là một giả định sai rất nghiêm trọng.

Tương tự:

```sql
COALESCE(p.direct_unit_cost, 0)
```

sẽ coi **thiếu giá** là giá bằng 0. Nếu đó là chính sách báo cáo “giá chưa cập nhật tạm tính bằng 0”, cần nêu rõ; nhưng nếu báo cáo dùng để duyệt giá thành, quy tắc này có thể làm giá thành bị đánh giá thấp.

### Báo cáo chất lượng dữ liệu riêng

Nếu schema có cột giá hoặc hệ số cho phép `NULL`, nên có kiểm tra trước khi roll-up:

```sql
-- Mẫu truy vấn kiểm tra trên một schema cho phép NULL:
SELECT parent_part_id, child_part_id
FROM bom_edges
WHERE qty_per_parent IS NULL
   OR qty_per_parent <= 0;

SELECT part_id, part_name
FROM parts
WHERE direct_unit_cost IS NULL;
```

Hai bảng `bom_edges`/`parts` ở đây chỉ là tên khái niệm; bảng thực hành `sql226_...` đã có các ràng buộc không cho phép loại lỗi này. Trên dữ liệu thật, cần quyết định **chặn tính toán**, **hiển thị trạng thái thiếu dữ liệu**, hay **dùng giá trị thay thế có quy tắc**, thay vì lặng lẽ bỏ qua `NULL`.

## 21. Tính lũy kế trong cấu trúc tổ chức và quyền sở hữu

Kỹ thuật mang accumulator qua recursion không chỉ dùng cho BOM.

### Ví dụ 1 — Số nhân viên thuộc toàn bộ cấp dưới

Một bảng nhân viên có `employee_id` và `manager_id`:

```sql
-- PostgreSQL: khung truy vấn đếm cấp dưới.
WITH RECURSIVE team_tree AS (
    SELECT
        employee_id,
        manager_id,
        0 AS depth,
        ARRAY[employee_id] AS visited_ids
    FROM employees
    WHERE employee_id = 10

    UNION ALL

    SELECT
        e.employee_id,
        e.manager_id,
        t.depth + 1,
        t.visited_ids || e.employee_id
    FROM team_tree AS t
    JOIN employees AS e
      ON e.manager_id = t.employee_id
    WHERE t.depth < 30
      AND NOT (e.employee_id = ANY(t.visited_ids))
)
SELECT COUNT(*) - 1 AS subordinate_count
FROM team_tree;
```

Ví dụ này **đếm dòng nhân viên bên dưới một quản lý**, không cần nhân số lượng. Nó giả định cấu trúc quản lý là cây đúng nghĩa (mỗi nhân viên tối đa một cấp trên), không có nhiều đường đi dẫn đến cùng người và truy vấn không bị cắt chiều sâu.

Nếu một người có nhiều đường quan hệ hoặc nhiều vai trò, `COUNT(*)` có thể đếm nhiều lần; khi cần người duy nhất phải xác định đơn vị và `COUNT(DISTINCT employee_id)` phù hợp.

### Ví dụ 2 — Tích tỷ lệ sở hữu qua nhiều cấp

Trong đồ thị sở hữu, Công ty A sở hữu 60% B, B sở hữu 50% C. Tỷ lệ gián tiếp theo đường đi đó là:

\[
0.60 \times 0.50 = 0.30 = 30\%.
\]

Nếu có **nhiều đường sở hữu**, người phân tích có thể cần cộng các đóng góp đường đi sau khi đã kiểm tra mô hình và loại quan hệ không hợp lệ. Tuy nhiên, các cấu trúc sở hữu chéo, cổ phần có quyền biểu quyết khác nhau và chu trình có thể yêu cầu **mô hình toán học phức tạp hơn chỉ SUM mọi đường đi**. Đừng bê nguyên công thức BOM sang sở hữu công ty mà không xem điều kiện nghiệp vụ.

### Ví dụ 3 — Tài nguyên hoặc thư mục lồng nhau

Một thư mục có nhiều thư mục con; nếu cần tổng dung lượng file thuộc **mọi cấp dưới**, ta có thể đệ quy tìm tất cả file rồi `SUM(file_size)`. Ở mô hình thư mục cây, mỗi file thường có một đường đi từ root; ở hệ liên kết/hard link hoặc quan hệ nhiều cha, phải xác định có đếm một file nhiều lần hay một lần theo ID.

**Ý nghĩa chung:** đệ quy tìm **những đóng góp ở các cấp liên quan**, còn công thức accumulator và phép tổng hợp cuối phụ thuộc câu hỏi nghiệp vụ.

## 22. Các khác biệt giữa PostgreSQL, MySQL/MariaDB, SQL Server, SQLite và Oracle

Ý tưởng anchor + recursive member + `UNION ALL` xuất hiện trong nhiều DBMS, nhưng cú pháp, giới hạn đệ quy, cách ghép kiểu và cách dò chu trình khác nhau.

| DBMS | Dạng đệ quy thông dụng | Điểm cần chú ý khi tính lũy kế |
| --- | --- | --- |
| **PostgreSQL** | `WITH RECURSIVE ...` | Hỗ trợ array để giữ đường đi, `numeric`, `CYCLE` trong phiên bản hỗ trợ; có thể dùng `EXPLAIN` |
| **MySQL 8.0+** | `WITH RECURSIVE ...` | Kiểu cột CTE chịu ảnh hưởng anchor; giới hạn đệ quy theo cấu hình `cte_max_recursion_depth`; không có kiểu array PostgreSQL |
| **MariaDB** | `WITH RECURSIVE ...` ở phiên bản hỗ trợ | Có `max_recursive_iterations`; thường cần `CAST` anchor đủ rộng, nhất là cột đường đi |
| **SQL Server** | `WITH cte AS (...)` không cần từ `RECURSIVE` | Recursive CTE có yêu cầu kiểu cột tương ứng; `OPTION (MAXRECURSION n)` điều khiển giới hạn; `varchar(max)` cho đường đi |
| **SQLite** | `WITH RECURSIVE ...` | Có thể dùng chuỗi đường đi + `instr`/`printf`; recursive member có các hạn chế với hàm tổng hợp/window |
| **Oracle Database** | Recursive subquery factoring trong `WITH`; có `CONNECT BY` | Danh sách alias cột, quy tắc cycle/`CYCLE` và kiểu dữ liệu theo cú pháp Oracle; không giả định dùng chữ `RECURSIVE` như PostgreSQL |

### 22.1. MySQL 8.0+/MariaDB: dùng chuỗi đường đi thay array

Ví dụ khung truy vấn trên MySQL/MariaDB với bảng `sql226_parts`/`sql226_bom` có cùng cột:

```sql
-- MySQL 8.0+ / MariaDB phiên bản hỗ trợ recursive CTE.
WITH RECURSIVE expansion AS (
    SELECT
        part_id,
        CAST(1 AS DECIMAL(30,0)) AS required_qty,
        0 AS depth,
        CAST(part_id AS CHAR(2000)) AS visited_csv
    FROM sql226_parts
    WHERE part_id = 100

    UNION ALL

    SELECT
        b.child_part_id,
        CAST(e.required_qty * b.qty_per_parent AS DECIMAL(30,0)),
        e.depth + 1,
        CONCAT(e.visited_csv, ',', b.child_part_id)
    FROM expansion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.part_id
    WHERE e.depth < 20
      AND FIND_IN_SET(b.child_part_id, e.visited_csv) = 0
)
SELECT
    part_id,
    SUM(required_qty) AS total_required_qty
FROM expansion
GROUP BY part_id
ORDER BY part_id;
```

`FIND_IN_SET` tìm mã con trong danh sách ID phân tách bằng dấu phẩy. Vì `part_id` là số nguyên, cách mã hóa này không có dấu phẩy bên trong một ID. Với ID chuỗi hoặc dữ liệu có ký tự phân cách, cần chọn cách lưu đường đi không va chạm.

**Giới hạn:** `CHAR(2000)` chỉ minh họa một độ dài cho đường đi và có thể bị vượt nếu cấu trúc sâu/rộng; cách xử lý dữ liệu chuỗi quá dài phụ thuộc phiên bản/cấu hình. Cột `DECIMAL(30,0)` cũng có giới hạn 30 chữ số nguyên; nếu sản phẩm hệ số lớn, phải mở rộng chính sách kiểu số. Query còn có thể bị giới hạn bởi cấu hình đệ quy dù điều kiện logic cho phép đi sâu hơn.

Trong MySQL/MariaDB, không đặt `SUM(...)` trực tiếp làm phép tổng hợp trong recursive member; hãy đệ quy để tạo các đóng góp, rồi `GROUP BY`/`SUM` **ở SELECT ngoài**.

### 22.2. SQL Server: WITH và MAXRECURSION

Trên SQL Server, cú pháp dùng `WITH` thay vì `WITH RECURSIVE`:

```sql
-- SQL Server: giả sử bảng dbo.sql226_parts và dbo.sql226_bom tồn tại.
WITH expansion AS (
    SELECT
        p.part_id,
        CAST(1 AS decimal(28,0)) AS required_qty,
        CAST(0 AS int) AS depth,
        CAST('/' + CONVERT(varchar(20), p.part_id) + '/'
            AS varchar(max)) AS visited_path
    FROM dbo.sql226_parts AS p
    WHERE p.part_id = 100

    UNION ALL

    SELECT
        b.child_part_id,
        CAST(e.required_qty * b.qty_per_parent
            AS decimal(28,0)),
        e.depth + 1,
        CAST(e.visited_path
             + CONVERT(varchar(20), b.child_part_id) + '/'
             AS varchar(max))
    FROM expansion AS e
    JOIN dbo.sql226_bom AS b
      ON b.parent_part_id = e.part_id
    WHERE e.depth < 20
      AND CHARINDEX(
          '/' + CONVERT(varchar(20), b.child_part_id) + '/',
          e.visited_path
      ) = 0
)
SELECT
    part_id,
    SUM(required_qty) AS total_required_qty
FROM expansion
GROUP BY part_id
ORDER BY part_id
OPTION (MAXRECURSION 100);
```

`MAXRECURSION 100` cho phép giới hạn số bước đệ quy tối đa theo SQL Server; nếu vượt giới hạn, engine có thể báo lỗi. Giá trị `0` có ý nghĩa tắt giới hạn mặc định của option này trong SQL Server, nhưng **không nên dùng để bỏ bảo vệ** trên BOM có thể chứa chu trình.

Chuỗi `'/100/200/500/'` sử dụng dấu phân cách hai bên ID, giúp tránh nhầm `10` với `100` khi tìm nút đã có trong đường đi. Nó là kỹ thuật minh họa cho ID số nguyên; trong sản xuất, cần xem độ dài chuỗi, collation và phương án phát hiện chu trình phù hợp.

### 22.3. SQLite: WITH RECURSIVE và instr

SQLite không có kiểu array như PostgreSQL, nhưng có thể dùng chuỗi đường đi:

```sql
-- SQLite:
WITH RECURSIVE expansion(part_id, required_qty, depth, path_text) AS (
    SELECT
        part_id,
        CAST(1 AS INTEGER),
        0,
        printf('/%d/', part_id)
    FROM sql226_parts
    WHERE part_id = 100

    UNION ALL

    SELECT
        b.child_part_id,
        e.required_qty * b.qty_per_parent,
        e.depth + 1,
        e.path_text || printf('%d/', b.child_part_id)
    FROM expansion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.part_id
    WHERE e.depth < 20
      AND instr(e.path_text, printf('/%d/', b.child_part_id)) = 0
)
SELECT part_id, SUM(required_qty) AS total_required_qty
FROM expansion
GROUP BY part_id
ORDER BY part_id;
```

Cách viết giả định `part_id` là số nguyên dương/âm hợp lệ và không có ký tự phân cách. Với cấu trúc lớn, kiểu integer 64-bit của SQLite có thể không đủ cho tích số lượng ở nhiều cấp; không nên trông chờ việc engine tự đổi biểu diễn số sẽ luôn giữ chính xác.

### 22.4. Oracle: recursive subquery factoring

Oracle có thể biểu diễn cấu trúc đệ quy bằng `WITH` với danh sách alias cột:

```sql
-- Oracle Database (dạng khung):
WITH expansion (
    part_id,
    required_qty,
    depth
) AS (
    SELECT
        p.part_id,
        CAST(1 AS NUMBER(28,0)),
        0
    FROM sql226_parts p
    WHERE p.part_id = 100

    UNION ALL

    SELECT
        b.child_part_id,
        CAST(e.required_qty * b.qty_per_parent AS NUMBER(28,0)),
        e.depth + 1
    FROM expansion e
    JOIN sql226_bom b
      ON b.parent_part_id = e.part_id
)
SELECT
    part_id,
    SUM(required_qty) AS total_required_qty
FROM expansion
GROUP BY part_id;
```

Đây là mẫu ngắn để nhấn mạnh **tên cột, phép nhân và cú pháp `WITH` của Oracle**; nó **chưa có kiểm soát chu trình** nên chỉ nên chạy trên dữ liệu đã được xác nhận là DAG. Oracle có cơ chế `CYCLE` trong recursive subquery factoring và các khả năng `CONNECT BY` để xử lý phân cấp; khi triển khai trên dữ liệu có nguy cơ chu trình, cần dùng cú pháp phát hiện vòng lặp và giới hạn phù hợp.

**Không chuyển nguyên cú pháp `ARRAY[...]`/`ANY` hay `::numeric` của PostgreSQL sang Oracle**, vì đây không phải cú pháp di động.

### 22.5. PostgreSQL và cú pháp CYCLE

PostgreSQL hiện đại có thể hỗ trợ mệnh đề `CYCLE` để đánh dấu đường đi quay lại node. Ngoài ra, PostgreSQL hỗ trợ cột array như các ví dụ đang dùng.

Khi chọn cú pháp `CYCLE`, cần xác định **những cột cấu thành định danh node** (có thể là cặp `tenant_id, part_id`), thay vì chỉ một cột không duy nhất. Cú pháp `CYCLE` giúp mô tả dò vòng lặp nhưng không thay thế **chính sách dữ liệu**: BOM có chu trình phải bị cảnh báo/loại khỏi việc duyệt giá thành hoặc được xử lý theo ngữ nghĩa riêng.

## 23. Hiệu năng và chỉ mục của phép nổ BOM

Mỗi bước trong recursive member có thao tác:

```sql
JOIN sql226_bom AS b
  ON b.parent_part_id = e.part_id
```

Vì vậy, khi đi từ cha xuống con, index trên `parent_part_id` có thể có ích. Trong bảng thực hành, khóa chính là `(parent_part_id, child_part_id)`, thường tạo index B-tree bắt đầu bằng `parent_part_id` — phù hợp để tìm các con của một cha.

Khi đi **ngược từ con lên cha** như mục 13, truy vấn cần:

```sql
JOIN sql226_bom AS b
  ON b.child_part_id = e.assembly_id
```

Index chỉ có `parent_part_id` làm cột dẫn đầu chưa chắc giúp tốt cho truy vấn theo `child_part_id`. Trên PostgreSQL có thể tạo thêm index:

```sql
CREATE INDEX ix_sql226_bom_child_parent
ON sql226_bom (child_part_id, parent_part_id);
```

Điều này hữu ích khi thường xuyên tra **linh kiện đang được dùng ở những cụm nào** hoặc tính roll-up ngược. Không thêm index tùy tiện nếu dữ liệu nhỏ hoặc chỉ chạy một lần; index có chi phí lưu trữ và cập nhật.

### Độ lớn kết quả phụ thuộc số đường đi, không chỉ số node

BOM có thể chứa vài nghìn mã linh kiện nhưng rất nhiều đường đi kết hợp nếu một cụm được tái sử dụng ở nhiều cấp. `WITH RECURSIVE` mở rộng từng đường đi có thể tạo **nhiều dòng hơn số node hoặc số cạnh**.

Ví dụ ở mỗi cấp có hai nhánh, số đường đi có thể tăng nhanh theo độ sâu. Dù dùng index tốt, truy vấn vẫn phải xử lý số lượng đóng góp cần tính theo ngữ nghĩa.

Các cách giảm chi phí khi phù hợp:

- Chỉ bắt đầu từ **những gốc thực sự cần tính**.
- Lọc **phiên bản BOM** và cấu hình sản phẩm trước khi đệ quy.
- Có chính sách giới hạn độ sâu/cảnh báo chu trình, không mở rộng vô hạn.
- Tạo index theo hướng duyệt: `parent_part_id` cho top-down, `child_part_id` cho bottom-up.
- Với nhiều đơn sản xuất cùng thành phẩm, cân nhắc **tổng hợp số lượng ở gốc trước khi nổ BOM**.
- Cache/materialize kết quả roll-up theo **revision/cấu hình** nếu việc tính lại nhiều lần tốn kém và có quy trình vô hiệu hóa cache đúng.
- Quan sát `EXPLAIN` và số dòng thực tế trên dữ liệu đại diện; không kết luận từ bảng 14 cạnh.

### PostgreSQL EXPLAIN

```sql
EXPLAIN
WITH RECURSIVE explosion AS (
    SELECT part_id, 1::numeric AS qty, 0 AS depth
    FROM sql226_parts
    WHERE part_id = 100

    UNION ALL

    SELECT b.child_part_id,
           e.qty * b.qty_per_parent,
           e.depth + 1
    FROM explosion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.part_id
    WHERE e.depth < 20
)
SELECT part_id, SUM(qty)
FROM explosion
GROUP BY part_id;
```

Ví dụ `EXPLAIN` này **chỉ minh họa kế hoạch của recursive CTE trên dữ liệu đã giả định không có chu trình**, không dùng thay cho truy vấn kiểm tra chu trình ở mục 15. PostgreSQL có thể hiển thị `Recursive Union`, `WorkTable Scan`, phép JOIN và Aggregate; kế hoạch cụ thể thay đổi theo thống kê và phiên bản.

`EXPLAIN` thường không thực thi truy vấn; `EXPLAIN ANALYZE` **có thực thi**, vì vậy chỉ chạy trên môi trường/dữ liệu đã được phép và có giới hạn phù hợp.

## 24. Tính đúng dưới cập nhật đồng thời và snapshot

Trong hệ thống sản xuất, BOM và giá linh kiện có thể được sửa trong lúc một báo cáo định mức đang chạy.

Nếu phép tính chi phí gồm **nhiều câu SQL tách rời**, ví dụ truy vấn lấy BOM ở thời điểm A, rồi lấy giá ở thời điểm B, dữ liệu có thể phản ánh **hai phiên bản khác nhau**. Một linh kiện có thể đổi định mức và giá trong khoảng giữa các lần đọc.

Dùng một recursive CTE cùng phép JOIN với giá **trong một câu truy vấn** thường giúp xác định một tập dữ liệu đang được câu lệnh nhìn thấy theo cơ chế giao dịch của DBMS. Nhưng độ nhất quán chính xác phụ thuộc engine và isolation level.

### Báo cáo phải gắn với phiên bản BOM và giá

Nếu một sản phẩm được chốt giá thành theo `revision R12`, nên lưu hoặc xác định:

- `product_id`, `revision` và cấu hình sản phẩm.
- Thời điểm hiệu lực dùng để chọn các cạnh.
- Bộ đơn giá/chi phí tại mốc được phê duyệt.
- Đơn vị tiền và đơn vị đo.
- Chính sách hao hụt/làm tròn.
- Trạng thái kiểm tra chu trình và dữ liệu thiếu.
- Thời điểm tính và mã batch báo cáo.

Không xem việc query hiện tại trả `573` là bằng chứng giá thành của **mọi đơn hàng trong quá khứ** đều bằng 573, nếu định mức hoặc giá nguyên vật liệu thay đổi theo thời gian.

### Một câu SQL không thay thế quản lý phiên bản

Khi BOM được cấu hình động hoặc tồn tại ngoài một database, có thể phải đưa cả cấu trúc và giá về một **snapshot dữ liệu đã chốt**. `WITH RECURSIVE` chỉ tính theo dữ liệu truy vấn được cung cấp; nó không tự tạo phiên bản lịch sử hay đồng bộ nhiều hệ thống.

## 25. Các lỗi thường gặp khi tính lũy kế đệ quy

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| 1 xe có 2 bánh nhưng chỉ tính 20 căm | Lấy số lượng con của bánh, quên nhân số bánh từ cấp cha | Dùng `required_qty * qty_per_parent` ở mỗi bước |
| Kết quả ốc bằng 3 thay vì 14 | Dùng `COUNT(*)` trên ba đường đi | Dùng `SUM(required_qty)` theo `part_id` |
| Kết quả ốc bằng 8 hoặc 10 thay vì 14 | Loại các đường đi cùng `part_id` quá sớm | Giữ `UNION ALL` và cộng sau khi đi hết các nhánh |
| Một linh kiện xuất hiện 3 dòng nên nghĩ có lỗi | BOM là DAG với nhiều đường đi | Giữ thông tin path, xác minh từng đóng góp rồi nhóm |
| Giá thành bị tính hai lần cho bánh xe | Giá cụm đã bao gồm thành phần con nhưng vẫn cộng chi phí con | Phân biệt direct cost và rolled-up cost |
| Giá thành thiếu khung | Chỉ cộng node lá dù khung có chi phí trực tiếp và có con | Cộng chi phí trực tiếp của mọi node theo mô hình |
| SQL đệ quy chạy mãi hoặc hết recursion | Có chu trình trong BOM | Dò chu trình, chặn khi nhập dữ liệu, có giới hạn an toàn |
| Query kết thúc nhưng tổng thiếu vật tư cấp sâu | `depth < n` cắt ngang BOM hợp lệ | Xác định chiều sâu tối đa và phát hiện vượt ngưỡng |
| Mã linh kiện dùng lại nhưng bị “visited” chặn | Dùng visited toàn cục, không theo path | Dùng path riêng cho từng dòng đệ quy |
| Đếm linh kiện của nhiều sản phẩm bị cộng lẫn | Không mang theo `root_part_id` khi cần nhóm từng gốc | Thêm root ID và nhóm theo root + component |
| Tổng sản xuất thấp hơn nhu cầu | Quên nhân số đơn vị thành phẩm được đặt | Anchor bằng `finished_qty` hoặc nhân sau kết quả định mức |
| Truy vấn lũy kế sai khi đổi phiên bản | Các cạnh nhiều revision cùng được đọc | Lọc BOM hiệu lực trước/mỗi bước |
| Số lượng thành `NULL` hoặc tổng thiếu | Hệ số/chi phí bị thiếu và `SUM` bỏ qua NULL | Kiểm tra chất lượng dữ liệu, không COALESCE tùy tiện |
| Tích số lượng bị tràn | Kiểu số quá nhỏ hoặc quá nhiều cấp | Chọn NUMERIC/DECIMAL đủ rộng và có giới hạn hợp lý |
| Giá sai do làm tròn sớm | ROUND từng cấp trước khi nhân/cộng | Chọn thời điểm làm tròn theo quy tắc nghiệp vụ |
| Tự nhận cây có thứ tự từ CTE | Recursive query không cam kết thứ tự hiển thị | Thêm `ORDER BY` ở SELECT cuối với khóa/path phù hợp |
| Truy vấn bottom-up chạy chậm | Không có index theo `child_part_id` | Đánh giá index đảo chiều và kế hoạch thực thi |
| Tính giá cho tất cả cụm quá nặng | Mở rộng mọi đường đi từ mọi gốc | Chọn phạm vi, tính batch và cache theo revision nếu cần |

## 26. Bài tập thực hành

Các bài sau dùng `sql226_parts` và `sql226_bom` đã tạo ở mục 5. Chỉ tạo lại nếu bạn đang ở một database thực hành mới.

### Bài 1 — Tích số lượng theo một đường đi

BOM có `A → B` với số lượng 3, `B → C` với số lượng 4, `C → D` với số lượng 5. Một A cần bao nhiêu D? Nếu sản xuất 7 A thì cần bao nhiêu D?

### Bài 2 — Tổng hợp khi có nhiều đường đi

Một thành phẩm cần:

- Trực tiếp 5 ốc.
- Hai cụm X, mỗi X cần 3 ốc.
- Một cụm Y, Y cần 4 ốc.

Hãy tính tổng số ốc cho một thành phẩm và giải thích vì sao `COUNT(DISTINCT part_id)` không giúp tính số lượng.

### Bài 3 — Đếm và SUM khác nhau

Trên xe đạp `100`, truy vấn mở BOM có bao nhiêu dòng mang `part_id = 500`? `COUNT(*)`, `SUM(required_qty)` và `COUNT(DISTINCT part_id)` trong nhóm ốc trả những số nào?

### Bài 4 — Viết recursive CTE cho một gốc

Viết PostgreSQL `WITH RECURSIVE` để lấy tất cả các đường đi từ `part_id = 100`, mang theo `required_qty` và `depth`. Có thể dùng array `visited_ids` để chặn vòng lặp trên từng đường đi.

### Bài 5 — Tổng hợp nhu cầu căm và ốc

Dùng CTE ở bài 4, trả `part_id` và tổng số lượng cần cho một xe đạp. Nêu kết quả cho căm `230` và ốc `500`.

### Bài 6 — Chi phí của xe đạp

Đối chiếu chi phí:

- Lốp 40/đơn vị, cần 2.
- Vành 60/đơn vị, cần 2.
- Căm 3/đơn vị, cần 40.
- Khung 150/đơn vị, cần 1.
- Bàn đạp 20/đơn vị, cần 2.
- Ốc 2/đơn vị, cần 14.
- Tay lái 35/đơn vị, cần 1.

Hãy tính tổng và giải thích vì sao `direct_unit_cost` của bánh xe phải là 0 trong dữ liệu đang dùng nếu không có tiền công lắp bánh riêng.

### Bài 7 — Nhiều thành phẩm

Dùng root `100` và `900`. Viết recursive CTE giữ `root_part_id`. Trả nhu cầu `part_id = 500` cho từng gốc và tổng chi phí của từng xe. Nêu số liệu dự kiến.

### Bài 8 — Đơn sản xuất

Có đơn sản xuất 10 xe thường và 5 xe mini. Tính nhu cầu căm, ốc và tổng chi phí từ dữ liệu mẫu. Nêu hai cách đưa số lượng đơn sản xuất vào công thức: nhân sau khi tính định mức đơn vị hoặc khởi tạo `required_qty` bằng số lượng thành phẩm ở anchor.

### Bài 9 — Tính giá cho mọi cụm

Viết truy vấn top-down khởi đầu từ **mọi node** và `GROUP BY assembly_id` để tính `rolled_up_unit_cost`. Giá của một bánh xe và một khung bằng bao nhiêu?

### Bài 10 — Đi ngược từ chi phí lên cụm

Ở hướng bottom-up, khi bắt đầu từ căm `230`:

1. Chi phí một căm đóng góp vào chính nó là bao nhiêu?
2. Chi phí căm trong một bánh xe là bao nhiêu?
3. Chi phí căm trong một xe đạp thường là bao nhiêu?

Viết phép nhân trên từng cạnh đi ngược.

### Bài 11 — Phân biệt cycle và linh kiện dùng chung

Tại sao `100 → 200 → 500` và `100 → 300 → 500` **không tạo chu trình**, dù node 500 xuất hiện hai lần trong kết quả? Tại sao `100 → 200 → 230 → 100` lại là chu trình? Trong truy vấn bảo vệ chu trình, tập visited nên thuộc về **từng path** hay toàn bộ cây?

### Bài 12 — Dữ liệu giá thành không đầy đủ

Nếu `direct_unit_cost` của khung bị thay bằng `NULL` trong một schema cho phép NULL, dùng `SUM(required_qty * direct_unit_cost)` có thể gây vấn đề gì? `COALESCE(NULL,0)` có luôn đúng không? Bạn sẽ thiết kế cảnh báo dữ liệu như thế nào?

### Bài 13 — Version và giới hạn độ sâu

Một BOM có revision R1 và R2, cùng khai báo quan hệ `200 → 230` nhưng lần lượt cần 20 và 22 căm. Nếu recursive CTE không lọc revision, một xe có hai bánh có thể bị tính như thế nào? `depth < 20` có bảo đảm mọi cấu trúc hợp lệ được tính đủ không?

### Bài 14 — Chọn phép tính đúng

Với mỗi yêu cầu dưới đây, chọn kỹ thuật chính:

1. Tổng số căm cần cho 10 xe.
2. Tổng giá hoàn chỉnh của từng cụm bất kỳ.
3. Tổng doanh thu tích lũy theo ngày trong một tháng.
4. Danh sách mọi mã linh kiện lá thuộc xe.
5. Những thành phẩm nào sử dụng linh kiện ốc.
6. Phát hiện A → B → C → A.

## 27. Gợi ý lời giải

**Bài 1:** Một A cần `3 × 4 × 5 = 60` D. Bảy A cần `7 × 60 = 420` D.

**Bài 2:** Tổng ốc là `5 + (2 × 3) + 4 = 15`. `COUNT(DISTINCT part_id)` chỉ biết một mã ốc, không giữ số lượng đóng góp từ ba nhánh.

**Bài 3:** Có **3 dòng đường đi** tới `500`; `COUNT(*) = 3`, `SUM(required_qty) = 14`, `COUNT(DISTINCT part_id) = 1`.

**Bài 4:** Một đáp án PostgreSQL:

```sql
WITH RECURSIVE expansion AS (
    SELECT
        part_id,
        1::numeric AS required_qty,
        0 AS depth,
        ARRAY[part_id] AS visited_ids
    FROM sql226_parts
    WHERE part_id = 100

    UNION ALL

    SELECT
        b.child_part_id,
        e.required_qty * b.qty_per_parent,
        e.depth + 1,
        e.visited_ids || b.child_part_id
    FROM expansion AS e
    JOIN sql226_bom AS b
      ON b.parent_part_id = e.part_id
    WHERE e.depth < 20
      AND NOT (b.child_part_id = ANY(e.visited_ids))
)
SELECT
    part_id,
    required_qty,
    depth,
    array_to_string(visited_ids, ' > ') AS path
FROM expansion
ORDER BY visited_ids;
```

**Bài 5:** Có thể thay `SELECT` cuối của CTE ở bài 4 bằng:

```sql
SELECT part_id, SUM(required_qty) AS qty
FROM expansion
WHERE depth > 0
GROUP BY part_id
ORDER BY part_id;
```

Kết quả `230 = 40`, `500 = 14`. Phần SELECT này cần đứng ngay sau định nghĩa CTE, không phải chạy tách rời khi CTE đã hết phạm vi.

**Bài 6:** `2×40 + 2×60 + 40×3 + 1×150 + 2×20 + 14×2 + 1×35 = 573`. Trong mô hình chi phí **trực tiếp chưa gồm con**, bánh xe có chi phí trực tiếp 0 vì chi phí lốp/vành/căm/ốc đã được cộng ở các node con. Nếu có tiền công lắp bánh riêng, có thể đưa **chỉ tiền công riêng đó** vào direct cost bánh xe.

**Bài 7:** Xe thường `100` cần **14 ốc**, giá **573**; xe mini `900` cần **12 ốc**, giá **534**. Truy vấn phải giữ `root_part_id` trong cả anchor và recursive member, nhóm theo root.

**Bài 8:** Căm `10×40 + 5×40 = 600`; ốc `10×14 + 5×12 = 200`; chi phí `10×573 + 5×534 = 8400`. Nhân ở anchor hoặc nhân định mức mỗi sản phẩm sau khi tính đều có thể đúng nếu dữ liệu và đơn vị nhất quán.

**Bài 9:** Giá một bánh xe `40 + 60 + 20×3 + 4×2 = 168`. Giá một khung `150 + 2×2 = 154`. Để tính mọi node, anchor từ `sql226_parts` không có `WHERE` giới hạn root, rồi giữ `assembly_id` trong đệ quy và nhóm theo mã cụm.

**Bài 10:** Chi phí trực tiếp một căm = **3**. Với bánh xe: `20×3 = 60`. Với xe thường: `2×20×3 = 120`. Hướng bottom-up đi từ `230` lên `200`, rồi lên `100`, nhân hệ số của cạnh cha→con khi chuyển sang mỗi cha.

**Bài 11:** Hai đường đi tới `500` đều kết thúc ở một linh kiện chung nhưng **không quay lại nút đã qua trên cùng đường đi**. Đường `100→200→230→100` trở về node gốc nên có chu trình. `visited_ids` phải được giữ **trên từng path**, không phải một tập dùng chung chặn mọi lần thấy một linh kiện.

**Bài 12:** `NULL` làm đóng góp chi phí khung không được tính đúng; `SUM` có thể bỏ qua các giá trị NULL và báo tổng thấp hơn thực tế. `COALESCE(...,0)` chỉ đúng khi chính sách được phê duyệt cho phép coi giá chưa biết là 0; nếu không, cần phát hiện giá thiếu và chặn/đánh dấu kết quả chưa đầy đủ.

**Bài 13:** Nếu cả quan hệ 20 và 22 căm cùng được đi qua, hai bánh có thể bị cộng `2×20 + 2×22 = 84` căm thay vì 40 hoặc 44 theo từng revision. `depth < 20` chỉ giới hạn việc duyệt; cấu trúc hợp lệ sâu hơn 20 vẫn có thể bị cắt và tính thiếu.

**Bài 14:** (1) Recursive CTE nhân hệ số + `SUM` theo linh kiện, rồi nhân số xe. (2) Roll-up cho mọi assembly hoặc tính ngược từ nguồn chi phí. (3) Window `SUM(...) OVER (ORDER BY ...)`. (4) Recursive CTE + `NOT EXISTS` tìm cạnh con. (5) Truy vấn ngược từ linh kiện lên tổ tiên bằng quan hệ `child_part_id`. (6) Dò chu trình dựa trên path hoặc `CYCLE` theo DBMS.

## 28. Dọn dữ liệu thực hành

Sau khi kết thúc bài và chắc chắn hai bảng dưới đây **do chính bạn tạo** trong database thực hành:

```sql
DROP TABLE sql226_bom;
DROP TABLE sql226_parts;
```

Xóa bảng quan hệ `sql226_bom` trước `sql226_parts` vì nó có khóa ngoại tham chiếu `sql226_parts`. Không chạy `DROP TABLE` trên cơ sở dữ liệu nghiệp vụ hoặc các bảng có dữ liệu dùng chung.

## 29. Kết luận

**Tính lũy kế trong cấu trúc thành phần bằng SQL là bài toán “nhân theo đường đi, cộng qua các đường đi”.** Ở mỗi bước đệ quy, mang theo `required_qty` và cập nhật bằng `required_qty × qty_per_parent`; sau khi đi đủ các nhánh, dùng `GROUP BY` và `SUM(required_qty)` để tìm tổng nhu cầu từng linh kiện. Nếu cần chi phí, nhân số lượng với **chi phí trực tiếp chưa gồm con** rồi cộng lại; nếu cần chi phí của từng cụm, giữ thêm mã cụm gốc hoặc truyền đóng góp từ các linh kiện lên các tổ tiên.

Một truy vấn đệ quy đúng cần hơn cú pháp `WITH RECURSIVE`: phải xác định **đơn vị số lượng, ý nghĩa chi phí, nhiều đường đi đến cùng linh kiện, chu trình, giới hạn chiều sâu, kiểu số, phiên bản BOM và thời điểm dữ liệu**. Tránh dùng `DISTINCT` để xóa đóng góp hợp lệ và tránh coi tổng chi phí cụm đã roll-up là một chi phí trực tiếp có thể cộng lại với toàn bộ linh kiện con. Khi các giả định này được làm rõ, SQL có thể biểu diễn và kiểm tra các phép tính lũy kế nhiều cấp một cách minh bạch, tái lập được và phù hợp nhu cầu sản xuất, quản trị cấu trúc hoặc phân tích dữ liệu phân cấp.
