# Xác định giới hạn bằng chứng do điều kiện môi trường khác thực tế

Trong module **VALIDATION_TESTING_STRATEGY**, kết quả kiểm thử chỉ có ý nghĩa trong phạm vi điều kiện đã được kiểm tra. Một bài kiểm thử đạt trên máy phát triển, CI hoặc staging cho thấy hành vi đã được xác minh trong môi trường đó, với phiên bản, cấu hình, dữ liệu, phụ thuộc và tải cụ thể. Kết quả ấy có thể cung cấp bằng chứng quan trọng cho chất lượng sản phẩm, nhưng không tự động chứng minh hệ thống sẽ hoạt động giống hệt trong môi trường thực tế.

Môi trường kiểm thử thường khác môi trường sản xuất về kiến trúc triển khai, quy mô hạ tầng, dữ liệu, quyền truy cập, dịch vụ bên ngoài, cấu hình mạng, tải, thời gian xử lý và cách vận hành. Những khác biệt này có thể làm thay đổi hành vi hoặc khiến một số rủi ro không thể xuất hiện trong bài kiểm thử. Vì vậy, nhóm cần xác định **giới hạn bằng chứng**: kết quả đã chứng minh điều gì, trong điều kiện nào, chưa chứng minh điều gì và rủi ro còn lại là gì.

Bài học này hướng dẫn cách so sánh môi trường kiểm thử với môi trường thực tế, đánh giá mức độ đại diện theo từng thuộc tính, xác định phạm vi kết luận, bổ sung bằng chứng khi môi trường không tương đương và báo cáo giới hạn một cách rõ ràng. Mục tiêu là giúp người đọc không diễn giải quá mức một kết quả đạt, đồng thời biết cần kiểm tra thêm ở đâu để có đủ cơ sở ra quyết định.

## 1. Hiểu giới hạn bằng chứng trong kiểm thử

### 1.1. Bằng chứng luôn gắn với điều kiện kiểm thử

Một kết quả kiểm thử được tạo ra từ một tập điều kiện cụ thể, chẳng hạn:

- Phiên bản ứng dụng và các dịch vụ liên quan.
- Cấu hình, feature flag và biến môi trường.
- Hạ tầng tính toán, lưu trữ và mạng.
- Dữ liệu, trạng thái và quyền của tài khoản.
- Dịch vụ bên ngoài, sandbox, mock hoặc stub.
- Số lượng người dùng đồng thời và phân bố tải.
- Thời gian, múi giờ và lịch chạy tác vụ.
- Cách thu thập log, metrics, trace và kết quả.

Nếu bất kỳ điều kiện quan trọng nào khác với thực tế, phạm vi kết luận cần được xem xét. Ví dụ, kiểm thử thanh toán thành công với mock chỉ chứng minh ứng dụng xử lý phản hồi giả lập theo kịch bản. Nó chưa chứng minh chứng thư, xác thực, endpoint, webhook hoặc đối soát với nhà cung cấp thanh toán thật hoạt động đúng.

### 1.2. Phân biệt kết quả đạt với bằng chứng đủ

- **Kết quả đạt (pass):** trường hợp kiểm thử đáp ứng tiêu chí đã đặt trong điều kiện chạy cụ thể.
- **Bằng chứng đủ:** các kết quả và nguồn quan sát đủ để hỗ trợ một kết luận xác định về yêu cầu hoặc rủi ro trong phạm vi đã nêu.
- **Giới hạn bằng chứng:** những điều kiện hoặc thuộc tính chưa được kiểm tra, được mô phỏng hoặc khác đáng kể so với thực tế.
- **Rủi ro còn lại:** khả năng xảy ra vấn đề chưa được loại trừ bởi bằng chứng hiện có.

Một suite có 100% trường hợp đạt vẫn có thể để lại rủi ro nếu các trường hợp chỉ chạy trên một cấu hình đơn giản, dùng dữ liệu nhỏ hoặc thay thế toàn bộ phụ thuộc quan trọng bằng mock. Tỷ lệ đạt phản ánh kết quả của tập kiểm thử; nó không tự nói lên mức đại diện của môi trường hay độ bao phủ rủi ro.

### 1.3. Không suy rộng ngoài phạm vi đã quan sát

Nếu kiểm thử xác nhận API trả đúng schema trên một phiên bản dịch vụ, kết luận hợp lý là phiên bản đó tuân thủ schema trong các trường hợp đã chạy. Không thể từ đó kết luận hệ thống chịu được tải sản xuất, xử lý đúng mọi trạng thái đồng thời hoặc tương thích với mọi consumer.

Tương tự:

- Kiểm thử thành công trên một trình duyệt không chứng minh tương thích với mọi trình duyệt.
- Kiểm thử trên database rỗng không chứng minh truy vấn hiệu quả với dữ liệu lớn.
- Kiểm thử bằng tài khoản quản trị không chứng minh phân quyền của người dùng thông thường.
- Kiểm thử với sandbox không chứng minh toàn bộ hành vi của endpoint sản xuất.
- Kiểm thử triển khai trên một vùng không chứng minh khả năng phục hồi khi mất cả vùng.

Kết luận phải gắn với yêu cầu, phiên bản, môi trường và tình huống thực sự được kiểm tra.

## 2. Xác định môi trường tham chiếu và môi trường được kiểm tra

