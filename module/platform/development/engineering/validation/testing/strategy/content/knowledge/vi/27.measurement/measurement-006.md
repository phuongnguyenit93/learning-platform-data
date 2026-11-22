# Đo thời gian điều tra, sửa lỗi và khôi phục pipeline

Pipeline CI/CD có thể thất bại vì lỗi mã nguồn, test không ổn định, cấu hình sai, runner thiếu tài nguyên hoặc dịch vụ phụ thuộc gián đoạn. Khi sự cố xảy ra, nhóm cần biết mất bao lâu để nhận ra, phân loại, tìm nguyên nhân, sửa, xác minh và đưa pipeline trở lại trạng thái đáng tin cậy. Chỉ đo tổng thời gian từ lúc job bắt đầu đến lúc chạy thành công lần tiếp theo sẽ không cho biết phần nào đang gây chậm trễ và nhóm có thể cải thiện ở đâu.

Đo thời gian điều tra, sửa lỗi và khôi phục pipeline là việc thu thập các mốc thời gian nhất quán trong vòng đời xử lý sự cố, sau đó phân tích theo loại lỗi, mức ảnh hưởng và giai đoạn. Mục tiêu là giảm thời gian chờ và điều tra không cần thiết, rút ngắn thời gian khôi phục, đồng thời giữ chất lượng xác minh. Một pipeline được đánh dấu xanh nhờ bỏ qua test hoặc retry vô hạn chưa phải là pipeline đã được khôi phục đáng tin cậy.

## 1. Phân biệt các khoảng thời gian trong vòng đời xử lý lỗi

Một lần pipeline thất bại có thể đi qua nhiều giai đoạn. Cần đặt tên và định nghĩa từng khoảng để mọi nhóm đo cùng một cách.

| Giai đoạn | Bắt đầu | Kết thúc | Câu hỏi được trả lời |
|---|---|---|---|
| Phát hiện | Lỗi hoặc tín hiệu bất thường xuất hiện | Hệ thống hoặc người phụ trách nhận biết | Mất bao lâu để phát hiện? |
| Tiếp nhận | Cảnh báo/ticket được tạo | Có người hoặc nhóm xác nhận nhận xử lý | Mất bao lâu để có chủ sở hữu? |
| Triage | Bắt đầu phân loại và xác định phạm vi | Có phân loại, mức độ và hướng điều tra ban đầu | Mất bao lâu để biết nên điều tra gì? |
| Chẩn đoán | Bắt đầu kiểm tra nguyên nhân | Có nguyên nhân đủ tin cậy hoặc giả thuyết được xác minh | Mất bao lâu để tìm ra nguyên nhân? |
| Sửa lỗi | Bắt đầu thay đổi mã, test, cấu hình hoặc hạ tầng | Bản sửa sẵn sàng để xác minh | Mất bao lâu để tạo phương án sửa? |
| Xác minh | Bắt đầu chạy kiểm tra sau sửa | Bằng chứng xác nhận bản sửa và phạm vi hồi quy đạt | Mất bao lâu để chứng minh đã sửa đúng? |
| Khôi phục | Pipeline hoặc năng lực CI bị suy giảm | Quy trình kiểm tra bắt buộc hoạt động ổn định trở lại | Mất bao lâu để trở về trạng thái phục vụ? |
| Theo dõi sau khôi phục | Bắt đầu quan sát sau sửa | Hết cửa sổ theo dõi hoặc đóng sự cố | Có tái diễn hoặc tác dụng phụ không? |

Các giai đoạn có thể chồng lấn. Ví dụ, một kỹ sư vừa điều tra vừa chuẩn bị bản sửa; nhóm vận hành có thể khôi phục runner trong khi QA phân tích test. Vì vậy, không nên cộng tất cả khoảng thời gian thành một con số nếu chúng không nối tiếp nhau. Cần ghi rõ đang đo thời gian lịch (elapsed time), công sức thực hiện (effort) hay thời gian chờ.

## 2. Phân biệt thời gian sửa lỗi với thời gian khôi phục pipeline

Hai chỉ số này thường bị dùng thay thế nhau nhưng đo kết quả khác nhau.

- **Thời gian sửa lỗi (time to fix):** khoảng từ khi bắt đầu xử lý một lỗi đến khi có bản sửa sẵn sàng được xác minh, hoặc đến khi bản sửa được xác nhận, tùy định nghĩa đã chọn.
- **Thời gian khôi phục pipeline (time to restore):** khoảng từ lúc pipeline mất khả năng cung cấp kết quả đáng tin cậy đến khi các gate cần thiết hoạt động trở lại.
- **Thời gian khôi phục dịch vụ (service recovery time):** thời gian đưa dịch vụ sản phẩm trở lại hoạt động; có thể liên quan đến pipeline nhưng là một mục tiêu vận hành khác.
- **Thời gian xử lý (handling time):** tổng thời gian con người thực sự dành cho triage, chẩn đoán, sửa và xác minh.
- **Thời gian chờ (waiting time):** thời gian chờ người khác, build, quyền, môi trường, runner hoặc dịch vụ phụ thuộc.

