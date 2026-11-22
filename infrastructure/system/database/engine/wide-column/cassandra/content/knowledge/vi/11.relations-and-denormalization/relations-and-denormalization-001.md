# Biểu diễn quan hệ một-một, một-nhiều và nhiều-nhiều trong Apache Cassandra

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện quan hệ **một-một (1:1)**, **một-nhiều (1:N)** và **nhiều-nhiều (N:M)** trong mô hình nghiệp vụ.
- Chuyển từng quan hệ thành các bảng Cassandra phục vụ **câu truy vấn cụ thể**, thay vì sao chép máy móc lược đồ quan hệ.
- Chọn `PRIMARY KEY`, **partition key** và **clustering column** phù hợp với cách đọc dữ liệu; nhận biết khi nào phân vùng có thể quá lớn.
- Giải thích vì sao phải lặp dữ liệu, cập nhật nhiều bảng ở phía ứng dụng và xử lý trường hợp các bản sao tạm thời không đồng bộ.

## 1. Tư duy thiết kế quan hệ trong Cassandra

Trong cơ sở dữ liệu quan hệ, ta thường chuẩn hóa thành bảng `users`, `orders`, `order_items`, dùng **khóa ngoại** để liên kết và `JOIN` để ghép dữ liệu khi đọc. Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình *wide-column*: dữ liệu được phân phối dựa trên **partition key** và thường được thiết kế theo **truy vấn cần phục vụ**. Cassandra không hỗ trợ `JOIN`, khóa ngoại và xóa dây chuyền (`ON DELETE CASCADE`) theo cách của một RDBMS.

Vì thế, một quan hệ nghiệp vụ có thể được biểu diễn bằng **một bảng**, **hai bảng** hoặc nhiều **bảng nhìn theo từng hướng truy vấn**. Những bảng này có thể lặp dữ liệu có chủ đích (*denormalization*). Ứng dụng chịu trách nhiệm giữ các bản biểu diễn nhất quán với nhau.

Ví dụ, trước khi thiết kế quan hệ khách hàng–đơn hàng, hãy viết các truy vấn cần chạy:

1. Lấy thông tin khách hàng theo `customer_id`.
2. Liệt kê 20 đơn mới nhất của một khách hàng trong một tháng.
3. Tìm một đơn hàng trực tiếp theo `order_id`.

Truy vấn (2) và (3) có hai khóa tra cứu khác nhau. Thực tế thường cần **hai bảng đơn hàng** để mỗi truy vấn đọc hiệu quả; tránh đọc toàn bộ dữ liệu rồi lọc ở ứng dụng hoặc dựa vào `ALLOW FILTERING`.

### Phân biệt hai phần của khóa chính

```sql
PRIMARY KEY ((customer_id, order_month), ordered_at, order_id)
--            ^ partition key              ^ clustering columns
```

- **Partition key** `(customer_id, order_month)` xác định phân vùng dữ liệu, giúp Cassandra định tuyến truy vấn đến đúng tập nút. Để đọc một phân vùng cụ thể, thông thường phải cung cấp đủ các thành phần khóa phân vùng.
- **Clustering columns** `ordered_at`, `order_id` xác định các hàng bên trong phân vùng và thứ tự lưu trữ. Chúng rất hữu ích khi liệt kê các bản ghi theo thời gian.
- **Khóa chính** xác định duy nhất một hàng. Ghi lại với cùng khóa chính là thao tác *upsert* trên hàng đó; đổi một thành phần khóa chính tương đương ghi một hàng khác.

Đừng đồng nhất **quan hệ nghiệp vụ** với **khóa ngoại**: các giá trị ID trong ví dụ dưới đây diễn tả liên kết về mặt logic, nhưng Cassandra không tự kiểm tra đối tượng được tham chiếu có tồn tại hay không.

## 2. Quan hệ một-một (1:1): người dùng và tùy chọn cá nhân

**Bài toán:** mỗi người dùng có tối đa một bộ tùy chọn (`locale`, `time_zone`, `email_notifications`). Hai kiểu thiết kế thường gặp:

**Cách A — Đặt chung một hàng** nếu ứng dụng gần như luôn đọc thông tin người dùng và tùy chọn cùng lúc:

