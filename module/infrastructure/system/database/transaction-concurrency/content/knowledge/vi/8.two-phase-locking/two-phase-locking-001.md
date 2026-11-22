# Giao thức khóa hai pha (2PL): giai đoạn lấy khóa và nhả khóa

Khi nhiều giao dịch cùng đọc và cập nhật dữ liệu, cơ sở dữ liệu cần một cơ chế điều phối để các thao tác xung đột không làm kết quả cuối cùng trở nên không nhất quán. Một cách phổ biến là dùng **khóa** (*lock*): trước khi đọc hoặc ghi một mục dữ liệu, giao dịch phải yêu cầu loại khóa phù hợp từ bộ quản lý khóa (*lock manager*).

**Giao thức khóa hai pha** (*Two-Phase Locking — 2PL*) quy định thứ tự lấy và nhả khóa trong một giao dịch. Một giao dịch có hai giai đoạn: giai đoạn tăng trưởng, trong đó nó có thể lấy thêm khóa nhưng chưa nhả khóa; và giai đoạn thu hẹp, trong đó nó có thể nhả khóa nhưng không được lấy thêm khóa mới. Quy tắc này giúp lịch thực thi các giao dịch có thể tuần tự hóa theo xung đột (*conflict-serializable*).

2PL là giao thức quản lý khóa trong quá trình thực thi giao dịch. Nó không phải là giao thức commit hai pha (*Two-Phase Commit — 2PC*), vốn được dùng để phối hợp commit trên nhiều thành phần trong giao dịch phân tán.

## 1. Vì sao cần quy tắc hai pha?

Giả sử hai giao dịch cùng truy cập tài khoản `A`. `T1` muốn đọc rồi cập nhật số dư; `T2` cũng muốn cập nhật số dư đó. Nếu hệ thống cho phép cả hai ghi đồng thời mà không điều phối, một giao dịch có thể ghi đè kết quả của giao dịch còn lại hoặc đọc một trạng thái trung gian không phù hợp.

Khóa giúp kiểm soát quyền truy cập:

- Khóa chia sẻ (*shared lock*, ký hiệu `S`) cho phép nhiều giao dịch cùng đọc một mục dữ liệu. Giao dịch đang giữ `S` không được tự ý ghi mục dữ liệu đó.
- Khóa độc quyền (*exclusive lock*, ký hiệu `X`) cho phép giao dịch đọc và ghi mục dữ liệu, đồng thời ngăn giao dịch khác lấy khóa `S` hoặc `X` xung đột trên cùng mục dữ liệu.

Nếu chỉ yêu cầu khóa trước mỗi thao tác mà không giới hạn thời điểm nhả và lấy lại khóa, một giao dịch có thể nhả khóa trên dữ liệu đã dùng rồi sau đó lấy khóa trên dữ liệu khác. Cách xen kẽ tùy ý này có thể tạo ra lịch thực thi không tuần tự hóa được. 2PL đặt một ranh giới rõ ràng: sau khi giao dịch bắt đầu nhả khóa, nó không được quay lại lấy thêm khóa.

## 2. Hai giai đoạn của 2PL

Ranh giới giữa hai giai đoạn là thời điểm giao dịch nhả khóa đầu tiên.

### 2.1. Giai đoạn tăng trưởng (growing phase)

Trong giai đoạn tăng trưởng, giao dịch được phép:

- Yêu cầu và nhận thêm khóa `S` hoặc `X`.
- Nâng cấp khóa đang giữ, chẳng hạn chuyển từ `S` sang `X`, nếu bộ quản lý khóa cho phép và không có xung đột.
- Tiếp tục giữ các khóa đã lấy.

Trong giai đoạn này, giao dịch **không được nhả khóa** hoặc hạ cấp khóa theo cách giải phóng một phần quyền khóa. Khi giao dịch nhả khóa đầu tiên, giai đoạn tăng trưởng kết thúc.

### 2.2. Giai đoạn thu hẹp (shrinking phase)

Sau lần nhả khóa đầu tiên, giao dịch bước vào giai đoạn thu hẹp. Trong giai đoạn này, giao dịch được phép:

- Nhả các khóa đang giữ.
- Hạ cấp khóa, ví dụ từ `X` xuống `S`; thao tác này giải phóng một phần quyền khóa và được xem là bắt đầu hoặc tiếp tục giai đoạn thu hẹp.
- Kết thúc giao dịch bằng commit hoặc rollback, qua đó giải phóng các khóa còn lại theo cơ chế của hệ quản trị.

