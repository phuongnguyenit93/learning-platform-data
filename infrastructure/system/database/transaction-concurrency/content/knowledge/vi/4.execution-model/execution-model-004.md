# Quan hệ phụ thuộc giữa các giao dịch trên cùng dữ liệu

## 1. Vì sao cần nhìn vào quan hệ giữa các giao dịch?

Giả sử hệ thống ngân hàng có hai giao dịch diễn ra gần như đồng thời:

- **T1:** rút 300.000 đồng từ tài khoản A.
- **T2:** chuyển 200.000 đồng từ tài khoản A sang tài khoản B.

Cả hai đều cần truy cập số dư A. Nếu T1 và T2 chạy tuần tự, mỗi giao dịch có thể sử dụng kết quả hợp lệ của giao dịch trước. Nhưng nếu chúng cùng đọc một giá trị cũ, tính số dư mới riêng rẽ rồi ghi lại, một cập nhật có thể làm mất cập nhật kia.

Vấn đề không chỉ là “có hai giao dịch đồng thời”, mà là **chúng phụ thuộc nhau ở những điểm nào, trên dữ liệu nào và theo thứ tự nào**.

Trong mô hình thực thi giao dịch, **quan hệ phụ thuộc (dependency)** diễn tả sự ràng buộc về thứ tự hoặc khả năng quan sát giữa các thao tác thuộc những giao dịch khác nhau. Các quan hệ này là cơ sở để phân tích:

- Một lịch thực thi xen kẽ có tương đương với thực thi tuần tự không?
- Giao dịch nào đã đọc giá trị do giao dịch nào tạo ra?
- Giao dịch nào đã ghi đè phiên bản của giao dịch nào?
- Một quyết định đã đọc dữ liệu cũ có còn đúng sau khi giao dịch khác ghi dữ liệu mới?
- Cơ chế cô lập phải chặn, trì hoãn, hủy hay thử lại giao dịch nào?

Phân tích phụ thuộc giúp nhận diện **lost update**, **dirty read**, **write skew**, các vi phạm ràng buộc trên tập dòng và những lịch thực thi không tuần tự hóa được.

## 2. Những khái niệm cần có trước khi lập đồ thị

### 2.1. Giao dịch và thao tác

Ký hiệu **T1, T2, T3** là các giao dịch. Với một đối tượng dữ liệu **X**, dùng ký hiệu:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `r1(X)` | T1 đọc X. |
| `w1(X)` | T1 ghi X. |
| `r2(X)` | T2 đọc X. |
| `w2(X)` | T2 ghi X. |
| `c1` | T1 commit. |
| `a1` | T1 abort/rollback. |

Một giao dịch có thể gồm nhiều thao tác và chạm vào nhiều đối tượng. Ví dụ:

```text
T1: r1(A) -> w1(A) -> r1(B) -> w1(B) -> c1
T2: r2(A) -> w2(A) -> c2
```

Ở đây hai giao dịch chia sẻ A, còn chỉ T1 truy cập B.

**Đối tượng dữ liệu** có thể được trừu tượng hóa là một dòng, một khóa logic, một bản ghi hay một tập kết quả tùy bài toán. Trong DBMS thực, phạm vi xung đột còn phụ thuộc chỉ mục, điều kiện truy vấn, khóa vùng, khóa predicate và các ràng buộc dữ liệu.

### 2.2. Lịch thực thi (schedule/history)

**Lịch thực thi** là thứ tự các thao tác được hệ thống thực hiện hoặc quan sát, vẫn giữ thứ tự nội bộ của từng giao dịch.

Ví dụ:

```text
T1: r1(X) -------- w1(X) -------- c1
T2: ------ r2(X) -------- w2(X) ----- c2

Lịch xen kẽ:
r1(X), r2(X), w1(X), w2(X), c1, c2
```

Hai giao dịch có thể xen kẽ nhưng vẫn hoàn tất chính xác. Điều cần xem là các thao tác của chúng có **xung đột** và tạo thứ tự phụ thuộc nào.

### 2.3. Lịch tuần tự và lịch tuần tự hóa được

- **Tuần tự (serial):** toàn bộ T1 chạy xong rồi T2, hoặc ngược lại; không có bước xen kẽ.
- **Xen kẽ (interleaved):** các bước của nhiều giao dịch đan xen.
- **Tuần tự hóa được (serializable):** hiệu ứng quan sát được của lịch đã commit tương đương một thứ tự tuần tự hợp lệ theo mô hình tuần tự hóa đang xét.

Một lịch tuần tự hóa được **không cần thực thi hoàn toàn tuần tự**. Chỉ cần các quan hệ phụ thuộc có thể sắp xếp thành thứ tự nhất quán. Đây là cơ sở để DBMS duy trì tính đúng đắn mà vẫn xử lý nhiều yêu cầu đồng thời.

## 3. Khi nào hai thao tác xung đột?

Trong mô hình lịch đơn phiên bản (*single-version*), hai thao tác từ **hai giao dịch khác nhau** được xem là xung đột khi:

1. Chúng truy cập **cùng đối tượng dữ liệu**.
2. Có ít nhất một thao tác là **ghi**.

