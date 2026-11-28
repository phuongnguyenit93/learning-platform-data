# Tài sản của bên thứ ba

## 1. Mục tiêu và phạm vi

Trong chương **Phân loại tài sản**, tài sản của bên thứ ba cần được nhìn nhận theo mối liên hệ với hệ thống đang thiết kế: hệ thống sử dụng tài sản nào, giao dữ liệu hoặc quyền gì cho tài sản đó và chịu hậu quả gì khi tài sản bị xâm phạm. Việc tài sản nằm ngoài quyền sở hữu hoặc hạ tầng của tổ chức không làm mất đi rủi ro đối với tổ chức.

Bài học này hướng dẫn chuyển thông tin về tài sản bên ngoài thành **yêu cầu bảo mật cụ thể, đo được và có thể kiểm chứng**. Sau bài học, người học có thể:

- Nhận diện tài sản, chủ thể sở hữu, nơi lưu giữ và bên có khả năng kiểm soát tài sản.
- Phân loại tài sản theo tính bí mật, toàn vẹn, sẵn sàng và phạm vi tác động khi xảy ra sự cố.
- Xác định ranh giới tin cậy, trách nhiệm và bằng chứng cần thu thập.
- Đặc tả yêu cầu về xác thực, phân quyền, dữ liệu, logging, phục hồi và kết thúc sử dụng dịch vụ.
- Liên kết từng yêu cầu với rủi ro, quyết định kiến trúc và tiêu chí kiểm thử trong vòng đời phát triển.

Các con số trong bài là **giả định cho ví dụ học tập**, cần được điều chỉnh theo dữ liệu, mô hình đe dọa và năng lực vận hành thực tế. Chúng không phải ngưỡng bảo mật áp dụng chung cho mọi nhà cung cấp.

## 2. Hiểu đúng tài sản của bên thứ ba

### 2.1. Xác định phạm vi theo quan hệ phụ thuộc

Trong bài này, bên thứ ba là tổ chức hoặc cá nhân bên ngoài phạm vi quản trị nội bộ, cung cấp tài sản, dịch vụ hoặc khả năng truy cập mà hệ thống phụ thuộc vào. Ví dụ gồm nhà cung cấp đám mây, nền tảng gửi thông báo, đơn vị vận hành thuê ngoài và nhà phát hành thư viện phần mềm.

**Tài sản của bên thứ ba** có thể là dữ liệu, phần mềm, hạ tầng, dịch vụ hoặc danh tính do bên ngoài sở hữu hay quản lý nhưng tham gia vào hoạt động của hệ thống. Cần phân biệt với **tài sản của tổ chức do bên thứ ba xử lý**. Hai nhóm này có thể xuất hiện trong cùng một tích hợp nhưng có quyền sở hữu và yêu cầu kiểm soát khác nhau.

| Tình huống | Tài sản bên ngoài | Tài sản của tổ chức liên quan | Câu hỏi bảo mật chính |
|---|---|---|---|
| Gửi thông báo giao dịch qua dịch vụ bên ngoài | API gửi thông báo, hạ tầng xử lý, tài khoản hỗ trợ của nhà cung cấp | Địa chỉ nhận, nội dung thông báo, khóa tích hợp | Bên ngoài thấy dữ liệu gì và ai được quyền gửi? |
| Đăng nhập qua dịch vụ nhận dạng | Điểm cấp token, khóa công khai, dịch vụ xác thực | Ánh xạ người dùng, phiên ứng dụng, chính sách cấp quyền | Tin cậy danh tính nào và ứng dụng tự quyết định quyền ra sao? |
| Cài thư viện từ kho gói | Mã thư viện, gói phát hành, tài khoản nhà phát hành | Mã ứng dụng, môi trường build, sản phẩm triển khai | Gói nào được phép chạy và có khả năng tiếp cận bí mật nào? |
| Thuê vận hành cơ sở dữ liệu | Dịch vụ quản trị, công cụ hỗ trợ, tài khoản kỹ thuật | Cơ sở dữ liệu, bản sao lưu, khóa mã hóa | Ai có quyền đọc, sửa và phục hồi dữ liệu? |
| Nhận bảng giá từ một đối tác | Tệp dữ liệu hoặc API bảng giá | Quy tắc tính tiền, đơn hàng, báo cáo | Làm sao phát hiện dữ liệu sai hoặc quá cũ? |

Tên nhà cung cấp là thông tin về **chủ thể**; API, tài khoản, kho lưu trữ, tập dữ liệu hoặc gói phần mềm mới là các đối tượng cần lập hồ sơ tài sản. Chỉ ghi một dòng “nhà cung cấp A” thường không đủ để xác định quyền, dữ liệu và yêu cầu kiểm thử.

### 2.2. Tách quyền sở hữu khỏi khả năng kiểm soát

Với mỗi tài sản, cần xác định riêng:

- **Chủ sở hữu tài sản:** bên có quyền sở hữu đối với tài sản đang xét.
- **Bên lưu giữ hoặc xử lý:** bên đang lưu trữ, truyền tải, vận hành hoặc biến đổi tài sản.
- **Đầu mối chịu trách nhiệm nội bộ:** người hoặc nhóm chấp nhận rủi ro, phê duyệt cách sử dụng và theo dõi yêu cầu bảo mật.
- **Bên thực thi kiểm soát:** bên có khả năng cấu hình quyền, thu hồi khóa, giữ log, khôi phục hoặc xóa tài sản.

Ví dụ, doanh nghiệp sở hữu nội dung thông báo; nhà cung cấp lưu một bản sao để xử lý; nhóm sản phẩm chịu trách nhiệm về mục đích sử dụng; nhóm nền tảng quản lý khóa API; nhà cung cấp thực hiện xóa bản sao trong hệ thống của họ. Một nhãn “thuộc nhà cung cấp” không thể thay cho các phân định này.

### 2.3. Nhận diện phụ thuộc gián tiếp

Nhà cung cấp có thể tiếp tục sử dụng nền tảng đám mây, dịch vụ hỗ trợ hoặc nhà thầu khác. Phụ thuộc trực tiếp và gián tiếp có thể tạo thêm nơi lưu dữ liệu, tài khoản truy cập và điểm gây gián đoạn.

Không phải lúc nào nhóm phát triển cũng có thể kiểm kê toàn bộ chuỗi phụ thuộc. Tuy nhiên, với các phụ thuộc có ảnh hưởng đáng kể, cần biết ít nhất: chức năng được chuyển tiếp, nhóm dữ liệu được tiếp cận, thay đổi nào phải thông báo và bên nào cung cấp bằng chứng kiểm soát. Chỗ chưa biết phải được ghi thành khoảng trống cần giải quyết, thay vì mặc định rằng không có rủi ro.

## 3. Lập hồ sơ và phân loại tài sản

### 3.1. Hồ sơ tối thiểu phục vụ đặc tả yêu cầu

Một hồ sơ tài sản cần đủ chi tiết để trả lời câu hỏi “yêu cầu này bảo vệ đối tượng nào, ở đâu, do ai thực hiện?”. Các trường sau là một mẫu thực hành:

| Nhóm thông tin | Nội dung cần ghi |
|---|---|
| Định danh | Mã tài sản, tên, loại tài sản, môi trường sử dụng, dịch vụ hoặc sản phẩm phụ thuộc |
| Chủ thể | Nhà cung cấp trực tiếp, bên xử lý tiếp theo đã biết, đầu mối chịu trách nhiệm nội bộ |
| Dữ liệu | Các trường dữ liệu gửi đi, nhận về, lưu tạm, ghi log và đưa vào bản sao lưu |
| Truy cập | Danh tính máy, tài khoản hỗ trợ, phạm vi quyền, cơ chế xác thực và điểm quản lý bí mật |
| Luồng và vị trí | Nguồn, đích, giao thức, nơi xử lý đã xác nhận và ranh giới tin cậy |
| Tầm quan trọng | Mức bí mật, toàn vẹn, sẵn sàng; chức năng bị ảnh hưởng; phạm vi người dùng chịu tác động |
| Vòng đời | Tạo lập, sử dụng, thay đổi, lưu giữ, xuất dữ liệu, thu hồi quyền và kết thúc sử dụng |
| Kiểm chứng | Kiểm soát hiện có, bằng chứng, ngày xác nhận, hạn chế và rủi ro còn lại |

Không ghi giá trị bí mật thật vào hồ sơ. Với khóa API, chỉ ghi mã tham chiếu tới nơi quản lý bí mật, chủ thể được sử dụng và phạm vi quyền.

### 3.2. Đánh giá theo ba thuộc tính và phạm vi tác động

Phân loại cần dựa trên cách tài sản được sử dụng trong hệ thống, không chỉ dựa trên mức độ nổi tiếng hay chứng nhận của nhà cung cấp.

- **Bí mật:** nếu dữ liệu hoặc quyền truy cập bị lộ, ai bị ảnh hưởng và thông tin nào bị tiết lộ?
- **Toàn vẹn:** nếu tài sản bị sửa sai hoặc giả mạo, quyết định nghiệp vụ nào có thể bị thay đổi?
- **Sẵn sàng:** nếu tài sản không truy cập được hoặc trả kết quả chậm, chức năng nào ngừng hoạt động và trong bao lâu?
- **Phạm vi tác động:** một lỗi chỉ ảnh hưởng một giao dịch, một khách hàng hay nhiều hệ thống và toàn bộ môi trường sản xuất?

Một tập dữ liệu công khai có thể có yêu cầu bí mật thấp nhưng yêu cầu toàn vẹn cao nếu được dùng để tính tiền. Một thư viện không lưu dữ liệu khách hàng vẫn có thể có mức tác động cao nếu mã của nó chạy trong tiến trình có quyền truy cập cơ sở dữ liệu.

