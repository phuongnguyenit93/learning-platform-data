# Kiểm tra ràng buộc tức thời và ràng buộc trì hoãn

Ràng buộc dữ liệu (*database constraint*) giúp cơ sở dữ liệu bảo vệ các quy tắc mà dữ liệu phải luôn tuân thủ, chẳng hạn khóa chính không được trùng, khóa ngoại phải tham chiếu đến hàng tồn tại, số lượng không được âm hoặc mã nghiệp vụ phải duy nhất. Khi một câu lệnh `INSERT`, `UPDATE` hoặc `DELETE` làm dữ liệu vi phạm ràng buộc, hệ quản trị phải xác định thời điểm kiểm tra và từ chối thay đổi không hợp lệ.

Có hai cách kiểm tra quan trọng:

- **Ràng buộc tức thời** (*immediate constraint*): được kiểm tra ngay trong quá trình thực thi câu lệnh, thông thường chậm nhất là khi câu lệnh kết thúc. Nếu vi phạm, câu lệnh thất bại ngay và giao dịch phải xử lý lỗi.
- **Ràng buộc trì hoãn** (*deferred constraint*): được phép tạm thời bị vi phạm trong transaction hiện tại; hệ quản trị kiểm tra khi transaction commit hoặc tại thời điểm ứng dụng chủ động yêu cầu kiểm tra sớm.

Ràng buộc trì hoãn hữu ích khi một thay đổi hợp lệ cần nhiều câu lệnh trung gian. Ví dụ, đổi chỗ hai giá trị đang có ràng buộc duy nhất hoặc tạo các bản ghi tham chiếu lẫn nhau trong cùng một transaction. Dù được trì hoãn, ràng buộc vẫn phải hợp lệ khi transaction hoàn tất. Đây không phải cơ chế cho phép lưu dữ liệu sai rồi sửa vào một thời điểm bất kỳ sau commit.

## 1. Vì sao cần thời điểm kiểm tra ràng buộc?

Giả sử bảng `seat_assignment` lưu vị trí ghế của từng người và có quy tắc mỗi `seat_no` chỉ được xuất hiện một lần.

| seat_id | seat_no |
|---:|---:|
| 101 | 1 |
| 102 | 2 |

Nghiệp vụ muốn đổi chỗ hai ghế: người ở ghế 1 chuyển sang ghế 2, người ở ghế 2 chuyển sang ghế 1. Trạng thái đầu và cuối đều hợp lệ, nhưng cách cập nhật tuần tự có thể tạo trạng thái trung gian bị trùng.

```text
Trạng thái ban đầu:       Trạng thái cuối:
seat 101 -> position 1    seat 101 -> position 2
seat 102 -> position 2    seat 102 -> position 1

Nếu cập nhật seat 101 thành 2 trước:
seat 101 -> position 2
seat 102 -> position 2   <- trùng tạm thời
```

Với ràng buộc `UNIQUE` được kiểm tra tức thời, câu lệnh đầu tiên có thể thất bại vì vị trí 2 vẫn đang được hàng 102 sử dụng. Một cách là dùng giá trị tạm để tránh trùng. Một cách khác, nếu hệ quản trị hỗ trợ, là khai báo ràng buộc duy nhất có thể trì hoãn để hệ quản trị kiểm tra trạng thái cuối của transaction.

Điểm quan trọng là phải phân biệt **trạng thái trung gian trong một transaction** và **trạng thái được phép commit**. Immediate yêu cầu trạng thái hợp lệ sau từng câu lệnh; deferred cho phép một số trạng thái trung gian chưa hợp lệ, miễn là transaction đưa dữ liệu về trạng thái hợp lệ trước khi commit.

## 2. Ràng buộc tức thời (Immediate Constraint)

Ràng buộc tức thời được kiểm tra khi câu lệnh gây thay đổi được thực thi. Nếu vi phạm, hệ quản trị trả lỗi ngay tại câu lệnh đó.

Ví dụ:

```sql
CREATE TABLE product (
    product_id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);
```

Các quy tắc trong ví dụ gồm:

- `PRIMARY KEY`: `product_id` phải duy nhất và không được `NULL`.
- `NOT NULL`: `sku` và `quantity` phải có giá trị.
- `UNIQUE`: hai sản phẩm không được dùng cùng một `sku`.
- `CHECK`: `quantity` không được âm.

