# Các giai đoạn đọc, kiểm định và ghi trong kiểm soát đồng thời lạc quan

**Kiểm soát đồng thời lạc quan (Optimistic Concurrency Control — OCC)** là cách điều phối giao dịch dựa trên giả định rằng xung đột giữa các giao dịch không xảy ra thường xuyên. Thay vì khóa dữ liệu ngay từ đầu và buộc giao dịch khác chờ, OCC cho phép giao dịch đọc và tính toán trên dữ liệu hiện có, ghi các thay đổi vào vùng làm việc riêng, rồi kiểm tra xung đột trước khi công bố kết quả.

Một giao dịch OCC thường đi qua ba giai đoạn: **đọc (read phase), kiểm định (validation phase) và ghi (write phase)**. Giai đoạn đọc thu thập dữ liệu cùng các tập đọc/ghi; giai đoạn kiểm định quyết định giao dịch có thể commit mà vẫn bảo toàn tính tuần tự hóa hay không; giai đoạn ghi áp dụng các thay đổi đã được chấp nhận vào cơ sở dữ liệu dùng chung.

## 1. Vì sao gọi là kiểm soát đồng thời lạc quan?

Trong kiểm soát đồng thời bi quan (pessimistic concurrency control), hệ quản trị thường giả định xung đột có thể xảy ra nên đặt khóa trước khi truy cập hoặc sửa dữ liệu. Nếu một giao dịch khác cần khóa không tương thích, nó phải chờ hoặc bị hủy theo chính sách của hệ quản trị.

OCC chọn cách tiếp cận khác. Giao dịch được phép thực hiện phần lớn công việc mà không giữ khóa ghi dài hạn trên các dữ liệu mà nó đọc. Hệ quản trị ghi nhận những dữ liệu giao dịch đã đọc và dự định ghi. Trước khi commit, hệ thống kiểm tra xem các giao dịch chạy đồng thời có làm cho kết quả của giao dịch hiện tại không còn hợp lệ hoặc không thể sắp xếp thành một thứ tự tuần tự hợp lệ hay không.

Nếu kiểm định thành công, thay đổi được công bố. Nếu kiểm định thất bại, giao dịch bị hủy (abort) và thường phải chạy lại từ đầu với dữ liệu mới nhất.

```text
Giao dịch bắt đầu
       |
       v
  READ PHASE
  Đọc dữ liệu, tính toán, lưu thay đổi riêng
       |
       v
  VALIDATION PHASE
  Kiểm tra xung đột và khả năng tuần tự hóa
       |
       +---- Không hợp lệ ----> ABORT / RETRY
       |
       v
  WRITE PHASE
  Công bố thay đổi đã kiểm định
       |
       v
     COMMIT
```

Từ “lạc quan” mô tả giả định về tần suất xung đột, không phải cam kết rằng giao dịch sẽ luôn thành công. OCC phù hợp khi phần lớn giao dịch có thể hoàn tất mà không tranh chấp cùng dữ liệu; khi xung đột thường xuyên, chi phí hủy và chạy lại có thể lớn.

## 2. Các tập dữ liệu cần theo dõi

Để kiểm định, hệ quản trị hoặc tầng ứng dụng cần biết giao dịch đã đọc gì và dự định thay đổi gì. Hai tập cơ bản là:

- **Read set (RS):** tập đối tượng mà giao dịch đã đọc và kết quả của chúng có ảnh hưởng đến quyết định hoặc kết quả giao dịch.
- **Write set (WS):** tập đối tượng mà giao dịch dự định tạo mới, cập nhật hoặc xóa.

Ví dụ, giao dịch T1 đọc tồn kho của hai sản phẩm rồi cập nhật số lượng của sản phẩm A:

```text
RS(T1) = {Product A.stock, Product B.stock}
WS(T1) = {Product A.stock}
```

Trong một triển khai thực tế, tập đọc/ghi có thể được biểu diễn bằng khóa bản ghi, khóa trang, định danh phiên bản, khoảng chỉ mục, predicate hoặc metadata khác. Phạm vi theo dõi phải đủ để phát hiện những thay đổi có thể ảnh hưởng đến kết quả truy vấn. Nếu chỉ ghi nhận các dòng đã trả về mà bỏ qua điều kiện truy vấn, hệ thống có thể bỏ sót phantom do một dòng mới được chèn vào phạm vi.

