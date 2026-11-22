# Xung đột đọc–ghi, ghi–đọc và ghi–ghi trong mô hình thực thi giao dịch

## 1. Vì sao phải xét xung đột giữa các thao tác?

Trong hệ thống có nhiều người dùng, hai giao dịch (*transactions*) có thể cùng truy cập một đối tượng dữ liệu trước khi một trong hai hoàn tất. Việc các câu lệnh xen kẽ nhau giúp tăng thông lượng, nhưng cũng đặt ra câu hỏi: **thứ tự đọc và ghi có làm thay đổi kết quả hay phá vỡ quy tắc nghiệp vụ không?**

Ví dụ, một bảng tài khoản đang có dòng dữ liệu:

```text
account_id = 101
balance    = 1000
```

Hai giao dịch cùng thao tác:

- **T1**: đọc số dư để quyết định có cho phép rút tiền.
- **T2**: cập nhật số dư vì có giao dịch chuyển tiền khác.

Nếu T1 đọc trước khi T2 cập nhật, quyết định của T1 có thể dựa trên số dư cũ. Nếu T2 đã ghi và commit rồi T1 mới đọc, T1 có thể nhìn thấy giá trị mới. Nếu cả hai cùng ghi vào một dòng, hệ quản trị phải điều phối việc cập nhật. Những quan hệ đó là nền tảng của **mô hình xung đột thao tác** (*conflict model*) trong lý thuyết điều khiển tương tranh.

Cần phân biệt hai nghĩa thường bị trộn lẫn:

1. **Xung đột theo lý thuyết lịch thực thi**: hai thao tác thuộc hai giao dịch khác nhau, tác động cùng đối tượng dữ liệu, và có ít nhất một thao tác ghi. Định nghĩa này dùng để phân tích **ràng buộc thứ tự** giữa các giao dịch.
2. **Tranh chấp thực thi**: một thao tác phải chờ khóa, bị từ chối hoặc bị hủy vì giao dịch khác. Đây là hành vi cụ thể của hệ quản trị và mức cô lập; có xung đột lý thuyết **không nhất thiết** có chờ khóa hoặc lỗi.

Một xung đột tự nó chưa phải là lỗi. Khi T2 cập nhật dữ liệu rồi commit, T1 đọc dữ liệu mới là tình huống bình thường và hữu ích. Vấn đề xuất hiện khi các quan hệ phụ thuộc hình thành thứ tự không hợp lý, hoặc chương trình không bảo vệ bất biến nghiệp vụ trước tương tranh.

## 2. Ký hiệu đọc, ghi và lịch thực thi

Ta dùng các ký hiệu quen thuộc trong môn học cơ sở dữ liệu:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `T1`, `T2` | Hai giao dịch riêng biệt |
| `r1(X)` | Giao dịch T1 đọc đối tượng dữ liệu X |
| `w1(X)` | Giao dịch T1 ghi/thay đổi X |
| `r2(Y)` | Giao dịch T2 đọc Y |
| `c1` | T1 commit |
| `a1` | T1 abort hoặc rollback |

Một **lịch thực thi** (*schedule*, ký hiệu S) mô tả thứ tự các thao tác từ một hay nhiều giao dịch. Ví dụ:

```text
T1:   r1(X) ---------------------- w1(Y) --- c1
T2:            r2(Y) --- w2(X) ---------------- c2

S = r1(X), r2(Y), w2(X), w1(Y), c1, c2
```

Trật tự từ trái sang phải là thứ tự thao tác xuất hiện trong lịch. Một giao dịch có thể bắt đầu trước nhưng commit sau giao dịch khác; do đó chỉ nhìn thứ tự `BEGIN` hoặc `COMMIT` là chưa đủ để hiểu tương tác giữa các thao tác.

### 2.1. Khi nào hai thao tác được xem là xung đột?

Trong mô hình lịch **một phiên bản dữ liệu** (*single-version schedule*), hai thao tác `op_i(X)` và `op_j(Y)` xung đột khi **đồng thời thỏa ba điều kiện**:

1. Chúng thuộc **hai giao dịch khác nhau**: `i ≠ j`.
2. Chúng truy cập **cùng đối tượng dữ liệu**: `X = Y`.
3. **Ít nhất một thao tác là ghi**.

Điều kiện thứ ba dẫn đến ba loại xung đột:

| Thứ tự thao tác | Tên | Ký hiệu | Ý nghĩa |
| --- | --- | --- | --- |
| Đọc trước, ghi sau | **Đọc–ghi** (*read–write*, RW) | `r1(X) → w2(X)` | T1 đã đọc X trước khi T2 thay đổi X |
| Ghi trước, đọc sau | **Ghi–đọc** (*write–read*, WR) | `w1(X) → r2(X)` | T2 đọc X sau khi T1 đã ghi X trong lịch |
| Ghi trước, ghi sau | **Ghi–ghi** (*write–write*, WW) | `w1(X) → w2(X)` | Cả T1 và T2 đều thay đổi X; thứ tự các lần ghi có ý nghĩa |

Mũi tên biểu thị **thứ tự phụ thuộc trong lịch**, chưa có nghĩa thao tác thứ hai chắc chắn bị chặn.

Hai lần **đọc–đọc** `r1(X)` và `r2(X)` không xung đột theo định nghĩa này: nếu chỉ đổi chỗ hai lần đọc, nội dung dữ liệu không đổi. Tương tự, `r1(X)` và `w2(Y)` không xung đột khi `X` và `Y` là hai đối tượng độc lập.

**Phạm vi đối tượng X rất quan trọng.** X có thể là một hàng, một bản ghi logic, hoặc đối tượng trừu tượng trong bài toán. Ở hệ quản trị thực, còn có xung đột mức bảng, phạm vi giá trị, chỉ mục, khóa ngoại và *predicate* (điều kiện truy vấn). Khi xét một ví dụ lý thuyết theo từng hàng, cần ghi rõ giả định về phạm vi dữ liệu.

### 2.2. Tại sao đổi thứ tự hai thao tác xung đột có thể đổi kết quả?

Giả sử `X = 100`.

- `r1(X); w2(X := 120)`: T1 có thể đọc `100`.
- `w2(X := 120); r1(X)`: T1 có thể đọc `120` nếu bản ghi mới đã khả kiến theo quy tắc cô lập.

Đổi chỗ hai thao tác tạo ra khác biệt về dữ liệu T1 dùng để tính toán. Với cặp ghi–ghi:

