# Directory latency

## 1. Độ trễ directory trong IAM là gì?

Trong IAM, **directory** là dịch vụ lưu trữ và tra cứu danh tính, chẳng hạn một thư mục LDAP, hệ thống directory doanh nghiệp hoặc dịch vụ kho danh tính mà nền tảng xác thực truy cập. Directory latency là thời gian cần để hoàn thành một tương tác đã xác định với dịch vụ đó.

Directory có thể cung cấp thông tin tài khoản, trạng thái hoạt động, thuộc tính tổ chức, nhóm và các dữ liệu cần cho quyết định truy cập. Vì vậy, độ trễ directory có thể ảnh hưởng trực tiếp tới thời gian đăng nhập, cấp phiên, ánh xạ thuộc tính hoặc kiểm tra quyền.

Ví dụ, người dùng nhập thông tin xác thực vào một ứng dụng. Dịch vụ IAM cần tìm tài khoản, xác minh thông tin đăng nhập và lấy nhóm phục vụ phân quyền. Nếu bước lấy nhóm kéo dài, người dùng vẫn cảm nhận đăng nhập chậm ngay cả khi bước xác minh thông tin đăng nhập rất nhanh.

Điểm quan trọng đầu tiên là xác định **đang đo tương tác nào và từ vị trí nào**. Thời gian tìm kiếm do directory server ghi nhận và thời gian IAM client phải đợi kết quả không phải cùng một phép đo.

## 2. Các phạm vi độ trễ cần phân biệt

Một hành trình đăng nhập có thể chứa nhiều lớp thời gian:

| Phạm vi đo | Điểm bắt đầu và kết thúc minh họa | Câu hỏi được trả lời |
| --- | --- | --- |
| Đăng nhập đầu cuối | IAM nhận giao dịch đến khi có kết quả theo hợp đồng luồng | Người dùng hoặc ứng dụng phải chờ bao lâu? |
| Tra cứu danh tính logic | Bắt đầu lấy dữ liệu danh tính đến khi có đủ dữ liệu hoặc kết thúc lỗi | Phụ thuộc directory đóng góp bao nhiêu vào giao dịch? |
| Chờ connection pool | Xin kết nối đến khi được cấp kết nối hoặc hết hạn chờ | Client có bị nghẽn tài nguyên kết nối không? |
| Thiết lập kết nối | Bắt đầu thiết lập đến khi kết nối sẵn sàng theo định nghĩa đo | DNS, mạng hoặc bắt tay bảo mật có đóng góp độ trễ không? |
| Thao tác directory tại client | Gửi thao tác đến khi nhận kết quả kết thúc hoặc timeout | Một lần gọi directory mất bao lâu từ phía IAM? |
| Xử lý tại server | Server tiếp nhận thao tác đến khi hoàn tất xử lý theo log của server | Directory có xử lý truy vấn chậm không? |

Không mặc định metric có tên `directory_duration` bao gồm mọi hàng trong bảng. Một thư viện có thể bắt đầu đồng hồ sau khi lấy kết nối; thư viện khác có thể tính cả thời gian chờ pool. Cần mô tả rõ ranh giới để người đọc không kết luận sai.

Một phép đo từ client thường có thể bao gồm truyền request, chờ server và nhận response. Thời gian client lớn hơn thời gian xử lý tại server chưa đủ để kết luận server báo sai: phần chênh lệch có thể nằm trên đường mạng, hàng đợi hoặc phía client.

### Đồng hồ đo và dấu thời gian

Đo thời lượng trong cùng một tiến trình nên dùng đồng hồ đơn điệu, tức đồng hồ phục vụ tính khoảng thời gian và không bị điều chỉnh như giờ hệ thống. Không lấy hiệu thời gian tuyệt đối giữa hai máy để tính độ trễ nếu chưa kiểm soát sai lệch đồng hồ.

Trace phân tán giúp liên kết các bước; thời lượng cục bộ của từng span vẫn cần được đo nhất quán. Đồng bộ thời gian hỗ trợ đối chiếu log, nhưng không thay thế việc định nghĩa đúng điểm bắt đầu và kết thúc.

## 3. Tách theo loại thao tác và kết quả

Các thao tác directory phục vụ những mục đích khác nhau và có phân bố độ trễ khác nhau.