Giao dịch **không được yêu cầu khóa mới hoặc nâng cấp khóa** sau khi đã bắt đầu thu hẹp. Nếu nhận ra mình cần thêm quyền truy cập dữ liệu sau thời điểm này, giao dịch phải thay đổi cách tổ chức thao tác hoặc kết thúc và bắt đầu một giao dịch khác phù hợp.

### 2.3. Sơ đồ diễn tiến

```text
Thời gian  ───────────────────────────────────────────────────────────►

       GIAI ĐOẠN TĂNG TRƯỞNG          GIAI ĐOẠN THU HẸP
       (Growing phase)               (Shrinking phase)

       lấy S(A)                      nhả S(A)
       lấy X(B)                      nhả X(B)
       nâng cấp S(C) lên X(C)        nhả X(C)
              │                            │
              │                            └─ Không được lấy khóa mới
              └─ Chưa được nhả khóa

                         ▲
                         └─ Lần nhả khóa đầu tiên: ranh giới hai pha
```

Ví dụ, một giao dịch có thể lấy khóa trên `A`, rồi `B`, rồi `C`; sau đó nhả `A`, `B` và `C`. Nhưng nó không thể lấy khóa `D` sau khi đã nhả `A`, dù `B` và `C` vẫn đang được giữ.

## 3. Các loại khóa và khả năng tương thích

2PL quy định thời điểm lấy và nhả khóa; loại khóa cần lấy phụ thuộc vào thao tác dữ liệu. Với khóa chia sẻ và độc quyền thông dụng, khả năng tương thích được biểu diễn như sau:

| Khóa đang được giữ | Yêu cầu `S` mới | Yêu cầu `X` mới |
|---|---:|---:|
| `S` | Tương thích | Xung đột |
| `X` | Xung đột | Xung đột |

Nhiều giao dịch có thể cùng giữ `S` trên một mục dữ liệu để đọc. Khi một giao dịch cần cập nhật, nó phải có `X`. Nếu một giao dịch khác vẫn giữ `S`, yêu cầu nâng cấp lên `X` có thể phải chờ cho đến khi khóa xung đột được giải phóng.

Ví dụ:

```text
T1: LOCK-S(A)  ── đọc A ───────────────── UNLOCK(A)
T2:       LOCK-S(A) ── đọc A ──────────── UNLOCK(A)
T3:       LOCK-X(A) ── phải chờ T1 và T2 nhả khóa
```

Khi một giao dịch yêu cầu khóa không tương thích với khóa đang được giữ, bộ quản lý khóa thường đưa yêu cầu vào trạng thái chờ. Giao dịch chỉ tiếp tục khi khóa có thể được cấp theo chính sách điều phối của hệ quản trị.

## 4. Ví dụ một giao dịch tuân thủ 2PL

Giả sử `T1` cần cập nhật hai tài khoản `A` và `B`. Giao dịch lấy khóa độc quyền trên cả hai tài khoản trước khi bắt đầu nhả bất kỳ khóa nào.

```text
T1:
    LOCK-X(A)          -- Lấy khóa A: tăng trưởng
    READ(A)
    WRITE(A)

    LOCK-X(B)          -- Lấy khóa B: vẫn tăng trưởng
    READ(B)
    WRITE(B)

    UNLOCK(A)          -- Bắt đầu thu hẹp
    UNLOCK(B)          -- Tiếp tục thu hẹp
    COMMIT
```

Lịch này tuân thủ 2PL vì mọi yêu cầu khóa đều xảy ra trước lần nhả khóa đầu tiên. Sau `UNLOCK(A)`, `T1` không yêu cầu thêm khóa nào nữa. Việc vẫn giữ `X(B)` không cho phép giao dịch quay lại giai đoạn tăng trưởng.

Một giao dịch có thể nhả khóa ngay khi không còn cần mục dữ liệu đó, miễn là nó không cần lấy thêm khóa về sau. Nếu muốn giữ quyền truy cập nhất quán trên nhiều mục dữ liệu, giao dịch thường phải lấy các khóa cần thiết trước khi bắt đầu nhả khóa.

## 5. Ví dụ vi phạm 2PL

Xét trình tự sau:

```text
T1:
    LOCK-X(A)
    WRITE(A)
    UNLOCK(A)          -- Đã bước vào giai đoạn thu hẹp

    LOCK-S(B)          -- Vi phạm: lấy khóa mới sau khi đã nhả khóa
    READ(B)
    UNLOCK(B)
    COMMIT
```

