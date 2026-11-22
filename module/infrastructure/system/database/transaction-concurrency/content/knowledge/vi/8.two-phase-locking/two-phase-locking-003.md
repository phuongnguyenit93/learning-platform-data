# Strict 2PL và thời điểm giải phóng khóa ghi

Trong cơ sở dữ liệu có nhiều giao dịch chạy đồng thời, một giao dịch có thể đang sửa dữ liệu trong khi giao dịch khác muốn đọc hoặc sửa chính dữ liệu đó. Hệ quản trị cơ sở dữ liệu (DBMS) cần một quy tắc để quyết định giao dịch nào được tiếp tục và giao dịch nào phải chờ. Khóa (lock) là một cơ chế phổ biến để điều phối những truy cập xung đột này.

**Strict Two-Phase Locking (Strict 2PL, khóa hai pha nghiêm ngặt)** quy định rằng giao dịch phải tuân theo hai pha của 2PL và phải giữ mọi khóa độc quyền (exclusive lock, khóa X) cho đến khi giao dịch kết thúc bằng `COMMIT` hoặc `ROLLBACK`. Vì vậy, một giao dịch khác không thể đọc hoặc ghi đè lên dữ liệu mà giao dịch trước vẫn có thể phải hoàn tác.

Điểm cần nhớ nhất của bài học là: **khóa ghi X được giải phóng sau khi giao dịch đã hoàn tất commit hoặc rollback, không phải ngay sau câu lệnh ghi cuối cùng.**

## 1. Ôn lại khóa S, khóa X và quy tắc hai pha

DBMS thường dùng hai loại khóa cơ bản:

- **Khóa chia sẻ S (Shared lock):** cho phép giao dịch đọc dữ liệu. Nhiều giao dịch có thể cùng giữ S trên một mục dữ liệu vì các thao tác đọc không xung đột với nhau.
- **Khóa độc quyền X (Exclusive lock):** dùng khi giao dịch cần ghi hoặc cập nhật dữ liệu. Khi một giao dịch giữ X trên một mục dữ liệu, giao dịch khác không thể lấy S hoặc X trên cùng mục đó cho đến khi X được giải phóng.

Bảng tương thích cơ bản:

| Khóa đang được giữ | Yêu cầu S mới | Yêu cầu X mới |
|---|---:|---:|
| S | Được cấp | Phải chờ |
| X | Phải chờ | Phải chờ |

Ví dụ, nếu `T1` đang giữ `X(A)`, `T2` muốn đọc `A` cũng phải chờ để lấy `S(A)`. Việc đọc có vẻ không làm thay đổi dữ liệu, nhưng nếu cho phép đọc khi `T1` chưa kết thúc thì `T2` có thể nhìn thấy một giá trị chưa được commit.

### Hai pha của 2PL

Quy tắc Two-Phase Locking chia vòng đời lấy và nhả khóa thành hai pha:

1. **Pha mở rộng (growing phase):** giao dịch có thể lấy thêm khóa và nâng cấp khóa, chẳng hạn từ S lên X. Giao dịch chưa được giải phóng khóa nào.
2. **Pha thu hẹp (shrinking phase):** bắt đầu khi giao dịch giải phóng khóa đầu tiên. Từ thời điểm này, giao dịch có thể tiếp tục nhả khóa nhưng không được lấy thêm khóa mới hoặc nâng cấp khóa.

Ví dụ về thứ tự hợp lệ của 2PL:

```text
Lấy S(A)
Lấy X(B)
Nâng cấp S(C) thành X(C)
        ↓ kết thúc pha mở rộng
Nhả S(A)
Nhả X(B)
Nhả X(C)
```

Nếu giao dịch đã nhả `S(A)` rồi lại lấy `X(D)`, thứ tự đó vi phạm 2PL vì giao dịch đã bước vào pha thu hẹp nhưng quay lại lấy khóa.

2PL điều chỉnh **thứ tự lấy và nhả khóa**. Quy tắc này không tự động yêu cầu giao dịch phải giữ mọi khóa đến lúc commit. Đó là điểm Strict 2PL bổ sung.

## 2. Strict 2PL bổ sung điều gì?

Strict 2PL kế thừa hai pha của 2PL và thêm một ràng buộc về thời điểm nhả khóa ghi:

