# Kiểm thử dựa trên rủi ro và lịch sử lỗi

Trong một sản phẩm có nhiều chức năng, tích hợp và môi trường triển khai, nhóm hiếm khi có đủ thời gian để kiểm tra mọi thứ với cùng độ sâu. Kiểm thử dựa trên rủi ro giúp nhóm phân bổ công sức vào những khu vực mà lỗi có khả năng xảy ra hoặc gây hậu quả lớn. Lịch sử lỗi bổ sung bằng chứng thực tế: nó cho biết những loại sai sót nào đã từng xuất hiện, ở đâu, trong điều kiện nào và vì sao các kiểm soát trước đó không phát hiện được.

Kết hợp hai nguồn này giúp xây dựng một cách tiếp cận kiểm thử có căn cứ. Rủi ro dự báo nơi có thể xảy ra vấn đề; lịch sử lỗi cho thấy những điểm yếu đã bộc lộ trong thực tế. Nhóm dùng chúng để chọn phạm vi, thứ tự, độ sâu và loại kiểm thử, sau đó cập nhật kế hoạch khi có thay đổi hoặc bằng chứng mới.

## 1. Kiểm thử dựa trên rủi ro là gì?

Kiểm thử dựa trên rủi ro (risk-based testing) là cách lập kế hoạch và thực hiện kiểm thử bằng cách ưu tiên theo mức độ rủi ro của sản phẩm hoặc dự án. Thay vì chia đều thời gian cho mọi chức năng, nhóm xác định những tình huống lỗi có thể ảnh hưởng đến mục tiêu nghiệp vụ và chất lượng, đánh giá mức độ quan trọng, rồi chọn hoạt động kiểm thử tương ứng.

Một rủi ro thường được mô tả bằng ba phần:

- **Nguyên nhân hoặc điều kiện:** điều gì khiến lỗi có thể xuất hiện?
- **Sự kiện không mong muốn:** hệ thống có thể hoạt động sai như thế nào?
- **Hậu quả:** ai hoặc điều gì chịu ảnh hưởng nếu sự kiện xảy ra?

Ví dụ: “Do yêu cầu thanh toán có thể được gửi lại khi mạng bị gián đoạn, một giao dịch có thể được xử lý hai lần, khiến khách hàng bị trừ tiền trùng và phát sinh công việc đối soát.” Từ mô tả này, nhóm có thể chọn kiểm thử retry, xử lý đồng thời, mã định danh idempotency, webhook trùng và đối soát.

Kiểm thử dựa trên rủi ro không phải là một loại kiểm thử riêng. Đây là nguyên tắc định hướng việc lựa chọn và sắp xếp các loại kiểm thử như unit, component, contract, integration, end-to-end, hiệu năng, bảo mật, khả dụng và thăm dò. Nó cũng không có nghĩa là bỏ qua mọi phần được xếp hạng thấp. Những yêu cầu bắt buộc, kiểm tra nền tảng và phạm vi hồi quy tối thiểu vẫn cần được duy trì.

## 2. Vì sao cần kết hợp rủi ro với lịch sử lỗi?

Phân tích rủi ro giúp nhìn về phía trước nhưng có thể dựa trên giả định chưa được kiểm chứng. Lịch sử lỗi giúp kiểm tra những giả định đó bằng dữ liệu thực tế. Ngược lại, chỉ dựa vào lỗi đã xảy ra có thể khiến nhóm tập trung quá nhiều vào vấn đề cũ và bỏ qua rủi ro mới do tính năng, người dùng hoặc kiến trúc thay đổi.

Hai nguồn bổ sung cho nhau theo các cách sau:

| Nguồn | Câu hỏi chính | Giá trị đối với kế hoạch kiểm thử |
|---|---|---|
| Phân tích rủi ro | Điều gì có thể sai và hậu quả sẽ ra sao? | Nhận diện rủi ro chưa từng xảy ra, ưu tiên theo tác động và khả năng |
| Lịch sử lỗi | Điều gì đã sai, ở đâu và trong điều kiện nào? | Tìm khu vực dễ lỗi, mẫu lỗi lặp lại và khoảng trống của kiểm soát hiện tại |
| Kết hợp cả hai | Rủi ro nào cần kiểm tra sâu hơn dựa trên cả dự báo và bằng chứng? | Phân bổ kiểm thử phù hợp với bối cảnh hiện tại, có thể giải thích và cập nhật |

Ví dụ, một dịch vụ mới xử lý dữ liệu khách hàng có thể chưa có lịch sử lỗi. Phân tích rủi ro vẫn chỉ ra nhu cầu kiểm thử phân quyền, cách ly dữ liệu và xóa dữ liệu. Trong khi đó, lịch sử lỗi của hệ thống cũ có thể cho thấy lỗi thường xuất hiện ở thao tác cập nhật đồng thời hoặc chuyển đổi múi giờ. Nhóm nên xem xét những bài học này khi thiết kế kiểm thử cho dịch vụ mới, đồng thời điều chỉnh cho kiến trúc và luồng dữ liệu mới.

