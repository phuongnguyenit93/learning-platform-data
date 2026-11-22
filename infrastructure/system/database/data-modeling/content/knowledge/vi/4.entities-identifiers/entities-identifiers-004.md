# Khóa tự nhiên, khóa thay thế và tiêu chí lựa chọn

Trong chương **Thực thể và định danh** của module **DATABASE_DATA_MODELING**, người học cần hiểu một thực thể đại diện cho đối tượng nghiệp vụ nào, điều gì làm cho đối tượng đó được nhận diện xuyên suốt vòng đời và cách bảo vệ tính duy nhất của nó. Sau khi xác định thực thể, một quyết định quan trọng là chọn khóa tự nhiên, khóa thay thế hay kết hợp cả hai.

Khóa không chỉ là một cột dùng để nối bảng. Nó là hợp đồng định danh giữa dữ liệu, quy trình nghiệp vụ và các hệ thống sử dụng dữ liệu. Chọn khóa thiếu ổn định có thể khiến việc đổi mã nghiệp vụ làm đứt quan hệ, trùng bản ghi hoặc phải cập nhật hàng loạt tham chiếu. Chọn khóa thay thế nhưng quên ràng buộc nghiệp vụ lại có thể cho phép hai bản ghi đại diện cùng một đối tượng. Bài này trình bày bản chất của hai cách định danh, tiêu chí lựa chọn và cách áp dụng trong mô hình dữ liệu có thể tiến hóa.

## 1. Thực thể cần được định danh như thế nào?

**Thực thể (entity)** là một đối tượng hoặc khái niệm nghiệp vụ có danh tính riêng và có thể được phân biệt với các đối tượng cùng loại. Ví dụ: một khách hàng, một sản phẩm, một đơn hàng hoặc một nhân viên. Thực thể thường có vòng đời, thuộc tính và quan hệ với các thực thể khác.

Khi nhận diện một thực thể, hãy hỏi:

- Đối tượng này có thể tồn tại độc lập trong nghiệp vụ không?
- Có cần phân biệt nó với những đối tượng khác cùng loại không?
- Nó có thể được tạo, cập nhật, ngừng hoạt động hoặc lưu lịch sử không?
- Các quy trình khác có cần tham chiếu lại đúng đối tượng này không?
- Những thuộc tính nào mô tả đối tượng, và thuộc tính nào chỉ mô tả một vai trò hoặc một lần tham gia?

Ví dụ, một khách hàng có thể đổi tên, email hoặc địa chỉ nhưng vẫn là cùng một khách hàng. Nếu định danh của khách hàng được gắn trực tiếp vào email, việc đổi email có thể khiến hệ thống hiểu nhầm rằng khách hàng cũ đã biến mất và một khách hàng mới xuất hiện. Định danh cần thể hiện danh tính của thực thể, còn email là thuộc tính có thể thay đổi theo quy tắc nghiệp vụ.

### Phân biệt thực thể và đối tượng giá trị

Không phải mọi khái niệm trong mô hình đều cần một định danh độc lập.

| Khái niệm | Cách nhận diện | Ví dụ |
|---|---|---|
| Thực thể | Có danh tính riêng, cần phân biệt qua thời gian | Khách hàng, Đơn hàng, Sản phẩm |
| Đối tượng giá trị (value object) | Được nhận diện bằng toàn bộ giá trị; thường không có vòng đời độc lập | Khoảng ngày, số tiền kèm đơn vị tiền, tọa độ |
| Thuộc tính | Một đặc điểm của thực thể hoặc đối tượng giá trị | Tên hiển thị, ngày tạo, số lượng |
| Thực thể liên kết | Biểu diễn một quan hệ có thuộc tính hoặc vòng đời riêng | Dòng đơn hàng, lượt đăng ký, phân công nhân viên |

Ví dụ, địa chỉ hiện tại trong hồ sơ khách hàng có thể là một đối tượng giá trị. Nhưng địa chỉ giao hàng đã được chụp vào một đơn hàng có ý nghĩa lịch sử riêng: nó phải giữ nguyên ngay cả khi khách hàng đổi địa chỉ sau đó. Tùy nghiệp vụ, snapshot địa chỉ có thể là một phần của đơn hàng hoặc một đối tượng có định danh riêng nếu cần quản lý và tham chiếu độc lập.

