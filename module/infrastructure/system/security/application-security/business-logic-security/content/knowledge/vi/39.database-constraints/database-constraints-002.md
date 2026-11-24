# Check constraint

## 1. CHECK bảo vệ quy tắc nghiệp vụ ở đâu?

`CHECK` là ràng buộc khai báo một điều kiện mà dữ liệu được ghi vào cơ sở dữ liệu phải thỏa mãn theo ngữ nghĩa của hệ quản trị. Nó phù hợp với những quy tắc có thể quyết định từ giá trị của một bản ghi, chẳng hạn số lượng phải dương, mức giảm không vượt giá gốc hoặc hai mốc thời gian phải có thứ tự hợp lệ.

Trong bảo mật logic nghiệp vụ, `CHECK` tạo thêm một điểm chặn tại nơi lưu dữ liệu. Kẻ tấn công có thể bỏ qua giao diện, gọi thẳng API hoặc lợi dụng một đường import thiếu kiểm tra. Nếu ràng buộc đang được thực thi đúng tại cơ sở dữ liệu, những đường ghi đó vẫn không thể lưu một bản ghi vi phạm điều kiện đã khai báo.

Ví dụ: ứng dụng yêu cầu số lượng mua lớn hơn 0, nhưng một endpoint cũ chấp nhận `quantity = -3`. Nếu phép tính trừ kho dùng giá trị âm, tồn kho có thể tăng hoặc tổng tiền có thể bị tính sai. Ràng buộc `CHECK (quantity > 0)` chặn giá trị âm ở tầng lưu trữ, kể cả khi endpoint quên kiểm tra.

Tuy nhiên, `CHECK` không tự biết ai được sửa giá, một phê duyệt có thật sự hợp lệ hay không, hoặc một thao tác đã được thực hiện trước đó chưa. Thiết kế cần dùng nó đúng phạm vi, kết hợp với quyền theo đối tượng, transaction, state machine và định danh thao tác.

## 2. Phân biệt CHECK với các cơ chế khác

| Cơ chế | Câu hỏi được bảo vệ | Ví dụ |
|---|---|---|
| Kiểu dữ liệu | Giá trị có biểu diễn được theo kiểu và độ chính xác đã chọn không? | Số lượng nguyên, số tiền thập phân có giới hạn độ lớn |
| `NOT NULL` | Trường bắt buộc có giá trị không? | Mọi dòng đơn hàng phải có số lượng |
| `CHECK` | Các giá trị của bản ghi có thỏa biểu thức không? | Số lượng dương, số tiền giảm không vượt giá gốc |
| `UNIQUE` | Có trùng một khóa được xác định không? | Một định danh thao tác trong một phạm vi nghiệp vụ |
| `FOREIGN KEY` | Tham chiếu có phù hợp quan hệ được khai báo không? | Dòng đơn hàng thuộc một đơn tồn tại |
| Quyền và logic ứng dụng | Người gọi có được thực hiện hành động này không? | Nhân viên chỉ sửa sản phẩm thuộc phạm vi được giao |
| Transaction và điều phối | Nhiều thay đổi cạnh tranh có giữ invariant chung không? | Giữ chỗ kho và tạo bản ghi giữ chỗ cùng thành công |

Không thay `UNIQUE` bằng một phép kiểm tra “chưa thấy dòng giống nhau” trong ứng dụng. Tương tự, không thay kiểm tra quyền bằng `CHECK (tenant_id > 0)`: một tenant ID dương vẫn có thể là tenant mà người gọi không được phép truy cập.

Các cơ chế bổ sung cho nhau. Một trường số lượng thường cần cả kiểu nguyên, `NOT NULL`, `CHECK` và logic kiểm tra nghiệp vụ tại bước thực hiện.

## 3. Ngữ nghĩa quan trọng: FALSE khác UNKNOWN

### 3.1. CHECK không thay thế NOT NULL

Trong ngữ nghĩa SQL thông dụng của các ví dụ dưới đây, biểu thức `CHECK` bị vi phạm khi kết quả là `FALSE`. Kết quả `TRUE` hoặc `UNKNOWN` không bị chính ràng buộc đó từ chối. `UNKNOWN` thường xuất hiện khi một phép so sánh có toán hạng `NULL`.

Xét khai báo:

```sql
quantity INTEGER CHECK (quantity > 0)
```

| Giá trị `quantity` | Kết quả `quantity > 0` | Bị CHECK này từ chối? |
|---|---|---|
| `3` | `TRUE` | Không |
| `0` | `FALSE` | Có |
| `-3` | `FALSE` | Có |
| `NULL` | `UNKNOWN` | Không |

Nếu số lượng là trường bắt buộc, cần khai báo riêng:

```sql
quantity INTEGER NOT NULL,
CONSTRAINT ck_order_line_quantity_positive CHECK (quantity > 0)
```

Không dùng `quantity <> NULL` để kiểm tra có giá trị. SQL dùng `IS NULL` hoặc `IS NOT NULL` cho mục đích đó.

