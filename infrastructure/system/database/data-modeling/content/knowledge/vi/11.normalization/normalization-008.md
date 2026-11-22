# Dạng chuẩn thứ năm và phân rã theo phụ thuộc nối

**Dạng chuẩn thứ năm (Fifth Normal Form, 5NF)**, còn gọi là **Project-Join Normal Form (PJNF)**, đề cập những quan hệ có thể phân rã thành nhiều hình chiếu nhỏ hơn và ghép lại **không mất thông tin** nhờ một quy tắc nghiệp vụ gọi là **phụ thuộc nối (join dependency, JD)**. Ở một số hệ thống, bảng ba cột biểu diễn các tổ hợp của ba quan hệ hai chiều; nếu ba quan hệ hai chiều là những sự thật độc lập và **mọi tổ hợp đáp ứng cả ba điều kiện đều hợp lệ**, lưu cả bộ ba gây dư thừa và tăng rủi ro sai lệch.

Trong chương **Chuẩn hóa** của mô-đun **DATABASE_DATA_MODELING**, chủ đề này tiếp nối khóa ứng viên, phụ thuộc hàm, BCNF và phụ thuộc đa trị của 4NF. Mục tiêu là đọc được quy tắc nghiệp vụ, xác minh một phép phân rã có thật sự **lossless join** hay không, và lựa chọn mô hình có thể kiểm chứng bằng khóa, ràng buộc và truy vấn. **Không nên phân rã chỉ vì một bảng có ba khóa ngoại hoặc phép JOIN có thể chạy được**; ngữ nghĩa của các tổ hợp là yếu tố quyết định.

## 1. Bài toán: nhà cung cấp, vật tư và dự án

Một công ty quản lý việc phân phối vật tư cho dự án. Đặt ba mã:

- **supplier_id (S):** nhà cung cấp;
- **part_id (P):** loại vật tư;
- **project_id (J):** dự án.

Theo phiên bản nghiệp vụ đầu tiên, một bộ **(S, P, J)** được phép khi và chỉ khi **đồng thời** thỏa ba điều kiện:

1. Nhà cung cấp S **có năng lực cung cấp** vật tư P.
2. Nhà cung cấp S **được phê duyệt tham gia** dự án J.
3. Dự án J **có nhu cầu sử dụng** vật tư P.

Không có điều kiện chấp thuận riêng cho từng bộ ba. Nếu cả ba cặp đều hợp lệ, bộ ba **bắt buộc được xem là hợp lệ**. Đây là giả định quan trọng sẽ dẫn đến JD.

Thiết kế ban đầu lưu các bộ ba hợp lệ trong một bảng:

| supplier_id | part_id | project_id |
| --- | --- | --- |
| S1 | P1 | J1 |
| S1 | P1 | J2 |
| S1 | P2 | J2 |
| S2 | P1 | J2 |

Theo dữ liệu này:

- S1 có năng lực với P1, P2; S2 có năng lực với P1.
- S1 tham gia J1, J2; S2 tham gia J2.
- J1 cần P1; J2 cần P1, P2.

Mỗi hàng là **một tổ hợp được phép**, nhưng không mang thông tin bổ sung riêng cho tổ hợp. Nếu chỉ muốn biết S1 có cung cấp P1 hay không, thông tin **(S1, P1)** xuất hiện ở hai hàng, ứng với J1 và J2. Những cặp khác cũng có thể được lặp lại.

## 2. Phụ thuộc nối là gì?

### 2.1. Định nghĩa qua phép chiếu và phép nối

Cho quan hệ **R** và các tập thuộc tính **R1, R2, ..., Rn** sao cho hợp các tập đó bằng toàn bộ thuộc tính R. Ký hiệu:

~~~text
*(R1, R2, ..., Rn)
~~~

là một **join dependency (JD)** nếu mọi trạng thái hợp lệ của R đều thỏa:

~~~text
R = π_R1(R) ⋈ π_R2(R) ⋈ ... ⋈ π_Rn(R)
~~~

Trong đó:

- **π** (projection/phép chiếu) chọn các cột và theo ngữ nghĩa tập hợp của mô hình quan hệ, loại bộ trùng.
- **⋈** là phép nối tự nhiên theo các thuộc tính cùng tên, với cùng ý nghĩa và miền giá trị.
- Dấu **=** đòi hỏi kết quả nối **không thiếu bộ gốc và không phát sinh bộ giả**.
- JD là quy tắc phải đúng với **mọi trạng thái dữ liệu hợp lệ**, không chỉ một bảng mẫu đang có.

Với ba thuộc tính S, P, J, xét phụ thuộc:

~~~text
*(SP, SJ, PJ)

R(S, P, J)
  = π_(S,P)(R)
    ⋈ π_(S,J)(R)
    ⋈ π_(P,J)(R)
~~~

Nó nói rằng toàn bộ các bộ ba được xác định hoàn toàn bằng **ba tập cặp**: nhà cung cấp–vật tư, nhà cung cấp–dự án và dự án–vật tư.

### 2.2. JD tầm thường và không tầm thường

Một JD là **tầm thường (trivial)** nếu trong các tập thuộc tính thành phần có **ít nhất một tập chứa toàn bộ các thuộc tính của R**. Ví dụ:

