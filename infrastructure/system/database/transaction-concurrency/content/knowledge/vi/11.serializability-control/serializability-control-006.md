# Lỗi tuần tự hóa khác gì với vi phạm ràng buộc nghiệp vụ?

Khi nhiều transaction chạy đồng thời, database có thể từ chối một transaction vì xung đột với lịch thực thi của transaction khác. Ứng dụng cũng có thể bị database từ chối một thao tác vì dữ liệu mới vi phạm một quy tắc toàn vẹn. Hai trường hợp thường bị gom chung thành “lỗi transaction”, nhưng chúng có nguyên nhân và cách phục hồi khác nhau.

**Lỗi tuần tự hóa (serialization failure)** xảy ra khi database không thể chấp nhận kết quả của transaction theo bảo đảm isolation đang áp dụng. Transaction thường phải được chạy lại từ đầu với một snapshot và các quyết định mới.

**Vi phạm ràng buộc nghiệp vụ (business constraint violation)** xảy ra khi trạng thái mà ứng dụng muốn ghi không thỏa một quy tắc, chẳng hạn email phải duy nhất, số lượng không được âm hoặc đơn hàng phải tham chiếu đến khách hàng tồn tại. Retry nguyên trạng thường không làm điều kiện đó trở nên hợp lệ.

Cần phân biệt thêm một lớp: ràng buộc nghiệp vụ có thể được kiểm tra trong ứng dụng, được khai báo thành constraint trong database hoặc được bảo vệ bằng transaction/isolation. Cùng một quy tắc có thể được bảo vệ ở nhiều lớp, nhưng lỗi phát sinh ở mỗi lớp không nhất thiết có cùng mã lỗi.

## 1. Lỗi tuần tự hóa là gì?

Một lịch thực thi được gọi là tuần tự hóa được (serializable) nếu kết quả của các transaction chạy đồng thời tương đương với một thứ tự chạy lần lượt nào đó. Khi dùng SERIALIZABLE hoặc một chế độ isolation có cơ chế phát hiện xung đột tương ứng, database theo dõi các quan hệ đọc/ghi để ngăn những lịch thực thi tạo ra kết quả không thể giải thích bằng một thứ tự tuần tự hợp lệ.

Nếu phát hiện một transaction có nguy cơ tạo ra kết quả không tuần tự hóa được, database có thể hủy transaction đó và trả về lỗi tuần tự hóa. Ứng dụng phải bắt đầu lại transaction để đọc trạng thái mới và tính toán lại quyết định.

### Ví dụ: luôn phải có ít nhất một người trực

Giả sử có hai bác sĩ A và B đang trực. Quy tắc nghiệp vụ là luôn phải có ít nhất một người trực. Hai transaction đồng thời muốn cho mỗi người nghỉ:

~~~text
Transaction T1                         Transaction T2
----------------                         ----------------
BEGIN                                   BEGIN
Đọc: A và B đều đang trực               Đọc: A và B đều đang trực
Kiểm tra: B vẫn đang trực               Kiểm tra: A vẫn đang trực
Cập nhật A = OFF                        Cập nhật B = OFF
COMMIT?                                 COMMIT?
~~~

Mỗi transaction chỉ cập nhật một dòng khác nhau. Nếu cả hai cùng commit dựa trên snapshot ban đầu, hệ thống có thể rơi vào trạng thái không còn bác sĩ nào trực.

Ở isolation level SERIALIZABLE, database có thể phát hiện phụ thuộc đọc/ghi giữa hai transaction và hủy một transaction. Transaction bị hủy nhận lỗi tuần tự hóa. Sau khi chạy lại toàn bộ transaction, nó đọc trạng thái mới: chỉ còn một người trực. Lúc này điều kiện nghiệp vụ không cho phép người còn lại nghỉ.

Quy trình có thể diễn ra như sau:

~~~text
Lần thực thi đầu
    |
    +-- T1 và T2 cùng đọc trạng thái có hai người trực
    |
    +-- T1 tắt A, T2 tắt B
    |
    +-- Database phát hiện lịch có nguy cơ không tuần tự hóa được
    |
    +-- Hủy một transaction: serialization failure
                    |
                    v
