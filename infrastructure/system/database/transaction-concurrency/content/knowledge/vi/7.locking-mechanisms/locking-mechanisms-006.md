# Gộp khóa (lock escalation) và ảnh hưởng đến mức tranh chấp

Trong cơ sở dữ liệu, khóa (lock) bảo vệ dữ liệu khi nhiều transaction cùng đọc hoặc ghi. Một transaction cập nhật vài dòng thường chỉ cần khóa ở mức dòng hoặc khóa chỉ mục. Nhưng khi một câu lệnh chạm đến hàng nghìn dòng, việc duy trì quá nhiều khóa nhỏ có thể tiêu tốn bộ nhớ và công sức quản lý. Một số hệ quản trị cơ sở dữ liệu giải quyết tình huống này bằng **gộp khóa (lock escalation)**: thay nhiều khóa ở mức chi tiết bằng một khóa ở mức rộng hơn, chẳng hạn từ khóa dòng/trang lên khóa bảng.

Gộp khóa giúp giảm số lượng khóa mà hệ quản trị phải theo dõi, nhưng phạm vi bảo vệ dữ liệu rộng hơn. Vì vậy, một transaction có thể làm các transaction khác phải chờ dù chúng đang truy cập những dòng khác nhau. Đây là lý do lock escalation có thể làm tăng mức tranh chấp (contention).

> Các ví dụ và ngưỡng cụ thể trong bài chủ yếu mô tả Microsoft SQL Server. Lock escalation là hành vi phụ thuộc hệ quản trị; không nên mặc định PostgreSQL, MySQL InnoDB, Oracle và SQL Server có cùng cơ chế.

## 1. Mức khóa và lý do cần gộp khóa

Hệ quản trị có thể khóa dữ liệu ở nhiều mức (lock granularity). Tên và cách tổ chức tài nguyên khóa thay đổi theo sản phẩm, nhưng các mức thường gặp gồm:

| Mức khóa | Phạm vi được bảo vệ | Đặc điểm |
|---|---|---|
| Dòng hoặc bản ghi | Một dòng dữ liệu | Phạm vi hẹp, cho phép nhiều transaction thao tác trên các dòng khác nhau |
| Khóa chỉ mục (key lock) | Một khóa trong chỉ mục | Thường được dùng để bảo vệ bản ghi thông qua chỉ mục; có thể liên quan đến khóa phạm vi |
| Trang (page) | Một trang dữ liệu hoặc chỉ mục | Bao phủ nhiều dòng nằm trên cùng trang |
| Phân vùng (partition) | Một phân vùng của bảng hoặc chỉ mục | Phạm vi lớn hơn dòng/trang nhưng hẹp hơn toàn bảng |
| Bảng (table) | Toàn bộ bảng | Dễ quản lý hơn khi có rất nhiều khóa nhỏ, nhưng có thể chặn nhiều hoạt động độc lập |

Khóa càng chi tiết thì các transaction càng có cơ hội làm việc song song trên những vùng dữ liệu khác nhau. Đổi lại, hệ quản trị phải lưu và kiểm tra nhiều mục khóa hơn. Mỗi mục khóa cần thông tin về tài nguyên, transaction sở hữu, chế độ khóa và các yêu cầu đang chờ.

Ví dụ, một transaction cập nhật 20.000 dòng có thể cần hàng chục nghìn khóa trên các dòng hoặc khóa chỉ mục. Nếu giữ tất cả khóa nhỏ, lock manager phải quản lý một tập khóa lớn. Gộp chúng thành một khóa bảng có thể giảm đáng kể số mục cần theo dõi.

Đây là sự đánh đổi giữa hai mục tiêu:

- **Giảm chi phí quản lý khóa:** ít mục khóa hơn, giảm áp lực bộ nhớ dành cho lock manager.
- **Giữ tính đồng thời cao:** khóa càng hẹp thì càng ít transaction độc lập bị chặn.

Không có một mức khóa luôn tốt nhất. Khóa dòng có lợi cho truy cập nhỏ và cạnh tranh cao; khóa bảng có thể hợp lý khi một transaction thực sự xử lý phần lớn bảng và những transaction khác không cần truy cập đồng thời.

### Khóa ý định (intent lock)

