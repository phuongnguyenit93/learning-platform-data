# Định nghĩa điều kiện bắt đầu cho từng hoạt động kiểm thử

Một hoạt động kiểm thử chỉ tạo ra bằng chứng có ý nghĩa khi các điều kiện cần thiết đã sẵn sàng. Nếu bắt đầu kiểm thử khi bản dựng chưa ổn định, yêu cầu chưa rõ, dữ liệu không phù hợp hoặc môi trường chưa hoạt động, kết quả có thể bị nhiễu. Nhóm có thể mất thời gian điều tra lỗi do chuẩn bị, bỏ sót lỗi sản phẩm hoặc đưa ra kết luận dựa trên một lần chạy không hợp lệ.

**Điều kiện bắt đầu (entry criteria)** là tập hợp điều kiện cần được đáp ứng trước khi một hoạt động kiểm thử hoặc một giai đoạn kiểm thử được phép bắt đầu. Chúng xác định mức độ sẵn sàng tối thiểu của đầu vào, sản phẩm, môi trường, dữ liệu, công cụ, nhân lực và các phụ thuộc. Điều kiện bắt đầu giúp nhóm quyết định có thể tiến hành, cần chuẩn bị thêm hay phải chấp nhận một ngoại lệ có kiểm soát.

Trong chiến lược kiểm thử xác thực (validation testing strategy), điều kiện bắt đầu cần được định nghĩa theo từng hoạt động cụ thể. Kiểm thử đơn vị, kiểm thử tích hợp, kiểm thử hệ thống, kiểm thử chấp nhận, kiểm thử hiệu năng và kiểm thử bảo mật có yêu cầu chuẩn bị khác nhau. Một checklist chung có thể cung cấp nền tảng, nhưng không nên áp dụng một cổng giống hệt cho mọi hoạt động.

## 1. Vì sao cần xác định điều kiện bắt đầu?

Không phải cứ có bản dựng hoặc có người kiểm thử là có thể bắt đầu một hoạt động. Ví dụ, kiểm thử tích hợp cần các dịch vụ phụ thuộc và hợp đồng giao tiếp phù hợp; kiểm thử hiệu năng cần tải, dữ liệu và cấu hình môi trường có tính đại diện; kiểm thử chấp nhận cần tiêu chí chấp nhận đã được thống nhất và người có thẩm quyền tham gia.

Điều kiện bắt đầu được xác định rõ giúp:

- **Bảo đảm đầu vào đủ tin cậy:** Sản phẩm, yêu cầu, dữ liệu và cấu hình đã đạt mức sẵn sàng tối thiểu.
- **Giảm kết quả nhiễu:** Tránh chạy kiểm thử trên môi trường hoặc bản dựng không phù hợp.
- **Sử dụng nguồn lực hiệu quả:** Người kiểm thử không phải chờ phụ thuộc hoặc lặp lại công việc chuẩn bị.
- **Phát hiện trở ngại sớm:** Các thiếu sót về dữ liệu, quyền, công cụ hoặc môi trường được nhận diện trước khi bắt đầu.
- **Tạo quyết định minh bạch:** Nhóm biết lý do bắt đầu, trì hoãn hoặc chấp nhận rủi ro.
- **Hỗ trợ truy vết:** Có thể xác định hoạt động đã bắt đầu trong điều kiện nào và bằng chứng được tạo ra có giới hạn gì.
- **Phối hợp giữa các nhóm:** Chủ sở hữu sản phẩm, phát triển, QA, vận hành và chuyên gia liên quan cùng hiểu trách nhiệm chuẩn bị.

Điều kiện bắt đầu không nhằm tạo thêm thủ tục cho mọi thay đổi nhỏ. Chúng phải tương xứng với rủi ro và chi phí của hoạt động. Với kiểm thử đơn vị cục bộ, một số điều kiện có thể được kiểm tra tự động trong vài giây. Với kiểm thử chấp nhận trước phát hành, việc xác nhận môi trường, dữ liệu, tiêu chí và người phê duyệt có thể cần quy trình chặt chẽ hơn.

## 2. Phân biệt điều kiện bắt đầu với các tiêu chí khác

Điều kiện bắt đầu thường được nhầm với Definition of Ready, tiêu chí hoàn thành, điều kiện dừng hoặc tiêu chí chấp nhận. Chúng có liên quan nhưng trả lời những câu hỏi khác nhau.

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| Điều kiện bắt đầu (entry criteria) | Điều gì phải sẵn sàng trước khi hoạt động kiểm thử bắt đầu? | Bản dựng đã triển khai lên môi trường test, smoke test đạt và dữ liệu đã nạp |
| Definition of Ready (DoR) | Hạng mục đã đủ rõ để nhóm bắt đầu phát triển hoặc đưa vào thực hiện chưa? | Mục tiêu, phạm vi, tiêu chí chấp nhận và phụ thuộc đã rõ |
| Tiêu chí chấp nhận (acceptance criteria) | Tính năng phải thể hiện hành vi nào để đáp ứng nhu cầu? | Người dùng chỉ hủy được đơn ở trạng thái đủ điều kiện |
| Điều kiện thoát/tiêu chí hoàn thành (exit criteria) | Khi nào hoạt động có đủ bằng chứng để kết thúc? | Các ca ưu tiên cao đã chạy, lỗi nghiêm trọng được xử lý hoặc có quyết định chấp nhận |
| Điều kiện tạm dừng (suspension criteria) | Khi nào phải tạm dừng vì việc tiếp tục không còn hữu ích hoặc an toàn? | Môi trường mất kết nối kéo dài hoặc bản dựng không khởi động |
| Điều kiện tiếp tục (resumption criteria) | Điều gì phải được khôi phục trước khi tiếp tục? | Môi trường hoạt động lại, dữ liệu được xác minh và smoke test đạt |
| Quality gate | Cổng chất lượng nào quyết định có được chuyển giai đoạn hoặc phát hành? | Không còn lỗi blocker chưa được xử lý và kiểm thử bắt buộc đạt |

