# Phối hợp triển khai từng phần, canary hoặc cờ tính năng (feature flag) theo khả năng hệ thống

Phát hành một phiên bản mới không nhất thiết phải chuyển toàn bộ người dùng sang phiên bản đó cùng một thời điểm. Với hệ thống phù hợp, nhóm có thể triển khai theo từng phần, đưa một tỷ lệ nhỏ lưu lượng vào phiên bản mới, mở tính năng cho một nhóm người dùng hoặc bật dần hành vi qua feature flag. Những cách này giúp giới hạn phạm vi ảnh hưởng, quan sát phản ứng thực tế và dừng sớm khi có dấu hiệu bất thường.

Triển khai từng phần, canary và feature flag là các cơ chế có liên quan nhưng giải quyết những vấn đề khác nhau. Triển khai từng phần điều phối việc cập nhật tài nguyên hoặc instance. Canary giới hạn lưu lượng hoặc nhóm sử dụng phiên bản mới để đánh giá rủi ro. Feature flag điều khiển việc một chức năng có được thực thi hay không trong khi mã có thể đã được triển khai. Nhóm có thể kết hợp chúng, nhưng phải dựa trên khả năng định tuyến, kiến trúc, dữ liệu, khả năng quan sát và quy trình vận hành của hệ thống.

Mục tiêu của bài học là giúp nhóm chọn cách phát hành phù hợp, phối hợp các bên liên quan, đặt điều kiện tăng hoặc dừng rollout, xử lý lỗi và thu hồi thay đổi an toàn.

## 1. Phân biệt triển khai, phát hành và kích hoạt tính năng

Ba hoạt động thường diễn ra gần nhau nhưng không đồng nghĩa:

- **Triển khai (deployment):** đưa artifact, cấu hình hoặc hạ tầng mới vào môi trường chạy.
- **Phát hành (release):** làm cho phiên bản hoặc khả năng mới sẵn sàng được sử dụng theo chính sách sản phẩm.
- **Kích hoạt tính năng (feature enablement):** cho phép một nhóm người dùng hoặc luồng nghiệp vụ sử dụng hành vi mới.

Một phiên bản có thể được triển khai nhưng tính năng vẫn tắt qua feature flag. Một tính năng có thể được bật cho nhân viên nội bộ trước khi mở cho khách hàng. Một bản canary có thể nhận một phần traffic để kiểm tra phiên bản mới trong khi phần còn lại tiếp tục chạy phiên bản ổn định.

Tách các hoạt động này giúp nhóm kiểm soát rủi ro ở nhiều lớp. Nếu có lỗi trong artifact, có thể dừng rollout hoặc quay lại phiên bản trước. Nếu mã mới ổn định nhưng chức năng gây vấn đề cho một nhóm người dùng, có thể tắt flag nếu thiết kế hỗ trợ. Nếu lỗi nằm ở schema dữ liệu đã được mở rộng, rollback ứng dụng đơn thuần có thể không đủ.

## 2. Các chiến lược triển khai từng phần

Có nhiều cách phân phối phiên bản mới. Việc lựa chọn phụ thuộc vào khả năng chạy song song nhiều phiên bản, định tuyến traffic, quản lý trạng thái và chi phí hạ tầng.

| Chiến lược | Cách hoạt động | Phù hợp khi | Điểm cần chú ý |
|---|---|---|---|
| Rolling deployment | Thay instance cũ bằng instance mới theo từng nhóm | Có nhiều replica và hệ thống hỗ trợ nhiều instance cùng phục vụ | Phiên bản cũ và mới phải tương thích trong thời gian chuyển tiếp |
| Blue-green deployment | Duy trì hai môi trường, chuyển traffic từ môi trường cũ sang môi trường mới | Có thể tạo môi trường song song và chuyển routing nhanh | Chi phí tài nguyên, trạng thái dùng chung và migration dữ liệu |
| Canary deployment | Chuyển một phần traffic hoặc người dùng sang phiên bản mới, tăng dần khi đạt điều kiện | Có thể phân tuyến và quan sát theo phiên bản hoặc cohort | Cần đủ traffic, telemetry và khả năng dừng/đảo routing |
| Ring deployment | Mở lần lượt theo vòng nhóm được xác định trước | Có các nhóm nội bộ, khách hàng thử nghiệm hoặc khu vực khác nhau | Phải kiểm soát tiêu chí vào/ra từng vòng |
| Phased rollout | Mở rộng theo đợt hoặc tỷ lệ đã lập kế hoạch | Hệ thống phân phối theo khu vực, tenant hoặc nền tảng | Cần theo dõi khác biệt giữa các đợt |
| Dark launch | Triển khai mã và có thể xử lý nền nhưng chưa hiển thị chức năng cho người dùng | Cần kiểm tra tải, dữ liệu hoặc tích hợp trước khi mở UI | Phải ngăn side effect không mong muốn và bảo vệ dữ liệu |

