# Quyền sở hữu, vòng đời phụ thuộc và ý nghĩa khi xóa thực thể liên quan

Trong mô hình dữ liệu, hai thực thể có quan hệ với nhau không có nghĩa là một thực thể sở hữu thực thể còn lại. Một khách hàng có thể đặt nhiều đơn hàng, nhưng đơn hàng đã phát sinh giao dịch thường cần được lưu giữ ngay cả khi hồ sơ khách hàng ngừng hoạt động. Ngược lại, một dòng đơn hàng thường chỉ có ý nghĩa trong phạm vi đơn hàng chứa nó; nếu đơn hàng nháp bị xóa theo quy trình cho phép, các dòng nháp tương ứng có thể được xóa cùng.

Vì vậy, khi mô hình hóa quan hệ, cần làm rõ ba câu hỏi:

- **Quyền sở hữu:** thực thể nào quản lý vòng đời của thực thể kia trong phạm vi nghiệp vụ?
- **Phụ thuộc vòng đời:** thực thể phụ thuộc có thể tồn tại độc lập khi thực thể chủ không còn hay không?
- **Ý nghĩa khi xóa:** nếu một bên bị xóa, dữ liệu ở bên còn lại phải được giữ, xóa theo, tách liên kết hay chuyển sang trạng thái khác?

Những câu hỏi này ảnh hưởng trực tiếp đến ranh giới thực thể, khóa, quan hệ, ràng buộc tham chiếu và chính sách lưu trữ. Chọn sai có thể làm mất dữ liệu giao dịch, tạo bản ghi mồ côi hoặc khiến hệ thống không thể giải thích lịch sử.

Bài học này giúp phân biệt quan hệ sở hữu với liên kết thông thường, nhận diện thực thể phụ thuộc, xác định vòng đời và chọn hành vi xóa phù hợp với ý nghĩa nghiệp vụ.

**Sau bài học, bạn có thể:**

- Phân biệt quan hệ sở hữu, quan hệ tham chiếu và quan hệ liên kết thông thường.
- Nhận diện thực thể phụ thuộc và thực thể có vòng đời độc lập.
- Mô tả vòng đời của thực thể chủ và thực thể con.
- Phân biệt xóa vật lý, xóa mềm, hủy nghiệp vụ, lưu trữ và ẩn danh hóa.
- Lựa chọn giữa RESTRICT, CASCADE, SET NULL và các chính sách xử lý khác.
- Kiểm tra nguy cơ dữ liệu mồ côi, xóa dây chuyền và mất lịch sử.
- Chuyển quyết định vòng đời thành mô hình logic có thể kiểm chứng.

## 1. Quyền sở hữu trong quan hệ dữ liệu là gì?

Trong bài học này, **quyền sở hữu** mô tả quan hệ phụ thuộc về vòng đời và trách nhiệm quản lý dữ liệu. Một thực thể chủ kiểm soát sự tồn tại hoặc phạm vi của một thực thể con theo quy tắc nghiệp vụ.

Ví dụ:

- Một đơn hàng quản lý các dòng đơn hàng của chính nó.
- Một giỏ hàng quản lý các mục đang nằm trong giỏ.
- Một hồ sơ người dùng quản lý các tùy chọn cá nhân của hồ sơ đó.
- Một phiếu nhập kho quản lý các dòng hàng được ghi nhận trên phiếu.

Khi thực thể chủ không còn hợp lệ, thực thể con có thể cũng không còn ý nghĩa độc lập. Dòng đơn hàng không thể được hiểu đúng nếu không biết nó thuộc đơn nào. Mục giỏ hàng không có ý nghĩa nếu giỏ hàng đã bị loại bỏ và nghiệp vụ không cho phép giữ mục đó như một đối tượng độc lập.

Quyền sở hữu trong mô hình dữ liệu không đồng nghĩa với quyền sở hữu pháp lý, quyền sở hữu tài sản hay quyền truy cập bảo mật. Một khách hàng có thể là chủ thể sở hữu tài khoản theo nghiệp vụ, nhưng quan hệ giữa CUSTOMER và ORDER vẫn cần được phân tích riêng về vòng đời dữ liệu.

### 1.1. Dấu hiệu của quan hệ sở hữu vòng đời

Một quan hệ có thể mang ý nghĩa sở hữu nếu phần lớn các dấu hiệu sau đúng:

- Thực thể con được tạo ra trong quá trình tạo hoặc vận hành thực thể chủ.
- Thực thể con luôn thuộc về một chủ thể cụ thể trong phạm vi nghiệp vụ.
- Thực thể con không có ý nghĩa độc lập nếu thiếu thực thể chủ.
- Định danh của con có thể phụ thuộc vào định danh của chủ.
- Quyền cập nhật, trạng thái hoặc quy tắc của con chịu ảnh hưởng trực tiếp từ chủ.
- Khi chủ kết thúc vòng đời, nghiệp vụ yêu cầu con cũng kết thúc, được lưu cùng hoặc được xử lý theo một quy tắc phụ thuộc rõ ràng.

Không nhất thiết mọi dấu hiệu đều phải đúng. Đây là bộ câu hỏi để xác minh, không phải công thức tự động kết luận.

### 1.2. Quyền sở hữu không đồng nghĩa với quan hệ một-nhiều

Một khách hàng có thể có nhiều đơn hàng, nhưng điều đó không có nghĩa đơn hàng là dữ liệu con phải bị xóa khi khách hàng bị xóa.

Một khách hàng có thể có nhiều địa chỉ trong sổ địa chỉ. Các địa chỉ này có thể thuộc hồ sơ khách hàng và được xóa khi hồ sơ bị xóa nếu chúng không được dùng ở nơi khác. Tuy nhiên, địa chỉ giao hàng đã chốt trên một đơn hàng có thể cần được lưu như bản chụp lịch sử của giao dịch.

Do đó:

- **Bội số** trả lời một instance liên kết với bao nhiêu instance khác.
- **Quyền sở hữu** trả lời ai quản lý vòng đời và sự tồn tại của dữ liệu liên quan.
- **Hành vi xóa** trả lời hệ thống xử lý dữ liệu liên quan như thế nào khi một đối tượng bị xóa.

Ba khía cạnh này có liên quan nhưng không thể suy ra thay thế cho nhau.

## 2. Phân biệt thực thể chủ, thực thể con và thực thể tham chiếu

