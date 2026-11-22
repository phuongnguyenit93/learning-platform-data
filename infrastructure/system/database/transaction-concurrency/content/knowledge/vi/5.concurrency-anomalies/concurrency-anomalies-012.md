# Lập lịch tối thiểu để phân biệt các bất thường dễ nhầm

Trong cơ sở dữ liệu có nhiều giao dịch chạy đồng thời, một lỗi thường không xuất hiện vì một câu SQL riêng lẻ sai cú pháp. Nó xuất hiện do **thứ tự xen kẽ giữa các thao tác đọc, ghi, commit và rollback** tạo ra một trạng thái mà nghiệp vụ không mong muốn. Muốn phân tích chính xác, cần biểu diễn lịch giao dịch đủ ngắn để nhìn rõ quan hệ gây lỗi, đồng thời giữ đủ thông tin để phân biệt các bất thường có tên gần giống nhau.

Bài học này sử dụng các lịch tối thiểu (minimal schedules) như một công cụ phân tích: bắt đầu từ trạng thái ban đầu, liệt kê thao tác cần thiết của từng transaction, đánh dấu điểm commit/abort, rồi rút ra điều kiện khiến bất thường xuất hiện. Trọng tâm là phân biệt **dirty read, dirty write, lost update, non-repeatable read, phantom read, read skew và write skew**. Các ví dụ dùng ký hiệu thao tác khái niệm; không hàm ý mọi DBMS đều cho phép thực thi lịch đó.

## 1. Lịch giao dịch biểu diễn điều gì?

**Lịch giao dịch** (*schedule/history*) là thứ tự thực thi các thao tác của một nhóm transaction. Một lịch có thể xen kẽ thao tác của nhiều transaction, miễn là thứ tự bên trong từng transaction được giữ nguyên.

Các ký hiệu được dùng trong bài:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `R1(X)` | Transaction T1 đọc đối tượng dữ liệu X. |
| `W1(X)` | Transaction T1 ghi đối tượng dữ liệu X. |
| `C1` | Transaction T1 commit. |
| `A1` | Transaction T1 abort/rollback. |
| `R2(X)` / `W2(X)` | T2 đọc/ghi X. |
| `R1(X=10)` | T1 đọc và nhận giá trị 10 của X. |
| `W1(X=20)` | T1 ghi giá trị 20 vào X. |

Ví dụ:

~~~text
T1: R1(X), W1(X), C1
T2: R2(X), W2(X), C2

Một lịch xen kẽ:
R1(X), R2(X), W1(X), C1, W2(X), C2
~~~

Để một lịch đủ rõ, cần phân biệt:

- **Thứ tự thao tác:** transaction nào đọc/ghi trước.
- **Thời điểm kết thúc:** transaction đã commit hay còn đang mở khi transaction khác thao tác.
- **Giá trị được đọc:** đọc phiên bản nào, giá trị cũ hay mới.
- **Phạm vi đối tượng:** một hàng, một khóa, một tập hàng thỏa điều kiện hay nhiều đối tượng liên quan.
- **Điều kiện nghiệp vụ:** trạng thái nào phải luôn đúng, hoặc kết quả nào phải tương đương một thứ tự chạy tuần tự.

Chỉ viết `R1(X), W2(X)` mà không có thông tin commit/abort có thể chưa đủ để xác định dirty read hay dirty write. Điểm commit của transaction liên quan thường quyết định phân loại.

## 2. Tại sao phải tìm lịch tối thiểu?

Lịch tối thiểu là lịch giữ lại **ít thao tác nhất nhưng vẫn thể hiện đầy đủ điều kiện gây ra bất thường đang phân tích**. Nó giúp tách nguyên nhân khỏi các chi tiết không liên quan như nhiều bảng, nhiều câu lệnh hoặc xử lý ứng dụng.

Ví dụ, để thể hiện dirty read, chỉ cần T1 ghi X nhưng chưa commit, T2 đọc X, rồi T1 rollback:

~~~text
W1(X), R2(X), A1
~~~

