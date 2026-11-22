# Gắn mục tiêu với bằng chứng, cách đo và điều kiện đánh giá

Trong chiến lược kiểm thử xác thực (validation testing strategy), mục tiêu chất lượng mô tả kết quả mà sản phẩm cần đạt để đáp ứng nhu cầu sử dụng và mức rủi ro mà tổ chức có thể chấp nhận. Mục tiêu chỉ hữu ích khi nhóm có thể thu thập bằng chứng, đo kết quả trong điều kiện xác định và so sánh kết quả với điều kiện đánh giá đã thống nhất.

Ví dụ, câu “hệ thống phải nhanh” chưa đủ để định hướng kiểm thử. Nhóm cần làm rõ thao tác nào phải phản hồi nhanh, đo từ thời điểm nào đến thời điểm nào, kiểm tra dưới tải bao nhiêu, lấy dữ liệu ở đâu và mức nào được xem là đạt. Tương tự, câu “hệ thống phải an toàn” cần được chuyển thành các yêu cầu bảo mật có thể kiểm tra, chẳng hạn người dùng không có quyền không thể xem dữ liệu của tài khoản khác và các thao tác nhạy cảm được ghi nhận đầy đủ.

Mạch lập luận cần duy trì xuyên suốt là:

```text
Nhu cầu và rủi ro
        ↓
Mục tiêu chất lượng
        ↓
Chỉ số và phương pháp đo
        ↓
Bằng chứng kiểm thử
        ↓
Điều kiện đánh giá
        ↓
Quyết định và rủi ro còn lại
```

Nếu một mắt xích không rõ, kết quả kiểm thử có thể khó diễn giải. Chạy được nhiều ca kiểm thử hoặc thu thập được nhiều số liệu chưa đồng nghĩa với việc đã chứng minh sản phẩm phù hợp.

## 1. Phân biệt nhu cầu, mục tiêu, chỉ số và tiêu chí

Các khái niệm này liên quan chặt chẽ nhưng có vai trò khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ với chức năng tìm kiếm |
|---|---|---|
| Nhu cầu | Việc người dùng cần hoàn thành hoặc vấn đề cần giải quyết | Người mua cần tìm được sản phẩm phù hợp mà không phải chờ lâu |
| Mục tiêu chất lượng | Kết quả chất lượng cần đạt để đáp ứng nhu cầu | Kết quả tìm kiếm phải liên quan và xuất hiện đủ nhanh trong điều kiện sử dụng dự kiến |
| Chỉ số (metric) | Đại lượng dùng để quan sát hoặc định lượng kết quả | Thời gian phản hồi, tỷ lệ truy vấn trả về kết quả phù hợp, tỷ lệ lỗi |
| Phương pháp đo | Cách thu thập chỉ số và điều kiện thực hiện | Đo thời gian từ lúc gửi truy vấn đến khi kết quả hiển thị trên tập dữ liệu đại diện |
| Mục tiêu đo (target) | Giá trị hoặc mức cần đạt của chỉ số | Phân vị 95 của thời gian phản hồi không vượt ngưỡng đã thống nhất |
| Tiêu chí đánh giá | Quy tắc dùng để kết luận bằng chứng đạt, không đạt hoặc chưa đủ | Chỉ chấp nhận khi ngưỡng thời gian và mức liên quan đều đạt trên bộ truy vấn đại diện |

Không nên gộp tất cả thành một câu. Một mục tiêu chất lượng có thể cần nhiều chỉ số để phản ánh đầy đủ kết quả. Ngược lại, một chỉ số có thể hỗ trợ nhiều mục tiêu. Ví dụ, tỷ lệ lỗi có thể ảnh hưởng đến độ tin cậy, khả năng sử dụng và mức độ hoàn thành nghiệp vụ.

Phân biệt thêm **chỉ số** và **mục tiêu đo**: chỉ số cho biết điều gì được đo; mục tiêu đo cho biết mức nào được kỳ vọng. “Thời gian phản hồi” là chỉ số, còn “phân vị 95 không vượt quá 2 giây trong điều kiện tải đã mô tả” là một mục tiêu đo có thể đánh giá. Con số 2 giây ở ví dụ chỉ mang tính minh họa; ngưỡng thật phải xuất phát từ nhu cầu, dữ liệu sử dụng và thỏa thuận của sản phẩm.

