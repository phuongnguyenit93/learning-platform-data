# Phiên bản hàng, định danh giao dịch và thông tin khả kiến

MVCC (Multi-Version Concurrency Control) cho phép cơ sở dữ liệu duy trì nhiều phiên bản của cùng một hàng trong một khoảng thời gian. Khi một giao dịch cập nhật dữ liệu, hệ quản trị có thể tạo phiên bản mới và giữ phiên bản cũ đủ lâu để những giao dịch đang đọc theo ảnh chụp dữ liệu trước đó tiếp tục nhìn thấy dữ liệu phù hợp.

Để chọn đúng phiên bản cho một truy vấn, DBMS cần biết phiên bản được tạo hoặc bị thay thế bởi giao dịch nào, giao dịch đó đã hoàn tất hay chưa, và giao dịch đọc đang nhìn vào trạng thái dữ liệu tại thời điểm nào. Các thông tin này thường được gọi chung là **metadata khả kiến (visibility metadata)**. Định danh giao dịch (transaction identifier, transaction ID hay TxID) là một thành phần quan trọng của metadata đó.

Các DBMS triển khai MVCC bằng cấu trúc nội bộ khác nhau. Bài học này trình bày mô hình chung trước, sau đó đối chiếu PostgreSQL, MySQL InnoDB, SQL Server và Oracle. Tên trường nội bộ hoặc quy tắc cụ thể của một hệ quản trị không phải là cú pháp hay bảo đảm chung của SQL.

## 1. Một hàng logic có thể có nhiều phiên bản

Ứng dụng thường nhìn một hàng như một thực thể có khóa chính ổn định. Ví dụ, tài khoản `account_id = 101` có số dư thay đổi qua thời gian:

| Thời điểm | account_id | balance |
|---|---:|---:|
| Ban đầu | 101 | 1.000.000 |
| Sau lần cập nhật A | 101 | 900.000 |
| Sau lần cập nhật B | 101 | 850.000 |

Về mặt nghiệp vụ, đây vẫn là tài khoản 101. Nhưng trong cơ chế MVCC, DBMS có thể biểu diễn các trạng thái này bằng những phiên bản hàng khác nhau:

```text
Hàng logic: Account(101)

Phiên bản V1: balance = 1.000.000
       |
       | được thay thế bởi giao dịch A
       v
Phiên bản V2: balance =   900.000
       |
       | được thay thế bởi giao dịch B
       v
Phiên bản V3: balance =   850.000
```

Một giao dịch đọc bắt đầu trước khi A commit có thể vẫn cần V1. Một giao dịch đọc bắt đầu sau khi A commit nhưng trước khi B commit có thể cần V2. Một giao dịch đọc mới sau khi B commit có thể nhìn thấy V3.

Điều này giải thích vì sao DBMS không thể xóa ngay phiên bản cũ mỗi khi có cập nhật. Một phiên bản không còn là trạng thái mới nhất vẫn có thể là trạng thái hợp lệ đối với một snapshot đang hoạt động.

**Phiên bản hàng** là một trạng thái cụ thể của hàng tại một thời điểm trong lịch sử giao dịch. Nó có thể được lưu thành một bản ghi vật lý riêng, được liên kết với undo record, hoặc được quản lý qua một cấu trúc version store. Ứng dụng thường chỉ thao tác với hàng logic; việc biểu diễn và truy vết các phiên bản thuộc về DBMS.

## 2. Định danh giao dịch dùng để làm gì?

DBMS gán cho giao dịch một định danh để phân biệt giao dịch đó với những giao dịch khác. Định danh này giúp hệ thống xác định ai đã tạo phiên bản, ai đã cập nhật hoặc xóa nó, giao dịch có nằm trong snapshot đang xét hay không, và kết quả giao dịch đã được commit hay rollback.

Ví dụ minh họa:

| Giao dịch | TxID giả định | Công việc |
|---|---:|---|
| T1 | 500 | Đọc tài khoản 101 |
| T2 | 501 | Cập nhật tài khoản 101 thành 900.000 |
| T3 | 502 | Đọc tài khoản 101 sau khi T2 commit |

