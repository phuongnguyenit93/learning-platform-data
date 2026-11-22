# Thống nhất quy trình ghi nhận, phân loại và xử lý lỗi

Một lỗi được phát hiện nhưng không được ghi nhận đầy đủ có thể bị tái hiện nhiều lần, chuyển qua nhiều nhóm mà không có người chịu trách nhiệm hoặc bị đóng khi chưa có bằng chứng sửa đúng. Những tình huống này làm tăng thời gian xử lý, khiến lỗi tái xuất hiện và làm giảm độ tin cậy của bộ kiểm thử. Khi lỗi xảy ra trong production, nhóm còn phải cân bằng giữa việc khôi phục dịch vụ ngay và việc tìm nguyên nhân gốc để ngăn tái diễn.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, quy trình ghi nhận, phân loại và xử lý lỗi cần tạo một luồng thống nhất từ phát hiện đến xác minh và đóng. Mỗi lỗi cần có thông tin đủ để người khác hiểu, tái hiện hoặc điều tra; mức độ ảnh hưởng và tính khẩn cấp phải được đánh giá nhất quán; chủ sở hữu và bước tiếp theo phải rõ; kết quả sửa phải được kiểm chứng bằng bằng chứng phù hợp. Quy trình cần kết nối lỗi từ kiểm thử, vận hành, hỗ trợ khách hàng và giám sát production, đồng thời phân biệt việc xử lý sự cố tức thời với việc sửa nguyên nhân trong sản phẩm.

## 1. Thống nhất khái niệm lỗi, khiếm khuyết và sự cố

### Lỗi được phát hiện trong quá trình xác thực

Trong quy trình này, **lỗi (defect)** là hành vi, kết quả, dữ liệu hoặc thuộc tính của sản phẩm không đáp ứng yêu cầu, hợp đồng, tiêu chí chấp nhận hoặc hành vi đã được phê duyệt. Lỗi có thể được phát hiện qua:

- Unit, component, integration, system hoặc E2E test.
- Kiểm thử hồi quy, hiệu năng, bảo mật, khả năng phục hồi hoặc khả năng tương thích.
- Review mã nguồn, phân tích tĩnh và kiểm tra cấu hình.
- Kiểm thử chấp nhận hoặc đánh giá thủ công.
- Monitoring, log, trace và cảnh báo production.
- Phản hồi từ người dùng, bộ phận hỗ trợ hoặc đối tác tích hợp.

Một test fail không tự động chứng minh sản phẩm có defect. Nguyên nhân có thể nằm ở test, dữ liệu, môi trường hoặc phụ thuộc bên ngoài. Quy trình phải cho phép ghi nhận kết quả ban đầu rồi phân loại sau khi có bằng chứng.

### Phân biệt defect với incident

**Sự cố (incident)** là sự kiện làm suy giảm hoặc gián đoạn dịch vụ, ảnh hưởng đến người dùng, dữ liệu, bảo mật hoặc hoạt động kinh doanh và cần được điều phối phản ứng. Một incident có thể xuất phát từ một defect, nhưng cũng có thể do cấu hình, hạ tầng, nhà cung cấp, thao tác vận hành hoặc sự kết hợp nhiều yếu tố.

| Khái niệm | Trọng tâm | Ví dụ | Kết quả cần đạt |
|---|---|---|---|
| Defect | Hành vi sản phẩm không đúng yêu cầu | Tính sai thuế ở một tổ hợp dữ liệu | Sửa nguyên nhân và xác minh hồi quy |
| Incident | Tác động đang xảy ra đối với dịch vụ hoặc người dùng | Nhiều đơn hàng không thể thanh toán | Khôi phục dịch vụ, giới hạn ảnh hưởng và điều tra |
| Test failure | Một lần kiểm thử không đạt hoặc không thể hoàn tất | E2E timeout ở bước chờ callback | Phân loại lỗi sản phẩm, test, môi trường hoặc phụ thuộc |
| Problem/root cause | Nguyên nhân hoặc điều kiện nền tạo ra một hay nhiều incident | Retry không idempotent gây giao dịch trùng | Loại bỏ nguyên nhân và ngăn tái diễn |

Một incident có thể được giảm tác động bằng rollback hoặc workaround trong khi defect gốc vẫn còn. Vì vậy, cần liên kết incident với defect và theo dõi cả hai cho đến khi các hành động cần thiết hoàn tất.

### Phân biệt lỗi sản phẩm với lỗi của hoạt động kiểm thử

Khi một bài test thất bại, cần xem xét ít nhất các khả năng:

- **Defect sản phẩm:** hành vi thực tế vi phạm yêu cầu.
- **Defect của test:** oracle, assertion, selector hoặc logic test sai.
- **Lỗi dữ liệu:** fixture, seed hoặc trạng thái ban đầu không hợp lệ.
- **Lỗi môi trường:** dịch vụ không sẵn sàng, cấu hình sai hoặc tài nguyên cạn.
- **Lỗi phụ thuộc:** API bên ngoài, sandbox hoặc nhà cung cấp gặp vấn đề.
- **Lỗi hạ tầng kiểm thử:** runner, container, network hoặc pipeline bị lỗi.
- **Chưa xác định:** bằng chứng hiện tại chưa đủ để kết luận.

Không gán mọi timeout là lỗi môi trường hoặc mọi assertion fail là lỗi sản phẩm. Phân loại ban đầu có thể thay đổi khi điều tra có thêm dữ liệu.

## 2. Thiết kế quy trình xử lý lỗi thống nhất

### Các giai đoạn trong vòng đời

Một quy trình điển hình gồm:

1. **Phát hiện:** ghi nhận tín hiệu từ test, review, monitoring hoặc người dùng.
2. **Ghi nhận:** tạo bản ghi có định danh, mô tả, bằng chứng và phạm vi ảnh hưởng.
3. **Phân loại:** xác định loại lỗi, thành phần, môi trường, mức độ nghiêm trọng và tính khẩn cấp.
4. **Triage:** xác nhận tính hợp lệ, loại trùng, đánh giá rủi ro và thống nhất ưu tiên.
5. **Giao xử lý:** chỉ định owner, nhóm phối hợp và thời hạn phản hồi.
6. **Điều tra:** tái hiện, phân tích nguyên nhân và xác định phạm vi tác động.
7. **Khắc phục:** sửa sản phẩm, test, dữ liệu, cấu hình hoặc quy trình theo nguyên nhân.
8. **Xác minh:** chạy kiểm tra mục tiêu, hồi quy và kiểm tra tác dụng phụ.
9. **Đóng hoặc theo dõi tiếp:** đóng khi có đủ bằng chứng; nếu chưa hoàn tất, giữ trạng thái và hành động tiếp theo rõ ràng.
10. **Học hỏi:** cập nhật test, tài liệu, giám sát, tiêu chí review hoặc quy trình khi cần.

~~~mermaid
flowchart TD
    A["Phát hiện lỗi"] --> B["Ghi nhận và gắn ID"]
    B --> C["Phân loại và đánh giá tác động"]
    C --> D{"Có incident đang ảnh hưởng?"}
    D -->|Có| E["Kích hoạt quy trình ứng phó incident"]
    D -->|Không| F["Triage và ưu tiên defect"]
    E --> G["Giảm tác động / khôi phục dịch vụ"]
    G --> H["Điều tra nguyên nhân và liên kết defect"]
    F --> H
    H --> I["Giao owner và khắc phục"]
    I --> J["Xác minh sửa và hồi quy"]
    J --> K{"Đạt tiêu chí đóng?"}
    K -->|Chưa| H
    K -->|Đạt| L["Đóng và cập nhật bài học"]
~~~

Sơ đồ mô tả luồng tổng quát. Incident có thể cần điều phối song song với điều tra defect; không nên chờ hoàn tất phân tích nguyên nhân mới bắt đầu khôi phục dịch vụ.

### Một nguồn ghi nhận có thể truy vết

Nhóm nên thống nhất nơi lưu bản ghi lỗi hoặc quy tắc liên kết giữa các công cụ. Không nhất thiết mọi tổ chức phải dùng một công cụ duy nhất, nhưng cần tránh thông tin quan trọng chỉ nằm trong chat, email hoặc log tạm thời.

Mỗi bản ghi cần có:

- ID duy nhất và liên kết đến bản ghi liên quan.
- Tiêu đề ngắn, mô tả triệu chứng.
- Thời điểm phát hiện và thời điểm xảy ra nếu biết.
- Người hoặc hệ thống báo cáo.
- Sản phẩm, phiên bản, build, commit và môi trường.
- Điều kiện trước, bước tái hiện và dữ liệu liên quan.
- Kết quả mong đợi và kết quả thực tế.
- Bằng chứng: log, trace, ảnh, video, request hoặc test report.
- Phân loại, severity, priority và trạng thái.
- Owner, nhóm phối hợp và bước tiếp theo.
- Liên kết đến pull request, incident, test case hoặc change request.

Không ghi secret, token, mật khẩu hoặc dữ liệu cá nhân không cần thiết vào bản ghi. Dùng định danh đã che giấu và liên kết đến kho bằng chứng có kiểm soát quyền.

### Bảo đảm lỗi không bị mất khi chuyển giao

Khi chuyển lỗi giữa QA, phát triển, vận hành hoặc hỗ trợ, bản ghi phải trả lời được:

- Điều gì đã xảy ra?
- Ai hoặc thành phần nào bị ảnh hưởng?
- Có thể tái hiện bằng cách nào?
- Bằng chứng nào đã được thu thập?
- Điều gì đã được loại trừ?
- Ai đang sở hữu bước tiếp theo?
- Khi nào cần cập nhật lại?
- Điều kiện nào để xem là xử lý xong?

Không chuyển một lỗi chỉ bằng câu “không phải phía tôi”. Nếu phân loại sai, hãy ghi bằng chứng và chuyển đúng owner, đồng thời giữ lịch sử quyết định.

## 3. Ghi nhận lỗi có chất lượng

### Viết tiêu đề và mô tả cụ thể

Tiêu đề nên nêu hành vi sai và điều kiện quan trọng. Ví dụ:

- Kém: “Thanh toán lỗi”.
- Tốt hơn: “Đơn hàng dùng mã giảm giá phần trăm bị tính tổng cao hơn sau callback thanh toán”.

Mô tả cần tách triệu chứng quan sát được khỏi giả thuyết nguyên nhân. Không kết luận “race condition ở worker” nếu mới chỉ thấy trạng thái cập nhật chậm. Có thể ghi “đơn hàng vẫn ở trạng thái PROCESSING sau khi callback thành công; nghi ngờ luồng cập nhật bất đồng bộ, cần kiểm tra trace worker”.

### Ghi bước tái hiện

Một báo cáo tái hiện tốt thường có:

1. Phiên bản hoặc build đang kiểm tra.
2. Môi trường và cấu hình liên quan.
3. Điều kiện trước khi thực hiện.
4. Dữ liệu hoặc fixture cần thiết.
5. Các bước thao tác theo thứ tự.
6. Kết quả mong đợi.
7. Kết quả thực tế.
8. Tần suất xảy ra hoặc số lần đã thử.
9. Phạm vi người dùng hoặc dữ liệu bị ảnh hưởng.

Nếu lỗi không tái hiện ổn định, ghi rõ số lần chạy, seed, thời điểm, run ID và các yếu tố biến thiên. Không viết “luôn xảy ra” khi chỉ quan sát một lần.

