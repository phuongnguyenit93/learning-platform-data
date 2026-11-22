# Tỷ lệ lỗi, hết thời gian chờ và giao dịch phải thực hiện lại

Trong tối ưu hiệu năng cơ sở dữ liệu, thời gian phản hồi trung bình chỉ cho biết một phần của bức tranh. Một hệ thống có thể trả lời rất nhanh với phần lớn truy vấn nhưng vẫn làm người dùng chờ lâu vì một nhóm giao dịch bị khóa, hết thời gian chờ hoặc phải chạy lại nhiều lần. Nếu chỉ nhìn vào độ trễ trung bình, các sự cố này dễ bị che khuất.

Ba nhóm chỉ số cần theo dõi cùng nhau là **tỷ lệ lỗi**, **tỷ lệ hết thời gian chờ (timeout)** và **tỷ lệ giao dịch phải thử lại (retry)**. Chúng cho biết yêu cầu có hoàn tất hay không, thời gian chờ bị giới hạn ở đâu và hệ thống phải tiêu tốn thêm bao nhiêu lần thực thi để hoàn thành công việc. Khi kết hợp các chỉ số này với độ trễ phân vị, kế hoạch thực thi, thống kê truy vấn, mức sử dụng I/O, bộ nhớ và tình trạng khóa, ta có cơ sở để xác định nút thắt và kiểm chứng hiệu quả sau khi điều chỉnh SQL hoặc chỉ mục.

## 1. Xác định đúng đơn vị cần đo

Trước khi tính tỷ lệ, cần thống nhất một yêu cầu nghiệp vụ, một giao dịch logic và một lần thực thi cơ sở dữ liệu khác nhau như thế nào.

- **Yêu cầu nghiệp vụ (logical operation)** là công việc mà ứng dụng cần hoàn thành, chẳng hạn tạo đơn hàng hoặc cập nhật số dư.
- **Giao dịch logic (logical transaction)** là đơn vị thay đổi dữ liệu cần bảo đảm tính nhất quán. Một giao dịch logic có thể gồm nhiều câu lệnh SQL.
- **Lần thử (attempt)** là một lần ứng dụng gửi thao tác hoặc giao dịch đến cơ sở dữ liệu. Nếu giao dịch bị deadlock rồi được chạy lại, một giao dịch logic đã tạo ra nhiều lần thử.
- **Lệnh SQL (statement)** là một câu lệnh riêng lẻ. Một giao dịch có thể thực hiện nhiều statement; vì vậy số statement không phải lúc nào cũng là mẫu số phù hợp để đánh giá tỷ lệ giao dịch thất bại.

Ví dụ: ứng dụng nhận một yêu cầu thanh toán. Lần thử đầu tiên bị deadlock, lần thứ hai hoàn tất. Ở cấp lần thử, hệ thống ghi nhận một lần thất bại và một lần thành công. Ở cấp giao dịch logic, kết quả cuối cùng là thành công, nhưng giao dịch đã cần retry và có thể đã tăng độ trễ. Nếu chỉ ghi nhận kết quả cuối cùng, ta bỏ sót áp lực mà tranh chấp khóa tạo ra; nếu chỉ đếm lỗi ở cấp lần thử, ta có thể đánh giá sai mức độ thất bại mà người dùng thực sự gặp phải.

Do đó, hãy ghi nhận cả hai cấp. Mỗi giao dịch logic nên có một mã định danh xuyên suốt các lần thử; mỗi lần thử có số thứ tự riêng. Dùng cùng một `trace_id` hoặc `operation_id` để liên kết log, trace và metric, nhưng không đưa mã định danh riêng lẻ vào nhãn metric có độ đa dạng cao.

## 2. Đo tỷ lệ lỗi

Tỷ lệ lỗi cho biết phần thao tác cơ sở dữ liệu không hoàn thành theo kết quả mong đợi. Công thức cơ bản ở cấp lần thử là:

\[
\text{Tỷ lệ lỗi lần thử} =
\frac{\text{Số lần thử thất bại}}{\text{Tổng số lần thử}}
\times 100\%
\]

