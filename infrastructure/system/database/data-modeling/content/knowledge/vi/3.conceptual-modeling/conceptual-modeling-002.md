# Phân biệt thực thể, thuộc tính, quan hệ và sự kiện

Khi đọc yêu cầu nghiệp vụ, ta thường gặp những câu như “khách hàng đặt đơn hàng”, “đơn hàng gồm nhiều sản phẩm”, “sản phẩm thuộc danh mục”, “khách thanh toán” và “kho giữ hàng cho đơn”. Những câu này chứa nhiều loại khái niệm khác nhau. Nếu gom tất cả thành bảng hoặc cột ngay lập tức, mô hình dễ nhầm lẫn giữa một đối tượng có định danh, một đặc điểm mô tả, một liên kết giữa các đối tượng và một việc đã xảy ra tại một thời điểm.

Trong mô hình dữ liệu khái niệm, bốn khái niệm này có vai trò riêng:

- **Thực thể (entity)** là đối tượng hoặc khái niệm nghiệp vụ cần được nhận diện và theo dõi qua thời gian.
- **Thuộc tính (attribute)** là thông tin mô tả một thực thể hoặc một quan hệ.
- **Quan hệ (relationship)** diễn tả cách các thực thể liên kết với nhau, cùng số lượng và tính bắt buộc của liên kết.
- **Sự kiện (event)** là điều đã xảy ra tại một thời điểm, có thể làm thay đổi trạng thái nghiệp vụ hoặc tạo ra dữ kiện lịch sử.

Bài học dùng ví dụ cửa hàng trực tuyến gồm khách hàng, danh mục, sản phẩm, đơn hàng, thanh toán và tồn kho. Ta sẽ phân loại từng khái niệm, vẽ mô hình khái niệm, rồi kiểm tra mô hình bằng các tình huống cụ thể. Đây là bước nền trong công việc chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, có thể kiểm chứng và tiến hóa.

## 1. Bốn khái niệm trả lời bốn câu hỏi khác nhau

Hãy bắt đầu với một đoạn yêu cầu:

> Khách hàng có hồ sơ và nhiều địa chỉ nhận hàng. Khách hàng có thể đặt nhiều đơn hàng. Mỗi đơn hàng gồm nhiều dòng hàng, mỗi dòng tham chiếu một sản phẩm và ghi số lượng, giá tại thời điểm mua. Một sản phẩm có thể thuộc nhiều danh mục. Khi khách gửi đơn, hệ thống ghi nhận thời điểm đặt hàng. Khi thanh toán thành công, hệ thống ghi nhận giao dịch và thay đổi trạng thái đơn. Kho giữ hàng cho đơn trước khi giao.

Ta có thể đặt bốn câu hỏi để tách các khái niệm:

| Câu hỏi | Khái niệm | Ví dụ trong cửa hàng |
|---|---|---|
| Hệ thống cần nhận diện những ai, cái gì? | Thực thể | Khách hàng, sản phẩm, đơn hàng, kho |
| Ta cần biết điều gì về mỗi đối tượng? | Thuộc tính | SKU, tên sản phẩm, ngày tạo, số lượng |
| Các đối tượng liên kết với nhau ra sao? | Quan hệ | Khách hàng đặt đơn; đơn hàng chứa dòng hàng |
| Việc gì đã xảy ra, khi nào và liên quan đến ai/cái gì? | Sự kiện | Đơn được đặt, thanh toán được xác nhận, hàng được giữ |

Một câu có thể chứa nhiều loại khái niệm. “Khách hàng đặt đơn hàng lúc 10 giờ” có:

- **Customer** và **SalesOrder** là hai thực thể.
- **places** là quan hệ giữa khách hàng và đơn hàng.
- **OrderPlaced** là sự kiện xảy ra lúc 10 giờ.
- **placed_at** có thể là thuộc tính thời gian của đơn hàng hoặc thuộc tính của bản ghi sự kiện, tùy mục đích lưu trữ và kiểm toán.

Không nên quyết định chỉ dựa vào từ loại. Danh từ không tự động là thực thể, động từ không tự động là sự kiện. Hãy xem xét định danh, vòng đời, khả năng tái sử dụng, lịch sử và quy tắc nghiệp vụ của khái niệm đó.

## 2. Thực thể: đối tượng cần được nhận diện

Một thực thể là thứ mà nghiệp vụ cần phân biệt một cá thể với các cá thể khác. Nó có định danh và thường có vòng đời riêng.

### 2.1. Dấu hiệu nhận biết thực thể

Một khái niệm có khả năng là thực thể khi có một hoặc nhiều dấu hiệu sau:

- Người dùng cần tìm, xem, tạo, cập nhật hoặc quản lý từng cá thể.
- Nó có thể được nhiều đối tượng khác tham chiếu.
- Nó có trạng thái hoặc vòng đời riêng.
- Nó cần giữ lịch sử thay đổi.
- Hai cá thể có cùng thuộc tính mô tả nhưng vẫn phải phân biệt được.

Trong cửa hàng, hai khách hàng có thể cùng tên và cùng thành phố nhưng vẫn là hai người khác nhau. Vì vậy, **Customer** cần định danh riêng. Hai sản phẩm có cùng tên hiển thị nhưng SKU khác nhau cũng phải được nhận diện riêng.

Ví dụ các thực thể chính:

| Thực thể | Vì sao cần nhận diện riêng? | Định danh nghiệp vụ có thể có |
|---|---|---|
| Customer | Có hồ sơ, địa chỉ, đơn hàng và lịch sử mua | Mã khách hàng |
| Product | Có SKU, giá, trạng thái bán và danh mục | SKU |
| Category | Có cấu trúc cha-con, tên và trạng thái | Slug hoặc mã danh mục |
| SalesOrder | Có vòng đời từ nháp đến hoàn tất/hủy | Mã đơn hàng |
| OrderItem | Một dòng cụ thể trong một đơn | Số dòng trong đơn |
| Payment | Có số tiền, nhà cung cấp và kết quả giao dịch | Mã giao dịch nhà cung cấp |
| Warehouse | Có vị trí và hoạt động lưu trữ riêng | Mã kho |
| InventoryMovement | Mỗi lần biến động phải truy vết được | Mã biến động |

Một thực thể không nhất thiết phải là vật thể hữu hình. Đơn hàng, thanh toán, hợp đồng, tài khoản và lần đặt lịch đều có thể là thực thể nghiệp vụ.

### 2.2. Định danh khác với thuộc tính mô tả