### Thu thập bằng chứng có ích

Bằng chứng có thể gồm:

- Test report và tên test.
- Log có cấu trúc và correlation ID.
- Trace xuyên dịch vụ.
- Request/response đã khử dữ liệu nhạy cảm.
- Screenshot, video hoặc DOM snapshot khi lỗi giao diện.
- Trạng thái dữ liệu có thẩm quyền.
- Metric về độ trễ, lỗi, queue backlog hoặc tài nguyên.
- Phiên bản ứng dụng, dependency, schema và cấu hình.
- Seed, fixture ID và run ID.

Thu thập vừa đủ để tái hiện và chẩn đoán. Artifact cần có thời hạn lưu, quyền truy cập và cơ chế xóa phù hợp.

### Phân biệt sự kiện, giả thuyết và kết luận

Bản ghi nên phân tách ba loại thông tin:

- **Sự kiện:** điều đã quan sát và có bằng chứng.
- **Giả thuyết:** giải thích đang được kiểm tra.
- **Kết luận:** nguyên nhân đã được xác minh ở mức đủ tin cậy.

Ví dụ:

- Sự kiện: callback thanh toán trả thành công lúc 10:03; order API vẫn trả PROCESSING lúc 10:04.
- Giả thuyết: consumer xử lý event bị chậm hoặc không nhận event.
- Kết luận sau điều tra: consumer đã nhận event nhưng transaction cập nhật trạng thái bị rollback do vi phạm ràng buộc.

Cách ghi này giúp người tiếp nhận không nhầm phỏng đoán ban đầu với nguyên nhân đã xác nhận.

## 4. Phân loại lỗi theo nhiều chiều

### Phân loại theo nguồn hoặc loại vấn đề

Một taxonomy có thể gồm:

| Nhóm | Nội dung |
|---|---|
| Functional | Sai quy tắc nghiệp vụ hoặc kết quả chức năng |
| Data | Sai, mất, trùng, không nhất quán hoặc không bảo toàn dữ liệu |
| Integration | Không tương thích API, event, schema hoặc giao thức |
| Performance | Độ trễ, throughput hoặc sử dụng tài nguyên không đạt |
| Reliability | Timeout, mất kết nối, retry hoặc phục hồi không đúng |
| Security | Xác thực, phân quyền, lộ dữ liệu hoặc kiểm soát truy cập sai |
| Compatibility | Hành vi khác giữa trình duyệt, thiết bị, runtime hoặc phiên bản |
| Usability/accessibility | Luồng sử dụng hoặc khả năng tiếp cận không đáp ứng tiêu chí |
| Test automation | Test, fixture, helper, selector hoặc oracle không đúng |
| Environment/configuration | Cấu hình, hạ tầng hoặc môi trường kiểm thử không đúng |

Có thể gắn nhiều nhãn nếu lỗi thuộc nhiều nhóm. Taxonomy cần đủ đơn giản để người báo cáo chọn đúng và đủ chi tiết để phân tích xu hướng.

### Phân loại theo giai đoạn phát hiện

Ghi lỗi được phát hiện ở đâu:

- Trong phát triển hoặc code review.
- Unit/component test.
- Integration hoặc contract test.
- System/E2E.
- Staging hoặc acceptance.
- Production monitoring.
- Hỗ trợ khách hàng hoặc đối tác.

Thông tin này giúp đánh giá khoảng trống kiểm thử. Một lỗi chức năng lọt đến production có thể cho thấy thiếu test, test không được chạy, dữ liệu không đại diện hoặc cổng chất lượng chưa phù hợp.

### Phân loại theo phạm vi ảnh hưởng

Xác định đối tượng và phạm vi:

- Một người dùng hoặc một tài khoản.
- Một tenant hoặc một nhóm khách hàng.
- Một khu vực, vùng hoặc nền tảng.
- Một hành trình hoặc một loại giao dịch.
- Nhiều dịch vụ hoặc toàn hệ thống.
- Dữ liệu đã bị thay đổi hoặc có nguy cơ không thể phục hồi.
- Bảo mật, quyền riêng tư hoặc tuân thủ bị ảnh hưởng.

Phạm vi có thể thay đổi trong khi điều tra. Cần cập nhật khi có bằng chứng mới và ghi rõ thời điểm đánh giá.

### Phân loại theo khả năng tái hiện

Có thể dùng các nhãn:

- Luôn tái hiện với điều kiện đã ghi.
- Tái hiện theo một tỷ lệ hoặc điều kiện cụ thể.
- Chỉ xảy ra trong môi trường hoặc tải nhất định.
- Chưa tái hiện được nhưng có bằng chứng đáng tin.
- Đã được xác định là lỗi test hoặc môi trường.
- Không còn tái hiện sau thay đổi nhưng chưa xác minh nguyên nhân.

Không đóng lỗi chỉ vì một lần chạy lại pass. Với lỗi không ổn định, cần lưu lịch sử lần fail, seed và điều kiện đã thử.

## 5. Đánh giá severity và priority

### Severity đo mức độ nghiêm trọng

Severity phản ánh hậu quả nếu lỗi tồn tại. Nhóm có thể định nghĩa các mức như:

| Mức tham khảo | Ý nghĩa | Ví dụ |
|---|---|---|
| Critical | Ảnh hưởng nghiêm trọng, phạm vi rộng hoặc rủi ro an toàn/dữ liệu lớn | Lộ dữ liệu giữa tenant, mất dữ liệu quan trọng, dịch vụ cốt lõi ngừng hoạt động |
| High | Chức năng quan trọng bị hỏng, nhiều người dùng bị ảnh hưởng hoặc không có workaround phù hợp | Không thể hoàn tất thanh toán ở luồng chính |
| Medium | Một phần chức năng bị ảnh hưởng, có workaround hoặc phạm vi giới hạn | Bộ lọc báo cáo sai trong một tổ hợp điều kiện |
| Low | Tác động nhỏ, không ảnh hưởng đáng kể đến luồng chính | Lỗi căn chỉnh giao diện không cản trở thao tác |

