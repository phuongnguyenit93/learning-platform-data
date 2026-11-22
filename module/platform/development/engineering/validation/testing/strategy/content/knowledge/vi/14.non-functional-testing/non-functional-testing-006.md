# Lập ma trận tương thích giữa nền tảng, phiên bản và cấu hình

Một sản phẩm có thể hoạt động đúng trên máy của lập trình viên nhưng gặp lỗi trên trình duyệt, hệ điều hành, thiết bị hoặc cấu hình khác. Sự khác biệt có thể đến từ phiên bản runtime, kích thước màn hình, quyền truy cập, ngôn ngữ, múi giờ, cơ sở dữ liệu, trình điều khiển, tính năng được bật hoặc dịch vụ tích hợp. Kiểm thử trên một môi trường duy nhất vì vậy không đủ để chứng minh sản phẩm tương thích với toàn bộ môi trường được hỗ trợ.

**Ma trận tương thích** là cách ghi nhận có cấu trúc các tổ hợp nền tảng, phiên bản và cấu hình mà sản phẩm cần hỗ trợ, cùng với mức ưu tiên và bằng chứng kiểm thử cho từng tổ hợp. Ma trận giúp nhóm thống nhất phạm vi hỗ trợ, lựa chọn môi trường đại diện, phân bổ công sức kiểm thử và báo cáo rõ những tổ hợp đã xác minh hoặc còn rủi ro.

Trong chiến lược kiểm thử xác thực, ma trận tương thích phải xuất phát từ người dùng và môi trường sử dụng dự kiến. Nó không phải danh sách mọi tổ hợp kỹ thuật có thể tồn tại. Mục tiêu là xác định những môi trường có ý nghĩa đối với sản phẩm, đánh giá rủi ro tại các ranh giới khác nhau và tạo bằng chứng đủ tin cậy cho quyết định phát hành.

## 1. Vì sao cần ma trận tương thích?

Sản phẩm thường chạy trên nhiều tổ hợp phần cứng và phần mềm. Chỉ một thay đổi nhỏ ở trình duyệt, runtime hoặc cấu hình cũng có thể làm thay đổi hành vi. Ví dụ:

- Một API trình duyệt mới chỉ có ở phiên bản mới khiến chức năng không hoạt động trên phiên bản cũ.
- Giao diện bị tràn hoặc nút thao tác bị che trên màn hình nhỏ.
- Cách xử lý font, ngày tháng, số thập phân hoặc múi giờ khác nhau giữa môi trường.
- Một phiên bản hệ điều hành áp dụng quyền truy cập tệp hoặc thông báo khác với phiên bản trước.
- Driver cơ sở dữ liệu hoặc cấu hình collation làm thay đổi thứ tự sắp xếp và so sánh chuỗi.
- Một tính năng được bật bằng feature flag trên môi trường staging nhưng chưa được bật trong môi trường sản xuất.
- Bộ nhớ, CPU hoặc giới hạn kết nối khác nhau khiến hiệu năng và độ ổn định thay đổi.

Ma trận tương thích giúp:

1. **Xác định phạm vi hỗ trợ:** Biết rõ nền tảng và phiên bản nào thuộc cam kết sản phẩm.
2. **Lập kế hoạch kiểm thử:** Chọn tổ hợp cần kiểm tra trực tiếp, tổ hợp có thể mô phỏng và tổ hợp cần kiểm tra bổ sung.
3. **Ưu tiên theo rủi ro:** Dành nguồn lực cho môi trường có nhiều người dùng, có tác động lớn hoặc có lịch sử lỗi.
4. **Tránh khoảng trống:** Nhận ra nền tảng hoặc cấu hình quan trọng chưa có bằng chứng.
5. **Hỗ trợ điều tra:** Biết phiên bản, cấu hình và môi trường của một lỗi để tái hiện chính xác hơn.
6. **Quản lý thay đổi:** Đánh giá tác động khi sản phẩm nâng cấp thư viện, runtime, trình duyệt hoặc dịch vụ phụ thuộc.
7. **Giao tiếp rõ ràng:** Giúp đội phát triển, QA, vận hành, hỗ trợ và người dùng hiểu phạm vi được hỗ trợ.

## 2. Xác định các chiều của ma trận

Trước khi liệt kê tổ hợp, cần xác định các chiều có thể làm thay đổi hành vi. Không phải sản phẩm nào cũng cần mọi chiều dưới đây; chỉ đưa vào những yếu tố có liên quan đến kiến trúc, người dùng và rủi ro.

### 2.1. Nền tảng

