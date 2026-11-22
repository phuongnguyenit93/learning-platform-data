# Trigger và các truy cập dữ liệu bổ sung trong giao dịch

Trigger (*bộ kích hoạt*) là đoạn mã do cơ sở dữ liệu tự động chạy khi một sự kiện như INSERT, UPDATE hoặc DELETE xảy ra. Trigger thường được dùng để ghi audit, cập nhật dữ liệu tổng hợp, đồng bộ bảng liên quan hoặc áp dụng quy tắc nghiệp vụ.

Một điểm dễ bị bỏ qua là câu lệnh mà ứng dụng gửi lên có thể chỉ tác động trực tiếp đến một bảng, nhưng trigger lại đọc hoặc ghi thêm nhiều bảng khác. Những thao tác này vẫn tham gia vào xử lý đồng thời của giao dịch. Chúng có thể lấy thêm khóa, mở rộng phạm vi dữ liệu bị ảnh hưởng, tạo blocking hoặc deadlock, và làm phát sinh xung đột mà câu SQL ở tầng ứng dụng không thể hiện rõ.

Vì vậy, khi phân tích một transaction, cần tính cả những truy cập do trigger thực hiện. Trigger là một phần của đường thực thi dữ liệu và thường là một phần của cùng transaction với câu lệnh kích hoạt nó.

## 1. Trigger được chạy khi nào?

Trigger là một đối tượng được gắn với một bảng, view hoặc sự kiện của cơ sở dữ liệu. Khi sự kiện phù hợp xảy ra, hệ quản trị gọi trigger theo thời điểm và phạm vi đã khai báo.

Các thời điểm phổ biến:

- **BEFORE:** chạy trước khi thao tác thay đổi hàng được áp dụng. Có thể dùng để kiểm tra hoặc điều chỉnh dữ liệu đầu vào tùy hệ quản trị.
- **AFTER:** chạy sau khi thao tác trên hàng hoặc câu lệnh đã diễn ra theo ngữ nghĩa của engine. Thường dùng để ghi audit hoặc cập nhật dữ liệu liên quan.
- **INSTEAD OF:** chạy thay cho thao tác gốc trên một số loại đối tượng, thường gặp với view hoặc các trường hợp được hệ quản trị hỗ trợ.

Trigger cũng có thể chạy theo phạm vi:

- **Row-level trigger:** chạy một lần cho mỗi hàng bị tác động.
- **Statement-level trigger:** chạy một lần cho cả câu lệnh, dù câu lệnh ảnh hưởng một hàng hay nhiều hàng.

Cách hỗ trợ khác nhau giữa các hệ quản trị. PostgreSQL hỗ trợ trigger theo hàng và theo câu lệnh. MySQL trigger là row-level. SQL Server DML trigger chạy theo câu lệnh và cung cấp các bảng logic inserted và deleted, có thể chứa nhiều hàng.

Điều này ảnh hưởng trực tiếp đến cách viết trigger. Một trigger theo hàng có thể chạy hàng trăm lần trong một câu UPDATE lớn. Một trigger theo câu lệnh phải xử lý tập hàng trong inserted hoặc deleted, không được giả định rằng mỗi lần kích hoạt chỉ có một hàng.

## 2. Truy cập do trigger thực hiện thuộc transaction nào?

Trong các hệ quản trị quan hệ phổ biến, trigger DML thông thường được thực thi như một phần của câu lệnh kích hoạt và transaction hiện tại.

Ví dụ, ứng dụng chạy:

~~~sql
BEGIN;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 501;

COMMIT;
~~~

Giả sử bảng orders có AFTER UPDATE trigger để thêm một bản ghi vào order_audit. Khi UPDATE chạy, trigger cũng thực hiện INSERT vào bảng audit.

Luồng thực thi khái quát:

~~~mermaid
flowchart TD
    A["Ứng dụng chạy UPDATE orders"] --> B["Database cập nhật hàng orders"]
    B --> C["Trigger AFTER UPDATE được gọi"]
    C --> D["Trigger INSERT vào order_audit"]
    D --> E{"Cả câu lệnh và trigger thành công?"}
    E -->|Có| F["Transaction tiếp tục và COMMIT"]
    E -->|Không| G["Câu lệnh thất bại; transaction xử lý lỗi/ROLLBACK"]