Rolling và blue-green chủ yếu điều phối phiên bản chạy. Canary và ring nhấn mạnh cách giới hạn đối tượng hoặc traffic nhận phiên bản. Dark launch đưa khả năng vào môi trường trước khi công khai trải nghiệm. Các chiến lược có thể phối hợp tùy kiến trúc.

## 3. Hiểu vai trò của canary release

Canary release là cách đưa phiên bản mới đến một phạm vi nhỏ được kiểm soát trước khi mở rộng. Phạm vi có thể là một tỷ lệ traffic, một nhóm tenant, một khu vực, một cụm thiết bị hoặc người dùng nội bộ.

Một quy trình canary thường gồm:

1. Triển khai phiên bản mới vào một nhóm instance hoặc đích routing riêng.
2. Xác minh health, readiness và smoke test.
3. Chuyển một lượng traffic hoặc nhóm người dùng giới hạn.
4. So sánh chỉ số của canary với phiên bản ổn định hoặc baseline.
5. Giữ, tăng, giảm hoặc dừng rollout theo điều kiện đã định.
6. Khi đủ bằng chứng, mở rộng đến các nhóm tiếp theo.
7. Theo dõi sau khi hoàn tất và lưu kết quả.

Canary chỉ có ý nghĩa nếu nhóm có thể nhận diện traffic và kết quả của phiên bản mới. Nếu telemetry trộn toàn bộ phiên bản, một lỗi chỉ xuất hiện ở canary có thể bị che bởi số liệu tổng. Nếu lưu lượng quá thấp, tỷ lệ lỗi và phân vị latency có thể không đủ mẫu để kết luận. Khi đó cần tăng thời gian quan sát, dùng kiểm thử tổng hợp hoặc chọn một cohort có đặc điểm đại diện.

Không nên chọn tỷ lệ canary cố định cho mọi hệ thống. Bắt đầu ở phạm vi đủ nhỏ để giới hạn tác động nhưng đủ lớn để thu thập tín hiệu hữu ích; tỷ lệ cụ thể cần dựa trên traffic, mức rủi ro, năng lực xử lý và khả năng rollback.

## 4. Hiểu feature flag và các loại cờ

Feature flag là cấu hình điều khiển hành vi ứng dụng tại runtime. Mã của tính năng có thể đã nằm trong artifact nhưng chỉ được thực thi khi điều kiện flag cho phép.

Một số loại cờ phổ biến:

- **Release flag:** bật hoặc tắt tính năng trong quá trình phát hành.
- **Experiment flag:** phân nhóm người dùng để thử nghiệm trải nghiệm hoặc giả thuyết sản phẩm.
- **Operational flag:** tắt một chức năng tốn tài nguyên hoặc phụ thuộc đang gặp sự cố.
- **Permission flag:** giới hạn tính năng theo vai trò, tenant hoặc gói dịch vụ; cần phối hợp với kiểm soát phân quyền thực sự.
- **Kill switch:** cơ chế tắt nhanh một hành vi có nguy cơ gây ảnh hưởng lớn.

Feature flag có thể điều khiển theo user ID, tenant, khu vực, thiết bị, phiên bản ứng dụng hoặc tỷ lệ phân phối. Điều kiện phải xác định ổn định để một người dùng không liên tục chuyển giữa hai hành vi trong cùng một luồng. Với giao dịch nhiều bước, có thể cần gắn quyết định flag vào session hoặc transaction context.

Feature flag không thay thế authorization. Việc ẩn nút giao diện bằng flag không bảo vệ API nếu backend không kiểm tra quyền. Mọi hành động nhạy cảm vẫn phải được xác thực và phân quyền tại điểm thực thi.