Nếu ứng dụng chạy:

```sql
INSERT INTO product (product_id, sku, quantity)
VALUES (1, 'SKU-001', -5);
```

Ràng buộc `CHECK` phát hiện `quantity = -5` không hợp lệ và câu lệnh bị từ chối. Ứng dụng nhận lỗi tại thao tác này, thay vì đợi đến cuối transaction mới biết dữ liệu sai.

Ràng buộc tức thời phù hợp với hầu hết quy tắc thông thường vì trạng thái dữ liệu sau mỗi câu lệnh đều được giữ hợp lệ. Nó giúp lỗi xuất hiện gần thao tác gây ra lỗi, thuận tiện cho việc xác định nguyên nhân và xử lý.

### Thời điểm kiểm tra không nhất thiết là từng dòng vật lý

Trong ngữ nghĩa SQL, immediate thường có nghĩa ràng buộc được kiểm tra chậm nhất khi câu lệnh kết thúc. Một câu lệnh cập nhật nhiều hàng có thể thay đổi nhiều hàng trong cùng một statement; hệ quản trị không nhất thiết phải kiểm tra và từ chối ngay sau mỗi hàng vật lý được ghi. Chi tiết thực thi phụ thuộc loại constraint và sản phẩm.

Vì vậy, không nên hiểu “tức thời” là mọi byte dữ liệu được kiểm tra ngay tại thời điểm ghi từng dòng. Điểm phân biệt chính là thời điểm xác nhận ràng buộc: cuối statement đối với immediate, hoặc cuối transaction/điểm kiểm tra được yêu cầu đối với deferred.

## 3. Ràng buộc trì hoãn (Deferred Constraint)

Ràng buộc trì hoãn cho phép transaction đi qua một số trạng thái trung gian chưa thỏa mãn ràng buộc. Hệ quản trị sẽ kiểm tra khi transaction commit. Nếu đến thời điểm kiểm tra mà dữ liệu vẫn vi phạm, commit thất bại.

Không phải mọi constraint đều có thể trì hoãn. Trong PostgreSQL, các loại ràng buộc có thể khai báo `DEFERRABLE` gồm `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY` và `EXCLUDE`. Các ràng buộc `NOT NULL` và `CHECK` không thể khai báo trì hoãn. Những hệ quản trị khác có tập tính năng và giới hạn khác nhau.

Một constraint có thể được khai báo theo một trong hai trạng thái mặc định:

- `DEFERRABLE INITIALLY IMMEDIATE`: có thể trì hoãn, nhưng mặc định vẫn kiểm tra theo từng statement.
- `DEFERRABLE INITIALLY DEFERRED`: có thể trì hoãn và mặc định chỉ kiểm tra khi transaction kết thúc hoặc khi được yêu cầu kiểm tra sớm.

Nếu constraint không được khai báo `DEFERRABLE`, ứng dụng không thể tùy ý chuyển nó sang deferred bằng `SET CONSTRAINTS` trong transaction.

## 4. Ví dụ: đổi chỗ hai giá trị UNIQUE trong PostgreSQL

Tạo bảng có ràng buộc duy nhất có thể trì hoãn:

```sql
CREATE TABLE seat_assignment (
    seat_id BIGINT PRIMARY KEY,
    seat_no INTEGER NOT NULL,
    CONSTRAINT uq_seat_no
        UNIQUE (seat_no)
        DEFERRABLE INITIALLY DEFERRED
);
```

Dữ liệu ban đầu:

```sql
INSERT INTO seat_assignment (seat_id, seat_no)
VALUES (101, 1), (102, 2);
```

Đổi chỗ hai vị trí trong một transaction:

```sql
BEGIN;

UPDATE seat_assignment
SET seat_no = CASE seat_no
    WHEN 1 THEN 2
    WHEN 2 THEN 1
END
WHERE seat_no IN (1, 2);

COMMIT;
```

Trong transaction, hai hàng có thể tạm thời mang giá trị `seat_no` trùng nhau theo thứ tự cập nhật nội bộ. Vì `uq_seat_no` được khai báo `INITIALLY DEFERRED`, PostgreSQL kiểm tra ràng buộc khi commit. Trạng thái cuối có hai giá trị khác nhau nên transaction có thể commit thành công.