Đây là ví dụ về taxonomy; tổ chức cần định nghĩa tiêu chí cụ thể theo sản phẩm và rủi ro. Severity không nên dựa trên cảm xúc hoặc chức danh của người báo cáo.

### Priority đo mức độ cần xử lý trước

Priority phản ánh thứ tự và thời điểm cần xử lý dựa trên rủi ro, cam kết, phụ thuộc và chi phí trì hoãn. Một lỗi severity cao thường có priority cao, nhưng không phải lúc nào cũng đồng nhất.

Ví dụ, một lỗi nghiêm trọng trong tính năng chưa được bật có thể cần xử lý trước release nhưng chưa gây incident đang diễn ra. Một lỗi mức trung bình đang chặn quy trình phát hành có thể cần ưu tiên ngay để tháo gỡ đường găng.

### Đánh giá bằng tiêu chí nhất quán

Khi xác định severity và priority, xem xét:

- Mức độ ảnh hưởng đến người dùng và hoạt động kinh doanh.
- Phạm vi và số lượng đối tượng bị ảnh hưởng.
- Khả năng mất, sai hoặc lộ dữ liệu.
- Khả năng có workaround an toàn.
- Tính thường xuyên và điều kiện kích hoạt.
- Khả năng phát hiện và phục hồi.
- Nghĩa vụ bảo mật, pháp lý hoặc hợp đồng.
- Thời điểm release và phụ thuộc của nhóm khác.
- Chi phí sửa muộn và nguy cơ lỗi lan rộng.

Ghi lý do cho mức đánh giá, đặc biệt khi severity và priority khác nhau hoặc có quyết định chấp nhận rủi ro.

### Định nghĩa cơ chế nâng mức

Mức độ có thể được nâng khi phát hiện thêm người dùng, vùng, dữ liệu hoặc tác động. Quy định ai có quyền nâng/giảm severity và priority, bằng chứng cần có và cách thông báo cho owner.

Không hạ severity chỉ để làm đẹp báo cáo hoặc đóng backlog. Khi giảm mức, phải lưu lý do và người quyết định.

## 6. Triage và quản lý backlog lỗi

### Mục tiêu của buổi triage

Triage là quá trình rà soát để xác nhận, phân loại, ưu tiên và quyết định bước tiếp theo. Một phiên triage hiệu quả trả lời:

- Đây có phải lỗi hợp lệ không?
- Có bản ghi trùng hoặc lỗi liên quan không?
- Phạm vi và tác động đã rõ đến đâu?
- Severity và priority phù hợp là gì?
- Có cần kích hoạt incident response không?
- Nhóm hoặc cá nhân nào chịu trách nhiệm?
- Có workaround, test bổ sung hoặc hành động giảm thiểu nào?
- Khi nào cần cập nhật lại?

Triage không nhất thiết phải là cuộc họp dài. Có thể dùng hàng đợi được quản lý với người chịu trách nhiệm và lịch xem xét phù hợp.

### Xử lý lỗi trùng

Trước khi tạo bản ghi mới, tìm lỗi cùng triệu chứng, điều kiện, phiên bản và thành phần. Nếu trùng:

- Liên kết bản ghi mới với lỗi chính.
- Bổ sung bằng chứng hoặc phạm vi ảnh hưởng.
- Ghi số lần và nhóm người gặp phải.
- Nâng priority nếu tần suất hoặc phạm vi tăng.
- Giữ lịch sử nguồn báo cáo.

Không gộp hai lỗi chỉ vì cùng thông báo lỗi nếu nguyên nhân hoặc tác động khác nhau.

### Chỉ định owner và người phối hợp

Mỗi lỗi đang mở cần có owner chịu trách nhiệm cho bước tiếp theo. Owner có thể là cá nhân hoặc nhóm, nhưng cần một đầu mối rõ.

Có thể phân vai:

- Người báo cáo: cung cấp điều kiện và bằng chứng.
- QA/triage: xác minh thông tin và phân loại.
- Owner kỹ thuật: điều tra và đề xuất sửa.
- Product owner: làm rõ hành vi mong đợi và quyết định ưu tiên nghiệp vụ.
- Incident commander hoặc người điều phối: điều phối phản ứng khi có incident.
- Người xác minh: kiểm tra bản sửa độc lập khi rủi ro yêu cầu.

Không để bản ghi ở trạng thái “đang xử lý” mà không có người và hành động tiếp theo.

### Quản lý thời hạn và trạng thái chờ

Nếu lỗi đang chờ thông tin, môi trường hoặc nhóm phụ thuộc, ghi rõ:

- Điều kiện đang chờ.
- Người hoặc nhóm cần phản hồi.
- Ngày cần cập nhật.
- Công việc có thể làm trong lúc chờ.
- Tác động nếu chậm.
- Điều kiện để tiếp tục.

Không để trạng thái Blocked hoặc Pending tồn tại vô thời hạn mà không được rà soát.

## 7. Điều tra và xác định nguyên nhân

### Tái hiện trong điều kiện được kiểm soát

Bắt đầu từ bản ghi và tái tạo:

- Cùng phiên bản hoặc commit.
- Cấu hình và feature flag liên quan.
- Môi trường hoặc điều kiện gần tương đương.
- Dữ liệu, seed và trạng thái ban đầu.
- Vai trò, quyền và tenant.
- Thứ tự sự kiện và mức concurrency.
- Thời điểm hoặc seed ngẫu nhiên khi có liên quan.

