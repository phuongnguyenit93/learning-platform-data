# Bất thường khi thêm, sửa hoặc xóa và nguồn gốc từ dữ liệu dư thừa

Một bảng có thể dễ truy vấn ở giai đoạn đầu nhưng trở nên khó duy trì khi cùng một sự thật nghiệp vụ được lưu ở nhiều hàng. Chỉ cần một thao tác thêm, cập nhật hoặc xóa không xử lý hết những bản sao đó, dữ liệu có thể thiếu, mâu thuẫn hoặc mất đi ngoài ý muốn. Đây là ba **bất thường dữ liệu** (*insertion, update, deletion anomalies*) thường dùng để lý giải vì sao cần chuẩn hóa mô hình quan hệ.

Trong thiết kế dữ liệu, mục tiêu không chỉ là lưu được trạng thái hiện tại mà còn là **biểu diễn đúng các sự thật nghiệp vụ, cho phép chúng thay đổi độc lập và giữ được ràng buộc nhất quán**. Bài học này đi từ ví dụ thực tế, nhận diện nguyên nhân, rồi phân rã lược đồ để khắc phục.

## 1. Bài toán: lưu nhân viên cùng thông tin phòng ban

Giả sử hệ thống nhân sự có các quy tắc:

- Mỗi nhân viên thuộc một phòng ban tại một thời điểm.
- Mỗi phòng ban có mã, tên và người quản lý riêng.
- Một phòng ban vẫn có thể tồn tại khi chưa có nhân viên.
- Khi đổi tên hoặc đổi người quản lý phòng ban, thay đổi đó áp dụng cho toàn bộ nhân viên thuộc phòng ban.

Thiết kế ban đầu gộp mọi thông tin vào một bảng; **mỗi hàng đại diện cho một nhân viên**:

| employee_id | employee_name | department_id | department_name | department_manager |
| ---: | --- | ---: | --- | --- |
| 101 | An | 10 | Kinh doanh | Bình |
| 102 | Chi | 10 | Kinh doanh | Bình |
| 103 | Dũng | 20 | Kỹ thuật | Hà |

Ví dụ SQL (cú pháp tương thích PostgreSQL):

~~~sql
CREATE TABLE employee_department_flat (
    employee_id         BIGINT PRIMARY KEY,
    employee_name       VARCHAR(100) NOT NULL,
    department_id       BIGINT NOT NULL,
    department_name     VARCHAR(100) NOT NULL,
    department_manager  VARCHAR(100) NOT NULL
);

INSERT INTO employee_department_flat
    (employee_id, employee_name, department_id,
     department_name, department_manager)
VALUES
    (101, 'An',   10, 'Kinh doanh', 'Bình'),
    (102, 'Chi',  10, 'Kinh doanh', 'Bình'),
    (103, 'Dũng', 20, 'Kỹ thuật',   'Hà');
~~~

Lợi điểm trước mắt là lấy thông tin nhân viên và phòng ban mà không cần phép nối. Đổi lại, các thông tin **Kinh doanh** và **Bình** xuất hiện một lần cho *mỗi* nhân viên phòng 10, dù thực tế chỉ có một phòng ban với một bộ thông tin hiện hành.

Đáng chú ý: việc nhiều nhân viên cùng có mã phòng ban **10** không tự nó là lỗi. Mã phòng ban là tham chiếu cần thiết để diễn tả quan hệ. Vấn đề nằm ở việc **tên phòng và người quản lý, vốn thuộc về phòng ban**, lại được sao chép vào từng bản ghi nhân viên.

## 2. Ba loại bất thường

### 2.1. Bất thường khi thêm (insertion anomaly)

**Nhu cầu:** tạo phòng ban mới có mã **30**, tên **Vận hành**, người quản lý **Lan**, nhưng phòng ban này chưa tuyển nhân viên.