Không cần thêm bảng, nhiều hàng hay các câu truy vấn khác để nhận diện. Ngược lại, nếu muốn chứng minh lost update, cần thể hiện hai transaction cùng đọc một giá trị cũ, cả hai tạo cập nhật, và một lần ghi làm mất kết quả của lần ghi còn lại.

Một lịch được rút gọn quá mức sẽ làm mất dữ kiện phân loại. Chẳng hạn `W1(X), W2(X)` chỉ cho biết có hai lần ghi; nếu thiếu trạng thái commit của T1, chưa thể xác định chính xác lần ghi thứ hai có xảy ra trên thay đổi chưa được xác nhận hay không.

## 3. Dirty read — đọc giá trị chưa commit

Dirty read xảy ra khi một transaction đọc giá trị do transaction khác ghi nhưng transaction ghi đó chưa commit. Nếu transaction ghi sau đó rollback, giá trị mà transaction đọc đã sử dụng chưa bao giờ trở thành dữ liệu được xác nhận.

**Lịch tối thiểu:**

~~~text
Ban đầu: X = 10
W1(X = 20), R2(X = 20), A1
~~~

Diễn giải:

1. T1 ghi X thành 20 nhưng chưa commit.
2. T2 đọc X và nhận 20.
3. T1 rollback, X trở lại 10.
4. Kết quả mà T2 đã quan sát là một thay đổi bị hủy.

Điều kiện nhận diện là **đọc trước commit của writer**, sau đó writer abort hoặc rollback. Nếu T1 commit trước khi T2 đọc, T2 đọc một giá trị đã xác nhận và lịch đó không phải dirty read.

~~~mermaid
sequenceDiagram
    participant T1
    participant DB as Database
    participant T2
    T1->>DB: W1(X = 20)
    Note over DB: T1 chưa commit
    T2->>DB: R2(X) -> 20
    T1->>DB: A1 / ROLLBACK
    Note over DB: X trở lại 10; T2 đã đọc giá trị bị hủy
~~~

Dirty read có thể dẫn tới các quyết định dây chuyền. T2 có thể tính tổng, kiểm tra điều kiện hoặc ghi dữ liệu khác dựa trên giá trị 20. Dù X được rollback về 10, những hành động tiếp theo của T2 không tự động được đảo ngược.

## 4. Dirty write — ghi lên thay đổi chưa commit

Dirty write xảy ra khi T2 ghi lên X trong khi thay đổi trước đó của T1 trên X vẫn chưa commit hoặc rollback.

**Lịch tối thiểu:**

~~~text
Ban đầu: X = 10
W1(X = 20), W2(X = 30), A1
~~~

Ở đây T2 ghi 30 lên đối tượng mà T1 vừa ghi 20 nhưng chưa kết thúc transaction. Khi T1 rollback, database phải bảo đảm việc hoàn tác T1 không vô tình phá hủy một thay đổi độc lập của T2.

Điều kiện nhận diện là **ghi sau một lần ghi chưa được xác nhận trên cùng đối tượng**. Dirty write khác dirty read ở thao tác của T2: dirty read dùng `R`, dirty write dùng `W`.

Các DBMS quan hệ thông dụng ngăn dirty write bằng khóa ghi hoặc cơ chế điều phối tương đương. Vì vậy, khi chạy ví dụ trên PostgreSQL hay InnoDB, thao tác ghi của T2 thường phải chờ T1 kết thúc hoặc nhận lỗi theo tình huống; lịch dirty write là lịch dùng để minh họa bất thường lý thuyết.

## 5. Lost update — cập nhật bị ghi đè

Lost update xảy ra khi hai transaction cùng dựa trên một giá trị đã đọc, sau đó kết quả cập nhật của transaction này bị lần ghi kia ghi đè. Khác với dirty write, lần ghi sau có thể diễn ra **sau khi transaction trước đã commit**.

Giả sử X ban đầu bằng 10. T1 tăng 1; T2 tăng 2. Cả hai đọc giá trị 10 và tính ra kết quả tuyệt đối.

**Lịch tối thiểu:**

