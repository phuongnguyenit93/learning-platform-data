# Quản lý ngoại lệ có thời hạn và biện pháp giảm thiểu

Tiêu chí chất lượng và quality gate giúp nhóm quyết định khi nào một thay đổi đủ điều kiện đi tiếp. Tuy nhiên, có lúc một kiểm tra bắt buộc chưa thể đạt: một test quan trọng đang không ổn định, dịch vụ phụ thuộc chưa sẵn sàng, lỗ hổng cần thời gian khắc phục hoặc ngưỡng hiệu năng chưa đáp ứng trong môi trường đặc biệt. Nếu chặn mọi công việc mà không có cơ chế xử lý, tiến độ có thể bị đình trệ. Nếu bỏ qua kiểm tra mà không ghi nhận, nhóm sẽ mất dấu rủi ro và dễ biến giải pháp tạm thời thành trạng thái bình thường.

**Ngoại lệ có thời hạn** là quyết định cho phép một phạm vi cụ thể tiếp tục khi một tiêu chí chưa được đáp ứng, trong khoảng thời gian xác định và dưới những điều kiện kiểm soát đã phê duyệt. Ngoại lệ phải nêu rõ rủi ro còn lại, người chấp nhận rủi ro, biện pháp giảm thiểu, thời điểm hết hiệu lực và hành động đưa hệ thống trở lại trạng thái tuân thủ.

Quản lý ngoại lệ là một phần của chiến lược chất lượng. Nó giúp nhóm xử lý tình huống thực tế mà vẫn giữ được tính minh bạch, khả năng truy vết và trách nhiệm đối với rủi ro.

## 1. Ngoại lệ trong tiêu chí chất lượng là gì?

Ngoại lệ (exception hoặc waiver) là sự chấp thuận có kiểm soát để tạm thời không áp dụng hoặc chưa đáp ứng một tiêu chí đã xác định. Ví dụ:

- Một test hồi quy quan trọng bị flaky do lỗi môi trường và cần được quarantine trong lúc sửa.
- Một kiểm tra tích hợp với sandbox của nhà cung cấp không thể chạy trong cửa sổ bảo trì đã biết.
- Một ngưỡng hiệu năng chưa đạt trên cấu hình ít được sử dụng, trong khi nhóm đang triển khai biện pháp giảm tải.
- Một cảnh báo dependency đã được xác nhận có phạm vi ảnh hưởng hạn chế, nhưng cần thời gian nâng cấp và kiểm tra tương thích.
- Một bước kiểm tra thủ công phải thay thế tạm thời cho bước tự động hóa chưa khả dụng.

Ngoại lệ không có nghĩa là kiểm tra đã đạt. Nó ghi nhận rằng một tiêu chí chưa đạt hoặc chưa có đủ bằng chứng, nhưng người có thẩm quyền đã chấp nhận một rủi ro cụ thể trong phạm vi và thời hạn nhất định.

### 1.1. Phân biệt ngoại lệ với các trạng thái khác

| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| Đạt (pass) | Tiêu chí được đáp ứng với bằng chứng hợp lệ | Cho phép chuyển tiếp nếu các gate khác cũng đạt |
| Không đạt (fail) | Có bằng chứng cho thấy tiêu chí bị vi phạm | Sửa lỗi hoặc đánh giá quyết định phát hành theo quy trình |
| Chưa có bằng chứng (not run/unknown) | Kiểm tra chưa chạy hoặc không thể kết luận | Không tự coi là đạt; xác định lý do và hành động |
| Ngoại lệ (waiver) | Một tiêu chí cụ thể được miễn trừ tạm thời theo quyết định được phê duyệt | Theo dõi rủi ro, biện pháp bù trừ và hạn hết hiệu lực |
| Quarantine | Một test hoặc nhóm test bị cách ly để điều tra vì kết quả không đáng tin | Ghi rõ khoảng trống bao phủ, owner và hạn xử lý |
| Rủi ro được chấp nhận lâu dài | Tổ chức quyết định sống chung với rủi ro sau đánh giá chính thức | Quản lý theo quy trình risk acceptance riêng, có rà soát định kỳ |

Quarantine là một biện pháp kỹ thuật có thể đi kèm ngoại lệ, nhưng hai khái niệm không đồng nghĩa. Một test bị quarantine không tự động cho phép bỏ qua gate nếu chưa có quyết định chấp thuận rủi ro.

### 1.2. Ngoại lệ không thay đổi kết quả kiểm thử