- `w1(X := 120); w2(X := 90)`: nếu cả hai ghi đều có hiệu lực và ghi sau thay thế giá trị trước, X cuối cùng là `90`.
- `w2(X := 90); w1(X := 120)`: X cuối cùng là `120`.

Đó là lý do phân tích xung đột quan tâm đến **thứ tự** giữa các thao tác. Các ví dụ trên là mô hình đơn giản; trong PostgreSQL có MVCC, thao tác đọc có thể thấy phiên bản đã commit trước đó thay vì thay đổi chưa commit của giao dịch khác.

## 3. Xung đột đọc–ghi (RW): đọc trạng thái cũ trước khi người khác thay đổi

Cặp xung đột đọc–ghi có dạng:

```text
T1:  r1(X) ---------------------------
T2:             w2(X) --------- c2

Quan hệ: T1 --RW--> T2
```

T1 đọc X; sau đó T2 ghi X. Nếu T1 dùng giá trị đọc được để quyết định một thao tác về sau, kết quả của T1 có thể không còn phù hợp với dữ liệu vừa thay đổi.

### 3.1. Ví dụ: kiểm tra tồn kho rồi mới đặt hàng

Giả sử X là số lượng hàng còn lại, ban đầu `stock = 10`:

1. T1 đọc `stock = 10`, quyết định sẽ nhận đơn hàng có số lượng `8`.
2. T2 hoàn thành một đơn hàng khác, làm `stock = 4`.
3. T1 tiếp tục dựa vào số `10` đã đọc, đồng ý đặt tiếp `8`.

Nếu chương trình không có bước kiểm tra và cập nhật đúng cách, nó có thể xác nhận số lượng bán vượt tồn kho. Cặp `r1(stock) → w2(stock)` cho biết **giá trị T1 sử dụng đã trở nên cũ**; đây là một trong các điều kiện có thể tạo ra lỗi *check-then-act*.

Tuy nhiên, T1 đọc trước khi T2 cập nhật **không tự động** làm dữ liệu sai. Nếu T1 chỉ hiển thị thông tin tham khảo, không tiếp tục ghi hoặc đưa ra quyết định đòi hỏi tính nhất quán, sự thay đổi đó có thể hoàn toàn chấp nhận được.

### 3.2. Liên hệ với non-repeatable read

Ở mức `READ COMMITTED` của PostgreSQL, T1 có thể chạy hai lần `SELECT` trong cùng giao dịch:

```text
Thời điểm    Giao dịch T1                  Giao dịch T2
   1         BEGIN
   2         SELECT X --> 100
   3                                      BEGIN
   4                                      UPDATE X = 120
   5                                      COMMIT
   6         SELECT X --> 120
   7         COMMIT
```

Lần đọc thứ hai trả về giá trị khác lần đầu; đây là **non-repeatable read** (*đọc không lặp lại*). Điểm mấu chốt là một giao dịch đã đọc dữ liệu, rồi giao dịch khác commit thay đổi trước lần đọc tiếp theo.

Ở `REPEATABLE READ` của PostgreSQL, hai lần `SELECT` thông thường trong cùng giao dịch dùng một ảnh chụp nhất quán, nên trường hợp trên không cho T1 tự nhiên nhìn thấy giá trị mới ở lần đọc thứ hai. Nhưng ảnh chụp nhất quán vẫn **không đồng nghĩa** toàn bộ lịch thực thi tương đương một thứ tự tuần tự trong mọi bài toán.

### 3.3. RW anti-dependency trong cơ sở dữ liệu dùng MVCC

PostgreSQL sử dụng **MVCC** (*Multi-Version Concurrency Control*): các lần đọc thường nhìn một phiên bản dữ liệu nhất quán mà không cần chặn giao dịch đang ghi. Khi T1 đã đọc phiên bản cũ của X và T2 tạo một phiên bản mới thay thế, quan hệ này thường được gọi là **RW anti-dependency** trong phân tích đồ thị phụ thuộc phiên bản.

Từ *anti-dependency* nhấn mạnh rằng T1 **không đọc kết quả ghi của T2**; trái lại, T1 đã đọc trạng thái **trước** thay đổi đó. Nếu T1 tiếp tục ghi những dữ liệu khác, các anti-dependency ở nhiều phía có thể tạo chu trình phụ thuộc, góp phần hình thành hiện tượng *write skew* hoặc lỗi khó thấy hơn trong mô hình đồng thời.

Một điểm cần nhớ: **truy vấn `SELECT` thông thường của PostgreSQL không khóa độc quyền hàng chỉ vì đang đọc**. Vì vậy, xung đột RW không nhất thiết tạo hàng đợi chờ khóa.

## 4. Xung đột ghi–đọc (WR): đọc kết quả của một lần ghi trước đó

Cặp xung đột ghi–đọc có dạng:

```text
T1:  w1(X) ----------- c1
T2:                         r2(X)

Quan hệ: T1 --WR--> T2
```

T1 ghi X; sau đó T2 đọc X. Nếu lần đọc của T2 thực sự nhìn thấy phiên bản do T1 tạo ra, ta có một quan hệ **read-from dependency**: kết quả của T2 phụ thuộc vào giá trị T1 đã tạo.

### 4.1. Trường hợp bình thường: đọc dữ liệu đã commit

Ví dụ, T1 chuyển `100` vào tài khoản, làm số dư từ `1000` thành `1100`, rồi commit. T2 sau đó truy vấn số dư và thấy `1100`.

Đây là xung đột WR **hợp lệ và thường gặp**: những giao dịch đến sau cần có khả năng đọc dữ liệu giao dịch trước đã commit. Không có lý do gì để xem mọi WR là lỗi.

### 4.2. Trường hợp nguy hiểm: dirty read

Giả sử lịch lý thuyết cho phép T2 thấy dữ liệu T1 ghi khi T1 **chưa commit**:

```text
T1:  BEGIN --- w1(X := 1100) ---------------- ROLLBACK
T2:                        r2(X) -> 1100 --- xử lý tiếp
```

T2 đã đọc một giá trị không bao giờ trở thành trạng thái được commit vì T1 rollback. Hiện tượng này gọi là **dirty read** (*đọc bẩn*). Nếu T2 dùng `1100` để ra quyết định thanh toán, kết quả có thể không hợp lệ.

