# Xác định trách nhiệm của phát triển, kiểm thử, nghiệp vụ và vận hành

Chất lượng sản phẩm được tạo ra bởi nhiều vai trò trong suốt vòng đời phát triển và vận hành. Nhóm phát triển hiểu mã nguồn và thiết kế kỹ thuật; nhóm kiểm thử tập trung vào chiến lược xác minh và bằng chứng; nghiệp vụ hiểu mục tiêu, quy tắc và giá trị người dùng; vận hành chịu trách nhiệm về độ ổn định, khả năng quan sát và phục hồi của hệ thống. Nếu các vai trò không thống nhất trách nhiệm, công việc dễ bị bỏ sót hoặc trùng lặp: yêu cầu không được làm rõ, lỗi bị chuyển qua lại, kiểm thử không có dữ liệu phù hợp, sự cố không có người điều phối hoặc quyết định phát hành không có người chịu trách nhiệm.

Xác định trách nhiệm là việc làm rõ ai thực hiện, ai quyết định, ai cần được tham vấn và ai cần được thông báo cho từng hoạt động chất lượng. Mục tiêu không phải tạo ra ranh giới cứng giữa các nhóm. Mục tiêu là để mọi người biết phần việc của mình, hiểu điểm cần phối hợp và chuyển giao công việc mà không làm mất thông tin.

Trong cách làm việc hiệu quả, chất lượng là trách nhiệm chung nhưng mỗi quyết định và đầu ra vẫn cần người sở hữu rõ ràng. Phát triển chịu trách nhiệm về chất lượng kỹ thuật của thay đổi; kiểm thử chịu trách nhiệm thiết kế và cung cấp bằng chứng; nghiệp vụ chịu trách nhiệm về tính đúng đắn của mục tiêu và quy tắc; vận hành chịu trách nhiệm về khả năng triển khai, giám sát và phục hồi. Các trách nhiệm này giao nhau trong nhiều hoạt động và cần được thống nhất theo bối cảnh sản phẩm.

## 1. Vì sao cần xác định trách nhiệm rõ ràng?

Khi trách nhiệm không rõ, các vấn đề thường xuất hiện ở ranh giới giữa nhóm:

- Yêu cầu thiếu điều kiện ngoại lệ nhưng không ai chịu trách nhiệm làm rõ.
- Developer cho rằng QA sẽ tìm mọi lỗi, trong khi QA không có đủ thông tin về quyết định thiết kế.
- Kiểm thử phát hiện lỗi nhưng không có người quyết định mức độ ưu tiên hoặc chấp nhận rủi ro.
- Nghiệp vụ xác nhận chức năng theo ví dụ thành công nhưng chưa xem xét quy trình vận hành thực tế.
- Pipeline thất bại do môi trường nhưng nhóm phát triển và vận hành không thống nhất đầu mối điều tra.
- Một thay đổi được phát hành mà không có hướng dẫn giám sát, rollback hoặc hỗ trợ người dùng.
- Lỗi được sửa trong mã nhưng dữ liệu bị ảnh hưởng chưa được đối soát.
- Công việc sau phát hành không được đưa trở lại backlog phát triển và kiểm thử.

Những vấn đề này không nhất thiết xuất phát từ năng lực cá nhân. Chúng thường là hệ quả của quy trình thiếu chủ sở hữu, quyền quyết định không rõ hoặc thông tin không được chuyển giao đầy đủ.

### Lợi ích của phân công rõ

- Giảm thời gian chờ vì biết ai có thể đưa ra quyết định.
- Phát hiện sớm yêu cầu mơ hồ và rủi ro chưa được kiểm chứng.
- Tránh để kiểm thử trở thành cổng chất lượng duy nhất ở cuối quy trình.
- Tăng khả năng tái hiện và xử lý lỗi.
- Bảo đảm thay đổi có kế hoạch triển khai, quan sát và phục hồi.
- Làm rõ người chấp nhận rủi ro và ngoại lệ phát hành.
- Giúp nhóm đánh giá năng lực, ngân sách và khoảng trống trách nhiệm.

## 2. Phân biệt trách nhiệm chung và trách nhiệm sở hữu

Câu nói “chất lượng là trách nhiệm của mọi người” nhấn mạnh sự phối hợp, nhưng không đủ để vận hành công việc. Nếu tất cả cùng chịu trách nhiệm mà không có người sở hữu, một nhiệm vụ quan trọng có thể không được thực hiện.

Cần phân biệt:

- **Trách nhiệm chung:** mọi vai trò đều cần quan tâm đến chất lượng và thông báo rủi ro mà họ nhận biết.
- **Trách nhiệm thực hiện:** người hoặc nhóm trực tiếp làm một công việc cụ thể.
- **Trách nhiệm sở hữu:** người hoặc nhóm bảo đảm đầu ra có chủ sở hữu, được hoàn tất và duy trì.
- **Quyền quyết định:** vai trò có thẩm quyền lựa chọn hoặc chấp thuận một phương án.
- **Trách nhiệm tham vấn:** vai trò cung cấp chuyên môn hoặc thông tin trước quyết định.
- **Trách nhiệm được thông báo:** vai trò cần biết kết quả để phối hợp công việc liên quan.

Một hoạt động có thể có nhiều người thực hiện nhưng nên có một đầu mối chịu trách nhiệm cuối cùng. Ví dụ, nhiều người có thể tham gia kiểm thử chấp nhận, nhưng chủ sản phẩm hoặc đại diện nghiệp vụ được chỉ định chịu trách nhiệm xác nhận tiêu chí chấp nhận và quyết định nghiệp vụ.

## 3. Vai trò của nhóm phát triển

Nhóm phát triển chịu trách nhiệm xây dựng và duy trì phần mềm theo yêu cầu, kiến trúc và tiêu chuẩn kỹ thuật. Trách nhiệm chất lượng của nhóm bắt đầu từ lúc làm rõ giải pháp, tiếp tục qua triển khai, kiểm thử, phát hành và xử lý vấn đề sau phát hành.

### Làm rõ giải pháp và thiết kế

Developer cần:

- Tham gia refinement để làm rõ yêu cầu và các điều kiện chưa xác định.
- Phân tích tác động của thay đổi đến thành phần, API, dữ liệu và phụ thuộc.
- Nêu giả định kỹ thuật, giới hạn và rủi ro.
- Đề xuất thiết kế có thể kiểm thử, quan sát và phục hồi.
- Xác định các trường hợp lỗi, trạng thái bất thường và hành vi khi phụ thuộc không sẵn sàng.
- Trao đổi sớm với nghiệp vụ và kiểm thử khi quy tắc chưa rõ.

