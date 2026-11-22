# Hệ thống và E2E: Lựa chọn điểm bắt đầu và kết quả kết thúc có thể quan sát

## 1. Vì sao điểm bắt đầu và kết quả kết thúc quyết định chất lượng E2E?

Kiểm thử hệ thống và kiểm thử đầu cuối (end-to-end – E2E) xác nhận hành vi của sản phẩm qua một luồng có ý nghĩa đối với người dùng hoặc hệ thống gọi. Một kịch bản E2E cần trả lời được hai câu hỏi cốt lõi: **kiểm thử bắt đầu ở đâu và điều gì chứng minh hành trình đã hoàn tất đúng?**

Nếu điểm bắt đầu quá thấp, bài kiểm thử có thể bỏ qua phần quan trọng của hành trình. Ví dụ, gọi trực tiếp một hàm xử lý đơn hàng không chứng minh người dùng có thể tạo đơn qua giao diện hoặc API công khai. Nếu điểm bắt đầu quá rộng, bài kiểm thử có thể kéo theo nhiều hệ thống và điều kiện không liên quan, khiến kết quả chậm, khó tái hiện và khó xác định nguyên nhân.

Tương tự, nếu chỉ kiểm tra một thông báo tức thời hoặc mã HTTP thành công, bài kiểm thử có thể kết thúc trước khi nghiệp vụ thật sự hoàn tất. Một giao dịch có thể trả về trạng thái đã tiếp nhận trong khi worker vẫn chưa cập nhật dữ liệu, thanh toán chưa được đối soát hoặc thông báo chưa được gửi.

Trong **VALIDATION_TESTING_STRATEGY**, lựa chọn đúng điểm vào và kết quả cuối giúp:

- Xác định chính xác ranh giới sản phẩm cần xác nhận.
- Bao phủ hành trình có ý nghĩa thay vì kiểm tra các bước kỹ thuật rời rạc.
- Đặt điều kiện ban đầu có thể tái lập và dữ liệu phù hợp.
- Chọn oracle dựa trên trạng thái hoặc tác động nghiệp vụ có thể quan sát.
- Xử lý đúng các luồng bất đồng bộ, trạng thái trung gian và lỗi phụ thuộc.
- Giảm kiểm thử trùng lặp, flaky test và kết luận pass không đủ bằng chứng.

Một kịch bản tốt phải thể hiện rõ tác nhân, điểm vào, điều kiện trước, hành động, kết quả mong đợi, thời hạn quan sát và cách thu thập bằng chứng.

## 2. Phân biệt điểm bắt đầu, bước thực thi và kết quả cuối

Ba khái niệm này thường bị gộp vào một kịch bản, nhưng chúng có vai trò khác nhau.

| Thành phần | Ý nghĩa | Ví dụ trong hành trình đặt lịch |
| --- | --- | --- |
| Điểm bắt đầu (entry point) | Ranh giới mà tại đó kiểm thử đưa hành động vào hệ thống | Người dùng xác nhận đặt lịch trên giao diện hoặc client gọi API công khai |
| Điều kiện ban đầu (preconditions) | Trạng thái và dữ liệu cần có trước khi hành động bắt đầu | Người dùng đã đăng nhập, khung giờ còn trống, tài khoản có quyền đặt |
| Các bước thực thi | Tương tác và xử lý diễn ra trong hành trình | Kiểm tra khung giờ, tạo lịch, gọi thanh toán, xử lý callback |
| Kết quả cuối (end state) | Trạng thái nghiệp vụ hoặc tác động cần đạt để kết luận | Lịch được xác nhận đúng một lần, giao dịch được liên kết và người dùng tra cứu được lịch |
| Bằng chứng | Dữ liệu quan sát được để so sánh với oracle | Phản hồi API, trạng thái lịch, mã giao dịch, event và trace |

Điểm bắt đầu không nhất thiết là màn hình đầu tiên người dùng nhìn thấy. Nó phải là ranh giới phù hợp với mục tiêu của bài kiểm thử. Một bài E2E API có thể bắt đầu ở API công khai; bài E2E giao diện có thể bắt đầu ở trang đăng nhập; bài kiểm thử luồng xử lý nền có thể bắt đầu bằng việc gửi một event qua broker được hỗ trợ.

