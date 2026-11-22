# Phát hiện chu trình, nhiều cha và trường hợp phải dùng đồ thị

Trong mô hình dữ liệu phân cấp, ta thường bắt đầu bằng câu “mỗi nút có một nút cha”. Câu này hợp lý cho **cây thư mục**, **cây tổ chức có một quản lý trực tiếp** hoặc **danh mục có một nhánh cha duy nhất**. Nhưng yêu cầu thực tế có thể thay đổi: một chủ đề thuộc hai nhóm, một kỹ năng có nhiều kỹ năng tiên quyết, hoặc một dịch vụ phụ thuộc đồng thời vào nhiều dịch vụ khác.

Khi đó, câu hỏi không còn chỉ là “lưu khóa cha thế nào?” mà là **cấu trúc có cho phép nhiều cha không, chu trình có hợp lệ không và truy vấn cần đi theo những quan hệ nào?** Ba cấu trúc phải phân biệt rõ:

- **Cây (tree):** mỗi nút có nhiều nhất một cha; không có chu trình; trong một cây có một gốc.
- **Đồ thị có hướng không chu trình (directed acyclic graph, DAG):** một nút có thể có nhiều cha hoặc nhiều đường đi từ gốc đến nó, nhưng **không có chu trình có hướng**.
- **Đồ thị có hướng tổng quát (directed graph):** cho phép nhiều quan hệ theo hướng; **có thể có chu trình** nếu nghiệp vụ cho phép.

Bài này thuộc chương **Kế thừa và phân cấp** của module **DATABASE_DATA_MODELING**. Mục tiêu là chuyển quy tắc nghiệp vụ thành mô hình thực thể, quan hệ và ràng buộc có thể kiểm chứng; chọn khóa, chỉ mục, lược đồ quan hệ, document hoặc đồ thị phù hợp và làm rõ cách hệ thống tiến hóa khi phát sinh nhiều cha hay quan hệ phức tạp.

> **Phân biệt thuật ngữ:** “cha” trong một **cây nút** là nút đứng trước qua một cạnh phân cấp. Nó không tự đồng nghĩa với “kiểu cha” (*supertype*) của quan hệ kế thừa **IS-A**. Một danh mục có hai danh mục cha chưa chắc là một subtype kế thừa hai kiểu dữ liệu; cần xác nhận đây là cấu trúc phân loại, phụ thuộc hay quan hệ thành phần.

## 1. Vì sao một khóa cha có lúc không đủ?

Xét cây danh mục ban đầu:

~~~text
Danh mục (1)
├── Điện tử (2)
│   └── Thiết bị di động (4)
│       └── Đồng hồ thông minh (5)
└── Phụ kiện (3)
~~~

Giả sử nghiệp vụ bổ sung: **“Đồng hồ thông minh cũng phải xuất hiện dưới Phụ kiện, nhưng vẫn nằm dưới Thiết bị di động.”** Cấu trúc lúc này là:

~~~mermaid
flowchart TD
    A["Danh mục (1)"] --> B["Điện tử (2)"]
    A --> C["Phụ kiện (3)"]
    B --> D["Thiết bị di động (4)"]
    D --> E["Đồng hồ thông minh (5)"]
    C --> E
    E --> F["Đồng hồ Android (6)"]
~~~

Nút 5 có **hai cha trực tiếp** là 3 và 4. Đây là một **DAG**, vì từ 1 đến 5 có hai đường đi:

- 1 → 3 → 5;
- 1 → 2 → 4 → 5.

Không có đường nào quay trở lại một nút đã gặp. Nếu cho thêm cạnh **6 → 2**, ta sẽ tạo chu trình **2 → 4 → 5 → 6 → 2**.

Một cột duy nhất **parent_id** trong bảng nút không thể lưu đồng thời hai cha của nút 5. Nhưng cũng **không nên vội kết luận phải chuyển sang DAG**: nếu yêu cầu chỉ là “một *sản phẩm* có thể nằm trong nhiều danh mục”, có thể giữ cây **Category** và dùng bảng nối **ProductCategory**. Nhiều danh mục gán cho một sản phẩm khác với nhiều cha trực tiếp của chính danh mục.

### Các câu hỏi để quyết định cấu trúc

1. **Đối tượng nào có nhiều cha?** Nút danh mục, sản phẩm, nhiệm vụ, người dùng hay vai trò tham gia một ngữ cảnh?
2. **Cạnh đại diện điều gì?** “Là danh mục con”, “phụ thuộc vào”, “được tham chiếu bởi”, “báo cáo cho”, “liên quan đến” hay “cùng nhóm”?
3. **Hướng cạnh có ý nghĩa không?** A phụ thuộc B không đồng nghĩa B phụ thuộc A.
4. **Có được quay lại nút ban đầu không?** Chu trình trong quan hệ “phải hoàn tất trước” là lỗi; trong quan hệ “theo dõi” có thể là bình thường.
5. **Một cặp nút có thể có nhiều cạnh khác loại hoặc cạnh có thời hạn không?** Nếu có, định danh cạnh cần lưu loại, ngữ cảnh hoặc thời gian.
6. **Truy vấn nào cần nhanh?** Con trực tiếp, toàn bộ hậu duệ, đường đi, tổ tiên, phụ thuộc bắc cầu, đường ngắn nhất, phát hiện vòng hay đường ảnh hưởng.

## 2. Phân biệt cây, rừng cây, DAG và đồ thị có chu trình