## 3. Xây dựng hồ sơ rủi ro để lập kế hoạch kiểm thử

Trước khi xếp thứ tự kiểm thử, nhóm cần tạo danh sách rủi ro có cấu trúc. Danh sách này có thể bắt đầu từ yêu cầu, câu chuyện người dùng, quy trình nghiệp vụ, sơ đồ kiến trúc, thay đổi kỹ thuật, phản hồi người dùng, sự cố và các giả định chưa được xác minh.

### Mô tả rủi ro theo kịch bản

Mô tả rủi ro cần đủ cụ thể để dẫn đến một hoặc nhiều trường hợp kiểm thử. Tránh những mục quá rộng như “rủi ro bảo mật”, “rủi ro hiệu năng” hoặc “có thể phát sinh lỗi”. Hãy mô tả điều kiện, sự kiện và hậu quả.

Ví dụ:

| Mô tả quá chung | Mô tả có thể hành động |
|---|---|
| Có rủi ro ở chức năng đăng nhập | Khi dịch vụ định danh chậm, người dùng gửi lại yêu cầu nhiều lần và hệ thống có thể tạo nhiều phiên đăng nhập không cần thiết |
| Có rủi ro về dữ liệu | Khi hai nhân viên cập nhật cùng một hồ sơ, thay đổi của người lưu sau có thể ghi đè dữ liệu mới hơn mà không cảnh báo |
| Có rủi ro về hiệu năng | Khi số yêu cầu tra cứu tăng đột biến, truy vấn báo cáo có thể chiếm kết nối cơ sở dữ liệu và làm chậm luồng tạo đơn hàng |
| Có rủi ro tích hợp | Khi nhà cung cấp gửi webhook trễ hoặc trùng, trạng thái giao dịch nội bộ có thể khác trạng thái thanh toán thực tế |

Một hồ sơ rủi ro nên ghi nhận mã, mô tả, nguồn phát hiện, thành phần hoặc quy trình bị ảnh hưởng, mục tiêu chất lượng liên quan, khả năng xảy ra, tác động, kiểm soát hiện có, người phụ trách và trạng thái xử lý. Ghi lại giả định và nguồn bằng chứng để nhóm khác có thể hiểu vì sao rủi ro được đánh giá như vậy.

### Đánh giá khả năng xảy ra

Khả năng xảy ra có thể được ước lượng dựa trên nhiều yếu tố:

- Độ phức tạp của logic và số lượng nhánh điều kiện.
- Số lượng thành phần phụ thuộc, giao thức và điểm tích hợp.
- Mức độ thay đổi gần đây hoặc tần suất thay đổi.
- Tính mới của công nghệ, nhóm triển khai hoặc môi trường.
- Tần suất xuất hiện lỗi tương tự trong lịch sử.
- Mức độ dễ tái hiện các điều kiện kích hoạt lỗi.

Không nên đồng nhất “đã từng xảy ra nhiều lần” với “chắc chắn sẽ xảy ra lại”. Lịch sử chỉ là một phần bằng chứng. Một khu vực đã được tái thiết kế có thể giảm rủi ro cũ; một khu vực chưa từng lỗi có thể vẫn có rủi ro cao nếu mới mở ra đường truy cập nhạy cảm.

### Đánh giá tác động

Tác động nên được xem xét theo hậu quả với người dùng và tổ chức, chẳng hạn:

- Mất hoặc lộ dữ liệu, sai lệch dữ liệu và khả năng phục hồi.
- Gián đoạn dịch vụ, suy giảm hiệu năng hoặc không hoàn thành nghiệp vụ.
- Sai lệch tài chính, doanh thu, tồn kho hoặc báo cáo.
- Vi phạm quyền riêng tư, bảo mật, quy định hoặc hợp đồng.
- Số lượng người dùng, khách hàng hoặc hệ thống phụ thuộc bị ảnh hưởng.
- Chi phí điều tra, khắc phục, hỗ trợ và khôi phục.

Hãy phân biệt tác động trực tiếp và tác động dây chuyền. Ví dụ, một hàng đợi xử lý bị tắc có thể ban đầu chỉ làm chậm thông báo, nhưng nếu các nghiệp vụ tiếp theo chờ thông báo đó thì cuối cùng đơn hàng có thể bị kẹt và nhân viên phải xử lý thủ công.

## 4. Xếp hạng và ưu tiên rủi ro

Một mô hình đơn giản là kết hợp khả năng xảy ra với mức độ tác động:

\[
Risk\ Score = Likelihood \times Impact
\]