### 2.1. Làm rõ “thực tế” có nghĩa là gì

Trong bài học này, môi trường thực tế thường là môi trường sản xuất hoặc điều kiện vận hành mà sản phẩm dự kiến phải đáp ứng. Tuy nhiên, có thể có nhiều môi trường tham chiếu:

- Sản xuất hiện tại.
- Cấu hình mục tiêu sau khi phát hành.
- Môi trường của khách hàng hoặc tổ chức triển khai.
- Thiết bị và mạng thực tế của người dùng.
- Hệ thống đối tác hoặc nhà cung cấp bên ngoài.
- Điều kiện vận hành đặc biệt như giờ cao điểm hoặc khu vực địa lý cụ thể.

Không nên so sánh một môi trường kiểm thử với khái niệm sản xuất chung chung. Hãy xác định hệ thống, khu vực, cấu hình, nhóm người dùng và thời điểm làm chuẩn so sánh.

### 2.2. Lập hồ sơ cho từng môi trường

Với mỗi môi trường, ghi các thuộc tính quan trọng:

| Nhóm thuộc tính | Thông tin cần xác định |
|---|---|
| Phiên bản | Ứng dụng, service, schema, runtime và dependency |
| Cấu hình | Feature flag, timeout, retry, giới hạn và biến môi trường |
| Hạ tầng | CPU, RAM, lưu trữ, loại máy, container và autoscaling |
| Kiến trúc triển khai | Số instance, topology, gateway, load balancer và vùng |
| Mạng | DNS, TLS, firewall, latency, bandwidth và proxy |
| Dữ liệu | Quy mô, phân bố, tính lịch sử, quan hệ và mức nhạy cảm |
| Tích hợp | Dịch vụ thật, sandbox, mock, stub và phiên bản hợp đồng |
| Bảo mật | Danh tính, quyền, secret, chính sách mạng và audit |
| Thời gian | Clock, timezone, lịch chạy và độ lệch đồng hồ |
| Vận hành | Monitoring, logging, tracing, backup và quy trình xử lý sự cố |

Không phải mọi thuộc tính đều cần chi tiết như nhau. Tập trung vào các khác biệt có thể ảnh hưởng đến mục tiêu kiểm thử.

### 2.3. Phân biệt tên môi trường với mức độ tương đồng

Tên như local, dev, test, integration, staging hoặc pre-production không cho biết chính xác môi trường giống sản xuất đến đâu. Hai môi trường cùng tên staging có thể có topology, dữ liệu và tích hợp rất khác nhau.

Vì vậy, không dùng nhãn môi trường làm bằng chứng duy nhất. Hãy ghi cấu hình và chế độ thực tế của các thành phần quan trọng trong lần chạy.

### 2.4. Xác định phiên bản và thời điểm so sánh

Môi trường thay đổi theo thời gian. Một lần chạy staging tuần trước có thể không đại diện cho bản dựng hiện tại nếu dịch vụ phụ thuộc đã được nâng cấp. Khi so sánh, ghi:

- Commit hoặc build ID.
- Phiên bản từng dịch vụ quan trọng.
- Phiên bản schema và migration.
- Cấu hình hoặc mã định danh cấu hình.
- Thời điểm chạy.
- Môi trường và vùng triển khai.

Nếu không thể xác nhận phiên bản hoặc cấu hình của một phụ thuộc, ghi rõ phần đó chưa được kiểm chứng.

## 3. Những khác biệt môi trường có thể giới hạn bằng chứng

### 3.1. Hạ tầng và tài nguyên

Môi trường kiểm thử có thể dùng máy nhỏ hơn, ít instance hơn, ổ đĩa khác loại hoặc không có autoscaling. Điều này ảnh hưởng đến:

- Thời gian phản hồi và thông lượng.
- Hành vi khi cạn CPU, RAM, connection hoặc file handle.
- Cạnh tranh tài nguyên giữa các tác vụ.
- Tính ổn định khi chạy song song.
- Khả năng chịu lỗi của một instance hoặc node.
- Hiệu năng đọc/ghi và độ trễ lưu trữ.

Một bài kiểm thử chức năng trên một instance không chứng minh hệ thống hoạt động đúng khi có nhiều instance và chia sẻ trạng thái. Một bài kiểm thử hiệu năng trên hạ tầng nhỏ hơn sản xuất cũng không thể dùng trực tiếp để kết luận năng lực tải sản xuất.

### 3.2. Kiến trúc và topology triển khai

Môi trường đơn giản hóa có thể gộp nhiều dịch vụ vào một tiến trình, bỏ gateway hoặc không triển khai nhiều vùng. Điều này có thể che giấu:

- Lỗi giao tiếp qua mạng.
- Sai cấu hình routing hoặc service discovery.
- Lỗi phân tán và đồng thời.
- Khác biệt giữa trạng thái cục bộ và trạng thái dùng chung.
- Lỗi failover, load balancing hoặc session affinity.
- Phụ thuộc vào thứ tự khởi động dịch vụ.

Nếu mục tiêu liên quan đến giao tiếp giữa các dịch vụ hoặc khả năng phục hồi, cần kiểm tra trên topology đại diện hơn hoặc bổ sung kiểm thử chuyên biệt cho các ranh giới bị giản lược.

### 3.3. Dữ liệu và trạng thái