Nền tảng là môi trường cơ bản nơi sản phẩm được chạy hoặc sử dụng. Tùy loại sản phẩm, có thể gồm:

- Hệ điều hành máy tính: Windows, macOS, Linux và các bản phân phối được hỗ trợ.
- Thiết bị di động: iOS, Android, loại thiết bị và kiến trúc CPU.
- Trình duyệt: Chrome, Edge, Firefox, Safari hoặc trình duyệt nhúng trong ứng dụng.
- Runtime hoặc nền tảng thực thi: JVM, .NET, Node.js, Python runtime, container runtime.
- Hạ tầng: máy chủ vật lý, máy ảo, container, nền tảng cloud hoặc môi trường on-premises.
- Dịch vụ lưu trữ và dữ liệu: loại cơ sở dữ liệu, message broker, hệ thống tệp hoặc cache.

Hãy ghi rõ tên nền tảng và loại biến thể cần phân biệt. Ví dụ “Linux” có thể chưa đủ nếu sản phẩm chỉ được hỗ trợ trên một số bản phân phối hoặc phiên bản kernel nhất định.

### 2.2. Phiên bản

Phiên bản có thể là phiên bản hệ điều hành, trình duyệt, runtime, framework, driver, cơ sở dữ liệu hoặc giao thức. Cần quyết định mức chi tiết phù hợp:

- Phiên bản chính (major) nếu các phiên bản nhỏ được nhà cung cấp cập nhật tương thích và sản phẩm không phụ thuộc vào khác biệt đó.
- Phiên bản cụ thể nếu có thay đổi hành vi, chính sách hỗ trợ hoặc lỗi đã biết.
- Khoảng phiên bản nếu cam kết hỗ trợ một dải, chẳng hạn từ phiên bản tối thiểu đến phiên bản hiện hành.
- Kênh phát hành nếu có khác biệt giữa stable, extended support, beta hoặc preview.

Không nên ghi “phiên bản mới nhất” mà không xác định thời điểm và chính sách cập nhật. Phiên bản mới nhất thay đổi theo thời gian; ma trận cần cho biết ai cập nhật, khi nào kiểm tra lại và cách xử lý phiên bản vừa phát hành.

### 2.3. Cấu hình

Cấu hình là các giá trị hoặc điều kiện có thể thay đổi cách sản phẩm hoạt động. Ví dụ:

| Nhóm cấu hình | Ví dụ |
|---|---|
| Phần cứng | CPU architecture, RAM, số lõi, độ phân giải, dung lượng lưu trữ |
| Hiển thị | Kích thước viewport, mật độ điểm ảnh, hướng màn hình, zoom |
| Ngôn ngữ và khu vực | Locale, định dạng ngày/giờ, dấu thập phân, đơn vị đo |
| Thời gian | Múi giờ, đồng hồ hệ thống, thời điểm chuyển giờ mùa hè |
| Mạng | Băng thông, độ trễ, proxy, TLS, mất kết nối, giới hạn timeout |
| Quyền và bảo mật | Vai trò người dùng, quyền tệp, chính sách cookie, cơ chế xác thực |
| Tính năng | Feature flag, module bật/tắt, cấu hình thử nghiệm |
| Dữ liệu | Collation, encoding, múi giờ lưu trữ, kích thước dữ liệu, trạng thái ban đầu |
| Tích hợp | Phiên bản API, endpoint sandbox/production, driver và credential theo môi trường |

Chỉ ghi cấu hình có thể ảnh hưởng đến hành vi hoặc kết quả kiểm thử. Nếu đưa quá nhiều chi tiết không liên quan vào ma trận, việc duy trì sẽ tốn công mà không cải thiện bằng chứng.

### 2.4. Người dùng và bối cảnh sử dụng

Một số khác biệt không nằm ở công nghệ mà ở cách người dùng tương tác:

- Vai trò hoặc quyền hạn khác nhau.
- Thiết bị dùng bằng cảm ứng, bàn phím hoặc công nghệ hỗ trợ.
- Kết nối mạng ổn định hoặc gián đoạn.
- Khu vực địa lý, ngôn ngữ và quy định địa phương.
- Khối lượng dữ liệu hoặc số lượng người dùng đồng thời.

Các yếu tố này có thể được quản lý trong một ma trận riêng hoặc bổ sung thành chiều của ma trận tương thích nếu chúng tác động đến kết quả xác nhận.

## 3. Phân biệt tổ hợp được hỗ trợ và tổ hợp cần kiểm thử

Không phải tổ hợp có thể chạy được đều thuộc phạm vi hỗ trợ. Ma trận cần thể hiện ít nhất ba trạng thái:

- **Được hỗ trợ:** Sản phẩm cam kết hoạt động theo yêu cầu đã công bố trên tổ hợp này.
- **Được kiểm thử:** Tổ hợp đã được thực hiện kiểm thử và có bằng chứng tương ứng. Một tổ hợp có thể được hỗ trợ nhưng chưa được kiểm tra trong chu kỳ hiện tại; đây là khoảng trống cần đánh giá.
- **Không hỗ trợ:** Sản phẩm không cam kết hoạt động trên tổ hợp này. Nếu người dùng vẫn sử dụng, nhóm cần có cách phản hồi và hướng dẫn rõ ràng.

Có thể thêm trạng thái như “đang đánh giá”, “đã lỗi thời”, “bị chặn” hoặc “có ngoại lệ”. Tránh dùng một trạng thái chung để biểu thị cả phạm vi hỗ trợ và kết quả kiểm thử; đây là hai thông tin khác nhau.

Ví dụ, một ứng dụng web có thể hỗ trợ hai phiên bản trình duyệt chính gần nhất, nhưng trong chu kỳ kiểm thử hiện tại chỉ chạy trực tiếp trên phiên bản hiện hành và phiên bản trước đó. Nhóm cần ghi rõ tổ hợp nào đã chạy, tổ hợp nào được suy luận từ bằng chứng khác và tổ hợp nào chưa được xác minh.

## 4. Thiết kế cấu trúc ma trận

Ma trận đơn giản có thể dùng bảng với một dòng cho mỗi tổ hợp hoặc mỗi nhóm tổ hợp có cùng điều kiện. Một bản ghi hữu ích thường có các trường:

| Trường | Ý nghĩa |
|---|---|
| ID tổ hợp | Mã duy nhất để tham chiếu trong kế hoạch và báo cáo |
| Nền tảng | Hệ điều hành, trình duyệt, runtime, thiết bị hoặc dịch vụ |
| Phiên bản | Phiên bản chính xác hoặc khoảng phiên bản |
| Cấu hình | Các giá trị quan trọng có thể làm thay đổi hành vi |
| Phạm vi hỗ trợ | Được hỗ trợ, không hỗ trợ hoặc đang đánh giá |
| Mức ưu tiên | Mức rủi ro hoặc tầm quan trọng đối với người dùng |
| Kiểu kiểm thử | Smoke, chức năng, tương thích, hiệu năng, bảo mật, khả năng truy cập... |
| Môi trường | Thiết bị thật, máy ảo, container, cloud hoặc sandbox |
| Trạng thái kiểm thử | Chưa chạy, đạt, không đạt, bị chặn hoặc cần kiểm tra lại |
| Bằng chứng | Liên kết báo cáo, lần chạy, log, lỗi hoặc kết quả đo |
| Người phụ trách | Người chịu trách nhiệm duy trì hoặc xác minh tổ hợp |
| Ghi chú | Giới hạn, giả định, lỗi đã biết và ngày cần xem xét lại |

Không cần mọi bảng đều có đủ các cột. Với ma trận hỗ trợ sản phẩm, phạm vi hỗ trợ và phiên bản là thiết yếu; với ma trận thực thi của một đợt kiểm thử, môi trường, trạng thái và bằng chứng cũng cần được ghi rõ.

## 5. Ví dụ ma trận tương thích cho ứng dụng web

Giả sử một ứng dụng web phục vụ khách hàng trên máy tính và điện thoại. Nhóm đã thống nhất hỗ trợ các trình duyệt phổ biến trên hệ điều hành được nêu trong chính sách sản phẩm. Một ma trận rút gọn có thể như sau:

| ID | Nền tảng | Phiên bản | Cấu hình | Hỗ trợ | Ưu tiên kiểm thử |
|---|---|---|---|---|---|
| WEB-01 | Windows + Chrome | Phiên bản hiện hành | Viewport 1440×900, locale vi-VN | Có | Cao |
| WEB-02 | Windows + Edge | Phiên bản hiện hành | Viewport 1366×768, zoom 100% | Có | Cao |
| WEB-03 | macOS + Safari | Phiên bản hiện hành | Màn hình Retina, viewport desktop | Có | Cao |
| WEB-04 | Windows + Firefox | Phiên bản hiện hành | Viewport desktop, cookie mặc định | Có | Trung bình |
| WEB-05 | iOS + Safari | Phiên bản iOS trong chính sách hỗ trợ | Thiết bị màn hình nhỏ, cảm ứng | Có | Cao |
| WEB-06 | Android + Chrome | Phiên bản Android trong chính sách hỗ trợ | Thiết bị tầm trung, cảm ứng | Có | Cao |
| WEB-07 | Trình duyệt cũ ngoài chính sách | Phiên bản không còn được hỗ trợ | Bất kỳ | Không | Không thuộc kiểm thử chấp nhận |