| Loại thao tác | Vai trò trong luồng IAM | Điểm cần quan sát |
| --- | --- | --- |
| Bind hoặc xác minh thông tin xác thực theo cơ chế tích hợp | Thiết lập ngữ cảnh xác thực hoặc kiểm tra thông tin đăng nhập | Tách bind của tài khoản dịch vụ với xác minh người dùng nếu có thể |
| Search tài khoản | Tìm bản ghi danh tính và thuộc tính cần dùng | Phạm vi tìm kiếm, bộ lọc, số thuộc tính, số kết quả |
| Search nhóm hoặc membership | Thu thập nhóm để ánh xạ quyền | Nhóm lồng nhau, số lượt truy vấn, giới hạn mở rộng |
| Modify hoặc cập nhật thuộc tính | Phục vụ quản lý vòng đời danh tính | Độ trễ ghi, kết quả ghi và xác nhận đồng bộ |
| Thao tác duy trì hoặc kiểm tra kết nối | Hỗ trợ vận hành connection pool | Tách khỏi truy vấn nghiệp vụ để tránh làm đẹp số liệu giả |

Các tên thao tác này minh họa những kiểu tương tác có thể có. Hệ thống thực tế có thể dùng API thay cho LDAP hoặc có cách xác minh khác. Nên giữ cùng nguyên tắc quan sát: phân loại theo mục đích có ý nghĩa và có tập giá trị hữu hạn.

Một truy vấn trả về “không tìm thấy tài khoản” có thể là thao tác directory hoàn tất bình thường, dù giao dịch đăng nhập bị từ chối. Tương tự, thông tin xác thực không hợp lệ là một kết quả khác với mất kết nối hoặc timeout. Nếu gom tất cả thành một nhãn `error`, đội vận hành khó phân biệt lỗi hạ tầng với kết quả nghiệp vụ dự kiến.

Có thể dùng nhóm kết quả minh họa như:

```text
success
not_found
invalid_credentials
timeout
connection_error
server_error
cancelled
```

Không áp dụng máy móc mọi kết quả cho mọi thao tác. Quan trọng là ghi nhận đủ kết quả và mô tả rõ kết quả nào được xem là lỗi phụ thuộc trong từng báo cáo.

## 4. Một lần gọi khác với một lần lấy danh tính hoàn chỉnh

Một lần tra cứu danh tính logic có thể tạo nhiều lần gọi vật lý:

```text
Tra cứu danh tính logic
  → tìm tài khoản
  → lấy nhóm trực tiếp
  → mở rộng nhóm lồng nhau
  → đọc trang kết quả tiếp theo
  → tổng hợp dữ liệu để áp dụng chính sách
```

Nếu chỉ đo từng request directory, tất cả request có thể tương đối nhanh nhưng tổng hành trình vẫn chậm do số lượng request lớn. Ví dụ, một lần đăng nhập cần 30 truy vấn tuần tự, mỗi truy vấn 40 ms. Chỉ riêng thời gian chờ truy vấn đã xấp xỉ 1,2 giây, chưa tính xử lý ứng dụng.

Với tìm kiếm phân trang, cần phân biệt thời gian từng trang với thời gian hoàn tất tập kết quả cần dùng. Trả về trang đầu nhanh không có nghĩa bước lấy dữ liệu danh tính đã hoàn thành.

Retry cũng tạo khác biệt. Giả sử ba lần thử mất lần lượt 250 ms, 250 ms và 200 ms; giữa chúng có hai khoảng chờ 100 ms. Thời lượng của yêu cầu logic là khoảng 900 ms, dù không lần thử nào vượt 250 ms.

Vì vậy, nên có hai góc nhìn:

- **Theo lần thử:** dùng để phát hiện lỗi kết nối, server chậm và tải thực tế lên directory.
- **Theo yêu cầu logic:** bao gồm các lần thử và khoảng chờ liên quan, dùng để hiểu tác động tới giao dịch IAM.

Nếu một thao tác yêu cầu dữ liệu từ nhiều nguồn song song, thời gian đầu cuối phụ thuộc đường thực thi quyết định lúc nào có đủ kết quả. Không cộng mọi thời lượng span song song để suy ra thời gian người dùng chờ.

## 5. Đọc phân bố độ trễ thay vì chỉ nhìn trung bình

Thời gian trung bình có thể che giấu một nhóm nhỏ truy vấn rất chậm. Trong IAM, nhóm này có thể bao gồm những người thuộc nhiều nhóm, một ứng dụng có bộ lọc rộng hoặc một vị trí địa lý xa directory.

Các đại lượng bổ sung nhau:

| Đại lượng | Ý nghĩa sử dụng |
| --- | --- |
| Số lượng thao tác | Cho biết mẫu đo có đủ lớn và lưu lượng có thay đổi không |
| Trung bình | Cho biết chi phí thời gian bình quân của tập mẫu |
| p50 | Mô tả vùng giữa của phân bố |
| p95, p99 | Giúp quan sát phần đuôi chậm của phân bố |
| Timeout và lỗi kết nối | Cho thấy những thao tác không nhận được kết quả bình thường |
| Số yêu cầu đang xử lý | Giúp phát hiện tích tụ hoặc tắc nghẽn trước khi hoàn tất |

Ví dụ minh họa có 1.000 thao tác: 950 thao tác mất 20 ms, còn 50 thao tác mất 2.000 ms. Trung bình là:

```text
(950 × 20 + 50 × 2.000) / 1.000 = 119 ms
```

Con số 119 ms không mô tả tốt trải nghiệm của 50 thao tác chậm. Biểu đồ phân bố hoặc percentile phần đuôi giúp thấy sự khác biệt đó. Giá trị percentile cụ thể còn phụ thuộc cách tính hoặc ước lượng, đặc biệt khi dùng histogram.

Không cộng `p95(pool_wait)` với `p95(search)` để suy ra `p95(login)`. Các mẫu ở percentile 95 của từng bước có thể thuộc những giao dịch khác nhau. Muốn biết percentile của đăng nhập, phải đo trực tiếp thời lượng đăng nhập.

Khi tổng hợp nhiều instance, không lấy trung bình các p95. Cần tổng hợp phân bố tương thích trước rồi tính percentile, hoặc tính từ dữ liệu giao dịch thích hợp.

## 6. Timeout, thao tác đang chờ và lỗi bị bỏ sót

Metric chỉ ghi các truy vấn thành công dễ tạo ra dashboard gây hiểu nhầm. Nếu những truy vấn chậm nhất đều timeout rồi bị bỏ khỏi histogram, p95 thành công có thể giảm trong khi người dùng gặp nhiều lỗi hơn.

Nên ghi thời lượng kết thúc theo từng nhóm kết quả, bao gồm timeout và hủy khi có thể. Với timeout, thời lượng này là khoảng thời gian client đã chờ đến khi kết thúc lần gọi; không phải thời gian directory thực sự hoàn thành xử lý phía server.

Các thao tác chưa kết thúc chưa xuất hiện trong histogram thời lượng hoàn tất. Khi directory bị treo, cần xem thêm số thao tác đang xử lý, yêu cầu chờ pool và thời gian chờ hiện tại nếu có. Không nên chờ histogram hoàn tất phản ánh toàn bộ sự cố.

Timeout ngắn hơn không đồng nghĩa directory nhanh hơn. Nó chỉ có thể làm client chờ ít hơn trước khi trả lỗi. Một thay đổi timeout cần được đánh giá cùng tỷ lệ thành công, số retry và thời gian của yêu cầu logic.

Trong luồng IAM, quyết định khi directory không phản hồi phải tuân theo chính sách xác thực và phân quyền đã thiết kế. Không tự diễn giải lỗi phụ thuộc thành tài khoản hợp lệ, bỏ qua kiểm tra quyền hoặc kéo dài quyền truy cập chỉ để cải thiện số liệu độ trễ.

## 7. Bộ metric và truy vấn minh họa

Một thiết kế metric có thể gồm:

```text
iam_directory_operation_duration_seconds
  Histogram thời lượng một lần gọi, có operation và outcome.

iam_directory_lookup_duration_seconds
  Histogram thời lượng lấy danh tính logic, gồm các lần thử liên quan.

iam_directory_pool_wait_duration_seconds
  Histogram thời lượng xin kết nối đến khi được cấp hoặc kết thúc lỗi.

iam_directory_inflight_operations
  Gauge số thao tác đang thực hiện tại client.

iam_directory_pool_pending_requests
  Gauge số yêu cầu đang chờ kết nối.
```

Đây là tên minh họa do ứng dụng định nghĩa, không phải metric mặc định của mọi sản phẩm IAM. Đơn vị `seconds` cần được giữ thống nhất; giao diện có thể chuyển sang ms để dễ đọc.

Giả sử dùng histogram Prometheus dạng classic, có các chuỗi `_bucket`, `_sum` và `_count`. Truy vấn p95 theo loại thao tác trên cửa sổ 5 phút có thể viết:

```promql
histogram_quantile(
  0.95,
  sum by (le, operation) (
    rate(iam_directory_operation_duration_seconds_bucket[5m])
  )
)
```

Truy vấn này gộp các outcome vào cùng phân bố và trả kết quả theo giây. Có thể lọc theo một outcome để điều tra, nhưng nên đặt tên dashboard rõ ràng, chẳng hạn “p95 search thành công”, đồng thời hiển thị lỗi và timeout cạnh đó.

