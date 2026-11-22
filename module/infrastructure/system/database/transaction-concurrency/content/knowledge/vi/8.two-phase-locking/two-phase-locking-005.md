# Khóa thận trọng trước khi thực thi và chi phí biết trước tập dữ liệu

Trong kiểm soát đồng thời, khóa hai pha (Two-Phase Locking — 2PL) bảo đảm các transaction có thể được sắp xếp thành một thứ tự tuần tự tương đương. Tuy nhiên, 2PL thông thường vẫn có thể tạo deadlock: mỗi transaction giữ một số khóa rồi chờ khóa mà transaction khác đang giữ.

Khóa hai pha thận trọng (Conservative 2PL), còn gọi là Static 2PL, thay đổi thời điểm lấy khóa. Transaction phải khai báo toàn bộ dữ liệu sẽ đọc hoặc ghi và loại khóa cần dùng trước khi bắt đầu xử lý. Bộ quản lý khóa chỉ cấp khóa khi có thể cấp tất cả cùng lúc. Nếu còn thiếu dù chỉ một khóa, transaction chờ mà không giữ khóa nào.

Đổi lại, giao thức này loại bỏ deadlock do chờ khóa trong chính cơ chế đó. Cái giá phải trả là ứng dụng hoặc hệ thống phải biết trước tập dữ liệu cần truy cập. Với truy vấn động, tập dữ liệu lớn hoặc nghiệp vụ chỉ xác định được bản ghi cần dùng sau khi đọc dữ liệu khác, việc khai báo trước có thể khó khăn và dẫn đến khóa dư thừa.

## 1. Nhắc lại khóa hai pha

Một transaction có thể yêu cầu các khóa đọc và ghi trên dữ liệu:

- **Shared lock (S):** cho phép nhiều transaction cùng đọc một đối tượng. Khóa S không tương thích với khóa X trên cùng đối tượng.
- **Exclusive lock (X):** dành quyền ghi độc quyền trên đối tượng. Khóa X không tương thích với khóa S hoặc X khác trên cùng đối tượng.

Bảng tương thích cơ bản:

| Khóa đang được giữ | Yêu cầu S | Yêu cầu X |
|---|---:|---:|
| S | Có thể cấp | Phải chờ |
| X | Phải chờ | Phải chờ |

2PL chia vòng đời lấy và nhả khóa thành hai pha:

1. **Growing phase:** transaction có thể lấy thêm khóa hoặc nâng cấp khóa, nhưng chưa được nhả khóa.
2. **Shrinking phase:** sau khi nhả khóa đầu tiên, transaction không được lấy thêm khóa mới hoặc nâng cấp khóa.

Điều kiện quan trọng là transaction không được quay lại pha lấy khóa sau khi đã bắt đầu nhả khóa. Tuân thủ 2PL bảo đảm conflict serializability, nhưng bản thân giao thức 2PL thông thường không loại bỏ deadlock.

Ví dụ, transaction T1 lấy khóa X trên hàng A rồi chờ hàng B; T2 đã lấy khóa X trên B rồi chờ A. T1 không thể tiếp tục nếu T2 chưa nhả B, còn T2 không thể tiếp tục nếu T1 chưa nhả A. Hai transaction tạo thành một vòng chờ.

## 2. Conservative 2PL hoạt động thế nào?

Conservative 2PL yêu cầu transaction xác định trước toàn bộ tập đối tượng cần khóa và chế độ khóa cho từng đối tượng. Trước khi thực thi câu lệnh nghiệp vụ, transaction gửi một yêu cầu lấy khóa tổng hợp.

Bộ quản lý khóa xử lý yêu cầu theo nguyên tắc:

- Nếu tất cả khóa trong tập yêu cầu đều tương thích với các khóa đang được giữ, cấp toàn bộ khóa cho transaction.
- Nếu ít nhất một khóa chưa thể cấp, không cấp khóa nào và để transaction chờ.
- Khi đủ điều kiện, cấp cả tập khóa rồi transaction mới bắt đầu đọc hoặc ghi dữ liệu.
- Trong quá trình thực thi, transaction không cần xin thêm khóa. Nó nhả các khóa theo quy tắc 2PL đã chọn.

Minh họa:

```text
T1 khai báo: X(A), X(B)
       |
       v
Yêu cầu cấp đồng thời cả X(A) và X(B)
       |
       +---- Cả hai khả dụng ----> Cấp cả hai -> Thực thi -> Nhả khóa
       |
       +---- Có khóa đang bận ----> Chờ, giữ 0 khóa
                                      |
                                      v
                              Đợi đến khi cấp đủ cả tập
```

Điểm quyết định là transaction không được giữ một phần tập khóa trong lúc chờ phần còn lại. Nếu lấy A trước, giữ A rồi chờ B, giao thức đã quay về kiểu lấy khóa từng phần và không còn bảo đảm tránh deadlock của Conservative 2PL.

## 3. Vì sao giao thức tránh deadlock?

Deadlock do khóa cần một vòng chờ: mỗi transaction trong vòng phải đang giữ ít nhất một khóa mà transaction kế tiếp cần, đồng thời chờ thêm khóa do transaction khác giữ.

Trong Conservative 2PL, một transaction đang chờ yêu cầu lấy khóa tổng hợp thì chưa giữ khóa nào. Transaction đã được cấp khóa thì đã có đủ toàn bộ khóa cần thiết và có thể thực thi mà không phải chờ thêm khóa thuộc tập đã khai báo. Vì vậy, không thể hình thành vòng chờ kiểu “giữ một khóa và chờ khóa tiếp theo” giữa các transaction tuân thủ giao thức.

Xét hai giao dịch chuyển tiền:

- T1 chuyển tiền từ tài khoản A sang B, cần khóa X(A) và X(B).
- T2 chuyển tiền từ B sang A, cũng cần khóa X(A) và X(B).

Nếu T1 được cấp cả hai khóa trước, T2 chờ mà không giữ khóa nào. T1 hoàn tất và nhả khóa; sau đó T2 mới được cấp cả tập khóa. Không xảy ra trường hợp T1 giữ A chờ B trong khi T2 giữ B chờ A.

Điều kiện này áp dụng cho các yêu cầu khóa được quản lý theo cùng giao thức. Nó không tự loại bỏ deadlock ở tài nguyên khác như mutex trong ứng dụng, khóa file, dịch vụ bên ngoài hoặc một cơ chế khóa khác được lấy theo thứ tự không nhất quán. Nếu transaction đã giữ khóa cơ sở dữ liệu rồi chờ một tài nguyên ngoài giao thức, hệ thống vẫn có thể gặp vòng chờ ở cấp ứng dụng.

## 4. Ví dụ: chuyển tiền giữa hai tài khoản

Một giao dịch chuyển tiền cần đọc và cập nhật số dư của hai tài khoản. Vì cả hai hàng đều được đọc và ghi, transaction cần khóa X trên cả hai hàng ngay từ đầu.

Pseudocode mô tả yêu cầu khóa tổng hợp:

```text
transfer(fromAccount, toAccount, amount):
    requiredLocks = {
        X(account[fromAccount]),
        X(account[toAccount])
    }

    lockManager.acquireAllOrWait(requiredLocks)

    try:
        source = read(account[fromAccount])
        target = read(account[toAccount])

        if source.balance < amount:
            rollback()
            return INSUFFICIENT_FUNDS

        source.balance = source.balance - amount
        target.balance = target.balance + amount

        commit()
        return SUCCESS
    finally:
        lockManager.releaseAccordingToProtocol(requiredLocks)
```

`acquireAllOrWait` là thao tác giả định của bộ quản lý khóa: hoặc cấp toàn bộ tập khóa, hoặc để transaction chờ mà không cấp khóa nào. Đây là pseudocode để giải thích giao thức, không phải tên một câu lệnh SQL chuẩn.

Khi đã có cả hai khóa, transaction có thể kiểm tra số dư và cập nhật hai tài khoản mà không bị transaction khác ghi đồng thời lên hai hàng đó. Nếu một transaction khác cũng chuyển tiền giữa hai tài khoản này theo chiều ngược lại, nó phải đợi được cấp đủ tập khóa trước khi đọc số dư.

Trong hệ thống thực tế, cần bảo đảm tài khoản nguồn và đích khác nhau hoặc xử lý trường hợp chúng trùng nhau để không khai báo cùng một đối tượng hai lần với cách xử lý không nhất quán. Cũng cần kiểm tra số tiền hợp lệ, ghi nhận lịch sử chuyển tiền và đặt các cập nhật trong cùng một transaction cơ sở dữ liệu.

