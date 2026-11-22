# Khả tuần tự theo xung đột của lịch tuân thủ 2PL

Khóa hai pha (Two-Phase Locking, 2PL) là một giao thức điều khiển tương tranh. Giao thức này quy định thời điểm một giao dịch được lấy và nhả khóa trên các mục dữ liệu. Một tính chất quan trọng của 2PL là: **mọi lịch thực thi hợp lệ được tạo ra theo 2PL đều khả tuần tự theo xung đột** (*conflict-serializable*).

Điều đó có nghĩa là các giao dịch vẫn có thể chạy xen kẽ, nhưng kết quả của lịch luôn tương đương với một thứ tự chạy tuần tự nào đó. Ta có thể chứng minh tính chất này bằng cách gắn mỗi giao dịch với một thời điểm gọi là *điểm khóa* (*lock point*), rồi chứng minh rằng mọi cạnh trong đồ thị ưu tiên đều đi theo thứ tự các điểm khóa.

## 1. Lịch tuần tự và khả tuần tự theo xung đột

Một giao dịch gồm các thao tác đọc và ghi dữ liệu. Ký hiệu thường dùng:

- `R1(A)`: giao dịch `T1` đọc mục dữ liệu `A`.
- `W1(A)`: giao dịch `T1` ghi mục dữ liệu `A`.
- `C1`: `T1` commit.
- `A1`: `T1` abort.

Một **lịch** (*schedule*) là thứ tự thực hiện các thao tác của nhiều giao dịch. Lịch phải giữ nguyên thứ tự nội bộ của từng giao dịch, nhưng thao tác của các giao dịch khác nhau có thể xen kẽ.

Ví dụ, nếu `T1` thực hiện `R1(A)` rồi `W1(A)`, lịch không được đảo thứ tự hai thao tác đó. Tuy nhiên, thao tác của `T2` có thể xuất hiện giữa chúng nếu các quy tắc điều khiển tương tranh cho phép.

Một lịch là **tuần tự** (*serial schedule*) khi tất cả thao tác của một giao dịch hoàn thành trước khi giao dịch tiếp theo bắt đầu. Lịch tuần tự dễ phân tích, nhưng nếu hệ thống chỉ chạy từng giao dịch một thì khả năng sử dụng tài nguyên thường thấp.

Một lịch là **khả tuần tự theo xung đột** nếu có thể biến đổi nó thành một lịch tuần tự tương đương bằng cách hoán đổi các thao tác không xung đột. Hai thao tác thuộc hai giao dịch khác nhau được xem là xung đột khi chúng cùng truy cập một mục dữ liệu và ít nhất một thao tác là ghi:

| Cặp thao tác | Có xung đột? | Lý do |
|---|---|---|
| `R1(A)` và `R2(A)` | Không | Cả hai chỉ đọc `A`; đổi thứ tự không làm thay đổi giá trị được đọc hoặc ghi. |
| `R1(A)` và `W2(A)` | Có | Ghi có thể làm thay đổi giá trị mà thao tác đọc nhận được. |
| `W1(A)` và `R2(A)` | Có | Đổi thứ tự có thể làm `T2` đọc giá trị khác. |
| `W1(A)` và `W2(A)` | Có | Đổi thứ tự có thể làm thay đổi giá trị cuối cùng của `A`. |
| `R1(A)` và `W2(B)` | Không | Hai thao tác truy cập hai mục dữ liệu khác nhau. |

### Đồ thị ưu tiên

Ta kiểm tra khả tuần tự theo xung đột bằng **đồ thị ưu tiên** (*precedence graph*, còn gọi là serialization graph):

1. Mỗi giao dịch trong lịch là một đỉnh.
2. Thêm cạnh `Ti → Tj` nếu có một cặp thao tác xung đột trên cùng mục dữ liệu, thao tác của `Ti` xuất hiện trước thao tác của `Tj`.
3. Kiểm tra chu trình trong đồ thị.

Lịch khả tuần tự theo xung đột khi và chỉ khi đồ thị ưu tiên không có chu trình. Nếu đồ thị không chu trình, một thứ tự tô-pô của các đỉnh chính là thứ tự tuần tự tương đương.