Dữ liệu thử nghiệm thường nhỏ, sạch và mới hơn dữ liệu thực tế. Môi trường sản xuất có thể chứa:

- Bản ghi lịch sử lâu năm.
- Dữ liệu thiếu, trùng hoặc không đồng nhất.
- Quan hệ phức tạp giữa nhiều đối tượng.
- Phân bố lệch, nhóm dữ liệu lớn và giá trị hiếm.
- Dữ liệu được tạo bởi phiên bản cũ.
- Nhiều giao dịch đang ở trạng thái trung gian.

Kiểm thử trên vài trăm bản ghi không chứng minh truy vấn sẽ hoạt động tốt trên hàng triệu bản ghi. Dữ liệu tổng hợp cần có phân bố và quan hệ đủ đại diện cho mục tiêu, đồng thời không làm lộ dữ liệu cá nhân.

### 3.4. Tích hợp và dịch vụ bên ngoài

Các phụ thuộc có thể ở những chế độ khác nhau:

- Dịch vụ nội bộ triển khai thật.
- Sandbox do nhà cung cấp cung cấp.
- Mock hoặc stub do nhóm kiểm thử quản lý.
- Service virtualization.
- Dịch vụ bị vô hiệu hóa hoặc không tham gia.

Mỗi chế độ cung cấp loại bằng chứng khác nhau. Mock có thể giúp kiểm tra nhánh lỗi và logic điều phối, nhưng không xác nhận kết nối, xác thực hoặc hành vi thật của provider. Sandbox gần với tích hợp thực hơn nhưng vẫn có thể khác về dữ liệu, giới hạn, latency và xử lý nghiệp vụ.

### 3.5. Cấu hình và feature flag

Cùng một phiên bản mã có thể chạy khác nhau khi cấu hình khác:

- Feature flag bật hoặc tắt.
- Timeout và retry khác nhau.
- Cache TTL khác nhau.
- Giới hạn request hoặc quota khác nhau.
- Endpoint và credential khác nhau.
- Mức log hoặc cơ chế giám sát khác nhau.
- Cấu hình bảo mật và quyền truy cập khác nhau.

Nếu kiểm thử không ghi cấu hình, người đọc khó biết kết quả có áp dụng cho cấu hình phát hành hay không. Với thay đổi có điều kiện theo feature flag, cần kiểm tra cả cấu hình bật, tắt và quá trình chuyển đổi nếu có rủi ro.

### 3.6. Mạng và điều kiện người dùng

Mạng trong CI hoặc staging thường ổn định hơn mạng người dùng. Môi trường thử có thể không đại diện cho:

- Độ trễ cao hoặc biến động.
- Mất gói, ngắt kết nối và kết nối lại.
- Băng thông thấp.
- DNS chậm hoặc lỗi.
- Proxy, firewall hoặc thiết bị trung gian.
- Mạng di động và chuyển đổi giữa Wi-Fi với cellular.

Nếu sản phẩm cần hoạt động trong điều kiện mạng không ổn định, cần bổ sung network shaping, fault injection hoặc kiểm thử trên mạng/thiết bị đại diện.

### 3.7. Danh tính, quyền và bảo mật

Môi trường thử có thể dùng tài khoản quản trị chung, chính sách xác thực đơn giản hoặc secret khác sản xuất. Điều này có thể bỏ sót:

- Lỗi phân quyền theo vai trò hoặc tenant.
- Quyền thừa do cấu hình sai.
- Hết hạn token và luân chuyển khóa.
- Cấu hình TLS, certificate và trust store.
- Giới hạn mạng hoặc chính sách truy cập.
- Audit và kiểm soát dữ liệu nhạy cảm.

Một kiểm thử đạt với tài khoản quản trị không cung cấp bằng chứng cho quyền của người dùng thông thường. Cần tạo ma trận danh tính và quyền phù hợp với mục tiêu.

### 3.8. Thời gian, locale và tác vụ nền

Đồng hồ, múi giờ, locale và lịch chạy có thể khác giữa môi trường. Điều này ảnh hưởng đến:

- Hết hạn token và phiên.
- Lịch hẹn, thanh toán và khuyến mãi.
- Báo cáo theo ngày hoặc tháng.
- Tác vụ định kỳ và xử lý hàng đợi.
- Thứ tự sự kiện và độ lệch đồng hồ.
- Định dạng số, tiền tệ và ngày giờ.

Kiểm thử cần đặt rõ thời điểm tham chiếu, timezone và locale. Không nên suy ra hành vi thời gian thực từ một môi trường chỉ chạy trong vài phút với đồng hồ hệ thống mặc định.

### 3.9. Quan sát và giám sát

Môi trường thử có thể bật log chi tiết hoặc có tracing đầy đủ, trong khi sản xuất dùng mức log khác hoặc có sampling. Ngược lại, một môi trường test có thể thiếu metrics và không lưu artifact đủ lâu.

Điều này giới hạn khả năng chứng minh:

- Một sự kiện đã được xử lý ở đâu.
- Lỗi xảy ra trước hay sau tác dụng phụ.
- Hệ thống có phát cảnh báo đúng không.
- Thời gian phản hồi được đo từ điểm nào.
- Một request có đi qua đúng các thành phần không.

Cần ghi rõ nguồn bằng chứng và mức độ đầy đủ của quan sát. Không kết luận hệ thống không phát sinh lỗi chỉ vì môi trường không có log để nhìn thấy lỗi.

