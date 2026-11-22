# Quản lý nợ kiểm thử và kế hoạch xử lý dài hạn

Trong quá trình phát triển, nhóm thường phải đưa ra lựa chọn để đáp ứng tiến độ: giữ lại một ca kiểm thử chậm, trì hoãn tự động hóa một luồng quan trọng, chấp nhận dữ liệu thử khó bảo trì hoặc tạm thời bỏ qua một kiểm tra đang không ổn định. Những lựa chọn này có thể hợp lý trong ngắn hạn, nhưng nếu không được ghi nhận và xử lý, chúng tích lũy thành **nợ kiểm thử (test debt)**. Nợ kiểm thử làm tăng chi phí thay đổi, kéo dài thời gian phản hồi, giảm độ tin cậy của kết quả và khiến nhóm khó biết sản phẩm đang được xác minh đến mức nào.

Quản lý nợ kiểm thử là quá trình nhận diện, ghi nhận, đánh giá, ưu tiên và xử lý có kế hoạch những thiếu hụt hoặc vấn đề trong tài sản, quy trình và môi trường kiểm thử. Mục tiêu không phải loại bỏ mọi khoản nợ ngay lập tức. Nhóm cần hiểu khoản nợ nào đang tạo rủi ro lớn, chi phí trì hoãn ra sao, ai chịu trách nhiệm và khi nào cần xử lý. Một kế hoạch dài hạn tốt liên kết công việc giảm nợ với lộ trình sản phẩm, ngân sách kỹ thuật, rủi ro và mục tiêu chất lượng.

## 1. Nợ kiểm thử là gì?

Nợ kiểm thử là phần chi phí hoặc rủi ro kiểm thử bị đẩy sang tương lai do quyết định hiện tại hoặc do tài sản kiểm thử không được duy trì. Khoản nợ có thể xuất hiện dưới dạng kiểm tra còn thiếu, kiểm thử khó sửa, môi trường không tái tạo được, dữ liệu không đáng tin hoặc bằng chứng không còn phù hợp với phiên bản sản phẩm.

Ví dụ:

- Một tính năng thanh toán được phát hành với kiểm thử thủ công nhưng chưa có kiểm thử hồi quy tự động. Mỗi lần sửa liên quan, nhóm phải thực hiện lại nhiều bước bằng tay.
- Một bộ kiểm thử UI dùng selector mong manh và sleep cố định. Khi giao diện thay đổi nhỏ, nhiều ca thất bại dù hành vi sản phẩm đúng.
- Một API thay đổi schema nhưng test fixture và tài liệu hợp đồng không được cập nhật. Kết quả kiểm thử không còn phản ánh cách consumer thực sự sử dụng API.
- Một nhóm tạm thời bỏ qua kiểm tra phân quyền vì thiếu tài khoản theo vai trò. Về sau, nhóm không có bằng chứng đủ tin cậy cho các quyền nhạy cảm.
- Một suite chạy quá lâu khiến lập trình viên thường bỏ qua hoặc trì hoãn chạy trước khi merge.

Nợ kiểm thử không chỉ là “chưa có automation”. Một bộ kiểm thử tự động lớn nhưng không ổn định, không có oracle đáng tin cậy hoặc không gắn với rủi ro cũng có thể chứa nhiều nợ. Ngược lại, một hoạt động kiểm thử thủ công được thiết kế tốt, có phạm vi rõ và phù hợp với mục tiêu không tự động trở thành nợ.

## 2. Phân biệt nợ kiểm thử với các loại nợ và vấn đề khác

Nợ kiểm thử có liên hệ với nợ kỹ thuật nhưng cần được theo dõi theo góc nhìn riêng.

| Khái niệm | Trọng tâm | Ví dụ |
|---|---|---|
| Nợ kỹ thuật (technical debt) | Chi phí tương lai do thiết kế hoặc triển khai phần mềm chưa tối ưu | Module phụ thuộc chặt, mã trùng lặp, cấu trúc khó mở rộng |
| Nợ kiểm thử (test debt) | Chi phí hoặc rủi ro do thiếu hụt, chất lượng thấp hoặc lỗi thời trong kiểm thử | Thiếu hồi quy cho quy tắc tính phí, suite flaky, test data không tái tạo |
| Defect/lỗi sản phẩm | Hành vi hiện tại không đáp ứng yêu cầu | Đơn hàng bị tính thuế sai |
| Rủi ro sản phẩm | Sự kiện lỗi có thể xảy ra và hậu quả tiềm tàng | Retry có thể tạo giao dịch trùng |
| Công việc kiểm thử đang chờ | Hoạt động đã được lên kế hoạch nhưng chưa thực hiện | Chưa chạy kiểm thử tương thích trên trình duyệt mới |

Một defect có thể tạo ra nợ kiểm thử nếu nhóm chỉ sửa lỗi mà không bổ sung kiểm tra ngăn tái diễn. Một khoản technical debt có thể làm phát sinh test debt nếu module khó kiểm tra hoặc không có seam để thay thế phụ thuộc. Tuy nhiên, không nên gộp tất cả vào một danh sách chung vì cách xử lý, người sở hữu và tiêu chí hoàn thành có thể khác nhau.

Nợ kiểm thử cũng khác với việc kiểm thử chưa hoàn tất trong một chu kỳ. Một hoạt động bị hoãn có thời hạn, người phụ trách và lý do rõ có thể chỉ là công việc đang chờ. Nó trở thành nợ cần quản lý khi việc trì hoãn làm tăng chi phí tương lai, tạo rủi ro hoặc tiếp tục bị đẩy qua nhiều chu kỳ mà không có kế hoạch đáng tin cậy.

