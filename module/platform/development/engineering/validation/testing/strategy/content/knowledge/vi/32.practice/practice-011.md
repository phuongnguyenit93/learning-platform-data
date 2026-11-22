# Soạn tài liệu chiến lược ngắn gọn với các quyết định có lý do

## 1. Mục tiêu của một tài liệu chiến lược kiểm thử

Tài liệu chiến lược kiểm thử (test strategy) mô tả cách nhóm sẽ tạo bằng chứng để kiểm soát rủi ro chất lượng trong một sản phẩm, dịch vụ hoặc chương trình thay đổi. Tài liệu cần giúp người đọc hiểu nhóm sẽ kiểm tra điều gì, tập trung vào rủi ro nào, sử dụng phương pháp nào, quyết định phát hành dựa trên điều kiện gì và ai chịu trách nhiệm.

Một tài liệu tốt không cần kể lại mọi test case hoặc sao chép toàn bộ quy trình. Nó cần làm rõ các lựa chọn quan trọng và lý do phía sau chúng. Người đọc có thể trả lời nhanh:

- Mục tiêu chất lượng và phạm vi áp dụng là gì?
- Rủi ro nào quan trọng nhất?
- Nhóm sẽ dùng những lớp kiểm thử và bằng chứng nào?
- Vì sao chọn cách tiếp cận này thay vì phương án khác?
- Điều kiện nào cho phép chuyển bước hoặc phát hành?
- Những giới hạn, giả định và rủi ro còn lại là gì?
- Ai sở hữu từng phần và khi nào cần xem xét lại?

Trong **VALIDATION_TESTING_STRATEGY**, chiến lược kiểm thử cần đủ ngắn để stakeholder có thể đọc và đưa ra quyết định, đồng thời đủ cụ thể để nhóm triển khai nhất quán. Độ dài không phải thước đo chất lượng. Một tài liệu ngắn nhưng chỉ liệt kê “unit, integration, E2E” mà không nói vì sao, phạm vi nào và tiêu chí ra sao vẫn chưa phải chiến lược có thể thực thi.

## 2. Viết cho đúng người đọc và quyết định cần hỗ trợ

Trước khi viết, xác định ai sẽ sử dụng tài liệu và họ cần quyết định điều gì.

| Người đọc | Điều họ cần hiểu |
|---|---|
| Product/business owner | Rủi ro đối với người dùng, hành trình trọng yếu và điều kiện chấp nhận |
| Engineering/service owner | Phạm vi kỹ thuật, dependency, trách nhiệm và kế hoạch kiểm thử |
| QA/test lead | Cách chọn test, coverage, dữ liệu, môi trường và bằng chứng |
| Platform/SRE/Operations | Pipeline, khả năng quan sát, readiness và rollback |
| Security/privacy specialist | Kiểm soát chuyên môn, dữ liệu nhạy cảm và điều kiện bắt buộc |
| Release authority | Gate, rủi ro còn lại, ngoại lệ và quyền quyết định |

Không cần viết một tài liệu riêng cho mỗi vai trò nếu một strategy brief có thể phục vụ tất cả. Hãy đặt quyết định quan trọng ở phần dễ tìm và dùng liên kết đến tài liệu chi tiết cho người cần đào sâu.

### 2.1. Nêu mục đích ngay đầu tài liệu

Phần mở đầu nên trả lời:

- Tài liệu này phục vụ sản phẩm, dịch vụ hoặc thay đổi nào?
- Được viết để hỗ trợ quyết định gì?
- Áp dụng cho release, giai đoạn hoặc khoảng thời gian nào?
- Ai là owner và ai cần review?

Tránh mở đầu bằng lịch sử dài của dự án hoặc định nghĩa chung về kiểm thử. Nếu bối cảnh quan trọng, tóm tắt trong vài câu và liên kết tới nguồn chính thức.

## 3. Nguyên tắc viết ngắn gọn nhưng đủ căn cứ

### 3.1. Viết quyết định trước, giải thích sau

Thay vì mô tả nhiều phương pháp rồi để người đọc tự đoán, hãy nêu lựa chọn trước:

> Chạy contract test trong mỗi pull request khi API contract thay đổi; chạy integration suite đầy đủ sau khi merge và trước release.

Sau đó giải thích lý do:

> Contract test phản hồi nhanh và phát hiện incompatibility sớm giữa provider và consumer. Integration suite tốn thời gian hơn nên chạy ở stage sau, nhưng phải hoàn tất trước release gate.

Cách viết này giúp người đọc thấy ngay nhóm sẽ làm gì và tại sao.

### 3.2. Chỉ giữ thông tin ảnh hưởng đến quyết định

Một chi tiết nên xuất hiện trong phần chính nếu nó:

- Làm thay đổi phạm vi hoặc cách kiểm thử.
- Giải thích một trade-off quan trọng.
- Xác định điều kiện pass/fail hoặc release.
- Làm rõ owner hoặc quyền quyết định.
- Nêu một giả định hoặc giới hạn có thể thay đổi kết luận.

Chi tiết như toàn bộ danh sách test case, hướng dẫn cài runner, schema dữ liệu, từng bước triage hoặc báo cáo test nên nằm ở tài liệu chuyên biệt và được liên kết.

### 3.3. Dùng bảng cho lựa chọn và trách nhiệm

Bảng phù hợp khi cần so sánh phương án, chỉ ra quyết định, owner, bằng chứng hoặc điều kiện. Không tạo bảng chỉ để biến mọi đoạn văn thành bảng. Mỗi cột cần trả lời một câu hỏi rõ.

### 3.4. Dùng từ cụ thể

Tránh các câu như:

- “Kiểm thử đầy đủ trước khi release.”
- “Đảm bảo chất lượng tốt.”
- “Tự động hóa khi phù hợp.”
- “Theo dõi hiệu năng thường xuyên.”

Viết rõ hơn:

- “Chạy toàn bộ test bắt buộc của luồng tạo, sửa và hủy đơn trên release candidate.”
- “Chặn release khi còn lỗi Critical chưa xử lý hoặc waiver hợp lệ.”
- “Tự động hóa contract test cho API có consumer bên ngoài; exploratory test vẫn được dùng cho luồng mới.”
- “Theo dõi p95 latency, error rate và tỷ lệ giao dịch hoàn tất trong cửa sổ canary.”

Nếu chưa thể đưa ra ngưỡng cụ thể, ghi ai sẽ xác định, dựa trên nguồn nào và trước thời điểm nào. Không dùng một từ mơ hồ để che khoảng trống quyết định.

### 3.5. Không biến tài liệu thành danh sách hoạt động

“Chạy unit test, integration test, E2E, performance test và security test” chỉ liệt kê hoạt động. Một chiến lược cần giải thích test nào bảo vệ rủi ro nào, chạy ở đâu, khi nào và kết quả ảnh hưởng ra sao đến quyết định.

## 4. Cấu trúc đề xuất cho strategy brief

Với một sản phẩm hoặc một thay đổi có phạm vi vừa phải, có thể dùng cấu trúc 1–3 trang sau:

| Phần | Câu hỏi phải trả lời | Độ sâu gợi ý |
|---|---|---|
| 1. Purpose and context | Tài liệu phục vụ điều gì? | Một đoạn ngắn |
| 2. Scope and exclusions | Phần nào được kiểm thử và phần nào không? | Gạch đầu dòng có lý do |
| 3. Quality risks | Rủi ro trọng yếu là gì? | 3–5 rủi ro chính |
| 4. Test approach | Dùng lớp kiểm thử và kỹ thuật nào? | Bảng risk-to-test |
| 5. Environments and data | Chạy ở đâu, với dữ liệu nào? | Các điều kiện quyết định |
| 6. Automation and execution | Tự động hóa và phân bổ test theo stage ra sao? | Pipeline ngắn |
| 7. Exit/release criteria | Điều kiện nào cho phép chuyển bước? | Hard gate và ngoại lệ |
| 8. Ownership | Ai thực hiện, review và quyết định? | Owner theo phạm vi |
| 9. Assumptions and residual risks | Điều gì chưa được xác nhận? | Các mục có owner |
| 10. Decisions and review | Vì sao chọn phương án và khi nào xem lại? | Decision log ngắn |

Không nhất thiết phải dùng đủ mười heading cho mọi dự án. Có thể gộp phần nhỏ nếu vẫn dễ tìm, nhưng không nên bỏ mục quan trọng chỉ để đạt số trang.