## 5. Vì sao phải biết trước tập dữ liệu?

Conservative 2PL cần biết hai thông tin trước khi thực thi:

1. **Đối tượng nào sẽ được truy cập:** hàng, trang, bảng, khoảng khóa hoặc đối tượng khác tùy mức khóa của hệ quản trị.
2. **Chế độ khóa cuối cùng của từng đối tượng:** S nếu chỉ đọc; X nếu có thể ghi. Nếu transaction sẽ đọc rồi cập nhật cùng một hàng, cần khai báo X ngay từ đầu để tránh phải nâng cấp khóa sau khi đã bắt đầu.

Yêu cầu này phù hợp với nghiệp vụ có tập khóa nhỏ và xác định được từ đầu, chẳng hạn chuyển tiền giữa hai tài khoản đã biết mã, cập nhật một nhóm sản phẩm được chọn sẵn hoặc xử lý một lô bản ghi có danh sách khóa rõ ràng.

Nó khó áp dụng hơn với truy vấn phụ thuộc dữ liệu vừa đọc. Ví dụ, một transaction tìm tất cả đơn hàng đang chờ của một khách hàng, rồi dựa trên trạng thái từng đơn để quyết định cập nhật thêm những bảng khác. Trước khi chạy truy vấn, ứng dụng có thể chưa biết chính xác những hàng nào thỏa điều kiện và những hàng liên quan tiếp theo.

Tập khóa khai báo phải bao gồm cả phạm vi bảo vệ điều kiện truy vấn, không chỉ những hàng tình cờ tồn tại tại thời điểm bắt đầu. Nếu nghiệp vụ phụ thuộc vào điều kiện như “mọi đăng ký của lớp X” hoặc “tất cả sản phẩm trong khoảng giá này”, transaction còn phải ngăn một transaction khác thêm hàng mới thỏa điều kiện trong lúc xử lý. Tùy hệ quản trị, việc đó có thể cần khóa phạm vi (range/next-key lock), predicate lock, khóa bảng hoặc một hàng điều phối chung.

Chỉ khóa các hàng hiện có sau khi chạy `SELECT` chưa chắc bảo vệ được phantom. Một transaction khác có thể chèn thêm hàng thỏa điều kiện nếu khoảng dữ liệu đó không được khóa hoặc cơ chế cô lập không ngăn việc chèn.

## 6. Chi phí của việc khai báo trước

### 6.1. Phải tính được tập đọc và ghi

Ứng dụng cần biết trước các nhánh xử lý, quan hệ dữ liệu và những thao tác có thể phát sinh. Với nghiệp vụ phụ thuộc kết quả truy vấn, việc xác định tập khóa có thể cần thêm bước phân tích hoặc thiết kế lại quy trình.

Nếu chỉ biết một tập khóa lớn hơn tập thực tế, có thể khai báo một tập bao phủ an toàn. Tuy nhiên, các hàng không thực sự được dùng vẫn bị khóa trong thời gian transaction chạy, làm giảm khả năng truy cập đồng thời của transaction khác.

### 6.2. Khóa sớm và giữ khóa lâu hơn mức cần thiết

Khi toàn bộ khóa được cấp, transaction có thể giữ một số khóa từ đầu dù chỉ sử dụng chúng ở bước cuối. Ví dụ, transaction khóa cả A, B và C ngay từ đầu nhưng đọc A, xử lý B rồi mới cập nhật C. Trong thời gian đó, transaction khác cần C có thể phải chờ dù transaction đầu chưa sử dụng C.

Nếu transaction thực thi lâu, giữ nhiều khóa có thể làm tăng thời gian chờ và giảm thông lượng. Vì vậy, transaction cần được thiết kế ngắn và chỉ khai báo đúng phạm vi dữ liệu thực sự cần bảo vệ.

### 6.3. Có thể phải khóa phạm vi lớn

Khi không biết chính xác các hàng sẽ xuất hiện, hệ thống có thể phải khóa một khoảng dữ liệu, bảng hoặc hàng điều phối để bảo vệ điều kiện nghiệp vụ. Cách này giúp tập khóa có thể xác định trước, nhưng nhiều transaction không liên quan cũng có thể bị chặn bởi cùng một khóa rộng.

