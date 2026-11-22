# Rà soát vùng chưa bao phủ và lý do chấp nhận khoảng trống

Một kế hoạch kiểm thử có thể chứa nhiều kịch bản và vẫn bỏ sót những điều quan trọng. Một hành trình có thể chưa được kiểm tra trên vai trò ít phổ biến; một thay đổi có thể ảnh hưởng đến dữ liệu cũ nhưng bộ hồi quy chỉ dùng dữ liệu mới; một dịch vụ phụ thuộc có thể chưa được thử khi mất kết nối; hoặc một yêu cầu có thể không có bằng chứng cho môi trường mà khách hàng thực sự sử dụng. Vì vậy, thiết kế bao phủ không kết thúc khi nhóm đã viết đủ test case. Nhóm cần thường xuyên rà soát vùng chưa được bao phủ, hiểu nguyên nhân và quyết định rõ khoảng trống nào phải được lấp, khoảng trống nào có thể được chấp nhận trong giới hạn rủi ro.

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, rà soát vùng chưa bao phủ là hoạt động đối chiếu mục tiêu, yêu cầu, rủi ro, hành trình và điều kiện kiểm thử với bằng chứng hiện có. Mục tiêu là phát hiện phần thiếu quan trọng trước khi ra quyết định phát hành, đồng thời tránh lãng phí nguồn lực vào các kiểm tra trùng lặp hoặc không tạo thêm giá trị. Mọi khoảng trống được chấp nhận cần có lý do, chủ sở hữu, biện pháp kiểm soát, thời hạn xem xét và người có thẩm quyền quyết định.

## 1. Hiểu bao phủ và khoảng trống bao phủ

### Bao phủ là mức độ bằng chứng đáp ứng phạm vi đã xác định

Bao phủ kiểm thử (test coverage) mô tả phần yêu cầu, rủi ro, chức năng, điều kiện, luồng hoặc cấu trúc đã được kiểm tra bằng một hay nhiều phương pháp. Khái niệm này rộng hơn tỷ lệ dòng mã được thực thi.

Các góc nhìn bao phủ thường gồm:

- **Bao phủ yêu cầu:** yêu cầu và tiêu chí chấp nhận có được liên kết với kiểm thử và kết quả không?
- **Bao phủ rủi ro:** các rủi ro ưu tiên có kịch bản và bằng chứng kiểm soát phù hợp không?
- **Bao phủ chức năng:** chức năng, quy tắc nghiệp vụ và trạng thái quan trọng có được kiểm tra không?
- **Bao phủ hành trình:** người dùng có thể hoàn thành các luồng cốt lõi và nhánh lỗi không?
- **Bao phủ điều kiện:** các phân vùng dữ liệu, giá trị biên, quyền, trạng thái và kết hợp điều kiện có được xem xét không?
- **Bao phủ tích hợp:** ranh giới API, database, cache, queue và nhà cung cấp có được xác minh không?
- **Bao phủ nền tảng:** trình duyệt, thiết bị, hệ điều hành, cấu hình và môi trường được hỗ trợ có được đại diện không?
- **Bao phủ phi chức năng:** hiệu năng, bảo mật, khả năng tiếp cận, độ tin cậy, chịu lỗi và phục hồi có bằng chứng không?
- **Bao phủ vận hành:** triển khai, giám sát, rollback, backup, restore và xử lý sự cố có được xác minh không?

Mỗi góc nhìn trả lời một câu hỏi khác nhau. Một bộ kiểm thử có độ bao phủ dòng mã cao vẫn có thể thiếu kiểm tra quyền, dữ liệu sai, hành trình nhiều dịch vụ hoặc phục hồi sau sự cố. Ngược lại, một hành trình E2E thành công không chứng minh mọi nhánh logic hoặc cấu trúc mã đã được kiểm tra.

### Khoảng trống bao phủ là phần chưa có bằng chứng đủ tin cậy

Một khoảng trống bao phủ (coverage gap) tồn tại khi một mục tiêu, điều kiện hoặc rủi ro nằm trong phạm vi cần xác thực nhưng chưa có bằng chứng phù hợp để kết luận. Khoảng trống có thể xuất hiện vì:

- Chưa có kịch bản kiểm thử.
- Có kịch bản nhưng chưa được thực thi.
- Kịch bản đã chạy nhưng không kiểm tra đúng kết quả mong đợi.
- Môi trường hoặc dữ liệu không đại diện cho điều kiện thực tế.
- Kết quả không ổn định hoặc không thể truy vết.
- Một phụ thuộc chưa được kiểm tra hoặc chỉ được mô phỏng.
- Bằng chứng đã cũ so với phiên bản hiện tại.
- Phạm vi được kiểm tra nhưng không bao gồm biến thể quan trọng.

Không nên xem một mục đã có tên trong test plan là đã được bao phủ. Chỉ tính bằng chứng khi có thể chỉ ra phiên bản, điều kiện, kết quả và liên kết với mục tiêu cần xác minh.

### Phân biệt khoảng trống, lỗi và giới hạn có chủ đích

Các trạng thái sau cần được phân biệt:

| Trạng thái | Ý nghĩa | Cách xử lý |
|---|---|---|
| Chưa được thiết kế | Chưa có phương pháp hoặc kịch bản kiểm tra | Đánh giá rủi ro và bổ sung thiết kế nếu cần |
| Chưa thực thi | Có kịch bản nhưng chưa chạy trong phiên bản hoặc môi trường liên quan | Lập lịch chạy hoặc ghi rõ lý do chưa chạy |
| Đã chạy nhưng thiếu oracle | Có thao tác nhưng không xác định được kết quả đúng | Xây dựng tiêu chí và nguồn bằng chứng |
| Bị chặn | Không thể kiểm tra do thiếu quyền, dữ liệu, môi trường hoặc phụ thuộc | Ghi nguyên nhân, người tháo gỡ và thời hạn |
| Không đạt | Có bằng chứng cho thấy sản phẩm vi phạm tiêu chí | Tạo lỗi, đánh giá tác động và xử lý |
| Không áp dụng | Mục không liên quan đến phạm vi hoặc cấu hình đã xác định | Ghi căn cứ loại trừ và người xác nhận |
| Được chấp nhận có điều kiện | Khoảng trống còn tồn tại nhưng có quyết định chấp nhận rủi ro | Ghi người phê duyệt, kiểm soát bù và ngày hết hạn |
| Đã bao phủ | Bằng chứng hiện hành đáp ứng tiêu chí đã thống nhất | Lưu liên kết và theo dõi hiệu lực khi có thay đổi |

