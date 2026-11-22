# Xác định phần hồi quy chưa chạy và rủi ro còn lại của bản phát hành

## 1. Vì sao phải công khai phần hồi quy chưa chạy?

Kiểm thử hồi quy xác nhận rằng thay đổi mới không làm hỏng hành vi đã hoạt động trước đó. Trong thực tế, không phải mọi test case đều có thể chạy trong mỗi lần phát hành. Bộ hồi quy có thể lớn, một số môi trường hoặc thiết bị không sẵn sàng, phụ thuộc bên ngoài bị giới hạn, thời gian phát hành ngắn hoặc một số kiểm thử chỉ phù hợp chạy theo lịch. Vì vậy, một báo cáo chỉ ghi số test đạt và tỷ lệ pass có thể che khuất những khu vực chưa được xác nhận.

**Phần hồi quy chưa chạy** là tập điều kiện, ca kiểm thử hoặc khu vực rủi ro thuộc phạm vi cần xem xét nhưng không có kết quả thực thi hợp lệ cho bản dựng đang phát hành. Phần này có thể chưa được chọn, bị hoãn, bị chặn, không thể chạy do môi trường, hoặc được loại khỏi phạm vi theo một quyết định có căn cứ. Những trạng thái đó không giống nhau và không được gộp thành “đã đạt”.

**Rủi ro còn lại (residual risk)** là rủi ro vẫn tồn tại sau các hoạt động kiểm soát và kiểm thử đã thực hiện. Rủi ro có thể còn lại vì một phần hồi quy chưa chạy, test không đủ khả năng phát hiện, bằng chứng chưa đầy đủ, môi trường khác sản xuất, lỗi đã biết chưa được sửa hoặc một ngoại lệ được chấp thuận.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, mục tiêu không phải buộc mọi test phải chạy trong mọi bản phát hành. Mục tiêu là giúp người ra quyết định biết chính xác điều gì đã được xác nhận, điều gì chưa được xác nhận, hậu quả có thể xảy ra, biện pháp giảm thiểu nào còn hiệu lực và ai có thẩm quyền chấp nhận rủi ro. Một bản phát hành có thể được xem xét dù còn một số test chưa chạy, nhưng quyết định phải dựa trên thông tin minh bạch và ngưỡng chấp nhận đã thống nhất.

## 2. Phân biệt trạng thái kiểm thử

Trước khi tính phần chưa chạy, cần thống nhất trạng thái của từng ca kiểm thử và từng điều kiện hồi quy. Nếu các nhóm dùng trạng thái khác nhau, báo cáo tổng hợp sẽ không đáng tin cậy.

| Trạng thái | Ý nghĩa | Cách diễn giải khi đánh giá phát hành |
|---|---|---|
| Passed | Test đã chạy trên phiên bản và điều kiện xác định, kết quả đáp ứng expected result | Có bằng chứng xác nhận trong phạm vi test |
| Failed | Test đã chạy và kết quả không đáp ứng expected result | Cần điều tra, đánh giá ảnh hưởng và xử lý theo mức rủi ro |
| Blocked | Không thể thực hiện hoặc kết luận do trở ngại như môi trường, quyền, dữ liệu hoặc phụ thuộc | Chưa có bằng chứng; cần nêu nguyên nhân và hành động |
| Not run | Được dự kiến hoặc thuộc phạm vi xem xét nhưng chưa được thực hiện | Chưa được xác nhận; không được tính là passed |
| Deferred | Chủ động hoãn sang thời điểm hoặc đợt kiểm thử khác | Cần lý do, owner, hạn hoàn tất và rủi ro tạm thời |
| Not applicable | Không áp dụng cho phiên bản hoặc thay đổi này, có căn cứ rõ | Chỉ loại khỏi mẫu số sau khi xác nhận phạm vi và lý do |
| Skipped | Runner hoặc người thực hiện bỏ qua test theo điều kiện hay chỉ thị | Phải ghi nguyên nhân; không mặc định tương đương not applicable |
| Inconclusive | Có thực hiện nhưng bằng chứng không đủ để kết luận, ví dụ kết quả chập chờn hoặc dữ liệu không hợp lệ | Không thể xem là đạt; cần chạy lại hoặc bổ sung bằng chứng |
| Quarantined | Tạm cách ly test do không ổn định hoặc có vấn đề đã biết | Rủi ro bao phủ bị giảm; phải có owner và kế hoạch đưa lại |

Một test bị blocked do môi trường khác với một test không được chọn vì thời gian. Một test not applicable khác với test skipped do cấu hình pipeline. Báo cáo cần giữ được các phân biệt này để nhóm có thể xử lý đúng nguyên nhân.

### 2.1. Không dùng tỷ lệ pass để che phần chưa chạy

Giả sử có 200 test trong phạm vi hồi quy: 170 passed, 5 failed, 10 blocked và 15 not run. Nếu chỉ tính trên 175 test đã có kết quả passed/failed, tỷ lệ pass là 97,1%. Con số này không có nghĩa 97,1% toàn bộ phạm vi đã được xác nhận. Trong tổng số 200 test, chỉ 85% đã có kết quả chạy; 12,5% chưa chạy và 2,5% bị chặn.

Báo cáo cần thể hiện đồng thời số lượng theo trạng thái, phạm vi áp dụng và mức độ quan trọng của test. Một test bảo mật hoặc thanh toán chưa chạy có thể quan trọng hơn hàng chục test giao diện ít rủi ro đã đạt.