```sql
CREATE TABLE users_with_preferences_by_id (
    user_id uuid PRIMARY KEY,
    display_name text,
    locale text,
    time_zone text,
    email_notifications boolean
);

SELECT display_name, locale, time_zone
FROM users_with_preferences_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Một lần tra cứu `user_id` đã có đủ dữ liệu. Tuy nhiên, khi tùy chọn có vòng đời riêng, cần quyền truy cập riêng hoặc được cập nhật bởi một dịch vụ khác, có thể chọn cách B.

**Cách B — Tách thành hai bảng, dùng cùng định danh:**

```sql
CREATE TABLE users_by_id (
    user_id uuid PRIMARY KEY,
    display_name text,
    email text
);

CREATE TABLE user_preferences_by_id (
    user_id uuid PRIMARY KEY,
    locale text,
    time_zone text,
    email_notifications boolean
);

INSERT INTO users_by_id (user_id, display_name, email)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'Lan', 'lan@example.com'
);

INSERT INTO user_preferences_by_id
    (user_id, locale, time_zone, email_notifications)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'vi-VN', 'Asia/Ho_Chi_Minh', true
);

SELECT locale, time_zone, email_notifications
FROM user_preferences_by_id
WHERE user_id = 11111111-1111-4111-8111-111111111111;
```

Ở cách B, `user_preferences_by_id` cho phép **tối đa một hàng ứng với mỗi `user_id`**, vì `user_id` là toàn bộ khóa chính. Nhưng Cassandra **không đảm bảo** rằng mỗi hàng `users_by_id` đều có hàng tùy chọn, cũng không ngăn ứng dụng tạo tùy chọn cho một ID chưa có người dùng. Nếu cần hiển thị cả hai, ứng dụng đọc hai bảng và ghép theo ID.

**Quy tắc chọn:** một hàng cho dữ liệu luôn đọc cùng nhau và có kích thước hợp lý; hai bảng khi cần đọc, kiểm soát truy cập hoặc quản lý vòng đời độc lập. Không tách bảng chỉ vì sơ đồ thực thể có quan hệ 1:1.

## 3. Quan hệ một-nhiều (1:N): khách hàng và đơn hàng

**Bài toán:** một khách hàng có nhiều đơn hàng. Cần:

- Lấy danh sách đơn mới nhất theo khách hàng và theo tháng.
- Tìm đơn bất kỳ bằng `order_id` (ví dụ qua trang chi tiết đơn hàng).

Ta tạo hai bảng đọc theo hai hướng:

```sql
-- Danh sách đơn của một khách hàng trong một tháng.
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    order_month date,
    ordered_at timestamp,
    order_id uuid,
    total_amount decimal,
    order_status text,
    PRIMARY KEY ((customer_id, order_month), ordered_at, order_id)
) WITH CLUSTERING ORDER BY (ordered_at DESC, order_id ASC);

-- Tra cứu trực tiếp một đơn bằng ID.
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    ordered_at timestamp,
    order_month date,
    total_amount decimal,
    order_status text
);
```

`order_month` là ngày đầu tháng, chẳng hạn `2026-11-01`, được tính tại thời điểm tạo đơn theo quy ước thời gian thống nhất của ứng dụng (ví dụ UTC). Khóa phân vùng ghép `(customer_id, order_month)` giúp tránh dồn toàn bộ lịch sử đơn hàng của một khách hàng vào một phân vùng không giới hạn. Khóa `order_id` đứng sau `ordered_at` phân biệt các đơn tạo cùng thời điểm.

```sql
-- Một sự kiện tạo đơn được ghi vào cả hai bảng.
INSERT INTO orders_by_id
    (order_id, customer_id, ordered_at, order_month,
     total_amount, order_status)
VALUES (
    22222222-2222-4222-8222-222222222222,
    11111111-1111-4111-8111-111111111111,
    '2026-11-21T01:00:00Z', '2026-11-01',
    199000.00, 'PAID'
);

INSERT INTO orders_by_customer_month
    (customer_id, order_month, ordered_at, order_id,
     total_amount, order_status)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-01', '2026-11-21T01:00:00Z',
    22222222-2222-4222-8222-222222222222,
    199000.00, 'PAID'
);

-- 20 đơn mới nhất trong tháng 11 của khách hàng.
SELECT order_id, ordered_at, total_amount, order_status
FROM orders_by_customer_month
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11-01'
LIMIT 20;

