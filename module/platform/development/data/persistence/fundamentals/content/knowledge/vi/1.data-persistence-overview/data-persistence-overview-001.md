# Lưu trữ bền vững (data persistence) là gì và giải quyết vấn đề nào?

> **Chương:** Định hướng  
> **Phạm vi:** DATA_PERSISTENCE_FUNDAMENTALS — nền tảng lưu trữ dữ liệu bền vững trong ứng dụng, đặc biệt khi thiết kế lớp truy cập dữ liệu cho Java.

## 1. Bắt đầu từ một tình huống quen thuộc

Giả sử một ứng dụng bán hàng có chức năng đặt mua sản phẩm. Khi khách hàng nhấn **Đặt hàng**, chương trình cần ghi nhận đơn hàng, giảm số lượng tồn kho và trả về mã đơn. Nếu mọi thông tin chỉ nằm trong biến, đối tượng Java hoặc một collection của tiến trình đang chạy, điều gì xảy ra khi ứng dụng được khởi động lại?

- Đơn hàng vừa tạo có thể biến mất.
- Kho hàng có thể trở về số lượng cũ, khiến hệ thống bán vượt số lượng thực.
- Khách hàng không thể tra cứu lịch sử mua hàng.
- Hai yêu cầu đặt hàng đến đồng thời có thể cùng nhìn thấy một sản phẩm cuối cùng và đều cho rằng mình mua thành công.
- Nếu hệ thống báo lỗi giữa chừng, không rõ đơn hàng đã được lưu hay chưa.

Đây là những vấn đề mà **data persistence** giúp giải quyết. Nó không chỉ trả lời câu hỏi “đưa dữ liệu vào ổ đĩa bằng cách nào?”, mà còn giúp ứng dụng quản lý dữ liệu **qua thời gian, qua sự cố và giữa nhiều phiên làm việc**.

Sau bài học, người học có thể:

1. Giải thích data persistence và phân biệt dữ liệu tạm thời với dữ liệu cần tồn tại lâu dài.
2. Nhận diện các yêu cầu về tính đúng đắn, độ bền, truy xuất, đồng thời và phục hồi.
3. Hiểu vai trò của mô hình dữ liệu, lược đồ, truy vấn, chỉ mục và giao dịch trong một hệ thống persistence.
4. Phác thảo ranh giới persistence của ứng dụng Java và lựa chọn hướng lưu trữ phù hợp với bài toán.

## 2. Data persistence là gì?

**Data persistence (lưu trữ bền vững)** là khả năng ghi nhận và duy trì trạng thái dữ liệu để dữ liệu vẫn có thể được truy xuất sau khi thao tác hiện tại kết thúc, đối tượng trong bộ nhớ bị hủy hoặc tiến trình ứng dụng ngừng chạy. Thông thường, dữ liệu được đặt trong hệ thống lưu trữ có khả năng tồn tại độc lập với vòng đời của tiến trình, ví dụ tệp trên thiết bị lưu trữ, cơ sở dữ liệu quan hệ hoặc kho đối tượng.

Hãy phân biệt hai loại trạng thái:

| Loại trạng thái | Ví dụ | Nếu tiến trình Java dừng |
| --- | --- | --- |
| **Tạm thời (transient)** | Biến cục bộ, danh sách kết quả tìm kiếm đang xử lý, bộ đệm trong RAM | Thường mất; có thể tính toán hoặc nạp lại |
| **Cần duy trì (persistent)** | Hồ sơ người dùng, đơn hàng, hóa đơn, số dư, trạng thái công việc | Phải có cách truy xuất lại theo cam kết của hệ thống |

Ví dụ, câu lệnh Java sau chỉ tạo dữ liệu trong bộ nhớ:

~~~java
Map<String, String> orders = new HashMap<>();
orders.put("ORD-1001", "CONFIRMED");
~~~

Nếu JVM kết thúc, nội dung của map không tự chuyển thành dữ liệu bền vững. Một cơ chế persistence phải ghi trạng thái cần giữ vào nơi lưu trữ thích hợp, rồi có khả năng đọc lại để phục vụ yêu cầu tiếp theo.

### “Bền vững” là một cam kết có điều kiện

Độ bền không có nghĩa dữ liệu **không bao giờ** mất trong mọi hoàn cảnh. Nó phụ thuộc vào khả năng của thiết bị, cách cấu hình hệ quản trị, thời điểm xác nhận ghi thành công, chính sách sao lưu và mô hình sự cố mà hệ thống dự kiến chịu được.

