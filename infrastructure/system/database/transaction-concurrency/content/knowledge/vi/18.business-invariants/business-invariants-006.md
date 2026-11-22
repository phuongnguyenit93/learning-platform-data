# Tính duy nhất theo quy tắc nghiệp vụ và xử lý yêu cầu trùng

Trong một hệ thống giao dịch, có hai vấn đề thường bị gọi chung là “trùng dữ liệu” nhưng cần được giải quyết bằng những cơ chế khác nhau.

- **Tính duy nhất theo quy tắc nghiệp vụ** bảo đảm hai thực thể không cùng chiếm một định danh hoặc một vị trí mà nghiệp vụ quy định là duy nhất. Ví dụ: một email đăng nhập chỉ thuộc về một tài khoản trong cùng tenant, một mã hóa đơn không được cấp cho hai hóa đơn, hoặc một người chỉ có một đăng ký đang hoạt động cho một sự kiện.
- **Yêu cầu trùng** xảy ra khi cùng một lệnh nghiệp vụ được gửi nhiều lần. Ví dụ: người dùng bấm nút thanh toán hai lần, client retry sau timeout, gateway gửi lại webhook hoặc message broker giao một message nhiều lần.

Một UNIQUE constraint có thể ngăn hai hàng cùng chiếm một khóa nghiệp vụ. Nhưng nó không tự động bảo đảm một yêu cầu thanh toán được thực hiện đúng một lần, cũng không tự trả lại kết quả của lần xử lý trước. Ngược lại, idempotency key có thể nhận diện một lần gửi lại nhưng không thay thế ràng buộc duy nhất của dữ liệu.

Thiết kế đúng cần xác định rõ điều gì phải duy nhất, trong phạm vi nào, theo cách chuẩn hóa nào; sau đó bảo vệ điều kiện đó ngay tại nơi ghi dữ liệu. Với yêu cầu có thể được gửi lại, hệ thống cần một khóa idempotency và một quy trình lưu kết quả nguyên tử để lần gửi lại không tạo thêm tác dụng phụ.

## 1. Xác định chính xác điều gì phải duy nhất

### 1.1. Khóa chính không đồng nghĩa với khóa nghiệp vụ

Khóa chính thường là định danh kỹ thuật của hàng:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL
);
~~~

id nhận diện một hàng. Nó không ngăn hai hàng có cùng email:

~~~sql
INSERT INTO customer (id, email)
VALUES (1, 'linh@example.com');

INSERT INTO customer (id, email)
VALUES (2, 'linh@example.com');
~~~

Nếu email phải duy nhất, cần biểu diễn quy tắc đó bằng UNIQUE:

~~~sql
ALTER TABLE customer
ADD CONSTRAINT uq_customer_email UNIQUE (email);
~~~

Khóa chính và khóa nghiệp vụ có vai trò khác nhau:

- Khóa chính thường ổn định, ngắn gọn và thuận tiện cho quan hệ tham chiếu.
- Khóa nghiệp vụ diễn đạt quy tắc mà người dùng hoặc quy trình kinh doanh quan tâm.
- Một hàng có thể có một khóa chính và nhiều ràng buộc duy nhất trên các thuộc tính nghiệp vụ khác nhau.

Không nên cho rằng khóa chính tự động giải quyết mọi yêu cầu chống trùng.

### 1.2. Xác định phạm vi duy nhất

Một giá trị có thể duy nhất trong một phạm vi nhưng được phép lặp ở phạm vi khác.

Ví dụ, username chỉ cần duy nhất trong từng tổ chức:

~~~sql
CREATE TABLE organization_user (
    id BIGINT PRIMARY KEY,
    organization_id BIGINT NOT NULL,
    username VARCHAR(100) NOT NULL,
    CONSTRAINT uq_org_username
        UNIQUE (organization_id, username)
);
~~~

Cặp organization_id và username là khóa nghiệp vụ. Hai tổ chức khác nhau có thể cùng có username là admin, nhưng một tổ chức không thể có hai tài khoản admin theo quy tắc này.

Một số phạm vi phổ biến:

- Toàn hệ thống: mã hóa đơn toàn cục.
- Theo tenant: mã khách hàng riêng trong từng tổ chức.
- Theo tài khoản: một người chỉ có một địa chỉ giao hàng mặc định.
- Theo sự kiện: một người chỉ có một đăng ký cho một sự kiện.
- Theo trạng thái: chỉ một bản ghi đang hoạt động cho một đối tượng.
- Theo khoảng thời gian: một phòng không có hai lịch đặt chồng lấn.

Nếu chỉ đặt UNIQUE trên username trong ví dụ trên, hệ thống sẽ từ chối username admin ở tổ chức thứ hai dù nghiệp vụ cho phép. Nếu chỉ đặt UNIQUE trên organization_id, mỗi tổ chức chỉ có thể có một người dùng. Phải đưa đầy đủ các thành phần của khóa nghiệp vụ vào ràng buộc.

### 1.3. Quy tắc duy nhất có thể gồm nhiều thuộc tính

Một yêu cầu nghiệp vụ có thể được mô tả bằng tổ hợp:

- Mã sản phẩm + kho hàng.
- Tenant + mã tài liệu.
- Sự kiện + người tham gia.
- Loại chứng từ + năm tài chính + số thứ tự.
- Tài khoản + loại thông báo + ngày gửi.

Ví dụ:

~~~sql
CREATE TABLE event_registration (
    id BIGINT PRIMARY KEY,
    event_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_event_customer
        UNIQUE (event_id, customer_id)
);
~~~

Ràng buộc bảo đảm một customer chỉ có một hàng đăng ký cho một event. Nếu cho phép đăng ký lại sau khi hủy, khóa nghiệp vụ cần được định nghĩa lại theo trạng thái hoặc lịch sử, như phần partial unique index bên dưới.

### 1.4. Phân biệt “trùng giá trị” và “trùng ý nghĩa”

Hai chuỗi giống nhau về ký tự chưa chắc là cùng một định danh nghiệp vụ. Ngược lại, hai chuỗi nhìn khác nhau có thể được nghiệp vụ xem là một.

Ví dụ:

- Email có thể được so sánh không phân biệt hoa thường theo chính sách của sản phẩm.
- Số điện thoại có thể được nhập với dấu cách, dấu gạch hoặc mã quốc gia khác nhau nhưng sau chuẩn hóa lại là cùng một số.
- Mã sản phẩm có thể không phân biệt chữ hoa/thường.
- Tên người hoặc địa chỉ thường không phải khóa duy nhất đáng tin cậy.

Không nên tự chọn một phép so sánh chỉ vì nó tiện về kỹ thuật. Cần định nghĩa quy tắc chuẩn hóa và so sánh theo hợp đồng nghiệp vụ trước khi tạo UNIQUE constraint.

## 2. Vì sao kiểm tra trước khi INSERT không an toàn?

### 2.1. Mẫu check-then-act

Một cách triển khai thường gặp là:

~~~sql
SELECT id
FROM customer
WHERE email = 'linh@example.com';

-- Nếu không tìm thấy thì thêm mới
INSERT INTO customer (id, email)
VALUES (101, 'linh@example.com');
~~~

Cách làm này có race condition khi nhiều giao dịch chạy đồng thời.

Giả sử T1 và T2 cùng thực hiện:

~~~text
T1: SELECT email -> không có hàng
T2: SELECT email -> không có hàng
T1: INSERT email
T2: INSERT email
T1: COMMIT
T2: COMMIT
~~~

Nếu không có ràng buộc UNIQUE, cả hai có thể cùng thành công và tạo dữ liệu trùng. Nếu có UNIQUE, chỉ một giao dịch có thể xác nhận giá trị; giao dịch còn lại nhận lỗi hoặc phải chờ giao dịch đầu tiên kết thúc rồi mới biết kết quả.

Vì vậy, SELECT trước khi ghi chỉ có thể phục vụ trải nghiệm người dùng hoặc tối ưu luồng thông thường. Nó không phải lớp bảo vệ cuối cùng cho tính duy nhất.

### 2.2. Khoảng trống giữa kiểm tra và ghi

Vấn đề nằm ở chỗ hai bước là hai thao tác riêng:

1. Đọc trạng thái hiện tại.
2. Dựa trên trạng thái đó để quyết định ghi.

Một giao dịch khác có thể thay đổi dữ liệu giữa hai bước. Đây là dạng check-then-act race, xuất hiện cả khi kiểm tra số lượng, kiểm tra tồn tại, kiểm tra coupon đã dùng hay kiểm tra một mã đã được cấp.

Mức cô lập REPEATABLE READ không tự làm mẫu này an toàn trong mọi DBMS. Snapshot ổn định có thể khiến hai giao dịch cùng không nhìn thấy hàng mới của nhau. Muốn bảo vệ tính duy nhất, hãy dùng ràng buộc duy nhất hoặc một cơ chế tuần tự hóa được thiết kế rõ ràng.

### 2.3. UNIQUE constraint là điểm quyết định

Cách cơ bản:

~~~sql
INSERT INTO customer (id, email)
VALUES (101, 'linh@example.com');
~~~

Cơ sở dữ liệu tự kiểm tra UNIQUE trong quá trình ghi. Nếu giao dịch khác đang tạo cùng khóa nhưng chưa COMMIT, hệ quản trị phải phối hợp để xác định giao dịch đó cuối cùng thành công hay rollback.

- Nếu giao dịch trước COMMIT, thao tác sau không thể tạo bản ghi trùng.
- Nếu giao dịch trước ROLLBACK, thao tác sau có thể tiếp tục và tạo bản ghi.
- Nếu hàng đã tồn tại từ trước, thao tác ghi bị từ chối theo ràng buộc.

Cơ chế này hoạt động tại nơi dữ liệu được ghi, kể cả khi có nhiều service, batch job hoặc ứng dụng cùng kết nối vào database.

## 3. Chuẩn hóa khóa nghiệp vụ trước khi áp dụng UNIQUE

### 3.1. Email

Nếu chính sách ứng dụng coi email không phân biệt hoa thường, hai giá trị sau có thể được xem là cùng một định danh:

~~~text
Linh@example.com
linh@example.com
~~~

Một cách triển khai là lưu email đã chuẩn hóa vào cột riêng:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    email_normalized VARCHAR(255) NOT NULL,
    CONSTRAINT uq_customer_email_normalized
        UNIQUE (email_normalized)
);
~~~

Ứng dụng chuẩn hóa trước khi ghi, ví dụ loại bỏ khoảng trắng ở hai đầu và áp dụng quy tắc chữ hoa/thường đã thống nhất. Việc chuẩn hóa phải nhất quán ở mọi writer, bao gồm API, batch, import và công cụ quản trị.

Một lựa chọn khác là expression index:

~~~sql
CREATE UNIQUE INDEX uq_customer_lower_email
ON customer (LOWER(email));
~~~

Cú pháp và hành vi expression index phụ thuộc hệ quản trị. PostgreSQL hỗ trợ unique expression index; một số DBMS dùng computed/generated column hoặc function-based index.

Lưu ý: quy tắc email không phân biệt hoa thường cần được quyết định theo chính sách sản phẩm và tiêu chuẩn xử lý email. Không nên tự ý biến mọi thành phần email thành chữ thường nếu hệ thống cần giữ ngữ nghĩa riêng.

### 3.2. Số điện thoại

Không nên dùng chuỗi người dùng nhập trực tiếp làm khóa duy nhất nếu định dạng có thể khác nhau:

~~~text
+84 912 345 678
0912-345-678
(0912) 345 678
~~~

Có thể lưu một giá trị chuẩn hóa theo định dạng quốc tế, sau khi xác định quốc gia và quy tắc chuyển đổi:

~~~sql
CREATE TABLE customer_contact (
    id BIGINT PRIMARY KEY,
    phone_display VARCHAR(40) NOT NULL,
    phone_e164 VARCHAR(20) NOT NULL,
    CONSTRAINT uq_customer_phone_e164 UNIQUE (phone_e164)
);
~~~

Không nên chỉ xóa mọi ký tự không phải số rồi coi kết quả là duy nhất. Mã quốc gia, số nội bộ và số có phần mở rộng cần được xử lý theo quy tắc rõ ràng.

### 3.3. Mã không phân biệt hoa thường hoặc dấu

Nếu mã sản phẩm không phân biệt hoa thường, cần chọn một trong các cách:

- Lưu dạng chuẩn hóa và đặt UNIQUE trên cột chuẩn hóa.
- Dùng collation phù hợp.
- Dùng expression index trên hàm chuẩn hóa.
- Dùng kiểu dữ liệu hoặc operator class chuyên biệt nếu DBMS hỗ trợ.

Nếu quy tắc bỏ dấu cũng được áp dụng, cần định nghĩa rõ thuật toán Unicode normalization, bảng ánh xạ dấu và phiên bản chuẩn hóa. Chỉ dùng LOWER không xử lý mọi trường hợp Unicode hoặc dấu.

### 3.4. Chuẩn hóa phải ổn định theo thời gian

Nếu thuật toán chuẩn hóa thay đổi, khóa đã lưu và khóa mới có thể không còn cùng quy tắc. Ví dụ, một phiên bản thư viện Unicode có thể xử lý một số ký tự khác phiên bản trước.

Khi thay đổi quy tắc chuẩn hóa:

1. Xác định tập dữ liệu có thể trở thành trùng theo quy tắc mới.
2. Xây dựng báo cáo xung đột trước khi áp dụng ràng buộc.
3. Quyết định cách hợp nhất hoặc đổi khóa.
4. Backfill cột chuẩn hóa.
5. Tạo hoặc xác nhận UNIQUE constraint.
6. Chuyển tất cả writer sang quy tắc mới.
7. Loại bỏ đường ghi cũ sau khi xác nhận không còn sử dụng.

Không nên đổi hàm chuẩn hóa rồi tạo UNIQUE index ngay trên dữ liệu lớn mà chưa kiểm tra các giá trị sẽ va chạm.

## 4. Duy nhất theo trạng thái và vòng đời dữ liệu

### 4.1. Chỉ một bản ghi đang hoạt động

Giả sử một khách hàng có thể có nhiều bản ghi đăng ký trong lịch sử, nhưng chỉ được có một đăng ký ACTIVE cho mỗi sự kiện.

Nếu đặt UNIQUE(event_id, customer_id) trên toàn bộ bảng, hàng đã hủy vẫn ngăn người dùng đăng ký lại. Quy tắc thực tế là duy nhất trong tập bản ghi đang hoạt động.