| Tính chất | Cây | Rừng cây | DAG | Đồ thị có hướng tổng quát |
| --- | --- | --- | --- | --- |
| Số cha trực tiếp của một nút | Tối đa 1 | Tối đa 1 | Có thể nhiều | Có thể nhiều |
| Số gốc | 1 nếu cây không rỗng | Nhiều cây, nhiều gốc | Có thể nhiều nguồn, tùy đồ thị | Có thể không có gốc |
| Chu trình có hướng | Không | Không | **Không** | Có thể có |
| Nhiều đường đi từ một nút đến nút khác | Không trong một cây | Không trong cùng cây | **Có thể** | Có thể |
| Mô hình điển hình | parent_id | parent_id + phạm vi cây | Bảng cạnh cha–con | Bảng cạnh có hướng, có thể có loại/thuộc tính |
| Ví dụ | Thư mục chuẩn | Nhiều cây thư mục độc lập | Kỹ năng tiên quyết, taxonomy nhiều cha | Quan hệ theo dõi, mạng lưới dịch vụ với các liên kết đa dạng |

**Rừng cây** không tự trở thành DAG chỉ vì có nhiều nút gốc. Mặt khác, DAG là khái niệm rộng hơn cây: nó có thể có nhiều cha và nhiều đường đi; nhưng một cây cũng là một DAG đặc biệt.

Với một phân cấp có nhiều cha, từ **“độ sâu”** không còn tự có một đáp án duy nhất. Nút 5 ở ví dụ có đường ngắn từ gốc dài **2 cạnh** và đường dài dài **3 cạnh**. Nếu cần một giá trị depth, phải xác định đó là:

- khoảng cách **ngắn nhất** từ gốc;
- khoảng cách **dài nhất**;
- độ sâu theo một **nhánh hiển thị được chọn**;
- hay độ sâu của **từng đường đi** riêng biệt.

Tương tự, một nút có thể xuất hiện nhiều lần trên giao diện cây khi được duyệt theo đường đi, nhưng vẫn chỉ là **một thực thể** với một node_id duy nhất trong dữ liệu.

## 3. Ràng buộc tối thiểu cho cây một cha

Một mô hình danh sách kề (*adjacency list*) thường bắt đầu từ bảng nút có khóa ngoại tự tham chiếu:

~~~sql
-- PostgreSQL: mô hình cây/rừng cây một cha
CREATE TABLE tree_nodes (
    node_id   BIGINT PRIMARY KEY,
    label     TEXT NOT NULL,
    parent_id BIGINT REFERENCES tree_nodes(node_id),
    CONSTRAINT node_cannot_parent_itself CHECK (
        parent_id IS NULL OR parent_id <> node_id
    )
);

CREATE INDEX idx_tree_nodes_parent
    ON tree_nodes(parent_id);
~~~

Mỗi hàng có một giá trị **parent_id** hoặc NULL, vì vậy nút không có nhiều hơn một cha trực tiếp. Khóa ngoại bảo đảm cha **tồn tại**; điều kiện CHECK ngăn chu trình một cạnh **nút tự làm cha mình**.

Nhưng những ràng buộc đó **chưa ngăn chu trình dài hơn**:

~~~text
A.parent_id = C
B.parent_id = A
C.parent_id = B
~~~

Cả ba khóa ngoại đều hợp lệ nếu ba nút đã tồn tại, và mỗi nút đều có cha khác chính nó, nhưng cấu trúc tạo ra vòng A → C → B → A khi đi theo parent_id. Một cây có chu trình là cấu trúc không hợp lệ ngay cả khi mọi khóa ngoại đều đúng.

Nếu nghiệp vụ yêu cầu **đúng một gốc**, còn phải có cơ chế bảo đảm số nút có parent_id IS NULL bằng một trong phạm vi cây. Nếu cho phép nhiều rễ vì đang lưu rừng cây, không áp đặt ràng buộc gốc duy nhất. Với dữ liệu có tenant/tree_id, kiểm tra và khóa ngoại phải giới hạn đúng phạm vi.

## 4. Dùng bảng cạnh khi một nút có nhiều cha

Đối với phân cấp thực sự là DAG, cách biểu diễn quan hệ trực tiếp phù hợp là **bảng cạnh (edge table)**. Mỗi hàng có hướng từ **parent_id → child_id**.

~~~sql
CREATE TABLE taxonomy_nodes (
    node_id BIGINT PRIMARY KEY,
    label   TEXT NOT NULL
);

CREATE TABLE taxonomy_edges (
    parent_id BIGINT NOT NULL REFERENCES taxonomy_nodes(node_id),
    child_id  BIGINT NOT NULL REFERENCES taxonomy_nodes(node_id),
    PRIMARY KEY (parent_id, child_id),
    CONSTRAINT no_self_edge CHECK (parent_id <> child_id)
);

-- Truy vấn cha của một nút thường bắt đầu ở child_id.
CREATE INDEX idx_taxonomy_edges_child_parent
    ON taxonomy_edges (child_id, parent_id);

INSERT INTO taxonomy_nodes (node_id, label) VALUES
    (1, 'Danh mục'),
    (2, 'Điện tử'),
    (3, 'Phụ kiện'),
    (4, 'Thiết bị di động'),
    (5, 'Đồng hồ thông minh'),
    (6, 'Đồng hồ Android');

INSERT INTO taxonomy_edges (parent_id, child_id) VALUES
    (1, 2),
    (1, 3),
    (2, 4),
    (3, 5),
    (4, 5),
    (5, 6);
~~~

Trong bảng này:

- **PRIMARY KEY(parent_id, child_id)** ngăn lặp cùng một cạnh có hướng.
- Hai khóa ngoại bảo đảm **hai đầu cạnh tồn tại**.
- **CHECK(parent_id <> child_id)** ngăn một vòng tự thân, nhưng **không chặn vòng nhiều cạnh**.
- Nút 5 có hai hàng cạnh: (3,5) và (4,5), nên không cần sao chép nút “Đồng hồ thông minh”.
- Chỉ mục đảo hỗ trợ truy vấn các cha của một nút; khóa chính đã hỗ trợ truy vấn các con theo parent_id.

Lấy **cha trực tiếp** của nút 5:

~~~sql
SELECT p.node_id, p.label
FROM taxonomy_edges AS e
JOIN taxonomy_nodes AS p ON p.node_id = e.parent_id
WHERE e.child_id = 5
ORDER BY p.node_id;
-- 3 Phụ kiện; 4 Thiết bị di động
~~~

