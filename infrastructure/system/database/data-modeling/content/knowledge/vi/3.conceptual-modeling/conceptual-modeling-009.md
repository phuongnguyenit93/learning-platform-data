# Chuyển từ mô hình khái niệm sang mô hình logic mà vẫn giữ đúng ý nghĩa

Mô hình khái niệm mô tả thế giới nghiệp vụ bằng các khái niệm như khách hàng, đơn hàng, sản phẩm, thanh toán và những quan hệ giữa chúng. Mô hình logic chuyển cách hiểu đó thành cấu trúc dữ liệu có thể tổ chức và kiểm tra: các loại dữ liệu, thuộc tính, định danh, quan hệ, khóa và ràng buộc. Quá trình chuyển đổi phải giữ nguyên ý nghĩa nghiệp vụ đã được xác nhận.

Nếu chỉ chuyển tên thực thể thành tên bảng và tên thuộc tính thành tên cột, mô hình có thể trông hợp lý nhưng vẫn làm mất thông tin. Một quan hệ nhiều-nhiều có thể bị biến thành quan hệ một-nhiều sai; thuộc tính nhiều giá trị có thể bị nhồi vào một chuỗi; quy tắc duy nhất có thể bị bỏ quên; hoặc một thực thể yếu có thể mất điều kiện nhận diện phụ thuộc vào thực thể chủ.

Bài học này trình bày cách chuyển đổi có hệ thống, cách chọn cấu trúc logic phù hợp và cách kiểm tra xem mô hình logic có còn biểu đạt đầy đủ các quy tắc trong mô hình khái niệm hay không.

**Sau bài học, bạn có thể:**

- Phân biệt mô hình khái niệm, mô hình logic và mô hình vật lý.
- Chuyển thực thể, thuộc tính và quan hệ thành các cấu trúc logic phù hợp.
- Biểu diễn đúng quan hệ một-một, một-nhiều, nhiều-nhiều, quan hệ đệ quy và quan hệ nhiều ngôi.
- Bảo toàn định danh, tính duy nhất, tính tùy chọn, miền giá trị và các quy tắc nghiệp vụ.
- Nhận diện những trường hợp cần tách thuộc tính, tạo thực thể kết hợp hoặc lưu lịch sử.
- Kiểm chứng mô hình logic bằng các tình huống nghiệp vụ và quy tắc bất biến.

## 1. Ba mức mô hình và mục tiêu của chuyển đổi

### 1.1. Mô hình khái niệm

Mô hình khái niệm trả lời câu hỏi: **Doanh nghiệp quan tâm đến những khái niệm nào và chúng liên hệ với nhau ra sao?**

Nó thường thể hiện:

- Các loại thực thể hoặc khái niệm nghiệp vụ;
- Những thuộc tính có ý nghĩa;
- Các quan hệ giữa các khái niệm;
- Bội số và tính tham gia bắt buộc hoặc tùy chọn;
- Các quy tắc nghiệp vụ quan trọng;
- Phạm vi và định nghĩa của từng khái niệm.

Mô hình khái niệm ưu tiên cách hiểu chung giữa chuyên gia nghiệp vụ, nhà phân tích, nhà phát triển và người kiểm thử. Nó không cần quyết định chi tiết lưu trữ theo một hệ quản trị cơ sở dữ liệu cụ thể.

### 1.2. Mô hình logic

Mô hình logic trả lời câu hỏi: **Cần tổ chức dữ liệu thành những cấu trúc nào, với thuộc tính, định danh, quan hệ và ràng buộc nào để biểu diễn đúng nghiệp vụ?**

Với mô hình logic quan hệ, các cấu trúc thường gồm:

- Quan hệ (relation), thường được triển khai thành bảng;
- Thuộc tính, miền giá trị và tính bắt buộc;
- Khóa chính, khóa ứng viên và khóa ngoại;
- Ràng buộc duy nhất, tham chiếu và kiểm tra;
- Quan hệ kết hợp cho những trường hợp cần biểu diễn nhiều-nhiều hoặc thuộc tính của quan hệ;
- Cấu trúc lưu lịch sử nếu nghiệp vụ cần theo dõi thay đổi.

Mô hình logic có thể dùng thuật ngữ và kiểu dữ liệu trừu tượng như **Money**, **Date**, **Identifier**, **Boolean** hoặc miền trạng thái đã được định nghĩa. Chưa cần quyết định kiểu vật lý cụ thể của từng hệ quản trị.

### 1.3. Mô hình vật lý

Mô hình vật lý trả lời câu hỏi: **Cấu trúc logic sẽ được triển khai như thế nào trên nền tảng cụ thể?**

Nó có thể quyết định kiểu dữ liệu cụ thể, cách sinh khóa, chỉ mục, phân vùng, lưu trữ, nén, tên đối tượng theo quy ước hệ thống và các tối ưu hiệu năng.

Ví dụ, mô hình logic có thuộc tính **order_created_at** mang ý nghĩa thời điểm tạo đơn. Mô hình vật lý mới quyết định kiểu timestamp cụ thể, độ chính xác, múi giờ, chỉ mục và cách lưu trữ trên hệ quản trị được chọn.

| Mức mô hình | Trọng tâm | Ví dụ quyết định |
|---|---|---|
| Khái niệm | Ý nghĩa nghiệp vụ | Một đơn hàng có nhiều dòng hàng |
| Logic | Cấu trúc dữ liệu và ràng buộc | Quan hệ ORDER_LINE tham chiếu ORDER và PRODUCT_VARIANT |
| Vật lý | Cách triển khai trên nền tảng | Kiểu cột, index, partition, tablespace hoặc chiến lược lưu trữ |

Không nên bỏ qua mô hình logic để đi thẳng từ sơ đồ khái niệm sang lệnh tạo bảng. Khi chưa làm rõ khóa, miền giá trị, quan hệ và ràng buộc, các quyết định vật lý rất dễ cố định một cách hiểu sai.

## 2. Nguyên tắc giữ nguyên ý nghĩa nghiệp vụ