## 5. Phân biệt canary với feature flag và khi nào kết hợp

Canary và feature flag thường bị xem là cùng một kỹ thuật nhưng chúng kiểm soát hai lớp khác nhau.

| Tiêu chí | Canary deployment | Feature flag |
|---|---|---|
| Đối tượng điều khiển | Phiên bản, instance, traffic hoặc cohort | Hành vi/chức năng trong ứng dụng |
| Thời điểm tác động | Trong quá trình triển khai và chuyển traffic | Khi ứng dụng đánh giá điều kiện flag |
| Yêu cầu chính | Routing, phân biệt phiên bản và telemetry | Flag evaluation, cấu hình, cache và quyền |
| Cách dừng | Đưa traffic khỏi phiên bản mới hoặc dừng rollout | Tắt flag hoặc thu hẹp đối tượng được bật |
| Giới hạn | Không nhất thiết cô lập một tính năng trong artifact | Không tự thay thế phiên bản mã hoặc khôi phục schema |

Có thể kết hợp: triển khai artifact mới theo canary, nhưng để feature flag tắt; xác minh health và tương thích; sau đó bật tính năng cho nhóm canary; quan sát hành vi; rồi mở rộng. Cách này tách rủi ro của artifact khỏi rủi ro của chức năng.

Kết hợp cũng có thể làm tăng độ phức tạp. Nếu có nhiều phiên bản và nhiều flag tương tác, số tổ hợp cần kiểm tra tăng nhanh. Cần giới hạn số flag đang hoạt động, ghi lại ma trận cấu hình quan trọng và xác định các tổ hợp được hỗ trợ.

## 6. Đánh giá khả năng hệ thống trước khi chọn chiến lược

Không phải hệ thống nào cũng hỗ trợ rollout từng phần. Trước khi quyết định, đánh giá các khả năng sau:

| Khả năng | Câu hỏi cần trả lời | Nếu chưa có |
|---|---|---|
| Định tuyến traffic | Có thể phân luồng theo phiên bản, tenant, khu vực hoặc header không? | Dùng ring/đợt triển khai ở cấp có thể kiểm soát hoặc bổ sung routing |
| Chạy nhiều phiên bản | API, schema và giao thức có tương thích khi cũ/mới cùng chạy không? | Dùng cửa sổ bảo trì hoặc triển khai đồng bộ có kiểm soát |
| Quan sát theo phiên bản | Log, metric và trace có gắn version, cohort và flag không? | Bổ sung telemetry trước rollout có rủi ro |
| Quản lý flag | Có dịch vụ/config đáng tin, cache và fallback rõ không? | Dùng cơ chế cấu hình đơn giản, kiểm soát quyền và kiểm thử |
| Quản lý trạng thái | Session, cache, queue và dữ liệu có dùng chung an toàn không? | Xác định ranh giới và khả năng tương thích trước khi chia traffic |
| Rollback/roll-forward | Có thể đưa traffic về bản cũ hoặc triển khai bản sửa không? | Chuẩn bị phương án phục hồi và kiểm tra trước |
| Migration dữ liệu | Phiên bản cũ có hoạt động với schema mới trong giai đoạn chuyển tiếp không? | Dùng expand-contract hoặc chia giai đoạn migration |
| Điều phối thiết bị/client | Client cũ có tiếp tục hoạt động khi backend đổi không? | Duy trì tương thích API và kế hoạch cập nhật client |

Nếu một khả năng quan trọng chưa có, nhóm cần thay đổi chiến lược hoặc đầu tư bổ sung trước. Không nên chọn canary chỉ vì nền tảng có nút chia traffic nếu hệ thống không thể phân biệt lỗi của phiên bản mới hoặc không thể quay lại trạng thái an toàn.

## 7. Thiết kế tương thích giữa các phiên bản

Trong rollout từng phần, phiên bản cũ và mới thường cùng tồn tại một thời gian. Các thành phần cần tương thích trong giai đoạn chuyển tiếp.

Hãy kiểm tra:

- API request/response có giữ tương thích ngược không?
- Database schema có cho cả phiên bản cũ và mới đọc/ghi không?
- Event và message có schema version hoặc quy tắc xử lý trường mới không?
- Cache key và cấu trúc cache có xung đột không?
- Session có thể được đọc bởi cả phiên bản không?
- Background worker cũ và mới có thể cùng xử lý queue không?
- Mobile/web client cũ có gọi backend mới an toàn không?
- Cấu hình và secret có tồn tại cho mọi phiên bản đang chạy không?

