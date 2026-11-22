# Thực thi tuần tự và thực thi đan xen giữa nhiều giao dịch

Khi nhiều người dùng truy cập một cơ sở dữ liệu, hệ quản trị (DBMS) thường phải xử lý nhiều giao dịch trong khoảng thời gian chồng lấn. Việc các giao dịch cùng tồn tại chưa cho biết các câu lệnh của chúng được xếp theo thứ tự nào. **Mô hình thực thi giao dịch** giúp chúng ta mô tả thứ tự ấy, phân tích kết quả và xác định lịch thực thi nào an toàn.

Có hai cách tổ chức cơ bản:

- **Thực thi tuần tự (serial execution):** hoàn thành toàn bộ thao tác của giao dịch này trước khi bắt đầu thao tác của giao dịch tiếp theo.
- **Thực thi đan xen (interleaved execution):** các thao tác của nhiều giao dịch được xen kẽ theo thời gian, trong khi thứ tự thao tác bên trong từng giao dịch vẫn được giữ nguyên.

Đan xen giúp DBMS tận dụng thời gian chờ I/O, phục vụ nhiều yêu cầu và tăng khả năng đáp ứng. Nhưng khi các giao dịch đọc hoặc ghi chung dữ liệu, thứ tự xen kẽ có thể thay đổi kết quả. Mục tiêu của **điều khiển đồng thời (concurrency control)** là cho phép những lịch đan xen có ích mà vẫn bảo đảm mức cô lập và các bất biến dữ liệu đã cam kết.

## 1. Giao dịch và lịch thực thi (schedule)

Một **giao dịch (transaction)** là một đơn vị công việc trên dữ liệu có điểm bắt đầu và kết thúc bằng `COMMIT` hoặc `ROLLBACK`. Trong lý thuyết lịch thực thi, ta thường giản lược giao dịch thành các thao tác:

| Ký hiệu | Ý nghĩa |
|---|---|
| `R1(X)` | Giao dịch `T1` đọc mục dữ liệu `X` |
| `W1(X)` | Giao dịch `T1` ghi mục dữ liệu `X` |
| `R2(Y)` | Giao dịch `T2` đọc mục dữ liệu `Y` |
| `W2(Y)` | Giao dịch `T2` ghi mục dữ liệu `Y` |
| `C1` hoặc `COMMIT1` | `T1` commit |
| `A1` hoặc `ABORT1` | `T1` abort/rollback |

Các ký hiệu này là **mô hình logic**, không phải cú pháp SQL. `R1(X)` có thể biểu diễn một câu `SELECT`, còn `W1(X)` có thể biểu diễn một câu `UPDATE`. Trên DBMS thực, một câu SQL có thể đọc/ghi nhiều dòng và tiến hành nhiều thao tác nội bộ; mô hình đơn giản giúp suy luận các quan hệ xung đột trước khi xét chi tiết triển khai.

Ví dụ có hai giao dịch:

```text
T1: R1(X) -> W1(X) -> C1
T2: R2(Y) -> W2(Y) -> C2
```

Một **schedule** là thứ tự tổng thể mà các thao tác của những giao dịch tham gia được thực hiện/quan sát trong mô hình, nhưng phải bảo toàn **thứ tự nội bộ** của từng giao dịch. Ví dụ `R1(X)` phải đứng trước `W1(X)` nếu đó là thứ tự chương trình của `T1`.

Lịch:

```text
R1(X) -> R2(Y) -> W2(Y) -> W1(X) -> C2 -> C1
```

là một lịch đan xen hợp lệ của hai chuỗi thao tác trên, vì thứ tự riêng của cả `T1` và `T2` vẫn được giữ. Ngược lại, đưa `W1(X)` lên trước `R1(X)` sẽ làm thay đổi chương trình của `T1` nên không phải lịch hợp lệ cho định nghĩa trên.

Trong tài liệu học thuật, ta còn gặp **history** (lịch sử thực thi), nhấn mạnh các thao tác đã xảy ra và kết quả mà giao dịch/client quan sát. Khi tìm hiểu tính đúng đắn, cần xét cả thao tác đọc, ghi, commit, abort và đôi khi cả giá trị đọc được, chứ không chỉ thứ tự bắt đầu giao dịch.

## 2. Thực thi tuần tự: một giao dịch xong mới đến giao dịch khác

Giả sử `T1` cập nhật tài khoản A, `T2` cập nhật tài khoản B. Có hai thứ tự tuần tự:

```text
Serial schedule S1:
Thời gian  ---------------------------------------->
T1:        R1(A) -- W1(A) -- C1
T2:                              R2(B) -- W2(B) -- C2

Serial schedule S2:
Thời gian  ---------------------------------------->
T2:        R2(B) -- W2(B) -- C2
T1:                              R1(A) -- W1(A) -- C1
```

Trong mỗi lịch, **không có thao tác của giao dịch thứ hai nằm giữa hai thao tác của giao dịch thứ nhất**. Khi `T1` chạy trước `T2`, `T2` sẽ làm việc với trạng thái được hình thành sau khi `T1` kết thúc, theo các quy tắc đọc/ghi liên quan.

### Vì sao lịch tuần tự dễ suy luận?