### 2.1. Thực thể chủ (owner hoặc parent)

Thực thể chủ là đối tượng quản lý phạm vi tồn tại của một hoặc nhiều đối tượng con. Nó thường có định danh riêng và vòng đời nghiệp vụ riêng.

Ví dụ:

- ORDER là chủ của ORDER_LINE.
- CART là chủ của CART_ITEM.
- PURCHASE_ORDER là chủ của PURCHASE_ORDER_LINE.

Một thực thể chủ có thể tồn tại mà chưa có con trong một số trạng thái. Ví dụ giỏ hàng mới tạo có thể chưa có mục; đơn hàng nháp có thể đang được xây dựng. Vì vậy, không nên giả định quan hệ chủ-con luôn bắt buộc ở cả hai chiều.

### 2.2. Thực thể con phụ thuộc (dependent entity)

Thực thể con phụ thuộc là đối tượng cần thực thể chủ để được nhận diện hoặc để có ý nghĩa nghiệp vụ.

Ví dụ, một dòng đơn hàng thường được xác định trong phạm vi một đơn. Số thứ tự dòng có thể chỉ duy nhất trong đơn đó. Một dòng không có đơn chủ là bản ghi không hoàn chỉnh.

Một số dấu hiệu:

- Khóa nhận diện có chứa khóa của thực thể chủ;
- Mỗi instance con thuộc đúng một chủ trong cùng thời điểm;
- Không có vòng đời nghiệp vụ độc lập;
- Xóa hoặc kết thúc chủ làm con không còn hợp lệ;
- Thuộc tính của con phụ thuộc vào cả khóa chủ và phần định danh cục bộ.

### 2.3. Thực thể tham chiếu hoặc thực thể dùng chung

Thực thể tham chiếu có thể được nhiều thực thể khác sử dụng và có vòng đời riêng. Nó không tự động bị xóa khi một thực thể tham chiếu tới nó bị xóa.

Ví dụ:

- PRODUCT_VARIANT được nhiều dòng đơn hàng tham chiếu.
- WAREHOUSE được nhiều phiếu nhập, phiếu xuất và đợt giao tham chiếu.
- PAYMENT_METHOD được nhiều giao dịch sử dụng.
- CUSTOMER có thể được nhiều đơn hàng tham chiếu.

Một sản phẩm có thể được ngừng kinh doanh nhưng các dòng đơn hàng cũ vẫn cần tham chiếu để giải thích giao dịch lịch sử. Xóa sản phẩm ngay khi không còn bán có thể làm mất khả năng truy vết.

### 2.4. Bảng so sánh

| Tiêu chí | Thực thể chủ | Thực thể con phụ thuộc | Thực thể tham chiếu |
|---|---|---|---|
| Vai trò | Quản lý phạm vi hoặc vòng đời | Tồn tại trong phạm vi chủ | Được nhiều đối tượng tham chiếu |
| Định danh | Thường độc lập | Có thể phụ thuộc vào chủ | Thường độc lập |
| Có thể được dùng chung? | Có thể | Thường không | Thường có |
| Vòng đời | Điều phối hoặc bao chứa con | Gắn với chủ | Tách biệt |
| Khi chủ thể khác bị xóa | Theo quy tắc riêng | Có thể bị xóa cùng chủ | Thường được giữ |
| Ví dụ | Đơn hàng | Dòng đơn hàng | Biến thể sản phẩm |

## 3. Phân biệt phụ thuộc định danh và phụ thuộc vòng đời

Hai dạng phụ thuộc này thường đi cùng nhau nhưng không phải lúc nào cũng giống nhau.

### 3.1. Phụ thuộc định danh

Một thực thể phụ thuộc định danh không thể được nhận diện đầy đủ nếu thiếu khóa của thực thể chủ.

Ví dụ, dòng đơn hàng được nhận diện bằng cặp:

- order_id;
- line_number.

Trong phạm vi một đơn, line_number có thể là duy nhất. Nhưng giữa các đơn khác nhau, số dòng có thể lặp lại. Khóa ghép xác định dòng bằng cả đơn chủ và số thứ tự.

### 3.2. Phụ thuộc vòng đời

Một thực thể phụ thuộc vòng đời cần thực thể chủ tồn tại để bản thân nó còn ý nghĩa theo nghiệp vụ.

Ví dụ, một mục trong giỏ hàng thuộc về giỏ hàng cụ thể. Nếu giỏ hàng bị loại bỏ, mục đó có thể bị xóa cùng.

Một thực thể có ID riêng vẫn có thể phụ thuộc vòng đời. Ví dụ CART_ITEM có cart_item_id riêng để thuận tiện cập nhật, nhưng nó vẫn không có ý nghĩa nếu giỏ hàng chủ bị xóa.

Ngược lại, một bản ghi có khóa ghép không nhất thiết phải bị xóa cùng chủ trong mọi hoàn cảnh. Quy tắc lưu trữ lịch sử hoặc kiểm toán có thể yêu cầu giữ lại bản ghi, dù thực thể chủ đã chuyển sang trạng thái kết thúc. Cần xác định rõ đây là dữ liệu lịch sử hợp lệ hay một bản ghi mồ côi không mong muốn.

### 3.3. Bảng câu hỏi xác định phụ thuộc

| Câu hỏi | Nếu câu trả lời là Có | Nếu câu trả lời là Không |
|---|---|---|
| Con có thể được tạo nếu chưa có chủ không? | Có thể là thực thể độc lập hoặc quan hệ chưa được mô tả đầy đủ | Có dấu hiệu phụ thuộc vòng đời |
| Con có thể chuyển sang chủ khác không? | Cần quy tắc chuyển quyền sở hữu hoặc liên kết | Có thể phụ thuộc vào chủ hiện tại |
| Con có thể được tham chiếu bởi nhiều chủ không? | Có thể là thực thể dùng chung hoặc quan hệ kết hợp | Có thể là con riêng của một chủ |
| Khi chủ kết thúc, con có còn ý nghĩa không? | Cần giữ con hoặc chuyển trạng thái | Có thể xóa theo hoặc lưu trong phạm vi lịch sử |
| Con có định danh độc lập ổn định không? | Có thể độc lập về định danh | Có thể cần khóa ghép với chủ |

Không nên chỉ dựa vào một câu trả lời để quyết định. Ví dụ một địa chỉ có ID riêng nhưng vẫn được sở hữu trong sổ địa chỉ của khách hàng; cùng lúc đó, một bản chụp địa chỉ giao hàng trên đơn lại có vòng đời theo đơn hàng.

