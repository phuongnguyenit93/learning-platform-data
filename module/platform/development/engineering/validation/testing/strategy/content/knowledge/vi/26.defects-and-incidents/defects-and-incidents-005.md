# Liên kết lỗi với yêu cầu, rủi ro, bản build và bằng chứng

## Mục tiêu bài học

Một báo cáo lỗi chỉ có thể hỗ trợ sửa chữa và quyết định phát hành khi người đọc hiểu lỗi ảnh hưởng đến điều gì, trong điều kiện nào xảy ra, phiên bản nào bị ảnh hưởng và bằng chứng nào chứng minh hành vi sai. Nếu báo cáo chỉ có tiêu đề như “không lưu được dữ liệu” cùng một ảnh chụp màn hình, nhóm có thể tái hiện sai điều kiện, đánh giá sai mức độ nghiêm trọng hoặc không biết lỗi đã được sửa trong bản build nào.

Trong chiến lược VALIDATION_TESTING_STRATEGY, quản lý lỗi cần duy trì mối liên kết có thể truy vết giữa **lỗi, yêu cầu, rủi ro, bản build và bằng chứng**. Các liên kết này tạo thành chuỗi giải thích từ điều sản phẩm phải làm, điều có thể xảy ra sai, biểu hiện thực tế, phiên bản bị ảnh hưởng, đến kết quả xác minh sau sửa. Chúng giúp nhóm xác định phạm vi ảnh hưởng, ưu tiên xử lý, tái hiện lỗi, kiểm tra bản sửa và cung cấp căn cứ cho quyết định phát hành.

Sau bài học, người học có thể:

- Giải thích vai trò của yêu cầu, rủi ro, defect, build và evidence trong quản lý lỗi.
- Thiết kế quan hệ truy vết hai chiều giữa lỗi và yêu cầu hoặc rủi ro liên quan.
- Ghi nhận build, commit, artifact, cấu hình và môi trường để xác định phạm vi bị ảnh hưởng.
- Thu thập bằng chứng có thể tái lập, kiểm tra và bảo vệ thông tin nhạy cảm.
- Phân biệt severity, priority, impact và mức độ khẩn cấp.
- Theo dõi vòng đời lỗi từ phát hiện đến xác minh bản sửa và đóng lỗi.
- Liên kết lỗi với test case, lần chạy, thay đổi mã và bản build đã xác minh.
- Dùng dữ liệu truy vết để phân tích xu hướng, lỗi tái diễn và rủi ro còn lại.

## 1. Vì sao cần liên kết lỗi với các đối tượng khác?

Một defect không tồn tại độc lập. Nó là biểu hiện cho thấy hành vi thực tế có thể khác với yêu cầu, hợp đồng hoặc bất biến mà sản phẩm cần đáp ứng. Một lỗi có thể ảnh hưởng đến nhiều yêu cầu; một yêu cầu có thể chịu tác động từ nhiều lỗi; một rủi ro có thể được biểu hiện qua nhiều defect; và một defect có thể xuất hiện ở nhiều build hoặc môi trường.

Nếu các liên kết này không được lưu, nhóm dễ gặp các vấn đề:

- Không biết lỗi vi phạm yêu cầu nào hoặc hành vi nào cần được bảo vệ.
- Không xác định được rủi ro nghiệp vụ, bảo mật hoặc dữ liệu mà lỗi có thể gây ra.
- Không biết build nào chứa lỗi, build nào đã được sửa hoặc artifact nào đã triển khai.
- Không thể tái hiện do thiếu môi trường, cấu hình, dữ liệu và phiên bản.
- Không biết test nào phát hiện lỗi và test nào cần chạy lại sau khi sửa.
- Đóng lỗi khi chỉ xác nhận một màn hình đã hoạt động, trong khi tác động dữ liệu vẫn còn.
- Không chứng minh được một release đã xử lý các lỗi trọng yếu.
- Khó phân tích lỗi tái diễn, thành phần có vấn đề hoặc khoảng trống kiểm thử.

Liên kết truy vết giúp chuyển báo cáo lỗi từ một ghi chú đơn lẻ thành hồ sơ có thể điều tra và kiểm chứng. Khi có thay đổi, nhóm có thể đi từ yêu cầu đến test và build; khi phát hiện lỗi, nhóm có thể đi ngược từ bằng chứng đến yêu cầu, rủi ro và phạm vi phiên bản.

## 2. Mô hình liên kết giữa lỗi, yêu cầu, rủi ro, build và bằng chứng

Một mô hình đơn giản có thể gồm các đối tượng:

- **Requirement:** yêu cầu chức năng, phi chức năng, quy tắc nghiệp vụ hoặc tiêu chí chấp nhận.
- **Risk:** hậu quả và khả năng xảy ra nếu yêu cầu không được đáp ứng.
- **Defect:** hành vi sai hoặc sai lệch đã được ghi nhận.
- **Build/Release:** phiên bản mã nguồn, artifact và gói triển khai liên quan.
- **Test case/test run:** kịch bản phát hiện hoặc xác minh lỗi.
- **Evidence:** log, ảnh, video, request/response, trace, dữ liệu và kết quả thực thi.
- **Change:** commit, pull request, migration hoặc cấu hình được thay đổi để sửa lỗi.
- **Environment:** môi trường, cấu hình và phụ thuộc nơi lỗi xảy ra hoặc được xác minh.

### 2.1. Sơ đồ truy vết khái quát