Retry toàn bộ transaction bị hủy
    |
    +-- Đọc lại: chỉ còn một người trực
    |
    +-- Kiểm tra quy tắc: không được cho người cuối cùng nghỉ
    |
    +-- Từ chối yêu cầu theo nghiệp vụ
~~~

Ví dụ này cho thấy hai loại kết quả có thể xuất hiện nối tiếp nhau:

1. Serialization failure là lý do database yêu cầu transaction thử lại.
2. Sau khi thử lại, ứng dụng có thể phát hiện yêu cầu không còn hợp lệ theo quy tắc nghiệp vụ.

Serialization failure không có nghĩa người dùng đã gửi yêu cầu sai. Tại thời điểm transaction đọc dữ liệu ban đầu, yêu cầu có thể hoàn toàn hợp lệ. Xung đột chỉ xuất hiện do các transaction khác cùng thay đổi dữ liệu.

## 2. Vi phạm ràng buộc nghiệp vụ là gì?

Ràng buộc nghiệp vụ mô tả những trạng thái mà hệ thống không chấp nhận. Một số quy tắc có thể được khai báo trực tiếp trong database dưới dạng integrity constraint:

- **NOT NULL:** cột bắt buộc phải có giá trị.
- **UNIQUE:** giá trị hoặc tổ hợp giá trị phải duy nhất.
- **PRIMARY KEY:** định danh bản ghi phải duy nhất và không null.
- **FOREIGN KEY:** giá trị tham chiếu phải trỏ đến bản ghi hợp lệ theo quy tắc quan hệ.
- **CHECK:** giá trị phải thỏa một biểu thức, chẳng hạn số lượng không âm.
- **EXCLUSION:** một số tổ hợp giá trị không được xung đột theo toán tử và phạm vi được khai báo; PostgreSQL hỗ trợ loại constraint này.

Ví dụ, hệ thống không cho phép số lượng tồn kho âm:

~~~sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    available_quantity INTEGER NOT NULL,
    CONSTRAINT ck_inventory_non_negative
        CHECK (available_quantity >= 0)
);
~~~

Nếu ứng dụng cố ghi số lượng âm:

~~~sql
UPDATE inventory
SET available_quantity = -1
WHERE product_id = 42;
~~~

Database từ chối thay đổi vì nó vi phạm CHECK constraint. Chạy lại cùng câu lệnh với cùng dữ liệu vẫn sẽ thất bại. Ứng dụng phải sửa giá trị hoặc xử lý yêu cầu theo quy tắc nghiệp vụ.

Một ví dụ khác là email phải duy nhất:

~~~sql
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    CONSTRAINT uq_users_email UNIQUE (email)
);
~~~

Nếu một tài khoản đã dùng địa chỉ email đó, lần đăng ký tiếp theo có thể bị từ chối vì vi phạm UNIQUE constraint.

Không phải mọi quy tắc nghiệp vụ đều có thể hoặc nên biểu diễn bằng một constraint đơn giản. Một số quy tắc được kiểm tra ở tầng ứng dụng, một số cần trigger, stored procedure, exclusion constraint, serializable transaction hoặc mô hình dữ liệu phù hợp. Điều quan trọng là xác định nơi thực thi quy tắc và lớp nào chịu trách nhiệm trả lời người dùng.

## 3. So sánh hai loại lỗi