Nếu một kiểm tra thất bại, báo cáo vẫn phải thể hiện thất bại. Ngoại lệ chỉ thay đổi quyết định xử lý của gate trong phạm vi đã phê duyệt; nó không được sửa kết quả thành pass, xóa lịch sử lỗi hoặc làm mất dấu kiểm tra bị bỏ qua.

## 2. Nguyên tắc quản lý ngoại lệ

Một cơ chế ngoại lệ đáng tin cậy cần tuân thủ các nguyên tắc:

- **Cụ thể:** nêu đúng tiêu chí, test, thành phần, phiên bản và phạm vi bị ảnh hưởng.
- **Có lý do:** mô tả nguyên nhân và vì sao chưa thể khắc phục ngay.
- **Dựa trên rủi ro:** đánh giá khả năng xảy ra, hậu quả và mức phơi nhiễm.
- **Có kiểm soát bù trừ:** giảm xác suất hoặc tác động trong thời gian ngoại lệ.
- **Có chủ sở hữu:** một người hoặc vai trò chịu trách nhiệm khắc phục và theo dõi.
- **Có người chấp thuận:** người có thẩm quyền phù hợp với mức rủi ro.
- **Có thời hạn:** xác định ngày hết hiệu lực và mốc rà soát.
- **Có thể truy vết:** liên kết với build, commit, release, issue và bằng chứng.
- **Không tự gia hạn:** mọi lần gia hạn phải được đánh giá và phê duyệt lại.
- **Được đóng khi có bằng chứng:** ngoại lệ kết thúc khi tiêu chí được khôi phục hoặc rủi ro được chuyển sang quy trình chấp nhận lâu dài.

Ngoại lệ càng rộng, kéo dài hoặc liên quan đến dữ liệu, bảo mật và giao dịch quan trọng thì mức thẩm quyền và bằng chứng cần thiết càng cao.

## 3. Khi nào có thể xem xét ngoại lệ?

Ngoại lệ có thể phù hợp khi:

- Có sự cố hoặc gián đoạn môi trường ngoài khả năng kiểm soát trực tiếp của nhóm.
- Một test không ổn định đã được xác nhận và đang có kế hoạch sửa.
- Có thay đổi khẩn cấp để xử lý sự cố sản xuất, nhưng một kiểm tra ít liên quan chưa thể hoàn tất.
- Phụ thuộc bên ngoài đang bảo trì hoặc sandbox không cung cấp một khả năng cần thiết.
- Có biện pháp kiểm tra thay thế cung cấp bằng chứng đủ để giảm rủi ro trong thời gian ngắn.
- Việc sửa ngay có thể tạo rủi ro lớn hơn, chẳng hạn nâng cấp dependency chưa được kiểm tra tương thích.

### 3.1. Trường hợp không nên dùng ngoại lệ

Không nên dùng ngoại lệ để:

- Che giấu lỗi sản phẩm hoặc làm đẹp tỷ lệ pass.
- Bỏ qua một kiểm tra chỉ vì pipeline đang chậm mà không đánh giá hậu quả.
- Né tránh review, phê duyệt hoặc trách nhiệm của người sở hữu.
- Vô hiệu hóa kiểm tra hàng loạt để một release được thông qua.
- Gia hạn vô thời hạn một test bị flaky hoặc một lỗ hổng chưa xử lý.
- Thay thế một nghĩa vụ pháp lý, quy định bắt buộc hoặc yêu cầu an toàn không có quyền miễn trừ.
- Chấp nhận rủi ro nghiêm trọng khi không có biện pháp kiểm soát khả thi.

Nếu yêu cầu thuộc loại không thể miễn trừ, nhóm phải đáp ứng yêu cầu hoặc dừng quyết định chuyển giai đoạn cho đến khi có phương án hợp lệ. Việc gọi một quyết định là waiver không làm thay đổi nghĩa vụ bắt buộc của tổ chức.

## 4. Đánh giá rủi ro trước khi xin ngoại lệ

Trước khi đề xuất ngoại lệ, cần xác định chính xác điều gì có thể xảy ra nếu tiêu chí chưa được đáp ứng.

### 4.1. Xác định phạm vi

Ghi lại:

- Tiêu chí hoặc quality gate chưa đạt.
- Test case, rule, module, dịch vụ hoặc môi trường liên quan.
- Commit, build, release hoặc phiên bản bị ảnh hưởng.
- Người dùng, dữ liệu và quy trình nghiệp vụ có thể chịu tác động.
- Thời điểm bắt đầu và thời gian dự kiến cần ngoại lệ.
- Những kiểm tra liên quan vẫn đạt và những kiểm tra chưa có bằng chứng.

