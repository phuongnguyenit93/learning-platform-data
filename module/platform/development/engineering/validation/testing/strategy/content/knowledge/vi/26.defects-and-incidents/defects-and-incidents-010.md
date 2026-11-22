# Quản lý lỗi tồn đọng và rủi ro được chấp nhận

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, phát hiện lỗi không phải là điểm kết thúc của hoạt động kiểm thử. Nhóm cần đánh giá mức độ ảnh hưởng, quyết định cách xử lý, giao trách nhiệm, theo dõi đến khi đóng và xác định điều kiện phát hành khi vẫn còn vấn đề chưa khắc phục. Một sản phẩm có thể còn lỗi đã biết tại thời điểm phát hành; điều quan trọng là tổ chức hiểu rõ tác động, không che giấu bằng chứng và chỉ chấp nhận rủi ro thông qua đúng thẩm quyền.

**Quản lý lỗi tồn đọng và rủi ro được chấp nhận** là quá trình duy trì danh sách lỗi có kiểm soát, ưu tiên xử lý dựa trên tác động và khả năng xảy ra, theo dõi tuổi lỗi và cam kết khắc phục, đồng thời ghi nhận minh bạch các rủi ro còn lại mà tổ chức quyết định tạm thời chấp nhận. Quá trình này kết nối kết quả test với quyết định sản phẩm, phát hành và vận hành.

Lỗi tồn đọng (defect backlog) không đơn giản là danh sách ticket chưa đóng. Nó là tập hợp các vấn đề đã biết cần được đánh giá và quản lý theo trạng thái, mức độ nghiêm trọng, ưu tiên, phạm vi ảnh hưởng, người chịu trách nhiệm và kế hoạch xử lý. Rủi ro được chấp nhận (accepted risk) cũng không có nghĩa là lỗi đã được sửa hoặc không còn nguy hiểm. Đó là quyết định có chủ đích của người có thẩm quyền, dựa trên thông tin và biện pháp kiểm soát đã được ghi nhận.

## 1. Phân biệt defect, issue, incident và risk

Các nhóm thường dùng những thuật ngữ gần nhau. Cần thống nhất ý nghĩa để không nhầm một lỗi được phát hiện trong test với một sự cố đang ảnh hưởng người dùng hoặc một rủi ro chưa xảy ra.

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| Defect/Bug | Sai lệch trong sản phẩm so với yêu cầu, hợp đồng, thiết kế hoặc hành vi được xác nhận | Tổng tiền đơn hàng bị tính thiếu phí vận chuyển |
| Issue | Vấn đề cần được theo dõi; có thể là defect, câu hỏi, công việc kỹ thuật hoặc phụ thuộc | Yêu cầu chưa rõ về cách làm tròn tiền |
| Incident | Sự kiện làm gián đoạn hoặc suy giảm dịch vụ, gây ảnh hưởng thực tế hoặc cần phản ứng vận hành | Người dùng không thể thanh toán sau khi phát hành |
| Risk | Tình huống không chắc chắn có thể xảy ra và gây ảnh hưởng đến mục tiêu | Retry thanh toán có thể tạo giao dịch trùng trong điều kiện timeout |
| Known error | Vấn đề đã được phân tích, nguyên nhân hoặc workaround đã biết nhưng chưa được loại bỏ hoàn toàn | Lỗi cache có cách giảm thiểu bằng cách làm mới cache thủ công |
| Accepted risk | Rủi ro còn tồn tại đã được người có thẩm quyền quyết định chấp nhận trong phạm vi và thời hạn xác định | Cho phép rollout giới hạn trong khi chờ hoàn thiện dashboard phụ trợ |

Một defect có thể dẫn đến incident nếu xuất hiện trong môi trường đang dùng. Một incident có thể được giải quyết bằng workaround nhưng defect gốc vẫn còn trong backlog. Một risk có thể chưa có defect tái hiện được, nhưng vẫn cần được theo dõi nếu hậu quả tiềm tàng đáng kể.

Không nên dùng trạng thái “accepted” để thay thế “fixed”, “verified” hoặc “closed”. Mỗi trạng thái phải phản ánh đúng điều đã xảy ra.

## 2. Mục tiêu quản lý lỗi tồn đọng

Quản lý backlog có hiệu quả giúp nhóm và các bên liên quan biết vấn đề nào cần xử lý trước, vấn đề nào đang chờ, ai chịu trách nhiệm và rủi ro nào có thể ảnh hưởng đến quyết định phát hành.

Các mục tiêu chính gồm:

- **Minh bạch:** mọi lỗi có ảnh hưởng đáng kể được ghi nhận, phân loại và có thể truy vết.
- **Ưu tiên đúng:** tập trung vào tác động, khả năng xảy ra, phạm vi người dùng và nghĩa vụ bắt buộc.
- **Trách nhiệm rõ:** mỗi lỗi có owner, hành động tiếp theo và thời điểm xem xét.
- **Không để lỗi già đi vô chủ:** theo dõi tuổi lỗi, trạng thái chờ và lý do trì hoãn.
- **Bảo vệ quyết định phát hành:** người quyết định biết lỗi còn mở, giới hạn kiểm thử và rủi ro tồn dư.
- **Ngăn tái diễn:** lỗi đã sửa được xác minh và có test hồi quy phù hợp.
- **Học hỏi liên tục:** xu hướng lỗi được dùng để cải thiện yêu cầu, thiết kế, quy trình và chiến lược test.

Backlog lớn không tự động có nghĩa chất lượng thấp; số lượng có thể phụ thuộc quy mô sản phẩm, cách ghi nhận và độ chi tiết ticket. Ngược lại, backlog ít không chứng minh sản phẩm tốt nếu nhóm không ghi nhận vấn đề hoặc đóng ticket không có bằng chứng.

## 3. Thiết lập một defect record đầy đủ

Một lỗi cần có đủ thông tin để người khác hiểu, đánh giá, tái hiện và quyết định cách xử lý. Ticket thiếu bối cảnh dễ bị chuyển qua lại hoặc đóng sai.

### Thông tin nhận diện

- Defect ID duy nhất.
- Tiêu đề mô tả triệu chứng và khu vực bị ảnh hưởng.
- Sản phẩm, service, module hoặc chức năng liên quan.
- Ngày phát hiện, người phát hiện và nguồn phát hiện (unit, integration, UAT, production monitoring...).
- Phiên bản/build, commit hoặc release liên quan.
- Môi trường, thiết bị, browser và cấu hình cần thiết.