Trong **PostgreSQL**, truy vấn `SELECT` thông thường ở `READ COMMITTED` sẽ **không** đọc dữ liệu chưa commit của T1; nó đọc phiên bản đã commit trước đó. PostgreSQL cũng xử lý `READ UNCOMMITTED` thực tế như `READ COMMITTED`. Vì vậy, không thể dựng dirty read bằng các lệnh `SELECT` thông thường trên PostgreSQL rồi kỳ vọng T2 thấy giá trị chưa commit.

Điều đó **không làm WR biến mất** trong mô hình phụ thuộc. Nó cho thấy hệ quản trị kiểm soát việc phiên bản nào được phép đọc. Để phân tích chính xác, cần biết không chỉ thứ tự thao tác `w1(X) → r2(X)` mà còn **T2 đọc phiên bản nào của X** và T1 đã commit hay chưa.

### 4.3. Dirty read và cascading rollback

Trong mô hình cho phép đọc bẩn, nếu T2 đọc giá trị chưa commit do T1 tạo ra, T2 có thể tiếp tục tính toán hoặc ghi kết quả dựa trên nó. Khi T1 rollback, T2 cũng có thể phải rollback để tránh giữ dữ liệu phụ thuộc vào một giao dịch thất bại. Hiện tượng hoàn tác kéo theo này gọi là **cascading abort**.

Các hệ quản trị giao dịch hiện đại thường cung cấp cơ chế ngăn dirty read hoặc hạn chế những lịch không thể phục hồi bằng quy tắc khóa, MVCC và isolation. Một lịch **có thể phục hồi** (*recoverable*) yêu cầu giao dịch đã đọc dữ liệu của giao dịch khác không được commit trước khi giao dịch tạo ra dữ liệu đó commit; lịch **không có đọc bẩn** (*cascadeless*) bảo vệ mạnh hơn bằng cách chỉ cho đọc những dữ liệu do giao dịch đã commit tạo ra.

## 5. Xung đột ghi–ghi (WW): hai giao dịch cùng thay đổi một đối tượng

Cặp ghi–ghi có dạng:

```text
T1:  w1(X) ------------ c1
T2:       (đợi nếu cần) ----- w2(X) --- c2

Quan hệ: T1 --WW--> T2
```

Hai lần ghi cùng đối tượng có thể tạo kết quả khác nhau tùy thứ tự, và DBMS phải quyết định khi nào giao dịch thứ hai được phép cập nhật.

### 5.1. Ví dụ dễ hình dung: hai lần thay số dư

Ban đầu X là số dư `1000`:

- T1 thực hiện `UPDATE balance = 1200`.
- T2 thực hiện `UPDATE balance = 900`.

Nếu cả hai ghi đều hoàn tất, thao tác ghi có hiệu lực sau cùng quyết định giá trị X cuối (trong ví dụ phép gán tuyệt đối). Việc đổi thứ tự làm X kết thúc ở `1200` hoặc `900`.

Trong PostgreSQL, hai giao dịch cùng chạy `UPDATE` trên **cùng một hàng** thường tranh chấp khóa hàng. Nếu T1 chưa kết thúc, T2 phải chờ khóa; sau khi T1 commit, T2 có thể tiếp tục theo mức cô lập và điều kiện của câu lệnh, hoặc có thể gặp lỗi xung đột tại mức cô lập cao hơn.

### 5.2. Lost update: đọc cũ rồi ghi đè

**Lost update** (*mất cập nhật*) thường là lỗi phát sinh từ cả quan hệ **RW** lẫn **WW**, không chỉ một cặp WW đơn lẻ.

Giả sử hai ứng dụng đọc số dư `1000` rồi tính giá trị mới bên ngoài SQL:

```text
T1:  đọc 1000; muốn cộng 200; tự tính 1200
T2:  đọc 1000; muốn trừ 100; tự tính  900

Thực tế:
T1:  r1(X=1000) -------- w1(X=1200) --- COMMIT
T2:       r2(X=1000) -------------------- w2(X=900) --- COMMIT

Kết quả: 900, trong khi nếu áp dụng cả +200 và -100 thì phải là 1100.
```

T2 ghi `900` tính từ dữ liệu cũ, nên hiệu quả của phép cộng `200` từ T1 bị ghi đè. Việc DBMS lần lượt cấp khóa cho hai lệnh `UPDATE` **không tự sửa được công thức đã được ứng dụng tính sai từ ảnh chụp cũ**.

Cách khắc phục đơn giản cho phép cộng/trừ một hàng là **cập nhật dựa trên giá trị hiện tại trong cùng câu SQL**:

```sql
UPDATE accounts
SET balance = balance + 200
WHERE account_id = 101;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101
  AND balance >= 100;
```

Khi hai câu `UPDATE` chạy đồng thời ở `READ COMMITTED` của PostgreSQL, DBMS dùng cơ chế khóa và cập nhật hàng hiện hành để xử lý, nên phép cộng/trừ không ghi đè bằng một giá trị tuyệt đối tính từ số dư cũ. Với yêu cầu phức tạp hơn, có thể sử dụng `SELECT ... FOR UPDATE`, kiểm tra phiên bản hoặc mức cô lập phù hợp.

### 5.3. WW không đồng nghĩa deadlock

Nếu T1 giữ khóa X và T2 cần ghi X, T2 thường **chờ**. Đây là tranh chấp khóa thông thường, không nhất thiết là deadlock.

**Deadlock** (*bế tắc*) đòi hỏi một **chu trình chờ**. Ví dụ:

```text
T1 đã khóa tài khoản A, muốn khóa B.
T2 đã khóa tài khoản B, muốn khóa A.

T1 chờ T2 giải phóng B
T2 chờ T1 giải phóng A
           -> chu trình chờ
```

PostgreSQL có cơ chế phát hiện deadlock và hủy một trong các giao dịch để phá vòng chờ. Các luồng nghiệp vụ thường giảm nguy cơ này bằng cách lấy khóa nhiều hàng theo cùng một thứ tự ổn định, giữ giao dịch ngắn và có cơ chế retry khi gặp deadlock.

## 6. So sánh nhanh ba kiểu xung đột

