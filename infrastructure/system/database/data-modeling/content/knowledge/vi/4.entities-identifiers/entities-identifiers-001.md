# Tiêu chí để một khái niệm có định danh và vòng đời riêng

Khi chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu, một quyết định nền tảng là xác định khái niệm nào cần được mô hình hóa thành **thực thể (entity)**. Nếu biến mọi danh từ trong yêu cầu thành bảng hoặc lớp có khóa riêng, mô hình sẽ phức tạp và tạo ra nhiều dữ liệu trùng lặp. Nếu gộp các đối tượng có danh tính và vòng đời riêng thành vài thuộc tính trong một bản ghi lớn, hệ thống lại khó tham chiếu, theo dõi lịch sử và kiểm soát thay đổi.

Một khái niệm thường phù hợp để trở thành thực thể khi nghiệp vụ cần nhận diện riêng từng trường hợp của khái niệm đó qua thời gian, phân biệt nó với những trường hợp khác, và quản lý những thay đổi của nó trong một vòng đời có ý nghĩa. Định danh giúp hệ thống nói về đúng một đối tượng ngay cả khi tên, địa chỉ, trạng thái hoặc những thuộc tính mô tả đối tượng thay đổi.

Ví dụ, một khách hàng có thể đổi tên hiển thị, email hoặc địa chỉ nhưng vẫn là khách hàng đó. Một đơn hàng có thể chuyển từ mới tạo sang đã xác nhận, đang giao rồi hoàn tất nhưng vẫn là cùng một đơn hàng. Ngược lại, số tiền 250.000 đồng thường là một giá trị mô tả; nếu số tiền thay đổi thì ta có một giá trị khác, không nhất thiết có một đối tượng tiền tệ cần theo dõi vòng đời riêng.

Bài học này tập trung vào cách nhận diện ranh giới giữa thực thể và các khái niệm khác, xác định nhu cầu định danh, lựa chọn phạm vi định danh và đánh giá vòng đời trước khi thiết kế bảng, khóa hoặc quan hệ.

## 1. Thực thể là gì?

Thực thể là một đối tượng nghiệp vụ có thể được nhận diện riêng và phân biệt với những đối tượng khác cùng loại. Mỗi thực thể có một danh tính (identity) tồn tại xuyên suốt những thay đổi được phép của các thuộc tính mô tả nó.

Ví dụ:

- Một khách hàng cụ thể trong hệ thống bán hàng.
- Một sản phẩm được quản lý trong danh mục.
- Một đơn hàng được tạo bởi một khách hàng.
- Một lần thanh toán cụ thể cho một đơn hàng.
- Một kho hàng tại một địa điểm.
- Một hợp đồng được ký giữa các bên.

Thực thể có thể là người, vật, tổ chức, địa điểm, tài khoản, giao dịch hoặc một khái niệm trừu tượng do nghiệp vụ quản lý. Nó không nhất thiết phải là một vật thể hữu hình.

### 1.1. Danh tính khác với thuộc tính mô tả

Danh tính trả lời câu hỏi “đây là đối tượng nào?”. Thuộc tính trả lời câu hỏi “đối tượng đó có đặc điểm gì?”.

Ví dụ, với khách hàng:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| customer_id | CUS-10482 | Định danh bản ghi khách hàng trong phạm vi hệ thống |
| full_name | Nguyễn An | Thuộc tính mô tả, có thể thay đổi |
| email | an@example.test | Thuộc tính liên hệ, có thể thay đổi hoặc được chia sẻ |
| birth_date | 1994-08-12 | Thuộc tính mô tả |
| status | active | Trạng thái trong vòng đời |

Nếu khách hàng đổi email, hệ thống cập nhật thuộc tính email của cùng một khách hàng. Nếu dùng email làm danh tính duy nhất mà không khảo sát, việc đổi email có thể khiến hệ thống tưởng đây là một khách hàng mới hoặc làm đứt các tham chiếu cũ.

### 1.2. Thực thể không đồng nghĩa với một dòng trong cơ sở dữ liệu

Thực thể là khái niệm nghiệp vụ. Bảng, tài liệu hoặc nút đồ thị là cách biểu diễn khái niệm đó trong một công nghệ lưu trữ.

Một thực thể có thể được lưu qua nhiều bảng; ngược lại, một bảng có thể lưu dữ liệu của nhiều loại đối tượng nếu mô hình được thiết kế như vậy. Trong document database, một thực thể có thể được lưu cùng các thành phần phụ thuộc trong một tài liệu. Trong graph database, nó có thể là một nút. Trong mô hình phân tích, nó có thể được biểu diễn bằng dimension hoặc các cấu trúc khác.

Vì vậy, hãy quyết định khái niệm nghiệp vụ trước, sau đó mới chọn cách biểu diễn vật lý. Không nên kết luận một khái niệm là thực thể chỉ vì nó đang có một bảng trong hệ thống cũ.

## 2. Những dấu hiệu cho thấy một khái niệm cần định danh riêng

Không có một dấu hiệu đơn lẻ nào luôn quyết định. Hãy xem xét tổng hợp các câu hỏi sau.

### 2.1. Có cần phân biệt từng trường hợp cụ thể không?

Nếu nghiệp vụ cần nói đến một trường hợp cụ thể trong số nhiều trường hợp cùng loại, đó là dấu hiệu mạnh của nhu cầu định danh.

Ví dụ:

- “Đơn hàng này đang chờ thanh toán” cần xác định đúng một đơn hàng.
- “Khách hàng này đã xác minh danh tính” cần xác định đúng một hồ sơ khách hàng.
- “Kiện hàng này đã được bàn giao cho đơn vị vận chuyển” cần xác định đúng một kiện hàng.

Ngược lại, một giá trị như “màu xanh” hoặc “đơn vị tiền tệ VND” có thể chỉ là giá trị thuộc tính hoặc dữ liệu tham chiếu. Nếu cần quản lý danh mục màu sắc hoặc đơn vị tiền tệ với mã và quy tắc riêng, danh mục đó có thể có thực thể tham chiếu; nhưng từng giá trị xuất hiện trong một thuộc tính không tự động trở thành một thực thể nghiệp vụ độc lập.

### 2.2. Đối tượng có giữ danh tính khi thuộc tính thay đổi không?

Hãy hỏi: nếu tên, địa chỉ, trạng thái, giá trị hiển thị hoặc cấu hình thay đổi, nghiệp vụ có vẫn coi đó là cùng một đối tượng không?

