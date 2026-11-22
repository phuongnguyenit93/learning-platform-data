# Chọn luồng cốt lõi từ góc nhìn người dùng hoặc tác nhân bên ngoài

**Chương:** Hệ thống và E2E  
**Phạm vi module:** `VALIDATION_TESTING_STRATEGY`

Kiểm thử hệ thống và kiểm thử đầu cuối (end-to-end, E2E) giúp đánh giá phần mềm trong một bối cảnh gần với cách nó được sử dụng thực tế. Thay vì chỉ gọi một hàm hoặc kiểm tra một thành phần riêng lẻ, nhóm theo dõi một luồng có ý nghĩa từ lúc người dùng hoặc một tác nhân bên ngoài khởi tạo hành động cho đến khi hệ thống tạo ra kết quả cần thiết.

Tuy nhiên, không phải mọi thao tác đều cần một kịch bản E2E. Nếu cố gắng tự động hóa mọi đường đi, bộ kiểm thử sẽ chậm, khó bảo trì và dễ hỏng do những thay đổi nhỏ ở giao diện hoặc môi trường. Nếu chỉ chọn luồng dễ chạy, nhóm có thể bỏ qua các hành trình tạo giá trị chính, các điểm tích hợp quan trọng hoặc những tình huống có hậu quả nghiêm trọng.

Bài học này trình bày cách nhận diện tác nhân, lập bản đồ hành trình, đánh giá mức quan trọng và chọn các luồng cốt lõi cần kiểm thử ở cấp hệ thống hoặc E2E. Mục tiêu là xây dựng một tập kịch bản nhỏ nhưng có giá trị chứng minh rõ ràng đối với người dùng, nghiệp vụ và các hệ thống phụ thuộc.

Sau bài học, người học có thể:

- Phân biệt kiểm thử hệ thống và kiểm thử đầu cuối theo phạm vi cần xác minh.
- Nhận diện người dùng, hệ thống bên ngoài và các tác nhân khởi tạo luồng.
- Mô tả hành trình từ mục tiêu của tác nhân đến kết quả quan sát được.
- Chọn luồng cốt lõi dựa trên giá trị nghiệp vụ, mức sử dụng, rủi ro và phụ thuộc.
- Xác định luồng chính, luồng thay thế, tình huống lỗi và ranh giới cần bao phủ.
- Thiết kế kịch bản E2E ổn định, có dữ liệu và tiêu chí kết quả rõ ràng.
- Duy trì tập luồng kiểm thử khi sản phẩm hoặc hành vi người dùng thay đổi.

## 1. Kiểm thử hệ thống và E2E nhìn vào hành vi tổng thể

### 1.1. Kiểm thử hệ thống (system testing)

Kiểm thử hệ thống đánh giá một hệ thống hoàn chỉnh hoặc một cấu hình hệ thống đã tích hợp so với các yêu cầu chức năng và phi chức năng. Phạm vi có thể bao gồm nhiều dịch vụ, giao diện, cơ sở dữ liệu, cấu hình và thành phần hạ tầng thuộc sản phẩm.

Kiểm thử hệ thống có thể xác minh:

- Các chức năng hoạt động đúng khi các thành phần được tích hợp.
- Hệ thống đáp ứng các yêu cầu hiệu năng, bảo mật, khả năng sử dụng và độ tin cậy đã chọn.
- Các luồng nghiệp vụ và trạng thái được xử lý đúng trong cấu hình triển khai dự kiến.
- Hệ thống xử lý phù hợp khi dịch vụ phụ thuộc hoặc môi trường gặp lỗi.

Kiểm thử hệ thống thường do nhóm kiểm thử thực hiện trên môi trường được kiểm soát. Kịch bản có thể bắt đầu từ API, giao diện, dòng lệnh, thông điệp hoặc một điểm vào khác, tùy mục tiêu xác minh.

### 1.2. Kiểm thử đầu cuối (end-to-end testing)

Kiểm thử E2E xác minh một hành trình xuyên suốt từ điểm khởi đầu có ý nghĩa đối với tác nhân đến kết quả cuối cùng, đi qua các thành phần và ranh giới liên quan. Hành trình thường phản ánh một nhiệm vụ thực tế như đặt hàng, đăng ký tài khoản, chuyển tiền, gửi hồ sơ hoặc đồng bộ một giao dịch từ hệ thống đối tác.

Một kịch bản E2E thường trả lời:

- Ai hoặc hệ thống nào khởi tạo hành động?
- Tác nhân đang cố hoàn thành mục tiêu gì?
- Hệ thống nhận đầu vào qua giao diện hoặc giao thức nào?
- Những thành phần hoặc dịch vụ nào tham gia?
- Kết quả cuối nào chứng minh mục tiêu đã hoàn tất?
- Có tác dụng phụ nào cần xác minh, chẳng hạn bản ghi, thông báo hoặc trạng thái ở hệ thống khác?

Ví dụ, một hành trình mua hàng có thể bắt đầu khi khách hàng tìm sản phẩm, thêm vào giỏ, nhập địa chỉ, áp dụng mã giảm giá, thanh toán và nhận xác nhận đơn hàng. Kịch bản có giá trị khi xác minh được cả kết quả người dùng nhìn thấy và trạng thái nghiệp vụ được lưu đúng.

### 1.3. Quan hệ giữa hai loại kiểm thử

Hai khái niệm có vùng giao nhau và cách gọi có thể khác nhau giữa các tổ chức. Kiểm thử hệ thống thường nhấn mạnh việc đánh giá sản phẩm đã tích hợp so với yêu cầu hệ thống. E2E nhấn mạnh hành trình xuyên suốt từ một điểm vào đến kết quả. Một kịch bản E2E thường là một phần của bộ kiểm thử hệ thống, nhưng kiểm thử hệ thống còn có thể bao gồm các bài kiểm tra không mô phỏng một hành trình người dùng đầy đủ, chẳng hạn đo tải, kiểm tra phục hồi hoặc xác minh cấu hình.

Điểm quan trọng là mô tả rõ phạm vi và mục tiêu của từng kịch bản. Đừng dựa vào tên “system” hay “E2E” để suy đoán một bài kiểm thử đã bao phủ điều gì.

## 2. Bắt đầu từ tác nhân và mục tiêu