| Khía cạnh | RW: `r1(X) → w2(X)` | WR: `w1(X) → r2(X)` | WW: `w1(X) → w2(X)` |
| --- | --- | --- | --- |
| Thao tác trước | Đọc | Ghi | Ghi |
| Thao tác sau | Ghi | Đọc | Ghi |
| Câu hỏi chính | Dữ liệu T1 đọc còn phù hợp khi T2 thay đổi không? | T2 nhìn thấy phiên bản nào do T1 tạo, và T1 đã commit chưa? | Ai cập nhật X trước và phiên bản nào được giữ? |
| Rủi ro điển hình | Quyết định dựa trên giá trị cũ, non-repeatable read, write skew | Dirty read nếu được phép; phụ thuộc vào giao dịch chưa commit | Chờ khóa, ghi đè bằng giá trị cũ, lost update, deadlock khi có nhiều khóa |
| Trong PostgreSQL thông thường | `SELECT` thường không chặn `UPDATE` | `SELECT` không đọc thay đổi chưa commit | Hai `UPDATE` cùng hàng được điều phối bằng khóa |
| Biện pháp thường dùng | Đọc có khóa, cập nhật có điều kiện, kiểm tra phiên bản, serializable | Không đọc bẩn, kiểm soát mức cô lập và thời điểm commit | Cập nhật nguyên tử, khóa theo thứ tự, optimistic locking, retry |

Cột “rủi ro” chỉ nêu các hiện tượng **có thể liên quan**; không có nghĩa một cặp thao tác theo đúng ký hiệu sẽ luôn gây ra hiện tượng đó. Việc có lỗi hay không còn phụ thuộc cách ứng dụng dùng giá trị đọc, thứ tự các thao tác khác, commit/rollback và isolation level.

## 7. Đồ thị xung đột và thứ tự tuần tự hóa

Một cách nhìn mạnh hơn bảng ba loại xung đột là dựng **đồ thị ưu tiên** (*precedence graph*, còn gọi là *conflict graph*) từ toàn bộ lịch.

### 7.1. Cách dựng đồ thị

- Mỗi giao dịch là một **đỉnh**.
- Nếu có hai thao tác xung đột và thao tác của `Ti` đứng trước thao tác của `Tj`, vẽ **cạnh có hướng** `Ti → Tj`.
- Có thể có nhiều lý do tạo cạnh giữa cùng một cặp giao dịch, nhưng chỉ cần một cạnh có hướng là đủ để thể hiện ràng buộc thứ tự.
- Nếu đồ thị **không có chu trình**, lịch được gọi là **conflict-serializable** theo mô hình một phiên bản cổ điển; có thể sắp các giao dịch theo thứ tự tô pô để tạo lịch tuần tự tương đương về các cặp thao tác xung đột.
- Nếu đồ thị **có chu trình**, không tồn tại một thứ tự tuần tự nào giữ được **tất cả** quan hệ thứ tự xung đột của lịch đó; lịch không conflict-serializable.

### 7.2. Ví dụ không có chu trình

Xét lịch:

```text
S1 = r1(X), w1(X), c1, r2(X), w2(X), c2
```

Ta có:

- `w1(X) → r2(X)`: cạnh `T1 → T2` loại WR.
- `r1(X) → w2(X)`: cạnh `T1 → T2` loại RW.
- `w1(X) → w2(X)`: cạnh `T1 → T2` loại WW.

Đồ thị:

```text
  +----+      WR, RW, WW      +----+
  | T1 | ------------------> | T2 |
  +----+                     +----+
```

Chỉ có cạnh từ T1 sang T2, nên không có chu trình. Thứ tự tuần tự `T1` rồi `T2` phù hợp với lịch S1.

### 7.3. Ví dụ có chu trình: mỗi giao dịch đọc rồi sửa một hàng khác

Giả sử X, Y biểu diễn hai dòng dữ liệu hoặc hai điều kiện nghiệp vụ có liên hệ với nhau. Xét lịch:

```text
S2 = r1(X), r1(Y), r2(X), r2(Y), w1(X), w2(Y), c1, c2
```

Các cặp tạo cạnh đáng chú ý:

1. `r2(X) → w1(X)` tạo **`T2 → T1`** loại RW.
2. `r1(Y) → w2(Y)` tạo **`T1 → T2`** loại RW.

Đồ thị:

```text
                    r1(Y) -> w2(Y)
              +-------------------------+
              |                         v
            +----+                    +----+
            | T1 |                    | T2 |
            +----+                    +----+
              ^                         |
              +-------------------------+
                    r2(X) -> w1(X)
```

Có chu trình `T1 → T2 → T1`, nên lịch không conflict-serializable. Đáng chú ý, **T1 ghi X, T2 ghi Y**, không có WW trên cùng hàng. Hai quan hệ RW đã đủ tạo chu trình.

### 7.4. Liên hệ với write skew

Xét một hệ thống luôn cần ít nhất một bác sĩ trực. Có hai hàng:

| Bác sĩ | Đang trực |
| --- | --- |
| An | Có |
| Bình | Có |

T1 đọc cả hai hàng, thấy có 2 người trực rồi cho **An** nghỉ. T2 cũng đọc cả hai hàng, thấy có 2 người trực rồi cho **Bình** nghỉ. Nếu mỗi giao dịch dựa trên một ảnh chụp trước thay đổi của giao dịch còn lại, cả hai có thể commit vì mỗi giao dịch chỉ ghi một hàng khác nhau. Cuối cùng **không còn người trực**, vi phạm quy tắc nghiệp vụ.

Phụ thuộc:

- T1 đã đọc hàng Bình trước khi T2 cập nhật hàng Bình: `T1 → T2` (RW).
- T2 đã đọc hàng An trước khi T1 cập nhật hàng An: `T2 → T1` (RW).

Đó là dạng **write skew**. Nó minh họa vì sao chỉ kiểm tra xung đột WW trên **cùng một hàng** không đủ để bảo vệ bất biến **trải trên nhiều hàng**.

Trong PostgreSQL, tình huống như vậy có thể xuất hiện dưới `REPEATABLE READ` (được triển khai bằng snapshot isolation). `SERIALIZABLE` sử dụng thêm cơ chế phát hiện phụ thuộc nguy hiểm và có thể hủy một giao dịch với lỗi cần retry, để bảo đảm kết quả tương đương thực thi tuần tự cho các giao dịch được commit.

> **Giới hạn mô hình:** Đồ thị xung đột cổ điển ở trên xét các thao tác đọc/ghi trên một đối tượng X trong một lịch một phiên bản. Với MVCC, mỗi lần đọc gắn với **phiên bản cụ thể**, và việc phân tích tuần tự hóa cần xét quan hệ *read-from*, thứ tự phiên bản ghi và RW anti-dependency. Không nên suy rằng PostgreSQL sẽ trực tiếp dựng đồ thị từ văn bản SQL y hệt ví dụ hoặc hủy giao dịch hễ thấy một cặp RW.