-- Đọc chi tiết đơn bằng ID.
SELECT * FROM orders_by_id
WHERE order_id = 22222222-2222-4222-8222-222222222222;
```

Đây là **denormalization có chủ đích**: `order_status`, `total_amount` và các trường nhận diện xuất hiện ở hai bảng để mỗi đường đọc hiệu quả. Nếu trạng thái đổi từ `PAID` sang `SHIPPED`, ứng dụng phải cập nhật **cả hai**:

```sql
UPDATE orders_by_id
SET order_status = 'SHIPPED'
WHERE order_id = 22222222-2222-4222-8222-222222222222;

UPDATE orders_by_customer_month
SET order_status = 'SHIPPED'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND order_month = '2026-11-01'
  AND ordered_at = '2026-11-21T01:00:00Z'
  AND order_id = 22222222-2222-4222-8222-222222222222;
```

**Lưu ý quan trọng:** để cập nhật chính xác bảng thứ hai, phải biết **giá trị khóa chính gốc** (`customer_id`, `order_month`, `ordered_at`, `order_id`). Nếu thời điểm đặt hàng thay đổi trong lúc cập nhật, Cassandra sẽ coi đó là một hàng khác; ứng dụng phải xử lý xóa hàng cũ và tạo hàng mới.

### Khi một phân vùng vẫn quá lớn

Chia theo tháng không đủ nếu một khách hàng tạo hàng triệu đơn trong tháng. Có thể chia tiếp theo ngày, tuần hoặc một **bucket** xác định trước, nhưng phải cân đối: mỗi bucket nhỏ hơn sẽ làm truy vấn tổng hợp nhiều bucket phức tạp hơn. Với yêu cầu xem danh sách trên nhiều tháng, ứng dụng truy vấn nhiều phân vùng rồi gộp/sắp xếp kết quả. Dùng **paging state** của driver để phân trang trong truy vấn; tránh mô phỏng `OFFSET` bằng cách quét rồi bỏ qua nhiều hàng.

## 4. Quan hệ nhiều-nhiều (N:M): học viên và khóa học

**Bài toán:** một học viên tham gia nhiều khóa học và một khóa học có nhiều học viên. Hai câu hỏi độc lập:

1. Học viên `S` đang tham gia những khóa nào?
2. Khóa học `C` có những học viên nào?

Trong RDBMS, bảng trung gian `enrollments(student_id, course_id)` và `JOIN` có thể phục vụ cả hai hướng. Với Cassandra, cách trực tiếp là **hai bảng biểu diễn cùng mối liên kết, mỗi bảng được khóa theo một hướng đọc**:

```sql
CREATE TABLE enrollments_by_student (
    student_id uuid,
    course_id uuid,
    enrolled_at timestamp,
    enrollment_status text,
    PRIMARY KEY ((student_id), course_id)
);

CREATE TABLE enrollments_by_course (
    course_id uuid,
    student_id uuid,
    enrolled_at timestamp,
    enrollment_status text,
    PRIMARY KEY ((course_id), student_id)
);
```

Một học viên đăng ký một khóa học thì ghi **cùng một cạnh quan hệ** vào cả hai bảng:

```sql
INSERT INTO enrollments_by_student
    (student_id, course_id, enrolled_at, enrollment_status)
VALUES (
    44444444-4444-4444-8444-444444444444,
    33333333-3333-4333-8333-333333333333,
    '2026-11-21T02:00:00Z', 'ACTIVE'
);

INSERT INTO enrollments_by_course
    (course_id, student_id, enrolled_at, enrollment_status)
VALUES (
    33333333-3333-4333-8333-333333333333,
    44444444-4444-4444-8444-444444444444,
    '2026-11-21T02:00:00Z', 'ACTIVE'
);

-- Các khóa học của một học viên.
SELECT course_id, enrolled_at, enrollment_status
FROM enrollments_by_student
WHERE student_id = 44444444-4444-4444-8444-444444444444;

