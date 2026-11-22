# Kiểm soát phạm vi và quyền của giao diện hỗ trợ kiểm thử

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), khả năng kiểm thử tốt giúp nhóm thiết lập trạng thái ban đầu, điều khiển điều kiện, quan sát kết quả và tái lập lỗi. Nhiều hệ thống vì thế cung cấp các giao diện hỗ trợ kiểm thử (*testability interfaces*), chẳng hạn API tạo dữ liệu mẫu, công cụ đặt lại trạng thái, đồng hồ giả lập, điểm quan sát sự kiện, trang chẩn đoán, selector ổn định cho UI hoặc cơ chế mô phỏng lỗi.

Những giao diện này có thể rút ngắn thời gian kiểm thử và giúp xác minh các tình huống khó tạo bằng thao tác người dùng thông thường. Tuy nhiên, chúng cũng có thể trở thành đường truy cập nhạy cảm nếu cho phép bỏ qua xác thực, thay đổi dữ liệu tùy ý, đọc thông tin nội bộ hoặc tác động đến môi trường ngoài phạm vi. Vì vậy, thiết kế testability cần xác định rõ **giao diện nào được cung cấp, ai được sử dụng, trên tài nguyên và môi trường nào, trong thời gian bao lâu, và hành động nào được phép**.

Bài học này hướng dẫn cách phân loại giao diện hỗ trợ kiểm thử, thiết kế phạm vi và quyền truy cập, cô lập dữ liệu và môi trường, kiểm soát các thao tác nguy hiểm, kiểm tra cả đường truy cập hợp lệ lẫn trái phép và quản lý vòng đời của các hỗ trợ này.

## 1. Hiểu giao diện hỗ trợ kiểm thử

### 1.1. Giao diện hỗ trợ kiểm thử là gì?

Giao diện hỗ trợ kiểm thử là điểm tương tác được thiết kế để giúp người kiểm thử hoặc công cụ kiểm thử chuẩn bị, điều khiển, quan sát hay xác minh hệ thống. Nó có thể là một API, một trang quản trị trong môi trường thử nghiệm, một hook trong ứng dụng, một fixture, một lệnh quản lý dữ liệu hoặc metadata dành cho automation.

Các giao diện thường gặp:

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Chuẩn bị dữ liệu | Tạo tài khoản, đơn hàng, trạng thái mẫu hoặc tập dữ liệu fixture. | Đưa hệ thống về điều kiện ban đầu có thể dự đoán. |
| Dọn dẹp và đặt lại | Xóa dữ liệu thuộc một lần chạy, reset sandbox hoặc khôi phục trạng thái. | Giữ các lần chạy độc lập và tái lập. |
| Điều khiển thời gian | Đồng hồ giả lập, đặt thời điểm hoặc tăng thời gian trong môi trường thử nghiệm. | Kiểm tra hết hạn, lịch chạy và quy tắc phụ thuộc thời gian. |
| Điều khiển phụ thuộc | Stub service, giả lập phản hồi, fault injection hoặc bật chế độ sandbox. | Tạo timeout, lỗi hoặc phản hồi đặc biệt có kiểm soát. |
| Quan sát và chẩn đoán | Health endpoint, test event log, trace ID, trạng thái job hoặc trang diagnostics. | Thu thập bằng chứng và định vị nguyên nhân. |
| Điều khiển tính năng | Feature flag hoặc cấu hình thử nghiệm theo tài khoản/tenant. | Kiểm tra các nhánh hành vi mà không thay đổi toàn bộ hệ thống. |
| Hỗ trợ UI automation | Accessible name, role, test ID hoặc thuộc tính định danh ổn định. | Giúp automation tìm đúng thành phần giao diện. |
| Điều phối tác vụ | Chạy lại job, phát sự kiện thử nghiệm hoặc chờ tác vụ bất đồng bộ. | Kiểm tra workflow và xử lý nền. |

Một giao diện hỗ trợ kiểm thử cần có mục đích và hợp đồng rõ ràng. Người sử dụng phải biết nó thay đổi điều gì, trả về bằng chứng nào, có tác dụng phụ gì và giới hạn áp dụng ở đâu.

### 1.2. Phân biệt giao diện sản phẩm và giao diện hỗ trợ kiểm thử

Giao diện sản phẩm là cách người dùng hoặc hệ thống tích hợp thực hiện nghiệp vụ. Giao diện hỗ trợ kiểm thử giúp chuẩn bị hoặc quan sát điều kiện để kiểm tra nghiệp vụ đó.

Ví dụ, người dùng tạo đơn hàng qua checkout UI hoặc order API là hành vi sản phẩm. Một test fixture API tạo đơn hàng ở trạng thái SHIPPED để kiểm tra trang lịch sử là hỗ trợ kiểm thử. Nếu mục tiêu kiểm tra là người dùng có thể đặt hàng, dùng fixture để tạo sẵn đơn hàng sẽ bỏ qua hành vi đang cần xác minh.

