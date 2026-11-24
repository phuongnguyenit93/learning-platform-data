# Transaction isolation choice

## 1. Chọn isolation để bảo vệ quy tắc nào?

Trong chương **Transactions** của module bảo vệ logic nghiệp vụ, transaction không chỉ dùng để gom nhiều câu SQL thành một lần commit. Nó còn tham gia bảo vệ các quyết định nghiệp vụ trước những yêu cầu chạy đồng thời.

Một giao dịch có thể hoàn toàn atomic nhưng vẫn đưa ra quyết định từ dữ liệu không còn phù hợp khi giao dịch khác cùng hoạt động. Ví dụ, hai request cùng thấy còn đủ hạn mức, cùng được chấp nhận, rồi tổng số tiền đã giữ chỗ vượt hạn mức. Mỗi request có thể chạy trong transaction riêng và commit thành công, nhưng quy tắc chung vẫn bị phá vỡ.

**Transaction isolation choice** là lựa chọn mức cô lập cùng các cơ chế dữ liệu cần thiết để những cách thực thi đồng thời được cho phép không làm sai invariant của nghiệp vụ.

Không nên bắt đầu bằng câu hỏi “mức isolation nào mạnh nhất?”. Hãy bắt đầu bằng:

> Hai hay nhiều thao tác hợp lệ khi chạy riêng có thể kết hợp thành trạng thái sai nào khi chạy đồng thời?

Bài học tập trung vào cách trả lời câu hỏi đó, chọn giữa cập nhật có điều kiện, khóa, constraint và serializable, rồi xác định ranh giới transaction và chiến lược retry. Các ví dụ SQL dùng PostgreSQL khi cần chỉ rõ hành vi; không mặc định tên isolation có cùng cách triển khai ở mọi cơ sở dữ liệu.

## 2. Invariant phải được viết trước khi chọn cơ chế

Một invariant có ích cần đủ cụ thể để kiểm tra ở trạng thái đã commit:

| Nghiệp vụ | Invariant minh họa |
| --- | --- |
| Giữ chỗ ngân sách | Tổng giá trị đang được giữ không vượt ngân sách của đúng tenant và kỳ |
| Trừ tồn kho | Tồn khả dụng của một mặt hàng không âm |
| Phê duyệt | Một phiên bản yêu cầu chỉ chuyển từ `PENDING` sang trạng thái kết thúc một lần |
| Hoàn tiền | Tổng phần đã hoàn và đã dành cho yêu cầu đang xử lý không vượt phần được phép |
| Quản trị | Mỗi tổ chức vẫn còn ít nhất một quản trị viên hoạt động |
| Xử lý lệnh trùng | Một định danh ý định nghiệp vụ không tạo hai tác động thành công |

Sau đó xác định:

1. Dữ liệu nào tham gia quyết định: một hàng, nhiều hàng đã biết hay một tập được tìm bằng điều kiện?
2. Những thao tác nào có thể thay đổi dữ liệu đó: tạo, sửa, hủy, hoàn tác, import, job nền, công cụ quản trị?
3. Ranh giới invariant nằm trong một database hay đi qua nhiều dịch vụ?
4. Đường ghi nào đang dựa vào dữ liệu đọc từ replica, cache hoặc trước transaction?
5. Hệ thống chấp nhận chờ khóa, retry hay từ chối cạnh tranh ở mức nào?

Không thể kết luận một mức isolation là đủ nếu chưa biết toàn bộ đường ghi có thể phá invariant. Một API khóa đúng nhưng job đồng bộ cập nhật trực tiếp không theo cùng quy tắc vẫn để lại lỗ hổng.

## 3. Atomicity khác với isolation

**Atomicity** yêu cầu các thay đổi thuộc cùng transaction cùng được commit hoặc cùng bị rollback. **Isolation** quy định các transaction đồng thời được nhìn thấy và tương tác với nhau như thế nào.

Ví dụ logic dễ sai:

```text
BEGIN
    đọc số dư
    nếu số dư >= số tiền cần trừ:
        ghi số dư mới
        ghi giao dịch chi
COMMIT
```

Việc đặt tất cả trong transaction giúp tránh chỉ ghi số dư mà quên ghi giao dịch chi khi rollback. Nó chưa chứng minh hai transaction không cùng quyết định dựa trên một số dư cũ.

Một lịch thực thi có thể xảy ra khi ứng dụng đọc rồi ghi đè giá trị ở mức cô lập không ngăn trường hợp này:

| Bước | Transaction A | Transaction B |
| --- | --- | --- |
| 1 | Đọc số dư `100` | |
| 2 | | Đọc số dư `100` |
| 3 | Chấp nhận khoản chi `80` | |
| 4 | | Chấp nhận khoản chi `80` |
| 5 | Ghi số dư `20`, ghi khoản chi `80`, commit | |
| 6 | | Ghi số dư `20`, ghi khoản chi `80`, commit |

