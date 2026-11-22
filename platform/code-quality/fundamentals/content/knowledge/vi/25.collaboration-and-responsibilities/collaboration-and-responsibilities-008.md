# Cân bằng tiến độ với công việc duy trì chất lượng

> **Chương:** Cộng tác và trách nhiệm  
> **Học phần:** CODE_QUALITY_FUNDAMENTALS — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao tốc độ giao hàng và chất lượng mã là hai yếu tố cùng quyết định khả năng tạo giá trị lâu dài.
2. Phân biệt **tiến độ sản phẩm**, **công việc duy trì chất lượng** và **việc xử lý rủi ro cấp bách**.
3. Nhận diện chi phí trì hoãn bảo trì qua thời gian sửa đổi, lỗi lặp lại, vòng phản hồi chậm, incident và rủi ro vận hành.
4. Đưa công việc chất lượng vào kế hoạch sản phẩm bằng mục tiêu, bằng chứng, người sở hữu và tiêu chí hoàn tất rõ ràng.
5. Chọn mức kiểm tra phù hợp với rủi ro thay đổi mà vẫn duy trì phản hồi nhanh.
6. Thảo luận trade-off về thời gian, phạm vi, rủi ro và chi phí bằng ngôn ngữ minh bạch, không biến chất lượng thành một khẩu hiệu hoặc KPI đơn lẻ.
7. Phân công trách nhiệm giữa product, engineering, QA, operations và người sở hữu hệ thống để chất lượng không trở thành việc riêng của một vai trò.
8. Sử dụng chỉ số ở cấp nhóm/hệ thống để phát hiện điểm nghẽn, đồng thời tránh xếp hạng cá nhân hoặc khuyến khích che giấu vấn đề.
9. Xây dựng kế hoạch duy trì chất lượng theo từng bước, đo kết quả và điều chỉnh theo bối cảnh thực tế.

## 1. Tiến độ và chất lượng cùng tạo nên năng lực giao hàng

Một nhóm có thể hoàn thành tính năng trong hai ngày bằng cách bỏ test hồi quy, sao chép logic và triển khai trực tiếp vào production. Bản phát hành có thể đến sớm hơn. Nhưng nếu tuần sau mỗi thay đổi nhỏ đều gây lỗi, nhóm phải dành nhiều thời gian điều tra và sửa nóng, thì lợi thế ban đầu có thể nhanh chóng biến mất.

Một nhóm khác dành thêm thời gian làm rõ hợp đồng API, tự động hóa kiểm thử ở ranh giới quan trọng và thiết lập quan sát sau phát hành. Lần đầu có thể chậm hơn một chút, nhưng các lần thay đổi sau dễ dự đoán hơn.

Điều này không có nghĩa lúc nào cũng phải chọn phương án hoàn hảo. Sản phẩm cần học từ người dùng, đáp ứng thời hạn và xử lý nhu cầu thật. Chất lượng kỹ thuật giúp nhóm **tiếp tục giao hàng mà không làm mỗi lần thay đổi trở nên đắt đỏ và rủi ro hơn**.

Có thể nhìn năng lực giao hàng qua ba câu hỏi:

- **Giá trị:** thay đổi có giải quyết vấn đề đúng lúc cho người dùng không?
- **Độ tin cậy:** thay đổi có bảo vệ dữ liệu, hợp đồng, bảo mật và hành vi quan trọng không?
- **Khả năng tiếp tục:** sau khi phát hành, nhóm còn có thể hiểu, sửa và mở rộng hệ thống với chi phí hợp lý không?

Tối ưu một câu hỏi mà bỏ hai câu còn lại thường tạo ra kết quả ngắn hạn nhưng làm suy yếu năng lực của nhóm.

> **Tiến độ bền vững là khả năng đưa thay đổi có giá trị tới người dùng một cách đều đặn, với mức rủi ro và chi phí bảo trì có thể quản lý.**

## 2. Phân biệt công việc giao tính năng và công việc duy trì chất lượng

Hai nhóm công việc thường được lập kế hoạch riêng, nhưng trên thực tế chúng liên hệ chặt chẽ.

| Loại công việc | Mục tiêu | Ví dụ |
| --- | --- | --- |
| **Phát triển sản phẩm** | Tạo hoặc thay đổi khả năng người dùng cần | Thêm thanh toán bằng phương thức mới |
| **Duy trì chất lượng** | Giữ hệ thống đáng tin cậy và dễ thay đổi | Bổ sung contract test, loại logic nhân bản, giảm flaky test |
| **Vận hành và phục hồi** | Giữ dịch vụ hoạt động, phát hiện và xử lý sự cố | Cải thiện alert, diễn tập rollback, nâng cấp bản vá bảo mật |
| **Khám phá và giảm bất định** | Làm rõ giả định trước khi đầu tư lớn | Prototype tích hợp, benchmark workload, kiểm chứng API đối tác |
| **Nâng cấp nền tảng** | Giảm rủi ro công nghệ hoặc đáp ứng yêu cầu mới | Nâng runtime, thư viện, database hoặc pipeline |

Một công việc có thể thuộc nhiều loại. Ví dụ thêm phương thức thanh toán mới vừa là tính năng, vừa cần idempotency, audit và kiểm thử lỗi để bảo vệ giao dịch.

Không nên xem công việc duy trì chất lượng là “việc phụ chỉ làm khi hết feature”. Nếu test pipeline hỏng thường xuyên, nếu module thanh toán không thể thay đổi an toàn, hoặc nếu dependency có lỗ hổng nghiêm trọng, những việc đó trực tiếp ảnh hưởng khả năng giao hàng.

### Đừng gom mọi việc kỹ thuật vào một backlog không phân loại

Một backlog duy trì chất lượng hữu ích cần phân biệt:

- **Rủi ro cần xử lý ngay:** lỗ hổng đang bị khai thác, dữ liệu sai, lỗi mất tiền hoặc vi phạm nghĩa vụ.
- **Điểm nghẽn thường xuyên:** CI chậm, test flaky, quy trình release thủ công.
- **Nợ kỹ thuật có chi phí quan sát:** thay đổi lặp lại nhiều nơi, khó test hoặc khó điều tra.
- **Cải thiện phòng ngừa:** nâng chất lượng contract test, logging, tài liệu vận hành.
- **Nâng cấp có thời hạn:** runtime hoặc dependency sắp hết hỗ trợ.

Phân loại giúp chọn cách ưu tiên phù hợp. Không nên đặt một lỗi phân quyền cùng mức với việc đổi tên class, cũng không nên dùng mọi cảnh báo kỹ thuật để chặn một tính năng không liên quan.

## 3. Chất lượng tạo ra hoặc lấy đi thời gian trong tương lai

Chi phí của một lựa chọn kỹ thuật không chỉ xuất hiện trong PR hiện tại. Nó còn thể hiện ở những lần thay đổi tiếp theo.