PostgreSQL có thể dùng partial unique index:

~~~sql
CREATE UNIQUE INDEX uq_active_event_customer
ON event_registration (event_id, customer_id)
WHERE status = 'ACTIVE';
~~~

SQL Server có filtered unique index:

~~~sql
CREATE UNIQUE INDEX uq_active_event_customer
ON event_registration (event_id, customer_id)
WHERE status = 'ACTIVE';
~~~

Cú pháp và điều kiện hỗ trợ khác nhau theo sản phẩm. Nếu DBMS không hỗ trợ partial/filtered unique index, có thể dùng generated column, cột khóa có điều kiện hoặc mô hình bảng riêng.

### 4.2. Dùng generated column khi không có partial index

Một mô hình tổng quát là tạo khóa chỉ có giá trị khi hàng đang hoạt động:

~~~text
active_event_id =
    event_id nếu status = ACTIVE
    NULL nếu trạng thái khác
~~~

Sau đó tạo UNIQUE trên (active_event_id, customer_id), nhưng phải kiểm tra semantics NULL của DBMS. Một số hệ quản trị cho phép nhiều NULL trong UNIQUE; một số có quy tắc hoặc cú pháp khác.

Ví dụ minh họa cho hệ quản trị hỗ trợ generated column:

~~~sql
-- Cú pháp thực tế cần điều chỉnh theo DBMS
active_event_id GENERATED ALWAYS AS (
    CASE WHEN status = 'ACTIVE' THEN event_id ELSE NULL END
)
~~~

Nếu hệ quản trị không bảo đảm nhiều hàng NULL được phép trong UNIQUE theo cách cần thiết, hãy dùng thiết kế khác như bảng current_registration riêng hoặc filtered index.

### 4.3. Soft delete và khóa duy nhất

Một bảng dùng deleted_at có thể giữ lại hàng đã xóa mềm:

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    email_normalized VARCHAR(255) NOT NULL,
    deleted_at TIMESTAMP NULL
);
~~~

Nghiệp vụ có thể yêu cầu email chỉ duy nhất trong các tài khoản chưa xóa. Một partial unique index trong PostgreSQL:

~~~sql
CREATE UNIQUE INDEX uq_active_account_email
ON account (email_normalized)
WHERE deleted_at IS NULL;
~~~

Khi tài khoản được soft delete, nó rời khỏi tập chỉ mục. Một tài khoản mới có thể dùng lại email theo quy tắc này.

Nhưng nếu hệ thống cần giữ quyền sở hữu email vĩnh viễn để tránh người khác chiếm lại danh tính cũ, predicate phải khác. Ràng buộc phản ánh chính sách nghiệp vụ; không có một lựa chọn mặc định đúng cho mọi sản phẩm.

### 4.4. Duy nhất theo thời gian

Một quy tắc như “một người chỉ có một hợp đồng hiệu lực tại một thời điểm” không đơn giản là UNIQUE trên person_id vì người đó có thể có nhiều hợp đồng ở các giai đoạn khác nhau.

Cần biểu diễn khoảng hiệu lực và ngăn các khoảng chồng lấn. PostgreSQL hỗ trợ exclusion constraint với range type trong các trường hợp phù hợp:

~~~sql
-- Ví dụ khái niệm với range thời gian
EXCLUDE USING gist (
    person_id WITH =,
    validity_period WITH &&
)
~~~

Toán tử && biểu diễn hai khoảng giao nhau. Cần extension/operator class phù hợp cho kiểu dữ liệu và kiểu khóa; cú pháp đầy đủ phụ thuộc schema cụ thể.

Ở DBMS khác, có thể cần transaction SERIALIZABLE, guard row, bảng lịch theo bucket hoặc một thủ tục giao dịch được thiết kế để tuần tự hóa việc cấp khoảng thời gian.

## 5. NULL và ngữ nghĩa của UNIQUE

Một điểm dễ gây lỗi là cách DBMS xử lý NULL trong UNIQUE.

Trong SQL, NULL biểu thị giá trị chưa biết hoặc không áp dụng; nó không giống một giá trị bình thường. Vì vậy, các hệ quản trị có thể cho phép nhiều hàng NULL trong một cột UNIQUE hoặc áp dụng quy tắc khác.

Ví dụ:

~~~sql
CREATE TABLE employee (
    id BIGINT PRIMARY KEY,
    national_id VARCHAR(30) UNIQUE
);
~~~

Nếu national_id được phép NULL, số hàng NULL có thể phụ thuộc DBMS. Không nên giả định mọi hệ thống đều xử lý giống nhau.

Các hướng thiết kế:

- Nếu thuộc tính bắt buộc duy nhất và luôn phải có, khai báo NOT NULL cùng UNIQUE.
- Nếu NULL có nghĩa “chưa cung cấp” và được phép lặp, kiểm tra semantics DBMS.
- Nếu chỉ cần duy nhất với giá trị khác NULL, dùng partial/filtered unique index khi được hỗ trợ.
- Nếu NULL mang một trạng thái nghiệp vụ riêng, cân nhắc biểu diễn trạng thái đó bằng cột riêng thay vì dựa vào hành vi NULL ngầm định.

Cũng cần kiểm tra cách ORM và driver gửi NULL, default và giá trị rỗng. Chuỗi rỗng không nhất thiết tương đương NULL; Oracle có quy tắc riêng với chuỗi rỗng trong một số kiểu dữ liệu.

## 6. Duy nhất trong một tập hợp và quy tắc liên hàng

### 6.1. Một hàng chỉ có thể kiểm tra một phần quy tắc

CHECK constraint thường kiểm tra giá trị trong chính hàng được thêm hoặc cập nhật. Nó không phải công cụ tổng quát để bảo đảm một điều kiện duy nhất trên nhiều hàng.

Ví dụ, quy tắc “mỗi khách hàng chỉ có một hóa đơn chưa thanh toán” là quy tắc liên hàng. Một CHECK trên từng hóa đơn không thể tự đếm các hàng khác một cách an toàn.

Có thể dùng partial unique index:

~~~sql
CREATE UNIQUE INDEX uq_one_unpaid_invoice_per_customer
ON invoice (customer_id)
WHERE status = 'UNPAID';
~~~

Nếu DBMS hỗ trợ, đây là cách diễn đạt trực tiếp: trong tập hóa đơn UNPAID, mỗi customer_id chỉ xuất hiện một lần.

### 6.2. Dùng guard row khi không thể tạo constraint trực tiếp

Một số quy tắc liên hàng không thể biểu diễn bằng UNIQUE hoặc exclusion constraint. Có thể tạo một hàng đại diện cho phạm vi cần bảo vệ.

Ví dụ, mỗi kho có một trạng thái điều phối:

~~~sql
CREATE TABLE warehouse_guard (
    warehouse_id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL
);
~~~

Mọi giao dịch thay đổi phân bổ tồn kho trong cùng kho phải khóa hoặc cập nhật hàng guard trước khi kiểm tra và ghi dữ liệu liên quan:

~~~sql
BEGIN;

SELECT warehouse_id
FROM warehouse_guard
WHERE warehouse_id = 10
FOR UPDATE;

-- Kiểm tra và ghi các hàng tồn kho liên quan.

COMMIT;
~~~

