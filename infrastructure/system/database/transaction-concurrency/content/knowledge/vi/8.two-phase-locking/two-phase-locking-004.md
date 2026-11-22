# Rigorous 2PL và việc giữ khóa đọc lẫn khóa ghi

Trong một hệ quản trị cơ sở dữ liệu, hai giao dịch có thể cùng truy cập một dữ liệu trong lúc chạy. Nếu một giao dịch đang đọc một tài khoản trong khi giao dịch khác cập nhật số dư của tài khoản đó, hệ thống phải quyết định giao dịch nào được tiếp tục và giao dịch nào phải chờ. Cơ chế khóa (locking) giải quyết vấn đề này bằng cách yêu cầu giao dịch xin quyền truy cập dữ liệu trước khi đọc hoặc ghi.

Rigorous Two-Phase Locking (Rigorous 2PL) là một biến thể của giao thức khóa hai pha. Điểm phân biệt quan trọng của nó nằm ở thời điểm giải phóng khóa: giao dịch giữ **cả khóa đọc lẫn khóa ghi cho đến khi commit hoặc abort**. Vì vậy, một giao dịch khác không thể ghi đè dữ liệu mà giao dịch hiện tại đang đọc, cũng không thể đọc hoặc ghi dữ liệu mà giao dịch hiện tại đang sửa, cho đến khi giao dịch hiện tại kết thúc.

## 1. Nhắc lại khóa đọc và khóa ghi

Một khóa biểu thị quyền truy cập của giao dịch lên một đối tượng dữ liệu, chẳng hạn một hàng, một trang dữ liệu hoặc cả một bảng. Hai chế độ khóa cơ bản thường dùng là:

- **Shared lock (S-lock, khóa chia sẻ/khóa đọc):** giao dịch cần đọc dữ liệu sẽ xin S-lock. Nhiều giao dịch có thể cùng giữ S-lock trên một đối tượng vì các thao tác đọc không làm thay đổi dữ liệu.
- **Exclusive lock (X-lock, khóa độc quyền/khóa ghi):** giao dịch cần ghi hoặc cập nhật dữ liệu sẽ xin X-lock. Khi một giao dịch giữ X-lock, giao dịch khác không được giữ S-lock hoặc X-lock trên cùng đối tượng.

> Bảng tương thích khóa cho một đối tượng dữ liệu:

| Khóa đang được giữ | Yêu cầu S-lock | Yêu cầu X-lock |
| --- | --- | --- |
| S-lock | Được cấp | Phải chờ |
| X-lock | Phải chờ | Phải chờ |

Có thể đọc bảng theo cách sau:

- S-lock tương thích với S-lock: nhiều giao dịch được đọc cùng một dữ liệu.
- S-lock xung đột với X-lock: một giao dịch đang đọc theo giao thức khóa sẽ chặn giao dịch khác ghi dữ liệu đó.
- X-lock xung đột với cả S-lock và X-lock: khi một giao dịch đang ghi, giao dịch khác phải chờ trước khi đọc hoặc ghi cùng dữ liệu.

Khóa không nhất thiết được đặt trên từng cột. Tùy hệ quản trị và mức khóa (lock granularity), khóa có thể áp dụng cho hàng, trang, bảng hoặc phạm vi dữ liệu. Đối tượng bị khóa càng lớn thì việc quản lý có thể đơn giản hơn, nhưng nhiều giao dịch không liên quan cũng có thể phải chờ nhau.

## 2. Nguyên tắc hai pha (Two-Phase Locking)

Giao thức Two-Phase Locking (2PL) chia vòng đời khóa của một giao dịch thành hai pha:

1. **Growing phase (pha tăng trưởng):** giao dịch được xin thêm khóa và có thể nâng cấp S-lock thành X-lock. Trong pha này, giao dịch chưa được giải phóng khóa.
2. **Shrinking phase (pha thu hẹp):** giao dịch bắt đầu giải phóng khóa. Sau khi đã giải phóng khóa đầu tiên, giao dịch không được xin thêm khóa mới hoặc nâng cấp khóa nữa.

Ranh giới giữa hai pha là thời điểm giao dịch giải phóng khóa đầu tiên. Một giao dịch có thể giữ nhiều khóa trong pha tăng trưởng; khi bước sang pha thu hẹp, số khóa nó giữ chỉ có thể giảm.