Nếu mỗi yếu tố được chấm theo thang 1 đến 5, điểm số giúp so sánh tương đối và hỗ trợ thảo luận. Tuy nhiên, không nên xem điểm số là xác suất chính xác hoặc kết luận tự động. Cùng một điểm tổng có thể đại diện cho những rủi ro rất khác nhau: một lỗi thường gặp nhưng ít ảnh hưởng và một lỗi hiếm nhưng gây mất dữ liệu không thể phục hồi.

Ví dụ về ma trận định tính:

| Khả năng / Tác động | Thấp | Trung bình | Cao | Rất cao |
|---|---|---|---|---|
| Rất cao | Trung bình | Cao | Rất cao | Rất cao |
| Cao | Trung bình | Cao | Cao | Rất cao |
| Trung bình | Thấp | Trung bình | Cao | Cao |
| Thấp | Thấp | Thấp | Trung bình | Cao |

Ngưỡng và cách phân loại cần được thống nhất trong nhóm. Với những rủi ro liên quan đến an toàn, bảo mật, quyền riêng tư, tài chính hoặc nghĩa vụ pháp lý, cần xem xét hậu quả nghiêm trọng và yêu cầu bắt buộc riêng, kể cả khi điểm số thấp.

### Ưu tiên kiểm thử dựa trên nhiều yếu tố

Thứ tự kiểm thử không nhất thiết trùng hoàn toàn với thứ tự điểm rủi ro. Khi quyết định thực hiện trước, nhóm có thể xem xét thêm:

- **Mức độ cấp thiết:** lỗi có thể ảnh hưởng đến bản phát hành hoặc quyết định đang chờ hay không?
- **Khả năng phát hiện:** kiểm thử có thể phát hiện vấn đề sớm và tạo tín hiệu rõ ràng không?
- **Chi phí kiểm thử:** cần bao nhiêu thời gian, môi trường, dữ liệu và chuyên môn?
- **Phụ thuộc:** kiểm thử nào cần chạy trước để kết quả của kiểm thử sau có ý nghĩa?
- **Khả năng giảm rủi ro:** kiểm thử có thể xác nhận một kiểm soát quan trọng hoặc phát hiện một lớp lỗi có tác động lớn không?

Ví dụ, một kiểm thử hợp đồng có thể chạy nhanh và giúp xác nhận tương thích giữa hai dịch vụ trước khi chạy bộ E2E dài. Một kiểm thử phục hồi dữ liệu có thể tốn nhiều thời gian nhưng cần được lên lịch riêng vì hậu quả của mất dữ liệu rất lớn. Kế hoạch tốt cân bằng mức rủi ro, thời gian phản hồi và khả năng thực hiện.

## 5. Thu thập và phân tích lịch sử lỗi

Lịch sử lỗi có thể đến từ hệ thống quản lý lỗi, pull request, báo cáo sự cố, log vận hành, phản hồi khách hàng, kết quả kiểm thử và các lần rollback. Muốn dùng dữ liệu này hiệu quả, nhóm cần ghi nhận nhất quán và có đủ thông tin để liên hệ lỗi với sản phẩm, điều kiện xảy ra và hoạt động kiểm thử.

### Thông tin nên lưu cho mỗi lỗi

Một bản ghi lỗi hữu ích thường có:

- Mã lỗi và mô tả hành vi sai có thể quan sát.
- Ngày phát hiện, ngày xảy ra nếu xác định được và phiên bản liên quan.
- Thành phần, dịch vụ, luồng nghiệp vụ và môi trường bị ảnh hưởng.
- Mức độ nghiêm trọng và mức độ ưu tiên xử lý.
- Điều kiện đầu vào, trạng thái dữ liệu và các bước tái hiện.
- Nguyên nhân gốc hoặc nguyên nhân có khả năng nhất, cùng mức độ chắc chắn.
- Cách lỗi được phát hiện: kiểm thử tự động, kiểm thử thủ công, giám sát hay phản hồi người dùng.
- Vì sao các kiểm soát trước đó không phát hiện lỗi.
- Cách sửa, kiểm thử hồi quy và bằng chứng xác nhận.
- Liên kết đến sự cố, thay đổi mã nguồn hoặc quyết định liên quan.

Không phải lúc nào nguyên nhân gốc cũng được xác định ngay. Hãy phân biệt nguyên nhân đã xác nhận với giả thuyết đang điều tra, tránh biến suy đoán thành dữ liệu thống kê.

### Phân loại lỗi để tìm mẫu

Có thể phân loại theo nhiều chiều, tùy mục đích phân tích:

| Chiều phân loại | Ví dụ |
|---|---|
| Thành phần | Giao diện, API, dịch vụ nghiệp vụ, cơ sở dữ liệu, hạ tầng, tích hợp |
| Loại lỗi | Logic, dữ liệu, đồng thời, bảo mật, hiệu năng, cấu hình, tương thích |
| Giai đoạn phát hiện | Khi lập trình, pull request, tích hợp, trước phát hành, sau phát hành |
| Nguyên nhân | Yêu cầu thiếu, thiết kế sai, triển khai lỗi, cấu hình, dữ liệu, môi trường |
| Cách phát hiện | Unit test, integration test, E2E, thăm dò, monitoring, người dùng báo |
| Mức độ ảnh hưởng | Nhẹ, trung bình, nghiêm trọng, khẩn cấp theo quy ước của nhóm |
| Khả năng tái diễn | Đã có kiểm thử hồi quy, phụ thuộc môi trường, chưa xác định |

Một lỗi có thể thuộc nhiều nhóm. Ví dụ, một lỗi phân quyền ở API có thể vừa là lỗi bảo mật, vừa liên quan đến dữ liệu và quy tắc nghiệp vụ. Hệ thống phân loại cần đủ đơn giản để mọi người sử dụng nhất quán; quá nhiều nhãn sẽ khiến dữ liệu khó nhập và khó phân tích.

### Tìm xu hướng thay vì chỉ đếm tổng số lỗi

Số lượng lỗi đơn lẻ ít có ý nghĩa nếu không xét quy mô thay đổi, số lượng người dùng, thời gian quan sát và mức độ nghiêm trọng. Nhóm nên tìm các xu hướng như:

- Thành phần nào thường phát sinh lỗi nghiêm trọng?
- Loại lỗi nào lặp lại qua nhiều phiên bản?
- Lỗi thường được phát hiện ở giai đoạn nào?
- Kiểm thử nào thường phát hiện lỗi trước khi phát hành?
- Lỗi nào chỉ xuất hiện ở một môi trường hoặc cấu hình?
- Thời gian từ khi phát hiện đến khi khắc phục có xu hướng tăng không?
- Có lỗi nào tái diễn sau khi đã đánh dấu khắc phục?

Ví dụ, số lỗi ở dịch vụ thanh toán tăng sau khi thêm nhà cung cấp mới có thể cho thấy ranh giới tích hợp cần được kiểm tra sâu hơn. Nếu lỗi tập trung ở bước chuyển trạng thái khi webhook đến trễ, nhóm có thể bổ sung kiểm thử thứ tự sự kiện và xử lý đồng thời.

## 6. Các chỉ số lịch sử lỗi hữu ích

Chỉ số nên phục vụ câu hỏi cụ thể và được diễn giải trong bối cảnh. Không nên dùng một chỉ số duy nhất để đánh giá chất lượng nhóm hoặc cá nhân.

| Chỉ số | Ý nghĩa | Cách sử dụng và giới hạn |
|---|---|---|
| Defect density | Số lỗi so với kích thước hoặc phạm vi phần mềm | Có thể giúp so sánh xu hướng trong cùng hệ thống; cách đo kích thước và mức độ phát hiện phải nhất quán |
| Defect leakage / escaped defects | Lỗi được phát hiện sau khi phát hành so với tổng lỗi hoặc tổng lỗi được ghi nhận | Cho thấy khoảng trống phát hiện trước phát hành; cần phân loại mức độ và tác động |
| Defect recurrence | Lỗi cùng loại hoặc cùng nguyên nhân tái diễn | Gợi ý kiểm soát hoặc kiểm thử hồi quy chưa đủ hiệu quả |
| Mean time to detect (MTTD) | Thời gian trung bình để phát hiện sự cố hoặc lỗi sau khi bắt đầu | Giúp đánh giá khả năng phát hiện; cần xác định mốc bắt đầu đáng tin cậy |
| Mean time to repair/recover (MTTR) | Thời gian trung bình để sửa hoặc khôi phục | Phản ánh khả năng điều tra và phục hồi; cần định nghĩa rõ “repair” hay “recovery” |
| Tỷ lệ lỗi được phát hiện trước phát hành | Phần lỗi được phát hiện trong các giai đoạn kiểm thử trước khi đến người dùng | Có thể theo dõi hiệu quả phát hiện, nhưng phụ thuộc chất lượng ghi nhận lỗi |
| Tỷ lệ lỗi chập chờn trong kiểm thử | Kết quả kiểm thử không ổn định khi điều kiện không đổi | Cho biết độ tin cậy của tín hiệu kiểm thử và công sức chạy lại |

### Cẩn trọng khi diễn giải chỉ số

Defect density có thể bị hiểu sai nếu nhóm A ghi nhận lỗi chi tiết hơn nhóm B hoặc một mô-đun có nhiều thay đổi hơn. Defect leakage có thể tăng khi sản phẩm được sử dụng rộng hơn, dù chất lượng mã không giảm. MTTR có thể bị kéo dài bởi thời gian chờ nhà cung cấp hoặc phê duyệt, không chỉ bởi năng lực kỹ thuật.