Ví dụ, tiêu chí chấp nhận mô tả đơn hàng đủ điều kiện có thể được hủy. Điều kiện bắt đầu kiểm thử tính năng hủy đơn có thể yêu cầu bản dựng chứa thay đổi, tài khoản và dữ liệu đơn hàng đã sẵn sàng, dịch vụ đơn hàng hoạt động và ca kiểm thử đã được review. Điều kiện thoát sau đó mới đánh giá các kịch bản cần thiết đã chạy và kết quả có đạt hay không.

## 3. Nguyên tắc thiết kế điều kiện bắt đầu

Điều kiện bắt đầu có giá trị khi chúng cụ thể, có thể xác minh và gắn với mục tiêu hoạt động.

### 3.1. Có thể quan sát và xác minh

Tránh điều kiện mơ hồ như “môi trường ổn định”, “dữ liệu đầy đủ” hoặc “bản dựng tốt”. Hãy mô tả bằng chứng cụ thể:

- Endpoint health check trả về trạng thái mong đợi.
- Bản dựng có build ID và commit đã xác định.
- Smoke test của các luồng nền tảng đạt.
- Bộ dữ liệu có số lượng, cấu trúc và trạng thái được xác nhận.
- Tài khoản kiểm thử có role và scope phù hợp.
- Các tiêu chí chấp nhận ưu tiên đã được người có thẩm quyền xác nhận.
- Công cụ thu thập log hoặc trace đã được kiểm tra.

Nếu điều kiện không thể đo trực tiếp, hãy nêu ai xác nhận, dựa trên tài liệu hoặc bằng chứng nào và thời điểm xác nhận.

### 3.2. Tập trung vào điều kiện cần thiết

Chỉ đưa vào entry criteria những điều kiện ảnh hưởng đến tính hợp lệ hoặc giá trị của hoạt động. Ví dụ, kiểm thử một hàm tính toán độc lập không cần môi trường staging hoạt động. Bắt buộc chờ staging có thể làm chậm phản hồi mà không tăng độ tin cậy.

Ngược lại, kiểm thử đầu cuối thanh toán không nên bắt đầu nếu chưa xác minh endpoint là sandbox, credential hợp lệ và cơ chế dọn dẹp giao dịch thử.

### 3.3. Phù hợp với rủi ro và cấp độ kiểm thử

Hoạt động có tác động lớn hoặc khó đảo ngược cần điều kiện chặt hơn. Kiểm thử migration dữ liệu, phân quyền, giao dịch tài chính hoặc phục hồi thảm họa cần kiểm soát môi trường và dữ liệu kỹ lưỡng. Một kiểm tra giao diện cục bộ có thể dùng điều kiện nhẹ hơn.

### 3.4. Có người sở hữu

Mỗi điều kiện cần có chủ thể chịu trách nhiệm cung cấp hoặc xác minh. Ví dụ, nhóm phát triển chịu trách nhiệm bàn giao bản dựng; vận hành xác nhận môi trường; QA xác nhận test data và ca kiểm thử; chủ sản phẩm xác nhận tiêu chí nghiệp vụ.

### 3.5. Có cách xử lý khi chưa đạt

Điều kiện bắt đầu không chỉ là danh sách để đánh dấu. Với mỗi điều kiện chưa đạt, cần biết hoạt động sẽ bị trì hoãn, thu hẹp, chuyển sang kiểm thử khác hay được bắt đầu theo ngoại lệ. Quyết định phải ghi rõ giới hạn và rủi ro còn lại.

### 3.6. Không biến điều kiện bắt đầu thành bảo đảm tuyệt đối

Entry criteria xác nhận điều kiện tối thiểu đã sẵn sàng tại thời điểm kiểm tra. Chúng không chứng minh sản phẩm không có lỗi hoặc môi trường sẽ không thay đổi trong suốt hoạt động. Nhóm vẫn cần theo dõi điều kiện trong khi thực hiện và áp dụng tiêu chí tạm dừng khi cần.

## 4. Các nhóm điều kiện thường cần xem xét

Tùy hoạt động, entry criteria có thể được chia thành các nhóm sau.

### 4.1. Yêu cầu và phạm vi

- Mục tiêu kiểm thử và quyết định cần hỗ trợ đã rõ.
- Phạm vi trong và ngoài hoạt động được xác định.
- Yêu cầu, tiêu chí chấp nhận hoặc hợp đồng liên quan có phiên bản rõ ràng.
- Các câu hỏi nghiệp vụ quan trọng đã được giải đáp hoặc có người chịu trách nhiệm.
- Rủi ro chính và ưu tiên kiểm thử đã được xác định.

### 4.2. Sản phẩm và bản dựng

- Bản dựng hoặc phiên bản sản phẩm đã được xác định.
- Các bước build, triển khai hoặc cài đặt cần thiết hoàn tất.
- Thay đổi nằm trong phạm vi hoạt động đã được tích hợp.
- Không có lỗi blocker đã biết khiến hoạt động không thể thực hiện mục tiêu.
- Các kiểm tra trước đó cần thiết, chẳng hạn compile, lint hoặc smoke test, đã đạt.

### 4.3. Thiết kế kiểm thử và bằng chứng