~~~text
*(SPJ, SP)
~~~

không chỉ ra một phân rã hữu ích vì một thành phần đã là cả quan hệ ban đầu.

Ngược lại:

~~~text
*(SP, SJ, PJ)
~~~

là **không tầm thường**: không tập thành phần nào chứa đủ S, P, J. Nếu JD này đúng vì nghiệp vụ, nó mở ra khả năng phân rã R thành ba quan hệ nhỏ hơn.

**Lưu ý:** việc có khóa chính **(S, P, J)**, hay chỉ cần thấy ba tập cặp trong dữ liệu, **không tự chứng minh** JD. Phải xác nhận quy tắc “mọi bộ ba thỏa ba cặp đều hợp lệ”.

## 3. Định nghĩa 5NF và vai trò của khóa ứng viên

Một quan hệ đạt **5NF (PJNF)** khi **mọi join dependency không tầm thường có hiệu lực trên quan hệ đều là hệ quả của các khóa ứng viên của quan hệ**. Nói cách khác, không còn JD không tầm thường nào độc lập với những ràng buộc khóa mà ta phải dùng để phân rã quan hệ thêm nhằm tránh dư thừa.

Diễn giải thực hành:

1. Xác định các **khóa ứng viên** từ các phụ thuộc hàm nghiệp vụ.
2. Tìm những JD không tầm thường có thể đúng theo quy tắc kết hợp của dữ liệu.
3. Nếu có JD **không suy ra chỉ từ các khóa**, xem xét phân rã theo những hình chiếu thành phần.
4. Chỉ chấp nhận phân rã nếu việc nối lại **lossless** đối với mọi trạng thái hợp lệ.

Trong ví dụ cung ứng, giả sử nghiệp vụ **không đặt phụ thuộc hàm không tầm thường nào** trên S, P, J. Cả **(S,P)**, **(S,J)** và **(P,J)** đều có thể xuất hiện trên nhiều hàng. Vì vậy, khóa ứng viên của quan hệ ba cột là **(S, P, J)**.

Khóa này bảo đảm mỗi bộ ba không lặp lại, nhưng **không bắt buộc** các cặp S–P, S–J, P–J hợp lệ phải tạo mọi tổ hợp cùng lúc. Nên JD ***(SP, SJ, PJ)** là **một ràng buộc nghiệp vụ bổ sung**, không phải hệ quả của khóa ba cột. Nếu JD đúng, quan hệ gốc **chưa đạt 5NF**.

### 3.1. So sánh nhanh với các dạng chuẩn thấp hơn

| Dạng chuẩn | Loại phụ thuộc cần chú ý | Điều kiện cốt lõi |
| --- | --- | --- |
| **3NF** | Phụ thuộc hàm X → A | X là siêu khóa **hoặc** A thuộc một khóa ứng viên |
| **BCNF** | Phụ thuộc hàm X → A | Mọi phụ thuộc không tầm thường có X là siêu khóa |
| **4NF** | Phụ thuộc đa trị X ↠ Y | Mọi MVD không tầm thường có X là siêu khóa |
| **5NF** | Phụ thuộc nối trên nhiều hình chiếu | Mọi JD không tầm thường phải suy ra từ các khóa ứng viên |

**MVD là một trường hợp đặc biệt của JD hai thành phần**. Với R(X,Y,Z), phụ thuộc đa trị **X ↠ Y** tương đương điều kiện nối không mất thông tin:

~~~text
R = π_(X,Y)(R) ⋈ π_(X,Z)(R)
~~~

5NF vì thế chặt hơn 4NF: 4NF xử lý các trường hợp có thể phân rã theo MVD, còn 5NF còn xét JD đòi hỏi **ba hay nhiều hình chiếu**. Một quan hệ có thể thỏa BCNF và 4NF nhưng vẫn có JD ba chiều cần phân rã.

## 4. Từ các bộ ba sang ba tập cặp

Lấy phép chiếu của bảng đầu bài:

**Supplier–Part (SP):**

| supplier_id | part_id |
| --- | --- |
| S1 | P1 |
| S1 | P2 |
| S2 | P1 |

**Supplier–Project (SJ):**

| supplier_id | project_id |
| --- | --- |
| S1 | J1 |
| S1 | J2 |
| S2 | J2 |

**Project–Part (PJ):**

| project_id | part_id |
| --- | --- |
| J1 | P1 |
| J2 | P1 |
| J2 | P2 |

Theo quy tắc nghiệp vụ đã nêu, một bộ ba **(S,P,J)** là hợp lệ khi cặp (S,P) thuộc SP, cặp (S,J) thuộc SJ và cặp (P,J) thuộc PJ.

~~~mermaid
flowchart LR
    SP["SP: nhà cung cấp có vật tư"]
    SJ["SJ: nhà cung cấp tham gia dự án"]
    PJ["PJ: dự án cần vật tư"]
    JOIN{"Cùng S, P, J và thỏa cả ba cặp?"}
    RESULT["Bộ ba (S, P, J) hợp lệ"]
    SP --> JOIN
    SJ --> JOIN
    PJ --> JOIN
    JOIN -->|"Có"| RESULT