TxID `501` cho phép DBMS liên hệ phiên bản mới với giao dịch T2. Tuy nhiên, chỉ biết TxID chưa đủ để quyết định phiên bản có khả kiến hay không. DBMS còn cần biết T2 đã commit trước hay sau snapshot của giao dịch đọc, hoặc T2 còn đang hoạt động khi snapshot được tạo.

### TxID khác với các loại định danh khác

| Loại định danh | Mục đích | Ví dụ |
|---|---|---|
| Khóa chính (primary key) | Xác định một thực thể nghiệp vụ | `account_id = 101` |
| Session / connection ID | Xác định phiên kết nối hoặc luồng làm việc với DBMS | Một phiên ứng dụng đang mở |
| Transaction ID (TxID) | Xác định một giao dịch trong cơ chế quản lý giao dịch và phiên bản | T2 có TxID 501 trong ví dụ |
| Query / statement ID | Theo dõi một câu lệnh hoặc kế hoạch thực thi | Một câu `UPDATE` trong T2 |
| Commit sequence / timestamp | Biểu diễn thứ tự hoặc mốc commit theo cơ chế của DBMS | SCN hoặc sequence nội bộ |

Một session có thể thực hiện nhiều giao dịch nối tiếp nhau. Một giao dịch có thể thực hiện nhiều câu lệnh. Khóa chính của hàng tồn tại qua nhiều lần cập nhật, trong khi TxID của giao dịch tạo phiên bản thay đổi theo từng giao dịch. Không nên dùng TxID nội bộ làm mã nghiệp vụ hoặc lưu nó như một định danh bền vững của hàng.

TxID cũng không nhất thiết là số tăng liên tục, duy nhất vĩnh viễn trên mọi bản sao, hoặc có cùng định dạng giữa các DBMS. Một số hệ thống dùng số giao dịch có thể quay vòng; một số hệ thống dùng sequence number hoặc SCN để xác định thứ tự. Phạm vi duy nhất và vòng đời của định danh phụ thuộc vào hệ quản trị.

## 3. Metadata khả kiến của một phiên bản hàng

Để quyết định một phiên bản có được đọc hay không, DBMS thường cần một số loại thông tin sau. Tên và vị trí lưu trữ của chúng tùy hệ quản trị.

| Thông tin | Ý nghĩa |
|---|---|
| Transaction tạo phiên bản | Giao dịch đã chèn hoặc tạo ra trạng thái hàng này |
| Transaction thay thế/xóa phiên bản | Giao dịch cập nhật hoặc xóa trạng thái cũ |
| Trạng thái giao dịch | Giao dịch đang chạy, đã commit, đã rollback hoặc ở trạng thái liên quan khác |
| Snapshot / read view | Tập quy tắc và mốc giao dịch dùng để xác định dữ liệu mà lần đọc được phép nhìn thấy |
| Liên kết phiên bản | Con trỏ hoặc thông tin undo để tìm phiên bản trước đó |
| Thứ tự câu lệnh | Thông tin bổ sung để phân biệt các thay đổi trong cùng giao dịch khi DBMS cần |

Metadata không nhất thiết nằm toàn bộ trong chính hàng dữ liệu. Trạng thái commit có thể được lưu trong cấu trúc quản lý giao dịch riêng; nội dung phiên bản cũ có thể nằm trong undo log hoặc version store; snapshot có thể được giữ trong bộ nhớ giao dịch.

Điểm cốt lõi là DBMS phải kết hợp thông tin về phiên bản với trạng thái giao dịch và snapshot. Một trường ghi TxID của người tạo phiên bản không tự nói lên phiên bản đã commit hoặc đang khả kiến.

## 4. Snapshot quyết định phiên bản nào được nhìn thấy

Snapshot (ảnh chụp dữ liệu) mô tả trạng thái giao dịch mà một lần đọc dùng làm mốc. Tùy mức cô lập và DBMS, snapshot có thể được tạo cho từng câu lệnh hoặc được giữ xuyên suốt giao dịch.

Giả sử có ba giao dịch:

1. T1 bắt đầu đọc và tạo snapshot S.
2. T2 cập nhật tài khoản 101 từ 1.000.000 thành 900.000.
3. T2 commit sau khi S đã được tạo.
4. T1 tiếp tục đọc tài khoản 101.