## 3. Các loại nợ kiểm thử thường gặp

Phân loại giúp nhóm nhận diện nguyên nhân và chọn biện pháp xử lý phù hợp. Một khoản nợ có thể thuộc nhiều loại.

### 3.1. Nợ về độ bao phủ và phạm vi

- Thiếu kiểm thử cho yêu cầu hoặc rủi ro quan trọng.
- Chỉ kiểm tra luồng chính, bỏ qua trường hợp biên, lỗi và quyền truy cập.
- Thiếu kiểm thử hồi quy sau khi sửa defect.
- Không có kiểm thử cho migration, tương thích hoặc khôi phục dữ liệu.
- Ma trận truy vết giữa yêu cầu, rủi ro và test case không đầy đủ.

### 3.2. Nợ về chất lượng và độ ổn định của test

- Flaky test thường xuyên pass/fail không nhất quán.
- Assertion yếu, chỉ kiểm tra mã phản hồi hoặc trạng thái bề mặt.
- Test phụ thuộc thứ tự, dữ liệu dùng chung hoặc thời gian thực.
- Test có oracle sai hoặc expected result đã lỗi thời.
- Nhiều ca trùng lặp nhưng không bổ sung bằng chứng.

### 3.3. Nợ về tốc độ và khả năng vận hành

- Suite quá chậm hoặc thường xuyên xếp hàng trong CI.
- Setup môi trường và tải dữ liệu tốn nhiều thời gian.
- Test chạy tuần tự dù có thể cô lập và chạy song song.
- Báo cáo đến muộn hoặc khó xác định ca gây lỗi.
- Quá nhiều bước thủ công làm chậm phản hồi.

### 3.4. Nợ về dữ liệu, môi trường và công cụ

- Test data thiếu tính đại diện, chứa dữ liệu cũ hoặc khó tái tạo.
- Không có cơ chế setup/reset/cleanup đáng tin cậy.
- Môi trường khác biệt lớn so với bối cảnh cần xác minh.
- Chứng chỉ, secret, quyền truy cập hoặc dependency không được quản lý tốt.
- Công cụ kiểm thử đã lỗi thời, không còn được hỗ trợ hoặc thiếu license.

### 3.5. Nợ về bảo trì và kiến thức

- Test không có người sở hữu.
- Tên, cấu trúc và tài liệu test khó hiểu.
- Helper, fixture hoặc framework tự xây dựng quá phức tạp.
- Quyết định bỏ qua kiểm thử không được ghi lại.
- Kiến thức chỉ nằm trong một cá nhân và không có hướng dẫn chuyển giao.

### 3.6. Nợ về oracle và bằng chứng

- Không xác định rõ kết quả đúng dựa trên nguồn nào.
- Test chỉ xác nhận thao tác hoàn tất mà không kiểm tra bất biến nghiệp vụ.
- Log và báo cáo không gắn với build, dữ liệu hoặc môi trường.
- Không lưu được đầu vào hoặc seed để tái hiện lỗi.
- Kết quả test không đủ để hỗ trợ quyết định phát hành.

## 4. Nguồn hình thành nợ kiểm thử

Nợ kiểm thử thường tích lũy qua nhiều quyết định nhỏ thay vì một sự kiện duy nhất.

Các nguyên nhân phổ biến:

- Áp lực phát hành khiến nhóm cắt giảm kiểm thử mà không tạo kế hoạch bù đắp.
- Thay đổi yêu cầu nhưng không cập nhật test case, dữ liệu và oracle.
- Kiến trúc hoặc API thay đổi nhanh hơn khả năng bảo trì suite.
- Tự động hóa quá sớm khi hành vi và giao diện chưa ổn định.
- Thiếu kỹ năng hoặc thời gian dành cho thiết kế test có thể bảo trì.
- Môi trường dùng chung, dữ liệu tranh chấp hoặc phụ thuộc ngoài không được kiểm soát.
- CI được mở rộng nhưng không đo queue time, flaky rate và chi phí vận hành.
- Nhóm chỉ đo số lượng test hoặc code coverage mà không đánh giá chất lượng tín hiệu.
- Không có cơ chế sở hữu, rà soát và đóng khoản nợ.
- Defect được sửa nhưng không cập nhật kiểm thử ngăn tái diễn.

Việc xác định nguyên nhân gốc quan trọng hơn chỉ ghi lại triệu chứng. Nếu suite chậm do môi trường khởi động lâu, viết lại assertion không giải quyết nguyên nhân. Nếu thiếu test do không có oracle nghiệp vụ, tăng số lượng test tự động có thể làm nợ lớn hơn.

## 5. Nhận diện và kiểm kê nợ kiểm thử

Nhóm nên kiểm tra nợ kiểm thử từ nhiều nguồn:

- Kết quả CI: thời gian chạy, queue time, retry, flaky test, job bị bỏ qua.
- Lịch sử defect và incident: lỗi lọt qua, lỗi tái diễn, khu vực thường phát sinh sự cố.
- Test suite: test lỗi thời, trùng lặp, assertion yếu, test không còn liên kết với yêu cầu.
- Quy trình phát triển: bước kiểm tra thường bị bỏ qua hoặc phải thực hiện thủ công lặp lại.
- Môi trường và dữ liệu: setup thất bại, tài nguyên mồ côi, cấu hình khác biệt.
- Phản hồi của nhóm: thời gian điều tra, khó khăn khi sửa test, thiếu tài liệu hoặc quyền truy cập.
- Đánh giá rủi ro: khu vực quan trọng chưa có bằng chứng hoặc mức kiểm thử chưa phù hợp.