~~~mermaid
flowchart TD
    REQ[Yêu cầu / tiêu chí chấp nhận] --> RISK[Rủi ro liên quan]
    REQ --> TEST[Test case / test objective]
    RISK --> DEF[Defect]
    TEST -->|phát hiện| DEF
    DEF --> EVID[Bằng chứng phát hiện]
    DEF --> BUILD[Bản build bị ảnh hưởng]
    DEF --> CHANGE[Thay đổi sửa lỗi]
    CHANGE --> FIXBUILD[Bản build chứa bản sửa]
    FIXBUILD --> RETEST[Retest / regression run]
    RETEST --> FIXEVID[Bằng chứng xác minh]
    BUILD --> ENV[Môi trường và cấu hình]
    EVID --> ENV
~~~

Sơ đồ minh họa các liên kết quan trọng. Trong hệ thống thực tế, một defect có thể liên kết nhiều requirement, risk, test run, build và evidence. Không nên ép mọi quan hệ thành một-một nếu sản phẩm có nhiều thành phần hoặc nhiều phiên bản.

### 2.2. Quan hệ truy vết cần duy trì

| Từ đối tượng | Đến đối tượng | Câu hỏi cần trả lời |
|---|---|---|
| Defect | Requirement | Hành vi nào không đáp ứng yêu cầu? |
| Defect | Risk | Nếu lỗi xảy ra, hậu quả nào có thể phát sinh? |
| Defect | Build | Phiên bản nào bị ảnh hưởng hoặc đã chứa bản sửa? |
| Defect | Evidence | Bằng chứng nào xác nhận biểu hiện và điều kiện lỗi? |
| Defect | Test case/test run | Test nào phát hiện, tái hiện hoặc xác minh lỗi? |
| Defect | Change | Commit hoặc thay đổi nào được cho là sửa nguyên nhân? |
| Build | Artifact | Gói triển khai chính xác nào được tạo từ mã nguồn nào? |
| Test run | Environment | Kiểm tra chạy ở đâu, với cấu hình và dữ liệu nào? |
| Requirement | Risk/Test | Yêu cầu được bảo vệ bởi rủi ro và kiểm tra nào? |

Mối liên kết phải có ý nghĩa. Việc gắn một defect vào hàng chục requirement chung chung không tạo ra truy vết tốt. Cần ghi rõ phần yêu cầu bị vi phạm và lý do rủi ro liên quan.

## 3. Liên kết defect với yêu cầu

Yêu cầu cung cấp căn cứ để xác định hành vi nào là đúng. Khi phát hiện lỗi, người báo cáo cần xác định yêu cầu hoặc tiêu chí chấp nhận bị vi phạm. Nếu yêu cầu chưa rõ, cần ghi nhận sự mơ hồ thay vì tự đặt ra kết quả mong đợi.

### 3.1. Các loại yêu cầu có thể liên quan

- **Yêu cầu chức năng:** sản phẩm phải thực hiện một hành động hoặc quy trình.
- **Quy tắc nghiệp vụ:** điều kiện, giới hạn, tính toán hoặc trạng thái cần được tuân thủ.
- **Yêu cầu phi chức năng:** hiệu năng, độ sẵn sàng, bảo mật, khả năng sử dụng hoặc tương thích.
- **Yêu cầu giao diện/hợp đồng:** schema API, mã lỗi, event format hoặc hành vi tích hợp.
- **Yêu cầu dữ liệu:** tính toàn vẹn, lưu trữ, quyền truy cập, thời hạn và quy tắc chuyển đổi.
- **Tiêu chí chấp nhận:** điều kiện cụ thể để xác nhận một tính năng hoặc thay đổi hoàn tất.

### 3.2. Ghi rõ phần yêu cầu bị vi phạm

Ví dụ, yêu cầu “người dùng chỉ được xem đơn hàng thuộc tenant đang hoạt động của mình” có thể được phân rã thành:

- Người dùng phải có tài khoản hợp lệ.
- Membership trong tenant phải đang hoạt động.
- Người dùng phải có quyền đọc đơn hàng.
- Đơn hàng phải thuộc đúng tenant được chọn.
- Truy vấn danh sách và truy vấn chi tiết phải áp dụng cùng ranh giới quyền.

Nếu defect chỉ xảy ra ở endpoint chi tiết, hãy liên kết đến tiêu chí về phạm vi tenant và quyền đọc tài nguyên. Không cần gắn mọi yêu cầu liên quan đến đăng nhập hoặc giao diện nếu chúng không bị ảnh hưởng.

### 3.3. Khi yêu cầu thay đổi hoặc mơ hồ

Một số lỗi được báo cáo vì người kiểm thử hiểu hành vi khác với sản phẩm. Trước khi kết luận, cần xác định:

- Yêu cầu có phiên bản hoặc ngày hiệu lực nào?
- Quy tắc hiện tại đã được phê duyệt chưa?
- Hành vi thực tế có nằm trong phạm vi hỗ trợ không?
- Đây là lỗi triển khai, thiếu yêu cầu hay đề xuất cải tiến?
- Có quyết định sản phẩm hoặc kiến trúc nào giải thích khác biệt không?

Nếu chưa có căn cứ, defect có thể được đặt ở trạng thái cần làm rõ. Không nên tạo test hồi quy để bảo vệ một kỳ vọng chưa được thống nhất.

### 3.4. Truy vết hai chiều

Truy vết xuôi từ requirement đến defect giúp biết yêu cầu nào có lỗi đang mở. Truy vết ngược từ defect về requirement giúp biết lỗi ảnh hưởng đến cam kết sản phẩm nào.

