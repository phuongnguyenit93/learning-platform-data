# Xác định sự kiện cần xem xét lại chiến lược

Chiến lược kiểm thử xác định cách tổ chức kiểm thử để kiểm soát rủi ro chất lượng trong một sản phẩm hoặc hệ thống. Chiến lược thường mô tả mục tiêu, phạm vi, cấp độ kiểm thử, loại kiểm thử, cách tự động hóa, môi trường và dữ liệu, trách nhiệm, tiêu chí hoàn thành và cách đánh giá bằng chứng. Những lựa chọn này được xây dựng dựa trên bối cảnh tại một thời điểm; khi sản phẩm, kiến trúc, rủi ro hoặc cách vận hành thay đổi đáng kể, chiến lược ban đầu có thể không còn phù hợp.

Xem xét lại chiến lược là hoạt động đánh giá có chủ đích để xác định liệu cách kiểm thử hiện tại còn kiểm soát đúng rủi ro và hỗ trợ mục tiêu sản phẩm hay không. Không phải mọi thay đổi nhỏ đều cần viết lại chiến lược. Một thay đổi giao diện cục bộ có thể chỉ cần cập nhật test case; việc chuyển sang kiến trúc dịch vụ mới, thêm loại dữ liệu nhạy cảm hoặc liên tục gặp sự cố production có thể yêu cầu xem xét ở cấp chiến lược.

Bài học này giúp nhận diện những sự kiện nên kích hoạt việc xem xét, đánh giá mức độ tác động, quyết định phạm vi rà soát và cập nhật chiến lược dựa trên bằng chứng.

## 1. Phân biệt xem xét chiến lược với cập nhật kiểm thử thường xuyên

Cần xác định đúng cấp độ thay đổi để tránh hai thái cực: bỏ qua thay đổi quan trọng hoặc biến mọi điều chỉnh nhỏ thành một lần lập chiến lược mới.

- **Cập nhật test case:** thay đổi bước kiểm thử, dữ liệu hoặc expected result cho một yêu cầu cụ thể.
- **Điều chỉnh test suite:** thêm, sửa, loại bỏ hoặc phân nhóm test trong một phạm vi chức năng.
- **Điều chỉnh kế hoạch kiểm thử:** thay đổi lịch, nguồn lực, môi trường, phạm vi của một đợt hoặc một release.
- **Xem xét chiến lược kiểm thử:** đánh giá lại các lựa chọn nền tảng như rủi ro được ưu tiên, cấp độ kiểm thử, mức tự động hóa, cách kiểm tra phi chức năng, mô hình môi trường, dữ liệu, trách nhiệm và tiêu chí ra quyết định.

Ví dụ, đổi nhãn một trường trên giao diện thường chỉ cần cập nhật test case. Nếu sản phẩm chuyển từ xử lý đồng bộ sang event-driven, cách xác minh trạng thái cuối, retry, idempotency, quan sát và kiểm thử tích hợp có thể phải thay đổi ở cấp chiến lược.

Một sự kiện có thể dẫn đến nhiều mức xử lý. Nhóm nên bắt đầu bằng đánh giá tác động; chỉ mở review chiến lược đầy đủ khi bằng chứng cho thấy giả định nền tảng đã thay đổi hoặc cách kiểm thử hiện tại không còn kiểm soát rủi ro.

## 2. Các nhóm sự kiện có thể kích hoạt review

Sự kiện kích hoạt (review trigger) là thay đổi, xu hướng hoặc phát hiện có khả năng làm mất hiệu lực một phần quan trọng của chiến lược hiện tại. Có thể nhóm chúng thành các loại sau:

| Nhóm sự kiện | Ví dụ | Phần chiến lược có thể bị ảnh hưởng |
|---|---|---|
| Sản phẩm và nghiệp vụ | Thêm luồng thanh toán, thay đổi mô hình giá, mở thị trường mới | Phạm vi, ưu tiên rủi ro, tiêu chí chấp nhận |
| Yêu cầu và quy định | Nghĩa vụ pháp lý mới, yêu cầu lưu trữ hoặc kiểm toán | Bảo mật, quyền riêng tư, bằng chứng và phê duyệt |
| Kiến trúc và công nghệ | Tách monolith, thêm queue, thay database hoặc cloud | Cấp độ kiểm thử, tích hợp, môi trường và dữ liệu |
| Sự cố và chất lượng | Lỗi nghiêm trọng production, lỗi lặp lại, nhiều defect lọt qua | Mô hình rủi ro, regression, kiểm thử phi chức năng |
| Hiệu năng và quy mô | Tăng tải, dữ liệu lớn, số tenant hoặc khu vực tăng | Workload, capacity, performance và reliability test |
| Bảo mật và dữ liệu | Có loại dữ liệu nhạy cảm mới, threat model thay đổi | Security test, phân quyền, masking và test data |
| Phát hành và vận hành | Chuyển sang canary, release thường xuyên hơn, yêu cầu rollback nhanh | CI/CD gates, smoke test, rollout và monitoring |
| Công cụ và môi trường | Thay framework, runner, browser, sandbox hoặc nhà cung cấp | Tính ổn định, khả năng tái hiện và phạm vi tự động hóa |
| Tổ chức và năng lực | Đổi ownership, thuê ngoài, thay mô hình nhóm hoặc kỹ năng | Trách nhiệm, bàn giao, nguồn lực và quy trình |
| Kết quả đo lường | SLO liên tục không đạt, test flaky tăng, chi phí kiểm thử tăng mạnh | Ngưỡng, mức bao phủ, ưu tiên và cách đo |