- Khách hàng đổi tên: thường vẫn là cùng khách hàng.
- Sản phẩm đổi mô tả: vẫn là cùng sản phẩm nếu mã sản phẩm và ý nghĩa sản phẩm không đổi.
- Đơn hàng chuyển trạng thái: vẫn là cùng đơn hàng.
- Một số điện thoại được chuyển từ người này sang người khác: giá trị số điện thoại không đại diện cho cùng một người trong toàn bộ thời gian.

Nếu danh tính cần tồn tại độc lập với thuộc tính có thể thay đổi, khái niệm thường cần một định danh ổn định.

### 2.3. Đối tượng có vòng đời nghiệp vụ riêng không?

Một thực thể thường có các mốc như tạo, kích hoạt, thay đổi, tạm ngưng, hoàn tất, đóng hoặc hủy. Không phải mọi thực thể đều cần nhiều trạng thái, nhưng nếu nghiệp vụ có hành động riêng và cần theo dõi tiến trình của từng trường hợp, đó là dấu hiệu quan trọng.

Ví dụ:

- Đơn hàng được tạo, xác nhận, giao một phần, giao đủ hoặc hủy.
- Tài khoản được mở, khóa, mở lại hoặc đóng.
- Hợp đồng được soạn, ký, có hiệu lực, gia hạn hoặc chấm dứt.
- Phiếu nhập kho được tạo, duyệt, nhận hàng và đóng.

Cần phân biệt vòng đời của thực thể với việc một thuộc tính đơn giản thay đổi. Một cờ is_active không đủ để chứng minh khái niệm có vòng đời riêng nếu không có quy tắc hoặc thao tác nghiệp vụ độc lập nào khác.

### 2.4. Đối tượng có được tham chiếu từ nơi khác không?

Nếu nhiều quy trình cần tham chiếu ổn định đến cùng một đối tượng, định danh riêng giúp tránh sao chép thông tin và giảm nhầm lẫn.

Ví dụ:

- Đơn hàng tham chiếu khách hàng.
- Dòng hàng tham chiếu sản phẩm.
- Phiếu xuất tham chiếu kho.
- Giao dịch hoàn tiền tham chiếu khoản thanh toán gốc.
- Lịch hẹn tham chiếu bệnh nhân và nhân viên phụ trách.

Tham chiếu không nhất thiết phải là khóa ngoại trong cùng một cơ sở dữ liệu. Nó có thể là mã định danh qua API, thông điệp, document reference hoặc liên kết giữa các nút. Điều quan trọng là đối tượng được nhận diện nhất quán trong phạm vi đã xác định.

### 2.5. Có cần quản lý quy tắc hoặc quyền riêng cho đối tượng không?

Nếu một khái niệm có các quy tắc kiểm tra, quyền truy cập, trạng thái, chính sách lưu giữ hoặc quy trình xử lý riêng, nó có thể cần ranh giới thực thể riêng.

Ví dụ, tài khoản đăng nhập và hồ sơ khách hàng có thể liên quan nhưng không nhất thiết là một đối tượng. Tài khoản có trạng thái xác thực, thông tin đăng nhập và quy tắc khóa tài khoản; hồ sơ khách hàng có tên, thông tin liên hệ và lịch sử mua hàng. Một khách hàng có thể có nhiều tài khoản hoặc tài khoản có thể được liên kết với nhiều vai trò, tùy nghiệp vụ.

### 2.6. Có cần lưu lịch sử hoặc truy nguyên riêng không?

Nếu cần biết một đối tượng đã thay đổi ra sao, ai thực hiện thay đổi hoặc trạng thái của nó tại một thời điểm, định danh ổn định giúp liên kết các phiên bản và sự kiện.

Ví dụ, hệ thống cần tra cứu toàn bộ lần chuyển trạng thái của một đơn hàng. Nếu chỉ lưu một bản ghi trạng thái tổng hợp mà không có định danh đơn hàng ổn định và lịch sử, việc điều tra sẽ khó khăn.

### 2.7. Bảng câu hỏi nhận diện

| Câu hỏi | Dấu hiệu cần thực thể |
|---|---|
| Có nhiều trường hợp riêng biệt cùng loại không? | Cần phân biệt từng trường hợp |
| Thuộc tính có thể thay đổi nhưng vẫn là cùng đối tượng không? | Danh tính độc lập với mô tả |
| Có vòng đời hoặc hành động nghiệp vụ riêng không? | Có trạng thái và chuyển đổi riêng |
| Quy trình khác cần tham chiếu đến đối tượng không? | Cần định danh ổn định |
| Có quy tắc, quyền hoặc chính sách riêng không? | Có ranh giới quản lý riêng |
| Cần lưu lịch sử hoặc truy nguyên theo từng trường hợp không? | Cần liên kết phiên bản/sự kiện |

Các câu hỏi trên là hướng dẫn phân tích, không phải phép chấm điểm máy móc. Một khái niệm không cần có đủ mọi dấu hiệu mới được xem là thực thể. Hãy ưu tiên yêu cầu nghiệp vụ đã được xác nhận và hậu quả nếu không có định danh riêng.

## 3. Phân biệt thực thể với các khái niệm gần giống

### 3.1. Thực thể và value object

**Value object (đối tượng giá trị)** được xác định chủ yếu bằng các giá trị cấu thành nó, thay vì một danh tính độc lập. Hai value object có cùng giá trị theo quy tắc so sánh có thể được xem là tương đương.

Ví dụ:

- Money gồm số tiền và loại tiền tệ.
- Khoảng thời gian gồm thời điểm bắt đầu và kết thúc.
- Địa chỉ giao hàng được chụp tại thời điểm đặt hàng.
- Tọa độ địa lý gồm kinh độ và vĩ độ.
- Một khoảng kích thước gồm chiều dài, chiều rộng và chiều cao.

Nếu giá trị thay đổi, ta thường có một value object mới thay cho giá trị cũ. Ta không nhất thiết phải hỏi “đây vẫn là cùng một đối tượng tiền tệ hay địa chỉ không?” như với một khách hàng.

Tuy nhiên, cùng một khái niệm có thể được mô hình hóa khác nhau tùy nghiệp vụ:

- Địa chỉ được chụp trong đơn hàng có thể là value object, vì nó mô tả nơi giao tại thời điểm đặt.
- Một địa điểm giao hàng được nhiều đơn vị quản lý, có mã, trạng thái hoạt động, lịch sử và được nhiều đơn hàng tham chiếu có thể là thực thể.
- Hồ sơ địa chỉ cá nhân được quản lý và chỉnh sửa độc lập cũng có thể cần định danh riêng.