## 2. Bắt đầu từ nhu cầu người dùng và rủi ro

Mục tiêu chất lượng nên bắt đầu từ điều người dùng cần làm và hậu quả nếu sản phẩm không đáp ứng. Cùng một thuộc tính chất lượng có thể có mức ưu tiên khác nhau tùy bối cảnh. Độ trễ vài giây có thể chấp nhận được với báo cáo chạy cuối ngày nhưng không phù hợp với thao tác xác nhận giao dịch tại quầy. Một lỗi hiển thị có thể gây bất tiện nhỏ ở trang giới thiệu nhưng có thể làm người dùng không thể đọc số tiền cần thanh toán.

Để xác định mục tiêu, nhóm có thể đi theo các bước:

1. **Mô tả hành trình hoặc công việc:** Ai sử dụng, họ muốn đạt kết quả gì và trong hoàn cảnh nào?
2. **Xác định kết quả quan trọng:** Điều gì phải đúng để người dùng hoàn thành công việc? Có yêu cầu pháp lý, hợp đồng hoặc chính sách nào áp dụng không?
3. **Nhận diện cách thất bại:** Điều gì có thể xảy ra nếu sản phẩm chậm, sai dữ liệu, không sẵn sàng, khó sử dụng hoặc để lộ thông tin?
4. **Đánh giá rủi ro:** Xem xét xác suất, mức độ ảnh hưởng, phạm vi người dùng và khả năng phát hiện hoặc khắc phục.
5. **Chọn mục tiêu có thể kiểm chứng:** Diễn đạt kết quả và liên kết nó với chỉ số, kịch bản hoặc bằng chứng phù hợp.

Ví dụ với luồng đặt hàng, nhu cầu của người mua là đặt đúng sản phẩm và biết đơn hàng đã được ghi nhận. Các rủi ro gồm tính sai tổng tiền, tạo đơn trùng khi người dùng gửi lại yêu cầu, ghi nhận thanh toán nhưng không cập nhật đơn hàng, hoặc để lộ thông tin đơn hàng cho tài khoản khác. Từ đó, nhóm có thể đặt các mục tiêu chất lượng về tính chính xác giao dịch, tính nhất quán trạng thái, khả năng phục hồi khi kết nối gián đoạn và kiểm soát truy cập.

Không phải mọi thuộc tính chất lượng đều cần một chỉ số số học. Một số mục tiêu cần bằng chứng định tính hoặc kiểm tra theo quy tắc, ví dụ người dùng có thể hoàn thành tác vụ bằng bàn phím, thông báo lỗi có thể hiểu được, hoặc vai trò không được phép không thể thực hiện thao tác quản trị. Điều quan trọng là quy tắc quan sát và đánh giá phải rõ ràng, có thể lặp lại và phù hợp với rủi ro.

## 3. Viết mục tiêu chất lượng có thể kiểm chứng

Một mục tiêu tốt nên nêu được đối tượng, kết quả mong muốn, bối cảnh sử dụng và lý do quan trọng. Có thể dùng mẫu câu:

> Trong [bối cảnh hoặc điều kiện], [người dùng/hệ thống] có thể [kết quả cần đạt] với [mức chất lượng mong muốn], để [nhu cầu hoặc rủi ro được giải quyết].

Ví dụ:

- Trong giờ cao điểm dự kiến, khách hàng có thể tải trang danh sách sản phẩm với thời gian phản hồi nằm trong ngưỡng đã thống nhất, để việc tìm và chọn hàng không bị gián đoạn.
- Khi một yêu cầu thanh toán được gửi lại do mất kết nối, hệ thống chỉ ghi nhận một giao dịch cho cùng một yêu cầu hợp lệ, để tránh thu tiền hoặc tạo đơn hàng trùng.
- Người dùng chỉ xem được hồ sơ thuộc phạm vi quyền của mình, kể cả khi họ thay đổi mã định danh trong địa chỉ yêu cầu.
- Người dùng chỉ sử dụng bàn phím có thể hoàn thành các bước cốt lõi của quy trình đăng ký và nhận biết được phần tử đang được chọn.