Không dùng mô tả chung như "tạm bỏ qua regression". Hãy chỉ rõ test nào, trong suite nào, cho thành phần nào và phiên bản nào.

### 4.2. Đánh giá khả năng xảy ra và hậu quả

Có thể xem xét các chiều:

| Chiều đánh giá | Câu hỏi |
|---|---|
| Khả năng xảy ra | Lỗi hoặc sự cố có thể xuất hiện thường xuyên đến mức nào? |
| Mức độ tác động | Nếu xảy ra, ảnh hưởng đến người dùng, dữ liệu, tiền, bảo mật hoặc vận hành ra sao? |
| Mức phơi nhiễm | Bao nhiêu người dùng, giao dịch, tenant hoặc môi trường chịu ảnh hưởng? |
| Khả năng phát hiện | Có thể nhận biết nhanh qua log, metric, alert hoặc đối soát không? |
| Khả năng phục hồi | Có thể rollback, tắt feature, khôi phục dữ liệu hoặc xử lý thủ công không? |
| Thời gian tồn tại | Rủi ro sẽ kéo dài bao lâu và có thể tăng lên khi điều kiện thay đổi không? |
| Độ tin cậy của bằng chứng | Kết luận dựa trên dữ liệu thực, mô phỏng hay giả định? |

Có thể dùng ma trận xác suất và tác động để phân loại mức rủi ro. Nếu tổ chức có thang điểm riêng, sử dụng thang đó nhất quán. Không nên cộng điểm máy móc để làm một rủi ro nghiêm trọng trở thành chấp nhận được; các yếu tố như dữ liệu nhạy cảm, an toàn, tính toàn vẹn giao dịch hoặc nghĩa vụ tuân thủ có thể cần tiêu chí chặn riêng.

### 4.3. Xác định rủi ro còn lại

Rủi ro ban đầu là rủi ro khi chưa có biện pháp kiểm soát. Rủi ro còn lại là phần rủi ro vẫn tồn tại sau khi áp dụng các biện pháp giảm thiểu.

Ví dụ, một test thanh toán E2E chưa chạy được vì sandbox bảo trì. Nếu nhóm có contract test, integration test nội bộ, kiểm tra chữ ký callback trên fixture đã xác minh và đối soát dữ liệu thử nghiệm, một phần rủi ro có thể giảm. Tuy nhiên, nhóm vẫn chưa có bằng chứng giao dịch thực sự hoạt động với sandbox trong build này; phần thiếu đó phải được ghi rõ.

## 5. Thiết kế biện pháp giảm thiểu

Biện pháp giảm thiểu (mitigation) làm giảm xác suất, tác động hoặc thời gian phát hiện và phục hồi trong thời gian ngoại lệ. Nó không nhất thiết loại bỏ rủi ro.

### 5.1. Ưu tiên loại bỏ nguyên nhân

Nếu có thể khắc phục nhanh và an toàn, sửa nguyên nhân là lựa chọn tốt nhất. Ví dụ, sửa cấu hình môi trường khiến test timeout hoặc cập nhật fixture không tương thích có thể khôi phục kiểm tra mà không cần ngoại lệ dài hạn.

### 5.2. Thu hẹp phạm vi phơi nhiễm

Nếu chưa thể khắc phục ngay, giảm phạm vi chịu rủi ro:

- Chỉ áp dụng cho một module, endpoint, tenant hoặc nhóm người dùng.
- Dùng feature flag để tắt chức năng có rủi ro.
- Giới hạn lưu lượng hoặc số giao dịch.
- Chỉ triển khai cho môi trường thử nghiệm hoặc nhóm canary nhỏ.
- Không mở rộng rollout cho đến khi có bằng chứng bổ sung.

### 5.3. Bổ sung kiểm tra thay thế

Chọn kiểm tra cung cấp bằng chứng gần nhất với mục tiêu ban đầu:

- Contract test thay cho một phần kiểm tra tích hợp chưa khả dụng.
- API test hoặc component test thay cho UI test đang lỗi do browser.
- Kiểm tra thủ công có checklist và bằng chứng khi tự động hóa chưa chạy được.
- Kiểm tra dữ liệu hoặc đối soát độc lập khi một luồng E2E chưa thể hoàn tất.
- Security scan hoặc review bổ sung trong khi một công cụ quét đang gặp sự cố.