Hai chiều này hữu ích khi:

- Đánh giá tác động của thay đổi yêu cầu.
- Xác định các test cần chạy lại.
- Chuẩn bị release readiness report.
- Điều tra lỗi lọt qua.
- Chứng minh một yêu cầu quan trọng đã được xử lý.

## 4. Liên kết defect với rủi ro

Yêu cầu cho biết sản phẩm cần làm gì; rủi ro mô tả hậu quả nếu hành vi đó sai hoặc không được đáp ứng. Hai defect có cùng biểu hiện kỹ thuật có thể có mức độ rủi ro khác nhau tùy dữ liệu, người dùng, giao dịch và phạm vi ảnh hưởng.

### 4.1. Thông tin rủi ro cần ghi

Một hồ sơ rủi ro có thể bao gồm:

- Tình huống gây ra rủi ro.
- Tài sản, quy trình hoặc nhóm người dùng bị ảnh hưởng.
- Hậu quả về nghiệp vụ, dữ liệu, tài chính, bảo mật hoặc vận hành.
- Khả năng xảy ra và mức phơi nhiễm.
- Biện pháp phòng ngừa hoặc phát hiện hiện có.
- Chủ sở hữu rủi ro.
- Mức chấp nhận và điều kiện escalation.

Defect nên liên kết đến rủi ro cụ thể mà nó làm tăng hoặc hiện thực hóa. Một lỗi hiển thị nhỏ có thể có tác động thấp; một lỗi tương tự ở màn hình xác nhận thanh toán có thể làm người dùng thực hiện giao dịch sai.

### 4.2. Severity, priority và risk không giống nhau

| Khái niệm | Ý nghĩa | Ví dụ câu hỏi |
|---|---|---|
| Severity | Mức độ nghiêm trọng của tác động do lỗi gây ra. | Lỗi có làm mất dữ liệu, lộ thông tin hoặc ngừng luồng cốt lõi không? |
| Priority | Mức độ ưu tiên xử lý theo thời gian và nhu cầu kinh doanh. | Cần sửa trước release nào? |
| Risk | Mức độ rủi ro tổng hợp từ khả năng xảy ra và hậu quả. | Tình huống này có thể xảy ra với ai và hậu quả là gì? |
| Impact | Phạm vi hoặc mức tác động thực tế/tiềm tàng. | Bao nhiêu tenant, giao dịch hoặc người dùng bị ảnh hưởng? |
| Urgency | Mức độ cần hành động ngay. | Có cần dừng release hoặc áp dụng giảm thiểu tức thời không? |

Không nên tự động suy priority từ severity. Một lỗi severity cao trong tính năng chưa phát hành có thể cần xử lý theo kế hoạch; một lỗi severity trung bình đang ảnh hưởng diện rộng có thể cần ưu tiên khẩn cấp.

### 4.3. Liên kết với risk register

Khi tổ chức có risk register, defect nên tham chiếu ID rủi ro thay vì chép lại nội dung rủi ro ở nhiều nơi. Hồ sơ defect vẫn cần mô tả tác động cụ thể của lần phát hiện này.

Nếu defect làm lộ một rủi ro chưa được ghi nhận, cần tạo hoặc cập nhật risk record theo quy trình. Không nên chỉ tăng severity của defect rồi cho rằng toàn bộ rủi ro đã được quản lý.

## 5. Liên kết defect với bản build, commit và artifact

Build provenance giúp trả lời phiên bản nào có lỗi, bản sửa nằm ở đâu và artifact nào đã được triển khai. Chỉ ghi “bản mới nhất” hoặc “staging hôm qua” là không đủ để tái hiện.

### 5.1. Thông tin phiên bản cần ghi

Tùy hệ thống, hồ sơ nên lưu:

- Tên sản phẩm hoặc service.
- Version/build number.
- Commit SHA hoặc revision.
- Pull request/merge request liên quan.
- Branch hoặc release branch.
- Artifact ID, digest hoặc image tag bất biến.
- Phiên bản dependency quan trọng.
- Database schema/migration version.
- Feature flag và cấu hình có ảnh hưởng.
- Thời điểm build và triển khai.

Không nên chỉ dùng tag có thể bị ghi đè như latest làm định danh artifact. Digest hoặc ID bất biến giúp xác định đúng gói đã chạy.

### 5.2. Phân biệt build phát hiện lỗi và build xác minh bản sửa

Một defect có thể có nhiều mốc build:

| Mốc | Ý nghĩa |
|---|---|
| First affected build | Build đầu tiên được xác nhận có lỗi. |
| Last known good build | Build gần nhất đã được xác minh không có lỗi. |
| Detection build | Build mà kiểm thử hoặc người dùng phát hiện lỗi. |
| Fix candidate build | Build chứa thay đổi được cho là sửa lỗi. |
| Verified fixed build | Build đã chạy retest/regression và có bằng chứng đạt. |
| Deployed build | Artifact thực tế đã được triển khai vào môi trường mục tiêu. |

Các mốc này không phải lúc nào cũng trùng nhau. Lỗi có thể đã tồn tại nhiều phiên bản trước khi được phát hiện. Bản sửa có thể được merge nhưng chưa nằm trong artifact đã triển khai.

### 5.3. Ghi phạm vi phiên bản bị ảnh hưởng

Nếu chưa biết build đầu tiên có lỗi, ghi rõ phạm vi chưa xác định. Có thể thu hẹp bằng:

- So sánh build gần nhất đã đạt và build đầu tiên thất bại.
- Kiểm tra commit hoặc migration thay đổi.
- Chạy lại test trên các artifact đã lưu.
- Đối chiếu cấu hình và feature flag.
- Xác nhận các phiên bản đang được hỗ trợ có cùng hành vi không.

Không nên kết luận lỗi chỉ ảnh hưởng một build khi chưa kiểm tra các nhánh hoặc artifact có chung thành phần.

## 6. Liên kết defect với môi trường và cấu hình

Cùng một build có thể hoạt động khác nhau giữa local, integration, staging và production do cấu hình, dữ liệu, phụ thuộc hoặc topology.

Thông tin môi trường có thể gồm:

- Environment ID và vùng triển khai.
- Hệ điều hành, runtime, container image.
- Phiên bản database, broker, cache và dịch vụ phụ thuộc.
- Cấu hình ứng dụng có liên quan.
- Feature flag, tenant plan và quyền tài khoản.
- Locale, múi giờ và định dạng dữ liệu.
- Tình trạng mạng, proxy, TLS và chứng thư.
- Quy mô dữ liệu, tải và số instance.
- Thời điểm chạy và trạng thái hệ thống.

### 6.1. Tách build khỏi environment

Build xác định mã và artifact; environment xác định điều kiện thực thi. Cùng một artifact có thể được triển khai vào nhiều môi trường. Nếu chỉ lưu environment mà không lưu build, nhóm không biết mã nào đã chạy. Nếu chỉ lưu build mà không lưu environment, nhóm không thể tái hiện khác biệt cấu hình.

### 6.2. Ghi cấu hình có liên quan, không sao chép bí mật

Ghi tên feature flag, giá trị cấu hình, phiên bản policy hoặc mã định danh cấu hình cần thiết. Không ghi password, token, private key hoặc secret thật vào defect. Có thể dùng mã tham chiếu tới secret version hoặc hệ thống quản lý bí mật.

### 6.3. Ghi thời điểm và điều kiện dữ liệu

Với lỗi liên quan đến thời gian, concurrency hoặc dữ liệu, cần lưu:

- Timestamp và múi giờ.
- Mã tenant, user hoặc transaction đã được giả lập/ẩn danh.
- Trạng thái dữ liệu trước khi thực hiện.
- Các thao tác xảy ra đồng thời.
- Correlation ID hoặc trace ID.
- Cách reset hoặc tạo lại dữ liệu.

Những thông tin này giúp phân biệt lỗi logic với lỗi do trạng thái cũ, race condition hoặc khác biệt môi trường.

## 7. Thu thập và quản lý bằng chứng

Evidence là căn cứ để người khác xác minh biểu hiện lỗi và đánh giá bản sửa. Bằng chứng tốt cần liên quan trực tiếp đến mục tiêu, có nguồn gốc rõ, đủ ngữ cảnh và có thể truy xuất.

### 7.1. Các loại bằng chứng

| Loại bằng chứng | Dùng để chứng minh | Lưu ý |
|---|---|---|
| Steps to reproduce | Điều kiện và thao tác dẫn đến lỗi. | Ngắn gọn, có thể lặp lại. |
| Screenshot/video | Biểu hiện giao diện hoặc trình tự thao tác. | Kèm phiên bản, thời điểm và trạng thái trước đó. |
| Application log | Luồng xử lý và lỗi trong ứng dụng. | Có correlation ID, tránh dữ liệu nhạy cảm. |
| Request/response | Hợp đồng API và dữ liệu trao đổi. | Loại bỏ token và thông tin cá nhân. |
| Trace/span | Đường đi qua nhiều dịch vụ. | Giữ trace ID và thời gian. |
| Database evidence | Trạng thái dữ liệu trước/sau. | Dùng dữ liệu test hoặc bản trích xuất đã kiểm soát. |
| Test report | Test case, kết quả, assertion và lần chạy. | Liên kết đúng build và môi trường. |
| Metrics/profile | Hiệu năng, tài nguyên và điểm nghẽn. | Ghi cấu hình tải và cách đo. |
| Security finding | Điều kiện, tác động và bằng chứng kiểm tra bảo mật. | Lưu theo quyền truy cập hạn chế. |

### 7.2. Bằng chứng cần có ngữ cảnh

Một ảnh chụp màn hình không có phiên bản hoặc bước trước đó có thể không đủ để tái hiện. Một log exception không có request ID có thể không liên kết được với giao dịch. Một báo cáo test không ghi commit có thể thuộc build khác.

Mỗi bằng chứng quan trọng nên liên kết với:

- Defect ID.
- Build/commit hoặc artifact.
- Environment ID.
- Test case và test run nếu có.
- Thời điểm.
- Người hoặc hệ thống thu thập.
- Mô tả nội dung và mục đích.
- Quyền truy cập và thời hạn lưu nếu cần.

### 7.3. Bảo vệ dữ liệu và tính toàn vẹn

Không đưa thông tin xác thực, dữ liệu cá nhân hoặc dữ liệu khách hàng thật vào ảnh, log hoặc attachment nếu không cần thiết. Dùng dữ liệu tổng hợp, ẩn danh hoặc mã tham chiếu. Với bằng chứng nhạy cảm, giới hạn người xem và tuân thủ chính sách lưu trữ.

Nếu cần bảo đảm bằng chứng không bị thay đổi, có thể lưu digest, thời gian thu thập và vị trí lưu trữ được kiểm soát. Không cần biến mọi screenshot thành hồ sơ pháp chứng; mức bảo vệ nên tương xứng với loại lỗi và yêu cầu quản trị.

