# Phân biệt dữ liệu thực tế, khái niệm nghiệp vụ và cách biểu diễn trong hệ thống

## Mục tiêu bài học

Sau bài này, bạn có thể phân biệt một sự vật hoặc sự kiện trong thế giới thực với khái niệm nghiệp vụ dùng để hiểu nó và bản ghi mà phần mềm lưu trữ. Bạn sẽ biết vì sao ba lớp này có thể không tương ứng một-một, cách chuyển từ sự kiện thực tế thành dữ liệu có ngữ nghĩa rõ ràng, và cách kiểm tra xem biểu diễn trong hệ thống có giữ đúng ý nghĩa cần thiết hay không.

## 1. Ba lớp cần phân biệt

Khi thiết kế dữ liệu, một lỗi phổ biến là xem những gì đang có trong bảng hoặc JSON như thể đó chính là sự vật ngoài đời. Trên thực tế, giữa thế giới thực và bản ghi trong phần mềm có nhiều bước diễn giải.

Có thể phân biệt ba lớp:

1. **Thực tế (reality):** sự vật, con người, tổ chức, hành động, sự kiện, trạng thái và hiện tượng tồn tại trong miền đang quan sát.
2. **Khái niệm nghiệp vụ (business concept):** cách tổ chức diễn giải và đặt tên cho một phần thực tế theo mục tiêu, quy tắc và ngôn ngữ của tổ chức.
3. **Biểu diễn trong hệ thống (system representation):** dữ liệu cụ thể được lưu, truyền hoặc xử lý trong ứng dụng, cơ sở dữ liệu, API, tệp hay báo cáo.

Ba lớp liên hệ chặt chẽ nhưng không đồng nhất. Một người ngoài đời có thể xuất hiện dưới nhiều vai trò nghiệp vụ; một khái niệm nghiệp vụ có thể được biểu diễn bằng nhiều bảng hoặc document; một bản ghi có thể tổng hợp thông tin từ nhiều nguồn và nhiều thời điểm.

### Ví dụ: một đơn hàng trực tuyến

Hãy xét một người đặt mua hai bàn phím tại một cửa hàng trực tuyến.

| Lớp | Điều đang được nói đến | Ví dụ |
|---|---|---|
| Thực tế | Những gì đã xảy ra | Người mua chọn hàng, xác nhận đặt mua, hệ thống thanh toán nhận yêu cầu và nhà vận chuyển giao kiện hàng |
| Khái niệm nghiệp vụ | Cách cửa hàng hiểu và quản lý sự việc | Khách hàng, đơn hàng, dòng hàng, lần thanh toán, lô giao hàng |
| Biểu diễn hệ thống | Cấu trúc dữ liệu dùng để ghi nhận | Bản ghi `customer`, `orders`, `order_items`, `payments`, sự kiện `OrderPlaced` và payload gửi hãng vận chuyển |

Bản ghi `orders` không phải chính đơn hàng theo nghĩa toàn bộ sự việc ngoài đời. Nó là biểu diễn được thiết kế để hệ thống quản lý đơn hàng. Nó có thể không chứa thông tin giao hàng, hoặc chỉ chứa trạng thái mới nhất, trong khi lịch sử giao hàng được lưu ở một dịch vụ khác.

Nếu coi bản ghi là thực tế, nhóm phát triển dễ đưa ra các giả định sai: xóa bản ghi là xóa sự kiện đã xảy ra; thay đổi trạng thái hiện tại làm thay đổi lịch sử; mã khách hàng là danh tính con người; hoặc một bản ghi tương ứng với đúng một đối tượng ngoài đời.

## 2. Thực tế: sự vật, sự kiện và trạng thái

**Thực tế** là phạm vi hiện tượng mà tổ chức muốn quan sát hoặc quản lý. Trong một miền bán hàng, thực tế có thể gồm con người mua hàng, sản phẩm được giao dịch, một lần thanh toán, kiện hàng được vận chuyển và việc khách nhận hàng.

Không phải mọi thứ trong thực tế đều được hệ thống ghi nhận. Hệ thống chỉ thu thập một phần thông tin phù hợp với mục tiêu và quyền hạn của nó. Vì vậy, dữ liệu luôn có phạm vi quan sát và ngữ cảnh.