Đừng kết luận “địa chỉ luôn là value object” hoặc “địa chỉ luôn là entity”. Hãy xét mục đích, quyền quản lý và vòng đời.

### 3.2. Thực thể và thuộc tính

Thuộc tính mô tả một thực thể. Nó thường không cần định danh riêng nếu chỉ tồn tại như một phần mô tả của đối tượng và không được quản lý độc lập.

Ví dụ, màu sắc hiện tại của sản phẩm có thể là thuộc tính color. Nếu doanh nghiệp cần quản lý bảng màu chuẩn, mã màu, tên đa ngôn ngữ và trạng thái sử dụng, mỗi màu trong danh mục có thể trở thành một bản ghi dữ liệu tham chiếu. Việc có mã riêng trong danh mục không có nghĩa màu sắc trở thành thực thể nghiệp vụ có vòng đời như đơn hàng.

Hãy hỏi liệu thuộc tính có được chia sẻ, tham chiếu, quản trị hoặc có lịch sử độc lập hay không.

### 3.3. Thực thể và dữ liệu tham chiếu

Dữ liệu tham chiếu là tập giá trị được quản lý để chuẩn hóa cách phân loại hoặc diễn giải dữ liệu, ví dụ loại tiền tệ, loại đơn hàng, mã vùng hoặc danh sách trạng thái.

Dữ liệu tham chiếu thường có mã ổn định và định nghĩa rõ, nhưng vòng đời có thể rất đơn giản: thêm giá trị, đổi nhãn, ngừng sử dụng. Nó có thể được lưu trong bảng riêng mà không cần mô hình hóa như một thực thể nghiệp vụ giàu hành vi.

Nếu danh mục có quy trình phê duyệt, hiệu lực theo thời gian, phân cấp, quan hệ hoặc chủ sở hữu riêng, nó có thể cần được mô hình hóa như một thực thể tham chiếu. Mức độ mô hình hóa phụ thuộc yêu cầu thực tế.

### 3.4. Thực thể và sự kiện

Sự kiện (event) mô tả một điều đã xảy ra tại một thời điểm, ví dụ OrderPlaced, PaymentCaptured hoặc AddressChanged. Sự kiện thường bất biến sau khi được ghi nhận và có thời điểm, nguồn phát sinh, dữ liệu liên quan.

Thực thể mô tả đối tượng có danh tính và có thể trải qua nhiều thay đổi. Một đơn hàng là thực thể; sự kiện đặt đơn và các sự kiện đổi trạng thái mô tả điều đã xảy ra với đơn hàng đó.

Một sự kiện cũng có thể có định danh riêng để chống xử lý trùng, truy nguyên và tham chiếu. Điều đó không có nghĩa sự kiện có cùng kiểu vòng đời với thực thể nghiệp vụ. Mã sự kiện thường nhận diện một lần phát sinh, còn mã đơn hàng nhận diện đối tượng đơn hàng xuyên suốt nhiều sự kiện.

### 3.5. Thực thể và quy trình

Quy trình mô tả chuỗi hoạt động nhằm đạt kết quả. Một bước quy trình có thể chỉ là trạng thái hoặc sự kiện, nhưng một trường hợp xử lý quy trình cụ thể có thể cần thực thể riêng.

Ví dụ:

- “Quy trình duyệt đơn” là khái niệm mô tả cách làm.
- Một lần yêu cầu duyệt đơn cụ thể có người yêu cầu, người duyệt, thời hạn, kết quả và lịch sử có thể là thực thể ApprovalRequest.
- Trạng thái pending chỉ là một trạng thái của yêu cầu duyệt, không nhất thiết là thực thể riêng.

### 3.6. Thực thể và nhóm phân loại

Một vai trò như admin, một loại khách hàng như VIP hoặc một trạng thái như pending thường là giá trị phân loại. Nếu cần quản lý danh mục vai trò hoặc trạng thái, ta có thể có bảng tham chiếu. Nhưng không nên tạo thực thể nghiệp vụ riêng cho mỗi giá trị chỉ vì chúng là danh từ hoặc có thể xuất hiện trong danh sách.

## 4. Quy trình quyết định một khái niệm có cần thực thể riêng

Có thể áp dụng quy trình sau cho từng danh từ hoặc khái niệm xuất hiện trong yêu cầu nghiệp vụ.

~~~mermaid
flowchart TD
    A["Khái niệm xuất hiện trong yêu cầu"] --> B{"Có cần nhận diện từng trường hợp cụ thể?"}
    B -->|Không| C["Xem xét thuộc tính, value object hoặc giá trị tham chiếu"]
    B -->|Có| D{"Danh tính có tồn tại khi thuộc tính mô tả thay đổi?"}
    D -->|Không| E["Xem xét value object hoặc bản ghi giá trị"]
    D -->|Có| F{"Có vòng đời, quy tắc hoặc tham chiếu riêng?"}
    F -->|Không rõ| G["Khảo sát thêm tình huống và hậu quả nghiệp vụ"]
    F -->|Có| H["Đề xuất thực thể có định danh riêng"]
    G --> F
    H --> I["Xác định phạm vi định danh và vòng đời"]
    I --> J["Kiểm tra bằng ví dụ, ngoại lệ và consumer"]
~~~

### Bước 1: Viết định nghĩa nghiệp vụ

Mô tả khái niệm bằng một câu nêu rõ nó là gì và phục vụ mục đích nào. Tránh định nghĩa vòng tròn như “khách hàng là một customer”.

Ví dụ: “Đơn hàng là yêu cầu mua hàng được hệ thống ghi nhận với một khách hàng, các dòng hàng, giá đã chốt và trạng thái xử lý riêng.”

Định nghĩa cần được người hiểu nghiệp vụ xác nhận. Một tên gọi giống nhau có thể mang ý nghĩa khác nhau giữa các phòng ban.

### Bước 2: Liệt kê các trường hợp riêng biệt

Hãy lấy ví dụ thật hoặc giả lập: có hai khách hàng cùng tên, một khách hàng đổi email, một đơn hàng có nhiều lần thanh toán, một địa chỉ được nhiều đơn hàng dùng. Nếu hệ thống cần phân biệt các trường hợp này, ghi rõ bằng cách nào.