Một phiên kiểm kê nên có đại diện từ phát triển, QA, vận hành và chủ sở hữu nghiệp vụ khi cần. Có thể rà soát theo thành phần, hành trình người dùng, loại kiểm thử hoặc pipeline.

### 5.1. Viết khoản nợ có thể hành động

Một khoản nợ cần mô tả cụ thể:

1. Tình trạng hiện tại và phạm vi bị ảnh hưởng.
2. Hành vi hoặc bằng chứng đang thiếu/kém chất lượng.
3. Nguyên nhân hoặc quyết định dẫn đến tình trạng đó.
4. Tác động hiện tại và chi phí có thể phát sinh.
5. Rủi ro nếu tiếp tục trì hoãn.
6. Biện pháp xử lý và tiêu chí hoàn thành.

Ví dụ mô tả chưa tốt: “Cần cải thiện test thanh toán”.

Ví dụ có thể hành động: “Các ca retry thanh toán hiện dùng chung một đơn hàng và không xác minh số giao dịch cuối cùng. Khi chạy song song, kết quả không ổn định và có nguy cơ bỏ sót giao dịch trùng. Cần tạo dữ liệu riêng theo test run, kiểm tra idempotency và đối soát số giao dịch trong integration suite.”

## 6. Cấu trúc sổ theo dõi nợ kiểm thử

Sổ nợ kiểm thử (test debt register) là nơi ghi nhận các khoản nợ, đánh giá, chủ sở hữu và kế hoạch xử lý. Có thể dùng bảng tính, công cụ quản lý công việc hoặc hệ thống quản lý chất lượng.

| Trường | Nội dung cần ghi |
|---|---|
| Debt ID | Mã định danh duy nhất |
| Tiêu đề | Mô tả ngắn, cụ thể |
| Loại nợ | Bao phủ, độ ổn định, tốc độ, dữ liệu/môi trường, bảo trì, oracle/bằng chứng |
| Thành phần/phạm vi | Module, API, hành trình, suite hoặc pipeline liên quan |
| Mô tả hiện trạng | Bằng chứng về vấn đề đang tồn tại |
| Nguyên nhân | Quyết định hoặc điều kiện dẫn đến khoản nợ |
| Rủi ro liên quan | Risk ID hoặc hậu quả nếu không xử lý |
| Mức độ/ưu tiên | Mức ưu tiên và căn cứ |
| Chi phí hiện tại | Thời gian chạy, điều tra, thao tác thủ công hoặc sửa chữa |
| Chi phí xử lý ước tính | Nỗ lực, phụ thuộc và nguồn lực cần thiết |
| Chủ sở hữu | Người chịu trách nhiệm theo dõi đến khi đóng |
| Kế hoạch | Các bước, mốc thời gian và phụ thuộc |
| Tiêu chí hoàn thành | Bằng chứng để xác nhận nợ đã được xử lý |
| Rủi ro còn lại | Phần chưa thể loại bỏ sau xử lý |
| Trạng thái/ngày rà soát | Mới, đã ưu tiên, đang xử lý, bị chặn, đã đóng; thời điểm cập nhật |

Không nên biến register thành một danh sách dài không có chủ sở hữu. Mỗi khoản nợ đang hoạt động cần người chịu trách nhiệm, ngày rà soát tiếp theo và quyết định rõ về thứ tự ưu tiên.

## 7. Đánh giá mức độ và ưu tiên nợ kiểm thử

Không phải khoản nợ nào cũng cần xử lý ngay. Nhóm cần đánh giá cả tác động của nợ và chi phí tiếp tục mang nó.

Các yếu tố nên xem xét:

- **Rủi ro sản phẩm:** Nợ có làm giảm khả năng phát hiện lỗi nghiêm trọng không?
- **Tần suất sử dụng:** Vấn đề ảnh hưởng đến mỗi pull request, mỗi lần phát hành hay chỉ một hoạt động hiếm?
- **Mức độ cản trở:** Nó làm chậm phát triển, điều tra hoặc quyết định phát hành đến đâu?
- **Khả năng tích lũy:** Chi phí có tăng theo số lượng tính năng, dữ liệu hoặc thay đổi không?
- **Phạm vi ảnh hưởng:** Một nhóm hay nhiều nhóm phụ thuộc vào tài sản này?
- **Khả năng khắc phục:** Có thể xử lý trong phạm vi nhỏ hay cần thay đổi kiến trúc/môi trường?
- **Chi phí trì hoãn:** Nếu chờ thêm một quý hoặc một phiên bản, chi phí và rủi ro tăng ra sao?
- **Cửa sổ cơ hội:** Có thay đổi kiến trúc, migration hoặc dự án nền tảng nào giúp xử lý thuận lợi hơn không?
- **Yêu cầu bắt buộc:** Có nghĩa vụ bảo mật, an toàn, tuân thủ hoặc hợp đồng cần đáp ứng không?

### 7.1. Ma trận ưu tiên tham khảo

