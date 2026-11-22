# Xác định phạm vi mô hình và loại bỏ chi tiết triển khai quá sớm

Trong module **DATABASE_DATA_MODELING**, mục tiêu là rèn kỹ năng chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ và ràng buộc đến lược đồ có thể triển khai; đồng thời biết so sánh các cách tổ chức dữ liệu quan hệ, document, đồ thị và phân tích. Ở bước mô hình hóa khái niệm, quyết định đầu tiên là xác định **mô hình đang mô tả phần nào của thế giới nghiệp vụ, phục vụ ai và trả lời câu hỏi nào**.

Nếu phạm vi không rõ, mô hình dễ phình ra thành bản sao của toàn doanh nghiệp, hoặc bỏ sót dữ liệu cần thiết cho một quy trình. Nếu đi quá sớm vào bảng, cột, kiểu SQL, index hay cấu trúc JSON, nhóm thiết kế có thể tối ưu một cách biểu diễn trước khi hiểu đúng vấn đề. Bài học này trình bày cách thiết lập ranh giới nghiệp vụ, chọn mức chi tiết phù hợp và giữ các quyết định triển khai ở đúng giai đoạn.

## 1. Phạm vi mô hình là gì?

Phạm vi mô hình dữ liệu là tập hợp có chủ đích gồm:

- **Miền nghiệp vụ:** lĩnh vực hoặc năng lực đang được mô tả, ví dụ quản lý đơn hàng, quản lý lịch hẹn hoặc quản lý học viên.
- **Mục tiêu sử dụng:** các quyết định, quy trình, truy vấn, báo cáo hoặc trao đổi dữ liệu mà mô hình cần hỗ trợ.
- **Đối tượng và sự kiện:** những khái niệm cần mô tả vì có ý nghĩa trong mục tiêu đó.
- **Ranh giới trách nhiệm:** dữ liệu nào do phạm vi này quản lý, dữ liệu nào thuộc hệ thống hoặc bộ phận khác.
- **Mức chi tiết:** mô hình mô tả một khách hàng, một đơn hàng, một dòng hàng, một lần thanh toán hay một sự kiện nhỏ hơn.
- **Giới hạn thời gian và vòng đời:** dữ liệu hiện tại, dữ liệu lịch sử, dữ liệu tạm thời, dữ liệu cần lưu để kiểm toán hoặc đối soát.

Phạm vi không đơn giản là danh sách bảng dự kiến. Đó là một thỏa thuận về ý nghĩa và trách nhiệm của mô hình. Hai nhóm có thể cùng nhắc đến “khách hàng” nhưng cần các phần dữ liệu khác nhau: nhóm đơn hàng cần định danh và thông tin nhận hàng tại thời điểm đặt; nhóm chăm sóc khách hàng có thể cần lịch sử liên hệ và sở thích. Không nên mặc định hai nhu cầu phải dùng cùng một cấu trúc hoặc cùng sở hữu toàn bộ dữ liệu.

### Phân biệt ba loại ranh giới

| Loại ranh giới | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Ranh giới nghiệp vụ | Quy trình hoặc năng lực nào đang được mô tả? | Quản lý đơn hàng từ lúc tạo đến khi xác nhận hoặc hủy |
| Ranh giới dữ liệu | Khái niệm nào được quản lý trong mô hình, khái niệm nào chỉ được tham chiếu? | Đơn hàng thuộc phạm vi; hồ sơ khách hàng chuẩn thuộc hệ thống khách hàng |
| Ranh giới triển khai | Dịch vụ, cơ sở dữ liệu hoặc nhóm nào sẽ lưu và xử lý dữ liệu? | Một dịch vụ đơn hàng và một hệ thống thanh toán riêng |

Ba ranh giới có liên quan nhưng không nhất thiết trùng nhau. Một mô hình khái niệm có thể mô tả quan hệ giữa nhiều hệ thống mà chưa quyết định chúng dùng chung cơ sở dữ liệu hay tách dịch vụ. Không nên suy ra ranh giới dữ liệu chỉ từ sơ đồ tổ chức hoặc sơ đồ triển khai hiện tại.

## 2. Bắt đầu từ mục tiêu và câu hỏi nghiệp vụ

Trước khi liệt kê thực thể, hãy viết một tuyên bố phạm vi ngắn. Tuyên bố này nên nói rõ đối tượng sử dụng, mục đích và điểm bắt đầu/kết thúc của quy trình.