Tìm các nút có nhiều hơn một cha:

~~~sql
SELECT child_id, COUNT(*) AS direct_parent_count
FROM taxonomy_edges
GROUP BY child_id
HAVING COUNT(*) > 1
ORDER BY direct_parent_count DESC, child_id;
-- node_id 5 có 2 cha trực tiếp
~~~

Truy vấn này giúp kiểm kê cấu trúc, nhưng **nhiều cha không mặc định là lỗi**. Nó là dữ liệu hợp lệ cho DAG; chỉ trở thành vi phạm nếu nghiệp vụ quy định mỗi nút phải có tối đa một cha.

### Cách giữ quy tắc “tối đa một cha”

Nếu dùng bảng cạnh nhưng vẫn muốn cây, một ràng buộc **UNIQUE(child_id)** sẽ giới hạn mỗi nút tối đa một cạnh cha trực tiếp:

~~~sql
-- Chỉ áp dụng nếu nghiệp vụ yêu cầu MỖI nút có tối đa một cha.
-- Không chạy trên ví dụ DAG ở trên: node 5 đang có hai cha.
ALTER TABLE taxonomy_edges
ADD CONSTRAINT one_parent_per_child UNIQUE (child_id);
~~~

Để mô hình **DAG nhiều cha**, **không thêm** UNIQUE(child_id). Quy tắc “một cha” và “không có chu trình” là hai ràng buộc **độc lập**: bỏ giới hạn một cha không có nghĩa cho phép chu trình.

## 5. Phát hiện chu trình trước khi thêm cạnh

Giả sử muốn thêm cạnh **6 → 2**. Việc này hợp lệ về khóa ngoại và không tự nối một nút với nó, nhưng tạo vòng **2 → 4 → 5 → 6 → 2**.

Với một cạnh đề xuất **P → C**, quy tắc rất rõ:

> Cạnh mới tạo chu trình **khi và chỉ khi** P = C, hoặc đã tồn tại đường đi có hướng **C → … → P** trong đồ thị hiện tại.

Vì vậy, để kiểm tra cạnh 6 → 2, hãy bắt đầu từ **C = 2**, đi **xuống các hậu duệ**, và xem có đến **P = 6** hay không.

### 5.1. Kiểm tra reachability bằng CTE đệ quy

~~~sql
-- Kiểm tra đề xuất thêm cạnh parent_id=6, child_id=2.
-- TRUE nghĩa là cạnh mới sẽ tạo chu trình.
WITH RECURSIVE reachable(node_id) AS (
    SELECT 2::BIGINT

    UNION

    SELECT e.child_id
    FROM reachable AS r
    JOIN taxonomy_edges AS e ON e.parent_id = r.node_id
)
SELECT EXISTS (
    SELECT 1 FROM reachable WHERE node_id = 6
) AS would_create_cycle;
-- true: 2 -> 4 -> 5 -> 6 đã tồn tại
~~~

Trong truy vấn trên, **UNION** loại bản ghi node_id trùng nhau nên phép duyệt trên một đồ thị hữu hạn có thể dừng ngay cả nếu dữ liệu hiện tại đã có chu trình. Dùng **UNION ALL** mà chỉ lưu node_id, không có cơ chế ghi nhớ nút đã đi qua, có thể khiến CTE chạy vô hạn khi gặp vòng.

Kiểm tra cần được thực hiện **trước cả INSERT lẫn UPDATE các đầu cạnh**; chỉnh sửa một cạnh có thể tạo ra chu trình giống như thêm cạnh mới. Các thao tác xóa cạnh không tạo thêm chu trình, nhưng có thể phá vỡ yêu cầu về tính liên thông hoặc số cha tối thiểu.

### 5.2. Vì sao “kiểm tra rồi INSERT” vẫn chưa đủ an toàn?

Giả sử ban đầu A và B không có đường đi đến nhau:

- Giao dịch T1 kiểm tra và chuẩn bị thêm **A → B**.
- Giao dịch T2 đồng thời kiểm tra và chuẩn bị thêm **B → A**.
- Mỗi giao dịch đọc trạng thái chưa có cạnh từ giao dịch kia, nên đều kết luận “không có chu trình”.
- Nếu cả hai INSERT rồi COMMIT mà không có cơ chế phối hợp phù hợp, kết quả tạo vòng A ↔ B.

Đây là **điều kiện tranh chấp (race condition)**, không phải lỗi của công thức kiểm tra đường đi. Với chính sách DAG bắt buộc, cần kiểm tra **và ghi cạnh như một thao tác nhất quán**.

Những cách tiếp cận phù hợp có thể gồm:

1. **Tuần tự hóa thay đổi của cùng đồ thị/tenant** bằng khóa giao dịch áp dụng nhất quán cho **mọi** thao tác đổi cạnh, rồi kiểm tra reachability và ghi trong cùng giao dịch. Trong PostgreSQL có thể dùng khóa tư vấn giao dịch (*transaction-level advisory lock*) trên định danh cây/tenant; chọn khóa và quyền sử dụng sao cho mọi writer tuân theo quy ước.
2. **Dùng giao dịch mức SERIALIZABLE** và xử lý lỗi serialization bằng cách **thử lại toàn bộ giao dịch**. Phải xác minh các thao tác kiểm tra/ghi đều tham gia cùng cơ chế kiểm soát; không thể chỉ đổi isolation level trên một truy vấn đọc riêng lẻ.
3. **Dùng cơ chế ghi tập trung** hoặc trigger/procedure trong cơ sở dữ liệu thực hiện kiểm tra và phối hợp ghi. Một trigger chỉ SELECT kiểm tra đường đi ở mức đọc mặc định vẫn có thể gặp race condition nếu không có cơ chế đồng bộ.