Chẳng hạn, một cơ sở dữ liệu có thể xác nhận giao dịch sau khi ghi thông tin cần thiết vào nhật ký khôi phục (write-ahead log, nếu hệ quản trị áp dụng kỹ thuật này). Dữ liệu sau đó có thể được phục hồi khi tiến trình gặp sự cố. Tuy nhiên, nếu cả thiết bị lưu trữ bị hủy, không có bản sao hoặc bản sao lưu, dữ liệu vẫn có thể mất. Vì thế, **durability của giao dịch, replication và backup là những cơ chế có mục đích khác nhau**.

### Persistence không đồng nhất với những khái niệm lân cận

| Khái niệm | Mục đích chính | Quan hệ với persistence |
| --- | --- | --- |
| **Serialization** | Chuyển đối tượng thành dạng byte, JSON, XML… | Là một kỹ thuật biểu diễn dữ liệu; bản thân việc chuyển đổi chưa làm dữ liệu tồn tại lâu dài |
| **Caching** | Giảm độ trễ bằng cách giữ kết quả truy cập thường dùng | Thường có thể mất và tạo lại; một số cache có khả năng lưu bền nhưng không tự động trở thành nguồn dữ liệu chính |
| **Replication** | Duy trì các bản sao trên nhiều nút/địa điểm | Cải thiện tính sẵn sàng và khả năng chịu lỗi; lỗi xóa hoặc ghi sai vẫn có thể lan sang các bản sao |
| **Backup** | Lưu bản sao có thể phục hồi tại một thời điểm | Hỗ trợ khôi phục sau lỗi nghiêm trọng, thao tác nhầm hoặc mất dữ liệu |
| **Archiving** | Giữ dữ liệu cũ để tra cứu, kiểm toán hoặc tuân thủ | Tập trung vào lưu giữ dài hạn, thường ít truy cập hơn dữ liệu vận hành |

## 3. Persistence giải quyết những vấn đề cốt lõi nào?

### 3.1. Duy trì dữ liệu qua vòng đời ứng dụng

Người dùng mong đợi thông tin đã lưu ngày hôm nay vẫn có sẵn ở lần đăng nhập sau. Dữ liệu phải độc lập với vòng đời của request HTTP, object Java và phiên chạy của server. Điều này cũng giúp triển khai lại ứng dụng mà không cần giữ nguyên tiến trình cũ.

### 3.2. Chia sẻ trạng thái giữa các yêu cầu và phiên làm việc

Một đơn hàng có thể được tạo từ điện thoại, được nhân viên kho xử lý qua giao diện web và được bộ phận chăm sóc khách hàng tra cứu sau đó. Những thành phần này cần nhìn vào một nguồn dữ liệu có quy tắc xác thực, cập nhật và truy vấn rõ ràng.

### 3.3. Bảo đảm các thay đổi liên quan diễn ra nhất quán

Khi đặt hàng, việc giảm tồn kho và tạo đơn là hai thay đổi có quan hệ nghiệp vụ. Nếu chỉ thực hiện thành công một thao tác, dữ liệu có thể trở nên mâu thuẫn. Giao dịch (transaction), ràng buộc dữ liệu và kiểm soát đồng thời giúp quản lý trường hợp này.

### 3.4. Truy vấn dữ liệu có hiệu quả

Ứng dụng thường cần trả lời các câu hỏi như “đơn hàng gần đây nhất của khách hàng là gì?” hoặc “sản phẩm nào còn hàng?”. Lưu dữ liệu thôi chưa đủ; hệ thống còn cần cấu trúc, khóa, truy vấn và chỉ mục phù hợp để xử lý khối lượng dữ liệu ngày càng tăng.

### 3.5. Khôi phục và kiểm soát rủi ro

Ứng dụng phải có cách ứng phó khi kết nối mạng gián đoạn, ổ đĩa đầy, dịch vụ lưu trữ ngừng hoạt động hoặc người vận hành xóa nhầm dữ liệu. Persistence đòi hỏi xác định dữ liệu nào được bảo vệ, có thể chấp nhận mất bao nhiêu, và phục hồi trong bao lâu.

### 3.6. Quản lý dữ liệu trong thời gian dài

Quy tắc nghiệp vụ thay đổi theo phiên bản sản phẩm: một đơn hàng có thể cần thêm địa chỉ giao, mã khuyến mãi hoặc trạng thái hoàn tiền. Lược đồ và cách đọc/ghi phải được tiến hóa để phiên bản ứng dụng mới vận hành được với dữ liệu đã tồn tại.

## 4. Dữ liệu đi từ yêu cầu người dùng tới nơi lưu trữ như thế nào?

Trong ứng dụng Java, một luồng xử lý điển hình có thể được hình dung như sau:

~~~mermaid
flowchart TD
    A["Người dùng gửi yêu cầu"] --> B["API / Controller"]
    B --> C["Kiểm tra dữ liệu và quy tắc nghiệp vụ"]
    C --> D["Application Service"]
    D --> E["Repository / Persistence Adapter"]
    E --> F[("Cơ sở dữ liệu")]
    F --> G{"Giao dịch thành công?"}
    G -- "Có, COMMIT" --> H["Trả kết quả đã ghi nhận"]
    G -- "Không, ROLLBACK" --> I["Thông báo lỗi hoặc xử lý thử lại"]
~~~

Sơ đồ là mô hình khái quát. Một hệ thống thực tế còn có thể có hàng đợi, bộ nhớ đệm, nhiều kho dữ liệu và tác vụ bất đồng bộ. Điểm quan trọng là **ứng dụng cần xác định nơi nào chịu trách nhiệm ghi dữ liệu, khi nào thao tác được xem là thành công và xử lý gì khi không xác định được kết quả ghi**.

Một trình tự thường gặp:

1. Nhận và kiểm tra cấu trúc dữ liệu đầu vào (ví dụ số lượng đặt phải lớn hơn 0).
2. Kiểm tra điều kiện nghiệp vụ (ví dụ sản phẩm có thể bán).
3. Mở giao dịch hoặc sử dụng ngữ cảnh giao dịch đã được cấu hình.
4. Ghi các thay đổi liên quan, đồng thời kiểm tra ràng buộc và số hàng được tác động.
5. Xác nhận giao dịch (*commit*) khi mọi thao tác hợp lệ, hoặc hủy (*rollback*) khi có lỗi.
6. Trả kết quả cho phía gọi; trường hợp mất kết nối ở thời điểm nhạy cảm phải có cách xác định lại trạng thái thực tế.

**Lưu ý:** “Nhận request thành công” và “ghi dữ liệu thành công” không phải cùng một sự kiện. Việc trả mã thành công quá sớm có thể làm người dùng tin rằng thông tin đã được lưu, trong khi thao tác ghi vẫn đang chờ xử lý.

## 5. Năm thành phần nền tảng của một thiết kế persistence

### 5.1. Mô hình dữ liệu: cần giữ lại những sự thật nào?

Trước khi chọn sản phẩm cơ sở dữ liệu, cần xác định:

- **Thực thể:** khách hàng, sản phẩm, đơn hàng, khoản thanh toán…
- **Thuộc tính:** mã định danh, thời gian tạo, số lượng, trạng thái…
- **Quan hệ:** một đơn hàng gồm nhiều dòng hàng; một khách hàng có thể có nhiều đơn.
- **Bất biến nghiệp vụ:** số lượng tồn kho không âm, mã đơn không trùng, mỗi dòng hàng có số lượng dương.
- **Vòng đời:** dữ liệu được tạo, chỉnh sửa, chốt, lưu trữ và xóa khi nào.

Mô hình tốt làm rõ điều gì được lưu như **sự thật gốc** và điều gì có thể tính lại. Chẳng hạn, tổng tiền đơn hàng có thể tính từ các dòng hàng, nhưng cần cân nhắc lưu giá bán tại thời điểm đặt để không bị ảnh hưởng khi giá niêm yết thay đổi.

### 5.2. Lược đồ và ràng buộc: dữ liệu hợp lệ trông như thế nào?

Với cơ sở dữ liệu quan hệ, lược đồ (schema) định nghĩa bảng, cột, kiểu, khóa và ràng buộc. Ví dụ dưới đây dùng cú pháp PostgreSQL để minh họa mô hình đơn hàng đơn giản:

~~~sql
CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    stock_qty INTEGER NOT NULL CHECK (stock_qty >= 0)
);