Kết quả cuối cũng không nhất thiết là bước cuối cùng trong giao diện. Nó là trạng thái hoặc tác động chứng minh mục tiêu nghiệp vụ đã được đáp ứng. Với luồng bất đồng bộ, kết quả cuối có thể xuất hiện sau phản hồi ban đầu.

## 3. Chọn điểm bắt đầu phù hợp với mục tiêu xác nhận

### 3.1. Bắt đầu từ hành trình hoặc rủi ro cần xác nhận

Trước khi chọn URL, màn hình hay API, hãy viết mục tiêu của kịch bản dưới dạng kết quả:

- Người mua hoàn tất đơn hàng và nhận được xác nhận.
- Người dùng chỉ xem được tài nguyên thuộc quyền của mình.
- Một callback thanh toán lặp không làm phát sinh giao dịch trùng.
- Một yêu cầu bị từ chối khi khung giờ đã được người khác đặt.
- Một event được xử lý và cập nhật trạng thái trong thời hạn đã thống nhất.

Sau đó xác định hành động đầu tiên nằm trong phạm vi cần kiểm tra. Nếu rủi ro liên quan đến trải nghiệm người dùng, có thể cần bắt đầu từ UI. Nếu rủi ro nằm ở hợp đồng API giữa hai hệ thống, điểm vào phù hợp có thể là API. Nếu cần xác nhận consumer xử lý message, có thể bắt đầu từ một event hợp lệ tại ranh giới message broker.

Điểm vào nên đủ cao để bao phủ trách nhiệm của SUT, nhưng không kéo theo các phần không cần thiết cho mục tiêu. Ví dụ, nếu bài kiểm thử nhằm xác nhận logic xử lý callback của dịch vụ đơn hàng, việc chạy lại toàn bộ hành trình từ trang chủ có thể không tăng thêm bằng chứng tương ứng với rủi ro đó.

### 3.2. Các loại điểm bắt đầu thường gặp

| Điểm bắt đầu | Khi phù hợp | Điều cần cân nhắc |
| --- | --- | --- |
| Giao diện người dùng (UI) | Xác nhận hành trình người dùng, điều hướng, hiển thị trạng thái và tương tác thực tế | Dễ bị ảnh hưởng bởi thay đổi giao diện, tốc độ trình duyệt và dữ liệu hiển thị |
| API công khai | Xác nhận hợp đồng mà client hoặc đối tác sử dụng, xác thực, phân quyền và nghiệp vụ qua API | Không chứng minh toàn bộ hành vi giao diện hoặc khả năng sử dụng |
| Giao diện tích hợp được công bố | Xác nhận SUT giao tiếp với hệ thống khác theo hợp đồng | Cần xác định rõ provider, consumer và phạm vi trách nhiệm |
| Event hoặc message | Xác nhận xử lý bất đồng bộ từ điểm nhận message | Cần quản lý schema, correlation ID, thứ tự, retry và dữ liệu khởi tạo |
| Tác vụ theo lịch hoặc lệnh vận hành | Xác nhận batch, scheduler, import/export hoặc tác vụ nền | Cần kiểm soát thời gian, trạng thái trước và tác động lặp |
| Thiết bị hoặc client thực tế | Xác nhận luồng có phụ thuộc thiết bị, cảm biến hoặc môi trường người dùng | Cần quản lý thiết bị, phiên bản, trạng thái và khả năng tái lập |

Không có điểm bắt đầu tốt nhất cho mọi bài kiểm thử. Chọn theo đối tượng sử dụng, rủi ro, ranh giới hệ thống và bằng chứng cần thu thập.

### 3.3. Tránh chọn điểm bắt đầu quá thấp hoặc quá rộng

**Quá thấp:** gọi trực tiếp method nội bộ hoặc ghi thẳng database có thể bỏ qua xác thực, validation, routing, transaction boundary và hợp đồng mà người dùng thực sự đi qua. Cách này phù hợp cho unit hoặc component test, nhưng không đủ để tuyên bố đã xác nhận hành trình đầu cuối.

**Quá rộng:** bắt đầu từ trang chủ, đăng nhập qua nhiều nhà cung cấp, điều hướng qua nhiều chức năng rồi mới đến hành động cần kiểm tra có thể làm tăng thời gian và điểm lỗi không liên quan. Nếu mục tiêu chỉ là xác nhận thanh toán callback, phần đăng nhập và điều hướng dài có thể trở thành nguồn flaky không cần thiết.

