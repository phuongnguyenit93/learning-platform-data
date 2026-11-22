# Xác định người sở hữu và ngân sách bảo trì bộ kiểm thử

Bộ kiểm thử tự động cần được duy trì trong suốt vòng đời sản phẩm. Khi yêu cầu thay đổi, giao diện được thiết kế lại, API được nâng cấp, dữ liệu thử nghiệm tăng lên hoặc môi trường CI thay đổi, các kiểm thử có thể lỗi thời, chạy chậm hoặc trở nên không ổn định. Nếu không có người chịu trách nhiệm và năng lực dành riêng cho công việc này, bộ kiểm thử dần mất độ tin cậy và nhóm có thể bắt đầu bỏ qua kết quả của nó.

Xác định người sở hữu và ngân sách bảo trì là hai quyết định gắn liền với nhau. Người sở hữu bảo đảm bộ kiểm thử có mục tiêu, chất lượng và vòng đời rõ ràng. Ngân sách bảo trì cung cấp thời gian, công cụ, hạ tầng và năng lực cần thiết để thực hiện trách nhiệm đó.

Một mô hình phù hợp cần trả lời được: ai chịu trách nhiệm cuối cùng cho từng bộ kiểm thử, ai sửa khi test thất bại, ai duy trì dữ liệu và môi trường, công việc bảo trì được đưa vào kế hoạch như thế nào, chi phí nào cần được dự trù và dấu hiệu nào cho thấy ngân sách hiện tại không còn đủ.

## 1. Vì sao bộ kiểm thử cần người sở hữu?

Một kiểm thử tự động không tự duy trì sau khi được viết. Nó có thể phụ thuộc vào mã ứng dụng, hợp đồng API, cơ sở dữ liệu, tài khoản, dữ liệu, trình duyệt, thư viện, container, dịch vụ bên ngoài và pipeline. Khi một phụ thuộc thay đổi, kiểm thử có thể thất bại dù hành vi sản phẩm vẫn đúng, hoặc tiếp tục đạt trong khi không còn xác minh rủi ro ban đầu.

Nếu không có chủ sở hữu, các tình huống sau thường xuất hiện:

- Kiểm thử thất bại nhiều lần nhưng không ai điều tra.
- Test bị tắt để pipeline chạy tiếp và không được bật lại.
- Dữ liệu dùng chung bị thay đổi, làm các lần chạy không ổn định.
- Một thay đổi API làm nhiều bộ kiểm thử hỏng nhưng các nhóm đổ trách nhiệm cho nhau.
- Kiểm thử chậm dần mà không ai xem xét thời gian chạy.
- Thư viện hoặc công cụ lỗi thời không được nâng cấp.
- Test không còn phù hợp với sản phẩm nhưng vẫn nằm trong pipeline.
- Không rõ ai quyết định giữ, sửa, thay thế hoặc xóa kiểm thử.

Chủ sở hữu giúp bộ kiểm thử luôn gắn với một mục tiêu chất lượng và có người theo dõi kết quả. Trách nhiệm này không có nghĩa một cá nhân phải tự viết và sửa mọi test. Nó có nghĩa có một đầu mối chịu trách nhiệm bảo đảm các hoạt động cần thiết được thực hiện và các bên liên quan phối hợp với nhau.

## 2. Phân biệt quyền sở hữu bộ kiểm thử và trách nhiệm chất lượng sản phẩm

Chủ sở hữu mã kiểm thử và chủ sở hữu chất lượng của tính năng có thể là cùng một nhóm, nhưng hai trách nhiệm cần được hiểu rõ.

**Chủ sở hữu sản phẩm hoặc thành phần** chịu trách nhiệm về hành vi, quy tắc và rủi ro của phần sản phẩm đó. Họ cần bảo đảm các yêu cầu quan trọng được kiểm chứng và kết quả thất bại được xử lý.

**Chủ sở hữu bộ kiểm thử** chịu trách nhiệm về cấu trúc, khả năng chạy, tính ổn định, dữ liệu, tài liệu và bảo trì của một nhóm kiểm thử cụ thể.

**Chủ sở hữu nền tảng kiểm thử** duy trì công cụ, runner, pipeline, môi trường dùng chung, thư viện nền tảng và cơ chế báo cáo.

Một nhóm có thể đảm nhận cả ba vai trò trong sản phẩm nhỏ. Với hệ thống nhiều nhóm, trách nhiệm nên được chia theo phạm vi và có đầu mối điều phối.

Ví dụ, nhóm thanh toán sở hữu hành vi thanh toán và các kiểm thử nghiệp vụ của dịch vụ. Nhóm nền tảng kiểm thử sở hữu runner và thư viện khởi tạo môi trường. Nhóm kiểm thử hoặc chất lượng hỗ trợ đánh giá chiến lược, theo dõi độ tin cậy và phát hiện khoảng trống. Khi một kiểm thử tích hợp thanh toán thất bại, các bên cần phối hợp xác định lỗi thuộc sản phẩm, hợp đồng, môi trường hay chính test.

## 3. Chọn mô hình sở hữu phù hợp

Không có một mô hình sở hữu duy nhất phù hợp với mọi tổ chức. Cần chọn dựa trên kiến trúc, quy mô nhóm, mức độ dùng chung của bộ kiểm thử và năng lực chuyên môn.

### Sở hữu theo nhóm sản phẩm hoặc thành phần

Mỗi nhóm sở hữu mã sản phẩm cũng sở hữu các kiểm thử liên quan đến thành phần và hành vi của mình.

Ưu điểm:

- Người hiểu sản phẩm trực tiếp duy trì kiểm thử.
- Thay đổi mã và kiểm thử có thể được thực hiện cùng nhau.
- Lỗi được xử lý gần nơi phát sinh.
- Trách nhiệm không bị tách khỏi công việc phát triển.