Chuyển đổi thành công không có nghĩa là giữ nguyên hình dạng sơ đồ. Một thực thể khái niệm có thể trở thành một hoặc nhiều quan hệ logic; một quan hệ khái niệm có thể được biểu diễn bằng khóa ngoại hoặc quan hệ kết hợp. Hình dạng thay đổi, nhưng các sự kiện và quy tắc mà hệ thống có thể biểu diễn phải tương đương với yêu cầu.

Cần giữ ít nhất các yếu tố sau:

1. **Định nghĩa:** mỗi cấu trúc logic vẫn đại diện cho đúng khái niệm đã được xác nhận.
2. **Độ hạt:** một hàng hoặc một bản ghi đại diện cho đúng một đơn vị nghiệp vụ.
3. **Định danh:** các đối tượng có thể được phân biệt và tham chiếu ổn định.
4. **Bội số:** số lượng đối tượng được phép tham gia quan hệ vẫn đúng.
5. **Tính tham gia:** quan hệ bắt buộc hay tùy chọn không bị thay đổi.
6. **Miền giá trị:** thuộc tính chỉ nhận những giá trị được nghiệp vụ cho phép.
7. **Quy tắc bất biến:** các điều kiện như duy nhất, không âm, không trùng hoặc phải thuộc cùng phạm vi vẫn được bảo toàn.
8. **Thời gian và lịch sử:** thời điểm có hiệu lực, thời điểm ghi nhận và yêu cầu truy vết không bị mất.
9. **Ngữ cảnh:** cùng tên nhưng khác nghĩa vẫn được phân biệt; bí danh không tạo ra khái niệm mới nếu chúng thực sự đồng nghĩa.

Một câu hỏi hữu ích khi đánh giá là: “Với mô hình logic này, hệ thống có thể lưu và kiểm tra mọi trường hợp hợp lệ, đồng thời ngăn những trường hợp nghiệp vụ cấm hay không?”

## 3. Quy trình chuyển đổi từ khái niệm sang logic

Có thể thực hiện theo trình tự sau:

### Bước 1: Chốt định nghĩa và phạm vi

Đọc lại định nghĩa của từng khái niệm, vai trò, quy tắc và phạm vi. Nếu tên thực thể hoặc thuộc tính còn mơ hồ, cần làm rõ trước khi ánh xạ. Không suy ra cấu trúc chỉ từ tên gọi.

### Bước 2: Xác nhận độ hạt

Viết rõ một instance đại diện cho điều gì. Ví dụ một bản ghi ORDER đại diện cho một đơn đã được tạo; một bản ghi ORDER_LINE đại diện cho một dòng hàng được ghi nhận trong đơn. Việc này giúp tránh đưa thuộc tính của dòng hàng vào cấp đơn hoặc đếm một đơn thành nhiều đơn.

### Bước 3: Xác định loại cấu trúc logic

Với mỗi khái niệm, xác định nó sẽ trở thành:

- Một quan hệ độc lập;
- Một thuộc tính của quan hệ khác;
- Một quan hệ kết hợp;
- Một miền giá trị hoặc danh mục tham chiếu;
- Một cấu trúc lịch sử;
- Hoặc một khái niệm chỉ dùng để tính toán, không nhất thiết lưu như dữ liệu gốc.

### Bước 4: Ánh xạ thuộc tính

Xác định thuộc tính đơn trị, nhiều giá trị, phức hợp, dẫn xuất hoặc có hiệu lực theo thời gian. Kiểm tra miền giá trị, đơn vị đo, độ chính xác và khả năng để trống.

### Bước 5: Chọn định danh và khóa

Xác định các khóa ứng viên từ quy tắc nghiệp vụ, sau đó chọn khóa chính trong mô hình logic. Ghi lại khóa thay thế và các điều kiện duy nhất khác.

### Bước 6: Ánh xạ quan hệ và bội số

Chuyển từng quan hệ khái niệm thành khóa ngoại hoặc quan hệ kết hợp phù hợp. Bảo toàn cả số lượng tối đa và tối thiểu, cũng như các điều kiện tham gia.

### Bước 7: Biểu diễn ràng buộc

Chuyển quy tắc nghiệp vụ thành ràng buộc logic có thể kiểm tra: bắt buộc, duy nhất, tham chiếu, miền giá trị, điều kiện liên thuộc và quy tắc thời gian.

### Bước 8: Kiểm tra tính toàn vẹn ngữ nghĩa

Dùng ví dụ, trường hợp biên và tình huống ngoại lệ để kiểm tra mô hình. Đối chiếu lại với mô hình khái niệm và yêu cầu nguồn.

~~~mermaid
flowchart TD
    A["Mô hình khái niệm đã xác nhận"] --> B["Chốt định nghĩa, phạm vi và độ hạt"]
    B --> C["Ánh xạ thực thể và thuộc tính"]
    C --> D["Xác định định danh và khóa ứng viên"]
    D --> E["Ánh xạ quan hệ và bội số"]
    E --> F["Biểu diễn miền giá trị và ràng buộc"]
    F --> G["Tạo mô hình logic"]
    G --> H["Kiểm tra tình huống và quy tắc nghiệp vụ"]
    H --> I{"Ý nghĩa được bảo toàn?"}
    I -->|Chưa| J["Điều chỉnh ánh xạ hoặc làm rõ nghiệp vụ"]
    J --> C
    I -->|Có| K["Chốt mô hình logic"]
~~~

## 4. Ánh xạ thực thể thành quan hệ logic

Trong mô hình quan hệ, một loại thực thể thường được ánh xạ thành một quan hệ. Mỗi instance của thực thể trở thành một hàng; thuộc tính đơn trị trở thành thuộc tính của quan hệ.

Ví dụ, thực thể khái niệm CUSTOMER có các thuộc tính:

- Mã khách hàng;
- Tên hiển thị;
- Ngày đăng ký;
- Email liên hệ.

Có thể ánh xạ thành quan hệ logic:

**CUSTOMER**

| Thuộc tính | Ý nghĩa | Ghi chú logic |
|---|---|---|
| customer_id | Định danh khách hàng | Khóa chính |
| display_name | Tên hiển thị | Bắt buộc nếu nghiệp vụ yêu cầu |
| registered_at | Thời điểm đăng ký | Thời điểm |
| contact_email | Email liên hệ | Có thể tùy chọn; duy nhất hay không phải xác nhận |

