# Phụ thuộc đọc–ghi và nguyên nhân ảnh chụp chưa đủ bảo đảm khả tuần tự

Snapshot Isolation (SI) cho phép mỗi transaction đọc một ảnh chụp nhất quán của dữ liệu tại một thời điểm. Nhờ đọc các phiên bản đã commit thay vì chờ mọi thao tác ghi, nhiều transaction có thể đọc đồng thời mà không nhìn thấy dữ liệu chưa commit hoặc một trạng thái bị ghép từ nhiều thời điểm khác nhau.

Tuy nhiên, một ảnh chụp nhất quán chỉ bảo đảm transaction nhìn thấy một trạng thái dữ liệu hợp lệ tại thời điểm bắt đầu. Nó không bảo đảm các quyết định được đưa ra từ ảnh chụp đó vẫn tương thích với mọi transaction khác khi tất cả cùng commit. Hai transaction có thể đọc cùng một trạng thái, cập nhật những hàng khác nhau, rồi kết hợp các thay đổi thành một trạng thái vi phạm quy tắc nghiệp vụ.

Nguyên nhân nằm ở phụ thuộc đọc–ghi (read–write dependency), còn gọi là phụ thuộc chống (read–write anti-dependency). Khi một transaction đọc phiên bản cũ của dữ liệu và transaction khác ghi phiên bản mới hơn, thứ tự đọc–ghi đó tạo ra một cạnh trong đồ thị tuần tự hóa. Nhiều cạnh đọc–ghi có thể tạo thành chu trình, dù không có hai transaction nào ghi đè cùng một hàng. Đó là lý do Snapshot Isolation chưa đủ để bảo đảm khả tuần tự (serializability).

## 1. Ảnh chụp nhất quán bảo đảm điều gì?

Trong Snapshot Isolation, transaction thường đọc dữ liệu từ một snapshot được xác định khi transaction bắt đầu hoặc tại thời điểm hệ quản trị thiết lập snapshot. Những thay đổi commit sau thời điểm đó không xuất hiện trong các lần đọc snapshot tiếp theo của transaction.

Điều này mang lại một số thuộc tính hữu ích:

- Transaction không đọc giá trị chưa commit từ transaction khác.
- Các lần đọc trong cùng transaction nhìn thấy một tập phiên bản ổn định theo snapshot.
- Transaction có thể đọc mà ít phải chờ khóa ghi của transaction khác, tùy cơ chế MVCC của hệ quản trị.
- Nhiều hệ thống dùng quy tắc từ chối một transaction khi nó cố ghi lên hàng đã bị transaction đồng thời khác thay đổi kể từ snapshot. Quy tắc này thường được gọi là first-committer-wins hoặc first-updater-wins, tùy cách triển khai.

Những bảo đảm đó giúp tránh nhiều bất thường đọc và ngăn hai transaction cùng commit các phiên bản ghi xung đột trên cùng một hàng theo mô hình SI thông dụng. Nhưng chúng không kiểm tra đầy đủ quan hệ giữa những hàng khác nhau mà các transaction đã đọc và ghi.

Ví dụ, transaction T1 đọc hàng A và B rồi chỉ cập nhật A. Transaction T2 cũng đọc A và B nhưng chỉ cập nhật B. Vì tập ghi của hai transaction không giao nhau, cơ chế phát hiện xung đột ghi trên cùng hàng có thể cho phép cả hai commit. Nếu mỗi lần cập nhật dựa trên điều kiện mà transaction đã đọc, kết quả cuối cùng vẫn có thể vi phạm invariant liên quan đến cả A và B.

## 2. Các loại phụ thuộc trong đồ thị tuần tự hóa

Để biết một lịch thực thi có tương đương với một thứ tự chạy tuần tự hay không, ta có thể dựng đồ thị tuần tự hóa (serialization graph). Mỗi transaction là một đỉnh. Cạnh có hướng từ transaction này sang transaction khác biểu diễn một quan hệ thứ tự mà lịch thực thi buộc phải giữ.

Với dữ liệu nhiều phiên bản, cần chú ý ba loại phụ thuộc chính:

| Loại phụ thuộc | Tình huống | Hướng cạnh |
|---|---|---|
| Write–read (wr) | T2 đọc phiên bản do T1 ghi. | T1 → T2 |
| Write–write (ww) | T2 ghi đè phiên bản mà T1 đã ghi trước đó. | T1 → T2 |
| Read–write (rw), hay anti-dependency | T1 đọc một phiên bản cũ; T2 ghi phiên bản mới hơn của cùng dữ liệu. | T1 → T2 |

Điểm dễ nhầm là hướng của cạnh rw. T1 đọc trước khi T2 ghi phiên bản mới, vì vậy trong một lịch tuần tự tương đương, T1 phải đứng trước T2. Cạnh đi từ transaction đọc phiên bản cũ đến transaction ghi phiên bản mới: `T1 →rw T2`.

Ví dụ, T1 đọc `balance = 100`, sau đó T2 cập nhật số dư thành 80. Nếu T1 đọc giá trị 100 từ snapshot cũ, T1 và T2 có quan hệ rw theo hướng T1 → T2. Trong thứ tự tuần tự tương đương, T1 phải đứng trước T2; nếu T2 đứng trước T1, T1 sẽ phải đọc giá trị 80.

Một lịch thực thi chỉ có thể tương đương với thứ tự tuần tự nếu đồ thị tuần tự hóa không có chu trình. Khi có chu trình, các ràng buộc thứ tự mâu thuẫn với nhau: transaction A phải đứng trước B, B phải đứng trước C, nhưng C lại phải đứng trước A. Không có thứ tự tuần tự nào thỏa mãn tất cả.

## 3. Ví dụ kinh điển: write skew với hai bác sĩ trực

Giả sử một ca trực có hai bác sĩ A và B. Quy tắc nghiệp vụ là luôn phải có ít nhất một bác sĩ đang trực:

```text
on_call(A) + on_call(B) >= 1
```

Ban đầu cả hai bác sĩ đều đang trực:

| Bác sĩ | Trạng thái ban đầu |
|---|---:|
| A | 1 (đang trực) |
| B | 1 (đang trực) |

Hai transaction chạy gần như đồng thời:

| Thời điểm | Transaction T1 | Transaction T2 |
|---|---|---|
| 1 | Bắt đầu, nhận snapshot | |
| 2 | | Bắt đầu, nhận snapshot |
| 3 | Đọc A=1, B=1 | |
| 4 | | Đọc A=1, B=1 |
| 5 | Quyết định tắt trạng thái trực của A | |
| 6 | | Quyết định tắt trạng thái trực của B |
| 7 | Ghi A=0, commit | |
| 8 | | Ghi B=0, commit |

Sau khi cả hai commit, dữ liệu là:

| Bác sĩ | Trạng thái cuối |
|---|---:|
| A | 0 (không trực) |
| B | 0 (không trực) |

Invariant bị vi phạm vì không còn bác sĩ nào trực. Mỗi transaction riêng lẻ đều đọc một snapshot hợp lệ và chỉ cập nhật một hàng. Hai transaction không ghi lên cùng một hàng, nên cơ chế chỉ phát hiện xung đột ghi trên cùng hàng không nhất thiết từ chối transaction nào.

### Đồ thị phụ thuộc đọc–ghi

T1 đọc trạng thái của B trước khi T2 ghi B=0. Vì vậy T1 phải đứng trước T2 trong thứ tự tuần tự:

```text
T1 ──rw──> T2
```

T2 đọc trạng thái của A trước khi T1 ghi A=0. Vì vậy T2 phải đứng trước T1:

```text
T2 ──rw──> T1
```

Gộp hai cạnh:

```text
        rw
   T1 -------> T2
    ^           |
    |           |
    +-----------+
         rw
```

Đồ thị có chu trình T1 → T2 → T1. Không thể sắp xếp T1 và T2 thành một thứ tự tuần tự hợp lệ. Lịch thực thi vì vậy không khả tuần tự, mặc dù cả hai transaction đã đọc snapshot nhất quán.

