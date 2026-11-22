# Phân loại lịch thực thi và chỉ ra bất thường có thể xảy ra

Khi nhiều transaction chạy xen kẽ, kết quả không chỉ phụ thuộc vào câu SQL của từng transaction mà còn phụ thuộc **thứ tự các thao tác đọc, ghi, commit và rollback**. Một lịch thực thi (schedule) mô tả thứ tự đó. Phân loại lịch giúp xác định transaction có thể đọc dữ liệu chưa commit, ghi đè thay đổi của nhau, nhìn thấy tập dòng không nhất quán, vi phạm bất biến nhiều dòng hoặc tạo ra kết quả không tương đương với bất kỳ thứ tự tuần tự nào.

Một cách phân tích đầy đủ cần xem nhiều khía cạnh riêng biệt:

- **Anomaly dữ liệu:** dirty read, dirty write, lost update, non-repeatable read, phantom read, read skew, write skew và các bất thường liên quan.
- **Khả năng phục hồi:** lịch có recoverable, cascadeless hay strict không; nếu transaction nguồn rollback thì transaction phụ thuộc có phải rollback theo không?
- **Tính tuần tự hóa:** lịch có tương đương một lịch serial không? Có conflict graph chứa chu trình không?
- **Ngữ nghĩa DBMS:** isolation level và cơ chế lock/MVCC của PostgreSQL, MySQL, SQL Server hoặc Oracle có cho phép lịch đó xảy ra không, hay sẽ chặn/hủy một transaction?

Các khái niệm này liên quan nhưng không đồng nghĩa. Một lịch có thể không có dirty read nhưng vẫn có write skew; một lịch có thể strict nhưng không conflict-serializable; một lịch có thể conflict-serializable nhưng không recoverable nếu commit sai thứ tự sau khi đọc dữ liệu chưa commit.

## 1. Ký hiệu lịch thực thi

Ta dùng các ký hiệu phổ biến:

| Ký hiệu | Ý nghĩa |
|---|---|
| `r1(X)` | Transaction T1 đọc dữ liệu X |
| `w1(X)` | Transaction T1 ghi dữ liệu X |
| `c1` | T1 commit |
| `a1` | T1 abort/rollback |
| `r2(X)` | Transaction T2 đọc X |
| `w2(X)` | Transaction T2 ghi X |

Ví dụ:

```text
S = r1(X), w1(X), r2(X), c1, c2
```

Lịch trên cho biết T1 đọc X, ghi X; sau đó T2 đọc X; cuối cùng T1 và T2 commit. Các thao tác của hai transaction được xen kẽ, nhưng thứ tự nội bộ của từng transaction vẫn phải được giữ.

### 1.1. Lịch serial và lịch interleaved

**Serial schedule** chạy trọn vẹn một transaction rồi mới chạy transaction tiếp theo:

```text
T1: r1(X) -> w1(X) -> c1
T2:                         r2(X) -> w2(X) -> c2
```

Lịch interleaved xen kẽ thao tác của nhiều transaction:

```text
T1: r1(X) -------- w1(X) ---------------- c1
T2:       r2(Y) -------- w2(Y) ---------------- c2
```

Interleaving tự nó không phải lỗi. Mục tiêu của concurrency control là cho phép các transaction chạy đồng thời nhưng vẫn bảo đảm kết quả tương đương một lịch tuần tự hợp lệ, đồng thời duy trì quy tắc phục hồi.

### 1.2. Đọc từ transaction nào?

Khi phân tích lịch, hãy ghi rõ mỗi thao tác đọc lấy giá trị từ đâu:

- Giá trị ban đầu trước khi các transaction trong lịch ghi.
- Giá trị do transaction nào ghi.
- Giá trị đó đã commit hay chưa tại thời điểm được đọc.

Ví dụ `w1(X=20), r2(X=20)` có nghĩa T2 đọc giá trị 20 do T1 vừa ghi. Nếu `c1` chưa xảy ra trước `r2(X)`, đây là dirty read. Nếu T1 đã commit trước thao tác đọc, T2 đọc một giá trị đã commit.

## 2. Quy trình phân loại một lịch

Không nên nhìn tên anomaly rồi đoán ngay. Hãy phân tích lịch theo một trình tự cố định:

1. **Tách transaction:** liệt kê thao tác của từng T1, T2, T3 và giữ đúng thứ tự nội bộ.
2. **Theo dõi nguồn dữ liệu:** xác định mỗi lần đọc lấy giá trị ban đầu hay giá trị do transaction khác ghi.
3. **Kiểm tra commit/abort:** tại thời điểm đọc, giá trị nguồn đã commit chưa? Transaction đọc có commit trước transaction ghi nguồn không?
4. **Tìm xung đột ghi:** hai thao tác từ transaction khác nhau xung đột nếu cùng truy cập một item và ít nhất một thao tác là ghi.
5. **Kiểm tra lặp lại và predicate:** một transaction đọc lại cùng item hoặc chạy lại cùng điều kiện có thấy kết quả khác không?
6. **Kiểm tra bất biến nghiệp vụ:** các transaction có đọc nhiều dòng rồi ghi những dòng khác nhau làm hỏng một quy tắc tổng thể không?
7. **Lập conflict graph:** thêm cạnh theo thứ tự các thao tác xung đột; chu trình cho biết lịch không conflict-serializable.
8. **Phân loại khả năng phục hồi:** kiểm tra dirty read, thứ tự commit và dirty write để xác định recoverable/cascadeless/strict.
9. **Đối chiếu isolation level của DBMS:** xác định lịch được phép, bị khóa chặn hay một transaction phải abort.