Điểm cần quản lý là sự khác biệt về kỹ năng, tiêu chuẩn và cách tổ chức giữa các nhóm. Tổ chức cần có quy ước chung và hỗ trợ kỹ thuật khi nhóm gặp vấn đề về framework hoặc hạ tầng.

### Sở hữu tập trung bởi nhóm kiểm thử hoặc tự động hóa

Một nhóm chuyên trách xây dựng và duy trì phần lớn bộ kiểm thử tự động.

Ưu điểm:

- Có chuyên môn tập trung về công cụ và thiết kế kiểm thử.
- Dễ chuẩn hóa framework, báo cáo và quy trình.
- Có thể tối ưu hạ tầng dùng chung.

Rủi ro là nhóm chuyên trách trở thành nút thắt, phải chạy theo thay đổi của nhiều nhóm và thiếu kiến thức chi tiết về hành vi nghiệp vụ. Nếu áp dụng mô hình này, nhóm sản phẩm vẫn cần tham gia xác nhận quy tắc, điều tra lỗi và duy trì các kiểm thử sát với mã của mình.

### Sở hữu liên kết hoặc mô hình lai

Nhóm sản phẩm sở hữu kiểm thử của thành phần và luồng nghiệp vụ; nhóm nền tảng hoặc tự động hóa sở hữu công cụ và hạ tầng dùng chung; nhóm chất lượng hỗ trợ tiêu chuẩn, đánh giá và điều phối.

Mô hình này thường phù hợp với hệ thống nhiều nhóm. Nó cần ranh giới trách nhiệm rõ để tránh tình trạng mỗi bên cho rằng bên còn lại sẽ sửa.

### Sở hữu theo rủi ro và tầng kiểm thử

Có thể phân công khác nhau theo tầng:

| Phạm vi | Chủ sở hữu chính gợi ý | Bên phối hợp |
|---|---|---|
| Kiểm thử đơn vị và thành phần | Nhóm sở hữu mã nguồn | Kỹ sư kiểm thử hoặc chất lượng |
| Kiểm thử hợp đồng | Provider và consumer theo hợp đồng | Nhóm tích hợp |
| Kiểm thử tích hợp | Nhóm sở hữu luồng hoặc các thành phần liên quan | Nền tảng, QA |
| Kiểm thử hệ thống và E2E | Nhóm sở hữu hành trình hoặc nhóm kiểm thử được chỉ định | Các nhóm dịch vụ, sản phẩm |
| Kiểm thử hiệu năng và bảo mật chuyên biệt | Nhóm chuyên môn phù hợp | Nhóm sở hữu sản phẩm |
| Framework và runner dùng chung | Nhóm nền tảng kiểm thử | Các nhóm sản phẩm |
| Dữ liệu và môi trường dùng chung | Nhóm được giao sở hữu dữ liệu hoặc môi trường | Các nhóm sử dụng |

Bảng là gợi ý. Điều quan trọng là mỗi bộ kiểm thử có một chủ sở hữu chính, một nhóm hỗ trợ khi cần và một quy trình chuyển giao khi phạm vi thay đổi.

## 4. Xác định trách nhiệm cụ thể của chủ sở hữu

Tên một nhóm trong tài liệu chưa đủ. Cần mô tả các công việc mà chủ sở hữu phải bảo đảm.

### Trách nhiệm về mục tiêu và phạm vi

Chủ sở hữu cần biết bộ kiểm thử bảo vệ hành vi hoặc rủi ro nào, tầng kiểm thử nào phù hợp và những phần nào nằm ngoài phạm vi. Khi yêu cầu thay đổi, họ đánh giá test nào cần cập nhật hoặc loại bỏ.

### Trách nhiệm về mã kiểm thử

Bao gồm khả năng đọc, cấu trúc, assertion, tính độc lập, khả năng chạy song song, mức độ trùng lặp và tuân thủ quy ước. Chủ sở hữu cần xem xét thay đổi của test giống như thay đổi mã sản phẩm.

### Trách nhiệm về dữ liệu và phụ thuộc

Cần bảo đảm dữ liệu có thể tạo lại, được cách ly, có cleanup và không chứa thông tin nhạy cảm không phù hợp. Phụ thuộc như database, broker, API sandbox và dịch vụ giả lập cần có cách khởi tạo, cấu hình và xử lý lỗi.

### Trách nhiệm về thực thi

Chủ sở hữu theo dõi kiểm thử có chạy đúng thời điểm không, pipeline có báo trạng thái chính xác không, test bị bỏ qua có được xử lý không và thời gian chạy có còn phù hợp không.

### Trách nhiệm về thất bại và flaky test

Khi test thất bại, cần phân loại nguyên nhân, xác định có phải lỗi sản phẩm hay lỗi kiểm thử, giao người điều tra và cập nhật trạng thái. Test không ổn định cần có kế hoạch xử lý và thời hạn, không nên bị retry hoặc tắt vô thời hạn.

### Trách nhiệm về vòng đời và tài liệu

Chủ sở hữu xem xét kiểm thử khi tính năng thay đổi, thư viện hết hỗ trợ, hợp đồng bị thay thế hoặc rủi ro không còn phù hợp. Tài liệu cần cho biết cách chạy, dữ liệu cần thiết, phụ thuộc, người liên hệ và cách xử lý khi thất bại.

## 5. Dùng ma trận trách nhiệm để tránh khoảng trống

Có thể dùng mô hình RACI để làm rõ ai thực hiện và ai chịu trách nhiệm cuối cùng:

- **R – Responsible:** trực tiếp thực hiện công việc.
- **A – Accountable:** chịu trách nhiệm cuối cùng về kết quả.
- **C – Consulted:** được tham vấn.
- **I – Informed:** được thông báo.