Một sự kiện đơn lẻ không tự động chứng minh chiến lược sai. Nó là tín hiệu cần được xác minh và đánh giá theo phạm vi, mức rủi ro, độ kéo dài và khả năng ảnh hưởng.

## 3. Sự kiện từ thay đổi sản phẩm và yêu cầu nghiệp vụ

Chiến lược cần được xem xét khi mục tiêu hoặc cách người dùng sử dụng sản phẩm thay đổi đáng kể.

Các trigger thường gặp:

- Sản phẩm bổ sung hành trình nghiệp vụ mới hoặc thay đổi luồng cốt lõi.
- Thêm vai trò, tenant, nhóm khách hàng hoặc mô hình phân quyền mới.
- Thay đổi cách tính tiền, thanh toán, hoàn tiền, định giá hoặc đối soát.
- Mở rộng sang quốc gia, khu vực, ngôn ngữ hoặc đơn vị tiền tệ mới.
- Chuyển từ giao dịch đơn lẻ sang xử lý hàng loạt hoặc xử lý nền.
- Thêm kênh sử dụng như mobile, API công khai, thiết bị hoặc đối tác tích hợp.
- Thay đổi tiêu chí chấp nhận, mục tiêu trải nghiệm hoặc mức độ quan trọng của chức năng.
- Sản phẩm bắt đầu hỗ trợ nhóm người dùng có nhu cầu tiếp cận hoặc điều kiện sử dụng khác trước.

Những thay đổi này có thể làm xuất hiện rủi ro mới. Ví dụ, thêm multi-tenant không chỉ tạo thêm test case; nó làm tăng tầm quan trọng của kiểm thử phân quyền và cô lập dữ liệu. Mở thị trường mới có thể yêu cầu kiểm tra timezone, locale, thuế, tiền tệ và quy định dữ liệu theo khu vực.

Khi review, cần hỏi mục tiêu nghiệp vụ nào mới xuất hiện, luồng nào quan trọng hơn, tiêu chí nào thay đổi và bằng chứng nào đủ để xác nhận trải nghiệm mới.

## 4. Sự kiện từ thay đổi kiến trúc, nền tảng và công nghệ

Thay đổi kiến trúc thường ảnh hưởng đến cách hệ thống thất bại và cách nhóm có thể quan sát hoặc kiểm soát nó.

Các sự kiện nên đánh giá:

- Tách hoặc hợp nhất dịch vụ, chuyển monolith sang microservices hoặc ngược lại.
- Chuyển database, thay schema lớn, đổi cơ chế replication hoặc consistency.
- Thêm message broker, event streaming, scheduler hoặc worker bất đồng bộ.
- Thay API gateway, service mesh, authentication provider hoặc cơ chế routing.
- Di chuyển cloud, data center, region hoặc nền tảng container.
- Thay runtime, framework, ngôn ngữ, thư viện nền tảng hoặc công cụ build.
- Thay đổi giao thức, serialization, event schema hoặc hợp đồng API.
- Bổ sung cache, search engine, CDN hoặc kho object storage.
- Thay đổi cách quản lý session, transaction hoặc trạng thái phân tán.

Sau thay đổi, test đơn vị có thể vẫn hữu ích nhưng cần bổ sung kiểm thử hợp đồng, tích hợp, migration, resilience hoặc compatibility. Nếu một thao tác trước đây đồng bộ nay trở thành bất đồng bộ, tiêu chí kiểm thử phải xác định trạng thái cuối, thời gian hội tụ, retry, thông điệp trùng và dead-letter.

Không nên giả định chiến lược cũ còn đúng chỉ vì các test hiện có vẫn chạy. Cần đánh giá xem chúng có còn quan sát đúng ranh giới và rủi ro mới hay không.

## 5. Sự kiện từ sự cố production và lỗi lọt qua kiểm thử

Sự cố production là một trong những tín hiệu mạnh nhất cho thấy mô hình rủi ro hoặc phạm vi kiểm thử có thể chưa đầy đủ.

Các trigger đáng chú ý:

- Sự cố nghiêm trọng hoặc ảnh hưởng nhiều khách hàng.
- Mất dữ liệu, giao dịch trùng, sai trạng thái hoặc vi phạm phân quyền.
- Lỗi đã có test nhưng test không phát hiện do dữ liệu hoặc điều kiện không đại diện.
- Nhiều defect cùng loại lặp lại qua các release.
- Lỗi xuất hiện ở môi trường production nhưng không tái hiện được ở staging.
- Rollback, hotfix hoặc incident response diễn ra thường xuyên.
- Thời gian phát hiện hoặc khôi phục vượt mục tiêu đã thống nhất.
- Một lỗi được đánh giá thấp vì thiếu bằng chứng hoặc thiếu chủ sở hữu.

Sau incident, không chỉ thêm một test tái hiện lỗi rồi đóng việc. Cần xác định vì sao lỗi lọt qua: thiếu rủi ro trong mô hình, thiếu cấp độ kiểm thử, test data không phù hợp, môi trường khác biệt, assertion yếu, telemetry thiếu hay quality gate không chặn.

Nếu nguyên nhân là một test case bị thiếu trong phạm vi đã được xác định đúng, cập nhật suite có thể đủ. Nếu sự cố cho thấy nhiều luồng cùng chia sẻ một rủi ro chưa được kiểm soát, cần review chiến lược và cách ưu tiên kiểm thử.

## 6. Sự kiện từ thay đổi rủi ro, bảo mật và dữ liệu

Rủi ro có thể thay đổi ngay cả khi chức năng không thay đổi. Một sản phẩm bắt đầu lưu dữ liệu nhạy cảm hơn, mở endpoint ra internet hoặc nhận yêu cầu kiểm toán mới có thể cần chiến lược kiểm thử khác.

Các trigger gồm:

- Thêm dữ liệu cá nhân, tài chính, sức khỏe hoặc dữ liệu nhạy cảm khác.
- Thay đổi mô hình xác thực, phân quyền, tenant isolation hoặc quản lý secret.
- Mở thêm API, tích hợp đối tác hoặc bề mặt truy cập bên ngoài.
- Xuất hiện mối đe dọa mới hoặc threat model thay đổi.
- Có lỗ hổng nghiêm trọng, sự kiện rò rỉ hoặc truy cập trái phép.
- Thay đổi yêu cầu mã hóa, lưu giữ, xóa hoặc chuyển dữ liệu.
- Có yêu cầu chứng minh tuân thủ, audit trail hoặc kiểm soát truy cập.
- Bổ sung cơ chế AI, xử lý tự động hoặc quyết định ảnh hưởng đến người dùng cần kiểm soát mới.

Review có thể dẫn đến mở rộng security test, privacy test, kiểm thử quyền theo vai trò, kiểm tra dữ liệu xuyên tenant, kiểm thử xóa/ẩn danh và xác minh audit log. Cần phối hợp với chủ sở hữu bảo mật, dữ liệu và tuân thủ để xác định phạm vi và bằng chứng phù hợp.

Không dùng một kết quả quét tự động làm bằng chứng duy nhất rằng rủi ro bảo mật đã được kiểm soát. Phải xem xét tài sản, khả năng khai thác, cấu hình, quyền và các luồng thực tế.

## 7. Sự kiện từ hiệu năng, độ tin cậy và quy mô sử dụng

Khi tải, dữ liệu hoặc mức phụ thuộc tăng, các ngưỡng và workload cũ có thể không còn đại diện.

Nên xem xét lại chiến lược khi:

- Lưu lượng, số người dùng đồng thời hoặc kích thước dữ liệu tăng đáng kể.
- Có giờ cao điểm, burst hoặc mùa vụ mới.
- Độ trễ p95/p99 hoặc tỷ lệ lỗi liên tục vượt mục tiêu.
- Queue lag, retry, timeout hoặc saturation tăng.
- SLO, availability, RPO hoặc RTO thay đổi.
- Hệ thống bắt đầu chạy đa vùng hoặc cần failover.
- Chi phí hạ tầng tăng nhanh hoặc hiệu năng không mở rộng theo dự kiến.
- Một dịch vụ phụ thuộc trở thành điểm nghẽn hoặc nguồn lỗi thường xuyên.

Review cần kiểm tra lại workload, dữ liệu, môi trường, công cụ tạo tải và tiêu chí chấp nhận. Nếu mục tiêu reliability mới yêu cầu phục hồi nhanh hơn, cần đánh giá backup/restore, failover, chaos hoặc fault injection. Nếu hệ thống có nhiều tenant hơn, cần kiểm tra fairness, noisy neighbor và giới hạn tài nguyên theo tenant.

## 8. Sự kiện từ CI/CD và cách phát hành

Cách phát hành thay đổi sẽ ảnh hưởng đến điểm kiểm soát và bằng chứng cần thu thập.

Các trigger gồm:

- Chuyển từ phát hành theo tháng sang triển khai liên tục.
- Bắt đầu dùng canary, blue-green, ring hoặc feature flag.
- Thêm nhiều service hoặc repository vào một release.
- Thay đổi yêu cầu phê duyệt hoặc quality gate.
- Cần rollback hoặc roll-forward trong thời gian ngắn hơn.
- Pipeline thường xuyên chậm, thất bại do hạ tầng hoặc có flaky test tăng.
- Chuyển từ kiểm thử thủ công sang tự động hóa diện rộng.
- Thêm môi trường hoặc khu vực triển khai.

Nếu release được chia nhỏ và thường xuyên hơn, chiến lược có thể cần smoke test tự động, contract test, kiểm tra migration tương thích và telemetry theo phiên bản. Nếu feature flag được dùng rộng rãi, cần kiểm thử cả trạng thái bật/tắt, fallback, quyền thay đổi flag và vòng đời loại bỏ cờ.

Không nên giảm kiểm thử chỉ để đáp ứng tần suất release. Hãy tìm cách đưa phản hồi có giá trị lên sớm, tự động hóa phần ổn định và giữ kiểm tra chuyên sâu ở thời điểm phù hợp.

## 9. Sự kiện từ công cụ, môi trường và phụ thuộc bên ngoài

Một chiến lược có thể dựa vào giả định rằng môi trường và công cụ luôn sẵn sàng. Khi giả định đó không còn đúng, độ tin cậy của bằng chứng bị ảnh hưởng.

Ví dụ:

- Chuyển framework tự động hóa hoặc test runner.
- Thay browser, driver, thiết bị hoặc hệ điều hành hỗ trợ.
- Thay nhà cung cấp cloud, sandbox, payment gateway hoặc API ngoài.
- Thay cách cấp phát môi trường hoặc quản lý dữ liệu.
- Runner không đủ capacity, queue CI kéo dài hoặc cache thường xuyên hỏng.
- Test phụ thuộc mạng ngoài trở nên flaky.
- Công cụ quét, giám sát hoặc báo cáo bị thay thế.
- Thay đổi chính sách truy cập làm nhóm không thể thực hiện kiểm thử như trước.

Review cần đánh giá độ phủ công cụ, khả năng tái hiện, tương thích, thời gian chạy, chi phí và rủi ro vendor lock-in. Có thể cần bổ sung contract test, fake server, sandbox riêng, môi trường tạm hoặc kiểm tra thủ công có mục tiêu trong giai đoạn chuyển đổi.

## 10. Sự kiện từ tổ chức, trách nhiệm và năng lực nhóm

Chiến lược không chỉ phụ thuộc công nghệ mà còn phụ thuộc khả năng thực hiện và quyền quyết định.

Nên xem xét lại khi:

- Đổi chủ sở hữu sản phẩm, service owner, QA lead hoặc người phê duyệt.
- Tách hoặc hợp nhất nhóm, chuyển trách nhiệm sang nhóm khác.
- Thuê ngoài một phần kiểm thử hoặc vận hành.
- Thay đổi mô hình on-call, hỗ trợ ngoài giờ hoặc lịch phát hành.
- Mất kỹ năng quan trọng hoặc đưa công nghệ mới vào nhóm.
- Thay đổi quyền truy cập, quy trình bàn giao hoặc kênh incident.
- Năng lực nhóm không đủ cho phạm vi và mục tiêu mới.

Review có thể dẫn đến điều chỉnh RACI, quy trình handoff, kế hoạch đào tạo, phân bổ nguồn lực hoặc mức tự động hóa. Không nên giữ một chiến lược yêu cầu kiểm thử chuyên sâu nếu không có người, quyền và công cụ để thực hiện.

## 11. Sự kiện từ số liệu và xu hướng chất lượng

Một thay đổi đơn lẻ có thể chưa đủ để kích hoạt review lớn, nhưng xu hướng kéo dài thường cho thấy cách kiểm thử hiện tại đang mất hiệu quả.

Các tín hiệu định lượng:

- Defect escape rate tăng.
- Tỷ lệ lỗi nghiêm trọng sau release tăng.
- Test pass rate giảm hoặc flaky rate tăng.
- Thời gian phản hồi pipeline hoặc thời gian khôi phục tăng.
- Regression suite tăng thời gian nhưng không phát hiện thêm rủi ro tương xứng.
- Coverage tăng nhưng defect lọt qua không giảm.
- Nhiều test bị quarantine hoặc bị bỏ qua.
- Chi phí môi trường và công cụ tăng nhanh.
- Tỷ lệ kiểm thử thủ công lặp lại tăng.
- Các quality gate thường xuyên được override.

Các tín hiệu định tính:

- Người dùng phản ánh cùng một vấn đề qua nhiều lần phát hành.
- QA và Development thường bất đồng về điều kiện hoàn tất.
- Nhóm không tin vào kết quả CI.
- Test không còn phản ánh luồng người dùng thực tế.
- Bằng chứng không đủ để quyết định release.
- Nhóm vận hành liên tục phát hiện khác biệt giữa staging và production.

Không nên đặt ngưỡng kích hoạt chỉ dựa vào một chỉ số mà không xét quy mô mẫu, thay đổi tải và mức ảnh hưởng. Ví dụ, một lần flaky test tăng do runner bảo trì có thể là sự kiện vận hành tạm thời; xu hướng tăng trong nhiều sprint và nhiều module có thể cho thấy vấn đề kiến trúc test hoặc môi trường.

## 12. Phân biệt trigger cần review chiến lược với thay đổi thường lệ

Có thể dùng ma trận sàng lọc để quyết định cấp độ phản ứng.

| Câu hỏi | Nếu câu trả lời là “có” | Hướng xử lý |
|---|---|---|
| Giả định nền tảng về kiến trúc, người dùng hoặc môi trường đã thay đổi? | Phạm vi kiểm thử có thể không còn phù hợp | Đánh giá review chiến lược |
| Có rủi ro mới hoặc mức nghiêm trọng tăng? | Mô hình ưu tiên và gate có thể thiếu | Review phần rủi ro liên quan |
| Sự cố cho thấy test hiện tại không phát hiện hoặc không tái hiện được vấn đề? | Cách kiểm thử có thể có khoảng trống hệ thống | Phân tích nguyên nhân và xem xét chiến lược |
| Nhiều nhóm hoặc nhiều luồng cùng bị ảnh hưởng? | Ranh giới trách nhiệm hoặc phương pháp có thể không đủ | Review liên chức năng |
| Chỉ một test case hoặc một trường dữ liệu thay đổi? | Phạm vi chiến lược có thể vẫn đúng | Cập nhật test hoặc suite |
| Thay đổi không làm đổi rủi ro, kiến trúc hay tiêu chí? | Có thể chỉ cần cập nhật tài liệu hoặc kế hoạch | Xử lý theo quy trình thường lệ |

Sàng lọc không phải phép quyết định tự động. Người sở hữu chiến lược cần xem xét bằng chứng và ghi lý do nếu quyết định không mở review dù có trigger.

## 13. Đánh giá mức độ tác động của sự kiện

Sau khi xác nhận sự kiện, đánh giá ảnh hưởng theo nhiều chiều:

1. **Phạm vi:** một test, một module, một service, nhiều sản phẩm hay toàn nền tảng?
2. **Mức rủi ro:** ảnh hưởng đến dữ liệu, tiền, quyền truy cập, an toàn hoặc nghĩa vụ không?
3. **Khả năng xảy ra:** sự kiện là một lần đơn lẻ, có xu hướng lặp hay có thể lan rộng?
4. **Khả năng phát hiện:** kiểm soát hiện tại có nhận ra lỗi trước khi gây tác động không?
5. **Khả năng phục hồi:** có workaround, rollback, backup hoặc phương án thay thế không?
6. **Tính khẩn cấp:** có release, deadline hoặc thay đổi bắt buộc sắp diễn ra không?
7. **Bằng chứng:** dữ liệu hiện có đủ để kết luận hay cần một hoạt động khám phá?

Có thể dùng ma trận tác động đơn giản:

| Mức | Đặc điểm | Phản ứng |
|---|---|---|
| Thấp | Tác động cục bộ, rủi ro không đổi, có cách kiểm soát rõ | Cập nhật test hoặc kế hoạch |
| Trung bình | Một nhóm rủi ro hoặc phương pháp bị ảnh hưởng | Review phần chiến lược liên quan |
| Cao | Nhiều luồng, phụ thuộc hoặc gate quan trọng bị ảnh hưởng | Mở review chiến lược có các bên liên quan |
| Khẩn cấp | Có nguy cơ dữ liệu, bảo mật, an toàn hoặc release đang gây tác động lớn | Ứng phó ngay, sau đó review chiến lược đầy đủ |

Phân mức cần theo chính sách tổ chức. Một sự kiện bảo mật có thể yêu cầu phản ứng tức thời ngay cả khi phạm vi kỹ thuật nhỏ.

## 14. Quy trình kích hoạt và thực hiện review

Một quy trình rõ ràng giúp trigger không bị bỏ qua và quyết định có thể truy vết.