Ví dụ một giao dịch đọc A rồi cập nhật B:

```text
BEGIN
  S-lock(A)
  read(A)

  X-lock(B)
  write(B)

  COMMIT
  unlock(A)
  unlock(B)
```

Giao dịch lấy khóa trên A và B trước khi giải phóng khóa nào, nên việc lấy khóa tuân theo pha tăng trưởng. Khi commit, giao dịch giải phóng các khóa và kết thúc. Đây cũng là hình thức giữ khóa mà Rigorous 2PL áp dụng: tất cả khóa được giữ đến cuối giao dịch.

2PL có ý nghĩa về tính đúng đắn: nếu mọi giao dịch đều tuân theo giao thức, lịch thực thi thu được là **conflict-serializable** (khả tuần tự theo xung đột). Nói cách khác, kết quả của các thao tác đọc/ghi có thể được xem như kết quả của một thứ tự chạy tuần tự nào đó, dù hệ thống thực tế có thể xen kẽ các thao tác của nhiều giao dịch.

Tuy nhiên, quy tắc hai pha cơ bản chỉ giới hạn thứ tự lấy và nhả khóa. Nó không bắt buộc mọi khóa phải được giữ đến commit. Một giao dịch có thể bắt đầu nhả khóa trước khi commit, miễn là sau khi đã nhả thì không lấy thêm khóa. Sự khác nhau giữa các biến thể 2PL nằm chủ yếu ở việc chúng giữ loại khóa nào đến thời điểm kết thúc.

## 3. Rigorous 2PL hoạt động như thế nào?

Rigorous 2PL yêu cầu một giao dịch giữ **mọi S-lock và X-lock** mà nó đã lấy cho đến khi giao dịch commit hoặc abort. Trước thời điểm đó, giao dịch không giải phóng khóa đọc hay khóa ghi.

Quy trình khái quát:

1. Khi cần đọc một đối tượng, giao dịch xin S-lock trên đối tượng đó.
2. Khi cần ghi, giao dịch xin X-lock. Nếu đang giữ S-lock và sau đó cần ghi cùng đối tượng, giao dịch có thể yêu cầu nâng cấp S-lock lên X-lock.
3. Nếu khóa yêu cầu không tương thích với khóa đang được giao dịch khác giữ, yêu cầu bị đặt vào trạng thái chờ.
4. Khi giao dịch commit hoặc abort, hệ thống mới giải phóng toàn bộ khóa mà giao dịch đang giữ.

Vì S-lock cũng được giữ đến cuối giao dịch, một giao dịch đọc có thể làm giao dịch ghi phải chờ. Đây là đặc điểm quan trọng nhất để phân biệt Rigorous 2PL với Strict 2PL theo định nghĩa phổ biến trong sách giáo khoa.

### Ví dụ: khóa đọc chặn giao dịch ghi

Giả sử A là số lượng sản phẩm còn trong kho. T1 cần đọc số lượng để tính toán, còn T2 muốn cập nhật số lượng đó.

| Thời điểm | Giao dịch T1 | Giao dịch T2 |
| --- | --- | --- |
| 1 | Xin S-lock(A), được cấp | |
| 2 | Đọc A = 10 | |
| 3 | Tiếp tục xử lý, vẫn giữ S-lock(A) | Xin X-lock(A), phải chờ vì T1 đang giữ S-lock |
| 4 | COMMIT, giải phóng S-lock(A) | Vẫn chờ cho đến khi khóa được giải phóng |
| 5 | | Được cấp X-lock(A), cập nhật A = 9 |
| 6 | | COMMIT, giải phóng X-lock(A) |

Ở thời điểm 3, T2 không thể cập nhật A ngay cả khi T1 đã đọc xong A. T1 vẫn có thể đang thực hiện các bước khác dựa trên giá trị vừa đọc. Rigorous 2PL giữ S-lock cho đến khi T1 kết thúc để ngăn một giao dịch khác thay đổi A trong khoảng thời gian đó.

Nếu T1 abort thay vì commit, T1 giải phóng khóa sau khi quá trình hủy giao dịch được xử lý. T2 chỉ tiếp tục sau khi khóa được giải phóng; T2 không thể cập nhật A trong khi T1 vẫn đang giữ S-lock.

