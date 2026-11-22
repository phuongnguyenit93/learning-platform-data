# Những bất thường được ngăn chặn và những tình huống cần kiểm chứng

**Cô lập ảnh chụp** (*Snapshot Isolation*, SI) là một cách điều khiển tương tranh dựa trên MVCC. Mỗi giao dịch đọc dữ liệu từ một ảnh chụp nhất quán của cơ sở dữ liệu tại một thời điểm xác định. Các phiên bản được giao dịch khác commit sau thời điểm đó thường không xuất hiện trong những lần đọc snapshot tiếp theo của giao dịch hiện tại. Giao dịch vẫn nhìn thấy các thay đổi do chính nó tạo ra.

Snapshot Isolation ngăn được nhiều bất thường đọc thường gặp, chẳng hạn dirty read, non-repeatable read và phantom read theo cách hiểu thông thường của các lần đọc snapshot. Các lần đọc cũng không bị lệch giữa những hàng vì mỗi hàng được đọc theo cùng một ảnh chụp. Nhiều hệ quản trị triển khai SI còn phát hiện xung đột ghi trên cùng một hàng và hủy một giao dịch để tránh lost update.

Tuy nhiên, **Snapshot Isolation không đồng nghĩa với Serializable**. Hai giao dịch có thể đọc cùng một ảnh chụp rồi ghi lên các hàng khác nhau. Nếu mỗi giao dịch dựa vào dữ liệu mà nó đã đọc để quyết định ghi, cả hai có thể cùng commit và làm hỏng một quy tắc nghiệp vụ. Bất thường kinh điển này được gọi là *write skew*.

Vì vậy, khi sử dụng SI, cần hiểu rõ hai phần: những bất thường mà snapshot giúp ngăn chặn và những bất biến nghiệp vụ vẫn cần khóa, ràng buộc dữ liệu hoặc mức Serializable để bảo vệ.

## 1. Snapshot Isolation hoạt động như thế nào?

MVCC lưu nhiều phiên bản của một hàng. Thay vì buộc mọi giao dịch đọc phải chờ giao dịch ghi kết thúc, hệ thống có thể cho giao dịch đọc phiên bản phù hợp với snapshot của nó.

Ở mô hình SI phổ biến:

1. Khi giao dịch bắt đầu hoặc thực hiện lần đọc snapshot đầu tiên (tùy hệ quản trị), hệ thống xác định snapshot của giao dịch.
2. Giao dịch đọc phiên bản đã commit và nhìn thấy được tại snapshot đó.
3. Giao dịch nhìn thấy các thay đổi hợp lệ do chính nó tạo ra sau khi bắt đầu.
4. Khi ghi, giao dịch tạo phiên bản mới. Các giao dịch khác chưa tự động nhìn thấy phiên bản chưa commit này.
5. Khi commit, hệ thống kiểm tra xung đột ghi. Trong mô hình SI với quy tắc *first-committer-wins*, nếu một giao dịch đồng thời đã commit thay đổi trên cùng đối tượng mà giao dịch hiện tại muốn ghi, một giao dịch phải bị từ chối hoặc hủy.

Ví dụ, `T1` và `T2` cùng bắt đầu khi `balance = 1000`:

```text
Thời điểm bắt đầu snapshot:
    T1 đọc phiên bản V1: balance = 1000
    T2 đọc phiên bản V1: balance = 1000

T1 ghi phiên bản V2: balance = 900
T2 vẫn đọc V1 theo snapshot của mình

T1 COMMIT
T2 muốn COMMIT một thay đổi trên cùng hàng
    -> hệ thống SI phát hiện xung đột ghi
    -> T2 có thể phải ABORT
```

Chi tiết thời điểm tạo snapshot, cách phát hiện xung đột và loại lỗi trả về phụ thuộc hệ quản trị. Quy tắc quan trọng của mô hình là các lần đọc dùng một ảnh chụp nhất quán, còn các xung đột ghi cần được kiểm tra khi cập nhật hoặc commit.

## 2. Những bất thường đọc được ngăn chặn

### Dirty read