Trong SQL Server, khi một transaction giữ khóa ở mức thấp, hệ quản trị thường đặt thêm khóa ý định ở mức cha. Chẳng hạn, transaction giữ khóa X trên một số dòng có thể đồng thời giữ khóa ý định IX ở mức bảng. Khóa ý định báo cho transaction khác biết rằng bên dưới tài nguyên cha đang có khóa chi tiết.

Các chế độ thường gặp:

- **IS (Intent Shared):** bên dưới có hoặc sẽ có khóa chia sẻ.
- **IX (Intent Exclusive):** bên dưới có hoặc sẽ có khóa độc quyền.
- **SIX (Shared with Intent Exclusive):** giữ khóa chia sẻ ở mức hiện tại và có ý định giữ khóa độc quyền ở cấp thấp hơn.

Khóa ý định giúp hệ quản trị kiểm tra tính tương thích ở các mức khác nhau mà không cần duyệt từng dòng. Nó cũng giải thích vì sao khóa X ở mức bảng có thể chặn một transaction khác ngay khi transaction đó mới xin IX để chuẩn bị cập nhật một dòng.

## 2. Lock escalation diễn ra như thế nào?

**Lock escalation** là quá trình thay một tập khóa ở mức chi tiết bằng khóa ở mức cao hơn, có phạm vi bao phủ các tài nguyên đã bị khóa.

Ví dụ, transaction A cập nhật nhiều dòng trong bảng Orders:

1. A lấy khóa độc quyền trên các dòng hoặc khóa chỉ mục cần cập nhật.
2. Số lượng khóa tăng lên trong khi câu lệnh tiếp tục xử lý.
3. Khi đạt điều kiện gộp khóa của hệ quản trị, SQL Server có thể thử lấy khóa ở mức bảng hoặc phân vùng với chế độ đủ mạnh để bảo vệ các thay đổi.
4. Nếu gộp thành công, nhiều khóa dòng/trang chi tiết được thay thế bằng khóa cấp cao hơn.
5. Khóa cấp cao hơn tiếp tục được giữ theo quy tắc thời gian sống của khóa và transaction.

Có thể hình dung sự thay đổi như sau:

~~~text
Trước khi gộp khóa

Bảng Orders
  ├── Dòng 101: X
  ├── Dòng 102: X
  ├── Dòng 103: X
  ├── ...
  └── Dòng 20.000: X

Sau khi gộp khóa thành công

Bảng Orders: X
  └── Phạm vi khóa bao phủ toàn bảng
~~~

Trong ví dụ cập nhật, chế độ khóa cấp bảng thường là X (Exclusive). Với thao tác đọc, chế độ khóa được chọn có thể là S (Shared), tùy câu lệnh, isolation level và trạng thái khóa hiện có. Không phải mọi lần gộp đều tạo khóa X; chế độ khóa phải đủ để duy trì quyền truy cập mà transaction đã có.

Gộp khóa không có nghĩa là transaction cập nhật thêm dữ liệu. Nó thay đổi **phạm vi khóa đang được giữ**. Một câu lệnh vẫn tác động lên cùng tập dữ liệu, nhưng các transaction khác phải kiểm tra tương thích với khóa rộng hơn.

### Gộp lên bảng hay phân vùng?

Trong SQL Server, đích gộp thường là bảng. Với bảng được phân vùng, cấu hình LOCK_ESCALATION có thể cho phép gộp ở mức phân vùng (partition) thay vì toàn bảng. Khi đó, transaction khóa một phân vùng có thể ít ảnh hưởng đến transaction thao tác trên phân vùng khác.

Gộp ở mức phân vùng vẫn làm tăng phạm vi so với khóa dòng/trang. Những transaction cùng truy cập phân vùng đó vẫn có thể phải chờ. Cấu hình phân vùng cần được kiểm thử với cách phân bố dữ liệu và thứ tự truy cập thực tế; nhiều transaction khóa nhiều phân vùng theo thứ tự khác nhau cũng có thể tạo ra tình huống chờ hoặc deadlock.

## 3. Khi nào SQL Server thử gộp khóa?

SQL Server có thể xem xét lock escalation khi số lượng khóa của một câu lệnh trên một tham chiếu bảng/chỉ mục tăng cao hoặc khi bộ nhớ dành cho khóa chịu áp lực.

