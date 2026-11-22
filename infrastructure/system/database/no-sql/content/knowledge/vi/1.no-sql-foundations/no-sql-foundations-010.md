# Bài toán phù hợp, giới hạn và các tình huống nên ưu tiên hệ quan hệ

## 1. Bắt đầu từ bài toán, không bắt đầu từ tên công nghệ

NoSQL là tên gọi chung cho nhiều kiểu cơ sở dữ liệu không lấy mô hình bảng quan hệ và SQL làm trung tâm. Một hệ **key–value**, **document**, **wide-column** và **graph** có cách lưu trữ, truy vấn, phân phối và bảo đảm tính nhất quán rất khác nhau. Vì vậy, câu hỏi “Có nên dùng NoSQL không?” chưa đủ cụ thể; cần hỏi **loại NoSQL nào, cho dữ liệu nào, với truy vấn và ràng buộc nào**.

Lựa chọn cơ sở dữ liệu là quyết định về những gì hệ thống phải làm đúng và làm thường xuyên:

- **Truy cập dữ liệu:** Hệ thống thường đọc bằng khóa, lấy một đối tượng hoàn chỉnh, tìm kiếm theo nhiều điều kiện, thực hiện phép nối hay đi qua nhiều tầng quan hệ?
- **Ranh giới giao dịch:** Một thao tác nghiệp vụ có cần cập nhật nhiều bản ghi/thực thể theo nguyên tắc “tất cả thành công hoặc tất cả thất bại” không?
- **Bất biến dữ liệu:** Có cần khóa ngoại, ràng buộc duy nhất, kiểm tra số dư, tồn kho không âm hoặc thứ tự xử lý nghiêm ngặt không?
- **Tải và quy mô:** Số lượt đọc/ghi, dung lượng, tốc độ tăng trưởng, độ trễ mục tiêu và phân bố khóa truy cập thực tế là bao nhiêu?
- **Vận hành:** Đội ngũ cần sao lưu, khôi phục, kiểm toán, đổi cấu trúc dữ liệu, quan sát hệ thống và khắc phục sự cố như thế nào?

NoSQL thường hấp dẫn khi mô hình dữ liệu và cách truy cập khớp với thế mạnh chuyên biệt của nó. Cơ sở dữ liệu quan hệ (RDBMS) thường là lựa chọn vững chắc khi tính toàn vẹn, giao dịch và truy vấn liên kết là trọng tâm. Quy mô lớn hoặc dữ liệu nhiều dạng **không tự động** đồng nghĩa với việc phải chuyển sang NoSQL: nhiều hệ quan hệ hiện đại hỗ trợ JSON, chỉ mục, phân vùng bảng, replica và mở rộng phù hợp với nhiều hệ thống lớn.

## 2. Những bài toán thường phù hợp với NoSQL

### 2.1. Đọc/ghi theo khóa: key–value

Giả sử ứng dụng quản lý phiên đăng nhập hoặc một giá trị đếm số yêu cầu trong khoảng thời gian ngắn. Ứng dụng biết khóa cần truy cập, muốn lấy hoặc cập nhật nhanh một giá trị và có thể cần thời hạn tự hết hiệu lực (**TTL**).

Ví dụ biểu diễn khái niệm:

~~~text
session:user-481:device-2 -> { userId: 481, lastSeen: "...", expiresAt: "..." }
rate-limit:api-key-17:minute-2026-11-14T08:30 -> 43
~~~

Một kho key–value có thể phù hợp cho cache, phiên, token ngắn hạn, bộ đếm hoặc trạng thái tạm. Tuy nhiên, phải phân biệt **dữ liệu có thể tạo lại** với **dữ liệu nghiệp vụ gốc**. Nếu mất một bản cache, ứng dụng có thể tải lại từ nguồn chính; nếu mất sổ cái thanh toán, hậu quả khác hoàn toàn. TTL, chính sách ghi xuống đĩa, nhân bản và phục hồi cần phù hợp với mức mất dữ liệu được phép.

Key–value kém thuận tiện khi câu hỏi trở thành “lọc tất cả khách hàng theo ba thuộc tính, kết hợp hợp đồng và tính tổng doanh thu theo khu vực”, vì truy cập theo khóa không giải quyết tự nhiên các phép lọc và nối tùy ý.

### 2.2. Đọc/ghi theo một đối tượng tổng hợp: document