Các tên phiên bản trong bảng cần được thay bằng phiên bản thực tế mà sản phẩm cam kết hỗ trợ. Cụm “hiện hành” chỉ có ý nghĩa khi chính sách xác định nguồn và thời điểm cập nhật danh sách.

Ma trận thực thi có thể bổ sung trạng thái và bằng chứng:

| ID | Smoke | Chức năng chính | Khả năng truy cập | Kết quả gần nhất |
|---|---|---|---|---|
| WEB-01 | Đạt | Đạt | Đạt | Bản dựng 2.8.0, lần chạy CI 1452 |
| WEB-02 | Đạt | Đạt | Chưa chạy | Bản dựng 2.8.0 |
| WEB-03 | Đạt | Không đạt | Chưa chạy | Lỗi định dạng ngày ở trang lịch |
| WEB-04 | Bị chặn | Chưa chạy | Chưa chạy | Môi trường kiểm thử không khởi động được |
| WEB-05 | Đạt | Đạt | Đạt | Thiết bị thật, bản dựng 2.8.0 |
| WEB-06 | Đạt | Đạt | Chưa chạy | Thiết bị thật, bản dựng 2.8.0 |

Bảng này cho thấy “được hỗ trợ” không đồng nghĩa “đã kiểm thử đạt”. Lỗi ở Safari cần được ghi nhận và đánh giá theo mức ảnh hưởng; Firefox bị chặn không được tính là đạt chỉ vì chưa quan sát thấy lỗi.

## 6. Tránh bùng nổ tổ hợp

Số lượng tổ hợp tăng rất nhanh khi có nhiều chiều. Nếu có 3 hệ điều hành, 4 trình duyệt, 3 phiên bản, 4 viewport, 2 locale và 3 cấu hình mạng, số tổ hợp đầy đủ là:

\[
3 \times 4 \times 3 \times 4 \times 2 \times 3 = 864
\]

Thực hiện toàn bộ 864 tổ hợp có thể không khả thi. Tuy nhiên, chọn một tổ hợp duy nhất cũng có thể bỏ sót tương tác quan trọng. Nhóm cần giảm không gian kiểm thử dựa trên rủi ro và kỹ thuật thiết kế tổ hợp.

### 6.1. Lọc theo phạm vi hỗ trợ

Loại các tổ hợp không thuộc phạm vi hỗ trợ hoặc không thể xảy ra trong kiến trúc thực tế. Ví dụ, một phiên bản trình duyệt không tồn tại trên hệ điều hành nhất định không cần xuất hiện như một tổ hợp hợp lệ. Ghi lại lý do loại trừ để tránh nhầm với một môi trường bị bỏ sót.

### 6.2. Chọn tổ hợp đại diện

Chọn những tổ hợp bao phủ các nền tảng, phiên bản và cấu hình có mức sử dụng hoặc rủi ro cao. Cần có ít nhất một số tổ hợp bao phủ các ranh giới khác nhau, chẳng hạn phiên bản tối thiểu được hỗ trợ, phiên bản hiện hành, thiết bị di động, locale khác nhau và cấu hình mạng yếu.

### 6.3. Kiểm thử theo cặp (pairwise)

Pairwise testing chọn một tập tổ hợp sao cho mọi cặp giá trị giữa các chiều đều xuất hiện ít nhất một lần. Kỹ thuật này hữu ích khi lỗi thường phát sinh từ tương tác giữa hai yếu tố, ví dụ trình duyệt với hệ điều hành hoặc locale với định dạng ngày.

Pairwise không bảo đảm phát hiện lỗi chỉ xuất hiện khi ba hoặc nhiều yếu tố kết hợp. Nếu có rủi ro đặc biệt, nhóm cần bổ sung tổ hợp ba chiều hoặc các kịch bản cụ thể dựa trên kiến thức miền.

### 6.4. Kiểm thử theo rủi ro

Ưu tiên tổ hợp dựa trên:

- Tỷ lệ người dùng hoặc lưu lượng sử dụng.
- Mức độ nghiêm trọng nếu tính năng lỗi.
- Khả năng xảy ra lỗi do khác biệt nền tảng hoặc phiên bản.
- Mức độ thay đổi trong bản phát hành hiện tại.
- Lịch sử lỗi và sự cố trên tổ hợp tương tự.
- Mức độ phức tạp khi tái hiện hoặc khắc phục.
- Yêu cầu hợp đồng, pháp lý, bảo mật hoặc khả năng truy cập.

