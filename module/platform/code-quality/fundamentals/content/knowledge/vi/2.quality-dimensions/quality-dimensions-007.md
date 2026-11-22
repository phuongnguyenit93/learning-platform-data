# An toàn bảo mật và kiểm soát dữ liệu nhạy cảm

> **Chương:** Các chiều chất lượng  
> **Học phần:** Code Quality Fundamentals (`CODE_QUALITY_FUNDAMENTALS`) — hiểu những thuộc tính quyết định mã nguồn có đáng tin cậy, dễ hiểu và dễ thay đổi hay không.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích vì sao **an toàn bảo mật (security)** là một chiều của chất lượng mã nguồn, kể cả khi phần mềm đang đáp ứng đúng yêu cầu chức năng.
2. Nhận diện tài sản, ranh giới tin cậy, đường đi của dữ liệu và những nơi thông tin nhạy cảm có thể bị lộ hoặc sửa trái phép.
3. Phân biệt **xác thực**, **phân quyền**, **kiểm tra đầu vào**, **bảo vệ dữ liệu khi truyền/lưu trữ**, **quản lý bí mật** và **ghi nhận sự kiện an toàn**.
4. Thiết kế một luồng truy cập dữ liệu theo nguyên tắc quyền tối thiểu, chỉ trả về dữ liệu cần thiết và từ chối truy cập khi không thể xác định quyền.
5. Đưa các yêu cầu bảo mật vào code review và kiểm thử bằng tình huống có thể xác minh.

## 1. Vì sao bảo mật là chất lượng mã nguồn?

Một chức năng “xem đơn hàng” có thể hoạt động đúng đối với người dùng hợp lệ nhưng vẫn kém chất lượng nếu thay mã đơn hàng trong URL là xem được đơn của người khác. Tương tự, một API có thể phản hồi nhanh nhưng lại ghi mật khẩu, token truy cập hoặc địa chỉ khách hàng vào log. Những lỗi này không nhất thiết làm ứng dụng sập, nhưng phá vỡ niềm tin và có thể gây thiệt hại nghiêm trọng.

Trong chất lượng phần mềm, bảo mật quan tâm đến khả năng hệ thống bảo vệ tài sản trước các truy cập và hành động không được phép. Ba mục tiêu cơ bản thường được dùng để phân tích là:

| Mục tiêu | Ý nghĩa | Ví dụ trong ứng dụng |
| --- | --- | --- |
| **Bí mật (Confidentiality)** | Chỉ người hoặc hệ thống được phép mới xem được dữ liệu | Người mua chỉ xem thông tin đơn hàng thuộc quyền truy cập của mình |
| **Toàn vẹn (Integrity)** | Dữ liệu, quy tắc và thao tác không bị sửa trái phép | Khách hàng không thể tự chỉnh giá hoặc trạng thái thanh toán |
| **Sẵn sàng (Availability)** | Dịch vụ và dữ liệu có thể phục vụ đúng nhu cầu hợp lệ | Truy vấn được giới hạn tài nguyên để tránh làm quá tải hệ thống |

Bảo mật còn đòi hỏi **xác thực danh tính**, **phân quyền hành động** và **khả năng truy vết** khi có sự cố. Không có biện pháp đơn lẻ nào bảo đảm toàn bộ các mục tiêu trên. Mã nguồn đáng tin cậy cần kiểm soát an toàn ở nhiều lớp và thể hiện được các giả định của mình.

### Bảo mật khác gì với kiểm tra tính đúng chức năng?

- **Đúng chức năng:** Người dùng A bấm “Xem đơn hàng” và nhận đúng đơn của A.
- **Đúng về phân quyền:** Người dùng A thử truy cập đơn của B và không nhận được dữ liệu của B.
- **Đúng về dữ liệu nhạy cảm:** Dù A có quyền xem đơn, phản hồi chỉ chứa những trường cần cho màn hình, không tự động lộ thông tin nội bộ.
- **Đúng khi lỗi xảy ra:** Khi kiểm tra quyền hoặc dịch vụ bên ngoài gặp trục trặc, hệ thống không mặc nhiên cấp thêm quyền hay ghi thông tin bí mật ra thông báo lỗi.