Một ngưỡng thường được nhắc đến trong SQL Server là khoảng **5.000 khóa trên một tham chiếu bảng hoặc chỉ mục trong một câu lệnh**. Áp lực bộ nhớ khóa cũng có thể khiến hệ quản trị thử gộp. Đây là quy tắc triển khai của SQL Server, không phải hằng số chung cho mọi hệ quản trị và cũng không phải cam kết rằng cứ đạt đúng con số đó thì chắc chắn sẽ gộp.

Một số điểm cần hiểu đúng:

- Số dòng bị ảnh hưởng không nhất thiết bằng số khóa. Một câu lệnh có thể cần khóa trên nhiều chỉ mục hoặc tài nguyên liên quan.
- Kế hoạch thực thi, chỉ mục, isolation level, loại thao tác và dữ liệu thực tế đều có thể làm số lượng khóa khác nhau.
- Đạt điều kiện chỉ có nghĩa SQL Server có thể thử gộp. Việc gộp có thành công hay không còn phụ thuộc khả năng lấy khóa cấp cao hơn.
- Nếu khóa cấp cao hơn xung đột với khóa do session khác đang giữ, lần thử có thể không thành công. SQL Server có thể tiếp tục dùng các khóa chi tiết và thử lại khi điều kiện thay đổi.
- Các hệ quản trị khác có cơ chế quản lý khóa và ngưỡng hoàn toàn khác.

Vì vậy, không nên suy luận rằng một câu lệnh cập nhật 5.000 dòng luôn gây lock escalation, hoặc một câu lệnh cập nhật ít hơn 5.000 dòng thì không thể gây ra hiện tượng này.

## 4. Vì sao gộp khóa làm tăng contention?

Contention là tình trạng nhiều transaction cạnh tranh cùng tài nguyên hoặc phải chờ nhau để được tiếp tục. Khi khóa được gộp, phạm vi tài nguyên mà transaction khác phải kiểm tra có thể mở rộng đáng kể.

Giả sử bảng Orders có một triệu dòng. Transaction A cập nhật một tập lớn các đơn hàng cũ. Transaction B cập nhật một đơn hàng mới có OrderId khác hoàn toàn với các dòng A đang xử lý.

Nếu A chỉ giữ khóa X trên các dòng cũ, B có thể cập nhật dòng riêng của mình mà không xung đột với những khóa đó. Nhưng nếu A được gộp thành khóa X ở mức bảng, B cần khóa ý định IX trên bảng trước khi cập nhật dòng của nó. Khóa IX không tương thích với khóa X cấp bảng, nên B phải chờ.

~~~text
Không gộp khóa

Session A                         Session B
---------                         ---------
X khóa các dòng cũ
                                  IX ở bảng
                                  X khóa dòng mới
A và B có thể tiếp tục nếu
các tài nguyên không giao nhau


Sau khi A gộp thành khóa X bảng

Session A                         Session B
---------                         ---------
X khóa toàn bảng
                                  Yêu cầu IX ở bảng
                                  |
                                  +---- WAIT
A COMMIT
                                  B tiếp tục
~~~

Điểm đáng chú ý là hai session không nhất thiết cập nhật cùng một dòng. Sự chờ xuất hiện vì khóa bảng của A bao phủ cả dòng mà B muốn cập nhật.

### Các ảnh hưởng thường gặp

**1. Tăng blocking**

Một transaction giữ khóa rộng có thể làm nhiều transaction khác phải chờ. Số session bị chặn có thể tăng dù số dòng thực sự giao nhau giữa các câu lệnh rất nhỏ.

Mức chặn phụ thuộc chế độ khóa và isolation level. Ví dụ, khóa X ở mức bảng thường xung đột với yêu cầu khóa cần thiết cho cả đọc có khóa lẫn ghi. Một số truy vấn đọc dùng row versioning có thể tránh phải lấy khóa S dữ liệu và nhờ đó ít bị ảnh hưởng hơn, nhưng thao tác ghi vẫn cần khóa phù hợp.

**2. Giảm concurrency và throughput**

Các transaction vốn có thể chạy song song trên những dòng độc lập nay phải xếp hàng. Số transaction hoàn tất trong một đơn vị thời gian (throughput) có thể giảm, nhất là khi transaction giữ khóa bảng trong thời gian dài.

**3. Tăng độ trễ và thời gian chờ**

