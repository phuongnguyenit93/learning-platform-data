# Đánh giá khả năng bảo trì, triển khai và quan sát hệ thống

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, chất lượng của một hệ thống không chỉ thể hiện qua việc chức năng trả về kết quả đúng. Nhóm còn cần đánh giá liệu phần mềm có thể được hiểu, sửa đổi và mở rộng với chi phí hợp lý; có thể triển khai lặp lại, an toàn trong các môi trường mục tiêu; và có cung cấp đủ tín hiệu để người vận hành nhận biết, điều tra hành vi bất thường hay không. Ba khía cạnh này thường được gọi là **khả năng bảo trì** (maintainability), **khả năng triển khai** (deployability) và **khả năng quan sát** (observability).

Ba khía cạnh có liên hệ chặt chẽ. Một hệ thống khó bảo trì khiến việc sửa lỗi hoặc thay đổi cấu hình triển khai trở nên chậm và rủi ro. Một quy trình triển khai thiếu kiểm soát có thể đưa lỗi vào production dù mã nguồn đã được kiểm thử. Một hệ thống thiếu khả năng quan sát khiến nhóm không biết thay đổi có gây ảnh hưởng hay không, hoặc mất nhiều thời gian để tìm nguyên nhân khi có sự cố. Vì vậy, chiến lược kiểm thử cần tạo bằng chứng cho cả ba khía cạnh thay vì chỉ kiểm tra kết quả chức năng.

## 1. Hiểu ba khía cạnh chất lượng

### Khả năng bảo trì (maintainability)

Khả năng bảo trì là mức độ dễ dàng mà sản phẩm có thể được phân tích, sửa lỗi, điều chỉnh, kiểm thử, mở rộng hoặc tái sử dụng khi yêu cầu và môi trường thay đổi. Trong các mô hình chất lượng phần mềm như ISO/IEC 25010, maintainability bao gồm những đặc tính như tính mô-đun, khả năng tái sử dụng, khả năng phân tích, khả năng sửa đổi và khả năng kiểm thử.

Những câu hỏi cần trả lời:

- Khi có lỗi, nhóm có xác định được thành phần và nguyên nhân liên quan không?
- Một thay đổi cục bộ có gây ảnh hưởng ngoài dự kiến đến các thành phần khác không?
- Mã nguồn, kiến trúc, cấu hình và tài liệu có đủ rõ để người khác tiếp tục làm việc không?
- Có thể kiểm thử các thành phần độc lập và phát hiện hồi quy với chi phí hợp lý không?
- Việc nâng cấp thư viện, thay đổi schema hoặc loại bỏ thành phần cũ có được kiểm soát không?

Khả năng bảo trì không đồng nghĩa với việc mã nguồn ngắn hoặc có nhiều comment. Điều quan trọng là cấu trúc và thiết kế giúp người có kỹ năng phù hợp hiểu được hành vi, xác định tác động và thực hiện thay đổi an toàn.

### Khả năng triển khai (deployability)

Khả năng triển khai là mức độ mà một phiên bản phần mềm có thể được đóng gói, cấu hình, đưa vào môi trường mục tiêu và cập nhật theo quy trình lặp lại, có thể kiểm soát và có thể khôi phục khi cần.

Những câu hỏi cần trả lời:

- Có thể tạo artifact xác định được nguồn gốc và phiên bản không?
- Quy trình triển khai có thể lặp lại và tự động hóa ở mức phù hợp không?
- Cấu hình, secret, migration và phụ thuộc có được quản lý đúng không?
- Có thể triển khai theo từng giai đoạn, kiểm tra sau triển khai và dừng khi có tín hiệu xấu không?
- Nếu phát hành thất bại, có thể rollback, roll-forward hoặc khôi phục trạng thái dữ liệu an toàn không?

Deployability không chỉ là tốc độ deploy. Một quy trình triển khai nhanh nhưng phụ thuộc thao tác thủ công không được ghi nhận, thiếu kiểm tra hoặc không có phương án khôi phục có thể có rủi ro cao.

### Khả năng quan sát (observability)

Khả năng quan sát là mức độ mà nhóm có thể suy luận trạng thái và hành vi bên trong của hệ thống từ các tín hiệu mà hệ thống phát ra. Trong hệ thống phần mềm, các tín hiệu phổ biến là metrics, logs và traces, kết hợp với dashboard, cảnh báo và thông tin ngữ cảnh.

Những câu hỏi cần trả lời:

- Nhóm có biết người dùng đang gặp lỗi hoặc chậm ở luồng nào không?
- Có thể liên kết một yêu cầu xuyên qua nhiều service không?
- Có đủ ngữ cảnh để phân biệt lỗi ứng dụng, dữ liệu, cấu hình và phụ thuộc không?
- Cảnh báo có phát hiện vấn đề có ý nghĩa và đến đúng người xử lý không?
- Dữ liệu quan sát có bảo vệ thông tin nhạy cảm và có chi phí hợp lý không?

