# Vòng đời từ yêu cầu nghiệp vụ đến mô hình, triển khai và phản hồi sử dụng

Mô hình dữ liệu không bắt đầu từ câu lệnh tạo bảng và cũng không kết thúc khi ứng dụng chạy được. Nó hình thành từ việc hiểu nghiệp vụ, tiếp tục qua quá trình mô tả dữ liệu, kiểm chứng quy tắc, triển khai cấu trúc lưu trữ và quan sát cách hệ thống được sử dụng. Khi quy trình hoặc khối lượng công việc thay đổi, phản hồi từ vận hành lại trở thành đầu vào cho lần thiết kế tiếp theo.

Trong **data modeling**, nhiệm vụ cốt lõi là chuyển yêu cầu nghiệp vụ thành mô hình có thể kiểm chứng: xác định thực thể, thuộc tính, quan hệ, khóa, ràng buộc và cách lưu trữ. Một mô hình hữu ích phải trả lời được dữ liệu đại diện cho điều gì, ai tạo và cập nhật nó, điều gì phải luôn đúng, dữ liệu được giữ trong bao lâu và ứng dụng sẽ đọc/ghi theo cách nào.

Bài học này trình bày vòng đời đó theo từng bước, từ khám phá yêu cầu đến phản hồi sau triển khai. Ví dụ xuyên suốt là hệ thống cho thuê thiết bị, nơi khách hàng đặt thuê thiết bị theo khoảng thời gian, nhân viên bàn giao và nhận lại thiết bị, còn bộ phận vận hành cần theo dõi tình trạng và lịch sử sử dụng.

## 1. Nhìn mô hình dữ liệu như một vòng đời

Một dự án thường trải qua các hoạt động: hiểu vấn đề, mô tả yêu cầu, xây mô hình, xác minh, triển khai, vận hành và cải tiến. Những hoạt động này có thể lặp lại. Một thay đổi nhỏ về chính sách đặt cọc có thể làm xuất hiện thuộc tính mới, một thực thể thanh toán hoặc quy tắc kiểm tra khác. Một báo cáo chậm có thể cho thấy mô hình vật lý cần thêm chỉ mục hoặc kho dữ liệu phân tích.

~~~mermaid
flowchart TD
    A[Khám phá nghiệp vụ] --> B[Đặc tả yêu cầu dữ liệu]
    B --> C[Mô hình khái niệm]
    C --> D[Mô hình logic]
    D --> E[Mô hình vật lý]
    E --> F[Kiểm chứng và thử nghiệm]
    F --> G[Triển khai và chuyển đổi dữ liệu]
    G --> H[Vận hành và quan sát]
    H --> I[Phản hồi và thay đổi]
    I --> A
    I --> C
    I --> D
    I --> E
~~~

Không phải mọi thay đổi đều quay lại từ đầu. Nếu quy tắc nghiệp vụ thay đổi, cần xem lại mô hình khái niệm và logic. Nếu truy vấn chậm nhưng ý nghĩa dữ liệu vẫn đúng, có thể chỉ cần điều chỉnh chỉ mục hoặc phân vùng ở mô hình vật lý. Nếu người dùng hiểu sai một trường, vấn đề có thể nằm ở định nghĩa dữ liệu hoặc giao diện, không nhất thiết ở cấu trúc bảng.

Điều quan trọng là giữ được mối liên hệ giữa yêu cầu ban đầu, quyết định mô hình hóa, thay đổi schema và kết quả vận hành. Khi có thể truy ngược, nhóm sẽ hiểu vì sao một cột tồn tại, quy tắc nào bảo vệ nó và ảnh hưởng của việc thay đổi nó.

## 2. Khám phá nghiệp vụ trước khi thiết kế

### 2.1. Xác định vấn đề và kết quả cần đạt

Một yêu cầu như “xây cơ sở dữ liệu cho thuê thiết bị” chưa đủ để thiết kế. Cần làm rõ mục tiêu thực tế:

- Khách hàng có thể tìm thiết bị còn trống và gửi yêu cầu thuê.
- Nhân viên xác nhận thời gian, giá thuê, tiền đặt cọc và điều kiện bàn giao.
- Một thiết bị không được giao cho hai hợp đồng có khoảng thời gian sử dụng chồng lấn.
- Khi bàn giao và nhận lại, nhân viên ghi nhận thời điểm, tình trạng và phụ kiện đi kèm.
- Bộ phận vận hành xem lịch sử sử dụng, lịch bảo trì và tình trạng hiện tại của thiết bị.
- Quản lý cần báo cáo tỷ lệ sử dụng, doanh thu và số ngày thiết bị ngừng hoạt động.

Các kết quả này cho biết hệ thống cần quản lý đặt thuê, hợp đồng, thiết bị, bàn giao, bảo trì và báo cáo. Chúng cũng gợi ý những truy vấn cần hỗ trợ. Từ đó mới có thể xác định dữ liệu nào cần lưu và quan hệ giữa chúng.

### 2.2. Nhận diện các bên liên quan

Mỗi vai trò nhìn dữ liệu theo một cách khác nhau. Khách hàng quan tâm thiết bị nào còn trống, giá nào được áp dụng và hợp đồng của mình đang ở trạng thái nào. Nhân viên kho quan tâm vị trí, tình trạng, phụ kiện và thời điểm bàn giao. Bộ phận bảo trì cần lịch sử hỏng hóc và các lần sửa chữa. Kế toán cần tiền thuê, đặt cọc, khoản hoàn trả và đối soát.

Hãy xác định ai là người:

- Tạo dữ liệu mới.
- Xem hoặc tìm kiếm dữ liệu.
- Chỉnh sửa dữ liệu và trong điều kiện nào.
- Xác nhận một giao dịch hoặc chuyển trạng thái.
- Chịu trách nhiệm khi dữ liệu sai.
- Sử dụng báo cáo hoặc xuất dữ liệu.

Ma trận vai trò giúp phát hiện yêu cầu ẩn. Ví dụ, khách hàng có thể hủy yêu cầu trước khi hợp đồng được xác nhận, nhưng chỉ nhân viên được ghi nhận việc thiết bị đã bàn giao. Một quản lý có thể xem báo cáo tổng hợp nhưng không cần quyền sửa từng lần kiểm tra thiết bị.

### 2.3. Phỏng vấn bằng tình huống cụ thể

Các câu hỏi chung như “có cần lịch sử không?” thường tạo ra câu trả lời mơ hồ. Hãy hỏi theo tình huống:

- Nếu khách hàng đổi ngày trả sau khi đã nhận thiết bị, hệ thống cần lưu ngày mới hay cả ngày cũ và người chấp thuận?
- Nếu thiết bị bị hỏng khi khách hàng đang thuê, hợp đồng có kết thúc ngay không? Có thay thiết bị khác không?
- Nếu một bộ thiết bị gồm máy chính và phụ kiện, có thể cho thuê từng phần không?
- Nếu khách hàng hủy trước ngày nhận, tiền đặt cọc được xử lý thế nào?
- Nếu thiết bị được gửi bảo trì, khoảng thời gian đó có được xem là không khả dụng để đặt thuê không?
- Nếu nhân viên nhập sai số serial, ai được sửa và cần giữ dấu vết chỉnh sửa không?