Nếu quy tắc snapshot của T1 yêu cầu nhìn dữ liệu đã commit trước thời điểm S, T1 vẫn nhìn thấy phiên bản 1.000.000. Giao dịch T3 bắt đầu một snapshot mới sau khi T2 commit có thể nhìn thấy 900.000.

```text
Thời gian ---------------------------------------------------->

T1: bắt đầu đọc -- tạo snapshot S ------------------- đọc hàng
                         |
T2:                      bắt đầu -- UPDATE -- COMMIT

T1 nhìn theo S: phiên bản cũ
T3 tạo snapshot sau COMMIT của T2: phiên bản mới
```

Snapshot không nhất thiết là bản sao vật lý của toàn bộ cơ sở dữ liệu. Nó thường là một tập mốc hoặc quy tắc để DBMS xác định phiên bản nào hợp lệ. Khi truy vấn đọc một hàng, DBMS có thể kiểm tra phiên bản hiện tại rồi lần theo chuỗi phiên bản hoặc undo record để tìm trạng thái phù hợp với snapshot.

### 4.1. Quy tắc khả kiến ở mức khái niệm

Với một phiên bản V được tạo bởi giao dịch C và sau đó có thể bị thay thế bởi giao dịch D, có thể suy luận theo các trường hợp khái quát:

- Nếu C đã commit trước mốc snapshot và phiên bản chưa bị một giao dịch đã commit trước snapshot thay thế, V có thể được nhìn thấy.
- Nếu C còn đang hoạt động khi snapshot được tạo, V thường chưa được nhìn thấy bởi giao dịch khác đang đọc theo snapshot đó.
- Nếu C rollback, phiên bản do C tạo không trở thành dữ liệu đã commit để giao dịch khác nhìn thấy.
- Nếu D chỉ mới cập nhật hoặc xóa nhưng chưa commit, giao dịch đọc theo snapshot cũ thường vẫn có thể nhìn thấy V.
- Nếu D đã commit trước snapshot, V có thể đã hết hiệu lực đối với snapshot đó; DBMS sẽ chọn phiên bản mới hơn phù hợp.
- Giao dịch thường có quy tắc riêng để nhìn thấy thay đổi do chính nó thực hiện, kể cả khi những thay đổi đó chưa commit.

Đây là mô hình giải thích, không phải thuật toán kiểm tra đầy đủ cho mọi DBMS. Hệ quản trị có thể phải xét tập giao dịch đang hoạt động, thứ tự commit, câu lệnh trong cùng giao dịch, khóa khoảng, thao tác đặc biệt và loại truy vấn. Không nên triển khai quy tắc khả kiến chỉ bằng cách so sánh hai con số TxID.

### 4.2. Mức cô lập ảnh hưởng đến thời điểm lấy snapshot

Ở mức cô lập kiểu `READ COMMITTED`, một DBMS dùng MVCC có thể tạo snapshot mới cho từng câu lệnh đọc. Hai câu `SELECT` trong cùng một giao dịch vì thế có thể nhìn thấy hai trạng thái đã commit khác nhau.

Ở mức cô lập kiểu `REPEATABLE READ` hoặc `SNAPSHOT`, tùy DBMS, snapshot có thể được giữ lâu hơn để các lần đọc lặp lại nhìn cùng một trạng thái dữ liệu. `SERIALIZABLE` có thể bổ sung kiểm tra xung đột hoặc cơ chế khóa để bảo vệ tính tương đương với thực thi tuần tự.

Tên mức cô lập giống nhau giữa các sản phẩm không bảo đảm thuật toán nội bộ hoàn toàn giống nhau. Cần xem tài liệu DBMS để biết snapshot được tạo khi bắt đầu giao dịch, ở câu lệnh đầu tiên hay theo quy tắc khác.

## 5. Vòng đời của các phiên bản hàng

Một chuỗi phiên bản thường trải qua các giai đoạn sau:

1. **Chèn:** giao dịch tạo phiên bản đầu tiên của hàng.
2. **Commit hoặc rollback:** nếu commit, phiên bản có thể trở thành dữ liệu nhìn thấy theo snapshot phù hợp; nếu rollback, thay đổi bị hủy theo quy tắc của DBMS.
3. **Cập nhật:** DBMS tạo trạng thái mới và lưu đủ thông tin để những snapshot cũ có thể tái dựng trạng thái trước đó.
4. **Xóa:** DBMS có thể đánh dấu phiên bản đã bị xóa hoặc tạo thông tin phiên bản xóa, trong khi snapshot cũ vẫn cần nhìn thấy hàng.
5. **Thu hồi:** khi không còn snapshot đang hoạt động nào cần phiên bản cũ, DBMS có thể dọn dẹp dữ liệu phiên bản hoặc undo tương ứng.

```text
INSERT V1 -- COMMIT
               |
               v
          UPDATE tạo V2 -- COMMIT
               |
               v
          DELETE / đánh dấu xóa -- COMMIT
               |
               v
      Không còn snapshot cần V1, V2
               |
               v
       VACUUM / PURGE / dọn version store
       (tên cơ chế phụ thuộc DBMS)
```

Thời điểm có thể thu hồi một phiên bản không chỉ phụ thuộc vào việc giao dịch cập nhật đã commit. Một giao dịch đọc lâu dài có thể vẫn cần phiên bản cũ. Vì vậy, DBMS phải theo dõi những snapshot còn hiệu lực trước khi dọn dữ liệu lịch sử.

### 5.1. Vì sao giao dịch đọc lâu có thể làm tăng dung lượng?

Giả sử T1 mở snapshot và đọc dữ liệu, sau đó giữ giao dịch trong nhiều phút hoặc nhiều giờ. Trong lúc đó, T2, T3 và các giao dịch khác liên tục cập nhật cùng bảng. DBMS có thể phải giữ các phiên bản cũ vì T1 vẫn có khả năng cần chúng.

Hệ quả có thể gồm:

- Nhiều phiên bản cũ hoặc undo record chưa thể thu hồi.
- Tăng dung lượng lưu trữ hoặc version store.
- Tăng công việc của vacuum, purge hoặc tác vụ dọn dẹp tương ứng.
- Tăng độ trễ truy vấn hoặc tạo áp lực lên bộ nhớ và I/O.

Đây là một lý do thực tế để tránh mở giao dịch đọc quá lâu, giữ transaction trong khi chờ người dùng thao tác, hoặc thực hiện công việc mạng bên ngoài. Ranh giới giao dịch nên ngắn và rõ ràng, phù hợp với yêu cầu nhất quán của nghiệp vụ.

## 6. PostgreSQL: `xmin`, `xmax` và `ctid`

PostgreSQL lưu metadata MVCC trong header của tuple (bản ghi vật lý). Một số system column giúp quan sát các thông tin này:

- `xmin`: transaction ID gắn với giao dịch đã tạo phiên bản tuple.
- `xmax`: transaction ID hoặc thông tin giao dịch liên quan đến việc xóa, thay thế hay khóa tuple.
- `ctid`: vị trí vật lý của tuple trong bảng, biểu diễn theo cặp số block và offset.

Ví dụ truy vấn quan sát:

```sql
SELECT
    account_id,
    balance,
    xmin,
    xmax,
    ctid
FROM account
WHERE account_id = 101;
```

Các cột này phục vụ quan sát nội bộ và chẩn đoán. Chúng không phải định danh nghiệp vụ ổn định để ứng dụng lưu làm khóa chính hoặc dùng làm liên kết lâu dài.

### 6.1. Ý nghĩa và giới hạn của `xmin`

`xmin` cho biết phiên bản tuple được tạo bởi giao dịch nào. Nếu một hàng được cập nhật, PostgreSQL thường tạo tuple phiên bản mới; tuple mới có `xmin` gắn với giao dịch thực hiện cập nhật. Tuple cũ vẫn có thể tồn tại để phục vụ snapshot cũ cho đến khi được dọn dẹp.

Một giá trị `xmin` không đủ để kết luận phiên bản đã commit. PostgreSQL phải xét trạng thái giao dịch và snapshot. Trạng thái commit được quản lý trong cấu trúc transaction status riêng; một số thông tin trạng thái có thể được lưu đệm trong tuple header bằng hint bits để tăng tốc kiểm tra.

### 6.2. `xmax` không phải lúc nào cũng có nghĩa hàng đã bị xóa