Vì vậy, không thể kết luận “đã an toàn” chỉ từ việc các trường hợp thành công chạy đúng. Cần chủ động kiểm tra cả trường hợp sử dụng sai, dữ liệu bất thường và tác nhân không được phép.

## 2. Dữ liệu nào cần được bảo vệ?

**Dữ liệu nhạy cảm** là dữ liệu mà việc truy cập, sử dụng, tiết lộ, sửa đổi hoặc mất mát không phù hợp có thể gây hại cho cá nhân, tổ chức hoặc hệ thống. Mức nhạy cảm phụ thuộc ngữ cảnh, mục đích sử dụng, chính sách nội bộ và quy định áp dụng; không thể suy ra chỉ từ tên cột.

| Nhóm dữ liệu | Ví dụ | Kiểm soát thường cần |
| --- | --- | --- |
| Dữ liệu cá nhân | Họ tên gắn với địa chỉ, số điện thoại, email, định danh người dùng | Giới hạn mục đích sử dụng, quyền xem, lượng dữ liệu trả về, thời gian lưu giữ |
| Dữ liệu tài chính/giao dịch | Lịch sử thanh toán, thông tin hóa đơn, dữ liệu phương thức thanh toán | Hạn chế truy cập, giảm dữ liệu thu thập, áp dụng chuẩn và chính sách phù hợp |
| Dữ liệu đặc biệt nhạy cảm theo bối cảnh | Hồ sơ sức khỏe, thông tin định danh có rủi ro cao, dữ liệu nhân sự | Phân quyền chặt, ghi nhận truy cập thích hợp, chính sách lưu giữ và xử lý riêng |
| **Bí mật kỹ thuật (secrets)** | Mật khẩu, khóa API, khóa ký, private key, token truy cập, chuỗi kết nối có thông tin xác thực | Không đưa vào mã nguồn/log; quản lý bằng cơ chế bí mật, giới hạn quyền và xoay vòng |
| Dữ liệu nội bộ của tổ chức | Báo giá chưa công bố, hợp đồng, báo cáo nội bộ, sơ đồ hệ thống | Phân loại, giới hạn chia sẻ, phân quyền theo vai trò và nhu cầu sử dụng |

**Dữ liệu cá nhân** và **bí mật kỹ thuật** có tính chất khác nhau. Email của khách hàng có thể cần xuất hiện ở một số giao diện đã được cấp quyền; token truy cập hoặc khóa bí mật thường không có lý do xuất hiện trong phản hồi ứng dụng. Không nên xem mọi chuỗi ký tự là an toàn chỉ vì nó không giống mật khẩu: mã đơn hàng, mã người dùng hoặc ID phiên có thể trở thành dữ liệu nhạy cảm khi liên kết được với một cá nhân hay phiên làm việc.

Việc mã hóa hoặc che bớt vài ký tự không thay thế được kiểm soát truy cập và giới hạn mục đích sử dụng. Dữ liệu đã được giải mã trong bộ nhớ vẫn cần bảo vệ khi đưa ra API, log, file xuất hoặc công cụ hỗ trợ.

## 3. Theo dõi dữ liệu qua toàn bộ vòng đời

Bảo vệ dữ liệu cần diễn ra từ lúc nhận đến khi hết nhu cầu lưu trữ:

~~~text
Người dùng / đối tác
        |
        v
Thu thập -> Kiểm tra -> Xử lý -> Lưu trữ
               |           |         |
               |           v         v
               |       API / UI   Sao lưu
               |           |         |
               +------> Log / trace / báo lỗi
                           |
                           v
                 Chia sẻ / Xuất dữ liệu
                           |
                           v
                  Hết hạn / Xóa / Hủy
~~~

Sơ đồ nhắc rằng **log, bản sao lưu, công cụ phân tích và file xuất** cũng là nơi tồn tại dữ liệu. Chỉ kiểm tra database chính chưa đủ.