## 8. Ghi defect sao cho có thể tái hiện và truy vết

Một defect report cần giúp người tiếp nhận hiểu điều gì sai, căn cứ nào cho kết quả mong đợi và điều kiện nào tạo ra kết quả thực tế.

### 8.1. Cấu trúc báo cáo đề xuất

~~~text
Defect ID:
Tiêu đề:
Trạng thái:
Severity:
Priority:
Requirement ID / tiêu chí chấp nhận:
Risk ID:
Service/component:
Affected build / commit / artifact:
Environment / cấu hình:
Test case / test run:
Điều kiện ban đầu:
Dữ liệu và trạng thái liên quan:
Các bước tái hiện:
Kết quả mong đợi:
Kết quả thực tế:
Tần suất tái hiện:
Tác động và phạm vi ảnh hưởng:
Bằng chứng / liên kết:
Nguyên nhân (khi đã xác nhận):
Change / pull request sửa lỗi:
Fix candidate build:
Verified fixed build:
Người sở hữu:
Ghi chú rủi ro còn lại:
~~~

Không phải mọi trường đều cần điền ngay lúc phát hiện. Nếu chưa biết nguyên nhân hoặc build đầu tiên có lỗi, ghi “chưa xác định” và giao người điều tra. Tránh suy đoán như thể đó là sự thật đã được xác nhận.

### 8.2. Viết tiêu đề có thông tin

Tiêu đề nên mô tả đối tượng, điều kiện và biểu hiện. Ví dụ:

- “API chi tiết đơn hàng trả dữ liệu tenant khác khi dùng ID hợp lệ”
- “Migration không giữ trạng thái membership bị đình chỉ trên build 2.8.14”
- “Retry thanh toán tạo giao dịch thứ hai khi phản hồi đầu tiên bị timeout”

Tránh tiêu đề chung như “Không hoạt động”, “Lỗi nghiêm trọng” hoặc “Bug mới”. Mức severity và priority nên là trường riêng.

### 8.3. Phân biệt sự kiện, giả thuyết và kết luận

Báo cáo cần tách:

- **Quan sát:** điều đã xảy ra và bằng chứng trực tiếp.
- **Giả thuyết:** nguyên nhân có thể giải thích biểu hiện.
- **Kết luận:** nguyên nhân đã được xác minh qua điều tra.
- **Phạm vi chưa rõ:** điều chưa đủ bằng chứng để khẳng định.

Ví dụ: “Response trả HTTP 500” là quan sát. “Có thể do connection pool cạn” là giả thuyết. Chỉ khi log và thử nghiệm xác nhận mới kết luận connection pool là nguyên nhân.

## 9. Vòng đời defect và các điểm kiểm soát truy vết

Tên trạng thái có thể khác giữa các công cụ, nhưng vòng đời cần thể hiện rõ trách nhiệm và điều kiện chuyển trạng thái.

~~~mermaid
stateDiagram-v2
    [*] --> New
    New --> Triaged
    Triaged --> Accepted
    Triaged --> Rejected
    Triaged --> NeedInfo
    NeedInfo --> Triaged
    Accepted --> InProgress
    InProgress --> Fixed
    Fixed --> Retest
    Retest --> Closed
    Retest --> Reopened
    Reopened --> InProgress
    Accepted --> Deferred
    Deferred --> InProgress
    Rejected --> [*]
    Closed --> [*]
~~~

### 9.1. New và triage

Khi tạo defect, kiểm tra tính đầy đủ, khả năng tái hiện, yêu cầu liên quan, build và bằng chứng. Triage xác định:

- Đây có phải defect hợp lệ không?
- Có trùng với defect đã tồn tại không?
- Mức severity và priority là gì?
- Requirement và risk nào bị ảnh hưởng?
- Component owner và người xử lý là ai?
- Có cần chặn release hoặc thông báo incident không?

### 9.2. Accepted và in progress

Khi defect được chấp nhận, gán owner và kế hoạch xử lý. Liên kết thay đổi mã, pull request hoặc migration khi bắt đầu sửa. Nếu nguyên nhân liên quan nhiều dịch vụ, cần ghi rõ các phần việc và người phối hợp.

### 9.3. Fixed và retest

Trạng thái Fixed chỉ cho biết có thay đổi được cho là sửa lỗi. Nó chưa chứng minh lỗi đã biến mất. Cần xác định fix candidate build, test xác minh và môi trường phù hợp.

Retest cần dùng điều kiện gây lỗi ban đầu hoặc một trường hợp tương đương. Nếu lỗi phụ thuộc dữ liệu, cần tạo lại trạng thái dữ liệu. Nếu lỗi phụ thuộc build, phải chạy đúng artifact có bản sửa.

### 9.4. Closed hoặc reopened

Chỉ đóng khi:

- Test xác minh đạt.
- Bằng chứng gắn với đúng build và môi trường.
- Các tác động phụ quan trọng đã được kiểm tra.
- Không còn điều kiện mở lại theo tiêu chí đã thống nhất.
- Requirement và risk traceability được cập nhật.

Nếu lỗi vẫn xuất hiện, mở lại defect hoặc tạo defect liên quan theo quy trình. Không đóng chỉ vì commit đã merge hoặc trạng thái ticket được chuyển sang Fixed.

### 9.5. Rejected, duplicate và deferred