Dirty read xảy ra khi một giao dịch đọc thay đổi chưa commit do giao dịch khác tạo ra. Nếu giao dịch tạo thay đổi rollback, giao dịch đọc đã sử dụng một giá trị không bao giờ trở thành dữ liệu đã commit.

Ví dụ:

```text
T1: UPDATE accounts SET balance = 900 WHERE id = 10
T1: chưa commit
T2: SELECT balance FROM accounts WHERE id = 10
T1: ROLLBACK
```

Trong SI, `T2` đọc phiên bản đã commit phù hợp với snapshot của nó. Nó không đọc phiên bản `balance = 900` chưa commit của `T1`. Dirty read vì thế bị ngăn chặn.

Điều này không ngăn `T1` đọc chính thay đổi `900` của nó. Đó là *read-your-own-writes*, một hành vi hợp lệ trong phạm vi giao dịch hiện tại.

### Non-repeatable read

Non-repeatable read xảy ra khi cùng một giao dịch đọc một hàng hai lần và nhận được hai giá trị khác nhau vì giao dịch khác đã cập nhật rồi commit ở giữa hai lần đọc.

Ví dụ, ban đầu `balance = 1000`:

```text
T1: BEGIN; tạo snapshot S
T1: SELECT balance -> 1000

T2: BEGIN
T2: UPDATE accounts SET balance = 1200 WHERE id = 10
T2: COMMIT

T1: SELECT balance -> vẫn là 1000 theo snapshot S
T1: COMMIT
```

Hai lần đọc của `T1` sử dụng cùng snapshot nên cùng nhìn thấy phiên bản `1000`. Phiên bản `1200` được `T2` commit sau khi snapshot của `T1` được tạo sẽ không thay thế phiên bản mà `T1` đang đọc.

Nếu `T1` tự cập nhật hàng đó, những lần đọc tiếp theo của `T1` nhìn thấy thay đổi của chính nó. Quy tắc snapshot không buộc giao dịch bỏ qua write set của mình.

### Phantom read trong các lần đọc snapshot

Phantom read thường được mô tả bằng một truy vấn có điều kiện trả về một tập hàng, sau đó cùng truy vấn chạy lại và nhận thêm hoặc mất hàng do giao dịch khác đã insert, delete hoặc cập nhật hàng để nó thỏa điều kiện.

Ví dụ:

```sql
-- T1 tạo snapshot S
SELECT id, status
FROM orders
WHERE status = 'PENDING';
```

Trong khi `T1` còn chạy, `T2` thêm một đơn hàng `PENDING` rồi commit. Khi `T1` chạy lại truy vấn trên, lần đọc snapshot vẫn không thấy hàng được `T2` thêm sau snapshot `S`. Tương tự, một hàng bị giao dịch khác xóa sau `S` vẫn có thể xuất hiện trong kết quả snapshot của `T1`.

Vì các lần đọc dùng cùng snapshot, SI ngăn phantom read theo nghĩa kết quả của lần đọc snapshot lặp lại thay đổi do commit bên ngoài. Tuy nhiên, **đừng suy ra rằng SI đã khóa khoảng giá trị hoặc bảo vệ mọi quy tắc dựa trên một tập hàng**. Một giao dịch khác vẫn có thể ghi vào các hàng khác nhau hoặc thêm dữ liệu mà giao dịch hiện tại chưa nhìn thấy. Các quyết định dựa trên tập hàng đó có thể dẫn đến write skew.

### Read skew và inconsistent analysis

Read skew xảy ra khi một giao dịch đọc các phần dữ liệu có quan hệ với nhau ở những thời điểm khác nhau, từ đó nhìn thấy một trạng thái kết hợp chưa từng tồn tại nhất quán.

Giả sử một tài khoản chuyển `100` từ `A` sang `B`:

```text
Trước chuyển tiền: A = 500, B = 300
Sau chuyển tiền:   A = 400, B = 400
```

Nếu một giao dịch đọc `A = 500`, sau đó giao dịch chuyển tiền commit, rồi nó đọc `B = 400`, giao dịch đọc có thể tính tổng là `900`, dù tổng thực tế trước và sau chuyển tiền đều là `800`. Nó đã kết hợp phiên bản trước cập nhật của `A` với phiên bản sau cập nhật của `B`.