Ví dụ một quy tắc tính giá VIP được sao chép trong báo giá, checkout và báo cáo. Lúc đầu mỗi bản sao chỉ vài dòng. Khi chính sách thay đổi:

1. Người phát triển phải tìm tất cả nơi có quy tắc.
2. Reviewer phải xác minh các nơi được sửa đồng bộ.
3. Test phải kiểm tra nhiều đường đi.
4. Một nơi bị bỏ sót có thể tạo sai khác giữa giá hiển thị và số tiền thu.
5. Nhóm phải điều tra và sửa dữ liệu hoặc giao dịch bị ảnh hưởng.

Nếu hợp nhất đúng chính sách và bảo vệ bằng test, thay đổi tiếp theo có thể ít tốn công hơn. **Giá trị của bảo trì không chỉ là mã đẹp hơn, mà là giảm công việc lặp lại và giảm xác suất xảy ra lỗi.**

### Chi phí thường ẩn trong công việc hằng ngày

- Thời gian chờ CI hoặc chạy lại test không ổn định.
- Thời gian tìm người biết một module cũ.
- Review kéo dài vì hợp đồng và ý định không rõ.
- Release cần nhiều bước thủ công hoặc phụ thuộc một cá nhân.
- Incident tái diễn vì thiếu test, telemetry hoặc runbook.
- Migration phải thực hiện nhiều lần do schema và caller không được quản lý.
- Onboarding chậm vì không biết cách chạy, kiểm tra và triển khai hệ thống.

Những chi phí này có thể không xuất hiện thành một ticket lớn, nhưng tích lũy qua từng thay đổi.

### Không phải mọi cải tiến đều hoàn vốn ngay

Một module ít thay đổi, có ranh giới ổn định và sắp bị thay thế có thể chưa cần refactor toàn diện. Một framework tổng quát cho yêu cầu chưa xuất hiện có thể tạo thêm abstraction và chi phí bảo trì.

Câu hỏi không phải “có thể cải thiện không?”, mà là:

- Vấn đề có ảnh hưởng thực tế hoặc rủi ro đáng kể không?
- Khu vực này có tiếp tục thay đổi không?
- Có bước nhỏ nào giảm chi phí hoặc rủi ro?
- Chi phí làm ngay so với trì hoãn là bao nhiêu?
- Có lựa chọn nào ít rủi ro hơn như test, adapter, giới hạn phạm vi hoặc theo dõi?

## 4. Không đánh đổi những bất biến chất lượng cốt lõi

Một thời hạn gấp có thể yêu cầu giảm phạm vi, dùng giải pháp đơn giản hơn hoặc trì hoãn một cải tiến có lợi ích chưa chắc chắn. Nhưng một số yêu cầu phải được bảo vệ ngay cả khi áp lực tiến độ cao.

Ví dụ:

- Không để người dùng đọc hoặc sửa dữ liệu ngoài quyền.
- Không báo thanh toán thành công khi trạng thái chưa được xác nhận.
- Không âm thầm làm mất hoặc nhân đôi giao dịch.
- Không đưa bí mật vào mã nguồn hoặc log không được bảo vệ.
- Không bỏ kiểm soát dữ liệu đầu vào ở ranh giới tin cậy.
- Không phát hành migration có thể làm hỏng dữ liệu mà không có kế hoạch khôi phục phù hợp.

Những yêu cầu này là **guardrails**: ranh giới an toàn cho phép nhóm lựa chọn cách triển khai linh hoạt bên trong.

### Phân biệt bất biến với mức hoàn thiện có thể điều chỉnh

| Có thể điều chỉnh theo bối cảnh | Không được bỏ qua khi liên quan |
| --- | --- |
| Phạm vi tính năng trong đợt đầu | Quyền truy cập và cách ly tenant |
| Mức tổng quát hóa kiến trúc | Tính đúng đắn của dữ liệu và giao dịch |
| Tài liệu thiết kế dài hay ngắn | Hướng dẫn vận hành tối thiểu cho thay đổi có rủi ro |
| Tối ưu hiệu năng chưa có bằng chứng cần thiết | Ngưỡng hiệu năng/SLA đã cam kết và đo được |
| Refactor vùng ít thay đổi | Xử lý defect nghiêm trọng và lỗ hổng đã xác định |
| Tự động hóa một bước ít rủi ro | Kiểm soát phát hành và khả năng rollback khi cần |

Một giải pháp có thể chưa tổng quát, chưa tối ưu hoặc còn giới hạn được công bố. Nhưng nó cần bảo vệ các bất biến quan trọng và không che giấu rủi ro.

## 5. Đưa công việc chất lượng vào kế hoạch từ đầu

Nếu đợi đến cuối dự án mới hỏi “đã có thời gian viết test chưa?”, nhóm dễ phải chọn giữa trì hoãn release và phát hành khi chưa có bằng chứng đủ tốt.

Thay vào đó, khi lập kế hoạch tính năng, hãy xác định cùng lúc:

- Hành vi và giá trị người dùng cần.
- Rủi ro nghiệp vụ và kỹ thuật.
- Test ở những ranh giới quan trọng.
- Quan sát cần có sau phát hành.
- Tài liệu hoặc runbook cần cập nhật.
- Migration, rollback và tương thích.
- Công việc duy trì nào phải hoàn tất để thay đổi có thể vận hành an toàn.

Ví dụ tính năng chuyển tiền giữa hai tài khoản không chỉ gồm form và endpoint. Nó cần xác định transaction, kiểm soát số dư, idempotency, audit, phân quyền, xử lý timeout và đối soát. Những phần này là **một phần của việc giao tính năng**, không phải phần trang trí thêm sau khi code xong.

### Lập kế hoạch theo kết quả, không chỉ theo hoạt động

| Hoạt động | Kết quả cần đạt |
| --- | --- |
| Viết unit test | Quy tắc tính tiền được kiểm tra ở ngưỡng và trường hợp lỗi |
| Thêm contract test | Client và server thống nhất schema/error behavior |
| Bổ sung telemetry | Có thể nhận biết giao dịch ở trạng thái chờ hoặc thất bại |
| Cải thiện rollback | Có cách quay lại phiên bản an toàn mà không làm sai dữ liệu |
| Refactor policy | Một quy tắc nghiệp vụ có một nơi sở hữu rõ ràng |
| Viết runbook | Người trực có thể chẩn đoán và xử lý sự cố phổ biến |

Nếu không biết công việc sẽ làm thay đổi rủi ro hoặc khả năng vận hành thế nào, cần làm rõ mục tiêu trước khi đưa vào kế hoạch.

## 6. Xác định Definition of Done có ý nghĩa

