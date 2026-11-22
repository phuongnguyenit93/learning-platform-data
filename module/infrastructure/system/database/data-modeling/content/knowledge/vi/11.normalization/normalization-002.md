# Dạng chuẩn thứ nhất và ý nghĩa tính nguyên tử theo miền dữ liệu

**Dạng chuẩn thứ nhất (First Normal Form, 1NF)** là nền tảng để biểu diễn dữ liệu dưới dạng các quan hệ có hàng, thuộc tính và giá trị rõ ràng. Trong cách diễn giải thực hành phổ biến, một cột tại một hàng phải biểu diễn **một giá trị thuộc miền dữ liệu đã xác định**, thay vì giấu cả danh sách các giá trị nghiệp vụ trong cùng một ô. Tuy nhiên, “một giá trị” không có nghĩa là giá trị ấy không thể chia nhỏ về mặt kỹ thuật: **tính nguyên tử phụ thuộc vào ngữ nghĩa và miền dữ liệu mà hệ thống cần xử lý**.

Bài học thuộc chương **Chuẩn hóa** của mô hình hóa dữ liệu. Mục tiêu là biết nhận diện những cấu trúc khiến việc truy vấn, ràng buộc và cập nhật dữ liệu trở nên khó kiểm soát; sau đó lựa chọn bảng, khóa và quan hệ phù hợp. Đây là bước cơ sở trước khi xét phụ thuộc hàm, 2NF, 3NF, chỉ mục, mô hình vật lý hay cân nhắc giữa cơ sở dữ liệu quan hệ và document.

## 1. Mỗi hàng đại diện cho điều gì, mỗi cột mang giá trị gì?

Một quan hệ được mô tả bằng các thuộc tính với miền giá trị xác định. Chẳng hạn:

- **customer_id**: định danh khách hàng, thuộc miền các mã khách hàng hợp lệ.
- **customer_name**: tên khách hàng, thuộc miền chuỗi tên phù hợp quy tắc hệ thống.
- **phone_e164**: một số điện thoại theo biểu diễn chuẩn E.164, ví dụ **+84901234567**.
- **registered_at**: một thời điểm đăng ký, thuộc miền các giá trị thời gian.

Với một bảng có mức chi tiết (*grain*) là **một khách hàng trên mỗi hàng**, những thông tin như tên hoặc thời điểm đăng ký có thể được đặt trực tiếp trong bảng khách hàng. Nhưng nếu một khách hàng có **0, 1 hoặc nhiều số điện thoại**, tập hợp số điện thoại là một quan hệ một-nhiều cần được mô hình hóa rõ ràng.

Xét bảng đầu vào:

| customer_id | customer_name | phone_numbers |
| ---: | --- | --- |
| 101 | An | +84901234567, +84909876543 |
| 102 | Bình | +84907654321 |
| 103 | Chi | *(trống)* |

Ở đây **phone_numbers** chứa danh sách, dù được lưu dưới dạng một chuỗi văn bản. Các câu hỏi tưởng như đơn giản bắt đầu khó trả lời:

- Có bao nhiêu số điện thoại liên hệ của khách hàng 101?
- Số **+84909876543** thuộc những khách hàng nào?
- Làm sao ngăn nhập trùng số trong cùng một khách hàng?
- Khi xóa một số, làm sao không xóa nhầm số còn lại?
- Làm sao buộc từng số, chứ không chỉ cả chuỗi, tuân theo định dạng hợp lệ?

Nếu mọi số chỉ là một đoạn con của chuỗi, các thao tác trên phải phân tách văn bản, xử lý khoảng trắng, dấu phân cách và định dạng. Chỉ mục, khóa, ràng buộc **UNIQUE** và khóa ngoại trên từng số cũng khó áp dụng trực tiếp.

## 2. “Nguyên tử” là khái niệm theo miền dữ liệu

### 2.1. Không có phép thử nguyên tử tuyệt đối cho mọi nghiệp vụ

Trong mô hình quan hệ cổ điển, giá trị của một thuộc tính được xem là một phần tử của miền giá trị của thuộc tính đó. Trong giảng dạy 1NF, ta thường nhấn mạnh rằng thuộc tính không chứa **nhóm lặp** hoặc **nhiều giá trị có ý nghĩa độc lập**.