### 3.2. Danh sách trạng thái cũng có bẫy NULL

```sql
status VARCHAR(24) CHECK (status IN ('DRAFT', 'APPROVED', 'CANCELLED'))
```

Khai báo trên giới hạn những chuỗi có giá trị, nhưng không tự buộc `status` phải có giá trị. Nếu nghiệp vụ không chấp nhận trạng thái thiếu, cần `NOT NULL` cùng ràng buộc danh sách.

`DEFAULT` cũng không thay thế `NOT NULL`: một đường ghi có thể cung cấp `NULL` rõ ràng thay vì bỏ qua cột để dùng giá trị mặc định.

### 3.3. NULL có thể là trạng thái nghiệp vụ được phép

Ví dụ một khoảng hiệu lực phải có thời điểm bắt đầu nhưng được phép không có thời điểm kết thúc:

```sql
starts_at TIMESTAMP NOT NULL,
ends_at TIMESTAMP,
CONSTRAINT ck_validity_time_order
    CHECK (ends_at IS NULL OR ends_at > starts_at)
```

Ở đây `NULL` của `ends_at` có nghĩa được định nghĩa là không có mốc kết thúc. Nếu nghiệp vụ bắt buộc phải có mốc kết thúc, hãy dùng `NOT NULL`; không vô tình để phép so sánh với `NULL` quyết định chính sách.

Kiểu thời gian, múi giờ và cách lưu thời điểm phải được chọn nhất quán với hệ quản trị. Biểu thức chỉ kiểm tra thứ tự các giá trị được lưu, không tự sửa cách client hiểu thời gian.

## 4. Thiết kế một dòng đơn hàng có invariant rõ ràng

Các ví dụ SQL trong bài minh họa nguyên tắc, không gắn với một phiên bản hệ quản trị cụ thể. Khi hiện thực, cần xác minh cú pháp, kiểu dữ liệu và chế độ thực thi ràng buộc của hệ thống đang dùng.

Giả sử chính sách của ví dụ là:

- Mỗi dòng có từ 1 đến 10.000 đơn vị; đây là giới hạn minh họa của nghiệp vụ này.
- `gross_amount` là tổng tiền trước giảm của dòng, không phải đơn giá.
- `discount_amount` không âm và không vượt tổng tiền trước giảm.
- `net_amount` bằng tổng tiền trước giảm trừ số tiền giảm.
- Các trường tiền trong ví dụ dùng cùng một đơn vị và quy tắc làm tròn đã được hệ thống xác định.

```sql
CREATE TABLE order_line (
    tenant_id BIGINT NOT NULL,
    line_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    gross_amount DECIMAL(18, 2) NOT NULL,
    discount_amount DECIMAL(18, 2) NOT NULL,
    net_amount DECIMAL(18, 2) NOT NULL,

    CONSTRAINT pk_order_line
        PRIMARY KEY (tenant_id, line_id),
    CONSTRAINT ck_order_line_quantity
        CHECK (quantity > 0 AND quantity <= 10000),
    CONSTRAINT ck_order_line_gross_nonnegative
        CHECK (gross_amount >= 0),
    CONSTRAINT ck_order_line_discount_nonnegative
        CHECK (discount_amount >= 0),
    CONSTRAINT ck_order_line_discount_within_gross
        CHECK (discount_amount <= gross_amount),
    CONSTRAINT ck_order_line_net_consistent
        CHECK (net_amount = gross_amount - discount_amount)
);
```

Các ràng buộc đảm bảo tính nhất quán của những giá trị được lưu. Chúng không chứng minh `gross_amount` là giá hợp lệ từ bảng giá, người gọi được phép áp dụng mức giảm hoặc người dùng đã chấp nhận số tiền đó.

Một request gửi cả ba giá trị 0 có thể thỏa các điều kiện về tiền trong ví dụ. Nếu hàng miễn phí chỉ được phép theo một chính sách riêng, phải kiểm tra chính sách đó ở bước xác định giá và phê duyệt. Không mặc định rằng một công thức đúng đồng nghĩa giá có thẩm quyền.

Nếu `net_amount` luôn có thể tính từ hai trường còn lại, có thể cân nhắc không lưu lặp hoặc dùng cơ chế cột sinh theo khả năng của hệ quản trị. Nếu vẫn lưu để đáp ứng yêu cầu cụ thể, ràng buộc giúp tránh ba trường lệch nhau.

## 5. Kiểu số, độ chính xác và dữ liệu trước khi CHECK chạy

### 5.1. CHECK đánh giá giá trị theo mô hình lưu trữ

Việc phân tích đầu vào, chuyển kiểu, giới hạn độ lớn hoặc làm tròn có thể diễn ra trước hoặc trong quá trình ghi theo hệ quản trị và driver. Vì vậy, cần phân biệt giá trị người dùng gửi với giá trị thực sự được biểu thức ràng buộc đánh giá.

