# Phạm vi khóa: hàng, trang, bảng và đối tượng cơ sở dữ liệu

Trong một hệ quản trị cơ sở dữ liệu (DBMS), khóa (lock) là cơ chế điều phối quyền truy cập đồng thời vào dữ liệu hoặc cấu trúc dữ liệu. Khi một giao dịch đọc, cập nhật, xóa hoặc thay đổi cấu trúc, DBMS có thể đặt khóa lên tài nguyên liên quan để giao dịch khác không thực hiện thao tác xung đột trước khi giao dịch hiện tại hoàn tất.

**Phạm vi khóa (lock granularity)** cho biết một khóa bảo vệ đơn vị tài nguyên lớn đến mức nào. Đơn vị đó có thể là một hàng, một trang lưu trữ, cả bảng, một phân vùng, một chỉ mục, metadata của đối tượng hoặc thậm chí toàn bộ cơ sở dữ liệu. Phạm vi khóa ảnh hưởng trực tiếp đến khả năng chạy đồng thời, chi phí quản lý khóa và mức độ tranh chấp giữa các giao dịch.

Các DBMS không nhất thiết hỗ trợ cùng một tập phạm vi khóa hoặc triển khai chúng giống nhau. Vì vậy, các cấp hàng, trang và bảng trong bài này là mô hình khái niệm phổ biến; khi phân tích một hệ thống cụ thể, cần đối chiếu tài liệu của DBMS đó.

## 1. Vì sao phạm vi khóa quan trọng?

Giả sử bảng `Account` có hai hàng:

| account_id | balance |
|---:|---:|
| 101 | 1.000.000 |
| 202 | 2.000.000 |

Giao dịch A cập nhật tài khoản 101, trong khi giao dịch B cập nhật tài khoản 202. Nếu DBMS có thể khóa riêng từng hàng, hai giao dịch thường có thể thực hiện đồng thời vì chúng tác động đến hai tài nguyên khác nhau. Nếu DBMS khóa toàn bộ bảng theo chế độ độc quyền, giao dịch B có thể phải chờ dù nó không sửa cùng hàng với giao dịch A.

Phạm vi nhỏ thường cho phép nhiều giao dịch làm việc song song hơn, nhưng DBMS phải tạo, lưu trữ, tra cứu và giải phóng nhiều mục khóa hơn. Phạm vi lớn giảm số lượng mục khóa cần quản lý, nhưng có thể khiến các giao dịch không liên quan đến cùng dữ liệu vẫn phải chờ nhau.

Có thể nhìn thấy sự đánh đổi này qua hai mục tiêu:

- **Tăng tính đồng thời:** khóa càng sát với phần dữ liệu thực sự được sử dụng thì càng ít giao dịch bị chặn không cần thiết.
- **Giảm chi phí quản lý:** khóa trên một vùng dữ liệu lớn có thể thay thế nhiều khóa nhỏ, giúp giảm bộ nhớ và công việc của bộ quản lý khóa.

Không có một phạm vi luôn tốt nhất. DBMS lựa chọn hoặc chuyển đổi phạm vi dựa trên loại thao tác, kế hoạch thực thi, chỉ mục, cấu hình, tải hệ thống và chính sách khóa của nó.

## 2. Các cấp phạm vi khóa thường gặp

Một mô hình phân cấp đơn giản có thể biểu diễn như sau:

```text
Cơ sở dữ liệu
└── Lược đồ / đối tượng
    ├── Bảng hoặc phân vùng
    │   ├── Trang dữ liệu hoặc trang chỉ mục
    │   │   └── Hàng / bản ghi / khóa chỉ mục
    │   └── ...
    ├── Chỉ mục
    └── Đối tượng và metadata khác
```

Đây là sơ đồ khái niệm, không phải cây cấu trúc bắt buộc của mọi DBMS. Một hệ quản trị có thể khóa trực tiếp khóa chỉ mục, phân vùng hoặc đối tượng mà không biểu diễn tất cả các cấp ở giữa. Một số hệ quản trị cũng không dùng khóa trang cho các thao tác dữ liệu thông thường.