## 8. Thực hành PostgreSQL bằng hai phiên độc lập

Các thí nghiệm này giúp quan sát cách xung đột được hệ quản trị xử lý. Chúng khác nhau về **thứ tự**, nên hãy hoàn tất một thí nghiệm trước khi làm thí nghiệm tiếp theo.

### 8.1. Chuẩn bị database và hai kết nối

Nếu máy đã có PostgreSQL, có thể dùng cơ sở dữ liệu thực hành tùy chọn. Nếu muốn tạo môi trường độc lập bằng Docker (có Docker Desktop hoặc Docker Engine đang chạy):

```powershell
docker run --name conflict-schedule-lab -e POSTGRES_USER=lab_user -e POSTGRES_PASSWORD=lab_password -e POSTGRES_DB=conflict_lab -p 127.0.0.1:55434:5432 -d postgres:16
```

Kiểm tra PostgreSQL sẵn sàng:

```powershell
docker exec conflict-schedule-lab pg_isready -U lab_user -d conflict_lab
```

Mở **Terminal A** và **Terminal B**, mỗi cửa sổ chạy riêng:

```powershell
docker exec -it conflict-schedule-lab psql -X -U lab_user -d conflict_lab
```

Trong mỗi phiên `psql`, có thể xác nhận đang dùng đúng database và hai kết nối thật sự khác nhau:

```sql
SELECT current_database(), pg_backend_pid();
SHOW default_transaction_isolation;
```

Tên database cần giống nhau, `pg_backend_pid()` cần khác nhau. Các thử nghiệm sau giả định mức mặc định là `READ COMMITTED`; nếu khác, hãy dùng `BEGIN ISOLATION LEVEL READ COMMITTED;` thay `BEGIN;`.

Trong **phiên A**, tạo dữ liệu:

```sql
DROP TABLE IF EXISTS public.conflict_accounts;

CREATE TABLE public.conflict_accounts (
    account_id INTEGER PRIMARY KEY,
    balance INTEGER NOT NULL CHECK (balance >= 0)
);

INSERT INTO public.conflict_accounts (account_id, balance)
VALUES (101, 1000), (202, 500);
```

Lệnh `DROP TABLE` chỉ dành cho database thực hành. Các phiên dùng cùng bảng `public.conflict_accounts`.

Để đặt lại số dư trước từng thử nghiệm, chỉ chạy **khi hai phiên đã commit hoặc rollback hết giao dịch đang mở**:

```sql
UPDATE public.conflict_accounts
SET balance = CASE account_id
    WHEN 101 THEN 1000
    WHEN 202 THEN 500
END
WHERE account_id IN (101, 202);
```

### 8.2. Thí nghiệm WR: phiên B đọc sau khi A ghi và commit

**Phiên A**:

```sql
BEGIN;

UPDATE public.conflict_accounts
SET balance = balance + 200
WHERE account_id = 101
RETURNING balance;
-- Kết quả ở A: 1200. Chưa COMMIT.
```

**Phiên B**, khi A vẫn chưa commit:

```sql
SELECT balance
FROM public.conflict_accounts
WHERE account_id = 101;
-- Dự kiến: 1000, vì không đọc thay đổi chưa commit.
```

Trở lại **phiên A**:

```sql
COMMIT;
```

Bây giờ **phiên B** chạy lại:

```sql
SELECT balance
FROM public.conflict_accounts
WHERE account_id = 101;
-- Dự kiến: 1200.
```

**Quan sát:** B đọc phiên bản cũ trong lúc A còn giao dịch; sau khi A commit, một câu `SELECT` mới đọc phiên bản `1200`. Quan hệ WR quan trọng ở lần đọc sau: T2 đã thấy giá trị do T1 ghi. Tình huống này cũng cho thấy **WR không mặc nhiên đồng nghĩa dirty read**.

### 8.3. Thí nghiệm RW: B thay đổi dữ liệu sau lần đọc đầu của A

Đặt lại dữ liệu về `1000 / 500`.

**Phiên A**:

```sql
BEGIN;

SELECT balance
FROM public.conflict_accounts
WHERE account_id = 101;
-- Kết quả: 1000.
```

**Phiên B**:

```sql
BEGIN;

UPDATE public.conflict_accounts
SET balance = balance - 100
WHERE account_id = 101;

COMMIT;
```

**Phiên A**, vẫn trong giao dịch cũ:

```sql
SELECT balance
FROM public.conflict_accounts
WHERE account_id = 101;
-- Ở READ COMMITTED: 900.

ROLLBACK;
```

**Quan sát:** `rA(X=1000)` xảy ra trước `wB(X=900)`. Hai lần đọc trong giao dịch A có kết quả khác nhau vì B commit giữa chúng. Đây là biểu hiện của RW và non-repeatable read ở `READ COMMITTED`.

A dùng `ROLLBACK` để kết thúc giao dịch đang mở; A không thực hiện thay đổi nào nên rollback **không đảo ngược** phần trừ `100` mà B đã commit.

### 8.4. Thí nghiệm WW: hai phiên cập nhật cùng một hàng

Đặt lại dữ liệu về `1000 / 500`.

**Phiên A**:

```sql
BEGIN;

UPDATE public.conflict_accounts
SET balance = balance + 200
WHERE account_id = 101
RETURNING balance;
-- A thấy 1200. Giữ giao dịch mở.
```

**Phiên B**:

```sql
BEGIN;

UPDATE public.conflict_accounts
SET balance = balance - 100
WHERE account_id = 101
RETURNING balance;
```

Lệnh `UPDATE` ở B **chờ** vì A đang giữ khóa cập nhật hàng 101. Trong khi B chờ, chuyển về **phiên A** và chạy:

```sql
COMMIT;
```

B được tiếp tục xử lý; với PostgreSQL `READ COMMITTED`, phép trừ `100` áp dụng vào giá trị hàng sau khi A commit, nên `RETURNING` ở B dự kiến trả `1100`. Kết thúc **phiên B**:

```sql
COMMIT;

SELECT balance
FROM public.conflict_accounts
WHERE account_id = 101;
-- Dự kiến: 1100.
```