## 4. Vòng đời của thực thể chủ và thực thể con

Vòng đời mô tả các trạng thái và sự kiện từ khi tạo đến khi kết thúc của một đối tượng. Khi có quan hệ sở hữu, cần hiểu các sự kiện ở chủ ảnh hưởng tới con như thế nào.

Một vòng đời đơn giản có thể gồm:

1. Tạo thực thể chủ;
2. Tạo các thực thể con;
3. Cập nhật hoặc bổ sung con;
4. Xác nhận hoặc kích hoạt chủ;
5. Kết thúc, hủy hoặc lưu trữ chủ;
6. Xử lý dữ liệu con theo chính sách đã xác định.

Ví dụ, một giỏ hàng có thể ở trạng thái ACTIVE, CHECKED_OUT hoặc ABANDONED. Các mục giỏ hàng có thể được thêm, sửa, xóa trong khi giỏ còn hoạt động. Khi giỏ chuyển thành đơn hàng, hệ thống có thể chuyển các dòng hàng sang một cấu trúc mới hoặc tạo đơn và giữ giỏ như dữ liệu lịch sử. Đây là quyết định nghiệp vụ cần xác nhận.

### 4.1. Vòng đời không phải lúc nào cũng kết thúc bằng xóa vật lý

Khi một đơn hàng bị hủy, dữ liệu đơn và dòng hàng thường vẫn cần được giữ để giải thích giao dịch, kiểm toán vận hành hoặc hỗ trợ khách hàng. Hủy đơn là một sự kiện nghiệp vụ làm thay đổi trạng thái, không đồng nghĩa với xóa bản ghi.

Tương tự:

- Ngừng bán sản phẩm không nhất thiết xóa sản phẩm.
- Khóa tài khoản không nhất thiết xóa tài khoản.
- Đóng hợp đồng không nhất thiết xóa lịch sử hợp đồng.
- Hủy yêu cầu chưa được duyệt có thể chuyển trạng thái thành CANCELLED thay vì xóa.

### 4.2. Chuyển quyền sở hữu hoặc chuyển chủ

Một số đối tượng có thể được chuyển từ chủ này sang chủ khác. Ví dụ, một thiết bị được chuyển từ phòng ban này sang phòng ban khác, hoặc một hồ sơ được chuyển cho nhóm xử lý mới.

Cần phân biệt:

- Chuyển chủ sở hữu hiện tại;
- Thêm một bên liên quan mới;
- Kết thúc quan hệ cũ và tạo quan hệ mới;
- Lưu lịch sử các lần chuyển giao.

Nếu quyền sở hữu thay đổi theo thời gian, có thể cần một thực thể quan hệ như ASSET_ASSIGNMENT gồm asset_id, owner_id, valid_from và valid_to. Cách này giữ được lịch sử ai chịu trách nhiệm trong từng giai đoạn.

Không nên chỉ ghi đè owner_id nếu nghiệp vụ cần truy vết các lần bàn giao.

## 5. Ý nghĩa của việc xóa một thực thể liên quan

Xóa dữ liệu có thể mang nhiều ý nghĩa. Trước khi chọn hành vi trong mô hình logic, hãy hỏi người dùng đang muốn kết thúc điều gì.

| Hành động | Ý nghĩa | Ví dụ |
|---|---|---|
| Xóa vật lý | Loại bỏ bản ghi khỏi kho dữ liệu | Xóa mục giỏ hàng nháp |
| Xóa mềm | Đánh dấu bản ghi không còn hoạt động hoặc bị xóa | Đánh dấu địa chỉ cũ là inactive |
| Hủy nghiệp vụ | Ghi nhận một sự kiện làm đối tượng chuyển sang trạng thái hủy | Hủy đơn hàng đã tạo |
| Ngừng hoạt động | Không cho sử dụng trong giao dịch mới nhưng vẫn giữ dữ liệu | Ngừng bán biến thể sản phẩm |
| Lưu trữ | Chuyển dữ liệu sang vùng lưu trữ hoặc trạng thái lưu trữ | Lưu đơn đã hoàn tất lâu ngày |
| Ẩn danh hóa | Thay hoặc loại bỏ thông tin nhận dạng theo quy tắc phù hợp | Ẩn danh thông tin cá nhân khi không còn cần nhận diện |

Những hành động này không tương đương. Ví dụ, xóa mềm không tự động xóa các bản ghi con; hủy đơn không có nghĩa là xóa dòng đơn hàng; ngừng bán sản phẩm không có nghĩa là xóa tham chiếu trong đơn cũ.

### 5.1. Xóa thực thể chủ

Khi một thực thể chủ bị yêu cầu xóa, cần rà soát:

- Có thực thể con phụ thuộc nào không?
- Có thực thể dùng chung đang tham chiếu tới nó không?
- Có bản ghi lịch sử hoặc giao dịch cần giữ không?
- Có ràng buộc pháp lý, kiểm toán, đối soát hoặc vận hành không?
- Có hệ thống ngoài nào đang giữ tham chiếu không?
- Có thể ẩn danh hoặc vô hiệu hóa thay cho xóa vật lý không?

Không nên áp dụng một hành vi xóa cho mọi quan hệ chỉ vì chúng đều có khóa ngoại.

### 5.2. Xóa thực thể con

Khi xóa một thực thể con, cần kiểm tra liệu nó có đang được tham chiếu bởi thực thể khác hoặc đã tham gia giao dịch không.

Ví dụ, một dòng đơn hàng có thể bị xóa khi đơn còn ở trạng thái nháp. Sau khi đơn được xác nhận hoặc đã giao, xóa dòng có thể làm sai lệch tổng tiền, hóa đơn, thanh toán và lịch sử giao hàng. Khi đó, nghiệp vụ có thể yêu cầu hủy dòng, điều chỉnh hoặc tạo giao dịch bù trừ.

## 6. Các hành vi ON DELETE trong mô hình quan hệ

Trong cơ sở dữ liệu quan hệ, khóa ngoại có thể quy định hành vi khi bản ghi được tham chiếu bị xóa. Những lựa chọn phổ biến gồm RESTRICT, NO ACTION, CASCADE, SET NULL và SET DEFAULT. Cú pháp, thời điểm kiểm tra và chi tiết hỗ trợ có thể khác giữa các hệ quản trị.