Giao dịch cũng thường có **vùng làm việc riêng (private workspace)** để lưu các giá trị mới. Trong giai đoạn đọc, một thao tác ghi chỉ cập nhật vùng riêng này; những giao dịch khác chưa nhìn thấy giá trị chưa commit. Khi đọc lại dữ liệu mà chính giao dịch đã sửa, giao dịch phải nhận được giá trị trong vùng riêng của mình theo quy tắc read-your-own-writes.

## 3. Giai đoạn đọc (Read Phase)

Trong giai đoạn đọc, giao dịch lấy dữ liệu cần thiết, thực hiện tính toán và chuẩn bị các thay đổi trong vùng làm việc riêng. Hệ thống ghi nhận read set và write set để dùng ở giai đoạn kiểm định.

Một trình tự khái niệm:

1. Bắt đầu giao dịch và ghi nhận thời điểm hoặc phiên bản bắt đầu.
2. Khi ứng dụng đọc một đối tượng, hệ thống lấy giá trị từ trạng thái dữ liệu được phép quan sát và thêm đối tượng vào `RS`.
3. Khi ứng dụng yêu cầu cập nhật hoặc xóa, hệ thống ghi giá trị dự kiến vào vùng làm việc riêng và thêm đối tượng vào `WS`.
4. Nếu giao dịch đọc lại đối tượng đã sửa, hệ thống trả về giá trị trong vùng làm việc riêng.
5. Khi phần xử lý nghiệp vụ hoàn tất, giao dịch chuyển sang kiểm định.

Ví dụ một giao dịch chuyển 100 đơn vị từ tài khoản A sang tài khoản B:

```sql
-- Pseudocode: các thay đổi vẫn nằm trong workspace của T1
BEGIN TRANSACTION;

balance_a = READ(account_A.balance);
balance_b = READ(account_B.balance);

IF balance_a >= 100 THEN
    WRITE(account_A.balance, balance_a - 100);
    WRITE(account_B.balance, balance_b + 100);
ELSE
    ABORT;
END IF;

-- Chưa công bố hai giá trị này vào database dùng chung.
VALIDATE_AND_COMMIT();
```

Sau phần đọc và tính toán, có thể mô tả trạng thái của T1 như sau:

```text
RS(T1) = {account_A.balance, account_B.balance}
WS(T1) = {account_A.balance, account_B.balance}

Workspace(T1):
  account_A.balance = balance_a - 100
  account_B.balance = balance_b + 100
```

Việc giữ thay đổi trong workspace giúp các giao dịch khác không quan sát một nửa kết quả chuyển tiền. Hai số dư chỉ được công bố sau khi kiểm định thành công và giai đoạn ghi hoàn tất theo cơ chế commit nguyên tử.

### 3.1. Read set phải phản ánh dữ liệu ảnh hưởng đến quyết định

Giả sử một giao dịch đặt hàng chỉ đọc `stock` của sản phẩm A và quyết định số lượng mua dựa trên giá trị đó. Nếu một giao dịch khác cập nhật `stock` trước khi T1 commit, T1 có thể đang dùng một quyết định dựa trên dữ liệu cũ. Vì vậy `Product A.stock` phải nằm trong read set.

Không phải mọi lần đọc nội bộ đều nhất thiết cần được giữ trong một tập riêng biệt đến cuối giao dịch. Một triển khai có thể tối ưu bằng version timestamp, predicate tracking hoặc cơ chế khác. Nhưng về mặt logic, hệ thống phải bảo vệ mọi dữ liệu mà kết quả giao dịch phụ thuộc vào.

### 3.2. Ghi riêng không có nghĩa là không có xung đột

Hai giao dịch có thể cùng đọc một giá trị rồi chuẩn bị các thay đổi khác nhau trong workspace. Việc chưa ghi ra database chỉ trì hoãn thời điểm xung đột được giải quyết. Khi kiểm định, hệ thống vẫn phải phát hiện nếu một giao dịch đã thay đổi dữ liệu mà giao dịch còn lại dựa vào.

## 4. Giai đoạn kiểm định (Validation Phase)

Kiểm định là bước quyết định giao dịch có được phép công bố thay đổi hay phải hủy. Hệ thống xem xét các giao dịch chạy đồng thời và kiểm tra xem những thay đổi của chúng có làm dữ liệu mà giao dịch hiện tại đã đọc trở nên lỗi thời hay tạo ra một lịch thực thi không thể tuần tự hóa hay không.