Trong bảng gộp, không thể thêm riêng thông tin phòng ban vì mỗi hàng buộc phải có **employee_id** làm khóa chính. Lệnh minh họa sau sẽ bị từ chối:

~~~sql
-- Minh họa lỗi: employee_id là khóa chính nên không được NULL.
INSERT INTO employee_department_flat
    (employee_id, employee_name, department_id,
     department_name, department_manager)
VALUES
    (NULL, 'Chưa có nhân viên', 30, 'Vận hành', 'Lan');
~~~

Nếu tạo một “nhân viên giả” để lấp khóa chính, hệ thống lại chứa dữ liệu không đúng nghiệp vụ. Nếu chờ đến khi có nhân viên mới ghi phòng ban, hệ thống không thể biểu diễn một phòng ban đang tồn tại nhưng chưa có thành viên.

**Bản chất:** sự tồn tại của thực thể *phòng ban* bị buộc phụ thuộc vào sự tồn tại của thực thể *nhân viên*, trái với yêu cầu nghiệp vụ.

### 2.2. Bất thường khi sửa (update anomaly)

**Nhu cầu:** thay người quản lý phòng **10** từ **Bình** thành **Minh**.

Thiết kế gộp buộc ứng dụng phải sửa *tất cả* hàng nhân viên của phòng 10. Nếu chỉ sửa hàng của An, ta có:

| employee_id | department_id | department_manager |
| ---: | ---: | --- |
| 101 | 10 | Minh |
| 102 | 10 | Bình |

Đây là kết quả của tình huống sau, thử độc lập trên dữ liệu mẫu:

~~~sql
BEGIN;

UPDATE employee_department_flat
SET department_manager = 'Minh'
WHERE employee_id = 101;

SELECT employee_id, department_id, department_manager
FROM employee_department_flat
WHERE department_id = 10
ORDER BY employee_id;

ROLLBACK;
~~~

Cùng một **department_id = 10** nhưng có hai giá trị quản lý. Hệ thống không thể biết đâu là giá trị đúng nếu chỉ nhìn vào dữ liệu. Một lệnh cập nhật theo **department_id** có thể sửa đủ các hàng trong một lần, nhưng thiết kế vẫn bắt buộc mọi luồng ghi dữ liệu phải nhớ quy tắc “sửa đồng thời mọi bản sao”; các lần nhập liệu, tích hợp hay sửa thủ công đều có nguy cơ bỏ sót.

**Bản chất:** một thay đổi của *một sự thật* phải được phản ánh trên *nhiều vị trí lưu trữ*.

### 2.3. Bất thường khi xóa (deletion anomaly)

**Nhu cầu:** nhân viên Dũng (mã **103**) nghỉ việc. Dũng đang là nhân viên cuối cùng của phòng **20**.

~~~sql
BEGIN;

DELETE FROM employee_department_flat
WHERE employee_id = 103;

SELECT *
FROM employee_department_flat
WHERE department_id = 20;
-- Không còn hàng nào.

ROLLBACK;
~~~

Xóa nhân viên làm mất luôn tên phòng **Kỹ thuật** và người quản lý **Hà** vì đó là bản ghi duy nhất chứa hai thông tin này. Sau khi xóa, bảng không còn cho biết phòng 20 từng tồn tại hay hiện vẫn hoạt động mà chưa có nhân viên.

**Bản chất:** xóa một thực thể kéo theo xóa ngoài ý muốn thông tin của một thực thể khác.

### 2.4. So sánh nhanh

| Loại bất thường | Thao tác hợp lệ mong muốn | Hậu quả do bảng gộp | Nguyên nhân gần nhất |
| --- | --- | --- | --- |
| **Thêm** | Tạo phòng ban chưa có nhân viên | Không thể biểu diễn nếu không tạo nhân viên giả | Dữ liệu phòng ban phụ thuộc vào hàng nhân viên |
| **Sửa** | Đổi một người quản lý phòng ban | Nhiều hàng có thể lưu các giá trị trái nhau | Một sự thật có nhiều bản sao cần đồng bộ |
| **Xóa** | Xóa nhân viên cuối cùng | Mất cả thông tin phòng ban | Hai thực thể có vòng đời khác nhau bị gộp chung |

