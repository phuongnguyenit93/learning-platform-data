# Quan hệ nhận diện và quan hệ không nhận diện

## Mục tiêu bài học

Sau bài này, bạn có thể phân biệt **quan hệ nhận diện (identifying relationship)** và **quan hệ không nhận diện (non-identifying relationship)** trong mô hình dữ liệu quan hệ; xác định tiêu chí phân loại dựa trên khóa chính và khóa ngoại; giải thích tác động của mỗi kiểu quan hệ đến định danh thực thể con; và lựa chọn cách thiết kế phù hợp với vòng đời nghiệp vụ.

Bạn cũng sẽ biết cách đọc ký pháp ERD, thiết kế khóa ghép hoặc khóa thay thế, chuyển quan hệ thành schema SQL và tránh nhầm lẫn giữa quan hệ nhận diện, tính bắt buộc, bội số và hành vi xóa dữ liệu.

## 1. Vì sao cần phân biệt hai loại quan hệ?

Trong mô hình dữ liệu, một thực thể con thường tham chiếu đến một thực thể cha. Ví dụ:

- Một dòng hàng thuộc về một đơn hàng.
- Một đơn hàng được tạo bởi một khách hàng.
- Một chi tiết hóa đơn thuộc về một hóa đơn.
- Một nhân viên được phân công vào một phòng ban.

Các quan hệ này có thể giống nhau về bội số: một thực thể cha có nhiều thực thể con, và mỗi thực thể con tham chiếu một thực thể cha. Tuy nhiên, cách định danh thực thể con có thể khác nhau.

Với một dòng hàng, mã dòng hàng có thể chỉ có ý nghĩa trong phạm vi đơn hàng. Nếu chuyển dòng hàng sang đơn hàng khác, nó trở thành một dòng hàng khác. Khi đó, khóa của dòng hàng thường bao gồm khóa đơn hàng.

Ngược lại, một đơn hàng có mã đơn hàng riêng, độc lập với khách hàng đã đặt nó. Khách hàng có thể thay đổi theo một quy trình được cho phép mà mã đơn hàng vẫn giữ nguyên. Khi đó, khóa ngoại khách hàng không cần tham gia khóa chính của đơn hàng.

Sự khác biệt này được mô tả bằng hai khái niệm:

- **Quan hệ nhận diện:** khóa chính của thực thể cha được đưa vào khóa chính của thực thể con.
- **Quan hệ không nhận diện:** thực thể con có khóa chính riêng; khóa ngoại đến thực thể cha không phải thành phần của khóa chính đó.

Phân biệt hai loại quan hệ giúp làm rõ thực thể con được nhận diện trong phạm vi nào, khóa của nó phụ thuộc vào cha đến mức nào và thay đổi quan hệ sẽ ảnh hưởng ra sao đến định danh.

## 2. Tiêu chí cốt lõi: khóa ngoại có tham gia khóa chính hay không?

Cách xác định đáng tin cậy nhất là xem cấu trúc khóa của thực thể con.

### 2.1. Quan hệ nhận diện (identifying relationship)

Một quan hệ là **nhận diện** khi khóa chính của thực thể cha được đưa vào khóa chính của thực thể con, thường là một phần của khóa chính ghép.

Ví dụ, một đơn hàng có nhiều dòng hàng. Mỗi dòng được đánh số trong phạm vi đơn hàng:

~~~text
ORDER
  PK: order_id

ORDER_ITEM
  PK: (order_id, line_no)
  FK: order_id -> ORDER.order_id
~~~

Khóa chính của ORDER_ITEM gồm:

- order_id: định danh đơn hàng cha;
- line_no: số thứ tự dòng hàng trong đơn hàng đó.

Chỉ biết line_no = 1 là chưa đủ để xác định một dòng hàng trên toàn hệ thống. Cần biết nó thuộc đơn hàng nào. Vì vậy, order_id tham gia định danh của dòng hàng.

### 2.2. Quan hệ không nhận diện (non-identifying relationship)