Trong SI, cả hai lần đọc snapshot của giao dịch dùng cùng một thời điểm:

```text
T1: snapshot S
T1: đọc A = 500
T2: chuyển tiền, commit (A = 400, B = 400)
T1: đọc B = 300 theo snapshot S
```

`T1` nhìn thấy trạng thái cũ nhất quán (`A = 500`, `B = 300`) thay vì trộn hai thời điểm. Nếu chính `T1` cập nhật một trong hai hàng, thay đổi của `T1` được áp dụng thêm vào snapshot theo quy tắc read-your-own-writes.

## 3. Lost update và xung đột ghi trên cùng dữ liệu

Lost update xảy ra khi hai giao dịch cùng đọc một giá trị cũ, tính ra các giá trị mới rồi ghi đè nhau, khiến một thay đổi bị mất.

Giả sử `balance = 100`:

```text
T1 đọc 100 và tính 110 (cộng 10)
T2 đọc 100 và tính 80  (trừ 20)

T1 ghi 110
T2 ghi 80
```

Nếu cả hai lần ghi được chấp nhận theo kiểu ghi đè cuối cùng thắng, thay đổi cộng `10` của `T1` bị mất. Trong mô hình SI phổ biến với phát hiện xung đột ghi, hai giao dịch cùng ghi một hàng sẽ xung đột. Hệ thống chỉ cho một giao dịch commit; giao dịch còn lại nhận lỗi xung đột hoặc lỗi serialization và cần được xử lý.

Đây là lý do nhiều tài liệu nói SI ngăn lost update. Tuy nhiên, cần kiểm chứng hành vi thực tế của hệ quản trị và cách ứng dụng cập nhật dữ liệu:

- Hệ thống có phát hiện hai giao dịch ghi cùng hàng dựa trên snapshot không?
- Xung đột được phát hiện ngay khi `UPDATE`, tại thời điểm chờ khóa, hay khi commit?
- Giao dịch thua cuộc nhận lỗi gì? Ứng dụng có rollback và retry toàn bộ giao dịch không?
- Ứng dụng có dùng câu lệnh cập nhật nguyên tử như `SET balance = balance + 10`, hay đọc giá trị về ứng dụng rồi ghi lại một con số đã tính từ dữ liệu cũ?
- Có đường ghi nào dùng cơ chế khác, bảng không hỗ trợ giao dịch hoặc thao tác ghi không tham gia cùng cơ chế kiểm soát phiên bản không?

Một câu lệnh cập nhật nguyên tử giúp tránh mẫu đọc-sửa-ghi ở phía ứng dụng, nhưng vẫn cần hiểu khóa, điều kiện cập nhật và quy tắc xung đột của cơ sở dữ liệu. Không nên kết luận chỉ từ việc ứng dụng đã dùng một câu `UPDATE`.

## 4. Bất thường SI không ngăn được: write skew

Write skew là bất thường quan trọng nhất cần nhớ khi dùng Snapshot Isolation. Nó xảy ra khi hai giao dịch:

1. Cùng đọc những dữ liệu liên quan từ snapshot tương thích.
2. Dựa trên kết quả đọc để quyết định cập nhật.
3. Ghi lên các hàng khác nhau nên không tạo xung đột ghi trực tiếp.
4. Cùng commit, nhưng trạng thái cuối vi phạm một bất biến nghiệp vụ.

### Ví dụ: luôn phải có ít nhất một bác sĩ trực

Giả sử có hai bác sĩ đang trực:

| doctor_id | name | on_call |
|---:|---|---|
| 1 | An | true |
| 2 | Bình | true |

Quy tắc nghiệp vụ là **luôn có ít nhất một bác sĩ trực**. Hai giao dịch bắt đầu gần như đồng thời và cùng đọc snapshot có hai bác sĩ đang trực.

**Giao dịch T1:**