Một danh mục sản phẩm có nhóm thuộc tính khác nhau cho điện thoại, sách, quần áo hoặc thiết bị. Mỗi sản phẩm thường được lấy như một khối để hiển thị. Document database cho phép biểu diễn cấu trúc lồng nhau tương đối gần với dữ liệu mà API trả về.

~~~json
{
  "productId": "P-104",
  "name": "Tai nghe không dây",
  "category": "audio",
  "attributes": {
    "color": "đen",
    "batteryHours": 24,
    "noiseCancellation": true
  },
  "variants": [
    { "sku": "P-104-BLK", "color": "đen" },
    { "sku": "P-104-WHT", "color": "trắng" }
  ]
}
~~~

**Nhúng dữ liệu** có ích khi thông tin thường được đọc cùng nhau, kích thước đối tượng có giới hạn và việc sửa có thể thực hiện trong phạm vi một document. Mỗi document lúc này có thể xem như một **aggregate**: một đơn vị dữ liệu mà ứng dụng quản lý cùng nhau.

Nhưng không nên mặc định nhúng mọi thứ. Chẳng hạn, toàn bộ lịch sử mua hàng vào một document khách hàng sẽ khiến document lớn dần vô hạn; nhúng hàng nghìn đánh giá có thể làm tăng chi phí đọc/ghi; lưu cùng một mức giá ở hàng triệu document khiến việc thay đổi giá trở thành cập nhật hàng loạt. Những quan hệ nhiều–nhiều hoặc cập nhật đồng thời nhiều thực thể có thể phù hợp hơn với thiết kế quan hệ.

Document database cũng có thể hỗ trợ chỉ mục, schema validation và giao dịch nhiều document ở một số sản phẩm. Khả năng cụ thể, phạm vi bảo đảm và chi phí cần kiểm tra theo hệ quản trị và cấu hình đang dùng; “document” không có nghĩa là luôn thiếu giao dịch.

### 2.3. Luồng ghi lớn và truy vấn có quy luật: wide-column hoặc time-series

Ví dụ, mỗi thiết bị gửi nhiệt độ và trạng thái vài giây một lần. Ứng dụng chủ yếu hỏi: “Lấy dữ liệu của thiết bị A trong 24 giờ gần nhất”, ít cần nối tùy ý với nhiều bảng nghiệp vụ.

~~~text
partition key: deviceId + ngày
clustering key: eventTimestamp
value: temperature, battery, status
~~~

Một mô hình wide-column được thiết kế theo **partition key**, thứ tự dữ liệu và truy vấn chủ đạo có thể xử lý tốt tải ghi phân tán. Cơ sở dữ liệu time-series chuyên dụng cũng đáng cân nhắc cho dữ liệu theo thời gian, lưu giữ theo kỳ và tổng hợp theo cửa sổ.

Điều kiện quan trọng là phải phân bố khóa hợp lý. Nếu mọi sự kiện cùng đổ vào một partition “today”, phân phối tải có thể thất bại dù hệ thống quảng bá khả năng mở rộng ngang. Cần quan tâm đến kích thước partition, **hot key/hot partition**, truy vấn đi qua nhiều partition, thời hạn giữ dữ liệu, nén, compaction và nhu cầu truy vấn lịch sử.

Nếu lượng sự kiện còn nhỏ, cần truy vấn SQL linh hoạt hoặc đã có hạ tầng quan hệ đủ sức đáp ứng, một bảng phân vùng theo thời gian trong RDBMS có thể đơn giản hơn về vận hành.

### 2.4. Truy vấn nhiều bước theo quan hệ: graph

Một hệ thống phát hiện gian lận có thể cần tìm các tài khoản chia sẻ thiết bị, địa chỉ giao hàng hoặc phương thức thanh toán qua nhiều bước. Mạng quan hệ này được mô tả tự nhiên bằng **đỉnh**, **cạnh** và thuộc tính.

~~~text
(Khách A) --sử dụng--> (Thiết bị X)
(Khách B) --sử dụng--> (Thiết bị X)
(Khách B) --thanh toán bằng--> (Thẻ Y)
~~~

Graph database đáng xem xét khi truy vấn đi qua số tầng quan hệ biến đổi, cần khám phá đường đi, cộng đồng hay mẫu kết nối phức tạp. Ngược lại, quan hệ “đơn hàng thuộc khách hàng” và một vài phép JOIN thông thường chưa đủ là lý do chuyển sang graph: RDBMS xử lý tốt rất nhiều quan hệ có cấu trúc rõ ràng.

