# Bóng ma (phantom read): tập hàng thỏa điều kiện thay đổi

Khi một giao dịch truy vấn dữ liệu theo điều kiện, kết quả của truy vấn là một tập hàng thỏa điều kiện đó. Nếu giao dịch chạy lại cùng truy vấn trong khi vẫn đang mở và nhận được một tập hàng khác vì giao dịch khác đã commit thay đổi, hiện tượng đó có thể là **đọc ma** (*phantom read*).

Ví dụ, giao dịch `T1` truy vấn các đơn hàng đang chờ xử lý có giá trị từ 100 trở lên và nhận được ba hàng. Trong lúc `T1` chưa kết thúc, giao dịch `T2` thêm một đơn hàng thỏa điều kiện rồi commit. Khi `T1` chạy lại truy vấn, nó nhận được bốn hàng. Hàng mới xuất hiện trong kết quả giống như một “bóng ma”, nên hiện tượng này được gọi là phantom read.

Đọc ma là một bất thường đồng thời liên quan đến **tập hàng thỏa một điều kiện truy vấn**. Nó khác với việc một hàng đã đọc bị thay đổi giá trị, và cũng khác với việc đọc một thay đổi chưa commit.

## 1. Đọc ma xảy ra như thế nào?

Một giao dịch có thể thực hiện nhiều câu truy vấn trong cùng một đơn vị công việc. Giả sử bảng `orders` chứa các đơn hàng và giao dịch cần đếm những đơn hàng đang chờ xử lý có giá trị ít nhất 100.

Trình tự sau minh họa một lần đọc ma:

| Thời điểm | Giao dịch T1 | Giao dịch T2 | Kết quả của truy vấn ở T1 |
|---|---|---|---|
| 1 | Bắt đầu giao dịch | | |
| 2 | Truy vấn các đơn hàng `PENDING` có `amount >= 100` | | Nhận các hàng 1001, 1003, 1005 |
| 3 | Vẫn đang mở | Bắt đầu giao dịch | |
| 4 | Chưa truy vấn lại | Thêm đơn hàng 1008 với trạng thái `PENDING`, số tiền 150 | |
| 5 | Chưa truy vấn lại | `COMMIT` | Hàng 1008 trở thành dữ liệu đã xác nhận |
| 6 | Chạy lại đúng truy vấn ở thời điểm 2 | Đã kết thúc | Nhận các hàng 1001, 1003, 1005, 1008 |

Hai lần truy vấn dùng cùng điều kiện nhưng trả về hai tập hàng khác nhau. Hàng 1008 là phantom đối với lần đọc thứ hai của `T1`.

Đọc ma không chỉ xuất hiện khi một giao dịch `INSERT` hàng mới. Một hàng vốn không thỏa điều kiện có thể được giao dịch khác cập nhật để bắt đầu thỏa điều kiện. Ngược lại, một hàng có thể biến mất khỏi kết quả vì bị xóa hoặc được cập nhật để không còn thỏa điều kiện. Điểm chung là tập hàng khớp với điều kiện truy vấn đã thay đổi giữa các lần đọc.

## 2. Minh họa bằng SQL với hai phiên làm việc

Giả sử bảng `orders` đã tồn tại và có một số hàng phù hợp để truy vấn. Ta dùng điều kiện trạng thái và giá trị đơn hàng để dễ quan sát tập kết quả.

**Phiên A — giao dịch đọc:**

```sql
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
BEGIN;

-- Lần đọc thứ nhất
SELECT order_id, amount
FROM orders
WHERE status = 'PENDING'
  AND amount >= 100
ORDER BY order_id;

-- Tạm dừng để phiên B thực hiện INSERT và COMMIT.

-- Lần đọc thứ hai: cùng câu truy vấn và cùng điều kiện
SELECT order_id, amount
FROM orders
WHERE status = 'PENDING'
  AND amount >= 100
ORDER BY order_id;

COMMIT;
```

**Phiên B — giao dịch ghi:**

```sql
BEGIN;

INSERT INTO orders (order_id, amount, status)
VALUES (1008, 150, 'PENDING');

COMMIT;
```

Thực hiện lần đọc thứ nhất ở phiên A, sau đó chạy toàn bộ giao dịch ở phiên B. Khi phiên B đã commit, chạy lần đọc thứ hai ở phiên A. Với hành vi `READ COMMITTED` thông thường, câu truy vấn thứ hai có thể nhìn thấy đơn hàng 1008 vì mỗi câu lệnh đọc lấy dữ liệu đã commit tại thời điểm câu lệnh đó thực hiện.

