# Đánh đổi giữa tính đúng, khả năng thay đổi, hiệu năng và độ phức tạp

Một mô hình dữ liệu tốt giúp hệ thống lưu đúng điều nghiệp vụ cần nhớ, truy vấn được trong thời gian chấp nhận được và thay đổi được khi quy trình phát triển. Tuy nhiên, bốn mục tiêu này thường kéo theo những lựa chọn khác nhau. Chuẩn hóa giúp giảm dữ liệu trùng lặp và tránh cập nhật mâu thuẫn, nhưng có thể làm truy vấn cần nhiều phép nối hơn. Lưu sẵn dữ liệu tổng hợp có thể tăng tốc đọc, nhưng tạo thêm trách nhiệm đồng bộ. Một lược đồ rất linh hoạt có thể tiếp nhận nhiều dạng dữ liệu, nhưng khiến việc kiểm tra và hiểu dữ liệu khó hơn.

Trong phạm vi **data modeling**, công việc của người thiết kế là chuyển yêu cầu nghiệp vụ thành thực thể, quan hệ, thuộc tính, khóa, ràng buộc và cấu trúc lưu trữ. Mô hình cần thể hiện đúng ý nghĩa dữ liệu, hỗ trợ các thao tác quan trọng và có đường tiến hóa rõ ràng. Không có một cấu trúc luôn tối ưu cho mọi hệ thống; lựa chọn hợp lý phụ thuộc vào bất biến nghiệp vụ, kiểu truy vấn, tốc độ thay đổi và năng lực vận hành của nhóm.

Bài học này dùng một hệ thống bán hàng làm ví dụ xuyên suốt để phân tích cách cân bằng tính đúng, khả năng thay đổi, hiệu năng và độ phức tạp; đồng thời so sánh mô hình quan hệ, document, đồ thị và phân tích.

## 1. Bốn mục tiêu cần cân bằng

| Mục tiêu | Câu hỏi cần trả lời | Dấu hiệu thiết kế tốt |
|---|---|---|
| Tính đúng | Dữ liệu có phản ánh đúng sự thật và quy tắc nghiệp vụ không? | Bất biến được thể hiện rõ; dữ liệu không hợp lệ bị chặn; giao dịch giữ được tính nhất quán |
| Khả năng thay đổi | Khi nghiệp vụ thay đổi, có thể tiến hóa mô hình mà không làm hỏng dữ liệu và hệ thống đang dùng không? | Ranh giới dữ liệu rõ; thay đổi có thể triển khai theo từng bước; lịch sử được giữ đúng ý nghĩa |
| Hiệu năng | Các thao tác quan trọng có đáp ứng độ trễ, thông lượng và chi phí tài nguyên mong muốn không? | Truy vấn phù hợp với mẫu truy cập; chỉ mục có chủ đích; phép đo xác nhận nút thắt |
| Độ phức tạp | Nhóm có hiểu, kiểm thử, triển khai và vận hành được cấu trúc này không? | Ít quy tắc ngầm; một nguồn sự thật dễ nhận biết; cơ chế đồng bộ và khôi phục có thể giải thích |

Các mục tiêu có quan hệ với nhau. Tính đúng là điều kiện nền tảng: một truy vấn nhanh nhưng trả về giá sai vẫn là lỗi. Khả năng thay đổi giúp hệ thống sống được qua nhiều phiên bản nghiệp vụ. Hiệu năng quyết định hệ thống có phục vụ được tải thực tế hay không. Độ phức tạp giới hạn số cơ chế mà nhóm có thể duy trì an toàn.

Không nên hiểu cân bằng là chia đều sự ưu tiên. Với hệ thống thanh toán, tính đúng và khả năng kiểm toán thường được ưu tiên cao hơn việc giảm vài mili giây. Với hệ thống gợi ý sản phẩm, một số dữ liệu có thể chấp nhận trễ cập nhật để đổi lấy khả năng đọc nhanh. Với một công cụ nội bộ ít người dùng, một truy vấn đơn giản có thể tốt hơn việc bổ sung tầng cache và quy trình đồng bộ.

## 2. Bắt đầu từ quy tắc nghiệp vụ

Thiết kế lược đồ bằng cách liệt kê bảng trước thường dẫn đến việc mô hình hóa theo thói quen của công nghệ. Hãy bắt đầu bằng câu hỏi hệ thống cần ghi nhớ điều gì, ai sở hữu dữ liệu đó, dữ liệu thay đổi khi nào và những điều kiện nào luôn phải đúng.

Với hệ thống bán hàng, một số quy tắc có thể là:

- Một khách hàng có thể tạo nhiều đơn hàng; mỗi đơn hàng thuộc về đúng một khách hàng.
- Một đơn hàng có ít nhất một dòng hàng trước khi được xác nhận.
- Số lượng của một dòng hàng phải là số nguyên dương.
- Đơn giá tại thời điểm mua phải được giữ lại, kể cả khi giá hiện tại của sản phẩm thay đổi.
- Mỗi đơn hàng dùng một loại tiền tệ xác định; không cộng các khoản tiền khác loại nếu chưa quy đổi.
- Đơn hàng đã thanh toán không được âm thầm thay đổi thành một giao dịch khác.
- Hai yêu cầu đồng thời không được làm số lượng tồn kho giảm xuống dưới không.

Những câu này chứa nhiều thông tin thiết kế hơn tên bảng. Chúng chỉ ra thực thể, quan hệ, vòng đời, dữ liệu lịch sử và ràng buộc. Chúng cũng giúp phân biệt dữ liệu hiện tại với dữ liệu đã được chốt tại một thời điểm.

### 2.1. Từ khái niệm đến lược đồ

Nên phân biệt ba mức mô hình:

