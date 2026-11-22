# Theo dõi kết quả rà soát và chuyển vấn đề thành hành động

Rà soát tĩnh giúp phát hiện vấn đề trong yêu cầu, thiết kế, mã nguồn, cấu hình và tài liệu trước khi hoặc không cần thực thi hệ thống. Tuy nhiên, một cảnh báo trong báo cáo chỉ tạo ra giá trị khi nhóm hiểu đúng vấn đề, đánh giá mức độ rủi ro, giao người xử lý và xác minh kết quả. Nếu cảnh báo bị bỏ quên, lặp lại qua nhiều lần chạy hoặc bị đóng mà không có bằng chứng, hoạt động rà soát khó cải thiện chất lượng sản phẩm.

Theo dõi kết quả rà soát là quá trình quản lý một phát hiện từ lúc được ghi nhận đến khi có quyết định rõ ràng: sửa, theo dõi, chuyển giao, chấp nhận ngoại lệ hoặc xác nhận không phải vấn đề. Quá trình này cần liên kết phát hiện với thành phần, phiên bản, rủi ro, người chịu trách nhiệm và bằng chứng xác minh. Mục tiêu là biến thông tin từ rà soát thành hành động có thể kiểm tra và học hỏi.

## 1. Phân biệt phát hiện, lỗi và cảnh báo

Kết quả từ rà soát tĩnh có thể đến từ nhiều nguồn: rà soát mã nguồn, phân tích tĩnh, quét dependency, kiểm tra cấu hình, kiểm tra bí mật, rà soát kiến trúc hoặc kiểm tra tài liệu yêu cầu. Công cụ thường gọi kết quả là finding, issue, alert hoặc violation. Không phải kết quả nào cũng là lỗi thực tế.

Cần phân biệt:

- **Phát hiện (finding):** một kết quả cần được con người hoặc quy trình xác minh. Nó có thể là lỗi thật, rủi ro tiềm ẩn, vấn đề về quy tắc hoặc cảnh báo sai.
- **Lỗi (defect):** hành vi hoặc thuộc tính của sản phẩm không đáp ứng yêu cầu, thiết kế hoặc tiêu chí đã thống nhất.
- **Rủi ro:** khả năng một điều kiện gây ra hậu quả không mong muốn. Một phát hiện có thể biểu thị rủi ro ngay cả khi chưa tái hiện được lỗi.
- **Cảnh báo sai (false positive):** công cụ báo vấn đề nhưng khi kiểm tra theo ngữ cảnh, điều kiện bị cảnh báo không tồn tại hoặc quy tắc không áp dụng.
- **Vấn đề đã biết hoặc ngoại lệ:** phát hiện được xác nhận nhưng có quyết định theo dõi, chấp nhận tạm thời hoặc loại trừ có căn cứ và thời hạn.

Ví dụ, công cụ phát hiện một truy vấn SQL được ghép chuỗi. Đây là tín hiệu cần điều tra. Nếu dữ liệu đầu vào thực sự có thể bị kiểm soát từ bên ngoài và không được tham số hóa, phát hiện có thể là lỗ hổng. Nếu giá trị được tạo từ một hằng số an toàn và không thể chứa dữ liệu không tin cậy, cảnh báo có thể không áp dụng. Nhóm cần ghi lại căn cứ xác minh thay vì tự động coi mọi cảnh báo là lỗi hoặc bỏ qua toàn bộ quy tắc.

## 2. Thiết lập nguồn ghi nhận thống nhất

Kết quả rà soát thường đến từ nhiều công cụ và nhóm khác nhau. Nếu mỗi nhóm lưu ở một bảng tính, email hoặc bình luận riêng, việc tìm trạng thái hiện tại và tránh xử lý trùng lặp sẽ khó khăn.

Nên có một nguồn ghi nhận thống nhất, chẳng hạn hệ thống quản lý issue hoặc defect. Mỗi phát hiện có một mã định danh ổn định và liên kết đến các nguồn gốc:

- Công cụ hoặc hoạt động rà soát tạo ra phát hiện.
- Quy tắc, tiêu chuẩn hoặc tiêu chí bị vi phạm.
- Repository, module, tệp, dòng mã hoặc thành phần liên quan.
- Nhánh, commit, pull request, bản dựng hoặc phiên bản đã phân tích.
- Báo cáo, log hoặc ảnh chụp kết quả có thể truy xuất.
- Yêu cầu, rủi ro hoặc biện pháp kiểm soát liên quan.

