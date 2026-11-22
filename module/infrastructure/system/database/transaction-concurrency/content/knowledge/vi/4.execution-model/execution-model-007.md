# Lịch có thể phục hồi và nguy cơ hủy bỏ dây chuyền

## 1. Bối cảnh: giao dịch chạy xen kẽ và phụ thuộc lẫn nhau

Khi nhiều giao dịch (transaction) truy cập cùng cơ sở dữ liệu, hệ quản trị thường xen kẽ các thao tác của chúng để tăng mức sử dụng tài nguyên và giảm thời gian chờ. Một giao dịch có thể đọc dữ liệu trong khi giao dịch khác đang sửa dữ liệu ấy. Thứ tự xen kẽ này được gọi là **lịch thực thi** (*schedule* hoặc *history*).

Không phải mọi lịch thực thi đều an toàn khi xảy ra lỗi. Vấn đề đặc biệt nguy hiểm là một giao dịch **đọc kết quả chưa commit** của giao dịch khác, dùng kết quả đó để tính toán rồi tiếp tục ghi dữ liệu hoặc thậm chí commit. Nếu giao dịch đầu tiên bị hủy, các quyết định dựa trên dữ liệu của nó có thể trở thành sai.

Ví dụ, đơn hàng T1 đang chuẩn bị giảm số tồn kho từ 10 xuống 7 nhưng chưa commit. Giao dịch T2 đọc số tồn kho 7 và tính toán kế hoạch nhập hàng. Sau đó T1 bị rollback, số tồn kho trở lại 10. Kết quả mà T2 tính từ giá trị 7 không còn có cơ sở hợp lệ trong trạng thái đã commit.

Từ câu hỏi “**Điều gì xảy ra nếu giao dịch tạo ra dữ liệu bị rollback?**”, lý thuyết điều khiển đồng thời phân biệt ba cấp độ quan trọng:

- **Recoverable schedule (lịch có thể phục hồi):** giao dịch đã đọc kết quả của giao dịch khác không được commit trước giao dịch cung cấp dữ liệu.
- **Cascadeless schedule / ACA (lịch không hủy bỏ dây chuyền):** giao dịch chỉ đọc kết quả của giao dịch khác sau khi kết quả đó đã commit.
- **Strict schedule (lịch nghiêm ngặt):** một giao dịch không đọc hoặc ghi đè dữ liệu mà giao dịch khác đã ghi nhưng chưa commit hay abort.

Ba khái niệm này thuộc **mô hình thực thi giao dịch**, giúp lý giải khả năng rollback an toàn và chi phí khôi phục. Chúng không có cùng ý nghĩa với *serializability*, *durability* hay cơ chế khôi phục sau khi máy chủ gặp sự cố.

### 1.1. Một giao dịch có thể thất bại khi nào?

Giao dịch có thể bị hủy vì:

- Ứng dụng phát hiện điều kiện nghiệp vụ không còn hợp lệ.
- Cơ sở dữ liệu phát hiện vi phạm ràng buộc như `UNIQUE` hoặc `CHECK`.
- Deadlock khiến một giao dịch bị chọn làm nạn nhân.
- Xung đột ở mức cô lập mạnh gây serialization failure.
- Ứng dụng chủ động gọi `ROLLBACK`.
- Lỗi hạ tầng buộc hệ thống hủy những transaction chưa commit.

Chính vì lỗi có thể xuất hiện ở nhiều thời điểm, một lịch thực thi phải được đánh giá cả trong tình huống **transaction sinh dữ liệu chưa kịp commit mà đã abort**.

## 2. Ký hiệu của một lịch thực thi

Để mô tả chính xác, sử dụng các ký hiệu sau:

| Ký hiệu | Ý nghĩa |
|---|---|
| `T1`, `T2`, `T3` | Các giao dịch khác nhau |
| `r1(X)` | T1 đọc mục dữ liệu X |
| `w1(X)` | T1 ghi mục dữ liệu X |
| `c1` | T1 commit thành công |
| `a1` | T1 abort hoặc rollback toàn bộ |
| `r2(X) <- w1(X)` | T2 đọc phiên bản X do T1 ghi (*reads-from dependency*) |

Một lịch có thể viết theo thứ tự từ trái qua phải:

~~~text
S = w1(X)  r2(X)  c1  c2
    ------> thời gian ------->
~~~

Trong lịch này, T1 ghi X, T2 đọc giá trị X do T1 ghi, T1 commit rồi T2 mới commit.

Mỗi giao dịch có thứ tự thao tác nội bộ riêng. Khi ghép các giao dịch thành schedule, hệ thống có thể xen kẽ thao tác của các giao dịch nhưng vẫn phải giữ thứ tự đã được định nghĩa bên trong từng giao dịch.

### 2.1. “Đọc từ” là quan hệ quan trọng nhất

Giả sử giá trị ban đầu của X là 100:

~~~text
T1: w1(X = 120) -------- c1
T2:          r2(X = 120) -------- c2
~~~

Nếu T2 thực sự đọc giá trị 120 do T1 tạo ra, ta có quan hệ:

~~~text
T1 --cung cấp phiên bản X--> T2
~~~

T2 **phụ thuộc dữ liệu** vào T1. Nếu T1 bị rollback, giá trị 120 không tồn tại trong lịch sử commit hợp lệ; vì vậy các quyết định mà T2 tạo từ 120 phải được xem xét lại.

Cần phân biệt với trường hợp T2 đọc **phiên bản đã commit cũ** của X trong hệ thống MVCC dù T1 đang có phiên bản mới chưa commit. Khi ấy T2 không có quan hệ *reads-from* với thay đổi chưa commit của T1 chỉ vì hai transaction cùng truy cập tên hàng X.

Một phép đọc trong cùng giao dịch từ dữ liệu do chính giao dịch đó vừa ghi cũng không tạo phụ thuộc rollback giữa hai transaction khác nhau.

### 2.2. Đọc bẩn là điều kiện có thể tạo ra phụ thuộc nguy hiểm

**Dirty read** xảy ra khi T2 đọc một phiên bản do T1 ghi nhưng T1 chưa commit.

~~~text
Giá trị đã commit trước đó: X = 100

T1: BEGIN -- w1(X = 120) ------------------- ?
T2:                  r2(X = 120) -- tính toán tiếp
~~~

Dấu hỏi là kết thúc chưa biết của T1. Nếu T1 commit, giá trị 120 cuối cùng trở thành hợp lệ. Nếu T1 abort, T2 đã dùng dữ liệu chưa từng trở thành trạng thái đã commit.

Tuy nhiên, **chỉ dirty read chưa tự động khiến lịch không thể phục hồi**. Tính có thể phục hồi còn phụ thuộc vào **thứ tự commit** của T2 so với T1.

## 3. Lịch có thể phục hồi (recoverable schedule)

### 3.1. Định nghĩa

Một lịch là **recoverable** nếu với mọi cặp giao dịch khác nhau Ti, Tj, khi Tj đọc một giá trị do Ti ghi thì Tj chỉ được commit **sau khi Ti đã commit**.

Viết ngắn gọn:

\[
T_j\ \text{reads-from}\ T_i
\quad\land\quad
c_j\ \text{xảy ra}
\quad\Longrightarrow\quad
c_i < c_j
\]

Trong đó dấu `<` là quan hệ thứ tự thời gian trong schedule, không phải phép so sánh giá trị dữ liệu.

Nếu Ti abort, Tj đã đọc dữ liệu chưa commit của Ti sẽ không thể commit hợp lệ theo điều kiện trên. Tj phải được hủy hoặc được xử lý lại theo cơ chế thích hợp.

