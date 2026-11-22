# Chọn hàng, thứ tự lấy khóa và phạm vi khóa thực tế

Khi một transaction cần đọc hoặc cập nhật dữ liệu đang được transaction khác sử dụng, hệ quản trị có thể dùng khóa để điều phối quyền truy cập. Thiết kế khóa hiệu quả cần trả lời ba câu hỏi: transaction phải bảo vệ những hàng hoặc điều kiện dữ liệu nào, các transaction sẽ lấy khóa theo thứ tự nào, và hệ quản trị thực sự khóa những tài nguyên nào khi chạy câu lệnh.

Ba câu hỏi này liên quan chặt chẽ với nhau. Khóa thiếu có thể để lọt race condition hoặc phantom; khóa quá rộng làm những thao tác không liên quan phải chờ; thứ tự lấy khóa không thống nhất có thể tạo deadlock. Ngoài ra, câu SQL nhìn như chỉ khóa một hàng chưa chắc chỉ tạo một khóa hàng: đường truy cập qua index, khóa phạm vi, khóa bảng, khóa do constraint hoặc trigger có thể làm lock footprint lớn hơn dự kiến.

Vì vậy, hãy thiết kế khóa từ invariant nghiệp vụ và tập dữ liệu thực sự được truy cập, sau đó kiểm tra kế hoạch thực thi và khóa runtime trên đúng hệ quản trị.

## 1. Xác định điều cần bảo vệ trước khi chọn hàng

Không nên bắt đầu bằng câu hỏi “cần khóa bảng nào?”. Trước hết hãy viết điều kiện nghiệp vụ phải luôn đúng sau khi transaction commit. Ví dụ:

- Số dư tài khoản không được âm.
- Một ghế chỉ có tối đa một lượt đặt còn hiệu lực.
- Một lớp học không có số đăng ký vượt sức chứa.
- Hai thao tác cập nhật cùng một đơn hàng không được ghi đè trạng thái của nhau.
- Một ca trực luôn có ít nhất một nhân viên đang làm việc.

Tiếp theo, xác định dữ liệu nào quyết định điều kiện đó. Một invariant có thể phụ thuộc vào:

1. **Một hàng:** ví dụ số dư của một tài khoản.
2. **Một nhóm hàng đã biết:** ví dụ hai tài khoản trong một lệnh chuyển tiền.
3. **Một tập hàng thỏa predicate:** ví dụ mọi lượt đặt ghế của một chuyến bay hoặc mọi đăng ký của một lớp.
4. **Một quan hệ tổng hợp:** ví dụ tổng số đăng ký, tổng hạn mức hoặc số nhân viên đang trực.

Khóa đúng phạm vi nghĩa là bảo vệ tất cả dữ liệu có thể làm thay đổi kết quả quyết định, bao gồm cả hàng chưa tồn tại nhưng có thể được chèn vào một tập kết quả. Khóa những hàng đang nhìn thấy là chưa đủ nếu nghiệp vụ còn phụ thuộc vào một điều kiện truy vấn có thể nhận thêm hàng.

## 2. Các đối tượng có thể được khóa

Tùy hệ quản trị và cơ chế khóa, khóa có thể áp dụng ở nhiều mức:

| Phạm vi | Ý nghĩa | Tác động thường gặp |
|---|---|---|
| Hàng hoặc bản ghi | Bảo vệ một bản ghi cụ thể. | Cho phép các transaction thao tác trên hàng khác nhau chạy đồng thời. |
| Khóa/index record | Bảo vệ mục khóa trong một index. | Có thể khóa mục index và hàng dữ liệu tương ứng; chi tiết phụ thuộc engine. |
| Khoảng khóa (range/gap) | Bảo vệ một khoảng giá trị hoặc predicate. | Có thể ngăn chèn hàng mới thỏa điều kiện trong phạm vi được bảo vệ. |
| Trang (page) | Bảo vệ một trang chứa nhiều hàng hoặc mục index. | Một hàng bị khóa có thể khiến thao tác trên hàng khác cùng trang phải chờ. |
| Bảng (table) | Bảo vệ toàn bộ bảng hoặc một chế độ truy cập trên bảng. | Đơn giản nhưng giảm khả năng đồng thời trên bảng lớn. |
| Predicate logic | Bảo vệ điều kiện đọc, kể cả những hàng chưa tồn tại. | Có thể dùng trong các cơ chế Serializable; không nhất thiết là khóa vật lý chặn ghi ngay lập tức. |