### Bằng chứng và khả năng tái hiện

- Điều kiện ban đầu và dữ liệu liên quan.
- Các bước tái hiện có thứ tự.
- Kết quả thực tế.
- Kết quả mong đợi hoặc tham chiếu yêu cầu/hợp đồng.
- Tần suất tái hiện và điều kiện ảnh hưởng.
- Log, trace, screenshot, video, request/response hoặc mã giao dịch đã che dữ liệu nhạy cảm.
- Workaround tạm thời nếu có.

### Đánh giá và quản lý

- Severity và priority theo định nghĩa của tổ chức.
- Phạm vi người dùng, dữ liệu và quy trình bị ảnh hưởng.
- Tác động nghiệp vụ, bảo mật, tuân thủ, vận hành hoặc tài chính.
- Owner, team phụ trách và người cần tham vấn.
- Trạng thái, blocker, dependency và hành động tiếp theo.
- Target fix version hoặc thời điểm review dự kiến.
- Liên kết đến incident, requirement, test case, release và risk record nếu có.

Không phải mọi trường đều cần điền ngay khi phát hiện. Tuy nhiên, lỗi nghiêm trọng cần được ghi nhận nhanh với thông tin tối thiểu đủ để bảo vệ người dùng và điều phối phản ứng; các chi tiết còn thiếu phải có người chịu trách nhiệm bổ sung.

## 4. Phân loại severity và priority

Severity (mức độ nghiêm trọng) và priority (mức độ ưu tiên xử lý) trả lời hai câu hỏi khác nhau.

- **Severity:** nếu lỗi xảy ra, mức độ ảnh hưởng hoặc hậu quả nghiêm trọng đến đâu?
- **Priority:** tổ chức cần xử lý lỗi sớm đến mức nào so với các công việc và rủi ro khác?

Một lỗi có severity cao thường cần ưu tiên cao, nhưng không phải lúc nào hai giá trị cũng giống nhau. Ví dụ, lỗi làm hỏng một chức năng ít người dùng nhưng có workaround rõ có thể có severity cao ở một phạm vi hẹp và priority được sắp xếp sau một lỗi ảnh hưởng diện rộng. Ngược lại, một lỗi giao diện nhỏ nhưng xuất hiện trên trang thanh toán cho tất cả người dùng có thể có priority cao vì tác động đến chuyển đổi.

### Ví dụ thang severity

| Mức | Diễn giải tham khảo | Ví dụ |
|---|---|---|
| Critical/Blocker | Mất dữ liệu, giao dịch sai nghiêm trọng, vi phạm bảo mật lớn, dịch vụ thiết yếu không hoạt động hoặc không có workaround an toàn | Ghi nhận thanh toán trùng; người dùng xem dữ liệu của người khác |
| High/Major | Chức năng quan trọng không hoạt động hoặc kết quả sai đáng kể; workaround khó hoặc có rủi ro | Không thể hoàn tất đặt hàng cho một nhóm khách hàng lớn |
| Medium | Chức năng phụ hoặc một phần luồng bị ảnh hưởng; có workaround chấp nhận được | Bộ lọc tìm kiếm không giữ lựa chọn sau khi tải lại |
| Low/Minor | Ảnh hưởng nhỏ, không làm sai nghiệp vụ chính | Căn lề hoặc thông báo phụ chưa nhất quán |

Đây là ví dụ, không phải hệ thống phân loại bắt buộc. Tổ chức cần định nghĩa severity theo sản phẩm, loại dữ liệu, mức độ ảnh hưởng và nghĩa vụ chuyên môn.

### Ví dụ thang priority

| Mức | Hướng xử lý tham khảo |
|---|---|
| P0 | Phản ứng ngay; xem xét dừng phát hành hoặc giảm thiểu sự cố đang diễn ra |
| P1 | Xử lý trong chu kỳ hiện tại hoặc trước mốc release đã xác định |
| P2 | Đưa vào kế hoạch gần; review theo sprint/release và rủi ro |
| P3 | Theo dõi backlog; xử lý khi có năng lực hoặc khi điều kiện thay đổi |

Thời hạn cụ thể cần gắn với chính sách SLA/OLA của tổ chức. Không nên hứa một thời gian cố định nếu chưa có quy trình hỗ trợ và nguồn lực tương ứng.

### Căn cứ xác định priority

Ưu tiên nên xem xét:

- Mức độ nghiêm trọng và hậu quả nếu xảy ra.
- Số lượng và loại người dùng bị ảnh hưởng.
- Tần suất xảy ra và khả năng tái hiện.
- Khả năng khai thác hoặc mức phơi nhiễm bảo mật.
- Tác động đến dữ liệu, tiền, an toàn, quyền riêng tư và tuân thủ.
- Có workaround an toàn hay không và chi phí sử dụng workaround.
- Mức độ ảnh hưởng đến mục tiêu release và cam kết khách hàng.
- Phụ thuộc, chi phí sửa và khả năng phát sinh lỗi mới.

Không nên chỉ dùng số người dùng bị ảnh hưởng. Một lỗi hiếm nhưng có thể làm mất dữ liệu hoặc vi phạm pháp lý vẫn có thể cần ưu tiên cao.

## 5. Triage — đánh giá và quyết định hướng xử lý

Defect triage là hoạt động review lỗi để xác nhận thông tin, phân loại, ưu tiên và thống nhất hành động. Triage có thể diễn ra thường xuyên hoặc được kích hoạt khi có lỗi nghiêm trọng, trước release hoặc khi backlog vượt ngưỡng.

### Thành phần tham gia

Tùy phạm vi, triage có thể gồm QA/Test Lead, developer/engineering lead, product owner, business analyst, vận hành/SRE, bảo mật, hỗ trợ khách hàng và đại diện nghiệp vụ. Không cần tất cả tham gia mọi cuộc họp; chọn người có kiến thức và quyền quyết định liên quan.

### Quy trình triage tham khảo

