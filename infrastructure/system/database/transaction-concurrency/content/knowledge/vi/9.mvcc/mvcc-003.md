# Ảnh chụp (snapshot) và quy tắc quyết định phiên bản được nhìn thấy

Trong cơ sở dữ liệu sử dụng MVCC (Multi-Version Concurrency Control), một bản ghi có thể có nhiều phiên bản cùng tồn tại trong một khoảng thời gian. Khi giao dịch đọc dữ liệu, hệ quản trị cần quyết định phiên bản nào thuộc về trạng thái dữ liệu mà giao dịch được phép quan sát. **Ảnh chụp (snapshot)** mô tả ranh giới quan sát đó; **quy tắc khả kiến (visibility rules)** quyết định một phiên bản cụ thể có xuất hiện trong kết quả đọc hay không.

Hai khái niệm này giải thích vì sao một giao dịch có thể tiếp tục đọc giá trị cũ trong khi giao dịch khác đã cập nhật và commit giá trị mới. Chúng cũng giúp phân biệt snapshot theo từng câu lệnh với snapshot ổn định trong suốt giao dịch, đồng thời làm rõ những giới hạn của mức cô lập dựa trên MVCC.

## 1. MVCC lưu nhiều phiên bản như thế nào?

Với cách khóa truyền thống, một thao tác ghi thường khiến thao tác đọc xung đột phải chờ khóa được giải phóng. MVCC giảm một phần xung đột đọc-ghi bằng cách giữ lại các phiên bản dữ liệu. Giao dịch đọc có thể dùng phiên bản phù hợp với snapshot của nó, trong khi giao dịch ghi tạo ra phiên bản mới.

Ví dụ, dòng tài khoản có số dư thay đổi theo thời gian:

| Phiên bản | Số dư | Giao dịch tạo phiên bản | Ý nghĩa |
|---|---:|---|---|
| V1 | 1.000 | T10 | Giá trị ban đầu |
| V2 | 800 | T25 | Giá trị sau khi T25 rút 200 |
| V3 | 950 | T31 | Giá trị sau khi T31 nạp 150 |

Các phiên bản có thể cùng tồn tại trong kho lưu trữ vật lý hoặc cấu trúc undo/version chain của hệ quản trị. Một giao dịch đọc không nhất thiết lấy phiên bản mới nhất đang nằm trên đĩa; nó tìm phiên bản hợp lệ đối với snapshot của mình.

Một mô hình khái niệm thường gắn mỗi phiên bản với thông tin về giao dịch tạo ra nó và giao dịch kết thúc hiệu lực của nó, chẳng hạn giao dịch cập nhật hoặc xóa. Có thể hình dung metadata của phiên bản như sau:

```text
Version V1:
  value       = 1000
  created_by  = T10
  ended_by    = T25

Version V2:
  value       = 800
  created_by  = T25
  ended_by    = T31

Version V3:
  value       = 950
  created_by  = T31
  ended_by    = none
```

Đây là mô hình giải thích, không phải cấu trúc lưu trữ bắt buộc của mọi DBMS. Một số hệ quản trị dùng transaction ID và thông tin commit; một số dùng undo record, read view hoặc metadata khác để tái tạo trạng thái phù hợp.

## 2. Snapshot là gì?

Snapshot là mô tả trạng thái giao dịch mà một lần đọc được phép nhìn thấy. Tại thời điểm tạo snapshot, hệ quản trị xác định những giao dịch nào đã hoàn tất, giao dịch nào còn đang chạy và những giao dịch nào bắt đầu sau ranh giới đó. Khi đánh giá một phiên bản, hệ quản trị dùng thông tin này để quyết định phiên bản có thuộc trạng thái quan sát hay không.

Có thể hiểu snapshot như một bức ảnh logic của dữ liệu tại một ranh giới thời gian. Nó không nhất thiết là bản sao vật lý của toàn bộ database. Thay vào đó, snapshot thường là tập metadata đủ để chọn đúng phiên bản từ những phiên bản đang tồn tại.

