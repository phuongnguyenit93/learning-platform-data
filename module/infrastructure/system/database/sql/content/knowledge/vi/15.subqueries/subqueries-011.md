# Diễn đạt yêu cầu mọi phần tử bằng NOT EXISTS lồng nhau

Trong nhiều bài toán SQL, câu hỏi không phải là “đối tượng này **có ít nhất một** quan hệ phù hợp không?” mà là **“đối tượng này đã đáp ứng tất cả những phần tử bắt buộc chưa?”**. Ví dụ:

- Tìm **ứng viên có đủ mọi kỹ năng bắt buộc** cho một vị trí.
- Tìm **học viên đã hoàn thành tất cả môn bắt buộc**.
- Tìm **nhà cung cấp có thể cung cấp tất cả mặt hàng** của một danh sách mua sắm.
- Tìm **khách hàng đã mua mọi sản phẩm** trong một bộ sản phẩm được chỉ định.
- Tìm **nhóm đã xử lý mọi nhiệm vụ** được giao.

Đây là dạng truy vấn **lượng từ toàn thể**: “với **mọi** phần tử thuộc tập yêu cầu, phải tồn tại một sự tương ứng hợp lệ”. SQL không có một dạng `FOR ALL` phổ quát trong mệnh đề `WHERE` để diễn đạt trực tiếp quan hệ như vậy. Một cách giải quyết đặc biệt rõ nghĩa là **hai tầng `NOT EXISTS`**:

> **Không tồn tại một yêu cầu bắt buộc nào mà đối tượng đang xét không có bản ghi đáp ứng.**

Bài học thuộc chủ đề **Truy vấn con** trong module **Database SQL**. Các ví dụ thực hành chạy với **PostgreSQL**; cấu trúc `EXISTS`, `NOT EXISTS` và truy vấn con tương quan áp dụng được với nhiều hệ quản trị SQL khác.

## 1. Từ “có ít nhất một” sang “có tất cả”

Hãy phân biệt ba câu hỏi:

1. “Ứng viên có **ít nhất một** kỹ năng bắt buộc không?”
2. “Ứng viên **không có kỹ năng bắt buộc nào** không?”
3. “Ứng viên có **tất cả** kỹ năng bắt buộc không?”

Chúng có nghĩa khác nhau.

| Yêu cầu | Diễn đạt bằng lời | Gợi ý SQL |
|---|---|---|
| **Có ít nhất một** | Tồn tại một yêu cầu mà ứng viên đáp ứng | `EXISTS (...)` |
| **Không có cái nào** | Không tồn tại yêu cầu nào mà ứng viên đáp ứng | `NOT EXISTS (...)` |
| **Có tất cả** | Không tồn tại yêu cầu nào mà ứng viên **không** đáp ứng | `NOT EXISTS (... NOT EXISTS (...))` |

Ví dụ, vị trí yêu cầu **SQL, Java và Git**:

| Ứng viên | SQL | Java | Git | Có ít nhất một? | Có tất cả? |
|---|---|---|---|---|---|
| An | Có | Có | Có | Có | **Có** |
| Bình | Có | Có | Không | Có | **Không** |
| Chi | Có | Có | Có | Có | **Có** |
| Dũng | Không | Không | Không | Không | **Không** |

`EXISTS` đơn thường đủ để kiểm tra **có ít nhất một kỹ năng**. Muốn kiểm tra **mọi kỹ năng trong một tập yêu cầu động**, chúng ta cần biết liệu có **kỹ năng bắt buộc bị thiếu** nào hay không.

Điểm mấu chốt không phải đếm số lần xuất hiện của chữ `NOT`, mà là hiểu **đối tượng nào đang bị phủ định** ở mỗi tầng.

## 2. Ý tưởng logic: “mọi” tương đương “không có phản ví dụ”

Ký hiệu:

- `C` là tập ứng viên.
- `R` là tập kỹ năng bắt buộc.
- `P(c, r)` có nghĩa “ứng viên `c` đáp ứng kỹ năng `r`”.

Mục tiêu là tìm các ứng viên `c` thỏa:

\[
\forall r \in R,\;P(c,r).
\]

Đọc: **Với mọi kỹ năng `r` thuộc tập bắt buộc, ứng viên `c` đều đáp ứng `r`**.

Tương đương về logic:

\[
\neg\exists r\in R:\neg P(c,r).
\]

Đọc: **Không tồn tại kỹ năng bắt buộc nào mà ứng viên không đáp ứng**.

Nếu “đáp ứng kỹ năng” được thể hiện bằng **sự tồn tại một dòng chứng nhận hợp lệ** thì:

\[
P(c,r)
\equiv
\exists s:\bigl(s.candidate\_id=c.id
\land s.skill\_id=r.id
\land s.verified=true\bigr).
\]

Thay vào biểu thức trên:

\[
\neg\exists r\in R:
\neg\exists s:\text{matching\_verified\_skill}(s,c,r).
\]

Đây chính là hai tầng phủ định trong SQL:

```sql
SELECT ...
FROM candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM required_skills AS r
    WHERE NOT EXISTS (
        SELECT 1
        FROM candidate_skills AS cs
        WHERE cs.candidate_id = c.candidate_id
          AND cs.skill_id = r.skill_id
          AND cs.is_verified = TRUE
    )
);
```

Ở đây `required_skills` là **tên mô tả nguồn yêu cầu về mặt ý tưởng**, chưa phải bảng thực hành. Trong phần sau, nguồn này sẽ được lấy từ bảng `lesson199_skills` với điều kiện `is_required = TRUE`.

### 2.1. Đọc câu truy vấn từ trong ra ngoài

1. `NOT EXISTS` **bên trong**: với một ứng viên `c` và một kỹ năng yêu cầu `r`, kiểm tra **không tồn tại chứng nhận hợp lệ tương ứng**.
2. `WHERE NOT EXISTS (bên trong)` của bảng yêu cầu: chỉ nhận các kỹ năng `r` **đang bị thiếu**.
3. `NOT EXISTS` **bên ngoài**: ứng viên chỉ được chọn khi tập kỹ năng **đang bị thiếu** là rỗng.

Vì vậy:

```text
Ứng viên c
    │
    ├─ Xem từng kỹ năng r trong tập bắt buộc R
    │      │
    │      └─ Có dòng candidate_skills hợp lệ cho (c, r)?
    │                  │
    │                  ├─ Có  → không phải kỹ năng thiếu
    │                  └─ Không → có một phản ví dụ
    │
    └─ Có tồn tại bất kỳ phản ví dụ nào?
               │
               ├─ Có    → loại ứng viên
               └─ Không → chọn ứng viên
```

**Không cần một nhánh `ELSE` hay một phép đếm bằng 0 ở đây:** `NOT EXISTS` trả giá trị logic dựa trên **tập dòng của truy vấn con có rỗng hay không**.

## 3. Chuẩn bị dữ liệu thực hành PostgreSQL

Ta thiết kế ba bảng:

- `lesson199_candidates`: danh sách ứng viên.
- `lesson199_skills`: danh mục kỹ năng, có cờ `is_required` cho biết kỹ năng nào bắt buộc.
- `lesson199_candidate_skills`: ứng viên có kỹ năng nào và việc xác minh đã hoàn tất chưa.

Hãy dùng **cơ sở dữ liệu thực hành** và chỉ chạy các lệnh tạo bảng/nhập dữ liệu một lần.

### 3.1. Tạo các bảng

```sql
CREATE TABLE lesson199_candidates (
    candidate_id INTEGER PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL
);

CREATE TABLE lesson199_skills (
    skill_id INTEGER PRIMARY KEY,
    skill_name VARCHAR(100) NOT NULL UNIQUE,
    is_required BOOLEAN NOT NULL
);

CREATE TABLE lesson199_candidate_skills (
    candidate_id INTEGER NOT NULL
        REFERENCES lesson199_candidates(candidate_id),
    skill_id INTEGER NOT NULL
        REFERENCES lesson199_skills(skill_id),
    is_verified BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (candidate_id, skill_id)
);
```

Khóa chính ghép `(candidate_id, skill_id)` bảo đảm trong bảng này mỗi cặp ứng viên–kỹ năng xuất hiện **tối đa một dòng**. Trong hệ thống cho phép nhiều lần xác minh, bạn có thể có bảng lịch sử riêng; khi đó truy vấn `EXISTS` vẫn chỉ cần **ít nhất một bản ghi hợp lệ**.

### 3.2. Thêm tập dữ liệu

```sql
INSERT INTO lesson199_candidates (candidate_id, full_name)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi'),
    (4, 'Dũng'),
    (5, 'Hà'),
    (6, 'Lan');

INSERT INTO lesson199_skills (
    skill_id, skill_name, is_required
)
VALUES
    (10, 'SQL',    TRUE),
    (20, 'Java',   TRUE),
    (30, 'Git',    TRUE),
    (40, 'Docker', FALSE);

INSERT INTO lesson199_candidate_skills (
    candidate_id, skill_id, is_verified
)
VALUES
    -- An: đủ ba kỹ năng bắt buộc; Docker là kỹ năng thêm.
    (1, 10, TRUE),
    (1, 20, TRUE),
    (1, 30, TRUE),
    (1, 40, TRUE),

    -- Bình: thiếu Git.
    (2, 10, TRUE),
    (2, 20, TRUE),

    -- Chi: đủ đúng ba kỹ năng bắt buộc.
    (3, 10, TRUE),
    (3, 20, TRUE),
    (3, 30, TRUE),

    -- Dũng: không có dòng kỹ năng nào.

    -- Hà: có dòng Git nhưng Git chưa được xác minh.
    (5, 10, TRUE),
    (5, 20, TRUE),
    (5, 30, FALSE),

    -- Lan: đủ ba kỹ năng bắt buộc;
    -- có dòng Docker nhưng Docker chưa được xác minh.
    (6, 10, TRUE),
    (6, 20, TRUE),
    (6, 30, TRUE),
    (6, 40, FALSE);
```