Một tổ hợp ít người dùng nhưng liên quan đến thao tác tài chính hoặc dữ liệu nhạy cảm vẫn có thể cần ưu tiên cao. Không nên xếp ưu tiên chỉ theo số lượng người dùng.

## 7. Chọn chiến lược kiểm thử cho từng tổ hợp

Không nhất thiết chạy toàn bộ bộ kiểm thử trên mọi tổ hợp. Có thể phân bổ theo mục tiêu:

| Nhóm kiểm thử | Mục đích | Cách áp dụng trong ma trận |
|---|---|---|
| Smoke test | Xác nhận ứng dụng khởi động và luồng cốt lõi hoạt động | Chạy trên tất cả tổ hợp ưu tiên cao trước khi kiểm thử sâu |
| Kiểm thử chức năng | Xác nhận hành vi nghiệp vụ | Chạy đầy đủ trên tổ hợp chính và chọn lọc trên tổ hợp khác |
| Kiểm thử giao diện và khả năng truy cập | Kiểm tra hiển thị, thao tác và hỗ trợ công nghệ tiếp cận | Tập trung vào viewport, trình duyệt, thiết bị và phương thức nhập liệu khác nhau |
| Kiểm thử tương thích dữ liệu | Kiểm tra encoding, locale, timezone, collation và định dạng | Chọn tổ hợp cấu hình có khả năng thay đổi cách xử lý dữ liệu |
| Kiểm thử hiệu năng | Đánh giá tài nguyên và thời gian phản hồi | Dùng cấu hình phần cứng, tải và mạng đại diện hoặc biên |
| Kiểm thử bảo mật | Xác nhận quyền, cơ chế xác thực và cấu hình an toàn | Kiểm tra các nền tảng và cấu hình làm thay đổi bề mặt tấn công |
| Kiểm thử hồi quy | Phát hiện hành vi cũ bị ảnh hưởng | Chạy trên tổ hợp đã từng có lỗi hoặc có thay đổi liên quan |

Ví dụ, một thay đổi CSS có thể cần kiểm thử giao diện trên viewport nhỏ và các trình duyệt được hỗ trợ. Một thay đổi thư viện mã hóa cần kiểm tra runtime, cấu hình TLS và tích hợp liên quan. Một thay đổi truy vấn dữ liệu cần chú ý phiên bản cơ sở dữ liệu, collation và driver.

## 8. Xây dựng môi trường và quản lý cấu hình kiểm thử

Ma trận chỉ hữu ích khi nhóm có thể tái tạo các tổ hợp. Mỗi môi trường kiểm thử nên có cấu hình được ghi nhận và có cách xác minh.

### 8.1. Môi trường thật, máy ảo và container

- **Thiết bị thật:** Cần thiết khi hành vi phụ thuộc phần cứng, cảm ứng, camera, cảm biến, driver hoặc chính sách của hệ điều hành.
- **Máy ảo:** Hữu ích để kiểm tra nhiều hệ điều hành và phiên bản với khả năng tạo lại snapshot.
- **Container:** Phù hợp để cố định runtime, thư viện và dịch vụ phụ thuộc; container không mô phỏng đầy đủ kernel, driver hoặc phần cứng của thiết bị thật.
- **Cloud device/browser farm:** Có thể mở rộng số tổ hợp, nhưng cần kiểm tra giới hạn môi trường, độ ổn định và phiên bản thực tế được cung cấp.
- **Môi trường tại chỗ:** Có thể cần cho sản phẩm phụ thuộc thiết bị chuyên dụng, mạng nội bộ hoặc chính sách doanh nghiệp.

Không nên giả định một môi trường mô phỏng đại diện hoàn toàn cho môi trường thật. Hãy ghi rõ giới hạn và bổ sung kiểm thử trên thiết bị thật khi rủi ro yêu cầu.

### 8.2. Cố định và ghi nhận cấu hình

Mỗi lần chạy cần lưu các thông tin đủ để tái hiện:

- Phiên bản sản phẩm và mã commit hoặc build ID.
- Hệ điều hành, trình duyệt, runtime, framework và driver.
- Cấu hình phần cứng hoặc loại thiết bị.
- Locale, timezone, encoding và định dạng dữ liệu.
- Feature flag, biến cấu hình và phiên bản API phụ thuộc.
- Dữ liệu ban đầu, vai trò người dùng và trạng thái môi trường.
- Ngày giờ chạy, người thực hiện và mã lần chạy.

Thông tin bí mật như token, mật khẩu và khóa riêng không được ghi vào ma trận hoặc log. Chỉ lưu định danh an toàn hoặc tham chiếu đến hệ thống quản lý bí mật.

