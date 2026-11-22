# Biểu diễn lịch thực thi bằng thao tác đọc, ghi, COMMIT và ROLLBACK

Khi nhiều transaction chạy gần như cùng lúc, cơ sở dữ liệu phải quyết định lúc nào thực hiện thao tác đọc, thao tác ghi, commit hoặc rollback của từng transaction. **Lịch thực thi (schedule)** là cách ghi lại thứ tự các thao tác ấy. Nó giúp chúng ta phân tích một tình huống đồng thời bằng các bước cụ thể, thay vì chỉ nói chung chung rằng “hai giao dịch chạy cùng lúc”.

Một transaction có thể hoàn toàn đúng khi thực hiện một mình, nhưng kết quả có thể khác đi nếu các thao tác của nó xen kẽ với transaction khác. Trong chủ đề *Database Transaction Concurrency*, mô hình lịch thực thi là công cụ để nhận biết những kết quả như dirty read, lost update, đọc không lặp lại, write skew; đồng thời giải thích vì sao commit, rollback và mức cô lập giao dịch lại quan trọng.

Bài này dùng mô hình khái niệm theo thao tác **read/write**. Khi triển khai, hệ quản trị cơ sở dữ liệu có thể thực hiện một câu SQL bằng nhiều thao tác nội bộ, nhiều phiên bản dữ liệu và nhiều cơ chế khóa khác nhau. Vì vậy, lịch ký hiệu là mô hình để suy luận, không phải bản ghi đầy đủ mọi thao tác vật lý của database engine.

## 1. Giao dịch và lịch thực thi

Giả sử một hệ thống có hai transaction:

- **T1** chuyển 20 từ tài khoản A sang tài khoản B.
- **T2** đọc số dư A và B để lập báo cáo tổng.

Trạng thái ban đầu:

| Mục dữ liệu | Giá trị |
|---|---:|
| A | 100 |
| B | 100 |
| A + B | 200 |

Nếu chỉ chạy T1, số dư sau khi commit là A = 80, B = 120, tổng vẫn là 200. Nếu T2 đọc cả hai số dư trước T1, tổng là 200; nếu đọc cả hai sau T1, tổng vẫn là 200.

Vấn đề xuất hiện khi **T2 đọc A ở một thời điểm và đọc B ở thời điểm khác**, trong khi T1 đã chuyển tiền giữa hai lần đọc. Chẳng hạn, nếu T2 đọc A = 100 trước T1 commit, nhưng đọc B = 120 sau T1 commit, tổng mà T2 tính được là **220**. Mỗi giá trị riêng lẻ từng là giá trị hợp lệ; cặp giá trị ghép lại không tương ứng một trạng thái đồng nhất của thao tác chuyển tiền.

Để nhìn rõ điều đó, cần chuyển các transaction thành những **thao tác nguyên thủy (primitive operations)** và sắp chúng lên một lịch.

### Ba khái niệm cần tách biệt

| Khái niệm | Mô tả |
|---|---|
| **Transaction** | Một chuỗi thao tác có quan hệ logic, được kết thúc bằng commit hoặc rollback |
| **Operation** | Một thao tác trong chuỗi: đọc, ghi, xác nhận, hủy |
| **Schedule** | Một thứ tự xen kẽ cụ thể của các operation thuộc một hoặc nhiều transaction, vẫn giữ thứ tự nội bộ của từng transaction |

Một lịch có thể chứa rất nhiều thao tác, nhưng luôn cần giữ được câu trả lời cho hai câu hỏi: **thao tác này thuộc transaction nào** và **nó xảy ra trước hay sau thao tác nào**.

## 2. Bộ ký hiệu R, W, C và A

Trong tài liệu lý thuyết về concurrency control, cách viết thường dùng là:

| Ký hiệu | Tên | Ý nghĩa |
|---|---|---|
| `R1(A)` | Read | T1 đọc mục dữ liệu A |
| `W1(A)` | Write | T1 ghi một giá trị mới cho A |
| `R2(B)` | Read | T2 đọc mục dữ liệu B |
| `W2(B)` | Write | T2 ghi một giá trị mới cho B |
| `C1` | Commit | T1 được commit |
| `C2` | Commit | T2 được commit |
| `A1` | Abort | T1 bị hủy và các tác động chưa commit của nó phải được hoàn tác |
| `A2` | Abort | T2 bị hủy và các tác động chưa commit của nó phải được hoàn tác |

Có tài liệu viết `r1(x)`, `w1(x)`, `c1`, `a1`; hoặc viết `ROLLBACK(T1)` thay cho `A1`. Các cách viết đều cùng ý tưởng. Chỉ số **1, 2, 3, ...** là định danh transaction, không phải thứ tự thời gian. Chữ **A, B, X, Y** là mục dữ liệu logic, không phải tên bảng cố định.

Trong bài này:

- `R1(A)=100` được dùng khi muốn chỉ rõ giá trị mà T1 nhìn thấy.
- `W1(A:=80)` được dùng khi muốn chỉ rõ giá trị T1 ghi.
- `C1` và `A1` thể hiện **kết cục của toàn transaction**, không phải một phép đọc hoặc ghi bổ sung.
- Ký hiệu `A1` cho *abort* khác với mục dữ liệu `A`; cần nhìn chỉ số và vị trí dấu ngoặc để tránh nhầm.

Ví dụ:

~~~text
R1(A)  W1(A)  R2(B)  C1  W2(B)  C2
~~~

Có thể đọc thành: T1 đọc A, T1 ghi A, T2 đọc B, T1 commit, T2 ghi B, T2 commit.