**Definition of Done (DoD)** là tập tiêu chí chung để nhóm xác định một thay đổi đủ hoàn tất. DoD không nên là một checklist dài giống nhau cho mọi thay đổi; nó cần phản ánh mức rủi ro và tiêu chuẩn của sản phẩm.

Một DoD nền tảng có thể gồm:

- Hành vi đáp ứng acceptance criteria đã thống nhất.
- Các kiểm tra tự động phù hợp đã chạy và đạt.
- Thay đổi được review theo quy trình nhóm.
- Quyền, dữ liệu, logging và lỗi được xem xét khi có liên quan.
- Tài liệu API, schema hoặc hướng dẫn vận hành được cập nhật nếu bị ảnh hưởng.
- Có kế hoạch rollout/rollback phù hợp với mức độ rủi ro.
- Không còn blocker chưa được giải quyết hoặc chấp nhận rõ bởi người có thẩm quyền.

### DoD theo loại thay đổi

| Loại thay đổi | Bằng chứng bổ sung có thể cần |
| --- | --- |
| Đổi nhãn UI | Test hiển thị hoặc kiểm tra accessibility phù hợp |
| Đổi logic giá | Test biên, đối soát, kiểm tra đơn vị tiền và caller |
| Đổi API công khai | Contract test, versioning và kiểm tra consumer |
| Đổi schema database | Migration test, backup/rollback và kiểm tra dữ liệu |
| Đổi xác thực/phân quyền | Test âm tính, kiểm tra tenant và audit |
| Đổi pipeline/release | Diễn tập đường deploy/rollback và quyền truy cập |
| Đổi query nóng | Benchmark workload đại diện và telemetry sau phát hành |

DoD nên ngăn việc “xong code” bị nhầm thành “đã sẵn sàng cho người dùng”. Nhưng không nên bắt một thay đổi tài liệu đơn giản chạy một bộ kiểm thử tải production không liên quan.

## 7. Chọn mức kiểm tra theo rủi ro

Không phải mọi thay đổi cần cùng độ sâu kiểm thử. Một sửa chính tả không có cùng rủi ro với thay đổi logic ghi nhận giao dịch.

Có thể đánh giá theo các chiều:

1. **Tác động:** nếu sai, người dùng hoặc dữ liệu bị ảnh hưởng thế nào?
2. **Khả năng xảy ra:** có đường lỗi hợp lý nào không?
3. **Phạm vi ảnh hưởng:** một người, một tenant, toàn hệ thống hay đối tác?
4. **Khả năng phát hiện:** monitoring/test có phát hiện sớm không?
5. **Khả năng phục hồi:** rollback hoặc sửa dữ liệu có an toàn không?
6. **Mức bất định:** nhóm đã hiểu rõ hành vi và phụ thuộc chưa?

| Mức rủi ro minh họa | Ví dụ | Bằng chứng phù hợp |
| --- | --- | --- |
| Thấp | Sửa nội dung hướng dẫn không ảnh hưởng code | Review nội dung và kiểm tra link nếu cần |
| Trung bình | Thêm bộ lọc danh sách | Unit/component test, kiểm tra quyền và query |
| Cao | Thay logic giá/hoàn tiền | Test biên, integration, đối soát và review chuyên môn |
| Rất cao | Thay cơ chế xác thực hoặc migration giao dịch | Threat/risk review, test rộng, kế hoạch rollout/rollback và giám sát |

Đây là cách phân loại minh họa. Nhóm cần thống nhất tiêu chí thực tế và cập nhật khi sản phẩm thay đổi.

### Tự động hóa phản hồi nhanh và phản hồi sâu

Có thể tổ chức nhiều lớp:

- **Mỗi commit/PR:** formatter, compiler, unit test và static checks phù hợp.
- **Trước merge hoặc release:** integration/contract/security checks theo phạm vi.
- **Theo lịch hoặc trước mốc lớn:** load test, dependency review, disaster recovery drill.
- **Sau phát hành:** telemetry, alert, error budget và kiểm tra hành vi thực tế.

Mục tiêu là phát hiện vấn đề càng gần thời điểm tạo ra càng tốt, đồng thời dành kiểm tra tốn kém cho nơi có rủi ro tương ứng.

## 8. Giữ vòng phản hồi ngắn để tiến độ không bị mắc kẹt

Một pipeline mất 45 phút, có test flaky và chỉ báo lỗi ở cuối khiến kỹ sư phải chờ lâu mới biết thay đổi sai. Nhóm có thể phản ứng bằng cách bỏ test hoặc gom nhiều thay đổi lớn để tiết kiệm thời gian CI. Điều đó lại làm lỗi khó định vị.

Hãy xem thời gian phản hồi là một phần của chất lượng quy trình:

- Chạy kiểm tra rẻ và có giá trị cao trước.
- Chia test theo unit, integration và end-to-end.
- Chỉ chạy lại phần liên quan khi có thể đảm bảo tính đúng đắn.
- Loại nguyên nhân flaky thay vì chấp nhận retry vô hạn.
- Làm thông báo lỗi dễ đọc và có hướng chẩn đoán.
- Đặt môi trường test có dữ liệu độc lập, dễ tái tạo.
- Theo dõi thời gian chờ CI và thời gian sửa lỗi, không chỉ tổng thời lượng job.

### Không tối ưu CI bằng cách xóa kiểm tra quan trọng

Nếu test chậm, cần tìm nguyên nhân: khởi động môi trường, truy cập mạng, dữ liệu dùng chung, query kém hoặc test end-to-end quá rộng. Có thể chuyển một số kiểm tra sang lịch chạy hoặc release gate nếu rủi ro cho phép, nhưng phải có **lý do, phạm vi và cách phát hiện hồi quy**.

## 9. Dành chỗ cho bảo trì mà không đặt một tỷ lệ cứng cho mọi nhóm

Một nhóm có thể dành một phần năng lực mỗi chu kỳ cho nợ kỹ thuật, test, nâng cấp và vận hành. Đây là cách lập kế hoạch hữu ích, nhưng không có một tỷ lệ phần trăm đúng cho mọi sản phẩm.

- Nhóm đang xử lý nhiều incident có thể cần ưu tiên phục hồi và giảm nguyên nhân tái diễn.
- Nhóm đang mở rộng tính năng trên module ổn định có thể dành ít công sức hơn cho refactor tổng quát.
- Nhóm sắp nâng cấp runtime có deadline hỗ trợ có thể cần tập trung migration trong một giai đoạn.
- Nhóm đang xây sản phẩm mới có thể cần đầu tư sớm vào pipeline, quan sát và hợp đồng nền tảng.

Có thể dùng capacity allocation như **giả thuyết ban đầu**, sau đó điều chỉnh theo bằng chứng. Nếu mọi chu kỳ đều không còn chỗ cho bảo trì, đó là tín hiệu cần trao đổi về kế hoạch và chi phí hệ thống. Nếu backlog bảo trì luôn chiếm phần lớn nhưng ít việc tạo giá trị, cần xem lại cách chọn và phạm vi các mục đó.