Độ trễ trung bình theo operation:

```promql
sum by (operation) (
  rate(iam_directory_operation_duration_seconds_sum[5m])
)
/
sum by (operation) (
  rate(iam_directory_operation_duration_seconds_count[5m])
)
```

Tỷ lệ các lần gọi kết thúc do timeout:

```promql
sum(rate(iam_directory_operation_duration_seconds_count{
  outcome="timeout"
}[5m]))
/
sum(rate(iam_directory_operation_duration_seconds_count[5m]))
```

Tử số và mẫu số cần cùng phạm vi ứng dụng, môi trường, directory và operation khi áp dụng bộ lọc. Khi mẫu số bằng 0, hiển thị trạng thái không có mẫu thay vì kết luận tỷ lệ bằng 0. Khi không thu thập được metric, hiển thị thiếu telemetry thay vì coi directory đang khỏe.

Các instance được gộp phải sử dụng cấu hình bucket tương thích. Histogram cần có bucket đủ phân giải quanh mức độ trễ quan tâm; cấu hình quá thưa có thể làm percentile ít hữu ích cho điều tra. Chọn cửa sổ và điều kiện số mẫu tối thiểu phù hợp với lưu lượng thực tế.

### Giới hạn nhãn và dữ liệu nhạy cảm

Các nhãn có thể hữu ích gồm môi trường, directory được đặt tên cấu hình sẵn, operation và outcome. Tập giá trị nên hữu hạn và được quản lý.

Không đưa username, email, distinguished name của người dùng, chuỗi bộ lọc đầy đủ, ID giao dịch hoặc token vào nhãn metric. Chúng tạo nhiều chuỗi thời gian và có thể làm lộ thông tin danh tính. Không ghi mật khẩu, bí mật bind hay thông tin xác thực vào metric, log hoặc trace.

Trace phục vụ đối soát nên dùng định danh tương quan và mô tả thao tác đã lọc dữ liệu nhạy cảm. Ví dụ `lookup_user_by_login` là tên mục đích ổn định, còn bộ lọc chứa giá trị đăng nhập thực thường không cần xuất hiện trong dữ liệu quan sát phổ biến.

## 8. Ví dụ phân tích một lần đăng nhập chậm

Một trace ghi nhận đường thực thi tuần tự sau. Các thời lượng chỉ dùng để minh họa:

| Bước | Thời lượng |
| --- | ---: |
| Chờ kết nối từ pool | 180 ms |
| Thiết lập kết nối mới | 120 ms |
| Bind tài khoản dịch vụ | 80 ms |
| Search tài khoản | 300 ms |
| Lấy thông tin nhóm | 120 ms |
| Xử lý còn lại của IAM | 50 ms |
| Tổng | 850 ms |

Ở ví dụ này, tổng bằng 850 ms vì các bước được giả định diễn ra tuần tự, không trùng thời gian và đã bao phủ toàn bộ giao dịch. Không áp dụng phép cộng đó nếu span lồng nhau hoặc có hoạt động song song.

Nếu chỉ theo dõi search 300 ms, đội vận hành bỏ qua 300 ms từ chờ pool và thiết lập kết nối. Nếu server báo search chỉ mất 40 ms, cần đối chiếu đúng request để tìm phần thời gian còn lại: đường mạng, đọc response, hàng đợi hoặc khác biệt về ranh giới đo.

Một kết luận điều tra nên gắn với bằng chứng cụ thể, ví dụ: “thời gian chờ pool tăng đồng thời số kết nối đang dùng đạt giới hạn; số kết nối mới cũng tăng sau triển khai”. Điều đó tốt hơn kết luận chung “directory chậm” khi chưa xác định vị trí độ trễ.

## 9. Các nguyên nhân thường cần đối chiếu

