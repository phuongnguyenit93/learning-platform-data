# Phân biệt giảm thiểu bằng kiểm thử với biện pháp thiết kế, vận hành và phòng ngừa

Kiểm thử là một phần quan trọng của quản lý rủi ro chất lượng, nhưng bản thân việc chạy thêm test không làm cho một hệ thống tự động an toàn, bảo mật hay sẵn sàng hơn. Kiểm thử tạo bằng chứng về hành vi của sản phẩm, giúp phát hiện điểm yếu và xác minh biện pháp kiểm soát. Rủi ro chỉ thực sự giảm khi kết quả đó dẫn đến hành động phù hợp, chẳng hạn sửa lỗi, thay đổi thiết kế, bổ sung kiểm soát vận hành hoặc điều chỉnh quyết định phát hành.

Khi một rủi ro được nhận diện, nhóm cần tìm nguyên nhân và hậu quả trước khi chọn cách xử lý. Có rủi ro được giảm tốt nhất bằng cách loại bỏ nguyên nhân trong thiết kế; có rủi ro cần phát hiện sớm bằng kiểm thử; có rủi ro phải được giới hạn bằng cơ chế vận hành và phục hồi. Nhiều tình huống cần phối hợp cả ba. Bài học này giải thích cách phân biệt các biện pháp đó, cách chọn tổ hợp kiểm soát và cách dùng bằng chứng kiểm thử để đánh giá rủi ro còn lại.

## 1. Hiểu đúng vai trò của kiểm thử trong giảm thiểu rủi ro

Rủi ro chất lượng thường được xem xét qua hai yếu tố: khả năng xảy ra một sự kiện không mong muốn và mức độ ảnh hưởng nếu sự kiện xảy ra. Một cách ước lượng đơn giản là:

\[
R \approx P \times I
\]

Trong đó \(P\) biểu thị khả năng xảy ra và \(I\) biểu thị mức độ ảnh hưởng. Đây là cách hỗ trợ xếp hạng và trao đổi, không phải phép đo chính xác trong mọi tình huống. Một rủi ro có tác động rất nghiêm trọng vẫn cần được ưu tiên ngay cả khi khả năng xảy ra thấp.

Kiểm thử tác động đến rủi ro thông qua một chuỗi hoạt động:

1. Xác định một tình huống thất bại có thể xảy ra.
2. Thiết kế phép thử để tạo hoặc quan sát tình huống đó.
3. Thu thập bằng chứng về hành vi thực tế.
4. Phân tích nguyên nhân nếu phát hiện sai lệch.
5. Sửa lỗi hoặc bổ sung biện pháp kiểm soát.
6. Kiểm thử lại để xác minh thay đổi.
7. Đánh giá phần rủi ro còn lại và quyết định có chấp nhận hay không.

Chỉ chạy bước 2 và 3 mà không xử lý phát hiện thì rủi ro vẫn còn. Một báo cáo có 100% test pass cũng không chứng minh rằng hệ thống không có lỗi; nó chỉ cho biết các phép thử đã chạy đạt kết quả mong đợi trong phạm vi, dữ liệu và môi trường cụ thể.

Kiểm thử thường đóng vai trò **phát hiện**: tìm lỗi hoặc xác minh một biện pháp kiểm soát có hoạt động không. Khi được tích hợp vào quy trình phát triển và có điều kiện chặn merge hoặc phát hành, kiểm thử còn giúp ngăn một lỗi đã biết đi tiếp đến môi trường người dùng. Tuy vậy, khả năng ngăn chặn đó phụ thuộc vào chất lượng phép thử, phạm vi bao phủ, độ tin cậy của pipeline và việc nhóm thực sự tuân thủ cổng kiểm soát.

Cần phân biệt ba kết quả:

- **Giảm bất định:** có thêm bằng chứng để hiểu khả năng và hậu quả của một rủi ro.
- **Giảm khả năng lỗi đi vào production:** phát hiện lỗi trước phát hành và yêu cầu sửa trước khi triển khai.
- **Giảm tác động khi lỗi xảy ra:** nhờ thiết kế, giới hạn quyền, giám sát, cô lập, sao lưu hoặc phục hồi.

Một hoạt động có thể đóng góp vào nhiều kết quả, nhưng không nên đánh đồng chúng. Ví dụ, kiểm thử phục hồi chứng minh bản sao lưu có thể được khôi phục trong điều kiện đã thử; chính bản sao lưu và quy trình phục hồi mới là biện pháp giúp giảm thiệt hại khi dữ liệu bị mất.

