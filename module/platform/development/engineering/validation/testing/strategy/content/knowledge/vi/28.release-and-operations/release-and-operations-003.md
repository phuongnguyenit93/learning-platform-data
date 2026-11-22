# Trình bày rủi ro còn lại cùng phương án giảm thiểu

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, kết quả kiểm thử và đánh giá phát hành không chỉ cho biết những tiêu chí đã đạt. Chúng còn phải làm rõ những điều chưa được xác minh, lỗi chưa khắc phục, giới hạn của môi trường, phụ thuộc chưa được kiểm soát và những tình huống vẫn có thể gây ảnh hưởng sau khi triển khai. Các yếu tố đó tạo thành **rủi ro còn lại** (residual risk) mà tổ chức cần hiểu trước khi quyết định phát hành và tiếp tục theo dõi trong vận hành.

Trình bày rủi ro còn lại là việc chuyển thông tin kỹ thuật và bằng chứng kiểm thử thành nội dung rõ ràng để người có trách nhiệm có thể đánh giá: điều gì có thể xảy ra, ảnh hưởng đến ai hoặc tài sản nào, khả năng và mức độ tác động ra sao, biện pháp nào đang giảm thiểu rủi ro, phần nào vẫn chưa được kiểm soát, ai sở hữu rủi ro và điều kiện nào buộc phải xem xét lại quyết định. Một báo cáo chỉ liệt kê lỗi hoặc ghi “còn rủi ro thấp” không cung cấp đủ thông tin để đưa ra quyết định có trách nhiệm.

Mục tiêu không phải là chứng minh mọi rủi ro đã biến mất. Phần mềm thực tế luôn có giới hạn về thời gian, phạm vi kiểm thử, môi trường, dữ liệu và khả năng dự đoán. Mục tiêu là trình bày trung thực, có căn cứ và có thể hành động để tổ chức quyết định sửa trước khi phát hành, giới hạn rollout, áp dụng biện pháp giảm thiểu, chấp nhận rủi ro theo thẩm quyền hoặc dừng phát hành.

## 1. Rủi ro còn lại là gì?

Rủi ro là tác động của sự không chắc chắn lên mục tiêu. Trong phát triển và phát hành phần mềm, rủi ro có thể liên quan đến chức năng, dữ liệu, bảo mật, quyền riêng tư, hiệu năng, độ tin cậy, khả năng vận hành, tuân thủ, nhà cung cấp hoặc trải nghiệm người dùng.

**Rủi ro còn lại** là phần rủi ro vẫn tồn tại sau khi đã áp dụng các biện pháp kiểm soát hoặc giảm thiểu. Một số kiểm soát có thể làm giảm khả năng xảy ra; một số khác làm giảm mức độ tác động; một số chỉ giúp phát hiện sớm và phục hồi nhanh hơn. Chúng không nhất thiết loại bỏ hoàn toàn tình huống gây rủi ro.

Ví dụ, một dịch vụ có lỗi đồng bộ trạng thái đơn hàng. Nhóm có thể bổ sung cảnh báo khi trạng thái thanh toán và trạng thái đơn không khớp, đồng thời tạo quy trình đối soát thủ công. Những biện pháp này có thể giảm thời gian phát hiện và tác động đến khách hàng, nhưng lỗi gốc vẫn có thể xảy ra. Rủi ro còn lại cần được trình bày cùng giới hạn của cảnh báo và khả năng xử lý thủ công.

### Phân biệt các khái niệm liên quan

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Inherent risk | Rủi ro trước khi tính đến các biện pháp kiểm soát | Webhook thanh toán đến trễ có thể khiến đơn không cập nhật trạng thái |
| Control | Biện pháp ngăn ngừa, phát hiện hoặc giảm tác động | Xử lý webhook idempotent, đối soát định kỳ, cảnh báo trạng thái lệch |
| Residual risk | Rủi ro còn lại sau khi xem xét hiệu quả kiểm soát | Một số trường hợp hiếm vẫn cần đối soát thủ công |
| Defect | Sai lệch đã được xác định trong sản phẩm | Trạng thái đơn không chuyển sau webhook hợp lệ |
| Known issue | Vấn đề đã biết, có thể có workaround nhưng chưa được loại bỏ | Đối tác đôi khi gửi callback ngoài thứ tự |
| Risk acceptance | Quyết định có thẩm quyền chấp nhận rủi ro trong phạm vi và điều kiện xác định | Cho phép rollout giới hạn trong 24 giờ với monitoring và rollback trigger |

Defect và risk có quan hệ nhưng không đồng nhất. Một defect có thể tạo ra một hoặc nhiều rủi ro. Một rủi ro cũng có thể tồn tại dù chưa có defect tái hiện, chẳng hạn chưa kiểm tra một cấu hình hiếm hoặc chưa có bằng chứng về khả năng phục hồi trong tình huống mất vùng.

## 2. Vì sao phải trình bày rủi ro trước phát hành?

Quyết định phát hành thường được đưa ra trong điều kiện thông tin không hoàn hảo. Người quyết định cần biết những gì đã được kiểm tra, những gì chưa được kiểm tra, lỗi nào còn mở và biện pháp nào sẽ bảo vệ người dùng nếu vấn đề xảy ra.

Trình bày rủi ro còn lại giúp:

- **Hỗ trợ Go/No-Go:** người có thẩm quyền hiểu các điều kiện có thể ảnh hưởng đến quyết định phát hành.
- **Ưu tiên khắc phục:** phân biệt rủi ro cần sửa trước release với rủi ro có thể kiểm soát trong phạm vi giới hạn.
- **Xác định trách nhiệm:** làm rõ risk owner, người thực hiện mitigation và người có quyền chấp nhận.
- **Chuẩn bị vận hành:** giúp Operations, SRE và Service Desk biết tín hiệu cần theo dõi và cách ứng phó.
- **Minh bạch với bên liên quan:** tránh tạo kỳ vọng rằng sản phẩm đã được kiểm tra toàn diện khi vẫn còn giới hạn.
- **Bảo vệ khách hàng và dữ liệu:** nhận diện các kịch bản có thể gây tổn thất, gián đoạn hoặc vi phạm nghĩa vụ.
- **Theo dõi sau phát hành:** biến rủi ro thành hành động, cảnh báo, mốc review và điều kiện đóng cụ thể.

