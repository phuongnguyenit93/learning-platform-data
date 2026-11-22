# Đọc bẩn (dirty read): đọc thay đổi chưa được xác nhận

Trong cơ sở dữ liệu, một giao dịch (*transaction*) có thể thay đổi dữ liệu trước khi quyết định `COMMIT` để xác nhận các thay đổi đó. Nếu một giao dịch khác đọc được phần dữ liệu đang thay đổi này khi giao dịch ghi vẫn chưa hoàn tất, giao dịch đọc đã thực hiện một **đọc bẩn** (*dirty read*).

Đọc bẩn nguy hiểm vì giá trị vừa đọc có thể biến mất nếu giao dịch ghi bị `ROLLBACK`. Ứng dụng khi đó đã đưa ra quyết định dựa trên một trạng thái chưa từng được xác nhận và cuối cùng không tồn tại trong dữ liệu đã commit.

## 1. Đặt đọc bẩn trong bối cảnh giao dịch

Một giao dịch thường gồm nhiều thao tác đọc và ghi nhưng được cơ sở dữ liệu quản lý như một đơn vị công việc. Ví dụ, khi chuyển tiền, hệ thống cần trừ tiền ở tài khoản nguồn và cộng tiền ở tài khoản đích. Nếu một bước thất bại, giao dịch có thể bị hủy để cơ sở dữ liệu quay lại trạng thái trước khi giao dịch bắt đầu.

`COMMIT` xác nhận các thay đổi của giao dịch. `ROLLBACK` hủy các thay đổi chưa được xác nhận. Trong lúc giao dịch đang chạy, những giá trị nó ghi ra chưa chắc sẽ trở thành dữ liệu chính thức.

**Đọc bẩn xảy ra khi giao dịch đọc quan sát được một thay đổi chưa commit của giao dịch khác.** Đây là vấn đề về tính cô lập (*isolation*) giữa các giao dịch đang chạy đồng thời. Tính cô lập xác định mức độ mà một giao dịch được phép nhìn thấy các thao tác chưa hoàn tất của giao dịch khác.

## 2. Diễn biến của một lần đọc bẩn

Giả sử kho hàng đang có 10 sản phẩm. Giao dịch `T1` tạm thời cập nhật số lượng thành 0 để xử lý một yêu cầu xuất kho. Trong khi `T1` chưa commit, giao dịch `T2` đọc số lượng này và kết luận sản phẩm đã hết. Sau đó, `T1` phát hiện yêu cầu xuất kho không hợp lệ và rollback.

| Thời điểm | Giao dịch T1 | Giao dịch T2 | Trạng thái có thể quan sát |
|---|---|---|---|
| 1 | Bắt đầu giao dịch | | Số lượng đã commit là 10 |
| 2 | Cập nhật số lượng thành 0, chưa commit | | T1 đang giữ thay đổi chưa xác nhận |
| 3 | Chưa kết thúc | Đọc số lượng và nhận giá trị 0 | T2 nhìn thấy thay đổi chưa commit của T1 |
| 4 | Phát hiện lỗi và thực hiện `ROLLBACK` | | Thay đổi của T1 bị hủy; số lượng trở lại 10 |
| 5 | Kết thúc | Đã dùng giá trị 0 để từ chối đơn hàng hoặc phát thông báo hết hàng | Quyết định của T2 dựa trên một giá trị không được xác nhận |

Ở thời điểm 3, `T2` đã đọc dữ liệu chưa được xác nhận. Sau thời điểm 4, giá trị 0 không còn là trạng thái của cơ sở dữ liệu. Tuy nhiên, tác động mà `T2` đã tạo ra ở bên ngoài cơ sở dữ liệu, chẳng hạn từ chối đơn hàng hoặc gửi thông báo, có thể không tự động được thu hồi khi `T1` rollback.

Điểm cốt lõi không nằm ở việc giá trị đọc được có đúng tại một thời điểm hay không. Vấn đề là giao dịch đọc đã nhìn thấy một thay đổi mà giao dịch ghi vẫn có quyền hủy bỏ.