Không dùng `CHECK` để thay thế quy tắc tiếp nhận độ chính xác. Nếu nghiệp vụ chỉ nhận hai chữ số thập phân, ứng dụng phải quyết định từ chối hay làm tròn đầu vào nhiều chữ số và thông báo theo hợp đồng. Đừng để một chuyển kiểu ngầm vô tình quyết định giá mà người dùng chưa xác nhận.

### 5.2. Tránh công thức tiền dựa vào số chấm động nhị phân

Với tiền và các đại lượng yêu cầu thập phân chính xác, thường cần kiểu số thập phân phù hợp hoặc số nguyên biểu diễn đơn vị nhỏ nhất đã được định nghĩa. Trong Java, `BigDecimal` giúp biểu diễn và tính toán thập phân theo quy tắc rõ ràng; vẫn phải chọn scale, cách làm tròn và giới hạn giá trị.

Nếu dùng số chấm động nhị phân, phép kiểm tra bằng nhau giữa các kết quả tính toán có thể không khớp với ý định nghiệp vụ. Thêm một sai số tùy ý vào `CHECK` có thể lại cho phép giá trị không mong muốn; nên giải quyết mô hình số và quy tắc làm tròn trước.

### 5.3. Giới hạn miền và tránh tràn số

Biểu thức cộng, trừ hoặc nhân có thể vượt miền kiểu dữ liệu theo quy tắc của hệ quản trị. Cần chọn độ chính xác cho cả cột và phép tính, giới hạn đầu vào và kiểm thử các giá trị sát biên.

Không giả định mọi giá trị phù hợp từng cột thì mọi phép nhân giữa chúng đều biểu diễn được. Với số lượng và đơn giá rất lớn, tổng tiền có thể vượt giới hạn dù từng toán hạng riêng đều hợp lệ.

## 6. Kiểm tra hình dạng trạng thái và bằng chứng phê duyệt

Một yêu cầu đổi giá có thể cần các quy tắc về tính đầy đủ của dữ liệu:

- Trạng thái thuộc danh sách cho phép.
- Người duyệt và thời điểm duyệt cùng có giá trị hoặc cùng không có.
- Trạng thái `APPROVED` phải có thông tin người duyệt.
- Theo chính sách minh họa, tài khoản tạo yêu cầu không được là tài khoản duyệt.

```sql
CREATE TABLE price_change_request (
    tenant_id BIGINT NOT NULL,
    request_id BIGINT NOT NULL,
    requested_by BIGINT NOT NULL,
    status VARCHAR(24) NOT NULL,
    approved_by BIGINT,
    approved_at TIMESTAMP,
    revision BIGINT NOT NULL,

    CONSTRAINT pk_price_change_request
        PRIMARY KEY (tenant_id, request_id),
    CONSTRAINT ck_price_change_status
        CHECK (status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'CANCELLED')),
    CONSTRAINT ck_price_change_approval_pair
        CHECK (
            (approved_by IS NULL AND approved_at IS NULL)
            OR
            (approved_by IS NOT NULL AND approved_at IS NOT NULL)
        ),
    CONSTRAINT ck_price_change_approved_evidence
        CHECK (status <> 'APPROVED' OR approved_by IS NOT NULL),
    CONSTRAINT ck_price_change_separate_accounts
        CHECK (approved_by IS NULL OR approved_by <> requested_by),
    CONSTRAINT ck_price_change_revision
        CHECK (revision >= 0)
);
```

Mô hình này cho phép giữ thông tin phê duyệt ở một số trạng thái khác để phục vụ lịch sử theo chính sách. Nó không quy định rằng mọi trạng thái khác `APPROVED` đều phải xóa thông tin duyệt. Nếu nghiệp vụ có yêu cầu khác, cần biểu diễn rõ thay vì để những tổ hợp chưa được cân nhắc tồn tại.

Các ràng buộc trên chỉ kiểm tra hình dạng và quan hệ giữa giá trị đã lưu. Chúng không chứng minh:

- `approved_by` là người dùng đang thực hiện thao tác.
- Tài khoản đó có vai trò hoặc hạn mức duyệt phù hợp.
- Hai tài khoản khác nhau thuộc hai người độc lập theo yêu cầu kiểm soát.
- Nội dung được duyệt là đúng phiên bản giá, sản phẩm và đối tượng hưởng lợi hiện tại.
- Người dùng được phép chuyển từ trạng thái trước sang `APPROVED`.

Các giá trị như `requested_by`, `approved_by` và thời điểm phải do máy chủ xác lập từ nguồn có thẩm quyền. Không nhận nguyên chúng từ request rồi coi việc qua `CHECK` là đã hoàn thành phê duyệt.

## 7. CHECK không tự thực thi state machine

### 7.1. Trạng thái hợp lệ khác với chuyển trạng thái hợp lệ

`CHECK (status IN (...))` ngăn một chuỗi trạng thái không được định nghĩa. Nó không tự so sánh trạng thái cũ với trạng thái mới để quyết định một chuyển trạng thái có được phép hay không.

Một bản ghi `CANCELLED` bị cập nhật thành `APPROVED` vẫn có thể thỏa danh sách trạng thái và các trường bằng chứng, dù nghiệp vụ cấm mở lại yêu cầu đã hủy.

