# Ảnh chụp theo câu lệnh và theo giao dịch

Trong cơ sở dữ liệu dùng MVCC (*Multi-Version Concurrency Control*), một dòng dữ liệu có thể có nhiều phiên bản. Khi giao dịch đọc dữ liệu, hệ quản trị xác định phiên bản nào được phép nhìn thấy dựa trên một **ảnh chụp nhất quán** (*consistent snapshot* hoặc *read view*). Ảnh chụp xác định ranh giới thời gian của dữ liệu đã commit mà thao tác đọc có thể quan sát.

Ảnh chụp có thể được tạo mới cho từng câu lệnh hoặc được giữ ổn định trong suốt một giao dịch. Hai cách này tạo ra hành vi khác nhau khi một giao dịch khác commit dữ liệu giữa hai lần đọc:

- **Ảnh chụp theo câu lệnh** (*statement-level snapshot*): mỗi câu lệnh đọc có ảnh chụp riêng. Câu lệnh sau có thể nhìn thấy dữ liệu được commit sau câu lệnh trước.
- **Ảnh chụp theo giao dịch** (*transaction-level snapshot*): các câu lệnh đọc nhất quán trong cùng giao dịch dùng chung một ảnh chụp. Giao dịch tiếp tục nhìn thấy cùng một trạng thái dữ liệu bên ngoài, kể cả khi giao dịch khác đã commit thay đổi mới.

Khác biệt này quyết định một giao dịch có thể nhìn thấy dữ liệu mới ở lần đọc kế tiếp hay phải tiếp tục làm việc với trạng thái đã quan sát trước đó.

## 1. MVCC tạo ảnh chụp nhất quán như thế nào?

MVCC cho phép hệ quản trị giữ nhiều phiên bản của một dòng thay vì bắt mọi thao tác đọc phải chờ thao tác ghi hoàn tất. Khi một giao dịch cập nhật dòng, hệ quản trị tạo hoặc duy trì một phiên bản mới và lưu thông tin cần thiết để các giao dịch khác có thể nhìn thấy phiên bản phù hợp với ảnh chụp của chúng.

Để quyết định một phiên bản có nhìn thấy được hay không, hệ quản trị thường theo dõi thông tin giao dịch như mã giao dịch, thời điểm bắt đầu/kết thúc hoặc thứ tự commit. Chi tiết cấu trúc khác nhau giữa các sản phẩm, nhưng quy tắc khái quát là:

- Phiên bản đã commit trước ranh giới ảnh chụp có thể được nhìn thấy, nếu nó không bị một phiên bản mới hơn trong cùng ảnh chụp thay thế.
- Phiên bản được commit sau ranh giới ảnh chụp thường không xuất hiện trong ảnh chụp đó.
- Giao dịch thường nhìn thấy các thay đổi do chính nó tạo ra, dù các thay đổi ấy chưa commit cho giao dịch khác nhìn thấy.
- Phiên bản chưa commit của giao dịch khác không được coi là dữ liệu đã xác nhận trong một lần đọc nhất quán thông thường.

Các phiên bản cũ phải được giữ lại khi vẫn còn giao dịch có thể cần chúng. Sau khi không còn ảnh chụp đang hoạt động cần một phiên bản cũ, hệ quản trị mới có thể dọn dẹp phiên bản đó bằng cơ chế như vacuum hoặc purge. Vì vậy, thời gian sống của giao dịch đọc có ảnh hưởng đến lượng phiên bản cũ cần lưu giữ.

## 2. Ảnh chụp theo câu lệnh

Với ảnh chụp theo câu lệnh, mỗi câu lệnh đọc bắt đầu bằng một ảnh chụp mới. Ảnh chụp thường phản ánh các thay đổi đã commit trước thời điểm câu lệnh bắt đầu lấy ảnh chụp.

Giả sử bảng `orders` có 10 đơn hàng đang chờ xử lý:

1. `T1` bắt đầu và chạy truy vấn đếm đơn hàng. Kết quả là 10.
2. `T2` thêm một đơn hàng đang chờ xử lý rồi commit.
3. `T1` chạy lại đúng truy vấn đếm trong cùng giao dịch.
4. Ảnh chụp mới của câu lệnh thứ hai nhìn thấy đơn hàng mà `T2` đã commit, nên kết quả là 11.

```text
Thời gian ───────────────────────────────────────────────────────────►

T1: BEGIN
    SELECT COUNT(*)  ───────────────► 10
                       │
                       │  T2 thêm đơn hàng và COMMIT
                       ▼
    SELECT COUNT(*)  ───────────────► 11
    COMMIT

Ảnh chụp:       [Câu lệnh 1]         [Câu lệnh 2]
                  thấy 10              thấy 11
```

Hai câu lệnh thuộc cùng một giao dịch nhưng quan sát hai trạng thái đã commit khác nhau. Đây là hành vi thường gặp của mức `READ COMMITTED` khi hệ quản trị triển khai mức này bằng MVCC với ảnh chụp theo câu lệnh.

Một câu lệnh đang chạy thường tiếp tục dùng ảnh chụp đã lấy khi nó bắt đầu. Nếu `T2` commit sau thời điểm đó, câu lệnh đang chạy không tự chuyển sang ảnh chụp mới giữa chừng. Thay đổi mới chỉ có thể xuất hiện ở một câu lệnh đọc tiếp theo có ảnh chụp mới.

## 3. Ảnh chụp theo giao dịch

Với ảnh chụp theo giao dịch, một ảnh chụp nhất quán được thiết lập cho giao dịch và được tái sử dụng ở các lần đọc nhất quán tiếp theo. Ranh giới ảnh chụp có thể được tạo tại thời điểm bắt đầu giao dịch hoặc tại lần đọc nhất quán đầu tiên, tùy hệ quản trị và mức cô lập.

Dùng lại ví dụ trên:

1. `T1` bắt đầu và thực hiện lần đọc nhất quán đầu tiên, nhận kết quả 10. Ảnh chụp của giao dịch được thiết lập.
2. `T2` thêm đơn hàng mới rồi commit.
3. `T1` chạy lại truy vấn đếm.
4. Lần đọc thứ hai vẫn dùng ảnh chụp cũ, nên kết quả tiếp tục là 10.

```text
Thời gian ───────────────────────────────────────────────────────────►

T1: BEGIN
    SELECT COUNT(*)  ───────────────► 10
                       │
                       │  T2 thêm đơn hàng và COMMIT
                       ▼
    SELECT COUNT(*)  ───────────────► 10
    COMMIT

Ảnh chụp T1:  [──────────────────────────────]
              thấy trạng thái tại cùng một mốc
```

T1 vẫn nhìn thấy các thay đổi do chính T1 thực hiện trong giao dịch của mình. Ảnh chụp cố định chủ yếu quyết định khả năng nhìn thấy thay đổi do các giao dịch khác commit sau mốc ảnh chụp.

Ảnh chụp theo giao dịch giúp các lần đọc nhất quán trong cùng giao dịch cùng dựa trên một trạng thái dữ liệu. Tuy nhiên, nó không có nghĩa toàn bộ hệ thống ngừng thay đổi; các giao dịch khác vẫn có thể ghi và commit phiên bản mới. T1 chỉ chưa nhìn thấy các phiên bản mới đó qua những lần đọc nhất quán dùng ảnh chụp cũ.

## 4. So sánh trực tiếp hai cách lấy ảnh chụp