| Cặp thao tác | Xung đột? | Lý do |
| --- | --- | --- |
| `r1(X)` và `r2(X)` | Không | Hai lần đọc không thay đổi X. |
| `r1(X)` và `w2(X)` | Có | Phép ghi của T2 có thể thay đổi giá trị T1 đọc. |
| `w1(X)` và `r2(X)` | Có | Phép đọc của T2 phụ thuộc việc T1 ghi X khi nào. |
| `w1(X)` và `w2(X)` | Có | Thứ tự hai phép ghi quyết định giá trị/phiên bản sau cùng. |
| `w1(X)` và `w2(Y)`, X khác Y | Không theo mô hình đơn giản | Hai thao tác trên dữ liệu độc lập; vẫn phải xét bất biến chung hoặc ràng buộc trên tập dòng. |

Không nên đồng nhất “cùng bảng” với “cùng dữ liệu”: hai giao dịch cập nhật hai dòng độc lập trong cùng bảng có thể không xung đột trực tiếp. Ngược lại, hai giao dịch cập nhật hai dòng **khác nhau** vẫn có thể ảnh hưởng đến cùng một bất biến nghiệp vụ, chẳng hạn yêu cầu luôn có ít nhất một bác sĩ trực.

## 4. Ba loại quan hệ phụ thuộc chính

Khi nói về đồ thị phụ thuộc giao dịch, có ba loại cạnh quan trọng: **write–read (WR)**, **write–write (WW)** và **read–write (RW)**. Tên gọi chỉ **thứ tự của thao tác liên quan**, không phải mức cô lập.

### 4.1. Write–read (WR): giao dịch sau đọc kết quả ghi của giao dịch trước

**T1 → T2** theo quan hệ WR khi T2 đọc một phiên bản dữ liệu do T1 ghi.

```text
T1: w1(X = 120) ----------- c1
T2: ---------------------------- r2(X) [đọc 120] --- c2

WR: T1 -> T2
```

T2 phụ thuộc vào kết quả do T1 tạo ra. Nếu T1 đã commit trước khi T2 đọc, đây thường là kiểu phụ thuộc bình thường: người dùng sau thấy bản ghi đã được cập nhật.

Nhưng nếu T2 đọc dữ liệu của T1 **khi T1 chưa commit**, đó là **dirty read**:

```text
T1: w1(X = 120) ---------------- a1
T2: --------------- r2(X = 120) ----- c2
```

Nếu T1 rollback, T2 đã dùng giá trị không bao giờ được chốt. Tùy thứ tự commit, lịch này còn có thể không có khả năng phục hồi an toàn (*non-recoverable*), vì T2 đã commit dựa trên kết quả của giao dịch bị hủy.

**Lưu ý:** không phải cứ `w1(X)` đứng trước `r2(X)` là T2 chắc chắn đọc phiên bản của T1. Trong hệ MVCC, T2 có thể đọc một snapshot cũ. Để xác định WR thực sự, phải biết **T2 đọc phiên bản nào**.

### 4.2. Write–write (WW): hai giao dịch cùng ghi một đối tượng

**T1 → T2** theo WW khi phiên bản T2 ghi đến sau phiên bản T1 ghi trong thứ tự các phiên bản của cùng dữ liệu.

```text
T1: w1(X = 110) --- c1
T2: ----------------- w2(X = 130) --- c2

WW: T1 -> T2
```

Vì cả hai đều ghi X, thứ tự cập nhật quan trọng. Nếu hai phép ghi được thực hiện theo thứ tự ngược lại, kết quả có thể khác.

Ví dụ cả hai câu lệnh đều ghi một giá trị đã tính sẵn ở ứng dụng:

```sql
-- T1, sau khi từng đọc 100:
UPDATE counters SET value = 110 WHERE id = 1;

-- T2, cũng từng đọc 100:
UPDATE counters SET value = 120 WHERE id = 1;
```

Nếu T2 ghi cuối, X bằng 120; kết quả cộng 10 của T1 đã không được giữ lại. Tuy nhiên, **một cạnh WW đơn lẻ chưa đủ kết luận có lost update**. Cần xét các lần đọc trước đó và toàn bộ lịch.

Các DBMS thường điều phối xung đột ghi qua khóa hoặc phát hiện conflict. MVCC không đồng nghĩa hai transaction có thể đồng thời commit mọi phép ghi lên cùng một bản ghi mà không xử lý xung đột.

### 4.3. Read–write (RW): giao dịch đã đọc một phiên bản bị giao dịch khác thay thế

**T1 → T2** theo RW, còn gọi là **anti-dependency**, khi T1 đọc phiên bản cũ của X và T2 tạo phiên bản mới hơn của X trong thứ tự phiên bản liên quan.

```text
Giá trị đã commit ban đầu: X = 100

T1: r1(X = 100) ----------------------- c1
T2: --------------- w2(X = 150) -- c2

RW: T1 -> T2
```

Ý nghĩa: nếu muốn T1 đã đọc X cũ còn T2 tạo X mới, quan sát của T1 đặt nó trước T2 trong thứ tự tuần tự tương đương. RW chỉ ra một khả năng **quyết định dựa trên dữ liệu cũ**.

Ví dụ T1 đọc số ghế trống để quyết định có nhận đặt vé; T2 bán ghế rồi commit trước khi T1 lưu quyết định. Nếu T1 vẫn dùng kết quả đọc cũ, điều kiện ban đầu có thể không còn đúng.