Một quan hệ nhiều-nhiều cũng có thể trở thành thực thể liên kết. Ví dụ, Sinh viên đăng ký Học phần tạo ra một Lượt đăng ký có ngày đăng ký, trạng thái và điểm. Nếu chỉ lưu một danh sách mã học phần trên sinh viên, ta khó biểu diễn nhiều lần đăng ký hoặc lịch sử của từng lượt.

## 2. Các khái niệm về khóa và định danh

Trước khi so sánh hai loại khóa, cần phân biệt các thuật ngữ thường gặp:

- **Siêu khóa (superkey):** một hoặc nhiều thuộc tính có thể xác định duy nhất mỗi bản ghi; tập thuộc tính có thể chứa phần dư.
- **Khóa ứng viên (candidate key):** một superkey tối thiểu, nghĩa là bỏ bất kỳ thuộc tính nào trong khóa thì không còn bảo đảm tính duy nhất.
- **Khóa chính (primary key):** khóa ứng viên được chọn làm định danh chính thức của hàng trong bảng.
- **Khóa thay thế (surrogate key):** định danh kỹ thuật được tạo ra để đại diện cho bản ghi, thường không mang ý nghĩa nghiệp vụ.
- **Khóa tự nhiên (natural key):** một hoặc nhiều thuộc tính vốn có ý nghĩa nghiệp vụ và có thể định danh đối tượng theo quy tắc đã xác định.
- **Khóa ứng viên còn lại (alternate key):** khóa ứng viên không được chọn làm khóa chính nhưng vẫn có thể dùng để nhận diện duy nhất.
- **Khóa ngoại (foreign key):** thuộc tính hoặc tập thuộc tính tham chiếu đến khóa được bảo vệ ở bảng khác.

Ví dụ, một nhân viên có mã nhân viên duy nhất trong một tổ chức. Nếu mã nhân viên được quy định không đổi và không tái sử dụng, tổ hợp (organization_id, employee_no) có thể là khóa tự nhiên. Bảng vẫn có thể dùng employee_id làm khóa chính thay thế; khi đó tổ hợp nghiệp vụ phải được bảo vệ bằng UNIQUE.

Một khóa chỉ hợp lệ trong một phạm vi đã xác định. Mã nhân viên có thể duy nhất trong một công ty nhưng không duy nhất trên toàn tập đoàn; SKU có thể duy nhất trong một nhà cung cấp nhưng trùng với SKU của nhà cung cấp khác. Vì vậy, phải ghi rõ phạm vi duy nhất, không mặc định một mã là duy nhất toàn hệ thống.

## 3. Khóa tự nhiên

**Khóa tự nhiên** dùng dữ liệu có ý nghĩa nghiệp vụ để nhận diện một đối tượng. Khóa có thể là một thuộc tính hoặc tổ hợp nhiều thuộc tính.

Ví dụ:

- Mã nhân viên trong một tổ chức.
- Mã quốc gia theo một bộ tiêu chuẩn xác định.
- Mã sản phẩm trong phạm vi nhà cung cấp.
- Số hiệu hợp đồng trong phạm vi đơn vị phát hành.
- Tổ hợp mã tổ chức và mã hồ sơ nếu mỗi hồ sơ chỉ duy nhất trong tổ chức đó.

Ưu điểm của khóa tự nhiên là dễ hiểu và có thể dùng để đối chiếu với nghiệp vụ hoặc hệ thống bên ngoài. Khi nhìn thấy mã nhân viên, người vận hành có thể hiểu bản ghi đại diện cho nhân viên nào mà không cần tra một bảng ánh xạ khác.

Tuy nhiên, một giá trị trông có vẻ tự nhiên chưa chắc là định danh tốt. Email có thể thay đổi, số điện thoại có thể được cấp lại, tên có thể trùng, địa chỉ có thể thay đổi, mã sản phẩm có thể bị tái sử dụng hoặc thay đổi theo chính sách nhà cung cấp. Dữ liệu có ý nghĩa với người dùng không đồng nghĩa với dữ liệu ổn định để làm khóa.

### Điều kiện để khóa tự nhiên phù hợp

Một khóa tự nhiên tốt nên đáp ứng các điều kiện sau:

1. **Duy nhất trong phạm vi rõ ràng:** hai đối tượng khác nhau không được có cùng giá trị khóa trong phạm vi áp dụng.
2. **Ổn định:** giá trị ít thay đổi trong suốt vòng đời tham chiếu của đối tượng.
3. **Không tái sử dụng:** khi đối tượng ngừng hoạt động, mã cũ không được gán cho đối tượng mới nếu hệ thống còn lưu tham chiếu lịch sử.
4. **Có mặt đúng thời điểm:** có thể xác định khi tạo đối tượng, hoặc có quy tắc rõ ràng cho giai đoạn chưa có mã.
5. **Không null và không mơ hồ:** giá trị có định dạng, quy tắc chuẩn hóa và ý nghĩa nhất quán.
6. **Không chứa thông tin nhạy cảm không cần thiết:** không dùng số định danh cá nhân, thông tin bí mật hoặc dữ liệu dễ lộ làm khóa hiển thị rộng rãi.
7. **Có chủ thể quản lý:** biết ai cấp mã, ai được thay đổi và hệ thống nào là nguồn chuẩn.

Tính duy nhất và ổn định phải được xác nhận bằng quy tắc nghiệp vụ hoặc hợp đồng dữ liệu, không chỉ dựa trên quan sát một tập dữ liệu hiện tại.

### Khóa tự nhiên đơn và khóa ghép

Khóa tự nhiên đơn gồm một thuộc tính, ví dụ country_code nếu bộ mã và phạm vi đã được xác định. Khóa ghép gồm nhiều thuộc tính, ví dụ (organization_id, employee_no).

Khóa ghép thể hiện đúng phạm vi nghiệp vụ nhưng có thể làm cho mọi khóa ngoại trở nên rộng hơn. Nếu một bảng khác tham chiếu nhân viên, nó phải lưu cả organization_id và employee_no. Điều này có thể hợp lý nếu các thành phần của khóa có ý nghĩa trong mô hình; nhưng nếu tổ hợp dài, hay thay đổi hoặc xuất hiện ở nhiều quan hệ, chi phí bảo trì sẽ tăng.

Không nên thêm một thuộc tính vào khóa chỉ vì nó đang có mặt trong màn hình hoặc API. Khóa phải tối thiểu và dựa trên quy tắc duy nhất thực sự.

## 4. Khóa thay thế

**Khóa thay thế** là định danh do hệ thống tạo ra, không mang ý nghĩa nghiệp vụ. Ví dụ: customer_id dạng số, product_id dạng UUID hoặc order_id được sinh bởi một dịch vụ định danh.

Khóa thay thế thường được chọn làm khóa chính vì nó có thể ổn định dù các thuộc tính nghiệp vụ thay đổi. Email khách hàng có thể đổi nhưng customer_id vẫn giữ nguyên; SKU có thể được chuẩn hóa hoặc thay đổi theo nhà cung cấp nhưng product_id của bản ghi sản phẩm vẫn giữ nguyên nếu nghiệp vụ coi đó là cùng một thực thể.

Các lợi ích thường gặp:

- Khóa ngắn và đơn giản hơn khóa ghép dài.
- Không phụ thuộc trực tiếp vào quy tắc mã nghiệp vụ có thể thay đổi.
- Dễ tham chiếu từ nhiều bảng khi một thực thể có nhiều định danh bên ngoài.
- Giảm việc lan truyền thay đổi khóa nghiệp vụ qua các quan hệ.
- Có thể hỗ trợ tạo bản ghi trước khi mã nghiệp vụ được cấp.
- Có thể giảm việc đưa dữ liệu nhạy cảm hoặc có ý nghĩa ra URL, log và thông điệp tích hợp.

Khóa thay thế không tự giải quyết tính duy nhất của nghiệp vụ. Nếu bảng khách hàng có customer_id tự sinh nhưng không có quy tắc duy nhất phù hợp cho mã khách hàng hoặc định danh đã xác minh, hệ thống vẫn có thể lưu hai bản ghi cùng đại diện cho một khách hàng. Khóa thay thế chỉ trả lời “đây là bản ghi nào trong hệ thống”; nó không tự trả lời “bản ghi này có trùng đối tượng nghiệp vụ nào không?”.

### Các cách tạo khóa thay thế

| Cách tạo | Đặc điểm | Điều cần cân nhắc |
|---|---|---|
| Số tăng dần/sequence | Ngắn, dễ đọc, thường có thứ tự tạo trong một nguồn cấp | Khó cấp độc lập ở nhiều node nếu không có cơ chế phân vùng; có thể làm lộ quy mô hoặc thứ tự tạo |
| UUID | Không cần một bộ đếm toàn cục đơn giản; phù hợp trao đổi định danh giữa nhiều thành phần | Dài hơn số nguyên; một số cách sinh có thể làm thứ tự ghi kém thân thiện với chỉ mục |
| ID có thời gian và thành phần phân tán | Có thể hỗ trợ tạo ở nhiều node và sắp xếp gần theo thời gian | Cần quản lý cấu trúc, đồng hồ, vùng cấp và nguy cơ va chạm theo thiết kế |
| Mã ngẫu nhiên có kiểm tra | Có thể khó đoán và thuận tiện cho định danh công khai | Phải kiểm tra va chạm; tính khó đoán không thay thế kiểm soát quyền truy cập |