### 6.1. RESTRICT

RESTRICT ngăn xóa bản ghi cha nếu còn bản ghi con tham chiếu.

Ví dụ: không cho xóa PRODUCT_VARIANT nếu vẫn có dòng đơn hàng lịch sử tham chiếu tới biến thể đó.

Đây thường là lựa chọn phù hợp khi dữ liệu con cần giữ và việc xóa chủ phải được giải quyết bằng một quy trình nghiệp vụ khác, chẳng hạn ngừng kinh doanh sản phẩm.

### 6.2. NO ACTION

NO ACTION cũng yêu cầu quan hệ tham chiếu phải hợp lệ khi ràng buộc được kiểm tra. Tùy hệ quản trị, thời điểm kiểm tra và khả năng trì hoãn ràng buộc có thể khác RESTRICT.

Không nên giả định hai từ này luôn có cùng hành vi ở mọi nền tảng. Khi triển khai, cần kiểm tra tài liệu của hệ quản trị và thời điểm constraint được đánh giá.

### 6.3. CASCADE

CASCADE xóa các bản ghi con tham chiếu khi bản ghi cha bị xóa. Nó phù hợp khi dữ liệu con thực sự phụ thuộc và không có ý nghĩa độc lập.

Ví dụ, nếu một giỏ hàng nháp bị xóa, các mục giỏ hàng riêng của nó có thể bị xóa cùng. Với dòng đơn hàng, cascade có thể phù hợp trong phạm vi đơn nháp được phép xóa vật lý.

CASCADE cần được sử dụng cẩn thận:

- Xóa một bản ghi cha có thể xóa nhiều tầng dữ liệu;
- Một bảng con có thể được nhiều quan hệ khác tham chiếu;
- Chuỗi cascade có thể lan rộng ngoài dự kiến;
- Có thể xóa mất lịch sử hoặc dữ liệu cần đối soát;
- Khó phát hiện tác động nếu không kiểm tra toàn bộ đồ thị khóa ngoại.

### 6.4. SET NULL

SET NULL giữ bản ghi con nhưng đặt khóa ngoại tham chiếu về NULL khi bản ghi cha bị xóa.

Nó phù hợp khi quan hệ là tùy chọn và bản ghi con vẫn có ý nghĩa độc lập. Ví dụ, một phiếu hỗ trợ có thể giữ lại dù nhân viên phụ trách cũ đã bị xóa khỏi hệ thống, nếu nghiệp vụ cho phép bỏ tham chiếu người phụ trách.

Không dùng SET NULL nếu khóa ngoại là một phần của khóa chính, hoặc nếu NULL làm mất thông tin bắt buộc. Cũng cần xác định liệu việc mất liên kết có làm dữ liệu trở nên khó giải thích hay không.

### 6.5. SET DEFAULT

SET DEFAULT thay khóa ngoại bằng giá trị mặc định khi bản ghi cha bị xóa. Giá trị mặc định phải tham chiếu tới một bản ghi hợp lệ nếu có ràng buộc khóa ngoại.

Ví dụ, một bản ghi có thể được chuyển về một nhóm mặc định như “Chưa phân công” nếu nghiệp vụ xác định nhóm đó tồn tại và có ý nghĩa. Tuy nhiên, không nên dùng một giá trị mặc định giả tạo để che đi việc mất quan hệ.

### 6.6. Bảng so sánh hành vi

| Hành vi | Dữ liệu con | Quan hệ sau khi xóa cha | Khi cân nhắc |
|---|---|---|---|
| RESTRICT | Được giữ | Không cho xóa cha nếu còn tham chiếu | Con cần tồn tại và tham chiếu cha |
| NO ACTION | Được giữ | Kiểm tra toàn vẹn tại thời điểm constraint | Khi dùng quy tắc kiểm tra của hệ quản trị |
| CASCADE | Bị xóa theo | Không còn bản ghi con | Con phụ thuộc hoàn toàn và được phép xóa |
| SET NULL | Được giữ | Khóa ngoại thành NULL | Quan hệ có thể mất mà con vẫn hợp lệ |
| SET DEFAULT | Được giữ | Khóa ngoại chuyển sang mặc định | Có đối tượng mặc định hợp lệ, có ý nghĩa |

Không có lựa chọn nào luôn đúng. Quyết định phải dựa trên vòng đời và ý nghĩa nghiệp vụ của từng quan hệ.

## 7. Ví dụ: đơn hàng và dòng đơn hàng

Một đơn hàng có các dòng hàng. Dòng hàng không có ý nghĩa nếu không thuộc đơn. Trong một hệ thống cho phép xóa đơn nháp chưa phát sinh giao dịch, xóa đơn có thể kéo theo xóa các dòng nháp.

~~~mermaid
erDiagram
    ORDER ||--|{ ORDER_LINE : owns
    PRODUCT_VARIANT ||--o{ ORDER_LINE : referenced_by
~~~

Một cấu trúc logic minh họa:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    order_status VARCHAR(30) NOT NULL
);

CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_number INTEGER NOT NULL,
    product_variant_id BIGINT NOT NULL,
    quantity DECIMAL(12, 3) NOT NULL,
    unit_price DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (order_id, line_number),
    FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
        ON DELETE CASCADE,
    FOREIGN KEY (product_variant_id)
        REFERENCES product_variant(product_variant_id)
        ON DELETE RESTRICT
);
~~~

Trong ví dụ:

- ORDER là thực thể chủ của ORDER_LINE.
- ORDER_LINE phụ thuộc vào đơn để xác định và tồn tại.
- PRODUCT_VARIANT là thực thể tham chiếu; dòng hàng không sở hữu sản phẩm.
- Xóa đơn có thể xóa dòng nếu quy trình cho phép.
- Xóa biến thể sản phẩm bị ngăn nếu vẫn có dòng hàng tham chiếu.

Tuy nhiên, cascade ở khóa ngoại không biết trạng thái đơn. Nếu hệ thống chỉ được xóa đơn ở trạng thái DRAFT, quy tắc đó phải được kiểm tra bằng quy trình nghiệp vụ hoặc cơ chế bổ sung. Khóa ngoại chỉ xử lý tham chiếu, không tự hiểu điều kiện “chỉ xóa đơn nháp”.

## 8. Ví dụ: khách hàng, đơn hàng và dữ liệu lịch sử