## 3. Minh họa bằng SQL với hai phiên làm việc

Ví dụ dưới đây mô tả trình tự ở mức khái niệm. Cú pháp bắt đầu giao dịch, thời điểm đặt mức cô lập và khả năng hỗ trợ `READ UNCOMMITTED` có thể khác nhau giữa các hệ quản trị cơ sở dữ liệu.

**Phiên A — giao dịch ghi:**

```sql
BEGIN;

UPDATE products
SET quantity = 0
WHERE product_id = 42;

-- Tạm dừng tại đây; thay đổi vẫn chưa được xác nhận.
-- Sau đó, giả sử phát hiện lỗi:
ROLLBACK;
```

**Phiên B — giao dịch đọc:**

```sql
SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
BEGIN;

SELECT quantity
FROM products
WHERE product_id = 42;

COMMIT;
```

Để tái hiện hiện tượng, thực hiện lệnh `UPDATE` ở phiên A trước, chưa chạy `ROLLBACK`, rồi chạy câu `SELECT` ở phiên B. Nếu hệ quản trị hỗ trợ đọc bẩn ở mức cô lập này, phiên B có thể nhận `quantity = 0` dù phiên A chưa commit. Khi phiên A rollback, giá trị đã commit trở lại 10.

Nếu phiên B chạy câu truy vấn sau khi phiên A đã rollback, nó sẽ đọc giá trị đã được khôi phục. Điều đó không xóa được quyết định mà ứng dụng có thể đã đưa ra từ lần đọc trước.

## 4. Vì sao đọc bẩn gây ra lỗi nghiệp vụ?

### 4.1. Quyết định dựa trên dữ liệu không được xác nhận

Một màn hình báo hết hàng, một báo cáo doanh thu hoặc một quy trình xét hạn mức có thể sử dụng giá trị đọc được ngay lập tức. Nếu giá trị đó đến từ giao dịch sẽ rollback, kết quả hiển thị hoặc quyết định nghiệp vụ có thể sai dù dữ liệu trong cơ sở dữ liệu cuối cùng vẫn đúng.

### 4.2. Sai lệch có thể lan sang giao dịch khác

Giả sử `T2` đọc số dư tạm thời đã bị giảm bởi `T1`, rồi ghi một bản ghi quyết định dựa trên số dư đó và commit. Sau đó `T1` rollback. Bản ghi của `T2` vẫn có thể tồn tại dù dữ liệu đầu vào mà nó dựa vào chưa bao giờ được xác nhận.

Khi một giao dịch đã đọc thay đổi chưa commit và tiếp tục tạo ra thay đổi phụ thuộc vào nó, việc giao dịch ghi ban đầu rollback có thể buộc các giao dịch phụ thuộc phải rollback theo. Hiện tượng này được gọi là **rollback dây chuyền** (*cascading rollback*). Hệ thống hạn chế đọc bẩn để tránh phải xử lý loại phụ thuộc này.

### 4.3. Tác động bên ngoài cơ sở dữ liệu khó hoàn tác

Rollback chỉ có thể hoàn tác những thay đổi thuộc phạm vi giao dịch mà cơ sở dữ liệu quản lý. Email, thông báo, lời gọi dịch vụ khác hoặc hành động của người dùng đã phát sinh từ dữ liệu đọc bẩn không tự động biến mất. Vì vậy, đọc bẩn có thể làm cho hệ thống bên ngoài và dữ liệu trong cơ sở dữ liệu không còn nhất quán.

## 5. Phân biệt đọc bẩn với các bất thường đồng thời khác

Các hiện tượng sau đều liên quan đến việc nhiều giao dịch cùng truy cập dữ liệu, nhưng nguyên nhân của chúng khác nhau.