Không có thuật toán sinh ID nào phù hợp mọi hệ thống. Hãy quyết định dựa trên yêu cầu phân tán, khả năng tạo ngoại tuyến, kích thước khóa, tính sắp xếp, khả năng đọc, mức độ lộ thông tin và hỗ trợ của hệ quản trị. ID không phải là cơ chế phân quyền; biết một ID không được mặc định là có quyền truy cập bản ghi.

## 5. So sánh khóa tự nhiên và khóa thay thế

| Tiêu chí | Khóa tự nhiên | Khóa thay thế |
|---|---|---|
| Nguồn gốc | Dữ liệu có ý nghĩa nghiệp vụ | Hệ thống tạo |
| Khả năng giải thích | Thường dễ hiểu với người nghiệp vụ | Thường không mang ý nghĩa |
| Độ ổn định | Phụ thuộc quy tắc nghiệp vụ và nguồn cấp | Có thể giữ ổn định khi thuộc tính nghiệp vụ thay đổi |
| Độ dài | Có thể ngắn hoặc là tổ hợp dài | Thường được thiết kế gọn hoặc có độ dài cố định |
| Phạm vi duy nhất | Phải xác định theo miền nghiệp vụ | Thường duy nhất trong hệ thống hoặc phạm vi cấp ID |
| Tích hợp | Thuận tiện khi nhiều hệ thống dùng chung mã nghiệp vụ | Cần chia sẻ ID hoặc ánh xạ ID giữa hệ thống |
| Bảo mật và riêng tư | Có thể làm lộ thông tin hoặc cấu trúc nghiệp vụ | Có thể giảm lộ thông tin, nhưng không phải biện pháp bảo mật |
| Thay đổi nghiệp vụ | Có thể kéo theo thay đổi tham chiếu nếu dùng làm PK | Thường ít ảnh hưởng đến quan hệ khi mã nghiệp vụ đổi |
| Kiểm soát trùng nghiệp vụ | Có thể biểu diễn trực tiếp bằng khóa duy nhất | Vẫn cần ràng buộc riêng trên các định danh nghiệp vụ |

Trong nhiều hệ thống, lựa chọn thực tế là **dùng khóa thay thế làm khóa chính và vẫn bảo vệ khóa tự nhiên bằng ràng buộc UNIQUE**. Cách này tách biệt định danh kỹ thuật khỏi quy tắc duy nhất của nghiệp vụ.

Dùng khóa tự nhiên trực tiếp làm khóa chính vẫn hợp lý khi mã nghiệp vụ thực sự ổn định, nhỏ gọn, có phạm vi rõ và được quản lý chặt chẽ. Không nên áp dụng một quy tắc duy nhất cho tất cả bảng.

## 6. Tiêu chí chọn khóa cho một thực thể

Có thể sử dụng quy trình quyết định sau:

### Bước 1: Xác định danh tính nghiệp vụ

Viết câu: “Hai bản ghi được xem là cùng một đối tượng khi nào?” và “Khi nào chúng chắc chắn là hai đối tượng khác nhau?”. Nếu nhóm chưa thống nhất, chưa nên chọn khóa.

Ví dụ, hai hồ sơ có cùng email có thể là một người dùng đăng ký lại, hai người dùng dùng chung email hoặc dữ liệu bị nhập trùng. Quy tắc hợp nhất phải được làm rõ trước khi coi email là khóa tự nhiên.

### Bước 2: Liệt kê khóa ứng viên

Tìm các thuộc tính hoặc tổ hợp thuộc tính có thể nhận diện duy nhất. Với mỗi ứng viên, ghi:

- Phạm vi duy nhất.
- Ai cấp và quản lý.
- Có thể thay đổi hay tái sử dụng không.
- Có sẵn khi tạo bản ghi không.
- Có thể null, trùng, sai định dạng hoặc cần chuẩn hóa không.
- Có chứa dữ liệu nhạy cảm không.
- Các hệ thống khác có phụ thuộc vào nó không.

### Bước 3: Đánh giá tính ổn định và chi phí thay đổi