Observability không đơn giản là cài một công cụ logging hoặc tạo nhiều dashboard. Hệ thống cần phát ra tín hiệu có ý nghĩa, nhất quán và đủ ngữ cảnh để trả lời các câu hỏi vận hành.

## 2. So sánh và mối liên hệ giữa ba khía cạnh

| Khía cạnh | Trọng tâm | Bằng chứng điển hình | Rủi ro nếu yếu |
|---|---|---|---|
| Maintainability | Hiểu, sửa đổi, kiểm thử và mở rộng phần mềm | Review kiến trúc/mã nguồn, phân tích tĩnh, cấu trúc module, thời gian xử lý thay đổi, độ ổn định của test | Sửa lỗi chậm, thay đổi gây hồi quy, phụ thuộc vào một vài cá nhân |
| Deployability | Đóng gói, cấu hình, phát hành và khôi phục phiên bản | Pipeline, artifact, deployment record, migration test, rollout/rollback rehearsal | Phát hành thất bại, cấu hình sai, downtime, dữ liệu không tương thích |
| Observability | Nhận biết, định vị và hiểu hành vi hệ thống | Metrics, logs, traces, dashboard, alert test, correlation ID, runbook | Phát hiện muộn, điều tra lâu, không biết tác động của thay đổi |

Ba khía cạnh tác động qua lại. Thiết kế có mô-đun rõ ràng thường giúp triển khai từng phần và gắn tín hiệu quan sát theo service dễ hơn. Pipeline triển khai tốt giúp đưa thay đổi quan sát được vào môi trường với rủi ro thấp hơn. Observability tốt cung cấp dữ liệu để phát hiện thành phần khó bảo trì, điểm nghẽn và lỗi thường xuyên sau phát hành.

Không nên gộp chúng thành một điểm số duy nhất mà không có tiêu chí riêng. Một hệ thống có pipeline triển khai tự động vẫn có thể khó bảo trì; một hệ thống có log phong phú vẫn có thể triển khai nguy hiểm; và mã nguồn dễ bảo trì không đảm bảo hệ thống production có đủ telemetry.

## 3. Đánh giá khả năng bảo trì

Kiểm thử khả năng bảo trì cần kết hợp đánh giá cấu trúc kỹ thuật với bằng chứng từ các thay đổi thực tế. Một số đặc tính quan trọng gồm:

### Tính mô-đun và mức độ kết dính/phụ thuộc

Các thành phần nên có trách nhiệm rõ ràng, giao diện được xác định và phụ thuộc có thể hiểu được. Khi một module thay đổi, nhóm cần biết phạm vi ảnh hưởng và kiểm tra được các phần liên quan.

Có thể đánh giá bằng cách:

- Review ranh giới module, trách nhiệm và luồng phụ thuộc.
- Kiểm tra mức độ phụ thuộc vòng, coupling quá chặt hoặc thành phần có quá nhiều trách nhiệm.
- Xem xét API nội bộ và hợp đồng giữa các module.
- Kiểm tra liệu một thành phần có thể được thay thế hoặc kiểm thử độc lập không.
- Đánh giá mức ảnh hưởng của thay đổi nhỏ qua ma trận phụ thuộc hoặc phân tích tác động.

Không có một cấu trúc module duy nhất phù hợp mọi sản phẩm. Điều cần kiểm tra là ranh giới có phản ánh đúng miền nghiệp vụ, giúp kiểm soát thay đổi và không tạo ra sự phức tạp không cần thiết hay không.

### Khả năng phân tích và chẩn đoán

Khi có lỗi, người bảo trì cần tìm được nơi phát sinh và hiểu điều kiện gây lỗi. Bằng chứng có thể gồm:

- Cấu trúc mã nguồn, tên gọi, tài liệu thiết kế và quyết định kiến trúc.
- Thông báo lỗi rõ ràng, log có ngữ cảnh và trace phù hợp.
- Quy trình tái hiện lỗi và bộ dữ liệu kiểm thử có thể tái lập.
- Thời gian trung bình để xác định nguyên nhân hoặc phân loại lỗi.
- Mức độ mà một người mới có thể thiết lập môi trường và chạy bộ test cần thiết.

Thời gian điều tra không chỉ phụ thuộc vào mã nguồn. Thiếu log, thiếu dữ liệu hoặc môi trường không tái lập được cũng làm giảm khả năng phân tích.

### Khả năng sửa đổi và mở rộng

Một thay đổi nên có phạm vi dễ dự đoán. Nhóm có thể chọn một số thay đổi đại diện, ví dụ thêm một trường API, bổ sung quy tắc nghiệp vụ hoặc nâng cấp thư viện, rồi đánh giá:

- Có phải sửa quá nhiều thành phần không liên quan không?
- Có phải thay đổi nhiều hợp đồng hoặc cấu hình không cần thiết không?
- Test có giúp phát hiện hồi quy ở các bên phụ thuộc không?
- Có thể triển khai thay đổi theo giai đoạn và giữ tương thích không?
- Thay đổi có làm tăng nợ kỹ thuật hoặc chi phí vận hành đáng kể không?

Một phép thử thay đổi (changeability assessment) có thể dùng một yêu cầu mẫu để đánh giá thời gian, số thành phần bị ảnh hưởng, số test cần sửa và các vấn đề phát sinh. Kết quả không nên được hiểu là benchmark tuyệt đối; nó giúp so sánh xu hướng và phát hiện điểm nghẽn trong cùng bối cảnh.

### Khả năng kiểm thử và tự động hóa

Phần mềm dễ kiểm thử khi hành vi có thể quan sát, phụ thuộc có thể kiểm soát, dữ liệu có thể chuẩn bị và trạng thái có thể tái lập. Có thể xem xét:

- Thành phần có thể chạy test độc lập không?
- Có thể thay thế phụ thuộc bên ngoài bằng test double khi phù hợp không?
- Có thể thiết lập trạng thái đầu vào và dọn dữ liệu sau test không?
- Test có ổn định, dễ chẩn đoán và không phụ thuộc vào thứ tự chạy không?
- Có thể kiểm tra các trường hợp lỗi mà không gây tác dụng phụ khó kiểm soát không?

Độ bao phủ mã nguồn có thể là một tín hiệu, nhưng không chứng minh test có chất lượng hoặc hệ thống dễ bảo trì. Cần xem test có kiểm tra đúng quy tắc, có khả năng phát hiện lỗi và có chi phí bảo trì hợp lý hay không.

### Chỉ số hỗ trợ đánh giá maintainability

Nhóm có thể theo dõi một số chỉ số như:

- Thời gian trung vị từ lúc bắt đầu thay đổi đến khi hoàn tất và được kiểm chứng.
- Thời gian trung vị để xác định nguyên nhân của lỗi.
- Tỷ lệ thay đổi gây hồi quy hoặc phải rollback.
- Số lượng phụ thuộc vòng, module có trách nhiệm quá rộng hoặc cảnh báo phân tích tĩnh nghiêm trọng.
- Tỷ lệ test flaky và thời gian điều tra test thất bại.
- Mức độ cập nhật của tài liệu và khả năng thiết lập môi trường theo hướng dẫn.

Các chỉ số này cần được đọc cùng quy mô thay đổi, mức độ phức tạp và rủi ro. Ví dụ, thời gian sửa lỗi ngắn không nhất thiết có nghĩa maintainability tốt nếu nhóm bỏ qua kiểm thử hoặc tạo nhiều lỗi về sau.

## 4. Đánh giá khả năng triển khai

Deployability cần được kiểm tra từ lúc tạo artifact đến khi phiên bản chạy ổn định trong môi trường mục tiêu.

### Tính lặp lại và tự động hóa

Quy trình triển khai cần có các bước xác định, có thể lặp lại và ghi nhận kết quả. Nhóm nên kiểm tra:

- Cùng một artifact có thể được đưa qua các môi trường mà không phải build lại tùy tiện không?
- Pipeline có kiểm tra chất lượng, bảo mật, cấu hình và điều kiện trước triển khai không?
- Thao tác thủ công có được giới hạn, ghi nhận và kiểm soát quyền không?
- Khi một bước thất bại, pipeline có dừng đúng cách và giữ được bằng chứng không?
- Có thể xác định ai triển khai, phiên bản nào, khi nào và với cấu hình nào không?

Infrastructure as Code và cấu hình có kiểm soát giúp giảm sai lệch môi trường, nhưng bản thân việc dùng IaC không chứng minh deployability. Cần kiểm tra khả năng tạo, cập nhật và khôi phục hạ tầng theo quy trình thực tế.

### Quản lý artifact và cấu hình

Artifact cần có định danh phiên bản, nguồn build và tính toàn vẹn. Cấu hình theo môi trường nên được tách khỏi mã nguồn, có kiểm soát thay đổi và không chứa secret dạng rõ. Nhóm cần kiểm tra:

- Artifact triển khai đúng với artifact đã kiểm thử và phê duyệt.
- Cấu hình bắt buộc có đủ và giá trị hợp lệ.
- Secret, token và chứng thư được lấy từ hệ thống quản lý bí mật phù hợp.
- Cấu hình thiếu hoặc sai tạo lỗi rõ ràng và không làm hệ thống chạy ở trạng thái nguy hiểm.
- Có thể xác định cấu hình thực tế đang được sử dụng khi điều tra sự cố.

### Migration và tương thích dữ liệu

Thay đổi schema hoặc dữ liệu có thể khiến phiên bản mới và phiên bản cũ không tương thích trong giai đoạn triển khai. Cần kiểm tra:

- Migration chạy đúng trên dữ liệu đại diện và dữ liệu lớn.
- Migration có thể chạy lại an toàn hoặc phát hiện trạng thái đã hoàn tất theo thiết kế.
- Phiên bản cũ có thể tiếp tục hoạt động trong thời gian rollout nếu kiến trúc yêu cầu.
- Có phương án khôi phục hoặc roll-forward nếu migration thất bại.
- Dữ liệu sau migration được đối soát và không mất hoặc nhân đôi bản ghi.

Với thay đổi có nguy cơ phá vỡ, chiến lược expand-and-contract thường giúp duy trì tương thích: mở rộng schema trước, triển khai ứng dụng có thể đọc/ghi cả hai dạng, chuyển dần luồng dữ liệu, sau đó mới loại bỏ cấu trúc cũ khi không còn phụ thuộc.

### Rollout, canary và kiểm tra sau triển khai

Deployability không kết thúc khi container hoặc tiến trình khởi động. Cần kiểm tra khả năng:

- Triển khai theo từng vùng, nhóm người dùng hoặc tỷ lệ lưu lượng.
- Dùng health/readiness và smoke test để xác nhận chức năng trọng yếu.
- Theo dõi lỗi, độ trễ và chỉ số nghiệp vụ trong cửa sổ quan sát.
- Dừng rollout khi vượt ngưỡng hoặc xuất hiện lỗi nghiêm trọng.
- Tắt feature flag, chuyển lưu lượng, rollback hoặc roll-forward theo phương án đã thử.
- Xác nhận trạng thái dữ liệu và luồng nghiệp vụ sau khôi phục.

Rollback ứng dụng không tự động khôi phục dữ liệu đã thay đổi. Mỗi release cần đánh giá riêng tương thích schema, message, cache và tác dụng phụ bên ngoài.

### Chỉ số hỗ trợ đánh giá deployability

Nhóm có thể theo dõi:

- Tần suất triển khai và thời gian từ commit đến production.
- Tỷ lệ triển khai thành công.
- Tỷ lệ triển khai gây sự cố hoặc cần rollback/hotfix.
- Thời gian khôi phục dịch vụ sau triển khai thất bại.
- Tỷ lệ triển khai cần thao tác thủ công hoặc can thiệp ngoài quy trình.
- Tỷ lệ migration thành công và số lần cần khôi phục dữ liệu.

Không nên tối ưu tần suất triển khai bằng cách giảm kiểm soát chất lượng. Các chỉ số cần được xem cùng mức độ ảnh hưởng, thời gian phục hồi và độ ổn định của dịch vụ.

## 5. Đánh giá khả năng quan sát

Observability cần giúp nhóm phát hiện điều bất thường, xác định tác động và thu thập đủ ngữ cảnh để điều tra. Ba loại tín hiệu phổ biến bổ sung cho nhau.

### Metrics — chỉ số tổng hợp

Metrics cho thấy xu hướng và mức độ thay đổi theo thời gian. Những nhóm chỉ số thường cần xem xét:

- **Lưu lượng:** số yêu cầu, thông điệp, giao dịch hoặc tác vụ.
- **Lỗi:** tỷ lệ lỗi, mã lỗi, timeout, retry và lỗi nghiệp vụ.
- **Độ trễ:** p50, p95, p99 hoặc thời gian xử lý theo từng giai đoạn.
- **Tài nguyên:** CPU, bộ nhớ, kết nối, dung lượng đĩa, hàng đợi và giới hạn quota.
- **Kết quả nghiệp vụ:** tỷ lệ thanh toán thành công, tỷ lệ hoàn tất tác vụ, số đơn bị treo hoặc giao dịch cần đối soát.

Không nên chỉ theo dõi CPU và bộ nhớ. Một service có thể sử dụng tài nguyên bình thường nhưng người dùng vẫn không hoàn tất được tác vụ do lỗi nghiệp vụ hoặc phụ thuộc bên ngoài.

### Logs — nhật ký có ngữ cảnh

Log giúp giải thích sự kiện cụ thể. Log có cấu trúc nên bao gồm thông tin phù hợp như timestamp, service, môi trường, phiên bản, severity, error code và correlation ID. Cần xác định mức log cho các sự kiện thành công, cảnh báo và lỗi để tránh vừa thiếu thông tin vừa tạo quá nhiều dữ liệu.

Log không nên chứa mật khẩu, token, khóa, dữ liệu thanh toán hoặc thông tin cá nhân không cần thiết. Cần kiểm tra việc che dữ liệu, quyền truy cập, thời gian lưu và khả năng tìm kiếm theo mã giao dịch.

### Traces — dấu vết qua nhiều thành phần

Trace cho thấy một yêu cầu đi qua những thành phần nào và thời gian được tiêu tốn ở mỗi bước. Với hệ thống phân tán, trace giúp phân biệt độ trễ ở gateway, service nội bộ, cơ sở dữ liệu hay dịch vụ bên ngoài.

Nhóm nên kiểm tra:

- Trace context được truyền qua các ranh giới service và message khi phù hợp.
- Span có tên và thuộc tính đủ rõ để hiểu luồng.
- Trace có liên kết với log và mã giao dịch.
- Lỗi và giao dịch quan trọng có cơ hội được ghi nhận dù đang dùng sampling.
- Dữ liệu nhạy cảm không bị đưa vào span attributes.

### Correlation ID và ngữ cảnh nghiệp vụ

Correlation ID giúp liên kết các log, message và trace thuộc cùng một quy trình. Với giao dịch quan trọng, cần xác định mã nào được tạo ở đâu, truyền qua thành phần nào và có được giữ nguyên khi retry hoặc xử lý bất đồng bộ không.

Không nên dùng ID của người dùng hoặc dữ liệu cá nhân làm nhãn metric có độ phân biệt cao. Dùng mã tương quan trong log/trace có kiểm soát và tuân thủ chính sách dữ liệu.

### Dashboard và cảnh báo

Dashboard nên trả lời các câu hỏi vận hành cụ thể: dịch vụ có sẵn sàng không, luồng quan trọng có lỗi không, độ trễ thay đổi ra sao, phụ thuộc nào đang gặp vấn đề và phiên bản nào bị ảnh hưởng. Tránh tạo dashboard chỉ để hiển thị thật nhiều biểu đồ mà không hỗ trợ quyết định.

Cảnh báo cần gắn với hành động. Một cảnh báo tốt xác định điều kiện, mức độ, tác động có thể có, người nhận và runbook liên quan. Cần kiểm tra toàn bộ đường đi của cảnh báo, từ metric hoặc log rule đến kênh thông báo và xác nhận của người trực.

### Chỉ số hỗ trợ đánh giá observability

Có thể theo dõi:

- Tỷ lệ luồng nghiệp vụ trọng yếu có metric và mã tương quan.
- Tỷ lệ cảnh báo quan trọng được kiểm tra định kỳ và có người nhận.
- Thời gian phát hiện (MTTD) và thời gian xác định nguyên nhân.
- Tỷ lệ sự cố có đủ log/trace để truy vết mà không cần tái hiện production.
- Tỷ lệ cảnh báo giả hoặc cảnh báo không dẫn đến hành động.
- Mức độ đầy đủ của telemetry trên các service và phụ thuộc quan trọng.

Các con số cần được diễn giải theo loại dịch vụ và cách đo. MTTD thấp không có nghĩa mọi lỗi đều được phát hiện; lỗi không có tín hiệu có thể không xuất hiện trong thống kê. Cần kết hợp diễn tập cảnh báo, review sự cố và kiểm tra các luồng quan trọng.

## 6. Thiết kế chiến lược kiểm thử cho ba khía cạnh

Một chiến lược kiểm thử nên chuyển từng thuộc tính thành mục tiêu, điều kiện, phép kiểm tra và bằng chứng cụ thể.

| Khía cạnh | Mục tiêu kiểm thử | Phương pháp có thể dùng | Bằng chứng |
|---|---|---|---|
| Maintainability | Thành phần có thể hiểu, sửa và kiểm thử độc lập với rủi ro hợp lý | Review kiến trúc/mã, phân tích tĩnh, kiểm tra phụ thuộc, testability assessment, thử một thay đổi đại diện | Báo cáo review, dependency graph, kết quả test, thời gian và phạm vi thay đổi |
| Deployability | Phiên bản có thể triển khai lặp lại, đúng cấu hình và khôi phục an toàn | Pipeline test, deploy rehearsal, configuration validation, migration test, canary/rollback rehearsal | Log pipeline, release record, kết quả smoke, migration/restore và quyết định rollout |
| Observability | Lỗi và suy giảm quan trọng có thể phát hiện, định vị và điều tra | Kiểm tra telemetry, synthetic monitoring, alert test, fault injection có kiểm soát, diễn tập incident | Metrics, logs, traces, cảnh báo nhận được, thời gian phát hiện và runbook result |

### Đưa kiểm tra vào các giai đoạn phát triển

**Trong thiết kế:** review ranh giới module, hợp đồng, chiến lược cấu hình, migration, telemetry và cách xử lý lỗi. Xác định các yêu cầu vận hành như SLI/SLO, RTO/RPO và quyền truy cập.

**Trong phát triển:** chạy phân tích tĩnh, kiểm thử đơn vị và tích hợp; kiểm tra logging, metric và trace ở các luồng trọng yếu; giữ cấu hình và pipeline dưới dạng có thể review.

**Trong CI/CD:** kiểm tra build, artifact, dependency, cấu hình, schema compatibility, migration và smoke test. Pipeline nên lưu bằng chứng, dừng khi có điều kiện chặn và cung cấp thông tin để điều tra.

**Trước phát hành:** diễn tập triển khai, canary, rollback/roll-forward, backup/restore, cảnh báo và runbook. Xác nhận người chịu trách nhiệm và điều kiện Go/No-Go.