## 2. Phân biệt các nhóm biện pháp kiểm soát

Biện pháp xử lý rủi ro có thể được phân loại theo thời điểm và chức năng của nó trong vòng đời hệ thống.

| Nhóm biện pháp | Mục tiêu | Ví dụ | Vai trò điển hình |
|---|---|---|---|
| Phòng ngừa | Loại bỏ nguyên nhân hoặc giảm khả năng tạo ra lỗi | Xác thực đầu vào, nguyên tắc least privilege, rà soát thiết kế, đào tạo thao tác | Ngăn lỗi hoặc hành vi không mong muốn hình thành |
| Thiết kế để chịu lỗi | Giới hạn phạm vi ảnh hưởng khi một thành phần thất bại | Cô lập tenant, timeout, circuit breaker, idempotency, giới hạn tài nguyên | Ngăn một lỗi lan rộng hoặc tạo hậu quả dây chuyền |
| Phát hiện bằng kiểm thử | Tìm lỗi trước hoặc sau khi thay đổi được đưa vào sử dụng | Unit test, integration test, security test, kiểm thử tải | Tạo bằng chứng và phát hiện sai lệch |
| Phát hiện khi vận hành | Nhận biết vấn đề trong môi trường thực tế | Monitoring, alert, audit log, health check, cảnh báo bất thường | Rút ngắn thời gian phát hiện |
| Ứng phó và phục hồi | Khôi phục dịch vụ hoặc dữ liệu sau sự cố | Rollback, restore, failover, runbook, incident response | Giảm thời gian và mức thiệt hại |
| Chuyển giao hoặc chia sẻ rủi ro | Phân bổ một phần hậu quả hoặc trách nhiệm theo thỏa thuận | Bảo hiểm, hợp đồng với nhà cung cấp, SLA và điều khoản bồi hoàn | Phân bổ tổn thất; không tự loại bỏ nguyên nhân kỹ thuật |
| Chấp nhận rủi ro | Ghi nhận rủi ro còn lại trong giới hạn được phê duyệt | Chấp nhận lỗi nhỏ có phương án thay thế và thời hạn xử lý | Cho phép tiếp tục với hiểu biết và trách nhiệm rõ ràng |

Các nhóm trên có thể chồng lấp. Ví dụ, kiểm tra quyền ở API là biện pháp phòng ngừa truy cập trái phép; kiểm thử phân quyền là hoạt động phát hiện để xác minh biện pháp đó; audit log giúp phát hiện và điều tra sự kiện khi vận hành. Điều quan trọng là ghi rõ mục tiêu của từng biện pháp và cách xác nhận nó hoạt động.

## 3. Chọn biện pháp theo nguyên nhân, không theo thói quen

Một lỗi có thể có nhiều nguyên nhân. Nếu nhóm chỉ thêm test case mà không xử lý nguyên nhân, lỗi tương tự có thể xuất hiện ở đường đi khác hoặc trong cấu hình khác.

Với từng rủi ro, hãy trả lời:

- Sự kiện không mong muốn là gì?
- Điều kiện nào có thể kích hoạt nó?
- Nguyên nhân nằm ở yêu cầu, thiết kế, mã nguồn, dữ liệu, cấu hình, con người hay phụ thuộc bên ngoài?
- Có thể loại bỏ nguyên nhân ngay từ đầu không?
- Nếu không thể loại bỏ, có thể giới hạn quyền, phạm vi hoặc mức độ ảnh hưởng không?
- Cần phép thử nào để xác minh biện pháp kiểm soát?
- Khi vấn đề vẫn xảy ra, hệ thống phát hiện, ứng phó và phục hồi như thế nào?

Một ma trận nguyên nhân giúp định hướng lựa chọn:

| Nguyên nhân hoặc điều kiện | Biện pháp thiết kế / phòng ngừa | Kiểm thử xác minh | Biện pháp vận hành |
|---|---|---|---|
| Đầu vào không hợp lệ làm hỏng dữ liệu | Xác thực ở ranh giới, ràng buộc dữ liệu, kiểu dữ liệu rõ ràng | Giá trị biên, dữ liệu sai định dạng, dữ liệu thiếu và fuzz test phù hợp | Theo dõi lỗi xác thực, cảnh báo mẫu dữ liệu bất thường |
| Người dùng vượt quyền truy cập | Phân quyền phía máy chủ, mặc định từ chối, cô lập tenant | Thử truy cập ngang/dọc, API trực tiếp và quyền đã thu hồi | Rà soát quyền định kỳ, cảnh báo truy cập bất thường |
| Yêu cầu lặp tạo giao dịch trùng | Idempotency key, ràng buộc duy nhất, thiết kế trạng thái giao dịch | Retry, timeout, gửi đồng thời và callback lặp | Đối soát giao dịch, cảnh báo giao dịch bất thường |
| Dịch vụ phụ ngừng phản hồi | Timeout, bulkhead, circuit breaker, hàng đợi bền vững | Fault injection, mất kết nối, phản hồi chậm và phục hồi | Monitoring, runbook, chuyển tuyến hoặc tắt tính năng |
| Xóa nhầm dữ liệu | Phê duyệt thao tác nguy hiểm, soft delete hoặc giới hạn phạm vi | Kiểm thử quyền, xác nhận, xóa hàng loạt và phục hồi | Backup, restore drill, audit log và quy trình sự cố |
| Triển khai cấu hình sai | Cấu hình có kiểm soát phiên bản, kiểm tra trước triển khai | Kiểm thử cấu hình, smoke test và kiểm tra chính sách | Canary, giám sát sau triển khai, rollback |

Ma trận này là điểm bắt đầu. Mỗi sản phẩm cần điều chỉnh theo kiến trúc, mức rủi ro, nghĩa vụ hợp đồng và năng lực vận hành thực tế.

## 4. Dùng kiểm thử để tìm và xác minh điểm yếu

Kiểm thử hữu ích khi được thiết kế quanh tình huống rủi ro cụ thể. Thay vì hỏi “đã có bao nhiêu test?”, hãy hỏi “rủi ro nào được kiểm tra, bằng chứng nào được tạo và kết quả đó dẫn đến quyết định gì?”.

### 4.1. Kiểm thử xác minh yêu cầu và quy tắc

Rà soát yêu cầu, thiết kế và tiêu chí chấp nhận có thể phát hiện mâu thuẫn trước khi mã nguồn được viết. Unit test và component test giúp kiểm tra quy tắc nghiệp vụ, giá trị biên, trạng thái và các điều kiện lỗi.

Ví dụ, nếu hệ thống tính phí theo bậc, kiểm thử cần bao phủ giá trị ngay dưới, đúng tại và ngay trên ranh giới mỗi bậc. Nhưng việc có test cho ranh giới không thay thế yêu cầu rõ ràng về cách tính, làm tròn và xử lý đơn vị tiền tệ.

### 4.2. Kiểm thử tích hợp và hợp đồng

Nhiều rủi ro xuất hiện ở ranh giới giữa dịch vụ: sai schema, thay đổi giao thức, timeout, retry không an toàn hoặc giả định khác nhau về trạng thái. Kiểm thử tích hợp và hợp đồng giúp xác minh cách các thành phần trao đổi dữ liệu.

Hãy kiểm tra cả trường hợp phụ thuộc phản hồi chậm, trả dữ liệu không hợp lệ, từ chối yêu cầu hoặc gửi thông điệp nhiều lần. Nếu chỉ kiểm thử đường đi thành công, nhóm có thể bỏ sót chính tình huống gây ra sự cố.

### 4.3. Kiểm thử bảo mật và quyền riêng tư

Kiểm thử bảo mật có thể xác minh phân quyền, xác thực, xử lý phiên, mã hóa, quản lý bí mật và các ranh giới tin cậy. Các phép thử cần bao gồm người dùng không có quyền, tài khoản bị khóa, token hết hạn, truy cập chéo tenant và thao tác đặc quyền.

Tuy nhiên, kiểm thử xâm nhập hoặc quét lỗ hổng chỉ phản ánh phạm vi và thời điểm đã kiểm tra. Kiến trúc phân quyền, quản lý khóa, cập nhật bản vá và quy trình ứng phó vẫn là các biện pháp cần thiết.

### 4.4. Kiểm thử tải, độ tin cậy và phục hồi

Kiểm thử tải cho biết hệ thống phản ứng thế nào dưới điều kiện tải đã mô phỏng. Kiểm thử chịu lỗi giúp quan sát hành vi khi dịch vụ phụ mất kết nối hoặc phản hồi chậm. Kiểm thử khôi phục xác minh dữ liệu và dịch vụ có thể được phục hồi từ bản sao lưu hoặc cơ chế dự phòng.