Một mục bị chặn không tự động trở thành không áp dụng. Một mục chưa được kiểm tra cũng không thể được đánh dấu đạt chỉ vì chưa ghi nhận lỗi. Việc phân loại rõ giúp báo cáo phản ánh đúng tình trạng.

## 2. Xác định phạm vi dùng để rà soát

### Thiết lập đường cơ sở bao phủ

Trước khi tìm khoảng trống, nhóm cần xác định phiên bản và phạm vi đang đánh giá:

- Phiên bản sản phẩm, commit hoặc build.
- Môi trường và cấu hình.
- Yêu cầu, hành trình và nhóm người dùng nằm trong phạm vi.
- Rủi ro và tiêu chí chất lượng cần xác minh.
- Nền tảng, thiết bị và tích hợp được hỗ trợ.
- Thay đổi kể từ lần đánh giá trước.
- Các điều kiện hoặc thành phần được loại trừ có chủ đích.

Nếu phạm vi không rõ, tỷ lệ bao phủ không có mẫu số đáng tin cậy. Ví dụ, báo cáo “90% yêu cầu đã được kiểm tra” không có ý nghĩa nếu nhóm chưa xác định 10% còn lại là yêu cầu nào, có quan trọng hay không và vì sao bị loại.

### Xác định nguồn tham chiếu có thẩm quyền

Việc rà soát cần đối chiếu với các nguồn đã được thống nhất, chẳng hạn:

- Yêu cầu và tiêu chí chấp nhận được phê duyệt.
- Danh mục rủi ro và quyết định xử lý rủi ro.
- Bản đồ hành trình và mô hình vai trò.
- Kiến trúc, sơ đồ phụ thuộc và hợp đồng tích hợp.
- Ma trận nền tảng hoặc cấu hình được hỗ trợ.
- Tiêu chí phi chức năng, SLI/SLO và yêu cầu phục hồi.
- Chính sách bảo mật, quyền riêng tư và nghĩa vụ liên quan.
- Quyết định thay đổi và ghi nhận sự cố.

Nếu hai nguồn mâu thuẫn, cần xác định nguồn nào có thẩm quyền và ai chịu trách nhiệm giải quyết. Không tự chọn nguồn thuận tiện để làm tỷ lệ bao phủ đẹp hơn.

### Chọn đơn vị đo phù hợp

Tùy góc nhìn, đơn vị bao phủ có thể là yêu cầu, rủi ro, hành trình, quy tắc, trạng thái, điều kiện, API, nền tảng hoặc nhánh mã. Cần ghi rõ đơn vị và cách tính.

Ví dụ:

- Bao phủ yêu cầu: số yêu cầu có bằng chứng hợp lệ trên tổng số yêu cầu trong phạm vi.
- Bao phủ rủi ro: số rủi ro ưu tiên có biện pháp và bằng chứng đã xác minh trên tổng số rủi ro ưu tiên.
- Bao phủ hành trình: số hành trình trọng yếu có kết quả kiểm tra đạt trên tổng số hành trình cần kiểm tra.
- Bao phủ nền tảng: số cấu hình được hỗ trợ đã xác minh trên tổng số cấu hình trong ma trận.
- Bao phủ nhánh: số nhánh được thực thi trên tổng số nhánh được công cụ ghi nhận.

Các tỷ lệ này không thể cộng hoặc so sánh trực tiếp nếu đơn vị, phạm vi và tiêu chí khác nhau.

## 3. Rà soát bao phủ theo yêu cầu và mục tiêu nghiệp vụ

### Truy vết từ yêu cầu đến bằng chứng

Một ma trận truy vết giúp xác định yêu cầu nào có kiểm thử, kết quả và phiên bản liên quan. Ví dụ:

| ID | Yêu cầu hoặc mục tiêu | Rủi ro | Kịch bản | Kết quả và bằng chứng | Trạng thái |
|---|---|---|---|---|---|
| REQ-01 | Người dùng có thể đăng nhập | Tài khoản hợp lệ bị từ chối | TC-LOGIN-01 | Kết quả build hiện tại và log xác thực | Đã bao phủ |
| REQ-02 | Thành viên chỉ xem dữ liệu tenant mình | Lộ dữ liệu chéo tenant | TC-AUTHZ-07 | Request, response và kiểm tra quyền | Đã bao phủ |
| REQ-03 | Giao dịch không bị ghi nhận trùng | Retry tạo tác dụng phụ lặp | Chưa có | Chưa có bằng chứng | Khoảng trống |
| REQ-04 | Báo cáo hoàn tất trong thời hạn | Worker xử lý quá chậm | TC-REPORT-04 | Đã chạy ở tải thấp, chưa có tải cao | Bao phủ một phần |

Ma trận cần liên kết đến bằng chứng có thể kiểm tra, không chỉ ghi mã test case. Với mục tiêu quan trọng, lưu kết quả chạy, phiên bản, môi trường, dữ liệu, log hoặc trace phù hợp.

### Kiểm tra tiêu chí chấp nhận và nhánh ngoại lệ

Một yêu cầu có thể có nhiều điều kiện. Ví dụ, “quản trị viên mời được thành viên” cần xem xét địa chỉ hợp lệ, địa chỉ đã tồn tại, lời mời hết hạn, người nhận đã là thành viên, quản trị viên mất quyền và dịch vụ email không sẵn sàng.

Rà soát cần hỏi:

- Mỗi tiêu chí chấp nhận đã có cách xác minh chưa?
- Có điều kiện trước và trạng thái sau rõ ràng không?
- Nhánh từ chối và ngoại lệ đã được xem xét chưa?
- Có trường hợp biên hoặc kết hợp điều kiện quan trọng không?
- Kết quả mong đợi có thể quan sát và phân biệt được không?
- Tiêu chí có còn phù hợp với phiên bản hiện tại không?