Tác nhân (actor) là người dùng, vai trò hoặc hệ thống bên ngoài tương tác với hệ thống đang kiểm thử để đạt một mục tiêu. Tác nhân có thể là con người, dịch vụ đối tác, thiết bị, bộ lập lịch hoặc một hệ thống khác gửi yêu cầu.

### 2.1. Các loại tác nhân thường gặp

- **Người dùng cuối:** khách hàng, nhân viên, quản trị viên hoặc người vận hành.
- **Vai trò nghiệp vụ:** nhân viên phê duyệt, nhân viên hỗ trợ, kế toán hoặc người kiểm soát giao dịch.
- **Hệ thống bên ngoài:** cổng thanh toán, dịch vụ định danh, hệ thống vận chuyển, nhà cung cấp email hoặc nền tảng dữ liệu.
- **Tác nhân tự động:** bộ lập lịch, webhook, tiến trình nền hoặc thiết bị gửi sự kiện.
- **Hệ thống tiêu thụ dữ liệu:** ứng dụng khác gọi API hoặc đọc sự kiện do sản phẩm phát ra.

Một hệ thống có thể có nhiều tác nhân với quyền và mục tiêu khác nhau. Khách hàng muốn hoàn tất thanh toán; nhân viên hỗ trợ muốn tra cứu trạng thái; cổng thanh toán muốn gửi kết quả giao dịch; tiến trình nền muốn đối soát các giao dịch chưa rõ kết quả. Mỗi tác nhân có thể tạo ra một luồng quan trọng riêng.

### 2.2. Mô tả mục tiêu thay vì liệt kê màn hình

Một hành trình nên được mô tả theo mục tiêu mà tác nhân cần đạt, không chỉ theo các màn hình hoặc nút bấm. Ví dụ:

| Mô tả theo giao diện | Mô tả theo mục tiêu của tác nhân |
|---|---|
| Mở trang sản phẩm, bấm nút mua, mở giỏ hàng | Khách hàng chọn sản phẩm và tạo đơn hàng hợp lệ |
| Mở trang quản trị, nhập mã đơn, bấm cập nhật | Nhân viên xác nhận đơn đã được giao sau khi có bằng chứng hợp lệ |
| Gửi POST đến endpoint callback | Cổng thanh toán thông báo kết quả giao dịch để cửa hàng cập nhật trạng thái |
| Chạy một job lúc nửa đêm | Bộ lập lịch khởi tạo quá trình đối soát các giao dịch chưa có kết quả cuối |

Mô tả theo mục tiêu ổn định hơn khi bố cục giao diện thay đổi và giúp nhóm hiểu kết quả nghiệp vụ cần chứng minh. Các bước giao diện vẫn cần thiết khi thiết kế tự động hóa E2E qua trình duyệt, nhưng không nên là định nghĩa duy nhất của hành trình.

### 2.3. Xác định ranh giới hệ thống

Trước khi chọn luồng, hãy xác định hệ thống đang kiểm thử gồm những thành phần nào và thành phần nào được coi là bên ngoài. Một tác nhân có thể tương tác qua giao diện web, API, hàng đợi hoặc webhook. Một dịch vụ thanh toán có thể nằm ngoài quyền kiểm soát của nhóm, nhưng phản hồi của nó vẫn là một phần quan trọng trong hành trình.

Ranh giới rõ giúp quyết định:

- Thành phần nào phải chạy thật trong môi trường kiểm thử.
- Thành phần nào có thể được giả lập trong một số kịch bản.
- Hợp đồng nào cần xác minh riêng.
- Trạng thái nào cần quan sát để chứng minh kết quả.
- Trách nhiệm xử lý lỗi nằm ở hệ thống nào.

Không nên gọi một kịch bản là E2E nếu phần lớn hành trình quan trọng bị thay bằng mock mà không nêu rõ giới hạn. Một kịch bản dùng sandbox hoặc dịch vụ mô phỏng vẫn có thể hữu ích, nhưng cần ghi chính xác ranh giới được kiểm tra và phần nào chưa được xác minh với hệ thống thật.

## 3. Lập bản đồ hành trình và các luồng nghiệp vụ

Sau khi xác định tác nhân và ranh giới, hãy mô tả các hành trình có ý nghĩa. Có thể dùng use case, user journey, sơ đồ hoạt động, sơ đồ tuần tự hoặc bảng sự kiện.

### 3.1. Cấu trúc của một hành trình

Một mô tả hành trình hữu ích thường gồm:

1. **Tác nhân:** ai hoặc hệ thống nào khởi tạo luồng.
2. **Mục tiêu:** kết quả tác nhân muốn đạt.
3. **Điều kiện trước:** trạng thái, quyền, dữ liệu và cấu hình cần có.
4. **Kích hoạt:** hành động hoặc sự kiện bắt đầu luồng.
5. **Luồng chính:** các bước hoặc tương tác dẫn đến kết quả thông thường.
6. **Luồng thay thế:** lựa chọn hợp lệ khác có thể dẫn đến cùng mục tiêu.
7. **Luồng ngoại lệ:** điều gì xảy ra khi dữ liệu sai, phụ thuộc lỗi hoặc quyền không đủ.
8. **Kết quả sau cùng:** trạng thái, dữ liệu, thông báo hoặc sự kiện có thể quan sát.
9. **Rủi ro và phụ thuộc:** điều gì có thể làm luồng thất bại hoặc gây hậu quả đáng kể.

Không phải kịch bản nào cũng cần tài liệu dài. Với luồng đơn giản, một bảng ngắn có thể đủ. Với hành trình có nhiều vai trò hoặc nhánh, sơ đồ giúp nhìn ra điều kiện và phụ thuộc bị bỏ sót.

### 3.2. Ví dụ hành trình đặt hàng

**Tác nhân:** Khách hàng đã đăng nhập.

**Mục tiêu:** Đặt mua sản phẩm còn hàng và nhận xác nhận đơn hàng.

**Điều kiện trước:** tài khoản đang hoạt động; sản phẩm có thể bán; môi trường thanh toán thử nghiệm sẵn sàng.

**Luồng chính:**