Cần ghi rõ giao diện nào được dùng để setup, giao diện nào thực hiện hành vi mục tiêu và giao diện nào chỉ quan sát kết quả. Điều này giúp tránh nhầm lẫn giữa bằng chứng về sản phẩm và bằng chứng về công cụ kiểm thử.

### 1.3. Testability không đồng nghĩa với mở quyền truy cập

Một hệ thống dễ kiểm thử cần có cách tạo trạng thái và quan sát hành vi có kiểm soát. Điều đó không đòi hỏi endpoint bí mật, tài khoản dùng chung hoặc cơ chế bỏ qua xác thực.

Ví dụ, có thể tạo tài khoản thử nghiệm qua fixture API được giới hạn trong môi trường test, với quyền chỉ tạo dữ liệu thuộc namespace của lần chạy. Không cần một endpoint có thể tạo bất kỳ tài khoản quản trị nào mà không kiểm tra danh tính.

Nguyên tắc thiết kế là làm cho các hành vi cần kiểm tra có thể điều khiển và quan sát được, đồng thời giữ nguyên các ranh giới bảo mật cần xác minh.

## 2. Xác định phạm vi của từng giao diện

Trước khi triển khai hoặc sử dụng một giao diện hỗ trợ kiểm thử, hãy xác định phạm vi theo môi trường, tài nguyên, hành động và thời gian.

### 2.1. Phạm vi môi trường

Ghi rõ giao diện được phép hoạt động ở đâu:

- Local developer environment.
- Môi trường CI dùng cho một job hoặc pipeline.
- Integration test environment.
- Staging hoặc sandbox được chỉ định.
- Production, nếu có một chức năng quan sát chỉ đọc được phê duyệt riêng.

Các chức năng thay đổi dữ liệu, reset, giả lập thời gian hoặc fault injection thường chỉ nên tồn tại trong môi trường cô lập. Không được dựa vào việc URL khó đoán hoặc giao diện không được công bố để bảo vệ endpoint test.

Nếu một giao diện không được phép chạy trong production, cấu hình triển khai cần bảo đảm nó không được đăng ký hoặc không thể được kích hoạt ở môi trường đó. Khi phát hiện cấu hình môi trường không rõ hoặc không an toàn, hành vi mặc định phải là từ chối.

### 2.2. Phạm vi tài nguyên

Mỗi thao tác cần giới hạn trên tài nguyên cụ thể:

- Một test run hoặc pipeline ID.
- Một tenant hoặc workspace thử nghiệm.
- Một user/account được cấp cho test.
- Một nhóm bản ghi có định danh và nguồn tạo rõ ràng.
- Một service, queue hoặc sandbox cụ thể.
- Một feature flag trong phạm vi người dùng thử nghiệm.

Tránh thao tác kiểu “xóa tất cả dữ liệu” hoặc “reset toàn hệ thống” nếu mục tiêu chỉ cần dọn dữ liệu của một lần chạy. Dùng namespace riêng như testRunId để mọi bản ghi tạo ra đều có thể truy vết và thu hồi đúng phạm vi.

### 2.3. Phạm vi hành động

Phân loại rõ hành động được phép:

| Mức hành động | Ví dụ | Cách kiểm soát |
|---|---|---|
| Đọc và quan sát | Xem trạng thái job, health, test event hoặc trace. | Chỉ cấp dữ liệu cần thiết; che thông tin nhạy cảm. |
| Tạo dữ liệu thử nghiệm | Tạo fixture, tài khoản hoặc đơn hàng mẫu. | Giới hạn loại dữ liệu, tenant, số lượng và namespace. |
| Sửa trạng thái thử nghiệm | Đặt đồng hồ giả lập, bật flag hoặc chuyển trạng thái mẫu. | Chỉ áp dụng cho tài nguyên do test sở hữu; ghi audit. |
| Xóa hoặc reset | Dọn fixture hoặc reset sandbox. | Yêu cầu phạm vi chính xác, xác nhận điều kiện và hỗ trợ khôi phục khi cần. |
| Tạo lỗi có kiểm soát | Mô phỏng timeout, lỗi phụ thuộc hoặc message trễ. | Chỉ cho phép ở môi trường cô lập, có giới hạn thời gian và điều kiện dừng. |
| Tác động hạ tầng | Restart service, thay đổi routing hoặc cấu hình mạng. | Quyền riêng biệt, phê duyệt phù hợp và phạm vi thực thi rõ. |

Không nên gom mọi hành động vào một quyền chung như test-admin. Quyền đọc log không cần đồng nghĩa với quyền xóa dữ liệu hoặc gây lỗi cho dịch vụ.

### 2.4. Phạm vi thời gian

Quyền hỗ trợ kiểm thử nên có thời hạn:

- Credential dùng cho một job hoặc một phiên.
- Token có thời hạn ngắn và có thể thu hồi.
- Fixture có TTL hoặc được dọn khi kết thúc run.
- Fault injection tự tắt sau khoảng thời gian định trước.
- Feature flag thử nghiệm có người sở hữu và ngày hết hạn.

Quyền tồn tại vô thời hạn dễ bị quên, tái sử dụng sai mục đích hoặc trở thành đường truy cập không còn được giám sát.

## 3. Thiết kế quyền truy cập theo nguyên tắc tối thiểu

### 3.1. Xác thực người hoặc hệ thống gọi

Mọi giao diện có khả năng đọc dữ liệu nội bộ hoặc thay đổi trạng thái cần xác định danh tính caller. Tùy môi trường, có thể dùng:

- Danh tính service account riêng cho CI.
- Token ngắn hạn được cấp cho từng pipeline.
- SSO hoặc cơ chế xác thực của môi trường staging.
- Chứng thư hoặc workload identity cho service-to-service.
- Tài khoản thử nghiệm riêng cho từng vai trò người dùng.

Không dùng một credential chia sẻ cho cả nhóm nếu không thể truy vết ai hoặc job nào đã thực hiện hành động. Không nhúng secret dài hạn vào mã nguồn, file cấu hình công khai hoặc log pipeline.

### 3.2. Phân quyền theo vai trò và hành động

Sau khi xác thực, hệ thống cần kiểm tra caller có được phép thực hiện hành động cụ thể trên tài nguyên cụ thể hay không.

Ví dụ ma trận quyền:

| Vai trò | Đọc diagnostics | Tạo fixture | Dọn fixture của mình | Đặt clock | Fault injection |
|---|---:|---:|---:|---:|---:|
| Developer trong local | Có | Có | Có | Có | Có, trong local |
| CI test runner | Có, trong job | Có, trong namespace job | Có, trong namespace job | Có, trong job | Có, nếu suite được phép |
| QA trên staging | Có, trong phạm vi được cấp | Có | Có, trong tenant test | Theo quyền riêng | Theo phê duyệt |
| Service vận hành | Theo nhiệm vụ | Không mặc định | Không mặc định | Không mặc định | Chỉ theo quy trình vận hành |
| Người dùng sản phẩm | Không | Không | Không | Không | Không |

Ma trận chỉ là ví dụ. Dự án cần xác định vai trò thực tế và quyền tương ứng. Quyền phải được kiểm tra ở server hoặc lớp kiểm soát đáng tin cậy, không chỉ bằng cách ẩn nút trên UI.

### 3.3. Kết hợp quyền với phạm vi tài nguyên

Chỉ kiểm tra vai trò là chưa đủ. Một CI runner có thể được phép tạo fixture nhưng chỉ trong namespace của pipeline hiện tại. QA có thể được phép đọc diagnostics của tenant staging được giao nhưng không được đọc dữ liệu của tenant khác.

Mỗi request nên được ràng buộc với:

- Caller đã xác thực.
- Vai trò hoặc scope được cấp.
- Môi trường đích.
- Tenant, project hoặc test run.
- Loại tài nguyên và hành động.
- Thời hạn hoặc trạng thái của phiên cấp quyền.

Server phải xác minh các ràng buộc này mỗi lần gọi. Không tin các trường tenantId, userId hoặc environment do client tự gửi nếu chưa đối chiếu với danh tính và quyền đã xác thực.

### 3.4. Mặc định từ chối

Nếu thiếu danh tính, quyền, môi trường hoặc phạm vi tài nguyên, giao diện phải từ chối yêu cầu. Không nên có chế độ “mặc định cho phép” khi cấu hình test bị thiếu.

Một số trường hợp cần từ chối rõ ràng:

- Không xác định được môi trường hiện tại.
- Token hết hạn hoặc không có scope cần thiết.
- testRunId không thuộc caller.
- Tài nguyên nằm ngoài tenant được cấp.
- Fault injection được gọi trên môi trường không cho phép.
- Yêu cầu reset không có phạm vi cụ thể.
- Feature flag không thuộc quyền quản lý của caller.

Thông báo lỗi nên đủ để người kiểm thử hiểu lý do nhưng không tiết lộ secret, cấu trúc nội bộ hoặc dữ liệu của tài khoản khác.

## 4. Thiết kế các giao diện hỗ trợ thường gặp

### 4.1. Fixture API và dữ liệu mẫu

Fixture API giúp tạo dữ liệu có cấu trúc và trạng thái xác định. Thiết kế nên:

- Chỉ chấp nhận loại fixture được định nghĩa.
- Giới hạn số lượng và kích thước dữ liệu.
- Gắn mọi bản ghi với testRunId hoặc namespace.
- Trả về ID để test có thể truy vết.
- Không cho phép chỉ định tùy ý tenant hoặc chủ sở hữu ngoài scope.
- Dùng dữ liệu giả, không sao chép dữ liệu cá nhân thật.
- Có cơ chế cleanup tương ứng.