Không nên chỉ lưu đường dẫn dòng mã nếu dòng có thể thay đổi sau commit. Hãy lưu thêm định danh commit hoặc phiên bản phân tích để người xử lý biết kết quả được tạo từ trạng thái nào. Khi tích hợp công cụ với hệ thống issue, cần giữ liên kết giữa mã phát hiện của công cụ và mã issue để đồng bộ trạng thái.

Một phát hiện có thể được tìm thấy lại ở nhiều lần chạy. Cần có quy tắc nhận diện trùng lặp dựa trên quy tắc, thành phần, vị trí hoặc dấu vết của vấn đề. Tránh tạo issue mới cho cùng một lỗi ở mọi lần quét, nhưng cũng không gộp các vấn đề khác nhau chỉ vì chúng có cùng thông báo.

## 3. Ghi đủ thông tin để người khác có thể xử lý

Một bản ghi phát hiện tốt phải giúp người nhận hiểu vấn đề mà không cần tự chạy lại toàn bộ hoạt động rà soát để đoán ý nghĩa.

Các trường nên có:

| Trường | Nội dung |
|---|---|
| Mã phát hiện | Định danh duy nhất và ổn định |
| Tiêu đề | Mô tả ngắn, nêu hành vi hoặc rủi ro |
| Nguồn | Công cụ, quy tắc, người rà soát và thời điểm |
| Thành phần | Repository, module, dịch vụ, tệp và vị trí |
| Phiên bản | Commit, nhánh, bản dựng hoặc phiên bản được rà soát |
| Mô tả | Điều kiện phát hiện, ngữ cảnh và hành vi quan sát được |
| Bằng chứng | Đoạn mã liên quan, log, kết quả phân tích hoặc ví dụ tái hiện |
| Tác động | Hậu quả có thể xảy ra với người dùng, dữ liệu hoặc vận hành |
| Mức độ nghiêm trọng | Mức ảnh hưởng nếu vấn đề xảy ra |
| Mức độ ưu tiên | Thứ tự cần xử lý theo rủi ro, thời hạn và phụ thuộc |
| Độ tin cậy | Mức chắc chắn của phát hiện và căn cứ xác minh |
| Chủ sở hữu | Người hoặc nhóm chịu trách nhiệm xử lý |
| Hạn xử lý | Mốc thời gian hoặc cam kết dịch vụ nội bộ |
| Trạng thái | Bước hiện tại trong vòng đời phát hiện |
| Quyết định và bằng chứng đóng | Cách xử lý, người phê duyệt và kết quả xác minh |

Mô tả nên nêu rõ điều kiện kích hoạt, đường đi dữ liệu hoặc thành phần liên quan. Với vấn đề bảo mật, ghi nguồn dữ liệu, ranh giới tin cậy, quyền cần có và tác động có thể xảy ra. Với vấn đề maintainability, nêu quy tắc, phần mã bị ảnh hưởng và hậu quả bảo trì dự kiến.

Không đưa mật khẩu, token, dữ liệu cá nhân hoặc bí mật vào phần mô tả hay ảnh chụp. Nếu bằng chứng chứa dữ liệu nhạy cảm, dùng dữ liệu đã che hoặc nơi lưu được kiểm soát quyền truy cập.

## 4. Phân loại và ưu tiên phát hiện

Không thể xử lý mọi phát hiện cùng lúc. Phân loại giúp định tuyến đến đúng chuyên môn; đánh giá mức độ nghiêm trọng và ưu tiên giúp quyết định thứ tự hành động.

### 4.1. Phân loại theo loại vấn đề

Một bộ phân loại có thể gồm:

- **Chức năng và logic:** điều kiện sai, xử lý trạng thái thiếu, nhánh không thể đạt hoặc tính toán sai.
- **Bảo mật và quyền riêng tư:** truy cập trái phép, xử lý đầu vào không an toàn, bí mật bị lộ hoặc dependency có lỗ hổng.
- **Độ tin cậy:** xử lý lỗi không đầy đủ, tài nguyên không được giải phóng, timeout hoặc retry không an toàn.
- **Hiệu năng và khả năng mở rộng:** thuật toán tốn kém, truy vấn không hiệu quả hoặc cấu hình giới hạn không phù hợp.
- **Chất lượng thiết kế và bảo trì:** coupling cao, trùng lặp, độ phức tạp hoặc vi phạm kiến trúc.
- **Tuân thủ và chính sách:** thiếu kiểm soát, sai cấu hình hoặc không đáp ứng quy tắc nội bộ hay nghĩa vụ đã xác nhận.
- **Tài liệu và khả năng vận hành:** thiếu hướng dẫn, thông tin lỗi hoặc dấu vết cần thiết để hỗ trợ và điều tra.