### 2.5. Chỉ mục tìm kiếm như một thành phần chuyên biệt

Tìm kiếm toàn văn, gợi ý từ khóa, xếp hạng độ liên quan và lọc đa chiều có thể được phục vụ bằng search engine. Đây thường là **chỉ mục phục vụ đọc**, được cập nhật từ cơ sở dữ liệu nghiệp vụ. Search index không nên tự động được coi là nguồn sự thật cho đơn hàng, tồn kho hay thanh toán. Nếu việc đồng bộ là bất đồng bộ, kết quả tìm kiếm có thể trễ trong một khoảng thời gian và ứng dụng phải xử lý tình huống đó.

## 3. Khi nào nên ưu tiên hệ quản trị cơ sở dữ liệu quan hệ?

### 3.1. Nghiệp vụ có giao dịch nhiều thực thể và bất biến nghiêm ngặt

Xét quy trình đặt hàng: tạo đơn, thêm dòng hàng và trừ tồn kho. Ta muốn tránh trường hợp đơn đã được ghi nhưng tồn kho chưa trừ, hoặc hai khách cùng mua vượt quá số lượng còn lại.

Một thiết kế quan hệ có thể sử dụng các bảng:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL REFERENCES orders(id),
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    quantity INT NOT NULL CHECK (quantity >= 0)
);
~~~

Khi xử lý một đơn, ứng dụng có thể đặt các thay đổi **trong cùng giao dịch SQL**: trừ tồn kho bằng câu UPDATE có điều kiện, kiểm tra số hàng bị tác động, sau đó tạo đơn và dòng hàng; nếu bước nào thất bại thì ROLLBACK. Ví dụ thao tác cốt lõi:

~~~sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 104 AND quantity >= 2;
-- Bắt buộc kiểm tra số hàng được cập nhật = 1;
-- nếu bằng 0 thì ROLLBACK, không tạo đơn hàng.

-- INSERT INTO orders (...);
-- INSERT INTO order_items (...);

COMMIT;
~~~

Đây là minh họa nguyên tắc, chưa phải một luồng đặt hàng chạy độc lập: ứng dụng vẫn phải cấp ID, kiểm tra kết quả UPDATE, xử lý lỗi và chọn mức cô lập giao dịch phù hợp. Cơ sở dữ liệu quan hệ hỗ trợ tập trung những nguyên tắc này bằng **ACID**, khóa/ràng buộc và cơ chế kiểm soát đồng thời.

Lưu ý ranh giới quan trọng: một giao dịch SQL **không** tự động bao trùm dịch vụ thanh toán bên ngoài hoặc nhiều cơ sở dữ liệu độc lập. Khi có các bước qua mạng, ứng dụng cần cơ chế như idempotency, outbox, saga, trạng thái trung gian và đối soát; không có loại cơ sở dữ liệu nào làm biến mất bài toán phân tán.

### 3.2. Nhiều quan hệ chéo và truy vấn thay đổi liên tục

Hệ thống quản lý nhân sự, kế toán, quản trị doanh nghiệp hoặc thương mại thường có các thực thể dùng chung: khách hàng, hóa đơn, sản phẩm, hợp đồng, chi nhánh, người duyệt. Một yêu cầu báo cáo mới có thể cần JOIN nhiều bảng, lọc theo nhiều điều kiện và tổng hợp theo giai đoạn.

Thiết kế chuẩn hóa trong RDBMS giúp dữ liệu chia sẻ có một nơi quản lý chính, giảm cập nhật lặp và thể hiện rõ quan hệ bằng khóa ngoại. SQL mang lại khả năng truy vấn kết hợp, tổng hợp và phân tích nghiệp vụ rất linh hoạt khi điều kiện báo cáo chưa biết hết từ đầu.

Ở document/wide-column, thiết kế thường tối ưu cho các kiểu truy vấn đã biết. Truy vấn mới đôi khi yêu cầu thêm chỉ mục, tạo bản chiếu dữ liệu hoặc xây lại mô hình lưu trữ. Nếu nhu cầu JOIN và báo cáo ad hoc là cốt lõi, hệ quan hệ thường giúp giảm độ phức tạp.

### 3.3. Cần toàn vẹn dữ liệu có thể diễn đạt trong cơ sở dữ liệu

Các yêu cầu như “mỗi email trong một phạm vi tenant phải duy nhất”, “dòng hóa đơn phải tham chiếu hóa đơn hợp lệ”, “số lượng phải dương”, “bản ghi con không được mồ côi” phù hợp với UNIQUE, FOREIGN KEY, CHECK và các cơ chế giao dịch của RDBMS.