Mục tiêu là bảo đảm kết quả commit tương đương với một thứ tự thực thi tuần tự hợp lệ (serializable schedule), theo giao thức OCC đang được sử dụng. Chỉ kiểm tra hai giao dịch có ghi cùng một dòng hay không thường chưa đủ: một giao dịch có thể đọc dòng A rồi ghi dòng B, trong khi giao dịch khác đọc B rồi ghi A. Hai tập ghi không giao nhau nhưng phụ thuộc đọc-ghi có thể tạo thành chu trình.

### 4.1. Kiểm tra read set với các thay đổi đã commit

Một cách kiểm định phổ biến là đối chiếu read set của giao dịch hiện tại với write set của các giao dịch đã commit trong khoảng thời gian giao dịch hiện tại đang đọc.

Nếu giao dịch khác đã ghi một đối tượng thuộc read set của T1 sau khi T1 đọc hoặc trong thời gian T1 đang thực hiện read phase, T1 có thể đã tính toán trên giá trị cũ. Khi đó, hệ thống cần hủy T1 hoặc chứng minh được thứ tự tuần tự phù hợp bằng một quy tắc kiểm định chi tiết hơn.

Ví dụ:

```text
Ban đầu: Product A.stock = 10

T1: READ stock = 10
    tính rằng có thể bán 6 sản phẩm

T2: READ stock = 10
    WRITE stock = 3
    VALIDATE -> PASS
    COMMIT

T1: WRITE stock = 4 (trong workspace)
    VALIDATE -> phát hiện T2 đã ghi Product A.stock
    ABORT T1
```

T1 không được phép ghi đè kết quả của T2 dựa trên số tồn kho cũ. Nếu T1 chạy lại, nó đọc `stock = 3` và có thể từ chối yêu cầu bán 6 sản phẩm.

### 4.2. Xung đột đọc-ghi và ghi-ghi

Khi đánh giá các giao dịch đồng thời, cần phân biệt các quan hệ:

| Quan hệ | Ý nghĩa | Vấn đề có thể phát sinh |
|---|---|---|
| Read-Write (RW) | T1 đọc đối tượng mà T2 ghi | T1 có thể đã dùng giá trị cũ để tính toán |
| Write-Read (WR) | T1 ghi đối tượng mà T2 đọc | T2 có thể cần nhìn thấy thay đổi của T1 theo thứ tự tuần tự được chọn |
| Write-Write (WW) | Hai giao dịch ghi cùng đối tượng | Có thể ghi đè, mất cập nhật hoặc không có thứ tự commit hợp lệ nếu không được điều phối |

Tên hướng phụ thuộc có thể được diễn đạt theo thứ tự giao dịch trong đồ thị tuần tự hóa; điều quan trọng là hệ thống phải xét cả read set lẫn write set và thứ tự xảy ra của các pha. Một bộ kiểm định có thể dùng quy tắc bảo thủ để hủy giao dịch khi phát hiện giao nhau, hoặc dùng timestamp/version và thông tin thứ tự để chứng minh một thứ tự tuần tự hợp lệ.

### 4.3. Kiểm định theo giao dịch đã commit và giao dịch đang hoạt động

Các giao thức OCC khác nhau ở cách so sánh giao dịch hiện tại với những giao dịch khác. Một số triển khai kiểm tra giao dịch đã commit kể từ khi T1 bắt đầu; một số triển khai kiểm tra cả giao dịch đang hoạt động và có thể buộc một giao dịch chờ, hủy hoặc nhường quyền kiểm định.

Hai hướng thường được nhắc đến:

- **Backward validation:** giao dịch sắp commit kiểm tra các giao dịch đã hoàn tất trong thời gian nó thực hiện phần đọc. Một câu hỏi trọng tâm là write set của giao dịch đã commit có giao với read set của giao dịch hiện tại hay không.
- **Forward validation:** giao dịch đang kiểm định kiểm tra các giao dịch còn hoạt động có thể xung đột với nó. Tùy chính sách, hệ thống có thể trì hoãn, hủy giao dịch hiện tại hoặc hủy một giao dịch đang chạy để duy trì thứ tự hợp lệ.

Đây là hai cách tổ chức kiểm định thường gặp, không phải một ma trận duy nhất bắt buộc cho mọi DBMS. Thuật toán cụ thể phải xét thời điểm bắt đầu, kết thúc read phase, thời điểm kiểm định, thời điểm ghi và cách cấp thứ tự tuần tự.