Nếu rủi ro không được trình bày, người quyết định có thể hiểu nhầm rằng không có lỗi đồng nghĩa không có rủi ro. Thực tế, không phát hiện lỗi trong phạm vi test không chứng minh mọi trạng thái, dữ liệu và điều kiện đều an toàn.

## 3. Những nguồn tạo ra rủi ro còn lại

Rủi ro còn lại có thể xuất phát từ nhiều nguồn. Báo cáo cần xem xét cả lỗi đã biết lẫn khoảng trống bằng chứng.

### Defect chưa khắc phục

Các lỗi chưa sửa hoặc đã sửa nhưng chưa retest có thể ảnh hưởng đến người dùng, dữ liệu hoặc luồng nghiệp vụ. Cần ghi rõ severity, phạm vi ảnh hưởng, phiên bản liên quan, workaround và trạng thái xác minh.

### Phạm vi kiểm thử chưa bao phủ

Một số browser, thiết bị, vai trò, cấu hình, loại dữ liệu, ngôn ngữ hoặc tình huống tải có thể chưa được kiểm tra. Rủi ro nằm ở phần chưa có bằng chứng, không nhất thiết là lỗi đã được xác nhận.

### Giới hạn môi trường và dữ liệu

Staging có thể không giống production về quy mô, network, quyền, dữ liệu, dịch vụ phụ thuộc hoặc topology. Test dùng dữ liệu tổng hợp có thể không tái hiện đầy đủ đặc tính dữ liệu thực tế. Cần mô tả khác biệt nào có thể ảnh hưởng kết luận.

### Phụ thuộc bên ngoài

Nhà cung cấp API, payment gateway, identity provider, message broker hoặc dịch vụ dữ liệu có thể thay đổi, giới hạn tốc độ hoặc gián đoạn. Sandbox không phải lúc nào cũng phản ánh chính xác production. Rủi ro cần nêu rõ phạm vi nằm ngoài quyền kiểm soát của nhóm.

### Hiệu năng và năng lực tải

Test tải có thể chỉ chạy ở một mức traffic, một vùng hoặc một thời lượng nhất định. Rủi ro còn lại có thể liên quan đến đỉnh tải, tăng trưởng dữ liệu, concurrency, hàng đợi hoặc giới hạn dịch vụ bên ngoài.

### Bảo mật và quyền riêng tư

Các phát hiện chưa xử lý, ngoại lệ cấu hình, quyền quá rộng, dependency có lỗ hổng hoặc giới hạn của đánh giá bảo mật có thể tạo rủi ro. Cần phân biệt phát hiện đã xác nhận với giả thuyết chưa kiểm chứng và tuân theo quy trình chuyên môn.

### Khả năng vận hành và phục hồi

Runbook chưa được diễn tập, cảnh báo chưa kiểm tra, backup chưa restore hoặc chưa xác nhận người trực có thể làm tăng thời gian gián đoạn khi sự cố xảy ra. Việc có tài liệu không tự chứng minh khả năng vận hành.

### Thay đổi muộn và bằng chứng chưa hoàn tất

Một thay đổi sau vòng hồi quy cuối, migration chưa được kiểm tra trên dữ liệu đại diện hoặc test bị quarantine có thể làm giảm độ tin cậy của kết quả. Báo cáo phải nêu rõ các thay đổi và suite chưa chạy lại.

## 4. Thu thập bằng chứng trước khi mô tả rủi ro

Một risk statement đáng tin cần dựa trên dữ liệu và nguồn có thể truy vết. Trước khi viết, nhóm nên tổng hợp bằng chứng từ các hoạt động kiểm thử, vận hành và đánh giá chuyên môn.

### Nguồn bằng chứng

- Defect backlog và các lỗi theo severity/priority.
- Kết quả smoke, core regression và extended regression.
- Test case chưa chạy, bị skip, flaky hoặc quarantine.
- Báo cáo hiệu năng, tải, độ trễ, tỷ lệ lỗi và tài nguyên.
- Security scan, penetration test, dependency scan và các ngoại lệ.
- Kết quả migration, backup/restore và failover rehearsal.
- Monitoring, alert test, log, trace và incident history.
- Contract/API compatibility và tình trạng nhà cung cấp.
- UAT, phản hồi người dùng và kết quả accessibility/usability.
- Release notes, commit, artifact digest và thay đổi cấu hình.

### Gắn bằng chứng với phiên bản

Mỗi kết quả cần liên kết với build hoặc artifact đã kiểm tra, môi trường, cấu hình và thời điểm chạy. Nếu báo cáo test thuộc một artifact cũ nhưng release candidate đã thay đổi, cần xác định test nào phải chạy lại. Không dùng một báo cáo chung không có version để chứng minh cho một release cụ thể.

### Phân biệt dữ kiện, suy luận và giả định

Khi trình bày, cần phân biệt:

- **Dữ kiện:** điều đã quan sát hoặc đo được, ví dụ 3 trong 10.000 request bị timeout trong test.
- **Suy luận:** kết luận được rút ra từ dữ kiện, ví dụ timeout có thể làm người dùng không biết giao dịch đã hoàn tất hay chưa.
- **Giả định:** điều đang được giả định nhưng chưa xác minh, ví dụ traffic production có phân bố tương tự môi trường staging.
- **Khoảng trống:** điều chưa có đủ dữ liệu để kết luận, ví dụ chưa thử failover giữa hai vùng.

Không trình bày giả định như sự thật. Nếu dữ liệu chưa đủ, nêu rõ mức độ bất định và hành động cần thiết để giảm bất định.

## 5. Viết risk statement rõ ràng

Một rủi ro nên được mô tả bằng câu có cấu trúc để người đọc hiểu điều kiện, sự kiện và hậu quả.

Có thể dùng mẫu:

> Do [nguyên nhân hoặc điều kiện], có khả năng [sự kiện không mong muốn] xảy ra, dẫn đến [hậu quả đối với người dùng, dữ liệu, dịch vụ hoặc mục tiêu].

Ví dụ chưa rõ:

- Có rủi ro về thanh toán.
- Có thể chậm hệ thống.
- Monitoring chưa tốt.
- Còn một số lỗi nhỏ.