`xmax` thường được gắn với giao dịch xóa hoặc cập nhật phiên bản tuple. Tuy nhiên, nó cũng có thể chứa thông tin liên quan đến khóa hàng, bao gồm trường hợp dùng MultiXact khi có nhiều giao dịch cùng tham gia khóa tuple. Giá trị đặc biệt hoặc các bit trong tuple header cũng ảnh hưởng đến cách diễn giải.

Vì vậy, không nên nhìn thấy `xmax` khác giá trị rỗng rồi kết luận ngay rằng hàng đã bị xóa. Cần xét trạng thái giao dịch, các cờ trong tuple header và ngữ cảnh của phiên bản.

### 6.3. `ctid` và chuỗi phiên bản

Khi PostgreSQL cập nhật một tuple, phiên bản mới thường được lưu ở vị trí vật lý khác. `ctid` của tuple cũ có thể liên hệ đến vị trí tuple mới trong một số trạng thái cập nhật, nhưng `ctid` chỉ là địa chỉ vật lý hiện tại của tuple. Nó có thể thay đổi sau cập nhật hoặc các thao tác như `VACUUM FULL` và không được dùng làm định danh bền vững của hàng.

### 6.4. Transaction ID có thể quay vòng

PostgreSQL sử dụng XID có không gian số hữu hạn cho nhiều thông tin MVCC truyền thống. Vì giá trị có thể quay vòng, so sánh XID không đơn giản như so sánh số nguyên tăng mãi. PostgreSQL có cơ chế chống transaction ID wraparound và đóng băng phiên bản cũ (freezing) để bảo đảm tính đúng đắn của khả kiến.

Đây cũng là lý do không nên tự suy ra tuổi đời tuyệt đối hoặc thứ tự commit chỉ từ giá trị `xmin` được in ra. Cần dùng các hàm, view và công cụ chẩn đoán đúng phiên bản PostgreSQL.

## 7. MySQL InnoDB: `DB_TRX_ID`, `DB_ROLL_PTR` và undo log

InnoDB quản lý phiên bản hàng bằng thông tin giao dịch trong bản ghi và các undo record. Với bản ghi clustered index, những trường hệ thống ẩn thường được mô tả như sau:

- `DB_TRX_ID`: định danh giao dịch gần nhất đã chèn hoặc thay đổi bản ghi.
- `DB_ROLL_PTR`: con trỏ đến undo record dùng để tìm trạng thái trước đó.
- `DB_ROW_ID`: định danh hàng nội bộ mà InnoDB tự tạo khi bảng không khai báo `PRIMARY KEY` và cũng không có khóa `UNIQUE NOT NULL` phù hợp để làm clustered index.

Khi một giao dịch cập nhật hàng, InnoDB ghi thông tin cần thiết vào undo log. Một consistent read có thể lần theo `DB_ROLL_PTR` và undo record để tái dựng phiên bản phù hợp với read view của nó.

### 7.1. Read view

Read view ghi nhận trạng thái các giao dịch tại thời điểm tạo snapshot. Về khái niệm, nó giúp InnoDB xác định giao dịch nào đã hoàn tất trước mốc đọc, giao dịch nào vẫn đang hoạt động và phiên bản nào cần được dựng lại từ undo log.

Các trường nội bộ thường được mô tả trong thuật toán read view gồm mốc giới hạn giao dịch và danh sách giao dịch đang hoạt động. Tên trường và chi tiết triển khai có thể khác theo phiên bản. Ứng dụng không nên tự đọc hoặc phụ thuộc vào các trường nội bộ này để quyết định dữ liệu nghiệp vụ.

### 7.2. Undo log và purge

Undo log có hai vai trò quan trọng: hỗ trợ rollback và cung cấp dữ liệu cũ để consistent read tái dựng phiên bản trước. Khi không còn giao dịch hoặc read view nào cần một undo record, InnoDB có thể thu hồi nó thông qua quá trình purge.

Nếu có read view tồn tại quá lâu, purge có thể không dọn được các undo record phía sau mốc mà snapshot cũ còn cần. History list có thể tăng và làm tăng áp lực lưu trữ, I/O hoặc thời gian phục hồi phiên bản.

### 7.3. Consistent read và locking read