Các cặp trong bảng là **dữ liệu minh họa**, không phải thông tin cá nhân thực.

### 3.3. Nhìn dữ liệu theo ma trận

`TRUE` ở bảng ma trận sau nghĩa là có dòng `is_verified = TRUE`. Dấu `–` nghĩa là không có dòng hoặc chưa được xác minh; khi kiểm tra “đáp ứng kỹ năng”, hai trường hợp này đều **chưa được tính**.

| Ứng viên | SQL (bắt buộc) | Java (bắt buộc) | Git (bắt buộc) | Docker (tùy chọn) | Đủ mọi kỹ năng bắt buộc? |
|---|---|---|---|---|---|
| An | ✓ | ✓ | ✓ | ✓ | **Có** |
| Bình | ✓ | ✓ | – | – | Không |
| Chi | ✓ | ✓ | ✓ | – | **Có** |
| Dũng | – | – | – | – | Không |
| Hà | ✓ | ✓ | – (chưa xác minh) | – | Không |
| Lan | ✓ | ✓ | ✓ | – (chưa xác minh) | **Có** |

Kết quả đúng dự kiến của bài toán “**mọi kỹ năng bắt buộc đã được xác minh**” là **An, Chi và Lan**.

Việc có Docker hay không **không ảnh hưởng** đến yêu cầu này vì `is_required = FALSE`.

## 4. Viết truy vấn NOT EXISTS lồng nhau hoàn chỉnh

```sql
SELECT
    c.candidate_id,
    c.full_name
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson199_skills AS r
    WHERE r.is_required = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM lesson199_candidate_skills AS cs
          WHERE cs.candidate_id = c.candidate_id
            AND cs.skill_id = r.skill_id
            AND cs.is_verified = TRUE
      )
)
ORDER BY c.candidate_id;
```

Kết quả:

| candidate_id | full_name |
|---:|---|
| 1 | An |
| 3 | Chi |
| 6 | Lan |

### 4.1. Tầng ngoài: mỗi dòng là một ứng viên cần xét

```sql
FROM lesson199_candidates AS c
WHERE NOT EXISTS (...)
```

Mỗi ứng viên từ bảng `c` sẽ được xét theo toàn bộ tập kỹ năng bắt buộc. Các cột của ứng viên `c` vẫn được truy cập trong truy vấn con bên trong — đó là **truy vấn con tương quan (correlated subquery)**.

### 4.2. Tầng giữa: tìm kỹ năng bắt buộc còn thiếu

```sql
SELECT 1
FROM lesson199_skills AS r
WHERE r.is_required = TRUE
  AND NOT EXISTS (...)
```

Nguồn `r` là danh mục kỹ năng bắt buộc. Một dòng `r` chỉ nằm trong kết quả truy vấn con khi:

- Kỹ năng đó thật sự bắt buộc, **và**
- **Không có dòng xác minh hợp lệ** cho kỹ năng đó của ứng viên hiện tại.

Nói cách khác, truy vấn giữa tạo ra **danh sách phản ví dụ**: các kỹ năng bắt buộc mà ứng viên chưa đáp ứng.

### 4.3. Tầng trong: có dòng chứng minh đã đáp ứng kỹ năng không?

```sql
SELECT 1
FROM lesson199_candidate_skills AS cs
WHERE cs.candidate_id = c.candidate_id
  AND cs.skill_id = r.skill_id
  AND cs.is_verified = TRUE
```

Ba điều kiện cùng cần đúng:

1. `cs.candidate_id = c.candidate_id`: đúng **ứng viên** đang xét.
2. `cs.skill_id = r.skill_id`: đúng **kỹ năng** bắt buộc đang xét.
3. `cs.is_verified = TRUE`: kỹ năng đó đã **được xác minh**.

Nếu có ít nhất một dòng đáp ứng cả ba điều kiện, `EXISTS` là TRUE, nên `NOT EXISTS` bên trong là FALSE. Kỹ năng đang xét **không phải phản ví dụ**.

Nếu không có dòng nào, `NOT EXISTS` bên trong là TRUE: ứng viên đang **thiếu kỹ năng bắt buộc này**.

### 4.4. Tại sao có hai dấu NOT?

```sql
WHERE NOT EXISTS (                -- Không có yêu cầu bị thiếu.
    SELECT 1
    FROM lesson199_skills AS r
    WHERE r.is_required = TRUE
      AND NOT EXISTS (            -- Yêu cầu r này đang bị thiếu?
          SELECT 1
          FROM lesson199_candidate_skills AS cs
          WHERE cs.candidate_id = c.candidate_id
            AND cs.skill_id = r.skill_id
            AND cs.is_verified = TRUE
      )
)
```

**Dấu NOT bên trong** xác định một yêu cầu **không có chứng cứ đáp ứng**. **Dấu NOT bên ngoài** bảo đảm **không tồn tại bất kỳ yêu cầu bị thiếu**.

Nếu chỉ giữ một trong hai phủ định, câu truy vấn sẽ nói về một quan hệ khác. Vì vậy không nên “rút gọn hai NOT thành một” theo trực giác; hai phủ định áp dụng trên **hai phép tồn tại khác nhau**.

## 5. Mô phỏng từng ứng viên để hiểu kết quả

Đối với ứng viên **An**:

1. SQL: có chứng nhận xác minh → không thiếu.
2. Java: có chứng nhận xác minh → không thiếu.
3. Git: có chứng nhận xác minh → không thiếu.
4. Không tồn tại kỹ năng bắt buộc bị thiếu → `NOT EXISTS` ngoài là TRUE → **chọn An**.

Đối với **Bình**:

1. SQL: có.
2. Java: có.
3. Git: không có dòng phù hợp.
4. Tìm thấy ít nhất một kỹ năng bắt buộc bị thiếu là Git → `NOT EXISTS` ngoài là FALSE → **loại Bình**.

Đối với **Hà**:

1. SQL: có xác minh.
2. Java: có xác minh.
3. Git: **có dòng** nhưng `is_verified = FALSE`.
4. Truy vấn trong không tìm thấy dòng Git **hợp lệ**, nên Git vẫn bị thiếu → **loại Hà**.

Đối với **Dũng**:

1. SQL bị thiếu.
2. Java bị thiếu.
3. Git bị thiếu.
4. Tồn tại rất nhiều phản ví dụ → **loại Dũng**.

Đối với **Lan**:

1. SQL, Java và Git đều hợp lệ.
2. Docker không bắt buộc và chưa xác minh.
3. Không có phản ví dụ trong **tập bắt buộc** → **chọn Lan**.

**Đáp ứng tất cả** không có nghĩa phải có tất cả kỹ năng của toàn hệ thống; chỉ cần đáp ứng **tất cả phần tử thuộc tập yêu cầu được xác định trong truy vấn**.

## 6. Truy vấn chẩn đoán: liệt kê chính xác những yêu cầu bị thiếu

Trước khi dùng phủ định bên ngoài, bạn có thể xem trực tiếp danh sách **ứng viên – kỹ năng bắt buộc đang thiếu**. Đây là bước giúp hiểu hai tầng `NOT EXISTS`.

```sql
SELECT
    c.candidate_id,
    c.full_name,
    r.skill_id,
    r.skill_name AS missing_skill
FROM lesson199_candidates AS c
CROSS JOIN lesson199_skills AS r
WHERE r.is_required = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM lesson199_candidate_skills AS cs
      WHERE cs.candidate_id = c.candidate_id
        AND cs.skill_id = r.skill_id
        AND cs.is_verified = TRUE
  )
ORDER BY c.candidate_id, r.skill_id;
```

Kết quả dự kiến:

| Ứng viên | Kỹ năng bị thiếu |
|---|---|
| Bình | Git |
| Dũng | SQL |
| Dũng | Java |
| Dũng | Git |
| Hà | Git |

An, Chi và Lan **không xuất hiện** trong danh sách thiếu kỹ năng.

`CROSS JOIN` ở đây tạo các cặp **ứng viên × kỹ năng** để kiểm tra từng yêu cầu. Trên dữ liệu nhỏ dùng để học, đây là cách nhìn trực quan. Với số lượng ứng viên/kỹ năng lớn, không nhất thiết phải xây dựng toàn bộ tích Descartes để trả kết quả sản xuất; truy vấn hai tầng `NOT EXISTS` có thể để bộ tối ưu hóa chọn chiến lược kiểm tra phù hợp.

### 6.1. Cùng ý tưởng, dùng LEFT JOIN để tìm cặp thiếu