### Thao tác SQL không luôn tương ứng đúng một R hoặc W

Một câu SQL:

~~~sql
UPDATE accounts
SET balance = balance - 20
WHERE id = 1 AND balance >= 20;
~~~

vừa cần **xem giá trị hiện tại** của tài khoản, vừa **ghi giá trị mới** nếu điều kiện thỏa. Trong mô hình đơn giản, nó có thể được diễn đạt như `R1(A)` rồi `W1(A)`; trong engine thật, các thao tác đọc để cập nhật có thể đi cùng khóa hàng hoặc kiểm tra lại điều kiện sau khi chờ transaction khác.

Tương tự, một `SELECT SUM(...)` có thể đọc nhiều hàng; một `INSERT` có thể đọc index để kiểm tra ràng buộc; một câu `DELETE` có thể ảnh hưởng nhiều mục dữ liệu. Ký hiệu lịch giúp **thu gọn** những điểm có ý nghĩa đối với cạnh tranh đồng thời.

## 3. Quy tắc tạo một lịch hợp lệ

Giả sử chương trình định nghĩa T1 như sau:

~~~text
T1:
  R1(A)
  W1(A)
  R1(B)
  W1(B)
  C1
~~~

T2 được định nghĩa:

~~~text
T2:
  R2(A)
  R2(B)
  C2
~~~

Một schedule được tạo bằng cách **đan xen** thao tác của T1 và T2 nhưng vẫn **giữ nguyên thứ tự của các thao tác trong mỗi transaction**. Chẳng hạn, `R1(A)` phải đứng trước `W1(A)`, và `W1(A)` phải đứng trước `R1(B)`, vì đó là thứ tự chương trình của T1.

Ta có thể đánh số vị trí trong lịch:

~~~text
S = [
  R1(A), W1(A),
  R2(A),
  R1(B), W1(B), C1,
  R2(B), C2
]
~~~

Trong S, thao tác `R2(A)` nằm giữa phần ghi A và phần ghi B của T1; song lịch vẫn bảo toàn thứ tự từng transaction.

Nếu một transaction bị hủy, lịch kết thúc transaction đó bằng `A1` thay vì `C1`. Một transaction không đồng thời có cả hai kết cục commit và abort trong cùng một lần thực thi.

**Lưu ý:** Lịch giữ đúng thứ tự chương trình vẫn có thể là lịch không an toàn hoặc không được một hệ quản trị/mức cô lập cụ thể cho phép. “Hợp lệ về mặt ký hiệu” không tự bảo đảm “được database chấp nhận”.

## 4. Lịch tuần tự và lịch xen kẽ

### 4.1. Lịch tuần tự (serial schedule)

Lịch **tuần tự** hoàn tất tất cả thao tác của một transaction trước khi chuyển sang transaction tiếp theo.

Ví dụ T1 chạy hết rồi đến T2:

~~~text
Thời gian →
T1: R1(A)  W1(A:=80)  R1(B)  W1(B:=120)  C1
T2:                                           R2(A)=80  R2(B)=120  C2
~~~

Hoặc T2 chạy hết rồi T1:

~~~text
Thời gian →
T2: R2(A)=100  R2(B)=100  C2
T1:                             R1(A)  W1(A:=80)  R1(B)  W1(B:=120)  C1
~~~

Ở hai lịch tuần tự này, T2 nhìn được một trạng thái hoàn chỉnh và báo cáo tổng bằng 200.

Lịch tuần tự dễ suy luận, nhưng buộc mọi transaction nối đuôi nhau có thể làm giảm khả năng sử dụng tài nguyên và thông lượng. Database thường cho phép các transaction **chạy xen kẽ** để khai thác nhiều kết nối, CPU và I/O.

### 4.2. Lịch xen kẽ (interleaved schedule)

Một lịch xen kẽ có thể được diễn đạt bằng bảng thời gian:

| Bước | T1: chuyển tiền | T2: báo cáo |
|---:|---|---|
| 1 | | `R2(A)=100` |
| 2 | `R1(A)=100` | |
| 3 | `W1(A:=80)` | |
| 4 | `R1(B)=100` | |
| 5 | `W1(B:=120)` | |
| 6 | `C1` | |
| 7 | | `R2(B)=120` |
| 8 | | `C2` |

Viết gọn:

~~~text
S = R2(A)  R1(A)  W1(A)  R1(B)  W1(B)  C1  R2(B)  C2
~~~

T2 đọc A = 100 trước khi T1 commit và đọc B = 120 sau khi T1 commit, nên tính tổng bằng 220. Đây là ví dụ **read skew** qua nhiều lần đọc. T2 không đọc giá trị chưa commit, vì lần đọc đầu xảy ra trước các cập nhật của T1 và lần đọc sau xảy ra sau commit. Trong PostgreSQL ở mức `READ COMMITTED`, hai câu `SELECT` tách biệt trong cùng transaction có thể quan sát hai snapshot khác nhau, làm lịch kiểu này có thể xảy ra.

Quan sát quan trọng: **xen kẽ không tự nó là lỗi**. Lỗi hay không phụ thuộc vào thao tác tranh chấp, ràng buộc nghiệp vụ, mức cô lập và kết quả mà transaction có quyền quan sát.

## 5. Biểu diễn giá trị theo thời gian

Một lịch chỉ ghi `R1(A), W1(A)` đôi khi chưa đủ để giải thích dữ liệu được đọc. Khi phân tích, có thể ghi rõ giá trị bên cạnh thao tác và một bảng trạng thái.