Các bất thường này là **rủi ro cấu trúc**. Bảng chưa từng có giá trị mâu thuẫn không chứng minh rằng thiết kế đã an toàn; sự cố có thể chỉ xuất hiện khi gặp một tình huống thay đổi dữ liệu cụ thể.

## 3. Nguồn gốc: dữ liệu dư thừa và phụ thuộc hàm

### 3.1. Phải xác định “mỗi hàng nói về điều gì”

Trong ví dụ trên, mức chi tiết (*grain*) của hàng là **một nhân viên**. Nhưng một số cột mô tả nhân viên, một số khác lại mô tả phòng ban:

- **employee_id → employee_name, department_id**: mã nhân viên xác định tên và phòng ban hiện tại của nhân viên.
- **department_id → department_name, department_manager**: mã phòng ban xác định tên và người quản lý hiện tại của phòng.

Ký hiệu **X → Y** là *phụ thuộc hàm*: với một giá trị X xác định, chỉ có một giá trị Y hợp lệ trong trạng thái dữ liệu mà quy tắc nghiệp vụ đang xét. Đây là một phát biểu về nghiệp vụ, không phải kết luận chỉ vì vài dòng dữ liệu tình cờ giống nhau.

Từ hai quy tắc, có chuỗi phụ thuộc:

~~~text
employee_id
    |---> employee_name
    |
    +---> department_id
               |---> department_name
               +---> department_manager
~~~

Tên phòng ban và người quản lý phụ thuộc vào **department_id**, thay vì phụ thuộc trực tiếp vào bản thân nhân viên. Trong bảng có khóa ứng viên là **employee_id**, đây là phụ thuộc bắc cầu từ khóa đến các thuộc tính không khóa thông qua **department_id**, dấu hiệu điển hình của việc chưa đạt **dạng chuẩn 3 (3NF)**. Với khóa chính chỉ có một cột, bảng này có thể vẫn thỏa **2NF**; không nên nhầm mọi dạng dư thừa với vi phạm 2NF.

Điều quan trọng là **mỗi sự thật nghiệp vụ nên có một nơi quản lý có thẩm quyền**. Nếu mỗi tên phòng chỉ được lưu một lần trong bản ghi phòng ban, việc đổi tên trở thành một thao tác trên đúng thực thể sở hữu thông tin đó.

### 3.2. Không phải mọi giá trị lặp lại đều là dư thừa có hại

Phân biệt ba tình huống:

1. **Tham chiếu lặp lại có chủ đích:** nhiều nhân viên cùng lưu **department_id = 10** để chỉ ra cùng thuộc về phòng 10. Đây là quan hệ bình thường trong mô hình quan hệ.
2. **Thuộc tính mô tả bị sao chép:** mỗi nhân viên cùng lưu **department_name = Kinh doanh** dù tên này thuộc về phòng 10. Đây là nguồn rủi ro bất thường khi sửa.
3. **Bản ghi lịch sử tại thời điểm khác nhau:** một đơn hàng giữ tên sản phẩm hoặc đơn giá *tại lúc chốt đơn* để đối soát sau này. Giá trị này có thể khác dữ liệu sản phẩm hiện tại vì hai cột phản ánh **hai sự thật theo thời gian**, không đơn thuần là hai bản sao cần cập nhật đồng loạt.

Muốn kết luận có dư thừa gây bất thường hay không, cần trả lời: **Ai sở hữu thuộc tính? Thuộc tính mô tả thời điểm nào? Quy tắc nào bắt buộc những hàng khác nhau phải giống nhau?**

## 4. Khắc phục bằng cách tách thực thể và ràng buộc rõ ràng

Vì thông tin phòng ban có vòng đời độc lập, tách bảng thành:

- **departments:** mỗi hàng là một phòng ban; lưu mã, tên và người quản lý.
- **employees:** mỗi hàng là một nhân viên; lưu thông tin riêng và khóa ngoại trỏ tới phòng ban.

~~~mermaid
erDiagram
    DEPARTMENTS ||--o{ EMPLOYEES : "có"
    DEPARTMENTS {
        bigint department_id PK
        varchar department_name
        varchar department_manager
    }
    EMPLOYEES {
        bigint employee_id PK
        varchar employee_name
        bigint department_id FK
    }
~~~

Ví dụ lược đồ:

~~~sql
CREATE TABLE departments (
    department_id      BIGINT PRIMARY KEY,
    department_name    VARCHAR(100) NOT NULL,
    department_manager VARCHAR(100) NOT NULL
);

CREATE TABLE employees (
    employee_id   BIGINT PRIMARY KEY,
    employee_name VARCHAR(100) NOT NULL,
    department_id BIGINT NOT NULL
        REFERENCES departments(department_id)
);

INSERT INTO departments
    (department_id, department_name, department_manager)
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

Khóa chính của **departments** bảo đảm mỗi mã phòng chỉ có một hàng chứa thông tin phòng đó. Khóa ngoại của **employees** bảo đảm nhân viên tham chiếu tới phòng ban có thật. Các ràng buộc này thể hiện trực tiếp các quy tắc nghiệp vụ thay vì giao hoàn toàn trách nhiệm đồng bộ cho mã ứng dụng.

### 4.1. Thử lại ba thao tác

**Thêm phòng chưa có nhân viên:**

~~~sql
INSERT INTO departments
    (department_id, department_name, department_manager)
VALUES (30, 'Vận hành', 'Lan');
-- Hợp lệ dù chưa có hàng nào trong employees trỏ tới phòng 30.
~~~

**Đổi người quản lý:** chỉ có một giá trị cần sửa.

~~~sql
UPDATE departments
SET department_manager = 'Minh'
WHERE department_id = 10;
~~~

**Xóa nhân viên cuối cùng của phòng:** thông tin phòng ban vẫn còn.

~~~sql
DELETE FROM employees
WHERE employee_id = 103;

SELECT department_id, department_name
FROM departments
WHERE department_id = 20;
-- Vẫn trả về phòng 20: Kỹ thuật.
~~~

Ba ví dụ này có thể chạy lần lượt trên dữ liệu đã tạo ở mục 4. Hệ quản trị còn có thể chặn việc xóa **phòng ban** đang được nhân viên tham chiếu theo hành vi khóa ngoại mặc định; nếu nghiệp vụ muốn chuyển phòng, đóng phòng hay xóa dây chuyền, phải định nghĩa quy tắc riêng.

### 4.2. Khi cần thông tin đầy đủ, dùng phép nối

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    d.department_id,
    d.department_name,
    d.department_manager
FROM employees AS e
JOIN departments AS d
    ON d.department_id = e.department_id
ORDER BY e.employee_id;
~~~

Phép nối có thể tạo ra một **kết quả truy vấn** giống bảng gộp ban đầu ở mức từng nhân viên, nhưng dữ liệu gốc của phòng ban vẫn chỉ được lưu một lần. Việc phân rã này không làm mất thông tin của nhân viên nếu khóa ngoại hợp lệ và **department_id** là khóa duy nhất của bảng phòng ban.

Để nhìn thấy cả những phòng chưa có nhân viên, truy vấn từ **departments** bằng **LEFT JOIN**:

~~~sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM departments AS d
LEFT JOIN employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
~~~

Phòng **30** sẽ xuất hiện với **employee_count = 0**. Đây là khả năng biểu diễn mà bảng gộp không có.

## 5. Nhận diện sớm bằng truy vấn và câu hỏi thiết kế

Trong dữ liệu cũ, có thể kiểm tra xem cùng một mã phòng đã chứa nhiều tên hay nhiều quản lý hay chưa:

~~~sql
SELECT
    department_id,
    COUNT(*) AS employee_rows,
    COUNT(DISTINCT department_name) AS distinct_names,
    COUNT(DISTINCT department_manager) AS distinct_managers
FROM employee_department_flat
GROUP BY department_id
HAVING COUNT(DISTINCT department_name) > 1
    OR COUNT(DISTINCT department_manager) > 1;
~~~

Truy vấn trả về những phòng có dấu hiệu mâu thuẫn giữa các hàng. Tuy nhiên, **không có hàng kết quả không đồng nghĩa thiết kế an toàn**: dữ liệu hiện tại có thể tình cờ nhất quán. Truy vấn này cũng không tìm được phòng ban chưa có nhân viên, vì bảng gộp vốn không lưu nổi trường hợp đó.

Khi xem xét một bảng, hãy thử những câu hỏi sau:

1. **Grain:** mỗi hàng đại diện cho thực thể hay sự kiện nào?
2. **Chủ sở hữu thông tin:** tên, trạng thái và thuộc tính trong hàng thực sự thuộc về thực thể nào?
3. **Thêm độc lập:** có thể tạo một thực thể A khi chưa có thực thể B liên quan không?
4. **Sửa một lần:** đổi một thông tin nghiệp vụ có buộc sửa nhiều hàng không?
5. **Xóa an toàn:** xóa hàng cuối cùng của một nhóm có làm mất thông tin vẫn cần giữ không?
6. **Ràng buộc:** khóa chính, khóa ngoại, điều kiện duy nhất và các phụ thuộc hàm đã phản ánh đúng quy tắc chưa?
7. **Thời gian:** hai giá trị giống nhau là bản sao của trạng thái hiện tại hay là các ảnh chụp lịch sử có ý nghĩa độc lập?

### Những cách xử lý dễ gây hiểu nhầm

| Cách làm | Tại sao chưa giải quyết tận gốc |
| --- | --- |
| Dùng **SELECT DISTINCT** để giấu hàng trùng | Chỉ xử lý kết quả đọc, không sửa cấu trúc lưu dữ liệu hay rủi ro khi ghi |
| Thêm **UNIQUE (department_id, department_name)** vào bảng gộp | Vừa cấm nhiều nhân viên cùng phòng với cùng tên phòng, vừa không chứng minh rằng một mã phòng chỉ có một tên trên các hàng khác nhau |
| Bọc mọi cập nhật trong transaction | Transaction làm thao tác đã viết có tính nguyên tử, nhưng không tự biết rằng chương trình đã bỏ quên một bản sao |
| Chỉ kiểm tra dữ liệu hiện tại không có mâu thuẫn | Không kiểm tra được khả năng thêm phòng rỗng hoặc mất phòng khi xóa nhân viên cuối |
| Tách bảng mà bỏ qua khóa ngoại | Có thể loại bỏ sao chép thuộc tính nhưng lại tạo tham chiếu tới phòng ban không tồn tại |

Khi chuẩn hóa, cũng cần kiểm tra các ràng buộc mới. Ví dụ, nếu **người quản lý** là một nhân viên trong hệ thống, thuộc tính quản lý có thể nên là **manager_employee_id** tham chiếu đến nhân viên, kèm quy tắc quản lý phù hợp. Chỉ dùng tên người tự do như ví dụ tối giản không đủ để bảo đảm danh tính người quản lý trong hệ thống thực tế.

## 6. Khi nào chủ động chấp nhận dữ liệu dư thừa?

Chuẩn hóa giúp giảm bất thường khi ghi, nhưng có những trường hợp giữ dữ liệu lặp lại là quyết định hợp lý:

- **Bảng đọc tối ưu / materialized view:** sao chép tên phòng vào mô hình phục vụ báo cáo để giảm số phép nối. Cần xác định nguồn dữ liệu chuẩn và quy trình làm mới, đối soát hoặc tái tạo.
- **Ảnh chụp lịch sử:** giữ tên sản phẩm và đơn giá tại thời điểm đặt hàng; bản ghi giao dịch phản ánh sự kiện quá khứ và không nhất thiết thay đổi theo danh mục hiện tại.
- **Kho phân tích:** mô hình chiều hoặc bảng dữ liệu đã làm phẳng có thể ưu tiên tốc độ tổng hợp, đổi lại yêu cầu pipeline đồng bộ và quy định rõ thời điểm dữ liệu có hiệu lực.

Trong các trường hợp này, cần làm rõ **nguồn chân lý**, **thời điểm hiệu lực**, **cách cập nhật**, **độ trễ được chấp nhận** và **cách phát hiện sai lệch**. Việc nhân bản dữ liệu có chủ đích và có cơ chế bảo trì khác với nhân bản ngẫu nhiên khiến mọi thao tác nghiệp vụ phải đồng bộ thủ công.

## 7. Bài tập vận dụng

Xét bảng đăng ký học:

| student_id | student_name | course_id | course_name | lecturer |
| ---: | --- | --- | --- | --- |
| 1 | Mai | C01 | SQL căn bản | Thảo |
| 2 | Nam | C01 | SQL căn bản | Thảo |
| 1 | Mai | C02 | Thiết kế dữ liệu | Phúc |

Giả định **mỗi sinh viên có một tên hiện hành**, **mỗi khóa học có một tên và một giảng viên hiện hành**, một sinh viên có thể tham gia nhiều khóa và khóa học có thể chưa có học viên.

**Yêu cầu:**

1. Tìm một tình huống thêm, một tình huống sửa và một tình huống xóa có thể gây bất thường.
2. Nêu các phụ thuộc hàm cơ bản và xác định khóa thích hợp cho bản ghi đăng ký.
3. Đề xuất các bảng, khóa chính và khóa ngoại để vẫn lưu được khóa học chưa có người đăng ký.

<details>
<summary>Gợi ý lời giải</summary>

- **Thêm:** chưa có học viên thì không thể tạo dòng chỉ để đăng ký khóa C03. **Sửa:** đổi giảng viên C01 phải sửa mọi lượt đăng ký C01. **Xóa:** xóa lượt đăng ký cuối cùng của C02 có thể làm mất thông tin khóa C02.
- Phụ thuộc hàm: **student_id → student_name**; **course_id → course_name, lecturer**. Nếu một sinh viên đăng ký một khóa nhiều nhất một lần, cặp **(student_id, course_id)** xác định bản ghi đăng ký.
- Tách thành **students(student_id PK, student_name)**, **courses(course_id PK, course_name, lecturer)** và **enrollments(student_id FK, course_id FK, PRIMARY KEY(student_id, course_id))**. Bảng **courses** tồn tại độc lập với **enrollments**, nên có thể giữ khóa chưa có học viên.

</details>

## 8. Điều cần ghi nhớ

**Bất thường khi thêm** khiến không thể biểu diễn một sự thật độc lập; **bất thường khi sửa** khiến nhiều bản sao của một sự thật có thể mâu thuẫn; **bất thường khi xóa** làm mất thông tin ngoài ý muốn. Căn nguyên thường là đặt thuộc tính của nhiều thực thể, với các phụ thuộc hàm và vòng đời khác nhau, vào một bảng có mức chi tiết không phù hợp.

Khi thiết kế mô hình dữ liệu quan hệ, hãy xác định thực thể, grain và phụ thuộc hàm trước; sau đó đặt mỗi thuộc tính dưới thực thể sở hữu nó, dùng khóa để liên kết và ràng buộc để bảo vệ tính đúng đắn. Có thể phi chuẩn hóa vì hiệu năng hoặc lịch sử, nhưng đó phải là một lựa chọn được giải thích và kiểm soát, không phải cách sửa tạm sự bất nhất trong thiết kế.
