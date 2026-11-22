# Đọc lại cấu trúc và kiểm tra hành vi sau mỗi phần được chuyển đổi

Khi tiếp nhận một hệ thống Java đã chạy nhiều năm, việc đầu tiên không phải là đổi tên lớp hoặc viết lại những phương thức trông phức tạp. Cần hiểu **cấu trúc đang tồn tại, các đường gọi thực tế, dữ liệu được sở hữu ở đâu và hành vi nào đang được người dùng hoặc hệ thống khác phụ thuộc**. Nếu chuyển đổi một phần mà không kiểm tra lại những mối quan hệ này, một thay đổi có vẻ nhỏ có thể làm hỏng một job theo lịch, một client cũ, một quy tắc dữ liệu hoặc một bước phục hồi sau lỗi.

Trong chương **Mã hiện hữu** của module **CODE_QUALITY_FUNDAMENTALS**, mục tiêu là cải thiện mã nguồn để nó **đáng tin cậy, dễ hiểu và dễ thay đổi** mà vẫn giữ được những hành vi cần thiết. Bài này trình bày cách đọc cấu trúc trước khi sửa, chia chuyển đổi thành những phần có thể kiểm chứng, rồi **đọc lại cấu trúc và xác minh hành vi sau từng phần**, thay vì chỉ kiểm tra một lần ở cuối dự án.

> Mỗi lát cắt chuyển đổi phải để lại hai loại bằng chứng: cấu trúc sau thay đổi vẫn có chủ đích và hành vi cần giữ vẫn đúng theo hợp đồng.

## 1. Vì sao phải hiểu mã hiện hữu trước khi chuyển đổi?

Mã hiện hữu (*existing code* hoặc *legacy code*) không nhất thiết là mã cũ hoặc mã xấu. Đó là mã đã tồn tại trong một hệ thống có người dùng, dữ liệu, tích hợp, lịch sử phát hành và những giả định có thể chưa được ghi thành tài liệu.

Một lớp có thể trông như chỉ tính tổng đơn hàng, nhưng các caller đang dựa vào những hành vi không dễ thấy:

- Phương thức trả về tổng đã bao gồm phí hay chưa?
- Khi không tìm thấy khách hàng, phương thức trả null, trả Optional.empty hay ném exception?
- Phương thức có ghi log, cập nhật cache hoặc tạo bản ghi phụ không?
- Có job chạy ban đêm gọi phương thức này với dữ liệu lịch sử không?
- Có client bên ngoài phụ thuộc tên trường JSON hoặc mã lỗi cũ không?
- Một thao tác có được gọi lại sau timeout hay không?
- Trạng thái đơn được cập nhật trước hay sau khi gửi thông điệp?

Nếu chỉ nhìn một tệp, reviewer có thể không thấy những ràng buộc ấy. **Mã hiện hữu cần được đọc như một phần của hệ thống đang hoạt động**, không phải một ví dụ cô lập.

### 1.1. Phân biệt ba mục tiêu của thay đổi

Trước khi sửa, cần xác định công việc thuộc loại nào:

| Loại thay đổi | Mục tiêu | Điều cần chứng minh |
| --- | --- | --- |
| **Refactor** | Cải thiện cấu trúc bên trong | Hành vi quan sát được theo hợp đồng vẫn giữ |
| **Bug fix** | Sửa hành vi hiện tại không đáp ứng yêu cầu | Hành vi mới khớp oracle đã xác nhận và tác động được kiểm soát |
| **Feature/change request** | Bổ sung hoặc thay đổi khả năng sản phẩm | Hợp đồng mới được xác định, tương thích và kiểm thử |

Một PR có thể kết hợp nhiều loại thay đổi, nhưng cần chỉ rõ ranh giới. Nếu vừa tách một chính sách tính phí vừa đổi ngưỡng nghiệp vụ, một test thất bại sẽ khó phân biệt lỗi do refactor hay do quy tắc mới.

**Refactor không đồng nghĩa bảo tồn mọi hành vi đang quan sát được nếu hành vi đó đã được xác nhận là lỗi.** Khi phát hiện lỗi hiện trạng, hãy ghi lại sự khác nhau giữa hành vi cũ và hành vi mục tiêu, rồi xử lý như một thay đổi có chủ đích.

### 1.2. Không đánh giá chất lượng chỉ bằng tuổi đời hoặc vẻ ngoài

Một module mười năm tuổi nhưng có hợp đồng ổn định, test đáng tin cậy và ít thay đổi có thể không cần đại tu. Một module mới viết nhưng thường xuyên phát sinh lỗi do phụ thuộc vòng, trạng thái dùng chung hoặc thiếu kiểm tra đầu vào vẫn cần cải thiện.

Ưu tiên dựa trên:

- Tác động khi vùng mã hoạt động sai.
- Tần suất vùng mã được sửa hoặc mở rộng.
- Số caller và hệ thống phụ thuộc.
- Mức độ thiếu bằng chứng kiểm thử.
- Khả năng chia thay đổi thành lát cắt an toàn.
- Chi phí duy trì và rủi ro vận hành quan sát được.

Mục tiêu là giảm trở ngại thực tế, không phải thay mọi thứ chỉ vì muốn dùng một phong cách mới.

## 2. Đọc cấu trúc trước khi thay đổi

Đọc cấu trúc là quá trình dựng lại bức tranh đủ dùng về **thành phần, trách nhiệm, phụ thuộc, luồng dữ liệu và ranh giới tác dụng phụ**. Không nhất thiết phải hiểu mọi dòng code trong repository trước khi bắt đầu; cần hiểu đủ sâu ở khu vực sắp thay đổi và các ranh giới nối với nó.

### 2.1. Xác định entry point và đường đi của yêu cầu

Một ứng dụng Java có thể nhận công việc từ nhiều entry point:

- HTTP controller hoặc REST endpoint.
- Consumer đọc message từ queue.
- Job theo lịch hoặc batch import.
- Command-line tool.
- Listener của framework hoặc callback.
- API công khai được module khác gọi.

Sơ đồ khái quát:

~~~text
HTTP request --------+
                     |
Queue message -------+--> Application service
                     |          |
Scheduled job -------+          +--> Domain policy
                                |
                                +--> Repository / database
                                |
                                +--> External gateway
                                |
                                +--> Event / notification
~~~

Nếu một chính sách được gọi từ cả HTTP và batch, chỉ đọc controller là chưa đủ. Cần xác định **tất cả đường vào có liên quan** và những caller có thể nằm ngoài module đang mở.

### 2.2. Lập bản đồ thành phần và trách nhiệm

Với vùng mã cần chuyển đổi, có thể lập bảng:

| Thành phần | Trách nhiệm hiện tại | Phụ thuộc vào | Ai sử dụng? |
| --- | --- | --- | --- |
| Controller | Nhận request, ánh xạ response | CheckoutService | HTTP clients |
| CheckoutService | Điều phối tạo đơn | PricingPolicy, repository, gateway | Controller, batch |
| PricingPolicy | Tính phí và chiết khấu | Dữ liệu đầu vào | CheckoutService, preview API |
| OrderRepository | Đọc/ghi đơn | Database | Service, job |
| PaymentGateway | Gửi yêu cầu thanh toán | Dịch vụ ngoài | CheckoutService |