Hãy chọn điểm vào nhỏ nhất vẫn bao phủ ranh giới và hành vi có liên quan đến mục tiêu. Khi một rủi ro cần xác nhận toàn bộ trải nghiệm, điểm bắt đầu ở UI có thể là cần thiết; khi rủi ro nằm ở một hợp đồng tích hợp, điểm bắt đầu ở API hoặc event có thể phù hợp hơn.

## 4. Xác định điều kiện ban đầu có thể tái lập

Một điểm bắt đầu chỉ có ý nghĩa khi trạng thái trước đó được xác định. Nếu dữ liệu, quyền hoặc cấu hình không rõ, cùng một hành động có thể tạo kết quả khác nhau giữa các lần chạy.

### 4.1. Các nhóm điều kiện trước

Trước khi thực thi, xác định:

- **Danh tính và quyền:** tài khoản, vai trò, tenant, phiên đăng nhập hoặc service identity.
- **Dữ liệu nghiệp vụ:** tài nguyên, trạng thái đơn hàng, số dư, khung giờ, bản ghi hoặc quan hệ dữ liệu.
- **Cấu hình:** feature flag, endpoint, locale, timezone, giới hạn và chính sách retry.
- **Môi trường:** phiên bản SUT, artifact, trình duyệt, thiết bị, database schema và dependency.
- **Thời gian:** ngày giờ hệ thống, thời hạn token, cửa sổ nghiệp vụ và lịch chạy.
- **Phụ thuộc:** sandbox, stub, provider thật hoặc trạng thái của message broker.
- **Điều kiện cô lập:** dữ liệu riêng cho lần chạy, không xung đột với test khác và có cách dọn dẹp.

Không ghi secret, token hoặc thông tin cá nhân thật vào kịch bản hay log. Sử dụng tài khoản và dữ liệu kiểm thử có quyền tối thiểu cần thiết.

### 4.2. Chuẩn bị dữ liệu mà không bỏ qua hành vi cần kiểm tra

Cách tạo dữ liệu ban đầu phải phù hợp với mục tiêu:

- Nếu kiểm tra hành trình tạo tài khoản, hãy bắt đầu từ trạng thái chưa có tài khoản và tạo tài khoản qua giao diện hoặc API được hỗ trợ.
- Nếu kiểm tra xử lý đơn hàng đã tồn tại, có thể dùng fixture hoặc API quản trị để tạo trạng thái trước, miễn là cách chuẩn bị không thay thế hành vi đang được kiểm tra.
- Nếu kiểm tra migration, cần dữ liệu ở schema phiên bản trước và thực hiện quy trình nâng cấp thực tế.
- Nếu kiểm tra consumer, hãy gửi message qua ranh giới broker hoặc adapter được công bố, thay vì gọi trực tiếp hàm xử lý nội bộ nếu mục tiêu là xác nhận nhận message.

Ghi rõ dữ liệu được tạo bằng cách nào. Nếu setup đi vòng qua một bước quan trọng, bài kiểm thử không thể dùng làm bằng chứng cho bước đó.

### 4.3. Cô lập và dọn dẹp

Kiểm thử E2E thường tạo dữ liệu có trạng thái và có thể gây tác động đến nhiều dịch vụ. Cần:

1. Dùng định danh riêng cho mỗi lần chạy hoặc mỗi worker.
2. Tránh chia sẻ tài khoản, đơn hàng, khung giờ hoặc tài nguyên có thể bị thay đổi đồng thời.
3. Đặt timeout và giới hạn số lần retry cho bước setup.
4. Dọn dữ liệu sau khi kiểm thử hoặc dùng cơ chế reset môi trường có kiểm soát.
5. Giữ bằng chứng đủ lâu để điều tra khi test thất bại.

Nếu cleanup thất bại, phải ghi nhận như một kết quả riêng. Dữ liệu sót lại có thể ảnh hưởng đến lần chạy tiếp theo và tạo lỗi khó tái hiện.

## 5. Định nghĩa kết quả cuối có thể quan sát

### 5.1. Kết quả cuối phải gắn với mục tiêu nghiệp vụ

Một kết quả cuối tốt mô tả trạng thái có ý nghĩa, không chỉ là việc một bước kỹ thuật đã chạy. Ví dụ:

| Mục tiêu | Kết quả chưa đủ | Kết quả cuối có ý nghĩa hơn |
| --- | --- | --- |
| Tạo đơn hàng | API trả HTTP 200 | Đơn có mã tham chiếu, trạng thái đúng, dữ liệu cần thiết được lưu và có thể tra cứu |
| Thanh toán | Provider trả accepted | Giao dịch được đối soát theo quy tắc và đơn chuyển sang trạng thái phù hợp |
| Gửi thông báo | Worker đã gọi provider | Thông báo có trạng thái gửi/nhận theo khả năng quan sát và hợp đồng đã xác định |
| Đặt lịch | Màn hình hiển thị “Thành công” | Lịch được tạo đúng một lần, khung giờ được giữ và người dùng tra cứu được lịch |
| Hủy đăng ký | Nút hủy đã được nhấn | Đăng ký ở trạng thái đã hủy, quyền truy cập liên quan được cập nhật và không phát sinh tác dụng phụ sai |

HTTP 2xx hoặc thông báo UI có thể là một phần của bằng chứng, nhưng không tự động chứng minh tác vụ nghiệp vụ đã hoàn tất.

### 5.2. Các nguồn quan sát kết quả

Kết quả cuối có thể được quan sát qua một hoặc nhiều nguồn:

- **UI:** trạng thái hiển thị, mã tham chiếu, thông báo và khả năng thực hiện bước tiếp theo.
- **API:** response body, status code, resource state và header định danh.
- **Dữ liệu nghiệp vụ:** bản ghi hoặc bất biến được phép kiểm tra qua giao diện hỗ trợ kiểm thử.
- **Event/message:** sự kiện đã phát, đã xử lý hoặc được đưa vào dead-letter theo quy tắc.
- **Hệ thống ngoài:** xác nhận từ sandbox hoặc API đối soát của provider.
- **Telemetry:** log, metric, trace, audit event và correlation ID.

Chọn nguồn quan sát theo ranh giới của mục tiêu. Nếu kiểm thử hành vi mà người dùng nhìn thấy, UI hoặc API công khai nên là nguồn chính; dữ liệu nội bộ có thể bổ sung bằng chứng khi cần xác nhận tính nhất quán. Nếu kiểm thử một hợp đồng tích hợp, response hoặc event tại ranh giới có thể là oracle chính.

### 5.3. Tránh phụ thuộc vào chi tiết triển khai không ổn định

Một bài E2E có thể trở nên mong manh nếu kiểm tra quá nhiều chi tiết nội bộ như tên bảng, thứ tự truy vấn, tên thread hoặc cấu trúc log không phải hợp đồng. Hãy ưu tiên các trạng thái và kết quả được cam kết bởi sản phẩm.

Có thể kiểm tra database hoặc log khi chúng là nguồn bằng chứng phù hợp và được phép, nhưng cần tách biệt:

- **Assertion nghiệp vụ:** sản phẩm tạo đúng kết quả.
- **Assertion kỹ thuật:** một dịch vụ gọi đúng endpoint, ghi đúng event hoặc tuân thủ cấu trúc nội bộ.

Assertion kỹ thuật rất hữu ích trong test thành phần và tích hợp. Trong E2E, chỉ giữ những kiểm tra nội bộ cần thiết để chứng minh rủi ro mà các giao diện công khai không thể quan sát.

## 6. Xử lý kết quả bất đồng bộ và eventual consistency

Nhiều hành trình hệ thống không hoàn tất ngay trong request ban đầu. API có thể trả về accepted hoặc pending, sau đó queue consumer, scheduler hoặc callback mới cập nhật trạng thái cuối.

### 6.1. Phân biệt phản hồi tiếp nhận và hoàn tất nghiệp vụ

Ví dụ, một API tạo đơn có thể trả về mã đơn và trạng thái pending. Điều này chứng minh yêu cầu đã được tiếp nhận theo hợp đồng, nhưng chưa chứng minh thanh toán đã thành công hoặc đơn đã được xác nhận.

Kịch bản cần tách:

1. Kết quả đồng bộ: request được chấp nhận hoặc bị từ chối.
2. Trạng thái trung gian: đơn đang chờ xử lý, thanh toán đang pending.
3. Kết quả cuối: đơn đã xác nhận, thanh toán thất bại hoặc quy trình đã được hủy theo quy tắc.

