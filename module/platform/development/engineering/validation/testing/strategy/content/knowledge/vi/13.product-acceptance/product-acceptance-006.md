# Kiểm tra mức sẵn sàng vận hành cùng nhóm phụ trách hệ thống

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, chấp nhận sản phẩm không chỉ là xác nhận người dùng hoàn thành được các tác vụ nghiệp vụ. Trước khi đưa phiên bản vào sử dụng, tổ chức còn cần biết hệ thống có thể được triển khai, giám sát, hỗ trợ, bảo vệ và khôi phục trong môi trường vận hành thực tế hay không. Vì vậy, nhóm phát triển và kiểm thử cần phối hợp với nhóm phụ trách hệ thống để đánh giá **mức sẵn sàng vận hành** (operational readiness).

Kiểm tra mức sẵn sàng vận hành xem xét liệu con người, quy trình, công cụ, hạ tầng và sản phẩm đã đủ điều kiện để vận hành an toàn, ổn định và có thể hỗ trợ sau phát hành hay chưa. Hoạt động này thường được tổ chức dưới dạng operational readiness review (ORR), service readiness review hoặc một bước đánh giá tương đương trong quy trình phát hành của tổ chức.

Đánh giá này bổ sung cho kiểm thử chấp nhận nghiệp vụ. Một ứng dụng có thể đáp ứng đúng yêu cầu và được người dùng xác nhận, nhưng vẫn chưa sẵn sàng nếu không có cảnh báo khi dịch vụ ngừng hoạt động, không có quy trình khôi phục dữ liệu, không ai chịu trách nhiệm trực ca hoặc nhóm hỗ trợ không biết cách xử lý sự cố. Ngược lại, hạ tầng có thể được cấu hình tốt nhưng sản phẩm vẫn chưa đáp ứng nhu cầu sử dụng. Quyết định chấp nhận cần xem xét cả hai loại bằng chứng.

## 1. Mức sẵn sàng vận hành là gì?

Mức sẵn sàng vận hành là mức độ mà một sản phẩm hoặc dịch vụ đã đáp ứng các điều kiện cần để được triển khai và duy trì trong môi trường mục tiêu. Những điều kiện này bao gồm khả năng triển khai, quan sát, xử lý sự cố, bảo vệ dữ liệu, khôi phục dịch vụ, hỗ trợ người dùng và duy trì trách nhiệm rõ ràng.

Nhóm phụ trách hệ thống có thể là IT Operations, SRE, Platform Engineering, Cloud Operations, DevOps, quản trị cơ sở dữ liệu, mạng, bảo mật, help desk hoặc nhóm dịch vụ chuyên trách. Cách tổ chức khác nhau giữa các doanh nghiệp, nhưng cần xác định rõ ai chịu trách nhiệm cho từng phần của dịch vụ.

Các câu hỏi cốt lõi gồm:

- Có xác định được chủ sở hữu kỹ thuật và người chịu trách nhiệm vận hành sau phát hành không?
- Có thể triển khai, cấu hình, nâng cấp và khôi phục phiên bản theo quy trình đã kiểm chứng không?
- Có đủ metric, log, trace, dashboard và cảnh báo để phát hiện vấn đề không?
- Nhóm trực vận hành có biết cách phân loại, tiếp nhận, xử lý và chuyển cấp sự cố không?
- Có thể sao lưu và khôi phục dữ liệu trong giới hạn đã cam kết không?
- Hệ thống có đáp ứng tải, dung lượng, khả năng mở rộng và khả năng chịu lỗi dự kiến không?
- Quyền truy cập, bí mật, cấu hình bảo mật và nghĩa vụ tuân thủ đã được xem xét chưa?
- Người dùng và bộ phận hỗ trợ có tài liệu, hướng dẫn và đầu mối liên hệ cần thiết không?
- Các phụ thuộc, nhà cung cấp và giới hạn còn tồn tại đã được nhận diện chưa?

Một dịch vụ được xem là sẵn sàng khi các điều kiện bắt buộc có bằng chứng phù hợp và các rủi ro còn lại đã được đánh giá, giao người chịu trách nhiệm và chấp thuận đúng thẩm quyền.

## 2. Phân biệt chấp nhận nghiệp vụ và chấp nhận vận hành

Chấp nhận nghiệp vụ và đánh giá sẵn sàng vận hành trả lời hai nhóm câu hỏi khác nhau. Chúng có thể được thực hiện trong cùng một đợt nghiệm thu, nhưng không nên gộp thành một kết luận mơ hồ.

| Khía cạnh | Chấp nhận nghiệp vụ/sản phẩm | Chấp nhận mức sẵn sàng vận hành |
|---|---|---|
| Trọng tâm | Sản phẩm giải quyết đúng nhu cầu và quy trình của người dùng | Dịch vụ có thể triển khai, vận hành, hỗ trợ và khôi phục đáng tin cậy |
| Người tham gia chính | Người dùng đại diện, chủ sở hữu nghiệp vụ, Product Owner, đại diện khách hàng | Chủ sở hữu dịch vụ, SRE/Operations, Platform, bảo mật, hỗ trợ và các nhóm phụ thuộc |
| Câu hỏi | Người dùng có hoàn thành công việc theo tiêu chí không? | Nhóm vận hành có duy trì dịch vụ và xử lý tình huống bất thường không? |
| Bằng chứng | Kịch bản UAT, kết quả tác vụ, phản hồi và tiêu chí nghiệp vụ | Kết quả triển khai, giám sát, cảnh báo, tải, backup/restore, runbook, phân quyền và diễn tập sự cố |
| Quyết định | Chấp nhận giá trị, chức năng và phạm vi bàn giao theo nghiệp vụ | Xác nhận điều kiện đưa dịch vụ vào vận hành theo trách nhiệm và chính sách tổ chức |
| Rủi ro nếu bỏ sót | Sản phẩm không phù hợp với công việc thực tế | Dịch vụ khó phát hiện lỗi, hỗ trợ kém, gián đoạn kéo dài hoặc mất dữ liệu |