Ví dụ, nếu mọi thao tác đăng ký lớp học đều khóa một hàng đại diện cho lớp, hai học viên đăng ký cùng lớp sẽ được xử lý lần lượt. Đây có thể là lựa chọn hợp lý nếu mỗi lớp có ít lượt đăng ký đồng thời; với một lớp có lưu lượng rất cao, hàng điều phối có thể trở thành điểm nghẽn.

### 6.4. Chờ lâu và nguy cơ starvation

Conservative 2PL ngăn deadlock do khóa nhưng không bảo đảm mọi transaction đều được phục vụ trong thời gian hữu hạn. Một transaction cần tập khóa lớn có thể liên tục bị trì hoãn bởi các transaction khác. Nếu bộ quản lý khóa không có chính sách công bằng, transaction có thể bị starvation.

Hàng đợi yêu cầu khóa, chính sách ưu tiên, timeout và giới hạn thời gian transaction vẫn cần được thiết kế. Deadlock-free không đồng nghĩa với wait-free hoặc starvation-free.

## 7. Khóa thừa và chiến lược xác định phạm vi

Khi khó biết chính xác tập dữ liệu, có một số cách thiết kế, mỗi cách có mức đánh đổi riêng:

- **Khai báo tập khóa chính xác:** hiệu quả khi danh sách khóa đã có từ đầu, nhưng đòi hỏi nghiệp vụ và luồng dữ liệu xác định rõ.
- **Khai báo tập bao phủ:** khóa mọi đối tượng có thể được truy cập ở các nhánh xử lý. Dễ bảo đảm an toàn hơn nhưng có thể khóa nhiều hơn cần thiết.
- **Khóa phạm vi hoặc predicate:** bảo vệ điều kiện truy vấn và ngăn phantom khi hệ quản trị hỗ trợ. Cần hiểu chính xác phạm vi mà khóa bao phủ.
- **Khóa một hàng điều phối:** các transaction cùng tác động lên một nhóm dữ liệu phải khóa hàng đại diện trước. Cách này đơn giản hóa tập khóa nhưng làm các thao tác trong cùng nhóm bị tuần tự hóa.
- **Tách bước khám phá và bước cập nhật:** có thể đọc trước danh sách ứng viên bằng snapshot, sau đó yêu cầu khóa và kiểm tra lại dữ liệu khi đã khóa. Việc kiểm tra lại phải bảo vệ cả predicate hoặc phạm vi có thể phát sinh phantom; chỉ kiểm tra các ID đã thấy trước đó không đủ nếu hàng mới có thể xuất hiện.

Không nên coi lần đọc khám phá không khóa là kết quả cuối cùng. Tập dữ liệu có thể thay đổi giữa lúc khám phá và lúc lấy khóa. Sau khi có khóa, ứng dụng phải xác nhận các điều kiện nghiệp vụ vẫn đúng. Nếu không thể khóa hoặc xác nhận an toàn phạm vi truy vấn, cần chọn một cơ chế khác như SERIALIZABLE, khóa điều phối phù hợp hoặc thiết kế cập nhật nguyên tử.

## 8. Khác nhau giữa Conservative, Strict và Rigorous 2PL

Các thuật ngữ này mô tả những khía cạnh khác nhau của vòng đời khóa:

| Giao thức | Đặc điểm chính | Mục tiêu nổi bật |
|---|---|---|
| Basic 2PL | Có pha lấy khóa và pha nhả khóa; sau khi nhả khóa đầu tiên không được lấy thêm khóa. | Bảo đảm conflict serializability. |
| Conservative 2PL | Lấy toàn bộ khóa cần thiết trước khi bắt đầu; nếu chưa đủ thì chờ mà không giữ khóa nào. | Tránh deadlock do chờ thêm khóa. |
| Strict 2PL | Giữ khóa X đến commit hoặc rollback; khóa S có thể được nhả sớm theo quy tắc 2PL. | Ngăn transaction khác đọc hoặc ghi dữ liệu do transaction chưa commit cập nhật, tránh cascading rollback. |
| Rigorous 2PL | Giữ cả khóa S và X đến commit hoặc rollback. | Giữ toàn bộ quyền đọc/ghi đến khi transaction kết thúc. |