Trong lịch đơn phiên bản, ta thường nhận ra RW từ `r1(X)` xảy ra trước `w2(X)`. Trong MVCC, anti-dependency có thể tồn tại dựa vào **phiên bản T1 đã đọc** ngay cả khi thời gian vật lý của các thao tác không đủ để suy luận thứ tự. Vì vậy phải phân biệt trật tự các thao tác với quan hệ phiên bản.

### 4.4. Bảng ghi nhớ ba loại cạnh

| Loại | Hình thức | Cách hiểu | Ví dụ nghiệp vụ |
| --- | --- | --- | --- |
| **WR** | `w1(X) -> r2(X)` | T2 đọc giá trị T1 đã tạo | Đọc số dư sau khi giao dịch trước cộng tiền |
| **WW** | `w1(X) -> w2(X)` | Hai transaction cùng ghi X theo một thứ tự | Hai yêu cầu cập nhật cùng hồ sơ |
| **RW** | `r1(X) -> w2(X)` | T1 dựa trên phiên bản trước khi T2 thay đổi X | T1 xác nhận còn hàng, T2 bán hết hàng |

Đây là **các cạnh định hướng**, không phải các cặp thao tác đối xứng. Đổi chiều mũi tên có thể thay đổi hoàn toàn kết luận về thứ tự tuần tự.

## 5. Ví dụ có đủ ba quan hệ phụ thuộc

Ban đầu X = 100; T1 và T2 mỗi giao dịch muốn cộng 10 vào X.

```text
Thời gian ->
T1: r1(X=100) -------- w1(X=110) -------- c1
T2: -------- r2(X=100) -------- w2(X=110) ------- c2
```

Nếu cả hai đọc 100, cùng tính 110 rồi ghi 110, kết quả cuối cùng là **110** thay vì **120**.

Các quan hệ trong lịch đơn phiên bản:

1. `r1(X)` trước `w2(X)` tạo cạnh **RW: T1 → T2**.
2. `r2(X)` trước `w1(X)` tạo cạnh **RW: T2 → T1**.
3. `w1(X)` trước `w2(X)` tạo cạnh **WW: T1 → T2**.

Đồ thị có hai chiều:

```text
        RW (T1 đọc trước T2 ghi)
   +----------------------------+
   |                            v
  T1 --------------------------> T2
   ^              WW             |
   |                             |
   +-----------------------------+
          RW (T2 đọc trước T1 ghi)
```

Hai cạnh RW đã tạo **chu trình T1 → T2 → T1**. Không thể chọn một thứ tự tuần tự vừa đặt T1 trước T2 vừa đặt T2 trước T1. Đây là dấu hiệu lịch không conflict-serializable và là cách hiểu hình thức của **lost update** trong ví dụ này.

Nếu thay bằng câu SQL cộng nguyên tử:

```sql
UPDATE counters
SET value = value + 10
WHERE id = 1;
```

thì hai phép ghi cạnh tranh trên cùng dòng được DBMS điều phối trong ngữ cảnh engine giao dịch; cả hai lần tăng có thể cùng được áp dụng để kết quả là 120, hoặc một giao dịch phải retry theo mức cô lập. Lúc đó không còn logic ứng dụng dùng cùng một giá trị cũ để ghi đè.

## 6. Đồ thị phụ thuộc và thứ tự tuần tự hóa

### 6.1. Tạo đồ thị như thế nào?

Một **đồ thị phụ thuộc** gồm:

- **Đỉnh:** mỗi giao dịch T1, T2, T3...
- **Cạnh có hướng T1 → T2:** tồn tại một quan hệ xung đột/phiên bản yêu cầu T1 đứng trước T2 trong thứ tự tuần tự tương đương.

Trong mô hình đơn phiên bản, đồ thị tiền nhiệm (*precedence graph*, hay *serialization graph* theo cách dạy cơ bản) được lập từ các cặp thao tác xung đột cùng dữ liệu. Nếu thao tác của T1 xuất hiện trước thao tác xung đột tương ứng của T2, thêm cạnh T1 → T2.

Ví dụ:

```text
T1: w1(A) ------- w1(B) ---------------- c1
T2: ------- r2(A) --------- w2(C) ------- c2
T3: ---------------- r3(B) -------- w3(C) ---- c3
```

Cạnh quan trọng:

- **T1 → T2** vì T2 đọc A sau khi T1 ghi A.
- **T1 → T3** vì T3 đọc B sau khi T1 ghi B.
- **T2 → T3** nếu T2 ghi C trước khi T3 ghi C.

Khi đó đồ thị:

```text
T1 ----> T2 ----> T3
  \-------------->/
```

Đồ thị **không có chu trình**. Có thể xếp thứ tự tuần tự tương đương là **T1, T2, T3**, dù trên thực tế các bước đã xen kẽ.

Nếu ngược lại xuất hiện cạnh **T3 → T1**, ta có chu trình T1 → T2 → T3 → T1. Không tồn tại một thứ tự tuần tự thỏa tất cả cạnh trong mô hình đó.

### 6.2. Tiêu chuẩn conflict-serializability

Với lịch đơn phiên bản được mô hình hóa bằng các xung đột đọc/ghi trên đối tượng xác định:

> **Một lịch conflict-serializable khi và chỉ khi đồ thị tiền nhiệm của nó không có chu trình.**

Vì thế, kiểm tra chu trình là cách phổ biến để chứng minh lịch có tương đương xung đột với một lịch tuần tự không.