Phạm vi và chế độ khóa là hai khái niệm khác nhau:

- **Phạm vi** trả lời: khóa đang bảo vệ tài nguyên nào và rộng đến đâu?
- **Chế độ khóa (lock mode)** trả lời: giao dịch được phép làm gì với tài nguyên đó và giao dịch khác có thể truy cập theo cách nào?

Ví dụ, khóa chia sẻ (Shared, `S`) thường cho phép nhiều giao dịch cùng đọc một tài nguyên, còn khóa độc quyền (Exclusive, `X`) thường ngăn giao dịch khác đọc hoặc ghi theo cách xung đột. Một khóa `S` có thể đặt ở cấp hàng hoặc cấp bảng; một khóa `X` cũng có thể tồn tại ở nhiều cấp. Vì thế, chỉ biết chế độ `X` chưa đủ để kết luận khóa đang chặn một hàng hay toàn bộ bảng.

## 3. Khóa cấp hàng (row-level lock)

Khóa cấp hàng bảo vệ một hàng cụ thể trong bảng. Đây là phạm vi nhỏ, phù hợp với những thao tác chỉ cần đọc hoặc thay đổi một số ít hàng.

Ví dụ, hai phiên làm việc cập nhật hai tài khoản khác nhau:

```sql
-- Giao dịch A
BEGIN TRANSACTION;
UPDATE Account
SET balance = balance - 100000
WHERE account_id = 101;
-- COMMIT hoặc ROLLBACK sau khi hoàn tất nghiệp vụ
```

```sql
-- Giao dịch B
BEGIN TRANSACTION;
UPDATE Account
SET balance = balance + 200000
WHERE account_id = 202;
-- COMMIT hoặc ROLLBACK sau khi hoàn tất nghiệp vụ
```

Nếu DBMS dùng khóa độc quyền riêng cho từng hàng và hai câu lệnh tìm thấy hai hàng khác nhau, chúng có thể cập nhật đồng thời. Cả hai giao dịch vẫn có thể giữ thêm khóa ở cấp cao hơn để thông báo rằng chúng đang khóa tài nguyên bên dưới; điều đó không đồng nghĩa với việc toàn bộ bảng đã bị khóa độc quyền.

Khóa cấp hàng có các đặc điểm sau:

- **Ưu điểm:** hạn chế phạm vi xung đột, thường cho phép nhiều giao dịch sửa các hàng khác nhau trong cùng bảng.
- **Chi phí:** một câu lệnh tác động đến hàng nghìn hàng có thể cần rất nhiều mục khóa, làm tăng bộ nhớ và công việc của lock manager.
- **Giới hạn:** khóa hàng không đảm bảo chỉ một bản ghi vật lý đơn giản bị ảnh hưởng. Với bảng có chỉ mục, DBMS có thể khóa bản ghi hoặc khóa chỉ mục tương ứng; một thao tác có thể cần khóa nhiều tài nguyên.

Khóa hàng cũng không tự giải quyết mọi vấn đề về truy vấn theo điều kiện. Chẳng hạn, một giao dịch kiểm tra rằng không có đơn hàng nào trong một khoảng thời gian rồi tạo đơn mới. Nếu DBMS chỉ khóa các hàng đang tồn tại, một giao dịch khác có thể chèn hàng mới thỏa điều kiện đó. Hiện tượng này liên quan đến phantom read. Ở mức cô lập phù hợp, DBMS có thể dùng khóa khoảng khóa (key-range lock), khóa predicate hoặc cơ chế tương đương để bảo vệ cả khoảng giá trị, tùy hệ quản trị.

Do đó, cần phân biệt khóa một hàng hiện có với khóa một điều kiện hoặc khoảng khóa có thể bao gồm những hàng sẽ được chèn trong tương lai.

## 4. Khóa cấp trang (page-level lock)

Trang (page) là một đơn vị lưu trữ mà DBMS dùng để tổ chức dữ liệu hoặc các mục của chỉ mục. Một trang thường chứa nhiều hàng hoặc nhiều mục chỉ mục. Kích thước trang và cách tổ chức phụ thuộc vào DBMS.

