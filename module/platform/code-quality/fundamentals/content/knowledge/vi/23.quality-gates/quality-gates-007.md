# Đặt ngưỡng có lý do và xem xét theo bối cảnh

## Mục tiêu học tập

Sau bài học này, bạn có thể:

1. Giải thích **cổng chất lượng (quality gate)** và phân biệt quy tắc kiểm tra, chỉ số đo, ngưỡng và quyết định cho phép hoặc chặn thay đổi.
2. Đặt ngưỡng dựa trên **rủi ro, yêu cầu sản phẩm, SLO, baseline, năng lực hệ thống và bằng chứng vận hành**, thay vì sao chép một con số chung.
3. Phân biệt **hard gate**, **soft gate**, cảnh báo và điều kiện cần theo dõi; chọn mức chặn phù hợp với mức nghiêm trọng và khả năng hành động.
4. Điều chỉnh cách áp dụng ngưỡng theo **loại thay đổi, mức quan trọng của luồng, dữ liệu, phạm vi triển khai, mã legacy và khả năng rollback**.
5. Tránh chạy theo coverage, số cảnh báo, điểm complexity hoặc p95 mà bỏ qua hành vi thật.
6. Thiết kế ngoại lệ có chủ sở hữu, lý do, biện pháp bù trừ, thời hạn và điều kiện xem xét lại; biết khi nào cần nâng, hạ hoặc loại bỏ một ngưỡng.

Trong module **CODE_QUALITY_FUNDAMENTALS**, chúng ta học những thuộc tính quyết định mã nguồn có **đáng tin cậy, dễ hiểu và dễ thay đổi hay không**. Cổng chất lượng biến một phần kỳ vọng đó thành điều kiện có thể kiểm tra trong quy trình phát triển và phát hành.

Một cổng chất lượng không tự làm phần mềm tốt. Nó chỉ đưa ra quyết định dựa trên những tín hiệu và quy tắc đã được thiết kế. Nếu ngưỡng không có căn cứ, nhóm có thể chặn những thay đổi an toàn, bỏ lọt rủi ro thật hoặc tìm cách làm đẹp chỉ số để vượt CI.

**Nguyên tắc xuyên suốt:** Một ngưỡng tốt phải trả lời được **vì sao con số hoặc điều kiện ấy phù hợp, áp dụng cho phạm vi nào, bằng chứng nào được dùng, điều gì xảy ra khi vượt ngưỡng và khi nào cần xem xét lại**.

## 1. Cổng chất lượng là gì?

**Quality gate** là tập hợp điều kiện được dùng để quyết định một thay đổi, bản build hoặc đợt phát hành có đủ điều kiện đi tiếp hay không.

Một cổng có thể kiểm tra:
- Build có biên dịch thành công không?
- Test bắt buộc có vượt qua không?
- Có lỗi bảo mật nghiêm trọng đã xác nhận không?
- API có vi phạm contract đã công bố không?
- Một luồng quan trọng có vượt SLO về độ trễ hoặc tỷ lệ lỗi không?
- Thay đổi có làm tăng nợ kỹ thuật vượt ngân sách đã thống nhất không?
- Những điều kiện bắt buộc về review, migration hoặc rollback đã được đáp ứng chưa?

Ví dụ, một pull request có thể phải:
1. Biên dịch thành công.
2. Vượt qua unit test và test hợp đồng liên quan.
3. Không thêm lỗ hổng mức nghiêm trọng cao đã xác nhận và có thể khai thác trong phạm vi triển khai.
4. Không làm giảm coverage của phần mã mới dưới mức nhóm đã chọn cho loại module đó.
5. Có review cần thiết và kế hoạch migration nếu thay đổi schema.

Đây là **một chính sách của dự án**, không phải danh sách phổ quát cho mọi repository. Một thư viện mã nguồn mở, một công cụ nội bộ và một dịch vụ xử lý thanh toán có thể cần những cổng khác nhau.

### Phân biệt bốn khái niệm

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Quy tắc (rule)** | Điều cần kiểm tra | Không cho phép API công khai thay đổi ngoài kế hoạch versioning |
| **Chỉ số (metric)** | Giá trị quan sát được | p95 latency, tỷ lệ lỗi, coverage, số cảnh báo |
| **Ngưỡng (threshold)** | Mức hoặc điều kiện dùng để diễn giải chỉ số | p95 không vượt SLO của endpoint trong workload xác định |
| **Cổng (gate)** | Quyết định khi áp dụng quy tắc và ngưỡng | Pass, fail, warn hoặc cần thêm bằng chứng |

Một chỉ số không tự nói lên chất lượng. Ví dụ, **coverage 85%** chỉ mô tả phần mã được công cụ ghi nhận đã chạy theo cách đo cụ thể; nó không chứng minh test đã kiểm tra đúng kết quả. Cần biết **đo cái gì, trên phạm vi nào, bằng công cụ nào và dùng ngưỡng đó để bảo vệ rủi ro nào**.

## 2. Vì sao không có một ngưỡng đúng cho mọi hệ thống?

Một con số có thể hợp lý ở nơi này nhưng vô lý ở nơi khác.

Ví dụ:
- p95 500 ms có thể chấp nhận cho một báo cáo nội bộ chạy nền, nhưng không phù hợp với thao tác xác nhận thanh toán cần phản hồi nhanh.
- Coverage 70% có thể là bước cải thiện đáng kể cho một module legacy chưa có test, nhưng thấp hơn kỳ vọng của một thư viện mới có API công khai và nhiều người phụ thuộc.
- Một cảnh báo dependency mức trung bình có thể chờ kế hoạch nâng cấp nếu không có đường khai thác phù hợp; một lỗ hổng nghiêm trọng đang bị khai thác trong thành phần public-facing cần phản ứng khẩn cấp.
- Một job batch chạy 15 phút mỗi đêm có thể đáp ứng yêu cầu; cùng thời gian đó trong luồng đồng bộ của người dùng có thể gây timeout.

Ngưỡng phải được đặt trong **bối cảnh sử dụng**.

### Những yếu tố làm thay đổi ngưỡng

| Yếu tố | Câu hỏi cần đặt ra | Ảnh hưởng có thể có |
| --- | --- | --- |
| **Mức quan trọng nghiệp vụ** | Lỗi có làm mất tiền, mất dữ liệu hoặc chặn hoạt động cốt lõi không? | Luồng quan trọng cần guardrail chặt hơn |
| **Mức phơi bày** | API nội bộ hay public-facing? Có nhận dữ liệu không tin cậy không? | Bảo mật, tải và tương thích cần mức kiểm soát khác |
| **Dữ liệu** | Dữ liệu nhạy cảm, lịch sử hay có thể tái tạo? | Yêu cầu về quyền, migration, audit và phục hồi |
| **Tần suất thay đổi** | Module có được sửa thường xuyên không? | Rủi ro hồi quy và lợi ích của test có thể cao hơn |
| **Quy mô và phân bố tải** | Tải đều hay có hot key, tenant lớn, burst? | Cần metric theo nhóm và phân vị |
| **Mức trưởng thành** | Hệ thống mới hay legacy nhiều ràng buộc? | Cách áp dụng baseline và lộ trình nâng ngưỡng khác nhau |
| **Phạm vi thay đổi** | Chỉ đổi văn bản hay đổi transaction, schema, quyền? | Cổng cần kiểm tra theo loại thay đổi |
| **Khả năng phục hồi** | Có rollback, backup, replay hoặc feature flag không? | Mức rủi ro có thể được giảm bằng biện pháp phục hồi |
| **Nghĩa vụ bên ngoài** | Có SLO, hợp đồng, luật hoặc yêu cầu kiểm toán không? | Có thể có ngưỡng bắt buộc không được miễn tùy ý |

Không nên dùng **độ quan trọng của module** làm lý do duy nhất để tăng mọi con số. Cần xác định rủi ro cụ thể: một module thanh toán có thể cần kiểm tra chính xác tiền và idempotency rất chặt, nhưng không nhất thiết phải có một ngưỡng line coverage cao hơn mọi module khác nếu chỉ số ấy không đo được rủi ro tương ứng.

## 3. Ngưỡng phải xuất phát từ mục tiêu và bằng chứng

Trước khi chọn một con số, hãy trả lời bốn câu hỏi:

1. **Muốn bảo vệ điều gì?** Hành vi, bảo mật, khả năng tương thích, hiệu năng, độ tin cậy hay khả năng bảo trì?
2. **Bằng chứng nào phản ánh điều đó?** Test, metric vận hành, phân tích phụ thuộc, review contract hay kiểm tra thủ công có kiểm soát?
3. **Ngưỡng nào phân biệt mức chấp nhận với mức cần hành động?** Dựa trên yêu cầu, baseline, năng lực và hậu quả.
4. **Khi vượt ngưỡng, ai làm gì?** Chặn merge, cảnh báo, điều tra, giảm rollout hay mở incident?

Ví dụ mục tiêu chưa đủ:

> “Coverage phải trên 80% vì dự án khác cũng dùng 80%.”

Mục tiêu rõ hơn:

> “Đối với module tính tiền mới, mọi nhánh quy tắc tính giá và làm tròn phải có test cho trường hợp biên đã xác nhận. Coverage của mã mới được dùng như một tín hiệu phụ để phát hiện vùng chưa được chạy; ngưỡng cảnh báo được chọn sau khi xem baseline và khả năng của công cụ. PR vẫn phải có test kiểm tra kết quả, không chỉ đạt tỷ lệ dòng.”

Ví dụ thứ hai không dựa vào một con số coverage làm đại diện cho tính đúng đắn. Nó xác định **rủi ro cần bảo vệ** và vai trò giới hạn của metric.

### Các nguồn bằng chứng có thể dùng

- **Yêu cầu sản phẩm:** thời gian phản hồi, tính sẵn sàng, khả năng tương thích, mức dữ liệu được xử lý.
- **SLO/SLA:** mục tiêu đã thống nhất cho availability, latency, error rate hoặc độ mới dữ liệu.
- **Baseline:** số đo trước thay đổi, tình trạng hiện tại của module hoặc nhánh chính.
- **Lịch sử sự cố:** loại lỗi đã từng xảy ra, nguyên nhân và tác động.
- **Workload đại diện:** kích thước, tần suất, phân bố key/tenant, burst và phụ thuộc.
- **Nghĩa vụ bảo mật/tuân thủ:** yêu cầu bắt buộc về truy cập, audit, lưu trữ hoặc dependency.
- **Khả năng phục hồi:** thời gian rollback, khả năng khôi phục dữ liệu, replay và giới hạn blast radius.
- **Chi phí thay đổi:** số nơi phải sửa, thời gian kiểm chứng, tỷ lệ hồi quy và mức phụ thuộc.

Nếu chưa có đủ bằng chứng, có thể đặt **ngưỡng tạm thời** với người chịu trách nhiệm và ngày xem lại. Không nên trình bày một con số ước đoán như một chuẩn đã được xác nhận.

## 4. Hard gate, soft gate và cảnh báo

Không phải mọi quy tắc đều nên chặn merge theo cùng cách.

### 4.1. Hard gate

**Hard gate** là điều kiện bắt buộc; nếu không đạt thì thay đổi không được đi tiếp theo quy trình bình thường.

Có thể phù hợp với:
- Build không biên dịch.
- Test bắt buộc thất bại.
- Contract công khai bị phá mà không có versioning hoặc phê duyệt cần thiết.
- Một kiểm tra bảo mật phát hiện rủi ro nghiêm trọng đã xác nhận và chưa có biện pháp kiểm soát.
- Migration không có kế hoạch bảo vệ dữ liệu ở một luồng quan trọng.
- Thiếu review hoặc phê duyệt bắt buộc theo chính sách tổ chức.

Hard gate nên **ổn định, có thể tái hiện và có hướng xử lý rõ**. Nếu CI thường xuyên chặn do test flake hoặc scanner nhiễu, nhóm sẽ mất niềm tin và tìm cách bypass.

### 4.2. Soft gate

**Soft gate** đưa ra cảnh báo hoặc yêu cầu xem xét, nhưng không tự động chặn trong mọi trường hợp.

Có thể phù hợp với:
- Một metric maintainability đang xấu dần nhưng chưa có rủi ro trực tiếp.
- Coverage của module legacy chưa đạt mục tiêu dài hạn.
- Cảnh báo dependency cần đánh giá khả năng khai thác và lộ trình nâng cấp.
- Một benchmark có độ biến thiên lớn, cần thêm mẫu trước khi kết luận.
- Số cảnh báo lint tăng nhẹ trong một khu vực chưa được ưu tiên.

Soft gate không có nghĩa bỏ qua. Cần có owner, cách xem xét và trigger nâng thành hard gate nếu rủi ro tăng.

### 4.3. Cảnh báo và thông tin

Một số tín hiệu chỉ nên được ghi nhận:
- Xu hướng số test tăng hoặc giảm.
- Thời gian build thay đổi.
- Tỷ lệ cache hit.
- Số lượng module phụ thuộc vào một package.
- Một metric mới chưa đủ dữ liệu để chọn ngưỡng.

Không nên chặn quy trình dựa trên một chỉ số chưa được hiểu rõ. Trước hết cần xác minh tính ổn định và mối liên hệ của nó với mục tiêu.

### So sánh

| Loại | Hành vi khi không đạt | Điều kiện sử dụng phù hợp |
| --- | --- | --- |
| **Hard gate** | Chặn hoặc yêu cầu phê duyệt ngoại lệ chính thức | Rủi ro cao, điều kiện rõ, kiểm tra đáng tin |
| **Soft gate** | Cảnh báo, yêu cầu đánh giá hoặc tạo công việc | Rủi ro cần quản lý nhưng chưa đủ cơ sở chặn mọi thay đổi |
| **Warning/informational** | Ghi nhận và quan sát xu hướng | Metric mới, rủi ro thấp hoặc cần thêm dữ liệu |

Một pipeline tốt có thể có cả ba. **Không nên biến mọi cảnh báo thành hard gate**, vì khi tất cả đều khẩn cấp thì không còn tín hiệu nào nổi bật.

## 5. Ngưỡng tuyệt đối, ngưỡng tương đối và xu hướng

Có nhiều cách định nghĩa ngưỡng. Mỗi cách phù hợp với loại vấn đề khác nhau.

### 5.1. Ngưỡng tuyệt đối

Một giá trị cố định được kiểm tra trực tiếp.

Ví dụ:
- Payload API không vượt giới hạn đã công bố.
- Một endpoint phải đáp ứng p95 trong SLO.
- Số lượng trên một dòng đơn không vượt giới hạn nghiệp vụ.
- Không cho phép một kiểu lỗi bắt buộc đã được xác định.

Ưu điểm: dễ hiểu và dễ thực thi. Nhược điểm: nếu bối cảnh thay đổi, con số cũ có thể không còn phù hợp.

### 5.2. Ngưỡng tương đối với baseline

Thay đổi được so sánh với một trạng thái chuẩn:
- Không làm tăng số cảnh báo mới so với nhánh chính.
- Không làm p95 xấu đi quá mức cho phép trong cùng workload.
- Không giảm coverage của phần mã thay đổi dưới mức nhóm đã thống nhất.
- Không thêm dependency vượt ngân sách module.

Ưu điểm: hữu ích cho codebase legacy và giúp tránh làm tình trạng xấu hơn. Nhược điểm: **baseline có thể đã tệ**; chỉ giữ nguyên baseline không đồng nghĩa chất lượng đạt yêu cầu.

### 5.3. Ngưỡng theo xu hướng

Một metric được xem qua nhiều cửa sổ thời gian:
- Số lỗi tăng liên tục trong nhiều phiên bản.
- p99 tăng trong các đợt tải tương đương.
- Thời gian build tăng qua nhiều tuần.
- Số cảnh báo mới tăng dần ở một module.

Xu hướng giúp giảm phản ứng quá mức với một lần đo nhiễu. Nhưng phải xác định **cửa sổ, lượng mẫu, cách loại trừ sự kiện bất thường và người xem xét**.

### 5.4. Ngưỡng kết hợp

Một gate có thể cần nhiều điều kiện cùng lúc:
- p95 vượt SLO **và** lượng mẫu đủ lớn.
- Có cảnh báo bảo mật nghiêm trọng **và** thành phần nằm trên đường thực thi có thể khai thác.
- Coverage giảm **và** phần giảm nằm trong mã mới có rủi ro cao.
- Migration thay đổi schema **và** có dữ liệu hiện hữu cần chuyển đổi.

Kết hợp điều kiện giúp giảm false positive, nhưng không nên làm rule khó hiểu đến mức không ai biết vì sao gate thất bại.

## 6. Baseline và ratchet cho codebase legacy

Một hệ thống lâu năm có thể đã có:
- Hàng nghìn cảnh báo static analysis.
- Coverage thấp ở module cũ.
- Dependency lỗi thời.
- Một số test chậm hoặc thiếu ổn định.
- Các lớp có complexity cao.