1. Khách hàng tìm và chọn sản phẩm.
2. Thêm sản phẩm vào giỏ với số lượng hợp lệ.
3. Nhập địa chỉ giao hàng và chọn phương thức vận chuyển.
4. Áp dụng mã giảm giá nếu đủ điều kiện.
5. Xác nhận tổng tiền và gửi yêu cầu đặt hàng.
6. Hoàn tất thanh toán qua cổng thử nghiệm.
7. Nhận xác nhận đơn hàng và xem trạng thái đơn.

**Luồng thay thế:** khách hàng không dùng mã giảm giá; chọn phương thức vận chuyển khác; thanh toán bằng một phương thức được hỗ trợ khác.

**Luồng ngoại lệ:** mã giảm giá hết hạn; tồn kho thay đổi trước khi xác nhận; cổng thanh toán từ chối hoặc timeout; khách hàng gửi lại yêu cầu.

**Kết quả mong đợi:** đơn hàng được tạo với chi tiết và tổng tiền đúng; chỉ một giao dịch thanh toán hợp lệ được ghi nhận; trạng thái đơn phản ánh kết quả giao dịch; khách hàng nhận thông báo phù hợp.

### 3.3. Ví dụ hành trình do hệ thống bên ngoài khởi tạo

**Tác nhân:** cổng thanh toán gửi webhook đến cửa hàng.

**Mục tiêu:** thông báo kết quả thanh toán để cửa hàng cập nhật giao dịch và đơn hàng.

**Điều kiện trước:** giao dịch đã được tạo; endpoint callback được cấu hình; khóa xác minh chữ ký đã sẵn sàng.

**Luồng chính:**

1. Cổng thanh toán gửi callback có mã giao dịch và trạng thái.
2. Cửa hàng xác minh chữ ký và định danh giao dịch.
3. Hệ thống kiểm tra callback có phù hợp với trạng thái hiện tại không.
4. Cửa hàng cập nhật trạng thái giao dịch và đơn hàng theo quy tắc.
5. Endpoint trả phản hồi xác nhận đã tiếp nhận.

**Luồng ngoại lệ:** chữ ký không hợp lệ; callback trùng; callback đến sai thứ tự; giao dịch không tồn tại; cơ sở dữ liệu tạm thời không khả dụng.

**Kết quả mong đợi:** callback hợp lệ được xử lý an toàn; callback giả mạo bị từ chối; callback lặp không tạo giao dịch trùng hoặc làm trạng thái lùi về trạng thái cũ; lỗi tạm thời có thể được thử lại hoặc đối soát theo hợp đồng.

Hành trình này không có thao tác của con người nhưng vẫn là luồng E2E quan trọng vì nó bắt đầu từ một tác nhân bên ngoài và ảnh hưởng trực tiếp đến trạng thái nghiệp vụ.

## 4. Xác định luồng nào là cốt lõi

Không thể tự động hóa mọi hành trình ở cấp E2E với cùng độ sâu. Cần chọn các luồng có giá trị chứng minh cao nhất dựa trên mục tiêu sản phẩm và rủi ro.

### 4.1. Giá trị nghiệp vụ

Ưu tiên luồng trực tiếp tạo ra hoặc bảo vệ giá trị chính của sản phẩm. Ví dụ:

- Với cửa hàng trực tuyến: tìm sản phẩm, đặt hàng, thanh toán, hủy và hoàn tiền.
- Với hệ thống ngân hàng: đăng nhập, xem số dư, chuyển tiền và tra cứu giao dịch.
- Với nền tảng tuyển dụng: tạo hồ sơ, đăng tuyển, ứng tuyển và xử lý hồ sơ.
- Với hệ thống quản lý nội bộ: tạo yêu cầu, phê duyệt, thực hiện và ghi nhận kết quả.

Một luồng ít được dùng vẫn có thể là cốt lõi nếu nó có tác động pháp lý, tài chính hoặc vận hành lớn.

### 4.2. Tần suất và phạm vi sử dụng

Luồng được sử dụng thường xuyên có nhiều cơ hội ảnh hưởng đến người dùng. Tuy nhiên, tần suất không phải tiêu chí duy nhất. Một luồng quản trị hiếm khi chạy nhưng có quyền thay đổi dữ liệu diện rộng có thể cần ưu tiên cao.

Hãy dùng dữ liệu phân tích sản phẩm, log vận hành, báo cáo hỗ trợ và trao đổi với chủ sản phẩm để hiểu mức sử dụng. Nếu chưa có dữ liệu, ghi rõ đây là giả định và xác minh sau khi có số liệu.

### 4.3. Hậu quả khi luồng thất bại

Đánh giá hậu quả đối với:

- Người dùng không thể hoàn thành nhiệm vụ.
- Dữ liệu bị mất, sai hoặc không nhất quán.
- Tiền, quyền truy cập hoặc thông tin nhạy cảm bị xử lý sai.
- Nghĩa vụ hợp đồng, pháp lý hoặc quy định bị vi phạm.
- Hoạt động vận hành bị gián đoạn hoặc cần xử lý thủ công.
- Các hệ thống phụ thuộc nhận dữ liệu sai và lan truyền lỗi.

Luồng có hậu quả nghiêm trọng cần được kiểm thử ngay cả khi tần suất thấp.

### 4.4. Độ phức tạp và số ranh giới tích hợp

Luồng đi qua nhiều dịch vụ, giao thức, vai trò hoặc kho dữ liệu có nhiều điểm có thể thất bại. Các ranh giới như cổng thanh toán, dịch vụ định danh, hệ thống vận chuyển và webhook thường cần được xem xét riêng.

Số lượng thành phần lớn không tự động làm một luồng quan trọng hơn. Hãy xác định ranh giới nào mang rủi ro và kết quả nào cần chứng minh.

### 4.5. Khả năng đại diện

Một luồng có thể đại diện cho nhiều chức năng dùng chung. Ví dụ, hành trình đăng nhập có thể xác minh xác thực, quản lý phiên, điều hướng và quyền truy cập cơ bản. Tuy nhiên, không nên giả định một hành trình đại diện đã bao phủ mọi vai trò, mọi phương thức xác thực hoặc mọi thiết bị.

Chọn các luồng có thể cung cấp bằng chứng cho nhiều yêu cầu quan trọng mà vẫn có mục tiêu rõ ràng. Tránh ghép quá nhiều mục tiêu vào một kịch bản khiến thất bại khó chẩn đoán.