Không nên chờ đến khi QA phát hiện một yêu cầu không thể triển khai hoặc một thiết kế không có cách xác minh.

### Xây dựng chất lượng trong mã nguồn

Developer chịu trách nhiệm:

- Viết mã dễ đọc, có cấu trúc và tuân theo quy ước.
- Viết và duy trì kiểm thử đơn vị, thành phần hoặc kiểm thử phù hợp với mã mình sở hữu.
- Thực hiện review mã và xem xét assertion của test.
- Xử lý lỗi tĩnh, bảo mật và chất lượng mã theo tiêu chuẩn nhóm.
- Thiết kế xử lý lỗi, logging, metric và tracing phù hợp.
- Bảo đảm thay đổi không phá vỡ hợp đồng đã công bố.
- Cập nhật tài liệu kỹ thuật và migration khi cần.

Việc có test không tự động chứng minh mã đúng. Developer cần bảo đảm test xác minh hành vi có ý nghĩa, có thể chạy lặp lại và phát hiện được lỗi cần quan tâm.

### Hỗ trợ kiểm thử và điều tra lỗi

Developer cần cung cấp:

- Bản dựng và cấu hình có thể tái hiện.
- Thông tin về thay đổi và khu vực có nguy cơ hồi quy.
- Dữ liệu hoặc công cụ hỗ trợ tạo trạng thái cần thiết.
- Log, trace và cách quan sát lỗi.
- Phân tích nguyên nhân và bản sửa có thể kiểm chứng.
- Hỗ trợ QA tái hiện các điều kiện khó hoặc lỗi phụ thuộc.

Khi QA báo lỗi, developer cần cùng xác minh điều kiện và bằng chứng. Không nên bác bỏ lỗi chỉ vì chưa tái hiện được trên máy cá nhân; cần xem khác biệt môi trường, dữ liệu, thời gian và cấu hình.

### Trách nhiệm sau phát hành

Developer tham gia xử lý sự cố liên quan đến mã, đánh giá ảnh hưởng của bản sửa, bổ sung kiểm thử hồi quy và loại bỏ nguyên nhân gốc. Khi sửa lỗi, cần xem xét các luồng và thành phần có thể bị ảnh hưởng thay vì chỉ sửa trường hợp tái hiện ban đầu.

## 4. Vai trò của nhóm kiểm thử

Nhóm kiểm thử giúp tổ chức hiểu chất lượng hiện tại bằng cách thiết kế hoạt động xác minh phù hợp, khám phá rủi ro và cung cấp bằng chứng. Trách nhiệm này bao gồm cả việc đặt câu hỏi về yêu cầu, không chỉ thực thi test case.

### Xây dựng chiến lược kiểm thử

Nhóm kiểm thử cần:

- Phân tích yêu cầu, hành trình, kiến trúc và rủi ro.
- Xác định phạm vi, mục tiêu và tiêu chí bao phủ.
- Chọn tầng kiểm thử và kỹ thuật phù hợp.
- Xác định dữ liệu, môi trường và phụ thuộc.
- Lập kế hoạch kiểm thử thủ công, thăm dò và tự động hóa.
- Xác định điều kiện bắt đầu, hoàn tất và báo cáo.
- Nêu rõ giới hạn bằng chứng và phần chưa thể kiểm tra.

Chiến lược kiểm thử cần được thống nhất với phát triển, nghiệp vụ và vận hành. QA không thể tự quyết định mọi rủi ro hoặc cam kết nghiệp vụ thay cho chủ sản phẩm.

### Thiết kế và thực hiện kiểm thử

Nhóm kiểm thử chịu trách nhiệm:

- Thiết kế test case và charter khám phá theo rủi ro.
- Chuẩn bị hoặc phối hợp chuẩn bị dữ liệu.
- Kiểm tra chức năng, tích hợp, hệ thống và các thuộc tính chất lượng phù hợp.
- Xác minh cả luồng thành công, ngoại lệ, trạng thái và phục hồi.
- Thực hiện kiểm thử hồi quy khi thay đổi.
- Ghi nhận kết quả, bằng chứng, điều kiện và phiên bản.
- Phân biệt lỗi sản phẩm, lỗi kiểm thử, lỗi dữ liệu và lỗi môi trường.

Nhóm kiểm thử cần tránh chạy theo số lượng test hoặc tỷ lệ pass. Mục tiêu là cung cấp bằng chứng đủ mạnh để đánh giá rủi ro và ra quyết định.

### Quản lý lỗi và báo cáo chất lượng

QA cần:

- Báo lỗi rõ ràng, có bước tái hiện và kết quả mong đợi.
- Đính kèm log, ảnh, request, response hoặc dữ liệu phù hợp.
- Phân biệt severity với priority.
- Phối hợp xác minh bản sửa và chạy hồi quy.
- Theo dõi lỗi tồn đọng, test bị chặn và ngoại lệ.
- Báo cáo phần đã kiểm tra, phần chưa kiểm tra và giới hạn môi trường.
- Cảnh báo khi bằng chứng không đủ cho quyết định phát hành.

QA có thể đưa ra khuyến nghị chất lượng và chỉ ra rủi ro. Quyết định chấp nhận rủi ro nghiệp vụ cần thuộc vai trò có thẩm quyền.

### Duy trì tài sản kiểm thử

Tùy mô hình tổ chức, nhóm kiểm thử có thể cùng phát triển sở hữu:

- Bộ test tự động và framework.
- Fixture, dữ liệu kiểm thử và tài liệu.
- Charter, test plan và ma trận bao phủ.
- Báo cáo, dashboard và quy trình triage.
- Quy ước quản lý test flaky và test bị tắt.

Cần xác định rõ phần nào QA sở hữu, phần nào thuộc nhóm phát triển hoặc nền tảng để tránh trách nhiệm chồng lấn.

## 5. Vai trò của nghiệp vụ và chủ sản phẩm

Nghiệp vụ cung cấp mục tiêu và quy tắc quyết định phần mềm cần làm gì, vì sao cần làm và kết quả nào có giá trị với người dùng. Chủ sản phẩm hoặc đại diện nghiệp vụ là cầu nối giữa nhu cầu, ưu tiên và quyết định phạm vi.

### Xác định mục tiêu và yêu cầu

Nghiệp vụ cần:

- Mô tả vấn đề, mục tiêu và kết quả mong đợi.
- Xác định người dùng, vai trò và hành trình quan trọng.
- Làm rõ quy tắc, điều kiện, ngoại lệ và giới hạn.
- Cung cấp ví dụ dữ liệu thực tế đã được bảo vệ phù hợp.
- Xác định ưu tiên và tiêu chí chấp nhận.
- Tham gia giải đáp câu hỏi trong quá trình phát triển và kiểm thử.
- Thông báo thay đổi quy trình hoặc chính sách có ảnh hưởng đến sản phẩm.

Yêu cầu cần mô tả hành vi có thể xác minh. Các cụm từ như “nhanh”, “dễ dùng”, “hợp lý” hoặc “an toàn” cần được cụ thể hóa bằng tiêu chí, ví dụ hoặc ngưỡng phù hợp.

### Xác nhận giá trị và tính đúng đắn nghiệp vụ

Nghiệp vụ cần tham gia:

- Rà soát prototype và quy trình.
- Xác nhận quy tắc tính toán và quyết định.
- Đánh giá các trường hợp ngoại lệ.
- Thực hiện hoặc phối hợp kiểm thử chấp nhận người dùng (UAT).
- Xác nhận dữ liệu và báo cáo theo ý nghĩa nghiệp vụ.
- Đánh giá tác động của lỗi đến người dùng và hoạt động.
- Đề xuất ưu tiên sửa lỗi theo giá trị và rủi ro.

QA có thể xác minh phần mềm khớp với tiêu chí đã thống nhất, nhưng nghiệp vụ cần xác nhận tiêu chí đó có phản ánh đúng nhu cầu và quy tắc thật hay không.

### Quyết định phạm vi và chấp nhận rủi ro

Chủ sản phẩm thường chịu trách nhiệm ưu tiên backlog và xác nhận giá trị của tính năng. Với quyết định phát hành, cần tuân theo cơ chế phê duyệt của tổ chức. Nghiệp vụ có thể chấp nhận một số giới hạn về trải nghiệm hoặc quy trình, nhưng không thể tự thay thế phê duyệt chuyên môn về bảo mật, quyền riêng tư, an toàn hoặc tuân thủ.

## 6. Vai trò của vận hành và SRE

Vận hành bảo đảm hệ thống có thể được triển khai, giám sát, hỗ trợ và phục hồi trong điều kiện thực tế. Nhóm vận hành hoặc SRE mang góc nhìn về độ tin cậy, năng lực, sự cố và chi phí vận hành.

### Chuẩn bị khả năng triển khai

Vận hành cần:

- Duy trì pipeline, hạ tầng và cấu hình triển khai.
- Xác định điều kiện môi trường và phụ thuộc.
- Quản lý secret, chứng thư, quyền và cấu hình theo chính sách.
- Phối hợp migration và thay đổi dữ liệu.
- Chuẩn bị rollout, rollback hoặc roll-forward.
- Kiểm tra tài nguyên, quota và giới hạn năng lực.
- Bảo đảm có quy trình triển khai lặp lại và có thể kiểm soát.

### Giám sát và phản ứng sự cố

Vận hành chịu trách nhiệm hoặc phối hợp:

- Xác định SLI/SLO và cảnh báo phù hợp.
- Theo dõi log, metric, trace và tình trạng phụ thuộc.
- Phân loại sự cố và điều phối phản ứng.
- Bảo toàn bằng chứng và thông tin phục vụ điều tra.
- Thực hiện hoặc phối hợp phục hồi.
- Thông báo trạng thái và tác động đến các bên.
- Theo dõi hành động sau sự cố.

Nhóm phát triển cần hỗ trợ phân tích nguyên nhân ứng dụng; nghiệp vụ đánh giá tác động người dùng và quy trình; kiểm thử giúp tái hiện, xác minh bản sửa và bổ sung hồi quy.

### Phản hồi từ vận hành vào phát triển

Vận hành cần đưa dữ liệu thực tế trở lại vòng lặp phát triển:

- Lỗi hoặc cảnh báo lặp lại.
- Điểm nghẽn hiệu năng.
- Hành vi người dùng gây tải bất thường.
- Quy trình thủ công dễ sai.
- Thiếu metric hoặc log.
- Khó khăn trong triển khai, rollback hoặc khôi phục.
- Khoảng trống kiểm thử chỉ xuất hiện trong môi trường thực tế.

Vận hành không chỉ tiếp nhận phần mềm sau khi phát triển hoàn tất. Góc nhìn vận hành cần tham gia sớm khi thiết kế thay đổi có ảnh hưởng đến độ tin cậy.

## 7. Trách nhiệm theo vòng đời phát triển

Phân công theo từng vai trò chỉ là một phần. Nhóm cần biết các vai trò phối hợp ở mỗi giai đoạn như thế nào.

| Giai đoạn | Phát triển | Kiểm thử | Nghiệp vụ | Vận hành |
|---|---|---|---|---|
| Khám phá nhu cầu | Đánh giá khả thi và tác động kỹ thuật | Nêu rủi ro và câu hỏi kiểm chứng | Xác định mục tiêu, người dùng, quy tắc | Nêu ràng buộc vận hành và độ tin cậy |
| Refinement | Phân tích giải pháp và phụ thuộc | Xác định phạm vi, dữ liệu, tiêu chí test | Làm rõ yêu cầu và tiêu chí chấp nhận | Xác định môi trường, giám sát và triển khai |
| Thiết kế | Thiết kế kiến trúc, API và dữ liệu | Rà soát khả năng kiểm thử và rủi ro | Xác nhận quy trình và ngoại lệ | Rà soát khả năng vận hành và phục hồi |
| Phát triển | Viết mã, test đơn vị, review | Chuẩn bị test và khám phá sớm | Giải đáp quy tắc | Chuẩn bị pipeline và môi trường |
| Tích hợp | Sửa lỗi và kiểm tra hợp đồng | Kiểm thử tích hợp, hệ thống và hồi quy | Xác nhận kết quả nghiệp vụ | Hỗ trợ hạ tầng, cấu hình và quan sát |
| Chấp nhận | Sửa lỗi còn lại | Điều phối kiểm thử và báo cáo bằng chứng | Thực hiện UAT và xác nhận nghiệp vụ | Xác nhận sẵn sàng vận hành |
| Phát hành | Cung cấp bản dựng và hỗ trợ rollout | Xác minh điều kiện kiểm thử và rủi ro còn lại | Xác nhận phạm vi và quyết định nghiệp vụ | Triển khai, theo dõi và chuẩn bị rollback |
| Sau phát hành | Điều tra và sửa lỗi | Kiểm tra lại, hồi quy và cập nhật test | Đánh giá tác động và phản hồi người dùng | Theo dõi, xử lý sự cố và phục hồi |