## 4. Đánh giá mức độ đại diện theo từng thuộc tính

### 4.1. Không dùng một nhãn “giống sản xuất” cho toàn bộ môi trường

Một môi trường có thể gần sản xuất về phiên bản ứng dụng nhưng khác về dữ liệu, tải và tích hợp. Đánh giá theo từng thuộc tính sẽ hữu ích hơn:

| Thuộc tính | Mức đại diện | Ví dụ giới hạn |
|---|---|---|
| Phiên bản ứng dụng | Cao | Cùng build ứng viên phát hành |
| Cấu hình | Trung bình | Timeout khác sản xuất |
| Hạ tầng | Thấp | Một instance nhỏ thay cho cụm nhiều node |
| Dữ liệu | Trung bình | Dữ liệu tổng hợp nhưng ít bản ghi lịch sử |
| Tích hợp | Thấp | Provider được thay bằng mock |
| Mạng | Thấp | Không mô phỏng latency hoặc mất kết nối |
| Bảo mật | Trung bình | Dùng SSO test nhưng không có chính sách thiết bị thật |
| Giám sát | Cao | Có log và trace đầy đủ hơn sản xuất |

Mức đại diện là nhận định có căn cứ, không phải điểm số tuyệt đối. Cần ghi tiêu chí dùng để đánh giá và ảnh hưởng của khác biệt đến mục tiêu.

### 4.2. Ma trận khác biệt và tác động

Với mỗi khác biệt, xác định:

1. Môi trường kiểm thử đang dùng điều kiện nào?
2. Môi trường thực tế dùng điều kiện nào?
3. Khác biệt có thể ảnh hưởng yêu cầu hoặc rủi ro nào?
4. Bằng chứng hiện tại có còn hợp lệ không?
5. Cần kiểm tra bổ sung hay chấp nhận giới hạn?

Ví dụ:

| Khác biệt | Rủi ro bị che giấu | Bằng chứng bổ sung |
|---|---|---|
| Mock payment provider | Sai xác thực, webhook hoặc đối soát | Contract test và sandbox integration |
| Database ít dữ liệu | Truy vấn chậm hoặc hết tài nguyên khi dữ liệu lớn | Dataset đại diện và performance test |
| Chỉ một instance | Lỗi đồng thời hoặc failover | Multi-instance integration và resilience test |
| Tài khoản quản trị | Lỗi phân quyền | Role/tenant matrix với tài khoản giới hạn |
| Không có network fault | Timeout và retry không an toàn | Network fault injection |
| Locale mặc định duy nhất | Parse hoặc định dạng sai ở locale khác | Locale matrix |
| Không chạy job nền | Trạng thái tồn đọng hoặc xử lý trễ | Scheduler test và kiểm tra hàng đợi |

### 4.3. Xác định mức đại diện cần thiết theo mục tiêu

Không cần mọi môi trường phải giống sản xuất ở mọi thuộc tính. Mức đại diện cần phù hợp với câu hỏi kiểm thử:

- Kiểm tra logic tính giá có thể dùng dữ liệu cố định và mock phụ thuộc.
- Kiểm tra hợp đồng API cần provider/consumer và schema tương ứng.
- Kiểm tra tích hợp cần các ranh giới thật hoặc sandbox đủ đại diện.
- Kiểm tra tải cần hạ tầng, dữ liệu và tải gần với mục tiêu vận hành.
- Kiểm tra failover cần topology và cơ chế lỗi tương ứng.
- Kiểm tra phân quyền cần danh tính, vai trò và chính sách thực tế.
- Kiểm tra trải nghiệm người dùng cần thiết bị, trình duyệt và công nghệ hỗ trợ trong phạm vi cam kết.

Môi trường càng đơn giản thì kiểm thử càng dễ lặp lại, nhưng một số rủi ro cần được kiểm tra ở môi trường khác. Mục tiêu là ghép nhiều nguồn bằng chứng, không yêu cầu một môi trường duy nhất chứng minh mọi thứ.

## 5. Xác định giới hạn kết luận cho từng loại kiểm thử

### 5.1. Unit và component testing

**Có thể hỗ trợ kết luận về:**

- Quy tắc logic trong phạm vi thành phần.
- Xử lý đầu vào và trạng thái được cung cấp.
- Nhánh lỗi được mô phỏng.
- Bất biến và kết quả tính toán.

**Giới hạn thường gặp:**

- Không xác nhận tích hợp mạng hoặc cấu hình triển khai.
- Mock có thể không phản ánh provider thật.
- Không chứng minh transaction và concurrency của hạ tầng thật nếu đã thay thế.
- Không xác nhận toàn bộ hành trình xuyên hệ thống.

### 5.2. API và contract testing

**Có thể hỗ trợ kết luận về:**

- Schema request/response.
- Mã trạng thái và cấu trúc lỗi.
- Tương thích provider–consumer trong hợp đồng được kiểm tra.
- Quy tắc API ở các điều kiện đã chạy.

**Giới hạn thường gặp:**

- Không tự chứng minh hiệu năng dưới tải.
- Không xác nhận mọi tích hợp ngoài nếu dùng mock.
- Không bao phủ hành vi UI hoặc toàn bộ hành trình.
- Có thể bỏ sót khác biệt cấu hình hoặc dữ liệu thực tế.

### 5.3. Integration testing