Không nên dựa duy nhất vào một câu SELECT chạy trước INSERT ở tầng ứng dụng. Khóa ngoại, PRIMARY KEY và CHECK ở ví dụ chỉ kiểm tra tính tồn tại, tính duy nhất và vòng tự thân; **chúng không tự cưỡng chế tính vô chu trình của toàn đồ thị**.

## 6. Phát hiện chu trình đã có trong dữ liệu

Khi nhập dữ liệu cũ, đồng bộ từ một hệ thống khác hoặc nghi ngờ bảng cạnh bị ghi sai, cần tìm những chu trình **đã tồn tại**.

### 6.1. Duyệt có ghi nhớ đường đi

Trong PostgreSQL, có thể giữ mảng các node_id đã đi qua. Khi bước kế tiếp gặp một ID đã có trong mảng, ta đánh dấu một chu trình và **không tiếp tục mở rộng** đường đó.

~~~sql
WITH RECURSIVE walks AS (
    SELECT n.node_id AS start_id,
           n.node_id AS current_id,
           ARRAY[n.node_id]::BIGINT[] AS path,
           FALSE AS is_cycle
    FROM taxonomy_nodes AS n

    UNION ALL

    SELECT w.start_id,
           e.child_id,
           w.path || e.child_id,
           e.child_id = ANY(w.path)
    FROM walks AS w
    JOIN taxonomy_edges AS e ON e.parent_id = w.current_id
    WHERE NOT w.is_cycle
)
SELECT DISTINCT start_id, path AS cycle_containing_path
FROM walks
WHERE is_cycle
ORDER BY start_id, path;
~~~

Với **dữ liệu ví dụ trước khi thêm cạnh 6 → 2**, truy vấn trả về **không hàng nào**. Nếu thử trong một giao dịch có thể rollback để minh họa:

~~~sql
BEGIN;

INSERT INTO taxonomy_edges (parent_id, child_id)
VALUES (6, 2);

-- Chạy truy vấn phát hiện chu trình ở trên:
-- xuất hiện các đường có đoạn lặp như 2 -> 4 -> 5 -> 6 -> 2.

ROLLBACK;
~~~

**Giải thích:** Mỗi đường bắt đầu từ một nút. Ở bước duyệt, điều kiện **e.child_id = ANY(w.path)** phát hiện node_id lặp trong *chính đường đang xét*. Nhánh đã ghi is_cycle = TRUE không tiếp tục mở rộng, nên không lặp vô hạn theo đường ấy.

Tuy nhiên, khi đồ thị lớn và có **rất nhiều đường đi khác nhau** giữa cùng hai nút, cách liệt kê đường từ **mọi nút** có thể sinh số lượng dòng rất lớn, dù không có chu trình. Nó phù hợp để minh họa, chẩn đoán trên tập dữ liệu giới hạn hoặc chạy kiểm tra quản trị có giới hạn tài nguyên; **không phải chiến lược giám sát hiệu năng cao cho mọi đồ thị khổng lồ**.

PostgreSQL phiên bản hỗ trợ cú pháp **CYCLE** trong CTE đệ quy cũng có thể tự theo dõi các nút đã đi qua. Dù dùng CYCLE hay mảng path, cần xác định đúng cột đại diện cho “trạng thái nút” để nhận diện quay lại.

### 6.2. Chỉ duyệt từ gốc có đủ không?

**Không đủ trong mọi trường hợp.** Một nhóm nút tạo vòng có thể **không có gốc** nào, hoặc thuộc một thành phần không đi được từ gốc mà truy vấn đang chọn. Nếu chỉ bắt đầu từ một gốc danh mục, ta có thể bỏ sót vòng ở phần dữ liệu khác.

Khởi tạo từ **tất cả các nút** như trên phát hiện các vòng trong các thành phần khác nhau, nhưng chi phí cao. Với dữ liệu lớn, có thể dùng một thuật toán kiểm tra chu trình toàn đồ thị, ví dụ:

- **DFS với trạng thái đang thăm** (*gray/visiting*) để nhận diện cạnh quay lại nút đang ở trên ngăn xếp.
- **Kahn/topological sorting:** liên tục bỏ các nút bậc vào bằng 0; nếu cuối cùng vẫn còn nút chưa bỏ, đồ thị chứa chu trình có hướng. Các nút còn lại có thể bao gồm nút nằm sau chu trình, nên bước này chủ yếu xác định sự tồn tại của vòng.

Các thuật toán này cần vận hành trên ảnh chụp nhất quán của tập cạnh và giới hạn tài nguyên phù hợp. Nếu chỉ cần biết **có hay không** chu trình, không nhất thiết liệt kê mọi đường tạo vòng.

## 7. Truy vấn trên DAG: một nút, nhiều đường

Với cây, mỗi nút trong nhánh thường có một đường duy nhất từ gốc. Với DAG, truy vấn đệ quy có thể gặp cùng nút theo nhiều đường.

### 7.1. Lấy tập nút có thể đi đến, không tính trùng đường

~~~sql
WITH RECURSIVE descendants(node_id) AS (
    SELECT 1::BIGINT

    UNION

    SELECT e.child_id
    FROM taxonomy_edges AS e
    JOIN descendants AS d ON e.parent_id = d.node_id
)
SELECT n.node_id, n.label
FROM descendants AS d
JOIN taxonomy_nodes AS n ON n.node_id = d.node_id
ORDER BY n.node_id;
~~~

Do dùng **UNION** theo **node_id**, nút 5 chỉ xuất hiện **một lần**, dù có hai đường từ 1 đến 5. CTE này trả về tập nút **reachable** bao gồm chính gốc 1. Nếu cần “hậu duệ không kể nút gốc”, loại node_id = 1.

Kỹ thuật UNION đặc biệt phù hợp khi chỉ quan tâm **tồn tại đường đi** chứ không cần biết đường đi cụ thể hoặc độ sâu. Nó cũng giúp quá trình đệ quy dừng trên đồ thị hữu hạn ngay cả khi dữ liệu có vòng, miễn hàng đệ quy chỉ mang một trạng thái node_id.