~~~text
Ban đầu: X = 10
R1(X = 10), R2(X = 10),
W1(X = 11), C1,
W2(X = 12), C2
~~~

Trạng thái cuối là 12. Nhưng nếu hai thao tác tăng đều được áp dụng tuần tự, kết quả phải là 13. T2 đã ghi giá trị 12 được tính từ bản đọc cũ, do đó làm mất phần tăng của T1.

Điều kiện nhận diện:

1. Hai transaction đọc cùng một giá trị/phiên bản trước khi cập nhật.
2. Mỗi transaction tính ra giá trị ghi dựa trên bản đọc đó.
3. Lần ghi sau ghi đè kết quả của lần ghi trước.
4. Transaction trước đã commit trước khi lần ghi sau hoàn tất trong lịch minh họa trên.

Lost update thường gặp khi ứng dụng làm theo mẫu `SELECT`, tính toán trong bộ nhớ, rồi `UPDATE` ghi một giá trị tuyệt đối mà không kiểm tra phiên bản.

### Cập nhật tương đối có thể thay đổi kết quả

Nếu thay vì ghi `X = 12`, T2 thực hiện câu lệnh nguyên tử `UPDATE counters SET value = value + 2`, database có thể áp dụng phép tăng trên giá trị hiện hành sau khi điều phối writer. Kết quả khi đó có thể là 13. Vì vậy, cần phân biệt **ghi giá trị tuyệt đối tính từ snapshot cũ** với **cập nhật tương đối được thực thi tại database**.

~~~sql
-- Mẫu dễ lost update nếu :new_value được tính từ lần đọc cũ:
UPDATE counters SET value = :new_value WHERE id = 1;

-- Mẫu cộng tương đối tại database:
UPDATE counters SET value = value + 2 WHERE id = 1;

-- Mẫu optimistic locking:
UPDATE counters
SET value = :new_value, version = version + 1
WHERE id = 1 AND version = :version_read;
~~~

Ở mẫu optimistic locking, nếu câu lệnh cập nhật 0 hàng, ứng dụng biết dữ liệu đã thay đổi hoặc không còn phiên bản phù hợp và phải xử lý xung đột.

## 6. Non-repeatable read — đọc lại cùng hàng nhưng thấy giá trị khác

Non-repeatable read xảy ra khi T1 đọc cùng một hàng hai lần, nhưng giữa hai lần đọc, T2 cập nhật hàng đó và commit. Cùng một điều kiện định danh hàng trả về giá trị khác nhau trong cùng transaction T1.

**Lịch tối thiểu:**

~~~text
Ban đầu: X = 10
R1(X = 10), W2(X = 20), C2, R1(X = 20), C1
~~~

T1 đọc X là 10. T2 cập nhật X thành 20 rồi commit. Khi T1 đọc lại cùng hàng, T1 thấy 20. Đây không phải dirty read vì T2 đã commit trước lần đọc thứ hai.

Điều kiện nhận diện: **cùng transaction, cùng hàng/đối tượng, hai lần đọc, giá trị khác nhau do một transaction khác commit ở giữa**.

~~~mermaid
sequenceDiagram
    participant T1
    participant DB as Database
    participant T2
    T1->>DB: R1(X) -> 10
    T2->>DB: W2(X = 20)
    T2->>DB: C2
    T1->>DB: R1(X) -> 20
~~~

Trong nhiều DBMS, `READ COMMITTED` cho phép non-repeatable read vì mỗi câu lệnh có thể lấy snapshot mới. `REPEATABLE READ` hoặc snapshot transaction phù hợp có thể ngăn cùng transaction nhìn thấy hai phiên bản khác nhau của hàng đó; hành vi chính xác tùy engine.

## 7. Phantom read — tập hàng phù hợp điều kiện thay đổi

Phantom read liên quan đến **tập kết quả** của một truy vấn điều kiện, thay vì chỉ giá trị của một hàng đã biết.

Giả sử T1 truy vấn các đơn hàng có trạng thái `OPEN`. Trong lúc đó, T2 thêm một đơn hàng mới thỏa điều kiện rồi commit.