Một số NoSQL cũng có ràng buộc và validation, nhưng phạm vi của chúng khác nhau. Khi nhiều ràng buộc tham chiếu qua tập dữ liệu lớn, việc tự kiểm tra ở tầng ứng dụng làm tăng số nơi có thể xảy ra lỗi và số tình huống cạnh tranh phải xử lý.

### 3.4. Tính ổn định và khả năng vận hành quan trọng hơn đổi mô hình

Hệ quan hệ nên được cân nhắc đầu tiên khi:

- Mô hình nghiệp vụ khá rõ, nhiều thực thể liên kết và lượng dữ liệu/tải nằm trong khả năng đáp ứng của hệ quan hệ.
- Đội ngũ đã có quy trình migration, backup/restore, giám sát, audit và năng lực tối ưu SQL.
- Sản phẩm cần nhiều báo cáo, truy vấn điều tra sự cố, truy vết lịch sử và công cụ BI.
- Một sai sót dữ liệu có chi phí lớn hơn lợi ích của tối ưu tốc độ đọc ở một vài màn hình.

Việc giữ một hệ quan hệ làm nguồn dữ liệu chính, bổ sung cache hoặc chỉ mục tìm kiếm khi cần, thường tạo ra ít rủi ro hơn việc chuyển toàn bộ dữ liệu sang NoSQL chỉ vì dự đoán sẽ có “nhiều người dùng”.

## 4. Bảng định hướng theo nhu cầu

| Nhu cầu nổi bật | Phương án nên đánh giá sớm | Câu hỏi cần xác minh |
| --- | --- | --- |
| Phiên, cache, đếm giới hạn tần suất; đọc theo khóa, TTL | Key–value | Mất dữ liệu có chấp nhận được không? Có cần lưu bền vững? |
| Đối tượng có thuộc tính biến thiên, thường đọc nguyên khối | Document hoặc SQL có JSON | Kích thước có giới hạn? Có cập nhật chéo nhiều đối tượng? |
| Sự kiện theo thiết bị/thời gian, ghi lớn, truy vấn theo khóa cố định | Wide-column hoặc time-series | Phân bố partition có đều? Cần truy vấn ad hoc tới đâu? |
| Khám phá đường đi và quan hệ nhiều bước | Graph | Có thật sự cần traversal sâu, hay JOIN thông thường đã đủ? |
| Đơn hàng, tồn kho, ví tiền, sổ cái, nhiều ràng buộc giao dịch | Quan hệ | Bất biến nào phải được bảo vệ trong một transaction? |
| Báo cáo kết hợp nhiều thực thể, bộ lọc thay đổi | Quan hệ; có thể kết hợp kho phân tích | Dữ liệu thời gian thực hay báo cáo theo lô? |
| Tìm kiếm toàn văn, xếp hạng kết quả | Search index đi cùng nguồn dữ liệu chính | Chấp nhận độ trễ đồng bộ bao lâu? |

Bảng này là **điểm bắt đầu cho đánh giá**, không phải một luật ánh xạ cứng. Cùng một sản phẩm có thể dùng SQL làm nguồn sự thật, key–value cho cache và document/search cho cách đọc chuyên biệt.

## 5. Những giới hạn và đánh đổi thường bị hiểu sai về NoSQL

### 5.1. “Không schema” không có nghĩa “không cần thiết kế”

Schema có thể không bị ép buộc ở dạng bảng cố định, nhưng dữ liệu vẫn có cấu trúc mà mã nguồn, API và quy trình phân tích kỳ vọng. Nếu document phiên bản cũ có trường **address** dạng chuỗi, còn phiên bản mới lưu thành object, mọi bộ đọc phải xử lý hai dạng hoặc dữ liệu cần được migration.

Thiết kế NoSQL vẫn cần quy ước tên trường, kiểu dữ liệu, validation, version, chính sách tương thích ngược và xử lý tài liệu lỗi. Schema linh hoạt hữu ích khi biến đổi có kiểm soát, không phải giấy phép lưu dữ liệu tùy tiện.

### 5.2. Phi chuẩn hóa giúp đọc nhanh nhưng khiến ghi khó hơn

Nhân bản tên sản phẩm vào từng đơn hàng có thể là **đúng** nếu mục tiêu là giữ ảnh chụp lịch sử tên tại thời điểm mua. Nhưng nhân bản trạng thái khách hàng đang hoạt động vào hàng nghìn document chỉ để đọc nhanh có thể khiến các bản sao lệch nhau.