Khóa cấp trang bảo vệ cả trang. Nếu một trang chứa nhiều hàng, khóa trang có thể ảnh hưởng đến các thao tác trên nhiều hàng cùng nằm trong trang đó, kể cả khi các giao dịch không định cập nhật cùng một hàng.

Ví dụ, trang P chứa các hàng 101, 102 và 103. Giao dịch A cần sửa hàng 101, còn giao dịch B cần sửa hàng 103. Nếu cả hai thao tác cần khóa độc quyền trên cùng trang P, chúng có thể phải chờ nhau. Với khóa riêng từng hàng, hai thao tác có khả năng chạy đồng thời.

Khóa trang nằm giữa khóa hàng và khóa bảng về độ rộng:

- **Ít mục khóa hơn khóa hàng:** một khóa có thể đại diện cho cả nhóm hàng trên cùng trang.
- **Phạm vi hẹp hơn khóa bảng:** các trang khác trong bảng vẫn có thể được truy cập đồng thời nếu chế độ khóa tương thích.
- **Có thể tăng tranh chấp cục bộ:** các hàng không liên quan về nghiệp vụ nhưng nằm chung một trang vẫn có thể xung đột.

Khóa trang không được mọi DBMS sử dụng giống nhau. SQL Server có thể dùng khóa trang trong một số tình huống và cung cấp các gợi ý khóa liên quan. InnoDB của MySQL chủ yếu khóa bản ghi chỉ mục, khoảng khóa và các tài nguyên liên quan ở cấp logic; thao tác DML thông thường không được mô tả đơn giản là khóa cả trang. PostgreSQL cũng có các khóa hàng và khóa bảng cho điều phối giao dịch, trong khi bảo vệ trang trong bộ nhớ thường liên quan đến latch. Vì vậy, không nên suy luận rằng mọi DBMS đều có khóa trang cho mỗi lần cập nhật.

### Khóa trang và latch trang không giống nhau

Một nhầm lẫn thường gặp là xem page lock và page latch như một khái niệm:

| Tiêu chí | Khóa trang (page lock) | Chốt trang (page latch) |
|---|---|---|
| Mục đích | Điều phối truy cập giao dịch và bảo đảm quy tắc đồng thời | Bảo vệ cấu trúc trang trong bộ nhớ khi DBMS đang thao tác nội bộ |
| Thời gian giữ | Có thể tồn tại đến khi giao dịch kết thúc, tùy chế độ và DBMS | Thường rất ngắn, trong một thao tác nội bộ |
| Phạm vi ý nghĩa | Quyền truy cập logic của các giao dịch | Tính toàn vẹn vật lý của cấu trúc bộ nhớ |
| Quan sát | Thường xuất hiện trong thông tin khóa và chờ khóa | Thường xuất hiện trong thống kê chờ latch riêng |

Một trang có thể cần latch trong lúc DBMS thay đổi cấu trúc của nó, đồng thời các giao dịch có thể giữ những khóa logic trên hàng hoặc khóa chỉ mục nằm trong trang đó. Hai cơ chế giải quyết hai vấn đề khác nhau.

## 5. Khóa cấp bảng (table-level lock)

Khóa cấp bảng bảo vệ toàn bộ bảng như một đối tượng. Phạm vi này rộng hơn khóa hàng hoặc khóa trang, nên có thể ảnh hưởng đến nhiều thao tác dù chúng truy cập các hàng khác nhau.

Khóa bảng có thể hữu ích trong các trường hợp như:

- Một thao tác hàng loạt tác động đến phần lớn hoặc toàn bộ bảng.
- Một quy trình bảo trì cần kiểm soát truy cập đồng thời vào bảng.
- Một thao tác yêu cầu chế độ khóa rộng theo thiết kế của DBMS.
- Một ứng dụng chủ động khóa bảng để thực hiện chuỗi thao tác cần tính loại trừ ở phạm vi bảng.