| Mức | Đặc điểm | Hướng xử lý |
|---|---|---|
| P0 – Khẩn cấp | Làm mất khả năng phát hiện rủi ro nghiêm trọng, gây nguy cơ an toàn/dữ liệu hoặc làm cổng phát hành không đáng tin | Xử lý ngay hoặc áp dụng biện pháp giảm thiểu trước khi tiếp tục hoạt động bị ảnh hưởng |
| P1 – Cao | Gây flaky thường xuyên, lỗi lọt ở luồng quan trọng hoặc chi phí vận hành lớn | Đưa vào chu kỳ gần nhất với người phụ trách và mốc cụ thể |
| P2 – Trung bình | Làm chậm một phần quy trình hoặc gây chi phí bảo trì đáng kể nhưng có biện pháp tạm thời | Lập kế hoạch theo quý hoặc gắn với thay đổi liên quan |
| P3 – Thấp | Tác động nhỏ, phạm vi hẹp hoặc chi phí trì hoãn thấp | Theo dõi và xử lý khi có cơ hội phù hợp |

Đây là ví dụ về cách phân loại, không phải quy tắc chung cho mọi tổ chức. Rủi ro rất nghiêm trọng có thể cần xử lý dù khoản nợ chỉ xuất hiện ở một ca ít chạy. Ngược lại, một test chậm vài giây có thể không đáng ưu tiên nếu không ảnh hưởng đáng kể đến phản hồi.

### 7.2. Ước lượng chi phí trì hoãn

Có thể ước lượng chi phí trì hoãn bằng cách xem xét:

- Thời gian thủ công lặp lại mỗi chu kỳ.
- Thời gian điều tra flaky test hoặc cảnh báo giả.
- Chi phí chạy lại pipeline và thời gian chờ của nhóm.
- Xác suất và hậu quả của lỗi có thể lọt qua.
- Số nhóm hoặc sản phẩm bị ảnh hưởng.
- Chi phí sửa sau này khi số lượng phụ thuộc tăng.

Ví dụ, một bộ kiểm thử thủ công mất 4 giờ cho mỗi lần phát hành và phát hành hai lần mỗi tháng sẽ tiêu tốn khoảng 8 giờ thao tác mỗi tháng. Con số này chưa bao gồm thời gian điều phối và rủi ro bỏ sót. Nếu tự động hóa phù hợp mất 3 ngày và cần bảo trì 2 giờ mỗi tháng, nhóm có thể so sánh thời gian đầu tư với lợi ích dài hạn. Tuy nhiên, nếu luồng có tác động tài chính lớn, giảm rủi ro có thể quan trọng hơn tiết kiệm thời gian.

Không cần giả vờ rằng mọi lợi ích đều quy đổi chính xác thành tiền. Hãy nêu giả định, khoảng ước lượng và yếu tố định tính để người ra quyết định hiểu căn cứ.

## 8. Chọn chiến lược xử lý cho từng loại nợ

Một khoản nợ có thể được xử lý theo nhiều cách. Không phải lúc nào cũng cần viết thêm test; đôi khi cần sửa oracle, thay môi trường hoặc loại bỏ ca không còn giá trị.

### 8.1. Bổ sung kiểm thử còn thiếu

Phù hợp khi yêu cầu hoặc rủi ro quan trọng chưa có bằng chứng. Cần xác định test level, test oracle, dữ liệu, trường hợp biên và liên kết với yêu cầu/rủi ro. Ưu tiên kiểm tra gần nơi logic được thực hiện, sau đó bổ sung kiểm thử tích hợp hoặc đầu cuối khi cần xác nhận phối hợp.

### 8.2. Sửa hoặc thiết kế lại flaky test

Điều tra nguyên nhân như dữ liệu dùng chung, thời gian, sleep cố định, race condition hoặc phụ thuộc ngoài. Sửa nguyên nhân gốc, giữ bằng chứng trước/sau và xác nhận ổn định qua số lần chạy phù hợp. Không chỉ tăng retry hoặc tăng timeout để che vấn đề.

### 8.3. Tái cấu trúc test suite

Tách test lớn thành các ca có mục tiêu rõ, loại bỏ trùng lặp có căn cứ, chuyển kiểm tra xuống cấp độ nhanh hơn khi phù hợp và chuẩn hóa helper/fixture. Cần bảo đảm phạm vi rủi ro vẫn được bao phủ sau khi thay đổi.

### 8.4. Cải thiện test data và môi trường

Tạo factory, seed có phiên bản, namespace riêng, cơ chế reset và môi trường dùng một lần. Kiểm soát secret, chứng chỉ, quyền truy cập và dependency. Đo setup time để xác nhận cải tiến có tác động.

### 8.5. Cải thiện oracle và assertion

Đối chiếu expected result với quy tắc nghiệp vụ hoặc nguồn độc lập. Thay assertion bề mặt bằng kiểm tra bất biến và trạng thái cuối quan trọng. Nếu chưa có oracle đủ tin cậy, cần làm rõ yêu cầu hoặc bổ sung người có chuyên môn xác nhận.

### 8.6. Tự động hóa có chọn lọc

Tự động hóa các thao tác lặp lại, có kết quả xác định và giá trị phản hồi cao. Giữ kiểm thử thủ công hoặc thăm dò cho hoạt động cần phán đoán, khám phá hoặc đánh giá trải nghiệm. Không dùng tỷ lệ tự động hóa làm mục tiêu thay thế cho mức bao phủ rủi ro.

### 8.7. Thay thế hoặc loại bỏ test lỗi thời

Nếu một ca không còn phù hợp với hành vi sản phẩm, hãy xác minh rằng yêu cầu đã thay đổi và không còn rủi ro cần kiểm tra trước khi xóa. Nếu ca bị trùng lặp, xác định ca hoặc lớp kiểm thử khác đang cung cấp bằng chứng tương đương. Ghi lại lý do loại bỏ và cập nhật liên kết truy vết.

### 8.8. Chấp nhận có thời hạn