Kiểm tra thay thế phải được ghi là bằng chứng thay thế và nêu rõ giới hạn. Ví dụ, contract test không chứng minh nhà cung cấp bên ngoài đang sẵn sàng; kiểm tra thủ công không tạo ra cùng mức tái lập như automation.

### 5.4. Tăng cường giám sát và phát hiện

Trong thời gian ngoại lệ, có thể tăng:

- Log và metric tại thành phần liên quan.
- Alert cho error rate, latency, timeout hoặc trạng thái bất thường.
- Theo dõi giao dịch tổng hợp an toàn.
- Đối soát dữ liệu theo chu kỳ ngắn hơn.
- Review thủ công kết quả trước khi mở rộng rollout.
- Theo dõi dashboard hoặc trace theo run ID và phiên bản.

Giám sát chỉ có giá trị khi có người nhận cảnh báo, ngưỡng hành động và quy trình phản ứng. Một dashboard không ai theo dõi không phải biện pháp kiểm soát hữu hiệu.

### 5.5. Chuẩn bị phục hồi

Xác định trước:

- Điều kiện dừng rollout hoặc tắt feature.
- Cách rollback hoặc roll-forward.
- Cách khôi phục dữ liệu và đối soát giao dịch.
- Người trực xử lý và kênh liên lạc.
- Hành động nếu biện pháp giảm thiểu không hoạt động.

Biện pháp giảm thiểu cần tương xứng với rủi ro và có thể kiểm chứng. "Theo dõi kỹ hơn" chưa đủ nếu không nêu chỉ số, ngưỡng, người nhận và hành động.

## 6. Quy trình quản lý ngoại lệ từ đầu đến cuối

### Bước 1: Phát hiện và ghi nhận

Khi quality gate không đạt hoặc không có đủ bằng chứng, tạo bản ghi ngoại lệ hoặc yêu cầu xem xét. Lưu kết quả gốc, log, build ID, test ID và môi trường.

### Bước 2: Phân loại nguyên nhân

Xác định vấn đề thuộc:

- Lỗi sản phẩm.
- Lỗi test hoặc flaky test.
- Lỗi dữ liệu.
- Lỗi môi trường hoặc hạ tầng.
- Phụ thuộc bên ngoài.
- Thiếu năng lực hoặc công cụ.
- Thay đổi yêu cầu hoặc tiêu chí chưa được cập nhật.

Không nên xin ngoại lệ trước khi hiểu nguyên nhân ở mức đủ để đánh giá rủi ro.

### Bước 3: Đánh giá tác động và rủi ro

Ghi rõ phạm vi, khả năng xảy ra, hậu quả, mức phơi nhiễm, khả năng phát hiện và phục hồi. Xác định phần nào chưa có bằng chứng.

### Bước 4: Đề xuất biện pháp giảm thiểu

Chọn biện pháp có thể thực hiện ngay, có người chịu trách nhiệm và có cách xác minh. Nêu rõ giới hạn của từng biện pháp và điều kiện dừng nếu rủi ro vượt ngưỡng.

### Bước 5: Xin phê duyệt đúng thẩm quyền

Người đề xuất không nên tự phê duyệt ngoại lệ cho rủi ro mà chính họ chịu trách nhiệm khắc phục nếu chính sách yêu cầu tách vai trò. Người phê duyệt phải có thẩm quyền tương ứng với mức tác động và phạm vi.

### Bước 6: Gắn ngoại lệ với pipeline hoặc quyết định phát hành

Gắn mã ngoại lệ vào build, PR, release hoặc quality gate cụ thể. Pipeline cần biết ngoại lệ nào đang có hiệu lực, áp dụng cho tiêu chí nào và khi nào hết hạn.

### Bước 7: Theo dõi trong thời hạn

Theo dõi biện pháp giảm thiểu, trạng thái khắc phục và các tín hiệu bất thường. Nhắc owner trước hạn đủ sớm để xử lý hoặc xin rà soát lại.

### Bước 8: Đóng, hết hạn hoặc gia hạn có kiểm soát

Đóng ngoại lệ khi tiêu chí gốc đã đạt và có bằng chứng. Nếu hết hạn mà chưa khắc phục, ngoại lệ tự mất hiệu lực theo chính sách; cần dừng quyết định bị ảnh hưởng hoặc xin phê duyệt mới trước khi tiếp tục. Gia hạn phải có đánh giá rủi ro cập nhật và lý do mới.

## 7. Nội dung bắt buộc của một bản ghi ngoại lệ