1. **Xác nhận ticket:** kiểm tra trùng lặp, thông tin tối thiểu, phiên bản và bằng chứng.
2. **Phân loại:** defect, question, environment issue, enhancement hay incident follow-up.
3. **Đánh giá tác động:** xác định người dùng, dữ liệu, quy trình, phạm vi và hậu quả.
4. **Gán severity:** dùng tiêu chí đã thống nhất, có giải thích khi trường hợp đặc biệt.
5. **Xác định priority:** cân nhắc rủi ro, workaround, release và nguồn lực.
6. **Giao owner:** chỉ định người hoặc nhóm chịu trách nhiệm và hành động tiếp theo.
7. **Chọn disposition:** sửa ngay, lên kế hoạch, chuyển nhóm, cần thêm thông tin, duplicate, won't fix hoặc đề xuất chấp nhận rủi ro.
8. **Đặt mốc review:** target version, due date hoặc ngày đánh giá lại.

### Kết quả triage có thể có

- Confirmed defect — xác nhận là lỗi sản phẩm.
- Needs information — cần thêm bước tái hiện, log hoặc làm rõ yêu cầu.
- Duplicate — liên kết đến ticket gốc và giữ thông tin ảnh hưởng riêng nếu cần.
- Not a defect — hành vi đúng theo yêu cầu đã xác nhận; cần giải thích căn cứ.
- Change request — đề xuất thay đổi ngoài phạm vi hiện tại.
- Environment/test issue — lỗi do môi trường hoặc test, cần giao đúng nhóm.
- Accepted risk candidate — đề xuất đánh giá rủi ro tồn dư, chưa phải quyết định chấp nhận.

Không đóng một ticket chỉ vì chưa tái hiện được trong một lần thử. Cần ghi điều kiện đã thử, giới hạn môi trường và lý do chuyển trạng thái.

## 6. Quản lý vòng đời lỗi

Trạng thái cần phản ánh chính xác tiến trình xử lý. Tên trạng thái có thể khác nhau giữa công cụ, nhưng ý nghĩa và điều kiện chuyển trạng thái phải rõ.

| Trạng thái | Ý nghĩa | Điều kiện chuyển tiếp điển hình |
|---|---|---|
| New/Open | Lỗi vừa được ghi nhận | Có đủ thông tin để triage |
| Triaged | Đã phân loại, đánh giá và ưu tiên | Có owner và hướng xử lý |
| Assigned | Đã giao nhóm/người phụ trách | Bắt đầu phân tích hoặc sửa |
| In Progress | Đang điều tra hoặc thực hiện thay đổi | Có bản sửa hoặc kết luận tiếp theo |
| Fixed/Resolved | Đã có bản sửa hoặc thay đổi được cho là xử lý nguyên nhân | Chờ kiểm thử xác minh |
| Ready for Retest | Bản sửa có sẵn trong build/môi trường xác định | QA thực hiện retest |
| Verified | Retest đạt và bằng chứng được lưu | Có thể đóng nếu không còn điều kiện mở |
| Reopened | Lỗi vẫn xảy ra hoặc tái xuất hiện | Quay lại phân tích, giữ lịch sử trước đó |
| Deferred | Được trì hoãn có lý do và mốc review | Đánh giá lại theo thời hạn/điều kiện |
| Accepted Risk | Rủi ro được chấp nhận theo hồ sơ và thẩm quyền | Theo dõi điều kiện, thời hạn và trigger |
| Closed | Quy trình xử lý hoàn tất theo tiêu chí | Có bằng chứng đóng hoặc quyết định hợp lệ |

`Resolved` không đồng nghĩa `Verified`. Developer có thể hoàn tất thay đổi nhưng QA vẫn cần xác nhận. `Deferred` cũng không đồng nghĩa `Accepted Risk`; trì hoãn là quyết định về kế hoạch công việc, còn chấp nhận rủi ro là quyết định về mức rủi ro tồn dư và thẩm quyền.

### Tiêu chí đóng lỗi

Một defect thường chỉ nên đóng khi:

- Nguyên nhân hoặc điều kiện lỗi đã được xử lý theo phạm vi.
- Bản sửa có trong build/version xác định.
- Retest xác nhận lỗi không còn xảy ra trong điều kiện tái hiện.
- Test hồi quy phù hợp đã chạy và đạt.
- Không phát sinh lỗi liên quan mới hoặc tác dụng phụ đáng kể.
- Bằng chứng và liên kết đến change/release được lưu.

Với lỗi không thể tái hiện, duplicate hoặc not a defect, cần ghi căn cứ và liên kết ticket gốc hoặc yêu cầu liên quan. Không dùng trạng thái Closed để làm biến mất vấn đề chưa được giải quyết.

## 7. Theo dõi tuổi lỗi và lỗi tồn đọng

Backlog cần được quản lý theo thời gian, không chỉ theo số lượng hiện tại. Lỗi lâu ngày có thể trở nên khó sửa hơn vì kiến trúc, dữ liệu và người hiểu bối cảnh đã thay đổi; đồng thời rủi ro có thể tăng khi sản phẩm mở rộng.

### Tuổi lỗi (defect age)

Có thể tính tuổi lỗi từ ngày phát hiện đến ngày hiện tại hoặc ngày đóng. Với lỗi đang mở:

`Defect age = Ngày đánh giá - Ngày phát hiện`.

Với lỗi đã đóng:

`Time to close = Ngày đóng - Ngày phát hiện`.

Nên thống nhất cách tính theo ngày lịch hay ngày làm việc, múi giờ và cách xử lý thời gian ticket ở trạng thái chờ bên ngoài. Không nên loại bỏ thời gian chờ khỏi số liệu nếu việc chờ đó vẫn làm rủi ro tồn tại; có thể báo cáo riêng active resolution time và elapsed age.

### Nhóm tuổi lỗi

Có thể chia bucket để nhìn xu hướng, ví dụ:

- 0–7 ngày: mới phát hiện.
- 8–30 ngày: cần theo dõi tiến độ.
- 31–60 ngày: cần review lý do tồn đọng.
- Trên 60 ngày: cần quyết định rõ về sửa, thay thế, chấp nhận hoặc loại bỏ có căn cứ.

Các mốc này chỉ là ví dụ. Lỗi bảo mật hoặc mất dữ liệu có thể cần phản ứng trong vài giờ; lỗi hiển thị nhỏ có thể có chu kỳ dài hơn. Dùng SLA theo mức rủi ro thay vì một hạn chung.