Ví dụ, nếu `W1(A)` xuất hiện trước `R2(A)`, ta thêm cạnh `T1 → T2`. Nếu một cặp xung đột khác tạo cạnh `T2 → T1`, đồ thị có chu trình và lịch không khả tuần tự theo xung đột.

## 2. Giao thức khóa hai pha

2PL yêu cầu mỗi giao dịch tuân theo hai giai đoạn. Giao thức áp dụng cho các khóa được cấp trước khi giao dịch đọc hoặc ghi dữ liệu.

### Hai loại khóa cơ bản

- **Khóa chia sẻ `S(A)`**: dùng để đọc `A`. Nhiều giao dịch có thể đồng thời giữ khóa chia sẻ trên cùng một mục dữ liệu.
- **Khóa độc quyền `X(A)`**: dùng để ghi `A`. Khi một giao dịch giữ khóa độc quyền, giao dịch khác không thể đồng thời giữ khóa chia sẻ hoặc độc quyền trên cùng mục dữ liệu.

Bảng tương thích khóa:

| Khóa đang được giữ | Yêu cầu `S` | Yêu cầu `X` |
|---|---:|---:|
| `S` | Được cấp | Phải chờ |
| `X` | Phải chờ | Phải chờ |

Một thao tác đọc cần khóa `S` hoặc `X`; một thao tác ghi cần khóa `X`. Nếu giao dịch đang giữ `S(A)` rồi muốn ghi `A`, nó phải nâng cấp lên `X(A)` khi việc nâng cấp còn được phép.

### Giai đoạn tăng trưởng và giai đoạn thu hẹp

**Giai đoạn tăng trưởng (*growing phase*)** bắt đầu khi giao dịch lấy khóa đầu tiên. Trong giai đoạn này, giao dịch có thể lấy thêm khóa và nâng cấp `S` lên `X`, nhưng chưa được nhả khóa.

**Giai đoạn thu hẹp (*shrinking phase*)** bắt đầu khi giao dịch nhả khóa đầu tiên hoặc thực hiện thao tác hạ cấp khóa. Từ thời điểm đó, giao dịch có thể tiếp tục nhả khóa, nhưng không được lấy khóa mới hoặc nâng cấp khóa.

Quy tắc cốt lõi là:

> Sau khi đã nhả một khóa, giao dịch không được lấy thêm khóa nào.

Ví dụ, chuỗi thao tác sau tuân thủ 2PL:

```text
X(A) → đọc/ghi A → X(B) → đọc/ghi B → U(A) → U(B)
```

Giao dịch lấy cả hai khóa trước khi nhả khóa đầu tiên. Ngược lại, chuỗi sau vi phạm 2PL:

```text
X(A) → ghi A → U(A) → X(B) → ghi B → U(B)
```

Sau `U(A)`, giao dịch đã bước vào giai đoạn thu hẹp. Việc lấy `X(B)` sau đó là không hợp lệ.

## 3. Điểm khóa (*lock point*)

**Điểm khóa của một giao dịch là thời điểm giao dịch lấy khóa cuối cùng của nó** (tính cả lần nâng cấp khóa nếu có). Đây là thời điểm giao dịch kết thúc giai đoạn tăng trưởng và chuyển sang giai đoạn thu hẹp.

Nếu một giao dịch không có lần lấy khóa nào thì nó không truy cập dữ liệu được bảo vệ bởi giao thức; có thể bỏ qua giao dịch đó khi xét thứ tự các điểm khóa. Với các giao dịch có khóa, điểm khóa nằm trước lần nhả khóa đầu tiên hoặc trùng với thời điểm chuyển pha theo mô hình thực thi đang xét.

Điểm khóa không phải là thời điểm lấy khóa đầu tiên, cũng không nhất thiết là thời điểm commit. Nó ghi nhận lúc giao dịch đã hoàn tất việc xin thêm quyền truy cập dữ liệu.

Thứ tự tăng dần của các điểm khóa tạo ra một thứ tự tuần tự tương đương cho các giao dịch tuân thủ 2PL. Phần tiếp theo chứng minh vì sao.

## 4. Vì sao lịch tuân thủ 2PL luôn khả tuần tự theo xung đột?