Không đặt assertion cuối cùng ngay sau phản hồi đầu tiên nếu hệ thống được thiết kế để xử lý bất đồng bộ.

### 6.2. Chờ theo điều kiện, không chờ bằng khoảng ngủ cố định

Một khoảng sleep cố định có thể quá ngắn khi hệ thống chậm và lãng phí thời gian khi hệ thống nhanh. Thay vào đó, hãy polling một điều kiện quan sát được với timeout tổng thể:

~~~text
deadline = thời điểm bắt đầu + timeout đã định nghĩa

while thời điểm hiện tại < deadline:
    đọc trạng thái qua giao diện quan sát phù hợp
    nếu trạng thái đạt kết quả mong đợi:
        PASS
    nếu trạng thái chuyển sang lỗi cuối:
        FAIL với bằng chứng trạng thái
    đợi một khoảng polling ngắn có giới hạn

FAIL vì hết thời hạn chờ, kèm trạng thái cuối và trace
~~~

Khoảng polling nên được kiểm soát để không tạo tải đáng kể. Timeout cần dựa trên cam kết hoặc đặc tính của hành trình, không tùy tiện chọn để test dễ pass.

### 6.3. Xác định trạng thái cuối và trạng thái không mong muốn

Một monitor cho E2E nên biết:

- Trạng thái nào là thành công.
- Trạng thái nào là thất bại cuối.
- Trạng thái nào là trung gian và có thể tiếp tục chờ.
- Thời hạn tối đa cho phép ở trạng thái trung gian.
- Có thể hủy hoặc bù trừ giao dịch hay không.
- Cách xác định một kết quả bị trùng hoặc mâu thuẫn.

Ví dụ, đơn hàng có thể ở các trạng thái CREATED, PAYMENT_PENDING, CONFIRMED, PAYMENT_FAILED hoặc CANCELLED. Kịch bản cần xác định chuyển trạng thái hợp lệ và không được xem PAYMENT_PENDING là hoàn tất.

~~~mermaid
stateDiagram-v2
    [*] --> CREATED
    CREATED --> PAYMENT_PENDING
    PAYMENT_PENDING --> CONFIRMED: Thanh toán được xác nhận
    PAYMENT_PENDING --> PAYMENT_FAILED: Thanh toán thất bại cuối
    PAYMENT_PENDING --> CANCELLED: Hết hạn hoặc hủy theo quy tắc
    CONFIRMED --> [*]
    PAYMENT_FAILED --> [*]
    CANCELLED --> [*]
~~~

Sơ đồ chỉ minh họa. Trạng thái và chuyển tiếp thực tế phải lấy từ quy tắc nghiệp vụ của sản phẩm.

## 7. Thiết kế oracle cho kết quả cuối

Oracle là căn cứ để xác định kết quả quan sát được có đúng hay không. Với một hành trình E2E, có thể cần nhiều oracle ở các ranh giới khác nhau.

### 7.1. Oracle đơn và oracle kết hợp

Một oracle đơn có thể là trạng thái tài nguyên hoặc phản hồi API. Oracle kết hợp có thể yêu cầu đồng thời:

- Người dùng nhận được mã tham chiếu.
- Tài nguyên có trạng thái cuối đúng.
- Giao dịch liên quan được liên kết đúng.
- Không có bản ghi trùng.
- Event cần thiết đã được xử lý.
- Người dùng có thể tra cứu hoặc tiếp tục hành động theo quy tắc.

Không nên thêm assertion không liên quan chỉ để tăng số lượng kiểm tra. Mỗi assertion cần hỗ trợ một yêu cầu hoặc rủi ro cụ thể.

### 7.2. Dùng bất biến nghiệp vụ

Bất biến mô tả điều phải luôn đúng sau khi hành trình hoàn tất. Ví dụ:

- Một mã giao dịch chỉ được ghi nhận thanh toán một lần.
- Một tài nguyên không được xác nhận cho hai lịch trùng nhau.
- Tổng các khoản phân bổ không vượt quá số lượng khả dụng.
- Người dùng không thể đọc tài nguyên ngoài phạm vi quyền.
- Một đơn đã hủy không thể quay lại trạng thái đã thanh toán nếu không có quy trình khôi phục được định nghĩa.