**Recoverable chỉ yêu cầu thứ tự commit an toàn đối với phụ thuộc đọc. Nó vẫn có thể cho phép Tj đọc dữ liệu chưa commit của Ti.** Đây là điểm giải thích vì sao recoverable schedule chưa tránh được hủy bỏ dây chuyền.

### 3.2. Lịch recoverable nhưng vẫn có dirty read

Xem lịch:

~~~text
S1 = w1(X)  r2(X)  c1  c2

Thời gian -->
T1: [w1(X)] ---------------- [COMMIT]
T2:            [r2(X)] ---------------- [COMMIT]
~~~

T2 đọc dữ liệu T1 chưa commit. Tuy nhiên T1 commit trước T2, nên khi T2 commit, giao dịch cung cấp dữ liệu đã được xác nhận. Đây là **lịch recoverable**.

Sự an toàn này còn mong manh khi có lỗi:

~~~text
S1' = w1(X)  r2(X)  a1  a2
~~~

Sau khi T1 abort, T2 buộc phải abort vì đã sử dụng giá trị không còn hợp lệ. Lịch có khả năng giữ quan hệ commit an toàn vì T2 chưa commit, nhưng nó tạo **rollback lan truyền** và lãng phí công việc T2 đã thực hiện.

### 3.3. Lịch không thể phục hồi (non-recoverable schedule)

~~~text
S2 = w1(X)  r2(X)  c2  a1
~~~

| Thứ tự | Sự kiện | Hệ quả |
|---:|---|---|
| 1 | T1 ghi X nhưng chưa commit | X là phiên bản tạm thời |
| 2 | T2 đọc X từ T1 | T2 phụ thuộc vào T1 |
| 3 | T2 commit | T2 xác nhận kết quả dựa trên X tạm thời |
| 4 | T1 abort | Giá trị X mà T2 dùng bị hủy |

T2 đã commit nên thông thường **không thể dùng ROLLBACK của T2 để hoàn tác** phần việc đã commit như đối với một transaction còn đang mở. Hệ thống có thể cần nghiệp vụ bù trừ, sửa dữ liệu hoặc đối soát ngoài giao dịch ban đầu. Không có một thứ tự commit an toàn tương ứng với quan hệ T2 đọc từ T1.

Ngay cả khi T1 cuối cùng cũng commit, lịch `w1(X) r2(X) c2 c1` vẫn được phân loại là **non-recoverable** theo định nghĩa vì T2 đã commit trước T1. Đánh giá dựa trên **khả năng xử lý nếu T1 thất bại**, không phải chỉ nhìn kết quả cuối của một lần chạy may mắn.

### 3.4. Recoverable không đồng nghĩa “có thể khôi phục sau sự cố máy chủ”

Trong lý thuyết schedule, *recoverable* là tính chất **thứ tự commit đối với giao dịch đọc phụ thuộc**. Nó khác với:

- **Crash recovery:** dùng transaction log, checkpoint, redo/undo để khôi phục trạng thái sau khi tiến trình hoặc máy chủ dừng đột ngột.
- **Durability:** dữ liệu đã commit tồn tại theo bảo đảm của hệ quản trị và cấu hình lưu trữ.
- **Backup/restore:** phục hồi dữ liệu từ bản sao lưu.
- **Compensating transaction:** tạo nghiệp vụ mới để bù một thay đổi đã commit, không phải rollback nguyên trạng một transaction đã kết thúc.

Một database có WAL tốt vẫn không thể tự động biến một schedule cho phép T2 commit phụ thuộc vào dữ liệu chưa commit của T1 thành lịch recoverable. Đó là trách nhiệm của thiết kế và cơ chế điều khiển đồng thời.

## 4. Hủy bỏ dây chuyền (cascading abort) hình thành như thế nào?

### 4.1. Từ một giao dịch thất bại sang nhiều giao dịch bị ảnh hưởng

Giả sử T1 cập nhật giá trị X; T2 đọc X và ghi Y; T3 đọc Y rồi ghi Z:

~~~text
S3 = w1(X)  r2(X)  w2(Y)  r3(Y)  w3(Z)  a1  a2  a3

      X                Y                 Z
     T1  -----------> T2  ------------> T3
      |                |                 |
      +-- abort ------ +-- phải abort -- +-- phải abort
~~~

T2 chưa commit nhưng kết quả Y của nó phụ thuộc vào X do T1 tạo ra. Khi T1 abort:

1. Thay đổi X của T1 không còn hiệu lực.
2. T2 đã dựa vào X chưa commit để tạo Y, nên T2 phải abort hoặc tính lại trong một transaction mới.
3. T3 đọc Y chưa commit từ T2, nên T3 cũng phải abort hoặc làm lại.
4. Công việc của T2 và T3 trở thành lãng phí dù bản thân câu lệnh của chúng không gặp lỗi dữ liệu.

Đây là **cascading abort**, còn gọi là *cascading rollback*: một quyết định rollback kéo theo nhiều transaction phụ thuộc bị hủy.

Một chuỗi không nhất thiết chỉ có một nhánh. Nếu T1 có nhiều transaction đọc dữ liệu chưa commit từ nó, mỗi transaction có thể tạo nhiều phụ thuộc tiếp:

~~~text
                     T2 ----> T4
                   /   \
T1 (abort) -------      T5
                   \
                     T3 ----> T6 ----> T7
~~~

Một abort ở T1 có thể tác động tới toàn bộ nhóm giao dịch phụ thuộc trực tiếp hoặc gián tiếp chưa commit.

### 4.2. Minh họa nghiệp vụ

Một hệ thống đặt hàng có các giao dịch:

- **T1:** điều chỉnh lượng hàng có thể xuất của kho, chưa commit.
- **T2:** đọc lượng hàng T1 vừa điều chỉnh để tính kế hoạch đóng gói.
- **T3:** đọc kế hoạch đóng gói T2 vừa ghi để lên lịch giao hàng.

Giả sử T1 bị rollback vì vi phạm quy tắc tồn kho. Nếu T2 và T3 đã đọc dữ liệu chưa commit, chúng đang dựa trên thông tin mà database sau đó phủ nhận. Cần hủy hoặc thực hiện lại các công việc phụ thuộc; trong trường hợp chúng đã gửi sự kiện hoặc gọi dịch vụ bên ngoài, rollback database còn không thể tự thu hồi các tác động đó.

Tình huống này cho thấy vấn đề không chỉ là tính đúng đắn. **Chi phí thực thi bị lãng phí và độ trễ tăng** khi nhiều giao dịch phải xử lý lại sau cùng một lỗi gốc.

### 4.3. Nguy cơ lớn hơn khi độ sâu và độ rộng phụ thuộc tăng

Ta có thể mô tả quan hệ bằng đồ thị:

- Mỗi **nút** là một transaction.
- Cạnh `Ti → Tj` nghĩa là Tj đã đọc một giá trị được Ti ghi.
- Nếu Ti abort, các giao dịch chưa commit nằm trong nhánh phụ thuộc vào Ti có thể phải abort theo.

Ở mô hình lý tưởng hóa, nếu đồ thị có nhiều cạnh lan ra và nhiều tầng, một lỗi đơn lẻ có thể làm tiêu tốn khối lượng công việc rất lớn. Số lượng phụ thuộc càng cao, khả năng lãng phí càng lớn.

Không nên hiểu đồ thị phụ thuộc đọc này là toàn bộ đồ thị tranh chấp (*conflict graph*) dùng kiểm tra serializability; đồ thị tranh chấp còn xét nhiều quan hệ đọc–ghi và ghi–ghi khác.