### 4.4. Vì sao cần điều phối chính giai đoạn kiểm định?

Nếu hai giao dịch đồng thời kiểm định trên cùng trạng thái cũ mà không có cơ chế phối hợp, cả hai có thể cùng kết luận rằng mình hợp lệ rồi cùng công bố các thay đổi xung đột. Vì vậy, giai đoạn kiểm định và chuyển sang ghi phải được điều phối bằng một cơ chế nguyên tử hoặc thứ tự hóa phù hợp.

Hệ thống có thể dùng khóa ngắn hạn trong vùng kiểm định/ghi, cấp timestamp tuần tự, compare-and-swap trên version hoặc cơ chế commit coordinator. OCC giảm thời gian khóa trong phần xử lý nghiệp vụ, nhưng không có nghĩa toàn bộ giao thức không bao giờ dùng khóa hay đồng bộ.

## 5. Giai đoạn ghi (Write Phase)

Khi kiểm định thành công, hệ thống áp dụng các thay đổi đang nằm trong workspace vào trạng thái dữ liệu dùng chung. Các thay đổi phải được công bố như một giao dịch nguyên tử: giao dịch khác không được quan sát một phần kết quả trong khi phần còn lại chưa được ghi.

Một trình tự khái niệm:

1. Xác nhận giao dịch đã vượt qua kiểm định và giữ quyền commit theo thứ tự đã chọn.
2. Áp dụng các giá trị trong write set vào database hoặc tạo các phiên bản mới.
3. Ghi nhận commit record/timestamp cần thiết để phục hồi và xác định thứ tự giao dịch.
4. Công bố trạng thái commit để giao dịch khác có thể nhìn thấy các thay đổi theo quy tắc cô lập.
5. Giải phóng metadata, vùng làm việc và tài nguyên điều phối không còn cần thiết.

Với ví dụ chuyển tiền, giai đoạn ghi phải công bố cả hai thay đổi:

```text
account_A.balance: 500 -> 400
account_B.balance: 200 -> 300
```

Nếu hệ thống chỉ công bố số dư A đã giảm nhưng số dư B chưa tăng, giao dịch khác có thể quan sát trạng thái sai. Cơ chế commit và phục hồi phải bảo đảm hai thay đổi cùng thành công hoặc cùng không có hiệu lực sau rollback/recovery.

Nếu kiểm định thất bại, giai đoạn ghi không được công bố write set của giao dịch. Hệ thống loại bỏ workspace, giải phóng tài nguyên và trả lỗi xung đột hoặc yêu cầu thử lại.

## 6. Ví dụ đầy đủ qua ba giai đoạn

Giả sử kho hàng có `stock = 10`. T1 muốn bán 6 sản phẩm, T2 muốn bán 7 sản phẩm. Cả hai giao dịch đều cần bảo đảm không bán vượt số lượng tồn.

### Bước 1: Hai giao dịch đọc

```text
T1 READ PHASE:
  đọc stock = 10
  RS(T1) = {stock}
  WS(T1) = {stock}
  workspace: stock = 4

T2 READ PHASE:
  đọc stock = 10
  RS(T2) = {stock}
  WS(T2) = {stock}
  workspace: stock = 3
```

Hai giao dịch chưa công bố thay đổi, nên trạng thái dùng chung vẫn là 10. Cả hai cùng tính toán dựa trên một giá trị ban đầu.

### Bước 2: T1 kiểm định và ghi

T1 đến giai đoạn kiểm định trước. Nếu không có giao dịch khác đã commit thay đổi `stock` kể từ khi T1 đọc, T1 vượt qua kiểm định. Hệ thống ghi `stock = 4` và commit T1.

### Bước 3: T2 kiểm định

T2 kiểm định sau khi T1 đã commit. T2 thấy `WS(T1)` giao với `RS(T2)` tại đối tượng `stock`. Dữ liệu T2 dùng để tính toán đã lỗi thời, nên T2 không được ghi `stock = 3`.

```text
T1: READ(10) -> VALIDATE PASS -> WRITE(4) -> COMMIT
T2: READ(10) -> VALIDATE FAIL -> ABORT
                                      |
                                      v
                                  RETRY T2
                                      |
                                      v
                            READ(4), yêu cầu 7 không hợp lệ
```