1. **Mô hình khái niệm** mô tả khái niệm nghiệp vụ và quan hệ giữa chúng, chưa phụ thuộc vào hệ quản trị cơ sở dữ liệu.
2. **Mô hình logic** xác định thuộc tính, khóa, quan hệ, lực lượng quan hệ và các quy tắc dữ liệu. Ở mức này có thể quyết định chuẩn hóa và ranh giới aggregate.
3. **Mô hình vật lý** chọn kiểu dữ liệu, chỉ mục, phân vùng, cách lưu trữ và các chi tiết triển khai theo hệ quản trị cụ thể.

Không nên đưa quyết định vật lý quá sớm vào mô hình khái niệm. Ví dụ, nghiệp vụ có khái niệm “đơn hàng” dù dữ liệu cuối cùng được lưu trong một số bảng quan hệ hay trong một document. Ngược lại, một mô hình logic đúng vẫn cần được điều chỉnh ở mức vật lý khi có số liệu về tải và truy vấn.

### 2.2. Thực thể, quan hệ và vòng đời

Sơ đồ khái niệm đơn giản có thể biểu diễn như sau:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
    CUSTOMER {
        bigint customer_id
        string email
    }
    ORDER {
        bigint order_id
        bigint customer_id
        string status
        datetime created_at
    }
    ORDER_ITEM {
        bigint order_id
        int line_no
        bigint product_id
        int quantity
        decimal unit_price_snapshot
    }
    PRODUCT {
        bigint product_id
        string sku
        decimal current_price
    }
~~~

Đơn hàng và dòng hàng có quan hệ một-nhiều. Dòng hàng không có ý nghĩa độc lập khi không thuộc đơn hàng, nên khóa của nó có thể bao gồm mã đơn hàng và số thứ tự dòng. Sản phẩm có thể được tham chiếu bởi nhiều dòng hàng, nhưng thông tin tên và giá tại thời điểm đặt hàng cần được chụp lại trong dòng hàng để lịch sử đơn hàng không đổi theo danh mục sản phẩm hiện tại.

Lực lượng quan hệ phải được suy ra từ nghiệp vụ. Không nên đặt một-một chỉ vì hiện tại giao diện chỉ cho nhập một địa chỉ. Nếu khách hàng có thể lưu nhiều địa chỉ trong tương lai, địa chỉ giao hàng đã chọn vẫn cần được chụp thành bản sao lịch sử trên đơn hàng; địa chỉ trong hồ sơ khách hàng là dữ liệu có thể chỉnh sửa.

## 3. Bảo vệ tính đúng bằng cấu trúc dữ liệu

Tính đúng không nên chỉ dựa vào lời hứa của mã ứng dụng. Mỗi quy tắc nên được đặt ở lớp có đủ thông tin và có thể bảo vệ nó trước mọi đường ghi dữ liệu.

### 3.1. Khóa và ràng buộc

Các ràng buộc phổ biến có vai trò khác nhau:

- **Primary key** xác định duy nhất một bản ghi và không được rỗng.
- **Foreign key** bảo vệ quan hệ tham chiếu, ngăn bản ghi trỏ đến đối tượng không tồn tại.
- **Unique constraint** ngăn hai bản ghi có cùng giá trị ở một khóa ứng viên, chẳng hạn email đăng nhập sau khi chuẩn hóa.
- **Not null** yêu cầu thuộc tính phải có giá trị.
- **Check constraint** kiểm tra điều kiện trên một hàng, chẳng hạn số lượng phải lớn hơn không.

Ví dụ, cơ sở dữ liệu quan hệ có thể biểu diễn một phần quy tắc của đơn hàng bằng SQL:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE
);

CREATE TABLE products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    current_price NUMERIC(14, 2) NOT NULL
        CHECK (current_price >= 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (stock_quantity >= 0)
);

CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES customers(id) ON DELETE RESTRICT,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'confirmed', 'paid', 'cancelled')),
    currency CHAR(3) NOT NULL,
    grand_total NUMERIC(14, 2) NOT NULL
        CHECK (grand_total >= 0),
    ship_to_name TEXT NOT NULL,
    ship_to_address TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL
        REFERENCES orders(id) ON DELETE RESTRICT,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT
        REFERENCES products(id) ON DELETE RESTRICT,
    product_name_snapshot TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_snapshot NUMERIC(14, 2) NOT NULL
        CHECK (unit_price_snapshot >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Ví dụ dùng kiểu tiền tệ có hai chữ số thập phân để dễ đọc. Hệ thống đa tiền tệ phải quy định chính xác số chữ số thập phân, quy tắc làm tròn và cách lưu số tiền theo từng loại tiền; không được giả định mọi loại tiền đều có cùng đơn vị nhỏ nhất.

Khóa chính thay thế như số nguyên tăng dần giúp quan hệ ổn định khi thuộc tính nghiệp vụ thay đổi. Khóa tự nhiên như email hoặc mã SKU vẫn có thể cần ràng buộc duy nhất, nhưng không nhất thiết phải dùng làm khóa tham chiếu. Nếu email thay đổi, khóa khách hàng không cần thay đổi theo.

Khóa ghép cũng có ý nghĩa nghiệp vụ. Trong ví dụ, cặp (order_id, line_no) định danh một dòng trong phạm vi đơn hàng. Khóa này diễn đạt rõ phạm vi duy nhất và tự tạo chỉ mục bắt đầu bằng order_id trong nhiều hệ quản trị.

### 3.2. Ràng buộc phải đặt đúng nơi

Check constraint thường kiểm tra được thuộc tính của cùng một hàng. Nó không tự bảo đảm một quy tắc cần so sánh nhiều hàng hoặc nhiều bảng, chẳng hạn tổng tiền đơn hàng bằng tổng các dòng hàng cộng thuế và phí. Quy tắc liên hàng cần được bảo vệ bằng thiết kế giao dịch, khóa phù hợp, trigger khi thực sự cần hoặc một mô hình sổ ghi nhận có thể đối soát.

Một quy tắc quan trọng phải chịu được nhiều tiến trình ghi đồng thời. Ví dụ, nếu hai khách hàng cùng mua sản phẩm còn một đơn vị, cách đọc tồn kho rồi trừ ở hai bước riêng có thể khiến cả hai yêu cầu cùng thấy số lượng là một. Hãy dùng thao tác cập nhật có điều kiện trong một câu lệnh nguyên tử:

~~~sql
UPDATE products
SET stock_quantity = stock_quantity - :requested_quantity
WHERE id = :product_id
  AND stock_quantity >= :requested_quantity;
~~~

Ứng dụng kiểm tra số hàng được cập nhật. Nếu bằng không, sản phẩm không tồn tại hoặc không đủ hàng. Điều kiện kiểm tra và phép trừ được thực hiện cùng nhau, tránh khoảng trống giữa lần đọc và lần ghi. Với quy trình nhiều bước, cần đặt các thao tác liên quan trong transaction và chọn mức cô lập hoặc khóa phù hợp.

Unique constraint cũng là hàng rào cuối cùng trước hai yêu cầu đồng thời tạo cùng một tài khoản. Kiểm tra trước bằng câu SELECT trong ứng dụng không đủ, vì hai yêu cầu có thể cùng kiểm tra thấy chưa tồn tại rồi cùng chèn. Cơ sở dữ liệu phải thực thi tính duy nhất.

### 3.3. NULL và ý nghĩa của dữ liệu

NULL biểu thị thiếu hoặc chưa biết giá trị, không đồng nghĩa với chuỗi rỗng, số không hay trạng thái “không áp dụng”. Mỗi thuộc tính cần có quy tắc rõ: có bắt buộc không, khi nào chưa có giá trị, và một giá trị thiếu có ý nghĩa gì.

NULL cũng ảnh hưởng đến so sánh và ràng buộc. Trong SQL, biểu thức so sánh với NULL thường cho kết quả UNKNOWN; phải dùng IS NULL hoặc IS NOT NULL. Hành vi UNIQUE với nhiều giá trị NULL khác nhau có thể phụ thuộc hệ quản trị và cấu hình. Vì vậy, các quy tắc về tính duy nhất khi thiếu dữ liệu phải được kiểm tra theo hệ quản trị thực tế.

Không nên biến một trường thành nơi chứa nhiều ý nghĩa. Ví dụ, dùng chuỗi rỗng để thay cho “chưa giao”, “khách không cung cấp” và “không cần giao” khiến truy vấn và báo cáo phải đoán ý định. Có thể cần trạng thái riêng hoặc một cấu trúc biểu diễn rõ ràng hơn.

## 4. Chuẩn hóa và phi chuẩn hóa

Chuẩn hóa tổ chức dữ liệu để giảm lặp lại và tránh các bất thường khi thêm, sửa hoặc xóa. Đây là điểm xuất phát hữu ích cho mô hình quan hệ.

Giả sử mỗi dòng hàng lưu cả email khách hàng, tên sản phẩm, địa chỉ khách hàng và giá hiện tại của sản phẩm. Khi email thay đổi, nhiều dòng lịch sử phải được cập nhật. Nếu một sản phẩm chưa từng được đặt hàng, ta không có nơi phù hợp để lưu thông tin của nó trong bảng đơn hàng. Khi xóa dòng hàng cuối cùng của một sản phẩm, dữ liệu sản phẩm có thể vô tình biến mất. Đây là các dạng bất thường do trộn nhiều khái niệm vào cùng một cấu trúc.

Các mức chuẩn hóa thường gặp:

- **1NF**: mỗi ô chứa một giá trị theo miền dữ liệu đã định nghĩa; không nhét danh sách không cấu trúc vào một cột để thay thế quan hệ.
- **2NF**: thuộc tính không khóa phụ thuộc đầy đủ vào toàn bộ khóa ứng viên, đặc biệt quan trọng khi khóa là khóa ghép.
- **3NF**: thuộc tính không khóa không phụ thuộc bắc cầu vào khóa thông qua một thuộc tính không khóa khác.

Ví dụ, tên sản phẩm và giá hiện tại thuộc về sản phẩm, không phụ thuộc vào từng dòng hàng. Chúng nên nằm ở thực thể sản phẩm. Tuy nhiên, tên sản phẩm và giá đã áp dụng tại thời điểm mua là một sự thật lịch sử khác; lưu snapshot trong dòng hàng không phải là lặp dữ liệu vô nghĩa. Hai trường có ý nghĩa và vòng đời khác nhau.

### 4.1. Khi nào nên phi chuẩn hóa?

Phi chuẩn hóa là chủ động lưu thêm dữ liệu đã có thể suy ra ở nơi khác để phục vụ mẫu truy cập quan trọng. Một số trường hợp:

- Lưu tổng tiền đã chốt trên đơn hàng để hiển thị và đối soát nhanh.
- Lưu số lượng đơn hàng trên hồ sơ khách hàng để tránh tổng hợp lặp lại ở một màn hình có tải đọc cao.
- Lưu bản sao tên hoặc địa chỉ tại thời điểm giao dịch để bảo toàn lịch sử.
- Gom các mục thường được đọc cùng nhau vào một document để giảm số lần truy vấn.

Mỗi bản sao tạo thêm một câu hỏi: khi dữ liệu gốc thay đổi, bản sao có phải thay đổi không? Nếu có, ai cập nhật, cập nhật trong cùng transaction hay bất đồng bộ, xử lý thế nào khi cập nhật thất bại, và làm sao phát hiện sai lệch?

Không phải mọi bản sao đều cần đồng bộ. Snapshot lịch sử cố ý giữ giá trị cũ sau khi dữ liệu nguồn thay đổi. Tổng tiền đã chốt cũng là một phần của sự kiện đơn hàng, không phải lúc nào cũng nên tính lại từ giá sản phẩm hiện tại. Ngược lại, số lượng đơn hàng hiển thị trên hồ sơ khách hàng là dữ liệu tổng hợp có thể được tái tạo từ các đơn hàng; nếu lưu sẵn, phải xác định cách cập nhật và đối soát.

Một nguyên tắc hữu ích là phân loại rõ:

| Loại dữ liệu | Ví dụ | Quy tắc cập nhật |
|---|---|---|
| Dữ liệu gốc hiện tại | Giá niêm yết của sản phẩm | Cập nhật theo vòng đời sản phẩm |
| Snapshot lịch sử | Đơn giá trong đơn hàng đã xác nhận | Giữ nguyên theo sự kiện đã xảy ra |
| Dữ liệu dẫn xuất | Tổng số đơn hàng của khách | Tính lại được; nếu lưu sẵn thì cần đồng bộ hoặc đối soát |
| Cache tạm thời | Kết quả truy vấn phổ biến | Có thể hết hạn và tái tạo theo chính sách rõ ràng |

Phi chuẩn hóa hợp lý khi lợi ích truy cập đã được đo hoặc yêu cầu nghiệp vụ đòi hỏi snapshot. Nếu chưa biết truy vấn nào chậm, hãy bắt đầu với mô hình rõ ràng, chuẩn hóa hợp lý và thêm tối ưu sau khi đo.

## 5. Hiệu năng bắt đầu từ mẫu truy cập

Hiệu năng không chỉ là số lượng bảng hay số phép JOIN. Một mô hình có nhiều bảng vẫn có thể nhanh khi chỉ mục và truy vấn phù hợp. Một document lớn có thể chậm khi phải đọc nhiều dữ liệu không dùng đến hoặc cập nhật một phần nhỏ của document rất thường xuyên.

Trước khi tối ưu, hãy xác định:

- Các truy vấn chính là gì: tìm theo mã, lọc theo trạng thái, xem lịch sử, tổng hợp hay tìm đường quan hệ?
- Tần suất đọc và ghi của từng loại thao tác?
- Dữ liệu có tăng đều hay có một số khóa nóng?
- Độ trễ mục tiêu và mức tải đồng thời?
- Dữ liệu nào phải nhất quán ngay lập tức, dữ liệu nào có thể cập nhật trễ?

### 5.1. Chỉ mục là một đánh đổi

Chỉ mục giúp tìm hàng mà không phải quét toàn bộ bảng, nhưng cần dung lượng lưu trữ và phải được cập nhật khi dữ liệu thay đổi. Quá nhiều chỉ mục làm tăng chi phí ghi, kéo dài bảo trì và có thể khiến bộ tối ưu hóa khó chọn kế hoạch phù hợp.

Ví dụ, nếu màn hình thường hiển thị đơn hàng mới nhất của một khách hàng, chỉ mục ghép theo khách hàng rồi thời gian tạo có thể hỗ trợ truy vấn:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);
~~~