## 5. Xác định phạm vi rõ ràng

### 5.1. In scope

Nêu thành phần, hành trình, API, dữ liệu, dependency, loại thay đổi hoặc release nằm trong phạm vi. Ví dụ:

- API tạo, cập nhật và hủy đơn.
- Quy tắc tính tổng tiền và áp dụng mã giảm giá.
- Tích hợp với dịch vụ tồn kho và thanh toán sandbox.
- Migration bổ sung trường trạng thái đơn.
- Khả năng khôi phục khi consumer nhận event lặp.

### 5.2. Out of scope

Nêu phần không kiểm thử trong tài liệu và lý do. Ví dụ, kiểm thử tải toàn hệ thống có thể nằm trong chiến lược performance riêng do một nhóm chuyên môn sở hữu. Nếu out of scope tạo ra rủi ro, ghi owner và nguồn bằng chứng thay thế.

Không dùng “out of scope” để bỏ qua một yêu cầu bắt buộc. Cần nêu ai chịu trách nhiệm và điều kiện nào bảo đảm phần đó vẫn được kiểm soát.

### 5.3. Phạm vi theo thay đổi và theo release

Phân biệt:

- **Change scope:** thành phần bị thay đổi trực tiếp và dependency chịu ảnh hưởng.
- **Regression scope:** hành vi hiện có có thể bị ảnh hưởng gián tiếp.
- **Release scope:** toàn bộ điều kiện cần để phát hành artifact cụ thể.

Một pull request có phạm vi nhỏ nhưng release vẫn có thể cần bằng chứng tích hợp hoặc vận hành rộng hơn.

## 6. Chọn rủi ro trọng yếu và liên kết với cách kiểm thử

Không cần đưa toàn bộ risk register vào strategy brief. Chọn những rủi ro ảnh hưởng đến cách phân bổ test hoặc quyết định phát hành.

Một risk statement nên mô tả:

- Điều gì có thể xảy ra?
- Trong điều kiện nào?
- Tác động đến người dùng, dữ liệu hoặc dịch vụ ra sao?
- Kiểm soát hiện tại nào đang giảm rủi ro?
- Bằng chứng nào còn thiếu?

Ví dụ:

> Khi consumer xử lý lại event sau timeout, cùng một yêu cầu có thể tạo hai đơn, dẫn đến giao dịch trùng và sai đối soát.

Câu này cụ thể hơn “rủi ro về xử lý đơn hàng” vì nó nêu điều kiện và hậu quả có thể kiểm tra.

### 6.1. Dùng bảng risk-to-test

| Rủi ro | Bằng chứng cần có | Phương pháp kiểm thử | Khi chạy |
|---|---|---|---|
| Tạo đơn trùng khi retry | Cùng event được xử lý nhiều lần nhưng chỉ tạo một đơn hợp lệ | Integration và idempotency test | PR liên quan, pre-release |
| Sai tổng tiền khi áp dụng giảm giá | Kết quả tính toán đúng ở boundary và kết hợp nhiều rule | Unit và property-based test | PR |
| Provider đổi contract làm consumer lỗi | Schema và hành vi tương thích | Contract test | PR và sau merge |
| Migration làm mất trạng thái | Dữ liệu trước/sau giữ invariant | Migration test và data reconciliation | Pre-release |
| Tăng latency khi traffic cao | p95/p99 và error rate trong workload mục tiêu | Load/performance test | Trước release lớn |

Bảng này là phần quan trọng của strategy: nó cho thấy lý do chọn test thay vì chỉ liệt kê tên test.

### 6.2. Giữ mối liên hệ truy vết

Nếu có hệ thống quản lý yêu cầu, rủi ro và test, dùng ID hoặc liên kết tới nguồn. Không sao chép toàn bộ dữ liệu vào tài liệu. Strategy brief nên giữ phần tóm tắt cần ra quyết định và trỏ tới risk register/test plan chi tiết.

## 7. Giải thích các lựa chọn kiểm thử

Mỗi lựa chọn quan trọng nên có tối thiểu bốn yếu tố:

1. **Decision:** nhóm chọn làm gì.
2. **Rationale:** bằng chứng hoặc rủi ro nào dẫn đến lựa chọn.
3. **Trade-off:** chi phí, giới hạn hoặc rủi ro chấp nhận kèm theo.
4. **Consequence/owner:** điều kiện thực thi, người chịu trách nhiệm và cách review.