**Quan sát:** có quan hệ WW, có chờ khóa, nhưng hai lần cập nhật số học đúng cách đều được bảo toàn. Không có mất cập nhật trong lịch này. Thí nghiệm được thiết kế để B **chờ**; nếu muốn giới hạn thời gian chờ khi thử ở máy riêng, có thể đặt `SET LOCAL lock_timeout = '10s';` sau `BEGIN` ở B. Khi timeout gây lỗi, cần `ROLLBACK;` ở B rồi làm lại theo trình tự.

Có thể quan sát tiến trình đang chờ khi B chưa được giải phóng. Trong **phiên A**, trước `COMMIT`, chạy:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid();
```

Nếu B đang đợi khóa, `wait_event_type` có thể là `Lock`; `blocking_pids` sẽ liên hệ đến PID của phiên A. Dữ liệu giám sát thay đổi theo thời điểm nên không nên dựa vào một giá trị PID cố định.

### 8.5. Thí nghiệm lost update do tự tính giá trị mới từ lần đọc cũ

Đặt lại dữ liệu về `1000 / 500`.

**Phiên A**:

```sql
BEGIN;
SELECT balance FROM public.conflict_accounts WHERE account_id = 101;
-- 1000, ứng dụng của A tính 1000 + 200 = 1200.
```

**Phiên B**:

```sql
BEGIN;
SELECT balance FROM public.conflict_accounts WHERE account_id = 101;
-- 1000, ứng dụng của B tính 1000 - 100 = 900.
```

**Phiên A**:

```sql
UPDATE public.conflict_accounts
SET balance = 1200
WHERE account_id = 101;

COMMIT;
```

**Phiên B**, dùng giá trị `900` đã tính từ lúc trước:

```sql
UPDATE public.conflict_accounts
SET balance = 900
WHERE account_id = 101;

COMMIT;
```

Kiểm tra số dư:

```sql
SELECT balance
FROM public.conflict_accounts
WHERE account_id = 101;
-- Kết quả: 900.
```

Cộng `200` và trừ `100` lẽ ra đưa `1000` thành `1100`. Giá trị `900` cho thấy kết quả của A bị ghi đè vì B sử dụng một **giá trị tuyệt đối tính từ lần đọc cũ**. Đây là ví dụ để phân biệt **đợi khóa WW** với việc giải quyết **stale read RW** ở tầng ứng dụng.

## 9. MVCC, locking và isolation thay đổi hành vi như thế nào?

Lý thuyết xung đột trả lời **những thao tác nào phụ thuộc thứ tự**. Cơ chế điều khiển tương tranh của DBMS trả lời **làm thế nào các thao tác được thực thi an toàn**.

### 9.1. Khóa độc quyền và chia sẻ

Trong các mô hình khóa kinh điển:

- **Shared lock (S)** cho phép nhiều bên đọc nhưng có thể ngăn ghi tương ứng.
- **Exclusive lock (X)** bảo vệ thao tác ghi và không tương thích với các khóa xung đột.

**Strict two-phase locking (strict 2PL)** giữ những khóa ghi đến khi giao dịch kết thúc, ngăn nhiều lịch gây lỗi và hỗ trợ phục hồi; biến thể và phạm vi khóa cụ thể tùy DBMS.

PostgreSQL dùng **MVCC** kết hợp nhiều loại khóa. `SELECT` thông thường ở `READ COMMITTED` không giữ khóa hàng loại trừ `UPDATE`, còn `SELECT ... FOR UPDATE` chủ động lấy khóa hàng để đồng bộ hóa việc kiểm tra rồi thay đổi. Không nên suy từ khái niệm shared lock trong sách rằng mọi `SELECT` của PostgreSQL đều chặn `UPDATE`.

### 9.2. Ảnh chụp MVCC và ba kiểu phụ thuộc

Trong một hệ quản trị nhiều phiên bản:

- **WR dependency** thường mô tả T2 **đọc đúng phiên bản** do T1 tạo và commit, dù thời điểm câu lệnh và ảnh chụp quyết định T2 có thể nhìn thấy nó.
- **WW dependency** thể hiện thứ tự các phiên bản do hai giao dịch ghi lên cùng đối tượng; các writer thường cần phối hợp hoặc phát hiện cập nhật xung đột.
- **RW anti-dependency** cho biết T1 đọc một phiên bản **trước phiên bản** do T2 tạo. Nó có thể tồn tại dù T1 và T2 không chờ khóa nhau.

Vì có nhiều phiên bản, ký hiệu `w1(X) → r2(X)` trong một lịch đơn giản không còn đủ để kết luận rằng T2 đọc giá trị của T1. Phải xác định **phiên bản dữ liệu được đọc** và **quy tắc hiển thị ảnh chụp**.

### 9.3. So sánh các mức cô lập PostgreSQL

| Isolation level | Hệ quả liên quan đến ba kiểu xung đột |
| --- | --- |
| `READ COMMITTED` | Mỗi câu lệnh thấy ảnh chụp dữ liệu đã commit tại lúc câu lệnh bắt đầu; không dirty read. Hai lần `SELECT` có thể thấy giá trị khác nhau; lệnh `UPDATE` cùng hàng được đồng bộ bằng khóa. |
| `REPEATABLE READ` | Dùng ảnh chụp nhất quán xuyên suốt giao dịch theo triển khai PostgreSQL; không non-repeatable read. Nếu cố cập nhật hàng đã bị giao dịch đồng thời sửa sau ảnh chụp, có thể gặp lỗi serialization; write skew trên các hàng khác nhau vẫn có thể xảy ra. |
| `SERIALIZABLE` | Tạo hành vi tương đương một thứ tự tuần tự cho các giao dịch đã commit. PostgreSQL dùng Serializable Snapshot Isolation (SSI) để phát hiện một số cấu trúc phụ thuộc nguy hiểm, có thể hủy giao dịch và yêu cầu retry toàn bộ. |

Ví dụ đặt mức cô lập ngay khi bắt đầu giao dịch:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
-- Đọc, kiểm tra điều kiện và cập nhật dữ liệu.
COMMIT;
```

Cần bắt lỗi SQLSTATE `40001` và **thử lại toàn bộ giao dịch từ đầu**, bởi thông tin đã đọc ở lần thử cũ có thể không còn hợp lệ. Với lỗi deadlock SQLSTATE `40P01`, giao dịch bị hủy cũng cần được cân nhắc retry an toàn. Không nên retry bằng cách chỉ chạy lại đúng câu `UPDATE` cuối mà bỏ qua kiểm tra điều kiện nghiệp vụ trước đó.