Do đó, hãy xem xu hướng theo thời gian, theo thành phần và theo mức độ nghiêm trọng. Ghi rõ mẫu số, phạm vi, khoảng thời gian và cách xử lý lỗi trùng. Dùng chỉ số để tìm nơi cần điều tra, không dùng chúng để tạo áp lực khiến nhóm giảm ghi nhận lỗi hoặc hạ mức độ nghiêm trọng.

## 7. Chuyển lịch sử lỗi thành hoạt động kiểm thử

Lịch sử lỗi chỉ có ích khi dẫn đến thay đổi trong cách kiểm thử hoặc kiểm soát. Với mỗi lỗi đáng chú ý, nhóm nên hỏi: lỗi xuất phát từ đâu, vì sao không được phát hiện sớm hơn, kiểm thử nào có thể tái hiện nó và kiểm thử đó nên chạy ở giai đoạn nào?

### Phân tích nguyên nhân và khoảng trống phát hiện

Một quy trình phân tích đơn giản gồm:

1. Tái hiện lỗi bằng dữ liệu và điều kiện gần với lúc lỗi xảy ra.
2. Xác định nguyên nhân ở mức hành vi, thiết kế, dữ liệu, cấu hình hoặc môi trường.
3. Xác định kiểm soát nào lẽ ra có thể ngăn chặn hoặc phát hiện lỗi.
4. Giải thích vì sao kiểm soát đó không hoạt động hoặc chưa tồn tại.
5. Chọn tầng kiểm thử có thể tái hiện nguyên nhân với độ tin cậy cao.
6. Xác định kiểm thử hồi quy cần chạy khi thay đổi liên quan xuất hiện.
7. Theo dõi lỗi có tái diễn và kiểm thử mới có tạo tín hiệu ổn định không.

Không nên chỉ thêm một kiểm thử xác nhận đúng ví dụ đã xảy ra. Hãy xem xét lớp trường hợp cùng nguyên nhân. Nếu lỗi do so sánh thời gian sai ở ranh giới ngày, kiểm thử cần bao gồm trước, đúng tại và sau thời điểm biên, các múi giờ liên quan và điều kiện dữ liệu tương ứng.

### Chọn nơi đặt kiểm thử hồi quy

Đặt kiểm thử ở tầng thấp nhất có thể xác nhận nguyên nhân. Nếu lỗi nằm trong một hàm tính toán thuần, unit test thường cho phản hồi nhanh và định vị tốt. Nếu lỗi phụ thuộc giao tiếp giữa hai dịch vụ, contract hoặc integration test có thể phù hợp. Nếu lỗi chỉ xuất hiện qua luồng người dùng và nhiều thành phần, cần thêm kịch bản E2E có chọn lọc.

Có thể cần kiểm thử ở nhiều tầng khi mỗi tầng bảo vệ một khía cạnh khác nhau. Ví dụ, unit test xác nhận quy tắc chuyển trạng thái; integration test xác nhận giao dịch dữ liệu; E2E xác nhận người dùng nhận đúng trạng thái sau khi thanh toán. Tránh nhân bản cùng một kiểm tra ở mọi tầng nếu không có lý do rõ ràng.

### Quản lý lỗi tái diễn và kiểm thử chập chờn

Lỗi tái diễn có thể cho thấy bản sửa chỉ xử lý triệu chứng, kiểm thử hồi quy chưa bao phủ điều kiện kích hoạt hoặc một đường mã khác vẫn có cùng vấn đề. Cần liên kết lỗi mới với lỗi cũ, xem lại giả thuyết nguyên nhân và cập nhật kiểm thử tương ứng.

Kiểm thử chập chờn (flaky test) cũng làm sai lệch dữ liệu lịch sử. Nếu nhóm ghi mọi lần thất bại như một lỗi sản phẩm, số liệu lỗi sẽ bị phóng đại; nếu tự động bỏ qua mọi thất bại sau khi chạy lại thành công, nhóm có thể che mất lỗi không ổn định. Nên ghi nhận lần chạy đầu, số lần chạy lại, điều kiện môi trường và kết quả cuối cùng để phân loại chính xác.

## 8. Lập kế hoạch kiểm thử theo mức rủi ro

Sau khi đánh giá rủi ro và phân tích lịch sử lỗi, nhóm chuyển kết quả thành kế hoạch thực thi. Kế hoạch cần thể hiện phạm vi, mức độ ưu tiên, loại kiểm thử, thời điểm chạy, dữ liệu, môi trường và người chịu trách nhiệm.

### Ma trận rủi ro và hoạt động kiểm thử