Ví dụ rõ hơn:

- Do webhook từ nhà cung cấp có thể đến trễ hoặc lặp và cơ chế đối soát chưa được kiểm tra ở tải cao, có khả năng trạng thái thanh toán và đơn hàng không đồng nhất, khiến khách hàng đã thanh toán nhưng không nhận được xác nhận đơn.
- Do test hiệu năng chỉ chạy đến 1.000 giao dịch đồng thời trong khi dự báo cao điểm là 2.000, có khả năng độ trễ và tỷ lệ timeout vượt mục tiêu khi lưu lượng tăng, làm giảm tỷ lệ hoàn tất giao dịch.
- Do backup đã được tạo nhưng chưa diễn tập restore trên môi trường tương đương, có khả năng thời gian khôi phục thực tế vượt RTO hoặc dữ liệu không đầy đủ khi xảy ra sự cố.

### Thành phần của risk statement

Một mô tả tốt nên làm rõ:

1. **Nguồn/điều kiện:** điều gì tạo ra sự không chắc chắn?
2. **Sự kiện:** điều không mong muốn nào có thể xảy ra?
3. **Hậu quả:** ai hoặc mục tiêu nào chịu ảnh hưởng?
4. **Phạm vi:** phiên bản, môi trường, nhóm người dùng hoặc luồng nào liên quan?
5. **Bằng chứng:** dữ liệu nào hỗ trợ nhận định?

Tránh mô tả quá dài và trộn nhiều rủi ro không liên quan trong một câu. Nếu một vấn đề có nhiều hậu quả hoặc cơ chế khác nhau, tách thành các risk record liên kết với cùng defect hoặc incident.

## 6. Đánh giá likelihood, impact và mức rủi ro

Đánh giá rủi ro cần nhất quán để so sánh và ưu tiên. Tổ chức có thể dùng thang định tính hoặc định lượng, nhưng cần định nghĩa tiêu chí rõ ràng.

### Likelihood — khả năng xảy ra

Likelihood có thể được đánh giá dựa trên:

- Tần suất lỗi quan sát được trong test hoặc production.
- Điều kiện kích hoạt và mức độ dễ tái hiện.
- Mức độ phơi nhiễm của tính năng hoặc endpoint.
- Khối lượng traffic, dữ liệu và concurrency.
- Lịch sử lỗi của thành phần hoặc nhà cung cấp.
- Hiệu quả và độ tin cậy của biện pháp kiểm soát.

Nếu chưa có dữ liệu production, không nên tự gán xác suất chính xác. Có thể dùng mô tả định tính và ghi rõ cơ sở hoặc mức độ tin cậy của đánh giá.

### Impact — mức độ tác động

Impact có thể xét theo nhiều chiều:

- Số lượng và nhóm người dùng bị ảnh hưởng.
- Giá trị giao dịch, doanh thu hoặc chi phí phát sinh.
- Mất, sai lệch hoặc lộ dữ liệu.
- Thời gian gián đoạn và khả năng phục hồi.
- Nghĩa vụ pháp lý, hợp đồng, an toàn hoặc quyền riêng tư.
- Uy tín và niềm tin của khách hàng.
- Khả năng hỗ trợ, điều tra và khôi phục.

Một lỗi ít xảy ra nhưng có hậu quả nghiêm trọng vẫn có thể là rủi ro cao. Không nên chỉ nhân likelihood với impact rồi bỏ qua các yêu cầu bắt buộc hoặc hậu quả không thể chấp nhận.

### Ma trận đánh giá tham khảo

| Likelihood / Impact | Thấp | Trung bình | Cao | Rất cao |
|---|---|---|---|---|
| Hiếm | Thấp | Thấp | Trung bình | Cao |
| Ít khả năng | Thấp | Trung bình | Cao | Cao |
| Có thể | Trung bình | Trung bình | Cao | Rất cao |
| Thường xuyên | Trung bình | Cao | Rất cao | Rất cao |

Ma trận chỉ là công cụ hỗ trợ. Tổ chức cần quy định cách xử lý từng mức, ai có quyền chấp nhận và trường hợp nào không được miễn trừ.

### Inherent risk và residual risk

Ghi nhận rủi ro trước kiểm soát và sau kiểm soát để người đọc thấy biện pháp đã giảm điều gì. Ví dụ:

| Nội dung | Trước kiểm soát | Sau kiểm soát |
|---|---|---|
| Tình huống | Webhook lặp có thể tạo xử lý thanh toán trùng | Có idempotency key và kiểm tra duplicate event |
| Likelihood | Có thể xảy ra khi provider retry | Giảm xuống ít khả năng theo test và log quan sát |
| Impact | Có thể ghi nhận trạng thái hoặc giao dịch sai | Vẫn có thể phát sinh trạng thái lệch trong tình huống hiếm |
| Bằng chứng | Lỗi đã tái hiện trong test | Test retry/duplicate pass; còn thiếu diễn tập mất kết nối kéo dài |
| Rủi ro còn lại | Cao | Trung bình, cần theo dõi và review |

Không hạ mức residual risk chỉ vì đã thêm một biện pháp. Cần bằng chứng cho thấy kiểm soát hoạt động và xem xét các giới hạn của nó.

## 7. Thiết kế phương án giảm thiểu

Mitigation là các hành động làm giảm likelihood, impact hoặc thời gian phát hiện/phục hồi. Một phương án tốt cần cụ thể, khả thi, có owner và có cách xác minh.

### Các chiến lược xử lý rủi ro

- **Avoid — tránh:** thay đổi hoặc loại bỏ hoạt động tạo ra rủi ro, ví dụ tắt tạm một phương thức thanh toán có lỗi.
- **Mitigate/Reduce — giảm thiểu:** thêm kiểm soát để giảm khả năng hoặc tác động, ví dụ idempotency, validation, rate limit, alert và backup.
- **Transfer/Share — chuyển giao/chia sẻ:** phân bổ một phần trách nhiệm qua hợp đồng hoặc bảo hiểm; không làm mất trách nhiệm quản trị của tổ chức.
- **Accept — chấp nhận:** giữ rủi ro trong giới hạn đã được đánh giá và phê duyệt đúng thẩm quyền.