**Sau phát hành:** theo dõi metrics, logs, traces, lỗi nghiệp vụ và phản hồi người dùng; dùng sự cố để cập nhật test, kiến trúc, quy trình triển khai và cảnh báo.

## 7. Quy trình đánh giá thực tế

Có thể tổ chức một đợt đánh giá ba khía cạnh theo các bước sau:

### Bước 1: Xác định phạm vi và rủi ro

Chọn service, phiên bản, luồng nghiệp vụ, môi trường và thay đổi cần đánh giá. Xác định rủi ro nếu khó bảo trì, triển khai thất bại hoặc không phát hiện được lỗi. Ưu tiên các luồng có tác động lớn đến dữ liệu, tiền, an toàn, bảo mật và hoạt động người dùng.

### Bước 2: Đặt tiêu chí đo được

Với mỗi khía cạnh, xác định mục tiêu, ngưỡng chấp nhận, điều kiện thử, người chịu trách nhiệm và bằng chứng. Ví dụ, deploy phải dùng cùng artifact đã kiểm thử; migration phải có thể khôi phục theo kế hoạch; cảnh báo lỗi thanh toán phải đến đúng nhóm trực trong giới hạn thời gian đã thống nhất.

### Bước 3: Thu thập baseline

Ghi nhận cấu trúc hiện tại, thời gian thay đổi, tỷ lệ lỗi triển khai, thời gian phục hồi, độ đầy đủ telemetry và các giới hạn đã biết. Baseline giúp so sánh sau cải tiến, nhưng cần ghi rõ phiên bản, tải và môi trường.

### Bước 4: Thực hiện review và thử nghiệm

Kết hợp review kỹ thuật với thử nghiệm thực tế. Đọc cấu trúc mã và dependency; thực hiện một thay đổi đại diện; chạy pipeline từ build đến deploy; thử migration và phương án khôi phục; tạo tín hiệu lỗi có kiểm soát để xác nhận dashboard, cảnh báo và trace.

### Bước 5: Phân tích kết quả và khoảng trống

Phân biệt lỗi của sản phẩm, lỗi quy trình, thiếu công cụ, thiếu tài liệu và thiếu kỹ năng. Đánh giá ảnh hưởng, tần suất, khả năng phát hiện và chi phí khắc phục. Không suy ra rằng một thuộc tính đạt chỉ vì công cụ đã được cài đặt.

### Bước 6: Lập kế hoạch cải thiện và quyết định

Ghi hành động, người phụ trách, thời hạn, bằng chứng cần có và điều kiện hoàn tất. Với rủi ro nghiêm trọng hoặc tiêu chí bắt buộc chưa đạt, chuyển đến người có thẩm quyền để quyết định dừng, giới hạn rollout hoặc chấp nhận ngoại lệ theo chính sách.

### Bước 7: Kiểm tra lại sau cải thiện

Chạy lại phép kiểm tra tương ứng và xác nhận thay đổi có cải thiện kết quả mà không tạo tác dụng phụ. Cập nhật baseline, tài liệu, dashboard, test và runbook khi cần.

## 8. Ví dụ xuyên suốt: dịch vụ đặt hàng trực tuyến

Giả sử một nền tảng thương mại điện tử có Order Service, Payment Service, Inventory Service và Notification Service. Nhóm chuẩn bị phát hành thay đổi lớn cho luồng thanh toán và cần đánh giá maintainability, deployability, observability.

### Khả năng bảo trì

Nhóm review ranh giới giữa Order và Payment, kiểm tra phụ thuộc vòng, xác định các adapter tích hợp và đánh giá khả năng test độc lập. Một thay đổi đại diện là bổ sung phương thức thanh toán mới. Nhóm đo số thành phần cần sửa, xác định hợp đồng bị ảnh hưởng, chạy hồi quy và ghi nhận nơi phải thay đổi ngoài dự kiến.

Nếu việc thêm phương thức mới đòi hỏi sửa nhiều module không liên quan, logic thanh toán bị phân tán hoặc test chỉ chạy được với toàn bộ hệ thống, đó là tín hiệu cần xem lại thiết kế. Không nên chỉ tối ưu số file thay đổi; cần đánh giá mức độ phụ thuộc và rủi ro thực tế.

### Khả năng triển khai

Pipeline tạo artifact có định danh, chạy test, kiểm tra dependency và schema, sau đó triển khai lên staging. Nhóm xác nhận cấu hình Payment Service, secret sandbox, migration và tương thích với phiên bản Order Service đang chạy. Canary được bật cho nhóm nhỏ; smoke test xác nhận thanh toán thử và trạng thái đơn hàng. Điều kiện dừng dựa trên tỷ lệ lỗi, độ trễ và giao dịch cần đối soát.