1. **Ghi nhận sự kiện:** tạo bản ghi từ change request, incident, metric, audit hoặc phản hồi người dùng.
2. **Xác minh:** kiểm tra sự kiện có thật, phạm vi và thời điểm.
3. **Sàng lọc:** xác định đây là cập nhật test thường lệ, review một phần hay review chiến lược.
4. **Đánh giá tác động:** liên kết với mục tiêu, rủi ro, kiến trúc, môi trường, nguồn lực và release.
5. **Chỉ định chủ trì:** giao test strategy owner hoặc người có thẩm quyền điều phối.
6. **Thu thập bằng chứng:** defect, telemetry, test result, change record, threat model và dữ liệu lịch sử.
7. **Tham vấn:** mời product, development, QA, platform, operations, security hoặc data owner tùy phạm vi.
8. **Đưa ra quyết định:** giữ nguyên, điều chỉnh cục bộ, sửa đổi chiến lược hoặc lập chiến lược mới.
9. **Cập nhật và phê duyệt:** sửa tài liệu, tiêu chí, trách nhiệm, nguồn lực và lịch có liên quan.
10. **Truyền thông và xác minh:** thông báo thay đổi, cập nhật test suite/gate và kiểm tra hiệu lực.
11. **Theo dõi:** đánh giá kết quả sau một hoặc nhiều chu kỳ kiểm thử/phát hành.

Không nên kết thúc review bằng một biên bản họp chung chung. Mỗi quyết định cần có chủ sở hữu, hành động, thời hạn, bằng chứng hoàn thành và rủi ro còn lại.

## 15. Các kết quả có thể có sau review

Review không nhất thiết dẫn đến viết lại toàn bộ chiến lược. Có thể chọn một trong các kết quả:

- **Giữ nguyên:** trigger đã được đánh giá nhưng không làm thay đổi giả định hoặc rủi ro cốt lõi; ghi rõ lý do.
- **Cập nhật test:** thêm hoặc sửa test case, fixture hay assertion.
- **Điều chỉnh test suite:** thay đổi nhóm regression, phạm vi tự động hóa hoặc thứ tự chạy.
- **Điều chỉnh kế hoạch:** bổ sung môi trường, nguồn lực, thời gian hoặc hoạt động khám phá.
- **Sửa đổi một phần chiến lược:** cập nhật rủi ro, cấp độ kiểm thử, loại kiểm thử, dữ liệu, môi trường, gate hoặc trách nhiệm liên quan.
- **Tái lập chiến lược:** dùng khi mục tiêu, kiến trúc, rủi ro hoặc mô hình vận hành đã thay đổi sâu rộng.
- **Tạm dừng hoặc giới hạn phát hành:** khi chưa có bằng chứng đủ để chấp nhận rủi ro.
- **Chấp nhận ngoại lệ có thời hạn:** chỉ khi đúng thẩm quyền, có lý do, biện pháp giảm thiểu và ngày xem xét lại.

Mỗi kết quả phải chỉ rõ phần nào thay đổi, phần nào giữ nguyên và lý do. Nếu giữ nguyên, lưu bằng chứng để tránh cùng trigger bị tranh luận lại mà không có thông tin mới.

## 16. Quy định trách nhiệm và quyền quyết định

Cần xác định ai có thể yêu cầu review, ai đánh giá và ai phê duyệt thay đổi chiến lược.

| Vai trò | Trách nhiệm điển hình |
|---|---|
| Test strategy owner / QA lead | Duy trì chiến lược, sàng lọc trigger, điều phối review và đề xuất thay đổi |
| Product owner / business owner | Xác nhận mục tiêu, tác động người dùng và ưu tiên nghiệp vụ |
| Development / architect | Đánh giá tác động mã nguồn, kiến trúc, API và phụ thuộc |
| Platform / DevOps / SRE | Đánh giá môi trường, CI/CD, khả năng quan sát và phục hồi |
| Security / privacy / compliance | Đánh giá rủi ro bảo mật, dữ liệu và nghĩa vụ |
| Data owner / DBA | Đánh giá dữ liệu, migration, backup và đối soát |
| Release manager | Liên kết thay đổi chiến lược với kế hoạch và quyết định phát hành |
| Risk owner / approver | Chấp nhận rủi ro hoặc phê duyệt ngoại lệ theo thẩm quyền |

Mọi thành viên có thể nêu trigger, nhưng cần có đầu mối chịu trách nhiệm theo dõi đến khi có quyết định. Người phê duyệt phải có thẩm quyền tương ứng; QA không tự động là người chấp nhận rủi ro nghiệp vụ hoặc pháp lý.

## 17. Thiết lập review định kỳ và review theo sự kiện

Có hai cơ chế bổ sung cho nhau:

- **Review định kỳ:** thực hiện theo chu kỳ đã thống nhất để kiểm tra chiến lược còn phù hợp, ngay cả khi chưa có trigger rõ ràng.
- **Review theo sự kiện:** kích hoạt khi có thay đổi hoặc tín hiệu vượt điều kiện đã định.

Review định kỳ có thể diễn ra theo quý, theo release lớn hoặc theo chu kỳ quản trị của tổ chức; tần suất phụ thuộc tốc độ thay đổi và mức rủi ro. Review theo sự kiện không nên chờ đến kỳ kế tiếp nếu có sự cố nghiêm trọng, thay đổi bảo mật hoặc nghĩa vụ bắt buộc.