Bảng là khung tham khảo. Một nhóm nhỏ có thể đảm nhiệm nhiều cột; một tổ chức lớn có thể có thêm bảo mật, dữ liệu, kiến trúc, hỗ trợ khách hàng hoặc quản lý phát hành.

## 8. Dùng RACI để làm rõ ai thực hiện và ai quyết định

RACI là một cách biểu diễn trách nhiệm:

- **R – Responsible:** trực tiếp thực hiện công việc.
- **A – Accountable:** chịu trách nhiệm cuối cùng về kết quả và quyết định.
- **C – Consulted:** được tham vấn trước hoặc trong khi thực hiện.
- **I – Informed:** được thông báo về tiến độ hoặc kết quả.

Mỗi công việc nên có một A rõ ràng. Có thể có nhiều R, C hoặc I tùy hoạt động. Không nên gán A cho mọi nhóm hoặc để một công việc không có ai chịu trách nhiệm cuối cùng.

### Ma trận RACI minh họa

| Hoạt động | Phát triển | Kiểm thử | Nghiệp vụ | Vận hành |
|---|---|---|---|---|
| Xác định mục tiêu và quy tắc nghiệp vụ | C | C | A/R | I |
| Đánh giá khả thi kỹ thuật | A/R | C | C | C |
| Xác định chiến lược kiểm thử | R | A/R | C | C |
| Thiết kế và viết test đơn vị | A/R | C | I | I |
| Thiết kế kiểm thử hệ thống | R | A/R | C | C |
| Chuẩn bị dữ liệu nghiệp vụ | R | R | A/C theo dữ liệu | C |
| Xây dựng môi trường kiểm thử | C | C | I | A/R |
| Xác nhận tiêu chí chấp nhận | C | R | A | I |
| Triage lỗi sản phẩm | A/R | R | C | C |
| Đánh giá tác động nghiệp vụ | C | C | A/R | C |
| Đánh giá sẵn sàng vận hành | R | C | C | A/R |
| Quyết định phát hành | R | C | A theo thẩm quyền | R/C |
| Điều phối sự cố sản xuất | R | C | C | A/R |
| Xác minh bản sửa và hồi quy | R | A/R | C | C |
| Cải tiến sau sự cố | R | R | C | A/R theo nguyên nhân |

Trong ma trận trên, vai trò A có thể thay đổi theo cơ chế quản trị thực tế. Ví dụ, quyết định phát hành có thể thuộc release manager hoặc hội đồng phát hành thay vì chủ sản phẩm. Cần ghi đúng quyền quyết định của tổ chức.

### Khi nào nên dùng RACI?

RACI hữu ích khi:

- Nhiều nhóm tham gia một quy trình.
- Có công việc thường bị bỏ sót ở ranh giới.
- Cần làm rõ quyền phê duyệt.
- Một quy trình có nhiều bước chuyển giao.
- Nhóm mở rộng hoặc thay đổi cơ cấu.

Không cần lập ma trận cho từng thao tác nhỏ. Hãy tập trung vào hoạt động có rủi ro hoặc phụ thuộc liên nhóm.

## 9. Làm rõ quyền quyết định và ranh giới thẩm quyền

Một vấn đề phổ biến là người thực hiện công việc không phải người có quyền quyết định. Ví dụ, QA có thể phát hiện rủi ro nhưng không phải người có quyền chấp nhận rủi ro nghiệp vụ; vận hành có thể xác nhận môi trường sẵn sàng nhưng không tự quyết định rằng một chức năng đáp ứng nhu cầu người dùng.

Cần phân biệt:

- Ai có quyền xác nhận yêu cầu nghiệp vụ?
- Ai quyết định giải pháp kỹ thuật?
- Ai xác nhận bằng chứng kiểm thử đủ cho mục tiêu đã đặt?
- Ai phân loại mức độ nghiêm trọng của lỗi?
- Ai ưu tiên sửa lỗi?
- Ai phê duyệt ngoại lệ?
- Ai quyết định triển khai, dừng rollout hoặc rollback?
- Ai điều phối sự cố và thông báo người bị ảnh hưởng?

### Nguyên tắc phân quyền

- Quyết định nghiệp vụ thuộc chủ sở hữu nghiệp vụ hoặc vai trò được ủy quyền.
- Quyết định kỹ thuật thuộc người sở hữu kiến trúc hoặc thành phần theo phạm vi.
- Kết luận về bằng chứng kiểm thử do nhóm kiểm thử cung cấp, với giới hạn được nêu rõ.
- Quyết định vận hành thuộc người sở hữu dịch vụ hoặc vai trò vận hành được chỉ định.
- Rủi ro bảo mật, quyền riêng tư, an toàn và tuân thủ cần người có chuyên môn và thẩm quyền tương ứng.
- Quyết định phát hành tuân theo quy trình quản trị phát hành đã thống nhất.

Không nên dùng sự đồng thuận chung để thay thế một quyết định có chủ sở hữu. Nếu chưa thống nhất, cần nêu rõ ai có quyền đưa ra quyết định cuối cùng và cơ chế leo thang.

## 10. Phối hợp làm rõ yêu cầu và tiêu chí chấp nhận

Chất lượng bắt đầu trước khi có mã. Một yêu cầu rõ giúp giảm tranh luận và tạo cơ sở kiểm thử.

### Nghiệp vụ cung cấp bối cảnh

Nghiệp vụ cần giải thích mục tiêu, người dùng, quy tắc và ví dụ. Cần nêu các trường hợp ngoại lệ, điều kiện từ chối, quyền và kết quả mong muốn.

### Phát triển đánh giá tính khả thi

Developer xem xét kiến trúc, phụ thuộc, dữ liệu, bảo mật và tác động của yêu cầu. Nếu quy tắc có nhiều cách hiểu, cần đưa ra câu hỏi và hệ quả của từng lựa chọn.

### Kiểm thử chuyển yêu cầu thành bằng chứng

QA xác định điều kiện kiểm thử, dữ liệu, nhánh, giá trị biên và tiêu chí có thể quan sát. Nếu yêu cầu không thể kiểm chứng, cần yêu cầu làm rõ.

### Vận hành đánh giá khả năng hỗ trợ

Vận hành xem xét log, metric, quyền, cấu hình, backup, khôi phục, tải và quy trình hỗ trợ. Một yêu cầu có thể đúng về chức năng nhưng khó vận hành nếu không có cách phát hiện lỗi hoặc khôi phục trạng thái.

### Ví dụ tiêu chí chấp nhận