Một khách hàng có thể tạo nhiều đơn hàng. Mối quan hệ này có bội số một-nhiều, nhưng đơn hàng thường cần tồn tại độc lập sau khi giao dịch đã phát sinh.

Nếu xóa khách hàng bằng CASCADE, hệ thống có thể xóa toàn bộ đơn hàng, dòng hàng và các thông tin lịch sử liên quan. Đây thường là hành vi nguy hiểm đối với dữ liệu giao dịch.

Một hướng thiết kế có thể là:

- Giữ đơn hàng và các dòng hàng;
- Ngăn xóa cứng khách hàng nếu còn đơn tham chiếu;
- Hoặc ẩn danh hóa thông tin cá nhân theo chính sách được xác nhận;
- Giữ các thông tin giao dịch tối thiểu cần thiết để giải thích đơn;
- Phân biệt dữ liệu hồ sơ hiện tại với bản chụp thông tin tại thời điểm đặt.

Ví dụ, đơn hàng có thể lưu tên người nhận và địa chỉ giao hàng tại thời điểm đặt. Khi khách hàng đổi địa chỉ trong hồ sơ, đơn cũ vẫn giữ địa chỉ đã chốt. Bản chụp này thuộc lịch sử giao dịch và không nên bị thay đổi theo hồ sơ hiện tại.

### 8.1. Ngừng hoạt động thay cho xóa

Đối với khách hàng, sản phẩm, kho hoặc phương thức thanh toán, nghiệp vụ thường có nhu cầu ngừng sử dụng hơn là xóa dữ liệu. Có thể dùng trạng thái như ACTIVE, INACTIVE hoặc DEACTIVATED, cùng thời điểm thay đổi nếu cần.

Cần xác định rõ:

- Đối tượng không được dùng trong giao dịch mới;
- Các giao dịch cũ vẫn tham chiếu được;
- Người dùng có thể xem lịch sử hay không;
- Có được kích hoạt lại hay không;
- Mã nghiệp vụ có được tái sử dụng hay không.

Không nên dùng một cờ is_deleted duy nhất để đại diện cho mọi trạng thái kết thúc nếu nghiệp vụ cần phân biệt hủy, ngừng hoạt động, lưu trữ và xóa theo yêu cầu.

## 9. Xóa mềm, lưu trữ và ẩn danh hóa

### 9.1. Xóa mềm

Xóa mềm giữ bản ghi trong cơ sở dữ liệu nhưng đánh dấu nó không còn hiển thị hoặc không còn hoạt động theo chính sách ứng dụng. Ví dụ có thể dùng deleted_at, deleted_by hoặc trạng thái DELETED.

Ưu điểm:

- Có thể khôi phục trong khoảng thời gian cho phép;
- Giữ tham chiếu từ dữ liệu lịch sử;
- Hỗ trợ điều tra và kiểm toán;
- Tránh xóa dây chuyền ngoài ý muốn.

Cần lưu ý:

- Khóa ngoại vẫn nhìn thấy bản ghi đã xóa mềm;
- Truy vấn phải lọc trạng thái phù hợp;
- Ràng buộc duy nhất có thể cần xét riêng các bản ghi đang hoạt động;
- Báo cáo có thể vô tình tính cả dữ liệu đã xóa mềm;
- Việc khôi phục phải kiểm tra xung đột và quy tắc vòng đời.

Xóa mềm không tự động tương đương với CASCADE. Nếu muốn đánh dấu con cùng chủ, ứng dụng phải thực hiện quy trình rõ ràng hoặc dùng cơ chế quản lý trạng thái phù hợp.

### 9.2. Lưu trữ

Lưu trữ thường chuyển dữ liệu cũ sang vùng hoặc trạng thái dành cho truy cập ít thường xuyên. Dữ liệu vẫn có thể cần cho báo cáo, kiểm toán hoặc truy vấn lịch sử.

Khi lưu trữ thực thể chủ, cần bảo đảm dữ liệu con và quan hệ liên quan vẫn có thể được tra cứu hoặc tái dựng. Không chuyển riêng bảng cha mà để mất khả năng liên kết với bảng con.

### 9.3. Ẩn danh hóa

Ẩn danh hóa thay hoặc loại bỏ thông tin nhận diện trong khi giữ lại phần dữ liệu có thể cần cho mục đích khác. Ví dụ, có thể cần giữ thông tin giao dịch nhưng không còn hiển thị tên hoặc thông tin liên hệ cá nhân theo chính sách được phê duyệt.

Ẩn danh hóa không đồng nghĩa với xóa mềm. Nó có thể làm thay đổi giá trị dữ liệu, do đó phải xác định:

- Thuộc tính nào được giữ;
- Thuộc tính nào được thay hoặc xóa;
- Có cần giữ khả năng liên kết giữa các giao dịch không;
- Có cần giữ mã định danh giả danh hay không;
- Những bảng hoặc bản sao nào cũng phải xử lý.

Đây là quyết định nghiệp vụ và quản trị dữ liệu, không nên tự suy ra chỉ từ quan hệ khóa ngoại.

## 10. Khi nào nên dùng CASCADE và khi nào nên ngăn xóa?

Một quy tắc thực hành là chỉ dùng CASCADE khi dữ liệu con thật sự phụ thuộc vào cha và nghiệp vụ cho phép xóa vật lý cả hai.

| Quan hệ | Hành vi thường cân nhắc | Lý do |
|---|---|---|
| CART → CART_ITEM | CASCADE | Mục giỏ hàng phụ thuộc giỏ; có thể xóa giỏ nháp |
| ORDER → ORDER_LINE | CASCADE có điều kiện nghiệp vụ | Dòng phụ thuộc đơn, nhưng đơn đã phát sinh giao dịch thường không được xóa cứng |
| PRODUCT_VARIANT → ORDER_LINE | RESTRICT hoặc ngừng hoạt động sản phẩm | Dòng đơn hàng lịch sử cần giữ tham chiếu |
| CUSTOMER → ORDER | RESTRICT hoặc giữ/ẩn danh khách hàng | Đơn hàng cần tồn tại sau giao dịch |
| ORDER → PAYMENT_ATTEMPT | Thường giữ và ngăn xóa đơn khi đã có giao dịch | Lịch sử xử lý thanh toán cần truy vết |
| SHIPMENT → SHIPMENT_EVENT | Có thể CASCADE nếu kiện bị xóa hợp lệ; thường giữ lịch sử khi đã bàn giao | Sự kiện phụ thuộc kiện nhưng có thể cần lưu lịch sử |
| USER → USER_PREFERENCE | Có thể CASCADE | Tùy chọn cá nhân có thể phụ thuộc hồ sơ |
| USER → AUDIT_EVENT | Thường giữ sự kiện và xử lý danh tính theo chính sách | Lịch sử kiểm toán không nên mất chỉ vì tài khoản bị xóa |