Ví dụ, một lỗi test do selector không còn phù hợp có thể cần 30 phút để sửa và 10 phút để xác minh, nhưng phải chờ runner khả dụng thêm 40 phút. Effort kỹ thuật là khoảng 40 phút; elapsed time từ lúc nhận việc đến khi xác minh xong có thể là 80 phút. Nếu chỉ báo cáo “mất 80 phút sửa lỗi”, nhóm sẽ hiểu sai nguyên nhân chậm.

Tương tự, pipeline có thể được khôi phục bằng cách chuyển job sang runner dự phòng trong 15 phút, trong khi nguyên nhân gốc của runner chính vẫn cần điều tra thêm. Khi đó cần ghi riêng thời gian khôi phục tạm thời và thời gian xử lý nguyên nhân gốc.

## 3. Xác định sự kiện nào được tính là lỗi pipeline

Không phải mọi job thất bại đều là sự cố cùng loại. Cần có quy tắc phân loại để dữ liệu thời gian có thể so sánh.

Các nhóm thường gặp:

- **Lỗi sản phẩm:** unit, integration hoặc end-to-end test phát hiện hành vi sai.
- **Lỗi kiểm thử:** assertion sai, fixture lỗi, selector mong manh hoặc test không đồng bộ.
- **Flaky test:** cùng mã và điều kiện nhưng kết quả thay đổi giữa các lần chạy.
- **Lỗi build/toolchain:** compiler, package manager, dependency hoặc bước đóng gói thất bại.
- **Lỗi cấu hình:** biến môi trường, secret, quyền hoặc tham số pipeline sai.
- **Lỗi hạ tầng:** runner, network, storage, cluster hoặc dịch vụ CI không sẵn sàng.
- **Lỗi phụ thuộc bên ngoài:** registry, sandbox, API nhà cung cấp hoặc dịch vụ được gọi không phản hồi.
- **Lỗi vận hành pipeline:** workflow sai, cache hỏng, queue tắc hoặc artifact không được truyền đúng.

Một pipeline đỏ có thể chứa nhiều nguyên nhân. Ví dụ, test chức năng thất bại vì dịch vụ sandbox không phản hồi; đó là lỗi môi trường hoặc phụ thuộc, không nhất thiết là lỗi sản phẩm. Ghi nhận đúng loại giúp nhóm chọn đúng người xử lý và tránh đánh giá sai chất lượng mã.

Cần định nghĩa rõ phạm vi thống kê: đo mọi lần job fail, chỉ các sự kiện gây chặn merge, hay chỉ sự cố làm mất năng lực CI của nhiều nhóm. Có thể theo dõi cả ba, nhưng phải tách chúng thành các tập dữ liệu khác nhau.

## 4. Thiết lập mốc thời gian có thể kiểm chứng

Đo thời gian đáng tin cậy bắt đầu từ việc ghi sự kiện đúng lúc và gắn chúng với cùng một định danh.

Các mốc nên được lưu:

- Thời điểm job hoặc test đầu tiên thất bại.
- Thời điểm cảnh báo hoặc incident được tạo.
- Thời điểm người phụ trách xác nhận.
- Thời điểm triage bắt đầu và kết thúc.
- Thời điểm có giả thuyết nguyên nhân và thời điểm được xác minh.
- Thời điểm bắt đầu sửa và tạo commit/bản cấu hình sửa.
- Thời điểm build sửa bắt đầu và kết thúc.
- Thời điểm xác minh bắt đầu và kết thúc.
- Thời điểm gate bắt buộc trở lại hoạt động.
- Thời điểm đóng sự cố và kết thúc theo dõi.

Mỗi sự kiện cần có pipeline ID, run ID, job ID, commit, môi trường, nhóm sở hữu và mã incident hoặc ticket. Nếu một lỗi xuất hiện ở nhiều pipeline, cần liên kết các lần chạy với cùng một sự cố gốc để tránh đếm như nhiều lỗi độc lập.

Dùng timestamp có múi giờ rõ ràng và đồng bộ đồng hồ giữa các hệ thống. Trong cùng một tiến trình, có thể dùng đồng hồ monotonic để đo duration vì nó không bị ảnh hưởng bởi việc đồng hồ hệ thống được chỉnh. Khi đối chiếu giữa CI, ticket và chat, dùng thời gian UTC hoặc một chuẩn chung và ghi rõ nguồn thời gian.