Thứ tự cột trong chỉ mục ghép quan trọng. Chỉ mục bắt đầu bằng customer_id phù hợp với truy vấn lọc theo customer_id và sắp xếp theo created_at. Nó không nhất thiết tối ưu cho truy vấn chỉ lọc theo created_at. Hãy thiết kế từ điều kiện lọc, thứ tự sắp xếp và các cột cần trả về của truy vấn thực tế.

Không phải mọi cột đều nên có chỉ mục. Cột có ít giá trị khác nhau có thể ít hữu ích nếu đứng riêng; cột được cập nhật liên tục có thể làm chi phí duy trì chỉ mục tăng. Chỉ mục duy nhất vừa hỗ trợ tra cứu vừa thực thi một quy tắc nghiệp vụ, nên có giá trị kép.

Các khóa ngoại không phải lúc nào cũng tự tạo chỉ mục ở bảng tham chiếu. Nếu ứng dụng thường tìm dòng hàng theo product_id hoặc xóa/kiểm tra sản phẩm có dòng hàng tham chiếu, có thể cần chỉ mục riêng trên order_items(product_id). Hãy kiểm tra hành vi của hệ quản trị đang dùng.

Đo kế hoạch thực thi bằng công cụ như EXPLAIN hoặc EXPLAIN ANALYZE trên dữ liệu có kích thước gần thực tế. Một truy vấn chạy nhanh với vài trăm hàng có thể trở thành nút thắt khi có hàng chục triệu hàng. Đừng đánh giá hiệu năng chỉ bằng cảm giác hoặc thời gian chạy trên dữ liệu thử quá nhỏ.

### 5.2. Tối ưu đọc và ghi

Nếu workload đọc nhiều và ghi ít, một số bản sao hoặc chỉ mục bổ sung có thể hợp lý. Nếu dữ liệu được cập nhật liên tục, chi phí duy trì các bản sao và chỉ mục có thể lớn hơn lợi ích đọc.

Tách một document thành nhiều thực thể có thể giảm kích thước cập nhật và giúp tránh tranh chấp khi nhiều tiến trình sửa các phần khác nhau. Ngược lại, gom dữ liệu thuộc cùng một aggregate có thể giảm số lần đọc và giúp thao tác nguyên tử đơn giản hơn.

Cache cũng là một dạng phi chuẩn hóa ở tầng truy cập. Cache giảm tải đọc nhưng tạo thêm vấn đề hết hạn, vô hiệu hóa, dữ liệu cũ và xử lý cache miss. Không nên dùng cache để che một mô hình dữ liệu không rõ ràng trước khi xác định nút thắt thực sự.