Một quy trình migration an toàn thường dùng **expand-contract**:

1. Mở rộng schema theo cách tương thích, ví dụ thêm trường nullable hoặc bảng mới.
2. Triển khai ứng dụng có thể đọc cả định dạng cũ và mới.
3. Chuyển dần việc ghi sang định dạng mới hoặc đồng bộ dữ liệu.
4. Xác minh tất cả consumer đã chuyển đổi.
5. Chỉ sau khi không còn phiên bản cũ phụ thuộc, mới loại bỏ cấu trúc cũ.

Không nên xóa hoặc đổi tên cột ngay trong cùng lần rollout nếu phiên bản cũ vẫn đang chạy. Rollback ứng dụng không thể tự khôi phục dữ liệu đã bị migration phá hủy.

## 8. Lập kế hoạch rollout và xác định các giai đoạn

Một kế hoạch rollout cần mô tả các giai đoạn, phạm vi, tiêu chí đi tiếp và người quyết định.

Ví dụ các vòng:

- **Vòng 0 – Nội bộ:** nhóm phát triển, QA và người dùng nội bộ được chọn.
- **Vòng 1 – Canary:** tỷ lệ traffic hoặc tenant giới hạn.
- **Vòng 2 – Mở rộng có kiểm soát:** tăng cohort theo khu vực hoặc nhóm khách hàng.
- **Vòng 3 – Phổ biến rộng:** mở cho phần lớn đối tượng đủ điều kiện.
- **Vòng 4 – Hoàn tất:** xác nhận rollout, chuyển sang giám sát thông thường và lập lịch dọn flag tạm.

Đây là ví dụ cấu trúc, không phải số vòng hoặc tỷ lệ bắt buộc. Mỗi hệ thống có thể dùng ít hoặc nhiều giai đoạn hơn. Kế hoạch cần ghi:

- Artifact, commit, cấu hình và flag liên quan.
- Đối tượng hoặc tỷ lệ nhận phiên bản ở mỗi vòng.
- Thời lượng hoặc lượng traffic cần quan sát.
- Chỉ số và ngưỡng tiếp tục, tạm dừng hoặc rollback.
- Smoke test và kiểm tra nghiệp vụ cần thực hiện.
- Người điều phối và người có quyền quyết định.
- Cửa sổ phát hành, phụ thuộc và kênh liên lạc.
- Phương án phục hồi và điều kiện hoàn tất.

## 9. Đặt tiêu chí tăng, giữ, dừng và rollback

Rollout cần có quyết định dựa trên bằng chứng, không chỉ dựa vào cảm giác “có vẻ ổn”.

| Quyết định | Điều kiện điển hình | Hành động |
|---|---|---|
| Tăng phạm vi | Health ổn định, SLI trong ngưỡng, không có lỗi nghiêm trọng và test quan trọng đạt | Mở rộng sang cohort tiếp theo |
| Giữ nguyên | Chưa đủ mẫu, chỉ số biến động hoặc đang chờ phụ thuộc | Duy trì phạm vi và thu thập thêm bằng chứng |
| Tạm dừng | Có dấu hiệu suy giảm nhưng chưa đủ căn cứ rollback | Không tăng traffic, điều tra nguyên nhân |
| Rollback/disable | Vượt ngưỡng dừng, lỗi nghiêm trọng hoặc có nguy cơ dữ liệu/bảo mật | Đưa traffic về bản ổn định hoặc tắt flag theo runbook |
| Tiếp tục có điều kiện | Có rủi ro đã đánh giá và ngoại lệ được phê duyệt | Giới hạn phạm vi, tăng giám sát và ghi thời hạn |

Các ngưỡng cần gắn với luồng nghiệp vụ. Theo dõi latency, tỷ lệ lỗi, timeout, throughput, queue lag, lỗi thanh toán, giao dịch trùng, crash, tài nguyên và chỉ số bảo mật tùy hệ thống. Không chỉ xem dashboard tổng; cần so sánh canary với control hoặc baseline cùng thời điểm nếu có thể.