Giả sử A ban đầu bằng 100, T1 trừ 20, T2 chỉ đọc:

~~~text
Ban đầu: A = 100

T1: R1(A)=100
T1: W1(A:=80)
T1: C1
T2: R2(A)=80
T2: C2

Cuối: A = 80
~~~

| Bước | Operation | A đã commit gần nhất | Giá trị ghi chưa commit | Ghi chú |
|---:|---|---:|---:|---|
| 0 | Khởi tạo | 100 | — | Chưa có transaction |
| 1 | `R1(A)=100` | 100 | — | T1 đọc giá trị ban đầu |
| 2 | `W1(A:=80)` | 100 | 80 bởi T1 | Chưa commit |
| 3 | `C1` | 80 | — | T1 xác nhận |
| 4 | `R2(A)=80` | 80 | — | T2 đọc giá trị đã commit |
| 5 | `C2` | 80 | — | T2 kết thúc |

Bảng này phân biệt **giá trị transaction đang cố ghi** với **giá trị đã commit có thể quan sát**. Hệ quản trị có MVCC có thể lưu nhiều phiên bản cùng tồn tại, nên “giá trị đã commit gần nhất” cũng không bảo đảm là giá trị một transaction cụ thể nhìn thấy: transaction đó có thể dùng snapshot cũ.

Vì vậy, khi có nhiều snapshot hoặc nhiều transaction, ký hiệu `R2(A)=...` cần đi kèm thông tin **T2 đang đọc phiên bản nào**, hoặc ít nhất xác định mức cô lập đang giả định.

## 6. COMMIT là ranh giới của kết quả đã xác nhận

Commit không phải cách viết trang trí cho việc một câu `UPDATE` đã chạy xong. Nó là mốc database xác nhận kết quả của **transaction**.

Ví dụ:

~~~text
Ban đầu: A = 100

R1(A)=100
W1(A:=80)
R2(A)=?
C1
C2
~~~

Dấu hỏi không có một đáp án đúng cho mọi hệ quản trị:

- Nếu T2 được phép **dirty read**, nó có thể thấy giá trị chưa commit là 80.
- Nếu T2 dùng một snapshot đã commit trước T1, nó có thể thấy 100.
- Nếu T2 yêu cầu khóa xung đột với T1, thao tác có thể bị chặn cho đến khi T1 hoàn tất, rồi đọc theo ngữ nghĩa của database và mức cô lập.
- Nếu T2 bắt đầu sau `C1` và đọc dữ liệu mới theo `READ COMMITTED`, nó thường thấy 80.

Khi mô hình hóa, phải **nói rõ giả định đọc** thay vì tự gán rằng mọi `R2(A)` sau `W1(A)` đều nhìn giá trị mới.

Commit cũng ảnh hưởng tới việc **một transaction đọc dữ liệu từ transaction khác trước hay sau mốc commit**. Quan hệ này đặc biệt quan trọng trong phân tích recoverability và cascading rollback.

## 7. ROLLBACK/ABORT làm thay đổi kết quả lịch

Giả sử T1 sửa A nhưng gặp lỗi và rollback:

~~~text
Ban đầu: A = 100

R1(A)=100
W1(A:=80)
A1
R2(A)=100
C2
~~~

Sau `A1`, thay đổi A:=80 chưa commit của T1 bị hoàn tác về mặt logic. T2 không được coi giá trị 80 của T1 là một thay đổi đã commit. Trong nhiều hệ quản trị, việc rollback được hiện thực bằng undo, phiên bản dữ liệu hoặc log phục hồi, chứ không nhất thiết bằng một câu SQL đảo ngược hiển thị cho client.

Có thể trình bày cùng diễn biến theo trục thời gian:

~~~text
Thời gian →
T1: R1(A) ─ W1(A:=80) ───── A1
T2:                             R2(A)=100 ─ C2
A đã commit: 100 ─────────────────────────────── 100
~~~

Trong mô hình kết quả, `A1` có nghĩa transaction **không đóng góp các thay đổi được commit**. Tuy nhiên, các thao tác mà transaction khác đã thực hiện *trước* khi biết T1 rollback vẫn có thể bị ảnh hưởng nếu engine cho phép đọc dữ liệu chưa commit. Đây là lý do cần phân tích **cả thao tác đọc lẫn thứ tự commit/abort**, không chỉ trạng thái cuối cùng.

### ROLLBACK không xóa lịch sử đã diễn ra

Khi viết lịch:

~~~text
W1(A:=80)  R2(A)=80  A1
~~~

Không được xóa `R2(A)` khỏi lịch như thể nó chưa từng xảy ra. T2 **đã đọc** giá trị do T1 tạo ra; nếu T2 dùng giá trị đó để ghi dữ liệu hoặc gửi phản hồi, việc T1 rollback không thể tự động biến quá khứ thành chưa xảy ra. Ta cần tiếp tục theo dõi kết cục của T2.

## 8. Dirty read và rollback dây chuyền

**Dirty read** là khi T2 đọc giá trị do T1 ghi **trước khi T1 commit**.

~~~text
Ban đầu: A = 100

T1: W1(A:=80)
T2: R2(A)=80        ← đọc dữ liệu chưa commit của T1
T1: A1              ← T1 rollback
T2: C2              ← T2 đã commit dựa trên giá trị bẩn
~~~

Nếu T2 thật sự sử dụng giá trị 80, nó có thể đã tạo ra kết quả phụ thuộc vào một thay đổi **không bao giờ được commit**. Lịch này còn có vấn đề về **khả năng phục hồi**: T2 commit trước khi transaction mà nó đọc được xác nhận.