Cũng cần đánh giá dữ liệu suy ra: địa chỉ nhận, thời điểm gửi, mã tương quan và tần suất giao dịch có thể tiết lộ hoạt động của người dùng dù nội dung thông báo đã được rút gọn.

### 3.3. Ví dụ phân loại một tích hợp gửi thông báo

Giả sử hệ thống đặt hàng dùng nhà cung cấp **NotifyHub** để gửi email xác nhận. Đây là tên giả định xuyên suốt bài. Quyết định nghiệp vụ của ví dụ là: lỗi gửi email không được làm mất hoặc hủy đơn hàng đã xác nhận.

| Mã | Tài sản cần quản lý | Đánh giá theo ngữ cảnh | Hệ quả đối với yêu cầu |
|---|---|---|---|
| AS-01 | API gửi email và tài khoản tích hợp NotifyHub | Toàn vẹn cao vì có thể phát tán nội dung giả; sẵn sàng quan trọng với thông báo | Hạn chế quyền gửi, kiểm soát đích kết nối, quản lý hàng đợi khi dịch vụ lỗi |
| AS-02 | Địa chỉ nhận và nội dung email do tổ chức chuyển đi | Cần bảo vệ bí mật; phạm vi ảnh hưởng tăng theo số bản ghi được lưu | Giảm trường dữ liệu, giới hạn lưu giữ, kiểm soát truy cập và xóa dữ liệu |
| AS-03 | Danh tính máy và khóa API do tổ chức sử dụng | Bí mật cao; lộ khóa có thể cho phép gửi giả hoặc tiêu thụ hạn mức | Lưu trong kho bí mật, tách môi trường, giới hạn phạm vi và có quy trình thu hồi |
| AS-04 | Sự kiện trạng thái gửi do nhà cung cấp trả về | Toàn vẹn cao nếu được dùng để cập nhật trạng thái | Xác thực nguồn, chống phát lại và kiểm tra quan hệ với thông báo đã gửi |
| AS-05 | Bản sao nội dung và log tại nhà cung cấp | Mức nhạy cảm phụ thuộc dữ liệu thực tế được lưu | Xác định truy cập hỗ trợ, thời hạn lưu, cách xuất log và bằng chứng xóa |

Mức phân loại phải đi kèm lý do. Nếu “cao” chỉ là một nhãn mà không dẫn đến yêu cầu hoặc quyết định kiến trúc nào, hồ sơ chưa giúp được việc thiết kế bảo mật.

## 4. Ranh giới tin cậy và trách nhiệm chung

### 4.1. Vẽ luồng dữ liệu trước khi viết yêu cầu

Với ví dụ NotifyHub, luồng chính có thể được mô tả như sau:

```text
[Dịch vụ đơn hàng] -> [Hàng đợi nội bộ] -> [Bộ gửi thông báo]
                                               |
                                      Ranh giới ra ngoài
                                               v
                                      [API NotifyHub]
                                               |
                                       [Hộp thư người nhận]

[NotifyHub] -> Ranh giới vào ứng dụng -> [Điểm nhận webhook]
                                            |
                                   [Trạng thái thông báo]
```

Webhook là yêu cầu HTTP do bên ngoài chủ động gửi tới điểm nhận của ứng dụng. Luồng đi ra có xác thực không làm cho luồng webhook đi vào tự động đáng tin cậy. Mỗi chiều cần có giả định và kiểm soát riêng.

Ngoài luồng dữ liệu chính, cần xem xét đường quản trị: bảng điều khiển của nhà cung cấp, tài khoản hỗ trợ, thao tác đổi khóa và nơi tải log. Đường quản trị thường có quyền lớn hơn đường xử lý giao dịch thông thường.

### 4.2. Phân định ai làm, ai kiểm chứng

| Hoạt động | Trách nhiệm của tổ chức sử dụng | Trách nhiệm cần xác nhận với nhà cung cấp |
|---|---|---|
| Chọn dữ liệu gửi | Quyết định trường dữ liệu và mục đích; loại bỏ dữ liệu không cần thiết | Xác nhận dữ liệu được tiếp nhận, xử lý, ghi log và chuyển tiếp |
| Quản lý danh tính | Cấp quyền cho ứng dụng và nhân sự của mình; thu hồi khi thay đổi vai trò | Cơ chế phân quyền nền tảng, truy cập hỗ trợ và truy vết thao tác |
| Bảo vệ tích hợp | Kiểm tra kết nối, bảo vệ bí mật, giới hạn quyền và xác thực webhook | Cung cấp cơ chế xác thực, quản lý khóa và giao thức tích hợp phù hợp |
| Xử lý sự cố | Phát hiện ảnh hưởng trong hệ thống, cô lập tích hợp và vận hành phương án dự phòng | Cung cấp đầu mối sự cố, thông tin ảnh hưởng và bằng chứng trong phạm vi của họ |
| Phục hồi | Khôi phục trạng thái nghiệp vụ, hàng đợi và dữ liệu do tổ chức quản lý | Khôi phục dịch vụ, dữ liệu và bản sao lưu thuộc phần họ vận hành |
| Kết thúc sử dụng | Ngắt luồng dữ liệu, thu hồi quyền, kiểm tra dữ liệu đã xuất | Xuất và xóa dữ liệu theo phạm vi cùng lịch lưu giữ đã thống nhất |