Ví dụ, tại thời điểm T1 tạo snapshot:

```text
Thời gian ---------------------------------------------------->

T10: BEGIN ---- UPDATE V1 -> V2 ---- COMMIT
                         |
                         +---- T1 tạo snapshot

T20: BEGIN ---- UPDATE một dòng khác ---- COMMIT
```

Nếu T10 đã commit trước khi snapshot của T1 được xác lập, T1 có thể nhìn thấy phiên bản do T10 tạo. Nếu T20 bắt đầu hoặc commit sau ranh giới snapshot, các thay đổi của T20 thường không thuộc snapshot đó.

Điểm quan trọng là snapshot không chỉ là một mốc đồng hồ. Giao dịch có thể bắt đầu trước snapshot nhưng vẫn chưa commit tại thời điểm snapshot được tạo. Vì vậy, nhiều DBMS phải lưu cả danh sách hoặc khoảng trạng thái giao dịch đang hoạt động để phân biệt giao dịch đã commit với giao dịch còn đang chạy.

## 3. Quy tắc quyết định một phiên bản có được nhìn thấy hay không

Trong mô hình MVCC tổng quát, hãy xem một phiên bản có hai mốc:

- **Mốc tạo phiên bản:** giao dịch nào tạo ra phiên bản này và giao dịch đó đã commit hay chưa.
- **Mốc kết thúc hiệu lực:** giao dịch nào cập nhật hoặc xóa phiên bản này và giao dịch đó đã commit hay chưa.

Một phiên bản thường được nhìn thấy khi nó đã được tạo bởi chính giao dịch đang đọc hoặc bởi một giao dịch đã commit trước snapshot, đồng thời nó chưa bị kết thúc hiệu lực bởi một giao dịch đã commit trước snapshot. Cách diễn đạt này cần tính đến quy tắc riêng cho thao tác của chính giao dịch đọc và các trạng thái giao dịch đặc biệt của DBMS.

### 3.1. Phiên bản được tạo bởi giao dịch đã commit trước snapshot

Nếu giao dịch tạo phiên bản đã commit trước khi snapshot được xác lập, phiên bản đó có thể được nhìn thấy, miễn là chưa có thao tác cập nhật hoặc xóa đã commit trước snapshot làm nó hết hiệu lực.

Ví dụ:

```text
T10: BEGIN -> UPDATE balance = 800 -> COMMIT
T20: BEGIN -> lấy snapshot -> SELECT balance
```

T20 nhìn thấy `800`, vì thay đổi của T10 đã commit trước snapshot của T20.

### 3.2. Phiên bản được tạo bởi giao dịch còn đang chạy tại snapshot

Nếu giao dịch tạo phiên bản chưa commit tại thời điểm snapshot được xác lập, giao dịch đọc thông thường không được nhìn thấy phiên bản đó. Việc giao dịch ghi commit sau đó không làm thay đổi ngược lại snapshot đã tồn tại.

Ví dụ:

```text
T10: BEGIN -> UPDATE balance = 800 ---------------- COMMIT
T20:                 BEGIN -> lấy snapshot -> SELECT
```

Nếu T10 vẫn đang chạy khi T20 lấy snapshot, T20 tiếp tục nhìn thấy phiên bản cũ. Ngay cả khi T10 commit trước lần đọc tiếp theo của T20, kết quả còn phụ thuộc snapshot của T20 có được giữ nguyên hay được tạo mới cho câu lệnh đó.

### 3.3. Phiên bản được tạo sau snapshot

Một phiên bản được tạo bởi giao dịch bắt đầu sau snapshot không thuộc trạng thái quan sát của snapshot đó. Giao dịch đọc không nhìn thấy phiên bản chỉ vì phiên bản đã tồn tại tại thời điểm câu lệnh thực sự đọc đến dòng dữ liệu.