### Ba cách tổ chức phổ biến

| Cách tổ chức | Phù hợp khi | Rủi ro cần quản lý |
| --- | --- | --- |
| **Đưa bảo trì vào từng feature** | Công việc chất lượng gắn chặt với thay đổi | Dễ bị quên nếu acceptance criteria không nêu rõ |
| **Dành capacity theo chu kỳ** | Có danh sách điểm nghẽn và mục tiêu cải thiện rõ | Dễ chọn việc kỹ thuật ít tác động nếu thiếu ưu tiên |
| **Đợt cải tiến tập trung** | Có migration/nâng cấp cần phối hợp lớn | Có thể trì hoãn quá lâu hoặc làm gián đoạn roadmap |

Nhiều nhóm kết hợp cả ba. Điều quan trọng là bảo trì phải có người sở hữu, lý do và kết quả mong đợi.

## 10. Ưu tiên công việc chất lượng bằng tác động và bằng chứng

Không phải mọi mục trong backlog chất lượng đều quan trọng ngang nhau. Một cảnh báo style ở module ít thay đổi có thể chờ; một lỗi phân quyền có thể cần xử lý ngay.

Khi sắp xếp, xem xét:

- Mức nghiêm trọng nếu lỗi xảy ra.
- Tần suất và số người dùng bị ảnh hưởng.
- Tần suất khu vực code cần thay đổi.
- Chi phí sửa hiện tại và chi phí lặp lại.
- Khả năng phát hiện và phục hồi.
- Thời hạn hỗ trợ hoặc nghĩa vụ bảo mật.
- Chi phí và rủi ro của việc cải tiến.
- Cơ hội kết hợp với thay đổi sản phẩm sắp tới.

### Ma trận ưu tiên minh họa

| Công việc | Bằng chứng/tác động | Hướng xử lý |
| --- | --- | --- |
| Lỗi có thể đọc dữ liệu tenant khác | Rủi ro bảo mật nghiêm trọng | Xử lý theo quy trình bảo mật, không chờ backlog thường |
| Test thanh toán flaky | PR thường phải chạy lại, feedback chậm | Ưu tiên cô lập dữ liệu và sửa nguyên nhân |
| Logic giá nhân bản ở nhiều luồng | Đã có sai khác giữa báo giá và checkout | Sửa defect, hợp nhất policy và test caller |
| Nâng version formatter | Không có rủi ro hỗ trợ hoặc chức năng | Lên kế hoạch khi phù hợp |
| Refactor module ổn định, ít thay đổi | Chưa có chi phí cụ thể | Thu thập bằng chứng, có thể chưa làm |
| Thiếu runbook cho thao tác khôi phục | Người trực không biết cách xử lý sự cố | Bổ sung trước khi mở rộng phạm vi vận hành |

Đừng tạo một điểm số duy nhất bằng cách cộng độ nghiêm trọng, tần suất và effort nếu chưa có cơ sở cho trọng số. Ma trận giúp trao đổi; quyết định vẫn cần bối cảnh.

## 11. Làm rõ trade-off thay vì nói chung chung “cần nhanh” hoặc “cần sạch”

Khi thời hạn không đủ để làm tất cả, nhóm cần lựa chọn minh bạch giữa:

- Phạm vi tính năng.
- Thời điểm phát hành.
- Mức rủi ro chấp nhận.
- Chi phí vận hành và bảo trì.
- Mức độ chắc chắn về yêu cầu.

Ví dụ một đối tác cần tích hợp trong tuần này, nhưng API còn một số hành vi chưa rõ. Nhóm có thể:

1. Giảm phạm vi tích hợp xuống một luồng có thể kiểm chứng.
2. Giữ các guardrail về xác thực, idempotency và xử lý lỗi.
3. Đưa phần tự động hóa hoặc tiện ích chưa thiết yếu sang đợt sau.
4. Giới hạn rollout cho một nhóm người dùng.
5. Theo dõi lỗi và có cách tắt/rollback.
6. Ghi lại phần còn thiếu, người sở hữu và điều kiện hoàn tất.

Đây là một trade-off có quản lý. Phát hành toàn bộ tích hợp mà không hiểu trạng thái timeout hoặc retry có thể tạo rủi ro giao dịch không chấp nhận được.

### Mẫu ghi nhận quyết định

~~~text
Mục tiêu:
  Đưa luồng thanh toán cơ bản tới nhóm thử nghiệm trong tuần này.

Phạm vi phát hành:
  Chỉ hỗ trợ một phương thức thanh toán và một thị trường.

Guardrails:
  Xác thực quyền, idempotency, ghi nhận trạng thái giao dịch,
  xử lý timeout và khả năng đối soát phải hoàn tất.

Phần trì hoãn:
  Dashboard phân tích nâng cao và tối ưu query chưa có bằng chứng cần thiết.

Rủi ro còn lại:
  Một số báo cáo chưa tự động tổng hợp; nhóm vận hành dùng quy trình
  đối soát thủ công đã được kiểm tra trong giai đoạn thử nghiệm.

Giới hạn rollout:
  Bật cho nhóm khách hàng thử nghiệm; theo dõi tỷ lệ lỗi và trạng thái
  giao dịch chờ.

Điều kiện mở rộng:
  Không có sai lệch đối soát nghiêm trọng; alert và quy trình hỗ trợ
  hoạt động; các lỗi đã biết được xử lý.

Người sở hữu:
  Product owner, payment engineering và operations.

Ngày xem lại:
  Trước khi mở rộng cho toàn bộ người dùng.
~~~

Mẫu này không phải giấy phép trì hoãn kiểm soát bắt buộc. Nó giúp người ra quyết định biết **đã chọn gì, vì sao, còn rủi ro nào và khi nào phải xem lại**.

## 12. Ví dụ Java: tính năng được giao cùng kiểm tra chất lượng

Giả sử sản phẩm cần thêm một luồng xác nhận đơn hàng. Một implementation thiếu kiểm soát có thể trông như sau:

~~~java
final class OrderService {
    void confirm(long orderId) {
        Order order = repository.findById(orderId).orElseThrow();
        paymentGateway.charge(order.totalVnd());
        order.markConfirmed();
        repository.save(order);
    }
}
~~~

Đoạn code rút gọn có nhiều câu hỏi chưa được giải quyết:

- Hai request đồng thời có thể cùng charge không?
- Gateway timeout sau khi xử lý được phân biệt ra sao?
- Giao dịch đã được ghi nhận trước hay sau khi trạng thái đơn đổi?
- Có idempotency key không?
- Người gọi có quyền xác nhận đơn này không?
- Nếu lưu trạng thái thất bại sau khi charge thì đối soát thế nào?