### 7.2. Nếu cần biết mọi đường đi hoặc số tầng

Khi cần breadcrumb theo từng nhánh, một tập node_id đã khử trùng là **không đủ**. Có thể lưu cả path và depth, cấm lặp nút ngay trên đường:

~~~sql
WITH RECURSIVE paths AS (
    SELECT 1::BIGINT AS node_id,
           ARRAY[1::BIGINT] AS path,
           0 AS depth

    UNION ALL

    SELECT e.child_id,
           p.path || e.child_id,
           p.depth + 1
    FROM paths AS p
    JOIN taxonomy_edges AS e ON e.parent_id = p.node_id
    WHERE NOT e.child_id = ANY(p.path)
)
SELECT node_id,
       MIN(depth) AS shortest_depth,
       MAX(depth) AS longest_depth,
       COUNT(*) AS distinct_paths_from_root
FROM paths
GROUP BY node_id
ORDER BY node_id;
~~~

Với DAG mẫu, nút 5 có **shortest_depth = 2**, **longest_depth = 3**, **distinct_paths_from_root = 2**. Các đường là 1 → 3 → 5 và 1 → 2 → 4 → 5.

Đếm đường đi có thể rất tốn kém: một DAG tuy ít nút vẫn có số đường tăng theo cấp số nhân. Chỉ thực hiện truy vấn liệt kê đường khi nghiệp vụ **thực sự cần từng đường** và có giới hạn kích thước hợp lý. Nếu chỉ cần số tổ tiên duy nhất, dùng phép duyệt khử trùng theo nút hoặc cấu trúc reachability chuyên dụng.

### 7.3. Bảng bao đóng trên DAG cần ngữ nghĩa độ sâu rõ ràng

Một **closure table** với khóa **(ancestor_id, descendant_id)** vẫn có thể lưu việc *có đường đi hay không* trên DAG. Nhưng nếu mỗi cặp chỉ có **một depth**, ta phải xác định depth là:

- khoảng cách **ngắn nhất**;
- khoảng cách **dài nhất**;
- hoặc một giá trị theo nhánh đại diện.

Nếu cần cả nhiều khoảng cách và nhiều đường đi, không thể đơn giản tái dùng closure table của **cây** như thể mỗi cặp chỉ có đúng một đường. Ngoài ra, khi DAG có nhiều đường từ tổ tiên đến hậu duệ, **xóa một cạnh** không nhất thiết làm mất reachability giữa hai nút. Xóa tùy tiện một hàng closure chỉ vì một đường đi biến mất sẽ làm sai dữ liệu; cần tính lại trạng thái reachable hoặc duy trì bộ đếm/đường đi theo thuật toán đã xác định.

## 8. Khi nào có thể giữ mô hình quan hệ, khi nào nên dùng graph database?

Việc dữ liệu là **đồ thị** theo nghĩa toán học **không bắt buộc** phải dùng **graph database**. RDBMS có thể lưu bảng nút và bảng cạnh, với CTE đệ quy, chỉ mục và giao dịch; điều này đủ cho rất nhiều hệ thống.

| Dấu hiệu yêu cầu | Thiết kế có thể phù hợp | Lý do |
| --- | --- | --- |
| Phân cấp một cha, chủ yếu hiển thị cây | Adjacency list trong RDBMS | Cấu trúc gọn, FK đơn giản, truy vấn đệ quy khi cần |
| DAG nhỏ hoặc vừa, cần tìm tổ tiên/hậu duệ | Bảng nút–cạnh trong RDBMS | Khóa và chỉ mục rõ, CTE giải quyết reachability |
| DAG cần nhiều truy vấn bắc cầu lặp lại | Bảng cạnh + cache/closure hợp lý | Tăng tốc đọc với chi phí cập nhật và kiểm soát nhất quán |
| Nhiều loại quan hệ giữa các kiểu nút, truy vấn theo mẫu đường đi | Cân nhắc graph database | Truy vấn traversal và mẫu cạnh có thể tự nhiên hơn |
| Phân tích nhiều bước qua mạng lưới lớn, độ dài đường biến thiên | Đánh giá graph database/engine đồ thị | Có thể phù hợp với traversal/phân tích graph chuyên dụng |
| Chủ yếu là giao dịch có ràng buộc quan hệ mạnh và JOIN ngắn | RDBMS vẫn là ứng viên tốt | Không cần đổi công nghệ chỉ vì có một bảng cạnh |
| Cần tìm đường tối ưu theo trọng số/định tuyến | Engine/thuật toán graph phù hợp | Cần định nghĩa trọng số, hướng cạnh và giới hạn đường đi |

### Những câu hỏi đáng đo trước khi chọn công nghệ

- **Số nút/cạnh:** hàng chục nghìn, hàng triệu hay hàng tỷ? Độ phân bố bậc của nút có lệch mạnh không?
- **Số bước truy vấn:** chỉ một hoặc hai hop, hay đường dài biến thiên?
- **Hình dạng truy vấn:** lấy tất cả hậu duệ, tìm chu trình, tìm đường ngắn nhất, tìm mẫu nhiều loại cạnh, hay phân tích cộng đồng?
- **Mức cập nhật:** cạnh có đổi liên tục và cần kiểm soát giao dịch cùng dữ liệu nghiệp vụ khác không?
- **Ràng buộc:** có yêu cầu khóa ngoại, phiên bản lịch sử, tenant, phân quyền và đồng bộ với kho dữ liệu khác không?
- **Vận hành:** nhóm có khả năng quản trị, giám sát, sao lưu, phân quyền, sao chép và kiểm tra đúng đắn trên công nghệ được chọn không?

**Graph database không tự động loại trừ chu trình**, cũng không mặc định biết cạnh nào hợp lệ theo nghiệp vụ. Nếu taxonomy phải là DAG, hệ thống vẫn cần quy tắc chống chu trình, kể cả khi lưu bằng property graph có node và relationship.

## 9. Thiết kế đồ thị có nhiều kiểu quan hệ