Khi chạy lại, T2 đọc tồn kho bằng 4 và từ chối yêu cầu bán 7 sản phẩm. OCC đã ngăn hai giao dịch cùng sử dụng giá trị 10 để ghi đè lẫn nhau.

## 7. Kiểm định để bảo vệ tính tuần tự hóa

Một mục tiêu quan trọng của OCC là bảo đảm lịch thực thi tương đương với một thứ tự tuần tự. Chỉ kiểm tra hai giao dịch có cùng write set hay không sẽ bỏ sót một số phụ thuộc đọc-ghi.

Ví dụ, hệ thống trực ca có hai bác sĩ An và Bình. Quy tắc nghiệp vụ yêu cầu luôn có ít nhất một người trực:

| Bác sĩ | Trạng thái ban đầu |
|---|---|
| An | Đang trực |
| Bình | Đang trực |

T1 đọc trạng thái của cả hai, sau đó tắt ca trực của An. T2 cũng đọc trạng thái của cả hai, sau đó tắt ca trực của Bình.

```text
T1: READ {An, Binh} -> WRITE {An = off}
T2: READ {An, Binh} -> WRITE {Binh = off}
```

Hai write set không giao nhau, nhưng:

- `WS(T1)` giao với `RS(T2)` tại An.
- `WS(T2)` giao với `RS(T1)` tại Bình.

Nếu cả hai cùng commit mà không xét các phụ thuộc này, kết quả không còn bác sĩ nào trực. Một bộ kiểm định OCC có khả năng bảo vệ serializability phải nhận ra rằng không thể tùy tiện chấp nhận cả hai giao dịch theo thứ tự tuần tự hợp lệ. Hệ thống cần hủy ít nhất một giao dịch hoặc áp dụng cơ chế bảo vệ ràng buộc tương đương.

Ví dụ này cho thấy read set quan trọng ngang với write set. Giao dịch có thể ghi hai đối tượng khác nhau nhưng vẫn phụ thuộc vào dữ liệu mà giao dịch kia đã thay đổi.

## 8. Dữ liệu phạm vi và phantom trong OCC

Theo dõi từng dòng đã đọc có thể chưa đủ nếu giao dịch dựa trên một điều kiện truy vấn. Giả sử T1 đọc:

```sql
SELECT *
FROM reservation
WHERE room_id = 10
  AND start_time < :end_time
  AND end_time > :start_time;
```

T1 kết luận phòng 10 còn trống trong khoảng thời gian yêu cầu. Trong lúc đó, T2 chèn một lượt đặt phòng mới thỏa điều kiện. Nếu read set của T1 chỉ chứa những dòng đã tìm thấy, nó có thể rỗng và không phát hiện dòng mới.

Để kiểm định đúng, hệ thống cần ghi nhận cả predicate hoặc khoảng dữ liệu mà truy vấn đã kiểm tra, hoặc dùng cơ chế tương đương như range validation, index-range version hay predicate lock. Khi kiểm định, hệ thống phải xem có giao dịch nào chèn hoặc sửa dữ liệu khiến predicate đó thay đổi hay không.

Mức chi tiết của read set là một quyết định quan trọng:

- Theo dõi từng dòng giúp giảm abort giả nhưng tốn metadata và chi phí.
- Theo dõi theo trang, bảng hoặc khoảng chỉ mục giảm metadata nhưng có thể làm nhiều giao dịch không thực sự xung đột phải hủy.
- Theo dõi predicate giúp bảo vệ truy vấn điều kiện, nhưng cần cơ chế xác định phạm vi và thay đổi liên quan.

## 9. OCC xử lý hủy và chạy lại như thế nào?

Khi validation thất bại, hệ thống không thể chỉ ghi đè giá trị mới nhất vào workspace cũ. Các phép tính và quyết định nghiệp vụ của giao dịch có thể đã dựa trên dữ liệu lỗi thời. Vì vậy, cách xử lý an toàn thường là hủy toàn bộ giao dịch và chạy lại từ đầu.

Một lần retry cần:

1. Bỏ workspace và các kết quả tính toán chưa commit của lần chạy cũ.
2. Bắt đầu một giao dịch mới với snapshot hoặc version mới.
3. Đọc lại dữ liệu và tạo read set/write set mới.
4. Tính toán lại các quyết định nghiệp vụ.
5. Kiểm định lại trước khi ghi.