Ví dụ hợp đồng minh họa:

~~~http
POST /test-support/v1/fixtures/orders
Authorization: Bearer <short-lived-test-token>
Content-Type: application/json

{
  "testRunId": "ci-4821",
  "scenario": "order-awaiting-payment"
}
~~~

Server xác minh token, môi trường, scope và testRunId; sau đó tạo một fixture thuộc namespace được phép và trả về định danh. Client không được tùy ý yêu cầu tạo đơn của người dùng thật hoặc truy cập tenant ngoài phạm vi.

### 4.2. Cleanup và reset dữ liệu

Cleanup cần an toàn hơn thao tác tạo dữ liệu vì một lỗi phạm vi có thể xóa tài nguyên ngoài ý muốn.

Thiết kế tốt nên:

- Xóa theo namespace hoặc danh sách ID đã được tạo bởi run.
- Kiểm tra quyền sở hữu trước khi xóa.
- Hỗ trợ chế độ preview/dry-run nếu thao tác có phạm vi lớn.
- Giới hạn số lượng bản ghi trong một lần gọi.
- Ghi audit về caller, phạm vi và kết quả.
- Có TTL để dọn tự động dữ liệu thử nghiệm bị bỏ quên.
- Từ chối thao tác không có testRunId hoặc scope cụ thể.

Tránh cung cấp endpoint reset database dùng chung cho mọi người. Nếu cần reset môi trường, thực hiện qua quy trình vận hành riêng, có quyền và xác nhận phù hợp.

### 4.3. Đồng hồ giả lập và điều khiển thời gian

Clock abstraction giúp kiểm tra thời hạn, lịch chạy, ngày nhuận và trạng thái phụ thuộc thời gian mà không phải chờ thực tế.

Nên giới hạn clock giả lập ở process, tenant hoặc test run cụ thể. Test không được thay đổi đồng hồ hệ thống của máy chủ dùng chung. Cần xác định:

- Ai có quyền đặt hoặc tiến thời gian.
- Phạm vi service nào sử dụng clock đó.
- Các job hoặc cache có được đồng bộ theo clock không.
- Cách khôi phục về thời gian thật.
- Hành vi khi phiên test kết thúc hoặc token hết hạn.

Nếu clock giả lập được chia sẻ giữa nhiều test, một test có thể làm thay đổi kết quả của test khác. Cần cô lập trạng thái thời gian theo run hoặc thực thi tuần tự khi không thể cô lập.

### 4.4. Fault injection và mô phỏng phụ thuộc

Fault injection có thể tạo timeout, lỗi mạng, phản hồi 5xx, message trễ, message lặp hoặc service không sẵn sàng. Đây là công cụ hữu ích để kiểm tra retry, timeout, circuit breaker và khả năng phục hồi.

Các điều kiện cần có:

- Chỉ bật trong môi trường và service được cho phép.
- Xác định đối tượng, loại lỗi và thời gian áp dụng.
- Giới hạn tỷ lệ hoặc số request bị ảnh hưởng.
- Có thời hạn tự tắt và nút dừng khẩn cấp.
- Không tác động đến traffic ngoài test run.
- Ghi audit và hiển thị trạng thái đang bật.
- Xác minh hệ thống trở về bình thường sau khi kết thúc.

Không dùng một cờ lỗi toàn cục trên staging dùng chung nếu có thể ảnh hưởng các nhóm khác. Ưu tiên fault injection theo request header được ký, tenant hoặc namespace riêng, với kiểm tra phía server.

### 4.5. Diagnostics, event và log hỗ trợ test

Giao diện quan sát có thể cung cấp health, trạng thái job, event đã phát, trace ID và kết quả xử lý. Chỉ cung cấp trường cần thiết cho việc xác minh.

Cần chú ý:

- Ẩn token, khóa, mật khẩu và dữ liệu cá nhân.
- Giới hạn quyền xem theo tenant, service hoặc test run.
- Không để endpoint diagnostics công khai thông tin cấu hình nhạy cảm.
- Không cho phép ghi log tùy ý vào hệ thống dùng chung.
- Giữ thời hạn lưu trữ phù hợp.
- Ghi lại ai đã truy cập dữ liệu diagnostics nhạy cảm.

Một endpoint health công khai có thể chỉ trả trạng thái tổng quát. Chi tiết về dependency, queue, cấu hình hoặc phiên bản nội bộ cần quyền phù hợp.

### 4.6. UI selector và thuộc tính phục vụ automation

UI automation cần cách nhận diện thành phần ổn định. Có thể dùng role, accessible name hoặc thuộc tính test ID được quản lý. Các selector này giúp test tránh phụ thuộc vào vị trí pixel hoặc cấu trúc CSS dễ thay đổi.

Ví dụ:

~~~html
<button data-testid="checkout-submit">
  Đặt hàng
</button>
~~~

Test ID chỉ hỗ trợ định vị thành phần; nó không phải cơ chế phân quyền hoặc bảo vệ dữ liệu. Không đưa thông tin nhạy cảm, token hay ID nội bộ bí mật vào thuộc tính hiển thị trên DOM. Với giao diện có dữ liệu theo vai trò, vẫn cần kiểm tra quyền ở backend.

## 5. Ngăn giao diện hỗ trợ kiểm thử trở thành đường tắt bảo mật

### 5.1. Không tạo bypass xác thực hoặc phân quyền

Tránh các cơ chế như:

- Header bí mật để đăng nhập thành admin.
- Query parameter cho phép bỏ qua kiểm tra quyền.
- Tài khoản quản trị dùng chung, không có audit.
- Endpoint test cho phép đọc mọi bản ghi.
- Hook có thể thay đổi trạng thái của tài nguyên bất kỳ.
- Cờ cấu hình có thể bật từ request của người dùng thông thường.

Nếu cần tạo trạng thái người dùng đã đăng nhập, hãy dùng danh tính thử nghiệm và quy trình cấp token có kiểm soát. Nếu cần kiểm tra quyền, test phải đi qua chính cơ chế xác thực và phân quyền đang được xác minh.

### 5.2. Cô lập theo môi trường và build

Cách an toàn nhất cho chức năng thay đổi trạng thái là chỉ đóng gói hoặc đăng ký trong build dành cho test, hoặc chỉ triển khai vào môi trường được phê duyệt. Nếu dùng cùng artifact cho nhiều môi trường, phải có kiểm soát server-side đáng tin cậy để chức năng không thể kích hoạt trong production.

Không chỉ ẩn route ở frontend. Người dùng có thể gọi trực tiếp API. Không chỉ kiểm tra biến môi trường ở client. Quyết định cho phép phải được thực thi ở backend hoặc hạ tầng có quyền kiểm soát.

### 5.3. Giới hạn mạng và nguồn gọi

Có thể bổ sung network policy, private endpoint hoặc allowlist cho CI runner và mạng thử nghiệm. Đây là lớp bảo vệ bổ sung, không thay thế xác thực và phân quyền ở ứng dụng.

Không dựa duy nhất vào IP allowlist vì địa chỉ nguồn có thể thay đổi, bị chia sẻ hoặc không xác định chính xác danh tính caller.

### 5.4. Tách quyền đọc, tạo, sửa, xóa và gây lỗi

Các quyền này có mức tác động khác nhau. Người cần xem trạng thái job không nên tự động có quyền reset dữ liệu. Người tạo fixture không nhất thiết được phép thay đổi clock hoặc mô phỏng lỗi toàn service.

Dùng scope riêng và kiểm tra quyền tại từng thao tác. Khi một chức năng có nhiều tác dụng phụ, hãy chia thành các thao tác nhỏ có hợp đồng rõ để giới hạn quyền và dễ audit.

### 5.5. Không để test support ảnh hưởng dữ liệu thật

Dữ liệu fixture phải được đánh dấu và cô lập. Cleanup chỉ được phép xóa dữ liệu có bằng chứng thuộc test run. Không sử dụng bản sao production chưa được xử lý dữ liệu nhạy cảm.

Với các tích hợp bên ngoài, dùng sandbox hoặc tài khoản thử nghiệm. Nếu cần xác minh một hành vi trên production, ưu tiên thao tác chỉ đọc và quy trình được phê duyệt; không bật fault injection hoặc reset qua giao diện test.

## 6. Kiểm tra phạm vi và quyền của chính giao diện hỗ trợ

Không chỉ kiểm tra tính năng sản phẩm. Giao diện hỗ trợ kiểm thử cũng cần có test cho các trường hợp hợp lệ, sai quyền và vượt phạm vi.

### 6.1. Kiểm tra xác thực

- Không có token hoặc danh tính: yêu cầu bị từ chối.
- Token sai chữ ký hoặc hết hạn: yêu cầu bị từ chối.
- Token có issuer hoặc audience không đúng: yêu cầu bị từ chối.
- Credential đã thu hồi: không còn sử dụng được.
- Service account của job khác: không truy cập được namespace hiện tại.

### 6.2. Kiểm tra phân quyền và phạm vi tài nguyên

| Tình huống | Kết quả cần xác minh |
|---|---|
| Caller có quyền đọc nhưng gọi tạo fixture | Bị từ chối. |
| Caller có quyền tạo fixture nhưng chọn tenant ngoài scope | Bị từ chối. |
| CI runner của run A xóa dữ liệu run B | Bị từ chối; dữ liệu run B không đổi. |
| QA có quyền diagnostics nhưng gọi reset | Bị từ chối. |
| Người dùng sản phẩm gọi endpoint test-support | Bị từ chối. |
| Caller dùng testRunId không thuộc mình | Bị từ chối. |
| Token hết hạn trong phiên | Thao tác tiếp theo bị từ chối. |
| Caller có quyền đúng nhưng môi trường không được phép | Bị từ chối. |