Đây là ví dụ minh họa, không phải kiến trúc bắt buộc. Một thành phần có thể đang đảm nhiệm nhiều trách nhiệm; bảng giúp nhìn ra nơi cần đọc sâu hơn.

### 2.3. Theo dõi cả chiều gọi và chiều dữ liệu

Đừng chỉ tìm “phương thức nào gọi phương thức này”. Hãy lần theo:

- **Ai tạo dữ liệu?** Giá tiền lấy từ client, DB, cache hay dịch vụ ngoài?
- **Ai xác thực dữ liệu?** Có kiểm tra quyền và tính hợp lệ trước khi dùng không?
- **Ai biến đổi dữ liệu?** Có đổi đơn vị, làm tròn hoặc chuẩn hóa?
- **Ai sở hữu trạng thái?** Service, entity, transaction hay hệ thống ngoài?
- **Ai đọc kết quả?** Có consumer phụ thuộc định dạng hoặc giá trị mặc định?
- **Ai chịu trách nhiệm khi lỗi?** Caller retry, service phục hồi hay operator đối soát?

Một phương thức có thể nhận **amountVnd** nhưng thực tế caller truyền số tiền chưa bao gồm thuế. Tên tham số không đủ để chứng minh ngữ nghĩa; cần đối chiếu nguồn dữ liệu và hợp đồng.

### 2.4. Tìm những mối quan hệ không thể thấy từ chữ ký

Các dấu hiệu nên điều tra:

- Phương thức phải được gọi sau một phương thức khởi tạo trạng thái.
- Một helper đọc trường mutable đã được gán ở nơi khác.
- Một repository vừa ghi DB vừa gửi event.
- Một exception được bắt ở nhiều tầng và chuyển thành các mã lỗi khác nhau.
- Một module truy cập trực tiếp bảng hoặc class nội bộ của module khác.
- Một static registry, cache hoặc singleton chứa trạng thái thay đổi.
- Một script hoặc job ngoài ứng dụng cũng cập nhật cùng dữ liệu.

Những mối quan hệ này thường tạo **temporal coupling**, **hidden dependency** hoặc **shared state**. Khi chuyển đổi, phải quyết định giữ, làm rõ hay loại bỏ từng quan hệ.

### 2.5. Đọc cấu hình và cách chạy đúng phạm vi

Hành vi runtime có thể phụ thuộc:

- Spring profile và file cấu hình theo môi trường.
- Biến môi trường, command-line arguments hoặc secret manager.
- Feature flag và cấu hình routing.
- Phiên bản JDK, dependency và plugin build.
- Transaction manager, isolation level và connection pool.
- Scheduler, concurrency setting và timeout.

Một unit test có thể tạo service với cấu hình mặc định nhưng production lại bật một nhánh khác. Không nên kết luận cấu trúc hoặc hành vi đã được hiểu nếu chưa biết **đường chạy thực tế nào đang sử dụng thành phần**.

## 3. Ghi nhận hành vi trước khi chuyển đổi

Sau khi hiểu đường gọi, cần ghi nhận những gì hệ thống đang làm và điều gì hợp đồng yêu cầu. Đây là cơ sở để phát hiện thay đổi ngoài ý muốn.

### 3.1. Lập bảng hành vi hiện tại và hành vi mục tiêu

Ví dụ chính sách phí vận chuyển:

| Trường hợp | Hành vi hiện tại quan sát được | Hành vi mục tiêu theo yêu cầu |
| --- | --- | --- |
| Khách thường, 499.999 VND | Phí 30.000 | Phí 30.000 |
| Khách thường, 500.000 VND | Phí 30.000 | Phí 0 |
| Khách thường, 500.001 VND | Phí 0 | Phí 0 |
| VIP, 299.999 VND | Phí 30.000 | Phí 30.000 |
| VIP, 300.000 VND | Phí 0 | Phí 0 |

Trong ví dụ, hệ thống cũ sai tại đúng **500.000 VND**. Một test ghi nhận hiện trạng có thể xác nhận lỗi này đang tồn tại, nhưng test theo hợp đồng mục tiêu phải yêu cầu phí 0.

Tách hai bảng hoặc hai loại test giúp tránh vô tình biến lỗi cũ thành chuẩn mới. Khi chuyển đổi, cần nói rõ **đang bảo tồn hành vi hay chủ động sửa sai khác**.

### 3.2. Characterization test và contract test

**Characterization test** mô tả hành vi quan sát được của hệ thống hiện tại. Nó hữu ích khi tài liệu thiếu và cần một mốc so sánh trước refactor.

**Contract test** kiểm tra lời hứa mà caller hoặc hệ thống khác phụ thuộc, ví dụ:

- Request hợp lệ tạo kết quả có schema đúng.
- Dữ liệu không hợp lệ bị từ chối theo loại lỗi đã công bố.
- Caller cũ vẫn nhận đúng response trong giai đoạn tương thích.
- Một idempotency key không tạo side effect trùng.

Hai loại test có thể cùng tồn tại. Nếu characterization test phát hiện một hành vi sai đã được xác nhận, hãy đánh dấu rõ và thêm test theo hợp đồng mục tiêu để dẫn đường cho bug fix.

### 3.3. Tạo baseline cho dữ liệu và side effect

Với luồng không thuần, ghi nhận:

- Số bản ghi được tạo/cập nhật.
- Trạng thái trước và sau thao tác.
- Số lần gọi gateway hoặc phát message.
- Các mã lỗi và loại exception.
- Thứ tự các bước quan trọng.
- Những tài nguyên cần đóng hoặc hoàn trả.

Không nhất thiết lưu payload thật chứa dữ liệu nhạy cảm. Có thể dùng fixture tổng hợp hoặc dữ liệu đã được loại thông tin định danh.

### 3.4. Đừng coi log production là oracle duy nhất

Log cho biết điều gì đã xảy ra trong một số lần chạy, không nhất thiết cho biết điều gì **đáng lẽ phải xảy ra**. Log có thể thiếu trường, bị sampling, ghi sai thời điểm hoặc phản ánh một lỗi đang tồn tại.

Khi cần xác định hành vi đúng, ưu tiên hợp đồng đã xác nhận, yêu cầu nghiệp vụ và test oracle độc lập. Log, metrics và trace là bằng chứng bổ trợ để hiểu cách hệ thống đang vận hành.

## 4. Chọn lát cắt chuyển đổi có thể hiểu và kiểm chứng

Một lát cắt tốt là một phần thay đổi có ranh giới rõ, có thể xác minh mà không cần giả định toàn bộ dự án đã được viết lại.

### 4.1. Chia theo trách nhiệm hoặc đường sử dụng

Ví dụ một checkout service đang làm nhiều việc:

~~~text
CheckoutService
  - validate request
  - calculate discount
  - calculate shipping
  - save order
  - capture payment
  - publish event
~~~

Có thể chuyển theo các bước:

1. Tách phép tính thuần và thêm test cho chính sách.
2. Chuyển một nhóm caller sang chính sách mới.
3. Giữ service điều phối và xác minh side effect không đổi.
4. Làm rõ ranh giới lưu đơn/thanh toán và test đường lỗi.
5. Chuyển dần các consumer còn lại.
6. Xóa logic cũ khi không còn caller và có bằng chứng tương thích.

Không phải mọi hệ thống đều cần đúng thứ tự này. Nếu rủi ro lớn nhất nằm ở quyền truy cập hoặc dữ liệu, có thể cần bảo vệ ranh giới đó trước.

### 4.2. Tránh lát cắt chỉ làm nửa cấu trúc nhưng không có hợp đồng

Ví dụ, tạo một class **NewPricingService** nhưng không chuyển bất kỳ caller nào và vẫn để công thức cũ tồn tại ở ba nơi. Điều đó chưa giảm được nguồn sự thật trùng lặp; nó chỉ thêm một khái niệm.

Mỗi lát cắt nên trả lời:

- Trách nhiệm nào được chuyển?
- Caller nào thực sự sử dụng phần mới?
- Hành vi nào được giữ?
- Hành vi nào thay đổi có chủ ý?
- Bằng chứng nào chứng minh bước này an toàn?
- Điều gì còn lại và ai chịu trách nhiệm bước tiếp?

### 4.3. Giữ tính nguyên tử ở nơi cần thiết

Chia nhỏ không có nghĩa tách một bất biến nghiệp vụ thành những trạng thái không hợp lệ. Ví dụ, nếu ghi hai cột trong cùng một DB transaction là cần thiết để duy trì nhất quán, không được tách thành hai lần commit độc lập chỉ để PR nhỏ hơn.

Khi một thay đổi cần nhiều thành phần phối hợp, hãy dùng adapter, schema tương thích, transaction hoặc quy trình chuyển đổi có kiểm soát để tạo các bước triển khai an toàn.

### 4.4. Định nghĩa tiêu chí hoàn tất trước khi sửa

Một mục tiêu cụ thể:

> “Tách phép tính phí khỏi CheckoutService, giữ nguyên API và thứ tự lưu đơn, thêm test cho hai ngưỡng và xác minh controller cùng batch đều dùng đúng chính sách.”

Một mục tiêu khó đánh giá:

> “Làm sạch checkout.”

Tiêu chí hoàn tất cần gắn với **hành vi, cấu trúc và phạm vi**. Nếu chỉ nói “code đẹp hơn”, reviewer không biết phải kiểm chứng điều gì.

## 5. Đọc lại cấu trúc sau mỗi lát cắt

Sau một phần chuyển đổi, không nên chỉ xem test xanh rồi chuyển ngay sang phần kế tiếp. Cần đọc lại cấu trúc đã thay đổi để xác nhận ranh giới và trách nhiệm vẫn hợp lý.

### 5.1. So sánh cấu trúc trước và sau

~~~text
TRƯỚC
Controller ----> CheckoutService
                    |  |  |
                    |  |  +--> PaymentGateway
                    |  +-----> OrderRepository
                    +--------> Pricing logic nội bộ

SAU MỘT LÁT CẮT
Controller ----> CheckoutService ----> PricingPolicy
                    |                       |
                    +--> OrderRepository    +--> phép tính thuần
                    |
                    +--> PaymentGateway
~~~

Đây là sơ đồ minh họa. Sau khi tách, hãy hỏi:

- **PricingPolicy** có thực sự sở hữu một quy tắc nghiệp vụ nhất quán không?
- CheckoutService có còn giữ bản sao công thức cũ không?
- Có caller nào tiếp tục dùng logic cũ?
- Có tạo dependency vòng hoặc làm module mới phụ thuộc tầng sai không?
- Dữ liệu và đơn vị có được truyền rõ qua tham số không?
- Có đưa trạng thái request vào field của service dùng chung không?
- Phần mới có thể được kiểm thử độc lập không?

### 5.2. Đọc lại đường gọi thật

Tìm lại các entry point đã lập ở bước khảo sát. Xác nhận mỗi caller:

1. Gọi đúng implementation mới hoặc adapter có chủ đích.
2. Truyền cùng ngữ nghĩa dữ liệu và đơn vị.
3. Giữ kiểm tra quyền, validation và transaction boundary.
4. Xử lý lỗi theo hợp đồng.
5. Không còn gọi một helper cũ bị bỏ quên.

Một refactor có thể làm unit test của chính sách xanh trong khi controller vẫn dùng công thức cũ. Vì vậy, **test lớp mới không thay thế việc kiểm tra caller đã được chuyển**.

### 5.3. Kiểm tra dependency và quyền sở hữu

Sau mỗi lát cắt, xem:

- Lớp nào sở hữu dữ liệu và trạng thái?
- Có truyền một object mutable sang nơi khác mà không rõ ai được sửa?
- Interface mới có đặt đúng ranh giới không?
- Có dependency mới vào framework hoặc hạ tầng không cần thiết?
- Có tạo một abstraction chỉ để bọc một lời gọi mà không làm rõ trách nhiệm?
- Có còn đường truy cập trực tiếp vào cấu trúc cũ?

Mục tiêu không phải đạt một sơ đồ kiến trúc đẹp tuyệt đối. Cần bảo đảm cấu trúc mới **làm lộ phụ thuộc quan trọng và giảm những phụ thuộc gây khó thay đổi**.

### 5.4. Đọc lại các trạng thái và vòng đời

Nếu chuyển một trường tạm thành biến cục bộ hoặc tách một service, kiểm tra:

- Trạng thái có còn tồn tại lâu hơn cần thiết?
- Có reset thủ công hoặc phụ thuộc thứ tự gọi không?
- Một exception giữa chừng để lại trạng thái không hợp lệ nào?
- Hai request có thể dùng chung object mutable không?
- Tài nguyên được tạo ở đâu và ai chịu trách nhiệm đóng?
- Transaction bắt đầu/kết thúc ở đâu?

Một phương thức ngắn hơn không nhất thiết là một cấu trúc an toàn hơn. Đọc lại phải xem **vòng đời dữ liệu và side effect**, không chỉ độ dài method.

## 6. Kiểm tra hành vi sau mỗi phần được chuyển đổi

Đây là bước phải lặp lại sau **từng lát cắt**, không phải một đợt kiểm thử tổng hợp chỉ chạy trước ngày phát hành. Mục tiêu là phát hiện sai khác ngay khi phạm vi thay đổi còn nhỏ và có thể truy nguyên.

### 6.1. Chu trình xác minh lặp lại

~~~text
Chọn một lát cắt
      |
      v
Ghi rõ hợp đồng và hành vi cần giữ
      |
      v
Thực hiện thay đổi nhỏ
      |
      v
Đọc lại cấu trúc và đường gọi
      |
      v
Chạy test phù hợp + kiểm tra side effect
      |
      v
So sánh với baseline / oracle
      |
      +---- Sai khác chưa giải thích ---> Dừng, điều tra, sửa
      |
      v
Ghi nhận bằng chứng và trạng thái
      |
      v