Các phép thử này cần gắn với mục tiêu đo được: tải đồng thời, độ trễ, thông lượng, tỷ lệ lỗi, thời gian phục hồi và mức mất dữ liệu cho phép. Kết quả trong môi trường thử nghiệm chỉ có ý nghĩa khi điều kiện đo và khác biệt với production được ghi rõ.

## 5. Biện pháp thiết kế và phòng ngừa xử lý rủi ro từ gốc

Thiết kế có thể làm cho một loại lỗi khó xảy ra hơn, ít nghiêm trọng hơn hoặc không thể lan sang phần khác. Đây thường là nơi nhóm nên xem xét trước khi bổ sung thêm nhiều bước kiểm tra thủ công.

### 5.1. Loại bỏ hoặc giảm bề mặt rủi ro

Một số cách tiếp cận:

- Không thu thập trường dữ liệu không cần thiết.
- Loại bỏ chức năng hoặc luồng không còn mục đích.
- Giảm số lượng thành phần và phụ thuộc bên ngoài.
- Giới hạn giao diện công khai và quyền truy cập.
- Dùng cấu hình mặc định an toàn.
- Giảm số thao tác thủ công có thể gây lỗi.

Ví dụ, nếu sản phẩm không cần lưu số thẻ thanh toán, dùng nhà cung cấp xử lý thanh toán và chỉ lưu mã tham chiếu có thể giảm phạm vi dữ liệu nhạy cảm mà hệ thống phải bảo vệ. Kiểm thử vẫn cần xác minh tích hợp, nhưng giảm dữ liệu được lưu đã loại bỏ một phần nguyên nhân và hậu quả tiềm tàng.

### 5.2. Áp dụng nguyên tắc an toàn trong thiết kế

Một số cơ chế thường dùng:

- **Least privilege:** mỗi người dùng hoặc dịch vụ chỉ có quyền tối thiểu cần thiết.
- **Deny by default:** từ chối nếu chưa có quy tắc cho phép rõ ràng.
- **Input validation:** kiểm tra dữ liệu tại ranh giới tin cậy.
- **Idempotency:** thiết kế thao tác có thể được gửi lại mà không tạo hiệu ứng lặp ngoài ý muốn.
- **Isolation:** cô lập dữ liệu và tài nguyên giữa tenant hoặc thành phần.
- **Timeout và giới hạn tài nguyên:** tránh yêu cầu treo hoặc tiêu thụ tài nguyên không giới hạn.
- **Fail safe:** khi không thể xác minh quyền hoặc trạng thái, chọn hành vi giảm nguy cơ gây hại.
- **Defense in depth:** dùng nhiều lớp kiểm soát độc lập để một lớp thất bại không làm mất toàn bộ bảo vệ.

Không nên thêm cơ chế theo danh sách một cách máy móc. Ví dụ, retry chỉ an toàn khi thao tác có tính idempotent hoặc có cách kiểm soát trùng lặp. Retry một yêu cầu thu tiền không có cơ chế chống trùng có thể làm rủi ro tăng lên.

### 5.3. Thiết kế để giới hạn tác động

Ngay cả khi lỗi không thể loại bỏ hoàn toàn, hệ thống có thể giới hạn phạm vi:

- Tách quyền và dữ liệu theo tenant.
- Dùng giới hạn tốc độ và hạn mức tài nguyên.
- Cô lập hàng đợi và worker theo loại tác vụ.
- Dùng transaction hoặc cơ chế bù trừ cho quy trình nhiều bước.
- Áp dụng circuit breaker để tránh lỗi dây chuyền.
- Triển khai từng phần để giới hạn số người dùng chịu ảnh hưởng.
- Tách vùng lỗi và tránh một phụ thuộc đơn lẻ làm sập toàn hệ thống.

Kiểm thử nên xác minh ranh giới này. Ví dụ, tạo tải bất thường trên một tenant để xem tenant khác có bị suy giảm dịch vụ hay không.

## 6. Biện pháp vận hành giúp phát hiện, ứng phó và phục hồi

Một hệ thống có thể vượt qua kiểm thử trước phát hành nhưng vẫn gặp lỗi do tải thật, cấu hình, nhà cung cấp hoặc hành vi người dùng. Kiểm soát vận hành giúp nhóm nhận biết và xử lý tình huống đó.

### 6.1. Quan sát hệ thống

Thiết lập log, metrics, traces và cảnh báo cho các luồng quan trọng. Chọn chỉ số phản ánh tác động với người dùng, chẳng hạn tỷ lệ giao dịch thất bại, độ trễ của API, số yêu cầu bị từ chối hoặc độ trễ hàng đợi.