Cần kiểm tra trạng thái nguồn tại ranh giới cập nhật. Ví dụ SQL minh họa:

```sql
UPDATE price_change_request
SET status = 'APPROVED',
    approved_by = :trusted_actor_id,
    approved_at = :trusted_now,
    revision = revision + 1
WHERE tenant_id = :trusted_tenant
  AND request_id = :request_id
  AND status = 'PENDING_APPROVAL'
  AND revision = :expected_revision
  AND requested_by <> :trusted_actor_id;
```

Các tham số có dấu `:` minh họa tham số bind của tầng truy cập dữ liệu. Trước khi áp dụng, máy chủ vẫn phải kiểm tra quyền duyệt, phạm vi đối tượng và nội dung được duyệt. Số dòng cập nhật bằng 0 không phải thành công: có thể trạng thái hoặc revision đã thay đổi, điều kiện không thỏa hoặc đối tượng không thuộc phạm vi được phép.

### 7.2. Thời gian trôi qua không làm CHECK tự chạy lại

Một ý tưởng dễ sai là khai báo điều kiện tương tự “thời hạn phải lớn hơn thời gian hiện tại” để chứng minh một phiếu vẫn có hiệu lực.

Ngay cả ở nơi cho phép biểu thức như vậy, việc đồng hồ đi qua mốc hết hạn không tự tạo một lệnh cập nhật để đánh giá lại mọi dòng. Khả năng dùng hàm thời gian trong ràng buộc cũng phụ thuộc hệ quản trị.

Hãy tách hai mục tiêu:

- Kiểm tra cấu trúc dữ liệu, ví dụ `expires_at > issued_at`, phù hợp với một điều kiện dựa trên giá trị đã lưu.
- Kiểm tra còn hiệu lực tại lúc sử dụng, ví dụ đối chiếu `expires_at` với nguồn thời gian có thẩm quyền, thuộc logic thực hiện thao tác.

Không thay một quy tắc tại thời điểm sử dụng bằng việc dữ liệu từng hợp lệ lúc được ghi.

## 8. Giới hạn với nhiều dòng, nhiều bảng và quyền truy cập

### 8.1. Không dùng CHECK như truy vấn tổng hợp toàn hệ thống

Các quy tắc sau không chỉ phụ thuộc một bản ghi:

| Invariant | Vì sao một CHECK trên một dòng chưa đủ? |
|---|---|
| Tổng phiếu cấp từ một phê duyệt không vượt hạn mức | Cần xét nhiều tác động hoặc một bộ đếm được bảo vệ |
| Mã ưu đãi chỉ dùng một lần trong một phạm vi | Cần phân xử tính duy nhất giữa các dòng |
| Tổng lượng giữ chỗ không vượt tồn kho | Cần phối hợp lượng hàng và các lần giữ chỗ cạnh tranh |
| Luôn còn ít nhất một người phê duyệt đủ quyền | Hai transaction có thể sửa hai người khác nhau |
| Đối tượng liên quan phải thuộc cùng tenant | Cần quan hệ hoặc truy vấn/ràng buộc phạm vi phù hợp |

Không phải mọi hệ quản trị đều cho phép truy vấn hoặc hàm tùy ý trong `CHECK`. Ngay cả khi có thể gọi một hàm đọc dữ liệu khác, không được suy ra rằng mọi thay đổi ở dữ liệu được đọc sẽ kích hoạt kiểm tra lại hoặc được phân xử đúng dưới cạnh tranh.

Với invariant liên dòng, hãy chọn `UNIQUE`, khóa ngoại thích hợp, một aggregate được cập nhật nguyên tử hoặc giao thức transaction/khóa phù hợp. Trigger có thể hỗ trợ một số quy tắc trong một hệ quản trị, nhưng cũng cần được thiết kế và kiểm thử cạnh tranh; tên gọi trigger không tự tạo ra bảo đảm.

### 8.2. Tenant hợp lệ về kiểu không chứng minh quyền theo đối tượng

`CHECK (tenant_id > 0)` chỉ hạn chế miền số. Nó không chứng minh người gọi thuộc tenant đó. Tương tự, `owner_id IS NOT NULL` không chứng minh người gọi được thay chủ sở hữu.

Cần lấy tenant từ ngữ cảnh xác thực, áp dụng điều kiện phạm vi trong truy vấn và kiểm tra quyền cho hành động. Có thể bổ sung các cơ chế cơ sở dữ liệu phù hợp như quan hệ khóa ghép hoặc chính sách truy cập nếu hệ thống dùng chúng; `CHECK` không thay thế các lớp này.

### 8.3. Phê duyệt có tồn tại chưa đủ để áp dụng mọi nội dung

Một trường `approval_id` không rỗng hoặc thậm chí tham chiếu đến một phê duyệt tồn tại không chứng minh phê duyệt đó dành cho dòng dữ liệu hiện tại. Cần ràng buộc nội dung, phiên bản, đối tượng và phạm vi theo chính sách.