**Lịch tối thiểu:**

~~~text
T1: R1(P) -> {đơn 1, đơn 2}
T2: W2(đơn 3 với status = OPEN), C2
T1: R1(P) -> {đơn 1, đơn 2, đơn 3}
~~~

`P` biểu diễn predicate `status = 'OPEN'`. T1 chạy lại cùng truy vấn và nhận thêm một hàng mới. Hàng mới là “phantom” vì nó không thuộc tập kết quả lần đầu nhưng xuất hiện ở lần sau.

Điều kiện nhận diện là **cùng truy vấn predicate được thực hiện lại và tập hàng thỏa điều kiện thay đổi do transaction khác commit**. Không nhất thiết một hàng cũ bị sửa; một hàng mới được insert hoặc một hàng cũ được sửa để bắt đầu thỏa predicate cũng có thể làm thay đổi tập kết quả.

### Phân biệt non-repeatable read và phantom

| Tiêu chí | Non-repeatable read | Phantom read |
| --- | --- | --- |
| Đối tượng quan sát | Một hàng đã đọc | Tập hàng thỏa điều kiện |
| Lần đọc lại | Cùng hàng có giá trị khác | Truy vấn predicate có số lượng/thành viên khác |
| Ví dụ | Đơn 1 đổi status từ OPEN sang PAID | Một đơn mới status OPEN xuất hiện |
| Cách diễn đạt tối thiểu | `R1(X=10), W2(X=20), C2, R1(X=20)` | `R1(P={a,b}), I2(c thuộc P), C2, R1(P={a,b,c})` |

Ranh giới không tuyệt đối trong mọi tài liệu: một hàng được cập nhật để vào/ra tập predicate có thể được mô tả vừa là thay đổi giá trị, vừa là thay đổi thành viên của tập. Khi phân loại, hãy nêu rõ đơn vị quan sát mà bài toán muốn nhấn mạnh.

## 8. Read skew — đọc các dữ liệu liên quan ở hai thời điểm khác nhau

Read skew (còn gọi là inconsistent analysis trong một số ngữ cảnh) xảy ra khi T1 đọc các đối tượng có quan hệ với nhau ở những thời điểm khác nhau, do đó ghép các giá trị thuộc hai trạng thái đã commit khác nhau.

Ví dụ hai tài khoản A và B có tổng số dư 200. T2 chuyển 30 từ A sang B, nên tổng phải luôn là 200. T1 đọc A trước khi T2 commit và đọc B sau khi T2 commit.

**Lịch tối thiểu:**

~~~text
Ban đầu: A = 100, B = 100
R1(A = 100),
W2(A = 70), W2(B = 130), C2,
R1(B = 130), C1
~~~

T1 tính tổng bằng 230, mặc dù trước và sau giao dịch chuyển tiền, tổng đã commit đều bằng 200. T1 không đọc giá trị chưa commit: lần đọc B diễn ra sau `C2`. Vấn đề là hai lần đọc của cùng báo cáo không dùng một snapshot chung.

Read skew thường được ngăn bằng transaction snapshot phù hợp, chẳng hạn PostgreSQL `REPEATABLE READ` cho nhiều truy vấn đọc trong cùng transaction. Chọn isolation cần căn cứ semantics của DBMS; một transaction `READ ONLY` ở `READ COMMITTED` vẫn có thể gặp read skew vì mỗi câu lệnh lấy snapshot mới.

## 9. Write skew — các giao dịch ghi khác hàng nhưng phá cùng một bất biến

Write skew là bất thường tinh vi hơn lost update. Hai transaction đọc cùng một trạng thái đáp ứng quy tắc, sau đó mỗi transaction cập nhật **một hàng khác nhau**. Không có ghi đè trên cùng hàng, nhưng kết quả kết hợp vi phạm bất biến tổng hợp.

Giả sử mỗi ca trực cần ít nhất một bác sĩ. Ban đầu A và B đều trực. Mỗi bác sĩ chỉ được nghỉ nếu còn một người khác trực.