### 4.4. Recoverable vẫn có thể chịu cascading abort

Lịch `w1(X) r2(X) w2(Y) r3(Y) a1 a2 a3` **không chứa giao dịch phụ thuộc nào đã commit trước nguồn dữ liệu**. Vì vậy nó không vi phạm điều kiện commit của recoverability; tuy nhiên, nó rõ ràng không tránh được cascading abort.

Đây là lý do hệ thống thực tế thường muốn mức bảo vệ mạnh hơn **recoverable**, cụ thể là **cascadeless**.

## 5. Lịch không hủy bỏ dây chuyền (cascadeless schedule)

### 5.1. Định nghĩa

Một lịch được gọi là **cascadeless** hoặc **ACA – Avoids Cascading Aborts** nếu một transaction chỉ đọc giá trị do transaction khác ghi **sau khi transaction ghi đã commit**.

Với mỗi quan hệ Tj đọc giá trị do Ti ghi:

\[
T_j\ \text{reads-from}\ T_i
\quad\Longrightarrow\quad
c_i < r_j(X)
\]

Ở đây điều kiện được đặt tại **thời điểm đọc**, mạnh hơn điều kiện recoverable đặt tại thời điểm commit của transaction phụ thuộc.

Không có giao dịch nào được phép lấy một giá trị **chưa commit của giao dịch khác** làm đầu vào. Vì vậy khi Ti abort, các giao dịch khác không bị buộc rollback chỉ vì đã đọc phiên bản chưa commit của Ti.

### 5.2. So sánh hai lịch gần giống nhau

**Lịch A – recoverable nhưng không cascadeless:**

~~~text
w1(X)   r2(X)   c1   c2
        ^
        T2 đọc X trước khi T1 commit
~~~

**Lịch B – cascadeless:**

~~~text
w1(X)   c1   r2(X)   c2
               ^
               T2 chỉ đọc sau khi T1 đã commit
~~~

Cả A và B đều có thứ tự commit T1 trước T2. Nhưng chỉ B tránh được việc đọc dữ liệu chưa commit.

### 5.3. Tại sao cascadeless kéo theo recoverable?

Nếu T2 chỉ đọc kết quả của T1 **sau `c1`**, và T2 commit sau phép đọc của chính mình, hiển nhiên `c1` xảy ra trước `c2`. Do đó:

\[
\text{Cascadeless} \Longrightarrow \text{Recoverable}
\]

Điều ngược lại **không đúng**: lịch `w1(X) r2(X) c1 c2` là phản ví dụ recoverable nhưng không cascadeless.

### 5.4. Tránh dirty read bằng cách nào?

Hai cơ chế phổ biến:

**Cách 1 – đọc chờ đến khi writer commit/abort**

~~~text
T1: w1(X) ----------------- c1
T2:       r2(X) yêu cầu
          [chờ T1] -------- r2(X) --> c2
~~~

Một cơ chế khóa phù hợp có thể không cho T2 đọc phiên bản đang được T1 ghi chưa commit.

**Cách 2 – đọc phiên bản đã commit trước đó (MVCC)**

~~~text
Phiên bản X=100 đã commit
T1 tạo phiên bản X=120 nhưng chưa commit
T2 đọc X=100 từ snapshot hợp lệ
T1 commit hoặc abort sau đó
~~~

Trong trường hợp này, T2 không phải chờ T1 để đọc bản đã commit cũ, nhưng nó cũng **không đọc phiên bản chưa commit** do T1 tạo. Khả năng nhìn thấy dữ liệu phụ thuộc isolation level và quy tắc snapshot của từng engine.

Cả hai cách đều hướng tới tránh phụ thuộc đọc bẩn. Tuy nhiên, tránh dirty read chưa bảo đảm mọi quy tắc nghiệp vụ đồng thời; lost update, write skew và các bất biến trên nhiều hàng là vấn đề riêng.

## 6. Lịch nghiêm ngặt (strict schedule)

### 6.1. Định nghĩa

Một lịch được gọi là **strict** nếu sau khi Ti ghi X, không có giao dịch khác được **đọc hoặc ghi X** cho đến khi Ti **commit hoặc abort**.

~~~text
w1(X) -------- c1/a1 -------- r2(X) hoặc w2(X)
       ^ cấm giao dịch khác đọc/ghi X ở đoạn này ^
~~~

Nói cách khác, một **giá trị do transaction chưa kết thúc ghi ra** phải được bảo vệ khỏi cả:

1. **Dirty read:** đọc giá trị chưa commit của Ti.
2. **Dirty write:** ghi đè dữ liệu mà Ti vừa ghi trong khi Ti chưa kết thúc.

Strict schedule bổ sung sự bảo vệ đối với thao tác **ghi-ghi** so với cascadeless.

### 6.2. Vì sao phải ngăn dirty write?

Giả sử ban đầu `X = 10`:

~~~text
T1: w1(X = 20) ---------------- a1
T2:            w2(X = 30) ---------------- c2
~~~

T2 ghi X=30 khi thay đổi X=20 của T1 vẫn chưa commit. Nếu T1 rollback, bộ quản lý khôi phục phải bảo đảm **undo của T1 không vô tình xóa cập nhật hợp lệ của T2**. Việc chồng nhiều phiên bản ghi chưa kết thúc lên cùng dữ liệu làm logic phục hồi phức tạp và dễ phát sinh sai sót nếu quản lý không đúng.

Một lịch strict tránh trường hợp đó:

~~~text
T1: w1(X = 20) ---- a1
T2:              [chờ] ---- w2(X = 30) ---- c2
~~~

Sau khi T1 abort, T2 mới được ghi X; T2 bắt đầu từ trạng thái mà database đã khôi phục hợp lệ.

Các hệ quản trị giao dịch thông dụng thường không cho hai transaction ghi đè tùy ý lên cùng bản ghi chưa commit mà không có điều phối khóa/xung đột.

### 6.3. Strict kéo theo cascadeless

Nếu mọi giao dịch khác đều không được đọc X trong lúc transaction viết X còn chưa kết thúc, thì một giao dịch không thể đọc **giá trị chưa commit** của transaction đó. Nếu transaction ghi abort, phiên bản chưa commit bị hủy; nếu commit, phiên bản đã được xác nhận trước khi có transaction khác đọc nó.

Do đó, theo mô hình lịch đọc/ghi giao dịch chuẩn:

\[
\text{Strict} \Longrightarrow \text{Cascadeless}
\Longrightarrow \text{Recoverable}
\]

Chiều ngược lại đều không đúng.

### 6.4. Cascadeless chưa chắc strict

Lịch:

~~~text
S4 = w1(X)  w2(X)  c1  c2
~~~

Không có transaction nào đọc dữ liệu chưa commit, nên lịch có thể thỏa điều kiện **cascadeless** dựa trên quan hệ đọc. Nhưng T2 ghi đè X trong lúc T1 chưa kết thúc, nên **không strict**.

Lịch này là ví dụ lý thuyết để phân biệt định nghĩa. Nhiều DBMS thực tế sẽ chặn hoặc xử lý xung đột ghi-ghi, không cho lịch trần như vậy xảy ra trực tiếp.

### 6.5. Strict không buộc mọi transaction chạy tuần tự

Ví dụ:

~~~text
T1: w1(X) ----------------- c1
T2:     w2(Y) ---- c2
~~~

T1 ghi X, T2 ghi Y; không cùng mục dữ liệu. Hai transaction có thể xen kẽ và T2 commit trước T1 mà lịch vẫn strict, vì T2 không đọc hoặc ghi phiên bản X đang chưa commit của T1.