### 9.4. Phantom và xung đột theo điều kiện truy vấn

Một câu lệnh như:

```sql
SELECT COUNT(*)
FROM reservations
WHERE room_id = 7
  AND status = 'ACTIVE';
```

đọc **tập hàng thỏa điều kiện**, không chỉ một hàng cố định. Nếu giao dịch khác chèn một reservation mới thỏa điều kiện, truy vấn sau có thể trả số lượng lớn hơn. Đây là một ví dụ về **phantom read** ở những mức cô lập cho phép.

Nếu chỉ biểu diễn xung đột bằng `r1(X)` và `w2(X)` trên các hàng đã tồn tại, ta có thể bỏ lỡ việc một `INSERT` mới làm thay đổi kết quả của truy vấn theo điều kiện. Vì vậy, các cơ chế cô lập tuần tự hóa cần xét cả các quan hệ theo **phạm vi/predicate**, ngoài từng hàng riêng lẻ.

## 10. Chọn kỹ thuật xử lý theo loại xung đột

Không phải mọi hệ thống đều cần `SERIALIZABLE` cho tất cả câu lệnh. Giải pháp phù hợp phụ thuộc bất biến nghiệp vụ, tần suất tranh chấp, chi phí chờ và khả năng retry.

| Tình huống | Kỹ thuật thường phù hợp | Điều cần chú ý |
| --- | --- | --- |
| Hiển thị số dư đã commit | `SELECT` thông thường | Số dư có thể thay đổi sau khi hiển thị; tránh dùng giá trị hiển thị làm điều kiện quyết định về sau |
| Trừ số dư nếu đủ tiền | `UPDATE ... SET balance = balance - :amount WHERE balance >= :amount` | Kiểm tra chính xác số hàng cập nhật; rollback nếu không đủ tiền |
| Kiểm tra nhiều điều kiện rồi cập nhật một vài hàng | `SELECT ... FOR UPDATE` trên tập hàng cần bảo vệ | Chọn tập và thứ tự khóa hợp lý; tránh giữ khóa quá lâu |
| Người dùng chỉnh sửa một bản ghi từ biểu mẫu đã đọc từ lâu | **Optimistic locking** bằng cột `version` | `UPDATE ... WHERE version = :expectedVersion`, kiểm tra số hàng cập nhật |
| Hai giao dịch sửa các hàng khác nhau nhưng cùng phụ thuộc một bất biến | Ràng buộc liên quan, khóa phù hợp hoặc `SERIALIZABLE` | Khóa từng hàng bị ghi có thể không chặn write skew; có thể cần retry |
| Nhiều tài khoản cần khóa để chuyển tiền | Lấy khóa theo thứ tự mã tài khoản ổn định | Giảm nguy cơ deadlock; kiểm tra đủ tài khoản và đủ số dư |
| Công việc có mức tranh chấp cao | Giảm thời gian giao dịch, giảm phạm vi khóa, chọn thiết kế phân vùng phù hợp | Phải giữ nguyên tính đúng đắn nghiệp vụ |

### 10.1. Ví dụ cập nhật có điều kiện để tránh quyết định từ số dư cũ

```sql
BEGIN;

UPDATE public.conflict_accounts
SET balance = balance - 300
WHERE account_id = 101
  AND balance >= 300
RETURNING account_id, balance;

-- Chỉ tiếp tục khi UPDATE đúng 1 hàng.
UPDATE public.conflict_accounts
SET balance = balance + 300
WHERE account_id = 202
RETURNING account_id, balance;

-- Chỉ COMMIT nếu cả hai thao tác hợp lệ và tài khoản đích tồn tại.
COMMIT;
```

Đoạn này minh họa **đường đi thành công**. Nếu lệnh đầu cập nhật 0 hàng hoặc lệnh sau không tìm thấy tài khoản đích, ứng dụng phải `ROLLBACK`, không được `COMMIT`. Nếu không, một giao dịch nguyên tử vẫn có thể thực hiện **logic nghiệp vụ sai**.

### 10.2. Optimistic locking bằng cột phiên bản

Thêm cột `version` vào mô hình ứng dụng (đây là ví dụ cấu trúc, không phải lệnh bắt buộc cho các bài thử trước):

```sql
ALTER TABLE public.conflict_accounts
ADD COLUMN version INTEGER NOT NULL DEFAULT 0;
```

Ứng dụng đọc `balance` và `version` cùng lúc, ví dụ nhận được `balance=1000, version=0`. Khi cập nhật:

```sql
UPDATE public.conflict_accounts
SET balance = 1200,
    version = version + 1
WHERE account_id = 101
  AND version = 0
RETURNING version;
```

Nếu giao dịch khác đã cập nhật hàng và tăng phiên bản, câu lệnh trên tác động **0 hàng**. Ứng dụng phải nhận diện xung đột, đọc lại dữ liệu, tính toán và thực hiện hành động phù hợp, thay vì ghi đè vô điều kiện. Cách này hữu ích cho các biểu mẫu chỉnh sửa, cập nhật trạng thái hoặc luồng nghiệp vụ mà yêu cầu chờ khóa dài không phù hợp.

## 11. Những hiểu lầm thường gặp

**“Cứ thấy hai giao dịch truy cập cùng hàng là có xung đột.”**  
Không hẳn. Hai thao tác **chỉ đọc** cùng hàng không xung đột theo mô hình đọc/ghi cơ bản. Phải có ít nhất một thao tác ghi và thuộc hai giao dịch khác nhau.

**“Xung đột đồng nghĩa với deadlock hoặc dữ liệu sai.”**  
Không. Xung đột là quan hệ thứ tự thao tác. Deadlock là chu trình **chờ tài nguyên**, còn lỗi dữ liệu phụ thuộc logic nghiệp vụ và lịch thực thi. Một lịch có nhiều cạnh xung đột vẫn có thể conflict-serializable.

**“Nếu không thấy câu lệnh chờ thì chắc chắn không xung đột.”**  
Không. `SELECT` thông thường trong PostgreSQL có thể đọc phiên bản cũ trong khi giao dịch khác đang ghi. Quan hệ RW anti-dependency có thể tồn tại mà không có chờ khóa trực tiếp.

**“Chỉ cần tránh WW là hết lỗi đồng thời.”**  
Không. Write skew có thể xuất hiện khi mỗi giao dịch **ghi một hàng khác nhau** nhưng cùng đọc những dữ liệu liên quan đến một bất biến. Hai cạnh RW có thể tạo chu trình ngay cả khi không có WW trên cùng hàng.