Kết quả là đã ghi nhận hai khoản chi tổng `160` nhưng số dư chỉ phản ánh một lần trừ. Đây là mất cập nhật theo mô hình đọc rồi ghi đè, đồng thời phá invariant kế toán.

Nếu đổi câu ghi thành `balance = balance - 80` nhưng giữ kiểm tra số dư ở câu đọc trước đó, hai lần trừ có thể đều được áp dụng và làm số dư âm. Tránh ghi đè không có nghĩa là đã bảo vệ điều kiện đủ số dư.

Với logic nhạy cảm, caller có thể cố ý tạo lịch cạnh tranh bằng nhiều request đồng thời. Vì thế, đây là một vấn đề bảo mật nghiệp vụ, không chỉ là lỗi hiệu năng hiếm gặp.

## 4. Các mức isolation và giới hạn của bảng tên gọi

Theo mô hình phân loại quen thuộc của SQL, các hiện tượng đọc thường được mô tả như sau:

| Mức | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| Read Uncommitted | Có thể được phép | Có thể được phép | Có thể được phép |
| Read Committed | Không được phép | Có thể được phép | Có thể được phép |
| Repeatable Read | Không được phép | Không được phép | Có thể được phép theo mô hình phân loại này |
| Serializable | Không được phép | Không được phép | Không được phép |

- **Dirty read:** đọc dữ liệu mà transaction khác chưa commit.
- **Non-repeatable read:** đọc lại một hàng và thấy giá trị khác vì transaction khác đã commit thay đổi.
- **Phantom read:** chạy lại truy vấn theo điều kiện và thấy tập hàng thay đổi do transaction khác.

Bảng này không mô tả hết các vấn đề như write skew, cập nhật mất dữ liệu hoặc quy tắc kết hợp nhiều hàng. Không nên chọn isolation chỉ bằng cách đánh dấu ba cột này.

### 4.1. Read Committed

Trong PostgreSQL, một câu lệnh thường đọc snapshot của dữ liệu đã commit tại thời điểm câu lệnh bắt đầu. Hai câu SELECT trong cùng transaction có thể thấy những thay đổi đã được commit giữa hai câu lệnh.

Read Committed có thể đủ cho nhiều invariant nếu dùng câu UPDATE có điều kiện, unique constraint hoặc khóa hàng đúng cách. Bản thân mức cô lập này không bảo vệ một quy trình “đọc điều kiện rồi ghi sau” tùy ý.

### 4.2. Repeatable Read và snapshot isolation

Trong PostgreSQL, Repeatable Read cung cấp snapshot ổn định cho các lần đọc thông thường trong transaction và ngăn phantom theo cách triển khai của nó. Tuy vậy, nó vẫn có thể cho phép write skew.

Hai transaction có thể cùng đọc một trạng thái hợp lệ rồi ghi vào hai hàng khác nhau, làm trạng thái kết hợp trở nên không hợp lệ. “Tôi đọc lại vẫn thấy như cũ” không đồng nghĩa “không ai có thể thay đổi điều kiện tôi đang dựa vào”.

Một số xung đột ghi ở mức này có thể làm transaction bị hủy và cần retry. Không nên suy ra rằng mọi lịch cạnh tranh nguy hiểm đều sẽ bị hủy.

### 4.3. Serializable

Serializable yêu cầu kết quả của các transaction được bảo đảm trong phạm vi đó tương đương với một thứ tự thực thi tuần tự nào đó. Nó không nhất thiết chạy từng transaction một hoặc khóa toàn bộ database.

PostgreSQL có thể phát hiện các phụ thuộc đọc–ghi nguy hiểm và hủy một transaction để giữ bảo đảm serializable. Ứng dụng phải chấp nhận và retry các transaction bị hủy theo thiết kế.

Serializable không sửa một quy tắc vốn sai ngay cả khi chạy tuần tự. Nó cũng không tạo transaction phân tán với cổng thanh toán, không thay thế authorization và không bao phủ một quyết định đã đọc ở ngoài transaction.

### 4.4. Không sao chép kết luận giữa các hệ quản trị

Read Uncommitted của PostgreSQL được xử lý như Read Committed. Repeatable Read của PostgreSQL cũng có các bảo đảm khác với những gì chỉ nhìn từ bảng phân loại tối thiểu có thể gợi ra.

Các hệ quản trị khác có thể dùng cách khóa, snapshot, khóa khoảng hoặc quy tắc cập nhật khác. Khi triển khai, cần kiểm tra hành vi của đúng hệ quản trị, cấu hình và loại truy vấn đang dùng, thay vì coi tên isolation là mô tả đầy đủ.

## 5. Read Committed có thể đủ khi cập nhật đúng một điểm tranh chấp

Giả sử mọi yêu cầu giữ ngân sách của cùng một phạm vi đều đi qua một hàng tổng hợp:

```sql
CREATE TABLE budget_account (
    tenant_id       uuid   NOT NULL,
    budget_id       uuid   NOT NULL,
    limit_minor     bigint NOT NULL,
    reserved_minor  bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, budget_id),
    CHECK (limit_minor >= 0),
    CHECK (reserved_minor >= 0),
    CHECK (reserved_minor <= limit_minor)
);
```

Invariant trên hàng:

```text
0 <= reserved_minor <= limit_minor
```

Thay vì đọc hạn mức rồi tính ở application, dùng cập nhật có điều kiện:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE budget_account
SET reserved_minor = reserved_minor + :amountMinor
WHERE tenant_id = :tenantId
  AND budget_id = :budgetId
  AND :amountMinor > 0
  AND :amountMinor <= limit_minor - reserved_minor
RETURNING reserved_minor, limit_minor;

-- Chỉ khi UPDATE trả đúng một hàng:
-- INSERT reservation của cùng ý định trong transaction này.
-- Nếu INSERT hoặc bước liên quan thất bại, rollback toàn bộ.

COMMIT;
```

Các tham số là bind parameter, không phải chuỗi SQL được nối từ input. Số tiền phải được kiểm tra kiểu, miền giá trị, đơn vị và quyền sử dụng ngân sách ở phía server. Điều kiện số tiền dương ngăn việc dùng khoản giữ âm để mở thêm hạn mức.

Với các hàng và phép cập nhật như ví dụ, PostgreSQL phân xử các cập nhật cạnh tranh trên cùng hàng. Sau khi đợi một cập nhật đồng thời, điều kiện UPDATE được xét lại trên phiên bản hàng thích hợp theo hành vi Read Committed. Hai request không thể chỉ dựa vào cùng một giá trị còn trống đã đọc trước đó.

Ví dụ còn `100`, hai request đều muốn giữ `80`: một request có thể thành công, request còn lại sẽ không cập nhật được nếu không có thay đổi khác mở thêm hạn mức.

Những điều kiện để kết luận này có giá trị:

- Mọi đường giữ ngân sách đều cập nhật cùng hàng có thẩm quyền.
- Record reservation và bộ đếm được ghi nhất quán trong cùng transaction.
- Hủy, giải phóng, tăng giảm hạn mức và công cụ quản trị cũng giữ các invariant tương ứng.
- Giải phóng một reservation chỉ được thực hiện một lần theo state machine của nó.
- Không coi kết quả UPDATE là thành công bền vững trước khi transaction commit.

`UPDATE` không trả hàng có thể do không tồn tại, không đủ hạn mức hoặc không đáp ứng một điều kiện khác. Việc trả lỗi cho client phải tuân thủ quyền truy cập; không cần lộ ngân sách của một đối tượng caller không được phép xem.

Ví dụ này chỉ chứng minh invariant đã đưa về cùng một hàng. Không được suy rộng rằng mọi UPDATE chứa subquery hay mọi điều kiện liên quan nhiều bảng đều an toàn tương tự ở Read Committed.

## 6. Khóa hàng khi quyết định cần đọc rồi ghi nhiều dữ liệu

Khi logic cần đọc nhiều thuộc tính, tính toán và ghi các hàng liên quan, khóa một hàng có thẩm quyền có thể tạo điểm phân xử rõ ràng:

```sql
BEGIN;

SELECT limit_minor, reserved_minor
FROM budget_account
WHERE tenant_id = :tenantId
  AND budget_id = :budgetId
FOR UPDATE;

-- Đọc dữ liệu cần thiết và kiểm tra quyền, trạng thái, hạn mức.
-- Mọi đường thay đổi cùng phạm vi phải tuân theo cùng giao thức khóa.
-- Ghi reservation và thay đổi budget_account.

COMMIT;
```

Điểm quan trọng là **khóa trước khi dựa vào dữ liệu để quyết định**. Đọc ở ngoài transaction, tính toán, rồi vào transaction khóa hàng nhưng không đọc lại không bảo vệ được quyết định cũ.

Một số nguyên tắc:

- Chọn hàng khóa theo đúng phạm vi tenant và tài nguyên.
- Khóa được giữ đến khi transaction kết thúc, không đến lúc application đọc xong.
- Mọi transaction có thể phá cùng invariant phải dùng một cơ chế bảo vệ tương thích.
- Khi cần khóa nhiều tài khoản, dùng thứ tự xác định, ví dụ theo tenant và account ID.
- Giữ transaction ngắn; không chờ người dùng hoặc gọi mạng chậm trong khi giữ khóa.

Khóa trong bộ nhớ Java như `synchronized` chỉ điều phối các luồng dùng chung đối tượng trong một process. Nó không thay thế khóa hoặc ràng buộc dữ liệu khi có nhiều instance, job nền hoặc công cụ khác cùng ghi.

### 6.1. Khóa một hàng không khóa mọi điều kiện liên quan

Nếu invariant dựa trên “số hàng thỏa điều kiện”, khóa các hàng hiện có không mặc định ngăn việc thêm một hàng mới thỏa điều kiện đó.

Đặc biệt, trong PostgreSQL:

```sql
SELECT id
FROM active_reservation
WHERE tenant_id = :tenantId
  AND budget_id = :budgetId