Giả sử hồ sơ khách hàng có tên, email và số điện thoại. Tên là thông tin mô tả, không đủ để phân biệt hai người. Email có thể là khóa nghiệp vụ nếu cửa hàng bảo đảm mỗi email chỉ thuộc một khách hàng và chính sách không cho phép chia sẻ; tuy nhiên email vẫn có thể thay đổi. Số điện thoại có thể được đổi, tái cấp cho người khác hoặc dùng chung trong gia đình.

Một định danh nên có các đặc tính:

- Phân biệt được các cá thể trong phạm vi đã xác định.
- Ổn định trong suốt vòng đời cần theo dõi.
- Không mang ý nghĩa dễ thay đổi nếu không cần thiết.
- Có quy tắc duy nhất rõ ràng.

Trong mô hình khái niệm, ta chỉ cần xác định thực thể có định danh nào và phạm vi duy nhất ra sao. Việc chọn khóa thay thế, kiểu số hay UUID là quyết định ở bước thiết kế logic/vật lý.

### 2.3. Thực thể độc lập và thực thể phụ thuộc

Một số thực thể có thể tồn tại độc lập. Ví dụ, **Product** có thể được tạo trước khi có đơn hàng nào.

Một số thực thể chỉ có ý nghĩa trong ngữ cảnh của thực thể khác. **OrderItem** là ví dụ: dòng hàng thuộc một đơn hàng cụ thể. Số dòng 1 chỉ có ý nghĩa trong một đơn nhất định; đơn khác cũng có thể có dòng số 1. Ta có thể nhận diện dòng hàng bằng cặp mã đơn và số dòng.

Thực thể phụ thuộc thường có một hoặc nhiều đặc điểm:

- Không có vòng đời nghiệp vụ tách khỏi thực thể cha.
- Định danh phụ thuộc một phần hoặc toàn bộ vào thực thể cha.
- Khi thực thể cha bị hủy, thực thể con có quy tắc xử lý đi kèm.
- Thuộc tính của nó chỉ có ý nghĩa trong ngữ cảnh của cha.

Tuy nhiên, không phải mọi bảng có khóa ngoại đều là thực thể phụ thuộc. Một **Payment** có liên kết với **SalesOrder**, nhưng giao dịch thanh toán có thể cần được giữ lại để đối soát ngay cả khi đơn hàng thay đổi trạng thái. Mức phụ thuộc là quyết định nghiệp vụ, không chỉ là chi tiết kỹ thuật.

### 2.4. Khi nào một nhóm thuộc tính trở thành thực thể?

Xem xét địa chỉ khách hàng:

- Nếu địa chỉ chỉ là vài trường dùng một lần khi giao đơn, nó có thể là một nhóm thuộc tính giá trị gắn với đơn hàng.
- Nếu khách hàng lưu nhiều địa chỉ, đặt tên cho địa chỉ, chọn địa chỉ mặc định, sửa và tái sử dụng chúng, **CustomerAddress** có vòng đời riêng và nên được mô hình hóa thành thực thể.
- Nếu địa chỉ giao hàng cần giữ nguyên như lúc đặt đơn, **DeliveryAddressSnapshot** là một giá trị lịch sử gắn với đơn. Nó không nhất thiết phải tham chiếu địa chỉ hiện tại của khách.

Cùng một khái niệm “địa chỉ” có thể được mô hình hóa khác nhau tùy cách nghiệp vụ sử dụng. Hãy hỏi: nó có định danh riêng không, có được tái sử dụng không, ai quản lý nó, và thay đổi của nó có được phép ảnh hưởng đến dữ liệu lịch sử không?

## 3. Thuộc tính: thông tin mô tả một thực thể hoặc quan hệ

Thuộc tính trả lời câu hỏi “ta cần biết điều gì về đối tượng này?”. Ví dụ **Product** có SKU, tên, mô tả và giá hiện tại; **SalesOrder** có mã đơn, thời điểm đặt và trạng thái.

### 3.1. Thuộc tính định danh và thuộc tính mô tả

- Thuộc tính định danh tham gia nhận diện một cá thể hoặc một nhóm cá thể.
- Thuộc tính mô tả cung cấp thông tin về cá thể nhưng không nhất thiết duy nhất.

Ví dụ:

| Thực thể | Thuộc tính định danh | Thuộc tính mô tả |
|---|---|---|
| Product | SKU | Tên, mô tả, giá hiện tại |
| Category | Slug/mã danh mục | Tên, mô tả, trạng thái |
| Warehouse | Mã kho | Tên kho, địa điểm |
| SalesOrder | Mã đơn hàng | Thời điểm tạo, trạng thái |
| Payment | Mã giao dịch | Số tiền, loại giao dịch, trạng thái |

Một thực thể có thể có nhiều khóa ứng viên. Ví dụ sản phẩm có product_id nội bộ và SKU dùng trong nghiệp vụ. Ở mức khái niệm, hãy ghi nhận cả các quy tắc nhận diện có ý nghĩa, sau đó mới chọn khóa chính ở bước thiết kế logic.

### 3.2. Thuộc tính đơn và thuộc tính phức hợp

Thuộc tính đơn là giá trị được xem như một đơn vị trong ngữ cảnh đang mô hình hóa, ví dụ mã SKU hoặc trạng thái.

Thuộc tính phức hợp có thể chia thành các thành phần có ý nghĩa riêng. Ví dụ địa chỉ giao hàng có người nhận, số điện thoại, dòng địa chỉ, phường/xã, thành phố và quốc gia. Nếu nghiệp vụ cần tìm kiếm hoặc xác thực theo thành phần, mô hình khái niệm nên thể hiện các thành phần đó.

Không phải lúc nào cũng cần tách tên người thành họ, tên đệm và tên gọi. Quy tắc tên khác nhau theo quốc gia và văn hóa; chỉ tách khi có yêu cầu nghiệp vụ cụ thể như sắp xếp, xưng hô hoặc tích hợp hệ thống.

### 3.3. Thuộc tính đơn trị và đa trị

Một thuộc tính đơn trị có tối đa một giá trị trên mỗi cá thể trong phạm vi thời điểm đang xét. Ví dụ, một đơn hàng có một mã đơn hàng.

Một thuộc tính đa trị có thể có nhiều giá trị. Khách hàng có thể có nhiều số điện thoại hoặc email liên hệ. Không nên lưu chúng thành một chuỗi phân cách bằng dấu phẩy nếu hệ thống cần xác minh, gắn nhãn, đặt mức ưu tiên hoặc theo dõi thời gian hiệu lực.