Nếu mỗi giao dịch, khi chạy riêng lẻ trên một trạng thái hợp lệ, đều duy trì đúng các bất biến, thì việc chạy chúng lần lượt theo một thứ tự tuần tự cũng thuận tiện để chứng minh tính đúng đắn: kết quả của giao dịch trước trở thành đầu vào hợp lệ cho giao dịch sau.

Chẳng hạn, `T1` chuyển 100 từ A sang B và `T2` chuyển 50 từ B sang A. Khi chạy tuần tự, mọi bước của một giao dịch được xử lý trọn vẹn trước khi giao dịch còn lại bắt đầu; các quan sát trung gian của giao dịch này không chen vào quá trình cập nhật của giao dịch kia.

Tuy vậy, **tuần tự không có nghĩa mọi giao dịch sẽ thành công**. Một giao dịch có thể bị từ chối vì thiếu số dư, vi phạm `UNIQUE` hoặc lỗi ứng dụng. Thực thi tuần tự chỉ nói về thứ tự xử lý giữa các giao dịch; nó không tự sửa lỗi nghiệp vụ trong bản thân giao dịch.

### Hạn chế của việc bắt buộc chạy tuần tự

DBMS có thể phải chờ đọc đĩa, ghi log, truyền dữ liệu, thực hiện tính toán hoặc chờ mạng. Nếu chỉ chạy một giao dịch tại một thời điểm trên toàn hệ thống, các tài nguyên khác có thể nhàn rỗi trong lúc giao dịch hiện tại chờ I/O.

Ví dụ, `T1` đang chờ đọc một trang dữ liệu từ đĩa nhưng `T2` chỉ cần thao tác trên một trang khác đã có trong bộ nhớ. Cho phép `T2` tiến hành trong lúc `T1` chờ có thể tăng thông lượng và giảm thời gian đáp ứng. Đây là động cơ quan trọng của thực thi đan xen.

Trong hệ thống thực tế, không nên hiểu “tuần tự” là DBMS chỉ có một luồng CPU; lịch tuần tự là **một quan hệ thứ tự logic giữa các giao dịch**.

## 3. Thực thi đan xen: các bước của nhiều giao dịch xen kẽ nhau

Một lịch đan xen có thể được hình dung:

```text
Thời gian ------------------------------------------------->

T1:        R1(X) ------ W1(X) ----------------- C1
T2:                R2(Y) ------ W2(Y) ---------------- C2

Thứ tự:    R1(X), R2(Y), W1(X), W2(Y), C1, C2
```

Hai giao dịch cùng tiến triển, nhưng thứ tự nội bộ vẫn đúng:

- `T1` đọc `X` rồi ghi `X` rồi commit.
- `T2` đọc `Y` rồi ghi `Y` rồi commit.

Nếu `X` và `Y` là các mục dữ liệu hoàn toàn độc lập, lịch đan xen này thường không tạo xung đột đọc/ghi giữa hai giao dịch. Hệ thống có thể xử lý chúng linh hoạt mà vẫn thu được hiệu ứng tương đương một lịch tuần tự.

### Đan xen khác với song song vật lý

**Đan xen** mô tả thứ tự logic các thao tác, không khẳng định chúng chạy trên bao nhiêu lõi CPU:

```text
Một bộ xử lý, xen kẽ:
  CPU:  [T1] [T2] [T1] [T2] [T1] [T2]

Hai bộ xử lý, thực thi vật lý song song:
  CPU1: [T1] [T1] [T1] [T1]
  CPU2: [T2] [T2] [T2] [T2]
```

Hai cách chạy đều có thể là **đồng thời (concurrent)** vì khoảng thực thi giao dịch chồng lấn. Trường hợp đầu không thực sự song song trên CPU; trường hợp thứ hai có. Với các thao tác thực sự chồng lấn, phân tích schedule thường dùng thứ tự hiệu lực logic của chúng, ví dụ thứ tự mà cơ chế khóa/MVCC và commit quyết định. Không thể suy luận mức cô lập chỉ từ sơ đồ CPU.

## 4. Ví dụ quan trọng: một lịch đan xen có thể làm kết quả đọc sai

Giả sử có hai tài khoản trong cùng một DB:

```text
A = 1.000
B =   500
Tổng A + B = 1.500
```

Hai giao dịch:

- **T1:** chuyển 100 từ A sang B, gồm ghi `A = 900`, ghi `B = 600`, rồi commit.
- **T2:** báo cáo tổng số dư bằng cách đọc A, đọc B, tính tổng, rồi commit.

Nếu chạy tuần tự `T2 -> T1`, báo cáo của `T2` là `1.500` (trước chuyển). Nếu chạy tuần tự `T1 -> T2`, báo cáo vẫn là `1.500` (sau chuyển). Cả hai lịch tuần tự đều đúng.

Nhưng có thể xảy ra lịch đan xen sau nếu mức cô lập cho phép mỗi lần đọc nhìn thấy một thời điểm commit khác nhau:

| Thứ tự | Giao dịch T1 — chuyển tiền | Giao dịch T2 — báo cáo | Giá trị T2 giữ |
|---:|---|---|---|
| 1 | | `R2(A)`, đọc `1.000` | `a = 1.000` |
| 2 | `W1(A)`, cập nhật `900` | | |
| 3 | `W1(B)`, cập nhật `600` | | |
| 4 | `C1` | | |
| 5 | | `R2(B)`, đọc `600` | `b = 600` |
| 6 | | Tính `a + b` rồi `C2` | **1.600** |

Lịch thao tác:

```text
R2(A) -> W1(A) -> W1(B) -> C1 -> R2(B) -> C2
```

Mặc dù `T1` chuyển tiền đúng và commit đầy đủ, **T2 ghép số dư cũ của A với số dư mới của B**, nên báo cáo thành `1.600`. Đây là một ví dụ về quan sát không nhất quán giữa nhiều lần đọc trong giao dịch.

Trên PostgreSQL, nếu `T2` dùng **hai câu `SELECT` riêng** ở mức `READ COMMITTED`, mỗi câu lệnh có thể lấy snapshot mới và tình huống tương tự có thể xảy ra. Không nên suy ra một câu `SELECT SUM(...)` duy nhất trên PostgreSQL tự trộn hai snapshot trong cùng câu lệnh: ví dụ ở đây cố ý có **hai lượt đọc**.

Ví dụ SQL của `T2`:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance FROM accounts WHERE id = 'A'; -- 1000
-- T1 cập nhật cả A và B, rồi COMMIT giữa hai SELECT này.
SELECT balance FROM accounts WHERE id = 'B'; -- 600

-- Ứng dụng cộng hai kết quả thành 1600.
COMMIT;
```

Điều sai không phải `T1` chỉ commit “nửa giao dịch”. Chính **lịch đan xen giữa hai lượt đọc** khiến `T2` quan sát hai thời điểm khác nhau.

## 5. Khi nào lịch đan xen tương đương lịch tuần tự?

Không phải mọi lịch đan xen đều có vấn đề. Mục tiêu của DBMS là cho phép lịch có kết quả tương đương việc chạy các giao dịch tuần tự theo một thứ tự nào đó.

Khái niệm cốt lõi là **serializability (tính khả tuần tự)**.

Một lịch được gọi là *serializable* nếu nó tương đương với **một lịch tuần tự** theo tiêu chí tương đương đang xét. Đây là cách diễn đạt tính đúng đắn của thực thi đồng thời mà không đòi hỏi các giao dịch thật sự chạy nối đuôi nhau.

Có nhiều khái niệm tương đương; hai khái niệm thường gặp là:

- **Conflict equivalence:** bảo toàn thứ tự của mọi cặp thao tác xung đột giữa các giao dịch.
- **View equivalence:** bảo toàn quan hệ đọc giá trị từ nguồn nào và những ghi cuối cùng đối với các mục dữ liệu, theo mô hình lý thuyết.

**Conflict serializability** là tiêu chí phổ biến để học cách phân tích schedule bằng đồ thị. **View serializability** có thể chấp nhận một số lịch mà conflict serializability không chấp nhận, chẳng hạn một số lịch có *blind writes*. Vì vậy, khi nói “lịch serializable”, cần biết đang dùng tiêu chí hay mức isolation cụ thể nào.

### 5.1. Các thao tác xung đột (conflicting operations)

Hai thao tác được xem là xung đột trong mô hình đọc/ghi đơn giản khi:

1. Chúng thuộc **hai giao dịch khác nhau**.
2. Chúng truy cập **cùng một mục dữ liệu**.
3. **Ít nhất một thao tác là ghi**.

| Cặp thao tác trên cùng `X` | Xung đột? | Vì sao? |
|---|---|---|
| `R1(X)` và `R2(X)` | Không | Cả hai chỉ đọc; đổi thứ tự không thay đổi giá trị lưu |
| `R1(X)` và `W2(X)` | Có | Đổi thứ tự có thể đổi giá trị mà `T1` đọc |
| `W1(X)` và `R2(X)` | Có | Đổi thứ tự có thể đổi giá trị mà `T2` đọc |
| `W1(X)` và `W2(X)` | Có | Đổi thứ tự có thể đổi giá trị ghi sau cùng |
| `W1(X)` và `R2(Y)` với `X ≠ Y` | Không | Không cùng mục dữ liệu trong mô hình |

Ví dụ, nếu `T1` ghi `X` trước khi `T2` đọc `X`, ta phải giữ thứ tự này nếu muốn hai lịch *conflict equivalent*. Nhưng thao tác `R1(X)` và `R2(Y)` có thể đổi chỗ khi không có ràng buộc khác.

### 5.2. Ví dụ lịch đan xen vẫn conflict-serializable

Xét:

```text
T1: R1(A), W1(A), R1(B), W1(B), C1
T2: R2(C), W2(C), R2(A), W2(A), C2
```

Hai giao dịch cùng có thao tác trên A; các mục B và C chỉ thuộc một bên. Một lịch đan xen:

```text
S_good:
R1(A) -> R2(C) -> W2(C) -> R1(B) -> W1(A)
      -> W1(B) -> C1 -> R2(A) -> W2(A) -> C2