Một schedule có thể có nhiều đặc điểm cùng lúc. Ví dụ, lost update thường đồng thời làm lịch không conflict-serializable; dirty read có thể xuất hiện trong một lịch vẫn conflict-serializable nhưng không strict.

## 3. Conflict và conflict graph

Hai thao tác thuộc hai transaction khác nhau là **conflict** khi chúng truy cập cùng một dữ liệu và ít nhất một thao tác là ghi.

| Cặp thao tác | Có conflict? | Lý do |
|---|---:|---|
| `r1(X)` và `r2(X)` | Không | Cả hai đều đọc |
| `r1(X)` và `w2(X)` | Có | Đọc/ghi cùng X |
| `w1(X)` và `r2(X)` | Có | Ghi/đọc cùng X |
| `w1(X)` và `w2(X)` | Có | Ghi/ghi cùng X |
| `r1(X)` và `w2(Y)` | Không | Hai item khác nhau |

Thứ tự của các thao tác conflict không thể đảo tùy ý mà vẫn giữ nguyên conflict equivalence. Dựa trên thứ tự đó, ta lập **precedence graph** (còn gọi là serialization graph):

- Mỗi transaction là một node.
- Nếu thao tác của Ti trên X xảy ra trước thao tác conflict của Tj trên X, thêm cạnh `Ti -> Tj`.
- Nếu một cặp transaction có nhiều conflict cùng chiều, vẫn chỉ cần một cạnh cùng chiều.
- Nếu có cạnh theo cả hai chiều, graph có chu trình.

**Quy tắc:** lịch conflict-serializable khi và chỉ khi precedence graph không có chu trình. Nếu graph không chu trình, một thứ tự topological là thứ tự serial tương đương.

### 3.1. Ví dụ graph không có chu trình

```text
S = r1(X), w1(X), r2(X), w2(X), c1, c2
```

Các conflict trên X đều có thao tác của T1 đứng trước thao tác của T2:

- `w1(X)` trước `r2(X)` tạo cạnh `T1 -> T2`.
- `w1(X)` trước `w2(X)` tạo cùng cạnh `T1 -> T2`.

Graph:

```text
T1 -----> T2
```

Không có chu trình. Lịch conflict-serializable và tương đương thứ tự serial T1 rồi T2.

### 3.2. Ví dụ graph có chu trình

```text
S = r1(X), r2(X), w1(X), w2(X), c1, c2
```

- `r1(X)` trước `w2(X)` tạo cạnh `T1 -> T2`.
- `r2(X)` trước `w1(X)` tạo cạnh `T2 -> T1`.

Graph:

```text
T1 -----> T2
 ^         |
 |_________|
```

Có chu trình `T1 -> T2 -> T1`, nên lịch không conflict-serializable. Đây là dạng lịch có thể tạo lost update nếu hai transaction cùng tính toán dựa trên giá trị đã đọc.

## 4. Dirty read: đọc dữ liệu chưa commit

Dirty read xảy ra khi T2 đọc giá trị mà T1 đã ghi nhưng chưa commit. Nếu T1 rollback, giá trị T2 đã đọc chưa từng trở thành dữ liệu đã commit.

```text
Ban đầu X = 10

T1: w1(X = 20) ---------------- a1
T2:            r2(X = 20) -------- c2
```

T2 đọc giá trị 20 từ T1 trước khi T1 commit. Sau đó T2 commit, nhưng T1 abort. T2 đã commit một quyết định dựa trên dữ liệu bị hủy.

### 4.1. Hậu quả

- T2 có thể ghi kết quả phụ thuộc vào giá trị 20 dù database quay về giá trị 10.
- Nếu T2 đã tạo đơn hàng, tính phí hoặc phát thông báo, rollback database của T1 không tự đảo tác dụng phụ của T2.
- Nếu nhiều transaction tiếp tục đọc giá trị chưa commit, một lần rollback có thể buộc nhiều transaction phụ thuộc phải rollback theo (cascading abort).

### 4.2. Cách nhận diện

Tìm cặp `w1(X)` rồi `r2(X)` xảy ra trước `c1`. Nếu T1 chưa commit tại thời điểm T2 đọc, có dirty read. Chỉ thấy `r2(X)` sau `c1` thì không phải dirty read.

`READ UNCOMMITTED` có thể cho phép dirty read ở các DBMS hỗ trợ đúng semantics này. PostgreSQL chấp nhận cú pháp `READ UNCOMMITTED` nhưng thực hiện như `READ COMMITTED`, nên không cung cấp dirty read theo nghĩa trên. Các engine khác có thể có hành vi khác.

## 5. Dirty write: ghi đè dữ liệu chưa commit

Dirty write xảy ra khi T2 ghi lên cùng item X trong khi lần ghi trước của T1 vẫn chưa commit hoặc abort.

```text
T1: w1(X = 20) ---------------- a1
T2:             w2(X = 30) -------- c2
```

T2 ghi X khi phiên bản do T1 tạo vẫn chưa có kết quả commit. Nếu T1 rollback, hệ thống phải xử lý một lịch ghi chồng lên phiên bản chưa hoàn tất; recovery có thể trở nên không nhất quán nếu không có cơ chế điều phối đúng.

Strict schedule cấm dirty write: sau khi Ti ghi X, transaction khác không được đọc hoặc ghi X cho đến khi Ti commit hoặc abort. Các DBMS giao dịch thông thường dùng khóa hoặc cơ chế MVCC/locking để ngăn các dirty write nguy hiểm này.

Dirty write khác dirty read:

- Dirty read: transaction khác **đọc** giá trị chưa commit.
- Dirty write: transaction khác **ghi** lên item đang có lần ghi chưa commit.

Một lịch không có dirty read vẫn có thể có dirty write; phải kiểm tra riêng các thao tác ghi.