Session bị chặn phải đợi transaction giữ khóa kết thúc hoặc nhả khóa. Một truy vấn vốn chỉ mất vài mili giây có thể kéo dài nhiều giây nếu phải chờ. Khi ứng dụng có timeout và retry, lượng công việc lặp lại còn có thể làm tải hệ thống tăng thêm.

**4. Tạo hiệu ứng dây chuyền**

Một session bị chặn có thể đang giữ những khóa khác. Session thứ ba lại chờ khóa do session thứ hai giữ, khiến một transaction gộp khóa trở thành điểm đầu của chuỗi blocking dài. Khi nhiều request cùng chờ, hàng đợi ở tầng ứng dụng cũng có thể tăng.

**5. Có thể làm tăng nguy cơ deadlock, nhưng không đồng nghĩa với deadlock**

Blocking là một transaction phải chờ transaction khác. Deadlock xảy ra khi tồn tại chu trình chờ: A chờ tài nguyên của B trong khi B chờ tài nguyên của A (hoặc có nhiều session tạo thành chu trình).

Khóa rộng làm tăng số tài nguyên có thể xung đột, nên có thể góp phần tạo điều kiện cho deadlock. Tuy nhiên, một khóa bảng được giữ bởi A và nhiều session cùng chờ A vẫn chỉ là blocking nếu không hình thành chu trình.

### Mặt lợi của lock escalation

Không nên xem mọi lần gộp khóa là lỗi. Gộp khóa có thể:

- Giảm số lượng mục khóa cần lưu và quản lý.
- Giảm áp lực bộ nhớ của lock manager.
- Giảm chi phí kiểm tra một tập rất lớn khóa chi tiết.
- Phù hợp với thao tác bảo trì hoặc cập nhật hàng loạt vốn đã chiếm phần lớn bảng và không cần nhiều transaction khác truy cập đồng thời.

Vấn đề cần đánh giá là lợi ích giảm chi phí quản lý khóa có lớn hơn chi phí chờ do phạm vi khóa rộng hay không.

## 5. Ví dụ thực tế với hai session trong SQL Server

Giả sử bảng Orders có chỉ mục trên OrderId và chứa nhiều đơn hàng. Session A lưu trữ các đơn hàng cũ; Session B cập nhật trạng thái một đơn hàng mới.

### Session A — cập nhật nhiều dòng

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.Orders
SET IsArchived = 1
WHERE OrderDate < '2024-01-01';

-- Giữ transaction mở trong lúc kiểm tra để quan sát blocking.
-- Trong ứng dụng thật, không nên cố ý kéo dài transaction.

COMMIT TRANSACTION;
~~~

Nếu câu lệnh xử lý nhiều dòng, SQL Server có thể giữ nhiều khóa X trên các dòng/khóa chỉ mục. Khi điều kiện gộp được đáp ứng và việc lấy khóa cấp cao hơn thành công, nó có thể gộp thành khóa X ở mức bảng.

### Session B — cập nhật một dòng khác

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.Orders
SET Status = 'Processing'
WHERE OrderId = 900001;

COMMIT TRANSACTION;
~~~

Nếu khóa X cấp bảng của A còn được giữ, B có thể bị chặn khi yêu cầu khóa IX ở bảng, dù OrderId 900001 không thuộc tập dòng cũ mà A cập nhật.

Khi A COMMIT, khóa được giải phóng và B có thể tiếp tục. Nếu câu lệnh A chạy trong chế độ autocommit, transaction thường kết thúc cùng câu lệnh và khoảng thời gian chặn có thể ngắn hơn. Với transaction tường minh, khóa ghi thường được giữ đến COMMIT hoặc ROLLBACK; vì vậy, thời gian sống của transaction ảnh hưởng trực tiếp đến thời gian session khác phải chờ.

**Lưu ý:** ví dụ mô tả tình huống có gộp khóa thành công. Không thể dựa vào số dòng trong ví dụ để khẳng định SQL Server chắc chắn sẽ gộp. Muốn xác nhận trên hệ thống thật, cần quan sát sự kiện lock escalation và các khóa đang được giữ.

## 6. Khác biệt giữa các hệ quản trị cơ sở dữ liệu

Tên gọi lock escalation thường được dùng khi nói về SQL Server, nhưng không nên áp dụng máy móc cho mọi DBMS.