## 6. Thiết kế để thay đổi được

Nghiệp vụ thay đổi theo thời gian: một đơn hàng có thể bổ sung mã khuyến mại, nhiều địa chỉ giao hàng, phương thức thanh toán mới hoặc quy tắc thuế khác. Khả năng thay đổi phụ thuộc vào việc mô hình có phân biệt rõ khái niệm, giữ được lịch sử và cho phép triển khai thay đổi theo từng bước.

### 6.1. Tránh mô hình quá cứng hoặc quá tự do

Một bảng có hàng chục cột nullable cho mọi loại đối tượng có thể tạo nhiều trạng thái không hợp lệ. Một cột JSON chứa toàn bộ thuộc tính không có cấu trúc cũng làm khó kiểm tra, lập chỉ mục và phân tích quan hệ. Ở chiều ngược lại, chia mọi thuộc tính thành các bảng key-value tổng quát có thể khiến truy vấn phức tạp và mất ràng buộc kiểu dữ liệu.

Hãy dùng kiểu dữ liệu và quan hệ tường minh cho những khái niệm ổn định, có ý nghĩa nghiệp vụ hoặc cần được truy vấn, ràng buộc thường xuyên. Có thể dùng JSON/document cho phần mở rộng có cấu trúc thay đổi theo loại đối tượng, nhưng cần xác định schema tối thiểu, quy tắc xác thực và cách lập chỉ mục cho các trường được truy vấn.

Đừng dùng một cột trạng thái để mã hóa quá nhiều ý nghĩa. Nếu quy trình có các chuyển trạng thái hợp lệ, hãy xác định state machine: trạng thái nào được chuyển sang trạng thái nào, điều kiện chuyển là gì, và có cần lưu lịch sử chuyển trạng thái hay không. Một danh sách giá trị hợp lệ trong CHECK constraint chỉ chặn được giá trị lạ; nó không tự bảo đảm luồng chuyển trạng thái đúng.

### 6.2. Thay đổi schema theo nhiều bước

Thay đổi một cột đang được ứng dụng sử dụng có thể cần phối hợp giữa phiên bản ứng dụng, cơ sở dữ liệu và dữ liệu cũ. Một chiến lược thường dùng là **expand–migrate–contract**:

1. **Expand**: thêm cấu trúc mới theo cách tương thích, ví dụ thêm cột mới cho phép NULL hoặc thêm bảng mới.
2. **Migrate**: triển khai ứng dụng có thể đọc/ghi theo giai đoạn; backfill dữ liệu cũ theo lô; kiểm tra số liệu và sai lệch.
3. **Switch**: chuyển luồng đọc chính sang cấu trúc mới sau khi dữ liệu đã sẵn sàng.
4. **Contract**: ở lần phát hành sau, ngừng dùng rồi mới xóa cột hoặc đường dẫn cũ khi không còn phiên bản ứng dụng nào phụ thuộc.

Ví dụ, đổi từ full_name sang first_name và last_name không nên lập tức xóa full_name trong khi các phiên bản ứng dụng cũ vẫn đọc trường đó. Có thể thêm hai cột mới, backfill, cập nhật ứng dụng, xác minh rồi mới xóa trường cũ.

Với bảng lớn, migration còn có rủi ro khóa bảng, tăng tải I/O hoặc tạo bản sao dữ liệu lớn. Hãy xem xét tạo chỉ mục theo cách ít chặn ghi nếu hệ quản trị hỗ trợ, backfill theo lô, theo dõi replication lag và có kế hoạch dừng hoặc tiếp tục migration an toàn.

### 6.3. Lịch sử và thời gian

Không phải mọi thuộc tính đều có cùng ý nghĩa theo thời gian. Giá hiện tại của sản phẩm có thể thay đổi; giá đã áp dụng cho đơn hàng cũ phải giữ nguyên. Địa chỉ hồ sơ khách hàng có thể thay đổi; địa chỉ giao hàng của đơn hàng đã gửi phải phản ánh nơi đã giao. Đây là lý do cần phân biệt dữ liệu hiện tại và snapshot lịch sử.

Nếu nghiệp vụ cần biết ai thay đổi điều gì và khi nào, chỉ lưu giá trị mới nhất là chưa đủ. Có thể thêm bảng lịch sử, bảng sự kiện hoặc audit log với người thực hiện, thời điểm, giá trị trước/sau và lý do. Chọn cách lưu theo nhu cầu truy vấn và kiểm toán; không cần biến mọi bảng thành event sourcing nếu hệ thống không cần khả năng phát lại toàn bộ sự kiện.

## 7. Chọn họ mô hình theo bản chất dữ liệu

Mô hình quan hệ, document, đồ thị và phân tích giải quyết các kiểu truy cập khác nhau. Có thể phối hợp nhiều mô hình trong cùng hệ thống, nhưng mỗi bản sao dữ liệu cần có mục đích và nguồn sự thật rõ ràng.

| Mô hình | Phù hợp khi | Điểm mạnh | Chi phí và giới hạn cần cân nhắc |
|---|---|---|---|
| Quan hệ | Dữ liệu có cấu trúc rõ, nhiều quan hệ và ràng buộc; giao dịch cần nhất quán | Khóa, foreign key, transaction và truy vấn kết hợp linh hoạt | Cần thiết kế JOIN, chỉ mục và migration; thay đổi cấu trúc phải được quản lý |
| Document | Dữ liệu thường được đọc/ghi theo một aggregate có cấu trúc lồng nhau | Gom dữ liệu đọc cùng nhau; schema linh hoạt cho phần mở rộng | Dữ liệu lồng nhau có thể bị lặp; cập nhật document lớn và quan hệ xuyên document cần thiết kế cẩn thận |
| Đồ thị | Quan hệ là trọng tâm và cần duyệt nhiều bước hoặc nhiều kiểu liên kết | Biểu diễn nút, cạnh và đường đi tự nhiên | Truy vấn tổng hợp dạng bảng và báo cáo có thể không thuận tiện; cần quản lý loại cạnh và giới hạn duyệt |
| Phân tích | Cần tổng hợp lịch sử lớn theo thời gian, sản phẩm, khu vực hoặc phân khúc | Tối ưu quét và tổng hợp dữ liệu; mô hình fact/dimension dễ dùng cho báo cáo | Thường là dữ liệu dẫn xuất từ hệ thống vận hành; cập nhật có thể trễ và cần quy trình nạp/đối soát |