- **Rejected:** bằng chứng cho thấy đây không phải lỗi hoặc hành vi thực tế phù hợp yêu cầu.
- **Duplicate:** đã có defect khác quản lý cùng một vấn đề; liên kết đến defect gốc và giữ bằng chứng mới nếu có giá trị.
- **Deferred:** quyết định chưa sửa trong phiên bản hiện tại; cần ghi rủi ro, lý do, người chấp nhận và mốc xem xét.

Các trạng thái này cần có lý do rõ ràng. “Không sửa” không đồng nghĩa “không có rủi ro”.

## 10. Liên kết test case và test run với defect

Test case mô tả cách kiểm tra; test run ghi nhận một lần thực thi cụ thể. Hai đối tượng này có vai trò khác nhau.

- Một test case có thể được chạy nhiều lần trên nhiều build.
- Một test run có thể phát hiện một hoặc nhiều defect.
- Một defect có thể được phát hiện bởi nhiều test case hoặc nhiều môi trường.
- Một test có thể xác minh bản sửa của nhiều defect nếu các mục tiêu thực sự liên quan.

Khi liên kết, cần lưu ID test case, run ID, kết quả, thời gian, build và environment. Không chỉ gắn tên suite chung chung.

### 10.1. Phân biệt phát hiện, retest và regression

- **Detection run:** lần chạy đầu tiên phát hiện lỗi.
- **Retest run:** lần chạy xác minh lỗi cụ thể đã được sửa.
- **Regression run:** lần chạy kiểm tra các hành vi liên quan không bị ảnh hưởng bởi thay đổi.
- **Release verification:** lần chạy trên artifact hoặc môi trường release để xác nhận trạng thái trước/sau triển khai theo quy trình.

Các lần chạy nên được liên kết riêng để biết test nào phát hiện, test nào xác minh bản sửa và test nào cung cấp bằng chứng hồi quy.

### 10.2. Tạo test hồi quy từ defect

Khi lỗi đã được xác nhận và có mục tiêu ổn định, nhóm nên đánh giá việc tạo hoặc cập nhật test hồi quy:

1. Xác định điều kiện tối thiểu gây lỗi.
2. Viết assertion cho bất biến hoặc hành vi cần bảo vệ.
3. Chọn tầng kiểm thử phù hợp với nguyên nhân.
4. Xác nhận test thất bại trên phiên bản lỗi nếu có thể.
5. Xác nhận test đạt trên bản sửa.
6. Liên kết test với defect, requirement và risk.
7. Đưa test vào pipeline phù hợp.

Không phải mọi defect đều cần tự động hóa. Một số lỗi cần kiểm tra thủ công, chuyên gia đánh giá hoặc giám sát vận hành; nhưng quyết định đó vẫn cần được ghi lại.

## 11. Liên kết thay đổi sửa lỗi và bản build xác minh

Một defect có thể được sửa qua nhiều commit hoặc pull request. Cần duy trì liên kết để biết thay đổi nào giải quyết nguyên nhân và artifact nào đã được xác minh.

### 11.1. Change traceability

Ghi nhận:

- Pull request hoặc change ID.
- Commit SHA chứa bản sửa.
- Thành phần và file hoặc migration liên quan.
- Review và approval nếu có.
- Test được thêm hoặc cập nhật.
- Build được tạo từ commit.
- Artifact digest hoặc package ID.
- Release chứa bản sửa.

Không nên liên kết defect với một pull request chỉ vì nó cùng thời điểm. Cần xác nhận thay đổi thực sự xử lý nguyên nhân hoặc có liên quan đến bản sửa.

### 11.2. Một lỗi có thể cần nhiều thay đổi

Ví dụ, lỗi giao dịch trùng có thể cần:

- Thay đổi API để nhận idempotency key.
- Thay đổi database constraint.
- Thay đổi client retry behavior.
- Thay đổi logging để ghi correlation ID.
- Bổ sung integration test cho request đồng thời.

Liên kết tất cả thay đổi liên quan và ghi rõ vai trò của từng phần. Nếu một thay đổi chỉ giảm triệu chứng nhưng chưa xử lý nguyên nhân gốc, cần ghi nhận rủi ro còn lại.

### 11.3. Xác minh artifact thực tế

Build thành công không tự chứng minh artifact được triển khai là artifact đã kiểm thử. Cần xác nhận:

- Artifact được tạo từ commit có bản sửa.
- Digest hoặc ID không bị thay đổi.
- Release pipeline lấy đúng artifact.
- Migrations và cấu hình tương ứng đã được áp dụng.
- Smoke hoặc verification test chạy trên phiên bản đã triển khai.
- Kết quả được liên kết với release ID.

## 12. Quản lý bằng chứng theo mức độ rủi ro

Không phải mọi defect cần cùng mức độ bằng chứng. Một lỗi hiển thị đơn giản có thể chỉ cần steps và screenshot; một lỗi mất dữ liệu hoặc truy cập trái phép cần bằng chứng có thể xác minh chặt chẽ hơn.

### 12.1. Bằng chứng tối thiểu theo loại lỗi

| Loại lỗi | Bằng chứng thường cần |
|---|---|
| UI/rendering | Screenshot/video, viewport, browser/version, steps và expected result. |
| API/contract | Request/response đã ẩn bí mật, schema/version, status và correlation ID. |
| Data integrity | Trạng thái trước/sau, khóa định danh giả lập, transaction/log và truy vấn xác minh. |
| Performance | Workload, cấu hình tài nguyên, percentile, throughput, error rate và thời gian đo. |
| Security/access control | Vai trò, phạm vi quyền, tài nguyên thử nghiệm, request/response và tác động dữ liệu. |
| Concurrency | Trình tự hoặc đồng bộ thao tác, số request, ID giao dịch, trạng thái cuối và trace. |
| Deployment/configuration | Build/artifact, environment, cấu hình liên quan, rollout event và health check. |