## 3. Xác định phạm vi hồi quy cần xem xét

### 3.1. Bắt đầu từ thay đổi của bản phát hành

Tập hợp thay đổi trong release candidate: mã nguồn, thư viện, cấu hình, schema, dữ liệu, hạ tầng, feature flag, quyền, endpoint và dependency. Không chỉ xem danh sách file được sửa. Một thay đổi trong thư viện dùng chung hoặc cấu hình gateway có thể ảnh hưởng đến nhiều dịch vụ dù mã nghiệp vụ không đổi.

Thông tin đầu vào nên gồm:

- Commit, build ID, tag hoặc phiên bản release candidate.
- Danh sách pull request, issue và thay đổi cấu hình.
- Dependency và image được nâng cấp.
- Migration dữ liệu và thay đổi schema.
- Feature flag được bật/tắt hoặc đổi giá trị.
- Thay đổi API, event, hợp đồng và tích hợp.
- Lỗi đã sửa, lỗi còn mở và ngoại lệ đã được chấp thuận.
- Các thay đổi môi trường hoặc hạ tầng có thể tác động hành vi.

Nếu không xác định chính xác phiên bản đang đánh giá, kết quả hồi quy có thể thuộc về một bản dựng khác và không hỗ trợ quyết định phát hành hiện tại.

### 3.2. Liên kết thay đổi với thành phần và hành trình

Với từng thay đổi, xác định thành phần trực tiếp, phụ thuộc gián tiếp và hành trình nghiệp vụ có thể bị ảnh hưởng. Có thể sử dụng sơ đồ kiến trúc, dependency graph, code ownership, API catalog, contract, log sử dụng và hồ sơ sự cố.

Ví dụ, thay đổi thư viện xác thực có thể tác động đến đăng nhập, refresh token, phân quyền API, job nền và tích hợp đối tác. Nếu chỉ chạy test của màn hình đăng nhập, phạm vi hồi quy có thể chưa bao phủ các consumer khác.

### 3.3. Chọn test theo tác động và rủi ro

Từ bản đồ ảnh hưởng, lập danh sách test liên quan rồi ưu tiên theo:

- Mức độ nghiêm trọng nếu hành vi hỏng.
- Khả năng thay đổi ảnh hưởng đến hành vi.
- Mức độ phụ thuộc và số lượng consumer.
- Tần suất sử dụng và giá trị nghiệp vụ.
- Lịch sử lỗi ở khu vực đó.
- Khả năng phát hiện lỗi sau phát hành.
- Khả năng rollback hoặc khôi phục.
- Yêu cầu bảo mật, pháp lý, an toàn hoặc hợp đồng.

Kiểm thử hồi quy dựa trên rủi ro có thể giảm số test chạy ở mỗi lần commit, nhưng không được loại bỏ test trọng yếu chỉ vì thời gian chạy dài. Những test dài có thể được xếp vào pipeline trước phát hành, chạy theo lịch hoặc thực hiện trên môi trường riêng; trạng thái của chúng vẫn phải được phản ánh trong quyết định release.

### 3.4. Phân biệt phạm vi bắt buộc và phạm vi mở rộng

Nhóm nên xác định trước:

- **Bắt buộc:** các kiểm thử không đạt hoặc chưa có kết quả sẽ chặn phát hành theo chính sách.
- **Có điều kiện:** có thể chấp nhận chưa chạy nếu có biện pháp thay thế, owner và phê duyệt phù hợp.
- **Mở rộng:** tăng độ tin cậy hoặc kiểm tra các rủi ro ít gặp; lịch chạy có thể khác nhưng vẫn cần theo dõi.
- **Không áp dụng:** có căn cứ cho thấy điều kiện không tồn tại hoặc thay đổi không ảnh hưởng đến phạm vi đó.

Không tự chuyển một test bắt buộc thành mở rộng chỉ vì pipeline đang chậm. Việc đổi phân loại cần được review theo rủi ro và chính sách chất lượng.

## 4. Tìm và ghi nhận phần hồi quy chưa chạy

### 4.1. Đối chiếu danh mục test với kết quả lần chạy

Đối chiếu danh mục test thuộc phạm vi release với execution report của đúng build. Mỗi test cần có định danh ổn định và một trạng thái rõ ràng. Những test không xuất hiện trong report không được coi là đạt.

Quy trình kiểm tra:

1. Chốt build hoặc release candidate cần đánh giá.
2. Xác định baseline regression suite và các test bắt buộc.
3. Cập nhật danh sách test theo thay đổi và impact analysis.
4. Lấy kết quả từ tất cả pipeline, môi trường và hoạt động thủ công có liên quan.
5. Ghép kết quả theo test ID, phiên bản, môi trường và thời điểm.
6. Liệt kê test không có kết quả hợp lệ, test blocked, inconclusive, quarantined và test bị loại.
7. Kiểm tra các trường hợp trùng, test chạy trên build cũ hoặc kết quả đã hết hiệu lực.

Nếu một test được chạy trên build trước khi có thay đổi cuối cùng, kết quả đó không tự động áp dụng cho release candidate mới. Cần đánh giá xem thay đổi sau đó có ảnh hưởng đến test hoặc phụ thuộc của nó hay không.

### 4.2. Phân loại lý do chưa chạy