### Ví dụ: khóa ghi chặn cả đọc lẫn ghi

Giả sử T1 đang thay đổi số dư tài khoản A. T1 cần X-lock vì thao tác ghi phải được thực hiện độc quyền.

```text
T1: X-lock(A)       -> được cấp
T1: write(A, 900)

T2: S-lock(A)       -> phải chờ
T3: X-lock(A)       -> phải chờ

T1: COMMIT
T1: unlock(A)

T2: S-lock(A)       -> được cấp, đọc được giá trị đã commit
T3: X-lock(A)       -> chỉ được cấp khi không còn khóa xung đột
```

Khi T1 đang giữ X-lock(A), cả yêu cầu đọc của T2 lẫn yêu cầu ghi của T3 đều phải chờ. Nhờ đó, T2 không đọc được giá trị chưa commit do T1 vừa ghi. Sau khi T1 kết thúc và giải phóng khóa, các giao dịch đang chờ mới có thể được cấp khóa theo quy tắc tương thích và chính sách xếp hàng của hệ quản trị.

## 4. Rigorous 2PL khác Strict 2PL và Basic 2PL ra sao?

Ba tên gọi thường xuất hiện cùng nhau vì chúng đều dựa trên quy tắc hai pha, nhưng chúng có yêu cầu giữ khóa khác nhau.

| Giao thức | Thời điểm có thể nhả S-lock | Thời điểm có thể nhả X-lock | Đặc điểm chính |
| --- | --- | --- | --- |
| Basic 2PL | Có thể nhả trong pha thu hẹp, trước khi kết thúc giao dịch | Có thể nhả trong pha thu hẹp, trước khi kết thúc giao dịch | Bảo đảm conflict serializability, nhưng có thể tạo lịch không strict và dẫn đến cascading rollback |
| Strict 2PL | Có thể nhả trước khi kết thúc giao dịch, sau khi đã bước vào pha thu hẹp | Giữ đến commit hoặc abort | Ngăn giao dịch khác đọc/ghi dữ liệu do một giao dịch chưa kết thúc ghi ra; hỗ trợ phục hồi đơn giản hơn |
| Rigorous 2PL | Giữ đến commit hoặc abort | Giữ đến commit hoặc abort | Giữ mọi khóa đến cuối giao dịch; giao dịch khác phải chờ cả khi muốn ghi dữ liệu mà giao dịch hiện tại chỉ đọc |

Điểm cần nhớ:

- **Basic 2PL** chỉ yêu cầu tuân thủ hai pha. Nó không bắt buộc khóa ghi phải được giữ đến commit.
- **Strict 2PL** giữ X-lock đến khi giao dịch kết thúc. Theo định nghĩa phổ biến, S-lock có thể được nhả sớm hơn.
- **Rigorous 2PL** giữ cả S-lock lẫn X-lock đến khi giao dịch kết thúc.

Ví dụ về khác biệt giữa Strict 2PL và Rigorous 2PL: T1 đọc A bằng S-lock rồi không còn cần đọc A nữa. Với Strict 2PL, T1 có thể nhả S-lock(A) trong pha thu hẹp; sau đó T2 có thể xin X-lock(A) và cập nhật A dù T1 chưa commit. Với Rigorous 2PL, T1 vẫn giữ S-lock(A), nên T2 phải chờ đến khi T1 commit hoặc abort.

Tên gọi có thể được dùng hơi khác nhau giữa tài liệu hoặc hệ quản trị. Khi đọc tài liệu kỹ thuật, hãy kiểm tra chính xác quy tắc giữ S-lock và X-lock thay vì chỉ dựa vào nhãn “strict”. Trong bài học này, Strict 2PL được hiểu là giữ X-lock đến cuối giao dịch, còn Rigorous 2PL giữ cả hai loại khóa.

## 5. Vì sao giữ cả khóa đọc đến cuối giao dịch?

Giữ S-lock lâu hơn làm giảm khả năng chạy đồng thời, nhưng nó tạo ra một bảo đảm mạnh hơn về thứ tự giao dịch.

### Ngăn dữ liệu bị thay đổi trong lúc giao dịch vẫn đang sử dụng kết quả đọc