**Lịch tối thiểu:**

~~~text
Ban đầu: A.on_call = true, B.on_call = true

T1: R1(A = true, B = true)
T2: R2(A = true, B = true)
T1: W1(A = false)
T2: W2(B = false)
C1, C2

Kết quả: A = false, B = false
~~~

T1 cập nhật hàng A; T2 cập nhật hàng B. Vì mỗi transaction ghi một hàng khác nhau nên kiểm soát xung đột ghi cùng hàng có thể không phát hiện. Tuy nhiên, cả hai cùng dựa vào điều kiện “còn người khác trực” từ snapshot ban đầu. Sau khi cả hai commit, không còn bác sĩ trực.

Điều kiện nhận diện:

1. Hai transaction đọc một tập dữ liệu chung hoặc cùng bất biến tổng hợp.
2. Mỗi transaction quyết định cập nhật dựa trên trạng thái đó.
3. Chúng ghi các đối tượng khác nhau, nên không nhất thiết có lost update trên cùng hàng.
4. Kết quả kết hợp vi phạm một quy tắc xuyên nhiều hàng.

Trong PostgreSQL, `REPEATABLE READ` dựa trên snapshot isolation và vẫn có thể cho phép write skew. `SERIALIZABLE` có thể phát hiện chu trình phụ thuộc và hủy một transaction; ứng dụng phải retry toàn bộ transaction khi gặp serialization failure. Một lựa chọn khác là khóa hàng đại diện chung mà mọi đường ghi đều phải tuân theo.

## 10. Dirty read/write và các bất thường “đọc lại” nhìn cạnh nhau

Bảng dưới đây giúp phân loại nhanh dựa trên thao tác tối thiểu gây ra vấn đề.

| Bất thường | Thao tác đặc trưng | Điều kiện thời gian then chốt |
| --- | --- | --- |
| Dirty read | `R2(X)` | T2 đọc sau `W1(X)` nhưng trước `C1`; T1 sau đó abort/rollback. |
| Dirty write | `W2(X)` | T2 ghi sau `W1(X)` nhưng trước khi T1 kết thúc. |
| Lost update | `R1(X)`, `R2(X)`, hai lần ghi | Hai transaction cùng dựa trên bản đọc cũ; lần ghi sau che mất cập nhật trước. |
| Non-repeatable read | `R1(X) ... R1(X)` | T2 commit thay đổi cùng hàng giữa hai lần đọc của T1. |
| Phantom read | `R1(P) ... R1(P)` | T2 commit làm thay đổi tập hàng thỏa predicate P. |
| Read skew | Đọc nhiều đối tượng có quan hệ | Các lần đọc thuộc các snapshot khác nhau và ghép thành trạng thái không nhất quán. |
| Write skew | Hai transaction đọc chung điều kiện rồi ghi khác hàng | Cả hai commit nhưng kết quả vi phạm bất biến tổng hợp. |

Không nên chỉ dựa vào tên hiện tượng. Hãy xác định **T2 làm gì với dữ liệu T1 đã ghi, commit xảy ra khi nào, truy vấn đọc một hàng hay một tập hàng, và các transaction ghi cùng hay khác đối tượng**.

## 11. Một bộ lịch tối thiểu dùng để ôn tập

Các lịch sau được cố ý rút gọn. Mỗi lịch chỉ giữ thao tác cần thiết để nhận ra một bất thường.

### A. Dirty read

~~~text
W1(X = 1), R2(X = 1), A1
~~~

T2 đọc giá trị do T1 ghi trước commit; T1 rollback.

### B. Dirty write

~~~text
W1(X = 1), W2(X = 2), A1
~~~

T2 ghi cùng X trước khi T1 kết thúc.

### C. Lost update

~~~text
R1(X = 0), R2(X = 0),
W1(X = 1), C1,
W2(X = 2), C2
~~~

T2 ghi giá trị tính từ bản đọc cũ, làm mất cập nhật của T1.

### D. Non-repeatable read

~~~text
R1(X = 0), W2(X = 1), C2, R1(X = 1), C1
~~~