| Nhóm nguyên nhân | Ví dụ | Thông tin cần ghi |
|---|---|---|
| Giới hạn thời gian | Không đủ cửa sổ phát hành để chạy bộ test dài | Thời lượng còn thiếu, ưu tiên và thời điểm chạy tiếp |
| Môi trường | Staging không sẵn sàng hoặc thiết bị không khả dụng | Environment ID, sự cố, owner và kế hoạch khôi phục |
| Dữ liệu | Không tạo được dữ liệu đại diện hoặc dữ liệu bị khóa | Điều kiện dữ liệu thiếu và cách bổ sung |
| Phụ thuộc bên ngoài | Sandbox đối tác ngừng hoạt động hoặc rate limit | Phạm vi phụ thuộc, bằng chứng thay thế và giới hạn |
| Hạ tầng/runner | Agent CI hết tài nguyên hoặc pipeline bị hủy | Run ID, log, nguyên nhân và khả năng chạy lại |
| Test không ổn định | Test bị cách ly do flaky | Lịch sử thất bại, rủi ro bị mất và owner |
| Thay đổi phạm vi | Test bị loại do chức năng không còn trong release | Căn cứ, người review và liên kết thay đổi |
| Thiếu quyền hoặc thiết bị | Không có role, chứng chỉ hoặc phần cứng cần thiết | Phần chưa xác nhận và phương án thay thế |
| Quyết định hoãn | Chủ động dời sang đợt sau | Lý do, người chấp thuận, hạn và biện pháp giảm thiểu |

Một nguyên nhân kỹ thuật không tự nó là lý do chấp nhận rủi ro. Ví dụ, “sandbox không hoạt động” giải thích vì sao test chưa chạy nhưng chưa cho biết có thể phát hành hay không. Cần đánh giá tác động và bằng chứng thay thế.

### 4.3. Phân biệt chưa chạy với không áp dụng

Chỉ đánh dấu not applicable khi có bằng chứng rằng điều kiện không tồn tại trong release hoặc yêu cầu không còn hiệu lực. Ví dụ, test cho một thiết bị đã chính thức ngừng hỗ trợ có thể không áp dụng nếu phạm vi sản phẩm và chính sách tương thích đã xác nhận.

Không đánh dấu not applicable chỉ vì test khó chạy, ít khi được sử dụng hoặc không có người phụ trách. Những trường hợp đó vẫn là khoảng trống hoặc quyết định loại trừ cần được ghi nhận.

### 4.4. Ghi nhận phần bao phủ bị mất

Với mỗi nhóm test chưa chạy, chỉ rõ:

- Yêu cầu, rủi ro và thành phần liên quan.
- Hành vi hoặc điều kiện chưa được xác nhận.
- Mức ưu tiên và hậu quả nếu có lỗi.
- Lý do test chưa chạy.
- Bằng chứng thay thế nếu có.
- Biện pháp giảm thiểu tạm thời.
- Người sở hữu và thời điểm xử lý tiếp.

Không chỉ liệt kê ID test. Người ra quyết định cần hiểu test đó bảo vệ điều gì và phần nào của sản phẩm còn chưa có bằng chứng.

## 5. Đánh giá rủi ro còn lại của bản phát hành

### 5.1. Từ khoảng trống kiểm thử đến rủi ro

Không phải mọi test chưa chạy đều tạo ra rủi ro như nhau. Cần xác định sự kiện lỗi có thể xảy ra, nguyên nhân, hậu quả và khả năng phát hiện. Ví dụ:

> Do kiểm thử migration chưa chạy trên dữ liệu có lịch sử dài, migration có thể làm sai lệch một số bản ghi cũ, dẫn đến báo cáo số dư không chính xác sau phát hành.

Mô tả này rõ hơn câu “còn thiếu test migration” vì nó cho biết điều chưa được xác nhận và hậu quả có thể xảy ra.

### 5.2. Các chiều đánh giá

Đánh giá rủi ro còn lại theo những chiều phù hợp:

- **Tác động:** ảnh hưởng đến người dùng, tiền, dữ liệu, bảo mật, hoạt động và nghĩa vụ tuân thủ.
- **Khả năng xảy ra:** mức độ có thể xuất hiện lỗi dựa trên thay đổi, độ phức tạp, lịch sử và điều kiện vận hành.
- **Phạm vi phơi nhiễm:** số người dùng, tenant, giao dịch, dịch vụ hoặc khu vực có thể bị ảnh hưởng.
- **Khả năng phát hiện:** metric, cảnh báo, đối soát hoặc phản hồi người dùng có phát hiện lỗi sớm không.
- **Khả năng khôi phục:** có thể rollback, tắt tính năng, sửa dữ liệu hoặc bù trừ giao dịch an toàn không.
- **Thời gian tồn tại:** lỗi có thể kéo dài bao lâu trước khi được phát hiện và xử lý.
- **Mức độ bất định:** bằng chứng còn thiếu nhiều hay ít, giả định nào chưa được xác nhận.

Không cần dùng một công thức số học duy nhất cho mọi sản phẩm. Nếu dùng ma trận xác suất và tác động, cần định nghĩa thang điểm và cách diễn giải. Với rủi ro bảo mật, an toàn, dữ liệu hoặc pháp lý, cần áp dụng ngưỡng chuyên môn và chính sách bắt buộc của tổ chức.

### 5.3. Rủi ro vốn có và rủi ro còn lại

**Rủi ro vốn có (inherent risk)** là mức rủi ro trước khi tính các biện pháp kiểm soát. **Rủi ro còn lại** là phần rủi ro sau khi đã xem xét kiểm thử, kiểm soát, giám sát và biện pháp giảm thiểu.

