Bạn sẽ giải thích mục tiêu của telemetry filtering trong hệ thống quan sát gồm logs, metrics và traces như thế nào?
Bạn sẽ phân biệt lọc bỏ telemetry với che thông tin nhạy cảm, biến đổi dữ liệu và lấy mẫu theo những tiêu chí nào?
Bạn sẽ xác định khi nào một bản ghi telemetry thật sự không cần thiết cho vận hành và có thể loại bỏ ra sao?
Bạn sẽ giải thích vì sao giảm khối lượng telemetry không tự động đồng nghĩa với tăng chất lượng quan sát hệ thống?
Bạn sẽ phân loại những nguồn telemetry có tỷ lệ nhiễu cao trước khi xây dựng chính sách lọc như thế nào?
Bạn sẽ cân bằng mục tiêu giảm chi phí với khả năng phát hiện và điều tra sự cố chưa biết trước bằng cách nào?
Bạn sẽ phân biệt chính sách thu thập dữ liệu tối thiểu với việc xóa dữ liệu đã đưa vào hệ thống lưu trữ ra sao?
Bạn sẽ xác định người có thẩm quyền phê duyệt quy tắc lọc có thể loại bỏ bằng chứng vận hành quan trọng dựa trên những tiêu chí nào?
Bạn sẽ lập danh mục các tín hiệu bắt buộc phải giữ cho SLI, cảnh báo và kiểm toán trước khi bật filtering ra sao?
Bạn sẽ mô tả đường đi của telemetry từ ứng dụng qua collector đến các backend để chọn đúng điểm áp dụng lọc như thế nào?
Bạn sẽ phân biệt filtering tại SDK, agent, gateway collector và backend theo khả năng bảo vệ dữ liệu cùng chi phí ra sao?
Bạn sẽ quyết định loại bỏ telemetry càng gần nguồn càng tốt trong những trường hợp nào?
Bạn sẽ phân tích rủi ro khi dữ liệu nhạy cảm chỉ được lọc sau khi đã qua mạng hoặc queue của collector như thế nào?
Bạn sẽ xác định thông tin nào cần giữ lại sau khi lọc để vẫn điều tra được một request thất bại?
Bạn sẽ đánh giá chính sách lọc có ảnh hưởng khác nhau đến người trực vận hành, nhóm bảo mật và kiểm toán như thế nào?
Bạn sẽ phân biệt noise từ health check, debug log và request nghiệp vụ thành công bằng những đặc điểm nào?
Bạn sẽ định nghĩa một chính sách lọc có mục đích, phạm vi, người sở hữu và tiêu chí rollback như thế nào?
Bạn sẽ xác định dữ liệu nào bị coi là nhạy cảm khi xuất hiện trong log body, metric label hoặc span attribute?
Bạn sẽ phân loại thông tin cá nhân, secret, dữ liệu nghiệp vụ nội bộ và thông tin hạ tầng trước khi lọc ra sao?
Bạn sẽ giải thích vì sao một trace ID hoặc user ID có thể tạo rủi ro nếu được xuất sang hệ thống ngoài phạm vi tin cậy?
Bạn sẽ thiết kế quy tắc hạn chế URL chứa token hoặc định danh người dùng xuất hiện trong log và span như thế nào?
Bạn sẽ phân biệt giá trị cần xóa hoàn toàn với giá trị có thể giữ lại sau masking hoặc pseudonymization ra sao?
Bạn sẽ đánh giá cách loại bỏ request body chứa thông tin nhạy cảm mà vẫn giữ được mã lỗi và thời gian xử lý như thế nào?
Bạn sẽ xác định lúc nào nên chặn cả bản ghi log thay vì chỉ xóa một trường có dữ liệu nhạy cảm?
Bạn sẽ phát hiện những trường dữ liệu nhạy cảm xuất hiện trong message tự do thay vì thuộc tính có cấu trúc như thế nào?
Bạn sẽ phân tích giới hạn của việc lọc bằng tên trường khi secret nằm trong stack trace hoặc exception message ra sao?
Bạn sẽ chọn allowlist hay denylist cho các trường được phép xuất ra khỏi hệ thống theo mức rủi ro nào?
Bạn sẽ thiết kế chính sách không đưa header Authorization, cookie phiên và API key vào telemetry bằng cách nào?
Bạn sẽ xác định ngữ cảnh nào khiến địa chỉ IP, tên thiết bị hoặc định danh tenant cần được xử lý đặc biệt ra sao?
Bạn sẽ kiểm thử resource attributes để phát hiện dữ liệu nhạy cảm còn sót lại sau filtering bằng cách nào?
Bạn sẽ xử lý các bản sao telemetry đã lọt qua pipeline trước khi một chính sách lọc mới được triển khai ra sao?
Bạn sẽ phân biệt mục tiêu lọc ở đầu vào với nghĩa vụ retention hoặc deletion ở backend như thế nào?
Bạn sẽ ghi nhận cơ sở phê duyệt và yêu cầu pháp lý áp dụng cho việc giữ hoặc bỏ một nhóm audit events ra sao?
Bạn sẽ xác định những loại security log hoặc audit log không được loại bỏ chỉ vì có dung lượng lớn như thế nào?
Bạn sẽ phân biệt dữ liệu được phép lọc với dữ liệu phải lưu theo cam kết hợp đồng hoặc nghĩa vụ kiểm toán ra sao?
Bạn sẽ mô tả cách lập ma trận loại telemetry, mục đích xử lý, quy tắc lọc và người phê duyệt như thế nào?
Bạn sẽ thiết kế quy tắc lọc tách biệt môi trường development, staging và production theo những giới hạn nào?
Bạn sẽ xác định khi nào một chính sách lọc áp dụng cho mọi dịch vụ và khi nào cần ngoại lệ theo workload ra sao?
Bạn sẽ kiểm soát một ngoại lệ cho phép giữ log chi tiết trong thời gian điều tra sự cố như thế nào?
Bạn sẽ xác định thời hạn và điều kiện thu hồi ngoại lệ filtering để tránh duy trì thu thập quá mức ra sao?
Bạn sẽ tổ chức đánh giá tác động khi đội phát triển yêu cầu loại bỏ một loại log đang được dashboard hoặc cảnh báo sử dụng như thế nào?
Bạn sẽ kiểm tra các tuyến xuất dữ liệu khác nhau có dùng chung chính sách lọc hay cần cấu hình riêng như thế nào?
Bạn sẽ xây dựng quy trình review thay đổi chính sách filtering bằng pull request và bằng chứng kiểm thử ra sao?
Bạn sẽ phân biệt quyết định lọc theo trường dữ liệu với quyết định lọc theo toàn bộ bản ghi hoặc tập dữ liệu ra sao?
Bạn sẽ xác định những yêu cầu về truy vết và tính toàn vẹn cần giữ nguyên khi xử lý telemetry phục vụ kiểm toán như thế nào?
Bạn sẽ mô tả vai trò của receiver, processor, exporter và service pipeline trong OpenTelemetry Collector như thế nào?
Bạn sẽ lựa chọn Collector chạy kiểu agent hay gateway để thực thi chính sách lọc theo yêu cầu nào?
Bạn sẽ xác định vị trí filter processor trong pipeline khi còn có memory limiter, transform và batch processor ra sao?
Bạn sẽ giải thích vì sao thứ tự các processor ảnh hưởng đến hiệu quả giảm tải và khả năng bảo vệ dữ liệu như thế nào?
Bạn sẽ phân biệt filtering áp dụng cho traces, metrics và logs trong cấu hình service pipelines ra sao?
Bạn sẽ tổ chức cấu hình filter processor khi các tín hiệu khác nhau cần chính sách loại bỏ khác nhau như thế nào?
Bạn sẽ xác định phiên bản và khả năng hỗ trợ của Collector trước khi dùng một kiểu điều kiện OTTL cụ thể như thế nào?
Bạn sẽ kiểm tra filter processor có nằm trong bản phân phối Collector đang triển khai hay không bằng cách nào?
Bạn sẽ thiết kế cấu hình cho nhiều collector replica sao cho mọi instance dùng cùng một phiên bản quy tắc lọc như thế nào?
Bạn sẽ đánh giá ưu và nhược điểm khi lọc trước khi export sang nhiều backend so với lọc riêng từng nhánh pipeline ra sao?
Bạn sẽ xử lý trường hợp một backend chỉ cần số liệu tổng hợp nhưng backend khác cần trace chi tiết như thế nào?
Bạn sẽ xác định khi nào nên nhân luồng telemetry qua nhiều pipeline và khi nào không nên vì nguy cơ tạo bản sao nhạy cảm?
Bạn sẽ kiểm chứng việc cấu hình pipeline có thực sự kích hoạt filter processor thay vì chỉ khai báo processor mà không sử dụng như thế nào?
Bạn sẽ mô tả ảnh hưởng của việc drop telemetry trong Collector đến dữ liệu mà downstream backend nhận được ra sao?
Bạn sẽ đánh giá mức sử dụng CPU, bộ nhớ và độ trễ của Collector khi thêm các điều kiện lọc phức tạp như thế nào?
Bạn sẽ lựa chọn những số liệu nào để đo và so sánh lưu lượng trước và sau filter processor?
Bạn sẽ phân biệt OTTL với một ngôn ngữ truy vấn log trong backend theo thời điểm đánh giá và mục đích sử dụng ra sao?
Bạn sẽ mô tả các thành phần cơ bản của một điều kiện OTTL dùng để quyết định giữ hay loại bỏ telemetry như thế nào?
Bạn sẽ giải thích cách OTTL truy cập thuộc tính và dữ liệu trong context tương ứng của log, metric hoặc span như thế nào?
Bạn sẽ xác định sự khác nhau giữa điều kiện so sánh thuộc tính, kiểm tra sự tồn tại và so khớp chuỗi trong OTTL ra sao?
Bạn sẽ viết ý tưởng điều kiện lọc một loại log dựa trên severity mà không loại nhầm log lỗi như thế nào?
Bạn sẽ xây dựng điều kiện lọc request health check dựa trên route và trạng thái phản hồi bằng cách nào?
Bạn sẽ lựa chọn cách kết hợp điều kiện AND và OR để chỉ loại bỏ những bản ghi thỏa đúng chính sách ra sao?
Bạn sẽ phân tích hậu quả khi đảo nhầm logic giữ lại và loại bỏ trong một rule filtering như thế nào?
Bạn sẽ thiết kế điều kiện kiểm tra giá trị thiếu hoặc nil để tránh lỗi khi một thuộc tính không tồn tại như thế nào?
Bạn sẽ đánh giá việc so khớp chính xác và so khớp bằng biểu thức chính quy theo hiệu năng và độ an toàn ra sao?
Bạn sẽ lựa chọn cách viết biểu thức chính quy tránh khớp quá rộng với các tên route hoặc loại sự kiện như thế nào?
Bạn sẽ phát hiện một điều kiện OTTL phụ thuộc kiểu dữ liệu sai khi so sánh số với chuỗi bằng cách nào?
Bạn sẽ giải thích vì sao cần xác định đúng context trước khi tham chiếu thuộc tính resource, scope hoặc record?
Bạn sẽ kiểm tra điều kiện theo service.name có tác động thế nào khi giá trị resource attribute không tồn tại ra sao?
Bạn sẽ kiểm chứng ngữ nghĩa kết hợp các biểu thức OTTL trên phiên bản processor đang dùng bằng cách nào?
Bạn sẽ lựa chọn cách tách nhiều rule nhỏ thay vì tạo một điều kiện dài khó kiểm thử theo tiêu chí nào?
Bạn sẽ phân tích cách sắp xếp và đặt tên quy tắc giúp người vận hành giải thích vì sao telemetry bị drop ra sao?
Bạn sẽ mô tả ảnh hưởng của cấu hình xử lý lỗi đánh giá điều kiện khi một biểu thức OTTL không thực thi được như thế nào?
Bạn sẽ xác định khi nào nên dừng xử lý do lỗi policy và khi nào chỉ ghi nhận lỗi rồi tiếp tục pipeline ra sao?
Bạn sẽ kiểm tra cú pháp và khả năng tương thích của OTTL trước khi áp dụng cấu hình lên Collector đang phục vụ production như thế nào?
Bạn sẽ thiết kế thử nghiệm OTTL với record đầy đủ, thiếu trường và giá trị sai kiểu để kiểm chứng hành vi như thế nào?
Bạn sẽ phân biệt điều kiện OTTL dùng để lọc toàn bản ghi với phép biến đổi một trường bằng processor phù hợp ra sao?
Bạn sẽ đánh giá khi nào phải dùng transform hoặc redaction processor thay vì filter processor để giữ bản ghi nhưng xóa dữ liệu nhạy cảm?
Bạn sẽ thiết kế thứ tự transform và filter để đảm bảo dữ liệu nhạy cảm không rời khỏi vùng xử lý đáng tin cậy như thế nào?
Bạn sẽ xác minh việc filter processor có hỗ trợ đúng loại ngữ cảnh telemetry mà rule đang tham chiếu bằng cách nào?
Bạn sẽ xây dựng cơ chế kiểm soát thay đổi rule OTTL để tránh dùng cú pháp khác nhau giữa các cụm Collector ra sao?
Bạn sẽ mô tả cách lọc application log có severity DEBUG trong khi giữ ERROR và audit events quan trọng như thế nào?
Bạn sẽ phân biệt severity text và severity number khi thiết kế điều kiện lọc log như thế nào?
Bạn sẽ xác định các trường hợp log INFO vẫn cần giữ vì chứa mốc nghiệp vụ quan trọng ra sao?
Bạn sẽ thiết kế điều kiện loại bỏ log lặp lại từ health check mà không làm mất dấu hiệu dịch vụ bị lỗi như thế nào?
Bạn sẽ tránh loại bỏ log request thất bại khi cùng đường dẫn health check có status không thành công ra sao?
Bạn sẽ chọn điều kiện dựa trên logger name, service name và event type để lọc log chẩn đoán không cần thiết như thế nào?
Bạn sẽ xử lý trường hợp log message thay đổi theo ngôn ngữ hoặc phiên bản ứng dụng khiến điều kiện theo chuỗi bị sai ra sao?
Bạn sẽ xác định nên lọc log từ thư viện quá nhiều chi tiết tại source hay tại Collector theo tác động vận hành nào?
Bạn sẽ phân biệt lọc log thuộc ứng dụng với log bảo mật hoặc hạ tầng khi các nguồn dùng chung pipeline như thế nào?
Bạn sẽ thiết kế chính sách giữ log lỗi hiếm gặp ngay cả khi lưu lượng log tổng thể tăng đột biến ra sao?
Bạn sẽ kiểm tra biến thể log có dữ liệu nhạy cảm trong body và attributes để tránh chỉ lọc một vị trí như thế nào?
Bạn sẽ phân tích vì sao bỏ mọi log thành công có thể khiến không còn bằng chứng về thời gian phục hồi sau sự cố?
Bạn sẽ xác định cần giữ những mốc log nào để liên kết một request với trace ID sau khi đã lọc log nhiễu ra sao?
Bạn sẽ thử nghiệm lọc log khi một request phát sinh cả log DEBUG, INFO, WARN và ERROR như thế nào?
Bạn sẽ kiểm tra ảnh hưởng của việc loại bỏ log đến khả năng điều tra nguyên nhân exception không có trace đầy đủ ra sao?
Bạn sẽ mô tả cách lọc metrics ít giá trị vận hành mà không làm mất tín hiệu trong SLI và SLO như thế nào?
Bạn sẽ quyết định loại bỏ toàn bộ metric nào dựa trên mức sử dụng thực tế trong dashboard và alerting ra sao?
Bạn sẽ xác định các metric tự phát sinh từ runtime hoặc thư viện đang tạo khối lượng series dư thừa như thế nào?
Bạn sẽ phân biệt loại bỏ metric family với loại bỏ datapoint theo bộ labels khi đánh giá hiệu quả filtering ra sao?
Bạn sẽ đánh giá mức hỗ trợ của filter processor đối với điều kiện metric và datapoint theo phiên bản Collector như thế nào?
Bạn sẽ thiết kế quy tắc lọc datapoint có label môi trường thử nghiệm trước khi đẩy lên backend production ra sao?
Bạn sẽ xác định những rủi ro khi loại bỏ metrics theo job hoặc instance mà không xem xét mô hình autoscaling như thế nào?
Bạn sẽ phân tích ảnh hưởng của việc lọc metric status theo nhãn đến phép tính tỷ lệ lỗi của cả dịch vụ ra sao?
Bạn sẽ xác định những dashboard và alert rule nào đang phụ thuộc vào metric dự kiến bị loại bỏ bằng cách nào?
Bạn sẽ đánh giá khi nào loại bỏ một nhãn cardinality cao cần processor biến đổi nhãn thay vì loại bỏ cả metric ra sao?
Bạn sẽ thiết kế phép thử chứng minh giảm số time series sau filtering mà không làm mất dữ liệu các nhãn cần giữ như thế nào?
Bạn sẽ xác định tác động của filtering đến histogram buckets, count và sum khi các thành phần được xử lý không nhất quán như thế nào?
Bạn sẽ lựa chọn điều kiện lọc một loại histogram không dùng đến mà vẫn giữ các histogram phục vụ latency SLI ra sao?
Bạn sẽ phân tích ảnh hưởng của việc lọc các datapoint thiếu label so với quyết định giữ chúng để phát hiện lỗi instrumentation như thế nào?
Bạn sẽ phân biệt tối ưu cardinality bằng thay đổi instrumentation và giải pháp lọc tạm thời trong Collector ra sao?
Bạn sẽ đánh giá độ lệch của báo cáo sau khi một số series thuộc region hoặc tenant đã bị loại bỏ như thế nào?
Bạn sẽ thiết kế kiểm thử so sánh tổng request rate và error rate trước và sau filtering để phát hiện sai lệch ra sao?
Bạn sẽ mô tả những loại span thường tạo nhiều dữ liệu nhưng ít giá trị chẩn đoán trong hệ thống microservice như thế nào?
Bạn sẽ lựa chọn các tiêu chí nào để loại bỏ span nội bộ nhiễu mà vẫn giữ cấu trúc trace có ý nghĩa?
Bạn sẽ giải thích việc drop một span ảnh hưởng đến quan hệ parent-child của các span còn được giữ như thế nào?
Bạn sẽ phân tích tình huống giữ span con nhưng đã loại span cha khiến trace hiển thị không đầy đủ ra sao?
Bạn sẽ thiết kế chính sách bảo toàn error spans và các mốc quan trọng của request trước khi lọc các span khác như thế nào?
Bạn sẽ phân biệt drop span theo thuộc tính với tail sampling theo trạng thái toàn trace về mức độ giữ ngữ cảnh ra sao?
Bạn sẽ quyết định lọc span health check dựa trên route, kind và status mà không che khuất lỗi thật như thế nào?
Bạn sẽ đánh giá tác động của việc loại bỏ một loại database span đến khả năng tìm nút thắt latency ra sao?
Bạn sẽ phân biệt việc bỏ span với việc bỏ span event trong trường hợp event có thông tin lỗi quan trọng như thế nào?
Bạn sẽ xác định phiên bản filter processor có hỗ trợ lọc ở mức span event và những điều kiện áp dụng như thế nào?
Bạn sẽ thiết kế test kiểm tra số span và quan hệ parent-child trước và sau pipeline lọc như thế nào?
Bạn sẽ kiểm tra tình huống trace chỉ còn một vài span và dễ bị diễn giải nhầm là request hoàn thành nhanh như thế nào?
Bạn sẽ đánh giá việc lọc span attributes khác với lọc span toàn phần về chất lượng chẩn đoán và bảo vệ dữ liệu ra sao?
Bạn sẽ xử lý yêu cầu giảm số lượng span có lưu lượng cao mà không làm mất thông tin từ các trace lỗi như thế nào?
Bạn sẽ phân biệt head sampling tại ứng dụng, tail sampling trong collector và filtering theo từng record như thế nào?
Bạn sẽ thiết kế thứ tự filtering và sampling để giảm chi phí mà vẫn giữ dữ liệu cần cho quyết định lấy mẫu ra sao?
Bạn sẽ phân tích nguy cơ áp dụng filter trước tail sampling khiến bộ lấy mẫu không còn thấy thuộc tính hoặc span báo lỗi như thế nào?
Bạn sẽ xác định lúc nào cần giữ dấu vết lỗi hiếm gặp dù chính sách giảm khối lượng telemetry rất mạnh?
Bạn sẽ so sánh chi phí của lọc tại ứng dụng với lọc tại gateway Collector khi lưu lượng trace rất lớn ra sao?
Bạn sẽ đánh giá tác động của việc giữ hoặc bỏ trace context khi một span bị lọc khỏi hệ thống xuất telemetry như thế nào?
Bạn sẽ giải thích vì sao filter processor không phải là cơ chế thay thế hoàn toàn cho bảo vệ dữ liệu tại nguồn?
Bạn sẽ thiết kế chính sách phối hợp filtering, redaction và transform để không gửi giá trị nhạy cảm đến exporter như thế nào?
Bạn sẽ xác định những thuộc tính nên được biến đổi hoặc hash trước khi lưu trữ thay vì drop toàn bộ record ra sao?
Bạn sẽ phân tích rủi ro khi một processor thêm thông tin nhạy cảm sau khi bước filtering đã chạy như thế nào?
Bạn sẽ chọn nơi thực hiện sanitization khi pipeline có nhánh xuất dữ liệu nội bộ và nhánh tới SaaS observability ra sao?
Bạn sẽ mô tả cách đánh giá trust boundary tại mỗi bước nhận, xử lý, buffer và export dữ liệu telemetry như thế nào?
Bạn sẽ phát hiện trường hợp log exporter hoặc debug mode của Collector in dữ liệu nhạy cảm trước khi lọc bằng phép thử nào?
Bạn sẽ thiết kế cơ chế bảo vệ secret trong cấu hình và log chẩn đoán khi thử nghiệm OTTL như thế nào?
Bạn sẽ xác định chính sách nào phải fail closed khi một bước sanitization không còn hoạt động đúng như thế nào?
Bạn sẽ đánh giá sự đánh đổi giữa giữ khả dụng của telemetry pipeline và ngăn dữ liệu trái phép thoát ra khi processor bị lỗi ra sao?
Bạn sẽ xây dựng bộ dữ liệu thử nghiệm đại diện gồm log, metric và trace với cả record hợp lệ lẫn dữ liệu nhạy cảm như thế nào?
Bạn sẽ thiết kế bảng input và expected output để kiểm thử từng điều kiện lọc một cách có thể lặp lại ra sao?
Bạn sẽ xác minh một rule chỉ loại bỏ các bản ghi đúng đối tượng mà không làm mất dữ liệu ở service khác như thế nào?
Bạn sẽ kiểm thử các trường hợp thuộc tính thiếu, giá trị rỗng, sai kiểu và Unicode trong điều kiện OTTL ra sao?
Bạn sẽ tạo các trường hợp kiểm thử xung đột điều kiện để bảo đảm logic lọc có hành vi dễ dự đoán như thế nào?
Bạn sẽ kiểm tra việc các rule hoạt động đúng khi service thay đổi schema hoặc tên thuộc tính sau rollout ra sao?
Bạn sẽ xây dựng phép thử hồi quy khi nâng cấp OpenTelemetry Collector hoặc thay đổi cấu hình processor như thế nào?
Bạn sẽ lựa chọn cách xác minh record bị drop mà không phải gửi dữ liệu nhạy cảm thật sang backend kiểm thử ra sao?
Bạn sẽ tổ chức kiểm tra trước và sau filtering bằng dữ liệu tổng hợp hoặc trace giả lập để tránh làm lộ dữ liệu thật như thế nào?
Bạn sẽ định nghĩa tiêu chí chấp nhận về tỷ lệ dữ liệu bị loại, lỗi parsing và số record quan trọng bị mất như thế nào?
Bạn sẽ đo khối lượng dữ liệu theo bytes, số record và time series trước và sau chính sách lọc ra sao?
Bạn sẽ quy đổi mức giảm telemetry thành tiết kiệm ingest, storage và truy vấn mà không bỏ qua chi phí tính toán filtering như thế nào?
Bạn sẽ đánh giá khi nào số record giảm nhiều nhưng hóa đơn observability không giảm tương ứng ra sao?
Bạn sẽ phân biệt giảm cardinality metrics với giảm khối lượng log hoặc span khi đánh giá hiệu quả kinh tế như thế nào?
Bạn sẽ thiết kế chỉ số theo dõi tỷ lệ telemetry bị lọc theo loại tín hiệu, service và policy mà không tạo nhãn cardinality cao ra sao?
Bạn sẽ kiểm chứng việc metrics nội bộ của Collector phản ánh tăng giảm đầu vào và đầu ra theo kỳ vọng như thế nào?
Bạn sẽ thiết kế dashboard giám sát lỗi của filter processor, throughput và tài nguyên Collector ra sao?
Bạn sẽ xác định dấu hiệu cấu hình lọc quá mạnh khi lưu lượng đầu ra giảm bất thường sau deploy như thế nào?
Bạn sẽ phân biệt việc telemetry giảm do policy filtering với việc receiver, exporter hoặc ứng dụng ngừng gửi dữ liệu ra sao?
Bạn sẽ xây dựng cảnh báo khi một loại telemetry bắt buộc đột nhiên biến mất sau cập nhật rule như thế nào?
Bạn sẽ đánh giá tác động filtering lên độ trễ pipeline, backpressure và khả năng giữ dữ liệu trong giờ cao điểm ra sao?
Bạn sẽ xác định những giới hạn vận hành khi một điều kiện OTTL sử dụng regex tốn nhiều CPU trên log volume lớn như thế nào?
Bạn sẽ phân tích ảnh hưởng của filtering đến tỷ lệ truy tìm root cause trong các incident đã biết ra sao?
Bạn sẽ dùng replay những sự cố lịch sử để kiểm tra chính sách mới còn giữ đủ bằng chứng điều tra như thế nào?
Bạn sẽ đánh giá việc mất trace spans có làm thay đổi kết luận về dịch vụ chậm nhất trong một request như thế nào?
Bạn sẽ kiểm chứng rằng các metrics được dùng cho SLO và alerting không bị thay đổi định nghĩa sau filtering ra sao?
Bạn sẽ mô tả cách triển khai thử nghiệm rule filtering cho một nhóm workload trước khi mở rộng toàn hệ thống như thế nào?
Bạn sẽ lập kế hoạch canary cho Collector configuration và so sánh dữ liệu trước sau mà không xuất dữ liệu nhạy cảm sang nhánh không an toàn ra sao?
Bạn sẽ thiết kế cơ chế rollback nhanh khi rule mới khiến log lỗi hoặc metrics thiết yếu không còn xuất hiện như thế nào?
Bạn sẽ xác định cách lưu phiên bản policy, người phê duyệt và kết quả thử nghiệm để phục vụ kiểm toán ra sao?
Bạn sẽ tổ chức thay đổi giữa các môi trường để xác nhận rule OTTL hoạt động trên đúng phiên bản Collector như thế nào?
Bạn sẽ xác minh tất cả Collector replica đã nhận đúng cấu hình filtering sau rolling deployment bằng cách nào?
Bạn sẽ xử lý khi một nhánh pipeline áp dụng rule mới nhưng nhánh khác vẫn gửi dữ liệu chưa được làm sạch như thế nào?
Bạn sẽ xác định ai được quyền sửa chính sách filtering và ai có quyền phê duyệt ngoại lệ theo nguyên tắc phân tách nhiệm vụ ra sao?
Bạn sẽ thiết kế audit trail cho thay đổi filter, transform và exporter để truy vết nguồn gốc một lần lộ dữ liệu như thế nào?
Bạn sẽ lập quy trình phản ứng khi phát hiện quy tắc filtering đã không loại bỏ token bí mật trong một thời gian như thế nào?
Bạn sẽ phối hợp chặn phát sinh, thu hồi secret và xử lý bản sao telemetry đã xuất đi trong tình huống rò rỉ ra sao?
Bạn sẽ xác định những ràng buộc dữ liệu kiểm toán phải được giữ trước khi xóa telemetry nhạy cảm phát hiện sau sự cố như thế nào?
Bạn sẽ kiểm tra lại rule khi dịch vụ bổ sung một route hoặc một loại event mới khiến điều kiện cũ không còn chính xác như thế nào?
Bạn sẽ tổ chức rà soát định kỳ những quy tắc lọc không còn được sử dụng hoặc đang chặn dữ liệu quan trọng như thế nào?
Bạn sẽ thiết kế tiêu chí nghiệm thu cuối về tính đúng đắn của rule, bảo vệ dữ liệu, khả năng điều tra, SLO và chi phí trước khi bật filtering trên production như thế nào?