Khi T1 đọc A, S-lock(A) ngăn T2 lấy X-lock(A). Do đó, giá trị A không thể bị T2 thay đổi cho đến khi T1 kết thúc. T1 có thể tiếp tục xử lý dựa trên dữ liệu đã đọc mà không phải đối mặt với một giao dịch khác ghi đè chính đối tượng đó giữa chừng.

### Thứ tự commit phù hợp với thứ tự tuần tự tương đương

Rigorous 2PL vẫn thỏa mãn 2PL nên bảo đảm conflict serializability. Vì một giao dịch giữ mọi khóa đến khi kết thúc, giao dịch khác có xung đột phải đợi giao dịch đó kết thúc trước khi lấy khóa tương ứng. Với các giao dịch commit thành công, thứ tự commit vì vậy phù hợp với thứ tự tuần tự tương đương của chúng.

Ví dụ, nếu T1 giữ S-lock(A) trước và T2 cần X-lock(A), T2 chỉ được tiếp tục sau khi T1 kết thúc. T1 kết thúc trước T2 trên xung đột này, nên lịch thực thi có thể được sắp theo thứ tự T1 rồi T2. Tương tự, nếu T1 giữ X-lock(A), T2 phải chờ trước khi đọc hoặc ghi A.

### Tránh đọc dữ liệu chưa commit và hạn chế lỗi dây chuyền khi rollback

Khi một giao dịch ghi dữ liệu bằng X-lock, nó giữ khóa đó đến commit hoặc abort. Giao dịch khác không thể đọc hoặc ghi cùng đối tượng trong lúc giá trị mới còn chưa được xác nhận. Điều này ngăn dirty read và dirty write trên đối tượng được khóa.

Nếu giao dịch ghi bị abort, hệ thống không phải xử lý tình huống một giao dịch khác đã đọc giá trị chưa commit của nó rồi cũng phải rollback theo. Đặc tính này làm cho việc phục hồi giao dịch dễ kiểm soát hơn. Việc giữ S-lock đến cuối giao dịch bổ sung khả năng ngăn writer chen vào trong thời gian reader còn hoạt động.

## 6. Chi phí và giới hạn của Rigorous 2PL

Rigorous 2PL đổi mức độ bảo vệ cao hơn lấy thời gian chờ dài hơn. Khóa được giữ lâu hơn đồng nghĩa nhiều yêu cầu có thể bị chặn.

### Giảm mức độ đồng thời

Hai giao dịch chỉ đọc cùng một hàng vẫn có thể cùng chạy vì S-lock tương thích với S-lock. Nhưng nếu một giao dịch đang giữ S-lock, mọi giao dịch muốn ghi hàng đó phải chờ đến khi giao dịch đọc kết thúc. Một truy vấn đọc lâu có thể làm các giao dịch cập nhật bị xếp hàng dù truy vấn đọc đã lấy xong dữ liệu cần thiết.

### Deadlock vẫn có thể xảy ra

Rigorous 2PL không loại bỏ deadlock. Một tình huống phổ biến là hai giao dịch cùng giữ S-lock rồi cùng muốn nâng cấp lên X-lock:

```text
T1: S-lock(A)        -> được cấp
T2: S-lock(A)        -> được cấp vì S/S tương thích

T1: yêu cầu X-lock(A) -> chờ T2 nhả S-lock(A)
T2: yêu cầu X-lock(A) -> chờ T1 nhả S-lock(A)
```

T1 chờ T2, đồng thời T2 chờ T1. Cả hai không thể tự tiếp tục, tạo thành deadlock. Vì Rigorous 2PL không cho nhả khóa trước khi giao dịch kết thúc, hệ quản trị thường phải phát hiện vòng chờ rồi chọn một giao dịch làm nạn nhân để rollback. Khi giao dịch đó kết thúc và giải phóng khóa, giao dịch còn lại có thể tiếp tục.

Các cách giảm nguy cơ deadlock gồm:

- Lấy khóa theo cùng một thứ tự giữa các giao dịch, ví dụ luôn khóa tài khoản có ID nhỏ trước.
- Nếu đã biết chắc sẽ ghi dữ liệu, cân nhắc xin X-lock ngay từ đầu thay vì nhiều giao dịch cùng lấy S-lock rồi đồng thời nâng cấp.
- Giữ transaction ngắn; không chờ người dùng nhập liệu hoặc gọi dịch vụ bên ngoài trong khi vẫn giữ khóa.
- Chỉ khóa phạm vi dữ liệu cần thiết và bảo đảm truy vấn có chỉ mục phù hợp để tránh khóa quá nhiều hàng.
- Theo dõi deadlock, đặt chính sách timeout hợp lý và thiết kế ứng dụng có thể retry giao dịch bị chọn rollback.

### Có thể gây chờ lâu hoặc starvation

Một giao dịch đọc kéo dài có thể giữ S-lock và làm nhiều giao dịch ghi phải chờ. Nếu hệ thống liên tục ưu tiên các yêu cầu mới hoặc chính sách xếp hàng không công bằng, một giao dịch có thể phải chờ rất lâu. Hệ quản trị thường kết hợp chính sách cấp khóa, timeout và giám sát lock wait để hạn chế tình trạng này.

### Không tự động giải quyết mọi vấn đề về phạm vi truy vấn

Khóa hàng đang tồn tại không phải lúc nào cũng ngăn được một giao dịch khác chèn thêm hàng mới thỏa mãn điều kiện truy vấn. Ví dụ, T1 đọc tất cả đơn hàng có `status = 'OPEN'`. Nếu T1 chỉ giữ S-lock trên các hàng hiện có, T2 có thể chèn một đơn hàng OPEN mới trừ khi hệ thống khóa cả phạm vi hoặc predicate tương ứng.

Để ngăn phantom, hệ quản trị cần cơ chế khóa phạm vi (range lock), gap lock hoặc predicate lock phù hợp với cách thực thi truy vấn. Vì vậy, bảo đảm của 2PL phụ thuộc vào cả đối tượng được khóa và việc giao thức có khóa đủ phạm vi dữ liệu liên quan hay không.

## 7. Khóa được cấp ở mức nào?

Rigorous 2PL mô tả **thời điểm lấy và nhả khóa**, còn lock granularity mô tả **phạm vi dữ liệu mà khóa bảo vệ**. Hai khái niệm này liên quan nhưng không giống nhau.

- **Khóa hàng (row-level):** khóa một hàng cụ thể. Mức này thường cho phép nhiều giao dịch cập nhật các hàng khác nhau cùng lúc.
- **Khóa trang (page-level):** khóa một trang chứa nhiều hàng. Một giao dịch có thể vô tình chặn giao dịch khác đang cần hàng khác trên cùng trang.
- **Khóa bảng (table-level):** khóa cả bảng. Việc quản lý có thể đơn giản hơn nhưng phạm vi chặn lớn.
- **Khóa phạm vi hoặc predicate:** bảo vệ một tập hợp được xác định bằng điều kiện, hữu ích khi cần ngăn phantom.

Một số hệ quản trị còn dùng intention lock để thể hiện ý định khóa ở cấp thấp hơn khi đang quản lý khóa ở nhiều cấp. Các chi tiết này phụ thuộc vào hệ quản trị; nguyên tắc của Rigorous 2PL vẫn là mọi khóa mà giao dịch đã lấy phải được giữ đến khi giao dịch kết thúc.

## 8. Rigorous 2PL trong thực tế

Rigorous 2PL là một mô hình khóa rõ ràng, hữu ích khi ứng dụng cần các giao dịch có thứ tự tuần tự mạnh và chấp nhận việc đọc có thể chặn ghi. Tuy vậy, không nên suy luận rằng mọi câu lệnh `SELECT` trong mọi cơ sở dữ liệu đều lấy S-lock và giữ đến commit.

Nhiều hệ quản trị dùng Multi-Version Concurrency Control (MVCC). Với MVCC, một giao dịch đọc có thể xem một phiên bản dữ liệu phù hợp với snapshot mà không cần chặn giao dịch khác ghi phiên bản mới. Cách này thường tăng khả năng đồng thời giữa reader và writer, nhưng các mức cô lập và bảo đảm cụ thể còn tùy hệ quản trị. MVCC, snapshot isolation và Rigorous 2PL là các khái niệm khác nhau; không thể xem chúng là tương đương chỉ vì đều giúp giao dịch đọc dữ liệu nhất quán.