Mục tiêu cần đủ cụ thể để thiết kế phép kiểm tra nhưng không nên nhồi toàn bộ bước thực thi vào câu mục tiêu. Chi tiết về dữ liệu, công cụ, số lần chạy và môi trường thuộc phương pháp đo hoặc kế hoạch kiểm thử.

Khung SMART (cụ thể, đo lường được, khả thi, phù hợp và có thời hạn) có thể dùng làm câu hỏi rà soát, nhưng không phải công thức thay thế tư duy chất lượng. Một mục tiêu có số đo rõ ràng vẫn có thể sai trọng tâm nếu nó không đại diện cho nhu cầu người dùng. Chẳng hạn, tăng số lượng ca kiểm thử tự động không tự chứng minh rằng sản phẩm dễ sử dụng hoặc ít rủi ro hơn.

## 4. Chọn chỉ số phản ánh đúng kết quả

Chỉ số phải phản ánh mục tiêu và có thể thu thập với độ tin cậy phù hợp. Nên chọn một tập chỉ số nhỏ nhưng đủ bao phủ các rủi ro chính, thay vì thu thập thật nhiều số liệu không dẫn đến quyết định.

Một số nhóm chỉ số thường gặp:

| Thuộc tính hoặc mục tiêu | Chỉ số hoặc bằng chứng có thể dùng | Điều cần làm rõ |
|---|---|---|
| Hiệu năng | Thời gian phản hồi, thông lượng, phân vị độ trễ, mức sử dụng tài nguyên | Thao tác nào được đo, tải và dữ liệu nào được dùng, thời gian làm nóng hệ thống |
| Độ tin cậy | Tỷ lệ lỗi, tỷ lệ giao dịch thành công, thời gian phục hồi | Cách định nghĩa lỗi, mẫu số, khoảng thời gian và điều kiện lỗi được tính |
| Tính sẵn sàng | Thời gian dịch vụ sẵn sàng, số lần gián đoạn, thời gian gián đoạn | Cách xác định trạng thái sẵn sàng và loại trừ bảo trì có kế hoạch |
| Tính chính xác dữ liệu | Số bản ghi đúng, sai lệch đối soát, tính duy nhất của giao dịch | Nguồn dữ liệu chuẩn, quy tắc đối chiếu và cách xử lý dữ liệu trễ |
| Bảo mật | Kết quả kiểm tra phân quyền, xác thực, xử lý đầu vào và ghi nhận sự kiện | Phạm vi kiểm tra, vai trò, loại tấn công và giới hạn của môi trường thử |
| Khả năng sử dụng | Tỷ lệ hoàn thành tác vụ, lỗi thao tác, thời gian hoàn thành, phản hồi người dùng | Nhóm người dùng, tác vụ, hướng dẫn được cung cấp và cách quan sát |
| Khả năng truy cập | Kết quả kiểm tra bàn phím, trình đọc màn hình, tương phản và cấu trúc nội dung | Tiêu chuẩn áp dụng, công cụ và kiểm tra thủ công cần thiết |
| Tương thích | Tỷ lệ kịch bản đạt trên tổ hợp thiết bị, trình duyệt hoặc hệ điều hành | Danh sách nền tảng được hỗ trợ và phiên bản cần kiểm tra |

Với các phép đo hiệu năng, giá trị trung bình thường không đủ. Một số ít yêu cầu rất chậm có thể bị che khuất bởi phần lớn yêu cầu nhanh. Phân vị 90 hoặc 95 giúp quan sát trải nghiệm ở phần đuôi của phân bố; cần ghi rõ cách tính và số lượng mẫu. Với tính sẵn sàng, phải định nghĩa thế nào là dịch vụ hoạt động được và khoảng thời gian nào được tính. Với tỷ lệ lỗi, phải xác định mẫu số là tổng yêu cầu, tổng giao dịch hay tổng phiên người dùng.