Một bản ghi tốt cần đủ thông tin để người không tham gia cuộc trao đổi ban đầu vẫn hiểu quyết định.

| Trường | Nội dung |
|---|---|
| Exception ID | Mã định danh duy nhất |
| Tiêu chí bị ngoại lệ | Quality gate, test, rule hoặc ngưỡng cụ thể |
| Phạm vi | Dịch vụ, module, môi trường, phiên bản, PR/build/release |
| Trạng thái gốc | Pass, fail, not run, flaky hoặc chưa có bằng chứng |
| Lý do | Nguyên nhân và vì sao chưa thể khắc phục ngay |
| Rủi ro | Khả năng xảy ra, tác động, mức phơi nhiễm và rủi ro còn lại |
| Biện pháp giảm thiểu | Kiểm soát thay thế, giới hạn phạm vi, giám sát và phục hồi |
| Owner khắc phục | Người chịu trách nhiệm đưa tiêu chí về trạng thái bình thường |
| Người phê duyệt | Vai trò/người chấp nhận rủi ro theo thẩm quyền |
| Ngày tạo và hết hạn | Thời điểm bắt đầu, ngày/giờ hết hiệu lực |
| Mốc rà soát | Ngày kiểm tra tiến độ trước khi hết hạn |
| Điều kiện đóng | Bằng chứng cần có để kết thúc ngoại lệ |
| Liên kết | Ticket, incident, test report, build, PR và release |
| Lịch sử | Thay đổi phạm vi, gia hạn, phê duyệt và quyết định |

Nên lưu bản ghi trong hệ thống có kiểm soát truy cập và audit trail. Nếu dùng ticket, cần bảo đảm các trường thời hạn, owner, trạng thái và liên kết build không bị bỏ trống.

## 8. Thời hạn, nhắc việc và gia hạn

### 8.1. Chọn thời hạn phù hợp

Thời hạn phải đủ ngắn để tạo áp lực xử lý nhưng đủ thực tế để hoàn tất công việc đã xác định. Có thể căn cứ vào:

- Mức độ nghiêm trọng và phạm vi ảnh hưởng.
- Tốc độ thay đổi của rủi ro.
- Lịch phát hành và cửa sổ bảo trì.
- Khả năng có biện pháp thay thế.
- Thời gian cần thiết để tái tạo, sửa và xác minh.

Không nên đặt một thời hạn mặc định giống nhau cho mọi loại ngoại lệ. Rủi ro bảo mật hoặc dữ liệu nhạy cảm thường cần thời hạn ngắn và kiểm soát mạnh hơn một kiểm tra báo cáo ít ảnh hưởng.

### 8.2. Tự động hóa nhắc việc và hết hạn

Hệ thống quản lý ngoại lệ có thể:

- Nhắc owner trước ngày hết hạn.
- Nhắc người phê duyệt khi ngoại lệ gần đến hạn.
- Hiển thị ngoại lệ đang hoạt động trên dashboard release.
- Cảnh báo khi ticket khắc phục quá hạn.
- Từ chối áp dụng ngoại lệ sau thời điểm hết hạn.
- Lưu lịch sử gia hạn và người phê duyệt.

Nếu pipeline không thể xác minh trạng thái hoặc thời hạn của ngoại lệ, không nên mặc định cho phép bypass. Cần có hành vi an toàn được định nghĩa rõ, chẳng hạn yêu cầu kiểm tra lại hoặc chặn gate cho đến khi xác minh được quyết định.

### 8.3. Điều kiện gia hạn

Gia hạn không phải thao tác đổi ngày đơn thuần. Người đề xuất cần:

1. Nêu lý do chưa hoàn thành hành động khắc phục.
2. Cập nhật đánh giá rủi ro và phạm vi.
3. Cung cấp bằng chứng biện pháp giảm thiểu vẫn hoạt động.
4. Xác định thời hạn mới và mốc hoàn tất cụ thể.
5. Xin người có thẩm quyền phê duyệt lại.

Nếu ngoại lệ liên tục được gia hạn, cần xem xét liệu vấn đề đã trở thành rủi ro thường trực cần xử lý ở cấp kiến trúc, ngân sách hoặc quy trình. Không dùng chuỗi gia hạn để che giấu việc không có kế hoạch khắc phục.

## 9. Áp dụng ngoại lệ trong CI/CD

Ngoại lệ cần được thực thi nhất quán trong pipeline thay vì dựa vào lời nhắn hoặc thao tác thủ công không có dấu vết.

### 9.1. Gắn với đúng phạm vi