Chọn lát cắt kế tiếp
~~~

Mỗi vòng cần có **điều kiện dừng**. Nếu một sai khác chưa được giải thích, không nên tiếp tục chuyển đổi chồng lên nó vì sẽ làm phạm vi điều tra lớn hơn.

### 6.2. Kiểm tra theo nhiều lớp

| Lớp xác minh | Điều cần xác nhận | Ví dụ |
| --- | --- | --- |
| Unit | Quy tắc cục bộ vẫn đúng | Phí vận chuyển ở ngay dưới, đúng và trên ngưỡng |
| Contract | Caller vẫn nhận đúng giao thức | JSON, kiểu lỗi, chữ ký API |
| Integration | Các thành phần tương tác đúng | Repository lưu đúng tổng tiền |
| Side-effect | Tác dụng phụ đúng số lần và đúng thứ tự | Gateway chỉ được gọi sau validation |
| State | Trạng thái sau thành công/lỗi hợp lệ | Không để đơn ở trạng thái nửa hoàn tất |
| Compatibility | Người dùng cũ còn hoạt động trong giai đoạn chuyển | Adapter API cũ gọi chính sách mới |
| Operational | Có thể quan sát và phục hồi | Metrics, log an toàn, rollback/fix-forward |

Không phải lát cắt nào cũng cần mọi lớp. Một hàm thuần có thể chỉ cần unit test và review cấu trúc. Một thay đổi ở transaction hoặc payment cần thêm integration test, kiểm tra lỗi và kế hoạch vận hành.

### 6.3. So sánh trước/sau bằng oracle độc lập

Khi có baseline, có thể chạy cùng dữ liệu trên implementation cũ và mới để tìm khác biệt. Nhưng phải phân loại:

- **Khác biệt được phép:** bug fix đã xác nhận hoặc thay đổi yêu cầu.
- **Khác biệt ngoài ý muốn:** kết quả sai, exception khác, thứ tự side effect đổi.
- **Khác biệt chưa biết:** hợp đồng thiếu hoặc dữ liệu hiện trạng không đại diện.

Không nên tự động coi implementation cũ là oracle đúng. Nó chỉ là **mốc quan sát**, còn hợp đồng mục tiêu mới quyết định kết quả nào phải được giữ.

### 6.4. Differential testing chỉ phù hợp với hành vi có thể so sánh an toàn

Với hàm tính thuần, có thể so sánh kết quả:

~~~java
long oldResult = legacyPolicy.feeVnd(subtotalVnd, vip);
long newResult = newPolicy.feeVnd(subtotalVnd, vip);
assertEquals(oldResult, newResult);
~~~

Đây là một cách kiểm tra tương đương cho **những đầu vào mà hành vi cũ cần được giữ**. Nếu biết implementation cũ sai ở ngưỡng, cần có test riêng theo oracle mới thay vì yêu cầu hai phiên bản luôn bằng nhau.

Không chạy hai implementation có tác dụng phụ cùng lúc trên dữ liệu thật chỉ để so sánh. Hai lệnh thanh toán, hai lần gửi email hoặc hai lần ghi DB có thể gây hại. Với side effect, dùng fake, sandbox, read-only mode hoặc fixture riêng.

### 6.5. Kiểm tra cả điều không được xảy ra

Ngoài assert kết quả, hãy kiểm tra:

- Validation thất bại thì repository không được ghi.
- Người không có quyền thì gateway không được gọi.
- Timeout không được tự động đánh dấu giao dịch là chắc chắn thất bại nếu kết quả chưa rõ.
- Retry cùng khóa không tạo side effect trùng theo hợp đồng.
- Exception không làm tài nguyên bị bỏ mở.
- Lần gọi sau không đọc trạng thái tạm của lần gọi trước.

Những assertion phủ định này thường phát hiện lỗi điều phối mà test “trả đúng một giá trị” không nhìn thấy.

## 7. Ví dụ Java: chuyển một chính sách khỏi mã hiện hữu

Giả sử controller và batch đều có công thức phí vận chuyển. Ta muốn đưa quy tắc về một nơi mà không thay đổi API tạo đơn trong cùng lát cắt.

### 7.1. Trước chuyển đổi

~~~java
public final class LegacyCheckoutService {
    private final OrderWriter writer;

    public LegacyCheckoutService(OrderWriter writer) {
        this.writer = writer;
    }

    public long createOrder(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        long feeVnd;
        if ((vip && subtotalVnd >= 300_000L)
                || subtotalVnd >= 500_000L) {
            feeVnd = 0L;
        } else {
            feeVnd = 30_000L;
        }

        long payableVnd = Math.addExact(subtotalVnd, feeVnd);
        writer.save(payableVnd);
        return payableVnd;
    }

    public interface OrderWriter {
        void save(long payableVnd);
    }
}
~~~

Đây là ví dụ rút gọn. Giả định **OrderWriter.save** là một ranh giới ghi đã có hợp đồng rõ; nó không mô tả transaction hoặc ID của đơn hàng.

### 7.2. Lát cắt thứ nhất: thêm chính sách thuần

Tệp **ShippingPolicy.java**:

~~~java
public final class ShippingPolicy {
    private static final long VIP_FREE_FROM_VND = 300_000L;
    private static final long FREE_FROM_VND = 500_000L;
    private static final long STANDARD_FEE_VND = 30_000L;

    private ShippingPolicy() {}

    public static long feeVnd(long subtotalVnd, boolean vip) {
        if (subtotalVnd < 0) {
            throw new IllegalArgumentException("Negative subtotal");
        }

        boolean free =
                (vip && subtotalVnd >= VIP_FREE_FROM_VND)
                || subtotalVnd >= FREE_FROM_VND;
        return free ? 0L : STANDARD_FEE_VND;
    }
}
~~~

Sau khi thêm class, **chưa xóa công thức cũ**. Đọc lại cấu trúc:

- Chính sách chỉ chứa quy tắc tính phí, không phụ thuộc repository hoặc framework.
- Các ngưỡng có tên và đơn vị VND.
- Phương thức không giữ trạng thái giữa các lần gọi.
- Validation và ngoại lệ được nêu rõ.

Kiểm tra hành vi:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class ShippingPolicyTest {
    @Test
    void chargesRegularFeeBelowThreshold() {
        assertEquals(30_000L,
                ShippingPolicy.feeVnd(499_999L, false));
    }

    @Test
    void waivesRegularFeeAtThreshold() {
        assertEquals(0L,
                ShippingPolicy.feeVnd(500_000L, false));
    }

    @Test
    void waivesVipFeeAtVipThreshold() {
        assertEquals(0L,
                ShippingPolicy.feeVnd(300_000L, true));
    }

    @Test
    void rejectsNegativeSubtotal() {
        assertThrows(IllegalArgumentException.class,
                () -> ShippingPolicy.feeVnd(-1L, false));
    }
}
~~~

JUnit Jupiter là dependency kiểm thử cần khai báo trong build; không có sẵn trong JDK. Các ca test dùng expected value viết độc lập theo hợp đồng, không gọi chính implementation để tự tạo expected.