### 2.1. Sự vật và vai trò

Một người ngoài đời có thể là người mua, người nhận hàng, người liên hệ hoặc người thanh toán. Các vai trò này có thể thuộc cùng một người hoặc nhiều người khác nhau.

Ví dụ, nhân viên mua hàng của một công ty có thể đặt hàng cho công ty, nhưng hàng được giao cho một chi nhánh và hóa đơn được gửi đến bộ phận kế toán. Nếu mô hình chỉ có một trường `customer_name` và một địa chỉ, hệ thống khó thể hiện đúng các vai trò này.

Khi phân tích, hãy phân biệt:

- **Đối tượng ngoài đời:** con người hoặc tổ chức thực tế.
- **Vai trò trong một quy trình:** người mua, người nhận, người phê duyệt, người thanh toán.
- **Tài khoản hoặc hồ sơ hệ thống:** cách ứng dụng nhận diện một chủ thể để đăng nhập hoặc quản lý dữ liệu.

Một tài khoản không nhất thiết là một con người. Một người có thể có nhiều tài khoản; một tài khoản tổ chức có thể được nhiều nhân viên sử dụng theo quyền hạn. Cần xác định ranh giới nghiệp vụ trước khi chọn cách lưu.

### 2.2. Sự kiện và trạng thái

**Sự kiện (event)** là điều đã xảy ra tại một thời điểm hoặc trong một khoảng thời gian, chẳng hạn đơn hàng được tạo, thanh toán bị từ chối hoặc kiện hàng được giao.

**Trạng thái (state)** mô tả tình trạng của một đối tượng tại một thời điểm, chẳng hạn đơn hàng đang chờ thanh toán hoặc đã hoàn tất.

Sự kiện và trạng thái có quan hệ nhưng không thể thay thế nhau. Một trạng thái hiện tại có thể được suy ra từ nhiều sự kiện trước đó. Nếu chỉ lưu trạng thái hiện tại, hệ thống có thể không trả lời được vì sao đơn hàng ở trạng thái đó hoặc đã đi qua những bước nào.

Ví dụ:

```text
OrderCreated
    |
    v
PaymentRequested
    |
    +----> PaymentFailed
    |          |
    |          v
    |     PaymentRetried
    |          |
    |          v
    +------> PaymentSucceeded
                   |
                   v
              OrderConfirmed
```

Đây là chuỗi sự kiện minh họa. Trạng thái hiện tại có thể là `CONFIRMED`, nhưng lịch sử vẫn cần giữ lần thanh toán thất bại và lần thành công. Việc có lưu toàn bộ sự kiện hay không phụ thuộc yêu cầu kiểm toán, truy vết và khôi phục; dù chọn cách nào, cần biết dữ liệu nào là lịch sử và dữ liệu nào chỉ là trạng thái hiện thời.

### 2.3. Quan sát, phép đo và sự thật có điều kiện

Một hệ thống thường không biết trực tiếp toàn bộ thực tế. Nó nhận dữ liệu qua biểu mẫu, cảm biến, dịch vụ bên ngoài hoặc con người nhập liệu. Dữ liệu đó là **quan sát (observation)** hoặc **phép đo (measurement)**.

Ví dụ, cảm biến ghi nhiệt độ 28,4°C lúc 10:00. Giá trị này có ý nghĩa khi đi kèm thiết bị đo, vị trí, đơn vị, thời điểm và độ chính xác. Nếu chỉ lưu số `28.4`, người đọc không thể biết đó là nhiệt độ, độ ẩm hay một chỉ số khác.

Một quan sát cũng có thể sai hoặc chưa đầy đủ. Người dùng nhập nhầm địa chỉ; thiết bị đo lệch; dịch vụ đối tác gửi dữ liệu trễ; hai nguồn có cách định nghĩa khác nhau. Vì thế, mô hình cần cân nhắc nguồn, thời gian ghi nhận, độ tin cậy và cách xử lý khi thông tin thay đổi.

## 3. Khái niệm nghiệp vụ: cách tổ chức hiểu thực tế