Tên gọi và cách triển khai không giống nhau giữa các sản phẩm. “Row lock” cũng không phải lúc nào là một khóa vật lý độc lập gắn trực tiếp vào tuple; có engine khóa mục index đại diện cho hàng, có engine quản lý khóa hàng và khóa bảng ở các lớp khác nhau.

Điều quan trọng là hiểu **đơn vị xung đột thực tế**: một transaction khác phải chờ khi truy cập chính xác tài nguyên nào? Không thể suy ra câu trả lời chỉ từ tên hàm ORM hoặc cú pháp `FOR UPDATE`.

## 3. Chọn hàng cần khóa

### 3.1. Khóa trực tiếp hàng đại diện cho invariant

Nếu invariant gắn với một hàng, khóa hàng đó trước khi đọc và quyết định cập nhật thường là cách dễ hiểu. Ví dụ, một tài khoản có hàng `account` chứa số dư:

```sql
BEGIN;

-- Cú pháp minh họa; cú pháp khóa hàng khác nhau theo hệ quản trị.
SELECT account_id, balance
FROM account
WHERE account_id = :account_id
FOR UPDATE;

-- Kiểm tra số dư rồi cập nhật trong cùng transaction.
UPDATE account
SET balance = balance - :amount
WHERE account_id = :account_id;

COMMIT;
```

Khóa phải được lấy trước khi đọc số dư dùng để quyết định. Nếu ứng dụng đọc trước, sau đó mới lấy khóa, giá trị vừa đọc có thể đã cũ. Sau khi lấy khóa, cần đọc lại hoặc xác nhận rằng lần đọc được bảo vệ bởi đúng ngữ nghĩa của hệ quản trị.

Nếu chỉ cần bảo vệ điều kiện `balance >= amount`, một câu cập nhật nguyên tử có điều kiện có thể đơn giản hơn việc tách đọc và ghi:

```sql
UPDATE account
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng. Cách này bảo vệ điều kiện trên chính hàng được cập nhật; nó không tự giải quyết invariant tổng hợp phụ thuộc nhiều tài khoản hoặc nhiều bảng.

### 3.2. Khóa tất cả hàng liên quan đến một thao tác

Chuyển tiền giữa hai tài khoản cần bảo vệ cả tài khoản nguồn và đích. Nếu chỉ khóa tài khoản nguồn, một transaction khác có thể cập nhật tài khoản đích theo cách làm thay đổi quyết định hoặc gây ra kết quả không mong muốn.

Hãy liệt kê toàn bộ hàng mà transaction có thể đọc hoặc ghi, gồm cả các hàng liên quan đến quy tắc nghiệp vụ. Nếu một thao tác có nhiều nhánh, tập khóa phải bao phủ các nhánh có thể chạy hoặc được xác định lại an toàn trước khi cập nhật.

### 3.3. Khóa một hàng điều phối

Với invariant phụ thuộc vào nhiều hàng, có thể tạo một hàng đại diện cho tài nguyên chung, chẳng hạn `class_capacity` cho một lớp học hoặc `inventory_control` cho một kho. Mọi transaction thay đổi invariant phải khóa hàng điều phối trước khi đọc và ghi dữ liệu chi tiết.

Cách này làm đơn giản hóa quy tắc phối hợp vì các transaction cùng tác động lên một invariant tranh chấp một khóa chung. Tuy nhiên, hàng điều phối trở thành điểm tuần tự hóa: các thao tác cùng tài nguyên phải chờ nhau. Mọi đường ghi liên quan đều phải tuân thủ giao thức; một luồng bỏ qua hàng điều phối sẽ phá vỡ bảo đảm.

## 4. Dùng thứ tự lấy khóa nhất quán để giảm deadlock

Deadlock thường xuất hiện khi các transaction lấy những khóa giống nhau theo thứ tự khác nhau. Ví dụ:

```text
T1: lấy X(A) ---- chờ X(B)
T2: lấy X(B) ---- chờ X(A)
```

T1 giữ A và chờ B; T2 giữ B và chờ A. Mỗi transaction cần khóa mà transaction kia đang giữ, tạo thành vòng chờ.

Một quy tắc phổ biến là sắp xếp tài nguyên theo một thứ tự toàn cục rồi mọi transaction đều lấy khóa theo thứ tự đó. Ví dụ, luôn khóa tài khoản có `account_id` nhỏ hơn trước:

```text
transfer(A, B):
    ids = sort([A.account_id, B.account_id])

    BEGIN
    lock account[ids[0]]
    lock account[ids[1]]

    validate balances
    update both accounts
    COMMIT