Hiện tượng này gọi là **write skew**. Hai transaction đọc chung một điều kiện nghiệp vụ nhưng ghi lên những hàng khác nhau. Mỗi transaction nhìn thấy một trạng thái mà thay đổi riêng của nó có vẻ hợp lệ; các thay đổi kết hợp lại làm sai invariant.

## 4. Vì sao phát hiện xung đột ghi cùng hàng chưa đủ?

Nhiều triển khai Snapshot Isolation sử dụng quy tắc ngăn hai transaction đồng thời commit các thay đổi xung đột trên cùng một hàng. Điều đó giúp tránh một số trường hợp lost update, nhưng write skew ở ví dụ trên có đặc điểm khác:

- T1 ghi hàng A.
- T2 ghi hàng B.
- T1 chỉ đọc hàng B để quyết định có thể tắt A hay không.
- T2 chỉ đọc hàng A để quyết định có thể tắt B hay không.
- Không có xung đột write–write trên cùng hàng, nhưng có hai phụ thuộc read–write ngược chiều.

Do đó, tập ghi không giao nhau không đồng nghĩa với việc hai transaction độc lập về mặt nghiệp vụ. Một transaction có thể phụ thuộc vào dữ liệu mà transaction kia sẽ thay đổi, dù nó không ghi lên chính dữ liệu đó.

Đây là điểm khác nhau giữa kiểm tra xung đột vật lý trên hàng được ghi và kiểm tra khả tuần tự của toàn bộ lịch thực thi. Khả tuần tự phải xét cả những lần đọc đã ảnh hưởng đến quyết định ghi.

## 5. Snapshot Isolation và Serializable khác nhau thế nào?

| Đặc điểm | Snapshot Isolation | Serializable |
|---|---|---|
| Dữ liệu đọc | Đọc từ snapshot nhất quán. | Phải tạo kết quả tương đương một thứ tự tuần tự hợp lệ. |
| Dirty read | Không đọc dữ liệu chưa commit. | Không đọc dữ liệu chưa commit. |
| Đọc lặp lại | Các lần đọc theo snapshot nhìn thấy phiên bản ổn định. | Hành vi phải tương đương thứ tự tuần tự; hệ quản trị có thể dùng khóa hoặc phiên bản. |
| Ghi cùng hàng | Nhiều triển khai từ chối một transaction khi có xung đột ghi đồng thời. | Hệ quản trị phải bảo đảm lịch tuần tự hóa được, có thể chờ hoặc hủy transaction. |
| Phụ thuộc đọc–ghi giữa các hàng khác nhau | Có thể tạo chu trình và write skew. | Phải phát hiện hoặc ngăn lịch tạo chu trình. |
| Khả năng write skew | Có thể xảy ra. | Không được phép commit lịch vi phạm khả tuần tự. |

Snapshot Isolation là một bảo đảm mạnh và hữu ích, nhưng không đồng nghĩa với Serializable. Serializable yêu cầu kết quả của các transaction đồng thời phải tương đương với một thứ tự thực thi tuần tự nào đó. Nếu một tổ hợp đọc–ghi tạo ra chu trình trong đồ thị, hệ quản trị phải ngăn lịch đó được commit đầy đủ.

Không nên suy luận rằng một isolation level có tên `REPEATABLE READ` luôn tương đương Snapshot Isolation hoặc Serializable. SQL chuẩn và từng hệ quản trị có ngữ nghĩa, cơ chế và mức hỗ trợ khác nhau. Cần xác nhận tài liệu của đúng sản phẩm, phiên bản và cấu hình đang sử dụng.

## 6. Read–write anti-dependency có thể xuất hiện ở đâu?

Phụ thuộc đọc–ghi thường xuất hiện khi transaction đọc một điều kiện rồi cập nhật một phần dữ liệu nằm trong điều kiện đó hoặc có liên quan đến điều kiện đó.

### 6.1. Giới hạn số người đăng ký

Một lớp có sức chứa 30 người. Hai transaction cùng đọc số lượng đăng ký là 29, sau đó mỗi transaction thêm một học viên. Nếu hai transaction ghi các hàng đăng ký khác nhau, snapshot có thể không phát hiện xung đột ghi cùng hàng. Kết quả là có 31 người.