Một thực thể không nhất thiết chỉ có một bảng trong mọi trường hợp. Khi thuộc tính có vòng đời, quyền truy cập hoặc độ hạt riêng, có thể cần quan hệ bổ sung. Ngược lại, một số khái niệm chỉ là vai trò hoặc thuộc tính và không cần tạo quan hệ độc lập.

### 4.1. Thực thể mạnh và thực thể phụ thuộc

Thực thể mạnh có thể được nhận diện độc lập theo định danh của nó. Thực thể phụ thuộc (weak entity) cần thực thể chủ để xác định hoặc tồn tại theo quy tắc nghiệp vụ.

Ví dụ, ORDER_LINE thường không có ý nghĩa độc lập ngoài đơn hàng chứa nó. Một số hệ thống xác định dòng bằng cặp (order_id, line_number).

| Thuộc tính | Vai trò |
|---|---|
| order_id | Tham chiếu đơn hàng chủ |
| line_number | Phân biệt dòng trong phạm vi đơn |
| product_variant_id | Biến thể được chọn |
| quantity | Số lượng |
| unit_price | Giá được áp dụng cho dòng |

Khóa logic có thể là (order_id, line_number) nếu số dòng duy nhất trong từng đơn. Nếu nghiệp vụ có mã dòng ổn định độc lập, có thể chọn mã đó làm khóa chính và thêm ràng buộc duy nhất cho cặp đơn hàng và số dòng. Quyết định phải phản ánh quy tắc nhận diện thực tế.

### 4.2. Thuộc tính đơn trị và phức hợp

Thuộc tính đơn trị có một giá trị tại độ hạt đã chọn. Thuộc tính phức hợp gồm nhiều thành phần có ý nghĩa riêng.

Ví dụ ADDRESS có thể gồm:

- Đường và số nhà;
- Phường hoặc xã;
- Quận hoặc huyện;
- Tỉnh hoặc thành phố;
- Mã bưu chính;
- Quốc gia.

Nếu hệ thống cần tìm kiếm, xác thực hoặc phân tích theo từng thành phần, mô hình logic nên tách chúng thành các thuộc tính phù hợp. Nếu địa chỉ chỉ được lưu để hiển thị nguyên văn và không cần xử lý từng phần, có thể giữ thêm một dòng địa chỉ. Cần dựa trên yêu cầu, không tách máy móc mọi chuỗi thành nhiều cột.

### 4.3. Thuộc tính nhiều giá trị

Một thuộc tính có thể có nhiều giá trị cho một instance, ví dụ khách hàng có nhiều số điện thoại liên hệ hoặc một sản phẩm có nhiều nhãn.

Trong mô hình quan hệ, không nên lưu danh sách giá trị trong một chuỗi nếu cần truy vấn, kiểm tra duy nhất hoặc liên kết từng giá trị. Có thể tạo quan hệ riêng:

**CUSTOMER_PHONE**

| Thuộc tính | Ý nghĩa |
|---|---|
| customer_id | Khách hàng sở hữu số điện thoại |
| phone_number | Một số điện thoại |
| phone_type | Loại số, nếu nghiệp vụ phân loại |
| is_primary | Có phải số chính hay không |

Khóa có thể là (customer_id, phone_number) nếu một số chỉ xuất hiện một lần trong hồ sơ khách hàng. Nếu số điện thoại cần định danh riêng hoặc có lịch sử, cấu trúc có thể cần mở rộng.

Nếu thứ tự các giá trị có ý nghĩa, chẳng hạn thứ tự ưu tiên liên hệ, phải lưu vị trí hoặc số thứ tự. Không nên dựa vào thứ tự trả về ngẫu nhiên của cơ sở dữ liệu.

### 4.4. Thuộc tính dẫn xuất

Thuộc tính dẫn xuất được tính từ dữ liệu khác, ví dụ tuổi từ ngày sinh hoặc tổng tiền đơn từ các dòng hàng và chi phí liên quan.

Trong mô hình logic, cần ghi rõ công thức và nguồn dữ liệu. Không nhất thiết phải lưu giá trị dẫn xuất như dữ liệu gốc. Nếu cần lưu bản sao để đáp ứng yêu cầu lịch sử hoặc hiệu năng, phải xác định thời điểm tính lại, nguồn có thẩm quyền và cách xử lý khi dữ liệu nguồn thay đổi.

Ví dụ, order_total có thể là tổng các dòng hàng, thuế, phí vận chuyển và giảm giá theo quy tắc tính tiền. Không nên mặc định tổng đơn chỉ là tổng quantity nhân unit_price nếu nghiệp vụ có nhiều thành phần khác.

## 5. Ánh xạ quan hệ và bội số

Quan hệ khái niệm mô tả cách các instance liên hệ với nhau. Trong mô hình logic quan hệ, khóa ngoại và quan hệ kết hợp thường được dùng để biểu diễn quan hệ đó.

### 5.1. Quan hệ một-nhiều (1:N)

Ví dụ, một khách hàng có thể đặt nhiều đơn hàng; mỗi đơn hàng thuộc về một khách hàng theo quy tắc của hệ thống.

Cấu trúc logic:

- CUSTOMER giữ khóa chính customer_id.
- ORDER giữ khóa ngoại customer_id tham chiếu CUSTOMER.

| CUSTOMER | ORDER |
|---|---|
| customer_id (PK) | order_id (PK) |
| display_name | customer_id (FK) |
| ... | created_at |

Khóa ngoại đặt ở phía nhiều vì mỗi đơn cần chỉ ra khách hàng liên quan. Nếu nghiệp vụ cho phép đơn khách vãng lai không có hồ sơ khách hàng, customer_id có thể tùy chọn hoặc cần một cách biểu diễn chủ thể mua khác. Không tự đặt NOT NULL nếu tính tham gia tối thiểu chưa được xác nhận.

### 5.2. Quan hệ một-một (1:1)

Ví dụ, một nhân viên có thể có một hồ sơ thông tin bổ sung và mỗi hồ sơ thuộc về đúng một nhân viên.