Một số khoản nợ không thể xử lý ngay. Có thể chấp nhận tạm thời nếu rủi ro còn lại được hiểu, có biện pháp bù đắp, người có thẩm quyền chấp thuận và ngày rà soát. Chấp nhận không có thời hạn hoặc không có chủ sở hữu thường khiến nợ bị lãng quên.

## 9. Xây dựng kế hoạch xử lý dài hạn

Kế hoạch dài hạn cần chia khoản nợ thành các đợt có thể thực hiện, gắn với lộ trình sản phẩm và năng lực nhóm. Một kế hoạch tổng quát có thể gồm các bước:

1. **Thiết lập đường cơ sở:** Đo hiện trạng về phạm vi, flaky rate, feedback time, chi phí thủ công và lỗi lọt.
2. **Lập danh mục:** Ghi từng khoản nợ, nguyên nhân, rủi ro, chi phí và chủ sở hữu.
3. **Ưu tiên:** Chọn khoản nợ có tác động lớn và chi phí trì hoãn cao.
4. **Xác định mục tiêu:** Nêu kết quả mong đợi, không chỉ liệt kê task.
5. **Chia giai đoạn:** Xử lý biện pháp khẩn cấp, cải thiện nền tảng, mở rộng phạm vi và tối ưu hóa.
6. **Phân bổ nguồn lực:** Dành năng lực cố định hoặc ngân sách theo quý cho công việc giảm nợ.
7. **Liên kết với roadmap:** Kết hợp xử lý nợ với refactor, migration, thay đổi API hoặc nâng cấp hạ tầng.
8. **Đo kết quả:** So sánh với đường cơ sở và kiểm tra chất lượng bằng chứng sau cải tiến.
9. **Rà soát lại:** Điều chỉnh ưu tiên khi rủi ro, sản phẩm hoặc dữ liệu vận hành thay đổi.

Kế hoạch cần thể hiện cả công việc chủ động và công việc giảm nợ phát sinh trong quá trình phát triển. Nếu chỉ xử lý nợ cũ nhưng liên tục tạo nợ mới với tốc độ cao hơn, tổng nợ sẽ không giảm.

## 10. Chia kế hoạch thành các giai đoạn

Một lộ trình tham khảo:

| Giai đoạn | Mục tiêu | Công việc điển hình | Bằng chứng hoàn thành |
|---|---|---|---|
| 0. Kiểm soát rủi ro tức thời | Ngăn nợ tạo nguy cơ nghiêm trọng | Bổ sung kiểm tra tối thiểu, chặn thao tác nguy hiểm, xác nhận rủi ro còn lại | Rủi ro khẩn cấp có biện pháp và người chấp nhận |
| 1. Ổn định nền tảng | Khôi phục niềm tin vào pipeline | Sửa flaky test, dữ liệu dùng chung, setup/reset và báo cáo lỗi | Flaky rate giảm, test có thể tái hiện, cleanup đạt |
| 2. Khôi phục bằng chứng | Bao phủ các yêu cầu/rủi ro quan trọng còn thiếu | Bổ sung test oracle, regression, contract và kiểm thử quyền | Rủi ro ưu tiên có test result và traceability |
| 3. Giảm chi phí vận hành | Rút ngắn phản hồi và bảo trì | Song song hóa, tối ưu setup, loại trùng lặp, cải thiện helper | P95 feedback time và effort bảo trì giảm |
| 4. Duy trì và phòng ngừa | Ngăn nợ tái tích lũy | Quality gate, review, debt budget, định kỳ rà soát | Nợ mới được ghi nhận, ưu tiên và xử lý trong SLA nội bộ |

Không nhất thiết phải hoàn thành toàn bộ một giai đoạn trước khi bắt đầu giai đoạn khác. Một khoản nợ nghiêm trọng có thể được xử lý song song với việc ổn định nền tảng. Lộ trình cần phản ánh phụ thuộc và năng lực thực tế.

## 11. Đặt mục tiêu và tiêu chí hoàn thành cho khoản nợ

Mỗi khoản nợ cần tiêu chí hoàn thành có thể xác minh. Tránh tiêu chí như “test tốt hơn” hoặc “đã refactor”.

Ví dụ:

| Khoản nợ | Tiêu chí hoàn thành minh họa |
|---|---|
| Thiếu hồi quy cho thanh toán | Các trường hợp retry, timeout, giao dịch trùng và trạng thái cuối có test; kết quả gắn với build và risk ID |
| Flaky UI test | Nguyên nhân gốc được sửa; chạy lặp trong điều kiện kiểm soát đạt ngưỡng ổn định đã thống nhất; không còn retry che giấu fail |
| Suite chậm | P95 feedback time giảm so với baseline trong cùng nhóm job mà không giảm phạm vi rủi ro bắt buộc |
| Test data dùng chung | Mỗi worker có namespace hoặc dữ liệu riêng; chạy song song không tranh chấp; cleanup được xác minh |
| Oracle lỗi thời | Expected result có nguồn nghiệp vụ được xác nhận; assertion kiểm tra kết quả có ý nghĩa |
| Test không có chủ sở hữu | Người sở hữu và tài liệu vận hành được xác định; quy trình cập nhật khi sản phẩm thay đổi rõ ràng |

Tiêu chí nên gồm cả chất lượng và vận hành. Một test mới được viết nhưng không chạy trong CI hoặc không ai chịu trách nhiệm vẫn có thể trở thành nợ tiếp theo.

## 12. Phân bổ năng lực và ngân sách giảm nợ

Nếu công việc giảm nợ chỉ được làm khi còn thời gian, nó thường bị đẩy lùi bởi tính năng mới. Nhóm nên dành năng lực rõ ràng cho bảo trì và cải thiện kiểm thử.