Nên duy trì danh mục trigger với:
- Tên sự kiện và mô tả.
- Nguồn phát hiện.
- Điều kiện kích hoạt hoặc ngưỡng.
- Người nhận thông báo.
- Mức phản ứng.
- Chủ sở hữu review.
- Thời hạn đánh giá.
- Bằng chứng cần thu thập.

Khi tổ chức thay đổi tần suất review, cần bảo đảm các trigger khẩn cấp vẫn có đường xử lý tức thời.

## 18. Ghi nhận và truy vết quyết định review

Một hồ sơ review nên cho phép người khác hiểu tại sao chiến lược được thay đổi hoặc giữ nguyên.

Các trường nên có:

| Trường | Nội dung |
|---|---|
| Review ID | Mã duy nhất |
| Trigger | Sự kiện, thay đổi hoặc xu hướng khởi tạo review |
| Nguồn và thời điểm | Incident, change request, metric, audit hoặc phản hồi |
| Phạm vi ảnh hưởng | Sản phẩm, module, service, môi trường và release |
| Rủi ro liên quan | Tác động, khả năng xảy ra và mức ưu tiên |
| Bằng chứng | Test result, log, trace, defect, workload hoặc tài liệu |
| Người tham gia | Chủ trì, chuyên gia và người phê duyệt |
| Quyết định | Giữ, cập nhật cục bộ, sửa đổi hoặc tái lập chiến lược |
| Hành động | Việc cần làm, chủ sở hữu và thời hạn |
| Ngoại lệ | Rủi ro còn lại, biện pháp giảm thiểu và ngày hết hạn |
| Ngày hiệu lực | Khi chiến lược hoặc gate mới bắt đầu áp dụng |
| Kết quả theo dõi | Bằng chứng cho thấy thay đổi có hiệu quả |

Liên kết hồ sơ với phiên bản chiến lược, test suite, pipeline, change request và incident liên quan. Không chỉ lưu bản cuối; cần giữ lịch sử để có thể hiểu sự thay đổi qua thời gian.

## 19. Ví dụ: thay đổi kiến trúc và sự cố làm phát sinh review

Một hệ thống đặt hàng chuyển bước xác nhận thanh toán từ lời gọi đồng bộ sang queue để giảm thời gian phản hồi. Sau triển khai, một số đơn hàng ở trạng thái chờ lâu, callback lặp tạo nhiều lần cập nhật và test tích hợp cũ vẫn pass vì chỉ xác minh phản hồi HTTP ban đầu.

Nhóm nhận diện ba trigger:

1. Kiến trúc thay đổi từ đồng bộ sang bất đồng bộ.
2. Sự cố production cho thấy trạng thái nghiệp vụ không được xác minh đến cuối.
3. Bộ test hiện tại không kiểm tra message lặp, retry và thời gian hội tụ.

Review xác định chiến lược cần bổ sung:

- Kiểm thử contract cho schema event.
- Integration test với queue và consumer.
- Test idempotency cho callback và message lặp.
- Kiểm thử timeout, retry, dead-letter và phục hồi worker.
- Tiêu chí chờ trạng thái cuối có timeout rõ.
- Telemetry theo correlation ID và trạng thái giao dịch.
- Đối soát dữ liệu sau khi xử lý lỗi.
- Điều kiện release dựa trên kết quả nghiệp vụ, không chỉ HTTP response.

Nhóm cũng cập nhật trách nhiệm giữa Development, QA và Operations, bổ sung runbook và theo dõi sau phát hành. Một test mới được thêm vào suite là cần thiết, nhưng chỉ review chiến lược mới giải quyết được khoảng trống ở cấp kiến trúc, quan sát và tiêu chí release.

## 20. Những sai lầm khi xác định trigger và thực hiện review

Các cách làm sau thường khiến review kém hiệu quả:

- **Chỉ review theo lịch:** bỏ qua sự cố hoặc thay đổi rủi ro xảy ra giữa hai kỳ.
- **Review mọi thay đổi:** tạo quá nhiều thủ tục và làm chậm công việc cục bộ.
- **Chỉ dựa vào cảm nhận:** không dùng incident, defect, metric hoặc bằng chứng thay đổi.
- **Chỉ thêm test sau sự cố:** không xem xét nguyên nhân hệ thống khiến lỗi lọt qua.
- **Không có chủ sở hữu:** trigger được ghi nhận nhưng không ai theo dõi quyết định.
- **Không kiểm tra hiệu quả:** thay đổi chiến lược được phê duyệt nhưng không xác minh có giảm rủi ro.
- **Giữ chiến lược vì chi phí đã đầu tư:** tiếp tục dùng phương pháp không còn phù hợp chỉ vì test suite hiện tại lớn.
- **Thay đổi ngưỡng để làm đẹp báo cáo:** giảm yêu cầu thay vì giải quyết nguyên nhân suy giảm.
- **Không cập nhật tài liệu và bên liên quan:** các nhóm tiếp tục làm theo phiên bản chiến lược cũ.