```sql
SELECT
    c.candidate_id,
    c.full_name,
    r.skill_name AS missing_skill
FROM lesson199_candidates AS c
CROSS JOIN lesson199_skills AS r
LEFT JOIN lesson199_candidate_skills AS cs
    ON cs.candidate_id = c.candidate_id
   AND cs.skill_id = r.skill_id
   AND cs.is_verified = TRUE
WHERE r.is_required = TRUE
  AND cs.candidate_id IS NULL
ORDER BY c.candidate_id, r.skill_id;
```

Điều kiện `cs.is_verified = TRUE` nằm trong `ON` để chỉ một dòng xác minh **hợp lệ** mới được coi là khớp. Nếu Hà có Git nhưng `is_verified = FALSE`, `LEFT JOIN` không nhận đó là cặp hợp lệ, rồi `cs.candidate_id IS NULL` phát hiện kỹ năng bị thiếu.

Ở đây `cs.candidate_id` là một phần khóa chính **NOT NULL**, nên kiểm tra `IS NULL` phân biệt được dòng **không khớp**. Trong các mô hình khác, hãy chọn cột phía phải chắc chắn không `NULL` khi có dòng khớp.

## 7. Bài toán “tất cả” có thể đúng khi tập yêu cầu rỗng

Đây là tình huống rất quan trọng.

Nếu tập kỹ năng bắt buộc **không có dòng nào**, liệu ứng viên có “đủ mọi kỹ năng bắt buộc” không?

Theo logic toán học thông thường:

\[
\forall r \in \varnothing,\;P(c,r)
\]

là **TRUE**. Đây gọi là **đúng một cách rỗng** (*vacuous truth*): không có phần tử bắt buộc nào để tạo phản ví dụ.

Với `NOT EXISTS` lồng nhau cũng vậy:

1. Truy vấn giữa xem các kỹ năng `r` bắt buộc: **không có dòng nào**.
2. `NOT EXISTS (truy vấn giữa)` là TRUE cho **mọi ứng viên**.
3. Vì vậy **cả sáu ứng viên** được chọn, kể cả Dũng.

### 7.1. Tự chạy ví dụ tập yêu cầu rỗng mà không sửa dữ liệu gốc

```sql
WITH required_skills AS (
    SELECT skill_id
    FROM lesson199_skills
    WHERE is_required = TRUE
      AND 1 = 0                 -- Tạo tập rỗng để minh họa.
)
SELECT
    c.candidate_id,
    c.full_name
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM required_skills AS r
    WHERE NOT EXISTS (
        SELECT 1
        FROM lesson199_candidate_skills AS cs
        WHERE cs.candidate_id = c.candidate_id
          AND cs.skill_id = r.skill_id
          AND cs.is_verified = TRUE
    )
)
ORDER BY c.candidate_id;
```

Kết quả là **An, Bình, Chi, Dũng, Hà, Lan**.

Điều này **đúng theo biểu thức “mọi phần tử trong tập rỗng”**, nhưng có thể **không đúng quy tắc nghiệp vụ** nếu một chương trình tuyển dụng không được phép có danh sách kỹ năng bắt buộc rỗng.

### 7.2. Khi nghiệp vụ yêu cầu tập bắt buộc phải không rỗng

Thêm `EXISTS` để kiểm tra tập yêu cầu có ít nhất một dòng:

```sql
WITH required_skills AS (
    SELECT skill_id
    FROM lesson199_skills
    WHERE is_required = TRUE
      AND 1 = 0
)
SELECT
    c.candidate_id,
    c.full_name
FROM lesson199_candidates AS c
WHERE EXISTS (
    SELECT 1
    FROM required_skills
)
AND NOT EXISTS (
    SELECT 1
    FROM required_skills AS r
    WHERE NOT EXISTS (
        SELECT 1
        FROM lesson199_candidate_skills AS cs
        WHERE cs.candidate_id = c.candidate_id
          AND cs.skill_id = r.skill_id
          AND cs.is_verified = TRUE
    )
);
```

Vì `required_skills` rỗng, kết quả bây giờ là **0 ứng viên**.

**Quyết định nghiệp vụ phải được xác định rõ:**

- Nếu không đặt yêu cầu nào thì mọi ứng viên mặc nhiên đạt, giữ nguyên `NOT EXISTS` kép.
- Nếu không đặt yêu cầu nào nghĩa là quy trình tuyển dụng **chưa được cấu hình hợp lệ**, thêm điều kiện tập yêu cầu **không rỗng**, hoặc tốt hơn là kiểm tra cấu hình ở bước xử lý nghiệp vụ.

### 7.3. Tập ứng viên rỗng thì sao?

Nếu bảng `lesson199_candidates` không có dòng nào, câu truy vấn cuối cũng không có ứng viên, kể cả khi tập yêu cầu rỗng. `NOT EXISTS` không “tạo ra” ứng viên: nó chỉ lọc những dòng **đã tồn tại** ở bảng ngoài.

## 8. ALL required khác với EXACTLY required

Hãy phân biệt hai yêu cầu:

1. **Có đủ mọi kỹ năng bắt buộc**: có thể có thêm kỹ năng ngoài danh sách yêu cầu.
2. **Có đúng và chỉ những kỹ năng bắt buộc**: vừa không thiếu kỹ năng bắt buộc, vừa không có kỹ năng hợp lệ nào ngoài tập bắt buộc.

Bài toán chính là loại **(1)**. Theo dữ liệu mẫu, An có Docker hợp lệ nhưng vẫn đáp ứng **tất cả yêu cầu**.

Muốn diễn đạt loại **(2)**, cần thêm một điều kiện phủ định đối xứng:

- Không thiếu kỹ năng bắt buộc.
- Không có kỹ năng đã xác minh nào **không thuộc tập bắt buộc**.

Ví dụ PostgreSQL:

```sql
SELECT
    c.candidate_id,
    c.full_name
FROM lesson199_candidates AS c
WHERE
    -- (A) Không thiếu bất kỳ kỹ năng bắt buộc nào.
    NOT EXISTS (
        SELECT 1
        FROM lesson199_skills AS r
        WHERE r.is_required = TRUE
          AND NOT EXISTS (
              SELECT 1
              FROM lesson199_candidate_skills AS cs
              WHERE cs.candidate_id = c.candidate_id
                AND cs.skill_id = r.skill_id
                AND cs.is_verified = TRUE
          )
    )
    AND
    -- (B) Không có kỹ năng đã xác minh nằm ngoài tập bắt buộc.
    NOT EXISTS (
        SELECT 1
        FROM lesson199_candidate_skills AS cs
        WHERE cs.candidate_id = c.candidate_id
          AND cs.is_verified = TRUE
          AND NOT EXISTS (
              SELECT 1
              FROM lesson199_skills AS r
              WHERE r.skill_id = cs.skill_id
                AND r.is_required = TRUE
          )
    )
ORDER BY c.candidate_id;
```

Kết quả với dữ liệu mẫu là **Chi và Lan**:

- **An** bị loại vì có Docker **đã xác minh**, là kỹ năng ngoài tập bắt buộc.
- **Chi** có đúng ba kỹ năng bắt buộc đã xác minh.
- **Lan** có Docker ở bảng quan hệ nhưng `is_verified = FALSE`, nên **không được tính** là kỹ năng đã xác minh ngoài tập bắt buộc.

Đây là ví dụ **bằng nhau của hai tập hợp kỹ năng hợp lệ**, còn điều kiện “có tất cả” chỉ là **bao hàm tập**.

Không thêm điều kiện loại kỹ năng tùy chọn nếu bài toán chỉ hỏi “đã đạt đủ mọi yêu cầu” — làm vậy sẽ loại oan những ứng viên có năng lực bổ sung.

## 9. Một tầng NOT EXISTS hay hai tầng NOT EXISTS?

Không phải câu hỏi có chữ **“mọi”** nào cũng cần đúng hai `NOT EXISTS`.

### 9.1. Khi đã có các dòng cần kiểm tra: một tầng là đủ

Giả sử hệ thống có bảng `tasks(task_id, team_id, status)`, cần tìm nhóm mà **tất cả công việc đang được giao đều hoàn tất**. Mỗi dòng `tasks` đã chính là một phần tử cần kiểm tra. Ta tìm **công việc chưa hoàn tất**:

```sql
-- Ví dụ thiết kế; giả định có teams(team_id) và
-- tasks(task_id, team_id, status).
SELECT
    t.team_id
FROM teams AS t
WHERE NOT EXISTS (
    SELECT 1
    FROM tasks AS x
    WHERE x.team_id = t.team_id
      AND (
          x.status <> 'DONE'
          OR x.status IS NULL
      )
);
```

Một `NOT EXISTS` là đủ: nó nói “**không có nhiệm vụ nào đang không hoàn tất**”.

Lưu ý nhóm **không có công việc** cũng thỏa điều kiện này theo logic tập rỗng. Nếu cần nhóm có ít nhất một nhiệm vụ, thêm `EXISTS (SELECT 1 FROM tasks ... )`.

### 9.2. Khi phải tìm chứng cứ ghép với từng yêu cầu: hai tầng tự nhiên hơn

Với “mọi kỹ năng bắt buộc đều phải có chứng nhận”, mỗi phần tử yêu cầu `r` cần một phép kiểm tra **có tồn tại bản ghi đối ứng** `cs`. Do đó ngôn ngữ logic có cấu trúc:

```text
KHÔNG TỒN TẠI kỹ năng bắt buộc r
    MÀ KHÔNG TỒN TẠI chứng nhận hợp lệ cs tương ứng.
```

Hai tầng `NOT EXISTS` giúp bám sát chính xác cấu trúc này.

**Số tầng phủ định không phải công thức máy móc đếm số chữ “mọi”**. Hãy hỏi:

- Tập phần tử cần kiểm tra có sẵn từng dòng không?
- “Đáp ứng” có được biểu diễn bằng một **dòng khác phải tồn tại** không?
- Phản ví dụ cụ thể mà bạn cần loại bỏ là gì?

## 10. Truy vấn con tương quan và phạm vi bí danh

Cấu trúc hai tầng `NOT EXISTS` dùng **ba bí danh ở ba cấp**:

```sql
SELECT c.candidate_id
FROM lesson199_candidates AS c          -- Tầng 0: ứng viên.
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson199_skills AS r          -- Tầng 1: kỹ năng yêu cầu.
    WHERE r.is_required = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM lesson199_candidate_skills AS cs -- Tầng 2: chứng nhận.
          WHERE cs.candidate_id = c.candidate_id
            AND cs.skill_id = r.skill_id
            AND cs.is_verified = TRUE
      )
);
```

Trong truy vấn con sâu nhất:

- `cs` là dòng của bảng `lesson199_candidate_skills` hiện đang xét.
- `r` đến từ **truy vấn con cha**, đang đại diện cho một kỹ năng bắt buộc.
- `c` đến từ **truy vấn ngoài cùng**, đang đại diện cho một ứng viên.

SQL cho phép truy vấn con **tham chiếu đến cột thuộc phạm vi truy vấn bên ngoài**. Đây là nền tảng của **correlated subquery**.

### 10.1. Thiếu điều kiện tương quan ứng viên

Một lỗi nguy hiểm:

```sql
-- SAI: quên ràng buộc với ứng viên c.
SELECT c.candidate_id, c.full_name
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson199_skills AS r
    WHERE r.is_required = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM lesson199_candidate_skills AS cs
          WHERE cs.skill_id = r.skill_id
            AND cs.is_verified = TRUE
      )
);
```

Điều kiện `cs.candidate_id = c.candidate_id` đã bị bỏ. Lúc này truy vấn chỉ hỏi:

> “Mỗi kỹ năng bắt buộc có **ai đó trong hệ thống** đã được xác minh không?”

Vì trong dữ liệu mẫu có người biết SQL, Java và Git, truy vấn sai này có thể chọn **cả sáu ứng viên**, kể cả Dũng. Nó không xác minh **mỗi ứng viên** đáp ứng mọi kỹ năng.

### 10.2. Thiếu điều kiện tương quan kỹ năng

Một lỗi khác:

```sql
-- SAI: quên ràng buộc kỹ năng đang xét.
SELECT c.candidate_id, c.full_name
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson199_skills AS r
    WHERE r.is_required = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM lesson199_candidate_skills AS cs
          WHERE cs.candidate_id = c.candidate_id
            AND cs.is_verified = TRUE
      )
);
```

Điều kiện `cs.skill_id = r.skill_id` bị bỏ. Vì thế, chỉ cần ứng viên có **một kỹ năng bất kỳ đã xác minh**, truy vấn trong có thể trả dòng cho **mọi kỹ năng yêu cầu**, khiến nhiều ứng viên thiếu kỹ năng vẫn được nhận.

Hai điều kiện tương quan quan trọng nhất là:

```sql
cs.candidate_id = c.candidate_id
AND cs.skill_id = r.skill_id
```

Với khóa ghép hoặc yêu cầu theo **phòng ban, chương trình đào tạo, thời kỳ**, còn cần thêm các điều kiện phân biệt phạm vi phù hợp.

## 11. Dùng NOT IN hoặc phép khác để thay thế có an toàn không?

### 11.1. Bẫy NULL với NOT IN

Một người có thể cố viết “mã kỹ năng không thuộc những kỹ năng đã có” bằng `NOT IN`. Tuy nhiên, `NOT IN` có thể tạo kết quả bất ngờ khi truy vấn con trả **`NULL`**.

Ví dụ độc lập:

```sql
SELECT
    30 NOT IN (10, 20) AS without_null,
    30 NOT IN (10, 20, NULL) AS with_null;
```

Trong PostgreSQL:

- `30 NOT IN (10, 20)` là `TRUE`.
- `30 NOT IN (10, 20, NULL)` là **`NULL`/UNKNOWN**, không phải `TRUE`.

Trong `WHERE`, UNKNOWN bị loại giống FALSE. Vì vậy, chỉ một `NULL` không mong muốn trong tập so sánh có thể khiến kết quả “không thuộc tập” không như mong đợi.

Bài thực hành dùng `skill_id` khóa chính `NOT NULL` ở bảng yêu cầu và khóa ngoại không `NULL` ở bảng quan hệ nên ví dụ `NOT IN` có thể tránh rủi ro cụ thể này. Tuy nhiên, với nguồn dữ liệu tổng quát, **`NOT EXISTS` với điều kiện tương quan rõ ràng thường diễn đạt thiếu quan hệ an toàn và dễ hiểu hơn**.

### 11.2. Phép khác (`<>`) không phải kiểm tra “thiếu”

Sai lầm khác:

```sql
-- Không đúng ý nghĩa tìm kỹ năng r bị thiếu.
WHERE cs.skill_id <> r.skill_id
```

Nếu ứng viên có SQL và đang xét Git, `SQL <> Git` là TRUE. Nhưng điều đó **không chứng minh** ứng viên thiếu Git: ứng viên có thể đồng thời có Git ở một dòng khác.

Để xác định thiếu một quan hệ, cần kiểm tra **không tồn tại dòng khớp**, không phải tồn tại một dòng **không khớp**.

Đó chính là lý do `NOT EXISTS (... WHERE cs.skill_id = r.skill_id ...)` phù hợp.

## 12. Dữ liệu trùng và vai trò của EXISTS

`EXISTS` chỉ quan tâm truy vấn con có **ít nhất một dòng**:

- Không có dòng → FALSE.
- Một dòng → TRUE.
- Mười dòng → vẫn TRUE.

Do đó, nếu hệ thống lưu lịch sử chứng nhận và một ứng viên có nhiều bản ghi hợp lệ cho cùng kỹ năng, `NOT EXISTS` bên trong vẫn xác định đúng việc **có ít nhất một chứng cứ hợp lệ**.

Ví dụ một cấu trúc lịch sử giả định:

```sql
-- Giả định verification_history có nhiều dòng mỗi cặp.
SELECT
    c.candidate_id,
    c.full_name
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson199_skills AS r
    WHERE r.is_required = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM verification_history AS h
          WHERE h.candidate_id = c.candidate_id
            AND h.skill_id = r.skill_id
            AND h.verification_status = 'PASSED'
      )
);
```

Nếu ứng viên có hai lần `PASSED` cho cùng kỹ năng, `EXISTS` vẫn là TRUE. Không cần `DISTINCT` để biểu diễn “có ít nhất một”.

Ngược lại, nếu bạn dùng phương pháp đếm số bản ghi, cần đề phòng nhiều lần chứng nhận cho cùng kỹ năng làm `COUNT(*)` lớn hơn số kỹ năng **khác nhau** đã đạt.

### 12.1. Trùng trong chính tập yêu cầu

Nếu tập bắt buộc được tạo từ một truy vấn có thể trả **cùng kỹ năng nhiều lần**, double `NOT EXISTS` vẫn diễn đạt đúng **từng dòng yêu cầu không thiếu**; trùng cùng một kỹ năng không đổi việc có tồn tại chứng nhận phù hợp hay không.

Tuy nhiên, các truy vấn thay bằng `COUNT(*)` cần chuẩn hóa **tập yêu cầu duy nhất**, nếu không số yêu cầu bị đếm hai lần.

Trong cơ sở dữ liệu học tập, `lesson199_skills.skill_id` là khóa chính nên không có hai dòng cùng mã kỹ năng trong bảng gốc. Nhưng một `JOIN` xây tập yêu cầu từ các bảng khác vẫn có thể tạo các dòng lặp.

## 13. So sánh với GROUP BY và HAVING COUNT(DISTINCT)

Một cách khác để kiểm tra “đạt đủ mọi kỹ năng bắt buộc” là **đếm số kỹ năng bắt buộc**, rồi **đếm số kỹ năng bắt buộc khác nhau mà ứng viên đã xác minh**, yêu cầu hai số bằng nhau.

Ví dụ:

```sql
WITH required_skills AS (
    SELECT skill_id
    FROM lesson199_skills
    WHERE is_required = TRUE
),
required_count AS (
    SELECT COUNT(*) AS required_total
    FROM required_skills
)
SELECT
    c.candidate_id,
    c.full_name
FROM lesson199_candidates AS c
CROSS JOIN required_count AS rc
LEFT JOIN lesson199_candidate_skills AS cs
    ON cs.candidate_id = c.candidate_id
   AND cs.is_verified = TRUE
   AND cs.skill_id IN (
       SELECT skill_id
       FROM required_skills
   )
GROUP BY
    c.candidate_id,
    c.full_name,
    rc.required_total
HAVING COUNT(DISTINCT cs.skill_id) = rc.required_total
ORDER BY c.candidate_id;
```