Nếu câu lệnh hoặc logic ứng dụng tạo ra trạng thái cuối vẫn có hai hàng cùng `seat_no`, `COMMIT` sẽ thất bại. Ứng dụng phải xử lý lỗi và rollback transaction theo đúng trạng thái mà driver/database báo về.

Nếu không muốn constraint luôn deferred, có thể khai báo `DEFERRABLE INITIALLY IMMEDIATE` rồi trì hoãn riêng trong transaction:

```sql
BEGIN;

SET CONSTRAINTS uq_seat_no DEFERRED;

UPDATE seat_assignment
SET seat_no = CASE seat_no
    WHEN 1 THEN 2
    WHEN 2 THEN 1
END
WHERE seat_no IN (1, 2);

COMMIT;
```

`SET CONSTRAINTS` áp dụng cho transaction hiện tại. Sau khi transaction kết thúc, trạng thái mặc định của constraint được dùng lại ở transaction sau.

## 5. Ví dụ: tạo các hàng có khóa ngoại tham chiếu lẫn nhau

Một trường hợp khác là các bản ghi cần tham chiếu đến nhau nhưng không thể tạo theo thứ tự nào mà mọi khóa ngoại đều hợp lệ ngay sau từng câu lệnh.

Ví dụ, hai nhân viên có thể là quản lý của nhau trong dữ liệu mô phỏng hoặc quan hệ đồng phụ trách. Bảng có khóa ngoại tự tham chiếu:

```sql
CREATE TABLE employee (
    employee_id BIGINT PRIMARY KEY,
    manager_id BIGINT,
    CONSTRAINT fk_employee_manager
        FOREIGN KEY (manager_id)
        REFERENCES employee(employee_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Với PostgreSQL, có thể tạo hai hàng trong cùng transaction:

```sql
BEGIN;

INSERT INTO employee (employee_id, manager_id)
VALUES (1, 2);

INSERT INTO employee (employee_id, manager_id)
VALUES (2, 1);

COMMIT;
```

Sau câu `INSERT` đầu tiên, nhân viên 2 chưa tồn tại. Nếu khóa ngoại được kiểm tra tức thời, câu lệnh đầu tiên sẽ thất bại. Với khóa ngoại trì hoãn, hệ quản trị cho phép tham chiếu tạm thời chưa có đích; sau câu lệnh thứ hai, cả hai hàng đều tồn tại và quan hệ tham chiếu hợp lệ khi commit.

Đây là ví dụ về quan hệ vòng (*cyclic reference*). Trong mô hình dữ liệu thực tế, cần cân nhắc xem quan hệ vòng có thật sự cần thiết hay có thể thiết kế theo cách dễ quản lý hơn, chẳng hạn tạo hàng trước với `manager_id = NULL` rồi cập nhật tham chiếu sau.

## 6. Điều khiển thời điểm kiểm tra bằng SET CONSTRAINTS

Trong PostgreSQL, `SET CONSTRAINTS` cho phép thay đổi trạng thái kiểm tra của các constraint có thể trì hoãn trong transaction hiện tại.

```sql
-- Trì hoãn một constraint có thể trì hoãn
SET CONSTRAINTS uq_seat_no DEFERRED;

-- Trì hoãn tất cả constraint có thể trì hoãn trong transaction
SET CONSTRAINTS ALL DEFERRED;