**Khái niệm nghiệp vụ** là cách tổ chức chia thế giới thành những đối tượng, sự kiện, vai trò và quy tắc có ý nghĩa đối với hoạt động của mình. Khái niệm giúp các bộ phận nói cùng một ngôn ngữ và quyết định cách xử lý tình huống.

Một khái niệm không đơn thuần là một từ trong tài liệu. Nó cần có định nghĩa, phạm vi, thuộc tính có ý nghĩa, quan hệ với các khái niệm khác và quy tắc áp dụng.

### 3.1. Định nghĩa thuật ngữ và ranh giới khái niệm

Giả sử một cửa hàng dùng từ “khách hàng”. Cần xác định khái niệm này là:

- cá nhân đã từng mua hàng;
- người có tài khoản trên website;
- tổ chức ký hợp đồng;
- chủ thể chịu trách nhiệm thanh toán;
- hay một hồ sơ tổng hợp nhiều vai trò.

Mỗi cách hiểu tạo ra một mô hình khác nhau. Nếu website cho phép khách mua không cần đăng ký, “người mua” và “tài khoản người dùng” rõ ràng không phải cùng một khái niệm.

Một **từ điển thuật ngữ nghiệp vụ (business glossary)** có thể ghi lại:

| Thuật ngữ | Định nghĩa | Cần phân biệt |
|---|---|---|
| Người mua | Chủ thể khởi tạo yêu cầu mua hàng | Có thể khác người nhận hoặc người thanh toán |
| Tài khoản | Hồ sơ xác thực và phân quyền truy cập hệ thống | Không mặc định tương ứng một người duy nhất |
| Đơn hàng | Cam kết/yêu cầu mua được hệ thống tiếp nhận theo quy tắc cửa hàng | Không đồng nghĩa với thanh toán hay giao hàng |
| Lần thanh toán | Một lần xử lý yêu cầu thu tiền cho một khoản phải trả | Một đơn hàng có thể có nhiều lần thử |
| Giao hàng | Quy trình chuyển hàng đến địa chỉ hoặc người nhận | Có thể gồm nhiều lô giao |

Từ điển giúp phát hiện các từ đồng âm hoặc gần nghĩa đang được dùng khác nhau giữa bán hàng, kế toán, kho và kỹ thuật.

### 3.2. Thuộc tính có ý nghĩa theo ngữ cảnh

Một thuộc tính chỉ có ý nghĩa khi biết nó mô tả điều gì và thuộc về khái niệm nào.

Ví dụ, `created_at` có thể là thời điểm hồ sơ được tạo, thời điểm đơn hàng được tiếp nhận hoặc thời điểm bản ghi được ghi vào database. Các thời điểm này không nhất thiết giống nhau.

Tên trường kỹ thuật không đủ để định nghĩa ý nghĩa nghiệp vụ. Cần mô tả:

- định nghĩa của thuộc tính;
- đơn vị đo hoặc miền giá trị;
- thời điểm hiệu lực;
- nguồn dữ liệu;
- điều kiện bắt buộc hoặc tùy chọn;
- quy tắc cập nhật và lưu lịch sử.

### 3.3. Ranh giới và vòng đời

Một khái niệm nghiệp vụ có vòng đời riêng khi nó có thể được tạo, thay đổi, hoàn tất hoặc hủy theo những quy tắc độc lập.

Ví dụ, đơn hàng và thanh toán có liên hệ chặt chẽ nhưng có vòng đời khác nhau. Đơn hàng có thể tồn tại khi chưa thanh toán; một lần thanh toán có thể thất bại trong khi đơn hàng vẫn còn hiệu lực; một đơn hàng có thể được thanh toán bằng nhiều giao dịch.

Tách hai khái niệm giúp biểu diễn đúng quy trình. Gộp chúng thành một trạng thái đơn giản như `order_status = PAID` có thể làm mất thông tin về các lần thử, hoàn tiền hoặc thanh toán một phần.

## 4. Biểu diễn trong hệ thống: dữ liệu là một mô tả