Một số điện thoại có mã quốc gia và phần số thuê bao; một ngày có năm, tháng, ngày; một địa chỉ có nhiều thành phần. Việc một giá trị có thể được phân tích thành các phần **không tự động** làm nó mất tính nguyên tử.

Hãy xét các miền dữ liệu khác nhau:

| Giá trị | Có thể coi là một giá trị nguyên tử khi… | Nên tách hoặc mô hình hóa lại khi… |
| --- | --- | --- |
| **+84901234567** | Hệ thống xem toàn bộ số là một phương thức liên hệ; kiểm tra và tìm kiếm theo số đầy đủ | Cần quản lý các thành phần với ràng buộc nghiệp vụ riêng, hoặc nhiều số cho một người |
| **2026-11-22** | Ứng dụng làm việc với một giá trị ngày | Cần lưu các khái niệm nghiệp vụ độc lập, chẳng hạn tháng tài chính với quy tắc riêng |
| **Nguyễn Văn An** | Hệ thống chỉ cần lưu và hiển thị tên đầy đủ | Cần quản lý họ, tên đệm, tên gọi theo những quy tắc rõ ràng; tránh giả định mọi văn hóa đặt tên như nhau |
| **Địa chỉ giao hàng** | Là ảnh chụp nguyên trạng địa chỉ đã được chấp nhận ở thời điểm đặt hàng | Cần xác thực hay truy vấn riêng tỉnh, mã bưu chính, quốc gia hoặc liên kết với danh mục địa lý |
| **[số A, số B]** trong ô điện thoại | Chỉ là một tài liệu/giá trị mà ứng dụng thật sự đối xử như đối tượng không phân rã | Mỗi số cần thêm, xóa, tìm kiếm, kiểm tra hoặc gắn thuộc tính riêng |

Vì vậy, câu hỏi đúng là: **“Đơn vị giá trị nhỏ nhất mà nghiệp vụ cần quản lý độc lập trong miền dữ liệu này là gì?”** Đây là quyết định mô hình hóa dựa trên cách sử dụng dữ liệu, không phải quy tắc “mọi chuỗi phải tách thành ký tự” hay “mọi ngày phải tách thành ba số”.

### 2.2. Phân biệt một giá trị có cấu trúc với một tập hợp nhiều giá trị

Hai tình huống dễ bị nhầm lẫn:

**Một giá trị có cấu trúc:** một thời điểm **2026-11-22T09:30:00+07:00** có nhiều thành phần nhưng là **một thời điểm** với miền dữ liệu thời gian. Kiểu **TIMESTAMP** hay kiểu giá trị thời gian thích hợp thường biểu diễn tốt hơn việc lưu một chuỗi tùy ý.

**Một tập hợp giá trị độc lập:** khách hàng có hai số điện thoại, mỗi số có thể thêm, hủy, xác minh hoặc đặt nhãn riêng. Hai số là **hai phần tử của một tập quan hệ**, dù người dùng nhìn thấy chúng trong một ô giao diện.

Nếu một thuộc tính chứa JSON hay ARRAY trong SQL, cần thận trọng khi kết luận. Hệ quản trị hiện đại cho phép những kiểu này; việc chúng có “thỏa 1NF” hay không còn phụ thuộc định nghĩa 1NF và cách xem miền giá trị, nên không thể kết luận chỉ bằng tên kiểu dữ liệu. **Về thiết kế thực tế**, khi các phần tử bên trong cần khóa, ràng buộc hoặc cập nhật độc lập, bảng con thường làm mô hình quan hệ rõ ràng và dễ kiểm chứng hơn.

## 3. Chuyển từ danh sách trong ô thành quan hệ một-nhiều

Với ví dụ khách hàng, ta tách hai tập sự thật:

1. Khách hàng **101** có tên **An**.
2. Khách hàng **101** có số **+84901234567** và có số **+84909876543**.

Mỗi sự thật “khách hàng có số điện thoại” trở thành một hàng trong bảng **customer_phones**. Tên khách hàng vẫn nằm trong bảng **customers**, không bị lặp lại theo từng số.

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ CUSTOMER_PHONES : "có"
    CUSTOMERS {
        bigint customer_id PK
        varchar customer_name
    }
    CUSTOMER_PHONES {
        bigint customer_id PK, FK
        varchar phone_e164 PK
        varchar phone_label
    }
