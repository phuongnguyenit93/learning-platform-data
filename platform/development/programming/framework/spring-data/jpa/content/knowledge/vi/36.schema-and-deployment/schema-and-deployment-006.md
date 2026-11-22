# Thay đổi cột, chỉ mục và ràng buộc mà vẫn tương thích triển khai

Thay đổi schema của database trong một ứng dụng đang chạy cần phối hợp giữa migration và vòng đời của phiên bản ứng dụng. Một lệnh ALTER TABLE có thể đúng về mặt SQL nhưng vẫn làm hỏng hệ thống nếu instance cũ còn chạy, worker đang xử lý message hoặc một job chưa được triển khai lại vẫn truy cập cột cũ.

Nguyên tắc quan trọng là **expand and contract** (mở rộng rồi thu hẹp):

1. Mở rộng schema theo cách vẫn tương thích với ứng dụng hiện tại.
2. Triển khai phiên bản ứng dụng mới có thể làm việc với schema cũ và mới trong giai đoạn chuyển tiếp.
3. Chuyển đổi và backfill dữ liệu theo từng đợt.
4. Chuyển toàn bộ luồng đọc/ghi sang cấu trúc mới.
5. Chỉ loại bỏ cột, index hoặc constraint cũ sau khi chắc chắn không còn phiên bản ứng dụng nào phụ thuộc vào chúng.

Bài này giải thích cách thay đổi cột, đổi tên hoặc kiểu dữ liệu, thêm index và constraint, backfill dữ liệu, triển khai rolling deployment, xử lý khóa bảng và kiểm thử migration bằng Flyway/Liquibase cùng database gần production.

**Điều kiện của ví dụ:** Java 17 trở lên, Spring Boot 3.x, Spring Data JPA và Hibernate. Các câu SQL DDL bên dưới là ví dụ; cú pháp, khả năng online, locking, transactional DDL và cách tạo index phụ thuộc database/version. Hãy điều chỉnh theo engine production. Đây là hướng dẫn cho ứng dụng đang hoạt động, không phải một script migration dùng nguyên trạng cho mọi database.

## 1. Vì sao thay đổi schema cần tương thích nhiều phiên bản?

Trong rolling deployment, các instance không được thay thế cùng một thời điểm. Trong một khoảng thời gian, hệ thống có thể đồng thời chạy:

- Instance phiên bản cũ.
- Instance phiên bản mới.
- Worker nền chưa được restart.
- Scheduled job hoặc consumer đang chạy.
- Các tác vụ quản trị và batch được triển khai độc lập.

Nếu phiên bản mới yêu cầu cột display_name nhưng database chưa có cột đó, instance mới lỗi. Nếu migration xóa name trong khi instance cũ vẫn đọc name, instance cũ lỗi.

Có thể biểu diễn giai đoạn chuyển tiếp:

~~~text
Database schema S0
       |
       | Expand: thêm cột/index/constraint tương thích
       v
Database schema S1
       |
       | Rolling deploy: app cũ và app mới cùng chạy
       v
App mới đọc/ghi cấu trúc mới, dữ liệu được backfill
       |
       | Chờ toàn bộ app cũ và job cũ kết thúc
       v
Contract: xóa cấu trúc cũ không còn được dùng
       |
       v
Database schema S2
~~~

Một migration an toàn phải xem xét cả hai chiều tương thích:

- **App cũ với schema mới:** app cũ có tiếp tục hoạt động sau bước expand không?
- **App mới với schema trong giai đoạn chuyển tiếp:** app mới có xử lý được dữ liệu chưa backfill hoặc cột mới còn null không?

Không chỉ kiểm tra schema sau migration cuối cùng. Cần kiểm tra từng trạng thái trung gian mà ứng dụng sẽ thực sự chạy qua.

## 2. Quy trình expand-and-contract

Một thay đổi lớn thường được chia thành các pha sau:

| Pha | Database | Ứng dụng | Mục tiêu |
|---|---|---|---|
| 1. Expand | Thêm cấu trúc mới, chưa xóa cấu trúc cũ | Phiên bản cũ vẫn chạy | Tạo schema tương thích |
| 2. Compatibility deploy | Giữ cả cấu trúc cũ và mới | Phiên bản mới hỗ trợ cả hai | Rolling deploy không gián đoạn |
| 3. Backfill | Chuyển dữ liệu cũ sang cấu trúc mới | Có thể dual-write hoặc đọc fallback | Đưa dữ liệu về trạng thái thống nhất |
| 4. Switch | Schema mới đã có dữ liệu cần thiết | Đọc/ghi chính vào cấu trúc mới | Chuyển use case sang schema mới |
| 5. Verify | Kiểm tra dữ liệu, metrics và dependency | Không còn code dùng cấu trúc cũ | Xác nhận đủ điều kiện contract |
| 6. Contract | Xóa cột/index/constraint cũ | Phiên bản mới không còn phụ thuộc | Hoàn tất thay đổi |