- Ca kiểm thử, checklist, charter hoặc kịch bản cần thiết đã sẵn sàng.
- Expected result hoặc test oracle đủ rõ cho mục tiêu cần xác nhận.
- Dữ liệu đầu vào và điều kiện tiên quyết được mô tả.
- Tiêu chí đạt/không đạt và cách ghi nhận kết quả đã thống nhất.
- Các công cụ đo lường, log, trace hoặc báo cáo đã được cấu hình.

### 4.4. Môi trường, dữ liệu và phụ thuộc

- Môi trường đúng loại và đúng phiên bản.
- Dịch vụ phụ thuộc, endpoint, DNS và mạng cần thiết hoạt động.
- Database, schema, queue, cache và storage ở trạng thái phù hợp.
- Dữ liệu kiểm thử có thể truy cập và đủ điều kiện sử dụng.
- Cấu hình, feature flag, timezone và locale được xác định.
- Cơ chế setup, reset và cleanup đã được kiểm tra.

### 4.5. Nhân lực, quyền và công cụ

- Người thực hiện có kỹ năng và thời gian cần thiết.
- Tài khoản, role, token hoặc chứng chỉ có quyền phù hợp.
- Công cụ kiểm thử và license cần thiết sẵn sàng.
- Người phê duyệt hoặc chuyên gia cần tham gia đã được xác định.
- Kênh báo cáo lỗi và xử lý sự cố hoạt động.

### 4.6. An toàn và kiểm soát tác động

- Đã xác minh môi trường không phải production nếu hoạt động không được phép chạy trên production.
- Dữ liệu nhạy cảm được bảo vệ hoặc thay bằng dữ liệu tổng hợp/ẩn danh.
- Có phương án khôi phục hoặc cleanup cho thao tác có tác dụng phụ.
- Phạm vi mạng và quyền truy cập chỉ bao gồm tài nguyên cần thiết.
- Các bên liên quan đã biết về hoạt động có thể gây tải hoặc thay đổi dữ liệu.

Không phải mọi nhóm điều kiện đều cần xuất hiện trong mọi hoạt động. Hãy chọn theo mục tiêu và tác động thực tế.

## 5. Xác định điều kiện bắt đầu cho từng cấp độ kiểm thử

### 5.1. Kiểm thử đơn vị

Kiểm thử đơn vị thường có phạm vi nhỏ và phụ thuộc bên ngoài được thay thế hoặc kiểm soát. Điều kiện bắt đầu có thể gồm:

- Mã nguồn và test code biên dịch được.
- Unit test liên quan đã được cập nhật theo yêu cầu hoặc thay đổi.
- Fixture, factory, mock và test data có thể khởi tạo.
- Test oracle và assertion đủ rõ.
- Đồng hồ, seed ngẫu nhiên hoặc dependency được kiểm soát nếu ảnh hưởng kết quả.
- Bộ kiểm thử có thể chạy độc lập trong môi trường phát triển hoặc CI.

Không cần chờ triển khai hệ thống đầy đủ để chạy unit test. Nếu test đơn vị yêu cầu database hoặc dịch vụ thật, cần xem lại ranh giới kiểm thử hoặc xác định rõ đây là kiểm thử tích hợp.

### 5.2. Kiểm thử thành phần

Kiểm thử thành phần xác nhận một module hoặc service trong phạm vi được kiểm soát. Điều kiện bắt đầu có thể gồm:

- Thành phần đã được build và cấu hình theo phiên bản cần kiểm tra.
- Các dependency được thay thế hoặc khởi chạy theo kế hoạch.
- API, interface hoặc hợp đồng nội bộ liên quan đã được xác định.
- Dữ liệu nền và trạng thái ban đầu có thể tái tạo.
- Log hoặc cơ chế quan sát đủ để nhận diện lỗi trong thành phần.
- Những kiểm tra đơn vị nền tảng cần thiết đã hoàn thành.

Nếu thành phần được kiểm tra với database hoặc broker thật, cần chuẩn bị namespace riêng, tài khoản và cơ chế reset phù hợp.

### 5.3. Kiểm thử API và hợp đồng

Điều kiện bắt đầu có thể gồm:

- Phiên bản hợp đồng hoặc schema cần kiểm tra đã được công bố hoặc chốt cho hoạt động.
- Endpoint provider hoặc môi trường giả lập sẵn sàng.
- Authentication, authorization và credential test hợp lệ.
- Dữ liệu request/response và các trường hợp lỗi đã được chuẩn bị.
- Consumer/provider contract tests có mapping đúng phiên bản.
- Chính sách tương thích và các thay đổi phá vỡ đã được nhận diện.
- Log request, correlation ID và cách che dữ liệu nhạy cảm được cấu hình.

Với API bên ngoài, cần xác nhận sandbox đang hoạt động và giới hạn sử dụng phù hợp. Không bắt đầu kiểm thử có tác dụng phụ nếu chưa xác minh endpoint không trỏ nhầm sang production.

### 5.4. Kiểm thử tích hợp

Kiểm thử tích hợp xác nhận các thành phần phối hợp qua ranh giới thật hoặc được mô phỏng. Điều kiện bắt đầu thường gồm:

- Các thành phần cần tích hợp đã được triển khai hoặc khởi chạy ở phiên bản tương thích.
- Hợp đồng, schema, cấu hình và thông tin kết nối đã thống nhất.
- Mạng, DNS, chứng chỉ, secret và quyền truy cập đã được xác minh.
- Database, queue, cache hoặc dịch vụ phụ thuộc có trạng thái phù hợp.
- Dữ liệu và namespace được cô lập cho hoạt động.
- Cơ chế setup, cleanup và thu thập trace hoạt động.
- Smoke test của từng thành phần liên quan đã đạt hoặc các lỗi còn lại đã được đánh giá.

