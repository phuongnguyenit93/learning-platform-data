# Điều khiển đồng thời đa phiên bản (MVCC) giải quyết vấn đề gì?

Một hệ quản trị cơ sở dữ liệu thường phải phục vụ nhiều giao dịch cùng lúc. Trong cùng một khoảng thời gian, một giao dịch có thể đang đọc số dư tài khoản trong khi giao dịch khác cập nhật số dư đó; một báo cáo có thể đọc hàng nghìn bản ghi trong khi ứng dụng vẫn tiếp tục ghi dữ liệu. Nếu mọi thao tác đọc và ghi đều phải chờ nhau, hệ thống sẽ giảm khả năng xử lý đồng thời và những giao dịch đọc lâu có thể làm chậm các giao dịch cập nhật.

**Điều khiển đồng thời đa phiên bản (Multi-Version Concurrency Control - MVCC)** là kỹ thuật quản lý nhiều phiên bản của cùng một dữ liệu để các giao dịch đọc có thể nhìn thấy phiên bản phù hợp với thời điểm đọc của chúng. Thay vì buộc mọi thao tác đọc phải chờ giao dịch ghi kết thúc, hệ quản trị có thể cho giao dịch đọc sử dụng một phiên bản đã commit, trong khi giao dịch ghi tạo phiên bản mới.

MVCC chủ yếu giải quyết xung đột giữa **đọc và ghi**: giảm việc người đọc chặn người ghi và người ghi chặn người đọc, đồng thời cung cấp một góc nhìn dữ liệu nhất quán theo snapshot của giao dịch hoặc câu lệnh. MVCC không loại bỏ mọi khóa và cũng không tự động giải quyết mọi xung đột giữa các giao dịch ghi.

## 1. Vấn đề khi đọc và ghi phải chờ nhau

Trong mô hình điều khiển đồng thời dựa nhiều vào khóa, giao dịch đọc có thể lấy khóa chia sẻ (`S`), còn giao dịch cập nhật cần khóa độc quyền (`X`). Hai chế độ này xung đột trên cùng tài nguyên. Nếu khóa đọc được giữ trong thời gian giao dịch, một giao dịch đọc lâu có thể khiến giao dịch cập nhật phải chờ. Ngược lại, giao dịch đang giữ khóa ghi có thể khiến giao dịch đọc có khóa phải chờ.

Ví dụ, T1 chạy báo cáo và đọc số dư tài khoản. Trong khi T1 vẫn giữ khóa đọc, T2 cần trừ tiền từ cùng tài khoản:

```text
Thời điểm     Giao dịch T1 (đọc)             Giao dịch T2 (ghi)
---------------------------------------------------------------------
1             BEGIN
2             Đọc account(10), lấy S
3                                             BEGIN
4                                             UPDATE account(10), cần X
5                                             Chờ T1 nhả S
6             Tiếp tục xử lý báo cáo
7             COMMIT, nhả S
8                                             Lấy X, cập nhật và COMMIT
```

T2 không thể hoàn thành cập nhật ở thời điểm 4 vì khóa `X` không tương thích với khóa `S` của T1. Nếu T1 đọc nhiều dữ liệu hoặc thực hiện thêm công việc trước khi commit, thời gian chờ của T2 có thể kéo dài.

Việc để người đọc và người ghi chờ nhau gây ra một số vấn đề:

- **Giảm thông lượng:** nhiều giao dịch phải xếp hàng dù thao tác đọc và ghi có thể sử dụng những phiên bản dữ liệu khác nhau.
- **Tăng độ trễ:** một truy vấn báo cáo hoặc giao dịch đọc lâu có thể làm chậm thao tác cập nhật của ứng dụng.
- **Khó duy trì tải đọc lớn:** hệ thống vừa phục vụ truy vấn đọc vừa tiếp nhận cập nhật có thể phát sinh nhiều tranh chấp khóa.
- **Khó có góc nhìn ổn định khi đọc nhiều dữ liệu:** nếu mỗi lần đọc nhìn thấy trạng thái khác nhau, một báo cáo có thể kết hợp các giá trị thuộc những thời điểm khác nhau, tùy mức cô lập và cách triển khai.