### 7.3. Lát cắt thứ hai: chuyển một caller và giữ hợp đồng service

Thay phần tính phí trong **createOrder**:

~~~java
public long createOrder(long subtotalVnd, boolean vip) {
    long feeVnd = ShippingPolicy.feeVnd(subtotalVnd, vip);
    long payableVnd = Math.addExact(subtotalVnd, feeVnd);
    writer.save(payableVnd);
    return payableVnd;
}
~~~

Đọc lại cấu trúc:

- Service vẫn chịu trách nhiệm điều phối lưu đơn.
- Chính sách tính phí có một nơi sở hữu.
- Dữ liệu được truyền tường minh qua tham số.
- Không có trường mutable mới.
- Thứ tự tính toán trước khi gọi writer vẫn giữ.

Kiểm tra hành vi service bằng fake:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class CheckoutServiceMigrationTest {
    @Test
    void savesTheExpectedAmountOnce() {
        AtomicInteger calls = new AtomicInteger();
        long[] saved = {-1L};

        LegacyCheckoutService.OrderWriter writer = amount -> {
            saved[0] = amount;
            calls.incrementAndGet();
        };
        var service = new LegacyCheckoutService(writer);

        long result = service.createOrder(500_000L, false);

        assertEquals(500_000L, result);
        assertEquals(500_000L, saved[0]);
        assertEquals(1, calls.get());
    }

    @Test
    void invalidSubtotalDoesNotWrite() {
        AtomicInteger calls = new AtomicInteger();
        var service = new LegacyCheckoutService(
                amount -> calls.incrementAndGet());

        assertThrows(IllegalArgumentException.class,
                () -> service.createOrder(-1L, false));
        assertEquals(0, calls.get());
    }
}
~~~

Các test trên kiểm tra tương tác service với writer fake. Chúng **không chứng minh** DB thật đã commit nguyên tử hoặc writer không thể timeout sau khi ghi. Những điều đó cần integration test ở đúng ranh giới lưu trữ.

### 7.4. Lát cắt thứ ba: chuyển batch sau khi xác minh chính sách

Trước khi thay công thức batch, kiểm tra nó có thực sự dùng **cùng chính sách** không. Nếu batch xử lý đơn lịch sử theo mức phí tại thời điểm tạo đơn, nó có thể cần đọc **policyVersion** đã lưu thay vì dùng chính sách hiện tại.

Chỉ khi hợp đồng xác nhận cùng một quy tắc, mới chuyển:

~~~java
long feeVnd = ShippingPolicy.feeVnd(subtotalVnd, vip);
~~~

Sau khi chuyển batch:

- Chạy test batch cho đầu vào đại diện và biên.
- Xác minh định dạng file xuất hoặc thông điệp không đổi.
- Kiểm tra số lượng bản ghi và tổng tiền trong fixture.
- Xác nhận không còn công thức cũ ở caller thuộc phạm vi.
- Kiểm tra batch có retry hoặc chạy lại mà không tạo tác dụng phụ trùng không.

### 7.5. Lát cắt cuối: xóa logic cũ khi không còn người dùng

Chỉ xóa implementation cũ khi:

- Các caller đã chuyển hoặc adapter cũ có kế hoạch riêng.
- Contract tests xác nhận giao diện được giữ.
- Test mới bao phủ các nhánh cần thiết.
- Không còn job, module hoặc script phụ thuộc.
- Có thể giải thích chính sách mới là nguồn sự thật.

Không nên xóa một phương thức chỉ vì tìm trong module hiện tại không thấy caller; nó có thể là API public được module hoặc client ngoài sử dụng.

## 8. Chuyển đổi API, schema và dữ liệu có tương thích

Đọc lại cấu trúc sau mỗi lát cắt đặc biệt quan trọng khi thay đổi ranh giới công khai hoặc dữ liệu bền vững.

### 8.1. API: giữ caller cũ trong giai đoạn chuyển

Nếu đổi tên phương thức công khai, có thể thêm API mới và giữ adapter:

~~~java
public final class ShippingFacade {
    public long shippingFeeVnd(long subtotalVnd, boolean vip) {
        return ShippingPolicy.feeVnd(subtotalVnd, vip);
    }

    @Deprecated(since = "2.0", forRemoval = false)
    public long getShipFee(long subtotalVnd, boolean vip) {
        return shippingFeeVnd(subtotalVnd, vip);
    }
}
~~~

Ví dụ giả định hai phương thức có cùng ngữ nghĩa. Nếu API cũ có hành vi khác, không được chuyển tiếp một cách mù quáng. Cần kiểm thử caller cũ, tài liệu migration và thời hạn hỗ trợ.

Sau mỗi bước chuyển:

- Xác nhận caller mới dùng API mới.
- Xác nhận caller cũ vẫn nhận kết quả theo hợp đồng.
- Theo dõi consumer chưa di trú nếu có khả năng quan sát.
- Không xóa adapter khi còn client được hỗ trợ.

### 8.2. Database: expand, migrate, contract

Đổi tên cột hoặc chuẩn hóa dữ liệu cần xem cả phiên bản ứng dụng đang chạy:

1. **Expand:** thêm cột/cấu trúc mới nhưng giữ cấu trúc cũ.
2. **Migrate:** backfill dữ liệu và giữ các writer tương thích.
3. **Verify:** đối chiếu dữ liệu cũ/mới, số bản ghi và constraint.
4. **Switch:** chuyển reader sang cấu trúc mới theo kế hoạch.
5. **Contract:** chỉ bỏ cấu trúc cũ khi không còn consumer.

Sau từng giai đoạn, xác minh:

- Schema đúng với migration đã chạy.
- Không có bản ghi chưa backfill ngoài ngưỡng cho phép.
- Các writer đang hoạt động giữ dữ liệu nhất quán.
- Reader mới xử lý dữ liệu cũ và dữ liệu mới đúng.
- Rollback hoặc fix-forward đã được đánh giá.

Dual write không tự động an toàn. Nếu ghi hai hệ thống khác nhau, một bên có thể thành công còn bên kia thất bại. Cần transaction, outbox, idempotency hoặc đối soát theo kiến trúc thực tế.

### 8.3. Đơn vị, null và giá trị mặc định

Một thay đổi từ **total** sang **totalVnd** không chỉ là đổi tên nếu dữ liệu trước đây có thể chứa nhiều loại tiền tệ hoặc đơn vị. Cần xác nhận:

- Giá trị cũ thực sự là VND hay đã được chuẩn hóa?
- Có bản ghi null, âm hoặc ngoài miền không?
- Quy tắc làm tròn có giống trước không?
- Giá trị mặc định có làm dữ liệu cũ bị diễn giải sai?
- Các báo cáo, export và consumer có dùng cột cũ?

Không được backfill bằng một công thức phỏng đoán nếu không có bằng chứng về ngữ nghĩa dữ liệu.

## 9. Quan sát hệ thống sau khi triển khai từng phần

Kiểm thử trước merge xác minh các tình huống được mô hình hóa. Khi thay đổi đã chạy trong môi trường tích hợp hoặc production, cần xác nhận hành vi thực tế vẫn phù hợp với giả định ban đầu.