Một người có thể tham gia cả hai quyết định nếu được giao quyền, nhưng cần nêu rõ họ đang xác nhận tiêu chí nào. Chữ ký của chủ sở hữu nghiệp vụ không tự động thay thế xác nhận chuyên môn của nhóm vận hành; tương tự, xác nhận hạ tầng sẵn sàng không chứng minh người dùng chấp nhận quy trình.

## 3. Vai trò của nhóm phụ trách hệ thống

Nhóm phụ trách hệ thống cần tham gia từ giai đoạn thiết kế và chuẩn bị phát hành, không chỉ được mời đến cuối dự án để ký duyệt. Sự tham gia sớm giúp các yêu cầu vận hành được đưa vào thiết kế, kiểm thử và tiêu chí chấp nhận.

### Chủ sở hữu dịch vụ

Chủ sở hữu dịch vụ (service owner) chịu trách nhiệm tổng thể về chất lượng, rủi ro và vòng đời vận hành của dịch vụ. Họ xác định người chịu trách nhiệm, mục tiêu dịch vụ, điều kiện phát hành và cách xử lý rủi ro tồn dư. Tùy cơ cấu tổ chức, service owner có thể là một cá nhân hoặc vai trò thuộc nhóm sản phẩm/kỹ thuật.

### SRE hoặc Operations

Nhóm SRE/Operations xem xét độ tin cậy, năng lực vận hành, giám sát, cảnh báo, trực ca, runbook, xử lý sự cố, khả năng mở rộng và khôi phục. Họ cần được cung cấp quyền truy cập, kiến thức và công cụ đủ để điều tra vấn đề mà không phụ thuộc hoàn toàn vào lập trình viên ban đầu.

### Platform, hạ tầng và cơ sở dữ liệu

Các nhóm này xác nhận môi trường, mạng, DNS, chứng thư, lưu trữ, tài nguyên tính toán, cơ sở dữ liệu, backup, migration, quyền và các giới hạn hạ tầng. Họ cũng xem xét khả năng triển khai lặp lại, cấu hình giữa các môi trường và tác động đến dịch vụ dùng chung.

### Bảo mật và tuân thủ

Nhóm bảo mật xem xét mô hình đe dọa, quyền truy cập, bí mật, mã hóa, lỗ hổng, nhật ký kiểm toán và quy trình ứng phó. Nhóm tuân thủ hoặc quyền riêng tư xác nhận các nghĩa vụ liên quan đến dữ liệu, lưu giữ, truy cập và báo cáo. Những tiêu chí bắt buộc cần được xác định là điều kiện chặn phát hành nếu chính sách quy định như vậy.

### Hỗ trợ người dùng và Service Desk

Nhóm hỗ trợ cần biết sản phẩm có chức năng gì, người dùng thường gặp vấn đề nào, cách thu thập thông tin, cách xử lý sự cố phổ biến và khi nào cần chuyển cấp. Họ cần có tài liệu, mã lỗi, kênh liên hệ và quyền truy cập phù hợp để hỗ trợ mà không vượt quá phạm vi được phép.

### Nhóm phát triển và kiểm thử

Nhóm phát triển cung cấp kiến trúc, cấu hình, hướng dẫn triển khai, thông tin phụ thuộc và hỗ trợ xử lý lỗi. Nhóm QA/Test cung cấp bằng chứng kiểm thử, các giới hạn đã biết, lỗi còn mở và những tình huống chưa được kiểm tra. Cả hai cần phối hợp với Operations để xác minh hệ thống có thể vận hành trong thực tế.

## 4. Các lĩnh vực cần đánh giá trong operational readiness review

ORR nên dựa trên đặc điểm và rủi ro của dịch vụ. Không phải dịch vụ nào cũng cần cùng mức độ kiểm tra, nhưng các lĩnh vực dưới đây là những nội dung thường cần xem xét.

### Quyền sở hữu và trách nhiệm

- Có service owner và nhóm kỹ thuật chịu trách nhiệm rõ ràng.
- Có đầu mối trực ca, người thay thế và quy trình chuyển cấp.
- Có danh sách phụ thuộc nội bộ và nhà cung cấp, kèm thông tin liên hệ.
- Có thỏa thuận trách nhiệm giữa nhóm phát triển, vận hành, bảo mật và hỗ trợ.
- Có lịch bảo trì, cửa sổ triển khai và quy tắc thông báo thay đổi.

### Triển khai và quản lý cấu hình