Ví dụ, một thay đổi trong luồng hoàn tiền có rủi ro vốn có cao vì có thể gây hoàn tiền sai. Contract test, API test, đối soát dữ liệu, giới hạn số tiền và giám sát sau phát hành làm giảm rủi ro. Tuy nhiên, nếu test tải đồng thời chưa chạy và chưa có bằng chứng về tranh chấp số dư, rủi ro còn lại vẫn cần được ghi nhận.

Không được coi một biện pháp đã thiết kế nhưng chưa thực hiện là biện pháp đã có hiệu lực. Một test case tồn tại trong repository nhưng chưa chạy không làm giảm rủi ro của release candidate.

### 5.4. Đánh giá độ tin cậy của bằng chứng

Rủi ro còn lại phụ thuộc vào chất lượng bằng chứng. Cần xem:

- Test có chạy trên đúng build và cấu hình không?
- Dữ liệu có đại diện cho điều kiện quan trọng không?
- Môi trường có đủ trung thực với môi trường đích không?
- Test có assertion đúng và đủ sâu không?
- Kết quả có ổn định qua các lần chạy không?
- Artifact có thể truy xuất và hỗ trợ điều tra không?
- Có phụ thuộc hoặc khoảng trống nào chưa được ghi nhận không?

Nếu test đạt nhưng chạy trên môi trường thiếu một dependency quan trọng, kết luận cần giới hạn theo phần đã xác nhận. Không dùng nhãn passed để ngụ ý mọi điều kiện sản xuất đã được kiểm tra.

## 6. Biện pháp giảm thiểu khi chưa thể chạy hồi quy

Khi một phần hồi quy chưa chạy, nhóm có thể cân nhắc các biện pháp thay thế hoặc giảm thiểu. Biện pháp phải phù hợp với rủi ro và được ghi rõ giới hạn.

### 6.1. Kiểm tra ở tầng khác

Nếu end-to-end test bị chặn, có thể chạy API, component hoặc contract test để xác nhận một phần hành vi. Tuy nhiên, test ở tầng khác không tự động thay thế toàn bộ bằng chứng đầu cuối. Cần nêu rõ các rủi ro còn lại như mạng, cấu hình, trình duyệt hoặc phối hợp nhiều dịch vụ.

### 6.2. Rà soát mã và cấu hình

Code review, static analysis, schema diff, dependency scan hoặc kiểm tra migration có thể cung cấp bằng chứng bổ sung. Những hoạt động này giúp phát hiện một số vấn đề nhưng không chứng minh hành vi runtime nếu chưa thực thi.

### 6.3. Canary, feature flag và giới hạn phạm vi

Có thể triển khai cho một nhóm nhỏ, tenant nội bộ hoặc tỷ lệ lưu lượng giới hạn; bật feature flag theo từng giai đoạn; giới hạn số giao dịch hoặc phạm vi dữ liệu. Cần có chỉ báo rõ và điều kiện dừng tự động hoặc do người có thẩm quyền quyết định.

Canary không thay thế kiểm thử trước phát hành cho các rủi ro có hậu quả nghiêm trọng. Nó là một biện pháp giảm phạm vi phơi nhiễm và thu thập bằng chứng trong vận hành.

### 6.4. Tăng cường giám sát và đối soát

Thêm metric, log, trace, cảnh báo và đối soát dữ liệu cho khu vực chưa được kiểm tra. Ví dụ, nếu chưa chạy đủ hồi quy thanh toán, có thể tăng theo dõi tỷ lệ giao dịch thất bại, giao dịch trùng, chênh lệch số tiền và thời gian xác nhận. Cần có người trực hoặc quy trình phản ứng khi chỉ báo vượt ngưỡng.

### 6.5. Giữ khả năng rollback hoặc forward-fix

Xác định điều kiện rollback, feature flag tắt nhanh, phiên bản tương thích và cách khôi phục dữ liệu. Nếu migration không thể đảo ngược, cần phương án forward-fix, backup, đối soát hoặc bù trừ. Thử nghiệm phương án khôi phục ở mức phù hợp trước khi dựa vào nó.

### 6.6. Hoãn phát hành hoặc giảm phạm vi

Nếu rủi ro còn lại vượt ngưỡng, lựa chọn phù hợp có thể là chờ môi trường, chạy lại test, tắt tính năng, hoãn một phần chức năng hoặc chia release thành nhiều đợt. Không nên dùng biện pháp giám sát sau phát hành để hợp thức hóa một rủi ro mà tổ chức không có khả năng phát hiện hoặc khôi phục.

## 7. Quy trình đánh giá phần chưa chạy và rủi ro release

### Bước 1: Chốt release candidate

Ghi build ID, commit, cấu hình, schema và các thành phần đi cùng. Nếu build thay đổi sau khi tổng hợp kết quả, đánh giá lại tính hiệu lực của bằng chứng.

### Bước 2: Xác định baseline và phạm vi hồi quy

Chọn bộ test chuẩn, test bắt buộc, test theo rủi ro và các test bổ sung từ impact analysis. Ghi rõ tiêu chí đưa test vào hoặc loại test khỏi phạm vi.

### Bước 3: Thu thập kết quả

Tập hợp báo cáo tự động và thủ công từ đúng build. Chuẩn hóa test ID, môi trường, trạng thái và artifact. Không gộp kết quả từ nhiều phiên bản nếu không có căn cứ tương đương.

### Bước 4: Lập danh sách khoảng trống