Một exception ID cần liên kết với:

- Rule hoặc test cụ thể.
- Repository, module hoặc dịch vụ.
- Branch, build hoặc release được phép áp dụng.
- Môi trường được phép.
- Ngày hết hạn.
- Người phê duyệt.

Không nên tạo một cờ bypass toàn cục có thể bỏ qua nhiều kiểm tra ngoài phạm vi đã phê duyệt.

### 9.2. Quy tắc quyết định của pipeline

Ví dụ logic:

~~~text
if quality_check == PASS:
    continue_pipeline()
elif valid_exception_exists(
    check_id,
    component,
    build,
    environment,
    current_time
):
    record_waiver_and_mitigation()
    continue_only_within_approved_scope()
else:
    block_gate()
~~~

Đây là logic minh họa. Hệ thống thực tế cần xác thực nguồn dữ liệu của ngoại lệ, quyền phê duyệt, phạm vi và thời hạn. Pipeline phải lưu kết quả kiểm tra gốc và exception ID vào báo cáo.

### 9.3. Hành vi khi ngoại lệ hết hạn

Khi ngoại lệ hết hạn:

- Không áp dụng bypass cho build hoặc quyết định mới.
- Đánh dấu ngoại lệ là expired và thông báo owner.
- Chặn quality gate liên quan hoặc yêu cầu quyết định mới theo chính sách.
- Giữ nguyên lịch sử để truy vết các release trước đó.
- Không tự động xóa ngoại lệ hoặc thay kết quả test cũ.

Việc xử lý hệ thống đã triển khai cần theo quy trình incident/risk riêng; hết hạn waiver không tự động thay thế đánh giá vận hành hoặc rollback.

## 10. Ví dụ 1: quarantine một test E2E không ổn định

Giả sử test E2E kiểm tra thanh toán sandbox thất bại ngẫu nhiên do callback của sandbox đôi khi đến chậm. Test này thuộc regression quan trọng trước phát hành.

### Tình trạng

- Test có lịch sử chạy không ổn định.
- Log cho thấy một số lần timeout trước khi callback đến.
- Chưa có bằng chứng lỗi nằm ở logic thanh toán của ứng dụng.
- Nếu bỏ test, nhóm mất bằng chứng về hành trình thanh toán hoàn chỉnh.

### Ngoại lệ đề xuất

- Phạm vi: chỉ test E2E thanh toán sandbox của một dịch vụ và một release candidate.
- Biện pháp giảm thiểu: chạy contract test, integration test adapter, kiểm tra chữ ký callback bằng fixture đã xác minh và đối soát trạng thái giao dịch thử nghiệm.
- Giám sát: ghi nhận callback delay và timeout; có người review kết quả trước khi release.
- Owner: nhóm sở hữu adapter thanh toán.
- Hạn: một khoảng thời gian ngắn đủ để sửa cơ chế chờ và xác minh lại.
- Điều kiện đóng: test chạy ổn định qua số lần lặp đã định, callback được xác minh và ngoại lệ được thu hồi.

Ngoại lệ này không biến E2E thành pass. Báo cáo vẫn thể hiện test bị quarantine và các bằng chứng thay thế. Nếu các kiểm tra thay thế không đạt, release gate vẫn phải dừng theo chính sách.

## 11. Ví dụ 2: ngoại lệ tạm thời cho một lỗ hổng dependency

Giả sử công cụ quét dependency phát hiện một lỗ hổng trong thư viện được dùng bởi một module. Bản nâng cấp đã có nhưng cần kiểm tra tương thích vì thư viện ảnh hưởng đến một giao thức quan trọng.

### Đánh giá

- Xác định phiên bản thư viện, module sử dụng và đường gọi có thể bị ảnh hưởng.
- Xác minh mức độ nghiêm trọng, điều kiện khai thác và khả năng tiếp cận từ bên ngoài.
- Xem xét liệu ứng dụng có bật chức năng liên quan hoặc có thể bị khai thác trong môi trường đích.
- Xác định dữ liệu, quyền và dịch vụ có thể chịu tác động.

### Biện pháp giảm thiểu có thể xem xét

- Tắt hoặc giới hạn chức năng có rủi ro nếu có thể.
- Hạn chế endpoint hoặc đường truy cập liên quan.
- Tăng giám sát log và tín hiệu khai thác.
- Chặn triển khai ở môi trường phơi nhiễm cao nếu không có biện pháp đủ mạnh.
- Chạy kiểm thử tương thích trên nhánh nâng cấp và lập lịch triển khai sớm.