Một số cách:

- Dành một phần năng lực mỗi sprint hoặc mỗi quý cho các khoản nợ ưu tiên.
- Tạo epic hoặc initiative riêng để nhóm theo dõi tiến độ dài hạn.
- Gắn công việc giảm nợ với thay đổi sản phẩm liên quan để giảm chi phí chuyển ngữ cảnh.
- Đưa sửa lỗi flaky nghiêm trọng vào tiêu chí hoàn thành của nhóm sở hữu test.
- Bố trí chuyên gia nền tảng cho test infrastructure, data và CI khi nhiều nhóm cùng phụ thuộc.
- Dự trù chi phí license, runner, môi trường và lưu trữ artifact.

Không cần áp dụng một tỷ lệ ngân sách cố định cho mọi tổ chức. Tỷ lệ phù hợp phụ thuộc tốc độ thay đổi, mức nợ hiện tại, mức rủi ro và độ trưởng thành của quy trình. Điều quan trọng là nguồn lực phải được nhìn thấy trong kế hoạch và được bảo vệ trước các ưu tiên ngắn hạn.

### 12.1. Cân bằng nợ cũ và nợ mới

Nhóm có thể theo dõi:

- Nợ được tạo mới trong kỳ.
- Nợ được xử lý hoặc đóng trong kỳ.
- Tổng nợ theo mức ưu tiên và loại.
- Tuổi trung vị và tuổi P90 của khoản nợ đang mở.
- Tỷ lệ khoản nợ quá hạn so với kế hoạch.

Nếu số khoản nợ mới tăng liên tục, cần tìm nguyên nhân trong quy trình: entry criteria không rõ, review test thiếu, lịch phát hành không có thời gian kiểm chứng hoặc môi trường không được duy trì. Không chỉ tăng số giờ sửa nợ mà bỏ qua cơ chế tạo ra nợ.

## 13. Quản trị và quyền quyết định

Quản lý nợ kiểm thử cần phân định trách nhiệm.

| Vai trò | Trách nhiệm |
|---|---|
| Chủ sở hữu sản phẩm/nghiệp vụ | Xác định hậu quả nghiệp vụ và ưu tiên rủi ro |
| QA/test lead | Điều phối kiểm kê, đánh giá bằng chứng và đề xuất kế hoạch xử lý |
| Nhóm phát triển | Sửa test, cải thiện khả năng kiểm thử và ngăn tái diễn |
| Chủ sở hữu test infrastructure | Quản lý framework, runner, môi trường và dữ liệu dùng chung |
| Vận hành/SRE | Đánh giá tác động vận hành, khả năng quan sát và phục hồi |
| Quản lý kỹ thuật | Phân bổ năng lực, giải quyết phụ thuộc và theo dõi roadmap |
| Người có thẩm quyền chấp nhận rủi ro | Phê duyệt khoản nợ chưa thể xử lý và thời hạn xem xét lại |

Một khoản nợ có thể cần nhiều nhóm tham gia, nhưng phải có một người chịu trách nhiệm điều phối đến khi đóng. Người thực hiện sửa chữa không nhất thiết là người có quyền chấp nhận rủi ro còn lại.

### 13.1. Cơ chế chấp nhận nợ có kiểm soát

Khi quyết định trì hoãn, cần ghi:

- Lý do và lợi ích của việc trì hoãn.
- Rủi ro hiện tại và hậu quả nếu xảy ra.
- Biện pháp bù đắp tạm thời, như kiểm thử thủ công bổ sung hoặc giám sát tăng cường.
- Người có thẩm quyền chấp nhận.
- Chủ sở hữu xử lý và mốc thời gian.
- Điều kiện buộc phải xử lý sớm hơn, ví dụ có incident hoặc thay đổi kiến trúc.

Không nên chấp nhận vô thời hạn một khoản nợ làm mất bằng chứng về an toàn, bảo mật hoặc nghĩa vụ bắt buộc. Nếu rủi ro vượt ngưỡng chấp nhận, cần dừng hoặc giới hạn hoạt động bị ảnh hưởng cho đến khi có biện pháp phù hợp.

## 14. Đo lường hiệu quả xử lý nợ kiểm thử

Đo lường cần cho biết khoản nợ đã giảm và tác động có cải thiện hay không. Một số chỉ số hữu ích:

### 14.1. Chỉ số danh mục nợ

- Số khoản nợ đang mở theo loại và mức ưu tiên.
- Tổng effort ước tính để xử lý.
- Tuổi trung vị/P90 của khoản nợ.
- Tỷ lệ khoản nợ có chủ sở hữu và ngày rà soát.
- Tỷ lệ khoản nợ được đóng đúng mốc kế hoạch.
- Số nợ mới so với số nợ được xử lý trong kỳ.

### 14.2. Chỉ số chất lượng kiểm thử

- Flaky failure rate và retry recovery rate.
- Tỷ lệ cảnh báo giả đã xác nhận.
- Số lỗi lọt qua các giai đoạn và lỗi tái diễn.
- Tỷ lệ rủi ro ưu tiên có bằng chứng kiểm thử phù hợp.
- Tỷ lệ test có oracle, dữ liệu và chủ sở hữu rõ.
- Tỷ lệ test bị skip/quarantine và thời gian tồn tại của chúng.

### 14.3. Chỉ số hiệu quả quy trình