Không phải rủi ro nào cũng nên được chấp nhận. Nếu hậu quả vượt ngưỡng hoặc vi phạm yêu cầu bắt buộc, cần tránh, giảm thiểu hoặc dừng hoạt động.

### Phân biệt biện pháp phòng ngừa, phát hiện và khắc phục

| Loại kiểm soát | Mục tiêu | Ví dụ |
|---|---|---|
| Phòng ngừa | Giảm khả năng sự kiện xảy ra | Validation, quyền tối thiểu, idempotency, giới hạn đầu vào |
| Phát hiện | Nhận biết sớm khi sự kiện xảy ra | Metric, alert, audit log, đối soát, synthetic monitoring |
| Khắc phục/phục hồi | Giảm tác động và khôi phục trạng thái | Rollback, restore, retry có kiểm soát, quy trình xử lý thủ công |
| Hạn chế phạm vi | Giảm số người hoặc hệ thống chịu tác động | Canary, feature flag, giới hạn tenant hoặc khu vực |

Một phương án giảm thiểu vững chắc thường kết hợp nhiều loại. Chỉ có cảnh báo không ngăn lỗi xảy ra; chỉ có rollback không bảo đảm dữ liệu đã thay đổi được khôi phục.

### Viết mitigation action có thể thực hiện

Mỗi hành động nên có:

- Việc cần làm và kết quả mong đợi.
- Người hoặc nhóm chịu trách nhiệm.
- Thời hạn và phụ thuộc.
- Phạm vi áp dụng.
- Cách xác minh hiệu quả.
- Bằng chứng hoàn tất.
- Kế hoạch thay thế nếu hành động không đạt.

Ví dụ mơ hồ: “Tăng monitoring”. Ví dụ cụ thể: “Thêm metric `payment_success_order_pending`, cảnh báo khi số giao dịch vượt ngưỡng trong 5 phút, gửi đến nhóm trực Payment, liên kết runbook đối soát và diễn tập cảnh báo trước khi mở rollout rộng”.

## 8. Đánh giá hiệu quả và giới hạn của mitigation

Không nên coi một hành động đã hoàn tất là bằng chứng rằng rủi ro đã giảm. Cần xác nhận kiểm soát hoạt động trong điều kiện liên quan.

### Câu hỏi kiểm chứng

- Kiểm soát có thực sự được triển khai trên phiên bản và môi trường mục tiêu không?
- Có test hoặc diễn tập chứng minh nó hoạt động không?
- Nó ngăn sự kiện, phát hiện sự kiện hay chỉ giúp phục hồi?
- Có thể bị vô hiệu hóa bởi cấu hình, quyền hoặc phụ thuộc không?
- Có tác động phụ hoặc rủi ro mới được tạo ra không?
- Có người nhận cảnh báo và có thể thực hiện hành động không?
- Kiểm soát có đủ khi tải tăng hoặc phụ thuộc bên ngoài suy giảm không?

### Bằng chứng hiệu quả

Bằng chứng có thể là test pass, kết quả diễn tập, log, metric, báo cáo restore, kết quả kiểm tra quyền, xác nhận từ nhà cung cấp hoặc hồ sơ vận hành. Cần ghi rõ build, môi trường, điều kiện và thời điểm thực hiện.

### Giới hạn còn lại

Ví dụ, cảnh báo được kiểm tra thành công trên staging nhưng production có thể có routing khác. Backup được tạo hằng ngày nhưng chưa kiểm tra restore. Rate limit bảo vệ API nhưng có thể ảnh hưởng người dùng hợp lệ trong đợt cao điểm. Mỗi giới hạn cần được nêu để người quyết định hiểu biện pháp không bảo đảm tuyệt đối.

## 9. Phân công ownership và thẩm quyền quyết định

Một risk record không có người sở hữu thường không được theo dõi đến cùng. Cần phân biệt người chịu trách nhiệm thực hiện mitigation với người sở hữu rủi ro và người có quyền chấp nhận.

### Các vai trò

- **Risk owner:** chịu trách nhiệm theo dõi rủi ro, đánh giá thay đổi và bảo đảm hành động được thực hiện.
- **Action owner:** trực tiếp thực hiện một biện pháp giảm thiểu cụ thể.
- **Risk acceptance authority:** người có quyền quyết định chấp nhận rủi ro theo chính sách và phạm vi được giao.
- **Technical reviewer:** đánh giá tính khả thi, hiệu quả và giới hạn của kiểm soát.
- **Release authority:** tổng hợp bằng chứng và đưa ra quyết định phát hành theo quy trình.
- **Operations/SRE owner:** nhận trách nhiệm theo dõi tín hiệu, ứng phó và thực hiện runbook sau phát hành.

Một người có thể đảm nhiệm nhiều vai trò ở nhóm nhỏ, nhưng không nên mặc định người phát hiện lỗi hoặc người viết bản sửa có quyền chấp nhận rủi ro nghiệp vụ, bảo mật hay tuân thủ.

### Ma trận trách nhiệm tham khảo

| Hoạt động | QA/Test | Engineering | Product/Business | Security/Privacy | Operations/SRE | Release authority |
|---|---|---|---|---|---|---|
| Thu thập bằng chứng test | R/A | C | C | C | C | I |
| Đánh giá tác động kỹ thuật | C | R/A | C | C | C | I |
| Đánh giá tác động nghiệp vụ | C | C | R/A | C | C | I |
| Đánh giá rủi ro bảo mật/dữ liệu | C | C | I | R/A | C | I |
| Thiết kế mitigation vận hành | C | R | C | C | R/A | I |
| Chấp nhận rủi ro | C | C | A hoặc theo thẩm quyền | A khi thuộc phạm vi | A khi thuộc phạm vi | A theo quy chế |
| Quyết định phát hành | C | C | C | C | C | R/A |

RACI trong bảng chỉ là ví dụ. Tổ chức cần xác định một người hoặc vai trò Accountable cho từng quyết định và tuân thủ quy chế phê duyệt thực tế.

## 10. Cấu trúc báo cáo rủi ro còn lại

Một báo cáo tốt nên giúp người đọc nắm nhanh rủi ro chính, hiểu bằng chứng và biết cần quyết định điều gì. Có thể dùng risk register kèm phần tóm tắt release readiness.