```

Nếu T1 chuyển A sang B và T2 chuyển B sang A, cả hai vẫn cố lấy tài khoản có ID nhỏ hơn trước. Một transaction có thể phải chờ khóa đầu tiên, nhưng không thể giữ khóa lớn hơn rồi chờ khóa nhỏ hơn theo quy tắc ngược lại. Điều đó loại bỏ vòng chờ do hai transaction này lấy khóa theo thứ tự trái ngược.

Quy tắc thứ tự phải được áp dụng nhất quán trên mọi đường code, không chỉ một service. Các luồng thanh toán, hoàn tiền, điều chỉnh số dư, tác vụ nền và xử lý quản trị nếu cùng truy cập những hàng đó đều phải tuân thủ cùng thứ tự.

## 5. Xác định thứ tự khóa cho nhiều loại tài nguyên

Với transaction liên quan đến nhiều bảng hoặc nhiều loại tài nguyên, chỉ sắp xếp ID trong từng bảng có thể chưa đủ. Cần quy định thứ tự giữa các loại tài nguyên, ví dụ:

```text
1. Tenant
2. Account (theo account_id tăng dần)
3. Order (theo order_id tăng dần)
4. Inventory item (theo product_id tăng dần)
```

Một transaction luôn lấy khóa theo thứ tự này, kể cả khi nghiệp vụ bắt đầu từ đơn hàng rồi mới tìm tài khoản. Nếu một transaction lấy Order trước Account trong khi transaction khác lấy Account trước Order, vẫn có thể hình thành deadlock.

Thứ tự toàn cục phải tính cả khóa được lấy gián tiếp bởi:

- Trigger chạy khi insert, update hoặc delete.
- Kiểm tra foreign key và unique constraint.
- Cascade update/delete.
- ORM flush các thay đổi theo thứ tự riêng.
- Stored procedure hoặc hàm được gọi bên trong transaction.
- Index và khóa bảng mà hệ quản trị tự lấy.

Nếu không kiểm soát được toàn bộ thứ tự khóa ngầm, quy tắc ở tầng ứng dụng chỉ giảm một số deadlock chứ không bảo đảm loại bỏ mọi deadlock. Hệ thống vẫn cần xử lý lỗi deadlock do engine phát hiện.

## 6. `ORDER BY` có bảo đảm thứ tự lấy khóa không?

Không nên mặc định rằng kết quả truy vấn được sắp xếp bằng `ORDER BY` đồng nghĩa với việc hệ quản trị lấy khóa theo đúng thứ tự đó. `ORDER BY` quy định thứ tự hàng trả về cho client; thời điểm lấy khóa có thể phụ thuộc vào kế hoạch thực thi, thứ tự truy cập index, join strategy, parallel execution và cơ chế khóa của engine.

Ví dụ:

```sql
SELECT account_id, balance
FROM account
WHERE account_id IN (:id1, :id2)
ORDER BY account_id
FOR UPDATE;
```

Câu lệnh này thể hiện thứ tự kết quả, nhưng không nên coi nó là bảo đảm portable rằng mọi hệ quản trị sẽ khóa các hàng theo `account_id` tăng dần. Hãy kiểm tra tài liệu sản phẩm và kiểm thử trên đúng phiên bản, kế hoạch thực thi và cấu hình.

Khi cần quy tắc thứ tự rõ ràng, có thể dùng một quy trình lấy khóa tuần tự theo thứ tự ID đã chuẩn hóa, nếu cách làm đó phù hợp về hiệu năng và ngữ nghĩa. Cần nhớ rằng việc chọn danh sách ID trước rồi khóa từng hàng có khoảng thời gian giữa bước khám phá và bước khóa; dữ liệu có thể thay đổi trong khoảng đó. Sau khi khóa, phải xác nhận lại các điều kiện nghiệp vụ. Nếu tập kết quả có thể có hàng mới xuất hiện, cần bảo vệ predicate/range hoặc dùng một cơ chế Serializable phù hợp.

## 7. Predicate và phạm vi khóa: bảo vệ cả hàng chưa tồn tại

Giả sử hệ thống cần khóa mọi đơn hàng đang ở trạng thái `PENDING` của một khách hàng:

```sql
SELECT order_id, status
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PENDING';
```

Nếu transaction chỉ khóa những hàng hiện có, transaction khác có thể chèn thêm một đơn hàng `PENDING` sau lần đọc. Khi đó, tập hàng thỏa predicate đã thay đổi dù không hàng cũ nào bị sửa.

Đây là vấn đề phantom. Để bảo vệ quy tắc phụ thuộc vào tập kết quả, hệ quản trị cần một cơ chế ngăn thay đổi predicate trong phạm vi liên quan, ví dụ:

- Khóa phạm vi index (range/next-key lock) trên một khoảng khóa.
- Predicate lock hoặc cơ chế theo dõi phụ thuộc trong Serializable.
- Khóa một hàng điều phối chung trước khi truy vấn và thay đổi dữ liệu.
- Biểu diễn quy tắc bằng một hàng tổng hợp được cập nhật nguyên tử.

Không phải hệ quản trị nào cũng dùng cùng cơ chế. Một số engine khóa khoảng index ở isolation level hoặc câu lệnh nhất định; engine khác có thể dùng Serializable Snapshot Isolation để theo dõi xung đột logic mà không chặn mọi thao tác chèn ngay từ đầu. Phải xác định rõ isolation level và cú pháp đang dùng có bảo vệ predicate hay chỉ khóa những hàng đã tìm thấy.

## 8. Index ảnh hưởng đến lock footprint như thế nào?

Index không chỉ ảnh hưởng tốc độ truy vấn. Nó còn ảnh hưởng đường truy cập và các tài nguyên có thể bị khóa.

Giả sử truy vấn:

```sql
SELECT order_id
FROM orders
WHERE customer_id = :customer_id
  AND status = 'PENDING'