-- Chuyển về kiểm tra tức thời
SET CONSTRAINTS uq_seat_no IMMEDIATE;
```

Hai trạng thái có ý nghĩa như sau:

- `DEFERRED`: kiểm tra khi transaction commit, trừ khi được chuyển sang immediate trước đó.
- `IMMEDIATE`: kiểm tra vào cuối mỗi statement tiếp theo. Khi chuyển từ deferred sang immediate, PostgreSQL còn kiểm tra ngay những thay đổi trước đó đang chờ xác nhận; nếu dữ liệu vi phạm, chính câu `SET CONSTRAINTS` thất bại.

Việc chuyển về immediate có thể hữu ích khi ứng dụng muốn xác nhận ràng buộc sau một nhóm thao tác, trước khi tiếp tục công việc khác trong transaction. Nếu việc kiểm tra thất bại, ứng dụng phải xử lý lỗi transaction hoặc rollback về savepoint phù hợp.

Chỉ các constraint được khai báo `DEFERRABLE` mới có thể chuyển qua lại bằng `SET CONSTRAINTS`. Tên constraint phải đúng với constraint trong schema; phạm vi `ALL` chỉ tác động đến các constraint có thể trì hoãn.

## 7. So sánh thời điểm kiểm tra

| Đặc điểm | Immediate | Deferred |
|---|---|---|
| Thời điểm kiểm tra | Cuối statement | Cuối transaction hoặc khi được yêu cầu chuyển sang immediate |
| Có cho phép trạng thái trung gian vi phạm? | Không, nếu statement kết thúc trong trạng thái vi phạm | Có, miễn là hợp lệ tại thời điểm kiểm tra |
| Thời điểm phát hiện lỗi | Gần câu lệnh gây vi phạm | Có thể muộn hơn, thường tại commit |
| Cách khai báo | Thường là mặc định | Cần constraint hỗ trợ `DEFERRABLE` |
| Trường hợp phù hợp | Quy tắc thông thường cần được giữ sau mỗi statement | Thao tác nhiều bước cần trạng thái trung gian tạm thời |
| Rủi ro vận hành | Lỗi xuất hiện sớm | Lỗi có thể xuất hiện ở commit, xa thao tác gây ra lỗi |

Ví dụ timeline:

```text
IMMEDIATE
BEGIN
  Statement 1 -> kiểm tra constraint -> lỗi nếu vi phạm
  Statement 2 -> chỉ chạy nếu transaction còn hợp lệ
COMMIT

DEFERRED
BEGIN
  Statement 1 -> có thể tạm vi phạm
  Statement 2 -> sửa trạng thái về hợp lệ
  COMMIT -> kiểm tra constraint
             +-- hợp lệ: commit thành công
             +-- vi phạm: commit thất bại
```

Deferred thay đổi **thời điểm kiểm tra**, không loại bỏ ràng buộc. Sau commit, dữ liệu vẫn phải thỏa mãn constraint.

## 8. Hệ quản trị cơ sở dữ liệu hỗ trợ khác nhau

Không nên giả định cú pháp và khả năng trì hoãn constraint giống nhau trên mọi hệ quản trị.

### PostgreSQL

PostgreSQL hỗ trợ khai báo `DEFERRABLE` cho một số constraint như `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY` và `EXCLUDE`. Trạng thái ban đầu có thể là `INITIALLY IMMEDIATE` hoặc `INITIALLY DEFERRED`; `SET CONSTRAINTS` điều khiển việc kiểm tra trong transaction. `NOT NULL` và `CHECK` không thể trì hoãn.

### Oracle Database

Oracle hỗ trợ constraint có thể trì hoãn với `DEFERRABLE INITIALLY IMMEDIATE` hoặc `DEFERRABLE INITIALLY DEFERRED`, và có câu lệnh `SET CONSTRAINTS` để điều khiển trạng thái trong transaction. Khả năng áp dụng phụ thuộc loại constraint và quy tắc của Oracle; cần kiểm tra tài liệu phiên bản trước khi thiết kế.

### MySQL InnoDB

MySQL InnoDB không hỗ trợ khai báo constraint trì hoãn theo cú pháp `DEFERRABLE`/`INITIALLY DEFERRED`. Các ràng buộc khóa ngoại được kiểm tra ngay trong câu lệnh; MySQL cũng không có `SET CONSTRAINTS` theo mô hình này. Nếu cần đổi chỗ giá trị duy nhất hoặc tạo quan hệ phụ thuộc vòng, ứng dụng thường phải sắp xếp thao tác trung gian, dùng giá trị tạm, cho phép `NULL` tạm thời khi mô hình cho phép, hoặc thiết kế lại quy trình ghi.

Ví dụ đổi chỗ hai vị trí mà không cần deferred constraint có thể dùng một giá trị tạm chưa được sử dụng:

```sql
START TRANSACTION;