Xét hai giao dịch `Ti` và `Tj` có một cặp thao tác xung đột trên mục dữ liệu `A`. Giả sử thao tác của `Ti` xuất hiện trước thao tác của `Tj` trong lịch.

Vì hai thao tác xung đột, ít nhất một thao tác là ghi. Do đó, hai giao dịch cần những khóa không tương thích trên `A`: một giao dịch cần khóa độc quyền, còn giao dịch kia cần khóa chia sẻ hoặc độc quyền. Bộ quản lý khóa không thể cấp đồng thời hai khóa đó.

Để thao tác của `Tj` được thực hiện sau thao tác của `Ti`, `Ti` phải nhả khóa đang ngăn yêu cầu của `Tj` được cấp. Theo 2PL, `Ti` đã lấy tất cả khóa của mình trước lần nhả khóa đầu tiên. Vì vậy, điểm khóa của `Ti` xảy ra trước khi khóa trên `A` được nhả. `Tj` chỉ có thể lấy khóa xung đột sau khi `Ti` nhả khóa; điểm khóa của `Tj` xảy ra tại hoặc sau lần lấy khóa đó.

Ta có thứ tự:

```text
lock point(Ti)
    < Ti nhả khóa trên A
    < Tj được cấp khóa xung đột trên A
    ≤ lock point(Tj)
```

Vì thế:

```text
Nếu đồ thị ưu tiên có cạnh Ti → Tj,
thì lock point(Ti) < lock point(Tj).
```

Đây là quan hệ quan trọng nhất trong chứng minh.

### Chứng minh đồ thị không thể có chu trình

Giả sử đồ thị ưu tiên có một chu trình:

```text
T1 → T2 → T3 → ... → Tn → T1
```

Theo quan hệ vừa chứng minh, mỗi cạnh buộc điểm khóa tăng nghiêm ngặt:

```text
LP(T1) < LP(T2)
     < LP(T3) < ... < LP(Tn)
     < LP(T1)
```

Điều này yêu cầu một thời điểm phải nhỏ hơn chính nó, điều không thể xảy ra. Do đó, đồ thị ưu tiên không có chu trình.

Vì đồ thị ưu tiên không chu trình, mọi lịch được tạo ra bởi 2PL đều khả tuần tự theo xung đột. Ta có thể sắp xếp các giao dịch theo thứ tự điểm khóa tăng dần; thứ tự đó là một thứ tự tuần tự tương đương với lịch thực tế.

## 5. Ví dụ: một lịch xen kẽ tuân thủ 2PL

Xét hai giao dịch:

```text
T1: X1(A), W1(A), X1(B), W1(B), U1(A), U1(B)
T2: X2(A), W2(A), U2(A)
```

Trong đó `Xi(A)` là lấy khóa độc quyền trên `A` cho giao dịch `Ti`, còn `Ui(A)` là nhả khóa đó. Một lịch xen kẽ hợp lệ có thể là:

| Bước | Thao tác | Giải thích |
|---:|---|---|
| 1 | `X1(A)` | `T1` lấy khóa độc quyền trên `A`. |
| 2 | `W1(A)` | `T1` ghi `A`. |
| 3 | `X1(B)` | `T1` lấy khóa độc quyền trên `B`; đây là khóa cuối cùng của `T1`. |
| 4 | `W1(B)` | `T1` ghi `B`. |
| 5 | `U1(A)` | `T1` nhả `A` và bắt đầu giai đoạn thu hẹp. |
| 6 | `X2(A)` | Sau khi `T1` nhả `A`, `T2` được cấp khóa độc quyền trên `A`. |
| 7 | `W2(A)` | `T2` ghi `A`. |
| 8 | `U2(A)` | `T2` nhả `A`. |
| 9 | `U1(B)` | `T1` nhả khóa còn lại. |

Lịch này không phải lịch tuần tự: `T2` đã ghi `A` trong khi `T1` vẫn còn giữ khóa trên `B`. Tuy nhiên, cả hai giao dịch đều tuân thủ 2PL:

- `T1` lấy `A` và `B` trước khi nhả khóa đầu tiên. Sau bước 5, `T1` chỉ nhả khóa còn lại.
- `T2` lấy `A`, thực hiện ghi rồi nhả khóa; giao dịch không lấy khóa mới sau khi bắt đầu nhả khóa.