FOR UPDATE;
```

Nếu có index phù hợp trên `(customer_id, status)`, hệ quản trị có thể tìm một vùng index hẹp hơn. Tùy engine, khóa có thể được đặt trên các index record, khoảng index và/hoặc hàng tương ứng. Nếu không có index phù hợp, engine có thể phải quét nhiều hàng hơn, dẫn đến nhiều khóa hơn hoặc phạm vi khóa rộng hơn.

Một số điểm cần xem xét:

- **Index phù hợp với predicate:** giúp giảm số mục cần đọc và có thể thu hẹp phạm vi khóa.
- **Index không chọn lọc:** truy vấn có thể chạm nhiều index entry và nhiều hàng hơn dự kiến.
- **Index phụ:** cập nhật một hàng có thể phải thay đổi nhiều index; engine có thể khóa các mục liên quan trong các index đó.
- **Index duy nhất:** kiểm tra tính duy nhất có thể cần khóa hoặc chờ trên giá trị khóa đang được chèn/cập nhật.
- **Không có index:** full scan có thể làm tăng I/O, thời gian transaction và phạm vi xung đột; một số engine có thể chọn khóa rộng hơn.

Không nên kết luận rằng thêm index luôn làm giảm số khóa. Index mới có thể tạo thêm cấu trúc cần cập nhật hoặc thay đổi kế hoạch thực thi. Cần xem kế hoạch truy vấn và khóa runtime sau khi thêm index.

## 9. Join và truy vấn nhiều bảng

Một truy vấn join có thể truy cập nhiều bảng theo thứ tự do optimizer lựa chọn. Khi dùng locking read, các hàng được khóa có thể phụ thuộc vào bảng nào được truy cập trước, join algorithm và cách engine triển khai khóa cho từng bảng.

Ví dụ:

```sql
SELECT o.order_id, i.available_quantity
FROM orders o
JOIN inventory i ON i.product_id = o.product_id
WHERE o.order_id = :order_id
FOR UPDATE;
```

Không nên mặc định rằng câu lệnh khóa mọi hàng của cả hai bảng theo một thứ tự nhất định trên mọi hệ quản trị. Cú pháp khóa có thể cho phép chỉ định bảng cần khóa; một số sản phẩm có quy tắc riêng về view, join, outer join và locking clause.

Khi thiết kế transaction nhiều bảng:

1. Xác định bảng và hàng nào thực sự cần bảo vệ để giữ invariant.
2. Xác định thứ tự toàn cục giữa các bảng và giữa các hàng trong mỗi bảng.
3. Kiểm tra engine khóa hàng nào trong join và có khóa các hàng chỉ đọc hay không.
4. Kiểm tra trigger, foreign key và cascade có mở rộng lock footprint hay không.
5. Dùng nhiều transaction cạnh tranh để xác nhận thứ tự và thời gian chờ thực tế.

Nếu optimizer thay đổi kế hoạch sau khi thống kê hoặc index thay đổi, thứ tự truy cập và lock footprint cũng có thể đổi. Đừng để tính đúng đắn của giao thức chỉ phụ thuộc vào một kế hoạch tình cờ nếu hệ thống không bảo đảm kế hoạch đó ổn định.

## 10. Lock escalation và khóa rộng ngoài dự kiến

Một số hệ quản trị có thể chuyển nhiều khóa nhỏ thành một khóa rộng hơn để giảm chi phí quản lý khóa. Hiện tượng này thường được gọi là lock escalation. Ví dụ, nhiều khóa hàng hoặc khóa trang có thể được thay bằng khóa bảng, tùy engine và điều kiện kích hoạt.

Khi escalation xảy ra, transaction khác có thể bị chặn dù chỉ cần một hàng không liên quan. Điều này làm lock footprint thực tế lớn hơn phạm vi logic của câu lệnh.

Các yếu tố có thể ảnh hưởng đến việc escalation hoặc khóa rộng gồm:

- Số lượng khóa mà transaction đang giữ.
- Áp lực bộ nhớ hoặc cấu hình quản lý khóa.
- Kiểu câu lệnh và kế hoạch thực thi.
- Cơ chế khóa của từng engine.

Không phải mọi hệ quản trị đều có lock escalation theo cùng cách. Một số engine chủ yếu dùng khóa hàng/index record và khóa bảng ở chế độ phối hợp; engine khác có cơ chế escalation cụ thể. Hãy đọc tài liệu đúng sản phẩm, quan sát wait event và lock metadata khi tải thực tế.

## 11. Ví dụ: chuyển tiền và thứ tự khóa thống nhất

Giả sử hai request đồng thời:

- T1 chuyển 100 từ tài khoản 10 sang 20.
- T2 chuyển 50 từ tài khoản 20 sang 10.

Nếu mỗi request khóa tài khoản nguồn trước rồi tài khoản đích, T1 có thể khóa 10 và T2 khóa 20. Sau đó mỗi transaction chờ hàng còn lại, tạo deadlock.

Thiết kế thứ tự chuẩn theo `account_id`:

```text
transfer(sourceId, targetId, amount):
    lockIds = unique([sourceId, targetId])
    lockIds.sortAscending()

    BEGIN
    for id in lockIds:
        acquire exclusive lock for account[id]

    source = read account[sourceId]
    target = read account[targetId]

    if source.balance < amount:
        ROLLBACK
        return INSUFFICIENT_FUNDS

    source.balance -= amount
    target.balance += amount
    write both rows
    COMMIT