Nếu bật hard gate yêu cầu toàn repository đạt chuẩn mới ngay lập tức, nhóm có thể phải dừng mọi phát triển hoặc tạo hàng loạt ngoại lệ. Nhưng nếu giữ nguyên tất cả mã cũ vô thời hạn, chất lượng cũng không cải thiện.

Một cách tiếp cận là **baseline + ratchet**.

### Baseline là gì?

Baseline ghi lại tình trạng hiện tại theo một phương pháp đo và phạm vi rõ ràng:
- Commit hoặc phiên bản nào được dùng làm mốc.
- Công cụ và ruleset phiên bản nào.
- Những cảnh báo nào đã tồn tại.
- Phần mã nào được tính coverage.
- Cách loại trừ generated code, test fixture hoặc thư mục không thuộc phạm vi.

Baseline giúp phân biệt **nợ cũ** với **hồi quy mới**. Nó không tuyên bố nợ cũ là an toàn.

### Ratchet là gì?

Ratchet là cách nâng chuẩn dần mà không cho tình trạng mới xấu hơn:
- Không thêm cảnh báo mới thuộc nhóm đã chặn.
- Phần mã mới phải đạt yêu cầu test đã chọn.
- Khi sửa một module cũ, không làm giảm chất lượng của vùng đó.
- Mỗi giai đoạn giảm một phần cảnh báo cũ.
- Sau khi nợ cũ được xử lý, nâng ngưỡng hoặc mở rộng phạm vi gate.

Ví dụ minh họa:

| Giai đoạn | Quy tắc |
| --- | --- |
| **Bắt đầu** | Ghi baseline cảnh báo hiện hữu; chặn một số loại lỗi mới có rủi ro cao |
| **Mã mới** | Áp dụng test và static checks đầy đủ cho mã mới |
| **Khi sửa mã cũ** | Không thêm lỗi mới trong vùng thay đổi; xử lý cảnh báo liên quan trực tiếp |
| **Theo kế hoạch** | Giảm dần nhóm cảnh báo cũ theo mức rủi ro |
| **Sau khi ổn định** | Nâng ngưỡng và mở rộng hard gate khi công cụ đáng tin |

### Rủi ro của baseline

- Baseline được tạo khi công cụ sai cấu hình.
- Cảnh báo nghiêm trọng bị đưa vào danh sách “đã tồn tại” mà không đánh giá.
- Mã cũ được miễn trừ dù đang được thay đổi nhiều.
- Baseline không được cập nhật khi phạm vi hoặc công cụ đổi.
- Nhóm coi “không tệ hơn” là mục tiêu cuối cùng.

**Baseline là mốc để cải thiện, không phải giấy phép bỏ qua rủi ro.** Lỗ hổng nghiêm trọng, vi phạm quyền hoặc lỗi dữ liệu vẫn phải xử lý theo mức ảnh hưởng thực tế, dù chúng đã tồn tại trước đó.

## 7. Đặt ngưỡng cho test và coverage

Coverage có thể là:
- **Line coverage:** tỷ lệ dòng được thực thi.
- **Branch coverage:** tỷ lệ nhánh điều khiển được thực thi.
- **Condition coverage:** mức các điều kiện logic nhận cả giá trị đúng/sai theo cách đo của công cụ.
- **Mutation score:** tỷ lệ mutation được test phát hiện trong tập mutation được tạo.

Các chỉ số này cung cấp góc nhìn khác nhau; không chỉ số nào chứng minh test đã xác nhận đúng nghiệp vụ.

### Vì sao một tỷ lệ chung dễ gây hiểu lầm?

Giả sử:
- Module A có coverage 95%, nhưng test chỉ gọi getter và không assert kết quả quan trọng.
- Module B có coverage 75%, nhưng những nhánh tính tiền, phân quyền và trường hợp biên đều được kiểm tra tốt.
- Module C có coverage 40% vì chứa adapter phụ thuộc hệ thống ngoài chưa được test tích hợp.

Chỉ nhìn tỷ lệ có thể đánh giá sai thứ tự rủi ro.

### Cách đặt gate coverage có lý do

1. Xác định **phạm vi đo**: toàn bộ module, mã mới, mã thay đổi hay package cụ thể.
2. Xác định loại coverage nào phù hợp với rủi ro.
3. Đặt yêu cầu test cho các nhánh nghiệp vụ quan trọng, không chỉ một tỷ lệ tổng.
4. Dùng coverage như tín hiệu phát hiện vùng chưa chạy, không làm bằng chứng duy nhất.
5. Theo dõi test chất lượng: assertion có ý nghĩa, test có thể phát hiện lỗi và có kiểm tra trường hợp biên.
6. Định kỳ xem lại cách công cụ tính, exclusions và code generated.

Ví dụ, nhóm có thể đặt **mức coverage tối thiểu cho phần mã mới** sau khi đo baseline và thử nghiệm trong CI. Con số 80% thường được dùng làm ví dụ trong thảo luận, nhưng **không phải ngưỡng mặc định được khuyến nghị ở đây**. Mức phù hợp phụ thuộc loại mã, độ rủi ro, công cụ và khả năng viết test có ý nghĩa.

### Đừng tối ưu để đạt coverage bằng mọi giá

Những cách làm sai:
- Gọi một phương thức chỉ để tăng line coverage.
- Viết test không có assertion.
- Loại trừ mọi class khó test khỏi báo cáo.
- Test private implementation thay vì hợp đồng.
- Mock tất cả phụ thuộc khiến test không còn xác nhận tích hợp quan trọng.
- Giảm phạm vi đo để tỷ lệ đẹp hơn mà không ghi rõ.

Một gate tốt nên khuyến khích **test có khả năng phát hiện lỗi**, không khuyến khích “đi qua dòng code”.

## 8. Đặt ngưỡng cho static analysis và code smells

Static analyzer có thể phát hiện:
- Null dereference có khả năng xảy ra.
- Tài nguyên không được đóng.
- API nguy hiểm.
- Code không thể chạy hoặc nhánh không thể tới.
- Duplicate code theo cấu trúc mà công cụ nhận diện.
- Complexity cao hoặc cấu trúc khó bảo trì.
- Vi phạm quy ước.

Không phải mọi cảnh báo có cùng mức nghiêm trọng.

### Phân loại theo rủi ro

| Nhóm | Ví dụ | Cách xử lý có thể phù hợp |
| --- | --- | --- |
| **Lỗi correctness** | Luồng có thể dùng null, đóng tài nguyên sai | Hard gate khi được xác nhận và có khả năng gây lỗi |
| **Bảo mật** | Injection, kiểm tra quyền thiếu, secret lộ | Ưu tiên theo mức nghiêm trọng và khả năng khai thác |
| **Độ tin cậy** | Nuốt exception, retry vô hạn, thiếu timeout | Gate theo luồng và hậu quả |
| **Maintainability** | Complexity cao, tên khó hiểu, duplication | Có thể soft gate hoặc ratchet |
| **Style** | Khoảng trắng, import, format | Formatter/linter tự động; thường dễ chặn vì ít mơ hồ |

Một ngưỡng như “không có cảnh báo mới mức blocker” có thể phù hợp nếu nhóm đã xác định blocker là lỗi có tác động lớn và công cụ có tỷ lệ false positive thấp. Nhưng nếu một rule thường báo sai, hard gate sẽ làm pipeline mất độ tin cậy.

### Đừng dùng tổng số cảnh báo đơn lẻ

Số cảnh báo có thể tăng vì:
- Thêm nhiều dòng code.
- Nâng phiên bản analyzer và phát hiện thêm pattern.
- Mở rộng phạm vi scan.
- Thay đổi ruleset.
- Một cảnh báo được nhân bản trên nhiều module.

Nên xem **cảnh báo mới, mức nghiêm trọng, vị trí, khả năng khai thác, trạng thái baseline và tác động thực tế**. Đếm tổng số mà không phân loại có thể khiến nhóm bỏ qua lỗi nghiêm trọng giữa hàng trăm cảnh báo nhỏ.

## 9. Đặt ngưỡng bảo mật theo mức rủi ro và khả năng khai thác

Một báo cáo dependency có thể chứa nhiều CVE với mức severity khác nhau. Severity là tín hiệu quan trọng nhưng chưa đủ để quyết định tự động.

