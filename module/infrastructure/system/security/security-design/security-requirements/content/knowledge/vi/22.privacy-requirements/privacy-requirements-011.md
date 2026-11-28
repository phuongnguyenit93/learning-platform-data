# Third-party processor

## 1. Nhà cung cấp mở rộng ranh giới xử lý dữ liệu

Trong bài này, third-party processor chỉ nhà cung cấp bên ngoài xử lý dữ liệu thay mặt tổ chức trong một phạm vi đã xác định. Ví dụ có thể là dịch vụ quản lý yêu cầu hỗ trợ, lưu trữ hồ sơ hoặc thực hiện một công đoạn nghiệp vụ theo chỉ dẫn.

Yêu cầu quyền riêng tư không chỉ là “nhà cung cấp có bảo mật”. Cần kiểm soát dữ liệu nào được gửi, dùng để làm gì, ai được tiếp cận, bên nào được xử lý tiếp và chuyện gì xảy ra khi kết thúc dịch vụ.

Một tích hợp có thể hoạt động đúng chức năng nhưng không đáp ứng mục tiêu bảo vệ dữ liệu:

- SDK gửi thêm định danh và nội dung ngoài mục đích được duyệt.
- Kho chính ở vùng đã chọn nhưng log, backup hoặc quyền hỗ trợ nằm ngoài phạm vi đã đánh giá.
- Tài khoản nhân viên đã bị thu hồi nội bộ nhưng phiên tại nhà cung cấp vẫn còn.
- Xóa hồ sơ ở ứng dụng không xử lý dữ liệu trong hàng đợi hoặc backup của nhà cung cấp.
- Thỏa thuận giới hạn mục đích nhưng cấu hình sản phẩm bật một tính năng tái sử dụng dữ liệu khác.

Thiết kế yêu cầu bảo mật phải nối mục tiêu quyền riêng tư với quan hệ xử lý, kiến trúc tích hợp, cấu hình và bằng chứng vận hành.

### Cách dùng thuật ngữ

“Bên thứ ba” trong cách nói kỹ thuật không luôn trùng định nghĩa pháp lý. Chẳng hạn, GDPR định nghĩa third party theo cách loại trừ controller, processor và một số người được ủy quyền. Vì vậy, tiêu đề bài học không tự quyết định vai trò pháp lý. [GDPR, Điều 4 trên EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679).

Nhóm có thẩm quyền cần xác định nghĩa vụ theo hoạt động và quy định thực sự áp dụng. Ngôn ngữ tiếng Việt, địa chỉ văn phòng hoặc tên sản phẩm không tự quyết định phạm vi pháp luật.

## 2. Phân vai theo hoạt động, không theo nhãn thương mại

### 2.1. Controller, processor và sub-processor

Trong mô hình thường gặp:

- Controller quyết định mục đích và những phương tiện xử lý thuộc vai trò quyết định của mình.
- Processor xử lý dữ liệu thay mặt controller trong phạm vi chỉ dẫn có thẩm quyền.
- Sub-processor là bên được processor sử dụng để thực hiện một phần hoạt động xử lý trong chuỗi đó.

Một tổ chức có thể có vai trò khác nhau ở các hoạt động khác nhau. Quyết định kỹ thuật vận hành không tự làm processor thành controller; tự dùng dữ liệu cho mục đích riêng cần được đánh giá riêng. [ICO, Xác định vai trò controller hoặc processor](https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/controllers-and-processors/controllers-and-processors/how-do-you-determine-whether-you-are-a-controller-or-processor/).

Không coi mọi bên nhận dữ liệu là processor. Một dịch vụ có quyền quyết định độc lập đối với hoạt động của mình cần được phân tích theo thực tế đó.

### 2.2. Ví dụ nền tảng quản lý ticket

Giả sử tổ chức thuê một dịch vụ để quản lý yêu cầu hỗ trợ khách hàng.

| Hoạt động | Câu hỏi cần làm rõ | Hệ quả thiết kế |
| --- | --- | --- |
| Lưu ticket theo cấu hình của tổ chức | Ai quyết định mục đích và dữ liệu cần xử lý? | Xác định chỉ dẫn, trường dữ liệu, thời hạn và quyền |
| Thuê hạ tầng cho công đoạn xử lý | Bên nào tiếp tục xử lý trong chuỗi? | Kiểm kê sub-processor và phạm vi công việc |
| Nhân sự hỗ trợ của nhà cung cấp mở ticket | Họ tiếp cận khi nào, bằng quyền nào? | Kiểm soát phiên hỗ trợ và audit |
| Dùng nội dung ticket cho sản phẩm riêng | Có mục đích riêng ngoài công việc được giao không? | Đánh giá lại vai trò và phạm vi cho phép |
| Quản lý thông tin thanh toán dịch vụ | Hoạt động này có cùng mục đích với xử lý ticket không? | Tách luồng và chính sách phù hợp |

Một dòng hợp đồng ghi “processor” không làm mọi hoạt động của nhà cung cấp tự thuộc cùng vai trò. Cần đối chiếu điều khoản với hành vi thực tế.

### 2.3. Trách nhiệm chia sẻ phải xuống đến từng kiểm soát

Mô hình trách nhiệm kỹ thuật giúp xác định bên nào quản lý danh tính, backup, log, khóa hoặc cấu hình tenant. Nó không thay thế việc phân vai quyền riêng tư.

Ngược lại, phân vai rõ vẫn chưa cho biết ai phải vô hiệu hóa API key, đổi retention hoặc kiểm tra cấu hình. Các nhiệm vụ đó cần owner cụ thể.

Không để một kiểm soát rơi vào khoảng trống vì cả hai bên đều cho rằng bên còn lại thực hiện.

## 3. Từ mô hình đe dọa đến kết quả cần đạt

### 3.1. Tài sản đi theo dữ liệu

Phạm vi cần xem xét gồm:

- Nội dung nghiệp vụ, dữ liệu cá nhân và tệp đính kèm.
- Định danh, metadata, log, telemetry và dữ liệu chẩn đoán.
- Chỉ mục, dữ liệu trích xuất, báo cáo và sản phẩm dẫn xuất.
- API key, webhook secret, tài khoản quản trị và phiên hỗ trợ.
- Backup, môi trường khôi phục và dữ liệu tạm.
- Chỉ dẫn xử lý, cấu hình và bằng chứng quyết định.

Thay tên bằng token không tự loại khả năng nhận diện hoặc liên kết. Cần đánh giá dữ liệu còn lại và quyền tái liên kết thay vì chỉ nhìn định dạng payload.

### 3.2. Bảng rủi ro minh họa

| Đe dọa hoặc sai sót | Tác động | Kết quả cần đặc tả |
| --- | --- | --- |
| Gửi toàn bộ hồ sơ thay vì trường cần thiết | Mở rộng dữ liệu bị phơi bày | Schema tối thiểu và lọc trước ranh giới gửi |
| Dùng dữ liệu ngoài mục đích | Mất kiểm soát cách sử dụng | Chỉ dẫn rõ, cấu hình tương ứng và quản lý thay đổi |
| Nhầm tenant hoặc tài khoản tích hợp | Lộ dữ liệu sang tổ chức khác | Ràng buộc tenant, danh tính và đích ở phía tin cậy |
| Quyền hỗ trợ rộng, tồn tại thường trực | Đọc hoặc export ngoài nhu cầu | Quyền theo nhiệm vụ, thời hạn và audit phiên |
| Sub-processor đổi ngoài phạm vi đánh giá | Chuỗi xử lý vượt kiểm soát | Inventory, thông báo và quyết định theo cơ chế áp dụng |
| Chỉ xét vị trí kho chính | Bỏ sót log, backup hoặc quyền tiếp cận | Phạm vi vị trí theo từng hoạt động và bản sao |
| Báo sự cố sau khi điều tra hoàn tất | Tổ chức không kịp ứng phó | Trigger và thời hạn thông báo ban đầu rõ |
| Đóng tài khoản nhưng dữ liệu còn | Kết thúc dịch vụ không kết thúc xử lý | Ngừng luồng, thu hồi quyền, trả hoặc xóa dữ liệu |
| Chứng nhận không bao phủ dịch vụ đang dùng | Dựa vào bằng chứng không phù hợp | Đối chiếu sản phẩm, thời kỳ và phần trách nhiệm còn lại |

Mỗi rủi ro cần được nối với một yêu cầu, điểm thực thi, owner và bằng chứng. “Nhà cung cấp tuân thủ bảo mật” chưa đủ làm tiêu chí chấp nhận.

## 4. Lập hồ sơ hoạt động và dòng dữ liệu

### 4.1. Đơn vị quản lý là hoạt động cụ thể

Hồ sơ tích hợp cần ít nhất:

- Dịch vụ, môi trường và tài khoản hoặc tenant.
- Mục đích, loại dữ liệu và nhóm chủ thể liên quan.
- Nguồn dữ liệu, điểm gửi và đầu ra.
- Vai trò từng bên theo hoạt động.
- Nơi lưu, nơi xử lý, backup và truy cập hỗ trợ.
- Sub-processor, tính năng tùy chọn và phụ thuộc.
- Retention, hỗ trợ yêu cầu dữ liệu và kế hoạch kết thúc.
- Owner nghiệp vụ, kỹ thuật, bảo mật và quyền riêng tư.

Không dùng một dòng “đã duyệt nhà cung cấp A” cho mọi sản phẩm, vùng và tính năng của A.

### 4.2. Kiểm kê cả đường không đi qua backend

Dữ liệu có thể được truyền bởi SDK trong trình duyệt, ứng dụng di động, agent, công cụ hỗ trợ hoặc tác vụ export.

Kiểm soát chỉ đặt tại API server không bao phủ SDK gọi thẳng ra ngoài. Cần biết ai có thể bật tích hợp và thay cấu hình theo môi trường.

~~~mermaid
flowchart LR
    A["Ứng dụng và nguồn dữ liệu"] --> B["Kiểm tra mục đích, tenant và payload"]
    B --> C["Processor trong phạm vi được chấp thuận"]
    C --> D["Kho, log và backup"]
    C --> E["Sub-processor đã xác định"]
    F["Truy cập hỗ trợ có kiểm soát"] --> C
    C --> G["Kết quả và yêu cầu vòng đời"]
    G --> H["Xác minh nguồn, quyền và trạng thái"]
~~~

Mỗi luồng phải gắn với danh tính, phạm vi dữ liệu và cách kiểm chứng. Sơ đồ không tự chứng minh kiểm soát đã hoạt động.

## 5. Chuyển thỏa thuận xử lý thành yêu cầu thực thi

### 5.1. Hợp đồng và cấu hình phải nói cùng một việc

Thỏa thuận xử lý dữ liệu thường được gọi là DPA. Không phải mọi DPA có cùng nội dung hoặc tự đáp ứng mọi nguồn yêu cầu.