## 6. Lost update: cập nhật của một transaction bị ghi đè

Lost update xảy ra khi hai transaction cùng đọc một giá trị cũ, tính giá trị mới độc lập rồi ghi lại. Lần ghi sau có thể làm mất thay đổi của lần ghi trước.

Giả sử X ban đầu bằng 100. T1 trừ 10; T2 trừ 20:

```text
T1: r1(X = 100) -------- w1(X = 90) -------- c1
T2:       r2(X = 100) ---------------- w2(X = 80) -- c2
```

T2 tính `100 - 20 = 80` từ dữ liệu cũ và ghi 80 sau khi T1 đã ghi 90. Kết quả cuối là 80, trong khi nếu cả hai phép trừ đều được áp dụng thì phải là 70.

### 6.1. Phân tích conflict graph

- `r1(X)` trước `w2(X)` tạo `T1 -> T2`.
- `r2(X)` trước `w1(X)` tạo `T2 -> T1`.

Graph có chu trình nên lịch không conflict-serializable.

### 6.2. Cách ngăn

- Dùng phép cập nhật nguyên tử như `SET balance = balance - :amount` để database áp dụng lên giá trị hiện tại.
- Dùng `SELECT ... FOR UPDATE` hoặc locking read tương đương trước khi đọc dữ liệu để tính.
- Dùng optimistic version: `UPDATE ... WHERE version = :old_version`; nếu không có dòng nào được cập nhật thì đọc lại và tính lại.
- Với bất biến nhiều dòng, dùng isolation/locking đủ mạnh cho toàn bộ tập dữ liệu tham gia.

Không nên kết luận mọi `READ COMMITTED` đều cho phép hoặc mọi `REPEATABLE READ` đều ngăn lost update. Một số engine phát hiện write conflict và abort transaction; một số lịch ghi giá trị tuyệt đối từ snapshot cũ vẫn có thể tạo lost update. Cần xét DBMS, câu SQL và isolation cụ thể.

## 7. Non-repeatable read: cùng một dòng cho kết quả khác nhau

Non-repeatable read xảy ra khi một transaction đọc cùng một item hai lần nhưng lần đọc thứ hai thấy giá trị khác vì transaction khác đã cập nhật và commit ở giữa.

```text
T1: r1(X = 10) ---------------------- r1(X = 20) -- c1
T2:       w2(X = 20) -- c2
```

T1 đọc X bằng 10, T2 đổi X thành 20 và commit, sau đó T1 đọc lại X và thấy 20. T1 không còn có cùng kết quả cho hai lần đọc cùng một item.

Conflict graph có:

- `r1(X)` trước `w2(X)`: `T1 -> T2`.
- `w2(X)` trước lần `r1(X)` thứ hai: `T2 -> T1`.

Có chu trình. Đây là lịch không conflict-serializable.

`READ COMMITTED` thường cho phép non-repeatable read vì mỗi statement có thể dùng snapshot mới. `REPEATABLE READ` hoặc transaction-level snapshot thường ngăn transaction nhìn thấy giá trị thay đổi của cùng một dòng trong suốt transaction; chi tiết phụ thuộc DBMS.

## 8. Phantom read: tập dòng thỏa predicate thay đổi

Phantom read xảy ra khi một transaction chạy lại truy vấn theo cùng điều kiện và nhận được một tập dòng khác do transaction khác insert, delete hoặc cập nhật dòng để nó bắt đầu/kết thúc thỏa điều kiện.

Giả sử T1 đếm đơn hàng có `amount >= 100`:

```text
T1: SELECT ... WHERE amount >= 100  -> 3 rows
T2: INSERT order(amount = 150); COMMIT
T1: SELECT ... WHERE amount >= 100  -> 4 rows
```

T1 không nhất thiết đọc lại một dòng đã tồn tại; nó thấy thêm một dòng mới thỏa predicate. Vì vậy phantom khác non-repeatable read ở phạm vi tập kết quả/predicate.

Ký hiệu trừu tượng:

```text
r1(P)       -- đọc tập dòng thỏa predicate P
T2: w2(new row satisfying P), c2
r1(P)       -- chạy lại P và thấy thêm dòng
```

`REPEATABLE READ` theo nghĩa ANSI cổ điển không nhất thiết ngăn phantom. `SERIALIZABLE` cần bảo vệ predicate/range để lịch kết quả tương đương serial. Cách thực hiện có thể là key-range lock, predicate lock hoặc cơ chế phát hiện serialization anomaly tùy DBMS.

## 9. Read skew / inconsistent analysis: đọc một trạng thái kết hợp không tồn tại

Read skew xảy ra khi một transaction đọc các phần dữ liệu liên quan tại những thời điểm khác nhau, khiến kết hợp các giá trị tạo ra một trạng thái chưa từng tồn tại như một snapshot nhất quán.

Ví dụ A và B ban đầu có 100 mỗi tài khoản. T2 chuyển 10 từ A sang B. Tổng số dư phải luôn là 200:

```text
T1: r1(A = 100) -------------------------------- r1(B = 110)
T2:       r2(A = 100), w2(A = 90), w2(B = 110), c2
```

T1 đọc A trước khi T2 commit nên thấy 100. Sau đó T2 commit. T1 đọc B sau commit nên thấy 110. T1 cộng được 210, dù tổng số dư đúng trước và sau chuyển đều là 200.

Điều kiện để xuất hiện:

- T1 đọc nhiều item liên quan trong các statement có snapshot khác nhau.
- T2 cập nhật các item theo cùng một nghiệp vụ và commit giữa các lần đọc của T1.
- T1 không có snapshot ổn định bao trùm toàn bộ các lần đọc.