Một chỉ số đơn lẻ có thể gây kết luận sai. Ví dụ tỷ lệ lỗi thấp nhưng chỉ có vài request; hoặc latency tổng tốt trong khi một khu vực canary đang suy giảm. Đặt yêu cầu về số mẫu, cửa sổ quan sát và phân nhóm trước khi rollout.

## 10. Thiết kế telemetry để so sánh canary và phiên bản ổn định

Canary chỉ hữu ích nếu có thể phân biệt hành vi của từng nhóm. Telemetry nên ghi nhận:

- Application version, build ID hoặc image digest.
- Deployment ring, region, tenant hoặc cohort.
- Feature flag key và trạng thái đã đánh giá (không ghi dữ liệu nhạy cảm).
- Request ID, trace ID và service dependency.
- Latency, error rate, throughput và saturation.
- Business outcome như giao dịch hoàn tất, hủy, hoàn tiền hoặc xử lý trùng.
- Crash, exception, queue lag và retry.
- Thời điểm bắt đầu/kết thúc từng vòng rollout.

Cần bảo đảm nhãn telemetry có cardinality phù hợp. Không gắn user ID duy nhất làm label metric nếu điều đó tạo số lượng chuỗi quá lớn hoặc vi phạm quyền riêng tư. Có thể dùng cohort hoặc dimension được kiểm soát; thông tin chi tiết truy vết nên nằm trong log/trace có quyền truy cập phù hợp.

Khi so sánh, kiểm tra hai nhóm có workload và điều kiện tương đương không. Nếu canary chỉ nhận request nhẹ hoặc người dùng nội bộ, số liệu có thể không đại diện cho toàn bộ khách hàng. Có thể bổ sung synthetic test, replay dữ liệu đã được bảo vệ hoặc mở rộng cohort theo từng bước.

## 11. Kiểm thử feature flag và các tổ hợp cấu hình

Feature flag tạo thêm trạng thái có thể ảnh hưởng hành vi. Nhóm cần kiểm tra cả đường bật, đường tắt và chuyển trạng thái.

Các kịch bản nên xem xét:

- Flag tắt: hành vi cũ vẫn hoạt động đúng.
- Flag bật: chức năng mới hoạt động đúng.
- Flag thay đổi khi ứng dụng đang chạy: cấu hình được cập nhật theo chính sách.
- Flag service không truy cập được: fallback có xác định và an toàn.
- Cache flag cũ: thời gian hiệu lực và invalidation đúng.
- Người dùng hoặc tenant không đủ điều kiện: không được kích hoạt.
- Nhiều flag tương tác: tổ hợp được hỗ trợ không tạo hành vi sai.
- Kill switch: có thể tắt trong thời gian phù hợp và không làm mất dữ liệu.
- Flag ở backend và frontend: quyết định nhất quán, backend vẫn bảo vệ quyền.
- Rollback phiên bản: flag và schema vẫn tương thích với mã cũ.

Không cần kiểm thử mọi tổ hợp nếu số flag lớn. Ưu tiên tổ hợp ảnh hưởng luồng quan trọng, quyền truy cập, dữ liệu và các cờ phụ thuộc nhau. Duy trì danh sách tổ hợp được hỗ trợ và loại bỏ flag hết hạn để tránh bùng nổ trạng thái.

## 12. Quản lý vòng đời feature flag

Flag tạm thời nếu tồn tại lâu sẽ trở thành nợ kỹ thuật và làm mã khó hiểu.

Mỗi flag nên có metadata:

- Tên và mô tả mục đích.
- Loại flag: release, experiment, operational hoặc loại khác.
- Chủ sở hữu kỹ thuật và chủ sở hữu sản phẩm.
- Giá trị mặc định và hành vi fallback.
- Đối tượng được bật và quy tắc phân nhóm.
- Ngày tạo, ngày xem xét và điều kiện loại bỏ.
- Quan hệ phụ thuộc với flag khác.
- Hành động khi flag service không sẵn sàng.

Sau khi rollout hoàn tất, nhóm cần quyết định giữ flag như một cấu hình vận hành lâu dài hay loại bỏ nó. Với release flag tạm thời, tạo công việc dọn mã và kiểm thử trạng thái cuối. Với operational flag hoặc kill switch cần giữ lâu dài, tài liệu hóa người được phép thay đổi và cách diễn tập.