### Phân tích backlog aging

Review định kỳ các câu hỏi:

- Có bao nhiêu lỗi theo severity/priority và tuổi?
- Lỗi nào chưa có owner hoặc hành động tiếp theo?
- Lỗi nào đang chờ bên ngoài và đã chờ bao lâu?
- Có nhóm lỗi lặp lại ở cùng thành phần hoặc nguyên nhân không?
- Có lỗi lâu ngày đang ảnh hưởng release hoặc tạo workaround tốn kém?
- Có ticket nào cần tách, gộp hoặc cập nhật mức độ tác động?

### Tránh chỉ tối ưu số lượng ticket

Đóng nhiều ticket nhỏ không nhất thiết làm giảm rủi ro tổng thể. Nhóm nên theo dõi số lỗi theo mức nghiêm trọng, thời gian tồn tại, mức phơi nhiễm, lỗi tái mở và rủi ro không có workaround. Chất lượng backlog phụ thuộc tính đầy đủ và tính chính xác, không chỉ số ticket.

## 8. Lập kế hoạch xử lý backlog

Backlog cần được đưa vào kế hoạch sản phẩm và kỹ thuật. Nếu lỗi chỉ được xem xét khi có thời gian rảnh, các vấn đề lâu ngày có thể trở thành nợ kỹ thuật và rủi ro vận hành.

### Các chiến lược xử lý

- **Fix now:** sửa ngay khi lỗi nghiêm trọng, đang ảnh hưởng hoặc là điều kiện chặn.
- **Schedule:** đưa vào sprint/release với owner và mục tiêu hoàn tất.
- **Mitigate:** áp dụng biện pháp giảm thiểu tạm thời trong khi chờ sửa triệt để.
- **Defer with review date:** trì hoãn có lý do, thời hạn và điều kiện xem xét lại.
- **Accept risk:** ghi nhận và phê duyệt rủi ro tồn dư đúng thẩm quyền.
- **Won't fix/retire:** quyết định không sửa vì chức năng bị loại bỏ, hành vi được xác nhận là đúng hoặc chi phí sửa không tương xứng; cần có căn cứ và người quyết định.

### Dành năng lực cho lỗi tồn đọng

Nhóm có thể dành một phần năng lực mỗi sprint hoặc release cho defect backlog, nhưng tỷ lệ phải dựa trên lịch sử lỗi, mức độ rủi ro và mục tiêu sản phẩm. Không có một tỷ lệ phần trăm đúng cho mọi nhóm.

Khi lên kế hoạch, cân nhắc:

- Lỗi có thể gây incident hoặc vi phạm nghĩa vụ.
- Lỗi chặn công việc hoặc làm tăng chi phí hỗ trợ.
- Lỗi có workaround tốn kém hoặc dễ gây sai sót.
- Lỗi lâu ngày có nguy cơ trở nên khó sửa.
- Lỗi lặp lại cho thấy nguyên nhân hệ thống.
- Chi phí sửa và khả năng tạo hồi quy mới.

### Kế hoạch khắc phục theo nhóm nguyên nhân

Nếu nhiều defect cùng xuất phát từ một nguyên nhân, ví dụ thiếu idempotency, validation không nhất quán hoặc migration không an toàn, có thể cần một initiative xử lý gốc thay vì đóng từng ticket riêng. Liên kết các lỗi vào epic/problem record để theo dõi hiệu quả thay đổi.

## 9. Phân biệt trì hoãn với chấp nhận rủi ro

Đây là phân biệt quan trọng trong quyết định release.

**Deferred** nghĩa là tổ chức chưa xử lý lỗi ngay và dự kiến xem xét lại theo kế hoạch. Rủi ro vẫn tồn tại và chưa nhất thiết đã được đánh giá/chấp nhận chính thức.

**Accepted risk** nghĩa là người có thẩm quyền đã xem xét rủi ro còn lại, hiểu tác động, quyết định chấp nhận trong một phạm vi cụ thể và xác định biện pháp kiểm soát, thời hạn hoặc điều kiện đánh giá lại.

Ví dụ:

- “Để lỗi này sang sprint sau vì nhóm đang bận” là trì hoãn, chưa phải chấp nhận rủi ro.
- “Cho phép rollout 5% trong 48 giờ, chỉ với nhóm nội bộ, có rollback tự động khi tỷ lệ lỗi vượt ngưỡng; service owner phê duyệt và review sau 24 giờ” là một quyết định chấp nhận có điều kiện nếu quy trình cho phép.

Không nên dùng accepted risk như một cách đổi nhãn để làm sạch backlog. Khi rủi ro được chấp nhận, defect gốc vẫn cần được liên kết và theo dõi nếu chưa sửa.

## 10. Đánh giá và ghi nhận rủi ro tồn dư

Rủi ro tồn dư (residual risk) là phần rủi ro còn lại sau khi đã áp dụng biện pháp kiểm soát hoặc giảm thiểu. Một defect chưa sửa có thể là nguồn rủi ro; workaround, giới hạn rollout hoặc monitoring có thể giảm xác suất hoặc tác động, nhưng không nhất thiết loại bỏ rủi ro.

### Thành phần của risk record

Một hồ sơ rủi ro nên ghi:

- Risk ID và liên kết đến defect/incident/requirement.
- Mô tả tình huống không chắc chắn và điều kiện kích hoạt.
- Tài sản, người dùng, quy trình hoặc mục tiêu bị ảnh hưởng.
- Khả năng xảy ra và mức độ tác động.
- Rủi ro ban đầu (inherent risk) nếu tổ chức sử dụng cách đo này.
- Biện pháp kiểm soát hiện có và hiệu quả của chúng.
- Rủi ro tồn dư sau kiểm soát.
- Workaround, giới hạn sử dụng hoặc kế hoạch giảm thiểu bổ sung.
- Người sở hữu rủi ro (risk owner).
- Người có thẩm quyền chấp nhận (risk acceptance authority).
- Ngày quyết định, phạm vi, thời hạn và điều kiện review.
- Trigger khiến quyết định phải được đánh giá lại hoặc rút lại.

### Đánh giá likelihood và impact

Có thể dùng thang định tính như Low/Medium/High hoặc thang số được tổ chức chuẩn hóa. Cần mô tả tiêu chí để các nhóm không tự gán mức theo cảm tính.