Yêu cầu “người dùng có thể hủy đơn” còn thiếu nhiều thông tin. Nhóm cần thống nhất:

- Vai trò nào được hủy?
- Đơn ở trạng thái nào được hủy?
- Có giới hạn thời gian không?
- Nếu đã thanh toán thì hoàn tiền theo quy tắc nào?
- Tồn kho được giải phóng khi nào?
- Nếu dịch vụ thanh toán không sẵn sàng thì trạng thái nào được ghi?
- Người dùng nhận thông báo gì?
- Hệ thống ghi nhận lịch sử và người thực hiện ra sao?

Khi có câu trả lời, developer có thể thiết kế trạng thái, QA xây dựng kiểm thử và vận hành chuẩn bị quan sát cùng quy trình xử lý.

## 11. Phối hợp trong review mã và thay đổi kỹ thuật

Review mã không chỉ kiểm tra cú pháp hoặc phong cách. Nó là điểm phối hợp để đánh giá hành vi, khả năng kiểm thử và ảnh hưởng vận hành.

### Trách nhiệm của developer reviewer

- Xem xét tính đúng đắn và độ rõ của mã.
- Kiểm tra xử lý lỗi, bảo mật và hiệu năng.
- Xác minh test liên quan được thêm hoặc cập nhật.
- Đánh giá tác động đến API, schema và phụ thuộc.
- Kiểm tra logging, metric và khả năng phục hồi khi cần.

### Trách nhiệm của QA khi review

QA có thể xem xét:

- Hành vi có thể kiểm chứng không?
- Test có bao phủ điều kiện và nhánh quan trọng không?
- Dữ liệu có ổn định và độc lập không?
- Có rủi ro hồi quy ở luồng liên quan không?
- Thay đổi có cần kiểm thử tích hợp hoặc E2E không?
- Có giới hạn bằng chứng nào cần ghi nhận?

Không phải mọi pull request đều cần QA phê duyệt. Cần quy định thay đổi nào có rủi ro cao hoặc ảnh hưởng rộng cần tham gia.

### Trách nhiệm của nghiệp vụ

Nghiệp vụ được tham vấn khi thay đổi ảnh hưởng quy tắc, trải nghiệm hoặc phạm vi đã thống nhất. Không nên yêu cầu nghiệp vụ review mọi chi tiết kỹ thuật.

### Trách nhiệm của vận hành

Vận hành tham gia khi thay đổi ảnh hưởng cấu hình, hạ tầng, quyền, logging, metric, migration, rollout hoặc khả năng phục hồi. Mục tiêu là phát hiện rủi ro trước khi thay đổi được đưa vào môi trường mục tiêu.

## 12. Phối hợp trong quản lý lỗi

Một lỗi cần đi qua quy trình từ phát hiện đến xác minh và đóng. Mỗi vai trò đóng góp thông tin khác nhau.

### Người phát hiện

QA, developer, nghiệp vụ, hỗ trợ khách hàng hoặc vận hành đều có thể phát hiện lỗi. Người phát hiện cần ghi bằng chứng và điều kiện, không cần tự xác định nguyên nhân gốc trước khi báo.

### Triage

Trong triage:

- QA mô tả mức tái hiện, phạm vi kiểm thử và bằng chứng.
- Developer phân tích mã, phụ thuộc và nguyên nhân kỹ thuật.
- Nghiệp vụ đánh giá tác động đến người dùng và quy tắc.
- Vận hành đánh giá phạm vi sự cố, metric và ảnh hưởng môi trường.
- Người sở hữu sản phẩm hoặc vai trò được chỉ định ưu tiên và quyết định hướng xử lý.

### Sửa và xác minh

Developer sửa lỗi và cung cấp bản dựng hoặc thay đổi. QA xác minh trường hợp lỗi, kiểm thử hồi quy và đánh giá tác động liên quan. Nghiệp vụ xác nhận lại quy tắc nếu giải pháp làm thay đổi hành vi. Vận hành kiểm tra điều kiện triển khai hoặc khôi phục nếu lỗi ảnh hưởng môi trường hay dữ liệu.

Không nên đóng lỗi chỉ vì mã đã được sửa. Cần có bằng chứng xác minh và xác nhận dữ liệu hoặc tác động đã được xử lý khi cần.

## 13. Phối hợp quản lý dữ liệu và môi trường kiểm thử

Dữ liệu và môi trường thường có nhiều chủ sở hữu. Nếu không phân công rõ, nhóm kiểm thử có thể phải chờ hoặc tự thay đổi cấu hình mà không biết ảnh hưởng.

### Phát triển

- Cung cấp migration, seed hoặc công cụ tạo dữ liệu.
- Duy trì schema và hợp đồng.
- Bảo đảm ứng dụng xử lý dữ liệu kiểm thử theo quy tắc.
- Hỗ trợ tái hiện trạng thái đặc biệt.

### Kiểm thử

- Xác định dữ liệu cần cho kịch bản.
- Quản lý fixture và trạng thái ban đầu.
- Kiểm tra tính độc lập, cleanup và khả năng tái tạo.
- Ghi nhận phiên bản dữ liệu và giới hạn.
- Không dùng dữ liệu nhạy cảm trái quy định.

### Nghiệp vụ

- Xác nhận quy tắc và ý nghĩa dữ liệu.
- Cung cấp ví dụ nghiệp vụ đã được bảo vệ phù hợp.
- Xác định các trường hợp đặc biệt và ngoại lệ.
- Xác nhận kết quả dữ liệu có ý nghĩa nghiệp vụ.

### Vận hành

- Cung cấp môi trường, quyền và cấu hình.
- Quản lý secret, chứng thư, backup và phục hồi.
- Theo dõi dung lượng, hiệu năng và trạng thái phụ thuộc.
- Hỗ trợ reset hoặc khôi phục môi trường theo quy trình.

Một bộ dữ liệu hoặc môi trường dùng chung cần có người sở hữu chính. Việc nhóm nào cũng có thể sử dụng không có nghĩa nhóm nào cũng được tự ý thay đổi.

## 14. Phối hợp trong tự động hóa kiểm thử

Tự động hóa cần sự tham gia của nhiều vai trò:

- Nghiệp vụ xác định quy tắc và hành trình có giá trị cần bảo vệ.
- QA thiết kế chiến lược, phạm vi, dữ liệu và assertion.
- Developer xây dựng test ở tầng phù hợp và hỗ trợ khả năng kiểm thử trong mã.
- Vận hành duy trì runner, môi trường, quyền, secret và quan sát pipeline.

### Phân công theo tầng