| Khía cạnh | Serialization failure | Vi phạm ràng buộc nghiệp vụ |
|---|---|---|
| Nguyên nhân | Các thao tác đồng thời tạo ra phụ thuộc hoặc lịch thực thi không được isolation hiện tại chấp nhận | Trạng thái hoặc thao tác không thỏa một quy tắc toàn vẹn/nghiệp vụ |
| Ai phát hiện | Cơ chế concurrency control của database | Constraint của database hoặc logic kiểm tra nghiệp vụ |
| Ý nghĩa | Transaction này cần được chạy lại để tính toán trên trạng thái mới | Yêu cầu hoặc dữ liệu cần được sửa, hoặc ứng dụng phải xử lý xung đột theo quy tắc |
| Khả năng retry | Thường retry toàn bộ transaction | Retry nguyên trạng thường không có ích |
| Dữ liệu đầu vào | Có thể hợp lệ khi bắt đầu nhưng xung đột với thay đổi đồng thời | Có thể sai hoặc không còn phù hợp với trạng thái hiện tại |
| Phạm vi lỗi | Thường làm transaction bị hủy | Có thể làm statement thất bại; transaction cần rollback hoặc phục hồi tùy engine |
| Cách phản hồi | Thử lại có giới hạn; nếu hết lần thử thì báo lỗi tạm thời | Trả lỗi nghiệp vụ phù hợp, ví dụ email đã tồn tại hoặc số dư không đủ |
| Ví dụ | Hai transaction cùng thay đổi các dòng khác nhau dựa trên snapshot khiến một bất biến bị phá vỡ | INSERT email trùng, CHECK số lượng không âm, FOREIGN KEY tham chiếu không tồn tại |

Điểm phân biệt quan trọng nhất là: **serialization failure yêu cầu tính toán lại transaction trên trạng thái mới; constraint violation yêu cầu xử lý trạng thái không hợp lệ hoặc xung đột nghiệp vụ.**

## 4. Mã lỗi giúp phân biệt như thế nào?

Mỗi hệ quản trị có mã lỗi và quy tắc báo lỗi riêng. Không nên chỉ dựa vào tên exception chung của framework như SQLException, DataAccessException hoặc TransactionException để quyết định retry.

### PostgreSQL và SQLSTATE

PostgreSQL cung cấp SQLSTATE để phân loại lỗi. Một số mã thường gặp:

| SQLSTATE | Tên/ý nghĩa | Nhóm |
|---|---|---|
| 40001 | serialization_failure | Lỗi tuần tự hóa |
| 40P01 | deadlock_detected | Deadlock, transaction bị hủy |
| 23502 | not_null_violation | Vi phạm NOT NULL |
| 23503 | foreign_key_violation | Vi phạm FOREIGN KEY |
| 23505 | unique_violation | Vi phạm UNIQUE |
| 23514 | check_violation | Vi phạm CHECK |
| 23P01 | exclusion_violation | Vi phạm EXCLUSION |

Các mã 23xxx thuộc nhóm integrity constraint violation. Mã 40001 thuộc nhóm transaction rollback và thường được xử lý bằng cách chạy lại transaction. Deadlock 40P01 cũng làm transaction thất bại và thường có thể retry, nhưng nguyên nhân là chu trình chờ lock chứ không phải serialization anomaly.

### Một số mã theo sản phẩm khác

| Database | Lỗi concurrency thường gặp | Vi phạm constraint thường gặp |
|---|---|---|
| PostgreSQL | 40001 serialization failure; 40P01 deadlock detected | 23505 unique; 23503 foreign key; 23514 check |
| MySQL/InnoDB | Error 1213 deadlock; error 1205 lock wait timeout | Error 1062 duplicate key; error 1452 foreign key; error 3819 check constraint ở các phiên bản hỗ trợ |
| SQL Server | Error 1205 deadlock victim; error 3960 snapshot isolation update conflict | Error 2627/2601 duplicate key; error 547 thường liên quan CHECK hoặc FOREIGN KEY |
| Oracle | ORA-08177 cannot serialize access for this transaction | ORA-00001 unique; ORA-02290 check; ORA-02291/02292 foreign key |

Bảng này chỉ là các ví dụ phổ biến. Mã lỗi, tên lỗi và hành vi retry còn phụ thuộc phiên bản, driver, isolation level và cách ứng dụng thực hiện transaction.

### Vì sao không nên phân loại chỉ theo tên exception?

Framework có thể bọc nhiều lỗi database vào cùng một kiểu exception. Ví dụ, một lớp exception chung về integrity có thể chứa lỗi unique, foreign key hoặc check constraint. Một lỗi concurrency cũng có thể được bọc thành exception khác nhau tùy driver.

Khi xử lý ở tầng persistence, nên lấy thông tin có cấu trúc:

- SQLSTATE hoặc vendor error code.
- Tên constraint nếu database cung cấp.
- Loại thao tác đang chạy.
- Isolation level và transaction context.
- Việc lỗi xuất hiện ở câu lệnh hay tại COMMIT.