Với mục tiêu bảo mật, một báo cáo không phát hiện lỗ hổng trong phạm vi đã kiểm tra không chứng minh hệ thống hoàn toàn an toàn. Báo cáo phải chỉ ra phạm vi, phương pháp, thời điểm và giới hạn kiểm tra. Với khả năng sử dụng, một vài ý kiến thuận lợi không đại diện cho mọi nhóm người dùng; cần mô tả người tham gia, tác vụ và bối cảnh quan sát.

## 5. Định nghĩa phương pháp đo trước khi chạy kiểm thử

Một chỉ số chỉ có ý nghĩa khi cách đo được định nghĩa đủ rõ để người khác có thể hiểu và lặp lại. Mỗi phép đo nên ghi lại các thông tin sau:

| Thành phần phép đo | Nội dung cần mô tả |
|---|---|
| Tên và mục đích | Đo điều gì và hỗ trợ mục tiêu chất lượng nào? |
| Định nghĩa | Công thức, đơn vị, điểm bắt đầu/kết thúc và cách xử lý trường hợp đặc biệt |
| Nguồn dữ liệu | Log, metric, trace, kết quả tự động, quan sát người dùng hay dữ liệu đối soát |
| Tập mẫu | Tình huống, người dùng, dữ liệu, giao dịch hoặc yêu cầu được đưa vào phép đo |
| Điều kiện môi trường | Phiên bản phần mềm, cấu hình, hạ tầng, mạng, thiết bị và dịch vụ phụ thuộc |
| Điều kiện tải | Số người dùng đồng thời, tốc độ gửi yêu cầu, thời lượng và mô hình tải nếu có |
| Cách phân tích | Trung bình, phân vị, tỷ lệ, phân nhóm, quy tắc xác định ngoại lệ |
| Mục tiêu và giới hạn | Ngưỡng đạt, ngưỡng cảnh báo, mức không chấp nhận và người phê duyệt |
| Trách nhiệm | Người chuẩn bị, người kiểm tra dữ liệu và người đưa ra quyết định |

Ví dụ về phép đo thời gian phản hồi API:

```yaml
metric: api_response_time
unit: milliseconds
start_event: request_sent
end_event: response_received
statistic: p95
population: checkout_api_requests
environment: staging
workload:
  concurrent_users: 100
  duration_minutes: 20
target:
  p95_max: 800
```

Đây là cấu hình minh họa để cho thấy một phép đo cần được mô tả như thế nào; các giá trị về số người dùng, thời lượng và ngưỡng không phải khuyến nghị áp dụng cho mọi hệ thống. Trong thực tế, nhóm phải thống nhất tải đại diện từ mô hình sử dụng, cấu hình gần với môi trường mục tiêu và nhu cầu sản phẩm. Cần xác định thêm giai đoạn làm nóng, số lần lặp, cách xử lý lỗi sinh tải và nguồn đồng hồ đo để kết quả có thể so sánh.

Khi so sánh giữa các lần chạy, hãy kiểm tra liệu phiên bản, cấu hình, dữ liệu và tải có tương đương hay không. Nếu điều kiện thay đổi, khác biệt kết quả có thể đến từ môi trường thay vì thay đổi của sản phẩm.

## 6. Thu thập bằng chứng và duy trì khả năng truy vết

Bằng chứng là dữ liệu hoặc quan sát hỗ trợ một kết luận về mục tiêu chất lượng. Tùy mục tiêu, bằng chứng có thể là kết quả ca kiểm thử, log, metric, trace, ảnh chụp, bản ghi phiên sử dụng, báo cáo quét bảo mật, dữ liệu đối soát hoặc biên bản chấp nhận của người dùng.

Một bằng chứng có thể sử dụng cần trả lời được:

- Đã kiểm tra yêu cầu, rủi ro hoặc mục tiêu nào?
- Phiên bản sản phẩm, môi trường và dữ liệu nào được dùng?
- Ai hoặc công cụ nào thực hiện, vào thời điểm nào?
- Điều kiện thực hiện và kết quả mong đợi là gì?
- Kết quả thực tế ra sao, có sai lệch hoặc ngoại lệ nào?
- Tệp, log, liên kết hoặc mã lần chạy nào cho phép kiểm tra lại?