Không biến `CHECK (approval_id IS NOT NULL)` thành bằng chứng rằng mọi mức giảm đều đã được duyệt.

## 9. CHECK và ghi đồng thời: chống số âm chưa đủ chống bán trùng

Giả sử bảng kho có `available INTEGER NOT NULL` và `CHECK (available >= 0)`. Hai worker cùng đọc `available = 10`, mỗi worker bán 6 rồi tự tính giá trị mới là 4.

Nếu cả hai ghi `available = 4`, từng bản ghi cuối đều không âm. `CHECK` không phát hiện rằng hệ thống đã xác nhận bán tổng cộng 12 đơn vị. Đây là lỗi mất cập nhật và sai ranh giới thực hiện nghiệp vụ.

Một cách tiếp cận phù hợp là cập nhật lượng khả dụng có điều kiện tại nguồn ghi có thẩm quyền:

```sql
UPDATE stock
SET available = available - :quantity
WHERE tenant_id = :trusted_tenant
  AND sku = :sku
  AND :quantity > 0
  AND available >= :quantity;
```

Trong một cơ sở dữ liệu có bảo đảm transaction phù hợp, câu lệnh này kết hợp điều kiện và phép giảm tại ranh giới ghi thay vì ghi lại một giá trị tính từ ảnh chụp cũ. Cần xử lý số dòng cập nhật, xung đột hoặc lỗi transaction theo hệ quản trị. Không xác nhận bán nếu thao tác giảm chưa thành công và commit.

`CHECK (available >= 0)` vẫn hữu ích làm rào chắn bổ sung cho các đường ghi khác. Tuy nhiên, nó không cấm tăng kho: nếu tham số giảm là số âm, phép trừ có thể làm kho tăng và ràng buộc vẫn thỏa. Vì vậy, miền của **lệnh** và miền của **trạng thái** là hai điều cần kiểm tra riêng.

Bản ghi tiêu thụ/giữ chỗ, định danh ý định và cập nhật số lượng phải được phối hợp trong transaction nếu chúng là một tác động nguyên tử. Nếu hai vùng ghi độc lập, mỗi nơi có thể giữ số không âm riêng nhưng tổng cam kết vẫn vượt kho chung. `CHECK` cục bộ không tạo bảo đảm nhất quán phân tán.

## 10. Transaction, lỗi ràng buộc và đường ghi Java

### 10.1. Không để lỗi một dòng bị biến thành thành công một phần ngoài ý muốn

Một import có thể ghi nhiều dòng. Nếu dòng giữa vi phạm `CHECK`, hành vi đối với câu lệnh và transaction còn tùy hệ quản trị, driver và ranh giới transaction. Không giả định bắt exception rồi tiếp tục luôn an toàn.

Nếu hợp đồng là toàn bộ import cùng thành công hoặc cùng thất bại, cần transaction bao trùm đúng phạm vi và rollback khi có lỗi. Nếu cho phép thành công từng phần, phải quy định rõ đơn vị nguyên tử, số dòng đã commit và cách xử lý dòng thất bại. Một trạng thái `FAILED` của job không tự xóa các chunk đã commit trước đó.

Một số lỗi chỉ được phía ứng dụng quan sát khi flush hoặc commit tùy cách truy cập dữ liệu. Vòng lặp đã chạy xong chưa chứng minh import đã thành công.

### 10.2. Cập nhật các trường phụ thuộc trong ranh giới thích hợp

Với `net_amount = gross_amount - discount_amount`, việc cập nhật từng trường bằng các câu lệnh riêng có thể tạo trạng thái trung gian vi phạm ràng buộc. Nên gửi một thay đổi nhất quán cho các trường phụ thuộc, thay vì tắt `CHECK` để cho trạng thái sai đi qua.

Thời điểm kiểm tra và khả năng trì hoãn một loại ràng buộc phụ thuộc hệ quản trị. Không giả định một câu lệnh sửa ở phía sau sẽ cứu được một câu lệnh trước đã bị từ chối.

### 10.3. Kiểm tra ở Java để phản hồi tốt, ở database để chặn dữ liệu sai

Ứng dụng nên kiểm tra sớm các trường bắt buộc, miền giá trị và quy tắc số để trả lỗi rõ ràng. Ràng buộc cơ sở dữ liệu vẫn cần thiết vì còn có cạnh tranh và các đường ghi khác.

Đoạn Java sau chỉ minh họa việc tiếp nhận một số tiền không âm với đúng hai chữ số thập phân:

```java
BigDecimal amount = new BigDecimal(input);
if (amount.signum() < 0) {
    throw new IllegalArgumentException("Số tiền không được âm");
}
amount = amount.setScale(2, RoundingMode.UNNECESSARY);
```

Đây là một phần logic, chưa bao gồm kiểm tra `input` thiếu/sai định dạng, giới hạn độ lớn, quyền hay quy tắc định giá. `UNNECESSARY` thể hiện lựa chọn không chấp nhận làm tròn mất độ chính xác trong ví dụ; một nghiệp vụ khác có thể chọn quy tắc làm tròn khác và phải áp dụng nhất quán.