Không nên suy đoán rằng mọi lỗi phát sinh trong transaction đều là lỗi có thể retry.

## 5. Serialization failure cần retry toàn bộ transaction

Khi database báo serialization failure, transaction cũ đã bị hủy hoặc không thể tiếp tục theo quy tắc của engine. Ứng dụng cần bắt đầu một transaction mới, đọc lại dữ liệu và thực hiện lại toàn bộ quyết định nghiệp vụ.

Không nên chỉ chạy lại câu lệnh cuối cùng bị lỗi. Những câu SELECT trước đó có thể đã đọc snapshot cũ. Nếu chỉ lặp lại UPDATE hoặc INSERT, ứng dụng vẫn sử dụng quyết định được tính từ trạng thái không còn hợp lệ.

Ví dụ:

~~~text
Sai:
    BEGIN
    SELECT balance
    Tính số tiền được phép rút
    UPDATE balance       -> serialization failure
    Chỉ retry UPDATE     -> vẫn dùng kết quả SELECT cũ

Đúng:
    BEGIN mới
    SELECT balance mới
    Kiểm tra lại điều kiện
    Tính lại số tiền
    UPDATE
    COMMIT
~~~

### Quy trình retry

Một chiến lược retry nên có các đặc điểm:

1. Chỉ retry những lỗi đã được xác định là tạm thời hoặc có thể giải quyết bằng transaction mới.
2. Rollback hoặc kết thúc transaction cũ theo yêu cầu của driver/framework.
3. Mở transaction mới và đọc lại toàn bộ dữ liệu cần thiết.
4. Tính lại điều kiện nghiệp vụ, không tái sử dụng quyết định dựa trên snapshot cũ.
5. Giới hạn số lần retry để tránh request bị lặp vô hạn.
6. Có backoff và jitter để các transaction cạnh tranh không lập tức va chạm lại cùng lúc.
7. Nếu hết số lần thử, trả lỗi tạm thời phù hợp và ghi log/metric để theo dõi.

Pseudocode:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    try:
        BEGIN NEW TRANSACTION

        read current state
        validate business conditions
        calculate changes
        write changes

        COMMIT
        return success

    catch serialization_failure:
        ROLLBACK
        if attempt == MAX_ATTEMPTS:
            return temporary_conflict
        wait with bounded backoff and jitter

    catch business_constraint_violation:
        ROLLBACK
        return mapped_business_error
~~~

Ví dụ PostgreSQL trả SQLSTATE 40001 thì ứng dụng có thể retry toàn bộ transaction. Với deadlock 40P01, một số ứng dụng cũng retry theo chính sách tương tự vì database đã chọn một transaction làm nạn nhân. Tuy nhiên, deadlock và serialization failure cần được ghi nhận riêng để điều tra nguyên nhân.

### Không retry side effect bên ngoài một cách mù quáng

Nếu transaction có gửi email, thu tiền hoặc gọi HTTP API, retry toàn bộ hàm có thể thực hiện side effect nhiều lần. Các thao tác ngoài database không tự rollback cùng transaction.

Cách an toàn hơn là ghi ý định gửi sự kiện vào Transactional Outbox trong transaction database. Worker xử lý sự kiện sau commit và dùng idempotency key khi gọi dịch vụ bên ngoài. Như vậy, việc retry transaction database không trực tiếp lặp lại hành động bên ngoài.

## 6. Constraint violation cần được ánh xạ thành kết quả nghiệp vụ

Khi database từ chối một thao tác vì constraint, ứng dụng cần xác định quy tắc nào bị vi phạm và trả kết quả phù hợp.

Ví dụ đăng ký tài khoản:

~~~sql
INSERT INTO users (user_id, email)
VALUES (1001, 'alice@example.com');
~~~

Nếu email đã tồn tại, PostgreSQL có thể trả SQLSTATE 23505. Ứng dụng có thể ánh xạ lỗi này thành thông báo:

~~~text
EMAIL_ALREADY_REGISTERED
Email này đã được sử dụng.
~~~

Đối với các constraint khác:

| Constraint | Ví dụ | Cách xử lý nghiệp vụ có thể phù hợp |
|---|---|---|
| UNIQUE | Email hoặc mã đơn hàng đã tồn tại | Báo tài nguyên đã tồn tại; có thể truy vấn bản ghi hiện có nếu nghiệp vụ cho phép |
| CHECK | Số lượng âm hoặc ngày kết thúc trước ngày bắt đầu | Từ chối dữ liệu và yêu cầu sửa giá trị |
| FOREIGN KEY | Tạo chi tiết đơn hàng với order_id không tồn tại | Kiểm tra tài nguyên tham chiếu và trạng thái của nó |
| NOT NULL | Thiếu trường bắt buộc | Báo dữ liệu đầu vào không đầy đủ |
| EXCLUSION | Hai lịch đặt phòng bị trùng khoảng thời gian | Báo khung thời gian không còn khả dụng |

Ứng dụng nên nhận diện tên constraint hoặc mã lỗi cụ thể để ánh xạ đúng. Không nên chuyển mọi lỗi integrity thành một thông báo chung như “dữ liệu không hợp lệ”, vì điều đó làm mất thông tin cần thiết để xử lý và hỗ trợ người dùng.

Một số constraint có thể được khai báo DEFERRABLE và chỉ được kiểm tra ở cuối transaction, thường tại COMMIT hoặc khi ứng dụng yêu cầu kiểm tra sớm. Vì vậy, lỗi constraint không nhất thiết xuất hiện ngay tại câu INSERT hoặc UPDATE tạo ra trạng thái vi phạm.

## 7. Vi phạm UNIQUE do cạnh tranh vẫn là constraint violation

Một trường hợp dễ nhầm là hai request đồng thời đăng ký cùng một email.

~~~text
Request A                         Request B
---------                         ---------
Kiểm tra email chưa tồn tại       Kiểm tra email chưa tồn tại
INSERT email                      INSERT email
COMMIT                            INSERT có thể phải chờ
                                  Sau khi A commit:
                                  UNIQUE violation
~~~

Cả hai request có thể cùng vượt qua bước kiểm tra ở tầng ứng dụng vì chúng đọc trước khi bản ghi được tạo. Nhưng UNIQUE constraint ở database bảo vệ tính duy nhất tại thời điểm ghi. Một request thành công; request còn lại bị từ chối.

Lỗi của request B là constraint violation, không nhất thiết là serialization failure. Ứng dụng có thể ánh xạ thành EMAIL_ALREADY_REGISTERED hoặc truy vấn lại bản ghi hiện có để xử lý theo chính sách nghiệp vụ.

Điều này cho thấy kiểm tra trước bằng SELECT không thể thay thế constraint:

~~~sql
-- Chỉ kiểm tra trước không đủ để bảo đảm duy nhất.
SELECT 1
FROM users
WHERE email = 'alice@example.com';

-- UNIQUE constraint vẫn cần thiết khi INSERT cạnh tranh.
INSERT INTO users (user_id, email)
VALUES (1002, 'alice@example.com');
~~~

Nếu nghiệp vụ hỗ trợ request lặp theo cùng một idempotency key, ứng dụng có thể tìm kết quả đã tạo và trả lại kết quả đó. Nhưng không nên coi mọi duplicate key là request retry hợp lệ: hai người dùng khác nhau có thể thực sự đang tranh cùng một email.

## 8. Một quy tắc nghiệp vụ có thể được bảo vệ bằng nhiều cơ chế

Cùng một quy tắc có thể được thực thi ở nhiều lớp:

- **Validation ở ứng dụng:** giúp phản hồi sớm và cung cấp thông báo thân thiện.
- **Constraint trong database:** là lớp bảo vệ cuối cùng cho dữ liệu được lưu, kể cả khi nhiều request cạnh tranh hoặc một đường ghi khác bỏ qua validation.
- **Isolation và locking:** bảo vệ các quy tắc phụ thuộc vào trạng thái đọc và các thay đổi đồng thời.
- **Workflow nghiệp vụ:** xử lý trạng thái trung gian, retry, hủy hoặc bù trừ khi quy tắc liên quan nhiều dịch vụ.