Strict nghĩa là **bảo vệ xung đột trên dữ liệu chưa kết thúc**, không có nghĩa hệ thống chỉ cho chạy một transaction tại một thời điểm.

## 7. Quan hệ giữa ba loại lịch

~~~text
+----------------------------------------------------------+
|                 RECOVERABLE SCHEDULES                    |
|   Cho phép đọc chưa commit, nhưng phải tuân thủ thứ tự    |
|   commit của quan hệ đọc phụ thuộc.                      |
|                                                          |
|    +----------------------------------------------+      |
|    |               CASCADELESS / ACA              |      |
|    |  Không đọc dữ liệu chưa commit của giao dịch  |      |
|    |  khác.                                       |      |
|    |                                              |      |
|    |      +-------------------------------+       |      |
|    |      |            STRICT             |       |      |
|    |      |  Không đọc hoặc ghi đè dữ     |       |      |
|    |      |  liệu chưa kết thúc.          |       |      |
|    |      +-------------------------------+       |      |
|    +----------------------------------------------+      |
+----------------------------------------------------------+
~~~

| Đặc tính | Recoverable | Cascadeless | Strict |
|---|---|---|---|
| Giao dịch phụ thuộc phải commit sau giao dịch cung cấp dữ liệu | Có | Có | Có |
| Cấm đọc dữ liệu chưa commit từ transaction khác | Không bắt buộc | Có | Có |
| Tránh cascading abort vì dirty read | Không bảo đảm | Có | Có |
| Cấm ghi đè dữ liệu do transaction khác ghi nhưng chưa kết thúc | Không bắt buộc | Không bắt buộc | Có |
| Giúp đơn giản hóa quản lý undo của các lần ghi chồng lấn | Không bảo đảm | Không bảo đảm | Có |
| Tự bảo đảm serializability | Không | Không | Không |

**Một lịch strict vẫn có thể không serializable**, và một lịch conflict-serializable vẫn có thể không recoverable. Cần đánh giá hai nhóm tính chất riêng.

## 8. Recoverability khác serializability ở đâu?

### 8.1. Hai câu hỏi hoàn toàn khác nhau

**Serializability** hỏi:

> Hiệu ứng của lịch các transaction đã hoàn tất có tương đương với một thứ tự chạy tuần tự hợp lệ hay không?

**Recoverability** hỏi:

> Nếu transaction Ti bị hủy, liệu có transaction Tj đã commit mà trước đó sử dụng kết quả chưa commit của Ti hay không?

Serializability tập trung vào **tính đúng đắn của thứ tự đọc/ghi đối với lịch tuần tự**. Recoverability tập trung vào **thứ tự commit và quan hệ phụ thuộc đọc**, đặc biệt khi có rollback.

### 8.2. Có thể serializable nhưng không recoverable

Xét lịch:

~~~text
S5 = w1(X)  r2(X)  c2  c1
~~~

Xét các thao tác đọc/ghi xung đột, có cạnh T1 → T2, không có cạnh ngược, nên phần thao tác này **conflict-serializable** tương đương thứ tự T1 rồi T2.

Nhưng T2 đọc giá trị X của T1 và commit **trước T1**, nên S5 là **non-recoverable**. Nếu T1 abort thay vì commit, T2 đã commit dựa trên dữ liệu không hợp lệ.

Điều này minh họa rằng chỉ kiểm tra conflict graph không đủ để kết luận thứ tự commit an toàn.

### 8.3. Có thể strict nhưng không serializable

Giả sử X ban đầu bằng 10. Hai giao dịch định tăng X bằng chuỗi **đọc trong ứng dụng rồi ghi giá trị tính được**. Xét lịch:

~~~text
S6 = r1(X=10)  r2(X=10)  w1(X=11)  c1  w2(X=11)  c2
~~~

- T1 và T2 đều đọc X trước khi có transaction nào ghi X.
- Sau khi T1 ghi X, T2 **chỉ ghi đè X sau khi T1 đã commit**. Không có giao dịch nào đọc hoặc ghi dữ liệu đang chưa commit của transaction khác.
- Vì vậy lịch này thỏa điều kiện **strict**.
- Nhưng lịch có xung đột tạo chu trình: `r1(X)` trước `w2(X)` tạo cạnh T1 → T2; `r2(X)` trước `w1(X)` tạo cạnh T2 → T1.
- Do có chu trình, lịch **không conflict-serializable**. Cả hai lần tăng lại chỉ tạo X=11, là lỗi lost update về mặt nghiệp vụ.

Một số DBMS và isolation level có thể phát hiện hoặc từ chối kiểu cập nhật cạnh tranh cụ thể; lịch trên là minh họa lý thuyết cho sự độc lập giữa các tính chất.

**Kết luận thiết kế:** vừa cần tính chất lịch đủ mạnh để ngăn phụ thuộc bẩn/hủy dây chuyền, vừa cần kiểm soát conflict và bất biến nghiệp vụ để tránh kết quả sai do xen kẽ.

## 9. Phân tích lịch thực thi từng bước

### 9.1. Phương pháp thủ công

Khi gặp một schedule, làm theo trình tự:

1. **Liệt kê các transaction:** T1, T2, T3…; xác định thời điểm commit/abort.
2. **Theo dõi phiên bản dữ liệu được đọc:** với mỗi `rj(X)`, xác định nó đọc X do transaction nào ghi. Không suy luận chỉ từ tên X nếu lịch có snapshot hoặc nhiều phiên bản.
3. **Vẽ cạnh phụ thuộc đọc:** Ti → Tj nếu Tj đọc phiên bản từ Ti.
4. **Kiểm tra recoverable:** với mỗi cạnh Ti → Tj, nếu Tj commit thì Ti đã commit trước đó chưa? Nếu không, lịch non-recoverable.
5. **Kiểm tra cascadeless:** với mỗi cạnh Ti → Tj, Ti đã commit **trước lần đọc** tương ứng chưa? Nếu không, lịch không cascadeless.
6. **Kiểm tra strict:** sau mỗi lần Ti ghi X, có Tj khác đọc hoặc ghi X trước khi Ti commit/abort không? Nếu có, lịch không strict.
7. **Phân tích abort:** nếu Ti abort, tìm các Tj chưa commit đọc phiên bản của Ti, rồi theo phụ thuộc bắc cầu để xác định những transaction có nguy cơ cascade.
8. **Đánh giá serializability riêng nếu được hỏi:** dựng conflict graph và kiểm tra chu trình.

Điều kiện cần phân biệt:

- **Không có phụ thuộc đọc** thì kiểm tra recoverable/cascadeless có thể đúng một cách hiển nhiên, dù vẫn có xung đột ghi.
- **Có cùng mục X** không đủ để kết luận T2 dirty-read T1; phải biết T2 nhìn thấy phiên bản nào.
- **Một transaction chưa có sự kiện commit** chưa được coi là đã commit; có thể đang chạy hoặc chuẩn bị abort.

### 9.2. Ví dụ A: lịch recoverable nhưng không cascadeless

~~~text
S_A = w1(X)  r2(X)  w2(Y)  c1  c2
~~~

T2 đọc phiên bản X từ T1 trước `c1`, nên lịch không cascadeless. Tuy nhiên `c1` trước `c2`, nên lịch recoverable.

Nếu T1 abort trước `c1`, T2 phải hủy thay đổi Y và các thay đổi phụ thuộc khác trước khi commit. Lịch có nguy cơ cascading abort.

### 9.3. Ví dụ B: lịch cascadeless nhưng không strict

~~~text
S_B = w1(X)  w2(X)  c1  c2
~~~