Nếu nhóm chỉ đếm “endpoint đã viết xong”, có thể bỏ qua phần rủi ro quan trọng nhất.

### Đặt hợp đồng trước khi chọn implementation

Giả định hợp đồng yêu cầu:

1. Chỉ chủ thể có quyền mới được xác nhận đơn.
2. Mỗi order chỉ tạo một charge logic cho một lần xác nhận.
3. Retry với cùng idempotency key không tạo charge thứ hai.
4. Trạng thái đơn và trạng thái thanh toán có thể được đối soát.
5. Lỗi hoặc timeout không được báo thành công giả.

Một thiết kế có thể dùng application service, repository, gateway port và cơ chế idempotency. Ví dụ dưới đây minh họa ranh giới và không phải một transaction payment hoàn chỉnh:

~~~java
record ConfirmOrderCommand(long orderId, String actorId, String idempotencyKey) {}

interface OrderRepository {
    Order findForUpdate(long orderId);
    void save(Order order);
}

interface PaymentGateway {
    PaymentResult charge(long orderId, long amountVnd, String idempotencyKey);
}

interface OrderAuthorization {
    void requireCanConfirm(String actorId, Order order);
}

final class ConfirmOrderService {
    private final OrderRepository orders;
    private final PaymentGateway payments;
    private final OrderAuthorization authorization;

    ConfirmOrderService(
            OrderRepository orders,
            PaymentGateway payments,
            OrderAuthorization authorization
    ) {
        this.orders = orders;
        this.payments = payments;
        this.authorization = authorization;
    }

    ConfirmOrderResult confirm(ConfirmOrderCommand command) {
        Order order = orders.findForUpdate(command.orderId());
        authorization.requireCanConfirm(command.actorId(), order);

        if (order.isConfirmed()) {
            return ConfirmOrderResult.alreadyConfirmed(order.id());
        }

        PaymentResult payment = payments.charge(
                order.id(),
                order.totalVnd(),
                command.idempotencyKey());

        if (!payment.isSuccessful()) {
            return ConfirmOrderResult.paymentPending(order.id());
        }

        order.markConfirmed(payment.reference());
        orders.save(order);

        return ConfirmOrderResult.confirmed(order.id());
    }
}
~~~

Các kiểu `Order`, `PaymentResult` và `ConfirmOrderResult` cùng một số phương thức domain trong ví dụ được lược bỏ để tập trung vào ranh giới phụ thuộc; đoạn mã minh họa kiến trúc, không phải một chương trình độc lập có thể biên dịch nguyên trạng. Ví dụ này cần thêm thiết kế cho transaction, lock, trạng thái không xác định, outbox/reconciliation và retry theo hợp đồng gateway. Không nên coi đoạn code là giải pháp production hoàn chỉnh. Mục đích là chỉ ra rằng **chất lượng cần được đưa vào acceptance criteria ngay khi lập kế hoạch**.

### Test là một phần của đường giao hàng

Một bộ test có thể kiểm tra:

- Người không có quyền không thể xác nhận.
- Đơn đã xác nhận không tạo charge mới.
- Retry cùng key không tạo charge trùng.
- Timeout sau khi gateway nhận request tạo trạng thái có thể đối soát.
- Lỗi persistence không làm nhóm báo thành công giả.
- Hai request đồng thời không tạo hai giao dịch logic.

Các test này cần được phân bố theo ranh giới: unit test cho policy, integration test cho repository/transaction, contract test cho gateway và kiểm thử vận hành cho đối soát. Không cần giả lập mọi thứ trong một test end-to-end duy nhất.

## 13. Đưa bảo trì vào luồng làm việc hằng ngày

Bảo trì sẽ dễ bị trì hoãn nếu chỉ được lên kế hoạch như một dự án lớn. Có thể kết hợp các việc nhỏ vào lúc thay đổi khu vực liên quan:

- Khi sửa một quy tắc bị nhân bản, đưa các caller về một policy có tên.
- Khi thêm endpoint, bổ sung contract và test quyền ngay.
- Khi test flaky cản PR, sửa dữ liệu dùng chung hoặc nguồn không xác định.
- Khi thay schema, cập nhật migration, consumer và hướng dẫn vận hành cùng kế hoạch.
- Khi phát hiện một lỗi tái diễn, thêm regression test ở ranh giới đã để lọt lỗi.
- Khi sửa module khó hiểu, làm rõ tên và trách nhiệm ở phần trực tiếp liên quan.

### Giữ phạm vi nhỏ và review được

Không nên biến mỗi feature thành cuộc tái cấu trúc toàn module. Hãy chọn cải tiến có quan hệ rõ với công việc hiện tại, đặt tiêu chí hoàn tất và tách phần không liên quan thành mục riêng.

Một PR tốt có thể gồm:
- Feature hoặc defect chính.
- Test bảo vệ hành vi mới và hành vi cần giữ.
- Một cải tiến cấu trúc nhỏ giúp thay đổi hiện tại an toàn hơn.
- Tài liệu/telemetry bắt buộc.

Nếu cần migration lớn, hãy tạo kế hoạch và các bước độc lập để giảm rủi ro review.

## 14. Vai trò và trách nhiệm không thể đẩy hết cho một người

Chất lượng là thuộc tính của sản phẩm và hệ thống làm việc. Không thể giao toàn bộ cho QA, reviewer, architect hoặc một “quality champion”.

| Vai trò | Trách nhiệm đóng góp |
| --- | --- |
| **Product owner / product manager** | Làm rõ giá trị, mức ưu tiên, thời hạn và trade-off; không yêu cầu che giấu rủi ro |
| **Developer / author** | Thiết kế, code, test, giải thích quyết định và xử lý vấn đề trong phạm vi thay đổi |
| **Reviewer / maintainer** | Đánh giá độc lập, kiểm tra hợp đồng và rủi ro, duy trì quy ước module |
| **QA / test engineer** | Hỗ trợ chiến lược kiểm thử, phân tích failure mode, cải thiện khả năng phát hiện lỗi |
| **Operations / SRE** | Cung cấp tín hiệu vận hành, khả năng quan sát, phục hồi và kiểm soát release |
| **Security / privacy specialist** | Hỗ trợ threat modeling, yêu cầu bảo vệ dữ liệu và đánh giá rủi ro chuyên môn |
| **Engineering lead / manager** | Giữ năng lực và ưu tiên cho bảo trì, giải quyết điểm nghẽn liên nhóm và làm rõ người ra quyết định |

Một người có thể đảm nhận nhiều vai trò trong nhóm nhỏ. Điều quan trọng là trách nhiệm được hiểu rõ và công việc không bị rơi vào khoảng trống.

### Trách nhiệm chung không có nghĩa trách nhiệm mơ hồ

Với mỗi công việc chất lượng, cần biết:

- Ai sở hữu kết quả?
- Ai phê duyệt trade-off?
- Ai thực hiện và kiểm chứng?
- Ai vận hành sau khi phát hành?
- Ai nhận cảnh báo hoặc xử lý khi kết quả không đạt?

Nếu tất cả “cùng chịu trách nhiệm” nhưng không ai có quyền quyết định hoặc theo dõi, việc bảo trì thường bị đẩy sang chu kỳ sau.

## 15. Xây dựng thói quen phối hợp giữa product và engineering

Product hiểu nhu cầu, ưu tiên và thời điểm; engineering hiểu giới hạn kỹ thuật, chi phí thay đổi và rủi ro hệ thống. Hai góc nhìn cần gặp nhau trước khi cam kết phạm vi.

Một cuộc trao đổi hữu ích không chỉ hỏi “mất bao lâu?” mà còn:

- Giá trị tối thiểu nào cần có trong lần phát hành đầu?
- Điều gì bắt buộc phải đúng ngay từ đầu?
- Có thể giới hạn đối tượng hoặc lưu lượng để học an toàn không?
- Rủi ro nào có thể giảm bằng test, feature flag hoặc rollout?
- Công việc nào nếu trì hoãn sẽ làm thay đổi tiếp theo đắt hơn?
- Khi nào phải quay lại hoàn tất phần đã hoãn?
- Ai có quyền chấp nhận rủi ro còn lại?

### Đưa chất lượng vào refinement

Trong refinement, mỗi story có thể có phần “quality considerations” ngắn:

~~~text
Mục tiêu người dùng:
  Xác nhận đơn hàng bằng phương thức thanh toán mới.

Hành vi và hợp đồng:
  Một order chỉ có một charge logic; retry dùng cùng idempotency key.

Rủi ro:
  Timeout sau khi provider đã xử lý; truy cập sai tenant.

Kiểm chứng:
  Unit test policy, integration test persistence, contract test gateway.

Vận hành:
  Metric giao dịch pending, alert sai lệch đối soát, runbook retry.

Rollout:
  Bật theo nhóm khách hàng, có kill switch và điều kiện mở rộng.
~~~

Không phải story nào cũng cần mẫu dài. Hãy chọn câu hỏi theo loại thay đổi, nhưng đảm bảo rủi ro thiết yếu không bị phát hiện quá muộn.

## 16. Sử dụng số liệu để nhìn hệ thống, không gây áp lực sai lệch

Chỉ số có thể cho biết nhóm đang mất thời gian ở đâu, nhưng cần được diễn giải theo ngữ cảnh.

Một số tín hiệu cấp nhóm có ích:

- Lead time theo loại thay đổi.
- Thời gian chờ CI/review.
- Tỷ lệ test flaky và số lần retry.
- Change failure rate và mức độ nghiêm trọng.
- Thời gian phát hiện/khôi phục sự cố.
- Tỷ lệ lỗi lặp lại theo failure mode.
- Thời gian xử lý dependency hoặc migration.
- Số lần thao tác thủ công trong release.
- Mức độ cập nhật của runbook và khả năng diễn tập.

### Đọc metric cùng guardrail

| Mục tiêu | Chỉ số quan sát | Guardrail |
| --- | --- | --- |
| Phản hồi nhanh hơn | Thời gian CI p50/p95 | Không giảm test bảo vệ rủi ro cao |
| Review nhanh hơn | Thời gian chờ phản hồi | Không tăng defect lọt qua review |
| Release thường xuyên hơn | Deployment frequency | Theo dõi change failure và rollback |
| Giảm lỗi | Lỗi theo loại và mức độ | Không giảm báo cáo hoặc thay cách phân loại để làm đẹp số |
| Giảm chi phí bảo trì | Thời gian sửa các thay đổi tương tự | Không tạo abstraction quá rộng |
| Nâng độ tin cậy | Availability và recovery time | Xem tác động người dùng và độ nghiêm trọng |

Không dùng số commit, dòng code, số ticket đóng hoặc coverage đơn lẻ để xếp hạng cá nhân. Metric chịu ảnh hưởng của loại công việc, phân công, độ khó và cách ghi nhận. Hãy dùng chúng để đặt câu hỏi và cải thiện hệ thống.

### Chú ý thay đổi cách đo

Nếu nhóm bật thêm test hoặc monitoring, số lỗi được phát hiện có thể tăng. Đây có thể là dấu hiệu khả năng quan sát tốt hơn, không nhất thiết chất lượng giảm. Khi thay định nghĩa metric hoặc instrumentation, cần ghi mốc để không so sánh hai giai đoạn như thể dữ liệu hoàn toàn tương đương.

## 17. Quản lý công việc bị trì hoãn có trách nhiệm

Có lúc nhóm phải trì hoãn một cải tiến. Điều đó có thể hợp lý nếu lợi ích chưa rõ hoặc chi phí hiện tại quá cao. Nhưng trì hoãn không nên biến thành quên lãng.

Một mục bị hoãn nên có:

- Vấn đề và phạm vi ảnh hưởng.
- Bằng chứng hiện có và điều chưa biết.
- Rủi ro nếu tiếp tục giữ nguyên.
- Lý do chưa xử lý bây giờ.
- Người sở hữu.
- Trigger hoặc thời điểm xem lại.
- Bước giảm rủi ro tạm thời nếu cần.

### Phân biệt chấp nhận rủi ro với bỏ mặc

**Chấp nhận có quản lý:** “Module cũ ít thay đổi, chưa có lỗi và sẽ được thay thế trong quý sau. Nhóm sẽ giữ test hiện tại, không mở rộng thêm dependency và đánh giá lại trước khi tích hợp hệ thống mới.”

**Bỏ mặc:** “Code này xấu, để sau refactor” mà không có người theo dõi, bằng chứng hay điều kiện xem lại.

Một quyết định trì hoãn tốt có thể được cập nhật khi bối cảnh đổi. Nếu tần suất sửa tăng hoặc sự cố xuất hiện, mức ưu tiên cần được đánh giá lại.

## 18. Case study: giảm thời gian phát hành mà không bỏ kiểm soát

Một nhóm bán lẻ cần ra mắt chức năng áp dụng voucher trong hai tuần. Module checkout hiện có:
- Logic giảm giá VIP bị sao chép.
- Test tích hợp chạy lâu và thỉnh thoảng flaky.
- Một số lỗi đầu vào chỉ được phát hiện ở production.
- Chưa có metric phân biệt voucher bị từ chối vì hết hạn hay sai điều kiện.

Product muốn giữ ngày ra mắt. Engineering không thể xử lý mọi vấn đề nền tảng trong cùng khoảng thời gian.

### Bước 1: xác định bất biến