Một `SELECT` thông thường trong InnoDB ở chế độ consistent read thường đọc theo read view và có thể không chặn giao dịch đang cập nhật hàng theo cách đọc khóa truyền thống. Ngược lại, các câu lệnh locking read như `SELECT ... FOR UPDATE` hoặc `SELECT ... FOR SHARE` yêu cầu khóa và có quy tắc đọc hiện tại (current read) phù hợp với mục đích điều phối ghi.

Do đó, khi phân tích kết quả đọc, cần biết câu lệnh là consistent read hay locking read. Không phải mọi câu `SELECT` đều dùng cùng một đường thực thi khả kiến.

## 8. SQL Server: row versioning và version store

SQL Server hỗ trợ row versioning cho các chế độ như `READ COMMITTED SNAPSHOT` và `SNAPSHOT ISOLATION`. Khi một hàng được sửa trong điều kiện cần tạo phiên bản, hệ thống giữ thông tin phiên bản trước và liên kết từ bản ghi hiện tại đến phiên bản cũ.

Một hàng có thể chứa thông tin liên kết phiên bản, trong đó có một tag 14 byte trong các trường hợp row versioning liên quan. Phiên bản cũ được lưu trong version store. Theo cấu hình và kiến trúc, version store có thể nằm trong `tempdb` hoặc Persistent Version Store trong cơ sở dữ liệu người dùng khi Accelerated Database Recovery (ADR) được bật.

SQL Server sử dụng các sequence number và thông tin giao dịch để xác định phiên bản phù hợp với snapshot. Với `READ_COMMITTED_SNAPSHOT`, mỗi câu lệnh đọc ở mức `READ COMMITTED` có thể nhìn một snapshot nhất quán tại thời điểm câu lệnh bắt đầu. Với `SNAPSHOT`, các lần đọc trong giao dịch sử dụng snapshot theo quy tắc của mức cô lập này.

### Đừng nhầm row versioning với kiểu dữ liệu `rowversion`

SQL Server có kiểu dữ liệu `rowversion` (tên cũ thường gặp là `timestamp`). Đây là giá trị nhị phân tự tăng được tạo khi hàng có cột `rowversion` được thêm hoặc cập nhật. Nó hữu ích cho kiểm soát cập nhật lạc quan (optimistic concurrency), ví dụ phát hiện hàng đã thay đổi kể từ lần đọc của ứng dụng.

Kiểu dữ liệu `rowversion` **không phải** phiên bản hàng MVCC, không chứa ảnh chụp dữ liệu cũ, và không phải TxID của giao dịch. Cơ chế row versioning và kiểu dữ liệu `rowversion` là hai tính năng khác nhau dù tên gọi dễ gây nhầm lẫn.

## 9. Oracle: SCN và undo data

Oracle dùng System Change Number (SCN) để biểu diễn mốc nhất quán theo thời gian logic của cơ sở dữ liệu. Khi một truy vấn cần đọc dữ liệu tại một SCN, Oracle có thể dùng undo data để tái dựng phiên bản block hoặc hàng phù hợp với mốc đó.

Trong mô hình này, SCN của snapshot đóng vai trò xác định trạng thái dữ liệu cần nhìn thấy. Thông tin giao dịch và undo record giúp DBMS xác định thay đổi nào đã xảy ra trước hoặc sau mốc đọc và dựng lại dữ liệu cũ khi cần.

Không nên cố ánh xạ trực tiếp `xmin`/`xmax` của PostgreSQL sang một cặp cột tương tự trong Oracle. Oracle có cấu trúc transaction table, undo segment và cơ chế nhất quán đọc riêng. Các hệ quản trị có thể giải quyết cùng một yêu cầu MVCC bằng metadata và thuật toán khác nhau.

## 10. So sánh cách biểu diễn giữa các DBMS

| DBMS | Định danh / mốc quan trọng | Cách tìm phiên bản cũ | Điểm cần lưu ý |
|---|---|---|---|
| PostgreSQL | `xmin`, `xmax`, XID và snapshot | Các tuple phiên bản cùng thông tin trạng thái giao dịch | `xmax` có nhiều cách dùng; XID có cơ chế wraparound và freezing |
| MySQL InnoDB | `DB_TRX_ID` và read view | `DB_ROLL_PTR` lần theo undo log | Phân biệt consistent read với locking/current read; purge thu hồi undo cũ |
| SQL Server | Sequence number và metadata row versioning | Version store (`tempdb` hoặc Persistent Version Store khi ADR) | Kiểu dữ liệu `rowversion` không phải MVCC version |
| Oracle | SCN và metadata giao dịch | Undo data dùng để dựng consistent read | SCN là mốc nhất quán; cấu trúc nội bộ khác PostgreSQL và InnoDB |