Đừng chỉ hỏi “giá trị này hiện có duy nhất không?”. Hãy hỏi “nếu giá trị thay đổi sau ba năm, có bao nhiêu hệ thống, bảng, thông điệp và báo cáo bị ảnh hưởng?”. Nếu một mã có thể thay đổi hoặc được cấp lại, dùng nó làm PK thường làm tăng chi phí tiến hóa.

### Bước 4: Chọn định danh chính

Chọn khóa tự nhiên khi quy tắc nghiệp vụ ổn định, phạm vi rõ, giá trị không nhạy cảm và việc dùng nó làm tham chiếu không gây chi phí lớn. Chọn khóa thay thế khi định danh nghiệp vụ có thể đổi, dài, ghép nhiều phần, đến muộn, phụ thuộc hệ thống ngoài hoặc không thích hợp để lan truyền.

### Bước 5: Bảo vệ các khóa còn lại

Dù chọn khóa chính nào, hãy giữ lại các khóa ứng viên khác dưới dạng ràng buộc UNIQUE khi quy tắc nghiệp vụ yêu cầu. Nếu tính duy nhất chỉ áp dụng trong một phạm vi, dùng tổ hợp cột tương ứng. Nếu quy tắc thay đổi theo thời gian hoặc trạng thái, cần mô hình hóa chính xác điều kiện đó và kiểm tra khả năng hỗ trợ của hệ quản trị.

### Ma trận đánh giá gợi ý

Chấm từng ứng viên từ 0 đến 2: 0 = không đạt, 1 = có điều kiện hoặc còn rủi ro, 2 = đạt. Đây là công cụ thảo luận, không thay thế quy tắc nghiệp vụ.

| Tiêu chí | Câu hỏi | Điểm tối đa |
|---|---|---:|
| Duy nhất | Có phân biệt được mọi đối tượng trong phạm vi không? | 2 |
| Ổn định | Có giữ nguyên qua vòng đời tham chiếu không? | 2 |
| Không tái sử dụng | Đối tượng cũ ngừng hoạt động thì mã có bị cấp cho đối tượng mới không? | 2 |
| Có sẵn | Có giá trị tại thời điểm cần tạo và liên kết không? | 2 |
| Tối thiểu, đơn giản | Có ít thành phần, độ dài và quy tắc chuẩn hóa dễ quản lý không? | 2 |
| An toàn | Có tránh lộ dữ liệu nhạy cảm và thông tin không cần thiết không? | 2 |
| Quản trị được | Có chủ thể cấp mã, quy tắc sửa đổi và kiểm soát chất lượng không? | 2 |

Một ứng viên có điểm cao vẫn có thể bị loại nếu vi phạm điều kiện bắt buộc, chẳng hạn không duy nhất hoặc có thể tái sử dụng trong khi lịch sử cần phân biệt. Không cộng điểm để bù cho một lỗi định danh nghiêm trọng.

## 7. Ví dụ thiết kế: khách hàng và sản phẩm

Giả sử hệ thống bán hàng quản lý khách hàng và sản phẩm. Nhóm thống nhất:

- Mỗi khách hàng có một định danh nội bộ ổn định.
- Email có thể thay đổi và không phải khách hàng nào cũng có email riêng.
- Mã sản phẩm được quản lý theo từng nhà cung cấp.
- Mã sản phẩm có thể được thay đổi khi nhà cung cấp đổi quy tắc mã.
- Các đơn hàng cũ phải tiếp tục tham chiếu đúng sản phẩm đã bán.

Thiết kế minh họa:

~~~sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    email VARCHAR(320),
    display_name VARCHAR(160) NOT NULL
);

CREATE TABLE supplier (
    supplier_id BIGINT PRIMARY KEY,
    supplier_name VARCHAR(200) NOT NULL
);

CREATE TABLE product (
    product_id BIGINT PRIMARY KEY,
    supplier_id BIGINT NOT NULL,
    supplier_sku VARCHAR(100) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    CONSTRAINT fk_product_supplier
        FOREIGN KEY (supplier_id) REFERENCES supplier(supplier_id),
    CONSTRAINT uq_product_supplier_sku
        UNIQUE (supplier_id, supplier_sku)
);
~~~

Trong ví dụ:

- customer_id và product_id là khóa thay thế dùng làm khóa chính.
- email không được chọn làm khóa vì có thể thay đổi, không bắt buộc và có thể không duy nhất theo quy tắc đã thống nhất.
- (supplier_id, supplier_sku) là khóa ứng viên nghiệp vụ trong phạm vi nhà cung cấp; UNIQUE bảo vệ tính duy nhất đó.
- Nếu nhà cung cấp đổi SKU, product_id vẫn giữ nguyên để các đơn hàng cũ tiếp tục tham chiếu đúng bản ghi sản phẩm.
- Nếu SKU cũ có thể được tái sử dụng cho sản phẩm khác, cần lưu lịch sử mã hoặc một thực thể định danh sản phẩm theo thời gian; không được giả định UNIQUE hiện tại đã giải quyết được lịch sử.

Đơn hàng có thể tham chiếu product_id và đồng thời lưu snapshot tên, giá tại thời điểm mua. Như vậy, quan hệ đến sản phẩm hiện tại và ý nghĩa giao dịch lịch sử được phân biệt rõ.

### Khi khóa tự nhiên là lựa chọn tốt

Giả sử bảng quốc gia dùng một bộ mã tiêu chuẩn được xác định rõ, mã có phạm vi toàn bộ bộ tiêu chuẩn, ổn định và được quản lý theo phiên bản. Nếu các điều kiện này được bảo đảm, mã quốc gia có thể làm khóa chính tự nhiên. Dù vậy, tài liệu vẫn phải nói rõ bộ mã nào được dùng và cách xử lý khi tiêu chuẩn thay đổi.

### Khi khóa ghép là bản chất của thực thể

Một dòng đơn hàng thường chỉ được định danh trong phạm vi đơn hàng. Nếu nghiệp vụ đảm bảo số thứ tự dòng không lặp trong một đơn, khóa ghép (order_id, line_no) có thể là định danh tự nhiên của dòng:

Giả sử các bảng customer_order và product đã được định nghĩa trong phần mô hình giao dịch tương ứng, bảng dòng đơn hàng có thể được khai báo như sau:

~~~sql
CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT pk_order_line PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id) REFERENCES customer_order(order_id),
    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id) REFERENCES product(product_id),
    CONSTRAINT ck_line_quantity CHECK (quantity > 0)
);
~~~

Ở đây, order_id là khóa ngoại đến đơn hàng; line_no là số thứ tự có ý nghĩa trong đơn. Nếu dòng đơn hàng cần được tham chiếu độc lập bởi nhiều hệ thống hoặc có vòng đời riêng sau khi chuyển đơn, nhóm có thể cân nhắc thêm line_id thay thế nhưng vẫn giữ UNIQUE(order_id, line_no). Quyết định phải xuất phát từ nhu cầu tham chiếu và quy tắc nghiệp vụ.

## 8. Những tình huống cần cân nhắc kỹ

### Định danh bên ngoài và định danh nội bộ

Một hệ thống có thể nhận mã khách hàng từ CRM, mã người dùng từ nhà cung cấp đăng nhập và ID nội bộ. Không nên dùng một trường để đại diện cho tất cả nếu chúng có nguồn cấp, phạm vi hoặc vòng đời khác nhau.

Có thể lưu từng định danh theo cặp (issuer, external_id), trong đó issuer xác định bên cấp mã. Một bên có thể cấp nhiều loại ID; vì vậy cần mô tả rõ phạm vi và loại định danh nếu cần. Việc ánh xạ phải có quy tắc khi mã bên ngoài đổi hoặc một tài khoản được liên kết với nhiều danh tính.

### Thay đổi định danh nghiệp vụ

Nếu mã nhân viên thay đổi do chuyển tổ chức hoặc chuẩn hóa dữ liệu, hãy xác định đây là cùng một nhân viên hay một quan hệ công việc mới. Nếu cùng một thực thể, định danh nội bộ nên giữ nguyên và mã nghiệp vụ có thể được lưu trong bảng định danh có hiệu lực theo thời gian. Nếu đó là một quan hệ hoặc vai trò mới, mô hình cần thực thể riêng để lưu lịch sử.

### Gộp và tách thực thể

Khi phát hiện hai hồ sơ khách hàng trùng nhau, không nên chỉ đổi khóa của một hồ sơ rồi xóa hồ sơ còn lại. Cần xác định hồ sơ chuẩn, lưu ánh xạ ID cũ sang ID chuẩn, xử lý các tham chiếu và giữ khả năng truy vết. Khi tách một hồ sơ thành hai thực thể, phải xác định dữ liệu, quan hệ và sự kiện lịch sử nào thuộc về từng thực thể mới.

### Dữ liệu nhạy cảm và ID có thể đoán