Ví dụ về một nguồn pháp lý cụ thể: khi GDPR áp dụng, Điều 28 quy định nội dung quan hệ xử lý, chỉ dẫn, điều kiện sử dụng bên xử lý tiếp và thông tin phục vụ kiểm chứng. Cần đối chiếu với điều khoản và hoạt động thực tế, thay vì chỉ kiểm tra có một tệp DPA. [GDPR, Điều 28 trên EUR-Lex](https://eur-lex.europa.eu/eli/reg/2016/679).

Trong thiết kế, có thể lập ánh xạ:

| Nội dung được thống nhất | Yêu cầu kỹ thuật hoặc vận hành | Bằng chứng |
| --- | --- | --- |
| Chỉ xử lý cho mục đích hỗ trợ | Payload và tính năng đúng phạm vi | Schema, cấu hình và kiểm tra luồng |
| Chỉ người được phép tiếp cận | Vai trò và truy cập hỗ trợ có kiểm soát | Quyền, phiên và audit |
| Có thời hạn lưu | Retention cho nội dung và bản sao liên quan | Cấu hình, kết quả và ngoại lệ |
| Hỗ trợ sửa hoặc xóa | API hoặc quy trình được xác thực, theo dõi được | Mã yêu cầu và xác nhận từng nơi |
| Có thông báo sự cố | Trigger, đầu mối, thời hạn và kênh | Diễn tập và lịch sử thông báo |
| Kiểm soát xử lý tiếp | Inventory và quản lý thay đổi | Danh sách, thông báo và quyết định |
| Trả hoặc xóa khi kết thúc | Export, xác minh, ngừng luồng và xử lý bản sao | Kết quả theo phạm vi |

“Không dùng ngoài mục đích” phải được đối chiếu với phân tích tùy chọn, liên kết nhiều sản phẩm, sử dụng nội dung cho mô hình hoặc hỗ trợ thủ công.

Nếu không thể cưỡng chế một phần bằng kỹ thuật phía tổ chức, cần ghi rõ kiểm soát phía nhà cung cấp và bằng chứng có thể nhận. Không trình bày một cam kết như hàng rào kỹ thuật đã được kiểm chứng.

### 5.2. Chỉ dẫn cần chủ thể có thẩm quyền và phiên bản

Cần biết ai được đổi trường gửi, bật tính năng, thay retention hoặc yêu cầu export.

Một nhân viên không tự có quyền đưa toàn bộ hồ sơ vào ticket gửi nhà cung cấp nếu ngoài phạm vi được duyệt. Chỉ dẫn qua dashboard và API cũng phải có quyền và audit phù hợp.

Thay đổi cần gắn với quyết định có thẩm quyền, thời điểm hiệu lực và phạm vi áp dụng. Không để cấu hình cũ được dùng lại mà không biết nó còn phù hợp hay không.

### 5.3. Mâu thuẫn cần có đường giải quyết

Nếu sản phẩm không hỗ trợ xóa từng hồ sơ, không thể chỉ ghi “sẽ hỗ trợ” rồi đánh dấu yêu cầu đã đạt.

Cần xác định phương án khả thi, giới hạn, tác động và người có thẩm quyền giải quyết. Có thể phải giảm dữ liệu gửi, giới hạn tính năng hoặc đổi kiến trúc.

Không dùng ngoại lệ hợp đồng chung để làm biến mất một giới hạn kỹ thuật đang tác động trực tiếp tới mục tiêu quyền riêng tư.

## 6. Đánh giá bảo đảm theo đúng phạm vi sử dụng

### 6.1. Chứng nhận không thay cho đối chiếu phạm vi

Một báo cáo có thể chỉ bao phủ một pháp nhân, sản phẩm, vùng, thời kỳ hoặc nhóm kiểm soát.

Cần xác định:

- Dịch vụ và tính năng đang dùng có thuộc phạm vi không?
- Bằng chứng áp dụng tới thời điểm nào?
- Có phát hiện hoặc ngoại lệ nào liên quan?
- Kiểm soát nào vẫn do tổ chức cấu hình?
- Hoạt động hỗ trợ và sub-processor được bao phủ thế nào?
- Thay đổi sau thời kỳ báo cáo được phát hiện ra sao?

Logo chứng nhận trên trang giới thiệu không đủ chứng minh một tích hợp cụ thể đáp ứng yêu cầu.

### 6.2. Kết hợp ba lớp bằng chứng

1. **Cam kết và mô tả:** thỏa thuận, chỉ dẫn và phạm vi dịch vụ.
2. **Bảo đảm của nhà cung cấp hoặc bên đánh giá:** báo cáo, kết quả và ngoại lệ có phạm vi rõ.
3. **Kiểm chứng phần tổ chức kiểm soát:** payload, quyền, cấu hình tenant, callback và quy trình vòng đời.

Kiểm thử API phía khách hàng không chứng minh mọi backup nội bộ đã được hủy. Báo cáo của nhà cung cấp cũng không chứng minh tổ chức cấu hình đúng quyền của mình.

Phải chỉ ra tiêu chí nào được kiểm thử trực tiếp, tiêu chí nào dựa trên bằng chứng khác và phần nào chưa xác minh.

### 6.3. Hoạt động đánh giá có giới hạn

Kiểm chứng phải trong phạm vi được cho phép và không truy cập dữ liệu tenant khác.

Nếu không quan sát trực tiếp được một kiểm soát, cần bằng chứng thay thế hoặc ghi nhận giới hạn. Không coi thiếu khả năng kiểm thử là kết quả đạt.

Bằng chứng có thể chứa thông tin nhạy cảm về hệ thống. Cần giới hạn người đọc và thời gian lưu tương ứng, tránh biến quy trình đánh giá thành một đường phát tán dữ liệu.

## 7. Tối thiểu hóa dữ liệu tại ranh giới tích hợp

### 7.1. Gửi theo schema được phép

Một ticket có thể chỉ cần mã tham chiếu, nội dung cần giải quyết và phần liên hệ tối thiểu.

Không gửi toàn bộ đối tượng customer chỉ vì thư viện có sẵn hàm chuyển JSON. Payload nên theo allowlist; trường mới không tự được gửi chỉ vì schema nội bộ mở rộng.

Các yêu cầu có thể gồm:

- Loại credential, bí mật và trường không phục vụ mục đích.
- Giới hạn kích thước, loại tệp và nội dung được gửi.
- Lọc hoặc che dữ liệu trước khi rời ranh giới.
- Tách dữ liệu và credential giữa môi trường.
- Kiểm tra telemetry và dữ liệu SDK tự phát sinh.

Lọc sau khi đã gửi hoặc đã ghi log không đáp ứng mục tiêu không chuyển dữ liệu đó ra ngoài.

### 7.2. Nội dung tự do và tệp đính kèm

Người dùng có thể nhập dữ liệu ngoài dự kiến vào mô tả và tệp. Bảo vệ các cột có nhãn sensitive chưa đủ.

Cần quy tắc nhập liệu, xử lý nội dung không được phép và quy trình khi gửi nhầm. Bộ phát hiện tự động có thể bỏ sót; không cam kết phát hiện tuyệt đối nếu không có căn cứ.

Cấp URL đọc tệp trong kho của tổ chức cũng mở một đường tiếp cận. Hết hạn URL chỉ ngừng một cách tải trong tương lai, không xóa bản nhà cung cấp đã tải.

### 7.3. Ràng buộc đúng đích và tenant

Đích, tài khoản và tenant phải lấy từ cấu hình có thẩm quyền hoặc cơ chế đã kiểm chứng.

Cần xét redirect, webhook cấu hình sai và retry. Một request ban đầu tới đúng đích nhưng bị chuyển sang điểm không được phép vẫn có thể làm lộ dữ liệu.

Egress control chỉ bao phủ những đường thực sự đi qua nó. SDK trong trình duyệt, export thủ công và công cụ quản trị cần được xét riêng.

### 7.4. Mã hóa không thay thế giới hạn mục đích

Đường truyền cần xác minh bên nhận; không tắt kiểm tra chứng chỉ để chữa lỗi kết nối.

Mã hóa khi lưu cũng cần được xét. Tuy nhiên, processor phải đọc plaintext để làm việc thì mã hóa đó không ngăn mọi hành vi sử dụng ngoài mục đích.

Khóa do khách hàng quản lý không tự chứng minh nhà cung cấp không thể đọc dữ liệu lúc dịch vụ đang hoạt động. Cần phân tích khả năng thực tế, đường quản trị và quyền vận hành.

“Đã mã hóa” không thay yêu cầu về mục đích, quyền, retention và bằng chứng.

## 8. Danh tính, cách ly và truy cập hỗ trợ

### 8.1. Tách quyền theo thao tác

Phân biệt quyền tạo, đọc, tìm kiếm, export, xóa và quản trị nếu dịch vụ hỗ trợ.

Workload chỉ cần tạo ticket không nên mặc nhiên xuất được toàn tenant. Quản lý API key theo môi trường, phạm vi và vòng đời; không nhúng bí mật có quyền rộng vào ứng dụng công khai.

Nếu sản phẩm không hỗ trợ độ chi tiết cần thiết, phải ghi nhận hạn chế và biện pháp bù. Không gọi quyền là tối thiểu nếu credential thực tế đọc được toàn bộ dữ liệu.

### 8.2. Truy cập nhân sự và phiên hỗ trợ

Yêu cầu cần làm rõ:

- Danh tính cá nhân hoặc workload có thể truy vết.
- Vai trò và phạm vi dữ liệu theo nhiệm vụ.
- Mức xác thực phù hợp rủi ro.
- Điều kiện mở phiên hỗ trợ và thời hạn quyền.
- Audit đọc, export và thay cấu hình.
- Cách thu hồi quyền, phiên và credential còn hiệu lực.

Thu hồi tài khoản nội bộ không tự chứng minh phiên tại nhà cung cấp đã dừng. Cần kiểm tra liên kết danh tính và tài khoản cục bộ còn lại.

### 8.3. Xác minh callback riêng

Webhook là một đường vào có thể thay trạng thái hệ thống.

Cần xác minh nguồn, chống replay theo thiết kế, kiểm tra tenant và ràng buộc event với đối tượng. Chữ ký hợp lệ không tự chứng minh sự kiện được dùng đúng hồ sơ hoặc chuyển trạng thái được phép.

Retry và event sai thứ tự không được ghi đè trạng thái mới bằng dữ liệu cũ. Không ghi nguyên payload nhạy cảm vào log phổ thông.

## 9. Sub-processor, vị trí và thay đổi hoạt động xử lý

### 9.1. Theo dõi chuỗi thực hiện công việc

Một processor có thể dùng dịch vụ hạ tầng, lưu trữ hoặc hỗ trợ để thực hiện công việc được giao.

Inventory cần biết bên nào xử lý loại dữ liệu gì, cho hoạt động nào, ở đâu và theo cơ chế áp dụng. Tên thương mại chung không luôn xác định được pháp nhân hay dịch vụ liên quan.

Quy trình thay đổi cần có:

- Cách nhận thông báo và phiên bản danh sách.
- Người đánh giá tác động theo dữ liệu, mục đích và quyền tiếp cận.
- Cơ chế chấp thuận hoặc phản đối được áp dụng.
- Cách xử lý khi không đạt điều kiện.
- Mốc hiệu lực và trạng thái luồng dữ liệu liên quan.

Không suy rằng mọi thay đổi đều dùng một kiểu phê duyệt. Cần thực hiện đúng cơ chế đã thống nhất và nguồn yêu cầu có thẩm quyền.

### 9.2. Vị trí có nhiều lớp

| Lớp | Câu hỏi cần trả lời |
| --- | --- |
| Kho chính | Nội dung nghiệp vụ được lưu ở đâu? |
| Replica và backup | Có sao chép sang vùng khác không? |
| Log và telemetry | Có chứa dữ liệu liên quan và đi đâu? |
| Xử lý nội dung | Công đoạn thực tế chạy ở vị trí nào? |
| Hỗ trợ | Ai có thể mở dữ liệu từ đâu? |
| Khóa và control plane | Thao tác nào ảnh hưởng khả năng tiếp cận? |
| Phục hồi | Chuyển vùng hoặc restore làm thay đổi phạm vi thế nào? |

Chọn region cho kho chính không trả lời toàn bộ bảng này. Vị trí endpoint nhìn thấy từ phía tổ chức cũng không đủ chứng minh đường xử lý phía sau.

Yêu cầu vị trí hoặc chuyển dữ liệu phải gắn với hoạt động cụ thể và đánh giá theo quy định áp dụng. Không suy một kết luận pháp lý chỉ từ nhãn kỹ thuật như region hoặc global support.

### 9.3. Tính năng mới có thể tạo hoạt động mới

Bật phân tích nội dung, tìm kiếm nâng cao hoặc tính năng mô hình có thể tạo thêm dữ liệu dẫn xuất và thêm bên xử lý.

Các trigger đánh giá lại nên gồm đổi tính năng, mục đích, loại dữ liệu, vùng, sub-processor, quyền hỗ trợ và điều khoản quan trọng.

Trong khi chờ quyết định, cần xác định dữ liệu nào được tiếp tục gửi. Không mặc định mọi tính năng mới kế thừa phạm vi của cấu hình cũ.

## 10. Sửa, xóa và yêu cầu liên quan đến dữ liệu

### 10.1. Quy trình phải đi hết phạm vi được cam kết

Cần biết nhà cung cấp hỗ trợ tìm, xuất, sửa, hạn chế hoặc xóa dữ liệu bằng cách nào.

Quy trình phải xác định:

- Actor và kênh có quyền phát lệnh.
- Tenant, đối tượng và tập dữ liệu.
- Trạng thái, mã theo dõi và mốc thời gian.
- Kho, chỉ mục, tệp và bên xử lý tiếp liên quan.
- Lỗi, ngoại lệ và phần chưa xác minh.
- Bằng chứng để tổ chức phản hồi đúng phạm vi.

Biết mã ticket không tự cấp quyền export hoặc xóa. Quyền yêu cầu và quyền thao tác vẫn cần được kiểm tra.

### 10.2. Ánh xạ định danh phải chính xác

Mã trong hệ thống tổ chức có thể khác mã tại processor.

Cần ánh xạ được bảo vệ, không dựa duy nhất vào thuộc tính có thể đổi hoặc tái sử dụng. Email chung không tự làm một lệnh xóa được phép tác động mọi hồ sơ có cùng email.

Kiểm thử nhiều tenant, nhiều tài khoản và quan hệ đã đổi. Sai đối tượng có thể làm lộ dữ liệu khi export hoặc mất dữ liệu khi xóa.

### 10.3. Retention bao phủ cả bản sao phụ

Không chỉ thời hạn ticket chính: cần xét tệp, bản nháp, log có nội dung, index, export, dữ liệu chẩn đoán và hàng đợi.

Backup không hỗ trợ xóa từng bản ghi cần giới hạn tồn dư được chấp thuận, quyền tiếp cận và điều kiện tái áp dụng trạng thái trước khi restore.

Tắt API key không xóa dữ liệu đã gửi. Xóa ở giao diện không tự chứng minh sub-processor đã xử lý phần liên quan.

Sửa dữ liệu cũng phải tính đến sự kiện đến chậm và import cũ. Consumer không được tự làm giá trị đã đính chính trở lại hiện hành.

### 10.4. Ngoại lệ không được che dưới trạng thái thành công

Nếu còn dữ liệu do một căn cứ lưu giữ được xác định, cần ghi phần nào, mục đích nào còn được phép, owner và điều kiện kết thúc.

Không dùng nhãn “compliance” chung để giữ mọi thứ không thời hạn.

Phân biệt đã xử lý kho hoạt động, còn backup theo phạm vi cho phép và phần chưa xác minh. Xác nhận của processor phải nêu rõ phạm vi thực sự được bao phủ.

## 11. Sự cố, gián đoạn và phối hợp

### 11.1. Chọn trigger thông báo rõ

Hai bên cần thống nhất sự kiện nào phải thông báo, mức thông tin ban đầu và mốc bắt đầu tính thời gian.

“Khi điều tra xong” có thể làm thông báo quá muộn. Mốc “khi có căn cứ về sự cố có thể ảnh hưởng dữ liệu trong phạm vi” phải được định nghĩa và lưu bằng chứng phù hợp.

Thông báo ban đầu, cập nhật tiếp theo và kết luận điều tra là các yêu cầu khác nhau.

Cam kết giữa hai bên không thay các thời hạn nghĩa vụ khác. Nhóm có thẩm quyền phải xác định các đồng hồ áp dụng và cách phối hợp.

### 11.2. Nội dung thông báo đủ dùng

Thông báo ban đầu có thể gồm mã sự cố, dịch vụ, phạm vi có thể bị ảnh hưởng, mốc nhận biết, loại dữ liệu, mức chắc chắn, biện pháp ngăn chặn và đầu mối.

Không chờ số lượng chính xác mới báo nếu trigger đã đạt. Cũng không trình bày ước lượng như kết luận chắc chắn.

Bằng chứng và mẫu dữ liệu nhạy cảm cần kênh, quyền truy cập phù hợp. Không phát tán cả hồ sơ bị ảnh hưởng trong một chuỗi email rộng người nhận.

### 11.3. Có khả năng dừng luồng và thu hồi quyền

Tổ chức cần cách dừng gửi mới, thu hồi credential hoặc hạn chế tính năng.

Dừng luồng tại nguồn không tự làm processor ngừng mọi xử lý dữ liệu đã nhận. Hành động tại processor và sub-processor phải được theo dõi riêng.

Không xóa ngay mọi log trong lúc điều tra nếu làm mất bằng chứng cần thiết. Hành động phải theo quyền và kế hoạch ứng phó, có xét bảo toàn và retention.

### 11.4. Gián đoạn không được mở đường gửi mới ngoài phạm vi

Khi dịch vụ lỗi, có thể từ chối, chờ hoặc đệm trong vùng được bảo vệ có hạn lưu.

Không tự gửi sang nhà cung cấp chưa được đánh giá chỉ vì endpoint cũ không sẵn sàng. Phương án dự phòng cũng cần vai trò, dữ liệu, vị trí và vòng đời được xác định.

Bộ đệm cần giới hạn dung lượng, retry, quyền, thời hạn và cảnh báo. Nó không được trở thành kho dữ liệu nhạy cảm tồn tại vô hạn.

## 12. Thiết kế kết thúc dịch vụ từ trước

### 12.1. Tách các mục tiêu

Kế hoạch kết thúc cần phân biệt:

1. Ngừng tạo thêm dữ liệu tại processor.
2. Lấy lại dữ liệu cần giữ theo mục đích và thẩm quyền.
3. Kiểm tra tính đầy đủ, định dạng và khả năng sử dụng.
4. Thu hồi tài khoản, credential, webhook và quyền hỗ trợ.
5. Xử lý dữ liệu còn tại processor và các bên xử lý tiếp.
6. Đối soát bản sao, ngoại lệ và bằng chứng.

Thứ tự phải phù hợp. Thu hồi mọi quyền trước khi lấy được bản dữ liệu cần giữ có thể làm mất khả năng chuyển dịch vụ.

### 12.2. Export cần được kiểm chứng

Cần biết export bao gồm tệp, quan hệ, metadata và lịch sử nào; có quota hoặc thời gian chuẩn bị ra sao.

Một nút download không chứng minh tổ chức rời được dịch vụ trong thời hạn cần thiết.

Bản export là một bản sao nhạy cảm cần nơi lưu, quyền, kiểm tra toàn vẹn và retention. Không giữ nó mãi chỉ để chứng minh đã kết thúc hợp đồng.

### 12.3. Báo kết quả theo từng phần

Cần biết luồng mới đã dừng, quyền đã thu hồi, bản trả đã xác minh, kho hoạt động đã xử lý và backup còn theo chính sách nào.

Không báo “không còn dữ liệu” khi mới đóng tài khoản. Nếu sub-processor hoặc phần ngoại lệ chưa xác nhận, trạng thái phải thể hiện giới hạn đó.

Diễn tập kết thúc bằng dữ liệu tổng hợp giúp phát hiện hạn chế khi vẫn còn thời gian thay đổi thiết kế.

## 13. Bộ yêu cầu và tiêu chí chấp nhận minh họa

### 13.1. Phạm vi và giả định

Giả sử tổ chức tích hợp dịch vụ quản lý ticket. Phạm vi trực tiếp gồm adapter phía máy chủ, tài khoản tenant tại processor, webhook, quyền nhân viên và các cấu hình đã chọn.

SDK tùy chọn chưa được phép gửi dữ liệu thật. Tệp được gửi chỉ khi phù hợp mục đích hỗ trợ. Những nhóm dữ liệu khác phải được đánh giá trước khi mở rộng.

Các mốc sau chỉ là giả định cho bài học, không phải thời hạn pháp lý mặc định:

- Thu hồi quyền có hiệu lực trong tối đa 15 phút từ khi lệnh hợp lệ được ghi bền.
- Xóa dữ liệu thuộc phạm vi kho hoạt động trong tối đa 24 giờ từ khi processor xác nhận tiếp nhận lệnh hợp lệ.
- Mỗi backup có tuổi tối đa 14 ngày, tính cả thời gian làm bản sao không còn khả năng phục hồi.
- Thông báo sự cố ban đầu trong tối đa 4 giờ từ mốc nhận biết được hai bên định nghĩa.

Cần theo dõi riêng thời gian từ khi tổ chức nhận yêu cầu của chủ thể. Mốc processor tiếp nhận không thay thế toàn bộ thời hạn xử lý đầu cuối.

### 13.2. Ma trận yêu cầu

| ID | Yêu cầu | Tiêu chí chấp nhận |
| --- | --- | --- |
| PP-01 | Mỗi hoạt động có mục đích, vai trò, dữ liệu, owner và cấu hình được xác định trước khi dùng dữ liệu thật | Không có luồng trong inventory thiếu thông tin; tính năng ngoài phạm vi không được tự bật |
| PP-02 | Adapter chỉ gửi trường được phép và áp dụng quy tắc nội dung trước ranh giới gửi | Trường cấu trúc bị cấm không ra ngoài; trường mới không tự xuất hiện trong payload; đường tệp và lỗi tuân thủ quy tắc |
| PP-03 | Đích, tenant và đối tượng được ràng buộc bằng cấu hình và ngữ cảnh tin cậy | Đổi URL, tenant hoặc mã đối tượng không gây gửi hoặc sửa dữ liệu ngoài quyền |
| PP-04 | Workload chỉ tạo ticket không có quyền đọc hoặc export toàn tenant | Các thao tác ngoài quyền bị từ chối; credential thử nghiệm không dùng được ở môi trường thật |
| PP-05 | Thu hồi quyền chặn cả phiên và credential trong tối đa 15 phút từ mốc đã chọn | Phiên đã mở, tài khoản cục bộ và đường API trong phạm vi không tiếp tục truy cập sau giới hạn |
| PP-06 | Thay tính năng, vị trí hoặc chuỗi xử lý tiếp phải đi qua cơ chế quản lý thay đổi áp dụng | Có thông báo, đánh giá, quyết định và mốc hiệu lực; không coi phạm vi cũ tự bao phủ thay đổi |
| PP-07 | Lệnh xóa hợp lệ được thực thi ở kho hoạt động trong tối đa 24 giờ; backup theo giới hạn riêng | Có xác nhận theo nội dung, tệp và kho liên quan; không gộp backup chưa hết vòng đời vào kết quả “đã xóa mọi nơi” |
| PP-08 | Yêu cầu dữ liệu được ràng buộc đúng tenant, chủ thể và mã tại processor | Ca trùng email, mã cũ và tenant khác không export hoặc xóa nhầm; theo dõi được phần còn chờ |
| PP-09 | Sự cố đạt trigger được thông báo ban đầu trong tối đa 4 giờ từ mốc nhận biết đã định nghĩa | Diễn tập chứng minh kênh, đầu mối và mốc; không chờ kết luận điều tra cuối cùng mới thông báo |
| PP-10 | Lỗi dịch vụ không dẫn tới gửi sang đích ngoài phạm vi hoặc lưu plaintext ở vùng bị cấm | Ca timeout, retry, bộ đệm đầy và lỗi lọc không tạo đường hạ mức bảo vệ |
| PP-11 | Kết thúc dịch vụ có export đã kiểm chứng, ngừng luồng, thu hồi quyền và xử lý dữ liệu còn lại | Dữ liệu thử được trả đủ theo manifest; mỗi hạng mục có trạng thái, owner và bằng chứng, không chỉ cờ đóng tài khoản |
| PP-12 | Bằng chứng chỉ kết luận trong phạm vi quan sát hoặc được xác nhận, không giữ bản sao gốc không cần thiết | Phân biệt tiếp nhận, thực thi, ngoại lệ và chưa xác minh; log phổ thông không chứa credential hoặc toàn bộ hồ sơ |

PP-02 không khẳng định bộ lọc phát hiện mọi dữ liệu nhạy cảm trong văn bản tùy ý. Ngoài kiểm soát schema, cần đánh giá cơ chế xử lý nội dung và giới hạn còn lại.

PP-05 phải được đối chiếu với khả năng thực tế của dịch vụ. Tắt tài khoản tại IdP mà vẫn để một API key cục bộ hoạt động không đạt yêu cầu.

### 13.3. Ví dụ đặc tả có truy vết

~~~yaml
requirement_id: PP-07
risk_id: TH-PROCESSOR-06
risk: Dữ liệu được giữ hoặc tái công bố sau khi lệnh xóa hợp lệ đã được xử lý
data_scope:
  - Nội dung ticket trong tenant được yêu cầu
  - Tệp đính kèm và bản sao hoạt động thuộc chính sách
trigger: Processor xác nhận tiếp nhận lệnh hợp lệ qua kênh đã xác thực
maximum_live_deletion_delay_hours: 24
required_behavior:
  - Xử lý đúng đối tượng và phạm vi
  - Theo dõi kết quả từng thành phần
  - Retry không tác động nhầm đối tượng hoặc thế hệ dữ liệu mới
  - Không báo hoàn tất toàn bộ khi còn nơi lỗi hoặc chưa xác minh
backup_policy:
  maximum_snapshot_age_days: 14
  restore_condition: Tái áp dụng trạng thái vòng đời trước khi mở dữ liệu
failure_behavior:
  - Ghi trạng thái xử lý một phần
  - Cảnh báo và chuyển owner theo quy trình
  - Không biến lỗi thành ngoại lệ lưu giữ vô thời hạn
verification:
  - Lệnh sai tenant không tác động dữ liệu
  - Lệnh đúng xử lý dữ liệu tổng hợp trong phạm vi
  - Xác nhận bao phủ kho hoạt động được kiểm kê
  - Bằng chứng backup có mốc và giới hạn rõ
evidence:
  - Mã lệnh và thời điểm tiếp nhận
  - Xác nhận theo từng loại kho
  - Phần ngoại lệ và phần chưa xác minh
owner: Nhóm dữ liệu, nhóm tích hợp và đầu mối processor
~~~

Đây là đặc tả minh họa, không phải cấu hình triển khai. Trong hồ sơ thực tế cần thay phạm vi khái niệm bằng inventory, cơ chế và nguồn bằng chứng cụ thể.

### 13.4. Đừng trộn các đồng hồ

Với lệnh xóa, có thể dùng:

~~~text
T_user_received: tổ chức nhận yêu cầu
T_authorized: yêu cầu đã được xác minh và có quyền thực hiện
T_processor_accepted: processor xác nhận nhận lệnh hợp lệ
T_live_done: hoàn tất trong phạm vi kho hoạt động

Trong ví dụ:
T_live_done - T_processor_accepted <= 24 giờ
~~~

Nếu lệnh bị chờ ba ngày trước khi gửi, chỉ đo 24 giờ tại processor không phản ánh thời gian của người yêu cầu.

Tuổi backup tính từ mốc tạo bản sao, không phải tuổi bản ghi bên trong. Backup mới không được tiếp tục mang dữ liệu đã phải loại khỏi nguồn mà không có phạm vi cho phép rõ.

Không suy một hạn xóa toàn hệ thống bằng cách cộng số giờ và ngày nếu chưa biết mốc chụp cuối cùng, mọi nguồn backup và ngữ nghĩa hủy thực tế.

## 14. Thiết kế kiểm chứng và thu thập bằng chứng

### 14.1. Kiểm tra payload và các đường gửi

Dùng dữ liệu tổng hợp, tenant thử và credential phù hợp phạm vi.

Kiểm tra payload thực sự rời adapter, thay vì chỉ xem đối tượng trong bộ nhớ trước serialize. Bao gồm trường mới, nội dung tự do, tệp, lỗi, retry và telemetry.

Thử trường cấu trúc bị cấm và loại tệp không được phép. Kết quả phải cho thấy dữ liệu không đi qua ranh giới, không chỉ bị ẩn ở giao diện.

Nếu có SDK gọi trực tiếp, phải quan sát đường đó riêng. Kiểm thử backend không bao phủ một luồng trình duyệt không đi qua backend.

### 14.2. Kiểm tra danh tính và cách ly

Thử workload tạo ticket với hành động đọc, export và quản trị. Kiểm tra cả tài khoản cục bộ, phiên đang mở và credential không đi qua cơ chế SSO chính.

Với nhiều tenant, thử ánh xạ sai trong phạm vi được phép kiểm thử bằng dữ liệu tổng hợp. Không truy cập dữ liệu khách hàng khác để chứng minh cách ly.

Webhook cần có ca chữ ký sai, replay, đúng nguồn nhưng sai tenant, đối tượng không thuộc quyền và event sai thứ tự. Mỗi ca kiểm tra một điều kiện khác nhau.

### 14.3. Kiểm tra yêu cầu dữ liệu và retention

Tạo dữ liệu tổng hợp có quan hệ xác định: ticket, tệp và các đối tượng liên quan. Thực hiện yêu cầu hợp lệ rồi đối soát từng nơi thuộc phạm vi.

Ca từ chối vì thiếu quyền không chứng minh dữ liệu đã được xóa. Cần phân biệt nguyên nhân và bằng chứng của từng kết quả.

Với backup hoặc hệ thống nội bộ không thể quan sát trực tiếp, dùng bằng chứng đã xác định trong thỏa thuận đánh giá. Nêu giới hạn thay vì suy từ kết quả API.

Cần kiểm tra restore hoặc bằng chứng quy trình restore không làm dữ liệu đã xử lý hoạt động trở lại. Không đồng nhất lời xác nhận chung với kết quả bao phủ mọi loại bản sao.

### 14.4. Diễn tập sự cố và kết thúc

Một ca diễn tập sự cố nên kiểm tra trigger, đồng hồ, kênh, đầu mối ngoài giờ và cập nhật khi thông tin chưa đầy đủ.

Một ca kết thúc nên kiểm tra manifest export, tính đầy đủ của tệp và quan hệ, ngừng gửi, thu hồi quyền và xác nhận xử lý dữ liệu còn lại.

Không cần dùng dữ liệu thật hoặc gửi thông báo sự cố tới người không thuộc phạm vi diễn tập. Mục tiêu là chứng minh quy trình và khả năng phối hợp.

### 14.5. Đối chiếu hồ sơ với cấu hình

Chọn các điều khoản có hệ quả kỹ thuật và đối chiếu cấu hình đang sử dụng: tính năng tùy chọn, retention, quyền hỗ trợ, region, callback và quyền export.

Khi bằng chứng cũ hoặc không đúng sản phẩm, kết quả phải phản ánh chưa đủ bảo đảm. Không chỉ ghi một ô “có chứng nhận” rồi coi mọi yêu cầu đạt.

Đánh giá không phải một lần kiểm tra duy nhất trước khi triển khai. Cần lặp lại khi có thay đổi liên quan hoặc theo chu kỳ đã được chọn cho mức rủi ro.

## 15. Vận hành, báo cáo và những cách đặc tả dễ sai

### 15.1. Quan sát kết quả thay vì chỉ số lần gọi API

Các số liệu hữu ích gồm:

- Luồng hoặc tính năng chưa có hồ sơ xử lý đầy đủ.
- Payload bị chặn và trường mới phát sinh.
- Quyền rộng, tài khoản không còn owner và credential quá hạn vòng đời.
- Độ trễ thu hồi quyền tại từng đường truy cập.
- Yêu cầu dữ liệu quá hạn, lỗi từng phần và tuổi lớn nhất của phần còn chờ.
- Thay đổi sub-processor, vị trí hoặc điều khoản chưa được đánh giá.
- Sự cố thông báo trễ và đầu mối không liên lạc được.
- Hạng mục kết thúc còn thiếu xác nhận.
- Phần kiểm soát chưa đủ bằng chứng hoặc đã hết thời kỳ bảo đảm.

Nếu cam kết là giới hạn tối đa, số trung bình hoặc p95 không chứng minh mọi trường hợp đáp ứng. Cần theo dõi vi phạm và phạm vi chưa quan sát được.

Không dùng số lệnh gửi thành công thay cho số đối tượng được xử lý đúng. Cũng không coi im lặng từ nhà cung cấp là bằng chứng không có thay đổi hoặc không có sự cố.

### 15.2. Rủi ro còn lại cần quyết định rõ

Một phần kiểm soát phụ thuộc cam kết và hệ thống của nhà cung cấp. Cần ghi điều chưa thể xác minh, mức ảnh hưởng, biện pháp bù và người có thẩm quyền quyết định.

Nếu rủi ro không phù hợp mục tiêu, có thể phải giảm dữ liệu, bỏ tính năng, thay mô hình hoặc chọn phương án khác. Không biến một giới hạn thành kết quả đạt chỉ vì tích hợp đã được xây xong.

### 15.3. Những câu yêu cầu cần sửa

| Cách viết chưa đủ | Vấn đề | Cách làm rõ |
| --- | --- | --- |
| Nhà cung cấp phải bảo mật | Không có đối tượng và phép kiểm chứng | Nêu dữ liệu, kiểm soát, owner và bằng chứng |
| Đã ký DPA nên có thể gửi mọi dữ liệu | Bỏ qua mục đích và cấu hình | Gắn hoạt động, schema và tính năng với phạm vi |
| Mọi nhà cung cấp đều là processor | Nhầm vai trò | Phân tích theo từng hoạt động thực tế |
| Chọn region là dữ liệu không rời vùng | Bỏ sót xử lý, log, hỗ trợ và backup | Kiểm kê từng lớp và bằng chứng vị trí |
| Mã hóa nghĩa là processor không đọc được | Dịch vụ có thể cần plaintext | Phân tích thời điểm và quyền tiếp cận thực tế |
| Có chứng nhận nên tích hợp đã đạt | Phạm vi có thể không khớp | Đối chiếu sản phẩm, thời kỳ và cấu hình |
| Thu hồi SSO là hết mọi truy cập | Phiên hoặc API key có thể còn | Kiểm tra mọi đường credential và tài khoản |
| API trả thành công nghĩa là đã xóa | Có thể mới tiếp nhận lệnh | Theo dõi thực thi theo kho và ngoại lệ |
| Đóng tài khoản là kết thúc xử lý | Dữ liệu và quyền phụ có thể tồn tại | Kế hoạch trả, xóa, thu hồi và đối soát |
| Dịch vụ lỗi thì gửi sang bên khác | Mở chuỗi xử lý chưa được đánh giá | Phương án dự phòng có phạm vi từ trước |
| Chờ điều tra xong mới báo sự cố | Mất thời gian ứng phó | Tách thông báo ban đầu và kết luận cuối |
| Processor chịu trách nhiệm nên tổ chức không cần theo dõi | Mất khả năng chứng minh kiểm soát | Giao owner và theo dõi hiệu lực đầu cuối |

Một đặc tả về processor có thể kiểm chứng phải nối được vai trò, mục đích, dòng dữ liệu, chuỗi xử lý, quyền truy cập và vòng đời. Khi những mối nối này rõ ràng, tổ chức có thể đánh giá việc thuê ngoài đã đáp ứng yêu cầu đến đâu và còn phụ thuộc vào những bảo đảm nào.