Khi hệ thống có nhiều loại quan hệ, chỉ một cột parent_id hoặc một bảng taxonomy_edges có thể trở nên quá chung hoặc sai nghĩa.

Ví dụ nền tảng đào tạo có:

- **Skill REQUIRES Skill:** kỹ năng A phải có trước kỹ năng B. Thông thường cần **DAG** để có thứ tự học hợp lệ.
- **Course TEACHES Skill:** khóa học dạy kỹ năng; đây là quan hệ giữa hai loại thực thể, không phải cạnh cha–con.
- **User FOLLOWS User:** quan hệ người dùng theo dõi nhau; **chu trình hai chiều hoàn toàn hợp lệ**.
- **Team MEMBER_OF Organization:** thành viên thuộc tổ chức; có quy tắc khác về số lượng, thời gian và vai trò.

Không nên dùng một cột quan hệ tên chung như parent_id cho cả bốn trường hợp. Cần mô hình loại cạnh, hướng và ràng buộc theo từng kiểu quan hệ:

| Loại cạnh | Cấu trúc có thể có | Chu trình | Ràng buộc cần xác nhận |
| --- | --- | --- | --- |
| PREREQUISITE | Skill → Skill | Thường cấm | Không tự tham chiếu; không đường quay lại; phiên bản kỹ năng |
| SUBCATEGORY_OF | Category → Category | Cấm | Số cha được phép, cùng taxonomy/tenant |
| FOLLOWS | User → User | Có thể hợp lệ | Có cho theo dõi bản thân không; một cặp lặp không |
| MEMBER_OF | User → Group | Quan hệ khác loại nút | Hiệu lực, vai trò trong nhóm, tư cách hoạt động |
| DEPENDS_ON | Service → Service | Tùy mục tiêu | Vòng phụ thuộc có bị cấm triển khai không, hay mô hình chấp nhận vòng để phân tích |

Một property graph có thể tạo các loại node/edge tương ứng, còn RDBMS có thể dùng **các bảng quan hệ chuyên biệt** thay vì gom mọi liên kết vào một bảng polymorphic. Tránh một bảng cạnh chung với cột source_type/source_id/target_type/target_id khi cách đó làm mất khả năng tạo **khóa ngoại có kiểm chứng** tới từng loại đối tượng. Nếu dùng bảng cạnh tổng quát, cần bổ sung cơ chế cưỡng chế tham chiếu và kiểu quan hệ rõ ràng.

### Quan hệ theo thời gian

Một nút có hai cha **ở hai thời điểm khác nhau** không nhất thiết có **hai cha đồng thời**. Nếu nghiệp vụ cho phép chuyển parent, nên lưu lịch sử hiệu lực:

~~~text
HierarchyEdge(
  parent_id,
  child_id,
  valid_from,
  valid_to
)
~~~

Tại một thời điểm t, chỉ lấy các cạnh có khoảng hiệu lực chứa t. Nếu chính sách “mỗi nút có tối đa một cha” áp dụng **theo từng thời điểm**, cần cấm các khoảng hiệu lực chồng nhau đối với cùng child_id nhưng thuộc các cha khác nhau. Nếu chính sách “không có chu trình” áp dụng theo từng thời điểm, cần kiểm tra chu trình trong **đồ thị các cạnh có hiệu lực tại thời điểm đó**, không phải chỉ trong đồ thị gộp mọi cạnh lịch sử.

Một đồ thị gộp toàn bộ lịch sử có thể chứa đường quay lại dù **chưa từng có chu trình đồng thời**. Ngược lại, một lược đồ chỉ lưu cạnh hiện tại sẽ không trả lời được “trước ngày đổi cơ cấu, nút này có cha nào?”.

## 10. Chất lượng dữ liệu, tenant và an toàn thao tác

### 10.1. Không tạo cạnh xuyên tenant ngoài chính sách

Trong hệ thống nhiều tổ chức, node_id có thể được đánh số riêng từng tenant. Nếu cần đảm bảo cạnh chỉ nối các nút trong cùng tenant, có thể thiết kế khóa ghép ngay từ đầu:

~~~sql
CREATE TABLE tenant_nodes (
    tenant_id BIGINT NOT NULL,
    node_id   BIGINT NOT NULL,
    label     TEXT NOT NULL,
    PRIMARY KEY (tenant_id, node_id)
);

CREATE TABLE tenant_edges (
    tenant_id BIGINT NOT NULL,
    parent_id BIGINT NOT NULL,
    child_id  BIGINT NOT NULL,
    PRIMARY KEY (tenant_id, parent_id, child_id),
    FOREIGN KEY (tenant_id, parent_id)
        REFERENCES tenant_nodes (tenant_id, node_id),
    FOREIGN KEY (tenant_id, child_id)
        REFERENCES tenant_nodes (tenant_id, node_id),
    CHECK (parent_id <> child_id)
);
~~~

Hai FK ghép buộc cả parent lẫn child có mặt **trong cùng tenant_id của cạnh**. Các truy vấn reachability, phát hiện chu trình, kiểm tra số cha và khóa dùng khi cập nhật phải lọc cùng tenant_id.

### 10.2. Những kiểm tra nên có

| Bất biến | Cách kiểm chứng |
| --- | --- |
| Mỗi nút có định danh duy nhất | PRIMARY KEY trên bảng node |
| Mọi cạnh nối hai nút tồn tại | FOREIGN KEY ở hai đầu |
| Không lặp cạnh cùng hướng | PRIMARY KEY/UNIQUE trên cặp nút |
| Không có cạnh tự trỏ nếu bị cấm | CHECK(parent_id <> child_id) |
| Tối đa một cha trực tiếp nếu là cây | UNIQUE(child_id) hoặc cột parent_id |
| Không có chu trình nếu là DAG | Kiểm tra reachability khi thêm/sửa cạnh và phối hợp giao dịch |
| Chỉ nối nút trong cùng tenant | Khóa ngoại ghép, truy vấn và quyền truy cập theo tenant |
| Một gốc chung nếu yêu cầu | Kiểm tra số gốc và phạm vi liên thông |
| Cạnh có hiệu lực theo đúng thời gian | Khoảng hiệu lực hợp lệ; kiểm tra chồng lấp và quy tắc theo thời điểm |