- Mọi khóa X mà giao dịch đã lấy phải được giữ đến khi giao dịch commit hoặc rollback xong.
- Khóa S có thể được giải phóng trong pha thu hẹp trước khi giao dịch kết thúc, miễn là giao dịch không lấy thêm khóa sau khi đã bắt đầu nhả khóa.

Điều đó có nghĩa một giao dịch có thể nhả một số khóa đọc S sớm hơn, nhưng không thể nhả khóa X rồi tiếp tục để giao dịch khác truy cập giá trị mà nó vừa ghi trước khi giao dịch kết thúc.

### Phân biệt 2PL, Strict 2PL và Rigorous 2PL

Ba tên gọi này thường bị dùng lẫn nhau, vì vậy cần nhìn vào chính quy tắc giữ khóa:

| Cơ chế | Khi nào được nhả khóa? | Ràng buộc đến lúc kết thúc |
|---|---|---|
| Basic 2PL | Có thể nhả khóa trong pha thu hẹp | Không được lấy khóa mới sau lần nhả đầu tiên |
| Strict 2PL | Có thể nhả S trong pha thu hẹp; giữ mọi X đến hết giao dịch | Tất cả X được giữ đến commit/rollback |
| Rigorous 2PL (còn gọi là strong strict 2PL trong một số tài liệu) | Giữ cả S và X đến hết giao dịch | Tất cả khóa được giữ đến commit/rollback |

Một số giáo trình hoặc hệ thống dùng thuật ngữ Strict 2PL theo nghĩa rộng hơn, tức giữ cả S và X đến cuối giao dịch. Khi đọc tài liệu, hãy kiểm tra định nghĩa được sử dụng. Trong bài này, Strict 2PL được dùng theo cách phân biệt phổ biến: **giữ tất cả khóa X đến cuối giao dịch; khóa S có thể được nhả sớm theo quy tắc 2PL.**

## 3. Chính xác khi nào giải phóng khóa ghi X?

Thời điểm giải phóng khóa X phụ thuộc vào kết quả cuối cùng của giao dịch.

### Khi giao dịch commit thành công

Giả sử `T1` đang giữ `X(A)` và đã cập nhật `A` từ `100` thành `120`. `T1` phải tiếp tục giữ `X(A)` trong khi kết quả ghi vẫn thuộc một giao dịch chưa hoàn tất.

Luồng xử lý khái niệm:

1. `T1` hoàn tất các thao tác cần thiết và yêu cầu commit.
2. DBMS hoàn tất quy trình commit, bao gồm việc ghi nhận commit trong log và bảo đảm yêu cầu durability theo cơ chế phục hồi của hệ thống.
3. Khi giao dịch đã commit, DBMS giải phóng `X(A)`.
4. Lock manager có thể cấp khóa đang chờ cho giao dịch khác, tùy theo chế độ khóa và thứ tự trong hàng đợi.

```text
T1: lấy X(A)
T1: ghi A = 120
T1: yêu cầu COMMIT
T1: commit hoàn tất
T1: nhả X(A)
                 └── T2 có thể được cấp khóa phù hợp trên A
```

Trong triển khai thực tế, thứ tự nội bộ và thời điểm xác nhận commit có thể khác nhau tùy DBMS. Ý nghĩa của Strict 2PL vẫn không đổi: giao dịch khác không được sử dụng khóa X của `T1` trước khi `T1` kết thúc thành công.

### Khi giao dịch rollback hoặc bị hủy

Nếu `T1` không thể commit, DBMS phải hoàn tác các thay đổi của `T1`. Trong suốt quá trình hoàn tác, `T1` vẫn giữ khóa X trên dữ liệu liên quan.

Luồng xử lý khái niệm:

1. `T1` bị yêu cầu rollback hoặc DBMS xác định giao dịch phải abort.
2. DBMS dùng thông tin phục hồi để hoàn tác các thay đổi chưa commit.
3. Sau khi rollback hoàn tất, DBMS giải phóng các khóa X của `T1`.
4. Giao dịch đang chờ mới có thể được cấp khóa và tiếp tục.

```text
T1: lấy X(A)
T1: ghi A = 120
T1: phát sinh lỗi / yêu cầu ROLLBACK
T1: hoàn tác A về 100
T1: rollback hoàn tất
T1: nhả X(A)
                 └── T2 có thể đọc giá trị đã được khôi phục
```