| Hiện tượng | Điều xảy ra | Dấu hiệu nhận biết |
|---|---|---|
| **Đọc bẩn (dirty read)** | Giao dịch đọc thấy thay đổi chưa commit của giao dịch khác | Giao dịch ghi sau đó có thể rollback, làm giá trị đã đọc chưa từng trở thành dữ liệu được xác nhận |
| **Đọc không lặp lại (non-repeatable read)** | Một giao dịch đọc cùng một dòng nhiều lần và nhận các giá trị khác nhau vì giao dịch khác đã commit một cập nhật giữa hai lần đọc | Cả hai lần đọc đều có thể là dữ liệu đã commit, nhưng giá trị của cùng một dòng thay đổi giữa các lần đọc |
| **Đọc ma (phantom read)** | Một giao dịch chạy lại truy vấn theo điều kiện và nhận thêm hoặc mất các dòng do giao dịch khác đã commit thay đổi tập dòng phù hợp | Số lượng hoặc tập dòng thỏa điều kiện truy vấn thay đổi giữa các lần đọc |
| **Ghi đè mất cập nhật (lost update)** | Hai giao dịch cập nhật dựa trên cùng một giá trị cũ, khiến kết quả ghi của giao dịch này ghi đè kết quả của giao dịch kia | Một cập nhật hợp lệ không được phản ánh trong giá trị cuối cùng |

Ví dụ, nếu `T1` cập nhật số lượng hàng nhưng chưa commit, rồi `T2` đọc được số lượng mới và sau đó `T1` rollback, đó là đọc bẩn. Nếu `T1` đã commit trước khi `T2` đọc lần thứ hai và `T2` thấy giá trị mới, đó có thể là đọc không lặp lại. Khác biệt quan trọng là trạng thái commit tại thời điểm đọc.

## 6. Mức cô lập giao dịch và khả năng đọc bẩn

SQL định nghĩa các mức cô lập để quy định những bất thường đồng thời nào có thể xảy ra. Xét riêng đọc bẩn:

| Mức cô lập | Có cho phép đọc bẩn theo định nghĩa chuẩn? | Ý nghĩa liên quan |
|---|---|---|
| `READ UNCOMMITTED` | Có | Đây là mức cô lập thấp nhất; giao dịch có thể đọc thay đổi chưa commit của giao dịch khác |
| `READ COMMITTED` | Không | Giao dịch chỉ đọc dữ liệu đã commit tại thời điểm mỗi câu lệnh đọc; các lần đọc sau vẫn có thể thấy dữ liệu mới đã commit |
| `REPEATABLE READ` | Không | Ngăn đọc bẩn và bảo đảm khả năng đọc lặp lại theo mức cô lập; cách xử lý đọc ma phụ thuộc vào hệ quản trị và cách triển khai |
| `SERIALIZABLE` | Không | Mức cô lập cao nhất trong các mức chuẩn; kết quả thực thi tương đương một thứ tự tuần tự hợp lệ của các giao dịch |

`READ COMMITTED` thường là mức tối thiểu phù hợp khi ứng dụng cần tránh đọc bẩn. Tuy nhiên, nó không đảm bảo mọi câu truy vấn trong cùng một giao dịch đều nhìn thấy cùng một ảnh chụp dữ liệu: một giao dịch khác có thể commit giữa hai câu lệnh, khiến lần đọc sau thấy giá trị mới.

Không nên suy ra hành vi thực tế chỉ từ tên mức cô lập. Mỗi hệ quản trị có thể hỗ trợ các mức khác nhau hoặc triển khai chúng bằng cơ chế khóa và kiểm soát phiên bản (MVCC). Một số hệ quản trị không cung cấp đọc bẩn thực sự và xử lý yêu cầu `READ UNCOMMITTED` như `READ COMMITTED`. Vì vậy, cần kiểm tra tài liệu và hành vi của hệ quản trị đang sử dụng.

## 7. Cách phòng tránh đọc bẩn

### 7.1. Chọn mức cô lập ngăn đọc bẩn

Đặt mức cô lập từ `READ COMMITTED` trở lên cho giao dịch có đọc dữ liệu cần được xác nhận. Việc đặt mức cô lập nên được thực hiện đúng phạm vi giao dịch và theo cú pháp mà hệ quản trị hỗ trợ. Không nên mặc định rằng cấu hình của một hệ quản trị sẽ có cùng hiệu lực trên hệ quản trị khác.