Không có một mô hình trách nhiệm chung duy nhất áp dụng cho mọi dịch vụ. Nếu nhà cung cấp chỉ nêu “có mã hóa” nhưng không xác định dữ liệu nào, tại giai đoạn nào và ai quản lý khóa, thông tin đó chưa đủ để viết tiêu chí chấp nhận.

## 5. Từ tài sản và đe dọa đến yêu cầu kiểm chứng được

### 5.1. Chuỗi truy vết

Một yêu cầu hữu ích có thể truy ngược theo chuỗi:

```text
Tài sản -> Mục tiêu bảo vệ -> Kịch bản đe dọa -> Rủi ro
        -> Yêu cầu bảo mật -> Cơ chế kiến trúc -> Kiểm thử và bằng chứng
```

Ví dụ:

```text
AS-04: Sự kiện trạng thái gửi
Mục tiêu: Chỉ cập nhật trạng thái từ sự kiện hợp lệ, đúng thông báo.
Đe dọa: Kẻ tấn công gửi webhook giả hoặc phát lại sự kiện cũ.
Rủi ro: Ứng dụng ghi nhận sai kết quả gửi, gây sai lệch đối soát.
Yêu cầu: Xác thực chữ ký, kiểm tra thời gian, chống xử lý lặp và ràng buộc sự kiện.
Kiến trúc: Bộ kiểm tra webhook trước tầng ghi trạng thái, có kho mã sự kiện.
Kiểm thử: Chữ ký sai, dữ liệu bị sửa, sự kiện quá hạn, lặp và sai tài khoản.
```

### 5.2. Cấu trúc một yêu cầu

Mỗi yêu cầu nên nêu rõ:

1. **Đối tượng và điều kiện:** áp dụng cho tài sản, luồng hoặc môi trường nào.
2. **Hành vi bắt buộc:** hệ thống hoặc nhà cung cấp phải thực hiện điều gì.
3. **Chỉ số hoặc giới hạn:** thời gian, phạm vi quyền, tập dữ liệu hay điều kiện từ chối.
4. **Trách nhiệm:** ai triển khai, ai vận hành và ai cung cấp bằng chứng.
5. **Tiêu chí chấp nhận:** kiểm thử thế nào và kết quả quan sát được là gì.

Ví dụ yêu cầu “nhà cung cấp phải an toàn” không có đối tượng kiểm thử. Có thể cụ thể hóa thành: “Mọi tài khoản nhân sự truy cập bảng điều khiển sản xuất phải sử dụng xác thực đa yếu tố; nhóm vận hành xuất danh sách tài khoản và cấu hình xác thực để kiểm tra trước khi đưa tích hợp vào sử dụng, sau đó kiểm tra lại theo lịch đã thống nhất”.

Các yêu cầu kiểm soát ứng dụng cần được đưa vào thiết kế và kiểm thử. Các yêu cầu về hành vi nội bộ của nhà cung cấp cần được xác nhận bằng cấu hình có thể quan sát, điều khoản dịch vụ, báo cáo phù hợp hoặc bằng chứng do nhà cung cấp cung cấp. Không tự coi điều khoản đã ký là bằng chứng kiểm soát đang hoạt động.

## 6. Đặc tả các nhóm yêu cầu cốt lõi

### 6.1. Xác thực và quản lý bí mật

Các danh tính cần được tách theo ứng dụng và môi trường. Một khóa dùng chung cho thử nghiệm và sản xuất làm tăng phạm vi tác động khi môi trường thử nghiệm bị lộ.

Trong ví dụ NotifyHub, có thể đặt yêu cầu:

- **REQ-AUTH-01:** Bộ gửi thông báo sản xuất chỉ lấy khóa tích hợp từ kho bí mật qua danh tính chạy dịch vụ được cấp quyền đọc đúng khóa đó. Khóa không được ghi trong mã nguồn, URL, log hoặc phản hồi lỗi. Kiểm chứng bằng cấu hình cấp quyền và một lượt thử gửi có kiểm tra log.
- **REQ-AUTH-02:** Khóa cũ phải bị vô hiệu hóa tại nhà cung cấp trong vòng 15 phút kể từ khi đầu mối ứng cứu xác nhận khóa bị lộ. Sau thu hồi, một yêu cầu mới dùng khóa cũ phải bị từ chối. Thử diễn tập bằng khóa dành riêng cho kiểm thử, có đo thời gian và lưu kết quả.
- **REQ-AUTH-03:** Tài khoản nhân sự có quyền quản trị tích hợp sản xuất phải dùng xác thực đa yếu tố và có thể truy về từng người. Việc cấp, đổi và thu hồi quyền phải để lại dấu vết kiểm tra.