Không phải mọi lỗi đều nên retry tự động. Nếu thất bại do vi phạm quy tắc nghiệp vụ, dữ liệu đầu vào không hợp lệ hoặc điều kiện không còn đúng, ứng dụng cần trả kết quả phù hợp thay vì lặp vô hạn. Với xung đột tạm thời, retry có giới hạn và backoff có thể giúp giảm việc nhiều giao dịch liên tục va chạm lại cùng lúc.

Ứng dụng cũng phải chú ý đến tác dụng phụ bên ngoài database. Gửi email, trừ tiền qua dịch vụ bên ngoài hoặc phát sự kiện trước khi giao dịch commit có thể khiến retry thực hiện tác dụng phụ nhiều lần. Nên trì hoãn tác dụng phụ đến sau commit hoặc dùng transactional outbox/idempotency key để phối hợp an toàn.

## 10. Ưu điểm, chi phí và tình huống phù hợp

| Khía cạnh | Lợi ích của OCC | Chi phí hoặc giới hạn |
|---|---|---|
| Đọc dữ liệu | Có thể đọc mà không giữ khóa ghi dài hạn | Vẫn cần theo dõi phiên bản và tập đọc |
| Giao dịch ít xung đột | Ít phải chờ khóa trong phần xử lý chính | Tốn chi phí kiểm định trước commit |
| Giao dịch xung đột nhiều | Có thể phát hiện và hủy thay vì giữ khóa lâu | Tỷ lệ abort/retry tăng, công việc bị lặp lại |
| Giao dịch dài | Có thể thực hiện tính toán trong workspace | Cửa sổ xung đột dài khiến xác suất kiểm định thất bại tăng |
| Ghi dữ liệu | Chỉ công bố sau khi được chấp nhận | Giai đoạn kiểm định/ghi có thể trở thành điểm nghẽn |
| Truy vấn theo điều kiện | Có thể kiểm định theo predicate/range | Theo dõi phạm vi phức tạp và tốn tài nguyên |

OCC thường phù hợp với workload đọc nhiều, cập nhật ít, xung đột thấp và giao dịch tương đối ngắn. Ví dụ có thể là thao tác cập nhật hồ sơ ít tranh chấp hoặc dịch vụ có nhiều lượt đọc độc lập.

Nếu nhiều giao dịch liên tục cập nhật cùng một hàng tồn kho, số dư nóng hoặc bộ đếm chung, OCC có thể hủy rất nhiều giao dịch. Trong trường hợp đó, khóa bi quan, hàng đợi tuần tự, phân vùng dữ liệu hoặc một cơ chế điều phối chuyên biệt có thể hiệu quả hơn.

Không có một ngưỡng chung để kết luận khi nào nên dùng OCC. Cần đo tỷ lệ xung đột, tỷ lệ retry, thời gian kiểm định, thời gian commit, kích thước read/write set và độ trễ ở tải thực tế.

## 11. OCC khác MVCC và khóa bi quan như thế nào?

OCC, MVCC và khóa bi quan giải quyết những khía cạnh liên quan nhưng không phải các tên gọi thay thế cho nhau.

| Cơ chế | Vai trò chính | Cách xử lý xung đột |
|---|---|---|
| Khóa bi quan | Ngăn xung đột bằng cách đặt khóa khi truy cập | Giao dịch xung đột thường phải chờ hoặc bị hủy |
| MVCC | Giữ nhiều phiên bản để giao dịch đọc trạng thái phù hợp | Đọc có thể dùng phiên bản cũ; ghi vẫn cần xử lý xung đột |
| OCC | Cho phép xử lý trước rồi kiểm định trước commit | Giao dịch không hợp lệ bị abort/retry |

Một hệ thống có thể kết hợp MVCC với kiểm định lạc quan: giai đoạn đọc lấy phiên bản theo snapshot, còn giai đoạn kiểm định đối chiếu version hoặc tập đọc/ghi trước khi công bố. Một hệ thống khác có thể dùng khóa ngắn trong validation/write phase. Vì vậy, nhìn thấy MVCC không đủ để kết luận DBMS đang dùng OCC thuần túy; cần xem giao thức commit cụ thể.

## 12. Những sai lầm thường gặp

**Giao dịch chưa ghi ra database thì không thể xung đột.** Không đúng. Hai giao dịch có thể cùng đọc dữ liệu cũ và chuẩn bị thay đổi xung đột trong workspace. Validation phase được dùng để phát hiện điều đó.