Mỗi lần phi chuẩn hóa cần trả lời: dữ liệu nào là nguồn sự thật, bản sao cập nhật bằng cách nào, độ trễ cho phép bao nhiêu, làm sao phát hiện và sửa sai lệch. Việc tối ưu một truy vấn đọc thường chuyển chi phí sang ghi, đồng bộ và bảo trì.

### 5.3. Tính nhất quán là thuộc tính cụ thể của thao tác và cấu hình

Không chính xác nếu nói “mọi NoSQL đều eventual consistency” hoặc “mọi SQL đều luôn nhất quán mạnh trong mọi cách triển khai”. Một sản phẩm NoSQL có thể cho đọc nhất quán mạnh trên một phạm vi dữ liệu, giao dịch nhiều document hoặc lựa chọn mức nhất quán. Ngược lại, một ứng dụng SQL đọc từ replica bất đồng bộ vẫn có thể nhận dữ liệu cũ.

Phải mô tả yêu cầu bằng hành vi quan sát được:

- Sau khi người dùng sửa hồ sơ, **chính người đó** có bắt buộc thấy giá trị mới ở lần đọc tiếp theo không?
- Khi hai người cùng mua món cuối, hệ thống có cho phép bán vượt tồn kho không?
- Danh sách tìm kiếm có thể chậm vài giây so với đơn hàng gốc không?
- Khi một vùng mạng gặp sự cố, thao tác nào được phép thất bại và thao tác nào phải tiếp tục?

**CAP** bàn về đánh đổi giữa tính nhất quán và khả dụng khi có phân vùng mạng, trong phạm vi mô hình phân tán mà định lý xét tới. Nó không chia mọi sản phẩm thành hai nhãn bất biến “CP” hoặc “AP” cho mọi thao tác. Ngoài sự cố mạng, thiết kế còn phải cân bằng độ trễ và mức nhất quán trong hoạt động bình thường (thường được thảo luận qua **PACELC**). Khi chọn hệ quản trị, đọc bảo đảm cụ thể về replica, quorum, transaction, mức cô lập và xử lý lỗi.

### 5.4. Mở rộng ngang có giá vận hành và giá truy vấn

Phân mảnh dữ liệu trên nhiều nút có thể tăng dung lượng hoặc thông lượng, nhưng cũng tạo ra các bài toán: phân bố khóa, shard nóng, replication lag, truy vấn xuyên shard, chi phí mạng, rebalance, compaction, sao lưu nhất quán, vận hành nhiều vùng và xử lý sự cố một phần.

Không nên suy từ “hỗ trợ sharding” thành “mọi truy vấn đều tự động nhanh hơn”. Chẳng hạn, truy vấn không có partition key có thể buộc hệ thống quét nhiều nút. Tốc độ phải được đo trên **mẫu truy cập thật**, với phân phối khóa và dữ liệu có kích thước gần sản xuất.

### 5.5. Khả năng truy vấn và chỉ mục tùy hệ quản trị

RDBMS nổi bật ở JOIN, GROUP BY, truy vấn kết hợp và ràng buộc có cấu trúc. Một số document database cũng hỗ trợ aggregation, phép nối giới hạn, chỉ mục đa trường và truy vấn mạnh. Wide-column thường yêu cầu thiết kế bảng theo truy vấn; graph tối ưu traversal; key–value tối ưu truy cập theo khóa.

Chỉ mục giúp tăng tốc một nhóm phép đọc nhưng tốn dung lượng và chi phí cập nhật trên mỗi lần ghi. Nên xác minh thực tế **truy vấn nào có thể biểu đạt và được tối ưu tốt**, thay vì suy diễn từ nhãn SQL/NoSQL.

### 5.6. Tổng chi phí sở hữu lớn hơn chi phí lưu trữ

Chi phí cần tính cả số nút/replica, IOPS, dữ liệu truyền giữa vùng, backup, môi trường thử nghiệm, quan sát, tài khoản vận hành, đào tạo, xử lý sự cố và công sức sửa dữ liệu không nhất quán. Dùng thêm một cơ sở dữ liệu chuyên biệt làm tăng số thành phần cần giám sát và khôi phục, nên lợi ích đo được phải đủ bù đắp độ phức tạp.

## 6. Tình huống thực tế: chọn công nghệ theo ranh giới nghiệp vụ