- Quy trình build, deploy, nâng cấp và rollback/roll-forward được mô tả và kiểm tra.
- Artifact có định danh phiên bản, nguồn gốc và tính toàn vẹn.
- Cấu hình theo môi trường được quản lý có kiểm soát; không lưu bí mật trong mã nguồn.
- Feature flag, canary hoặc rollout theo giai đoạn có chủ sở hữu và điều kiện dừng.
- Migration dữ liệu có kế hoạch, kiểm tra tương thích và phương án khôi phục.
- Có thể xác định chính xác phiên bản đang chạy trên từng môi trường hoặc vùng triển khai.

### Giám sát và khả năng quan sát

- Có metric về lưu lượng, lỗi, độ trễ và tài nguyên.
- Có log đủ ngữ cảnh để điều tra nhưng không làm lộ dữ liệu nhạy cảm.
- Có trace hoặc correlation ID để truy vết luồng qua nhiều thành phần khi cần.
- Dashboard phản ánh trạng thái và mục tiêu dịch vụ quan trọng.
- Cảnh báo gắn với ngưỡng hoặc tín hiệu có ý nghĩa và có người nhận.
- Có thể kiểm tra một cảnh báo từ lúc phát sinh đến khi người trực nhận và xử lý.

### Độ tin cậy, hiệu năng và dung lượng

- Có mục tiêu dịch vụ hoặc ngưỡng vận hành phù hợp, ví dụ SLI/SLO.
- Đã đánh giá tải bình thường, tải cao điểm và xu hướng tăng trưởng.
- Có giới hạn tài nguyên, quota, connection pool và dung lượng lưu trữ.
- Có cơ chế xử lý khi phụ thuộc chậm hoặc không khả dụng.
- Đã xác định điểm lỗi đơn, cơ chế dự phòng và cách phục hồi.
- Có bằng chứng kiểm thử hiệu năng và độ tin cậy tương xứng với rủi ro.

### Sao lưu, khôi phục và liên tục kinh doanh

- Chính sách backup xác định dữ liệu, tần suất, thời gian lưu và quyền truy cập.
- Việc khôi phục đã được thử nghiệm; chỉ có bản backup thành công chưa đủ.
- Có RPO (mức mất dữ liệu tối đa chấp nhận) và RTO (thời gian khôi phục mục tiêu) nếu phù hợp.
- Có kế hoạch khôi phục khi mất vùng, lỗi cơ sở dữ liệu, hỏng dữ liệu hoặc sự cố nhà cung cấp.
- Có quy trình đối soát sau khôi phục và xác nhận dữ liệu nhất quán.

### Bảo mật và quyền riêng tư

- Quyền được cấp theo nguyên tắc tối thiểu cần thiết.
- Tài khoản dịch vụ, secret, khóa và chứng thư có chủ sở hữu, thời hạn và cách luân chuyển.
- Dữ liệu được bảo vệ khi truyền và lưu trữ theo yêu cầu.
- Lỗ hổng và ngoại lệ bảo mật được xử lý theo chính sách.
- Log và dữ liệu quan sát không thu thập thông tin nhạy cảm không cần thiết.
- Có quy trình thu hồi quyền, ứng phó sự cố và thông báo khi cần.

### Hỗ trợ và tài liệu

- Có runbook cho các cảnh báo và tình huống vận hành thường gặp.
- Có hướng dẫn người dùng, FAQ hoặc tài liệu hỗ trợ cần thiết.
- Có kênh tiếp nhận yêu cầu và phân loại mức độ ưu tiên.
- Nhân viên hỗ trợ biết cách thu thập thông tin và chuyển cấp.
- Có hướng dẫn xử lý bảo trì, gián đoạn, khôi phục và thông báo người dùng.
- Có đào tạo hoặc bàn giao kiến thức cho nhóm trực tiếp vận hành.

### Phụ thuộc và nhà cung cấp

- Các API, dịch vụ, broker, nền tảng và nhà cung cấp quan trọng đã được liệt kê.
- Có xác nhận về quota, SLA, giới hạn tốc độ, lịch bảo trì và đầu mối hỗ trợ.
- Có hành vi dự phòng khi phụ thuộc lỗi hoặc mất kết nối.
- Có kiểm tra tương thích phiên bản và kế hoạch khi nhà cung cấp thay đổi.
- Có cách theo dõi tình trạng dịch vụ bên ngoài và phân biệt lỗi nội bộ với lỗi phụ thuộc.

## 5. Xác định tiêu chí sẵn sàng có thể kiểm chứng

Các phát biểu như “có giám sát”, “đã chuẩn bị backup” hoặc “Operations đã được bàn giao” chưa đủ để kết luận sẵn sàng. Mỗi tiêu chí nên có kết quả mong đợi, cách kiểm tra, bằng chứng và người chịu trách nhiệm.

Ví dụ:

| Lĩnh vực | Tiêu chí có thể kiểm chứng | Bằng chứng |
|---|---|---|
| Quyền sở hữu | Có service owner, nhóm trực và đầu mối chuyển cấp được công bố | Danh sách trách nhiệm, lịch trực, thông tin liên hệ |
| Triển khai | Có thể triển khai đúng artifact vào môi trường đích và xác nhận phiên bản | Pipeline, release record, kết quả deploy và kiểm tra phiên bản |
| Rollback | Quy trình khôi phục phiên bản đã được diễn tập trong điều kiện đại diện | Biên bản diễn tập, thời gian thực hiện, kết quả kiểm tra sau rollback |
| Giám sát | Cảnh báo cho lỗi nghiêm trọng được kích hoạt và gửi đúng người nhận | Kết quả thử cảnh báo, dashboard, log nhận thông báo |
| Backup/restore | Có thể khôi phục dữ liệu mẫu hoặc môi trường phục hồi trong RTO/RPO đã thống nhất | Báo cáo restore, đối soát dữ liệu và thời gian thực tế |
| Hiệu năng | Hệ thống đáp ứng ngưỡng tải và độ trễ được xác định | Báo cáo tải, phân vị độ trễ, thông lượng và tỷ lệ lỗi |
| Bảo mật | Quyền, secret và các phát hiện nghiêm trọng được xử lý theo chính sách | Kết quả review, quét, kiểm tra quyền và phê duyệt ngoại lệ |
| Hỗ trợ | Service Desk có thể phân loại và chuyển cấp một tình huống phổ biến | Bài diễn tập, runbook, kết quả đào tạo và ghi nhận phản hồi |

Với mỗi tiêu chí, nên ghi rõ:

1. Phạm vi dịch vụ, môi trường và phiên bản áp dụng.
2. Kết quả hoặc ngưỡng cần đạt.
3. Cách kiểm tra và điều kiện thực hiện.
4. Bằng chứng phải lưu và nơi lưu.
5. Người thực hiện, người xem xét và người có quyền chấp nhận.
6. Hành động khi không đạt hoặc chưa có đủ bằng chứng.

Ngưỡng cần dựa trên mục tiêu dịch vụ, nhu cầu người dùng, rủi ro và cam kết. Không nên lấy một con số chung cho mọi hệ thống. Với hệ thống quan trọng, yêu cầu phục hồi, bảo mật và toàn vẹn dữ liệu có thể là điều kiện bắt buộc không được miễn trừ.

## 6. Các hoạt động kiểm thử để chứng minh mức sẵn sàng

ORR không chỉ là buổi xem tài liệu. Nhiều tiêu chí cần được chứng minh bằng cách thực hiện kiểm tra hoặc diễn tập trong môi trường phù hợp.

### Kiểm thử triển khai và khôi phục phiên bản

Thực hiện deploy theo đúng quy trình, xác nhận artifact, cấu hình, quyền, migration và trạng thái sau triển khai. Thử rollback hoặc roll-forward trên môi trường đại diện; kiểm tra tương thích dữ liệu và xác nhận các luồng quan trọng sau khôi phục.

### Kiểm thử giám sát và cảnh báo

Tạo tín hiệu thử nghiệm an toàn, chẳng hạn lỗi có kiểm soát hoặc ngưỡng giả lập, rồi xác nhận metric được ghi nhận, cảnh báo được kích hoạt, thông báo đến đúng người và runbook liên quan có thể sử dụng. Không tạo sự cố thật trên production chỉ để kiểm tra nếu chưa có kế hoạch và phê duyệt.

### Kiểm thử tải và khả năng mở rộng

Chạy tải đại diện với lưu lượng, dữ liệu và cấu hình phù hợp. Theo dõi độ trễ theo phân vị, thông lượng, tỷ lệ lỗi, tài nguyên, hàng đợi và giới hạn phụ thuộc. Kiểm tra hành vi khi tăng tải, giảm tài nguyên hoặc phụ thuộc chậm; xác nhận hệ thống suy giảm theo cách có kiểm soát.

### Kiểm thử backup và restore

Thử khôi phục dữ liệu từ bản backup vào môi trường được kiểm soát. Đối chiếu số lượng, quan hệ, trạng thái và dữ liệu quan trọng; đo thời gian thực tế; kiểm tra quyền truy cập và quy trình sau khôi phục. Nếu có yêu cầu point-in-time recovery, cần kiểm tra khả năng khôi phục đến mốc thời gian đã xác định.

### Kiểm thử failover và khả năng chịu lỗi

Mô phỏng hoặc diễn tập mất một node, vùng, kết nối hay phụ thuộc theo phạm vi an toàn. Xác nhận cơ chế chuyển đổi, phát hiện lỗi, thời gian gián đoạn, tính toàn vẹn dữ liệu và khả năng trở lại trạng thái ổn định. Phạm vi diễn tập phải được kiểm soát để không gây ảnh hưởng ngoài dự kiến.

### Kiểm thử bảo mật và quyền vận hành

Kiểm tra quyền truy cập theo vai trò, tài khoản dịch vụ, secret, chứng thư, cấu hình mạng, log và khả năng kiểm toán. Xác nhận nhóm trực có quyền cần thiết để xử lý sự cố nhưng không được cấp quyền rộng hơn mức cần thiết.

### Diễn tập xử lý sự cố và chuyển cấp

Chọn một số kịch bản như API không khả dụng, hàng đợi tăng bất thường, hết dung lượng, lỗi xác thực hoặc nhà cung cấp ngừng dịch vụ. Yêu cầu nhóm vận hành dùng dashboard, cảnh báo và runbook để xác định tác động, phân loại, xử lý hoặc chuyển cấp. Ghi nhận thời gian phát hiện, thời gian phản ứng, thông tin còn thiếu và điểm cần cải thiện.

### Bàn giao và đào tạo