Không có lần đọc bẩn, nên không có cascade do reads-from. Nhưng `w2(X)` xảy ra trước khi T1 kết thúc, tạo dirty write. Lịch không strict.

### 9.4. Ví dụ C: lịch strict

~~~text
S_C = w1(X)  w2(Y)  c2  r3(Y)  c1  r4(X)  c3  c4
~~~

T1 ghi X nhưng không transaction khác đọc/ghi X trước `c1`. T2 ghi Y, T3 chỉ đọc Y sau `c2`. Lịch strict và vì thế cũng cascadeless và recoverable.

Lưu ý T2 được commit trước T1 vì không có phụ thuộc dữ liệu từ T1 sang T2.

### 9.5. Ví dụ D: thứ tự commit không thể thỏa cả hai phụ thuộc

~~~text
S_D = w1(X)  r2(X)  w2(Y)  r1(Y)  ...
~~~

Ta có hai cạnh:

~~~text
T1 --> T2   (T2 đọc X của T1)
T2 --> T1   (T1 đọc Y của T2)
~~~

Nếu cả hai transaction muốn commit mà vẫn recoverable, bắt buộc:

~~~text
c1 < c2    và    c2 < c1
~~~

Hai điều kiện không thể đồng thời đúng. Vì vậy **không có cách đặt cả hai COMMIT** để lịch này trở thành recoverable; cần hủy hoặc thực hiện lại ít nhất một transaction. Lịch minh họa quan hệ đọc dữ liệu chưa commit có thể tạo phụ thuộc vòng, dù hệ quản trị thực tế thường ngăn những thao tác nguy hiểm này trước khi chúng xảy ra.

## 10. Liên hệ với cơ chế khóa và Strict Two-Phase Locking

### 10.1. S và X lock

Trong mô hình khóa hai pha, có thể xét:

- **S lock (shared lock):** thường dùng bảo vệ lần đọc; các S lock tương thích có thể cùng tồn tại.
- **X lock (exclusive lock):** dùng bảo vệ lần ghi; xung đột với các khóa không tương thích trên cùng mục dữ liệu.

Một transaction ghi X cần X lock. Nếu hệ thống **giữ X lock đến khi commit hoặc abort**, transaction khác không thể đọc/ghi trực tiếp X qua các thao tác khóa xung đột cho tới lúc transaction ghi kết thúc.

### 10.2. Strict 2PL tạo lịch strict theo mô hình khóa chuẩn

**Two-Phase Locking (2PL)** cơ bản có hai pha:

1. **Growing phase:** transaction lấy thêm khóa.
2. **Shrinking phase:** transaction trả khóa, không lấy khóa mới sau khi đã bắt đầu trả.

2PL cơ bản được dùng để bảo đảm **conflict serializability** trong mô hình chuẩn, nhưng **không mặc nhiên strict** nếu trả X lock sớm.

**Strict 2PL** bổ sung quy tắc **giữ các X lock đến khi commit hoặc abort**. Khi mọi truy cập tuân thủ quy tắc khóa này, transaction khác không thể dirty-read hoặc dirty-write dữ liệu đang được ghi chưa commit, nên lịch là strict.

Có biến thể **rigorous 2PL** còn giữ cả S lock và X lock đến khi transaction kết thúc.

~~~text
T1: lấy X-lock(X) -> w1(X) -------------- c1 -> nhả X-lock(X)
T2:           yêu cầu X-lock(X) -> [chờ] -----> lấy lock -> w2(X)
~~~

Strict 2PL đánh đổi độ an toàn và đơn giản của rollback bằng nguy cơ chờ khóa và deadlock. Database thường dùng các chiến lược khóa tinh vi hơn và có thể kết hợp với MVCC; đừng giả định mọi engine đang chạy strict 2PL toàn phần chỉ từ hành vi bên ngoài.

### 10.3. Vì sao 2PL không giải quyết hết mọi vấn đề?

Strict 2PL theo mô hình thích hợp giúp đạt serializability và strictness đối với các thao tác tham gia khóa. Nhưng ở hệ thống thực:

- Phạm vi predicate/range và phantom cần cơ chế tương ứng, không chỉ khóa những hàng đã tồn tại.
- Read replica, cache và dịch vụ ngoài database không tự tham gia hệ khóa.
- Thời gian chờ khóa có thể tăng mạnh khi một hàng trở thành điểm nóng.
- Deadlock vẫn có thể xảy ra và cần cơ chế phát hiện/rollback.

## 11. Liên hệ với MVCC và isolation level

### 11.1. Không đọc dữ liệu chưa commit mà vẫn giữ khả năng đọc đồng thời

Trong **Multi-Version Concurrency Control (MVCC)**, database lưu nhiều phiên bản của một hàng. Một transaction có thể đọc một phiên bản đã commit phù hợp với snapshot của nó trong khi transaction khác đang tạo phiên bản chưa commit.

~~~text
X=100: phiên bản đã commit

T1: cập nhật X=120 (chưa commit)
T2: đọc snapshot và thấy X=100
T1: rollback -> phiên bản X=120 bị bỏ
T2: không bị phụ thuộc vào X=120
~~~

Đây là ví dụ cho thấy hệ thống có thể tránh dirty read mà không buộc mọi lần đọc phải đợi writer. Tuy nhiên, **MVCC không tự bảo đảm serializability**: kết quả phụ thuộc isolation level, kiểm soát write-write conflict và việc bảo vệ bất biến của ứng dụng.

### 11.2. READ COMMITTED và READ UNCOMMITTED

Mức `READ COMMITTED`, trong các engine cung cấp đúng ngữ nghĩa phổ biến, không cho một transaction đọc giá trị chưa commit từ transaction khác. Nhờ vậy, nó loại bỏ nguyên nhân trực tiếp của cascading abort do dirty read.

Ngược lại, `READ UNCOMMITTED` về mặt mô hình SQL có thể cho phép dirty read, nhưng **không phải DBMS nào cũng thực thi được dirty read ở mức này**.

Ví dụ đặc thù:

- **PostgreSQL:** đặt `READ UNCOMMITTED` có hiệu ứng như `READ COMMITTED`; các truy vấn thông thường không thấy các phiên bản ghi chưa commit của transaction khác.
- **MySQL InnoDB:** `READ UNCOMMITTED` có thể cho consistent read nhìn thấy các phiên bản chưa commit; không nên dùng nó để ra quyết định nghiệp vụ cần dữ liệu đáng tin cậy.
- **SQL Server:** có chế độ `READ UNCOMMITTED` hoặc `NOLOCK` cho một số truy vấn, nhưng việc đọc dữ liệu chưa commit và các hiện tượng đọc không ổn định khiến nó không phù hợp khi tính đúng đắn phụ thuộc vào kết quả đọc.

Hành vi cụ thể còn phụ thuộc loại câu lệnh đọc, isolation mode, engine và cấu hình. Không nên suy luận rằng chỉ cần chọn một tên isolation level là mọi DBMS sẽ có một lịch thực thi giống hệt nhau.

### 11.3. REPEATABLE READ và SERIALIZABLE không nên bị nhầm với strictness

Tên isolation level mô tả những bảo đảm về khả năng nhìn thấy dữ liệu và thứ tự xử lý, tùy engine. Thuật ngữ **strict schedule** lại là một điều kiện hình thức trên thứ tự các thao tác đọc/ghi và thời điểm transaction tạo bản ghi kết thúc.

Ở DBMS thực tế, có thể kết hợp snapshot cho đọc, khóa cho ghi và cơ chế phát hiện phụ thuộc nguy hiểm. Vì vậy phải xem **ngữ nghĩa cụ thể của engine và loại thao tác** thay vì mặc định từ tên isolation rằng lịch ở mức nào trong ba lớp recoverable/cascadeless/strict.