### 7.1. Mô hình quan hệ

Mô hình quan hệ phù hợp khi tính toàn vẹn giữa nhiều thực thể là quan trọng. Đơn hàng, khách hàng, sản phẩm, thanh toán và tồn kho thường có quan hệ rõ và cần transaction. Việc tách bảng giúp một sự thật được quản lý ở một nơi, còn foreign key và unique constraint bảo vệ các quan hệ.

Nhược điểm thực tế thường đến từ thiết kế truy vấn và vận hành: nhiều JOIN, chỉ mục không phù hợp, migration lớn hoặc transaction giữ khóa quá lâu. Đây là các vấn đề cần đo và xử lý theo workload, không phải lý do tự động từ bỏ mô hình quan hệ.

### 7.2. Mô hình document

Nếu một đơn hàng thường được đọc cùng toàn bộ dòng hàng và địa chỉ giao hàng, có thể lưu đơn hàng như một document:

~~~json
{
  "orderId": "O-1042",
  "customerId": "C-18",
  "status": "paid",
  "currency": "VND",
  "grandTotal": 1250000,
  "shipTo": {
    "name": "Nguyen Van A",
    "address": "12 Example Street"
  },
  "items": [
    {
      "productId": "P-7",
      "productName": "Keyboard",
      "quantity": 1,
      "unitPrice": 1250000
    }
  ]
}
~~~

Các dòng hàng nằm trong document vì chúng thuộc vòng đời của đơn hàng và thường được đọc cùng đơn hàng. Tên và giá được lưu như snapshot. Hồ sơ khách hàng và danh mục sản phẩm vẫn có thể là document riêng vì chúng có vòng đời và cách truy cập riêng.

Embed dữ liệu khi nó thuộc về aggregate, có kích thước giới hạn hợp lý và thường được đọc cùng nhau. Dùng reference khi dữ liệu được chia sẻ, có vòng đời độc lập, có thể lớn không giới hạn hoặc được truy vấn độc lập thường xuyên. Nếu cùng một dữ liệu được embed vào nhiều document và cần cập nhật đồng bộ, chi phí nhất quán có thể tăng nhanh.

Document không đồng nghĩa với không có schema hoặc không có transaction. Hệ thống document vẫn có thể xác thực cấu trúc, lập chỉ mục và hỗ trợ transaction; phạm vi và chi phí của các khả năng đó phụ thuộc sản phẩm cụ thể. Cần đánh giá theo tính năng thật của hệ quản trị được chọn.

### 7.3. Mô hình đồ thị

Mô hình đồ thị phù hợp khi câu hỏi chủ yếu là về đường đi qua quan hệ. Ví dụ: tìm người dùng có liên hệ với một tài khoản gian lận qua tối đa ba bước; tìm sản phẩm thường được mua cùng sản phẩm khác; hoặc xác định chuỗi phụ thuộc giữa dịch vụ.

Đồ thị biểu diễn thực thể thành node và quan hệ thành edge. Quan hệ có thể mang thuộc tính như thời điểm bắt đầu, vai trò hoặc mức độ tin cậy. Truy vấn đường đi nhiều bước thường tự nhiên hơn so với việc viết nhiều JOIN lồng nhau.

Nếu phần lớn thao tác chỉ là lấy một bản ghi theo khóa, cập nhật một số trường và tổng hợp theo ngày, mô hình đồ thị có thể tăng thêm chi phí mà không mang lại lợi ích tương xứng. Đừng chọn đồ thị chỉ vì miền nghiệp vụ có nhiều quan hệ; hãy chọn khi việc duyệt quan hệ là thao tác cốt lõi.

### 7.4. Mô hình phân tích

Hệ thống vận hành thường tối ưu cho giao dịch nhỏ, cập nhật chính xác và phản hồi nhanh. Hệ thống phân tích cần quét lượng dữ liệu lớn để tổng hợp theo chiều thời gian, khách hàng, sản phẩm hoặc khu vực. Hai workload này có thể cần cấu trúc khác nhau.

Mô hình sao (star schema) thường có bảng fact lưu sự kiện hoặc số đo, kết nối đến các bảng dimension mô tả ngữ cảnh:

~~~mermaid
flowchart TD
    SALES[Fact_Sales]
    DATE[Dim_Date]
    PRODUCT[Dim_Product]
    CUSTOMER[Dim_Customer]
    STORE[Dim_Store]
    DATE --> SALES
    PRODUCT --> SALES
    CUSTOMER --> SALES
    STORE --> SALES
~~~

Fact_Sales có thể chứa số lượng, doanh thu và khóa đến các dimension. Dim_Date mô tả ngày, tuần, tháng; Dim_Product mô tả nhóm sản phẩm; Dim_Customer mô tả phân khúc khách hàng. Một số dimension có thể cần lưu lịch sử thay đổi, chẳng hạn khách hàng chuyển khu vực nhưng báo cáo cũ phải giữ khu vực tại thời điểm giao dịch.