Điều kiện này được dùng trong **mô hình conflict-serializability**. Một lịch không conflict-serializable đôi khi vẫn *view-serializable*; trong hệ MVCC cần xét lịch theo **phiên bản thực tế**, đọc-từ và thứ tự phiên bản. Không được lấy thứ tự thời gian các câu SQL rồi áp dụng máy móc quy tắc đơn phiên bản cho mọi engine MVCC.

### 6.3. Cách đọc chu trình cho đúng

Một chu trình cho thấy các giao dịch buộc phải đứng trước nhau theo các quan hệ phụ thuộc không thể cùng thỏa mãn. Nó không nhất thiết có nghĩa **một giao dịch phải chờ một giao dịch khác về mặt khóa**.

Cụ thể:

- **Chu trình trong đồ thị phụ thuộc:** dấu hiệu lịch không tuần tự hóa được theo mô hình đang xét.
- **Deadlock trong đồ thị chờ khóa:** các giao dịch đang chờ tài nguyên nhau thành vòng nên không thể tiến triển nếu không phá vòng.

Hai loại đồ thị liên quan đến concurrency nhưng có đỉnh/cạnh mang ý nghĩa khác nhau. **Serializable** có thể được bảo đảm bằng phát hiện xung đột và hủy giao dịch, không nhất thiết chỉ bằng chờ khóa.

## 7. Những bất thường nhìn từ quan hệ phụ thuộc

### 7.1. Dirty read: phụ thuộc vào dữ liệu chưa chốt

```text
T1: w1(price=90) --------------------- a1
T2: ---------------- r2(price=90) -------- c2
```

T2 có **WR T1 → T2**, nhưng phiên bản nguồn của T1 chưa commit và cuối cùng bị rollback. Nếu T2 đã commit, kết quả của nó có thể phụ thuộc vào dữ liệu không hợp lệ.

Thông thường, `READ COMMITTED` và các mức mạnh hơn của DBMS quan hệ ngăn dirty read. Tuy nhiên tên mức cô lập và cách engine hiện thực cần được hiểu theo từng hệ.

### 7.2. Non-repeatable read: cùng một giao dịch nhìn thấy phiên bản khác

```text
T1: r1(X=10) ----------------------- r1(X=15) --- c1
T2: ----------- w2(X=15) --- c2
```

T1 đọc X hai lần và thấy hai giá trị. Trong mô hình lịch đơn phiên bản có RW **T1 → T2** từ lần đọc đầu và WR **T2 → T1** từ lần đọc sau; hai chiều này thể hiện một chu trình.

Nếu T1 được cấp snapshot ổn định và đọc phiên bản X=10 cả hai lần, quan sát sẽ khác. Đó là lý do phải biết mức cô lập và cơ chế snapshot trước khi dự đoán kết quả.

### 7.3. Lost update: hai giao dịch sửa cùng đối tượng dựa trên giá trị cũ

```text
Ban đầu: stock = 10
T1: đọc 10; tính 10 - 3 = 7
T2: đọc 10; tính 10 - 4 = 6
T1: ghi 7; commit
T2: ghi 6; commit
```

Kết quả cuối là 6, trong khi nếu hai phép trừ hợp lệ đều được áp dụng tuần tự, tồn kho phải là 3. Các cạnh RW hai chiều xuất hiện do cả hai giao dịch cùng đọc phiên bản cũ rồi ghi.

Cách phòng tránh thường gặp: cập nhật có điều kiện trong một câu SQL, `SELECT ... FOR UPDATE` theo DBMS, optimistic locking theo cột version hoặc mức cô lập phù hợp.

### 7.4. Write skew: cạnh RW giữa những giao dịch ghi **khác dòng**

Giả sử bệnh viện yêu cầu **ít nhất một trong hai bác sĩ A và B luôn trực**. Ban đầu cả A và B đang trực:

```text
T1 đọc: A=true, B=true     -> quyết định cho A nghỉ
T2 đọc: A=true, B=true     -> quyết định cho B nghỉ

T1 ghi A=false
T2 ghi B=false

T1 commit
T2 commit

Kết quả: A=false, B=false
```

Các cạnh phụ thuộc:

- T1 đã đọc B=true trước khi T2 ghi B=false: **RW T1 → T2**.
- T2 đã đọc A=true trước khi T1 ghi A=false: **RW T2 → T1**.

Không có xung đột WW trực tiếp, vì T1 chỉ ghi A còn T2 chỉ ghi B. Nhưng đồ thị có chu trình:

```text
  T1 ---- RW ----> T2
   ^               |
   |               |
   +----- RW ------+
```

Đây là ví dụ đặc trưng cho **write skew**: một số mô hình snapshot isolation cho phép cả hai giao dịch commit vì chúng không cùng ghi một dòng, dù bất biến tổng thể bị phá vỡ.

Khắc phục có thể là dùng `SERIALIZABLE` với retry, khóa một tài nguyên chung, hoặc thiết kế lại cách lưu bất biến để DBMS kiểm soát bằng ràng buộc/ghi có điều kiện. Chỉ thêm `BEGIN` và `COMMIT` mà không thay cơ chế xung đột có thể không giải quyết được.

### 7.5. Phantom: phụ thuộc trên **tập dòng thỏa điều kiện**

T1 chạy:

```sql
SELECT COUNT(*)
FROM bookings
WHERE room_id = 7
  AND state = 'CONFIRMED';
```

Sau đó T2 chèn một booking mới cùng `room_id` và `state` rồi commit. Khi T1 đếm lại, số lượng có thể tăng lên.