Khi làm việc với một hệ quản trị cụ thể, hãy kiểm tra tài liệu về isolation level, locking behavior, lock timeout và deadlock handling. Nếu ứng dụng cần hành vi tương tự Rigorous 2PL, cần xác nhận rằng hệ quản trị thực sự giữ khóa đọc và khóa ghi đến cuối transaction, đồng thời khóa đúng phạm vi dữ liệu mà truy vấn phụ thuộc vào.

Một số thói quen giúp giao dịch dùng khóa hiệu quả hơn:

1. Bắt đầu transaction sát với thời điểm cần đọc/ghi và commit ngay khi công việc cơ sở dữ liệu hoàn tất.
2. Tránh giữ transaction mở trong lúc gọi API, gửi email, chờ người dùng hoặc thực hiện tác vụ tốn thời gian bên ngoài cơ sở dữ liệu.
3. Khóa các đối tượng theo thứ tự nhất quán giữa các luồng xử lý.
4. Dùng chỉ mục phù hợp để thu hẹp số hàng cần đọc và khóa.
5. Ghi nhận thời gian chờ khóa, deadlock và transaction chạy lâu để tìm điểm nghẽn.
6. Thiết kế xử lý lỗi để có thể rollback và thử lại khi hệ quản trị chọn transaction làm nạn nhân deadlock.

## 9. Tình huống tổng hợp

Giả sử hệ thống bán hàng có hai giao dịch:

- T1 đọc số lượng tồn kho A và B để kiểm tra xem có đủ hàng cho một đơn hàng hay không.
- T2 cập nhật số lượng tồn kho A sau khi một đơn hàng khác được xác nhận.

Với Rigorous 2PL, T1 lấy S-lock(A) và S-lock(B). Khi T2 yêu cầu X-lock(A), T2 phải chờ vì T1 vẫn giữ S-lock(A), kể cả khi T1 đã đọc xong A nhưng chưa commit. Nếu T1 commit, các khóa được giải phóng và T2 có thể cập nhật A. Nếu T1 abort, các khóa cũng được giải phóng sau khi giao dịch được hủy.

Điều này giúp kết quả kiểm tra của T1 không bị một giao dịch khác thay đổi trên A hoặc B trong khi T1 còn đang chạy. Đổi lại, một giao dịch đọc đơn hàng lâu có thể làm giao dịch cập nhật kho chờ lâu. Nếu hệ thống có lượng đọc lớn và yêu cầu reader không chặn writer, một cơ chế dựa trên MVCC có thể phù hợp hơn, tùy theo mức cô lập và yêu cầu nhất quán cần đạt.

Khi chọn Rigorous 2PL, cần cân nhắc cả hai mặt: nó cho quy tắc khóa dễ suy luận và thứ tự commit rõ ràng, nhưng thời gian giữ S-lock có thể làm giảm throughput và tăng lock contention. Quyết định sử dụng phải dựa trên yêu cầu nhất quán, thời lượng transaction, mức độ tranh chấp dữ liệu và khả năng xử lý deadlock của ứng dụng.

## 10. Những điểm cần ghi nhớ

- 2PL có pha tăng trưởng để lấy khóa và pha thu hẹp để nhả khóa; sau khi đã nhả khóa thì không được lấy thêm khóa.
- S-lock cho phép nhiều giao dịch cùng đọc; X-lock độc quyền đối với cả yêu cầu đọc lẫn ghi khác trên cùng đối tượng.
- Strict 2PL giữ X-lock đến commit/abort; Rigorous 2PL giữ cả S-lock và X-lock đến commit/abort.
- Việc giữ S-lock đến cuối giao dịch khiến reader có thể chặn writer, kể cả khi thao tác đọc đã hoàn tất.
- Rigorous 2PL bảo đảm conflict serializability và giúp thứ tự commit phù hợp với thứ tự tuần tự tương đương; nó cũng ngăn giao dịch khác truy cập dữ liệu đang được một writer chưa kết thúc giữ X-lock.
- Đổi lại, giao thức có thể làm giảm concurrency, tăng thời gian chờ và vẫn có thể gặp deadlock.
- Phạm vi khóa, phantom, MVCC và hành vi cụ thể của từng hệ quản trị cần được xem xét riêng khi áp dụng vào hệ thống thực tế.