Tác động của khóa bảng phụ thuộc vào **chế độ khóa**. Khóa chia sẻ cấp bảng có thể cho phép nhiều giao dịch đọc cùng lúc, trong khi khóa độc quyền cấp bảng thường chặn các thao tác đọc hoặc ghi xung đột trên bảng. Vì vậy, câu nói “đã khóa bảng” chưa đủ để xác định chính xác giao dịch khác bị chặn đến mức nào.

Ví dụ minh họa cú pháp SQL Server:

```sql
-- Gợi ý yêu cầu khóa độc quyền ở cấp bảng
BEGIN TRANSACTION;

SELECT *
FROM dbo.Account WITH (TABLOCKX, HOLDLOCK);

-- Thực hiện phần công việc cần thiết
COMMIT TRANSACTION;
```

`TABLOCKX` yêu cầu khóa độc quyền cấp bảng; `HOLDLOCK` yêu cầu giữ ngữ nghĩa khóa tương đương mức cô lập `SERIALIZABLE` cho tham chiếu bảng trong phạm vi câu lệnh/giao dịch tương ứng. Đây là cú pháp riêng của SQL Server, không phải SQL chuẩn có thể dùng nguyên trạng trên mọi DBMS. Việc dùng khóa bảng cũng có thể làm giảm mạnh tính đồng thời, nên cần có lý do nghiệp vụ và kiểm chứng tác động trước khi áp dụng.

### Khóa ý định (intent lock)

Trong hệ thống hỗ trợ nhiều cấp khóa, DBMS cần biết một giao dịch đang khóa tài nguyên con nào trước khi cấp một khóa rộng ở cấp cha. Khóa ý định (intent lock) ghi nhận rằng giao dịch dự định hoặc đang giữ khóa ở cấp thấp hơn.

Một số chế độ thường gặp trong SQL Server là:

- `IS` (Intent Shared): giao dịch dự định hoặc đang giữ khóa chia sẻ ở cấp thấp hơn.
- `IX` (Intent Exclusive): giao dịch dự định hoặc đang giữ khóa độc quyền ở cấp thấp hơn.
- `SIX` (Shared with Intent Exclusive): giao dịch giữ khóa chia sẻ ở cấp hiện tại và có ý định giữ khóa độc quyền ở một số tài nguyên con.

Ví dụ, khi cập nhật một hàng trong bảng, DBMS có thể giữ khóa `IX` ở cấp bảng và khóa `X` ở cấp hàng. Khóa `IX` giúp DBMS nhận ra bảng có giao dịch đang thay đổi dữ liệu bên dưới. Khi một giao dịch khác muốn lấy khóa độc quyền toàn bảng, DBMS có thể kiểm tra khóa ý định ở cấp bảng để xác định xung đột mà không phải dò từng hàng.

Khóa ý định không có nghĩa toàn bộ bảng đang bị khóa độc quyền. Nó là tín hiệu về các khóa ở cấp thấp hơn. Các DBMS có thể dùng tên chế độ và quy tắc tương thích khác nhau, nên cần đọc đúng tài liệu của hệ quản trị đang sử dụng.

## 6. Khóa trên các đối tượng cơ sở dữ liệu

Ngoài hàng, trang và bảng, DBMS còn quản lý khóa trên những đối tượng khác. “Đối tượng cơ sở dữ liệu” là khái niệm rộng; phạm vi cụ thể phụ thuộc vào kiến trúc của hệ quản trị.

### 6.1. Chỉ mục (index)

Chỉ mục là cấu trúc dữ liệu giúp tìm kiếm và sắp xếp bản ghi. Khi chèn, cập nhật hoặc xóa dữ liệu, DBMS có thể phải thay đổi cả hàng dữ liệu lẫn một hoặc nhiều mục chỉ mục. Vì thế, giao dịch có thể giữ khóa trên khóa chỉ mục hoặc cấu trúc chỉ mục, ngay cả khi câu lệnh SQL chỉ nhắc đến bảng.

Trong SQL Server, tài nguyên khóa có thể được thể hiện ở cấp `KEY` hoặc `OBJECT`. Trong InnoDB, khóa bản ghi gắn với các bản ghi chỉ mục; việc dùng chỉ mục nào và điều kiện truy vấn có thể ảnh hưởng đến tập khóa được giữ. Điều này giải thích vì sao hai câu lệnh cùng cập nhật một bảng nhưng có kế hoạch truy vấn hoặc chỉ mục khác nhau có thể tạo ra mẫu khóa và mức tranh chấp khác nhau.