Khi bị từ chối, cần xác minh không có tác dụng phụ một phần. Ví dụ, request xóa bị từ chối không được xóa một số bản ghi trước khi kiểm tra xong quyền.

### 6.3. Kiểm tra giới hạn đầu vào và chống lạm dụng

Giao diện hỗ trợ cũng cần giới hạn:

- Số lượng fixture trong một request.
- Kích thước payload và file.
- Tần suất gọi và số tác vụ đồng thời.
- Thời lượng fault injection.
- Số bản ghi được reset.
- Độ dài tên, ID và nhãn do caller cung cấp.
- Các giá trị enum được hỗ trợ.

Kiểm tra dữ liệu ở server và từ chối giá trị không được định nghĩa. Không cho phép caller truyền lệnh, tên bảng, câu truy vấn hoặc đường dẫn tùy ý để thực hiện thao tác quản trị.

### 6.4. Kiểm tra audit và khả năng truy vết

Với thao tác nhạy cảm, xác minh audit log ghi đủ:

- Danh tính caller hoặc service account.
- Hành động và tài nguyên.
- Môi trường, tenant và testRunId.
- Thời điểm và kết quả.
- Lý do hoặc mã tham chiếu nếu quy trình yêu cầu.

Không ghi credential, token hoặc payload nhạy cảm đầy đủ. Audit log cần có quyền truy cập và thời hạn lưu giữ phù hợp; người gọi test-support không nên có quyền sửa hoặc xóa dấu vết do chính họ tạo.

## 7. Thiết kế hợp đồng và vòng đời cho test-support API

Một giao diện hỗ trợ tốt cần có hợp đồng ổn định, tài liệu và cơ chế ngừng sử dụng.

### 7.1. Hợp đồng rõ ràng

Với mỗi thao tác, mô tả:

- Mục đích và trường hợp sử dụng.
- Method, path hoặc lệnh.
- Scope và vai trò cần có.
- Môi trường được phép.
- Input, output và giới hạn.
- Tác dụng phụ.
- Mã lỗi và hành vi khi từ chối.
- Cách dọn dẹp hoặc khôi phục.
- Phiên bản hợp đồng và chính sách tương thích.

Không tạo endpoint chỉ với tên chung như reset hoặc debug mà không mô tả chính xác phạm vi tác động.

### 7.2. Idempotency và khả năng chạy lại

Test có thể được chạy lại sau timeout hoặc lỗi CI. Các thao tác tạo fixture nên hỗ trợ định danh theo run hoặc idempotency key để tránh tạo dữ liệu trùng khi request được gửi lại.

Cleanup cần an toàn khi gọi nhiều lần: lần gọi tiếp theo không được xóa tài nguyên ngoài scope hoặc gây lỗi khó hiểu chỉ vì fixture đã được dọn.

### 7.3. TTL và thu hồi

Fixture, token, feature flag và fault injection nên có vòng đời hữu hạn. Cần quy định:

- Thời điểm hết hạn.
- Cách gia hạn nếu được phép.
- Ai có thể thu hồi.
- Điều gì xảy ra khi run bị hủy.
- Cách dọn dữ liệu khi worker hoặc pipeline dừng bất thường.
- Cảnh báo khi tài nguyên thử nghiệm tồn tại quá lâu.

TTL không thay thế cleanup có chủ đích, nhưng giúp hạn chế dữ liệu và quyền bị bỏ quên.

### 7.4. Phiên bản hóa và ngừng hỗ trợ

Khi thay đổi hợp đồng test-support, cần thông báo cho các bộ test phụ thuộc, cung cấp thời gian chuyển đổi phù hợp và xóa endpoint cũ sau khi xác nhận không còn caller hợp lệ.

Giao diện test-support thường không phải API sản phẩm công khai, nhưng vẫn cần quản lý thay đổi để tránh làm hỏng pipeline hoặc khiến nhóm tạo ra cách sử dụng không an toàn.

## 8. Quy trình thiết kế và phê duyệt một giao diện hỗ trợ kiểm thử

Có thể dùng quy trình sau khi đề xuất một endpoint, hook hoặc công cụ mới.

### Bước 1: Nêu mục tiêu kiểm thử

Xác định vấn đề hiện tại: setup quá chậm, không tạo được trạng thái hiếm, khó quan sát tác vụ bất đồng bộ hay không thể tái lập lỗi.

### Bước 2: Chọn giao diện tối thiểu cần thiết

Xác định thao tác nào cần cung cấp và liệu có thể dùng API sản phẩm, fixture có sẵn hoặc công cụ môi trường hiện tại hay không. Mỗi giao diện mới cần có lý do duy trì.