Khi dùng JDBC, bind số thập phân bằng kiểu phù hợp như `setBigDecimal`, dùng prepared statement và đặt ranh giới transaction rõ ràng. Khi dùng ORM, các annotation kiểm tra đầu vào không tự chứng minh schema thực tế đã có `CHECK`; cần quản lý migration và xác nhận trạng thái schema.

## 11. Thêm CHECK vào hệ thống đang có dữ liệu

### 11.1. Kiểm tra dữ liệu cũ trước khi áp dụng chính sách

Một ràng buộc mới có thể phát hiện các dòng đang tồn tại không hợp lệ. Không nên chỉ sửa script tạo bảng cho môi trường mới rồi coi các môi trường đã chạy đều được bảo vệ.

Quy trình migration cần xem xét:

1. Phát biểu chính xác invariant, bao gồm ý nghĩa của `NULL`, giá trị 0 và các ngoại lệ nghiệp vụ.
2. Đo và phân loại dữ liệu hiện có có thể vi phạm, bằng truy vấn trong phạm vi được phép.
3. Xác định cách sửa từng loại dữ liệu với bằng chứng và quyết định nghiệp vụ phù hợp.
4. Phối hợp triển khai đường ghi ứng dụng để không tiếp tục tạo dữ liệu sai.
5. Tạo/kích hoạt ràng buộc và kiểm tra trạng thái thực thi, trạng thái xác minh dữ liệu cũ theo hệ quản trị.
6. Theo dõi lỗi và các đường ghi còn vi phạm sau triển khai.

Một số hệ quản trị có cơ chế tách việc áp dụng cho dữ liệu mới khỏi việc xác minh dữ liệu đã tồn tại. Nếu dùng cơ chế như vậy, phải phân biệt rõ “đang chặn dữ liệu mới sai” với “toàn bộ dữ liệu cũ đã được xác minh”. Không suy ra cả hai chỉ từ tên ràng buộc xuất hiện trong schema.

### 11.2. Đừng sửa dữ liệu bằng quy tắc thuận tiện nhưng sai nghiệp vụ

Ví dụ, không đổi mọi số tiền âm thành 0 chỉ để migration qua được. Số âm có thể là dữ liệu lỗi, một loại điều chỉnh đang được mô hình hóa chung hoặc bằng chứng của một lỗ hổng cần điều tra.

Nếu nghiệp vụ có bút toán ghi có/ghi nợ, phải chọn mô hình dấu và loại bút toán đúng trước khi cấm giá trị âm. Nếu đơn hủy vẫn giữ dòng lịch sử, không áp dụng một quy tắc mới theo cách phá mất khả năng biểu diễn lịch sử hợp lệ.

Dọn dữ liệu cần giữ liên kết và audit, tránh tạo ra một trạng thái có vẻ đẹp về mặt số học nhưng làm mất tác động thực tế đã diễn ra.

### 11.3. Tránh khoảng hở giữa kiểm tra và kích hoạt

Truy vấn kiểm tra dữ liệu cũ chỉ phản ánh một thời điểm. Trong lúc migration chuẩn bị ràng buộc, các writer khác có thể chèn thêm dữ liệu sai.

Cần một chiến lược triển khai phù hợp với hệ quản trị: phối hợp các phiên bản ứng dụng, quản lý đường ghi và chọn cách thêm/xác minh ràng buộc có bảo đảm mong muốn. Đánh giá ảnh hưởng khóa, thời gian xác minh và kế hoạch phục hồi migration trước khi áp dụng trên dữ liệu lớn.

Không cấp quyền cho tài khoản ứng dụng tự tắt ràng buộc để retry request. Công cụ import, batch và script quản trị cũng phải nằm trong mô hình kiểm soát; một đường ghi đặc quyền có thể làm mất bảo đảm mà API đang dựa vào.

## 12. Xử lý lỗi mà không làm lộ dữ liệu hoặc che mất sự cố

### 12.1. Ánh xạ lỗi theo ràng buộc đã biết

Đặt tên constraint rõ ràng giúp vận hành biết invariant nào bị vi phạm. Tầng truy cập dữ liệu có thể ánh xạ các lỗi đã nhận diện sang mã lỗi nghiệp vụ, chẳng hạn số lượng ngoài miền hoặc số tiền không nhất quán.

Không giả định mọi lỗi toàn vẹn dữ liệu đều là `CHECK`. Lỗi `NOT NULL`, `UNIQUE`, khóa ngoại hoặc chuyển kiểu cần được phân biệt theo khả năng của driver và hệ quản trị. Trong Java, thông tin từ `SQLException` hoặc exception do framework bọc cần được xử lý qua một lớp ánh xạ phù hợp; không dựa duy nhất vào một chuỗi thông báo tự do.

Không trả nguyên thông báo lỗi cơ sở dữ liệu, SQL, tên bảng nội bộ hoặc giá trị nhạy cảm cho client. Phản hồi có thể nêu trường hoặc quy tắc bị vi phạm trong phạm vi người gọi được phép biết.