-- Các học viên của một khóa học.
SELECT student_id, enrolled_at, enrollment_status
FROM enrollments_by_course
WHERE course_id = 33333333-3333-4333-8333-333333333333;
```

Đọc một hướng chỉ cần truy vấn đúng bảng của hướng đó. Cassandra không kiểm tra học viên hoặc khóa học tương ứng có tồn tại trong bảng thực thể khác; ứng dụng phải kiểm tra khi nghiệp vụ yêu cầu.

Khi rút học viên khỏi khóa học, phải cập nhật hoặc xóa **hai bản ghi liên kết**. Nếu dùng trạng thái `CANCELLED` thay vì xóa, cả hai bảng cần nhận cùng trạng thái. Giữ `enrolled_at` và các trường liên kết ổn định để ghi lại cùng khóa chính mang tính **idempotent** (lặp lại thao tác mà không sinh thêm liên kết).

**Giới hạn cần dự liệu:** một khóa học có hàng triệu học viên có thể tạo phân vùng rất lớn ở `enrollments_by_course`. Nếu có nguy cơ này, có thể thiết kế `PRIMARY KEY ((course_id, bucket), student_id)` rồi định nghĩa cách tính bucket. Khi đó ứng dụng cần biết bucket để truy vấn hoặc quét các bucket phù hợp; không có một cấu trúc khóa chung tối ưu cho mọi quy mô và mọi kiểu truy vấn.

## 5. Chọn mẫu biểu diễn theo cách đọc

| Quan hệ | Câu hỏi cần trả lời | Bố trí dữ liệu điển hình | Điểm phải kiểm soát |
| --- | --- | --- | --- |
| 1:1 | Lấy hồ sơ và tùy chọn theo `user_id` | Một hàng chung hoặc hai bảng cùng `user_id` làm khóa phân vùng | Không có khóa ngoại; đọc hai bảng nếu tách |
| 1:N | Lấy danh sách con theo cha; tìm một bản ghi con bằng ID | `orders_by_customer_month` và `orders_by_id` | Kích thước phân vùng, cập nhật hai bản sao, truy vấn qua nhiều bucket |
| N:M | Liệt kê các đối tượng liên kết theo cả hai chiều | `enrollments_by_student` và `enrollments_by_course` | Ghi/xóa hai hướng, phân vùng lớn khi bậc liên kết cao |

Một cách kiểm tra thiết kế là viết **truy vấn CQL thực tế** trước khi triển khai. Nếu truy vấn hay dùng không có đầy đủ partition key, phải quét nhiều phân vùng, hoặc phụ thuộc `ALLOW FILTERING`, hãy xem lại khóa và cân nhắc tạo bảng riêng theo truy vấn đó. Không nên tự động dùng secondary index hoặc materialized view như một bản thay thế tổng quát cho thiết kế bảng theo đường đọc; mỗi cơ chế có giới hạn về hiệu năng và vận hành riêng.

## 6. Đồng bộ dữ liệu lặp và mức nhất quán

Denormalization đổi chi phí `JOIN` ở lúc đọc thành công việc **ghi và duy trì nhiều biểu diễn**. Giả sử tạo đơn thành công ở `orders_by_id` nhưng ghi vào `orders_by_customer_month` bị lỗi: tra cứu bằng ID thấy đơn, còn trang danh sách theo khách hàng chưa thấy. Đây là lỗi đồng bộ ở **mức ứng dụng**, dù từng lần ghi đã nhận xác nhận thành công ở mức nhất quán Cassandra được cấu hình.

Một quy trình thường dùng:

1. Xác định **dữ liệu nguồn** và các bảng phục vụ từng đường đọc; chốt khóa chính của mọi bản sao ngay khi tạo thực thể.
2. Khi sự kiện nghiệp vụ xảy ra, cập nhật các bảng liên quan bằng câu lệnh đã chuẩn bị (*prepared statement*). Giữ cùng ID, thời điểm và bucket khi retry.
3. Chấp nhận rằng một số đường đọc có thể tạm lệch nhau trong lúc lỗi/timeout; theo dõi ghi thất bại, retry có kiểm soát và có cơ chế **đối soát/sửa dữ liệu**.
4. Khi xóa hoặc thay đổi liên kết, cập nhật toàn bộ các bảng theo hướng đọc. Nếu xóa, chú ý tombstone và tải quét/xóa lớn.

Ví dụ phác thảo ở tầng ứng dụng Java, sau khi chuẩn bị hai câu `INSERT` như phần 3:

```java
// orderId, customerId, orderedAt, orderMonth, amount, status
// là các giá trị được cố định cho cùng một đơn hàng.
session.execute(insertOrderById.bind(
    orderId, customerId, orderedAt, orderMonth, amount, status));

session.execute(insertOrderByCustomerMonth.bind(
    customerId, orderMonth, orderedAt, orderId, amount, status));