Nhóm diễn tập rollback ứng dụng và xác nhận schema vẫn tương thích với phiên bản trước. Nếu migration không thể đảo ngược an toàn, kế hoạch roll-forward hoặc phục hồi dữ liệu phải được xác định trước khi phát hành.

### Khả năng quan sát

Mỗi giao dịch có correlation ID xuyên Order, Payment và Notification. Dashboard hiển thị số yêu cầu, tỷ lệ thanh toán thành công, lỗi theo mã, p95 latency, webhook retry và số giao dịch ở trạng thái chờ quá lâu. Trace cho biết thời gian ở từng service; log có event ID và mã lỗi nhưng không ghi thông tin thẻ hoặc token.

Nhóm tạo một tình huống timeout có kiểm soát, xác nhận cảnh báo được kích hoạt, người trực nhận được và trace cho phép xác định Payment Service là phụ thuộc chậm. Nếu dashboard chỉ hiển thị CPU và số request tổng thể, nhóm chưa có đủ bằng chứng để phát hiện lỗi nghiệp vụ hoặc điều tra một giao dịch cụ thể.

### Đánh giá tổng hợp

| Khía cạnh | Kết quả giả định | Khoảng trống | Hành động |
|---|---|---|---|
| Maintainability | Unit và contract test chạy độc lập; adapter có ranh giới rõ | Một số logic retry còn nằm rải rác | Tập trung chính sách retry, bổ sung test trạng thái và tài liệu |
| Deployability | Pipeline lặp lại, canary và smoke test hoạt động | Rollback schema chưa được diễn tập | Thử chiến lược expand-and-contract và kiểm tra dữ liệu phục hồi |
| Observability | Có metric, log, trace và correlation ID | Chưa cảnh báo giao dịch chờ quá lâu | Bổ sung SLI, ngưỡng cảnh báo và runbook điều tra |

Nhóm dùng các khoảng trống này để quyết định điều kiện phát hành và lập kế hoạch cải thiện. Việc một khía cạnh đạt không bù cho rủi ro nghiêm trọng ở khía cạnh khác.

## 9. Những sai lầm thường gặp

**Đánh giá maintainability chỉ bằng style hoặc số dòng code.** Mã nguồn đúng định dạng vẫn có thể phụ thuộc chặt, khó kiểm thử và khó thay đổi. Cần review kiến trúc, phụ thuộc, testability và tác động của thay đổi thực tế.

**Coi nhiều comment là dễ bảo trì.** Comment lỗi thời có thể gây hiểu nhầm. Ưu tiên cấu trúc, tên gọi, hợp đồng và tài liệu quyết định kiến trúc rõ ràng; comment nên giải thích lý do hoặc ràng buộc khó suy ra từ mã.

**Coi deploy thành công là deployability tốt.** Một lần triển khai thành công chưa chứng minh quy trình có thể lặp lại, xử lý lỗi hoặc khôi phục. Cần diễn tập nhiều tình huống và ghi nhận điều kiện môi trường.

**Build lại artifact cho từng môi trường.** Việc tạo artifact khác nhau sau khi test có thể làm production chạy thứ chưa được kiểm chứng. Nên thúc đẩy artifact bất biến qua các môi trường và quản lý cấu hình riêng.

**Chỉ kiểm tra rollback mã nguồn.** Schema, dữ liệu, message và tác dụng phụ bên ngoài có thể không quay lại được. Cần đánh giá tương thích dữ liệu và phương án roll-forward/khôi phục.

**Coi observability là thu thập càng nhiều log càng tốt.** Log quá nhiều gây chi phí, khó tìm và có thể lộ dữ liệu. Chọn tín hiệu theo câu hỏi vận hành, bảo vệ dữ liệu và kiểm tra khả năng truy vết.

**Chỉ theo dõi hạ tầng mà bỏ qua kết quả nghiệp vụ.** CPU và bộ nhớ bình thường không chứng minh thanh toán hoặc đặt hàng hoạt động. Theo dõi các chỉ số phản ánh tác vụ quan trọng và trạng thái giao dịch.

**Cài dashboard nhưng không kiểm tra cảnh báo.** Dashboard chỉ hữu ích khi có người xem hoặc tín hiệu dẫn đến hành động. Cần diễn tập cảnh báo, xác nhận người nhận và runbook.

**Dùng một chỉ số để kết luận chất lượng.** Độ bao phủ test, tần suất deploy hoặc số lượng log không thể đại diện toàn bộ maintainability, deployability hay observability. Kết hợp nhiều bằng chứng và phân tích bối cảnh.

## 10. Checklist đánh giá ba khía cạnh

### Khả năng bảo trì

- [ ] Ranh giới module và trách nhiệm thành phần rõ ràng.
- [ ] Phụ thuộc, giao diện và các điểm thay đổi được kiểm soát.
- [ ] Có thể thiết lập môi trường và chạy test theo hướng dẫn.
- [ ] Test độc lập, ổn định và có khả năng phát hiện hồi quy quan trọng.
- [ ] Log, lỗi và tài liệu giúp điều tra nguyên nhân.
- [ ] Có đánh giá tác động cho thay đổi đại diện và nâng cấp phụ thuộc.