| Tầng | Vai trò chính thường gặp | Phối hợp |
|---|---|---|
| Unit | Developer | QA tư vấn chiến lược và rủi ro |
| Component | Developer | QA và nhóm sở hữu thành phần |
| Contract | Provider/consumer developer | QA, kiến trúc hoặc nhóm tích hợp |
| Integration | Nhóm sở hữu luồng hoặc thành phần | QA, vận hành |
| E2E | QA hoặc nhóm sản phẩm theo mô hình tổ chức | Developer, nghiệp vụ, vận hành |
| Performance | Nhóm chuyên môn hoặc SRE | Developer, nghiệp vụ |
| Security | Nhóm bảo mật chuyên môn | Developer, QA, vận hành |
| Acceptance | Nghiệp vụ/chủ sản phẩm | QA, developer |

Bảng là gợi ý. Tổ chức có thể phân công khác nhưng cần bảo đảm test có người sở hữu, dữ liệu và môi trường được quản lý, kết quả có người theo dõi.

### Trách nhiệm khi test flaky

- QA hoặc người sở hữu test ghi nhận và phân loại flaky test.
- Developer điều tra lỗi trong mã, đồng thời, thời gian hoặc trạng thái.
- Vận hành điều tra runner, tài nguyên, mạng và môi trường.
- Nghiệp vụ được thông báo nếu test liên quan đến rủi ro hoặc tiêu chí chấp nhận.
- Người sở hữu bộ kiểm thử theo dõi thời hạn sửa hoặc cách ly.

Không nên để test flaky bị tắt vô thời hạn mà không có người chịu trách nhiệm.

## 15. Phối hợp trong quyết định phát hành

Quyết định phát hành cần tổng hợp bằng chứng kỹ thuật, kiểm thử, nghiệp vụ và vận hành.

### Phát triển cung cấp

- Trạng thái thay đổi và lỗi còn mở.
- Ảnh hưởng kỹ thuật và phụ thuộc.
- Kết quả review, test và phân tích mã.
- Migration, cấu hình và kế hoạch rollback.
- Những giới hạn hoặc rủi ro đã biết.

### Kiểm thử cung cấp

- Phạm vi và kết quả kiểm thử.
- Bao phủ chức năng, luồng và trạng thái.
- Lỗi còn mở theo severity.
- Test bị blocked, skipped hoặc flaky.
- Môi trường và dữ liệu đã dùng.
- Giới hạn bằng chứng và khuyến nghị.

### Nghiệp vụ cung cấp

- Xác nhận tiêu chí chấp nhận.
- Kết quả UAT.
- Tác động và ưu tiên nghiệp vụ.
- Phạm vi người dùng hoặc tính năng được phép mở.
- Rủi ro nghiệp vụ được chấp nhận theo thẩm quyền.

### Vận hành cung cấp

- Trạng thái môi trường và phụ thuộc.
- Kế hoạch triển khai và rollback.
- Metric, log, cảnh báo và dashboard.
- Năng lực, backup và phương án phục hồi.
- Lịch trực, đầu mối hỗ trợ và điều kiện dừng rollout.

### Ai quyết định?

Tổ chức cần chỉ định một vai trò chịu trách nhiệm cuối cùng cho quyết định phát hành. Vai trò đó xem xét bằng chứng và các phê duyệt chuyên môn cần thiết. Không nên coi QA là người duy nhất có quyền hoặc nghĩa vụ “cho phép” phát hành nếu cơ chế quản trị không quy định như vậy.

## 16. Phối hợp sau phát hành và trong sự cố

Sau khi triển khai, trách nhiệm chuyển sang theo dõi hành vi thực tế và phản ứng khi có vấn đề. Đây là giai đoạn kiểm tra các giả định trong môi trường vận hành.

### Khi hệ thống hoạt động bình thường

- Vận hành theo dõi SLI/SLO, cảnh báo và xu hướng.
- Developer xử lý lỗi ứng dụng và cải thiện khả năng quan sát.
- QA xem xét phản hồi, lỗi lọt và bổ sung kiểm thử.
- Nghiệp vụ đánh giá tác động đến người dùng và kết quả kinh doanh.

### Khi xảy ra sự cố

- Vận hành hoặc incident commander điều phối phản ứng theo quy trình.
- Developer phân tích nguyên nhân kỹ thuật và chuẩn bị bản sửa.
- QA hỗ trợ tái hiện, xác minh bản sửa và đánh giá hồi quy.
- Nghiệp vụ xác định mức ảnh hưởng và thông tin cần truyền đạt cho người dùng.
- Chủ dịch vụ hoặc người có thẩm quyền quyết định giảm chức năng, dừng rollout hoặc khôi phục.

Vai trò điều phối sự cố cần được xác định trước. Không nên mặc định người phát hiện lỗi là người có trách nhiệm điều phối toàn bộ sự cố.

### Sau sự cố

Các nhóm cùng tham gia review không đổ lỗi:

- Xác định nguyên nhân và điều kiện góp phần.
- Đánh giá tại sao kiểm thử hoặc giám sát không phát hiện sớm.
- Xác định dữ liệu và người dùng bị ảnh hưởng.
- Bổ sung kiểm thử hồi quy và cảnh báo.
- Cải thiện quy trình triển khai hoặc phục hồi.
- Giao người sở hữu và thời hạn cho từng hành động.

## 17. Quy trình chuyển giao giữa các vai trò

Chuyển giao không chỉ là gửi một thông báo. Người nhận cần đủ thông tin để tiếp tục công việc và biết điều kiện nào đã được xác minh.

### Chuyển từ nghiệp vụ sang phát triển và kiểm thử

Cần có mục tiêu, quy tắc, tiêu chí chấp nhận, ví dụ, ngoại lệ, ưu tiên và người giải đáp. Các điểm chưa rõ phải được ghi lại thay vì mặc định.

### Chuyển từ phát triển sang kiểm thử

Cần có phiên bản, phạm vi thay đổi, hướng dẫn triển khai, migration, cấu hình, dữ liệu, phụ thuộc, rủi ro đã biết và cách quan sát. Bản dựng phải có thể xác định và tái tạo.

### Chuyển từ kiểm thử sang quyết định phát hành

Cần có kết quả, bằng chứng, lỗi còn mở, test chưa chạy, giới hạn môi trường, khuyến nghị và các rủi ro chưa được xác minh.

### Chuyển từ phát triển sang vận hành

Cần có hướng dẫn triển khai, cấu hình, secret, tài nguyên, migration, dashboard, cảnh báo, runbook, rollback và đầu mối hỗ trợ.

