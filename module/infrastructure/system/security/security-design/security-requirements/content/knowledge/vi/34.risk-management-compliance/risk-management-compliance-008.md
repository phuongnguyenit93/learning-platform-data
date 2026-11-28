# Monitor: giám sát yêu cầu bảo mật và rủi ro trong suốt vòng đời hệ thống

## 1. Mục tiêu của Monitor

Một yêu cầu bảo mật có thể vượt qua kiểm thử trước khi phát hành nhưng mất hiệu lực sau đó: tài khoản mới được cấp quyền ngoài quy trình, dịch vụ đổi cấu hình, luồng dữ liệu đi qua nhà cung cấp mới hoặc hệ thống ghi log ngừng gửi sự kiện. Monitor là hoạt động duy trì bằng chứng về trạng thái thực tế, nhận ra thay đổi và dùng kết quả đó để điều chỉnh quyết định rủi ro.

Trong chương Risk management và compliance của module Security Requirements, câu hỏi trung tâm là: **yêu cầu nào còn được đáp ứng, bằng chứng nào đủ để kết luận, và phải làm gì khi giả định ban đầu không còn đúng?**

Trong NIST Risk Management Framework, bước Monitor duy trì nhận thức về trạng thái an ninh và quyền riêng tư nhằm hỗ trợ quyết định quản trị rủi ro; kết quả bao gồm đánh giá kiểm soát liên tục, phân tích kết quả, phản hồi và báo cáo cho cấp quản lý. Đây là một cách tham chiếu để tổ chức hoạt động giám sát. [Nguồn: NIST RMF — Monitor Step](https://csrc.nist.gov/projects/risk-management/about-rmf/monitor-step).

Sau bài học, người học có thể:

- Chuyển một yêu cầu bảo mật thành đặc tả giám sát có chỉ số, nguồn bằng chứng, ngưỡng và người chịu trách nhiệm.
- Thiết kế kiểm chứng khi vận hành cho xác thực, phân quyền, dữ liệu, logging và phục hồi.
- Phân biệt vi phạm yêu cầu với thiếu bằng chứng hoặc ngoại lệ đã được phê duyệt.
- Liên kết phát hiện với hồ sơ rủi ro, thay đổi kiến trúc, kiểm thử và quyết định xử lý.

Các ngưỡng, thời hạn, mã định danh và tình huống trong bài là ví dụ thiết kế cho một hệ thống giả định. Chúng phải được điều chỉnh theo rủi ro, hợp đồng và nghĩa vụ thực sự áp dụng; không phải ngưỡng mặc định của NIST hay cam kết tuân thủ pháp lý.

## 2. Giám sát điều gì?

Giả sử một cổng quản trị hóa đơn có yêu cầu: “Mọi truy cập chức năng xuất hóa đơn của người dùng quản trị phải có xác thực đa yếu tố và kiểm tra quyền theo tổ chức sở hữu dữ liệu.”

Một biểu đồ đếm đăng nhập thành công chưa chứng minh yêu cầu này được đáp ứng. Cần biết đường truy cập nào tồn tại, tài khoản nào thuộc phạm vi, quyết định quyền được thực hiện ở đâu, chính sách nào đang chạy và có bằng chứng kiểm chứng hành vi từ đầu đến cuối hay không.

| Đối tượng theo dõi | Câu hỏi cần trả lời | Ví dụ bằng chứng |
| --- | --- | --- |
| Yêu cầu bảo mật | Hành vi thực tế còn thỏa tiêu chí đã chấp thuận? | Kiểm thử truy cập hợp lệ và truy cập phải bị từ chối |
| Hiệu lực kiểm soát | Cơ chế triển khai có hoạt động đúng trong phạm vi đã định? | Kết quả kiểm tra chính sách, cấu hình triển khai và hành vi |
| Giả định rủi ro | Tài sản, tác nhân, luồng dữ liệu hoặc mức phơi nhiễm có đổi? | Thay đổi kiến trúc, endpoint mới, sự kiện từ nhà cung cấp |
| Bằng chứng tuân thủ | Bằng chứng có đủ phạm vi, thời gian và nguồn gốc để kiểm tra? | Báo cáo có phiên bản, truy vấn tái lập được, hồ sơ phê duyệt |
| Quy trình phản ứng | Phát hiện có được giao người xử lý và đóng bằng kiểm chứng? | Ticket, quyết định rủi ro và kết quả kiểm tra lại |

Giám sát vận hành, kiểm thử bảo mật và kiểm toán bổ sung cho nhau. Dữ liệu vận hành cho thấy điều đang xảy ra; kiểm thử chủ động tạo tình huống để kiểm chứng cả các nhánh hiếm gặp; kiểm toán xem xét bằng chứng và cách thực hiện trong một phạm vi xác định. Không nên lấy một loại bằng chứng thay cho mọi loại kết luận.

### Liên tục không có nghĩa mọi phép kiểm tra chạy từng giây

Chương trình giám sát có thể kết hợp tín hiệu theo sự kiện, kiểm tra định kỳ và đánh giá thủ công. NIST SP 800-137 đặt trọng tâm vào khả năng nhìn thấy tài sản, mối đe dọa, điểm yếu và hiệu lực kiểm soát để hỗ trợ phản ứng theo rủi ro. [Nguồn: NIST SP 800-137](https://csrc.nist.gov/pubs/sp/800/137/final).

Trong thiết kế minh họa, thay đổi quyền đặc biệt có thể cần được xử lý ngay; đối soát danh sách tài khoản thực hiện mỗi ngày; diễn tập phục hồi theo tháng hoặc khi đổi kiến trúc lưu trữ. Tần suất phải tương ứng với hậu quả và khoảng thời gian tổ chức có thể chấp nhận việc chưa nhận ra sai lệch.

## 3. Đầu vào và đầu ra của một kế hoạch Monitor

Trước khi chọn công cụ, cần xác định các đầu vào:

1. Danh mục tài sản, chủ sở hữu, môi trường và luồng dữ liệu thuộc phạm vi.
2. Danh sách yêu cầu có mã định danh và tiêu chí kiểm chứng.
3. Mô hình đe dọa, sổ đăng ký rủi ro và giả định đã dùng để chấp nhận rủi ro.
4. Ánh xạ yêu cầu với thành phần kiến trúc, kiểm soát và ca kiểm thử.
5. Danh sách ngoại lệ, biện pháp bù đắp, người phê duyệt và ngày hết hạn.
6. Nguồn bằng chứng, quyền truy cập, lịch thu thập và thời hạn lưu được phê duyệt.

Đầu ra hữu ích không chỉ là dashboard. Cần có kết luận theo yêu cầu, bằng chứng đi kèm, việc cần xử lý, thay đổi đối với rủi ro còn lại và quyết định có tiếp tục vận hành trong điều kiện hiện tại hay không.

~~~mermaid
flowchart TD
    A["Rủi ro và nghĩa vụ áp dụng"] --> B["Yêu cầu có tiêu chí kiểm chứng"]
    B --> C["Kiểm soát và thành phần kiến trúc"]
    C --> D["Thu thập bằng chứng khi vận hành"]
    D --> E{"Đủ bằng chứng và còn đáp ứng?"}
    E -->|"Đủ, đáp ứng"| F["Ghi nhận kết quả và tiếp tục theo dõi"]
    E -->|"Thiếu hoặc sai lệch"| G["Phân loại, đánh giá tác động, giao xử lý"]
    G --> H["Khắc phục hoặc quyết định rủi ro có thẩm quyền"]
    H --> I["Kiểm chứng lại, cập nhật hồ sơ"]
    I --> B
    F --> D
~~~

Vòng phản hồi phải quay lại đặc tả yêu cầu. Nếu một đường truy cập mới không thuộc phạm vi kiểm tra cũ, chỉ sửa cảnh báo sẽ chưa giải quyết khoảng trống thiết kế.

## 4. Chuyển yêu cầu thành hợp đồng giám sát

Một hợp đồng giám sát mô tả rõ khi nào được kết luận, khi nào phải báo động và ai chịu trách nhiệm. Có thể dùng mẫu sau trong tài liệu yêu cầu:

| Thành phần | Nội dung cần đặc tả |
| --- | --- |
| Mã yêu cầu và phiên bản | Định danh ổn định, phiên bản yêu cầu đang có hiệu lực |
| Rủi ro liên quan | Tình huống đe dọa, tài sản và hậu quả cần giảm |
| Phạm vi | Endpoint, tài khoản, tổ chức, dữ liệu, môi trường, trường hợp loại trừ |
| Tiêu chí cần duy trì | Hành vi hoặc trạng thái phải đúng |
| Phương pháp kiểm chứng | Đối soát cấu hình, quan sát sự kiện, kiểm thử chủ động hoặc xem xét hồ sơ |
| Định nghĩa phép đo | Tử số, mẫu số, đơn vị, cửa sổ thời gian, quy tắc khử trùng lặp |
| Chất lượng bằng chứng | Nguồn, độ mới, độ bao phủ, phiên bản chính sách, độ trễ cho phép |
| Ngưỡng và thời hạn | Điều kiện vi phạm, mất dữ liệu, xác nhận và phản ứng |
| Quyền xử lý | Người trực nhận cảnh báo, chủ kiểm soát, chủ rủi ro, tuyến escalation |
| Điều kiện đóng | Bằng chứng kiểm chứng lại, kết quả trên đúng phạm vi và quyết định liên quan |

### Ví dụ MON-AUTH-01: duy trì MFA cho đường quản trị

**Rủi ro:** kẻ tấn công sử dụng mật khẩu bị lộ để xuất dữ liệu hóa đơn.

**Yêu cầu SEC-AUTH-04 phiên bản 3:** mọi người dùng tương tác truy cập chức năng quản trị thuộc phạm vi phải đi qua chính sách MFA được phê duyệt. Danh tính máy được quản lý theo yêu cầu riêng. Tài khoản khẩn cấp, nếu có, phải nằm trong cơ chế ngoại lệ và giám sát riêng.

Hợp đồng giám sát minh họa:

- Đối soát danh sách tài khoản quản trị đang hiệu lực với chính sách áp dụng ít nhất mỗi 24 giờ và sau thay đổi quyền.
- Sau mỗi thay đổi cấu hình truy cập, chạy kiểm thử bằng tài khoản thử: luồng đạt chính sách được phép đi tiếp; luồng thiếu điều kiện phải bị chặn trước khi có dữ liệu.
- Dùng quyết định chính sách từ nguồn xác thực đáng tin cậy, gồm ngữ cảnh MFA phù hợp, thay vì chỉ tin một trường do trình duyệt tự gửi.
- Cảnh báo khi phát hiện một đường truy cập quản trị bỏ qua chính sách hoặc tài khoản không nằm trong chính sách bắt buộc.
- Nếu ảnh chụp cấu hình gần nhất quá 24 giờ, trạng thái bằng chứng là UNKNOWN; không suy luận rằng chính sách vẫn đúng.
- Nhóm IAM sở hữu kiểm soát; nhóm ứng dụng sở hữu kiểm thử đường truy cập; người trực nhận cảnh báo xác nhận trong 15 phút theo lịch trực đã cam kết.
- Chỉ đóng phát hiện sau khi cấu hình thực tế và kiểm thử đầu cuối cùng chứng minh đường truy cập đã được bảo vệ.

“Có đăng ký MFA” và “MFA được thực thi đúng khi truy cập tài nguyên” là hai mệnh đề khác nhau. Nếu chỉ đo tỷ lệ đăng ký, hệ thống có thể báo đạt dù tồn tại phiên cũ, endpoint khác hoặc chính sách chưa bao phủ hết phạm vi.

## 5. Thiết kế phép đo và cách kết luận

### 5.1. Bao phủ phải dựa trên danh mục tài sản

Ví dụ định nghĩa:

~~~text
Độ bao phủ bằng chứng mới
  = số tài sản trong phạm vi có bằng chứng hợp lệ còn hạn
    / tổng số tài sản trong phạm vi

Tỷ lệ đáp ứng được chứng minh
  = số tài sản trong phạm vi có kết quả PASS còn hạn
    / tổng số tài sản trong phạm vi

Tỷ lệ quá hạn xử lý
  = số phát hiện đang mở đã vượt hạn
    / tổng số phát hiện đang mở thuộc phạm vi đo
~~~

Nếu mẫu số bằng 0, cần báo N/A và giải thích phạm vi; không tự hiển thị 100%.

Giả sử danh mục có 100 dịch vụ. Có 80 dịch vụ gửi bằng chứng mới: 78 PASS, 2 FAIL; 20 dịch vụ còn lại chưa có bằng chứng hợp lệ.

- Độ bao phủ bằng chứng mới: 80/100 = 80%.
- Tỷ lệ đáp ứng được chứng minh: 78/100 = 78%.
- Tỷ lệ PASS trong nhóm đã có bằng chứng: 78/80 = 97,5%.

Con số 97,5% chỉ mô tả nhóm đã quan sát. Báo cáo phải thể hiện 20 dịch vụ UNKNOWN và 2 dịch vụ FAIL để người ra quyết định nhìn thấy khoảng trống.

Danh mục dùng làm mẫu số cần được đối soát với nguồn cấp phát hoặc nguồn triển khai. Nếu một dịch vụ bị bỏ sót khỏi cả inventory lẫn collector, dashboard nội bộ có thể nhất quán nhưng vẫn thiếu phạm vi thực tế.

### 5.2. Trạng thái bằng chứng và ngoại lệ là hai chiều khác nhau

| Trạng thái đánh giá | Ý nghĩa |
| --- | --- |
| PASS | Bằng chứng còn hạn cho thấy đạt tiêu chí trong phạm vi đã kiểm tra |
| FAIL | Có bằng chứng không đạt ít nhất một tiêu chí |
| UNKNOWN | Bằng chứng thiếu, lỗi, không đáng tin cậy hoặc hết hạn |
| NOT_APPLICABLE | Có căn cứ được xem xét rằng yêu cầu không áp dụng cho đối tượng này |

Ngoại lệ đã phê duyệt nên là thuộc tính đi kèm, không ghi đè kết quả đánh giá. Một kiểm soát FAIL có ngoại lệ còn hiệu lực vẫn là FAIL về kỹ thuật; hồ sơ ngoại lệ giải thích điều kiện được phép tiếp tục vận hành, người chấp nhận rủi ro và hạn xử lý.

Một PASS cũng cần giới hạn kết luận. Kiểm thử một nhóm endpoint tại một thời điểm không chứng minh mọi endpoint khác hoặc toàn bộ thời gian giữa hai lần kiểm thử đều đạt.

### 5.3. Chỉ số kiểm soát và chỉ số rủi ro

Chỉ số kiểm soát cho biết cơ chế đang được duy trì như thế nào, chẳng hạn tỷ lệ tài khoản quản trị nằm trong chính sách bắt buộc. Chỉ số rủi ro theo dõi mức phơi nhiễm hoặc hậu quả tiềm ẩn, chẳng hạn số đường xuất dữ liệu nhạy cảm chưa được kiểm chứng sau thay đổi.

Số cảnh báo tăng có thể do tấn công tăng, triển khai thêm detector hoặc tăng độ bao phủ. Cần phân tích nguyên nhân thay đổi trước khi kết luận mức rủi ro tăng tương ứng. Tương tự, không có cảnh báo có thể do hệ thống thu thập đã hỏng.

## 6. Giám sát năm nhóm yêu cầu bảo mật

### 6.1. Xác thực

Theo dõi các chính sách thực sự được áp dụng: MFA, vòng đời tài khoản, thu hồi phiên và thông tin xác thực, tài khoản khẩn cấp và danh tính dịch vụ.

Ví dụ yêu cầu thu hồi: “Sau khi tài khoản nhân viên bị vô hiệu hóa, mọi truy cập quản trị qua các đường đã liệt kê phải bị từ chối trong tối đa 5 phút.” Kế hoạch đo phải nêu rõ mốc bắt đầu từ hệ thống danh tính, các loại phiên/token thuộc phạm vi, đồng hồ tham chiếu và cách thử mà không dùng tài khoản thật của nhân viên.

Giám sát số tài khoản bị vô hiệu hóa chưa chứng minh phiên cũ đã mất hiệu lực. Cần kiểm chứng hành vi truy cập sau thu hồi trên các cơ chế thực tế của kiến trúc.

### 6.2. Phân quyền

Theo dõi thay đổi quyền đặc biệt, sai lệch chính sách, quyền tồn đọng và ranh giới giữa các tổ chức hoặc khách hàng.

Ví dụ SEC-AUTHZ-07: “Người dùng tổ chức A không thể đọc hoặc xuất hóa đơn của tổ chức B qua API, giao diện, tác vụ nền hoặc đường tải file.” Bằng chứng nên kết hợp kiểm thử truy cập bị từ chối với kiểm thử truy cập hợp lệ, dùng dữ liệu tổng hợp cho các tổ chức thử độc lập.

Tỷ lệ phản hồi HTTP 403 cao không chứng minh chính sách đúng: dịch vụ hỏng có thể từ chối cả yêu cầu hợp lệ. Kết quả cần kiểm tra cả quyền cho phép, quyền từ chối và sự vắng mặt của dữ liệu hoặc tác dụng phụ không được phép.

### 6.3. Dữ liệu

Theo dõi nơi lưu trữ và truyền dữ liệu, quyền truy cập, cấu hình mã hóa, sử dụng khóa, lưu giữ và xóa dữ liệu theo yêu cầu đã được phê duyệt.

Ví dụ: khi xuất hiện kho lưu trữ mới trong luồng hóa đơn, chương trình giám sát phải đối soát kho đó với phân loại dữ liệu và chủ sở hữu, thay vì chỉ kiểm tra những kho đã được đăng ký thủ công trước đây.

Với yêu cầu xóa dữ liệu, bằng chứng cần phân biệt dữ liệu đang phục vụ, bản sao tìm kiếm, cache và bản sao lưu. Kết luận phải phản ánh cơ chế và thời hạn áp dụng cho từng loại; một lần xóa bản ghi khỏi cơ sở dữ liệu chính không chứng minh mọi bản sao đã biến mất.

### 6.4. Logging và khả năng điều tra

Theo dõi sự hiện diện của các sự kiện bắt buộc, trường dữ liệu, độ trễ gửi, tính toàn vẹn và quyền truy cập log.

Ví dụ SEC-LOG-03: mọi thao tác thay đổi quyền quản trị phải tạo bản ghi có mã chủ thể, mã đối tượng, hành động, kết quả, thời gian sự kiện, mã tương quan và phiên bản chính sách liên quan. Không ghi mật khẩu, access token, khóa bí mật hoặc toàn bộ nội dung hóa đơn vào log để phục vụ phép đo này.

Kiểm thử phải phát sinh thao tác tổng hợp có mã tương quan rồi kiểm tra cả đường đi đến nơi lưu bằng chứng và quy tắc cảnh báo. Heartbeat của collector chỉ chứng minh collector còn gửi heartbeat, chưa chứng minh sự kiện bắt buộc được ứng dụng tạo đúng.

### 6.5. Phục hồi

Theo dõi kết quả sao lưu, độ mới bản sao có thể dùng, khả năng truy cập khóa khi phục hồi, quyền hạn trong môi trường phục hồi và kết quả diễn tập.

Ví dụ yêu cầu giả định: RPO tối đa 15 phút và RTO tối đa 2 giờ cho dịch vụ hóa đơn. Kế hoạch diễn tập phải định nghĩa:

- RPO được đánh giá qua mốc dữ liệu nhất quán cuối cùng khôi phục được so với thời điểm sự cố giả lập.
- RTO được đo từ mốc bắt đầu đã thỏa thuận đến khi chức năng nghiệp vụ đáp ứng tiêu chí sẵn sàng đã định.
- Kiểm tra bao gồm phụ thuộc như danh tính, khóa, cấu hình mạng và dữ liệu tham chiếu.
- Môi trường diễn tập bảo vệ dữ liệu và giới hạn người truy cập tương ứng với yêu cầu.

Thông báo “backup succeeded” là bằng chứng một tác vụ kết thúc theo tiêu chí của công cụ. Muốn chứng minh phục hồi đạt yêu cầu phải có thử khôi phục và kiểm tra dữ liệu, chức năng, thời gian thực tế.

## 7. Chất lượng bằng chứng và giám sát chính hệ thống giám sát

Một chuỗi bằng chứng thường gồm ứng dụng hoặc nền tảng nguồn, bộ thu thập, đường truyền, nơi lưu, phép chuyển đổi, truy vấn và báo cáo. Mỗi mắt xích có thể làm mất, làm trễ hoặc diễn giải sai dữ liệu.

Cần đặc tả ít nhất các thuộc tính sau:

- **Nguồn gốc:** hệ thống phát sinh, danh tính thực hiện thu thập, môi trường và đối tượng được kiểm tra.
- **Ngữ cảnh:** mã yêu cầu, phiên bản chính sách, phiên bản triển khai và phạm vi.
- **Thời gian:** thời điểm xảy ra, thời điểm thu nhận, múi giờ, giới hạn lệch đồng hồ và độ trễ cho phép.
- **Độ đầy đủ:** sự kiện kỳ vọng, sự kiện bị mất, tài sản không báo cáo, khoảng thời gian bị đứt dữ liệu.
- **Khả năng tái lập:** truy vấn hoặc phiên bản công cụ, tham số và dữ liệu đầu vào cần để kiểm tra lại.
- **Bảo vệ:** quyền đọc/ghi/xóa, lưu giữ, sao lưu bằng chứng và dấu vết truy cập bằng chứng.

Hash giúp phát hiện thay đổi so với giá trị tham chiếu đã biết; bản thân một hash đặt cạnh file chưa chứng minh ai đã tạo file hoặc dữ liệu nguồn là đúng. Nếu rủi ro bao gồm sửa log, cần thiết kế bảo vệ cả nguồn, quyền quản trị, nơi lưu và cơ chế đối chiếu phù hợp.

### Ba phép thử cho đường giám sát

1. **Thử đầu cuối:** tạo sự kiện tổng hợp an toàn, xác minh bản ghi và cảnh báo được tạo đúng.
2. **Thử mất nguồn:** chủ động ngừng một nguồn thử, xác minh trạng thái chuyển sang UNKNOWN và có người nhận thông báo.
3. **Thử khôi phục:** khôi phục đường truyền, kiểm tra dữ liệu bị trễ hoặc phát lại không tạo kết luận hoặc ticket trùng lặp.

Các phép thử cần giới hạn phạm vi và có chủ sở hữu. Không đưa dữ liệu nhạy cảm thật vào sự kiện tổng hợp chỉ để kiểm tra đường gửi log.

Thời hạn lưu bằng chứng phải dựa trên mục đích, thời gian điều tra, hợp đồng và nghĩa vụ áp dụng. Có thể cho dashboard xem số liệu tổng hợp trong khi giới hạn chặt quyền truy cập log chi tiết; không cần sao chép toàn bộ dữ liệu gốc vào mọi báo cáo.

## 8. Theo dõi thay đổi và quyết định đánh giá lại

Giám sát sai lệch cấu hình chỉ hữu ích khi baseline có phiên bản và được phê duyệt. Một thay đổi hợp lệ vẫn có thể tạo ra rủi ro mới cần đánh giá.

| Sự kiện thay đổi | Điều cần xem xét lại |
| --- | --- |
| Mở endpoint quản trị hoặc public API mới | Ranh giới tin cậy, xác thực, phân quyền, logging và phạm vi kiểm thử |
| Chuyển nhà cung cấp danh tính | Chính sách MFA, thu hồi phiên, thông tin quyết định truy cập và chế độ lỗi |
| Thêm trường dữ liệu nhạy cảm | Phân loại, mục đích xử lý, quyền truy cập, lưu giữ và xóa |
| Thêm nhà cung cấp xử lý dữ liệu | Luồng dữ liệu, trách nhiệm, bằng chứng được chia sẻ và nghĩa vụ hợp đồng |
| Đổi kiến trúc sao lưu hoặc quản lý khóa | Khả năng phục hồi, RPO/RTO và quyền truy cập khi khẩn cấp |
| Phát hiện kỹ thuật tấn công mới liên quan | Giả định đe dọa, khả năng kiểm soát hiện tại và nhu cầu kiểm thử bổ sung |
| Ngừng một thành phần | Thu hồi quyền và bí mật, xử lý dữ liệu còn lại, cập nhật inventory và bằng chứng |

Khi thay đổi, có thể cần quay lại mô hình đe dọa, sửa yêu cầu, bổ sung kiểm thử hoặc đưa quyết định tiếp tục vận hành lên người có thẩm quyền. Không tự động cập nhật baseline theo trạng thái hiện tại rồi xóa cảnh báo: cách đó có thể hợp thức hóa một cấu hình sai.

Nếu đơn vị sử dụng mô hình chấp thuận vận hành, phải quy định sự kiện nào buộc xem xét lại quyết định đó. Đội vận hành cung cấp dữ kiện; người có thẩm quyền quyết định theo cơ chế quản trị đã thiết lập.

## 9. Từ phát hiện đến xử lý rủi ro

Một quy trình xử lý có thể gồm bảy bước:

1. **Xác nhận dữ kiện:** đối chiếu nguồn, phạm vi, thời gian, độ trễ và khả năng detector lỗi.
2. **Phân loại:** vi phạm yêu cầu, thiếu bằng chứng, sai lệch cấu hình, thay đổi phạm vi hoặc dấu hiệu sự cố.
3. **Đánh giá tác động:** tài sản bị ảnh hưởng, mức phơi nhiễm, hậu quả và biện pháp đang còn hiệu lực.
4. **Giao trách nhiệm:** chỉ định chủ kiểm soát, chủ rủi ro, thời hạn và tuyến escalation.
5. **Thực hiện quyết định:** khắc phục, hạn chế chức năng, áp dụng biện pháp bù đắp hoặc xin quyết định chấp nhận rủi ro theo thẩm quyền.
6. **Kiểm chứng lại:** dùng tiêu chí ban đầu và bổ sung kiểm thử hồi quy cho đường sai lệch vừa phát hiện.
7. **Cập nhật hồ sơ:** lưu bằng chứng, sổ rủi ro, yêu cầu, kiến trúc và quyết định đóng hoặc tiếp tục theo dõi.

Nếu phát hiện thể hiện sự cố đang diễn ra, chuyển vào quy trình ứng phó sự cố tương ứng; không chờ tới cuộc họp rà soát rủi ro định kỳ.

Cảnh báo cần gắn với hành động. Ví dụ “có tài khoản quản trị không thuộc chính sách MFA” phải xác định cách chặn đường truy cập, thu hồi quyền hoặc khôi phục chính sách, cùng người được phép thực hiện. Thao tác tự động có tác động nghiệp vụ phải có điều kiện kích hoạt, phạm vi và phương án phục hồi rõ ràng.

### Ngoại lệ phải có thời hạn

Một hồ sơ ngoại lệ nên ghi mã yêu cầu, phạm vi, lý do, hậu quả, biện pháp bù đắp, chủ rủi ro, người phê duyệt, thời điểm hết hạn và tiêu chí kết thúc.

Giám sát ngoại lệ cần trả lời: phạm vi có nở rộng không, biện pháp bù đắp còn hoạt động không, ngày hết hạn có tới gần không và rủi ro còn nằm trong điều kiện đã phê duyệt không. Hết hạn phải kích hoạt xử lý theo chính sách; không tự gia hạn.

Quyết định chấp nhận rủi ro kỹ thuật cũng không tự miễn trừ một nghĩa vụ bắt buộc. Khi cần diễn giải nghĩa vụ hoặc ngoại lệ tuân thủ, phải có người phụ trách phù hợp xem xét căn cứ thực sự áp dụng.

## 10. Truy vết từ bằng chứng đến yêu cầu và nghĩa vụ

Một chuỗi truy vết có ích là:

~~~text
Nghĩa vụ hoặc mục tiêu kiểm soát
  -> rủi ro
  -> yêu cầu có phiên bản
  -> thành phần triển khai
  -> ca kiểm thử / phép đo
  -> bằng chứng theo thời gian và phạm vi
  -> phát hiện
  -> quyết định và kết quả kiểm chứng lại
~~~

Ví dụ cho hệ thống giả định:

| Liên kết | Giá trị minh họa |
| --- | --- |
| Mục tiêu | Hạn chế xuất hóa đơn của tổ chức khác |
| Rủi ro | R-17: người dùng A truy cập dữ liệu B |
| Yêu cầu | SEC-AUTHZ-07 v2 |
| Thành phần | Export API và worker xuất file |
| Kiểm chứng | T-AUTHZ-12: thử hợp lệ cùng tổ chức và thử chéo tổ chức |
| Bằng chứng | Kết quả kiểm thử gắn release, chính sách và thời điểm chạy |
| Phát hiện | F-204: worker không kiểm tra lại quyền của yêu cầu nền |
| Quyết định | Tạm ngừng chức năng bị ảnh hưởng, sửa kiểm soát, thử lại |
| Điều kiện đóng | Hành vi đạt yêu cầu trên API, worker và đường tải kết quả |

Một bảng ánh xạ tới tiêu chuẩn chỉ cho biết mối liên hệ được đề xuất. Để hỗ trợ kết luận tuân thủ, cần xác nhận nghĩa vụ áp dụng, phạm vi, giai đoạn đánh giá và chất lượng bằng chứng. Không suy ra hệ thống đạt toàn bộ tiêu chuẩn chỉ vì một yêu cầu được đánh dấu PASS.

Bằng chứng của dịch vụ dùng chung cũng cần ranh giới rõ ràng. Nhóm IAM có thể chứng minh cấu hình chính sách; nhóm ứng dụng vẫn phải chứng minh ứng dụng dùng đúng chính sách trên mọi đường truy cập thuộc phạm vi.

## 11. Tình huống: quyền quản trị vượt khỏi chính sách

Cổng hóa đơn có 100 tài khoản quản trị trong inventory. Ảnh chụp cấu hình mới cho thấy 97 tài khoản thuộc chính sách MFA bắt buộc; 3 tài khoản vừa được tạo qua một luồng quản trị cũ chưa được bao phủ. Bộ thu thập vẫn hoạt động bình thường.

**Kết luận đầu tiên:** độ bao phủ bằng chứng cấu hình là 100/100, còn tỷ lệ tài khoản có cấu hình đạt là 97/100. Ba tài khoản là FAIL, không phải UNKNOWN. Tuy nhiên, số liệu cấu hình này chưa đủ chứng minh toàn bộ hành vi đăng nhập của 97 tài khoản còn lại.

**Xác minh:** nhóm IAM đối chiếu cấu hình và phiên bản chính sách; nhóm ứng dụng dùng tài khoản thử để kiểm chứng đường truy cập qua luồng cũ. Kết quả xác nhận có thể đi tới chức năng quản trị khi chưa đáp ứng MFA.

**Xử lý trước mắt:** người có quyền quyết định áp dụng biện pháp hạn chế phù hợp cho đường bị ảnh hưởng. Nếu có dấu hiệu truy cập trái phép, nhóm ứng phó sự cố điều tra theo quy trình riêng.

**Khắc phục:** sửa luồng cấp tài khoản, đối soát lại toàn bộ tài khoản và kiểm thử đường truy cập. Bổ sung kiểm thử sau thay đổi quyền, đồng thời yêu cầu tài khoản mới thuộc chính sách bắt buộc trước khi được sử dụng.

**Cập nhật rủi ro:** hồ sơ ghi khoảng thời gian có thể bị phơi nhiễm, phạm vi dữ liệu, độ tin cậy của bằng chứng và những điều chưa biết. Không viết “không có khai thác” chỉ vì không tìm thấy bản ghi, nhất là khi tính đầy đủ của log trong giai đoạn đó chưa được chứng minh.

**Đóng phát hiện:** cần kết quả kiểm chứng lại, bằng chứng cho các tài khoản và đường truy cập liên quan, xác nhận của chủ kiểm soát và cập nhật tài liệu yêu cầu. Việc ticket sửa lỗi đã merge chưa đủ để đóng.

## 12. Tích hợp Monitor vào vòng đời phát triển

| Giai đoạn | Công việc gắn với yêu cầu |
| --- | --- |
| Phân tích | Định nghĩa rủi ro, đối tượng trong phạm vi và bằng chứng chấp nhận được |
| Thiết kế | Bố trí điểm thực thi, điểm quan sát, quyền truy cập bằng chứng và chế độ khi mất dữ liệu |
| Xây dựng | Triển khai kiểm soát, sự kiện bắt buộc, kiểm thử và phiên bản chính sách |
| Phát hành | Xác nhận đường giám sát chạy, có người nhận cảnh báo và tiêu chí chặn phát hành |
| Vận hành | Đối soát phạm vi, đánh giá bằng chứng, xử lý sai lệch và ngoại lệ |
| Thay đổi | Đánh giá tác động, cập nhật mô hình đe dọa, yêu cầu và ca kiểm thử |
| Kết thúc sử dụng | Thu hồi truy cập, xử lý dữ liệu còn lại và lưu bằng chứng theo chính sách |

Các kiểm soát quan trọng nên có tiêu chí sẵn sàng vận hành: nguồn dữ liệu đã kết nối, phép đo có định nghĩa, người nhận cảnh báo đã được phân công, kịch bản mất nguồn đã được thử và bằng chứng có thể truy xuất.

Không áp dụng chung một phản ứng khi thiếu bằng chứng. Với một đường xuất dữ liệu nhạy cảm, tổ chức có thể chọn hạn chế chức năng khi mất khả năng kiểm chứng; với chức năng khác, có thể dùng biện pháp thay thế trong thời gian ngắn. Quyết định phải được thiết kế và phê duyệt theo tác động thực tế.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Đo những gì công cụ có sẵn | Chỉ số nhiều nhưng không trả lời yêu cầu nào còn đạt | Bắt đầu từ yêu cầu và quyết định cần hỗ trợ |
| Chỉ đếm nguồn đang gửi dữ liệu | Tài sản mất giám sát biến mất khỏi mẫu số | Đối soát với inventory và nguồn cấp phát độc lập |
| Coi mất dữ liệu là không có vi phạm | Tạo trạng thái an toàn giả | Định nghĩa độ mới và chuyển sang UNKNOWN khi hết hạn |
| Chỉ xem cấu hình | Bỏ sót đường truy cập hoặc hành vi thực tế | Kết hợp kiểm thử đầu cuối và đối soát kiến trúc |
| Chỉ kiểm thử truy cập bị từ chối | Hệ thống từ chối mọi thứ vẫn có thể được chấm đạt | Kiểm tra cả truy cập được phép và tác dụng phụ |
| Tự cập nhật baseline để hết cảnh báo | Che mất sai lệch chưa được phê duyệt | Quản lý phiên bản và phê duyệt thay đổi baseline |
| Có ngoại lệ nhưng không có ngày hết hạn | Rủi ro tạm thời tồn tại vô thời hạn | Theo dõi hạn và hiệu lực biện pháp bù đắp |
| Chỉ đóng theo trạng thái ticket | Chưa chứng minh yêu cầu được khôi phục | Đóng bằng kiểm chứng lại trên phạm vi thực tế |
| Thu thập quá nhiều dữ liệu nhạy cảm | Tăng hậu quả khi kho giám sát bị lộ | Thu thập tối thiểu đủ mục đích và giới hạn quyền |
| Báo cáo một tỷ lệ trung bình duy nhất | Che một tài sản quan trọng đang FAIL | Thể hiện mức quan trọng, phạm vi và phân bố trạng thái |

## 14. Thực hành xây dựng kế hoạch Monitor

Với chức năng xuất hóa đơn, lập một bảng giám sát tối thiểu cho năm yêu cầu: xác thực quản trị, cách ly giữa các tổ chức, bảo vệ file xuất, ghi nhận thao tác và phục hồi dịch vụ.

Với mỗi yêu cầu, hãy xác định:

1. Rủi ro và thành phần kiến trúc cần theo dõi.
2. Phạm vi, tiêu chí PASS/FAIL và giới hạn kết luận.
3. Nguồn bằng chứng, độ mới, tử số và mẫu số.
4. Tần suất và sự kiện buộc kiểm chứng lại.
5. Quy tắc UNKNOWN và cách nhận biết lỗi đường giám sát.
6. Người chịu trách nhiệm, thời hạn phản ứng và thẩm quyền quyết định.
7. Bằng chứng cần có để đóng sai lệch.
8. Cách cập nhật sổ rủi ro, yêu cầu và ca kiểm thử.

Sau đó xét ba tình huống: một worker xuất file mới chưa có trong inventory; nguồn log bị ngắt; một ngoại lệ phân quyền hết hạn. Một kế hoạch đạt mục tiêu phải chỉ ra được cách phát hiện từng tình huống, người nhận việc và quyết định cần đưa ra.

Monitor có giá trị khi bằng chứng dẫn tới hành động và cải thiện yêu cầu. Kết quả mong muốn là tổ chức biết điều gì còn được bảo đảm, điều gì đã sai lệch, điều gì chưa thể kết luận và ai đang xử lý phần rủi ro còn lại.
