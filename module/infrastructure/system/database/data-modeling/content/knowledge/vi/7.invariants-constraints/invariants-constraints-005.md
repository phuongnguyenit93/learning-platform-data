# Ranh giới giao dịch cần thiết để bảo vệ từng bất biến

## Mục tiêu bài học

Sau bài này, bạn có thể xác định những thay đổi dữ liệu nào phải được commit hoặc rollback cùng nhau để giữ một bất biến; chọn ranh giới transaction phù hợp với phạm vi dữ liệu và quy trình nghiệp vụ; phân biệt transaction boundary với ranh giới aggregate hoặc service; và lựa chọn khóa, isolation level hoặc constraint để bảo vệ cập nhật đồng thời.

Bạn cũng sẽ biết cách tránh transaction quá ngắn làm hở bất biến, transaction quá dài gây tranh chấp tài nguyên, và cách xử lý khi quy trình trải qua nhiều dịch vụ hoặc hệ thống bên ngoài.

## 1. Transaction boundary là gì?

**Transaction boundary (ranh giới giao dịch)** xác định phần công việc dữ liệu bắt đầu tại đâu và kết thúc tại đâu, sao cho các thay đổi bên trong được xử lý như một đơn vị nhất quán. Với transaction cơ sở dữ liệu, các thay đổi được commit cùng nhau hoặc rollback cùng nhau.

Ví dụ, khi chuyển tiền giữa hai tài khoản, hệ thống phải trừ tiền tài khoản gửi và cộng tiền tài khoản nhận. Nếu chỉ trừ tiền rồi gặp lỗi trước khi cộng tiền, dữ liệu sẽ sai. Hai cập nhật phải nằm trong cùng transaction:

~~~text
BEGIN
  Trừ tiền tài khoản gửi
  Cộng tiền tài khoản nhận
COMMIT
~~~

Nếu bất kỳ bước bắt buộc nào thất bại, transaction phải rollback để cả hai thay đổi không được ghi nhận một phần.

Ranh giới transaction được chọn dựa trên **bất biến cần bảo vệ**. Hãy hỏi: những dữ liệu nào phải cùng thay đổi để sau thao tác, điều kiện nghiệp vụ vẫn đúng? Toàn bộ thay đổi cần thiết đó phải được bảo vệ bằng một cơ chế nhất quán, thường là một transaction cùng constraint hoặc khóa phù hợp.

### 1.1. Transaction bảo vệ một chuyển đổi trạng thái

Một transaction có trạng thái trước và trạng thái sau:

~~~text
Trạng thái hợp lệ D
       |
       | Transaction T
       v
Trạng thái hợp lệ D'
~~~

Nếu transaction thành công, hệ thống chuyển từ D sang D'. Nếu thất bại, hệ thống giữ D. Với bất biến P, yêu cầu là:

~~~text
P(D) = true
T thành công => P(D') = true
T thất bại   => trạng thái được rollback, P(D) vẫn đúng
~~~

Điều này giả định trạng thái ban đầu đã hợp lệ và mọi đường ghi liên quan đều tuân theo cơ chế bảo vệ. Transaction không tự sửa dữ liệu sai đã tồn tại và cũng không tự biết quy tắc nghiệp vụ nếu ta không mã hóa quy tắc đó.

### 1.2. Ranh giới transaction không chỉ là vị trí BEGIN và COMMIT

Đặt BEGIN và COMMIT quanh một đoạn code chưa chắc đã bảo vệ được bất biến. Cần xác định:

- Những hàng hoặc bảng nào liên quan?
- Có request khác cập nhật cùng dữ liệu không?
- Có thao tác nào nằm ngoài transaction nhưng vẫn có thể phá quy tắc không?
- Isolation level có đủ để bảo vệ điều kiện nhiều hàng không?
- Constraint database có chặn trạng thái sai không?
- Lỗi giữa chừng có rollback được mọi thay đổi không?
- Có side effect bên ngoài database nào đã xảy ra trước khi commit không?

Ví dụ, transaction xác nhận đơn hàng có thể khóa bản ghi Order nhưng thao tác xóa OrderItem không lấy cùng khóa. Khi đó hai transaction vẫn có thể phối hợp sai và đơn đã xác nhận không còn dòng hàng. Ranh giới đúng phải đi cùng một giao thức đồng bộ được mọi đường ghi tuân thủ.

## 2. Bắt đầu từ bất biến, không bắt đầu từ số lượng câu lệnh

Một transaction nên được thiết kế quanh điều kiện phải luôn đúng. Không nên gom các câu SQL vào cùng transaction chỉ vì chúng nằm trong một hàm hoặc một endpoint.

### 2.1. Viết bất biến thành câu có thể kiểm tra

Ví dụ:

> Số dư của mỗi tài khoản không được âm, và tổng số tiền trong giao dịch chuyển nội bộ phải được bảo toàn.

Bất biến này liên quan đến hai tài khoản và hai cập nhật số dư. Transaction phải bao gồm cả hai cập nhật và ghi nhận giao dịch nếu bản ghi giao dịch là một phần bắt buộc của sổ cái.

Một ví dụ khác:

> Một phòng không được có hai booking đã xác nhận với khoảng thời gian chồng lấn.

Bất biến này liên quan đến tất cả booking có cùng phòng và khoảng thời gian giao nhau. Transaction chỉ cập nhật một booking chưa chắc đủ; cần cơ chế ngăn hai request đồng thời cùng vượt qua kiểm tra.

### 2.2. Lập bản đồ dữ liệu bị ảnh hưởng

Với mỗi bất biến, liệt kê:

1. Dữ liệu được đọc để ra quyết định.
2. Dữ liệu được tạo, cập nhật hoặc xóa.
3. Các hàng khác có thể bị ảnh hưởng bởi thao tác đồng thời.
4. Các constraint bảo vệ dữ liệu.
5. Các sự kiện hoặc side effect cần phát ra sau commit.

Ví dụ xác nhận đơn hàng:

| Thành phần | Vai trò |
|---|---|
| Order | Trạng thái chuyển từ DRAFT sang CONFIRMED |
| OrderItem | Phải có ít nhất một dòng hợp lệ |
| Inventory | Tồn kho phải đủ và được giữ/trừ theo chính sách |
| Payment | Điều kiện thanh toán phải được đáp ứng nếu quy trình yêu cầu |
| Outbox event | Ghi sự kiện OrderConfirmed để phát sau commit |

Bảng này cho thấy một số thay đổi có thể thuộc cùng transaction database; một số khác có thể nằm ở service khác và cần quy trình phân tán.

### 2.3. Xác định điểm kiểm tra và điểm commit

Một quy trình thường có các giai đoạn:

- đọc dữ liệu cần thiết;
- khóa hoặc kiểm soát phiên bản;
- kiểm tra precondition;
- thực hiện các thay đổi;
- kiểm tra postcondition hoặc dựa vào constraint;
- ghi sự kiện cần phát;
- commit.

Điểm commit phải nằm sau tất cả thay đổi cần thiết để giữ bất biến. Nếu commit quá sớm, dữ liệu có thể ở trạng thái trung gian mà nghiệp vụ không cho phép. Nếu commit quá muộn, transaction có thể giữ khóa lâu và tăng tranh chấp.

## 3. Nguyên tắc chọn ranh giới transaction

### 3.1. Bao gồm mọi thay đổi cần atomicity

Nếu hai hoặc nhiều thay đổi phải cùng thành công hoặc cùng thất bại để giữ bất biến, hãy đặt chúng trong cùng transaction khi chúng nằm trong cùng ranh giới database có thể giao dịch.

Ví dụ:

- trừ tiền và cộng tiền trong chuyển khoản;
- trừ tồn kho và tạo bản ghi giữ hàng;
- cập nhật trạng thái đơn và ghi nhận lịch sử trạng thái;
- tạo hóa đơn và các dòng hóa đơn;
- ghi dữ liệu nghiệp vụ và outbox event tương ứng.

Nếu thiếu một thay đổi bắt buộc, hệ thống có thể commit một trạng thái không hợp lệ.

### 3.2. Không gom các công việc không cần atomicity

Một transaction quá rộng có thể:

- giữ khóa lâu;
- tăng xác suất deadlock;
- làm giảm throughput;
- tăng lượng rollback khi một bước không liên quan thất bại;
- tạo phụ thuộc giữa những công việc có thể chạy độc lập.

Ví dụ, tạo đơn hàng và gửi email xác nhận thường không cần nằm trong cùng transaction database. Email có thể gửi sau khi đơn đã commit. Nếu gửi email thất bại, đơn hàng vẫn tồn tại và hệ thống có thể retry gửi email.

Điều quan trọng là phân biệt side effect bắt buộc để giữ bất biến với side effect có thể thực hiện sau.

### 3.3. Transaction phải ngắn và có thời hạn

Transaction nên hoàn thành nhanh, tránh giữ tài nguyên trong khi chờ người dùng hoặc dịch vụ ngoài.

Không nên:

- mở transaction khi người dùng mở form và giữ nó trong nhiều phút;
- gọi API thanh toán hoặc gửi email trong khi đang khóa hàng database;
- chờ nhập OTP hoặc phê duyệt thủ công trong transaction;
- thực hiện báo cáo lớn trong transaction ghi dữ liệu nóng nếu không cần snapshot dài.

Hãy thu thập đầu vào trước, thực hiện phần giao dịch ngắn khi người dùng xác nhận, rồi xử lý side effect bên ngoài theo cơ chế phù hợp.

### 3.4. Một transaction cần có một mục tiêu nhất quán

Tên transaction nên phản ánh ý nghĩa nghiệp vụ, chẳng hạn:

- ReserveInventory;
- ConfirmOrder;
- TransferFunds;
- PostJournalEntry;
- AssignEmployeeToDepartment.

Mục tiêu rõ giúp người đọc nhận ra bất biến nào được bảo vệ và đánh giá liệu thao tác nào có thuộc transaction hay không.

## 4. Phạm vi của một transaction và ranh giới aggregate

Trong thiết kế hướng miền (Domain-Driven Design), **aggregate** là nhóm thực thể và value object được quản lý như một đơn vị nhất quán. Aggregate root là điểm truy cập chính để thay đổi trạng thái bên trong nhóm.

Aggregate giúp xác định nơi tập trung bảo vệ invariant. Tuy nhiên, aggregate boundary và database transaction boundary không phải lúc nào cũng đồng nhất tuyệt đối.

### 4.1. Bất biến bên trong một aggregate

Ví dụ, Order và OrderItem được quản lý trong cùng aggregate:

- dòng hàng phải thuộc đúng đơn;
- số lượng phải dương;
- tổng tiền phải được tính theo quy tắc;
- đơn đã xác nhận không được sửa dòng hàng theo chính sách.

Một lệnh ConfirmOrder có thể cập nhật trạng thái Order sau khi kiểm tra các dòng hàng trong cùng transaction.

### 4.2. Bất biến giữa nhiều aggregate

Giả sử một đơn hàng cần giữ tồn kho từ nhiều sản phẩm. Order và Inventory có thể là hai aggregate riêng vì tồn kho được quản lý độc lập theo sản phẩm.

Nếu cả hai nằm trong cùng database và nghiệp vụ yêu cầu giữ hàng cùng lúc với tạo đơn, có thể dùng một transaction database bao gồm các bản ghi cần thiết. Nếu chúng thuộc hai service/database khác nhau, không thể dùng transaction cục bộ để bảo đảm atomicity toàn cục; cần một quy trình phân tán như saga.

### 4.3. Không tạo aggregate quá lớn chỉ để gom transaction

Nếu gom tất cả sản phẩm, đơn hàng, khách hàng, thanh toán và vận chuyển vào một aggregate khổng lồ, mọi thao tác có thể tranh chấp cùng một khóa và khó mở rộng.

Hãy xác định invariant thật sự cần được bảo vệ tức thời. Những quy tắc khác có thể được xử lý bằng sự kiện, quy trình bất đồng bộ hoặc kiểm tra hội tụ nếu nghiệp vụ cho phép.

## 5. Cơ chế database bảo vệ ranh giới

Transaction đảm bảo atomicity, nhưng cần kết hợp constraint, khóa và isolation để bảo vệ tính đúng đắn khi có cạnh tranh.

### 5.1. Constraint vẫn cần thiết

Ví dụ, chuyển tiền trong một transaction không thay thế CHECK số dư không âm:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(18, 2) NOT NULL CHECK (balance >= 0)
);
~~~