Nếu DBMS giải phóng `X(A)` trước khi hoàn tác xong, `T2` có thể đọc hoặc ghi trên giá trị trung gian `120`, trong khi `T1` vẫn có khả năng khôi phục `A` về `100`. Điều đó tạo ra rủi ro đọc dữ liệu chưa commit hoặc ghi đè dữ liệu đang được phục hồi.

### Những thời điểm không được nhả khóa X

Theo Strict 2PL, các thời điểm sau chưa đủ điều kiện để giải phóng khóa X:

- Ngay sau câu lệnh `UPDATE` cuối cùng.
- Ngay sau lần truy cập hoặc ghi cuối cùng vào một bản ghi.
- Ngay khi giao dịch bắt đầu pha thu hẹp.
- Ngay khi ứng dụng gửi yêu cầu `COMMIT` nhưng DBMS chưa hoàn tất giao dịch.
- Trong khi DBMS vẫn đang hoàn tác giao dịch bị abort.

Nói cách khác, thời điểm kết thúc thao tác trên một dữ liệu không đồng nghĩa với thời điểm kết thúc giao dịch. Khóa X bảo vệ dữ liệu trong toàn bộ khoảng thời gian kết quả ghi còn có thể bị rollback.

## 4. Ví dụ: giao dịch đọc phải chờ giao dịch ghi commit

Giả sử tài khoản `A` đang có số dư `100`. `T1` cộng thêm `20`; cùng lúc `T2` muốn đọc số dư.

| Thứ tự | Giao dịch T1 | Giao dịch T2 | Trạng thái khóa trên A |
|---:|---|---|---|
| 1 | Lấy `X(A)` | | `T1` giữ X |
| 2 | Ghi `A = 120` | | `T1` vẫn giữ X |
| 3 | | Yêu cầu `S(A)` | `T2` phải chờ vì X và S không tương thích |
| 4 | Hoàn tất `COMMIT` | Đang chờ | `T1` vẫn giữ X cho đến khi commit hoàn tất |
| 5 | Nhả `X(A)` | | Lock manager có thể cấp S(A) cho T2 |
| 6 | | Được cấp `S(A)`, đọc `120` | `T2` giữ S |

`T2` chỉ đọc được giá trị `120` sau khi `T1` commit. Vì vậy, `T2` không phụ thuộc vào một thay đổi chưa được xác nhận.

Nếu ở bước 4 `T1` rollback, DBMS khôi phục `A = 100` trước khi nhả `X(A)`. Khi `T2` được cấp `S(A)`, nó đọc giá trị `100`. `T2` không bao giờ nhìn thấy giá trị trung gian `120` của giao dịch đã thất bại.

### So sánh với Basic 2PL

Giả sử `T1` lấy `X(A)`, ghi `A = 120`, sau đó nhả `X(A)` trước khi commit. `T2` có thể lấy `S(A)` và đọc `120`. Nếu `T1` tiếp tục rollback, giá trị `A` trở về `100`, nhưng `T2` đã đọc dữ liệu chưa commit.

```text
T1: X(A) → ghi A = 120 → nhả X(A) ─────────────→ ROLLBACK
                                      T2: S(A) → đọc 120
```

Lịch thực thi này có thể tuân theo Basic 2PL nếu `T1` không lấy thêm khóa sau khi nhả khóa đầu tiên, nhưng nó không tuân theo Strict 2PL vì `T1` đã nhả khóa X trước khi kết thúc. Nếu `T2` sử dụng dữ liệu đó để cập nhật dữ liệu khác, lỗi có thể lan sang các giao dịch tiếp theo và gây ra cascading rollback (hoàn tác dây chuyền).

Strict 2PL ngăn tình huống này bằng cách giữ `X(A)` cho đến khi `T1` commit hoặc rollback hoàn tất.

## 5. Strict 2PL bảo đảm điều gì?

### Ngăn dirty read và dirty write

- **Dirty read (đọc bẩn):** giao dịch đọc giá trị do một giao dịch khác ghi nhưng chưa commit. Vì X xung đột với S, giao dịch đọc phải chờ cho đến khi giao dịch ghi kết thúc.
- **Dirty write (ghi bẩn):** giao dịch ghi đè lên thay đổi chưa commit của giao dịch khác. Vì X xung đột với X, giao dịch ghi thứ hai phải chờ.

Các bảo đảm này giả định những truy cập xung đột đều đi qua cơ chế khóa và các mục dữ liệu cần bảo vệ được khóa ở phạm vi thích hợp.

### Tránh cascading rollback