### Bước 3: Xác định môi trường, tài nguyên và hành động

Ghi rõ môi trường cho phép, namespace, tenant, tài nguyên, giới hạn số lượng, thời gian và tác dụng phụ.

### Bước 4: Thiết kế danh tính và quyền

Chọn caller, scope và quyền tối thiểu. Tách quyền đọc, tạo, sửa, xóa, điều khiển thời gian và fault injection.

### Bước 5: Thiết kế guardrail và hành vi từ chối

Quy định mặc định từ chối, kiểm tra server-side, allowlist môi trường, TTL, audit, rate limit và điều kiện dừng. Xác định hành vi nếu cấu hình bị thiếu hoặc không nhất quán.

### Bước 6: Viết kiểm thử cho chính giao diện hỗ trợ

Kiểm tra caller hợp lệ, caller sai quyền, tài nguyên ngoài scope, token hết hạn, môi trường không cho phép, payload quá giới hạn và thao tác lặp. Xác minh không có tác dụng phụ khi request bị từ chối.

### Bước 7: Triển khai, quan sát và rà soát

Ghi nhận ai sử dụng, thao tác nào được gọi, lỗi quyền và tài nguyên còn tồn tại. Rà soát định kỳ quyền, endpoint và dữ liệu thử nghiệm; thu hồi những giao diện không còn cần thiết.

## 9. Ví dụ: test-support cho luồng đặt hàng

Giả sử nhóm cần kiểm tra trang lịch sử đơn hàng, callback thanh toán trễ và khả năng xử lý lỗi của order service. Nếu phải tạo toàn bộ trạng thái qua UI, test sẽ chậm và khó tạo các tình huống hiếm.

Có thể thiết kế một bộ hỗ trợ trong môi trường integration riêng:

| Giao diện | Mục đích | Phạm vi và quyền |
|---|---|---|
| Fixture API tạo đơn | Tạo đơn PENDING, PAID hoặc SHIPPED cho test. | Chỉ tenant test và testRunId của caller; giới hạn số lượng. |
| Diagnostics API | Đọc trạng thái xử lý và trace ID của đơn fixture. | Chỉ đọc đơn thuộc namespace được cấp; che dữ liệu nhạy cảm. |
| Clock control | Đưa đồng hồ của test run đến thời điểm callback hết hạn. | Chỉ áp dụng cho service instance hoặc namespace cô lập. |
| Fault control | Mô phỏng callback trễ hoặc timeout phụ thuộc. | Chỉ sandbox riêng; TTL ngắn và tự tắt. |
| Cleanup API | Xóa fixture sau khi test hoàn tất. | Chỉ xóa tài nguyên có testRunId khớp caller. |
| UI test selector | Tìm dòng đơn hàng và trạng thái trên trang lịch sử. | Không cấp quyền dữ liệu; chỉ là định danh giao diện ổn định. |

### 9.1. Luồng kiểm thử

1. CI runner nhận token ngắn hạn với scope tạo, đọc và dọn fixture trong một test run.
2. Fixture API tạo một đơn PENDING thuộc tenant thử nghiệm và trả về order ID.
3. Test mở UI bằng tài khoản có quyền xem đơn và xác minh dòng đơn xuất hiện.
4. Fault control mô phỏng callback đến trễ trong sandbox riêng.
5. Diagnostics API cung cấp trạng thái job và trace ID để test chờ điều kiện phù hợp.
6. UI và API xác minh đơn chuyển sang trạng thái mong đợi.
7. Cleanup API xóa fixture thuộc đúng testRunId.
8. Quyền token hết hạn hoặc được thu hồi sau run.

### 9.2. Kiểm tra âm tính

Bộ test cho test-support cần xác minh thêm:

- Token của run A không đọc được fixture của run B.
- Caller chỉ có quyền diagnostics không thể tạo hoặc xóa fixture.
- Endpoint fault control bị từ chối trên môi trường không được phép.
- Người dùng sản phẩm không gọi được fixture API.
- Request cleanup không có testRunId bị từ chối.
- Token hết hạn không thể tiếp tục điều khiển clock.
- Request tạo quá số lượng giới hạn không tạo một phần dữ liệu ngoài dự kiến.

### 9.3. Tiêu chí hoàn tất

- Các giao diện hỗ trợ có mục đích và hợp đồng được tài liệu hóa.
- Môi trường và tài nguyên được giới hạn rõ.
- Caller có danh tính riêng và quyền tối thiểu.
- Thao tác nhạy cảm có audit, TTL và cơ chế thu hồi.
- Các đường truy cập trái phép bị từ chối ở server.
- Không có tác dụng phụ ngoài phạm vi khi request thất bại.
- Fixture có thể tái lập và cleanup không ảnh hưởng dữ liệu khác.
- Các hỗ trợ không cần thiết được loại bỏ hoặc vô hiệu hóa.