### Khả năng triển khai

- [ ] Artifact có phiên bản và nguồn gốc; artifact đã kiểm thử được đưa qua các môi trường.
- [ ] Pipeline có kiểm tra, quyền và bằng chứng rõ ràng.
- [ ] Cấu hình, secret và chứng thư được quản lý an toàn.
- [ ] Migration và tương thích giữa phiên bản được kiểm tra.
- [ ] Có rollout theo giai đoạn, health/readiness và smoke test.
- [ ] Có điều kiện dừng, rollback/roll-forward và phương án dữ liệu.
- [ ] Quy trình triển khai có thể lặp lại và được diễn tập.

### Khả năng quan sát

- [ ] Metrics bao phủ lưu lượng, lỗi, độ trễ, tài nguyên và kết quả nghiệp vụ quan trọng.
- [ ] Logs có cấu trúc, ngữ cảnh và không chứa dữ liệu nhạy cảm không cần thiết.
- [ ] Traces và correlation ID giúp truy vết luồng qua các thành phần.
- [ ] Dashboard trả lời câu hỏi vận hành và gắn với phiên bản/phân khúc phù hợp.
- [ ] Cảnh báo có ngưỡng, người nhận, mức độ và hành động rõ.
- [ ] Cảnh báo và runbook đã được diễn tập.
- [ ] Chi phí, sampling, retention và quyền truy cập telemetry được quản lý.

### Quyết định và cải tiến

- [ ] Mục tiêu, ngưỡng và điều kiện đo được xác định trước.
- [ ] Bằng chứng gắn với phiên bản, môi trường và điều kiện thử.
- [ ] Khoảng trống và rủi ro tồn dư có người phụ trách, thời hạn.
- [ ] Các tiêu chí bắt buộc chưa đạt được chuyển đến đúng thẩm quyền.
- [ ] Kết quả production được dùng để cập nhật test, thiết kế, pipeline và telemetry.

## 11. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Một module có nhiều phụ thuộc vòng và mỗi thay đổi nhỏ thường làm hỏng nhiều test không liên quan. Đây là tín hiệu về maintainability. Nhóm nên phân tích ranh giới module, coupling và cách cô lập phụ thuộc; chỉ tăng số lượng test không giải quyết được nguyên nhân cấu trúc.

**Tình huống 2:** Pipeline deploy chạy thành công nhưng dùng artifact được build lại riêng cho production, khác artifact đã test ở staging. Deployability chưa được chứng minh đầy đủ vì artifact đưa vào production không phải artifact đã kiểm chứng. Cần quản lý artifact bất biến và cấu hình theo môi trường.

**Tình huống 3:** Hệ thống có log rất nhiều nhưng không thể liên kết request từ Order Service đến Payment Service. Observability còn thiếu correlation hoặc trace context. Nhóm cần chuẩn hóa mã tương quan và kiểm tra việc truyền qua các ranh giới đồng bộ, bất đồng bộ.

**Tình huống 4:** Sau triển khai, CPU và bộ nhớ bình thường nhưng số đơn ở trạng thái chờ thanh toán tăng nhanh. Nếu chỉ theo dõi hạ tầng, nhóm có thể bỏ sót lỗi nghiệp vụ hoặc webhook. Cần metric theo trạng thái giao dịch, cảnh báo theo thời gian chờ và trace/log để điều tra.

**Tình huống 5:** Rollback ứng dụng thành công nhưng phiên bản cũ không đọc được schema mới. Đây là khoảng trống deployability liên quan đến migration và tương thích. Cần kiểm tra chiến lược expand-and-contract, roll-forward hoặc phục hồi dữ liệu trước các lần phát hành sau.

Khi đánh giá một hệ thống, hãy tự hỏi: **nhóm có thể thay đổi nó an toàn không, có thể đưa phiên bản vào môi trường và khôi phục có kiểm soát không, và có thể nhận biết cũng như điều tra điều đang xảy ra không?** Mỗi câu hỏi cần có tiêu chí và bằng chứng riêng.

## Kết luận

Khả năng bảo trì giúp hệ thống có thể được hiểu, sửa đổi và kiểm thử với chi phí hợp lý. Khả năng triển khai giúp phiên bản được đưa vào môi trường mục tiêu theo quy trình lặp lại, có kiểm soát và có phương án khôi phục. Khả năng quan sát giúp nhóm nhận biết, định vị và hiểu hành vi của hệ thống từ metrics, logs, traces và các tín hiệu liên quan. Đánh giá cả ba khía cạnh bằng tiêu chí đo được, thử nghiệm thực tế và bằng chứng vận hành giúp chiến lược kiểm thử phản ánh tốt hơn chất lượng dài hạn của sản phẩm.