Có thể thêm nhãn theo thành phần, sản phẩm, nhóm sở hữu, loại dữ liệu hoặc giai đoạn phát hiện. Danh mục cần đủ ổn định để phân tích xu hướng nhưng không quá chi tiết đến mức người dùng không biết chọn loại nào.

### 4.2. Phân biệt severity và priority

**Severity (mức độ nghiêm trọng)** mô tả hậu quả nếu vấn đề xảy ra. **Priority (mức độ ưu tiên)** mô tả khi nào nhóm cần xử lý. Hai khái niệm có liên quan nhưng không giống nhau.

Một vấn đề có severity cao thường cần ưu tiên cao, nhưng thứ tự còn phụ thuộc khả năng khai thác, phạm vi ảnh hưởng, mức độ phơi nhiễm, thời điểm phát hành, biện pháp giảm thiểu tạm thời và nghĩa vụ phải đáp ứng. Một lỗi nhỏ nhưng chặn toàn bộ quy trình triển khai có thể cần xử lý ngay; một lỗi nghiêm trọng trong thành phần chưa được bật có thể cần kiểm soát trước khi thành phần đó được đưa vào sử dụng.

Ví dụ một thang severity:

| Mức | Ý nghĩa tham khảo | Ví dụ |
|---|---|---|
| Critical | Có thể gây mất dữ liệu nghiêm trọng, xâm phạm bảo mật diện rộng hoặc ngừng dịch vụ trọng yếu | Lộ bí mật có quyền truy cập production; bỏ qua xác thực trên API nhạy cảm |
| High | Tác động lớn đến chức năng, dữ liệu, bảo mật hoặc nhóm người dùng đáng kể | Truy cập chéo tenant trong một luồng quan trọng |
| Medium | Ảnh hưởng giới hạn hoặc có điều kiện kích hoạt cụ thể; có thể có phương án thay thế | Xử lý lỗi không đầy đủ trong một chức năng phụ |
| Low | Tác động nhỏ, chủ yếu về bảo trì hoặc trải nghiệm, không chặn luồng trọng yếu | Thông báo lỗi thiếu ngữ cảnh trong công cụ nội bộ |
| Informational | Khuyến nghị hoặc dấu hiệu cần theo dõi, chưa xác định là defect | Gợi ý giảm độ phức tạp hoặc cập nhật thư viện |

Tên mức và tiêu chí phải được tổ chức thống nhất. Không nên dùng bảng ví dụ này thay cho chính sách severity của sản phẩm hoặc tiêu chuẩn bảo mật áp dụng.

### 4.3. Xem xét độ tin cậy và khả năng khai thác

Độ tin cậy cho biết bằng chứng có hỗ trợ kết luận hay không. Khả năng khai thác mô tả điều kiện để một tác nhân hoặc tình huống kích hoạt vấn đề. Một cảnh báo có mức ảnh hưởng tiềm tàng cao nhưng độ tin cậy thấp cần được điều tra ưu tiên để xác minh, chứ không nên tự động đóng hoặc coi là lỗi đã xác nhận.

Với lỗ hổng bảo mật, cân nhắc nguồn đầu vào, quyền cần thiết, khả năng truy cập từ mạng, cấu hình triển khai, dependency thực sự được nạp và mức độ sẵn có của biện pháp giảm thiểu. Với vấn đề logic, xem đường đi thực tế, điều kiện nhánh và dữ liệu có thể xuất hiện.

### 4.4. Xác định thời hạn xử lý

Tổ chức có thể đặt mục tiêu thời gian xử lý theo severity hoặc loại rủi ro. Ví dụ, phát hiện Critical cần được triage ngay và có quyết định kiểm soát trong thời gian ngắn; phát hiện Low có thể đưa vào backlog. Mốc cụ thể cần được thống nhất theo năng lực, hợp đồng và chính sách nội bộ.

Không nên biến SLA xử lý thành lý do đóng issue vội vàng. Nếu chưa thể sửa đúng hạn, cần ghi nhận người chịu trách nhiệm, biện pháp giảm thiểu tạm thời, lý do, người chấp thuận và ngày xem xét lại.