Ví dụ:

> Mô hình quản lý đơn hàng mô tả việc tạo, xác nhận, theo dõi và hủy đơn của khách hàng. Mô hình phải hỗ trợ tra cứu nội dung đơn tại thời điểm đặt, kiểm tra kết quả thanh toán và cung cấp thông tin cần thiết cho giao vận. Hồ sơ khách hàng, danh mục sản phẩm, xử lý thanh toán và điều phối vận chuyển thuộc các phạm vi nghiệp vụ khác.

Sau tuyên bố phạm vi, liệt kê các câu hỏi mà mô hình cần trả lời:

- Ai có thể tạo đơn và đơn được tạo vào thời điểm nào?
- Một đơn hàng gồm những dòng hàng nào?
- Giá và tên sản phẩm được hiểu theo thời điểm đặt hay theo dữ liệu hiện tại?
- Một đơn có thể có nhiều lần thanh toán hoặc thử thanh toán không?
- Điều gì xảy ra khi thanh toán thất bại, đơn bị hủy hoặc giao hàng không thành công?
- Nhân viên cần tra cứu lịch sử đơn hàng để giải quyết khiếu nại như thế nào?

Câu hỏi giúp kiểm tra phạm vi thực tế. Nếu một khái niệm không giúp trả lời câu hỏi, bảo vệ quy tắc hoặc mô tả một giao tiếp bắt buộc, có thể nó chưa cần xuất hiện trong mô hình. Ngược lại, nếu một câu hỏi quan trọng không có khái niệm hoặc dữ liệu nào hỗ trợ, phạm vi đang thiếu.

Không nên chỉ dựa vào danh từ trong tài liệu yêu cầu. Từ “đơn hàng” có thể bao gồm nhiều khái niệm khác nhau: đơn, dòng hàng, lần thanh toán, phiếu giao, lần giao, hoàn tiền và lịch sử trạng thái. Hãy xem xét động từ và sự kiện đi kèm: tạo, thêm dòng, xác nhận, thanh toán, hủy, hoàn tiền, bàn giao, giao thành công.

## 3. Vẽ ranh giới với hệ thống và bên liên quan

Sơ đồ ngữ cảnh cho thấy phạm vi đang xét và các tác nhân hoặc hệ thống trao đổi dữ liệu với nó. Sơ đồ này không cần mô tả công nghệ hay giao thức; mục tiêu là làm rõ thông tin đi qua ranh giới.

Ví dụ với phạm vi quản lý đơn hàng:

~~~mermaid
flowchart LR
    Customer[Khách hàng]
    subgraph OrderScope["Phạm vi: Quản lý đơn hàng"]
        Order[Đơn hàng]
        Lines[Dòng hàng]
        Snapshot[Thông tin sản phẩm và giao nhận tại thời điểm đặt]
        Order --> Lines
        Order --> Snapshot
    end
    Payment[Hệ thống thanh toán]
    Shipping[Hệ thống giao vận]
    Customer -->|Yêu cầu đặt hoặc hủy| Order
    Order -->|Yêu cầu thu tiền| Payment
    Payment -->|Kết quả và mã giao dịch| Order
    Order -->|Thông tin cần giao| Shipping
    Shipping -->|Trạng thái giao hàng| Order
~~~

Sơ đồ cho thấy phạm vi đơn hàng cần biết kết quả thanh toán và trạng thái giao hàng. Nó không cần mô tả cách hệ thống thanh toán xác thực thẻ, kết nối ngân hàng hoặc xử lý sổ cái; cũng không cần mô tả thuật toán chọn tuyến giao hàng. Những phần đó thuộc phạm vi khác.

Với mỗi đường trao đổi, ghi rõ:

1. Bên gửi và bên nhận là ai?
2. Sự kiện nào làm phát sinh trao đổi?
3. Dữ liệu tối thiểu nào cần đi qua ranh giới?
4. Bên nào chịu trách nhiệm về ý nghĩa và độ đúng của dữ liệu?
5. Nếu dữ liệu đến trễ, lặp lại hoặc không đến thì nghiệp vụ xử lý thế nào?

Ở bước khái niệm, câu trả lời có thể ở mức nghiệp vụ. Chẳng hạn “hệ thống thanh toán gửi kết quả và mã giao dịch” là đủ để xác định thông tin cần có; chưa cần chọn webhook, hàng đợi, REST hay định dạng JSON.