T1 đọc cùng một hàng hai lần và nhận hai giá trị.

### E. Phantom read

~~~text
R1(P = {a}), I2(b thuộc P), C2, R1(P = {a,b}), C1
~~~

T2 thêm hàng b thỏa điều kiện P; lần truy vấn lại của T1 thấy tập kết quả lớn hơn.

### F. Read skew

~~~text
R1(A = 100), W2(A = 70), W2(B = 130), C2, R1(B = 130), C1
~~~

T1 ghép A cũ với B mới trong khi bất biến tổng A+B phải bằng 200.

### G. Write skew

~~~text
R1(A = on, B = on), R2(A = on, B = on),
W1(A = off), W2(B = off), C1, C2
~~~

T1 và T2 ghi hàng khác nhau, nhưng cả hai cùng phá bất biến còn ít nhất một bác sĩ trực.

## 12. Lịch nào được phép dưới isolation nào?

Isolation level mô tả những loại tương tác đồng thời nào được phép quan sát và kết quả lịch cần tương đương đến đâu. Tuy nhiên, tên mức isolation không phải một thuật toán thống nhất trên mọi DBMS.

| Mức cô lập theo mô hình SQL | Dirty read | Non-repeatable read | Phantom | Ghi chú |
| --- | --- | --- | --- | --- |
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể | Engine có thể thực thi mạnh hơn mức tối thiểu; dirty write vẫn thường bị ngăn. |
| `READ COMMITTED` | Không | Có thể | Có thể | Snapshot thường được xác định theo câu lệnh ở PostgreSQL. |
| `REPEATABLE READ` | Không | Không theo định nghĩa truyền thống | Tùy cách triển khai/định nghĩa và engine | PostgreSQL dùng snapshot isolation; write skew vẫn có thể xuất hiện. |
| `SERIALIZABLE` | Không | Không | Không theo mục tiêu tuần tự hóa | Hệ thống có thể abort transaction để bảo toàn serializability; cần retry. |

Dirty write thường không được chấp nhận trong các DBMS quan hệ thông dụng, kể cả khi cấu hình mức đọc thấp. Một bảng isolation truyền thống có thể không liệt kê dirty write như một hiện tượng được phép/không được phép, vì đó là yêu cầu điều phối writer nền tảng của engine.

PostgreSQL nhận cú pháp `READ UNCOMMITTED` nhưng hành xử như `READ COMMITTED`. Với PostgreSQL `REPEATABLE READ`, snapshot ổn định giúp ngăn non-repeatable read và phantom theo cách quan sát thông thường, nhưng write skew vẫn có thể xảy ra; `SERIALIZABLE` bổ sung kiểm soát để bảo vệ tính tương đương tuần tự.

## 13. Cách phân tích một lịch mới

Khi gặp lịch giao dịch trong bài tập hoặc trace production, hãy làm theo các bước sau.

**Bước 1 — Xác định đối tượng và phạm vi.** X và Y có phải cùng hàng không? P có phải predicate truy vấn trên cả tập dữ liệu không? Bất biến có trải qua nhiều hàng không?

**Bước 2 — Viết lại theo transaction.** Tách thao tác của T1, T2, ... và giữ nguyên thứ tự bên trong mỗi transaction.

**Bước 3 — Đánh dấu commit/abort.** Không phân loại dirty read/write khi thiếu thông tin transaction trước đã kết thúc hay chưa.

**Bước 4 — Theo dõi giá trị và phiên bản.** Ghi rõ transaction đọc giá trị nào, phiên bản nào; lần ghi sau dựa trên giá trị hiện hành hay bản đọc cũ.

**Bước 5 — Tìm lần đọc hoặc ghi lặp.** Cùng hàng đổi giá trị gợi ý non-repeatable read; cùng predicate đổi tập kết quả gợi ý phantom; đọc nhiều đối tượng không cùng snapshot gợi ý read skew.

**Bước 6 — Kiểm tra bất biến kết hợp.** Nếu hai transaction ghi các hàng khác nhau nhưng cùng điều kiện nghiệp vụ, hãy xem xét write skew.