`READ COMMITTED` có thể cho phép lịch này vì từng statement nhìn snapshot riêng. Transaction-level snapshot như PostgreSQL `REPEATABLE READ` hoặc SQL Server `SNAPSHOT` thường ngăn T1 trộn giá trị trước/sau commit trong ví dụ này.

## 10. Write skew: ghi các dòng khác nhau nhưng phá vỡ bất biến chung

Write skew xảy ra khi hai transaction cùng đọc một tập dữ liệu để kiểm tra một quy tắc, sau đó ghi các dòng khác nhau. Vì không ghi cùng một dòng nên không có write-write conflict trực tiếp; cả hai có thể commit nhưng trạng thái tổng thể vi phạm bất biến.

Ví dụ quy tắc trực ca: luôn phải có ít nhất một trong hai bác sĩ A hoặc B đang trực. Ban đầu cả hai đều trực (`on_call = true`). T1 muốn tắt ca A, T2 muốn tắt ca B.

```text
T1: r1(A = on), r1(B = on) -------- w1(A = off) -- c1
T2:       r2(A = on), r2(B = on) -------- w2(B = off) -- c2
```

Cả T1 và T2 đều thấy người kia vẫn trực, nên mỗi transaction kết luận có thể tắt ca của mình. T1 chỉ ghi A; T2 chỉ ghi B. Sau khi cả hai commit, A và B đều off, vi phạm quy tắc phải có ít nhất một bác sĩ trực.

### 10.1. Conflict graph

- `r1(B)` trước `w2(B)`: cạnh `T1 -> T2`.
- `r2(A)` trước `w1(A)`: cạnh `T2 -> T1`.

Graph có chu trình. Đây là serialization anomaly dù hai transaction ghi hai dòng khác nhau.

### 10.2. Vì sao snapshot isolation vẫn có thể cho write skew?

Snapshot isolation thường phát hiện hai transaction cùng ghi một dòng và hủy một transaction do write-write conflict. Trong ví dụ này, T1 ghi A và T2 ghi B; hai dòng khác nhau nên không có xung đột ghi trực tiếp. Mỗi transaction đọc cùng snapshot cũ và có thể commit.

Để bảo vệ bất biến, có thể:

- Dùng `SERIALIZABLE` và retry transaction bị báo serialization failure.
- Khóa một dòng guard đại diện cho quy tắc trực ca trước khi đọc/ghi.
- Mô hình hóa quy tắc thành constraint hoặc cập nhật nguyên tử nếu DBMS/schema cho phép.
- Dùng một hàng tổng hợp/bộ đếm được cập nhật có điều kiện để biến bất biến thành xung đột trên cùng resource.

Không nên chỉ khóa dòng mà mỗi transaction định ghi nếu quy tắc phụ thuộc vào nhiều dòng; cần khóa resource đại diện cho toàn bộ bất biến.

## 11. Recoverable, cascadeless và strict schedule

Serializability trả lời câu hỏi “kết quả có tương đương một thứ tự tuần tự không?”. Recoverability trả lời câu hỏi “nếu một transaction đọc dữ liệu do transaction khác ghi, thứ tự commit có bảo đảm không để transaction phụ thuộc commit trước nguồn không?”. Đây là hai trục phân tích riêng.

### 11.1. Recoverable schedule

Một lịch recoverable bảo đảm: nếu Tj đọc giá trị do Ti ghi, Ti phải commit trước khi Tj commit. Nếu Ti abort, Tj chưa được commit một kết quả phụ thuộc vào Ti.

Ví dụ:

```text
T1: w1(X = 20) -------- c1
T2:       r2(X = 20) -------- c2
```

T2 đọc giá trị chưa commit của T1, nên có dirty read. Nhưng T1 commit trước T2; lịch vẫn recoverable. Nếu T1 abort thay vì commit, T2 chưa commit và có thể rollback theo.

### 11.2. Non-recoverable schedule

```text
T1: w1(X = 20) ---------------- a1
T2:       r2(X = 20) -- c2
```

T2 commit trước khi T1 kết thúc. Nếu T1 abort, T2 đã commit một kết quả dựa trên dữ liệu bị hủy. Lịch không recoverable.

### 11.3. Cascadeless schedule

Một lịch cascadeless yêu cầu transaction chỉ đọc giá trị do transaction khác ghi sau khi transaction ghi đã commit. Vì vậy, không có dirty read và không cần cascading rollback do đọc dữ liệu chưa commit.

```text
T1: w1(X = 20) -- c1
T2:                    r2(X = 20) -- c2
```

Lịch cascadeless luôn recoverable. Chiều ngược lại không đúng: lịch recoverable vẫn có thể cho phép dirty read miễn transaction đọc chỉ commit sau transaction nguồn.

### 11.4. Strict schedule

Một lịch strict yêu cầu nếu Ti đã ghi X thì transaction khác không được đọc hoặc ghi X cho đến khi Ti commit hoặc abort. Strict ngăn cả dirty read và dirty write.

```text
T1: w1(X = 20) -------- c1
T2:                          r2(X = 20), w2(X = 30) -- c2
```

T2 chỉ đọc/ghi X sau khi T1 commit. Lịch strict, cascadeless và recoverable.

Quan hệ bao hàm:

```text
Strict  =>  Cascadeless  =>  Recoverable
```

Chiều ngược lại không đúng. Một lịch recoverable có thể chứa dirty read; một lịch cascadeless có thể vẫn cho dirty write nếu không có quy tắc strict.

## 12. Strict không đồng nghĩa conflict-serializable

Đây là điểm dễ nhầm khi phân loại. Strict kiểm soát việc đọc/ghi item chưa commit; conflict serializability kiểm tra chu trình phụ thuộc giữa transaction. Một lịch có thể strict nhưng vẫn không conflict-serializable.