CHECK bảo vệ từng hàng khi ghi. Transaction bảo đảm cập nhật hai tài khoản cùng commit hoặc rollback. Cả hai lớp có vai trò riêng.

### 5.2. UNIQUE bảo vệ tính duy nhất đồng thời

Giả sử mỗi khách hàng chỉ có một hồ sơ đang hoạt động cho một loại giấy tờ. Nếu ứng dụng chỉ truy vấn trước rồi mới insert, hai request đồng thời có thể cùng thấy chưa tồn tại.

Một unique constraint phù hợp là lớp bảo vệ cuối:

~~~sql
CREATE UNIQUE INDEX uq_active_identity
ON identity_documents(customer_id, document_type)
WHERE status = 'ACTIVE';
~~~

Cú pháp partial index phụ thuộc hệ quản trị. Với PostgreSQL, ví dụ này ngăn hai bản ghi ACTIVE cùng customer_id và document_type. Ứng dụng cần xử lý lỗi vi phạm unique như một kết quả nghiệp vụ có thể dự đoán.

### 5.3. FOREIGN KEY bảo vệ tham chiếu

Nếu một bản ghi con phải tham chiếu cha tồn tại, FK đảm bảo không có tham chiếu mồ côi tại thời điểm commit theo quy tắc của database.

~~~sql
CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id)
);
~~~

FK không tự đảm bảo mọi Order có ít nhất một OrderItem. Đó là bất biến phía cha và cần cơ chế riêng.

### 5.4. Constraint hoãn kiểm tra (deferred constraint)

Một số hệ quản trị cho phép constraint được kiểm tra ở cuối transaction thay vì ngay sau từng câu lệnh. Điều này hữu ích khi trạng thái trung gian bên trong transaction tạm thời chưa thỏa mãn, nhưng trạng thái cuối phải hợp lệ.