Các hành vi trong bảng chỉ là gợi ý ban đầu. Phải xác nhận quy trình, yêu cầu lưu giữ và trạng thái thực tế trước khi chốt.

## 11. Tránh dữ liệu mồ côi và xóa dây chuyền ngoài ý muốn

### 11.1. Dữ liệu mồ côi (orphan record)

Bản ghi mồ côi là bản ghi con tham chiếu tới thực thể chủ không còn tồn tại hoặc không thể xác định theo mô hình.

Khóa ngoại có thể ngăn nhiều trường hợp mồ côi trong cơ sở dữ liệu quan hệ. Tuy nhiên, dữ liệu mồ côi vẫn có thể xuất hiện nếu:

- Ràng buộc khóa ngoại không được khai báo hoặc bị vô hiệu hóa;
- Dữ liệu được import không qua kiểm tra;
- Dữ liệu được lưu ở nhiều hệ thống không có transaction chung;
- Khóa tham chiếu bị thay đổi hoặc xóa thủ công;
- Quan hệ được biểu diễn bằng mã trong văn bản thay vì khóa ngoại.

Cần có quy trình kiểm tra và đối soát nếu dữ liệu được đồng bộ qua nhiều hệ thống.

### 11.2. Xóa dây chuyền

Xóa dây chuyền xảy ra khi xóa một bản ghi cha kích hoạt xóa nhiều bản ghi con, rồi tiếp tục xóa các bản ghi ở tầng sâu hơn.

Ví dụ:

~~~mermaid
flowchart TD
    A["Xóa CUSTOMER"] --> B["ORDER"]
    B --> C["ORDER_LINE"]
    B --> D["PAYMENT"]
    B --> E["SHIPMENT"]
    E --> F["SHIPMENT_EVENT"]
    style D fill:#fce8e6,stroke:#c5221f,color:#5f1110
    style F fill:#fce8e6,stroke:#c5221f,color:#5f1110
~~~

Sơ đồ chỉ minh họa một chuỗi phụ thuộc có thể xảy ra. Nếu tất cả quan hệ đều dùng CASCADE, một thao tác xóa khách hàng có thể xóa cả giao dịch và lịch sử vận chuyển. Điều đó có thể vi phạm yêu cầu lưu giữ dữ liệu.

Trước khi chọn cascade, hãy lần theo toàn bộ các đường tham chiếu và trả lời:

- Những bảng nào có thể bị xóa gián tiếp?
- Có dữ liệu nào được chia sẻ hoặc cần lưu độc lập không?
- Có bản ghi nào đã phát sinh giao dịch hoặc nghĩa vụ không?
- Có cần yêu cầu xác nhận hoặc quy trình nghiệp vụ riêng không?
- Có thể kiểm tra tác động trước khi thực hiện không?

### 11.3. Xóa có kiểm soát

Với nghiệp vụ quan trọng, ứng dụng có thể thực hiện một quy trình xóa có kiểm soát:

1. Kiểm tra trạng thái và quyền thực hiện;
2. Kiểm tra các thực thể phụ thuộc;
3. Xác định dữ liệu được giữ, xóa, ẩn danh hoặc chuyển trạng thái;
4. Ghi nhận lý do và người thực hiện nếu cần;
5. Thực hiện các thay đổi trong transaction hoặc quy trình nhất quán;
6. Kiểm tra tham chiếu và kết quả;
7. Ghi nhận sự kiện hoàn tất.

Không phải thao tác nào cũng cần một quy trình dài. Nhưng đối với giao dịch, hồ sơ dùng chung hoặc dữ liệu có lịch sử, cần xác định rõ tác động trước khi cho phép xóa.

## 12. Quyền sở hữu trong document, graph và dữ liệu phân tích

Quyền sở hữu và vòng đời phụ thuộc vẫn quan trọng khi không dùng mô hình quan hệ.

### 12.1. Mô hình document

Một document có thể chứa các thành phần con được quản lý cùng aggregate. Ví dụ document ORDER chứa mảng ORDER_LINE.

Nếu dòng hàng chỉ có ý nghĩa trong đơn và luôn được đọc/cập nhật cùng đơn, nhúng dòng hàng có thể phù hợp. Khi xóa document ORDER, các phần tử nhúng biến mất cùng document.

Tuy nhiên, nếu dòng hàng cần được tham chiếu độc lập từ nhiều kiện giao, lịch sử hoặc hệ thống khác, cần cân nhắc định danh riêng hoặc cấu trúc tham chiếu. Việc nhúng không tự giải quyết mọi quy tắc vòng đời.

### 12.2. Mô hình đồ thị

Trong đồ thị, xóa một node không nhất thiết đồng nghĩa xóa mọi node hàng xóm. Cần phân biệt:

- Xóa cạnh: chấm dứt quan hệ;
- Xóa node: loại bỏ đối tượng;
- Xóa node phụ thuộc: xóa các đối tượng chỉ có ý nghĩa dưới node chủ;
- Giữ node và đánh dấu trạng thái: lưu lịch sử nhưng không còn hoạt động.

Ví dụ, một CUSTOMER có thể liên kết với ORDER bằng cạnh PLACED. Xóa cạnh không nên tự động xóa ORDER nếu đơn hàng có vòng đời độc lập. Ngược lại, một node CART_ITEM có thể phụ thuộc vào CART và được xóa cùng khi giỏ bị xóa hợp lệ.

### 12.3. Mô hình phân tích

Dữ liệu phân tích thường cần giữ sự kiện và snapshot lịch sử. Xóa thực thể chiều hiện tại không nên làm mất các fact lịch sử đã ghi nhận.

Ví dụ, một sản phẩm ngừng kinh doanh vẫn có thể xuất hiện trong fact bán hàng quá khứ. Có thể dùng trạng thái inactive, chiều phiên bản hoặc khóa thay thế để duy trì liên kết lịch sử.