Khi một giao dịch chỉ đọc dữ liệu đã được commit, việc giao dịch ghi trước đó rollback không làm cho giao dịch đọc phải rollback theo vì nó đã sử dụng dữ liệu chưa commit. Strict 2PL tạo ra lịch thực thi strict và cascadeless theo mô hình khóa chuẩn.

### Giữ tính khả tuần tự xung đột

Strict 2PL kế thừa bảo đảm conflict serializability của 2PL. Có thể xem lịch thực thi đồng thời như một thứ tự tuần tự tương đương về xung đột, dù các thao tác của nhiều giao dịch được xen kẽ trong thời gian thực.

Tuy nhiên, Strict 2PL **không loại bỏ mọi vấn đề đồng thời**. Nó không tự động ngăn deadlock, không tự quyết định khóa ở phạm vi nào là đủ, và không thay thế thiết kế isolation phù hợp cho các truy vấn phức tạp.

## 6. Đánh đổi: thời gian chờ và deadlock

Giữ khóa X đến cuối giao dịch giúp dữ liệu an toàn hơn, nhưng cũng khiến khóa có thể bị giữ lâu hơn thời gian thực hiện câu lệnh ghi. Giao dịch khác muốn đọc hoặc ghi cùng dữ liệu phải chờ.

Ví dụ deadlock:

```text
T1 giữ X(A), sau đó yêu cầu X(B)
T2 giữ X(B), sau đó yêu cầu X(A)

T1 chờ T2 nhả B
T2 chờ T1 nhả A
```

Hai giao dịch chờ lẫn nhau. Strict 2PL yêu cầu giữ các khóa X đến khi giao dịch kết thúc, nên một giao dịch không thể tùy ý nhả khóa đang giữ để phá vòng chờ. DBMS thường phải phát hiện deadlock hoặc dùng chính sách phòng tránh/timeout, chọn một giao dịch làm nạn nhân, rollback giao dịch đó rồi mới giải phóng khóa.

Một số cách giảm thời gian chờ:

- Giữ giao dịch ngắn và tránh thực hiện công việc không liên quan trong khi đang giữ khóa.
- Truy cập các tài nguyên theo một thứ tự nhất quán để giảm khả năng tạo chu trình chờ.
- Chỉ khóa phạm vi dữ liệu cần thiết, đồng thời bảo đảm phạm vi khóa vẫn bảo vệ đúng điều kiện nghiệp vụ.
- Xử lý lỗi và retry giao dịch một cách có kiểm soát khi DBMS báo deadlock hoặc timeout.

## 7. Khóa phải bao phủ đúng dữ liệu mà truy vấn cần bảo vệ

Strict 2PL chỉ giữ khóa đúng theo những khóa mà giao dịch đã lấy. Nếu truy vấn kiểm tra một điều kiện trên cả một khoảng dữ liệu, chỉ khóa các hàng hiện có có thể chưa đủ để ngăn giao dịch khác chèn một hàng mới thỏa điều kiện đó. Vấn đề này thường được gọi là phantom (bản ghi ảo).

Ví dụ, `T1` đếm số đơn hàng có trạng thái `PENDING`, trong khi `T2` chèn thêm một đơn hàng mới cũng có trạng thái `PENDING`. Nếu cơ chế khóa chỉ bảo vệ các hàng đã tồn tại, kết quả truy vấn lặp lại của `T1` có thể thay đổi.

Để bảo vệ điều kiện truy vấn, DBMS có thể cần predicate lock, range lock, gap lock hoặc một cơ chế tương đương tùy theo hệ thống và isolation level. Việc khóa hàng hiện có và việc khóa cả một phạm vi điều kiện là hai vấn đề khác nhau.

Ngoài ra, nhiều DBMS hiện đại kết hợp MVCC với khóa ghi. Trong mô hình đó, truy vấn đọc thông thường có thể đọc một phiên bản nhất quán mà không phải chờ khóa X, trong khi các thao tác ghi vẫn cần điều phối xung đột. Vì thế, không nên suy ra rằng mọi câu `SELECT` trong mọi DBMS đều phải chờ một khóa X theo đúng ví dụ khóa thuần túy ở trên. Hãy kiểm tra cơ chế concurrency control và isolation level cụ thể của DBMS đang sử dụng.

## 8. Ví dụ SQL mang tính minh họa