### 12.2. Không biến lỗi ràng buộc thành retry vô hạn

Gửi lại cùng một số lượng âm không làm nó trở nên hợp lệ. Đây thường là lỗi cần sửa dữ liệu hoặc lệnh, không phải lỗi tạm thời để retry tự động.

Phân biệt:

- Giá trị chắc chắn vi phạm miền: từ chối và yêu cầu sửa nội dung.
- Xung đột do dữ liệu đã đổi: đánh giá lại lệnh theo quyền và invariant, không tự bỏ ràng buộc.
- Kết quả commit chưa rõ do lỗi kết nối: tra cứu định danh thao tác trước khi thực hiện lại.
- Lỗi hệ thống hoặc mapping chưa nhận diện: giữ bằng chứng, xử lý theo cơ chế lỗi tương ứng.

Không bắt một lỗi `CHECK`, thay số tiền hoặc trạng thái bằng giá trị khác rồi báo thành công nếu việc đó không nằm trong hợp đồng nghiệp vụ được người dùng chấp nhận.

### 12.3. Theo dõi lỗi để tìm đường ghi yếu

Các lần vi phạm có thể đến từ lỗi ứng dụng, cấu hình làm tròn khác nhau, dữ liệu import cũ hoặc hành vi thử lạm dụng. Theo dõi theo tên ràng buộc/mã quy tắc, đường ghi, phiên bản triển khai và phạm vi phù hợp.

Không cần đưa toàn bộ nội dung request hoặc dữ liệu cá nhân vào log. Một tỷ lệ lỗi tăng đột ngột cần được điều tra, nhưng số lần bị ràng buộc chặn không tự chứng minh đã có dữ liệu sai được commit.

## 13. Những tình huống lạm dụng và giới hạn bảo vệ

| Tình huống | CHECK có thể chặn gì? | Còn cần cơ chế nào? |
|---|---|---|
| Gửi số lượng âm | Chặn dòng có `quantity <= 0` theo schema mẫu | Kiểm tra miền lệnh ở các đường không lưu dòng đó |
| Gửi `NULL` để né phép so sánh | CHECK riêng có thể không chặn | `NOT NULL` hoặc quy tắc cho NULL được biểu diễn rõ |
| Giảm giá vượt tổng tiền | Chặn `discount_amount > gross_amount` | Giá gốc có thẩm quyền và phê duyệt mức giảm |
| Đặt mọi giá trị tiền bằng 0 | Có thể vẫn thỏa các công thức | Chính sách miễn phí, định giá và quyền thay giá |
| Tự gửi ID người duyệt khác người tạo | Có thể thỏa quy tắc hai ID khác nhau | Xác định chủ thể tin cậy, quyền duyệt và nội dung phê duyệt |
| Chuyển trực tiếp từ hủy sang duyệt | Trạng thái đích có thể vẫn thuộc danh sách hợp lệ | State machine, trạng thái nguồn và revision |
| Hai lần bán cùng đọc tồn kho 10 rồi ghi 4 | Cả hai giá trị cuối vẫn không âm | Cập nhật nguyên tử và ranh giới xác nhận nghiệp vụ |
| Dùng phê duyệt qua nhiều request | Mỗi dòng riêng có thể đều hợp lệ | Tính duy nhất theo ý định/phê duyệt và idempotency |
| Sửa đối tượng của tenant khác | Tenant ID có thể vẫn hợp lệ về miền | Quyền theo đối tượng và điều kiện phạm vi ở máy chủ |
| Dùng phiếu sau hết hạn | Dữ liệu thời hạn có thể vẫn đúng thứ tự | Kiểm tra hiệu lực tại thời điểm sử dụng |
| Import bỏ qua validation giao diện | Chặn các giá trị sai thuộc ràng buộc đang thực thi | Transaction, quyền import và kiểm tra toàn bộ quy tắc còn lại |
| Tắt constraint để nạp dữ liệu | Ràng buộc không còn bảo vệ đường đó | Quản lý quyền DDL, quy trình migration và xác minh lại |

Một rào chắn tốt cần có cam kết chính xác: `CHECK` bảo vệ những biểu thức đã khai báo và đang được thực thi. Không nên mô tả nó như bằng chứng rằng mọi dòng đã được phân quyền, phê duyệt và xử lý đúng lịch sử nghiệp vụ.

## 14. Kiểm thử CHECK và các ranh giới liên quan

Kiểm thử phải chạy trên hệ quản trị và schema thật của môi trường kiểm thử khi cần xác nhận hành vi constraint. Một bài kiểm tra chỉ gọi hàm validation Java không chứng minh database đã từ chối đường ghi khác.