Một quan hệ là **không nhận diện** khi thực thể con có khóa chính riêng, còn khóa ngoại đến cha chỉ dùng để biểu diễn liên kết.

Ví dụ, đơn hàng có order_id riêng và tham chiếu khách hàng:

~~~text
CUSTOMER
  PK: customer_id

ORDER
  PK: order_id
  FK: customer_id -> CUSTOMER.customer_id
~~~

order_id đủ để nhận diện một đơn hàng. customer_id cho biết khách hàng liên quan nhưng không tham gia khóa chính của ORDER.

### 2.3. Bảng so sánh

| Tiêu chí | Quan hệ nhận diện | Quan hệ không nhận diện |
|---|---|---|
| Khóa chính của con | Chứa khóa của cha | Độc lập với khóa của cha |
| Khóa ngoại đến cha | Là một phần của PK và đồng thời là FK | Là FK riêng, không thuộc PK |
| Định danh con | Thường phụ thuộc phạm vi cha | Có định danh riêng |
| Di chuyển con sang cha khác | Thường làm thay đổi PK của con | Có thể chỉ thay đổi FK nếu nghiệp vụ cho phép |
| Ví dụ | Dòng hàng trong đơn hàng | Đơn hàng thuộc khách hàng |
| Cách triển khai phổ biến | PK ghép | Surrogate key hoặc natural key riêng |

Tiêu chí này dựa trên cấu trúc khóa. Không thể chỉ nhìn tên thực thể, đường nối hoặc việc một đối tượng “có vẻ phụ thuộc” để kết luận.

## 3. Ví dụ quan hệ nhận diện

### 3.1. Đơn hàng và dòng hàng

Một dòng hàng không có mã độc lập trong nghiệp vụ minh họa. Nó được xác định bằng đơn hàng và số dòng:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);
~~~

Ở đây:

- order_id vừa là khóa ngoại tham chiếu ORDER, vừa là một phần khóa chính ORDER_ITEM.
- line_no chỉ duy nhất trong phạm vi một order_id.
- Hai dòng hàng có cùng line_no vẫn có thể tồn tại nếu chúng thuộc hai đơn hàng khác nhau.
- Một dòng hàng không thể được nhận diện nếu thiếu order_id.

Nếu dòng hàng được chuyển từ đơn hàng A sang đơn hàng B, khóa ghép thay đổi. Theo mô hình này, đó thường là một thao tác thay thế dòng hàng trong phạm vi đơn mới, không đơn thuần là đổi thuộc tính mô tả.

### 3.2. Chi tiết hóa đơn

Một hóa đơn có thể chứa nhiều dòng chi tiết. Số thứ tự dòng chỉ có ý nghĩa trong hóa đơn:

~~~text
INVOICE
  PK: invoice_id

INVOICE_LINE
  PK: (invoice_id, line_number)
  FK: invoice_id -> INVOICE.invoice_id
~~~

Quan hệ INVOICE–INVOICE_LINE là nhận diện nếu invoice_id tham gia PK của INVOICE_LINE.

Nếu hệ thống dùng line_id riêng làm PK và invoice_id chỉ là FK, quan hệ sẽ là không nhận diện theo cấu trúc khóa, dù dòng chi tiết vẫn phụ thuộc nghiệp vụ vào hóa đơn.

### 3.3. Thành phần phụ thuộc vào thực thể cha

Một số ví dụ khác có thể phù hợp với quan hệ nhận diện:

- Địa chỉ liên hệ được đánh số trong hồ sơ khách hàng, nếu số thứ tự chỉ duy nhất trong hồ sơ đó.
- Bản dịch của một tài liệu, nếu ngôn ngữ là phần còn lại của khóa ghép cùng document_id.
- Bước trong quy trình, nếu step_number chỉ có ý nghĩa trong workflow_id.
- Phiên bản con trong một tài liệu, nếu số phiên bản chỉ duy nhất trong tài liệu đó.