FOR UPDATE;
```

Nếu chưa có reservation, câu lệnh không khóa được một hàng nào để ngăn hai request cùng tạo reservation mới. Không nên dùng “khóa tập rỗng” làm bảo đảm uniqueness hoặc giới hạn tổng.

Có thể khóa một hàng cha ổn định như `budget_account`, dùng unique constraint khi invariant là duy nhất, hoặc dùng serializable cho quyết định theo predicate. Không dựa vào giả định khóa khoảng của một hệ quản trị khác nếu database đang dùng không có cùng hành vi.

## 7. Write skew: snapshot ổn định vẫn có thể phá invariant

Giả sử một tổ chức có hai quản trị viên hoạt động A và B. Quy tắc là:

```text
Mỗi tổ chức phải còn ít nhất một quản trị viên hoạt động.
```

Mỗi transaction cho phép tắt một quản trị viên nếu vẫn còn người khác hoạt động.

| Bước | Transaction A | Transaction B |
| --- | --- | --- |
| 1 | Đọc thấy A và B đang hoạt động | |
| 2 | | Đọc thấy A và B đang hoạt động |
| 3 | Kết luận có thể tắt A vì còn B | |
| 4 | | Kết luận có thể tắt B vì còn A |
| 5 | Cập nhật hàng A thành không hoạt động | |
| 6 | | Cập nhật hàng B thành không hoạt động |
| 7 | Commit | Commit |

Dưới snapshot isolation như Repeatable Read của PostgreSQL, hai transaction ghi vào hai hàng khác nhau có thể cùng commit trong tình huống này. Kết quả không còn quản trị viên nào hoạt động.

Đây là **write skew**: quyết định đọc phụ thuộc chéo nhưng phần ghi không tranh chấp trực tiếp trên cùng hàng. Không có yêu cầu nào tự nó vi phạm invariant khi nhìn từ snapshot riêng.

Ba hướng bảo vệ thường dùng:

1. **Khóa một hàng cha của tổ chức.** Mọi thay đổi ảnh hưởng số quản trị viên phải khóa hàng đó trước khi kiểm tra.
2. **Duy trì bộ đếm có thẩm quyền.** Cập nhật số quản trị viên bằng điều kiện không xuống dưới một, cùng transaction với thay đổi thành viên.
3. **Dùng Serializable.** Đọc điều kiện và ghi trong cùng transaction, xử lý serialization failure rồi chạy lại toàn bộ quyết định.

Hướng thứ nhất và thứ hai đưa invariant về một điểm tranh chấp chung. Hướng thứ ba để database phát hiện lịch không thể coi là tuần tự và buộc một transaction làm lại.

Chỉ tăng từ Read Committed lên một snapshot ổn định chưa đủ để kết luận write skew biến mất.

## 8. Khi nào nên chọn Serializable?

Serializable đáng cân nhắc khi:

- Quyết định phụ thuộc tổng, sự tồn tại hoặc tập hàng được chọn bằng predicate.
- Khó xác định đầy đủ các hàng cần khóa trước khi đọc.
- Có nhiều phụ thuộc đọc–ghi mà giao thức khóa thủ công dễ thiếu sót.
- Cần kết quả tương đương một thứ tự thực thi tuần tự cho nhóm transaction tham gia.
- Ứng dụng có thể thực hiện lại một transaction bị hủy mà không lặp tác động bên ngoài.

Ví dụ quy trình:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM organization_member
WHERE tenant_id = :tenantId
  AND organization_id = :organizationId
  AND role_code = 'ADMIN'
  AND active = true;

-- Nếu việc tắt thành viên vẫn giữ ít nhất một admin:
-- UPDATE đúng thành viên trong cùng transaction.

COMMIT;
```

Ở lịch write skew, database có thể hủy một transaction thay vì cho cả hai cùng commit. Sau retry, transaction bị hủy phải đọc lại trạng thái; lúc đó có thể phải từ chối tắt người cuối cùng.

Không phải mọi transaction serializable đều sẽ thành công sau retry. Retry có thể dẫn đến một quyết định nghiệp vụ khác, và đó chính là hành vi cần thiết để giữ invariant.

Những giới hạn cần nhớ:

- Các bước đọc quyết định phải nằm trong cùng transaction được bảo vệ.
- Mọi đường ghi liên quan phải dùng cơ chế phù hợp; không giả định một transaction serializable tự sửa được đường ghi khác bỏ qua toàn bộ quy tắc.
- Unique constraint, foreign key và check constraint vẫn nên tồn tại khi mô hình biểu diễn được bằng chúng.
- Tác động ở dịch vụ bên ngoài không được rollback theo transaction nội bộ.
- Truy vấn rộng và transaction dài có thể làm tăng lượng phụ thuộc, tranh chấp và khả năng phải retry.

Trong PostgreSQL, cơ chế theo dõi predicate của serializable không nên được hiểu như một khóa ứng dụng đơn giản làm mọi writer chờ ngay. Có thể có transaction cùng tiến triển rồi một transaction bị hủy khi phát hiện không thể duy trì bảo đảm.

## 9. Constraint và optimistic concurrency bổ sung cho isolation

### 9.1. Uniqueness nên được biểu diễn bằng unique constraint

Mẫu dễ sai:

```text
SELECT xem business_intent_id đã tồn tại chưa
nếu chưa có:
    INSERT kết quả
```

Hai request có thể cùng không thấy dữ liệu. Nếu invariant là “một kết quả cho một intent trong cùng tenant”, hãy biểu diễn nó ở database:

```sql
ALTER TABLE operation_result
ADD CONSTRAINT operation_result_tenant_intent_unique
UNIQUE (tenant_id, business_intent_id);
```

Ứng dụng vẫn cần xử lý xung đột đúng: tìm kết quả thuộc đúng scope, so sánh command nếu cần và kiểm tra quyền trước khi replay. Không chuyển unique violation thành quyền bỏ kiểm tra rồi thực thi lại bằng ID khác.

### 9.2. Phiên bản giúp phát hiện cập nhật dựa trên dữ liệu cũ

Ví dụ chuyển trạng thái yêu cầu phê duyệt:

```sql
UPDATE approval_request
SET state = 'APPROVED',
    version = version + 1,
    approved_by = :actorId
WHERE tenant_id = :tenantId
  AND id = :requestId
  AND version = :expectedVersion
  AND state = 'PENDING'
RETURNING id, version;
```

Nếu không trả hàng, command không đáp ứng điều kiện chuyển trạng thái. Ứng dụng không được coi như đã duyệt thành công hoặc bỏ điều kiện để cập nhật lại.

Trường `approved_by` không tự kiểm tra người gọi có quyền duyệt. Authorization, phân tách nhiệm vụ và invariant như “người tạo không tự phê duyệt” cần được thực thi bằng logic và dữ liệu có thẩm quyền.

Optimistic concurrency trên một hàng không tự bảo vệ một invariant về tổng nhiều hàng. Nếu hai transaction cập nhật hai request khác nhau, cả hai phiên bản riêng có thể hợp lệ nhưng vẫn vượt hạn mức chung.

### 9.3. Constraint chỉ bảo vệ điều nó thực sự diễn đạt

`CHECK (balance >= 0)` bảo vệ số dư không âm trên hàng đó. Nó không chứng minh mọi khoản chi đã ghi sổ đều được phản ánh đúng trong số dư, không kiểm tra quyền đối tượng và không ngăn hoàn tiền trùng dưới nhiều định danh.

Các invariant liên hàng hoặc liên bảng cần mô hình và cơ chế bổ sung. Không giả định một CHECK thông thường có thể tự duy trì một tổng tùy ý của các hàng ở bảng khác.

## 10. Ranh giới transaction, quyền và dữ liệu đọc

### 10.1. Quyết định không được đọc ở ngoài phạm vi bảo vệ

Mẫu sai về ranh giới:

```text
Đọc hạn mức hoặc trạng thái từ cache/replica.
Kết luận được phép thực hiện.
Mở transaction Serializable.
Chỉ ghi kết quả dựa trên kết luận cũ.
```

Transaction không thể bảo vệ một phép đọc mà nó không thực hiện. Dữ liệu có thẩm quyền tham gia quyết định cần được đọc hoặc kiểm tra có điều kiện tại nơi tạo tác động.

Cache và replica có thể phục vụ hiển thị hoặc tối ưu các bước không quyết định. Nếu dùng chúng để cấp phép chi tiền hay chuyển trạng thái mà không có hàng rào kiểm tra lại, độ trễ dữ liệu có thể trở thành đường lạm dụng.

### 10.2. Một transaction phải dùng đúng kết nối và nguồn dữ liệu

Nếu bước đọc dùng một connection và bước ghi dùng connection khác ngoài transaction, đặt isolation trên connection ghi không bảo vệ bước đọc đó.

Khi dùng transaction qua framework, cần xác nhận ranh giới thực tế: thao tác nào tham gia transaction, thao tác nào mở transaction khác, và dữ liệu có đi qua cùng database hay không. Tên phương thức hoặc annotation trong mã nguồn không thay thế bằng chứng về hành vi khi chạy.