Về logic, T1 đã đọc **tập dữ liệu đáp ứng predicate**, trong khi T2 tạo dòng mới thuộc tập đó. Quan hệ phụ thuộc không thể chỉ diễn đạt bằng “cùng ID dòng đã có từ trước”. Các cách triển khai serializable hoặc khóa predicate/range cần xét cả tập kết quả có khả năng xuất hiện hay biến mất.

Một hệ dựa hoàn toàn vào row lock cho các dòng T1 hiện thấy có thể không bảo vệ điều kiện “không có dòng nào thỏa điều kiện” trước thao tác chèn mới, tùy kiểu khóa/engine.

## 8. Quan hệ phụ thuộc trong MVCC

**Multi-Version Concurrency Control (MVCC)** quản lý nhiều phiên bản logic của một bản ghi. Thay vì đọc một vị trí dữ liệu có giá trị duy nhất ở mọi thời điểm, giao dịch đọc phiên bản phù hợp với snapshot của mình.

Hình dung:

```text
X^0 = 100   (phiên bản đã commit)
   |
   +-- T2 tạo X^2 = 130 và commit
   |
   +-- T1 vẫn đọc X^0 = 100 vì snapshot của T1 cũ hơn
```

Phép ghi của T2 có thể đã commit trước lúc T1 **về thời gian thực** đọc X. Nhưng nếu snapshot của T1 không bao gồm T2, T1 vẫn được thấy phiên bản cũ.

Vì thế, khi phân tích giao dịch MVCC, cần theo dõi:

1. **Phiên bản nào** của X được giao dịch đọc?
2. **Giao dịch nào** tạo ra phiên bản đó?
3. **Thứ tự phiên bản** của các lần ghi X là gì?
4. Giao dịch nào đọc phiên bản cũ và giao dịch nào ghi phiên bản kế tiếp?
5. Những giao dịch nào đã commit, đã hủy hoặc có giao dịch đang chồng lấn?

Từ đó hình thành các cạnh WR, WW và RW theo quan hệ phiên bản.

### 8.1. Read-from không giống “câu ghi chạy trước”

Giả sử:

```text
T0 đã commit X^0 = 100
T2 tạo và commit X^2 = 200
T1, với snapshot cũ, đọc X^0 = 100
```

T1 không có WR từ T2 chỉ vì T2 đã ghi X trước khi T1 thực hiện lệnh `SELECT`. T1 đọc từ phiên bản của T0. Việc T1 không thấy X^2 tạo một quan hệ RW/anti-dependency thích hợp giữa T1 và giao dịch cập nhật theo mô hình phiên bản.

### 8.2. Snapshot isolation có giống serializable không?

Không. **Snapshot isolation (SI)** thường cho mỗi giao dịch đọc một snapshot nhất quán và kiểm soát xung đột ghi đồng thời. Cơ chế này loại được nhiều bất thường, nhưng có thể cho phép write skew khi hai giao dịch đọc cùng điều kiện và ghi **hai tập dòng khác nhau**.

**Serializable Snapshot Isolation (SSI)** là một nhóm kỹ thuật theo dõi những quan hệ phụ thuộc nguy hiểm, đặc biệt các cạnh RW, để ngăn lịch không tuần tự hóa được. DBMS có thể hủy một giao dịch và yêu cầu ứng dụng retry. Không được suy ra SSI chỉ từ việc engine “có MVCC” hoặc mức tên `REPEATABLE READ`.

## 9. Quan hệ giữa phụ thuộc và khả năng phục hồi

Không phải mọi vấn đề về phụ thuộc đều là vấn đề tuần tự hóa. Ngoài thứ tự kết quả, hệ thống còn phải xử lý việc giao dịch nguồn **commit hay rollback**.

### 9.1. Recoverable schedule

Một lịch được gọi là **recoverable** khi nếu T2 đọc giá trị do T1 ghi, thì T2 **không được commit trước khi T1 commit**. Nếu T1 cuối cùng abort, T2 không được commit dựa trên kết quả đó.

Ví dụ lịch không recoverable:

```text
w1(X) -> r2(X) -> c2 -> a1
```

T2 đã commit dựa vào thay đổi bị T1 hủy. DBMS không thể chỉ rollback T2 như một giao dịch đang mở.

Lịch recoverable nhưng có nguy cơ phải rollback dây chuyền:

```text
w1(X) -> r2(X) -> a1 -> a2
```

T2 đọc dữ liệu chưa chốt của T1. Khi T1 abort, T2 phải abort để tránh dùng giá trị vô hiệu; nếu nhiều giao dịch nối tiếp nhau đọc phụ thuộc, có thể xảy ra **cascading rollback**.

### 9.2. Cascadeless và strict

- **Cascadeless:** một giao dịch chỉ đọc giá trị do giao dịch khác ghi **sau khi giao dịch ghi đã commit**. Nhờ vậy tránh phải rollback dây chuyền do dirty read.
- **Strict:** không cho giao dịch khác đọc **hoặc ghi đè** giá trị đã được một giao dịch chưa kết thúc ghi, cho đến khi giao dịch ghi đó commit hoặc abort. Đây là điều kiện mạnh hơn đối với các xung đột trên cùng dữ liệu trong mô hình lịch chuẩn.

Có thể tóm tắt quan hệ thông thường:

```text
Strict  =>  Cascadeless  =>  Recoverable
```