**Bước 7 — Đối chiếu khả năng thực thi của DBMS.** Một lịch dùng để minh họa lý thuyết có thể bị engine chặn hoặc abort. Phân biệt “lịch thể hiện bất thường” với “DBMS đang dùng có cho phép lịch này hay không”.

~~~mermaid
flowchart TD
    A[Đọc lịch thao tác] --> B{T2 đọc hay ghi lên dữ liệu T1 chưa commit?}
    B -- Đọc --> C[Dirty read]
    B -- Ghi --> D[Dirty write]
    B -- Không --> E{Cùng một hàng được đọc lại?}
    E -- Có, giá trị đổi --> F[Non-repeatable read]
    E -- Không --> G{Tập hàng theo predicate đổi?}
    G -- Có --> H[Phantom read]
    G -- Không --> I{Hai lần đọc ghép nhiều snapshot?}
    I -- Có --> J[Read skew]
    I -- Không --> K{Hai transaction đọc chung quy tắc rồi ghi hàng khác?}
    K -- Có --> L[Write skew]
    K -- Không --> M{Ghi sau dựa trên bản đọc cũ và che mất cập nhật?}
    M -- Có --> N[Lost update]
    M -- Không --> O[Kiểm tra lịch và bất biến khác]
~~~

Sơ đồ là công cụ định hướng. Một lịch phức tạp có thể chứa **nhiều hơn một bất thường**, nên hãy xác định từng quan hệ thao tác thay vì ép mọi lịch vào đúng một nhãn.

## 14. Cách ngăn các bất thường thường gặp

| Bất thường | Biện pháp thường dùng | Lưu ý |
| --- | --- | --- |
| Dirty read | Đọc phiên bản đã commit; isolation phù hợp | Các DBMS quan hệ phổ biến ngăn dirty read ở READ COMMITTED trở lên. |
| Dirty write | Khóa ghi/điều phối writer | Không cho writer chồng lên thay đổi chưa commit của writer khác. |
| Lost update | Conditional update, optimistic version, khóa hàng, isolation mạnh phù hợp | Kiểm tra kết quả cập nhật; retry hoặc báo conflict. |
| Non-repeatable read | Snapshot transaction hoặc isolation phù hợp | Xác định semantics của engine. |
| Phantom read | Predicate/range locking hoặc serializable/snapshot semantics phù hợp | Cần bảo vệ tập kết quả, không chỉ các hàng đã đọc. |
| Read skew | Cùng snapshot cho các lần đọc liên quan | READ ONLY một mình chưa đủ nếu mỗi statement có snapshot mới. |
| Write skew | Serializable hoặc khóa đại diện chung; mô hình dữ liệu/ràng buộc phù hợp | Khóa phải được mọi đường ghi tuân thủ. |

Không có một mức isolation duy nhất là lựa chọn tối ưu cho mọi nghiệp vụ. Mức cô lập mạnh hơn có thể tăng chờ đợi, xung đột hoặc serialization failure. Cần xác định bất biến nào phải đúng, sau đó chọn cơ chế bảo vệ chính xác.

## 15. Những nhầm lẫn thường gặp

- **“Hai transaction cùng ghi một hàng thì là dirty write.”** Chỉ dirty write khi lần ghi sau diễn ra trước khi transaction ghi trước kết thúc. Ghi nối tiếp sau commit không phải dirty write.
- **“T1 rollback sau khi T2 đọc thì đó là dirty write.”** Nếu T2 đọc, đó là dirty read. Dirty write đòi hỏi thao tác ghi của T2 lên dữ liệu chưa commit.
- **“Lost update là dirty write.”** Lost update có thể xảy ra sau khi lần ghi đầu đã commit; T2 ghi đè dựa trên một bản đọc cũ.
- **“Non-repeatable read và phantom read giống nhau.”** Một hiện tượng nhấn vào giá trị cùng hàng; hiện tượng kia nhấn vào thành viên của tập hàng thỏa predicate.
- **“Read skew là dirty read.”** Read skew có thể chỉ đọc các phiên bản đã commit nhưng đến từ các snapshot khác nhau.
- **“Write skew là lost update.”** Hai giao dịch write skew có thể cập nhật hai hàng khác nhau, không có một lần ghi nào ghi đè cùng hàng của lần ghi kia.
- **“REPEATABLE READ luôn ngăn write skew.”** Không đúng với snapshot isolation của PostgreSQL. Cần hiểu semantics engine hoặc dùng SERIALIZABLE/khóa chung phù hợp.
- **“Sơ đồ lịch lý thuyết chứng minh DBMS sẽ thực thi lịch đó.”** DBMS thực tế có thể chặn lệnh, phát hiện xung đột hoặc abort transaction.