Với mỗi công việc quan trọng, nên có một đầu mối A rõ ràng. Có thể có nhiều người R hoặc C. Không nên để trách nhiệm A mơ hồ giữa nhiều nhóm.

Ví dụ:

| Công việc | Nhóm sản phẩm | Nhóm QA | Nền tảng kiểm thử | Chủ sản phẩm |
|---|---|---|---|---|
| Xác định rủi ro và phạm vi test | R | R | C | A |
| Viết test đơn vị và thành phần | A/R | C | I | I |
| Duy trì test E2E của luồng | R | A/R hoặc R theo phân công | C | C |
| Duy trì runner và framework chung | C | C | A/R | I |
| Chuẩn bị dữ liệu nghiệp vụ | A/R | R | C | C |
| Duy trì môi trường dùng chung | C | C | A/R | I |
| Triage lỗi sản phẩm | A/R | R | C | I |
| Triage lỗi hạ tầng kiểm thử | C | R | A/R | I |
| Quyết định chấp nhận rủi ro nghiệp vụ | C | C | I | A/R |
| Xem xét ngân sách bảo trì | R | R | R | A |

Ma trận cần được điều chỉnh theo cấu trúc tổ chức. Nếu một nhóm đảm nhận nhiều vai trò, hãy ghi rõ trong tài liệu để người dùng biết nơi chuyển vấn đề.

### Gắn quyền sở hữu vào kho mã

Có thể dùng CODEOWNERS, quy tắc reviewer, metadata của test hoặc nhãn trong công cụ quản lý để chỉ ra người sở hữu. Những thông tin này nên nằm gần mã kiểm thử hoặc trong hệ thống quản lý nhóm đang sử dụng.

Cần có quy trình cập nhật khi nhóm đổi tên, thành viên rời nhóm, dịch vụ chuyển quyền sở hữu hoặc test được di chuyển. Một tệp CODEOWNERS lỗi thời không tạo ra trách nhiệm thực tế.

## 6. Xác định ngân sách bảo trì gồm những gì

Ngân sách bảo trì không chỉ là thời gian sửa test thất bại. Nó bao gồm toàn bộ nguồn lực để giữ bộ kiểm thử đáng tin cậy và phù hợp với sản phẩm.

Các nhóm chi phí thường gặp:

### Công sức con người

- Triage và điều tra test thất bại.
- Sửa test khi hành vi hoặc giao diện thay đổi.
- Cập nhật dữ liệu và fixture.
- Sửa flaky test và loại bỏ nguyên nhân không ổn định.
- Nâng cấp framework, driver và thư viện.
- Tối ưu thời gian chạy và giảm trùng lặp.
- Rà soát assertion, phạm vi và khoảng trống.
- Viết tài liệu, hướng dẫn và hỗ trợ nhóm khác.
- Đào tạo người mới và chuyển giao quyền sở hữu.

### Hạ tầng và công cụ

- Máy chạy CI, runner, container và tài nguyên tính toán.
- Môi trường kiểm thử và dịch vụ phụ trợ.
- Lưu trữ log, video, trace, báo cáo và artifact.
- License cho công cụ, trình duyệt hoặc nền tảng.
- Dịch vụ sandbox hoặc tài khoản thử nghiệm của nhà cung cấp.
- Công cụ quản lý dữ liệu và bí mật kiểm thử.

### Chi phí gián tiếp

- Thời gian chờ pipeline.
- Thời gian nhà phát triển bị gián đoạn bởi cảnh báo không đáng tin cậy.
- Chi phí điều tra lỗi giả.
- Chi phí phát hành bị trì hoãn do test không ổn định.
- Chi phí bảo trì framework dùng chung.
- Chi phí phục hồi dữ liệu hoặc môi trường sau test lỗi.

Ngân sách cần tính cả chi phí trực tiếp và phần năng lực bị tiêu hao do độ tin cậy thấp. Một bộ kiểm thử chạy nhanh nhưng thường xuyên báo sai có thể tốn nhiều thời gian của nhóm hơn một bộ test chạy lâu nhưng ổn định.

## 7. Phân biệt chi phí tạo mới và chi phí duy trì

Khi lập kế hoạch tự động hóa, nhóm thường ước lượng thời gian viết test nhưng đánh giá thấp chi phí trong các vòng lặp sau.

**Chi phí tạo mới** gồm phân tích hành vi, thiết kế kịch bản, viết test, tạo dữ liệu, thiết lập môi trường và đưa vào pipeline.

**Chi phí duy trì** gồm cập nhật theo thay đổi, xử lý thất bại, sửa dữ liệu, nâng cấp phụ thuộc, xử lý flaky test và kiểm tra lại bằng chứng.

Một test E2E có thể tốn nhiều công sức duy trì hơn test đơn vị vì phụ thuộc vào nhiều thành phần, dữ liệu, giao diện và môi trường. Một test đơn vị cũng có thể khó duy trì nếu nó gắn chặt với chi tiết triển khai hoặc có fixture phức tạp.

Không nên quyết định tự động hóa chỉ dựa trên chi phí viết test. Hãy xem xét tổng chi phí sở hữu trong khoảng thời gian dự kiến sử dụng.

### Ước lượng tổng chi phí sở hữu

Có thể mô hình hóa đơn giản:

\[
TCO = C_{create} + \sum_{k=1}^{n} C_{maintain,k} + C_{infra} + C_{tooling}
\]

Trong đó:

- \(C_{create}\): công sức tạo và đưa kiểm thử vào sử dụng.
- \(C_{maintain,k}\): chi phí bảo trì trong chu kỳ thứ \(k\).
- \(C_{infra}\): chi phí hạ tầng thực thi và lưu trữ.
- \(C_{tooling}\): chi phí công cụ và license.