Xét lại write skew với hai item A và B:

```text
S = r1(A), r1(B), r2(A), r2(B), w1(A), w2(B), c1, c2
```

Sau `w1(A)`, T2 không đọc/ghi A nữa. Sau `w2(B)`, T1 không đọc/ghi B nữa. Không có transaction nào đọc hoặc ghi item do transaction khác ghi trước khi writer commit; vì vậy lịch strict theo định nghĩa item-level.

Nhưng graph có:

- `r1(B)` trước `w2(B)`: `T1 -> T2`.
- `r2(A)` trước `w1(A)`: `T2 -> T1`.

Có chu trình, nên lịch không conflict-serializable. Điều này giải thích vì sao chỉ ngăn dirty read/dirty write vẫn chưa đủ để bảo vệ mọi bất biến nhiều dòng.

## 13. Conflict-serializable và view-serializable

Conflict-serializable là một lớp con của view-serializable. View equivalence xem xét:

- Transaction nào đọc giá trị ban đầu.
- Mỗi thao tác đọc lấy giá trị do transaction nào ghi.
- Transaction nào là final writer của mỗi item.

Một số lịch có blind write có thể view-serializable nhưng không conflict-serializable. Ví dụ:

```text
S = w1(X), w2(X), w1(X), c2, c1
```

Không có thao tác đọc. Final writer của X là T1. Lịch view-equivalent với thứ tự serial T2 rồi T1 vì cuối cùng T1 ghi X. Tuy nhiên, conflict graph có `T1 -> T2` do lần `w1(X)` đầu trước `w2(X)`, và `T2 -> T1` do `w2(X)` trước lần `w1(X)` cuối. Graph có chu trình nên không conflict-serializable.

Trong thực hành, conflict-serializability được dùng phổ biến vì có thuật toán kiểm tra graph đơn giản. View-serializability tổng quát hơn nhưng khó kiểm tra hơn. Không nên nhầm “graph có chu trình” với “không view-serializable”; kết luận trực tiếp là không conflict-serializable.

## 14. Phân loại lịch mẫu

Các ví dụ sau dùng giá trị X ban đầu là 10 nếu không ghi chú khác. Mục tiêu là luyện cách đọc lịch, không giả định mọi DBMS đều cho phép mọi interleaving.

### Lịch A

```text
S_A = r1(X), w1(X), c1, r2(X), w2(X), c2
```

Phân tích:

- T2 chỉ đọc X sau khi T1 commit.
- Không dirty read hoặc dirty write.
- Các conflict đều theo chiều T1 trước T2; graph không có chu trình.
- Transaction chạy nối tiếp, đây là serial schedule.

Kết luận: serial, conflict-serializable, strict, cascadeless và recoverable.

### Lịch B

```text
S_B = w1(X = 20), r2(X = 20), c1, c2
```

Phân tích:

- T2 đọc giá trị do T1 ghi trước khi T1 commit: dirty read.
- T1 commit trước T2 nên lịch recoverable.
- Không cascadeless vì có dirty read; không strict vì T2 đọc X khi T1 chưa commit.
- Conflict graph chỉ có `T1 -> T2`, nên conflict-serializable.

Kết luận: dirty read; recoverable nhưng không cascadeless và không strict; conflict-serializable.

### Lịch C

```text
S_C = w1(X = 20), r2(X = 20), c2, a1
```

Phân tích:

- T2 đọc giá trị chưa commit từ T1: dirty read.
- T2 commit trước T1; sau đó T1 abort.
- T2 đã commit kết quả phụ thuộc dữ liệu bị rollback.
- Graph có cạnh `T1 -> T2`, không chu trình, nhưng điều đó không làm lịch recoverable.

Kết luận: dirty read, non-recoverable, không cascadeless, không strict; vẫn conflict-serializable theo phép kiểm tra conflict.

### Lịch D

```text
S_D = r1(X = 10), r2(X = 10), w1(X = 5), c1, w2(X = 7), c2
```

Phân tích:

- Cả hai đọc cùng giá trị cũ 10.
- T1 ghi 5 và commit; sau đó T2 ghi 7 dựa trên phép tính từ 10.
- T2 ghi đè kết quả T1; nếu hai phép biến đổi đều phải được áp dụng thì kết quả đúng khác 7.
- Có cạnh `T1 -> T2` và `T2 -> T1`.

Kết luận: lost update và không conflict-serializable. Lịch vẫn strict, cascadeless và recoverable vì T2 chỉ ghi sau khi T1 commit. Không có dirty read hoặc dirty write; việc không có dirty read/write không loại bỏ lost update.

### Lịch E

```text
S_E = r1(X = 10), w2(X = 20), c2, r1(X = 20), c1
```

Phân tích:

- T1 đọc X hai lần và thấy 10 rồi 20.
- T2 cập nhật và commit giữa hai lần đọc.
- Có cạnh `T1 -> T2` từ lần đọc đầu và `T2 -> T1` từ lần đọc sau.

Kết luận: non-repeatable read và không conflict-serializable.

### Lịch F

```text
S_F = r1(P), w2(new_row_matching_P), c2, r1(P), c1
```

Phân tích:

- T1 chạy cùng predicate P hai lần.
- T2 thêm một dòng thỏa P và commit ở giữa.
- Lần đọc sau của T1 thấy thêm một dòng phantom.

Kết luận: phantom read. Cần predicate/range protection hoặc serializable semantics phù hợp để ngăn.

### Lịch G

```text
S_G = r1(A), r1(B), r2(A), r2(B), w1(A), w2(B), c1, c2
```

Giả sử A và B ban đầu đều `on_call = true`; mỗi transaction tắt một dòng sau khi thấy cả hai đang trực.

Phân tích:

- T1 và T2 đọc cùng snapshot có cả A và B đang trực.
- T1 chỉ ghi A; T2 chỉ ghi B.
- Không có dirty read/write trên cùng item.
- Graph có `T1 -> T2` và `T2 -> T1`.

Kết luận: write skew; lịch strict nhưng không conflict-serializable. Snapshot isolation có thể cho phép nếu không có write-write conflict trên cùng dòng.

### Lịch H

```text
S_H = r1(A), r2(A), w1(A), w2(A), c1, c2
```

Phân tích:

- T2 đọc A trước khi T1 ghi, nên không phải dirty read.
- Hai transaction ghi cùng A; các thao tác xung đột tạo hai chiều phụ thuộc.
- T2 ghi sau từ một giá trị đọc cũ có thể làm mất cập nhật T1; vì `w2(A)` xảy ra trước `c1`, lịch còn có dirty write.

Kết luận: lost update/stale overwrite và dirty write; không conflict-serializable. Không có dirty read trong lịch đã cho.

### Lịch I

```text
S_I = w1(X = 20), w2(X = 30), a1, c2
```

Phân tích:

- T2 ghi X khi lần ghi của T1 chưa commit/abort: dirty write.
- Lịch vi phạm strictness.
- Engine strict không cho phép T2 ghi chồng lên X theo thứ tự này; T2 phải chờ T1 kết thúc hoặc lịch được điều phối khác.

Kết luận: dirty write, không strict. Không cần có thao tác đọc để phát hiện dirty write.

### Lịch J

```text
S_J = w1(X = 20), r2(X = 20), c1, r2(X = 20), c2
```

Phân tích:

- Lần đọc đầu của T2 xảy ra trước commit T1: dirty read.
- T1 commit trước T2: lịch recoverable.
- T2 đọc lại cùng giá trị sau commit; không nhất thiết có non-repeatable read vì cả hai lần đều lấy giá trị 20.
- Không cascadeless/strict vì lần đọc đầu là dirty read.

Kết luận: dirty read nhưng recoverable; không cascadeless, không strict. Conflict graph chỉ có `T1 -> T2`, nên conflict-serializable.

## 15. Bảng tổng hợp các bất thường

| Anomaly | Dấu hiệu trong lịch | Rủi ro |
|---|---|---|
| Dirty read | `rj(X)` đọc giá trị do `wi(X)` ghi trước `ci` | Đọc dữ liệu có thể rollback |
| Dirty write | `wj(X)` xảy ra trước khi `Ti` commit/abort sau `wi(X)` | Ghi chồng lên phiên bản chưa hoàn tất, recovery phức tạp |
| Lost update | Hai transaction đọc cùng giá trị cũ rồi ghi các kết quả dựa trên giá trị đó | Mất một thay đổi |
| Non-repeatable read | Cùng transaction đọc lại cùng X và thấy giá trị khác sau commit của writer | Một transaction không có góc nhìn ổn định trên item |
| Phantom read | Cùng predicate trả về tập dòng khác sau transaction khác commit | Kết quả truy vấn tập hợp thay đổi |
| Read skew | Đọc các item liên quan từ các snapshot khác thời điểm | Kết hợp dữ liệu tạo trạng thái không nhất quán |
| Write skew | Cùng đọc invariant, sau đó ghi các dòng khác nhau làm invariant sai | Vi phạm quy tắc nhiều dòng dù không có write-write conflict |
| Cascading abort | Transaction đọc dữ liệu chưa commit; nguồn abort kéo theo transaction phụ thuộc | Rollback lan truyền và tăng chi phí phục hồi |
| Non-recoverable commit | Transaction đọc dữ liệu chưa commit rồi commit trước transaction nguồn | Dữ liệu đã commit phụ thuộc vào giao dịch bị hủy |

Một lịch có thể chứa nhiều anomaly. Ví dụ dirty read có thể dẫn đến cascading abort; lost update thường tạo chu trình conflict graph; write skew có thể xảy ra mà không có dirty read hay dirty write.

## 16. Recoverability không thay thế serializability

Hãy xem lịch:

```text
S = w1(X), r2(X), c1, c2
```

Lịch recoverable nhưng có dirty read. Nó conflict-serializable theo thứ tự T1 rồi T2. Tuy nhiên, dirty read có thể khiến T2 phải rollback nếu T1 abort trước commit. Vì vậy, conflict-serializable không tự động đồng nghĩa cascadeless hoặc strict.

Ngược lại, lịch write skew ở phần trên strict và recoverable nhưng không conflict-serializable. Điều này cho thấy:

- Recoverability bảo vệ thứ tự commit của các transaction có quan hệ đọc-từ.
- Strictness ngăn đọc/ghi một item đang được transaction khác ghi chưa commit.
- Serializability bảo đảm kết quả tương đương một thứ tự chạy tuần tự.

Một hệ thống cần cả ba loại bảo đảm phù hợp với nghiệp vụ. Chọn isolation level chỉ dựa trên việc “không thấy dirty read” là chưa đủ.

## 17. Liên hệ với isolation level của DBMS

Các anomaly là cách mô tả hành vi lịch. Isolation level và concurrency control quyết định engine có cho phép lịch xảy ra, chặn một thao tác, hoặc abort một transaction.

| Isolation / cơ chế | Dirty read | Non-repeatable read / phantom | Write skew / serialization anomaly |
|---|---|---|---|
| `READ UNCOMMITTED` theo semantics cho phép dirty read | Có thể xảy ra | Có thể xảy ra | Có thể xảy ra |
| `READ COMMITTED` | Thường bị ngăn | Có thể xảy ra | Có thể xảy ra |
| `REPEATABLE READ` theo chuẩn SQL cổ điển | Bị ngăn | Non-repeatable read bị ngăn; phantom có thể còn | Không nhất thiết ngăn mọi write skew |
| Snapshot isolation | Bị ngăn | Snapshot ổn định trong phạm vi transaction | Có thể cho write skew |
| `SERIALIZABLE` | Bị ngăn | Ngăn anomaly làm lịch không serializable | Ngăn serialization anomaly; có thể abort/retry |