### Phân biệt dữ liệu sở hữu và dữ liệu tham chiếu

Một khái niệm có thể xuất hiện trong mô hình mà không có nghĩa phạm vi đó sở hữu toàn bộ dữ liệu của nó.

| Khái niệm | Vai trò trong phạm vi đơn hàng | Cách xác định trách nhiệm |
|---|---|---|
| Đơn hàng | Đối tượng trung tâm, có vòng đời riêng | Phạm vi đơn hàng quản lý |
| Khách hàng | Chủ thể đặt đơn | Hệ thống khách hàng quản lý hồ sơ chuẩn; đơn hàng giữ định danh và thông tin cần cho giao dịch |
| Sản phẩm | Đối tượng được mua | Danh mục sản phẩm quản lý dữ liệu hiện tại; đơn hàng giữ thông tin snapshot cần để giải thích giao dịch |
| Kết quả thanh toán | Thông tin cần để xác nhận hoặc xử lý đơn | Hệ thống thanh toán quản lý nghiệp vụ thanh toán; đơn hàng tham chiếu kết quả và mã giao dịch |
| Giao vận | Trạng thái thực hiện giao hàng | Hệ thống giao vận quản lý quy trình giao; đơn hàng nhận trạng thái cần cho người dùng |

Sự phân biệt này tránh hai lỗi: sao chép toàn bộ dữ liệu của hệ thống khác vào mô hình hiện tại, hoặc chỉ lưu một tham chiếu nhưng không giữ lại dữ liệu lịch sử mà nghiệp vụ cần.

## 4. Quyết định khái niệm nào nằm trong phạm vi

Có thể đánh giá một khái niệm ứng viên bằng các câu hỏi sau:

- Nó có danh tính hoặc vòng đời riêng trong nghiệp vụ không?
- Nó có thuộc tính, quan hệ hoặc quy tắc cần quản lý không?
- Nó có cần được lưu lại sau khi quy trình kết thúc không?
- Một câu hỏi hoặc kịch bản thuộc mục tiêu mô hình có cần đến nó không?
- Phạm vi hiện tại chịu trách nhiệm về dữ liệu chuẩn của nó hay chỉ cần tham chiếu?
- Nếu bỏ nó đi, có quy tắc hoặc quyết định nghiệp vụ nào không thể giải thích được không?

Một khái niệm thường thuộc mô hình khi nó có ý nghĩa nghiệp vụ độc lập hoặc là điều kiện cần để mô tả một quy tắc trong phạm vi. Khái niệm bên ngoài vẫn có thể xuất hiện dưới dạng tham chiếu hoặc thông tin giao tiếp.

### Bảng trong phạm vi, ngoài phạm vi và giao tiếp

| Phân loại | Ý nghĩa | Ví dụ trong quản lý đơn hàng |
|---|---|---|
| Trong phạm vi | Được mô tả và quản lý trực tiếp | Đơn hàng, dòng hàng, trạng thái đơn |
| Ngoài phạm vi | Có nghiệp vụ riêng, không mô hình hóa chi tiết ở đây | Xác thực thanh toán, quản lý tồn kho, điều phối tuyến giao |
| Giao tiếp/tham chiếu | Cần một phần thông tin để thực hiện quy trình | Mã khách hàng, mã sản phẩm, kết quả thanh toán, trạng thái giao |

Không nên hiểu “ngoài phạm vi” là “không liên quan”. Một quy trình ngoài phạm vi vẫn có thể cung cấp dữ liệu cần thiết. Điểm cần ghi rõ là mô hình hiện tại nhận hoặc gửi thông tin gì, và ai chịu trách nhiệm cho ý nghĩa của nó.

### Ghi rõ những gì chưa giải quyết

Tạo danh sách giả định và câu hỏi mở thay vì âm thầm biến giả định thành thiết kế. Ví dụ:

| Câu hỏi | Giả định tạm thời | Khi nào cần quyết định |
|---|---|---|
| Có cho phép một đơn chứa sản phẩm từ nhiều nhà bán không? | Chưa hỗ trợ nhiều nhà bán | Trước khi mở rộng nghiệp vụ marketplace |
| Đơn hàng có thể thanh toán nhiều lần không? | Có thể có nhiều lần thử thanh toán | Khi xác nhận quy trình thanh toán và đối soát |
| Có cần lưu lịch sử mọi lần thay đổi địa chỉ giao không? | Lưu snapshot địa chỉ khi đặt và sự kiện thay đổi quan trọng | Khi có yêu cầu kiểm toán hoặc khiếu nại |
| Đơn đã hủy có được khôi phục không? | Chưa cho phép khôi phục | Khi nghiệp vụ định nghĩa quy trình phục hồi |