Không suy ra thời điểm phát hiện từ thời điểm ticket được cập nhật nếu hệ thống không lưu sự kiện ban đầu. Nếu thiếu mốc, đánh dấu dữ liệu không đầy đủ thay vì tự điền một giá trị ước đoán như thể đó là dữ liệu chính xác.

## 5. Định nghĩa chỉ số và công thức nhất quán

Có thể xây dựng bộ chỉ số theo các mốc đã thống nhất.

| Chỉ số | Công thức khái quát | Ý nghĩa |
|---|---|---|
| Time to Detect (TTD) | Thời điểm phát hiện − thời điểm lỗi bắt đầu | Tốc độ nhận biết vấn đề |
| Time to Acknowledge (TTA) | Thời điểm xác nhận − thời điểm cảnh báo/ticket | Tốc độ tiếp nhận |
| Time to Triage (TTT) | Kết thúc triage − bắt đầu triage | Thời gian phân loại ban đầu |
| Time to Diagnose (TTDg) | Nguyên nhân được xác minh − bắt đầu điều tra | Thời gian chẩn đoán |
| Time to Fix (TTF) | Bản sửa sẵn sàng − bắt đầu sửa | Thời gian tạo bản sửa |
| Time to Verify (TTV) | Xác minh đạt − bắt đầu xác minh | Thời gian chứng minh bản sửa |
| Time to Restore (TTR) | Pipeline hoạt động tin cậy − lúc suy giảm bắt đầu | Thời gian khôi phục năng lực CI |
| Reopen/Recur interval | Lần tái mở hoặc tái diễn − thời điểm đóng | Khoảng thời gian trước khi lỗi quay lại |

Các chữ viết tắt có thể khác nhau giữa tổ chức. Đặc biệt, TTD đôi khi được dùng cho detect hoặc diagnose; cần chọn tên nội bộ rõ ràng, công bố định nghĩa và không thay đổi giữa các báo cáo.

Với một sự kiện pipeline, có thể tính elapsed time từ thời điểm thất bại đầu tiên đến lúc gate bắt buộc hoạt động lại. Nhưng cần báo cáo thêm các giai đoạn để biết thời gian nằm ở chờ tiếp nhận, chẩn đoán, sửa hay xác minh.

## 6. Phân tách thời gian làm việc và thời gian chờ

Elapsed time là thời gian trôi qua; effort là thời gian con người hoặc tài nguyên chủ động làm việc. Hai số liệu phục vụ quyết định khác nhau.

Ví dụ:

| Hoạt động | Thời gian lịch | Công sức thực hiện | Phần chờ |
|---|---:|---:|---:|
| Chờ người tiếp nhận | 45 phút | 0 | 45 phút |
| Triage và tái hiện | 25 phút | 25 phút | 0 |
| Chờ môi trường | 60 phút | 0 | 60 phút |
| Sửa test | 35 phút | 35 phút | 0 |
| Chạy build và test | 20 phút | 5 phút giám sát | 15 phút |
| Review và xác minh | 30 phút | 30 phút | 0 |

Không nên cộng công sức của nhiều người thành thời gian lịch. Hai người cùng điều tra trong 30 phút tạo ra 60 phút effort nhưng elapsed time vẫn là 30 phút. Ngược lại, một ticket có thể tồn tại 2 ngày nhưng chỉ cần 45 phút làm việc vì chờ quyền truy cập hoặc lịch chuyên gia.

Đo cả hai giúp xác định giải pháp phù hợp. Nếu effort cao, cần cải thiện công cụ, tài liệu hoặc kỹ năng. Nếu thời gian chờ cao, cần cải thiện quyền sở hữu, quy trình tiếp nhận, năng lực runner hoặc phụ thuộc giữa nhóm.

## 7. Đo thời gian triage và chẩn đoán

Triage xác định mức ảnh hưởng, loại lỗi, chủ sở hữu và bước tiếp theo. Chẩn đoán tìm nguyên nhân đủ tin cậy để sửa đúng.

Nên ghi nhận:

- Thời gian từ cảnh báo đến khi có người xác nhận.
- Thời gian từ tiếp nhận đến khi phân loại được lỗi.
- Số lần chuyển nhóm trước khi tìm đúng chủ sở hữu.
- Số lần cần yêu cầu thêm log, dữ liệu hoặc bước tái hiện.
- Thời gian để tạo được kịch bản tái hiện.
- Thời gian từ giả thuyết đầu tiên đến khi nguyên nhân được xác minh.
- Tỷ lệ phân loại lại sau khi có thêm bằng chứng.

Nếu triage nhanh nhưng chẩn đoán kéo dài, có thể thiếu log, trace, correlation ID, dữ liệu tái hiện hoặc quyền truy cập. Nếu triage kéo dài, có thể quy trình tiếp nhận chưa rõ hoặc cảnh báo thiếu thông tin. Nếu lỗi liên tục bị chuyển qua lại, ma trận trách nhiệm và ranh giới giữa sản phẩm, test và hạ tầng cần được cải thiện.