### 7.1. Chọn test level

Ví dụ:

| Quyết định | Lý do | Trade-off |
|---|---|---|
| Dùng unit test cho quy tắc tính tiền | Logic có nhiều boundary và có thể kiểm tra nhanh, ổn định | Không xác nhận được tích hợp database hoặc provider |
| Dùng contract test giữa order và payment | Hai service phát hành độc lập, contract drift có thể gây lỗi | Cần duy trì contract và consumer version |
| Dùng integration test cho retry/event | Lỗi phụ thuộc transaction và message delivery | Chạy chậm hơn unit test, cần môi trường/dữ liệu |
| Giới hạn E2E vào hành trình cốt lõi | E2E có chi phí và độ flaky cao | Một số tổ hợp hiếm được kiểm tra ở tầng thấp hơn |

### 7.2. Chọn automation

Không viết “tự động hóa tối đa”. Nêu loại test được tự động hóa và lý do:

- Tự động hóa unit, API và contract test vì cần phản hồi thường xuyên.
- Tự động hóa smoke test sau deploy vì kết quả cần lặp lại và có thể chặn rollout.
- Dùng exploratory testing cho hành vi mới hoặc vùng có yêu cầu chưa ổn định.
- Chỉ tự động hóa E2E khi luồng đủ ổn định và có giá trị kiểm tra xuyên hệ thống.

Nêu rõ ai duy trì test, dữ liệu và môi trường. Một test tự động nhưng không có owner sẽ nhanh chóng mất độ tin cậy.

### 7.3. Chọn môi trường và dữ liệu

Ghi môi trường dùng cho từng nhóm test, khác biệt quan trọng so với production, nguồn dữ liệu và cách làm sạch. Nếu test cần dữ liệu tổng hợp, nêu cách tạo và giới hạn đại diện. Nếu test production, mô tả biện pháp tránh tác dụng phụ và người có quyền dừng.

### 7.4. Chọn thứ tự và thời điểm chạy

Đặt test phản hồi nhanh và có khả năng phát hiện lỗi cao ở giai đoạn sớm. Test phụ thuộc nhiều service, tải lớn hoặc thiết bị chuyên biệt có thể chạy ở stage sau, miễn hoàn tất trước gate tương ứng.

Nêu rõ test nào chạy ở pull request, sau merge, nightly, pre-release, post-deployment hoặc canary. Không ghi “chạy thường xuyên” nếu không có trigger hoặc cadence.

## 8. Viết tiêu chí hoàn tất và quyết định phát hành

Tiêu chí cần xác định điều kiện để chuyển bước, không chỉ nói “đã kiểm thử xong”.

### 8.1. Phân biệt hard gate và advisory

- **Hard gate:** điều kiện bắt buộc; không đạt thì dừng chuyển bước trừ ngoại lệ hợp lệ theo policy.
- **Advisory:** cảnh báo cần được ghi nhận và có owner, nhưng có thể không chặn theo quy định.

Ví dụ hard gate:

- Tất cả test bắt buộc của luồng thanh toán đạt trên release candidate.
- Không có lỗ hổng Critical chưa xử lý theo policy.
- Migration test và kiểm tra tính toàn vẹn dữ liệu đạt.
- Smoke test sau deploy đạt trước khi mở rộng traffic.

Ví dụ advisory:

- Một test trên browser best-effort chưa chạy, nếu nền tảng đó không nằm trong cam kết bắt buộc và rủi ro đã được đánh giá.
- Một cảnh báo tài liệu có owner và hạn xử lý, không ảnh hưởng vận hành hoặc nghĩa vụ phát hành.

### 8.2. Nêu rõ trạng thái thiếu bằng chứng

Phân biệt Passed, Failed, Blocked, Not run, Inconclusive và Not applicable. Không coi test chưa chạy hoặc môi trường không sẵn sàng là pass. Nếu một tiêu chí bắt buộc bị blocked, tài liệu cần nói ai xử lý và quyết định release được giữ ở trạng thái nào.

### 8.3. Ghi điều kiện waiver

Nếu policy cho phép waiver, ghi:

- Tiêu chí nào được miễn trừ.
- Lý do và bằng chứng.
- Rủi ro còn lại và biện pháp giảm thiểu.
- Người có thẩm quyền phê duyệt.
- Owner theo dõi và ngày hết hiệu lực.
- Điều kiện dừng hoặc rollback.

Không dùng waiver để thay đổi lịch sử test fail thành pass. Một ngoại lệ vẫn phải giữ trạng thái gốc và được truy xuất.

## 9. Nêu ownership và cơ chế phối hợp

Strategy brief cần cho biết ai sở hữu các quyết định và đầu ra chính:

| Phạm vi | Owner điển hình | Trách nhiệm |
|---|---|---|
| Product behavior | Product/domain owner | Xác nhận expected behavior và tác động nghiệp vụ |
| Service quality | Service owner | Chịu trách nhiệm chất lượng, dependency và rủi ro dịch vụ |
| Test strategy/scope | Test lead/QA owner | Xác định test approach, coverage và bằng chứng |
| Test suite | Suite owner | Duy trì test, dữ liệu và độ ổn định |
| Pipeline/environment | Platform/CI owner | Duy trì runner, môi trường và artifact |
| Security/privacy | Specialist có thẩm quyền | Đánh giá kiểm soát và ngoại lệ chuyên môn |
| Release decision | Release authority | Quyết định chuyển bước theo policy |

Một người có thể kiêm nhiều vai trò, nhưng không để các hoạt động quan trọng không có owner. Với thay đổi liên dịch vụ, nêu provider, consumer và cách thông báo thay đổi.

## 10. Ghi giả định, giới hạn và rủi ro còn lại

Một strategy có lý do cần nói rõ điều gì đang được giả định:

- Dependency ngoài nhóm giữ contract ổn định trong thời gian kiểm thử.
- Staging có cấu hình tương đương production ở các yếu tố liên quan.
- Dataset tổng hợp đại diện cho các boundary đã xác định.
- Một nhóm thiết bị được chọn đại diện cho nền tảng hỗ trợ.
- Một test chuyên biệt được thực hiện bởi nhóm khác và có report riêng.

Với mỗi giả định quan trọng, ghi nguồn xác nhận, owner và hành động nếu giả định không còn đúng.

Rủi ro còn lại cần mô tả tác động, phần chưa được kiểm tra, kiểm soát thay thế và người chấp nhận. Không dùng câu “không còn rủi ro” chỉ vì tất cả test đã pass; kiểm thử giảm bất định chứ không chứng minh tuyệt đối không có lỗi.

## 11. Cách viết rationale có sức thuyết phục

### 11.1. Dùng cấu trúc “vì – nên – đổi lại”

Một câu rationale tốt có thể theo mẫu:

> Vì [bằng chứng/rủi ro], nhóm chọn [quyết định], nên [kết quả mong đợi]. Đổi lại, [trade-off/giới hạn] được quản lý bằng [biện pháp/owner].

Ví dụ:

> Vì API payment có nhiều consumer phát hành độc lập và contract drift từng gây lỗi tích hợp, nhóm chạy contract test trong mỗi pull request. Cách này phát hiện incompatibility trước merge; đổi lại, consumer cần duy trì contract version và xử lý test khi thay đổi có chủ đích.

### 11.2. Nêu phương án đã cân nhắc khi trade-off quan trọng

Không cần ghi mọi phương án bị loại. Chỉ nêu phương án thay thế khi nó giúp giải thích quyết định:

| Phương án | Vì sao không chọn |
|---|---|
| Chạy toàn bộ E2E ở mỗi pull request | Thời gian phản hồi và độ flaky quá cao; test cốt lõi được giữ ở PR, suite rộng chạy sau merge |
| Chỉ dùng unit test cho event retry | Không mô phỏng đầy đủ transaction và delivery semantics; cần integration test |
| Kiểm tra mọi thiết bị thật trước mỗi commit | Không khả thi về thiết bị và thời gian; dùng automation/emulator thường xuyên và thiết bị thật ở release gate |

### 11.3. Phân biệt lý do với khẩu hiệu

“Best practice”, “industry standard” hoặc “đội ngũ đã quen” chưa đủ để biện minh. Nếu viện dẫn tiêu chuẩn hoặc chính sách, ghi tên tài liệu/điều khoản và cách nó áp dụng cho sản phẩm. Nếu lựa chọn dựa trên kinh nghiệm, nói rõ dữ liệu hoặc sự kiện hỗ trợ.