Một yêu cầu chỉ có kiểm thử happy path thường chưa được bao phủ đầy đủ nếu nhánh lỗi có thể gây hậu quả đáng kể.

### Kiểm tra mục tiêu nghiệp vụ có được đo

Không phải mọi mục tiêu nghiệp vụ đều chuyển thành một test case chức năng. Ví dụ, giảm thời gian hoàn thành công việc có thể cần thử nghiệm với người dùng, đo thời gian tác vụ hoặc phân tích hành vi. Tăng tỷ lệ chuyển đổi có thể cần dữ liệu thực nghiệm hoặc phân tích sản phẩm sau phát hành.

Hãy phân biệt bằng chứng kiểm thử kỹ thuật với bằng chứng xác nhận giá trị. Nếu mục tiêu chưa thể xác minh trước phát hành, ghi rõ phương pháp đo sau phát hành, ngưỡng xem xét và người theo dõi.

## 4. Rà soát bao phủ theo rủi ro

### Đối chiếu mức rủi ro với độ sâu bằng chứng

Rủi ro cao cần bằng chứng mạnh hơn và thường cần nhiều góc nhìn. Rà soát nên xem:

- Rủi ro có được mô tả bằng nguyên nhân, sự kiện và hậu quả không?
- Mức khả năng xảy ra và tác động có căn cứ không?
- Có biện pháp kiểm soát và chủ sở hữu không?
- Kịch bản có kiểm tra đúng nguyên nhân hoặc hậu quả không?
- Bằng chứng có đại diện cho môi trường và dữ liệu liên quan không?
- Có kiểm tra phục hồi hoặc tác dụng phụ khi cần không?
- Rủi ro còn lại đã được người có thẩm quyền xem xét chưa?

Không nên dùng số lượng test case làm đại diện cho mức bao phủ rủi ro. Một rủi ro nghiêm trọng có thể chỉ cần một số kịch bản được thiết kế tốt nhưng phải kiểm tra đúng điều kiện, oracle và trạng thái cuối.

### Tìm rủi ro không có bằng chứng

Tạo danh sách rủi ro ưu tiên rồi nối từng mục với kịch bản và kết quả. Các mục không có liên kết cần được xem xét riêng. Đặc biệt chú ý:

- Rủi ro về quyền truy cập, phân tách tenant và dữ liệu nhạy cảm.
- Rủi ro mất, sai hoặc nhân đôi giao dịch.
- Rủi ro từ dịch vụ bên ngoài và thành phần do nhóm khác sở hữu.
- Rủi ro đồng bộ, retry, sự kiện trùng và trạng thái bất đồng bộ.
- Rủi ro hiệu năng, tải, cạn tài nguyên và lỗi dây chuyền.
- Rủi ro backup, restore, failover và phục hồi.
- Rủi ro triển khai, migration, rollback và cấu hình.

Nếu rủi ro không được kiểm tra trực tiếp, hãy xác định liệu có biện pháp kiểm soát khác tạo bằng chứng đủ mạnh hay không. Ví dụ, một kiểm soát quyền có thể được xác minh bằng review thiết kế, kiểm thử API và kiểm tra cấu hình; chỉ một bài kiểm tra giao diện thường không đủ.

### Đánh giá mức độ mới và hiệu lực của bằng chứng

Bằng chứng cũ có thể không còn áp dụng sau khi thay đổi mã, schema, nhà cung cấp, cấu hình hoặc hành trình. Với mỗi bằng chứng, xem xét:

- Được tạo trên phiên bản nào?
- Điều kiện và môi trường có tương đương phiên bản hiện tại không?
- Phần liên quan đã thay đổi kể từ lần chạy chưa?
- Có lỗi hoặc sự cố mới làm giả định cũ không còn đúng không?
- Có thể tái sử dụng kết quả hay cần chạy lại?
- Người sở hữu đã xác nhận tính phù hợp chưa?

Không đánh dấu đã bao phủ chỉ vì test case tồn tại trong repository. Cần biết nó đã chạy khi nào và kết quả có còn đại diện không.

## 5. Rà soát bao phủ theo hành trình và vai trò

### Kiểm tra đường đi chính và các nhánh quan trọng

Với từng hành trình, đối chiếu:

- Điểm bắt đầu và điều kiện trước.
- Các bước nghiệp vụ và chuyển trạng thái.
- Điểm tích hợp và phụ thuộc.
- Điều kiện thành công.
- Nhánh lỗi, timeout, retry và hủy.
- Tác dụng phụ đồng bộ và bất đồng bộ.
- Trạng thái cuối và khả năng tiếp tục.

Một hành trình có thể được kiểm tra từ đầu đến cuối nhưng vẫn thiếu nhánh thu hồi quyền, mất kết nối hoặc sự kiện đến muộn. Hãy chọn nhánh theo hậu quả và khả năng xảy ra, không cố tạo mọi kết hợp không có giá trị.

### Rà soát ma trận vai trò và quyền

Một hành trình thường thay đổi theo danh tính, vai trò và tenant. Hãy đối chiếu:

- Người chưa đăng nhập.
- Người dùng thông thường.
- Quản trị viên.
- Người phê duyệt hoặc người có quyền đặc biệt.
- Tài khoản bị khóa, hết hạn hoặc thu hồi quyền.
- Người dùng thuộc tenant hoặc tổ chức khác.

Kiểm tra cả hành động được phép và bị từ chối. Các khoảng trống về phân tách tenant, quyền quản trị và dữ liệu nhạy cảm cần được ưu tiên vì hậu quả có thể lớn ngay cả khi số người bị ảnh hưởng nhỏ.

### Kiểm tra tác dụng phụ và trạng thái cuối

Đối với hành trình có tác dụng phụ, hãy xác minh không chỉ trạng thái giao diện mà còn:

- Bản ghi nghiệp vụ có được tạo hoặc cập nhật đúng không?
- Có sự kiện hoặc thông điệp nào cần phát không?
- Email, SMS, hóa đơn hoặc giao dịch có được tạo đúng người nhận và số lần không?
- Có cập nhật cache, search index hoặc hệ thống phụ thuộc không?
- Audit log có ghi đúng actor, tài nguyên và thời điểm không?
- Có tác dụng phụ không mong muốn khi giao dịch bị từ chối không?