Ví dụ minh họa cho một hệ thống đặt hàng:

| Rủi ro | Bằng chứng lịch sử | Ưu tiên | Hoạt động kiểm thử | Thời điểm |
|---|---|---|---|---|
| Thanh toán trùng khi retry | Đã từng xảy ra timeout sau khi nhà cung cấp thu tiền | Rất cao | Unit cho idempotency; integration cho retry/webhook; E2E cho luồng thanh toán | Pull request và trước phát hành |
| Sai tổng tiền khi áp dụng nhiều ưu đãi | Lỗi làm tròn và điều kiện giảm giá từng xuất hiện | Cao | Unit theo bảng quyết định; integration với dữ liệu đơn hàng | Mỗi thay đổi nghiệp vụ |
| Dữ liệu khách hàng bị truy cập chéo | Có thay đổi mô hình phân quyền | Rất cao | Kiểm thử API âm tính, kiểm thử cách ly tenant, rà soát bảo mật | Mỗi thay đổi quyền và trước phát hành |
| Trang tra cứu chậm khi tải tăng | P95 tăng ở giờ cao điểm | Cao | Kiểm thử tải, truy vấn cơ sở dữ liệu và theo dõi hiệu năng | Theo lịch và trước phát hành lớn |
| Webhook đến trễ làm kẹt đơn | Có sự cố xử lý thông báo không đúng thứ tự | Cao | Integration cho sự kiện trễ, trùng và sai thứ tự; đối soát | Pull request liên quan và bộ hồi quy tích hợp |
| Lỗi hiển thị ở trình duyệt ít phổ biến | Phản hồi hỗ trợ từ một nhóm thiết bị | Trung bình | Kiểm thử tương thích theo ma trận thiết bị được hỗ trợ | Trước phát hành giao diện |

Ma trận này giúp nhóm thấy vì sao một kiểm thử được ưu tiên và bằng chứng nào hỗ trợ quyết định. Mức ưu tiên cần được cập nhật khi có bản sửa kiến trúc, thay đổi nhà cung cấp hoặc dữ liệu mới.

### Phân bổ theo vòng phản hồi

Không phải mọi kiểm thử rủi ro cao đều chạy trong cùng một thời điểm. Một số kiểm tra có thể chạy nhanh ở mỗi pull request; một số cần môi trường chuyên biệt hoặc dữ liệu lớn và nên chạy theo lịch hay trước phát hành.

| Vòng kiểm thử | Nội dung thường phù hợp | Mục đích |
|---|---|---|
| Khi phát triển | Unit, component, kiểm tra kiểu và các trường hợp biên quan trọng | Phát hiện lỗi gần nơi thay đổi được tạo ra |
| Pull request | Unit, contract, integration nhanh và kiểm tra bảo mật trọng yếu | Cung cấp cổng phản hồi đáng tin cậy trước khi hợp nhất |
| Sau hợp nhất | Integration rộng, E2E cốt lõi và hồi quy các khu vực rủi ro cao | Xác nhận tương tác giữa các thành phần |
| Theo lịch hoặc trước phát hành | Kiểm thử tải, sức chịu đựng, phục hồi, tương thích và bảo mật chuyên sâu | Kiểm chứng thuộc tính cần môi trường hoặc thời gian riêng |
| Sau phát hành | Monitoring, synthetic test, đối soát và kiểm tra dữ liệu | Phát hiện rủi ro chỉ xuất hiện trong vận hành thực tế |

Khi một lỗi nghiêm trọng được phát hiện, nhóm có thể tạm thời tăng độ sâu kiểm thử ở khu vực liên quan cho đến khi nguyên nhân được xử lý và kiểm soát được xác nhận. Khi một tính năng ít rủi ro thay đổi, nhóm có thể dùng phạm vi hồi quy phù hợp thay vì chạy toàn bộ bộ kiểm thử dài ở mọi lần thay đổi. Mọi quyết định thu hẹp phạm vi cần có căn cứ và không được bỏ qua yêu cầu bắt buộc.

### Chọn dữ liệu và môi trường kiểm thử

Rủi ro có thể không xuất hiện nếu dữ liệu hoặc môi trường kiểm thử quá đơn giản. Hãy chuẩn bị dữ liệu đại diện cho điều kiện kích hoạt: số lượng bản ghi lớn, dữ liệu biên, trạng thái không đồng nhất, yêu cầu trùng, múi giờ khác nhau hoặc vai trò người dùng khác nhau.

Môi trường cần đủ giống môi trường đích ở những khía cạnh liên quan đến rủi ro. Ví dụ, kiểm thử hiệu năng trên cơ sở dữ liệu nhỏ và không có dữ liệu cạnh tranh không thể đại diện cho giờ cao điểm. Kiểm thử tích hợp với một stub đơn giản không xác nhận được hành vi retry hoặc webhook thực tế của nhà cung cấp. Khi không thể dùng môi trường thật, hãy mô phỏng có chủ đích và ghi rõ giới hạn của bằng chứng.