Hàng guard tạo một điểm tuần tự hóa rõ ràng. Tất cả writer phải tuân thủ cùng giao thức; nếu một đường ghi bỏ qua guard, bất biến vẫn có thể bị vi phạm.

Nhược điểm là các thao tác cùng phạm vi bị tuần tự hóa trên một hàng. Nếu một kho có lưu lượng rất cao, guard row có thể trở thành hot row.

### 6.3. Dùng SERIALIZABLE khi quy tắc phụ thuộc predicate

Một lựa chọn là chạy kiểm tra và ghi trong transaction SERIALIZABLE. Hệ quản trị có thể khóa phạm vi hoặc theo dõi phụ thuộc để ngăn lịch thực thi không tuần tự hóa được.

Ví dụ:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM reservation
WHERE room_id = 10
  AND start_time < :end_time
  AND end_time > :start_time;

-- Nếu không có lịch chồng lấn thì INSERT.

COMMIT;
~~~

Hai giao dịch cùng kiểm tra một predicate rồi cùng INSERT có thể khiến một giao dịch nhận serialization failure hoặc bị chặn, tùy DBMS. Ứng dụng phải retry toàn bộ transaction khi nhận đúng lỗi có thể phục hồi.

SERIALIZABLE không thay thế ràng buộc đơn giản có thể biểu diễn bằng UNIQUE. Với khóa duy nhất trực tiếp, constraint thường dễ hiểu và ít phụ thuộc vào logic ứng dụng hơn.

## 7. Xử lý lỗi UNIQUE trong ứng dụng

### 7.1. Phân biệt lỗi trùng với lỗi cơ sở dữ liệu khác

Một INSERT có thể thất bại vì nhiều lý do:

- Vi phạm UNIQUE.
- Vi phạm PRIMARY KEY.
- Vi phạm FOREIGN KEY.
- Vi phạm CHECK hoặc NOT NULL.
- Deadlock.
- Lock timeout.
- Mất kết nối.
- Lỗi cú pháp hoặc lỗi tài nguyên.

Không nên bắt mọi exception rồi trả về “đã tồn tại”. Hãy phân loại theo mã lỗi SQLSTATE/vendor code và tên constraint nếu driver cung cấp.

Một số mã thường gặp:

| Hệ quản trị | Mã lỗi thường gặp cho UNIQUE |
|---|---|
| PostgreSQL | SQLSTATE 23505 |
| MySQL | Error 1062 |
| SQL Server | Error 2601 hoặc 2627 |
| Oracle | ORA-00001 |

Mã lỗi có thể được bọc trong exception của framework. Cần kiểm tra exception cause chain và metadata constraint để phân biệt đúng loại vi phạm.

### 7.2. Không dựa vào thông báo lỗi dạng văn bản

Thông báo lỗi có thể thay đổi theo phiên bản, ngôn ngữ hoặc driver. Không nên tìm chuỗi “Duplicate entry” trong message để quyết định logic nghiệp vụ nếu có thể dùng mã lỗi có cấu trúc.

Tên constraint cũng hữu ích. Ví dụ, uq_customer_email có thể được ánh xạ thành lỗi “email đã được sử dụng”, trong khi uq_org_username có thể thành “username đã tồn tại trong tổ chức”.

Không nên tiết lộ giá trị nhạy cảm hoặc thông tin tài khoản khác trong lỗi trả về cho client.

### 7.3. Trạng thái transaction sau lỗi

Sau lỗi constraint, trạng thái transaction phụ thuộc DBMS:

- PostgreSQL đánh dấu transaction hiện tại là aborted sau lỗi statement; phải rollback hoặc rollback to savepoint trước khi chạy câu lệnh tiếp theo.
- SQL Server có thể để transaction ở trạng thái không thể commit tùy lỗi và cấu hình XACT_ABORT; cần kiểm tra XACT_STATE.
- MySQL InnoDB thường rollback statement vi phạm nhưng transaction có thể còn hoạt động; vẫn cần xử lý theo loại lỗi và trạng thái cụ thể.
- Oracle thường rollback statement gây lỗi, transaction có thể tiếp tục nếu ứng dụng xử lý phù hợp.

Đừng giả định một hành vi chung cho mọi hệ quản trị. Framework transaction manager cũng có thể đánh dấu transaction rollback-only dù DBMS cho phép tiếp tục.

## 8. Upsert và xử lý khi khóa đã tồn tại

### 8.1. UPSERT là gì?

UPSERT kết hợp thao tác thêm mới với xử lý khi khóa duy nhất đã tồn tại. Nó hữu ích khi nghiệp vụ cho phép “tạo nếu chưa có” hoặc “cập nhật bản ghi hiện có”.

PostgreSQL:

~~~sql
INSERT INTO customer (id, email_normalized, display_name)
VALUES (101, 'linh@example.com', 'Linh')
ON CONFLICT (email_normalized)
DO UPDATE
SET display_name = EXCLUDED.display_name;
~~~

MySQL:

~~~sql
INSERT INTO customer (id, email_normalized, display_name)
VALUES (101, 'linh@example.com', 'Linh')
ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name);
~~~

Cú pháp MySQL có khác biệt giữa các phiên bản; hãy dùng cú pháp được hỗ trợ trong phiên bản đang chạy.

SQL Server thường dùng INSERT/UPDATE riêng trong transaction hoặc một mẫu có khóa phù hợp; MERGE có các lưu ý concurrency và không nên dùng như một cách tự động bảo đảm mọi trường hợp.

### 8.2. Chọn đúng conflict target

Nếu bảng có nhiều UNIQUE constraint, cần xác định xung đột nào được xử lý như một nhánh UPSERT.

Ví dụ, customer có email duy nhất và external_id duy nhất. Một INSERT có thể xung đột ở một trong hai khóa. Không nên mặc định mọi xung đột đều có nghĩa là cùng một khách hàng.

PostgreSQL cho phép chỉ rõ conflict target, chẳng hạn ON CONFLICT (email_normalized). Nếu xung đột ở một UNIQUE khác không thuộc target, thao tác vẫn có thể lỗi.

MySQL ON DUPLICATE KEY UPDATE phản ứng với xung đột khóa duy nhất/primary key; khi có nhiều unique index, cần đặc biệt cẩn thận để không cập nhật nhầm hàng theo khóa khác với khóa nghiệp vụ mong muốn.

### 8.3. UPSERT không đồng nghĩa idempotency hoàn chỉnh

Một UPSERT có thể ngăn tạo hai hàng cùng khóa, nhưng nó vẫn có thể chạy lại phần UPDATE nhiều lần.

Ví dụ, nếu mỗi lần retry đều:

~~~sql
UPDATE account
SET balance = balance - 100
WHERE id = 10;
~~~

thì việc bọc thao tác vào một cú pháp UPSERT không làm phép trừ trở nên idempotent. Một yêu cầu bị gửi hai lần vẫn có thể trừ tiền hai lần.

UPSERT giải quyết xung đột khi tạo hàng theo khóa duy nhất. Idempotency cần nhận diện cùng một yêu cầu nghiệp vụ và bảo đảm tác dụng của yêu cầu đó chỉ được áp dụng một lần.

### 8.4. Tránh REPLACE nếu không muốn xóa rồi tạo lại