Khi một giá trị đa trị có thông tin riêng, hãy cân nhắc mô hình hóa thành thực thể con:

- **CustomerContact:** loại liên hệ, giá trị, đã xác minh hay chưa.
- **CustomerAddress:** loại địa chỉ, địa chỉ chi tiết, mặc định hay không.
- **ProductCategory:** sản phẩm được gán vào danh mục nào, gán từ khi nào, có phải danh mục chính hay không.

### 3.4. Thuộc tính bắt buộc, tùy chọn và có điều kiện

Một thuộc tính bắt buộc phải có trong mọi cá thể hợp lệ, ví dụ SKU của sản phẩm được phát hành để bán. Thuộc tính tùy chọn có thể chưa biết hoặc không áp dụng, ví dụ địa chỉ dòng 2.

Cần phân biệt ba trạng thái:

- **Không có giá trị vì không áp dụng:** ví dụ địa chỉ không có dòng thứ hai.
- **Chưa biết:** ví dụ ngày sinh khách hàng chưa được cung cấp.
- **Đang chờ xác nhận:** ví dụ email đã nhập nhưng chưa xác minh.

Nếu các trạng thái này có ý nghĩa nghiệp vụ khác nhau, không nên gộp tất cả thành một giá trị rỗng mà không có quy tắc bổ sung.

Một số thuộc tính chỉ bắt buộc khi một điều kiện xảy ra. Ví dụ mã vận đơn chỉ bắt buộc sau khi đơn đã được bàn giao cho đơn vị vận chuyển. Hãy ghi điều kiện đó thành quy tắc nghiệp vụ, vì mô hình ER đơn giản có thể không diễn tả đầy đủ.

### 3.5. Thuộc tính lưu trữ, suy diễn và lịch sử

Một thuộc tính suy diễn có thể tính từ dữ liệu khác:

- Tuổi tính từ ngày sinh và ngày hiện tại.
- Tổng tiền đơn tính từ các dòng hàng, giảm giá, thuế và phí.
- Số lượng có thể bán tính bằng tồn thực tế trừ số lượng giữ chỗ.

Có thể lưu thuộc tính suy diễn để tăng tốc đọc hoặc chụp lại giá trị tại một thời điểm. Nhưng khi lưu, cần xác định nguồn sự thật và quy tắc đồng bộ để tránh lệch dữ liệu.

Thuộc tính lịch sử thay đổi theo thời gian. Giá hiện tại của sản phẩm là một giá trị tại hiện tại; giá đã áp dụng cho một dòng hàng là dữ kiện của giao dịch trong quá khứ. Tên sản phẩm có thể thay đổi nhưng tên đã in trên hóa đơn nên được giữ nguyên.

Có hai cách mô hình hóa lịch sử phổ biến:

1. Lưu ảnh chụp tại sự kiện, ví dụ tên và đơn giá trong **OrderItem**.
2. Lưu các phiên bản có khoảng hiệu lực, ví dụ lịch sử giá hoặc lịch sử phân loại khách hàng.

Cách chọn phụ thuộc vào câu hỏi cần trả lời: “Giá của đơn này là bao nhiêu lúc mua?” khác với “Giá niêm yết của sản phẩm trong từng giai đoạn là bao nhiêu?”.

## 4. Quan hệ: cách các thực thể liên kết

Quan hệ diễn tả một thực thể tham gia với một hoặc nhiều thực thể khác theo quy tắc nghiệp vụ. Tên quan hệ nên là động từ hoặc cụm động từ có nghĩa rõ ràng.

Ví dụ:

- Customer **places** SalesOrder.
- SalesOrder **contains** OrderItem.
- OrderItem **references** Product.
- Product **belongs to** Category.
- Warehouse **stores** Product.
- Payment **settles** SalesOrder.

Một mô hình tốt cần chỉ ra hai chiều đọc của quan hệ. Ví dụ “khách hàng đặt đơn” và “đơn hàng được đặt bởi khách hàng” mô tả cùng một liên kết nhưng giúp kiểm tra quy tắc từ cả hai phía.

### 4.1. Lực lượng và tính bắt buộc

Cardinality cho biết số lượng cá thể ở một phía có thể liên kết với một cá thể phía còn lại. Hai câu hỏi phải được trả lời:

- Tối thiểu bao nhiêu liên kết là hợp lệ?
- Tối đa bao nhiêu liên kết là hợp lệ?

Một số dạng thường gặp:

| Dạng | Ý nghĩa | Ví dụ |
|---|---|---|
| 0..1 | Không có hoặc có tối đa một | Đơn hàng có thể chưa có địa chỉ đã chọn trong trạng thái nháp |
| 1..1 | Bắt buộc đúng một | Mỗi đơn hàng đã xác nhận thuộc một khách hàng |
| 0..* | Có thể không có hoặc có nhiều | Một khách hàng có thể chưa đặt đơn nào |
| 1..* | Phải có ít nhất một, có thể nhiều | Đơn hàng đã xác nhận có ít nhất một dòng hàng |

Không chỉ ghi “một-nhiều”. Hãy viết câu đầy đủ ở cả hai phía:

- Một khách hàng có thể đặt **0 đến nhiều** đơn hàng.
- Mỗi đơn hàng phải thuộc về **đúng một** khách hàng.

Với vòng đời đơn hàng, một đơn nháp có thể chưa có dòng hàng; khi xác nhận, nó phải có ít nhất một dòng. Như vậy, quy tắc 1..* chỉ áp dụng ở trạng thái đã xác nhận. Mô hình cần ghi rõ điều kiện thời điểm này, thay vì áp dụng một cardinality duy nhất cho mọi trạng thái.

### 4.2. Quan hệ một-một, một-nhiều và nhiều-nhiều

**Một-một (1:1)** xảy ra khi mỗi cá thể ở mỗi phía liên kết với tối đa một cá thể phía kia. Ví dụ, nếu mỗi tài khoản đăng nhập chỉ thuộc một hồ sơ khách hàng và mỗi hồ sơ chỉ có một tài khoản đăng nhập, có thể mô hình hóa quan hệ 1:1. Trước khi tách hai khái niệm thành hai thực thể, hãy hỏi liệu chúng có vòng đời, quyền truy cập hoặc nguồn dữ liệu độc lập hay không.

**Một-nhiều (1:N)**: một khách hàng có nhiều đơn hàng, nhưng mỗi đơn hàng thuộc một khách hàng. Đây là dạng phổ biến trong hệ thống giao dịch.