Không nên áp dụng quan hệ nhận diện chỉ vì một đối tượng nằm bên trong đối tượng khác về mặt giao diện. Cần xác nhận cách nghiệp vụ nhận diện nó.

## 4. Ví dụ quan hệ không nhận diện

### 4.1. Khách hàng và đơn hàng

Đơn hàng có mã riêng. Mã khách hàng chỉ mô tả ai đã đặt đơn:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
~~~

Ở đây:

- order_id là PK của ORDER.
- customer_id là FK nhưng không nằm trong PK.
- Một khách hàng có thể có nhiều đơn hàng.
- Mỗi đơn hàng bắt buộc tham chiếu một khách hàng vì customer_id là NOT NULL.

Đây là quan hệ không nhận diện dù liên kết khách hàng là bắt buộc.

### 4.2. Nhân viên và phòng ban

Một nhân viên có mã nhân viên độc lập với phòng ban:

~~~sql
CREATE TABLE departments (
    department_id BIGINT PRIMARY KEY,
    department_name VARCHAR(150) NOT NULL
);

CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    FOREIGN KEY (department_id) REFERENCES departments(department_id)
);
~~~

Nếu nhân viên chuyển phòng ban, employee_id vẫn giữ nguyên. Chỉ department_id thay đổi theo quy trình nghiệp vụ. Quan hệ này là không nhận diện.

### 4.3. Bản ghi có vòng đời riêng

Các ví dụ thường phù hợp với quan hệ không nhận diện:

- Một khoản thanh toán có payment_id riêng và tham chiếu đơn hàng.
- Một ticket hỗ trợ có ticket_id riêng và tham chiếu khách hàng.
- Một thiết bị có device_id riêng và được gán cho một nhân viên.
- Một giao dịch có transaction_id riêng và tham chiếu tài khoản.

Các thực thể này có thể có vòng đời, trạng thái hoặc lịch sử riêng. Khóa của chúng không cần chứa khóa cha.

## 5. Hai loại quan hệ không quyết định bội số

Cần tách biệt bốn câu hỏi:

1. **Quan hệ nhận diện hay không nhận diện?** Khóa cha có tham gia PK của con không?
2. **Một-một hay một-nhiều?** Có bao nhiêu bản ghi ở hai phía có thể liên kết?
3. **Bắt buộc hay tùy chọn?** Quan hệ có thể vắng mặt không?
4. **Vòng đời và xóa dữ liệu ra sao?** Khi cha bị xóa, con được giữ, xóa, chuyển hoặc chặn thao tác?

Đây là các khía cạnh khác nhau.

Ví dụ, ORDER–ORDER_ITEM có thể là quan hệ nhận diện và một-nhiều. CUSTOMER–ORDER có thể là quan hệ không nhận diện và cũng là một-nhiều. Cả hai đều có thể bắt buộc ở đầu con, nhưng cấu trúc PK khác nhau.

Một quan hệ không nhận diện vẫn có thể có FK NOT NULL. Một quan hệ nhận diện thường có FK không NULL vì cột FK nằm trong PK, mà thành phần PK không được NULL trong mô hình quan hệ thông dụng.

Không được suy ra hành vi ON DELETE CASCADE chỉ từ tên identifying. Chính sách xóa là quyết định riêng, cần căn cứ vào nghiệp vụ và khả năng lưu lịch sử.

## 6. Quan hệ nhận diện và thực thể yếu

### 6.1. Thực thể yếu (weak entity)

**Thực thể yếu** là khái niệm mô hình hóa có định danh phụ thuộc vào một thực thể chủ hoặc một phạm vi định danh khác. Nó thường không có khóa tự nhiên độc lập đủ để nhận diện trong toàn miền.

Ví dụ, một dòng hàng có số thứ tự 1, 2, 3 trong mỗi đơn hàng. Số thứ tự chỉ có ý nghĩa khi đi kèm đơn hàng.

~~~text
ORDER
  order_id

ORDER_ITEM
  order_id
  line_no
~~~

ORDER_ITEM là ví dụ gần với thực thể yếu: định danh của nó phụ thuộc ORDER.