## 5. Dùng ma trận để xếp hạng ứng viên E2E

Nhóm có thể đánh giá các hành trình theo thang điểm định tính hoặc bán định lượng. Một cách đơn giản là chấm mỗi tiêu chí từ 1 đến 5:

| Tiêu chí | Câu hỏi | Điểm cao thể hiện |
|---|---|---|
| Giá trị nghiệp vụ | Luồng có trực tiếp hỗ trợ mục tiêu sản phẩm không? | Luồng tạo hoặc bảo vệ giá trị chính |
| Mức sử dụng | Người dùng hoặc hệ thống có thực hiện thường xuyên không? | Tần suất hoặc phạm vi sử dụng lớn |
| Hậu quả thất bại | Điều gì xảy ra nếu luồng không hoạt động hoặc cho kết quả sai? | Tổn thất, rủi ro hoặc ảnh hưởng nghiêm trọng |
| Rủi ro tích hợp | Luồng có nhiều phụ thuộc hoặc ranh giới dễ lỗi không? | Có nhiều điểm tích hợp quan trọng |
| Khả năng phát hiện muộn | Lỗi có dễ bị bỏ qua nếu chỉ kiểm thử ở tầng thấp không? | Cần xác minh hành vi xuyên suốt |

Ví dụ xếp hạng sơ bộ:

| Hành trình | Giá trị | Mức sử dụng | Hậu quả | Tích hợp | Khó phát hiện ở tầng thấp | Nhận định |
|---|---:|---:|---:|---:|---:|---|
| Khách hàng đặt và thanh toán đơn | 5 | 5 | 5 | 5 | 4 | Ưu tiên rất cao |
| Khách hàng cập nhật ảnh đại diện | 2 | 3 | 1 | 2 | 1 | Ưu tiên thấp hơn |
| Cổng thanh toán gửi callback | 5 | 4 | 5 | 5 | 5 | Ưu tiên rất cao |
| Nhân viên xem báo cáo tổng hợp | 3 | 3 | 3 | 3 | 2 | Cân nhắc theo rủi ro dữ liệu |
| Quản trị viên thay đổi quyền người dùng | 4 | 2 | 5 | 3 | 4 | Ưu tiên cao dù tần suất thấp |

Điểm số trong bảng chỉ minh họa cách thảo luận. Nếu nhóm cộng điểm hoặc nhân trọng số, cần công bố cách tính và giả định. Không dùng điểm tổng để bù trừ cho yêu cầu bắt buộc hoặc rủi ro nghiêm trọng. Hãy ghi lý do xếp hạng và người chịu trách nhiệm quyết định.

### 5.1. Xác định bộ luồng tối thiểu

Sau khi xếp hạng, chọn một tập luồng đáp ứng các mục tiêu chính:

- Bao phủ các nhiệm vụ tạo giá trị cốt lõi.
- Bao phủ tác nhân và vai trò có quyền khác nhau.
- Bao phủ ranh giới tích hợp quan trọng.
- Bao phủ ít nhất các kết quả thành công và một số tình huống thất bại có hậu quả cao.
- Bao phủ các yêu cầu phi chức năng quan trọng ở cấp hệ thống bằng các bài kiểm tra phù hợp.

Không cần tạo một test E2E cho từng tổ hợp dữ liệu. Nhiều tổ hợp phù hợp hơn với unit test, API test hoặc integration test. E2E nên xác minh hành trình đại diện và kết quả tổng thể.

## 6. Chọn luồng chính, thay thế và ngoại lệ

Một hành trình cốt lõi không chỉ có đường thành công. Nhóm cần xác định các nhánh nào phải được xác minh xuyên suốt và nhánh nào nên được kiểm tra ở tầng khác.

### 6.1. Luồng chính (happy path)

Luồng chính là con đường thông thường khi điều kiện và phụ thuộc đều đáp ứng. Đây thường là kịch bản E2E đầu tiên vì nó xác minh khả năng hoàn thành nhiệm vụ từ đầu đến cuối.

Ví dụ đặt hàng thành công:

- Khách hàng đăng nhập.
- Chọn sản phẩm còn hàng.
- Xác nhận địa chỉ và phương thức giao hàng.
- Thanh toán thành công.
- Nhận mã đơn hàng và trạng thái đã xác nhận.

Kịch bản cần xác minh kết quả cuối và các tác dụng phụ quan trọng, chẳng hạn đơn hàng chỉ được tạo một lần và giao dịch gắn đúng đơn hàng.

### 6.2. Luồng thay thế (alternative flow)

Luồng thay thế là một cách hợp lệ khác để đạt cùng mục tiêu. Ví dụ khách hàng dùng ví điện tử thay cho thẻ, chọn nhận tại cửa hàng thay cho giao hàng hoặc dùng địa chỉ đã lưu thay cho nhập địa chỉ mới.

Chỉ đưa luồng thay thế vào E2E khi nó đại diện cho hành vi quan trọng hoặc có rủi ro khác biệt. Nếu hai phương thức chỉ khác cách gọi API nhưng dùng cùng logic nghiệp vụ, có thể kiểm tra chi tiết ở contract hoặc integration test và giữ một luồng đại diện ở E2E.

### 6.3. Luồng ngoại lệ (exception flow)

Luồng ngoại lệ xảy ra khi điều kiện không đáp ứng hoặc một phụ thuộc gặp lỗi. Ví dụ:

- Người dùng không đủ quyền.
- Tồn kho thay đổi trước khi xác nhận đơn.
- Thanh toán bị từ chối.
- Dịch vụ bên ngoài timeout.
- Callback được gửi lặp hoặc sai thứ tự.
- Phiên đăng nhập hết hạn giữa hành trình.

Hãy chọn các ngoại lệ có tác động đáng kể hoặc ảnh hưởng đến trạng thái xuyên suốt. Những biến thể dữ liệu nhỏ, nhiều trường hợp biên hoặc lỗi nội bộ của một hàm thường phù hợp hơn với tầng kiểm thử thấp hơn.

### 6.4. Hủy, thử lại và phục hồi