| Dấu hiệu | Nhóm nguyên nhân cần kiểm tra | Bằng chứng bổ sung |
| --- | --- | --- |
| Pool wait tăng, số yêu cầu chờ tăng | Kết nối bị giữ lâu, thiếu khả năng phục vụ hoặc tăng lưu lượng | Kết nối đang dùng, thời gian giữ kết nối, số request đồng thời |
| Thiết lập kết nối tăng | Kết nối bị tạo lại thường xuyên, DNS hoặc bắt tay bảo mật chậm | Tỷ lệ mở mới, lỗi kết nối, thay đổi định tuyến và chứng thư |
| Search theo một mục đích chậm | Phạm vi tìm kiếm rộng, bộ lọc hoặc thuộc tính trả về tốn chi phí | Thời gian server, số kết quả, số trang, mẫu truy vấn đã loại dữ liệu nhạy cảm |
| Lấy nhóm logic chậm nhưng từng call nhanh | Nhiều lượt gọi hoặc mở rộng nhóm tuần tự | Số call mỗi giao dịch, độ sâu mở rộng, số nhóm |
| Chỉ một vùng triển khai chậm | Khoảng cách mạng, định tuyến hoặc lựa chọn directory endpoint | Độ trễ theo vùng, lỗi mạng, endpoint thực tế |
| Lookup logic tăng cùng retry | Lỗi tạm thời hoặc thời hạn chờ không phù hợp với ngân sách luồng | Kết quả từng lần thử, backoff, tổng thời gian giao dịch |
| p95 thành công thấp nhưng timeout tăng | Mẫu thành công không phản ánh các lần thất bại chậm | Phân bố theo outcome, số thao tác đang xử lý |

Các dấu hiệu này là giả thuyết điều tra, không phải kết luận tự động. Ví dụ, tăng kích thước pool có thể giảm thời gian chờ tại client nhưng đồng thời dồn thêm tải vào directory. Cần xác định giới hạn ở đâu trước khi thay đổi.

Nếu dùng connection pool với các thao tác thay đổi ngữ cảnh xác thực của kết nối, phải bảo đảm cơ chế quản lý kết nối giữ đúng ngữ cảnh cho từng yêu cầu. Tái sử dụng kết nối không được làm lẫn danh tính hay quyền giữa các giao dịch.

## 10. Độ trễ, cache và tính đúng của quyết định truy cập

Cache có thể giảm số lần gọi directory, nhưng cần đọc số liệu theo cả hit và miss. Khi hit tăng, độ trễ đăng nhập có thể giảm mà tốc độ xử lý của directory không thay đổi. Ngược lại, chỉ một nhóm miss nhỏ có thể tiếp tục gặp độ trễ cao.

Đối với thuộc tính và nhóm dùng để phân quyền, dữ liệu cache còn liên quan tới thời điểm một thay đổi quyền có hiệu lực. Một tài khoản bị vô hiệu hóa hoặc bị thu hồi nhóm có thể đòi hỏi cơ chế làm mới hay vô hiệu hóa cache phù hợp với chính sách của hệ thống.

Độ trễ đọc cũng khác với độ trễ đồng bộ dữ liệu. Directory có thể trả lời nhanh nhưng replica đang phục vụ dữ liệu cũ. Khi đó, metric latency vẫn đẹp dù thay đổi vòng đời tài khoản chưa hiện diện tại nơi quyết định quyền.

Vì vậy, quan sát directory cho IAM cần đặt ba câu hỏi độc lập:

1. Thao tác có hoàn thành trong thời gian mong đợi không?
2. Thao tác có thành công theo hợp đồng nghiệp vụ và kỹ thuật không?
3. Dữ liệu dùng cho quyết định có đủ mới theo yêu cầu của chính sách không?

Không tối ưu câu hỏi đầu bằng cách bỏ qua hai câu hỏi còn lại.

## 11. Đặt ngưỡng theo ngân sách của luồng IAM

Không có một ngưỡng latency chung cho mọi directory. Mức phù hợp phụ thuộc vị trí triển khai, loại thao tác, tải và ngân sách thời gian của luồng gọi nó.

Nếu đăng nhập có một ngân sách thời gian đã thỏa thuận, phần directory phải được xem cùng các phụ thuộc khác như xác thực bổ sung, kho phiên và xử lý token. Timeout của từng lần thử cùng số retry và backoff phải phù hợp với thời hạn còn lại của giao dịch; không để mỗi lớp độc lập tiêu thụ toàn bộ ngân sách.

Cảnh báo nên kết hợp độ trễ phần đuôi, số mẫu đủ lớn, khoảng thời gian duy trì, timeout hoặc lỗi và tác động tới đăng nhập. Những biến động theo chu kỳ như đầu giờ làm việc cần được đánh giá trên đường cơ sở tương ứng.

Một dashboard hữu ích đặt p95/p99 theo operation cạnh lưu lượng, timeout, pool wait, số yêu cầu đang xử lý và thời gian đăng nhập đầu cuối. Cách trình bày này giúp xác định directory đang xử lý chậm, client đang chờ tài nguyên hay toàn bộ luồng đang tạo quá nhiều lần gọi.

Mục tiêu vận hành là giữ các giao dịch IAM phản hồi đúng thời gian với dữ liệu danh tính đáng tin cậy, đồng thời nhận ra vị trí gây chậm đủ rõ để điều tra và khắc phục.