Tình huống buộc các bên làm rõ điều kiện, ngoại lệ và thời điểm xảy ra sự kiện. Đây là cơ sở để xác định thuộc tính, trạng thái, quan hệ và ràng buộc.

### 2.4. Quan sát quy trình và dữ liệu hiện có

Phỏng vấn không phải nguồn thông tin duy nhất. Hãy xem biểu mẫu, bảng tính, báo cáo, quy trình giấy, dữ liệu nhập từ hệ thống cũ và các thao tác thực tế. Người dùng có thể nói “mỗi thiết bị có một mã”, nhưng bảng tính đang tồn tại có thể cho thấy mã đó bị tái sử dụng sau khi thanh lý. Đây là một khác biệt quan trọng giữa mã hiển thị và định danh ổn định.

Khi có dữ liệu mẫu, hãy kiểm tra:

- Tỷ lệ trường bị trống và ý nghĩa của giá trị trống.
- Giá trị trùng lặp và cách viết không nhất quán.
- Định dạng ngày giờ, tiền tệ, số lượng và mã định danh.
- Các giá trị ngoài dự kiến hoặc trạng thái không còn được sử dụng.
- Quan hệ tham chiếu bị thiếu hoặc không khớp.
- Những cột mà người dùng đang dùng cho nhiều mục đích khác nhau.

Phân tích dữ liệu hiện có giúp phát hiện khoảng cách giữa quy trình được mô tả và thực tế. Tuy nhiên, không nên mặc định mọi dữ liệu cũ đều đúng hoặc mọi cách nhập cũ đều phải được giữ lại.

## 3. Chuyển yêu cầu thành đặc tả dữ liệu

### 3.1. Tạo từ điển thuật ngữ

Các phòng ban có thể dùng cùng một từ với ý nghĩa khác nhau. “Thiết bị” có thể chỉ dòng sản phẩm hoặc một đơn vị vật lý có serial riêng. “Đặt thuê” có thể là yêu cầu chưa được xác nhận hoặc một hợp đồng đã có hiệu lực. “Ngày trả” có thể là ngày dự kiến hoặc ngày thực tế.

Tạo từ điển thuật ngữ để thống nhất:

| Thuật ngữ | Định nghĩa nghiệp vụ | Ghi chú mô hình |
|---|---|---|
| Dòng thiết bị | Loại thiết bị được cung cấp, ví dụ máy chiếu | Có thể có nhiều đơn vị vật lý |
| Thiết bị | Một đơn vị vật lý có mã serial riêng | Có tình trạng và vị trí hiện tại |
| Yêu cầu thuê | Đề nghị thuê trong một khoảng thời gian | Có thể bị từ chối hoặc hủy |
| Hợp đồng thuê | Thỏa thuận đã được xác nhận | Có giá và điều kiện tại thời điểm ký |
| Lần bàn giao | Sự kiện chuyển thiết bị giữa các bên | Có thời điểm, người thực hiện và tình trạng |
| Phiếu bảo trì | Công việc kiểm tra hoặc sửa chữa thiết bị | Có thời gian bắt đầu và kết thúc |

Từ điển giúp tránh việc đặt tên cột trước khi hiểu khái niệm. Nó cũng là tài liệu tham chiếu khi viết API, giao diện, báo cáo và hướng dẫn sử dụng.

### 3.2. Phân loại yêu cầu

Yêu cầu dữ liệu nên được phân loại để dễ kiểm chứng:

| Nhóm | Ví dụ | Cách thể hiện |
|---|---|---|
| Dữ liệu cần lưu | Serial, tên thiết bị, khách hàng, thời gian thuê | Thực thể và thuộc tính |
| Quan hệ | Một khách hàng có nhiều hợp đồng | Quan hệ và khóa ngoại |
| Ràng buộc | Không đặt trùng một thiết bị trong hai hợp đồng hiệu lực | Quy tắc nghiệp vụ, transaction hoặc constraint phù hợp |
| Trạng thái và vòng đời | Yêu cầu, xác nhận, đang thuê, hoàn tất | State machine và lịch sử chuyển trạng thái |
| Truy vấn | Tìm thiết bị khả dụng theo ngày và loại | Mẫu truy cập và chỉ mục |
| Báo cáo | Tỷ lệ sử dụng theo tháng | Sự kiện, dữ liệu tổng hợp hoặc mô hình phân tích |
| Phi chức năng | Phản hồi tìm kiếm trong giới hạn thời gian | Mục tiêu hiệu năng và kiểm thử tải |
| Quản trị | Ai được sửa hợp đồng đã ký | Quyền truy cập và audit |

Việc phân loại ngăn một yêu cầu giao diện bị hiểu nhầm thành yêu cầu lưu trữ. Ví dụ, người dùng muốn xem “tổng số ngày thuê” không có nghĩa bắt buộc phải lưu một cột tổng số ngày; có thể tính từ các khoảng thời gian đã chốt. Nếu lưu sẵn vì lý do hiệu năng, cần quy định cách cập nhật và đối soát.

### 3.3. Viết quy tắc có thể kiểm thử

Một quy tắc tốt phải nêu rõ điều kiện, thời điểm và kết quả. Ví dụ:

> Khi hợp đồng đã xác nhận một thiết bị vật lý trong khoảng thời gian thuê, hệ thống không được xác nhận hợp đồng khác có khoảng thời gian giao nhau với khoảng đó, trừ khi thiết bị đã được thay thế hoặc hợp đồng trước đã được hủy hợp lệ.

Quy tắc này rõ hơn câu “thiết bị không được đặt trùng”. Nó gợi ý cần biết thiết bị vật lý nào được gán cho hợp đồng, trạng thái nào chiếm dụng lịch và cách xác định hai khoảng thời gian giao nhau.

Một số quy tắc khác:

- Ngày kết thúc phải sau ngày bắt đầu.
- Tiền đặt cọc không âm và dùng cùng loại tiền tệ đã quy định cho hợp đồng.
- Chỉ hợp đồng đã xác nhận mới tạo lịch chiếm dụng thiết bị.
- Mỗi lần bàn giao phải gắn với một hợp đồng và một thiết bị cụ thể.
- Một thiết bị đang trong đợt bảo trì không được phân bổ cho hợp đồng mới trong khoảng thời gian đó.

Quy tắc nên có ví dụ hợp lệ và không hợp lệ để các bên xác nhận. Điều này làm giảm nguy cơ mỗi nhóm tự diễn giải cùng một câu chữ theo cách khác nhau.

### 3.4. Xác định dữ liệu nguồn và chủ sở hữu

Với mỗi khái niệm, hãy xác định hệ thống hoặc bộ phận nào là nguồn tạo và xác nhận sự thật. Ví dụ, danh mục thiết bị có thể do bộ phận kho quản lý; hợp đồng do bộ phận cho thuê xác nhận; giao dịch tiền do hệ thống thanh toán ghi nhận. Báo cáo có thể sao chép dữ liệu từ các nguồn này nhưng không nên trở thành nơi chỉnh sửa dữ liệu gốc.

Một ma trận CRUD đơn giản giúp làm rõ quyền sở hữu:

| Dữ liệu | Tạo | Đọc | Cập nhật | Hủy/xóa |
|---|---|---|---|---|
| Danh mục thiết bị | Nhân viên kho | Các bộ phận liên quan | Nhân viên được phân quyền | Đánh dấu ngừng sử dụng |
| Yêu cầu thuê | Khách hàng hoặc nhân viên | Khách hàng, nhân viên | Theo trạng thái yêu cầu | Hủy theo chính sách |
| Hợp đồng | Nhân viên xác nhận | Khách hàng, vận hành, kế toán | Theo quy trình điều chỉnh | Thường lưu lịch sử, không xóa vật lý |
| Bàn giao | Nhân viên thực hiện | Vận hành, khách hàng liên quan | Sửa có kiểm soát và audit | Không xóa sự kiện đã xác nhận |
| Bảo trì | Nhân viên kỹ thuật | Kho, quản lý | Cập nhật tiến độ và kết quả | Lưu lịch sử |

Nguồn sự thật, quyền cập nhật và lịch sử cần được xác định trước khi chọn công nghệ lưu trữ.

## 4. Xây dựng mô hình khái niệm

Mô hình khái niệm mô tả các khái niệm nghiệp vụ và quan hệ của chúng bằng ngôn ngữ mà chuyên gia nghiệp vụ có thể kiểm tra. Nó chưa cần quyết định kiểu dữ liệu cụ thể, tên index hay cú pháp của hệ quản trị.

### 4.1. Tìm thực thể và phân biệt thực thể với thuộc tính

Một khái niệm nên trở thành thực thể khi nó có định danh, vòng đời hoặc quan hệ riêng. Trong hệ thống cho thuê:

- Customer có thể tạo nhiều yêu cầu và hợp đồng.
- EquipmentModel mô tả dòng thiết bị, ví dụ máy chiếu loại A.
- Equipment là đơn vị vật lý cụ thể, có serial và tình trạng.
- RentalRequest là đề nghị thuê đang chờ xử lý.
- RentalContract là thỏa thuận đã xác nhận.
- ContractEquipment liên kết hợp đồng với thiết bị được phân bổ.
- Handover ghi nhận lần giao hoặc nhận thiết bị.
- Maintenance ghi nhận thời gian và công việc bảo trì.

Không nên tạo thực thể chỉ vì một danh từ xuất hiện trong tài liệu. Một thuộc tính như màu vỏ có thể chỉ là trường của Equipment. Ngược lại, địa điểm kho có thể cần thực thể riêng nếu có mã, địa chỉ, giờ hoạt động và nhiều thiết bị thuộc về nó.

### 4.2. Xác định quan hệ và lực lượng quan hệ