// Nếu một lần ghi lỗi hoặc timeout: ghi nhận và retry/đối soát.
// Dùng lại chính các khóa ban đầu để tránh tạo hàng trùng logic.
```

Trong ví dụ, `insertOrderById` và `insertOrderByCustomerMonth` là các `PreparedStatement` đã chuẩn bị, còn `session` là `CqlSession` của Java Driver. Đoạn mã minh họa **hai lần ghi cần thiết**, chưa phải một quy trình xử lý lỗi hoàn chỉnh; trong hệ thống thật cần xác định cách retry, xử lý xung đột và theo dõi kết quả từng lần ghi.

**Mức nhất quán:** tùy replication factor và topology, ứng dụng có thể dùng `LOCAL_QUORUM` cho từng lần đọc/ghi để tăng bảo đảm nhìn thấy dữ liệu đã được xác nhận trong cùng datacenter. Tuy nhiên, việc chọn `LOCAL_QUORUM` **không tự tạo giao dịch nhiều bảng** hay khóa ngoại. `LOGGED BATCH` có ngữ nghĩa ghi batch và hỗ trợ bảo đảm các mutation cuối cùng được áp dụng, nhưng không cho khả năng cô lập hoặc rollback giống giao dịch quan hệ; batch qua nhiều phân vùng còn tăng chi phí. Đừng mặc định dùng `BATCH` cho mọi thao tác ghi hai hướng nếu chưa đánh giá tính đúng đắn và tải thực tế.

## 7. Những sai lầm phổ biến

| Cách làm dễ mắc | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chỉ lưu `orders_by_id`, rồi muốn tìm tất cả đơn theo `customer_id` | Không có đường tra cứu hiệu quả bằng khóa phân vùng | Thêm bảng danh sách theo khách hàng với bucket phù hợp |
| Cho `customer_id` làm khóa phân vùng duy nhất của hàng triệu đơn | Phân vùng rất lớn, có thể trở thành điểm nóng | Chia theo tháng/ngày/bucket dựa trên lưu lượng thực |
| Chỉ lưu `enrollments_by_student` nhưng cần danh sách theo khóa học | Không đọc hiệu quả theo `course_id` | Thêm `enrollments_by_course` |
| Xem hai bảng chứa cùng ID như quan hệ có khóa ngoại | Dữ liệu mồ côi hoặc không đồng bộ khi ghi/xóa lỗi | Kiểm tra nghiệp vụ, retry và đối soát ở ứng dụng |
| Cập nhật dữ liệu lặp ở một bảng duy nhất | Các màn hình hiển thị kết quả khác nhau | Liệt kê đầy đủ các bản sao chịu ảnh hưởng của sự kiện |
| Đổi `ordered_at` hoặc bucket mà tưởng là `UPDATE` tại chỗ | Hàng cũ có thể còn tồn tại, hàng mới được tạo | Xử lý thay khóa như thao tác chuyển/xóa–tạo có kiểm soát |

## 8. Bài thực hành tự kiểm tra

Thiết kế hệ thống **bài viết và thẻ (tag)** với hai yêu cầu: (a) đọc 10 bài mới nhất mang một thẻ; (b) đọc tất cả thẻ gắn với một bài viết. Hãy trả lời trước khi xem gợi ý:

1. Quan hệ `article`–`tag` thuộc loại nào?
2. Cần những bảng nào nếu muốn truy vấn hiệu quả theo cả hai hướng?
3. Khóa phân vùng và khóa sắp xếp nên gồm những gì để lấy bài mới nhất theo thẻ?
4. Khi bỏ một thẻ khỏi bài viết, ứng dụng phải làm gì?

**Gợi ý đáp án:** (1) N:M; (2) ít nhất `tags_by_article` và `articles_by_tag` cho hai đường đọc; (3) bảng `articles_by_tag` có thể dùng partition key `(tag_id, time_bucket)` và clustering `(published_at DESC, article_id)`; (4) xóa hoặc cập nhật liên kết ở cả hai bảng rồi đối soát nếu có lỗi. Với một thẻ cực kỳ phổ biến, chọn bucket theo tốc độ phát sinh bài và chấp nhận ứng dụng cần đọc nhiều bucket khi xem nhiều khoảng thời gian.

## Kết luận

Trong Cassandra, **1:1** thường biểu diễn bằng một hàng hoặc hai bảng dùng chung ID; **1:N** dùng phân vùng theo đối tượng cha và clustering để liệt kê đối tượng con; **N:M** thường cần các bảng riêng cho từng chiều tra cứu. Mọi lựa chọn phải bắt đầu từ truy vấn, kích thước phân vùng và yêu cầu nhất quán. Dữ liệu lặp là công cụ để đọc hiệu quả trên hệ phân tán, đồng thời tạo trách nhiệm đồng bộ rõ ràng cho ứng dụng.