Bất biến thường bền vững hơn assertion vào chi tiết giao diện, nhưng cần được diễn đạt chính xác theo chính sách sản phẩm.

### 7.3. Kiểm tra cả tác dụng phụ

Một hành động có thể tạo nhiều tác dụng phụ: gửi email, phát event, cập nhật tồn kho hoặc ghi nhận audit. Hãy xác định tác dụng phụ nào là bắt buộc của hành trình và tác dụng nào không được xảy ra.

Ví dụ, hủy đơn có thể cần giải phóng tồn kho và phát event hủy. Nếu chỉ kiểm tra trạng thái đơn, bài test có thể bỏ sót việc tồn kho chưa được hoàn lại. Ngược lại, nếu email là best-effort và không phải điều kiện chặn nghiệp vụ, không nên bắt E2E chờ email đến hộp thư thật trong mọi lần chạy.

## 8. Ví dụ hoàn chỉnh: chọn điểm vào và điểm kết thúc cho hành trình đặt hàng

### 8.1. Mục tiêu

Xác nhận khách hàng có thể đặt một sản phẩm còn hàng, thanh toán thành công và tra cứu được đơn đã xác nhận.

### 8.2. Điểm bắt đầu

Vì mục tiêu bao gồm trải nghiệm mua hàng, điểm bắt đầu phù hợp là trang sản phẩm hoặc giỏ hàng trong ứng dụng web, với một tài khoản kiểm thử đã đăng nhập. Nếu mục tiêu chỉ là xác nhận API tạo đơn, có thể dùng API công khai làm điểm vào trong một kịch bản riêng.

### 8.3. Điều kiện trước

- Tài khoản kiểm thử có quyền mua hàng.
- Sản phẩm còn đủ tồn kho và có giá đã biết.
- Giỏ hàng không chứa dữ liệu từ lần chạy trước.
- Cổng thanh toán đang ở sandbox với kịch bản chấp nhận giao dịch.
- Phiên bản ứng dụng, cấu hình và dữ liệu được ghi nhận.
- Mỗi lần chạy có mã tham chiếu riêng để truy vết.

### 8.4. Hành động và kết quả cuối

| Giai đoạn | Hành động | Điều quan sát |
| --- | --- | --- |
| Điểm vào | Mở trang sản phẩm và thêm vào giỏ | Sản phẩm và số lượng hiển thị đúng |
| Tạo đơn | Xác nhận thông tin giao hàng và đặt hàng | Có mã đơn, trạng thái ban đầu đúng |
| Thanh toán | Chọn phương thức sandbox và xác nhận | Giao dịch có mã tham chiếu và kết quả theo kịch bản |
| Xử lý bất đồng bộ | Chờ callback/event được xử lý | Đơn chuyển sang CONFIRMED trong thời hạn |
| Kết quả cuối | Mở trang chi tiết đơn | Người dùng thấy đơn đã xác nhận, số tiền và sản phẩm đúng |
| Kiểm tra bổ sung | Đối chiếu trạng thái giao dịch và tồn kho | Giao dịch không trùng, tồn kho thay đổi đúng theo quy tắc |

### 8.5. Kịch bản minh họa

~~~gherkin
Feature: Hoàn tất đơn hàng

  Scenario: Khách hàng thanh toán thành công
    Given khách hàng đã đăng nhập
      And sản phẩm còn đủ tồn kho
      And cổng thanh toán sandbox chấp nhận giao dịch
    When khách hàng thêm sản phẩm vào giỏ
      And xác nhận đặt hàng
      And hoàn tất thanh toán
    Then hệ thống tạo một đơn hàng có mã tham chiếu duy nhất
      And đơn hàng chuyển sang trạng thái CONFIRMED
      And giao dịch thanh toán được liên kết đúng với đơn hàng
      And khách hàng có thể tra cứu chi tiết đơn hàng
      And tồn kho được cập nhật theo quy tắc bán hàng
~~~

### 8.6. Giới hạn kết luận

Kịch bản này xác nhận một đường đi thành công với một loại tài khoản, một cấu hình sandbox và một loại sản phẩm. Nó chưa chứng minh:

- Thanh toán bị từ chối hoặc timeout được xử lý đúng.
- Callback lặp không tạo giao dịch trùng.
- Nhiều người mua đồng thời không làm tồn kho âm.
- Mọi phương thức giao hàng hoặc vai trò đều hoạt động.
- Hiệu năng đáp ứng tải cao.