Không khuyến khích đóng triage nhanh bằng cách gán mọi lỗi cho “hạ tầng” hoặc “flaky”. Phân loại ban đầu có thể thay đổi; hãy lưu lịch sử và lý do thay đổi để dữ liệu phản ánh quá trình học hỏi.

## 8. Đo thời gian sửa lỗi theo loại công việc

Thời gian sửa khác nhau đáng kể theo nguyên nhân. Gộp mọi lỗi thành một chỉ số duy nhất dễ tạo kết luận sai.

Có thể phân nhóm:

- Sửa assertion hoặc test data.
- Sửa flaky test và đồng bộ.
- Sửa mã sản phẩm.
- Sửa cấu hình pipeline hoặc secret.
- Sửa image, dependency hoặc toolchain.
- Khôi phục runner, cluster hoặc network.
- Xử lý dịch vụ phụ thuộc.
- Sửa cache hoặc artifact.
- Sửa quyền và chính sách bảo mật.

Với mỗi loại, ghi thời điểm bắt đầu sửa, thời điểm bản sửa sẵn sàng, số commit hoặc thay đổi cấu hình và số lần phải sửa lại. Nếu bản sửa đầu tiên không đạt, không nên chỉ tính từ lần sửa cuối; hãy báo cả thời gian đến bản sửa đạt và số vòng sửa.

Một số lỗi cần workaround để khôi phục nhanh, sau đó mới có bản sửa gốc. Ghi hai kết quả riêng: thời gian khôi phục dịch vụ tạm thời và thời gian loại bỏ nguyên nhân gốc. Workaround có thể giảm tác động ngay nhưng không đồng nghĩa vấn đề đã được giải quyết triệt để.

## 9. Đo thời gian xác minh và khôi phục có chất lượng

Sau khi sửa, pipeline cần chạy lại các kiểm tra phù hợp. Một lần chạy xanh đơn lẻ chưa chắc đủ để xác nhận khôi phục, đặc biệt với flaky test hoặc sự cố hạ tầng chập chờn.

Điều kiện khôi phục có thể gồm:

- Build và các gate bắt buộc hoàn tất thành công.
- Test thất bại trước đó pass trên đúng commit và môi trường.
- Phạm vi hồi quy theo rủi ro đã chạy.
- Không có lỗi mới hoặc suy giảm quan trọng do bản sửa.
- Runner, queue và dịch vụ phụ thuộc ổn định.
- Kết quả được liên kết với build và cấu hình cụ thể.
- Nếu cần, nhiều lần chạy liên tiếp đạt điều kiện ổn định.

Định nghĩa trước “pipeline restored” theo mức ảnh hưởng. Với một lỗi đơn lẻ trên một pull request, khôi phục có thể là gate của pull request đó hoạt động trở lại. Với sự cố runner dùng chung, cần xác nhận năng lực phục vụ các nhóm và job quan trọng đã trở lại.

Không được đánh dấu restored nếu chỉ tắt test, hạ gate, bỏ qua bước bảo mật hoặc chuyển tất cả lỗi thành cảnh báo. Nếu có ngoại lệ tạm thời, pipeline có thể hoạt động với suy giảm được công bố, nhưng trạng thái phải là “degraded/mitigated” cho đến khi điều kiện đầy đủ được khôi phục.

## 10. Theo dõi retry, flaky test và tái diễn

Retry có thể giúp phân biệt lỗi tạm thời với lỗi ổn định, nhưng cũng có thể che giấu nguyên nhân. Cần ghi:

- Số lần chạy đầu tiên và số lần retry.
- Kết quả của từng lần, không chỉ kết quả cuối.
- Thời gian giữa các lần retry.
- Nguyên nhân retry: chính sách tự động, người dùng hay hệ thống.
- Tỷ lệ test pass sau retry.
- Số lần cùng lỗi tái diễn trong một cửa sổ thời gian.
- Thời điểm test được quarantine và thời điểm được đưa lại gate.

Một test pass sau retry vẫn có thể là flaky. Nếu pipeline coi kết quả cuối cùng là pass mà không ghi lần đầu thất bại, chỉ số độ ổn định sẽ bị đánh giá quá tốt.

Cần phân biệt:
- **Retry phục hồi tạm thời:** dùng lại job sau lỗi runner hoặc network có bằng chứng là tạm thời.
- **Retry test:** chạy lại test để xác minh tính ổn định, phải giữ cả kết quả đầu.
- **Rerun sau sửa:** chạy trên commit hoặc cấu hình đã thay đổi.
- **Rebuild/redeploy:** tạo artifact hoặc môi trường mới để xác minh.