Một hành trình thực tế có thể bị gián đoạn. Hãy xác định tác nhân có thể hủy, quay lại, thử lại hoặc tiếp tục từ trạng thái trước hay không. Kiểm tra rằng hành động lặp không tạo dữ liệu trùng và việc phục hồi không làm sai trạng thái.

Ví dụ, sau khi người mua bấm thanh toán nhưng trình duyệt không nhận được phản hồi, người dùng có thể tải lại trang hoặc gửi lại yêu cầu. Hệ thống cần hiển thị trạng thái phù hợp và tránh tạo giao dịch mới nếu thao tác trước đã được xử lý.

## 7. Thiết kế một kịch bản E2E có tiêu chí rõ

Một kịch bản E2E cần có đủ thông tin để người khác hiểu mục tiêu, chạy lại và đánh giá kết quả.

### 7.1. Các trường thông tin nên có

- **Mã và tên:** định danh duy nhất và mô tả mục tiêu.
- **Tác nhân:** vai trò hoặc hệ thống khởi tạo.
- **Mục tiêu nghiệp vụ:** điều tác nhân cần hoàn thành.
- **Phạm vi hệ thống:** các thành phần và dịch vụ tham gia.
- **Điều kiện trước:** trạng thái tài khoản, cấu hình, dữ liệu và môi trường.
- **Các bước chính:** hành động hoặc sự kiện theo trình tự.
- **Kết quả mong đợi:** trạng thái cuối và thông tin quan sát được.
- **Bằng chứng:** mã giao dịch, log, báo cáo, sự kiện hoặc ảnh chụp phù hợp.
- **Dọn dẹp:** cách khôi phục dữ liệu và trạng thái để lần chạy sau độc lập.
- **Rủi ro và giới hạn:** phụ thuộc nào được giả lập, tình huống nào chưa được bao phủ.

### 7.2. Ví dụ: khách hàng hoàn tất một đơn hàng

| Thành phần | Mô tả |
|---|---|
| Mã | `E2E-ORDER-001` |
| Tác nhân | Khách hàng đã đăng nhập |
| Mục tiêu | Đặt một sản phẩm và thanh toán thành công |
| Điều kiện trước | Sản phẩm có tồn kho; tài khoản thử nghiệm hoạt động; sandbox thanh toán sẵn sàng |
| Bước 1 | Mở trang sản phẩm và thêm một đơn vị vào giỏ |
| Bước 2 | Chọn địa chỉ và phương thức giao hàng hợp lệ |
| Bước 3 | Xác nhận tổng tiền và gửi yêu cầu đặt hàng |
| Bước 4 | Hoàn tất thanh toán bằng phương thức thử nghiệm |
| Bước 5 | Mở trang đơn hàng và kiểm tra xác nhận |
| Kết quả mong đợi | Một đơn hàng được tạo; tổng tiền đúng; giao dịch thành công liên kết đúng đơn; trạng thái đơn phù hợp; xác nhận được hiển thị hoặc gửi theo yêu cầu |
| Bằng chứng | Mã đơn, mã giao dịch sandbox, trạng thái cuối và liên kết báo cáo lần chạy |

Kịch bản này xác minh hành trình của khách hàng. Các phép tính chi tiết về thuế, phí và chiết khấu vẫn nên được kiểm tra kỹ bằng unit test; E2E xác minh rằng kết quả được hiển thị và lưu đúng trong luồng tích hợp.

### 7.3. Ví dụ: hệ thống nhận callback thanh toán

| Thành phần | Mô tả |
|---|---|
| Mã | `E2E-PAYMENT-002` |
| Tác nhân | Cổng thanh toán sandbox |
| Mục tiêu | Thông báo giao dịch thành công để cửa hàng cập nhật đơn hàng |
| Điều kiện trước | Có giao dịch đang chờ; endpoint callback và khóa xác minh được cấu hình |
| Bước 1 | Sandbox gửi callback hợp lệ cho giao dịch |
| Bước 2 | Cửa hàng xác minh chữ ký và định danh giao dịch |
| Bước 3 | Cửa hàng cập nhật giao dịch và đơn hàng |
| Bước 4 | Gửi lại cùng callback để kiểm tra xử lý lặp an toàn |
| Kết quả mong đợi | Giao dịch và đơn hàng có trạng thái phù hợp; callback lặp không tạo giao dịch thứ hai hoặc gửi thông báo trùng; endpoint trả phản hồi theo hợp đồng |
| Bằng chứng | Payload đã loại bỏ dữ liệu nhạy cảm, mã giao dịch, log tương quan và trạng thái đọc lại |

Nếu sandbox không hỗ trợ gửi callback trùng theo cách kiểm soát, có thể dùng một công cụ kiểm thử hợp đồng hoặc bộ phát sự kiện được kiểm soát cho nhánh đó. Cần ghi rõ phần nào được thực hiện qua sandbox và phần nào dùng mô phỏng.

## 8. Xác định kết quả có thể quan sát

Một kịch bản E2E không thể kết luận đạt chỉ vì không có lỗi hiển thị trên trình duyệt. Nhiều sai lệch chỉ xuất hiện ở trạng thái lưu trữ, hệ thống phụ thuộc hoặc tác dụng phụ.

Tùy luồng, kết quả có thể gồm:

- Thông báo hoặc trạng thái người dùng nhìn thấy.
- Mã định danh nghiệp vụ như mã đơn hàng, mã hồ sơ hoặc mã giao dịch.
- Trạng thái cuối trong hệ thống và các bản ghi liên quan.
- Sự kiện hoặc thông điệp được phát ra đúng số lần.
- Phản hồi từ hệ thống bên ngoài và trạng thái đối soát.
- Log hoặc số liệu có mã tương quan để truy vết.
- Thời gian hoàn tất hoặc tỷ lệ thành công nếu đó là yêu cầu chất lượng.

Hãy chọn oracle kiểm thử (test oracle) phù hợp: nguồn hoặc quy tắc dùng để xác định kết quả đúng. Ví dụ, nội dung trên giao diện có thể được đối chiếu với API đọc đơn hàng; trạng thái giao dịch có thể được đối chiếu với bản ghi nghiệp vụ và phản hồi sandbox. Không nên dựa vào cùng một thành phần có lỗi để vừa tạo kết quả vừa làm nguồn duy nhất xác nhận kết quả.