### Trường thông tin tối thiểu

| Trường | Nội dung cần ghi |
|---|---|
| Risk ID | Mã duy nhất để truy vết |
| Title | Tên ngắn mô tả rủi ro |
| Risk statement | Nguyên nhân/điều kiện, sự kiện và hậu quả |
| Scope | Phiên bản, môi trường, chức năng, người dùng hoặc vùng ảnh hưởng |
| Evidence | Test result, defect, incident, metric, log hoặc giới hạn đã xác nhận |
| Inherent rating | Đánh giá trước kiểm soát nếu áp dụng |
| Existing controls | Kiểm soát hiện có và trạng thái |
| Residual rating | Mức rủi ro còn lại và căn cứ |
| Mitigation actions | Hành động, owner, deadline và cách xác minh |
| Workaround/contingency | Cách giảm tác động khi sự kiện xảy ra |
| Risk owner | Người chịu trách nhiệm theo dõi |
| Acceptance authority | Người có quyền phê duyệt nếu cần |
| Decision/status | Open, mitigating, accepted, escalated, closed... |
| Review/expiry | Ngày xem xét lại hoặc hết hạn quyết định |
| Trigger | Điều kiện buộc đánh giá lại hoặc dừng rollout |

### Tóm tắt điều hành

Phần tóm tắt nên trả lời:

1. Có bao nhiêu rủi ro còn lại theo mức độ?
2. Rủi ro nào có thể ảnh hưởng trực tiếp đến release?
3. Những kiểm soát quan trọng nào đã được xác minh?
4. Khoảng trống hoặc giới hạn nào vẫn tồn tại?
5. Cần quyết định gì, bởi ai và trước thời điểm nào?

Không nên đưa hàng chục trang chi tiết vào phần mở đầu. Hãy trình bày các rủi ro quan trọng trước, sau đó liên kết đến bằng chứng và risk register đầy đủ.

## 11. Trình bày mức rủi ro và ưu tiên dễ hiểu

Người đọc cần phân biệt mức độ rủi ro với trạng thái xử lý. Một rủi ro có thể được đánh giá cao nhưng đang có mitigation; một rủi ro trung bình có thể chưa có owner hoặc chưa có kế hoạch.

### Dùng nhãn có định nghĩa

Ví dụ:

- **Critical:** có thể gây hậu quả nghiêm trọng hoặc vi phạm điều kiện bắt buộc; thường cần dừng phát hành hoặc escalte theo chính sách.
- **High:** ảnh hưởng đáng kể đến người dùng, dữ liệu hoặc dịch vụ; cần xử lý hoặc phê duyệt rõ trước release.
- **Medium:** tác động có giới hạn hoặc có workaround, nhưng cần owner và kế hoạch.
- **Low:** tác động nhỏ, có kiểm soát và có thể theo dõi theo lịch.

Các nhãn cần gắn với tiêu chí nội bộ. Không dùng màu sắc hoặc từ ngữ để làm nhẹ một rủi ro chưa được phân tích.

### Nêu rõ mức độ tin cậy

Nếu đánh giá dựa trên dữ liệu ít, ghi mức độ tin cậy thấp hoặc trung bình và lý do. Ví dụ, “likelihood: ít khả năng” dựa trên một lần diễn tập không đủ mạnh như dữ liệu production nhiều tháng. Người quyết định cần biết cả mức rủi ro và chất lượng bằng chứng.

### Phân biệt mức rủi ro và quyết định

Một risk có thể được xếp High nhưng tổ chức vẫn quyết định không phát hành. Một risk Medium có thể được chấp nhận có điều kiện. Trình bày hai trường riêng:

- **Risk rating:** đánh giá likelihood/impact hoặc mức residual.
- **Decision:** fix before release, mitigate, defer, accept, restrict rollout hoặc no-go.

Không suy ra rằng trạng thái “accepted” có nghĩa rủi ro thấp.

## 12. Trình bày rủi ro trong release readiness review

Release readiness review là điểm kết nối kết quả test, defect backlog, operational readiness và quyết định phát hành. Báo cáo rủi ro cần được chuẩn bị trước buổi review, không nên đợi đến lúc được hỏi mới tổng hợp.

### Nội dung cần có

- Release ID, artifact/version, môi trường và phạm vi phát hành.
- Những suite đã chạy, chưa chạy, skip hoặc quarantine.
- Defect còn mở theo severity/priority và tuổi lỗi.
- Residual risk theo mức độ và nhóm tác động.
- Mitigation đã hoàn tất, đang thực hiện và chưa có bằng chứng.
- Workaround, monitoring, on-call và rollback plan.
- Ngoại lệ bảo mật, quyền riêng tư, hợp đồng hoặc tuân thủ nếu có.
- Quyết định cần đưa ra, người quyết định và thời hạn.

### Quyết định Go/No-Go

Một quy trình có thể xác định:

- **Go:** tiêu chí bắt buộc đạt, residual risk nằm trong ngưỡng và các phê duyệt cần thiết hoàn tất.
- **Go có điều kiện:** chỉ áp dụng nếu chính sách cho phép, phạm vi và thời hạn rõ, mitigation có thể thực thi và người có thẩm quyền chấp nhận.
- **No-Go:** còn điều kiện chặn, rủi ro vượt ngưỡng, thiếu bằng chứng bắt buộc hoặc chưa có kiểm soát đủ tin cậy.

Không phải mọi rủi ro đều có thể chấp nhận. Nghĩa vụ pháp lý, hợp đồng, an toàn hoặc chính sách bảo mật có thể không cho phép ngoại lệ. Người quản lý dự án không thể tự miễn trừ yêu cầu nằm ngoài thẩm quyền.

### Khi có nhiều rủi ro

Ưu tiên trình bày theo mức độ tác động, thời hạn quyết định và khả năng xử lý. Không xếp theo thứ tự ticket được tạo. Một rủi ro ít khả năng nhưng gây mất dữ liệu có thể cần được trình bày trước các lỗi giao diện nhỏ.

## 13. Rollout giới hạn và điều kiện vận hành