Hai thao tác xung đột trên `A` là `W1(A)` và `W2(A)`. Thao tác của `T1` đứng trước thao tác của `T2`, nên đồ thị ưu tiên có cạnh:

```text
T1 → T2
```

Không có cạnh ngược `T2 → T1`, vì `T2` không có thao tác xung đột nào trên `B` và thao tác ghi trên `A` của `T2` xuất hiện sau thao tác ghi của `T1`. Đồ thị không có chu trình. Thứ tự tuần tự tương đương là:

```text
T1 → T2
```

Điểm khóa cũng xác nhận kết quả: `LP(T1)` nằm ở bước 3, khi `T1` lấy `X1(B)`; `LP(T2)` nằm ở bước 6, khi `T2` lấy `X2(A)`. Vì `LP(T1) < LP(T2)`, thứ tự điểm khóa khớp với cạnh `T1 → T2`.

Ví dụ cho thấy 2PL vẫn cho phép các giao dịch xen kẽ và giữ khóa trên những mục dữ liệu khác nhau trong cùng một khoảng thời gian. Điều được bảo đảm là thứ tự xung đột không tạo thành chu trình.

## 6. Cách phân tích một lịch cụ thể

Khi đề bài yêu cầu xác định lịch có tuân thủ 2PL và có khả tuần tự theo xung đột hay không, có thể làm theo trình tự sau:

1. **Liệt kê thao tác khóa.** Xác định khóa `S`, khóa `X`, nâng cấp/hạ cấp và thao tác nhả khóa của từng giao dịch.
2. **Kiểm tra quyền truy cập.** Mỗi lần đọc phải có `S` hoặc `X`; mỗi lần ghi phải có `X`. Các khóa không tương thích không được đồng thời được cấp trên cùng mục dữ liệu.
3. **Kiểm tra hai pha.** Với từng giao dịch, tìm lần nhả khóa đầu tiên. Sau thời điểm đó không được có lần lấy khóa mới hoặc nâng cấp khóa.
4. **Tìm điểm khóa.** Ghi nhận lần lấy khóa cuối cùng của mỗi giao dịch.
5. **Lập đồ thị ưu tiên.** Xét các cặp thao tác thuộc hai giao dịch, cùng mục dữ liệu và có ít nhất một thao tác ghi. Thêm cạnh theo thứ tự xuất hiện trong lịch.
6. **Kết luận.** Nếu lịch tuân thủ 2PL thì định lý bảo đảm đồ thị ưu tiên không chu trình. Khi cần chỉ ra thứ tự tuần tự tương đương, sắp xếp các giao dịch theo điểm khóa tăng dần hoặc tìm một thứ tự tô-pô của đồ thị.

Nếu đề bài chỉ đưa lịch gồm các thao tác đọc/ghi mà không cho biết các khóa hoặc giao thức khóa, ta có thể kiểm tra khả tuần tự theo xung đột bằng đồ thị ưu tiên, nhưng không thể khẳng định lịch được tạo ra bởi 2PL chỉ từ thứ tự đọc/ghi đó.

## 7. Phạm vi bảo đảm của 2PL

2PL bảo đảm **khả tuần tự theo xung đột**. Điều này không đồng nghĩa với việc giao thức giải quyết mọi vấn đề của xử lý giao dịch.

### 2PL không loại bỏ deadlock

Hai giao dịch có thể giữ các khóa khác nhau rồi chờ khóa của nhau:

```text
T1 giữ X(A), chờ X(B)
T2 giữ X(B), chờ X(A)
```

Khi đó, `T1` chờ `T2` và `T2` chờ `T1`; cả hai không thể tiếp tục nếu hệ thống không phát hiện và xử lý deadlock. Đây là chu trình trong **đồ thị chờ** (*wait-for graph*), khác với chu trình trong đồ thị ưu tiên. Đồ thị chờ mô tả quan hệ chờ khóa; đồ thị ưu tiên mô tả thứ tự các thao tác xung đột. 2PL bảo đảm đồ thị ưu tiên không có chu trình, nhưng không bảo đảm đồ thị chờ không có chu trình.