| Hệ quản trị | Cách tiếp cận liên quan |
|---|---|
| Microsoft SQL Server | Có cơ chế tự động gộp nhiều khóa chi tiết thành khóa bảng hoặc, tùy cấu hình bảng phân vùng, khóa phân vùng |
| PostgreSQL | Không thực hiện kiểu tự động nâng hàng loạt row lock thành table lock như SQL Server; PostgreSQL vẫn sử dụng các table-level lock mode riêng bên cạnh row-level lock |
| MySQL InnoDB | Dùng record lock, gap lock và next-key lock tùy truy vấn/isolation; không dựa trên cơ chế SQL Server-style tự động gộp row lock thành table lock |
| Oracle Database | Sử dụng row-level lock cho dữ liệu được cập nhật và table-level lock mode để phối hợp truy cập; không nên suy ra có cùng ngưỡng escalation như SQL Server |

Do đó, khi phân tích contention cần đọc tài liệu của đúng DBMS và đúng phiên bản. Một hệ quản trị không có lock escalation kiểu SQL Server vẫn có thể gặp blocking do khóa dòng, khóa phạm vi, khóa bảng phục vụ DDL hoặc các cơ chế đồng thời khác.

## 7. Cách giảm tác động của lock escalation

Không có một biện pháp phù hợp cho mọi workload. Hãy xác định câu lệnh nào tạo nhiều khóa, transaction nào giữ khóa lâu và session nào đang chờ, sau đó chọn cách giảm phạm vi hoặc thời gian giữ khóa.

### 7.1. Chia thao tác lớn thành các batch nhỏ

Thay vì cập nhật hàng trăm nghìn dòng trong một transaction dài, có thể xử lý theo từng nhóm nhỏ và COMMIT sau mỗi nhóm.

Ví dụ T-SQL:

~~~sql
WHILE 1 = 1
BEGIN
    ;WITH BatchOrders AS
    (
        SELECT TOP (1000) OrderId
        FROM dbo.Orders
        WHERE IsArchived = 0
          AND OrderDate < '2024-01-01'
        ORDER BY OrderId
    )
    UPDATE o
    SET IsArchived = 1
    FROM dbo.Orders AS o
    INNER JOIN BatchOrders AS b
        ON b.OrderId = o.OrderId;

    IF @@ROWCOUNT = 0
        BREAK;
END;
~~~

Trong ví dụ này, mỗi câu lệnh UPDATE chạy ở chế độ autocommit nếu không có transaction bên ngoài bao quanh vòng lặp. Vì vậy, mỗi batch có thể kết thúc và giải phóng khóa trước khi batch tiếp theo chạy. Kích thước 1.000 chỉ là giá trị minh họa; cần điều chỉnh dựa trên thời gian chạy, tải hệ thống, kích thước dòng và mức blocking thực tế.

Chia batch có một đánh đổi về nghiệp vụ: toàn bộ công việc không còn là một transaction nguyên tử duy nhất. Nếu tiến trình dừng giữa chừng, một phần dữ liệu đã được cập nhật. Cần thiết kế thao tác có thể chạy tiếp an toàn, ghi nhận tiến độ khi cần và bảo đảm mỗi batch không xử lý sai dữ liệu khi có transaction khác cùng hoạt động.

Nếu đặt toàn bộ vòng lặp trong một transaction lớn rồi chỉ COMMIT ở cuối, khóa có thể vẫn được giữ đến cuối vòng lặp. Khi đó, chia câu lệnh thành batch chưa chắc giảm được thời gian giữ khóa.

### 7.2. Làm cho câu truy vấn chọn đúng tập dữ liệu

Một điều kiện lọc thiếu chọn lọc có thể khiến SQL Server quét và khóa nhiều tài nguyên hơn cần thiết. Hãy:

- Kiểm tra execution plan để biết truy vấn đang seek hay scan và số dòng thực tế được đọc/cập nhật.
- Tạo hoặc điều chỉnh chỉ mục phù hợp với điều kiện lọc và thứ tự truy cập khi có lợi.
- Tránh cập nhật các dòng không cần thay đổi.
- Chọn tập khóa chính rõ ràng trước khi cập nhật hàng loạt nếu điều đó giúp giới hạn công việc.

Chỉ mục không phải giải pháp tự động: cập nhật một dòng có thể phải thay đổi nhiều chỉ mục, và chỉ mục bổ sung cũng làm tăng chi phí ghi. Hãy đo bằng workload đại diện trước khi giữ lại thay đổi.