Các pha có thể kéo dài qua nhiều lần release. Không nhất thiết phải thực hiện expand, deploy, backfill và contract trong cùng một lần triển khai.

**Không contract ngay sau khi deploy code mới.** Hãy xác nhận tất cả instance, consumer, cron job, báo cáo, script quản trị và tích hợp bên ngoài đã ngừng dùng schema cũ.

## 3. Thêm một cột mới mà không làm hỏng ứng dụng cũ

Giả sử bảng customers đang có cột name. Yêu cầu mới muốn tách thành first_name và last_name.

Không nên xóa name và thêm hai cột NOT NULL trong cùng một migration khi app cũ vẫn đang chạy. App cũ có thể tiếp tục INSERT/UPDATE name, còn app mới cần hai cột mới.

### Bước 1: Expand bằng các cột nullable

Ví dụ SQL:

~~~sql
ALTER TABLE customers
    ADD COLUMN first_name VARCHAR(120) NULL;

ALTER TABLE customers
    ADD COLUMN last_name VARCHAR(120) NULL;
~~~

Hai cột mới cho phép app cũ tiếp tục ghi name mà không phải cung cấp dữ liệu cho các cột mới.

Việc thêm cột có thể vẫn cần metadata lock hoặc lock ngắn trên một số database. Với bảng lớn, cần kiểm tra engine, version và khả năng thêm cột online trước khi chạy.

### Bước 2: Triển khai code tương thích

Phiên bản trung gian có thể:

- Khi tạo/cập nhật customer, ghi name và hai cột mới theo quy tắc chuyển đổi đã thống nhất.
- Khi đọc, ưu tiên dữ liệu mới nếu đã có, nếu chưa thì dùng dữ liệu cũ.
- Không giả định mọi hàng đã được backfill ngay khi release bắt đầu.

Ví dụ service ở mức ý tưởng:

~~~java
@Transactional
public void renameCustomer(
        Long id,
        String firstName,
        String lastName) {

    Customer customer = repository.findById(id).orElseThrow();

    customer.setFirstName(firstName);
    customer.setLastName(lastName);
    customer.setName(firstName + " " + lastName);
}
~~~

Đoạn code chỉ minh họa dual-write. Quy tắc ghép tên cần phù hợp domain; không phải mọi tên người đều có thể tách/ghép chính xác bằng một dấu cách. Nếu hai cột mới được tạo ra từ dữ liệu cũ không thể phân tích chắc chắn, cần quy trình xác nhận hoặc mapping nghiệp vụ riêng.

### Bước 3: Backfill dữ liệu cũ

Chạy job cập nhật những hàng chưa có dữ liệu mới. Backfill cần idempotent: chạy lại không làm hỏng dữ liệu đã được chuyển đổi.

Ví dụ SQL minh họa cho dữ liệu có quy tắc tách đơn giản:

~~~sql
UPDATE customers
SET first_name = ...,
    last_name = ...
WHERE first_name IS NULL
   OR last_name IS NULL;
~~~

Dấu ba chấm là biểu thức chuyển đổi phụ thuộc dữ liệu và database, không phải SQL có thể thực thi nguyên văn. Với dữ liệu lớn, không nên mặc định chạy một UPDATE toàn bảng trong một transaction dài. Hãy chia theo ID hoặc khóa phân trang ổn định, giới hạn số hàng mỗi batch và theo dõi lock/log/replication lag.

### Bước 4: Chuyển sang đọc và ghi cột mới

Sau khi backfill hoàn tất và đã kiểm tra dữ liệu:

- Chuyển code đọc sang first_name/last_name.
- Dừng dual-write vào name sau khi mọi consumer cũ đã ngừng.
- Theo dõi lỗi đọc, dữ liệu null và số lượng truy cập cột cũ.

### Bước 5: Contract

Ở một release sau, khi xác nhận không còn dependency:

~~~sql
ALTER TABLE customers DROP COLUMN name;
~~~

Đây là bước phá vỡ tương thích. Chỉ chạy khi app cũ, job cũ, view, trigger, report và tích hợp không còn sử dụng cột đó. Có thể cần một release chỉ để ngừng ghi cột cũ, rồi một release khác mới xóa.

## 4. Đổi tên cột an toàn

Một lệnh rename trực tiếp:

~~~sql
ALTER TABLE customers RENAME COLUMN name TO display_name;
~~~

có thể khiến phiên bản ứng dụng cũ không còn hoạt động vì SQL do Hibernate tạo vẫn tham chiếu name.