~~~

Nếu trigger ghi audit thất bại và lỗi được truyền ra ngoài, câu UPDATE có thể thất bại. Khi transaction rollback, thay đổi trên orders và bản ghi audit thuộc cùng transaction cũng được rollback.

Vì vậy, trigger không phải một transaction độc lập tự động commit riêng. Nó tham gia vào ranh giới nguyên tử của thao tác kích hoạt nó. Chi tiết về loại storage engine, lỗi được xử lý bên trong trigger và khả năng phục hồi của transaction vẫn phụ thuộc hệ quản trị.

Không nên đặt trong trigger các hành động bên ngoài cơ sở dữ liệu như gọi HTTP, gửi email trực tiếp hoặc ghi file mà không có cơ chế điều phối phù hợp. Những tác động đó có thể không rollback cùng transaction nếu câu lệnh sau đó thất bại.

## 3. Một câu SQL có thể có tập đọc và tập ghi lớn hơn bạn nhìn thấy

Giả sử ứng dụng chỉ chạy:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 501;
~~~

Nhưng trigger thực hiện:

~~~sql
INSERT INTO order_audit (order_id, old_status, new_status)
VALUES (501, 'PENDING', 'PAID');

UPDATE customer_summary
SET paid_order_count = paid_order_count + 1
WHERE customer_id = 77;

SELECT credit_limit
FROM customer
WHERE customer_id = 77;
~~~

Tập truy cập thực tế của transaction bao gồm:

- Hàng trong orders bị UPDATE.
- Hàng mới trong order_audit được INSERT.
- Hàng customer_summary bị UPDATE.
- Hàng customer được SELECT.
- Các chỉ mục, khóa ngoại, constraint và trigger khác bị tác động gián tiếp.

Có thể mô hình hóa:

| Thành phần | Truy cập trực tiếp của ứng dụng | Truy cập bổ sung của trigger |
|---|---|---|
| orders | UPDATE | Có thể đọc giá trị OLD/NEW |
| order_audit | Không | INSERT |
| customer_summary | Không | UPDATE |
| customer | Không | SELECT |
| Chỉ mục và constraint | Theo câu UPDATE | Theo INSERT/UPDATE phát sinh |

Nếu chỉ đọc log ở tầng ứng dụng, ta có thể thấy một câu UPDATE nhưng không biết transaction đã ghi thêm hai bảng và đọc thêm một bảng. Điều này làm cho việc phân tích lock wait, deadlock và hiệu năng trở nên khó hơn.

Khi điều tra, hãy xem trigger của tất cả bảng bị tác động trực tiếp và gián tiếp. Một trigger trên bảng thứ hai cũng có thể kích hoạt trigger khác, tạo thành chuỗi truy cập nhiều tầng.

## 4. Trigger làm thay đổi thứ tự lấy khóa

Deadlock thường xuất hiện khi hai transaction lấy khóa trên cùng các tài nguyên theo thứ tự khác nhau.

Giả sử:

- T1 cập nhật orders, trigger của T1 cập nhật customer_summary.
- T2 cập nhật customer_summary, sau đó ứng dụng cập nhật orders.

Diễn biến có thể là:

| Bước | T1 | T2 |
|---|---|---|
| 1 | Khóa hàng orders(501) | |
| 2 | | Khóa hàng customer_summary(77) |
| 3 | Trigger yêu cầu khóa customer_summary(77), phải chờ T2 | |
| 4 | | Ứng dụng yêu cầu khóa orders(501), phải chờ T1 |

T1 giữ khóa orders và chờ customer_summary. T2 giữ customer_summary và chờ orders. Hai transaction tạo thành chu trình chờ.

~~~mermaid
flowchart LR
    T1["T1 giữ orders(501)"] -->|"chờ"| T2["T2 giữ customer_summary(77)"]
    T2 -->|"chờ"| T1
~~~

Nếu không biết trigger, người điều tra có thể thắc mắc vì sao câu UPDATE orders lại chờ khóa ở customer_summary. Nguyên nhân nằm trong đường thực thi ẩn bên trong trigger.