### 2PL cơ bản không tự bảo đảm lịch nghiêm ngặt

Trong 2PL cơ bản, giao dịch có thể nhả khóa độc quyền trước khi commit. Nếu giao dịch khác đọc hoặc ghi giá trị chưa commit đó, khi giao dịch đầu tiên abort, giao dịch sau có thể phải rollback theo. Vì vậy, 2PL cơ bản bảo đảm khả tuần tự theo xung đột nhưng không tự bảo đảm lịch tránh đọc dữ liệu chưa commit hoặc tránh rollback dây chuyền.

Một số biến thể bổ sung quy tắc giữ khóa:

- **Strict 2PL**: giữ các khóa độc quyền đến khi commit hoặc abort. Biến thể này ngăn giao dịch khác đọc hoặc ghi dữ liệu do giao dịch chưa kết thúc sửa đổi, nhờ đó tránh cascading abort và tạo lịch nghiêm ngặt theo định nghĩa thông dụng.
- **Rigorous 2PL**: giữ cả khóa chia sẻ và khóa độc quyền đến khi commit hoặc abort. Thứ tự kết thúc giao dịch khi đó cũng phù hợp với thứ tự tuần tự được suy ra từ khóa.

Các biến thể này vẫn dựa trên nguyên tắc hai pha và vẫn có tính chất khả tuần tự theo xung đột của 2PL.

### 2PL là điều kiện đủ, không phải điều kiện cần

Có những lịch khả tuần tự theo xung đột nhưng không tuân thủ 2PL. Chẳng hạn, một giao dịch có thể nhả khóa trên `A`, sau đó mới lấy khóa trên `B`; hành vi đó vi phạm quy tắc hai pha. Dù vậy, nếu mọi xung đột trong lịch vẫn có cùng một thứ tự giữa các giao dịch và đồ thị ưu tiên không có chu trình, lịch vẫn khả tuần tự theo xung đột.

Vì thế, từ “lịch tuân thủ 2PL” ta có thể kết luận lịch khả tuần tự theo xung đột. Chiều ngược lại không luôn đúng: chỉ biết một lịch khả tuần tự theo xung đột không đủ để kết luận lịch tuân thủ 2PL.

## 8. Những nhầm lẫn thường gặp

- **Cho rằng 2PL buộc giao dịch chạy lần lượt.** Không đúng. Các giao dịch vẫn có thể xen kẽ; bộ quản lý khóa chỉ buộc những thao tác xung đột phải chờ nhau.
- **Nhầm điểm khóa với lần lấy khóa đầu tiên.** Điểm khóa là lần lấy khóa cuối cùng, không phải lần đầu tiên.
- **Cho rằng có thể lấy khóa mới sau khi nhả một khóa nếu khóa mới thuộc mục dữ liệu khác.** Không đúng. 2PL áp dụng cho toàn bộ giao dịch, không chỉ từng mục dữ liệu riêng lẻ.
- **Nhầm đồ thị ưu tiên với đồ thị chờ.** Đồ thị ưu tiên dùng để kiểm tra khả tuần tự; đồ thị chờ dùng để phát hiện deadlock.
- **Cho rằng khả tuần tự đồng nghĩa với an toàn phục hồi.** Khả tuần tự theo xung đột nói về tương đương thứ tự thao tác. Tính nghiêm ngặt, khả phục hồi và việc tránh cascading abort cần được xem xét riêng; Strict 2PL bổ sung quy tắc giữ khóa độc quyền đến khi giao dịch kết thúc.

## Kết luận

Hai pha giới hạn thời điểm giao dịch lấy và nhả khóa. Khi một cặp thao tác xung đột buộc `Ti` đứng trước `Tj`, quy tắc không lấy khóa sau khi nhả khóa khiến điểm khóa của `Ti` phải đứng trước điểm khóa của `Tj`. Vì mọi cạnh của đồ thị ưu tiên đều làm điểm khóa tăng nghiêm ngặt, đồ thị không thể có chu trình. Do đó, mọi lịch tuân thủ 2PL đều khả tuần tự theo xung đột và có thể được ánh xạ về một thứ tự tuần tự theo thứ tự điểm khóa.