```

Hai request đều khóa 10 rồi 20. Một request có thể chờ ngay ở tài khoản 10 mà chưa giữ tài khoản 20, nên vòng chờ do thứ tự đảo ngược không hình thành.

Trong code thật, `acquire exclusive lock` phải được thay bằng API hoặc câu lệnh phù hợp với hệ quản trị. Nếu dùng hai câu lệnh khóa riêng, cần bảo đảm mỗi lần lấy khóa thực sự diễn ra theo thứ tự đã sắp xếp. Sau khi lấy khóa, phải đọc giá trị mới nhất theo ngữ nghĩa của engine; không dùng một snapshot cũ được tạo trước khi chờ khóa nếu nó không phù hợp với quyết định ghi.

## 12. Khác biệt giữa một số hệ quản trị

Các hệ quản trị quan hệ thường cung cấp cùng khái niệm khóa đọc/ghi nhưng cách khóa vật lý và phạm vi bảo vệ khác nhau:

| Hệ quản trị | Một số đặc điểm cần kiểm tra |
|---|---|
| PostgreSQL | Row-level locking như `FOR UPDATE` khóa các hàng được chọn; vẫn có table-level lock ở mức phối hợp. Predicate lock trong Serializable Snapshot Isolation dùng để phát hiện phụ thuộc và có thể không chặn như khóa hàng thông thường. PostgreSQL không dùng gap lock tổng quát giống InnoDB cho mọi locking read. |
| MySQL InnoDB | Locking read và update thường khóa index record mà đường truy cập sử dụng; ở một số isolation level và truy vấn phạm vi có thể dùng gap/next-key lock để ngăn phantom. Index và điều kiện truy vấn ảnh hưởng đáng kể đến phạm vi khóa. |
| SQL Server | Lock có thể ở mức key, row, page hoặc table; engine có thể escalation. Kế hoạch thực thi, index, isolation level và lock hints ảnh hưởng tài nguyên bị khóa. `ORDER BY` không nên được coi là cam kết độc lập về thứ tự lấy khóa vật lý. |
| Oracle Database | DML thường khóa hàng bị thay đổi và dùng khóa bảng ở chế độ phối hợp; `SELECT ... FOR UPDATE` khóa các hàng được chọn theo ngữ nghĩa của Oracle. Cần kiểm tra các giới hạn của locking clause và các trường hợp truy vấn phức tạp. |

Bảng chỉ nêu điểm cần chú ý, không thay thế tài liệu của phiên bản đang triển khai. Ngay trong cùng một sản phẩm, thay đổi isolation level, index, execution plan hoặc câu lệnh cũng có thể làm thay đổi lock footprint.

## 13. Cách quan sát lock footprint thực tế

Để biết một câu lệnh thực sự khóa gì, hãy kết hợp nhiều nguồn:

1. **Execution plan:** xác định index scan/seek, table scan, join order và số hàng ước tính/thực tế. Kế hoạch giúp giải thích đường truy cập, nhưng không phải danh sách đầy đủ mọi khóa runtime.
2. **Lock metadata hoặc lock view:** quan sát loại khóa, resource, mode, owner và trạng thái chờ của transaction. Tên view và cột khác nhau theo hệ quản trị.
3. **Wait events và deadlock graph:** xác định transaction đang chờ tài nguyên nào, ai giữ khóa, và chu trình chờ hình thành từ đâu.
4. **Thử nghiệm nhiều connection:** chạy các transaction có tập dữ liệu giao nhau và không giao nhau để xác nhận phạm vi chặn.
5. **So sánh trước/sau index hoặc thay đổi truy vấn:** đo số khóa, thời gian chờ, deadlock, thông lượng và độ trễ.

Khi kiểm tra, hãy ghi nhận isolation level thực tế của connection và thời điểm bắt đầu transaction. Một truy vấn thử độc lập ngoài transaction hoặc chạy với cấu hình khác có thể cho kết quả không phản ánh workload thật.

## 14. Các nguyên tắc giảm phạm vi khóa và thời gian giữ khóa

- Tạo index phù hợp với điều kiện lọc và thứ tự truy cập thường dùng; xác nhận bằng execution plan.
- Chỉ khóa các hàng cần thiết để bảo vệ invariant, nhưng bao gồm predicate/range nếu hàng mới có thể làm thay đổi quyết định.
- Lấy khóa theo một thứ tự toàn cục nhất quán giữa mọi luồng xử lý.
- Giữ transaction ngắn; không chờ người dùng hoặc gọi dịch vụ mạng trong khi đang giữ khóa.
- Tránh cập nhật hàng hoặc index không cần thiết vì mỗi thay đổi có thể tạo thêm xung đột.
- Chia batch lớn thành đơn vị hợp lý nếu có thể giữ nguyên tính đúng đắn nghiệp vụ.
- Theo dõi lock escalation, lock wait, deadlock và thay đổi kế hoạch truy vấn sau khi deploy.
- Xử lý deadlock và serialization failure bằng retry toàn bộ transaction khi nghiệp vụ cho phép.

Retry cần có giới hạn, backoff và tính idempotent phù hợp. Nếu transaction gửi email, phát sự kiện hoặc gọi dịch vụ thanh toán, hãy tránh thực hiện tác dụng phụ không thể lặp an toàn trước khi commit. Có thể ghi sự kiện trong cùng transaction và gửi sau commit qua transactional outbox.

## 15. Quy trình thiết kế khóa cho một thao tác

Khi thiết kế một transaction có nhiều hàng hoặc nhiều bảng, hãy đi theo các bước sau:

1. Viết invariant cần bảo vệ và xác định dữ liệu làm thay đổi kết quả của invariant.
2. Liệt kê các hàng đã biết, các hàng có thể phát sinh và predicate/range liên quan.
3. Chọn đối tượng khóa phù hợp: hàng, index range, bảng hoặc hàng điều phối.
4. Xác định chế độ S/X và thời điểm lấy khóa; lấy khóa trước khi thực hiện các lần đọc quyết định.
5. Định nghĩa thứ tự toàn cục giữa loại tài nguyên và ID của từng tài nguyên.
6. Kiểm tra khóa ngầm từ index, constraint, foreign key, trigger, cascade và ORM flush.
7. Chạy execution plan và quan sát khóa runtime trên đúng hệ quản trị.
8. Kiểm thử hai hoặc nhiều transaction có tập khóa giao nhau, bao gồm thứ tự tài nguyên đảo ngược và hàng mới thỏa predicate.
9. Đo thời gian chờ, deadlock, số khóa, phạm vi khóa và thông lượng dưới tải đại diện.
10. Thiết kế retry, timeout và phản hồi nghiệp vụ khi không thể lấy khóa hoặc transaction bị hủy.

## 16. Checklist trước khi đưa cơ chế khóa vào production

- [ ] Đã viết rõ invariant nghiệp vụ cần bảo vệ.
- [ ] Đã xác định đầy đủ hàng và predicate ảnh hưởng đến quyết định.
- [ ] Đã chọn phạm vi khóa đủ bảo vệ cả hàng mới có thể xuất hiện.
- [ ] Đã xác nhận câu lệnh khóa bảo vệ đúng hàng và đúng bảng trên hệ quản trị đang dùng.
- [ ] Đã định nghĩa thứ tự lấy khóa nhất quán giữa mọi luồng xử lý.
- [ ] Đã xem xét khóa ngầm từ index, join, foreign key, constraint, trigger và cascade.
- [ ] Đã kiểm tra khả năng khóa rộng hoặc lock escalation.
- [ ] Đã kiểm tra execution plan và lock metadata trong workload đại diện.
- [ ] Đã kiểm thử deadlock, lock wait, phantom và các trường hợp rollback.
- [ ] Đã có timeout, retry toàn transaction và xử lý tác dụng phụ an toàn.

Chọn hàng và thứ tự lấy khóa là một phần của thiết kế tính đúng đắn, còn lock footprint là kết quả của cách hệ quản trị thực thi câu lệnh trên index, predicate và các quan hệ dữ liệu thực tế. Một thiết kế tốt phải bảo vệ đúng invariant, giữ thứ tự khóa thống nhất và được xác nhận bằng kế hoạch thực thi cùng quan sát khóa runtime. Khi đó, hệ thống vừa giảm được deadlock và phạm vi chặn không cần thiết, vừa giữ được hành vi nghiệp vụ đúng dưới tải đồng thời.