Nếu hai lần đọc ở phiên A trả về cùng một tập hàng, ví dụ không có giao dịch nào khác làm thay đổi dữ liệu phù hợp, thì lịch chạy cụ thể đó không biểu hiện đọc ma. Chỉ riêng việc một giao dịch chạy cùng câu SQL hai lần chưa đủ để kết luận có phantom read; phải có thay đổi đồng thời đã commit làm thay đổi tập kết quả.

Lệnh `SET TRANSACTION ISOLATION LEVEL` và cú pháp bắt đầu giao dịch có thể khác nhau giữa các hệ quản trị. Hãy dùng cú pháp tương ứng với cơ sở dữ liệu đang thực hành.

## 3. Vì sao đọc ma có thể gây lỗi nghiệp vụ?

### 3.1. Kết quả đếm thay đổi giữa hai lần kiểm tra

Giả sử `T1` kiểm tra số đơn hàng đang chờ xử lý trước khi quyết định có mở thêm một đợt xử lý hay không. Lần đọc đầu tiên cho kết quả 3. Sau khi `T2` thêm và commit một đơn hàng phù hợp, lần đọc thứ hai cho kết quả 4. Nếu nghiệp vụ cần một tập dữ liệu ổn định trong suốt quá trình xử lý, thay đổi này có thể làm quyết định của `T1` không nhất quán.

### 3.2. Kiểm tra điều kiện rồi thực hiện hành động có thể bị sai lệch

Một quy trình có thể truy vấn các bản ghi thỏa điều kiện, tính tổng hoặc kiểm tra giới hạn, rồi thực hiện thao tác tiếp theo. Nếu một giao dịch khác thêm bản ghi thỏa điều kiện sau bước kiểm tra, tổng hoặc số lượng thực tế có thể khác với dữ liệu mà giao dịch đầu tiên đã dùng để ra quyết định.

Ví dụ, một hệ thống kiểm tra số chỗ đã đặt trong một phòng trước khi xác nhận thêm một lượt đặt chỗ. Nếu hai giao dịch cùng kiểm tra một tập chỗ trống rồi mỗi giao dịch thêm một lượt đặt chỗ, việc chỉ đọc và kiểm tra mà không có cơ chế bảo vệ bất biến có thể dẫn đến vượt sức chứa. Đây là một vấn đề phối hợp giao dịch rộng hơn; phantom read là một trong những dấu hiệu cho thấy tập dữ liệu được kiểm tra có thể thay đổi đồng thời.

### 3.3. Báo cáo trong cùng giao dịch có thể không nhất quán

Một báo cáo gồm nhiều câu truy vấn theo các điều kiện liên quan có thể lấy dữ liệu ở những thời điểm khác nhau. Nếu giao dịch khác commit các hàng mới hoặc cập nhật hàng khiến chúng chuyển vào hay ra khỏi tập điều kiện, các phần của báo cáo có thể phản ánh những tập dữ liệu khác nhau.

## 4. Phân biệt đọc ma với các bất thường đồng thời khác

Các hiện tượng này đều xuất hiện trong môi trường nhiều giao dịch, nhưng cần quan sát đúng loại dữ liệu thay đổi để phân biệt.

| Hiện tượng | Điều xảy ra | Dấu hiệu nhận biết |
|---|---|---|
| **Đọc bẩn (dirty read)** | Giao dịch đọc thấy thay đổi chưa commit của giao dịch khác | Giá trị được đọc có thể bị hủy khi giao dịch ghi rollback |
| **Đọc không lặp lại (non-repeatable read)** | Giao dịch đọc cùng một hàng nhiều lần và nhận giá trị cột khác nhau vì giao dịch khác đã commit cập nhật hàng đó | Cùng một hàng vẫn được nhận diện, nhưng giá trị của hàng thay đổi giữa hai lần đọc |
| **Đọc ma (phantom read)** | Giao dịch chạy lại truy vấn theo điều kiện và nhận một tập hàng khác do giao dịch khác đã commit làm thay đổi các hàng thỏa điều kiện | Hàng mới xuất hiện, hàng biến mất hoặc hàng chuyển vào/ra tập kết quả |
| **Ghi đè mất cập nhật (lost update)** | Các giao dịch cập nhật dựa trên cùng dữ liệu cũ và một lần ghi làm mất kết quả của lần ghi khác | Một cập nhật không được phản ánh trong dữ liệu cuối cùng |

Ví dụ, nếu `T2` cập nhật `amount` của một đơn hàng đã tồn tại từ 80 lên 150 và commit, hàng đó bắt đầu thỏa điều kiện `amount >= 100`. Khi `T1` chạy lại truy vấn, hàng này xuất hiện trong kết quả. Đây là thay đổi tập kết quả theo điều kiện, dù không có hàng mới nào được chèn. Nếu `T1` chỉ truy vấn trực tiếp một `order_id` cố định và thấy giá trị `amount` thay đổi, hiện tượng phù hợp hơn với đọc không lặp lại.