Người có thẩm quyền bảo mật phải đánh giá rủi ro còn lại. Nếu không thể giảm rủi ro xuống mức chấp nhận được hoặc lỗ hổng thuộc điều kiện không được miễn trừ, không cấp ngoại lệ. Ngoại lệ được phê duyệt phải có thời hạn ngắn, owner và kế hoạch nâng cấp cụ thể.

## 12. Vai trò và trách nhiệm

| Vai trò | Trách nhiệm |
|---|---|
| Người đề xuất | Mô tả tiêu chí chưa đạt, nguyên nhân, phạm vi và biện pháp giảm thiểu |
| Owner khắc phục | Lập kế hoạch sửa, cập nhật tiến độ và cung cấp bằng chứng đóng |
| Người phê duyệt rủi ro | Đánh giá rủi ro còn lại và quyết định trong phạm vi thẩm quyền |
| QA/Test lead | Đánh giá ảnh hưởng đến độ bao phủ, tính hợp lệ của test và bằng chứng thay thế |
| Security/Compliance | Tham gia khi liên quan đến bảo mật, dữ liệu hoặc nghĩa vụ tuân thủ |
| Release manager/Engineering lead | Xem xét các ngoại lệ đang hoạt động trước quyết định phát hành |
| Platform/CI owner | Thực thi phạm vi, thời hạn và audit trail trong pipeline |

Một người có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ, nhưng cần tránh tự phê duyệt rủi ro vượt quá thẩm quyền của mình. Với rủi ro nghiêm trọng, nên có đánh giá độc lập.

## 13. Theo dõi ngoại lệ và các chỉ số quản trị

Dashboard ngoại lệ nên hiển thị:

- Số ngoại lệ đang hoạt động theo mức rủi ro.
- Ngoại lệ sắp hết hạn hoặc đã hết hạn.
- Số lần gia hạn và thời gian tồn tại trung bình.
- Ngoại lệ theo module, loại kiểm tra và môi trường.
- Tỷ lệ ngoại lệ có owner, approver và mitigation đầy đủ.
- Số ngoại lệ chưa có ticket khắc phục.
- Số ngoại lệ đóng đúng hạn.
- Số sự cố có liên quan đến ngoại lệ đã phê duyệt.
- Số lần pipeline bypass ngoài phạm vi hoặc thất bại khi xác minh waiver.

Một số chỉ số cần diễn giải cẩn thận:

- Số ngoại lệ thấp không nhất thiết chứng minh chất lượng cao; có thể nhóm không ghi nhận ngoại lệ.
- Tỷ lệ đóng đúng hạn cao không đủ nếu các ngoại lệ được gia hạn liên tục.
- Thời gian tồn tại dài có thể chỉ ra vấn đề cấu trúc, thiếu nguồn lực hoặc tiêu chí không thực tế.
- Sự cố liên quan ngoại lệ cần được phân tích theo mức độ đóng góp của rủi ro và hiệu lực của biện pháp giảm thiểu.

Mục tiêu là giảm rủi ro tồn đọng và cải thiện quy trình, không tạo động lực để nhóm che giấu ngoại lệ.

## 14. Kiểm toán và truy vết quyết định

Với mỗi ngoại lệ, cần có lịch sử bất biến hoặc audit trail thể hiện:

- Ai tạo và thời điểm tạo.
- Ai đánh giá, ai phê duyệt và dựa trên bằng chứng nào.
- Nội dung và phạm vi đã được phê duyệt.
- Các thay đổi về thời hạn, owner và biện pháp giảm thiểu.
- Các build/release đã sử dụng ngoại lệ.
- Các cảnh báo, sự cố hoặc hành động phát sinh.
- Thời điểm đóng, hết hạn hoặc thu hồi và lý do.

Khi điều tra sự cố, nhóm cần biết một quality gate đã bị miễn trừ hay không và người nào đã chấp nhận rủi ro. Nếu thiếu audit trail, tổ chức khó đánh giá quyết định trước đó và cải thiện chính sách.

## 15. Những sai lầm thường gặp