| Giai đoạn | Câu hỏi cần trả lời |
| --- | --- |
| Thu thập | Có thật sự cần trường này? Người dùng có biết mục đích sử dụng theo chính sách áp dụng? |
| Tiếp nhận/kiểm tra | Dữ liệu đến từ nguồn nào, có hợp lệ và có thể bị thao túng không? |
| Xử lý | Danh tính nào đang hành động? Có được phép với bản ghi và thao tác cụ thể không? |
| Truyền | Kết nối có được bảo vệ và xác minh đúng điểm cuối không? |
| Lưu trữ | Ai có thể đọc/sửa? Dữ liệu và khóa bảo vệ được quản lý ra sao? |
| Trả về/ghi log | Có trường thừa nào bị đưa ra ngoài? Thông báo lỗi có lộ chi tiết nội bộ? |
| Chia sẻ/xuất | Đích nhận có quyền và nhu cầu hợp lệ? Dữ liệu xuất có cần toàn bộ trường? |
| Hết hạn/xóa | Có chính sách thời hạn, thao tác xóa và xử lý bản sao lưu/ngoại lệ lưu giữ không? |

Một nguyên tắc hữu ích là **giảm thiểu dữ liệu (data minimization)**: chỉ thu thập, xử lý, trả về và giữ lại lượng dữ liệu cần thiết cho mục đích đã xác định. Dữ liệu không tồn tại ở một vị trí thì không thể rò rỉ từ vị trí đó.

## 4. Ranh giới tin cậy và mô hình đe dọa

**Ranh giới tin cậy (trust boundary)** là nơi dữ liệu hoặc yêu cầu chuyển từ vùng có mức tin cậy này sang vùng khác: trình duyệt đến API, API đến database, dịch vụ nội bộ đến hệ thống bên thứ ba. Mọi giá trị được gửi từ phía client cần được coi là **có thể bị thay đổi**, ngay cả khi giao diện đã ẩn nút hoặc kiểm tra dữ liệu bằng JavaScript.

Với chức năng lấy chi tiết đơn hàng, hãy đặt câu hỏi theo một mô hình đe dọa đơn giản:

1. **Tài sản:** Những gì cần giữ bí mật/toàn vẹn? Ví dụ đơn hàng, địa chỉ giao hàng, trạng thái thanh toán.
2. **Tác nhân:** Ai tham gia? Chủ đơn, nhân viên hỗ trợ, dịch vụ thanh toán, người không đăng nhập.
3. **Điểm vào:** URL chứa mã đơn, tham số tìm kiếm, body JSON, header, hàng đợi sự kiện.
4. **Khả năng lạm dụng:** Đổi mã đơn của người khác, gửi dữ liệu sai kiểu, giả mạo trường `ownerId`, gọi API quá mức.
5. **Biện pháp:** Xác thực từ phiên/credential đáng tin, kiểm tra quyền theo bản ghi, giới hạn dữ liệu đầu ra, giới hạn tần suất phù hợp, ghi nhận sự kiện.
6. **Xác minh:** Viết kiểm thử với tài khoản không có quyền và quan sát kết quả khi một phụ thuộc lỗi.

Một sơ đồ định hướng đặt kiểm soát ở đúng nơi:

~~~mermaid
flowchart LR
    C["Ứng dụng khách"] --> A["API: xác thực và xác minh đầu vào"]
    A --> S["Service: kiểm tra quyền hành động"]
    S --> R["Repository: ràng buộc dữ liệu theo chủ sở hữu"]
    R --> D[("Cơ sở dữ liệu")]
    S --> O["DTO: chỉ trường được phép công bố"]
    O --> C
    S -. "Sự kiện không chứa bí mật" .-> L["Log / giám sát"]
~~~

Đây là sơ đồ khái niệm; cách phân chia lớp có thể thay đổi theo kiến trúc. Điều cốt lõi là **quyền được kiểm tra ở phía máy chủ**, gắn với danh tính và tài nguyên cụ thể, không phụ thuộc vào việc client có hiển thị nút hay không.

## 5. Xác thực, phân quyền và nguyên tắc quyền tối thiểu

Hai khái niệm thường bị nhầm:

- **Authentication (xác thực):** “Yêu cầu này đại diện cho ai?” Ví dụ kiểm tra phiên đăng nhập hoặc access token hợp lệ.
- **Authorization (phân quyền):** “Danh tính đã xác thực có được làm việc này với tài nguyên này không?” Ví dụ khách hàng có được xem **đơn số 42** hay không.