Trong mô hình quan hệ, quan hệ nhận diện thường được dùng để thể hiện cấu trúc này. Tuy nhiên, “weak entity” là khái niệm về ý nghĩa định danh và phụ thuộc trong mô hình; “identifying relationship” là cách thể hiện quan hệ khóa giữa cha và con. Hai khái niệm liên quan chặt chẽ nhưng không nên dùng thay thế máy móc trong mọi trường hợp.

### 6.2. Phụ thuộc tồn tại và phụ thuộc định danh

Một thực thể có thể phụ thuộc tồn tại vào cha nhưng vẫn có khóa riêng.

Ví dụ, một dòng hàng có line_id UUID riêng và order_id NOT NULL. Dòng hàng không thể có ý nghĩa nếu không thuộc đơn hàng, nhưng PK của nó không chứa order_id. Quan hệ này là không nhận diện theo tiêu chí khóa, dù có phụ thuộc tồn tại.

Ngược lại, khi PK của con chứa PK cha, con phụ thuộc định danh vào cha. Điều này làm rõ phạm vi định danh và thường khiến việc chuyển con sang cha khác làm thay đổi khóa.

## 7. Chọn khóa cho thực thể con

### 7.1. Dùng khóa ghép khi định danh phụ thuộc phạm vi cha

Khóa ghép phù hợp khi:

- mã cục bộ chỉ duy nhất trong phạm vi cha;
- con không cần được tham chiếu độc lập ở nhiều hệ thống;
- việc chuyển con sang cha khác có nghĩa là đổi định danh;
- nghiệp vụ muốn thể hiện rõ cấu trúc cha–con.

Ví dụ:

~~~sql
PRIMARY KEY (order_id, line_no)
~~~

Ưu điểm:

- thể hiện rõ phạm vi định danh;
- không cần thêm ID riêng chỉ để định danh dòng;
- có thể phản ánh tự nhiên quy tắc “dòng số 2 của đơn X”.

Cần cân nhắc:

- khóa có nhiều cột hơn;
- mọi bảng tham chiếu dòng hàng phải mang đủ khóa ghép;
- thay đổi khóa cha có thể ảnh hưởng nhiều khóa con;
- thứ tự cột trong index cần phù hợp với truy vấn.

### 7.2. Dùng khóa thay thế cho thực thể con

Có thể dùng ID riêng dù con phụ thuộc nghiệp vụ vào cha:

~~~sql
CREATE TABLE order_items (
    order_item_id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    UNIQUE (order_id, line_no)
);
~~~

Trong thiết kế này:

- order_item_id là PK độc lập;
- order_id là FK bắt buộc nhưng không thuộc PK;
- UNIQUE(order_id, line_no) vẫn bảo đảm số dòng không trùng trong cùng đơn;
- quan hệ ORDER–ORDER_ITEM là không nhận diện theo cấu trúc PK.

Cách này có thể hữu ích khi dòng hàng được tham chiếu bởi nhiều dịch vụ, message hoặc bảng khác thông qua một ID đơn giản. Nó cũng giảm độ rộng khóa ngoại ở các bảng phụ thuộc.

Tuy nhiên, ID riêng không tự xóa bỏ quy tắc rằng dòng hàng phải thuộc đơn hàng. Quy tắc đó vẫn cần được bảo vệ bằng FK, NOT NULL và logic nghiệp vụ.

### 7.3. Đánh giá theo cách sử dụng

| Câu hỏi | Gợi ý thiết kế |
|---|---|
| Mã con chỉ có ý nghĩa trong cha? | Cân nhắc PK ghép có khóa cha |
| Con được tham chiếu độc lập ở nhiều nơi? | Cân nhắc surrogate key |
| Có cần giữ mã nghiệp vụ cục bộ? | Dùng UNIQUE theo khóa cha và mã cục bộ |
| Con có thể chuyển sang cha khác? | Đánh giá tác động của việc đổi PK hoặc chỉ đổi FK |
| Khóa ghép quá rộng? | Cân nhắc ID riêng và ràng buộc UNIQUE bổ sung |
| Cần giữ lịch sử định danh? | Thiết kế alias hoặc bảng lịch sử riêng |