Nhóm thống nhất:
- Không áp dụng voucher hết hạn.
- Không áp dụng voucher cho đơn ngoài phạm vi.
- Tổng tiền không âm và được tính theo đơn vị tiền đã xác định.
- Retry không tạo áp dụng voucher hoặc giao dịch trùng.
- Báo giá và checkout phải dùng cùng chính sách được xác nhận.

Những điều này thuộc tiêu chí đúng đắn và bảo vệ dữ liệu, không bị bỏ qua để đạt ngày ra mắt.

### Bước 2: chia phạm vi theo giá trị và rủi ro

| Công việc | Quyết định |
| --- | --- |
| Tích hợp voucher cho một loại đơn | Làm trong đợt đầu |
| Test điều kiện hết hạn/ngưỡng và phạm vi áp dụng | Bắt buộc cùng tính năng |
| Hợp nhất chính sách VIP đang bị nhân bản | Làm nếu cùng ranh giới và có thể kiểm tra an toàn |
| Viết lại toàn bộ module checkout | Chưa làm; phạm vi quá lớn |
| Sửa flaky test đang chặn pipeline | Ưu tiên vì feedback hiện tại không đáng tin |
| Dashboard phân tích nâng cao | Trì hoãn; metric cơ bản và log phân loại lỗi vẫn cần |
| Thêm alert giao dịch bất thường | Hoàn tất trước rollout rộng |

### Bước 3: triển khai theo lát cắt

1. Viết test cho hợp đồng voucher và các trường hợp biên.
2. Thêm policy có tên, không gom voucher và VIP nếu chúng có lý do thay đổi khác nhau.
3. Tích hợp một luồng checkout nhỏ.
4. Sửa flaky test liên quan trực tiếp tới pipeline checkout.
5. Thêm log/metric đủ để phân biệt nguyên nhân từ chối.
6. Phát hành cho nhóm thử nghiệm bằng feature flag.
7. Theo dõi sai lệch, lỗi và phản hồi.
8. Mở rộng khi guardrails được đáp ứng.

### Bước 4: đánh giá sau phát hành

Nhóm xem:
- Tính năng có được người dùng sử dụng không?
- Có sai khác giá giữa báo giá và checkout không?
- Tỷ lệ voucher bị từ chối có nguyên nhân bất thường không?
- CI có phản hồi ổn định hơn không?
- Có lỗi hoặc thao tác thủ công nào lặp lại không?
- Phần việc trì hoãn nào trở nên cấp thiết sau khi có lưu lượng thật?

Kết luận không chỉ là “ra mắt đúng ngày”. Nhóm cũng học được phần nào cần duy trì để lần phát hành tiếp theo ít rủi ro hơn.

## 19. Cải thiện liên tục bằng vòng phản hồi ngắn

Một chu kỳ duy trì chất lượng có thể gồm:

1. **Quan sát:** lỗi, CI, review, vận hành hoặc phản hồi người dùng chỉ ra điểm nghẽn nào?
2. **Chọn vấn đề:** vấn đề nào có tác động lớn và có thể cải thiện trong phạm vi phù hợp?
3. **Đặt giả thuyết:** thay đổi kỹ thuật nào có thể giảm chi phí hoặc rủi ro?
4. **Xác định guardrail:** điều gì không được xấu đi?
5. **Thực hiện nhỏ:** thay đổi có thể review và rollback.
6. **Đo lại:** bằng chứng nào cho thấy kết quả?
7. **Chia sẻ:** cập nhật quy ước, tài liệu hoặc cách làm để nhóm cùng hưởng lợi.

~~~mermaid
flowchart TD
    A["Quan sát điểm nghẽn"] --> B["Ưu tiên theo tác động và rủi ro"]
    B --> C["Đặt mục tiêu và guardrails"]
    C --> D["Lập kế hoạch cùng công việc sản phẩm"]
    D --> E["Thực hiện và kiểm tra theo rủi ro"]
    E --> F["Rollout và quan sát"]
    F --> G{"Kết quả đạt và an toàn?"}
    G -->|"Có"| H["Chuẩn hóa cách làm, tiếp tục giao hàng"]
    G -->|"Chưa"| I["Giảm phạm vi, khắc phục hoặc rollback"]
    I --> A
    H --> A
~~~

Không phải mọi cải tiến cần một dự án đo lường lớn. Một test hồi quy ở đúng ranh giới hoặc một cảnh báo có thể giải quyết điểm mù rõ ràng. Nhưng với thay đổi rộng hoặc tốn kém, cần nêu giả thuyết và cách đánh giá trước.

## 20. Những ngộ nhận thường gặp

**“Muốn giao nhanh thì phải bỏ test và refactor.”** Có thể giảm phạm vi hoặc trì hoãn tối ưu chưa cần, nhưng bỏ kiểm soát cần thiết thường chuyển chi phí sang điều tra, sửa nóng và vận hành.

**“Chất lượng nghĩa là phải làm kiến trúc hoàn hảo trước khi phát hành.”** Chất lượng là đáp ứng các tiêu chí và guardrails phù hợp với rủi ro; không cần tổng quát hóa trước khi có nhu cầu.

**“Bảo trì chỉ làm khi roadmap trống.”** CI chậm, test flaky, lỗ hổng hoặc module không thể thay đổi an toàn trực tiếp ảnh hưởng tiến độ sản phẩm.

**“Mọi feature đều cần một bộ kiểm thử giống nhau.”** Mức kiểm tra cần dựa vào tác động, khả năng xảy ra, phạm vi và khả năng phục hồi.

**“Dành một tỷ lệ cố định cho technical debt luôn đúng.”** Capacity cần được điều chỉnh theo tình trạng hệ thống, thời hạn và bằng chứng.

**“Nếu release đúng hạn thì dự án thành công.”** Còn phải xem lỗi, trải nghiệm người dùng, chi phí vận hành và khả năng tiếp tục phát triển.

**“Nếu chất lượng giảm thì developer phải làm việc nhanh hơn.”** Có thể nguyên nhân là yêu cầu thay đổi, thiếu người sở hữu, CI, phụ thuộc hoặc quy trình ra quyết định.

**“QA chịu trách nhiệm về chất lượng.”** Mọi vai trò đều đóng góp; test engineer hỗ trợ kiểm chứng nhưng không thể thay developer, product và operations chịu trách nhiệm.

**“Một dashboard tốt có thể tự quyết định ưu tiên.”** Metric cung cấp tín hiệu; quyết định cần bối cảnh, rủi ro và trade-off.

**“Trì hoãn một việc nghĩa là đã chấp nhận rủi ro vĩnh viễn.”** Quyết định trì hoãn cần người sở hữu, trigger và thời điểm xem lại.

**“Refactor càng lớn thì lợi ích càng cao.”** Thay đổi rộng tăng phạm vi hồi quy; bước nhỏ có kiểm chứng thường dễ quản lý hơn.