### 6.2. Phân vùng (partition)

Một bảng lớn có thể được chia thành nhiều phân vùng theo khoảng ngày, vùng địa lý hoặc một khóa phân vùng khác. Một số DBMS hỗ trợ khóa hoặc thao tác ở cấp phân vùng, giúp giới hạn ảnh hưởng vào phần dữ liệu cần xử lý.

Ví dụ, một bảng lịch sử đơn hàng được chia theo tháng. Quy trình lưu trữ dữ liệu cũ có thể thao tác trên phân vùng của một tháng thay vì toàn bộ bảng, nếu DBMS và thiết kế bảng hỗ trợ cách làm đó. Khả năng khóa riêng phân vùng, chuyển phân vùng hoặc bảo trì phân vùng là tính năng cụ thể của từng DBMS.

### 6.3. Lược đồ, metadata và cấu trúc bảng

Thay đổi cấu trúc như `ALTER TABLE`, tạo hoặc xóa chỉ mục, đổi tên đối tượng hay thay đổi metadata có thể cần khóa để tránh việc một truy vấn đang sử dụng cấu trúc bị thay đổi giữa chừng.

Một số hệ quản trị có các khóa metadata hoặc khóa lược đồ riêng. Trong SQL Server, chẳng hạn, có các chế độ khóa lược đồ như `Sch-S` (Schema Stability) và `Sch-M` (Schema Modification). Khóa lược đồ bảo vệ việc sử dụng hoặc thay đổi định nghĩa đối tượng; nó không đồng nghĩa với khóa hàng thông thường.

Vì vậy, một câu lệnh đọc dữ liệu có thể phải chờ thao tác DDL do xung đột ở cấp metadata hoặc lược đồ, dù hai thao tác không cùng cập nhật một hàng dữ liệu.

### 6.4. Cấp cơ sở dữ liệu (database-level lock)

Khóa cấp cơ sở dữ liệu có phạm vi rất rộng. Nó có thể xuất hiện trong các hoạt động quản trị, bảo trì, thay đổi trạng thái hoặc thao tác cần điều phối ở phạm vi toàn cơ sở dữ liệu. Với DML thông thường, DBMS thường tìm cách dùng phạm vi hẹp hơn để tránh chặn mọi hoạt động không liên quan.

Không nên hiểu rằng mọi giao dịch đều khóa độc quyền toàn cơ sở dữ liệu khi bắt đầu. DBMS có thể giữ một số khóa cấp cơ sở dữ liệu ở chế độ tương thích để xác nhận quyền truy cập hoặc bảo vệ metadata, đồng thời đặt khóa dữ liệu ở cấp bảng, hàng hay tài nguyên khác.

## 7. Nhiều cấp khóa có thể cùng tồn tại

Một giao dịch không nhất thiết chỉ giữ một khóa ở một cấp. Khi cập nhật một hàng, nó có thể giữ khóa trên hàng hoặc khóa chỉ mục, cùng với các khóa ý định ở những cấp cha. Cơ chế này giúp DBMS quản lý phân cấp tài nguyên.

Ví dụ khái niệm:

```text
Transaction A
  Database: khóa điều phối phù hợp
    Table Account: IX (ý định cập nhật tài nguyên con)
      Page P: tùy DBMS và thao tác
        Row / Index key 101: X (độc quyền)
```

Đây không phải danh sách khóa bắt buộc của mọi DBMS. Một hệ thống có thể bỏ qua cấp trang, dùng khóa `KEY` thay cho cách biểu diễn trực tiếp bằng hàng, hoặc quản lý khóa trên phân vùng theo một cấu trúc khác.

Khi một giao dịch yêu cầu khóa rộng hơn, DBMS phải xét cả các khóa đang tồn tại ở cấp con và các khóa ý định ở cấp cha. Quy tắc tương thích khóa quyết định yêu cầu mới được cấp ngay hay phải chờ.