Một khoảng trống phổ biến là kiểm tra kết quả chính nhưng không kiểm tra tác dụng phụ. Ví dụ, đơn hàng hiển thị đã tạo nhưng tồn kho không được trừ hoặc email xác nhận gửi hai lần.

## 6. Rà soát bao phủ theo dữ liệu, điều kiện và nền tảng

### Phân vùng dữ liệu và giá trị biên

Với mỗi trường hoặc quy tắc quan trọng, kiểm tra xem các phân vùng tương đương và giá trị biên đã được đại diện chưa:

- Giá trị hợp lệ thông thường.
- Giá trị nhỏ nhất và lớn nhất.
- Giá trị ngay dưới hoặc trên ngưỡng.
- Trường thiếu, null, rỗng hoặc sai định dạng.
- Dữ liệu trùng hoặc xung đột.
- Chuỗi dài, ký tự đặc biệt, Unicode và dữ liệu không tin cậy.
- Trạng thái cũ hoặc dữ liệu được tạo bởi phiên bản trước.

Không cần kiểm tra mọi giá trị có thể. Cần chứng minh nhóm đã chọn trường hợp dựa trên quy tắc và rủi ro, đồng thời không bỏ qua miền dữ liệu có thể làm thay đổi kết quả.

### Kiểm tra kết hợp điều kiện

Nhiều lỗi chỉ xuất hiện khi các điều kiện kết hợp, ví dụ vai trò quản trị + tenant đã bị khóa + phiên cũ; hoặc thanh toán timeout + webhook đến trễ + người dùng gửi lại request.

Có thể dùng pairwise hoặc kỹ thuật chọn tổ hợp để giảm số trường hợp, nhưng phải xem xét các điều kiện có tương tác đặc biệt. Pairwise không bảo đảm bao phủ mọi lỗi phụ thuộc ba hoặc nhiều điều kiện. Với rủi ro cao, cần thêm tổ hợp có chủ đích dựa trên kiến trúc và lịch sử sự cố.

### Kiểm tra nền tảng và cấu hình được hỗ trợ

Ma trận nền tảng có thể gồm trình duyệt, phiên bản hệ điều hành, thiết bị, độ phân giải, mạng, vùng địa lý hoặc cấu hình triển khai. Rà soát xem:

- Mỗi nền tảng được hỗ trợ có bằng chứng tương ứng không?
- Có nhóm nền tảng nào chỉ được thử trên môi trường mô phỏng không?
- Phiên bản cũ còn được hỗ trợ có được kiểm tra không?
- Có khác biệt về cookie, lưu trữ, phông chữ, timezone hoặc quyền thiết bị không?
- Có thiết bị hoặc mạng hạn chế ảnh hưởng đến hành trình không?

Nếu dùng chiến lược lấy mẫu, ghi rõ cơ sở chọn cấu hình đại diện và những khác biệt chưa được xác minh. Không tuyên bố hỗ trợ một nền tảng chỉ vì ứng dụng đã mở được trên đó.

## 7. Rà soát bao phủ phi chức năng và vận hành

### Hiệu năng và khả năng mở rộng

Đối chiếu yêu cầu tải với bằng chứng:

- Lưu lượng bình thường, cao điểm và đột biến.
- Độ trễ p50, p95, p99 và tỷ lệ timeout.
- Số người dùng đồng thời và số giao dịch.
- Thời gian xử lý queue và tuổi thông điệp.
- Tài nguyên CPU, bộ nhớ, kết nối và I/O.
- Hành vi khi một phụ thuộc chậm hoặc giới hạn tần suất.
- Khả năng mở rộng và thời gian bổ sung năng lực.

Một bài test tải nhỏ không đủ chứng minh hệ thống đáp ứng mục tiêu tải cao. Nếu tải production chưa thể mô phỏng, ghi rõ phạm vi đã thử và kế hoạch xác minh bổ sung.

### Bảo mật và quyền riêng tư

Rà soát khoảng trống liên quan đến:

- Xác thực, phân quyền và phân tách tenant.
- Quản lý secret, token và khóa.
- Mã hóa dữ liệu khi truyền và khi lưu.
- Xử lý đầu vào không tin cậy.
- Lộ dữ liệu trong log, trace, cache hoặc queue.
- Kiểm soát truy cập vào backup và môi trường thử nghiệm.
- Vòng đời lưu giữ và xóa dữ liệu.
- Kiểm tra phụ thuộc và thành phần bên thứ ba.

Không chấp nhận một khoảng trống nghiêm trọng chỉ vì tỷ lệ bao phủ tổng thể cao. Các yêu cầu bảo mật, quyền riêng tư hoặc nghĩa vụ pháp lý cần được chuyển đến người có chuyên môn và thẩm quyền theo quy trình áp dụng.

### Chịu lỗi, phục hồi và độ sẵn sàng

Đối chiếu bằng chứng về:

- Failover của ứng dụng, database hoặc broker.
- Backup và restore có xác minh dữ liệu.
- RTO/RPO được đo trong diễn tập.
- Retry, idempotency, circuit breaker và degraded mode.
- Khôi phục worker, queue và outbox.
- Đối soát trạng thái sau gián đoạn.
- Synthetic monitoring và hành trình có ý nghĩa với người dùng.
- Cảnh báo, runbook và trách nhiệm trực vận hành.

Một tài liệu mô tả kế hoạch DR chưa phải bằng chứng rằng tổ chức có thể thực hiện được kế hoạch đó. Cần diễn tập hoặc kiểm tra thực tế phù hợp.

### Khả năng tiếp cận, tương thích và khả năng sử dụng

Với sản phẩm có giao diện, xem xét:

- Điều hướng bằng bàn phím và công nghệ hỗ trợ.
- Nhãn, thông báo lỗi và trạng thái có thể nhận biết.
- Tương phản, phóng to và bố cục phù hợp.
- Hành vi trên trình duyệt và thiết bị được hỗ trợ.
- Ngôn ngữ, định dạng ngày giờ và tiền tệ.
- Khả năng hoàn thành tác vụ của người dùng mục tiêu.

Kiểm tra tự động có thể phát hiện một số vấn đề nhưng không thay thế đánh giá thủ công và thử nghiệm với người dùng đại diện khi cần.

