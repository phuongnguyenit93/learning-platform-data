# Giao dịch là gì và vì sao cơ sở dữ liệu cần xử lý đồng thời?

## 1. Bài toán bắt đầu từ một thao tác nghiệp vụ

Trong ứng dụng, một thao tác mà người dùng xem là **một việc duy nhất** thường cần nhiều lần đọc hoặc ghi dữ liệu. Khi chuyển tiền, hệ thống phải trừ tiền ở tài khoản nguồn, cộng tiền vào tài khoản đích và ghi nhận kết quả. Khi đặt vé, hệ thống phải xác nhận chỗ còn trống, giữ hoặc bán chỗ và tạo đơn hàng. Khi tạo đơn mua sắm, hệ thống có thể phải tạo đơn, tạo các dòng hàng và cập nhật tồn kho.

Nếu chỉ có một câu lệnh thành công còn các câu lệnh khác thất bại, cơ sở dữ liệu có thể rơi vào trạng thái không hợp lệ. Nếu hai người dùng cùng thao tác trên dữ liệu liên quan, việc từng câu lệnh đều chạy thành công cũng **chưa đủ** để bảo đảm kết quả nghiệp vụ đúng.

Hai nhu cầu xuất hiện đồng thời:

- **Giao dịch (transaction):** gom các thay đổi liên quan vào một đơn vị công việc có quy tắc hoàn tất hoặc hủy bỏ.
- **Xử lý đồng thời (concurrency control):** điều phối nhiều giao dịch đang cùng hoạt động để dữ liệu vẫn đáp ứng các ràng buộc nghiệp vụ.

Ví dụ, với hai tài khoản A và B:

| Thời điểm | Số dư A | Số dư B | Tổng tiền |
| --- | ---: | ---: | ---: |
| Ban đầu | 1.000.000 | 200.000 | 1.200.000 |
| Sau khi chuyển 300.000 từ A sang B | 700.000 | 500.000 | 1.200.000 |

Nếu hệ thống trừ 300.000 ở A rồi gặp lỗi trước khi cộng vào B, tổng tiền chỉ còn 900.000. Một giao dịch giúp hai thay đổi này cùng hoàn tất hoặc cùng được hủy bỏ. Nhưng nếu hai lệnh chuyển tiền **cùng lúc** trừ tiền từ A, ta còn phải giải quyết câu hỏi khác: mỗi lệnh có nhìn thấy và xử lý đúng ảnh hưởng của lệnh kia hay không?

## 2. Giao dịch là gì?

**Giao dịch cơ sở dữ liệu** là một đơn vị thực thi logic gồm một hoặc nhiều thao tác đọc/ghi, được hệ quản trị cơ sở dữ liệu (DBMS) quản lý theo các bảo đảm giao dịch mà hệ đó hỗ trợ.

Một vòng đời cơ bản:

1. **Bắt đầu** giao dịch, tường minh bằng lệnh như `BEGIN` hoặc ngầm định theo cơ chế của kết nối.
2. **Thực hiện** các câu lệnh đọc/ghi dữ liệu.
3. **Hoàn tất bằng `COMMIT`** để chấp nhận các thay đổi, hoặc **hủy bằng `ROLLBACK`** để bỏ những thay đổi chưa được chốt trong giao dịch.
4. Khi phát sinh lỗi, xung đột hoặc deadlock, DBMS có thể buộc giao dịch hủy; ứng dụng cần xử lý và có thể thử lại theo quy tắc phù hợp.

Ví dụ SQL mang tính minh họa:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 300000
WHERE id = 101;

UPDATE accounts
SET balance = balance + 300000
WHERE id = 202;