Nếu không thể tái hiện, không xóa bỏ bằng chứng ban đầu. Kiểm tra sự khác biệt giữa lần lỗi và lần chạy lại, như tải, timezone, phiên bản dependency, trạng thái queue hoặc dữ liệu đã bị cleanup.

### Dùng log, metric và trace

Với luồng nhiều dịch vụ, correlation ID hoặc trace ID giúp nối sự kiện từ đầu đến cuối. Điều tra cần xác định:

- Request đã được tiếp nhận chưa?
- Transaction có commit không?
- Message có được publish và consume không?
- Worker có retry hoặc chuyển DLQ không?
- Tác dụng phụ với nhà cung cấp đã xảy ra chưa?
- Read model hoặc cache đã hội tụ chưa?
- Có lỗi quyền, quota, timeout hoặc lock không?

Kết luận nên dựa trên nguồn dữ liệu có thẩm quyền. Log thiếu hoặc không liên kết là một khoảng trống cần ghi nhận như hành động cải tiến.

### Phân tích nguyên nhân gốc

Có thể dùng các phương pháp:

- **5 Whys:** hỏi tiếp “vì sao” để đi từ triệu chứng đến điều kiện nền.
- **Fishbone/Ishikawa:** nhóm nguyên nhân theo con người, quy trình, công nghệ, dữ liệu, môi trường và đo lường.
- **Fault tree:** phân tích tổ hợp điều kiện dẫn đến sự kiện không mong muốn.
- **Timeline analysis:** sắp xếp sự kiện theo thời gian để tìm race, timeout hoặc thứ tự sai.

Không dừng ở câu “người dùng thao tác sai” hoặc “test thiếu”. Cần xem xét vì sao hệ thống cho phép trạng thái không hợp lệ, vì sao test không phát hiện hoặc vì sao quy trình không ngăn được.

### Phân biệt nguyên nhân gốc với yếu tố góp phần

Một incident có thể có nhiều yếu tố:

- Trigger: sự kiện trực tiếp làm lỗi xuất hiện.
- Root cause: điều kiện nền khiến hệ thống có thể thất bại.
- Contributing factor: yếu tố làm tăng xác suất hoặc mức ảnh hưởng.
- Detection gap: lý do lỗi không được phát hiện sớm.
- Recovery gap: lý do việc khôi phục chậm hoặc không đầy đủ.

Ghi rõ mức độ chắc chắn. Nếu nguyên nhân chưa được xác minh, giữ trạng thái điều tra thay vì ghi một giả thuyết như kết luận.

## 8. Khắc phục và quản lý thay đổi

### Chọn loại hành động phù hợp

Hành động khắc phục có thể gồm:

- Sửa logic hoặc dữ liệu sản phẩm.
- Thay đổi API, schema, event hoặc hợp đồng.
- Sửa cấu hình hoặc hạ tầng.
- Thêm kiểm soát đầu vào, quyền hoặc validation.
- Cải thiện retry, idempotency và phục hồi.
- Sửa test, fixture, helper hoặc oracle.
- Thêm log, metric, trace hoặc cảnh báo.
- Cập nhật tài liệu, hướng dẫn vận hành hoặc đào tạo.

Một lỗi có thể cần nhiều hành động. Ví dụ, sửa worker để xử lý idempotent đồng thời bổ sung test cho message trùng và metric cho retry bất thường.

### Workaround và fix lâu dài

Workaround giảm tác động trong ngắn hạn nhưng có thể không loại bỏ nguyên nhân. Ví dụ, tắt tạm một feature flag hoặc rollback phiên bản có thể khôi phục dịch vụ, trong khi bản sửa lâu dài cần được phát triển và xác minh.

Bản ghi phải nêu:

- Workaround đang áp dụng.
- Rủi ro và giới hạn của workaround.
- Người chịu trách nhiệm theo dõi.
- Điều kiện gỡ workaround.
- Fix lâu dài và mốc dự kiến.
- Cách xác minh sau khi thay đổi.

Không đóng defect gốc chỉ vì incident đã được giảm tác động bằng workaround.

### Liên kết lỗi với thay đổi

Khi sửa, liên kết defect với:

- Pull request hoặc commit.
- Review và quyết định thiết kế.
- Migration hoặc thay đổi cấu hình.
- Test mới hoặc test đã cập nhật.
- Build và môi trường xác minh.
- Release chứa bản sửa.

Liên kết giúp truy vết từ lỗi đến thay đổi và chứng minh phiên bản nào đã bao gồm fix.

### Đánh giá rủi ro của bản sửa

Bản sửa có thể tạo hồi quy. Trước khi triển khai, đánh giá:

- Thành phần và consumer bị ảnh hưởng.
- Tương thích ngược.
- Dữ liệu cũ và migration.
- Quyền và bảo mật.
- Hành vi khi retry hoặc chạy song song.
- Khả năng rollback hoặc bù trừ.
- Test mục tiêu và phạm vi hồi quy cần chạy.

Không chỉ chạy lại test đã fail nếu thay đổi dùng chung hoặc ảnh hưởng nhiều luồng.

## 9. Xác minh bản sửa và tiêu chí đóng lỗi

### Xác minh đúng điều kiện đã gây lỗi

Sau khi có bản sửa:

1. Xác định build hoặc commit chứa fix.
2. Chuẩn bị lại dữ liệu và điều kiện gây lỗi.
3. Chạy test tái hiện hoặc kiểm tra tương đương.
4. Xác minh kết quả mong đợi.
5. Chạy hồi quy các luồng liên quan.
6. Kiểm tra tác dụng phụ và dữ liệu.
7. Thu thập report và artifact.
8. Cập nhật trạng thái và liên kết bằng chứng.

Nếu lỗi chỉ xảy ra trong production, có thể cần xác minh trong staging hoặc canary với điều kiện an toàn, đồng thời theo dõi metric sau triển khai.