### 10.3. Quyền bị thu hồi đồng thời cần ngữ nghĩa rõ ràng

Giả sử request kiểm tra quyền duyệt trong khi một transaction khác thu hồi quyền. Serializable có thể sắp xếp request đang chồng lấn như diễn ra trước việc thu hồi. Không thể suy ra rằng “quyền phải còn ở đúng thời điểm commit thực tế” đã được bảo đảm chỉ bằng tên mức cô lập.

Nếu nghiệp vụ yêu cầu quy tắc chặt hơn cho việc thu hồi và các thao tác đang thực hiện, cần định nghĩa rõ chúng được phân xử ở điểm nào. Có thể dùng hàng phân xử chung, khóa hoặc kiểm tra phiên bản quyền tại bước tạo tác động, với cả đường thu hồi cùng tuân theo giao thức.

Trong mọi trường hợp, truy vấn phải giới hạn đúng tenant và tài nguyên được phép. Isolation không sửa lỗi dùng ID của người khác hoặc thiếu điều kiện tenant.

## 11. Retry là một phần của lựa chọn isolation

Khi chọn Serializable hoặc dùng khóa có thể deadlock, cần thiết kế transaction như một đơn vị có thể bị hủy rồi thực hiện lại.

Với PostgreSQL, các SQLSTATE thường cần phân loại gồm:

| SQLSTATE | Ý nghĩa | Cách xử lý khái quát |
| --- | --- | --- |
| `40001` | Serialization failure | Rollback và cân nhắc retry toàn bộ transaction |
| `40P01` | Deadlock detected | Rollback và cân nhắc retry toàn bộ transaction; xem lại thứ tự khóa |

Không retry mọi lỗi SQL. Unique violation, lỗi quyền, dữ liệu không hợp lệ hoặc từ chối nghiệp vụ có cách xử lý riêng.

Mã giả cho vòng retry:

```text
executeCommand(command, authenticatedContext):
    for attempt từ 1 đến giới hạn:
        mở một transaction mới với isolation đã chọn
        try:
            đọc lại dữ liệu có thẩm quyền
            kiểm tra lại quyền cần thiết và invariant
            thực hiện toàn bộ thay đổi nội bộ
            ghi kết quả và outbox nếu cần
            commit
            trả kết quả đã commit
        catch lỗi xác định transaction đã bị hủy và được phép retry:
            rollback, đóng transaction
            nếu đã hết giới hạn: trả lỗi có kiểm soát
            chờ backoff ngắn có jitter ngoài transaction
        catch lỗi khác:
            rollback nếu cần và chuyển lỗi theo hợp đồng
```

Các điểm bắt buộc:

- Retry từ đầu, gồm cả những phép đọc làm cơ sở cho quyết định.
- Không chỉ retry câu UPDATE cuối dựa trên snapshot cũ.
- Mỗi lần thử phải dùng transaction mới; transaction đã lỗi không được tiếp tục như bình thường.
- Có giới hạn số lần, thời hạn tổng và quan sát tỷ lệ abort.
- Backoff không được giữ transaction hoặc khóa cũ.
- Giữ nguyên định danh ý định nghiệp vụ để retry không tạo command mới.

Một lỗi serialization có thể xuất hiện ở bước đọc, ghi hoặc commit; không chỉ bao quanh một câu UPDATE bằng khối retry.

### 11.1. Mất kết nối lúc commit khác với serialization failure

Nếu database đã commit nhưng client mất kết nối trước khi nhận xác nhận, kết quả có thể chưa xác định từ phía ứng dụng. Không được mặc định đó là rollback và tạo lại tác động bằng một ý định mới.

Cần dùng business intent, idempotency record hoặc đường tra cứu để xác định kết quả. Chỉ tự retry theo cùng cơ chế khi hệ thống có thể nhận diện và xử lý ý định đã commit mà không lặp tác động.

### 11.2. Ranh giới JDBC minh họa

Đoạn Java sau minh họa việc đặt isolation và rollback trên cùng connection; phần vòng retry nằm bên ngoài mỗi lần thử này:

```java
try (java.sql.Connection connection = dataSource.getConnection()) {
    connection.setTransactionIsolation(
            java.sql.Connection.TRANSACTION_SERIALIZABLE);
    connection.setAutoCommit(false);

    try {
        // Tất cả phép đọc quyết định và phép ghi của lần thử
        // phải dùng connection này hoặc cùng transaction thực tế.
        // Không tạo tác động mạng không thể rollback tại đây.

        connection.commit();
    } catch (java.sql.SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (java.sql.SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
```

Đây là khung minh họa, chưa phải executor hoàn chỉnh. Khi dùng connection pool hoặc framework, cấu hình và khôi phục trạng thái connection phải theo cơ chế của hệ thống đó. SQLSTATE cần được đọc từ lỗi database phù hợp thay vì phân loại bằng chuỗi thông báo có thể thay đổi.