| Tiêu chí | Ảnh chụp theo câu lệnh | Ảnh chụp theo giao dịch |
|---|---|---|
| Phạm vi ảnh chụp | Một câu lệnh đọc | Nhiều lần đọc nhất quán trong một giao dịch |
| Thời điểm làm mới | Thường là khi câu lệnh mới bắt đầu | Một mốc được giữ ổn định theo quy tắc của hệ quản trị |
| Giao dịch khác commit giữa hai lần đọc | Câu lệnh sau có thể nhìn thấy thay đổi mới | Các lần đọc sau thường vẫn không nhìn thấy thay đổi mới đó |
| Tính nhất quán giữa các câu lệnh | Có thể thấy các trạng thái đã commit khác nhau | Các lần đọc nhất quán dùng chung một trạng thái bên ngoài |
| Hành vi thường gặp | `READ COMMITTED` dùng MVCC | Snapshot isolation hoặc một số triển khai `REPEATABLE READ` |
| Giới hạn chính | Có thể có non-repeatable read, phantom read hoặc read skew giữa các câu lệnh | Có thể gặp xung đột ghi và các bất thường như write skew; không mặc nhiên tương đương `SERIALIZABLE` |

Tên mức cô lập chỉ là một phần của câu trả lời. Cần biết hệ quản trị tạo ảnh chụp lúc nào và loại thao tác đọc nào thực sự sử dụng ảnh chụp đó.

## 5. Ví dụ SQL với hai phiên làm việc

Giả sử bảng `orders` đã tồn tại và có các hàng dữ liệu ban đầu. Cả hai phiên đều truy vấn cùng một điều kiện:

```sql
SELECT COUNT(*)
FROM orders
WHERE status = 'PENDING';
```

**Phiên A — giao dịch đọc:**

```sql
BEGIN;

-- Lần đọc thứ nhất
SELECT COUNT(*)
FROM orders
WHERE status = 'PENDING';

-- Tạm dừng để phiên B thêm dữ liệu và COMMIT.

-- Lần đọc thứ hai, vẫn cùng câu truy vấn
SELECT COUNT(*)
FROM orders
WHERE status = 'PENDING';

COMMIT;
```

**Phiên B — giao dịch ghi:**

```sql
BEGIN;

INSERT INTO orders (order_id, status)
VALUES (2001, 'PENDING');

COMMIT;
```

Chạy lần đọc đầu tiên ở phiên A, sau đó chạy và commit phiên B, rồi chạy lần đọc thứ hai ở phiên A.

- Nếu phiên A dùng ảnh chụp theo câu lệnh, lần đọc thứ hai có thể đếm thêm hàng `2001`.
- Nếu phiên A dùng ảnh chụp theo giao dịch và ảnh chụp đã được thiết lập trước khi phiên B commit, lần đọc thứ hai vẫn không đếm hàng `2001`.

Để thử nghiệm chính xác, cần cấu hình mức cô lập trước khi thực hiện các câu lệnh đọc và dùng cú pháp bắt đầu giao dịch phù hợp với hệ quản trị. Không thể chỉ nhìn vào hai lệnh `BEGIN` và `SELECT` rồi kết luận loại ảnh chụp; cấu hình kết nối và mức cô lập đang có hiệu lực mới quyết định hành vi.

## 6. Ảnh hưởng đến các bất thường đọc

### 6.1. Đọc không lặp lại (non-repeatable read)

Với ảnh chụp theo câu lệnh, một giao dịch có thể đọc cùng một hàng hai lần và nhận hai giá trị khác nhau nếu giao dịch khác cập nhật hàng đó rồi commit giữa hai câu lệnh. Ví dụ, lần đọc đầu thấy số dư 500; giao dịch khác chuyển tiền và commit; lần đọc sau thấy số dư 450.

Ảnh chụp theo giao dịch giữ phiên bản nhìn thấy ổn định cho các lần đọc nhất quán. T1 tiếp tục thấy số dư 500 trong ví dụ, dù phiên bản mới đã được commit.

### 6.2. Đọc ma (phantom read)

Phantom read xảy ra khi giao dịch chạy lại truy vấn theo điều kiện và nhận một tập hàng khác vì dữ liệu phù hợp đã thay đổi. Với ảnh chụp theo câu lệnh, một hàng mới được commit giữa hai câu lệnh có thể xuất hiện ở lần đọc sau. Với ảnh chụp theo giao dịch, hàng đó thường không xuất hiện trong những lần đọc nhất quán tiếp theo của cùng giao dịch.