### Thêm kiểm thử hồi quy phù hợp

Khi defect đã được xác nhận, cân nhắc thêm test ở cấp phù hợp:

- Unit test cho quy tắc hoặc nhánh logic.
- Component test cho trạng thái và tương tác nội bộ.
- Contract test cho API hoặc event.
- Integration test cho database, queue hoặc nhà cung cấp.
- E2E cho hành trình có rủi ro người dùng.
- Monitoring hoặc synthetic check cho hành vi cần theo dõi liên tục.

Không mặc định mọi lỗi đều cần E2E. Chọn cấp test có thể bắt lỗi sớm, ổn định và ít chi phí bảo trì, bổ sung test xuyên thành phần khi ranh giới tích hợp là một phần của nguyên nhân.

### Điều kiện đóng lỗi

Một defect có thể được đóng khi:

- Nguyên nhân hoặc phạm vi đã được hiểu đủ để xử lý.
- Bản sửa đã được review và nằm trong build xác định.
- Test tái hiện trước đây đã đạt hoặc có giải thích được phê duyệt.
- Hồi quy liên quan đã chạy theo kế hoạch.
- Không còn tác dụng phụ hoặc dữ liệu sai chưa được xử lý.
- Tài liệu, monitoring hoặc test đã được cập nhật khi cần.
- Bằng chứng xác minh được liên kết.
- Người có thẩm quyền chấp nhận rủi ro còn lại nếu có.

Nếu chỉ không tái hiện được mà không có thay đổi hay bằng chứng nguyên nhân, cân nhắc trạng thái Cannot reproduce hoặc Need information theo quy ước; không tự động đánh dấu Fixed.

### Mở lại lỗi

Mở lại khi:

- Lỗi tái xuất hiện trong điều kiện đã xác định.
- Bản sửa không có trong phiên bản được kiểm tra.
- Test hồi quy không bao phủ đúng nhánh.
- Tác dụng phụ hoặc dữ liệu sai vẫn còn.
- Workaround bị gỡ nhưng lỗi chưa được giải quyết.
- Bằng chứng mới cho thấy phạm vi rộng hơn.

Giữ lịch sử đóng và mở lại để phân tích chất lượng fix và độ chính xác của tiêu chí đóng.

## 10. Xử lý defect liên quan đến incident production

### Ưu tiên khôi phục và giảm tác động

Khi có incident, phản ứng ban đầu tập trung vào an toàn và dịch vụ:

- Xác nhận phạm vi và mức ảnh hưởng.
- Chỉ định người điều phối.
- Bảo toàn log, trace và dữ liệu cần điều tra.
- Giảm tác động bằng rollback, failover, feature flag hoặc biện pháp phù hợp.
- Thông báo cho các bên theo quy trình.
- Xác minh dịch vụ đã phục hồi.
- Theo dõi dấu hiệu tái diễn.

Không chờ hoàn tất root cause analysis mới khôi phục dịch vụ nếu đã có hành động giảm tác động an toàn.

### Liên kết incident và defect

Một incident có thể liên quan nhiều defect; một defect có thể gây nhiều incident. Dùng liên kết để phân biệt:

- Incident record: timeline, tác động, điều phối và khôi phục.
- Defect record: hành vi sai, nguyên nhân kỹ thuật và bản sửa.
- Problem record: mẫu lặp hoặc nguyên nhân hệ thống cần hành động dài hạn.

Nếu incident được khắc phục bằng cấu hình hoặc rollback, vẫn cần đánh giá có defect sản phẩm hoặc khoảng trống quy trình cần theo dõi không.

### Post-incident review

Sau khi dịch vụ ổn định, thực hiện review phù hợp mức độ sự cố:

- Timeline và quyết định chính.
- Phạm vi tác động và thời gian ảnh hưởng.
- Cách phát hiện và thời gian phản ứng.
- Điều gì giúp giảm tác động.
- Điều gì làm chậm điều tra hoặc khôi phục.
- Root cause và yếu tố góp phần.
- Hành động ngăn tái diễn.
- Owner, thời hạn và cách xác minh từng hành động.

Review nên tập trung vào hệ thống và điều kiện làm lỗi có thể xảy ra, không tìm người để đổ lỗi. Hành động cần có tiêu chí hoàn tất và được theo dõi đến khi đóng.

## 11. Quản lý trạng thái và quy tắc chuyển trạng thái

### Bộ trạng thái tham khảo

Có thể dùng các trạng thái:

| Trạng thái | Ý nghĩa |
|---|---|
| New | Vừa được ghi nhận, chưa triage |
| Triaged | Đã phân loại và xác định bước tiếp theo |
| Accepted | Xác nhận là lỗi cần xử lý |
| Assigned | Đã có owner |
| In progress | Đang điều tra hoặc sửa |
| Blocked | Chờ điều kiện hoặc nhóm khác |
| Ready for verification | Có bản sửa chờ xác minh |
| Verified | Đã xác minh đạt tiêu chí |
| Closed | Đã hoàn tất điều kiện đóng |
| Reopened | Lỗi tái xuất hiện hoặc fix không đạt |
| Deferred | Có quyết định hoãn và ghi nhận rủi ro |
| Duplicate | Liên kết đến bản ghi chính |
| Rejected/Not a defect | Có bằng chứng cho thấy không phải defect |

Tên trạng thái có thể khác theo công cụ. Điều quan trọng là định nghĩa rõ điều kiện vào/ra và ai có quyền chuyển.

### Kiểm soát chuyển trạng thái

Một số nguyên tắc:

- New sang Triaged cần đủ thông tin tối thiểu hoặc có yêu cầu bổ sung.
- Triaged sang Assigned cần owner và priority.
- In progress sang Ready for verification cần liên kết thay đổi và mô tả fix.
- Ready for verification sang Verified cần bằng chứng kiểm tra.
- Verified sang Closed cần đáp ứng tiêu chí đóng và xử lý rủi ro còn lại.
- Closed sang Reopened cần bằng chứng lỗi còn tồn tại hoặc tái xuất hiện.
- Deferred cần owner, lý do và ngày xem xét lại.

Không cho phép chuyển trạng thái chỉ để đáp ứng chỉ số backlog. Lịch sử chuyển trạng thái cần được lưu.

### Quản lý lỗi bị hoãn hoặc chấp nhận rủi ro

Nếu chưa sửa, ghi:

- Lý do hoãn.
- Severity và priority hiện tại.
- Phạm vi người dùng hoặc tính năng chịu ảnh hưởng.
- Workaround hoặc kiểm soát bù.
- Người chấp nhận rủi ro.
- Ngày xem xét lại hoặc điều kiện kích hoạt.
- Tác động nếu rủi ro xảy ra.

Deferred không có nghĩa lỗi đã được giải quyết. Cần rà soát khi sản phẩm, mức sử dụng hoặc điều kiện rủi ro thay đổi.

## 12. Đo lường và cải thiện quy trình lỗi

### Chọn chỉ số phản ánh chất lượng xử lý

Có thể theo dõi:

- Số defect mới theo loại, thành phần và giai đoạn phát hiện.
- Backlog theo severity, priority và tuổi lỗi.
- Thời gian từ phát hiện đến triage.
- Thời gian từ triage đến owner nhận xử lý.
- Thời gian đến khi xác định nguyên nhân.
- Thời gian từ fix đến verification và closure.
- Tỷ lệ lỗi bị mở lại.
- Tỷ lệ defect tái xuất hiện.
- Tỷ lệ incident có liên kết defect và hành động hậu kiểm.
- Tỷ lệ lỗi lọt qua từng tầng kiểm thử.
- Số lỗi bị deferred và tuổi của quyết định hoãn.

Cần định nghĩa cách đo nhất quán. Ví dụ, thời gian xử lý không nên chỉ tính từ lúc bắt đầu sửa code nếu thời gian chờ triage hoặc owner cũng là một phần của quy trình.

### Phân tích xu hướng thay vì chạy theo số lượng

Số defect tăng có thể do chất lượng giảm, nhưng cũng có thể do khả năng phát hiện và ghi nhận tốt hơn. Số defect giảm không nhất thiết chứng minh chất lượng tăng nếu nhóm ghi nhận thiếu hoặc đóng lỗi quá sớm.

Kết hợp số liệu với:

- Mức độ nghiêm trọng.
- Tỷ lệ lỗi lọt production.
- Mức độ bao phủ test.
- Tỷ lệ tái diễn và mở lại.
- Thời gian phát hiện và khôi phục.
- Phản hồi người dùng.
- Chất lượng bằng chứng và phân loại.

### Rà soát backlog định kỳ

Trong mỗi lần rà soát:

- Xác nhận owner và bước tiếp theo.
- Kiểm tra lỗi quá hạn hoặc bị blocked lâu.
- Xem xét severity/priority có thay đổi không.
- Loại trùng và liên kết lỗi liên quan.
- Rà soát lỗi deferred và kiểm soát bù.
- Xác định lỗi có thể giải quyết bằng cải tiến chung.
- Cập nhật kế hoạch hồi quy hoặc testability.

Một nhóm lỗi cùng nguyên nhân có thể cho thấy vấn đề kiến trúc hoặc quy trình lớn hơn một defect đơn lẻ.

## 13. Ví dụ: ghi nhận và xử lý lỗi thanh toán

Giả sử trong E2E, người dùng áp mã giảm giá và thanh toán thành công ở sandbox. Giao dịch phía nhà cung cấp báo thành công nhưng đơn hàng trong sản phẩm vẫn ở trạng thái PROCESSING sau thời gian chờ đã định.

### Ghi nhận ban đầu

**Tiêu đề:** Đơn hàng vẫn PROCESSING sau callback thanh toán thành công khi có mã giảm giá.

Thông tin cần có:

- Build và commit được kiểm tra.
- Môi trường và tenant thử nghiệm.
- Order ID, payment reference và event ID đã che giấu thông tin nhạy cảm.
- Mã giảm giá, tiền tệ và số tiền kỳ vọng.
- Các bước tạo đơn và thanh toán.
- Thời điểm callback và trạng thái quan sát được.
- Expected: đơn chuyển sang PAID trong giới hạn đã định.
- Actual: đơn vẫn PROCESSING sau timeout.
- Correlation ID, trace và log worker.
- Số lần tái hiện và seed/fixture nếu có.

### Phân loại và triage

Ban đầu có thể phân loại là lỗi integration hoặc reliability, mức severity và priority được đánh giá theo phạm vi giao dịch bị ảnh hưởng và khả năng có workaround. Nếu đang xảy ra trên production và ngăn thanh toán hoàn tất, kích hoạt quy trình incident tương ứng.

Triage cần xác minh callback có được nhận, event có được publish, consumer có xử lý và transaction cập nhật có commit hay không. Không kết luận nhà cung cấp lỗi chỉ vì trạng thái cuối bị chậm.

### Điều tra và khắc phục

Giả sử trace cho thấy worker nhận event nhưng transaction rollback vì trường discount amount không được ánh xạ đúng. Hành động có thể gồm:

- Sửa mapping và validation dữ liệu.
- Bổ sung test cho đơn có và không có giảm giá.
- Thêm integration test cho callback và trạng thái đơn.
- Bổ sung metric cho event nhận, xử lý, retry và rollback.
- Đối soát các đơn đã bị ảnh hưởng nếu lỗi từng xảy ra ở production.