Thu hồi khóa không chứng minh rằng các yêu cầu đã được chấp nhận trước đó đã bị hủy. Cần xác định riêng cách xử lý công việc đang chờ, phiên đang tồn tại và tác vụ mà nhà cung cấp đã bắt đầu thực hiện.

### 6.2. Phân quyền và giới hạn phạm vi

Quyền được cấp phải tương xứng với chức năng tích hợp. Với dịch vụ gửi thông báo, cần xem xét quyền gửi, đọc nội dung, xuất danh sách người nhận, quản trị khóa và thay đổi cấu hình.

**REQ-AUTHZ-01:** Danh tính gửi thông báo sản xuất chỉ được gửi bằng miền gửi đã phê duyệt, không có quyền quản lý người dùng hoặc tạo khóa mới. Tiêu chí chấp nhận gồm gửi thành công với miền hợp lệ, bị từ chối khi dùng miền ngoài phạm vi và không thực hiện được thao tác quản trị.

Nếu nhà cung cấp không hỗ trợ quyền chi tiết như yêu cầu, phải ghi rõ khoảng thiếu. Có thể đánh giá một tài khoản tách biệt, giới hạn luồng ra hoặc lựa chọn tích hợp khác. Chỉ ghi “đã áp dụng quyền tối thiểu” khi tập quyền thực tế đã được kiểm tra.

Với truy cập hỗ trợ của nhà cung cấp vào tài sản do tổ chức quản lý, yêu cầu cần nêu tài nguyên, mục đích, thời hạn quyền, người phê duyệt và bằng chứng thao tác. Quyền hỗ trợ thường trực trên toàn bộ môi trường phải được đánh giá như một rủi ro riêng.

### 6.3. Dữ liệu và giới hạn sử dụng

Mã hóa bảo vệ một số tình huống truy cập trái phép nhưng không thay thế quyết định về việc bên ngoài có cần nhận dữ liệu hay không. Dịch vụ xử lý nội dung thường phải tiếp cận nội dung rõ tại một giai đoạn nào đó.

**REQ-DATA-01:** Luồng gửi email xác nhận chỉ chuyển địa chỉ nhận, mã thông báo, ngôn ngữ, mã mẫu và tham số nội dung đã được liệt kê trong hợp đồng dữ liệu. Không gửi thông tin thanh toán hoặc bản ghi khách hàng đầy đủ. Kiểm chứng bằng kiểm thử hợp đồng với dữ liệu giả và kiểm tra payload tại điểm tích hợp.

**REQ-DATA-02:** Kết nối tới API phải dùng HTTPS, xác thực chứng chỉ và tên máy chủ theo chính sách của ứng dụng. Kết nối có chứng chỉ không được tin cậy hoặc sai tên phải thất bại và không chuyển sang kết nối không mã hóa.

**REQ-DATA-03:** Nhà cung cấp phải xác nhận rõ nơi xử lý, phạm vi truy cập, mục đích sử dụng và các bên tiếp nhận tiếp theo đối với dữ liệu gửi. Những thay đổi làm vượt phạm vi đã phê duyệt phải được đánh giá trước khi cho phép chuyển dữ liệu theo phạm vi mới.

Với lưu giữ, cần tách dữ liệu đang hoạt động, log, bản sao lưu và dữ liệu tại bên xử lý tiếp theo. Ví dụ, có thể yêu cầu xóa nội dung email khỏi kho hoạt động trong 7 ngày sau khi kết thúc xử lý và loại khỏi chu kỳ bản sao lưu trong tối đa 35 ngày. Hai mốc phải có bằng chứng riêng; xác nhận xóa trên giao diện không chứng minh mọi bản sao đã bị xóa.

Nếu chỉ có thể kiểm chứng thông qua xác nhận của nhà cung cấp, hồ sơ phải ghi rõ giới hạn bằng chứng. Trước khi tiếp nhận dữ liệu nhạy cảm, cần xử lý khoảng thiếu bằng lựa chọn dữ liệu, kiến trúc hoặc quyết định chấp nhận rủi ro có trách nhiệm.

### 6.4. Toàn vẹn dữ liệu nhận về

Dữ liệu từ bên thứ ba vẫn là đầu vào cần kiểm tra. Kết nối mã hóa không chứng minh dữ liệu đúng về nghiệp vụ hoặc chưa bị phát lại.

**REQ-INT-01:** Điểm nhận webhook chỉ xử lý sự kiện có chữ ký hợp lệ theo giao thức đã thống nhất, dấu thời gian nằm trong khoảng lệch cho phép 5 phút và mã sự kiện chưa được xử lý. Khi giao thức ký trên nội dung thô, việc xác minh phải dùng đúng chuỗi byte nhận được trước khi biến đổi nội dung.

Ngoài chữ ký, sự kiện phải thuộc đúng tài khoản tích hợp, tham chiếu đến thông báo có tồn tại và tạo ra chuyển trạng thái hợp lệ. Mã sự kiện đã xử lý được lưu bền vững trong 7 ngày; thời hạn này giả định bao phủ toàn bộ khoảng nhà cung cấp được phép gửi lại. Nếu lịch gửi lại thay đổi, thời hạn chống lặp phải được đánh giá lại.