**Likelihood** có thể dựa trên tần suất tái hiện, điều kiện kích hoạt, mức phơi nhiễm, độ phức tạp và dữ liệu lịch sử. **Impact** có thể dựa trên số người dùng, giá trị giao dịch, dữ liệu, downtime, an toàn, bảo mật, pháp lý và uy tín.

Một ma trận risk rating có thể giúp phân nhóm, nhưng không nên để phép nhân số học che khuất nghĩa vụ bắt buộc. Rủi ro pháp lý, an toàn hoặc bảo mật có thể cần quy trình phê duyệt chuyên biệt ngay cả khi điểm tổng hợp không cao.

### Rủi ro ban đầu và rủi ro tồn dư

Ví dụ, lỗi đồng bộ đơn hàng có khả năng gây trạng thái sai ở nhiều cửa hàng. Biện pháp giảm thiểu có thể là tạm thời tắt đồng bộ tự động, đối soát thủ công và giới hạn rollout. Rủi ro sau kiểm soát có thể giảm, nhưng vẫn còn khả năng chậm cập nhật và sai sót thao tác. Hồ sơ cần mô tả cả rủi ro trước và sau kiểm soát, cùng bằng chứng cho hiệu quả của biện pháp.

## 11. Quy trình chấp nhận rủi ro

Chấp nhận rủi ro cần là quyết định có thể truy vết, không phải sự im lặng hoặc đồng thuận miệng trong cuộc họp.

### Bước 1: Mô tả vấn đề và phạm vi

Nêu defect hoặc tình huống, phiên bản, môi trường, nhóm người dùng, điều kiện kích hoạt và phần nào bị ảnh hưởng. Phân biệt điều đã quan sát với giả định.

### Bước 2: Đánh giá tác động và khả năng xảy ra

Xem xét hậu quả về nghiệp vụ, dữ liệu, tiền, bảo mật, quyền riêng tư, tuân thủ, vận hành và khách hàng. Dùng bằng chứng từ test, incident, log, dữ liệu lịch sử và chuyên gia.

### Bước 3: Xác định lựa chọn xử lý

Các lựa chọn có thể gồm sửa trước release, giảm phạm vi, tắt feature, giới hạn người dùng, tăng monitoring, bổ sung thao tác kiểm soát, rollback plan, chuyển sang release sau hoặc chấp nhận rủi ro theo thẩm quyền.

### Bước 4: Đánh giá biện pháp giảm thiểu

Với mỗi biện pháp, xác định cách thực hiện, hiệu quả dự kiến, người phụ trách và bằng chứng xác nhận. Workaround chỉ được xem là kiểm soát khi có thể thực hiện an toàn và có người chịu trách nhiệm.

### Bước 5: Trình đúng người có thẩm quyền

Trình bày rủi ro, lựa chọn, hậu quả, giới hạn và đề xuất. Người có thẩm quyền cần có đủ thông tin và quyền theo chính sách, hợp đồng hoặc quy định. Người phát hiện lỗi hoặc developer không mặc nhiên có quyền chấp nhận rủi ro nghiệp vụ, bảo mật hoặc pháp lý.

### Bước 6: Ghi quyết định

Ghi rõ chấp nhận, từ chối, yêu cầu giảm thiểu thêm hoặc cần đánh giá lại. Nếu chấp nhận, xác định phạm vi, thời hạn, owner, điều kiện, trigger và cách thông báo.

### Bước 7: Theo dõi và xem xét lại

Theo dõi tín hiệu, sự cố, điều kiện vận hành và thời hạn. Khi có thay đổi về phạm vi, tần suất, tác động hoặc biện pháp kiểm soát, đánh giá lại quyết định. Rủi ro được chấp nhận không phải giấy phép vĩnh viễn.

## 12. Ai có quyền chấp nhận rủi ro?

Quyền chấp nhận phụ thuộc loại rủi ro và quy chế của tổ chức. Không có một chức danh duy nhất phù hợp với mọi tình huống.

| Loại rủi ro | Vai trò thường cần tham gia | Lưu ý về thẩm quyền |
|---|---|---|
| Nghiệp vụ/sản phẩm | Product owner, business owner, đại diện khách hàng | Chấp nhận trong phạm vi giá trị và quyền được giao |
| Vận hành/độ tin cậy | Service owner, SRE/Operations, release manager | Cần xem SLO, khả năng hỗ trợ, rollback và năng lực trực |
| Bảo mật | Security owner, CISO delegate hoặc người được ủy quyền | Ngoại lệ bảo mật phải theo chính sách; một số lỗi không được miễn trừ |
| Quyền riêng tư/dữ liệu | Privacy/DPO hoặc vai trò tương đương, legal | Tuân thủ nghĩa vụ pháp lý và chính sách dữ liệu |
| Hợp đồng/tài chính | Contract owner, finance, legal, customer authority | Không thể tự miễn trừ nghĩa vụ hợp đồng bằng quyết định kỹ thuật |
| Phát hành | Release authority hoặc change advisory process | Tổng hợp bằng chứng và quyết định Go/No-Go theo quy trình |

Một rủi ro có thể cần nhiều xác nhận chuyên môn. Ví dụ, Product Owner chấp nhận tác động nghiệp vụ trong phạm vi của họ, nhưng không thể thay Security phê duyệt ngoại lệ bảo mật nếu quy chế yêu cầu Security approval. Cần xác định người quyết định cuối cùng và các phê duyệt bắt buộc trước khi trình release.

## 13. Giới hạn không được tùy tiện chấp nhận

Không phải mọi rủi ro đều có thể được miễn trừ. Một số yêu cầu pháp lý, hợp đồng, an toàn, bảo mật hoặc chính sách nội bộ có thể là điều kiện bắt buộc. Nếu vi phạm, người có thẩm quyền dự án không thể tự biến chúng thành lựa chọn tùy ý.

Ví dụ cần chuyển đúng quy trình chuyên môn:

- Lỗ hổng nghiêm trọng có thể làm lộ dữ liệu hoặc chiếm quyền.
- Xử lý dữ liệu cá nhân trái căn cứ hoặc vượt mục đích được phép.
- Rủi ro gây mất dữ liệu không thể khôi phục trong hệ thống quan trọng.
- Giao dịch tài chính sai hoặc không thể đối soát theo nghĩa vụ.
- Vi phạm yêu cầu an toàn hoặc tiêu chuẩn bắt buộc.
- Điều kiện nghiệm thu hợp đồng chưa đạt nhưng vẫn muốn ký bàn giao.