### Bước 3: Kiểm tra danh tính khi thuộc tính thay đổi

Hỏi liệu đối tượng có còn là cùng một đối tượng sau khi đổi tên, địa chỉ, trạng thái, chủ sở hữu hoặc cấu hình không. Nếu câu trả lời là có, danh tính không nên phụ thuộc hoàn toàn vào thuộc tính dễ thay đổi đó.

### Bước 4: Xác định hành động và vòng đời

Liệt kê các thao tác tạo, sửa, tạm ngưng, kích hoạt, hoàn tất, hủy, hợp nhất hoặc đóng. Ghi rõ thao tác nào làm thay đổi trạng thái, ai được thực hiện và điều kiện nào phải thỏa mãn.

### Bước 5: Kiểm tra quan hệ và tham chiếu

Xác định đối tượng nào cần liên kết tới khái niệm này. Nếu một khái niệm được nhiều quy trình dùng chung, hãy đánh giá việc cấp định danh riêng và quản lý vòng đời độc lập.

### Bước 6: Xác định dữ liệu nào thực sự cần lưu độc lập

Không tách một khái niệm chỉ để có bảng riêng. Hãy cân nhắc nó có cần lưu trữ, truy vấn, phân quyền, lịch sử, kiểm tra chất lượng hoặc thay đổi độc lập không.

### Bước 7: Kiểm tra ngoại lệ

Xét các trường hợp như hợp nhất hai hồ sơ, tách một tổ chức thành hai, đổi mã, chuyển quyền sở hữu, xóa hoặc khôi phục. Nếu các trường hợp này có ý nghĩa nghiệp vụ, mô hình cần giải thích được danh tính trước và sau thay đổi.

## 5. Xác định phạm vi của định danh

Sau khi quyết định cần thực thể, cần trả lời định danh có ý nghĩa trong phạm vi nào. Một mã duy nhất trong một bảng có thể không đủ khi dữ liệu được trao đổi giữa nhiều hệ thống hoặc nhiều tổ chức.

### 5.1. Phân biệt identity, identifier và key

- **Identity (danh tính):** khái niệm giúp nhận ra cùng một đối tượng qua thời gian.
- **Identifier (định danh):** giá trị hoặc tập giá trị được dùng để chỉ ra đối tượng.
- **Key (khóa):** thuộc tính hoặc tập thuộc tính được dùng để nhận diện một bản ghi theo quy tắc của mô hình dữ liệu.

Một thực thể có thể có nhiều identifier: mã nội bộ, mã nghiệp vụ, mã từ đối tác hoặc mã cũ. Chúng có thể cùng tham chiếu đến một identity nhưng có phạm vi và thời hạn khác nhau.

### 5.2. Định danh nội bộ và mã nghiệp vụ

Định danh nội bộ được hệ thống quản lý để tham chiếu ổn định. Mã nghiệp vụ được người dùng hoặc đối tác sử dụng trong quy trình.

Ví dụ:

- customer_id = 8f... là mã nội bộ.
- customer_number = KH-2026-0042 là mã nghiệp vụ hiển thị.
- legacy_customer_code = A01983 là mã từ hệ thống cũ.

Không nhất thiết phải dùng cùng một giá trị cho cả ba mục đích. Mã nghiệp vụ có thể có quy tắc định dạng, có thể đổi khi sáp nhập hệ thống hoặc khi doanh nghiệp thay đổi quy trình. Mã nội bộ thường nên ổn định hơn.

### 5.3. Phạm vi duy nhất

Hãy xác định mã phải duy nhất ở đâu:

- Trong một bảng.
- Trong một tenant hoặc tổ chức.
- Trong một hệ thống nguồn.
- Trên toàn doanh nghiệp.
- Trên toàn bộ mạng lưới đối tác.
- Trong một khoảng thời gian.

Ví dụ, employee_number có thể duy nhất trong từng công ty con nhưng trùng giữa hai công ty. Khi đó, cặp (organization_id, employee_number) mới nhận diện duy nhất nhân viên trong phạm vi tổ chức.

### 5.4. Định danh không nên phụ thuộc vào dữ liệu dễ thay đổi

Email, số điện thoại, tên, địa chỉ, tên đăng nhập hoặc mã phân loại có thể thay đổi, được tái sử dụng hoặc không duy nhất. Chỉ dùng chúng làm khóa chính khi nghiệp vụ chứng minh được tính ổn định, duy nhất và không tái sử dụng trong toàn bộ thời gian cần tham chiếu.

Ví dụ, một số điện thoại có thể được chuyển cho người khác sau một thời gian. Nếu số điện thoại là khóa khách hàng, lịch sử liên hệ có thể bị gắn nhầm sang chủ sở hữu mới. Hãy lưu số điện thoại như thuộc tính có thời gian hiệu lực hoặc tạo thực thể liên hệ riêng nếu cần quản lý nó độc lập.

### 5.5. Không tái sử dụng định danh

Nếu một khách hàng bị đóng hoặc xóa theo chính sách, mã định danh của họ thường không nên được cấp lại cho khách hàng mới. Việc tái sử dụng có thể khiến lịch sử đơn hàng, nhật ký hoặc tham chiếu cũ trỏ nhầm đối tượng.

Nếu nghiệp vụ có yêu cầu tái sử dụng một mã hiển thị, cần tách mã hiển thị khỏi định danh nội bộ và quy định rõ thời gian hiệu lực hoặc phạm vi duy nhất.

### 5.6. Định danh xuyên hệ thống

Khi nhiều hệ thống có mã riêng, cần có cách ánh xạ rõ ràng:

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| entity_id | 01J... | Định danh nội bộ ổn định |
| source_system | CRM | Nguồn cấp mã ngoài |
| external_id | C-00982 | Mã khách hàng ở CRM |
| valid_from | 2026-01-01 | Thời điểm ánh xạ bắt đầu có hiệu lực |
| valid_to | NULL | Thời điểm kết thúc, nếu có |

Bảng ánh xạ cần có ràng buộc phù hợp, chẳng hạn một cặp (source_system, external_id) chỉ ánh xạ tới một thực thể tại cùng một thời điểm trong phạm vi đã định. Khi hai bản ghi được hợp nhất, cần giữ thông tin mã cũ và quy tắc chuyển hướng để các consumer không mất khả năng truy nguyên.

## 6. Chọn loại khóa cho thực thể

### 6.1. Khóa tự nhiên (natural key)