Các lần đọc `COUNT(*)` phụ thuộc vào những hàng mà transaction khác thêm vào. Đây là quan hệ đọc–ghi trên một predicate (điều kiện truy vấn), dù hàng được thêm chưa tồn tại trong snapshot ban đầu.

### 6.2. Ngân sách theo nhiều khoản mục

Một phòng ban có hai khoản mục chi tiêu A và B, với tổng chi không vượt 100 triệu. T1 đọc cả hai khoản mục và tăng A; T2 cũng đọc cả hai và tăng B. Nếu mỗi transaction chỉ kiểm tra tổng cũ trước khi ghi, cả hai có thể cùng vượt giới hạn tổng hợp mà không ghi đè cùng một hàng.

### 6.3. Phân bổ tài nguyên theo điều kiện chung

Một hệ thống chỉ cho phép tối đa N tác vụ ở trạng thái hoạt động. Nhiều worker cùng đọc số tác vụ đang chạy rồi cập nhật trạng thái những tác vụ khác nhau. Nếu việc kiểm tra và thay đổi không được phối hợp trên một invariant chung, số tác vụ có thể vượt giới hạn.

Các ví dụ đều có một điểm chung: transaction đưa ra quyết định dựa trên tập dữ liệu hoặc kết quả tổng hợp, nhưng thay đổi của transaction khác có thể làm mất hiệu lực quyết định đó.

## 7. Cách phát hiện và ngăn chu trình phụ thuộc

### 7.1. Dùng mức Serializable

Nếu invariant phụ thuộc vào nhiều hàng hoặc predicate và không thể biểu diễn an toàn bằng một thao tác nguyên tử, Serializable thường là lựa chọn trực tiếp. Hệ quản trị có thể dùng khóa, predicate/range lock hoặc theo dõi phụ thuộc đọc–ghi để ngăn chu trình.

Serializable không có nghĩa mọi transaction phải chạy lần lượt hoàn toàn. Nhiều transaction vẫn có thể chạy đồng thời; hệ quản trị chỉ cần bảo đảm lịch được commit tương đương một thứ tự tuần tự. Khi không thể bảo đảm, nó có thể chờ hoặc hủy một transaction.

Ứng dụng phải xử lý serialization failure bằng cách chạy lại toàn bộ transaction khi nghiệp vụ cho phép. Không chỉ chạy lại câu lệnh cuối, vì những lần đọc trước đó có thể đã tạo ra quyết định không còn hợp lệ.

### 7.2. Serializable Snapshot Isolation (SSI)

Một số hệ quản trị triển khai Serializable bằng cách theo dõi các phụ thuộc đọc–ghi trên snapshot thay vì khóa mọi lần đọc. Cách tiếp cận này thường được gọi là Serializable Snapshot Isolation (SSI).

SSI theo dõi các anti-dependency và nhận diện những cấu trúc nguy hiểm có thể hoàn thiện thành chu trình tuần tự hóa. Khi phát hiện cấu trúc như vậy, hệ quản trị có thể hủy một transaction để bảo đảm các transaction còn lại tạo được lịch tuần tự hóa.

Do việc phát hiện có thể bảo thủ, một transaction đôi khi bị hủy dù lịch cụ thể cuối cùng có thể vẫn tuần tự hóa được. Ứng dụng cần coi lỗi serialization là một kết quả bình thường có thể xảy ra dưới tải đồng thời và có chính sách retry có giới hạn.

### 7.3. Khóa một hàng điều phối chung

Nếu mọi transaction có thể làm thay đổi invariant đều khóa cùng một hàng điều phối trước khi đọc dữ liệu liên quan, các thao tác sẽ được tuần tự hóa tại điểm đó.

Ví dụ, thêm một hàng `class_capacity` cho mỗi lớp. Mọi transaction đăng ký đều khóa hàng của lớp trước khi đếm và thêm đăng ký. Khi T1 giữ khóa, T2 phải chờ trước khi đọc trạng thái sức chứa. Sau khi T1 commit, T2 mới tiếp tục và đọc trạng thái đã cập nhật.