Cảnh báo cần có ngưỡng, người nhận và hành động tiếp theo. Một dashboard không có người theo dõi hoặc không dẫn đến quy trình xử lý chưa phải biện pháp vận hành hữu hiệu.

### 6.2. Quy trình ứng phó sự cố

Runbook nên xác định cách xác nhận sự cố, phân loại mức độ, cô lập ảnh hưởng, thông báo các bên, thu thập bằng chứng, khôi phục và đánh giá sau sự cố. Người trực cần biết quyền hạn và điều kiện gọi hỗ trợ.

Tổ chức diễn tập định kỳ để kiểm tra quy trình, liên lạc và quyền truy cập. Việc có một tài liệu runbook không chứng minh rằng nhóm có thể thực hiện nó dưới áp lực.

### 6.3. Sao lưu và phục hồi

Sao lưu chỉ có giá trị khi bản sao có thể khôi phục và phù hợp với yêu cầu về thời gian, dữ liệu và bảo mật. Xác định:

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa có thể chấp nhận được, thường biểu thị bằng khoảng thời gian dữ liệu.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ sau gián đoạn.

Thực hiện restore drill, đo thời gian thực tế, kiểm tra tính đầy đủ và ghi lại lỗi. Kiểm tra cả quyền truy cập bản sao lưu, mã hóa, vị trí lưu và khả năng khôi phục khóa. Bản sao lưu chưa được thử phục hồi là một giả định, chưa phải bằng chứng chắc chắn về khả năng phục hồi.

### 6.4. Triển khai an toàn và quay lui

Canary, rolling deployment, feature flag và rollback giúp giới hạn ảnh hưởng của thay đổi. Tuy nhiên, rollback không phải lúc nào cũng an toàn, nhất là khi schema dữ liệu đã thay đổi hoặc giao dịch đã được xử lý.

Cần kiểm thử quy trình triển khai và quay lui, gồm tương thích ngược giữa các phiên bản, migration, dữ liệu phát sinh và cách tắt tính năng. Ghi rõ điều kiện kích hoạt rollback, người có quyền quyết định và cách xác minh hệ thống sau khi quay lui.

## 7. Ghép kiểm thử với các lớp kiểm soát

Một biện pháp thiết kế hoặc vận hành cần được kiểm thử để chứng minh nó đáp ứng mục tiêu. Đồng thời, kiểm thử có thể phát hiện lỗ hổng khiến nhóm phải bổ sung kiểm soát.

| Rủi ro | Kiểm soát thiết kế / phòng ngừa | Kiểm thử xác minh | Kiểm soát vận hành / phục hồi |
|---|---|---|---|
| Truy cập trái phép dữ liệu tenant khác | Phân quyền phía máy chủ, tenant isolation, deny by default | Kiểm thử truy cập ngang và dọc qua UI/API | Audit log, cảnh báo truy cập bất thường, rà soát quyền |
| Giao dịch bị ghi nhận hai lần | Idempotency key, ràng buộc duy nhất và mô hình trạng thái giao dịch | Retry, gửi đồng thời, timeout và callback lặp | Đối soát, cảnh báo giao dịch trùng, quy trình hoàn tiền |
| Dịch vụ phụ ngừng hoạt động | Timeout, circuit breaker, hàng đợi và giới hạn tài nguyên | Fault injection, kiểm thử timeout và phục hồi | Monitoring, runbook, chuyển tuyến hoặc chế độ suy giảm |
| Mất hoặc hỏng dữ liệu | Ràng buộc dữ liệu, transaction, kiểm soát thao tác nguy hiểm | Kiểm thử lỗi ghi, tính toàn vẹn và khôi phục | Backup, restore drill, đối soát và quy trình ứng phó |
| Lỗi cấu hình gây lộ bí mật | Secret manager, cấu hình mặc định an toàn, tách môi trường | Quét cấu hình, kiểm thử quyền và kiểm tra artifact | Theo dõi thay đổi cấu hình, xoay vòng bí mật và ứng phó |
| Nâng cấp làm hỏng tương thích | Hợp đồng API, tương thích ngược và rollout từng phần | Contract test, regression và kiểm thử môi trường đại diện | Canary, giám sát lỗi theo phiên bản, rollback |

Không phải mọi rủi ro đều cần đủ mọi cột. Với rủi ro có tác động cao, nên tìm cách kiểm soát theo nhiều lớp và tránh phụ thuộc vào một phép thử hoặc một người duy nhất.