**Nhiều-nhiều (M:N)**: một sản phẩm có thể thuộc nhiều danh mục và một danh mục có nhiều sản phẩm. Quan hệ này thường được triển khai bằng thực thể liên kết ở mô hình logic.

Sơ đồ đơn giản:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
    PRODUCT ||--o{ PRODUCT_CATEGORY : classified_by
    CATEGORY ||--o{ PRODUCT_CATEGORY : includes
~~~

Trong sơ đồ trên, **||** thể hiện đúng một, **o{** thể hiện không hoặc nhiều, còn **|{** thể hiện một hoặc nhiều. Ký hiệu cần được đọc cùng quy tắc nghiệp vụ; sơ đồ không tự diễn tả được điều kiện “một hoặc nhiều sau khi đơn được xác nhận”.

### 4.3. Quan hệ đệ quy

Một thực thể có thể liên kết với chính nó. Danh mục có quan hệ cha-con:

- Một danh mục có thể không có danh mục cha nếu nó là danh mục gốc.
- Một danh mục cha có thể có nhiều danh mục con.
- Mỗi danh mục con có tối đa một cha nếu cây danh mục không cho phép nhiều cha.

Đây là quan hệ đệ quy một-nhiều. Khi mô hình hóa, hãy đặt tên vai trò rõ ràng như **parent category** và **child category**, tránh tên chung chung khiến người đọc không biết phía nào là cha.

Các quan hệ đệ quy phức tạp hơn cũng có thể là nhiều-nhiều. Ví dụ một nhân viên hướng dẫn nhiều nhân viên khác, và một nhân viên có thể có nhiều người hướng dẫn.

### 4.4. Quan hệ có thuộc tính và thực thể liên kết

Một quan hệ đôi khi có dữ liệu riêng. Ví dụ sản phẩm thuộc danh mục từ thời điểm nào, ai gán, hoặc danh mục nào là danh mục chính. Những thông tin đó không mô tả riêng Product hay Category mà mô tả chính lần gán sản phẩm vào danh mục.

Khi đó, hãy mô hình hóa quan hệ thành thực thể liên kết **ProductCategory**:

| Thuộc tính của ProductCategory | Ý nghĩa |
|---|---|
| Product | Sản phẩm được gán |
| Category | Danh mục nhận sản phẩm |
| AssignedAt | Thời điểm gán |
| AssignedBy | Người hoặc hệ thống thực hiện |
| IsPrimary | Có phải danh mục chính không |

Tương tự, **OrderItem** là phần tử của quan hệ “đơn hàng chứa sản phẩm”. Quan hệ này có số lượng, đơn giá, giảm giá và số dòng. Không thể chỉ lưu liên kết Order–Product rồi bỏ mất dữ kiện của lần mua.

Quy tắc thực hành: nếu một quan hệ nhiều-nhiều có thuộc tính riêng, cần được tìm kiếm, có vòng đời hoặc được tham chiếu, hãy xem nó như một thực thể liên kết.

### 4.5. Quan hệ nhị phân và quan hệ bậc cao

Phần lớn mô hình nghiệp vụ dùng quan hệ nhị phân giữa hai thực thể. Tuy nhiên, một số quy tắc liên quan đồng thời đến ba hay nhiều thực thể.

Ví dụ: nhân viên kiểm kê số lượng của một sản phẩm tại một kho vào một thời điểm. Bản ghi kiểm kê có ba vai trò: **Employee**, **Product**, **Warehouse**, cùng thời điểm và số lượng đếm được.

Có thể mô hình hóa thành thực thể **StockCount** liên kết với nhân viên, sản phẩm và kho. Cách này thường dễ diễn giải hơn khi nghiệp vụ còn cần trạng thái kiểm kê, lý do chênh lệch hoặc người phê duyệt.

Đừng tách một quan hệ bậc cao thành nhiều quan hệ nhị phân nếu việc đó làm mất ý nghĩa của sự kết hợp ban đầu.

## 5. Sự kiện: điều đã xảy ra tại một thời điểm

Sự kiện là một sự thật về nghiệp vụ đã xảy ra. Nó thường có thời điểm, tác nhân, đối tượng liên quan và dữ liệu mô tả kết quả.

Ví dụ trong cửa hàng:

- **CustomerRegistered:** khách hàng đăng ký.
- **OrderPlaced:** đơn hàng được gửi.
- **PaymentAuthorized:** khoản thanh toán được cấp phép.
- **PaymentCaptured:** tiền được thu thành công.
- **StockReserved:** số lượng được giữ cho đơn.
- **ShipmentDispatched:** kiện hàng được bàn giao vận chuyển.
- **StockAdjusted:** số lượng kho được điều chỉnh sau kiểm kê.

Một sự kiện thường có các thành phần:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Định danh sự kiện | Sự kiện cụ thể nào? | event_id |
| Loại sự kiện | Việc gì đã xảy ra? | PaymentCaptured |
| Thời điểm | Xảy ra khi nào? | occurred_at |
| Tác nhân | Ai hoặc hệ thống nào thực hiện? | customer, employee, payment provider |
| Đối tượng liên quan | Sự kiện tác động đến ai/cái gì? | order_id, payment_id |
| Dữ liệu sự kiện | Giá trị nào được ghi nhận? | amount, currency, quantity |
| Nguồn và tương quan | Đến từ đâu, thuộc luồng xử lý nào? | source, correlation_id |
| Chống lặp | Có thể nhận lại cùng một sự kiện không? | provider_event_id hoặc idempotency_key |

### 5.1. Quan hệ lâu dài khác với sự kiện tại thời điểm

“Khách hàng đặt đơn hàng” có thể được nhìn ở hai góc:

- Quan hệ **Customer places SalesOrder** cho biết đơn hàng thuộc về khách hàng nào. Liên kết này vẫn có ý nghĩa khi đơn đã giao hoặc đã hủy.
- Sự kiện **OrderPlaced** ghi nhận hành động gửi đơn đã xảy ra lúc nào và theo dữ liệu nào.

Quan hệ diễn tả cấu trúc liên kết; sự kiện diễn tả một lần xảy ra. Chúng bổ sung cho nhau.

Ví dụ khác:

- **Payment** là thực thể đại diện cho một giao dịch thanh toán có định danh và vòng đời.
- **PaymentCaptured** là sự kiện xác nhận tiền đã được thu.
- **SalesOrder.status** là trạng thái hiện tại của đơn.
- **OrderStatusChanged** là sự kiện hoặc bản ghi lịch sử cho biết trạng thái đã chuyển từ gì sang gì, khi nào và do ai.

Nếu chỉ lưu trạng thái hiện tại, ta có thể biết đơn đang **PAID**, nhưng không trả lời được ai xác nhận, xác nhận lúc nào, trước đó đơn ở trạng thái nào và có bao nhiêu lần thử thanh toán thất bại.

### 5.2. Sự kiện không phải là lệnh

Một lệnh (command) yêu cầu hệ thống làm điều gì đó; sự kiện ghi nhận điều đã xảy ra.

| Lệnh | Sự kiện sau khi xử lý thành công |
|---|---|
| PlaceOrder | OrderPlaced |
| CapturePayment | PaymentCaptured |
| ReserveStock | StockReserved |
| CancelOrder | OrderCancelled |
| DispatchShipment | ShipmentDispatched |

Lệnh có thể bị từ chối vì không đủ hàng, đơn không hợp lệ hoặc thanh toán không được chấp nhận. Không được phát ra sự kiện thành công trước khi điều kiện nghiệp vụ đã được xác nhận.

Phân biệt này giúp API, log và hệ thống thông điệp rõ nghĩa. **ReserveStockRequested** có thể là một yêu cầu; **StockReserved** phải phản ánh kết quả giữ hàng đã thành công.

### 5.3. Trạng thái là ảnh chụp, sự kiện là lịch sử

Một đơn hàng có thể chuyển qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_PAYMENT: OrderPlaced
    PENDING_PAYMENT --> PAID: PaymentCaptured
    PENDING_PAYMENT --> CANCELLED: OrderCancelled
    PAID --> PROCESSING: FulfillmentStarted
    PROCESSING --> SHIPPED: ShipmentDispatched
    SHIPPED --> COMPLETED: DeliveryConfirmed
    PAID --> REFUNDED: RefundCompleted
~~~

Cột **status** trên đơn hàng cho biết trạng thái hiện tại để ứng dụng đọc nhanh. Lịch sử sự kiện hoặc bảng lịch sử trạng thái cho biết đường đi đã xảy ra.

Cần xác định chuyển trạng thái hợp lệ. Ví dụ, không được chuyển trực tiếp từ **DRAFT** sang **SHIPPED** nếu chưa có bước xác nhận và xử lý đơn. Quy tắc này nên được thể hiện trong quy trình nghiệp vụ và kiểm tra ở tầng thực thi phù hợp.

### 5.4. Tồn kho: số dư là trạng thái, biến động là sự kiện

Số lượng hiện tại trong kho là một trạng thái. Mỗi lần nhập hàng, giữ chỗ, nhả giữ chỗ, xuất giao hoặc điều chỉnh là một sự kiện/biến động.

Ví dụ, sản phẩm A trong kho H có:

- Số lượng thực tế: 20.
- Số lượng đang giữ chỗ: 3.
- Số lượng có thể bán: 17.

Khi một đơn giữ thêm 2 sản phẩm:

- Một sự kiện **StockReserved** ghi nhận sản phẩm A, kho H, đơn hàng, số lượng 2 và thời điểm.
- Số lượng thực tế vẫn là 20.
- Số lượng giữ chỗ tăng từ 3 lên 5.
- Số lượng có thể bán giảm từ 17 xuống 15.

Khi đơn được giao, số lượng thực tế và số lượng giữ chỗ cùng giảm 2. Khi đơn bị hủy trước khi giao, số lượng giữ chỗ giảm 2 còn số lượng thực tế không đổi.

Nếu chỉ cập nhật số dư mà không ghi biến động, hệ thống khó truy nguyên nguyên nhân chênh lệch. Nếu chỉ ghi biến động mà không có cách đọc số dư hiệu quả, việc tính lại có thể tốn kém. Nhiều hệ thống lưu cả trạng thái hiện tại và sổ biến động, với quy tắc cập nhật nhất quán trong cùng giao dịch.

### 5.5. Sự kiện có thể được lưu thế nào?

Không phải mọi hệ thống đều cần một nền tảng event streaming hoặc event sourcing. Có một số mức độ:

1. **Thuộc tính thời gian trên thực thể:** created_at, placed_at, paid_at. Đơn giản, phù hợp khi chỉ cần mốc thời gian chính.
2. **Bảng lịch sử:** OrderStatusHistory, PaymentEvent, InventoryMovement. Phù hợp khi cần truy vết từng lần thay đổi.
3. **Event log hoặc message stream:** ghi sự kiện để nhiều dịch vụ hoặc hệ thống phân tích tiêu thụ. Cần định danh, thứ tự, retry, chống trùng và xử lý dữ liệu đến trễ.
4. **Event sourcing:** sự kiện là nguồn dữ liệu chính; trạng thái hiện tại được dựng lại bằng cách áp dụng các sự kiện. Cách này mạnh về lịch sử nhưng đòi hỏi thiết kế versioning, replay, snapshot và xử lý sửa sai cẩn thận.

Lưu sự kiện không đồng nghĩa với event sourcing. Một hệ thống quan hệ bình thường vẫn có thể có bảng lịch sử và transactional outbox mà không biến mọi thao tác thành event-sourced.

## 6. Mô hình khái niệm cho cửa hàng trực tuyến

Ta có thể kết hợp bốn loại khái niệm trong một mô hình. Phần thực thể và quan hệ mô tả cấu trúc nghiệp vụ; các thực thể sự kiện ghi nhận những lần xảy ra quan trọng.

~~~mermaid
erDiagram
    CUSTOMER ||--o{ CUSTOMER_ADDRESS : owns
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--o{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
    PRODUCT ||--o{ PRODUCT_CATEGORY : classified_by
    CATEGORY ||--o{ PRODUCT_CATEGORY : includes
    CATEGORY o|--o{ CATEGORY : parent_of
    SALES_ORDER ||--o{ PAYMENT : has
    SALES_ORDER ||--o{ ORDER_EVENT : records
    PAYMENT ||--o{ PAYMENT_EVENT : records
    PRODUCT ||--o{ INVENTORY : stocked_as
    WAREHOUSE ||--o{ INVENTORY : stores
    PRODUCT ||--o{ INVENTORY_MOVEMENT : affected_by
    WAREHOUSE ||--o{ INVENTORY_MOVEMENT : records
    SALES_ORDER o|--o{ INVENTORY_MOVEMENT : may_cause
~~~

### 6.1. Phân loại từng thành phần

| Thành phần | Loại | Thuộc tính hoặc vai trò nổi bật |
|---|---|---|
| Customer | Thực thể | Mã khách, tên, email, thời điểm tạo |
| CustomerAddress | Thực thể phụ thuộc theo nghiệp vụ | Người nhận, số điện thoại, địa chỉ, loại địa chỉ |
| Product | Thực thể | SKU, tên, giá hiện tại, trạng thái |
| Category | Thực thể | Mã, tên, danh mục cha |
| ProductCategory | Thực thể liên kết | Sản phẩm, danh mục, thời điểm gán, danh mục chính |
| SalesOrder | Thực thể | Mã đơn, khách hàng, trạng thái, tổng tiền |
| OrderItem | Thực thể phụ thuộc/chi tiết | Sản phẩm, số lượng, giá chụp tại thời điểm mua |
| Payment | Thực thể giao dịch | Mã giao dịch, số tiền, nhà cung cấp, trạng thái |
| Warehouse | Thực thể | Mã kho, tên, địa điểm |
| Inventory | Trạng thái tồn theo sản phẩm và kho | Số lượng thực tế, giữ chỗ |
| OrderEvent | Sự kiện hoặc bản ghi lịch sử | Loại sự kiện, thời điểm, tác nhân, dữ liệu |
| PaymentEvent | Sự kiện thanh toán | Mã sự kiện nhà cung cấp, loại, thời điểm |
| InventoryMovement | Sự kiện/biến động kho | Sản phẩm, kho, loại biến động, số lượng thay đổi |

Sự kiện có thể được mô hình hóa thành thực thể nếu cần định danh và truy vấn từng lần xảy ra. Tên **OrderEvent** trong sơ đồ là một khái niệm tổng quát; trong hệ thống cụ thể có thể dùng bảng riêng cho từng loại hoặc một bảng sự kiện có trường phân loại. Quyết định đó thuộc thiết kế logic.

### 6.2. Phân biệt thuộc tính với thực thể trong ví dụ

| Câu hỏi nghiệp vụ | Cách mô hình hóa hợp lý | Vì sao |
|---|---|---|
| Sản phẩm có giá hiện tại? | Thuộc tính current_price của Product | Giá hiện tại mô tả sản phẩm |
| Đơn hàng có giá mua tại thời điểm đặt? | Thuộc tính unit_price_snapshot của OrderItem | Đây là dữ kiện của dòng hàng trong giao dịch |
| Khách hàng có nhiều địa chỉ lưu sẵn? | Thực thể CustomerAddress | Mỗi địa chỉ có thể được quản lý và tái sử dụng |
| Đơn hàng cần giữ địa chỉ giao lúc đặt? | Nhóm thuộc tính snapshot trên SalesOrder | Lịch sử đơn không phụ thuộc hồ sơ địa chỉ hiện tại |
| Sản phẩm được gán vào danh mục nào? | Quan hệ Product–Category | Đây là liên kết giữa hai thực thể |
| Lần gán có thời điểm và người thực hiện? | Thực thể liên kết ProductCategory | Liên kết có dữ liệu riêng |
| Đơn hàng đang ở trạng thái nào? | Thuộc tính trạng thái hiện tại | Phản ánh ảnh chụp hiện tại |
| Đơn hàng đã chuyển trạng thái ra sao? | Sự kiện/bảng OrderStatusHistory | Ghi lại từng lần thay đổi |
| Kho đang còn bao nhiêu hàng? | Trạng thái Inventory | Số dư hiện tại theo sản phẩm và kho |
| Vì sao số lượng thay đổi? | InventoryMovement | Ghi nhận từng lần nhập, giữ, nhả, xuất hoặc điều chỉnh |

### 6.3. Một dòng yêu cầu có thể tạo ra nhiều thành phần

Xét yêu cầu: “Khi khách đặt hai chiếc sản phẩm A, hệ thống phải giữ hai chiếc tại kho được chọn và ghi lại thời điểm giữ hàng.”

Ta tách thành:

1. **Thực thể:** Customer, SalesOrder, Product, Warehouse.
2. **Quan hệ:** Customer places SalesOrder; SalesOrder contains OrderItem; OrderItem references Product.
3. **Thuộc tính:** OrderItem.quantity = 2; OrderItem.unit_price_snapshot; thời điểm đặt đơn.
4. **Sự kiện:** StockReserved với số lượng 2, sản phẩm A, kho được chọn, đơn hàng và thời điểm.
5. **Trạng thái:** Inventory.reserved_quantity tăng 2; số lượng khả dụng giảm 2.

Nếu chỉ tạo một cột reserved = true trên sản phẩm, ta mất số lượng, kho, đơn hàng gây giữ chỗ và lịch sử giữ/nhả. Mô hình khái niệm tốt giúp phát hiện những thông tin còn thiếu trước khi thiết kế bảng.

## 7. Cách chuyển một đoạn nghiệp vụ thành mô hình

Có thể áp dụng một quy trình lặp lại cho mỗi nhóm yêu cầu.

### Bước 1: Tìm đối tượng có định danh

Đọc câu và đánh dấu những khái niệm cần quản lý qua thời gian. Hãy hỏi:

- Có nhiều cá thể cùng loại không?
- Người dùng cần mở từng cá thể không?
- Có cần tham chiếu nó từ nơi khác không?
- Nó có trạng thái hoặc lịch sử riêng không?

Nếu câu trả lời là có, xem xét thực thể.

### Bước 2: Tách thông tin mô tả

Với mỗi thực thể, liệt kê các dữ kiện cần lưu. Gắn nhãn:

- Định danh hay mô tả.
- Bắt buộc hay tùy chọn.
- Đơn trị hay đa trị.
- Có thể suy diễn hay cần lưu.
- Thay đổi theo thời gian hay là ảnh chụp lịch sử.

Đừng vội chọn kiểu dữ liệu hay tên cột SQL. Trước hết cần hiểu dữ kiện có nghĩa gì trong nghiệp vụ.

### Bước 3: Tìm động từ và xác định quan hệ

Động từ thường gợi ý quan hệ: đặt, chứa, thuộc, sở hữu, thanh toán, lưu kho. Hãy viết tên quan hệ theo hướng đọc tự nhiên và kiểm tra cả hai phía.

Đừng mặc định mỗi động từ là một bảng. “Khách hàng đặt đơn” thường là quan hệ; “đơn hàng được đặt lúc nào” có thể là thuộc tính thời gian hoặc sự kiện OrderPlaced.

### Bước 4: Ghi min/max cho từng phía

Không dừng ở “một-nhiều”. Hãy viết:

- Mỗi khách hàng có thể đặt 0..* đơn.
- Mỗi đơn phải thuộc đúng 1 khách.
- Mỗi đơn nháp có thể có 0..* dòng.
- Mỗi đơn đã xác nhận phải có 1..* dòng.
- Mỗi dòng hàng tham chiếu đúng 1 sản phẩm.

Nếu cardinality thay đổi theo trạng thái hoặc thời điểm, ghi điều kiện đó thành business rule.

### Bước 5: Tìm dữ liệu riêng của quan hệ

Nếu liên kết có số lượng, giá, vai trò, thời điểm bắt đầu/kết thúc hoặc người thực hiện, hãy cân nhắc thực thể liên kết. OrderItem và ProductCategory là hai ví dụ điển hình.

### Bước 6: Tìm những điều đã xảy ra

Các cụm từ như “đã đặt”, “đã thu tiền”, “đã giao”, “đã điều chỉnh” thường gợi ý sự kiện. Với mỗi sự kiện, hỏi:

- Điều gì được xác nhận là đã xảy ra?
- Xảy ra khi nào?
- Ai hoặc hệ thống nào thực hiện?
- Đối tượng nào bị tác động?
- Có thể nhận sự kiện trùng hoặc đến trễ không?
- Có cần lưu dữ liệu trước/sau hay lý do không?

### Bước 7: Viết quy tắc chưa thể hiện trong sơ đồ

Một sơ đồ ER không thể diễn tả mọi quy tắc. Ghi riêng những điều kiện như:

- SKU phải duy nhất.
- Số lượng đặt phải lớn hơn 0.
- Đơn đã xác nhận phải có ít nhất một dòng hàng.
- Số lượng giữ chỗ không được vượt số lượng thực tế.
- Thanh toán chỉ được tính thành công khi có xác nhận hợp lệ.
- Một sự kiện webhook không được áp dụng hai lần.

Các quy tắc này sẽ trở thành ràng buộc, transaction, kiểm tra ứng dụng hoặc quy trình đối soát ở các bước sau.

## 8. Những nhầm lẫn thường gặp và cách sửa

| Nhầm lẫn | Hậu quả | Cách suy nghĩ lại |
|---|---|---|
| Coi mọi danh từ là thực thể | Quá nhiều bảng, mô hình khó hiểu | Kiểm tra định danh và vòng đời |
| Coi thuộc tính đa trị là một chuỗi | Khó xác minh, tìm kiếm và gắn metadata | Tách thành thực thể/quan hệ con nếu cần |
| Coi quan hệ nhiều-nhiều như một cột ID đơn | Mất khả năng biểu diễn nhiều liên kết | Mô hình hóa M:N và thực thể liên kết |
| Coi quan hệ là sự kiện | Mất phân biệt giữa liên kết hiện tại và lần xảy ra | Tách relationship khỏi event history |
| Chỉ lưu trạng thái hiện tại | Không truy vết được lịch sử | Bổ sung sự kiện hoặc bảng lịch sử khi cần |
| Lưu sự kiện nhưng không xác định đối tượng liên quan | Khó truy nguyên và đối soát | Gắn sự kiện với thực thể và nguồn |
| Lưu mọi dữ kiện thành event | Khó vận hành, nhiều dữ liệu không có giá trị lịch sử | Chỉ ghi sự kiện có ý nghĩa nghiệp vụ |
| Dùng tên hoặc email làm định danh mà không có quy tắc ổn định | Trùng hoặc thay đổi làm hỏng tham chiếu | Xác định định danh và phạm vi duy nhất |
| Nhầm thực thể liên kết với thực thể độc lập | Không rõ vòng đời và quyền sở hữu | Xác định liên kết có thể tồn tại độc lập không |
| Vẽ cardinality mà không ghi điều kiện | Quy tắc thay đổi theo trạng thái bị bỏ sót | Ghi min/max và điều kiện áp dụng |

### Ví dụ sai: lưu sản phẩm trong đơn hàng bằng danh sách văn bản

Một đơn hàng có cột items = "A:2:500000,B:1:100000". Cách này không cho biết rõ ràng mỗi dòng có định danh nào, có thể kiểm tra sản phẩm còn hoạt động hay không, hoặc cập nhật tồn kho cho từng sản phẩm ra sao. Hơn nữa, giá trị chứa nhiều loại dữ liệu bị trộn trong một chuỗi.

Cách mô hình hóa rõ ràng hơn:

- SalesOrder là thực thể.
- OrderItem là thực thể chi tiết phụ thuộc.
- SalesOrder contains OrderItem là quan hệ 1:N.
- OrderItem references Product là quan hệ N:1.
- quantity và unit_price_snapshot là thuộc tính của OrderItem.

### Ví dụ sai: lưu status = PAID rồi xóa các lần thanh toán trước

Cách này không trả lời được lần thử nào thất bại, giao dịch nào thành công, có hoàn tiền chưa hoặc webhook nào được xử lý. Cách tốt hơn là giữ Payment như một thực thể giao dịch, lưu trạng thái hiện tại và ghi PaymentEvent khi cần kiểm toán.

## 9. Kiểm chứng mô hình bằng tình huống

Sau khi vẽ mô hình, hãy thử dùng câu hỏi nghiệp vụ để xem có thể trả lời được không.

| Tình huống | Mô hình phải cho biết |
|---|---|
| Một khách có ba địa chỉ | Mỗi địa chỉ thuộc khách nào, địa chỉ mặc định là địa chỉ nào |
| Một sản phẩm thuộc nhiều danh mục | Danh mục nào liên kết với sản phẩm và liên kết có metadata gì |
| Một đơn có hai dòng cùng sản phẩm | Hai dòng được phân biệt bằng gì và có thể có giá/khuyến mại khác nhau không |
| Khách sửa địa chỉ sau khi đặt | Đơn cũ vẫn giữ địa chỉ giao hàng tại thời điểm đặt |
| Khách thử thanh toán hai lần | Mỗi lần thử và kết quả được nhận diện riêng |
| Nhà cung cấp gửi webhook hai lần | Sự kiện trùng không làm tăng số tiền đã thu hai lần |
| Hai đơn cùng giữ sản phẩm cuối | Hệ thống có thể xác định và ghi nhận chỉ một thao tác giữ thành công |
| Nhân viên điều chỉnh tồn kho | Ai điều chỉnh, tại kho nào, sản phẩm nào, số lượng thay đổi và lý do |
| Đơn bị hủy sau khi giữ hàng | Có sự kiện nhả giữ chỗ và số dư khả dụng được khôi phục |
| Sản phẩm đổi tên sau khi mua | Dòng hàng cũ vẫn hiển thị tên đã chụp tại thời điểm mua |

Hãy thử cả trường hợp bình thường, trường hợp biên và trường hợp thất bại. Mô hình chỉ hỗ trợ luồng thành công thường chưa đủ cho hệ thống thực tế.

### Bộ câu hỏi rà soát

- Mỗi thực thể có định danh và lý do tồn tại rõ ràng không?
- Thuộc tính đang mô tả đúng thực thể hay thực chất mô tả một quan hệ?
- Thuộc tính đa trị có cần được tách ra để quản lý không?
- Quan hệ đã có min/max và tính bắt buộc ở cả hai phía chưa?
- Quan hệ nhiều-nhiều có dữ liệu riêng cần thực thể liên kết không?
- Sự kiện có thời điểm, tác nhân, đối tượng và dữ liệu cần thiết chưa?
- Trạng thái hiện tại có được phân biệt với lịch sử trạng thái không?
- Các quy tắc phụ thuộc trạng thái hoặc nhiều thực thể đã được ghi riêng chưa?
- Mô hình có trả lời được các câu hỏi kiểm toán và đối soát không?

## 10. Từ mô hình khái niệm đến các mô hình lưu trữ

Mô hình khái niệm mô tả ngôn ngữ nghiệp vụ và các quy tắc cốt lõi. Nó chưa bị ràng buộc bởi cách một hệ quản trị cụ thể lưu dữ liệu.

Khi chuyển sang mô hình quan hệ, ta ánh xạ thực thể thành bảng, thuộc tính thành cột, quan hệ thành khóa ngoại hoặc bảng liên kết, sự kiện thành bảng lịch sử hay bảng sự kiện. Các quy tắc cardinality và tính duy nhất được triển khai bằng khóa và ràng buộc.

Khi chuyển sang document database, một số thực thể và thuộc tính có thể được nhúng vào cùng một document nếu chúng thường được đọc/ghi cùng nhau và có vòng đời phù hợp. Ví dụ Order có thể nhúng OrderItem và DeliveryAddressSnapshot; Payment và InventoryMovement thường có vòng đời độc lập nên có thể ở collection riêng.

Trong graph database, thực thể trở thành node, quan hệ thành edge; thuộc tính mô tả node hoặc edge. Mô hình này hữu ích khi câu hỏi nghiệp vụ cần duyệt nhiều bước liên kết, chẳng hạn sản phẩm thường được mua cùng nhau hoặc mạng quan hệ giữa khách hàng và địa chỉ.

Trong mô hình phân tích, sự kiện giao dịch thường được chuyển thành fact với grain rõ ràng, còn thực thể mô tả trở thành dimension. Ví dụ mỗi dòng hàng là một fact sales; Product, Customer, Category và Date là các dimension. Sự kiện thanh toán và biến động tồn kho có grain riêng nên không nên gộp tùy tiện vào cùng một fact.

| Thành phần khái niệm | Quan hệ | Document | Graph | Phân tích |
|---|---|---|---|---|
| Thực thể | Bảng | Document hoặc collection | Node | Dimension hoặc đối tượng trong fact |
| Thuộc tính | Cột | Field | Node/edge property | Dimension attribute hoặc measure |
| Quan hệ | Foreign key/bảng liên kết | Tham chiếu hoặc nhúng | Edge | Foreign key trong dimension/fact |
| Sự kiện | Bảng sự kiện/lịch sử | Document sự kiện | Node/edge có thời điểm | Fact event có grain xác định |

Không cần chọn một mô hình lưu trữ chỉ vì sơ đồ khái niệm có nhiều quan hệ hoặc nhiều sự kiện. Hãy chọn dựa trên workload, yêu cầu nhất quán, cách truy vấn, quy mô, lịch sử và khả năng vận hành. Cùng một mô hình khái niệm có thể được triển khai thành nhiều mô hình vật lý khác nhau.

## 11. Quy trình thực hành ngắn

Khi nhận một yêu cầu nghiệp vụ mới, hãy tạo một bảng phân loại ban đầu:

| Cụm từ trong yêu cầu | Phân loại sơ bộ | Câu hỏi xác minh |
|---|---|---|
| Khách hàng | Thực thể | Có hồ sơ và định danh riêng không? |
| Email khách hàng | Thuộc tính hoặc thực thể liên hệ | Có nhiều email, xác minh và lịch sử không? |
| Đặt đơn | Quan hệ và có thể có sự kiện | Cần lưu liên kết hay cả thời điểm gửi đơn? |
| Dòng hàng | Thực thể liên kết/chi tiết | Có số lượng, giá và khuyến mại riêng không? |
| Thuộc danh mục | Quan hệ | Một sản phẩm có nhiều danh mục không? |
| Thanh toán thành công | Sự kiện liên quan thực thể Payment | Cần lưu mã tham chiếu, số tiền, thời điểm nào? |
| Tồn kho | Trạng thái | Được quản lý theo sản phẩm, kho hay lô hàng? |
| Điều chỉnh tồn kho | Sự kiện | Ai điều chỉnh, vì sao và thay đổi bao nhiêu? |

Sau đó:

1. Chốt thuật ngữ với người phụ trách nghiệp vụ. Một từ như “khách hàng”, “tài khoản” hay “người mua” có thể đang chỉ các khái niệm khác nhau.
2. Xác định thực thể và định danh.
3. Phân loại thuộc tính theo ý nghĩa, tính bắt buộc, số lượng giá trị và lịch sử.
4. Vẽ quan hệ, ghi tên vai trò và min/max ở hai phía.
5. Tách quan hệ có dữ liệu riêng thành thực thể liên kết.
6. Xác định sự kiện quan trọng, thời điểm, tác nhân và đối tượng bị tác động.
7. Ghi các quy tắc không thể hiện đầy đủ trong sơ đồ.
8. Dùng các tình huống thực tế để kiểm tra mô hình trước khi chuyển sang lược đồ logic.

Phân biệt đúng thực thể, thuộc tính, quan hệ và sự kiện giúp mô hình dữ liệu diễn tả đúng nghiệp vụ. Thực thể cho ta biết cần quản lý những đối tượng nào; thuộc tính cho biết điều gì mô tả chúng; quan hệ cho biết chúng gắn với nhau ra sao; sự kiện cho biết điều gì đã xảy ra theo thời gian. Khi bốn phần này rõ ràng, việc chọn khóa, chuẩn hóa, ràng buộc, chỉ mục và mô hình lưu trữ ở các bước tiếp theo sẽ có cơ sở vững chắc hơn.