Ví dụ, cập nhật các tham chiếu vòng hoặc ghi nhiều dòng có quan hệ phụ thuộc có thể cần kiểm tra khi commit. Khả năng DEFERRABLE và cú pháp khác nhau giữa hệ quản trị; không giả định mọi CHECK hoặc constraint đều có thể hoãn.

## 6. Isolation level và các bất biến liên hàng

Transaction boundary trả lời những thay đổi nào đi cùng nhau. Isolation level trả lời các transaction đồng thời có thể quan sát và tác động lên nhau như thế nào.

### 6.1. Read Committed

Ở mức Read Committed, mỗi câu lệnh thường nhìn thấy dữ liệu đã commit trước khi câu lệnh bắt đầu. Hai câu SELECT trong cùng transaction có thể nhìn thấy các phiên bản khác nhau nếu transaction khác commit ở giữa.

Mức này đủ cho nhiều thao tác nếu có constraint và cập nhật nguyên tử phù hợp. Tuy nhiên, kiểm tra một tập hàng rồi dựa vào kết quả đó để ghi có thể gặp race condition.

### 6.2. Repeatable Read và Snapshot Isolation

Ở một số hệ quản trị, Repeatable Read dựa trên snapshot giúp transaction đọc một ảnh nhất quán hơn. Nhưng snapshot không đồng nghĩa mọi bất biến liên hàng đều được bảo vệ. Hai transaction có thể cùng đọc một điều kiện đúng rồi ghi các hàng khác nhau khiến tổng thể vi phạm (write skew), tùy isolation semantics.

Không nên chọn Repeatable Read chỉ vì tên nghe như mọi lần đọc đều lặp lại được. Cần hiểu hành vi cụ thể của database.

### 6.3. Serializable

Serializable hướng tới kết quả tương đương một thứ tự thực thi tuần tự. Database có thể hủy một transaction khi phát hiện xung đột cần retry.

Mức này hữu ích với một số bất biến phức tạp phụ thuộc tập hàng hoặc điều kiện vắng mặt. Nhưng nó không loại bỏ nhu cầu thiết kế đúng:

- ứng dụng phải retry lỗi serialization an toàn;
- transaction nên ngắn;
- side effect bên ngoài không được thực hiện trước khi biết commit;
- cần kiểm thử tải và xung đột thực tế.

### 6.4. Khóa hàng và khóa phạm vi

SELECT ... FOR UPDATE khóa các hàng được chọn theo cơ chế của database. Nó hữu ích khi các transaction cạnh tranh cập nhật cùng một tài nguyên đã có hàng đại diện.

Nhưng nếu bất biến phụ thuộc việc **không có hàng nào** thỏa điều kiện, khóa các hàng đang tồn tại có thể chưa đủ. Một transaction khác vẫn có thể insert hàng mới (phantom) trừ khi isolation hoặc cơ chế khóa phạm vi phù hợp ngăn điều đó.

Có thể dùng:

- unique/exclusion constraint;
- khóa một hàng cha làm mutex nghiệp vụ;
- advisory lock nếu hệ quản trị hỗ trợ;
- serializable transaction;
- thiết kế lại dữ liệu để có một hàng tài nguyên/guard row rõ ràng.

Chọn cơ chế theo điều kiện cần bảo vệ, không chỉ theo câu lệnh SQL quen thuộc.

## 7. Ví dụ: chuyển tiền giữa hai tài khoản

Bất biến:

1. Số dư tài khoản không âm.
2. Tổng tiền chuyển được trừ khỏi tài khoản gửi và cộng vào tài khoản nhận.
3. Bản ghi giao dịch chỉ được ghi nhận nếu hai cập nhật thành công.

### 7.1. Ranh giới transaction

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :from_account
  AND balance >= :amount;

-- Ứng dụng phải xác nhận đúng một hàng được cập nhật.
-- Nếu không, rollback và trả lỗi không đủ số dư.

UPDATE accounts
SET balance = balance + :amount
WHERE account_id = :to_account;

-- Ứng dụng phải xác nhận tài khoản nhận tồn tại.
-- Nếu không, rollback.

INSERT INTO transfers (
    transfer_id,
    from_account_id,
    to_account_id,
    amount,
    status
)
VALUES (
    :transfer_id,
    :from_account,
    :to_account,
    :amount,
    'COMPLETED'
);

COMMIT;
~~~

Đây là phác thảo transaction; ứng dụng phải kiểm tra số hàng bị ảnh hưởng và rollback nếu bất kỳ bước bắt buộc nào không thành công. Cần xác thực amount dương, hai tài khoản khác nhau nếu nghiệp vụ yêu cầu, tiền tệ tương thích và quyền chuyển tiền trước khi commit.

### 7.2. Tránh deadlock khi khóa nhiều tài khoản

Hai giao dịch ngược chiều có thể khóa tài khoản theo thứ tự khác nhau:

- Transaction A khóa tài khoản 10 rồi chờ 20.
- Transaction B khóa tài khoản 20 rồi chờ 10.

Đây là tình huống deadlock. Có thể giảm nguy cơ bằng cách khóa tài khoản theo thứ tự account_id nhất quán trong mọi đường chuyển tiền.

Database vẫn có thể phát hiện deadlock và hủy một transaction. Ứng dụng cần xử lý retry có giới hạn và idempotency để không tạo chuyển tiền trùng.

### 7.3. Idempotency

Client có thể gửi lại yêu cầu do timeout dù transaction trước đã commit. Dùng một idempotency key duy nhất trong phạm vi phù hợp:

~~~sql
CREATE TABLE transfers (
    transfer_id UUID PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    from_account_id BIGINT NOT NULL,
    to_account_id BIGINT NOT NULL,
    amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
    status VARCHAR(20) NOT NULL
);
~~~

Nếu yêu cầu được gửi lại với cùng key, hệ thống trả lại kết quả giao dịch đã có thay vì trừ tiền lần nữa. Cần ràng buộc phạm vi key theo tenant hoặc client nếu key chỉ duy nhất trong phạm vi đó.

## 8. Ví dụ: xác nhận đơn hàng và giữ tồn kho

Giả sử một đơn hàng có nhiều dòng và cần giữ đủ tồn kho cho tất cả sản phẩm. Nếu Order và Inventory nằm trong cùng database, transaction có thể gồm:

1. khóa hoặc cập nhật có điều kiện các hàng tồn kho;
2. xác minh đủ số lượng cho mọi sản phẩm;
3. ghi bản ghi reservation;
4. chuyển Order sang CONFIRMED hoặc RESERVED theo mô hình;
5. ghi outbox event;
6. commit.

Nếu bất kỳ sản phẩm nào thiếu hàng, toàn bộ transaction rollback để không giữ một phần tồn kho ngoài ý muốn.

### 8.1. Cập nhật có điều kiện

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :product_id
  AND available_quantity >= :quantity;
~~~

Nếu số hàng bị cập nhật bằng 0, không đủ tồn kho hoặc sản phẩm không tồn tại. Với đơn có nhiều sản phẩm, ứng dụng cần kiểm tra tất cả dòng và rollback nếu bất kỳ dòng nào không giữ được.

### 8.2. Khóa theo thứ tự ổn định

Nếu cần khóa nhiều sản phẩm, hãy lấy khóa theo thứ tự product_id nhất quán để giảm deadlock. Nếu nhiều dòng đơn cùng sản phẩm, hãy gộp số lượng trước khi trừ để tránh cập nhật lặp khó kiểm soát.

### 8.3. Khi nào không giữ kho trong transaction tạo đơn?

Nếu chính sách cho phép đơn được tạo trước rồi giữ kho sau, không cần gom tất cả thành một transaction lớn. Có thể tạo đơn ở trạng thái PENDING_RESERVATION, rồi một worker thực hiện reservation. Mô hình phải định nghĩa rõ trạng thái trung gian và cách xử lý khi hết hàng.

Lựa chọn phụ thuộc vào trải nghiệm khách hàng, mức độ cạnh tranh tồn kho và yêu cầu không bán vượt số lượng. Trạng thái PENDING không phải lỗi nếu nó là trạng thái nghiệp vụ được thiết kế có chủ đích.

## 9. Bất biến cần nhiều hàng: dùng guard row hoặc khóa phù hợp

Một số bất biến phụ thuộc vào tổng hoặc số lượng bản ghi. Ví dụ, mỗi lớp học chỉ có tối đa 30 học viên.

Nếu hai transaction cùng đếm 29 học viên rồi insert, cả hai có thể cùng vượt qua kiểm tra và tạo tổng 31. Việc đếm rồi insert mà không bảo vệ concurrency là không an toàn.

### 9.1. Guard row

Có thể lưu capacity và enrolled_count trên một hàng Course:

~~~sql
UPDATE courses
SET enrolled_count = enrolled_count + 1
WHERE course_id = :course_id
  AND enrolled_count < capacity;
~~~

Chỉ transaction cập nhật được một hàng mới tiếp tục tạo enrollment. Bản ghi đăng ký và bộ đếm phải nằm trong cùng transaction để không lệch nhau.

Cách này làm một hàng Course trở thành điểm đồng bộ. Nếu throughput cao, hàng đó có thể nóng; cần đo tải và cân nhắc chiến lược khác.

### 9.2. Counter phải được đồng bộ với dữ liệu chi tiết

Nếu enrolled_count là giá trị dẫn xuất từ bảng enrollments, cần xác định cách duy trì:

- cập nhật counter cùng transaction khi thêm/xóa enrollment;
- tính lại định kỳ và đối chiếu;
- hoặc tính trực tiếp từ bảng nếu workload cho phép.