COMMIT;
```

Các câu lệnh nằm trong cùng một giao dịch trên cùng kết nối. Nếu ứng dụng phát hiện một bước không hợp lệ, nó cần `ROLLBACK` thay vì `COMMIT`. Đoạn SQL này mới diễn tả **ranh giới giao dịch**; triển khai thực tế còn phải kiểm tra tài khoản tồn tại, số dư đủ và số dòng được cập nhật (xem mục 9).

### 2.1. Giao dịch khác gì với một câu SQL?

Một câu `UPDATE` đơn lẻ thường cũng được DBMS thực hiện trong một giao dịch, đặc biệt khi chế độ **autocommit** đang bật. Tuy nhiên, nhiều câu SQL chạy liên tiếp trong autocommit thường thuộc **nhiều giao dịch độc lập**, nên thành công của câu đầu không phụ thuộc vào thành công của câu sau.

| Trường hợp | Điều xảy ra |
| --- | --- |
| `UPDATE A` thành công và tự commit, `UPDATE B` thất bại | Thay đổi ở A có thể đã được chốt; không thể hoàn tác bằng rollback của câu B. |
| `BEGIN` → `UPDATE A` → `UPDATE B` → `ROLLBACK` | Các thay đổi chưa commit của cả hai câu trong giao dịch bị hủy. |
| `BEGIN` → `UPDATE A` → `UPDATE B` → `COMMIT` | Hai thay đổi được chấp nhận như một đơn vị giao dịch. |

Một giao dịch **không nhất thiết tương ứng một yêu cầu HTTP** hoặc một hàm trong mã nguồn. Ranh giới thực tế do ứng dụng và DBMS thiết lập. Giao dịch cũng không tự bao phủ email, API của đối tác hay hệ thống thanh toán khác chỉ vì chúng được gọi trong cùng một hàm.

### 2.2. “Thành công” có nhiều lớp nghĩa

- **Câu lệnh thực thi thành công:** DBMS chấp nhận câu lệnh và thực hiện nó, nhưng có thể không cập nhật dòng nào.
- **Giao dịch commit thành công:** DBMS xác nhận việc chốt giao dịch theo cam kết của cấu hình đang dùng.
- **Nghiệp vụ thành công:** toàn bộ điều kiện cần thiết, chẳng hạn có đủ tiền, người nhận tồn tại và yêu cầu không bị xử lý trùng, đều được đáp ứng.

Vì vậy, kết quả `UPDATE ... WHERE id = ?` trả về **0 dòng bị ảnh hưởng** có thể là lỗi nghiệp vụ, ngay cả khi câu SQL không báo lỗi.

## 3. Bốn thuộc tính ACID

ACID là cách diễn đạt những bảo đảm nền tảng thường được kỳ vọng ở giao dịch quan hệ. Mỗi thuộc tính giải quyết một loại rủi ro khác nhau.

### 3.1. Atomicity — Tính nguyên tử

Các thay đổi của giao dịch được xử lý như một đơn vị **tất cả hoặc không có gì** về mặt commit. Không để tình huống một phần thay đổi được chốt trong khi phần còn lại của cùng giao dịch bị bỏ.

Trong ví dụ chuyển tiền, nếu bước cộng tiền không thể hoàn tất, giao dịch phải rollback thay đổi trừ tiền chưa commit. Atomicity không nói rằng những bước bên trong phải chạy đồng thời trong một khoảnh khắc, mà nói về kết quả cuối cùng khi giao dịch được chấp nhận hoặc hủy.

### 3.2. Consistency — Tính nhất quán

Một giao dịch hợp lệ phải đưa dữ liệu từ trạng thái đáp ứng các quy tắc sang một trạng thái cũng đáp ứng các quy tắc đó. Các quy tắc có thể gồm:

- Ràng buộc DBMS: khóa chính, khóa ngoại, `UNIQUE`, `CHECK`, `NOT NULL`.
- Bất biến nghiệp vụ: tồn kho không âm, số tiền không bị tạo ra hoặc mất đi trong một chuyển khoản nội bộ, mỗi chỗ ngồi chỉ có một người sở hữu hợp lệ.

**DBMS không thể tự suy ra mọi quy tắc nghiệp vụ.** Atomicity không tự khiến phép chuyển tiền hợp lệ nếu mã nguồn trừ sai số tiền hoặc chuyển đến tài khoản không tồn tại. Ứng dụng phải kiểm tra điều kiện và dùng ràng buộc thích hợp; cơ chế đồng thời phải bảo vệ các điều kiện ấy trước giao dịch khác.

“Consistency” trong ACID cũng không đồng nghĩa hoàn toàn với các khái niệm “strong consistency” hay “eventual consistency” khi bàn về hệ thống phân tán.

### 3.3. Isolation — Tính cô lập

Khi nhiều giao dịch chạy chồng lấn, giao dịch này không được quan sát hoặc gây ảnh hưởng lên giao dịch kia theo những cách vượt quá **mức cô lập (isolation level)** đã chọn.

Mức cô lập càng thấp thường cho phép nhiều lịch thực thi hơn, nhưng ứng dụng phải cân nhắc thêm hiện tượng bất thường. Mức cao nhất theo nghĩa **serializable** đòi hỏi kết quả các giao dịch đã commit tương đương một thứ tự thực thi tuần tự hợp lệ; điều đó **không có nghĩa DBMS buộc phải chạy từng giao dịch một**.

Isolation là trọng tâm khi nghiên cứu xử lý đồng thời.

### 3.4. Durability — Tính bền vững

Sau khi `COMMIT` được xác nhận, những thay đổi đã chốt phải tồn tại qua các sự cố mà cam kết bền vững và cấu hình DBMS bảo đảm. Hệ thống thường sử dụng nhật ký ghi trước (*write-ahead log*), ghi bền vững và cơ chế phục hồi để đạt điều này.

Cần phân biệt: **commit thành công** không tự bảo đảm dữ liệu đã xuất hiện ở mọi bản sao đọc (*read replica*) hoặc tại mọi hệ thống bên ngoài ngay lập tức. Đồng bộ bản sao, cấu hình ghi bền và cơ chế khôi phục ảnh hưởng đến phạm vi cam kết thực tế.

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Atomicity | Nếu một bước lỗi thì các bước còn lại ra sao? | Trừ tiền rồi cộng tiền phải cùng commit hoặc cùng rollback. |
| Consistency | Kết quả có đáp ứng ràng buộc dữ liệu/nghiệp vụ không? | Không bán vượt số lượng hàng có sẵn. |
| Isolation | Hai giao dịch tác động nhau thế nào khi chồng lấn? | Hai đơn hàng không cùng “giành” một vé cuối. |
| Durability | Dữ liệu sau commit có sống sót qua sự cố không? | Đơn hàng đã chốt vẫn còn sau khi hệ thống phục hồi. |

## 4. Vì sao cơ sở dữ liệu phải xử lý đồng thời?

Hệ thống thực tế phục vụ nhiều người dùng, dịch vụ và tác vụ nền. Trong cùng một khoảng thời gian có thể có hàng trăm yêu cầu xem số dư, thanh toán, cập nhật tồn kho và lập báo cáo. Kể cả khi ứng dụng dùng nhiều máy chủ, các thao tác cuối cùng vẫn có thể cùng đọc hoặc ghi một tập bản ghi.

**Đồng thời (concurrency)** nghĩa là các công việc có tiến trình thực thi chồng lấn và có thể xen kẽ các bước. **Song song (parallelism)** nghĩa là các bước thực sự thực thi cùng thời điểm trên nhiều tài nguyên xử lý. Một hệ thống một lõi CPU vẫn có thể xử lý đồng thời nhờ chuyển đổi giữa các công việc; một DBMS nhiều lõi có thể vừa đồng thời vừa song song.

DBMS cho phép đồng thời vì những lợi ích quan trọng:

- **Thông lượng:** xử lý được nhiều giao dịch trong một đơn vị thời gian.
- **Độ trễ và mức sử dụng tài nguyên:** trong lúc một truy vấn chờ I/O hoặc khóa, truy vấn độc lập khác có thể tiến triển.
- **Khả năng phục vụ nhiều người dùng:** không phải xếp mọi yêu cầu của cả hệ thống thành một hàng tuần tự.
- **Khả năng mở rộng:** những giao dịch trên dữ liệu độc lập thường có thể tiến hành với ít cản trở hơn những giao dịch cạnh tranh cùng bản ghi.

Tuy nhiên, thứ tự xen kẽ có thể làm thay đổi kết quả. DBMS cần cân bằng **khả năng tiến triển của các giao dịch** với **tính đúng đắn của dữ liệu**.

### 4.1. Một lịch thực thi xen kẽ

Giả sử tồn kho của một sản phẩm là **1**. Hai giao dịch T1 và T2 cùng xử lý một đơn mua một sản phẩm, và ứng dụng dùng cách “đọc rồi tự tính rồi ghi”:

| Bước | Giao dịch T1 | Giao dịch T2 |
| ---: | --- | --- |
| 1 | Đọc tồn kho = 1 | |
| 2 | | Đọc tồn kho = 1 |
| 3 | Quyết định nhận đơn | |
| 4 | | Quyết định nhận đơn |
| 5 | Ghi tồn kho = 0; tạo đơn 1 | |
| 6 | | Ghi tồn kho = 0; tạo đơn 2 |
| 7 | Commit | Commit |

Cuối cùng có **hai đơn được nhận nhưng chỉ có một sản phẩm**. Giá trị tồn kho là 0 không hề tiết lộ rằng đã bán quá một đơn. Cả hai giao dịch có thể đã dùng `BEGIN` và `COMMIT`; chỉ có giao dịch thôi chưa đủ, vì quyết định nghiệp vụ dựa trên hai lần đọc cùng dữ liệu cũ.

Một cách bảo vệ phổ biến là đặt điều kiện kiểm tra và trừ tồn kho **trong cùng câu ghi nguyên tử**:

```sql
UPDATE inventory
SET available = available - 1
WHERE product_id = 42
  AND available >= 1;