~~~

| customers.customer_id | customer_name |
| ---: | --- |
| 101 | An |
| 102 | Bình |
| 103 | Chi |

| customer_phones.customer_id | phone_e164 | phone_label |
| ---: | --- | --- |
| 101 | +84901234567 | mobile |
| 101 | +84909876543 | work |
| 102 | +84907654321 | mobile |

Bảng **customers** có một hàng cho mỗi khách hàng; bảng **customer_phones** có một hàng cho mỗi **cặp khách hàng – số điện thoại**. Khách hàng 103 không có số vẫn có thể tồn tại. Trong ví dụ, cùng một số không được lặp lại **trong cùng một khách hàng**, nhưng việc một số có thể gắn với hai khách hàng khác nhau hay không là quy tắc nghiệp vụ riêng; không nên tự áp đặt **UNIQUE(phone_e164)** cho toàn hệ thống.

### 3.1. Lược đồ SQL có khóa và ràng buộc

Ví dụ sau dùng PostgreSQL để có thể kiểm tra biểu thức định dạng số với toán tử chính quy **~**:

~~~sql
CREATE TABLE customers (
    customer_id   BIGINT PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
);

CREATE TABLE customer_phones (
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id),
    phone_e164 VARCHAR(16) NOT NULL
        CHECK (phone_e164 ~ '^\+[1-9][0-9]{1,14}$'),
    phone_label VARCHAR(20) NOT NULL
        CHECK (phone_label IN ('mobile', 'home', 'work')),
    PRIMARY KEY (customer_id, phone_e164)
);

INSERT INTO customers (customer_id, customer_name) VALUES
    (101, 'An'),
    (102, 'Bình'),
    (103, 'Chi');

INSERT INTO customer_phones
    (customer_id, phone_e164, phone_label)
VALUES
    (101, '+84901234567', 'mobile'),
    (101, '+84909876543', 'work'),
    (102, '+84907654321', 'mobile');
~~~

Những ràng buộc đang bảo vệ các quy tắc khác nhau:

- **PRIMARY KEY (customer_id, phone_e164)**: không nhập cùng một số hai lần cho cùng một khách hàng.
- **FOREIGN KEY customer_id**: không gán số cho khách hàng chưa tồn tại.
- **CHECK phone_e164**: kiểm tra cấu trúc chuỗi có tiền tố **+** và số chữ số phù hợp phần biểu diễn E.164, chứ **không** chứng thực số có tồn tại hoặc đã được cấp phát.
- **CHECK phone_label**: nhãn nằm trong tập giá trị mà hệ thống chấp nhận.

Không cần một cột **phone_1**, **phone_2** hay dự đoán khách hàng tối đa có bao nhiêu số. Nếu nghiệp vụ yêu cầu định danh từng bản ghi phương thức liên hệ xuyên suốt các lần đổi số, có thể dùng **phone_id** làm khóa thay thế và thêm ràng buộc duy nhất cho **(customer_id, phone_e164)**. Lựa chọn khóa cần theo vòng đời dữ liệu, không có một đáp án duy nhất cho mọi hệ thống.

### 3.2. Thao tác đơn giản khi dữ liệu đã có một hàng cho mỗi số

**Thêm số thứ ba** cho một khách hàng:

~~~sql
INSERT INTO customer_phones
    (customer_id, phone_e164, phone_label)
VALUES (101, '+84903334444', 'home');
~~~

**Tìm khách hàng theo số đầy đủ:**

~~~sql
SELECT c.customer_id, c.customer_name
FROM customer_phones AS p
JOIN customers AS c
    ON c.customer_id = p.customer_id
WHERE p.phone_e164 = '+84909876543';
~~~

**Xóa đúng một số**, không đụng đến số còn lại hay bản ghi khách hàng:

~~~sql
DELETE FROM customer_phones
WHERE customer_id = 101
  AND phone_e164 = '+84903334444';
~~~