Khóa tự nhiên là thuộc tính có ý nghĩa nghiệp vụ và có thể nhận diện đối tượng, chẳng hạn mã số định danh do cơ quan có thẩm quyền cấp, mã sản phẩm theo chuẩn hoặc mã hợp đồng đã được quy định.

Ưu điểm:

- Có ý nghĩa với nghiệp vụ.
- Có thể dùng để đối chiếu với nguồn bên ngoài.
- Có thể tránh tạo thêm một mã nếu giá trị đã ổn định và đáng tin cậy.

Rủi ro:

- Giá trị có thể thay đổi theo quy định hoặc quy trình.
- Phạm vi duy nhất có thể không toàn cục.
- Có thể chứa thông tin nhạy cảm.
- Có thể được nhập sai hoặc cấp lại.
- Có thể khó dùng làm tham chiếu kỹ thuật nếu dài hoặc có định dạng phức tạp.

Trước khi dùng khóa tự nhiên làm khóa chính, hãy xác minh nó có duy nhất, không rỗng, ổn định, không tái sử dụng và được phép lưu hoặc chia sẻ hay không.

### 6.2. Khóa thay thế (surrogate key)

Khóa thay thế là mã được hệ thống tạo ra, không mang ý nghĩa nghiệp vụ trực tiếp. Ví dụ: số tăng tự động, UUID hoặc một định danh khác.

Ưu điểm:

- Tách danh tính kỹ thuật khỏi thuộc tính nghiệp vụ.
- Có thể giữ ổn định khi mã nghiệp vụ thay đổi.
- Dễ tham chiếu trong các quan hệ.
- Có thể giảm việc lộ thông tin nghiệp vụ trong URL hoặc log nếu được thiết kế phù hợp.

Rủi ro:

- Không tự bảo đảm duy nhất trong mọi hệ thống nếu cách sinh mã không phù hợp.
- Không thay thế được ràng buộc duy nhất trên mã nghiệp vụ.
- Có thể tạo thêm bước ánh xạ khi tích hợp.
- Mã tăng tuần tự có thể để lộ quy mô hoặc thứ tự tạo nếu công khai.

Một lựa chọn phổ biến là dùng surrogate key làm khóa chính nội bộ và thêm unique constraint cho mã nghiệp vụ có quy tắc duy nhất. Đây là lựa chọn thiết kế, không phải quy tắc bắt buộc cho mọi mô hình.

### 6.3. Khóa đơn và khóa ghép

Khóa đơn dùng một thuộc tính để nhận diện. Khóa ghép dùng nhiều thuộc tính kết hợp.

Ví dụ, trong bảng thành viên của một lớp học, nếu một học viên chỉ được đăng ký một lần trong mỗi lớp, khóa ghép (class_id, student_id) có thể phù hợp. Nhưng nếu mỗi lần đăng ký có thể bị hủy rồi đăng ký lại và cần lưu lịch sử từng lần, cần định danh riêng cho từng enrollment hoặc thêm thành phần phân biệt lần đăng ký.

Khóa ghép phản ánh quy tắc nghiệp vụ trực tiếp, nhưng có thể làm khóa ngoại dài và khiến việc thay đổi thành phần khóa trở nên khó khăn. Hãy chọn dựa trên vòng đời và cách tham chiếu thực tế.

### 6.4. Candidate key, primary key và alternate key

Một thực thể có thể có nhiều tập thuộc tính nhận diện duy nhất:

- **Candidate key:** tập thuộc tính tối thiểu có khả năng nhận diện duy nhất.
- **Primary key:** candidate key được chọn làm khóa chính.
- **Alternate key:** candidate key khác không được chọn làm khóa chính.

Ví dụ, một sản phẩm có product_id nội bộ và sku duy nhất trong phạm vi cửa hàng. Có thể chọn product_id làm primary key và đặt unique constraint trên sku làm alternate key.

Định danh không thay thế các ràng buộc dữ liệu. Nếu sku phải duy nhất, mô hình cần thể hiện quy tắc đó bằng ràng buộc hoặc cơ chế kiểm soát tương ứng.

## 7. Đánh giá vòng đời của thực thể

Định danh ổn định cho biết đối tượng nào đang được nói đến; vòng đời mô tả đối tượng có thể trải qua những trạng thái và sự kiện nào.

### 7.1. Xác định các mốc vòng đời

Với mỗi thực thể, hãy khảo sát:

- Ai hoặc quy trình nào được phép tạo?
- Khi nào đối tượng được xem là tồn tại chính thức?
- Có bước kiểm tra hoặc phê duyệt trước khi kích hoạt không?
- Những trạng thái hợp lệ là gì?
- Ai được phép chuyển trạng thái?
- Điều kiện nào cần thỏa mãn trước khi chuyển?
- Có thể quay lại trạng thái trước không?
- Khi nào đối tượng được xem là hoàn tất, đóng hoặc hết hiệu lực?
- Có được khôi phục sau khi đóng không?
- Khi nào dữ liệu được xóa, ẩn danh hoặc lưu trữ?

Không phải thực thể nào cũng cần một state machine phức tạp. Hãy mô hình hóa đúng các trạng thái có ý nghĩa nghiệp vụ và tránh tạo trạng thái chỉ để phản ánh từng bước kỹ thuật nội bộ.

### 7.2. Phân biệt trạng thái hiện tại và lịch sử chuyển trạng thái

Một cột status thường biểu diễn trạng thái hiện tại. Nếu cần biết đối tượng đã trải qua những trạng thái nào, cần thêm cấu trúc lịch sử hoặc sự kiện.

Ví dụ:

| order_id | status hiện tại | created_at |
|---|---|---|
| ORD-104 | shipped | 2026-04-02 09:00 |

Lịch sử chuyển trạng thái có thể lưu:

| order_id | from_status | to_status | changed_at | actor |
|---|---|---|---|---|
| ORD-104 | NULL | pending | 2026-04-02 09:00 | customer |
| ORD-104 | pending | confirmed | 2026-04-02 09:03 | order-service |
| ORD-104 | confirmed | packed | 2026-04-02 10:20 | warehouse |
| ORD-104 | packed | shipped | 2026-04-02 13:15 | carrier |

Bảng trên chỉ minh họa. Cần xác định trạng thái nào thuộc vòng đời đơn hàng, trạng thái nào thuộc vận chuyển hoặc thanh toán. Không nên gộp trạng thái của nhiều đối tượng khác nhau vào một cột nếu chúng có vòng đời riêng.