Khóa vẫn cần thiết để bảo vệ tính đúng đắn của dữ liệu. Vấn đề nằm ở chỗ một thao tác chỉ cần đọc dữ liệu có thể phải chờ một thao tác ghi, hoặc một thao tác ghi phải chờ một giao dịch đọc đang giữ khóa trong thời gian dài.

## 2. MVCC thay đổi cách đọc dữ liệu như thế nào?

MVCC giữ lại nhiều phiên bản của một hàng dữ liệu trong một khoảng thời gian. Khi giao dịch cập nhật một hàng, hệ quản trị tạo hoặc ghi nhận phiên bản mới thay vì bắt mọi giao dịch đọc phải đợi cho đến khi việc cập nhật kết thúc. Giao dịch đọc chọn phiên bản mà nó được phép nhìn thấy theo snapshot và quy tắc hiển thị của hệ quản trị.

Quy trình khái quát:

1. Một giao dịch bắt đầu đọc và có một snapshot xác định những thay đổi nào đã commit mà nó được phép nhìn thấy.
2. Giao dịch khác cập nhật một hàng. Hệ quản trị tạo phiên bản mới và thực hiện việc ghi theo cơ chế của nó.
3. Trong lúc cập nhật chưa commit, giao dịch đọc tiếp tục nhìn thấy phiên bản cũ phù hợp với snapshot; nó không đọc dữ liệu chưa commit của giao dịch ghi.
4. Khi giao dịch ghi commit, phiên bản mới trở thành phiên bản có thể được những snapshot phù hợp nhìn thấy.
5. Phiên bản cũ được giữ lại khi vẫn có giao dịch cần đọc nó. Sau khi không còn snapshot nào cần phiên bản đó, hệ quản trị có thể thu hồi hoặc dọn dẹp nó.

```text
                  Cùng một hàng account(10)

Phiên bản V1: balance = 1.000.000  (đã commit)
       |
       | T2 cập nhật, tạo phiên bản mới
       v
Phiên bản V2: balance =   900.000  (đang được T2 ghi)

T1 có snapshot cũ  --------------------> đọc V1
T2 đang cập nhật ---------------------> tạo V2
Sau khi T2 COMMIT:
  - snapshot cũ của T1 vẫn có thể nhìn thấy V1
  - snapshot mới phù hợp có thể nhìn thấy V2
```

Sơ đồ mô tả ý tưởng chung. Cách lưu phiên bản, cách xác định giao dịch tạo phiên bản, cách tạo snapshot và thời điểm dọn dẹp khác nhau giữa các hệ quản trị. Một số hệ thống lưu phiên bản cũ trong chính cấu trúc hàng; hệ thống khác có thể dùng vùng lưu trữ undo hoặc cơ chế tương đương.

## 3. MVCC giải quyết xung đột đọc - ghi

Điểm quan trọng nhất của MVCC là **đọc có thể tiếp tục trên phiên bản phù hợp trong khi một giao dịch khác đang ghi phiên bản mới**. Vì vậy, một truy vấn đọc thông thường thường không cần lấy khóa hàng chia sẻ có khả năng chặn cập nhật.

Xét lại tình huống T1 đọc và T2 cập nhật cùng một tài khoản:

```text
Thời điểm     Giao dịch T1 (đọc)             Giao dịch T2 (ghi)
---------------------------------------------------------------------
1             BEGIN, lấy snapshot
2             Đọc balance = 1.000.000
3                                             BEGIN
4                                             Tạo phiên bản balance = 900.000
5             Đọc tiếp phiên bản phù hợp
6                                             COMMIT
7             Tiếp tục đọc snapshot của mình
8             COMMIT
```

T1 có thể tiếp tục đọc phiên bản cũ trong khi T2 tạo và commit phiên bản mới. T1 không nhìn thấy dữ liệu chưa commit của T2. Tùy mức cô lập, snapshot của T1 được cố định ở đầu giao dịch hoặc được tạo lại ở đầu mỗi câu lệnh; điều này quyết định T1 có nhìn thấy thay đổi vừa commit ở lần đọc kế tiếp hay không.

Điều này hữu ích cho:

- **Ứng dụng đọc nhiều:** màn hình danh sách, tra cứu, tìm kiếm và API đọc có thể tiếp tục phục vụ khi dữ liệu đang được cập nhật.
- **Báo cáo và phân tích:** một truy vấn dài có thể đọc dữ liệu theo snapshot mà không phải giữ khóa đọc chặn các thao tác ghi trong suốt quá trình xử lý.
- **Hệ thống có nhiều thao tác đọc và cập nhật xen kẽ:** giảm tranh chấp giữa người đọc và người ghi, từ đó cải thiện khả năng đồng thời trong các tải công việc phù hợp.
- **Đọc nhất quán:** nhiều lần đọc trong cùng snapshot có thể nhìn thấy cùng một trạng thái dữ liệu logic, tùy mức cô lập được chọn.

MVCC không có nghĩa mọi truy vấn đọc đều không bao giờ chờ. Truy vấn đọc yêu cầu khóa tường minh, truy vấn phải chờ tài nguyên khác, hoặc thao tác liên quan đến metadata có thể vẫn phải chờ theo quy tắc của hệ quản trị.

## 4. MVCC giúp tránh đọc dữ liệu chưa commit

Một mục tiêu khác của MVCC là cho phép giao dịch đọc chọn phiên bản đã commit phù hợp thay vì đọc phần dữ liệu mà giao dịch khác đang sửa dở. Điều này giúp tránh **dirty read** trong các mức cô lập không cho phép dirty read.

Ví dụ:

1. T1 bắt đầu cập nhật số dư từ 1.000.000 thành 500.000 nhưng chưa commit.
2. T2 chạy truy vấn đọc số dư.
3. T2 nhìn thấy phiên bản đã commit trước đó là 1.000.000, thay vì đọc giá trị chưa commit là 500.000.
4. Nếu T1 rollback, giá trị 500.000 không bao giờ trở thành dữ liệu đã commit; T2 không bị ảnh hưởng bởi thay đổi dở dang đó.

```text
Giá trị đã commit trước đó: 1.000.000
T1 ghi giá trị mới:            500.000 (chưa commit)

T2 đọc theo snapshot:        1.000.000

Nếu T1 COMMIT: phiên bản mới có thể hiển thị với snapshot mới.
Nếu T1 ROLLBACK: phiên bản chưa commit bị loại bỏ theo cơ chế của hệ quản trị.
```

Đây là một lợi ích của cơ chế quản lý phiên bản, nhưng cần diễn đạt chính xác: **MVCC không tự đặt mọi giao dịch vào mức cô lập cao nhất**. Mức cô lập và quy tắc snapshot vẫn quyết định những hiện tượng mà giao dịch có thể quan sát. Một hệ quản trị có thể hỗ trợ `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` với hành vi cụ thể riêng; ở mức cho phép dirty read, hành vi cũng phụ thuộc cách hệ quản trị triển khai mức đó.

## 5. Snapshot giúp đọc nhất quán như thế nào?

Snapshot là góc nhìn dữ liệu mà một giao dịch hoặc câu lệnh được phép quan sát. Nó giúp hệ quản trị xác định phiên bản nào của mỗi hàng có thể được đọc.

Giả sử số dư ban đầu là 1.000.000. T1 bắt đầu giao dịch và đọc số dư. Sau đó T2 trừ 100.000 và commit. T1 đọc lại số dư:

```text
Thời điểm     T1                                  T2
----------------------------------------------------------------
1             BEGIN
2             SELECT balance -> 1.000.000
3                                                 BEGIN
4                                                 UPDATE balance = 900.000
5                                                 COMMIT
6             SELECT balance -> phụ thuộc snapshot
7             COMMIT
```

Kết quả ở bước 6 phụ thuộc mức cô lập và hệ quản trị:

- Với snapshot được giữ ở cấp giao dịch, T1 tiếp tục nhìn thấy 1.000.000 trong lần đọc thứ hai.
- Với snapshot mới cho mỗi câu lệnh, T1 có thể nhìn thấy 900.000 trong lần đọc thứ hai vì T2 đã commit trước khi câu lệnh đó bắt đầu.

Ví dụ này cho thấy MVCC không chỉ là giữ nhiều bản sao dữ liệu. Nó còn cần một quy tắc xác định **giao dịch nào được nhìn thấy phiên bản nào**. Quy tắc đó gắn với mức cô lập và thời điểm tạo snapshot.

### Read Committed và Repeatable Read

Tên và chi tiết triển khai mức cô lập có thể khác nhau giữa các hệ quản trị, nhưng có thể hình dung hai cách tạo snapshot thường gặp:

| Cách đọc | Snapshot thường được xác định khi nào? | Hệ quả với ví dụ T1/T2 |
|---|---|---|
| `READ COMMITTED` | Thường tại đầu mỗi câu lệnh đọc | Câu lệnh sau của T1 có thể nhìn thấy thay đổi T2 đã commit |
| `REPEATABLE READ` theo snapshot | Thường tại đầu giao dịch | T1 tiếp tục nhìn thấy cùng snapshot trong các lần đọc của giao dịch |

Đây là mô tả khái quát. Ví dụ, PostgreSQL và InnoDB của MySQL có các chi tiết khác nhau về snapshot, khóa và cách xử lý xung đột ở từng mức cô lập. Khi cần dự đoán chính xác kết quả, phải xét tài liệu của sản phẩm và phiên bản đang dùng.

## 6. MVCC hoạt động cùng cơ chế khóa

Một hiểu lầm phổ biến là MVCC thay thế hoàn toàn khóa. Trên thực tế, nhiều hệ quản trị kết hợp MVCC với khóa và các cơ chế kiểm tra xung đột khác.

- Truy vấn `SELECT` thông thường có thể đọc phiên bản phù hợp mà không cần khóa hàng chia sẻ chặn người ghi.
- Câu lệnh `UPDATE` hoặc `DELETE` vẫn phải điều phối quyền sửa cùng một hàng. Hai giao dịch cùng cập nhật một hàng có thể phải chờ nhau hoặc một giao dịch có thể bị báo xung đột.
- Truy vấn như `SELECT ... FOR UPDATE` hoặc `SELECT ... FOR SHARE` yêu cầu khóa rõ ràng để phối hợp với giao dịch khác.
- Khóa bảng, khóa metadata, khóa ngoại, khóa phạm vi và các cơ chế bảo vệ cấu trúc dữ liệu vẫn có thể được sử dụng.

Do đó, cách hiểu phù hợp là: **MVCC giảm nhu cầu để thao tác đọc thông thường tranh chấp khóa với thao tác ghi; khóa vẫn bảo vệ những thao tác cần quyền truy cập loại trừ hoặc cần phối hợp cập nhật.**

## 7. MVCC không giải quyết mọi xung đột giao dịch

MVCC cải thiện khả năng đọc đồng thời, nhưng vẫn có những tình huống cần khóa, kiểm tra xung đột hoặc mức cô lập cao hơn.

### Xung đột ghi - ghi

Nếu T1 và T2 cùng cập nhật một hàng, cả hai không thể tùy ý ghi đè phiên bản của nhau. Hệ quản trị phải tuần tự hóa thao tác ghi trên hàng đó, chờ một giao dịch, từ chối một cập nhật hoặc xử lý xung đột theo quy tắc của nó.

Ví dụ, hai giao dịch cùng đọc số dư 1.000.000 rồi mỗi giao dịch tính ra một giá trị mới. Nếu ứng dụng ghi lại toàn bộ giá trị đã tính từ bản đọc cũ, có nguy cơ mất cập nhật (*lost update*) nếu không có cơ chế bảo vệ phù hợp. Có thể dùng câu lệnh cập nhật nguyên tử, khóa đọc để cập nhật, hoặc cột phiên bản và optimistic locking tùy nghiệp vụ.

```sql
-- Cập nhật nguyên tử: cơ sở dữ liệu thực hiện phép trừ trên giá trị hiện hành
UPDATE account
SET balance = balance - 100000
WHERE id = 10;
```

Ví dụ này tránh mô hình ứng dụng tự đọc số dư, tính số mới ở bên ngoài rồi ghi đè toàn bộ giá trị cũ. Điều kiện nghiệp vụ như số dư không âm vẫn cần được bảo vệ bằng constraint, điều kiện `WHERE` hoặc cơ chế phù hợp.

### Deadlock vẫn có thể xảy ra

Các thao tác ghi vẫn có thể lấy khóa trên nhiều hàng theo thứ tự khác nhau. Nếu T1 giữ khóa hàng A và chờ hàng B, trong khi T2 giữ B và chờ A, hệ quản trị có thể phát hiện deadlock và hủy một giao dịch. MVCC không loại bỏ chu trình chờ giữa các khóa ghi.

### Write skew và các bất biến liên hàng