Quy trình an toàn hơn:

1. Thêm display_name nullable.
2. Triển khai code tương thích ghi cả name và display_name.
3. Backfill display_name từ name.
4. Kiểm tra null, sai khác và số lượng hàng.
5. Chuyển code đọc sang display_name.
6. Dừng ghi name sau khi không còn app cũ.
7. Xóa name trong migration contract riêng.

Nếu cần dual-write trong một thời gian, phải xác định một nguồn dữ liệu có thẩm quyền. Khi hai cột có thể bị cập nhật khác nhau, ứng dụng cần quy tắc giải quyết xung đột rõ ràng; chỉ ghi cả hai mà không có quy tắc có thể tạo dữ liệu lệch nhau.

Với một rename thuần túy trên database nhỏ và deployment có downtime được kiểm soát, rename trực tiếp có thể phù hợp. Nhưng trong rolling deployment hoặc hệ thống có nhiều consumer, add-copy-switch-drop thường an toàn hơn.

## 5. Thay đổi kiểu dữ liệu bằng shadow column

Đổi kiểu trực tiếp có thể khóa bảng, scan dữ liệu lớn, thất bại vì giá trị không chuyển đổi được hoặc làm code cũ không tương thích.

Ví dụ muốn đổi phone từ chuỗi tự do sang định dạng chuẩn hóa hoặc kiểu/cấu trúc mới. Có thể dùng cột trung gian:

1. Thêm phone_normalized với kiểu dữ liệu mới.
2. Deploy code ghi đồng thời field cũ và field mới.
3. Backfill giá trị cũ qua hàm chuyển đổi có kiểm tra.
4. Ghi nhận hàng không thể chuyển đổi để xử lý riêng.
5. Đọc từ cột mới sau khi xác minh.
6. Dừng ghi cột cũ.
7. Xóa cột cũ và đổi tên cột mới ở release sau nếu cần.

Không ép chuyển đổi bằng CAST nếu dữ liệu cũ có giá trị không hợp lệ. Trước migration, hãy thống kê:

- Số hàng null.
- Giá trị không parse được.
- Giá trị vượt độ dài/precision mới.
- Giá trị trùng sau chuẩn hóa.
- Giá trị cần quy tắc làm tròn hoặc timezone.

Với decimal, thay đổi precision/scale có thể làm mất dữ liệu. Với timestamp, cần xác định timezone và ý nghĩa instant/local time. Với enum, phải bảo đảm các giá trị cũ có mapping trong code mới.

## 6. Thay đổi NOT NULL theo nhiều bước

Thêm cột mới dưới dạng NOT NULL ngay có thể thất bại khi bảng đã có dữ liệu hoặc app cũ chưa gửi giá trị.

Quy trình an toàn thường là:

1. Thêm cột nullable.
2. Deploy code luôn ghi giá trị cho bản ghi mới.
3. Backfill các hàng cũ.
4. Kiểm tra không còn NULL.
5. Thêm NOT NULL constraint.
6. Chuyển mapping entity sang nullable = false nếu phù hợp.

Kiểm tra trước khi enforce:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE external_code IS NULL;
~~~

Chỉ khi kết quả bằng 0 và mọi writer đã bảo đảm cung cấp giá trị mới thì mới thêm constraint:

~~~sql
ALTER TABLE customers
    ALTER COLUMN external_code SET NOT NULL;
~~~

Cú pháp trên phù hợp với PostgreSQL và một số hệ quản trị; MySQL, SQL Server và Oracle có cú pháp riêng. Thao tác thay đổi nullability có thể cần lock hoặc scan bảng tùy engine/version.

Đặt default ở database có thể giúp writer cũ tiếp tục insert, nhưng cần hiểu khác biệt giữa:

- **Database DEFAULT:** được áp dụng khi INSERT bỏ qua cột hoặc dùng DEFAULT.
- **JPA field initializer:** chỉ áp dụng khi Java tạo object.
- **@ColumnDefault:** metadata Hibernate phục vụ DDL/schema generation, không tự bảo đảm mọi INSERT do mọi client thực hiện đều nhận default.
- **@PrePersist:** callback ứng dụng, không chạy với SQL ghi trực tiếp từ nguồn khác.

Không dùng default giả tạo nếu giá trị cần phản ánh dữ liệu nghiệp vụ thực. Default chỉ nên được chọn khi nó đúng với ý nghĩa của mọi bản ghi mới.

## 7. Thêm FOREIGN KEY mà không gây gián đoạn

Giả sử cần thêm orders.customer_id tham chiếu customers.id.

Quy trình thường dùng:

1. Thêm customer_id nullable.
2. Deploy code mới ghi customer_id cho order mới.
3. Backfill quan hệ cho order cũ.
4. Kiểm tra không còn customer_id null nếu nghiệp vụ yêu cầu bắt buộc.
5. Kiểm tra không có orphan reference.
6. Tạo index cho cột khóa ngoại nếu workload cần.
7. Thêm FOREIGN KEY.
8. Thêm NOT NULL sau khi mọi hàng đã hợp lệ và mọi writer tương thích.

Kiểm tra orphan:

~~~sql
SELECT o.id, o.customer_id
FROM orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE o.customer_id IS NOT NULL
  AND c.id IS NULL;
~~~

Kết quả phải rỗng trước khi thêm FK.

Index trên cột foreign key thường hữu ích cho JOIN và thao tác xóa/cập nhật phía bảng cha, nhưng database không phải lúc nào cũng tự tạo index khi thêm FK. Kiểm tra quy tắc engine và workload trước khi tạo.

PostgreSQL có thể thêm một số constraint bằng NOT VALID, sau đó xác thực dữ liệu cũ riêng:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id) REFERENCES customers(id)
NOT VALID;

ALTER TABLE orders
VALIDATE CONSTRAINT fk_orders_customer;
~~~

Đây là cú pháp PostgreSQL-specific. Constraint mới vẫn được áp dụng cho thay đổi mới sau khi được thêm, còn việc validate dữ liệu cũ diễn ra ở bước riêng. Database khác có cơ chế và mức lock khác; không sao chép cú pháp này sang engine khác.

## 8. Thêm CHECK constraint theo giai đoạn

Ví dụ muốn quantity phải lớn hơn 0:

~~~sql
ALTER TABLE order_items
ADD CONSTRAINT ck_order_items_quantity_positive
CHECK (quantity > 0);
~~~

Trước khi thêm constraint, kiểm tra dữ liệu cũ:

~~~sql
SELECT COUNT(*)
FROM order_items
WHERE quantity <= 0;
~~~

Nếu có hàng vi phạm, cần quyết định sửa, loại bỏ hoặc xử lý theo nghiệp vụ trước khi enforce.

Với PostgreSQL, có thể dùng NOT VALID rồi VALIDATE CONSTRAINT để tách việc thêm constraint và scan dữ liệu cũ. Khả năng này không portable. Trên engine khác, hãy xem tài liệu về online constraint validation và mức khóa của DDL.

Sau khi constraint được enforce, code mới nên validate input sớm để người dùng nhận lỗi rõ ràng. Database vẫn là nơi bảo vệ cuối cùng, kể cả khi dữ liệu được ghi ngoài ứng dụng.

## 9. Thêm UNIQUE constraint và xử lý dữ liệu trùng

Giả sử muốn email duy nhất trong mỗi tenant:

~~~sql
ALTER TABLE users
ADD CONSTRAINT uk_users_tenant_email
UNIQUE (tenant_id, email);
~~~

Trước khi tạo unique constraint, tìm các tổ hợp trùng:

~~~sql
SELECT tenant_id, email, COUNT(*)
FROM users
GROUP BY tenant_id, email
HAVING COUNT(*) > 1;
~~~

Phải giải quyết dữ liệu trùng trước khi enforce. Không tự động xóa bản ghi trùng nếu chưa có quy tắc nghiệp vụ về hợp nhất dữ liệu, foreign key và lịch sử.

Với bảng lớn, tạo unique index có thể cần thời gian và lock. PostgreSQL hỗ trợ:

~~~sql
CREATE UNIQUE INDEX CONCURRENTLY
    ux_users_tenant_email
ON users(tenant_id, email);
~~~

Sau đó có thể gắn index vào constraint:

~~~sql
ALTER TABLE users
ADD CONSTRAINT uk_users_tenant_email
UNIQUE USING INDEX ux_users_tenant_email;
~~~

Đây là quy trình PostgreSQL-specific. CREATE INDEX CONCURRENTLY có giới hạn về transaction và có thể để lại index invalid nếu thất bại; cần kiểm tra trạng thái và có quy trình cleanup/retry được kiểm soát. Không đặt lệnh này trong một migration transaction thông thường nếu công cụ migration đang bọc toàn bộ script trong transaction.

Trên database khác, cú pháp và khả năng tạo unique index online khác nhau. Hãy kiểm tra đúng phiên bản engine và lựa chọn deployment window phù hợp.

## 10. Tạo index mà không khóa hoạt động ghi quá lâu

Index giúp query nhanh hơn nhưng tạo index trên bảng lớn có thể tiêu tốn CPU, IO, dung lượng và gây lock. Việc tạo index cũng cần tính đến tốc độ ghi trong lúc build.

Trước khi thêm index:

- Xác định query nào đang chậm.
- Xem WHERE, JOIN, ORDER BY và selectivity.
- Kiểm tra index hiện có.
- Đọc execution plan.
- Ước lượng dung lượng và thời gian build.
- Kiểm tra replication lag và tải ghi.
- Chọn phương thức online/concurrent nếu database hỗ trợ.

Ví dụ index cho query lọc theo status và sắp xếp theo created_at:

~~~sql
CREATE INDEX idx_orders_status_created_at
ON orders(status, created_at);
~~~

Index này chỉ là ví dụ. Thứ tự cột phù hợp phụ thuộc query pattern, cardinality, filter equality/range và database optimizer. Một index mới có thể không được dùng nếu selectivity thấp hoặc query không khớp prefix của composite index.

Các lựa chọn theo database:

- **PostgreSQL:** CREATE INDEX CONCURRENTLY giảm mức cản trở với INSERT/UPDATE/DELETE nhưng tốn thời gian hơn và không chạy trong transaction block thông thường.
- **MySQL/InnoDB:** một số ALTER TABLE/CREATE INDEX hỗ trợ ALGORITHM=INPLACE hoặc INSTANT và LOCK=NONE tùy thao tác/version. Không phải mọi thay đổi đều online.
- **SQL Server:** hỗ trợ ONLINE = ON cho một số edition/operation/index type; cần kiểm tra giới hạn cụ thể.
- **Oracle:** có tùy chọn online cho một số thao tác index/DDL; vẫn cần đánh giá tài nguyên và lock.

Không suy luận online nghĩa là không có lock hoặc không có tác động. Các thao tác online vẫn dùng tài nguyên và có thể cần lock ngắn ở đầu/cuối.

## 11. Backfill dữ liệu lớn theo batch

Backfill là quá trình chuyển dữ liệu đã tồn tại sang cấu trúc mới. Một câu UPDATE toàn bảng có thể:

- Giữ lock lâu.
- Tạo transaction log/WAL lớn.
- Tăng replication lag.
- Làm phình undo/redo log.
- Cạnh tranh tài nguyên với workload người dùng.
- Khó rollback nếu job thất bại giữa chừng.

Với bảng lớn, chia thành batch theo khóa ổn định:

~~~sql
UPDATE customers
SET normalized_email = LOWER(TRIM(email))
WHERE id > :last_id
  AND id <= :next_id
  AND normalized_email IS NULL;
~~~

Câu lệnh trên là mẫu SQL có placeholder do job điều phối cung cấp; cú pháp bind và cách chọn range phụ thuộc ứng dụng/database.

Một backfill job nên:

1. Xác định range hoặc keyset tiếp theo.
2. Cập nhật một batch nhỏ.
3. Commit batch.
4. Ghi checkpoint để có thể tiếp tục.
5. Theo dõi tốc độ, lỗi và replication lag.
6. Nghỉ hoặc giảm batch size khi hệ thống đang tải cao.
7. Chạy lại an toàn nếu worker dừng giữa chừng.

Dùng điều kiện như normalized_email IS NULL giúp job có tính idempotent khi dữ liệu đã được xử lý. Tuy nhiên, nếu app mới đồng thời cập nhật giá trị này, cần quy tắc đồng bộ rõ để backfill không ghi đè dữ liệu mới hơn.

Tránh OFFSET lớn cho backfill trên bảng thay đổi liên tục. Keyset theo ID hoặc khóa tăng dần thường ổn định hơn. Với nhiều worker, cần cơ chế phân vùng range hoặc claim batch để không xử lý trùng ngoài ý muốn.

## 12. Dual-write và đồng bộ dữ liệu trong giai đoạn chuyển tiếp

Khi có cả cột cũ và cột mới, có thể cần ghi cả hai trong thời gian chuyển đổi. Dual-write có thể diễn ra trong cùng transaction database nếu cả hai cột nằm trong cùng database.

Các nguyên tắc:

- Chọn một nguồn dữ liệu có thẩm quyền tại mỗi pha.
- Ghi cả hai theo cùng một quy tắc chuyển đổi.
- Tránh hai service khác nhau cập nhật hai cột độc lập.
- Theo dõi số hàng có giá trị lệch nhau.
- Backfill chỉ sửa hàng chưa được chuyển hoặc đã xác định rõ cần sửa.
- Dừng dual-write sau khi không còn consumer cũ.

Nếu dual-write đi qua hai database hoặc hai hệ thống độc lập, không có atomicity tự động. Khi đó cần transactional outbox, event-driven synchronization, retry và cơ chế phát hiện/reconcile dữ liệu lệch.

Không dùng một trigger database để đồng bộ hai cột mà không ghi nhận nó trong thiết kế. Trigger có thể hữu ích, nhưng làm thay đổi dữ liệu ngoài code path, gây bất ngờ cho auditing, debugging và ORM state. Nếu dùng, phải tài liệu hóa, kiểm thử và quản lý bằng migration.