### Nâng cấp khóa (lock escalation)

Nếu một giao dịch giữ quá nhiều khóa nhỏ, chi phí quản lý có thể tăng đáng kể. Một số DBMS có cơ chế nâng cấp khóa (lock escalation): thay nhiều khóa cấp hàng hoặc cấp trang bằng một khóa ở cấp rộng hơn, thường là cấp bảng hoặc phân vùng.

Ví dụ, một giao dịch cập nhật hàng chục nghìn hàng trong cùng bảng có thể bắt đầu với nhiều khóa nhỏ. Khi đạt điều kiện nâng cấp do DBMS quy định, hệ thống có thể thay chúng bằng một khóa rộng hơn. Việc này giúp giảm số lượng mục khóa, nhưng có thể khiến giao dịch khác phải chờ dù chúng chỉ cần truy cập một số hàng không liên quan.

Các điểm cần nhớ:

- Ngưỡng và điều kiện nâng cấp khóa khác nhau theo DBMS, phiên bản, cấu hình và áp lực bộ nhớ.
- Không phải mọi hệ quản trị đều có cơ chế nâng cấp giống nhau; có hệ quản trị quản lý khóa theo cách khác.
- Nâng cấp khóa là quyết định quản lý tài nguyên của DBMS, không nhất thiết là dấu hiệu truy vấn viết sai.
- Có thể giảm nguy cơ giữ quá nhiều khóa bằng cách chia công việc lớn thành các giao dịch nhỏ hợp lý, nhưng chỉ khi việc chia nhỏ vẫn bảo đảm yêu cầu nhất quán nghiệp vụ.

## 8. DBMS lựa chọn phạm vi khóa như thế nào?

Ứng dụng thường mô tả **điều cần làm** bằng câu lệnh SQL và ranh giới giao dịch. DBMS quyết định **tài nguyên nào cần khóa**, chế độ khóa, thời gian giữ và phạm vi khóa theo quy tắc của nó.

Các yếu tố thường ảnh hưởng đến lựa chọn đó gồm:

1. **Loại thao tác:** đọc, cập nhật, xóa, chèn hoặc thay đổi cấu trúc có nhu cầu khóa khác nhau.
2. **Số hàng bị tác động:** thao tác trên một hàng có thể dùng khóa hẹp; thao tác hàng loạt có thể tạo ra nhiều khóa hoặc chuyển sang phạm vi rộng.
3. **Điều kiện truy vấn và chỉ mục:** chỉ mục được chọn quyết định DBMS phải duyệt và bảo vệ những tài nguyên nào.
4. **Mức cô lập giao dịch:** mức cô lập ảnh hưởng đến loại xung đột cần ngăn chặn và thời gian giữ khóa. Một số DBMS còn dùng MVCC hoặc cơ chế đọc phiên bản để giảm nhu cầu khóa chặn khi đọc.
5. **Tải và tài nguyên hệ thống:** số lượng khóa, bộ nhớ dành cho khóa và chính sách nội bộ có thể ảnh hưởng đến việc chuyển phạm vi.
6. **Yêu cầu đặc thù của DBMS:** cú pháp gợi ý khóa, khả năng khóa phân vùng và chính sách nâng cấp không giống nhau giữa các sản phẩm.

Một số DBMS cho phép người dùng đưa ra gợi ý phạm vi khóa. Ví dụ SQL Server có các gợi ý `ROWLOCK`, `PAGLOCK`, `TABLOCK` và `TABLOCKX`. Các gợi ý này là cơ chế riêng của SQL Server. Chúng có thể tác động đến cách DBMS chọn khóa, nhưng không nên được xem là cam kết phổ quát rằng hệ thống sẽ luôn giữ đúng một phạm vi trong mọi tình huống. Những cơ chế như nâng cấp khóa và yêu cầu của thao tác vẫn cần được xem xét.