Trong một số trường hợp, tổ chức có thể giảm phạm vi phát hành để kiểm chứng thêm trong điều kiện thực tế. Đây là một biện pháp giảm thiểu, không phải cách thay thế việc đánh giá rủi ro.

### Các hình thức giới hạn

- Canary cho một tỷ lệ nhỏ lưu lượng.
- Chỉ mở cho người dùng nội bộ hoặc nhóm pilot.
- Bật feature flag theo tenant, khu vực hoặc vai trò.
- Giới hạn số giao dịch hoặc giá trị giao dịch.
- Tắt tạm một tích hợp hoặc chức năng có rủi ro.
- Triển khai theo vùng hoặc theo nhóm dịch vụ.

### Điều kiện phải ghi rõ

- Phạm vi người dùng, tenant, khu vực hoặc traffic được phép.
- Thời gian rollout và thời điểm review.
- Metric, log, dashboard và cảnh báo cần theo dõi.
- Ngưỡng tiếp tục, dừng hoặc rollback.
- Người trực, người nhận cảnh báo và người có quyền dừng.
- Runbook và cách phục hồi dữ liệu/trạng thái.
- Cách thông báo người dùng hoặc bộ phận hỗ trợ.
- Điều kiện mở rộng phạm vi và bằng chứng cần đạt.

Ví dụ, “triển khai 5%” chưa đủ cụ thể nếu không nói 5% người dùng nào, trong bao lâu, đo chỉ số gì và ai dừng rollout khi có vấn đề.

### Trigger để dừng hoặc đánh giá lại

Trigger có thể gồm:

- Tỷ lệ lỗi hoặc timeout vượt ngưỡng.
- Metric nghiệp vụ bất thường, như giao dịch thành công nhưng đơn chưa xác nhận.
- Tăng đột biến khiếu nại hoặc yêu cầu hỗ trợ.
- Cảnh báo bảo mật hoặc phát hiện dữ liệu truy cập trái phép.
- Phụ thuộc bên ngoài suy giảm hoặc thay đổi hợp đồng.
- Workaround không thể thực hiện hoặc người trực không sẵn sàng.
- Hết thời hạn chấp nhận hoặc phạm vi rollout thay đổi.

Trigger phải gắn với hành động: dừng, rollback, tắt feature, chuyển cấp, điều tra hoặc trình phê duyệt lại.

## 14. Theo dõi rủi ro sau phát hành

Rủi ro không kết thúc khi release được phê duyệt. Các giả định trước phát hành cần được kiểm chứng bằng dữ liệu thực tế.

### Monitoring theo risk statement

Mỗi rủi ro cần có tín hiệu phù hợp. Ví dụ:

- Rủi ro thanh toán lệch trạng thái: theo dõi số payment success nhưng order pending.
- Rủi ro quá tải: theo dõi latency p95/p99, error rate, queue depth và resource saturation.
- Rủi ro mất dữ liệu: theo dõi backup job, restore test và dữ liệu đối soát.
- Rủi ro xác thực: theo dõi login failure bất thường, token error và access denied theo vai trò.
- Rủi ro phụ thuộc ngoài: theo dõi availability, timeout, rate limit và provider status.

### Runbook và người trực

Monitoring chỉ có giá trị khi cảnh báo đến đúng người và có hành động. Risk record cần liên kết đến runbook, on-call rota, escalation path và thông tin cần thu thập. Runbook phải được thử ở mức phù hợp.

### Review sau phát hành

Đặt thời điểm review dựa trên rủi ro: sau vài giờ rollout, sau 24 giờ, sau một chu kỳ giao dịch hoặc sau khi đạt đủ lượng dữ liệu. Không chọn thời gian tùy tiện nếu chưa đủ mẫu để đánh giá.

Trong review, so sánh actual với giả định: tỷ lệ lỗi, tác động, workaround, alert, thời gian phát hiện, số người dùng ảnh hưởng và chi phí hỗ trợ. Cập nhật residual risk nếu dữ liệu mới cho thấy khả năng hoặc hậu quả khác dự kiến.

### Đóng rủi ro

Chỉ đóng risk record khi điều kiện gây rủi ro đã được loại bỏ hoặc kiểm soát đủ theo tiêu chí, bằng chứng đã được xem xét và risk owner xác nhận. Nếu defect được sửa nhưng chưa chạy regression hoặc chưa triển khai, rủi ro có thể vẫn tồn tại trong release hiện tại.

## 15. Giao tiếp rủi ro với các nhóm khác nhau

Thông tin cốt lõi phải nhất quán, nhưng cách trình bày nên phù hợp với vai trò người nhận.

### Với lãnh đạo và người phê duyệt

Tập trung vào tác động kinh doanh, quyết định cần thiết, mức độ rủi ro, lựa chọn, chi phí và hậu quả nếu không xử lý. Tránh yêu cầu họ diễn giải stack trace hoặc chi tiết framework.

### Với nhóm phát triển

Nêu điều kiện kích hoạt, phiên bản, bước tái hiện, log/trace, thành phần liên quan, giả thuyết nguyên nhân và tiêu chí xác minh bản sửa.

### Với Operations/SRE

Nêu tín hiệu phát hiện, ngưỡng cảnh báo, runbook, workaround, người chuyển cấp, điều kiện rollback và giới hạn vận hành.

### Với Product/Business

Nêu luồng nghiệp vụ và nhóm người dùng bị ảnh hưởng, khả năng sử dụng workaround, tác động đến quy trình, thời điểm và lựa chọn phát hành.

### Với Security/Privacy/Legal

Nêu tài sản/dữ liệu liên quan, mức phơi nhiễm, bằng chứng, phạm vi ảnh hưởng, biện pháp kiểm soát và nghĩa vụ cần tuân thủ. Không tự đưa ra kết luận pháp lý thay cho vai trò chuyên môn.

## 16. Mẫu risk register và mẫu tóm tắt release

### Mẫu risk record