### Chuyển từ vận hành trở lại phát triển và kiểm thử

Cần có thời điểm, phạm vi ảnh hưởng, log, trace, metric, phiên bản, hành động đã thực hiện, dữ liệu có thể bị ảnh hưởng và điều kiện tái hiện.

Mỗi chuyển giao nên có người gửi, người nhận, thời điểm, nội dung và xác nhận đã tiếp nhận khi rủi ro đủ cao.

## 18. Ví dụ tổng hợp: phát triển tính năng hủy đơn hàng

Giả sử sản phẩm bổ sung khả năng hủy đơn sau khi thanh toán nhưng trước khi đơn được bàn giao cho vận chuyển.

### Nghiệp vụ

- Xác định ai được hủy và trong khoảng thời gian nào.
- Quy định trường hợp hoàn tiền toàn phần hoặc một phần.
- Xác định cách xử lý mã giảm giá và điểm thưởng.
- Quy định thông báo và lịch sử giao dịch.
- Xác nhận tiêu chí chấp nhận và trường hợp ngoại lệ.

### Phát triển

- Thiết kế chuyển trạng thái và kiểm soát đồng thời.
- Bảo đảm yêu cầu hủy không xử lý hai lần.
- Tích hợp với dịch vụ thanh toán và tồn kho.
- Viết test đơn vị cho quy tắc hủy và hoàn tiền.
- Thêm log, metric và xử lý lỗi phụ thuộc.
- Cung cấp migration hoặc cấu hình nếu cần.

### Kiểm thử

- Kiểm tra đơn ở các trạng thái khác nhau.
- Kiểm tra quyền và giới hạn thời gian.
- Kiểm tra webhook hoàn tiền lặp hoặc đến trễ.
- Kiểm tra hai yêu cầu hủy đồng thời.
- Kiểm tra dữ liệu và lịch sử giao dịch.
- Thực hiện E2E và UAT theo tiêu chí đã thống nhất.
- Báo cáo lỗi và khoảng trống bằng chứng.

### Vận hành

- Chuẩn bị môi trường và sandbox thanh toán.
- Xác minh secret, quota và webhook endpoint.
- Thiết lập metric cho tỷ lệ hủy, hoàn tiền lỗi và giao dịch chờ.
- Chuẩn bị cảnh báo, runbook và quy trình đối soát.
- Xác nhận rollback hoặc kill switch nếu có lỗi.

### Quyết định phát hành

Chủ thể có thẩm quyền xem xét kết quả kiểm thử, UAT, trạng thái lỗi, khả năng đối soát và phương án phục hồi. Nếu webhook hoàn tiền lặp chưa được kiểm soát, nhóm có thể quyết định chưa mở tính năng hoặc giới hạn phạm vi theo quy trình phê duyệt. QA không tự chấp nhận rủi ro tài chính thay nghiệp vụ.

## 19. Ví dụ: xử lý lỗi sau phát hành

Giả sử sau khi triển khai, vận hành phát hiện tỷ lệ request tạo đơn thất bại tăng cao.

1. Vận hành xác nhận cảnh báo, xác định thời điểm bắt đầu và phạm vi ảnh hưởng.
2. Developer kiểm tra log, trace và thay đổi gần nhất để tìm nguyên nhân.
3. QA tái hiện trong môi trường tương đương và xác minh luồng tạo đơn cùng các nhánh lỗi.
4. Nghiệp vụ đánh giá số người dùng và giao dịch bị ảnh hưởng, xác định thông tin cần truyền đạt.
5. Người có thẩm quyền quyết định rollback, tắt feature flag hoặc chuyển sang phương án an toàn.
6. Developer sửa lỗi; QA kiểm tra bản sửa và hồi quy.
7. Vận hành triển khai, theo dõi metric và xác nhận hệ thống ổn định.
8. Các nhóm cùng review sự cố và giao hành động phòng ngừa.

Ví dụ cho thấy một sự cố không thuộc riêng một nhóm. Mỗi nhóm có trách nhiệm riêng và cần phối hợp theo một đầu mối điều phối.

## 20. Xử lý bất đồng và leo thang quyết định

Bất đồng có thể xảy ra khi các vai trò đánh giá tác động khác nhau. QA có thể cho rằng bằng chứng chưa đủ; nghiệp vụ muốn phát hành đúng hạn; phát triển tin rằng lỗi ít có khả năng xảy ra; vận hành lo ngại không thể phục hồi.

Cách xử lý:

1. Mô tả quyết định cần đưa ra và thời hạn.
2. Tập hợp bằng chứng, giả định và phần chưa biết.
3. Tách dữ kiện khỏi nhận định.
4. Xác định tác động và rủi ro còn lại.
5. Nêu các phương án, chi phí và hậu quả.
6. Xác định người có thẩm quyền quyết định.
7. Ghi lại quyết định, lý do và điều kiện xem xét lại.

Không nên kéo dài tranh luận mà không làm rõ ai có quyền quyết định. Nếu rủi ro thuộc lĩnh vực bảo mật, an toàn hoặc tuân thủ, cần chuyển đến vai trò chuyên môn tương ứng thay vì giải quyết bằng biểu quyết thông thường.

## 21. Thiết lập working agreement giữa các nhóm

Working agreement là thỏa thuận vận hành chung về cách phối hợp. Nó nên ngắn, rõ và có thể được xem lại khi nhóm thay đổi.

Các nội dung nên thống nhất:

- Ai sở hữu yêu cầu và tiêu chí chấp nhận.
- Ai review thay đổi kỹ thuật và kiểm thử.
- Ai chuẩn bị dữ liệu và môi trường.
- Cách bàn giao bản dựng cho QA.
- Cách báo lỗi và thời gian phản hồi dự kiến.
- Ai phân loại severity và ai ưu tiên.
- Ai quyết định ngoại lệ và phát hành.
- Cách thông báo thay đổi môi trường.
- Ai điều phối sự cố.
- Cách xác minh bản sửa và đóng lỗi.
- Cách cập nhật tài liệu, test và runbook.
- Cách xử lý khi người sở hữu vắng mặt.

Thỏa thuận cần phù hợp với quy mô và nhịp làm việc. Không nên tạo quy trình nặng cho một nhóm nhỏ nếu một cuộc trao đổi trực tiếp và thông tin trong ticket đã đủ rõ.

## 22. Theo dõi hiệu quả phối hợp và khoảng trống trách nhiệm

Có thể dùng một số chỉ số để phát hiện vấn đề trong cách phối hợp:

- Thời gian từ khi phát hiện lỗi đến khi có người nhận xử lý.
- Số lỗi bị chuyển qua lại giữa các nhóm.
- Số yêu cầu cần làm rõ sau khi bắt đầu phát triển.
- Tỷ lệ test bị chặn do thiếu dữ liệu hoặc môi trường.
- Thời gian chờ phản hồi nghiệp vụ.
- Số thay đổi phát hành thiếu hướng dẫn vận hành.
- Số sự cố không có đầu mối điều phối rõ.
- Tỷ lệ hành động sau sự cố hoàn tất đúng hạn.
- Số ngoại lệ phát hành không có thời hạn hoặc người sở hữu.

Không nên dùng các chỉ số này để đánh giá cá nhân một cách máy móc. Chúng hữu ích để tìm điểm nghẽn trong quy trình, năng lực và cách phân công.

### Rà soát định kỳ

Trong retrospective hoặc buổi review chất lượng, hãy hỏi:

- Có công việc nào bị bỏ sót vì không rõ chủ sở hữu không?
- Có quyết định nào phải chờ sai người không?
- Có bước bàn giao nào thiếu thông tin?
- Có nhóm nào đang gánh quá nhiều việc ngoài trách nhiệm?
- Có trách nhiệm nào trùng lặp mà không tạo thêm giá trị?
- Có quyền quyết định nào cần được làm rõ?
- Có cần cập nhật RACI hoặc working agreement không?

## 23. Những sai lầm thường gặp

- **Cho rằng chất lượng là trách nhiệm của QA:** developer, nghiệp vụ và vận hành có thể bỏ qua phần đóng góp của mình.
- **Cho rằng mọi người cùng chịu trách nhiệm nghĩa là không cần chủ sở hữu:** công việc dễ bị bỏ sót.
- **Giao QA quyền quyết định nghiệp vụ:** QA cung cấp bằng chứng nhưng không thay thế chủ sản phẩm.
- **Giao toàn bộ test tự động cho một nhóm chuyên trách:** nhóm phát triển mất trách nhiệm với chất lượng mã của mình.
- **Để developer tự quyết định mọi rủi ro:** góc nhìn người dùng, nghiệp vụ và vận hành có thể bị thiếu.
- **Chỉ mời vận hành ở cuối dự án:** các yêu cầu về giám sát, cấu hình và phục hồi được phát hiện muộn.
- **Dùng RACI quá chi tiết:** ma trận trở thành gánh nặng và nhanh lỗi thời.
- **Có nhiều người A cho một việc:** không rõ ai chịu trách nhiệm cuối cùng.
- **Không có người thay thế:** công việc dừng khi người sở hữu vắng mặt.
- **Chuyển giao chỉ bằng lời nói:** thông tin và quyết định không có dấu vết.
- **Không cập nhật trách nhiệm sau thay đổi tổ chức:** tài liệu không phản ánh thực tế.
- **Đánh giá phối hợp bằng số ticket:** số lượng không thể hiện chất lượng trao đổi hoặc giá trị bằng chứng.

## 24. Mẫu xác định trách nhiệm cho một hoạt động

~~~text
TÊN HOẠT ĐỘNG:
MỤC TIÊU:
PHẠM VI:
ĐẦU RA CẦN CÓ:

NGƯỜI / NHÓM THỰC HIỆN (R):
NGƯỜI CHỊU TRÁCH NHIỆM CUỐI (A):
BÊN THAM VẤN (C):
BÊN CẦN ĐƯỢC THÔNG BÁO (I):

QUYỀN QUYẾT ĐỊNH:
ĐIỀU KIỆN BẮT ĐẦU:
ĐIỀU KIỆN HOÀN TẤT:
THÔNG TIN BÀN GIAO:
PHỤ THUỘC:
NGƯỜI THAY THẾ:
CƠ CHẾ LEO THANG:
NƠI LƯU BẰNG CHỨNG:
NGÀY RÀ SOÁT:
~~~

## 25. Mẫu working agreement giữa phát triển, kiểm thử, nghiệp vụ và vận hành

~~~text
MỤC TIÊU PHỐI HỢP:
PHẠM VI SẢN PHẨM / NHÓM:

1. YÊU CẦU VÀ NGHIỆP VỤ
- Người sở hữu yêu cầu:
- Người xác nhận quy tắc:
- Cách xử lý điểm chưa rõ:

2. PHÁT TRIỂN
- Người sở hữu mã:
- Quy tắc review:
- Kiểm thử ở tầng mã:
- Thông tin khi bàn giao:

3. KIỂM THỬ
- Người sở hữu chiến lược:
- Phạm vi và tiêu chí:
- Cách báo lỗi:
- Báo cáo và giới hạn bằng chứng:

4. VẬN HÀNH
- Người sở hữu môi trường:
- Triển khai và rollback:
- Giám sát và cảnh báo:
- Điều phối sự cố:

5. QUYẾT ĐỊNH
- Người ưu tiên lỗi:
- Người chấp nhận rủi ro:
- Người quyết định phát hành:
- Vai trò chuyên môn cần phê duyệt:

6. CHUYỂN GIAO
- Bản dựng và phiên bản:
- Dữ liệu và môi trường:
- Bằng chứng:
- Tài liệu và runbook:

7. RÀ SOÁT
- Nhịp xem lại:
- Chỉ số theo dõi:
- Cách cập nhật thỏa thuận:
~~~

Mẫu nên được điều chỉnh theo thực tế. Một thỏa thuận tốt đủ rõ để người mới biết cần liên hệ ai và đủ linh hoạt để nhóm phối hợp khi tình huống không nằm trong quy trình chuẩn.

## Kết luận

Phát triển, kiểm thử, nghiệp vụ và vận hành có trách nhiệm khác nhau nhưng liên kết trong cùng mục tiêu chất lượng. Phát triển xây dựng và duy trì phần mềm; kiểm thử thiết kế xác minh và cung cấp bằng chứng; nghiệp vụ xác định giá trị, quy tắc và tiêu chí chấp nhận; vận hành bảo đảm triển khai, giám sát và phục hồi. Mỗi nhóm cần sở hữu phần việc của mình, đồng thời tham gia các điểm phối hợp và chuyển giao đã thống nhất.

RACI, quyền quyết định rõ ràng, working agreement và bằng chứng bàn giao giúp giảm khoảng trống trách nhiệm. Khi các vai trò cùng tham gia từ làm rõ yêu cầu đến sau phát hành, lỗi được phát hiện và xử lý sớm hơn, quyết định rủi ro có cơ sở hơn và sản phẩm có thể được duy trì trong điều kiện vận hành thực tế.