```

Ứng dụng chỉ xác nhận đơn khi số dòng được cập nhật bằng 1; nếu là 0 thì báo hết hàng và không tạo đơn. Khi hai giao dịch cạnh tranh cùng dòng, DBMS phải thực thi hoặc kiểm tra xung đột ghi theo cơ chế của nó để không cho cả hai phép trừ có điều kiện cùng thành công trên một đơn vị hàng. Toàn bộ việc trừ kho và tạo đơn vẫn phải nằm trong cùng giao dịch để tránh trạng thái dở dang.

Ví dụ này cho thấy **tính nguyên tử của một câu ghi có điều kiện** là công cụ mạnh, nhưng không thay thế việc chọn ranh giới giao dịch và kiểm tra kết quả.

## 5. Lịch thực thi, tuần tự và tuần tự hóa

Một **lịch thực thi (schedule/history)** mô tả thứ tự các thao tác của các giao dịch, chẳng hạn đọc X, ghi X, commit hoặc rollback.

- **Lịch tuần tự (serial):** T1 kết thúc rồi T2 bắt đầu, hoặc ngược lại; các bước của hai giao dịch không xen kẽ.
- **Lịch xen kẽ (interleaved):** một số bước của T1 và T2 được thực hiện đan xen.
- **Lịch có tính tuần tự hóa (serializable):** dù có xen kẽ, hiệu ứng quan sát được của các giao dịch đã commit tương đương một lịch tuần tự hợp lệ.

Lịch xen kẽ không đương nhiên sai. Chẳng hạn, giao dịch cập nhật hồ sơ khách hàng A và giao dịch cập nhật hồ sơ khách hàng B có thể không xung đột. Ngược lại, hai giao dịch cùng sửa một số dư cần được điều phối cẩn thận.

Xét X ban đầu bằng 100:

- T1 tăng X thêm 20.
- T2 tăng X thêm 10%.

Nếu chạy tuần tự, T1 rồi T2 cho kết quả **132**; T2 rồi T1 cho kết quả **130**. Nhưng nếu T1 và T2 cùng đọc X = 100, sau đó T1 ghi 120 còn T2 ghi 110, kết quả cuối cùng **110** không phản ánh đủ cả hai thay đổi. Đây là ví dụ về **lost update**.

Cốt lõi của điều khiển đồng thời là khiến những xung đột đọc/ghi được xử lý theo các bảo đảm mong muốn, dù DBMS vẫn cho phép những công việc độc lập hoạt động xen kẽ.

## 6. Các hiện tượng bất thường khi giao dịch chồng lấn

### 6.1. Dirty read — Đọc dữ liệu chưa commit

1. T1 sửa giá sản phẩm từ 100 thành 120 nhưng chưa commit.
2. T2 đọc được giá 120.
3. T1 rollback, khiến thay đổi 120 chưa từng được chốt.

T2 đã dùng dữ liệu không được xác nhận. Nếu T2 dựa vào đó để quyết định, ứng dụng có thể tạo ra kết quả sai. Mức `READ COMMITTED` phổ biến ngăn đọc dữ liệu chưa commit; không nên mặc định mọi DBMS đều cho phép dirty read ở `READ UNCOMMITTED`.

### 6.2. Non-repeatable read — Đọc lại cùng dòng thấy giá trị khác

1. T1 đọc số dư tài khoản A = 100.
2. T2 cập nhật A = 120 và commit.
3. Trong cùng giao dịch, T1 đọc lại A và thấy 120.

Hai lần đọc **cùng dòng** cho giá trị khác nhau vì T2 đã commit ở giữa. Hiện tượng này có thể bình thường trong một số ứng dụng, nhưng nguy hiểm khi T1 giả định giá trị ban đầu luôn ổn định trong suốt quyết định nghiệp vụ.

### 6.3. Phantom read — Đọc lại một tập kết quả thấy “dòng mới/mất”

1. T1 truy vấn: `SELECT COUNT(*) FROM orders WHERE status = 'PENDING'` và nhận 3.
2. T2 thêm một đơn có `status = 'PENDING'` rồi commit.
3. T1 chạy lại cùng điều kiện và nhận 4.

Điểm khác với non-repeatable read là **tập dòng thỏa điều kiện truy vấn thay đổi**, thay vì chỉ một giá trị trên cùng dòng. Cách các DBMS dùng MVCC hoặc khóa vùng để xử lý phantom phụ thuộc engine và mức cô lập.

### 6.4. Lost update — Một cập nhật bị cập nhật khác ghi đè

1. T1 đọc điểm thưởng = 100.
2. T2 cũng đọc điểm thưởng = 100.
3. T1 cộng 20 và ghi 120.
4. T2 cộng 10 từ giá trị cũ và ghi 110.

Phần cộng 20 của T1 bị mất. Hiện tượng thường đến từ việc **đọc → tính trong ứng dụng → ghi đè** mà không kiểm tra xem bản ghi đã thay đổi hay chưa.

Các hướng khắc phục tùy trường hợp gồm dùng phép cập nhật nguyên tử như `SET points = points + 10`, khóa dòng khi đọc để sửa, dùng cột phiên bản cho optimistic locking hoặc mức cô lập phù hợp. Không được suy ra rằng chỉ cần `READ COMMITTED` là mọi trường hợp lost update đã được ngăn.

### 6.5. Write skew — Các giao dịch sửa khác dòng nhưng cùng phá một bất biến

Giả sử cần **ít nhất một bác sĩ trực**. A và B đều đang trực:

1. T1 kiểm tra thấy A và B đang trực, nên định cho A nghỉ.
2. T2 cũng kiểm tra thấy cả hai đang trực, nên định cho B nghỉ.
3. T1 cập nhật `A.on_call = false`; T2 cập nhật `B.on_call = false`.
4. Cả hai commit, kết quả không còn ai trực.

Hai giao dịch cập nhật **hai dòng khác nhau**, nên việc chỉ phát hiện xung đột khi cùng ghi một dòng có thể không đủ. Một số cơ chế snapshot isolation vẫn cho phép write skew. Bảo vệ có thể đòi hỏi mức `SERIALIZABLE` với xử lý retry, khóa trên một tài nguyên chung hoặc tái cấu trúc bất biến thành ràng buộc được DBMS kiểm soát.

### 6.6. Deadlock và chờ khóa

Deadlock không phải một giá trị đọc sai, mà là tình huống các giao dịch chờ nhau thành vòng:

- T1 đang giữ khóa A rồi muốn khóa B.
- T2 đang giữ khóa B rồi muốn khóa A.
- Cả hai đều không thể tiến triển nếu không có cơ chế giải quyết.

DBMS thường phát hiện deadlock và hủy một giao dịch để phá vòng chờ. Ứng dụng cần hiểu lỗi này có thể xảy ra ngay cả khi thiết kế nghiệp vụ đúng và nên retry **cả giao dịch** khi thao tác an toàn để thử lại. Khóa theo thứ tự nhất quán và giữ giao dịch ngắn giúp giảm xác suất deadlock.

## 7. Mức cô lập giao dịch: chọn bảo đảm phù hợp

Chuẩn SQL nêu bốn tên mức cô lập quen thuộc. Chúng mô tả những hành vi có thể quan sát, nhưng cách hiện thực và các hiện tượng được ngăn **khác nhau giữa PostgreSQL, MySQL/InnoDB, SQL Server, Oracle và các engine khác**.

| Mức cô lập | Dirty read | Non-repeatable read | Phantom read | Ý nghĩa khái quát |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` | Có thể xảy ra theo mô hình chuẩn | Có thể | Có thể | Cho phép mức quan sát yếu; nhiều engine vẫn ngăn dirty read. |
| `READ COMMITTED` | Không | Có thể | Có thể | Chỉ đọc dữ liệu đã commit; các lần đọc có thể thấy snapshot khác nhau. |
| `REPEATABLE READ` | Không | Không đối với dữ liệu đã đọc theo bảo đảm mức này | Chuẩn SQL vẫn cho phép; thực tế tùy engine | Giữ ổn định các lần đọc liên quan, nhưng chưa mặc định ngăn mọi write skew. |
| `SERIALIZABLE` | Không | Không | Không | Kết quả giao dịch đã commit phải tương đương một thứ tự tuần tự hợp lệ. |