Một lịch strict không tự chứng minh là serializable; hai tính chất nói về những khía cạnh khác nhau. Tương tự, lịch serializable vẫn có thể có vấn đề về khả năng phục hồi nếu cho phép đọc từ giao dịch chưa commit theo một thứ tự commit nguy hiểm.

### 9.3. Dirty write

**Dirty write** là việc T2 ghi đè dữ liệu mà T1 đã ghi nhưng chưa commit. Nếu T1 rollback sau đó, việc khôi phục phiên bản đúng có thể phức tạp và làm mất ý nghĩa “giao dịch nào sở hữu thay đổi nào”.

DBMS giao dịch thường ngăn hoặc điều phối dirty write nghiêm ngặt. Khi học phụ thuộc, đừng chỉ nhìn đọc bẩn; **thứ tự ghi trước commit** cũng ảnh hưởng tính an toàn phục hồi.

## 10. Quan hệ phụ thuộc và cơ chế khóa

Khi hai giao dịch có khả năng tạo cạnh xung đột, DBMS có thể sử dụng khóa nhằm ép chúng có thứ tự phù hợp.

### 10.1. Khóa chia sẻ và khóa độc quyền

Trong mô hình khóa cổ điển:

- **Shared lock (S):** hỗ trợ nhiều giao dịch đọc cùng dữ liệu.
- **Exclusive lock (X):** bảo vệ thao tác ghi, thường xung đột với các khóa S/X khác trên cùng đối tượng.

| Đã giữ | Xin S | Xin X |
| --- | --- | --- |
| S | Thường tương thích | Thường phải chờ |
| X | Thường phải chờ | Thường phải chờ |

Đây là bảng trực giác của mô hình khóa S/X cơ bản; DBMS thực có thêm nhiều loại khóa như ý định, cập nhật, vùng chỉ mục và predicate, cũng như cơ chế đọc không khóa nhờ MVCC.

### 10.2. Two-phase locking (2PL)

**Two-phase locking** yêu cầu giao dịch có một giai đoạn nhận thêm khóa rồi một giai đoạn nhả khóa, không nhận thêm khóa mới sau khi đã bắt đầu nhả. Theo mô hình khóa cổ điển với các giả định thích hợp, **2PL bảo đảm conflict-serializability**, vì lịch khóa tạo được một thứ tự giao dịch nhất quán.

Trong **strict 2PL**, khóa ghi thường được giữ đến commit/abort, giúp tránh các giao dịch khác quan sát hoặc ghi đè dữ liệu chưa chốt. Việc giữ khóa có thể tạo chờ khóa và deadlock; DBMS cần phát hiện deadlock hoặc dùng chính sách timeout/abort.

### 10.3. Khóa đọc rồi cập nhật

Một mẫu SQL để khóa bản ghi trước khi quyết định:

```sql
BEGIN;

SELECT balance
FROM accounts
WHERE id = 101
FOR UPDATE;

-- Nếu đủ tiền, ứng dụng cập nhật trong cùng transaction.

UPDATE accounts
SET balance = balance - 300000
WHERE id = 101;

COMMIT;
```

`FOR UPDATE` được nhiều DBMS hỗ trợ với những khác biệt về cú pháp và hành vi. Mẫu này có thể khiến giao dịch khác phải chờ khi cạnh tranh bản ghi 101. Nhưng khóa bản ghi hiện có **không tự bảo vệ** mọi bất biến liên quan nhiều dòng hoặc những dòng có thể được chèn trong tương lai.

## 11. Phụ thuộc và kiểm soát lạc quan

Khi xung đột ít gặp, có thể để giao dịch đọc rồi thử ghi, sau đó **phát hiện phiên bản đã thay đổi** thay vì khóa lâu từ đầu.

Ví dụ bảng hồ sơ có cột `version`:

```sql
-- T1 đã đọc version = 4 cùng dữ liệu hồ sơ.

UPDATE customer_profiles
SET display_name = :new_name,
    version = version + 1
WHERE customer_id = :id
  AND version = 4;
```

Nếu số dòng cập nhật là 1, phiên bản mong đợi vẫn phù hợp tại thời điểm câu ghi được xử lý. Nếu bằng 0, bản ghi có thể đã bị người khác sửa hoặc không còn tồn tại; ứng dụng phải báo conflict, đọc lại hoặc thử lại theo nghiệp vụ.

Cơ chế này giúp phát hiện **WW/lost update** trên một đối tượng theo phiên bản. Nhưng nếu T1 và T2 đọc cùng một ràng buộc trên **nhiều dòng khác nhau**, chỉ kiểm tra version của từng dòng được ghi vẫn có thể bỏ sót **RW anti-dependency** dẫn đến write skew.

Muốn bảo vệ bất biến toàn cục, có thể cần ràng buộc dữ liệu, một bản ghi tổng để cạnh tranh trên cùng tài nguyên, khóa phù hợp hoặc `SERIALIZABLE`.

## 12. Từ đồ thị phụ thuộc đến thiết kế nghiệp vụ

Hãy xét bài toán phòng họp có tối đa 10 người đăng ký cho một buổi. Hai giao dịch T1 và T2 chạy:

```text
T1: SELECT COUNT(*) -> 9; nếu < 10, INSERT thành viên A.
T2: SELECT COUNT(*) -> 9; nếu < 10, INSERT thành viên B.
```