## 5. Tổ chức buổi triage và ra quyết định

Triage là hoạt động xem xét phát hiện để xác định tính hợp lệ, mức độ ảnh hưởng, ưu tiên, người xử lý và hướng tiếp theo. Triage nên có người hiểu sản phẩm và người có chuyên môn phù hợp; các vấn đề bảo mật hoặc dữ liệu nhạy cảm cần có đại diện chịu trách nhiệm về lĩnh vực đó.

Một buổi triage hiệu quả cần trả lời:

1. Phát hiện có tái hiện hoặc có căn cứ kỹ thuật không?
2. Quy tắc hoặc yêu cầu nào bị ảnh hưởng?
3. Thành phần và phiên bản nào nằm trong phạm vi?
4. Hậu quả và điều kiện kích hoạt là gì?
5. Có phát hiện trùng lặp hoặc cảnh báo sai không?
6. Mức severity, priority và độ tin cậy là gì?
7. Cần sửa ngay, lên backlog, điều tra thêm hay xin ngoại lệ?
8. Ai chịu trách nhiệm và khi nào cần cập nhật?
9. Cần bằng chứng gì để xác minh việc xử lý?

Kết quả triage cần được ghi lại trong issue. Nếu nhóm chưa đủ thông tin, chuyển sang trạng thái cần điều tra, chỉ định người tìm hiểu và thời hạn phản hồi. Không nên để phát hiện ở trạng thái “mới” vô thời hạn mà không có chủ sở hữu.

## 6. Quản lý vòng đời của một phát hiện

Một quy trình đơn giản có thể dùng các trạng thái sau:

| Trạng thái | Ý nghĩa | Điều kiện chuyển tiếp |
|---|---|---|
| New | Vừa được ghi nhận, chưa triage | Có người xem xét và xác nhận thông tin cơ bản |
| Triaged | Đã phân loại, đánh giá và xác định hướng xử lý | Gán chủ sở hữu hoặc quyết định điều tra/ngoại lệ |
| In Progress | Đang phân tích hoặc sửa | Có thay đổi hoặc kết quả điều tra để xem xét |
| Ready for Verification | Đã có thay đổi, chờ xác minh | Có phiên bản chứa thay đổi và bằng chứng kiểm tra |
| Verified | Biện pháp xử lý đã được xác minh | Có căn cứ cho thấy vấn đề được giải quyết trong phạm vi |
| Closed | Hồ sơ được kết thúc theo quy trình | Đủ bằng chứng, quyết định và thông tin đóng |
| Reopened | Vấn đề tái xuất hiện hoặc xác minh không đạt | Quay lại phân tích và xử lý |
| Deferred / Accepted | Được hoãn hoặc chấp nhận theo quyết định | Có lý do, người phê duyệt, biện pháp và ngày xem xét |

Tên trạng thái có thể khác theo công cụ. Điều quan trọng là định nghĩa rõ ý nghĩa và điều kiện chuyển trạng thái. Ví dụ, “Resolved” có thể có nghĩa đã sửa nhưng chưa xác minh; “Closed” chỉ nên dùng khi điều kiện đóng đã đạt theo quy trình.

Trạng thái hoãn hoặc chấp nhận không nên bị hiểu là đã sửa. Cần phân biệt phát hiện đã khắc phục với rủi ro được chấp nhận có kiểm soát.

## 7. Chuyển phát hiện thành hành động có thể thực hiện

Một phát hiện chỉ trở thành công việc khi được chuyển thành hành động cụ thể. Hành động nên mô tả kết quả cần đạt, phạm vi thay đổi, người thực hiện và cách xác minh.

Ví dụ:

**Phát hiện:** API trả về thông tin tài khoản khi chỉ kiểm tra người dùng đã đăng nhập, chưa kiểm tra quyền sở hữu tài khoản.

Hành động phù hợp có thể gồm:

- Xác định tất cả endpoint và luồng truy cập cùng dữ liệu tài khoản.
- Bổ sung kiểm tra quyền ở phía máy chủ theo người dùng hoặc tenant.
- Rà soát các đường truy cập gián tiếp như export, tìm kiếm và API nội bộ.
- Viết kiểm thử cho chủ sở hữu hợp lệ, người dùng khác, quản trị viên và quyền đã bị thu hồi.
- Xác minh log không làm lộ dữ liệu nhạy cảm.
- Chạy kiểm thử hồi quy trên các luồng liên quan.