Nếu chính sách cho phép ngoại lệ, cần có người được chỉ định, quy trình và bằng chứng cụ thể. Nếu không cho phép, phải khắc phục, giới hạn hoặc dừng phát hành. Không dùng một biên bản “chấp nhận rủi ro” chung để vượt qua nghĩa vụ bắt buộc.

## 14. Theo dõi accepted risk trong thời gian phát hành và vận hành

Sau khi chấp nhận, rủi ro cần được quản lý như một cam kết có điều kiện.

### Xác định thời hạn

Quyết định nên có ngày hết hạn hoặc ngày review. Nếu rủi ro cần tồn tại lâu hơn, phải đánh giá lại và tái phê duyệt theo chính sách. Tránh các mục accepted risk không có thời hạn hoặc không có owner.

### Xác định trigger đánh giá lại

Ví dụ:

- Tỷ lệ lỗi vượt ngưỡng.
- Có incident hoặc khiếu nại liên quan.
- Phạm vi rollout tăng hoặc mở cho nhóm người dùng mới.
- Có thay đổi kiến trúc, dữ liệu hoặc nhà cung cấp.
- Workaround không còn hoạt động hoặc không có người thực hiện.
- Phát hiện lỗ hổng mới hoặc thay đổi nghĩa vụ tuân thủ.
- Đến ngày review hoặc hết thời hạn chấp nhận.

### Theo dõi biện pháp giảm thiểu

Mỗi hành động cần có owner, deadline, trạng thái và bằng chứng hoàn tất. Nếu biện pháp là monitoring, phải xác định dashboard, cảnh báo, ngưỡng, người nhận và runbook. Nếu là workaround thủ công, cần có quy trình, tần suất, người thay thế và kiểm soát sai sót.

### Liên kết defect và risk register

Defect backlog theo dõi vấn đề sản phẩm cần sửa; risk register theo dõi rủi ro và quyết định. Một defect có thể liên kết một hoặc nhiều risk record. Khi defect được sửa và verified, risk owner cần xác nhận rủi ro đã giảm hoặc đóng, không tự động xóa risk record mà không kiểm tra.

## 15. Quản lý lỗi trong quyết định release

Trước release, nhóm cần tổng hợp lỗi tồn đọng và rủi ro còn lại thành một bức tranh đủ rõ để người có thẩm quyền quyết định.

### Release readiness review

Thông tin nên gồm:

- Tổng số defect theo severity/priority và trạng thái.
- Các lỗi critical/high còn mở, tuổi lỗi và owner.
- Lỗi mới phát hiện trong release candidate.
- Lỗi đã sửa nhưng chưa retest hoặc chưa chạy regression.
- Test bị skip, flaky hoặc quarantine và rủi ro liên quan.
- Incident gần đây và known errors còn ảnh hưởng.
- Risk record được đề xuất chấp nhận, thời hạn và người phê duyệt.
- Workaround, rollout restriction, monitoring và rollback plan.
- Nghĩa vụ bắt buộc hoặc tiêu chí không được miễn trừ.

### Quy tắc Go/No-Go

Một quy trình có thể quy định:

- No-Go nếu còn defect chặn, tiêu chí bắt buộc chưa đạt hoặc chưa có bằng chứng cho rủi ro nghiêm trọng.
- Go nếu tiêu chí đạt, không còn rủi ro vượt ngưỡng và các phê duyệt cần thiết đã hoàn tất.
- Go có điều kiện nếu chính sách cho phép, rủi ro được chấp nhận đúng thẩm quyền và các điều kiện kiểm soát có thể thực thi.

Không nên quyết định chỉ dựa trên số lượng lỗi. Một lỗi critical có thể quan trọng hơn hàng trăm lỗi hiển thị nhỏ. Ngược lại, một backlog nhiều lỗi nhỏ có thể cho thấy chất lượng trải nghiệm hoặc chi phí hỗ trợ đang xấu đi và cần được xem xét.

### Rollout giới hạn và rollback

Nếu phát hành có điều kiện, có thể giới hạn theo phần trăm lưu lượng, nhóm nội bộ, khu vực hoặc chức năng. Cần xác định:

- Ai được tiếp cận và ai bị giới hạn.
- Metric và cảnh báo dùng để đánh giá.
- Ngưỡng dừng hoặc rollback.
- Người có quyền kích hoạt dừng.
- Cách thông báo người dùng và hỗ trợ.
- Cách bảo vệ dữ liệu khi rollback hoặc tắt feature.
- Thời hạn mở rộng hoặc kết thúc thử nghiệm.

Rollout giới hạn chỉ là biện pháp giảm thiểu khi có thể kiểm soát tác động; nó không làm biến mất defect gốc.

## 16. Tích hợp lỗi production và incident với defect backlog

Incident response tập trung khôi phục dịch vụ và giảm tác động ngay lập tức. Defect management tập trung xử lý nguyên nhân và ngăn tái diễn. Hai luồng cần liên kết nhưng không thay thế nhau.

Sau incident:

1. Ghi nhận incident ID, thời gian, tác động và dịch vụ/phiên bản liên quan.
2. Khôi phục dịch vụ bằng workaround, rollback hoặc biện pháp an toàn.
3. Tạo defect/problem record cho nguyên nhân kỹ thuật hoặc hành vi cần sửa.
4. Liên kết log, trace, deployment, commit và dữ liệu điều tra.
5. Xác định test thiếu hoặc test đã không phát hiện lỗi.
6. Tạo test hồi quy ở tầng phù hợp và xác nhận sau khi sửa.
7. Cập nhật runbook, monitoring, risk record và tài liệu nếu cần.

Không nên đóng defect chỉ vì incident đã được resolve. Nếu workaround vẫn đang được dùng hoặc nguyên nhân chưa được loại bỏ, defect vẫn cần được theo dõi.

### Problem management và phân tích nguyên nhân gốc