Với bộ dữ liệu mẫu, kết quả cũng là **An, Chi, Lan**.

### 13.1. Vì sao phải đếm DISTINCT?

Nếu mỗi kỹ năng có thể có **nhiều chứng nhận**, thì `COUNT(*)` hoặc `COUNT(cs.skill_id)` đếm **số dòng chứng nhận**, không phải số kỹ năng yêu cầu khác nhau đã hoàn thành.

Ví dụ ứng viên có:

| Kỹ năng | Số chứng nhận PASSED |
|---|---:|
| SQL | 2 |
| Java | 1 |
| Git | 0 |

Có **3 dòng PASSED** nhưng chỉ có **2 kỹ năng khác nhau được đáp ứng**. Nếu tập yêu cầu có 3 kỹ năng, điều kiện `COUNT(*) = 3` có thể nhận nhầm ứng viên. `COUNT(DISTINCT skill_id) = 2` phản ánh số kỹ năng khác nhau, tránh nhầm số dòng với số yêu cầu đạt.

Ở bảng thực hành, khóa chính ghép loại trùng trực tiếp; `DISTINCT` trong phiên bản tổng quát giúp giữ đúng cách hiểu khi nguồn dữ liệu thay đổi.

### 13.2. Phải lọc đúng tập yêu cầu trước khi đếm

Nếu quên giới hạn `cs.skill_id` chỉ thuộc tập bắt buộc, một ứng viên có **SQL, Java, Docker** có thể bị đếm là 3 kỹ năng và bị nhận nhầm là đủ **SQL, Java, Git**.

Hai tập cùng kích thước **không có nghĩa là cùng phần tử**. Điều kiện đếm chỉ hợp lệ khi:

1. Những phần tử được đếm đều thuộc **tập yêu cầu**.
2. Mỗi phần tử yêu cầu chỉ được đếm **một lần**.
3. Mọi phần tử thuộc tập yêu cầu được xác định đúng phạm vi.

`NOT EXISTS` lồng nhau thể hiện logic **kiểm tra từng yêu cầu** trực tiếp hơn và ít cần suy luận về hai phép đếm.

### 13.3. Trường hợp tập yêu cầu rỗng

Với CTE `required_skills` rỗng:

- `required_total = 0`.
- `LEFT JOIN` vẫn có một dòng cho mỗi ứng viên với `cs.skill_id NULL`.
- `COUNT(DISTINCT cs.skill_id) = 0`.

Vì vậy truy vấn `HAVING` ở trên cũng chọn **mọi ứng viên**, giống hành vi tập yêu cầu rỗng của double `NOT EXISTS`.

Nếu nghiệp vụ muốn tập bắt buộc phải không rỗng, thêm điều kiện `rc.required_total > 0` trong `HAVING` hoặc `WHERE` theo cách phù hợp.

### 13.4. Khi nào nên dùng COUNT/HAVING?

`GROUP BY/HAVING` có thể phù hợp khi cùng lúc cần xuất:

- Số kỹ năng bắt buộc.
- Số kỹ năng đã hoàn thành.
- Số kỹ năng còn thiếu.
- Tỷ lệ hoàn thành.

Nếu chỉ cần điều kiện **đã đáp ứng tất cả hay chưa**, double `NOT EXISTS` thường giúp mô tả logic rõ ràng mà không cần so sánh số đếm và tự phòng chống dòng trùng.

Không kết luận một cách luôn nhanh hơn cách kia. Bộ tối ưu hóa có thể đổi truy vấn con thành anti-join, chọn chỉ mục hoặc cách thực thi khác tùy dữ liệu và DBMS.

## 14. Dùng EXCEPT để biểu diễn hiệu hai tập

Trong PostgreSQL, toán tử tập hợp `EXCEPT` cho phép lấy các phần tử ở tập thứ nhất **không nằm trong** tập thứ hai.

Ý tưởng:

```text
Các kỹ năng bắt buộc
      EXCEPT
Các kỹ năng ứng viên đã xác minh
      =
Các kỹ năng còn thiếu
```

Nếu hiệu tập hợp là **rỗng**, ứng viên đã có đủ mọi yêu cầu:

```sql
SELECT
    c.candidate_id,
    c.full_name
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT r.skill_id
    FROM lesson199_skills AS r
    WHERE r.is_required = TRUE

    EXCEPT

    SELECT cs.skill_id
    FROM lesson199_candidate_skills AS cs
    WHERE cs.candidate_id = c.candidate_id
      AND cs.is_verified = TRUE
)
ORDER BY c.candidate_id;
```

Kết quả cũng là **An, Chi, Lan**.

`EXCEPT` (không ghi `ALL`) sử dụng ngữ nghĩa **tập hợp** để loại dòng trùng. Đây là cách nhìn gần với **phép chia quan hệ (relational division)** trong đại số quan hệ: tìm các đối tượng có quan hệ với **toàn bộ** phần tử của tập yêu cầu.

Lưu ý tính tương thích: PostgreSQL, SQL Server và SQLite hỗ trợ `EXCEPT`; Oracle thường dùng `MINUS` trong các phiên bản truyền thống (các phiên bản mới có thể có cú pháp mở rộng). Cú pháp tập hợp và hỗ trợ `EXCEPT` ở MySQL/MariaDB phụ thuộc phiên bản. Hai tầng `NOT EXISTS` thường là phương pháp dễ mang sang nhiều hệ quản trị hơn.

## 15. Phép chia quan hệ: vì sao bài toán này có tên riêng?

Trong đại số quan hệ, giả sử:

- `CandidateSkills(candidate_id, skill_id)` là quan hệ những kỹ năng đã đáp ứng.
- `RequiredSkills(skill_id)` là tập kỹ năng bắt buộc.

Yêu cầu:

> Tìm các `candidate_id` sao cho với **mọi `skill_id` thuộc `RequiredSkills`**, cặp `(candidate_id, skill_id)` đều thuộc quan hệ `CandidateSkills`.

Có thể xem đây là một phép **chia quan hệ**: một tập cặp `(ứng viên, kỹ năng)` được “chia” cho tập kỹ năng để lấy những ứng viên đáp ứng tất cả phần tử.

Biểu thức SQL double `NOT EXISTS` là một cách diễn đạt điều kiện của phép chia quan hệ mà **không cần SQL có toán tử DIVIDE chuyên dụng**.

### 15.1. Mô hình ba tập

```text
C = {An, Bình, Chi, Dũng, Hà, Lan}

R = {SQL, Java, Git}

Kỹ năng đã xác minh:
An   → {SQL, Java, Git, Docker}
Bình → {SQL, Java}
Chi  → {SQL, Java, Git}
Dũng → {}
Hà   → {SQL, Java}
Lan  → {SQL, Java, Git}

Tìm c mà R là tập con của kỹ năng đã xác minh của c:
→ {An, Chi, Lan}
```

Công thức tập hợp:

\[
R \subseteq Skills(c)
\iff
R \setminus Skills(c)=\varnothing.
\]

Ý tưởng `NOT EXISTS` kép và `EXCEPT` đều đi từ việc chứng minh **hiệu tập hợp rỗng**.

## 16. Yêu cầu phụ thuộc từng đối tượng: nhóm, lớp học hoặc thời kỳ

Trong ví dụ đầu, **mọi ứng viên dùng chung một tập yêu cầu**. Thực tế có thể khác:

- Vị trí Backend cần SQL, Java, Git.
- Vị trí Data Analyst cần SQL, Python.
- Khóa học A và B có các môn bắt buộc khác nhau.
- Quy định thay đổi theo năm hoặc phòng ban.

Khi đó, tập `R` phụ thuộc vào ứng viên `c`, chứ không phải danh sách chung cho tất cả.

### 16.1. Ví dụ bảng giả định theo vai trò

Giả sử có:

```text
candidates(candidate_id, role_id, full_name)
role_requirements(role_id, skill_id)
candidate_skills(candidate_id, skill_id, is_verified)
```

Yêu cầu là **ứng viên đáp ứng mọi kỹ năng bắt buộc của vai trò mà mình ứng tuyển**.

```sql
-- Ví dụ thiết kế; các bảng trong đoạn này là giả định,
-- không phải những bảng lesson199_... đã tạo ở trên.
SELECT
    c.candidate_id,
    c.full_name,
    c.role_id
FROM candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM role_requirements AS r
    WHERE r.role_id = c.role_id
      AND NOT EXISTS (
          SELECT 1
          FROM candidate_skills AS cs
          WHERE cs.candidate_id = c.candidate_id
            AND cs.skill_id = r.skill_id
            AND cs.is_verified = TRUE
      )
);
```

Điều kiện rất quan trọng là:

```sql
r.role_id = c.role_id
```

Nó bảo đảm ứng viên chỉ được đối chiếu với **tập yêu cầu của đúng vai trò**. Nếu quên, truy vấn sẽ có thể yêu cầu ứng viên đáp ứng **kỹ năng của mọi vai trò trên toàn hệ thống**.

### 16.2. Phạm vi theo thời gian