**Đếm số của từng khách hàng, kể cả người không có số:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(p.phone_e164) AS phone_count
FROM customers AS c
LEFT JOIN customer_phones AS p
    ON p.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Kết quả là **An: 2**, **Bình: 1**, **Chi: 0**. Cần dùng **COUNT(p.phone_e164)** thay vì **COUNT(*)**, vì phép **LEFT JOIN** vẫn tạo một hàng kết quả với các cột **p** là **NULL** cho khách hàng chưa có số.

Nếu giao diện muốn hiển thị nhiều số trên một dòng, ta có thể **tổng hợp ở lớp truy vấn hoặc ứng dụng**; nhu cầu hiển thị một dòng không buộc phải lưu mọi số trong một ô:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        STRING_AGG(p.phone_e164, ', ' ORDER BY p.phone_e164),
        ''
    ) AS phones_for_display
FROM customers AS c
LEFT JOIN customer_phones AS p
    ON p.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Tập hợp chuỗi ở kết quả đọc nhằm phục vụ giao diện; dữ liệu được quản lý vẫn theo từng hàng có khóa và ràng buộc độc lập.

## 4. Nhận diện nhóm lặp và ranh giới của quy tắc 1NF

### 4.1. Danh sách trong một cột

~~~text
article_id | tags
-----------+---------------------------
10         | database,sql,architecture
~~~

Nếu thẻ là các thực thể cần tìm kiếm, đổi tên, cấp quyền hoặc dùng lại, cột **tags** thực chất đang biểu diễn nhiều mối liên hệ. Một mô hình phù hợp có thể là:

~~~text
articles(article_id, ...)
tags(tag_id, tag_name, ...)
article_tags(article_id, tag_id)
~~~

Đặt **PRIMARY KEY (article_id, tag_id)** trong bảng nối nếu mỗi thẻ được gắn tối đa một lần cho một bài. Nếu chỉ lưu một bản mô tả JSON bất biến để hiển thị hoặc truyền qua API, quyết định mô hình lại có thể khác; hãy xét các thao tác nghiệp vụ thực tế.

### 4.2. Nhiều cột được đánh số

~~~text
customer_id | phone_1       | phone_2       | phone_3
------------+---------------+---------------+---------
101         | +84901234567  | +84909876543  | NULL
~~~

**phone_1**, **phone_2** và **phone_3** đều có thể là giá trị scalar hợp lệ của từng cột. Vì vậy không chính xác nếu khẳng định **mọi** bảng có cột đánh số đều vi phạm 1NF theo mọi định nghĩa hình thức.

Tuy vậy, cấu trúc này thường biểu hiện **nhóm lặp theo nghiệp vụ**: phải dự đoán số lượng tối đa, thêm cột khi nhu cầu tăng, khó áp dụng cùng ràng buộc cho mọi số, truy vấn phải xét nhiều cột, và “số thứ 2” đôi khi không có ý nghĩa ổn định. Mô hình bảng con vẫn phù hợp hơn cho tập số có số lượng biến đổi.

Ngược lại, các cột **home_phone** và **emergency_phone** có thể phản ánh **hai vai trò khác nhau** với quy tắc và số lượng cố định; trước khi tách, cần hỏi nghiệp vụ có cho nhiều số trong mỗi vai trò hay cần lưu lịch sử, ưu tiên và trạng thái xác minh của từng phương thức liên hệ hay không.

### 4.3. Nhiều dòng cùng mô tả thực thể gốc

Một cách “sửa nhanh” khác là lặp lại thông tin khách hàng ở mỗi dòng:

| customer_id | customer_name | phone_e164 |
| ---: | --- | --- |
| 101 | An | +84901234567 |
| 101 | An | +84909876543 |

Mỗi ô hiện chứa một giá trị, nhưng **customer_name** lại bị sao chép. Thay đổi tên An cần sửa nhiều hàng; không thể biểu diễn khách hàng chưa có số nếu khóa bắt buộc gồm số điện thoại. Bảng có thể đáp ứng cách hiểu đơn giản về thuộc tính nguyên tử mà **vẫn chưa là thiết kế tốt**.

Đó là lý do 1NF là điểm khởi đầu: các dạng chuẩn tiếp theo và quy tắc xác định *grain*, khóa, phụ thuộc hàm giúp xử lý những nguồn dư thừa còn lại. Không nên coi “đã tách chuỗi thành nhiều dòng” là đủ để kết luận toàn bộ lược đồ được chuẩn hóa đúng.