Hai loại lịch cần phân biệt:

**Lịch có thể phục hồi (recoverable schedule):** nếu T2 đọc giá trị do T1 ghi, thì T2 chỉ được commit **sau khi T1 đã commit**.

~~~text
W1(A:=80)  R2(A)=80  C1  C2
~~~

Lịch này *recoverable* vì `C1` đứng trước `C2`. Nhưng T2 vẫn đọc dữ liệu chưa commit. Nếu T1 rollback trước `C1`, T2 cũng có thể phải rollback. Đó là **cascading abort**: hủy một transaction kéo theo những transaction đã tiêu thụ dữ liệu chưa commit của nó.

**Lịch không gây rollback dây chuyền (cascadeless schedule):** T2 chỉ đọc giá trị T1 đã ghi **sau khi T1 commit**.

~~~text
W1(A:=80)  C1  R2(A)=80  C2
~~~

Như vậy, nếu T1 rollback, T2 chưa từng tiêu thụ giá trị chưa được xác nhận ấy. Đây là cách nhìn trực quan vì sao các mức cô lập không cho đọc uncommitted giúp tránh nhóm lỗi này.

**Lưu ý triển khai:** PostgreSQL không cho phép dirty read, kể cả khi yêu cầu mức `READ UNCOMMITTED` (hành vi thực tế tương đương `READ COMMITTED` đối với điểm này). Các lịch dirty read là **mô hình lý thuyết** và có thể tương ứng với cơ chế khác, không phải mặc định của PostgreSQL.

## 9. Dirty write và yêu cầu lịch strict

**Dirty write** xảy ra khi T2 ghi đè một mục dữ liệu mà T1 đã ghi nhưng T1 chưa commit hoặc rollback.

~~~text
Ban đầu: A = 100

W1(A:=80)
W2(A:=70)     ← T2 ghi đè khi T1 chưa kết thúc
A1
C2
~~~

Một vấn đề là việc hoàn tác T1 phải xác định trạng thái nào cần khôi phục mà không phá kết quả hợp lệ của T2. Nhiều database giao dịch ngăn dirty write bằng khóa ghi hoặc cơ chế cạnh tranh tương đương.

Khái niệm **strict schedule** cung cấp điều kiện mạnh hơn: nếu T1 đã ghi mục dữ liệu X, transaction khác **không được đọc hoặc ghi X cho tới khi T1 commit hoặc abort**.

~~~text
Lịch KHÔNG strict:
  W1(A:=80)  R2(A)=80  C1  C2

Lịch strict:
  W1(A:=80)  C1  R2(A)=80  C2
~~~

Trong lịch strict, sau khi T1 ghi A, mọi transaction khác phải chờ kết cục của T1 trước khi đọc/ghi A theo mô hình này.

Quan hệ giữa ba tính chất thường được tóm tắt như sau:

~~~text
Strict
  ⇒ Cascadeless
  ⇒ Recoverable
~~~

Chiều ngược lại **không nhất thiết đúng**:

- Một lịch recoverable vẫn có thể đọc dữ liệu chưa commit và gây cascading abort.
- Một lịch cascadeless không dirty read vẫn có thể không strict nếu cho phép dirty write.
- Lịch strict hỗ trợ phục hồi đơn giản hơn, nhưng chỉ strict **không tự đảm bảo serializability** và không tự giải quyết mọi bất biến nghiệp vụ.

## 10. Non-repeatable read dưới dạng lịch

**Non-repeatable read** xảy ra khi cùng một transaction đọc một mục dữ liệu hai lần nhưng nhận hai giá trị khác nhau, vì transaction khác đã cập nhật và commit ở giữa.

~~~text
Ban đầu: A = 100

R1(A)=100
W2(A:=90)
C2
R1(A)=90
C1
~~~

Ở đây, T1 không có cùng một ảnh chụp trong hai lần đọc. Không có dirty read: lần đọc thứ hai nhìn dữ liệu **đã commit** của T2. Với PostgreSQL `READ COMMITTED`, hai câu `SELECT` thông thường trong cùng T1 có thể nhìn hai snapshot khác nhau.

Một bảng diễn giải:

| Bước | Transaction | Kết quả |
|---:|---|---|
| 1 | T1: `R1(A)` | 100 |
| 2 | T2: `W2(A:=90)` | Chuẩn bị giá trị mới |
| 3 | T2: `C2` | Giá trị 90 đã commit |
| 4 | T1: `R1(A)` | 90 |
| 5 | T1: `C1` | Kết thúc |

Ở mức PostgreSQL `REPEATABLE READ`, những lần đọc thông thường của T1 sẽ dùng snapshot nhất quán của transaction (trừ những khác biệt liên quan tới chính thay đổi do T1 tạo ra), nên mẫu đọc khác nhau như trên được ngăn đối với cập nhật từ T2.

Cần nhớ **non-repeatable read khác dirty read**: thay đổi ở lần đọc thứ hai là thay đổi đã commit, không phải dữ liệu tạm.

## 11. Lost update: hai transaction cùng sửa dựa trên giá trị cũ

**Lost update** là một tình huống điển hình cần biểu diễn cả R và W. Giả sử A = 100, T1 muốn trừ 10, T2 muốn trừ 20.

Khi chạy tuần tự, kết quả mong đợi là:

~~~text
T1 rồi T2: 100 - 10 - 20 = 70
T2 rồi T1: 100 - 20 - 10 = 70
~~~

Nếu mỗi transaction tính toán dựa trên số đọc cũ:

| Bước | T1 | T2 |
|---:|---|---|
| 1 | `R1(A)=100` | |
| 2 | | `R2(A)=100` |
| 3 | `W1(A:=90)` | |
| 4 | `C1` | |
| 5 | | `W2(A:=80)` |
| 6 | | `C2` |

Lịch:

~~~text
R1(A)=100  R2(A)=100  W1(A:=90)  C1  W2(A:=80)  C2
~~~

Kết quả là **80**, mất tác động trừ 10 của T1. Mỗi transaction tin rằng mình đã trừ tiền, nhưng T2 ghi một giá trị tính từ snapshot cũ.

Lịch có thể sinh ra từ ứng dụng đọc giá trị rồi ghi lại giá trị đã tính:

~~~sql
-- T1 và T2 đều đọc balance = 100 trước khi ghi.
SELECT balance FROM accounts WHERE id = 1;

-- T1 tính 100 - 10, ghi 90.
UPDATE accounts SET balance = 90 WHERE id = 1;

-- T2 tính 100 - 20, ghi 80.
UPDATE accounts SET balance = 80 WHERE id = 1;
~~~

Đây là các câu SQL minh họa **cách tổ chức đọc–tính–ghi**. Cửa sổ lost update cụ thể còn tùy cách transaction/driver và mức cô lập chạy. Ở PostgreSQL `READ COMMITTED`, mẫu ứng dụng đọc rồi ghi giá trị cố định có thể bị overwrite khi các transaction lần lượt cập nhật.

Nếu nghiệp vụ chỉ cần cộng/trừ theo giá trị đang có, một phép ghi tương đối thường an toàn hơn:

~~~sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :account_id
  AND balance >= :amount
RETURNING balance;
~~~

Trong PostgreSQL `READ COMMITTED`, UPDATE cạnh tranh trên cùng một hàng sẽ dùng cơ chế khóa hàng và đánh giá lại điều kiện liên quan đến phiên bản hiện hành sau khi chờ. Ứng dụng vẫn phải kiểm tra số hàng được cập nhật và đặt các thay đổi nghiệp vụ liên quan trong transaction phù hợp.

Nếu phép tính bắt buộc dựa trên dữ liệu đã đọc trước đó, có thể cân nhắc **optimistic locking** bằng cột version:

~~~sql
UPDATE accounts
SET balance = :new_balance,
    version = version + 1
WHERE id = :account_id
  AND version = :version_read;
~~~

Khi kết quả là 0 hàng, giá trị đã đọc có thể đã lỗi thời và ứng dụng cần đọc lại hoặc xử lý xung đột.

## 12. Write skew: ghi vào các hàng khác nhau vẫn có thể sai

Không phải mọi lịch nguy hiểm đều có hai transaction cùng ghi một hàng. Xét ca trực bệnh viện có hai bác sĩ A và B đang trực, cùng quy tắc **phải còn ít nhất một người trực**.

T1 muốn cho A nghỉ, T2 muốn cho B nghỉ. Mỗi transaction đọc tình trạng cả hai bác sĩ rồi chỉ cập nhật **hàng của mình**:

~~~text
Ban đầu: A_on_duty = true, B_on_duty = true

T1: R1(A)=true
T1: R1(B)=true

T2: R2(A)=true
T2: R2(B)=true

T1: W1(A:=false)
T2: W2(B:=false)

T1: C1
T2: C2
~~~

Hai transaction đọc cùng một snapshot trong đó vẫn có hai bác sĩ; mỗi transaction kết luận “nếu mình nghỉ thì vẫn còn một người”. Nhưng kết quả sau hai commit là **không ai trực**.

Lịch này là ví dụ của **write skew**. Không có `W1(A)` cạnh tranh trực tiếp với `W2(A)`; T1 ghi A, T2 ghi B. Chỉ nhìn xung đột *write–write* là chưa đủ để phát hiện vi phạm bất biến liên quan nhiều hàng.

Với PostgreSQL, mức `REPEATABLE READ` dùng snapshot isolation có thể cho phép mẫu write skew như trên. Có thể dùng transaction `SERIALIZABLE` cùng xử lý retry khi bị hủy do serialization failure, hoặc khóa một hàng phối hợp chung theo một giao thức nhất quán, hoặc thiết kế lại dữ liệu để bất biến được cưỡng chế trực tiếp.

## 13. Xung đột giữa các operation

Hai thao tác được coi là **conflict** trong mô hình conflict-serializability nếu thỏa đủ ba điều kiện:

1. Chúng thuộc **hai transaction khác nhau**.
2. Chúng truy cập **cùng một mục dữ liệu**.
3. Có **ít nhất một thao tác ghi**.

Bảng phân loại:

| Cặp thao tác | Có conflict? | Giải thích |
|---|---|---|
| `R1(A)`, `R2(A)` | Không | Cùng đọc A |
| `R1(A)`, `W2(A)` | Có | T2 thay đổi thứ T1 đã đọc |
| `W1(A)`, `R2(A)` | Có | T2 đọc mục T1 đã ghi |
| `W1(A)`, `W2(A)` | Có | Hai transaction cùng ghi A |
| `W1(A)`, `R2(B)` | Không | Khác mục dữ liệu |
| `R1(A)`, `W1(A)` | Không theo định nghĩa conflict giữa các transaction | Cùng thuộc T1; thứ tự nội bộ đã cố định |

**Thứ tự giữa các conflict rất quan trọng.** Ví dụ:

~~~text
S1: W1(A)  R2(A)
S2: R2(A)  W1(A)
~~~