Nếu một chiều bị xóa hoặc thay đổi, cần quyết định fact cũ sẽ tham chiếu phiên bản nào, dùng thành viên “không xác định” hay giữ snapshot mô tả tại thời điểm sự kiện. Không nên xóa dây chuyền fact chỉ vì một thực thể mô tả không còn hoạt động.

## 13. Quy trình xác định chính sách vòng đời và xóa

Có thể sử dụng quy trình sau khi khảo sát một quan hệ.

### Bước 1: Xác định hai đầu và ý nghĩa quan hệ

Ghi rõ thực thể chủ thể, thực thể được tham chiếu, tên quan hệ và vai trò ở hai đầu.

### Bước 2: Viết độ hạt của mỗi thực thể

Xác định một bản ghi đại diện cho điều gì. Nếu con không có ý nghĩa ngoài chủ, ghi rõ đơn vị phụ thuộc.

### Bước 3: Kiểm tra quyền sở hữu và chia sẻ

Hỏi con có thể thuộc nhiều chủ không, có thể chuyển chủ không, có được tham chiếu từ đối tượng khác không và ai chịu trách nhiệm quản lý vòng đời.

### Bước 4: Vẽ vòng đời

Liệt kê các trạng thái và sự kiện của chủ và con. Xác định tạo, kích hoạt, kết thúc, hủy, lưu trữ và khôi phục.

### Bước 5: Xác định ý nghĩa của từng loại xóa

Phân biệt xóa vật lý, xóa mềm, hủy nghiệp vụ, ngừng hoạt động, lưu trữ và ẩn danh hóa. Không gộp chúng thành một hành động chung.

### Bước 6: Chọn hành vi tham chiếu

Chọn RESTRICT, NO ACTION, CASCADE, SET NULL hoặc cơ chế xử lý nghiệp vụ phù hợp. Kiểm tra tác động nhiều tầng.

### Bước 7: Kiểm tra dữ liệu lịch sử và bản ghi dùng chung

Đảm bảo giao dịch, sự kiện, fact và các đối tượng được nhiều nơi tham chiếu không bị xóa ngoài ý muốn.

### Bước 8: Xác nhận với người phụ trách nghiệp vụ

Đưa ra ví dụ cụ thể: “Nếu xóa một khách hàng đã có đơn đã giao, hệ thống phải làm gì với đơn, thanh toán, hóa đơn và địa chỉ?” Ghi lại quyết định và người xác nhận.

~~~mermaid
flowchart TD
    A["Quan hệ giữa hai thực thể"] --> B["Xác định vai trò và độ hạt"]
    B --> C["Kiểm tra sở hữu và phụ thuộc vòng đời"]
    C --> D{"Con có ý nghĩa độc lập?"}
    D -->|Không| E["Xác định chính sách kết thúc cùng chủ"]
    D -->|Có| F["Xác định cách giữ hoặc tách tham chiếu"]
    E --> G["Phân biệt xóa vật lý, hủy và lưu trữ"]
    F --> G
    G --> H["Chọn hành vi xóa và ràng buộc"]
    H --> I["Kiểm tra cascade, orphan và lịch sử"]
    I --> J["Xác nhận với nghiệp vụ"]
~~~

## 14. Những câu hỏi cần ghi trong từ điển dữ liệu

Với mỗi quan hệ có ý nghĩa sở hữu hoặc phụ thuộc, nên ghi nhận các thông tin:

| Trường thông tin | Nội dung cần ghi |
|---|---|
| Owner concept | Thực thể quản lý vòng đời |
| Dependent concept | Thực thể có thể phụ thuộc |
| Relationship name | Tên quan hệ nghiệp vụ |
| Ownership type | Sở hữu vòng đời, tham chiếu hay liên kết |
| Dependency | Phụ thuộc định danh, phụ thuộc vòng đời hay không |
| Transferability | Có thể chuyển chủ hay không |
| Parent deletion policy | Khi chủ bị xóa, con được xử lý thế nào |
| Child deletion policy | Khi con bị xóa, chủ có bị ảnh hưởng không |
| Historical retention | Có cần giữ lịch sử hoặc snapshot không |
| Business condition | Điều kiện trạng thái hoặc quyền cho phép xóa |
| Confirmation owner | Người/bộ phận xác nhận quy tắc |

Ví dụ mô tả ngắn:

~~~yaml
relationship:
  name: ORDER_OWNS_ORDER_LINE
  owner_concept: ORDER
  dependent_concept: ORDER_LINE
  ownership_type: lifecycle
  dependency:
    identifying: true
    lifecycle: true
  transferability: false
  parent_deletion_policy:
    draft: cascade
    confirmed_or_later: prohibit_physical_delete
  child_deletion_policy:
    allowed_when: order_status_is_draft
  historical_retention:
    required_after_confirmation: true
  confirmation_owner: Order Operations
~~~

Đây là cấu trúc tài liệu minh họa, không phải định dạng bắt buộc. Giá trị cần được xác nhận với nghiệp vụ và ánh xạ sang ràng buộc hoặc quy trình thực thi cụ thể.

## 15. Những lỗi thường gặp

1. **Coi mọi quan hệ 1:N là sở hữu:** khách hàng có nhiều đơn không có nghĩa xóa khách hàng sẽ xóa đơn.
2. **Coi khóa ngoại là bằng chứng của quyền sở hữu:** khóa ngoại chỉ thể hiện tham chiếu, không mô tả đầy đủ vòng đời.
3. **Dùng CASCADE cho mọi quan hệ:** có thể xóa dữ liệu lịch sử hoặc dữ liệu dùng chung.
4. **Không phân biệt hủy và xóa:** hủy đơn là sự kiện nghiệp vụ, thường cần giữ lịch sử.
5. **Nhầm thực thể có ID riêng là độc lập:** một mục giỏ hàng có ID riêng nhưng vẫn có thể phụ thuộc vào giỏ.
6. **Nhầm phụ thuộc định danh với phụ thuộc vòng đời:** khóa ghép không tự quyết định chính sách xóa.
7. **Dùng SET NULL cho quan hệ bắt buộc:** làm mất liên kết mà nghiệp vụ yêu cầu.
8. **Giữ bản ghi mồ côi mà không có ý nghĩa:** dữ liệu con không có chủ hoặc không thể giải thích.
9. **Xóa thực thể dùng chung:** sản phẩm, kho hoặc phương thức thanh toán có thể được nhiều giao dịch tham chiếu.
10. **Không kiểm tra cascade nhiều tầng:** một thao tác xóa có thể lan sang nhiều bảng.
11. **Dùng xóa mềm nhưng quên lọc truy vấn:** bản ghi đã xóa vẫn xuất hiện trong màn hình hoặc báo cáo.
12. **Ẩn danh hóa không đồng bộ:** thông tin nhận diện vẫn còn trong bản chụp, log hoặc bảng liên quan.
13. **Không ghi lịch sử chuyển chủ:** chỉ ghi đè khóa chủ làm mất thông tin bàn giao.
14. **Không xác định chính sách cho từng trạng thái:** xóa đơn nháp và xóa đơn đã giao có thể cần hai hành vi khác nhau.