**Có thể hỗ trợ kết luận về:**

- Giao tiếp giữa các thành phần được triển khai.
- Serialization, xác thực và xử lý lỗi ở ranh giới.
- Transaction, event và trạng thái giữa các dịch vụ trong môi trường.

**Giới hạn thường gặp:**

- Topology có thể ít node hơn thực tế.
- Một số provider vẫn là sandbox hoặc mock.
- Dữ liệu và tải có thể không đại diện.
- Không chứng minh vận hành dài hạn hoặc khả năng phục hồi ở quy mô sản xuất.

### 5.4. System và E2E testing

**Có thể hỗ trợ kết luận về:**

- Hành trình hoặc chức năng xuyên qua các thành phần được tham gia.
- Kết quả nghiệp vụ cuối của các kịch bản đã chạy.
- Phối hợp giữa các dịch vụ và giao diện trong cấu hình cụ thể.

**Giới hạn thường gặp:**

- Chỉ bao phủ các hành trình và dữ liệu đã chọn.
- Có thể dùng mock cho ranh giới quan trọng.
- Môi trường có thể khác sản xuất về tải, dữ liệu, quyền hoặc topology.
- Một số lỗi hiếm, dài hạn hoặc phụ thuộc vận hành không xuất hiện trong lần chạy.

### 5.5. Performance và resilience testing

**Có thể hỗ trợ kết luận về:**

- Hiệu năng trong tải, dữ liệu và hạ tầng được mô tả.
- Ngưỡng tài nguyên và hành vi khi có lỗi được tiêm vào.
- Khả năng phục hồi theo kịch bản và thời gian quan sát.

**Giới hạn thường gặp:**

- Kết quả phụ thuộc mạnh vào hạ tầng và phân bố tải.
- Mô phỏng không phản ánh đầy đủ hành vi dịch vụ thật.
- Một lần chạy ngắn không chứng minh ổn định dài hạn.
- Không thể suy rộng trực tiếp sang quy mô khác nếu chưa có mô hình và bằng chứng phù hợp.

## 6. Thiết kế chiến lược bổ sung bằng chứng

### 6.1. Ghép nhiều môi trường và phương pháp

Một chiến lược hợp lý có thể dùng:

- Local/CI để phản hồi nhanh và kiểm tra logic.
- Integration để xác nhận các ranh giới dịch vụ.
- Staging/pre-production để kiểm tra cấu hình phát hành và hành trình quan trọng.
- Kiểm thử tải trên hạ tầng đại diện để đo năng lực.
- Kiểm thử bảo mật trong phạm vi được phép.
- Smoke hoặc synthetic monitoring sau triển khai để xác nhận hoạt động thực tế.

Mỗi tầng bổ sung một loại bằng chứng. Cần tránh lặp lại cùng một kiểm thử ở nhiều môi trường mà không có mục tiêu rõ ràng.

### 6.2. Bổ sung kiểm thử cho khác biệt đã xác định

Ví dụ nếu staging dùng mock cho nhà cung cấp thanh toán:

1. Contract test xác nhận request và response theo hợp đồng.
2. Test với sandbox xác nhận xác thực và giao thức tích hợp.
3. Fault injection xác nhận timeout, retry và trạng thái chưa rõ.
4. E2E xác nhận hành trình đặt hàng trong cấu hình staging.
5. Kiểm tra sau triển khai được phê duyệt xác nhận một số hành vi an toàn trên endpoint thật.

Các bước này không nhất thiết chạy trong cùng một pipeline. Hãy chọn vị trí phù hợp với chi phí, rủi ro và quyền truy cập.

### 6.3. Dùng dữ liệu đại diện

Khi dữ liệu test nhỏ hoặc sạch hơn thực tế, bổ sung:

- Dữ liệu tổng hợp có phân bố gần với thực tế.
- Bản ghi lịch sử và trạng thái cũ.
- Dữ liệu biên và quan hệ phức tạp.
- Dữ liệu lệch hoặc dữ liệu hiếm theo rủi ro.
- Kích thước dữ liệu phù hợp với mục tiêu tải.

Nếu không thể dùng dữ liệu thật, ghi cách tổng hợp và những đặc tính không được mô hình hóa.

### 6.4. Dùng fault injection có kiểm soát

Để kiểm tra rủi ro mạng và phụ thuộc, có thể mô phỏng:

- Latency cao.
- Mất kết nối.
- Timeout trước hoặc sau khi dịch vụ xử lý.
- Phản hồi lỗi hoặc sai định dạng.
- Event trùng hoặc đến sai thứ tự.
- Một instance hoặc node không sẵn sàng.
- Cơ sở dữ liệu hoặc broker tạm thời không truy cập được.

Fault injection cần giới hạn phạm vi, môi trường và tài nguyên. Không gây lỗi trên hệ thống sản xuất nếu chưa có phê duyệt và cơ chế bảo vệ rõ ràng.

### 6.5. Xác minh cấu hình phát hành

Trước phát hành, so sánh các cấu hình quan trọng giữa staging và production:

- Feature flag và tham số ứng dụng.
- Timeout, retry và connection pool.
- Endpoint, certificate và trust chain.
- Quyền, role và secret reference.
- Autoscaling và resource limit.
- Cache, queue và scheduler.
- Logging, tracing và alert.
- Chính sách backup, retention và migration.