Cần xem:
- Thành phần có nằm trong **runtime path** hay chỉ là test/build tool?
- Chức năng bị ảnh hưởng có được sử dụng không?
- Dịch vụ có public-facing hay chỉ chạy trong mạng giới hạn?
- Có dữ liệu nhạy cảm hoặc quyền cao trong đường thực thi?
- Có exploit đã được công bố/khai thác không?
- Phiên bản bị ảnh hưởng có thực sự được triển khai không?
- Có bản vá hoặc biện pháp giảm thiểu được hỗ trợ không?
- Nâng cấp có phá tương thích hoặc tạo rủi ro lớn hơn không?

### Ví dụ chính sách minh họa

- Lỗ hổng nghiêm trọng, có thể khai thác trong đường chạy public-facing: **hard gate** và quy trình xử lý khẩn cấp.
- Lỗ hổng mức trung bình ở dependency chỉ dùng trong test, chưa có đường khai thác phù hợp: **cảnh báo có owner và deadline đánh giá**.
- Dependency hết hỗ trợ nhưng không có lỗ hổng đã biết: **kế hoạch nâng cấp theo thời hạn**, cân nhắc khả năng tương thích.
- Secret được phát hiện trong mã hoặc artifact: xử lý như sự cố bảo mật, thu hồi/rotate theo quy trình; không chỉ xóa dòng rồi cho qua.

Đây là ví dụ về phân loại, không thay thế chính sách bảo mật của tổ chức. Không nên bỏ qua một lỗ hổng chỉ vì scanner đánh giá thấp nếu phân tích thực tế cho thấy đường khai thác nghiêm trọng.

### Ngưỡng bảo mật không nên chỉ dựa trên CVSS

CVSS giúp mô tả mức độ nghiêm trọng theo một mô hình, nhưng **khả năng khai thác trong hệ thống cụ thể** còn phụ thuộc cấu hình, exposure, dữ liệu và quyền. Cần kết hợp severity với reachability, exploitability và tác động nghiệp vụ.

Ngoại lệ bảo mật phải có người có thẩm quyền chấp nhận rủi ro, biện pháp bù trừ và thời hạn. Một ticket “accepted” không thể làm lỗ hổng biến mất.

## 10. Đặt ngưỡng cho hiệu năng và SLO

Với hiệu năng, một ngưỡng chỉ có nghĩa khi **đo cùng một loại công việc trong điều kiện xác định**.

Ví dụ mục tiêu:
- p95 của API tra cứu đơn không vượt mức SLO.
- p99 không xấu đi đáng kể sau thay đổi.
- Tỷ lệ lỗi và timeout không tăng.
- Throughput hoàn tất đạt tải mục tiêu.
- Queue và connection wait không tăng liên tục.
- CPU/heap/GC nằm trong ngân sách vận hành.

### Vì sao p95 cần bối cảnh?

Một con số p95 thiếu các thông tin:
- Endpoint và loại request.
- Thời gian cửa sổ đo, số mẫu.
- Tải đến và mức đồng thời.
- Phân bố key/tenant/payload.
- Warm-up, cache state và cấu hình JVM.
- Tình trạng database và dịch vụ phụ thuộc.
- Tỷ lệ lỗi, retry và timeout.

Nếu bài test chỉ dùng 100 request giống nhau trên cache đã warm, nó có thể không phản ánh giờ cao điểm có hot key và nhiều cache miss.

### Ví dụ gate hiệu năng

Giả sử endpoint xác nhận đơn có SLO p95 là 300 ms trong workload đã được định nghĩa. Gate cho một thay đổi ảnh hưởng luồng đó có thể yêu cầu:
- Bộ tải tạo đủ request theo mô hình đã thống nhất.
- Lượng mẫu tối thiểu đủ để phân vị có ý nghĩa.
- p95 không vượt 300 ms.
- p99 không vượt guardrail riêng.
- Error rate và timeout không vượt ngân sách.
- Không có queue tăng liên tục khi tải ổn định.

**300 ms là số minh họa**, không phải chuẩn chung. SLO phải xuất phát từ trải nghiệm người dùng, phụ thuộc và khả năng vận hành.

### Không kết luận từ một lần đo nhiễu

Nếu p95 thay đổi vài mili giây nhưng độ biến thiên giữa các lần chạy lớn hơn mức chênh, chưa đủ bằng chứng để chặn hoặc cho qua. Có thể cần:
- Chạy lặp trong môi trường ổn định.
- Tăng lượng mẫu.
- So sánh cùng baseline.
- Tách nhóm request.
- Xác định khoảng tin cậy hoặc mức biến thiên thực tế phù hợp với công cụ.

Không nên biến một benchmark không ổn định thành hard gate chỉ để pipeline có vẻ nghiêm ngặt.

## 11. Đặt ngưỡng cho độ tin cậy và khả năng phục hồi

Một hệ thống có thể vượt test chức năng nhưng vẫn thiếu khả năng xử lý lỗi phụ thuộc.

Các gate có thể liên quan tới:
- Timeout cho mọi lời gọi ngoài quan trọng.
- Retry có giới hạn và phù hợp idempotency.
- Không retry vô hạn khi dịch vụ đang quá tải.
- Có giới hạn queue/concurrency.
- Có hành vi từ chối hoặc fallback được định nghĩa.
- Có backup, restore hoặc replay được kiểm chứng với dữ liệu cần bảo vệ.
- Migration có chiến lược rollback hoặc forward-fix.
- Cảnh báo vận hành có owner và runbook.

### SLO và error budget

**SLO (Service Level Objective)** là mục tiêu chất lượng dịch vụ trong một cửa sổ đo, ví dụ tỷ lệ request thành công hoặc độ trễ. **Error budget** biểu diễn phần lỗi/không đáp ứng được phép xảy ra theo SLO trong khoảng thời gian đó.

Nếu một dịch vụ có SLO availability 99,9%, error budget phản ánh phần thời gian hoặc request không đạt mục tiêu theo định nghĩa cụ thể. Khi budget bị tiêu thụ nhanh, nhóm có thể:
- Tạm giảm tốc độ phát hành thay đổi rủi ro.
- Ưu tiên reliability work.
- Điều tra nguyên nhân sự cố.
- Tăng cường kiểm thử và rollout có kiểm soát.

Không nên lấy một SLO availability duy nhất làm gate cho mọi thay đổi. Một thay đổi chỉ sửa nội dung tài liệu không có cùng rủi ro với thay đổi connection pool hoặc retry policy. Gate cần **liên hệ với blast radius của thay đổi**.

## 12. Đặt ngưỡng cho maintainability mà không biến nó thành cuộc thi điểm số

Maintainability khó đo bằng một con số duy nhất. Một số tín hiệu có thể hỗ trợ:
- Số cảnh báo mới thuộc nhóm có rủi ro.
- Độ phức tạp của phần mã thay đổi.
- Số module phụ thuộc trực tiếp vào chi tiết nội bộ.
- Mức độ lặp tri thức phải sửa cùng nhau.
- Khả năng test một quy tắc mà không dựng toàn bộ hạ tầng.
- Thời gian build/test và độ ổn định của CI.
- Số lần sửa hồi quy trong cùng khu vực.

### Dùng ngưỡng như hàng rào, không phải định nghĩa chất lượng

Ví dụ, nhóm có thể chọn:
- Không thêm dependency vòng mới.
- Không tăng số cảnh báo blocker.
- Không đưa logic nghiệp vụ mới vào package hạ tầng.
- Không thêm public API không có hợp đồng hoặc tài liệu phù hợp.
- Không để một thay đổi nhỏ làm sửa nhiều module ngoài phạm vi mà không giải thích.

Các điều kiện này thường diễn đạt **nguyên tắc kiến trúc** rõ hơn một con số complexity chung.

### Khi complexity vượt ngưỡng

Nếu một phương thức có complexity cao, đừng tự động tách nó thành nhiều hàm. Hãy hỏi:
- Các nhánh có đại diện cho các quy tắc nghiệp vụ độc lập không?
- Có thể lập bảng quyết định để xác nhận tính đầy đủ không?
- Có trạng thái ngầm hoặc boolean flag làm thay đổi nhiều nhánh không?
- Tách hàm có giảm số giả định cần giữ trong đầu không?
- Có thể test nhánh quan trọng độc lập không?

Ngưỡng complexity nên là **tín hiệu yêu cầu review**, trừ khi nhóm đã xác định một phạm vi rất cụ thể mà mức vượt thực sự có liên hệ với rủi ro.

## 13. Áp dụng ngưỡng theo phạm vi thay đổi

Một thay đổi nhỏ và một thay đổi có blast radius lớn không cần cùng tập gate.