Bảng này là **mô hình khái quát để học khái niệm**, không phải cam kết chính xác cho mọi phiên bản DBMS. Ví dụ, một hệ dùng snapshot nhất quán có thể tránh thấy phantom ở những lần đọc snapshot lặp lại nhưng vẫn cho phép write skew. Tên `REPEATABLE READ` không tự chứng minh rằng một loạt thao tác đọc rồi ghi là serializable.

Mức cô lập mạnh hơn có thể kéo theo chờ khóa, xung đột hoặc lỗi yêu cầu thử lại, tùy engine. Việc chọn mức nên bắt đầu từ **bất biến nghiệp vụ** và các kết quả không thể chấp nhận, sau đó kiểm chứng theo DBMS cụ thể.

### 7.1. Snapshot và khả năng nhìn thấy dữ liệu

Một giao dịch không nhất thiết đọc “giá trị mới nhất trên toàn thế giới” tại mọi thời điểm. Với cơ chế phiên bản, một truy vấn có thể đọc phiên bản đã commit phù hợp với **snapshot** của nó. Snapshot được xác định theo câu lệnh hay theo giao dịch tùy mức cô lập và DBMS.

Nhờ đó, một giao dịch đọc lâu có thể không cản trở nhiều giao dịch ghi khác. Nhưng snapshot ổn định **không tự bảo đảm** rằng nhiều quyết định dựa trên cùng một điều kiện toàn cục là an toàn khi chúng ghi vào các dòng khác nhau.