## 12. Tác động bên ngoài không thuộc rollback nội bộ

Ví dụ nguy hiểm:

```text
BEGIN Serializable
    kiểm tra hạn mức
    gọi cổng thanh toán thu tiền
    ghi kết quả nội bộ
COMMIT bị serialization failure
```

Rollback database không hoàn tác lần thu tiền đã xảy ra. Retry transaction có thể thu thêm lần nữa. Transaction càng dài và giữ khóa càng lâu thì tranh chấp, timeout và sự không chắc chắn càng khó xử lý.

Một hướng thiết kế phù hợp hơn:

1. Trong transaction nội bộ, kiểm tra quyền và invariant, ghi ý định hoặc khoản giữ chỗ cùng outbox.
2. Commit các dữ liệu nội bộ đó.
3. Worker giao command từ outbox với định danh ổn định.
4. Phía tạo tác động dùng idempotency hoặc cơ chế nhận diện command tương ứng.
5. Lưu trạng thái kết quả, xử lý lỗi và đối soát khi chưa biết tác động đã xảy ra hay chưa.

Outbox không tự làm giao nhận đúng một lần. Nó có thể giao lại thông điệp; consumer và nơi tạo tác động cuối vẫn cần chống trùng.

Nếu invariant trải qua nhiều database hoặc dịch vụ, cần mô hình phối hợp như giữ chỗ, saga, bù trừ có kiểm soát hoặc một nơi có thẩm quyền cho quyết định. Serializable ở một database chỉ bảo vệ phạm vi transaction mà database đó quản lý.

## 13. Bảng lựa chọn theo hình dạng invariant

| Hình dạng vấn đề | Lựa chọn có thể phù hợp | Điều kiện và giới hạn |
| --- | --- | --- |
| Một giá trị không được xuống dưới 0 | Read Committed + UPDATE có điều kiện + CHECK | Mọi đường ghi phải giữ cùng invariant |
| Một intent chỉ có một kết quả | Unique constraint + xử lý conflict trong transaction | Scope phải đúng; replay cần quyền và so sánh command |
| Một tài nguyên chỉ chuyển từ trạng thái hoặc phiên bản kỳ vọng | UPDATE có điều kiện hoặc optimistic concurrency | Không tự bảo vệ hạn mức nhiều tài nguyên |
| Quyết định trên một số hàng đã biết | Khóa hàng theo thứ tự + transaction ngắn | Khóa trước khi quyết định; tất cả đường ghi liên quan phải phối hợp |
| Tổng hoặc sự tồn tại của tập hàng có thể thêm/bớt | Hàng phân xử chung, bộ đếm có thẩm quyền hoặc Serializable | Khóa các hàng hiện có không mặc định khóa tập điều kiện |
| Đọc báo cáo cần snapshot ổn định | Repeatable Read có thể phù hợp tùy mục tiêu | Snapshot ổn định không đồng nghĩa bảo vệ quyết định ghi nhiều hàng |
| Nhiều phụ thuộc đọc–ghi khó liệt kê khóa | Serializable + retry toàn transaction | Phải giữ các phép đọc và ghi trong đúng phạm vi bảo vệ |
| Tác động đi qua dịch vụ ngoài | Transaction nội bộ + điều phối bền vững + idempotency | Isolation cục bộ không rollback tác động mạng |

Đây là bảng định hướng, không phải thuật toán chọn mức bằng tên endpoint. Cùng một nghiệp vụ có thể đổi lựa chọn khi đổi mô hình dữ liệu.

Ví dụ, giới hạn tổng của hàng nghìn reservation có thể khó bảo vệ bằng cách quét và khóa tập hàng. Nếu đưa số đã giữ về một hàng ngân sách có thẩm quyền, cập nhật có điều kiện ở Read Committed có thể đủ. Đổi lại, hàng này trở thành điểm tranh chấp cần đo tải và duy trì nhất quán với chi tiết reservation.

Không tách bộ đếm thành nhiều shard chỉ để giảm chờ khóa nếu sau đó không còn cơ chế bảo đảm giới hạn tổng. Tối ưu cách lưu không được âm thầm đổi invariant từ “không vượt” thành “có thể vượt rồi sửa sau” khi nghiệp vụ chưa cho phép.

## 14. Kiểm thử lựa chọn isolation bằng lịch cạnh tranh

Kiểm thử tuần tự chỉ xác nhận từng thao tác riêng. Cần tạo lịch mà nhiều request cùng đi qua điểm quyết định nguy hiểm.