Yêu cầu người nhận bàn giao thực hiện một số thao tác thực tế: tìm phiên bản đang chạy, xem dashboard, truy vấn log, xác định runbook, mở sự cố thử nghiệm và liên hệ đúng nhóm. Việc gửi tài liệu qua email hoặc đánh dấu đã họp không chứng minh người nhận có thể vận hành.

## 7. Runbook, playbook và khả năng ứng phó sự cố

Runbook mô tả các bước xử lý một tình huống vận hành cụ thể. Playbook có thể rộng hơn, bao gồm cách phối hợp và quyết định trong một nhóm tình huống. Tài liệu cần đủ rõ để người trực có thể sử dụng trong áp lực sự cố.

Một runbook hữu ích thường có:

- Tên cảnh báo hoặc triệu chứng kích hoạt.
- Mức độ nghiêm trọng và tác động có thể có.
- Cách xác nhận sự cố và dashboard/log cần xem.
- Các bước chẩn đoán an toàn, có thứ tự.
- Hành động giảm thiểu và điều kiện dừng.
- Khi nào cần chuyển cấp, ai là đầu mối và thông tin cần cung cấp.
- Cách xác nhận dịch vụ đã phục hồi.
- Liên kết đến tài liệu phụ thuộc, lịch sử sự cố và thông tin liên hệ.

Không nên đưa lệnh nguy hiểm hoặc thao tác thay đổi dữ liệu vào runbook mà không nêu rõ điều kiện, quyền, kiểm tra trước/sau và phương án hoàn tác. Runbook cần được kiểm tra định kỳ vì giao diện, dashboard, quyền và kiến trúc có thể thay đổi.

### Xác nhận mô hình trực và chuyển cấp

Trước phát hành, cần biết ai nhận cảnh báo ngoài giờ, ai là người thay thế, mức độ nào cần gọi người trực, ai điều phối sự cố và ai giao tiếp với người dùng. Nếu dịch vụ phụ thuộc nhiều nhóm, phải có quy trình chuyển cấp và thông tin liên hệ có thể sử dụng được.

Một bài diễn tập có thể mô phỏng cảnh báo được gửi vào kênh trực, người nhận xác nhận, tra cứu runbook, đánh giá tác động, gọi nhóm phụ thuộc và cập nhật trạng thái. Mục tiêu là phát hiện khoảng trống trong quy trình trước khi có sự cố thật.

## 8. Đánh giá mức độ sẵn sàng và xử lý ngoại lệ

Không phải mọi tiêu chí đều có cùng mức quan trọng. Nhóm cần phân loại rõ điều kiện bắt buộc, điều kiện cần cải thiện và các rủi ro có thể được chấp nhận theo thẩm quyền.

Một cách phân loại thực tế:

- **Điều kiện chặn phát hành:** vi phạm có thể gây hậu quả nghiêm trọng hoặc trái yêu cầu bắt buộc, chẳng hạn không có quyền truy cập kiểm soát, thiếu khả năng khôi phục dữ liệu quan trọng hoặc chưa xử lý lỗ hổng nghiêm trọng theo chính sách.
- **Điều kiện cần hoàn tất trước khi mở rộng:** dịch vụ có thể chạy giới hạn nhưng cần hoàn thành trước khi tăng lưu lượng hoặc mở cho toàn bộ người dùng, chẳng hạn dashboard cho một phân khúc hoặc diễn tập bổ sung.
- **Cải tiến sau phát hành:** vấn đề có tác động thấp, có biện pháp kiểm soát và có người phụ trách cùng thời hạn rõ ràng.

Phân loại phải theo chính sách tổ chức và mức độ rủi ro của dịch vụ. Không được tự chuyển một tiêu chí bắt buộc thành cải tiến sau phát hành chỉ để kịp lịch.

### Khi chưa đạt tiêu chí

Với mỗi tiêu chí chưa đạt, ghi rõ:

1. Điều kiện chưa đạt và bằng chứng hiện có.
2. Tác động nếu phát hành trong trạng thái này.
3. Biện pháp giảm thiểu hoặc giới hạn phạm vi sử dụng.
4. Người chịu trách nhiệm khắc phục và thời hạn.
5. Người có thẩm quyền chấp nhận rủi ro, nếu chính sách cho phép.
6. Điều kiện phải kiểm tra lại và tiêu chí đóng ngoại lệ.

Một quyết định chấp nhận có điều kiện phải có phạm vi, thời hạn và người chịu trách nhiệm. Không nên chấp nhận vô thời hạn một dịch vụ không có người trực, không có cách khôi phục hoặc không đáp ứng nghĩa vụ bắt buộc.

### Quyết định Go/No-Go

Kết quả ORR có thể được dùng trong quyết định Go/No-Go trước phát hành hoặc trước khi mở rộng rollout. Quyết định cần xem xét:

- Các điều kiện chặn đã đạt chưa?
- Các rủi ro cao đã có biện pháp kiểm soát và người chấp nhận chưa?
- Nhóm vận hành có khả năng nhận trách nhiệm và hỗ trợ không?
- Các giới hạn, ngoại lệ và kế hoạch khắc phục đã được ghi nhận chưa?
- Có phương án dừng, giảm lưu lượng hoặc khôi phục nếu tín hiệu xấu xuất hiện không?

Go không có nghĩa là không còn rủi ro; nó có nghĩa bằng chứng và rủi ro đã được xem xét theo tiêu chí và thẩm quyền. No-Go cần kèm điều kiện để đánh giá lại, thay vì chỉ ghi “chưa sẵn sàng”.