Có thể đặt khóa ngoại ở một trong hai quan hệ và thêm ràng buộc duy nhất để bảo đảm một nhân viên không có nhiều hồ sơ tương ứng. Nếu quan hệ bắt buộc ở cả hai phía và vòng đời luôn đi cùng nhau, nhóm cần cân nhắc liệu hai khái niệm có thực sự nên là một quan hệ hay không.

| Quy tắc | Cách biểu diễn logic thường dùng |
|---|---|
| Một nhân viên có tối đa một hồ sơ | FK employee_id trong EMPLOYEE_PROFILE |
| Mỗi hồ sơ phải thuộc một nhân viên | FK bắt buộc |
| Một nhân viên chỉ có một hồ sơ | FK có ràng buộc UNIQUE |

Khóa ngoại duy nhất biểu diễn tối đa một; tính bắt buộc của khóa ngoại biểu diễn tối thiểu một ở phía hồ sơ. Cần kiểm tra cả hai chiều để không nhầm quan hệ 1:1 với 1:N.

### 5.3. Quan hệ nhiều-nhiều (M:N)

Ví dụ, một đơn hàng có nhiều sản phẩm và một sản phẩm có thể xuất hiện trong nhiều đơn hàng. Không thể đặt một khóa ngoại đơn lẻ ở một phía để biểu diễn đầy đủ quan hệ nhiều-nhiều.

Tạo quan hệ kết hợp ORDER_LINE:

- order_id tham chiếu ORDER;
- product_variant_id tham chiếu PRODUCT_VARIANT;
- quantity, unit_price và các thuộc tính khác mô tả quan hệ lựa chọn sản phẩm trong đơn.

Quan hệ kết hợp không chỉ là kỹ thuật nối hai bảng. Nó có ý nghĩa nghiệp vụ riêng: một dòng hàng cụ thể trong một đơn. Khi quan hệ có thuộc tính hoặc cần định danh riêng, việc tạo cấu trúc kết hợp là cần thiết.

### 5.4. Quan hệ đệ quy

Quan hệ đệ quy là quan hệ giữa các instance cùng một loại thực thể.

Ví dụ, một nhân viên có thể quản lý các nhân viên khác. Trong mô hình logic có thể dùng khóa ngoại manager_employee_id trong EMPLOYEE tham chiếu lại employee_id của chính quan hệ đó.

Cần xác định:

- Một nhân viên có thể không có quản lý trực tiếp không?
- Một nhân viên có thể quản lý nhiều người không?
- Có cho phép tự quản lý không?
- Có được phép tạo vòng lặp quản lý không?

Khóa ngoại bảo đảm người quản lý được tham chiếu tồn tại, nhưng không tự ngăn mọi chu trình trong cây quản lý. Quy tắc chống chu trình có thể cần logic nghiệp vụ hoặc cơ chế kiểm tra bổ sung.

### 5.5. Quan hệ nhiều ngôi

Một quan hệ có thể liên kết ba hoặc nhiều loại thực thể. Ví dụ, nhà cung cấp cung cấp một sản phẩm cho một kho theo một điều kiện hợp đồng cụ thể. Nếu tách thành ba quan hệ đôi, có thể mất ý nghĩa rằng một sự kiện cung ứng là tổ hợp của cả ba bên.

Có thể tạo quan hệ kết hợp SUPPLIER_PRODUCT_WAREHOUSE chứa khóa tham chiếu tới nhà cung cấp, sản phẩm và kho, cùng các thuộc tính như giá cung ứng, ngày hiệu lực hoặc thời gian giao dự kiến.

Khóa chính hoặc ràng buộc duy nhất phải phản ánh điều kiện phân biệt một thỏa thuận. Không mặc định mọi quan hệ nhiều ngôi đều có khóa ghép gồm toàn bộ khóa ngoại; cần xác nhận một nhà cung cấp có thể có nhiều thỏa thuận cho cùng sản phẩm và kho theo các thời hạn hoặc hợp đồng khác nhau hay không.

## 6. Bảo toàn định danh và khóa

Định danh mô tả cách nhận diện một instance nghiệp vụ. Khóa logic là cấu trúc thuộc tính dùng để phân biệt và tham chiếu các hàng trong mô hình quan hệ.

Cần phân biệt:

- **Khóa ứng viên:** tập thuộc tính tối thiểu có thể nhận diện duy nhất một hàng.
- **Khóa chính:** khóa ứng viên được chọn làm định danh chính trong quan hệ.
- **Khóa thay thế:** khóa ứng viên khác không được chọn làm khóa chính.
- **Khóa ngoại:** thuộc tính hoặc tập thuộc tính tham chiếu khóa của quan hệ khác.

Ví dụ, khách hàng có thể có customer_id và một mã khách hàng nghiệp vụ. Nếu mã nghiệp vụ duy nhất trong phạm vi doanh nghiệp, nó có thể là khóa ứng viên thay thế. Email thường không nên tự động chọn làm khóa vì có thể thay đổi, có thể dùng chung hoặc có quy tắc duy nhất khác nhau theo doanh nghiệp.

### 6.1. Khóa đơn và khóa ghép

Khóa đơn dùng một thuộc tính. Khóa ghép dùng nhiều thuộc tính cùng nhau.

Ví dụ, (order_id, line_number) có thể phân biệt dòng hàng trong phạm vi một đơn. Chỉ line_number có thể lặp ở các đơn khác nhau nên không đủ để nhận diện dòng trên toàn hệ thống.

Khóa ghép cần được kiểm tra về tính tối thiểu và ổn định. Không thêm thuộc tính vào khóa chỉ vì muốn tạo cảm giác duy nhất nếu chúng không cần thiết cho nhận diện.

### 6.2. Khóa thay thế và khóa nghiệp vụ

Khóa thay thế như một ID kỹ thuật có thể hữu ích khi khóa nghiệp vụ dài, có thể thay đổi hoặc phụ thuộc vào hệ thống ngoài. Tuy nhiên, việc thêm ID không loại bỏ các quy tắc duy nhất của nghiệp vụ.

Ví dụ, dù customer_id là khóa chính, hệ thống vẫn có thể cần ràng buộc duy nhất cho mã khách hàng trong một tổ chức. Nếu bỏ ràng buộc đó, có thể tạo hai hồ sơ cùng một mã nghiệp vụ dù mỗi hàng có ID riêng.