Không nên bắt đầu nếu một dependency bắt buộc không sẵn sàng và không có phương án giả lập phù hợp. Nếu dùng stub hoặc fake, cần ghi rõ phần tương tác thật chưa được xác nhận.

### 5.5. Kiểm thử hệ thống và đầu cuối

Điều kiện bắt đầu có thể gồm:

- Bản dựng tích hợp đã được triển khai lên môi trường hệ thống.
- Các dịch vụ cốt lõi và phụ thuộc cần thiết hoạt động.
- Cấu hình môi trường, feature flag và endpoint đã được xác minh.
- Tài khoản và dữ liệu đại diện cho các vai trò hoặc hành trình cần kiểm tra đã sẵn sàng.
- Smoke test hệ thống đạt.
- Kịch bản đầu cuối và expected result đã được review.
- Log, trace, metric và cơ chế thu thập bằng chứng có thể truy cập.
- Môi trường không bị hoạt động khác làm thay đổi dữ liệu hoặc tải ngoài dự kiến.

Với kiểm thử đầu cuối trên UI, cần xác định trình duyệt/thiết bị, viewport, ngôn ngữ và quyền truy cập. Với hành trình giao dịch, cần có sandbox, mã giao dịch thử và cơ chế bù trừ.

### 5.6. Kiểm thử chấp nhận sản phẩm

Kiểm thử chấp nhận xác nhận sản phẩm đáp ứng nhu cầu người dùng hoặc điều kiện nghiệm thu. Điều kiện bắt đầu thường gồm:

- Phạm vi nghiệm thu và tiêu chí chấp nhận đã được chủ sở hữu xác nhận.
- Bản dựng ứng viên đã được triển khai vào môi trường chấp nhận phù hợp.
- Các lỗi nghiêm trọng đã biết được xử lý hoặc có quyết định ngoại lệ rõ ràng.
- Dữ liệu và tài khoản đại diện cho bối cảnh sử dụng sẵn sàng.
- Người dùng đại diện, chuyên gia nghiệp vụ hoặc người phê duyệt có lịch tham gia.
- Hướng dẫn, kịch bản và biểu mẫu ghi nhận kết quả đã sẵn sàng.
- Điều kiện môi trường đủ gần với bối cảnh sử dụng cần đánh giá.

Không nên bắt đầu nghiệm thu khi tiêu chí vẫn còn mâu thuẫn hoặc người có thẩm quyền chưa thống nhất cách xử lý các trường hợp quan trọng. Nếu phạm vi nghiệm thu chỉ giới hạn ở một phần sản phẩm, báo cáo phải nêu rõ giới hạn đó.

### 5.7. Kiểm thử hồi quy

Điều kiện bắt đầu có thể gồm:

- Build chứa thay đổi cần kiểm tra đã được xác định.
- Phân tích tác động và tập kiểm thử hồi quy được chọn đã được review.
- Bộ test, dữ liệu, môi trường và mapping requirement/test phù hợp với phiên bản hiện tại.
- Các kiểm tra bắt buộc luôn chạy đã được thêm vào tập lựa chọn.
- Test bị flaky hoặc bị chặn đã có trạng thái và người phụ trách rõ.
- Ngân sách thời gian và quy tắc mở rộng sang full regression đã thống nhất.

Nếu thay đổi rộng, phụ thuộc không rõ hoặc metadata lựa chọn đã cũ, cần mở rộng phạm vi thay vì bắt đầu với một tập con quá hẹp.

### 5.8. Kiểm thử hiệu năng và tải

Kiểm thử hiệu năng có thể tạo tải lớn và ảnh hưởng đến hệ thống. Điều kiện bắt đầu thường gồm:

- Mục tiêu, workload, tải dự kiến, thời lượng và ngưỡng đánh giá đã xác định.
- Môi trường đủ đại diện cho câu hỏi cần trả lời.
- Dữ liệu và trạng thái ban đầu phù hợp với quy mô tải.
- Công cụ sinh tải đã được kiểm tra và đồng bộ thời gian.
- Hạ tầng quan sát metric, log, trace và tài nguyên sẵn sàng.
- Đã xác nhận giới hạn tải, phạm vi mạng và sự cho phép của chủ sở hữu môi trường.
- Có kế hoạch dừng khẩn cấp và khôi phục sau kiểm thử.
- Không có hoạt động khác làm sai lệch kết quả hoặc gây cạnh tranh tài nguyên ngoài dự kiến.

Không bắt đầu load test trên production hoặc dịch vụ của bên thứ ba nếu chưa có phê duyệt và giới hạn được thống nhất. Nếu môi trường nhỏ hơn production, phải ghi rõ kết quả chỉ đại diện cho cấu hình đã đo.

### 5.9. Kiểm thử bảo mật

Điều kiện bắt đầu có thể gồm:

- Phạm vi tài sản, endpoint, tài khoản và môi trường được cho phép kiểm tra đã xác định bằng văn bản.
- Mục tiêu, kỹ thuật và giới hạn kiểm thử được thống nhất.
- Tài khoản và quyền thử nghiệm được cấp riêng, đủ cho các kịch bản cần kiểm tra.
- Dữ liệu nhạy cảm được bảo vệ; có phương án tránh hoặc phục hồi tác động.
- Công cụ và phiên bản công cụ đã được kiểm tra.
- Người chịu trách nhiệm ứng phó khi phát hiện vấn đề nghiêm trọng đã được xác định.
- Có quy trình bảo vệ bằng chứng và báo cáo phát hiện.