Yêu cầu `LOCK-S(B)` không hợp lệ theo giao thức 2PL vì `T1` đã nhả `A`. Dù khóa mới chỉ là khóa chia sẻ để đọc, quy tắc vẫn áp dụng cho mọi loại khóa: sau lần nhả đầu tiên, không được lấy thêm khóa hoặc nâng cấp khóa.

Tương tự, trình tự sau cũng vi phạm:

```text
LOCK-S(A)
READ(A)
UNLOCK(A)
LOCK-X(A)             -- Không được nâng cấp sau khi đã nhả khóa
WRITE(A)
```

Nếu giao dịch cần chuyển `S(A)` thành `X(A)`, nó phải thực hiện nâng cấp khi vẫn còn giữ `S(A)` và trước khi nhả bất kỳ khóa nào khác. Việc nâng cấp có thể phải chờ các giao dịch đang giữ khóa chia sẻ khác kết thúc.

## 6. Nâng cấp và hạ cấp khóa

Trong thực tế, giao dịch có thể chưa biết ngay từ đầu liệu nó chỉ cần đọc hay sẽ cần cập nhật một mục dữ liệu.

### Nâng cấp (lock upgrade)

Nâng cấp thường là chuyển `S` thành `X`:

```text
LOCK-S(A)
READ(A)

LOCK-X(A)             -- Yêu cầu nâng cấp khi vẫn giữ S(A)
WRITE(A)

UNLOCK(A)
```

Yêu cầu nâng cấp phải xảy ra trong giai đoạn tăng trưởng. Nếu giao dịch đã nhả một khóa khác trước đó, nó không còn được phép nâng cấp theo 2PL. Bộ quản lý khóa có thể phải đợi các khóa chia sẻ khác trên `A` được nhả trước khi cấp `X(A)`.

### Hạ cấp (lock downgrade)

Hạ cấp thường là chuyển `X` thành `S`, tức giao dịch từ bỏ quyền ghi độc quyền nhưng vẫn giữ quyền đọc:

```text
LOCK-X(A)
WRITE(A)
LOCK-S(A)             -- Hạ cấp X(A) xuống S(A)
READ(A)
UNLOCK(A)
```

Hạ cấp giải phóng một phần quyền khóa nên được xem là thao tác nhả khóa. Vì vậy, nó chỉ phù hợp trong giai đoạn thu hẹp. Sau khi hạ cấp, giao dịch không thể nâng cấp trở lại `X` hoặc lấy khóa khác.

## 7. Vì sao 2PL bảo đảm khả năng tuần tự hóa theo xung đột?

Một lịch thực thi là **tuần tự hóa theo xung đột** nếu có thể sắp xếp các giao dịch thành một thứ tự tuần tự mà vẫn giữ nguyên thứ tự của mọi cặp thao tác xung đột.

Với 2PL, có thể xác định **điểm khóa** (*lock point*) của một giao dịch là thời điểm nó lấy khóa cuối cùng. Theo quy tắc hai pha, sau điểm khóa, giao dịch chỉ có thể tiếp tục nhả khóa; nó không thể lấy thêm khóa. Thứ tự các điểm khóa tạo ra một thứ tự tuần tự tương ứng cho các giao dịch trong lịch, bảo đảm lịch tuân thủ 2PL là conflict-serializable.

Có thể hình dung như sau:

```text
T1: lấy khóa A ── lấy khóa B ── LOCK POINT ── nhả A ── nhả B
T2:       chờ A ─────────────── lấy khóa A ── LOCK POINT ── nhả A
                                      │
                                      └─ T1 có lock point trước T2

Thứ tự tuần tự tương ứng: T1 → T2
```

Điểm khóa là khái niệm dùng để chứng minh thứ tự tuần tự hóa, không phải một lệnh SQL mà ứng dụng phải gọi. Trong triển khai thực tế, bộ quản lý khóa điều phối các yêu cầu và thời gian chờ để bảo đảm quy tắc khóa.

## 8. Các biến thể thường gặp của 2PL

2PL cơ bản quy định hai giai đoạn lấy và nhả khóa. Các biến thể bổ sung ràng buộc về thời điểm giải phóng khóa để tăng khả năng phục hồi hoặc tránh một số vấn đề vận hành.