```

Các thao tác trên C của `T2` đã xen vào khi `T1` chưa hoàn tất. Tuy nhiên, đối với mục A, mọi thao tác của `T1` liên quan tới A đều xảy ra trước thao tác của `T2`. Không có xung đột theo chiều ngược lại.

Vì vậy, lịch này có hiệu ứng tương đương thứ tự tuần tự **`T1 -> T2`** về các xung đột đọc/ghi. Đây là một ví dụ cho thấy **thực thi đan xen không nhất thiết làm mất tính khả tuần tự**.

### 5.3. Ví dụ lịch đan xen không conflict-serializable

Giả sử `X = 100`. Mỗi giao dịch muốn tăng `X` thêm 10, theo kiểu ứng dụng đọc giá trị rồi tính số mới:

```text
T1: R1(X=100) -> tính 110 -> W1(X=110) -> C1
T2: R2(X=100) -> tính 110 -> W2(X=110) -> C2
```

Lịch đan xen:

```text
R1(X) -> R2(X) -> W1(X) -> W2(X) -> C1 -> C2
```

Kết quả cuối là `X = 110`, thay vì `120` như khi hai lần tăng độc lập thực hiện tuần tự và không có cập nhật nào bị bỏ. Đây là tình huống **lost update** do đọc–tính–ghi dựa trên giá trị cũ. Trong một DBMS cụ thể, khóa, mức cô lập, kiểm tra phiên bản hoặc cơ chế phát hiện xung đột có thể chặn/làm thất bại lịch này.

Lịch này không conflict-serializable: `R1(X)` đứng trước `W2(X)` tạo quan hệ `T1 -> T2`, nhưng `R2(X)` đứng trước `W1(X)` tạo quan hệ `T2 -> T1`. Hai yêu cầu thứ tự mâu thuẫn.

## 6. Kiểm tra conflict serializability bằng đồ thị

**Precedence graph**, còn gọi là **serialization graph** trong mô hình xung đột, biểu diễn ràng buộc thứ tự giữa các giao dịch:

1. Tạo một đỉnh cho mỗi giao dịch `Ti`.
2. Với mỗi cặp thao tác **xung đột** trên cùng mục dữ liệu, nếu thao tác của `Ti` đứng trước thao tác của `Tj` trong lịch, thêm cạnh `Ti -> Tj`.
3. Nếu đồ thị **không có chu trình**, lịch là *conflict-serializable*. Một thứ tự topo của đồ thị là thứ tự tuần tự tương đương.
4. Nếu đồ thị **có chu trình**, lịch **không conflict-serializable**.

Ví dụ lịch `S_good` ở trên có cạnh:

```text
T1 ───────> T2
    (trên A)

Không có chu trình.
Thứ tự tuần tự tương đương: T1, T2.
```

Lịch lost update có hai cạnh:

```text
    (R1 trước W2)
T1 ───────────────> T2
 ^                  |
 |                  |
 +──────────────────+
    (R2 trước W1)

Có chu trình T1 -> T2 -> T1.
```

Đối với ví dụ báo cáo tổng tiền:

```text
R2(A) -> W1(A) -> W1(B) -> C1 -> R2(B) -> C2

R2(A) trước W1(A) : T2 -> T1
W1(B) trước R2(B) : T1 -> T2