**Biểu diễn dữ liệu (data representation)** là cách một hệ thống mã hóa một khái niệm hoặc quan sát thành dạng có thể lưu, truyền và xử lý. Biểu diễn có thể là hàng trong bảng, document JSON, nút và cạnh trong graph, message trên hàng đợi, tệp CSV hoặc một ô trong báo cáo.

Biểu diễn cần giữ đủ ý nghĩa cho mục đích sử dụng. Một biểu diễn có thể chính xác về cú pháp nhưng sai về ngữ nghĩa.

Ví dụ, giá trị `100` là số hợp lệ, nhưng nếu không biết đó là 100 đồng, 100 nghìn đồng hay 100 USD thì không thể dùng đúng trong nghiệp vụ.

### 4.1. Biểu diễn không phải bản sao hoàn hảo của thực tế

Mọi hệ thống đều có giới hạn về phạm vi, độ chính xác, thời gian cập nhật và cấu trúc. Một bản ghi khách hàng có thể chỉ lưu tên và email; nó không mô tả toàn bộ con người đó.

Hệ thống cũng có thể tạo ra dữ liệu dẫn xuất, chẳng hạn tổng tiền đơn hàng, điểm xếp hạng hoặc trạng thái được tính từ các sự kiện. Dữ liệu dẫn xuất là kết quả của quy tắc tính toán, không phải lúc nào cũng là một sự kiện được quan sát trực tiếp.

Khi dùng dữ liệu dẫn xuất, cần ghi rõ:

- công thức hoặc quy tắc tính;
- dữ liệu nguồn;
- thời điểm tính;
- cách xử lý khi dữ liệu nguồn thay đổi;
- việc giá trị có được lưu lại hay tính lại mỗi lần truy vấn.

### 4.2. Một khái niệm có thể có nhiều biểu diễn

Khái niệm “đơn hàng” có thể được biểu diễn theo nhiều cách trong cùng hệ thống:

- các bảng `orders`, `order_items` và `payments` trong database quan hệ;
- một JSON document cho màn hình xem chi tiết đơn hàng;
- một message `OrderPlaced` gửi sang hệ thống kho;
- một dòng trong bảng fact để tổng hợp doanh thu;
- một nút `Order` trong graph để truy vết mối quan hệ.

Những biểu diễn này có thể phục vụ mục đích khác nhau và chứa lượng thông tin khác nhau. Chúng cần có quy tắc ánh xạ để tránh việc mỗi nơi diễn giải khái niệm “đơn hàng” theo một cách không tương thích.

### 4.3. Một biểu diễn có thể kết hợp nhiều khái niệm

Một document đơn hàng có thể nhúng địa chỉ giao hàng, các dòng hàng và thông tin người nhận. Điều đó không có nghĩa tất cả các phần đều là cùng một khái niệm nghiệp vụ. Chúng được đặt chung vì thường được đọc hoặc quản lý cùng nhau.

Ngược lại, một khái niệm có thể trải qua nhiều bản ghi. Thông tin khách hàng có thể nằm trong bảng khách hàng, bảng địa chỉ, bảng liên hệ và bảng tài khoản. Không thể chỉ nhìn một bảng rồi kết luận toàn bộ khái niệm nghiệp vụ được lưu ở đó.

## 5. Ánh xạ giữa ba lớp

**Ánh xạ (mapping)** mô tả cách một khái niệm nghiệp vụ được chuyển thành cấu trúc dữ liệu cụ thể và cách dữ liệu được diễn giải trở lại thành ý nghĩa nghiệp vụ.

Một ánh xạ tốt phải giải thích được nguồn, đích, quy tắc biến đổi, trường hợp thiếu dữ liệu và cách xử lý khi hai nguồn mâu thuẫn.

### 5.1. Bảng ánh xạ minh họa

| Thực tế hoặc quan sát | Khái niệm nghiệp vụ | Biểu diễn hệ thống | Câu hỏi cần làm rõ |
|---|---|---|---|
| Một người đặt hàng | Người mua | `buyer_id`, hồ sơ khách hàng hoặc thông tin mua khách | Người mua có cần tài khoản không? |
| Một yêu cầu mua được tiếp nhận | Đơn hàng | `orders` hoặc document `Order` | Khi nào đơn được coi là đã tiếp nhận? |
| Hai sản phẩm được đặt | Dòng hàng | `order_items` hoặc mảng `items` | Số lượng và đơn giá được chốt lúc nào? |
| Nhà cung cấp thanh toán trả kết quả | Lần thanh toán | `payments`, payment event | Mã giao dịch bên ngoài có duy nhất không? |
| Kiện hàng đến người nhận | Lần giao hàng | `shipments`, tracking event | Một đơn hàng có thể giao thành nhiều kiện không? |