### 8.1. Tránh xác minh quá nông

Ví dụ, chỉ kiểm tra thông báo “Thanh toán thành công” có thể bỏ sót trường hợp:

- Không có giao dịch được lưu.
- Giao dịch được gắn nhầm đơn hàng.
- Một giao dịch bị ghi hai lần.
- Đơn hàng vẫn ở trạng thái chờ thanh toán.
- Thông báo được gửi lặp.

Với luồng có tác động tài chính, cần kiểm tra các trạng thái và liên kết dữ liệu quan trọng, không chỉ nội dung giao diện.

### 8.2. Tránh phụ thuộc vào chi tiết giao diện không ổn định

Khi tự động hóa qua trình duyệt, nên định vị phần tử theo vai trò, nhãn hoặc thuộc tính ổn định mà sản phẩm cung cấp. Tránh phụ thuộc vào vị trí pixel, cấu trúc DOM quá sâu hoặc thời gian chờ cố định không có căn cứ. Nếu mục tiêu là xác minh API hoặc trạng thái nghiệp vụ, có thể dùng API hoặc giao diện quan sát phù hợp thay vì thao tác qua UI cho mọi bước.

Việc dùng API để kiểm tra hậu điều kiện không làm mất giá trị của hành trình E2E qua UI, miễn là điểm khởi đầu và phạm vi tương tác vẫn phản ánh mục tiêu cần xác minh. Hãy ghi rõ cách tạo hành động và cách quan sát kết quả.

## 9. Chọn ranh giới thực và mô phỏng phụ thuộc

Một luồng E2E thường đi qua nhiều hệ thống, nhưng không nhất thiết phải phụ thuộc vào tất cả dịch vụ sản xuất trong mọi lần chạy. Cần cân bằng giữa tính đại diện và độ ổn định.

### 9.1. Khi nên dùng thành phần thật

Ưu tiên thành phần thật trong môi trường kiểm thử khi mục tiêu cần xác minh phụ thuộc vào hành vi của nó, ví dụ:

- Tích hợp ứng dụng với cơ sở dữ liệu và migration.
- Xác thực, phân quyền và quản lý phiên.
- Cấu hình định tuyến, gateway hoặc cơ chế xác minh chữ ký.
- Luồng ghi dữ liệu và giao tiếp giữa các dịch vụ thuộc quyền kiểm soát.
- Hành vi của message broker nếu thứ tự hoặc xác nhận thông điệp là yêu cầu.

### 9.2. Khi có thể dùng sandbox hoặc mô phỏng

Sandbox hoặc mô phỏng có thể phù hợp khi:

- Dịch vụ ngoài có chi phí hoặc giới hạn gọi cao.
- Không thể tạo giao dịch thật trong kiểm thử tự động.
- Cần tái tạo lỗi hiếm như timeout, từ chối hoặc phản hồi sai định dạng.
- Cần kết quả ổn định và có thể lặp lại.
- Dịch vụ bên ngoài không cung cấp môi trường thử nghiệm đủ tin cậy.

Mô phỏng phải bám sát hợp đồng đã thống nhất và được kiểm tra riêng. Một mock tự tạo có thể không phản ánh chính xác hành vi nhà cung cấp. Vì vậy, nên có một số kiểm thử hợp đồng hoặc kiểm thử sandbox để xác minh tương thích, cùng với các kịch bản mô phỏng lỗi.

### 9.3. Ghi rõ giới hạn phạm vi

Trong báo cáo, nêu rõ:

- Thành phần nào chạy thật.
- Thành phần nào dùng sandbox, stub hoặc fake.
- Hợp đồng nào đã được xác minh.
- Những hành vi nào của nhà cung cấp chưa được kiểm tra.
- Rủi ro còn lại và hoạt động xác minh bổ sung nếu cần.

Điều này giúp người đọc không hiểu nhầm một kịch bản chạy thành công với sandbox là bằng chứng đầy đủ cho mọi tình huống trên hệ thống sản xuất.

## 10. Dữ liệu, tài khoản và môi trường cho luồng E2E

Luồng E2E thường chạm đến nhiều thành phần và tạo ra trạng thái lâu dài. Nếu dữ liệu dùng chung hoặc môi trường không ổn định, kết quả có thể khó tái lập.

### 10.1. Dữ liệu riêng cho mỗi lần chạy

Nên tạo dữ liệu có định danh riêng cho mỗi lần chạy hoặc mỗi worker:

- Tài khoản thử nghiệm theo vai trò.
- Sản phẩm và tồn kho được chuẩn bị có kiểm soát.
- Mã khuyến mãi với thời hạn rõ ràng.
- Đơn hàng và giao dịch dùng mã tương quan duy nhất.
- Địa chỉ, phương thức giao hàng và phương thức thanh toán thử nghiệm.

Tránh để nhiều kịch bản đồng thời sửa cùng một tài khoản, mã giảm giá hoặc sản phẩm nếu không có cơ chế cô lập. Dọn dẹp dữ liệu sau khi chạy hoặc dùng dữ liệu có vòng đời được quản lý.

### 10.2. Quản lý tài khoản và bí mật

Tài khoản thử nghiệm cần quyền tối thiểu đủ để thực hiện luồng. Bí mật truy cập phải được lưu trong cơ chế quản lý bí mật của môi trường, không ghi trong mã nguồn, log hoặc báo cáo. Với luồng quản trị, cần dùng tài khoản riêng và xác minh quyền thực tế.

### 10.3. Kiểm soát thời gian và tác vụ nền

Một hành trình có thể phụ thuộc vào email, webhook, hàng đợi hoặc tác vụ chạy theo lịch. Thay vì chờ một khoảng thời gian cố định dài, hãy chờ một điều kiện có thể quan sát với thời hạn tối đa rõ ràng. Nếu hệ thống xử lý bất đồng bộ, cần xác định trạng thái trung gian và điều kiện kết thúc.

Với tác vụ theo lịch, có thể cung cấp cơ chế kích hoạt trong môi trường kiểm thử hoặc điều khiển đồng hồ nếu kiến trúc hỗ trợ. Cần kiểm tra hành vi thực của bộ lập lịch ở phạm vi phù hợp, nhưng tránh làm bộ test phụ thuộc vào thời điểm đồng hồ thật một cách khó kiểm soát.