```sql
BEGIN;

SELECT COUNT(*)
FROM doctors
WHERE on_call = TRUE;
-- Kết quả theo snapshot: 2

UPDATE doctors
SET on_call = FALSE
WHERE doctor_id = 1;

COMMIT;
```

**Giao dịch T2, với snapshot được tạo trước khi T1 commit:**

```sql
BEGIN;

SELECT COUNT(*)
FROM doctors
WHERE on_call = TRUE;
-- Kết quả theo snapshot: 2

UPDATE doctors
SET on_call = FALSE
WHERE doctor_id = 2;

COMMIT;
```

Hai giao dịch ghi hai hàng khác nhau. Vì không có xung đột ghi trên cùng hàng, SI có thể cho cả hai commit. Trạng thái cuối:

| doctor_id | name | on_call |
|---:|---|---|
| 1 | An | false |
| 2 | Bình | false |

Không còn bác sĩ nào trực, vi phạm quy tắc nghiệp vụ. Mỗi giao dịch riêng lẻ đều thấy một bác sĩ khác vẫn trực trong snapshot của mình; kết hợp hai thay đổi mới làm quy tắc bị phá vỡ.

### Vì sao kiểm tra xung đột ghi không phát hiện được?

Có thể hình dung phụ thuộc giữa hai giao dịch như sau:

```text
T1 đọc trạng thái của bác sĩ 2
T1 ghi trạng thái của bác sĩ 1

T2 đọc trạng thái của bác sĩ 1
T2 ghi trạng thái của bác sĩ 2
```

T1 phụ thuộc vào dữ liệu mà T2 có thể thay đổi; T2 cũng phụ thuộc vào dữ liệu mà T1 có thể thay đổi. Đây là các phụ thuộc đọc-ghi (*read-write antidependencies*). Hai giao dịch không ghi cùng hàng nên kiểm tra write-write conflict đơn thuần không đủ để phát hiện chu trình phụ thuộc tuần tự hóa.

SI không đảm bảo rằng đồ thị phụ thuộc tuần tự hóa luôn không có chu trình. Vì vậy, SI mạnh hơn một số mức cô lập đọc thông thường nhưng vẫn yếu hơn Serializable.

### Cách bảo vệ bất biến nghiệp vụ

Tùy quy tắc dữ liệu và hệ quản trị, có thể chọn một trong các cách:

- **Dùng Serializable:** yêu cầu hệ quản trị bảo đảm kết quả tương đương một thứ tự tuần tự. Một giao dịch có thể bị hủy với lỗi serialization; ứng dụng phải retry toàn bộ giao dịch khi phù hợp.
- **Dùng một hàng điều phối chung:** mọi giao dịch thay đổi lịch trực đều cập nhật cùng một hàng đại diện, chẳng hạn tăng `version` của hàng `schedule_guard`. Như vậy, các giao dịch tạo xung đột ghi trên cùng một hàng và SI có thể buộc một giao dịch phải hủy rồi retry với snapshot mới. Nếu dùng `SELECT ... FOR UPDATE` để khóa hàng điều phối, phải kiểm chứng thời điểm tạo snapshot và hành vi sau khi chờ khóa: ở một số hệ thống, transaction vẫn giữ snapshot cũ sau khi lấy được khóa, nên chỉ khóa rồi đọc lại số lượng chưa chắc đã làm mới dữ liệu nó nhìn thấy.
- **Dùng ràng buộc dữ liệu phù hợp:** nếu bất biến có thể diễn đạt bằng `UNIQUE`, `CHECK`, khóa ngoại hoặc một cơ chế ràng buộc được hệ quản trị kiểm tra an toàn khi có giao dịch đồng thời, hãy để cơ sở dữ liệu thực thi nó. Không phải mọi quy tắc liên hàng đều có thể biểu diễn bằng một `CHECK` đơn giản.
- **Thiết kế lại mô hình ghi:** có thể lưu số lượng hoặc trạng thái điều phối trên một hàng chung để các giao dịch phải tranh chấp cùng một điểm ghi. Cách này cần bảo đảm dữ liệu tổng hợp luôn được cập nhật đúng và không trở thành một nguồn sai lệch mới.