Chỉ nên ép phạm vi khóa khi đã xác định được vấn đề cụ thể, hiểu tác động đến các giao dịch khác và đo kiểm dưới tải đại diện. Thêm `ROWLOCK` không tự động làm truy vấn nhanh hơn; nó có thể làm tăng số lượng khóa và chi phí quản lý. Dùng khóa bảng cũng không tự động làm thao tác hàng loạt hiệu quả hơn nếu nó tạo ra điểm nghẽn cho phần còn lại của ứng dụng.

## 9. Phạm vi khóa và mức cô lập giao dịch

Phạm vi khóa thường bị nhầm với mức cô lập giao dịch (transaction isolation level), nhưng hai khái niệm trả lời hai câu hỏi khác nhau:

- **Mức cô lập** xác định những hiện tượng đọc/ghi nào giao dịch phải tránh, chẳng hạn dirty read, non-repeatable read hoặc phantom read.
- **Phạm vi khóa** mô tả đơn vị tài nguyên mà một khóa cụ thể bảo vệ.

Mức cô lập có thể ảnh hưởng đến loại khóa, thời gian giữ khóa và việc DBMS có cần khóa khoảng giá trị hay không. Tuy nhiên, không thể suy ra trực tiếp rằng một mức cô lập luôn tương ứng với khóa hàng hoặc khóa bảng.

Ví dụ, một DBMS có thể dùng khóa chia sẻ để bảo vệ dữ liệu đọc ở một mức cô lập, trong khi DBMS khác dùng MVCC để trả về phiên bản dữ liệu phù hợp mà không chặn người ghi theo cùng cách. Ngay trong một DBMS, thao tác DML và thao tác DDL cũng có thể dùng các cơ chế khóa khác nhau.

Khi điều tra một vấn đề đồng thời, cần xem đồng thời mức cô lập, chế độ khóa, tài nguyên bị khóa và thời gian giữ khóa. Chỉ thay đổi mức cô lập hoặc chỉ ép phạm vi khóa mà không hiểu nguyên nhân có thể tạo ra vấn đề mới.

## 10. Cách phân tích một tình huống tranh chấp khóa

Khi một giao dịch phải chờ, hãy lần lượt xác định:

1. **Giao dịch đang chờ là giao dịch nào?** Xác định câu lệnh, thời điểm bắt đầu và thời gian chờ.
2. **Tài nguyên nào đang bị khóa?** Đó là hàng, khóa chỉ mục, trang, bảng, phân vùng hay metadata?
3. **Chế độ khóa của hai phía là gì?** Kiểm tra khóa được yêu cầu và khóa đang được giữ có xung đột hay không.
4. **Phạm vi có rộng hơn dữ liệu ứng dụng dự kiến không?** Ví dụ, truy vấn cập nhật một hàng nhưng đang chờ khóa bảng hoặc khóa metadata.
5. **Vì sao DBMS chọn phạm vi đó?** Xem kế hoạch thực thi, chỉ mục, số hàng bị tác động, mức cô lập và khả năng nâng cấp khóa.
6. **Giao dịch giữ khóa trong bao lâu?** Một giao dịch mở quá lâu hoặc chờ thao tác bên ngoài trong khi vẫn giữ khóa có thể kéo dài tranh chấp.

Thông tin chẩn đoán cụ thể khác nhau theo hệ quản trị. SQL Server cung cấp DMV và công cụ theo dõi khóa/chờ; PostgreSQL có các view như `pg_locks` kết hợp với thông tin phiên; MySQL/InnoDB cung cấp thông tin khóa và giao dịch trong các bảng hệ thống tương ứng với phiên bản. Khi sử dụng các công cụ này, hãy đọc đúng tài liệu phiên bản đang chạy và đối chiếu cả giao dịch chặn lẫn giao dịch bị chặn.

Một tình huống điển hình là truy vấn cập nhật nhiều hàng nhưng thiếu chỉ mục phù hợp. DBMS có thể phải quét nhiều dữ liệu, giữ khóa trên nhiều tài nguyên và làm tăng khả năng xung đột. Cải thiện điều kiện truy vấn hoặc chỉ mục có thể giảm số tài nguyên phải truy cập và thời gian giữ khóa. Tuy nhiên, việc thêm chỉ mục cũng làm tăng công việc khi chèn, cập nhật và xóa, nên cần đánh giá cả đọc lẫn ghi.