T1 <----> T2  (có chu trình)
```

Đồ thị cho thấy không có thứ tự tuần tự nào vừa yêu cầu `T2` đứng trước `T1` để giữ giá trị đọc của A, vừa yêu cầu `T1` đứng trước `T2` để giữ giá trị đọc của B.

### Một số lưu ý khi dựng đồ thị

- Không tạo cạnh vì hai thao tác thuộc **cùng một giao dịch**: thứ tự nội bộ vốn đã được giữ.
- Không tạo cạnh cho hai thao tác **chỉ đọc** cùng dữ liệu.
- Không suy ra cạnh chỉ vì `T1` bắt đầu trước `T2` hoặc commit trước `T2`; cần xét các thao tác xung đột.
- Lịch càng có nhiều giao dịch và mục dữ liệu thì đồ thị càng nhiều cạnh, nhưng quy tắc xác định chu trình không đổi.
- Phân tích trên là mô hình lý thuyết các thao tác đọc/ghi; việc ánh xạ SQL thực tế sang các mục dữ liệu và xung đột có thể phức tạp hơn với truy vấn điều kiện, predicate, chỉ mục, snapshot và phantom.

Đồ thị xung đột là một công cụ học tập quan trọng; nó không có nghĩa ứng dụng phải tự dựng đồ thị mỗi lần gọi DB. DBMS hiện thực các giao thức điều khiển đồng thời để ngăn hoặc phát hiện những lịch vi phạm bảo đảm isolation.

## 7. Thứ tự commit và khả năng khôi phục là câu hỏi khác

Một lịch có thể conflict-serializable nhưng vẫn **đọc dữ liệu chưa commit**. Vì vậy, ngoài tính khả tuần tự, cần xét các thuộc tính phục hồi khi giao dịch abort.

Giả sử `T1` ghi `X` và `T2` đọc giá trị mới trước khi `T1` commit:

```text
W1(X) -> R2(X) -> C1 -> C2
```

Trên đồ thị xung đột, chỉ có cạnh `T1 -> T2` nên lịch này conflict-serializable. Nhưng tại thời điểm `R2(X)`, giá trị của `T1` **chưa commit**. Nếu `T1` sau đó abort thay vì commit, `T2` đã dựa vào dữ liệu bị hủy.

Những thuộc tính cần phân biệt:

| Thuộc tính lịch | Yêu cầu | Ý nghĩa |
|---|---|---|
| **Recoverable** | Nếu `Tj` đọc giá trị do `Ti` ghi, `Tj` chỉ commit sau khi `Ti` đã commit | Tránh một giao dịch đã commit phụ thuộc vào giao dịch bị hủy |
| **Cascadeless** | Không cho đọc giá trị do giao dịch khác ghi khi giao dịch đó chưa commit | Tránh phải abort dây chuyền do dirty read |
| **Strict** | Không cho giao dịch khác đọc hoặc ghi đè mục dữ liệu vừa được giao dịch chưa kết thúc ghi | Đơn giản hóa khôi phục và tránh dirty read, dirty write |

Quan hệ thường dùng trong mô hình này là:

```text
Strict  =>  Cascadeless  =>  Recoverable
```

Chiều ngược lại không nhất thiết đúng.

### Lịch không recoverable

```text
W1(X) -> R2(X) -> C2 -> A1
```

`T2` đã **commit** kết quả dựa trên dữ liệu của `T1`, nhưng `T1` lại abort. Không thể đơn giản rollback `T2` như một giao dịch chưa commit. Đây là lịch **không recoverable**.

### Cascading abort

```text
W1(X) -> R2(X) -> A1 -> A2
```

`T2` đọc dữ liệu chưa commit của `T1`. Khi `T1` abort, `T2` cũng phải abort nếu đã phụ thuộc vào giá trị đó. Nếu nhiều giao dịch đọc nối tiếp, việc hủy có thể lan rộng.

### Lịch strict

```text
W1(X) -> C1 -> R2(X) -> W2(X) -> C2
```

Ở đây, `T2` chỉ đọc/ghi `X` sau khi giao dịch đã ghi `X` trước đó kết thúc bằng commit. Nếu `T1` abort, `T2` có thể tiếp tục theo trạng thái đã rollback, tùy thứ tự và kết quả thực tế.

**Serializability** và **recoverability/strictness** không phải cùng một khái niệm. Một lịch có thể tương đương tuần tự về xung đột nhưng vẫn bất tiện hoặc nguy hiểm cho khôi phục nếu cho phép đọc dữ liệu chưa commit.

## 8. DBMS tổ chức lịch đan xen bằng cơ chế nào?

Để cung cấp concurrency mà vẫn bảo vệ dữ liệu, DBMS sử dụng những cơ chế khác nhau. Dưới đây là các nhóm ý tưởng chính, gắn trực tiếp với thứ tự các thao tác.

### 8.1. Khóa (locking)

DBMS có thể dùng:

- **Shared/read lock:** cho phép các thao tác đọc tương thích tùy mô hình khóa.
- **Exclusive/write lock:** bảo vệ dữ liệu đang được ghi, hạn chế các thao tác xung đột.
- **Row/table/predicate/range locks:** khóa tại các phạm vi khác nhau; chi tiết phụ thuộc DBMS.

Ví dụ, khi `T1` giữ khóa ghi trên `X`, `T2` muốn ghi hoặc đọc dưới chế độ khóa không tương thích có thể phải chờ:

```text
T1: LOCK X -> W1(X) ------------ C1 -> UNLOCK X
T2:               request LOCK X -> wait -> LOCK X -> W2(X) -> C2
```

**Two-Phase Locking (2PL)** là họ giao thức có giai đoạn lấy khóa và giai đoạn nhả khóa; sau khi đã bắt đầu nhả khóa thì không lấy thêm khóa theo mô hình 2PL chuẩn. 2PL phù hợp bảo đảm conflict serializability trong giả thiết giao thức. **Strict 2PL** giữ các khóa ghi cho đến khi commit/abort để ngăn những lịch không strict.

Khóa có chi phí: giao dịch giữ khóa quá lâu có thể làm nhiều giao dịch khác chờ. Hai giao dịch giữ các khóa khác nhau và chờ khóa của nhau có thể gây **deadlock**. DBMS thường có cơ chế phát hiện hoặc xử lý deadlock, chẳng hạn hủy một giao dịch để giao dịch khác có thể tiến lên.

### 8.2. MVCC và snapshot

**Multi-Version Concurrency Control (MVCC)** duy trì nhiều phiên bản logic của dữ liệu, cho phép những lượt đọc nhìn thấy một snapshot phù hợp mà không nhất thiết phải chờ mọi thao tác ghi.

Thay vì một bản sao giá trị `X` đang bị ghi đè tức thì, DBMS quản lý các phiên bản và điều kiện hiển thị:

```text
X phiên bản cũ ------> X phiên bản mới
      ^                       ^
      |                       |
  snapshot S_old          snapshot S_new