### 8.3. Tránh sai lệch cấu hình

Nếu cấu hình được nhập thủ công, các môi trường có thể lệch nhau mà nhóm không nhận ra. Có thể giảm sai lệch bằng cấu hình dưới dạng mã (configuration as code), image/container được version hóa, script thiết lập môi trường và kiểm tra cấu hình trước khi chạy.

Khi một lần chạy bị lỗi, cần xác định lỗi đến từ sản phẩm, cấu hình sai, môi trường không sẵn sàng hay dữ liệu kiểm thử. Trạng thái “bị chặn” nên được dùng khi không thể đánh giá sản phẩm do điều kiện kiểm thử không đáp ứng.

## 9. Quản lý ma trận trong CI/CD

Ma trận tương thích có thể được liên kết với pipeline để kiểm tra tự động các tổ hợp quan trọng. Một pipeline thường có các lớp:

1. Kiểm tra nhanh trên cấu hình chuẩn cho mỗi thay đổi.
2. Chạy tập kiểm thử trên các phiên bản hoặc runtime được chọn.
3. Chạy ma trận mở rộng theo lịch, trước phát hành hoặc khi thay đổi phụ thuộc.
4. Chạy kiểm thử trên thiết bị hoặc dịch vụ cloud theo nhu cầu.
5. Tổng hợp kết quả theo ID tổ hợp, phiên bản sản phẩm và build.

Ví dụ cấu hình ma trận CI minh họa:

```yaml
strategy:
  matrix:
    os: [windows-latest, ubuntu-latest]
    runtime: ["17", "21"]
    include:
      - os: macos-latest
        runtime: "21"
```

Đây chỉ là ví dụ cấu trúc. Tên runner và phiên bản runtime phải được chọn theo công cụ CI, khả năng cung cấp môi trường và chính sách hỗ trợ thực tế. Không nên đưa tất cả tổ hợp vào mỗi lần commit nếu thời gian pipeline quá dài.

Khi ma trận lớn, có thể:

- Chạy một tập nhỏ cho pull request và tập rộng hơn theo lịch.
- Chỉ chạy tổ hợp liên quan đến phần mã hoặc phụ thuộc thay đổi, nếu có phân tích tác động đáng tin cậy.
- Chạy song song có kiểm soát và bảo đảm dữ liệu/tài nguyên được cách ly.
- Dùng cache hoặc image dựng sẵn để giảm thời gian thiết lập.
- Tự động lưu báo cáo, log và kết quả vào nơi có thể truy vết.
- Cảnh báo khi một tổ hợp quan trọng không được chạy hoặc liên tục bị chặn.

Việc chọn tổ hợp theo thay đổi không được loại bỏ kiểm thử rộng hoàn toàn. Nên có lịch chạy toàn bộ ma trận ưu tiên hoặc bộ kiểm thử mở rộng để phát hiện tác động không được dự đoán từ phân tích thay đổi.

## 10. Theo dõi kết quả và báo cáo độ bao phủ

Một báo cáo tương thích cần phân biệt rõ:

- **Đạt:** Kiểm thử đã chạy và kết quả đáp ứng tiêu chí.
- **Không đạt:** Có sai lệch được xác nhận hoặc lỗi tái hiện được.
- **Bị chặn:** Không thể đánh giá do môi trường, dữ liệu, dịch vụ hoặc công cụ không sẵn sàng.
- **Chưa chạy:** Chưa có bằng chứng trong chu kỳ hiện tại.
- **Không áp dụng:** Tổ hợp không liên quan đến phạm vi kiểm thử đã xác định, kèm lý do.
- **Được chấp nhận có điều kiện:** Có sai lệch hoặc giới hạn đã được người có thẩm quyền chấp nhận, cùng điều kiện và kế hoạch xử lý.

Không gộp “chưa chạy” và “đạt”; không coi “bị chặn” là thành công. Báo cáo nên có ngày chạy và phiên bản sản phẩm để người đọc hiểu bằng chứng còn phù hợp hay không.

### 10.1. Các chỉ số hữu ích

- Tỷ lệ tổ hợp ưu tiên cao đã được kiểm thử trong chu kỳ.
- Tỷ lệ tổ hợp đạt, không đạt, bị chặn và chưa chạy.
- Số lỗi theo nền tảng, phiên bản và cấu hình.
- Số lỗi chỉ xuất hiện trên một tổ hợp hoặc một nhóm tổ hợp.
- Thời gian trung bình để chuẩn bị và chạy từng tổ hợp.
- Tỷ lệ môi trường không ổn định hoặc sai cấu hình.
- Số tổ hợp có bằng chứng cũ hơn ngưỡng thời gian đã quy định.
- Tỷ lệ lỗi tương thích được phát hiện trước phát hành so với sau phát hành.