Khóa điều phối chỉ hiệu quả khi mọi đường ghi có liên quan đều tuân thủ cùng quy tắc. Phải lấy khóa trước các lần đọc quyết định nghiệp vụ. Với hệ quản trị thiết lập snapshot ngay khi transaction bắt đầu, cần xác nhận cách kết hợp khóa và snapshot để transaction chờ không tiếp tục dùng một snapshot cũ.

### 7.4. Biểu diễn invariant trong một hàng hoặc constraint

Nếu có thể, hãy đưa quy tắc tổng hợp về một hàng được cập nhật nguyên tử. Ví dụ, dùng bộ đếm sức chứa và câu `UPDATE` có điều kiện:

```sql
UPDATE class_capacity
SET enrolled_count = enrolled_count + 1
WHERE class_id = :class_id
  AND enrolled_count < capacity;
```

Ứng dụng kiểm tra số hàng bị ảnh hưởng. Nếu một hàng được cập nhật, tiếp tục ghi bản đăng ký trong cùng transaction; nếu không, từ chối vì lớp đã đầy hoặc không tồn tại. Có thể thêm unique constraint để ngăn một học viên đăng ký cùng lớp nhiều lần.

Một hàng điều phối hoặc bộ đếm giúp biến quy tắc nhiều hàng thành một điểm ghi có thể kiểm soát. Tuy nhiên, bộ đếm và các bản ghi chi tiết phải được cập nhật trong cùng transaction để không bị lệch.

### 7.5. Dùng khóa phạm vi hoặc predicate lock

Nếu invariant phụ thuộc vào toàn bộ hàng thỏa một điều kiện, khóa từng hàng hiện có có thể chưa đủ vì transaction khác vẫn có thể chèn một hàng mới thỏa điều kiện. Khóa phạm vi hoặc predicate lock có thể bảo vệ điều kiện truy vấn, tùy khả năng của hệ quản trị.

Phải xác nhận khóa bao phủ đúng phạm vi nghiệp vụ và không giả định mọi `SELECT ... FOR UPDATE` đều khóa các hàng chưa tồn tại. Nếu hệ quản trị không hỗ trợ cách khóa predicate phù hợp, có thể dùng Serializable hoặc một hàng điều phối.

## 8. Phân biệt write skew với lost update

Hai hiện tượng thường bị nhầm lẫn vì đều xuất phát từ các transaction đồng thời:

| Hiện tượng | Đặc điểm | Ví dụ |
|---|---|---|
| Lost update | Hai transaction cùng cập nhật một giá trị dựa trên bản đọc cũ; một thay đổi bị ghi đè. | Hai lần tăng số dư cùng đọc 100 rồi đều ghi 110, làm mất một lần tăng. |
| Write skew | Hai transaction đọc chung một invariant nhưng cập nhật các hàng khác nhau; các thay đổi kết hợp làm invariant sai. | Hai bác sĩ cùng đọc rằng còn người trực khác rồi mỗi người tắt trạng thái trực của mình. |

Một triển khai Snapshot Isolation có thể ngăn lost update trên cùng hàng bằng cách từ chối một ghi xung đột, nhưng vẫn cho phép write skew vì không có xung đột write–write. Vì vậy, kiểm tra xem các transaction có ghi cùng hàng hay không là chưa đủ; phải xem những lần đọc nào đã ảnh hưởng đến quyết định ghi.

## 9. Quy trình phân tích phụ thuộc đọc–ghi

Khi điều tra một lỗi đồng thời hoặc thiết kế transaction có nhiều bước, hãy thực hiện theo trình tự:

1. Viết invariant nghiệp vụ bằng điều kiện có thể kiểm tra, chẳng hạn tổng số người trực luôn lớn hơn hoặc bằng một.
2. Liệt kê tập dữ liệu mỗi transaction đọc và ghi, gồm cả điều kiện truy vấn và các hàng có thể được thêm mới.
3. Xác định những lần đọc đã ảnh hưởng đến quyết định ghi nào.
4. Với mỗi hàng hoặc predicate được đọc, tìm transaction đồng thời có thể ghi thay đổi làm kết quả đọc đó trở nên cũ.
5. Vẽ cạnh rw từ transaction đọc phiên bản cũ đến transaction ghi phiên bản mới; bổ sung các cạnh wr và ww cần thiết.
6. Kiểm tra đồ thị có chu trình hay không. Nếu có, lịch không khả tuần tự.
7. Chọn cách ngăn chu trình: Serializable/SSI, khóa điều phối, predicate/range lock, constraint hoặc thiết kế cập nhật nguyên tử.
8. Kiểm thử bằng nhiều connection chạy chồng lấp và xác nhận invariant sau khi tất cả transaction kết thúc.