```

Ở mức `READ COMMITTED` trên PostgreSQL, hai câu `SELECT` riêng trong cùng giao dịch có thể dùng snapshot tại hai thời điểm khác nhau. Ở mức `REPEATABLE READ` của PostgreSQL, các truy vấn thông thường của giao dịch sử dụng snapshot ổn định hơn; hành vi chi tiết ở các DBMS khác có thể khác.

**MVCC không có nghĩa tự động serializable.** Một snapshot nhất quán cho từng transaction vẫn có thể cho phép những bất thường như *write skew* trong một số mức cô lập. Để bảo đảm tương đương tuần tự, DBMS có thể cần thêm phát hiện xung đột, khóa, validation hoặc cơ chế serializable chuyên biệt.

### 8.3. Điều khiển đồng thời lạc quan (optimistic concurrency control)

Trong hướng **optimistic**, giao dịch có thể đọc và tính toán mà không giữ khóa xung đột suốt quá trình, rồi **kiểm tra** trước khi ghi/commit xem dữ liệu mình dựa vào có bị thay đổi hay không. Khi validation thất bại, giao dịch phải abort và retry phù hợp.

Ở mức ứng dụng, có thể áp dụng cơ chế **version check**:

```sql
-- Ứng dụng đã đọc một dòng với version = 7.
UPDATE documents
SET content = 'new content',
    version = version + 1
WHERE id = 42 AND version = 7;
```

Nếu số dòng cập nhật bằng 0, phiên bản đã thay đổi hoặc dòng không còn tồn tại; ứng dụng cần tải lại dữ liệu, kiểm tra xung đột rồi quyết định retry hay báo người dùng. Một `UPDATE` có điều kiện như vậy giúp ngăn **một kiểu lost update trên cùng dòng**, nhưng không tự xử lý mọi bất biến liên dòng và không tương đương một chứng minh serializability toàn hệ thống.

### 8.4. Sắp thứ tự bằng timestamp

Một số giao thức sử dụng timestamp/transaction order để quyết định thao tác nào có thể đọc hoặc ghi phiên bản nào. Nếu thao tác vi phạm thứ tự dự kiến, hệ thống có thể phải hủy và thực hiện lại giao dịch. Chi tiết của timestamp ordering, MVCC, khóa và các biến thể lai phụ thuộc thiết kế DBMS.

Các cơ chế trên đều hướng tới cùng câu hỏi: **làm sao cho phép nhiều transaction cùng tiến triển trong khi ngăn hoặc phát hiện lịch không phù hợp với bảo đảm isolation đã chọn?**

## 9. Isolation level tác động đến những lịch nào được phép

**Isolation level** là hợp đồng về mức độ giao dịch được bảo vệ khỏi ảnh hưởng của giao dịch khác. Nó quyết định lớp lịch thực thi mà DBMS có thể cho phép, đồng thời ảnh hưởng hiệu năng và tỷ lệ phải chờ/abort.

| Isolation level | Góc nhìn khái quát | Điều cần lưu ý khi suy luận schedule |
|---|---|---|
| `READ UNCOMMITTED` | Mức cô lập yếu nhất theo mô hình SQL | Tùy DBMS; PostgreSQL xử lý tương đương `READ COMMITTED`, không cho dirty read |
| `READ COMMITTED` | Chỉ quan sát dữ liệu đã commit theo cơ chế DBMS | Hai lượt đọc riêng có thể nhìn thấy hai thời điểm khác nhau |
| `REPEATABLE READ` | Bảo vệ nhiều hơn khỏi việc thay đổi kết quả đọc lại | Ngữ nghĩa và bất thường còn cho phép khác nhau theo DBMS |
| `SERIALIZABLE` | Các giao dịch thành công phải có hiệu ứng tương đương lịch tuần tự | Có thể chờ hoặc buộc một giao dịch abort/retry để duy trì bảo đảm |

Không nên lập luận “đã mở transaction nên mọi lần đọc đều thấy cùng một trạng thái”. Cần biết mức isolation và hành vi snapshot/locking của DBMS.

Ngoài ra, **Serializable không đòi hỏi DBMS thực sự chạy từng giao dịch từ đầu đến cuối theo hàng đợi**. Hệ thống vẫn có thể chạy đan xen mạnh, rồi dùng cơ chế thích hợp để bảo đảm các giao dịch commit có hiệu ứng tương đương tuần tự.

Một số DBMS triển khai serializable theo cách khác nhau. Ví dụ, PostgreSQL có thể báo **serialization failure** với mã SQLSTATE `40001` để ứng dụng retry **toàn bộ transaction**, bởi các quyết định đọc/ghi trước đó có thể đã không còn phù hợp.

## 10. Lịch thực thi trong tình huống bán sản phẩm cuối cùng

Giả sử bảng `inventory` có một sản phẩm còn `quantity = 1`. Hai khách hàng cùng đặt sản phẩm này.

### 10.1. Lịch đọc rồi ghi dựa trên giá trị cũ

Ứng dụng của mỗi khách thực hiện:

1. Đọc `quantity`.
2. Nếu `quantity > 0`, xác nhận đơn.
3. Ghi `quantity = quantity_đã_đọc - 1`.

Một lịch đan xen nguy hiểm:

| Bước | T1 — khách A | T2 — khách B |
|---:|---|---|
| 1 | Đọc `quantity = 1` | |
| 2 | | Đọc `quantity = 1` |
| 3 | Chấp nhận đơn A | |
| 4 | | Chấp nhận đơn B |
| 5 | Ghi `quantity = 0` | |
| 6 | | Ghi `quantity = 0` |
| 7 | Commit | Commit |

Tồn kho vẫn hiển thị 0 nhưng đã có hai đơn cho một sản phẩm. Mỗi giao dịch ra quyết định dựa trên cùng dữ liệu cũ; đây là hậu quả của lịch thực thi và cách ứng dụng kiểm tra điều kiện.

### 10.2. Đưa điều kiện vào cập nhật nguyên tử

Trong PostgreSQL, có thể dùng:

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42
  AND quantity > 0
RETURNING quantity;

-- Chỉ tạo/xác nhận đơn trong cùng transaction khi UPDATE
-- trả về đúng một dòng.
-- Nếu không có dòng nào: hết hàng, không xác nhận đơn.

COMMIT;
```