### 7.2. Khi nào nghĩ đến serializable?

Serializable hữu ích khi kết quả phải giống một thứ tự giao dịch tuần tự, chẳng hạn bảo vệ điều kiện phức tạp phụ thuộc nhiều dòng và khó diễn tả bằng một câu cập nhật có điều kiện. Nó không có nghĩa cứ bật lên là mọi câu SQL hoặc logic nghiệp vụ đều đúng: DBMS vẫn chỉ bảo vệ tương quan thực thi, còn ứng dụng vẫn phải áp dụng đúng quy tắc.

Ở một số hệ, hai giao dịch đồng thời hợp lệ nếu chạy riêng lẻ nhưng không thể cùng commit theo lịch hiện tại. DBMS sẽ báo lỗi serialization failure. Ứng dụng phải **thử lại toàn bộ giao dịch**, đọc lại dữ liệu và tính lại quyết định; không chỉ gửi lại một câu `COMMIT`.

## 8. DBMS điều khiển đồng thời bằng cách nào?

### 8.1. Khóa bi quan (pessimistic locking)

DBMS có thể đặt khóa để ngăn hoặc trì hoãn thao tác xung đột. Khóa có thể nằm ở mức dòng, vùng khóa chỉ mục, bảng hoặc đối tượng khác, tùy DBMS và truy vấn.

Nếu nghiệp vụ cần đọc một dòng, quyết định và sau đó sửa chính dòng đó, có hệ hỗ trợ đọc với ý định khóa:

```sql
BEGIN;

SELECT available
FROM inventory
WHERE product_id = 42
FOR UPDATE;

-- Ứng dụng kiểm tra điều kiện rồi cập nhật trong cùng giao dịch.

COMMIT;
```

`FOR UPDATE` và phạm vi khóa là ví dụ SQL phổ biến; cú pháp và hành vi cụ thể tùy hệ quản trị. Một khóa dòng không mặc nhiên bảo vệ mọi điều kiện liên quan tới **tập nhiều dòng**. Nếu truy vấn không tìm được dòng nào, việc “khóa dòng không tồn tại” cũng cần xem xét riêng.

Ưu điểm: diễn đạt rõ ràng ý định loại trừ xung đột với tài nguyên đã khóa. Đổi lại, giao dịch khác có thể phải chờ; giao dịch dài gây tắc nghẽn và tăng nguy cơ deadlock.

### 8.2. MVCC — Điều khiển đồng thời bằng nhiều phiên bản

**Multi-Version Concurrency Control (MVCC)** cho phép lưu hoặc quản lý nhiều phiên bản logic của bản ghi, để các truy vấn đọc có thể thấy một phiên bản phù hợp thay vì luôn chặn nhau bằng khóa đọc/ghi truyền thống.