## 8. Phân loại nguyên nhân của khoảng trống

### Khoảng trống do thiết kế

Nhóm chưa nhận diện mục tiêu, rủi ro hoặc điều kiện cần kiểm tra. Ví dụ, test plan chỉ mô tả luồng thành công và bỏ qua trạng thái hủy.

Cách xử lý: quay lại yêu cầu, hành trình và rủi ro; bổ sung câu hỏi xác thực, tiêu chí và phương pháp kiểm tra.

### Khoảng trống do thực thi

Kịch bản đã có nhưng chưa chạy, chạy sai phiên bản hoặc bị bỏ qua do thời gian. Ví dụ, bài kiểm thử tích hợp bị tắt vì môi trường không ổn định.

Cách xử lý: xác định điều kiện chạy lại, sửa môi trường, lập lịch và ghi rõ rủi ro trong thời gian chưa có bằng chứng. Không xem việc test bị skip là pass.

### Khoảng trống do môi trường hoặc phụ thuộc

Nhóm không có sandbox, quyền, dữ liệu hoặc thành phần đại diện. Ví dụ, nhà cung cấp bên ngoài không cung cấp môi trường thử nghiệm cho một luồng đặc biệt.

Cách xử lý có thể gồm contract test, simulator, test double, xác nhận của nhà cung cấp, thử nghiệm có kiểm soát hoặc kế hoạch xác minh sau phát hành. Ghi rõ hành vi nào vẫn chưa được kiểm chứng.

### Khoảng trống do khả năng quan sát

Hành trình có thể chạy nhưng không có oracle hoặc tín hiệu đủ để biết trạng thái cuối. Ví dụ, API trả về tiếp nhận nhưng không thể xác định worker đã hoàn tất hay chưa.

Cách xử lý: bổ sung trạng thái nghiệp vụ, correlation ID, metric, log, trace hoặc giao diện kiểm tra được phê duyệt.

### Khoảng trống do dữ liệu hoặc tổ hợp điều kiện

Dữ liệu không đại diện, thiếu dữ liệu biên hoặc không thể tạo trạng thái cần thiết. Ví dụ, không có tài khoản đã hết hạn quyền hoặc dữ liệu đủ lớn để kiểm tra phân trang.

Cách xử lý: tạo fixture tổng hợp, công cụ seed dữ liệu, dữ liệu đã khử định danh hoặc chiến lược chọn tổ hợp theo rủi ro.

### Khoảng trống do thay đổi và lỗi thời

Bằng chứng không còn khớp với phiên bản, hợp đồng hoặc cấu hình hiện tại. Ví dụ, API đã thay đổi nhưng contract test chưa được cập nhật.

Cách xử lý: đánh giá tác động thay đổi, cập nhật truy vết, chạy lại kiểm thử liên quan và lưu kết quả mới.

### Khoảng trống do nguồn lực hoặc thời gian

Nhóm chưa thể kiểm tra mọi trường hợp trong cửa sổ phát hành. Đây là lý do cần minh bạch, nhưng tự nó không chứng minh khoảng trống có thể chấp nhận.

Cách xử lý: ưu tiên theo rủi ro, cân nhắc kiểm soát bù, chuyển thời điểm phát hành nếu cần hoặc xin quyết định chấp nhận rủi ro đúng thẩm quyền.

## 9. Quyết định lấp đầy, loại trừ hay chấp nhận khoảng trống

### Lấp đầy khoảng trống

Cần bổ sung kiểm thử hoặc bằng chứng khi:

- Mục tiêu quan trọng chưa có cách xác minh.
- Rủi ro cao chưa có kiểm soát được kiểm chứng.
- Một nhánh có thể gây mất dữ liệu, lộ dữ liệu hoặc tác dụng phụ sai.
- Bằng chứng hiện tại không đại diện cho phiên bản hoặc môi trường.
- Một sự cố mới cho thấy giả định trước đây không đúng.
- Tiêu chí bắt buộc chưa được xác nhận.

Biện pháp có thể là thêm test case, kiểm thử hợp đồng, thử nghiệm người dùng, phân tích tĩnh, diễn tập phục hồi, kiểm tra bảo mật hoặc bổ sung quan sát.

### Loại trừ có căn cứ

Một mục có thể được đánh dấu không áp dụng khi nằm ngoài phạm vi được hỗ trợ hoặc không liên quan đến kiến trúc và hành trình đang đánh giá. Ví dụ, kiểm thử trên một hệ điều hành không được hỗ trợ có thể không nằm trong ma trận phát hành.

Quyết định loại trừ cần ghi:

- Mục hoặc điều kiện được loại trừ.
- Phạm vi và giả định làm căn cứ.
- Nguồn xác nhận phạm vi hỗ trợ.
- Tác động nếu giả định thay đổi.
- Người xác nhận.

Không dùng nhãn không áp dụng để che giấu việc thiếu môi trường hoặc chưa có thời gian kiểm thử.

### Chấp nhận khoảng trống có điều kiện

Có thể cân nhắc chấp nhận khi nhóm đã hiểu rủi ro còn lại, có biện pháp kiểm soát bù phù hợp và người có thẩm quyền đồng ý. Ví dụ, một biến thể trình duyệt ít được sử dụng có thể chưa được kiểm tra trên mọi cấu hình, nhưng đã có bằng chứng trên cấu hình đại diện, có theo dõi sau phát hành và có phương án quay lui.

Chấp nhận cần có điều kiện cụ thể. Không nên dùng câu “rủi ro thấp” mà không nêu căn cứ, phạm vi và người chịu trách nhiệm.

### Khi không nên chấp nhận

Một khoảng trống không nên được chấp nhận chỉ vì cần giữ ngày phát hành. Đặc biệt, nếu có nguy cơ nghiêm trọng về an toàn, bảo mật, quyền riêng tư, dữ liệu tài chính hoặc nghĩa vụ bắt buộc, phải chuyển đến người có chuyên môn và thẩm quyền theo chính sách. Worker hoặc người thực hiện kiểm thử không tự quyết định miễn trừ yêu cầu thuộc thẩm quyền khác.

Nếu chưa thể đánh giá hậu quả hoặc không có bằng chứng đủ tin cậy, trạng thái đúng là chưa đủ bằng chứng. Cần làm rõ trước khi đưa ra quyết định.