Chỉ thêm một câu `SELECT COUNT(*)` trước khi `UPDATE` không bảo vệ được bất biến, vì cả hai giao dịch vẫn có thể đọc cùng một snapshot cũ.

## 5. Snapshot Isolation và Serializable khác nhau ở đâu?

Hai cơ chế đều có thể dùng MVCC, nhưng cam kết về kết quả khác nhau.

| Thuộc tính | Snapshot Isolation | Serializable |
|---|---|---|
| Đọc phiên bản nhất quán theo snapshot | Có | Có thể có, tùy triển khai |
| Dirty read | Bị ngăn chặn | Bị ngăn chặn |
| Non-repeatable read trong các lần đọc snapshot | Bị ngăn chặn | Bị ngăn chặn |
| Phantom trong các lần đọc snapshot lặp lại | Không xuất hiện từ commit bên ngoài sau snapshot | Được xử lý theo bảo đảm tuần tự hóa |
| Xung đột ghi trên cùng hàng | Thường phát hiện và hủy một giao dịch | Phải được xử lý để giữ tương đương tuần tự |
| Write skew trên các hàng khác nhau | Có thể xảy ra | Không được phép commit nếu làm vi phạm tương đương tuần tự |
| Kết quả tương đương một thứ tự tuần tự | Không bảo đảm | Có bảo đảm theo hợp đồng của mức cô lập |

Serializable có thể được triển khai bằng khóa phạm vi, predicate lock, theo dõi phụ thuộc hoặc kỹ thuật khác. Một số hệ thống dùng phát hiện bất thường ở thời điểm commit nên ứng dụng phải chấp nhận giao dịch bị từ chối và thử lại. SI thường cho khả năng đọc đồng thời tốt, nhưng ứng dụng phải tự bảo vệ các bất biến có thể bị write skew.

Không nên suy ra ngữ nghĩa chỉ từ tên `REPEATABLE READ`, `SNAPSHOT` hoặc `SERIALIZABLE` mà ORM hay cơ sở dữ liệu hiển thị. Tên mức cô lập có thể được ánh xạ khác nhau giữa các sản phẩm. Cần kiểm tra tài liệu của đúng phiên bản hệ quản trị, cấu hình datasource và loại câu lệnh đọc đang dùng.

## 6. Những tình huống cần kiểm chứng trong hệ thống thực tế

Khi áp dụng SI cho một ứng dụng, hãy kiểm chứng các trường hợp sau thay vì chỉ dựa vào tên isolation level.

### Ranh giới của snapshot

- Snapshot được tạo ngay khi `BEGIN`, ở câu đọc đầu tiên, hay ở từng câu lệnh?
- Hai câu `SELECT` trong cùng transaction có thật sự dùng cùng snapshot không?
- Giao dịch đọc lâu có tiếp tục thấy phiên bản cũ sau khi giao dịch khác commit không?
- Một transaction được mở bởi connection pool có vô tình giữ snapshot hoặc isolation level từ lần sử dụng trước không?

Ranh giới này ảnh hưởng trực tiếp đến kết quả kiểm tra non-repeatable read, phantom và read skew.

### Đọc thường và đọc có khóa

Các câu lệnh đọc snapshot thông thường có thể có ngữ nghĩa khác với `SELECT ... FOR UPDATE`, `FOR SHARE`, locking read hoặc thao tác đọc mới nhất. Một số hệ quản trị có thể chờ khóa, đọc phiên bản mới hơn, hoặc trả lỗi nếu hàng đã thay đổi kể từ snapshot.

Hãy kiểm tra riêng từng kiểu đọc mà ứng dụng thực sự dùng. Đặc biệt, không trộn kết quả của một truy vấn snapshot với một truy vấn đọc có khóa rồi giả định cả hai quan sát cùng một thời điểm.

### Cập nhật cùng hàng và xử lý lỗi

Tạo hai giao dịch đồng thời cập nhật cùng một hàng. Xác nhận giao dịch nào bị chặn, giao dịch nào thất bại, lỗi được trả ở câu lệnh hay lúc commit, và ứng dụng có rollback đúng cách.