### 12.2. Giữ bằng chứng gốc và kết quả phân tích

Khi có thể, giữ bản gốc không chỉnh sửa của log hoặc báo cáo trong hệ thống lưu trữ được kiểm soát. Nếu cần che thông tin nhạy cảm, lưu bản đã xử lý và ghi rõ việc biến đổi. Không sửa ảnh hoặc log theo cách làm thay đổi ý nghĩa sự kiện.

### 12.3. Thời hạn lưu và quyền truy cập

Thời hạn lưu bằng chứng nên phù hợp với chính sách chất lượng, bảo mật và tuân thủ. Bằng chứng nhạy cảm cần quyền truy cập giới hạn. Khi defect đóng, không tự động xóa mọi evidence nếu vẫn cần cho audit, phân tích xu hướng hoặc điều tra tái diễn.

## 13. Phân tích phạm vi ảnh hưởng bằng truy vết

Khi defect được phát hiện, truy vết giúp xác định nơi cần kiểm tra thêm.

### 13.1. Từ defect đi đến thành phần và build

- Thành phần nào tạo ra hành vi sai?
- Các service hoặc consumer nào phụ thuộc vào thành phần đó?
- Những build hoặc release nào dùng cùng phiên bản?
- Các môi trường nào đang chạy artifact bị ảnh hưởng?
- Có feature flag hoặc cấu hình làm thay đổi mức phơi nhiễm không?

### 13.2. Từ defect đi đến yêu cầu và rủi ro

- Yêu cầu nào bị vi phạm?
- Có tiêu chí chấp nhận nào chưa được kiểm tra?
- Rủi ro có ảnh hưởng đến dữ liệu, bảo mật hoặc giao dịch không?
- Có nhóm người dùng hoặc tenant đặc biệt bị ảnh hưởng?
- Có rủi ro liên quan nào cần đánh giá lại?

### 13.3. Từ defect đi đến test và bằng chứng

- Test nào đã phát hiện lỗi?
- Test nào cùng mục tiêu có thể bị ảnh hưởng?
- Có test nào cần bổ sung hoặc sửa?
- Test nào cần chạy trên các build liên quan?
- Bằng chứng nào xác nhận bản sửa và không gây hồi quy?

Phân tích tác động cần tránh chạy mọi test một cách máy móc. Dựa trên quan hệ thành phần, rủi ro và yêu cầu để chọn phạm vi kiểm tra, đồng thời giữ các gate bắt buộc.

## 14. Ví dụ thực tế: lỗi truy cập chéo tenant

Một người dùng thuộc tenant Alpha gọi API chi tiết hồ sơ bằng ID của hồ sơ thuộc tenant Beta. API trả về dữ liệu thành công. Nhóm cần liên kết lỗi với các đối tượng liên quan.

### 14.1. Hồ sơ truy vết

| Đối tượng | Liên kết ví dụ |
|---|---|
| Defect | DEF-4821 — API trả dữ liệu hồ sơ ngoài tenant. |
| Requirement | REQ-SEC-014 — Người dùng chỉ truy cập tài nguyên thuộc tenant được cấp quyền. |
| Risk | RISK-DATA-003 — Rò rỉ dữ liệu giữa khách hàng. |
| Detection test | API-ACL-021 — Truy cập hồ sơ bằng user tenant Alpha và resource tenant Beta. |
| Detection build | Build 5.14.2, commit a1b2c3d (giá trị minh họa). |
| Environment | Staging, hai tenant dữ liệu tổng hợp, cấu hình policy tương ứng. |
| Evidence | Request/response đã ẩn dữ liệu, trace ID, trạng thái hồ sơ trước/sau. |
| Change | PR-917 — Bổ sung điều kiện tenant trong lớp truy vấn. |
| Fix candidate | Build 5.14.3, artifact digest được ghi nhận. |
| Retest | API-ACL-021 đạt trên build 5.14.3. |
| Regression | Test danh sách, export và truy vấn chi tiết đều xác minh tenant boundary. |

Các mã và phiên bản trên chỉ minh họa cấu trúc hồ sơ. Một defect thực tế cần dùng ID và build có thật trong hệ thống quản lý dự án.

### 14.2. Các bước xử lý

1. Xác nhận yêu cầu và risk liên quan, đánh giá mức độ ảnh hưởng.
2. Lưu request, response, trace và dữ liệu thử nghiệm để tái hiện.
3. Xác định build và artifact có lỗi, kiểm tra các môi trường hoặc release dùng cùng thành phần.
4. Điều tra nguyên nhân, xác nhận truy vấn thiếu điều kiện tenant.
5. Liên kết PR và commit sửa lỗi.
6. Tạo build mới và xác minh đúng artifact.
7. Chạy retest cho endpoint chi tiết.
8. Chạy regression cho danh sách, tìm kiếm, export và các đường truy cập liên quan.
9. Cập nhật trạng thái defect sau khi bằng chứng đạt.
10. Rà soát risk record và test coverage để ngăn lỗi tương tự.

### 14.3. Điều kiện đóng lỗi