### 7.2. Hiểu cơ chế đọc của hệ quản trị

Hệ quản trị dựa trên khóa có thể phải chờ giao dịch ghi giải phóng khóa trước khi cho phép giao dịch khác đọc. Hệ quản trị dùng MVCC có thể cung cấp cho giao dịch đọc một phiên bản đã commit phù hợp, thay vì cho đọc phiên bản chưa commit. Cả hai cách tiếp cận đều có thể ngăn đọc bẩn, nhưng khác nhau về thời gian chờ, xung đột và khả năng nhìn thấy dữ liệu mới.

### 7.3. Chỉ tạo tác động nghiệp vụ sau khi dữ liệu được xác nhận

Không nên gửi thông báo, phát sự kiện hoặc gọi dịch vụ bên ngoài chỉ dựa trên một giá trị có thể thuộc giao dịch chưa commit. Hãy thiết kế thứ tự xử lý để hành động phụ thuộc chỉ được phát sinh sau khi giao dịch ghi đã commit thành công. Với hệ thống cần phối hợp cơ sở dữ liệu và thông điệp, có thể dùng mẫu transactional outbox để ghi thông điệp trong cùng giao dịch rồi phát đi sau khi commit.

### 7.4. Chọn mức cô lập theo yêu cầu nhất quán

Ngăn đọc bẩn không đồng nghĩa với việc mọi bất thường đồng thời đều đã được loại bỏ. Nếu nghiệp vụ cần nhiều lần đọc nhất quán hoặc cần bảo vệ một điều kiện trên tập dòng, hãy xác định rõ bất biến cần bảo vệ rồi chọn mức cô lập, khóa hoặc cơ chế đồng bộ phù hợp. Mức cô lập cao hơn có thể làm tăng thời gian chờ hoặc khiến giao dịch bị hủy khi phát hiện xung đột; ứng dụng cần xử lý retry khi hệ quản trị yêu cầu.

## 8. Cách kiểm tra khi điều tra lỗi

Khi nghi ngờ một kết quả đọc sai do đọc bẩn, hãy lần theo thứ tự thời gian của các giao dịch:

1. Xác định giao dịch nào đã ghi giá trị mà giao dịch khác đọc được.
2. Kiểm tra giao dịch ghi đã `COMMIT` hay vẫn đang mở tại thời điểm đọc.
3. Kiểm tra giao dịch ghi có `ROLLBACK` sau lần đọc đó hay không.
4. Xác định mức cô lập thực tế của giao dịch đọc và hành vi tương ứng của hệ quản trị.
5. Kiểm tra giao dịch đọc đã dùng giá trị đó để ghi dữ liệu, trả kết quả cho người dùng hay tạo tác động bên ngoài nào chưa.

Một bản ghi log chỉ cho thấy câu `SELECT` trả về giá trị bất thường chưa đủ để kết luận có đọc bẩn. Cần đối chiếu thời điểm đọc với trạng thái commit/rollback của giao dịch ghi và cấu hình cô lập có hiệu lực.

## 9. Ghi nhớ

- Đọc bẩn là đọc thay đổi của giao dịch khác khi thay đổi đó chưa được commit.
- Giao dịch ghi có thể rollback, khiến giá trị mà giao dịch đọc đã quan sát không còn tồn tại trong dữ liệu được xác nhận.
- Quyết định hoặc thay đổi phát sinh từ lần đọc đó có thể tồn tại sau rollback và gây sai lệch nghiệp vụ.
- `READ COMMITTED` trở lên ngăn đọc bẩn theo định nghĩa chuẩn; hành vi cụ thể vẫn cần được xác minh trên hệ quản trị đang dùng.

Khi phân tích một lịch thực thi đồng thời, câu hỏi quan trọng nhất để nhận diện dirty read là: **Tại đúng thời điểm giao dịch đọc lấy giá trị, giao dịch ghi tạo ra giá trị đó đã commit hay chưa?**