Không có một lựa chọn đúng cho mọi hệ thống. Hãy xét định danh nghiệp vụ, workload truy vấn, cách tích hợp và chi phí thay đổi.

## 8. Ký pháp ERD và cách đọc

Nhiều công cụ ERD biểu diễn quan hệ nhận diện bằng đường nối liền (solid line) và quan hệ không nhận diện bằng đường nối đứt (dashed line). Đây là quy ước phổ biến trong một số ký pháp, nhưng cần kiểm tra legend của công cụ đang dùng.

Ví dụ minh họa:

~~~text
Quan hệ nhận diện:
ORDER ━━━━━ ORDER_ITEM
       order_id thuộc PK của ORDER_ITEM

Quan hệ không nhận diện:
CUSTOMER - - - ORDER
          customer_id không thuộc PK của ORDER
~~~

Ký pháp đường nối chỉ là dấu hiệu trực quan. Tiêu chí quyết định vẫn là cấu trúc khóa trong mô hình logic hoặc schema.

### 8.1. Đọc ví dụ tổng hợp

~~~mermaid
erDiagram
    CUSTOMER ||..o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
~~~

Trong sơ đồ minh họa:

- CUSTOMER–ORDER được vẽ theo kiểu không nhận diện: order_id độc lập, customer_id là FK.
- ORDER–ORDER_ITEM được vẽ theo kiểu nhận diện: order_id tham gia PK của ORDER_ITEM.

Cú pháp đường nối có thể khác giữa các công cụ Mermaid và ERD chuyên dụng. Khi công cụ không hỗ trợ kiểu đường nối hoặc dùng quy ước khác, hãy ghi rõ loại quan hệ trong legend hoặc tài liệu mô hình.

### 8.2. Đừng nhầm đường nối với optionality

Đường liền hoặc đứt mô tả identifying/non-identifying theo quy ước. Vòng tròn, vạch và chân quạ mô tả min–max. Hai nhóm ký hiệu giải quyết hai câu hỏi khác nhau và có thể cùng xuất hiện trên một quan hệ.

Ví dụ, một ORDER có thể bắt buộc tham chiếu CUSTOMER bằng FK NOT NULL nhưng quan hệ vẫn không nhận diện. Trong một công cụ ERD, đường đứt có thể đi cùng ký hiệu bắt buộc ở đầu ORDER.

## 9. Tác động đến thay đổi khóa và di chuyển thực thể con

### 9.1. Khi khóa cha thay đổi

Nếu PK cha là một phần PK con, thay đổi khóa cha có thể kéo theo cập nhật khóa con và mọi FK tham chiếu con. Với khóa tự nhiên có thể thay đổi, việc này tạo chi phí lớn.

Ví dụ, nếu order_id được dùng trong PK của ORDER_ITEM, thay order_id có thể cần cập nhật các dòng hàng và những bảng đang tham chiếu chúng. Có thể dùng ON UPDATE CASCADE trong một số hệ quản trị, nhưng cần đánh giá phạm vi, khóa ngoại và tính an toàn của thao tác.

Vì vậy, khóa cha tham gia PK con nên ổn định. Nếu mã cha có thể thay đổi theo nghiệp vụ, cân nhắc dùng surrogate key làm PK và lưu mã nghiệp vụ riêng.

### 9.2. Khi chuyển con sang cha khác

Với quan hệ nhận diện, chuyển ORDER_ITEM sang ORDER khác làm thay đổi một phần PK. Điều đó có thể được xem là thay đổi danh tính của dòng hàng.

Với quan hệ không nhận diện, nếu nghiệp vụ cho phép chuyển, có thể cập nhật FK order_id mà order_item_id giữ nguyên. Nhưng việc giữ ID không có nghĩa chuyển là hợp lệ: cần kiểm tra lịch sử, trạng thái, kiểm toán và tham chiếu từ hệ thống khác.