Mô hình này giúp so sánh các lựa chọn, nhưng cần ghi rõ kỳ tính toán, đơn vị và giả định. Không nên cộng giờ công với tiền hạ tầng thành một con số nếu chưa quy đổi về cùng đơn vị chi phí.

## 8. Ước lượng ngân sách thời gian bảo trì

Ngân sách thời gian có thể được ước lượng từ lịch sử thực tế, số lượng test, tầng kiểm thử, tốc độ thay đổi và mức độ không ổn định.

Một cách tiếp cận là chia công việc thành các nhóm:

| Nhóm công việc | Cách ước lượng |
|---|---|
| Triage thất bại | Số lần thất bại cần điều tra × thời gian triage trung bình |
| Sửa test do thay đổi sản phẩm | Số thay đổi ảnh hưởng test × thời gian cập nhật trung bình |
| Xử lý flaky test | Số test không ổn định × thời gian điều tra và sửa |
| Dữ liệu và môi trường | Số lần làm mới, lỗi dữ liệu và thời gian chuẩn bị |
| Nâng cấp công cụ | Số đợt nâng cấp × thời gian kiểm tra tương thích |
| Tối ưu hiệu năng bộ test | Thời gian phân tích và cải tiến theo mục tiêu |
| Rà soát phạm vi | Thời gian xem lại test lỗi thời, thiếu assertion hoặc trùng lặp |

Có thể dùng công thức dự báo:

\[
H_{maintenance} =
H_{triage} + H_{repair} + H_{data} + H_{environment} +
H_{upgrade} + H_{review}
\]

Trong đó \(H\) là số giờ công trong một chu kỳ. Nên thêm phần dự phòng cho sự cố bất ngờ dựa trên biến động lịch sử, thay vì dùng một tỷ lệ không có căn cứ.

### Dùng dữ liệu lịch sử thay cho phỏng đoán

Nếu nhóm đã có dữ liệu từ vài sprint hoặc vài tháng, hãy xem:

- Bao nhiêu test thất bại mỗi tuần?
- Bao nhiêu phần trăm là lỗi sản phẩm, lỗi test, môi trường hoặc flaky?
- Trung bình mất bao lâu để xác định nguyên nhân?
- Bao nhiêu test cần sửa sau mỗi thay đổi lớn?
- Bao nhiêu giờ bị tiêu hao do dữ liệu hoặc môi trường?
- Pipeline tăng thời gian chạy bao nhiêu theo thời gian?
- Có bao nhiêu test bị tắt hoặc bỏ qua và trong bao lâu?

Nếu chưa có lịch sử, bắt đầu bằng ước lượng nhỏ, ghi nhận thực tế trong một vài chu kỳ rồi điều chỉnh. Không nên giả định rằng số lượng test tỷ lệ tuyến tính với chi phí bảo trì; chất lượng thiết kế, độ ổn định và số lượng phụ thuộc ảnh hưởng rất lớn.

## 9. Dành năng lực bảo trì trong kế hoạch sprint

Bảo trì kiểm thử cần được đưa vào kế hoạch như công việc có chủ sở hữu và thời lượng, thay vì làm vào thời gian còn dư.

Có thể sử dụng ba nguồn năng lực:

1. **Năng lực thường xuyên:** thời gian dành cho triage, sửa lỗi test, cập nhật dữ liệu và xử lý thay đổi nhỏ.
2. **Năng lực cải tiến định kỳ:** thời gian xử lý flaky test, giảm thời gian chạy, refactor framework và loại bỏ test lỗi thời.
3. **Năng lực dự phòng:** thời gian dành cho thay đổi lớn, sự cố pipeline, nâng cấp bắt buộc hoặc vấn đề ảnh hưởng phát hành.

Tỷ lệ cụ thể cần dựa trên lịch sử và mức độ trưởng thành. Một nhóm có bộ test mới, ít phụ thuộc có thể cần ít giờ bảo trì hơn nhóm có hệ thống lâu năm với nhiều test E2E và môi trường dùng chung. Không nên áp dụng một tỷ lệ cứng cho mọi nhóm.

### Ví dụ phân bổ năng lực

Giả sử một nhóm có 100 giờ năng lực kỹ thuật trong một sprint. Dựa trên dữ liệu vài sprint trước, nhóm dự trù:

| Hạng mục | Giờ dự kiến |
|---|---:|
| Triage và sửa test thất bại | 6 |
| Cập nhật test do thay đổi tính năng | 5 |
| Dữ liệu và môi trường | 3 |
| Flaky test và độ ổn định | 3 |
| Nâng cấp hoặc cải tiến framework | 2 |
| Dự phòng sự cố | 1 |
| Tổng | 20 |

Trong ví dụ, nhóm dành 20 giờ cho bảo trì bộ kiểm thử trong sprint. Đây là cách minh họa, không phải tỷ lệ chuẩn. Nhóm cần điều chỉnh theo khối lượng thực tế, độ rủi ro và năng lực còn lại.

Nếu công việc bảo trì thường xuyên vượt ngân sách, cần điều tra nguyên nhân: test thiết kế kém, thay đổi giao diện quá thường xuyên, môi trường không ổn định, dữ liệu dùng chung hoặc thiếu người sở hữu. Tăng ngân sách có thể cần thiết, nhưng cũng cần loại bỏ nguyên nhân tạo ra công việc lặp lại.

## 10. Ưu tiên công việc bảo trì

Không phải mọi test lỗi hoặc cảnh báo đều cần xử lý ngay. Cần ưu tiên theo tác động đến quyết định chất lượng và khả năng tin cậy của pipeline.

Có thể dùng các nhóm ưu tiên:

| Mức | Ví dụ | Hướng xử lý |
|---|---|---|
| Khẩn cấp | Test quan trọng thất bại do lỗi sản phẩm nghiêm trọng hoặc pipeline không thể đánh giá điều kiện phát hành | Điều tra ngay, có thể dừng phát hành |
| Cao | Flaky test ở luồng cốt lõi, test bị tắt ở khu vực rủi ro cao | Ưu tiên trong chu kỳ hiện tại |
| Trung bình | Test chậm, dữ liệu khó tái tạo hoặc helper gây khó bảo trì | Lập kế hoạch cải tiến |
| Thấp | Trùng lặp nhỏ, tên chưa rõ hoặc tài liệu phụ thiếu | Xử lý cùng thay đổi liên quan |

Thứ tự xử lý cần xem xét cả rủi ro bị che khuất. Một test flaky ở luồng thanh toán có thể làm nhóm bỏ qua cảnh báo thật. Một test chậm ở pipeline chạy mọi pull request có thể làm chậm toàn bộ nhóm. Một test lỗi thời có thể tạo cảm giác bao phủ giả.

### Không chỉ sửa triệu chứng

Khi một test thất bại, hãy phân loại nguyên nhân:

- Lỗi sản phẩm.
- Lỗi mã kiểm thử hoặc assertion.
- Dữ liệu không đúng hoặc bị chia sẻ.
- Môi trường hoặc phụ thuộc không sẵn sàng.
- Timeout hoặc giới hạn tài nguyên.
- Flaky do đồng thời, thời gian hoặc thứ tự.
- Thay đổi yêu cầu khiến test không còn đúng.

Sửa đúng nguyên nhân giúp tránh cùng một loại công việc lặp lại trong các sprint tiếp theo.

## 11. Quản lý flaky test như một khoản nợ bảo trì

Flaky test là kiểm thử cho kết quả không ổn định trong những điều kiện tương đương. Nó có thể đạt ở lần này và thất bại ở lần khác mà không có thay đổi liên quan.

Flaky test làm giảm niềm tin vào pipeline. Khi nhóm thường xuyên bỏ qua thất bại hoặc chạy lại cho đến khi đạt, cảnh báo thật có thể bị che khuất.

### Theo dõi flaky test

Nên ghi:

- Tên và định danh test.
- Tần suất đạt và thất bại.
- Môi trường, worker và cấu hình liên quan.
- Lần thất bại đầu tiên và kết quả retry.
- Nguyên nhân đã biết hoặc giả thuyết.
- Người sở hữu.
- Trạng thái điều tra và thời hạn xử lý.

### Quy trình xử lý

1. Xác nhận test thực sự không ổn định.
2. Thu thập log, trace, ảnh chụp và dữ liệu.
3. Xem xét phụ thuộc thời gian, thứ tự, dữ liệu dùng chung và đồng thời.
4. Tái hiện trong điều kiện có kiểm soát.
5. Sửa nguyên nhân gốc hoặc thay đổi cách kiểm chứng.
6. Chạy đủ số lần và trong môi trường phù hợp để đánh giá độ ổn định.
7. Gỡ trạng thái cách ly hoặc bật lại test khi có bằng chứng.
8. Cập nhật chỉ số và bài học.

Nếu cần cách ly test khỏi cổng chặn trong lúc điều tra, phải có chủ sở hữu, thời hạn và biện pháp kiểm soát rủi ro. Không nên tắt test vô thời hạn hoặc loại bỏ nó khỏi báo cáo.

## 12. Ngân sách cho dữ liệu, môi trường và hạ tầng

Một bộ kiểm thử đáng tin cậy cần dữ liệu và môi trường có thể tái tạo. Đây thường là phần chi phí bị đánh giá thấp vì nó không nằm trực tiếp trong tệp mã test.

### Dữ liệu kiểm thử

Ngân sách dữ liệu có thể gồm:

- Tạo và làm sạch dữ liệu.
- Quản lý tài khoản và quyền.
- Sinh dữ liệu tổng hợp.
- Snapshot hoặc khôi phục trạng thái.
- Cấp phát namespace hoặc database riêng.
- Xóa dữ liệu hết hạn.
- Kiểm tra dữ liệu tham chiếu và quan hệ.
- Bảo vệ dữ liệu và kiểm soát truy cập.

Cần chỉ định người sở hữu dữ liệu và quy trình khi dữ liệu bị hỏng. Một bộ test có thể rất ổn định về mã nhưng vẫn thất bại thường xuyên nếu dữ liệu nền không được quản lý.

### Môi trường kiểm thử

Chi phí môi trường gồm tài nguyên tính toán, dịch vụ phụ trợ, mạng, chứng thư, secret, broker, database và công sức vận hành. Cần quyết định môi trường nào được chia sẻ, môi trường nào được tạo tạm thời và ai chịu trách nhiệm khôi phục.

### Chi phí thực thi CI

Có thể ước lượng chi phí thực thi từ:

\[
C_{CI} = N_{runs} \times T_{average} \times R_{compute}
\]

Trong đó:

- \(N_{runs}\): số lần chạy trong kỳ.
- \(T_{average}\): thời gian trung bình của một lần chạy.
- \(R_{compute}\): chi phí tài nguyên trên một đơn vị thời gian.

Công thức chỉ là mô hình đơn giản. Thực tế có thể cần tính thời gian chờ, mức sử dụng runner, chạy song song, lưu trữ artifact và license. Dù vậy, nó giúp thấy tác động của một bộ E2E quá dài khi được chạy trên mọi pull request.

### Tối ưu chi phí thực thi

Có thể giảm chi phí bằng cách:

- Chạy test nhanh và quan trọng ở pull request.
- Chạy bộ test rộng theo lịch hoặc trước phát hành.
- Chia nhóm theo tầng và mức rủi ro.
- Loại bỏ test trùng lặp sau khi đánh giá bằng chứng.
- Chạy song song an toàn.
- Dùng môi trường tạm thời khi phù hợp.
- Lưu artifact theo thời hạn cần thiết.
- Tối ưu fixture và thời gian khởi tạo.
- Theo dõi test chậm nhất và nguyên nhân.

Không nên giảm chi phí bằng cách bỏ kiểm thử rủi ro cao hoặc tắt cảnh báo mà chưa đánh giá ảnh hưởng.

## 13. Lập backlog bảo trì có thể theo dõi

Công việc bảo trì cần được ghi thành hạng mục có thể lập kế hoạch, ưu tiên và xác nhận hoàn tất. Không nên để nó tồn tại dưới dạng danh sách việc nhỏ không có người chịu trách nhiệm.

Một backlog bảo trì có thể gồm:

- Sửa test hỏng sau thay đổi sản phẩm.
- Điều tra flaky test.
- Cập nhật fixture và dữ liệu.
- Nâng cấp thư viện hoặc framework.
- Giảm thời gian chạy.
- Thay thế test dùng mock quá mức.
- Xóa test trùng lặp hoặc không còn giá trị.
- Bổ sung assertion cho rủi ro mới.
- Cập nhật hướng dẫn và quyền sở hữu.
- Cải thiện báo cáo và khả năng điều tra.

Mỗi hạng mục nên có:

- Mô tả vấn đề và tác động.
- Bộ kiểm thử hoặc khu vực liên quan.
- Người sở hữu.
- Mức ưu tiên.
- Ước lượng công sức.
- Phụ thuộc.
- Điều kiện hoàn tất.
- Bằng chứng sau xử lý.

### Điều kiện hoàn tất bảo trì

Ví dụ, một hạng mục sửa flaky test chỉ nên đóng khi:

- Nguyên nhân đã được xác định hoặc có giải thích kỹ thuật đáng tin cậy.
- Cách sửa đã được áp dụng.
- Test chạy ổn định trong điều kiện và số lần đã thống nhất.
- Không làm giảm assertion hoặc phạm vi quan trọng.
- Pipeline và báo cáo phản ánh đúng trạng thái.
- Người sở hữu xác nhận và tài liệu được cập nhật nếu cần.

Đối với việc xóa test, cần xác minh rằng rủi ro được bảo vệ ở nơi khác hoặc không còn liên quan. Không nên xóa chỉ vì test thường xuyên thất bại.

## 14. Theo dõi sức khỏe và chi phí của bộ kiểm thử

Chỉ số giúp nhận ra ngân sách có đủ hay không và công việc bảo trì đang tạo ra giá trị gì. Nên theo dõi một tập chỉ số nhỏ, có thể hành động.

### Độ tin cậy

- Tỷ lệ test thất bại do lỗi test hoặc môi trường.
- Tỷ lệ flaky và số test đang bị cách ly.
- Tỷ lệ pipeline chạy thành công mà không cần retry.
- Thời gian trung bình để phân loại thất bại.

### Khả năng vận hành

- Thời gian chạy theo tầng.
- Thời gian chờ runner và mức sử dụng tài nguyên.
- Số lần pipeline bị gián đoạn.
- Tỷ lệ test bị bỏ qua hoặc tắt.
- Tuổi của test đang chờ sửa.

### Chi phí bảo trì

- Giờ công dành cho triage và sửa test.
- Giờ công dành cho dữ liệu và môi trường.
- Thời gian nâng cấp framework.
- Chi phí tài nguyên CI và lưu trữ.
- Tỷ lệ công việc bảo trì phát sinh ngoài kế hoạch.

### Giá trị chất lượng

- Rủi ro quan trọng được kiểm chứng.
- Lỗi sản phẩm được phát hiện trước phát hành.
- Lỗi lọt ra sau phát hành có liên quan đến khoảng trống kiểm thử.
- Tỷ lệ phát hiện được chuyển thành kiểm thử hồi quy.
- Thời gian từ khi phát hiện đến khi có bằng chứng đáng tin cậy.

Không nên dùng số lượng test, tỷ lệ pass hoặc số lỗi phát hiện làm thước đo duy nhất. Các chỉ số có thể bị tối ưu theo cách làm giảm chất lượng thực tế. Hãy xem chúng cùng với phạm vi rủi ro và mức độ tin cậy của assertion.

## 15. Nhận biết ngân sách bảo trì đang thiếu

Một số dấu hiệu cho thấy năng lực hoặc nguồn lực hiện tại không đủ:

- Test thất bại tồn đọng qua nhiều sprint.
- Flaky test bị retry hoặc cách ly lâu ngày.
- Nhóm thường xuyên tắt test để giữ pipeline chạy.
- Người phát triển dành nhiều thời gian điều tra cảnh báo giả.
- Test chậm đến mức nhóm tránh chạy thường xuyên.
- Dữ liệu và môi trường thường xuyên phải sửa thủ công.
- Không có thời gian nâng cấp framework hoặc thư viện hết hỗ trợ.
- Không ai nhận trách nhiệm khi chủ sở hữu cũ rời nhóm.
- Các thay đổi tính năng liên tục làm test hỏng nhưng không có thời gian cập nhật.
- Kiểm thử quan trọng chưa được viết vì nhóm chỉ đủ thời gian xử lý công việc mới.

Khi gặp các dấu hiệu này, cần phân tích nguồn gốc trước khi tăng ngân sách. Có thể vấn đề đến từ thiết kế test quá phụ thuộc giao diện, dữ liệu dùng chung, thiếu môi trường tạm thời hoặc quy trình triage chưa rõ. Một khoản đầu tư cải thiện nền tảng có thể giảm chi phí bảo trì lâu dài.