- P50/P90/P95 feedback time.
- Queue time, setup time và execution time.
- Thời gian triage và tái hiện lỗi.
- Thời gian bảo trì test theo sprint hoặc quý.
- Tỷ lệ pipeline bị chặn do môi trường so với lỗi sản phẩm.
- Thời gian từ khi phát hiện khoản nợ đến khi có quyết định và chủ sở hữu.

Không nên tối ưu một chỉ số riêng lẻ. Flaky rate có thể giảm vì nhóm cách ly quá nhiều test; execution time có thể giảm vì bỏ các ca quan trọng. Cần đọc chỉ số cùng phạm vi bao phủ, rủi ro, lỗi lọt và chất lượng bằng chứng.

## 15. Tích hợp quản lý nợ vào quy trình thay đổi

Nợ kiểm thử cần được xem xét khi thay đổi sản phẩm hoặc quy trình có thể tạo thêm chi phí tương lai.

Trước khi merge hoặc phát hành, nhóm có thể hỏi:

- Thay đổi này có tạo rủi ro mới chưa được kiểm thử không?
- Có test cũ nào cần cập nhật hoặc loại bỏ không?
- Có dữ liệu, môi trường hoặc oracle mới cần duy trì không?
- Nếu phải hoãn một kiểm tra, khoản nợ có được ghi nhận và phê duyệt không?
- Có thể bổ sung kiểm tra ở cấp độ thấp hơn để phản hồi sớm không?
- Có ảnh hưởng đến thời gian pipeline hoặc độ ổn định không?

Trong review, nên yêu cầu thay đổi có rủi ro đáng kể đi kèm bằng chứng phù hợp. Nếu chấp nhận chưa có test, ghi rõ khoản nợ và thời điểm xử lý. Khi sửa defect, cân nhắc bổ sung regression test để tránh tái diễn.

Có thể đưa một số quy tắc vào Definition of Done:

- Test mới có mục tiêu, oracle và dữ liệu rõ.
- Test liên quan được cập nhật khi hành vi thay đổi.
- Flaky test mới được điều tra trước khi trở thành cổng chặn chính.
- Bỏ test cần có lý do và đánh giá tác động đến rủi ro.
- Nợ phát sinh có ID, chủ sở hữu và kế hoạch.

## 16. Ví dụ kế hoạch dài hạn cho hệ thống thương mại điện tử

Giả sử một nền tảng thương mại điện tử có các vấn đề sau:

| ID | Khoản nợ | Ưu tiên | Tác động hiện tại |
|---|---|---|---|
| TD-01 | Kiểm thử thanh toán retry thiếu kiểm tra giao dịch trùng | P0 | Nguy cơ tài chính và khó đối soát |
| TD-02 | UI regression flaky do sleep cố định và selector mong manh | P1 | Tăng retry, giảm niềm tin vào pipeline |
| TD-03 | Test data đơn hàng dùng chung giữa worker | P1 | Chạy song song không ổn định |
| TD-04 | Thiếu kiểm thử tương thích trên nhóm trình duyệt được hỗ trợ | P2 | Có nguy cơ lỗi giao diện ở một số người dùng |
| TD-05 | Tài liệu test và owner của báo cáo đối soát chưa rõ | P2 | Chậm điều tra khi có thay đổi |

Một kế hoạch theo quý có thể như sau:

| Thời gian | Mục tiêu | Công việc | Tiêu chí kết quả |
|---|---|---|---|
| Tuần 1–2 | Giảm rủi ro thanh toán tức thời | Thêm kiểm tra idempotency, retry, số giao dịch và đối soát; review oracle với nghiệp vụ | Có bằng chứng cho các tình huống ưu tiên; rủi ro còn lại được ghi nhận |
| Tuần 3–4 | Ổn định pipeline UI | Thay sleep bằng chờ điều kiện, cải thiện selector, phân loại flaky và xử lý nguyên nhân | Flaky rate giảm theo ngưỡng đã thống nhất, attempt đầu được lưu |
| Tháng 2 | Cô lập test data | Dùng testRunId, namespace theo worker, cleanup và kiểm tra chạy song song | Không còn tranh chấp dữ liệu trong bộ kiểm thử mục tiêu |
| Tháng 2–3 | Khôi phục bằng chứng tương thích | Chọn tổ hợp trình duyệt theo dữ liệu hỗ trợ, thêm smoke và regression phù hợp | Các tổ hợp ưu tiên có kết quả và liên kết phạm vi |
| Tháng 3 | Củng cố vận hành | Bổ sung tài liệu, owner, dashboard và quy trình review nợ | Mỗi khoản nợ đang mở có owner, trạng thái và ngày rà soát |

Lộ trình này xử lý rủi ro nghiêm trọng trước, sau đó cải thiện độ ổn định và khả năng vận hành. Nhóm cần đo baseline trước khi bắt đầu và so sánh sau mỗi giai đoạn. Nếu có incident thanh toán mới, thứ tự ưu tiên cần được xem xét lại ngay thay vì chờ hết quý.

## 17. Ví dụ tính toán và theo dõi lợi ích

Giả sử một bộ hồi quy thủ công cho luồng hoàn tiền cần 3 người, mỗi người mất 2 giờ trước mỗi lần phát hành. Với 3 lần phát hành mỗi tháng, công việc lặp lại là:

\[
3 \text{ người} \times 2 \text{ giờ} \times 3 \text{ lần} = 18 \text{ giờ/tháng}
\]

Nhóm ước lượng tự động hóa phần kiểm tra dữ liệu và API mất 5 ngày công ban đầu, sau đó 3 giờ bảo trì mỗi tháng. Có thể so sánh effort đầu tư với thời gian tiết kiệm trong nhiều tháng, đồng thời tính thêm giá trị phát hiện lỗi sớm và giảm thao tác sai.

