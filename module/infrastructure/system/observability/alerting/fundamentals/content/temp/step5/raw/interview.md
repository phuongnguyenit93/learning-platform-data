Bạn sẽ giải thích sự khác nhau giữa monitoring, observability và alerting trong vận hành một hệ thống như thế nào?
Một cảnh báo có ý nghĩa cần giúp người nhận đưa ra quyết định hoặc hành động gì?
Bạn sẽ phân biệt sự kiện quan sát được, dấu hiệu bất thường và sự cố thực sự ảnh hưởng người dùng ra sao?
Bạn sẽ xây dựng quy trình từ tín hiệu observability đến cảnh báo và phản ứng của người trực như thế nào?
Bạn sẽ giải thích vì sao không nên tạo cảnh báo cho mọi metric có thể thu thập?
Bạn sẽ chọn giữa metrics, logs, traces và synthetic checks làm nguồn phát hiện sự cố theo tiêu chí nào?
Bạn sẽ phân biệt cảnh báo về triệu chứng người dùng với cảnh báo về nguyên nhân kỹ thuật bằng ví dụ nào?
Bạn sẽ quyết định khi nào một tín hiệu cần cảnh báo ngay và khi nào chỉ nên hiển thị trên dashboard ra sao?
Bạn sẽ xác định trách nhiệm xử lý và người sở hữu trước khi đưa một cảnh báo mới vào vận hành như thế nào?
Bạn sẽ đánh giá mối liên hệ giữa chất lượng cảnh báo, thời gian phát hiện và thời gian khắc phục sự cố ra sao?
Bạn sẽ mô tả đặc điểm của một cảnh báo có thể hành động được và một cảnh báo chỉ tạo thêm nhiễu như thế nào?
Bạn sẽ xây dựng tiêu chí để biết người trực có đủ thông tin hành động mà không cần tìm hiểu lại từ đầu ra sao?
Bạn sẽ giải thích SLI, SLO và SLA khác nhau về mục đích và đối tượng sử dụng như thế nào?
Bạn sẽ lựa chọn SLI phù hợp cho một API cần đáp ứng nhanh và trả kết quả chính xác như thế nào?
Bạn sẽ phân biệt availability, latency, error rate và correctness khi đánh giá trải nghiệm người dùng ra sao?
Bạn sẽ chọn mẫu số và tử số cho SLI tỷ lệ request thành công để tránh làm sai lệch kết quả như thế nào?
Bạn sẽ phân loại các mã phản hồi HTTP được tính là lỗi trong SLI theo hợp đồng dịch vụ và ngữ cảnh request ra sao?
Bạn sẽ xây dựng SLI độ trễ từ histogram thay vì chỉ dựa vào giá trị trung bình như thế nào?
Bạn sẽ đánh giá việc chọn percentile độ trễ có phản ánh đúng trải nghiệm của người dùng quan trọng hay không ra sao?
Bạn sẽ xác định khoảng thời gian đo SLO cho dịch vụ có lưu lượng biến động theo giờ và ngày như thế nào?
Bạn sẽ giải thích error budget biểu diễn phần sai lệch được chấp nhận so với SLO như thế nào?
Bạn sẽ tính và diễn giải tốc độ tiêu thụ error budget khi tỷ lệ lỗi đột ngột tăng như thế nào?
Bạn sẽ phân biệt một SLO vừa bị vi phạm với nguy cơ sớm cạn error budget để chọn hành động phù hợp ra sao?
Bạn sẽ lựa chọn cảnh báo theo error-budget burn rate thay vì ngưỡng CPU khi mục tiêu là bảo vệ người dùng như thế nào?
Bạn sẽ thiết kế cảnh báo burn rate kết hợp cửa sổ ngắn và dài để cân bằng tốc độ phát hiện với nhiễu ra sao?
Bạn sẽ đánh giá tác động của việc đặt SLO quá chặt hoặc quá lỏng lên số lượng cảnh báo như thế nào?
Bạn sẽ xác định dịch vụ ít request cần cách phát hiện lỗi nào để tránh mẫu SLI quá nhỏ gây dao động?
Bạn sẽ xử lý trường hợp không có lưu lượng trong khoảng đo SLI mà vẫn tránh hiểu nhầm là dịch vụ khỏe như thế nào?
Bạn sẽ phân biệt cảnh báo theo yêu cầu khách hàng với cảnh báo theo tài nguyên hạ tầng như thế nào?
Bạn sẽ chọn tín hiệu golden signals hoặc RED và USE cho các loại dịch vụ khác nhau như thế nào?
Bạn sẽ xác định những phụ thuộc quan trọng khiến một SLO cấp ứng dụng bị ảnh hưởng từ dịch vụ khác ra sao?
Bạn sẽ giải thích tại sao nhiều cảnh báo CPU cao không nhất thiết phản ánh mức độ ảnh hưởng đến người dùng?
Bạn sẽ lựa chọn ngưỡng cảnh báo tĩnh cho tài nguyên có giới hạn rõ ràng bằng cách nào?
Bạn sẽ sử dụng lịch sử metric để thiết lập ngưỡng theo hành vi bình thường và phát hiện sai lệch như thế nào?
Bạn sẽ so sánh ngưỡng tĩnh, ngưỡng động và phát hiện bất thường theo lợi ích và rủi ro ra sao?
Bạn sẽ xác định các điều kiện kích hoạt cảnh báo sớm và cảnh báo nguy cấp cho dung lượng đĩa như thế nào?
Bạn sẽ đánh giá tác động của khoảng lấy mẫu và cửa sổ tính toán đến độ trễ phát hiện cảnh báo ra sao?
Bạn sẽ chọn thời gian duy trì điều kiện trước khi firing để tránh cảnh báo do đột biến ngắn như thế nào?
Bạn sẽ phân biệt trạng thái pending, firing và resolved trong vòng đời một cảnh báo như thế nào?
Bạn sẽ thiết kế điều kiện khôi phục hoặc hysteresis để giảm tình trạng cảnh báo bật tắt liên tục như thế nào?
Bạn sẽ xác định ngưỡng nào cần đánh giá theo tỷ lệ và ngưỡng nào cần giá trị tuyệt đối trong một hệ thống nhiều quy mô?
Bạn sẽ thiết kế cảnh báo dung lượng còn lại dựa trên tốc độ tiêu thụ thay vì chỉ mức phần trăm như thế nào?
Bạn sẽ nhận diện sai lệch metric do counter reset và tránh tạo cảnh báo giả khi tính rate ra sao?
Bạn sẽ phân biệt gauge, counter và histogram khi chọn phép tính cho luật cảnh báo như thế nào?
Bạn sẽ kiểm tra vấn đề mẫu dữ liệu thiếu hoặc scrape thất bại trước khi kết luận metric trở về không như thế nào?
Bạn sẽ thiết kế cảnh báo về mất telemetry mà không coi việc thiếu dữ liệu là trạng thái bình thường ra sao?
Bạn sẽ phân biệt dịch vụ ngừng hoạt động với hệ thống thu thập metrics bị lỗi bằng những tín hiệu nào?
Bạn sẽ kiểm thử biểu thức cảnh báo khi label hoặc series biến mất theo thời gian như thế nào?
Bạn sẽ giải thích tại sao phép tổng hợp metrics sai nhãn có thể che giấu một vùng bị lỗi hoàn toàn?
Bạn sẽ xác định chiều phân tách cảnh báo theo service, region, cluster và environment như thế nào?
Bạn sẽ cân nhắc cardinality của labels khi tạo cảnh báo có chứa user ID, request ID hoặc đường dẫn động ra sao?
Bạn sẽ chọn mức độ phân nhóm metric để vừa phát hiện một instance lỗi vừa tránh tạo hàng trăm thông báo như thế nào?
Trong trường hợp nào lưu lượng quá thấp khiến tỷ lệ lỗi cao chưa đủ cơ sở để gửi page khẩn cấp?
Bạn sẽ kết hợp mức ảnh hưởng tuyệt đối với tỷ lệ lỗi để cảnh báo không bị méo ở tải thấp ra sao?
Bạn sẽ xây dựng cảnh báo khi một queue backlog tăng nhanh dù tổng số job chưa vượt ngưỡng cứng như thế nào?
Bạn sẽ thiết kế cảnh báo cho ứng dụng batch hoặc job chạy định kỳ khi không có dòng lưu lượng request liên tục như thế nào?
Bạn sẽ xác định cách cảnh báo khi một job quan trọng không chạy đúng lịch mà hệ thống không phát sinh metric thất bại?
Bạn sẽ lựa chọn cửa sổ thời gian đánh giá để tránh cảnh báo giả khi lưu lượng có tính mùa vụ như thế nào?
Bạn sẽ phân tích lý do một thay đổi deployment làm metric đổi tên và khiến cảnh báo im lặng ra sao?
Bạn sẽ kiểm soát phiên bản của alert rules cùng mã nguồn ứng dụng và dashboard như thế nào?
Bạn sẽ mô tả vai trò của alert rule evaluator, alert manager và notification receiver trong một pipeline cảnh báo như thế nào?
Bạn sẽ phân biệt trạng thái firing của luật cảnh báo với việc người trực đã nhận thông báo ra sao?
Bạn sẽ thiết kế labels và annotations của một alert để phân tách định danh kỹ thuật với hướng dẫn xử lý như thế nào?
Bạn sẽ quyết định những trường nào cần có trong tiêu đề và nội dung thông báo để người trực hiểu ngay mức ảnh hưởng?
Bạn sẽ đặt quy ước đặt tên alert sao cho ngắn gọn, nhất quán và không mô tả sai bản chất sự cố như thế nào?
Bạn sẽ chọn các labels như team, service, severity và environment để hỗ trợ routing mà không tạo thông tin mâu thuẫn như thế nào?
Bạn sẽ thiết kế đường dẫn từ cảnh báo đến dashboard, trace, log và runbook để điều tra nhanh ra sao?
Bạn sẽ sử dụng template trong annotations mà không vô tình đưa secret hoặc thông tin nhạy cảm vào thông báo như thế nào?
Bạn sẽ phân biệt alert fingerprint, danh tính alert và notification được tạo từ nhiều alert như thế nào?
Bạn sẽ giải thích cơ chế deduplication giúp tránh gửi lặp lại cùng sự kiện qua nhiều nguồn như thế nào?
Bạn sẽ quyết định khi nào nên gửi lại thông báo cho alert vẫn đang firing mà chưa được giải quyết như thế nào?
Bạn sẽ chọn mức độ nghiêm trọng dựa trên ảnh hưởng người dùng, độ khẩn cấp và khả năng khôi phục như thế nào?
Bạn sẽ phân biệt page, ticket và thông báo chỉ để theo dõi theo mức độ cần can thiệp ra sao?
Bạn sẽ thiết kế bảng tiêu chí severity cho một API thanh toán và một dịch vụ báo cáo nội bộ như thế nào?
Bạn sẽ xác định những điều kiện nào cần đánh thức on-call ngoài giờ thay vì chờ đến giờ làm việc?
Bạn sẽ kết hợp mức độ ảnh hưởng và phạm vi khách hàng bị tác động để ưu tiên xử lý nhiều cảnh báo cùng lúc như thế nào?
Bạn sẽ xử lý thế nào khi một alert có severity cao nhưng người trực không được phép thực hiện hành động khắc phục?
Bạn sẽ phân biệt sự cố trên môi trường thử nghiệm với production trong luật cảnh báo và định tuyến như thế nào?
Bạn sẽ chọn kênh thông báo phù hợp giữa chat, email, ticket và paging dựa trên loại sự cố như thế nào?
Bạn sẽ thiết kế chính sách escalation khi người trực không xác nhận cảnh báo trong thời gian yêu cầu như thế nào?
Bạn sẽ kiểm soát thay đổi lịch trực và chuyển giao trách nhiệm để cảnh báo không rơi vào khoảng trống ra sao?
Bạn sẽ xác định người hoặc nhóm sở hữu cuối cùng của một alert liên quan nhiều dịch vụ như thế nào?
Bạn sẽ thiết kế cơ chế xác nhận alert và liên kết với incident đang xử lý để tránh nhiều người phản ứng trùng lặp ra sao?
Bạn sẽ phân biệt notification delivery failed với tình trạng không có ai chịu trách nhiệm phản hồi như thế nào?
Bạn sẽ kiểm tra tuyến routing cho severity và team trước khi phát hành alert rules mới ra sao?
Bạn sẽ xây dựng cấu trúc routing tree để cảnh báo khẩn cấp được chuyển đúng nhóm và đúng kênh như thế nào?
Bạn sẽ phân biệt matching theo label và matching theo điều kiện phức hợp trong quy tắc routing ra sao?
Bạn sẽ xử lý cảnh báo thiếu label sở hữu để không bị rơi vào receiver mặc định không được theo dõi như thế nào?
Bạn sẽ xác định khi nào một alert cần gửi nhiều receiver và làm sao tránh thông báo lặp không cần thiết?
Bạn sẽ thiết kế chính sách routing cho sự cố chung của nhiều region nhưng chỉ một nhóm chịu trách nhiệm chính như thế nào?
Bạn sẽ mô tả grouping giúp giảm số thông báo nhưng không làm mất thông tin về các instance gặp sự cố ra sao?
Bạn sẽ lựa chọn group_by dựa trên service, alertname, cluster và severity bằng những tiêu chí nào?
Bạn sẽ phân tích vì sao grouping theo instance ID có thể làm mất lợi ích gom cảnh báo trong đợt sự cố diện rộng?
Bạn sẽ đánh giá rủi ro khi gom các alert độc lập vào cùng nhóm và khiến người trực khó xác định việc cần làm như thế nào?
Bạn sẽ phân biệt group_wait, group_interval và repeat_interval trong chính sách thông báo của Alertmanager như thế nào?
Bạn sẽ lựa chọn thời gian group_wait để chờ alert liên quan xuất hiện mà không trì hoãn phát hiện sự cố nghiêm trọng như thế nào?
Bạn sẽ xác định số lần notification phát sinh khi nhiều instance lần lượt chuyển sang firing trong cùng một nhóm ra sao?
Bạn sẽ thiết kế quy tắc thông báo resolved để người trực biết dịch vụ đã phục hồi mà không tạo thêm nhiễu như thế nào?
Bạn sẽ giải thích silence khác việc xóa alert rule hoặc tắt nguồn thu thập dữ liệu như thế nào?
Bạn sẽ tạo silence có phạm vi chính xác cho một maintenance window mà không che khuất lỗi của dịch vụ khác ra sao?
Bạn sẽ chọn nhãn matcher và thời hạn kết thúc silence để tránh vô tình tắt cảnh báo production quá rộng như thế nào?
Bạn sẽ kiểm tra các silence đang tồn tại và người tạo chúng trước khi chẩn đoán vì sao không nhận được thông báo như thế nào?
Bạn sẽ đánh giá rủi ro của silence không có thời hạn hoặc được gia hạn liên tục thay vì xử lý nguyên nhân gốc ra sao?
Bạn sẽ lên lịch maintenance và gắn đường dẫn thay đổi để người trực biết vì sao cảnh báo bị silence như thế nào?
Bạn sẽ phân biệt silence, mute time interval và inhibition theo mục đích và điều kiện áp dụng ra sao?
Bạn sẽ giải thích inhibition ngăn thông báo thứ cấp khi đã có cảnh báo nguyên nhân gốc như thế nào?
Bạn sẽ thiết kế inhibition khi một cluster mất kết nối khiến hàng loạt service cùng báo lỗi như thế nào?
Bạn sẽ xác định source alert, target alert và các labels cần bằng nhau để inhibition không chặn nhầm vùng khác ra sao?
Bạn sẽ phân tích trường hợp một alert vừa có thể là source vừa là target và ảnh hưởng đến quy tắc inhibition như thế nào?
Bạn sẽ phân biệt suppression có chủ đích với việc alert đã được giải quyết hoàn toàn như thế nào?
Bạn sẽ kiểm tra vì sao một alert đang firing nhưng không tạo notification do silence, inhibition hay routing như thế nào?
Bạn sẽ lựa chọn cơ chế giảm nhiễu khi một node ngừng hoạt động làm hàng chục ứng dụng phát cảnh báo thứ cấp ra sao?
Bạn sẽ đánh giá nguy cơ cấu hình inhibition quá rộng che mất sự cố độc lập xảy ra cùng lúc như thế nào?
Bạn sẽ thiết kế cơ chế tổng hợp cảnh báo theo nguyên nhân nhưng vẫn giữ đủ thông tin ảnh hưởng đến người dùng như thế nào?
Bạn sẽ phân biệt alert storm, flapping alert và duplicate notification theo nguyên nhân và cách giảm nhiễu ra sao?
Bạn sẽ chọn tiêu chí đo alert fatigue như số page mỗi ca trực, tỷ lệ cảnh báo không cần hành động và tỷ lệ bỏ qua như thế nào?
Bạn sẽ đánh giá tác động của hàng trăm alert không hữu ích đến khả năng phản ứng với sự cố thật như thế nào?
Bạn sẽ xử lý việc người trực thường xuyên silence một alert bằng cách phân tích dữ liệu nào?
Bạn sẽ thiết kế quy trình rà soát alert rules định kỳ để loại bỏ cảnh báo không còn đại diện cho rủi ro thực tế ra sao?
Bạn sẽ chọn điều chỉnh threshold, tăng thời gian pending hay đổi severity cho một alert liên tục flapping theo tiêu chí nào?
Bạn sẽ phân tích lịch sử sự cố để nhận biết alert phát hiện sớm và alert chỉ lặp lại triệu chứng ra sao?
Bạn sẽ thiết kế cách liên kết nhiều alert trong cùng incident để người trực tập trung xử lý một nguyên nhân gốc ra sao?
Bạn sẽ lựa chọn tín hiệu canary hoặc synthetic check để phát hiện sự cố mà metrics nội bộ vẫn bình thường như thế nào?
Bạn sẽ đặt tiêu chí đánh giá chất lượng cảnh báo sau mỗi incident và cập nhật rule như thế nào?
Bạn sẽ mô tả những thành phần bắt buộc của một runbook để người trực không biết sâu về dịch vụ vẫn có thể bắt đầu xử lý như thế nào?
Bạn sẽ xây dựng runbook cho cảnh báo tỷ lệ lỗi API tăng gồm bước xác nhận, khoanh vùng, giảm tác động và escalation ra sao?
Bạn sẽ phân biệt phần chẩn đoán với thao tác giảm thiểu rủi ro trong runbook như thế nào?
Bạn sẽ đặt điều kiện dừng hoặc xin phê duyệt trong runbook trước một hành động có thể gây mất dữ liệu như thế nào?
Bạn sẽ thiết kế đường dẫn dashboard và câu truy vấn log trong runbook để chúng không phụ thuộc vào một instance cụ thể ra sao?
Bạn sẽ lựa chọn giữa tự động khắc phục và yêu cầu người trực quyết định dựa trên mức độ rủi ro nào?
Bạn sẽ kiểm soát nguy cơ vòng lặp tự động khởi động lại dịch vụ khi vấn đề gốc chưa được xử lý ra sao?
Bạn sẽ kiểm thử runbook trong môi trường thực hành để xác minh lệnh và quyền truy cập vẫn còn hợp lệ như thế nào?
Bạn sẽ tổ chức cập nhật runbook khi chủ sở hữu dịch vụ hoặc kiến trúc hệ thống thay đổi ra sao?
Bạn sẽ xây dựng bài kiểm thử alert rule bằng dữ liệu giả lập để xác minh điều kiện pending, firing và resolved như thế nào?
Bạn sẽ kiểm chứng biểu thức của alert rule trước các trường hợp mất series, counter reset và lưu lượng bằng không ra sao?
Bạn sẽ dùng replay dữ liệu lịch sử hoặc sự cố đã ghi nhận để đo alert rule có phát hiện đúng thời điểm như thế nào?
Bạn sẽ thử nghiệm quy tắc grouping, silence và inhibition mà không gửi page thật cho người đang trực như thế nào?
Bạn sẽ xác minh thông báo đi đến đúng receiver và kênh gửi hoạt động trước khi đưa rule vào production ra sao?
Bạn sẽ thiết kế một phép thử hỗn loạn khi dịch vụ tắt đột ngột để đo thời gian phát hiện và thời gian gửi cảnh báo như thế nào?
Bạn sẽ điều tra nguyên nhân alert rule hoạt động trong môi trường thử nghiệm nhưng không kích hoạt ở production bằng những bước nào?
Bạn sẽ thực hiện review thay đổi alert rules như code, bao gồm kiểm tra labels, owner, threshold và runbook ra sao?
Bạn sẽ xây dựng quy trình rollback khi thay đổi routing hoặc grouping khiến các cảnh báo quan trọng không đến người trực như thế nào?
Bạn sẽ đánh giá hệ thống alerting có điểm lỗi đơn hay không và thiết kế tính sẵn sàng cho alert evaluator và notification manager ra sao?
Bạn sẽ phân biệt sự cố dịch vụ được giám sát với lỗi pipeline metrics hoặc hệ thống gửi thông báo bằng các cảnh báo tự giám sát như thế nào?
Bạn sẽ kiểm tra nguy cơ gửi notification trùng từ nhiều replica cảnh báo và cách cấu hình deduplication ra sao?
Bạn sẽ thiết lập cảnh báo kiểm tra định kỳ về đường truyền notification để phát hiện tích hợp paging bị ngắt như thế nào?
Bạn sẽ quản lý secret của webhook, token tích hợp và quyền cấu hình alerting trong quy trình CI/CD như thế nào?
Bạn sẽ phân tích rủi ro đưa thông tin định danh khách hàng hoặc dữ liệu nhạy cảm vào labels và nội dung notification ra sao?
Bạn sẽ thiết kế phân quyền ai được tạo, sửa, silence hoặc vô hiệu hóa cảnh báo mức nguy cấp như thế nào?
Bạn sẽ ghi nhận audit log cho các thay đổi routing, silence và mức severity để phục vụ điều tra ra sao?
Bạn sẽ xác định giới hạn chi phí và khả năng mở rộng khi số lượng series, alert rules và notification recipients tăng mạnh như thế nào?
Bạn sẽ lựa chọn những chỉ số nào để giám sát độ trễ đánh giá rule, hàng đợi notification và tỷ lệ gửi thất bại?
Bạn sẽ chẩn đoán tình huống dashboard báo API lỗi nhưng alert không firing bằng cách kiểm tra chuỗi tín hiệu nào?
Bạn sẽ điều tra tại sao alert đã firing trong hệ thống quan sát nhưng người trực không nhận được thông báo như thế nào?
Bạn sẽ xử lý sự cố nhiều cảnh báo nguy cấp cùng xuất hiện nhưng một vài cảnh báo chỉ là hệ quả của một dependency lỗi ra sao?
Bạn sẽ xây dựng tiêu chí nghiệm thu về độ chính xác, khả năng hành động, độ trễ cảnh báo, đúng tuyến nhận và mức độ nhiễu trước khi vận hành như thế nào?