Giả sử chứng nhận chỉ hợp lệ nếu **chưa hết hạn**, và bảng quan hệ có cột `expires_on DATE` (mô hình giả định). Khi đó điều kiện đáp ứng cần bao gồm tính hợp lệ tại ngày đánh giá:

```sql
-- Ví dụ thiết kế có cột expires_on; không chạy trực tiếp
-- trên bảng lesson199_candidate_skills của phần 3.
WHERE cs.candidate_id = c.candidate_id
  AND cs.skill_id = r.skill_id
  AND cs.is_verified = TRUE
  AND (
       cs.expires_on IS NULL
       OR cs.expires_on >= DATE '2026-11-14'
  )
```

Nếu `expires_on` được quy ước là **ngày cuối cùng còn hiệu lực**, phép `>=` là phù hợp. Nếu được quy ước là **mốc kết thúc không bao gồm**, cần dùng `>`. Luôn xác định ranh giới nghiệp vụ.

Điểm mấu chốt: **toàn bộ điều kiện tạo nên “chứng nhận hợp lệ” phải nằm trong truy vấn chứng cứ bên trong**, nếu không một chứng nhận hết hạn vẫn có thể bị tính nhầm là đáp ứng.

## 17. “Mọi đơn đều có ít nhất một dòng chi tiết”: cùng khuôn mẫu

Một ví dụ khác không dùng tập kỹ năng, mà kiểm tra **tất cả các đơn hàng của từng khách hàng đều có ít nhất một dòng chi tiết**.

Giả sử tồn tại ba bảng:

```text
customers(customer_id, customer_name)
orders(order_id, customer_id)
order_items(item_id, order_id)
```

Yêu cầu logic:

- Với mỗi khách hàng `c`,
- **Không có đơn hàng `o` của khách hàng đó** mà
- **Không có bất kỳ dòng chi tiết `i` nào thuộc đơn `o`**.

SQL:

```sql
-- Ví dụ trên mô hình giả định; không dùng ba bảng lesson199_...
SELECT
    c.customer_id,
    c.customer_name
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND NOT EXISTS (
          SELECT 1
          FROM order_items AS i
          WHERE i.order_id = o.order_id
      )
);
```

Lưu ý **khách hàng không có đơn** cũng được chọn theo logic tập rỗng: không có đơn nào là phản ví dụ “đơn không có chi tiết”.

Nếu nghiệp vụ đòi hỏi khách hàng phải có **ít nhất một đơn** và mọi đơn đều có chi tiết:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND NOT EXISTS (
          SELECT 1
          FROM order_items AS i
          WHERE i.order_id = o.order_id
      )
);
```

Đây là ví dụ lý tưởng của hai yêu cầu **“có ít nhất một”** và **“tất cả đều đạt”** được kết hợp.

## 18. “Nhà cung cấp có mọi sản phẩm cần mua”: biến thể thông dụng

Giả sử có:

- `suppliers(supplier_id, supplier_name)`.
- `required_products(product_id)`.
- `supplier_products(supplier_id, product_id, is_available)`.

Yêu cầu: nhà cung cấp **có sẵn tất cả các sản phẩm trong danh sách cần mua**.

```sql
-- Ví dụ mô hình giả định, không tạo các bảng này trong bài.
SELECT
    s.supplier_id,
    s.supplier_name
FROM suppliers AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM required_products AS r
    WHERE NOT EXISTS (
        SELECT 1
        FROM supplier_products AS sp
        WHERE sp.supplier_id = s.supplier_id
          AND sp.product_id = r.product_id
          AND sp.is_available = TRUE
    )
);
```

Đổi tên đối tượng nhưng cấu trúc logic vẫn giữ nguyên:

```text
Không tồn tại sản phẩm bắt buộc r
    mà không tồn tại dòng hàng có sẵn (nhà cung cấp s, sản phẩm r).
```

Để xử lý điều kiện phức tạp hơn như đủ **số lượng đặt mua**, cần thay `sp.is_available` bằng điều kiện đủ số lượng tại đúng cấp sản phẩm, ví dụ `sp.available_quantity >= r.required_quantity`. Nếu một nhà cung cấp có nhiều kho hoặc nhiều dòng tồn kho trên cùng sản phẩm, có thể cần tổng hợp số lượng trước khi kiểm tra; một dòng `sp` riêng lẻ không nhất thiết đại diện cho tổng tồn có sẵn.

## 19. Hiệu năng và chỉ mục cho double NOT EXISTS

Hai truy vấn con lồng nhau **không có nghĩa chắc chắn DBMS thực thi từng vòng lặp tuần tự với chi phí cố định theo số tầng**. Bộ tối ưu hóa có thể chuyển một số truy vấn thành **anti-join**, sử dụng chỉ mục hoặc chọn một chiến lược khác.

Tuy nhiên, các quan hệ tương quan sau là điểm quan trọng:

```sql
cs.candidate_id = c.candidate_id
AND cs.skill_id = r.skill_id
```

Bảng thực hành đã khai báo:

```sql
PRIMARY KEY (candidate_id, skill_id)
```

Trong PostgreSQL, khóa chính tạo chỉ mục duy nhất phù hợp cho phép tìm kiếm một **cặp ứng viên–kỹ năng**, rất hữu ích cho truy vấn chứng cứ bên trong.

Tùy số lượng kỹ năng và tỷ lệ bắt buộc, có thể cân nhắc chỉ mục hỗ trợ lọc `is_required`. Ví dụ trong PostgreSQL:

```sql
-- Cân nhắc khi bảng skills lớn và truy vấn thường lấy required.
CREATE INDEX lesson199_required_skills_idx
    ON lesson199_skills (skill_id)
    WHERE is_required = TRUE;
```

Đây là **partial index**, cú pháp đặc thù PostgreSQL. Với bảng chỉ có 4 kỹ năng trong ví dụ, tạo chỉ mục này không có ý nghĩa về tốc độ; DBMS có thể quét toàn bảng nhanh hơn.

### 19.1. EXPLAIN để xem kế hoạch

```sql
EXPLAIN
SELECT c.candidate_id
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson199_skills AS r
    WHERE r.is_required = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM lesson199_candidate_skills AS cs
          WHERE cs.candidate_id = c.candidate_id
            AND cs.skill_id = r.skill_id
            AND cs.is_verified = TRUE
      )
);
```

`EXPLAIN` cho biết kế hoạch dự kiến. Nếu dùng `EXPLAIN ANALYZE`, DBMS **thực thi câu truy vấn** để đo thời gian; chỉ chạy trong môi trường phù hợp. Không suy luận rằng truy vấn có hai tầng `NOT EXISTS` luôn chậm hơn `GROUP BY/HAVING` chỉ dựa vào việc nhìn cấu trúc cú pháp.

### 19.2. Thu hẹp tập yêu cầu trước khi kiểm tra

Nếu có hàng nghìn kỹ năng nhưng vai trò chỉ yêu cầu ba kỹ năng, hãy giới hạn tập `r` theo **vai trò, chương trình, thời gian hiệu lực, trạng thái bắt buộc** trước khi kiểm tra sự thiếu.

Một điều kiện thiếu trong truy vấn giữa không chỉ làm sai hiệu năng mà có thể **thay đổi toàn bộ ý nghĩa câu hỏi**, ví dụ yêu cầu ứng viên biết mọi kỹ năng có trong cơ sở dữ liệu, kể cả kỹ năng không liên quan.

## 20. Khác biệt DBMS và lưu ý SQL ba giá trị

### 20.1. EXISTS và NOT EXISTS là cấu trúc SQL phổ biến

`EXISTS (subquery)` và `NOT EXISTS (subquery)` có mặt trong PostgreSQL, MySQL/MariaDB, SQL Server, Oracle Database, SQLite và nhiều DBMS khác. Chúng dựa trên nguyên tắc **truy vấn con có trả dòng nào không**.

Khi dùng `SELECT 1` bên trong, số `1` **không phải giá trị đang đem so sánh**. Dòng `SELECT 1` chỉ tạo một dòng có giá trị tùy ý; `EXISTS` quan tâm **có dòng hay không**, không quan tâm giá trị trong cột được chọn.

```sql
-- Cả hai cùng kiểm tra có tồn tại ít nhất một dòng khớp.
EXISTS (SELECT 1 FROM lesson199_candidate_skills AS cs WHERE ...)
EXISTS (SELECT cs.skill_id FROM lesson199_candidate_skills AS cs WHERE ...)
```

Việc chọn `1` thường giúp người đọc nhận ra rằng phần dữ liệu cụ thể không được sử dụng.

### 20.2. Kiểu BOOLEAN có thể khác giữa các hệ

Các ví dụ PostgreSQL dùng:

```sql
WHERE r.is_required = TRUE
  AND cs.is_verified = TRUE