Với hai giao dịch cạnh tranh trên cùng dòng, PostgreSQL xử lý xung đột ghi bằng cơ chế khóa và quy tắc cập nhật tương ứng. Sau khi giao dịch đi trước hoàn tất, giao dịch đang chờ sẽ xử lý điều kiện trên trạng thái thích hợp, hoặc gặp lỗi cần xử lý tùy isolation. **Không thể cả hai thành công trừ sản phẩm cuối cùng** theo lệnh cập nhật có điều kiện này.

Nếu việc xác nhận đơn nằm ở một cơ sở dữ liệu/dịch vụ khác, transaction cục bộ chỉ bảo vệ phần dữ liệu thuộc phạm vi của nó; quy trình phân tán còn cần thiết kế riêng. Ví dụ ở đây nhằm minh họa việc thay đổi **lịch cạnh tranh trên một dòng** bằng một thao tác ghi có điều kiện đúng.

## 11. Chọn giữa an toàn và khả năng xử lý đồng thời

Thực tế không chỉ có hai lựa chọn “chạy tất cả tuần tự” hoặc “cho phép mọi thao tác đan xen tự do”. DBMS và ứng dụng có thể đạt an toàn bằng cách **chỉ tuần tự hóa những truy cập thực sự xung đột**, trong khi vẫn cho phần công việc độc lập chạy xen kẽ.

Ví dụ:

- Hai giao dịch chỉ đọc những dữ liệu độc lập có thể tiến hành đồng thời rất hiệu quả.
- Hai giao dịch cập nhật **cùng một dòng tồn kho** cần được phân xử để không bán vượt số lượng.
- Nhiều giao dịch truy cập những dòng khác nhau vẫn có thể chạy đồng thời khi không có bất biến chung gây phụ thuộc.
- Một giao dịch giữ khóa xuyên qua lời gọi HTTP lâu có thể kéo dài thời gian chờ của mọi giao dịch đang cần cùng dòng.

Các chi phí cần theo dõi là độ trễ giao dịch, thời gian chờ khóa, tỷ lệ deadlock, tỷ lệ serialization failure, số lần retry và mức tranh chấp trên những dòng “nóng”. Tăng số worker hoặc số connection không nhất thiết tăng thông lượng nếu các giao dịch đều xếp hàng chờ cùng tài nguyên.

### Gợi ý khi thiết kế transaction

1. **Xác định bất biến:** điều gì tuyệt đối không được sai sau commit?
2. **Xác định dữ liệu chung:** những dòng, khóa, điều kiện hay tài nguyên nào nhiều giao dịch cùng sử dụng?
3. **Xác định lịch nguy hiểm:** có thể đọc giá trị cũ, ghi đè nhau, nhìn thấy nửa quá trình hoặc dựa vào các snapshot khác thời điểm không?
4. **Chọn cơ chế bảo vệ:** constraint, cập nhật có điều kiện, khóa, MVCC/snapshot, isolation và retry phù hợp.
5. **Giữ giao dịch đủ ngắn:** tránh tính toán hoặc chờ mạng không cần thiết khi đang giữ khóa/tài nguyên.
6. **Xử lý abort/retry có chủ đích:** retry toàn bộ phần quyết định có liên quan, giới hạn số lần retry, bảo vệ side effect bằng idempotency khi cần.

Đối với dữ liệu quan trọng, một lịch khiến dữ liệu cuối cùng “trông hợp lý” chưa đủ. Cần chứng minh rằng bất biến được bảo vệ đối với **mọi lịch mà hệ thống có thể cho phép** theo mức isolation và các cơ chế đã dùng.

## 12. Bài tập đọc lịch thực thi

### Bài tập 1: Lịch nào tuần tự?

Cho:

```text
T1: R1(A), W1(A), C1
T2: R2(B), W2(B), C2
```

Ba lịch:

```text
S1: R1(A), W1(A), C1, R2(B), W2(B), C2
S2: R1(A), R2(B), W1(A), W2(B), C1, C2
S3: R2(B), W2(B), C2, R1(A), W1(A), C1
```

**Đáp án:** `S1` và `S3` tuần tự. `S2` đan xen nhưng không có xung đột giữa hai giao dịch vì chúng truy cập các mục dữ liệu khác nhau, nên vẫn tương đương một lịch tuần tự theo mô hình.