Ở cấp nghiệp vụ, nên tính thêm tỷ lệ giao dịch logic thất bại:

\[
\text{Tỷ lệ thất bại logic} =
\frac{\text{Số giao dịch logic không hoàn tất}}{\text{Tổng giao dịch logic}}
\times 100\%
\]

Hai tỷ lệ trả lời hai câu hỏi khác nhau. Tỷ lệ lỗi lần thử phản ánh độ ổn định của từng lần truy cập và chi phí retry. Tỷ lệ thất bại logic phản ánh công việc cuối cùng có được hoàn tất hay không. Một giao dịch thành công sau retry vẫn là thành công ở cấp logic, nhưng lần thử lỗi phải được giữ lại trong số liệu vận hành.

### Phân loại lỗi trước khi cộng vào tử số

Không phải mọi phản hồi không thành công đều là lỗi hiệu năng cơ sở dữ liệu. Nên phân loại ít nhất các nhóm sau:

| Nhóm kết quả | Ví dụ | Cách xử lý khi đo |
|---|---|---|
| Lỗi cơ sở dữ liệu | Vi phạm ràng buộc, lỗi cú pháp SQL, thiếu quyền, lỗi thực thi | Ghi nhận riêng theo nhóm nguyên nhân; xác định lỗi nào thuộc trách nhiệm ứng dụng và lỗi nào phản ánh sự cố dịch vụ |
| Lỗi tranh chấp tạm thời | Deadlock, lỗi serialization, khóa chưa sẵn sàng | Đếm là lần thử thất bại; theo dõi riêng khả năng retry thành công |
| Hết thời gian chờ | Vượt thời hạn chờ khóa, statement hoặc kết nối | Ghi nhận loại timeout và giai đoạn xảy ra |
| Lỗi kết nối | Không lấy được kết nối, kết nối bị ngắt, lỗi mạng | Phân biệt lỗi pool kết nối, mạng và máy chủ cơ sở dữ liệu |
| Kết quả nghiệp vụ bị từ chối | Đơn hàng không đủ điều kiện, dữ liệu đầu vào không hợp lệ | Thường không tính là lỗi cơ sở dữ liệu nếu truy vấn đã thực thi đúng và ứng dụng chủ động từ chối |
| Hủy chủ động | Người dùng hủy thao tác hoặc ứng dụng ngừng chờ | Ghi nhận riêng; không tự động gộp với timeout do hệ thống quá tải |

Định nghĩa “lỗi” phải ổn định giữa các phiên bản ứng dụng. Nếu thay đổi cách phân loại, hãy ghi rõ thời điểm thay đổi để tránh so sánh hai giai đoạn có định nghĩa khác nhau.

### Theo dõi lỗi theo phạm vi

Tách số liệu theo loại giao dịch, dịch vụ gọi cơ sở dữ liệu, nhóm câu lệnh hoặc mẫu truy vấn, cụm cơ sở dữ liệu và phiên bản ứng dụng. Khi cần điều tra, có thể đối chiếu thêm mã SQLSTATE, tên constraint hoặc fingerprint truy vấn trong log và trace. Không nên gắn nội dung SQL đầy đủ, giá trị tham số, mã người dùng hay mã giao dịch riêng lẻ vào nhãn metric vì vừa có nguy cơ lộ dữ liệu, vừa làm số lượng chuỗi nhãn tăng không kiểm soát.

## 3. Đo tỷ lệ hết thời gian chờ

Timeout xảy ra khi một thao tác không hoàn tất trong khoảng thời gian được cấu hình. Timeout là một giới hạn bảo vệ tài nguyên và trải nghiệm, nhưng tỷ lệ timeout tăng thường là dấu hiệu cần điều tra. Tăng thời hạn chờ một cách máy móc có thể chỉ khiến nhiều yêu cầu giữ kết nối và tài nguyên lâu hơn.

Tỷ lệ timeout ở cấp lần thử được tính như sau:

\[
\text{Tỷ lệ timeout} =
\frac{\text{Số lần thử kết thúc do timeout}}{\text{Tổng số lần thử}}
\times 100\%
\]