Hai lịch có cùng tập thao tác nhưng khác thứ tự xung đột, nên T2 có thể quan sát phiên bản A khác nhau. Ngược lại, đổi chỗ hai thao tác không conflict có thể giữ được ý nghĩa tương đương của lịch ở mô hình này.

Khi xét xung đột, `C1` và `A1` không phải read/write trên một mục dữ liệu, nhưng **không thể bỏ qua** khi phân tích dữ liệu chưa commit, tính recoverable, lock và kết quả cuối cùng.

## 14. Đồ thị phụ thuộc và conflict-serializability

Một cách kiểm tra lịch có thể tương đương về xung đột với một lịch tuần tự là lập **precedence graph** (đồ thị thứ tự trước).

Cách dựng:

1. Tạo một đỉnh cho mỗi transaction trong lịch đang xét.
2. Với mỗi cặp operation conflict giữa Ti và Tj, nếu thao tác của Ti xảy ra trước thao tác của Tj thì thêm cạnh **Ti → Tj**.
3. Nếu đồ thị **không có chu trình**, lịch là **conflict-serializable**. Thứ tự topo của đồ thị cho một thứ tự transaction tuần tự tương đương theo xung đột.
4. Nếu đồ thị **có chu trình**, lịch không conflict-serializable.

### Ví dụ không có chu trình

~~~text
S = R1(A)  W1(A)  C1  R2(A)  W2(A)  C2
~~~

Ở cùng mục dữ liệu A, các xung đột đi từ T1 sang T2. Đồ thị có một cạnh:

~~~mermaid
flowchart LR
  T1["T1"] --> T2["T2"]
~~~

Có thể xếp tuần tự T1 rồi T2. Lịch này vốn đã tuần tự, nên kết quả dễ nhận biết; nguyên tắc tương tự áp dụng cho lịch xen kẽ với các thao tác không conflict.

Ví dụ các thao tác độc lập:

~~~text
R1(A)  R2(B)  W1(A)  W2(B)  C1  C2
~~~

T1 chỉ đụng A, T2 chỉ đụng B. Không có cạnh conflict giữa chúng, nên lịch xen kẽ này tương đương cả hai thứ tự tuần tự theo mô hình read/write.

### Ví dụ có chu trình

Quay lại lịch write skew:

~~~text
R1(A)  R1(B)  R2(A)  R2(B)  W1(A)  W2(B)  C1  C2
~~~

Các xung đột tạo hai chiều:

- `R1(B)` đứng trước `W2(B)` nên có **T1 → T2**.
- `R2(A)` đứng trước `W1(A)` nên có **T2 → T1**.

~~~mermaid
flowchart LR
  T1["T1"] --> T2["T2"]
  T2 --> T1
~~~

Vì có chu trình, lịch không conflict-serializable. Nếu T1 chạy hết trước T2, T2 sẽ thấy A đã nghỉ và không thể cho B nghỉ theo quy tắc. Nếu T2 chạy hết trước T1, tình huống đối xứng cũng vậy. Hai transaction cùng commit trong lịch xen kẽ gây ra kết quả không tương đương với hai thứ tự tuần tự hợp lệ.

**Giới hạn cần nhớ:** Conflict-serializability là tiêu chí của mô hình read/write trên các mục dữ liệu xác định. Nó là điều kiện đủ mạnh, nhưng không phải mọi lịch không conflict-serializable đều sai nghiệp vụ; khái niệm view-serializability rộng hơn. Ngoài ra, các **predicate read** như “đếm tất cả ghế chưa bán” có thể phụ thuộc vào tập hàng thay đổi hoặc phantom, nên trong phân tích thực tế cần biểu diễn cả phạm vi điều kiện đọc, không chỉ các hàng đã thấy.

## 15. Lịch đầy đủ, lịch chưa hoàn tất và transaction abort

Một lịch đang được quan sát có thể kết thúc ở một thời điểm mà transaction còn mở:

~~~text
R1(A)  W1(A)  R2(B)
~~~

Đây là một **prefix** của lịch, chưa phải lịch kết thúc đầy đủ. Ta chưa thể kết luận T1 đã commit hay sẽ rollback; cũng chưa biết T2 sẽ đọc/ghi gì tiếp theo.

Hai lịch tiếp diễn có thể dẫn đến kết quả khác nhau:

~~~text
S_commit:
R1(A)  W1(A)  R2(B)  C1  C2

S_abort:
R1(A)  W1(A)  R2(B)  A1  C2
~~~

Trong một lịch có abort, khi phân tích trạng thái cuối cùng chỉ có tác động từ những transaction commit được giữ lại. Nhưng khi phân tích **recoverability**, vẫn phải xét những transaction đã đọc từ transaction abort và các phụ thuộc phát sinh trước đó.

Điều này lý giải vì sao **cùng một chuỗi đọc–ghi ban đầu không đủ quyết định tính an toàn**, nếu chưa biết phần đuôi commit/rollback.

### Commit order khác với thời điểm bắt đầu

~~~text
R1(A)  R2(B)  W2(B)  C2  W1(A)  C1
~~~

T1 bắt đầu trước T2, nhưng T2 commit trước T1. Lịch xen kẽ không bắt buộc transaction có ID nhỏ hoặc bắt đầu trước phải commit trước. Thứ tự commit có thể khác thứ tự khởi tạo, dù các cơ chế cô lập và xung đột có thể hạn chế kết cục hợp lệ.

## 16. Từ lịch ký hiệu sang hai phiên SQL thực tế

Giả sử dùng **PostgreSQL**, có bảng:

~~~sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(12, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts(id, balance)
VALUES (1, 100.00), (2, 100.00);
~~~

Mở hai kết nối độc lập, gọi là **Session 1** (T1) và **Session 2** (T2). Ta muốn quan sát lịch **read skew qua hai câu SELECT** ở mức READ COMMITTED.

| Thứ tự | Session 2: T2 (báo cáo) | Session 1: T1 (chuyển tiền) |
|---:|---|---|
| 1 | `BEGIN ISOLATION LEVEL READ COMMITTED;` | |
| 2 | `SELECT balance FROM accounts WHERE id = 1;` → 100 | |
| 3 | | `BEGIN;` |
| 4 | | `UPDATE accounts SET balance = balance - 20 WHERE id = 1;` |
| 5 | | `UPDATE accounts SET balance = balance + 20 WHERE id = 2;` |
| 6 | | `COMMIT;` |
| 7 | `SELECT balance FROM accounts WHERE id = 2;` → 120 | |
| 8 | `COMMIT;` | |

Nếu T2 tự cộng hai giá trị nhận được, kết quả là 220. Đây là hệ quả từ **hai câu SELECT có snapshot khác nhau** dưới PostgreSQL READ COMMITTED, mặc dù T2 đã bao cả hai SELECT trong một transaction.

Sơ đồ thao tác:

~~~text
R2(A)=100
R1(A)=100
W1(A:=80)
R1(B)=100
W1(B:=120)
C1
R2(B)=120
C2
~~~

Muốn đọc một ảnh chụp nhất quán của cả hai tài khoản, có thể:

- Đọc cả hai giá trị trong **một statement SELECT** dưới cơ chế snapshot nhất quán áp dụng cho statement đó.
- Dùng transaction ở mức **REPEATABLE READ** phù hợp cho nhiều SELECT, với ngữ nghĩa cụ thể của PostgreSQL.
- Khi nghiệp vụ cần bảo đảm tương đương thực thi tuần tự đối với các phép đọc/ghi phức tạp, cân nhắc **SERIALIZABLE** và xử lý retry.

Ví dụ một câu SELECT:

~~~sql
SELECT SUM(balance) AS total_balance
FROM accounts
WHERE id IN (1, 2);
~~~

Trong PostgreSQL READ COMMITTED, một câu SELECT thông thường đọc dữ liệu theo một snapshot ở thời điểm statement bắt đầu. Nó sẽ thấy một trạng thái đã commit phù hợp trước hoặc sau T1, thay vì tự ghép hai snapshot riêng theo hai lần truy vấn. Tuy nhiên, để coi tổng số dư “luôn phải bằng 200”, nghiệp vụ còn phải bảo đảm không có giao dịch nạp/rút hợp lệ nào khác thay đổi tổng.

### Tình huống rollback trong hai session

Nếu Session 1 thực hiện:

~~~sql
BEGIN;

UPDATE accounts
SET balance = 80.00
WHERE id = 1;

ROLLBACK;
~~~

thì một câu SELECT mới ở Session 2 theo PostgreSQL READ COMMITTED sẽ không thấy giá trị 80 chưa commit của T1. Sau rollback, giá trị đã commit của tài khoản 1 vẫn là 100 trong ví dụ đơn lẻ này.

Không dùng ví dụ PostgreSQL để “thử dirty read” bằng `SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED`, vì PostgreSQL xử lý mức đó tương tự READ COMMITTED, không thực hiện dirty read.

## 17. Lịch thực thi và thực tế của MVCC, lock, isolation

Mô hình R/W/C/A giúp biểu diễn thứ tự logic, nhưng cần hiểu các giả định ẩn:

| Mô hình ký hiệu | Trong database thực tế có thể cần bổ sung |
|---|---|
| `R1(A)` | Phiên bản A nào được đọc? Snapshot ở đầu câu lệnh hay đầu transaction? |
| `W1(A)` | T1 đã khóa hàng chưa, có phải chờ transaction khác không? |
| `R1(P)` với P là tập hàng thỏa điều kiện | Tập hàng có thể có phantom khi transaction khác INSERT/DELETE không? |
| `C1` | Commit có thành công không, có bị serialization failure hoặc lỗi kết nối không? |
| `A1` | Engine dùng MVCC/undo/log thế nào để đảm bảo không lộ tác động đã rollback? |
| `W1(A), W2(A)` | Database có cho phép cả hai thao tác xảy ra theo thứ tự đề xuất không, hay khóa/wait/abort một bên? |

Một số điểm thực tế:

**Thứ nhất, lịch ký hiệu không đồng nghĩa thực thi song song vật lý.** Hai transaction có thể chạy xen kẽ trên một CPU hoặc chạy song song trên nhiều core. Điều được phân tích là **thứ tự quan sát được của các operation**, không nhất thiết là số luồng của hệ điều hành.

**Thứ hai, MVCC thay đổi cách đọc.** Một transaction có thể thấy phiên bản A cũ dù một transaction khác đã tạo phiên bản A mới, tùy snapshot; vì vậy việc đọc/ghi xảy ra theo thứ tự vật lý không luôn có nghĩa “đọc thấy lần ghi gần nhất”.

**Thứ ba, mức cô lập có thể chặn hoặc làm transaction thất bại.** Một lịch không conflict-serializable có thể được dùng như phản ví dụ lý thuyết; nhưng khi chạy ở PostgreSQL SERIALIZABLE, engine có thể từ chối một commit và buộc retry thay vì cho cả hai transaction hoàn tất như lịch ấy.

**Thứ tư, rollback chỉ bao phủ phạm vi transaction.** Gửi email, gọi API thanh toán hoặc ghi vào hệ thống ngoài không tự được hoàn tác khi transaction SQL abort. Nếu mô hình cần biểu diễn hệ thống phân tán, phải bổ sung operation của từng tài nguyên và quy tắc phối hợp tương ứng.

## 18. Cách đọc một lịch khi giải bài tập

Khi gặp một chuỗi như:

~~~text
S = R1(X) R2(X) W1(X) C1 W2(X) C2
~~~

nên làm theo trình tự sau:

1. **Tách thao tác theo transaction.** T1 gồm `R1(X), W1(X), C1`; T2 gồm `R2(X), W2(X), C2`.
2. **Xác định thứ tự mỗi transaction.** Kiểm tra xem lịch có giữ thứ tự mà từng chương trình yêu cầu hay không.
3. **Điền giá trị ban đầu và giá trị đọc/ghi.** Nếu T1 và T2 đều đọc X ban đầu rồi tự tính giá trị mới, có thể có lost update. Không được tự giả định `R2(X)` đọc giá trị chưa commit nếu không có thông tin snapshot.
4. **Đánh dấu mọi điểm commit và abort.** Chỉ giá trị của transaction được commit mới thuộc kết quả đã xác nhận.
5. **Xác định các cặp conflict.** Với cùng X, lần lượt so sánh R/W giữa T1 và T2, xác định chiều phụ thuộc.
6. **Vẽ precedence graph khi cần.** Có chu trình hay không? Lịch có conflict-serializable không?
7. **Phân tích phục hồi.** Có ai đọc dữ liệu chưa commit không? Có transaction phụ thuộc commit quá sớm không? Có khả năng cascading rollback hay dirty write không?
8. **Nêu giả định database.** Một lịch có thể khả thi theo lý thuyết nhưng bị chặn, chờ hoặc abort bởi khóa và isolation thực tế.
9. **Đối chiếu invariant nghiệp vụ.** Cơ sở dữ liệu có thể không tự kiểm tra “tổng tiền luôn được bảo toàn”, “luôn còn một bác sĩ trực”, “chỉ bán tối đa N vé”.

Các câu hỏi “có dirty read không?”, “recoverable không?”, “serializable không?” và “đúng nghiệp vụ không?” **không phải cùng một câu hỏi**. Một lịch có thể recoverable nhưng không serializable; một lịch serializable vẫn có thể chạy một transaction lập trình sai nghiệp vụ.

## 19. Bài tập áp dụng

### Bài tập 1: xác định kết cục đã commit

Cho X ban đầu bằng 50:

~~~text
W1(X:=70)  A1  R2(X)  C2
~~~

Với giả định T2 đọc giá trị đã commit sau khi T1 rollback, hãy xác định `R2(X)` trả về bao nhiêu. Vì sao `W1(X:=70)` vẫn được ghi trong lịch mặc dù T1 không commit?

**Gợi ý:** ROLLBACK không xóa thao tác từng xảy ra khỏi lịch; nó loại bỏ tác động chưa commit của transaction khỏi trạng thái được xác nhận.

### Bài tập 2: phân biệt dirty read và non-repeatable read

X ban đầu bằng 10. So sánh hai lịch:

~~~text
S1 = W1(X:=20)  R2(X)=20  A1  A2
S2 = R2(X)=10  W1(X:=20)  C1  R2(X)=20  C2
~~~

Hỏi:

- Lịch nào có **dirty read**?
- Lịch nào có **non-repeatable read**?
- Lịch nào đọc giá trị của T1 trước khi T1 commit?
- Tại sao việc T2 cuối cùng abort ở S1 không xóa đi thực tế là T2 đã đọc dữ liệu chưa commit?

### Bài tập 3: kiểm tra conflict-serializability

Cho:

~~~text
S = R1(A)  R2(B)  W1(B)  W2(A)  C1  C2
~~~

Xác định:

1. Conflict nào tạo cạnh T1 → T2?
2. Conflict nào tạo cạnh T2 → T1?
3. Đồ thị có chu trình không?
4. Kết luận conflict-serializability của lịch là gì?

**Gợi ý:** `R1(A)` đứng trước `W2(A)`, còn `R2(B)` đứng trước `W1(B)`. Mỗi cặp liên quan cùng một mục và có một thao tác ghi.

### Bài tập 4: thiết kế lịch chuyển tiền có khả năng phục hồi

T1 chuyển 20 từ A sang B, T2 đọc A và B để báo cáo tổng. Ban đầu A = B = 100. Hãy xây dựng:

- Một lịch tuần tự hợp lệ, trong đó T2 đọc tổng 200.
- Một lịch xen kẽ theo PostgreSQL READ COMMITTED, trong đó T2 có thể ghép hai snapshot khác nhau và tính ra 220.
- Một lịch mà T1 rollback sau khi đã ghi A, nhưng T2 không bao giờ đọc dữ liệu chưa commit của T1.
- Một cách điều chỉnh transaction của T2 để tránh read skew khi cần nhiều câu SELECT trên PostgreSQL.

**Điểm cốt lõi:** Khi biểu diễn lịch thực thi, phải ghi rõ ai đọc, ai ghi, thao tác nào đứng trước, và mỗi transaction kết thúc bằng commit hay rollback. Từ đó mới có thể lập luận về giá trị được nhìn thấy, phục hồi sau abort, xung đột giữa các transaction và sự tương đương với một thứ tự tuần tự. Không thể kết luận đầy đủ chỉ bằng thứ tự SQL trên giấy nếu chưa xác định snapshot, khóa, isolation và bất biến nghiệp vụ mà hệ thống phải giữ.