Đăng nhập thành công chưa có nghĩa là được xem mọi đơn hàng. Chỉ kiểm tra một vai trò chung như `USER` cũng chưa đủ nếu quyền phụ thuộc vào **chủ sở hữu, tổ chức/tenant, trạng thái đơn** hoặc nhiệm vụ được giao.

Các nguyên tắc khi thiết kế:

- **Deny by default:** Nếu không xác định được quyền thì từ chối. Lỗi dịch vụ kiểm tra quyền không được trở thành “cho phép”.
- **Least privilege:** Mỗi người dùng, dịch vụ và tài khoản database chỉ có quyền cần cho công việc.
- **Kiểm tra trên từng tài nguyên:** Quyền với nhóm bản ghi không tự suy ra quyền với bản ghi bất kỳ.
- **Không tin thuộc tính định danh từ client:** Client có thể gửi `userId` hoặc `role` tùy ý; danh tính dùng để xét quyền phải lấy từ ngữ cảnh xác thực đã được máy chủ xác minh.
- **Bảo vệ thao tác ghi:** Kiểm tra cả xem, sửa, xóa, duyệt và xuất dữ liệu; nhiều hệ thống kiểm soát GET nhưng bỏ sót PATCH/DELETE.

### Ví dụ Java: truy vấn đơn hàng theo đúng người sở hữu

Giả sử một hệ thống Java lưu đơn hàng có `id`, `owner_id`, `total_vnd`, `status`, `shipping_address`. Màn hình “Tóm tắt đơn hàng” chỉ cần ID, số tiền và trạng thái.

**Thiết kế rủi ro:**

~~~java
// Không đủ an toàn: ai biết orderId cũng có thể lấy được đơn.
Order findOrder(long orderId) {
    return repository.findById(orderId)
            .orElseThrow();
}
~~~

Nếu controller trả nguyên đối tượng `Order`, phản hồi có thể còn chứa địa chỉ giao hàng và các trường nội bộ mà giao diện không cần.

**Thiết kế có giới hạn quyền và dữ liệu:**

~~~java
record OrderSummary(long id, long totalVnd, String status) {}

OrderSummary readOwnOrder(
        Connection connection,
        long orderId,
        String authenticatedUserId
) throws SQLException {

    if (authenticatedUserId == null || authenticatedUserId.isBlank()) {
        throw new SecurityException("Authentication required");
    }

    String sql = """
            SELECT id, total_vnd, status
            FROM orders
            WHERE id = ? AND owner_id = ?
            """;

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setLong(1, orderId);
        statement.setString(2, authenticatedUserId);

        try (ResultSet result = statement.executeQuery()) {
            if (!result.next()) {
                throw new NoSuchElementException("Order not found");
            }
            return new OrderSummary(
                    result.getLong("id"),
                    result.getLong("total_vnd"),
                    result.getString("status")
            );
        }
    }
}
~~~

Ở ví dụ này:

1. `authenticatedUserId` **phải được cấp bởi lớp xác thực máy chủ**, không lấy trực tiếp từ query parameter, request body hoặc header tùy ý.
2. Điều kiện `owner_id = ?` ràng buộc kết quả với người sở hữu. Hệ thống nhiều tenant hoặc có nhân viên hỗ trợ cần mô hình phân quyền tương ứng, không thể mặc định mọi người chỉ được xem đơn của mình.
3. `PreparedStatement` truyền dữ liệu qua tham số thay vì ghép chuỗi SQL, giảm nguy cơ SQL injection ở vị trí giá trị. Nếu tên bảng/cột buộc phải chọn động, cần danh sách cho phép (allowlist); dấu `?` không thay thế được tên đối tượng SQL.
4. DTO `OrderSummary` chỉ chứa ba trường cần hiển thị; việc dùng DTO giúp hạn chế vô tình trả cả dữ liệu nhạy cảm.
5. Không tìm thấy đơn hoặc không có quyền sở hữu cùng dẫn đến “Order not found”, giúp tránh tiết lộ sự tồn tại của đơn qua thông điệp. Việc ánh xạ exception sang HTTP 404/401 và cách ghi audit cần nhất quán theo hợp đồng API.