## 9. Ví dụ thực hành: dùng lịch sử lỗi để điều chỉnh chiến lược kiểm thử

Giả sử trong ba phiên bản gần đây, nhóm phát hiện các lỗi sau ở hệ thống quản lý đơn hàng:

| Mã lỗi | Mô tả | Nơi phát hiện | Nguyên nhân được xác nhận |
|---|---|---|---|
| D-101 | Đơn hàng bị tạo hai lần khi người dùng gửi lại | Sau phát hành | API không kiểm tra mã yêu cầu duy nhất |
| D-102 | Tổng tiền sai khi giảm giá kết hợp thuế | Pull request | Thứ tự áp dụng quy tắc làm tròn không đúng |
| D-103 | Đơn hàng không cập nhật sau thanh toán | Vận hành | Webhook đến trễ và bị xử lý sai trạng thái |
| D-104 | Báo cáo chậm khi dữ liệu tăng | Monitoring | Truy vấn thiếu chỉ mục và cạnh tranh tài nguyên |
| D-105 | Người dùng thấy dữ liệu của tổ chức khác | Sau phát hành | Một API thiếu điều kiện lọc theo tổ chức |

Nhóm không chỉ đếm năm lỗi mà phân tích mẫu:

- D-101 và D-103 cùng liên quan đến xử lý bất đồng bộ, retry và tính nhất quán trạng thái.
- D-102 cho thấy quy tắc tính toán có nhiều điều kiện kết hợp và cần kiểm thử bảng quyết định.
- D-104 cho thấy hiệu năng phụ thuộc vào quy mô dữ liệu và kế hoạch truy vấn.
- D-105 là lỗi bảo mật nghiêm trọng; cần xem xét toàn bộ các điểm truy cập dữ liệu, không chỉ API đã sửa.

Từ đó, kế hoạch được điều chỉnh:

1. Thêm unit test cho quy tắc tính tiền và các trường hợp làm tròn ở ranh giới.
2. Thêm integration test cho webhook trễ, trùng, sai thứ tự và retry sau timeout.
3. Bổ sung kiểm thử cách ly dữ liệu theo tổ chức cho toàn bộ API đọc và ghi dữ liệu khách hàng.
4. Thiết lập kiểm thử tải với tập dữ liệu gần quy mô dự kiến, đồng thời theo dõi P95 và tài nguyên cơ sở dữ liệu.
5. Thêm kịch bản E2E cốt lõi cho luồng thanh toán và trạng thái đơn hàng.
6. Đưa các lỗi nghiêm trọng đã xảy ra vào danh mục hồi quy và liên kết chúng với các thay đổi có thể ảnh hưởng.

Khi có phiên bản mới, nhóm theo dõi xem lỗi cùng loại có tái diễn không, kiểm thử mới có phát hiện lỗi sớm không và thời gian phản hồi có làm chậm quy trình không. Nếu dữ liệu cho thấy một nhóm kiểm thử quá chậm hoặc không ổn định, nhóm điều tra nguyên nhân và tối ưu cách thực hiện mà vẫn giữ bằng chứng cần thiết.

## 10. Cập nhật ưu tiên khi sản phẩm thay đổi

Điểm rủi ro không cố định. Một rủi ro có thể tăng khi số người dùng tăng, mở thêm API, thay đổi quy trình nghiệp vụ hoặc chuyển sang kiến trúc phân tán. Nó cũng có thể giảm khi một biện pháp kiểm soát được triển khai và xác nhận hiệu quả.

Nhóm nên rà soát danh sách rủi ro và kế hoạch kiểm thử khi:

- Có tính năng mới, thay đổi yêu cầu hoặc thay đổi nhóm người dùng.
- Có thay đổi lớn về kiến trúc, cơ sở dữ liệu, nhà cung cấp hoặc môi trường.
- Có sự cố nghiêm trọng, lỗi lọt ra sản xuất hoặc lỗi cũ tái diễn.
- Chỉ số vận hành hoặc xu hướng lỗi thay đổi đáng kể.
- Một kiểm soát quan trọng được thêm, loại bỏ hoặc thay thế.
- Phạm vi phát hành, thời gian hoặc nguồn lực thay đổi.

Mỗi lần rà soát nên ghi rõ rủi ro nào tăng, giảm, mới xuất hiện hoặc không còn phù hợp; lý do và bằng chứng; kiểm thử nào cần thêm, sửa, chuyển thời điểm hoặc loại bỏ; ai chịu trách nhiệm và khi nào đánh giá lại. Điều này giúp kế hoạch phản ánh trạng thái hiện tại thay vì giữ nguyên ưu tiên từ đầu dự án.