Theo dõi lỗi tái diễn sau khi ticket đóng. Nếu cùng nguyên nhân xuất hiện lại, xem xét chất lượng chẩn đoán, phạm vi hồi quy, điều kiện tái hiện và việc khắc phục nguyên nhân gốc.

## 11. Xác định mức độ ưu tiên và phân tích theo tác động

Không phải lỗi nào cũng cần cùng thời gian phản hồi. Một lỗi chặn toàn bộ merge hoặc ảnh hưởng pipeline phát hành quan trọng cần được xử lý khác với một cảnh báo không chặn ở nhánh thử nghiệm.

Phân loại theo:

- Số nhóm, repository và pipeline bị ảnh hưởng.
- Có chặn merge, release hoặc triển khai khẩn cấp không.
- Mức độ quan trọng của test/gate bị lỗi.
- Có workaround an toàn không.
- Có nguy cơ dữ liệu, bảo mật hoặc tính toàn vẹn không.
- Sự cố có lan rộng hoặc tăng nhanh không.
- Có phụ thuộc chung khiến nhiều nhóm cùng bị ảnh hưởng không.

Báo cáo thời gian nên phân tầng theo severity, loại lỗi, môi trường và phạm vi. Trung bình của tất cả sự cố có thể bị chi phối bởi một vài sự cố lớn và không phản ánh trải nghiệm thường ngày. Nên xem median, p75, p90 hoặc p95 cùng số lượng sự kiện.

Không so sánh trực tiếp thời gian xử lý của nhóm có sự cố đơn giản với nhóm xử lý sự cố bảo mật hoặc hạ tầng phân tán nếu không điều chỉnh theo mức phức tạp và phạm vi.

## 12. Thiết kế dữ liệu sự kiện và bảng theo dõi

Một cấu trúc dữ liệu nhất quán giúp tổng hợp thời gian mà không cần diễn giải thủ công từng ticket.

Ví dụ các trường:

| Trường | Mục đích |
|---|---|
| incident_id | Định danh sự cố gốc |
| pipeline_id / run_id / job_id | Liên kết với lần chạy và job |
| repository / service | Xác định phạm vi sản phẩm |
| commit_sha / build_version | Xác định mã và artifact |
| environment | Local, CI, integration, staging hoặc production |
| failure_category | Product, test, infra, config, dependency... |
| severity | Mức độ ảnh hưởng |
| detected_at | Thời điểm phát hiện |
| acknowledged_at | Thời điểm tiếp nhận |
| triage_started_at / triage_completed_at | Khoảng triage |
| diagnosis_confirmed_at | Thời điểm xác nhận nguyên nhân |
| fix_started_at / fix_ready_at | Khoảng sửa |
| verification_started_at / verification_passed_at | Khoảng xác minh |
| restored_at | Thời điểm khôi phục theo định nghĩa |
| closed_at | Thời điểm đóng |
| recurrence_of | Liên kết sự cố tái diễn |
| owner_team | Nhóm sở hữu xử lý |
| data_quality | Độ đầy đủ và nguồn của timestamp |

Có thể lưu sự kiện dưới dạng append-only để giữ lịch sử thay đổi. Khi ticket đổi trạng thái, tạo sự kiện mới thay vì ghi đè timestamp cũ. Điều này giúp tái dựng timeline và giải thích vì sao một sự cố được phân loại lại.

Nếu một sự cố ảnh hưởng nhiều pipeline, dùng incident ID chung và lưu danh sách run bị ảnh hưởng. Không nhân bản cùng một thời gian xử lý thành nhiều sự cố độc lập khi tính số lần incident.

## 13. Phân tích phân bố thay vì chỉ nhìn trung bình

Thời gian xử lý thường có phân bố lệch: nhiều lỗi nhỏ được giải quyết nhanh, một số ít lỗi phức tạp kéo dài rất lâu. Trung bình có thể bị kéo lên bởi các trường hợp ngoại lệ.

Nên báo cáo:

- Median để hiểu trường hợp điển hình.
- p75/p90/p95 để thấy nhóm sự cố kéo dài.
- Min/max chỉ như thông tin bổ sung, không dùng riêng để đánh giá.
- Số lượng sự cố và tỷ lệ thiếu timestamp.
- Phân bố theo loại lỗi, severity và môi trường.
- Tỷ lệ xử lý trong mục tiêu thời gian nếu tổ chức có mục tiêu đã thống nhất.

Ví dụ, median khôi phục 25 phút nhưng p90 là 4 giờ cho thấy đa số lỗi được xử lý nhanh, song vẫn có một nhóm sự cố kéo dài cần phân tích riêng. Cần đọc cùng số lượng sự kiện: p90 từ 10 sự cố có độ ổn định thống kê thấp hơn p90 từ hàng nghìn sự cố.