### 7.3. Rút ngắn transaction

Hoàn tất công việc cần thiết rồi COMMIT hoặc ROLLBACK sớm. Không giữ transaction mở trong lúc chờ người dùng, gọi dịch vụ bên ngoài, xử lý tệp hoặc thực hiện công việc không liên quan đến database.

Transaction ngắn giúp khóa được giải phóng sớm hơn. Điều này không ngăn mọi lần lock escalation, nhưng giảm khoảng thời gian các transaction khác phải chờ khóa đã được gộp.

### 7.4. Cân nhắc row versioning cho workload đọc/ghi

Trong SQL Server, READ_COMMITTED_SNAPSHOT hoặc SNAPSHOT có thể cho phép một số truy vấn đọc lấy phiên bản dữ liệu thay vì chờ khóa S trên dữ liệu đang được ghi. Điều này thường giảm blocking giữa reader và writer.

Row versioning không loại bỏ khóa ghi và không giải quyết xung đột khi hai transaction cùng cập nhật dữ liệu. Nó cũng có chi phí lưu trữ và dọn dẹp row version. Chỉ bật sau khi hiểu tác động đến isolation, tempdb và hành vi ứng dụng.

### 7.5. Đánh giá gộp ở mức phân vùng

Với bảng phân vùng và workload có ranh giới dữ liệu rõ ràng, cấu hình lock escalation ở mức phân vùng có thể hạn chế việc một transaction ảnh hưởng đến toàn bảng. Cần xác nhận rằng các transaction thường hoạt động trên các phân vùng độc lập và kiểm tra nguy cơ deadlock khi chúng khóa nhiều phân vùng.

### 7.6. Thận trọng với lock hints và việc tắt escalation

Một số lock hint có thể thay đổi cách SQL Server chọn khóa, nhưng không phải hint nào cũng bảo đảm điều người viết truy vấn mong muốn.

- ROWLOCK yêu cầu ưu tiên khóa dòng trong những trường hợp phù hợp; nó **không phải cam kết ngăn lock escalation**.
- TABLOCK chủ động yêu cầu khóa bảng trong nhiều trường hợp, nên có thể làm phạm vi tranh chấp lớn hơn.
- Tắt escalation có thể khiến số lượng khóa nhỏ tiếp tục tăng, làm lock manager tiêu tốn nhiều bộ nhớ và trong trường hợp xấu có thể gây lỗi do thiếu tài nguyên.

Chỉ thay đổi cấu hình escalation sau khi đã chứng minh escalation là nguyên nhân của vấn đề, hiểu rõ mức tiêu thụ bộ nhớ và kiểm thử tải đồng thời. Không dùng ROWLOCK hoặc tắt escalation như một cách chữa blocking chung.

## 8. Quan sát và chẩn đoán

Khi hệ thống chậm, cần phân biệt ba câu hỏi:

1. Có sự kiện lock escalation hay không?
2. Session nào đang giữ khóa và session nào đang chờ?
3. Khóa đó có thực sự làm workload chậm hay chỉ xuất hiện mà không gây blocking đáng kể?

Với SQL Server, có thể kết hợp các công cụ sau:

| Công cụ | Dùng để |
|---|---|
| Extended Events, sự kiện **lock_escalation** | Ghi nhận thời điểm SQL Server thực hiện gộp khóa và thông tin liên quan |
| Extended Events, **blocked_process_report** | Thu thập thông tin về các session bị chặn khi cấu hình ngưỡng blocked process phù hợp |
| Extended Events, **xml_deadlock_report** | Thu thập đồ thị deadlock để tìm chu trình chờ |
| **sys.dm_tran_locks** | Quan sát các khóa hiện đang được giữ hoặc đang được yêu cầu |
| **sys.dm_exec_requests** | Xem session đang chạy, session chặn, wait type và tài nguyên đang chờ |
| **sys.dm_os_waiting_tasks** | Quan sát các task đang chờ, bao gồm chờ khóa |

Ví dụ xem các khóa hiện tại trong database:

~~~sql
SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status,
    resource_description
FROM sys.dm_tran_locks
WHERE resource_database_id = DB_ID();
~~~

Ví dụ tìm request đang bị session khác chặn:

~~~sql
SELECT
    session_id,
    blocking_session_id,
    wait_type,
    wait_time,
    wait_resource,
    status