| Loại thay đổi | Gate thường cần xem xét |
| --- | --- |
| **Sửa văn bản hoặc comment** | Format, lint cơ bản; không cần load test nếu không ảnh hưởng runtime |
| **Thay đổi logic thuần** | Unit test, static analysis, trường hợp biên |
| **Thay đổi API public** | Contract/serialization test, compatibility/versioning, security |
| **Thay đổi schema/database** | Migration, backup/rollback, integration test, đối soát dữ liệu |
| **Thay đổi authentication/authorization** | Test quyền theo chủ thể/tài nguyên, security review, audit |
| **Thay đổi transaction hoặc đồng thời** | Integration/concurrency test, idempotency, lock và rollback |
| **Thay đổi hot path hiệu năng** | Benchmark/load test đúng workload, p95/p99, tài nguyên |
| **Nâng dependency nền tảng** | Compatibility test, security scan, smoke/integration test |
| **Thay đổi pipeline/deployment** | Kiểm tra artifact, cấu hình, rollout, rollback và quyền triển khai |

Không nên chỉ dựa vào danh sách file để xác định rủi ro. Một thay đổi một dòng trong hàm kiểm tra quyền có thể rất quan trọng; một thay đổi hàng trăm dòng generated code có thể không thay đổi logic thủ công. Cần phân loại theo **hành vi và ranh giới bị tác động**.

### Gate theo module và luồng nghiệp vụ

Có thể áp dụng một số gate chung toàn repository và thêm gate theo miền:
- Module tính tiền: test làm tròn, currency, trường hợp biên.
- Module bảo mật: kiểm tra quyền, secret, dependency và audit.
- Module báo cáo: giới hạn dữ liệu, tính đầy đủ, thời gian xử lý.
- Module tích hợp: contract, timeout, retry và schema.
- Thư viện dùng chung: tương thích API và kiểm thử consumer.

Không nên sao chép một cấu hình khổng lồ cho mọi module nếu rủi ro khác nhau. Nhưng cũng không nên tạo quá nhiều ngoại lệ khiến không ai hiểu pipeline đang bảo vệ điều gì.

## 14. Gate trong các giai đoạn của pipeline

Cổng chất lượng có thể được phân bố theo vòng đời:

~~~mermaid
flowchart TD
    A[Local development] --> B[Pull request]
    B --> C[Merge / main branch]
    C --> D[Staging / pre-production]
    D --> E[Production rollout]
    E --> F[Post-deployment observation]
    F --> G[Review thresholds and incidents]
    G --> B
~~~

### Local development

Mục tiêu là phản hồi nhanh:
- Formatter.
- Compile.
- Unit test nhỏ.
- Lint nhanh.
- Kiểm tra secret cơ bản.

Không nên yêu cầu mọi kiểm tra tải kéo dài hàng giờ trên máy lập trình viên.

### Pull request

Mục tiêu là phát hiện sớm lỗi do thay đổi:
- Build và test bắt buộc.
- Static analysis theo phạm vi.
- Test contract cho API bị ảnh hưởng.
- Kiểm tra migration hoặc dependency.
- Review bắt buộc với khu vực rủi ro cao.

### Main branch và staging

Có thể chạy:
- Integration test với database hoặc dịch vụ phụ thuộc phù hợp.
- Test migration từ schema hiện tại.
- Security scan đầy đủ hơn.
- Smoke test và test luồng nghiệp vụ chính.
- Performance test theo lịch hoặc khi thay đổi hot path.

### Production rollout

Không chỉ dựa vào CI:
- Canary hoặc rollout từng phần.
- Theo dõi error rate, latency, saturation.
- Health checks và khả năng rollback.
- Feature flag cho thay đổi có thể tách.
- Dừng rollout khi guardrail vi phạm.

### Sau triển khai

Metric production có thể cho thấy ngưỡng trước đó không còn phù hợp. Cần:
- So sánh với SLO và baseline.
- Xem phân bố theo endpoint/tenant.
- Đánh giá false positive/negative của gate.
- Cập nhật quy tắc khi có bằng chứng mới.

**Quality gate là một vòng phản hồi**, không phải bộ luật viết một lần rồi giữ mãi.

## 15. Ví dụ cấu hình một quality gate có ngữ cảnh

Đoạn dưới đây là **pseudo-configuration để minh họa ý tưởng**, không phải schema hợp lệ cho một CI provider cụ thể:

~~~yaml
qualityGates:
  pullRequest:
    compile:
      required: true
      failureAction: block

    unitTests:
      required: true
      failureAction: block

    newHighRiskFindings:
      required: true
      scope: changed-code-and-reachable-dependencies
      failureAction: block
      exceptionRequires:
        - owner
        - rationale
        - compensatingControl
        - expiry

    coverage:
      scope: changed-production-code
      mode: signal
      threshold: project-defined
      failureAction: warn

  staging:
    apiContracts:
      requiredForChangedPublicApis: true
      failureAction: block

    migration:
      requiredWhenSchemaChanges: true
      failureAction: block

    performance:
      requiredForHotPathChanges: true
      workload: representative
      minimumSamples: project-defined
      compareWith: baseline
      guardrails:
        - p95
        - p99
        - errorRate
        - resourceSaturation

  production:
    rollout:
      mode: canary
      stopOn:
        - errorBudgetBurn
        - latencyGuardrailViolation
        - criticalHealthCheckFailure
~~~

Các giá trị **project-defined** phải được xác định bằng dữ liệu và chính sách thật. Tên trường **scope**, **failureAction** và cấu trúc YAML trên chỉ nhằm giúp diễn đạt quyết định; không được sao chép nguyên văn rồi kỳ vọng một công cụ tự hiểu.

### Vì sao coverage để ở mức signal trong ví dụ?

Bởi vì coverage là chỉ số gián tiếp. Nhóm có thể nâng nó thành hard gate khi:
- Phạm vi đo ổn định.
- Loại trừ đã được quản lý.
- Mã mới có tiêu chí rõ.
- Test có assertion và chất lượng phù hợp.
- Gate không tạo động lực viết test hình thức.

Một gate có thể **block theo việc thiếu test cho nhánh nghiệp vụ bắt buộc** trong khi coverage tổng vẫn là warning. Điều này thường gắn với rủi ro trực tiếp hơn.

## 16. Ví dụ Java 17: quyết định gate hiệu năng với dữ liệu đo đủ mẫu

Một gate không nên chỉ so p95 với một con số. Nó cần biết **đo đúng endpoint/workload**, có đủ mẫu và guardrail liên quan.

Ví dụ dưới đây mô hình hóa một phần nhỏ của quyết định:

- p95 phải không vượt **300 ms** trong workload được chỉ định.
- Cần ít nhất **1.000 mẫu** trước khi đưa ra kết luận.
- Nếu thiếu mẫu, kết quả là **INSUFFICIENT_DATA**, không tự coi là PASS.
- Ví dụ không thay thế đánh giá p99, error rate và saturation ở pipeline đầy đủ.

~~~java
import java.time.Duration;
import java.util.Objects;

enum GateResult {
    PASS,
    FAIL,
    INSUFFICIENT_DATA
}

record LatencyMeasurement(
        Duration p95,
        long sampleCount) {
    LatencyMeasurement {
        Objects.requireNonNull(p95, "p95");
        if (p95.isNegative() || sampleCount < 0) {
            throw new IllegalArgumentException("invalid measurement");
        }
    }
}

record LatencyGatePolicy(
        Duration maximumP95,
        long minimumSamples) {
    LatencyGatePolicy {
        Objects.requireNonNull(maximumP95, "maximumP95");
        if (maximumP95.isNegative()
                || maximumP95.isZero()
                || minimumSamples <= 0) {
            throw new IllegalArgumentException("invalid gate policy");
        }
    }

    GateResult evaluate(LatencyMeasurement measurement) {
        Objects.requireNonNull(measurement, "measurement");

        if (measurement.sampleCount() < minimumSamples) {
            return GateResult.INSUFFICIENT_DATA;
        }

        return measurement.p95().compareTo(maximumP95) <= 0
                ? GateResult.PASS
                : GateResult.FAIL;
    }
}
~~~

**Điểm cần chú ý:**
- **Duration** làm rõ đơn vị thời gian, tránh một số nguyên không biết là millisecond hay microsecond.
- Policy chứa cả **ngưỡng** và **mức dữ liệu tối thiểu**.
- Thiếu mẫu là trạng thái riêng để pipeline yêu cầu chạy lại hoặc bổ sung bằng chứng.
- So sánh p95 với ngưỡng không dùng số thực gần đúng.