Ở mức snapshot isolation, hai giao dịch có thể đọc cùng một snapshot rồi cập nhật những hàng khác nhau. Mỗi giao dịch riêng lẻ không nhất thiết xung đột ở cấp hàng, nhưng kết quả kết hợp có thể vi phạm một quy tắc nghiệp vụ liên quan nhiều hàng. Hiện tượng này thường được gọi là *write skew*.

Ví dụ, một lịch trực yêu cầu luôn có ít nhất một bác sĩ đang trực. T1 đọc thấy bác sĩ A và B đều đang trực rồi tắt trạng thái trực của A. Đồng thời T2 cũng đọc cùng snapshot rồi tắt trạng thái trực của B. Nếu hai giao dịch chỉ cập nhật hai hàng riêng biệt và không có kiểm tra bổ sung, kết quả cuối cùng có thể là không còn ai trực.

Để bảo vệ bất biến liên hàng, có thể cần constraint phù hợp, khóa một tài nguyên điều phối chung, thiết kế cập nhật nguyên tử hoặc mức `SERIALIZABLE` với cơ chế phát hiện và từ chối lịch thực thi không tuần tự hóa được. MVCC tự nó không bảo đảm mọi lịch giao dịch tương đương một thứ tự tuần tự.

## 8. Chi phí và giới hạn của việc giữ nhiều phiên bản

Giữ nhiều phiên bản giúp giảm chờ giữa đọc và ghi, nhưng cũng tạo chi phí quản lý:

- **Dung lượng lưu trữ:** phiên bản cũ cần không gian cho đến khi không còn giao dịch nào cần đọc.
- **Dọn dẹp phiên bản:** hệ quản trị phải xác định phiên bản nào đã lỗi thời và có thể thu hồi an toàn.
- **Giao dịch kéo dài:** một snapshot tồn tại lâu có thể khiến phiên bản cũ phải được giữ lại lâu hơn, làm tăng dung lượng hoặc làm chậm quá trình dọn dẹp.
- **Chi phí tìm phiên bản:** khi một hàng có nhiều phiên bản, hệ quản trị phải xác định đúng phiên bản hiển thị cho snapshot hiện tại.
- **Tranh chấp ghi:** MVCC không loại bỏ thời gian chờ giữa các giao dịch cùng sửa dữ liệu.

Tên và cơ chế dọn dẹp phụ thuộc sản phẩm. PostgreSQL có quy trình VACUUM để thu hồi không gian từ các phiên bản không còn cần thiết; InnoDB của MySQL dùng undo log và purge để quản lý phiên bản cũ. Người vận hành cần theo dõi giao dịch chạy lâu, lượng phiên bản cũ và tình trạng dọn dẹp theo hướng dẫn của hệ quản trị.

## 9. Ví dụ SQL minh họa hành vi đọc và ghi

Ví dụ dưới đây mô tả hai phiên làm việc. Cú pháp `FOR UPDATE` và hành vi đọc snapshot phải được đối chiếu với hệ quản trị cụ thể; đoạn đầu dùng một truy vấn đọc thông thường để minh họa lợi ích phổ biến của MVCC.

```sql
-- Phiên T1: giao dịch đọc
BEGIN;

SELECT balance
FROM account
WHERE id = 10;

-- T1 tiếp tục xử lý trong khi giao dịch khác cập nhật.
-- Ở mức snapshot cấp giao dịch, lần đọc tiếp theo dùng snapshot đó.

SELECT balance
FROM account
WHERE id = 10;

COMMIT;
```

```sql
-- Phiên T2: giao dịch ghi chạy xen kẽ với T1
BEGIN;

UPDATE account
SET balance = balance - 100000
WHERE id = 10;

COMMIT;
```

Trong hệ quản trị MVCC, truy vấn đọc thông thường của T1 thường có thể đọc phiên bản phù hợp trong khi T2 ghi. Nếu T1 dùng `READ COMMITTED`, hai câu `SELECT` có thể thấy hai snapshot khác nhau. Nếu T1 dùng mức snapshot cấp giao dịch, cả hai câu có thể thấy cùng phiên bản cũ. Hành vi cụ thể phải dựa trên mức cô lập và hệ quản trị.