## 9. Quy trình tổ chức operational readiness review

Một quy trình ORR có thể triển khai theo các bước sau:

### Bước 1: Xác định phạm vi dịch vụ và thời điểm đánh giá

Ghi rõ tên dịch vụ, phiên bản, môi trường, vùng triển khai, nhóm người dùng, phụ thuộc và thay đổi của đợt phát hành. Xác định đây là lần đưa dịch vụ mới vào vận hành, thay đổi kiến trúc, mở rộng quy mô hay đánh giá định kỳ.

### Bước 2: Chỉ định người tham gia và người quyết định

Mời service owner, nhóm phát triển, QA, Operations/SRE, Platform, bảo mật, dữ liệu, hỗ trợ và đại diện nghiệp vụ theo phạm vi. Xác định ai cung cấp bằng chứng, ai review chuyên môn, ai nhận trách nhiệm vận hành và ai có quyền chấp nhận ngoại lệ hoặc quyết định Go/No-Go.

### Bước 3: Xác định tiêu chí và mức độ bắt buộc

Chọn các lĩnh vực cần đánh giá theo rủi ro. Ghi rõ điều kiện chặn, điều kiện cần hoàn tất trước khi mở rộng và cải tiến có thể theo dõi sau phát hành. Thống nhất cách đo và bằng chứng trước khi xem kết quả.

### Bước 4: Thu thập hồ sơ và thực hiện diễn tập

Review kiến trúc, runbook, dashboard, quyền, backup, quy trình deploy và phụ thuộc. Thực hiện các bài kiểm tra cần thiết như smoke, alert test, restore, load, failover hoặc incident simulation. Không chỉ đánh dấu tài liệu đã tồn tại; cần xác minh chúng hoạt động.

### Bước 5: Đánh giá khoảng trống và rủi ro tồn dư

Với mỗi tiêu chí, ghi trạng thái đạt, chưa đạt hoặc chưa có đủ bằng chứng. Xác định nguyên nhân, tác động, biện pháp giảm thiểu, chủ sở hữu và thời hạn. Phân biệt lỗi có thể khắc phục trước phát hành với giới hạn cần quyết định ở cấp quản trị.

### Bước 6: Họp review và đưa ra quyết định

Trình bày bằng chứng, kết quả diễn tập, lỗi còn mở và rủi ro tồn dư. Các nhóm chuyên môn xác nhận trong phạm vi trách nhiệm; service owner hoặc người có thẩm quyền đưa ra quyết định theo quy chế. Ghi rõ Go, No-Go hoặc Go có điều kiện nếu được phép.

### Bước 7: Theo dõi điều kiện và xác nhận sau triển khai

Theo dõi các hành động còn mở đến khi hoàn tất. Sau khi triển khai, xác nhận phiên bản, dashboard, cảnh báo, luồng quan trọng và khả năng tiếp nhận sự cố. Cập nhật hồ sơ dịch vụ dựa trên dữ liệu thực tế.

## 10. Ví dụ xuyên suốt: đưa ứng dụng quản lý kho vào vận hành

Giả sử tổ chức chuẩn bị phát hành ứng dụng quản lý nhập, xuất và kiểm kê cho nhiều kho. Người dùng đã hoàn thành UAT cho các luồng chính. Tuy nhiên, ứng dụng còn phụ thuộc vào hệ thống danh tính, cơ sở dữ liệu trung tâm, dịch vụ đồng bộ và thiết bị quét mã.

### Các vấn đề vận hành cần xác nhận

- Nhóm trực biết cách phát hiện lỗi đăng nhập hoặc đồng bộ.
- Có dashboard theo dõi tỷ lệ đồng bộ thành công, hàng đợi tồn đọng và độ trễ.
- Cảnh báo khi hàng đợi vượt ngưỡng được gửi đến đúng nhóm.
- Backup dữ liệu kho có thể khôi phục và đối soát.
- Quy trình deploy hỗ trợ phiên bản ứng dụng và schema tương thích trong thời gian rollout.
- Có runbook xử lý thiết bị mất kết nối, thông điệp đồng bộ trùng và lỗi xác thực.
- Service Desk biết cách thu thập mã kho, thiết bị, thời điểm và mã giao dịch trước khi chuyển cấp.
- Quyền truy cập của nhân viên trực được cấp theo vai trò và có thể kiểm toán.

### Một số tiêu chí và phép kiểm tra

| Tiêu chí | Cách kiểm tra | Kết quả cần lưu |
|---|---|---|
| Cảnh báo hàng đợi đồng bộ | Tạo backlog thử nghiệm trong môi trường được kiểm soát | Thời điểm phát hiện, người nhận, nội dung cảnh báo và runbook |
| Khôi phục dữ liệu | Restore bản backup vào môi trường phục hồi | Thời gian, số bản ghi, đối soát và sai lệch |
| Triển khai phiên bản | Thực hiện pipeline trên môi trường staging tương đương | Artifact, cấu hình, migration và kết quả smoke test |
| Xử lý mất kết nối | Mô phỏng thiết bị ngoại tuyến rồi kết nối lại | Số giao dịch đồng bộ, phát hiện trùng và trạng thái cuối |
| Chuyển cấp sự cố | Diễn tập lỗi đăng nhập hoặc dịch vụ danh tính | Thời gian tiếp nhận, thông tin chuyển cấp và kết quả khôi phục |
| Quyền vận hành | Kiểm tra tài khoản trực theo vai trò | Quyền được cấp, thao tác được phép và log kiểm toán |