| Ca kiểm thử | Kết quả cần xác nhận |
|---|---|
| `quantity = 1` và `quantity = 10000` trong schema mẫu | Giá trị biên hợp lệ được lưu nếu các điều kiện khác đều thỏa |
| `quantity = 0`, `-1`, `10001` | Bị ràng buộc số lượng từ chối |
| `quantity = NULL` | Bị `NOT NULL` từ chối, không dựa vào so sánh với NULL |
| `discount_amount = 0` | Được phép theo chính sách của schema mẫu |
| `discount_amount = gross_amount` | Được phép về mặt công thức; chính sách miễn phí vẫn được kiểm tra riêng |
| Giảm giá âm hoặc lớn hơn giá gốc | Bị ràng buộc tương ứng từ chối |
| `net_amount` lệch với hiệu hai trường còn lại | Bị từ chối, không được tự sửa âm thầm sau lỗi |
| Một trường tiền bắt buộc là NULL | Bị `NOT NULL` chặn |
| Một mốc kết thúc NULL trong mô hình cho phép mở | Được phép theo chính sách thời gian đã khai báo |
| Mốc kết thúc bằng hoặc trước mốc bắt đầu | Bị từ chối trong mô hình yêu cầu lớn hơn nghiêm ngặt |
| `status = NULL` hoặc một chuỗi không nằm trong danh sách | Lần lượt bị `NOT NULL` hoặc CHECK trạng thái chặn |
| Chỉ có người duyệt hoặc chỉ có thời điểm duyệt | Bị ràng buộc cặp thông tin chặn |
| Trạng thái APPROVED thiếu thông tin duyệt | Bị ràng buộc hình dạng dữ liệu chặn |
| Người tạo và người duyệt cùng ID | Bị chặn theo chính sách tách tài khoản của ví dụ |
| Request giả mạo người duyệt khác ID | API không dùng dữ liệu giả làm bằng chứng; không kỳ vọng CHECK tự nhận diện người thật |
| Cập nhật một dòng đang hợp lệ thành giá trị sai | UPDATE cũng bị ràng buộc đang thực thi chặn |
| Ghi trực tiếp qua JDBC hoặc đường import | Cùng invariant cơ sở dữ liệu vẫn được giữ |
| Đầu vào có thêm chữ số thập phân hoặc sát giới hạn số | Hành vi từ chối/làm tròn đúng chính sách, không phụ thuộc chuyển kiểu ngoài ý muốn |
| Hai worker cùng tiêu thụ một lượng kho | Không xác nhận tác động trùng chỉ vì từng giá trị lưu đều không âm |
| Lỗi giữa một import nguyên tử | Không còn các thay đổi thuộc transaction đã rollback; chỉ báo thành công sau commit |
| Dữ liệu cũ vi phạm khi thêm ràng buộc | Migration phát hiện và có quy trình xử lý, trạng thái xác minh được ghi nhận đúng |
| Đồng hồ đi qua thời hạn của phiếu | Bước sử dụng từ chối theo thời gian; không trông chờ CHECK tự chạy lại |

Nên tách kiểm thử miền giá trị của schema khỏi kiểm thử quyền và state machine để biết lớp nào đang bảo vệ điều gì. Khi kiểm thử chặn dữ liệu, xác nhận cả dữ liệu cuối cùng và kết quả transaction, không chỉ nội dung exception.

Các ví dụ hợp lệ cũng cần được kiểm tra. Một constraint quá chặt có thể chặn trạng thái hợp lệ như giảm giá toàn phần được phê duyệt hoặc khoảng hiệu lực không có ngày kết thúc nếu nghiệp vụ cho phép. Khi đó cần sửa mô hình theo chính sách, không tìm cách cho một đường ghi đặc biệt lách constraint.

## 15. Các câu hỏi cần chốt khi thiết kế

- Điều kiện có thực sự được quyết định từ một bản ghi hay phụ thuộc dữ liệu/lịch sử bên ngoài?
- NULL, giá trị 0, giá trị âm và các mốc bằng nhau có ý nghĩa gì trong nghiệp vụ?
- Trường bắt buộc đã có `NOT NULL` thay vì chỉ có phép so sánh chưa?
- Kiểu số, độ chính xác, đơn vị và cách làm tròn có nhất quán từ Java đến database không?
- Constraint chỉ kiểm tra hình dạng phê duyệt hay còn cần quyền và ràng buộc nội dung riêng?
- Chuyển trạng thái có kiểm tra trạng thái nguồn, revision và chủ thể ở máy chủ không?
- Ghi đồng thời, import và các đường batch có cùng giữ invariant không?
- Ràng buộc đang được thực thi và dữ liệu cũ đã được xác minh đến đâu?
- Lỗi được ánh xạ rõ ràng mà không lộ SQL hoặc dữ liệu nhạy cảm không?
- Có đường đặc quyền nào được phép tắt hoặc bỏ qua constraint mà ứng dụng chưa tính đến không?

Một `CHECK` hiệu quả diễn đạt một invariant cụ thể bằng điều kiện rõ ràng, kết hợp với kiểu dữ liệu và quy tắc NULL đúng. Khi đặt nó cùng quyền theo đối tượng, state machine và transaction phù hợp, hệ thống có thêm một rào chắn bền vững trước các đường ghi thiếu validation hoặc cố tình gửi dữ liệu sai.