Conservative 2PL nói về **thời điểm lấy khóa**. Strict và Rigorous 2PL nói về **thời điểm nhả khóa**. Có thể kết hợp hai ý tưởng: lấy toàn bộ khóa từ đầu để tránh deadlock và giữ khóa X đến commit để có lịch thực thi strict.

Nếu một giao thức Conservative 2PL nhả khóa X trước khi transaction commit, transaction khác có thể đọc giá trị mà transaction đầu đã ghi nhưng chưa commit. Nếu transaction đầu rollback, transaction đọc sau đó có thể phải rollback theo. Vì thế, khi cần tránh cascading rollback, nên kết hợp Conservative 2PL với Strict 2PL hoặc giữ toàn bộ khóa đến khi kết thúc theo Rigorous 2PL.

## 9. Áp dụng trong hệ quản trị cơ sở dữ liệu

Conservative 2PL là một giao thức kiểm soát đồng thời, không phải một isolation level mà ứng dụng có thể mặc định đặt bằng câu lệnh `SET TRANSACTION ISOLATION LEVEL`. Nhiều hệ quản trị cơ sở dữ liệu quan hệ dùng khóa, MVCC hoặc kết hợp các cơ chế này; không nên giả định chúng cung cấp một thao tác SQL chuẩn để yêu cầu cấp tất cả khóa theo kiểu all-or-none.

Ví dụ, thực hiện lần lượt hai câu `SELECT ... FOR UPDATE` có thể khóa hàng thứ nhất rồi chờ hàng thứ hai. Nếu transaction khác làm điều ngược lại, deadlock vẫn có thể xảy ra. Một truy vấn khóa nhiều hàng cũng không mặc nhiên bảo đảm hệ quản trị lấy toàn bộ khóa một cách nguyên tử trước khi trả kết quả; thứ tự và thời điểm lấy khóa phụ thuộc sản phẩm, kế hoạch thực thi và tài liệu của hệ quản trị.

Trong hệ thống thực tế, có thể cân nhắc các cách sau:

1. Dùng API hoặc lock manager có hỗ trợ yêu cầu khóa tổng hợp đúng nghĩa, nếu nền tảng cung cấp.
2. Khi tập khóa đã biết, yêu cầu khóa theo một thứ tự toàn cục thống nhất ở mọi transaction để tránh vòng chờ. Cách này có thể tránh deadlock nếu mọi đường truy cập tuân thủ thứ tự, nhưng không đồng nghĩa với việc cấp toàn bộ khóa nguyên tử.
3. Dùng một hàng điều phối hoặc khóa phạm vi phù hợp để gom các thao tác vào cùng một thứ tự xử lý.
4. Nếu dùng cơ chế khóa mặc định của hệ quản trị, triển khai phát hiện deadlock, timeout và retry toàn bộ transaction khi cần.

Không dựa vào giả định về thứ tự khóa chỉ từ thứ tự các ID trong mã nguồn hoặc `ORDER BY`. Hãy xác nhận tài liệu sản phẩm và kiểm thử bằng nhiều connection thực tế. Nếu ứng dụng cần bảo đảm không deadlock, tất cả đường ghi có liên quan phải tuân thủ cùng một quy tắc lấy khóa.

## 10. Khi nào nên chọn Conservative 2PL?

Giao thức này phù hợp hơn khi:

- Tập hàng hoặc tài nguyên cần truy cập đã biết trước, có giới hạn và tương đối nhỏ.
- Mỗi transaction cần nhiều khóa và việc deadlock gây chi phí xử lý đáng kể.
- Nghiệp vụ có thể khai báo trước chế độ S/X cho từng đối tượng.
- Có thể lấy khóa tổng hợp theo cơ chế đáng tin cậy và giữ transaction ngắn.
- Mức cạnh tranh cho phép khóa toàn bộ tập dữ liệu ngay từ đầu mà không làm nghẽn hệ thống.

Nó kém phù hợp hơn khi:

- Tập dữ liệu chỉ xác định được sau nhiều lần đọc hoặc phụ thuộc vào nhánh xử lý động.
- Transaction truy cập số lượng hàng lớn hoặc phạm vi dữ liệu thay đổi liên tục.
- Khóa phạm vi rộng làm nhiều thao tác không liên quan phải chờ nhau.
- Transaction kéo dài, gọi dịch vụ bên ngoài hoặc chờ người dùng trong khi đang giữ khóa.
- Hệ quản trị không hỗ trợ cách cấp tập khóa phù hợp và ứng dụng không thể duy trì thứ tự khóa toàn cục.