Một nguyên tắc hữu ích là thống nhất thứ tự truy cập tài nguyên trong toàn hệ thống. Nếu mọi luồng đều cập nhật orders trước rồi mới cập nhật customer_summary, khả năng deadlock do đảo thứ tự sẽ giảm. Nhưng cần xem cả trigger, stored procedure, batch job và các đường ghi khác. Một quy tắc thứ tự chỉ có hiệu lực khi mọi đường thực thi liên quan cùng tuân thủ.

## 5. Trigger kiểm tra điều kiện bằng SELECT có thể gặp race condition

Một trigger đôi khi kiểm tra dữ liệu trước khi cho phép thao tác. Ví dụ, hệ thống không cho phép tổng số đơn hàng đang mở của khách hàng vượt hạn mức.

Một cách viết có vẻ hợp lý:

~~~sql
-- Pseudocode: minh họa logic trigger, không phải cú pháp chung cho mọi DBMS.
SELECT COUNT(*)
INTO open_count
FROM orders
WHERE customer_id = NEW.customer_id
  AND status = 'OPEN';

IF open_count >= 10 THEN
    RAISE ERROR;
END IF;
~~~

Nếu hai transaction cùng tạo đơn hàng cho một khách hàng khi số đơn đang mở là 9, cả hai trigger có thể cùng đọc được 9. Mỗi transaction thấy điều kiện hợp lệ và cho phép INSERT. Kết quả sau khi cả hai commit là 11 đơn mở.

Vấn đề vẫn là race condition kiểu check-then-act:

1. Trigger đọc một tập dữ liệu hoặc aggregate.
2. Transaction khác cũng đọc cùng trạng thái.
3. Mỗi transaction ghi một hàng khác nhau.
4. Không có xung đột ghi trực tiếp trên cùng hàng để tự động ngăn cả hai.
5. Bất biến tổng hợp bị vi phạm.

Đưa câu SELECT vào trigger không tự làm cho phép kiểm tra trở nên nguyên tử. Trigger chạy trong transaction nhưng vẫn chịu isolation level và cơ chế khóa của hệ quản trị.

### 5.1. Cách bảo vệ điều kiện tổng hợp

Tùy loại quy tắc, có thể chọn:

- Dùng SERIALIZABLE để hệ quản trị bảo vệ tính khả tuần tự; ứng dụng phải xử lý serialization failure và retry toàn bộ transaction.
- Khóa một hàng điều phối đã tồn tại cho khách hàng trước khi đọc aggregate. Mọi đường tạo/hủy đơn phải lấy cùng khóa trước khi kiểm tra.
- Duy trì một hàng tổng hợp như open_order_count bằng UPDATE nguyên tử có điều kiện, trong cùng transaction với thay đổi đơn hàng.
- Dùng constraint nếu điều kiện có thể diễn đạt trực tiếp bằng constraint được hệ quản trị hỗ trợ.

Ví dụ một hàng bộ đếm được cập nhật nguyên tử:

~~~sql
UPDATE customer_summary
SET open_order_count = open_order_count + 1
WHERE customer_id = 77
  AND open_order_count < 10;
~~~

Ứng dụng hoặc trigger phải kiểm tra số hàng bị cập nhật. Nếu không cập nhật được hàng nào, thao tác tạo đơn phải bị từ chối và toàn bộ transaction phải rollback. Khi giảm số đơn mở, bộ đếm cũng phải được cập nhật trong cùng transaction.

Cách này tuần tự hóa các thay đổi trên cùng hàng summary. Nó chỉ đúng khi mọi thao tác tạo, đóng, hủy hoặc chuyển trạng thái đơn đều duy trì bộ đếm theo cùng một quy tắc.

## 6. Trigger cập nhật dữ liệu tổng hợp: dùng phép cập nhật nguyên tử

Một use case phổ biến là duy trì số lượng hàng con hoặc tổng giá trị của nhóm.

Ví dụ, sau khi thêm một dòng vào order_item, trigger tăng tổng số mặt hàng của đơn:

~~~sql
UPDATE order_summary
SET item_count = item_count + 1
WHERE order_id = NEW.order_id;
~~~

Phép cộng trực tiếp trên cột trong một UPDATE thường an toàn hơn mẫu đọc giá trị vào ứng dụng rồi ghi một giá trị tuyệt đối:

~~~sql
-- Mẫu dễ mất cập nhật nếu không có kiểm soát đồng thời thích hợp.
SELECT item_count
FROM order_summary
WHERE order_id = 501;