Liệt kê test not run, blocked, deferred, inconclusive, quarantined và skipped. Xác định lý do, phạm vi và phần bao phủ bị mất. Review các test được đánh dấu not applicable.

### Bước 5: Liên kết với rủi ro

Với mỗi khoảng trống, ghi yêu cầu, thành phần, hành trình, rủi ro, tác động và khả năng phát hiện. Gộp các test cùng bảo vệ một rủi ro khi phù hợp, nhưng giữ lại liên kết tới từng test.

### Bước 6: Đánh giá bằng chứng thay thế và biện pháp giảm thiểu

Xác định test ở tầng khác, review, kiểm tra cấu hình, canary, giám sát hoặc phương án khôi phục có thể giảm rủi ro hay không. Ghi rõ biện pháp nào đã thực hiện và biện pháp nào mới chỉ được đề xuất.

### Bước 7: Xác định mức rủi ro còn lại

Đánh giá tác động, khả năng xảy ra, phạm vi phơi nhiễm, khả năng phát hiện, khôi phục và bất định. Xác định rủi ro vượt ngưỡng hoặc cần phê duyệt ngoại lệ.

### Bước 8: Quyết định và ghi nhận

Người có thẩm quyền quyết định phát hành, phát hành có điều kiện, giảm phạm vi hoặc hoãn. Ghi lý do, rủi ro chấp nhận, owner, hành động sau phát hành và hạn hoàn tất. Không để quyết định chỉ tồn tại trong cuộc họp hoặc tin nhắn không truy xuất được.

### Bước 9: Theo dõi sau phát hành

Theo dõi chỉ báo đã định, chạy test còn thiếu khi điều kiện cho phép, đóng ngoại lệ và cập nhật hồ sơ rủi ro. Nếu xuất hiện tín hiệu bất thường, kích hoạt quy trình incident và thực hiện biện pháp đã thống nhất.

## 8. Ma trận quyết định phát hành

Ma trận dưới đây là ví dụ để tổ chức điều chỉnh theo chính sách chất lượng:

| Trạng thái bằng chứng/rủi ro | Quyết định thường phù hợp | Điều kiện |
|---|---|---|
| Test bắt buộc đạt, không có lỗi nghiêm trọng mở, rủi ro còn lại trong ngưỡng | Có thể phát hành | Bằng chứng thuộc đúng build và có giám sát cần thiết |
| Một số test mở rộng chưa chạy, không liên quan thay đổi và có đánh giá tác động | Có thể phát hành theo chính sách | Lý do và giới hạn được ghi; không ảnh hưởng yêu cầu bắt buộc |
| Test quan trọng bị blocked nhưng có bằng chứng thay thế đủ mạnh | Xem xét phát hành có điều kiện | Owner và người có thẩm quyền xác nhận phần rủi ro còn lại |
| Test bắt buộc chưa chạy, không có bằng chứng thay thế | Thường hoãn phát hành | Chạy test hoặc giảm phạm vi chức năng |
| Test trọng yếu failed hoặc phát hiện lỗi nghiêm trọng chưa xử lý | Chặn phát hành theo chính sách | Chỉ xem xét lại sau khi xử lý và xác minh đầy đủ |
| Rủi ro bảo mật, dữ liệu, an toàn hoặc tuân thủ vượt ngưỡng | Không phát hành nếu chưa có quyết định hợp lệ | Tuân thủ quy trình chuyên môn và thẩm quyền bắt buộc |
| Kết quả không thể kết luận hoặc build đã thay đổi sau test | Chưa đủ bằng chứng | Chạy lại hoặc đánh giá lại tính áp dụng của bằng chứng |

Ma trận không thay thế chính sách phát hành. Các yêu cầu bắt buộc theo hợp đồng, pháp luật, an toàn hoặc bảo mật có thể không được phép miễn trừ bởi quyết định quản lý thông thường.

## 9. Chấp thuận rủi ro và quản lý ngoại lệ

### 9.1. Nội dung của một ngoại lệ

Một ngoại lệ phát hành cần có:

- Mã ngoại lệ và release candidate liên quan.
- Test hoặc điều kiện chưa chạy.
- Lý do và bằng chứng xác nhận nguyên nhân.
- Yêu cầu, thành phần, người dùng và rủi ro bị ảnh hưởng.
- Mức rủi ro còn lại và giả định chưa được xác nhận.
- Biện pháp giảm thiểu trước, trong và sau phát hành.
- Người sở hữu rủi ro và người có thẩm quyền chấp thuận.
- Thời hạn, điều kiện hết hiệu lực và hành động bắt buộc sau phát hành.
- Tiêu chí kích hoạt dừng, rollback hoặc incident.

### 9.2. Ai có quyền chấp thuận?

Người sở hữu kỹ thuật có thể giải thích phạm vi và bằng chứng; product owner có thể đánh giá tác động nghiệp vụ; security, privacy, compliance hoặc safety owner có thể có quyền quyết định chuyên môn theo chính sách. Release authority hoặc người chịu trách nhiệm cuối cùng quyết định trong phạm vi thẩm quyền của mình.

Người thực hiện test không nên tự chấp thuận rủi ro vượt quá quyền hạn. Nhóm phát triển cũng không thể tự miễn trừ một yêu cầu bắt buộc thuộc quyền phê duyệt của bộ phận khác.

### 9.3. Ngoại lệ phải có thời hạn