Những quy tắc như **không chu trình**, **mọi nút được nối tới gốc** hoặc **đúng một nguồn gốc** là tính chất của **nhiều hàng**. Một CHECK chỉ tham chiếu các cột cùng hàng không tự chứng minh được chúng.

### 10.3. Cẩn thận khi xóa cạnh và nút

Một cạnh có thể được xóa mà vẫn giữ nguyên reachability vì có đường thay thế trong DAG. Ví dụ bỏ cạnh **3 → 5** thì 1 vẫn đi đến 5 qua 2 → 4 → 5. Nhưng xóa cạnh **5 → 6** khiến 6 không còn nối với gốc, trừ khi có cạnh khác.

Việc xóa node có FK từ edge đến node có thể bị từ chối hoặc được cấu hình xóa liên đới. Với danh mục đang được sản phẩm sử dụng hoặc kỹ năng đang làm điều kiện học, xóa vật lý có thể gây mất tham chiếu hoặc lịch sử. Hãy xác định liệu cần xóa toàn bộ phụ thuộc, chuyển cạnh, lưu trữ inactive hay cấm xóa.

## 11. So sánh quan hệ, document, đồ thị và phân tích

Quy tắc “nhiều cha” và “không chu trình” tồn tại ở **mức nghiệp vụ**; cách lưu trữ chỉ quyết định cách biểu diễn và cưỡng chế.

| Kiến trúc | Biểu diễn phổ biến | Điểm mạnh | Rủi ro cần kiểm soát |
| --- | --- | --- | --- |
| **RDBMS** | node + edge, recursive CTE, có thể closure | PK/FK, giao dịch, JOIN và dữ liệu nghiệp vụ chung | Kiểm tra chu trình xuyên nhiều hàng; chi phí duyệt sâu |
| **Document** | parentIds, childIds hoặc collection edge | Đọc một document/nút tiện lợi, linh hoạt schema | Hai phía cập nhật lệch nhau; vòng và cạnh sai tenant; tài liệu lớn |
| **Graph database** | node/relationship có hướng, loại, thuộc tính | Biểu đạt nhiều quan hệ và truy vấn theo đường đi tự nhiên | Cần kiểm soát quy tắc nghiệp vụ, chi phí đường đi, phân quyền và vận hành |
| **Data warehouse** | bridge ancestor–descendant, bảng edge theo phiên bản | Phân tích phân cấp và tác động bắc cầu | Đếm trùng khi nhiều đường tới cùng nút, sai hiệu lực thời gian |

### Ví dụ document cho nút nhiều cha

~~~json
{
  "nodeId": 5,
  "label": "Đồng hồ thông minh",
  "parentIds": [3, 4]
}
~~~

Một mảng parentIds biểu diễn được hai cha, nhưng **không tự phát hiện chu trình**; cần kiểm tra và cập nhật nhất quán. Nếu đồng thời lưu childIds ở mỗi cha, đó là **dữ liệu hai chiều dư thừa** và phải đồng bộ hai phía. Với những quan hệ có thuộc tính như thời hạn hiệu lực hoặc nguồn phân loại, một collection **edges** tách riêng có thể dễ quản lý hơn mảng id.

### Tại sao số liệu phân tích dễ bị nhân đôi?

Giả sử một sản phẩm được gắn danh mục 5, danh mục đó có hai đường về gốc 1. Khi JOIN đơn hàng tới tất cả đường từ 5 lên 1, có thể nhận **hai hàng ứng với cùng một sản phẩm/đơn hàng**. Nếu cộng doanh thu trên các hàng đó, doanh thu bị **nhân đôi** dù giao dịch chỉ xảy ra một lần.

Đối với báo cáo cần phân loại theo **tập tổ tiên duy nhất**, hãy khử trùng cặp (fact_id, ancestor_id) theo đúng hạt dữ liệu. Nếu nghiệp vụ yêu cầu **phân bổ doanh thu theo từng nhánh**, cần quy tắc trọng số/phân bổ rõ ràng thay vì lấy DISTINCT một cách máy móc. Hai bài toán khác nhau sẽ cho kết quả khác nhau nhưng đều có thể hợp lệ nếu có định nghĩa chỉ tiêu chính xác.

## 12. Quy trình chuyển yêu cầu thành mô hình có thể kiểm chứng

Có thể sử dụng chuỗi quyết định sau trong quá trình phân tích:

1. **Viết mệnh đề nghiệp vụ về cạnh:** “A là cha của B” có nghĩa gì, chiều nào, trong phạm vi thời gian và tenant nào?
2. **Đếm cha trực tiếp hợp lệ:** 0..1, đúng 1 trừ gốc, hay 0..N? Phân biệt “nút có nhiều cha” với “một đối tượng gán vào nhiều nhóm”.
3. **Xác định chu trình hợp lệ hay bất hợp lệ:** đặc biệt với quan hệ “phụ thuộc trước”, “cấp trên” và “thành phần”.
4. **Chọn cấu trúc:** cây/rừng cây với parent_id; DAG với bảng cạnh; graph tổng quát nếu có vòng hoặc nhiều loại quan hệ.
5. **Chọn công nghệ sau khi đã rõ cấu trúc:** RDBMS, document hoặc graph database tùy hình dạng truy vấn, khối lượng và yêu cầu giao dịch.
6. **Thiết kế khóa và chỉ mục:** node_id, cặp đầu cạnh, chỉ mục đảo để tìm cha, FK ghép khi có tenant và thời gian hiệu lực nếu cần.
7. **Thiết kế ràng buộc xuyên bảng:** kiểm tra chu trình khi INSERT/UPDATE, số cha, liên thông, điều kiện trạng thái; xử lý cập nhật cạnh tranh.
8. **Quy định lịch sử và xóa:** khi đổi cha, khi hết hiệu lực, khi xóa nút có phụ thuộc và khi truy vấn phiên bản quá khứ.
9. **Kiểm tra chất lượng bằng tình huống biên:** chu trình ba nút, hai giao dịch thêm cạnh đối nghịch, nhiều cha hợp lệ, cạnh sang tenant khác, hai đường cùng đến một nút.
10. **Đo và điều chỉnh:** dùng dữ liệu đại diện để đo truy vấn reachability, độ sâu, số cạnh và số đường đi; giới hạn truy vấn liệt kê đường có khả năng bùng nổ.