## 13. Triển khai rolling deployment an toàn

Một trình tự release có thể áp dụng:

**Release A — Expand**

- Chạy migration thêm cột mới nullable, index hoặc constraint ở trạng thái chuyển tiếp.
- Kiểm tra migration hoàn tất.
- App cũ vẫn chạy được với schema mới.

**Release B — Compatibility code**

- Deploy app mới hỗ trợ schema cũ và mới.
- Nếu cần, ghi cả hai cột.
- Đọc dữ liệu mới nếu có, fallback sang dữ liệu cũ.
- Giữ code chịu được hàng chưa backfill.

**Backfill phase**

- Chạy job theo batch.
- Theo dõi số hàng còn thiếu và lỗi chuyển đổi.
- So sánh dữ liệu cũ/mới theo rule đã định.
- Có thể pause/resume mà không làm hỏng kết quả.

**Release C — Switch**

- Chuyển toàn bộ code đọc sang cột mới.
- Dừng phụ thuộc vào cột cũ.
- Chờ mọi instance/worker/consumer cũ kết thúc.
- Xác nhận không còn query, report hoặc script dùng cột cũ.

**Release D — Contract**

- Xóa cột cũ hoặc constraint/index không còn dùng.
- Loại bỏ mapping và code tương thích cũ.
- Theo dõi lỗi sau migration.

Nếu một release có thể rollback về phiên bản cũ, schema phải tiếp tục tương thích với phiên bản rollback đó. Khi contract đã xóa cột cũ, rollback app về phiên bản cũ có thể không còn an toàn; lúc này cần forward-fix hoặc một quy trình phục hồi dữ liệu đã chuẩn bị trước.

## 14. Spring Data JPA mapping trong giai đoạn chuyển đổi

Entity có thể tạm thời ánh xạ cả hai cột:

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "name")
    private String legacyName;

    @Column(name = "display_name")
    private String displayName;

    public String getEffectiveDisplayName() {
        if (displayName != null) {
            return displayName;
        }
        return legacyName;
    }

    public void rename(String newDisplayName) {
        this.displayName = newDisplayName;
        this.legacyName = newDisplayName;
    }
}
~~~

Đây là ví dụ cho trường hợp hai cột có cùng ngữ nghĩa. Nếu chuyển từ một cột name sang first_name/last_name, cần mapper theo quy tắc domain thay vì sao chép nguyên chuỗi.

Trong giai đoạn compatibility, có thể dùng:

- Entity mapping cả cột cũ và mới.
- Service method duy nhất chịu trách nhiệm dual-write.
- DTO chỉ công khai field mới.
- Metrics để đếm hàng chưa backfill hoặc số lần fallback sang cột cũ.

Sau khi contract, xóa field legacy khỏi entity trong cùng release hoặc release sau khi migration drop column đã hoàn tất. Không deploy code tham chiếu cột mới trước khi migration expand đã chạy thành công.

## 15. Quản lý migration bằng Flyway hoặc Liquibase

Không nên để Hibernate tự thay đổi schema production bằng ddl-auto=update. Schema thay đổi cần được review, version hóa, kiểm thử và triển khai theo trình tự rõ ràng.

Với Flyway, migration versioned thường được đặt tên theo dạng:

~~~text
V001__create_customers.sql
V002__add_display_name.sql
V003__backfill_display_name.sql
V004__add_customer_email_index.sql
~~~

Flyway lưu lịch sử migration để biết script nào đã chạy. Migration versioned đã chạy trên môi trường dùng chung nên được coi là bất biến; nếu cần sửa logic, tạo migration mới thay vì chỉnh sửa script cũ đã áp dụng.

Liquibase dùng changelog và changeset để quản lý thay đổi. Dù chọn công cụ nào:

- Chỉ nên có một nguồn quản lý schema chính.
- Review SQL/DDL trước khi deploy.
- Ghi nhận database/version mục tiêu.
- Kiểm thử cả migration từ schema cũ lẫn database mới hoàn toàn.
- Quản lý rollback hoặc forward-fix theo từng thay đổi.
- Không để nhiều application instance tự cạnh tranh chạy cùng migration mà không hiểu cơ chế locking của công cụ.

Trong production, có thể chạy migration ở một bước triển khai có kiểm soát trước khi rollout app. Điều này giúp quan sát thời gian, lock và lỗi migration độc lập với việc khởi động instance.

## 16. DDL transaction và khóa bảng phụ thuộc database

Không phải database nào cũng xử lý DDL trong transaction giống nhau.