**“Dùng transaction có nghĩa mọi giao dịch tự động chạy như tuần tự.”**  
Không. `BEGIN` và `COMMIT` xác định ranh giới giao dịch; mức cô lập và kỹ thuật đồng bộ hóa quyết định những hiện tượng đồng thời nào được phép. Atomicity không tự bảo đảm mọi lịch đều serializable.

**“Đọc hai lần khác nhau chứng minh có dirty read.”**  
Không. Hai lần đọc tại `READ COMMITTED` có thể khác nhau vì giao dịch khác đã **commit** thay đổi giữa hai câu lệnh. Đó là non-repeatable read, khác với dirty read là đọc dữ liệu **chưa commit**.

**“Một cạnh RW trong đồ thị chắc chắn khiến PostgreSQL báo lỗi serialization.”**  
Không. PostgreSQL `SERIALIZABLE` đánh giá cấu trúc phụ thuộc của nhiều thao tác/giao dịch và các điều kiện thực thi. Một cặp RW riêng lẻ không đủ để kết luận giao dịch nào phải hủy.

## 12. Bài tập phân tích lịch thực thi

Các bài dưới đây dùng mô hình lịch một phiên bản. Hãy tự đánh dấu cặp xung đột, vẽ cạnh phụ thuộc và xác định có chu trình hay không.

### Bài 1. Ba giao dịch nhưng chỉ một hướng

```text
S = r1(X), w1(X), r2(X), w2(Y), r3(Y), c1, c2, c3
```

Các cặp quan trọng:

- `w1(X) → r2(X)`: WR, cạnh `T1 → T2`.
- `w2(Y) → r3(Y)`: WR, cạnh `T2 → T3`.

Đồ thị `T1 → T2 → T3` không có chu trình; lịch **conflict-serializable** theo thứ tự `T1, T2, T3`.

### Bài 2. Hai cạnh RW tạo chu trình

```text
S = r1(X), r2(Y), w1(Y), w2(X), c1, c2
```

- `r1(X) → w2(X)`: RW, `T1 → T2`.
- `r2(Y) → w1(Y)`: RW, `T2 → T1`.

Đồ thị có chu trình, nên lịch **không conflict-serializable**. Không hề có hai lần ghi cùng một hàng, nhưng vẫn có phụ thuộc hai chiều.

### Bài 3. Các thao tác không xung đột

```text
S = r1(X), r2(X), w1(Y), r2(Z), c1, c2
```

Hai lần đọc `r1(X)` và `r2(X)` không xung đột. `w1(Y)` và `r2(Z)` cũng không xung đột vì khác đối tượng. Nếu các đối tượng X, Y, Z độc lập như giả định, không có cạnh xung đột giữa hai giao dịch. Điều này nhắc rằng **hai giao dịch chạy xen kẽ không tự động tạo quan hệ phụ thuộc**.

### Bài 4. Có WW nhưng không có chu trình

```text
S = w1(X), w2(X), r2(Y), c1, c2
```

Có `w1(X) → w2(X)`: WW, `T1 → T2`. Chỉ với cạnh này, đồ thị không có chu trình. Lịch conflict-serializable theo thứ tự `T1 → T2` nếu xét đúng các thao tác đã cho. Tuy nhiên, một lịch lý thuyết có WW chưa nói rõ DBMS có cho phép ghi bẩn hay không, hoặc trạng thái phục hồi khi một giao dịch abort; đó là vấn đề khác với điều kiện **conflict-serializable**.

### Bài 5. Phân loại tình huống thực tiễn

Với từng sự kiện, hãy nêu loại quan hệ chính và nguy cơ có thể phát sinh:

| Tình huống | Phân tích |
| --- | --- |
| T1 đọc tồn kho `10`; T2 giảm còn `4`; T1 dùng `10` để nhận đơn hàng mới | RW, nguy cơ quyết định dựa trên số liệu cũ |
| T1 cập nhật giá rồi commit; T2 đọc giá mới | WR, phụ thuộc hợp lệ vào bản ghi đã commit |
| T1 ghi số dư chưa commit; T2 được phép đọc ngay số dư này | WR kèm **dirty read** trong hệ thống cho phép đọc bẩn |
| Hai phiên cùng cập nhật hàng số dư | WW; cần phối hợp, có thể phải chờ khóa |
| T1 và T2 cùng đọc toàn bộ lịch trực, mỗi bên tắt một người trực khác nhau | Các RW anti-dependency hai chiều có thể dẫn đến **write skew** |

## 13. Phương pháp đọc một lịch thực thi bất kỳ

Khi gặp một lịch mới, có thể phân tích theo trình tự:

1. **Liệt kê các giao dịch** và đánh dấu từng thao tác đọc/ghi, đối tượng X/Y được truy cập, cùng commit hoặc rollback.
2. **Lọc các cặp xung đột**: hai giao dịch khác nhau, cùng đối tượng và có ít nhất một thao tác ghi.
3. **Xác định chiều theo thứ tự**: thao tác nào đi trước tạo cạnh từ giao dịch của nó tới giao dịch thao tác sau.
4. **Gắn nhãn RW, WR hoặc WW** cho từng cạnh để thấy bản chất phụ thuộc.
5. **Vẽ đồ thị** và kiểm tra chu trình nếu bài toán yêu cầu conflict-serializability.
6. **Đối chiếu cơ chế DBMS**: có MVCC không, từng lần đọc thấy phiên bản nào, mức cô lập là gì, khóa nào được giữ và có lỗi retry không.
7. **Đối chiếu bất biến nghiệp vụ**: việc lịch có vẻ hợp lệ về thao tác chưa đủ; kết quả có bảo toàn tiền, tồn kho, chỗ đặt và các điều kiện nghiệp vụ hay không?

Tóm lại, xung đột **RW** cho biết một giao dịch đã đọc trước thay đổi của giao dịch khác; **WR** cho biết thao tác đọc đứng sau một lần ghi; **WW** cho biết có hai lần ghi cạnh tranh thứ tự trên cùng dữ liệu. Ba loại quan hệ này là những viên gạch để dựng đồ thị phụ thuộc, phân biệt lịch tương đương tuần tự, giải thích hiện tượng tương tranh và chọn cách bảo vệ dữ liệu thích hợp trong hệ quản trị thực tế.