| Biến thể | Quy tắc chính | Đặc điểm |
|---|---|---|
| **Basic 2PL** | Có giai đoạn tăng trưởng và thu hẹp; sau khi nhả khóa đầu tiên không được lấy khóa mới | Bảo đảm conflict-serializability, nhưng có thể nhả khóa ghi trước khi commit |
| **Strict 2PL** | Giữ mọi khóa `X` đến khi commit hoặc rollback | Ngăn giao dịch khác đọc hoặc ghi dữ liệu đã bị ghi bởi giao dịch chưa kết thúc; đơn giản hóa phục hồi và tránh cascading rollback do đọc dữ liệu chưa commit |
| **Rigorous 2PL** | Giữ cả khóa `S` và `X` đến khi commit hoặc rollback | Tất cả khóa chỉ được giải phóng khi giao dịch kết thúc; thứ tự commit cũng phản ánh thứ tự tuần tự hóa theo khóa |
| **Conservative (Static) 2PL** | Lấy trước toàn bộ khóa cần thiết trước khi bắt đầu thao tác | Nếu lấy không đủ khóa thì chờ mà chưa giữ một phần khóa nào; tránh deadlock do chờ khóa, nhưng cần biết trước tập khóa và có thể giảm mức đồng thời |

### 8.1. Basic 2PL và Strict 2PL khác nhau ở đâu?

Basic 2PL cho phép giao dịch nhả khóa độc quyền trước khi commit, miễn là sau đó không lấy thêm khóa. Điều này vẫn đáp ứng quy tắc hai pha và bảo đảm conflict-serializability, nhưng một giao dịch khác có thể đọc giá trị vừa được ghi trước khi giao dịch đầu tiên kết thúc. Nếu giao dịch đầu tiên rollback, giao dịch đọc có thể đã dựa trên dữ liệu chưa được xác nhận.

Strict 2PL giữ khóa độc quyền đến khi giao dịch commit hoặc rollback. Giao dịch khác vì thế không thể đọc hoặc ghi mục dữ liệu đang có thay đổi chưa được xác nhận. Quy tắc này giúp lịch thực thi có tính nghiêm ngặt (*strict*) và đơn giản hóa việc phục hồi.

Rigorous 2PL còn giữ cả khóa chia sẻ đến cuối giao dịch. Do đó, nó ràng buộc thời điểm giải phóng mọi khóa, chặt hơn Strict 2PL.

### 8.2. Conservative 2PL có tác dụng gì?

Conservative 2PL yêu cầu giao dịch khai báo và lấy toàn bộ khóa cần dùng trước khi bắt đầu. Nếu một khóa chưa sẵn sàng, giao dịch chờ mà không giữ một phần tập khóa. Vì không giữ khóa này trong khi chờ khóa khác, giao dịch không tạo chu trình chờ do cơ chế khóa đó. Đổi lại, ứng dụng hoặc hệ thống phải biết trước các mục dữ liệu cần khóa, và giao dịch có thể phải chờ lâu trước khi bắt đầu.

## 9. 2PL có ngăn deadlock không?

Không. 2PL bảo đảm khả năng tuần tự hóa theo xung đột, nhưng **không loại bỏ deadlock**. Hai giao dịch vẫn có thể giữ các khóa khác nhau rồi chờ khóa mà giao dịch còn lại đang giữ.

Ví dụ:

```text
T1: LOCK-X(A) thành công
T2: LOCK-X(B) thành công

T1: yêu cầu LOCK-X(B) ── chờ T2
T2: yêu cầu LOCK-X(A) ── chờ T1
```

Quan hệ chờ tạo thành chu trình:

```text
T1 ── chờ B do T2 giữ ──► T2
 ▲                         │
 └── chờ A do T1 giữ ──────┘
```

Không giao dịch nào có thể tiếp tục nếu không có một hành động phá vỡ chu trình. Hệ quản trị có thể phát hiện chu trình trong đồ thị chờ (*wait-for graph*) và chọn một giao dịch làm nạn nhân để rollback; cũng có thể áp dụng timeout hoặc các chiến lược phòng ngừa deadlock.

Một cách giảm nguy cơ là yêu cầu các giao dịch lấy khóa theo cùng một thứ tự, chẳng hạn luôn khóa tài khoản theo thứ tự mã tăng dần. Cách này giúp giảm chu trình chờ trong các luồng thao tác tuân theo cùng quy ước, nhưng không thay thế cơ chế phát hiện và xử lý deadlock của hệ quản trị.

Ngoài deadlock, hệ thống còn cần quan tâm đến **starvation**: một giao dịch có thể liên tục phải chờ hoặc bị chọn làm nạn nhân, khiến nó không hoàn tất trong thời gian hợp lý. Chính sách ưu tiên, công bằng cấp khóa và giới hạn retry có thể giúp kiểm soát tình trạng này.