Nếu T1 cần đọc hàng và bảo đảm giao dịch khác không cập nhật hàng đó trước khi T1 quyết định ghi, T1 có thể cần một truy vấn khóa tường minh, chẳng hạn `SELECT ... FOR UPDATE` ở hệ quản trị hỗ trợ cú pháp này. Khi đó, mục tiêu đã chuyển từ đọc snapshot không chặn ghi sang chủ động phối hợp quyền cập nhật bằng khóa.

## 10. Khi nào MVCC đặc biệt hữu ích?

MVCC thường có lợi khi tải công việc có nhiều truy vấn đọc xen kẽ với cập nhật, nhất là khi truy vấn đọc có thể kéo dài hơn thao tác ghi. Các ví dụ điển hình gồm:

- Website có nhiều người dùng xem danh sách, chi tiết và trạng thái đơn hàng trong lúc đơn hàng vẫn được cập nhật.
- Hệ thống quản trị có truy vấn thống kê và báo cáo chạy song song với giao dịch nghiệp vụ.
- Dịch vụ có nhiều API đọc, nơi độ trễ truy vấn quan trọng và việc chặn đọc - ghi làm giảm thông lượng.
- Tác vụ cần đọc một tập dữ liệu nhất quán trong khi các giao dịch khác tiếp tục cập nhật dữ liệu.

MVCC không tự động làm mọi truy vấn nhanh hơn. Truy vấn vẫn cần chỉ mục và kế hoạch thực thi phù hợp; việc giữ phiên bản cũ có thể tăng dung lượng; tải ghi nặng trên cùng một tập hàng vẫn có thể tranh chấp. Lợi ích thực tế phụ thuộc tỷ lệ đọc/ghi, thời gian giao dịch, mức cô lập, cấu trúc dữ liệu và cách hệ quản trị triển khai MVCC.

## 11. Cách phân tích một tình huống MVCC

Khi hai giao dịch cùng truy cập dữ liệu và cần hiểu vì sao chúng có thể chạy song song hoặc phải chờ nhau, hãy lần lượt xác định:

1. **Thao tác là đọc hay ghi?** Một `SELECT` thông thường có thể có hành vi khác với `SELECT ... FOR UPDATE`.
2. **Snapshot được tạo khi nào?** Ở đầu câu lệnh hay đầu giao dịch? Snapshot có được giữ qua nhiều lần đọc không?
3. **Phiên bản nào đã commit và phiên bản nào còn chưa commit?** Giao dịch đọc chỉ được nhìn thấy những phiên bản phù hợp với quy tắc hiển thị.
4. **Có hai giao dịch cùng ghi một hàng không?** Nếu có, cần xét cơ chế khóa và xử lý xung đột ghi.
5. **Có bất biến liên quan nhiều hàng không?** Snapshot isolation có thể chưa đủ để bảo vệ các quy tắc này.
6. **Phiên bản cũ còn được giao dịch nào cần không?** Giao dịch kéo dài có thể làm chậm việc thu hồi phiên bản cũ.

## 12. Những điểm cốt lõi

- MVCC giữ nhiều phiên bản dữ liệu để giao dịch đọc có thể chọn phiên bản phù hợp với snapshot của mình.
- Nó chủ yếu giảm xung đột đọc - ghi: người đọc không cần chờ mọi cập nhật và người ghi không phải luôn chờ truy vấn đọc thông thường.
- Snapshot giúp giao dịch đọc dữ liệu nhất quán theo quy tắc của mức cô lập.
- Giao dịch đọc không nhìn thấy thay đổi chưa commit trong các mức cô lập không cho phép dirty read.
- MVCC vẫn kết hợp với khóa hoặc cơ chế kiểm tra xung đột để điều phối ghi, khóa tường minh và các thao tác đặc biệt.
- Xung đột ghi - ghi, deadlock và write skew vẫn cần được xử lý bằng thiết kế giao dịch, constraint, khóa hoặc mức cô lập phù hợp.
- Giữ phiên bản cũ tạo chi phí lưu trữ và dọn dẹp; giao dịch kéo dài có thể làm chi phí này tăng lên.

Khi một hệ thống có nhiều thao tác đọc và ghi đồng thời, MVCC giúp giảm thời gian chờ bằng cách cho người đọc sử dụng phiên bản dữ liệu phù hợp thay vì buộc họ tranh chấp trực tiếp với người ghi. Việc chọn mức cô lập và cơ chế bảo vệ cập nhật vẫn quyết định tính đúng đắn của toàn bộ giao dịch.