Dữ liệu phân tích thường được nạp từ hệ thống vận hành qua ETL/ELT hoặc luồng sự kiện. Cần xác định độ trễ chấp nhận được, cách xử lý bản ghi đến muộn, dữ liệu trùng, sự kiện bị phát lại và đối soát tổng số. Không nên để truy vấn báo cáo nặng tranh chấp tài nguyên với giao dịch quan trọng nếu có thể tách workload.

## 8. Ví dụ tổng hợp: thiết kế dữ liệu đơn hàng

Xét yêu cầu: khách hàng tạo đơn hàng, chọn sản phẩm và số lượng, xác nhận giá, thanh toán, sau đó có thể tra cứu lịch sử. Thiết kế cần bảo vệ dữ liệu giao dịch và vẫn hỗ trợ danh mục sản phẩm thay đổi.

### 8.1. Quyết định mô hình

- Dùng mô hình quan hệ làm nguồn dữ liệu vận hành vì đơn hàng liên kết với khách hàng, sản phẩm và thanh toán; nhiều quy tắc cần transaction và ràng buộc tham chiếu.
- Tách customers, products, orders và order_items vì chúng có ý nghĩa và vòng đời riêng.
- Chụp tên sản phẩm, đơn giá và địa chỉ giao hàng tại thời điểm đặt hàng để bảo toàn lịch sử.
- Dùng khóa chính ổn định; dùng khóa ngoại và CHECK/UNIQUE để bảo vệ quy tắc có thể biểu diễn trong cơ sở dữ liệu.
- Lưu grand_total đã chốt vì đây là số tiền đơn hàng được xác nhận; cập nhật cùng transaction với các thành phần đơn hàng và thanh toán. Nếu nghiệp vụ cần đối soát chi tiết, lưu thêm thuế, phí, giảm giá và quy tắc làm tròn.
- Chỉ thêm chỉ mục theo truy vấn thực tế, ví dụ tra cứu đơn hàng mới nhất của khách hàng hoặc tìm dòng hàng theo sản phẩm.

### 8.2. Xem xét bốn mục tiêu

**Tính đúng:** khóa ngoại bảo đảm khách hàng và sản phẩm được tham chiếu tồn tại. CHECK bảo vệ số lượng và giá không âm. Transaction bảo đảm cập nhật tồn kho, đơn hàng và thanh toán theo một quy trình nhất quán. Snapshot giữ giá trị lịch sử. Các quy tắc liên bảng cần được kiểm tra trong transaction hoặc cơ chế đối soát thích hợp.

**Khả năng thay đổi:** thêm phương thức giao hàng mới không nhất thiết làm thay đổi cấu trúc đơn hàng. Nếu mỗi phương thức có nhiều thuộc tính khác nhau, có thể dùng bảng phương thức giao hàng riêng hoặc một phần document có schema được kiểm soát. Khi bổ sung trường, triển khai migration theo giai đoạn để các phiên bản ứng dụng cũ không bị lỗi.

**Hiệu năng:** chỉ mục theo (customer_id, created_at) hỗ trợ màn hình lịch sử đơn hàng. Chỉ mục theo product_id hỗ trợ tra cứu sản phẩm có trong đơn nào. Các truy vấn phân tích doanh thu nên chạy trên kho phân tích hoặc bảng tổng hợp được cập nhật theo chính sách rõ ràng, thay vì quét bảng giao dịch liên tục.

**Độ phức tạp:** mỗi bảng đại diện một khái niệm có tên rõ ràng. Snapshot có lý do nghiệp vụ. Các bản sao tổng hợp chỉ được thêm khi có nhu cầu đo được và có cách đối soát. Nhóm có thể giải thích dữ liệu nào là hiện tại, dữ liệu nào là lịch sử và dữ liệu nào có thể tái tạo.

### 8.3. Những lựa chọn cần xác nhận trước khi triển khai

Một mô hình mẫu không thay thế việc làm rõ nghiệp vụ. Trước khi chốt schema, cần xác nhận:

- Một đơn hàng có thể chứa nhiều loại tiền tệ hay chỉ một loại?
- Có cho phép sửa dòng hàng sau khi thanh toán không? Nếu có, cần lưu điều chỉnh như thế nào?
- Có cho phép xóa khách hàng hoặc sản phẩm đã xuất hiện trong giao dịch không?
- Hủy đơn có hoàn lại tồn kho không, và thao tác đó có thể chạy lặp an toàn không?
- Thuế, phí vận chuyển và giảm giá được tính tại thời điểm nào, làm tròn ra sao?
- Có cần lưu lịch sử trạng thái, người thay đổi và lý do không?
- Báo cáo cần gần thời gian thực hay chấp nhận trễ vài phút hoặc vài giờ?

Các câu trả lời có thể làm thay đổi khóa, ràng buộc, transaction boundary, bảng lịch sử và mô hình phân tích. Ghi lại quyết định cùng lý do giúp người phát triển sau hiểu vì sao cấu trúc được chọn.

## 9. Quy trình ra quyết định thực tế

Khi thiết kế một mô hình mới hoặc xem xét tối ưu mô hình hiện tại, có thể đi theo trình tự sau:

1. **Liệt kê sự thật nghiệp vụ và bất biến.** Viết rõ dữ liệu nào phải tồn tại, quan hệ nào hợp lệ, giá trị nào bị cấm và sự kiện nào cần giữ lịch sử.
2. **Xác định workload.** Liệt kê các truy vấn và lệnh ghi quan trọng, tần suất, kích thước dữ liệu, mức đồng thời và mục tiêu độ trễ.
3. **Chọn ranh giới dữ liệu.** Xác định thực thể, aggregate, quyền sở hữu và vòng đời. Tách dữ liệu có vòng đời độc lập; gom dữ liệu thường được thao tác cùng nhau khi điều đó giúp transaction rõ ràng.
4. **Thiết kế chuẩn hóa làm nền.** Dùng khóa và ràng buộc tường minh. Tránh lặp dữ liệu nếu chưa có lý do về lịch sử hoặc truy cập.
5. **Xác định nơi cần nhất quán mạnh.** Quyết định thao tác nào cần transaction, khóa, unique constraint hoặc cơ chế chống cập nhật đồng thời.
6. **Tối ưu theo số liệu.** Đo truy vấn, xem execution plan, thêm chỉ mục hoặc bản sao dẫn xuất khi có bằng chứng.
7. **Lập đường tiến hóa.** Xem xét dữ liệu cũ, tương thích phiên bản, backfill, thời gian khóa và cách rollback hoặc tiếp tục migration.
8. **Kiểm thử và đối soát.** Kiểm thử ràng buộc, tải đồng thời, migration trên dữ liệu gần thực tế và các báo cáo phát hiện sai lệch.

Một quyết định thiết kế tốt nên ghi lại ít nhất: bối cảnh, lựa chọn, lý do, đánh đổi chấp nhận, giả định về workload và tín hiệu cần theo dõi. Khi tải hoặc nghiệp vụ thay đổi, nhóm có cơ sở để xem xét lại quyết định thay vì tranh luận dựa trên sở thích công nghệ.

## 10. Những sai lầm thường gặp

**Tối ưu trước khi biết truy vấn quan trọng.** Tạo nhiều chỉ mục, cache hoặc bảng tổng hợp ngay từ đầu làm tăng chi phí ghi và vận hành. Hãy đo trước, sau đó tối ưu đúng nút thắt.

**Đưa mọi thứ vào JSON để dễ thay đổi.** Schema linh hoạt không tự tạo ra khả năng tiến hóa an toàn. Nếu trường quan trọng không được xác thực, ràng buộc và lập chỉ mục, dữ liệu có thể nhanh chóng trở nên khó hiểu.

**Chuẩn hóa tuyệt đối bất kể workload.** Tách dữ liệu là nền tảng tốt, nhưng có thể cần snapshot hoặc dữ liệu dẫn xuất để bảo toàn lịch sử và phục vụ truy cập. Quan trọng là phân biệt rõ nguồn sự thật với bản sao.

**Dùng ứng dụng làm hàng rào duy nhất.** Kiểm tra trước khi ghi không bảo vệ được mọi đường ghi và không tự giải quyết race condition. Dùng constraint và transaction ở cơ sở dữ liệu khi có thể.

**Dùng CASCADE theo mặc định.** Xóa một khách hàng hoặc sản phẩm có thể vô tình xóa lịch sử giao dịch. Chính sách xóa phải phản ánh vòng đời và yêu cầu lưu trữ của dữ liệu con.

**Thay schema trong một bước lớn.** Xóa hoặc đổi tên cột ngay khi ứng dụng còn phiên bản cũ có thể gây lỗi triển khai. Dùng thay đổi tương thích và migration nhiều giai đoạn.

**Dùng cùng một mô hình cho giao dịch và báo cáo nặng.** Hai workload có đặc tính khác nhau. Có thể cần kho phân tích hoặc mô hình tổng hợp riêng, cùng quy trình nạp và đối soát.

## 11. Checklist đánh giá mô hình

Trước khi chốt một thiết kế, hãy tự kiểm tra:

- [ ] Mỗi thực thể và thuộc tính có ý nghĩa nghiệp vụ rõ ràng.
- [ ] Khóa chính, khóa ứng viên và quan hệ tham chiếu đã được xác định.
- [ ] Các bất biến quan trọng được bảo vệ bằng constraint hoặc transaction phù hợp.
- [ ] NULL, giá trị mặc định, xóa và vòng đời dữ liệu có ý nghĩa rõ.
- [ ] Dữ liệu hiện tại, snapshot lịch sử và dữ liệu dẫn xuất được phân biệt.
- [ ] Mẫu truy cập chính đã được liệt kê; chỉ mục có lý do cụ thể.
- [ ] Những thao tác đồng thời có thể gây ghi đè hoặc vượt giới hạn đã được xử lý.
- [ ] Có kế hoạch migration tương thích với dữ liệu và phiên bản ứng dụng đang chạy.
- [ ] Độ trễ chấp nhận được của dữ liệu tổng hợp hoặc dữ liệu phân tích đã được thống nhất.
- [ ] Nhóm có thể giải thích nguồn sự thật, cơ chế đồng bộ và cách phát hiện sai lệch.

## Kết luận

Mô hình dữ liệu là tập hợp các quyết định về ý nghĩa, quyền sở hữu, quan hệ, vòng đời và cách truy cập dữ liệu. Tính đúng được bảo vệ bằng ràng buộc, transaction và cách biểu diễn đúng sự thật nghiệp vụ. Khả năng thay đổi đến từ ranh giới rõ ràng, snapshot có chủ đích và migration theo giai đoạn. Hiệu năng đến từ việc hiểu workload, đo truy vấn và tối ưu đúng điểm nghẽn. Độ phức tạp được kiểm soát khi mỗi cơ chế bổ sung có lý do, chủ sở hữu và cách kiểm chứng.

Hãy chọn mô hình dựa trên đặc tính dữ liệu và thao tác cốt lõi. Mô hình quan hệ phù hợp với nhiều nghiệp vụ giao dịch có ràng buộc; document hữu ích cho aggregate được đọc cùng nhau; đồ thị phù hợp khi truy vấn đường đi là trọng tâm; mô hình phân tích phục vụ tổng hợp lịch sử quy mô lớn. Khi kết hợp các mô hình, hãy xác định nguồn sự thật, độ trễ đồng bộ và cách đối soát để lợi ích hiệu năng không làm mất khả năng tin cậy dữ liệu.