Ví dụ sau mô tả ý tưởng một giao dịch khóa bản ghi tài khoản để cập nhật số dư. Cú pháp và hành vi khóa cụ thể của `SELECT ... FOR UPDATE` phụ thuộc DBMS.

```sql
BEGIN;

-- Yêu cầu khóa bản ghi để cập nhật.
SELECT balance
FROM account
WHERE account_id = 1
FOR UPDATE;

UPDATE account
SET balance = balance + 20
WHERE account_id = 1;

COMMIT;
```

Trong thời gian giao dịch chưa kết thúc, một giao dịch khác muốn cập nhật cùng bản ghi thường phải chờ khóa tương ứng. Khi commit hoàn tất, DBMS giải phóng khóa và giao dịch đang chờ có thể tiếp tục. Nếu giao dịch đầu tiên rollback, DBMS hoàn tác thay đổi trước khi cho giao dịch đang chờ tiếp tục.

Đoạn SQL trên chỉ minh họa mục đích khóa bản ghi. Nó không chứng minh rằng mọi DBMS đều triển khai toàn bộ cơ chế bên trong bằng Strict 2PL; một số hệ thống sử dụng MVCC hoặc kết hợp nhiều cơ chế.

## 9. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Ghi xong một hàng thì có thể nhả X ngay. | Strict 2PL giữ X đến khi giao dịch commit hoặc rollback hoàn tất. |
| Bắt đầu pha thu hẹp là được nhả tất cả khóa. | Khóa X vẫn phải được giữ; khóa S có thể được nhả theo quy tắc 2PL. |
| Strict 2PL nghĩa là luôn giữ mọi khóa S và X đến cuối. | Đó là cách mô tả của Rigorous 2PL; cần kiểm tra quy ước thuật ngữ trong tài liệu. |
| Strict 2PL loại bỏ deadlock. | Strict 2PL vẫn có thể tạo deadlock; DBMS cần cơ chế phát hiện hoặc phòng tránh. |
| Gửi lệnh `COMMIT` đồng nghĩa khóa được nhả ngay lập tức. | Khóa X chỉ được nhả sau khi giao dịch thực sự kết thúc theo quy trình commit của DBMS. |
| Khóa hàng hiện có luôn ngăn được phantom. | Truy vấn theo phạm vi có thể cần predicate/range/gap lock hoặc cơ chế tương đương. |

## 10. Tự kiểm tra

**Tình huống 1:** `T1` lấy `X(A)`, cập nhật `A`, rồi thực hiện thêm một số thao tác trên `B`. `T2` yêu cầu `S(A)` ngay sau khi `T1` cập nhật `A`. `T2` có được đọc `A` trước khi `T1` commit không?

**Đáp án:** Không. `T1` vẫn giữ `X(A)` cho đến khi commit hoặc rollback hoàn tất. Yêu cầu `S(A)` của `T2` phải chờ.

**Tình huống 2:** `T1` cập nhật `A` rồi bị abort. Khi nào `T2` có thể được cấp khóa để đọc `A`?

**Đáp án:** Sau khi DBMS hoàn tất rollback các thay đổi của `T1` và giải phóng `X(A)`. Khi đó `T2` đọc được giá trị đã được khôi phục.

**Tình huống 3:** `T1` nhả `S(A)` trong pha thu hẹp, sau đó yêu cầu lấy `X(B)`. Thứ tự này có hợp lệ theo 2PL không?

**Đáp án:** Không. Sau khi nhả khóa đầu tiên, `T1` đã vào pha thu hẹp và không được lấy thêm khóa. Quy tắc này áp dụng cho cả Basic 2PL và Strict 2PL.

**Tình huống 4:** `T1` và `T2` giữ X trên hai hàng khác nhau rồi chờ khóa của nhau. Strict 2PL có tự giải quyết tình trạng này không?

**Đáp án:** Không. Đây là deadlock. DBMS cần phát hiện hoặc phòng tránh deadlock; nếu chọn một giao dịch làm nạn nhân, giao dịch đó phải rollback trước khi các khóa liên quan được giải phóng.

Khi phân tích một lịch thực thi, hãy lần lượt xác định giao dịch đang giữ khóa nào, giao dịch khác đang yêu cầu khóa nào, thời điểm giao dịch bước vào pha thu hẹp và thời điểm commit/rollback thực sự hoàn tất. Với Strict 2PL, mốc quyết định để giải phóng khóa ghi luôn là **kết thúc giao dịch**, không phải thời điểm câu lệnh ghi kết thúc.