## 8. Ví dụ: giảm rủi ro giao dịch thanh toán trùng lặp

Giả sử người dùng bấm nút thanh toán nhưng kết nối mạng bị gián đoạn trước khi giao diện nhận được phản hồi. Người dùng bấm lại; nhà cung cấp thanh toán có thể đã nhận yêu cầu đầu tiên nhưng phản hồi chưa về. Nếu hệ thống tạo một giao dịch mới, khách hàng có thể bị thu tiền hai lần.

### 8.1. Mô tả rủi ro

- **Sự kiện:** một đơn hàng tạo ra nhiều giao dịch thu tiền.
- **Nguyên nhân:** timeout không cho biết yêu cầu đầu tiên đã được xử lý hay chưa; lần retry được xem như giao dịch mới.
- **Hậu quả:** khách hàng bị thu tiền trùng, cần hoàn tiền, tăng chi phí hỗ trợ và làm giảm niềm tin.
- **Yếu tố kích hoạt:** mạng chậm, callback đến trễ, người dùng gửi lại hoặc dịch vụ xử lý thông điệp nhiều lần.

### 8.2. Biện pháp thiết kế

Thiết kế một định danh idempotency ổn định cho mỗi ý định thanh toán. Khi nhận yêu cầu lặp với cùng khóa, dịch vụ trả lại kết quả đã biết hoặc trạng thái đang xử lý thay vì tạo một khoản thu mới. Ràng buộc dữ liệu và mô hình trạng thái phải ngăn hai worker cùng tạo giao dịch cho một ý định thanh toán.

Thiết kế cũng cần xác định thời hạn lưu khóa, phạm vi duy nhất, cách xử lý khóa hết hạn và cách đối chiếu với nhà cung cấp. Chỉ thêm một header idempotency mà không có lưu trữ và xử lý đồng thời đúng cách là chưa đủ.

### 8.3. Kiểm thử xác minh

- Gửi cùng yêu cầu nhiều lần và xác nhận chỉ có một giao dịch thu tiền.
- Gửi hai yêu cầu đồng thời với cùng khóa và kiểm tra tính nguyên tử.
- Mô phỏng timeout sau khi nhà cung cấp đã xử lý nhưng trước khi hệ thống nhận phản hồi.
- Gửi callback trùng hoặc callback đến sai thứ tự.
- Khởi động lại worker giữa quá trình xử lý và xác minh trạng thái được phục hồi.
- Dùng khóa khác cho một ý định thanh toán mới và xác nhận giao dịch mới được xử lý đúng.

Kiểm thử phải đối chiếu cả bản ghi nội bộ và mã giao dịch từ nhà cung cấp thử nghiệm. Chỉ kiểm tra giao diện hiển thị một thông báo thành công không đủ để chứng minh không có giao dịch trùng.

### 8.4. Biện pháp vận hành

Theo dõi tỷ lệ yêu cầu retry, giao dịch có trạng thái không xác định và chênh lệch giữa hệ thống nội bộ với nhà cung cấp. Thiết lập cảnh báo cho các giao dịch bất thường, quy trình đối soát và cách xử lý hoàn tiền. Có runbook cho tình huống nhà cung cấp phản hồi chậm hoặc callback bị gián đoạn.

### 8.5. Đánh giá rủi ro còn lại

Sau khi áp dụng các biện pháp, nhóm cần xem xét các tình huống chưa được loại bỏ: nhà cung cấp vi phạm hợp đồng idempotency, khóa bị dùng sai phạm vi, dữ liệu khóa bị mất hoặc quy trình đối soát chậm. Ghi rõ bằng chứng, giới hạn, người chấp nhận rủi ro và biện pháp theo dõi.

Ví dụ này cho thấy kiểm thử xác minh tính đúng của thiết kế, còn cơ chế idempotency và đối soát mới trực tiếp xử lý nguyên nhân và hậu quả của giao dịch trùng.

## 9. Đánh giá mức độ mạnh và độc lập của kiểm soát

Nhiều kiểm soát cùng tồn tại nhưng có thể phụ thuộc vào một giả định chung. Ví dụ, unit test và integration test đều có thể dùng cùng một mock sai lệch; hai kết quả pass khi đó không tạo ra hai bằng chứng độc lập.

Khi đánh giá tổ hợp kiểm soát, hãy xem:

- **Hiệu lực:** kiểm soát có xử lý đúng nguyên nhân hoặc hậu quả đã xác định không?
- **Phạm vi:** kiểm soát bao phủ tất cả thành phần, tenant, môi trường và đường đi liên quan không?
- **Độ tin cậy:** kiểm soát có thể bị bỏ qua, cấu hình sai hoặc thất bại âm thầm không?
- **Tính độc lập:** các lớp có dựa vào cùng một dữ liệu, quyền hoặc dịch vụ có thể cùng hỏng không?
- **Khả năng quan sát:** nhóm có biết khi kiểm soát thất bại không?
- **Khả năng phục hồi:** có thể khôi phục sau khi các biện pháp phòng ngừa và phát hiện không ngăn được sự cố không?
- **Chi phí duy trì:** kiểm soát có thể được vận hành ổn định trong thời gian dài không?

Một kiểm soát mạnh trên giấy nhưng không có chủ sở hữu, không được rà soát và không có bằng chứng thực thi có thể trở thành kiểm soát hình thức.

## 10. Dùng bằng chứng để đánh giá rủi ro còn lại

Sau khi thực hiện các biện pháp, cập nhật danh mục rủi ro với bằng chứng cụ thể. Không nên chỉ đổi trạng thái từ “cao” sang “thấp” vì đã bổ sung một số test case.

Hồ sơ đánh giá nên bao gồm:

| Nội dung | Câu hỏi |
|---|---|
| Rủi ro ban đầu | Sự kiện, nguyên nhân và hậu quả nào được xét? |
| Biện pháp thiết kế | Nguyên nhân hoặc phạm vi ảnh hưởng nào đã được xử lý? |
| Biện pháp vận hành | Có phát hiện, ứng phó và phục hồi được không? |
| Kiểm thử đã chạy | Phạm vi, môi trường, dữ liệu, phiên bản và kết quả là gì? |
| Phát hiện còn mở | Có lỗi, giới hạn hoặc giả định nào chưa được xác minh? |
| Rủi ro còn lại | Khả năng và tác động còn lại được đánh giá thế nào? |
| Chủ sở hữu và quyết định | Ai chấp nhận, giảm thiểu tiếp hoặc hoãn phát hành? |
| Thời điểm xem lại | Sự kiện nào sẽ kích hoạt đánh giá lại? |

Có thể dùng các mức cao, trung bình, thấp hoặc thang điểm nội bộ, nhưng cần định nghĩa cách xếp hạng. Đừng coi tỷ lệ pass hoặc độ bao phủ mã nguồn là đại diện trực tiếp cho mức giảm rủi ro. Chúng là chỉ số hỗ trợ, cần được đọc cùng mức độ bao phủ tình huống, chất lượng dữ liệu, tính độc lập của kiểm soát và hậu quả nếu lỗi xảy ra.

## 11. Những sai lầm thường gặp khi chọn biện pháp giảm thiểu

**Chỉ thêm test mà không sửa nguyên nhân.** Một bài kiểm thử phát hiện lỗi nhưng lỗi vẫn được phát hành hoặc lặp lại ở đường đi khác. Cần gắn phát hiện với hành động sửa và kiểm thử hồi quy.

**Dùng pass rate để kết luận an toàn.** Các test có thể không bao phủ rủi ro nghiêm trọng hoặc có thể dùng dữ liệu mô phỏng không phản ánh thực tế. Hãy báo cáo rõ phạm vi và giới hạn bằng chứng.

**Dùng kiểm thử thay cho kiểm soát phòng ngừa.** Kiểm thử phân quyền không thay thế việc kiểm tra quyền ở phía máy chủ. Kiểm thử backup không thay thế việc tạo và bảo vệ bản sao lưu.

**Dùng monitoring thay cho ngăn ngừa.** Cảnh báo sau khi dữ liệu đã bị lộ không thể đảo ngược việc lộ dữ liệu. Cần giới hạn quyền, giảm dữ liệu nhạy cảm và phát hiện bất thường kết hợp.

**Dùng rollback cho mọi sự cố.** Migration phá vỡ tương thích hoặc giao dịch đã hoàn tất có thể khiến rollback gây thêm hỏng dữ liệu. Cần thiết kế và kiểm thử đường quay lui riêng.

**Coi một kiểm soát là đủ.** Một lớp có thể thất bại do cấu hình, quyền hoặc phụ thuộc chung. Với rủi ro cao, cần nhiều lớp có mục tiêu rõ ràng và mức độc lập phù hợp.