Các chỉ số cần được đọc cùng mức rủi ro và mức sử dụng. Một tổ hợp có tỷ lệ đạt 100% nhưng chỉ chạy một ca smoke không thể được xem là có bằng chứng tương đương với tổ hợp đã chạy đầy đủ các kịch bản rủi ro cao.

### 10.2. Mẫu báo cáo rút gọn

| Nền tảng/tổ hợp | Phiên bản sản phẩm | Mức ưu tiên | Trạng thái | Phát hiện chính |
|---|---|---|---|---|
| Windows + Chrome hiện hành | 2.8.0 | Cao | Đạt | Không có lỗi nghiêm trọng |
| macOS + Safari hiện hành | 2.8.0 | Cao | Không đạt | Ngày hiển thị sai với locale vi-VN |
| Android + Chrome | 2.8.0 | Cao | Đạt | Đã kiểm tra luồng đăng nhập và thanh toán |
| Windows + Firefox hiện hành | 2.8.0 | Trung bình | Bị chặn | Browser runner không sẵn sàng |

## 11. Duy trì và cập nhật ma trận

Ma trận tương thích là tài liệu sống. Cần xem xét lại khi có các sự kiện:

- Nhà cung cấp nền tảng phát hành phiên bản mới hoặc ngừng hỗ trợ phiên bản cũ.
- Sản phẩm thay đổi runtime, framework, thư viện giao diện hoặc driver.
- Có lỗi hoặc sự cố chỉ xuất hiện trên một nền tảng/cấu hình.
- Dữ liệu sử dụng cho thấy một nhóm thiết bị hoặc trình duyệt trở nên phổ biến hơn.
- Sản phẩm mở rộng sang khu vực, ngôn ngữ hoặc thiết bị mới.
- Yêu cầu bảo mật, khả năng truy cập hoặc tuân thủ thay đổi.
- Một môi trường kiểm thử bị loại bỏ hoặc thay bằng nền tảng mới.

Mỗi lần cập nhật nên có người chịu trách nhiệm, lý do, ngày hiệu lực và ảnh hưởng đến phạm vi kiểm thử. Khi bỏ hỗ trợ một phiên bản, cần thông báo theo chính sách sản phẩm và đánh giá tác động đến người dùng hiện tại.

Nên rà soát định kỳ để loại bỏ tổ hợp không còn sử dụng, bổ sung tổ hợp mới có ý nghĩa và xác nhận lại các phiên bản tối thiểu. Tránh để ma trận phát triển thành danh sách lịch sử không còn phản ánh sản phẩm.

## 12. Ví dụ: lập ma trận cho một dịch vụ Java

Giả sử một dịch vụ backend chạy trên JVM, sử dụng framework web, cơ sở dữ liệu quan hệ và được triển khai bằng container. Các chiều cần xem xét có thể gồm:

- Hệ điều hành hoặc môi trường container được hỗ trợ.
- Phiên bản JDK được hỗ trợ.
- Phiên bản cơ sở dữ liệu và driver JDBC.
- Phiên bản framework hoặc thư viện tích hợp quan trọng.
- Cấu hình timezone, locale, encoding và TLS.
- CPU architecture và giới hạn bộ nhớ của container.

Một ma trận rút gọn:

| ID | Runtime | Database | Driver | Cấu hình | Mục tiêu kiểm thử |
|---|---|---|---|---|---|
| JAVA-01 | JDK 17 | PostgreSQL phiên bản được hỗ trợ | Driver tương ứng | UTC, UTF-8, cấu hình chuẩn | Smoke, chức năng và tích hợp |
| JAVA-02 | JDK 21 | PostgreSQL phiên bản được hỗ trợ | Driver tương ứng | UTC, UTF-8, cấu hình chuẩn | Smoke, chức năng và tích hợp |
| JAVA-03 | JDK 21 | PostgreSQL phiên bản mới hơn trong phạm vi | Driver được hỗ trợ | Locale vi-VN, timezone Asia/Ho_Chi_Minh | Kiểm thử ngày giờ, số và truy vấn |
| JAVA-04 | JDK 21 | PostgreSQL phiên bản được hỗ trợ | Driver tương ứng | Container giới hạn CPU/RAM | Khởi động, hiệu năng và khả năng phục hồi |