Tiêu chí kiểm thử gồm: sự kiện hợp lệ được xử lý một lần; sai chữ ký, bị sửa hoặc quá hạn bị từ chối; sự kiện trùng không tạo thêm tác động nghiệp vụ; sự kiện có chữ ký hợp lệ nhưng thuộc tài khoản khác không cập nhật dữ liệu. Việc chống xử lý lặp phải có hiệu lực cả khi hai bản sao đến đồng thời.

Với dữ liệu tham chiếu như bảng giá, tiêu chí có thể là nguồn được phê duyệt, phiên bản, độ mới tối đa, định dạng, miền giá trị và ngưỡng biến động cần rà soát. Không dùng chữ ký làm tiêu chí duy nhất cho tính đúng đắn nghiệp vụ.

### 6.5. Logging và khả năng điều tra

Log cần giúp nối một thao tác nội bộ với yêu cầu gửi ra ngoài, kết quả nhận về và hoạt động quản trị. Tuy nhiên, log cũng là một bản sao dữ liệu cần được phân loại.

**REQ-LOG-01:** Mỗi lần gọi API phải có mã tương quan, mã thông báo nội bộ, danh tính dịch vụ, thời điểm, loại thao tác, kết quả và mã lỗi đã chuẩn hóa. Log không chứa khóa API, token, nội dung email hoặc địa chỉ nhận đầy đủ.

**REQ-LOG-02:** Mọi thao tác tạo khóa, đổi quyền và thay đổi cấu hình tích hợp sản xuất phải có dấu vết gồm chủ thể, thời điểm, đối tượng và kết quả. Trong ví dụ, dấu vết phải truy vấn được trong vòng 10 phút sau thao tác và được lưu 90 ngày với quyền truy cập hạn chế.

Mã tương quan nên là mã không chứa dữ liệu cá nhân trực tiếp. Nếu cần liên kết với người dùng, quyền tra cứu bảng ánh xạ phải được kiểm soát riêng. Tránh cho rằng băm một địa chỉ email sẽ tự động làm dữ liệu không còn nhạy cảm.

Kiểm chứng log bằng một chuỗi thao tác có chủ đích: gửi thành công, xác thực thất bại, webhook bị từ chối và thay đổi cấu hình. Đối chiếu kết quả thực tế với trường log bắt buộc; thử truy cập bằng danh tính không được cấp quyền. Nếu thiếu log phía nhà cung cấp, phải ghi rõ phần điều tra nào không thể thực hiện.

### 6.6. Sẵn sàng và phục hồi

Cam kết thời gian hoạt động của nhà cung cấp không tự tạo ra khả năng phục hồi cho ứng dụng. Kiến trúc phải xác định hành vi khi bên ngoài lỗi, chậm, trả kết quả không rõ ràng hoặc ngừng cung cấp dịch vụ.

Trong ví dụ NotifyHub:

- **REQ-REC-01:** Lỗi dịch vụ gửi email không làm mất đơn hàng đã xác nhận. Yêu cầu gửi được lưu bền vững và có thể đối soát với đơn hàng sau phục hồi. Dùng thử nghiệm dừng tiến trình ở các điểm chuyển trạng thái để kiểm tra không mất yêu cầu.
- **REQ-REC-02:** Mỗi lần gọi API có thời gian chờ tối đa 3 giây. Cơ chế thử lại có giới hạn, tăng khoảng chờ và tuân theo tín hiệu giới hạn lưu lượng. Yêu cầu không xác định được kết quả phải có cách đối soát trước khi gửi lại để giảm nguy cơ gửi trùng.
- **REQ-REC-03:** Khi giả lập nhà cung cấp ngừng hoạt động 30 phút, hệ thống tiếp tục tiếp nhận đơn hàng và bảo toàn yêu cầu gửi. Sau khi dịch vụ trở lại, hàng đợi phải được xử lý hết trong 60 phút với giả định tối đa 10.000 yêu cầu đang chờ và lưu lượng mới không quá 100 yêu cầu mỗi phút.

Yêu cầu cuối chỉ có ý nghĩa nếu hạn mức gửi, năng lực xử lý và phương pháp đo đã được xác nhận. Chuyển sang nhà cung cấp dự phòng cũng cần kiểm tra dữ liệu, khóa, cấu hình miền gửi và khả năng gửi trùng; không thể coi dự phòng là một thao tác chuyển địa chỉ đơn giản.

Nếu tài sản bên ngoài là nguồn lưu dữ liệu cần phục hồi, hãy đặc tả thêm **RPO** và **RTO**. RPO là mức mất dữ liệu tối đa chấp nhận được theo khoảng thời gian; RTO là khoảng thời gian mục tiêu để khôi phục hoạt động sau gián đoạn. Bằng chứng phải đến từ thử phục hồi dữ liệu và chức năng phù hợp, không chỉ từ việc có tệp sao lưu.