Điều đặc biệt quan trọng: **Không dirty read** vẫn chưa đồng nghĩa **không lost update, không write skew và không vi phạm bất biến nghiệp vụ**.

## 12. SQL minh họa trên hai session

Các ví dụ sau nhằm giúp quan sát hành vi của một hệ quản trị hiện đại. Chúng sử dụng **PostgreSQL** để minh họa cách ngăn dirty read. Không thể dùng PostgreSQL ở `READ UNCOMMITTED` để chứng minh một dirty read, vì engine này xử lý mức đó giống `READ COMMITTED`.

### 12.1. Chuẩn bị

~~~sql
CREATE TABLE IF NOT EXISTS balances (
    account_id BIGINT PRIMARY KEY,
    amount INTEGER NOT NULL
);

INSERT INTO balances(account_id, amount)
VALUES (1, 100)
ON CONFLICT (account_id)
DO UPDATE SET amount = EXCLUDED.amount;
~~~

### 12.2. Session A cập nhật nhưng chưa commit

~~~sql
-- SESSION A
BEGIN;
UPDATE balances
SET amount = 120
WHERE account_id = 1;

-- Chưa COMMIT. Giữ session này mở để quan sát từ session B.
~~~

### 12.3. Session B đọc trong lúc A chưa commit

~~~sql
-- SESSION B, kết nối PostgreSQL riêng
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT amount
FROM balances
WHERE account_id = 1;

-- Thường thấy 100: bản đã commit trước thay đổi của A.
COMMIT;
~~~

Session B không dùng phiên bản 120 chưa commit của A. Nếu A rollback, B không phải rollback chỉ vì đã đọc giá trị 100.

### 12.4. Session A abort rồi kiểm tra lại

~~~sql
-- SESSION A
ROLLBACK;
~~~

~~~sql
-- SESSION B
SELECT amount
FROM balances
WHERE account_id = 1;
-- Giá trị được giữ là 100 nếu không có giao dịch khác sửa hàng.
~~~

Nếu A commit thay vì rollback, một câu `SELECT` mới từ B trong `READ COMMITTED` có thể thấy 120. Đây là việc đọc thay đổi **đã commit**, khác với dirty read.

### 12.5. Cách mô phỏng hủy dây chuyền khi DB ngăn dirty read

Để nghiên cứu lý thuyết, có thể tạo một **schedule simulator** trong test hoặc vẽ trace thao tác theo ký hiệu `w1/r2/a1/a2`. Không nên tắt bảo vệ nhất quán trên cơ sở dữ liệu sản xuất chỉ để tái hiện một lịch dirty read.

Mục tiêu của thực nghiệm là phân biệt:

- B đọc **giá trị cũ đã commit**: không có phụ thuộc dirty read.
- B **chờ** A hoàn tất: nếu A commit, B đọc giá trị mới; nếu A abort, B đọc giá trị hợp lệ sau rollback.
- B đọc **phiên bản chưa commit** của A: phụ thuộc bẩn; nếu A abort, B có nguy cơ bị buộc hủy.

## 13. Hệ quản trị phục hồi như thế nào khi có abort?

### 13.1. Undo giao dịch chưa commit

Một DBMS phải bảo đảm rằng các thay đổi của transaction abort không còn hiện diện như dữ liệu đã commit. Cơ chế thực tế có thể sử dụng undo log, transaction log, MVCC versioning, rollback segments hoặc cách phối hợp khác tùy engine.

Trong lịch strict, không có transaction khác được đọc hoặc ghi đè trực tiếp giá trị chưa commit ấy. Vì vậy khi Ti abort, database có thể xử lý các thay đổi của Ti mà không phải xử lý một chuỗi giao dịch đã đọc phiên bản dirty của Ti.

### 13.2. Tại sao strictness giúp đơn giản hóa recovery?

Giả sử một hệ thống cho phép các thao tác sau trên cùng X:

~~~text
w1(X=20)
w2(X=30)
a1
c2
~~~

Nếu undo T1 theo cách khôi phục X về giá trị cũ mà không nhận biết lần ghi T2, hệ thống có thể vô tình làm mất cập nhật T2. Một cơ chế log/undo phức tạp có thể quản lý trường hợp này, nhưng strict schedule loại bỏ chính kiểu ghi chồng khi chưa kết thúc.

Tương tự, nếu T2 đã đọc X=20 của T1 và tiếp tục tính toán, khi T1 abort sẽ có phụ thuộc lây lan. Với strict schedule, giao dịch T2 không nhận kết quả X chưa commit đó.

### 13.3. Viết log bền vững khác với giữ lịch recoverable

Các thuật toán khôi phục kiểu **Write-Ahead Logging (WAL)** bảo đảm log cần thiết được ghi trước các thao tác lưu dữ liệu tương ứng theo quy tắc engine, giúp redo dữ liệu đã commit và undo dữ liệu chưa commit khi cần.

Một mô hình phục hồi phổ biến trong giáo trình là **STEAL / NO-FORCE**:

- *STEAL:* database có thể ghi trang dữ liệu chứa thay đổi chưa commit ra đĩa, nên khi khôi phục có thể cần undo.
- *NO-FORCE:* transaction commit không nhất thiết ép mọi trang dữ liệu bẩn ra đĩa ngay, nên có thể cần redo sau sự cố.

Các kỹ thuật log giải quyết dữ liệu trên lưu trữ sau crash, trong khi recoverable/cascadeless/strict mô tả **quan hệ an toàn giữa các transaction trong schedule**. Hai vấn đề hỗ trợ lẫn nhau nhưng không thay thế nhau.

## 14. Hậu quả vận hành và hiệu năng của cascading abort

### 14.1. Công việc phải làm lại

Giả sử hệ thống đã thực hiện:

- T1: 10 ms xử lý rồi abort.
- T2: 30 ms xử lý dựa trên dữ liệu dirty của T1.
- T3: 40 ms xử lý dựa trên kết quả dirty của T2.

Nếu cả T2 và T3 phải abort, tổng công việc đã làm có thể bị lãng phí đáng kể và cần chạy lại. Trong thực tế còn phát sinh tải I/O, log, giữ connection, thao tác CPU và hàng đợi request.

**Giảm mức cô lập để đọc nhanh hơn** có thể làm giảm thời gian chờ trong vài tình huống nhưng lại tăng rủi ro sử dụng dữ liệu không đáng tin cậy và chi phí sửa sai về sau.

### 14.2. Chờ writer hay đọc snapshot?

Có hai chiến lược tổng quát để tránh đọc dirty:

| Chiến lược | Cách tránh dirty read | Chi phí nổi bật |
|---|---|---|
| Đọc có khóa phù hợp | Chờ transaction đang ghi hoàn tất | Lock wait, nguy cơ deadlock và độ trễ đuôi |
| Đọc phiên bản đã commit (MVCC) | Đọc snapshot hợp lệ thay vì phiên bản chưa commit | Quản lý nhiều phiên bản, vacuum/cleanup, chọn snapshot đúng |

Việc bảo vệ dữ liệu không nhất thiết đồng nghĩa với việc khóa chặn mọi reader. MVCC cho phép nhiều đọc chạy đồng thời mà vẫn tránh đọc bẩn trong các isolation mode thích hợp.

### 14.3. Các chỉ số nên quan sát