## 10. Ghi nhận quyết định chấp nhận khoảng trống

### Nội dung tối thiểu của một bản ghi

Một bản ghi chấp nhận khoảng trống nên có:

| Trường | Nội dung cần ghi |
|---|---|
| ID và mô tả | Khoảng trống cụ thể, mục tiêu và điều kiện chưa được kiểm tra |
| Phạm vi | Phiên bản, môi trường, người dùng, hành trình và nền tảng liên quan |
| Lý do | Vì sao chưa có bằng chứng hoặc vì sao chưa thể lấp đầy |
| Rủi ro còn lại | Nguyên nhân, khả năng xảy ra, tác động và mức bất định |
| Bằng chứng hiện có | Những gì đã được kiểm tra và giới hạn của kết quả |
| Kiểm soát bù | Giám sát, giới hạn tính năng, fallback, review thủ công hoặc rollback |
| Chủ sở hữu | Người chịu trách nhiệm theo dõi và xử lý |
| Người phê duyệt | Người có thẩm quyền chấp nhận theo chính sách |
| Thời hạn | Ngày hết hạn hoặc mốc phải đánh giá lại |
| Điều kiện kích hoạt | Sự kiện khiến phải mở lại quyết định |
| Kế hoạch đóng | Việc cần làm để lấp đầy khoảng trống |

Không để một quyết định chấp nhận tồn tại vô thời hạn mà không có ngày rà soát. Nếu điều kiện thay đổi, quyết định cũ cần được đánh giá lại.

### Phân biệt chấp nhận rủi ro với xác nhận đã bao phủ

Chấp nhận khoảng trống không biến phần chưa kiểm tra thành đã kiểm tra. Báo cáo phải giữ trạng thái rõ ràng, ví dụ “chưa được kiểm tra – được chấp nhận đến ngày … theo quyết định …”. Điều này giúp người đọc hiểu sản phẩm vẫn có rủi ro còn lại.

Không tính khoảng trống được chấp nhận vào tử số bao phủ như một bài kiểm thử đạt. Có thể báo cáo riêng tỷ lệ mục được kiểm tra và số khoảng trống được chấp nhận.

### Ví dụ bản ghi

~~~yaml
gap_id: GAP-017
item: "Kiểm tra hành trình trên phiên bản trình duyệt cũ"
scope: "Phiên bản phát hành 2.4, cấu hình trình duyệt được nêu trong ma trận hỗ trợ"
status: "ACCEPTED_WITH_CONDITIONS"
reason: "Môi trường tự động cho phiên bản này chưa sẵn sàng trong cửa sổ phát hành"
residual_risk: "Một số lỗi hiển thị hoặc thao tác có thể chưa được phát hiện"
existing_evidence:
  - "Đã kiểm tra trên phiên bản trình duyệt hiện hành"
  - "Đã rà soát tương thích API và CSS liên quan"
compensating_controls:
  - "Theo dõi lỗi giao diện sau phát hành"
  - "Có thể tắt tính năng bằng feature flag"
owner: "Chủ sở hữu trải nghiệm"
approver: "Người có thẩm quyền phát hành"
review_by: "Mốc rà soát đã thống nhất"
reopen_when:
  - "Tỷ lệ lỗi trên nền tảng này vượt ngưỡng"
  - "Có thay đổi lớn về giao diện hoặc thư viện"
closure_plan: "Bổ sung môi trường và chạy lại bộ kiểm thử tương thích"
~~~

Đây là cấu trúc minh họa. Dùng trường, trạng thái và quy trình phê duyệt thực tế của tổ chức; không sao chép tên vai trò hoặc ngày mẫu như dữ liệu thật.

## 11. Ưu tiên khoảng trống cần xử lý

### Dùng mức rủi ro và độ bất định

Có thể xếp thứ tự xử lý dựa trên:

- Mức tác động nếu lỗi xảy ra.
- Khả năng xảy ra hoặc tần suất phơi nhiễm.
- Khả năng phát hiện trước khi người dùng bị ảnh hưởng.
- Mức khó phục hồi hoặc chi phí sửa muộn.
- Số người dùng, tenant hoặc hành trình bị ảnh hưởng.
- Độ tin cậy của bằng chứng hiện có.
- Mức độ gần của mốc phát hành hoặc thay đổi liên quan.

Một khoảng trống có tác động rất cao nhưng ít dữ liệu vẫn cần được ưu tiên xem xét. Không tự giảm ưu tiên chỉ vì khả năng xảy ra chưa được chứng minh.

### Ma trận ưu tiên minh họa

| Mức | Đặc điểm | Hành động |
|---|---|---|
| Rất cao | Có thể gây hậu quả nghiêm trọng; không có bằng chứng hoặc kiểm soát phù hợp | Bổ sung bằng chứng hoặc xử lý trước quyết định phát hành; chuyển cấp khi cần |
| Cao | Ảnh hưởng hành trình quan trọng hoặc có bất định lớn | Gán chủ sở hữu, thời hạn và kiểm chứng trước mốc đã định |
| Trung bình | Có ảnh hưởng giới hạn, có phương án thay thế và kiểm soát quan sát được | Lập kế hoạch xử lý hoặc chấp nhận có điều kiện |
| Thấp | Hậu quả nhỏ, phạm vi hẹp và dễ phát hiện/phục hồi | Theo dõi, lấy mẫu hoặc xử lý theo chu kỳ |

Các mức cần được hiệu chỉnh theo khẩu vị rủi ro và nghĩa vụ của sản phẩm. Quy tắc vượt mức vẫn cần áp dụng cho các lĩnh vực như an toàn, bảo mật và tuân thủ.

### Xem xét chi phí và giá trị của bằng chứng bổ sung

Không phải mọi khoảng trống đều cần một bài E2E mới. Hãy chọn phương pháp tạo bằng chứng đáng tin cậy với chi phí phù hợp:

- Rà soát yêu cầu có thể giải quyết mơ hồ trước khi viết test.
- Contract test có thể xác minh tương thích giữa hai dịch vụ.
- Unit test có thể bao phủ nhiều giá trị biên với thời gian chạy thấp.
- Kiểm thử tích hợp có thể xác minh database hoặc broker thật.
- Kiểm thử E2E có thể xác nhận một hành trình cốt lõi.
- Thử nghiệm người dùng có thể đánh giá mức dễ hiểu và khả năng hoàn thành.
- Giám sát sau phát hành có thể bổ sung bằng chứng trong điều kiện sử dụng thực tế.

Nếu một phương pháp chỉ tạo thêm cùng loại bằng chứng đã có, hãy cân nhắc đầu tư vào góc nhìn còn thiếu.

## 12. Theo dõi khoảng trống trong suốt vòng đời

### Rà soát khi có thay đổi

Mỗi thay đổi có thể làm mất hiệu lực một phần bao phủ. Khi yêu cầu, mã, schema, quyền, phụ thuộc hoặc cấu hình thay đổi, hãy xác định:

- Mục tiêu và rủi ro nào bị ảnh hưởng?
- Kịch bản nào cần sửa hoặc chạy lại?
- Bằng chứng cũ nào còn hiệu lực?
- Có nhánh, nền tảng hoặc tác dụng phụ mới không?
- Có khoảng trống mới phát sinh không?
- Quyết định chấp nhận trước đó có còn phù hợp không?

Rà soát tác động thay đổi giúp tránh chạy lại toàn bộ bộ kiểm thử khi không cần, đồng thời không bỏ sót vùng chịu ảnh hưởng.

### Rà soát sau sự cố

Sự cố vận hành là nguồn thông tin quan trọng về khoảng trống. Sau sự cố, hãy hỏi:

- Vì sao kiểm thử trước phát hành không phát hiện?
- Kịch bản có thiếu hay chỉ không chạy?
- Oracle có kiểm tra sai nguồn hoặc sai trạng thái không?
- Môi trường có khác thực tế ở điểm quan trọng không?
- Cảnh báo hoặc log có thiếu khiến sự cố kéo dài không?
- Một giả định về nhà cung cấp hoặc người dùng có sai không?
- Cần thêm bằng chứng nào và ai duy trì?

Không phải mọi sự cố đều có thể dự đoán bằng test case. Mục tiêu là cập nhật chiến lược dựa trên bài học có thể áp dụng, không biến mỗi sự cố thành hàng loạt kiểm thử trùng lặp.

### Quản lý tuổi thọ của khoảng trống được chấp nhận

Khoảng trống được chấp nhận cần được rà soát theo thời hạn và điều kiện kích hoạt. Một quyết định có thể hết hiệu lực khi:

- Hết ngày chấp nhận.
- Phiên bản mới được phát hành.
- Phạm vi người dùng hoặc tải thay đổi.
- Có sự cố hoặc khiếu nại liên quan.
- Môi trường hoặc công cụ kiểm thử đã sẵn sàng.
- Biện pháp kiểm soát bù không còn hoạt động.

Khi hết hạn, cần đóng khoảng trống bằng bằng chứng mới hoặc xin quyết định mới. Không tự động gia hạn chỉ vì chưa có người xử lý.

## 13. Ví dụ: rà soát khoảng trống trong hành trình thanh toán thuê bao

Giả sử sản phẩm SaaS cho phép quản trị viên chọn gói, thanh toán qua nhà cung cấp, kích hoạt thuê bao và mời thành viên. Nhóm đã có kiểm thử đơn vị cho công thức giá, kiểm thử API cho tạo giao dịch và một bài E2E cho thanh toán thành công.

### Những vùng còn thiếu được phát hiện

| Vùng | Bằng chứng hiện có | Khoảng trống |
|---|---|---|
| Giá và thuế | Unit test cho trường hợp chuẩn | Chưa kiểm tra tiền tệ và giá trị biên |
| Quyền thanh toán | E2E dùng tài khoản quản trị | Chưa kiểm tra thành viên thường bị từ chối |
| Callback | API test phản hồi thành công | Chưa kiểm tra chữ ký sai và callback lặp |
| Timeout | Chưa có | Chưa biết kết quả khi nhà cung cấp đã xử lý nhưng phản hồi bị mất |
| Kích hoạt thuê bao | E2E kiểm tra giao diện | Chưa đối chiếu trạng thái thuê bao và giao dịch ở nguồn có thẩm quyền |
| Email xác nhận | Log cho biết job đã tạo | Chưa xác minh người nhận và số lần gửi |
| Phục hồi | Có tài liệu vận hành | Chưa diễn tập xử lý giao dịch không rõ kết quả |

### Quyết định xử lý

- Bổ sung kiểm thử giá trị biên cho giá, thuế và tiền tệ.
- Thêm kiểm thử phân quyền ở API và E2E cho vai trò không có quyền thanh toán.
- Thêm contract/integration test cho chữ ký callback, callback trùng và sự kiện đến muộn.
- Tạo kịch bản timeout sau khi nhà cung cấp đã xử lý để xác minh idempotency và đối soát.
- Đối chiếu giao dịch, thuê bao, hóa đơn và audit log sau hành trình.
- Dùng email sink hoặc sandbox để kiểm tra đúng người nhận và số lần gửi.
- Diễn tập quy trình xử lý giao dịch có kết quả không xác định.

Nếu một môi trường nhà cung cấp chưa hỗ trợ một loại lỗi cụ thể, nhóm có thể dùng test double để xác minh logic tiêu thụ, đồng thời ghi rõ hành vi thật của nhà cung cấp chưa được kiểm chứng. Khoảng trống đó chỉ được chấp nhận theo quyết định có thẩm quyền, kèm kiểm soát và kế hoạch xác minh bổ sung.

## 14. Báo cáo tình trạng bao phủ

### Báo cáo theo nhiều góc nhìn

Một báo cáo hữu ích nên tách các nhóm thay vì đưa ra một tỷ lệ duy nhất:

| Góc nhìn | Tổng mục trong phạm vi | Đã có bằng chứng đạt | Chưa đủ bằng chứng | Không đạt | Chấp nhận có điều kiện |
|---|---:|---:|---:|---:|---:|
| Yêu cầu | Theo baseline | Theo kết quả | Theo kết quả | Theo kết quả | Theo quyết định |
| Rủi ro ưu tiên | Theo danh mục | Theo kết quả | Theo kết quả | Theo kết quả | Theo quyết định |
| Hành trình | Theo bản đồ | Theo kết quả | Theo kết quả | Theo kết quả | Theo quyết định |
| Nền tảng | Theo ma trận hỗ trợ | Theo kết quả | Theo kết quả | Theo kết quả | Theo quyết định |
| Phi chức năng | Theo tiêu chí | Theo kết quả | Theo kết quả | Theo kết quả | Theo quyết định |