Trong hệ thống thật, sampleCount phải đếm mẫu **đúng endpoint, đúng cửa sổ, đúng workload và đúng giai đoạn đo**. Một nghìn request rất nhẹ không đại diện cho một nghìn request có payload lớn hoặc hot key.

### Unit test cho chính sách gate

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import org.junit.jupiter.api.Test;

class LatencyGatePolicyTest {
    private final LatencyGatePolicy policy =
            new LatencyGatePolicy(Duration.ofMillis(300), 1_000);

    @Test
    void passesWhenP95IsAtThresholdAndSampleIsSufficient() {
        var measurement =
                new LatencyMeasurement(Duration.ofMillis(300), 1_000);

        assertEquals(GateResult.PASS, policy.evaluate(measurement));
    }

    @Test
    void failsWhenP95ExceedsThreshold() {
        var measurement =
                new LatencyMeasurement(Duration.ofMillis(301), 2_000);

        assertEquals(GateResult.FAIL, policy.evaluate(measurement));
    }

    @Test
    void doesNotPassWhenSampleIsInsufficient() {
        var measurement =
                new LatencyMeasurement(Duration.ofMillis(100), 999);

        assertEquals(
                GateResult.INSUFFICIENT_DATA,
                policy.evaluate(measurement));
    }

    @Test
    void passesWhenP95IsBelowThreshold() {
        var measurement =
                new LatencyMeasurement(Duration.ofMillis(250), 1_500);

        assertEquals(GateResult.PASS, policy.evaluate(measurement));
    }
}
~~~

Các test bảo vệ logic so sánh và điều kiện mẫu của ví dụ. Chúng **không chứng minh hệ thống load test thu thập p95 chính xác**, không xác nhận workload đại diện và không kiểm tra p99/error rate. Những phần đó cần integration với công cụ đo và pipeline thực.

**Đừng nhầm test cho code quyết định gate với bằng chứng gate đang đo hệ thống đúng.** Cả hai đều cần thiết nếu tự xây một cơ chế gate.

## 17. Ngoại lệ: có thể có, nhưng phải kiểm soát

Một cổng cứng đôi khi gặp trường hợp đặc biệt:
- Scanner báo false positive đã được xác minh.
- Dependency chưa có bản vá tương thích.
- Một module legacy cần thời gian để đạt ngưỡng mới.
- Một test tích hợp phụ thuộc môi trường ngoài đang gián đoạn.
- Một thay đổi khẩn cấp cần đi theo quy trình break-glass.

Không nên cấm mọi ngoại lệ; cũng không nên có nút **bypass** không lưu dấu vết.

### Một ngoại lệ có trách nhiệm cần gì?

1. **Phạm vi chính xác:** rule nào, artifact nào, môi trường nào.
2. **Lý do:** vì sao không thể đáp ứng ngay.
3. **Bằng chứng:** false positive, phân tích rủi ro hoặc sự cố môi trường.
4. **Người có thẩm quyền chấp nhận:** không để tác giả tự miễn trừ rủi ro vượt quyền.
5. **Biện pháp bù trừ:** test bổ sung, giới hạn rollout, monitoring, feature flag, kiểm tra thủ công.
6. **Thời hạn hết hiệu lực:** ngoại lệ tự hết hạn hoặc phải được xem xét lại.
7. **Trigger thu hồi:** điều kiện khiến không được tiếp tục bypass.
8. **Ticket/ADR liên quan:** để truy nguyên và lên kế hoạch xử lý.

### Ngoại lệ không nên biến thành baseline vĩnh viễn

Nếu cùng một rule bị bypass ở mọi release, đó có thể là dấu hiệu:
- Rule không phù hợp hoặc cấu hình sai.
- Công cụ có quá nhiều false positive.
- Ngưỡng không dựa trên rủi ro.
- Nhóm thiếu năng lực xử lý cảnh báo.
- Một nợ kỹ thuật đang bị che giấu.

Cần xem lại chính sách gate, không chỉ gia hạn ngoại lệ liên tục.

### Break-glass cho thay đổi khẩn cấp

Quy trình khẩn cấp có thể cho phép một số bước được thực hiện sau, nhưng cần:
- Người phê duyệt theo thẩm quyền.
- Ghi nhận lý do và phạm vi.
- Giới hạn blast radius.
- Theo dõi sau triển khai.
- Hạn chót hoàn tất kiểm tra bị bỏ qua.
- Review hậu sự kiện.

**Khẩn cấp không có nghĩa bỏ mọi kiểm soát**; nó thay đổi thứ tự và cơ chế phê duyệt để phản ứng nhanh mà vẫn truy nguyên được.

## 18. False positive, false negative và độ tin cậy của gate

Một quality gate có giá trị khi kết quả của nó đủ đáng tin.

### False positive

Gate báo FAIL nhưng thay đổi thực tế không vi phạm điều kiện cần bảo vệ.

Ví dụ:
- Scanner nhận diện một dependency không nằm trong runtime path như một rủi ro khai thác trực tiếp.
- Test thất bại do môi trường tạm thời, không do thay đổi.
- Metric hiệu năng có quá ít mẫu.
- Analyzer không hiểu framework hoặc code generated.

Hậu quả: pipeline bị chặn không cần thiết, người phát triển mất thời gian và có thể hình thành thói quen bypass.

### False negative

Gate PASS nhưng rủi ro thực tế vẫn tồn tại.

Ví dụ:
- Coverage cao nhưng test không assert kết quả quan trọng.
- Security scan không mô hình hóa đường khai thác qua cấu hình runtime.
- Unit test dùng mock nên bỏ sót lỗi transaction/database.
- Performance test dùng dữ liệu đều, bỏ qua hot tenant.
- Contract test chỉ kiểm tra schema nhưng bỏ sót ngữ nghĩa của trường.

Hậu quả: nhóm có cảm giác an toàn giả.

### Cách cải thiện độ tin cậy

- Định kỳ đo false positive và false negative qua review kết quả.
- Cập nhật công cụ, ruleset và model dependency.
- Kiểm tra test flakiness và độ ổn định môi trường.
- Đảm bảo dữ liệu thử đại diện cho tải và phân bố thật.
- Dùng nhiều lớp kiểm tra cho rủi ro có hậu quả cao.
- Không gộp tất cả loại lỗi vào một trạng thái PASS/FAIL không giải thích.
- Lưu lý do gate thất bại và đường xử lý cụ thể.

Một gate báo **INSUFFICIENT_DATA** khác với **FAIL**. Một test thất bại do assertion khác với test không thể khởi tạo vì database test environment ngừng hoạt động. Phân loại chính xác giúp nhóm hành động đúng.

## 19. Tránh gaming the metric

Khi một chỉ số trở thành mục tiêu bắt buộc, nhóm có thể vô tình hoặc cố ý tối ưu nó thay vì chất lượng thật.

| Ngưỡng bị theo đuổi | Hành vi có thể xuất hiện | Guardrail cần thêm |
| --- | --- | --- |
| Coverage tối thiểu | Test không assertion, loại trừ file khó test | Review chất lượng test, nhánh nghiệp vụ và mutation khi phù hợp |
| Không có cảnh báo mới | Suppress hàng loạt, tắt rule | Theo dõi suppression, owner và expiry |
| p95 dưới ngưỡng | Chỉ đo request nhẹ hoặc loại timeout khỏi mẫu | Workload đại diện, error rate, p99 và sample completeness |
| Build dưới 5 phút | Bỏ test hoặc giảm kiểm tra | Phân tầng pipeline, kiểm tra bắt buộc vẫn chạy trước release |
| Complexity thấp | Chuyển nhánh sang nhiều lớp hoặc cấu hình khó hiểu | Review độ phức tạp toàn luồng và khả năng truy vết |
| Không có dependency CVE | Nâng version bất chấp tương thích hoặc bỏ dependency scan | Đánh giá exploitability, regression và version support |
| Không tăng số dòng lặp | Gộp hai chính sách khác nhau vào abstraction chung | Review cùng lý do thay đổi và ranh giới sở hữu |

Một chỉ số chỉ nên làm gate khi nhóm có thể giải thích **hành vi nào nó khuyến khích** và **cách nó có thể bị tối ưu sai**. Hãy thêm guardrail cho những cách làm có thể khiến metric đẹp nhưng hệ thống tệ hơn.

## 20. Đánh giá ngưỡng theo thời gian