Không để flag mặc định bật trong production mà không có quyết định rõ. Kiểm tra trạng thái mặc định trong mọi môi trường và bảo đảm cấu hình không bị thay đổi bởi người không có quyền.

## 13. Phối hợp vai trò và truyền thông trong rollout

Rollout liên quan đến nhiều nhóm. Cần xác định ai điều phối, ai quan sát, ai có quyền tăng phạm vi và ai quyết định rollback.

Một phân công điển hình:

| Vai trò | Nhiệm vụ trong rollout |
|---|---|
| Release manager / rollout lead | Điều phối lịch, trạng thái, quyết định theo kế hoạch và thông tin liên lạc |
| Product owner | Xác nhận cohort, trải nghiệm, mức chấp nhận và ưu tiên nghiệp vụ |
| Development / service owner | Chịu trách nhiệm artifact, tính tương thích và xử lý lỗi mã |
| QA lead / test engineer | Xác minh gate, smoke test, kết quả theo cohort và bằng chứng |
| Platform / DevOps | Điều phối deploy, routing, cấu hình, capacity và rollback kỹ thuật |
| SRE / Operations | Theo dõi health, SLI/SLO, cảnh báo, runbook và phục hồi |
| Security | Đánh giá rủi ro, quyền, secret và phát hiện bảo mật |
| Support / Customer success | Theo dõi phản hồi khách hàng và chuyển thông tin tác động |
| Risk owner / approver | Chấp nhận ngoại lệ hoặc quyết định trong phạm vi thẩm quyền |

Trước rollout, công bố thời gian, phạm vi, kênh theo dõi, người trực và điều kiện dừng. Trong rollout, cập nhật mỗi lần tăng hoặc thay đổi trạng thái. Sau rollout, gửi kết quả, rủi ro còn lại và hành động tiếp theo.

Không nên để quyết định rollback phụ thuộc vào một người không có mặt trong cửa sổ phát hành. Cần chỉ định người thay thế và quyền dừng khẩn cấp theo chính sách.

## 14. Xử lý rollback, roll-forward và dữ liệu đã thay đổi

Rollback là đưa hệ thống về phiên bản hoặc trạng thái trước đó. Roll-forward là triển khai bản sửa mới để xử lý vấn đề. Chọn cách nào phụ thuộc vào loại lỗi và khả năng tương thích dữ liệu.

Rollback phù hợp khi:
- Phiên bản mới gây suy giảm và bản trước vẫn tương thích với trạng thái dữ liệu.
- Routing có thể chuyển traffic về bản cũ.
- Feature flag có thể tắt hành vi mới mà không làm mất dữ liệu.
- Các side effect đã phát sinh có thể được xử lý hoặc đối soát.

Roll-forward có thể phù hợp khi:
- Schema đã thay đổi theo cách không thể đảo ngược an toàn.
- Dữ liệu mới đã được tạo và bản cũ không thể xử lý.
- Bản sửa nhỏ có thể triển khai nhanh hơn rollback.
- Cần giữ tương thích với client hoặc message đã phát hành.

Trước rollout, ghi rõ:
- Điều kiện kích hoạt rollback hoặc roll-forward.
- Artifact và cấu hình đích.
- Migration nào có thể đảo ngược và migration nào không.
- Cách xử lý queue, event, cache và session.
- Cách đối soát hoặc sửa dữ liệu đã phát sinh.
- Người quyết định và người thực hiện.
- Cách xác minh sau phục hồi.

Rollback ứng dụng không tự động đảo ngược side effect như email đã gửi, giao dịch đã tạo hoặc message đã tiêu thụ. Với luồng nghiệp vụ quan trọng, cần thiết kế idempotency, compensating action và reconciliation.

## 15. Các giới hạn với hệ thống stateful, client lâu dài và thiết bị biên

Một số hệ thống khó rollout từng phần hơn vì trạng thái hoặc client tồn tại lâu.