Nếu cả hai cùng đọc 9 rồi insert, tổng cuối là 11, vi phạm giới hạn. Hai giao dịch chèn **hai dòng khác nhau**, nên khóa riêng các dòng đăng ký đã có có thể không đủ.

Mô hình phụ thuộc của bài toán:

- T1 đọc tập đăng ký, T2 chèn dòng mới thuộc tập mà T1 vừa đọc ⇒ **RW T1 → T2** ở cấp predicate.
- T2 đọc tập đăng ký, T1 chèn dòng mới thuộc tập mà T2 vừa đọc ⇒ **RW T2 → T1**.
- Chu trình thể hiện hai quyết định không thể cùng được đặt trong một lịch tuần tự hợp lệ khi cả hai cùng xác nhận còn chỗ.

Các hướng thiết kế:

**Giải pháp A — Đưa giới hạn vào một dòng được ghi có điều kiện.**

```sql
BEGIN;

UPDATE sessions
SET registered_count = registered_count + 1
WHERE session_id = :session_id
  AND registered_count < capacity;

-- Chỉ tiếp tục nếu cập nhật đúng 1 dòng.
INSERT INTO registrations (session_id, user_id)
VALUES (:session_id, :user_id);

COMMIT;
```

Cách này biến việc tranh chấp điều kiện giới hạn thành tranh chấp một dòng `sessions`. Phải dùng một transaction cho tăng số đếm và tạo bản ghi, đồng thời giữ ràng buộc nhất quán giữa số đếm và các đăng ký; xử lý trùng người đăng ký bằng `UNIQUE` thích hợp.

**Giải pháp B — Serializable.** Chạy kiểm tra và insert trong transaction serializable và retry toàn bộ khi DBMS báo lỗi serialization. Với một số trường hợp, ứng dụng có thể nhận conflict thay vì chờ vô hạn.

**Giải pháp C — Khóa đối tượng đại diện.** Khóa dòng `sessions` trước khi đếm và chèn, bảo đảm mọi đường ghi đăng ký đều tuân thủ quy tắc khóa đó. Không chỉ khóa một số dòng đăng ký hiện có.

Việc lựa chọn dựa trên lưu lượng, khả năng biểu diễn bất biến và DBMS cụ thể; không có một cách giải quyết được mọi bài toán mà không cần kiểm chứng.

## 13. Những ngộ nhận khi đọc quan hệ phụ thuộc

### “Hai giao dịch sửa hai dòng khác nhau thì độc lập”

Không chắc. Chúng có thể dựa trên cùng một điều kiện nhiều dòng, tạo chu trình RW như write skew. Cần xem cả **tập dữ liệu đã đọc**, không chỉ bản ghi đã ghi.

### “Có cạnh phụ thuộc nghĩa là có lỗi”

Không. Một lịch tuần tự đúng vẫn có rất nhiều cạnh, ví dụ T1 cập nhật số dư rồi T2 đọc kết quả T1 đã commit. Điều cần xét là **chu trình, trạng thái commit, phiên bản được đọc và bất biến**.

### “Có chu trình nghĩa là đang deadlock”

Không. Chu trình trong đồ thị phụ thuộc biểu diễn yêu cầu thứ tự không thể cùng thỏa mãn; deadlock biểu diễn **vòng chờ tài nguyên**. Một lịch không serializable có thể hoàn tất mà không hề có deadlock.

### “Cứ bật transaction là tránh được lost update”

Không. Transaction đảm nhiệm nguyên tử và những bảo đảm cô lập theo cấu hình. Ở mức cô lập/kiểu truy cập phù hợp, hai giao dịch vẫn có thể cùng đọc giá trị cũ rồi ghi đè. Cần câu cập nhật nguyên tử, khóa, version hoặc mức cô lập mạnh hơn.

### “Snapshot luôn là ảnh mới nhất”

Không. Snapshot có thể cố định theo giao dịch hoặc theo câu lệnh tùy DBMS và isolation level. Một truy vấn có thể thấy phiên bản đã commit cũ dù giao dịch khác vừa commit phiên bản mới.

### “Đồ thị tiền nhiệm từ thứ tự câu SQL luôn mô tả đúng MVCC”

Không. Với MVCC, **read-from** và **version order** mới xác định chính xác những quan hệ phụ thuộc liên quan; thứ tự thời gian thực hiện một `SELECT` và một `UPDATE` không đủ để kết luận phiên bản đã được đọc.

## 14. Quy trình thực tế để phân tích xung đột

Khi điều tra một lỗi dữ liệu do đồng thời, có thể làm theo các bước:

1. **Nêu bất biến nghiệp vụ:** ví dụ tồn kho không âm, một ghế chỉ có một đơn hợp lệ, số người đăng ký không quá sức chứa.
2. **Liệt kê các transaction cạnh tranh:** mỗi transaction đọc những dòng/điều kiện nào và ghi những gì.
3. **Ghi rõ phiên bản đã đọc hoặc giá trị nhìn thấy:** cùng một câu `SELECT` ở mức cô lập khác nhau có thể cho kết quả khác nhau.
4. **Đánh dấu WR, WW, RW:** chú ý cả bản ghi và predicate trên tập dòng.
5. **Dựng đồ thị có hướng:** tìm chu trình trong mô hình đang xét và đối chiếu trạng thái commit/abort.
6. **Kiểm tra cơ chế DBMS:** mức cô lập, MVCC, locking, ràng buộc và lỗi serialization có cho phép cả hai transaction commit không.
7. **Chọn biện pháp bảo vệ phù hợp:** cập nhật nguyên tử có điều kiện, ràng buộc, optimistic locking, khóa chung hoặc serializable.
8. **Xác định đường lỗi:** nếu DBMS hủy một transaction hoặc mạng đứt lúc commit, ứng dụng có thể retry an toàn và phân biệt yêu cầu trùng không?