Nên duy trì liên kết hai chiều giữa nhu cầu, mục tiêu chất lượng, yêu cầu, rủi ro, ca kiểm thử, kết quả và lỗi. Ví dụ, từ một mục tiêu về tính chính xác giao dịch, người xem báo cáo cần truy ngược được đến quy tắc tính tiền, các kịch bản kiểm thử, dữ liệu đầu vào, kết quả đối soát và lỗi liên quan. Ngược lại, khi một yêu cầu thay đổi, nhóm có thể xác định mục tiêu và bằng chứng nào cần cập nhật.

Không nên chỉ lưu trạng thái “Pass” hoặc “Fail” mà thiếu dữ liệu hỗ trợ. Trạng thái cho biết kết luận của một lần chạy; bằng chứng đi kèm cho phép người khác đánh giá kết luận đó có đáng tin cậy hay không. Với dữ liệu nhạy cảm, cần giới hạn quyền truy cập, che thông tin nhận dạng và tuân thủ chính sách lưu trữ của tổ chức.

## 7. Xây dựng điều kiện đánh giá rõ ràng

Điều kiện đánh giá chuyển kết quả đo thành quy tắc ra quyết định. Một điều kiện tốt phải chỉ ra ngưỡng, phạm vi áp dụng, cách xử lý trường hợp ngoại lệ và người có thẩm quyền chấp nhận rủi ro.

Có thể chia điều kiện theo thời điểm:

- **Điều kiện bắt đầu:** Yêu cầu, mục tiêu, phương pháp đo, môi trường, dữ liệu và ngưỡng đánh giá đã được thống nhất; các phụ thuộc cần thiết sẵn sàng.
- **Điều kiện kết thúc:** Các phép kiểm tra đã định được thực hiện; bằng chứng đủ chất lượng; kết quả được phân loại; sai lệch và rủi ro tồn dư được ghi nhận.
- **Điều kiện chấp nhận:** Các mục tiêu bắt buộc đạt ngưỡng; không còn vấn đề vượt mức rủi ro cho phép nếu chưa có quyết định chấp nhận ngoại lệ; bên có thẩm quyền xác nhận kết quả.

Một bảng quyết định đơn giản có thể giúp thống nhất cách xử lý:

| Kết quả | Điều kiện | Hành động |
|---|---|---|
| Đạt | Các mục tiêu bắt buộc có bằng chứng hợp lệ và nằm trong ngưỡng | Ghi nhận kết quả, tiếp tục bước đánh giá hoặc phát hành theo quy trình |
| Không đạt | Có mục tiêu bắt buộc vượt ngưỡng hoặc phát hiện lỗi không thể chấp nhận | Tạo hoặc cập nhật lỗi, phân tích nguyên nhân, sửa và kiểm thử lại |
| Bị chặn | Không thể đo do môi trường, dữ liệu hoặc phụ thuộc không sẵn sàng | Ghi rõ nguyên nhân, người xử lý và thời điểm đánh giá lại |
| Chưa đủ bằng chứng | Phép đo đã chạy nhưng mẫu, phạm vi hoặc chất lượng dữ liệu không đủ để kết luận | Bổ sung mẫu hoặc phương pháp, sau đó đánh giá lại |
| Chấp nhận có điều kiện | Còn rủi ro đã được mô tả và người có thẩm quyền chấp thuận | Ghi quyết định, biện pháp giảm thiểu, người chịu trách nhiệm và hạn xử lý |

Không nên tự động gộp tất cả chỉ số thành một điểm trung bình. Một chỉ số tổng hợp có thể che giấu một lỗi nghiêm trọng ở mục tiêu bắt buộc. Ví dụ, hiệu năng tốt không bù được việc người dùng có thể xem dữ liệu của tài khoản khác. Hãy phân biệt ngưỡng bắt buộc, ngưỡng cảnh báo và chỉ số theo dõi để quyết định phản ánh đúng mức độ rủi ro.