## 16. Tình huống luyện tập

### Tình huống A — Số dư tài khoản

Ban đầu `balance = 500`. T1 đọc 500. T2 cộng 100 rồi commit. T1 ghi 450 dựa trên số liệu 500 và commit. Hãy xác định bất thường.

Đây là **lost update** nếu nghiệp vụ của T1 là trừ 50: T1 lẽ ra cần tạo 550 sau khi T2 cộng 100, nhưng ghi 450 từ bản đọc cũ đã làm mất cập nhật T2. Không phải dirty write vì T2 đã commit trước lần ghi của T1.

### Tình huống B — Đơn hàng thay đổi trạng thái

T1 đọc đơn hàng là `PENDING`. T2 đổi sang `PAID` và commit. T1 đọc lại cùng đơn hàng và thấy `PAID`.

Đây là **non-repeatable read**: cùng hàng được đọc hai lần trong một transaction, giá trị đổi do transaction khác đã commit.

### Tình huống C — Báo cáo số dư

T1 đọc tài khoản A. T2 chuyển tiền giữa A và B rồi commit. T1 đọc tài khoản B và tổng hai số dư không còn bằng tổng ban đầu.

Đây là **read skew** nếu hai lần đọc T1 thuộc hai snapshot khác nhau. Cần snapshot nhất quán cho báo cáo.

### Tình huống D — Phân ca trực

T1 đọc A và B đều đang trực. T2 đọc cùng trạng thái. T1 cho A nghỉ; T2 cho B nghỉ. Hai transaction cùng commit.

Đây là **write skew** nếu bất biến yêu cầu ít nhất một người trực. Hai transaction ghi các hàng khác nhau nhưng phá cùng một điều kiện tổng hợp.

### Tình huống E — Hai người cùng đặt một ghế

T1 đánh dấu ghế là đang giữ nhưng chưa commit. T2 cố ghi trạng thái ghế đó cho khách khác.

Dirty write sẽ xảy ra nếu T2 thực sự ghi chồng lên thay đổi chưa commit của T1. DBMS thông dụng cần điều phối ghi cạnh tranh; nếu T2 chỉ đọc trạng thái chưa commit của T1 thì đó lại là dirty read.

## 17. Kết luận

Lịch tối thiểu là cách thu gọn một bất thường thành các thao tác thực sự quyết định kết quả. Để phân biệt chính xác, hãy tập trung vào **đối tượng được đọc/ghi, thứ tự thao tác, thời điểm commit/abort, snapshot quan sát và bất biến nghiệp vụ**.

Dirty read là đọc dữ liệu chưa commit; dirty write là ghi lên thay đổi chưa commit; lost update là làm mất cập nhật dựa trên bản đọc cũ; non-repeatable read là cùng hàng đổi giá trị khi đọc lại; phantom là tập hàng thỏa predicate thay đổi; read skew là ghép dữ liệu từ các snapshot khác nhau; write skew là các transaction ghi khác hàng nhưng phá một bất biến chung.

Một lịch có thể minh họa bất thường dù DBMS thực tế sẽ chặn hoặc abort nó. Phân tích tốt vì thế luôn có hai phần: **xác định lịch thể hiện điều gì** và **xác định cơ chế của DBMS nào ngăn hoặc cho phép lịch ấy**.