## 7. Thay đổi và kết thúc vòng đời tài sản

Phân loại tài sản không chỉ thực hiện khi chọn nhà cung cấp. Mỗi thay đổi có thể làm khác đi dữ liệu, quyền hoặc mức phụ thuộc ban đầu.

| Sự kiện | Điều cần xem lại | Kết quả phải có |
|---|---|---|
| Thêm loại dữ liệu hoặc mục đích sử dụng | Mức bí mật, phạm vi sử dụng, nơi ghi log và lưu giữ | Hồ sơ tài sản cùng yêu cầu dữ liệu được cập nhật trước khi dùng |
| Cài SDK hoặc cập nhật gói phần mềm | Quyền chạy mã, nguồn gói, dữ liệu thu thập, ảnh hưởng môi trường build | Phiên bản được chấp thuận, bằng chứng kiểm tra và khả năng quay về phiên bản phù hợp |
| Thay đổi API, cơ chế ký hoặc hạn mức | Xác thực, hợp đồng dữ liệu, chống lặp và năng lực phục hồi | Kiểm thử tích hợp và vận hành được thực hiện lại theo phần ảnh hưởng |
| Thay bên xử lý tiếp theo hoặc nơi xử lý | Đường đi dữ liệu và khả năng kiểm chứng kiểm soát | Đánh giá thay đổi và quyết định chấp thuận có trách nhiệm |
| Nhân sự hỗ trợ thay vai trò | Tài khoản, quyền tồn tại và phiên truy cập | Thu hồi quyền, xử lý phiên theo cơ chế thực tế và giữ bằng chứng |
| Ngừng sử dụng | Luồng đang chạy, dữ liệu, khóa, webhook, bản sao và chi phí còn phát sinh | Hoàn thành các tiêu chí thoát dịch vụ |

Một bộ tiêu chí thoát dịch vụ có thể yêu cầu: ngừng phát sinh yêu cầu mới; xử lý công việc đang chờ; xuất dữ liệu theo định dạng đọc được; kiểm tra số lượng, quan hệ và khả năng sử dụng của dữ liệu đã xuất; thu hồi khóa; ngắt webhook; đóng tài khoản và xác nhận xóa dữ liệu theo từng lớp lưu trữ.

Nếu bản sao lưu còn tồn tại đến hết chu kỳ lưu giữ, cần ghi ngày hết hạn và cách ngăn dữ liệu đã yêu cầu xóa quay trở lại kho hoạt động sau phục hồi. Kết thúc hợp đồng hoặc nhận một tệp xuất chưa đủ để chứng minh đã kết thúc mọi phụ thuộc.

## 8. Ma trận truy vết dùng trong phát triển

Bảng sau nối việc phân loại với những đầu việc cụ thể trong thiết kế và kiểm thử của ví dụ:

| Tài sản và rủi ro | Yêu cầu liên quan | Quyết định kiến trúc | Bằng chứng chấp nhận |
|---|---|---|---|
| AS-03: Lộ khóa cho phép gửi giả | REQ-AUTH-01, REQ-AUTH-02, REQ-AUTHZ-01 | Kho bí mật, danh tính riêng, phạm vi quyền gửi | Cấu hình quyền; kiểm thử lấy khóa trái phép; diễn tập thu hồi; thử thao tác vượt quyền |
| AS-02, AS-05: Dữ liệu bị chuyển hoặc giữ quá phạm vi | REQ-DATA-01, REQ-DATA-03 và yêu cầu lưu giữ | Bộ ánh xạ dữ liệu cho phép; cấu hình lưu giữ; quy trình xóa | Payload kiểm thử; phạm vi xử lý đã xác nhận; cấu hình và bằng chứng xóa theo từng lớp |
| AS-04: Webhook giả hoặc phát lại làm sai trạng thái | REQ-INT-01 | Xác minh trước khi cập nhật; chống lặp bền vững; kiểm tra chuyển trạng thái | Kiểm thử chữ ký, thời gian, sự kiện trùng đồng thời, sai tài khoản và sai quan hệ |
| AS-01: Nhà cung cấp lỗi gây mất thông báo | REQ-REC-01, REQ-REC-02, REQ-REC-03 | Lưu bền vững yêu cầu gửi, hàng đợi, thử lại và đối soát | Thử lỗi tại điểm chuyển trạng thái; mô phỏng ngừng dịch vụ; số liệu xử lý tồn đọng |
| AS-01, AS-05: Không truy được nguyên nhân sự cố | REQ-LOG-01, REQ-LOG-02 | Mã tương quan, thu thập dấu vết, giới hạn quyền đọc log | Đối chiếu chuỗi sự kiện; đo độ trễ log; thử truy cập log trái quyền |

Trong quản lý yêu cầu, mỗi dòng nên có người chịu trách nhiệm, trạng thái triển khai, liên kết tới bằng chứng, ngày kiểm tra và rủi ro còn lại. Một kiểm thử đã đạt chỉ phản ánh phiên bản và phạm vi đã thử; thay đổi quyền hoặc cấu hình có thể làm bằng chứng cũ không còn phù hợp.