Đây là đoạn minh họa lớp truy cập dữ liệu với Java text block (Java 15+). Ứng dụng thực tế còn cần cấu hình xác thực, xử lý lỗi, quản lý kết nối, timeout và chính sách phân quyền tổng thể.

## 6. Các lớp phòng vệ quan trọng khác

### 6.1. Kiểm tra đầu vào và mã hóa đầu ra

Dữ liệu từ URL, biểu mẫu, header, tệp tải lên hoặc phản hồi từ dịch vụ ngoài đều có thể chứa giá trị không mong đợi.

- Kiểm tra **kiểu, kích thước, phạm vi, định dạng và quan hệ giữa các trường** theo quy tắc nghiệp vụ.
- Dùng API truy vấn có tham số hoặc ORM đúng cách; tránh ghép dữ liệu người dùng thành câu lệnh SQL.
- Khi hiển thị nội dung vào HTML, JavaScript hoặc URL, sử dụng **escaping/encoding phù hợp với ngữ cảnh đầu ra**; chỉ kiểm tra đầu vào không đủ để ngăn XSS.
- Giới hạn kích thước yêu cầu và số lượng thao tác khi cần để bảo vệ tài nguyên.
- Không tự tạo “bộ lọc ký tự nguy hiểm” thay thế cho cơ chế xử lý đúng của framework và truy vấn tham số.

### 6.2. Bí mật kỹ thuật và thông tin xác thực

Khóa API, private key và mật khẩu không được nhúng vào source code, file cấu hình đưa vào repository, test fixture công khai hoặc log. Hãy dùng cơ chế quản lý bí mật được tổ chức phê duyệt, cấp quyền theo phạm vi nhỏ, phân tách môi trường và có quy trình **thu hồi/luân chuyển (rotation)**.

**Biến môi trường** có thể là một phương thức truyền cấu hình tới ứng dụng, nhưng bản thân nó không tự bảo đảm an toàn: giá trị vẫn có thể bị lộ qua công cụ chẩn đoán, cấu hình triển khai hoặc quyền truy cập tiến trình. Cần kiểm soát cả nơi tạo, phân phối và sử dụng bí mật.

- Không lưu mật khẩu người dùng dưới dạng văn bản thuần hoặc mã hóa có thể giải mã để xác thực. Dùng cơ chế **băm mật khẩu chuyên dụng có salt và chi phí phù hợp**, chẳng hạn Argon2id hoặc bcrypt theo hướng dẫn bảo mật hiện hành.
- Không tự thiết kế thuật toán mật mã hay lưu khóa giải mã cùng vị trí và cùng quyền truy cập với dữ liệu cần bảo vệ.
- Không ghi access token, session cookie, thông tin đăng nhập hoặc chuỗi kết nối chứa bí mật vào thông báo lỗi.

### 6.3. Bảo vệ dữ liệu khi truyền và khi lưu

**Mã hóa khi truyền** (ví dụ TLS được cấu hình đúng) giúp bảo vệ dữ liệu trên đường truyền giữa các điểm cuối được xác minh. **Mã hóa khi lưu** có thể giảm thiệt hại khi thiết bị/lưu trữ bị truy cập trái phép, nhưng không ngăn được một tài khoản ứng dụng có đủ quyền đọc dữ liệu đã giải mã.

Cần quan tâm đến **quản lý khóa**, phân quyền database và backup, quyền truy cập công cụ vận hành, vòng đời dữ liệu và thời gian lưu giữ. Trường hợp xử lý thông tin thanh toán, sức khỏe hoặc dữ liệu được quản lý đặc biệt phải theo chính sách và yêu cầu áp dụng của hệ thống.

### 6.4. Log, trace và thông báo lỗi

Log giúp điều tra sự cố nhưng cũng có thể thành nơi rò rỉ dữ liệu. Chẳng hạn, cách ghi sau chứa rủi ro:

~~~java
// Không nên: có thể đưa toàn bộ dữ liệu cá nhân/bí mật vào log.
logger.info("Request body: {}", requestBody);
logger.error("Provider response: {}", rawProviderResponse);
~~~

Nên ghi những sự kiện có ích cho vận hành với thông tin **đã được lựa chọn**:

~~~java
// requestId là mã tương quan kỹ thuật; reasonCode là giá trị
// do ứng dụng kiểm soát, không sao chép từ dữ liệu thô bên ngoài.
logger.warn(
        "payment_failed requestId={} reasonCode={}",
        requestId,
        reasonCode
);
~~~

Giữ quyền xem log ở mức cần thiết; đặt thời gian lưu phù hợp, bảo vệ việc xuất/chia sẻ log và thực hiện xóa hoặc che dữ liệu khi chính sách yêu cầu. Cả `requestId` cũng có thể trở thành dữ liệu có khả năng liên kết với cá nhân nếu hệ thống lưu bảng đối chiếu; không nên mặc định nó hoàn toàn vô hại.

Tránh trả về stack trace, câu SQL, tên hạ tầng hoặc thông tin cấu hình cho client. Có thể trả **mã lỗi ổn định và mã yêu cầu**, đồng thời giữ chi tiết kỹ thuật cần thiết trong kênh log có kiểm soát.

### 6.5. Thư viện, cấu hình và quyền vận hành

Mã nguồn của ứng dụng có thể đúng nhưng vẫn bị ảnh hưởng bởi thư viện lỗi thời, cấu hình mặc định không an toàn, quyền database quá rộng hoặc secret bị dùng chung.

Trong quá trình phát triển, cần xem xét phiên bản và nguồn gốc dependency, thông báo lỗ hổng có liên quan, cấu hình môi trường, chính sách cấp quyền, khả năng thu hồi thông tin xác thực và cơ chế kiểm soát triển khai. Sửa dependency cần kiểm tra tính tương thích; cập nhật phiên bản đơn thuần chưa chứng minh hệ thống an toàn.

## 7. Tình huống thực tế: API hỗ trợ khách hàng

Giả sử hệ thống cho phép nhân viên hỗ trợ tra cứu đơn để xử lý yêu cầu hoàn tiền. Cần xác định rõ **nhân viên nào** được truy cập **đơn nào** và **được xem những trường nào**.

| Tình huống | Thiết kế dễ gây rủi ro | Hướng kiểm soát |
| --- | --- | --- |
| Khách hàng thay `/orders/42` thành `/orders/43` | Chỉ kiểm tra đăng nhập | Kiểm tra quyền trên từng mã đơn, gắn với chủ sở hữu hoặc quyền được cấp |
| Nhân viên hỗ trợ xem tất cả khách hàng | Chỉ cần vai trò `SUPPORT` là được xem toàn bộ | Giới hạn theo phạm vi nhiệm vụ, tenant, nhóm hoặc phiên xử lý hợp lệ |
| API trả lại entity trực tiếp | Lộ địa chỉ, số điện thoại, trường nội bộ | Dùng DTO theo mục đích; quy định rõ từng trường được phép xuất |
| Form cập nhật đơn cho client gửi `paid=true` | Ánh xạ toàn bộ JSON vào entity | Chỉ cho cập nhật các trường được phép; trạng thái thanh toán do luồng đáng tin quyết định |
| Lỗi gọi cổng thanh toán | Log toàn bộ request/response của đối tác | Dùng mã tương quan và mã lỗi đã kiểm soát; hạn chế dữ liệu nhạy cảm |
| Hệ thống phân quyền tạm thời không phản hồi | Mặc định cho truy cập để “không gián đoạn” | Từ chối hoặc dùng chính sách dự phòng an toàn đã được xác định trước |

Trường hợp có quyền truy cập khẩn cấp phải là cơ chế **được thiết kế rõ**, có thời hạn, phê duyệt và truy vết phù hợp; không nên tạo “đường tắt” ẩn trong mã.

## 8. Kiểm thử bảo mật và tiêu chí nghiệm thu

Kiểm thử bảo mật có thể bắt đầu từ hợp đồng chức năng thông thường, sau đó bổ sung các trường hợp bị từ chối và dữ liệu cần được bảo vệ. Một bộ tình huống tối thiểu cho chức năng “Xem đơn hàng”:

| Tình huống thử | Kết quả mong đợi |
| --- | --- |
| Người dùng đã xác thực mở đơn của mình | Thành công; chỉ có các trường đã được phép |
| Người dùng đã xác thực mở đơn của người khác | Bị từ chối hoặc phản hồi không tồn tại theo thiết kế API; không trả dữ liệu đơn |
| Không có phiên hoặc token hợp lệ | Không truy cập được dữ liệu; phản hồi xác thực đúng hợp đồng |
| Người dùng cố gửi `ownerId` khác trong request | Không thay đổi danh tính dùng để xét quyền |
| Input không đúng kiểu, vượt giới hạn hoặc chứa ký tự đặc biệt | Xử lý an toàn; không ghép vào câu SQL hay làm lộ chi tiết nội bộ |
| Cơ chế kiểm tra quyền gặp lỗi | Từ chối theo chính sách an toàn; có sự kiện giám sát phù hợp |
| Phản hồi lỗi ở API hoặc tích hợp bên ngoài | Không có token, mật khẩu, câu SQL, stack trace hoặc dữ liệu cá nhân không cần thiết |
| Log khi thành công, thất bại và exception | Có thông tin chẩn đoán cần thiết nhưng không chứa payload nhạy cảm |
| Thay đổi chính sách quyền | Các trường hợp truy cập hợp lệ và bị từ chối được kiểm tra hồi quy |

Bổ sung các mức kiểm thử tùy nguy cơ:

- **Unit test:** Kiểm tra quy tắc phân quyền và biến đổi dữ liệu có thể tách riêng; kiểm tra các nhánh bị từ chối.
- **Integration test:** Xác minh điều kiện lọc theo chủ sở hữu/tenant và quyền của tài khoản database.
- **API/end-to-end test:** Xác minh trạng thái HTTP, trường dữ liệu thực trả về, luồng đăng nhập và truy cập xuyên tài khoản.
- **Review/công cụ tự động:** Xem xét mã nguồn, dependency, secret trong repository và cấu hình; điều tra các phát hiện thực sự liên quan đến ngữ cảnh.
- **Đánh giá bảo mật chuyên sâu khi thích hợp:** Đối với luồng rủi ro cao, có thể cần kiểm thử xâm nhập được ủy quyền hoặc review độc lập theo quy trình của tổ chức.

**Không nên lấy “có nhiều bài test” làm bằng chứng đủ.** Một ứng dụng có độ bao phủ dòng cao vẫn có thể không kiểm thử được việc một người đọc dữ liệu của người khác. Giá trị nằm ở chỗ kiểm thử bao phủ đúng ranh giới và kịch bản lạm dụng.

## 9. Bảo mật đi cùng khả năng hiểu và thay đổi mã

Trong học phần Code Quality Fundamentals, bảo mật không đứng riêng khỏi tính dễ hiểu, dễ kiểm tra và dễ thay đổi.

- **Mã dễ hiểu** giúp reviewer biết danh tính đến từ đâu, quyền được quyết định ở đâu và trường nào rời khỏi hệ thống. Logic phân quyền rải rác trong controller, service và template dễ gây bỏ sót.
- **Mã dễ kiểm tra** cho phép thử truy cập trái phép, dữ liệu bất thường, sự cố xác thực và trạng thái lỗi mà không phải dựng quá nhiều phụ thuộc.
- **Mã dễ thay đổi** giúp cập nhật chính sách quyền hoặc thời gian lưu giữ ở các thành phần có trách nhiệm rõ, giảm tình trạng vá một nơi mà quên nơi khác.
- **Mã có thể quan sát** giúp điều tra sự cố bảo mật bằng sự kiện có cấu trúc, song vẫn tránh biến log thành kho chứa dữ liệu nhạy cảm.

Cần cân bằng hợp lý. Ví dụ, một lớp phân quyền được tái sử dụng có thể giảm trùng lặp, nhưng một cơ chế quá trừu tượng, khó lần theo cũng khiến người review khó xác nhận tài nguyên nào được cấp phép. Mục tiêu là **luồng quyết định quyền rõ ràng và có thể xác minh**, không phải số lượng lớp hoặc công cụ lớn nhất.

### Quy trình cải thiện từng bước