Không cần chia sẻ giá trị secret trong báo cáo. Có thể so sánh mã định danh cấu hình, trạng thái và nguồn quản lý secret.

## 7. Đánh giá bằng chứng từ staging và production

### 7.1. Staging là bằng chứng trước phát hành

Staging hữu ích khi có cùng build hoặc cấu hình gần với bản phát hành. Tuy nhiên, cần ghi rõ:

- Những thành phần nào giống production.
- Những thành phần nào dùng sandbox hoặc mock.
- Dữ liệu và tải có đại diện không.
- Các khác biệt về quyền, mạng và hạ tầng.
- Những kiểm tra nào chưa thể thực hiện.

Một staging đạt có thể hỗ trợ quyết định phát hành trong phạm vi đã kiểm tra, nhưng không loại trừ sự cố do dữ liệu, tải, cấu hình hoặc hành vi chỉ tồn tại ở production.

### 7.2. Kiểm thử trên production có kiểm soát

Một số bằng chứng chỉ có thể thu được sau triển khai, chẳng hạn hành vi trên hạ tầng và tuyến mạng thực tế. Có thể dùng:

- Smoke test với tài khoản hoặc dữ liệu thử đã được phê duyệt.
- Synthetic monitoring trên hành trình không gây tác dụng phụ ngoài dự kiến.
- Kiểm tra read-only và truy vấn trạng thái.
- Quan sát metrics, log, trace và cảnh báo.
- Canary hoặc progressive rollout với tiêu chí dừng rõ ràng.

Kiểm thử production cần có phạm vi, quyền và cơ chế an toàn. Tránh tạo giao dịch, gửi thông báo đến khách thật hoặc thay đổi dữ liệu không thể hoàn tác chỉ để có bằng chứng.

### 7.3. Không dùng production như nơi thay thế kiểm thử đầy đủ

Production có dữ liệu và tải thật, nhưng không phải mọi tình huống đều có thể hoặc nên tạo ở đó. Những tình huống như xóa dữ liệu, vượt giới hạn, thử quyền trái phép hoặc gây lỗi phụ thuộc cần được kiểm tra trong môi trường an toàn hoặc bằng phương pháp được phê duyệt.

Kết quả giám sát production có thể bổ sung bằng chứng về vận hành, nhưng không thay thế kiểm thử có kiểm soát cho các nhánh hiếm và tình huống phá hủy.

## 8. Đánh giá giới hạn theo rủi ro và mức độ nghiêm trọng

### 8.1. Xác định rủi ro chưa được loại trừ

Với mỗi khác biệt môi trường, hỏi:

- Có thể che giấu loại lỗi nào?
- Hậu quả nếu lỗi xảy ra là gì?
- Bao nhiêu người dùng hoặc quy trình bị ảnh hưởng?
- Có thể phát hiện bằng monitoring không?
- Có thể phục hồi hoặc rollback không?
- Có cách kiểm thử bổ sung an toàn không?
- Ai có quyền chấp nhận rủi ro còn lại?

Không phải mọi khác biệt đều cần xử lý trước phát hành. Nhưng khác biệt liên quan đến tiền, dữ liệu nhạy cảm, quyền truy cập, tính toàn vẹn hoặc hành trình cốt lõi cần được xem xét kỹ.

### 8.2. Ma trận rủi ro còn lại

| Rủi ro | Khả năng bị che giấu bởi môi trường | Hậu quả | Hành động gợi ý |
|---|---|---|---|
| Sai xác thực với payment provider | Cao nếu dùng mock | Cao | Kiểm tra sandbox và cấu hình phát hành |
| Truy vấn chậm trên dữ liệu lớn | Cao nếu dataset nhỏ | Trung bình/cao | Performance test với dữ liệu đại diện |
| Lỗi quyền giữa tenant | Cao nếu chỉ dùng admin | Cao | Test ma trận role/tenant |
| Retry tạo giao dịch trùng | Trung bình nếu mock quá đơn giản | Cao | Fault injection và đối soát |
| Lỗi failover nhiều vùng | Cao nếu staging một vùng | Cao | Resilience test trên topology phù hợp |
| Lỗi hiển thị theo locale | Cao nếu chỉ chạy một locale | Trung bình | Locale matrix |
| Mất log khi sampling | Có thể cao nếu quan sát hạn chế | Tùy sự cố | Kiểm tra tracing/monitoring và cảnh báo |

Ma trận cần được điều chỉnh theo sản phẩm. Mức khả năng và hậu quả phải dựa trên dữ liệu, lịch sử sự cố hoặc đánh giá có căn cứ.

### 8.3. Quyết định chấp nhận rủi ro

Nếu không thể bổ sung bằng chứng trước phát hành, ghi rõ:

- Rủi ro cụ thể.
- Khác biệt môi trường tạo ra giới hạn.
- Bằng chứng hiện có.
- Lý do chưa thể kiểm tra thêm.
- Biện pháp giảm thiểu.
- Chỉ số hoặc cảnh báo cần theo dõi.
- Người có thẩm quyền chấp nhận.
- Thời điểm hoặc điều kiện xem xét lại.

Không nên biến “chưa kiểm tra” thành “đạt có điều kiện” nếu chưa có người chịu trách nhiệm và biện pháp theo dõi. Việc chấp nhận rủi ro phải minh bạch và có thời hạn hoặc điều kiện xem xét khi phù hợp.