Không để ngoại lệ tồn tại vô thời hạn. Ghi ngày hết hạn hoặc sự kiện làm ngoại lệ mất hiệu lực, ví dụ khi có build mới, thay đổi phạm vi, phát hiện lỗi liên quan hoặc hết thời gian hỗ trợ. Nếu test bị hoãn sang đợt sau, cần tạo công việc có owner và hạn cụ thể.

### 9.4. Không biến chấp thuận thành bằng chứng đạt

Chấp thuận rủi ro chỉ ghi nhận rằng người có thẩm quyền đồng ý phát hành trong điều kiện đã nêu. Nó không làm cho test chưa chạy trở thành passed, không xóa khoảng trống bao phủ và không chứng minh rủi ro đã được loại bỏ.

## 10. Báo cáo hồi quy và rủi ro còn lại

### 10.1. Nội dung tối thiểu của báo cáo

Một báo cáo phục vụ quyết định phát hành nên có:

| Nhóm thông tin | Nội dung |
|---|---|
| Release identity | Release candidate, build ID, commit, thời điểm và cấu hình |
| Scope | Bộ hồi quy, thay đổi và thành phần được đánh giá |
| Execution summary | Tổng test theo passed, failed, blocked, not run, deferred, inconclusive, skipped và not applicable |
| Mandatory checks | Trạng thái từng kiểm thử bắt buộc và tiêu chí chặn |
| Untested areas | Khu vực, yêu cầu, hành trình hoặc rủi ro chưa được xác nhận |
| Reasons | Nguyên nhân chưa chạy và bằng chứng liên quan |
| Residual risks | Mô tả rủi ro, tác động, khả năng, phơi nhiễm và khả năng phát hiện |
| Mitigations | Bằng chứng thay thế, giám sát, canary, rollback hoặc giới hạn phạm vi |
| Exceptions | Mã ngoại lệ, người chấp thuận, thời hạn và điều kiện |
| Decision | Phát hành, phát hành có điều kiện, giảm phạm vi hoặc hoãn |
| Follow-up | Owner, hành động, thời hạn và tiêu chí đóng |

### 10.2. Trình bày số liệu đúng cách

Nên báo cáo cả số lượng tuyệt đối và tỷ lệ. Ghi rõ mẫu số được tính từ tập test nào, cách xử lý test not applicable và thời điểm chốt dữ liệu. Có thể tách:

- Tỷ lệ thực thi: số test có kết quả chạy hợp lệ trên tổng test áp dụng.
- Tỷ lệ đạt: số test passed trên tổng test đã chạy có kết quả kết luận, kèm số failed và inconclusive.
- Tỷ lệ chưa chạy/bị chặn: số test not run, deferred hoặc blocked trên tổng test áp dụng.
- Bao phủ theo rủi ro: các rủi ro cao có bằng chứng hiện hành và rủi ro chưa được xác nhận.

Không cộng các trạng thái khác nhau thành một tỷ lệ “coverage” duy nhất nếu làm mất thông tin. Không đưa test not applicable vào mẫu số như thể nó là test chưa chạy; đồng thời phải giữ lý do loại trừ để có thể review.

### 10.3. Tóm tắt cho người ra quyết định

Phần tóm tắt cần trả lời ngắn gọn:

1. Bản dựng nào đang được đánh giá?
2. Những kiểm thử bắt buộc nào đã đạt, thất bại hoặc chưa có kết quả?
3. Khu vực rủi ro nào chưa được xác nhận?
4. Biện pháp giảm thiểu nào đã có bằng chứng?
5. Rủi ro còn lại nào cần chấp thuận?
6. Đề xuất phát hành, phát hành có điều kiện, giảm phạm vi hay hoãn?

Không chỉ đưa ra màu xanh/vàng/đỏ mà thiếu lý do. Người ra quyết định cần thấy cơ sở và giới hạn của kết luận.

## 11. Ví dụ thực tế

### Ví dụ A: Phát hành dịch vụ thanh toán khi test tải chưa chạy

Release candidate thay đổi cách tính phí và cập nhật thư viện xử lý giao dịch. Unit test, API test và contract test đều đạt. Kiểm thử tải đồng thời chưa chạy vì cụm performance đang bảo trì.

Phân tích tác động cho thấy thay đổi nằm trên đường xử lý giao dịch đồng thời. Rủi ro còn lại là tranh chấp cập nhật hoặc suy giảm khi nhiều yêu cầu cùng xử lý. Nhóm ghi test tải là blocked, không phải not applicable. Bằng chứng thay thế gồm kiểm thử component với số luồng giới hạn và review thay đổi đồng bộ; chúng không chứng minh tải cực đại.

Release authority cân nhắc giảm lưu lượng ban đầu, bật canary cho một phần giao dịch, theo dõi tỷ lệ lỗi, độ trễ và giao dịch trùng, đồng thời giữ ngưỡng dừng rõ. Nếu rủi ro thanh toán vượt ngưỡng hoặc chính sách yêu cầu load test bắt buộc, phát hành phải hoãn đến khi kiểm thử hoàn tất.

### Ví dụ B: Một số kiểm thử trình duyệt chưa chạy

Một bản phát hành giao diện thay đổi component dùng chung. Bộ test Chromium đạt nhưng test trên Safari bị blocked do thiết bị CI không khả dụng. Nhóm xác định các luồng sử dụng API trình duyệt mới và các trang có lượng người dùng Safari đáng kể.