## 16. Checklist trước khi chốt quan hệ sở hữu và chính sách xóa

- [ ] Đã xác định rõ thực thể chủ, thực thể con và thực thể tham chiếu.
- [ ] Đã phân biệt bội số với quyền sở hữu vòng đời.
- [ ] Độ hạt và định danh của thực thể con đã rõ.
- [ ] Đã xác định phụ thuộc định danh và phụ thuộc vòng đời.
- [ ] Đã xác nhận con có thể được chia sẻ hoặc chuyển sang chủ khác không.
- [ ] Vòng đời và trạng thái kết thúc của cả hai phía đã được mô tả.
- [ ] Đã phân biệt xóa vật lý, xóa mềm, hủy, ngừng hoạt động, lưu trữ và ẩn danh hóa.
- [ ] Hành vi RESTRICT, NO ACTION, CASCADE, SET NULL hoặc SET DEFAULT có lý do nghiệp vụ rõ.
- [ ] Đã rà soát toàn bộ tác động cascade nhiều tầng.
- [ ] Giao dịch, hóa đơn, thanh toán và sự kiện lịch sử được giữ theo yêu cầu.
- [ ] Đã có cách xử lý dữ liệu mồ côi và tham chiếu từ hệ thống ngoài.
- [ ] Xóa mềm có quy tắc truy vấn, uniqueness và khôi phục.
- [ ] Các quyết định theo trạng thái đã được ghi rõ.
- [ ] Người phụ trách nghiệp vụ đã xác nhận chính sách.

## 17. Bài tập thực hành

Một hệ thống bán hàng có các quy tắc:

- Một giỏ hàng có nhiều mục giỏ hàng.
- Mục giỏ hàng chỉ có ý nghĩa trong một giỏ.
- Khi khách hàng đặt mua, hệ thống tạo đơn hàng và các dòng đơn hàng.
- Một đơn có thể có nhiều lần thử thanh toán.
- Một đơn có thể có nhiều kiện giao hàng và sự kiện vận chuyển.
- Sản phẩm có thể được ngừng bán nhưng đơn hàng cũ vẫn cần hiển thị.
- Khách hàng có thể yêu cầu ngừng sử dụng tài khoản.
- Đơn đã giao phải được giữ để tra cứu lịch sử.

Hãy đề xuất chính sách vòng đời và xóa cho các quan hệ:

1. CART → CART_ITEM;
2. ORDER → ORDER_LINE;
3. ORDER → PAYMENT_ATTEMPT;
4. ORDER → SHIPMENT;
5. SHIPMENT → SHIPMENT_EVENT;
6. PRODUCT_VARIANT → ORDER_LINE;
7. CUSTOMER → ORDER;
8. CUSTOMER → CUSTOMER_PROFILE.

Với mỗi quan hệ, hãy nêu:

- Có phải quan hệ sở hữu vòng đời không?
- Thực thể con có thể tồn tại độc lập không?
- Hành vi xóa hoặc kết thúc phù hợp là gì?
- Cần giữ dữ liệu lịch sử nào?
- Ràng buộc nào có thể dùng và quy tắc nào cần xử lý ở tầng nghiệp vụ?

**Gợi ý đáp án:**

| Quan hệ | Nhận định vòng đời | Chính sách tham khảo |
|---|---|---|
| CART → CART_ITEM | Mục giỏ phụ thuộc giỏ | Có thể CASCADE khi xóa giỏ nháp |
| ORDER → ORDER_LINE | Dòng phụ thuộc đơn | Có thể CASCADE chỉ với đơn nháp; đơn đã xác nhận cần hủy hoặc giữ lịch sử |
| ORDER → PAYMENT_ATTEMPT | Lần thử là lịch sử xử lý giao dịch | Thường ngăn xóa đơn đã có lần thử; giữ bản ghi để truy vết |
| ORDER → SHIPMENT | Kiện giao có định danh vận hành và lịch sử riêng | Giữ đơn và kiện; xử lý hủy hoặc hoàn tất theo trạng thái |
| SHIPMENT → SHIPMENT_EVENT | Sự kiện phụ thuộc kiện về ngữ cảnh | Giữ cùng lịch sử kiện; chỉ xóa khi kiện chưa phát sinh sự kiện cần lưu |
| PRODUCT_VARIANT → ORDER_LINE | Biến thể là thực thể tham chiếu | Ngăn xóa cứng khi có dòng lịch sử; chuyển sang inactive |
| CUSTOMER → ORDER | Đơn có vòng đời giao dịch độc lập | Giữ đơn; ngừng hoặc ẩn danh hồ sơ theo chính sách |
| CUSTOMER → CUSTOMER_PROFILE | Hồ sơ có thể phụ thuộc tài khoản | Có thể xóa cùng nếu hồ sơ chỉ chứa tùy chọn riêng và không cần giữ lịch sử |

Các đáp án là phương án khởi đầu. Ví dụ, PAYMENT_ATTEMPT có thể có thông tin nhạy cảm cần xử lý theo chính sách riêng; CUSTOMER_PROFILE có thể chứa dữ liệu kiểm toán cần giữ. Cần xác nhận phạm vi dữ liệu cụ thể trước khi quyết định.

**Kết quả cần đạt:** mô hình phải giải thích được tại sao một số thực thể con được xóa cùng chủ, một số thực thể được giữ lại, một số quan hệ chỉ bị ngắt và một số đối tượng chỉ chuyển trạng thái. Mỗi hành vi cần phản ánh vòng đời nghiệp vụ, tránh tạo dữ liệu mồ côi và tránh xóa nhầm giao dịch hoặc lịch sử quan trọng.