Tuy nhiên, không nên kết luận rằng tự động hóa toàn bộ UI là lựa chọn tốt nhất. Có thể kiểm tra quy tắc hoàn tiền ở API và unit level, còn đánh giá trải nghiệm người dùng vẫn cần kiểm tra thủ công ở một số trường hợp. Kế hoạch xử lý nợ cần chỉ rõ phần nào được tự động hóa, phần nào được duy trì thủ công và rủi ro nào còn lại.

## 18. Duy trì phòng ngừa nợ mới

Sau khi giảm nợ hiện tại, nhóm cần ngăn các nguyên nhân cũ tái xuất hiện.

Các cơ chế phòng ngừa:

- Review test cùng với review mã và yêu cầu.
- Có tiêu chuẩn cho tên test, assertion, dữ liệu, setup/cleanup và báo cáo.
- Định nghĩa ownership cho suite, framework, môi trường và dữ liệu.
- Theo dõi feedback time, flaky rate và test bị quarantine.
- Định kỳ rà soát test lỗi thời, trùng lặp và không còn gắn với rủi ro.
- Đưa kiểm tra chất lượng test vào CI khi có thể.
- Đào tạo nhóm về test design, oracle, isolation và diagnosis.
- Ghi nhận quyết định trì hoãn kiểm thử trong risk/debt register.
- Đưa thời gian bảo trì vào kế hoạch thay đổi và release.

Một nhóm trưởng thành không nhất thiết có zero test debt. Họ biết khoản nợ nào đang tồn tại, vì sao chấp nhận, tác động là gì và khi nào sẽ xem xét lại.

## 19. Những sai lầm thường gặp

- **Đồng nhất nợ kiểm thử với thiếu automation:** Bỏ qua flaky test, oracle yếu, dữ liệu và môi trường khó bảo trì.
- **Chỉ ghi số lượng khoản nợ:** Không đánh giá rủi ro, tuổi nợ, chi phí trì hoãn hoặc chủ sở hữu.
- **Ưu tiên khoản dễ làm thay vì khoản quan trọng:** Làm đẹp dashboard nhưng không giảm rủi ro sản phẩm.
- **Không có thời gian xử lý dài hạn:** Nợ luôn thua tính năng mới và tiếp tục tích lũy.
- **Dùng retry để che flaky test:** Tỷ lệ pass cuối tăng nhưng tín hiệu ban đầu bị mất.
- **Xóa test không ổn định mà không thay thế bằng chứng:** Làm giảm độ bao phủ rủi ro.
- **Coi test pass là đã xóa nợ:** Không kiểm tra chất lượng oracle, phạm vi và khả năng duy trì.
- **Không ghi nợ phát sinh từ quyết định phát hành:** Không ai biết vì sao kiểm thử bị hoãn.
- **Chấp nhận nợ vô thời hạn:** Rủi ro không được rà soát và có thể trở thành bình thường mới.
- **Không đo baseline:** Không thể biết kế hoạch có thực sự cải thiện hay không.
- **Tối ưu tốc độ bằng cách giảm kiểm thử quan trọng:** Thời gian ngắn hơn nhưng bằng chứng yếu hơn.
- **Không xử lý nguyên nhân gốc:** Cùng loại nợ tái xuất hiện sau mỗi sprint.

## 20. Checklist quản lý nợ kiểm thử và kế hoạch dài hạn

Trước khi phê duyệt kế hoạch, nhóm có thể sử dụng checklist sau:

- [ ] Nợ kiểm thử được định nghĩa và phân biệt với defect, technical debt và công việc đang chờ.
- [ ] Các loại nợ về bao phủ, độ ổn định, tốc độ, dữ liệu, môi trường, oracle và bảo trì đã được xem xét.
- [ ] Mỗi khoản nợ có mô tả cụ thể, nguyên nhân và bằng chứng.
- [ ] Rủi ro sản phẩm và chi phí trì hoãn được đánh giá.
- [ ] Khoản nợ có ID, chủ sở hữu, mức ưu tiên và ngày rà soát.
- [ ] Có tiêu chí hoàn thành và bằng chứng cần thu thập.
- [ ] Kế hoạch xử lý phân giai đoạn theo rủi ro và phụ thuộc.
- [ ] Có năng lực hoặc ngân sách dành cho giảm nợ trong các chu kỳ tiếp theo.
- [ ] Kế hoạch cân bằng nợ cũ với việc ngăn nợ mới.
- [ ] Ngoại lệ được chấp nhận đúng thẩm quyền, có biện pháp bù đắp và thời hạn.
- [ ] Có baseline và chỉ số theo dõi sau cải tiến.
- [ ] Không đánh đổi phạm vi rủi ro bắt buộc chỉ để giảm thời gian chạy.
- [ ] Test bị xóa, thay thế hoặc cách ly có đánh giá tác động và lưu lý do.
- [ ] Kết quả được rà soát định kỳ và cập nhật khi sản phẩm thay đổi.

Quản lý nợ kiểm thử và lập kế hoạch xử lý dài hạn giúp nhóm duy trì khả năng xác minh sản phẩm khi tốc độ thay đổi tăng lên. Khi khoản nợ được mô tả bằng bằng chứng, ưu tiên theo rủi ro và chi phí trì hoãn, gắn với người sở hữu cùng tiêu chí hoàn thành, nhóm có thể giảm dần chi phí bảo trì, cải thiện thời gian phản hồi và giữ được độ tin cậy của quyết định chất lượng qua nhiều chu kỳ phát triển.