Một số DBMS có cú pháp REPLACE hoặc hành vi tương tự. Trong MySQL, REPLACE có thể xóa hàng cũ rồi chèn hàng mới khi gặp xung đột khóa duy nhất.

Điều này có thể gây tác dụng phụ:

- Thay đổi giá trị khóa hoặc cột không được truyền.
- Kích hoạt DELETE/INSERT trigger.
- Ảnh hưởng khóa ngoại và cascade.
- Thay đổi audit/history.
- Cấp lại giá trị auto-increment.
- Làm mất dữ liệu cũ không có trong câu lệnh mới.

Nếu nghiệp vụ muốn cập nhật có chọn lọc, dùng UPSERT/UPDATE có chủ đích và xác định rõ các cột được thay đổi.

## 9. Yêu cầu trùng và idempotency

### 9.1. Vì sao một yêu cầu có thể đến nhiều lần?

Trong hệ thống phân tán, client không phải lúc nào cũng biết server đã xử lý yêu cầu hay chưa.

Ví dụ:

1. Client gửi yêu cầu tạo đơn hàng.
2. Server tạo đơn và COMMIT.
3. Response bị mất trên đường truyền.
4. Client timeout và gửi lại yêu cầu.
5. Server nhận một request mới về mặt kết nối nhưng thực chất là cùng ý định nghiệp vụ.

Nếu server xử lý lần hai như một lệnh mới, nó có thể tạo hai đơn hàng hoặc thu tiền hai lần.

Các nguồn gửi trùng thường gặp:

- Người dùng bấm nút nhiều lần.
- Browser/app tự retry khi timeout.
- API gateway retry request.
- Mobile client gửi lại sau khi đổi mạng.
- Webhook provider giao lại event khi không nhận được phản hồi.
- Message broker giao message ít nhất một lần.
- Worker bị crash sau khi hoàn tất tác dụng phụ nhưng trước khi ACK.

### 9.2. Idempotent operation

Một thao tác idempotent có tính chất: thực hiện nhiều lần với cùng một định danh yêu cầu và cùng nội dung sẽ không làm thay đổi kết quả nghiệp vụ sau lần đầu.

Ví dụ:

- Đặt trạng thái đơn hàng thành SHIPPED có thể idempotent nếu việc lặp lại không tạo thêm tác dụng phụ.
- Cộng thêm 100 vào số dư không idempotent; mỗi lần chạy làm số dư tăng thêm 100.
- Ghi nhận một webhook có event_id duy nhất có thể idempotent nếu event_id được bảo vệ bằng UNIQUE.

Idempotency không có nghĩa mọi câu SQL phải trả cùng số hàng hoặc cùng metadata. Nó có nghĩa một yêu cầu lặp lại không tạo thêm một lần thực hiện nghiệp vụ.

### 9.3. Idempotency key

Client gửi một khóa nhận diện lần thực hiện nghiệp vụ:

~~~http
POST /payments
Idempotency-Key: 7f8b0e2a-...
Content-Type: application/json
~~~

Server lưu khóa cùng phạm vi và kết quả xử lý. Nếu cùng khóa được gửi lại:

- Nếu yêu cầu trước đã hoàn tất với cùng payload, trả lại kết quả đã lưu.
- Nếu yêu cầu đang được xử lý, chờ, trả trạng thái đang xử lý hoặc cung cấp cơ chế polling theo hợp đồng API.
- Nếu cùng khóa nhưng payload khác, từ chối vì client đã dùng lại một key cho ý định khác.

Idempotency key nên được tạo ở phía client hoặc tầng điều phối và phải ổn định qua các lần retry của cùng một thao tác.

### 9.4. Phạm vi của idempotency key

Không nên đặt UNIQUE trên key đơn lẻ nếu key chỉ duy nhất trong một khách hàng hoặc một endpoint.

Một bảng có thể lưu:

~~~sql
CREATE TABLE idempotency_record (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    operation VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(30) NOT NULL,
    response_code INT,
    response_body TEXT,
    created_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    CONSTRAINT uq_idempotency_scope
        UNIQUE (tenant_id, operation, idempotency_key)
);
~~~

Khóa duy nhất gồm tenant, operation và idempotency_key. Nhờ vậy:

- Hai tenant khác nhau có thể dùng cùng chuỗi key.
- Hai loại thao tác có thể có namespace riêng.
- Một client không thể vô tình tái sử dụng cùng key cho hai lần thực hiện trong cùng phạm vi.

Phạm vi cụ thể phụ thuộc hợp đồng API. Nếu key được quy định duy nhất toàn hệ thống, schema phải phản ánh đúng điều đó.

### 9.5. Request hash để phát hiện dùng lại key sai nội dung

Khi nhận request, server tính hash từ payload đã chuẩn hóa và các trường ảnh hưởng đến nghiệp vụ.

Ví dụ, cùng key được gửi lần đầu với:

~~~json
{
  "account_id": 10,
  "amount": 100
}
~~~

Nhưng lần sau lại gửi:

~~~json
{
  "account_id": 10,
  "amount": 500
}
~~~

Nếu server chỉ kiểm tra key mà không so sánh payload, request thứ hai có thể nhận nhầm kết quả của lần đầu hoặc làm thay đổi ý nghĩa xử lý.

Lưu request_hash giúp phát hiện trường hợp cùng key nhưng nội dung khác. Cần chuẩn hóa payload trước khi hash để khác biệt không quan trọng về thứ tự thuộc tính JSON hoặc định dạng không làm thay đổi hash một cách không mong muốn.

Hash không thay thế kiểm tra quyền truy cập. Khi replay response, server vẫn phải xác thực caller và phạm vi tenant theo chính sách hiện hành.

## 10. Lưu idempotency record một cách nguyên tử

### 10.1. Mẫu đơn giản trong một transaction

Với nghiệp vụ có thể hoàn tất trong một transaction database, có thể thực hiện:

1. Thử INSERT idempotency record với key duy nhất.
2. Nếu INSERT thành công, transaction sở hữu quyền xử lý key đó.
3. Thực hiện thay đổi nghiệp vụ.
4. Lưu response hoặc kết quả.
5. COMMIT cả thay đổi nghiệp vụ và idempotency record cùng lúc.

Sơ đồ:

~~~text
BEGIN
  |
  v
INSERT idempotency key (UNIQUE)
  |
  +-- key đã tồn tại --> đọc trạng thái/kết quả cũ
  |
  +-- key mới --------> thực hiện nghiệp vụ
                           |
                           v
                      lưu kết quả
                           |
                           v
                         COMMIT
~~~

Nếu transaction rollback, cả thay đổi nghiệp vụ và idempotency record chưa hoàn tất đều rollback. Một lần retry có thể thử chiếm key và xử lý lại.

Nếu transaction commit thành công nhưng response bị mất, lần retry tìm thấy record đã hoàn tất và trả lại kết quả đã lưu.

### 10.2. Hai request cùng key đến đồng thời

Giả sử hai request R1 và R2 cùng dùng một idempotency key.

- R1 INSERT record trước.
- R2 INSERT cùng khóa duy nhất và phải chờ kết quả transaction R1 hoặc nhận conflict sau khi R1 commit.
- Nếu R1 commit, R2 đọc record đã lưu và replay kết quả.
- Nếu R1 rollback, R2 có thể chiếm key và thực hiện nghiệp vụ.