## 5. Mức cô lập giao dịch và khả năng đọc ma

Mức cô lập (*isolation level*) quy định những thay đổi đồng thời mà một giao dịch có thể quan sát. Theo các mức cô lập trong định nghĩa SQL chuẩn, khả năng xuất hiện đọc ma được tóm tắt như sau:

| Mức cô lập | Đọc ma theo định nghĩa chuẩn | Ý nghĩa liên quan |
|---|---|---|
| `READ UNCOMMITTED` | Có thể xảy ra | Mức này cũng có thể cho phép đọc bẩn và đọc không lặp lại |
| `READ COMMITTED` | Có thể xảy ra | Mỗi câu lệnh có thể nhìn thấy những thay đổi đã commit trước khi câu lệnh đó bắt đầu; hai câu lệnh trong cùng giao dịch có thể thấy hai tập hàng khác nhau |
| `REPEATABLE READ` | Được phép theo định nghĩa SQL chuẩn | Ngăn đọc bẩn và đọc không lặp lại, nhưng chuẩn SQL vẫn cho phép tập hàng thỏa điều kiện thay đổi |
| `SERIALIZABLE` | Không được xảy ra | Kết quả thực thi phải tương đương với một thứ tự chạy tuần tự hợp lệ của các giao dịch |

Không nên suy ra hành vi của một hệ quản trị chỉ từ tên mức cô lập. Một số hệ quản trị triển khai `REPEATABLE READ` mạnh hơn yêu cầu tối thiểu của chuẩn, chẳng hạn giữ một ảnh chụp dữ liệu nhất quán cho giao dịch và do đó không biểu hiện phantom read theo cách mô tả ở trên. Một số hệ quản trị dùng khóa phạm vi hoặc khóa vị từ để ngăn giao dịch khác chèn hay sửa hàng vào tập đang được bảo vệ. Cơ chế và bảo đảm cụ thể phụ thuộc vào hệ quản trị, phiên bản và loại truy vấn.

Vì vậy, khi cần biết một mức cô lập cụ thể có ngăn phantom read hay không, hãy kiểm tra tài liệu của hệ quản trị đang sử dụng và xác minh bằng lịch thực thi trên môi trường đó.

## 6. Cách phòng tránh và kiểm soát đọc ma

### 6.1. Dùng `SERIALIZABLE` khi cần kết quả tương đương chạy tuần tự

`SERIALIZABLE` là lựa chọn trực tiếp khi nghiệp vụ yêu cầu các giao dịch đồng thời phải có kết quả tương đương với một thứ tự thực thi tuần tự. Hệ quản trị có thể dùng khóa hoặc cơ chế phát hiện xung đột để bảo đảm điều kiện này. Tùy cách triển khai, một giao dịch có thể phải chờ hoặc bị hủy với lỗi serialization; ứng dụng cần có chiến lược retry phù hợp.

Không nên thêm retry vô hạn. Hãy giới hạn số lần thử, chỉ thử lại các lỗi được hệ quản trị xác định là có thể thử lại, và bảo đảm thao tác được thử lại an toàn.

### 6.2. Bảo vệ phạm vi truy vấn bằng khóa vị từ hoặc khóa phạm vi

Một khóa trên từng hàng hiện có chưa chắc đã bảo vệ được các hàng chưa tồn tại nhưng có thể được chèn vào để thỏa điều kiện. Để bảo vệ một khoảng giá trị hoặc điều kiện truy vấn, hệ quản trị có thể dùng khóa phạm vi (*range lock*), khóa vị từ (*predicate lock*) hoặc cơ chế tương đương.

Ví dụ, nếu giao dịch cần giữ ổn định tập đơn hàng có `status = 'PENDING'` và `amount >= 100`, cơ chế bảo vệ phải xét đến cả khả năng giao dịch khác thêm hoặc cập nhật một hàng để hàng đó bắt đầu thỏa điều kiện. Cú pháp và mức độ khóa phụ thuộc vào hệ quản trị; không nên giả định `SELECT ... FOR UPDATE` trên các hàng hiện có luôn ngăn được một hàng mới thỏa điều kiện xuất hiện.

### 6.3. Khóa một hàng điều phối khi nghiệp vụ có điểm đồng bộ rõ ràng

Trong một số thiết kế, các giao dịch có thể khóa chung một hàng điều phối hoặc hàng cha trước khi kiểm tra và thay đổi dữ liệu con. Cách này buộc các giao dịch liên quan tuần tự hóa qua cùng một điểm khóa. Nó chỉ đúng khi mọi đường ghi có thể ảnh hưởng đến điều kiện nghiệp vụ đều tuân theo quy ước khóa đó.