Một bài kiểm thử write skew nên điều khiển thứ tự rõ ràng: cả hai transaction bắt đầu và đọc cùng snapshot trước khi transaction nào ghi; sau đó mỗi transaction cập nhật một hàng riêng rồi thử commit. Nếu chỉ chạy lần lượt T1 rồi T2, bài kiểm thử không tái hiện được lịch gây lỗi.

## 10. Những điều cần quan sát trong vận hành

Khi chuyển một workload sang Serializable hoặc bổ sung cơ chế phối hợp, cần theo dõi:

- Số transaction bị từ chối do serialization failure.
- Số lần retry và tỷ lệ retry thành công.
- Thời gian chờ khóa và deadlock nếu giải pháp dùng locking.
- Độ trễ commit và thông lượng khi tải tăng.
- Các invariant quan trọng sau những đợt xử lý đồng thời cao.

Retry phải chạy lại toàn bộ transaction, có giới hạn số lần thử và backoff phù hợp. Nếu transaction có tác dụng phụ ngoài cơ sở dữ liệu như gửi email hoặc gọi dịch vụ thanh toán, cần bảo đảm retry không lặp tác dụng phụ; có thể ghi sự kiện trong cùng transaction rồi xử lý sau commit bằng transactional outbox.

Không nên tăng mức cô lập chỉ để xử lý một lỗi mà chưa xác định được phụ thuộc gây lỗi. Một hàng điều phối hoặc cập nhật nguyên tử có thể đơn giản và hiệu quả hơn cho một invariant cụ thể. Ngược lại, nếu transaction phụ thuộc vào nhiều predicate phức tạp, một cơ chế Serializable có thể dễ chứng minh đúng hơn việc tự quản lý nhiều khóa rời rạc.

## 11. Checklist khi snapshot chưa đủ

- [ ] Đã xác định invariant phụ thuộc vào nhiều hàng hoặc predicate.
- [ ] Đã liệt kê tập đọc và tập ghi của từng transaction liên quan.
- [ ] Đã xem xét các phụ thuộc đọc–ghi, không chỉ xung đột ghi cùng hàng.
- [ ] Đã hiểu hướng cạnh rw: transaction đọc phiên bản cũ đi trước transaction ghi phiên bản mới.
- [ ] Đã kiểm tra đồ thị phụ thuộc có chu trình hay không.
- [ ] Đã phân biệt write skew với lost update.
- [ ] Đã xác nhận snapshot isolation và Serializable có ngữ nghĩa gì trên hệ quản trị đang dùng.
- [ ] Đã chọn cơ chế ngăn chu trình phù hợp: Serializable/SSI, khóa điều phối, predicate lock, constraint hoặc cập nhật nguyên tử.
- [ ] Đã thiết kế retry toàn transaction và bảo vệ tác dụng phụ ngoài cơ sở dữ liệu.
- [ ] Đã kiểm thử lịch đồng thời thực sự và kiểm tra invariant sau commit.

Ảnh chụp nhất quán bảo đảm transaction đọc một trạng thái dữ liệu ổn định. Khả tuần tự còn yêu cầu mọi quan hệ đọc–ghi giữa các transaction phải cùng phù hợp với một thứ tự thực thi duy nhất. Khi các transaction đọc chung dữ liệu nhưng ghi những hàng khác nhau, các phụ thuộc chống có thể tạo thành chu trình và gây write skew. Muốn bảo vệ invariant trong trường hợp đó, cần cơ chế kiểm soát phụ thuộc ở mức Serializable hoặc một thiết kế khóa/cập nhật chung mà mọi transaction liên quan đều tuân thủ.