Bảng này là định hướng khái niệm, không phải ma trận hành vi chính xác cho mọi DBMS. Ví dụ:

- PostgreSQL `READ UNCOMMITTED` hoạt động như `READ COMMITTED`; PostgreSQL `REPEATABLE READ` dựa trên snapshot isolation và ngăn phantom theo snapshot, nhưng vẫn có thể có write skew.
- MySQL InnoDB `REPEATABLE READ` dùng consistent read snapshot và locking read/range lock có hành vi khác nhau; cần phân biệt `SELECT` thông thường với `SELECT ... FOR UPDATE`.
- SQL Server `READ COMMITTED` có thể dùng locking hoặc RCSI tùy database setting; `SNAPSHOT` có update conflict detection; `SERIALIZABLE` dùng range protection phù hợp.
- Oracle `READ COMMITTED` dùng statement-level read consistency; `SERIALIZABLE`/read-only transaction có semantics snapshot khác và có thể trả lỗi serialization hoặc snapshot-related errors theo tình huống.

Đừng kết luận một lịch chắc chắn xảy ra chỉ từ tên isolation level. Hãy đọc tài liệu phiên bản engine, loại read (consistent read hay locking read), câu SQL, constraint và cấu hình thực tế.

## 18. Cách lập conflict graph từng bước

Xét lịch:

```text
S = r1(A), w2(A), r2(B), w3(B), r3(C), w1(C), c1, c2, c3
```

Ta làm như sau:

1. Liệt kê transaction: T1, T2, T3.
2. Với item A: `r1(A)` trước `w2(A)` nên thêm `T1 -> T2`.
3. Với item B: `r2(B)` trước `w3(B)` nên thêm `T2 -> T3`.
4. Với item C: `r3(C)` trước `w1(C)` nên thêm `T3 -> T1`.
5. Graph:

```text
T1 -----> T2 -----> T3
 ^                    |
 |____________________|
```

Có chu trình `T1 -> T2 -> T3 -> T1`; lịch không conflict-serializable.

Khi làm bài, đừng tạo cạnh chỉ vì hai transaction có thao tác gần nhau. Phải có cùng item và ít nhất một thao tác ghi. Đừng tạo cạnh theo thứ tự commit; cạnh được tạo từ thứ tự thao tác conflict trong lịch.

## 19. Phân biệt conflict với dependency nghiệp vụ

Conflict graph cơ bản xét thao tác đọc/ghi trên cùng item. Nhưng một bất biến nghiệp vụ có thể phụ thuộc vào nhiều dòng hoặc một predicate. Write skew là ví dụ: hai transaction ghi các dòng khác nhau nhưng quyết định của chúng phụ thuộc vào tập dữ liệu chung.

Do đó, khi phân tích ứng dụng:

- Xác định item ở mức dữ liệu thực tế: một row, một key, một predicate hoặc một resource guard.
- Xác định invariant có liên quan nhiều item không.
- Kiểm tra việc khóa từng row có đủ bảo vệ invariant không.
- Nếu cần, biến invariant thành xung đột có thể điều phối: guard row, unique/exclusion constraint, conditional aggregate update hoặc serializable transaction.

Một conflict graph trên các read/write item đơn giản giúp phát hiện nhiều anomaly, nhưng không thay thế việc hiểu quy tắc nghiệp vụ và phạm vi predicate.

## 20. Câu hỏi luyện tập

Với mỗi lịch dưới đây, hãy xác định: anomaly (nếu có), recoverable/cascadeless/strict, conflict serializability và cạnh của precedence graph.

### Bài 1

```text
S1 = r1(X), w1(X), c1, r2(X), c2
```

### Bài 2

```text
S2 = w1(X), r2(X), c2, c1
```

### Bài 3

```text
S3 = r1(X), r2(X), w2(X), c2, r1(X), c1
```

### Bài 4

```text
S4 = r1(A), r1(B), r2(A), r2(B), w1(A), w2(B), c1, c2
```

Giả sử invariant là `A + B` phải không đổi.

### Bài 5

```text
S5 = w1(X), w2(X), a1, c2
```

### Bài 6

```text
S6 = r1(X), r2(X), w1(X), w2(X), c1, c2
```

## 21. Đáp án gợi ý

### Bài 1

- T2 đọc sau khi T1 commit.
- Không dirty read/write, không lost update.
- Graph có cạnh `T1 -> T2`, không chu trình.
- Serial, strict, cascadeless, recoverable và conflict-serializable.

### Bài 2

- T2 đọc giá trị do T1 ghi khi T1 chưa commit: dirty read.
- T2 commit trước T1 nên non-recoverable.
- Không cascadeless, không strict.
- Graph có `T1 -> T2`, không chu trình; lịch vẫn conflict-serializable.
- Nếu T1 abort, T2 đã commit kết quả dựa trên giá trị bị hủy.

### Bài 3

- T1 đọc X lần đầu, T2 cập nhật và commit, T1 đọc lại thấy giá trị mới: non-repeatable read.
- Graph có `T1 -> T2` từ lần đọc đầu và `T2 -> T1` từ lần đọc sau.
- Có chu trình nên không conflict-serializable.
- Không có dirty read: lần đọc đầu của T1 lấy giá trị ban đầu, còn lần đọc sau xảy ra sau khi T2 commit.
- Lịch strict vì T1 chỉ đọc lại X sau khi T2 đã commit; do đó lịch cũng cascadeless và recoverable.