- **Database và stateful service:** cần tương thích schema, backup, replication và kế hoạch migration.
- **Queue và worker:** phiên bản consumer cũ/mới có thể xử lý message khác nhau; cần schema version và quy tắc tương thích.
- **WebSocket hoặc session dài:** người dùng có thể tiếp tục kết nối tới phiên bản cũ sau khi routing thay đổi.
- **Mobile app:** không thể buộc mọi thiết bị cập nhật ngay; backend phải hỗ trợ client cũ trong khoảng thời gian xác định.
- **IoT/edge:** thiết bị có thể mất kết nối, cập nhật theo đợt và cần cơ chế phục hồi khi update thất bại.
- **Hệ thống đơn instance:** không có replica để chia traffic; cần cửa sổ bảo trì, standby hoặc phương án blue-green nếu đủ tài nguyên.
- **Batch và tác vụ dài:** job bắt đầu trên phiên bản cũ có thể kết thúc sau khi phiên bản mới đã triển khai.

Nếu không có routing hoặc khả năng chạy song song, feature flag có thể giúp điều khiển hành vi sau khi triển khai, nhưng không giải quyết được mọi vấn đề tương thích artifact. Hãy chọn cơ chế phù hợp với giới hạn thật của hệ thống và công bố rõ phần nào không thể rollout dần.

## 16. Ví dụ: canary kết hợp feature flag cho API đặt hàng

Một dịch vụ đặt hàng bổ sung quy trình tính phí vận chuyển mới. Hệ thống có nhiều instance, gateway hỗ trợ routing theo tenant và telemetry gắn version. Nhóm quyết định triển khai artifact theo canary và dùng feature flag để điều khiển logic mới.

Kế hoạch:

1. Mở rộng schema theo hướng tương thích với phiên bản hiện tại.
2. Triển khai artifact mới lên nhóm instance canary, flag vẫn tắt.
3. Chạy health check, smoke test và xác minh instance cũ/mới cùng đọc ghi dữ liệu đúng.
4. Chuyển một cohort tenant thử nghiệm vào canary.
5. Bật flag tính phí mới cho cohort đó.
6. So sánh tỷ lệ tạo đơn thành công, sai lệch phí, latency, timeout và lỗi theo version/cohort.
7. Nếu đạt điều kiện và đủ mẫu, mở flag hoặc traffic sang nhóm tiếp theo.
8. Nếu vượt ngưỡng, tắt flag trước nếu lỗi chỉ thuộc logic mới; chuyển traffic khỏi canary nếu lỗi liên quan artifact hoặc hạ tầng.
9. Khi rollout hoàn tất, xác minh toàn bộ cohort, dọn release flag tạm và lên lịch loại bỏ cấu trúc cũ khi không còn phiên bản phụ thuộc.

Ma trận quyết định minh họa:

| Tín hiệu | Phạm vi lỗi | Hành động ban đầu |
|---|---|---|
| Phí vận chuyển sai chỉ khi flag bật | Logic tính phí mới | Tắt flag, giữ artifact để điều tra |
| Lỗi 5xx tăng trên mọi request canary, kể cả flag tắt | Artifact hoặc hạ tầng | Dừng tăng traffic, chuyển routing về bản ổn định |
| Queue lag tăng khi worker mới nhận message | Tương thích consumer hoặc tải | Tạm dừng rollout worker, kiểm tra schema và năng lực |
| Latency chỉ tăng ở một vùng | Routing hoặc phụ thuộc vùng | Giữ cohort vùng đó, điều tra theo region |
| Không đủ request để đánh giá | Thiếu mẫu | Giữ phạm vi, kéo dài quan sát hoặc dùng kiểm tra bổ sung |

Các quyết định cần dựa trên ngưỡng đã thống nhất, không áp dụng máy móc bảng minh họa. Với giao dịch đã được tạo bằng logic mới, tắt flag không tự sửa các giao dịch đó; cần đối soát và xử lý theo quy tắc nghiệp vụ.

## 17. Quy trình phối hợp triển khai theo từng phần

Có thể dùng quy trình sau cho một đợt phát hành:

1. **Đánh giá khả năng hệ thống:** xác nhận routing, chạy song song, telemetry, flag, migration và rollback.
2. **Chọn chiến lược:** rolling, blue-green, canary, ring, phased rollout hoặc kết hợp.
3. **Xác định phạm vi:** chọn cohort, tỷ lệ, khu vực, tenant và thời gian mỗi vòng.
4. **Chuẩn bị tương thích:** kiểm tra API, schema, event, cache, session và client cũ.
5. **Thiết kế test và gate:** smoke, contract, regression, security và SLI cần theo dõi.
6. **Phân công và truyền thông:** chỉ định rollout lead, người quan sát, người quyết định và người thay thế.
7. **Chuẩn bị phục hồi:** artifact trước, routing, flag, migration và quy trình đối soát.
8. **Triển khai vòng đầu:** xác minh health và chức năng trong phạm vi giới hạn.
9. **Đánh giá bằng chứng:** so sánh với control/baseline và quyết định tăng, giữ, dừng hoặc rollback.
10. **Mở rộng và theo dõi:** lặp lại từng vòng cho đến khi hoàn tất.
11. **Đóng rollout:** xác nhận trạng thái cuối, dọn flag tạm, ghi nhận ngoại lệ và bài học.