UPDATE seat_assignment SET seat_no = -1 WHERE seat_no = 1;
UPDATE seat_assignment SET seat_no = 1  WHERE seat_no = 2;
UPDATE seat_assignment SET seat_no = 2  WHERE seat_no = -1;

COMMIT;
```

Giá trị tạm phải được bảo đảm không xung đột với dữ liệu hợp lệ, đồng thời các quy tắc `CHECK`, kiểu dữ liệu và logic ứng dụng phải cho phép nó. Nếu không có giá trị tạm an toàn, hãy xem xét mô hình dữ liệu hoặc cách biểu diễn thứ tự khác.

## 9. Deferred constraint và tính đúng đắn khi có giao dịch đồng thời

Trì hoãn kiểm tra không có nghĩa là tắt kiểm tra trong thời gian transaction. Hệ quản trị vẫn phải bảo đảm constraint được thực thi chính xác khi nhiều giao dịch cùng sửa dữ liệu liên quan.

Khi commit, việc xác nhận constraint có thể cần kiểm tra các hàng liên quan, chờ khóa hoặc phát hiện xung đột với giao dịch khác. Một transaction dùng deferred constraint vẫn có thể gặp lock wait, deadlock hoặc serialization failure tùy hệ quản trị và kiểu thao tác.

Không nên tự kiểm tra bằng `SELECT` trong ứng dụng rồi cho rằng constraint trì hoãn không cần thiết. Hai giao dịch có thể cùng đọc một trạng thái hợp lệ và cùng đưa ra quyết định gây vi phạm nếu không có constraint hoặc cơ chế điều phối phù hợp. Constraint ở database là lớp bảo vệ cuối cùng cho quy tắc mà nó biểu diễn.

Deferred constraint cũng không tự giải quyết mọi bất biến nghiệp vụ nhiều hàng. Một `CHECK` thông thường thường kiểm tra một hàng, không thể dùng để đếm toàn bộ hàng trong bảng. Nếu quy tắc phụ thuộc nhiều hàng, cần constraint phù hợp mà hệ quản trị hỗ trợ, trigger được thiết kế an toàn khi đồng thời, hàng guard, bộ đếm tổng hợp hoặc mức `SERIALIZABLE`.

## 10. Những giới hạn và lưu ý khi sử dụng

- **Không phải loại constraint nào cũng deferrable.** Kiểm tra tài liệu hệ quản trị trước khi chọn thiết kế.
- **Không thể trì hoãn constraint không hỗ trợ.** Việc gọi `SET CONSTRAINTS` với constraint không thể trì hoãn sẽ báo lỗi trong các hệ quản trị hỗ trợ câu lệnh này.
- **Lỗi có thể xuất hiện tại COMMIT.** Ứng dụng phải bắt lỗi ở cả câu lệnh commit, không chỉ quanh `INSERT` hoặc `UPDATE`.
- **Transaction phải thật sự bao trùm nhiều statement.** Nếu driver hoặc framework bật autocommit, mỗi statement có thể trở thành transaction riêng và deferred constraint không giúp nối các thao tác lại với nhau.
- **Giữ transaction ngắn.** Deferred không phải lý do để mở transaction lâu; transaction dài có thể giữ khóa và tài nguyên lâu hơn.
- **Kiểm tra sớm khi cần.** Chuyển constraint sang immediate sau một nhóm thao tác giúp phát hiện lỗi trước khi tiếp tục phần còn lại của nghiệp vụ.
- **Đặt tên constraint rõ ràng.** Tên ổn định giúp ứng dụng và câu lệnh `SET CONSTRAINTS` tham chiếu chính xác hơn.
- **Đừng nhầm deferred với eventual consistency.** Dữ liệu không được phép commit trong trạng thái vi phạm constraint.

## 11. Khi nào nên dùng immediate hoặc deferred?

### Ưu tiên immediate cho quy tắc thông thường

Immediate phù hợp với phần lớn constraint:

- `NOT NULL` cho dữ liệu bắt buộc.
- `CHECK` cho miền giá trị của một hàng, ví dụ `quantity >= 0`.
- `UNIQUE` cho mã định danh hoặc email cần duy nhất trong trạng thái sau mỗi statement.
- `FOREIGN KEY` cho quan hệ cha-con được tạo theo thứ tự thông thường.

Kiểm tra sớm giúp lỗi gần với thao tác gây ra vi phạm, giảm độ phức tạp khi xử lý và giữ trạng thái trung gian dễ hiểu.

### Dùng deferred khi transaction cần thay đổi theo nhiều bước

Deferred có thể phù hợp khi:

- Cần hoán đổi hai giá trị duy nhất mà không muốn dùng giá trị tạm.
- Cần tạo một tập bản ghi có tham chiếu vòng trong cùng transaction.
- Một quy trình nhiều bước tạm thời phá vỡ quan hệ khóa ngoại nhưng sẽ khôi phục tính hợp lệ trước commit.
- Ứng dụng cần điều khiển rõ thời điểm xác nhận constraint sau khi hoàn tất một nhóm thao tác.

Trước khi dùng deferred, hãy kiểm tra liệu có cách đơn giản hơn không: sắp xếp thứ tự cập nhật, dùng câu lệnh cập nhật nguyên tử, tạo hàng trước rồi bổ sung tham chiếu, hoặc dùng giá trị tạm an toàn. Deferred hữu ích khi trạng thái trung gian là cần thiết và hệ quản trị hỗ trợ đúng loại constraint.

## 12. Quy trình xử lý lỗi constraint trong ứng dụng

Với immediate constraint, lỗi thường xảy ra ở statement gây vi phạm. Với deferred constraint, lỗi có thể xảy ra tại `COMMIT`. Vì vậy, vùng xử lý lỗi của ứng dụng phải bao trùm toàn bộ transaction:

```text
BEGIN
  thực hiện các INSERT / UPDATE / DELETE
  xử lý các bước nghiệp vụ liên quan
  nếu cần: SET CONSTRAINTS ... IMMEDIATE để kiểm tra sớm