Các rủi ro đó cần kịch bản riêng hoặc kiểm thử ở tầng phù hợp. Nêu rõ giới hạn giúp báo cáo không suy rộng kết quả của một hành trình thành công thành kết luận cho toàn bộ sản phẩm.

## 9. Ví dụ: E2E cho xử lý event bất đồng bộ

Không phải E2E nào cũng bắt đầu ở UI. Giả sử mục tiêu là xác nhận dịch vụ thông báo xử lý event đơn hàng đã xác nhận.

**Điểm bắt đầu:** gửi event hợp lệ qua topic hoặc endpoint tích hợp được hỗ trợ, với event ID và correlation ID riêng.

**Điều kiện trước:** consumer đang hoạt động, schema event hợp lệ, môi trường gửi thông báo là sandbox và người nhận là địa chỉ kiểm thử.

**Kết quả cuối:** event được xử lý theo quy tắc, trạng thái gửi được ghi nhận và không có thông báo trùng cho cùng event ID.

Kịch bản nên xác nhận:

1. Event hợp lệ được tiếp nhận.
2. Consumer xử lý và tạo yêu cầu gửi thông báo.
3. Provider sandbox trả kết quả phù hợp.
4. Trạng thái xử lý được cập nhật và có thể tra cứu.
5. Gửi lại cùng event không tạo tác dụng phụ ngoài quy tắc idempotency.
6. Nếu provider lỗi tạm thời, retry và dead-letter hoạt động theo chính sách.

Ở đây, điểm bắt đầu là ranh giới message chứ không phải màn hình đặt hàng. Điều này phù hợp vì bài test nhắm vào hợp đồng và hành vi của consumer. Một bài E2E cấp sản phẩm khác có thể bắt đầu từ UI và theo dõi toàn bộ đường đi tới thông báo.

## 10. Chẩn đoán lỗi và giảm flaky test

### 10.1. Khi bài kiểm thử thất bại

Khi không đạt kết quả cuối, cần phân loại:

- Hành động đầu vào không được tiếp nhận.
- Điều kiện ban đầu không đúng hoặc dữ liệu setup bị lỗi.
- SUT xử lý sai quy tắc nghiệp vụ.
- Phụ thuộc ngoài không sẵn sàng hoặc trả kết quả khác dự kiến.
- Tác vụ bất đồng bộ chưa hoàn tất trong thời hạn.
- Oracle hoặc cách quan sát bị sai.
- Cleanup hoặc dữ liệu dùng chung ảnh hưởng kết quả.

Thu thập ảnh chụp UI khi phù hợp, request/response đã làm sạch dữ liệu, trạng thái tài nguyên, log, trace, correlation ID và thời điểm. Bằng chứng cần đủ để xác định lỗi ở điểm vào, trong quá trình xử lý hay ở điều kiện kết thúc.

### 10.2. Các nguyên nhân phổ biến của flaky test

| Nguyên nhân | Biểu hiện | Cách giảm |
| --- | --- | --- |
| Chờ bằng sleep cố định | Lúc pass lúc timeout | Chờ điều kiện với deadline |
| Dữ liệu dùng chung | Test chạy riêng pass nhưng chạy song song thất bại | Cách ly dữ liệu và định danh theo lần chạy |
| Phụ thuộc sandbox không ổn định | Provider trả lỗi ngẫu nhiên | Stub cho kiểm thử xác định; giữ một tập sandbox test có kiểm soát |
| Oracle kiểm tra quá sớm | Response đầu tiên pass nhưng trạng thái cuối chưa hoàn tất | Xác định rõ trạng thái trung gian và kết quả cuối |
| Chọn locator UI mong manh | Test hỏng khi bố cục thay đổi | Dùng locator theo vai trò/nhãn ổn định và kiểm tra hành vi người dùng |
| Cleanup không hoàn tất | Lần chạy sau bị ảnh hưởng | Dùng cleanup có thể lặp, theo dõi dữ liệu sót và reset có kiểm soát |
| Đồng hồ hoặc timezone khác nhau | Kết quả sai ở ranh giới ngày/giờ | Kiểm soát clock, timezone và dữ liệu thời gian |