Kiểm thử bảo mật chủ động có thể tạo request bất thường hoặc làm thay đổi dữ liệu. Cần xác nhận rõ phạm vi và giới hạn trước khi thực hiện. Không thử trên tài sản ngoài phạm vi được phép.

### 5.10. Kiểm thử tương thích và khả năng truy cập

Điều kiện bắt đầu có thể gồm:

- Ma trận nền tảng, phiên bản, thiết bị và cấu hình đã được xác định.
- Các tổ hợp ưu tiên và mức bao phủ cần đạt đã rõ.
- Thiết bị thật, máy ảo hoặc dịch vụ browser/device farm sẵn sàng.
- Dữ liệu, locale, timezone, viewport và phương thức tương tác đã được chuẩn bị.
- Tiêu chí tương thích hoặc khả năng truy cập được thống nhất.
- Công cụ hỗ trợ như screen reader, bàn phím, scanner hoặc báo cáo giao diện hoạt động.

Nếu một tổ hợp không thể chạy do thiết bị hoặc dịch vụ không sẵn sàng, cần đánh dấu bị chặn và đánh giá ảnh hưởng đến phạm vi hỗ trợ.

## 6. Xác định mức độ bắt buộc của từng điều kiện

Không phải mọi điều kiện đều có mức quan trọng như nhau. Có thể phân loại:

- **Bắt buộc (must):** Thiếu điều kiện khiến hoạt động không hợp lệ, không an toàn hoặc không thể đạt mục tiêu.
- **Khuyến nghị (should):** Điều kiện làm tăng độ tin cậy hoặc hiệu quả; có thể chấp nhận thiếu trong một số trường hợp nếu ghi rõ giới hạn.
- **Tùy chọn (may):** Điều kiện hữu ích nhưng không cần thiết cho mọi lần thực hiện.

Ví dụ với kiểm thử hiệu năng:

| Điều kiện | Mức | Lý do |
|---|---|---|
| Workload và ngưỡng đánh giá đã thống nhất | Bắt buộc | Không có mục tiêu thì không thể diễn giải kết quả |
| Môi trường có cấu hình được ghi nhận | Bắt buộc | Cần biết kết quả đại diện cho điều kiện nào |
| Dashboard tài nguyên sẵn sàng | Bắt buộc | Không thể chẩn đoán nút thắt nếu thiếu quan sát tối thiểu |
| Có dữ liệu tải gần thực tế | Khuyến nghị hoặc bắt buộc tùy mục tiêu | Mức đại diện của workload phụ thuộc dữ liệu |
| Có so sánh với build trước | Khuyến nghị | Hữu ích cho phân tích xu hướng nhưng không luôn có baseline |

Phân loại cần dựa trên mục tiêu. Nếu hoạt động nhằm xác nhận khả năng xử lý dữ liệu lớn, dữ liệu đại diện có thể là điều kiện bắt buộc. Nếu chỉ đo overhead của một hàm trong microbenchmark, môi trường hệ thống đầy đủ có thể không cần thiết.

## 7. Mô tả điều kiện theo dạng có thể kiểm tra

Một điều kiện bắt đầu tốt nên có cấu trúc gồm điều kiện, bằng chứng, người xác nhận và cách xử lý khi không đạt.

Ví dụ:

| Điều kiện chưa đủ rõ | Điều kiện có thể xác minh |
|---|---|
| Bản dựng sẵn sàng | Build ID được ghi trong kế hoạch; triển khai hoàn tất; endpoint health check đạt; không còn lỗi blocker đã biết |
| Dữ liệu đầy đủ | Dataset `checkout-regression-v3` đã nạp; số bản ghi và trạng thái kiểm tra khớp manifest; tài khoản có role cần thiết |
| Môi trường ổn định | Các dependency bắt buộc đạt health check trong khoảng xác nhận; không có bảo trì đang diễn ra; cấu hình và phiên bản được ghi nhận |
| Test đã chuẩn bị | Các ca ưu tiên có bước, dữ liệu, expected result và trạng thái review; test oracle đã được xác định |
| Người dùng sẵn sàng | Danh sách người tham gia, vai trò, thời gian và hướng dẫn đã được xác nhận |
| Quyền truy cập phù hợp | Danh tính kiểm thử đăng nhập được; scope và tenant đúng; thao tác ngoài quyền bị từ chối theo kịch bản kiểm tra |

Không nên tạo ra ngưỡng tùy tiện chỉ để làm điều kiện có vẻ định lượng. Ví dụ, “health check đạt ba lần liên tiếp” chỉ có ý nghĩa nếu khoảng thời gian và tần suất đó được chọn dựa trên đặc tính dịch vụ. Hãy nêu căn cứ hoặc dùng điều kiện vận hành đã được tổ chức thống nhất.

## 8. Quy trình thiết lập và phê duyệt điều kiện bắt đầu

Một quy trình đơn giản có thể gồm:

1. **Xác định hoạt động:** Nêu cấp độ, mục tiêu, phạm vi và kết quả cần tạo.
2. **Phân tích phụ thuộc:** Xác định sản phẩm, dữ liệu, môi trường, công cụ, người tham gia và hệ thống liên quan.
3. **Nhận diện rủi ro:** Xác định điều gì có thể làm kết quả không hợp lệ, gây nhiễu hoặc tạo tác động không mong muốn.
4. **Soạn điều kiện:** Chọn điều kiện bắt buộc, khuyến nghị và tùy chọn; mô tả bằng chứng cần có.
5. **Phân công chủ sở hữu:** Chỉ định ai cung cấp, ai xác minh và ai có quyền chấp nhận ngoại lệ.
6. **Kiểm tra trước khi bắt đầu:** Đối chiếu từng điều kiện với bằng chứng hiện tại.
7. **Đưa ra quyết định:** Bắt đầu, trì hoãn, thu hẹp phạm vi hoặc bắt đầu có điều kiện.
8. **Ghi nhận:** Lưu phiên bản sản phẩm, môi trường, trạng thái điều kiện và quyết định.
9. **Theo dõi trong khi thực hiện:** Nếu điều kiện nền thay đổi, đánh giá tính hợp lệ của các kết quả đã thu thập.