### 9.1. Chọn tín hiệu theo mục tiêu chuyển đổi

| Mục tiêu | Tín hiệu nên theo dõi | Điều cần tránh |
| --- | --- | --- |
| Tách chính sách tính giá | Phân bố phí, số sai khác được xác nhận, lỗi tính toán | Log toàn bộ dữ liệu khách hàng |
| Chuyển caller | Tỷ lệ request qua đường mới/cũ, lỗi theo phiên bản | Không biết caller nào vẫn dùng adapter |
| Đổi schema | Số bản ghi backfill, số mismatch, lỗi đọc/ghi | Chỉ nhìn migration job báo thành công |
| Đổi luồng thanh toán | Trạng thái pending/unknown, timeout, retry, duplicate | Đánh dấu timeout là thất bại chắc chắn |
| Giảm phụ thuộc | Số caller còn dùng API cũ, module còn import cũ | Xóa API trước khi xác minh consumer |

Metrics cần có tên, đơn vị và nhãn đủ để phân biệt phiên bản/đường xử lý, nhưng tránh tạo cardinality quá lớn hoặc chứa thông tin định danh nhạy cảm. Log và trace nên hỗ trợ điều tra mà không làm lộ token, thông tin thanh toán hoặc dữ liệu cá nhân.

### 9.2. So sánh trước/sau bằng cùng một định nghĩa

Nếu trước chuyển đổi đo **tỷ lệ lỗi tạo đơn** theo một định nghĩa, sau chuyển đổi phải dùng cùng định nghĩa và phạm vi so sánh. Nếu đổi cách tính metric cùng lúc, số liệu có thể trông tốt hơn chỉ vì cách đếm thay đổi.

Nên ghi:

- Khoảng thời gian và traffic được so sánh.
- Phiên bản code và cấu hình.
- Module/caller được chuyển.
- Mức rollout và các feature flag đang bật.
- Sự khác nhau về dữ liệu hoặc điều kiện môi trường.

Không nên tuyên bố “giảm 30% lỗi” nếu chưa có baseline, mẫu đủ đại diện hoặc chưa loại trừ thay đổi traffic và môi trường.

### 9.3. Canary hoặc rollout theo nhóm

Nếu hệ thống hỗ trợ, có thể chuyển một nhóm caller hoặc tỷ lệ traffic nhỏ trước. Theo dõi:

- Tỷ lệ lỗi và loại lỗi.
- Độ trễ p50/p95/p99 khi phù hợp.
- Số lần retry và timeout.
- Sai khác kết quả nghiệp vụ.
- Số bản ghi tạo/cập nhật và trạng thái cuối.
- Tài nguyên như connection pool, CPU, memory.

Mở rộng rollout khi các điều kiện đã định trước được đáp ứng. Nếu vượt ngưỡng, dừng chuyển đổi, điều tra và rollback/fix-forward theo kế hoạch.

Canary không bảo đảm mọi nhóm dữ liệu được đại diện. Nhóm thử cần đủ đa dạng cho rủi ro cần kiểm tra; với dữ liệu tài chính hoặc tenant, cần đảm bảo cách chọn nhóm không gây phân biệt hoặc rò rỉ dữ liệu.

## 10. Lập kế hoạch rollback và fix-forward

Một phần chuyển đổi chỉ an toàn khi biết cách xử lý nếu kết quả không đạt. Tuy nhiên, rollback code không phải lúc nào cũng đảo ngược được dữ liệu hoặc side effect.

### 10.1. Câu hỏi trước khi chuyển một lát cắt

- Có thể quay lại phiên bản code trước không?
- Schema mới có còn tương thích với code cũ không?
- Dữ liệu mới ghi có được code cũ đọc đúng không?
- Có message, email hoặc thanh toán đã gửi ra ngoài không?
- Nếu có side effect không thể hoàn tác, cách đối soát/bù trừ là gì?
- Ai có quyền dừng rollout và quyết định phục hồi?
- Có dữ liệu và log đủ để xác định trạng thái thực tế không?

### 10.2. Rollback code khác rollback nghiệp vụ

Ví dụ, code mới đã thu tiền thành công rồi lưu trạng thái **PAID**. Nếu deployment sau đó rollback về code cũ, thao tác thu tiền không tự biến mất. Tương tự, một migration đã xóa cột cũ có thể khiến code cũ không chạy được.

Do đó:

- Giữ schema tương thích trong giai đoạn rolling deploy.
- Với side effect bên ngoài, dùng idempotency và quy trình đối soát.
- Với dữ liệu đã chuyển, có kế hoạch restore hoặc migration ngược đã kiểm chứng nếu khả thi.
- Khi không thể đảo chiều an toàn, xác định đường **fix-forward** và người ra quyết định.

### 10.3. Định nghĩa điều kiện dừng trước rollout

Ví dụ một kế hoạch có thể nêu:

~~~text
Lát cắt: Chuyển 10% request sang PricingPolicy mới

Tiếp tục khi:
  - Không có sai khác kết quả chưa giải thích.
  - Tỷ lệ lỗi không vượt ngưỡng vận hành đã thống nhất.
  - Độ trễ không tăng vượt giới hạn.
  - Không có bản ghi đơn hàng sai trạng thái.

Dừng và điều tra khi:
  - Có sai khác tính phí đã xác nhận.
  - Có duplicate side effect.
  - Có mismatch dữ liệu vượt ngưỡng.
  - Metrics không còn đủ để xác định đường chạy.

Phục hồi:
  - Tắt route mới nếu dữ liệu tương thích.
  - Nếu dữ liệu đã đổi không thể đảo ngược,
    dùng quy trình fix-forward/đối soát đã chuẩn bị.
~~~

Các ngưỡng cần được xác định từ SLO và mức rủi ro của sản phẩm, không lấy ví dụ này làm con số mặc định.

## 11. Những cách chuyển đổi dễ làm mất dấu hành vi

### 11.1. Chuyển một lần rồi chỉ chạy toàn bộ test ở cuối

Khi nhiều lát cắt được gộp lại, một test đỏ có thể liên quan tới nhiều thay đổi. Phạm vi điều tra lớn hơn và có thể che khuất sai lệch đầu tiên.

**Cách tốt hơn:** sau mỗi lát cắt, đọc lại cấu trúc, chạy test phù hợp, ghi sai khác và chỉ đi tiếp khi kết quả được giải thích.

### 11.2. Dùng implementation cũ làm chuẩn tuyệt đối

Mã cũ có thể chứa bug đã biết, dữ liệu sai hoặc hành vi vô tình mà không ai muốn giữ. Nếu mọi test mới chỉ so sánh bằng với mã cũ, lỗi sẽ được bảo tồn.

**Cách tốt hơn:** tách characterization test khỏi test theo hợp đồng mục tiêu. Ghi rõ những sai khác được chấp nhận và lý do.

### 11.3. Chỉ kiểm tra class mới mà quên caller

Một PricingPolicy mới có thể đúng, nhưng controller và batch vẫn gọi công thức cũ. Test của class mới xanh không chứng minh toàn hệ thống đã chuyển.