Không điền số liệu nếu chưa có dữ liệu. Báo cáo cần nêu thời điểm, phiên bản, môi trường, cách tính và các giới hạn.

### Không dùng tỷ lệ tổng để che rủi ro trọng yếu

Một sản phẩm có thể đạt 98% bao phủ nhưng 2% còn lại là kiểm tra phân tách tenant hoặc phục hồi thanh toán. Tỷ lệ tổng cao không làm rủi ro đó trở nên chấp nhận được.

Hãy làm nổi bật:

- Khoảng trống có tác động nghiêm trọng.
- Mục bắt buộc chưa có bằng chứng.
- Kiểm thử quan trọng bị skip hoặc flaky.
- Bằng chứng chỉ có ở môi trường mô phỏng.
- Quyết định chấp nhận sắp hết hạn.
- Khoảng trống không có chủ sở hữu hoặc kế hoạch đóng.

### Nêu rõ điều chưa biết

Báo cáo nên phân biệt dữ liệu đã xác minh với giả định. Ví dụ, “đã kiểm tra failover một instance trong staging” không đồng nghĩa “đã chứng minh phục hồi mất vùng”. Ghi rõ phạm vi thử nghiệm giúp người ra quyết định hiểu mức bảo đảm thực tế.

## 15. Những sai lầm thường gặp

- **Chỉ nhìn tỷ lệ code coverage:** bỏ qua yêu cầu, rủi ro, hành trình và vận hành.
- **Tính test case tồn tại là đã bao phủ:** chưa chứng minh test đã chạy hoặc có oracle đúng.
- **Đánh dấu test bị skip là pass:** che giấu khoảng trống thực tế.
- **Gộp không áp dụng với chưa kiểm tra:** làm mẫu số và kết luận sai.
- **Dùng tỷ lệ tổng để che rủi ro cao:** một khoảng trống nghiêm trọng vẫn cần quyết định riêng.
- **Chấp nhận vì thiếu thời gian:** không có phân tích rủi ro, kiểm soát bù hoặc người phê duyệt.
- **Không ghi thời hạn chấp nhận:** khoảng trống có thể tồn tại vô hạn.
- **Không xem lại bằng chứng cũ:** kết quả trên phiên bản cũ bị dùng cho phiên bản mới.
- **Chỉ kiểm tra happy path:** bỏ sót quyền, timeout, dữ liệu biên và tác dụng phụ.
- **Không kiểm tra nguồn dữ liệu có thẩm quyền:** giao diện có thể đúng tạm thời trong khi trạng thái nghiệp vụ sai.
- **Không gắn chủ sở hữu:** khoảng trống được ghi nhận nhưng không được xử lý.
- **Tạo thêm test trùng lặp:** tăng chi phí nhưng không cải thiện góc nhìn còn thiếu.
- **Kết luận vượt quá bằng chứng:** mô phỏng hoặc kiểm tra giới hạn bị trình bày như xác minh toàn diện.

## 16. Đầu ra cần có trước khi chốt rà soát bao phủ

Một lần rà soát đủ dùng nên tạo ra:

1. **Baseline phạm vi:** phiên bản, môi trường, yêu cầu, hành trình, rủi ro và nền tảng được đánh giá.
2. **Ma trận truy vết:** liên kết mục tiêu với kịch bản, kết quả và bằng chứng.
3. **Danh sách khoảng trống:** mô tả, loại, nguyên nhân, mức rủi ro và phạm vi ảnh hưởng.
4. **Phân loại trạng thái:** chưa thiết kế, chưa chạy, bị chặn, không đạt, không áp dụng hoặc đã chấp nhận.
5. **Đánh giá ưu tiên:** tác động, khả năng, độ bất định và chi phí lấp đầy.
6. **Kế hoạch xử lý:** kịch bản hoặc bằng chứng cần bổ sung, người phụ trách và thời hạn.
7. **Bản ghi chấp nhận:** lý do, rủi ro còn lại, kiểm soát bù, người phê duyệt và ngày hết hạn.
8. **Báo cáo bao phủ:** kết quả theo từng góc nhìn và phương pháp tính.
9. **Kế hoạch rà soát lại:** mốc phát hành, thay đổi, sự cố và điều kiện kích hoạt.
10. **Giới hạn kết luận:** phần đã kiểm tra, phần được mô phỏng và điều chưa được chứng minh.

Trước khi chốt, hãy rà soát:

- Phạm vi và mẫu số bao phủ có rõ ràng không?
- Mỗi mục quan trọng có bằng chứng hiện hành và truy vết được không?
- Rủi ro ưu tiên có được kiểm tra đúng nguyên nhân và hậu quả không?
- Hành trình, vai trò, dữ liệu, nền tảng và tác dụng phụ có vùng thiếu đáng kể không?
- Các bài test bị bỏ qua, không ổn định hoặc bị chặn có được phân loại đúng không?
- Mục không áp dụng có căn cứ và người xác nhận không?
- Mọi khoảng trống được chấp nhận có chủ sở hữu, kiểm soát bù, thời hạn và người phê duyệt không?
- Rủi ro nghiêm trọng có được chuyển đến đúng thẩm quyền không?
- Báo cáo có nêu giới hạn và điều chưa được chứng minh không?
- Có kế hoạch cập nhật khi thay đổi hoặc có sự cố mới không?

Rà soát vùng chưa bao phủ giúp nhóm nhìn thấy giới hạn của bằng chứng trước khi đưa ra quyết định. Khoảng trống cần được lấp đầy khi rủi ro đòi hỏi; nếu được chấp nhận, quyết định phải minh bạch, có thời hạn và có người chịu trách nhiệm. Hãy duy trì hoạt động này qua từng thay đổi, lần phát hành và sự cố để chiến lược xác thực luôn phản ánh đúng sản phẩm đang được xây dựng và sử dụng.