Ngưỡng được chọn hôm nay có thể không còn phù hợp sau:
- Lưu lượng tăng gấp nhiều lần.
- Sản phẩm mở thêm khu vực hoặc loại khách.
- Thay database hoặc nền tảng.
- Thay đổi SLO.
- Công cụ phân tích được nâng cấp.
- Một loại sự cố mới xuất hiện.
- Module legacy được refactor và baseline cũ không còn ý nghĩa.
- Một API trở thành public hoặc xử lý dữ liệu nhạy cảm hơn.

### Lịch xem xét và sự kiện kích hoạt

Có thể xem lại:
- Theo chu kỳ, ví dụ mỗi quý.
- Sau sự cố liên quan đến loại rủi ro gate đang bảo vệ.
- Khi SLO hoặc hợp đồng khách hàng đổi.
- Khi thay major version của scanner/test framework.
- Khi tỷ lệ bypass hoặc false positive vượt mức nhóm chấp nhận.
- Trước một đợt tăng tải hoặc rollout lớn.

Không cần chờ lịch định kỳ nếu đã có bằng chứng ngưỡng sai. Ngược lại, không nên thay đổi threshold mỗi lần một build đơn lẻ có số đo bất thường.

### Ai sở hữu ngưỡng?

Một chính sách gate cần:
- **Owner kỹ thuật:** duy trì rule và cấu hình.
- **Owner rủi ro/nghiệp vụ:** xác nhận hậu quả và mức chấp nhận.
- **Người vận hành:** xác nhận metric, cảnh báo và hành động khả thi.
- **Nhóm phát triển:** cung cấp bằng chứng và phản hồi false positive/negative.

Với các điều kiện bảo mật hoặc tuân thủ, thẩm quyền chấp nhận ngoại lệ phải theo quy định tổ chức. Không nên mặc định người sửa code có thể tự phê duyệt mọi rủi ro.

## 21. Case study: đặt gate cho dịch vụ đặt hàng

Một dịch vụ đặt hàng có ba luồng:
- **Tra cứu sản phẩm:** nhiều request, chủ yếu đọc.
- **Xác nhận đơn:** ít hơn nhưng ảnh hưởng tiền và tồn kho.
- **Xuất báo cáo:** dữ liệu lớn, có thể chạy nền.

Nhóm ban đầu đề xuất một quality gate chung:
- Coverage ít nhất 85%.
- p95 mọi endpoint dưới 200 ms.
- Không có cảnh báo static analysis.
- Không có dependency warning.

### Vì sao gate ban đầu chưa hợp lý?

**Coverage 85% cho mọi module:** Không xét mã mới hay legacy, cũng không nói test có bảo vệ tính tiền, quyền và trường hợp biên hay không.

**p95 dưới 200 ms cho mọi endpoint:** Báo cáo lớn có thể có hợp đồng bất đồng bộ; một ngưỡng chung không phản ánh trải nghiệm hoặc cách sử dụng.

**Không có cảnh báo static analysis:** Một số warning có thể là style hoặc false positive, trong khi một lỗi correctness cụ thể cần ưu tiên hơn nhiều.

**Không có dependency warning:** Có thể chặn vì một dependency test-only ít rủi ro hoặc bỏ sót một dependency runtime có đường khai thác thực tế.

### Thiết kế lại theo bối cảnh

| Phạm vi | Gate có thể phù hợp | Lý do |
| --- | --- | --- |
| Mọi PR | Build và test bắt buộc; format ổn định; không thêm lỗi correctness nghiêm trọng | Điều kiện cơ bản, dễ tái hiện |
| Tra cứu sản phẩm | Contract test; p95/p99 theo SLO đọc; workload có hot SKU | Bảo vệ trải nghiệm và phân bố tải |
| Xác nhận đơn | Test tính tiền/làm tròn, tồn kho đồng thời, idempotency và quyền; migration/transaction test | Hậu quả lỗi cao |
| Xuất báo cáo | Giới hạn dữ liệu, tính đầy đủ, thời gian job, retry và khả năng tiếp tục | Luồng có workload lớn và cách phản hồi khác |
| Dependency | Scan theo runtime reachability, severity, exploitability và owner | Ưu tiên rủi ro thật |
| Legacy | Baseline, chặn lỗi mới và ratchet theo vùng được sửa | Cải thiện dần mà không miễn trừ nợ vĩnh viễn |

### Quyết định ngưỡng cụ thể

Nhóm thu thập:
- SLO của từng endpoint.
- Phân bố kích thước request và dữ liệu.
- Lịch sử lỗi thanh toán và tồn kho.
- Baseline test/coverage theo module.
- Danh sách dependency runtime và test-only.

Sau đó nhóm mới chọn con số và hành động tương ứng. **Không có cơ sở để tự điền 85%, 200 ms hoặc zero warning** chỉ vì các con số ấy dễ nhớ.

### Bằng chứng khi review gate mới

- Mỗi rule có owner và lý do.
- Các con số được liên hệ với SLO hoặc baseline.
- Luồng xác nhận đơn có hard gate cho test tính đúng đắn và quyền.
- Performance gate chỉ chạy khi thay đổi ảnh hưởng hot path hoặc theo lịch đã thống nhất.
- Ngoại lệ có expiry và người phê duyệt.
- Gate báo rõ FAIL, WARN hoặc INSUFFICIENT_DATA.
- Có lịch xem lại false positive/negative và threshold.

Kết quả là pipeline có thể ít quy tắc hơn nhưng **mỗi quy tắc bảo vệ một rủi ro có ý nghĩa**.

## 22. Mẫu ghi quyết định cho một ngưỡng

Một quality gate nên có tài liệu ngắn đủ để người khác hiểu và đánh giá lại.

~~~text
GATE ID:
Tên:
Phạm vi áp dụng:
Rủi ro/mục tiêu cần bảo vệ:
Rule và metric:
Nguồn dữ liệu/công cụ:
Baseline:
Ngưỡng và cách tính:
Cửa sổ đo / số mẫu:
Loại gate: HARD / SOFT / INFO
Hành động khi vượt ngưỡng:
Owner kỹ thuật:
Owner rủi ro/nghiệp vụ:
Ngoại lệ được phép:
Biện pháp bù trừ:
Ngày xem xét lại:
Trigger điều chỉnh:
Bằng chứng false positive/negative:
~~~

Ví dụ rút gọn:

~~~text
GATE ID: ORDER-CONFIRM-LATENCY
Phạm vi: API xác nhận đơn ở staging và canary
Mục tiêu: Bảo vệ SLO p95 của luồng xác nhận
Metric: p95 theo endpoint và workload đại diện
Nguồn: Load test report và telemetry cùng phiên bản
Ngưỡng: Theo SLO đã phê duyệt cho endpoint
Guardrail: p99, error rate, DB wait, connection saturation
Gate: HARD khi đủ mẫu và vi phạm SLO; WARN nếu thiếu mẫu
Hành động: Dừng rollout, điều tra phân bố request và phụ thuộc
Owner: Nhóm Orders; SRE phối hợp metric
Xem lại: Khi SLO, workload hoặc dependency thay đổi
~~~

Không điền ngưỡng bằng con số không có nguồn. Nếu chính sách chưa được phê duyệt, ghi **cần xác định** và giao việc thu thập bằng chứng.

## 23. Quy trình xây dựng hoặc điều chỉnh quality gate

1. **Xác định rủi ro:** mô tả hậu quả cần ngăn, phạm vi và người bị ảnh hưởng.
2. **Chọn tín hiệu:** tìm metric hoặc rule có liên hệ trực tiếp với rủi ro.
3. **Thu baseline:** đo bằng công cụ và cấu hình được ghi nhận.
4. **Chọn loại gate:** hard, soft hay informational theo hậu quả và độ tin cậy.
5. **Đặt ngưỡng tạm thời:** dùng SLO, hợp đồng, giới hạn năng lực hoặc baseline có lý do.
6. **Chạy thử ở chế độ quan sát:** nếu phù hợp, đánh giá false positive/negative trước khi chặn.
7. **Xác định hành động:** ai xử lý, trong thời gian nào, có rollback hoặc exception không.
8. **Tích hợp pipeline:** giữ feedback nhanh ở PR và các kiểm tra nặng ở giai đoạn phù hợp.
9. **Theo dõi kết quả:** số lần fail, bypass, cảnh báo đúng/sai và tác động tới thời gian giao hàng.
10. **Xem lại và điều chỉnh:** nâng, hạ, chuyển hard/soft hoặc bỏ gate khi bằng chứng thay đổi.

Không phải gate nào cũng cần chạy thử ở chế độ warning. Với điều kiện bắt buộc về bảo mật hoặc tính đúng đắn, có thể cần hard gate ngay khi rule đã được xác minh. Nhưng với metric mới và chưa ổn định, giai đoạn quan sát giúp tránh chặn sai.