Không nên tạo một task chung chung như “fix security finding”. Task cần đủ cụ thể để người thực hiện biết phạm vi và reviewer có thể xác nhận kết quả.

Một hành động có thể chia thành nhiều task nếu cần thay đổi thiết kế, mã nguồn, cấu hình, tài liệu hoặc quy trình vận hành. Giữ liên kết từ các task đó về một phát hiện gốc để không mất khả năng theo dõi trạng thái tổng thể.

## 8. Xác minh việc sửa và đóng phát hiện

Sau khi có thay đổi, cần xác minh đúng vấn đề đã được giải quyết và không tạo ra lỗi mới.

Quy trình xác minh có thể gồm:

1. Xác định commit hoặc phiên bản chứa thay đổi.
2. Chạy lại đúng quy tắc hoặc hoạt động rà soát đã phát hiện vấn đề.
3. Kiểm tra đường đi liên quan trong điều kiện kích hoạt ban đầu.
4. Chạy kiểm thử hồi quy phù hợp với thành phần và rủi ro.
5. Kiểm tra cấu hình hoặc môi trường thực tế nếu vấn đề phụ thuộc triển khai.
6. Lưu kết quả, log hoặc bằng chứng.
7. Cập nhật trạng thái và người xác minh.

Không nên đóng chỉ vì cảnh báo biến mất khỏi báo cáo. Cảnh báo có thể biến mất do đổi tên tệp, thay đổi cấu hình quét, tắt quy tắc hoặc loại thành phần khỏi phạm vi. Hãy xác nhận nguyên nhân biến mất là thay đổi đúng, và ghi lại nếu phạm vi phân tích đã thay đổi.

Với phát hiện được đánh giá là false positive, người triage cần ghi rõ lý do và bằng chứng. Nếu công cụ hỗ trợ suppression hoặc baseline, dùng cơ chế có kiểm soát, gắn phạm vi cụ thể và thời hạn xem lại. Tránh tắt toàn bộ quy tắc chỉ vì một trường hợp không áp dụng.

Nếu vấn đề tái xuất hiện, mở lại issue hoặc tạo phát hiện mới có liên kết đến issue trước. Phân tích vì sao kiểm soát trước đó không ngăn được tái diễn: test hồi quy thiếu, cấu hình bị thay đổi, code path khác hoặc fix chưa xử lý nguyên nhân.

## 9. Quản lý ngoại lệ và cảnh báo sai có kiểm soát

Không phải mọi phát hiện đều cần sửa ngay. Một số quy tắc có thể không áp dụng với một thành phần; một số vấn đề cần thời gian chuyển đổi; một số rủi ro có thể được chấp nhận trong phạm vi nhất định. Quyết định này phải minh bạch.

Một hồ sơ ngoại lệ nên có:

- Mã phát hiện và quy tắc được miễn.
- Thành phần, tệp, phiên bản hoặc phạm vi chính xác.
- Lý do không xử lý hoặc không áp dụng.
- Bằng chứng hỗ trợ cách đánh giá.
- Rủi ro còn lại và điều kiện có thể làm rủi ro tăng.
- Biện pháp giảm thiểu tạm thời.
- Người đề xuất và người có thẩm quyền phê duyệt.
- Ngày hết hạn hoặc ngày xem xét lại.
- Điều kiện tự động mở lại, nếu công cụ hỗ trợ.

Ví dụ, một dependency có cảnh báo nhưng chỉ được dùng trong công cụ build, không có mặt trong artifact production. Nhóm cần xác minh đường sử dụng và phạm vi triển khai, ghi lại căn cứ, sau đó quyết định cập nhật hoặc chấp nhận có thời hạn theo chính sách. Không nên bỏ qua cảnh báo chỉ dựa trên tên package hoặc giả định rằng mã không được gọi.

Với cảnh báo sai, lưu lý do để tránh triage lại cùng vấn đề trong mỗi lần chạy. Tuy nhiên, khi phiên bản công cụ, quy tắc, kiến trúc hoặc cách sử dụng thay đổi, cần xem lại kết luận cũ. Một ngoại lệ không nên tồn tại vĩnh viễn mà không có người sở hữu.

## 10. Thiết lập trách nhiệm và nhịp theo dõi