Nếu một kiểm soát không khả thi, cần mô tả rõ tài sản chịu ảnh hưởng, kịch bản còn mở, biện pháp thay thế, người có thẩm quyền chấp nhận và thời điểm xem lại. Không đổi nhãn tài sản xuống mức thấp hơn chỉ để phù hợp với khả năng hiện có của nhà cung cấp.

## 9. Những sai sót thường gặp

| Sai sót | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ phân loại dữ liệu tổ chức tự lưu | Bỏ sót bản sao, log và quyền bên ngoài | Theo toàn bộ luồng gửi, nhận, hỗ trợ, sao lưu và xóa |
| Coi dữ liệu công khai là không quan trọng | Bỏ qua rủi ro sửa sai dữ liệu dùng cho nghiệp vụ | Đánh giá toàn vẹn và ảnh hưởng quyết định sử dụng dữ liệu |
| Coi mọi dữ liệu của cùng nhà cung cấp có một mức phân loại | Kiểm soát quá rộng hoặc thiếu chính xác | Tách theo loại tài sản, tập dữ liệu, môi trường và chức năng |
| Chỉ yêu cầu “mã hóa, có log, có backup” | Không có điều kiện kiểm thử rõ ràng | Ghi phạm vi, hành vi bắt buộc, chỉ số, trách nhiệm và bằng chứng |
| Dùng chứng nhận hoặc báo cáo chung thay cho kiểm tra tích hợp | Không biết cấu hình và luồng dữ liệu của mình có được bảo vệ | Đối chiếu phạm vi báo cáo và kiểm tra cấu hình, quyền, luồng thực tế |
| Đồng nhất chữ ký hợp lệ với sự kiện đúng nghiệp vụ | Sự kiện đúng nguồn nhưng sai tài khoản hoặc sai quan hệ vẫn được xử lý | Xác minh cả nguồn, thời gian, chống lặp và ràng buộc nghiệp vụ |
| Kiểm tra thành công ở môi trường thử nghiệm rồi coi như hoàn tất | Quyền, dữ liệu và hạn mức sản xuất có thể khác | Xác nhận các khác biệt cấu hình và bằng chứng cho môi trường đích |
| Có nhà cung cấp dự phòng nhưng chưa thử chuyển đổi | Phương án dự phòng có thể không gửi được hoặc gây gửi trùng | Diễn tập theo tải, dữ liệu và điều kiện lỗi đã xác định |

## 10. Bài tập vận dụng

Một hệ thống bán hàng dự định thêm công cụ phân tích hành vi do bên ngoài cung cấp. SDK chạy trong trình duyệt, gửi sự kiện sang máy chủ nhà cung cấp và cho phép kỹ thuật viên bên ngoài hỗ trợ cấu hình. Nhóm phát triển dự định gửi mã khách hàng, URL trang và nội dung lỗi để điều tra vấn đề thanh toán.

Hãy thực hiện các bước sau:

1. Lập hồ sơ riêng cho SDK, điểm nhận sự kiện, tập dữ liệu phân tích và danh tính hỗ trợ. Phân biệt tài sản thuộc nhà cung cấp với dữ liệu do tổ chức chuyển giao.
2. Vẽ luồng dữ liệu, chỉ ra khả năng URL hoặc nội dung lỗi chứa thông tin nhạy cảm và xác định quyền SDK có trong trang thanh toán.
3. Phân loại bí mật, toàn vẹn, sẵn sàng và phạm vi tác động; giải thích bằng tình huống cụ thể thay vì chỉ gán nhãn.
4. Viết ít nhất một yêu cầu kiểm chứng được cho mỗi nhóm: xác thực, phân quyền, dữ liệu, logging và phục hồi. Chọn các ngưỡng có lý do và nêu cách đo.
5. Xác định bằng chứng nào nhóm phát triển tự thu được, bằng chứng nào phải lấy từ nhà cung cấp và khoảng thiếu nào cần giải quyết trước khi sử dụng.
6. Đề xuất điều kiện kết thúc sử dụng, bao gồm gỡ SDK, ngắt đường gửi dữ liệu, thu hồi quyền hỗ trợ và xử lý dữ liệu đã lưu bên ngoài.

Một kết quả đạt yêu cầu phải nối được từng tài sản với rủi ro và từng yêu cầu với một cách kiểm chứng. Chẳng hạn, yêu cầu “không gửi thông tin thanh toán” cần được cụ thể hóa bằng danh sách trường được phép, xử lý URL và lỗi trước khi gửi, rồi kiểm thử với dữ liệu giả có chứa các giá trị cần loại bỏ. Đồng thời, việc SDK có thể truy cập trang thanh toán cần được đánh giá riêng; lọc payload do ứng dụng chủ động gửi không chứng minh mọi hành vi của mã bên ngoài đã bị giới hạn.