Mỗi giả định nên có người xác nhận hoặc điều kiện để xem xét lại. Nếu một giả định ảnh hưởng đến khóa, vòng đời, quan hệ hoặc khả năng giữ lịch sử, cần giải quyết trước khi chốt mô hình logic.

## 5. Giữ đúng mức trừu tượng: mô hình khái niệm chưa phải thiết kế triển khai

Mô hình khái niệm mô tả các khái niệm trong miền nghiệp vụ, thuộc tính có ý nghĩa, quan hệ và quy tắc. Nó nên dễ đọc với cả người nghiệp vụ lẫn người kỹ thuật, không yêu cầu người đọc biết hệ quản trị cơ sở dữ liệu đang dùng.

| Câu hỏi | Ở mức khái niệm | Chi tiết nên để giai đoạn sau |
|---|---|---|
| Đối tượng nào tồn tại? | Khách hàng, Đơn hàng, Dòng hàng | Tên bảng, tên class, tên collection |
| Đối tượng có đặc điểm gì? | Ngày đặt, trạng thái, số lượng, giá tại thời điểm mua | VARCHAR(…), DECIMAL(p,s), kiểu enum của một DB cụ thể |
| Định danh có ý nghĩa gì? | Mỗi đơn hàng được nhận diện duy nhất trong nghiệp vụ | BIGINT tự tăng, UUID, sequence hoặc cách sinh ID |
| Các đối tượng liên hệ ra sao? | Một đơn có một hoặc nhiều dòng hàng | Cột FK, bảng join, embedding hoặc document reference |
| Quy tắc nào phải đúng? | Số lượng dương; đơn đã xác nhận phải có dòng hàng | CHECK, trigger, transaction, validator hoặc stored procedure |
| Truy vấn nào cần hỗ trợ? | Tra cứu đơn của khách hàng theo thời gian | B-tree, composite index, partition, cache hoặc query plan |
| Dữ liệu được tổ chức thế nào? | Một đơn bao gồm các dòng hàng và snapshot liên quan | Chuẩn hóa bảng, document aggregate, graph traversal hay fact table |

Một số thông tin kỹ thuật có thể được ghi ở tài liệu quyết định riêng, nhưng không nên để chúng chi phối sơ đồ khái niệm. Ví dụ, quan hệ “một đơn hàng có nhiều dòng hàng” vẫn đúng dù sau này các dòng hàng được lưu trong bảng riêng, nhúng trong document hay được chuyển sang một cấu trúc phục vụ phân tích.

### Những dấu hiệu đang đi quá sớm vào triển khai

- Bắt đầu sơ đồ bằng CREATE TABLE, kiểu SQL hoặc tên cột vật lý trước khi thống nhất thuật ngữ nghiệp vụ.
- Chọn UUID, số tự tăng hoặc quy tắc sinh khóa trước khi xác định ý nghĩa định danh và phạm vi duy nhất.
- Quyết định index, partition, sharding hoặc cache khi chưa biết truy vấn và quy mô cần phục vụ.
- Mô hình hóa theo class của ORM, DTO của API hoặc cấu trúc màn hình hiện tại.
- Nhúng hoặc tách document chỉ vì công nghệ đang dùng hỗ trợ một cách nào đó.
- Thêm trường kỹ thuật như created_by_service, retry_count, json_payload vào mô hình khái niệm mà chưa chỉ ra ý nghĩa nghiệp vụ.
- Dùng tên bảng hoặc tên cột để thay cho định nghĩa rõ ràng của một khái niệm.

Điều này không có nghĩa phải bỏ qua các yêu cầu phi chức năng. Bảo mật, lưu giữ, khả năng kiểm toán, khối lượng và độ trễ có thể ảnh hưởng trực tiếp đến phạm vi dữ liệu. Hãy ghi nhận chúng dưới dạng yêu cầu hoặc ràng buộc; chỉ trì hoãn cách hiện thực cụ thể cho đến khi có đủ thông tin.