- Số transaction abort, phân loại theo lỗi nghiệp vụ, deadlock và serialization failure.
- Số lần retry và tỉ lệ transaction hoàn tất sau retry.
- Độ trễ p50/p95/p99 của thao tác nghiệp vụ.
- Thời gian chờ khóa và số lượng transaction đang chờ.
- Transaction kéo dài quá lâu, đặc biệt khi giữ khóa ghi.
- Bất biến dữ liệu sau commit, số bản ghi phải bù trừ hoặc đối soát.
- Số lần xử lý side effect trùng sau khi request thất bại hoặc retry.

Những chỉ số này không chứng minh trực tiếp một lịch cụ thể recoverable hay cascadeless; chúng giúp điều tra hệ quả của việc xử lý xung đột và abort trong thực tế.

## 15. Liên hệ với Java, JDBC và Spring Transaction

### 15.1. Duy trì ranh giới transaction rõ ràng

Một luồng nghiệp vụ trong JDBC:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class InventoryAdjustment {

    public void adjust(String url, String user, String password,
                       long productId, int delta) throws SQLException {
        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement update = connection.prepareStatement(
                        "UPDATE products SET stock = stock + ? WHERE id = ?")) {
                    update.setInt(1, delta);
                    update.setLong(2, productId);

                    int changed = update.executeUpdate();
                    if (changed != 1) {
                        throw new SQLException("Product not found");
                    }
                }

                // Các thao tác bắt buộc khác nằm trong cùng transaction.
                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }
}
~~~

Đoạn mã chủ yếu minh họa **commit hoặc rollback rõ ràng**. Tính đúng đắn tồn kho còn phụ thuộc vào các ràng buộc và điều kiện nghiệp vụ (ví dụ bảo đảm stock không âm, kiểm tra delta và đồng bộ với việc tạo đơn). Một transaction đơn lẻ có `setAutoCommit(false)` không đủ để tự giải quyết mọi lỗi đồng thời.

Khi hai connection cùng thao tác, cách database xử lý phiên bản đã commit, xung đột ghi và rollback quyết định liệu giao dịch khác có thể đọc bản chưa commit hay không.

### 15.2. Spring @Transactional

Trong Spring, `@Transactional` giúp đặt các phương thức thuộc cùng một ranh giới transaction khi transaction manager và propagation được cấu hình đúng:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;

    public OrderService(OrderRepository orders,
                        InventoryRepository inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    @Transactional
    public void createOrder(long productId, int quantity, String requestKey) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        int affected = inventory.decreaseIfEnough(productId, quantity);
        if (affected != 1) {
            throw new IllegalStateException("Insufficient stock");
        }

        orders.insertOrder(requestKey, productId, quantity);
    }
}
~~~

Một câu SQL có điều kiện tương ứng:

~~~sql
UPDATE products
SET stock = stock - :quantity
WHERE id = :product_id
  AND stock >= :quantity;
~~~

Các thao tác giảm kho và tạo đơn cùng thuộc một transaction; nếu việc tạo đơn thất bại và lỗi dẫn đến rollback, giảm kho cũng bị rollback. Các transaction khác không nên đưa ra quyết định dựa trên kết quả giảm kho khi nó chưa commit.

**Lưu ý:** Spring `@Transactional` không tự kiểm tra mọi bất biến, không mặc định chống request trùng, và việc rollback phụ thuộc các quy tắc exception/transaction manager. Cần có ràng buộc database và chiến lược idempotency cho nghiệp vụ thực tế.

### 15.3. Không gửi kết quả chưa commit ra hệ thống khác

Ngay cả khi các transaction trong **một database** có lịch strict, ứng dụng vẫn có thể phát sinh dạng phụ thuộc nguy hiểm ở bên ngoài:

~~~text
T1: INSERT order (chưa commit)
T1: gửi HTTP event "order created" đến service B
B:  xử lý event và ghi dữ liệu của riêng nó
T1: ROLLBACK
~~~

Service B đã xử lý dữ liệu mà database của T1 chưa từng commit. Đây không phải một lịch đọc/ghi trên cùng item trong một DBMS, nhưng **ý tưởng phụ thuộc vào dữ liệu chưa xác nhận** là tương tự.

Giải pháp thường dùng:

1. Ghi thay đổi nghiệp vụ và bản ghi **outbox** trong cùng transaction local.
2. Chỉ sau khi transaction commit, worker mới thấy và gửi outbox event.
3. Consumer dùng idempotency key hoặc deduplication để chịu được gửi lặp.
4. Nếu nghiệp vụ trải qua nhiều dịch vụ, thiết kế orchestration/compensation phù hợp, vì không có một SAVEPOINT hay ROLLBACK duy nhất tự bảo đảm mọi hệ thống cùng hủy.

Không nên xem việc gọi API trong một phương thức `@Transactional` là bảo đảm API có thể rollback theo database.

## 16. Cách kiểm thử các thuộc tính của schedule

### 16.1. Kiểm thử trên lịch trừu tượng

Có thể tạo một bảng thao tác và chạy bộ phân tích đơn giản:

~~~text
INPUT:
  operation = {txn, kind: READ|WRITE|COMMIT|ABORT, item, versionSource?}
  operations được sắp theo thứ tự thời gian

FOR mỗi READ của Tj lấy version từ Ti khác Tj:
  thêm phụ thuộc Ti -> Tj
  nếu Ti chưa COMMIT tại thời điểm READ:
    lịch không cascadeless

FOR mỗi WRITE của Ti trên X:
  kiểm tra các READ/WRITE của Tj khác Ti
  trước thời điểm Ti COMMIT hoặc ABORT
  nếu có thao tác xung đột trên X:
    lịch không strict

FOR mỗi phụ thuộc Ti -> Tj:
  nếu Tj COMMIT mà Ti không COMMIT trước Tj:
    lịch không recoverable
~~~

Mô tả trên là **thuật toán khái niệm**, chưa phải trình mô phỏng đầy đủ MVCC. Với nhiều phiên bản, phải biết chính xác nguồn phiên bản mỗi lần đọc; không được luôn chọn thao tác ghi gần nhất chỉ theo thứ tự dòng nếu snapshot semantics khác.

### 16.2. Kiểm thử DB thật

Thiết lập hai session độc lập và đồng bộ thời điểm bằng barrier/test harness:

1. T1 bắt đầu transaction, cập nhật X nhưng chưa commit.
2. T2 đọc X theo mức isolation mục tiêu.
3. Ghi lại T2 có thấy bản đã commit cũ, chờ hay thấy bản chưa commit.
4. T1 rollback.
5. Quan sát trạng thái T2 và dữ liệu sau rollback.
6. Lặp lại với T1 commit để quan sát lúc phiên bản mới có hiệu lực.

Nếu engine ngăn dirty read, đây là **kết quả mong muốn**, không phải test thất bại. Bài kiểm thử nên xác nhận bảo đảm của engine thay vì cố tình tạo cascading abort trên production data.

Để đánh giá correctness đầy đủ, cần thêm test concurrent updates, uniqueness constraints, predicate invariants và retry logic. Việc không có cascading abort không chứng minh mọi thao tác nghiệp vụ an toàn.

### 16.3. Kiểm thử trạng thái không rõ sau COMMIT

Một client có thể mất kết nối ngay sau khi database đã commit. Client không nhận được phản hồi, nhưng kết quả có thể đã tồn tại. **Không nên mặc định timeout = rollback** rồi gửi lại yêu cầu dưới mã mới.

Với đơn hàng hoặc thanh toán, dùng `request_key` ổn định, ràng buộc `UNIQUE` và truy vấn kết quả theo khóa đó khi kết quả commit chưa rõ. Đây là cơ chế bổ sung cho recoverability của schedule, không phải phần định nghĩa recoverable.

## 17. Những nhầm lẫn thường gặp