### Bài tập 2: Dùng đồ thị precedence

Cho:

```text
S: R1(X), W1(X), R2(X), W2(Y), R1(Y), C1, C2
```

Xác định cạnh trên đồ thị.

**Đáp án:**

- `W1(X)` trước `R2(X)` ⇒ cạnh `T1 -> T2`.
- `W2(Y)` trước `R1(Y)` ⇒ cạnh `T2 -> T1`.
- Đồ thị có chu trình `T1 -> T2 -> T1`, nên lịch **không conflict-serializable**.

### Bài tập 3: Conflict-serializable có đủ để recoverable?

Cho:

```text
S: W1(X), R2(X), C2, A1
```

**Đáp án:** Chỉ có ràng buộc xung đột `T1 -> T2` nên đồ thị không chu trình; lịch có thể conflict-serializable theo mô hình thao tác. Nhưng `T2` commit sau khi đọc giá trị chưa commit của `T1`, còn `T1` abort sau đó. Lịch **không recoverable**. Đây là lý do cần xem thêm commit/abort và quy tắc tránh dirty read.

### Bài tập 4: Không có cập nhật ghi đè nhưng vẫn có kết quả sai?

T1 chuyển tiền từ A sang B; T2 đọc A trước khi T1 commit và đọc B sau khi T1 commit. Không giao dịch nào ghi đè giá trị của giao dịch khác.

**Đáp án:** `T2` vẫn có thể tính tổng sai nếu hai lượt đọc dùng hai snapshot khác nhau. Vấn đề nằm ở **lịch xen kẽ và mức isolation**, không nhất thiết phải có lost update hoặc dirty write.

## 13. Những nhầm lẫn thường gặp

**“Đan xen nghĩa là lịch không an toàn.”** Sai. Rất nhiều lịch đan xen có thể tương đương tuần tự, chẳng hạn giao dịch truy cập dữ liệu độc lập hoặc được DBMS điều phối xung đột đúng.

**“Hai transaction BEGIN cùng lúc thì chúng song song.”** Chưa đủ để kết luận. Chúng có thể chỉ xen kẽ hoặc một giao dịch đang chờ khóa. Song song nói về thực thi vật lý, còn schedule nói về thứ tự thao tác.

**“Commit theo thứ tự T1 rồi T2 thì lịch tương đương T1 trước T2.”** Không luôn đúng. Các thao tác đọc/ghi xung đột **trước commit** mới quyết định quan hệ bắt buộc trong precedence graph.

**“Nếu giá trị cuối cùng đúng thì lịch chắc chắn serializable.”** Không. Hai lịch có thể tình cờ cho cùng giá trị với một dữ liệu đầu vào nhưng vẫn khác quan hệ đọc/ghi, hoặc khác kết quả khi dữ liệu thay đổi. Serializability là tính chất của lịch theo mô hình tương đương, không được chứng minh chỉ bằng một giá trị quan sát.

**“Có transaction thì không thể đọc dữ liệu cũ.”** Không. Snapshot và mức isolation quyết định dữ liệu mà mỗi câu lệnh thấy; replication còn có thể tạo độ trễ độc lập với isolation trong DB cục bộ.

**“Serializable buộc mọi transaction chạy nối đuôi.”** Không. Một triển khai có thể cho các thao tác xen kẽ, rồi dùng locking, validation hoặc phát hiện xung đột để bảo đảm kết quả của các giao dịch thành công tương đương một thứ tự tuần tự.

## 14. Cách tư duy khi gặp một lịch nhiều giao dịch

Đối với bất kỳ mô tả thực thi nào, hãy đi theo chuỗi câu hỏi:

1. **Mỗi giao dịch làm gì và thứ tự nội bộ là gì?** Viết các thao tác `R/W/C/A` cùng mục dữ liệu liên quan.
2. **Lịch tổng thể có tuần tự hay đan xen?** Xem có thao tác của giao dịch này xuất hiện giữa các thao tác của giao dịch khác không.
3. **Có thao tác xung đột nào?** Tìm các cặp cùng mục dữ liệu, thuộc giao dịch khác nhau, có ít nhất một thao tác ghi.
4. **Có lịch tuần tự tương đương theo xung đột không?** Dựng precedence graph và tìm chu trình.
5. **Lịch có an toàn khi một giao dịch abort?** Kiểm tra dirty read, commit phụ thuộc, recoverable/cascadeless/strict.
6. **DBMS thực tế bảo đảm điều gì?** Xác định isolation level, khóa/MVCC, ràng buộc và cơ chế retry.

Nắm được sự khác nhau giữa **thứ tự tuần tự**, **lịch đan xen** và **lịch đan xen nhưng vẫn khả tuần tự** giúp giải thích vì sao DBMS có thể xử lý nhiều người dùng cùng lúc mà vẫn giữ tính đúng đắn của dữ liệu. Điều cần bảo vệ không phải là sự vắng mặt hoàn toàn của đan xen, mà là **các ràng buộc thứ tự và bất biến khi nhiều giao dịch cùng truy cập dữ liệu**.