- **PostgreSQL:** hỗ trợ transaction cho nhiều DDL, nhưng một số lệnh như CREATE INDEX CONCURRENTLY không được chạy trong transaction block thông thường.
- **MySQL:** nhiều DDL gây implicit commit; khả năng instant/in-place/online phụ thuộc operation, storage engine và version.
- **Oracle và SQL Server:** có quy tắc transaction/locking DDL riêng; không suy ra hành vi từ PostgreSQL hoặc MySQL.

Một migration có thể thành công trên database dev nhỏ nhưng làm production bị chặn vì bảng lớn, lock queue hoặc long-running transaction.

Trước khi chạy DDL:

1. Đọc tài liệu đúng database/version.
2. Xác định lock mode và thời gian dự kiến.
3. Kiểm tra transaction dài đang giữ lock.
4. Đặt lock timeout hoặc statement timeout phù hợp nếu engine hỗ trợ.
5. Chạy thử trên dữ liệu có kích thước gần production.
6. Chuẩn bị monitoring và điều kiện dừng.
7. Có kế hoạch retry/cleanup nếu DDL online thất bại một phần.

Không coi việc migration chạy nhanh trên local là bằng chứng nó an toàn ở production.

## 17. Giữ migration nhỏ, có thể quan sát và phục hồi

Một migration tốt có phạm vi rõ và thời gian chạy dự đoán được. Tránh gộp trong một release duy nhất:

- Thêm nhiều cột.
- Chuyển hàng triệu bản ghi.
- Tạo nhiều index lớn.
- Enforce nhiều constraint.
- Xóa cột cũ.

Tách DDL và backfill giúp có thể theo dõi từng bước, điều chỉnh batch size và tạm dừng nếu ảnh hưởng workload.

Các metrics nên theo dõi:

- Thời gian migration.
- Số hàng đã backfill và còn lại.
- Số hàng không chuyển đổi được.
- Số lần đọc fallback sang cột cũ.
- Số lỗi ghi hoặc constraint violation.
- Lock wait và deadlock.
- CPU, IO, connection pool.
- WAL/redo/transaction log và replication lag.
- Query latency của workload chính.

Khi migration bị gián đoạn, phải biết bước nào đã hoàn tất, job có thể chạy lại không và cách kiểm tra trạng thái. Đừng giả định rollback SQL sẽ phục hồi mọi dữ liệu đã chuyển đổi hoặc mọi DDL trên mọi database.

## 18. Kiểm thử migration và tương thích ứng dụng

Một migration test cần kiểm tra nhiều trạng thái schema, không chỉ chạy toàn bộ migration trên database trống.

### Kiểm thử từ schema phiên bản trước

- Khởi tạo database ở schema cũ.
- Nạp dữ liệu đại diện, gồm null, giá trị biên, dữ liệu trùng và hàng orphan nếu có.
- Chạy migration.
- Kiểm tra dữ liệu mới, constraint và index.
- Xác nhận dữ liệu không bị mất hoặc biến đổi sai.

### Kiểm thử tương thích code

- Chạy phiên bản app cũ với schema sau expand.
- Chạy phiên bản app mới với dữ liệu chưa backfill.
- Chạy app mới sau khi backfill.
- Kiểm tra dual-write không tạo sai lệch.
- Xác nhận app mới không còn phụ thuộc cột cũ trước contract.

### Dùng Testcontainers

~~~java
@Testcontainers
@SpringBootTest
class CustomerMigrationIntegrationTest {

    @Container
    static PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16");

    // Cấu hình DataSource từ container và chạy migration
    // trước khi thực hiện các assertion về schema/dữ liệu.
}
~~~

Đây là khung minh họa; ứng dụng cần cấu hình datasource động, dependency Testcontainers phù hợp và migration tool. Dùng cùng engine/version gần production để kiểm tra DDL, constraint, index và SQL behavior. H2 không thay thế hoàn toàn PostgreSQL/MySQL/Oracle/SQL Server khi migration dùng tính năng riêng của database.

## 19. Rollback, forward-fix và dữ liệu đã chuyển đổi

Rollback ứng dụng và rollback database là hai việc khác nhau.

- Rollback app có thể thực hiện bằng cách deploy lại artifact cũ nếu schema vẫn tương thích.
- Rollback DDL có thể không khả thi nếu đã xóa hoặc chuyển đổi dữ liệu.
- Backfill có thể không đảo ngược nếu phép chuyển đổi làm mất thông tin.
- Unique constraint hoặc NOT NULL có thể không được gỡ an toàn nếu code mới đã phụ thuộc vào chúng.

Với thay đổi có tính phá hủy, thường cần ưu tiên forward-fix: sửa migration/code bằng một bước mới có kiểm soát, thay vì cố chạy ngược một DDL có nguy cơ mất dữ liệu.

Trước contract hoặc chuyển đổi không thể đảo ngược:

- Xác nhận backup và khả năng restore đã được kiểm tra.
- Lưu số lượng và checksum/đối soát phù hợp.
- Biết cách khôi phục cột cũ nếu cần.
- Giữ khoảng thời gian quan sát đủ lâu.
- Xác nhận các consumer đã chuyển xong.

Backup chỉ hữu ích khi quy trình restore đã được diễn tập và thời gian phục hồi đáp ứng yêu cầu vận hành.

## 20. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| App cũ lỗi sau migration | Rename/drop cột khi instance cũ vẫn chạy | Dùng expand-and-contract |
| App mới lỗi với hàng cũ | Giả định cột mới đã được backfill | Cho phép null/fallback trong giai đoạn chuyển tiếp |
| Thêm NOT NULL thất bại | Bảng cũ còn hàng null hoặc app cũ chưa ghi field mới | Add nullable, backfill, rồi enforce |
| Thêm UNIQUE thất bại | Dữ liệu hiện tại đã trùng | Kiểm tra và xử lý duplicate trước |
| Thêm FK thất bại | Có orphan reference | Backfill và xác minh dữ liệu cha-con |
| Tạo index làm chậm ghi | Build index gây lock hoặc cạnh tranh IO | Dùng online/concurrent phù hợp và theo dõi tải |
| Backfill khóa bảng lâu | Một transaction cập nhật toàn bộ dữ liệu | Chia batch, commit và checkpoint |
| Dual-write tạo dữ liệu lệch | Hai field không có nguồn có thẩm quyền | Định nghĩa quy tắc, reconcile và metrics |
| Rollback app không chạy | Contract đã xóa cột app cũ cần | Chỉ contract sau khi hết dependency |
| Migration chạy local nhưng timeout production | Dữ liệu nhỏ, lock/DDL behavior khác | Test với dữ liệu lớn và đúng database/version |
| Hibernate tự thay đổi schema | Dùng ddl-auto=update trong production | Quản lý bằng Flyway/Liquibase |
| Migration version đã chạy bị sửa | Lịch sử migration không còn tái lập | Tạo migration version mới |
| Test chỉ chạy trên H2 | Khác biệt DDL, constraint, index và SQL | Dùng Testcontainers với engine production |
| CREATE INDEX CONCURRENTLY thất bại | Lệnh không được phép trong transaction hoặc index invalid còn sót | Dùng cấu hình migration đúng và kiểm tra trạng thái index |

## 21. Checklist trước khi triển khai thay đổi schema

- [ ] Liệt kê mọi app instance, worker, scheduler, report và integration đang dùng schema.
- [ ] Xác định app cũ có tương thích với schema sau expand không.
- [ ] Thêm cột mới ở trạng thái nullable hoặc có default đúng nghiệp vụ khi phù hợp.
- [ ] Deploy code tương thích trước khi chuyển dữ liệu.
- [ ] Thiết kế dual-write/read fallback có nguồn dữ liệu có thẩm quyền.
- [ ] Backfill theo batch, có checkpoint, idempotent và có thể pause/resume.
- [ ] Kiểm tra null, duplicate, orphan và dữ liệu không chuyển đổi được.
- [ ] Tạo index/constraint theo phương thức online phù hợp engine/version.
- [ ] Đánh giá lock, transaction DDL, replication lag và tài nguyên.
- [ ] Chuyển toàn bộ code đọc/ghi sang schema mới.
- [ ] Xác nhận không còn consumer dùng cột/index/constraint cũ.
- [ ] Contract trong một migration riêng sau thời gian quan sát.
- [ ] Kiểm thử rollback app và forward-fix database.
- [ ] Kiểm thử migration từ schema cũ trên đúng database engine.
- [ ] Dùng Flyway/Liquibase làm nguồn quản lý schema chính.
- [ ] Giữ Hibernate schema validation phù hợp ở production, ví dụ ddl-auto=validate.

## 22. Kết luận

Thay đổi schema an toàn cần tương thích với nhiều phiên bản ứng dụng cùng tồn tại trong rolling deployment. **Expand-and-contract** giúp tách việc thêm cấu trúc mới, triển khai code tương thích, backfill dữ liệu, chuyển luồng đọc/ghi và cuối cùng mới xóa cấu trúc cũ.

Cột, kiểu dữ liệu, index và constraint đều cần được đánh giá theo kích thước dữ liệu, lock, khả năng online và đặc tính của database/version. Dùng migration có version, backfill theo batch có thể chạy lại, kiểm tra dữ liệu trước khi enforce constraint và chỉ contract khi mọi consumer đã chuyển xong. Như vậy, thay đổi schema có thể được triển khai từng bước, quan sát được và phục hồi theo kế hoạch.