## 12. Quy trình soạn strategy brief

### Bước 1: Thu thập đầu vào

Đọc yêu cầu, architecture/change description, risk register, lịch sử defect/incident, support policy, test inventory và điều kiện release. Chỉ lấy dữ liệu liên quan đến quyết định đang viết.

### Bước 2: Xác định câu hỏi quyết định

Ví dụ: “Những bằng chứng nào cần có trước khi mở rộng canary?” hoặc “Test nào cần chạy cho thay đổi contract này?”. Nếu chưa rõ câu hỏi, tài liệu dễ trở thành bản tổng hợp thông tin không có kết luận.

### Bước 3: Chọn 3–5 rủi ro chính

Ưu tiên theo tác động, exposure, thay đổi gần đây, lịch sử lỗi và khả năng phát hiện. Đưa rủi ro còn lại vào risk register thay vì nhồi tất cả vào brief.

### Bước 4: Lập bảng risk-to-test

Với mỗi rủi ro, chọn bằng chứng và phương pháp kiểm thử. Ghi lý do, môi trường, thời điểm và owner.

### Bước 5: Chốt gate và ownership

Xác định hard criteria, advisory, trạng thái thiếu bằng chứng, quyền waiver, owner và release authority.

### Bước 6: Ghi trade-off và giả định

Nêu những giới hạn ảnh hưởng đến quyết định. Nếu chưa có dữ liệu, tạo action để thu thập và xác định ngày review.

### Bước 7: Rút gọn và liên kết

Xóa phần trùng lặp, giải thích chung không cần thiết và chi tiết triển khai đã có tài liệu riêng. Thay bằng liên kết tới test plan, risk register, runbook hoặc dashboard.

### Bước 8: Review với người ra quyết định

Yêu cầu owner và stakeholder kiểm tra tính chính xác, phạm vi, khả năng thực thi, quyền hạn và các ngoại lệ. Ghi nhận quyết định cuối cùng và phiên bản tài liệu.

## 13. Ví dụ strategy brief ngắn

Ví dụ sau minh họa cách trình bày một chiến lược có quyết định và rationale. Bối cảnh là thay đổi luồng tạo đơn của một dịch vụ thương mại điện tử; các ngưỡng và tên vai trò phải được thay bằng quy định thực tế.

~~~markdown
# Test Strategy Brief — Order API release 5.2

## Purpose and scope

Xác nhận thay đổi idempotency và event handling trước khi phát hành Order API 5.2.
Phạm vi gồm API tạo đơn, consumer xử lý event và migration trạng thái đơn.
Kiểm thử hiệu năng toàn nền tảng nằm trong performance strategy riêng.

## Key risks

1. Event retry có thể tạo đơn trùng.
2. Consumer có thể xử lý sai thứ tự trạng thái.
3. Migration có thể làm mất hoặc chuyển đổi sai trạng thái cũ.
4. Contract thay đổi có thể làm consumer hiện tại không tương thích.

## Test approach and rationale

| Risk | Test/evidence | When | Rationale |
|---|---|---|---|
| Duplicate order | Integration + replay/concurrency test | PR and pre-release | Lỗi phụ thuộc transaction và delivery |
| Invalid state transition | Unit + state-transition test | PR | Phản hồi nhanh cho logic nghiệp vụ |
| Migration regression | Migration test + data invariant check | Pre-release | Cần xác nhận trên schema và dữ liệu đại diện |
| Consumer incompatibility | Contract test | PR and post-merge | Provider và consumer phát hành độc lập |

E2E chỉ chạy cho luồng tạo đơn cốt lõi vì suite rộng có chi phí cao;
trường hợp biên được kiểm tra ở unit/integration level.

## Environments and data

Unit test chạy trong CI. Integration và contract test dùng môi trường
integration với dependency version được pin. Migration test dùng dataset
tổng hợp có trạng thái cũ, mới và dữ liệu biên.

## Release criteria

- Tất cả hard test liên quan đến idempotency, state transition và contract đạt.
- Migration invariant check đạt trên release candidate.
- Không còn defect Critical/High chưa có quyết định theo policy.
- Smoke test sau deploy đạt trước khi mở rộng traffic.
- Test blocked hoặc not run phải có owner và quyết định rõ; không tính là pass.