### 10.4. Dọn dẹp và khôi phục

Sau khi chạy, xóa hoặc vô hiệu hóa dữ liệu thử nghiệm theo chính sách, giải phóng tài nguyên và khôi phục cấu hình dùng chung. Nếu không thể dọn dẹp hoàn toàn, cần dùng tiền tố định danh và quy trình thu gom rõ ràng. Không để một lần chạy thất bại làm hỏng dữ liệu của lần chạy sau.

## 11. Tổ chức bộ kiểm thử hệ thống và E2E

Một bộ kiểm thử tốt không chỉ là danh sách các kịch bản được chọn. Nó cần có cấu trúc để nhóm biết luồng nào chạy ở thời điểm nào, luồng nào chặn phát hành và cách xử lý khi một phụ thuộc không sẵn sàng.

### 11.1. Phân nhóm theo mục tiêu

Có thể tổ chức theo các nhóm:

- **Smoke test:** một số kiểm tra nhanh để xác nhận bản dựng và môi trường đủ sẵn sàng cho kiểm thử sâu hơn.
- **Luồng cốt lõi:** hành trình chính tạo giá trị cho người dùng hoặc hệ thống bên ngoài.
- **Luồng quyền hạn:** hành động quan trọng theo vai trò, bao gồm cả trường hợp bị từ chối.
- **Luồng tích hợp:** trao đổi với các hệ thống bên ngoài hoặc dịch vụ quan trọng.
- **Luồng phục hồi:** thử lại, hủy, timeout, callback lặp và tiếp tục sau lỗi.
- **Kiểm thử phi chức năng:** hiệu năng, bảo mật, khả năng sử dụng, khả năng tương thích và độ tin cậy ở cấp hệ thống.

Không phải mọi nhóm đều cần được triển khai dưới dạng E2E UI. Một số bài kiểm tra cấp hệ thống phù hợp hơn với API, công cụ tải, công cụ bảo mật hoặc kiểm tra vận hành.

### 11.2. Phân tầng thời gian chạy

Ví dụ về cách sắp xếp:

| Thời điểm | Nhóm kiểm thử | Mục tiêu |
|---|---|---|
| Sau triển khai môi trường | Smoke test | Xác nhận hệ thống và phụ thuộc chính sẵn sàng |
| Mỗi bản dựng ứng viên | Một số luồng cốt lõi ngắn | Phát hiện nhanh lỗi làm hỏng hành trình quan trọng |
| Theo lịch hoặc trước phát hành | Bộ E2E mở rộng và system test | Bao phủ vai trò, nhánh thay thế và rủi ro cao |
| Theo kế hoạch chuyên biệt | Hiệu năng, bảo mật, phục hồi và tương thích | Đánh giá thuộc tính chất lượng cần điều kiện riêng |

Các luồng chặn phát hành phải được xác định trước. Nếu một dịch vụ ngoài không sẵn sàng, nhóm cần phân biệt test bị chặn do môi trường với lỗi sản phẩm; không tự động đánh dấu đạt.

### 11.3. Giữ mỗi kịch bản có một mục tiêu chính

Một kịch bản có thể kiểm tra nhiều kết quả liên quan, nhưng nên có một mục tiêu chính. Nếu một kịch bản vừa đăng ký, vừa mua hàng, vừa hoàn tiền, vừa thay đổi quyền, khi thất bại sẽ khó xác định phần nào gây lỗi. Hãy chia thành các hành trình độc lập và tái sử dụng bước chuẩn bị khi phù hợp.

### 11.4. Không nhân bản cùng một kiểm tra ở nhiều tầng

Một số hành vi cần được kiểm tra ở nhiều tầng vì mỗi tầng cung cấp bằng chứng khác nhau. Tuy nhiên, không nên lặp lại hàng trăm tổ hợp dữ liệu ở E2E nếu chúng đã được kiểm tra tốt ở unit hoặc API test. Giữ E2E cho hành trình và tích hợp có ý nghĩa, dùng tầng thấp hơn để kiểm tra chi tiết.

## 12. Đánh giá độ ổn định và khả năng bảo trì

E2E thường có nhiều phụ thuộc hơn các tầng kiểm thử thấp. Bộ kiểm thử có thể trở nên không đáng tin nếu phụ thuộc vào dữ liệu chia sẻ, thời gian chờ cứng, trạng thái môi trường hoặc chi tiết giao diện thay đổi thường xuyên.

### 12.1. Tránh chờ theo thời gian cố định

Thay vì luôn chờ 10 giây sau khi bấm nút, hãy chờ trạng thái cụ thể như mã đơn hàng xuất hiện, API trả về trạng thái cuối hoặc sự kiện được ghi nhận. Đặt thời hạn tối đa và cung cấp thông tin chẩn đoán khi hết thời gian.

### 12.2. Xử lý tính bất đồng bộ

Với webhook, email hoặc hàng đợi, kết quả có thể đến sau hành động khởi tạo. Kịch bản cần xác định điều kiện hoàn tất và cách truy vấn trạng thái. Không nên kiểm tra ngay lập tức rồi kết luận thất bại nếu hệ thống được thiết kế để xử lý bất đồng bộ.

### 12.3. Theo dõi test không ổn định

Flaky test là kiểm thử có thể lúc đạt, lúc thất bại dù mã và điều kiện đầu vào không thay đổi đáng kể. Nguyên nhân thường gồm race condition, dữ liệu dùng chung, phụ thuộc mạng, đồng hồ, thứ tự chạy hoặc locator giao diện không ổn định.

Hãy ghi nhận số lần chạy, môi trường, log, ảnh chụp và mã tương quan. Phân loại nguyên nhân, giao người xử lý và theo dõi thời hạn. Không nên chạy lại vô hạn cho đến khi test xanh rồi bỏ qua thất bại đầu tiên.

### 12.4. Bảo trì khi giao diện thay đổi

Nếu mục tiêu là xác minh nhiệm vụ người dùng, hãy ưu tiên locator theo vai trò và nhãn có ý nghĩa. Khi giao diện thay đổi nhưng hành vi nghiệp vụ không đổi, chỉ cập nhật phần tương tác cần thiết. Nếu hành trình hoặc kết quả nghiệp vụ thay đổi, cần rà soát lại mục tiêu và tiêu chí của kịch bản.