```text
RISK ID:
TITLE:
RELEASE / VERSION:
SCOPE / ENVIRONMENT:

RISK STATEMENT:
SOURCE / CONDITION:
POTENTIAL EVENT:
CONSEQUENCE:

EVIDENCE / REFERENCES:
INHERENT LIKELIHOOD / IMPACT:
EXISTING CONTROLS:
CONTROL EVIDENCE:
RESIDUAL LIKELIHOOD / IMPACT:
CONFIDENCE / UNCERTAINTY:

MITIGATION ACTIONS:
- Action:
  Owner:
  Due date:
  Verification evidence:

WORKAROUND / CONTINGENCY:
RISK OWNER:
ACCEPTANCE AUTHORITY:
DECISION / STATUS:
SCOPE AND EXPIRY OF ACCEPTANCE:
REVIEW DATE:
TRIGGERS / STOP CONDITIONS:
LINKED DEFECTS / INCIDENTS:
```

### Mẫu tóm tắt release readiness

```text
Release ID / Version:
Artifact digest:
Environment(s):
Review date:

Test execution summary:
- Suites passed:
- Suites failed:
- Tests skipped/quarantined:
- Important scope limitations:

Open defects:
- Critical/High:
- Medium/Low:
- Oldest unresolved defect:

Residual risks:
- Risk ID / Rating / Impact:
- Controls verified:
- Remaining gaps:
- Owner / Review date:

Mitigation and contingency:
- Action / Owner / Due date:
- Monitoring / Alert / Runbook:
- Rollout restriction / Rollback trigger:

Decision required:
- Go / Conditional Go / No-Go:
- Decision authority:
- Conditions and expiry:
```

Các mẫu có thể điều chỉnh theo công cụ của tổ chức. Tránh lưu secret hoặc dữ liệu cá nhân trong risk record; dùng liên kết đến kho bằng chứng có kiểm soát.

## 17. Ví dụ xuyên suốt: phát hành luồng thanh toán mới

Giả sử một nền tảng thương mại điện tử thay đổi tích hợp thanh toán. Unit, API và core regression đều đạt. Tuy nhiên, test với provider sandbox cho thấy một số webhook đến trễ; nhóm chưa diễn tập đầy đủ tình huống provider retry trong thời gian dài.

### Mô tả rủi ro

**Risk ID:** RSK-PAY-014

**Risk statement:** Do webhook từ provider có thể đến trễ hoặc được gửi lại sau timeout và chưa có bằng chứng đầy đủ về xử lý retry kéo dài, có khả năng trạng thái thanh toán và trạng thái đơn hàng không đồng nhất, khiến khách hàng đã thanh toán nhưng không nhận được xác nhận đơn hoặc hệ thống phải đối soát thủ công.

**Bằng chứng:** test sandbox đã tái hiện webhook đến trễ; test duplicate event hiện đạt với một số trường hợp; chưa có diễn tập mất kết nối dài và phục hồi hàng đợi trên môi trường gần production.

**Inherent risk:** Cao do liên quan giao dịch và trạng thái đơn.

### Biện pháp giảm thiểu

- Dùng idempotency key và kiểm tra event ID trước khi xử lý.
- Thêm metric theo dõi payment success nhưng order pending.
- Cảnh báo khi số lượng hoặc thời gian trạng thái lệch vượt ngưỡng.
- Tạo job đối soát định kỳ và runbook xử lý các giao dịch chưa khớp.
- Giới hạn rollout ban đầu cho nhóm người dùng nội bộ.
- Chuẩn bị feature flag để tắt phương thức thanh toán mới.

### Đánh giá hiệu quả

Nhóm đã chạy test duplicate webhook và xác nhận không tạo giao dịch xử lý trùng trong phạm vi test. Cảnh báo đã được diễn tập trên staging và gửi đến đúng nhóm trực. Tuy nhiên, job đối soát chưa được kiểm tra với lượng dữ liệu lớn; đây vẫn là giới hạn cần ghi nhận.

**Residual risk:** Trung bình trong phạm vi rollout nội bộ, với điều kiện monitoring và đối soát hoạt động. Mức này không được tự động áp dụng cho rollout toàn bộ khách hàng.

### Quyết định và điều kiện

Nếu chính sách cho phép, release authority có thể xem xét conditional go cho nhóm nội bộ trong 24 giờ. Điều kiện gồm:

- Giới hạn người dùng và giá trị giao dịch.
- Nhóm Payment trực theo dõi dashboard và cảnh báo.
- Đối soát thủ công theo lịch đã xác định.
- Dừng rollout nếu trạng thái lệch vượt ngưỡng hoặc có giao dịch trùng.
- Hoàn tất test phục hồi hàng đợi trước khi mở rộng.
- Service owner review dữ liệu sau 24 giờ và quyết định tiếp tục, sửa hoặc rollback.

Nếu hợp đồng hoặc quy định yêu cầu đối soát tự động trước khi xử lý giao dịch thật, conditional go không được dùng để bỏ qua điều kiện đó. Khi đó phải hoãn phát hành hoặc tìm phương án đáp ứng yêu cầu.

### Theo dõi sau rollout

Trong thời gian giới hạn, nhóm ghi nhận số giao dịch, số trạng thái lệch, thời gian xử lý, số lần cảnh báo, số trường hợp đối soát thủ công và khiếu nại. Sau thời hạn, risk owner cập nhật residual risk dựa trên dữ liệu. Nếu không có sự cố nhưng số giao dịch còn ít, không nên kết luận rủi ro đã biến mất; cần đủ bằng chứng hoặc tiếp tục giới hạn.

## 18. Những sai lầm thường gặp

**Chỉ liệt kê defect mà không mô tả rủi ro.** Người đọc không biết lỗi ảnh hưởng đến ai và hậu quả ra sao. Chuyển defect thành risk statement có điều kiện, sự kiện và tác động.

**Ghi “rủi ro thấp” không có căn cứ.** Mức đánh giá cần liên kết với dữ liệu, kiểm soát và giới hạn. Nếu bằng chứng yếu, nêu độ tin cậy thấp thay vì tạo cảm giác chắc chắn.

**Nhầm mitigation với việc đã sửa lỗi.** Monitoring hoặc workaround có thể giảm tác động nhưng defect vẫn còn. Ghi riêng trạng thái defect, kiểm soát và residual risk.

**Chỉ nêu hành động mà không có owner.** “Sẽ tăng monitoring” không phải kế hoạch thực thi. Gán người phụ trách, deadline, ngưỡng và bằng chứng xác minh.