Việc đạt điều kiện kiểm thử cũng không tự động đồng nghĩa với quyết định phát hành. Người có thẩm quyền cần xem xét phạm vi đã kiểm tra, rủi ro chưa được bao phủ, tác động kinh doanh, kế hoạch giám sát và phương án khôi phục.

## 8. Ví dụ xuyên suốt: xác nhận chất lượng của luồng thanh toán

Giả sử nhóm cần xác nhận luồng thanh toán trực tuyến trước một đợt phát hành. Mục tiêu chất lượng có thể được xây dựng như sau:

| Nhu cầu/rủi ro | Mục tiêu chất lượng | Chỉ số hoặc bằng chứng | Điều kiện đánh giá minh họa |
|---|---|---|---|
| Khách hàng bị thu tiền sai | Tổng tiền giao dịch khớp với đơn hàng và quy tắc giảm giá/thuế | Đối soát số tiền giữa giỏ hàng, yêu cầu thanh toán và kết quả từ cổng thanh toán | Tất cả trường hợp ưu tiên cao khớp theo quy tắc đã thống nhất |
| Gửi lại yêu cầu gây giao dịch trùng | Một yêu cầu thanh toán hợp lệ chỉ tạo một kết quả giao dịch | Mã định danh yêu cầu, số giao dịch, số đơn hàng và log xử lý lặp | Kiểm thử gửi lại và mất kết nối không tạo giao dịch hoặc đơn hàng trùng |
| Người mua không biết đơn hàng đã được xác nhận | Trạng thái đơn hàng và thông báo phản ánh đúng kết quả thanh toán | Trạng thái lưu trữ, phản hồi API và thông báo được gửi | Các nhánh thành công, thất bại, hủy và chờ xử lý có kết quả đúng |
| Người khác truy cập thông tin đơn hàng | Chỉ chủ thể có quyền mới xem được thông tin đơn hàng | Kết quả kiểm thử xác thực và phân quyền với nhiều vai trò/tài khoản | Mọi trường hợp truy cập trái phép trong phạm vi kiểm tra đều bị từ chối và được ghi nhận phù hợp |
| Thanh toán chậm làm gián đoạn mua hàng | Luồng thanh toán đáp ứng mức hiệu năng đã thống nhất | Phân vị thời gian phản hồi, tỷ lệ lỗi và thông lượng dưới tải đại diện | Các chỉ số nằm trong ngưỡng đã phê duyệt ở điều kiện tải được mô tả |

Để thực hiện, nhóm chuẩn bị dữ liệu đơn hàng có nhiều mức giá, thuế và mã giảm giá; tài khoản sandbox; các kịch bản giao dịch thành công, thất bại, hủy và gửi lại; môi trường có log và metric; cùng tập tài khoản ở các vai trò khác nhau. Mỗi lần chạy ghi lại phiên bản, thời gian, cấu hình và mã lần chạy để có thể truy vết.

Khi đánh giá, nhóm không chỉ đếm số ca đạt. Họ kiểm tra liệu từng mục tiêu bắt buộc đã có bằng chứng tương ứng chưa, kết quả có lặp lại được không, có sai lệch nào chưa giải thích không và rủi ro còn lại có được người có thẩm quyền chấp nhận không. Nếu kiểm thử hiệu năng đạt nhưng phép đối soát phát hiện thu tiền sai, mục tiêu chất lượng quan trọng vẫn chưa đạt và quyết định phát hành phải phản ánh rủi ro đó.

Các ngưỡng định lượng cụ thể trong dự án phải được xác định dựa trên yêu cầu, dữ liệu thực tế, năng lực hệ thống và mức rủi ro. Bảng trên mô tả cấu trúc lập luận, không phải bộ tiêu chuẩn chung cho mọi cổng thanh toán.

## 9. Những sai lệch thường gặp khi đo và đánh giá

Một số lỗi trong thiết kế phép đo có thể làm kết luận sai lệch dù nhóm thực hiện đúng quy trình:

- **Chọn chỉ số dễ đo thay vì chỉ số có ý nghĩa:** Số lượng ca kiểm thử hoặc tỷ lệ tự động hóa không trực tiếp chứng minh trải nghiệm người dùng hay mức an toàn.
- **Không định nghĩa mẫu số:** Tỷ lệ lỗi không có ý nghĩa nếu không rõ lỗi được chia cho tổng yêu cầu, giao dịch hay phiên.
- **Chỉ nhìn giá trị trung bình:** Trung bình có thể che khuất các trường hợp rất chậm hoặc rất xấu ở nhóm người dùng nhỏ.
- **Mẫu không đại diện:** Dữ liệu thử quá đơn giản hoặc tải không phản ánh cách sử dụng thực tế khiến kết quả thiếu giá trị dự báo.
- **Môi trường không tương đương:** Khác biệt về cấu hình, dữ liệu hoặc dịch vụ phụ thuộc làm phép so sánh mất ý nghĩa.
- **Chạy ít lần hoặc không kiểm tra độ ổn định:** Một kết quả đơn lẻ có thể chịu ảnh hưởng ngẫu nhiên hoặc lỗi môi trường.
- **Chỉ đo điều thuận lợi:** Bỏ qua nhánh lỗi, người dùng có nhu cầu tiếp cận khác nhau hoặc điều kiện mạng kém có thể làm thiếu bằng chứng.
- **Thay đổi ngưỡng sau khi xem kết quả:** Điều chỉnh tiêu chí mà không ghi lý do và người phê duyệt làm giảm tính khách quan.
- **Dùng chỉ số thay thế như mục tiêu cuối cùng:** Khi nhóm bị đánh giá chỉ bằng một con số, họ có thể tối ưu con số đó trong khi kết quả người dùng không cải thiện. Cần kiểm tra cả chỉ số kết quả và các chỉ số bảo vệ (guardrail).
- **Coi không phát hiện lỗi là chứng minh không có lỗi:** Kết luận phải giới hạn trong phạm vi, điều kiện và phương pháp đã kiểm tra.

Khi phát hiện một phép đo không đáng tin cậy, hãy ghi rõ giới hạn và bổ sung bằng chứng cần thiết. Không nên biến dữ liệu thiếu thành kết luận đạt.

## 10. Rà soát và cập nhật mục tiêu trong suốt vòng đời sản phẩm

Mục tiêu chất lượng cần được xem xét khi nhu cầu, kiến trúc, quy mô sử dụng, nền tảng, tích hợp hoặc mức rủi ro thay đổi. Ví dụ, khi lượng người dùng tăng, mục tiêu hiệu năng và tính sẵn sàng có thể cần điều chỉnh; khi bổ sung vai trò mới, phạm vi kiểm tra phân quyền và bằng chứng bảo mật cần được cập nhật.

Sau mỗi chu kỳ kiểm thử hoặc phát hành, nhóm nên:

1. Đối chiếu từng mục tiêu với bằng chứng thực tế và ghi nhận mục tiêu chưa có đủ bằng chứng.
2. Phân tích lỗi lọt ra môi trường sử dụng để tìm khoảng trống trong mục tiêu, chỉ số, dữ liệu hoặc điều kiện kiểm thử.
3. Kiểm tra xem các ngưỡng còn phù hợp với nhu cầu và điều kiện vận hành hiện tại không.
4. Cập nhật liên kết giữa mục tiêu, yêu cầu, rủi ro, ca kiểm thử và báo cáo.
5. Ghi nhận thay đổi, lý do, người phê duyệt và thời điểm áp dụng để các lần đánh giá có thể so sánh.

Mục tiêu chất lượng tốt giúp nhóm trả lời ba câu hỏi: sản phẩm cần đạt kết quả gì, bằng chứng nào chứng minh kết quả đó và điều kiện nào cho phép đưa ra kết luận. Khi các câu trả lời được xác định trước khi kiểm thử, nhóm có thể thu thập dữ liệu đúng trọng tâm, diễn giải kết quả nhất quán và đưa ra quyết định dựa trên mức độ rủi ro thực tế.