## 13. Duy trì bản đồ luồng theo thay đổi sản phẩm

Danh sách luồng cốt lõi không cố định mãi mãi. Sản phẩm có thể thêm tác nhân, thay đổi quy trình, tích hợp nhà cung cấp mới hoặc chuyển một nhiệm vụ sang kênh khác.

Hãy xem xét bản đồ luồng khi:

- Có tính năng mới hoặc thay đổi hành trình chính.
- Có vai trò hoặc quyền hạn mới.
- Thêm, bỏ hoặc thay thế hệ thống bên ngoài.
- Dữ liệu sử dụng cho thấy một luồng mới trở nên quan trọng.
- Sự cố thực tế cho thấy một luồng chưa được kiểm thử hoặc một nhánh bị bỏ sót.
- Cam kết chất lượng, quy định hoặc rủi ro thay đổi.

Với mỗi luồng, duy trì chủ sở hữu, mức ưu tiên, môi trường, trạng thái tự động hóa và ngày rà soát gần nhất. Khi loại bỏ một kịch bản, ghi lý do và xác định bằng chứng nào khác đang bảo vệ hành vi đó.

## 14. Những sai lầm thường gặp

### 14.1. Chọn kịch bản theo màn hình thay vì mục tiêu

Một danh sách thao tác giao diện có thể bỏ qua lý do người dùng thực hiện chúng và kết quả nghiệp vụ cần đạt. Hãy bắt đầu từ tác nhân và mục tiêu, sau đó mới quyết định cách tương tác.

### 14.2. Chỉ kiểm tra người dùng cuối

Webhook, bộ lập lịch, dịch vụ đối tác và ứng dụng tiêu thụ API cũng là tác nhân. Nếu chúng tạo hoặc thay đổi trạng thái quan trọng, cần đưa luồng của chúng vào bản đồ kiểm thử.

### 14.3. Chỉ kiểm tra đường thành công

Luồng thành công xác minh khả năng hoàn thành nhiệm vụ, nhưng không bao phủ từ chối, timeout, thử lại, hủy hoặc phục hồi. Chọn các ngoại lệ có hậu quả đáng kể và kiểm tra ở tầng phù hợp.

### 14.4. Dùng một kịch bản E2E để chứng minh mọi thứ

Một hành trình mua hàng thành công không chứng minh mọi phép tính, mọi quyền và mọi tổ hợp dữ liệu đều đúng. Cần kết hợp unit, API, integration, contract, system và E2E test theo mục tiêu.

### 14.5. Giả lập quá nhiều nhưng vẫn tuyên bố bao phủ toàn bộ

Nếu cổng thanh toán, cơ sở dữ liệu hoặc hệ thống định danh đều được mock, kịch bản không chứng minh các ranh giới đó hoạt động thật. Ghi rõ phần mô phỏng và bổ sung kiểm thử hợp đồng hoặc sandbox phù hợp.

### 14.6. Chọn luồng chỉ vì dễ tự động hóa

Luồng đơn giản và ổn định có thể hữu ích cho smoke test, nhưng không nên chiếm hết nguồn lực nếu các rủi ro lớn hơn nằm ở luồng khác. Xếp hạng theo giá trị và hậu quả, không chỉ theo độ dễ viết test.

### 14.7. Chỉ kiểm tra thông báo thành công

Thông báo trên giao diện không đủ chứng minh dữ liệu và tác dụng phụ đúng. Hãy kiểm tra trạng thái cuối, liên kết định danh và các sự kiện quan trọng.

### 14.8. Để dữ liệu test phụ thuộc lẫn nhau

Kịch bản chạy trước có thể làm thay đổi tồn kho, mã giảm giá hoặc tài khoản khiến kịch bản sau thất bại. Tạo dữ liệu riêng, cô lập trạng thái và dọn dẹp rõ ràng.

## 15. Danh sách rà soát khi chọn luồng cốt lõi

Trước khi đưa một hành trình vào bộ kiểm thử hệ thống hoặc E2E, hãy kiểm tra:

- [ ] Tác nhân và mục tiêu nghiệp vụ được xác định rõ.
- [ ] Ranh giới hệ thống và các thành phần tham gia được mô tả.
- [ ] Điều kiện trước, luồng chính và kết quả cuối có thể quan sát.
- [ ] Luồng thay thế và ngoại lệ có hậu quả cao đã được xem xét.
- [ ] Giá trị nghiệp vụ, mức sử dụng và hậu quả thất bại được đánh giá.
- [ ] Các ranh giới tích hợp quan trọng được xác định.
- [ ] Tầng kiểm thử được chọn phù hợp với câu hỏi cần chứng minh.
- [ ] Thành phần thật, sandbox và mô phỏng được phân biệt rõ.
- [ ] Dữ liệu, tài khoản, thời gian và môi trường có thể tái lập.
- [ ] Kết quả được xác minh qua nguồn bằng chứng phù hợp, không chỉ qua thông báo giao diện.
- [ ] Kịch bản có mục tiêu chính, thời hạn và thông tin chẩn đoán rõ.
- [ ] Có chủ sở hữu và điều kiện rà soát lại khi sản phẩm thay đổi.

## 16. Kết luận

Chọn luồng cốt lõi cho kiểm thử hệ thống và E2E cần bắt đầu từ tác nhân và mục tiêu mà họ muốn đạt, bao gồm cả người dùng, vai trò nghiệp vụ và hệ thống bên ngoài. Nhóm cần xác định ranh giới hệ thống, mô tả hành trình chính cùng các nhánh có ý nghĩa, rồi xếp hạng theo giá trị nghiệp vụ, mức sử dụng, hậu quả thất bại và rủi ro tích hợp.

Một bộ E2E có giá trị không cần chứa mọi tổ hợp dữ liệu. Nó cần chứng minh các hành trình quan trọng từ điểm khởi đầu đến kết quả cuối bằng dữ liệu, môi trường và oracle phù hợp. Kết hợp các luồng E2E đại diện với unit, integration, contract và các kiểm thử hệ thống chuyên biệt sẽ tạo bằng chứng đầy đủ hơn mà vẫn giữ bộ kiểm thử ổn định và có thể bảo trì.