## 24. Bài tập tự luyện

### Bài tập 1 — Chọn ngưỡng cho hai loại dịch vụ

Một hệ thống có:
- API tra cứu danh mục sản phẩm.
- API chuyển tiền giữa hai tài khoản.

Hãy đề xuất những gate khác nhau cho hai API về test, quyền, tính đồng thời, latency, audit và rollback. Giải thích vì sao không nên dùng cùng một ngưỡng p95 hoặc cùng một yêu cầu coverage cho mọi trường hợp.

*Gợi ý:* Bắt đầu từ hậu quả nếu sai và hợp đồng người dùng. Chọn SLO theo trải nghiệm thật; bảo vệ số dư và quyền bằng test/invariant riêng.

### Bài tập 2 — Đánh giá gate coverage

Một nhóm yêu cầu toàn repository có coverage tối thiểu 90%. Sau khi áp dụng, lập trình viên loại trừ nhiều package khó test và thêm test chỉ gọi getter để đạt tỷ lệ.

Hãy chỉ ra:
- Gate đang đo điều gì?
- Nó khuyến khích hành vi sai nào?
- Nên dùng baseline/ratchet ra sao?
- Những test nào cần được yêu cầu trực tiếp thay vì dựa vào tỷ lệ?

*Gợi ý:* Xem mã mới, nhánh nghiệp vụ quan trọng, assertion, contract và test tích hợp.

### Bài tập 3 — Hard hay soft?

Phân loại các điều kiện sau thành hard, soft hoặc informational trong một dự án cụ thể, và giải thích:
- Build thất bại.
- Một warning style mới.
- Lỗ hổng nghiêm trọng có thể khai thác trên API public.
- Coverage giảm 1% ở package legacy ít thay đổi.
- p99 chưa đủ mẫu.
- Migration không có kế hoạch bảo vệ dữ liệu.
- Thời gian build tăng 10% qua một lần chạy.

*Gợi ý:* Không có đáp án duy nhất nếu chưa biết bối cảnh. Cần nêu mức rủi ro, độ tin cậy của tín hiệu và hành động khi fail.

### Bài tập 4 — Thiết kế ngưỡng hiệu năng

Một endpoint có SLO p95 250 ms. Load test hiện đo 200 request trong 20 giây, chỉ dùng một tenant và cache luôn nóng. Nhóm muốn đặt hard gate p95 dưới 250 ms.

Hãy nêu những bằng chứng còn thiếu trước khi biến thành hard gate. Thiết kế lại workload và guardrail để tránh kết luận sai.

*Gợi ý:* Xem sample count, phân bố tenant/key, cache miss, burst, p99, error rate và phụ thuộc.

### Bài tập 5 — Ngoại lệ bảo mật có thời hạn

Scanner báo một dependency mức cao. Nhóm xác minh dependency chỉ nằm trong test tooling và chưa có đường khai thác trong runtime, nhưng chưa thể nâng version vì plugin tương thích chưa sẵn sàng.

Hãy viết một exception record gồm phạm vi, bằng chứng, owner, biện pháp bù trừ, expiry và trigger thu hồi. Nêu ai cần phê duyệt theo chính sách tổ chức.

*Gợi ý:* Không chỉ ghi “false positive”; lưu bằng chứng reachability và điều kiện đánh giá lại.

### Bài tập 6 — Baseline cho legacy

Repository có 1.200 cảnh báo static analysis. Hãy đề xuất cách:
- Chụp baseline có version và phạm vi.
- Chọn nhóm lỗi mới phải chặn ngay.
- Ngăn tăng nợ ở mã mới.
- Xử lý cảnh báo cũ theo mức rủi ro.
- Tránh việc baseline trở thành danh sách miễn trừ vĩnh viễn.

### Bài tập 7 — Ngưỡng bị gaming

Sau khi áp dụng gate “không tăng số cảnh báo”, nhóm bắt đầu suppress warning ở những nơi khó sửa. Số cảnh báo vẫn bằng baseline nhưng chất lượng giảm.

Hãy đề xuất metric hoặc review nào có thể phát hiện xu hướng này, cách kiểm soát suppression và khi nào cần thay đổi chính sách gate.

### Bài tập 8 — Viết quality gate decision record

Chọn một rủi ro thực tế trong dự án học tập, chẳng hạn migration database, API compatibility hoặc N+1 query. Viết một quyết định gồm **mục tiêu, metric, baseline, ngưỡng, loại gate, hành động khi fail, owner, ngoại lệ và ngày xem lại**. Nếu chưa có dữ liệu, ghi rõ cần đo gì trước khi chốt con số.

## 25. Tự kiểm tra kiến thức

**Câu 1.** Một ngưỡng được dùng phổ biến trong nhiều dự án có mặc nhiên phù hợp với dự án hiện tại?

*Trả lời:* Không. Cần xét rủi ro, loại workload, SLO, baseline, mức trưởng thành và khả năng kiểm tra của hệ thống.

**Câu 2.** Coverage 90% có chứng minh logic nghiệp vụ đúng?

*Trả lời:* Không. Coverage cho biết phần mã được thực thi theo cách đo; test còn cần assertion và trường hợp biên có ý nghĩa.

**Câu 3.** Vì sao một cảnh báo static analysis không phải lúc nào cũng nên chặn merge?

*Trả lời:* Vì mức nghiêm trọng và độ tin cậy khác nhau; false positive, cảnh báo style và lỗi correctness có hậu quả khác nhau. Cần phân loại và quy định hành động.

**Câu 4.** Baseline có nghĩa là chấp nhận mọi cảnh báo cũ?

*Trả lời:* Không. Baseline giúp phân biệt nợ cũ với lỗi mới; rủi ro nghiêm trọng vẫn cần được xử lý theo tác động thực tế.

**Câu 5.** Khi nào p95 không đủ để làm hard gate?

*Trả lời:* Khi workload hoặc lượng mẫu không đại diện, cách đo không ổn định, hoặc thiếu guardrail như p99, error rate và saturation.

**Câu 6.** Một exception record cần những gì?

*Trả lời:* Phạm vi, lý do, bằng chứng, owner/phê duyệt, biện pháp bù trừ, thời hạn, trigger thu hồi và công việc xử lý.

**Câu 7.** Vì sao không nên dùng một gate chung cho mọi loại thay đổi?

*Trả lời:* Vì blast radius và rủi ro khác nhau. Thay đổi văn bản, logic tính tiền, quyền truy cập và migration database cần bằng chứng khác nhau.

**Câu 8.** Gate PASS có nghĩa hệ thống chắc chắn không còn lỗi?

*Trả lời:* Không. Nó chỉ xác nhận những điều kiện đã được kiểm tra trong phạm vi và môi trường cụ thể. Cần biết rõ phần chưa được bao phủ.

**Câu 9.** Khi nào nên xem lại ngưỡng?

*Trả lời:* Khi SLO, workload, dữ liệu, công cụ, kiến trúc, sự cố hoặc nghĩa vụ sản phẩm thay đổi; ngoài ra nên có lịch review định kỳ.

**Câu 10.** Mục đích cuối cùng của quality gate là gì?

*Trả lời:* Giúp quyết định thay đổi/phát hành dựa trên bằng chứng và rủi ro, bảo vệ chất lượng mà không tạo rào cản tùy tiện hoặc khuyến khích tối ưu sai chỉ số.

## Ghi nhớ

**Đặt ngưỡng có lý do và xem xét theo bối cảnh** nghĩa là bắt đầu từ rủi ro cần bảo vệ, chọn tín hiệu có liên hệ với rủi ro, thu baseline và đặt điều kiện có thể hành động. Hard gate phù hợp với yêu cầu bắt buộc, rõ và đáng tin; soft gate hoặc cảnh báo phù hợp khi cần đánh giá thêm hoặc theo dõi xu hướng. Ngưỡng cần thay đổi theo mức quan trọng của luồng, loại thay đổi, dữ liệu, tải, SLO, mã legacy và khả năng phục hồi. Ngoại lệ phải có owner, bằng chứng, biện pháp bù trừ và thời hạn; baseline phải là điểm xuất phát để cải thiện, không phải miễn trừ vĩnh viễn. Một cổng chất lượng tốt **không chạy theo con số đẹp**: nó giúp nhóm phát hiện rủi ro thật, ra quyết định nhất quán và duy trì phần mềm **đáng tin cậy, dễ hiểu và dễ thay đổi**.