Unique constraint là cơ chế phân xử giữa các request đồng thời. Một câu SELECT xem key đã tồn tại trước khi INSERT vẫn có race condition giống kiểm tra email.

### 10.3. Vì sao không nên commit một record PROCESSING quá sớm mà thiếu cơ chế phục hồi?

Với một transaction ngắn, có thể giữ idempotency record và kết quả nghiệp vụ trong cùng transaction. Các request trùng thường phải chờ đến khi transaction đầu hoàn tất rồi mới đọc được kết quả.

Với công việc dài hoặc gọi dịch vụ ngoài, hệ thống có thể muốn commit trạng thái PROCESSING trước khi thực hiện. Khi đó cần thiết kế thêm:

- Lease hoặc thời điểm hết hạn của worker.
- Owner/attempt token để chỉ worker hợp lệ được hoàn tất.
- Cơ chế phát hiện công việc bị bỏ dở.
- Quy trình retry hoặc takeover sau khi lease hết hạn.
- Trạng thái FAILED/RETRYABLE rõ ràng.
- Cơ chế bảo vệ tác dụng phụ ngoài database.

Nếu worker crash sau khi đánh dấu PROCESSING, key có thể bị kẹt vĩnh viễn nếu không có lease/recovery. Nếu worker khác tự xử lý lại trong khi worker cũ vẫn chạy, tác dụng phụ có thể bị thực hiện hai lần.

### 10.4. Lưu response để replay

Idempotency record có thể lưu:

- HTTP status code.
- Response body hoặc resource ID.
- Các header cần thiết như Location hoặc ETag.
- Thời điểm hoàn tất.
- Hash request.
- Mã lỗi nghiệp vụ nếu hợp đồng yêu cầu replay lỗi.

Khi request lặp lại, trả kết quả tương đương với lần đầu. Không nhất thiết lưu mọi header kỹ thuật như Date hoặc trace ID; hãy xác định response nào thuộc kết quả nghiệp vụ cần replay.

Nếu dữ liệu nhạy cảm, response lưu trữ cần được bảo vệ, phân quyền và có chính sách retention.

## 11. Idempotency cho thanh toán và tác dụng phụ ngoài database

### 11.1. Không thể rollback một hệ thống bên ngoài

Một transaction database không thể tự rollback khoản thanh toán đã được cổng thanh toán chấp nhận. Nếu server gọi cổng thanh toán rồi crash trước khi lưu kết quả, lần retry có thể gọi thanh toán lần nữa.

Nên truyền idempotency key xuống provider nếu provider hỗ trợ, dùng cùng một key cho cùng ý định thanh toán. Đồng thời lưu trạng thái giao dịch nội bộ và correlation ID để đối soát.

Không tự tạo key mới mỗi lần retry. Key mới có thể khiến provider xem đó là một khoản thanh toán mới.

### 11.2. Transactional outbox

Một mẫu thường dùng là ghi thay đổi nghiệp vụ và event cần phát vào outbox trong cùng transaction:

~~~sql
BEGIN;

INSERT INTO payment (...);

INSERT INTO outbox_event (
    event_id,
    aggregate_id,
    event_type,
    payload,
    created_at
)
VALUES (...);

COMMIT;
~~~

Một worker đọc outbox và gửi event ra message broker. Nếu worker gửi event thành công nhưng crash trước khi đánh dấu đã gửi, event có thể được gửi lại. Consumer vẫn cần dedup theo event_id hoặc xử lý idempotent.

Outbox bảo đảm sự kiện được ghi cùng thay đổi database. Nó không tự biến việc giao message thành exactly-once ở mọi hệ thống.

### 11.3. Inbox/dedup ở consumer

Consumer có thể lưu event đã xử lý:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    message_id VARCHAR(200) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_processed_message
        UNIQUE (consumer_name, message_id)
);
~~~

Trong cùng transaction:

1. INSERT message_id vào bảng processed_message.
2. Nếu insert thành công, áp dụng thay đổi nghiệp vụ.
3. COMMIT.
4. Nếu key đã tồn tại, bỏ qua tác dụng phụ và ACK message.

Bảng dedup và thay đổi nghiệp vụ phải commit cùng nhau. Nếu đánh dấu đã xử lý trước rồi crash trước khi cập nhật dữ liệu, message sẽ bị bỏ qua dù tác dụng nghiệp vụ chưa xảy ra.

## 12. Xử lý webhook giao nhiều lần

Webhook provider thường có thể gửi lại event khi server timeout, lỗi mạng hoặc response không thành công.

Một mẫu xử lý:

~~~sql
CREATE TABLE webhook_event (
    provider VARCHAR(50) NOT NULL,
    event_id VARCHAR(200) NOT NULL,
    payload_hash VARCHAR(128) NOT NULL,
    status VARCHAR(30) NOT NULL,
    received_at TIMESTAMP NOT NULL,
    processed_at TIMESTAMP,
    CONSTRAINT uq_provider_event
        UNIQUE (provider, event_id)
);
~~~

Khi nhận webhook:

1. Xác thực chữ ký và nguồn gửi.
2. Xác định provider và event_id ổn định.
3. INSERT event vào bảng với UNIQUE(provider, event_id).
4. Nếu mới, xử lý event trong transaction hoặc đưa vào queue theo thiết kế.
5. Nếu đã có, kiểm tra trạng thái và không lặp tác dụng phụ.
6. Trả response theo hợp đồng của provider.

Không dùng hash toàn payload làm định danh duy nhất nếu provider đã cấp event ID. Hai event khác nhau có thể có payload giống nhau nhưng vẫn là hai sự kiện nghiệp vụ riêng. Ngược lại, cùng một event có thể được gửi với metadata truyền tải khác nhau.

## 13. Thời hạn lưu idempotency key

Idempotency record không nhất thiết phải được giữ mãi mãi, nhưng thời hạn phải phù hợp với cửa sổ retry thực tế.

Cần cân nhắc:

- Client có thể retry trong bao lâu?
- API gateway hoặc provider webhook retry trong bao lâu?
- Message có thể được phát lại sau bao lâu?
- Một thao tác thanh toán có yêu cầu tra soát lâu dài không?
- Sau khi xóa record, cùng key có thể bị dùng lại và tạo tác dụng phụ mới không?

Nếu xóa record quá sớm, một request cũ được gửi lại sau thời hạn có thể bị xử lý như request mới. Với nghiệp vụ tài chính hoặc chứng từ, có thể cần giữ dấu vết lâu hơn hoặc lưu một tombstone nhỏ sau khi response chi tiết hết hạn.

Cần tài liệu hóa thời hạn key trong API. Client không nên tự giả định một key được bảo vệ vĩnh viễn nếu server chỉ giữ trong một khoảng thời gian.

## 14. Phân biệt các loại “trùng” và cách xử lý