Mỗi phát hiện cần một chủ sở hữu chịu trách nhiệm cập nhật trạng thái và điều phối xử lý. Chủ sở hữu không nhất thiết là người trực tiếp sửa mã; họ phải bảo đảm issue có quyết định và không bị bỏ quên.

Có thể phân vai như sau:

| Vai trò | Trách nhiệm |
|---|---|
| Người phát hiện | Cung cấp mô tả, nguồn, bằng chứng và ngữ cảnh ban đầu |
| Người triage | Xác minh, phân loại, đánh giá severity/priority và hướng xử lý |
| Chủ sở hữu thành phần | Đánh giá tác động, lập kế hoạch và điều phối sửa |
| Người thực hiện | Sửa mã, cấu hình, tài liệu hoặc quy trình theo task |
| Người xác minh | Chạy lại rà soát và kiểm tra bằng chứng xử lý |
| Chủ sở hữu rủi ro | Chấp nhận rủi ro còn lại hoặc phê duyệt ngoại lệ trong phạm vi thẩm quyền |
| Người quản lý chất lượng | Theo dõi xu hướng, quá hạn, điểm nghẽn và chất lượng quy trình |

Với nhóm nhỏ, một người có thể giữ nhiều vai trò. Với vấn đề nghiêm trọng, nên có người xác minh độc lập với người sửa khi khả thi, nhằm giảm nguy cơ bỏ sót giả định của chính người triển khai.

Nhịp theo dõi có thể gồm:

- Triage nhanh khi có phát hiện mới thuộc mức nghiêm trọng cao.
- Rà soát issue đang mở trong buổi refinement hoặc họp chất lượng định kỳ.
- Báo cáo các phát hiện quá hạn, không có chủ sở hữu hoặc chờ xác minh.
- Rà soát ngoại lệ sắp hết hạn.
- Xem xu hướng theo release, thành phần và loại vấn đề.

Không nên chờ đến cuối dự án mới xem danh sách issue. Khi phát hiện được xử lý sớm, nhóm có thể giảm chi phí sửa và tránh việc nhiều vấn đề phụ thuộc nhau tích tụ.

## 11. Đo lường hiệu quả theo dõi và chuyển vấn đề thành hành động

Chỉ số cần phản ánh cả chất lượng phát hiện và hiệu quả xử lý. Đếm tổng số cảnh báo không đủ để đánh giá quy trình.

Một số chỉ số hữu ích:

| Chỉ số | Cách hiểu | Câu hỏi quản lý |
|---|---|---|
| Phát hiện mới theo severity | Số phát hiện mới theo mức độ | Có thành phần hoặc thay đổi nào làm rủi ro tăng? |
| Tỷ lệ phát hiện được triage | Phần phát hiện đã có quyết định trên tổng số cần triage | Có backlog cảnh báo chưa được xem xét không? |
| Thời gian đến triage | Thời gian từ ghi nhận đến quyết định ban đầu | Nhóm có phản hồi đủ nhanh với vấn đề nghiêm trọng không? |
| Thời gian xử lý | Thời gian từ xác nhận đến khắc phục hoặc quyết định ngoại lệ | Vấn đề nào thường bị mắc kẹt? |
| Phát hiện quá hạn | Số issue vượt thời hạn đã thống nhất | Có thiếu năng lực, chủ sở hữu hoặc quyết định không? |
| Tỷ lệ false positive | Phần phát hiện được xác định không áp dụng hoặc sai | Quy tắc, cấu hình hoặc phạm vi công cụ có cần cải thiện? |
| Tỷ lệ tái mở | Phần issue đã đóng nhưng xuất hiện lại hoặc xác minh không đạt | Fix hoặc quy trình xác minh có đủ tốt không? |
| Tuổi của ngoại lệ | Thời gian ngoại lệ còn hiệu lực | Có rủi ro nào được chấp nhận quá lâu? |
| Lỗi lọt liên quan | Vấn đề phát hiện sau phát hành có thể đã được rà soát tĩnh tìm ra | Có khoảng trống trong quy tắc, phạm vi hoặc triage không? |

Khi tính tỷ lệ, cần thống nhất mẫu số, khoảng thời gian và cách xử lý issue trùng. Ví dụ, tỷ lệ false positive cao có thể cho thấy cấu hình công cụ chưa phù hợp, nhưng cũng có thể do nhóm thiếu thông tin để xác minh. Không nên dùng một chỉ số riêng lẻ để đánh giá hiệu suất cá nhân hoặc tạo động lực đóng issue nhanh mà không xử lý đúng.