Bảng trên chỉ nêu những khái niệm tiêu biểu. Cấu trúc nội bộ có thể thay đổi theo phiên bản, cấu hình và loại thao tác. Khi chẩn đoán production, hãy dùng tài liệu và công cụ dành cho đúng phiên bản DBMS đang chạy.

## 11. MVCC vẫn cần khóa và cơ chế điều phối ghi

MVCC giúp nhiều giao dịch đọc các phiên bản phù hợp mà không phải chờ mọi cập nhật hoàn tất. Tuy nhiên, MVCC không loại bỏ toàn bộ khóa.

Hai giao dịch cùng cập nhật một hàng vẫn có thể phải chờ hoặc xung đột. Các thao tác `SELECT ... FOR UPDATE`, cập nhật, xóa, thay đổi cấu trúc và một số truy vấn bảo vệ điều kiện vẫn có thể cần khóa. DBMS cũng có thể dùng khóa hoặc kiểm tra xung đột để ngăn các lịch thực thi vi phạm mức cô lập.

Ví dụ, T1 và T2 cùng đọc số dư 1.000.000 theo snapshot rồi đều muốn trừ 100.000. Nếu cả hai chỉ ghi dựa trên giá trị cũ mà không có cơ chế điều phối phù hợp, kết quả có thể mất một cập nhật. DBMS phải xử lý xung đột ghi bằng khóa, kiểm tra phiên bản hoặc cơ chế tương đương. Snapshot nhất quán cho đọc không tự bảo đảm mọi thao tác ghi đồng thời đều an toàn.

MVCC cũng không có nghĩa giao dịch luôn nhìn thấy phiên bản mới nhất. Nó nhìn thấy phiên bản hợp lệ theo snapshot và quy tắc cô lập. Một giao dịch đọc lâu có thể cố ý nhìn dữ liệu cũ hơn dữ liệu hiện tại đã commit.

## 12. Cách quan sát và chẩn đoán

Khi cần hiểu vì sao một truy vấn nhìn thấy một giá trị, hãy trả lời lần lượt các câu hỏi sau:

1. Truy vấn đang chạy trong giao dịch nào và mức cô lập nào?
2. Snapshot/read view được tạo vào thời điểm nào và có được giữ qua nhiều câu lệnh không?
3. Phiên bản hàng hiện tại được tạo bởi giao dịch nào?
4. Giao dịch tạo phiên bản đã commit, đang hoạt động hay rollback tại mốc snapshot?
5. Phiên bản có bị một giao dịch khác cập nhật hoặc xóa không? Giao dịch đó đã commit trước snapshot chưa?
6. DBMS tìm phiên bản cũ bằng tuple chain, undo log hay version store?
7. Phiên bản cũ còn được snapshot nào sử dụng nên chưa thể dọn dẹp không?

Các hướng quan sát theo hệ quản trị:

- **PostgreSQL:** có thể quan sát `xmin`, `xmax`, `ctid` trên hàng; kết hợp thông tin giao dịch, `pg_stat_activity`, `pg_locks` và thống kê vacuum để hiểu trạng thái và áp lực dọn tuple. Không kết luận khả kiến chỉ từ một cột system column.
- **MySQL InnoDB:** xem transaction đang hoạt động, thông tin khóa và trạng thái history/purge bằng các công cụ hệ thống phù hợp với phiên bản; phân biệt consistent read và locking read.
- **SQL Server:** xem cấu hình `READ_COMMITTED_SNAPSHOT`, `ALLOW_SNAPSHOT_ISOLATION`, giao dịch đang hoạt động và mức sử dụng version store; khi dùng ADR cần xem Persistent Version Store.
- **Oracle:** xem SCN, giao dịch đang hoạt động và thông tin undo; lỗi snapshot quá cũ có thể liên quan đến việc undo cần thiết không còn khả dụng.