## 6. Ví dụ: xác định phạm vi cho quản lý đơn hàng

Giả sử cửa hàng cần một mô hình để tạo đơn, xem lại nội dung đã mua, xác nhận thanh toán và theo dõi giao hàng. Nhóm nghiệp vụ thống nhất:

- Một khách hàng có thể tạo nhiều đơn hàng.
- Mỗi đơn hàng có một hoặc nhiều dòng hàng khi được xác nhận.
- Mỗi dòng hàng tham chiếu một sản phẩm và ghi nhận tên, giá tại thời điểm đặt.
- Một đơn có thể có nhiều lần thử thanh toán.
- Đơn hàng cần biết kết quả thanh toán và trạng thái giao hàng.
- Hồ sơ khách hàng, danh mục sản phẩm, xử lý thanh toán và điều phối giao hàng được quản lý ở phạm vi khác.

### Ranh giới đã chọn

| Nội dung | Quyết định | Lý do |
|---|---|---|
| Đơn hàng và dòng hàng | Mô hình hóa trực tiếp | Đây là dữ liệu trung tâm của quy trình |
| Định danh khách hàng | Tham chiếu | Hồ sơ chuẩn do hệ thống khách hàng quản lý |
| Tên và giá sản phẩm tại thời điểm đặt | Lưu như dữ liệu lịch sử của đơn | Giá và tên hiện tại có thể thay đổi |
| Chi tiết thẻ và quy trình thu tiền | Ngoài phạm vi | Hệ thống thanh toán chịu trách nhiệm |
| Mã giao dịch và kết quả thanh toán | Mô hình hóa phần thông tin nhận được | Cần để xác nhận, đối soát và xử lý đơn |
| Thuật toán chọn tuyến giao hàng | Ngoài phạm vi | Hệ thống giao vận chịu trách nhiệm |
| Trạng thái giao hàng | Tham chiếu như thông tin trạng thái | Người dùng cần theo dõi tiến độ đơn |