### 6.3. Read skew giữa nhiều câu lệnh

Ảnh chụp theo câu lệnh có thể khiến hai truy vấn liên quan nhìn thấy các mốc dữ liệu khác nhau. Chẳng hạn, một giao dịch đọc số dư tài khoản A trước khi một giao dịch chuyển tiền commit, rồi đọc số dư tài khoản B sau khi giao dịch chuyển tiền đã commit. Kết quả ghép lại có thể không phản ánh một trạng thái nhất quán duy nhất của cả hai tài khoản.

Ảnh chụp theo giao dịch giúp các lần đọc nhất quán cùng quan sát một mốc dữ liệu bên ngoài, nên giảm loại sai lệch này. Tuy nhiên, các thao tác khóa hoặc ghi có thể tuân theo quy tắc đọc hiện hành khác với lần đọc snapshot thông thường.

## 7. Snapshot isolation không đồng nghĩa với Serializable

Một giao dịch giữ ảnh chụp ổn định thường được gọi là đang chạy dưới **snapshot isolation** (*cô lập bằng ảnh chụp*). Cơ chế này ngăn nhiều bất thường đọc vì các câu lệnh đọc nhất quán cùng nhìn thấy một phiên bản dữ liệu. Nhưng hai giao dịch vẫn có thể cùng đọc một trạng thái cũ, sau đó ghi vào những hàng khác nhau và cùng commit theo cách phá vỡ một quy tắc nghiệp vụ.

Ví dụ có hai bác sĩ `A` và `B` đang trực. Quy tắc là luôn phải có ít nhất một bác sĩ trực:

1. `T1` và `T2` cùng lấy ảnh chụp khi cả A và B đều đang trực.
2. `T1` kiểm tra và thấy B vẫn trực, nên tắt trạng thái trực của A.
3. `T2` kiểm tra và thấy A vẫn trực, nên tắt trạng thái trực của B.
4. Hai giao dịch cập nhật hai hàng khác nhau nên có thể không xung đột ghi trực tiếp; cả hai cùng commit.
5. Kết quả cuối cùng là không còn bác sĩ nào trực, vi phạm quy tắc nghiệp vụ.

Đây là **write skew**. Ảnh chụp giao dịch giúp mỗi giao dịch đọc nhất quán, nhưng không tự động bảo vệ mọi điều kiện trên nhiều hàng. `SERIALIZABLE` cung cấp bảo đảm mạnh hơn: kết quả của các giao dịch đồng thời phải tương đương một thứ tự tuần tự hợp lệ. Tùy hệ quản trị, giao dịch có thể phải chờ hoặc bị hủy do xung đột tuần tự hóa và cần được thử lại.

Nếu quy tắc nghiệp vụ là một bất biến quan trọng, hãy bảo vệ nó bằng mức cô lập phù hợp, khóa điều phối, ràng buộc cơ sở dữ liệu hoặc một thiết kế ghi có kiểm soát. Đừng chỉ dựa vào việc các lần đọc dùng chung một ảnh chụp.

## 8. Cần phân biệt consistent read và current/locking read

Trong nhiều hệ quản trị MVCC, một câu `SELECT` thông thường có thể đọc phiên bản theo ảnh chụp. Một thao tác đọc có khóa như `SELECT ... FOR UPDATE`, hoặc một câu lệnh cập nhật, có thể cần kiểm tra trạng thái hiện hành để khóa và thay đổi dữ liệu chính xác.

Điều này đặc biệt quan trọng khi làm việc với MySQL InnoDB: consistent read không khóa thường dùng read view theo mức cô lập, trong khi locking read và thao tác ghi có thể dùng cách đọc hiện hành (*current read*). Vì vậy, không nên giả định mọi câu lệnh trong một giao dịch `REPEATABLE READ` đều nhìn thấy cùng một phiên bản theo cùng một quy tắc. Cần phân biệt loại thao tác và kiểm tra tài liệu hệ quản trị.