## 11. Các sai lầm cần tránh

- **Chấm điểm rủi ro chỉ để hoàn thành biểu mẫu:** điểm số cần có căn cứ và phải dẫn đến quyết định kiểm thử hoặc kiểm soát cụ thể.
- **Chỉ nhìn vào số lượng lỗi:** một lỗi bảo mật nghiêm trọng có thể quan trọng hơn nhiều lỗi giao diện nhỏ; cần xét mức độ tác động và phạm vi.
- **Cho rằng khu vực chưa từng lỗi là an toàn:** thiếu dữ liệu lịch sử không đồng nghĩa với rủi ro thấp, đặc biệt ở tính năng mới hoặc ranh giới tin cậy mới.
- **Chỉ kiểm thử lỗi đã từng xảy ra:** lịch sử lỗi cần bổ sung cho phân tích dự báo, không thay thế việc tìm rủi ro mới.
- **Dùng dữ liệu lịch sử thiếu nhất quán:** nhãn, mức độ nghiêm trọng và cách ghi nhận khác nhau làm sai kết quả phân tích.
- **Chỉ thêm kiểm thử đúng ví dụ cũ:** cần tìm lớp điều kiện và nguyên nhân chung để tránh lỗi biến thể tái diễn.
- **Đưa mọi kiểm thử rủi ro cao vào cổng pull request:** kiểm thử tải lớn hoặc phục hồi có thể cần môi trường và thời gian riêng; hãy bố trí vòng chạy phù hợp.
- **Bỏ qua kiểm thử vì điểm rủi ro thấp:** yêu cầu bắt buộc và các kiểm tra nền tảng vẫn cần thực hiện.
- **Đóng rủi ro ngay khi kiểm thử xanh một lần:** cần xem xét tính ổn định, phạm vi bằng chứng và rủi ro còn lại.
- **Dùng chỉ số để đánh giá cá nhân:** điều này có thể khiến nhóm ngại báo cáo lỗi hoặc làm sai lệch dữ liệu.

## 12. Danh sách kiểm tra khi lập kế hoạch

Trước khi chốt kế hoạch kiểm thử cho một tính năng hoặc bản phát hành, nhóm có thể rà soát:

**Hồ sơ rủi ro**

- Các kịch bản lỗi có mô tả nguyên nhân, sự kiện và hậu quả rõ ràng không?
- Rủi ro đã được đánh giá theo khả năng, tác động và nghĩa vụ bắt buộc chưa?
- Có ghi nguồn bằng chứng, giả định và người chịu trách nhiệm không?
- Rủi ro còn lại sau kiểm soát đã được xem xét chưa?

**Lịch sử lỗi**

- Các lỗi nghiêm trọng và lỗi tái diễn trong khu vực liên quan đã được xem xét chưa?
- Có mẫu lỗi theo thành phần, loại lỗi, môi trường hoặc giai đoạn phát hiện không?
- Các sự cố và near miss có được chuyển thành kiểm thử hồi quy hoặc biện pháp kiểm soát không?
- Dữ liệu lỗi có đủ nhất quán để so sánh xu hướng không?

**Kế hoạch kiểm thử**

- Mỗi rủi ro quan trọng có hoạt động kiểm chứng và bằng chứng mong đợi không?
- Tầng kiểm thử và thời điểm chạy có phù hợp với rủi ro và thời gian phản hồi không?
- Dữ liệu, môi trường và phụ thuộc đã đại diện cho điều kiện kích hoạt chưa?
- Có kiểm thử hồi quy cho nguyên nhân lỗi cũ và các biến thể quan trọng không?
- Có người sở hữu, tiêu chí hoàn thành và cách xử lý khi kiểm thử thất bại không?

**Theo dõi sau kiểm thử và phát hành**

- Kết quả kiểm thử có được liên kết với rủi ro và phiên bản không?
- Có theo dõi lỗi lọt, lỗi tái diễn và kiểm thử chập chờn không?
- Có điều kiện kích hoạt rà soát lại khi bối cảnh hoặc bằng chứng thay đổi không?

## Kết luận

Kiểm thử dựa trên rủi ro giúp nhóm tập trung vào những tình huống có khả năng hoặc hậu quả đáng kể. Lịch sử lỗi làm cho quyết định đó sát với thực tế hơn bằng cách chỉ ra các mẫu sai sót, khu vực dễ lỗi và khoảng trống phát hiện. Khi hồ sơ rủi ro, dữ liệu lỗi, kế hoạch kiểm thử và bằng chứng được liên kết, nhóm có thể giải thích vì sao một kiểm thử được ưu tiên, cập nhật phạm vi khi bối cảnh thay đổi và cải thiện khả năng phát hiện lỗi qua từng phiên bản.