### Tình huống A: Cửa hàng trực tuyến cần đặt hàng và quản lý tồn kho

**Yêu cầu:** Khách có thể đặt nhiều sản phẩm; số lượng không được âm; một đơn có nhiều dòng hàng; cần đối soát, hủy và báo cáo doanh thu.

**Hướng chọn:** RDBMS làm nguồn dữ liệu chính cho đơn hàng, dòng hàng và tồn kho. Sử dụng transaction, điều kiện cập nhật tồn kho, khóa/ràng buộc và idempotency để tránh tạo đơn lặp. Thanh toán qua dịch vụ ngoài cần luồng trạng thái và đối soát riêng.

**Chỗ NoSQL có thể bổ sung:** Cache giỏ hàng ngắn hạn hoặc chỉ mục tìm kiếm sản phẩm; cần phân biệt trạng thái tạm với đơn hàng đã xác nhận. Một document database không tự động giải quyết xung đột tồn kho giữa nhiều đơn.

### Tình huống B: Catalog sản phẩm nhiều loại, thuộc tính thay đổi

**Yêu cầu:** Mỗi nhóm hàng có thuộc tính riêng, API chủ yếu trả về một sản phẩm cùng cấu hình; số lượng biến thể mỗi sản phẩm có giới hạn.

**Hướng chọn:** Document có thể phù hợp vì cấu trúc lồng nhau và cách đọc theo sản phẩm. Tuy nhiên, nếu sản phẩm là một phần của hệ thống bán hàng dùng SQL, cột JSON/JSONB cùng chỉ mục phù hợp có thể đáp ứng mà không cần thêm hệ quản trị.

**Điểm phải cân nhắc:** Thuộc tính nào được nhúng, thuộc tính nào tham chiếu, giới hạn kích thước document, tần suất cập nhật, yêu cầu lọc đa tiêu chí và phân tích dữ liệu.

### Tình huống C: Thu thập sự kiện từ lượng lớn thiết bị

**Yêu cầu:** Ghi nhiều hơn đọc; thường truy vấn theo thiết bị và khoảng thời gian; giữ dữ liệu thô 30 ngày rồi tổng hợp.

**Hướng chọn:** Đánh giá wide-column hoặc time-series. Thiết kế khóa phân vùng theo thiết bị và khoảng thời gian phù hợp, quy định TTL/retention, cách xử lý dữ liệu đến muộn và nhu cầu tổng hợp.

**Khi vẫn chọn quan hệ:** Số thiết bị nhỏ hoặc tải chưa cao, truy vấn thay đổi nhiều và đội ngũ đã vận hành tốt bảng partition trong RDBMS. Không có lợi ích khi tăng số hệ thống trước khi giới hạn thật xuất hiện.

### Tình huống D: Phát hiện nhóm tài khoản có liên hệ đáng ngờ

**Yêu cầu:** Tìm chuỗi tài khoản dùng chung thiết bị, thẻ hoặc địa chỉ trong nhiều bước với chiều sâu không cố định.

**Hướng chọn:** Graph database có thể hỗ trợ hiệu quả mô hình đỉnh–cạnh và truy vấn đường đi. Tuy nhiên, giao dịch tài chính vẫn có thể cần SQL làm nguồn chính; graph là bản chiếu phục vụ phân tích, được đồng bộ theo quy tắc rõ ràng.

**Khi vẫn chọn quan hệ:** Mối liên hệ chỉ một hoặc hai tầng, số lượng dữ liệu vừa phải, các truy vấn JOIN đã cho độ trễ phù hợp.

### Tình huống E: Hệ thống quản trị nội bộ nhiều loại báo cáo

**Yêu cầu:** Người dùng liên tục thêm yêu cầu lọc, thống kê theo phòng ban, hợp đồng, nhân viên, khách hàng; dữ liệu cần kiểm toán và liên kết nhất quán.

**Hướng chọn:** RDBMS thường là mặc định tốt. Thiết kế chuẩn hóa, chỉ mục theo truy vấn, materialized view hoặc kho phân tích khi cần. Nếu báo cáo quá lớn ảnh hưởng hệ giao dịch, tách pipeline sang hệ OLAP thay vì vội chuyển toàn bộ dữ liệu nguồn sang một NoSQL bất kỳ.

## 7. Một hệ thống có thể kết hợp nhiều mô hình lưu trữ

Chọn “quan hệ hay NoSQL” không nhất thiết là quyết định loại trừ trên phạm vi toàn ứng dụng. Một kiến trúc có thể có ranh giới như sau:

~~~mermaid
flowchart LR
    API[Ứng dụng/API] --> SQL[(SQL: đơn hàng, tồn kho)]
    API --> KV[(Key-value: phiên và cache)]
    SQL --> EVT[Outbox / sự kiện thay đổi]
    EVT --> INDEX[(Search index / bản chiếu đọc)]
    API --> INDEX
~~~

Trong mô hình này:

1. **SQL** chịu trách nhiệm bảo vệ ràng buộc nghiệp vụ và lưu trạng thái gốc.
2. **Key–value** tăng tốc dữ liệu có thể tạo lại hoặc có vòng đời ngắn. Ứng dụng phải quyết định khi cache trống hoặc sai lệch.
3. **Outbox/event** chuyển thay đổi đã commit sang chỉ mục/bản chiếu. Bộ tiêu thụ cần xử lý trùng lặp, thử lại và theo dõi độ trễ.
4. **Search index** phục vụ các kiểu tìm kiếm chuyên biệt; khi có mâu thuẫn, quy tắc nguồn sự thật phải rõ ràng.

Kiến trúc nhiều cơ sở dữ liệu chỉ đáng áp dụng khi có lợi ích cụ thể. Mỗi bản chiếu thêm chi phí đồng bộ, monitoring, backup, quyền truy cập và tái tạo dữ liệu. Với hệ thống nhỏ, một RDBMS được thiết kế và lập chỉ mục tốt có thể đáp ứng toàn bộ yêu cầu ban đầu.

## 8. Quy trình ra quyết định có thể kiểm chứng

### Bước 1: Viết các thao tác chủ đạo thay vì chỉ liệt kê dữ liệu

Ví dụ, với ứng dụng đặt chỗ:

| Thao tác | Điều kiện truy cập | Đặc tính bắt buộc |
| --- | --- | --- |
| Xem thông tin một địa điểm | Theo ID, đọc thường xuyên | Độ trễ thấp; có thể cache |
| Tìm địa điểm theo bộ lọc | Khu vực, giá, tiện nghi | Kết hợp điều kiện và sắp xếp |
| Xác nhận đặt chỗ | ID phòng, khoảng thời gian | Không được bán trùng chỗ |
| Hủy và hoàn tiền | Đơn đặt, giao dịch thanh toán | Trạng thái rõ ràng, đối soát |
| Báo cáo doanh thu | Nhiều bảng, nhiều khoảng thời gian | Số liệu tin cậy, tổng hợp |

Nhìn vào thao tác cho thấy: đọc thông tin địa điểm có thể hợp với document hoặc cache, nhưng xác nhận đặt chỗ và hoàn tiền có yêu cầu giao dịch khác hẳn. Không thể chọn cơ sở dữ liệu chỉ từ việc “địa điểm có nhiều thuộc tính”.

### Bước 2: Liệt kê bất biến và mức nhất quán

Viết thành câu kiểm chứng được, chẳng hạn “một chỗ không được có hai đặt chỗ đã xác nhận trùng thời gian” hoặc “không được xác nhận hoàn tiền hai lần cho cùng giao dịch”. Sau đó xác định nơi thực thi: constraint/index, transaction, kiểm tra cạnh tranh, idempotency hay quy trình bù trừ. Nếu một bất biến kéo dài qua nhiều dịch vụ, nêu rõ cách phối hợp.

### Bước 3: Vẽ ranh giới dữ liệu và đường đi của truy vấn

Với document, chọn **aggregate boundary** và giới hạn kích thước; với wide-column, chọn partition key và mô hình phân bố dữ liệu; với graph, xác định loại cạnh và độ sâu traversal; với SQL, xác định thực thể, quan hệ, khóa và chỉ mục. Đánh giá chi phí cả đọc lẫn ghi, kể cả cập nhật bản sao.

### Bước 4: Đo trên dữ liệu và tải đại diện

Thực hiện thử nghiệm nhỏ dựa trên truy vấn thật: độ trễ trung vị và p95/p99, thông lượng, số hàng/bản ghi được quét, chi phí ghi và chỉ mục, phân bố khóa, ảnh hưởng khi thêm nút, thời gian phục hồi sau lỗi. So sánh với phương án quan hệ đã được tối ưu hợp lý; nếu phương án đơn giản đạt mục tiêu, không cần bổ sung thành phần mới.

### Bước 5: Kiểm tra vòng đời vận hành