## 13. Bài tập tự kiểm tra có lời giải

### Bài 1. Có thật sự cần nhiều cha?

**Đề bài:** Một sản phẩm có thể gắn nhiều nhãn; mỗi nhãn nằm trong đúng một nhóm cha. Nhân viên đề xuất cho bảng nhóm nhãn nhiều parent_id vì sản phẩm có nhiều nhãn.

**Lời giải:** **Không nhất thiết.** Sản phẩm có nhiều nhãn là quan hệ nhiều–nhiều **Product–Tag**. Mỗi Tag vẫn có thể có một TagGroup cha duy nhất. Chỉ cần mô hình nhiều cha nếu bản thân **TagGroup hoặc Tag** được phép thuộc nhiều nhóm cha trực tiếp.

### Bài 2. Thêm cạnh nào tạo chu trình?

**Đề bài:** DAG có cạnh 1 → 2, 2 → 4, 4 → 5, 5 → 6. Xét ba cạnh đề xuất 6 → 2, 3 → 5, 6 → 7 (giả sử nút 3 và 7 đã tồn tại).

**Lời giải:** **6 → 2** tạo vòng **2 → 4 → 5 → 6 → 2**. Hai cạnh còn lại không tạo vòng nếu không có đường sẵn có từ 5 về 3 hoặc từ 7 về 6. Cần kiểm tra đồ thị đầy đủ trước khi kết luận trong hệ thống thật.

### Bài 3. Tại sao UNIQUE(child_id) không thay cho kiểm tra chu trình?

**Đề bài:** Mỗi nút chỉ có một cha. Vì sao vẫn có thể có vòng?

**Lời giải:** Ràng buộc UNIQUE(child_id) chỉ giới hạn số cạnh đi **vào** một nút. Ba cạnh **A → B, B → C, C → A** cho mỗi nút đúng một cha nhưng vẫn có chu trình. Phải kiểm tra tính vô chu trình riêng.

### Bài 4. Nhiều đường ảnh hưởng báo cáo thế nào?

**Đề bài:** Nút 5 có hai đường đi từ 1, mỗi giao dịch gắn với nút 5 có doanh thu 100. Nếu nối giao dịch với tất cả đường đến 1 rồi SUM, báo cáo gốc có thể ra bao nhiêu?

**Lời giải:** Nếu JOIN tạo hai hàng cho hai đường, phép SUM cho ra **200** dù doanh thu thật là **100**. Nếu chỉ cần tính doanh thu một lần trên tập tổ tiên duy nhất, phải khử trùng cặp giao dịch–tổ tiên hoặc tính tổng ở đúng hạt trước khi nối.

### Bài 5. Khi nào chu trình hợp lệ?

**Đề bài:** User A theo dõi User B và User B theo dõi User A. Có cần cấm vòng?

**Lời giải:** Với quan hệ **FOLLOWS**, vòng hai chiều có thể là hành vi hợp lệ. Nếu cùng cấu trúc cạnh được dùng cho **PREREQUISITE** của khóa học, vòng A → B → A sẽ khiến yêu cầu học trước mâu thuẫn, thường phải cấm. Chính **ngữ nghĩa của loại cạnh** quyết định quy tắc.

### Bài 6. Hai giao dịch đồng thời

**Đề bài:** T1 kiểm tra rồi thêm A → B, T2 kiểm tra rồi thêm B → A. Mỗi lần kiểm tra riêng đều báo “không tạo vòng”. Điều gì còn thiếu?

**Lời giải:** Thiếu cơ chế phối hợp **đọc và ghi** trong cùng phạm vi đồ thị: khóa giao dịch để tuần tự hóa thay đổi, SERIALIZABLE kèm retry hoặc cơ chế tương đương. Chỉ truy vấn reachability một lần trước INSERT không đủ cưỡng chế bất biến trong môi trường có cập nhật đồng thời.

## 14. Ghi nhớ

- **Một cha** và **không chu trình** là hai ràng buộc riêng biệt; cả hai cần được xác định từ nghiệp vụ.
- **Nhiều cha nhưng không vòng** dẫn tới **DAG**; **có vòng được phép** dẫn tới đồ thị tổng quát với quy tắc riêng cho mỗi loại cạnh.
- Khi đề xuất thêm cạnh **P → C**, phải bác bỏ nếu **P = C** hoặc **C đã đi đến P** theo các cạnh có hướng hiện tại.
- Truy vấn trên DAG cần phân biệt **nút duy nhất** và **đường đi**; nhiều đường tới một nút không có nghĩa nhiều thực thể, cũng không có nghĩa số đo được cộng nhiều lần.
- **Graph database là một lựa chọn công nghệ**, còn *graph* là một cấu trúc dữ liệu. Có thể biểu diễn và kiểm tra nhiều mô hình đồ thị bằng RDBMS, rồi lựa chọn công nghệ theo tải và yêu cầu truy vấn thực tế.

Việc mô hình hóa đúng giúp tránh chu trình vô tình, tránh nhân bản danh tính khi một nút có nhiều cha, và bảo đảm các quan hệ phân cấp, phụ thuộc và vai trò được kiểm chứng xuyên suốt từ yêu cầu nghiệp vụ đến lược đồ vật lý.