1. Chọn một luồng truy cập dữ liệu quan trọng, chẳng hạn “Xem đơn hàng”.
2. Vẽ đường đi dữ liệu qua request, xác thực, service, repository, phản hồi và log.
3. Xác định tài sản, đối tượng được phép, trường dữ liệu thực sự cần trả về và những điểm vượt ranh giới tin cậy.
4. Kiểm tra mã ở từng điểm: quyết định quyền có dựa vào dữ liệu client không; repository có lọc theo phạm vi không; phản hồi có thừa trường không?
5. Sửa từng phần có thể xác minh: ràng buộc quyền trên truy vấn, tách DTO, lọc log, bổ sung các bài kiểm thử bị từ chối.
6. Đánh giá sau thay đổi bằng kết quả kiểm thử, khả năng review và mức độ quan sát sự kiện; tiếp tục cập nhật theo rủi ro thực tế.

## 10. Những ngộ nhận thường gặp

**“Đã đăng nhập thì đủ an toàn.”** Đăng nhập chỉ xác định danh tính; vẫn cần xem quyền trên từng hành động và tài nguyên.

**“Frontend đã ẩn nút, người dùng không thể thao tác.”** Client do người dùng kiểm soát; điều kiện an toàn phải được xác minh tại backend.

**“Đã dùng HTTPS thì dữ liệu an toàn mọi nơi.”** TLS bảo vệ đường truyền trong phạm vi kết nối, không kiểm soát việc hệ thống lưu, log hoặc chia sẻ dữ liệu sau khi nhận.

**“Mã hóa dữ liệu là không cần phân quyền.”** Ứng dụng có khóa giải mã hoặc quyền truy vấn vẫn có thể trả dữ liệu cho sai đối tượng nếu thiếu authorization.

**“Chỉ cần che số điện thoại là bảo vệ được dữ liệu.”** Masking giảm thông tin hiển thị trong một ngữ cảnh, nhưng dữ liệu gốc vẫn cần giới hạn quyền, thời gian lưu và mục đích sử dụng.

**“Không có cảnh báo từ công cụ quét nghĩa là không có lỗ hổng.”** Công cụ chỉ phát hiện một số mẫu; lỗi phân quyền theo nghiệp vụ thường đòi hỏi hiểu logic hệ thống.

**“Ghi toàn bộ request để điều tra là tốt nhất.”** Ghi quá mức có thể làm lộ token và dữ liệu cá nhân; sự kiện có cấu trúc và chọn lọc thường hữu ích hơn.

## 11. Câu hỏi tự kiểm tra

1. Một API yêu cầu token hợp lệ nhưng cho phép đọc đơn hàng theo ID bất kỳ. Vấn đề nằm ở xác thực hay phân quyền? Cần kiểm soát ở đâu?
2. Vì sao trả trực tiếp đối tượng database từ controller có thể nguy hiểm ngay cả khi đã kiểm tra quyền của người yêu cầu?
3. Có thể dùng `PreparedStatement` để thay thế kiểm tra quyền sở hữu đơn hàng không? Hãy phân biệt hai mục tiêu bảo vệ.
4. Nếu hệ thống dùng TLS và mã hóa database nhưng ghi body chứa token vào log, rủi ro nào vẫn tồn tại?
5. Nêu một ví dụ về dữ liệu cần thiết cho chức năng, một dữ liệu có thể loại bỏ khỏi phản hồi và một bí mật tuyệt đối không nên trả về.
6. Điều gì nên xảy ra khi dịch vụ kiểm tra phân quyền không khả dụng? Cần thiết kế kiểm thử thế nào để xác nhận quyết định đó?
7. Khi đổi chính sách giữ dữ liệu từ nhiều năm xuống thời hạn ngắn hơn, những nơi nào ngoài bảng dữ liệu chính cần được rà soát?

## Ghi nhớ

**Bảo mật là thuộc tính chất lượng có thể kiểm tra được trong thiết kế và mã nguồn.** Hãy bắt đầu từ dữ liệu cần bảo vệ, xác định ai được phép làm gì, đặt kiểm soát tại ranh giới tin cậy, giảm lượng dữ liệu đi qua mỗi bước và kiểm tra cả các trường hợp bị từ chối. Một hệ thống đáng tin cậy cần bảo vệ dữ liệu khi mọi thứ chạy đúng và vẫn duy trì quyết định an toàn khi gặp đầu vào xấu, yêu cầu không hợp lệ hoặc lỗi phụ thuộc.