### 6.3. Khóa ngoại và toàn vẹn tham chiếu

Khóa ngoại bảo đảm giá trị tham chiếu tới một hàng tồn tại trong quan hệ được tham chiếu. Nó giúp ngăn dữ liệu mồ côi, nhưng không tự biểu diễn mọi quy tắc nghiệp vụ.

Ví dụ, ORDER.customer_id tham chiếu một khách hàng tồn tại. Nhưng quy tắc “khách hàng bị khóa không được tạo đơn mới” là quy tắc nghiệp vụ bổ sung, không được bảo đảm chỉ bằng khóa ngoại.

## 7. Ánh xạ miền giá trị và ràng buộc

Mỗi thuộc tính cần có miền giá trị rõ ràng. Miền có thể mô tả kiểu trừu tượng, giới hạn, đơn vị đo, tập giá trị hợp lệ và điều kiện bắt buộc.

Ví dụ:

| Thuộc tính | Miền hoặc quy tắc logic |
|---|---|
| quantity | Số lượng dương theo đơn vị hàng; có cho phép số lẻ hay không cần xác nhận |
| unit_price | Giá tiền không âm, gắn với đơn vị tiền tệ và quy tắc làm tròn |
| order_status | Một trong các trạng thái hợp lệ theo vòng đời đơn |
| registered_at | Thời điểm đăng ký, có quy tắc múi giờ |
| email | Chuỗi theo định dạng được chấp nhận; tính duy nhất cần xác định phạm vi |

### 7.1. Ràng buộc bắt buộc và tùy chọn

Một thuộc tính bắt buộc không được thiếu giá trị trong những bản ghi hợp lệ. Một thuộc tính tùy chọn có thể chưa có hoặc không áp dụng.

Không nên dùng NULL thay cho mọi trạng thái “chưa biết”, “chưa cung cấp”, “không áp dụng” và “đang chờ”. Những ý nghĩa này có thể khác nhau. Nếu phân biệt có giá trị nghiệp vụ, hãy dùng trạng thái hoặc cấu trúc rõ ràng.

### 7.2. Ràng buộc duy nhất

Quy tắc duy nhất có thể áp dụng trên một thuộc tính hoặc tổ hợp thuộc tính.

Ví dụ:

- Mã khách hàng duy nhất trong một tổ chức;
- Số dòng duy nhất trong một đơn;
- Mỗi kho chỉ có một bản ghi cấu hình mặc định cho một loại cấu hình;
- Một SKU chỉ có một mã quét chính trong phạm vi đã quy định.

Cần ghi rõ phạm vi duy nhất. “Email duy nhất” có thể là duy nhất toàn hệ thống, trong một tenant hoặc chỉ trong nhóm tài khoản đang hoạt động.

### 7.3. Ràng buộc miền và điều kiện

Ràng buộc miền kiểm tra giá trị có hợp lệ không. Ví dụ số lượng phải lớn hơn 0, ngày kết thúc không trước ngày bắt đầu, hoặc tỷ lệ nằm trong khoảng cho phép.

Ràng buộc liên thuộc kiểm tra nhiều thuộc tính hoặc nhiều quan hệ cùng lúc. Ví dụ:

- Ngày kết thúc phải lớn hơn hoặc bằng ngày bắt đầu;
- Đơn đã giao phải có thông tin giao hàng phù hợp;
- Một dòng giao hàng không được phân bổ vượt số lượng còn có thể giao;
- Tổng số tiền hoàn không vượt số tiền đã thu theo quy tắc tài chính.

Một số quy tắc có thể được biểu diễn bằng ràng buộc khai báo trong mô hình logic; một số khác cần quy trình hoặc logic nghiệp vụ vì phụ thuộc nhiều hàng, nhiều bước hoặc trạng thái theo thời gian.

### 7.4. Ràng buộc tham gia quan hệ

Bội số tối đa và tối thiểu cần được bảo toàn. Ví dụ:

- Mỗi dòng đơn hàng phải thuộc đúng một đơn;
- Một đơn có thể có một hoặc nhiều dòng khi đã được xác nhận;
- Một đơn có thể chưa có thanh toán nếu cho phép thanh toán sau;
- Một kiện hàng phải thuộc một quy trình giao hàng cụ thể.

Khóa ngoại có thể bảo đảm tham chiếu tồn tại nhưng không tự bảo đảm mọi điều kiện tối thiểu ở phía cha. Chẳng hạn, nó không tự bảo đảm một đơn đã xác nhận phải có ít nhất một dòng hàng. Quy tắc này có thể cần kiểm tra khi chuyển trạng thái đơn.

## 8. Ví dụ tổng hợp: từ mô hình khái niệm bán hàng sang mô hình logic

Giả sử nghiệp vụ đã xác nhận:

- Một khách hàng có thể tạo nhiều đơn hàng.
- Mỗi đơn hàng thuộc về một khách hàng trong phạm vi bán hàng đã đăng ký.
- Một đơn hàng có ít nhất một dòng khi được xác nhận.
- Mỗi dòng thuộc đúng một đơn và tham chiếu một biến thể sản phẩm.
- Một đơn có thể có nhiều lần thử thanh toán.
- Một đơn có thể được giao thành nhiều kiện.
- Một dòng đơn hàng có thể được phân bổ vào nhiều kiện giao khác nhau.
- Giá bán tại thời điểm đặt phải được giữ lại để giải thích giao dịch lịch sử.