Không nên tự động retry mọi lần thất bại đến khi pass mà không lưu lần thất bại đầu tiên. Retry có thể giúp phân biệt lỗi tạm thời, nhưng cũng có thể che giấu vấn đề đồng thời hoặc phụ thuộc không ổn định.

### 10.3. Giữ bài E2E tập trung

Một bài E2E nên có mục tiêu rõ và số điểm kiểm tra vừa đủ để chứng minh mục tiêu đó. Nếu một kịch bản chứa quá nhiều hành trình độc lập, khi thất bại sẽ khó biết phần nào gây lỗi và việc chạy lại tốn kém.

Có thể chia thành:

- E2E cho hành trình người dùng quan trọng.
- E2E cho từng hợp đồng hoặc luồng tích hợp có rủi ro.
- Kiểm thử thành phần cho logic nội bộ và các trường hợp biên rộng.
- Kiểm thử phi chức năng riêng cho tải, phục hồi hoặc bảo mật.

Chia nhỏ theo mục tiêu giúp giữ tín hiệu rõ ràng và vẫn duy trì một số hành trình đầu cuối đại diện.

## 11. Mẫu thiết kế kịch bản E2E

Có thể dùng mẫu sau khi thiết kế một kịch bản:

~~~text
ID / tên kịch bản:
Mục tiêu nghiệp vụ hoặc rủi ro:
Phạm vi SUT:

Tác nhân:
Điểm bắt đầu / entry point:
Lý do chọn điểm bắt đầu:

Điều kiện trước:
- Danh tính và quyền:
- Dữ liệu ban đầu:
- Cấu hình và môi trường:
- Trạng thái phụ thuộc:

Hành động chính:
Các bước hoặc sự kiện quan trọng:

Kết quả cuối mong đợi:
Trạng thái trung gian được phép:
Trạng thái lỗi cuối:
Thời hạn chờ:

Oracle:
Nguồn quan sát:
Bằng chứng cần lưu:
Correlation ID / mã tham chiếu:

Cleanup:
Giới hạn kết luận:
Rủi ro chưa được bao phủ:
~~~

Mẫu này buộc người thiết kế xác định cả điểm vào và điểm kết thúc trước khi viết automation. Nếu một mục không thể điền vì chưa có quyết định nghiệp vụ, hãy ghi câu hỏi và chủ sở hữu thay vì tự giả định.

## 12. Checklist lựa chọn điểm bắt đầu và kết quả cuối

- [ ] Mục tiêu E2E mô tả kết quả nghiệp vụ cần xác nhận.
- [ ] Điểm bắt đầu nằm ở ranh giới phù hợp với mục tiêu và phạm vi SUT.
- [ ] Lý do chọn UI, API, event, scheduler hoặc giao diện tích hợp đã rõ.
- [ ] Điểm bắt đầu không bỏ qua hành vi cần kiểm tra và không kéo theo phạm vi thừa.
- [ ] Điều kiện ban đầu về danh tính, quyền, dữ liệu, cấu hình và phụ thuộc được xác định.
- [ ] Dữ liệu setup không thay thế bước đang được xác nhận.
- [ ] Dữ liệu được cô lập theo lần chạy và có cách cleanup.
- [ ] Kết quả cuối là trạng thái hoặc tác động nghiệp vụ có thể quan sát.
- [ ] Phân biệt rõ phản hồi tiếp nhận, trạng thái trung gian và hoàn tất nghiệp vụ.
- [ ] Với luồng bất đồng bộ, có điều kiện chờ và timeout tổng thể.
- [ ] Oracle kiểm tra cả kết quả chính và tác dụng phụ quan trọng.
- [ ] Bằng chứng gắn với phiên bản, môi trường, dữ liệu và correlation ID.
- [ ] Kịch bản nêu rõ giới hạn kết luận và rủi ro chưa được bao phủ.
- [ ] Khi thất bại, có đủ log, trace và trạng thái để chẩn đoán.

Lựa chọn điểm bắt đầu và kết quả kết thúc có thể quan sát giúp bài kiểm thử hệ thống/E2E chứng minh đúng hành trình mà nó được thiết kế để xác nhận. Khi điểm vào phản ánh đúng ranh giới, điều kiện trước có thể tái lập và oracle kiểm tra trạng thái nghiệp vụ cuối, kết quả kiểm thử sẽ đáng tin cậy hơn và hữu ích hơn cho quyết định chất lượng.