~~~

Khi nối ba bảng cặp, ta thu đúng bốn hàng ban đầu:

| supplier_id | part_id | project_id | Lý do đủ điều kiện |
| --- | --- | --- | --- |
| S1 | P1 | J1 | S1–P1; S1–J1; J1–P1 |
| S1 | P1 | J2 | S1–P1; S1–J2; J2–P1 |
| S1 | P2 | J2 | S1–P2; S1–J2; J2–P2 |
| S2 | P1 | J2 | S2–P1; S2–J2; J2–P1 |

Không có bộ **(S2,P2,J2)** vì SP không chứa (S2,P2). Không có **(S1,P2,J1)** vì PJ không chứa (J1,P2). Kết quả chính xác xuất phát từ **ba điều kiện nghiệp vụ**, chứ không phải may mắn của phép nối.

### 4.1. Một phụ thuộc nối có thể tồn tại dù không có phụ thuộc đa trị

Trong quan hệ R(S,P,J) đang xét, **S ↠ P** không đúng. Từ hai hàng:

~~~text
(S1, P1, J1)
(S1, P2, J2)
~~~

nếu S ↠ P đúng thì phải có **(S1,P2,J1)**, nhưng bộ này không hợp lệ vì dự án J1 không cần P2. Tương tự, các MVD dạng **P ↠ S** hoặc **J ↠ S** không phải quy tắc nghiệp vụ của hệ thống này.

Với giả định **không có FD hay MVD không tầm thường bổ sung**, quan hệ ba cột đã ở **4NF**, nhưng chưa ở **5NF** do JD ***(SP,SJ,PJ)**. Đây là lý do việc chỉ kiểm tra 4NF chưa đủ cho mọi bài toán tổ hợp ba chiều.

## 5. Thiết kế vật lý: lưu cặp và sinh bộ ba khi cần

Mỗi bảng mới có grain và khóa rõ ràng:

~~~text
supplier_parts(supplier_id, part_id)
supplier_projects(supplier_id, project_id)
project_parts(project_id, part_id)
~~~

Các bảng này lần lượt đại diện cho **năng lực cung ứng**, **quyền tham gia dự án** và **nhu cầu vật tư của dự án**. Không cần bảng chỉ để nhân các tổ hợp nếu không có sự thật riêng của bộ ba.