## 10. Mẫu đặc tả giao diện hỗ trợ kiểm thử

Có thể dùng mẫu sau để review một API, hook hoặc công cụ mới:

~~~text
Tên giao diện:
Mục tiêu kiểm thử:
Nhóm người dùng / caller:

Môi trường được phép:
Môi trường bị cấm:
Tài nguyên / tenant / testRun scope:

Hành động được cung cấp:
- Đọc:
- Tạo:
- Sửa:
- Xóa:
- Điều khiển thời gian / phụ thuộc:
- Quan sát:

Xác thực:
Vai trò và scope:
Điều kiện từ chối:
Giới hạn đầu vào / tần suất:
TTL / thu hồi:
Audit và dữ liệu log:

Tác dụng phụ:
Cơ chế cleanup / khôi phục:
Phiên bản hợp đồng:
Người sở hữu:
Ngày rà soát tiếp theo:

Kiểm thử bảo vệ giao diện:
- Caller hợp lệ:
- Không xác thực:
- Sai vai trò:
- Ngoài tenant / test run:
- Môi trường không được phép:
- Token hết hạn:
- Payload vượt giới hạn:
- Request lặp:
- Không có tác dụng phụ khi bị từ chối:
~~~

## 11. Những sai lầm thường gặp

- **Tạo endpoint test không giới hạn môi trường:** route có thể bị gọi ngoài môi trường dự kiến.
- **Dựa vào URL khó đoán hoặc ẩn nút UI:** người gọi vẫn có thể truy cập trực tiếp endpoint.
- **Dùng tài khoản quản trị chung:** khó truy vết và tạo quyền quá rộng.
- **Chỉ kiểm tra vai trò, không kiểm tra tài nguyên:** caller có thể truy cập tenant hoặc test run khác.
- **Cho phép reset toàn bộ dữ liệu:** một lỗi tham số có thể ảnh hưởng môi trường dùng chung.
- **Không có TTL:** fixture, token hoặc fault injection có thể tồn tại sau khi test kết thúc.
- **Dùng dữ liệu production:** có thể làm lộ dữ liệu cá nhân hoặc gây tác động ngoài ý muốn.
- **Không kiểm tra đường từ chối:** endpoint có thể vô tình cho phép caller sai quyền.
- **Không audit thao tác nhạy cảm:** khó điều tra khi dữ liệu bị thay đổi hoặc xóa.
- **Dùng test hook để bỏ qua hành vi đang cần xác minh:** kết quả test không còn chứng minh đúng luồng sản phẩm.
- **Không dọn hoặc cô lập fixture:** các test ảnh hưởng lẫn nhau và tạo kết quả không ổn định.
- **Giữ giao diện hỗ trợ sau khi hết nhu cầu:** bề mặt truy cập và chi phí bảo trì tăng.

## 12. Danh sách rà soát trước khi đưa giao diện hỗ trợ vào sử dụng

- [ ] Mục tiêu kiểm thử và lợi ích của giao diện được xác định.
- [ ] Giao diện sản phẩm và giao diện hỗ trợ kiểm thử được phân biệt rõ.
- [ ] Môi trường, tài nguyên, tenant và test run scope được giới hạn.
- [ ] Caller có danh tính riêng và credential có thời hạn.
- [ ] Quyền đọc, tạo, sửa, xóa và fault injection được tách riêng.
- [ ] Server xác minh quyền và phạm vi trên mỗi request.
- [ ] Cấu hình thiếu hoặc môi trường không rõ dẫn đến từ chối.
- [ ] Fixture dùng dữ liệu thử nghiệm, có namespace và cleanup.
- [ ] Reset, clock control và fault injection có guardrail và điều kiện dừng.
- [ ] Diagnostics không làm lộ secret hoặc dữ liệu nhạy cảm.
- [ ] UI selector ổn định nhưng không bị coi là cơ chế bảo mật.
- [ ] Kiểm thử âm tính xác minh caller sai quyền không tạo tác dụng phụ.
- [ ] Audit, TTL, thu hồi và phiên bản hóa được thiết kế.
- [ ] Giao diện được rà soát định kỳ và loại bỏ khi không còn cần thiết.

## Kết luận

Giao diện hỗ trợ kiểm thử giúp tạo dữ liệu, điều khiển điều kiện và quan sát hệ thống một cách có thể tái lập. Để sử dụng an toàn, cần giới hạn rõ môi trường, tài nguyên, hành động và thời gian; xác thực caller; phân quyền tối thiểu theo vai trò và phạm vi; đồng thời kiểm tra cả trường hợp được phép lẫn bị từ chối. Khi fixture, cleanup, clock, fault injection, diagnostics và UI hook có hợp đồng, audit và vòng đời rõ ràng, nhóm có thể cải thiện khả năng kiểm thử mà vẫn bảo vệ các ranh giới bảo mật của sản phẩm.