Test Safari được ghi blocked, liên kết với các hành trình bị ảnh hưởng. Nhóm có thể chạy kiểm tra thủ công trên thiết bị được phê duyệt hoặc kiểm tra tương thích API ở tầng khác, nhưng phải ghi giới hạn. Nếu phát hành có điều kiện, cần giới hạn rollout, theo dõi lỗi client theo browser và có phương án tắt thay đổi.

### Ví dụ C: Migration chưa được kiểm tra trên dữ liệu lịch sử lớn

Release thay đổi kiểu cột và cách chuẩn hóa mã khách hàng. Migration đã chạy trên fixture nhỏ nhưng chưa chạy trên snapshot tổng hợp có quy mô và phân bố gần thực tế.

Rủi ro còn lại gồm thời gian migration quá dài, khóa bảng, cắt cụt dữ liệu hoặc làm thay đổi giá trị có số 0 đầu. Nhóm ghi rõ fixture nhỏ không đại diện cho dữ liệu lịch sử lớn. Biện pháp giảm thiểu có thể gồm dry run trên bản sao dữ liệu đã được phê duyệt, đo thời gian, đối chiếu checksum/thống kê, backup và kế hoạch forward-fix.

Nếu dữ liệu có thể bị mất hoặc không thể khôi phục, cần hoàn tất xác nhận trên quy mô phù hợp trước khi phát hành.

### Ví dụ D: Test bị cách ly do flaky

Một test hồi quy xác nhận phân quyền API bị cách ly vì thất bại không ổn định. Nhóm không xóa test khỏi báo cáo. Họ ghi lịch sử flaky, điều kiện tái hiện, rủi ro truy cập trái phép và các kiểm tra thay thế hiện có.

Nếu test khác xác nhận cùng quyền ở tầng service nhưng không bao phủ gateway hoặc token scope, khoảng trống vẫn còn. Người có thẩm quyền cần quyết định có thể phát hành với biện pháp giảm thiểu hay phải sửa test và chạy lại. Test cách ly phải có owner và thời hạn đưa trở lại.

### Ví dụ E: Kết quả test thuộc build cũ

Pipeline hồi quy chạy thành công trên build A. Sau đó, một commit sửa cấu hình cache tạo build B nhưng báo cáo release vẫn đính kèm kết quả build A. Vì thay đổi cache có thể ảnh hưởng dữ liệu và trạng thái, nhóm không dùng kết quả A như bằng chứng tự động cho B.

Nhóm xác định test nào phụ thuộc cache, chạy lại tập liên quan trên build B và ghi rõ các test khác được đánh giá là không bị ảnh hưởng theo căn cứ nào. Release report phải trỏ đến đúng build B.

## 12. Mẫu báo cáo phần hồi quy chưa chạy và rủi ro còn lại

Có thể dùng mẫu sau trong release review:

~~~yaml
release_assessment:
  release_candidate: "release-4.8.0-rc2"
  build_id: "build-1842"
  commit: "a81f2d"
  assessed_at: "2027-01-18T09:30:00Z"

regression_summary:
  in_scope: 200
  passed: 170
  failed: 5
  blocked: 10
  not_run: 15
  deferred: 0
  inconclusive: 0
  not_applicable: 0

untested_items:
  - test_id: "PERF-PAY-014"
    status: blocked
    reason: "Performance environment unavailable"
    affected_area: "Concurrent payment processing"
    risk_id: "RISK-PAY-008"
    owner: "Payment test lead"
    next_action: "Run load test when dedicated environment is restored"
    due: "2027-01-19"

residual_risks:
  - id: "RR-REL-003"
    statement: "Concurrent requests may expose a race condition."
    impact: high
    likelihood: unknown
    exposure: "Initial rollout traffic"
    detection: "Duplicate-transaction alert and reconciliation"
    mitigation: "Canary rollout with transaction limits"
    owner: "Payment service owner"

decision:
  status: conditional
  approver: "Release authority"
  conditions:
    - "Keep rollout at the agreed traffic limit"
    - "Monitor duplicate transaction and error metrics"
    - "Stop rollout if the agreed threshold is exceeded"
  expiry: "2027-01-19T18:00:00Z"
~~~

Đây là mẫu minh họa. Số liệu và quyết định phải lấy từ kết quả thực tế của đúng release candidate. Không dùng nội dung ví dụ làm ngưỡng mặc định hoặc chấp thuận phát hành thực tế.

## 13. Theo dõi sau phát hành và đóng khoảng trống

Phần hồi quy chưa chạy cần được chuyển thành công việc có thể theo dõi. Sau khi phát hành:

- Chạy lại test bị blocked hoặc deferred khi môi trường và phụ thuộc sẵn sàng.
- Xác nhận test được cách ly đã có kế hoạch sửa và đưa lại vào suite.
- Theo dõi metric và cảnh báo được dùng làm biện pháp giảm thiểu.
- Kiểm tra canary hoặc rollout theo từng giai đoạn trước khi mở rộng.
- Đối chiếu dữ liệu, giao dịch hoặc trạng thái nếu rủi ro liên quan đến tính toàn vẹn.
- Cập nhật trạng thái ngoại lệ và đóng khi điều kiện hoàn tất được đáp ứng.
- Liên kết sự cố phát sinh với khoảng trống kiểm thử để cải thiện regression suite.

Nếu test chạy sau phát hành phát hiện lỗi, cần đánh giá ngay mức ảnh hưởng đến phiên bản đang chạy và quyết định rollback, forward-fix, tắt tính năng hoặc biện pháp bù trừ. Không chỉ cập nhật báo cáo hồi quy rồi coi vấn đề đã được xử lý.