### 7.3. Vòng đời của đối tượng phụ thuộc

Một số đối tượng chỉ có ý nghĩa trong phạm vi một thực thể cha. Ví dụ, dòng hàng của đơn hàng phụ thuộc vào đơn hàng; một chi tiết địa chỉ trong hồ sơ có thể phụ thuộc khách hàng; một dòng trong bảng kê có thể phụ thuộc chứng từ.

Hãy hỏi:

- Đối tượng con có tồn tại độc lập khi đối tượng cha bị xóa hoặc đóng không?
- Nó có thể được chuyển sang cha khác không?
- Có cần tham chiếu hoặc tra cứu trực tiếp không?
- Có vòng đời riêng hay chỉ thay đổi cùng cha?
- Có cần định danh riêng để phân biệt các lần xuất hiện giống nhau không?

Nếu dòng hàng chỉ có ý nghĩa trong một đơn hàng, khóa ghép (order_id, line_number) có thể đủ. Nếu dòng hàng có thể được tham chiếu từ vận chuyển, hoàn tiền hoặc kiểm toán trong thời gian dài, một order_item_id ổn định có thể hữu ích.

### 7.4. Hợp nhất, tách và thay thế đối tượng

Đây là các tình huống dễ làm mất tính nhất quán của danh tính:

- **Hợp nhất:** hai hồ sơ khách hàng được xác định là cùng một người. Cần chọn hồ sơ chuẩn, giữ ánh xạ mã cũ và xử lý các tham chiếu.
- **Tách:** một hồ sơ tổ chức chứa hai đơn vị độc lập và cần tách thành hai. Cần xác định dữ liệu và giao dịch nào thuộc mỗi đối tượng.
- **Thay thế:** một thiết bị cũ được thay bằng thiết bị mới. Không nên giữ cùng identity nếu nghiệp vụ xem chúng là hai thiết bị khác nhau.
- **Chuyển quyền sở hữu:** một tài sản chuyển từ người này sang người khác nhưng vẫn là cùng tài sản.
- **Đổi mã:** mã nghiệp vụ thay đổi nhưng đối tượng vẫn giữ danh tính.

Đừng nhầm việc thay đổi chủ sở hữu hoặc mã nhận diện với việc tạo ra một thực thể mới. Cần căn cứ vào định nghĩa nghiệp vụ và quy tắc theo dõi lịch sử.

## 8. Các trường hợp dễ quyết định sai

### 8.1. Email và số điện thoại

Một khách hàng có thể có nhiều email hoặc số điện thoại; một địa chỉ liên hệ có thể được chia sẻ; giá trị có thể thay đổi hoặc được tái sử dụng. Nếu nghiệp vụ cần quản lý từng phương thức liên hệ, xác minh, mức ưu tiên, thời hạn hiệu lực và lịch sử thay đổi, có thể mô hình hóa ContactPoint thành thực thể phụ thuộc có định danh riêng.

Nếu chỉ cần lưu một email hiển thị và không cần quản lý độc lập, email có thể là thuộc tính hoặc value object.

### 8.2. Địa chỉ

Địa chỉ có thể là:

- Value object được chụp trong đơn hàng.
- Thực thể địa điểm được quản lý và chia sẻ.
- Thực thể địa chỉ liên hệ của khách hàng với nhiều phiên bản hiệu lực.
- Dữ liệu tham chiếu đến một địa điểm chuẩn hóa bên ngoài.

Cần phân biệt địa chỉ vật lý, địa chỉ nhận thư, địa chỉ giao hàng và địa chỉ xuất hóa đơn. Chúng có thể trùng giá trị nhưng có ý nghĩa nghiệp vụ khác nhau.

### 8.3. Dòng hàng đơn hàng

Dòng hàng thường cần định danh riêng vì hai dòng có thể cùng sản phẩm nhưng khác giá, khuyến mại, ghi chú, lô giao hoặc trạng thái xử lý. Nếu chỉ dùng product_id làm định danh dòng hàng, hai lần xuất hiện của cùng sản phẩm trong một đơn có thể bị nhầm lẫn.

Dòng hàng có thể là thực thể phụ thuộc vào đơn hàng. Danh tính của nó có thể được xác định bằng order_item_id hoặc cặp (order_id, line_number) tùy yêu cầu.

### 8.4. Số tiền và đơn giá

Số tiền thường là value object gồm giá trị số và đơn vị tiền tệ. Một đơn giá được áp dụng cho dòng hàng có thể được chụp lại trong giao dịch. Nếu hệ thống cần quản lý bảng giá, phiên bản giá, thời gian hiệu lực và quy trình phê duyệt, PriceList hoặc PriceRule có thể là thực thể riêng.

Không nên tạo thực thể cho mỗi con số tiền chỉ vì nó được lưu trong một cột.

### 8.5. Trạng thái

pending, approved, closed thường là giá trị trạng thái. Một trạng thái có thể nằm trong danh mục tham chiếu, nhưng mỗi lần chuyển trạng thái là một sự kiện hoặc bản ghi lịch sử. Đối tượng đang chuyển trạng thái mới là thực thể có vòng đời.

### 8.6. Phiên đăng nhập và tài khoản

Tài khoản có danh tính và vòng đời dài hơn một phiên đăng nhập. Phiên đăng nhập là một lần xác thực có thời điểm bắt đầu, hết hạn, thiết bị và trạng thái riêng. Nếu cần thu hồi từng phiên, kiểm toán hoặc giới hạn thiết bị, session có thể là một thực thể kỹ thuật có định danh riêng, dù nó không phải thực thể nghiệp vụ cốt lõi như khách hàng.

## 9. Ví dụ xuyên suốt: nhận diện thực thể trong hệ thống bán hàng

Giả sử yêu cầu nghiệp vụ là: khách hàng duyệt sản phẩm, thêm vào giỏ, đặt đơn, thanh toán và nhận hàng.

### 9.1. Phân loại khái niệm