~~~mermaid
erDiagram
    SUPPLIERS ||--o{ SUPPLIER_PARTS : "có năng lực"
    PARTS ||--o{ SUPPLIER_PARTS : "được cung cấp"
    SUPPLIERS ||--o{ SUPPLIER_PROJECTS : "được phê duyệt"
    PROJECTS ||--o{ SUPPLIER_PROJECTS : "có nhà cung cấp"
    PROJECTS ||--o{ PROJECT_PARTS : "cần vật tư"
    PARTS ||--o{ PROJECT_PARTS : "được sử dụng"
    SUPPLIER_PARTS {
        varchar supplier_id PK
        varchar part_id PK
    }
    SUPPLIER_PROJECTS {
        varchar supplier_id PK
        varchar project_id PK
    }
    PROJECT_PARTS {
        varchar project_id PK
        varchar part_id PK
    }
~~~

Sơ đồ có các bảng danh mục SUPPLIERS, PARTS, PROJECTS để minh họa thực thể độc lập; phần trọng tâm của phân rã JD là **ba bảng liên kết hai chiều**.

### 5.1. DDL và dữ liệu mẫu trong PostgreSQL

Ví dụ tối giản sau chỉ định nghĩa ba bảng liên kết; khi dùng thực tế, thêm khóa ngoại đến bảng danh mục nhà cung cấp, vật tư và dự án:

~~~sql
CREATE TABLE supplier_parts (
    supplier_id VARCHAR(10) NOT NULL,
    part_id     VARCHAR(10) NOT NULL,
    PRIMARY KEY (supplier_id, part_id)
);

CREATE TABLE supplier_projects (
    supplier_id VARCHAR(10) NOT NULL,
    project_id  VARCHAR(10) NOT NULL,
    PRIMARY KEY (supplier_id, project_id)
);

CREATE TABLE project_parts (
    project_id VARCHAR(10) NOT NULL,
    part_id    VARCHAR(10) NOT NULL,
    PRIMARY KEY (project_id, part_id)
);

INSERT INTO supplier_parts (supplier_id, part_id) VALUES
    ('S1', 'P1'),
    ('S1', 'P2'),
    ('S2', 'P1');

INSERT INTO supplier_projects (supplier_id, project_id) VALUES
    ('S1', 'J1'),
    ('S1', 'J2'),
    ('S2', 'J2');

INSERT INTO project_parts (project_id, part_id) VALUES
    ('J1', 'P1'),
    ('J2', 'P1'),
    ('J2', 'P2');
~~~

Tạo một **VIEW** để truy vấn các tổ hợp hợp lệ:

~~~sql
CREATE VIEW eligible_supplier_part_projects AS
SELECT
    sp.supplier_id,
    sp.part_id,
    sj.project_id
FROM supplier_parts AS sp
JOIN supplier_projects AS sj
    ON sj.supplier_id = sp.supplier_id
JOIN project_parts AS pp
    ON pp.project_id = sj.project_id
   AND pp.part_id = sp.part_id;

SELECT supplier_id, part_id, project_id
FROM eligible_supplier_part_projects
ORDER BY supplier_id, part_id, project_id;
~~~

Kết quả là đúng bốn bộ ở mục 1. Mỗi bảng cặp quản lý một sự thật nghiệp vụ độc lập; VIEW dùng phép nối để xác định bộ ba **khi cần đọc**.

### 5.2. Thao tác cập nhật sau phân rã

**Thêm năng lực mới** cho S2 đối với P2:

~~~sql
INSERT INTO supplier_parts (supplier_id, part_id)
VALUES ('S2', 'P2');
~~~

Vì S2 đã tham gia J2 và J2 cần P2, VIEW tự xuất hiện thêm **(S2,P2,J2)** theo quy tắc nghiệp vụ.

**Thu hồi phê duyệt S1 ở J2:**

~~~sql
DELETE FROM supplier_projects
WHERE supplier_id = 'S1' AND project_id = 'J2';
~~~

Khi đó VIEW không còn các bộ **(S1,P1,J2)** và **(S1,P2,J2)**. Việc mất cả hai tổ hợp là **đúng theo nghiệp vụ** vì nhà cung cấp không còn được duyệt tham gia J2. Tách bảng cho phép thay đổi đúng sự thật nền tảng mà không phải tìm mọi tổ hợp liên quan để sửa từng hàng.

Nếu thực hiện hai ví dụ theo thứ tự trên dữ liệu mẫu, thay đổi thứ hai không làm mất cặp năng lực S1–P1/S1–P2 hay nhu cầu vật tư của J2. Các bảng giữ riêng vòng đời của từng quan hệ.

## 6. Kiểm chứng lossless join và phát hiện bộ giả

### 6.1. Không thể xác nhận JD chỉ bằng một lần JOIN

Một phép JOIN trả kết quả không lỗi SQL **không chứng minh** đây là phân rã đúng. Có hai vấn đề khác nhau:

- **Lossless join:** từ các hình chiếu của quan hệ gốc hợp lệ, phép nối khôi phục đúng toàn bộ các bộ gốc.
- **Phụ thuộc nghiệp vụ:** quy tắc nào buộc mọi tổ hợp thỏa ba cặp cũng là bộ hợp lệ? Đây là lý do để kết luận JD đúng với **mọi trạng thái hợp lệ**.

Đối với ba hình chiếu SP, SJ, PJ của quan hệ R, một bộ **(S,P,J)** hiện diện trong R luôn xuất hiện trong phép nối, vì nó đóng góp cả ba cặp. Rủi ro của phép nối chủ yếu là sinh thêm **bộ giả (spurious tuple)**, tức một tổ hợp từ ba cặp chưa từng có trong quan hệ gốc.

Trong ví dụ ở mục 1, không có bộ giả vì quy tắc nghiệp vụ đã khẳng định mọi bộ đáp ứng ba cặp đều hợp lệ. Nhưng ta có thể sử dụng SQL để phát hiện sai lệch trong **một trạng thái dữ liệu đang xét**.

### 6.2. Tạo dữ liệu tham chiếu và phép nối từ hình chiếu

Để các truy vấn kiểm chứng sau có thể chạy độc lập với việc thay đổi ba bảng ở mục 5, tạo một bảng tạm biểu diễn các bộ ba gốc:

~~~sql
CREATE TEMP TABLE supply_triples (
    supplier_id VARCHAR(10) NOT NULL,
    part_id     VARCHAR(10) NOT NULL,
    project_id  VARCHAR(10) NOT NULL,
    PRIMARY KEY (supplier_id, part_id, project_id)
);

INSERT INTO supply_triples (supplier_id, part_id, project_id) VALUES
    ('S1', 'P1', 'J1'),
    ('S1', 'P1', 'J2'),
    ('S1', 'P2', 'J2'),
    ('S2', 'P1', 'J2');

CREATE TEMP VIEW reconstructed_triples AS
SELECT
    sp.supplier_id,
    sp.part_id,
    sj.project_id
FROM (
    SELECT DISTINCT supplier_id, part_id
    FROM supply_triples
) AS sp
JOIN (
    SELECT DISTINCT supplier_id, project_id
    FROM supply_triples
) AS sj
    ON sj.supplier_id = sp.supplier_id
JOIN (
    SELECT DISTINCT project_id, part_id
    FROM supply_triples
) AS pj
    ON pj.project_id = sj.project_id
   AND pj.part_id = sp.part_id;
~~~

Phép kiểm tra **hai chiều** bằng toán tử tập hợp **EXCEPT**:

~~~sql
-- Bộ có trong phép nối nhưng không có ở R gốc: bộ giả.
SELECT supplier_id, part_id, project_id
FROM reconstructed_triples
EXCEPT
SELECT supplier_id, part_id, project_id
FROM supply_triples;

-- Bộ gốc không có trong phép nối: bộ bị mất.
SELECT supplier_id, part_id, project_id
FROM supply_triples
EXCEPT
SELECT supplier_id, part_id, project_id
FROM reconstructed_triples;
~~~

Với bốn hàng ban đầu, **cả hai truy vấn đều không trả về hàng nào**. Điều này xác nhận phép nối chính xác **đối với mẫu hiện tại**; để được phép dùng thiết kế lâu dài, vẫn cần quy tắc nghiệp vụ làm cơ sở cho JD.

### 6.3. Thử xóa một bộ ba nhưng vẫn giữ cả ba cặp

Xét thao tác xóa **(S1,P1,J2)** khỏi bảng gộp, trong khi giữ lại ba hàng còn lại:

~~~sql
BEGIN;

DELETE FROM supply_triples
WHERE supplier_id = 'S1'
  AND part_id = 'P1'
  AND project_id = 'J2';

SELECT supplier_id, part_id, project_id
FROM reconstructed_triples
EXCEPT
SELECT supplier_id, part_id, project_id
FROM supply_triples;

ROLLBACK;
~~~

Truy vấn sẽ trả **(S1,P1,J2)**. Lý do là ba cặp liên quan vẫn còn trong dữ liệu:

- **(S1,P1)** còn ở hàng (S1,P1,J1).
- **(S1,J2)** còn ở hàng (S1,P2,J2).
- **(J2,P1)** còn ở hàng (S2,P1,J2).

Phép nối các hình chiếu tạo lại bộ vừa xóa. Nếu quy tắc nghiệp vụ xác nhận ba cặp là đủ, thao tác “xóa riêng bộ ba” **không phải** thay đổi nghiệp vụ hợp lệ: muốn bộ ba không còn hợp lệ phải thay đổi **ít nhất một sự thật cặp**. Ngược lại, nếu có nghiệp vụ cho phép cấm riêng bộ ba trong khi ba cặp vẫn đúng, đó là dấu hiệu **JD giả định đã sai** và không thể chỉ lưu ba bảng cặp.

Đây là khác biệt quan trọng giữa **đọc lại một trạng thái** và **đánh giá mọi trạng thái hợp lệ**. Dữ liệu không khớp kết quả nối có thể là lỗi thiếu bộ ba theo quy tắc JD, hoặc là bằng chứng quy tắc cần diễn đạt khác.

## 7. Phản ví dụ: phê duyệt riêng cho từng bộ ba

Giả sử bộ phận quản trị thay đổi yêu cầu:

> Nhà cung cấp S có thể cung cấp vật tư P, được duyệt vào dự án J, và dự án J cần P; **tuy nhiên mỗi sự kết hợp (S,P,J) còn phải được phê duyệt kỹ thuật riêng**.

Khi đó, ba cặp chỉ là **điều kiện cần**. Chúng **không đủ** để kết luận một bộ ba hợp lệ.

Ví dụ những bộ ba được phê duyệt là:

| supplier_id | part_id | project_id |
| --- | --- | --- |
| S1 | P1 | J1 |
| S1 | P2 | J2 |
| S2 | P1 | J2 |

Ba hình chiếu của tập này vẫn chứa:

~~~text
SP: (S1,P1), (S1,P2), (S2,P1)
SJ: (S1,J1), (S1,J2), (S2,J2)
PJ: (J1,P1), (J2,P2), (J2,P1)
~~~

Khi nối, ta nhận thêm **(S1,P1,J2)**. Bộ ba này thỏa cả ba cặp, nhưng **chưa được phê duyệt riêng**. Nó là **bộ giả** đối với quan hệ mới; phương trình JD ***(SP,SJ,PJ)** **không đúng**.

Một thiết kế phù hợp có thể giữ bảng **approved_supply_combinations** ở grain một bộ ba, bên cạnh ba bảng cặp đang thể hiện các điều kiện cần:

~~~sql
CREATE TABLE approved_supply_combinations (
    supplier_id VARCHAR(10) NOT NULL,
    part_id     VARCHAR(10) NOT NULL,
    project_id  VARCHAR(10) NOT NULL,
    PRIMARY KEY (supplier_id, part_id, project_id),
    FOREIGN KEY (supplier_id, part_id)
        REFERENCES supplier_parts(supplier_id, part_id),
    FOREIGN KEY (supplier_id, project_id)
        REFERENCES supplier_projects(supplier_id, project_id),
    FOREIGN KEY (project_id, part_id)
        REFERENCES project_parts(project_id, part_id)
);
~~~

Ba khóa ngoại ghép bảo đảm **bộ ba được phê duyệt chỉ được chọn từ những cặp đang hợp lệ**. Nhưng không có yêu cầu “mọi bộ ba từ ba cặp đều được phê duyệt”: bảng ba cột có nhiệm vụ lưu những quyết định riêng.

Không thể suy rằng bảng **approved_supply_combinations** cần tách thêm theo JD cũ. Nếu mỗi bộ ba là một quyết định độc lập không suy ra từ các cặp, nó là **một sự thật nghiệp vụ thực sự**, không phải bản sao dư thừa.

**Lưu ý về thay đổi quy tắc:** nếu phê duyệt từng bộ ba mang trạng thái, ngày hiệu lực hoặc người phê duyệt, những thuộc tính đó càng làm rõ grain độc lập của bộ ba. Khi cần lịch sử, có thể phải thêm phiên bản, kỳ hiệu lực hoặc sự kiện phê duyệt.

## 8. Phân rã theo JD khác gì phân rã theo FD hoặc MVD?

| Tình huống | Phụ thuộc được xác nhận | Cách phân rã tiêu biểu |
| --- | --- | --- |
| Mỗi phòng ban có một tên hiện hành | FD: **department_id → department_name** | Tách bảng phòng ban, giữ mã phòng tại nhân viên |
| Học viên có các ngôn ngữ và sở thích độc lập | MVD: **student_id ↠ language_code** | Tách **student_languages** và **student_hobbies** |
| Nhà cung cấp–vật tư–dự án xác định hoàn toàn bởi ba điều kiện cặp | JD: ***(SP,SJ,PJ)** | Tách **supplier_parts**, **supplier_projects**, **project_parts** |
| Mỗi tổ hợp ba chiều phải phê duyệt riêng | Không có JD ba cặp đã nêu | Giữ bảng bộ ba như một quan hệ có ý nghĩa riêng |

Một phép phân rã nhị phân từ MVD có cấu trúc:

~~~text
R(X,Y,Z) = π_(X,Y)(R) ⋈ π_(X,Z)(R)
~~~

Trong ví dụ cung ứng, các hình chiếu **SP** và **SJ** nối với nhau chưa đủ: chúng có thể kết hợp S1–P2–J1, dù J1 không cần P2. Phải dùng thêm **PJ**. Chính điều kiện kết hợp **ba** tập cặp này làm JD ở ví dụ khác với mô hình hai tập đa trị độc lập.

### 8.1. 5NF có bắt buộc mọi bảng chỉ còn hai cột?

**Không.** 5NF không giới hạn số lượng cột. Một bảng ba, bốn hoặc nhiều thuộc tính vẫn có thể đạt 5NF nếu không có JD không tầm thường cần phân rã tiếp ngoài những JD suy ra từ khóa ứng viên.

Ví dụ, **order_lines(order_id, line_no, product_id, quantity, unit_price_at_order)** có thể là bảng có grain một dòng hàng và chứa những sự thật độc lập của dòng hàng. Không có cơ sở tách bảng chỉ vì nó có nhiều cột. Khóa, lịch sử giá, quy tắc giao dịch và các phụ thuộc thực tế mới quyết định dạng chuẩn.

### 8.2. JD tầm thường không phải vi phạm

Phụ thuộc có một thành phần chứa **toàn bộ thuộc tính R** là tầm thường, ví dụ ***(SPJ, SP)**. Nó không tạo phân rã có ích. Khi kiểm tra 5NF, tập trung vào các JD **không tầm thường** và câu hỏi chúng có được suy ra từ khóa hay không.

### 8.3. Thêm khóa thay thế không tự loại bỏ quy tắc kết hợp

Nếu thêm **id** làm khóa chính vào bảng ba chiều, ba cặp vẫn là những sự thật nghiệp vụ có thể xác định bộ ba trong mô hình đầu tiên. Khóa thay thế giúp định danh một hàng nhưng không thay đổi câu hỏi liệu mọi tổ hợp thỏa ba điều kiện đều hợp lệ.

Đánh giá dạng chuẩn của **quan hệ mở rộng** cần tính lại các khóa ứng viên và phụ thuộc có hiệu lực. Không thể kết luận “có ID nên đạt 5NF”, cũng không nên bỏ các ràng buộc cặp chỉ để thêm ID.

## 9. Áp dụng trong hệ thống thực tế: toàn vẹn dữ liệu và hiệu năng

### 9.1. Quy trình xác minh một phân rã theo JD

1. **Xác định grain:** một hàng là quan hệ kết hợp ba chiều, giao dịch độc lập hay chỉ là hệ quả của những điều kiện nhỏ hơn?
2. **Liệt kê khóa ứng viên và FD:** không suy khóa từ dữ liệu mẫu; cần quy tắc tối thiểu để định danh bộ.
3. **Xét MVD:** có thể đã có phân rã hai thành phần được bảo đảm bởi các tập đa trị độc lập hay chưa?
4. **Đề xuất JD:** ghi rõ các tập thuộc tính cần chiếu, ví dụ ***(SP,SJ,PJ)**.
5. **Xác nhận điều kiện hai chiều với nghiệp vụ:** mỗi bộ ba hợp lệ có đủ ba cặp; và **mọi bộ ba có đủ ba cặp đều hợp lệ**.
6. **Kiểm chứng trên dữ liệu:** dùng phép chiếu, phép nối và phép hiệu tập hợp theo cả hai hướng để phát hiện bộ giả hoặc thiếu bộ trong trạng thái hiện tại.
7. **Phân rã và đặt khóa:** mỗi bảng thành phần phải biểu diễn một sự thật độc lập và có grain, khóa, khóa ngoại phù hợp.
8. **Thử các thao tác thay đổi:** thêm cặp mới có làm xuất hiện đúng các tổ hợp mới không; bỏ một cặp có loại đúng những tổ hợp phụ thuộc vào nó không?
9. **Kiểm tra tính khả thi của quy tắc ghi:** nếu có ngoại lệ theo bộ ba, cần mô hình lưu ngoại lệ/quyết định riêng thay vì giả định JD.
10. **Tối ưu truy vấn sau khi đúng mô hình:** đánh giá chỉ mục, thứ tự JOIN, số lượng bộ kết quả, nhu cầu view hay materialized view.

### 9.2. Có thể tạo chỉ mục và view đọc riêng

Các khóa chính ghép của ba bảng ở mục 5 bảo vệ các cặp duy nhất. Trong một hệ quản trị SQL, thường cần cân nhắc thứ tự cột của chỉ mục theo kiểu truy vấn:

- **supplier_parts(supplier_id, part_id)** thuận lợi khi lọc theo supplier_id.
- **supplier_projects(supplier_id, project_id)** thuận lợi khi lọc theo supplier_id.
- **project_parts(project_id, part_id)** thuận lợi khi lọc theo project_id.

Nếu thường xuyên tìm **nhà cung cấp theo vật tư** hoặc **nhà cung cấp theo dự án**, có thể đánh giá các chỉ mục bổ sung đặt cột lọc lên trước, tùy hệ quản trị và kế hoạch thực thi:

~~~sql
CREATE INDEX idx_supplier_parts_part_supplier
ON supplier_parts (part_id, supplier_id);

CREATE INDEX idx_supplier_projects_project_supplier
ON supplier_projects (project_id, supplier_id);
~~~

Chỉ mục cần được xác nhận qua truy vấn thực tế, số lượng bản ghi và chi phí cập nhật. Nếu kết quả ba chiều được đọc rất thường xuyên nhưng thay đổi cặp hiếm, có thể cân nhắc **materialized view** hoặc bảng đọc suy ra từ ba nguồn chuẩn, với cơ chế làm mới và kiểm tra nhất quán. Việc tăng tốc đọc không có nghĩa làm biến mất JD hoặc quy tắc nghiệp vụ.

### 9.3. Không đánh đồng lossless join với khả năng bảo toàn mọi ràng buộc

**Lossless join** nói về việc tái tạo bộ gốc khi các bảng được chiếu từ một quan hệ hợp lệ. **Dependency preservation** nói về khả năng suy ra và kiểm soát các phụ thuộc từ ràng buộc ở các bảng sau phân rã. Đây là hai tính chất khác nhau.

Trong thiết kế chỉ có ba tập cặp và quy tắc “đủ ba cặp là hợp lệ”, view tự thực hiện JD. Nhưng các quy tắc **trên bộ ba** mới phát sinh — chẳng hạn cần giấy phép riêng cho tổ hợp nhà cung cấp–vật tư–dự án — không được ba khóa chính cặp bảo vệ. Khi yêu cầu thay đổi, phải cập nhật mô hình hoặc cơ chế kiểm soát phù hợp.

Đặc biệt, khóa ngoại giữa các bảng cặp và danh mục có thể bảo vệ tính tồn tại của mã, nhưng **không chứng minh** điều kiện “mọi tổ hợp đều hợp lệ”. Điều kiện đó phải được người thiết kế xác nhận với nghiệp vụ.

## 10. Bài tập vận dụng

### Bài 1. Chuyên gia, kỹ năng và thị trường

Hệ thống tư vấn lưu các bộ ba **(consultant_id, skill_id, region_id)**. Nghiệp vụ khẳng định:

- Chuyên gia C có kỹ năng K trong danh mục **consultant_skills**.
- Chuyên gia C được phép làm việc ở khu vực R trong **consultant_regions**.
- Kỹ năng K được phép cung cấp ở R trong **region_skills**.
- **Mọi** bộ ba C–K–R đáp ứng đủ ba điều kiện đều là tổ hợp dịch vụ được phép, không cần xét duyệt riêng theo bộ ba.

Dữ liệu:

~~~text
consultant_skills:  (C1,K1), (C1,K2), (C2,K1)
consultant_regions: (C1,R1), (C1,R2), (C2,R2)
region_skills:     (R1,K1), (R2,K1), (R2,K2)
~~~

**Yêu cầu:**

1. Viết JD trên quan hệ gốc **R(C,K,Rg)**, dùng ký hiệu Rg cho region để tránh nhầm tên quan hệ.
2. Liệt kê các bộ ba được phép.
3. Nếu không có FD/MVD nghiệp vụ không tầm thường bổ sung, bảng ba cột đạt 4NF và 5NF hay chưa?
4. Đề xuất ba bảng lưu trữ và giải thích vì sao phép nối là lossless theo nghiệp vụ.

<details>
<summary>Gợi ý lời giải bài 1</summary>

JD là ***(CK, CRg, KRg)**. Các bộ ba được phép:

~~~text
(C1,K1,R1)
(C1,K1,R2)
(C1,K2,R2)
(C2,K1,R2)
~~~

Nếu không có FD và MVD không tầm thường, khóa ứng viên của quan hệ gốc là **(C,K,Rg)**; nó có thể đạt **4NF**. JD ba cặp là không tầm thường, không suy ra từ khóa ba cột, nên bảng gốc **chưa đạt 5NF**.

Lưu **consultant_skills(C,K)**, **consultant_regions(C,Rg)**, **region_skills(Rg,K)**. Mỗi bảng cặp có khóa chính ghép. Phép nối theo C, K và Rg khôi phục chính xác bộ ba vì nghiệp vụ xác nhận không còn điều kiện riêng của bộ ba.

</details>

### Bài 2. Một ngoại lệ thay đổi mô hình

Giữ dữ liệu của bài 1, nhưng cơ quan quản lý yêu cầu **C1 cung cấp K1 tại R2 phải có chứng chỉ riêng và hiện chưa được duyệt**. Các cặp C1–K1, C1–R2 và K1–R2 vẫn hợp lệ.

**Câu hỏi:** ba bảng cặp có còn đủ để thể hiện đúng tập tổ hợp được phép không? Phép nối sẽ tạo bộ giả nào? Cần lưu thông tin mới ở grain nào?

<details>
<summary>Gợi ý lời giải bài 2</summary>

Ba bảng cặp vẫn tạo **(C1,K1,R2)** dù tổ hợp này chưa được phép. Vì thế JD ba cặp **không còn đúng** với quan hệ các tổ hợp đã phê duyệt.

Cần thêm quan hệ theo bộ ba như **approved_consultant_skill_regions(C,K,Rg)**, có thể kèm trạng thái và chứng chỉ. Có thể dùng các khóa ngoại ghép về ba bảng cặp để bảo đảm điều kiện cần. Tách toàn bộ thành ba cặp mà bỏ quyết định riêng sẽ làm mất thông tin.

</details>

### Bài 3. Tại sao 4NF chưa đủ?

Cho **R(S,P,J)** với các giả định của bài toán đầu tiên. Hãy giải thích:

- Vì sao **S ↠ P** không đúng khi J1 không cần P2?
- Tại sao điều đó không phủ định JD ***(SP,SJ,PJ)**?
- Vì sao quan hệ vẫn có thể đạt 4NF nhưng vi phạm 5NF?

**Gợi ý:** MVD S ↠ P sẽ buộc mọi vật tư của S kết hợp với mọi dự án J của S. Quy tắc doanh nghiệp lại yêu cầu thêm điều kiện **J cần P** nên phép nối phải dùng **ba quan hệ cặp**. JD ba thành phần có thể đúng dù không có MVD hai thành phần thích hợp.

## 11. Những nhầm lẫn cần tránh

| Nhận định sai | Cách đánh giá đúng |
| --- | --- |
| “Có ba khóa ngoại là phải tách thành ba bảng.” | Chỉ tách khi **quy tắc nghiệp vụ bảo đảm JD** và không làm mất một sự thật bộ ba. |
| “Ba hình chiếu JOIN được nghĩa là lossless.” | Phải so sánh với quan hệ gốc và chứng minh đúng với **mọi trạng thái hợp lệ**. |
| “Đạt 4NF thì chắc chắn đạt 5NF.” | Một JD ba thành phần có thể đúng dù không có MVD hai thành phần vi phạm 4NF. |
| “5NF bắt buộc mọi bảng chỉ hai cột.” | Số cột không quyết định dạng chuẩn; cần xét JD và khóa ứng viên. |
| “Đã có PRIMARY KEY ba cột thì không thể dư thừa.” | Khóa chặn bộ ba trùng, không tự loại bỏ sự lặp lại của các điều kiện cặp. |
| “Cứ tách càng nhiều là càng chuẩn hóa tốt.” | Phân rã thiếu cơ sở có thể tạo **bộ giả** hoặc bỏ mất quy tắc riêng của bộ ba. |
| “Không thấy bộ giả ở dữ liệu hiện tại là đủ.” | Kiểm tra dữ liệu chỉ xác nhận một trạng thái; JD là **quy tắc cho mọi trạng thái hợp lệ**. |
| “Thêm surrogate ID sẽ giải quyết vấn đề 5NF.” | ID không thay đổi nguồn gốc các tổ hợp hoặc thay thế việc xác định phụ thuộc. |
| “Tối ưu JOIN đồng nghĩa tối ưu cấu trúc dữ liệu.” | Chỉ mục và view tối ưu đọc; vẫn phải làm rõ nguồn dữ liệu chuẩn và ràng buộc. |

## 12. Ghi nhớ

**5NF yêu cầu mọi phụ thuộc nối không tầm thường phải là hệ quả của các khóa ứng viên.** Trường hợp điển hình là một quan hệ ba chiều được xác định hoàn toàn bằng **ba tập cặp**: S có thể cung cấp P, S được tham gia J, và J cần P. Nếu **mọi bộ ba thỏa cả ba cặp đều hợp lệ**, JD ***(SP,SJ,PJ)** đúng và có thể phân rã quan hệ thành ba bảng cặp, rồi nối lại không mất thông tin.

Điều kiện **“nếu và chỉ nếu”** của nghiệp vụ là mấu chốt. Nếu một tổ hợp ba chiều còn cần xét duyệt hoặc mang thuộc tính riêng, ba cặp không đủ và phép nối có thể sinh bộ giả. Hãy xác định grain, khóa ứng viên và phụ thuộc thật sự, kiểm chứng **lossless join**, bảo vệ các ràng buộc sau phân rã và chỉ sau đó cân nhắc chỉ mục hoặc mô hình đọc phi chuẩn hóa.