Đây là lý do một snapshot ổn định có thể trả về cùng một phiên bản trong nhiều lần đọc, dù giao dịch khác đã commit một giá trị mới ở giữa hai lần đọc.

### 3.4. Phiên bản bị cập nhật hoặc xóa sau snapshot

Giả sử một phiên bản đã hợp lệ tại thời điểm snapshot, nhưng giao dịch khác cập nhật hoặc xóa nó sau thời điểm đó. Giao dịch đọc dùng snapshot cũ vẫn có thể nhìn thấy phiên bản cũ, bởi thao tác kết thúc hiệu lực xảy ra sau ranh giới quan sát.

Ví dụ:

```text
T20: lấy snapshot -------------------------- SELECT
T30:             UPDATE V1 -> V2 -> COMMIT
```

Nếu T30 commit sau khi snapshot của T20 được xác lập, T20 tiếp tục nhìn thấy V1. Một giao dịch có snapshot mới hơn có thể nhìn thấy V2.

### 3.5. Thay đổi của chính giao dịch đọc

Một giao dịch thường phải nhìn thấy các thay đổi mà chính nó đã thực hiện trước đó, kể cả khi những thay đổi đó chưa commit. Nếu T1 cập nhật một dòng rồi đọc lại dòng đó, T1 phải quan sát được kết quả của chính thao tác ghi của mình theo quy tắc đọc-your-own-writes.

Do đó, quy tắc khả kiến không thể chỉ xét thời điểm commit của giao dịch khác. Hệ quản trị còn phải nhận diện transaction ID của giao dịch hiện tại và áp dụng quy tắc riêng cho các phiên bản do nó tạo hoặc kết thúc hiệu lực.

## 4. Bảng quyết định khả kiến theo snapshot

Bảng sau mô tả quy tắc khái niệm cho một giao dịch đọc T1. Giả sử phiên bản không thuộc thao tác ghi của chính T1, trừ dòng được ghi rõ:

| Trạng thái giao dịch tạo phiên bản | Thời điểm so với snapshot | Khả năng nhìn thấy |
|---|---|---|
| Đã commit | Commit trước snapshot | Có thể nhìn thấy nếu phiên bản chưa hết hiệu lực tại snapshot |
| Còn hoạt động | Đang chạy tại snapshot | Không nhìn thấy phiên bản đó |
| Bắt đầu sau snapshot | Sau snapshot | Không nhìn thấy phiên bản đó |
| Bị rollback | Bất kỳ thời điểm nào | Không nhìn thấy phiên bản do giao dịch thất bại tạo ra |
| Chính giao dịch đọc | Thay đổi do T1 tạo trước lần đọc | T1 thường nhìn thấy thay đổi của chính mình |

Với mốc kết thúc hiệu lực, áp dụng quy tắc tương ứng:

| Trạng thái giao dịch cập nhật/xóa phiên bản | Thời điểm so với snapshot | Trạng thái phiên bản cũ đối với snapshot |
|---|---|---|
| Đã commit | Commit trước snapshot | Phiên bản cũ không còn khả kiến |
| Còn hoạt động | Đang chạy tại snapshot | Phiên bản cũ vẫn có thể khả kiến |
| Commit sau snapshot | Sau snapshot | Phiên bản cũ vẫn khả kiến đối với snapshot cũ |
| Rollback | Giao dịch bị hủy | Phiên bản cũ vẫn còn hiệu lực |
| Chính giao dịch đọc | T1 tự cập nhật/xóa trước lần đọc | T1 thường thấy kết quả của thao tác do chính mình thực hiện |

Không nên áp dụng các bảng này như đặc tả triển khai cho mọi DBMS. Chúng diễn tả logic cốt lõi của MVCC; quy tắc chi tiết về transaction ID, snapshot, thao tác đọc/ghi và khóa có thể khác theo sản phẩm và mức cô lập.

## 5. Ví dụ lần theo chuỗi phiên bản

Giả sử dòng `Product.stock` bắt đầu ở giá trị 20. T10 cập nhật còn 15, sau đó T20 cập nhật còn 12.