-- Ứng dụng tính item_count + 1 rồi gửi giá trị tuyệt đối.
UPDATE order_summary
SET item_count = 6
WHERE order_id = 501;
~~~

Với câu UPDATE nguyên tử, hệ quản trị điều phối các lần ghi cạnh tranh trên hàng order_summary. Hai transaction tăng cùng bộ đếm sẽ không đơn giản ghi đè cùng một giá trị cũ nếu dùng đúng cơ chế cập nhật của database.

Tuy vậy, hàng tổng hợp có thể trở thành điểm nóng (*hot row*) nếu nhiều transaction đồng thời cập nhật cùng một nhóm. Điều này làm tăng thời gian chờ và có thể giảm throughput. Cần cân nhắc liệu aggregate có thể được tính khi đọc, phân vùng thành nhiều bộ đếm, hay cập nhật theo batch.

Nếu trigger chạy theo từng hàng, một câu INSERT nhiều hàng có thể khiến UPDATE summary lặp lại nhiều lần. Với workload lớn, trigger theo câu lệnh hoặc xử lý theo tập có thể hiệu quả hơn nếu hệ quản trị hỗ trợ.

## 7. Trigger phải xử lý đúng câu lệnh tác động nhiều hàng

Không được mặc định một câu UPDATE chỉ sửa một hàng. Ví dụ:

~~~sql
UPDATE orders
SET status = 'EXPIRED'
WHERE expires_at < CURRENT_TIMESTAMP;
~~~

Câu lệnh có thể tác động hàng nghìn đơn. Trigger phải xử lý tất cả hàng liên quan.

Khác biệt theo hệ quản trị:

| Hệ quản trị | Dạng trigger DML | Cách xử lý nhiều hàng |
|---|---|---|
| PostgreSQL | Có trigger theo hàng và theo câu lệnh | Trigger theo hàng nhận OLD/NEW cho từng hàng; statement-level trigger có thể dùng transition tables khi được hỗ trợ và cấu hình phù hợp |
| MySQL | Trigger DML theo hàng | Trigger chạy một lần cho mỗi hàng bị tác động |
| SQL Server | Trigger DML theo câu lệnh | Dùng các bảng logic inserted và deleted, mỗi bảng có thể chứa nhiều hàng |

Trong SQL Server, trigger không nên viết kiểu giả định chỉ có một hàng:

~~~sql
-- Không an toàn nếu inserted có nhiều hàng:
SELECT @order_id = OrderId
FROM inserted;
~~~

Cách này chỉ gán một giá trị biến từ một tập nhiều hàng, không xử lý đầy đủ mọi hàng.

Nên dùng thao tác theo tập:

~~~sql
-- Ví dụ minh họa trigger SQL Server:
UPDATE s
SET s.item_count = s.item_count + x.added_count
FROM dbo.OrderSummary AS s
JOIN (
    SELECT OrderId, COUNT(*) AS added_count
    FROM inserted
    GROUP BY OrderId
) AS x
  ON x.OrderId = s.order_id;
~~~

Đây là một cập nhật theo tập, gom số hàng mới theo từng đơn rồi cập nhật summary tương ứng. Với trigger xử lý DELETE hoặc UPDATE, cần xem cả deleted và inserted để tính phần giảm và tăng. Nếu một UPDATE đổi OrderId, cần trừ ở nhóm cũ và cộng ở nhóm mới.

Với PostgreSQL, nếu cần xử lý một tập hàng ở cấp statement, có thể cân nhắc transition tables cho các loại trigger hỗ trợ. Với MySQL, do trigger theo hàng, cần viết logic sao cho đúng khi được gọi nhiều lần và chú ý chi phí truy cập lặp lại.

## 8. Trigger có thể kích hoạt trigger khác

Một câu lệnh trong trigger có thể tác động đến bảng cũng có trigger riêng. Khi đó, một sự kiện ban đầu có thể tạo ra chuỗi:

~~~mermaid
flowchart TD
    A["INSERT order_item"] --> B["Trigger trên order_item"]
    B --> C["UPDATE order_summary"]
    C --> D["Trigger trên order_summary"]
    D --> E["UPDATE customer_summary"]
    E --> F["Trigger trên customer_summary"]
    F --> G["Ghi audit hoặc cập nhật thêm dữ liệu"]