Các truy vấn chẩn đoán và tên view cụ thể có thể thay đổi theo phiên bản, quyền truy cập và cấu hình. Không chạy câu lệnh dọn dẹp hoặc thay đổi cấu hình chỉ dựa trên một chỉ số đơn lẻ; cần xác định giao dịch hoặc snapshot đang giữ lịch sử và đánh giá tác động đến ứng dụng.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Một hàng logic chỉ có một phiên bản vật lý. | MVCC có thể giữ nhiều phiên bản để các snapshot khác nhau đọc đúng trạng thái. |
| TxID là khóa chính của hàng. | TxID xác định giao dịch; khóa chính xác định thực thể nghiệp vụ. |
| Biết `xmin` là biết hàng đã commit. | Phải xét trạng thái giao dịch và snapshot; `xmin` chỉ gắn phiên bản với giao dịch tạo nó. |
| `xmax` khác rỗng luôn có nghĩa hàng đã bị xóa. | Trong PostgreSQL, `xmax` còn có thể liên quan đến khóa hoặc MultiXact và phải xét tuple header. |
| Snapshot là bản sao vật lý của toàn bộ database. | Snapshot thường là mốc và tập quy tắc để chọn phiên bản hợp lệ. |
| Giao dịch cập nhật commit thì phiên bản cũ được xóa ngay. | Phiên bản cũ chỉ được thu hồi khi không còn snapshot cần nó và cơ chế dọn dẹp cho phép. |
| MVCC loại bỏ khóa. | MVCC giảm một số xung đột đọc/ghi nhưng vẫn cần điều phối ghi, khóa và kiểm tra xung đột. |
| SQL Server `rowversion` là phiên bản MVCC. | `rowversion` là giá trị nhị phân tự tăng cho kiểm soát cập nhật lạc quan; version store là cơ chế khác. |
| TxID luôn tăng mãi và có thể so sánh như số nguyên. | Một số DBMS có không gian định danh hữu hạn hoặc cơ chế sequence riêng; cần tuân theo quy tắc của DBMS. |

## 14. Ví dụ tổng hợp: hai snapshot đọc cùng một hàng

Giả sử ban đầu `Account(101).balance = 1.000.000`. T1 và T2 bắt đầu ở các thời điểm khác nhau:

| Bước | Hoạt động | Phiên bản liên quan |
|---:|---|---|
| 1 | T1 tạo snapshot S1 | V1 = 1.000.000 |
| 2 | T2 cập nhật thành 900.000 | Tạo V2 |
| 3 | T2 commit | V2 được commit sau khi S1 đã tồn tại |
| 4 | T3 tạo snapshot S2 | S2 được tạo sau commit của T2 |
| 5 | T1 đọc tài khoản 101 | S1 chọn V1 |
| 6 | T3 đọc tài khoản 101 | S2 chọn V2 |

```text
                 T2 tạo V2 và commit
                         |
                         v
Thời gian ----+----------+------------------------------>
              |
T1            +-- Snapshot S1 ------------------ đọc V1
                         |
T3                       +-- Snapshot S2 ------ đọc V2

V1 = 1.000.000
V2 =   900.000
```

T1 không đọc sai dữ liệu. Nó đọc đúng phiên bản mà snapshot S1 cho phép nhìn thấy. T3 cũng đọc đúng vì snapshot S2 được tạo sau khi T2 commit. Cả hai kết quả đều nhất quán với quy tắc MVCC của snapshot tương ứng.

Sau khi T1 kết thúc và không còn snapshot nào cần V1, DBMS có thể thu hồi phiên bản cũ thông qua vacuum, purge, version-store cleanup hoặc cơ chế tương ứng. Việc dọn dẹp diễn ra theo chính sách và chu kỳ của DBMS, không nhất thiết ngay tại thời điểm T1 commit.

Khi đọc metadata MVCC, hãy luôn kết nối ba yếu tố: **phiên bản hàng**, **giao dịch tạo/thay thế phiên bản**, và **snapshot của giao dịch đọc**. TxID cho biết phiên bản liên quan đến giao dịch nào; trạng thái giao dịch và snapshot mới quyết định phiên bản đó có khả kiến hay không.