Với lỗi lặp lại hoặc có tác động lớn, cần tìm nguyên nhân hệ thống thay vì chỉ sửa triệu chứng. Có thể dùng 5 Whys, fishbone hoặc fault tree tùy bối cảnh. Kết quả cần chuyển thành hành động có owner, chẳng hạn thay đổi kiến trúc, thêm validation, cải thiện observability, sửa pipeline hoặc đào tạo.

Không nên dùng phân tích nguyên nhân để quy lỗi cá nhân. Mục tiêu là hiểu điều kiện trong hệ thống và cải thiện khả năng ngăn ngừa, phát hiện và phục hồi.

## 17. Chỉ số theo dõi backlog và rủi ro

Metrics giúp nhìn xu hướng và phát hiện vấn đề quản lý. Không nên tối ưu một chỉ số đơn lẻ vì có thể tạo hành vi đóng ticket hình thức hoặc giảm ghi nhận lỗi.

### Chỉ số backlog

- Tổng defect đang mở theo severity/priority.
- Số defect mới và số defect đóng trong kỳ.
- Defect age trung vị và phân vị cao.
- Số lỗi quá SLA hoặc quá ngày review.
- Tỷ lệ lỗi không có owner hoặc không có hành động tiếp theo.
- Tỷ lệ reopen sau khi đã verified/closed.
- Backlog theo component, nguồn phát hiện và nguyên nhân.

### Chỉ số xử lý

- Mean/median time to triage.
- Time to fix hoặc time to verify.
- Tỷ lệ defect được giải quyết trong mục tiêu SLA.
- Thời gian ở trạng thái blocked/deferred.
- Tỷ lệ lỗi tái diễn sau release.

### Chỉ số rủi ro

- Số risk record đang mở theo mức residual risk.
- Số accepted risk sắp hết hạn hoặc quá hạn review.
- Số ngoại lệ không có mitigation owner.
- Số incident liên quan đến risk đã chấp nhận.
- Tỷ lệ hành động giảm thiểu hoàn tất đúng hạn.

### Diễn giải thận trọng

MTTR thấp có thể là tín hiệu tốt, nhưng nếu ticket được đóng quá sớm và reopen nhiều thì số liệu gây hiểu nhầm. Backlog giảm có thể do sửa lỗi hoặc do ticket bị đóng không đúng. Luôn xem số liệu cùng mẫu ticket, severity, release, lịch sử incident và chất lượng bằng chứng.

## 18. Ví dụ xuyên suốt: lỗi đồng bộ trạng thái đơn hàng

Giả sử một nền tảng thương mại điện tử phát hiện một số đơn hàng vẫn ở trạng thái “đang xử lý” dù cổng thanh toán đã xác nhận thành công. Lỗi xuất hiện khi webhook đến chậm sau một lần timeout.

### Ghi nhận defect

- Tiêu đề: Đơn hàng không cập nhật trạng thái sau webhook thanh toán đến trễ.
- Môi trường: staging, build `order-service` 3.8.2-rc.2.
- Điều kiện: yêu cầu thanh toán timeout ở client nhưng provider xử lý thành công; webhook đến sau đó.
- Thực tế: payment reference ở trạng thái thành công nhưng order vẫn chờ thanh toán.
- Mong đợi: order chuyển sang trạng thái phù hợp đúng một lần và có thể đối soát.
- Bằng chứng: order ID, payment reference, timestamp, correlation ID và trace đã che dữ liệu nhạy cảm.

### Triage và ưu tiên

Triage xác định lỗi ảnh hưởng luồng đặt hàng và có thể làm khách hàng trả tiền nhưng không nhận xác nhận đơn. Severity có thể được xếp High hoặc Critical tùy phạm vi và khả năng đối soát; priority cao vì liên quan giao dịch tài chính. Nhóm giao owner cho Payment/Order integration và yêu cầu phân tích idempotency, thứ tự event và trạng thái cuối.

### Lựa chọn xử lý

Nhóm có thể chọn:

- Sửa trước release bằng cơ chế xử lý webhook idempotent và đối soát trạng thái.
- Tạm dừng phương thức thanh toán bị ảnh hưởng.
- Giới hạn rollout nếu có thể xác định rõ phạm vi và kiểm soát rủi ro.
- Tăng monitoring cho payment success nhưng order pending.
- Bổ sung quy trình đối soát thủ công trong thời gian ngắn nếu được phê duyệt và có kiểm soát.

### Nếu đề xuất chấp nhận có điều kiện

Giả sử tổ chức cân nhắc rollout nội bộ trong 24 giờ để thu thập thêm bằng chứng. Hồ sơ cần nêu rõ đây chỉ là nhóm người dùng nội bộ, giới hạn giao dịch, dashboard đối soát, cảnh báo khi trạng thái lệch, người trực và điều kiện dừng. Service owner và người có thẩm quyền nghiệp vụ/bảo mật liên quan phải phê duyệt theo quy trình. Nếu có nghĩa vụ tài chính hoặc hợp đồng không cho phép, không được dùng chấp nhận rủi ro để bỏ qua.

### Xác minh và đóng

Sau khi sửa, QA kiểm tra webhook đến đúng thứ tự, đến trễ, gửi lặp, timeout và retry. Test xác nhận trạng thái đơn cuối cùng nhất quán, không ghi nhận trùng giao dịch và có log/trace đủ để điều tra. Sau khi regression đạt và bản sửa được triển khai, defect có thể đóng; risk record liên quan được review để xác nhận biện pháp kiểm soát không còn cần thiết hoặc cập nhật trạng thái.

## 19. Những sai lầm thường gặp

**Đánh đồng severity và priority.** Severity mô tả mức ảnh hưởng; priority mô tả thứ tự xử lý. Ghi rõ hai giá trị và căn cứ để tránh tranh luận theo cảm tính.

**Không có owner cho lỗi tồn đọng.** Ticket không có người chịu trách nhiệm thường nằm im. Mỗi lỗi cần owner hoặc nhóm sở hữu cùng hành động tiếp theo.

**Để backlog tăng mà không review tuổi lỗi.** Lỗi cũ có thể ảnh hưởng ngày càng rộng hoặc khó sửa. Theo dõi aging và đặt ngày đánh giá lại.

**Đóng lỗi khi developer báo đã sửa.** Cần build/version cụ thể, retest và regression phù hợp trước khi xác nhận verified.

**Dùng Deferred như Accepted Risk.** Trì hoãn công việc không phải quyết định chấp nhận rủi ro. Hai trạng thái cần hồ sơ và điều kiện riêng.