CREATE TABLE orders (
    order_id UUID PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('NEW', 'CONFIRMED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE order_items (
    order_id UUID NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_minor BIGINT NOT NULL CHECK (unit_price_minor >= 0),
    PRIMARY KEY (order_id, product_id)
);
~~~

Ở đây, **primary key** ngăn trùng định danh, **foreign key** ngăn dòng hàng tham chiếu tới đơn hoặc sản phẩm không tồn tại, và **CHECK** chặn một số giá trị không hợp lệ ngay tại tầng dữ liệu. Nếu đã có bảng khách hàng, có thể bổ sung khóa ngoại từ **customer_id** đến bảng đó.

Trường **unit_price_minor** dùng đơn vị tiền nhỏ nhất (chẳng hạn cent với loại tiền có phần lẻ) để tránh lỗi làm tròn của số thực nhị phân khi biểu diễn tiền. Đơn vị tiền và loại tiền vẫn cần được định nghĩa rõ theo nghiệp vụ; không phải mọi loại tiền đều có hai chữ số thập phân.

**Ràng buộc trong database là lớp bảo vệ bổ sung**, không thay thế việc kiểm tra đầu vào và quy tắc nghiệp vụ trong Java. Nó đặc biệt hữu ích khi nhiều ứng dụng hoặc nhiều tiến trình cùng ghi vào một nguồn dữ liệu.

### 5.3. Truy vấn và chỉ mục: tìm dữ liệu bằng cách nào?

Ví dụ yêu cầu lấy 20 đơn gần nhất của một khách hàng:

~~~sql
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 101
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Khi lượng đơn tăng, chỉ mục phù hợp có thể giúp truy vấn tránh phải duyệt toàn bộ bảng:

~~~sql
CREATE INDEX idx_orders_customer_created
    ON orders (customer_id, created_at DESC, order_id DESC);
~~~

Chỉ mục giúp tăng tốc một số cách đọc, nhưng cũng chiếm dung lượng và làm phát sinh công việc khi chèn, sửa, xóa. Vì vậy, nên thiết kế dựa trên **mẫu truy vấn thực tế**, sau đó kiểm chứng bằng kế hoạch thực thi truy vấn và số liệu đo. Nếu phân trang qua nhiều lần gọi, cần quy định thứ tự ổn định để hạn chế bỏ sót hoặc lặp bản ghi.

### 5.4. Giao dịch: nhiều thay đổi được xem như một đơn vị

Một giao dịch gom các thao tác có liên quan thành đơn vị xử lý. Trong hệ quản trị giao dịch quan hệ, bộ thuộc tính **ACID** thường được dùng để diễn giải:

| Thuộc tính | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Atomicity (nguyên tử)** | Các thay đổi trong giao dịch được xác nhận cùng nhau hoặc bị hủy theo cơ chế rollback | Không tạo đơn hàng nếu thao tác giảm kho thất bại |
| **Consistency (nhất quán)** | Giao dịch hợp lệ đưa dữ liệu từ trạng thái thỏa ràng buộc sang trạng thái thỏa ràng buộc | Số lượng tồn kho không được âm |
| **Isolation (cô lập)** | Các giao dịch đồng thời được quan sát theo mức cô lập đã chọn | Hai người không được cùng mua sản phẩm cuối do lỗi cập nhật |
| **Durability (bền vững)** | Một khi giao dịch đã được xác nhận thành công, hệ thống phải giữ được kết quả theo cam kết độ bền của nó | Đơn đã commit vẫn truy xuất được sau khi dịch vụ ứng dụng khởi động lại |

Ví dụ logic đặt một mặt hàng, với các tham số do ứng dụng truyền vào:

~~~sql
BEGIN;

UPDATE products
SET stock_qty = stock_qty - :quantity
WHERE product_id = :productId
  AND stock_qty >= :quantity;

-- Ứng dụng phải kiểm tra số hàng cập nhật bằng 1.
-- Nếu bằng 0, ROLLBACK và báo hết hàng hoặc sản phẩm không tồn tại.

INSERT INTO orders (order_id, customer_id, status)
VALUES (:orderId, :customerId, 'NEW');

INSERT INTO order_items (order_id, product_id, quantity, unit_price_minor)
VALUES (:orderId, :productId, :quantity, :unitPriceMinor);

COMMIT;
~~~

Đây là **mã SQL minh họa luồng giao dịch**: các biến có dấu hai chấm đại diện cho tham số, không phải cú pháp có thể chạy nguyên vẹn trong mọi công cụ SQL. Nếu cập nhật tồn kho không tác động đúng một hàng hoặc bất kỳ lệnh nào lỗi, lớp truy cập dữ liệu phải rollback, không tiếp tục commit. Câu **UPDATE có điều kiện** giúp ngăn việc trừ tồn kho xuống âm ngay cả khi có nhiều giao dịch cùng cạnh tranh.

Giao dịch cơ sở dữ liệu **không tự bao trùm** những tác động bên ngoài như gọi cổng thanh toán, gửi email hoặc ghi vào hệ thống khác. Khi cần kết hợp những thành phần đó, ứng dụng phải thiết kế thêm cơ chế như idempotency, thông điệp đáng tin cậy, transactional outbox hoặc quy trình bù trừ.

### 5.5. Kiểm soát đồng thời: điều gì xảy ra khi nhiều người cùng sửa?

Giả sử sản phẩm có tồn kho bằng 1. Hai request cùng đọc giá trị này, rồi mỗi request đều tính **1 - 1 = 0** và ghi kết quả. Nếu luồng xử lý chỉ dựa vào “đọc rồi ghi”, cả hai có thể cùng nhận thông báo thành công.

Một số cách xử lý:

- **Cập nhật có điều kiện và kiểm tra số hàng cập nhật:** như ví dụ trừ tồn kho ở trên; phù hợp với nhiều thao tác tăng/giảm đơn giản.
- **Khóa bi quan (pessimistic locking):** khóa bản ghi trong khi quyết định cập nhật; cần quản lý thời gian giữ khóa và nguy cơ deadlock.
- **Khóa lạc quan (optimistic locking):** lưu cột phiên bản và chỉ cập nhật nếu phiên bản chưa đổi; khi xung đột thì báo lỗi hoặc thử lại có kiểm soát.
- **Mức cô lập giao dịch:** chọn dựa trên các bất thường cần tránh (dirty read, non-repeatable read, phantom, lost update, write skew…), cùng đặc tính cụ thể của hệ quản trị.

Không nên xem việc “đã bật transaction” là bằng chứng đủ để mọi tình huống cạnh tranh đều an toàn. Một giao dịch vẫn có thể đọc dữ liệu cũ hoặc gặp xung đột tùy mức cô lập và kiểu truy vấn.

## 6. Chọn nơi lưu trữ: bắt đầu từ nhu cầu, không bắt đầu từ công nghệ

Persistence có nhiều cách hiện thực; không có một loại lưu trữ tối ưu cho tất cả dữ liệu.

| Cơ chế | Điểm mạnh tiêu biểu | Phù hợp khi | Điều cần cân nhắc |
| --- | --- | --- | --- |
| **Tệp cục bộ** (CSV, JSON, nhị phân…) | Đơn giản, dễ mang theo, dễ kiểm tra với dữ liệu nhỏ | Cấu hình, công cụ cá nhân, xuất dữ liệu, ứng dụng một tiến trình | Ghi đồng thời, khóa tệp, ghi nguyên tử, đồng bộ xuống thiết bị và sao lưu |
| **CSDL quan hệ** (PostgreSQL, MySQL…) | Lược đồ, truy vấn linh hoạt, ràng buộc và giao dịch | Đơn hàng, tài khoản, tài chính, quan hệ dữ liệu rõ ràng | Thiết kế schema, migration, chỉ mục, chi phí vận hành |
| **Document database** | Lưu và truy vấn tài liệu có cấu trúc lồng nhau | Dữ liệu tài liệu, mô hình đọc theo aggregate | Ràng buộc và giao dịch phụ thuộc sản phẩm; quản lý trùng lặp |
| **Key–value store có lưu bền** | Tra cứu nhanh theo khóa | Session cần lưu giữ, cấu hình phân tán, tra cứu theo ID | Mức độ bền, khả năng truy vấn và cách cấu hình tùy sản phẩm |
| **Object storage** | Lưu đối tượng lớn với độ bền theo dịch vụ | Ảnh, video, tài liệu, bản xuất hoặc bản sao lưu | Không thay thế truy vấn quan hệ và giao dịch nhiều bản ghi |
| **Append-only/event log** | Giữ lịch sử sự kiện, thuận lợi cho phát lại hoặc tích hợp | Audit, xử lý sự kiện, kiến trúc event-driven | Thiết kế idempotency, thứ tự sự kiện, xây dựng trạng thái hiện tại |

Ngay cả **tệp** cũng có thể là persistence nếu được ghi đúng cách và tồn tại sau khi tiến trình dừng. Ngược lại, sử dụng một hệ quản trị cơ sở dữ liệu không bảo đảm an toàn nếu ứng dụng ghi sai giao dịch, quyền truy cập quá rộng hoặc không có chiến lược khôi phục.

Nên bắt đầu bằng các câu hỏi:

1. Dữ liệu nào cần truy vấn? Truy vấn theo khóa hay lọc, sắp xếp, kết hợp nhiều bảng?
2. Một thay đổi phải tác động lên bao nhiêu đối tượng cùng lúc?
3. Mức độ nhất quán, độ trễ, thông lượng và khả năng hoạt động khi mất mạng cần đến đâu?
4. Dự kiến có bao nhiêu dữ liệu, người ghi đồng thời và nhu cầu phân vùng hoặc mở rộng?
5. Hệ thống được phép mất tối đa bao nhiêu dữ liệu và gián đoạn bao lâu?
6. Ai có quyền đọc, sửa, xóa dữ liệu và dữ liệu phải được lưu giữ trong thời gian nào?

## 7. Ranh giới persistence trong ứng dụng Java

Một thiết kế dễ kiểm thử thường để **logic nghiệp vụ** gọi một hợp đồng truy cập dữ liệu, trong khi lớp hạ tầng quyết định dùng JDBC, JPA hay công nghệ lưu trữ cụ thể. Ví dụ:

~~~java
import java.sql.SQLException;
import java.util.UUID;

record CreateOrder(
        UUID orderId,
        long customerId,
        long productId,
        int quantity) {}

interface OrderRepository {
    // Lưu đơn và thay đổi tồn kho trong cùng ranh giới giao dịch.
    void createAtomically(CreateOrder command) throws SQLException;

    // Dùng để kiểm tra lại kết quả khi phản hồi ghi bị gián đoạn.
    boolean exists(UUID orderId) throws SQLException;
}

final class CheckoutService {
    private final OrderRepository orders;

    CheckoutService(OrderRepository orders) {
        this.orders = orders;
    }

    void placeOrder(CreateOrder command) throws SQLException {
        if (command.orderId() == null
                || command.customerId() <= 0
                || command.productId() <= 0
                || command.quantity() <= 0) {
            throw new IllegalArgumentException("Thông tin đặt hàng không hợp lệ");
        }

        orders.createAtomically(command);
    }
}
~~~

Đây là ví dụ về **ranh giới trách nhiệm**, chưa phải một chương trình thương mại điện tử hoàn chỉnh. Triển khai của **OrderRepository** có thể dùng **DataSource** và JDBC với **Connection**, **PreparedStatement**, **commit/rollback**, hoặc dùng một framework quản lý giao dịch. Điều quan trọng là nơi quyết định **giao dịch bắt đầu/kết thúc** phải bao trùm đầy đủ các ghi cần tính nguyên tử.

Một số quy tắc thiết kế hữu ích:

- Để nghiệp vụ làm việc với khái niệm đơn hàng và thao tác “tạo đơn”, hạn chế đưa SQL hoặc chi tiết kết nối vào controller.
- Dùng truy vấn tham số hóa (**PreparedStatement** trong JDBC), không ghép chuỗi trực tiếp từ đầu vào của người dùng thành câu SQL.
- Quản lý vòng đời kết nối bằng **try-with-resources** hoặc cơ chế tương đương; dùng connection pool khi phục vụ nhiều request.
- Phân biệt **lỗi nghiệp vụ** (hết hàng, dữ liệu không hợp lệ) với **lỗi hạ tầng** (hết kết nối, timeout, database tạm ngừng).
- Xác định rõ ai chịu trách nhiệm thử lại, giới hạn số lần và cách tránh tạo dữ liệu trùng.
- Không giấu lỗi ghi bằng cách trả về thành công giả; các thao tác bị gián đoạn cần kết quả có thể kiểm tra.

### Nếu kết nối đứt đúng lúc commit thì sao?

Một trường hợp khó là ứng dụng gửi lệnh commit nhưng mất kết nối trước khi nhận câu trả lời. Lúc đó có thể xảy ra hai khả năng: giao dịch đã được database commit, hoặc chưa được commit. Chỉ từ lỗi mạng, chương trình **không thể luôn kết luận** trường hợp nào đã xảy ra.

Nếu cứ tạo đơn mới mỗi lần retry, khách hàng có thể có hai đơn. Một thiết kế an toàn hơn là giữ **orderId** hoặc **idempotency key** ổn định cho cùng một yêu cầu nghiệp vụ, lưu nó với ràng buộc duy nhất rồi tra cứu trạng thái trước khi quyết định thử lại. Ràng buộc duy nhất là cơ sở ngăn ghi trùng; ứng dụng vẫn phải định nghĩa cách phản hồi khi phát hiện yêu cầu đã tồn tại.

## 8. Các sự cố cần dự liệu ngay từ đầu

| Tình huống | Rủi ro | Biện pháp thiết kế thường dùng |
| --- | --- | --- |
| Ứng dụng restart sau khi ghi | Dữ liệu chỉ có trong RAM bị mất | Lưu tại kho bền vững; xác định rõ điểm hoàn tất ghi |
| Một câu lệnh lỗi sau các câu lệnh khác | Đơn đã tạo nhưng kho chưa cập nhật hoặc ngược lại | Giao dịch và rollback đầy đủ |
| Hai request sửa cùng một bản ghi | Ghi đè, bán quá số lượng, cập nhật bị mất | Ràng buộc, câu lệnh cập nhật có điều kiện, khóa/phiên bản, mức cô lập phù hợp |
| Timeout khi ghi | Không rõ giao dịch đã commit hay chưa | Mã yêu cầu duy nhất, truy vấn trạng thái, retry có idempotency |
| Database tạm dừng hoặc kết nối hết hạn | Request thất bại, tài nguyên bị giữ lâu | Timeout rõ ràng, pool được cấu hình, retry giới hạn cho lỗi có thể phục hồi |
| Đĩa đầy hoặc thiết bị hỏng | Ghi thất bại, có thể mất dữ liệu | Cảnh báo dung lượng, giám sát, dự phòng, backup và diễn tập restore |
| Thao tác xóa hoặc migration nhầm | Mất hoặc sai dữ liệu trên diện rộng | Sao lưu, kiểm soát quyền, migration có kế hoạch và phục hồi được |
| Rò rỉ thông tin nhạy cảm | Lộ dữ liệu khách hàng | Giới hạn quyền, mã hóa phù hợp, quản lý bí mật, che dữ liệu trong log |

**Retry không phải lúc nào cũng an toàn.** Với thao tác đọc thường có thể thử lại dễ dàng hơn; với thao tác tạo đơn, trừ tiền hay gửi thông báo, thử lại không kiểm soát có thể nhân đôi tác động. Ngoài ra, retry dồn dập khi database đang quá tải có thể làm sự cố nghiêm trọng hơn. Cần dùng thời gian chờ hợp lý, số lần thử giới hạn và khoảng nghỉ có điều chỉnh.

## 9. Dữ liệu tồn tại lâu hơn mã nguồn: schema, bảo mật và sao lưu

### 9.1. Tiến hóa schema

Giả sử phiên bản mới bổ sung trường **delivery_note** cho đơn hàng. Một cách triển khai tương thích với bản cũ có thể gồm:

1. Thêm cột cho phép **NULL** hoặc có giá trị mặc định phù hợp.
2. Triển khai ứng dụng đọc được dữ liệu cũ và mới, đồng thời bắt đầu ghi trường mới.
3. Chuyển đổi dữ liệu cũ theo lô nếu nghiệp vụ cần.
4. Sau khi xác nhận dữ liệu và ứng dụng đều tương thích, mới siết ràng buộc hoặc loại bỏ cột cũ.

Quy trình này thường gọi là **expand–migrate–contract**. Mục tiêu là tránh tình huống phiên bản ứng dụng đang chạy đọc không được schema vừa cập nhật. Migration cần được quản lý phiên bản, chạy có kiểm soát và có kế hoạch khôi phục khi thất bại.

### 9.2. Bảo mật và quyền truy cập

Dữ liệu lưu bền vững thường gắn với thông tin khách hàng, giao dịch và lịch sử hoạt động. Cần xác định người và dịch vụ nào được phép đọc hoặc ghi từng nhóm dữ liệu. Một số thực hành cơ bản là:

- Cấp **quyền tối thiểu** cho tài khoản ứng dụng và tách quyền vận hành/migration khi có thể.
- Bảo vệ kết nối bằng TLS khi phù hợp; mã hóa dữ liệu lưu trữ và bản sao lưu theo mức nhạy cảm.
- Lưu thông tin xác thực trong hệ thống quản lý bí mật, không ghi mật khẩu vào source code.
- Kiểm tra dữ liệu đầu vào, sử dụng truy vấn tham số hóa và không ghi thông tin nhạy cảm nguyên văn vào log.
- Có chính sách lưu giữ, xóa và kiểm toán phù hợp với yêu cầu nghiệp vụ và pháp lý.

### 9.3. Sao lưu, khôi phục và khả năng phục vụ

**Backup** chỉ thật sự hữu ích khi có thể **restore**. Hai chỉ số giúp thảo luận yêu cầu phục hồi:

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa có thể chấp nhận, thường đo bằng khoảng thời gian. Ví dụ RPO 15 phút nghĩa là kế hoạch phục hồi phải nhắm đến mất không quá khoảng 15 phút dữ liệu.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ sau sự cố. Ví dụ RTO 1 giờ nghĩa là mục tiêu đưa dịch vụ vận hành lại trong vòng 1 giờ.

Để đạt những mục tiêu này có thể cần kết hợp backup định kỳ, lưu nhật ký thay đổi, replication, hạ tầng dự phòng, giám sát và diễn tập phục hồi. Replication hỗ trợ khi nút hỏng, nhưng không thay thế bản sao lưu độc lập nếu dữ liệu bị xóa nhầm hoặc bị sửa sai rồi đồng bộ sang các nút khác.

## 10. Hiệu năng: lưu đúng rồi mới tối ưu cách lưu

Khi tăng quy mô, lớp persistence thường trở thành điểm nghẽn do truy vấn, kết nối hoặc cạnh tranh ghi. Những hướng quan sát và cải thiện gồm:

| Dấu hiệu | Điều nên kiểm tra |
| --- | --- |
| Trang danh sách đơn hàng tải chậm | Điều kiện lọc, sắp xếp, kế hoạch truy vấn, chỉ mục, phân trang |
| Một màn hình gây ra rất nhiều query nhỏ | Hiện tượng **N+1 query**; cân nhắc batch, join hoặc thay đổi cách lấy dữ liệu |
| Hết kết nối vào giờ cao điểm | Kích thước pool, thời gian giữ connection, giao dịch quá dài, giới hạn database |
| Ghi chậm khi có nhiều người mua | Tranh chấp trên bản ghi nóng, khóa, deadlock, chiến lược cập nhật |
| Dữ liệu tăng nhanh | Lưu giữ, phân vùng, lưu trữ lịch sử, kích thước chỉ mục và backup |

Một chỉ mục hoặc bộ nhớ đệm có thể giúp một đường truy vấn, nhưng cũng có chi phí. Cần đo **độ trễ theo percentile**, thông lượng, tỉ lệ lỗi, thời gian chờ kết nối và các truy vấn chậm thay vì tối ưu chỉ vì dự đoán. Cache có thể làm dữ liệu trả về cũ hơn nguồn chính; phải thống nhất yêu cầu nhất quán trước khi thêm cache.

## 11. Nhìn toàn bộ vòng đời một bản ghi

Lấy ví dụ một đơn hàng:

~~~mermaid
flowchart LR
    A["Tạo đơn"] --> B["Ghi theo giao dịch"]
    B --> C["Đọc và cập nhật trạng thái"]
    C --> D["Hoàn tất / hủy"]
    D --> E["Lưu giữ lịch sử"]
    E --> F["Lưu trữ hoặc xóa theo chính sách"]
    B -. "Sao lưu và phục hồi" .-> G["Bản sao phục hồi"]
    C -. "Sao lưu và phục hồi" .-> G
    E -. "Sao lưu và phục hồi" .-> G
~~~

Ở mỗi giai đoạn, hãy hỏi:

- **Ghi:** thao tác nào phải nguyên tử, ai được phép ghi, khi nào trả thành công?
- **Đọc:** cần xem dữ liệu mới nhất hay chấp nhận đọc chậm hơn một chút; có cần phân trang không?
- **Cập nhật:** làm gì khi hai người thay đổi cùng một bản ghi?
- **Lưu giữ:** dữ liệu cần tồn tại bao lâu, có cần phục vụ kiểm toán hay báo cáo?
- **Phục hồi:** sẽ xảy ra điều gì khi dịch vụ, kết nối hoặc thiết bị gặp sự cố?
- **Thay đổi phiên bản:** liệu ứng dụng mới và cũ có đọc được cùng dữ liệu trong giai đoạn triển khai?

Những câu hỏi này phản ánh phạm vi thực tế của persistence: từ **mô hình, schema, truy vấn, chỉ mục** tới **giao dịch, cô lập, xử lý kết nối, tiến hóa dữ liệu, bảo mật, sao lưu và hiệu năng**.

## 12. Tự đánh giá một thiết kế persistence ban đầu

Trước khi xem một chức năng là sẵn sàng vận hành, có thể dùng danh sách kiểm tra ngắn sau:

- [ ] Đã xác định dữ liệu nào là trạng thái cần lưu bền vững và ai là nguồn sự thật của nó.
- [ ] Đã có định danh rõ ràng, kiểu dữ liệu hợp lý và ràng buộc ngăn trạng thái sai.
- [ ] Đã xác định các thao tác ghi cần cùng một giao dịch và quy tắc xử lý cạnh tranh.
- [ ] Đã phân biệt lỗi nghiệp vụ, lỗi kết nối và kết quả ghi chưa xác định.
- [ ] Đã có chiến lược idempotency hoặc kiểm tra trạng thái cho thao tác có thể bị gửi lại.
- [ ] Đã biết những truy vấn chính, nhu cầu phân trang và cách đo hiệu năng.
- [ ] Đã dự kiến migration khi schema thay đổi.
- [ ] Đã xác định quyền truy cập, bảo vệ dữ liệu nhạy cảm và chính sách lưu giữ.
- [ ] Đã xác định mục tiêu phục hồi và kiểm chứng khả năng khôi phục từ bản sao lưu.

## 13. Kết luận

Lưu trữ bền vững là nền tảng để một ứng dụng **nhớ được những điều đã xảy ra** và tiếp tục hoạt động đúng khi người dùng quay lại, server khởi động lại hoặc nhiều thao tác diễn ra đồng thời. Chọn được nơi ghi dữ liệu chỉ là điểm khởi đầu; một thiết kế persistence tốt còn định nghĩa dữ liệu hợp lệ, cách cập nhật nhất quán, cách đọc hiệu quả và khả năng phục hồi khi có sự cố.

Với ứng dụng Java, hãy bắt đầu bằng **ranh giới nghiệp vụ và hợp đồng truy cập dữ liệu**, sau đó chọn công nghệ, schema, giao dịch và cơ chế vận hành đáp ứng các yêu cầu đó. Cách tiếp cận này giúp persistence phục vụ tính đúng đắn lâu dài của hệ thống, thay vì trở thành tập hợp các lệnh đọc và ghi rời rạc.