**Chỉ cần so sánh write set là đủ.** Không đúng trong trường hợp cần bảo đảm serializability. Giao dịch có thể ghi các dòng khác nhau nhưng đọc dữ liệu mà giao dịch kia thay đổi, tạo thành chu trình phụ thuộc hoặc write skew.

**Validation thành công nghĩa là write phase không thể thất bại.** Validation chỉ chứng minh giao dịch hợp lệ theo giao thức và trạng thái được kiểm tra. Hệ thống vẫn phải xử lý lỗi ghi, lỗi lưu trữ, mất kết nối và phục hồi theo cơ chế transaction.

**OCC không bao giờ dùng khóa.** Không đúng. Hệ thống vẫn cần điều phối kiểm định, công bố ghi, metadata hoặc các tài nguyên dùng chung. Điểm khác biệt là tránh giữ khóa bảo vệ toàn bộ phần xử lý đọc/tính toán trong nhiều trường hợp.

**Abort có thể tiếp tục từ câu lệnh cuối cùng.** Thường không an toàn. Nếu dữ liệu đầu vào đã thay đổi, các quyết định trước đó có thể không còn hợp lệ. Giao dịch thường cần chạy lại từ đầu với read set mới.

**OCC luôn nhanh hơn khóa bi quan.** Không đúng. Khi xung đột cao, chi phí kiểm định và retry có thể lớn hơn chi phí chờ khóa. Hiệu quả phụ thuộc workload, kích thước giao dịch và cách triển khai.

## 13. Cách quan sát và đánh giá một triển khai OCC

Khi phân tích một hệ thống dùng OCC, hãy xác định các câu hỏi sau:

1. Read phase lấy dữ liệu từ snapshot, phiên bản hiện tại hay một nguồn khác?
2. Read set ghi nhận từng dòng, từng cột, phạm vi chỉ mục hay predicate?
3. Write set được giữ ở workspace nào và khi nào được công bố?
4. Validation phase so sánh với giao dịch đã commit, giao dịch đang hoạt động hay cả hai?
5. Thuật toán validation bảo đảm thứ tự tuần tự bằng quy tắc nào?
6. Giai đoạn kiểm định và ghi được điều phối ra sao để hai giao dịch không cùng vượt qua trên một trạng thái lỗi thời?
7. Khi validation thất bại, hệ thống abort giao dịch nào và ứng dụng retry như thế nào?
8. Có metric về validation failure, retry count, conflict rate và thời gian commit hay không?
9. Truy vấn theo predicate có được bảo vệ khỏi phantom không?
10. Tác dụng phụ ngoài database được trì hoãn hoặc làm idempotent ra sao?

Một log hữu ích có thể ghi nhận transaction ID, thời điểm bắt đầu, thời điểm vào validation, read/write set hoặc fingerprint của chúng, version bị xung đột, lý do abort và số lần retry. Không nên ghi dữ liệu nhạy cảm trực tiếp vào log; định danh và fingerprint thường đủ để chẩn đoán quan hệ xung đột.

## 14. Luồng xử lý tổng hợp

```text
BEGIN
  |
  v
READ PHASE
  - đọc dữ liệu cần thiết
  - ghi nhận RS
  - tính toán trong private workspace
  - ghi nhận WS
  |
  v
VALIDATION PHASE
  - xác định các giao dịch có quan hệ đồng thời
  - kiểm tra read/write dependencies
  - bảo đảm thứ tự tuần tự hợp lệ
  |
  +---- FAIL ----> ABORT -> bỏ workspace -> RETRY hoặc trả lỗi
  |
  v PASS
WRITE PHASE
  - công bố write set một cách nguyên tử
  - ghi nhận commit order/version
  |
  v
COMMIT
```

Ba giai đoạn tạo thành một giao thức thống nhất. Read phase thu thập bằng chứng về dữ liệu mà giao dịch phụ thuộc; validation phase dùng bằng chứng đó để quyết định có thể commit an toàn hay không; write phase chỉ công bố các thay đổi đã được chấp nhận. Khi hiểu rõ vai trò của từng giai đoạn, có thể phân tích vì sao một giao dịch bị abort, tại sao OCC hiệu quả ở workload ít xung đột và vì sao hệ thống vẫn cần xử lý cẩn thận các phụ thuộc đọc-ghi, phantom, retry và tính nguyên tử khi ghi.