Xác nhận cơ chế backup/restore và diễn tập khôi phục, sửa schema, truy vết thay đổi, mã hóa/phân quyền, quan sát replica và lag, giới hạn dịch vụ quản lý, chi phí theo vùng, và kế hoạch xử lý dữ liệu lệch. Đây là tiêu chí của lựa chọn công nghệ, không phải việc để sau khi triển khai.

## 9. Các kết luận sai thường gặp

| Kết luận vội vàng | Cách nghĩ chính xác hơn |
| --- | --- |
| “Dữ liệu lớn thì bắt buộc dùng NoSQL.” | Đo tải và truy vấn; SQL cũng có partition, replica, chỉ mục và nhiều phương án mở rộng. |
| “NoSQL không có transaction.” | Khả năng giao dịch khác nhau theo hệ và phạm vi; phải kiểm tra bảo đảm cùng chi phí thực tế. |
| “Document linh hoạt nên không cần schema.” | Cấu trúc vẫn là hợp đồng giữa dữ liệu và mã nguồn, cần validation và kế hoạch version/migration. |
| “Dữ liệu lồng nhau luôn nên lưu một document.” | Chỉ nhúng khi quan hệ cùng vòng đời, đọc cùng nhau và kích thước/chi phí cập nhật có giới hạn. |
| “Thêm replica sẽ vừa tăng tốc mọi truy vấn vừa bảo đảm đọc mới nhất.” | Replica phục vụ những mục tiêu cụ thể; đọc từ bản sao bất đồng bộ có thể trễ. |
| “Phân tán đồng nghĩa với không cần nghĩ đến khóa nóng.” | Partition key và phân bố tải quyết định hệ thống có cân bằng hay không. |
| “Chọn NoSQL là hết cần JOIN và ràng buộc.” | Nhu cầu liên kết và bất biến vẫn tồn tại, đôi khi chuyển sang ứng dụng hoặc pipeline đồng bộ. |
| “Chỉ cần một hệ cơ sở dữ liệu cho tất cả.” | Một hệ đủ tốt thường nên được giữ đơn giản, nhưng workload chuyên biệt có thể cần thành phần bổ sung. |

## 10. Bài tập tư duy lựa chọn

Xét ba yêu cầu sau và thử đưa ra **một phương án khởi đầu**, **một rủi ro cần đo** và **một điều kiện khiến bạn đổi lựa chọn**:

1. Ứng dụng ghi nhật ký thao tác người dùng, mỗi sự kiện có nhiều thuộc tính tùy loại; chủ yếu xem chuỗi sự kiện theo người dùng và thời gian.
2. Nền tảng bán khóa học quản lý học viên, đơn mua, quyền truy cập khóa học, giảng viên và báo cáo doanh thu; số lượng giao dịch mỗi ngày chưa lớn.
3. Mạng xã hội cần gợi ý “bạn của bạn của bạn” với độ sâu thay đổi; đồng thời phải quản lý thanh toán gói thành viên.

Gợi ý lập luận: trường hợp (1) nên đánh giá mô hình sự kiện theo thời gian và partition/retention; (2) có nhiều quan hệ và giao dịch nên thường khởi đầu với RDBMS; (3) có thể dùng graph cho truy vấn quan hệ sâu, còn thanh toán nên được thiết kế với bảo đảm giao dịch riêng. Với cả ba, kết quả cuối cùng còn phụ thuộc tải đo được, độ trễ yêu cầu và năng lực vận hành.

## Kết luận

NoSQL phù hợp khi **kiểu truy cập chủ đạo, cấu trúc dữ liệu và nhu cầu mở rộng** tương thích với một mô hình lưu trữ chuyên biệt: truy cập theo khóa, đọc một aggregate, ghi sự kiện phân tán hoặc duyệt đồ thị. Giới hạn chính xuất hiện ở các phép nối linh hoạt, cập nhật nhiều thực thể, ràng buộc toàn vẹn, quản lý bản sao và độ phức tạp vận hành — mức độ cụ thể tùy từng sản phẩm.

Khi bài toán đặt trọng tâm vào **ACID, tính đúng đắn của giao dịch, nhiều quan hệ chéo và báo cáo đa dạng**, hãy ưu tiên đánh giá hệ quan hệ trước. Chọn công nghệ bằng bất biến nghiệp vụ, mẫu truy vấn, số liệu hiệu năng và khả năng khôi phục, rồi chỉ bổ sung NoSQL ở nơi lợi ích của nó được chứng minh.