## 9. Ghi nhận và báo cáo giới hạn bằng chứng

### 9.1. Mẫu hồ sơ môi trường kiểm thử

| Trường | Nội dung |
|---|---|
| Test run ID | Mã lần chạy |
| Build / commit | Phiên bản ứng dụng |
| Environment | Local, CI, integration, staging hoặc production |
| Time | Thời điểm chạy và timezone |
| Configuration | Mã hoặc phiên bản cấu hình |
| Infrastructure | Tài nguyên và topology liên quan |
| Data profile | Quy mô, phân bố và nguồn dữ liệu |
| Dependencies | Thành phần thật, sandbox, mock hoặc stub |
| Security context | Tài khoản, vai trò và phạm vi quyền |
| Network conditions | Latency, giới hạn hoặc mô phỏng lỗi |
| Observability | Log, metrics, trace và artifact |
| Differences | Khác biệt so với môi trường tham chiếu |
| Limitations | Những điều chưa được xác minh |
| Residual risks | Rủi ro còn lại và hành động tiếp theo |

### 9.2. Mẫu ghi nhận giới hạn cho một trường hợp kiểm thử

| Nội dung | Ví dụ |
|---|---|
| Mục tiêu | Xác nhận khách thanh toán đơn thành công |
| Môi trường | Staging |
| Thành phần thật | Web, Order API, Payment service, database |
| Thành phần mô phỏng | Payment provider được thay bằng sandbox |
| Dữ liệu | Khách và sản phẩm tổng hợp, tồn kho được seed |
| Kết quả | Đơn được xác nhận, giao dịch sandbox thành công |
| Giới hạn | Chưa xác minh settlement và hành vi chống gian lận của endpoint production |
| Bằng chứng bổ sung | Đối soát sandbox; kiểm tra vận hành sau triển khai theo quy trình được duyệt |
| Rủi ro còn lại | Khác biệt giữa sandbox và production |

### 9.3. Cách viết kết luận chính xác

Ví dụ kết luận có giới hạn:

> Bộ kiểm thử E2E đạt trên staging với build đã ghi nhận. Các dịch vụ nội bộ trong hành trình đặt hàng chạy bằng bản dựng thật của môi trường; nhà cung cấp thanh toán sử dụng sandbox. Kết quả xác nhận luồng tạo đơn, cập nhật tồn kho và xử lý phản hồi sandbox trong các kịch bản đã chạy. Chưa có bằng chứng về settlement, chống gian lận và giới hạn tải của endpoint production. Các nội dung này được theo dõi bằng kiểm tra tích hợp và giám sát sau triển khai theo phạm vi được phê duyệt.

Cách viết này nêu kết quả, điều kiện, phạm vi và giới hạn. Tránh câu như “toàn bộ hệ thống đã được kiểm thử thành công” nếu bằng chứng chỉ bao phủ một phần.

### 9.4. Truy vết giới hạn đến yêu cầu và quyết định phát hành

Liên kết:

- Yêu cầu hoặc thuộc tính chất lượng.
- Test case và test run.
- Môi trường cùng khác biệt.
- Bằng chứng đạt/không đạt.
- Giới hạn và rủi ro còn lại.
- Hành động khắc phục hoặc kiểm tra bổ sung.
- Người chấp nhận rủi ro và quyết định phát hành.

Khi môi trường được nâng cấp hoặc khác biệt được loại bỏ, cập nhật hồ sơ và chạy lại kiểm thử liên quan. Không để giới hạn cũ tiếp tục xuất hiện trong báo cáo sau khi điều kiện đã thay đổi.

## 10. Ví dụ tổng hợp: giới hạn bằng chứng của một hành trình đặt hàng

Giả sử hành trình gồm Web, Order API, Inventory, Payment service, nhà cung cấp thanh toán, message broker và Notification.

### 10.1. Điều kiện môi trường

| Thuộc tính | Staging | Production tham chiếu |
|---|---|---|
| Ứng dụng | Build ứng viên phát hành | Build đã triển khai |
| Dịch vụ nội bộ | Bản dựng thật của staging | Bản triển khai thật |
| Database | Dữ liệu tổng hợp, dung lượng nhỏ hơn | Dữ liệu giao dịch lớn và lịch sử dài |
| Payment provider | Sandbox | Endpoint production |
| Broker | Một cụm nhỏ | Cụm có cấu hình HA |
| Tải | Một tập hồi quy nhỏ | Tải biến động theo giờ |
| Tài khoản | Tài khoản thử có quyền giới hạn | Vai trò và chính sách thật |
| Giám sát | Log chi tiết, trace đầy đủ | Có sampling và chính sách retention |

### 10.2. Kết quả kiểm thử staging

Các kịch bản đã chạy:

- Đặt hàng với tồn kho đủ.
- Thanh toán thành công qua sandbox.
- Thanh toán bị từ chối.
- Hủy đơn ở trạng thái được phép.
- Gửi lại yêu cầu với cùng idempotency key.

Kết quả đều đạt theo tiêu chí đã xác định. Điều đó cung cấp bằng chứng về luồng ứng dụng và các dịch vụ nội bộ trong cấu hình staging.

### 10.3. Giới hạn còn lại