```text
V1: stock = 20   created by T0, ended by T10
V2: stock = 15   created by T10, ended by T20
V3: stock = 12   created by T20, not ended
```

Giả sử T1 lấy snapshot khi T10 đã commit nhưng T20 vẫn đang chạy. Khi T1 đọc dòng này:

1. V1 đã bị kết thúc hiệu lực bởi T10, và T10 đã commit trước snapshot, nên V1 không còn là phiên bản phù hợp.
2. V2 được tạo bởi T10 đã commit trước snapshot.
3. V2 bị T20 kết thúc hiệu lực, nhưng T20 còn hoạt động tại snapshot; thao tác kết thúc đó chưa có hiệu lực đối với snapshot của T1.
4. V3 được T20 tạo ra trong một giao dịch còn hoạt động tại snapshot, nên T1 không nhìn thấy V3.

Kết quả T1 nhận được là `stock = 15`.

Nếu T20 commit sau đó, T1 vẫn có thể đọc `15` bằng snapshot cũ. Một giao dịch T2 lấy snapshot sau khi T20 commit có thể đọc `12`.

| Giao dịch | Thời điểm lấy snapshot | Phiên bản nhìn thấy | Giá trị |
|---|---|---|---:|
| T1 | Sau khi T10 commit, trong khi T20 còn chạy | V2 | 15 |
| T2 | Sau khi T20 commit | V3 | 12 |

Ví dụ này cho thấy trạng thái vật lý mới nhất và trạng thái logic mà một giao dịch được nhìn thấy có thể khác nhau. MVCC chọn phiên bản theo snapshot, không đơn giản chọn phiên bản có giá trị mới nhất.

## 6. Snapshot theo câu lệnh và snapshot theo giao dịch

Một điểm quan trọng của MVCC là thời điểm tạo snapshot. Hai mức cô lập có thể dùng cùng cơ chế phiên bản nhưng khác nhau ở việc snapshot được giữ trong bao lâu.

### 6.1. Snapshot mới cho mỗi câu lệnh

Ở mức cô lập kiểu Read Committed trong một số DBMS, mỗi câu lệnh đọc có thể nhận snapshot mới tại đầu câu lệnh. Nếu một giao dịch khác commit giữa hai câu `SELECT`, câu thứ hai có thể nhìn thấy dữ liệu mới hơn câu thứ nhất.

Ví dụ:

```sql
-- T1, Read Committed
BEGIN;
SELECT balance FROM account WHERE id = 7; -- trả về 100

-- Trong lúc đó T2 cập nhật balance = 130 và COMMIT.

SELECT balance FROM account WHERE id = 7; -- có thể trả về 130
COMMIT;
```

Mỗi câu lệnh đọc có snapshot riêng nên T1 có thể quan sát hai trạng thái đã commit khác nhau trong cùng một giao dịch. Hành vi chính xác của Read Committed phụ thuộc DBMS; ví dụ trên mô tả cách triển khai dùng snapshot theo câu lệnh.

### 6.2. Snapshot ổn định trong giao dịch

Ở mức cô lập kiểu Repeatable Read hoặc Snapshot Isolation, một snapshot có thể được giữ ổn định trong phạm vi giao dịch hoặc từ lần đọc đầu tiên, tùy DBMS. Những giao dịch commit sau khi snapshot được xác lập không làm thay đổi kết quả đọc của snapshot đó.

```sql
-- T1, mức cô lập có snapshot ổn định
BEGIN;
SELECT balance FROM account WHERE id = 7; -- trả về 100

-- T2 cập nhật balance = 130 và COMMIT.

SELECT balance FROM account WHERE id = 7; -- vẫn trả về 100
COMMIT;
```

Snapshot ổn định giúp các lần đọc trong một giao dịch nhất quán hơn. Tuy nhiên, nó không tự bảo đảm mọi dạng tuần tự hóa; các giao dịch vẫn có thể gặp xung đột ghi hoặc anomaly tùy mức cô lập và cách DBMS phát hiện chúng.