Counter cache không được xem là nguồn sự thật độc lập nếu nó có thể lệch với dữ liệu chi tiết.

### 9.3. Constraint hoặc khóa phù hợp hơn

Nếu bất biến là “mỗi học viên chỉ đăng ký một lần trong cùng kỳ”, UNIQUE(student_id, course_id, term_id) là giải pháp trực tiếp hơn. Nếu bất biến là tổng số học viên không vượt capacity, unique không giải quyết được; cần guard row, khóa, serializable hoặc một thiết kế khác.

Hãy chọn cơ chế gần nhất với cấu trúc quy tắc.

## 10. Transaction boundary trong hệ thống nhiều dịch vụ

Khi dữ liệu nằm ở nhiều database do các service sở hữu, transaction ACID cục bộ không thể tự bao trùm toàn bộ quy trình. Không nên giữ transaction mở trong khi gọi lần lượt các service qua mạng.

### 10.1. Transaction cục bộ và distributed workflow

Ví dụ đặt hàng cần:

- tạo đơn hàng ở Order Service;
- giữ tồn kho ở Inventory Service;
- thu tiền ở Payment Service;
- yêu cầu giao hàng ở Shipping Service.

Mỗi service có transaction riêng trên database của mình. Quy trình tổng thể cần một mô hình điều phối và xử lý lỗi.

### 10.2. Saga

**Saga** chia một quy trình dài thành nhiều transaction cục bộ. Mỗi bước có thể có một hành động bù trừ (compensating action) nếu bước sau thất bại.

Ví dụ:

| Bước | Transaction cục bộ | Hành động bù trừ |
|---|---|---|
| 1 | Tạo Order PENDING | Hủy Order |
| 2 | Giữ tồn kho | Giải phóng reservation |
| 3 | Thu tiền | Hoàn tiền hoặc void authorization |
| 4 | Tạo yêu cầu giao hàng | Hủy shipment nếu còn khả thi |
| 5 | Xác nhận Order | Có thể không cần bù nếu quy trình hoàn tất |

Compensation không phải rollback database toàn cục. Nó là một hành động nghiệp vụ mới để đưa hệ thống về trạng thái chấp nhận được. Ví dụ hoàn tiền tạo thêm một giao dịch hoàn tiền và lịch sử, không xóa giao dịch thu tiền trước đó.

### 10.3. Bất biến trong trạng thái trung gian

Saga có thể để hệ thống ở trạng thái trung gian trong một khoảng thời gian. Mô hình phải quy định trạng thái nào được phép:

- PENDING_INVENTORY;
- PENDING_PAYMENT;
- PAYMENT_AUTHORIZED;
- CANCELLATION_REQUESTED;
- COMPENSATING;
- FAILED.

Không nên coi trạng thái trung gian là vi phạm nếu nghiệp vụ cho phép và có timeout, retry, compensation cùng giám sát để đạt kết quả cuối.

Cần phân biệt bất biến an toàn phải đúng mọi lúc, ví dụ không phát hành giao hàng khi chưa được phép, với điều kiện tiến triển, ví dụ đơn hợp lệ cuối cùng phải hoàn tất hoặc chuyển sang trạng thái thất bại rõ ràng.

### 10.4. Outbox pattern

Nếu transaction cập nhật dữ liệu và phát message riêng rẽ, có thể xảy ra:

- database commit nhưng message không được gửi;
- message được gửi nhưng database rollback.

Outbox pattern ghi thay đổi nghiệp vụ và một bản ghi outbox trong cùng transaction database. Một tiến trình khác đọc outbox và phát message sau commit.

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :order_id;