Hãy đọc chỉ số cùng bối cảnh: thay đổi quy mô code, số lần quét, mức độ trưởng thành của công cụ, thành phần mới và loại dự án. Mục tiêu là tìm điểm nghẽn và cải thiện hệ thống làm việc.

## 12. Ví dụ: theo dõi kết quả rà soát tĩnh trong một pull request

Giả sử một công cụ phân tích mã nguồn chạy trên pull request và tạo ba phát hiện:

| Mã | Phát hiện | Đánh giá ban đầu | Hành động |
|---|---|---|---|
| ST-101 | Đầu vào API được đưa vào truy vấn SQL bằng nối chuỗi | High, cần xác minh nguồn dữ liệu | Kiểm tra luồng dữ liệu, chuyển sang truy vấn tham số hóa và thêm test |
| ST-102 | Hàm xử lý có độ phức tạp cao | Medium, ảnh hưởng bảo trì | Xem xét tách nhánh và bổ sung kiểm thử cho các đường đi |
| ST-103 | Dependency có phiên bản chứa cảnh báo bảo mật | Chưa kết luận mức áp dụng | Kiểm tra phiên bản được nạp, khả năng tiếp cận và phạm vi artifact |

Trong buổi triage, nhóm xác minh ST-101 có thể nhận dữ liệu từ request bên ngoài và chưa có tham số hóa. Chủ sở hữu API được giao sửa trước khi merge. Người thực hiện thay đổi truy vấn, bổ sung test với đầu vào chứa ký tự đặc biệt và liên kết commit với issue. Người xác minh chạy lại quy tắc phân tích, kiểm tra test và rà soát các truy vấn tương tự.

ST-102 được chuyển thành task refactor có ưu tiên phù hợp. Nhóm bổ sung test cho các nhánh trước khi thay đổi cấu trúc để bảo vệ hành vi hiện có. Sau refactor, test và rà soát được chạy lại; issue chỉ đóng khi độ phức tạp giảm theo tiêu chí nhóm đã thống nhất và không làm thay đổi kết quả nghiệp vụ.

Với ST-103, nhóm xác định dependency chỉ được dùng ở một đường build hay có nằm trong runtime artifact. Nếu có mặt trong production, cần đánh giá mức độ ảnh hưởng và kế hoạch nâng cấp. Nếu không có mặt trong artifact, vẫn ghi bằng chứng, phạm vi và quyết định theo chính sách; không tự động bỏ qua chỉ dựa trên giả định.

Kết quả cuối cùng là ba phát hiện có ba quyết định khác nhau, nhưng tất cả đều có chủ sở hữu, bằng chứng và trạng thái rõ ràng. Nhóm có thể truy lại vì sao một vấn đề được sửa, hoãn hoặc xác định không áp dụng.

## 13. Cải thiện quy trình từ dữ liệu phát hiện

Theo dõi không chỉ phục vụ đóng issue. Dữ liệu qua nhiều vòng rà soát có thể cho thấy nguyên nhân hệ thống khiến vấn đề lặp lại.

Ví dụ:

- Nhiều lỗi null handling có thể cho thấy hợp đồng dữ liệu hoặc quy ước xử lý null chưa rõ.
- Nhiều lỗi phân quyền ở các endpoint có thể cho thấy thiếu cơ chế dùng chung hoặc thiếu rà soát kiến trúc.
- Nhiều cảnh báo sai trong một thư mục có thể cho thấy phạm vi quét hoặc quy tắc cần cấu hình lại.
- Nhiều issue quá hạn ở một thành phần có thể cho thấy thiếu chủ sở hữu hoặc năng lực bảo trì.
- Nhiều lỗi tái mở có thể cho thấy tiêu chí xác minh chưa đủ hoặc fix chỉ xử lý triệu chứng.

Hãy thực hiện phân tích nguyên nhân gốc với vấn đề lặp lại hoặc có tác động lớn. Hành động cải tiến có thể là thay đổi coding standard, thêm quy tắc phân tích, cập nhật mẫu thiết kế, cải thiện đào tạo, bổ sung test hồi quy hoặc điều chỉnh quy trình review.

Mỗi hành động cải tiến nên có chủ sở hữu, thời hạn và cách đánh giá hiệu quả. Sau một số chu kỳ, xem tỷ lệ tái diễn hoặc lỗi lọt có giảm không. Nếu không, cần xem lại giả thuyết nguyên nhân và biện pháp đã chọn.