### 9.3. Thay đổi mô hình theo thời gian

Nếu ban đầu dùng khóa ghép nhưng sau đó cần tham chiếu con độc lập, có thể bổ sung surrogate key. Quá trình chuyển đổi cần:

1. thêm cột ID mới;
2. sinh ID ổn định cho dữ liệu hiện có;
3. tạo UNIQUE cho khóa nghiệp vụ cũ;
4. cập nhật các FK tham chiếu;
5. triển khai tương thích trong ứng dụng và API;
6. kiểm tra dữ liệu và chuyển đổi transaction;
7. chỉ bỏ khóa cũ khi không còn phụ thuộc.

Đây là thay đổi schema có ảnh hưởng rộng, nên cần migration có kế hoạch và kiểm thử dữ liệu thực tế.

## 10. Chính sách xóa và vòng đời là quyết định riêng

Quan hệ nhận diện thường xuất hiện giữa thực thể chủ và thực thể phụ thuộc, nhưng không được tự động kết luận rằng phải xóa con khi xóa cha.

Các hành vi FK phổ biến:

- **RESTRICT/NO ACTION:** chặn xóa cha khi còn bản ghi con tham chiếu.
- **CASCADE:** xóa bản ghi con khi cha bị xóa.
- **SET NULL:** đặt FK con thành NULL nếu cột cho phép.
- **SET DEFAULT:** đặt FK về giá trị mặc định nếu hệ quản trị và ràng buộc cho phép.

Lựa chọn phụ thuộc vào quy tắc nghiệp vụ:

- Dòng hàng của đơn đã phát hành có thể phải giữ để kiểm toán.
- Chi tiết nháp có thể được xóa cùng bản nháp.
- Hồ sơ khách hàng có thể được ẩn danh thay vì xóa các đơn hàng lịch sử.
- Bản ghi thanh toán thường cần được giữ dù đơn hàng bị hủy.

Với quan hệ nhận diện, FK nằm trong PK con nên không thể SET NULL mà vẫn giữ PK hợp lệ. Nếu muốn tách liên kết, cần thiết kế lại định danh hoặc dùng một mô hình khác. Dù vậy, CASCADE vẫn là một lựa chọn riêng nếu chính sách cho phép.

Không nên dùng CASCADE chỉ vì công cụ ERD vẽ đường nhận diện. Hãy ghi hành vi xóa thành quyết định có thể kiểm chứng.

## 11. Từ mô hình đến tiêu chí chấp nhận

Có thể viết tiêu chí kiểm thử để xác nhận loại quan hệ và quy tắc khóa.

### 11.1. Tiêu chí cho ORDER–ORDER_ITEM nhận diện

- Mỗi ORDER_ITEM phải tham chiếu một ORDER tồn tại.
- Cặp (order_id, line_no) phải duy nhất.
- Hai đơn hàng khác nhau có thể có dòng cùng line_no.
- Không thể tạo ORDER_ITEM nếu thiếu order_id.
- Thay đổi order_id phải tuân theo chính sách khóa và tham chiếu đã xác định.

### 11.2. Tiêu chí cho CUSTOMER–ORDER không nhận diện

- Mỗi ORDER có order_id duy nhất, độc lập với customer_id.
- customer_id phải tham chiếu CUSTOMER hợp lệ nếu nghiệp vụ yêu cầu bắt buộc.
- Một CUSTOMER có thể có nhiều ORDER.
- Thay đổi liên kết khách hàng, nếu được phép, không làm đổi order_id.
- Không thể xóa CUSTOMER nếu còn ORDER tham chiếu khi chính sách là RESTRICT.

### 11.3. Kiểm tra bằng dữ liệu mẫu

Với ORDER_ITEM có PK ghép:

~~~sql
INSERT INTO orders(order_id, created_at)
VALUES (1001, CURRENT_TIMESTAMP), (1002, CURRENT_TIMESTAMP);