~~~

Chuỗi trigger làm tăng:

- Số câu SQL thực sự được thực thi.
- Số hàng và chỉ mục bị truy cập.
- Số khóa được yêu cầu và thời gian giữ khóa.
- Khả năng gặp deadlock hoặc lock escalation.
- Độ khó khi truy vết lỗi và đo hiệu năng.

Một trigger có thể gián tiếp kích hoạt lại chính nó hoặc tạo vòng lặp giữa nhiều bảng. Cách hệ quản trị cho phép, giới hạn hoặc phát hiện trigger recursion khác nhau. Cần xác định rõ đường gọi, điều kiện dừng và các cờ kiểm soát recursion nếu engine hỗ trợ.

Tránh để trigger phụ thuộc vào việc một trigger khác chạy trước nếu thứ tự đó không được hệ quản trị bảo đảm. Nếu cần một thứ tự nghiệp vụ cụ thể, hãy dùng cơ chế thứ tự trigger được tài liệu hóa của engine hoặc gộp logic vào một đường thực thi rõ ràng.

## 9. Trigger và các ràng buộc dữ liệu

Trigger có thể kiểm tra quy tắc nghiệp vụ phức tạp, nhưng không nên dùng trigger thay thế mọi constraint.

Ưu tiên constraint khi quy tắc có thể biểu diễn bằng:

- PRIMARY KEY hoặc UNIQUE cho tính duy nhất.
- FOREIGN KEY cho quan hệ tham chiếu.
- NOT NULL cho giá trị bắt buộc.
- CHECK cho điều kiện trên hàng mà hệ quản trị hỗ trợ.

Constraint thường dễ nhìn thấy hơn, được tích hợp vào engine và áp dụng thống nhất cho mọi đường ghi. Một trigger tự viết có thể chứa lỗi race condition nếu chỉ SELECT kiểm tra rồi mới cho INSERT/UPDATE.

Trigger phù hợp khi cần thực hiện hành động bổ sung gắn với sự kiện dữ liệu, chẳng hạn ghi audit, duy trì dữ liệu dẫn xuất hoặc áp dụng logic không thể diễn đạt bằng constraint thông thường. Nhưng khi trigger kiểm tra bất biến nhiều hàng, vẫn phải thiết kế cơ chế đồng bộ phù hợp.

## 10. Trigger không làm biến mất khác biệt isolation level

Trigger chạy trong transaction, nên các truy vấn bên trong trigger chịu quy tắc visibility và isolation của transaction đó. Nó không tự nâng isolation level và không tự lấy khóa mạnh hơn chỉ vì mã được đặt trong trigger.

Ví dụ, một trigger chạy câu SELECT COUNT để kiểm tra số lượng hàng thỏa điều kiện có thể gặp phantom hoặc write skew nếu isolation level và cơ chế khóa cho phép. Cùng một trigger có thể có hành vi đồng thời khác nhau khi chạy ở READ COMMITTED, REPEATABLE READ, SNAPSHOT hoặc SERIALIZABLE, tùy engine.

Khi dùng trigger để duy trì bất biến:

1. Xác định tất cả bảng và predicate trigger đọc.
2. Xác định tất cả hàng trigger ghi.
3. Xác định isolation level mà ứng dụng thực sự dùng.
4. Xác định loại khóa hoặc cơ chế serialization của engine.
5. Kiểm tra xem nhiều transaction có thể đọc cùng điều kiện rồi ghi các hàng khác nhau không.
6. Nếu cần, dùng constraint, guard row, cập nhật nguyên tử hoặc SERIALIZABLE kèm retry.

Không nên kết luận “trigger chạy trong transaction nên dữ liệu chắc chắn nhất quán”. Tính nguyên tử chỉ bảo đảm các thay đổi của một transaction được commit hoặc rollback cùng nhau; nó không tự giải quyết mọi xung đột giữa nhiều transaction.

## 11. Trigger và giao dịch lồng nhau

Một số hệ quản trị không cho trigger thông thường tự bắt đầu hoặc commit transaction riêng. Trigger tham gia transaction đã kích hoạt nó. Ví dụ, PostgreSQL trigger function không thể thực hiện COMMIT/ROLLBACK như một transaction độc lập; MySQL trigger cũng không được tự điều khiển transaction theo cách đó.