Mô hình khái niệm có thể được minh họa:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ RENTAL_REQUEST : submits
    CUSTOMER ||--o{ RENTAL_CONTRACT : signs
    RENTAL_REQUEST o|--o| RENTAL_CONTRACT : may_become
    RENTAL_CONTRACT ||--|{ CONTRACT_EQUIPMENT : allocates
    EQUIPMENT ||--o{ CONTRACT_EQUIPMENT : assigned_to
    EQUIPMENT_MODEL ||--o{ EQUIPMENT : describes
    EQUIPMENT ||--o{ HANDOVER : recorded_for
    RENTAL_CONTRACT ||--o{ HANDOVER : includes
    EQUIPMENT ||--o{ MAINTENANCE : has
    CUSTOMER {
        string customer_code
        string display_name
    }
    EQUIPMENT {
        string serial_number
        string condition
    }
    RENTAL_CONTRACT {
        string contract_number
        date start_date
        date end_date
    }
~~~

Một khách hàng có thể có nhiều hợp đồng. Một hợp đồng có thể phân bổ nhiều thiết bị; một thiết bị cũng có thể xuất hiện trong nhiều hợp đồng ở các thời điểm khác nhau. Vì vậy, quan hệ giữa RentalContract và Equipment là nhiều-nhiều theo thời gian và cần một thực thể liên kết để lưu khoảng thời gian phân bổ, giá áp dụng hoặc trạng thái.

Quan hệ một-một, một-nhiều và nhiều-nhiều cần được xác nhận từ quy tắc nghiệp vụ. Đừng suy ra lực lượng quan hệ chỉ từ giao diện hiện tại. Nếu một hợp đồng hiện chỉ thuê một thiết bị nhưng có khả năng thuê bộ thiết bị, cần hỏi rõ đây là giới hạn nghiệp vụ hay giới hạn tạm thời của màn hình.

### 4.3. Xem xét thực thể kết hợp và thực thể phụ thuộc

Khi một quan hệ nhiều-nhiều có thuộc tính riêng, hãy mô hình hóa quan hệ thành thực thể kết hợp. ContractEquipment có thể lưu:

- Hợp đồng nào.
- Thiết bị nào.
- Thời gian phân bổ.
- Giá thuê áp dụng cho thiết bị.
- Tình trạng khi bàn giao.
- Tình trạng khi nhận lại.

Một Handover là sự kiện có thời điểm, người thực hiện và biên bản. Nó có thể phụ thuộc vào hợp đồng và thiết bị, nhưng vẫn có định danh riêng vì cần truy xuất, kiểm tra và lưu lịch sử. Ngược lại, một dòng mô tả phụ kiện nằm trong biên bản có thể được định danh bằng cặp (handover_id, line_no) nếu không cần vòng đời độc lập.

### 4.4. Phân biệt trạng thái với sự kiện

Trạng thái mô tả tình hình hiện tại, ví dụ thiết bị đang sẵn sàng, đang được thuê, đang bảo trì hoặc đã thanh lý. Sự kiện mô tả điều đã xảy ra, ví dụ thiết bị được bàn giao lúc 09:15 hoặc được đưa vào bảo trì ngày 12/05.

Nếu chỉ lưu trạng thái hiện tại, nhóm có thể biết thiết bị đang bảo trì nhưng không biết ai đưa vào bảo trì, khi nào và vì sao. Nếu chỉ lưu sự kiện mà không có cách suy ra trạng thái, các màn hình vận hành có thể phải tính toán lại toàn bộ lịch sử mỗi lần đọc.

Có thể lưu trạng thái hiện tại để truy cập nhanh cùng lịch sử sự kiện để kiểm toán. Khi đó, cần quy định cập nhật trạng thái và ghi sự kiện trong cùng transaction hoặc cơ chế đáng tin cậy tương đương. Không nên để hai nguồn dữ liệu lệch nhau mà không có cách phát hiện.

## 5. Chuyển sang mô hình logic

Mô hình logic cụ thể hóa thực thể thành quan hệ, thuộc tính, khóa và ràng buộc. Với cơ sở dữ liệu quan hệ, đây là bước xác định bảng, cột và cách liên kết mà chưa cần tối ưu theo một máy chủ cụ thể.

### 5.1. Xác định khóa

Mỗi thực thể cần một cách định danh ổn định. Serial thiết bị có thể là mã tự nhiên, nhưng cần xác nhận nó duy nhất toàn hệ thống, có thể thay đổi hay không và có thể bị tái sử dụng sau khi thiết bị thanh lý không. Nếu có rủi ro thay đổi, có thể dùng equipment_id làm khóa chính và đặt unique constraint trên serial hiện tại.

Các loại khóa thường gặp:

- **Khóa chính (primary key):** định danh mỗi hàng trong bảng.
- **Khóa ứng viên (candidate key):** tập thuộc tính tối thiểu có thể định danh duy nhất.
- **Khóa tự nhiên (natural key):** định danh có ý nghĩa nghiệp vụ, như mã hợp đồng hoặc serial.
- **Khóa thay thế (surrogate key):** định danh kỹ thuật ổn định, như số nguyên hoặc UUID.
- **Khóa ngoại (foreign key):** liên kết hàng với hàng ở bảng khác.
- **Khóa ghép (composite key):** kết hợp nhiều thuộc tính để định danh, như (contract_id, equipment_id, start_at) trong một số mô hình phân bổ.

Không nên dùng khóa thay thế để thay thế mọi quy tắc duy nhất. Nếu contract_number phải duy nhất, vẫn cần unique constraint. Khóa chính ổn định và ràng buộc nghiệp vụ có thể cùng tồn tại.

### 5.2. Chọn thuộc tính và kiểu dữ liệu theo ý nghĩa

Thuộc tính cần được định nghĩa cả về kiểu và ý nghĩa:

| Thuộc tính | Kiểu logic gợi ý | Điều cần làm rõ |
|---|---|---|
| serial_number | Chuỗi | Có phân biệt hoa thường, khoảng trắng hoặc ký tự đặc biệt không? |
| start_at, end_at | Thời điểm có múi giờ hoặc ngày | Khoảng thời gian tính theo ngày địa phương hay thời điểm tuyệt đối? |
| daily_rate | Số thập phân chính xác | Quy tắc làm tròn và loại tiền tệ là gì? |
| condition | Miền giá trị hữu hạn | Những trạng thái nào được phép và ai xác nhận? |
| notes | Văn bản | Có giới hạn độ dài, quy tắc tìm kiếm hoặc yêu cầu lưu trữ không? |
| is_active | Boolean | Không hoạt động có đồng nghĩa đã thanh lý không? |

Tên trường nên thể hiện ý nghĩa rõ. created_at là thời điểm tạo bản ghi; start_at là thời điểm bắt đầu thuê. Tránh các tên mơ hồ như date, value, type nếu không có ngữ cảnh.

Ngày và thời điểm cần được phân biệt. Ngày thuê có thể là ngày lịch địa phương, còn thời điểm bàn giao là một thời điểm cụ thể. Nếu lưu timestamp, cần quy định cách lưu múi giờ và cách hiển thị. Nếu khoảng thuê tính theo ngày, cần xác định hai đầu khoảng có bao gồm hay không. Chẳng hạn khoảng [10/06, 12/06) có thể hiểu là bắt đầu ngày 10 và kết thúc đầu ngày 12, gồm hai ngày thuê.

Tiền cần lưu số thập phân chính xác hoặc đơn vị nhỏ nhất của tiền tệ, tránh kiểu số thực nhị phân cho số tiền. Cần lưu currency cùng số tiền khi hệ thống có nhiều loại tiền.

### 5.3. Xác định NULL, mặc định và miền giá trị

NULL có nghĩa là chưa biết hoặc chưa có giá trị theo định nghĩa của thuộc tính. Nó không nên được dùng thay cho mọi trạng thái đặc biệt. Ví dụ, returned_at có thể NULL khi thiết bị chưa được nhận lại. Nhưng nếu cần phân biệt “chưa đến ngày trả” với “đã quá hạn”, đó có thể là trạng thái suy ra từ thời gian và trạng thái hợp đồng, không cần nhồi nhiều nghĩa vào NULL.

Giá trị mặc định phải phản ánh nghiệp vụ. Mặc định condition = 'good' khi tạo thiết bị mới có thể sai nếu thiết bị chưa được kiểm tra. Có thể dùng 'inspection_pending' để phản ánh trạng thái chưa xác minh.

Các miền giá trị như status, condition và currency cần được xác thực. Có thể dùng CHECK constraint, bảng danh mục hoặc kiểu enum tùy mức độ thay đổi và hệ quản trị. Nếu danh sách trạng thái có thể được quản trị viên mở rộng, bảng danh mục có thể phù hợp hơn một enum cố định.

### 5.4. Chuẩn hóa để làm rõ nguồn dữ liệu

Chuẩn hóa giúp tránh lưu cùng một sự thật ở nhiều nơi. Tên dòng thiết bị thuộc EquipmentModel; serial và tình trạng thuộc Equipment; tên khách hàng thuộc Customer. Nếu mỗi hợp đồng lưu lại tên dòng thiết bị để bảo toàn cách gọi tại thời điểm ký, cần xác định đó là snapshot có chủ đích.

Hãy tìm các phụ thuộc hàm. Nếu equipment_id xác định serial_number, model_id và warehouse_id, những thuộc tính đó phụ thuộc vào thiết bị. Nếu model_id xác định model_name và manufacturer, các thuộc tính tên và nhà sản xuất thuộc về EquipmentModel. Lưu tên model lặp lại trên mọi thiết bị có thể gây bất thường cập nhật.

Chuẩn hóa là điểm xuất phát để dữ liệu nhất quán. Sau khi hiểu truy vấn thực tế, có thể lưu thêm dữ liệu dẫn xuất hoặc snapshot có mục đích, nhưng phải ghi rõ nguồn sự thật và cách đối soát.

## 6. Thiết kế ràng buộc từ quy tắc nghiệp vụ

Ràng buộc là cách biến quy tắc thành điều kiện mà dữ liệu phải tuân thủ. Một số quy tắc có thể được bảo vệ ngay trong cơ sở dữ liệu:

- Serial thiết bị không được trùng.
- Mỗi hợp đồng phải tham chiếu khách hàng tồn tại.
- Ngày kết thúc phải sau ngày bắt đầu.
- Tiền thuê và tiền đặt cọc không âm.
- Mỗi dòng phân bổ phải tham chiếu một thiết bị và hợp đồng hợp lệ.

Ví dụ SQL minh họa một phần mô hình logic:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_code VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE equipment_models (
    model_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_code VARCHAR(40) NOT NULL UNIQUE,
    model_name VARCHAR(200) NOT NULL
);

CREATE TABLE equipment (
    equipment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL REFERENCES equipment_models(model_id),
    serial_number VARCHAR(100) NOT NULL UNIQUE,
    condition VARCHAR(30) NOT NULL
        CHECK (condition IN ('inspection_pending', 'good', 'damaged', 'retired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rental_contracts (
    contract_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contract_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    currency CHAR(3) NOT NULL,
    deposit_amount NUMERIC(14, 2) NOT NULL DEFAULT 0
        CHECK (deposit_amount >= 0),
    status VARCHAR(30) NOT NULL
        CHECK (status IN ('draft', 'confirmed', 'active', 'completed', 'cancelled')),
    CHECK (end_at > start_at)
);

CREATE TABLE contract_equipment (
    contract_id BIGINT NOT NULL REFERENCES rental_contracts(contract_id),
    equipment_id BIGINT NOT NULL REFERENCES equipment(equipment_id),
    allocated_from TIMESTAMPTZ NOT NULL,
    allocated_until TIMESTAMPTZ NOT NULL,
    daily_rate NUMERIC(14, 2) NOT NULL CHECK (daily_rate >= 0),
    CHECK (allocated_until > allocated_from),
    PRIMARY KEY (contract_id, equipment_id)
);
~~~

Ví dụ trên chưa giải quyết đầy đủ việc chống chồng lấn lịch thuê, vì quy tắc đó phụ thuộc vào các hàng khác và trạng thái hợp đồng. Một CHECK trên cùng hàng không đủ để kiểm tra khoảng thời gian với mọi hợp đồng khác. Có thể dùng exclusion constraint nếu hệ quản trị hỗ trợ kiểu khoảng và điều kiện phù hợp, hoặc dùng transaction với khóa/chiến lược đồng thời được thiết kế cẩn thận. Không nên chỉ SELECT kiểm tra lịch trống rồi INSERT riêng rẽ mà không bảo vệ trước hai yêu cầu đồng thời.

Hãy phân loại ràng buộc:

| Phạm vi | Ví dụ | Cơ chế thường dùng |
|---|---|---|
| Một thuộc tính | daily_rate không âm | CHECK |
| Một hàng | end_at lớn hơn start_at | CHECK |
| Duy nhất | serial_number không trùng | UNIQUE |
| Tham chiếu | contract.customer_id phải tồn tại | FOREIGN KEY |
| Nhiều hàng | Không có lịch thuê chồng lấn | Transaction, khóa hoặc constraint chuyên biệt |
| Quy trình | Chỉ hợp đồng đã xác nhận mới được bàn giao | Logic chuyển trạng thái và kiểm soát giao dịch |

Không phải mọi quy tắc đều có thể mô tả bằng một constraint đơn giản. Nhưng cần biết rõ quy tắc nào đang được bảo vệ ở đâu và làm thế nào để kiểm thử nó.

## 7. Từ mô hình logic đến mô hình vật lý

Mô hình vật lý quyết định cách cấu trúc được triển khai trên hệ quản trị cụ thể. Ở bước này, nhóm cần xét kích thước dữ liệu, workload, độ sẵn sàng, sao lưu, khôi phục và khả năng mở rộng.

### 7.1. Chọn hệ quản trị theo yêu cầu

Không nên chọn cơ sở dữ liệu chỉ theo mức độ phổ biến. Hãy đánh giá:

- Mức độ quan hệ và ràng buộc cần bảo vệ.
- Yêu cầu transaction và tính nhất quán.
- Kiểu truy vấn: tra cứu theo khóa, tìm kiếm văn bản, duyệt đồ thị hay tổng hợp lớn.
- Khối lượng đọc/ghi, dữ liệu tăng trưởng và mức đồng thời.
- Cơ chế sao lưu, phục hồi, replication và phân vùng.
- Năng lực vận hành, công cụ giám sát và kỹ năng của nhóm.
- Chi phí bản quyền, hạ tầng và chuyển đổi khi cần.

Với hệ thống cho thuê, cơ sở dữ liệu quan hệ thường là lựa chọn hợp lý cho hợp đồng, khách hàng, phân bổ thiết bị và thanh toán vì có nhiều quan hệ và quy tắc giao dịch. Có thể bổ sung kho phân tích riêng cho báo cáo dài hạn nếu workload báo cáo gây ảnh hưởng đến giao dịch.

### 7.2. Thiết kế chỉ mục từ truy vấn

Chỉ mục cần xuất phát từ truy vấn đã xác định. Ví dụ:

- Tìm hợp đồng theo contract_number.
- Tìm các hợp đồng của một khách hàng theo thời gian.
- Tìm lịch phân bổ của một thiết bị trong một khoảng ngày.
- Tìm thiết bị theo model và condition.
- Liệt kê các đợt bảo trì đang mở.

Một chỉ mục ghép trên (customer_id, start_at) có thể hỗ trợ lịch sử thuê của khách hàng. Một chỉ mục trên (model_id, condition) có thể hỗ trợ bộ lọc danh sách thiết bị. Nhưng chỉ mục cần dung lượng và chi phí cập nhật khi ghi. Hãy kiểm tra execution plan và tần suất truy vấn trước khi thêm.

### 7.3. Phân vùng và tăng trưởng dữ liệu

Nếu bảng lịch sử bàn giao tăng rất lớn theo thời gian, có thể cân nhắc phân vùng theo tháng hoặc năm để quản lý dữ liệu và truy vấn theo khoảng thời gian. Phân vùng không tự động làm mọi truy vấn nhanh hơn; điều kiện lọc cần cho phép hệ quản trị loại bỏ các phân vùng không liên quan.

Trước khi phân vùng, cần biết:

- Bảng nào tăng nhanh và tốc độ tăng bao nhiêu?
- Truy vấn thường lọc theo thời gian nào?
- Khóa chính và unique constraint có tương thích với chiến lược phân vùng không?
- Dữ liệu cũ được lưu trực tuyến, lưu trữ lạnh hay xóa theo chính sách nào?
- Việc tạo và xóa phân vùng có thể tự động hóa và kiểm soát ra sao?

Đừng thêm phân vùng chỉ vì dự đoán bảng sẽ lớn. Hãy theo dõi dữ liệu thực tế và ngưỡng vận hành để chọn thời điểm phù hợp.

### 7.4. Lập chính sách vòng đời dữ liệu

Mỗi loại dữ liệu có thể cần thời hạn lưu khác nhau. Hợp đồng và biên bản có thể phải giữ lâu theo yêu cầu pháp lý hoặc kiểm toán; dữ liệu phiên làm việc tạm thời có thể hết hạn sớm; log kỹ thuật có thể được lưu theo chính sách vận hành.

Chính sách cần trả lời:

- Dữ liệu nào là hồ sơ chính thức?
- Dữ liệu nào có thể lưu trữ lạnh?
- Dữ liệu nào được ẩn danh hoặc xóa sau thời hạn?
- Ai phê duyệt việc xóa hoặc xuất dữ liệu?
- Có cần giữ bản sao lưu trong một khoảng thời gian sau khi xóa không?
- Làm thế nào để xử lý yêu cầu sửa hoặc xóa dữ liệu mà vẫn giữ nghĩa vụ lưu hồ sơ?

Không nên dùng một quy tắc xóa chung cho mọi bảng. Quan hệ giữa hợp đồng, thanh toán, bàn giao và bảo trì có thể yêu cầu lưu lịch sử lâu hơn hồ sơ tạm.

## 8. Kiểm chứng mô hình trước khi triển khai

Một sơ đồ đẹp chưa chứng minh mô hình đáp ứng nghiệp vụ. Cần xác minh với các bên liên quan và dữ liệu mẫu.

### 8.1. Walkthrough theo kịch bản

Chạy từng kịch bản qua mô hình:

1. Khách hàng gửi yêu cầu thuê hai thiết bị trong ba ngày.
2. Nhân viên xác nhận yêu cầu và gán hai thiết bị vật lý.
3. Hợp đồng được ký; giá và tiền đặt cọc được chốt.
4. Nhân viên bàn giao thiết bị, ghi nhận tình trạng và phụ kiện.
5. Khách hàng gia hạn một thiết bị thêm một ngày.
6. Nhân viên nhận lại thiết bị, ghi tình trạng và khoản phát sinh.
7. Thiết bị bị hỏng được chuyển sang bảo trì.
8. Quản lý xem báo cáo ngày thuê thực tế và thời gian ngừng hoạt động.

Ở mỗi bước, hỏi: dữ liệu nào được tạo, hàng nào thay đổi, sự kiện nào cần lưu, transaction nào phải nguyên tử, ai có quyền thực hiện và có thể truy vấn lại lịch sử hay không?

Nếu một bước cần lưu thông tin mà mô hình không có chỗ phù hợp, có thể thiếu thực thể hoặc thuộc tính. Nếu phải lưu cùng một sự thật ở nhiều bảng mà không có quy tắc đồng bộ, ranh giới mô hình có thể chưa rõ.

### 8.2. Kiểm thử tình huống biên

Đừng chỉ kiểm tra luồng thành công. Hãy thử:

- Hai khách hàng đồng thời đặt cùng một thiết bị trong cùng khoảng thời gian.
- Hợp đồng bị hủy sau khi thiết bị đã được phân bổ.
- Ngày kết thúc đúng bằng thời điểm bắt đầu của hợp đồng kế tiếp.
- Thiết bị đang bảo trì nhưng nhân viên cố gắng phân bổ.
- Thiết bị được thay thế giữa thời gian thuê.
- Khách hàng gia hạn khi đã có hợp đồng khác chờ sử dụng.
- Bản ghi bàn giao bị gửi lặp do người dùng nhấn nút hai lần.
- Dữ liệu import có serial trùng hoặc ngày kết thúc nhỏ hơn ngày bắt đầu.

Những tình huống này thường phát hiện lỗi về khoảng thời gian, trạng thái, tính duy nhất và thao tác đồng thời.

### 8.3. Kiểm tra dữ liệu mẫu và khả năng truy vấn

Tạo dữ liệu mẫu đủ đa dạng: thiết bị mới, thiết bị đang thuê, thiết bị bảo trì, hợp đồng đã hủy, hợp đồng có nhiều thiết bị và nhiều lần bàn giao. Thử chạy các truy vấn quan trọng và xác minh kết quả với người dùng nghiệp vụ.

Một truy vấn trả kết quả đúng với năm bản ghi có thể không còn phù hợp khi có hàng triệu bản ghi. Vì vậy, cần kiểm tra cả tính đúng và kế hoạch thực thi trên quy mô dữ liệu dự kiến. Dùng EXPLAIN hoặc công cụ tương đương để hiểu hệ quản trị quét bảng, dùng chỉ mục hay thực hiện phép nối như thế nào.

### 8.4. Dùng prototype để kiểm tra giả định

Prototype có thể là một schema nhỏ, một truy vấn mẫu hoặc một luồng API đơn giản. Mục tiêu của nó là kiểm tra giả định có rủi ro cao trước khi triển khai rộng:

- Có thể ngăn hai lịch thuê chồng lấn một cách an toàn không?
- Truy vấn tìm thiết bị còn trống có đáp ứng tải dự kiến không?
- Có thể truy xuất lịch sử tình trạng của thiết bị mà không phải lưu trùng dữ liệu quá nhiều không?
- Quy trình migration có chạy được trên bản sao dữ liệu gần thực tế không?

Prototype không phải phiên bản sản phẩm thu nhỏ bắt buộc phải giữ lại. Nếu giả định sai, hãy điều chỉnh mô hình trước khi chi phí thay đổi tăng lên.

## 9. Triển khai schema và chuyển đổi dữ liệu

### 9.1. Quản lý thay đổi bằng migration

Schema là một phần của mã nguồn và cần được quản lý phiên bản. Mỗi migration nên có mục tiêu rõ, có thể kiểm tra, có thứ tự và có cách phục hồi hoặc tiếp tục nếu gặp lỗi.

Ví dụ, khi cần thêm trường location_code cho thiết bị:

1. Thêm cột mới cho phép NULL hoặc có giá trị mặc định an toàn.
2. Triển khai ứng dụng có thể đọc và ghi trường mới.
3. Backfill dữ liệu cũ từ nguồn đã xác nhận.
4. Kiểm tra số lượng hàng đã được cập nhật và giá trị không hợp lệ.
5. Chuyển ứng dụng sang yêu cầu trường mới.
6. Thêm NOT NULL hoặc ràng buộc cần thiết sau khi dữ liệu đã đạt yêu cầu.

Đây là cách mở rộng trước, chuyển dữ liệu và ứng dụng, rồi mới siết chặt cấu trúc. Nó giảm rủi ro khi nhiều phiên bản ứng dụng cùng hoạt động trong quá trình phát hành.

### 9.2. Chuyển đổi dữ liệu cũ

Migration dữ liệu cần có quy tắc ánh xạ giữa cấu trúc cũ và mới. Ví dụ, một bảng thiết bị cũ có cột model_name dạng văn bản; mô hình mới tách EquipmentModel thành bảng riêng. Cần xác định cách nhóm tên tương đương, xử lý lỗi chính tả, giá trị thiếu và tên không thể đối chiếu.

Một quy trình chuyển đổi an toàn thường gồm:

- Sao lưu và xác minh có thể khôi phục.
- Lập bản đồ trường nguồn sang trường đích.
- Chuẩn hóa định dạng và xử lý dữ liệu lỗi theo quy tắc đã được duyệt.
- Nạp thử trên môi trường kiểm thử.
- Đối chiếu số lượng bản ghi, tổng tiền, khóa tham chiếu và các chỉ số nghiệp vụ.
- Chạy thử các truy vấn quan trọng trên dữ liệu mới.
- Lập kế hoạch chuyển đổi chính thức, theo dõi lỗi và phương án quay lại.

Không nên âm thầm tự đoán dữ liệu thiếu. Nếu không thể xác định một dòng thiết bị thuộc model nào, hãy đưa vào danh sách cần xử lý hoặc vùng cách ly thay vì gán ngẫu nhiên.

### 9.3. Triển khai tương thích

Trong hệ thống đang chạy, ứng dụng cũ và mới có thể cùng truy cập cơ sở dữ liệu trong một khoảng thời gian. Vì vậy, đổi tên hoặc xóa cột ngay lập tức có thể làm phiên bản cũ lỗi.

Chiến lược expand–migrate–contract giúp triển khai theo giai đoạn:

1. **Expand:** thêm cột/bảng mới và giữ cấu trúc cũ.
2. **Migrate:** backfill, ghi đồng thời hoặc chuyển dần dữ liệu theo cách kiểm soát.
3. **Switch:** chuyển luồng đọc sang cấu trúc mới sau khi xác minh.
4. **Contract:** loại bỏ cấu trúc cũ khi không còn ứng dụng phụ thuộc.

Với bảng lớn, cần xem xét thời gian khóa, tải I/O, replication lag và kích thước batch. Một migration chạy nhanh trên dữ liệu thử nhỏ có thể gây gián đoạn khi chạy trên dữ liệu thật.

## 10. Vận hành và thu thập phản hồi

Sau triển khai, mô hình cần được đánh giá qua dữ liệu và cách người dùng thực sự sử dụng hệ thống.

### 10.1. Theo dõi chất lượng dữ liệu

Một số chỉ số có thể theo dõi:

- Tỷ lệ thiết bị thiếu serial hoặc model.
- Số hợp đồng có khoảng thời gian không hợp lệ.
- Số tham chiếu bị thiếu hoặc dữ liệu mồ côi.
- Số lần bàn giao thiếu người thực hiện hoặc thời điểm.
- Số trường hợp lịch thuê chồng lấn bị từ chối.
- Chênh lệch giữa tổng tiền hợp đồng và các thành phần tiền.
- Tỷ lệ bản ghi bị lỗi trong luồng import.

Chỉ số cần có ngưỡng và người chịu trách nhiệm. Một cảnh báo “có dữ liệu sai” không đủ hữu ích nếu không biết bảng nào, quy tắc nào và ai xử lý.

### 10.2. Theo dõi hiệu năng và cách truy cập

Quan sát các truy vấn chậm, tần suất đọc/ghi, kích thước bảng, chỉ mục ít được dùng, khóa tranh chấp và thời gian migration. Khi người dùng thường xuyên lọc theo một trường mới, đó có thể là tín hiệu cần thêm chỉ mục hoặc thiết kế lại truy vấn.

Không nên thêm chỉ mục cho mọi trường xuất hiện trong bộ lọc. Hãy xác định truy vấn thực tế, phân bố dữ liệu và chi phí ghi. Với hệ thống báo cáo, có thể tách workload hoặc tạo mô hình phân tích riêng nếu việc tổng hợp ảnh hưởng đến giao dịch.

### 10.3. Thu thập phản hồi người dùng

Phản hồi có thể đến từ phỏng vấn, hỗ trợ khách hàng, yêu cầu thay đổi, quan sát thao tác hoặc phân tích báo cáo. Hãy phân loại:

- Người dùng không tìm thấy dữ liệu vì thiếu trường hoặc thiếu bộ lọc.
- Người dùng nhập cùng thông tin nhiều lần vì chưa có nguồn dữ liệu dùng chung.
- Một trạng thái không phản ánh đúng quy trình thực tế.
- Một báo cáo cho kết quả khác với cách bộ phận nghiệp vụ tính.
- Một bước xác nhận quá chậm vì truy vấn hoặc thao tác dữ liệu không phù hợp.

Đừng chuyển mọi phản hồi thành cột mới. Hãy hỏi vấn đề nằm ở định nghĩa dữ liệu, giao diện, quy trình, quyền truy cập hay hiệu năng. Một yêu cầu hiển thị có thể được giải quyết ở lớp truy vấn hoặc báo cáo mà không cần thay đổi mô hình lưu trữ.

### 10.4. Đánh giá tác động trước khi thay đổi

Trước khi sửa schema, cần xác định:

- Bảng, API, báo cáo, job và dịch vụ nào đang sử dụng trường hoặc quan hệ đó?
- Dữ liệu cũ có thể chuyển đổi tự động không?
- Thay đổi có ảnh hưởng khóa, ràng buộc hoặc ý nghĩa lịch sử không?
- Ứng dụng cũ có tương thích không?
- Cần backfill, reindex hay rebuild bảng tổng hợp không?
- Làm sao phát hiện thay đổi gây sai lệch?

Mỗi thay đổi quan trọng nên có ghi nhận quyết định: bối cảnh, lựa chọn, lý do, đánh đổi, người phê duyệt và cách kiểm chứng. Tài liệu này giúp nhóm duy trì tính nhất quán khi thành viên hoặc yêu cầu thay đổi.

## 11. Quản trị mô hình và tài liệu hóa

Mô hình dữ liệu là tài sản dùng chung của nhiều nhóm. Nếu tên cột và ý nghĩa chỉ nằm trong đầu một người, việc bảo trì sẽ phụ thuộc vào kiến thức cá nhân.

### 11.1. Những tài liệu nên duy trì

- **Từ điển dữ liệu:** tên trường, định nghĩa, kiểu, đơn vị, giá trị hợp lệ và ví dụ.
- **Sơ đồ thực thể quan hệ:** thực thể, quan hệ, lực lượng quan hệ và khóa.
- **Ma trận CRUD:** vai trò nào tạo, đọc, cập nhật hoặc xóa dữ liệu.
- **Quy tắc nghiệp vụ:** điều kiện, ngoại lệ và cách kiểm thử.
- **Migration log:** phiên bản schema, mục đích và tác động.
- **Data lineage:** dữ liệu đến từ đâu, được biến đổi thế nào và đi tới báo cáo nào.
- **Quyết định kiến trúc:** lý do chọn mô hình hoặc cơ chế lưu trữ.

Tài liệu cần được cập nhật cùng thay đổi schema. Một sơ đồ cũ có thể gây hiểu nhầm hơn việc không có sơ đồ, vì người đọc tin vào thông tin đã lỗi thời.

### 11.2. Quy ước đặt tên

Quy ước nhất quán giúp đọc schema và truy vấn dễ hơn. Hãy chọn một kiểu đặt tên cho bảng, cột, khóa và chỉ mục; tránh trộn số ít/số nhiều hoặc viết tắt không có định nghĩa.

Tên nên phản ánh khái niệm nghiệp vụ: rental_contracts, equipment, handovers. Trường thời gian nên nói rõ là created_at, handed_over_at hay expected_return_at. Tránh tên chung chung như date1 hoặc status2.

Nếu hệ thống đa ngôn ngữ, có thể dùng tên kỹ thuật ổn định bằng tiếng Anh nhưng giữ định nghĩa nghiệp vụ bằng ngôn ngữ đội ngũ sử dụng. Quan trọng là mọi người hiểu cùng một ý nghĩa, không phải ngôn ngữ đặt tên.

### 11.3. Quản lý thay đổi có trách nhiệm

Không phải ai cũng cần quyền thay đổi mọi bảng. Hãy xác định chủ sở hữu dữ liệu, quy trình review migration và cách thông báo cho các nhóm phụ thuộc. Thay đổi phá vỡ tương thích cần có kế hoạch triển khai và thời gian chuyển tiếp.

Một thay đổi schema nên được review cùng câu hỏi:

- Yêu cầu nghiệp vụ nào dẫn đến thay đổi?
- Quy tắc dữ liệu nào được thêm, sửa hoặc bỏ?
- Dữ liệu cũ được xử lý ra sao?
- Những ứng dụng và báo cáo nào bị ảnh hưởng?
- Có cách kiểm tra và khôi phục không?

## 12. Ví dụ xuyên suốt: từ yêu cầu đến phản hồi

Giả sử hệ thống cho thuê thiết bị ban đầu chỉ quản lý yêu cầu thuê và hợp đồng. Sau một thời gian, người dùng phản ánh rằng thiết bị bị trùng lịch và không truy được lịch sử hư hỏng.

**Giai đoạn khám phá:** nhóm phỏng vấn nhân viên kho và kỹ thuật. Họ phát hiện một dòng thiết bị có nhiều đơn vị vật lý, nhưng bảng cũ chỉ lưu model_name và quantity. Nhân viên ghi serial ở ghi chú tự do nên khó biết đơn vị nào đã được giao.

**Giai đoạn đặc tả:** yêu cầu mới xác định mỗi đơn vị vật lý cần serial duy nhất, có tình trạng hiện tại và lịch sử bảo trì. Hợp đồng phải gán thiết bị cụ thể. Khoảng thời gian phân bổ không được chồng lấn với hợp đồng đã xác nhận hoặc đợt bảo trì.

**Giai đoạn mô hình hóa:** tách EquipmentModel khỏi Equipment; thêm ContractEquipment để gán thiết bị vào hợp đồng; thêm Maintenance và Handover để lưu sự kiện. Các bên xác nhận định nghĩa trạng thái, thời gian và quy tắc hủy.

**Giai đoạn kiểm chứng:** chạy kịch bản hai khách hàng đặt cùng serial trong cùng khoảng thời gian; kiểm thử việc hủy hợp đồng, gia hạn và đưa thiết bị đi bảo trì. Nhóm xác nhận cơ chế transaction ngăn hai lần phân bổ đồng thời.

**Giai đoạn triển khai:** thêm bảng và khóa ngoại mới, import serial từ ghi chú sau khi chuẩn hóa, đưa các dòng không xác định vào danh sách cần nhân viên xác minh. Ứng dụng mới ghi ContractEquipment; sau khi đối soát, báo cáo chuyển sang dùng thiết bị vật lý.

**Giai đoạn phản hồi:** theo dõi số lần lịch trùng bị từ chối, số thiết bị thiếu serial, thời gian tìm lịch trống và số lần bảo trì không có kết quả nghiệm thu. Nếu tìm lịch vẫn chậm, nhóm phân tích truy vấn và thêm chỉ mục phù hợp.

Ví dụ cho thấy mô hình dữ liệu phát triển cùng hiểu biết về nghiệp vụ. Mỗi bước đều có đầu vào, quyết định, cách kiểm chứng và phản hồi để bước tiếp theo tốt hơn.

## 13. Những lỗi thường gặp trong vòng đời mô hình hóa

**Thiết kế theo biểu mẫu hiện tại.** Biểu mẫu thường chỉ phản ánh một luồng thuận lợi. Hãy tìm hiểu ngoại lệ, quyền hạn, lịch sử và các quy trình phía sau.

**Bắt đầu từ bảng thay vì thuật ngữ nghiệp vụ.** Điều này dễ tạo các bảng trùng ý nghĩa hoặc thiếu ranh giới sở hữu. Hãy thống nhất từ điển trước khi chốt cấu trúc.

**Đặc tả bằng câu mơ hồ.** “Thiết bị không được trùng lịch” chưa nói trạng thái nào chiếm dụng lịch, cách tính biên khoảng thời gian và cách xử lý thao tác đồng thời. Viết quy tắc có ví dụ và điều kiện rõ.

**Không phân biệt yêu cầu vận hành và báo cáo.** Một bảng tối ưu cho giao dịch không nhất thiết phù hợp cho tổng hợp lịch sử lớn. Xác định workload và mức trễ chấp nhận được.

**Chỉ kiểm thử luồng thành công.** Lỗi thường xuất hiện ở hủy, gia hạn, gửi lặp, ghi đồng thời và dữ liệu cũ không sạch. Hãy kiểm thử tình huống biên.

**Migration không có đối soát.** Chuyển đủ số hàng không đồng nghĩa dữ liệu đúng. Cần so sánh khóa, tổng tiền, quan hệ, giá trị trạng thái và kết quả truy vấn nghiệp vụ.

**Không theo dõi sau triển khai.** Một mô hình có thể đúng lúc phát hành nhưng không còn phù hợp khi quy trình và tải thay đổi. Cần quan sát chất lượng dữ liệu, truy vấn và phản hồi người dùng.

**Tài liệu không đi cùng schema.** Sơ đồ và từ điển lỗi thời khiến nhóm hiểu sai dữ liệu. Hãy đưa cập nhật tài liệu vào quy trình review migration.

## 14. Quy trình thực hành và checklist

Khi nhận một yêu cầu mô hình dữ liệu mới, có thể dùng trình tự:

1. Xác định mục tiêu nghiệp vụ, người dùng và quyết định mà dữ liệu cần hỗ trợ.
2. Phỏng vấn các vai trò và quan sát quy trình, biểu mẫu, dữ liệu hiện có.
3. Tạo từ điển thuật ngữ và phân loại yêu cầu dữ liệu.
4. Viết quy tắc nghiệp vụ có điều kiện, ngoại lệ và ví dụ kiểm thử.
5. Xác định nguồn sự thật, quyền CRUD và nhu cầu lưu lịch sử.
6. Xây mô hình khái niệm với thực thể, quan hệ và vòng đời.
7. Chuyển thành mô hình logic với thuộc tính, khóa, miền giá trị và ràng buộc.
8. Chọn cấu trúc vật lý, hệ quản trị, chỉ mục và chính sách vòng đời dữ liệu.
9. Walkthrough theo kịch bản, kiểm thử tình huống biên và prototype giả định rủi ro.
10. Lập migration, chuyển đổi dữ liệu, đối soát và triển khai tương thích.
11. Theo dõi chất lượng dữ liệu, hiệu năng và phản hồi sau phát hành.
12. Ghi nhận quyết định và đưa phản hồi vào vòng thiết kế tiếp theo.

Checklist trước khi chốt mô hình:

- [ ] Mục tiêu và phạm vi nghiệp vụ được xác nhận bởi các bên liên quan.
- [ ] Thuật ngữ có định nghĩa thống nhất.
- [ ] Thực thể, thuộc tính và quan hệ phản ánh đúng vòng đời dữ liệu.
- [ ] Khóa và ràng buộc có thể bảo vệ các bất biến quan trọng.
- [ ] Trạng thái hiện tại được phân biệt với lịch sử sự kiện.
- [ ] Nguồn sự thật và quyền cập nhật đã rõ.
- [ ] Truy vấn chính và workload đã được liệt kê.
- [ ] Tình huống biên và thao tác đồng thời đã được kiểm thử.
- [ ] Dữ liệu cũ có quy tắc chuyển đổi và đối soát.
- [ ] Migration tương thích với ứng dụng đang chạy.
- [ ] Có chỉ số theo dõi chất lượng dữ liệu và hiệu năng.
- [ ] Tài liệu và quyết định được cập nhật cùng schema.

## Kết luận

Vòng đời mô hình dữ liệu bắt đầu bằng việc hiểu cách nghiệp vụ hoạt động và kết thúc mỗi vòng bằng phản hồi từ người dùng cùng hệ thống vận hành. Yêu cầu cần được chuyển thành thuật ngữ, quy tắc và mẫu truy cập có thể kiểm chứng. Mô hình khái niệm làm rõ thực thể và quan hệ; mô hình logic xác định thuộc tính, khóa và ràng buộc; mô hình vật lý chọn cách triển khai phù hợp với workload và năng lực vận hành.

Kiểm chứng qua kịch bản, tình huống biên và dữ liệu mẫu giúp phát hiện sai lệch trước khi phát hành. Migration có kế hoạch bảo vệ dữ liệu hiện tại và tương thích với các phiên bản ứng dụng. Sau triển khai, chất lượng dữ liệu, hiệu năng và phản hồi người dùng cung cấp bằng chứng để điều chỉnh mô hình. Khi duy trì được chu trình này, mô hình dữ liệu có thể theo kịp nghiệp vụ mà vẫn giữ được tính rõ ràng, nhất quán và khả năng kiểm soát.