### Bài 4

- T1 và T2 đọc cùng snapshot, ghi hai item khác nhau.
- Không dirty read/write; lịch strict, cascadeless và recoverable.
- Graph có `T1 -> T2` từ `r1(B)` trước `w2(B)` và `T2 -> T1` từ `r2(A)` trước `w1(A)`.
- Có chu trình; không conflict-serializable.
- Nếu mỗi transaction tắt một phía của invariant hoặc chuyển giá trị tương ứng, trạng thái cuối có thể vi phạm `A + B` hoặc quy tắc nhiều dòng. Đây là write skew.

### Bài 5

- T2 ghi X trước khi T1 kết thúc: dirty write.
- Không strict.
- Không có thao tác đọc nên không có dirty read; cần xem recovery semantics để xử lý abort.
- Graph chỉ có cạnh `T1 -> T2` vì `w1(X)` xảy ra trước `w2(X)`; không có chu trình nên conflict-serializable.
- Không có thao tác đọc nên lịch recoverable và cascadeless theo định nghĩa đọc-từ; lịch vẫn không strict vì có dirty write.

### Bài 6

- Hai transaction cùng đọc X trước khi ghi.
- `w1(X)` trước `w2(X)` và các lần đọc trước các lần ghi tạo phụ thuộc hai chiều.
- Có thể tạo lost update nếu T1/T2 ghi các giá trị tuyệt đối tính từ cùng giá trị cũ.
- Graph có chu trình `T1 -> T2 -> T1`; không conflict-serializable.
- Không có dirty read trong lịch; dirty write phụ thuộc thứ tự commit: T2 ghi X khi T1 chưa commit, nên lịch có dirty write nếu T1 chưa kết thúc trước `w2(X)`.

## 22. Checklist khi trả lời một bài phân loại lịch

Hãy trình bày kết quả theo mẫu:

```text
1. Transaction tham gia: T1, T2, ...
2. Giá trị ban đầu và các lần đọc từ transaction nào.
3. Anomaly:
   - dirty read: có/không
   - dirty write: có/không
   - lost update: có/không
   - non-repeatable read: có/không
   - phantom: có/không
   - read skew/write skew: có/không
4. Recoverability:
   - recoverable: có/không
   - cascadeless: có/không
   - strict: có/không
5. Conflict graph:
   - các cạnh: ...
   - chu trình: có/không
   - conflict-serializable: có/không
6. Bất biến nghiệp vụ sau cùng có còn đúng không?
7. Isolation level/DBMS nào cho phép, chặn hoặc abort lịch này?
```

Nếu đề bài không cung cấp giá trị cụ thể, hãy nêu giả định rõ ràng. Ví dụ lost update cần biết mỗi transaction ghi giá trị tuyệt đối được tính từ lần đọc trước hay dùng phép cập nhật nguyên tử. Write skew cần biết invariant phụ thuộc những dòng nào. Phantom cần biết predicate và lần chạy lại truy vấn.

## 23. Những nhầm lẫn thường gặp

**Có interleaving nghĩa là có anomaly.** Không đúng. Một lịch interleaved có thể serializable và strict.

**Không có dirty read nghĩa là lịch an toàn.** Không đúng. Lost update, read skew và write skew vẫn có thể xảy ra.

**Recoverable nghĩa là không đọc dữ liệu chưa commit.** Không đúng. Recoverable vẫn có thể có dirty read; điều kiện là transaction đọc chỉ commit sau transaction ghi nguồn.

**Strict nghĩa là serializable.** Không đúng. Write skew có thể là strict nhưng không conflict-serializable.

**Graph có chu trình nghĩa là không view-serializable.** Kết luận đúng trực tiếp là không conflict-serializable. View serializability là khái niệm rộng hơn.

**Hai transaction ghi hai dòng khác nhau thì không thể xung đột.** Có thể có read-write anti-dependency và write skew nếu quyết định ghi phụ thuộc dữ liệu mà transaction kia đã đọc.

**Thứ tự commit tạo cạnh trong precedence graph.** Không. Cạnh được tạo bởi thứ tự thao tác conflict trên cùng item.

**Isolation level có cùng tên thì cùng hành vi trên mọi DBMS.** Không. Cần phân biệt snapshot read, locking read, row versioning và cách engine phát hiện serialization anomaly.

**Mọi `UPDATE` trên cùng một dòng đều tạo lost update.** Không. `UPDATE SET x = x + 1` có thể được database áp dụng tuần tự trên giá trị hiện tại; ghi giá trị tuyệt đối từ snapshot cũ mới là dạng rủi ro thường gặp. Engine cũng có thể phát hiện và abort xung đột.

## 24. Kết luận

Phân loại lịch thực thi cần tách ba câu hỏi: dữ liệu có bị đọc/ghi sai thời điểm không, thứ tự commit có phục hồi an toàn không và lịch có tương đương một thứ tự serial không. Dirty read/write, lost update, non-repeatable read, phantom, read skew và write skew mô tả các dạng anomaly khác nhau. Recoverable, cascadeless và strict mô tả mức an toàn phục hồi; conflict graph mô tả tính conflict-serializable.

Khi làm bài, hãy theo dấu nguồn của từng lần đọc, kiểm tra trạng thái commit tại thời điểm đọc/ghi, xác định các cặp conflict rồi lập graph. Cuối cùng đối chiếu bất biến nghiệp vụ và isolation semantics của DBMS. Cách làm này tránh các kết luận vội như “không dirty read là an toàn” hoặc “strict là serializable”, đồng thời giúp giải thích chính xác vì sao một lịch được phép, bị chặn hay khiến transaction phải retry.