### Quyết định phát hành

Giả sử UAT đạt, nhưng diễn tập khôi phục cho thấy thời gian restore vượt mục tiêu RTO và nhóm vận hành chưa có runbook đối soát dữ liệu. Đây là khoảng trống vận hành có tác động lớn. Nhóm cần đánh giá liệu có thể phát hành giới hạn với phương án giảm thiểu được phê duyệt hay phải hoãn để hoàn thiện khả năng khôi phục. Việc người dùng đã chấp nhận chức năng không tự giải quyết rủi ro này.

Nếu tổ chức cho phép Go có điều kiện, quyết định cần ghi rõ giới hạn quy mô hoặc phạm vi sử dụng, người chịu trách nhiệm hoàn thiện restore, thời hạn, điều kiện mở rộng và cách kiểm tra lại. Nếu RTO hoặc khả năng khôi phục là yêu cầu bắt buộc, phải đạt tiêu chí trước khi phát hành theo chính sách.

## 11. Hồ sơ bàn giao cho nhóm vận hành

Hồ sơ bàn giao cần giúp nhóm vận hành hiểu hệ thống, xử lý các tình huống phổ biến và biết khi nào cần gọi hỗ trợ chuyên môn. Tùy dịch vụ, bộ hồ sơ có thể gồm:

- Sơ đồ kiến trúc, luồng dữ liệu và danh sách phụ thuộc.
- Danh mục môi trường, phiên bản, cấu hình và quy trình triển khai.
- Danh sách service owner, nhóm trực, người thay thế và đầu mối nhà cung cấp.
- Dashboard, metric, log, trace, cảnh báo và định nghĩa SLI/SLO.
- Runbook, playbook, hướng dẫn khôi phục và quy trình chuyển cấp.
- Chính sách backup, kết quả restore, RPO/RTO và kế hoạch khôi phục thảm họa nếu áp dụng.
- Ma trận quyền, quy trình cấp/thu hồi quyền, quản lý secret và chứng thư.
- Kết quả kiểm thử hiệu năng, bảo mật, độ tin cậy và các giới hạn đã biết.
- Hướng dẫn người dùng, FAQ, mã lỗi và quy trình hỗ trợ.
- Danh sách lỗi còn mở, ngoại lệ, rủi ro tồn dư và hành động có thời hạn.

Hồ sơ phải được cập nhật khi kiến trúc, dashboard, quyền, quy trình hoặc phụ thuộc thay đổi. Tài liệu lỗi thời có thể nguy hiểm hơn việc thiếu tài liệu vì người trực có thể thực hiện sai bước dựa trên thông tin cũ.

## 12. Những sai lầm thường gặp

**Chỉ mời Operations vào cuối dự án.** Khi vận hành tham gia muộn, các vấn đề như thiếu log, không có quyền, cấu hình khó triển khai hoặc không có phương án backup có thể đòi hỏi thay đổi lớn. Hãy đưa yêu cầu vận hành vào thiết kế và tiêu chí kiểm thử từ sớm.

**Coi ORR là buổi ký checklist.** Một tài liệu có đủ mục không chứng minh các quy trình hoạt động. Cần thực hiện diễn tập deploy, cảnh báo, restore, chuyển cấp và các kiểm tra rủi ro cao.

**Đồng nhất UAT với operational readiness.** UAT xác nhận mức phù hợp nghiệp vụ; ORR đánh giá khả năng vận hành. Cần có bằng chứng riêng cho cả hai.

**Không có service owner rõ ràng.** Khi xảy ra sự cố, các nhóm có thể không biết ai điều phối và ai quyết định. Chỉ định chủ sở hữu, nhóm trực và cơ chế thay thế trước phát hành.

**Có dashboard nhưng không có cảnh báo hành động được.** Chỉ số không được theo dõi hoặc không có người nhận không giúp phát hiện sự cố kịp thời. Kiểm tra đường đi của cảnh báo từ nguồn đến người xử lý.

**Có backup nhưng chưa thử restore.** Backup có thể thiếu dữ liệu, không truy cập được hoặc mất quá nhiều thời gian để khôi phục. Cần diễn tập và đối soát theo mục tiêu.

**Runbook chỉ có trên giấy.** Các bước có thể sai, thiếu quyền hoặc không còn phù hợp với phiên bản hiện tại. Yêu cầu người trực thực hiện thử và cập nhật theo phản hồi.

**Chấp nhận rủi ro không có thời hạn.** Ngoại lệ kéo dài dễ trở thành trạng thái bình thường. Mọi ngoại lệ cần người phê duyệt, phạm vi, biện pháp giảm thiểu, thời hạn và điều kiện đóng.

**Không kiểm tra năng lực hỗ trợ người dùng.** Nhóm phát triển có thể biết hệ thống nhưng Service Desk lại không biết mã lỗi, thông tin cần thu thập hoặc đầu mối chuyển cấp. Cần diễn tập một yêu cầu hỗ trợ thực tế.

## 13. Checklist đánh giá mức sẵn sàng vận hành

Về trách nhiệm và phối hợp:

- [ ] Đã chỉ định service owner, nhóm vận hành, người trực và đầu mối thay thế.
- [ ] Trách nhiệm giữa phát triển, QA, Operations, bảo mật, hỗ trợ và nhà cung cấp đã rõ.
- [ ] Kênh liên hệ, quy trình chuyển cấp và lịch bảo trì đã được công bố.

Về triển khai và hạ tầng:

- [ ] Artifact, phiên bản và cấu hình được quản lý có kiểm soát.
- [ ] Quy trình deploy, migration, rollback/roll-forward đã được kiểm tra.
- [ ] Môi trường, mạng, chứng thư, tài nguyên và phụ thuộc đã sẵn sàng.
- [ ] Giới hạn tải, dung lượng và quota đã được đánh giá.

Về giám sát và xử lý sự cố:

- [ ] Metric, log, trace và dashboard phản ánh các luồng quan trọng.
- [ ] Cảnh báo có ngưỡng phù hợp, người nhận và hành động rõ.
- [ ] Runbook và playbook đã được người vận hành thử.
- [ ] Quy trình trực, phân loại, điều phối và chuyển cấp đã được diễn tập.

Về dữ liệu, bảo mật và phục hồi:

- [ ] Backup có phạm vi, tần suất, thời hạn lưu và quyền truy cập rõ.
- [ ] Restore đã được thử và đối soát theo mục tiêu RPO/RTO nếu áp dụng.
- [ ] Quyền, secret, chứng thư, mã hóa và log kiểm toán đáp ứng chính sách.
- [ ] Kế hoạch failover hoặc khôi phục thảm họa đã được xem xét theo mức rủi ro.

Về hỗ trợ và quyết định:

- [ ] Service Desk có tài liệu và đã thực hành tiếp nhận/chuyển cấp.
- [ ] Nhóm vận hành đã nhận bàn giao và có thể thực hiện thao tác thiết yếu.
- [ ] Tiêu chí chặn phát hành, ngoại lệ và rủi ro tồn dư được ghi nhận.
- [ ] Người có thẩm quyền đã đưa ra quyết định Go/No-Go hoặc Go có điều kiện.
- [ ] Các hành động còn mở có người phụ trách, thời hạn và cách xác minh.

## 14. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Người dùng đã hoàn thành UAT và xác nhận quy trình tạo đơn đúng. Tuy nhiên, không có nhóm trực chịu trách nhiệm khi API ngừng hoạt động. Sản phẩm đã có bằng chứng chấp nhận nghiệp vụ nhưng còn thiếu điều kiện sẵn sàng vận hành; cần xác định service owner, lịch trực và quy trình ứng phó trước khi phát hành theo chính sách.

**Tình huống 2:** Dashboard hiển thị độ trễ và tỷ lệ lỗi, nhưng cảnh báo chưa được cấu hình gửi đến người trực. Có khả năng quan sát một phần nhưng chưa có quy trình phát hiện và phản ứng đầy đủ. Cần kiểm tra cảnh báo từ lúc kích hoạt đến khi người nhận xác nhận và thực hiện runbook.

**Tình huống 3:** Backup chạy hằng ngày và báo thành công, nhưng chưa ai thử khôi phục. Chưa đủ bằng chứng về khả năng phục hồi. Cần thực hiện restore trong môi trường được kiểm soát, đo thời gian và đối soát dữ liệu với mục tiêu đã thống nhất.

**Tình huống 4:** Nhóm Operations yêu cầu bổ sung runbook và dashboard trước khi mở rộng lưu lượng. Đây là yêu cầu vận hành cần được đánh giá theo rủi ro và tiêu chí. Nếu thiếu chúng làm nhóm không thể phát hiện hoặc xử lý sự cố, có thể phải giữ rollout hoặc đặt điều kiện rõ ràng trước khi mở rộng.

**Tình huống 5:** Một dịch vụ đạt kiểm thử tải nhưng phụ thuộc vào nhà cung cấp chưa có đầu mối hỗ trợ và không có phương án khi dịch vụ đó ngừng hoạt động. Kết quả tải chưa đủ chứng minh sẵn sàng. Cần đánh giá phụ thuộc, SLA, giới hạn, cảnh báo và hành vi suy giảm an toàn.

Khi chuẩn bị đưa sản phẩm vào vận hành, hãy tự hỏi: **ai chịu trách nhiệm khi hệ thống gặp vấn đề, họ phát hiện và xử lý bằng cách nào, dữ liệu có thể khôi phục ra sao và bằng chứng nào chứng minh các quy trình đó hoạt động?** Nếu chưa trả lời được, nhóm cần bổ sung đánh giá cùng Operations trước khi quyết định phát hành.

## Kết luận

Kiểm tra mức sẵn sàng vận hành cùng nhóm phụ trách hệ thống giúp xác nhận sản phẩm có thể được triển khai, giám sát, hỗ trợ, bảo vệ và khôi phục trong môi trường thực tế. ORR cần có tiêu chí đo được, bằng chứng từ hoạt động kiểm tra và diễn tập, vai trò chịu trách nhiệm rõ ràng cùng quy trình xử lý ngoại lệ. Khi phối hợp sớm giữa phát triển, QA, nghiệp vụ, Operations, Platform, bảo mật và hỗ trợ, tổ chức có cơ sở tốt hơn để quyết định Go/No-Go và duy trì chất lượng sau phát hành.