Để hiểu nguyên nhân, cần phân biệt timeout theo giai đoạn:

- **Chờ lấy kết nối:** ứng dụng không lấy được kết nối từ connection pool trong thời hạn cho phép. Pool có thể quá nhỏ, kết nối bị giữ quá lâu hoặc lưu lượng tăng đột biến.
- **Chờ khóa:** giao dịch phải chờ một giao dịch khác giải phóng khóa. Đây là tín hiệu quan trọng về tranh chấp giao dịch, thứ tự cập nhật hoặc thời gian giữ khóa.
- **Thực thi câu lệnh:** truy vấn chưa hoàn tất trước `statement timeout` hoặc thời hạn truy vấn do ứng dụng đặt. Nguyên nhân có thể là kế hoạch thực thi kém, quét quá nhiều dữ liệu, I/O chậm, thiếu tài nguyên hoặc dữ liệu tăng trưởng.
- **Chờ giao dịch hoặc kết quả:** ứng dụng chờ toàn bộ giao dịch, commit hoặc phản hồi từ máy chủ vượt quá thời hạn. Cần xác định thao tác đang chạy, đang chờ hay kết nối đã mất.
- **Kết nối và mạng:** kết nối bị gián đoạn hoặc phản hồi không đến đúng hạn. Không nên mặc định mọi trường hợp này đều do truy vấn chậm.

Ghi lại thời gian bắt đầu, thời gian kết thúc, thời hạn cấu hình, giai đoạn chờ và loại timeout. So sánh thời gian thực tế với thời hạn giúp phân biệt một truy vấn chạy lâu với một thao tác bị kẹt ở bước lấy kết nối hoặc chờ khóa.

Timeout cũng cần được xem cùng độ trễ phân vị. Trung bình có thể ổn định trong khi p95 hoặc p99 tăng mạnh. Hãy dùng histogram để theo dõi phân phối thời gian, đồng thời ghi nhận số lượng timeout theo cùng khoảng thời gian. Với các nhóm giao dịch khác nhau, có thể đặt ngưỡng thời hạn riêng theo yêu cầu nghiệp vụ và đặc tính truy vấn.

## 4. Đo giao dịch phải thực hiện lại

Retry là việc thực hiện lại một thao tác sau khi lần thử trước gặp lỗi được xem là có khả năng phục hồi. Retry giúp ứng dụng vượt qua một số lỗi tạm thời, nhưng cũng tạo thêm tải cho cơ sở dữ liệu. Khi máy chủ đang quá tải, retry dồn dập có thể làm tình trạng xấu hơn.

Nên theo dõi ít nhất bốn chỉ số:

1. **Tỷ lệ giao dịch có retry:** số giao dịch logic có ít nhất một lần thử lại chia cho tổng giao dịch logic.
2. **Số lần retry:** tổng số lần thử lại, không tính lần thử đầu tiên.
3. **Số lần thử trung bình trên mỗi giao dịch logic:** tổng số lần thử chia cho tổng giao dịch logic. Giá trị này bằng 1 khi không có retry.
4. **Tỷ lệ retry cạn giới hạn:** số giao dịch logic vẫn thất bại sau khi dùng hết số lần thử cho phép chia cho tổng giao dịch logic.

Có thể bổ sung **tỷ lệ retry thành công**: số giao dịch thất bại ở lần đầu nhưng hoàn tất ở một lần retry sau đó chia cho số giao dịch đã phát sinh retry. Chỉ số này giúp đánh giá retry có đang xử lý lỗi tạm thời hiệu quả hay chỉ lặp lại cùng một thất bại.

Ví dụ, trong một phút có 10.000 giao dịch logic. Có 120 giao dịch phải retry ít nhất một lần; tổng số lần retry là 160; 110 giao dịch hoàn tất sau retry và 10 giao dịch vẫn thất bại. Khi đó:

- Tỷ lệ giao dịch có retry là `120 / 10.000 = 1,2%`.
- Số lần thử trung bình trên mỗi giao dịch logic là `(10.000 + 160) / 10.000 = 1,016`.
- Tỷ lệ retry thành công là `110 / 120 ≈ 91,7%`.
- Tỷ lệ retry cạn giới hạn trên tổng giao dịch logic là `10 / 10.000 = 0,1%`.

Ví dụ này cho thấy tỷ lệ thất bại logic có thể thấp trong khi hệ thống vẫn tốn thêm tài nguyên cho retry. Khi lưu lượng lớn, phần tải tăng thêm này có thể làm độ trễ và tranh chấp khóa tăng theo.

## 5. Quy tắc retry an toàn

Chỉ retry những lỗi có khả năng tạm thời và chỉ khi thao tác có thể được thực hiện lại an toàn. Một số lỗi thường có thể xem xét retry tùy hệ quản trị và ngữ cảnh gồm deadlock hoặc serialization failure. Lỗi cú pháp, thiếu quyền, vi phạm dữ liệu đầu vào hoặc vi phạm ràng buộc do dữ liệu không hợp lệ thường không tự biến mất khi chạy lại; retry các lỗi này chỉ tạo thêm tải.

### Retry toàn bộ đơn vị giao dịch phù hợp

Khi cơ sở dữ liệu hủy một giao dịch do deadlock hoặc serialization conflict, ứng dụng thường cần bắt đầu lại toàn bộ giao dịch logic từ đầu. Chỉ chạy lại câu SQL cuối cùng có thể khiến các câu lệnh trước đó và quyết định nghiệp vụ dựa trên dữ liệu cũ không còn nhất quán.

Ví dụ, một giao dịch chuyển tiền gồm đọc số dư, kiểm tra điều kiện, trừ tiền tài khoản nguồn và cộng tiền tài khoản đích. Nếu giao dịch bị hủy do xung đột đồng thời, hãy chạy lại toàn bộ đơn vị giao dịch trong một transaction mới để các bước đọc và kiểm tra được thực hiện trên trạng thái nhất quán.

### Giới hạn số lần thử và thời gian

Một chính sách retry tốt cần có:

- Số lần thử tối đa nhỏ và phù hợp với thời hạn tổng của yêu cầu.
- Khoảng chờ tăng dần (exponential backoff) để giảm tần suất gọi lại khi sự cố kéo dài.
- Jitter ngẫu nhiên để nhiều máy khách không retry đồng loạt vào cùng một thời điểm.
- Một deadline tổng cho toàn bộ giao dịch logic, bao gồm thời gian chờ và mọi lần thử.
- Bộ ngắt mạch (circuit breaker) hoặc cơ chế giảm tải khi tỷ lệ lỗi tăng kéo dài.

Ví dụ giả mã:

```text
for attempt in 1..MAX_ATTEMPTS:
    try:
        begin transaction
        perform all steps of the logical transaction
        commit
        return success
    catch error:
        rollback if the transaction is still active

        if error is not classified as transient:
            return failure

        if attempt == MAX_ATTEMPTS or deadline has expired:
            return failure

        wait with bounded exponential backoff and jitter
```

Đây là cấu trúc khái quát; cách rollback, nhận biết trạng thái kết nối và phân loại lỗi phải theo driver cùng hệ quản trị đang dùng. Không giữ transaction hoặc khóa mở trong lúc chờ backoff.

### Bảo đảm tính lặp an toàn

Một điểm khó là kết quả commit có thể không rõ ràng với ứng dụng. Ví dụ, máy chủ đã commit nhưng kết nối bị ngắt trước khi ứng dụng nhận được phản hồi. Nếu ứng dụng gửi lại thao tác tạo đơn hàng hoặc trừ tiền, nghiệp vụ có thể bị thực hiện hai lần.

Với thao tác có tác dụng phụ, hãy thiết kế tính idempotent. Có thể dùng khóa idempotency do ứng dụng tạo và lưu cùng kết quả xử lý trong một giao dịch; lần gọi lại với cùng khóa sẽ trả về kết quả đã ghi nhận thay vì thực hiện tác dụng phụ lần nữa. Với các quy trình phát sự kiện sau commit, cân nhắc mẫu transactional outbox để việc ghi dữ liệu và ghi sự kiện được phối hợp nhất quán.