Nếu cần retry, hãy retry toàn bộ transaction từ đầu để có snapshot mới. Chỉ chạy lại câu `UPDATE` cuối cùng thường không đủ, vì quyết định nghiệp vụ trước đó được đưa ra từ snapshot cũ. Retry phải có giới hạn, backoff phù hợp và bảo đảm các tác dụng phụ bên ngoài không bị thực hiện lặp ngoài ý muốn.

### Quy tắc liên hàng và liên bảng

Liệt kê các bất biến mà quyết định ghi phụ thuộc vào nhiều hàng hoặc nhiều bảng, ví dụ:

- Luôn có ít nhất một nhân viên đang trực.
- Tổng số chỗ đã đặt không vượt quá sức chứa.
- Tổng tiền phân bổ không vượt ngân sách.
- Một người không được có hai lịch đặt giao nhau.
- Chỉ có tối đa một bản ghi đang hoạt động trong một nhóm.

Với từng bất biến, hãy hỏi liệu hai giao dịch có thể đọc cùng điều kiện rồi ghi lên các hàng khác nhau hay không. Nếu có, phải thiết kế khóa, constraint hoặc Serializable để bảo vệ quy tắc.

### Predicate, insert và unique constraint

Thử trường hợp hai giao dịch cùng kiểm tra rằng chưa có hàng thỏa một điều kiện rồi cùng insert. Snapshot có thể khiến cả hai không nhìn thấy hàng mới của nhau. Nếu quy tắc là duy nhất, cần một unique constraint hoặc cơ chế đồng bộ phù hợp. Kiểm tra truy vấn ứng dụng trước khi insert không thay thế được unique constraint khi có cạnh tranh.

Với điều kiện dạng khoảng, tổng, `COUNT`, `SUM` hoặc `NOT EXISTS`, cần xác định rõ hệ quản trị có khóa predicate/range hay chỉ đọc snapshot. Đừng giả định SI tự động khóa mọi hàng tương lai có thể thỏa điều kiện.

### Thời gian sống của transaction và phiên bản cũ

Transaction đọc lâu có thể giữ snapshot cũ, khiến hệ quản trị phải giữ lại các phiên bản mà snapshot đó còn cần. Tùy engine, điều này có thể làm tăng lượng phiên bản chết, trì hoãn dọn dẹp hoặc tăng áp lực lưu trữ.

Kiểm tra thời lượng transaction, connection bị bỏ quên, cursor mở lâu và tác vụ báo cáo chạy nhiều phút. Transaction nên kết thúc ngay khi hoàn thành công việc cần snapshot; không giữ transaction trong lúc chờ người dùng hoặc gọi dịch vụ bên ngoài.

### Ranh giới transaction và tác dụng phụ bên ngoài

Xác nhận ORM, framework và connection pool thực sự mở một transaction bao quanh đúng chuỗi câu lệnh. Autocommit có thể khiến mỗi câu lệnh thành một transaction riêng, nên không có snapshot chung giữa nhiều câu đọc.

Email, HTTP request, gửi thông điệp hoặc thao tác trên hệ thống khác không tự động thuộc transaction cơ sở dữ liệu. Nếu transaction bị abort rồi retry, tác dụng phụ bên ngoài có thể đã xảy ra. Cần thiết kế idempotency hoặc transactional outbox khi quy trình nghiệp vụ yêu cầu tính nhất quán giữa dữ liệu và thông điệp.

## 7. Cách kiểm chứng bằng hai phiên kết nối

Một bài kiểm chứng tốt cần chạy đồng thời trên hai connection độc lập. Chỉ chạy hai transaction lần lượt sẽ không tạo ra cạnh tranh cần quan sát.

### Kiểm tra snapshot ổn định

Chuẩn bị hàng thử nghiệm `id = 1`, `value = 100`.

**Phiên A:**

```sql
BEGIN;

SELECT value FROM snapshot_demo WHERE id = 1;
-- 100; snapshot của A được thiết lập theo ngữ nghĩa engine
```

**Phiên B:**