Nếu incident đang mở, workaround có thể là quy trình đối soát hoặc xử lý thủ công được kiểm soát cho giao dịch liên quan. Workaround phải có owner và điều kiện gỡ.

### Xác minh và đóng

Sau fix:

- Chạy test tái hiện với fixture giảm giá.
- Chạy contract/integration test callback.
- Chạy E2E thanh toán và hoàn tiền liên quan.
- Xác minh không tạo giao dịch hoặc event trùng khi retry.
- Kiểm tra dữ liệu đơn và payment reference.
- Lưu report, trace và commit chứa fix.
- Đóng defect khi đủ bằng chứng; đóng incident theo tiêu chí phục hồi và hậu kiểm riêng.

Ví dụ cho thấy bản ghi lỗi, incident, điều tra nguyên nhân, hành động khắc phục và xác minh cần liên kết nhưng có tiêu chí hoàn tất riêng.

## 14. Những sai lầm thường gặp

- **Chỉ ghi tiêu đề ngắn:** người nhận không thể tái hiện hoặc đánh giá tác động.
- **Gộp giả thuyết vào sự kiện:** làm nhóm điều tra theo hướng sai.
- **Đồng nhất test fail với defect sản phẩm:** bỏ qua lỗi test, dữ liệu và môi trường.
- **Dùng severity và priority như một trường:** không phân biệt mức độ nghiêm trọng với thứ tự xử lý.
- **Không có owner:** lỗi nằm trong backlog nhưng không có bước tiếp theo.
- **Chuyển lỗi qua chat mà không cập nhật bản ghi:** mất lịch sử và bằng chứng.
- **Gộp lỗi chỉ vì cùng thông báo:** che giấu nguyên nhân hoặc phạm vi khác nhau.
- **Đóng lỗi khi test chỉ pass một lần:** bỏ qua khả năng flaky hoặc điều kiện gây lỗi chưa được tái tạo.
- **Đóng defect khi incident đã khôi phục:** nguyên nhân gốc vẫn còn.
- **Retry hoặc workaround mà không đối soát:** có thể tạo tác dụng phụ trùng.
- **Không thêm test hồi quy:** lỗi đã sửa có thể tái xuất hiện.
- **Giữ lỗi deferred vô thời hạn:** rủi ro không còn được xem xét.
- **Chỉ đo số defect:** khuyến khích đóng nhiều lỗi thay vì cải thiện chất lượng.
- **Review incident theo hướng đổ lỗi:** làm giảm khả năng báo cáo và học hỏi.
- **Không giữ bằng chứng có kiểm soát:** khó điều tra hoặc vô tình lưu dữ liệu nhạy cảm.

## 15. Đầu ra cần có trước khi chốt quy trình ghi nhận, phân loại và xử lý lỗi

Một quy trình đủ dùng nên có:

1. **Từ điển khái niệm:** defect, incident, test failure, problem và root cause.
2. **Luồng vòng đời:** phát hiện, ghi nhận, triage, giao owner, điều tra, sửa, xác minh và đóng.
3. **Mẫu bản ghi lỗi:** triệu chứng, điều kiện, expected/actual, bước tái hiện, môi trường và bằng chứng.
4. **Taxonomy:** loại lỗi, nguồn phát hiện, phạm vi và khả năng tái hiện.
5. **Ma trận severity/priority:** tiêu chí, quyền quyết định và quy tắc nâng mức.
6. **Quy tắc triage:** loại trùng, chấp nhận, từ chối, hoãn và xử lý lỗi chưa xác định.
7. **Ma trận vai trò:** người báo cáo, QA, owner kỹ thuật, product owner và incident coordinator.
8. **Quy trình điều tra:** tái hiện, log/trace, phân tích nguyên nhân và mức độ chắc chắn.
9. **Quy trình khắc phục:** workaround, fix lâu dài, liên kết thay đổi và đánh giá rủi ro.
10. **Tiêu chí xác minh/đóng:** test mục tiêu, hồi quy, bằng chứng và điều kiện mở lại.
11. **Quy trình incident:** giảm tác động, khôi phục, liên kết defect và post-incident review.
12. **Chỉ số và lịch rà soát:** backlog, tuổi lỗi, thời gian xử lý, lỗi mở lại và xu hướng lỗi lọt.

Trước khi áp dụng, hãy rà soát:

- Người báo cáo có biết nơi ghi nhận và thông tin tối thiểu cần cung cấp không?
- Bản ghi có ID, phiên bản, môi trường, bước tái hiện và expected/actual không?
- Bằng chứng có thể truy vết và được bảo vệ dữ liệu nhạy cảm không?
- Defect, incident và test failure có được phân biệt không?
- Severity và priority có tiêu chí và người quyết định rõ không?
- Mỗi lỗi đang mở có owner và bước tiếp theo không?
- Lỗi trùng, lỗi blocked và lỗi deferred có được quản lý không?
- Điều tra có phân biệt sự kiện, giả thuyết và kết luận không?
- Bản sửa có liên kết commit, build và test hồi quy không?
- Tiêu chí đóng và mở lại có bằng chứng không?
- Incident có được khôi phục trước, rồi liên kết với defect và hành động ngăn tái diễn không?
- Chỉ số có đo chất lượng xử lý thay vì chỉ đếm số lỗi không?

Thống nhất quy trình ghi nhận, phân loại và xử lý lỗi giúp thông tin không bị thất lạc giữa các nhóm, ưu tiên phản ánh đúng rủi ro và mỗi bản sửa được xác minh trước khi đóng. Khi quy trình kết nối kiểm thử, phát triển và vận hành, nhóm có thể rút ngắn thời gian từ phát hiện đến nguyên nhân, giảm lỗi tái diễn và biến mỗi defect hoặc incident thành cơ hội cải thiện sản phẩm cùng hệ thống kiểm thử.