## Ownership and residual risk

Order service owner chịu trách nhiệm defect và rủi ro dịch vụ.
Test lead sở hữu phạm vi và evidence; platform owner duy trì CI.
Release authority quyết định rollout theo gate.

Load ở quy mô production chưa được tái tạo đầy đủ trong integration
environment. Rủi ro này được theo dõi bằng canary, queue lag và duplicate-order
signal trong cửa sổ quan sát đã phê duyệt.

## Review trigger

Review strategy khi event contract, database schema, consumer set hoặc
production telemetry thay đổi đáng kể.
~~~

### 13.1. Vì sao ví dụ này đủ dùng?

Brief nêu mục đích và ranh giới, chọn một số rủi ro có tác động, liên kết từng rủi ro với test và thời điểm chạy, giải thích trade-off của E2E, xác định gate và owner, đồng thời công khai giới hạn chưa được kiểm chứng. Người đọc có thể hiểu quyết định mà không cần xem toàn bộ test case.

## 14. Ví dụ chuyển câu chung chung thành quyết định có lý do

| Câu chưa đủ rõ | Cách viết có quyết định và rationale |
|---|---|
| “Chúng tôi sẽ kiểm thử API.” | “Chạy contract test cho API được consumer bên ngoài sử dụng trong mỗi PR có thay đổi schema, vì incompatibility có thể làm consumer lỗi sau khi provider deploy.” |
| “Tất cả chức năng phải được regression.” | “Regression tập trung vào luồng tạo/hủy đơn, tính tiền và trạng thái thanh toán; các luồng này có tác động giao dịch cao và từng có defect liên quan.” |
| “Sử dụng automation tối đa.” | “Tự động hóa unit, API, contract và smoke test ổn định; giữ exploratory testing cho hành vi mới vì yêu cầu còn thay đổi và cần quan sát linh hoạt.” |
| “Test trên nhiều thiết bị.” | “Kiểm tra P0 trên OS tối thiểu và phổ biến, thêm tổ hợp pairwise cho network/permission; dùng thiết bị thật cho camera và biometric vì emulator không đại diện đầy đủ phần cứng.” |
| “Performance phải tốt.” | “Chạy workload đại diện cho giờ cao điểm và đánh giá p95 latency, error rate cùng queue lag theo SLO đã thống nhất; không kết luận từ một lần chạy ngắn.” |
| “Không có lỗi nghiêm trọng.” | “Không phát hành khi còn defect Critical chưa xử lý; defect High cần service owner đánh giá và release authority chấp thuận theo quy trình ngoại lệ nếu policy cho phép.” |

## 15. Quản lý phiên bản và quyết định trong tài liệu

Strategy brief là tài liệu sống, nhưng không nên sửa âm thầm. Mỗi phiên bản cần ghi:

- Document ID, version và ngày cập nhật.
- Owner và reviewer.
- Phạm vi release/change áp dụng.
- Các quyết định mới hoặc đã thay đổi.
- Lý do và evidence tham chiếu.
- Người phê duyệt khi cần.
- Ngày review tiếp hoặc trigger cập nhật.

### 15.1. Decision log

| ID | Quyết định | Lý do/evidence | Trade-off | Owner | Trạng thái |
|---|---|---|---|---|---|
| D-01 | Contract test chạy trong PR | Consumer phát hành độc lập; contract drift từng gây lỗi | Cần cập nhật contract khi thay đổi có chủ đích | API owner | Approved |
| D-02 | E2E chỉ giữ luồng cốt lõi ở PR | E2E rộng chậm và flaky | Một số case chạy ở integration stage | Test lead | Approved |
| D-03 | Dùng canary cho phần chưa mô phỏng đủ tải | Staging không tái tạo đầy đủ production load | Cần monitoring và rollback readiness | SRE/release owner | Pending approval |

Decision log giúp người đọc biết vì sao chiến lược hiện tại có hình dạng như vậy và điều gì cần xem lại khi bối cảnh thay đổi.

### 15.2. Trigger review

Rà soát tài liệu khi:

- Thay đổi kiến trúc, API, schema hoặc dependency quan trọng.
- Incident hoặc escaped defect làm thay đổi đánh giá rủi ro.
- Support policy, SLO hoặc yêu cầu bảo mật thay đổi.
- Môi trường hoặc năng lực kiểm thử không còn đáp ứng.
- Một hard gate hoặc waiver được thay đổi.
- Owner hoặc quyền quyết định thay đổi.

## 16. Những lỗi thường gặp khi soạn strategy

- **Quá dài và lặp lại:** sao chép test plan, quy trình và tài liệu kiến trúc vào một nơi.
- **Quá ngắn và chung chung:** chỉ liệt kê tên test mà không có phạm vi, lý do hoặc gate.
- **Không nêu audience:** người đọc không biết tài liệu cần hỗ trợ quyết định nào.
- **Không phân biệt in scope/out of scope:** tạo kỳ vọng sai về mức bao phủ.
- **Chọn test theo thói quen:** không liên kết với rủi ro hoặc bằng chứng.
- **Không ghi trade-off:** người đọc không biết giới hạn của lựa chọn.
- **Không nêu trạng thái thiếu bằng chứng:** blocked/not run bị hiểu nhầm là pass.
- **Không có owner:** quyết định không chuyển thành hành động.
- **Ngưỡng không có nguồn:** con số được chọn tùy ý và khó bảo vệ.
- **Giả định bị trình bày như sự thật:** rủi ro còn lại bị che khuất.
- **Không phiên bản hóa:** không thể truy lại chiến lược tại thời điểm release.
- **Không review với người có quyền:** tài liệu được viết nhưng không tạo ra quyết định được chấp thuận.

## 17. Checklist review strategy brief

### Mục đích và phạm vi

- [ ] Tên sản phẩm/change, audience, owner và quyết định cần hỗ trợ được nêu.
- [ ] In scope, out of scope và giới hạn được phân biệt.
- [ ] Hành trình hoặc thành phần quan trọng được xác định.

### Rủi ro và cách tiếp cận

- [ ] Rủi ro được mô tả bằng điều kiện và hậu quả cụ thể.
- [ ] Mỗi rủi ro trọng yếu có test/evidence tương ứng.
- [ ] Lựa chọn test level, automation, môi trường và thời điểm có rationale.
- [ ] Trade-off và phương án thay thế quan trọng được nêu.

### Gate và trách nhiệm

- [ ] Hard gate, advisory và trạng thái thiếu bằng chứng rõ ràng.
- [ ] Waiver có điều kiện, owner và người phê duyệt.
- [ ] Service, test, platform, specialist và release owner được xác định.
- [ ] Điều kiện rollback/mitigation được nêu nếu cần.

### Giả định và quản trị

- [ ] Giả định và residual risk được công khai.
- [ ] Ngưỡng có nguồn hoặc owner xác định.
- [ ] Tài liệu liên kết tới test plan, risk register, dashboard và runbook liên quan.
- [ ] Version, reviewer, decision log và review trigger được ghi.
- [ ] Người có thẩm quyền đã review các quyết định thuộc phạm vi của họ.

### Kiểm tra độ súc tích

- [ ] Phần chính tập trung vào quyết định, không sao chép chi tiết triển khai.
- [ ] Mỗi đoạn đóng góp một thông tin cần thiết.
- [ ] Bảng có mục đích và cột rõ ràng.
- [ ] Thuật ngữ được dùng nhất quán và từ viết tắt được giải thích khi cần.
- [ ] Người đọc có thể tìm câu trả lời cho các quyết định chính trong vài phút.

## Kết luận

Một tài liệu chiến lược kiểm thử ngắn gọn cần nêu rõ mục đích, phạm vi, rủi ro, cách tạo bằng chứng, gate, owner và giới hạn. Mỗi lựa chọn quan trọng nên đi cùng rationale, trade-off và điều kiện review. Hãy bắt đầu từ quyết định cần hỗ trợ, liên kết rủi ro với test, dùng bảng để làm rõ phân bổ và trách nhiệm, rồi chuyển chi tiết vận hành sang tài liệu chuyên biệt có liên kết. Khi strategy brief đủ cụ thể để thực thi nhưng không lặp lại toàn bộ test plan, nó giúp stakeholder hiểu và phê duyệt các lựa chọn chất lượng một cách có căn cứ.