- **Ngoại lệ không có ngày hết hạn:** biến quyết định tạm thời thành bỏ qua vĩnh viễn.
- **Không có owner khắc phục:** không ai chịu trách nhiệm đưa tiêu chí về trạng thái đạt.
- **Biện pháp giảm thiểu chung chung:** không thể xác minh hiệu quả hoặc biết khi nào cần dừng.
- **Phạm vi quá rộng:** một ngoại lệ cho một test vô tình bỏ qua cả suite hoặc module.
- **Người đề xuất tự phê duyệt mọi rủi ro:** thiếu kiểm soát độc lập khi tác động lớn.
- **Gia hạn tự động:** không xem xét rủi ro, điều kiện môi trường hoặc bằng chứng mới.
- **Xem waiver là pass:** làm sai lệch báo cáo chất lượng.
- **Không ghi nhận kiểm tra thay thế:** người ra quyết định không biết bằng chứng nào còn thiếu.
- **Không xử lý khi hết hạn:** pipeline tiếp tục bypass dù không còn quyết định hợp lệ.
- **Không lưu lịch sử:** không thể truy vết build/release đã dùng ngoại lệ.
- **Dùng ngoại lệ để che flaky test:** không sửa nguyên nhân khiến test mất độ tin cậy.
- **Bỏ qua nghĩa vụ không thể miễn trừ:** tạo rủi ro pháp lý, bảo mật hoặc an toàn không được phép chấp nhận.

## 16. Checklist quản lý ngoại lệ

- [ ] Tiêu chí chưa đạt hoặc chưa có bằng chứng được xác định chính xác.
- [ ] Kết quả gốc vẫn được lưu và hiển thị đúng trạng thái.
- [ ] Nguyên nhân, phạm vi và phiên bản bị ảnh hưởng được ghi rõ.
- [ ] Rủi ro được đánh giá theo khả năng, tác động, phơi nhiễm và khả năng phục hồi.
- [ ] Xác định yêu cầu có được phép miễn trừ hay không.
- [ ] Biện pháp giảm thiểu có owner, cách kiểm chứng và điều kiện dừng.
- [ ] Bằng chứng thay thế và giới hạn của nó được ghi nhận.
- [ ] Người phê duyệt có thẩm quyền phù hợp.
- [ ] Exception ID liên kết với PR, build, release và ticket khắc phục.
- [ ] Ngày hết hạn và mốc rà soát được đặt rõ.
- [ ] Pipeline xác minh phạm vi và thời hạn trước khi bypass gate.
- [ ] Có nhắc việc, cảnh báo và xử lý khi hết hạn.
- [ ] Gia hạn cần đánh giá và phê duyệt lại.
- [ ] Có điều kiện đóng và bằng chứng khôi phục tiêu chí.
- [ ] Audit trail được lưu để điều tra và kiểm toán.

## 17. Luồng quyết định và vòng đời ngoại lệ

~~~mermaid
flowchart TD
    A["Quality gate không đạt hoặc thiếu bằng chứng"]
    B["Ghi nhận kết quả và phạm vi"]
    C["Phân loại nguyên nhân và đánh giá rủi ro"]
    D{"Có thể khắc phục ngay?"}
    E["Sửa nguyên nhân và chạy lại kiểm tra"]
    F{"Có được phép xem xét ngoại lệ?"}
    G["Dừng chuyển giai đoạn và xử lý theo yêu cầu bắt buộc"]
    H["Đề xuất mitigation, owner và thời hạn"]
    I{"Đúng thẩm quyền phê duyệt?"}
    J["Từ chối hoặc bổ sung bằng chứng"]
    K["Gắn exception ID vào gate và theo dõi"]
    L{"Tiêu chí đã được khôi phục trước hạn?"}
    M["Đóng ngoại lệ và lưu bằng chứng"]
    N["Hết hạn: chặn bypass, đánh giá lại hoặc xin phê duyệt mới"]
    A --> B --> C --> D
    D -->|Có| E --> L
    D -->|Không| F
    F -->|Không| G
    F -->|Có| H --> I
    I -->|Không| J --> H
    I -->|Có| K --> L
    L -->|Có| M
    L -->|Không| N
    N --> C
~~~

Ngoại lệ có thời hạn giúp nhóm tiếp tục công việc trong những tình huống có lý do mà vẫn giữ rõ ràng phần chất lượng chưa được chứng minh. Khi mỗi ngoại lệ có phạm vi cụ thể, đánh giá rủi ro, biện pháp giảm thiểu kiểm chứng được, người chịu trách nhiệm, người phê duyệt và ngày hết hạn, nhóm có thể quản lý rủi ro tạm thời mà không làm suy yếu ý nghĩa của quality gate. Mục tiêu cuối cùng luôn là khôi phục tiêu chí gốc, đóng ngoại lệ bằng bằng chứng và dùng dữ liệu tích lũy để giảm nhu cầu miễn trừ trong tương lai.