FROM sys.dm_exec_requests
WHERE blocking_session_id <> 0;
~~~

Hai truy vấn DMV trên là ảnh chụp trạng thái tại thời điểm truy vấn; chúng không thay thế việc ghi sự kiện khi sự cố chỉ xảy ra thoáng qua. Extended Events phù hợp hơn khi cần xác định escalation đã xảy ra vào thời điểm nào. Khi đọc kết quả, hãy ghép session đang chờ với session giữ khóa, câu lệnh đang chạy và transaction mở của chúng.

Một sự kiện lock escalation đơn lẻ chưa đủ kết luận hệ thống đang gặp sự cố. Nếu không có transaction cạnh tranh, gộp khóa có thể chỉ giúp giảm chi phí quản lý. Ngược lại, blocking có thể xuất hiện mà không có escalation, chẳng hạn khi hai transaction khóa cùng dòng hoặc cùng vùng khóa chỉ mục.

## 9. Phân tích tình huống và lựa chọn biện pháp

| Dấu hiệu | Cách diễn giải | Hướng xử lý nên kiểm tra |
|---|---|---|
| Có escalation nhưng không có session chờ | Hệ quản trị đã giảm số lượng khóa; chưa có bằng chứng contention đáng kể | Theo dõi thêm dưới tải đồng thời thực tế |
| Escalation đi kèm nhiều session chờ khóa bảng | Phạm vi khóa rộng có thể là nguyên nhân blocking | Xác định transaction giữ khóa, cân nhắc batch và rút ngắn transaction |
| Không có escalation nhưng vẫn có LCK_M_* waits | Có thể là xung đột khóa dòng/trang, khóa phạm vi hoặc khóa khác | Kiểm tra resource, lock mode và câu lệnh của blocker |
| Một batch lớn chạy lâu và chặn nhiều request | Transaction có thời gian giữ khóa dài hoặc xử lý quá nhiều dữ liệu | Chia batch, tối ưu điều kiện lọc và kiểm tra index |
| Deadlock xuất hiện giữa các transaction nhiều bước | Có chu trình chờ, có thể liên quan đến thứ tự khóa hoặc phạm vi khóa | Đọc deadlock graph, thống nhất thứ tự truy cập và rút ngắn transaction |

Khi đánh giá biện pháp, nên đo ít nhất: thời gian hoàn thành batch, số dòng xử lý, số lần escalation, thời gian chờ khóa, số session bị chặn và throughput của workload cạnh tranh. Chỉ giảm số lần escalation chưa chắc làm hệ thống nhanh hơn nếu đổi lại là lượng khóa chi tiết quá lớn hoặc transaction giữ khóa lâu hơn.

## 10. Những điểm cần ghi nhớ

- Lock escalation thay nhiều khóa chi tiết bằng khóa có phạm vi rộng hơn để giảm chi phí quản lý khóa.
- SQL Server có thể gộp khóa dòng/trang lên bảng hoặc phân vùng; ngưỡng và hành vi này phụ thuộc điều kiện thực thi và bộ nhớ.
- Khóa rộng có thể chặn transaction thao tác trên những dòng khác nhau, từ đó giảm concurrency, throughput và tăng latency.
- Escalation có thể hữu ích cho thao tác hàng loạt; bản thân một sự kiện escalation không chứng minh có sự cố.
- Blocking không đồng nghĩa với deadlock. Deadlock chỉ xảy ra khi hình thành chu trình chờ.
- Chia batch chỉ giảm thời gian giữ khóa nếu mỗi batch thực sự kết thúc transaction và COMMIT.
- Chỉ mục phù hợp, transaction ngắn và row versioning có thể giảm một số dạng blocking, nhưng không loại bỏ mọi xung đột ghi.
- Luôn kiểm tra đúng cơ chế của DBMS đang sử dụng; không áp dụng ngưỡng SQL Server cho PostgreSQL, InnoDB hoặc Oracle.

Hiểu lock escalation giúp giải thích một hiện tượng dễ gây nhầm lẫn: hai transaction cập nhật các dòng khác nhau nhưng vẫn phải chờ nhau. Điều quyết định không chỉ là dòng dữ liệu có giao nhau hay không, mà còn là **phạm vi và chế độ khóa mà hệ quản trị đang giữ tại thời điểm đó**.