SQL Server hỗ trợ các transaction lồng nhau ở mức cú pháp và có thể gọi stored procedure từ trigger, nhưng các transaction này vẫn nằm trong transaction ngoài; một rollback có thể ảnh hưởng toàn bộ transaction hiện hành tùy điểm rollback và trạng thái transaction.

Không nên xem việc gọi stored procedure từ trigger là cách tách biệt thay đổi của trigger thành một transaction độc lập. Nếu cần tác động bên ngoài database, hãy ghi một bản ghi outbox trong cùng transaction rồi để tiến trình riêng gửi thông điệp sau khi commit.

Ví dụ mô hình outbox:

~~~sql
BEGIN;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 501;

-- Trigger hoặc ứng dụng ghi sự kiện vào outbox.
INSERT INTO outbox_event (event_type, aggregate_id, payload)
VALUES ('OrderPaid', 501, '{"orderId":501}');

COMMIT;
~~~

Worker đọc các sự kiện đã commit trong outbox và gửi đến hệ thống bên ngoài. Cách này giúp trạng thái đơn và ý định phát sự kiện được ghi nguyên tử. Worker vẫn cần xử lý gửi lặp bằng idempotency key hoặc cơ chế deduplication vì việc gửi ra ngoài và đánh dấu đã gửi có thể thất bại ở các thời điểm khác nhau.

## 12. Cách điều tra blocking và deadlock có liên quan đến trigger

Khi một câu lệnh bị chờ khóa, đừng chỉ xem SQL do ứng dụng gửi. Hãy thu thập:

- Trigger gắn với bảng mà câu lệnh INSERT/UPDATE/DELETE tác động.
- Stored procedure hoặc function được trigger gọi.
- Các bảng được SELECT, INSERT, UPDATE hoặc DELETE bên trong trigger.
- Thứ tự truy cập tài nguyên giữa các trigger và đường SQL trực tiếp.
- Isolation level, locking hint và access path.
- Deadlock graph hoặc báo cáo deadlock của hệ quản trị.
- Transaction nào giữ khóa, transaction nào đang yêu cầu khóa, và câu lệnh thực tế tại thời điểm chờ.

Một deadlock graph có thể cho thấy ứng dụng chạy UPDATE trên orders, nhưng tài nguyên bị chờ lại là khóa trên customer_summary. Khi đó cần lần theo trigger đã tạo yêu cầu khóa bổ sung.

Hãy phân biệt blocking với deadlock. Trigger có thể làm transaction chờ lâu vì nó cập nhật một hàng summary đang nóng. Chỉ khi các quan hệ chờ tạo thành chu trình thì mới là deadlock.

## 13. Thiết kế trigger để giảm tranh chấp

Một số nguyên tắc giúp trigger dễ hiểu và ít tạo bất ngờ hơn:

**Giữ trigger ngắn.** Chỉ thực hiện thao tác cần thiết. Tránh truy vấn rộng, tính toán nặng hoặc gọi các dịch vụ ngoài trong lúc transaction đang giữ khóa.

**Dùng câu lệnh theo tập.** Nếu hệ quản trị hỗ trợ statement-level trigger, xử lý tập hàng thay vì chạy cùng một truy vấn phụ lặp lại cho từng hàng.

**Thống nhất thứ tự truy cập bảng.** Mọi đường cập nhật liên quan nên lấy khóa theo cùng một thứ tự, kể cả các thao tác ẩn trong trigger.

**Dùng cập nhật nguyên tử cho bộ đếm.** Tránh đọc giá trị vào biến rồi ghi giá trị tuyệt đối nếu có thể dùng một câu UPDATE tăng/giảm trực tiếp.

**Không dựa vào SELECT kiểm tra đơn thuần cho bất biến liên hàng.** Dùng constraint, SERIALIZABLE, guard row hoặc cơ chế khóa predicate phù hợp.

**Kiểm soát trigger chain và recursion.** Biết trigger nào gọi trigger nào, điều kiện nào dừng chuỗi, và tránh cập nhật vòng lặp không cần thiết.

**Làm cho lỗi dễ quan sát.** Ghi log hoặc trả lỗi có ngữ nghĩa rõ ràng. Tránh nuốt lỗi rồi để ứng dụng tưởng rằng toàn bộ thao tác đã thành công.