Bảng sau gợi ý loại cạnh cần chú ý ở một số bài toán:

| Bài toán | Quan hệ cần quan sát | Cơ chế thường hữu ích |
| --- | --- | --- |
| Hai người tăng cùng số dư bằng đọc–tính–ghi | RW hai chiều; WW | `SET balance = balance + ...`; version; khóa. |
| Một giao dịch đọc dữ liệu chưa commit | WR từ transaction chưa commit | Ngăn dirty read bằng cô lập phù hợp. |
| Hai nhân viên sửa cùng hồ sơ | WW, RW | Optimistic locking hoặc row lock. |
| Hai bác sĩ tự bỏ lịch trực | RW trên các dòng được đọc | Serializable, khóa chung hoặc mô hình bất biến khác. |
| Hai người đặt cùng ghế | WW trên ghế hoặc RW trên điều kiện ghế trống | Unique constraint, ghi có điều kiện, transaction. |
| Hai người cùng đăng ký suất cuối | RW ở cấp tập/predicate; có thể WW nếu dùng bộ đếm chung | Bộ đếm có điều kiện, serializable hoặc khóa đại diện. |

## 15. Tự luyện phân tích lịch thực thi

### Bài 1 — Lịch không có chu trình

Cho lịch:

```text
r1(A), w1(A), r2(A), w2(B), c1, c2
```

- `w1(A)` trước `r2(A)` tạo cạnh **WR T1 → T2**.
- Các thao tác trên B không xung đột với thao tác trên A.
- Không có cạnh ngược T2 → T1, nên đồ thị không có chu trình.

Trong mô hình conflict-serializability đơn phiên bản, lịch tương đương thứ tự tuần tự **T1 rồi T2**. Tuy nhiên nếu `r2(A)` đọc giá trị T1 chưa commit, còn phải xét khả năng phục hồi; lịch trên chỉ ghi `c1` sau `r2(A)` nên việc T2 có đọc bẩn hay không phụ thuộc mô hình đọc được cho phép.

### Bài 2 — Hai chiều phụ thuộc

Cho lịch:

```text
r1(A), r2(B), w1(B), w2(A), c1, c2
```

- `r1(A)` trước `w2(A)`: **RW T1 → T2**.
- `r2(B)` trước `w1(B)`: **RW T2 → T1**.

Đồ thị có chu trình. Không thể sắp T1 trước T2 và đồng thời sắp T2 trước T1; lịch không conflict-serializable trong mô hình đơn phiên bản.

### Bài 3 — Ghi đè sau commit

Cho:

```text
w1(X), c1, r2(X), w2(X), c2
```

- T2 đọc phiên bản do T1 đã commit: **WR T1 → T2**.
- T2 viết phiên bản X mới sau T1: **WW T1 → T2**.
- Không có cạnh ngược.

Có phụ thuộc nhưng không có lỗi hiển nhiên. Đây có thể là một lịch hợp lệ tương đương **T1 → T2**.

### Bài 4 — Phòng trực

T1 đọc A/B, ghi `A=false`. T2 đọc A/B, ghi `B=false`. Cả hai commit dù bắt đầu với A/B đều `true`.

- Hai giao dịch có xung đột WW trên cùng dòng không? **Không.**
- Có quan hệ RW hai chiều không? **Có**, vì mỗi giao dịch đọc dòng mà giao dịch kia thay đổi.
- Một cơ chế chỉ ngăn hai giao dịch ghi cùng dòng có đủ không? **Không**, vì bất biến liên quan cả A và B.

Bài tập này phân biệt rõ **xung đột ghi trực tiếp** và **phụ thuộc đọc–ghi trong một quyết định nghiệp vụ**.

## 16. Kết nối mô hình với điều khiển đồng thời

Quan hệ phụ thuộc trả lời câu hỏi: **“Các giao dịch đã quan sát và thay đổi dữ liệu của nhau theo trật tự nào?”**. Bộ điều khiển đồng thời sử dụng những thông tin có liên quan để quyết định khi nào cho phép đọc, khi nào khóa hoặc tạo phiên bản, khi nào commit và khi nào phải abort.

Một hệ thống có thể cho nhiều giao dịch chạy xen kẽ mà vẫn đúng, miễn là các quan hệ phụ thuộc của những giao dịch đã commit phù hợp với bảo đảm cô lập cần thiết. Ngược lại, một chuỗi SQL chạy “thành công” về mặt câu lệnh vẫn có thể tạo kết quả sai nếu các giao dịch đã đọc phiên bản cũ, ghi vào những đối tượng khác nhau và phá một bất biến chung.

Khi thiết kế hoặc gỡ lỗi ứng dụng có nhiều truy cập đồng thời, hãy đi từ **bất biến**, đến **tập dữ liệu mỗi giao dịch đọc/ghi**, rồi đến **đồ thị WR/WW/RW**, và cuối cùng chọn cơ chế transaction phù hợp với DBMS đang dùng.