Ví dụ, quy tắc số lượng tồn kho không âm có thể được bảo vệ bằng CHECK constraint:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT ck_inventory_non_negative
CHECK (available_quantity >= 0);
~~~

Câu lệnh cập nhật có điều kiện giúp giảm xung đột và biểu đạt ý định rõ ràng:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = 42
  AND available_quantity > 0;
~~~

Ứng dụng kiểm tra số dòng được cập nhật. Nếu không có dòng nào, có thể sản phẩm đã hết hoặc không tồn tại. Nếu một đường ghi khác cố đặt số lượng âm, CHECK constraint vẫn bảo vệ dữ liệu.

Đối với một quy tắc liên quan nhiều dòng, chẳng hạn luôn phải có một bác sĩ trực, CHECK constraint trên từng dòng không đủ để bảo vệ tổng thể. Ứng dụng có thể cần SERIALIZABLE, khóa một dòng điều phối chung, trigger phù hợp hoặc thay đổi mô hình dữ liệu để biểu diễn bất biến đó ở một nơi có thể được database bảo vệ.

Nếu database phát hiện xung đột serialization, transaction được retry. Nếu sau khi đọc lại trạng thái, yêu cầu vẫn vi phạm quy tắc nghiệp vụ, ứng dụng trả lỗi nghiệp vụ. Hai lớp bảo vệ giải quyết hai vấn đề khác nhau.

## 9. Phân biệt với deadlock, lock timeout và optimistic locking

Không phải mọi lỗi khiến transaction thất bại đều là serialization failure hoặc constraint violation.

| Loại lỗi | Ý nghĩa | Hướng xử lý thường gặp |
|---|---|---|
| Serialization failure | Lịch đọc/ghi không thể được chấp nhận theo isolation guarantee | Retry toàn bộ transaction với snapshot mới |
| Deadlock | Các transaction tạo chu trình chờ lock; engine chọn một transaction làm nạn nhân | Điều tra thứ tự truy cập lock; retry transaction bị hủy có giới hạn |
| Lock timeout | Transaction chờ lock lâu hơn thời gian cho phép | Điều tra blocker và thời gian giữ lock; retry tùy chính sách |
| Optimistic locking conflict | UPDATE theo version không cập nhật được dòng nào vì version đã đổi | Đọc lại, hợp nhất thay đổi hoặc báo xung đột cập nhật |
| Constraint violation | Giá trị hoặc quan hệ dữ liệu không thỏa constraint | Ánh xạ lỗi nghiệp vụ, sửa dữ liệu hoặc xử lý tài nguyên đã tồn tại |

Ví dụ optimistic locking:

~~~sql
UPDATE documents
SET title = 'New title',
    version = version + 1
WHERE document_id = 42
  AND version = 7;
~~~

Nếu không có dòng nào được cập nhật, version có thể đã thay đổi. Đây thường là một xung đột cập nhật mà ứng dụng phát hiện qua số dòng affected. Nó không tự động đồng nghĩa với SQLSTATE 40001 hoặc một constraint violation.

Tương tự, deadlock là một loại transaction abort do thứ tự chờ lock. Một số database phân loại nó trong nhóm transaction rollback, nhưng nguyên nhân và cách điều tra khác với serialization anomaly.

## 10. Những cách xử lý sai thường gặp

**Retry mọi exception xảy ra trong transaction.**

Cách này có thể lặp vô hạn với UNIQUE hoặc CHECK constraint, đồng thời che giấu lỗi dữ liệu. Chỉ retry các mã lỗi được xác định là có thể phục hồi bằng transaction mới.

**Chỉ retry câu SQL cuối cùng.**

Serialization failure có thể làm mất hiệu lực các quyết định dựa trên những lần đọc trước đó. Phải chạy lại toàn bộ đơn vị transaction.

**Bắt lỗi constraint rồi bỏ qua.**

Nếu ứng dụng bỏ qua lỗi mà vẫn trả thành công, trạng thái nghiệp vụ có thể không đúng. Cần xác định constraint và trả kết quả tương ứng.

**Chỉ dùng validation ở tầng ứng dụng.**