Không nên chỉ công bố median để che nhóm lỗi nghiêm trọng kéo dài hoặc chỉ công bố max khiến mọi cải thiện thường ngày không được nhìn thấy.

## 14. Phân biệt nguyên nhân chậm trễ và chọn hành động cải thiện

Khi một chỉ số tăng, cần tìm giai đoạn đóng góp nhiều nhất và nguyên nhân gốc.

| Dấu hiệu trong dữ liệu | Nguyên nhân có thể | Hướng cải thiện |
|---|---|---|
| TTA cao | Không rõ ai trực, cảnh báo thiếu phân tuyến | Ownership, lịch trực, routing và nội dung alert |
| Triage lâu | Ticket thiếu log, bước tái hiện hoặc phân loại | Chuẩn hóa template, tự động đính kèm artifact |
| Chẩn đoán lâu | Thiếu trace, dữ liệu khó tạo, phụ thuộc chồng chéo | Observability, correlation ID, fixture và sơ đồ phụ thuộc |
| Sửa lâu | Code coupling, test framework khó sửa, thiếu kỹ năng | Refactor có mục tiêu, tài liệu và pairing |
| Chờ build lâu | Runner thiếu, queue dài, pipeline không tối ưu | Capacity, cache, phân luồng job và concurrency |
| Xác minh lâu | Test suite lớn, môi trường không ổn định | Chọn regression theo rủi ro, cải thiện test data và môi trường |
| TTR cao dù fix nhanh | Deploy bản sửa hoặc khôi phục hạ tầng chậm | Runbook, rollback, runner dự phòng và tự động hóa phục hồi |
| Tái diễn nhiều | Chỉ xử lý triệu chứng, thiếu regression test | Phân tích nguyên nhân gốc và thêm kiểm soát hồi quy |

Không nên mặc định mọi thời gian dài đều do cá nhân làm chậm. Nhiều yếu tố nằm ở quy trình, quyền, năng lực hạ tầng, thiếu thông tin hoặc phụ thuộc ngoài. Dữ liệu dùng để tìm điểm nghẽn hệ thống, không phải bảng xếp hạng cá nhân.

## 15. Ví dụ: đo một sự cố pipeline CI

Giả sử pipeline pull request thất bại vì runner hết dung lượng đĩa. Các mốc được ghi như sau:

| Sự kiện | Thời điểm minh họa |
|---|---|
| Job đầu tiên thất bại | 09:00 |
| Alert được tạo | 09:02 |
| Platform xác nhận | 09:12 |
| Triage hoàn tất, xác định runner disk full | 09:22 |
| Bắt đầu dọn và tăng dung lượng | 09:25 |
| Runner sẵn sàng | 09:45 |
| Pipeline chạy lại bắt đầu | 09:48 |
| Gate bắt buộc hoàn tất thành công | 10:03 |
| Incident đóng sau theo dõi | 10:30 |

Từ timeline:

- Thời gian phát hiện từ job fail đến alert: 2 phút.
- Thời gian tiếp nhận từ alert đến xác nhận: 10 phút.
- Thời gian triage: 10 phút.
- Thời gian khôi phục runner: 20 phút.
- Thời gian xác minh pipeline sau khôi phục: 15 phút.
- Thời gian từ job fail đến gate hoạt động lại: 63 phút.
- Thời gian đến đóng incident: 90 phút.

Những con số này là ví dụ cách tính, không phải mục tiêu SLA. Nhóm cần quyết định mốc restored có phải lúc runner sẵn sàng hay lúc gate bắt buộc đã chạy thành công. Với pipeline, mốc sau thường phản ánh năng lực kiểm thử thực tế tốt hơn.

Sau điều tra, nhóm phát hiện artifact cũ không được dọn theo chính sách. Hành động phòng ngừa có thể là thiết lập lifecycle cleanup, cảnh báo dung lượng và runner dự phòng. Lần sau, cần đo xem các biện pháp đó có giảm tần suất và thời gian khôi phục hay không.

## 16. Ví dụ: lỗi test cần chẩn đoán, sửa và xác minh

Một integration test thanh toán thất bại ngẫu nhiên vì callback đôi khi đến sau khi assertion chạy. Nhóm ghi nhận:

- Lần thất bại đầu tiên và số lần tái diễn.
- Thời điểm QA xác nhận ticket.
- Thời gian tạo kịch bản tái hiện với callback trễ.
- Thời gian xác minh nguyên nhân là điều kiện chờ cố định.
- Thời gian sửa test để chờ trạng thái cuối có timeout rõ.
- Thời gian chạy lại nhiều lần và trên nhiều worker.
- Kết quả hồi quy để bảo đảm test vẫn phát hiện callback bị mất.