### 17.1. “T2 đọc chưa commit thì lịch chắc chắn non-recoverable”

**Sai.** Lịch `w1(X) r2(X) c1 c2` có dirty read nhưng vẫn recoverable. Rủi ro là nếu T1 abort, T2 phải abort theo, nên lịch **không cascadeless**.

### 17.2. “Chỉ cần T1 commit cuối cùng là mọi thứ hợp lệ”

**Sai về recoverability.** Nếu T2 đọc từ T1 rồi commit trước T1 (`c2 < c1`), lịch non-recoverable dù lần chạy cụ thể T1 cuối cùng commit.

### 17.3. “Cascadeless có nghĩa không bao giờ có rollback hàng loạt”

**Không hẳn.** Cascadeless ngăn cascading abort **do đọc dữ liệu chưa commit**. Nhiều transaction vẫn có thể bị hủy độc lập bởi deadlock, constraint violation, serialization conflict hoặc lỗi hạ tầng.

### 17.4. “Strict đồng nghĩa với serializable”

**Sai.** Strict kiểm soát truy cập các mục dữ liệu đã bị transaction chưa hoàn tất ghi. Nó không tự ngăn mọi lịch đọc trước khi ghi dẫn đến lost update hoặc mọi chu trình trong conflict graph. Cần đánh giá serializability riêng.

### 17.5. “READ COMMITTED cho phép ứng dụng bỏ mọi khóa”

**Sai.** Ngăn dirty read chỉ giải quyết một lớp rủi ro. Quy tắc tồn kho, chuyển tiền và các bất biến tập hàng vẫn có thể cần SQL cập nhật nguyên tử, khóa, constraint, version check hoặc mức isolation cao hơn.

### 17.6. “Recoverable là khả năng phục hồi từ backup”

**Sai.** Trong chủ đề schedule, recoverable nói về **thứ tự commit của các giao dịch có quan hệ đọc dữ liệu**, không phải backup, WAL hay disaster recovery.

### 17.7. “Nếu rollback có thể chạy, chẳng có vấn đề gì”

**Sai.** Trong lịch recoverable nhưng không cascadeless, các transaction phụ thuộc có thể phải hủy và làm lại. Cách này có thể giữ correctness nhưng vẫn tốn tài nguyên, tăng độ trễ và khiến luồng nghiệp vụ khó quản lý.

## 18. Bài tập tự luyện

### Bài 1 — Phân loại lịch

Cho:

~~~text
S = w1(X)  r2(X)  c1  c2
~~~

- Có recoverable không?
- Có cascadeless không?
- Có strict không?

**Đáp án:** Recoverable vì `c1` trước `c2`. Không cascadeless vì `r2(X)` xảy ra trước `c1`. Không strict vì T2 đọc X khi T1 còn chưa kết thúc.

### Bài 2 — Nhận diện non-recoverable

~~~text
S = w1(X)  r2(X)  c2  c1
~~~

**Đáp án:** Non-recoverable vì T2 commit trước T1 dù T2 đã đọc phiên bản do T1 ghi. Nếu T1 abort sau `c2`, T2 đã commit dựa trên giá trị không hợp lệ.

### Bài 3 — Đếm số giao dịch có nguy cơ cascade

~~~text
S = w1(A)  r2(A)  w2(B)  r3(B)  w3(C)  r4(C)  a1
~~~

Hỏi những giao dịch nào phải được xem xét abort do phụ thuộc dữ liệu?

**Đáp án:** T2 phụ thuộc T1; T3 phụ thuộc T2; T4 phụ thuộc T3. Nếu tất cả vẫn chưa commit và các thao tác thực sự dựa vào phiên bản đã đọc, T2, T3 và T4 đều có nguy cơ phải abort hoặc chạy lại. Nếu một trong các giao dịch này đã commit sai thứ tự trước nguồn của nó, ta còn gặp vấn đề non-recoverable.

### Bài 4 — Cascadeless hay strict?

~~~text
S = w1(X)  w2(X)  c1  c2
~~~

**Đáp án:** Cascadeless theo điều kiện không có dirty read vì lịch không chứa phép đọc. Nhưng không strict vì T2 ghi X khi T1 đã ghi X và chưa kết thúc.

### Bài 5 — Strict đã đủ để tăng bộ đếm đúng chưa?

Hai transaction đọc X=10 rồi lần lượt ghi X=11. Chúng không dirty-read hay dirty-write. Tuy nhiên kết quả cuối chỉ tăng một lần.

**Đáp án:** Strict không đủ để ngăn lost update ở lịch này. Có thể dùng `UPDATE counters SET value = value + 1 WHERE id = ...` dưới cơ chế điều phối ghi phù hợp của database, optimistic version check hoặc isolation ngăn lịch không serializable theo yêu cầu.

### Bài 6 — Xây đồ thị phụ thuộc commit

Cho:

~~~text
w1(X) r2(X) w2(Y) r3(Y) c1 c2 c3
~~~

Vẽ đồ thị read-from và nêu thứ tự commit cần có.

**Đáp án:** `T1 → T2 → T3`. Để recoverable, thứ tự commit phải tôn trọng `c1 < c2 < c3`. Tuy vậy lịch vẫn **không cascadeless** nếu T2 đã đọc X và T3 đã đọc Y trước khi các writer tương ứng commit.

### Bài 7 — Chọn cách phòng tránh thực tế

Một báo cáo tổng hợp cần đọc trạng thái đơn hàng trong lúc các transaction khác tạo và hủy đơn. Có nên yêu cầu báo cáo đọc dữ liệu chưa commit để giảm chờ hay không?

**Gợi ý trả lời:** nếu báo cáo ảnh hưởng quyết định nghiệp vụ hoặc được cung cấp như dữ liệu chính thức, đọc dữ liệu chưa commit không đáng tin cậy. Ưu tiên snapshot đã commit hoặc mức isolation phù hợp với tính nhất quán yêu cầu. Cũng cần lựa chọn thời điểm snapshot theo nhu cầu một báo cáo nhất quán trong toàn bộ câu truy vấn hay toàn transaction.

## 19. Các nguyên tắc áp dụng

Khi đánh giá một lịch thực thi, đừng bắt đầu bằng câu hỏi “Có nhiều transaction cùng chạy không?”. Hãy bắt đầu từ **ai đã đọc phiên bản của ai, phiên bản đó đã commit chưa, và giao dịch nào commit trước**.

- **Recoverable** giữ thứ tự commit hợp lệ cho các transaction có phụ thuộc đọc, nhưng vẫn cho phép dirty read và có thể phải hủy công việc dây chuyền.
- **Cascadeless** ngăn đọc dữ liệu chưa commit của transaction khác, loại bỏ nguyên nhân trực tiếp của cascading abort do dirty read.
- **Strict** đi xa hơn: ngăn cả việc đọc và ghi đè dữ liệu do transaction chưa kết thúc ghi ra, giúp việc undo trở nên đơn giản và đáng tin cậy hơn.

Quan hệ cần ghi nhớ là:

\[
\boxed{\text{Strict} \subset \text{Cascadeless} \subset \text{Recoverable}}
\]

Đây là quan hệ bao hàm về **tập lịch thực thi**: strict là điều kiện mạnh nhất trong ba loại. Hệ thống thực tế thường sử dụng phối hợp khóa, MVCC, isolation level và cơ chế commit/rollback để tránh phụ thuộc bẩn. Nhưng việc tránh cascading abort vẫn cần đi cùng kiểm soát lost update, write skew, ràng buộc nghiệp vụ, retry và side effect ngoài database nếu muốn toàn bộ ứng dụng vừa đúng đắn vừa có hiệu năng tốt.