Ví dụ, khi quản lý số chỗ của một sự kiện, hệ thống có thể khóa hàng sự kiện trước khi đếm chỗ đã đặt và thêm lượt đặt chỗ mới. Nếu có một đường xử lý khác chèn đặt chỗ mà không lấy khóa hàng sự kiện, bất biến vẫn có thể bị phá vỡ.

### 6.4. Dùng ràng buộc để bảo vệ bất biến có thể biểu diễn trong cơ sở dữ liệu

Ràng buộc `UNIQUE`, `CHECK`, khóa ngoại hoặc một mô hình dữ liệu phù hợp có thể ngăn một số trạng thái không hợp lệ ngay cả khi có truy cập đồng thời. Ví dụ, `UNIQUE` trên mã ghế và sự kiện có thể ngăn hai lượt đặt cùng một ghế cho cùng sự kiện.

Ràng buộc bảo vệ bất biến mà nó biểu diễn; nó không tự động thay thế mức cô lập cần thiết cho mọi truy vấn tổng hợp hoặc điều kiện trên một tập hàng. Cần xác định rõ quy tắc nghiệp vụ và chọn cơ chế bảo vệ tương ứng.

### 6.5. Chọn cơ chế đọc nhất quán phù hợp với báo cáo

Nếu nhiều câu truy vấn của một báo cáo phải nhìn thấy cùng một trạng thái dữ liệu, hãy chọn cơ chế snapshot hoặc mức cô lập cung cấp ảnh chụp nhất quán ở phạm vi cần thiết. Cần phân biệt ảnh chụp nhất quán trong một giao dịch với bảo đảm serializable: một ảnh chụp ổn định có thể ngăn tập kết quả thay đổi giữa các lần đọc nhưng chưa chắc loại bỏ mọi bất thường ghi đồng thời.

## 7. Cách điều tra khi nghi ngờ có phantom read

Khi hai lần truy vấn trong cùng giao dịch trả về số lượng hoặc tập hàng khác nhau, hãy kiểm tra theo trình tự:

1. Xác nhận hai câu truy vấn dùng cùng điều kiện lọc, cùng phạm vi dữ liệu và cùng các tham số.
2. So sánh danh sách khóa chính của hai tập kết quả để tìm hàng xuất hiện hoặc biến mất.
3. Kiểm tra các giao dịch khác đã `INSERT`, `DELETE` hoặc `UPDATE` những hàng có thể làm thay đổi điều kiện lọc hay chưa.
4. Đối chiếu thời điểm commit của các giao dịch ghi với thời điểm bắt đầu hai câu lệnh đọc.
5. Xác định mức cô lập thực tế, cơ chế khóa hoặc snapshot mà hệ quản trị đã áp dụng.
6. Kiểm tra giao dịch đã dựa vào tập kết quả đó để tính tổng, kiểm tra giới hạn hoặc tạo ra thay đổi nghiệp vụ nào chưa.

Log cho thấy số hàng trả về thay đổi là dấu hiệu để điều tra, nhưng chưa đủ để kết luận phantom read. Cần chứng minh rằng giao dịch khác đã commit thay đổi làm một hoặc nhiều hàng bắt đầu hoặc ngừng thỏa điều kiện truy vấn trong khoảng giữa hai lần đọc.

## 8. Ghi nhớ

- Phantom read xảy ra khi một giao dịch chạy lại truy vấn theo điều kiện và nhận tập hàng khác vì giao dịch khác đã commit thay đổi dữ liệu phù hợp.
- Thay đổi có thể đến từ `INSERT`, `DELETE` hoặc `UPDATE` làm hàng chuyển vào hay ra khỏi tập kết quả.
- `READ COMMITTED` cho phép hiện tượng này; định nghĩa SQL chuẩn cũng cho phép nó ở `REPEATABLE READ`.
- `SERIALIZABLE` ngăn phantom read theo bảo đảm của mức cô lập chuẩn, nhưng có thể làm giao dịch chờ hoặc phải retry.
- Khóa từng hàng hiện có không nhất thiết bảo vệ được những hàng mới có thể xuất hiện; cần chọn cơ chế khóa phạm vi, khóa vị từ, điểm đồng bộ hoặc ràng buộc phù hợp với bất biến nghiệp vụ.

Khi phân tích một lịch thực thi đồng thời, hãy tập trung vào câu hỏi: **Giữa hai lần chạy cùng một truy vấn, có giao dịch nào đã commit thay đổi khiến một hàng bắt đầu hoặc ngừng thỏa điều kiện lọc hay không?**