## 16. Xem xét giá trị của từng kiểm thử

Không phải test nào cũng đáng được giữ mãi. Một số test có thể trở nên dư thừa, không còn bảo vệ rủi ro hoặc tốn nhiều chi phí hơn giá trị mà nó cung cấp.

Khi rà soát, hãy xem:

- Test bảo vệ yêu cầu hoặc rủi ro nào?
- Rủi ro đó còn tồn tại không?
- Có test khác cung cấp bằng chứng tương đương không?
- Test có assertion đủ mạnh không?
- Test chạy ở tầng phù hợp không?
- Chi phí chạy và bảo trì là bao nhiêu?
- Test có thường xuyên thất bại giả không?
- Nếu xóa, khoảng trống nào sẽ xuất hiện?

Có thể quyết định:

- Giữ nguyên.
- Cải thiện assertion hoặc dữ liệu.
- Chuyển xuống tầng thấp hơn để chạy nhanh và ổn định hơn.
- Gộp với test khác nếu cùng mục tiêu và không mất bằng chứng.
- Thay thế bằng cách kiểm chứng phù hợp hơn.
- Xóa khi rủi ro không còn hoặc đã được bảo vệ đầy đủ ở nơi khác.

Quyết định cần được ghi lại cho các test quan trọng. Không nên xóa hàng loạt chỉ để giảm thời gian pipeline mà chưa xem xét phạm vi rủi ro.

## 17. Quy trình chuyển giao quyền sở hữu

Quyền sở hữu có thể thay đổi khi nhóm tái cấu trúc, dịch vụ chuyển nhóm, nhân sự rời tổ chức hoặc framework được chuyển sang nền tảng chung. Chuyển giao cần được thực hiện có chủ đích.

Một quy trình phù hợp:

1. Xác định bộ kiểm thử và tài nguyên liên quan.
2. Ghi nhận mục tiêu, phạm vi và rủi ro được bảo vệ.
3. Liệt kê cách chạy, môi trường, dữ liệu, phụ thuộc và pipeline.
4. Ghi nhận flaky test, lỗi đang mở và nợ bảo trì.
5. Chỉ định chủ sở hữu mới và người thay thế.
6. Tổ chức buổi bàn giao với ví dụ chạy và xử lý thất bại.
7. Cập nhật CODEOWNERS, tài liệu và quyền truy cập.
8. Xác nhận nhóm mới có thể chạy và điều tra kiểm thử.
9. Cập nhật ngân sách và backlog theo trách nhiệm mới.

Không nên chỉ đổi tên nhóm trong một tệp rồi xem như đã chuyển giao. Chủ sở hữu mới cần hiểu mục tiêu và có đủ quyền, kiến thức cùng năng lực để duy trì.

## 18. Ví dụ: xác định chủ sở hữu và ngân sách cho bộ kiểm thử thanh toán

Giả sử sản phẩm có dịch vụ thanh toán với các kiểm thử đơn vị, hợp đồng, tích hợp và E2E. Bộ kiểm thử chạy trên CI và dùng sandbox của nhà cung cấp.

### Phân công sở hữu

| Phạm vi | Chủ sở hữu | Trách nhiệm |
|---|---|---|
| Test đơn vị dịch vụ thanh toán | Nhóm thanh toán | Quy tắc số tiền, trạng thái và idempotency |
| Test hợp đồng API | Nhóm thanh toán cùng consumer | Schema, mã lỗi và tương thích |
| Test webhook tích hợp | Nhóm thanh toán | Thông điệp lặp, trễ và sai thứ tự |
| E2E thanh toán | Chủ sở hữu luồng mua hàng | Hành trình người dùng và trạng thái đơn |
| Sandbox và secret | Nhóm nền tảng hoặc tích hợp | Cấu hình, tài khoản và quyền |
| Runner và báo cáo CI | Nhóm nền tảng kiểm thử | Hạ tầng, pipeline và lưu artifact |
| Quyết định rủi ro phát hành | Chủ sản phẩm | Chấp nhận rủi ro còn lại |

### Ngân sách bảo trì mẫu theo sprint

| Công việc | Giờ |
|---|---:|
| Triage và điều tra thất bại | 4 |
| Cập nhật test theo thay đổi API | 3 |
| Duy trì dữ liệu và sandbox | 2 |
| Xử lý flaky test | 3 |
| Nâng cấp thư viện và runner | 2 |
| Rà soát phạm vi và assertion | 2 |
| Dự phòng thay đổi nhà cung cấp | 2 |
| Tổng | 18 |

Nhóm có thể xem lại ngân sách sau vài sprint. Nếu phần lớn thời gian dùng để sửa dữ liệu sandbox hoặc xử lý flaky test, cần cải thiện cách cô lập dữ liệu và mô phỏng phụ thuộc. Nếu phần lớn thời gian đến từ thay đổi hợp đồng, cần tăng phối hợp provider-consumer và tự động hóa kiểm tra tương thích.

Ví dụ này cho thấy ngân sách không chỉ là số giờ dành cho việc sửa test. Nó cần bao phủ các yếu tố làm cho kiểm thử có thể chạy và cung cấp bằng chứng đáng tin cậy.

## 19. Mẫu sổ đăng ký quyền sở hữu bộ kiểm thử

Có thể duy trì một bản ghi cho mỗi bộ kiểm thử hoặc nhóm kiểm thử:

~~~text
TÊN BỘ KIỂM THỬ:
SẢN PHẨM / THÀNH PHẦN:
MỤC TIÊU VÀ RỦI RO ĐƯỢC BẢO VỆ:
TẦNG KIỂM THỬ:
PHẠM VI VÀ GIỚI HẠN:

CHỦ SỞ HỮU CHÍNH:
NHÓM THỰC HIỆN:
NHÓM HỖ TRỢ:
NGƯỜI THAY THẾ:
ĐẦU MỐI QUYẾT ĐỊNH:

MÃ NGUỒN / VỊ TRÍ:
CÁCH CHẠY:
PIPELINE:
MÔI TRƯỜNG:
DỮ LIỆU:
PHỤ THUỘC:
TÀI LIỆU:

TÌNH TRẠNG:
- Thời gian chạy:
- Tỷ lệ flaky:
- Test đang tắt hoặc cách ly:
- Lỗi bảo trì đang mở:
- Nợ kỹ thuật:

NGÂN SÁCH:
- Triage và sửa:
- Dữ liệu và môi trường:
- Hạ tầng và công cụ:
- Nâng cấp và cải tiến:
- Dự phòng:

NGÀY RÀ SOÁT GẦN NHẤT:
NGÀY RÀ SOÁT TIẾP THEO:
RỦI RO CÒN LẠI:
HÀNH ĐỘNG TIẾP THEO:
~~~

Với bộ kiểm thử nhỏ, có thể lưu các trường này trong README hoặc metadata của kho mã. Với hệ thống lớn, nên quản lý trong danh mục dịch vụ hoặc công cụ quản trị kiểm thử hiện có.

## 20. Mẫu lập ngân sách bảo trì theo chu kỳ

~~~text
CHU KỲ / SPRINT:
BỘ KIỂM THỬ:
CHỦ SỞ HỮU:
NĂNG LỰC DỰ KIẾN:

CÔNG VIỆC:
1. Triage và phân loại thất bại:
   Ước lượng giờ:
   Người phụ trách:

2. Sửa test và assertion:
   Ước lượng giờ:
   Người phụ trách:

3. Dữ liệu và môi trường:
   Ước lượng giờ:
   Người phụ trách:

4. Flaky test:
   Ước lượng giờ:
   Người phụ trách:

5. Framework và phụ thuộc:
   Ước lượng giờ:
   Người phụ trách:

6. Hiệu năng và thời gian chạy:
   Ước lượng giờ:
   Người phụ trách:

7. Rà soát phạm vi và tài liệu:
   Ước lượng giờ:
   Người phụ trách:

8. Dự phòng:
   Ước lượng giờ:
   Điều kiện sử dụng:

TỔNG GIỜ:
CHI PHÍ HẠ TẦNG / CÔNG CỤ:
GIẢ ĐỊNH:
RỦI RO VƯỢT NGÂN SÁCH:
KẾT QUẢ THỰC TẾ:
ĐIỀU CHỈNH CHO CHU KỲ SAU:
~~~

Nên so sánh ngân sách dự kiến với thực tế qua nhiều chu kỳ. Một sprint có sự cố lớn không nhất thiết đại diện cho mức bảo trì thông thường, nhưng các biến động lặp lại là tín hiệu cần điều chỉnh cách thiết kế, sở hữu hoặc cấp nguồn lực.

## 21. Những sai lầm thường gặp

- **Không chỉ định chủ sở hữu:** mọi người cùng nghĩ người khác sẽ xử lý test thất bại.
- **Giao toàn bộ trách nhiệm cho QA:** nhóm sở hữu mã và nghiệp vụ không tham gia duy trì bằng chứng.
- **Chỉ định tên cá nhân mà không có nhóm thay thế:** trách nhiệm biến mất khi người đó nghỉ hoặc chuyển nhóm.
- **Chỉ tính thời gian viết test:** bỏ qua triage, dữ liệu, môi trường, nâng cấp và flaky test.
- **Coi bảo trì là việc làm khi rảnh:** công việc liên tục bị dời và nợ kỹ thuật tăng.
- **Dùng một tỷ lệ ngân sách cứng cho mọi nhóm:** không phản ánh độ phức tạp và rủi ro.
- **Đo ngân sách bằng số lượng test:** số lượng không thể hiện chi phí hoặc giá trị.
- **Tắt test thất bại để giữ pipeline xanh:** làm mất bằng chứng và che khuất lỗi.
- **Retry cho đến khi đạt:** tạo cảm giác ổn định giả và tiêu tốn tài nguyên.
- **Không tính chi phí CI và lưu trữ:** bộ test có thể tăng chi phí hạ tầng ngoài dự kiến.
- **Không rà soát test lỗi thời:** giữ lại kiểm thử không còn bảo vệ rủi ro.
- **Chuyển quyền sở hữu mà không bàn giao:** nhóm mới không biết cách chạy hoặc xử lý lỗi.
- **Tăng ngân sách mà không xử lý nguyên nhân:** cùng một công việc lặp lại tiếp tục tiêu tốn năng lực.

## Kết luận

Mỗi bộ kiểm thử cần có chủ sở hữu rõ ràng, phạm vi trách nhiệm cụ thể và nguồn lực bảo trì phù hợp. Chủ sở hữu bảo đảm kiểm thử còn đúng mục tiêu, chạy đáng tin cậy, có dữ liệu và môi trường phù hợp, đồng thời được cập nhật khi sản phẩm thay đổi. Ngân sách cần bao gồm công sức con người, hạ tầng, công cụ, dữ liệu, xử lý flaky test, nâng cấp và dự phòng.

Khi phân công theo thành phần và tầng kiểm thử, dùng ma trận trách nhiệm, ghi nhận chi phí thực tế và theo dõi sức khỏe bộ kiểm thử, nhóm có thể dự báo nhu cầu bảo trì và phát hiện sớm tình trạng thiếu nguồn lực. Quyền sở hữu và ngân sách cần được xem xét định kỳ, đặc biệt khi kiến trúc, quy mô bộ kiểm thử hoặc cơ cấu nhóm thay đổi.