- Sandbox không đại diện đầy đủ cho settlement và chống gian lận production.
- Dataset nhỏ chưa chứng minh hiệu năng truy vấn với dữ liệu lịch sử lớn.
- Cụm broker staging nhỏ chưa xác nhận failover production.
- Tải hồi quy chưa đại diện giờ cao điểm.
- Ma trận tài khoản chưa bao phủ mọi vai trò và tenant.
- Mức log staging khác production nên cách điều tra có thể khác.

### 10.4. Kế hoạch bổ sung bằng chứng

| Khoảng trống | Kiểm tra bổ sung |
|---|---|
| Hành vi payment production | Contract và sandbox integration; kiểm tra cấu hình; đối soát sau triển khai trong phạm vi an toàn |
| Dữ liệu lớn | Performance test với dữ liệu tổng hợp có phân bố đại diện |
| Broker HA | Resilience test trên topology tương ứng |
| Tải giờ cao điểm | Load và stress test theo mô hình tải đã xác nhận |
| Quyền tenant | Role/tenant matrix và kiểm tra truy cập đối tượng |
| Quan sát production | Synthetic monitoring, metrics và trace theo chính sách |

Nhóm có thể đưa ra quyết định phát hành khi các rủi ro trọng yếu đã có bằng chứng hoặc được người có thẩm quyền chấp nhận kèm biện pháp giảm thiểu. Kết quả staging không cần bị phủ nhận; cần mô tả đúng phần nó đã chứng minh.

## 11. Những sai lầm thường gặp

1. **Coi staging là bản sao production:** không kiểm tra khác biệt về cấu hình, dữ liệu, hạ tầng và tích hợp.
2. **Suy rộng từ kết quả pass:** cho rằng tất cả rủi ro đã được loại trừ dù chỉ chạy một số kịch bản.
3. **Không ghi phiên bản và cấu hình:** kết quả không thể tái tạo hoặc không rõ áp dụng cho bản dựng nào.
4. **Bỏ qua dữ liệu:** dùng dataset nhỏ, sạch và mới rồi kết luận truy vấn hoặc báo cáo sẽ hoạt động ở quy mô thực.
5. **Nhầm mock với tích hợp thật:** báo cáo hành trình đạt mà không nêu phụ thuộc đã được thay thế.
6. **Dùng tài khoản quá quyền:** bỏ sót lỗi phân quyền và ranh giới tenant.
7. **Không kiểm tra topology:** bỏ qua lỗi nhiều instance, failover và trạng thái phân tán.
8. **Không đại diện điều kiện mạng:** bỏ sót timeout, retry và kết nối không ổn định.
9. **Không so sánh cấu hình phát hành:** feature flag, timeout hoặc giới hạn khác làm thay đổi hành vi.
10. **Dựa vào log không đầy đủ:** kết luận không có lỗi dù nguồn quan sát không ghi nhận được lỗi.
11. **Dùng production cho thử nghiệm không an toàn:** tạo tác dụng phụ hoặc thay đổi dữ liệu thật ngoài phạm vi được phép.
12. **Ghi giới hạn nhưng không có hành động:** không xác định người chịu trách nhiệm, cách giảm thiểu hoặc điều kiện xem xét lại.

## 12. Checklist xác định giới hạn bằng chứng do điều kiện môi trường khác thực tế

- [ ] Đã xác định môi trường thực tế hoặc cấu hình tham chiếu cần so sánh.
- [ ] Đã ghi phiên bản ứng dụng, dịch vụ, schema và cấu hình của lần chạy.
- [ ] Đã so sánh hạ tầng, topology, mạng và tài nguyên có liên quan.
- [ ] Đã đánh giá quy mô, phân bố, lịch sử và trạng thái dữ liệu.
- [ ] Đã ghi rõ dịch vụ thật, sandbox, mock, stub hoặc thành phần không tham gia.
- [ ] Đã so sánh danh tính, vai trò, quyền và chính sách bảo mật.
- [ ] Đã xem xét timezone, locale, clock và lịch chạy tác vụ.
- [ ] Đã xác định mức độ đầy đủ của log, metrics, trace và artifact.
- [ ] Đã đánh giá mức đại diện theo từng thuộc tính thay vì dùng một nhãn chung.
- [ ] Đã xác định rủi ro có thể bị che giấu bởi từng khác biệt.
- [ ] Đã phân biệt kết quả pass với phạm vi bằng chứng thực sự có.
- [ ] Đã bổ sung kiểm thử ở môi trường hoặc tầng phù hợp cho khoảng trống quan trọng.
- [ ] Đã ghi giới hạn, rủi ro còn lại, hành động và người chịu trách nhiệm.
- [ ] Việc kiểm tra production, nếu có, có phạm vi và biện pháp an toàn được phê duyệt.
- [ ] Kết luận kiểm thử nêu rõ điều kiện, phạm vi và những điều chưa được chứng minh.
- [ ] Hồ sơ được cập nhật khi môi trường hoặc cấu hình tham chiếu thay đổi.

Xác định giới hạn bằng chứng giúp nhóm hiểu chính xác một kết quả kiểm thử đã chứng minh điều gì trong điều kiện cụ thể. Khi các khác biệt về phiên bản, cấu hình, dữ liệu, tích hợp, hạ tầng và vận hành được ghi nhận, nhóm có thể bổ sung kiểm tra đúng chỗ, quản lý rủi ro còn lại và đưa ra quyết định phát hành minh bạch hơn.