### 6.3. Snapshot và Serializable

Serializable yêu cầu kết quả thực thi tương đương một thứ tự tuần tự của các giao dịch. Một số hệ quản trị triển khai Serializable bằng cách theo dõi phụ thuộc đọc-ghi, phát hiện cấu trúc xung đột và hủy một giao dịch khi cần. Cơ chế đó có thể được xây dựng trên MVCC nhưng không đồng nghĩa mọi snapshot đều là Serializable.

Snapshot Isolation thường ngăn nhiều dạng đọc không nhất quán và có thể phát hiện xung đột khi hai giao dịch cập nhật cùng một dòng. Tuy vậy, nó có thể cho phép **write skew**: hai giao dịch đọc cùng một trạng thái nhất quán, rồi cập nhật hai dòng khác nhau theo cách kết hợp làm vi phạm một ràng buộc nghiệp vụ.

Ví dụ, quy tắc trực ca yêu cầu luôn có ít nhất một bác sĩ đang trực:

| Bác sĩ | Trạng thái ban đầu |
|---|---|
| An | Đang trực |
| Bình | Đang trực |

T1 đọc thấy cả An và Bình đang trực, rồi tắt trạng thái trực của An. T2 cũng đọc cùng snapshot, rồi tắt trạng thái trực của Bình. Vì hai giao dịch cập nhật hai dòng khác nhau, một cơ chế Snapshot Isolation đơn giản có thể không phát hiện xung đột ghi trực tiếp. Nếu cả hai cùng commit, không còn bác sĩ nào trực.

Để bảo vệ quy tắc này, hệ thống có thể dùng Serializable, khóa phạm vi phù hợp, một dòng điều phối chung hoặc ràng buộc được DBMS bảo vệ. Lựa chọn cụ thể phải dựa trên ngữ nghĩa nghiệp vụ và khả năng của hệ quản trị.

## 7. Snapshot có ngăn phantom không?

Phantom xảy ra khi cùng một truy vấn điều kiện trả về tập dòng khác nhau vì một giao dịch khác chèn, xóa hoặc thay đổi dòng làm nó bắt đầu hoặc ngừng thỏa điều kiện.

Ví dụ, T1 truy vấn:

```sql
SELECT *
FROM orders
WHERE total >= 1000;
```

Sau đó T2 chèn một đơn hàng có `total = 1500` và commit. Nếu T1 chạy lại truy vấn với snapshot mới, tập kết quả có thể xuất hiện dòng mới. Nếu T1 dùng snapshot ổn định, dòng được chèn sau snapshot thường không xuất hiện trong lần đọc tiếp theo của T1.

Điều đó không có nghĩa MVCC tự động giải quyết mọi phantom trong mọi mức cô lập. Cần phân biệt:

- Snapshot ổn định giữ tập dữ liệu quan sát theo một ranh giới nhất định.
- Read Committed có thể tạo snapshot mới cho mỗi câu lệnh nên truy vấn lặp lại có thể thấy dòng mới.
- Serializable phải bảo đảm tính tương đương tuần tự, có thể cần theo dõi predicate hoặc phụ thuộc để phát hiện các giao dịch tạo ra anomaly.

Khả năng ngăn phantom và cách triển khai phụ thuộc mức cô lập, loại truy vấn và DBMS.

## 8. Snapshot có loại bỏ khóa không?

Không. MVCC giảm nhu cầu để thao tác đọc thông thường phải chờ thao tác ghi, nhưng hệ quản trị vẫn có thể dùng khóa cho nhiều mục đích:

- Giao dịch ghi thường cần phối hợp với giao dịch ghi khác trên cùng dòng hoặc cùng đối tượng.
- DDL và các thao tác thay đổi cấu trúc có thể cần khóa metadata hoặc khóa bảng.
- `SELECT ... FOR UPDATE` hoặc cú pháp tương đương yêu cầu khóa để bảo vệ dòng cho thao tác cập nhật sau đó.
- Một số mức cô lập hoặc cơ chế Serializable dùng khóa phạm vi, predicate hoặc theo dõi phụ thuộc.
- Khóa vẫn được dùng để bảo vệ tính toàn vẹn và điều phối truy cập đến tài nguyên dùng chung.

Do đó, khi thấy một truy vấn đọc chạy bằng MVCC, không nên kết luận rằng truy vấn không bao giờ chờ. Nó có thể không chờ một khóa ghi trên phiên bản dữ liệu thông thường, nhưng vẫn có thể chờ khóa metadata, khóa tường minh, tài nguyên nội bộ hoặc cơ chế đồng bộ khác.

## 9. Quản lý phiên bản cũ và chi phí của snapshot dài

Để một snapshot cũ tiếp tục đọc được phiên bản phù hợp, DBMS phải giữ lại các phiên bản chưa thể xóa an toàn. Khi không còn snapshot hoặc giao dịch nào có thể cần một phiên bản cũ, hệ quản trị mới có thể thu hồi không gian của nó.

Các cơ chế dọn dẹp có tên và cách triển khai khác nhau:

- PostgreSQL dùng VACUUM để thu hồi hoặc tái sử dụng không gian của tuple cũ khi chúng không còn cần thiết đối với snapshot đang hoạt động.
- InnoDB của MySQL dùng undo log và purge để loại bỏ thông tin phiên bản cũ khi không còn cần thiết.
- Oracle dùng undo data để cung cấp consistent read và quản lý vòng đời thông tin undo.

Một giao dịch đọc kéo dài có thể giữ snapshot cũ lâu. Điều đó có thể khiến phiên bản cũ phải tồn tại lâu hơn, làm tăng lượng dữ liệu cần giữ, chi phí dọn dẹp và áp lực lưu trữ. Trong hệ thống có workload ghi lớn, snapshot quá dài có thể góp phần làm tăng bloat hoặc làm chậm quá trình purge/cleanup.

Vì vậy, nên tránh mở giao dịch rồi để nó chờ người dùng, gọi dịch vụ bên ngoài hoặc xử lý công việc dài không cần thiết. Hãy giữ transaction ngắn và chỉ bao quanh phần thao tác dữ liệu cần tính nguyên tử, nhất quán.

## 10. Cách phân tích một kết quả đọc theo snapshot

Khi một giao dịch nhìn thấy giá trị cũ hoặc không nhìn thấy một dòng mà giao dịch khác đã commit, hãy phân tích theo trình tự sau:

1. Xác định mức cô lập của giao dịch đọc và DBMS đang dùng.
2. Xác định snapshot được tạo ở đầu câu lệnh, lần đọc đầu tiên hay đầu giao dịch.
3. Xác định giao dịch tạo phiên bản cần kiểm tra và trạng thái commit/rollback của nó tại snapshot.
4. Xác định giao dịch cập nhật hoặc xóa phiên bản trước đó, cùng trạng thái của giao dịch này tại snapshot.
5. Kiểm tra phiên bản có phải do chính giao dịch đọc tạo ra hay không; giao dịch thường nhìn thấy thay đổi của chính mình.
6. Lần theo chuỗi phiên bản để tìm phiên bản mới nhất còn hợp lệ đối với snapshot.
7. Nếu kết quả thay đổi giữa hai lần đọc, kiểm tra xem DBMS có tạo snapshot mới cho câu lệnh thứ hai hay không.
8. Nếu vấn đề liên quan đến anomaly nghiệp vụ, kiểm tra mức cô lập có bảo vệ quy tắc đó hay cần khóa/ràng buộc/Serializable.

Một bảng ghi chép đơn giản có thể giúp phân tích:

| Câu hỏi | Thông tin cần tìm |
|---|---|
| Snapshot bắt đầu lúc nào? | Đầu câu lệnh, lần đọc đầu tiên hay đầu giao dịch |
| Phiên bản được tạo bởi ai? | Transaction ID hoặc metadata tương ứng |
| Giao dịch tạo phiên bản đã commit chưa? | Trạng thái tại ranh giới snapshot |
| Phiên bản bị thay thế/xóa bởi ai? | Giao dịch kết thúc hiệu lực |
| Giao dịch kết thúc hiệu lực đã commit chưa? | Trạng thái tại ranh giới snapshot |
| Có phải thay đổi của chính giao dịch đọc? | Transaction ID của giao dịch hiện tại |
| Snapshot có được làm mới không? | Quy tắc theo mức cô lập và DBMS |

## 11. Những nhầm lẫn thường gặp

**Snapshot là bản sao vật lý của toàn bộ database.** Thông thường không phải. Snapshot thường là metadata mô tả ranh giới khả kiến; DBMS dùng metadata đó để chọn phiên bản từ cấu trúc lưu trữ hiện có.

**Giao dịch luôn đọc phiên bản mới nhất.** Không đúng. Giao dịch đọc phiên bản hợp lệ đối với snapshot của nó. Một phiên bản mới hơn có thể đã commit nhưng vẫn nằm ngoài snapshot cũ.

**Giao dịch khác commit thì mọi lần đọc sau của tôi đều thấy dữ liệu mới.** Điều này phụ thuộc thời điểm snapshot được tạo. Với snapshot ổn định, giao dịch có thể tiếp tục nhìn thấy trạng thái cũ đến khi kết thúc; với snapshot theo câu lệnh, câu lệnh tiếp theo có thể thấy dữ liệu mới.

**MVCC có nghĩa là không có khóa và không có chờ đợi.** Không đúng. MVCC giảm một số xung đột đọc-ghi, nhưng ghi, DDL, khóa tường minh và các cơ chế đồng bộ khác vẫn có thể gây chờ.

**Repeatable Read luôn giống nhau ở mọi DBMS.** Không đúng. Tên mức cô lập có thể gắn với hành vi snapshot và bảo vệ anomaly khác nhau. Cần xem tài liệu của DBMS cụ thể.

**Snapshot Isolation tương đương Serializable.** Không đúng. Snapshot Isolation có thể cho phép write skew hoặc anomaly khác. Serializable cần cơ chế bảo đảm tương đương một thứ tự tuần tự.

**Phiên bản cũ có thể xóa ngay sau khi phiên bản mới commit.** Không đúng. Nếu còn snapshot có thể cần phiên bản cũ, DBMS phải giữ lại nó cho đến khi an toàn để thu hồi.

## 12. Kết luận về cách chọn phiên bản

Khi đọc bằng MVCC, hệ quản trị không chỉ hỏi “giá trị nào mới nhất?” mà hỏi “phiên bản nào hợp lệ đối với snapshot của giao dịch này?”. Để trả lời, nó xét giao dịch tạo phiên bản, giao dịch cập nhật hoặc xóa phiên bản, trạng thái commit của các giao dịch tại ranh giới snapshot và các thay đổi do chính giao dịch đọc thực hiện.

Thời điểm tạo snapshot quyết định phạm vi dữ liệu được quan sát. Snapshot theo câu lệnh có thể cho phép các câu lệnh liên tiếp thấy trạng thái commit khác nhau; snapshot ổn định giúp các lần đọc giữ cùng một góc nhìn trong thời gian dài hơn. Mức cô lập cao hơn còn phải xử lý các phụ thuộc và anomaly mà chỉ chọn phiên bản nhất quán chưa đủ để ngăn chặn.

Khi vận hành hoặc thiết kế ứng dụng, hãy xác định chính xác DBMS, mức cô lập và thời điểm tạo snapshot trước khi giải thích một kết quả đọc. Đó là cơ sở để lần theo phiên bản, hiểu vì sao giá trị cũ còn được nhìn thấy và chọn cơ chế bảo vệ phù hợp với quy tắc nghiệp vụ.