Nếu chỉ tăng timeout cho test, thời gian chạy có thể dài hơn nhưng nguyên nhân không được giải quyết. Nếu retry đến khi pass, flaky test bị che giấu. Một bản sửa tốt cần chứng minh test ổn định và vẫn phát hiện lỗi sản phẩm khi callback không đến.

Trong trường hợp này, nhóm nên báo riêng effort sửa test, elapsed time chờ môi trường và thời gian xác minh độ ổn định. Nếu lỗi phát sinh từ thiết kế xử lý callback của sản phẩm, cần tạo incident hoặc defect riêng, liên kết với test thất bại và không gộp hai công việc thành một chỉ số.

## 17. Đặt mục tiêu thời gian theo mức ảnh hưởng và năng lực thực tế

Có thể đặt mục tiêu nội bộ cho tiếp nhận, triage hoặc khôi phục, nhưng cần dựa trên lịch sử và mức quan trọng.

Ví dụ khung mục tiêu có thể gồm:

- Lỗi chặn toàn bộ pipeline phát hành: xác nhận trong khoảng thời gian ngắn theo lịch trực đã công bố.
- Sự cố runner dùng chung: có workaround hoặc runner dự phòng trong mục tiêu phục hồi đã thống nhất.
- Lỗi test đơn lẻ không chặn release: triage theo mức ưu tiên và lịch làm việc của nhóm.
- Lỗi bảo mật hoặc nguy cơ dữ liệu: theo quy trình incident/security, không dùng thời gian xử lý lỗi thông thường.

Không nên tự áp dụng một SLA giống nhau cho mọi nhóm. Mục tiêu cần xem xét số người trực, múi giờ, mức độ phụ thuộc, năng lực runner và chi phí dự phòng. Nếu mục tiêu liên tục không đạt, cần điều chỉnh quy trình hoặc năng lực; không sửa định nghĩa chỉ số để làm đẹp báo cáo.

Mục tiêu thời gian nên là công cụ cải tiến dịch vụ nội bộ. Không dùng nó để khuyến khích đóng ticket trước khi xác minh hoặc phân loại thấp sự cố nhằm đạt chỉ tiêu.

## 18. Quản lý ngoại lệ, dữ liệu thiếu và các trường hợp chưa khôi phục hoàn toàn

Có những trường hợp không thể xác định chính xác mốc thời gian hoặc pipeline chỉ được khôi phục một phần.

Ví dụ:

- Alert đến trễ hoặc mất sự kiện.
- Ticket được tạo sau khi nhóm đã bắt đầu điều tra.
- Hai hệ thống dùng đồng hồ lệch nhau.
- Pipeline chỉ hoạt động trên một runner nhưng nhóm khác vẫn bị chặn.
- Gate được tạm thời bỏ qua để unblock một thay đổi.
- Workaround khôi phục hoạt động nhưng nguyên nhân gốc chưa được sửa.

Trong báo cáo, cần:

- Đánh dấu timestamp thiếu hoặc không đáng tin.
- Nêu nguồn và mức độ chắc chắn của mốc thời gian.
- Phân biệt restored, mitigated, degraded và resolved.
- Ghi rõ gate nào đang bị bỏ qua hoặc thay thế.
- Chỉ định chủ sở hữu và thời hạn cho hành động còn mở.
- Không đưa các trường hợp thiếu dữ liệu vào phân vị mà không công bố quy tắc xử lý.
- Giữ liên kết giữa workaround, incident gốc và công việc khắc phục triệt để.

Một sự cố được giảm thiểu chưa chắc đã resolved. Trạng thái phải phản ánh khả năng phục vụ thực tế và rủi ro còn lại.

## 19. Dùng số liệu để cải thiện, không tạo động cơ sai lệch

Khi thời gian xử lý trở thành KPI, nhóm có thể vô tình tối ưu cách ghi nhận thay vì chất lượng thực tế. Các hành vi không mong muốn gồm:

- Đóng ticket sớm rồi mở lại khi lỗi tái diễn.
- Gán lỗi cho hạ tầng để giảm thời gian sửa lỗi sản phẩm.
- Tăng retry để pipeline xanh mà không xử lý flaky test.
- Bỏ qua gate hoặc giảm phạm vi kiểm tra để đạt mục tiêu thời gian.
- Không ghi nhận sự cố nhỏ hoặc chỉ tạo ticket khi đã xử lý xong.
- Chia một incident lớn thành nhiều ticket nhỏ để cải thiện số liệu.

Để giảm các động cơ này:

- Định nghĩa mốc bắt đầu/kết thúc và trạng thái restored rõ ràng.
- Theo dõi tỷ lệ tái mở và tái diễn cùng thời gian xử lý.
- Đối chiếu dữ liệu CI tự động với ticket và incident.
- Báo cáo cả chất lượng xác minh và số lần retry.
- Phân tích theo loại lỗi và mức ảnh hưởng.
- Dùng số liệu cho cải tiến nhóm và hệ thống, không xếp hạng cá nhân.
- Rà soát mẫu sự cố đóng nhanh bất thường hoặc dữ liệu thiếu.

Thời gian thấp chỉ là kết quả tốt khi vấn đề được xử lý đúng, bằng chứng đầy đủ và không tạo rủi ro mới.

## 20. Quy trình đo lường và cải thiện vòng đời xử lý pipeline

Có thể triển khai theo các bước:

1. **Định nghĩa phạm vi sự kiện:** xác định pipeline, job, gate và loại lỗi được đo.
2. **Chuẩn hóa trạng thái:** thống nhất detected, acknowledged, triaged, diagnosing, fixing, verifying, restored và resolved.
3. **Ghi timestamp và ID:** liên kết run, commit, incident, ticket, môi trường và nhóm sở hữu.
4. **Phân loại nguyên nhân:** product, test, infrastructure, configuration, dependency hoặc tooling.
5. **Tính các khoảng thời gian:** elapsed, effort, waiting, triage, diagnose, fix, verify và restore.
6. **Kiểm tra chất lượng dữ liệu:** timestamp thiếu, đồng hồ lệch, incident trùng và trạng thái cập nhật muộn.
7. **Phân tích phân bố:** median, p90/p95, số lượng và phân nhóm theo severity.
8. **Tìm giai đoạn gây chậm:** tiếp nhận, chẩn đoán, chờ build, sửa hay xác minh.
9. **Chọn hành động:** cải thiện ownership, observability, runner, test isolation, automation hoặc runbook.
10. **Đo lại và rà soát:** so sánh trước/sau, theo dõi tái diễn và cập nhật mục tiêu.

~~~mermaid
flowchart TD
    A["Pipeline/job phát sinh lỗi"] --> B["Ghi sự kiện và timestamp"]
    B --> C["Tạo incident ID, liên kết run/commit"]
    C --> D["Tiếp nhận và triage"]
    D --> E["Chẩn đoán nguyên nhân"]
    E --> F["Sửa hoặc áp dụng workaround"]
    F --> G["Chạy xác minh và hồi quy"]
    G --> H{"Gate bắt buộc hoạt động tin cậy?"}
    H -->|Chưa| E
    H -->|Có, còn theo dõi| I["Đánh dấu restored và theo dõi"]
    I --> J{"Có tái diễn?"}
    J -->|Có| E
    J -->|Không| K["Đóng sự cố và tổng hợp thời gian"]
    K --> L["Phân tích điểm nghẽn và cải tiến"]
~~~

## 21. Checklist đo thời gian điều tra, sửa lỗi và khôi phục pipeline

Trước khi đưa dashboard hoặc báo cáo thời gian vào sử dụng, hãy kiểm tra:

- Phạm vi pipeline, job và sự kiện được đo đã rõ chưa?
- Các giai đoạn phát hiện, tiếp nhận, triage, chẩn đoán, sửa, xác minh và khôi phục có định nghĩa thống nhất chưa?
- Có phân biệt elapsed time, effort và waiting time không?
- Timestamp có nguồn, múi giờ và độ tin cậy rõ không?
- Run ID, commit, incident ID, môi trường và owner team có được liên kết không?
- Lỗi sản phẩm, test, flaky, cấu hình, hạ tầng và phụ thuộc có được phân loại riêng không?
- Thời gian khôi phục có yêu cầu gate bắt buộc hoạt động lại và bằng chứng ổn định không?
- Retry, workaround, quarantine và ngoại lệ có được ghi nhận đầy đủ không?
- Dữ liệu thiếu, sự cố trùng và tái diễn có quy tắc xử lý không?
- Báo cáo có median, phân vị, số mẫu và phân nhóm theo mức ảnh hưởng không?
- Có đo thời gian chờ và effort để tìm đúng điểm nghẽn không?
- Hành động cải thiện có chủ sở hữu và cách đo lại không?
- Chỉ số có được dùng để cải thiện hệ thống thay vì tạo áp lực đóng ticket sớm không?

Đo thời gian điều tra, sửa lỗi và khôi phục pipeline giúp nhóm nhìn thấy chính xác nơi vòng phản hồi bị kéo dài. Khi các mốc được định nghĩa rõ, thời gian làm việc được tách khỏi thời gian chờ, nguyên nhân được phân loại và trạng thái khôi phục gắn với bằng chứng, nhóm có thể ưu tiên đúng cải tiến. Mục tiêu cuối cùng là khôi phục năng lực kiểm thử nhanh và đáng tin cậy, đồng thời giảm khả năng cùng một sự cố quay lại.