COMMIT
   |
   +-- thành công: trả kết quả
   |
   +-- lỗi constraint: rollback/đóng transaction theo driver
                        trả lỗi nghiệp vụ phù hợp
```

Không nên trả thành công cho người dùng trước khi commit hoàn tất. Nếu transaction commit thất bại vì deferred constraint, các thay đổi trong transaction không được xác nhận. Ứng dụng cần phân biệt lỗi constraint với lỗi mạng không rõ kết quả commit; trường hợp mất kết nối đúng lúc commit có thể cần cơ chế idempotency hoặc truy vấn trạng thái để xác định kết quả.

## 13. Những điểm cần nhớ

- Immediate constraint được kiểm tra chậm nhất khi statement kết thúc; nếu vi phạm, lỗi xuất hiện tại statement.
- Deferred constraint cho phép trạng thái trung gian tạm thời vi phạm và được kiểm tra khi commit hoặc khi chuyển sang immediate.
- Chỉ constraint được khai báo hỗ trợ trì hoãn mới có thể dùng `SET CONSTRAINTS`.
- PostgreSQL hỗ trợ deferred cho một số loại như `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY` và `EXCLUDE`; `NOT NULL` và `CHECK` không deferrable.
- Oracle cũng hỗ trợ deferrable constraint nhưng chi tiết phụ thuộc loại constraint và phiên bản.
- MySQL InnoDB không hỗ trợ `DEFERRABLE`/`SET CONSTRAINTS`; cần thiết kế lại thứ tự cập nhật hoặc dùng giá trị tạm phù hợp.
- Deferred không cho phép commit dữ liệu vi phạm; constraint vẫn được xác nhận trước khi transaction hoàn tất.
- Lỗi deferred có thể xuất hiện tại `COMMIT`, nên ứng dụng phải xử lý lỗi ở ranh giới transaction.
- Deferred thay đổi thời điểm xác nhận, không thay thế khóa, kiểm soát đồng thời hoặc thiết kế bất biến nhiều hàng.

Hãy dùng kiểm tra tức thời làm mặc định để phát hiện lỗi sớm và giữ trạng thái sau mỗi câu lệnh dễ hiểu. Chỉ trì hoãn constraint khi một transaction nhiều bước thực sự cần trạng thái trung gian chưa hợp lệ và hệ quản trị có hỗ trợ phù hợp. Dù chọn cách nào, transaction chỉ được commit khi toàn bộ ràng buộc dữ liệu đã được thỏa mãn.