## 14. Quy trình tổng quát từ phát hiện đến hành động

Có thể dùng quy trình sau cho mỗi kết quả rà soát:

1. **Thu thập:** nhập phát hiện vào nguồn quản lý thống nhất và lưu nguồn, phiên bản, vị trí cùng bằng chứng.
2. **Khử trùng lặp:** liên kết với issue đang mở nếu đó là cùng một vấn đề.
3. **Xác minh:** kiểm tra ngữ cảnh, điều kiện kích hoạt, độ tin cậy và phạm vi ảnh hưởng.
4. **Phân loại:** gán loại vấn đề, severity, priority và trạng thái.
5. **Triage:** quyết định sửa, điều tra, chuyển giao, hoãn, chấp nhận hoặc xác định false positive.
6. **Giao việc:** chỉ định chủ sở hữu, hành động cụ thể, hạn xử lý và tiêu chí hoàn thành.
7. **Thực hiện:** sửa mã, thiết kế, cấu hình, tài liệu hoặc quy trình.
8. **Xác minh:** chạy lại rà soát và kiểm thử liên quan trên phiên bản đã sửa.
9. **Đóng hoặc mở lại:** lưu bằng chứng và quyết định; mở lại nếu vấn đề vẫn còn hoặc tái xuất hiện.
10. **Học hỏi:** phân tích xu hướng để cải thiện quy tắc, thiết kế và quy trình.

~~~mermaid
flowchart TD
    A["Kết quả rà soát tĩnh"] --> B["Ghi nhận nguồn, phiên bản và bằng chứng"]
    B --> C["Khử trùng lặp và xác minh"]
    C --> D["Triage: loại, severity, priority"]
    D --> E{"Quyết định"}
    E -->|Sửa| F["Giao chủ sở hữu và hành động"]
    F --> G["Thực hiện thay đổi"]
    G --> H["Rà soát lại và kiểm thử xác minh"]
    H --> I{"Đạt tiêu chí?"}
    I -->|Có| J["Đóng với bằng chứng"]
    I -->|Chưa| F
    E -->|Điều tra| K["Thu thập thêm bằng chứng"]
    K --> C
    E -->|Ngoại lệ| L["Phê duyệt, giảm thiểu và đặt ngày xem lại"]
    E -->|False positive| M["Ghi căn cứ và suppression có kiểm soát"]
    J --> N["Phân tích xu hướng và cải tiến"]
    L --> N
    M --> N
~~~

## 15. Checklist rà soát

Trước khi kết thúc một đợt rà soát, hãy kiểm tra:

- Mọi phát hiện cần xử lý đã được ghi vào nguồn thống nhất chưa?
- Mỗi bản ghi có nguồn, phiên bản, thành phần và bằng chứng không?
- Phát hiện trùng lặp đã được liên kết đúng chưa?
- Finding, defect, risk và false positive đã được phân biệt chưa?
- Severity, priority và độ tin cậy có căn cứ rõ ràng không?
- Mỗi phát hiện đang mở có chủ sở hữu và bước tiếp theo không?
- Hành động được giao có phạm vi, tiêu chí hoàn thành và thời hạn không?
- Ngoại lệ có lý do, người phê duyệt, biện pháp và ngày xem lại không?
- Việc sửa đã được xác minh trên đúng phiên bản chưa?
- Issue chỉ được đóng khi có bằng chứng phù hợp chưa?
- Các phát hiện tái diễn hoặc quá hạn đã được phân tích nguyên nhân chưa?
- Chỉ số theo dõi có phản ánh chất lượng xử lý thay vì chỉ số lượng cảnh báo không?
- Bài học từ rà soát đã được đưa vào quy tắc, thiết kế và quy trình phát triển chưa?

Theo dõi kết quả rà soát tốt giúp nhóm biến cảnh báo thành quyết định và công việc có thể kiểm chứng. Mỗi phát hiện cần có ngữ cảnh, mức rủi ro, chủ sở hữu, hành động và bằng chứng đóng. Khi dữ liệu được duy trì xuyên suốt các lần rà soát, nhóm không chỉ xử lý vấn đề hiện tại mà còn nhận ra nguyên nhân lặp lại để cải thiện cách thiết kế, xây dựng và vận hành sản phẩm.