Các phiên bản trong bảng là ví dụ về cách tổ chức; nhóm cần thay bằng phiên bản thực tế đã được xác nhận trong chính sách hỗ trợ. Cần kiểm tra tính tương thích của cả bộ JDK, framework, driver và cơ sở dữ liệu, vì từng thành phần riêng lẻ có thể được hỗ trợ nhưng tổ hợp cụ thể chưa chắc đã được chứng minh.

Một lỗi có thể chỉ xuất hiện trên JAVA-03 nếu ứng dụng giả định timezone của máy chủ là UTC hoặc định dạng ngày theo locale mặc định. Một lỗi khác có thể chỉ xuất hiện trên JAVA-04 khi giới hạn bộ nhớ làm thay đổi hành vi garbage collection hoặc gây timeout. Ma trận giúp nhóm xác định nơi cần tái hiện và chọn bằng chứng phù hợp.

## 13. Những sai lầm thường gặp

- **Kiểm thử trên một môi trường rồi suy rộng:** Một tổ hợp đạt không chứng minh mọi tổ hợp khác đều đạt.
- **Liệt kê mọi tổ hợp mà không ưu tiên:** Ma trận trở nên quá lớn và không thể duy trì.
- **Không phân biệt hỗ trợ với đã kiểm thử:** Người đọc có thể hiểu nhầm rằng mọi môi trường được hỗ trợ đều đã được xác minh trong phiên bản hiện tại.
- **Ghi phiên bản không chính xác:** “Mới nhất” hoặc “bản hiện tại” thiếu nguồn và ngày tham chiếu sẽ nhanh chóng lỗi thời.
- **Bỏ qua cấu hình:** Cùng một nền tảng và phiên bản vẫn có thể hành xử khác nhau do locale, quyền, mạng hoặc feature flag.
- **Dùng container thay thế mọi kiểm thử thiết bị thật:** Container không mô phỏng đầy đủ phần cứng, driver và hành vi hệ điều hành.
- **Chỉ kiểm tra cặp tổ hợp:** Pairwise không phát hiện mọi lỗi tương tác ba chiều trở lên.
- **Không ghi bằng chứng và build:** Không thể biết kết quả có áp dụng cho phiên bản sản phẩm hiện tại hay không.
- **Coi bị chặn là đạt:** Thiếu môi trường không tạo ra bằng chứng chất lượng.
- **Không cập nhật ma trận:** Phiên bản đã lỗi thời hoặc nền tảng mới có thể bị bỏ sót.
- **Không thông báo thay đổi phạm vi hỗ trợ:** Người dùng và nhóm vận hành có thể tiếp tục dựa vào một cam kết đã thay đổi.

## 14. Checklist xây dựng ma trận tương thích

Trước khi bắt đầu một chu kỳ kiểm thử tương thích, nhóm có thể dùng checklist sau:

- [ ] Xác định người dùng, bối cảnh sử dụng và phạm vi nền tảng sản phẩm cam kết hỗ trợ.
- [ ] Liệt kê các chiều nền tảng, phiên bản và cấu hình có thể ảnh hưởng đến hành vi.
- [ ] Ghi rõ phiên bản tối thiểu, khoảng phiên bản và chính sách cập nhật.
- [ ] Phân biệt trạng thái được hỗ trợ, được kiểm thử và không hỗ trợ.
- [ ] Xác định tổ hợp ưu tiên theo mức sử dụng, tác động và lịch sử lỗi.
- [ ] Chọn tổ hợp đại diện và bổ sung kiểm thử theo cặp hoặc theo rủi ro khi phù hợp.
- [ ] Xác định môi trường thật, máy ảo, container hoặc dịch vụ cloud cần dùng.
- [ ] Ghi lại cấu hình, dữ liệu, build và phiên bản phụ thuộc cho từng lần chạy.
- [ ] Định nghĩa trạng thái đạt, không đạt, bị chặn, chưa chạy và không áp dụng.
- [ ] Liên kết kết quả với báo cáo, lỗi và người phụ trách.
- [ ] Xác định lịch cập nhật ma trận và người chịu trách nhiệm duy trì.
- [ ] Thông báo rõ thay đổi trong phạm vi hỗ trợ cho các bên liên quan.

Ma trận tương thích tốt giúp nhóm biết chính xác sản phẩm được kỳ vọng hoạt động ở đâu, cần kiểm tra những tổ hợp nào và bằng chứng hiện có đến mức nào. Khi nền tảng, phiên bản và cấu hình được quản lý có chủ đích, nhóm có thể kiểm thử theo rủi ro, giảm bùng nổ tổ hợp và đưa ra quyết định phát hành dựa trên phạm vi hỗ trợ được xác định rõ.