**Chấp nhận rủi ro bằng lời nói.** Đồng thuận trong cuộc họp không đủ để truy vết. Ghi risk record, người có thẩm quyền, phạm vi, thời hạn và trigger.

**Chấp nhận rủi ro không có hạn.** Rủi ro có thể bị quên và trở thành trạng thái lâu dài. Đặt ngày hết hạn hoặc review và điều kiện rút lại quyết định.

**Cho rằng workaround loại bỏ defect.** Workaround chỉ giảm tác động nếu an toàn và được thực hiện đúng. Ghi chi phí, giới hạn và người chịu trách nhiệm.

**Chỉ nhìn số lượng ticket.** Một lỗi nghiêm trọng có thể quan trọng hơn nhiều lỗi nhỏ. Theo dõi severity, residual risk, tuổi lỗi và tác động thực tế.

**Đóng defect khi incident đã phục hồi.** Dịch vụ có thể hoạt động lại nhưng nguyên nhân gốc vẫn còn. Liên kết incident với defect/problem record và test hồi quy.

**Dùng accepted risk để vượt yêu cầu bắt buộc.** Một số nghĩa vụ không thể được miễn trừ bởi người quản lý dự án. Chuyển đến đúng quy trình chuyên môn hoặc không phát hành.

## 20. Checklist quản lý lỗi tồn đọng và rủi ro được chấp nhận

### Ghi nhận và triage

- [ ] Defect có ID, mô tả, build, môi trường và bằng chứng phù hợp.
- [ ] Kết quả thực tế được so sánh với yêu cầu hoặc hành vi mong đợi đã xác nhận.
- [ ] Ticket được phân loại đúng: defect, question, environment issue, incident follow-up hoặc change request.
- [ ] Severity và priority được xác định theo tiêu chí đã thống nhất.
- [ ] Có owner, hành động tiếp theo và mốc review.

### Theo dõi backlog

- [ ] Backlog được review định kỳ theo mức độ rủi ro.
- [ ] Tuổi lỗi, thời gian chờ và lỗi quá SLA được theo dõi.
- [ ] Lỗi không có owner hoặc không có hành động được xử lý.
- [ ] Lỗi lặp lại được phân tích theo nguyên nhân hệ thống.
- [ ] Lỗi đã sửa có retest và regression evidence trước khi đóng.

### Chấp nhận rủi ro

- [ ] Rủi ro có mô tả, likelihood, impact và residual risk.
- [ ] Biện pháp giảm thiểu và workaround được đánh giá.
- [ ] Risk owner và người có quyền chấp nhận được xác định.
- [ ] Quyết định có phạm vi, lý do, thời hạn và trigger review.
- [ ] Nghĩa vụ bắt buộc không bị miễn trừ trái quy định.
- [ ] Rủi ro accepted được theo dõi và đánh giá lại khi điều kiện đổi.

### Release và vận hành

- [ ] Báo cáo release readiness nêu rõ lỗi còn mở và test chưa chạy.
- [ ] Go/No-Go dựa trên bằng chứng và đúng thẩm quyền.
- [ ] Điều kiện rollout, monitoring, rollback và hỗ trợ được xác định.
- [ ] Incident liên kết với defect, release, deployment và test hồi quy.
- [ ] Metrics backlog và risk được review để cải thiện quy trình.

## 21. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Một lỗi hiển thị nhỏ có severity thấp nhưng xuất hiện trên trang thanh toán của mọi khách hàng trong ngày khuyến mãi. Priority có thể cao vì tác động kinh doanh và thời điểm, dù severity kỹ thuật không lớn. Cần giải thích cả hai đánh giá.

**Tình huống 2:** Developer chuyển defect sang Resolved, nhưng QA chưa có build chứa bản sửa. Lỗi chưa được verified. Giữ trạng thái chờ retest và yêu cầu build/version cùng bằng chứng trước khi đóng.

**Tình huống 3:** Nhóm chuyển một lỗi sang Deferred vì thiếu thời gian. Không có người phê duyệt, ngày review hoặc đánh giá tác động. Đây chưa phải accepted risk. Cần triage lại và xác định quyết định phù hợp.

**Tình huống 4:** Một lỗi bảo mật nghiêm trọng được Product Owner đồng ý bỏ qua để kịp release. Nếu chính sách yêu cầu Security approval hoặc không cho phép ngoại lệ, quyết định này không hợp lệ. Cần chuyển đúng thẩm quyền và có thể phải dừng phát hành.

**Tình huống 5:** Một rủi ro được chấp nhận cho rollout 10% trong 24 giờ. Sau 6 giờ, tỷ lệ lỗi vượt ngưỡng đã thống nhất. Trigger đã xảy ra; nhóm phải thực hiện hành động đã định, chẳng hạn dừng rollout hoặc rollback, và đánh giá lại quyết định.

**Tình huống 6:** Incident được khắc phục bằng thao tác đối soát thủ công, nhưng defect gây lệch trạng thái vẫn chưa được sửa. Incident có thể được resolve, nhưng defect và risk liên quan vẫn cần owner, kế hoạch khắc phục và monitoring.

Khi review backlog hoặc chuẩn bị phát hành, hãy tự hỏi: **vấn đề nào còn tồn tại, ảnh hưởng đến ai, ai chịu trách nhiệm xử lý, rủi ro còn lại là gì và ai có quyền chấp nhận trong phạm vi nào?** Nếu không thể trả lời bằng hồ sơ và bằng chứng, quyết định chưa đủ minh bạch để bảo vệ sản phẩm và người dùng.

## Kết luận

Quản lý lỗi tồn đọng cần một quy trình liên tục từ ghi nhận, triage, phân loại severity/priority, giao owner, theo dõi tuổi lỗi, sửa, retest đến đóng có bằng chứng. Rủi ro chưa được loại bỏ phải được đánh giá riêng, có biện pháp giảm thiểu, risk owner, người có thẩm quyền, phạm vi, thời hạn và trigger xem xét lại. Khi defect backlog, incident, risk register và quyết định release được liên kết, tổ chức có thể ưu tiên đúng vấn đề, minh bạch rủi ro tồn dư và tránh biến lỗi đã biết thành những bất ngờ trong vận hành.