Khi một test đã được thay thế bằng kiểm soát khác, cần review chính thức và cập nhật liên kết. Không để danh sách test bắt buộc cũ tồn tại nhưng không ai thực hiện, cũng không âm thầm xóa test khỏi suite.

## 14. Những sai lầm thường gặp

- **Chỉ báo cáo tỷ lệ pass:** che khuất test chưa chạy, blocked và rủi ro quan trọng.
- **Coi not run là not applicable:** biến khoảng trống thành trạng thái có vẻ hợp lệ.
- **Gộp blocked, skipped và deferred:** mất thông tin về nguyên nhân và hành động tiếp theo.
- **Dùng kết quả của build cũ:** bằng chứng không còn chắc chắn áp dụng cho release candidate.
- **Chỉ đếm số test:** không thể hiện yêu cầu và rủi ro nào được bảo vệ.
- **Loại test vì thời gian mà không phân tích:** có thể bỏ sót hành vi có hậu quả nghiêm trọng.
- **Coi test tồn tại là test đã xác nhận:** mã test chưa chạy không làm giảm rủi ro.
- **Dùng test ở tầng khác như bằng chứng thay thế toàn phần:** bỏ qua các rủi ro tích hợp còn lại.
- **Không đánh giá chất lượng môi trường:** kết quả passed có thể không đại diện cho điều kiện đích.
- **Chấp thuận rủi ro không có owner hoặc thời hạn:** ngoại lệ trở thành khoảng trống kéo dài.
- **Đưa biện pháp giảm thiểu chưa triển khai vào báo cáo như đã hoàn tất:** tạo cảm giác an toàn sai.
- **Không có tiêu chí dừng/rollback:** canary và giám sát không thể hạn chế tác động kịp thời.
- **Không chạy bù test sau phát hành:** rủi ro tạm thời không được đóng và bằng chứng luôn thiếu.
- **Đánh dấu flaky test là quarantined nhưng không theo dõi:** mất dần bao phủ mà không ai chịu trách nhiệm.

## 15. Checklist đánh giá phần hồi quy chưa chạy và rủi ro release

### Trước khi tổng hợp

- [ ] Release candidate, build ID, commit và cấu hình được chốt.
- [ ] Baseline regression suite và test bắt buộc được xác định.
- [ ] Thay đổi mã, dependency, schema, dữ liệu, cấu hình và hạ tầng được rà soát.
- [ ] Impact analysis liên kết thay đổi với thành phần, hành trình và rủi ro.
- [ ] Test thuộc phạm vi được chọn theo mức rủi ro và chính sách.

### Khi xác định phần chưa chạy

- [ ] Kết quả được đối chiếu theo đúng test ID và build.
- [ ] Passed, failed, blocked, not run, deferred, skipped, inconclusive, quarantined và not applicable được phân biệt.
- [ ] Mỗi test chưa chạy có lý do và owner.
- [ ] Test not applicable có căn cứ và người review.
- [ ] Phần bao phủ bị mất được liên kết với yêu cầu, thành phần và rủi ro.
- [ ] Kết quả trên build cũ hoặc môi trường khác được đánh giá tính áp dụng.

### Khi đánh giá rủi ro còn lại

- [ ] Tác động, khả năng xảy ra, phạm vi phơi nhiễm và khả năng phát hiện được xem xét.
- [ ] Khả năng khôi phục và mức độ bất định được ghi nhận.
- [ ] Bằng chứng thay thế được phân biệt với test chưa chạy.
- [ ] Biện pháp giảm thiểu đã triển khai được phân biệt với đề xuất.
- [ ] Rủi ro vượt ngưỡng và yêu cầu bắt buộc được xác định rõ.

### Trước quyết định phát hành

- [ ] Test bắt buộc đạt hoặc có quyết định ngoại lệ hợp lệ theo chính sách.
- [ ] Báo cáo có số lượng theo trạng thái và mẫu số rõ ràng.
- [ ] Rủi ro còn lại có owner và người chấp thuận đúng thẩm quyền.
- [ ] Ngoại lệ có lý do, điều kiện, hạn hết hiệu lực và hành động tiếp theo.
- [ ] Có kế hoạch canary, giám sát, dừng, rollback hoặc forward-fix khi cần.
- [ ] Đề xuất phát hành, phát hành có điều kiện, giảm phạm vi hoặc hoãn có căn cứ.

### Sau phát hành

- [ ] Test blocked/deferred được chạy bù theo hạn.
- [ ] Metric và cảnh báo giảm thiểu được theo dõi.
- [ ] Ngoại lệ được rà soát và đóng khi đủ điều kiện.
- [ ] Lỗi phát sinh được liên kết với khoảng trống hồi quy.
- [ ] Regression suite và impact mapping được cập nhật.

## Kết luận

Đánh giá hồi quy chưa chạy và rủi ro còn lại là một phần của quyết định phát hành, không chỉ là thống kê test. Nhóm cần chốt đúng release candidate, đối chiếu toàn bộ trạng thái thực thi, xác định phần bao phủ bị mất, liên kết khoảng trống với rủi ro và đánh giá chất lượng bằng chứng. Biện pháp thay thế, canary, giám sát hoặc rollback có thể giảm rủi ro nhưng không biến test chưa chạy thành test đạt. Khi ngoại lệ có owner, thẩm quyền, điều kiện và thời hạn rõ ràng, người ra quyết định có thể phát hành có trách nhiệm hoặc hoãn khi bằng chứng chưa đủ.