Hình dung bản ghi X thay đổi:

```text
Phiên bản đã commit trước: X = 100
T2 tạo phiên bản mới:       X = 120
T2 commit
T1 đang đọc snapshot cũ:   có thể vẫn thấy X = 100
T3 bắt đầu snapshot mới:   có thể thấy X = 120
```

Bản ghi nào được nhìn thấy phụ thuộc snapshot và mức cô lập. MVCC **không có nghĩa mọi giao dịch ghi được phép ghi tùy ý**: các xung đột ghi vẫn cần được kiểm soát; một số bất thường như write skew vẫn có thể tồn tại.

### 8.3. Kiểm soát lạc quan (optimistic concurrency control)

Khi xung đột tương đối hiếm, ứng dụng có thể đọc dữ liệu kèm số phiên bản, tính toán rồi chỉ ghi nếu phiên bản **vẫn còn như lúc đọc**:

```sql
UPDATE customer_profiles
SET display_name = :new_name,
    version = version + 1
WHERE id = :customer_id
  AND version = :version_read_before;
```

- Nếu cập nhật **1 dòng**, điều kiện phiên bản khớp.
- Nếu cập nhật **0 dòng**, dữ liệu có thể đã được thay đổi hoặc bản ghi không còn tồn tại; ứng dụng cần đọc lại, giải quyết xung đột hoặc trả lỗi thích hợp.

Đây là cách chống ghi đè mù, nhưng không tự giải quyết mọi bất biến liên quan nhiều dòng. Không nên mặc định “optimistic” luôn nhanh hơn “pessimistic”; kết quả phụ thuộc mức tranh chấp và chi phí retry.

### 8.4. Ràng buộc dữ liệu và câu ghi có điều kiện

Nhiều vấn đề nên được chặn gần dữ liệu nhất có thể:

| Bất biến | Công cụ thường hữu ích |
| --- | --- |
| Một email chỉ thuộc một tài khoản | `UNIQUE(email)`, xử lý lỗi vi phạm ràng buộc. |
| Số dư/tồn kho không âm | `CHECK` nếu được hỗ trợ và phù hợp, kết hợp `UPDATE ... WHERE amount >= ?`. |
| Không tạo dòng con trỏ đến bản ghi cha không tồn tại | `FOREIGN KEY`. |
| Chỉ sửa dữ liệu còn phiên bản đang đọc | `UPDATE ... WHERE version = ?` và kiểm tra số dòng. |
| Một chỗ ngồi chỉ được đặt một lần | Ràng buộc duy nhất theo chuyến/chỗ hoặc cập nhật trạng thái có điều kiện; xử lý xung đột. |

Ràng buộc DBMS có lợi vì vẫn được thực thi ngay cả khi có nhiều đường ghi khác nhau vào dữ liệu. Tuy nhiên, phải thiết kế khóa và mô hình dữ liệu đúng với điều kiện thực tế, kể cả trạng thái “hủy”, “giữ chỗ” hoặc “đã thanh toán”.

## 9. Ví dụ đầy đủ: chuyển tiền an toàn trước lỗi và cạnh tranh

Giả sử tài khoản nguồn A muốn chuyển `amount` cho B. Những điều kiện tối thiểu:

1. `amount` dương và biểu diễn bằng kiểu tiền chính xác như đơn vị nhỏ nhất dạng số nguyên hoặc `DECIMAL` thích hợp; tránh dùng số thực dấu phẩy động cho số tiền.
2. A và B tồn tại, là tài khoản hợp lệ; A có đủ tiền.
3. Trừ A và cộng B cùng thuộc một giao dịch; không được có một bước commit riêng.
4. Các yêu cầu cạnh tranh trừ tiền từ A không được cùng dựa vào một số dư cũ để rút vượt mức cho phép.
5. Nếu hệ thống có thể gửi lại cùng yêu cầu vì timeout, phải ngăn **xử lý chuyển tiền hai lần** bằng mã yêu cầu nghiệp vụ duy nhất và cơ chế idempotency phù hợp.

Một luồng khái niệm:

```text
Bắt đầu giao dịch
    |
    v
UPDATE accounts
SET balance = balance - :amount
WHERE id = :source_id
  AND balance >= :amount

    |-- affected_rows != 1 --> ROLLBACK; báo thiếu tiền/không có nguồn
    |
    v
UPDATE accounts
SET balance = balance + :amount
WHERE id = :destination_id

    |-- affected_rows != 1 --> ROLLBACK; báo đích không hợp lệ
    |
    v
Ghi bản ghi chuyển tiền / mã nghiệp vụ duy nhất (nếu yêu cầu)
    |-- lỗi ràng buộc --> ROLLBACK; xử lý trùng yêu cầu
    |
    v
COMMIT
    |
    v
Trả kết quả thành công
```

Đây là **pseudocode về trình tự giao dịch**, không phải một script SQL có thể chạy nguyên xi. Toàn bộ thao tác phải dùng một ngữ cảnh giao dịch; ứng dụng cần xử lý ngoại lệ, lỗi commit và trường hợp không biết chắc kết quả commit do mất kết nối.