**“Chỉ cần unit test xanh là đủ phát hành.”** Thay đổi về DB, API, quyền, transaction và vận hành có thể cần integration, contract và rollout checks.

## 21. Checklist cân bằng tiến độ với chất lượng

### Khi lập kế hoạch

- [ ] Mục tiêu người dùng và phạm vi đợt phát hành rõ ràng.
- [ ] Rủi ro nghiệp vụ, bảo mật, dữ liệu và vận hành đã được xác định.
- [ ] Công việc test, quan sát, migration và rollback được tính vào kế hoạch.
- [ ] Các cải tiến bảo trì có tác động rõ được ưu tiên.
- [ ] Có người sở hữu và tiêu chí hoàn tất cho công việc bị trì hoãn.
- [ ] Trade-off được trao đổi giữa product và engineering.

### Khi thực hiện

- [ ] Code được kiểm tra tự động phù hợp với loại thay đổi.
- [ ] Test bảo vệ hành vi và các failure mode quan trọng.
- [ ] Review tập trung vào hợp đồng, rủi ro và khả năng thay đổi.
- [ ] Phạm vi refactor đủ nhỏ để kiểm tra.
- [ ] Dependency và API được thay đổi có kiểm soát.
- [ ] Không bỏ qua guardrail để đạt tiến độ.

### Trước và sau phát hành

- [ ] Có bằng chứng phù hợp với mức rủi ro.
- [ ] Rollout/rollback có người sở hữu.
- [ ] Monitoring và alert đủ để phát hiện vấn đề quan trọng.
- [ ] Runbook hoặc hướng dẫn hỗ trợ được cập nhật khi cần.
- [ ] Kết quả được đánh giá theo giá trị người dùng và chất lượng hệ thống.
- [ ] Những phần đã trì hoãn được xem lại theo trigger hoặc lịch đã thống nhất.

## 22. Bài tập thực hành

### Bài tập A — lập kế hoạch khi thời hạn gấp

Một tính năng báo giá cần phát hành trong 5 ngày. Hệ thống có một test flaky, logic tính phí bị sao chép và chưa có telemetry cho lỗi timeout.

Hãy:
1. Phân loại công việc thành guardrail, điểm nghẽn, cải tiến có thể trì hoãn.
2. Chọn phạm vi phát hành nhỏ nhất vẫn có giá trị.
3. Nêu test và telemetry cần có trước rollout.
4. Xác định phần nào có thể trì hoãn, ai sở hữu và khi nào xem lại.
5. Giải thích trade-off cho product owner.

### Bài tập B — xây Definition of Done

Thiết kế DoD cho ba thay đổi:
- Đổi màu một thành phần giao diện.
- Thay logic tính tiền.
- Thay migration của bảng giao dịch.

Chỉ ra tiêu chí chung và bằng chứng riêng theo rủi ro.

### Bài tập C — phản biện KPI tốc độ

Một nhóm được đánh giá bằng số ticket hoàn thành mỗi tuần. Sau vài chu kỳ, ticket bị chia nhỏ, test ít hơn và lỗi sau release tăng.

Hãy đề xuất bộ tín hiệu cấp nhóm có guardrail, giải thích giới hạn từng metric và cách tránh biến dashboard thành bảng xếp hạng cá nhân.

### Bài tập D — xử lý nợ kỹ thuật có bằng chứng

Một module có ba bản sao cùng quy tắc giá; mỗi lần thay đổi mất thêm thời gian và đã từng có sai khác. Hãy lập kế hoạch giảm nợ theo từng bước: xác nhận policy, test, chọn owner, chuyển caller, kiểm tra kết quả và tiêu chí hoàn tất.

### Bài tập E — phân vai trách nhiệm

Một incident phát sinh do migration không tương thích với phiên bản ứng dụng cũ. Hãy xác định product, developer, reviewer, QA, operations và engineering lead cần đóng góp gì trong:
- Khôi phục dịch vụ.
- Điều tra nguyên nhân hệ thống.
- Cải thiện migration test và rollout.
- Cập nhật DoD/ownership để tránh tái diễn.

## 23. Câu hỏi tự kiểm tra

1. Vì sao tốc độ giao hàng và chất lượng kỹ thuật cùng quyết định năng lực giao hàng lâu dài?
2. Phân biệt công việc tính năng, duy trì chất lượng, vận hành và giảm bất định.
3. Nêu ba loại chi phí ẩn do chất lượng thấp gây ra.
4. Những bất biến nào không nên bị bỏ qua khi thời hạn gấp?
5. Definition of Done cần thay đổi theo loại rủi ro như thế nào?
6. Vì sao không nên chạy cùng một bộ kiểm tra cho mọi thay đổi?
7. Làm thế nào giữ vòng phản hồi CI ngắn mà không xóa test quan trọng?
8. Khi nào nên dành capacity riêng cho bảo trì và khi nào tích hợp nó vào feature?
9. Những yếu tố nào nên dùng để ưu tiên backlog chất lượng?
10. Một quyết định trade-off cần ghi lại những thông tin gì?
11. Vì sao một endpoint thanh toán cần tính idempotency và trạng thái timeout vào acceptance criteria?
12. Product và engineering nên trao đổi gì trước khi cam kết ngày phát hành?
13. Vai trò nào sở hữu chất lượng và vì sao không thể giao cho QA riêng?
14. Những metric cấp nhóm nào có ích để tìm điểm nghẽn?
15. Vì sao số ticket, commit hoặc coverage không đủ đánh giá cá nhân?
16. Khi instrumentation tốt hơn làm số lỗi tăng, nên diễn giải thế nào?
17. Một mục nợ kỹ thuật bị trì hoãn cần thông tin gì để không bị bỏ quên?
18. Làm sao biết một cải tiến bảo trì đã tạo ra kết quả có ích?
19. Vì sao rollout có giới hạn và rollback là một phần của chất lượng?
20. Hãy nêu một ví dụ nhóm giảm phạm vi tính năng để bảo vệ các guardrail chất lượng.

## Ghi nhớ

**Cân bằng tiến độ với duy trì chất lượng là bảo vệ khả năng giao hàng qua nhiều lần thay đổi, không phải chọn một bên và bỏ bên còn lại.** Hãy đưa test, bảo mật, dữ liệu, quan sát và phục hồi vào kế hoạch từ đầu; phân biệt guardrails bắt buộc với mức hoàn thiện có thể điều chỉnh; ưu tiên bảo trì theo tác động và bằng chứng. Khi phải trì hoãn, ghi rõ lý do, rủi ro, người sở hữu và điều kiện xem lại. Product, engineering, QA và operations cần cùng chịu trách nhiệm trong phạm vi của mình. Một nhóm giao hàng bền vững là nhóm vừa tạo giá trị đúng lúc, vừa giữ hệ thống **đáng tin cậy, dễ hiểu và dễ thay đổi**.