**Không nói rõ phần chưa kiểm tra.** Một test suite pass không có nghĩa mọi browser, tải hoặc phụ thuộc đã được kiểm tra. Nêu phạm vi, giới hạn và hệ quả của khoảng trống.

**Dùng rollout giới hạn như bằng chứng an toàn tuyệt đối.** Canary giảm phạm vi ảnh hưởng nhưng không loại bỏ defect. Cần trigger dừng, rollback, người trực và tiêu chí mở rộng.

**Chấp nhận rủi ro bằng lời nói.** Quyết định cần có hồ sơ, người có thẩm quyền, phạm vi, thời hạn và điều kiện review.

**Không liên kết rủi ro với release cụ thể.** Rủi ro và test evidence có thể thay đổi theo build. Gắn artifact/version, cấu hình và môi trường vào báo cáo.

**Không cập nhật sau khi điều kiện thay đổi.** Khi rollout mở rộng, provider đổi hành vi hoặc workaround thất bại, mức rủi ro cũ không còn phù hợp. Thiết lập trigger và review định kỳ.

**Đưa quá nhiều chi tiết kỹ thuật vào phần điều hành.** Người phê duyệt cần tác động và quyết định; nhóm kỹ thuật cần log và bước tái hiện. Dùng phần tóm tắt và phụ lục bằng chứng theo đối tượng.

## 19. Checklist trình bày rủi ro còn lại

### Xác định và đánh giá

- [ ] Rủi ro có ID và mô tả rõ nguyên nhân/điều kiện, sự kiện, hậu quả.
- [ ] Phạm vi release, version, môi trường và nhóm người dùng được xác định.
- [ ] Bằng chứng được liên kết và có thể truy vết.
- [ ] Dữ kiện, suy luận, giả định và khoảng trống được phân biệt.
- [ ] Likelihood, impact, inherent risk và residual risk có căn cứ.
- [ ] Mức độ tin cậy và giới hạn bằng chứng được nêu.

### Giảm thiểu và ownership

- [ ] Kiểm soát phòng ngừa, phát hiện và phục hồi được mô tả.
- [ ] Hiệu quả kiểm soát đã được kiểm tra ở môi trường phù hợp.
- [ ] Giới hạn và rủi ro mới do mitigation được xem xét.
- [ ] Mỗi hành động có owner, deadline và cách xác minh.
- [ ] Có workaround/contingency và runbook khi cần.
- [ ] Risk owner và acceptance authority được xác định.

### Quyết định phát hành

- [ ] Defect còn mở, test skip/flaky/quarantine và giới hạn kiểm thử được tổng hợp.
- [ ] Rủi ro bắt buộc hoặc không được miễn trừ được nhận diện.
- [ ] Go/No-Go/Conditional Go có căn cứ và đúng thẩm quyền.
- [ ] Phạm vi, thời hạn, điều kiện và trigger của conditional go rõ ràng.
- [ ] Monitoring, on-call, escalation và rollback được chuẩn bị.

### Theo dõi sau phát hành

- [ ] Risk record có ngày review/expiry.
- [ ] Metric, alert và runbook được liên kết.
- [ ] Dữ liệu thực tế được so sánh với giả định.
- [ ] Trigger đánh giá lại có hành động tương ứng.
- [ ] Chỉ đóng rủi ro khi tiêu chí và bằng chứng hoàn tất.

## 20. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Test tải đạt ở 1.000 người dùng đồng thời nhưng dự báo cao điểm là 3.000. Rủi ro còn lại là hiệu năng ở mức tải chưa kiểm tra. Báo cáo cần nêu giới hạn test, dự báo, tác động có thể có và phương án như giới hạn rollout, tăng năng lực, chạy test bổ sung hoặc theo dõi ngưỡng dừng.

**Tình huống 2:** Một defect đã có workaround nhưng chưa được sửa. Không nên ghi risk là “đã xử lý”. Cần mô tả defect, cách workaround giảm tác động, giới hạn, người thực hiện và residual risk còn lại.

**Tình huống 3:** Backup job chạy thành công nhưng chưa restore thử. Rủi ro là khả năng khôi phục chưa được chứng minh. Mitigation cần có restore rehearsal, đối soát dữ liệu và đo thời gian so với RTO/RPO.

**Tình huống 4:** Product Owner muốn chấp nhận một lỗ hổng bảo mật nghiêm trọng để kịp release. Cần kiểm tra chính sách và thẩm quyền. Nếu ngoại lệ không được phép hoặc cần Security approval, quyết định của Product Owner không đủ; có thể phải No-Go.

**Tình huống 5:** Canary 5% không có cảnh báo hoặc người trực. Đây chưa phải phương án giảm thiểu đầy đủ. Cần xác định metric, ngưỡng, người nhận, runbook, quyền dừng và điều kiện rollback trước khi rollout.

**Tình huống 6:** Một rủi ro được chấp nhận trong 24 giờ nhưng rollout kéo dài một tuần. Phạm vi và thời hạn quyết định đã thay đổi; phải đánh giá lại và xin phê duyệt mới trước khi tiếp tục.

Khi chuẩn bị release review, hãy tự hỏi: **điều gì vẫn có thể xảy ra, bằng chứng nào cho thấy khả năng và tác động, biện pháp nào đang giảm thiểu, giới hạn nào còn lại, ai chịu trách nhiệm và điều kiện nào sẽ khiến tổ chức dừng hoặc xem xét lại?** Một báo cáo tốt giúp trả lời các câu hỏi đó mà không che giấu bất định.

## Kết luận

Trình bày rủi ro còn lại cùng phương án giảm thiểu là một phần thiết yếu của quyết định phát hành và vận hành. Nhóm cần thu thập bằng chứng có thể truy vết, viết risk statement rõ, đánh giá likelihood/impact và residual risk, mô tả kiểm soát cùng giới hạn, giao owner và xác định thẩm quyền chấp nhận. Quyết định Go/No-Go hoặc rollout có điều kiện phải gắn với phạm vi, thời hạn, monitoring, runbook, rollback trigger và ngày review. Khi rủi ro được trình bày minh bạch và theo dõi sau phát hành, tổ chức có thể đưa ra quyết định thực tế mà vẫn bảo vệ người dùng, dữ liệu và mục tiêu dịch vụ.
