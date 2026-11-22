# Dạng chuẩn thứ ba và các phụ thuộc cần tách

Trong mô hình dữ liệu quan hệ, một bảng có thể đạt **dạng chuẩn thứ nhất (1NF)** và **dạng chuẩn thứ hai (2NF)** nhưng vẫn lưu lặp đi lặp lại một sự thật thuộc về thực thể khác. Khi tên phòng ban nằm trên mọi hàng nhân viên, việc đổi tên phòng đòi hỏi sửa nhiều hàng, còn xóa nhân viên cuối có thể làm mất thông tin phòng ban. **Dạng chuẩn thứ ba (Third Normal Form, 3NF)** giúp nhận diện và xử lý nhóm phụ thuộc hàm gây ra tình huống đó.

Mục tiêu của bài học thuộc chương **Chuẩn hóa** trong mô-đun **DATABASE_DATA_MODELING** là chuyển các quy tắc nghiệp vụ thành phụ thuộc hàm, nhận diện những thuộc tính cần chuyển sang bảng sở hữu thông tin, phân rã lược đồ và kiểm tra tính đúng đắn bằng khóa, khóa ngoại và phép nối. Bài cũng phân biệt quy tắc thực hành “loại bỏ phụ thuộc bắc cầu” với định nghĩa hình thức của 3NF, vì không phải mọi phụ thuộc giữa hai thuộc tính không phải khóa chính đều vi phạm 3NF.

## 1. Bài toán: bảng nhân viên đang chứa thông tin phòng ban

Giả sử hệ thống nhân sự có các quy tắc:

- Mỗi nhân viên có một **employee_id** duy nhất, tên hiện hành và thuộc một phòng ban hiện hành.
- Mỗi phòng ban có **department_id** duy nhất, tên và một người phụ trách hiện hành.
- Nhiều nhân viên có thể cùng thuộc một phòng ban; phòng ban có thể chưa có nhân viên.
- Khi tên hoặc người phụ trách phòng ban thay đổi, thay đổi áp dụng cho cả phòng, không riêng nhân viên nào.

Bảng ban đầu:

| employee_id | employee_name | department_id | department_name | department_lead |
| ---: | --- | ---: | --- | --- |
| 101 | An | 10 | Kinh doanh | Bình |
| 102 | Chi | 10 | Kinh doanh | Bình |
| 103 | Dũng | 20 | Kỹ thuật | Hà |

SQL minh họa theo PostgreSQL:

~~~sql
CREATE TABLE employees_flat (
    employee_id     BIGINT PRIMARY KEY,
    employee_name   VARCHAR(100) NOT NULL,
    department_id   BIGINT NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    department_lead VARCHAR(100) NOT NULL
);

INSERT INTO employees_flat
    (employee_id, employee_name, department_id,
     department_name, department_lead)
VALUES
    (101, 'An',   10, 'Kinh doanh', 'Bình'),
    (102, 'Chi',  10, 'Kinh doanh', 'Bình'),
    (103, 'Dũng', 20, 'Kỹ thuật',   'Hà');
~~~

**Grain** của bảng là **một nhân viên trên mỗi hàng**; khóa ứng viên duy nhất theo giả định là **employee_id**. Bảng chỉ có một khóa đơn thuộc tính nên không xuất hiện phụ thuộc bộ phận vào khóa ứng viên: bảng đạt **2NF** khi đã thỏa 1NF. Tuy vậy, tên phòng và người phụ trách bị sao chép theo số nhân viên.

Đây là một dấu hiệu thiết kế cần kiểm tra ở 3NF.

## 2. Đọc phụ thuộc hàm từ quy tắc nghiệp vụ

Ký hiệu **X → Y** nghĩa là với mỗi giá trị X, quy tắc nghiệp vụ cho phép tối đa một giá trị Y trong một trạng thái dữ liệu hợp lệ. Một phụ thuộc hàm là **quy tắc cho mọi trạng thái hợp lệ**, không thể chứng minh chỉ bằng vài dòng dữ liệu mẫu.

Với bài toán trên:

~~~text
employee_id   -> employee_name, department_id
department_id -> department_name, department_lead
~~~

Từ tính bắc cầu của phụ thuộc hàm, suy ra:

~~~text
employee_id -> department_id -> department_name
employee_id -> department_id -> department_lead
~~~

Sơ đồ:

~~~mermaid
flowchart LR
    E["employee_id<br/>(khóa ứng viên)"]
    N["employee_name"]
    D["department_id"]
    DN["department_name"]
    DL["department_lead"]
    E --> N
    E --> D
    D --> DN
    D --> DL
~~~

Thuộc tính **department_name** và **department_lead** được xác định bởi **department_id**, vốn không phải siêu khóa của bảng **employees_flat**: nhiều nhân viên có thể cùng mang một **department_id**. Chúng mô tả **phòng ban**, không mô tả riêng một nhân viên.

Phụ thuộc **department_id → department_name, department_lead** là điểm cần tách. Không phải vì hai cột có tên bắt đầu bằng *department_* mà vì **mỗi mã phòng xác định một bộ thông tin phòng** trong nghiệp vụ đang xét.

### 2.1. Những bất thường có thể xuất hiện

**Bất thường khi sửa:** đổi người phụ trách phòng 10 thành Minh nhưng chỉ cập nhật một trong hai hàng:

~~~sql
BEGIN;

UPDATE employees_flat
SET department_lead = 'Minh'
WHERE employee_id = 101;

SELECT employee_id, department_id, department_lead
FROM employees_flat
WHERE department_id = 10
ORDER BY employee_id;
-- 101 -> Minh, 102 -> Bình: cùng phòng có hai người phụ trách.

ROLLBACK;
~~~

**Bất thường khi thêm:** không thể ghi phòng **30 – Vận hành** khi chưa có nhân viên, bởi bảng buộc có **employee_id**.

**Bất thường khi xóa:** xóa nhân viên 103 là xóa hàng duy nhất còn lưu tên **Kỹ thuật** và người phụ trách **Hà** của phòng 20.

Một giao dịch **UPDATE ... WHERE department_id = 10** có thể tránh bỏ sót trong một thao tác cụ thể. Nhưng thiết kế vẫn phải đồng bộ cùng một sự thật ở nhiều hàng, kể cả khi dữ liệu được ghi bởi luồng khác, nhập liệu thủ công hoặc tích hợp ngoài. Việc tách phụ thuộc giúp **loại bỏ nghĩa vụ đồng bộ bản sao ngay trong cấu trúc lưu trữ**.

## 3. Định nghĩa 3NF chính xác

Trước khi áp dụng 3NF, cần nắm bốn khái niệm:

| Khái niệm | Diễn giải | Ví dụ trong **employees_flat** |
| --- | --- | --- |
| **Siêu khóa (superkey)** | Tập thuộc tính xác định duy nhất một hàng | **{employee_id}** hoặc một tập chứa nó |
| **Khóa ứng viên (candidate key)** | Siêu khóa tối thiểu, bỏ một thành phần sẽ không còn định danh được hàng | **{employee_id}** |
| **Thuộc tính nguyên tố (prime attribute)** | Thuộc **ít nhất một** khóa ứng viên | **employee_id** |
| **Thuộc tính không nguyên tố (non-prime attribute)** | Không thuộc bất kỳ khóa ứng viên nào | **employee_name**, **department_id**, **department_name**, **department_lead** |

**Định nghĩa hình thức:** một quan hệ **R** ở **3NF** nếu với **mọi phụ thuộc hàm không tầm thường** có dạng **X → A**, trong đó **A** là một thuộc tính, **ít nhất một** trong hai điều kiện sau đúng:

1. **X là siêu khóa của R**; hoặc
2. **A là thuộc tính nguyên tố**, tức nằm trong ít nhất một khóa ứng viên của R.

*Không tầm thường* nghĩa là **A không thuộc X**. Điều kiện được đánh giá trên các phụ thuộc hàm thực sự đúng theo quy tắc nghiệp vụ, bao gồm cả phụ thuộc suy ra từ các quy tắc đã biết.

Tương đương trong cách học thông thường, 3NF bắt đầu từ 2NF và loại bỏ các phụ thuộc bắc cầu không hợp lệ giữa thuộc tính không khóa, nhưng cách nói này là **mẹo nhận diện**, không đủ chính xác cho mọi bảng có nhiều khóa ứng viên.

### 3.1. Áp dụng lên bảng nhân viên

Xét **department_id → department_name**:

- Phụ thuộc này **không tầm thường**: tên phòng không nằm trong vế trái.
- **department_id** không phải siêu khóa của **employees_flat**, vì một phòng có nhiều nhân viên.
- **department_name** không thuộc khóa ứng viên nào, nên là thuộc tính không nguyên tố.