Một review tốt có phạm vi vừa đủ, bằng chứng rõ, quyết định có người sở hữu và bước xác minh sau thay đổi.

## 21. Quy trình tổng hợp xác định và xử lý trigger

Có thể áp dụng quy trình sau:

1. **Theo dõi nguồn sự kiện:** change request, incident, defect, metric, audit, roadmap và phản hồi người dùng.
2. **Đối chiếu danh mục trigger:** xác định sự kiện thuộc nhóm nào và có đạt điều kiện kích hoạt không.
3. **Xác minh dữ liệu:** loại bỏ cảnh báo sai, trùng lặp hoặc thiếu bối cảnh.
4. **Đánh giá phạm vi và rủi ro:** xem ảnh hưởng tới mục tiêu, kiến trúc, dữ liệu, bảo mật, vận hành và release.
5. **Chọn cấp phản ứng:** cập nhật test, điều chỉnh kế hoạch, review một phần hay review toàn chiến lược.
6. **Chỉ định chủ trì và thời hạn:** xác định người theo dõi đến khi có quyết định.
7. **Thu thập bằng chứng và tham vấn:** mời đúng nhóm chuyên môn.
8. **Quyết định và ghi nhận:** giữ nguyên, cập nhật, sửa đổi, tái lập hoặc tạm dừng.
9. **Triển khai thay đổi:** cập nhật tài liệu, test suite, pipeline, môi trường và trách nhiệm.
10. **Xác minh hiệu quả:** đo lại tín hiệu, kiểm tra test mới và đánh giá rủi ro còn lại.
11. **Đóng review:** lưu quyết định, liên kết tài liệu và lịch rà soát tiếp theo.

~~~mermaid
flowchart TD
    A["Sự kiện, thay đổi hoặc xu hướng"] --> B["Đối chiếu danh mục trigger"]
    B --> C["Xác minh và đánh giá tác động"]
    C --> D{"Có ảnh hưởng giả định hoặc rủi ro nền tảng?"}
    D -->|Không| E["Cập nhật test hoặc kế hoạch thường lệ"]
    D -->|Có| F["Mở review chiến lược"]
    F --> G["Thu thập bằng chứng và tham vấn"]
    G --> H["Quyết định giữ, sửa đổi hoặc tái lập"]
    H --> I["Cập nhật chiến lược và artefact liên quan"]
    I --> J["Xác minh hiệu quả và rủi ro còn lại"]
    J --> K["Lưu quyết định và theo dõi"]
    E --> K
~~~

## 22. Checklist xác định sự kiện cần xem xét lại chiến lược

Khi có thay đổi hoặc tín hiệu bất thường, hãy kiểm tra:

- Sự kiện có làm thay đổi mục tiêu, hành trình hoặc mức quan trọng của sản phẩm không?
- Có kiến trúc, công nghệ, API, database hoặc phụ thuộc mới không?
- Có rủi ro mới về bảo mật, quyền riêng tư, dữ liệu hoặc tuân thủ không?
- Có incident nghiêm trọng, lỗi lọt qua hoặc xu hướng defect lặp lại không?
- Tải, quy mô dữ liệu, SLO, RPO hoặc RTO có thay đổi không?
- Cách phát hành, CI/CD, canary hoặc feature flag có thay đổi không?
- Công cụ, môi trường hoặc nhà cung cấp có làm giảm độ tin cậy của bằng chứng không?
- Vai trò, ownership, kỹ năng hoặc nguồn lực có thay đổi không?
- Số liệu cho thấy test flaky, thời gian pipeline, chi phí hoặc defect escape đang xấu đi không?
- Thay đổi chỉ cần cập nhật test case/suite hay đã ảnh hưởng giả định nền tảng?
- Phạm vi review, người chủ trì, người phê duyệt và thời hạn đã rõ chưa?
- Quyết định có gắn với bằng chứng, hành động, chủ sở hữu và ngày hiệu lực không?
- Sau khi cập nhật, có cách xác minh chiến lược mới kiểm soát rủi ro tốt hơn không?

Chiến lược kiểm thử cần được xem xét khi bối cảnh làm thay đổi rủi ro, giả định hoặc khả năng tạo bằng chứng đáng tin cậy. Nhận diện trigger từ sản phẩm, kiến trúc, sự cố, bảo mật, hiệu năng, CI/CD, công cụ và tổ chức giúp nhóm phản ứng đúng lúc. Khi mỗi review có phạm vi rõ, bằng chứng, người quyết định và bước xác minh sau thay đổi, chiến lược có thể phát triển cùng hệ thống mà không tạo thủ tục không cần thiết cho những điều chỉnh thường lệ.