**Vì sao câu `UPDATE ... WHERE balance >= :amount` quan trọng?** Kiểm tra số dư và phép trừ nằm trong cùng câu ghi. Hai giao dịch cùng tranh chấp bản ghi A không được cùng trừ dựa trên kiểm tra tách rời từ số dư cũ; DBMS điều phối ghi và kiểm tra theo cơ chế của nó. Cần kiểm tra `affected_rows`; nếu 0 thì không được cộng tiền vào B.

**Nếu A và B bị cập nhật theo thứ tự ngược nhau giữa hai giao dịch?** Có khả năng deadlock. Một quy tắc khóa theo thứ tự định danh cố định có thể giảm deadlock; ứng dụng vẫn cần xử lý lỗi retry có giới hạn.

**Nếu khách hàng bấm lại nút chuyển tiền?** ACID bảo vệ tính nguyên tử của **một lần xử lý**, không tự nhận diện hai yêu cầu HTTP là cùng một nghiệp vụ. Một khóa duy nhất cho `transfer_request_id` và logic trả kết quả của yêu cầu đã xử lý giúp tránh chuyển lặp.

**Nếu chuyển giữa hai ngân hàng hoặc gọi cổng thanh toán bên ngoài?** Giao dịch local của một DBMS không tự rollback được hiệu ứng đã hoàn thành tại một dịch vụ khác. Bài toán khi đó cần thêm cơ chế phối hợp giữa hệ thống như idempotency, outbox, trạng thái nghiệp vụ hoặc saga tùy yêu cầu.

## 10. Những sai lầm thường gặp

### “Có `BEGIN` và `COMMIT` nên mọi thứ đã an toàn”

Sai ở chỗ ACID giao dịch và logic điều khiển đồng thời giải quyết những vấn đề liên quan nhưng khác nhau. Giao dịch có thể nguyên tử mà ứng dụng vẫn đọc dữ liệu cũ, tính sai hoặc vi phạm bất biến khi chạy song song. Cần xét mức cô lập, khóa, cập nhật có điều kiện và ràng buộc.

### “Dùng `SELECT` kiểm tra trước khi `INSERT` là đủ”

Hai giao dịch có thể cùng thấy “chưa tồn tại” rồi cùng chèn. Nếu yêu cầu duy nhất, nên dùng ràng buộc `UNIQUE` và xử lý lỗi cạnh tranh. Đọc trước có thể phục vụ thông báo thân thiện, nhưng không là hàng rào bảo vệ cuối cùng.

### “Dùng MVCC thì không có khóa và không xảy ra xung đột”

MVCC giúp các phiên đọc/ghi hoạt động hiệu quả hơn trong nhiều trường hợp; nó không loại bỏ xung đột khi nhiều giao dịch cùng sửa dữ liệu hay quyết định dựa trên cùng một bất biến.

### “Serializable nghĩa là không cần retry”

Tùy cách triển khai, DBMS có thể hủy một giao dịch để giữ tính tuần tự hóa. Ứng dụng phải coi lỗi serialization/deadlock là một khả năng bình thường, và chỉ thử lại khi thao tác có thể lặp lại an toàn.

### “Rollback có thể thu hồi mọi thứ đã thực hiện trong hàm”

Rollback của DBMS không thu hồi email đã gửi, lời gọi HTTP đã được xử lý, file đã xóa hoặc giao dịch ở một hệ thống khác. Nên giữ giao dịch DB ngắn, tách tác dụng phụ không tham gia giao dịch và dùng cơ chế giao nhận đáng tin cậy khi cần.

### “Đọc 0 dòng hoặc sửa 0 dòng không phải lỗi nên cứ commit”

Với nghiệp vụ trừ tiền, giữ chỗ, đổi phiên bản hoặc cập nhật trạng thái, **0 dòng** thường là tín hiệu điều kiện không còn hợp lệ. Nếu bỏ qua số dòng ảnh hưởng, chương trình có thể xác nhận thành công giả.

## 11. Thiết kế ranh giới giao dịch thực tế

Một ranh giới tốt thường đủ rộng để giữ **một bất biến nghiệp vụ**, nhưng đủ ngắn để không giữ tài nguyên quá lâu.

Ví dụ xử lý một đơn hàng đơn giản:

```text
Nhận yêu cầu
  -> kiểm tra định dạng và quyền cần thiết
  -> BEGIN
  -> giảm tồn kho có điều kiện
  -> kiểm tra số dòng cập nhật
  -> tạo đơn và dòng hàng
  -> COMMIT
  -> trả kết quả / phát sự kiện sau commit theo cơ chế đáng tin cậy
```

Không nên mở giao dịch rồi chờ người dùng xác nhận, gọi một API chậm không có giới hạn hoặc thực hiện công việc CPU dài trước khi commit. Khóa bị giữ lâu làm tăng thời gian chờ và khả năng deadlock.

Một số lưu ý vận hành:

- **Autocommit:** hiểu mặc định của thư viện/ORM; không tưởng rằng nhiều lệnh tự động nằm cùng giao dịch nếu chưa thiết lập.
- **Connection/transaction context:** các câu lệnh cần chung giao dịch phải dùng đúng kết nối hoặc ngữ cảnh giao dịch được framework quản lý.
- **Timeout và hủy:** phân biệt query timeout, lock timeout, transaction timeout và lỗi kết nối; biết khi nào giao dịch cần rollback.
- **Retry:** thử lại **toàn bộ quyết định** sau khi đọc dữ liệu mới; giới hạn số lần và dùng backoff phù hợp. Không retry mù những thao tác tạo tác dụng phụ không idempotent.
- **Thứ tự truy cập:** nếu nhiều giao dịch phải khóa nhiều tài nguyên, cố gắng dùng một thứ tự ổn định.
- **Quan sát:** theo dõi thời gian giao dịch, thời gian chờ khóa, tỷ lệ deadlock, serialization failure và số lần retry để nhận biết điểm tranh chấp.
- **Phạm vi bảo đảm:** tìm hiểu ngữ nghĩa thực tế của isolation level, khóa, snapshot và commit trên chính DBMS/phiên bản đang dùng.

### 11.1. Savepoint có thay thế transaction không?

Một số DBMS hỗ trợ `SAVEPOINT` và `ROLLBACK TO SAVEPOINT`, cho phép hủy một phần công việc chưa chốt **bên trong giao dịch hiện hành**:

```sql
BEGIN;

UPDATE ...;

SAVEPOINT step_two;
-- Một số thao tác có thể thất bại.
ROLLBACK TO SAVEPOINT step_two;

COMMIT;
```

Đây là ví dụ cấu trúc; `UPDATE ...` là chỗ giữ vị trí, không phải câu SQL hoàn chỉnh. Savepoint không biến phần công việc trước nó thành một giao dịch đã commit độc lập; toàn bộ vẫn phụ thuộc commit cuối cùng. Hỗ trợ và quy tắc xử lý lỗi sau savepoint khác nhau theo DBMS.

## 12. Chọn giải pháp cho từng loại cạnh tranh

| Tình huống | Rủi ro chính | Hướng thiết kế ban đầu |
| --- | --- | --- |
| Hai người cùng mua sản phẩm cuối | Bán vượt tồn kho | Cập nhật tồn kho có điều kiện, kiểm tra số dòng, tạo đơn trong cùng giao dịch. |
| Hai yêu cầu cùng tạo tài khoản với một email | Tạo dữ liệu trùng | Ràng buộc `UNIQUE` và xử lý xung đột khi insert. |
| Hai người cùng sửa biểu mẫu hồ sơ | Ghi đè thay đổi | Cột phiên bản và optimistic locking, hoặc quy tắc hợp nhất rõ ràng. |
| Một phép chuyển tiền gồm hai cập nhật | Thay đổi một nửa; trừ vượt số dư | Transaction, cập nhật có điều kiện, kiểm tra kết quả, idempotency. |
| Một quyết định dựa trên bất biến ở nhiều dòng | Write skew | Thiết kế ràng buộc/khóa chung hoặc dùng serializable với retry. |
| Các giao dịch ghi nhiều dòng theo thứ tự khác nhau | Deadlock | Thứ tự khóa nhất quán, giao dịch ngắn, xử lý retry. |
| Truy vấn báo cáo phải thấy một ảnh chụp dữ liệu ổn định | Các lần đọc không đồng nhất | Cân nhắc snapshot phù hợp với DBMS và tính chất báo cáo. |

Không có một mức cô lập hay kiểu khóa “tốt nhất cho mọi bài toán”. Đúng đắn đến từ việc phát biểu rõ **điều kiện phải luôn đúng**, nhận diện những giao dịch có thể cạnh tranh, rồi chọn biện pháp mà DBMS thực sự bảo đảm.

## 13. Tự phân tích ba tình huống

**Tình huống A — Rút tiền:** tài khoản còn 500.000. Hai yêu cầu rút 400.000 cùng đọc số dư 500.000 trước khi cập nhật. Nếu mỗi yêu cầu tính `new_balance = old_balance - 400000` rồi ghi đè, điều gì sẽ xảy ra? Số dư cuối bằng 100.000 không chứng minh hệ thống đã rút hợp lệ: cả hai yêu cầu có thể đã được xác nhận dù tổng tiền rút là 800.000. Cần kiểm soát cạnh tranh ngay tại phép trừ hoặc cơ chế khóa/phiên bản phù hợp.

**Tình huống B — Thống kê tồn kho:** T1 đếm các sản phẩm còn hàng, T2 vừa nhập thêm một sản phẩm mới rồi commit. T1 đếm lại trong cùng giao dịch thấy số khác. Đây là hiện tượng liên quan **phantom read**; việc có xảy ra hay không phụ thuộc snapshot và isolation của giao dịch.

**Tình huống C — Lịch trực:** hai giao dịch cùng xác nhận “còn một người trực khác” rồi tự cho một người nghỉ. Chúng sửa hai dòng khác nhau nhưng kết quả không còn ai trực. Đây là ví dụ **write skew**: không thể chỉ kiểm tra xem hai giao dịch có ghi đè đúng cùng một dòng hay không.

Qua ba tình huống, có thể thấy câu hỏi trọng tâm không chỉ là **“đã dùng transaction chưa?”**, mà còn là **“khi giao dịch khác chen vào giữa các lần đọc và ghi, bất biến nào còn được bảo vệ?”**. Đó là lý do giao dịch và điều khiển đồng thời phải được thiết kế cùng nhau trong cơ sở dữ liệu.