Vì **cả hai điều kiện đều sai**, quan hệ **không đạt 3NF**. Lập luận tương tự áp dụng cho **department_id → department_lead**.

Ngược lại, **employee_id → employee_name, department_id** là các phụ thuộc hợp lệ theo 3NF vì **employee_id** là khóa ứng viên.

## 4. Phân rã theo nơi sở hữu sự thật

Mỗi sự thật cần được lưu tại grain thích hợp:

- **departments**: mỗi hàng là **một phòng ban**, chứa tên và người phụ trách.
- **employees**: mỗi hàng là **một nhân viên**, chứa tên nhân viên và **department_id** tham chiếu phòng.

~~~mermaid
erDiagram
    DEPARTMENTS ||--o{ EMPLOYEES : "có"
    DEPARTMENTS {
        bigint department_id PK
        varchar department_name
        varchar department_lead
    }
    EMPLOYEES {
        bigint employee_id PK
        varchar employee_name
        bigint department_id FK
    }
~~~

### 4.1. Lược đồ SQL có khóa và ràng buộc

~~~sql
CREATE TABLE departments (
    department_id   BIGINT PRIMARY KEY,
    department_name VARCHAR(100) NOT NULL,
    department_lead VARCHAR(100) NOT NULL
);

CREATE TABLE employees (
    employee_id   BIGINT PRIMARY KEY,
    employee_name VARCHAR(100) NOT NULL,
    department_id BIGINT NOT NULL
        REFERENCES departments(department_id)
);

INSERT INTO departments
    (department_id, department_name, department_lead)
VALUES
    (10, 'Kinh doanh', 'Bình'),
    (20, 'Kỹ thuật',   'Hà');

INSERT INTO employees
    (employee_id, employee_name, department_id)
VALUES
    (101, 'An',   10),
    (102, 'Chi',  10),
    (103, 'Dũng', 20);
~~~

Khóa chính của **departments** biểu diễn phụ thuộc **department_id → department_name, department_lead** trong đúng một hàng phòng ban. Khóa chính của **employees** biểu diễn **employee_id → employee_name, department_id**. Khóa ngoại yêu cầu nhân viên tham chiếu tới phòng có thật.

Trong ví dụ tối giản, **department_lead** là tên hiển thị. Nếu người phụ trách là một nhân viên, mô hình thực tế có thể cần **lead_employee_id** làm khóa ngoại cùng quy tắc phù hợp; tên riêng không đủ để định danh một người.

### 4.2. Thử lại ba thao tác

**Thêm phòng ban chưa có nhân viên:**

~~~sql
INSERT INTO departments
    (department_id, department_name, department_lead)
VALUES (30, 'Vận hành', 'Lan');
~~~

**Sửa người phụ trách phòng 10 đúng một bản ghi:**

~~~sql
UPDATE departments
SET department_lead = 'Minh'
WHERE department_id = 10;
~~~

**Xóa nhân viên cuối cùng của phòng 20:**

~~~sql
DELETE FROM employees
WHERE employee_id = 103;

SELECT department_id, department_name
FROM departments
WHERE department_id = 20;
-- Vẫn có phòng 20: Kỹ thuật.
~~~

**Đọc thông tin nhân viên kèm phòng ban:**

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    d.department_id,
    d.department_name,
    d.department_lead
FROM employees AS e
JOIN departments AS d
    ON d.department_id = e.department_id
ORDER BY e.employee_id;
~~~

Phép nối tạo ra *kết quả đọc* gồm các cột như bảng gộp, còn sự thật về phòng ban chỉ được lưu một lần. Muốn hiển thị cả phòng chưa có nhân viên, truy vấn nên bắt đầu từ **departments** và dùng **LEFT JOIN**.

## 5. Kiểm tra phép phân rã: không mất thông tin và bảo toàn phụ thuộc

Không phải cứ chia bảng thành các phần nhỏ hơn là đúng. Một phân rã tốt cần quan tâm tối thiểu hai tính chất:

1. **Nối không mất thông tin (lossless-join decomposition):** khi nối các bảng theo thuộc tính chung dưới các phụ thuộc hợp lệ, ta khôi phục được quan hệ gốc, không tạo bộ giả hay làm mất bộ gốc.
2. **Bảo toàn phụ thuộc (dependency preservation):** những phụ thuộc hàm quan trọng có thể được kiểm soát từ các bảng thành phần, không nhất thiết phải nối toàn bộ dữ liệu để kiểm tra.

### 5.1. Vì sao phép phân rã trong ví dụ là lossless?

Ký hiệu quan hệ gốc có tập thuộc tính:

~~~text
R(employee_id, employee_name,
  department_id, department_name, department_lead)

R1(employee_id, employee_name, department_id)  -- employees
R2(department_id, department_name, department_lead)  -- departments
~~~

Giao của hai tập thuộc tính là **{department_id}**. Phụ thuộc **department_id → department_name, department_lead** cho biết tập thuộc tính chung xác định **toàn bộ R2**. Do đó, theo tiêu chí phân rã nhị phân, **R1 ⋈ R2** là phép nối không mất thông tin đối với mọi trạng thái gốc thỏa phụ thuộc hàm đã nêu.

Mỗi hàng nhân viên khớp **tối đa một** hàng phòng; nếu dữ liệu gốc hợp lệ và khóa ngoại được bảo vệ, nó khớp **đúng một** hàng phòng. Phòng được bổ sung sau này nhưng chưa có nhân viên vẫn có thể nằm trong **departments**; những phòng này không sinh ra hàng nhân viên giả khi dùng **INNER JOIN**.

Một lỗi phân rã dễ gặp là nối bằng một thuộc tính không duy nhất, khiến một hàng ở bảng thứ nhất ghép với nhiều hàng ở bảng thứ hai và tạo kết quả giả. Vì vậy cần xác định phụ thuộc hàm và khóa trước khi tách.

### 5.2. Vì sao các phụ thuộc chính vẫn được bảo toàn?

~~~text
employees:
  employee_id   -> employee_name, department_id

departments:
  department_id -> department_name, department_lead
~~~

Mỗi phụ thuộc được kiểm tra ngay trong một bảng bởi khóa/siêu khóa tương ứng. Hệ quản trị không cần thực hiện phép nối để phát hiện một mã phòng có hai hàng thông tin phòng khác nhau.

Hai tính chất **lossless join** và **dependency preservation** không đồng nghĩa: có phân rã không mất thông tin nhưng khó bảo toàn tất cả phụ thuộc bằng các ràng buộc ở từng bảng. Khi chọn giữa 3NF và các dạng chuẩn chặt hơn, đặc biệt **BCNF**, cần cân nhắc cả hai.

## 6. Trường hợp đặc biệt: 3NF cho phép một số phụ thuộc không có siêu khóa ở vế trái

Câu “mọi thuộc tính không khóa phải phụ thuộc trực tiếp vào khóa” rất hữu ích trong ví dụ đơn giản, nhưng có thể dẫn đến nhận định sai khi bảng có **nhiều khóa ứng viên**.

Xét quan hệ trừu tượng **R(A, B, C)** với các phụ thuộc hàm:

~~~text
AB -> C
C  -> B
~~~

Giả định không có các phụ thuộc hàm nghiệp vụ bổ sung ngoài hệ quả suy diễn của hai quy tắc trên.

### 6.1. Tìm tất cả khóa ứng viên

- **AB** xác định **C**, nên **AB** xác định cả A, B, C và là một khóa ứng viên.
- **AC** xác định **B** qua **C → B**, nên **AC** cũng là một khóa ứng viên.
- Không thuộc tính đơn lẻ nào xác định cả A, B, C.

Các khóa ứng viên là **AB** và **AC**. Cả **A**, **B** lẫn **C** đều là **thuộc tính nguyên tố** vì mỗi thuộc tính thuộc ít nhất một khóa ứng viên.

### 6.2. Đánh giá 3NF và BCNF

Xét **C → B**:

- C **không** phải siêu khóa, bởi C không xác định A.
- B **là thuộc tính nguyên tố**, vì B thuộc khóa ứng viên AB.

Vậy phụ thuộc này **được phép ở 3NF** theo điều kiện “vế phải là thuộc tính nguyên tố”. Quan hệ đạt **3NF** theo các phụ thuộc đã giả định, nhưng **không đạt BCNF**, vì BCNF yêu cầu vế trái của **mọi phụ thuộc hàm không tầm thường** phải là siêu khóa.

| Tiêu chí | 3NF | BCNF |
| --- | --- | --- |
| Phụ thuộc **AB → C** | Hợp lệ: AB là siêu khóa | Hợp lệ: AB là siêu khóa |
| Phụ thuộc **C → B** | Hợp lệ: B là thuộc tính nguyên tố | **Không hợp lệ:** C không phải siêu khóa |

Đây là một ví dụ cho thấy **3NF không tuyệt đối loại bỏ mọi dạng dư thừa**. Nó cho phép một số cấu trúc để thuận lợi hơn cho việc **bảo toàn phụ thuộc**.

Nếu phân rã ví dụ thành **R1(C, B)** và **R2(A, C)**, phép nối là không mất thông tin vì **C → B**, nhưng phụ thuộc **AB → C** không còn được kiểm tra từ một bảng thành phần riêng lẻ. Không nên tùy tiện dùng quy tắc “thấy phụ thuộc thì tách” mà bỏ qua các ràng buộc cần duy trì.

## 7. Quy trình chuẩn hóa lên 3NF khi thiết kế thực tế

### Bước 1: Xác định grain và thuộc tính

Hỏi một hàng biểu diễn **một nhân viên**, **một lần giao dịch**, **một sản phẩm**, hay **một dòng hàng**. Cùng tên cột chưa chắc cùng ý nghĩa thời gian hoặc cùng quy tắc xác định.

### Bước 2: Liệt kê các phụ thuộc hàm nghiệp vụ

Ghi rõ các quy tắc như **department_id → department_name**; không suy từ dữ liệu mẫu đơn thuần. Đặt câu hỏi liệu một mã phòng có được phép đổi tên theo thời gian, một nhân viên có được đồng thời thuộc nhiều phòng hay một mã sản phẩm có tái sử dụng không.

### Bước 3: Tìm mọi khóa ứng viên và đánh dấu thuộc tính nguyên tố

Đừng chỉ nhìn **PRIMARY KEY**. Một bảng có khóa thay thế **id** vẫn có thể chứa khóa ứng viên nghiệp vụ ghép, ví dụ **(order_id, line_no)** được bảo vệ bởi **UNIQUE** và **NOT NULL**. Việc thêm **id** không tự làm biến mất phụ thuộc hàm hay làm bảng đạt 3NF.

### Bước 4: Áp dụng điều kiện 3NF

Với mỗi phụ thuộc không tầm thường **X → A**, kiểm tra:

1. **X có là siêu khóa?** Nếu có, phụ thuộc thỏa điều kiện.
2. Nếu không, **A có thuộc ít nhất một khóa ứng viên?** Nếu có, phụ thuộc vẫn được phép ở 3NF.
3. Nếu cả hai đều không, đó là vi phạm 3NF cần xử lý.

Đừng đánh giá 3NF chỉ bằng việc xem A “có nằm trong khóa chính hay không”; **thuộc tính nguyên tố** được xác định từ **tất cả khóa ứng viên**.

### Bước 5: Phân rã và đặt ràng buộc

Đưa các thuộc tính mà **department_id** xác định sang bảng **departments**; giữ **department_id** làm khóa ngoại tại **employees**. Lựa chọn khóa phù hợp và áp dụng **NOT NULL**, **CHECK**, **UNIQUE** và khóa ngoại theo nghiệp vụ. Nếu muốn dùng thuật toán tổng hợp lược đồ 3NF cho một tập phụ thuộc phức tạp, có thể:

1. Tìm một **phủ tối thiểu** của các phụ thuộc hàm.
2. Tạo các quan hệ bao phủ các phụ thuộc của phủ, gộp các quan hệ phù hợp có cùng vế xác định.
3. Loại các quan hệ có tập thuộc tính nằm hoàn toàn trong một quan hệ khác khi việc đó phù hợp.
4. Nếu chưa có quan hệ nào chứa **một khóa ứng viên** của quan hệ gốc, thêm một quan hệ chứa khóa ứng viên.

Với các điều kiện và cách dựng chuẩn của thuật toán tổng hợp 3NF, kết quả hướng tới **nối không mất thông tin và bảo toàn các phụ thuộc hàm**. Trong dự án thực tế vẫn cần đối chiếu với ngữ nghĩa nghiệp vụ, khóa ngoại và các ràng buộc không biểu đạt được chỉ bằng phụ thuộc hàm.

### Bước 6: Kiểm tra thao tác và nhu cầu vật lý

Thử thêm một thực thể chưa có quan hệ con, đổi thông tin ở một nơi, xóa bản ghi cuối cùng và truy vấn tổng hợp sau phân rã. Tiếp đó đánh giá các phép nối phổ biến và chỉ mục cần thiết; lựa chọn chỉ mục không thay thế thiết kế quan hệ đúng.

Ví dụ, nếu ứng dụng thường lọc nhân viên theo phòng, có thể cân nhắc:

~~~sql
CREATE INDEX idx_employees_department_id
ON employees (department_id);
~~~

Chỉ mục này hỗ trợ truy vấn có điều kiện theo **department_id** và có thể hỗ trợ phép nối; hiệu quả thực tế phải được đánh giá bằng kế hoạch truy vấn và kích thước dữ liệu.

## 8. Phân biệt phụ thuộc cần tách với dữ liệu lịch sử có chủ đích

Đôi khi hai cột nhìn như dư thừa nhưng lại diễn tả **những sự thật ở các thời điểm khác nhau**.

Giả sử **products(product_id, current_price)** chứa giá hiện tại và **order_lines(order_id, line_no, product_id, unit_price_at_order)** lưu giá đã chốt khi đặt hàng. Không nên gán phụ thuộc **product_id → unit_price_at_order** chỉ vì nhiều đơn hàng có thể cùng sản phẩm: giá lúc mua có thể phụ thuộc thời điểm, chương trình giảm giá hoặc hợp đồng cụ thể.

| Tình huống | Chủ sở hữu thông tin | Cách xem xét |
| --- | --- | --- |
| Tên phòng ban hiện hành trên mọi nhân viên | Phòng ban | Chuyển sang **departments** để có một nguồn chuẩn |
| Giá niêm yết hiện hành của sản phẩm | Sản phẩm hoặc bảng giá có hiệu lực | Đặt ở thực thể/quy tắc giá phù hợp |
| Giá đơn hàng đã chốt | Dòng hàng hoặc điều khoản giao dịch | Giữ như một sự thật lịch sử của giao dịch |
| Bản sao dữ liệu trong bảng đọc/phân tích | Nguồn nghiệp vụ gốc và pipeline đồng bộ | Có thể phi chuẩn hóa có chủ đích, nhưng phải xác định nguồn chuẩn và độ trễ chấp nhận được |

Với dữ liệu có lịch sử hiệu lực, phụ thuộc hàm có thể cần bao gồm yếu tố thời gian hoặc phiên bản, ví dụ **(department_id, effective_from) → department_name** trong một thiết kế lịch sử có quy tắc thời gian rõ ràng. Không áp đặt phụ thuộc của trạng thái hiện tại lên toàn bộ bản ghi lịch sử.

3NF đánh giá **một quan hệ cùng các phụ thuộc hàm nghiệp vụ của nó**. Mô hình document, đồ thị hoặc kho phân tích có thể lựa chọn cấu trúc khác vì kiểu truy vấn và cách cập nhật khác nhau; việc so sánh nên dựa trên ràng buộc, nguồn dữ liệu chuẩn, chi phí ghi/đọc và khả năng tiến hóa.

## 9. Bài tập: đơn hàng và thông tin khách hàng

Xét bảng:

| order_id | order_date | customer_id | customer_name | customer_tier |
| --- | --- | --- | --- | --- |
| O01 | 2026-11-20 | C01 | An | GOLD |
| O02 | 2026-11-21 | C01 | An | GOLD |
| O03 | 2026-11-21 | C02 | Bình | SILVER |

Giả định:

- **order_id** xác định một đơn hàng, ngày đặt và khách hàng đặt đơn.
- **customer_id** xác định tên và hạng thành viên **hiện hành**.
- Một khách hàng có thể đặt nhiều đơn; hạng thành viên có thể thay đổi mà không cần thay đổi bản ghi đơn hàng.

**Yêu cầu:**

1. Xác định grain và khóa ứng viên của bảng; giải thích vì sao bảng có thể đạt 2NF.
2. Viết các phụ thuộc hàm quan trọng. Phụ thuộc nào vi phạm định nghĩa 3NF và vì sao?
3. Nêu một tình huống thêm, sửa hoặc xóa có thể gây bất thường.
4. Phân rã thành bảng **customers** và **orders**, ghi khóa chính và khóa ngoại.
5. Nếu nghiệp vụ cần biết **hạng thành viên đúng tại lúc đặt đơn**, có nên tiếp tục cập nhật hạng này khi khách hàng đổi hạng không?

<details>
<summary>Gợi ý lời giải</summary>

Grain là **một đơn hàng**; khóa ứng viên theo giả định là **order_id** (một thuộc tính), nên không có phụ thuộc bộ phận kiểu thông thường và có thể thỏa 2NF.

~~~text
order_id    -> order_date, customer_id
customer_id -> customer_name, customer_tier
~~~

Phụ thuộc **customer_id → customer_name, customer_tier** vi phạm 3NF trong bảng gộp: **customer_id** không phải siêu khóa và hai thuộc tính vế phải là không nguyên tố. Khi khách hàng C01 đổi hạng, nếu chỉ sửa O01 thì O02 còn hạng cũ. Khi chưa có đơn nào, bảng không biểu diễn được khách hàng mới.

Một cách phân rã:

~~~sql
CREATE TABLE customers (
    customer_id   VARCHAR(10) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    customer_tier VARCHAR(20) NOT NULL
);

CREATE TABLE orders (
    order_id     VARCHAR(10) PRIMARY KEY,
    order_date   DATE NOT NULL,
    customer_id  VARCHAR(10) NOT NULL
        REFERENCES customers(customer_id)
);
~~~

Nếu cần biết hạng **ở thời điểm đặt hàng**, nên mô hình hóa rõ **tier_at_order** như một sự thật lịch sử của đơn, hoặc dùng dữ liệu lịch sử hạng với khoảng hiệu lực thích hợp. **Không** tự cập nhật giá trị lịch sử theo hạng hiện tại. Cần quyết định theo yêu cầu kiểm toán và báo cáo.

</details>

## 10. Các nhầm lẫn cần tránh

| Nhận định | Điều cần nhớ |
| --- | --- |
| “Đã ở 2NF là không còn bất thường.” | 2NF chủ yếu loại bỏ phụ thuộc bộ phận vào khóa ứng viên; phụ thuộc bắc cầu gây dư thừa vẫn có thể tồn tại. |
| “Mọi phụ thuộc bắc cầu đều vi phạm 3NF.” | Phải xét **định nghĩa hình thức**: X là siêu khóa hoặc A là thuộc tính nguyên tố; không kết luận chỉ từ hình dạng chuỗi phụ thuộc. |
| “Chỉ cần kiểm tra các cột không thuộc khóa chính.” | Một thuộc tính có thể thuộc **khóa ứng viên khác** nên vẫn là thuộc tính nguyên tố. |
| “Thêm khóa ID đơn là đạt 3NF.” | Khóa thay thế không thay đổi các phụ thuộc hàm nghiệp vụ đang có. |
| “Đổi kiểu cột hoặc thêm chỉ mục sẽ giải quyết phụ thuộc bắc cầu.” | Kiểu dữ liệu và chỉ mục không đưa thông tin về đúng thực thể sở hữu nó. |
| “Tách càng nhiều bảng càng tốt.” | Phân rã phải kiểm tra **lossless join**, bảo toàn phụ thuộc và mục tiêu nghiệp vụ. |
| “Hai giá trị giống nhau ở nhiều bảng luôn sai.” | Dữ liệu lịch sử, ảnh chụp giao dịch và bản sao đọc có thể có ngữ nghĩa riêng, cần quản lý nguồn chuẩn và đồng bộ. |

## 11. Ghi nhớ

**3NF** yêu cầu mỗi phụ thuộc hàm không tầm thường **X → A** thỏa **X là siêu khóa** hoặc **A là thuộc tính nguyên tố**. Trong các lược đồ nghiệp vụ có khóa ứng viên đơn giản, dấu hiệu quen thuộc là một thuộc tính như **department_name** phụ thuộc vào **department_id** thay vì thuộc về nhân viên; tách bảng phòng ban giúp loại bỏ sao chép và giảm bất thường thêm, sửa, xóa.

Thiết kế tốt bắt đầu từ **grain, khóa ứng viên, phụ thuộc hàm và ngữ nghĩa thời gian**, rồi mới phân rã và đặt ràng buộc. Kiểm tra **nối không mất thông tin** và **bảo toàn phụ thuộc** trước khi hoàn thiện lược đồ vật lý; sau đó mới tối ưu chỉ mục hoặc cân nhắc phi chuẩn hóa có chủ đích. **3NF là tiêu chí rõ ràng để kiểm chứng cấu trúc quan hệ, không phải lời hứa loại bỏ mọi rủi ro dữ liệu trong mọi mô hình.**