~~~mermaid
flowchart TD
    A["Đánh giá khả năng hệ thống"] --> B["Chọn rolling, canary, ring hoặc feature flag"]
    B --> C["Xác minh tương thích và phương án phục hồi"]
    C --> D["Triển khai vào phạm vi nhỏ"]
    D --> E["Smoke test và quan sát telemetry"]
    E --> F{"Đạt ngưỡng và đủ bằng chứng?"}
    F -->|Có| G["Tăng cohort hoặc traffic"]
    G --> H{"Đã hoàn tất rollout?"}
    H -->|Chưa| E
    H -->|Rồi| I["Xác nhận release và dọn flag tạm"]
    F -->|Chưa rõ| J["Giữ phạm vi và thu thập thêm dữ liệu"]
    J --> E
    F -->|Không| K["Dừng rollout, tắt flag hoặc rollback"]
    K --> L["Đối soát dữ liệu và xác minh phục hồi"]
    L --> M["Điều tra nguyên nhân và lập kế hoạch tiếp tục"]
~~~

## 18. Checklist trước, trong và sau rollout

**Trước rollout**

- Chiến lược được chọn có phù hợp với routing, replica và trạng thái hệ thống không?
- Phiên bản cũ và mới có tương thích trong giai đoạn chuyển tiếp không?
- Migration, event, queue, cache và session có kế hoạch rõ không?
- Cohort hoặc tỷ lệ traffic được xác định và có thể nhận diện không?
- Telemetry phân biệt được version, region, tenant và trạng thái flag không?
- Ngưỡng tăng, giữ, dừng và rollback đã được thống nhất chưa?
- Smoke test, regression và kiểm tra bảo mật có người sở hữu không?
- Người điều phối, người quyết định, người trực và kênh liên lạc đã rõ chưa?
- Artifact trước, routing, flag và phương án đối soát đã sẵn sàng chưa?

**Trong rollout**

- Health và readiness có đạt ở từng vòng không?
- Traffic thực tế có đúng cohort dự kiến không?
- SLI và kết quả nghiệp vụ có được so sánh với baseline/control không?
- Có đủ mẫu và thời gian quan sát để ra quyết định không?
- Có lỗi mới, cảnh báo bảo mật hoặc suy giảm theo vùng/tenant không?
- Mỗi quyết định tăng, giữ, dừng hoặc rollback có người xác nhận và ghi lại không?
- Thay đổi flag có được kiểm tra quyền và ghi audit không?

**Sau rollout**

- Tất cả cohort có ở trạng thái phiên bản dự kiến không?
- Các giao dịch và tác vụ đang chạy có hoàn tất đúng không?
- Có lỗi hoặc dữ liệu cần đối soát sau khi bật tính năng không?
- Feature flag tạm có chủ sở hữu và kế hoạch loại bỏ không?
- Schema cũ chỉ được loại bỏ khi không còn consumer phụ thuộc?
- Runbook, dashboard và tài liệu vận hành đã cập nhật chưa?
- Kết quả, ngoại lệ và bài học đã được lưu chưa?

Phối hợp triển khai từng phần, canary hoặc feature flag giúp giảm phạm vi rủi ro và cho phép nhóm học từ tín hiệu thực tế trước khi mở rộng. Hiệu quả phụ thuộc vào khả năng tương thích giữa phiên bản, định tuyến và quan sát theo cohort, quản lý trạng thái và dữ liệu, quyền quyết định rõ ràng cùng phương án phục hồi đã được kiểm tra. Khi chiến lược được chọn theo năng lực thật của hệ thống và mỗi bước rollout có tiêu chí bằng chứng cụ thể, nhóm có thể phát hành có kiểm soát mà vẫn giữ được chất lượng và tính liên tục của dịch vụ.