## 5. 1NF không tự bảo đảm điều gì?

| Khái niệm | 1NF giúp định hướng | Vẫn cần xem xét riêng |
| --- | --- | --- |
| **Miền giá trị** | Một thuộc tính đại diện cho một giá trị thuộc miền đã xác định | Kiểu dữ liệu, định dạng, **CHECK**, danh mục hợp lệ |
| **Tính duy nhất** | Mỗi hàng biểu diễn một bộ giá trị trong quan hệ | Khóa ứng viên, **PRIMARY KEY**, **UNIQUE** trong hệ SQL |
| **Dữ liệu thiếu** | Không nên dùng một chuỗi danh sách để thay thế cấu trúc quan hệ | **NULL**, tính bắt buộc và ý nghĩa “chưa biết” so với “không áp dụng” |
| **Dư thừa** | Làm lộ các giá trị độc lập thay vì giấu trong một ô | Phụ thuộc hàm, **2NF**, **3NF**, **BCNF** và các dạng chuẩn liên quan |
| **Toàn vẹn quan hệ** | Phân biệt rõ thực thể và từng liên kết | Khóa ngoại, quy tắc xóa/cập nhật và transaction |
| **Hiệu năng** | Cho lược đồ có cấu trúc dễ ràng buộc và truy vấn rõ ràng | Chỉ mục, kế hoạch truy vấn, khối lượng dữ liệu, nhu cầu đọc/ghi |

Trong mô hình quan hệ toán học, một quan hệ là tập hợp các bộ, không chứa các bộ trùng hệt nhau. Hệ SQL trong thực tế có thể cho phép dòng trùng nếu không khai báo khóa hoặc ràng buộc. Vì vậy, dùng một giá trị mỗi ô **không thay thế** việc xác định và bảo vệ tính duy nhất.

Tương tự, 1NF không đơn giản có nghĩa “cấm mọi **NULL**”. Nhiều lược đồ SQL tuân theo cách thực hành 1NF vẫn sử dụng **NULL** theo ngữ nghĩa của SQL; cần quyết định từng cột có cho phép thiếu hay không. Riêng ví dụ **khách hàng không có số điện thoại**, việc **không có hàng** trong bảng **customer_phones** thường rõ nghĩa hơn một hàng “số điện thoại = NULL”.

## 6. Quy trình áp dụng khi chuyển yêu cầu nghiệp vụ thành lược đồ

1. **Xác định grain của từng bảng.** “Một hàng là một khách hàng”, “một hàng là một số thuộc về khách hàng”, hay “một hàng là một sự kiện gọi điện”? Đừng ghép các grain khác nhau mà chưa xác định quan hệ.
2. **Liệt kê miền giá trị và thao tác của từng thuộc tính.** Dữ liệu này được tìm kiếm, so sánh, cập nhật, xác minh hay cấp quyền theo cả giá trị hay theo từng phần tử?
3. **Tìm tập hợp bị giấu.** Kiểm tra chuỗi có dấu phân cách, JSON/ARRAY chứa danh sách thực thể, cột đánh số và số lượng phần tử có thể thay đổi.
4. **Tách thực thể và liên kết khi cần.** Với quan hệ một-nhiều, đặt nhiều hàng trong bảng con; với quan hệ nhiều-nhiều, xem xét bảng nối.
5. **Đặt khóa và ràng buộc theo nghiệp vụ.** Khóa chính quyết định độ duy nhất; khóa ngoại bảo vệ tham chiếu; các ràng buộc kiểu dữ liệu, **CHECK** và **UNIQUE** bảo vệ miền giá trị.
6. **Kiểm thử ca biên.** Không phần tử, một phần tử, nhiều phần tử, phần tử trùng, giá trị không hợp lệ, xóa một phần tử, thay đổi thuộc tính của thực thể gốc.
7. **Đánh giá truy vấn và chiến lược truy cập.** Chỉ mục có thể bổ sung theo truy vấn thường dùng. Nếu cân nhắc nhúng document hoặc phi chuẩn hóa để tối ưu, phải xác định nguồn dữ liệu chuẩn và cách giữ nhất quán.