| Khái niệm | Đề xuất ban đầu | Lý do |
|---|---|---|
| Customer | Thực thể | Có danh tính, hồ sơ, quyền và lịch sử riêng |
| Product | Thực thể | Có mã, mô tả, trạng thái kinh doanh và được nhiều quy trình tham chiếu |
| ShoppingCart | Thực thể | Có chủ sở hữu, thời gian tồn tại, trạng thái và nội dung thay đổi |
| CartItem | Thành phần phụ thuộc hoặc thực thể con | Cần phân biệt từng dòng và thay đổi số lượng |
| Order | Thực thể | Có định danh, giao dịch và vòng đời riêng |
| OrderItem | Thực thể phụ thuộc | Có giá chốt, số lượng, chiết khấu và lịch sử xử lý riêng |
| Payment | Thực thể | Có mã giao dịch, trạng thái, kết quả và đối soát riêng |
| Money | Value object | Được xác định bởi số tiền và loại tiền tệ |
| ShippingAddressSnapshot | Value object | Mô tả địa chỉ đã chốt tại thời điểm đặt |
| OrderStatus | Giá trị tham chiếu hoặc enum | Mô tả trạng thái hiện tại |
| OrderStatusChange | Sự kiện/bản ghi lịch sử | Ghi lại một lần chuyển trạng thái |
| EmailAddress | Thuộc tính/value object hoặc thực thể phụ thuộc | Tùy có cần xác minh, nhiều địa chỉ và lịch sử riêng hay không |

Đây là đề xuất ban đầu, cần xác nhận với nghiệp vụ. Chẳng hạn giỏ hàng ẩn danh có thể được chuyển cho khách hàng sau đăng nhập; một giỏ có thể hết hạn; một đơn hàng có thể có nhiều khoản thanh toán. Những tình huống này ảnh hưởng đến ranh giới và quan hệ.

### 9.2. Kiểm tra danh tính qua thay đổi

- Khách hàng đổi email: giữ customer_id.
- Sản phẩm đổi tên hiển thị: giữ product_id.
- Giá sản phẩm thay đổi: giữ sản phẩm, tạo phiên bản hoặc bản ghi giá phù hợp.
- Đơn hàng đổi trạng thái: giữ order_id.
- Một lần thanh toán bị từ chối rồi khách thử lại: cần xác định mỗi lần thử có phải một payment attempt riêng hay chỉ là lần cập nhật cùng một giao dịch.
- Địa chỉ giao hàng thay đổi sau khi đơn được đặt: địa chỉ hồ sơ có thể thay đổi, nhưng ảnh chụp địa chỉ của đơn vẫn giữ dữ kiện đã xác nhận.