**Cách tốt hơn:** sau khi chuyển, kiểm tra từng entry point, contract test và đường gọi thật; tìm những caller còn phụ thuộc implementation cũ.

### 11.4. Xóa code cũ trước khi xác minh consumer

Không thấy caller trong module hiện tại không có nghĩa API không được dùng ở nơi khác. Job, script, client bên ngoài hoặc plugin có thể phụ thuộc vào nó.

**Cách tốt hơn:** kiểm tra phạm vi công khai, phiên bản hỗ trợ, log/telemetry nếu có và kế hoạch migration. Giữ adapter trong thời gian tương thích cần thiết.

### 11.5. Chạy hai nhánh có side effect để so sánh

Chạy cả code cũ và mới có thể hữu ích với phép tính thuần, nhưng nguy hiểm nếu cả hai cùng ghi DB, thu tiền hoặc gửi thông báo.

**Cách tốt hơn:** dùng dữ liệu fixture, sandbox, read-only shadow hoặc so sánh kết quả thuần; không nhân đôi tác dụng phụ trên dữ liệu thật.

### 11.6. Đổi schema và code mà không có giai đoạn tương thích

Rolling deployment có thể khiến phiên bản cũ và mới chạy đồng thời. Nếu code mới xóa cột cũ ngay, node cũ có thể lỗi; nếu code cũ ghi cột cũ sau khi backfill, dữ liệu mới có thể lệch.

**Cách tốt hơn:** expand–migrate–verify–switch–contract; kiểm tra reader và writer trong từng giai đoạn.

### 11.7. Chỉ kiểm tra happy path

Một lần chạy thành công không xác minh timeout, retry, dữ liệu thiếu, lỗi giữa chừng, cleanup hoặc concurrency.

**Cách tốt hơn:** xác định các điểm thất bại và kiểm tra trạng thái sau lỗi, bao gồm những side effect **không được phép xảy ra**.

### 11.8. Refactor đồng thời quá nhiều khái niệm

Nếu cùng lúc đổi tên domain, framework, cấu trúc package, database và giao thức, reviewer khó đánh giá ranh giới nào tạo ra thay đổi hành vi.

**Cách tốt hơn:** ưu tiên một mục tiêu cấu trúc mỗi lát cắt, giữ phạm vi dễ đọc và tách bug fix hoặc feature change khi có thể.

## 12. Hồ sơ chuyển đổi để giữ ngữ cảnh giữa các lát cắt

Khi công việc kéo dài qua nhiều PR hoặc nhiều người, cần một ghi nhận ngắn để không phải suy luận lại từ đầu.

Một mẫu:

~~~text
Vùng mã:
  CheckoutService / ShippingPolicy

Vấn đề:
  Công thức phí bị lặp ở controller và batch.

Hợp đồng đã xác nhận:
  - VIP miễn phí từ 300.000 VND.
  - Khách thường miễn phí từ 500.000 VND.
  - Tổng âm bị từ chối.

Lát cắt đã hoàn tất:
  - Thêm ShippingPolicy.
  - Controller đã chuyển.

Bằng chứng:
  - Unit test hai ngưỡng và ca âm.
  - Contract test response controller.
  - Không thay đổi số lần ghi đơn.

Chưa chuyển:
  - OrderBatch vẫn dùng công thức cũ.

Rủi ro còn lại:
  - Batch xử lý đơn lịch sử; cần xác nhận policy version.

Lát cắt kế tiếp:
  - Xác minh hợp đồng batch, chuyển caller nếu cùng chính sách.

Điều kiện dọn:
  - Không còn consumer hợp lệ của công thức cũ.
~~~

Đây là ví dụ hồ sơ minh họa. Không ghi bí mật, token hoặc dữ liệu cá nhân vào tài liệu chuyển đổi.

### 12.1. Nội dung cần cập nhật sau mỗi bước

- Lát cắt nào đã hoàn tất và commit/phiên bản nào chứa nó?
- Những caller nào đã chuyển?
- Hành vi nào được giữ và sai khác nào được chấp thuận?
- Test hoặc kiểm tra nào đã chạy, trên phạm vi nào?
- Cấu trúc nào đã thay đổi sau khi đọc lại?
- Rủi ro nào vẫn còn và ai chịu trách nhiệm?
- Bước kế tiếp và điều kiện để xóa adapter/flag/schema cũ?

Hồ sơ này giúp reviewer, maintainer và người trực vận hành có cùng bối cảnh, đặc biệt khi người thực hiện thay đổi không phải người hiểu hệ thống ban đầu.

## 13. Checklist sau mỗi lát cắt chuyển đổi

Trước khi đánh dấu một phần đã hoàn tất, có thể dùng checklist sau.

### 13.1. Đọc lại cấu trúc

- [ ] Trách nhiệm của lớp/phương thức sau thay đổi có rõ hơn không?
- [ ] Tất cả caller thuộc phạm vi đã được xác định và kiểm tra?
- [ ] Có dependency mới hoặc dependency vòng không cần thiết?
- [ ] Dữ liệu được truyền rõ qua tham số/kết quả hay còn phụ thuộc trạng thái ngầm?
- [ ] Ai sở hữu object mutable, transaction và tài nguyên?
- [ ] Có trạng thái tạm, reset thủ công hoặc thứ tự gọi bí mật?
- [ ] Có logic cũ còn sót hoặc abstraction mới chưa được caller sử dụng?
- [ ] API, schema, cấu hình và tài liệu liên quan còn nhất quán?

### 13.2. Kiểm tra hành vi

- [ ] Có oracle độc lập cho hành vi mục tiêu?
- [ ] Đã kiểm tra happy path và các giá trị biên quan trọng?
- [ ] Đã kiểm tra đầu vào lỗi và loại lỗi theo hợp đồng?
- [ ] Các side effect có đúng số lần và thứ tự?
- [ ] Trạng thái sau lỗi có hợp lệ?
- [ ] Retry, timeout, idempotency và concurrency đã được xem xét khi liên quan?
- [ ] Tài nguyên được đóng và transaction có ranh giới rõ?
- [ ] Contract/API của caller cũ vẫn được giữ trong giai đoạn tương thích?
- [ ] Test đã chạy trên đúng module, profile và artifact liên quan?

### 13.3. Chuẩn bị bước kế tiếp

- [ ] Sai khác với baseline đã được giải thích?
- [ ] Lỗi cũ được phân biệt với thay đổi hành vi có chủ đích?
- [ ] Có metrics/log/trace phù hợp để quan sát sau triển khai?
- [ ] Rollback hoặc fix-forward đã được đánh giá?
- [ ] Rủi ro còn lại và người sở hữu được ghi nhận?
- [ ] Có tiêu chí rõ để chuyển sang lát cắt kế tiếp hoặc xóa adapter cũ?

Nếu một mục không áp dụng, ghi lý do ngắn. Checklist là công cụ hỗ trợ suy nghĩ; không nên đánh dấu tất cả ô chỉ để hoàn thành hình thức.

## 14. Tình huống luyện tập

Một hệ thống Java quản lý đơn hàng đã chạy nhiều năm. Repository có:

~~~text
orders-api
  - OrderController
  - OrderService

orders-batch
  - RecalculateOrderJob

orders-domain
  - Order
  - PricingPolicy (chưa được mọi caller dùng)

database
  - orders.total
  - orders.shipping_fee
~~~

Hiện trạng quan sát:

- **OrderService** tự tính phí vận chuyển.
- **RecalculateOrderJob** có công thức riêng, ngưỡng khác.
- Một số đơn cũ không lưu phiên bản chính sách.
- Controller trả trường JSON **total**.
- Job chạy mỗi đêm và có thể được chạy lại sau khi timeout.
- Unit test chỉ kiểm tra một trường hợp khách VIP có tổng lớn hơn ngưỡng.

Nhóm muốn chuyển toàn bộ logic sang **PricingPolicy**, đổi trường JSON thành **payableVnd**, chuẩn hóa schema DB và viết lại job.

### 14.1. Câu hỏi

1. Trước khi sửa, cần xác định những entry point, caller, reader và writer nào?
2. Vì sao không thể mặc định hai ngưỡng phí khác nhau ở service và batch là cùng một lỗi trùng code?
3. Hành vi nào cần characterization test và hành vi nào cần oracle nghiệp vụ?
4. Hãy chia công việc thành ít nhất bốn lát cắt; với mỗi lát cắt, nêu cấu trúc cần đọc lại và test cần chạy.
5. Nếu đơn cũ không lưu policy version, cần xác minh gì trước khi tính lại tổng?
6. Có thể đổi JSON **total** thành **payableVnd** ngay không? Cần adapter hoặc versioning nào?
7. Job timeout rồi chạy lại có thể tạo tác dụng phụ gì? Cần idempotency hoặc checkpoint ra sao?
8. Làm sao biết mọi caller đã chuyển và có thể xóa công thức cũ?
9. Sau khi triển khai một nhóm nhỏ, những metrics nào cần so sánh?

### 14.2. Gợi ý đối chiếu

- Lập bản đồ controller, batch, service, domain policy, repository, API consumers, báo cáo và mọi writer khác của hai cột DB.
- Hai ngưỡng khác nhau có thể là lỗi hoặc hai chính sách theo thời điểm/loại đơn. Cần xác nhận hợp đồng lịch sử trước khi hợp nhất.
- Characterization test ghi lại hành vi hiện tại; oracle nghiệp vụ xác định chính sách phải áp dụng cho đơn mới và đơn cũ.
- Có thể tách theo thứ tự: khảo sát và thêm test; xác minh/tách chính sách cho đơn mới; chuyển controller và kiểm tra JSON; chuyển batch với idempotency; migration schema tương thích; sau cùng mới xóa cấu trúc cũ.
- Với đơn lịch sử, cần biết chính sách tại thời điểm tạo đơn, nguồn dữ liệu và cách xử lý khi thiếu thông tin. Không tự áp dụng ngưỡng hiện tại cho dữ liệu cũ nếu hợp đồng không cho phép.
- JSON là hợp đồng bên ngoài; cần giữ trường cũ, versioning hoặc cơ chế tương thích trong thời gian client chuyển.
- Job cần checkpoint/idempotency để chạy lại không tạo bản ghi hoặc side effect trùng; timeout không chứng minh lần chạy trước chưa ghi.
- Chỉ xóa công thức cũ sau khi xác minh caller, job, script và client ngoài đã chuyển; có test/telemetry hỗ trợ.
- Theo dõi sai khác tổng tiền, số đơn được tính lại, lỗi job, duplicate, latency, mismatch DB và số consumer còn dùng API cũ.

## 15. Những hiểu nhầm thường gặp

**“Mã cũ không có test thì phải viết lại trước.”** Có thể bắt đầu bằng việc lập bản đồ và thêm characterization tests cho một lát cắt quan trọng. Không cần viết lại toàn bộ để có bằng chứng đầu tiên.

**“Test cũ xanh nghĩa là hành vi đúng.”** Test có thể ghi nhận cả bug. Cần phân biệt hiện trạng và hợp đồng mục tiêu.

**“Chỉ cần test class mới.”** Caller cũ có thể vẫn dùng đường cũ hoặc truyền dữ liệu khác ngữ nghĩa. Phải kiểm tra đường gọi thật.

**“Chạy full test cuối cùng là đủ.”** Khi nhiều thay đổi chồng lên nhau, khó xác định sai khác bắt đầu ở đâu. Cần kiểm tra sau mỗi lát cắt.

**“Tách method làm cấu trúc tốt hơn tự động.”** Helper có thể tạo temporal coupling nếu đọc trạng thái ngầm hoặc phải gọi theo thứ tự bí mật.

**“So sánh code cũ và mới luôn chứng minh tương đương.”** Code cũ có thể sai. So sánh chỉ có ý nghĩa khi biết phần hành vi nào cần giữ và phần nào được sửa.

**“Có thể chạy hai phiên bản để so sánh trên production.”** Chỉ phù hợp với phép tính thuần hoặc đường đọc an toàn. Không nhân đôi thanh toán, ghi DB hay gửi thông báo.

**“Đổi schema và code trong một lần sẽ đơn giản hơn.”** Rolling deployment, job cũ và dữ liệu lịch sử có thể cần giai đoạn tương thích.

**“Không thấy caller trong module là có thể xóa API.”** Consumer bên ngoài, script hoặc job có thể không nằm trong phạm vi tìm kiếm.

**“Rollback code là quay lại trạng thái cũ.”** Side effect và dữ liệu đã ghi không tự biến mất. Có thể cần đối soát, bù trừ hoặc fix-forward.

**“Checklist hoàn tất nghĩa là không còn rủi ro.”** Checklist giúp tránh quên; kết luận vẫn phải dựa trên bằng chứng và phạm vi đã xác minh.

## 16. Ghi nhớ

- Trước khi chuyển đổi, hãy **đọc cấu trúc và đường sử dụng thực tế**: entry point, caller, dependency, luồng dữ liệu, trạng thái và side effect.
- Ghi nhận **hành vi hiện tại** và phân biệt với **hợp đồng mục tiêu**; characterization test không được vô tình biến bug cũ thành chuẩn.
- Chia công việc thành các lát cắt có ranh giới và tiêu chí hoàn tất rõ; giữ tính nguyên tử ở nơi dữ liệu hoặc nghiệp vụ yêu cầu.
- Sau **mỗi lát cắt**, đọc lại cấu trúc, xác minh caller và chạy test phù hợp cho kết quả, giá trị biên, lỗi và side effect.
- Chỉ so sánh implementation cũ/mới trên đường chạy an toàn; không nhân đôi tác dụng phụ để tạo bằng chứng.
- Với API, schema và job, cần bảo đảm tương thích, migration, idempotency và khả năng phục hồi trước khi xóa cấu trúc cũ.
- Ghi nhận sai khác, bằng chứng, rủi ro còn lại và điều kiện chuyển bước tiếp theo. Chất lượng của chuyển đổi nằm ở **khả năng hiểu và kiểm chứng từng bước**, không phải tốc độ thay được nhiều dòng code.