### Mô hình khái niệm ban đầu

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--o{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : identifies
    ORDER ||--o{ PAYMENT_ATTEMPT : has
~~~

Sơ đồ chỉ biểu diễn khái niệm và quan hệ cần thiết. CUSTOMER và PRODUCT ở đây là các khái niệm được tham chiếu; nó không khẳng định phạm vi đơn hàng sở hữu toàn bộ hồ sơ khách hàng hoặc danh mục sản phẩm. PAYMENT_ATTEMPT mô tả lần thử và kết quả mà quy trình đơn hàng cần biết, không mô tả chi tiết xử lý thanh toán bên ngoài.

Một số điểm cần xác minh với nghiệp vụ trước khi chuyển sang mô hình logic:

1. “Một hoặc nhiều dòng hàng” áp dụng từ thời điểm tạo đơn hay chỉ khi đơn được xác nhận? Đơn nháp có thể chưa có dòng hàng không?
2. Có thể thử thanh toán lại sau thất bại không? Mỗi lần thử có mã tham chiếu riêng không?
3. Đơn đã thanh toán nhưng bị hủy có tạo một sự kiện hoàn tiền không? Nếu có, phạm vi đơn hàng chỉ cần kết quả hoàn tiền hay cần mô hình cả vòng đời hoàn tiền?
4. Có cho phép thay đổi dòng hàng sau khi thanh toán không? Nếu có, lịch sử cần thể hiện điều gì?
5. Địa chỉ giao hàng được chụp tại lúc đặt hay có thể thay đổi trước khi bàn giao?

Các câu hỏi này xác định ý nghĩa và vòng đời dữ liệu. Chúng cần được trả lời trước khi chọn cách lưu thành bảng, document hay cấu trúc khác.

## 7. Quy trình thực hiện trong một buổi phân tích phạm vi

Có thể dùng quy trình sau cho một bài toán mới:

1. **Viết mục tiêu:** nêu quy trình, người sử dụng và quyết định mà mô hình cần hỗ trợ.
2. **Liệt kê kịch bản:** mô tả các luồng chính, luồng ngoại lệ và các sự kiện làm thay đổi dữ liệu.
3. **Tạo danh sách khái niệm ứng viên:** lấy từ danh từ, động từ, trạng thái và quy tắc; chưa biến chúng thành bảng.
4. **Vẽ sơ đồ ngữ cảnh:** đặt phạm vi ở trung tâm, thể hiện tác nhân, hệ thống liên quan và dữ liệu đi qua ranh giới.
5. **Phân loại khái niệm:** trong phạm vi, ngoài phạm vi hoặc chỉ tham chiếu; ghi rõ lý do và nguồn dữ liệu chuẩn.
6. **Chọn mức chi tiết:** xác định đối tượng, sự kiện và lịch sử nào cần được mô tả; tránh chi tiết không giúp trả lời mục tiêu.
7. **Ghi giả định và câu hỏi mở:** nêu tác động của từng giả định, người cần xác nhận và thời điểm phải quyết định.
8. **Kiểm chứng bằng kịch bản:** lần theo dữ liệu từ đầu đến cuối quy trình, bao gồm lỗi, hủy, thay đổi và tra cứu lịch sử.
9. **Chốt đầu ra:** công bố tuyên bố phạm vi, sơ đồ ngữ cảnh, thuật ngữ, danh sách khái niệm và các quyết định còn mở.

### Bộ đầu ra tối thiểu

| Đầu ra | Nội dung cần có |
|---|---|
| Tuyên bố phạm vi | Mục tiêu, người sử dụng, quy trình bắt đầu/kết thúc |
| Sơ đồ ngữ cảnh | Tác nhân, hệ thống liên quan và trao đổi dữ liệu |
| Danh sách khái niệm | Định nghĩa, vai trò, trạng thái trong/ngoài/tham chiếu |
| Từ điển thuật ngữ | Tên chuẩn, định nghĩa và ví dụ |
| Danh sách quy tắc | Điều kiện, ngoại lệ, vòng đời và lịch sử |
| Giả định/câu hỏi mở | Nội dung chưa xác nhận, tác động và người chịu trách nhiệm |
| Nhật ký quyết định | Lý do chọn phạm vi, phương án bị loại và điều kiện xem xét lại |

## 8. Kiểm tra phạm vi trước khi chuyển sang mô hình logic

Một phạm vi đủ rõ khi người nghiệp vụ và người kỹ thuật có thể cùng trả lời nhất quán các câu hỏi sau:

- [ ] Mục tiêu và người sử dụng mô hình đã được nêu rõ.
- [ ] Điểm bắt đầu, điểm kết thúc và các kịch bản chính của quy trình đã được xác định.
- [ ] Các khái niệm trung tâm có định nghĩa thống nhất.
- [ ] Ranh giới với hệ thống khác và dữ liệu tham chiếu đã được chỉ rõ.
- [ ] Có quyết định về dữ liệu hiện tại, snapshot và lịch sử cần lưu.
- [ ] Các quy tắc và trường hợp ngoại lệ quan trọng đã được ghi nhận.
- [ ] Nội dung ngoài phạm vi có lý do và đầu mối chịu trách nhiệm.
- [ ] Giả định có tác động lớn đã có người xác nhận hoặc lịch xử lý.
- [ ] Mô hình chưa bị chi phối bởi tên bảng, kiểu SQL, index, ORM hay công nghệ lưu trữ cụ thể.
- [ ] Có thể dùng sơ đồ và ví dụ để giải thích phạm vi cho người mới tham gia dự án.

Sau khi phạm vi được thống nhất, nhóm mới chuyển các khái niệm thành mô hình logic: xác định khóa ứng viên, quan hệ, ràng buộc và phụ thuộc dữ liệu; sau đó mới cân nhắc chuẩn hóa, kiểu dữ liệu, chỉ mục và lược đồ vật lý. Khi chọn quan hệ, document, đồ thị hay mô hình phân tích, hãy dựa trên cùng tập yêu cầu và ranh giới đã được xác nhận. Nhờ vậy, các phương án có thể được so sánh công bằng mà không nhầm quyết định công nghệ với ý nghĩa nghiệp vụ.

Một mô hình khái niệm tốt bắt đầu bằng ranh giới có thể giải thích được. Nó bao gồm đủ dữ liệu để trả lời các câu hỏi trong phạm vi, chỉ tham chiếu phần thuộc trách nhiệm nơi khác, và giữ các chi tiết triển khai ở giai đoạn phù hợp. Khi mục tiêu, khái niệm, trách nhiệm và giả định đã rõ, việc chuyển sang mô hình logic và vật lý sẽ có cơ sở để kiểm chứng và tiến hóa.