```

Trong SQL Server, nhiều hệ thống dùng `BIT` và so với `1` thay vì biểu thức boolean như PostgreSQL. Với MySQL hoặc SQLite, cách lưu cờ thường tương thích với biểu diễn số `0`/`1` theo schema. Khi chuyển bài sang DBMS khác, thay điều kiện cờ theo **kiểu cột thực tế**, còn cấu trúc `NOT EXISTS` lồng nhau vẫn giữ ý nghĩa.

### 20.3. EXISTS không bị “NULL phá hỏng” như NOT IN

`EXISTS` trả TRUE nếu truy vấn con có dòng, **ngay cả khi cột được chọn trên dòng đó là `NULL`**. Trong mẫu trên, chứng cứ khớp được xác định bởi `WHERE`; một dòng có `NULL` ở cột khác không tự khiến `EXISTS` thành UNKNOWN.

Ngược lại, `NOT IN` có thể trả UNKNOWN khi tập so sánh chứa `NULL`. Vì vậy với bài toán tìm **thiếu quan hệ theo khóa**, `NOT EXISTS` là cách biểu đạt vững vàng hơn.

### 20.4. Truy vấn con tương quan là cơ chế logic, không phải bảo đảm cách chạy vật lý

Từ “tương quan” chỉ việc truy vấn con **tham chiếu cột ở truy vấn ngoài**. Không có nghĩa SQL bắt buộc chạy từng truy vấn con đầy đủ lại cho mỗi dòng theo thứ tự cố định. Hệ quản trị được phép tối ưu miễn giữ kết quả ngữ nghĩa.

## 21. Những lỗi thường gặp và cách sửa

### Lỗi 1: Chỉ dùng EXISTS nên nhận cả người thiếu yêu cầu

```sql
-- Chỉ chứng minh có ít nhất một kỹ năng bắt buộc đã xác minh.
WHERE EXISTS (
    SELECT 1
    FROM lesson199_skills AS r
    JOIN lesson199_candidate_skills AS cs
        ON cs.skill_id = r.skill_id
    WHERE cs.candidate_id = c.candidate_id
      AND r.is_required = TRUE
      AND cs.is_verified = TRUE
)
```

Với dữ liệu mẫu, Bình và Hà vẫn được chọn vì có SQL/Java. Muốn **đủ mọi** kỹ năng, dùng `NOT EXISTS (yêu cầu thiếu)`.

### Lỗi 2: Quên một trong hai khóa tương quan

Thiếu `cs.candidate_id = c.candidate_id` làm kiểm tra **toàn hệ thống có người biết kỹ năng**. Thiếu `cs.skill_id = r.skill_id` làm kiểm tra ứng viên **có một kỹ năng bất kỳ**, không phải kỹ năng đang được yêu cầu.

### Lỗi 3: Không lọc đúng tập bắt buộc

```sql
-- Nguy cơ sai: yêu cầu mọi kỹ năng, kể cả Docker tùy chọn.
FROM lesson199_skills AS r
WHERE NOT EXISTS (...)
```

Phải thêm:

```sql
WHERE r.is_required = TRUE
  AND NOT EXISTS (...)
```

Hoặc lọc qua bảng yêu cầu đúng vai trò/chương trình.

### Lỗi 4: Có dòng nhưng chưa hợp lệ vẫn được tính

Nếu bỏ `cs.is_verified = TRUE`, Hà được coi là có Git vì bảng quan hệ có dòng Git, dù chưa xác minh. **Điều kiện chứng nhận hợp lệ** phải nằm trong truy vấn trong cùng với hai khóa khớp.

### Lỗi 5: Tưởng tập yêu cầu rỗng khiến mọi người không đạt

Theo logic toàn thể, **tập yêu cầu rỗng khiến mọi ứng viên trong bảng ngoài đạt**. Nếu nghiệp vụ không muốn như vậy, kiểm tra tập yêu cầu có ít nhất một dòng.

### Lỗi 6: So sánh số lượng mà không kiểm tra đúng phần tử

Có ba kỹ năng bất kỳ không đồng nghĩa đã có đúng SQL, Java, Git. Khi dùng `COUNT`, phải chỉ đếm các kỹ năng **nằm trong tập yêu cầu** và dùng `DISTINCT` nếu một kỹ năng có thể xuất hiện nhiều lần.

### Lỗi 7: Dùng NOT IN mà không xét NULL

`NOT IN` có thể trả UNKNOWN khi tập so sánh chứa `NULL`. Dùng `NOT EXISTS` với điều kiện tương quan để biểu đạt thiếu bản ghi; vẫn phải đảm bảo các khóa và các phép so sánh có ngữ nghĩa đúng.

### Lỗi 8: Cố dùng điều kiện <> để chứng minh vắng mặt

Sự tồn tại một kỹ năng **khác** Git không chứng minh **không có Git**. Phải kiểm tra **không tồn tại dòng có `skill_id = Git`**.

### Lỗi 9: Nhầm “có tất cả” với “chỉ có đúng tập”

An có cả ba kỹ năng bắt buộc **và Docker thêm** nên vẫn đạt “có tất cả”. Chỉ loại An nếu bài toán yêu cầu tập kỹ năng hợp lệ phải **bằng đúng** tập bắt buộc, với điều kiện phủ định bổ sung.

### Lỗi 10: Dùng INNER JOIN làm mất người không có dữ liệu trước khi kiểm tra ALL

Nếu bắt đầu từ một `INNER JOIN` giữa ứng viên và kỹ năng, ứng viên không có kỹ năng như Dũng có thể bị loại từ đầu. Trong tập yêu cầu **không rỗng**, Dũng vẫn không đạt — nhưng với tập yêu cầu **rỗng**, việc loại từ đầu sẽ làm sai logic “mọi phần tử” vì Dũng phải đạt theo quy tắc vacuous truth.

Hãy bắt đầu từ **tập thực thể cần đánh giá**, rồi dùng điều kiện lượng từ để lọc, không vô tình thu hẹp tập ứng viên bằng một JOIN khác trước khi kiểm tra.

### Lỗi 11: Giả định thêm DISTINCT ngoài SELECT sửa được logic sai

`SELECT DISTINCT` chỉ loại các dòng kết quả trùng nhau. Nó **không sửa** điều kiện tương quan thiếu, tập yêu cầu sai, chứng nhận chưa hợp lệ hoặc sự khác biệt giữa “ít nhất một” và “tất cả”.

## 22. Bài tập thực hành có lời giải

Các bài 1–8 sử dụng ba bảng `lesson199_...` ở phần 3. Một số bài dùng CTE độc lập hoặc mô hình bảng giả định như đã ghi chú.

### Bài 1. Dự đoán kết quả của double NOT EXISTS

Chạy:

```sql
SELECT c.candidate_id, c.full_name
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson199_skills AS r
    WHERE r.is_required = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM lesson199_candidate_skills AS cs
          WHERE cs.candidate_id = c.candidate_id
            AND cs.skill_id = r.skill_id
            AND cs.is_verified = TRUE
      )
)
ORDER BY c.candidate_id;
```

**Đáp án:** **An, Chi, Lan**. Đây là ba người có SQL, Java, Git đều được xác minh.

### Bài 2. Tìm ứng viên có ít nhất một kỹ năng bắt buộc

```sql
SELECT
    c.candidate_id,
    c.full_name
FROM lesson199_candidates AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson199_skills AS r
    JOIN lesson199_candidate_skills AS cs
        ON cs.skill_id = r.skill_id
    WHERE cs.candidate_id = c.candidate_id
      AND r.is_required = TRUE
      AND cs.is_verified = TRUE
)
ORDER BY c.candidate_id;
```

**Đáp án:** **An, Bình, Chi, Hà, Lan**; Dũng không có kỹ năng nào nên không đạt.

So sánh với bài 1: **có một** yếu hơn **có tất cả**.

### Bài 3. Tìm ứng viên không có kỹ năng bắt buộc được xác minh nào

```sql
SELECT
    c.candidate_id,
    c.full_name
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson199_skills AS r
    JOIN lesson199_candidate_skills AS cs
        ON cs.skill_id = r.skill_id
    WHERE cs.candidate_id = c.candidate_id
      AND r.is_required = TRUE
      AND cs.is_verified = TRUE
)
ORDER BY c.candidate_id;
```

**Đáp án:** **Dũng**.

Truy vấn này **khác** bài 1: nó hỏi **không có bất kỳ kỹ năng bắt buộc được xác minh**, không hỏi có **đầy đủ mọi kỹ năng bắt buộc**.

### Bài 4. Liệt kê những cặp ứng viên – kỹ năng còn thiếu

```sql
SELECT
    c.full_name,
    r.skill_name AS missing_skill
FROM lesson199_candidates AS c
CROSS JOIN lesson199_skills AS r
WHERE r.is_required = TRUE
  AND NOT EXISTS (
      SELECT 1
      FROM lesson199_candidate_skills AS cs
      WHERE cs.candidate_id = c.candidate_id
        AND cs.skill_id = r.skill_id
        AND cs.is_verified = TRUE
  )