INSERT INTO outbox_events (
    event_id,
    aggregate_id,
    event_type,
    payload,
    created_at
)
VALUES (
    :event_id,
    :order_id,
    'OrderConfirmed',
    :payload,
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

Worker phát event từ outbox và đánh dấu đã gửi. Message có thể được gửi lặp, nên consumer cần idempotency hoặc inbox/deduplication.

Outbox không tạo transaction phân tán với broker; nó bảo đảm việc ghi event cần phát được commit cùng thay đổi nghiệp vụ trong database nguồn.

## 11. Những điều không nên đặt bên trong transaction

Tránh các thao tác có thời gian không xác định hoặc phụ thuộc hệ thống bên ngoài:

- gọi cổng thanh toán;
- gửi email hoặc SMS;
- gọi API vận chuyển;
- chờ người dùng xác nhận;
- chờ nhập mã OTP;
- tải tệp lớn;
- xử lý ảnh hoặc video;
- chạy báo cáo dài không liên quan đến cập nhật;
- chờ một message khác đến.

Các thao tác này có thể chậm, timeout hoặc thất bại độc lập. Giữ transaction mở trong lúc chờ sẽ giữ connection và khóa, làm giảm khả năng phục vụ các request khác.

Một cách tổ chức thường dùng:

1. Tạo bản ghi trạng thái PENDING và commit.
2. Gửi yêu cầu ngoài bằng worker hoặc workflow.
3. Nhận kết quả qua callback/message.
4. Mở transaction mới để cập nhật trạng thái và lịch sử.
5. Retry hoặc compensation nếu thất bại.

Với thanh toán, cần phân biệt authorize, capture và refund theo hợp đồng nhà cung cấp. Không thể giả định gọi API thành công đồng nghĩa database đã commit hoặc ngược lại.

## 12. Retry, timeout và lỗi commit

Một transaction có thể thất bại vì deadlock, serialization failure, mất kết nối hoặc timeout.

### 12.1. Retry chỉ khi an toàn

Có thể retry một transaction khi:

- lỗi được phân loại là tạm thời;
- toàn bộ thao tác có thể chạy lại;
- không có side effect ngoài database đã thực hiện trước đó;
- idempotency bảo vệ thao tác khỏi lặp;
- số lần retry có giới hạn và có backoff.

Không retry vô hạn. Cần ghi log đủ để điều tra và trả lỗi phù hợp khi vượt giới hạn.

### 12.2. Kết quả commit không rõ ràng

Nếu kết nối bị đứt ngay sau khi client gửi COMMIT, client có thể không biết database đã commit hay chưa. Không được mặc định rằng lỗi mạng nghĩa là transaction rollback.

Cách xử lý là dùng idempotency key hoặc transaction identifier để truy vấn kết quả đã ghi. Với thao tác tạo giao dịch, khóa duy nhất trên idempotency key giúp nhận diện lần thực hiện trước.

### 12.3. Timeout và hủy request

Khi client timeout hoặc ngắt kết nối, server có thể đã commit trước khi biết request bị hủy. Hệ thống cần xác định thao tác có thể tiếp tục hay phải hủy, và cung cấp endpoint tra cứu trạng thái khi nghiệp vụ cần.

Không nên gắn việc hủy kết nối HTTP với rollback một giao dịch đã commit.

## 13. Ghi chép transaction boundary

Với mỗi invariant quan trọng, nên ghi cách transaction bảo vệ nó.

| Trường | Nội dung |
|---|---|
| Invariant ID | Mã bất biến liên quan |
| Transaction/use case | Tên thao tác nghiệp vụ |
| Dữ liệu tham gia | Bảng, aggregate hoặc service |
| Precondition | Điều kiện trước khi bắt đầu |
| Atomic changes | Các thay đổi phải commit cùng nhau |
| Concurrency control | Constraint, lock, version hoặc isolation |
| Commit condition | Điều kiện để commit |
| Failure handling | Rollback, retry, compensation hoặc trạng thái lỗi |
| Side effects | Event, email, API ngoài và thời điểm phát |
| Verification | Test thường, concurrency test, monitoring |

### 13.1. Ví dụ transaction record

**TX-ORDER-002 — ConfirmOrder**

- **Invariant:** đơn CONFIRMED phải có ít nhất một dòng hàng hợp lệ và không xác nhận khi thiếu điều kiện tồn kho.
- **Phạm vi cục bộ:** Order, OrderItem, Inventory và Outbox trong cùng database.
- **Precondition:** Order ở DRAFT; các dòng hàng hợp lệ; sản phẩm còn kinh doanh.
- **Atomic changes:** giữ tồn kho, cập nhật trạng thái Order, ghi reservation và outbox event.
- **Concurrency control:** khóa Order; cập nhật tồn kho có điều kiện; khóa sản phẩm theo thứ tự ID.
- **Commit condition:** mọi dòng hàng giữ được tồn kho và trạng thái được chuyển hợp lệ.
- **Failure handling:** rollback toàn bộ transaction nếu thiếu hàng; trả kết quả hết hàng.
- **Side effect:** worker phát OrderConfirmed sau commit.
- **Verification:** test đơn rỗng, thiếu hàng một sản phẩm, hai request cùng giữ lượng cuối, worker phát event lặp.

Nếu Inventory nằm ở service khác, transaction record phải thay đổi: Order Service không thể ghi Inventory cùng transaction cục bộ. Khi đó dùng saga, reservation và compensation với trạng thái trung gian được định nghĩa.

## 14. Kiểm chứng ranh giới transaction

Một transaction có vẻ đúng trong luồng đơn lẻ vẫn có thể sai khi có lỗi hoặc cạnh tranh. Hãy kiểm thử ít nhất các nhóm tình huống:

1. Lỗi trước thay đổi đầu tiên.
2. Lỗi sau một phần thay đổi nhưng trước commit.
3. Constraint bị vi phạm ở bước cuối.
4. Hai request cùng sửa một tài nguyên.
5. Hai request cùng kiểm tra một điều kiện nhiều hàng.
6. Deadlock hoặc serialization failure.
7. Timeout khi client không biết kết quả commit.
8. Message được phát lặp sau commit.
9. Worker dừng giữa lúc xử lý outbox.
10. Một service ngoài thành công nhưng service tiếp theo thất bại.
11. Retry sau lỗi tạm thời.
12. Compensation thất bại và cần tiếp tục xử lý.

Sau mỗi trường hợp, xác minh:

- bất biến còn đúng không;
- có thay đổi dở dang không;
- side effect nào đã xảy ra;
- có thể xác định kết quả transaction không;
- retry có tạo bản ghi hoặc giao dịch trùng không;
- trạng thái trung gian có thể được phục hồi không.

### 14.1. Kiểm thử rollback

Ví dụ chuyển tiền: cố tình làm bước ghi tài khoản nhận thất bại. Sau rollback, số dư tài khoản gửi phải bằng trước transaction và không có transfer COMPLETED.

### 14.2. Kiểm thử đồng thời

Chạy nhiều request cùng đặt chỗ cuối cùng hoặc cùng giữ tồn kho. Kết quả phải không vượt capacity và không có reservation trùng. Test nên chạy với database thực tế hoặc engine tương đương, vì mô phỏng bằng mock không thể xác minh locking và isolation semantics.

### 14.3. Kiểm thử crash recovery

Dừng worker sau khi đọc outbox nhưng trước khi đánh dấu đã gửi. Khi worker khởi động lại, message có thể được phát lại; consumer phải xử lý lặp an toàn.

## 15. Những sai lầm thường gặp

- **Chia transaction theo từng câu SQL:** các thay đổi cần atomicity bị commit riêng, tạo trạng thái trung gian sai.
- **Gom mọi thứ vào một transaction lớn:** giữ khóa lâu và làm tăng tranh chấp, rollback và deadlock.
- **Chỉ khóa ở một đường ghi:** một thao tác khác không dùng cùng giao thức có thể phá bất biến.
- **Cho rằng BEGIN/COMMIT tự bảo vệ mọi bất biến:** cần constraint, isolation hoặc concurrency control phù hợp.
- **Đếm rồi insert mà không khóa:** hai transaction có thể cùng vượt qua kiểm tra.
- **Giữ transaction khi gọi API ngoài:** timeout và lỗi mạng khiến tài nguyên database bị giữ lâu.
- **Phát message trước commit:** consumer có thể thấy sự kiện cho dữ liệu chưa được commit.
- **Cho rằng saga là rollback nguyên tử:** compensation là hành động nghiệp vụ riêng, có thể thất bại và cần retry.
- **Retry mọi lỗi:** lỗi nghiệp vụ hoặc thao tác không idempotent có thể gây hậu quả lặp.
- **Không xử lý kết quả commit không rõ:** timeout phía client không chứng minh database đã rollback.
- **Đồng nhất aggregate với transaction toàn hệ thống:** aggregate xác định ranh giới nhất quán miền; quy trình nhiều service cần thiết kế khác.
- **Không kiểm thử concurrency và crash:** luồng thành công đơn lẻ không chứng minh transaction boundary đúng.

## 16. Kết luận

Ranh giới transaction cần bao phủ mọi thay đổi phải cùng thành công hoặc cùng thất bại để giữ một bất biến. Hãy bắt đầu từ phát biểu bất biến, xác định dữ liệu và đường ghi bị ảnh hưởng, sau đó chọn transaction boundary, constraint và concurrency control phù hợp.

Transaction cục bộ bảo vệ thay đổi trong một database; isolation và khóa bảo vệ trước cạnh tranh; outbox giúp phát sự kiện sau commit; saga điều phối quy trình qua nhiều service với trạng thái trung gian và compensation. Transaction nên ngắn, có mục tiêu rõ, retry an toàn và được kiểm thử cả khi lỗi lẫn khi nhiều request chạy đồng thời.

## Tự kiểm tra

1. Vì sao transaction boundary phải được xác định từ invariant thay vì số lượng câu SQL?
2. Trong chuyển tiền, những thay đổi nào phải commit hoặc rollback cùng nhau?
3. Một Order được khóa khi xác nhận nhưng thao tác xóa OrderItem không dùng cùng cơ chế. Rủi ro là gì?
4. Vì sao Repeatable Read hoặc snapshot không tự bảo vệ mọi bất biến liên hàng?
5. Khi nào cần guard row, unique/exclusion constraint hoặc Serializable?
6. Vì sao không nên gọi cổng thanh toán trong khi đang giữ transaction database?
7. Outbox pattern giải quyết tình huống nào? Vì sao consumer vẫn cần idempotency?
8. Saga khác rollback transaction ACID như thế nào?
9. Client timeout ngay sau COMMIT. Vì sao không thể kết luận transaction đã rollback?
10. Hãy viết transaction record cho một use case trong hệ thống bạn biết, gồm invariant, dữ liệu tham gia, atomic changes, concurrency control và failure handling.