Không dựa vào giả định “timeout nghĩa là giao dịch chưa commit”. Khi không xác định được kết quả commit, cần kiểm tra trạng thái bằng mã định danh nghiệp vụ hoặc cơ chế idempotency trước khi thực hiện lại.

## 6. Kết hợp ba nhóm chỉ số để tìm nguyên nhân

Một chỉ số đơn lẻ hiếm khi đủ để kết luận. Hãy quan sát lỗi, timeout, retry, độ trễ và tài nguyên trên cùng trục thời gian, sau đó phân đoạn theo loại giao dịch và fingerprint truy vấn.

| Dấu hiệu quan sát | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Timeout tăng, thời gian chờ khóa tăng, retry do deadlock tăng | Tranh chấp khóa hoặc giao dịch giữ khóa lâu | Xem giao dịch chặn, thứ tự cập nhật bản ghi, thời gian transaction và phạm vi khóa |
| Timeout truy vấn tăng, p95/p99 tăng, CPU hoặc I/O cao | Truy vấn tốn tài nguyên hoặc kế hoạch thực thi thay đổi | So sánh execution plan, số hàng ước lượng với thực tế, số lần đọc và thống kê truy vấn |
| Timeout lấy kết nối tăng nhưng truy vấn trên máy chủ không chậm tương ứng | Connection pool cạn hoặc kết nối bị giữ quá lâu | Kiểm tra kích thước pool, thời gian mượn kết nối, rò rỉ kết nối và số kết nối đang hoạt động |
| Lỗi kết nối tăng đồng thời với lỗi mạng hoặc máy chủ | Sự cố kết nối, failover hoặc máy chủ không sẵn sàng | Đối chiếu log máy chủ, driver, proxy, mạng và sự kiện chuyển đổi dự phòng |
| Tỷ lệ retry tăng nhưng tỷ lệ thất bại logic chưa tăng | Retry đang che bớt lỗi tạm thời | Tính tải phát sinh thêm, độ trễ cuối cùng và tỷ lệ retry thành công |
| Retry tăng cùng lúc với CPU, I/O và timeout tăng | Retry amplification làm quá tải nặng hơn | Giới hạn retry, backoff, jitter và giảm tải đầu vào |
| Lỗi ràng buộc hoặc lỗi cú pháp tăng sau khi phát hành | Thay đổi ứng dụng hoặc dữ liệu không tương thích | Kiểm tra phiên bản triển khai, migration, dữ liệu đầu vào và câu SQL |

Các quan hệ trên là giả thuyết điều tra, không phải bằng chứng kết luận. Cần xác nhận bằng trace, log cơ sở dữ liệu, thống kê truy vấn và kế hoạch thực thi tại thời điểm sự cố.

## 7. Xây dựng mục tiêu và cảnh báo

Mục tiêu nên mô tả kết quả mà người dùng hoặc nghiệp vụ quan tâm, đồng thời giữ các chỉ số vận hành để giải thích nguyên nhân.

Một cách định nghĩa SLI ở cấp giao dịch logic là tỷ lệ giao dịch hoàn tất thành công trong thời hạn nghiệp vụ:

\[
\text{SLI thành công} =
\frac{\text{Giao dịch logic thành công trong thời hạn}}{\text{Tổng giao dịch logic hợp lệ}}
\times 100\%
\]

Giao dịch hoàn tất sau retry có thể được tính là thành công nếu vẫn nằm trong thời hạn nghiệp vụ. Tuy nhiên, số lần retry và độ trễ của giao dịch đó vẫn phải được ghi nhận. Nếu giao dịch hoàn tất sau khi người dùng đã hết thời gian chờ, kết quả kỹ thuật thành công chưa chắc đồng nghĩa trải nghiệm đã thành công.

Khi đặt mục tiêu, hãy làm theo các bước:

1. Chọn nhóm giao dịch có ý nghĩa nghiệp vụ và xác định rõ mẫu số.
2. Đo đường cơ sở qua nhiều khung giờ và tải đại diện, bao gồm giờ cao điểm.
3. Chọn thời hạn hoàn tất dựa trên yêu cầu của ứng dụng; theo dõi p95/p99 để nhận biết phần đuôi phân phối.
4. Đặt mục tiêu tỷ lệ thành công, giới hạn timeout và ngưỡng retry dựa trên đường cơ sở cùng mức độ ảnh hưởng có thể chấp nhận.
5. Xác định cửa sổ đánh giá, cách loại trừ yêu cầu hủy hợp lệ và cách xử lý lưu lượng quá thấp.
6. Theo dõi xu hướng theo thời gian và điều chỉnh mục tiêu khi tải hoặc yêu cầu nghiệp vụ thay đổi.

Không nên dùng một ngưỡng chung cho mọi truy vấn. Một truy vấn báo cáo chạy nền có thể có thời hạn dài hơn thao tác xác nhận thanh toán; hai nhóm cần mục tiêu và cảnh báo riêng.

### Thiết kế cảnh báo có ích

Ưu tiên cảnh báo khi một chỉ số vượt ngưỡng trong một khoảng thời gian đủ dài hoặc khi tốc độ xấu đi bất thường. Kết hợp tỷ lệ với số lượng tuyệt đối để tránh báo động giả khi chỉ có vài yêu cầu. Ví dụ, tỷ lệ timeout 50% trên hai yêu cầu không có cùng mức độ ảnh hưởng với 2% trên hàng chục nghìn yêu cầu.

Một dashboard cơ bản nên có:

- Tổng giao dịch logic và tổng lần thử.
- Tỷ lệ lỗi lần thử và tỷ lệ thất bại logic.
- Tỷ lệ timeout, phân chia theo giai đoạn chờ.
- Tỷ lệ giao dịch có retry, số lần retry và tỷ lệ retry cạn giới hạn.
- Độ trễ p50, p95, p99 của giao dịch logic và từng lần thử.
- Số kết nối đang dùng, thời gian chờ pool, giao dịch đang hoạt động và giao dịch chờ khóa.
- CPU, I/O, bộ nhớ, cache hit hoặc các chỉ số tài nguyên tương ứng của hệ quản trị.

## 8. Ví dụ điều tra một đợt timeout tăng

Giả sử sau khi triển khai phiên bản mới, thao tác cập nhật tồn kho bắt đầu có p99 tăng, timeout chờ khóa tăng và số lần retry do deadlock tăng. Tỷ lệ thất bại logic vẫn thấp vì phần lớn giao dịch thành công sau một lần retry.

Quy trình điều tra có thể thực hiện như sau:

1. So sánh trước và sau triển khai theo cùng loại giao dịch, khung giờ và mức tải. Xác nhận thay đổi không đến từ lưu lượng tăng hoặc thay đổi cách đo.
2. Dùng trace để tìm các giao dịch có thời gian chờ khóa dài; đối chiếu với log giao dịch chặn và các bản ghi được cập nhật đồng thời.
3. Kiểm tra xem các luồng cập nhật có truy cập nhiều bản ghi theo thứ tự khác nhau hay giữ transaction mở trong lúc gọi dịch vụ bên ngoài không.
4. Kiểm tra execution plan và chỉ mục của câu lệnh cập nhật hoặc truy vấn đọc trước khi cập nhật. Xác định có quét phạm vi dữ liệu lớn hoặc khóa nhiều hàng hơn dự kiến không.
5. Thử thay đổi thứ tự truy cập nhất quán, thu hẹp phạm vi transaction hoặc bổ sung chỉ mục phù hợp trong môi trường kiểm thử đại diện.
6. Chạy lại cùng kịch bản tải và so sánh timeout, deadlock, retry, p95/p99, CPU và I/O. Chỉ coi thay đổi là có hiệu quả khi các chỉ số cải thiện mà tính đúng đắn dữ liệu vẫn được bảo đảm.

Trong ví dụ này, tỷ lệ thất bại logic thấp không đủ để kết luận hệ thống khỏe. Retry đã che bớt lỗi cuối cùng nhưng vẫn làm tăng độ trễ và số lần thực thi. Các chỉ số ở cấp lần thử giúp phát hiện vấn đề sớm hơn.