ORDER BY c.candidate_id, r.skill_id;
```

**Đáp án:** **Bình–Git**, **Dũng–SQL**, **Dũng–Java**, **Dũng–Git**, **Hà–Git**. Truy vấn trả 5 cặp còn thiếu.

### Bài 5. Nếu chỉ cần SQL và Java thì ai đạt?

Không sửa cờ `is_required` trong bảng, chỉ tạo tập yêu cầu con bằng CTE:

```sql
WITH required_skills AS (
    SELECT skill_id
    FROM lesson199_skills
    WHERE skill_id IN (10, 20)
)
SELECT
    c.candidate_id,
    c.full_name
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM required_skills AS r
    WHERE NOT EXISTS (
        SELECT 1
        FROM lesson199_candidate_skills AS cs
        WHERE cs.candidate_id = c.candidate_id
          AND cs.skill_id = r.skill_id
          AND cs.is_verified = TRUE
    )
)
ORDER BY c.candidate_id;
```

**Đáp án:** **An, Bình, Chi, Hà, Lan**. Dũng vẫn không đạt. Hà không có Git đã xác minh nhưng Git **không nằm trong tập yêu cầu của bài này**.

### Bài 6. Tập yêu cầu rỗng trả bao nhiêu người?

```sql
WITH required_skills AS (
    SELECT skill_id
    FROM lesson199_skills
    WHERE is_required = TRUE
      AND 1 = 0
)
SELECT COUNT(*) AS qualified_candidates
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM required_skills AS r
    WHERE NOT EXISTS (
        SELECT 1
        FROM lesson199_candidate_skills AS cs
        WHERE cs.candidate_id = c.candidate_id
          AND cs.skill_id = r.skill_id
          AND cs.is_verified = TRUE
    )
);
```

**Đáp án:** **6**. Không tồn tại bất kỳ yêu cầu nào bị thiếu nên mọi ứng viên đạt theo logic tập rỗng. Nếu nghiệp vụ bắt buộc tập yêu cầu không rỗng, thêm `EXISTS (SELECT 1 FROM required_skills)`.

### Bài 7. Tìm những người có “đúng và chỉ” kỹ năng bắt buộc đã xác minh

**Yêu cầu:** phải có SQL, Java, Git và **không có kỹ năng đã xác minh nào ngoài tập yêu cầu**.

Một lời giải là ghép hai điều kiện `NOT EXISTS`:

```sql
SELECT c.candidate_id, c.full_name
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson199_skills AS r
    WHERE r.is_required = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM lesson199_candidate_skills AS cs
          WHERE cs.candidate_id = c.candidate_id
            AND cs.skill_id = r.skill_id
            AND cs.is_verified = TRUE
      )
)
AND NOT EXISTS (
    SELECT 1
    FROM lesson199_candidate_skills AS cs
    WHERE cs.candidate_id = c.candidate_id
      AND cs.is_verified = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM lesson199_skills AS r
          WHERE r.skill_id = cs.skill_id
            AND r.is_required = TRUE
      )
)
ORDER BY c.candidate_id;
```

**Đáp án:** **Chi, Lan**. An bị loại vì Docker đã được xác minh nhưng không bắt buộc. Lan có dòng Docker nhưng chưa xác minh nên không được tính là kỹ năng hợp lệ ngoài yêu cầu.

### Bài 8. Phát hiện lỗi thiếu tương quan

Câu truy vấn sau có vấn đề gì?

```sql
SELECT c.candidate_id, c.full_name
FROM lesson199_candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson199_skills AS r
    WHERE r.is_required = TRUE
      AND NOT EXISTS (
          SELECT 1
          FROM lesson199_candidate_skills AS cs
          WHERE cs.skill_id = r.skill_id
            AND cs.is_verified = TRUE
      )
);
```

**Đáp án:** thiếu `cs.candidate_id = c.candidate_id`. Vì truy vấn con chỉ yêu cầu **ai đó** có từng kỹ năng, nó có thể nhận cả người không có kỹ năng. Cách sửa: thêm điều kiện tương quan ứng viên vào truy vấn sâu nhất.

### Bài 9. Khách hàng có mọi đơn đều có chi tiết

Giả định có bảng `customers`, `orders` và `order_items` như phần 17. Viết truy vấn chọn khách hàng **có ít nhất một đơn, đồng thời mọi đơn đều có ít nhất một chi tiết**.

```sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
AND NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND NOT EXISTS (
          SELECT 1
          FROM order_items AS i
          WHERE i.order_id = o.order_id
      )
);
```

**Giải thích:** `EXISTS` đầu loại khách không có đơn; double `NOT EXISTS` bảo đảm không tồn tại đơn thiếu chi tiết. Hai điều kiện phối hợp để xử lý đúng cả trường hợp tập đơn hàng rỗng.

### Bài 10. So sánh NOT EXISTS và HAVING

Yêu cầu: giải thích khi nào biểu thức sau có thể sai:

```sql
HAVING COUNT(cs.skill_id) = (
    SELECT COUNT(*)
    FROM lesson199_skills
    WHERE is_required = TRUE
)
```

**Đáp án:** có thể sai nếu:

- `COUNT(cs.skill_id)` đếm cả kỹ năng **không bắt buộc**.
- Một kỹ năng xuất hiện nhiều dòng chứng nhận, khiến số dòng nhiều hơn số kỹ năng khác nhau.
- `COUNT(*)` của tập yêu cầu đếm trùng phần tử qua một `JOIN`.
- Không kiểm tra `is_verified = TRUE` theo quy tắc nghiệp vụ.
- Điều kiện `JOIN` làm nhân dòng.

Muốn áp dụng phương pháp đếm, phải giới hạn **đúng tập kỹ năng bắt buộc đã xác minh**, rồi dùng `COUNT(DISTINCT cs.skill_id)` và một số đếm tập yêu cầu duy nhất, như truy vấn mẫu ở phần 13.

### Bài 11. NOT IN với NULL

```sql
SELECT 1 AS result_value
WHERE 30 NOT IN (10, 20, NULL);
```

**Đáp án:** trong PostgreSQL, truy vấn không trả dòng nào vì điều kiện trở thành `UNKNOWN`. Đây là một lý do cần thận trọng khi thay các truy vấn kiểm tra thiếu quan hệ bằng `NOT IN` mà không kiểm soát `NULL`.

### Bài 12. Mở rộng yêu cầu theo vai trò

Giả sử các bảng:

```text
candidates(candidate_id, role_id, full_name)
role_requirements(role_id, skill_id)
candidate_skills(candidate_id, skill_id, verified)
```

Viết truy vấn tìm ứng viên đáp ứng mọi kỹ năng của **vai trò chính họ ứng tuyển**.

```sql
SELECT c.candidate_id, c.full_name
FROM candidates AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM role_requirements AS r
    WHERE r.role_id = c.role_id
      AND NOT EXISTS (
          SELECT 1
          FROM candidate_skills AS cs
          WHERE cs.candidate_id = c.candidate_id
            AND cs.skill_id = r.skill_id
            AND cs.verified = TRUE
      )
);
```

**Giải thích:** `r.role_id = c.role_id` giới hạn tập yêu cầu theo đúng vai trò; `cs.candidate_id = c.candidate_id` giới hạn chứng cứ theo đúng ứng viên; `cs.skill_id = r.skill_id` đối chiếu từng kỹ năng bắt buộc.

## 23. Bảng ghi nhớ

| Câu hỏi | Kỹ thuật và ý nghĩa |
|---|---|
| Có ít nhất một quan hệ phù hợp? | `EXISTS (matching_rows)` |
| Không có bất kỳ quan hệ phù hợp? | `NOT EXISTS (matching_rows)` |
| Đã đáp ứng **tất cả** yêu cầu? | `NOT EXISTS (required r WHERE NOT EXISTS (matching evidence for r))` |
| Tại sao cần hai NOT? | Một NOT xác định **yêu cầu bị thiếu**, NOT ngoài bảo đảm **không còn yêu cầu bị thiếu** |
| Tập yêu cầu rỗng? | Mọi đối tượng ở tập ngoài đạt theo **vacuous truth**, nếu không đặt điều kiện bổ sung |
| Chỉ cho phép tập yêu cầu không rỗng? | Thêm `EXISTS (SELECT 1 FROM required)` |
| Có tất cả khác với có đúng tập? | “Có tất cả” cho phép phần tử bổ sung; “đúng tập” cần điều kiện **không có phần tử ngoài tập** |
| Dữ liệu chứng nhận trùng? | `EXISTS` chỉ cần một dòng; `COUNT` thường cần `DISTINCT` |
| So sánh bằng HAVING? | Đếm **phần tử yêu cầu khác nhau đã đáp ứng**, không đếm tùy tiện mọi dòng |
| Chỉ muốn kiểm tra mọi dòng hiện có đều đạt? | Thường một `NOT EXISTS` trên những dòng **không đạt** là đủ |
| Truy vấn sai cho kết quả quá nhiều đối tượng? | Kiểm tra đủ điều kiện tương quan **đối tượng** và **phần tử yêu cầu** |
| Cần hiệu năng? | Xác định đúng tập yêu cầu, có chỉ mục trên cặp khóa ghép và xem `EXPLAIN` |

**Câu đọc SQL nên ghi nhớ:**

> “Chọn đối tượng `c` khi **không tồn tại yêu cầu `r` nào mà không tồn tại bản ghi hợp lệ chứng minh `c` đã đáp ứng `r`**.”

Nếu bạn hiểu được câu này, bạn đã nắm được bản chất của **`NOT EXISTS` lồng nhau**: biến bài toán “**mọi phần tử đều được đáp ứng**” thành bài toán “**không tồn tại phản ví dụ**”. Cách tư duy đó áp dụng cho kỹ năng, môn học, sản phẩm, đơn hàng, nhiệm vụ và nhiều mối quan hệ khác trong SQL.