Với hoạt động lặp lại, có thể tự động hóa bước kiểm tra điều kiện. Ví dụ pipeline xác nhận build ID, dependency health, schema version và quyền truy cập trước khi chạy integration test. Các điều kiện cần phán đoán của con người, như mức đầy đủ của tiêu chí nghiệp vụ hoặc phạm vi chấp nhận rủi ro, vẫn cần người có thẩm quyền xác nhận.

## 9. Quyết định khi một hoặc nhiều điều kiện chưa đạt

Khi entry criteria chưa được đáp ứng, nhóm không nên đánh dấu hoạt động là đã bắt đầu bình thường mà không ghi nhận. Có một số lựa chọn:

### 9.1. Trì hoãn hoạt động

Phù hợp khi điều kiện thiếu là bắt buộc, chẳng hạn endpoint không đúng môi trường, dữ liệu không an toàn, bản dựng không khởi động hoặc chưa có quyền kiểm thử được phê duyệt. Nhóm ghi rõ điều kiện chưa đạt, người xử lý và thời điểm đánh giá lại.

### 9.2. Thu hẹp phạm vi

Nếu một phần môi trường hoặc dữ liệu chưa sẵn sàng, có thể thực hiện phần kiểm thử độc lập đã đủ điều kiện. Ví dụ, kiểm thử đơn vị có thể tiếp tục dù sandbox đối tác đang ngừng hoạt động; kiểm thử tích hợp phụ thuộc sandbox được đánh dấu bị chặn.

Phạm vi thu hẹp cần được ghi rõ để tránh diễn giải kết quả như đã bao phủ toàn bộ mục tiêu.

### 9.3. Dùng phương án thay thế có kiểm soát

Có thể dùng stub, fake, dữ liệu tổng hợp hoặc môi trường mô phỏng nếu phương án đó vẫn trả lời được câu hỏi kiểm thử. Phải nêu phần nào được xác minh và phần nào chưa được xác nhận với phụ thuộc thật.

### 9.4. Chấp nhận ngoại lệ

Một số trường hợp có thể bắt đầu dù điều kiện khuyến nghị chưa đạt. Ngoại lệ cần có:

- Điều kiện chưa đạt và lý do.
- Tác động đến phạm vi, độ tin cậy và rủi ro.
- Biện pháp giảm thiểu hoặc kiểm tra thay thế.
- Người có thẩm quyền chấp nhận.
- Thời hạn hoặc điều kiện kết thúc ngoại lệ.
- Cách báo cáo giới hạn trong kết quả kiểm thử.

Không nên cho phép ngoại lệ đối với điều kiện bắt buộc liên quan đến an toàn, quyền truy cập, dữ liệu hoặc phạm vi được phép nếu việc tiếp tục có thể gây tác động không thể chấp nhận.

## 10. Điều kiện bắt đầu và điều kiện tạm dừng/tiếp tục

Điều kiện bắt đầu được xác nhận trước hoạt động, nhưng một số điều kiện có thể thay đổi khi đang chạy. Ví dụ, dịch vụ phụ thuộc mất kết nối, chứng chỉ hết hạn, dữ liệu bị sửa bởi tiến trình khác hoặc môi trường được triển khai lại.

Nhóm nên định nghĩa khi nào phải tạm dừng:

- Bản dựng hoặc cấu hình đang kiểm tra không còn đúng phiên bản đã xác định.
- Môi trường mất ổn định khiến kết quả không thể diễn giải.
- Dữ liệu hoặc tài nguyên dùng chung bị thay đổi ngoài kế hoạch.
- Quyền truy cập không còn phù hợp hoặc có nguy cơ chạm vào hệ thống ngoài phạm vi.
- Hoạt động gây tải hoặc tác dụng phụ vượt giới hạn đã phê duyệt.
- Công cụ đo lường hoặc thu thập bằng chứng không hoạt động.

Trước khi tiếp tục, cần xác minh lại các điều kiện bị ảnh hưởng, khôi phục dữ liệu và môi trường nếu cần, chạy kiểm tra nhanh và ghi rõ phần kiểm thử phải thực hiện lại. Không phải mọi kết quả trước khi tạm dừng đều mất hiệu lực; nhóm cần đánh giá dựa trên thời điểm và phạm vi thay đổi.

## 11. Quản lý điều kiện bắt đầu trong CI/CD

Pipeline có thể tự động kiểm tra nhiều điều kiện trước khi khởi chạy bộ kiểm thử. Ví dụ:

```text
preflight:
  verify_build_id()
  verify_required_services_health()
  verify_database_schema_version()
  verify_test_endpoint_is_not_production()
  verify_test_data_manifest()
  verify_required_credentials_and_scopes()
  verify_test_artifacts_and_oracles()

if all_mandatory_checks_pass:
    run_test_suite()
else:
    mark_as_blocked_and_report_missing_conditions()
```

Đây là mô hình khái niệm. Trong triển khai thực tế, pipeline cần tránh in secret, kiểm tra endpoint an toàn và phân biệt lỗi sản phẩm với lỗi môi trường. Không nên coi job bị bỏ qua hoặc bị chặn là đạt.

Một số thực hành hữu ích:

- Gắn preflight check với build ID và commit.
- Dùng health check có ngưỡng và timeout rõ.
- Kiểm tra schema/database migration trước integration test.
- Xác nhận namespace và dữ liệu riêng trước khi chạy song song.
- Kiểm tra secret tồn tại và quyền phù hợp mà không hiển thị giá trị.
- Ghi nhận trạng thái từng điều kiện như pass, fail, blocked hoặc waived.
- Giữ báo cáo preflight cùng báo cáo kiểm thử để truy vết.

## 12. Mẫu điều kiện bắt đầu cho một hoạt động

Có thể sử dụng mẫu sau và điều chỉnh theo hoạt động:

```text
Tên hoạt động:
Mục tiêu và phạm vi:
Phiên bản sản phẩm/build:

Điều kiện bắt buộc:
  - Điều kiện:
    Bằng chứng:
    Người xác nhận:
    Trạng thái:

Điều kiện khuyến nghị:
  - Điều kiện:
    Bằng chứng:
    Người xác nhận:
    Trạng thái:

Đầu vào và dữ liệu:
Môi trường và phụ thuộc:
Công cụ và quyền truy cập:
Rủi ro nếu điều kiện chưa đạt:
Phương án thay thế hoặc giảm thiểu:
Người có quyền chấp nhận ngoại lệ:
Quyết định: START / DEFER / SCOPE-REDUCED / WAIVED
Thời điểm xác nhận:
```

Mẫu này giúp tránh việc chỉ đánh dấu checkbox mà không có bằng chứng. Với hoạt động nhỏ, có thể rút gọn các trường; với hoạt động có rủi ro cao, cần lưu đầy đủ người xác nhận và căn cứ.

## 13. Ví dụ: điều kiện bắt đầu cho kiểm thử luồng thanh toán

Giả sử nhóm cần kiểm thử tích hợp và đầu cuối cho luồng thanh toán bằng thẻ trong môi trường sandbox. Mục tiêu là xác nhận giao dịch thành công, thất bại, timeout và retry không tạo giao dịch trùng.

Điều kiện bắt đầu có thể được định nghĩa như sau:

| Điều kiện | Mức | Bằng chứng cần có | Chủ sở hữu |
|---|---|---|---|
| Build chứa thay đổi thanh toán đã triển khai | Bắt buộc | Build ID, commit và trạng thái deploy | Phát triển/vận hành |
| API đơn hàng và payment service hoạt động | Bắt buộc | Health check và smoke test | Vận hành |
| Endpoint là sandbox của nhà cung cấp | Bắt buộc | Hostname và cấu hình môi trường đã xác minh | Phát triển/vận hành |
| Token sandbox hợp lệ và đúng scope | Bắt buộc | Kiểm tra xác thực không hiển thị token | Chủ sở hữu tích hợp |
| Chứng chỉ và TLS hợp lệ | Bắt buộc | Kiểm tra hostname, chain và thời hạn | Vận hành/bảo mật |
| Test data có khách hàng, đơn hàng và số tiền xác định | Bắt buộc | Manifest dữ liệu và ID lần chạy | QA |
| Cơ chế reset hoặc bù trừ giao dịch thử sẵn sàng | Bắt buộc | Kiểm tra cleanup trên giao dịch mẫu | QA/phát triển |
| Các kịch bản và oracle được review | Bắt buộc | Test case, expected result và người review | QA/chủ sản phẩm |
| Log và correlation ID có thể truy cập | Bắt buộc | Một request kiểm tra có trace | Vận hành |
| Người theo dõi trong cửa sổ kiểm thử sẵn sàng | Khuyến nghị hoặc bắt buộc theo lịch | Lịch trực và đầu mối liên hệ | Điều phối kiểm thử |

Nếu token sandbox hết hạn, hoạt động phải được trì hoãn hoặc chỉ thực hiện phần không cần token. Nếu log chưa sẵn sàng, có thể kiểm thử một số chức năng cục bộ nhưng không nên tuyên bố đã xác nhận khả năng truy vết giao dịch. Nếu endpoint chưa được xác minh, không được gửi request có tác dụng phụ.

Sau khi preflight đạt, nhóm ghi nhận build, endpoint, phiên bản dữ liệu và thời điểm bắt đầu. Trong quá trình chạy, nếu sandbox ngừng hoạt động hoặc môi trường được triển khai lại, cần tạm dừng các ca bị ảnh hưởng và xác nhận lại điều kiện trước khi tiếp tục.

## 14. Ví dụ: điều kiện bắt đầu cho kiểm thử hiệu năng

Giả sử nhóm cần đo khả năng xử lý 500 request/giây trong một khoảng thời gian đã thống nhất. Trước khi chạy, cần:

- Chốt mục tiêu đo, loại request, phân bố dữ liệu và ngưỡng độ trễ/lỗi.
- Xác định môi trường và cấu hình tài nguyên; ghi rõ khác biệt với sản xuất.
- Chuẩn bị dữ liệu đủ lớn và trạng thái ban đầu có thể tái tạo.
- Xác nhận công cụ sinh tải có thể tạo tải mục tiêu mà không trở thành nút thắt.
- Bật metric CPU, bộ nhớ, kết nối, database, queue và độ trễ.
- Kiểm tra giới hạn tải, quyền thực hiện và cửa sổ thời gian được phép.
- Xác định ngưỡng dừng khẩn cấp và người theo dõi.
- Bảo đảm không có job khác gây cạnh tranh tài nguyên hoặc làm sai kết quả.

Nếu môi trường chỉ có một nửa tài nguyên so với môi trường đích, kết quả không thể được diễn giải trực tiếp thành năng lực của sản xuất. Hoạt động vẫn có thể hữu ích để so sánh hai build trên cùng cấu hình, nhưng phạm vi kết luận cần được ghi rõ.