### 9.3. Mô hình định danh khái quát

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
    ORDER ||--o{ PAYMENT : has
    ORDER ||--o{ ORDER_STATUS_CHANGE : records
    CUSTOMER ||--o{ SHOPPING_CART : owns
    SHOPPING_CART ||--o{ CART_ITEM : contains
    PRODUCT ||--o{ CART_ITEM : selected
~~~

Sơ đồ chỉ thể hiện quan hệ khái niệm ở mức khái quát. Nó chưa quyết định khóa vật lý, tính tùy chọn, bội số chính xác của mọi trường hợp hoặc cách lưu địa chỉ chụp. Những quyết định đó cần được kiểm chứng bằng quy tắc nghiệp vụ.

### 9.4. Câu hỏi cần chốt trước khi thiết kế bảng

- Một khách hàng có thể có nhiều tài khoản không?
- Một giỏ hàng có thể tồn tại khi chưa có khách hàng đăng nhập không?
- Một sản phẩm có thể xuất hiện nhiều lần trong cùng một đơn không?
- Mỗi lần thử thanh toán có định danh riêng không?
- Đơn hàng có được tách thành nhiều lô giao không?
- Địa chỉ giao hàng có thể được sửa sau khi xác nhận không? Nếu có, cần lưu phiên bản nào?
- Mã đơn hàng có duy nhất toàn doanh nghiệp hay chỉ trong một kênh?
- Khi hai hồ sơ khách hàng được hợp nhất, các đơn cũ tham chiếu mã nào?

Câu trả lời sẽ xác định entity boundary, khóa và quan hệ; không nên tự giả định dựa trên cấu trúc của một ứng dụng hiện có.

## 10. Chuyển quyết định khái niệm thành mô hình dữ liệu

Sau khi xác định thực thể, cần ghi nhận những thông tin tối thiểu để chuyển sang thiết kế logic.

| Nội dung | Cần xác định |
|---|---|
| Tên và định nghĩa | Tên chuẩn và ý nghĩa nghiệp vụ |
| Phạm vi | Đối tượng thuộc tổ chức, tenant hoặc miền nào |
| Identity | Điều gì làm cho một trường hợp khác biệt với trường hợp khác |
| Identifier | Khóa nội bộ, mã nghiệp vụ và mã ngoài |
| Uniqueness | Phạm vi và thời gian duy nhất |
| Lifecycle | Trạng thái, sự kiện và quy tắc chuyển đổi |
| Ownership | Ai chịu trách nhiệm tạo, sửa, đóng và hợp nhất |
| Relationships | Đối tượng nào tham chiếu đến thực thể |
| History | Thuộc tính hoặc sự kiện nào cần lưu lịch sử |
| Retention | Khi nào dữ liệu được lưu trữ, ẩn danh hoặc xóa |

### 10.1. Không tạo khóa trước khi xác định quy tắc duy nhất

Một cột id có thể giúp nhận diện bản ghi, nhưng không chứng minh dữ liệu nghiệp vụ không bị trùng. Ví dụ, hai khách hàng có hai customer_id khác nhau vẫn có thể là cùng một khách hàng do quy trình nhập liệu tạo trùng hồ sơ.

Cần xác định các candidate key và quy tắc phát hiện trùng. Với dữ liệu có thể trùng hợp lệ, ví dụ hai người cùng tên hoặc cùng địa chỉ, không được dùng thuộc tính mô tả đơn lẻ để hợp nhất.

### 10.2. Định danh và quan hệ phải nhất quán

Nếu một thực thể được tham chiếu từ nhiều nơi, thay đổi định danh hoặc hợp nhất bản ghi cần có quy trình cập nhật hoặc ánh xạ. Không nên xóa bản ghi gốc rồi tạo mã mới mà không xử lý các khóa ngoại, sự kiện, báo cáo và consumer.

Trong mô hình quan hệ, điều này thường liên quan đến primary key, foreign key, unique constraint và bảng ánh xạ. Trong document model, có thể cần reference hoặc cập nhật các document liên quan. Trong graph model, cần quản lý identity của node và các cạnh tham chiếu. Công nghệ khác nhau nhưng yêu cầu nghiệp vụ về danh tính vẫn phải rõ.

### 10.3. Định danh không thay thế kiểm soát truy cập

Biết customer_id không đồng nghĩa người dùng có quyền xem khách hàng đó. Định danh chỉ xác định đối tượng; quyền truy cập cần được kiểm tra theo vai trò, quan hệ sở hữu, tenant và mục đích.

Không nên coi việc dùng UUID khó đoán là biện pháp phân quyền. API vẫn phải xác minh quyền trên từng đối tượng.

## 11. Lỗi thường gặp khi nhận diện thực thể

- **Biến mọi danh từ thành bảng:** làm mô hình có quá nhiều bảng tham chiếu hoặc bảng không có ý nghĩa nghiệp vụ.
- **Dùng thuộc tính dễ thay đổi làm khóa chính:** đổi email hoặc mã hiển thị làm đứt tham chiếu.
- **Nhầm trạng thái với thực thể:** tạo một bảng cho từng trạng thái trong khi đó chỉ là giá trị hoặc sự kiện.
- **Nhầm sự kiện với đối tượng:** dùng mã sự kiện thay cho định danh thực thể xuyên suốt vòng đời.
- **Gộp nhiều vòng đời vào một thực thể:** tài khoản, khách hàng và phiên đăng nhập có quy tắc khác nhau nhưng bị đặt chung.
- **Tách value object quá mức:** tạo thực thể riêng cho mọi địa chỉ hoặc số tiền dù không có nhu cầu quản lý độc lập.
- **Không xác định phạm vi duy nhất:** một mã duy nhất trong một tenant bị dùng như mã toàn cục.
- **Tái sử dụng ID sau khi xóa:** tham chiếu lịch sử có thể trỏ sang đối tượng mới.
- **Không xử lý hợp nhất hồ sơ:** các hệ thống khác tiếp tục dùng mã cũ và tạo dữ liệu mồ côi.
- **Chỉ dựa vào khóa thay thế:** bỏ qua unique constraint trên các khóa nghiệp vụ.
- **Dùng một trạng thái cho nhiều đối tượng:** trạng thái thanh toán, đơn hàng và giao hàng bị trộn lẫn.
- **Thiết kế theo bảng cũ:** giữ nguyên cấu trúc kỹ thuật dù nghiệp vụ hiện tại đã thay đổi.

## 12. Tiêu chí kiểm chứng quyết định thực thể

Một quyết định mô hình hóa nên có ví dụ và cách kiểm tra. Các tình huống sau giúp phát hiện sai lầm:

**Đổi thuộc tính nhưng giữ danh tính**

- Given: một khách hàng có customer_id ổn định.
- When: khách hàng đổi tên hoặc email.
- Then: đơn hàng và lịch sử trước đó vẫn tham chiếu đúng khách hàng đó.

**Phân biệt hai trường hợp cùng thuộc tính**

- Given: hai khách hàng có cùng tên hiển thị.
- When: hệ thống tạo hồ sơ cho cả hai.
- Then: hệ thống không tự coi họ là một người chỉ dựa trên tên.

**Kiểm tra phạm vi duy nhất**

- Given: hai tổ chức có thể dùng cùng mã nhân viên.
- When: mỗi tổ chức tạo nhân viên có cùng employee_number.
- Then: mô hình vẫn phân biệt được hai nhân viên theo phạm vi tổ chức.

**Giữ định danh khi đổi mã nghiệp vụ**

- Given: đơn hàng có mã hiển thị cũ.
- When: quy tắc mã đơn hàng được thay đổi.
- Then: các tham chiếu nội bộ và lịch sử vẫn trỏ đến cùng đơn hàng.

**Xử lý thực thể phụ thuộc**

- Given: một đơn hàng có hai dòng cùng sản phẩm nhưng khác giá chốt.
- When: hệ thống lưu các dòng hàng.
- Then: mỗi dòng được phân biệt và có thể tham chiếu riêng khi xử lý hoàn tiền hoặc giao hàng.

**Hợp nhất hồ sơ**

- Given: hai hồ sơ khách hàng được xác nhận là trùng.
- When: nghiệp vụ hợp nhất chúng.
- Then: có hồ sơ chuẩn, ánh xạ mã cũ, xử lý tham chiếu và dấu vết thay đổi.

**Quản lý vòng đời**

- Given: một tài khoản đã bị khóa.
- When: người dùng thử đăng nhập hoặc quản trị viên yêu cầu mở lại.
- Then: hệ thống áp dụng đúng quy tắc chuyển trạng thái và lưu lịch sử theo yêu cầu.

## 13. Danh sách kiểm tra trước khi chốt thực thể

- [ ] Đã có định nghĩa nghiệp vụ rõ cho khái niệm.
- [ ] Đã xác định có cần phân biệt từng trường hợp cụ thể hay không.
- [ ] Đã kiểm tra danh tính có tồn tại khi thuộc tính mô tả thay đổi.
- [ ] Đã xác định hành động, trạng thái và vòng đời riêng nếu có.
- [ ] Đã kiểm tra các quy trình khác có cần tham chiếu đối tượng không.
- [ ] Đã phân biệt thực thể với thuộc tính, value object, dữ liệu tham chiếu, sự kiện và quy trình.
- [ ] Đã xác định phạm vi định danh và quy tắc duy nhất.
- [ ] Đã đánh giá khóa tự nhiên, khóa thay thế và khóa ghép.
- [ ] Đã xác định mã nội bộ, mã nghiệp vụ và mã từ hệ thống ngoài.
- [ ] Đã xác định cách xử lý đổi mã, hợp nhất, tách và xóa đối tượng.
- [ ] Đã xác định quan hệ phụ thuộc và việc đối tượng con có thể tồn tại độc lập hay không.
- [ ] Đã xác định yêu cầu lịch sử, lưu giữ và truy nguyên.
- [ ] Đã có tình huống kiểm chứng cho các trường hợp bình thường và ngoại lệ.
- [ ] Quyết định đã được người chịu trách nhiệm nghiệp vụ xác nhận.

Một khái niệm nên được mô hình hóa thành thực thể khi nghiệp vụ cần nhận diện từng trường hợp riêng, giữ danh tính qua những thay đổi hợp lệ và quản lý nó như một đối tượng có trách nhiệm hoặc vòng đời xác định. Định danh được chọn cần phản ánh đúng phạm vi duy nhất và không phụ thuộc vào thuộc tính dễ biến động. Làm rõ những điểm này trước khi tạo bảng và khóa sẽ giúp mô hình dữ liệu dễ tham chiếu, bảo toàn lịch sử và tiến hóa theo nghiệp vụ.