Tương tự, trong các hệ quản trị khác, thao tác đọc có khóa, truy vấn cập nhật và truy vấn đọc nhất quán có thể có quy tắc nhìn thấy dữ liệu khác nhau. Ảnh chụp nhất quán không thay thế cơ chế khóa khi giao dịch cần bảo vệ dữ liệu để ghi.

## 9. Cách các hệ quản trị triển khai ảnh chụp

Các tên mức cô lập có vẻ giống nhau nhưng thời điểm tạo ảnh chụp và hành vi cụ thể khác nhau. Một số ví dụ phổ biến:

| Hệ quản trị / cấu hình | Ảnh chụp thường dùng | Ghi chú |
|---|---|---|
| PostgreSQL `READ COMMITTED` | Theo câu lệnh | Mỗi câu lệnh lấy một snapshot mới; câu lệnh sau có thể thấy commit mới |
| PostgreSQL `REPEATABLE READ` | Theo giao dịch | Snapshot được cố định cho các lần đọc trong giao dịch; triển khai này cũng ngăn phantom read theo hành vi của PostgreSQL |
| MySQL InnoDB `READ COMMITTED` | Theo câu lệnh đọc nhất quán | Mỗi consistent read có read view mới |
| MySQL InnoDB `REPEATABLE READ` | Theo giao dịch đọc nhất quán | Read view thường được tạo ở lần consistent read đầu tiên; locking read và ghi có thể dùng current read |
| Oracle `READ COMMITTED` | Theo câu lệnh | Mỗi câu lệnh có tính nhất quán tại thời điểm bắt đầu câu lệnh |
| Oracle `SERIALIZABLE` hoặc `READ ONLY` | Theo giao dịch | Các câu lệnh đọc trong giao dịch dựa trên một mốc nhất quán của giao dịch; giao dịch ghi có thể gặp lỗi serialization |
| SQL Server với `READ_COMMITTED_SNAPSHOT` bật | Theo câu lệnh | `READ COMMITTED` dùng row versioning cho ảnh chụp ở phạm vi câu lệnh |
| SQL Server với `SNAPSHOT` | Theo giao dịch | Cần bật tùy chọn hỗ trợ snapshot isolation ở cơ sở dữ liệu; giao dịch dùng ảnh chụp ở phạm vi giao dịch |

Bảng trên mô tả các hành vi điển hình, không thay thế tài liệu của phiên bản cụ thể. Chẳng hạn, SQL Server `READ COMMITTED` khi không bật `READ_COMMITTED_SNAPSHOT` thường dùng khóa chia sẻ thay vì ảnh chụp MVCC; còn thời điểm chính xác tạo read view và quy tắc của truy vấn có khóa phụ thuộc sản phẩm.

Khi chuyển ứng dụng giữa các hệ quản trị, không nên chỉ giữ nguyên tên isolation level rồi giả định kết quả đọc sẽ giống nhau. Hãy xác nhận cấu hình MVCC, loại câu lệnh, thời điểm lấy snapshot và các hành vi xung đột ghi.

## 10. Chi phí và lưu ý vận hành

Ảnh chụp ổn định giúp giao dịch đọc nhất quán nhưng có thể làm tăng lượng phiên bản cũ phải giữ lại. Một giao dịch tồn tại lâu vẫn có thể cần đọc phiên bản tại mốc cũ, khiến cơ chế dọn dẹp chưa thể xóa các phiên bản đó.

Các hệ quả thường gặp gồm:

- **Tăng dung lượng phiên bản:** cập nhật và xóa tạo ra phiên bản cũ cần giữ lại trong thời gian có snapshot còn tham chiếu.
- **Chậm dọn dẹp:** giao dịch đọc kéo dài có thể ngăn vacuum, purge hoặc cơ chế dọn dẹp tương ứng thu hồi phiên bản không còn cần thiết.
- **Xung đột khi ghi:** snapshot isolation không bảo đảm mọi giao dịch cùng commit; hai giao dịch cập nhật cùng một hàng có thể khiến một giao dịch phải chờ hoặc thất bại.
- **Lỗi serialization:** mức cô lập mạnh có thể hủy giao dịch khi hệ quản trị phát hiện kết quả không thể tuần tự hóa; ứng dụng cần retry có giới hạn và an toàn.
- **Dữ liệu đọc có thể cũ:** giao dịch giữ snapshot lâu có thể tiếp tục thấy trạng thái cũ dù hệ thống đã có nhiều commit mới.

Do đó, nên giữ giao dịch ngắn, tránh chờ người dùng hoặc dịch vụ ngoài trong khi giao dịch đang mở, theo dõi giao dịch lâu và xử lý các lỗi xung đột theo hướng dẫn của hệ quản trị.

## 11. Cách kiểm tra khi kết quả đọc không như mong đợi

Khi hai câu lệnh trong cùng giao dịch trả về kết quả khác nhau hoặc dữ liệu có vẻ cũ, hãy xác định:

1. Mức cô lập thực tế của phiên kết nối tại thời điểm giao dịch chạy.
2. Hệ quản trị dùng ảnh chụp theo câu lệnh hay theo giao dịch ở mức cô lập đó.
3. Snapshot được tạo lúc bắt đầu giao dịch, ở lần đọc nhất quán đầu tiên hay lúc bắt đầu từng câu lệnh.
4. Giao dịch khác commit thay đổi trước hay sau thời điểm lấy snapshot.
5. Câu lệnh là consistent read thông thường, locking read hay thao tác ghi dùng current read.
6. Giao dịch có đọc các thay đổi do chính nó tạo ra hay không.
7. Có xung đột ghi, lỗi serialization hoặc giao dịch kéo dài làm giữ phiên bản cũ hay không.

Để tái hiện, dùng hai phiên làm việc và một lịch chạy có kiểm soát: T1 đọc lần đầu; T2 ghi và commit; T1 đọc lần hai. Ghi lại kết quả, mức cô lập và loại câu lệnh. Nếu cần xác minh thời điểm snapshot chính xác, dùng tài liệu và công cụ chẩn đoán của chính hệ quản trị.

## 12. Ghi nhớ

- MVCC giữ nhiều phiên bản để các giao dịch đọc được trạng thái phù hợp mà không phải luôn chờ giao dịch ghi.
- Ảnh chụp theo câu lệnh được làm mới cho từng câu lệnh đọc; commit mới có thể xuất hiện ở câu lệnh tiếp theo.
- Ảnh chụp theo giao dịch được giữ ổn định cho các lần đọc nhất quán trong cùng giao dịch; thay đổi commit sau mốc snapshot thường chưa xuất hiện.
- Mốc tạo snapshot không giống nhau ở mọi hệ quản trị; nó có thể gắn với thời điểm bắt đầu giao dịch hoặc lần đọc nhất quán đầu tiên.
- Snapshot isolation giúp các lần đọc nhất quán nhưng không đồng nghĩa với `SERIALIZABLE`; write skew vẫn có thể phá vỡ bất biến nghiệp vụ.
- Cần phân biệt consistent read với locking/current read, đặc biệt khi giao dịch vừa đọc snapshot vừa cập nhật dữ liệu.
- Giao dịch kéo dài có thể giữ phiên bản cũ lâu hơn, làm tăng chi phí lưu trữ và dọn dẹp.

Khi phân tích một giao dịch MVCC, hãy hỏi: **Các câu lệnh đọc của giao dịch này dùng một ảnh chụp chung hay mỗi câu lệnh lấy một ảnh chụp mới, và ảnh chụp được tạo tại thời điểm nào?**