## 11. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| Khóa hàng nghĩa là giao dịch chỉ có một khóa. | Một giao dịch có thể khóa nhiều hàng, nhiều khóa chỉ mục và giữ khóa ý định ở cấp cao hơn. |
| Hai giao dịch sửa hai hàng khác nhau thì chắc chắn không chặn nhau. | Chúng vẫn có thể xung đột do khóa trang, khóa bảng, khóa chỉ mục, khóa metadata hoặc tài nguyên khác. |
| Khóa bảng luôn chặn mọi thao tác đọc. | Việc có chặn hay không phụ thuộc chế độ khóa và quy tắc tương thích của DBMS. |
| Mọi DBMS đều khóa trang khi cập nhật hàng. | Cách quản lý khóa trang khác nhau; có hệ quản trị dùng khóa bản ghi chỉ mục và cơ chế bảo vệ trang riêng. |
| Page lock và page latch là một. | Lock điều phối truy cập giao dịch; latch bảo vệ cấu trúc bộ nhớ trong thao tác nội bộ ngắn. |
| Chọn `ROWLOCK` luôn cải thiện hiệu năng. | Nhiều khóa nhỏ có thể tăng chi phí quản lý; gợi ý khóa cần được đánh giá theo tình huống và DBMS. |
| Mức cô lập cao hơn đồng nghĩa khóa rộng hơn. | Mức cô lập ảnh hưởng đến quy tắc đồng thời, nhưng phạm vi thực tế phụ thuộc DBMS và cơ chế thực thi. |
| Khóa cơ sở dữ liệu nghĩa là mọi giao dịch đều khóa độc quyền toàn DB. | Khóa cấp cơ sở dữ liệu có nhiều mục đích và chế độ; DML thông thường thường dùng thêm các phạm vi dữ liệu hẹp hơn. |

## 12. So sánh nhanh các phạm vi

| Phạm vi | Đơn vị được bảo vệ | Lợi ích chính | Đánh đổi chính |
|---|---|---|---|
| Hàng | Một hàng hoặc tài nguyên bản ghi tương ứng | Tính đồng thời cao khi giao dịch sửa các hàng khác nhau | Nhiều mục khóa khi thao tác trên nhiều hàng |
| Trang | Một trang chứa nhiều hàng hoặc mục chỉ mục | Ít mục khóa hơn so với khóa từng hàng | Các thao tác trên những hàng cùng trang có thể tranh chấp |
| Bảng | Toàn bộ bảng | Quản lý đơn giản hơn cho thao tác phạm vi lớn | Có thể chặn nhiều giao dịch không cùng sửa một hàng |
| Phân vùng | Một phần dữ liệu thuộc bảng được phân vùng | Giới hạn ảnh hưởng vào một phần bảng | Phụ thuộc tính năng phân vùng và cách khóa của DBMS |
| Đối tượng / metadata | Chỉ mục, lược đồ, định nghĩa hoặc đối tượng cụ thể | Bảo vệ cấu trúc và tính nhất quán khi truy cập/thay đổi đối tượng | Có thể làm DDL hoặc truy vấn phụ thuộc đối tượng phải chờ |
| Cơ sở dữ liệu | Tài nguyên hoặc trạng thái ở phạm vi toàn DB | Phù hợp với một số hoạt động quản trị và điều phối rộng | Phạm vi ảnh hưởng rất lớn nếu chế độ khóa không tương thích |

Khi thiết kế và vận hành ứng dụng, hãy bắt đầu bằng việc xác định câu lệnh thực sự truy cập những tài nguyên nào, giao dịch giữ khóa trong bao lâu và DBMS đang dùng chế độ khóa nào. Sau đó mới cân nhắc thay đổi chỉ mục, chia nhỏ giao dịch, điều chỉnh mức cô lập hoặc gợi ý phạm vi khóa. Cách tiếp cận dựa trên tài nguyên và bằng chứng chờ khóa giúp xử lý đúng nguyên nhân tranh chấp, thay vì chỉ thay đổi phạm vi khóa theo cảm tính.