**Không cập nhật rủi ro sau thay đổi.** Một thư viện, nhà cung cấp hoặc cấu hình mới có thể làm giả định cũ không còn đúng. Hãy kích hoạt rà soát khi có thay đổi liên quan.

## 12. Quy trình lựa chọn và theo dõi biện pháp giảm thiểu

Có thể áp dụng quy trình sau cho mỗi rủi ro ưu tiên:

1. **Mô tả sự kiện và hậu quả:** viết rõ điều gì có thể xảy ra, ai hoặc tài sản nào chịu ảnh hưởng.
2. **Tìm nguyên nhân:** xem xét yêu cầu, thiết kế, mã nguồn, dữ liệu, cấu hình, con người và phụ thuộc.
3. **Chọn chiến lược xử lý:** tránh, giảm khả năng, giới hạn tác động, phát hiện, phục hồi, chuyển giao hoặc chấp nhận.
4. **Chỉ định kiểm soát:** mô tả hành vi cụ thể, vị trí áp dụng, chủ sở hữu và cách vận hành.
5. **Thiết kế kiểm thử:** xác định điều kiện, dữ liệu, môi trường, kết quả mong đợi và bằng chứng.
6. **Thực thi và xử lý phát hiện:** sửa lỗi, thay đổi kiểm soát hoặc ghi nhận giới hạn.
7. **Đánh giá rủi ro còn lại:** xem xét bằng chứng và các giả định chưa được xác minh.
8. **Phê duyệt và theo dõi:** ghi người quyết định, thời hạn, chỉ số vận hành và điều kiện đánh giá lại.

Sơ đồ sau cho thấy mối quan hệ giữa kiểm thử và các lớp kiểm soát:

~~~mermaid
flowchart TD
    A["Nhận diện rủi ro và nguyên nhân"] --> B["Chọn biện pháp thiết kế / phòng ngừa"]
    B --> C["Chọn kiểm soát vận hành và phục hồi"]
    B --> D["Thiết kế kiểm thử xác minh"]
    C --> D
    D --> E["Chạy kiểm thử và thu thập bằng chứng"]
    E --> F{"Kiểm soát có hiệu lực?"}
    F -->|Không| G["Phân tích nguyên nhân và cải thiện kiểm soát"]
    G --> B
    F -->|Có| H["Đánh giá rủi ro còn lại"]
    H --> I{"Nằm trong mức chấp nhận?"}
    I -->|Không| B
    I -->|Có| J["Ghi nhận quyết định và theo dõi vận hành"]
    J --> K["Rà soát khi có thay đổi hoặc sự cố"]
    K --> A
~~~

## 13. Checklist rà soát

Trước khi kết luận một rủi ro đã được giảm thiểu, hãy kiểm tra:

- Sự kiện, nguyên nhân và hậu quả được mô tả rõ ràng chưa?
- Nhóm đã tìm biện pháp loại bỏ hoặc giảm nguyên nhân ngay trong thiết kế chưa?
- Có cơ chế giới hạn phạm vi ảnh hưởng khi một thành phần thất bại không?
- Kiểm thử được thiết kế để xác minh đúng biện pháp và tình huống rủi ro chưa?
- Có kiểm thử đường đi lỗi, dữ liệu bất thường, thao tác lặp và phụ thuộc không sẵn sàng chưa?
- Biện pháp vận hành có người theo dõi, ngưỡng cảnh báo và runbook chưa?
- Backup, restore, rollback hoặc failover đã được diễn tập trong điều kiện phù hợp chưa?
- Các kiểm soát có phụ thuộc vào cùng một giả định hoặc điểm lỗi đơn không?
- Kết quả kiểm thử có gắn với phiên bản, môi trường và dữ liệu cụ thể không?
- Phát hiện còn mở và giới hạn bằng chứng đã được ghi lại chưa?
- Rủi ro còn lại có người chấp nhận, thời hạn và điều kiện xem lại không?

Một chiến lược giảm thiểu tốt không đo thành công bằng số lượng bài kiểm thử đã thêm. Nó thể hiện được nguyên nhân nào đã được xử lý, kiểm soát nào đang bảo vệ hệ thống, kiểm thử nào xác minh kiểm soát đó và cách nhóm phát hiện, ứng phó khi rủi ro vẫn xảy ra. Khi các lớp này được nối với nhau bằng bằng chứng và trách nhiệm rõ ràng, nhóm có cơ sở vững chắc hơn để quyết định phát hành và duy trì chất lượng trong vận hành.