Không đóng chỉ vì API trả 403 sau bản sửa. Cần xác minh response không chứa dữ liệu nhạy cảm, không có tác dụng phụ trái phép, các đường truy cập liên quan cũng được bảo vệ và bản build được xác minh là bản sẽ phát hành.

## 15. Báo cáo và truy vấn dữ liệu defect

Dữ liệu liên kết có thể hỗ trợ nhiều báo cáo:

- Defect đang mở theo requirement hoặc risk.
- Defect severity cao theo build hoặc release.
- Build có defect chưa xác minh bản sửa.
- Defect không có test run hoặc evidence.
- Defect đã fixed nhưng chưa retest.
- Defect reopened hoặc tái diễn.
- Requirement có nhiều defect nhưng ít test bảo vệ.
- Component có tỷ lệ defect cao.
- Defect được phát hiện sau release.
- Ngoại lệ hoặc deferred defect còn hiệu lực.

### 15.1. Kiểm tra chất lượng dữ liệu truy vết

Một báo cáo chỉ đáng tin khi dữ liệu đầu vào được duy trì:

- ID liên kết tồn tại và không trỏ đến đối tượng đã xóa.
- Trạng thái và thời gian cập nhật nhất quán.
- Build và artifact được định danh bất biến.
- Test run có kết quả và môi trường.
- Evidence có quyền truy cập và vị trí lưu hợp lệ.
- Defect duplicate liên kết đến bản ghi gốc.
- Deferred defect có người chấp nhận rủi ro và ngày xem xét.
- Closed defect có bằng chứng xác minh.

Không nên đánh giá nhóm chỉ bằng số defect được đóng. Chất lượng truy vết, mức độ tái diễn và khả năng ngăn lỗi lọt qua cũng quan trọng.

## 16. Những sai lầm thường gặp

- **Chỉ ghi tiêu đề và ảnh chụp:** thiếu yêu cầu, build, môi trường và dữ liệu để tái hiện.
- **Liên kết mọi defect với một yêu cầu chung:** không thể xác định phần hành vi thực sự bị vi phạm.
- **Nhầm severity với priority:** ưu tiên xử lý không phản ánh đầy đủ hậu quả kỹ thuật.
- **Ghi “bản mới nhất”:** không xác định được artifact chính xác.
- **Không tách build phát hiện và build sửa:** không biết bản sửa đã được xác minh ở đâu.
- **Chỉ lưu log không có correlation ID:** khó ghép sự kiện giữa nhiều dịch vụ.
- **Không ghi cấu hình hoặc feature flag:** lỗi không tái hiện khi môi trường thay đổi.
- **Đóng lỗi ngay sau merge:** chưa chứng minh artifact đã sửa và test đã đạt.
- **Chỉ chạy retest, bỏ regression:** có thể sửa lỗi này nhưng làm hỏng hành vi lân cận.
- **Đưa bí mật vào evidence:** tạo rủi ro bảo mật và quyền riêng tư.
- **Không liên kết defect duplicate:** dữ liệu lỗi bị phân tán và báo cáo đếm trùng.
- **Không ghi rủi ro của lỗi deferred:** quyết định trì hoãn mất khả năng truy vết.
- **Dùng giả thuyết như nguyên nhân đã xác nhận:** hướng điều tra sai và báo cáo thiếu chính xác.

## 17. Checklist liên kết lỗi và bằng chứng

- [ ] Defect có ID, tiêu đề mô tả và người sở hữu.
- [ ] Hành vi mong đợi có căn cứ từ requirement hoặc tiêu chí chấp nhận.
- [ ] Requirement liên kết đúng phần bị vi phạm.
- [ ] Risk liên quan và hậu quả được ghi nhận.
- [ ] Severity, priority và impact được phân biệt.
- [ ] Build, commit, artifact và phiên bản phụ thuộc được định danh.
- [ ] Environment, cấu hình, feature flag và dữ liệu liên quan được ghi.
- [ ] Steps to reproduce và tần suất tái hiện rõ ràng.
- [ ] Evidence có thời điểm, nguồn, liên kết và ngữ cảnh.
- [ ] Bí mật và dữ liệu nhạy cảm đã được loại bỏ hoặc bảo vệ.
- [ ] Test case và detection run được liên kết.
- [ ] Change/PR và fix candidate build được liên kết khi có.
- [ ] Retest và regression run được ghi nhận riêng.
- [ ] Verified fixed build và deployed build được phân biệt.
- [ ] Defect chỉ được đóng khi tiêu chí xác minh đạt.
- [ ] Deferred hoặc ngoại lệ có người chấp nhận rủi ro và thời hạn.
- [ ] Truy vết hai chiều hỗ trợ phân tích tác động và release readiness.

## Kết luận

Liên kết lỗi với yêu cầu, rủi ro, bản build và bằng chứng giúp nhóm hiểu chính xác hành vi nào sai, hậu quả nào có thể xảy ra, phiên bản nào bị ảnh hưởng và căn cứ nào xác nhận bản sửa. Một hồ sơ defect tốt cần truy vết được đến requirement, risk, test run, environment, change và artifact; đồng thời phân biệt rõ quan sát, giả thuyết và kết luận. Chỉ đóng lỗi sau khi retest và các kiểm tra hồi quy liên quan đã cung cấp bằng chứng trên đúng build. Khi các liên kết được duy trì xuyên suốt vòng đời, nhóm có thể ưu tiên xử lý dựa trên rủi ro, tái hiện sự cố, đánh giá phạm vi phát hành và học hỏi từ lỗi đã xảy ra.