**Tách tác động bên ngoài bằng outbox.** Ghi ý định gửi sự kiện trong transaction; gửi sau commit bằng worker có khả năng retry an toàn.

## 14. Ví dụ tổng hợp: ghi audit và cập nhật summary

Giả sử mỗi lần trạng thái đơn hàng thay đổi, hệ thống cần:

1. Cập nhật trạng thái đơn.
2. Ghi lịch sử thay đổi.
3. Cập nhật số đơn đã thanh toán của khách hàng.

Một trigger AFTER UPDATE có thể thực hiện hai thao tác phụ. Logic khái quát:

~~~sql
-- Pseudocode: cú pháp trigger phụ thuộc hệ quản trị.
IF OLD.status <> NEW.status THEN
    INSERT INTO order_audit (
        order_id, old_status, new_status, changed_at
    )
    VALUES (
        NEW.order_id, OLD.status, NEW.status, CURRENT_TIMESTAMP
    );

    IF NEW.status = 'PAID' THEN
        UPDATE customer_summary
        SET paid_order_count = paid_order_count + 1
        WHERE customer_id = NEW.customer_id;
    END IF;
END IF;
~~~

Khi thiết kế cần xác định:

- Nếu một câu UPDATE thay đổi nhiều đơn, trigger có xử lý đủ mọi hàng không?
- Nếu đơn chuyển từ PAID sang CANCELLED, bộ đếm có phải giảm không?
- Nếu customer_id thay đổi, bộ đếm của khách cũ và khách mới được điều chỉnh thế nào?
- Nếu summary chưa có hàng, thao tác UPDATE ảnh hưởng 0 hàng; có cần tạo hàng hoặc dùng cơ chế upsert không?
- Nếu hai đơn của cùng khách thay đổi đồng thời, chúng cùng cập nhật một summary row và có thể phải chờ nhau không?
- Nếu một trigger khác cũng cập nhật bảng customer hoặc audit, thứ tự lấy khóa có nhất quán không?
- Nếu ghi audit thất bại, có cần rollback luôn thay đổi trạng thái đơn không? Thông thường, audit bắt buộc nên nằm trong cùng transaction để không ghi nhận thiếu.

Các câu hỏi này cho thấy trigger cần được thiết kế như một phần của transaction, với tập đọc, tập ghi và thứ tự khóa rõ ràng.

## 15. Checklist khi dùng trigger trong transaction

- [ ] Đã xác định trigger nào được kích hoạt bởi INSERT, UPDATE hoặc DELETE chưa?
- [ ] Trigger chạy theo hàng hay theo câu lệnh, và có thể nhận nhiều hàng không?
- [ ] Đã liệt kê mọi bảng trigger đọc và ghi chưa?
- [ ] Các thao tác bổ sung có làm thay đổi thứ tự lấy khóa giữa các transaction không?
- [ ] Trigger có kiểm tra aggregate hoặc predicate dễ gặp race condition không?
- [ ] Có thể dùng constraint hoặc câu UPDATE nguyên tử thay cho SELECT rồi ghi không?
- [ ] Nếu dùng guard row hoặc SERIALIZABLE, mọi đường ghi có tuân thủ cùng cơ chế không?
- [ ] Trigger chain có thể đệ quy hoặc kích hoạt vòng lặp không?
- [ ] Có đang gọi dịch vụ ngoài hoặc tạo side effect không rollback được trong trigger không?
- [ ] Deadlock diagnostics có giúp truy ngược được câu SQL bên trong trigger không?
- [ ] Có xử lý retry toàn bộ transaction khi gặp serialization failure hoặc deadlock không?

Trigger giúp đặt logic gần dữ liệu và bảo đảm các thao tác bổ sung tham gia cùng transaction với câu lệnh kích hoạt. Nhưng chính các thao tác bổ sung đó làm tăng tập đọc, tập ghi và số khóa mà transaction cần. Khi phân tích tính đúng đắn và hiệu năng, hãy xem trigger như một phần của câu lệnh thực tế: xác định mọi truy cập ẩn, bảo vệ predicate bằng cơ chế phù hợp, thống nhất thứ tự lấy khóa và giữ trigger đủ ngắn để giảm tranh chấp.