Số định danh cá nhân, số tài khoản hoặc số điện thoại có thể có vẻ duy nhất nhưng không nên trở thành khóa hiển thị rộng rãi nếu điều đó làm lộ dữ liệu. Khóa thay thế ngẫu nhiên hoặc khó đoán có thể giảm khả năng suy ra thứ tự bản ghi, nhưng quyền truy cập vẫn phải được kiểm tra riêng ở mỗi yêu cầu.

## 9. Khóa trong các họ mô hình dữ liệu

Khái niệm định danh xuất hiện trong nhiều cách tổ chức dữ liệu, dù cách triển khai khác nhau.

| Họ mô hình | Cách định danh thường gặp | Điều cần làm rõ |
|---|---|---|
| Quan hệ | PK, candidate key, UNIQUE và FK | Phạm vi duy nhất, nullability, toàn vẹn tham chiếu và tác động khi khóa thay đổi |
| Document | Trường ID của document và các khóa nghiệp vụ trong nội dung | ID duy nhất ở phạm vi collection hay toàn cụm; nhúng hay tham chiếu; phiên bản schema |
| Đồ thị | ID node và thuộc tính nghiệp vụ của node/edge | Node đại diện cho thực thể nào; edge có định danh riêng hay không; hai node trùng nghĩa được phát hiện thế nào |
| Phân tích | Surrogate key cho dimension, khóa nghiệp vụ để đối chiếu và grain của fact | Lịch sử thay đổi, bản ghi dimension theo thời gian và cách tránh nhân đôi khi join |

Trong kho phân tích, một dimension có thể dùng surrogate key để phân biệt các phiên bản của cùng một đối tượng nghiệp vụ. Ví dụ, khi địa chỉ khách hàng thay đổi và báo cáo cần giữ lịch sử theo địa chỉ tại từng thời kỳ, mỗi phiên bản dimension có thể có một khóa thay thế riêng cùng business key chung và khoảng hiệu lực. Fact sẽ tham chiếu phiên bản dimension tương ứng với thời điểm sự kiện.

Trong document store, một document có thể có ID kỹ thuật và đồng thời chứa mã nghiệp vụ. Việc nhúng một đối tượng con không tự quyết định đối tượng con có danh tính độc lập hay không. Nếu cần tham chiếu, cập nhật hoặc quản lý vòng đời riêng, cần xem xét ID và ranh giới aggregate rõ ràng.

Trong đồ thị, ID nội bộ của node có thể khác với mã nghiệp vụ. Một node Người dùng có thể có nhiều định danh ngoài; ràng buộc duy nhất theo từng nguồn cấp giúp ngăn tạo node trùng khi đồng bộ dữ liệu.

## 10. Kiểm chứng lựa chọn khóa

Trước khi chốt mô hình, hãy kiểm tra bằng dữ liệu và kịch bản:

1. **Trùng khóa:** thử tạo hai đối tượng khác nhau cùng giá trị khóa trong đúng phạm vi.
2. **Giá trị thiếu:** thử tạo bản ghi khi định danh tự nhiên chưa có hoặc bị null.
3. **Thay đổi mã:** đổi email, SKU hoặc mã nhân viên và kiểm tra quan hệ lịch sử.
4. **Tái sử dụng mã:** ngừng một đối tượng rồi thử cấp lại mã cho đối tượng mới.
5. **Tham chiếu:** tạo dữ liệu con tham chiếu đến thực thể và kiểm tra hành vi khi thực thể bị ngừng hoạt động.
6. **Đồng bộ:** nhận lại cùng một thông điệp hoặc cùng một định danh ngoài nhiều lần; kiểm tra tính idempotent và khả năng hợp nhất.
7. **Gộp/tách:** mô phỏng hai bản ghi trùng và một bản ghi cần tách thành hai; xác minh ánh xạ tham chiếu.
8. **Quyền riêng tư:** kiểm tra ID xuất hiện trong URL, log, export và thông điệp tích hợp có làm lộ dữ liệu không cần thiết không.

Ví dụ, truy vấn sau có thể phát hiện mã SKU bị trùng trong cùng nhà cung cấp trước khi thêm ràng buộc duy nhất:

~~~sql
SELECT supplier_id, supplier_sku, COUNT(*) AS duplicate_count
FROM product
GROUP BY supplier_id, supplier_sku
HAVING COUNT(*) > 1;
~~~