Từ đó có thể tạo mô hình logic minh họa:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_LINE : contains
    PRODUCT_VARIANT ||--o{ ORDER_LINE : selected_as
    ORDER ||--o{ PAYMENT_ATTEMPT : has
    ORDER ||--o{ SHIPMENT : fulfilled_by
    SHIPMENT ||--o{ SHIPMENT_LINE : includes
    ORDER_LINE ||--o{ SHIPMENT_LINE : allocated_to
~~~

Các quan hệ logic có thể được mô tả:

**CUSTOMER**

| Thuộc tính | Quy tắc |
|---|---|
| customer_id | PK |
| customer_code | Duy nhất trong phạm vi tổ chức nếu nghiệp vụ xác nhận |
| display_name | Bắt buộc |
| registered_at | Thời điểm đăng ký |

**ORDER**

| Thuộc tính | Quy tắc |
|---|---|
| order_id | PK |
| customer_id | FK tới CUSTOMER, bắt buộc theo giả định nghiệp vụ |
| order_number | Mã tra cứu nghiệp vụ; duy nhất theo phạm vi được xác nhận |
| created_at | Thời điểm tạo đơn |
| order_status | Thuộc miền trạng thái đơn hàng |

**ORDER_LINE**

| Thuộc tính | Quy tắc |
|---|---|
| order_id | FK tới ORDER |
| line_number | Số thứ tự dòng trong đơn |
| product_variant_id | FK tới PRODUCT_VARIANT |
| quantity | Số lượng hợp lệ theo đơn vị hàng |
| unit_price | Giá đã chốt tại thời điểm đặt |
| line_discount | Mức giảm giá của dòng theo quy tắc bán hàng |

Khóa logic tham khảo của ORDER_LINE là (order_id, line_number). Nếu có order_line_id độc lập, vẫn cần giữ ràng buộc duy nhất của (order_id, line_number) nếu nghiệp vụ yêu cầu.

**PAYMENT_ATTEMPT**

| Thuộc tính | Quy tắc |
|---|---|
| payment_attempt_id | PK |
| order_id | FK tới ORDER |
| attempted_at | Thời điểm thử |
| amount | Số tiền yêu cầu xử lý |
| result_status | Miền kết quả lần thử |
| provider_reference | Mã tham chiếu nhà cung cấp, duy nhất trong phạm vi thích hợp |

**SHIPMENT**

| Thuộc tính | Quy tắc |
|---|---|
| shipment_id | PK |
| order_id | FK tới ORDER |
| shipment_number | Mã kiện hoặc lô gửi theo quy tắc vận chuyển |
| handed_over_at | Thời điểm bàn giao nếu đã xảy ra |
| shipment_status | Miền trạng thái giao hàng |

**SHIPMENT_LINE**

| Thuộc tính | Quy tắc |
|---|---|
| shipment_id | FK tới SHIPMENT |
| order_id | Thành phần tham chiếu dòng đơn nếu dùng khóa ghép |
| line_number | Tham chiếu dòng đơn hàng |
| shipped_quantity | Số lượng phân bổ vào kiện |

Trong ví dụ này, SHIPMENT_LINE tham chiếu một dòng đơn hàng và một kiện giao hàng. Khóa và các khóa ngoại ghép phải được thiết kế sao cho dòng được phân bổ thực sự thuộc đơn mà kiện đó đang giao. Có thể dùng khóa thay thế cho ORDER_LINE, nhưng vẫn cần ràng buộc bảo toàn quan hệ thuộc đơn.

Đây là mô hình logic minh họa, chưa phải lược đồ vật lý hoàn chỉnh. Những quy tắc như giới hạn tổng số lượng giao, số tiền hoàn, trạng thái chuyển tiếp và xử lý đơn vãng lai cần được mô tả và triển khai ở bước phù hợp.

## 9. Giữ nguyên ý nghĩa khi chọn kiểu mô hình khác

Mô hình logic quan hệ là một cách biểu diễn phổ biến, nhưng mô hình khái niệm có thể được ánh xạ sang document, graph hoặc mô hình phân tích. Cấu trúc khác nhau không làm thay đổi định nghĩa nghiệp vụ.

| Kiểu mô hình | Cách chuyển đổi | Điểm cần bảo toàn |
|---|---|---|
| Quan hệ | Thực thể thành quan hệ; quan hệ thành FK hoặc quan hệ kết hợp | Khóa, bội số, miền giá trị, toàn vẹn tham chiếu |
| Document | Đối tượng hoặc aggregate thành document; thành phần lồng nhau thành object/array | Ranh giới aggregate, định danh phần tử, cập nhật và lịch sử |
| Đồ thị | Thực thể thành node; quan hệ thành edge hoặc node quan hệ | Loại node/edge, hướng, bội số, thuộc tính và hiệu lực |
| Phân tích | Sự kiện hoặc snapshot thành fact; khái niệm mô tả thành dimension | Độ hạt fact, chiều, phép đo, quy tắc cộng gộp và thời gian |

### 9.1. Với document

Một document có thể đại diện cho một đơn hàng và chứa các dòng hàng lồng nhau. Điều này phù hợp khi đơn và các dòng thường được đọc hoặc cập nhật cùng nhau. Tuy nhiên, mỗi phần tử dòng hàng vẫn cần định danh hoặc quy tắc phân biệt nếu nghiệp vụ cần sửa, tham chiếu, giao từng phần hoặc lưu lịch sử riêng.

Nếu một dòng hàng có thể được liên kết từ nhiều kiện giao, cấu trúc lồng nhau đơn giản có thể không đủ. Cần thiết kế tham chiếu hoặc một aggregate khác để biểu diễn phân bổ giao hàng mà không nhân bản sai ý nghĩa dòng gốc.

### 9.2. Với đồ thị

Một khách hàng và một đơn hàng có thể là hai loại node; quan hệ đặt hàng là edge. Nếu edge chỉ biểu diễn quan hệ hiện tại, một edge giữa khách hàng và đơn hàng có thể đủ. Nếu cần lưu mỗi lần tương tác hoặc lịch sử thay đổi, có thể cần node sự kiện hoặc thuộc tính thời gian trên edge.

Điều quan trọng là xác định một edge đại diện cho quan hệ tồn tại hay một lần sự kiện. Không dùng cùng một cạnh cho hai ý nghĩa khác nhau.

### 9.3. Với mô hình phân tích

Mô hình phân tích cần xác định độ hạt fact trước khi chọn dimension và measure. Ví dụ fact bán hàng ở độ hạt dòng đơn hàng có thể liên kết tới dimension sản phẩm, khách hàng, cửa hàng và ngày. Nếu fact lại ở độ hạt đơn hàng, chỉ số số lượng theo sản phẩm có thể không còn chính xác nếu đơn chứa nhiều sản phẩm.

Đặc biệt, cần phân biệt chỉ số cộng được, cộng được một phần và không cộng được. Số lượng bán có thể cộng qua các dòng; số dư và tồn kho tại thời điểm là chỉ số trạng thái, không nên cộng qua nhiều thời điểm để tạo tổng.

## 10. Chuẩn hóa logic và tránh mất dữ liệu

Sau khi ánh xạ, cần xem xét các phụ thuộc và cấu trúc có gây trùng lặp hoặc bất thường cập nhật hay không. Chuẩn hóa giúp mỗi sự kiện và thuộc tính được lưu ở nơi phù hợp với ý nghĩa và phụ thuộc của nó.

Ví dụ, nếu tên sản phẩm và thông tin nhà sản xuất được lặp lại trên mọi dòng đơn hàng, thay đổi tên nhà sản xuất có thể yêu cầu cập nhật nhiều nơi. Tuy nhiên, giá bán tại thời điểm đặt là thông tin lịch sử của dòng đơn hàng, không nên thay bằng giá hiện tại trong danh mục sản phẩm.

Không nên xóa mọi bản sao dữ liệu một cách máy móc. Một số giá trị được chụp lại có chủ đích để bảo toàn sự kiện lịch sử, như giá đã chốt, tên hiển thị trên chứng từ hoặc địa chỉ giao hàng tại thời điểm đặt. Cần phân biệt dữ liệu lặp gây bất thường với dữ liệu snapshot cần thiết.

Khi chuẩn hóa, hãy kiểm tra:

- Thuộc tính có phụ thuộc đúng vào khóa của quan hệ không?
- Có thuộc tính của thực thể khác bị lặp ở nhiều hàng không?
- Quan hệ nhiều-nhiều đã được biểu diễn bằng cấu trúc phù hợp chưa?
- Có thuộc tính nhiều giá trị bị lưu trong chuỗi hoặc cột lặp không?
- Dữ liệu lịch sử có bị thay đổi khi dữ liệu danh mục hiện tại thay đổi không?
- Việc tách quan hệ có giữ lại đầy đủ khả năng kết hợp dữ liệu ban đầu không?

## 11. Kiểm chứng mô hình logic có bảo toàn ý nghĩa không

Một mô hình logic cần được kiểm tra theo cả cấu trúc lẫn hành vi. Chỉ nhìn sơ đồ có đủ bảng và khóa chưa thể kết luận mô hình đúng.

### 11.1. Kiểm tra truy vết

Mỗi thực thể, thuộc tính, quan hệ và ràng buộc logic nên truy vết được về một khái niệm hoặc quy tắc nghiệp vụ. Ngược lại, mỗi quy tắc nghiệp vụ quan trọng phải có vị trí biểu diễn hoặc cơ chế kiểm soát trong mô hình.

Có thể lập bảng:

| Yêu cầu hoặc quy tắc | Cấu trúc logic liên quan | Cách kiểm chứng |
|---|---|---|
| Mỗi đơn thuộc một khách hàng | ORDER.customer_id | Thử tạo đơn không có khách hàng hợp lệ |
| Mỗi dòng thuộc một đơn | ORDER_LINE.order_id | Thử tạo dòng tham chiếu đơn không tồn tại |
| Một số dòng duy nhất trong một đơn | ORDER_LINE(order_id, line_number) | Thử tạo hai dòng cùng số thứ tự trong một đơn |
| Một dòng có thể giao thành nhiều kiện | SHIPMENT_LINE tham chiếu ORDER_LINE | Thử phân bổ một dòng vào hai kiện |
| Giá lịch sử được giữ nguyên | ORDER_LINE.unit_price | Thay giá danh mục sau khi đặt và kiểm tra dòng đơn cũ |

### 11.2. Kiểm tra bằng tình huống hợp lệ

Thử những trường hợp nghiệp vụ cho phép:

- Một khách hàng tạo nhiều đơn;
- Một đơn có nhiều dòng hàng;
- Một đơn có nhiều lần thử thanh toán;
- Một dòng hàng được giao thành nhiều kiện;
- Một SKU tồn tại ở nhiều kho;
- Một sản phẩm đổi tên nhưng chứng từ cũ vẫn giữ thông tin tại thời điểm giao dịch.

Mô hình phải biểu diễn được những trường hợp này mà không cần bóp méo ý nghĩa của bản ghi.

### 11.3. Kiểm tra trường hợp bị cấm

Thử những trường hợp nghiệp vụ không cho phép:

- Dòng hàng tham chiếu đơn không tồn tại;
- Hai dòng trong cùng đơn vi phạm quy tắc số dòng duy nhất;
- Số lượng âm khi nghiệp vụ chỉ cho phép số lượng dương;
- Kiện hàng được phân bổ vượt số lượng còn được phép giao;
- Một mã duy nhất bị sử dụng cho hai đối tượng trong cùng phạm vi.

Nếu mô hình logic không có cách biểu diễn hoặc kiểm soát quy tắc, cần bổ sung ràng buộc hoặc ghi rõ cơ chế thực thi ở tầng nghiệp vụ.

### 11.4. Kiểm tra khả năng tái tạo thông tin

Sau khi chuyển đổi, hãy thử kết hợp các quan hệ để tái tạo thông tin ở mức khái niệm:

- Từ đơn hàng có thể xác định khách hàng và các dòng hàng không?
- Từ dòng giao hàng có thể biết dòng đơn nào được giao và thuộc đơn nào không?
- Từ các lần thử có thể biết lịch sử xử lý thanh toán của đơn không?
- Từ dữ liệu chi tiết có thể tính lại chỉ số tổng hợp theo quy tắc đã công bố không?

Nếu việc tách quan hệ làm mất khả năng tái tạo dữ liệu hoặc tạo ra các kết hợp không hợp lệ, ánh xạ cần được xem xét lại.

## 12. Những lỗi thường gặp khi chuyển đổi

1. **Chuyển mỗi danh từ thành một bảng:** danh từ có thể là vai trò, thuộc tính, sự kiện hoặc khái niệm không cần lưu độc lập.
2. **Bỏ qua độ hạt:** một bảng có tên đúng nhưng hàng đại diện cho nhiều loại đơn vị nghiệp vụ.
3. **Đặt khóa ngoại sai phía:** quan hệ 1:N bị biểu diễn thành quan hệ khác hoặc khóa ngoại không phản ánh phía tham gia.
4. **Không tạo quan hệ kết hợp cho M:N:** dẫn đến danh sách ID trong một cột hoặc mất thuộc tính của quan hệ.
5. **Làm mất tính tùy chọn:** một quan hệ có thể là tùy chọn trong nghiệp vụ nhưng bị ép bắt buộc trong mô hình.
6. **Dùng khóa thay thế thay cho quy tắc duy nhất:** ID khác nhau nhưng mã nghiệp vụ vẫn có thể bị trùng.
7. **Nhồi thuộc tính nhiều giá trị vào chuỗi:** khó kiểm tra, tìm kiếm, cập nhật và tham chiếu.
8. **Tách thuộc tính quá mức:** làm cấu trúc phức tạp dù không có nhu cầu xử lý riêng từng thành phần.
9. **Lưu giá trị dẫn xuất mà không có quy tắc đồng bộ:** dữ liệu tổng hợp hoặc tổng tiền có thể lệch với dữ liệu nguồn.
10. **Mất lịch sử:** cập nhật thuộc tính hiện tại khiến không thể giải thích giao dịch quá khứ.
11. **Ánh xạ quan hệ nhiều ngôi thành các quan hệ đôi không tương đương:** mất điều kiện ràng buộc trên tổ hợp.
12. **Đưa chi tiết vật lý vào quá sớm:** chọn kiểu cột, index hoặc partition trước khi ý nghĩa và ràng buộc logic được thống nhất.

## 13. Checklist hoàn tất mô hình logic

- [ ] Mỗi cấu trúc logic có định nghĩa và độ hạt rõ ràng.
- [ ] Mọi thực thể khái niệm cần lưu đã được ánh xạ hoặc có lý do không lưu riêng.
- [ ] Thuộc tính đơn trị, phức hợp, nhiều giá trị và dẫn xuất đã được phân biệt.
- [ ] Khóa ứng viên, khóa chính, khóa thay thế và khóa ngoại đã được xác định.
- [ ] Quan hệ 1:1, 1:N, M:N, đệ quy và nhiều ngôi được biểu diễn đúng.
- [ ] Bội số tối đa và tối thiểu, tính bắt buộc và tùy chọn được bảo toàn.
- [ ] Miền giá trị, đơn vị đo, độ chính xác và tính duy nhất được ghi rõ.
- [ ] Các quy tắc liên thuộc và quy tắc theo thời gian đã được ghi nhận.
- [ ] Dữ liệu lịch sử và snapshot được giữ theo đúng mục đích nghiệp vụ.
- [ ] Không có thuộc tính hoặc quan hệ bị mất khi ánh xạ.
- [ ] Có thể biểu diễn các trường hợp hợp lệ và ngăn hoặc phát hiện trường hợp bị cấm.
- [ ] Các quyết định logic có thể truy vết về yêu cầu và mô hình khái niệm.
- [ ] Mô hình đã được người có trách nhiệm nghiệp vụ xác nhận.

## 14. Bài tập thực hành

Một hệ thống bán hàng có mô hình khái niệm sau:

- Khách hàng đặt đơn hàng.
- Đơn hàng chứa các dòng hàng.
- Mỗi dòng hàng chọn một biến thể sản phẩm.
- Một đơn có thể có nhiều lần thử thanh toán.
- Đơn có thể được giao thành nhiều kiện.
- Một dòng hàng có thể được chia vào nhiều kiện.
- Mỗi kiện có nhiều sự kiện theo dõi vận chuyển.
- Giá bán tại thời điểm đặt phải được giữ lại.

Hãy đề xuất mô hình logic quan hệ, gồm:

1. Danh sách quan hệ cần có.
2. Thuộc tính chính của mỗi quan hệ.
3. Khóa chính, khóa ngoại và ràng buộc duy nhất.
4. Cách biểu diễn quan hệ nhiều-nhiều giữa dòng đơn hàng và kiện hàng.
5. Cách phân biệt kiện hàng với sự kiện theo dõi vận chuyển.
6. Các quy tắc nghiệp vụ chưa thể biểu diễn chỉ bằng khóa ngoại.

**Gợi ý đáp án:**

| Quan hệ | Độ hạt | Khóa và tham chiếu chính |
|---|---|---|
| CUSTOMER | Một khách hàng | customer_id PK |
| ORDER | Một đơn hàng | order_id PK; customer_id FK |
| ORDER_LINE | Một dòng trong một đơn | (order_id, line_number) PK hoặc order_line_id PK kèm UNIQUE |
| PRODUCT_VARIANT | Một biến thể có thể bán | product_variant_id PK |
| PAYMENT_ATTEMPT | Một lần thử thanh toán | payment_attempt_id PK; order_id FK |
| SHIPMENT | Một kiện hoặc lô gửi | shipment_id PK; order_id FK |
| SHIPMENT_LINE | Phần số lượng của một dòng được đưa vào một kiện | FK tới SHIPMENT và ORDER_LINE; khóa theo quy tắc phân bổ |
| SHIPMENT_EVENT | Một sự kiện theo dõi của kiện | shipment_event_id PK; shipment_id FK |

SHIPMENT_LINE là quan hệ kết hợp để biểu diễn một dòng đơn hàng có thể được phân bổ vào nhiều kiện và một kiện có thể chứa phần hàng từ nhiều dòng. SHIPMENT_EVENT có độ hạt là một lần quét hoặc cập nhật vận chuyển, do đó một kiện có thể có nhiều sự kiện.

unit_price cần được lưu ở ORDER_LINE để giữ giá đã chốt tại thời điểm đặt, kể cả khi giá trong danh mục sản phẩm thay đổi. Các quy tắc như tổng số lượng giao không vượt số lượng đặt, đơn đã xác nhận phải có dòng hàng, hoặc sự kiện vận chuyển phải theo trình tự hợp lệ cần được kiểm tra bằng ràng buộc liên thuộc hoặc logic nghiệp vụ thích hợp.

Bài tập đạt yêu cầu khi mô hình logic phân biệt được đơn hàng, dòng hàng, lần thử thanh toán, kiện hàng và sự kiện vận chuyển; đồng thời bảo toàn khả năng giao nhiều đợt và lịch sử giá.