### Chú ý khi di chuyển từ dữ liệu cũ

Không nên coi **SPLIT** chuỗi theo dấu phẩy là đủ trong mọi tình huống. Dữ liệu thật có thể có khoảng trắng, ký tự phân cách xuất hiện trong nội dung, định dạng số khác nhau, giá trị trùng và dòng thiếu. Nên **kiểm kê nguồn dữ liệu**, chuẩn hóa từng phần tử theo miền hợp lệ, xác định bản ghi lỗi hoặc cần xử lý thủ công, rồi mới nạp vào bảng con và áp dụng ràng buộc.

Trong ví dụ số điện thoại, một quy trình chuyển đổi an toàn cần quyết định cách chuẩn hóa mã quốc gia, cách xử lý số trùng, ý nghĩa số ưu tiên và kết quả khi không có số nào. **E.164** cũng là cách biểu diễn số, không tự chứng minh số đó có người sử dụng hay có thể nhận cuộc gọi.

## 7. Bài tập: danh sách sản phẩm trong đơn hàng

Hệ thống bán hàng nhận bảng sau:

| order_id | ordered_at | items |
| --- | --- | --- |
| O-01 | 2026-11-22 | P10:2; P20:1 |
| O-02 | 2026-11-22 | P20:3 |

Giả định phần tử **P10:2** nghĩa là sản phẩm P10 với số lượng 2, và một đơn có thể có nhiều dòng hàng. Sau khi tạo đơn, nghiệp vụ có thể sửa số lượng hoặc hủy riêng một dòng; mỗi dòng cần kiểm tra số lượng dương.

**Yêu cầu:**

1. Giải thích vì sao **items** là một tập giá trị nghiệp vụ cần quản lý độc lập; chỉ ra khó khăn khi cập nhật riêng P10.
2. Xác định grain cho bảng đơn hàng và bảng dòng hàng. Đề xuất khóa chính và khóa ngoại.
3. Viết điều kiện để bảo đảm **quantity > 0** trên từng dòng.
4. Nếu một đơn được phép có **hai dòng cùng sản phẩm** (do chương trình khuyến mãi hoặc giá khác nhau), lựa chọn khóa nào phù hợp?

**Gợi ý lời giải:**

~~~text
orders(
    order_id PRIMARY KEY,
    ordered_at
)

order_lines(
    order_id REFERENCES orders(order_id),
    line_no,
    product_id,
    quantity CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
)
~~~

- **orders** có grain “một đơn hàng”; **order_lines** có grain “một dòng hàng của một đơn”. Việc sửa P10 diễn ra trên đúng dòng liên quan.
- **(order_id, line_no)** là khóa phù hợp khi một đơn cho phép nhiều dòng cùng **product_id**. Nếu nghiệp vụ bảo đảm tối đa một dòng cho mỗi sản phẩm trong một đơn, **(order_id, product_id)** cũng có thể là khóa ứng viên.
- Trong một hệ thống thực tế, **product_id** thường cần khóa ngoại tới bảng sản phẩm; các thông tin giá tại thời điểm đặt hàng có thể cần lưu trong dòng hàng như **dữ liệu lịch sử của giao dịch**, không tự động cập nhật theo giá danh mục hiện tại.

## 8. Ghi nhớ

1NF giúp dữ liệu quan hệ có **đơn vị giá trị rõ ràng theo miền**. Nó hướng người thiết kế tránh chôn các phần tử cần quản lý độc lập trong một chuỗi hay nhóm lặp và khuyến khích thể hiện tập hợp bằng các hàng cùng khóa, ràng buộc và quan hệ thích hợp. **Nguyên tử là quyết định về ngữ nghĩa dữ liệu**, không phải mệnh lệnh phải phân rã mọi giá trị có thể tách kỹ thuật.

Khi một thuộc tính thực chất chứa nhiều sự thật độc lập, hãy xác định grain của chúng, tách thành bảng hoặc liên kết phù hợp và bảo vệ bằng các ràng buộc. Sau đó tiếp tục đánh giá phụ thuộc hàm, vòng đời thực thể và các dạng chuẩn cao hơn: **đạt 1NF là điều kiện khởi đầu, chưa bảo đảm đã hết dữ liệu dư thừa hay bất thường khi ghi**.