| Tình huống | Kết quả cần kiểm tra |
| --- | --- |
| Hai khoản giữ `80`, hạn mức còn `100` | Không có hai khoản giữ cùng thành công vượt hạn mức |
| Hai lần cập nhật cùng phiên bản phê duyệt | Tối đa một chuyển trạng thái được chấp nhận |
| Hai transaction cùng tắt hai admin cuối | Vẫn còn ít nhất một admin sau các commit |
| Hai transaction cùng thấy tập reservation rỗng | Không tạo trạng thái vi phạm giới hạn hoặc uniqueness |
| Hai intent khác nhau nhắm cùng tài nguyên | Invariant vẫn giữ dù idempotency key khác nhau |
| Cùng intent qua nhiều instance | Constraint hoặc cơ chế chung ngăn kết quả trùng |
| API giữ đúng khóa nhưng job nền ghi song song | Job cũng phải giữ invariant; test phát hiện đường bỏ qua |
| Đọc điều kiện từ replica trễ rồi ghi trên primary | Hàng rào kiểm tra ở primary ngăn quyết định dựa trên dữ liệu cũ |
| Lỗi serialization tại commit | Toàn transaction được làm lại từ phép đọc đầu |
| Retry sau khi trạng thái đã thay đổi | Có thể từ chối nghiệp vụ thay vì cưỡng ép thành công |
| Hai transaction khóa tài khoản theo thứ tự ngược nhau | Deadlock được xử lý; thiết kế thống nhất thứ tự khóa |
| Mất kết nối lúc commit | Không tự tạo tác động mới khi kết quả chưa xác định |
| Nhà cung cấp đã nhận command nhưng nội bộ timeout | Đối soát bằng intent ổn định, không thu tiền lại mù |
| Thu hồi quyền đồng thời với tạo tác động | Hành vi đúng ngữ nghĩa phân xử quyền đã công bố |
| Chuyển hạn mức sang giá trị thấp hơn phần đang giữ | Constraint hoặc logic cập nhật từ chối trạng thái không hợp lệ |
| Hủy reservation hai lần đồng thời | Không giải phóng hạn mức hai lần |

Một cách tổ chức test:

```text
1. Chuẩn bị dữ liệu ở sát giới hạn invariant.
2. Mở các connection độc lập tới đúng loại database cần kiểm tra.
3. Dùng barrier/latch để các transaction cùng đọc hoặc cùng tới điểm tranh chấp.
4. Cho chúng tiếp tục, thu kết quả commit, abort và quyết định nghiệp vụ.
5. Đọc lại dữ liệu đã commit bằng connection kiểm tra riêng.
6. Kiểm tra invariant và số tác động thực tế, không chỉ status code.
```

Không dùng một connection cho mọi luồng rồi kết luận isolation hoạt động. Không thay database mục tiêu bằng một kho in-memory có hành vi khóa và snapshot khác rồi coi đó là bằng chứng đầy đủ.

Một test có thể chấp nhận serialization failure hoặc deadlock được retry đúng, nhưng không chấp nhận trạng thái sai cuối cùng. Khi đo hiệu năng, cần tính cả tỷ lệ abort, số lần retry, thời gian chờ khóa và độ trễ đuôi, không chỉ số transaction bắt đầu mỗi giây.

## 15. Quy trình quyết định và các điểm cần nhớ

Trước khi chốt lựa chọn cho một thao tác, hãy ghi được một bản giải thích ngắn theo mẫu:

```text
Invariant:
  Điều gì phải đúng sau các transaction đã commit?

Phạm vi:
  Tenant, tài nguyên, tập dữ liệu và các đường ghi tham gia là gì?

Lịch nguy hiểm:
  Hai request nào có thể cùng quyết định đúng riêng lẻ nhưng sai khi kết hợp?

Cơ chế:
  Constraint, UPDATE có điều kiện, khóa chung, version hay Serializable?

Isolation:
  Mức được chọn có đủ cùng các cơ chế trên ở database mục tiêu không?

Ranh giới:
  Mọi phép đọc quyết định và phép ghi có nằm trong phạm vi được bảo vệ không?

Thất bại và phục hồi:
  Retry toàn transaction ra sao? Xử lý commit chưa xác định và tác động ngoài thế nào?

Kiểm chứng:
  Lịch cạnh tranh nào chứng minh invariant vẫn giữ?
```

Lựa chọn tốt là lựa chọn có thể giải thích được bằng invariant và lịch cạnh tranh cụ thể. Read Committed kết hợp cập nhật có điều kiện hoặc khóa đúng có thể bảo vệ một quy tắc tốt hơn Repeatable Read dùng sai. Serializable giúp bảo vệ các quyết định phức tạp, nhưng chỉ phát huy khi transaction bao trọn dữ liệu quyết định và ứng dụng xử lý abort đúng.

Nguyên tắc cốt lõi: **atomic không đồng nghĩa với an toàn trước cạnh tranh; snapshot ổn định không đồng nghĩa với invariant được giữ**. Chọn isolation cùng mô hình dữ liệu, constraint, quyền và chiến lược phục hồi để mọi lịch được chấp nhận đều tạo ra kết quả nghiệp vụ hợp lệ.