## 9. Lưu ý khi triển khai đo đạc

- Dùng counter cho tổng số lần thử, lỗi, timeout và retry; dùng histogram cho thời gian thực thi, thời gian chờ kết nối và thời gian chờ khóa.
- Gắn nhãn có giới hạn như `operation_type`, `outcome`, `error_class`, `timeout_stage` và `database_cluster`. Không gắn ID giao dịch, ID người dùng hoặc SQL chứa tham số vào nhãn metric.
- Đồng bộ thời gian giữa ứng dụng và máy chủ cơ sở dữ liệu để đối chiếu trace, log và sự kiện.
- Ghi nhận cả kết quả cuối cùng lẫn lịch sử lần thử. Một log giao dịch logic có thể chứa số lần thử, nguyên nhân retry và tổng thời gian đã tiêu tốn.
- Xác định rõ timeout do ứng dụng, driver, connection pool hay hệ quản trị đặt ra. Nhiều tầng timeout có thể chồng lấn; cần ghi nhận tầng nào kết thúc thao tác trước.
- Với hệ quản trị hỗ trợ mã lỗi có cấu trúc, phân loại theo mã thay vì dò chuỗi thông báo. Ví dụ, PostgreSQL có SQLSTATE `40001` cho serialization failure và `40P01` cho deadlock detected; cần đối chiếu tài liệu của phiên bản đang chạy trước khi xây dựng bộ phân loại.
- Bảo vệ log và trace khỏi dữ liệu nhạy cảm. Chỉ ghi thông tin cần thiết để điều tra, áp dụng quyền truy cập và thời hạn lưu phù hợp.
- Kiểm tra bộ đếm sau khi ứng dụng khởi động lại, failover hoặc thay đổi cấu hình để hiểu rõ metric nào được lưu ở máy chủ và metric nào được ghi ở ứng dụng.

## 10. Checklist đánh giá sau điều chỉnh

Khi thay đổi SQL, chỉ mục, cấu hình pool hoặc chính sách retry, hãy dùng cùng một kịch bản tải và xác nhận các điểm sau:

- [ ] Mẫu số và quy tắc phân loại lỗi giống nhau ở giai đoạn trước và sau.
- [ ] Tỷ lệ lỗi lần thử và tỷ lệ thất bại logic được báo cáo riêng.
- [ ] Timeout được phân chia theo lấy kết nối, chờ khóa, thực thi và kết nối.
- [ ] Tỷ lệ giao dịch có retry, số lần thử trung bình và retry cạn giới hạn được theo dõi.
- [ ] p95/p99 và thời gian hoàn tất giao dịch logic đáp ứng mục tiêu.
- [ ] CPU, I/O, bộ nhớ, số kết nối và mức tranh chấp khóa không chuyển thành nút thắt mới.
- [ ] Retry có giới hạn, backoff, jitter và chỉ áp dụng cho lỗi được phân loại phù hợp.
- [ ] Thao tác có tác dụng phụ được bảo vệ bằng cơ chế idempotency hoặc cách xử lý kết quả commit không rõ ràng.
- [ ] Dữ liệu đầu ra vẫn đúng khi có đồng thời, rollback, deadlock và retry.
- [ ] Kết quả được so sánh trên cùng điều kiện tải, cùng khoảng thời gian và cùng định nghĩa chỉ số.

Tỷ lệ lỗi cho biết lần thử nào không thành công; timeout cho biết thao tác bị giới hạn ở giai đoạn nào; retry cho biết hệ thống phải làm thêm bao nhiêu công việc để hoàn tất giao dịch. Khi đo riêng từng cấp và phân tích chúng cùng độ trễ, kế hoạch thực thi, khóa và tài nguyên, nhóm phát triển có thể xác định nguyên nhân rõ hơn, đặt mục tiêu có căn cứ và chứng minh một thay đổi hiệu năng thực sự cải thiện hoạt động của cơ sở dữ liệu.