Bảng ánh xạ giúp nhìn thấy khoảng trống giữa nghiệp vụ và dữ liệu. Nếu không trả lời được một câu hỏi, có thể khái niệm chưa được định nghĩa hoặc biểu diễn chưa đủ.

### 5.2. Ví dụ chuyển yêu cầu thành dữ liệu

Yêu cầu: “Một khách hàng có thể đặt nhiều đơn hàng. Mỗi đơn hàng gồm nhiều sản phẩm. Giá của sản phẩm có thể thay đổi, nhưng đơn hàng cũ phải giữ đúng giá lúc mua.”

**Ở lớp thực tế**, có người mua hàng ở một thời điểm, sản phẩm được chọn, số lượng được xác nhận và giá được áp dụng.

**Ở lớp nghiệp vụ**, ta định nghĩa:

- `Customer`: chủ thể được cửa hàng quản lý như khách hàng.
- `Order`: yêu cầu mua hàng được tiếp nhận.
- `Product`: mặt hàng được kinh doanh.
- `OrderItem`: một sản phẩm cùng số lượng và giá được áp dụng trong đơn hàng.

**Ở lớp biểu diễn**, mô hình quan hệ có thể dùng:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY
);

CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    current_price DECIMAL(12, 2) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12, 2) NOT NULL
);
```

Trong thiết kế này, `products.current_price` thể hiện giá hiện tại của danh mục sản phẩm; `order_items.unit_price` lưu giá đã áp dụng cho giao dịch. Hai trường cùng liên quan đến “giá sản phẩm” nhưng có ý nghĩa và thời điểm hiệu lực khác nhau.

Nếu chỉ lưu `product_id` và luôn đọc giá hiện tại, lịch sử đơn hàng sẽ bị thay đổi khi danh mục cập nhật giá. Nếu chỉ lưu một giá duy nhất trong bảng sản phẩm, ta đã gộp hai khái niệm thời gian khác nhau vào một giá trị.

### 5.3. Không giả định quan hệ một-một

Các quan hệ giữa thực tế, khái niệm và biểu diễn thường có dạng nhiều-nhiều:

- Một người ngoài đời có thể có nhiều tài khoản hoặc hồ sơ ở các hệ thống.
- Một khái niệm khách hàng có thể kết hợp dữ liệu từ CRM, cửa hàng và hệ thống hỗ trợ.
- Một đơn hàng có thể được biểu diễn trong database giao dịch, message tích hợp và kho phân tích.
- Một bản ghi có thể chứa dữ liệu tổng hợp từ nhiều sự kiện.

Vì vậy, khi đồng bộ dữ liệu giữa các hệ thống, cần có quy tắc nhận diện, hợp nhất, ưu tiên nguồn và xử lý xung đột. Không nên mặc định rằng hai bản ghi có cùng tên hoặc email là cùng một chủ thể.

## 6. Những yếu tố quyết định ý nghĩa của dữ liệu

Dữ liệu không chỉ là giá trị. Để diễn giải đúng, thường cần thêm định danh, ngữ cảnh, thời gian, nguồn và quy tắc.

### 6.1. Định danh và nhận diện

**Định danh (identifier)** là giá trị được dùng để tham chiếu một đối tượng trong một phạm vi xác định. Mã khách hàng `CUS-18` có thể duy nhất trong hệ thống cửa hàng nhưng không có ý nghĩa duy nhất trên toàn thế giới.

Cần phân biệt:

- **Danh tính (identity):** đối tượng nào đang được nói đến.
- **Định danh:** giá trị dùng để tham chiếu đối tượng.
- **Khóa database:** cột hoặc tập cột dùng để xác định một hàng.
- **Mã nghiệp vụ:** mã có ý nghĩa với người dùng hoặc quy trình.

Một đối tượng có thể có nhiều định danh: ID nội bộ, mã khách hàng hiển thị, mã ở hệ thống đối tác. Chúng có thể thay đổi theo phạm vi và thời gian. Hãy xác định định danh nào ổn định, ai cấp và hệ thống nào chịu trách nhiệm quản lý.

### 6.2. Thời gian và hiệu lực

Một giá trị có thể thay đổi theo thời gian. Cần phân biệt ít nhất:

- **Thời điểm sự kiện xảy ra (event time):** khi việc thực tế xảy ra.
- **Thời điểm hệ thống ghi nhận (recorded time):** khi hệ thống nhận hoặc lưu thông tin.
- **Thời gian hiệu lực (valid time):** khoảng thời gian giá trị được xem là đúng trong nghiệp vụ.

Ví dụ, khách hàng chuyển địa chỉ ngày 10/5 nhưng hệ thống chỉ nhận được cập nhật ngày 12/5. Thời điểm hiệu lực và thời điểm ghi nhận khác nhau. Nếu báo cáo lịch sử cần biết địa chỉ nào có hiệu lực ngày 11/5, chỉ lưu thời điểm cập nhật mới nhất là chưa đủ.

Đối với thời gian, cần xác định múi giờ, độ chính xác và cách xử lý ngày không có giờ. Không nên lưu một chuỗi thời gian thiếu quy ước rồi giả định mọi hệ thống hiểu giống nhau.

### 6.3. Đơn vị và miền giá trị

Các số đo cần đơn vị: kilogram, mét, giây, độ C. Số tiền cần đơn vị tiền tệ và quy tắc làm tròn. Tỷ lệ cần biết biểu diễn theo phần trăm hay số thập phân.

Ví dụ, `0.15` có thể nghĩa là 15% hoặc 0,15%; `1000` có thể là gram hoặc kilogram. Nếu đơn vị không được thể hiện trong tên trường, schema hoặc hợp đồng dữ liệu, các hệ thống có thể tính toán sai mà không phát sinh lỗi cú pháp.

Nên dùng kiểu dữ liệu và miền giá trị thể hiện rõ ý nghĩa. Với tiền, cần kiểu số thập phân chính xác hoặc kiểu tiền tệ phù hợp, cùng mã tiền tệ; không dùng số thực nhị phân cho phép tính tài chính cần độ chính xác thập phân.

### 6.4. Thiếu dữ liệu và trạng thái chưa biết

Giá trị thiếu có nhiều ý nghĩa:

- chưa được cung cấp;
- chưa được xác minh;
- không áp dụng;
- không tồn tại;
- bị ẩn do quyền truy cập;
- chưa được đồng bộ.

Không nên dùng cùng một giá trị `NULL`, chuỗi rỗng hoặc số 0 cho tất cả trường hợp nếu nghiệp vụ cần phân biệt. Ví dụ, “chưa biết ngày giao” khác với “đơn hàng không cần giao”. Một số trường hợp cần trạng thái riêng hoặc lý do thiếu dữ liệu.

### 6.5. Nguồn gốc và độ tin cậy

**Nguồn gốc dữ liệu (data provenance)** cho biết dữ liệu đến từ đâu, được tạo hoặc biến đổi như thế nào. Ví dụ, địa chỉ có thể do khách nhập, nhân viên xác nhận hoặc được lấy từ đối tác giao hàng.

Khi có nhiều nguồn, cần xác định:

- nguồn nào có thẩm quyền cho từng thuộc tính;
- dữ liệu được đồng bộ theo thời gian thực hay theo lô;
- quy tắc chọn giá trị khi có xung đột;
- cách lưu nguồn và thời điểm cập nhật;
- ai có quyền sửa dữ liệu.

Không có một nguồn duy nhất luôn đúng cho mọi thuộc tính. Hệ thống CRM có thể là nguồn chuẩn cho thông tin liên hệ, trong khi hệ thống hóa đơn là nguồn chuẩn cho tên pháp lý trên hóa đơn.

## 7. Chọn cấu trúc biểu diễn theo mục đích

Sau khi hiểu khái niệm nghiệp vụ, mới quyết định cách biểu diễn vật lý. Mỗi kiểu mô hình có cách lưu và truy vấn khác nhau.

| Kiểu biểu diễn | Cách thể hiện khái niệm | Phù hợp với |
|---|---|---|
| Quan hệ | Bảng, hàng, cột, khóa và quan hệ | Giao dịch, ràng buộc toàn vẹn, dữ liệu có quan hệ rõ |
| Document | Đối tượng và dữ liệu lồng nhau | Đọc/ghi theo aggregate hoặc hồ sơ có cấu trúc linh hoạt |
| Đồ thị | Nút, cạnh và thuộc tính quan hệ | Truy vấn nhiều bước, mạng lưới và đường đi |
| Phân tích | Fact, dimension và grain | Tổng hợp, báo cáo và so sánh theo chiều |

Dù chọn cấu trúc nào, ý nghĩa nghiệp vụ cần được giữ nhất quán. Ví dụ, `OrderPlaced` trong message tích hợp và bản ghi `orders` có thể cùng nói về một đơn hàng nhưng thời điểm phát sinh, trạng thái và nội dung không giống nhau. Hợp đồng dữ liệu cần định nghĩa chính xác sự khác nhau đó.

### 7.1. Hợp đồng dữ liệu

**Hợp đồng dữ liệu (data contract)** mô tả cấu trúc và ngữ nghĩa dữ liệu mà một bên cung cấp cam kết với bên sử dụng. Hợp đồng có thể bao gồm:

- tên trường, kiểu dữ liệu và định dạng;
- ý nghĩa nghiệp vụ của từng trường;
- trường bắt buộc, tùy chọn và điều kiện hợp lệ;
- đơn vị, múi giờ, mã hóa và quy ước null;
- định danh và quy tắc duy nhất;
- nguồn gốc, tần suất cập nhật và độ trễ;
- chính sách tương thích khi thay đổi schema.

Ví dụ, API trả về `createdAt` cần xác định đó là thời điểm đơn hàng được tạo theo nghiệp vụ hay thời điểm record được ghi vào database, định dạng timezone ra sao và độ chính xác đến giây hay mili giây.

Một schema JSON hợp lệ chỉ chứng minh payload có cấu trúc đúng. Hợp đồng dữ liệu tốt còn phải bảo đảm bên nhận hiểu đúng ý nghĩa của các trường.

## 8. Kiểm tra chất lượng của biểu diễn

Có thể kiểm tra biểu diễn qua nhiều chiều:

- **Đúng cú pháp (syntactic validity):** dữ liệu có tuân theo định dạng, kiểu và schema không?
- **Đúng ngữ nghĩa (semantic validity):** giá trị có đúng ý nghĩa nghiệp vụ không?
- **Đầy đủ (completeness):** có đủ thông tin cần thiết cho mục đích sử dụng không?
- **Nhất quán (consistency):** các trường và nguồn liên quan có mâu thuẫn không?
- **Chính xác (accuracy):** dữ liệu có phản ánh đúng quan sát hoặc thực tế được xác minh không?
- **Kịp thời (timeliness):** dữ liệu có đủ mới cho quyết định đang thực hiện không?
- **Truy nguyên được (traceability):** có thể biết nguồn, quy tắc biến đổi và lịch sử của dữ liệu không?

Ví dụ, chuỗi ngày `2026-13-40` sai cú pháp. Chuỗi `2026-11-21` đúng cú pháp nhưng có thể sai ngữ nghĩa nếu trường đó yêu cầu ngày sinh mà dữ liệu nguồn là ngày tạo tài khoản. Một số tiền có kiểu decimal hợp lệ nhưng sai đơn vị tiền tệ cũng là dữ liệu sai.

### 8.1. Kiểm chứng bằng tình huống

Với mỗi khái niệm quan trọng, hãy thử các tình huống:

1. **Đối tượng có nhiều vai trò:** người mua và người nhận có thể khác nhau.
2. **Một chủ thể có nhiều hồ sơ:** cùng một tổ chức xuất hiện ở nhiều hệ thống với các mã khác nhau.
3. **Thay đổi theo thời gian:** địa chỉ, giá hoặc trạng thái thay đổi; lịch sử cần được giữ ra sao?
4. **Sự kiện đến trễ:** thông báo giao hàng đến sau khi hệ thống đã nhận một cập nhật mới hơn.
5. **Nguồn mâu thuẫn:** hai hệ thống gửi hai địa chỉ khác nhau.
6. **Thiếu thông tin:** trường hợp không áp dụng phải được phân biệt với chưa biết.
7. **Đơn vị khác nhau:** một nguồn gửi kilogram, nguồn khác gửi gram.
8. **Lặp message:** cùng một sự kiện được gửi nhiều lần; hệ thống có tạo bản ghi trùng không?

Nếu mô hình không thể giải thích những tình huống này, cần xem lại định nghĩa khái niệm, quy tắc ánh xạ hoặc hợp đồng dữ liệu.

## 9. Những sai lầm thường gặp

- **Đồng nhất bản ghi với đối tượng ngoài đời:** xóa hoặc sửa record không làm sự kiện thực tế biến mất. Hãy xác định dữ liệu là trạng thái hiện tại, lịch sử hay bản sao.
- **Đồng nhất tài khoản với con người:** một người có thể có nhiều tài khoản, còn tài khoản tổ chức có thể do nhiều người sử dụng.
- **Dùng một thuật ngữ cho nhiều khái niệm:** “khách hàng”, “người dùng”, “người mua” và “người thanh toán” cần được định nghĩa theo quy trình.
- **Coi trạng thái là lịch sử:** trạng thái hiện tại không giải thích được các bước đã xảy ra. Hãy lưu sự kiện hoặc lịch sử khi nghiệp vụ cần truy vết.
- **Lưu số mà thiếu đơn vị:** dữ liệu vẫn hợp lệ về kiểu nhưng có thể sai hoàn toàn về ý nghĩa.
- **Không phân biệt thời điểm xảy ra và thời điểm ghi nhận:** cập nhật trễ có thể làm báo cáo lịch sử sai.
- **Giả định nguồn nào cũng có thẩm quyền như nhau:** cần quy tắc nguồn chuẩn theo từng thuộc tính.
- **Chỉ kiểm tra schema:** dữ liệu đúng cấu trúc vẫn có thể sai ngữ nghĩa, thiếu ngữ cảnh hoặc không nhất quán.

## 10. Kết luận

Thực tế là những sự vật, sự kiện và trạng thái mà tổ chức muốn quan sát. Khái niệm nghiệp vụ là cách tổ chức diễn giải và quản lý phần thực tế đó. Biểu diễn hệ thống là cấu trúc dữ liệu được tạo ra để lưu, truyền và xử lý thông tin theo một mục đích.

Giữ rõ ba lớp giúp tránh nhầm bản ghi với đối tượng, nhầm thuật ngữ với cấu trúc database và nhầm dữ liệu hợp lệ về cú pháp với dữ liệu đúng về ý nghĩa. Khi thiết kế, hãy định nghĩa khái niệm trước, làm rõ quy tắc và ngữ cảnh, sau đó mới chọn biểu diễn và kiểm chứng ánh xạ.

## Tự kiểm tra

1. Vì sao một bản ghi `orders` không phải toàn bộ sự kiện đặt hàng ngoài đời?
2. Phân biệt người mua, người nhận hàng và tài khoản người dùng bằng một ví dụ.
3. Một đơn hàng có thể có nhiều lần thanh toán thất bại và thành công. Vì sao trạng thái hiện tại không đủ để mô tả toàn bộ lịch sử?
4. Vì sao giá trị `100` chưa đủ ý nghĩa nếu thiếu đơn vị hoặc mã tiền tệ?
5. Phân biệt event time, recorded time và valid time.
6. Một khái niệm nghiệp vụ có thể được biểu diễn trong nhiều cấu trúc hệ thống như thế nào?
7. Hãy chọn một trường dữ liệu trong hệ thống bạn biết và mô tả định nghĩa, đơn vị, nguồn, thời gian hiệu lực, quy tắc thiếu dữ liệu và cách kiểm tra ngữ nghĩa.