INSERT INTO order_items(order_id, line_no, product_id, quantity, unit_price)
VALUES
    (1001, 1, 501, 2, 100.00),
    (1002, 1, 501, 1, 100.00);
~~~

Hai dòng cùng line_no = 1 hợp lệ vì order_id khác nhau. Nếu thêm một dòng khác với (1001, 1), database phải từ chối do trùng khóa chính.

Đối với CUSTOMER–ORDER, có thể kiểm tra order_id không đổi khi customer_id được cập nhật trong một quy trình được phép. Kiểm thử phải phản ánh đúng chính sách thay đổi liên kết, không giả định mọi hệ thống đều cho phép đổi khách hàng của đơn.

## 12. Những sai lầm thường gặp

- **Cho rằng quan hệ nhận diện là quan hệ bắt buộc:** tính bắt buộc và cấu trúc PK là hai khía cạnh riêng. Một FK không thuộc PK vẫn có thể NOT NULL.
- **Cho rằng mọi thực thể con đều phải có khóa ghép:** con có thể có ID riêng dù phụ thuộc tồn tại vào cha.
- **Cho rằng quan hệ không nhận diện là tùy chọn:** FK của quan hệ không nhận diện vẫn có thể bắt buộc.
- **Dùng đường liền/đứt để suy ra bội số:** đường nối mô tả kiểu quan hệ theo quy ước công cụ; min–max cần ký hiệu riêng.
- **Đồng nhất identifying relationship với ON DELETE CASCADE:** hành vi xóa cần quyết định riêng.
- **Đưa mã cha có thể thay đổi vào PK con:** làm thay đổi định danh lan rộng. Cần cân nhắc khóa cha ổn định.
- **Bỏ UNIQUE khi dùng surrogate key:** ID riêng không tự ngăn hai dòng trùng số thứ tự trong cùng đơn.
- **Không xét các bảng tham chiếu con:** thay PK ghép hoặc đổi quan hệ có thể ảnh hưởng toàn bộ FK phụ thuộc.
- **Coi phụ thuộc nghiệp vụ là phụ thuộc khóa:** một thực thể có thể không tồn tại nếu thiếu cha nhưng vẫn có PK riêng.

## 13. Kết luận

Quan hệ nhận diện được xác định khi khóa chính của thực thể cha tham gia khóa chính của thực thể con. Quan hệ không nhận diện xảy ra khi thực thể con có khóa chính riêng và FK đến cha nằm ngoài PK. Đây là khác biệt về cấu trúc định danh.

Khi thiết kế, hãy xác định cách nghiệp vụ nhận diện thực thể con, phạm vi duy nhất của mã cục bộ, nhu cầu tham chiếu độc lập và độ ổn định của khóa cha. Sau đó chọn PK ghép hoặc khóa thay thế, bổ sung FK và UNIQUE phù hợp, đồng thời ghi riêng tính bắt buộc, bội số và chính sách xóa. Một mô hình rõ ràng giúp định danh ổn định, thay đổi quan hệ có kiểm soát và kiểm chứng được các quy tắc dữ liệu.

## Tự kiểm tra

1. Tiêu chí kỹ thuật nào phân biệt quan hệ nhận diện và không nhận diện?
2. Vì sao ORDER–ORDER_ITEM có thể dùng PK ghép (order_id, line_no)?
3. Một ORDER bắt buộc có CUSTOMER nhưng customer_id không nằm trong PK. Đây là quan hệ gì? Vì sao?
4. Một thực thể con có thể phụ thuộc tồn tại vào cha nhưng vẫn có quan hệ không nhận diện không?
5. Vì sao identifying relationship không tự động có nghĩa ON DELETE CASCADE?
6. Khi nào nên dùng surrogate key cho thực thể con thay vì PK ghép?
7. Nếu khóa cha có thể thay đổi, việc đưa nó vào PK con tạo ra rủi ro gì?
8. Hãy chọn hai quan hệ trong một hệ thống, xác định loại quan hệ, PK/FK, optionality, cardinality và chính sách xóa cho từng quan hệ.