## 15. Đánh giá và cải tiến điều kiện bắt đầu

Điều kiện bắt đầu cần được xem xét sau các hoạt động kiểm thử để xác định chúng có thực sự ngăn được công việc không hợp lệ hay đang tạo thủ tục không cần thiết.

Nhóm có thể theo dõi:

- Số lần hoạt động bị trì hoãn do điều kiện chưa đạt.
- Nguyên nhân phổ biến khiến preflight thất bại.
- Số lần bắt đầu nhưng phải dừng vì điều kiện nền không ổn định.
- Tỷ lệ lỗi môi trường hoặc dữ liệu bị nhầm là lỗi sản phẩm.
- Số ngoại lệ được chấp nhận và rủi ro phát sinh sau đó.
- Thời gian chuẩn bị trước mỗi hoạt động.
- Số lần phải chạy lại do bản dựng, dữ liệu hoặc cấu hình không đúng.
- Tỷ lệ điều kiện được tự động xác minh và độ tin cậy của các phép kiểm tra đó.

Nếu một điều kiện thường xuyên không đạt, cần xử lý nguyên nhân gốc. Ví dụ, nếu test data luôn thiếu, cải thiện quy trình seed và kiểm tra manifest có thể tốt hơn việc yêu cầu QA kiểm tra thủ công mỗi lần. Nếu health check quá nhạy và tạo false alarm, điều chỉnh phép kiểm tra theo đặc tính dịch vụ thay vì bỏ qua hoàn toàn.

Ngược lại, nếu một điều kiện chưa từng giúp phát hiện vấn đề và không ảnh hưởng tính hợp lệ, nhóm có thể đơn giản hóa hoặc loại bỏ. Mọi thay đổi nên được review để tránh làm yếu một cổng quan trọng mà không nhận ra.

## 16. Những sai lầm thường gặp

- **Dùng một checklist giống nhau cho mọi cấp độ:** Tạo điều kiện thừa ở kiểm thử nhỏ và thiếu điều kiện quan trọng ở kiểm thử tích hợp hoặc phi chức năng.
- **Dùng từ ngữ mơ hồ:** “Môi trường ổn định” hoặc “dữ liệu đầy đủ” không thể xác minh nhất quán.
- **Nhầm entry criteria với exit criteria:** Điều kiện sẵn sàng trước khi chạy không phải bằng chứng rằng mục tiêu đã đạt.
- **Bắt buộc mọi điều kiện dù không liên quan:** Làm chậm hoạt động mà không tăng độ tin cậy.
- **Không phân biệt must và should:** Nhóm không biết điều kiện nào thực sự ngăn việc bắt đầu.
- **Không chỉ định người xác nhận:** Điều kiện bị bỏ quên vì mọi người nghĩ nhóm khác chịu trách nhiệm.
- **Chấp nhận ngoại lệ không ghi nhận:** Kết quả được diễn giải như đầy đủ dù có giới hạn chưa được công bố.
- **Bỏ qua endpoint và quyền:** Có thể kiểm thử nhầm production hoặc thực hiện hành động ngoài phạm vi.
- **Không xác nhận lại sau khi môi trường thay đổi:** Bằng chứng thu được có thể không còn áp dụng cho cấu hình mới.
- **Coi preflight pass là bảo đảm chất lượng:** Điều kiện bắt đầu chỉ xác nhận mức sẵn sàng, không chứng minh sản phẩm đúng.
- **Không phân biệt blocked với failed:** Môi trường không sẵn sàng không đồng nghĩa sản phẩm không đạt, nhưng cũng không thể tính là đạt.

## 17. Checklist định nghĩa điều kiện bắt đầu

Trước khi phê duyệt entry criteria cho một hoạt động, nhóm có thể dùng checklist sau:

- [ ] Mục tiêu, phạm vi và cấp độ kiểm thử đã rõ.
- [ ] Yêu cầu, tiêu chí chấp nhận và rủi ro liên quan có phiên bản xác định.
- [ ] Sản phẩm/build và cấu hình cần kiểm tra đã sẵn sàng.
- [ ] Test case, checklist, oracle và cách ghi bằng chứng đã được chuẩn bị.
- [ ] Môi trường, dịch vụ phụ thuộc, mạng và endpoint đã được xác minh.
- [ ] Dữ liệu, tài khoản, quyền và cơ chế setup/reset phù hợp.
- [ ] Công cụ, license, log, trace và metric cần thiết hoạt động.
- [ ] Các điều kiện bắt buộc và khuyến nghị được phân loại rõ.
- [ ] Mỗi điều kiện có bằng chứng và người xác nhận.
- [ ] Có phương án khi điều kiện chưa đạt: trì hoãn, thu hẹp, thay thế hoặc ngoại lệ.
- [ ] Quyền chấp nhận ngoại lệ và rủi ro còn lại được xác định.
- [ ] Có tiêu chí tạm dừng và điều kiện tiếp tục khi môi trường thay đổi.
- [ ] Trạng thái preflight và quyết định bắt đầu được lưu để truy vết.

Định nghĩa điều kiện bắt đầu theo từng hoạt động giúp nhóm kiểm thử đúng thời điểm, trên đầu vào và môi trường phù hợp. Khi điều kiện được viết rõ, có thể xác minh, gắn với người sở hữu và tương xứng với rủi ro, nhóm giảm kết quả nhiễu, sử dụng nguồn lực hiệu quả và biết chính xác giới hạn của bằng chứng trước khi đưa ra quyết định chất lượng.