Trong các trường hợp này, Basic/Strict 2PL kết hợp deadlock detection và retry, optimistic locking, cập nhật nguyên tử hoặc SERIALIZABLE có thể phù hợp hơn. Lựa chọn phụ thuộc vào invariant cần bảo vệ, cấu trúc dữ liệu và hành vi thực tế của hệ quản trị.

## 11. Quy trình thiết kế và kiểm chứng

Khi cân nhắc Conservative 2PL cho một nghiệp vụ, hãy thực hiện lần lượt:

1. Xác định invariant và toàn bộ dữ liệu mà transaction có thể đọc hoặc ghi.
2. Xác định chế độ khóa cuối cùng cho từng đối tượng; nếu một hàng có thể được cập nhật, khai báo X từ đầu.
3. Xác định predicate hoặc phạm vi cần bảo vệ để ngăn hàng mới xuất hiện làm thay đổi kết quả nghiệp vụ.
4. Kiểm tra nền tảng có hỗ trợ cấp toàn bộ tập khóa trước khi thực thi hay không. Nếu lấy từng khóa, xác định quy tắc thứ tự toàn cục và bảo đảm mọi đường truy cập đều tuân thủ.
5. Quyết định thời điểm nhả khóa: Strict 2PL nếu cần giữ khóa X đến kết thúc; Rigorous 2PL nếu cần giữ cả S và X.
6. Đặt timeout, chính sách công bằng và giới hạn thời gian transaction để xử lý chờ lâu và starvation.
7. Kiểm thử nhiều transaction chồng lấp, bao gồm trường hợp yêu cầu khóa giao nhau, thứ tự tài khoản ngược nhau, predicate có hàng mới được chèn và rollback.
8. Đo thời gian chờ, số lượng khóa, tỷ lệ transaction bị trì hoãn, thông lượng và độ trễ dưới tải đại diện.

Một kiểm thử quan trọng là cho hai transaction yêu cầu các tập khóa giao nhau. Xác nhận rằng transaction không được cấp đủ khóa chưa giữ bất kỳ khóa nào, và transaction đã được cấp đủ có thể hoàn tất mà không chờ thêm khóa thuộc tập đó. Đồng thời kiểm tra các đường ghi khác có tuân thủ cùng giao thức hay không.

## 12. Checklist trước khi dùng Conservative 2PL

- [ ] Đã biết trước toàn bộ hàng, phạm vi hoặc tài nguyên mà transaction có thể truy cập.
- [ ] Đã khai báo đúng chế độ S/X cho từng đối tượng; không cần nâng cấp khóa bất ngờ sau khi bắt đầu.
- [ ] Đã bảo vệ predicate/range cần thiết để tránh phantom.
- [ ] Bộ quản lý khóa cấp toàn bộ tập khóa hoặc không cấp khóa nào trong lúc transaction chờ.
- [ ] Mọi transaction liên quan đều tuân thủ cùng giao thức hoặc cùng thứ tự khóa.
- [ ] Đã quyết định dùng Strict hay Rigorous locking nếu cần tránh cascading rollback.
- [ ] Transaction đủ ngắn và tập khóa không rộng hơn mức cần thiết.
- [ ] Có chính sách timeout, công bằng và xử lý starvation.
- [ ] Đã kiểm thử nhiều connection và đo ảnh hưởng đến thông lượng, độ trễ.

Conservative 2PL đổi việc phải xử lý deadlock lấy yêu cầu phải biết trước tập khóa. Khi dữ liệu truy cập đã rõ ràng và có thể khóa toàn bộ trước khi thực thi, đây là cách đơn giản để loại bỏ vòng chờ do lấy khóa từng phần. Khi tập dữ liệu thay đổi theo kết quả truy vấn hoặc nghiệp vụ, chi phí xác định và giữ tập khóa có thể lớn hơn lợi ích. Quyết định nên dựa trên khả năng khai báo tập khóa chính xác, phạm vi khóa cần thiết và mức cạnh tranh của workload.