| Tình huống | Ví dụ | Cơ chế chính |
|---|---|---|
| Trùng khóa nghiệp vụ | Hai tài khoản cùng email chuẩn hóa | UNIQUE constraint/index |
| Trùng trong phạm vi tenant | Hai mã khách hàng giống nhau trong cùng tổ chức | Composite UNIQUE |
| Trùng theo trạng thái | Hai hóa đơn UNPAID cho cùng khách hàng | Partial/filtered unique hoặc mô hình tương đương |
| Trùng theo khoảng thời gian | Hai lịch phòng chồng lấn | Exclusion constraint, SERIALIZABLE hoặc guard row |
| Request gửi lại | Client retry tạo đơn hàng sau timeout | Idempotency key + kết quả lưu trữ |
| Webhook giao lại | Provider gửi cùng event nhiều lần | UNIQUE(provider, event_id) + xử lý nguyên tử |
| Message broker redelivery | Consumer nhận lại message | Inbox/dedup key + transaction |
| Người dùng gửi hai ý định riêng | Hai lần mua hàng thật sự khác nhau | Hai request ID/key khác nhau; áp dụng quy tắc nghiệp vụ bình thường |

Hai request có payload giống nhau chưa chắc là cùng một ý định. Người dùng có thể thực sự muốn mua hai sản phẩm giống nhau ở hai thời điểm khác nhau. Vì vậy, không nên dùng hash payload làm idempotency key toàn cục để tự động loại bỏ mọi request giống nội dung.

## 15. Thiết kế API khi gặp xung đột duy nhất

### 15.1. Mã trạng thái và nội dung lỗi

Khi client tạo tài nguyên với khóa nghiệp vụ đã tồn tại, API có thể trả lỗi conflict theo hợp đồng, ví dụ HTTP 409 Conflict:

~~~json
{
  "code": "CUSTOMER_EMAIL_ALREADY_EXISTS",
  "message": "Email đã được sử dụng."
}
~~~

Nếu lỗi là điều kiện If-Match không còn đúng, HTTP 412 Precondition Failed có thể phù hợp hơn. Nếu cùng idempotency key nhưng payload khác, API có thể trả 409 với mã lỗi riêng.

Không nên trả stack trace, tên bảng nội bộ hoặc dữ liệu của hàng đang tồn tại. Lỗi nên đủ rõ để client biết cần sửa input, tải lại dữ liệu hay dùng key khác.

### 15.2. Phân biệt conflict nghiệp vụ và retryable error

- UNIQUE violation thường là xung đột dữ liệu cần xử lý theo nghiệp vụ.
- Deadlock thường có thể retry toàn transaction.
- Serialization failure có thể retry toàn transaction.
- Lock timeout cần chính sách riêng.
- Mất kết nối khi COMMIT có thể tạo trạng thái không chắc chắn: server không biết client đã nhận kết quả hay chưa. Idempotency key giúp client gửi lại và lấy kết quả đã lưu.

Không retry mọi lỗi như nhau. Retry một UNIQUE violation với cùng dữ liệu thường chỉ lặp lại lỗi; retry deadlock với transaction mới có thể thành công.

### 15.3. Trả lại tài nguyên đã tồn tại hay báo lỗi?

Tùy nghiệp vụ, khi tạo tài nguyên đã tồn tại, API có thể:

- Trả 409 và yêu cầu client xử lý.
- Trả thông tin tài nguyên hiện có nếu caller có quyền.
- Trả thành công nếu thao tác được định nghĩa là “ensure exists” và trạng thái đã đạt đúng kết quả mong muốn.
- Cập nhật tài nguyên hiện có nếu đây là UPSERT có chủ đích.

Không nên mặc định mọi duplicate đều phải trả 200 hoặc mọi duplicate đều phải trả 409. Hợp đồng API cần phân biệt “đã tồn tại trước request”, “request này đã được xử lý trước đó” và “một request khác đang xử lý cùng key”.

## 16. Kiểm thử tính duy nhất và xử lý yêu cầu trùng

### 16.1. Kiểm thử UNIQUE với hai transaction đồng thời

Một kiểm thử cần chứng minh database chặn được race condition:

1. Tạo bảng với UNIQUE(email_normalized).
2. Mở hai connection và hai transaction độc lập.
3. Dùng barrier để cả hai cùng bắt đầu INSERT cùng giá trị chuẩn hóa.
4. Cho phép hai thao tác chạy đồng thời.
5. Xác nhận chỉ một hàng được commit.
6. Xác nhận giao dịch còn lại nhận duplicate-key error hoặc kết quả conflict theo DBMS.
7. Đọc lại bảng và xác nhận không có hai hàng cùng khóa nghiệp vụ.

Không dùng Thread.sleep làm cơ chế đồng bộ chính vì thứ tự chạy có thể thay đổi giữa các lần test.

### 16.2. Kiểm thử scope

Tạo hai hàng:

- Tenant 1 có username admin.
- Tenant 2 cũng có username admin.

Nếu quy tắc là duy nhất trong tenant, cả hai phải được phép. Sau đó thử thêm admin thứ hai vào tenant 1 và xác nhận bị từ chối.

Kiểm thử này giúp phát hiện việc đặt UNIQUE sai phạm vi.

### 16.3. Kiểm thử chuẩn hóa

Thử các đầu vào tương đương theo chính sách:

- Khác chữ hoa/thường.
- Có khoảng trắng đầu/cuối.
- Số điện thoại có dấu cách hoặc dấu gạch.
- Ký tự Unicode ở dạng normalization khác nhau.
- Mã có số 0 đầu.

Xác nhận các giá trị được chuẩn hóa theo đúng hợp đồng trước khi ghi và UNIQUE thực sự bảo vệ cột chuẩn hóa.

### 16.4. Kiểm thử idempotency với response bị mất

Mô phỏng:

1. Gửi request với key K.
2. Server commit nghiệp vụ và lưu response.
3. Giả lập response bị mất trước khi client nhận.
4. Gửi lại cùng key K và payload.
5. Xác nhận server trả lại cùng kết quả nghiệp vụ.
6. Xác nhận chỉ có một đơn hàng hoặc một lần ghi nhận thanh toán.

Tiếp tục gửi cùng K nhưng payload khác và xác nhận API trả conflict theo hợp đồng.

### 16.5. Kiểm thử hai request cùng key đến đồng thời

Dùng hai connection hoặc hai request đồng thời:

- Cả hai cùng INSERT idempotency key K.
- Chỉ một request sở hữu quyền thực hiện nghiệp vụ.
- Request còn lại đọc kết quả hoặc trạng thái của request đầu.
- Không có tác dụng phụ bị thực hiện hai lần.

Cần test cả trường hợp request đầu rollback, để request thứ hai có thể xử lý theo đúng chính sách.

### 16.6. Kiểm thử crash và recovery

Với quy trình có trạng thái PROCESSING hoặc worker bất đồng bộ, mô phỏng crash ở các điểm:

- Sau khi tạo idempotency record.
- Sau khi gọi dịch vụ ngoài.
- Sau khi commit nghiệp vụ nhưng trước khi ACK message.
- Sau khi phát event nhưng trước khi đánh dấu outbox đã gửi.

Xác nhận lease, retry, outbox và consumer dedup không làm mất tác dụng nghiệp vụ hoặc nhân đôi tác dụng phụ.

## 17. Quan sát và vận hành

Một hệ thống chống trùng cần số liệu để phân biệt xung đột bình thường với lỗi thiết kế hoặc tải bất thường.

Các chỉ số hữu ích:

| Nhóm | Chỉ số | Ý nghĩa |
|---|---|---|
| Business key | Số UNIQUE violation theo constraint | Khóa nghiệp vụ nào thường bị tranh |
| API | Tỷ lệ HTTP 409 theo loại lỗi | Mức xung đột mà client gặp |
| Idempotency | Số request replay | Tần suất client/provider gửi lại |
| Idempotency | Số lần cùng key nhưng payload hash khác | Lỗi client hoặc dùng key sai |
| Processing | Số record PROCESSING quá hạn | Worker crash hoặc lease/recovery lỗi |
| Payment | Số lần provider báo cùng transaction/event ID | Kiểm tra tác dụng phụ trùng |
| Queue | Số message redelivery và dedup hit | Hành vi giao lại message |
| Database | Lock wait/deadlock trên unique index hoặc guard row | Điểm contention |
| Retention | Số key hết hạn và bị dọn | Rủi ro cửa sổ retry |

Log nên ghi correlation ID, tenant, operation, idempotency key ở dạng đã bảo vệ phù hợp và mã constraint. Tránh ghi payload thanh toán hoặc dữ liệu cá nhân đầy đủ chỉ để điều tra duplicate.

Khi key là thông tin có thể bị lạm dụng, cần tránh đưa nguyên văn vào log công khai. Có thể log hash hoặc một phần đã che.

## 18. Những lỗi thiết kế thường gặp

**Chỉ SELECT kiểm tra rồi mới INSERT.**

Hai transaction có thể cùng không thấy hàng và cùng thêm. Dùng UNIQUE constraint làm lớp bảo vệ cuối cùng.

**Dùng khóa chính thay cho khóa nghiệp vụ.**

Hai hàng có id khác nhau vẫn có thể vi phạm quy tắc email, username hoặc mã chứng từ. Đặt UNIQUE trên đúng thuộc tính nghiệp vụ.

**Đặt UNIQUE sai phạm vi.**

Nếu username duy nhất theo tenant, UNIQUE(username) sẽ từ chối dữ liệu hợp lệ giữa các tenant. Dùng composite key đúng phạm vi.

**Chuẩn hóa ở một API nhưng bỏ qua batch/import.**

Một đường ghi không chuẩn hóa có thể tạo giá trị mà đường ghi khác không nhận diện là trùng. Đưa chuẩn hóa vào một thư viện/chính sách dùng chung và bảo vệ cột chuẩn hóa bằng UNIQUE.

**Dùng UPSERT để chống mọi request trùng.**

UPSERT ngăn hoặc xử lý xung đột khóa hàng. Nó không ngăn một lệnh cộng tiền hoặc tạo tác dụng phụ chạy hai lần. Dùng idempotency key cho cùng một ý định request.

**Dùng payload hash làm idempotency key toàn cục.**

Hai lần mua hàng giống nhau có thể là hai ý định riêng. Idempotency key phải đại diện cho một lần thực hiện cụ thể và có phạm vi rõ ràng.

**Lưu idempotency key sau khi đã thực hiện nghiệp vụ.**

Nếu server crash sau khi tạo đơn nhưng trước khi lưu key, retry có thể tạo đơn thứ hai. Lưu dấu key và thay đổi nghiệp vụ trong cùng transaction khi có thể.

**Đánh dấu message đã xử lý trước khi commit thay đổi.**

Nếu crash sau khi đánh dấu nhưng trước khi thay đổi nghiệp vụ, message sẽ bị bỏ qua. Ghi inbox/dedup và thay đổi dữ liệu trong cùng transaction.

**Tự động retry mọi duplicate-key error.**

Lỗi UNIQUE có thể là xung đột nghiệp vụ thật. Retry mù quáng không làm dữ liệu đầu vào trở nên hợp lệ.

**Xóa idempotency record quá sớm.**

Request cũ được gửi lại sau khi record bị xóa có thể thực hiện nghiệp vụ lần nữa. Retention phải phù hợp cửa sổ retry và yêu cầu đối soát.

## 19. Quy trình thiết kế và xử lý yêu cầu trùng

Khi xây dựng một chức năng có nguy cơ tạo dữ liệu trùng, hãy đi theo các bước:

1. **Viết quy tắc nghiệp vụ thành điều kiện rõ ràng.** Giá trị nào phải duy nhất, trong phạm vi nào, theo trạng thái nào và theo cách so sánh nào?
2. **Xác định khóa nghiệp vụ.** Chọn một cột hoặc tổ hợp cột đại diện cho quy tắc đó.
3. **Chuẩn hóa dữ liệu.** Quy định cách xử lý hoa/thường, khoảng trắng, Unicode, mã quốc gia, collation và giá trị NULL.
4. **Đặt constraint/index tại database.** Dùng PRIMARY KEY, UNIQUE, composite UNIQUE, partial/filtered unique hoặc exclusion constraint khi phù hợp.
5. **Xây dựng cách xử lý conflict.** Ánh xạ lỗi constraint thành kết quả API hoặc nhánh nghiệp vụ rõ ràng.
6. **Phân biệt request retry.** Xác định thao tác nào cần idempotency key và phạm vi của key.
7. **Lưu key và kết quả nguyên tử.** Với tác dụng phụ ngoài database, dùng provider idempotency, outbox, inbox hoặc workflow có lease/recovery.
8. **Thiết kế retention.** Giữ idempotency record đủ lâu và có quy tắc dọn dẹp an toàn.
9. **Kiểm thử đồng thời.** Dùng nhiều transaction thực sự chạy song song, không chỉ test tuần tự.
10. **Theo dõi vận hành.** Đo unique violation, replay, payload mismatch, stuck processing và retry.

## 20. Câu hỏi định hướng

Trước khi triển khai, hãy trả lời:

- Đối tượng nào phải duy nhất: hàng dữ liệu, mã nghiệp vụ, quan hệ hay một lần thực hiện request?
- Tính duy nhất áp dụng toàn hệ thống hay theo tenant/tài khoản/sự kiện?
- Giá trị có cần chuẩn hóa trước khi so sánh không?
- NULL có được phép lặp không?
- Bản ghi đã hủy hoặc soft delete có còn chiếm khóa nghiệp vụ không?
- Quy tắc có phụ thuộc trạng thái hoặc khoảng thời gian không?
- Có thể biểu diễn trực tiếp bằng UNIQUE/partial index/exclusion constraint không?
- Nếu hai transaction cùng tạo giá trị, database sẽ phân xử thế nào?
- API trả gì khi một khóa nghiệp vụ đã tồn tại?
- Client dùng key nào để nhận diện một request retry?
- Cùng idempotency key nhưng payload khác được xử lý ra sao?
- Kết quả và idempotency record có commit nguyên tử với nhau không?
- Tác dụng phụ ngoài database có cơ chế idempotency hoặc outbox không?
- Record chống trùng được giữ trong bao lâu?
- Có test được request đồng thời, timeout sau commit và worker crash không?

Tính duy nhất theo quy tắc nghiệp vụ là thuộc tính của dữ liệu và cần được bảo vệ tại database bằng constraint hoặc cơ chế tuần tự hóa phù hợp. Xử lý yêu cầu trùng là thuộc tính của luồng thực thi và cần một định danh request ổn định cùng cách lưu kết quả để lần gửi lại không lặp tác dụng phụ. Khi tách rõ hai vấn đề, hệ thống có thể vừa ngăn dữ liệu trùng do cạnh tranh đồng thời, vừa xử lý an toàn các lần retry vốn là điều bình thường trong môi trường phân tán.