Hai request đồng thời có thể cùng vượt qua validation. Constraint ở database vẫn cần thiết để bảo vệ tính toàn vẹn tại thời điểm ghi.

**Coi timeout là serialization failure.**

Timeout cho biết thao tác chờ quá lâu. Nó không nói rằng lịch thực thi không tuần tự hóa được. Cần đọc đúng mã lỗi và nguyên nhân.

**Đưa mọi lỗi thành HTTP 500.**

Một số lỗi có thể ánh xạ thành conflict hoặc validation response. Serialization failure sau khi hết số lần retry có thể là lỗi tạm thời cần client thử lại sau. Mã HTTP cụ thể phụ thuộc API contract, nhưng không nên làm mất khác biệt giữa lỗi dữ liệu và lỗi concurrency.

## 11. Quy trình phân loại và xử lý trong ứng dụng

Khi một transaction thất bại, có thể phân loại theo trình tự sau:

1. Lấy SQLSTATE hoặc vendor error code từ exception gốc.
2. Xác định lỗi có thuộc nhóm serialization, deadlock, lock timeout, optimistic conflict hay integrity constraint.
3. Nếu là serialization failure, kết thúc transaction cũ và retry toàn bộ transaction với dữ liệu mới.
4. Nếu là deadlock, ghi nhận tài nguyên và thứ tự lấy lock để điều tra; retry theo chính sách có giới hạn.
5. Nếu là constraint violation, xác định tên constraint và ánh xạ thành kết quả nghiệp vụ cụ thể.
6. Nếu là optimistic conflict, đọc lại version và quyết định hợp nhất, ghi đè có kiểm soát hoặc báo người dùng.
7. Ghi log có cấu trúc gồm mã lỗi, tên constraint nếu có, isolation level, transaction attempt và correlation id; tránh ghi dữ liệu nhạy cảm không cần thiết.

Có thể tổ chức chính sách như sau:

| Điều kiện | Retry tự động? | Phản hồi hoặc hành động |
|---|---|---|
| Serialization failure | Có, giới hạn số lần | Chạy lại toàn bộ transaction |
| Deadlock victim | Có thể, giới hạn số lần | Retry transaction và theo dõi deadlock |
| Lock timeout | Tùy chính sách | Kiểm tra blocker, có thể báo tài nguyên đang bận |
| UNIQUE violation | Thường không retry nguyên trạng | Báo trùng hoặc xử lý theo idempotency |
| CHECK violation | Không retry nguyên trạng | Báo điều kiện dữ liệu không hợp lệ |
| FOREIGN KEY violation | Không retry nguyên trạng nếu dữ liệu tham chiếu không đổi | Kiểm tra tài nguyên tham chiếu |
| Optimistic version conflict | Không retry câu UPDATE nguyên trạng | Đọc lại và xử lý xung đột |

Đối với retry tự động, transaction phải có ranh giới rõ ràng và không phát side effect bên ngoài trước khi commit. Nếu nghiệp vụ cần gửi sự kiện hoặc gọi dịch vụ khác, nên ghi Outbox trong cùng transaction rồi để worker xử lý sau commit.

## Kết luận

Serialization failure và business constraint violation đều có thể khiến database từ chối transaction, nhưng chúng biểu thị hai vấn đề khác nhau. Serialization failure phản ánh xung đột trong lịch thực thi đồng thời và thường được xử lý bằng cách retry toàn bộ transaction trên trạng thái mới. Constraint violation phản ánh trạng thái không thỏa một quy tắc toàn vẹn hoặc nghiệp vụ và cần được ánh xạ thành cách xử lý phù hợp.

Một ứng dụng tốt phải phân loại bằng SQLSTATE hoặc vendor error code, hiểu constraint nào đã bị vi phạm và biết transaction có thể được retry hay không. Validation giúp phản hồi sớm, constraint bảo vệ dữ liệu ở database, còn isolation và locking bảo vệ các quy tắc phụ thuộc vào truy cập đồng thời. Khi kết hợp đúng các lớp này, ứng dụng vừa giữ được tính toàn vẹn dữ liệu vừa phục hồi đúng cách khi nhiều transaction cạnh tranh.