```sql
BEGIN;

UPDATE snapshot_demo
SET value = 200
WHERE id = 1;

COMMIT;
```

**Quay lại phiên A:**

```sql
SELECT value FROM snapshot_demo WHERE id = 1;
-- Với SI dùng snapshot cấp transaction: vẫn là 100

COMMIT;
```

Mở transaction mới sau đó và đọc lại để xác nhận phiên bản `200` đã commit có thể nhìn thấy. Nếu kết quả trong phiên A là `200`, hãy kiểm tra xem snapshot có được tạo ở lần đọc đầu hay không, isolation level có thực sự là SI hay không, và câu đọc có phải locking/current read không.

### Kiểm tra write skew

Tạo hai hàng trực bác sĩ như ví dụ ở phần 4. Dùng hai phiên và một barrier trong test để bảo đảm cả hai transaction đều đọc được `COUNT(*) = 2` trước khi một phiên commit. Sau đó cho mỗi phiên cập nhật một hàng khác nhau.

Nếu cả hai cùng commit và không còn bác sĩ trực, thử lại bằng Serializable hoặc cơ chế khóa chung. Kết quả mong đợi là hệ thống từ chối ít nhất một giao dịch hoặc buộc hai quyết định diễn ra tuần tự để bất biến không bị phá vỡ.

Không nên dùng `sleep` tùy ý làm bằng chứng duy nhất về thứ tự chạy. Một test đồng thời đáng tin cậy nên dùng latch, barrier hoặc cơ chế đồng bộ tương đương để kiểm soát thời điểm hai transaction đọc và ghi.

### Kiểm tra retry

Khi một giao dịch thất bại do xung đột hoặc serialization, ghi nhận:

1. Mã lỗi và vị trí phát sinh lỗi.
2. Transaction đã rollback hoàn toàn chưa.
3. Retry có bắt đầu transaction mới và lấy snapshot mới không.
4. Mọi thao tác ngoài database có được bảo vệ khỏi thực hiện trùng không.
5. Số lần retry có giới hạn và lỗi cuối cùng có được trả về cho tầng gọi hay không.

## 8. Bảng tổng hợp các bất thường

| Bất thường | SI xử lý thế nào? | Điều cần nhớ |
|---|---|---|
| Dirty read | Ngăn chặn | Chỉ đọc phiên bản đã commit phù hợp snapshot và thay đổi của chính mình. |
| Non-repeatable read | Ngăn chặn trong snapshot | Cùng hàng được đọc từ cùng snapshot qua các lần đọc. |
| Phantom read | Ngăn phantom mới trong các lần đọc snapshot | Tập kết quả snapshot ổn định; điều đó không khóa predicate để bảo vệ mọi quy tắc liên hàng. |
| Read skew / inconsistent analysis | Ngăn chặn | Các hàng được đọc theo một ảnh chụp nhất quán. |
| Lost update trên cùng hàng | Thường ngăn bằng phát hiện xung đột ghi | Kiểm chứng chính sách conflict và cách ứng dụng retry. |
| Write skew trên các hàng khác nhau | Không ngăn chặn nói chung | Cần Serializable, khóa chung hoặc constraint phù hợp. |
| Vi phạm bất biến nghiệp vụ liên hàng | Không tự động ngăn chặn | Phải nhận diện và bảo vệ từng bất biến. |

Khi phân tích một hệ thống, đừng chỉ hỏi “mức cô lập có ngăn dirty read không?”. Hãy xác định dữ liệu nào được đọc từ snapshot, giao dịch ghi lên những hàng nào, và quyết định nghiệp vụ phụ thuộc vào điều kiện liên hàng nào. Snapshot Isolation tạo ra một góc nhìn đọc ổn định và thường xử lý xung đột ghi cùng hàng, nhưng các giao dịch vẫn có thể cùng commit trên những hàng khác nhau rồi phá vỡ một bất biến chung. Đó là lý do cần kiểm chứng write skew và chọn Serializable, khóa hoặc ràng buộc dữ liệu khi nghiệp vụ đòi hỏi tính tuần tự hóa.