## 10. Chi phí và giới hạn khi sử dụng 2PL

Khóa giúp bảo vệ tính nhất quán nhưng có chi phí:

- **Chờ khóa:** giao dịch có thể bị chặn khi yêu cầu khóa không tương thích với khóa đang được giữ.
- **Giảm mức đồng thời:** khóa được giữ càng lâu thì càng nhiều giao dịch khác có thể phải chờ.
- **Deadlock:** các giao dịch có thể chờ lẫn nhau theo chu trình.
- **Chi phí quản lý khóa:** hệ quản trị phải theo dõi khóa, hàng đợi yêu cầu, thời gian chờ và việc giải phóng khóa.
- **Phạm vi khóa:** khóa ở mức bảng, trang hoặc hàng có đặc điểm khác nhau về chi phí và mức độ đồng thời. Một số hệ quản trị còn dùng khóa ý định (*intention lock*) khi phối hợp nhiều mức hạt khóa.

Giữ khóa quá lâu, chẳng hạn trong khi chờ người dùng nhập dữ liệu hoặc gọi một dịch vụ bên ngoài, có thể làm tăng thời gian chờ và nguy cơ deadlock. Giao dịch nên được thiết kế ngắn gọn, chỉ giữ khóa trong khoảng thời gian cần thiết và tránh thực hiện công việc chậm không liên quan khi vẫn đang giữ khóa.

## 11. Cách quan sát và kiểm tra hành vi khóa

Khi điều tra một giao dịch bị chờ hoặc deadlock, cần xác định cả giao dịch đang giữ khóa lẫn giao dịch đang yêu cầu khóa. Tên view và câu lệnh chẩn đoán phụ thuộc vào hệ quản trị, nhưng các thông tin cần tìm thường gồm:

1. Giao dịch nào đang giữ khóa trên mục dữ liệu bị tranh chấp?
2. Khóa đang giữ và khóa đang yêu cầu là `S`, `X` hay một chế độ khóa khác?
3. Yêu cầu bị chờ do hai chế độ khóa không tương thích hay do một ràng buộc khóa ở mức cao hơn?
4. Giao dịch đã bước vào giai đoạn thu hẹp chưa? Nó có còn yêu cầu khóa mới sau lần nhả khóa đầu tiên không?
5. Có chu trình chờ trong các giao dịch đang hoạt động hay không?
6. Khóa có được giữ lâu do giao dịch thực hiện công việc bên ngoài cơ sở dữ liệu hay không?

Không nên chỉ nhìn thấy một câu lệnh đang chờ rồi kết luận có deadlock. Một giao dịch chờ khóa đơn lẻ có thể tiếp tục bình thường khi giao dịch giữ khóa commit hoặc rollback. Deadlock cần có chu trình chờ; còn 2PL được nhận diện qua trình tự lấy và nhả khóa trong từng giao dịch.

## 12. Ghi nhớ

- 2PL chia giao dịch thành **giai đoạn tăng trưởng** (chỉ lấy khóa) và **giai đoạn thu hẹp** (chỉ nhả khóa).
- Lần nhả khóa đầu tiên đánh dấu ranh giới hai giai đoạn. Sau thời điểm đó, giao dịch không được lấy khóa mới hoặc nâng cấp khóa.
- Nâng cấp `S` lên `X` phải diễn ra khi giao dịch vẫn ở giai đoạn tăng trưởng; hạ cấp `X` xuống `S` là thao tác giải phóng quyền khóa và thuộc giai đoạn thu hẹp.
- Lịch thực thi tuân thủ 2PL có thể tuần tự hóa theo xung đột; điểm khóa là thời điểm giao dịch lấy khóa cuối cùng.
- 2PL cơ bản không tự ngăn deadlock và không bảo đảm strictness. Strict 2PL giữ khóa độc quyền đến khi commit hoặc rollback; Rigorous 2PL giữ tất cả khóa đến cuối giao dịch.
- Conservative 2PL lấy trước toàn bộ khóa cần thiết, nhờ đó tránh deadlock do chờ khóa nhưng đòi hỏi biết trước tập khóa.

Khi đọc một lịch giao dịch, hãy tìm thời điểm mỗi giao dịch nhả khóa đầu tiên. Nếu sau mốc đó nó còn yêu cầu khóa mới hoặc nâng cấp khóa, lịch đó đã vi phạm giao thức khóa hai pha.