Kết quả phải được xử lý theo quy tắc nghiệp vụ trước khi áp dụng ràng buộc. Không nên tự động xóa bản ghi trùng khi chưa xác định các đơn hàng và quan hệ lịch sử đang tham chiếu đến chúng.

## 11. Checklist và bài tập thực hành

### Checklist lựa chọn khóa

- [ ] Thực thể và danh tính nghiệp vụ đã được định nghĩa.
- [ ] Đã xác định phạm vi duy nhất của từng khóa ứng viên.
- [ ] Khóa tự nhiên đã được đánh giá về tính ổn định và khả năng tái sử dụng.
- [ ] Khóa thay thế có nguồn cấp và quy tắc tạo rõ ràng.
- [ ] Khóa chính tối thiểu, không null và ổn định trong vòng đời tham chiếu.
- [ ] Các định danh nghiệp vụ khác vẫn được bảo vệ bằng UNIQUE khi cần.
- [ ] Khóa ghép phản ánh đúng phạm vi nghiệp vụ và không chứa thuộc tính dư.
- [ ] Định danh bên ngoài được phân biệt với định danh nội bộ.
- [ ] Quy tắc đổi mã, gộp, tách và lưu lịch sử đã được xem xét.
- [ ] ID không bị xem như cơ chế xác thực hoặc phân quyền.
- [ ] Các truy vấn và migration quan trọng đã có kịch bản kiểm chứng.

### Bài tập

**Bài 1 — Chọn khóa cho nhân viên**

Một tổ chức có nhiều chi nhánh. Mỗi chi nhánh cấp số nhân viên riêng; nhân viên có thể chuyển chi nhánh, và mã cũ phải được lưu để kiểm toán.

Hãy đề xuất:

- Thực thể nào cần định danh?
- (branch_id, employee_no) có phải khóa ổn định của nhân viên không?
- Có nên dùng employee_id làm khóa thay thế?
- Cần lưu lịch sử mã và chi nhánh bằng cách nào?
- Quy tắc nào bảo vệ việc mã cũ không bị gán nhầm?

**Bài 2 — Chọn khóa cho sản phẩm**

Nhiều nhà cung cấp có thể dùng cùng SKU. Một nhà cung cấp có thể đổi SKU nhưng sản phẩm đã bán phải tiếp tục được nhận diện.

Hãy xác định khóa chính, khóa ứng viên, ràng buộc duy nhất và dữ liệu snapshot cần giữ trong dòng đơn hàng.

**Bài 3 — Đánh giá email làm khóa khách hàng**

Một ứng dụng cho phép người dùng đổi email, dùng email công ty hoặc email cá nhân, và có thể mời nhiều thành viên dùng chung địa chỉ email nhóm.

Hãy giải thích vì sao email có thể không đáp ứng điều kiện làm khóa tự nhiên, sau đó đề xuất định danh nội bộ và quy tắc duy nhất phù hợp.

**Bài 4 — Định danh trong kho phân tích**

Một khách hàng đổi khu vực cư trú và báo cáo cần phân tích doanh thu theo khu vực tại thời điểm phát sinh đơn hàng.

Hãy mô tả cách dùng business key và surrogate key cho dimension khách hàng, xác định khoảng hiệu lực và giải thích fact cần tham chiếu phiên bản nào.

### Tiêu chí tự đánh giá

Bài làm đạt yêu cầu khi người học có thể giải thích:

- Vì sao đối tượng được xem là một thực thể và cần danh tính riêng.
- Khóa ứng viên nào thực sự duy nhất, tối thiểu và trong phạm vi nào.
- Tại sao chọn khóa tự nhiên hoặc khóa thay thế làm khóa chính.
- Các ràng buộc nghiệp vụ vẫn được bảo vệ khi dùng khóa thay thế.
- Điều gì xảy ra khi mã nghiệp vụ thay đổi, bị tái sử dụng, hoặc thực thể được gộp/tách.
- Cách lựa chọn ảnh hưởng đến quan hệ, tích hợp, lịch sử và khả năng tiến hóa của mô hình.

Một thiết kế định danh tốt phân biệt được **danh tính của thực thể** với **các mã mà nghiệp vụ hoặc hệ thống khác dùng để gọi nó**. Khóa chính giúp hệ thống tham chiếu ổn định; khóa nghiệp vụ bảo vệ ý nghĩa và tính duy nhất theo quy tắc thực tế. Khi cả hai vai trò được xác định rõ, mô hình dữ liệu sẽ dễ tích hợp, kiểm chứng và thay đổi hơn.

