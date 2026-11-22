# Phân biệt mô hình logic với cách tổ chức dữ liệu vật lý

## 1. Hai câu hỏi khác nhau trong thiết kế dữ liệu

Khi thiết kế cơ sở dữ liệu NoSQL, cần tách hai câu hỏi:

1. **Mô hình logic (logical data model):** Hệ thống quản lý những thực thể, thuộc tính và quan hệ nào? Dữ liệu có ý nghĩa gì đối với nghiệp vụ? Ứng dụng cần nhìn thấy và truy cập dữ liệu dưới cấu trúc nào?
2. **Tổ chức dữ liệu vật lý (physical data organization):** Hệ quản trị thực sự mã hóa, sắp xếp, lập chỉ mục, phân vùng, nhân bản và lưu các byte dữ liệu ở đâu và như thế nào để phục vụ các thao tác đó?

Ví dụ, phát biểu “một khách hàng có nhiều đơn hàng; mỗi đơn gồm các dòng hàng” là một quan hệ **logic**. Quyết định “lưu các đơn vào các phân vùng theo mã khách hàng, sắp theo thời gian giảm dần, tạo chỉ mục phụ và nhân bản trên ba nút” thuộc về thiết kế **vật lý** hoặc các lựa chọn cấu hình triển khai.

Hai tầng này có liên hệ chặt chẽ nhưng không đồng nhất. Trong NoSQL, một số lựa chọn trông giống cấu trúc logic — chẳng hạn chọn **partition key** — cũng trực tiếp ảnh hưởng vị trí lưu trữ và khả năng mở rộng vật lý. Việc phân biệt tầng thiết kế giúp tránh nhầm “dữ liệu được biểu diễn như thế nào” với “hệ thống lưu và tìm dữ liệu như thế nào”.

### Ba tầng thường dùng để mô tả hệ thống

| Tầng | Câu hỏi trung tâm | Ví dụ cho hệ thống bán hàng |
| --- | --- | --- |
| **Khái niệm (conceptual)** | Những khái niệm nghiệp vụ và quan hệ cốt lõi là gì? | Khách hàng đặt đơn; đơn chứa sản phẩm |
| **Logic (logical)** | Cấu trúc và định danh dữ liệu nào được ứng dụng sử dụng, bất kể vị trí byte trên đĩa? | Document đơn hàng có \`orderId\`, \`customerId\`, \`items[]\`; quan hệ đơn–khách qua ID |
| **Vật lý (physical)** | Trên một sản phẩm và hạ tầng cụ thể, dữ liệu được phân bố, sắp xếp, đánh chỉ mục, lưu và sao chép ra sao? | Chỉ mục theo \`customerId, createdAt\`, shard theo khóa được chọn, replica, định dạng trang hoặc cấu trúc lưu trữ |

Mô hình logic có thể gắn với họ cơ sở dữ liệu (document, key–value, wide-column, graph), vì mỗi họ đưa ra cách biểu diễn và thao tác riêng. Nhưng **họ mô hình không quyết định duy nhất cách triển khai vật lý**: hai sản phẩm cùng hỗ trợ document có thể sử dụng storage engine, chỉ mục và cơ chế phân vùng khác nhau.

~~~mermaid
flowchart TD
    R["Yêu cầu nghiệp vụ và mẫu truy cập"] --> C["Mô hình khái niệm"]
    C --> L["Mô hình logic: đối tượng, quan hệ, khóa, cấu trúc"]
    L --> P["Thiết kế vật lý: phân vùng, chỉ mục, thứ tự, lưu trữ"]
    P --> D["Triển khai: nút, replica, đĩa, bộ nhớ, mạng"]
    D -. "Số đo thực tế: độ trễ, tải, lỗi" .-> L
~~~

Đường phản hồi trong sơ đồ nhắc rằng một quyết định vật lý không đạt yêu cầu có thể khiến nhóm cần điều chỉnh lại khóa hoặc thậm chí mô hình logic. Điều này xảy ra thường xuyên trong NoSQL, nơi đường truy cập dữ liệu ảnh hưởng mạnh đến cách mô hình hóa.

## 2. Nhận diện các thành phần thuộc tầng logic

Mô hình logic mô tả **hợp đồng dữ liệu** giữa các thành phần ứng dụng và cách người viết truy vấn hiểu dữ liệu. Những nội dung thường thuộc tầng này gồm:

- **Thực thể và danh tính:** khách hàng, đơn hàng, thiết bị, sự kiện; khóa \`customerId\`, \`orderId\` có ý nghĩa gì và duy nhất trong phạm vi nào.
- **Thuộc tính và kiểu dữ liệu:** số lượng là số nguyên không âm; thời điểm là timestamp; trạng thái thuộc tập \`PENDING\`, \`PAID\`, \`CANCELLED\`.
- **Quan hệ và lực lượng quan hệ:** một–một, một–nhiều, nhiều–nhiều; tham chiếu bằng ID hay biểu diễn lồng nhau.
- **Đơn vị truy cập và thay đổi:** một document đại diện cho một đơn hàng, hay một record cho mỗi sự kiện; những trường nào phải được đọc và cập nhật cùng nhau.
- **Quy tắc dữ liệu:** trường bắt buộc, tính duy nhất, dữ liệu nào là ảnh chụp lịch sử, dữ liệu nào là trạng thái hiện hành, vòng đời và khả năng xóa.
- **Giao diện truy vấn dự kiến:** tra cứu theo ID; liệt kê đơn của một khách hàng; đọc chuỗi sự kiện theo thiết bị và khoảng thời gian.

Trong NoSQL, cấu trúc logic thường được tổ chức quanh **mẫu truy cập**. Ví dụ, nếu API luôn cần đơn hàng cùng các dòng hàng, có thể nhúng \`items[]\` vào một document \`Order\`. Quyết định nhúng này là **mô hình hóa logic**: nó xác định đơn vị dữ liệu mà ứng dụng thao tác. Nó chưa nói document sẽ nằm trên đĩa nào, có bao nhiêu replica hay sử dụng chỉ mục nội bộ gì.

### Ví dụ logic: một đơn hàng

~~~json
{
  "orderId": "O-2026-0142",
  "customerId": "C-008",
  "createdAt": "2026-11-14T08:15:00Z",
  "status": "PAID",
  "currency": "VND",
  "items": [
    {
      "productId": "P-19",
      "nameAtPurchase": "Sách Java",
      "quantity": 2,
      "unitPrice": 125000
    },
    {
      "productId": "P-57",
      "nameAtPurchase": "Sổ tay",
      "quantity": 1,
      "unitPrice": 45000
    }
  ]
}
~~~

Đây là **biểu diễn logic minh họa**. JSON giúp người đọc hiểu cấu trúc; nó không khẳng định sản phẩm database sẽ ghi nguyên văn văn bản JSON lên đĩa. Hệ thống có thể lưu dạng nhị phân, nén dữ liệu, tạo bản ghi nội bộ khác hoặc lưu chỉ mục riêng.

Lưu ý \`nameAtPurchase\`: tên tại thời điểm mua là một phần của lịch sử đơn hàng; không nhất thiết phải đồng bộ theo tên sản phẩm hiện hành. Ngược lại, \`customerId\` là tham chiếu đến khách hàng, không có nghĩa mọi trường hồ sơ khách hàng đều nên được sao chép vào từng đơn.

### Logic không đồng nghĩa với “không có schema”

Nhiều document database cho phép các document có trường khác nhau, nhưng ứng dụng vẫn dựa vào một hợp đồng logic. Khi trường \`unitPrice\` thay từ số sang chuỗi hoặc \`items\` thay từ mảng sang object, API có thể hỏng dù database vẫn chấp nhận bản ghi mới.

Vì thế mô hình logic vẫn cần quy ước kiểu dữ liệu, version, validation, tính tương thích ngược và kế hoạch migration. “Schema linh hoạt” chỉ thay đổi cách **thi hành** và **tiến hóa** schema, không loại bỏ nhu cầu thiết kế.

## 3. Nhận diện các thành phần thuộc tầng vật lý

Thiết kế vật lý giải thích **cách hệ quản trị thực hiện truy cập và bảo vệ dữ liệu**, với một khối lượng công việc và cấu hình cụ thể. Các thành phần quan trọng gồm:

| Quyết định vật lý | Ảnh hưởng chính | Ví dụ |
| --- | --- | --- |
| **Phân vùng / sharding** | Bản ghi nằm ở nút/phân vùng nào; tải có phân bố đều không | Hash theo \`customerId\` hoặc phân vùng theo vùng khóa |
| **Thứ tự lưu/khóa sắp xếp** | Truy cập theo khoảng và thứ tự kết quả | Sắp các sự kiện của một thiết bị theo \`eventTime\` |
| **Chỉ mục** | Truy vấn tìm bản ghi mà không quét toàn tập | Index trên \`(customerId, createdAt)\` |
| **Cấu trúc lưu trữ** | Chi phí ghi, đọc, cập nhật, compaction và dùng đĩa | B-tree, LSM-tree, log, file segments |
| **Mã hóa/serialization/nén** | Kích thước byte, CPU và tương thích định dạng | BSON hoặc định dạng nhị phân nội bộ; nén block |
| **Replication** | Khả năng chịu lỗi, nơi phục vụ đọc và độ trễ lan truyền | Bản sao trên các nút hoặc vùng |
| **Cache/buffer** | Dữ liệu nào được giữ ở RAM để tăng tốc đọc | Cache trang, block hoặc kết quả |
| **TTL, retention, compaction** | Dữ liệu hết hạn được loại bỏ và tài nguyên thu hồi ra sao | Xóa logic rồi thu hồi qua compaction |
| **Bố trí hạ tầng** | Độ trễ mạng/đĩa, khả năng phục hồi và chi phí | Nút ở nhiều vùng khả dụng, SSD, giới hạn RAM |

Một vài cấu phần này được người quản trị cấu hình trực tiếp; số khác do storage engine triển khai và chỉ cho phép tác động thông qua tham số. Không phải mọi NoSQL đều có cùng cơ chế hoặc cho phép điều khiển cùng mức chi tiết.

### Phân biệt “nơi lưu” và “cách truy vấn”

Một collection tên \`orders\` là **tên tổ chức logic** mà ứng dụng truy cập. Tuy nhiên, các document trong collection đó có thể:

1. Được ánh xạ sang các shard khác nhau theo một khóa;
2. Mỗi shard giữ một hay nhiều bản sao dữ liệu;
3. Có những file dữ liệu và file chỉ mục riêng;
4. Được mã hóa thành byte theo định dạng nội bộ và sắp vào cấu trúc lưu trữ;
5. Được đưa một phần vào bộ nhớ đệm khi hệ thống truy cập.

Vì vậy không nên hình dung “một collection = một file”, “một document = một dòng JSON trên đĩa”, hay “một node trong graph = một file vật lý”. Đây là những sự đánh đồng giữa hình thức API và cách lưu trữ nội bộ.

## 4. Cùng một mô hình logic có nhiều cách tổ chức vật lý

Giả sử API đặt hàng có hai truy vấn chủ đạo:

~~~text
Q1: Lấy chi tiết đơn bằng orderId.
Q2: Lấy 20 đơn mới nhất của customerId, có phân trang.
~~~

Ứng dụng cần một mô hình logic \`Order\` giống ví dụ trên. Có nhiều cách triển khai:

**Phương án A — Tập trung tra cứu theo ID.** Dùng \`orderId\` làm khóa chính/định danh, lập chỉ mục phụ phù hợp cho \`customerId\` và \`createdAt\`. Nếu chỉ có Q1 và Q2, đây có thể là thiết kế đủ đơn giản.

**Phương án B — Tổ chức theo khách hàng.** Chọn \`customerId\` hoặc khóa kết hợp có thành phần khách hàng để nhóm đơn, đồng thời sử dụng thứ tự thời gian trong phạm vi nhóm. Q2 có thể nhanh hơn nếu dữ liệu nằm cùng phạm vi truy cập, nhưng Q1 chỉ có \`orderId\` có thể cần bảng/ánh xạ tra cứu khác.

**Phương án C — Bản chiếu phục vụ đọc.** Giữ một nguồn sự thật cho từng đơn và thêm cấu trúc \`ordersByCustomer\` để liệt kê nhanh. Phải đồng bộ thay đổi trạng thái đơn đến bản chiếu, chịu chi phí ghi thêm và quy định mức trễ được chấp nhận.

Các phương án biểu diễn **cùng ý nghĩa nghiệp vụ**. Khác biệt nằm ở khóa dùng truy xuất, nhóm dữ liệu, chỉ mục, đường đọc và các cấu trúc phụ. Tùy sản phẩm NoSQL, một số lựa chọn nằm ngay trong định nghĩa bảng/collection và tác động đồng thời đến giao diện truy vấn lẫn phân bố dữ liệu.

### Sơ đồ hai cách lưu một đối tượng logic

~~~mermaid
flowchart TB
    O["Logic: Order(orderId, customerId, createdAt, items)"]
    O --> A["Cách A: khóa orderId"]
    O --> B["Cách B: nhóm theo customerId"]
    A --> IA["Index phụ cho danh sách đơn khách hàng"]
    B --> IB["Thứ tự createdAt trong nhóm"]
    A --> Q1["Q1: tìm theo orderId thuận tiện"]
    B --> Q2["Q2: duyệt đơn theo khách hàng thuận tiện"]
~~~

Không có cách nào luôn nhanh nhất. Lợi ích phụ thuộc số đơn mỗi khách, tần suất Q1/Q2, phân bố dữ liệu, yêu cầu phân trang, chi phí ghi và khả năng phân vùng.

## 5. Ranh giới logic/vật lý trong các họ NoSQL

### 5.1. Key–value: khóa và giá trị không quyết định cấu trúc lưu trữ

**Tầng logic:** Ứng dụng lưu một cặp \`key -> value\`, ví dụ:

~~~text
cart:C-008 -> { items: [{sku: "P-19", quantity: 2}], updatedAt: "..." }
~~~

Từ góc nhìn ứng dụng, thao tác chính là \`GET(key)\`, \`PUT(key, value)\` và có thể \`DELETE(key)\`. Quy tắc định danh của khóa, định dạng giá trị, TTL theo nghiệp vụ và vòng đời của giỏ hàng là những quyết định logic.

**Tầng vật lý:** Engine có thể dùng bảng băm, B-tree, LSM-tree hoặc cơ chế khác; phân bố khóa lên nhiều partition; sao chép sang nhiều nút; giữ một phần dữ liệu ở RAM hoặc ghi bền vững xuống đĩa. Ký tự trong khóa \`cart:C-008\` không tự chứng minh giỏ hàng sẽ nằm trên một nút hay một vị trí byte cụ thể.

Nếu tất cả client ghi vào ít khóa rất nóng, việc tăng số shard có thể không xử lý được nút thắt. **Độ đa dạng khóa** và cách ánh xạ khóa đến partition là vấn đề vật lý phải đo và thiết kế.

### 5.2. Document: object lồng nhau không đồng nghĩa lưu nguyên JSON

**Tầng logic:** Document có mảng, object lồng nhau, khóa ID, trường tùy loại và các thao tác lọc/cập nhật. Quyết định nhúng \`order.items[]\` hay chỉ giữ \`productId\` là quyết định mô hình logic, vì nó ảnh hưởng hợp đồng dữ liệu và đơn vị cập nhật.

**Tầng vật lý:** Document có thể được mã hóa dạng nhị phân, đặt trong các trang/segment, phân shard theo khóa và đi kèm chỉ mục riêng cho các trường. Hệ quản trị có thể đánh chỉ mục cả đường dẫn lồng nhau, nhưng chỉ mục phải được cấu hình phù hợp và có chi phí dung lượng/ghi.

Ví dụ một truy vấn danh sách theo khách hàng có thể cần chỉ mục theo:

~~~text
(customerId ASC, createdAt DESC)
~~~

Đây là mô tả **thứ tự khóa chỉ mục mong muốn**, không phải cú pháp tạo chỉ mục dành cho một sản phẩm cụ thể. Khả năng sử dụng chỉ mục còn phụ thuộc quy tắc của engine, cách lọc và cách sắp xếp truy vấn.

### 5.3. Wide-column: khóa có hai vai trò

Ở nhiều hệ wide-column, cách định nghĩa bảng gắn rất gần với đường truy cập và phân bố dữ liệu:

~~~text
Logical row:
  deviceId = "D-17"
  day = "2026-11-14"
  eventTime = "08:15:03Z"
  temperature = 29.3

Illustrative key design:
  partition key = (deviceId, day)
  clustering key = eventTime
~~~

**Logic:** Mỗi bản ghi biểu diễn một phép đo, có danh tính thiết bị, thời gian và giá trị. Ứng dụng cần xem sự kiện theo thiết bị và khoảng thời gian.

**Vật lý:** Partition key thường quyết định cách nhóm/phân phối bản ghi, còn clustering key ảnh hưởng trật tự trong partition theo quy tắc của hệ quản trị. Đọc một khoảng thời gian ngắn trong cùng partition có thể hiệu quả hơn việc quét toàn bộ thiết bị.

Điểm giao nhau là **partition key xuất hiện trong schema logic nhưng quyết định tổ chức vật lý**. Không nên cố gán nó vào một tầng duy nhất trong mọi tài liệu. Hãy diễn đạt rõ hai tác động: “ứng dụng truy vấn bằng khóa này” và “engine phân bố/sắp dữ liệu dựa trên khóa này”.

Nếu tất cả sự kiện của thiết bị rất bận rộn trong một ngày dồn vào một partition, thiết kế vẫn có thể tạo **hot partition** hoặc partition quá lớn. Có thể cần đổi kích thước cửa sổ thời gian, thêm bucket theo quy tắc truy vấn hoặc dùng một công nghệ time-series thích hợp, sau khi đo tải thực tế.

### 5.4. Graph: quan hệ logic không phải cạnh vật lý theo nghĩa đen

**Logic:** Đỉnh \`Customer\`, \`Device\`, \`PaymentMethod\` và các cạnh \`USES_DEVICE\`, \`PAID_WITH\`:

~~~text
(Customer C-1) --USES_DEVICE--> (Device D-7)
(Customer C-2) --USES_DEVICE--> (Device D-7)
(Customer C-2) --PAID_WITH-->  (PaymentMethod M-9)
~~~

Ứng dụng có thể hỏi “Từ C-1, những khách hàng nào có liên hệ qua thiết bị trong hai bước?” Đó là truy vấn logic về sự liên kết.

**Vật lý:** Engine có thể lưu các đỉnh/cạnh dưới dạng bản ghi, danh sách kề, các chỉ mục tra cứu hoặc những cấu trúc khác; trên hệ phân tán, các đỉnh liên quan có thể nằm ở những máy khác nhau. Khi truy vấn đi qua nhiều shard, chi phí mạng có thể lớn, dù truy vấn logic chỉ là một phép traversal ngắn.

Graph là **cách mô hình và truy vấn quan hệ**, không phải bảo đảm tự động rằng mọi cạnh được đặt cạnh nhau trên đĩa.

### So sánh nhanh

| Họ dữ liệu | Mô hình logic ứng dụng nhìn thấy | Ví dụ lựa chọn tổ chức vật lý |
| --- | --- | --- |
| Key–value | Khóa duy nhất và giá trị; đọc/ghi theo khóa | Hash/phân vùng khóa, cấu trúc lưu trữ, RAM/SSD, replication |
| Document | Document, trường lồng nhau, mảng, chỉ mục truy vấn | Mã hóa nhị phân, index, shard key, compression |
| Wide-column | Bảng/hàng với partition/clustering key và kiểu truy vấn định trước | Phân bố partition, thứ tự dữ liệu, SSTable/compaction ở những engine phù hợp |
| Graph | Đỉnh, cạnh, nhãn, thuộc tính, đường đi | Adjacency/index, phân bố đỉnh/cạnh, chiến lược phục vụ traversal |

Đây là các **đặc điểm thường gặp**, không phải chuẩn bắt buộc cho mọi sản phẩm trong từng họ. Nhiều cơ sở dữ liệu hỗ trợ hơn một kiểu API hoặc mô hình lưu trữ.

## 6. Phân vùng, chỉ mục và replication: ba việc không nên trộn lẫn

Ba khái niệm xuất hiện cùng nhau khi tối ưu hệ thống NoSQL nhưng giải quyết các vấn đề khác nhau.

### 6.1. Partition/shard: dữ liệu thuộc phần nào?

Với một tập dữ liệu lớn, hệ thống có thể chia dữ liệu thành các phần. **Partitioning** là cách chia dữ liệu theo khóa hoặc khoảng giá trị; **sharding** thường chỉ việc phân chia/phân bố đó giữa các tài nguyên lưu trữ hoặc nút độc lập, tuy thuật ngữ cụ thể khác theo sản phẩm.

Ví dụ minh họa:

~~~text
Order O-101, customer C-1  -> shard A
Order O-102, customer C-2  -> shard B
Order O-103, customer C-1  -> shard A
~~~

Nếu phân theo \`customerId\`, các đơn của C-1 có thể ở cùng shard, thuận tiện cho truy vấn theo khách hàng. Nhưng khách quá lớn có thể tạo tải mất cân bằng. Nếu phân theo \`orderId\`, các đơn phân tán đều hơn trong một số workload, nhưng truy vấn “mọi đơn của C-1” có thể cần truy vấn nhiều shard hoặc dùng cấu trúc tra cứu khác.

Các câu hỏi vật lý cần đặt ra là: khóa có đủ nhiều giá trị khác nhau không, có khách hàng/tenant nào quá nóng không, truy vấn có chứa partition key không, kích thước partition tăng theo thời gian đến đâu và việc rebalance diễn ra thế nào?

### 6.2. Index: tìm bản ghi qua thuộc tính nào?

Giả sử document được phân theo \`orderId\` nhưng truy vấn lại theo \`customerId\`. Chỉ mục thứ cấp có thể giúp hệ quản trị tìm nhanh bản ghi mà không quét toàn tập. Tuy vậy:

- Mỗi chỉ mục tiêu thụ dung lượng.
- Ghi/sửa/xóa dữ liệu thường phải cập nhật chỉ mục.
- Index trên trường có ít giá trị phân biệt có thể không hiệu quả cho một số truy vấn.
- Trong hệ phân tán, chỉ mục có thể là cục bộ trên shard hoặc có thiết kế toàn cục tùy sản phẩm; phạm vi này ảnh hưởng cách định tuyến truy vấn.

**Index không thay thế cho partition key.** Một truy vấn dùng index rất tốt bên trong mỗi shard vẫn có thể phải đi tới nhiều shard nếu không xác định được shard cần đọc.

### 6.3. Replication: có bao nhiêu bản sao và đọc/ghi qua bản nào?

Replication giữ nhiều bản sao để tăng khả năng chịu lỗi và có thể tăng năng lực phục vụ đọc. Nó không đồng nghĩa với sharding: mỗi shard có thể có nhiều replica.

~~~mermaid
flowchart LR
    K["Dữ liệu được chia theo shard key"] --> S1["Shard A"]
    K --> S2["Shard B"]
    S1 --> A1["Replica A1"]
    S1 --> A2["Replica A2"]
    S2 --> B1["Replica B1"]
    S2 --> B2["Replica B2"]
~~~

Việc có bản sao không nói lên ngay dữ liệu có được đọc nhất quán hay không. Phải xem sản phẩm dùng đồng bộ hay bất đồng bộ, có leader không, chọn quorum ra sao, định tuyến đọc ở đâu và ứng xử khi mạng phân vùng. Đọc từ replica cập nhật chậm có thể thấy dữ liệu cũ, dù cách tổ chức logic hoàn toàn giống với bản gốc.

## 7. Cấu trúc lưu trữ: vì sao dữ liệu logic giống nhau vẫn có hiệu năng khác nhau?

### B-tree và các cấu trúc dựa trên cây

Những cấu trúc dạng cây cân bằng giúp tra cứu theo khóa và quét khoảng có thứ tự. Việc ghi có thể sửa các trang dữ liệu hoặc chỉ mục, và engine dùng bộ đệm hoặc log để hỗ trợ tính bền vững. Chi tiết phụ thuộc sản phẩm, cấu hình và storage engine.

### LSM-tree và ghi tuần tự

Một số hệ thống ghi trước vào log/memory table, rồi xả thành các file có thứ tự và hợp nhất nhiều file về sau (**compaction**). Cách tổ chức này có thể phù hợp với lưu lượng ghi lớn nhưng phát sinh những đánh đổi khác:

- Cần nhiều lần đọc hoặc cấu trúc bổ trợ để tìm dữ liệu qua các file.
- Compaction dùng CPU và I/O, có thể tạo dao động độ trễ.
- Tombstone biểu diễn thao tác xóa trước khi dung lượng được thu hồi thực sự.
- Write amplification, read amplification và space amplification cần được đo.

Không thể suy rằng “NoSQL = LSM-tree” hoặc “SQL = B-tree”. Cả hai là **chi tiết của storage engine**; mỗi sản phẩm có thể chọn cấu trúc khác nhau hoặc kết hợp nhiều kỹ thuật.

### Cùng một truy vấn, đường đi vật lý khác nhau

Với yêu cầu “lấy 20 sự kiện mới nhất của thiết bị D-17”:

1. Một thiết kế có thể đọc vùng dữ liệu được sắp theo \`(deviceId, eventTime)\`.
2. Thiết kế khác có thể đọc chỉ mục thứ cấp theo thiết bị và thời gian rồi truy xuất bản ghi.
3. Thiết kế thứ ba có thể phải quét nhiều partition, lọc, sắp lại dữ liệu và chỉ trả 20 kết quả cuối cùng.

Các thiết kế đều trả về **cùng kết quả logic** nhưng khác số lần đọc đĩa, số nút tham gia, lượng dữ liệu chuyển qua mạng và độ trễ. Đây chính là lý do phải phân biệt mô hình dữ liệu với đường truy cập vật lý.

## 8. Ví dụ xuyên suốt: nền tảng đo nhiệt độ IoT

Một nền tảng tiếp nhận sự kiện từ thiết bị và cần hỗ trợ:

~~~text
Q1: Lấy nhiệt độ mới nhất của thiết bị D-17.
Q2: Lấy toàn bộ phép đo của D-17 từ 08:00 đến 09:00.
Q3: Tính nhiệt độ trung bình theo giờ trong 30 ngày.
~~~

### 8.1. Mô hình logic

Mỗi phép đo là một sự kiện bất biến với các trường:

~~~json
{
  "eventId": "evt-901",
  "deviceId": "D-17",
  "measuredAt": "2026-11-14T08:15:03Z",
  "temperatureC": 29.3,
  "quality": "OK"
}
~~~

Cần xác định thêm: \`eventId\` có duy nhất toàn hệ thống không, thiết bị có gửi lại một sự kiện khi mạng lỗi không, hai phép đo có được phép trùng \`measuredAt\` không, dữ liệu đến muộn có được ghi bù không, nhiệt độ âm có hợp lệ không và sự kiện phải giữ trong bao lâu.

Đó là các câu hỏi **logic và nghiệp vụ**. Dữ liệu có thể được biểu diễn dưới document, hàng wide-column hay dạng record của một hệ time-series mà vẫn giữ cùng ý nghĩa.

### 8.2. Một phương án tổ chức vật lý

Với tải lớn và truy vấn thường theo thiết bị/thời gian, có thể khảo sát cách tổ chức:

~~~text
partitionKey: (deviceId, dateBucket)
sortKey:      (measuredAt, eventId)
payload:      temperatureC, quality

dateBucket = YYYY-MM-DD theo thời gian UTC
~~~

Khóa \`eventId\` trong thứ tự có thể giúp phân biệt những phép đo cùng timestamp. Khi cần xem một giờ của D-17, hệ quản trị có thể đọc dải khóa tương ứng; nếu khoảng thời gian vượt qua hai ngày, ứng dụng hoặc lớp truy vấn phải đọc hai bucket. Cơ chế này phụ thuộc cách engine lưu dữ liệu có thứ tự và hỗ trợ truy vấn theo khoảng.

Thiết kế nên thử nghiệm với tải thực tế:

- Nếu một thiết bị tạo quá nhiều sự kiện trong một ngày, bucket theo ngày có thể quá lớn.
- Nếu thêm bucket theo giờ, truy vấn một tuần sẽ phải ghép nhiều bucket hơn.
- Nếu có một số ít thiết bị gửi phần lớn sự kiện, partition vẫn có thể bị nóng.
- Nếu Q3 được hỏi thường xuyên, tổng hợp theo giờ vào một bản chiếu riêng có thể tiết kiệm chi phí đọc lại dữ liệu thô.
- Nếu chỉ giữ 30 ngày, cần xác định TTL/retention và cơ chế thu hồi dung lượng vật lý.

### 8.3. Phân biệt thêm một bản chiếu cho Q1

Q1 chỉ muốn nhiệt độ mới nhất, còn Q2 cần lịch sử. Có thể duy trì thêm:

~~~text
latestByDevice["D-17"] = {
  measuredAt: "2026-11-14T08:15:03Z",
  temperatureC: 29.3
}
~~~

Về **logic**, đây là một trạng thái suy ra từ chuỗi sự kiện. Về **vật lý**, nó có thể nằm trong key–value store, bảng riêng hoặc cache. Nếu sự kiện đến không đúng thứ tự, không được đơn giản ghi đè \`latestByDevice\` theo **thứ tự đến**; cần so sánh thời gian đo, xử lý cùng timestamp và xác định quy tắc chọn bản mới nhất.

Nếu bản chiếu được cập nhật bất đồng bộ, Q1 có thể trễ so với dữ liệu thô. Hệ thống cần định nghĩa mức trễ chấp nhận được và cách tái dựng bản chiếu khi sai lệch. Đây là đánh đổi giữa truy vấn vật lý hiệu quả và tính nhất quán quan sát được.

### 8.4. Nếu thay sản phẩm database thì logic có đổi không?

Có thể giữ nguyên định nghĩa “một phép đo của thiết bị tại thời điểm T có giá trị V” khi chuyển từ document database sang time-series database. Nhưng cần xây lại partitioning, index, retention, query và pipeline tổng hợp cho cơ chế lưu trữ mới.

Ngược lại, nếu thay đổi cấu trúc logic từ “mỗi bản ghi là một phép đo” thành “mỗi document chứa một mảng toàn bộ phép đo trong ngày”, API đọc/ghi, xử lý dữ liệu đến muộn, đồng thời ghi và giới hạn kích thước document đều có thể đổi. Đó không còn chỉ là thay đổi vật lý.

## 9. Ví dụ thứ hai: quan hệ khách hàng và đơn hàng

Yêu cầu:

- Tra cứu đơn hàng bằng ID;
- Liệt kê đơn của một khách hàng từ mới đến cũ;
- Cập nhật trạng thái đơn;
- Giữ chính xác giá đã mua để đối soát.

Hai mô hình logic có thể được cân nhắc:

**Mô hình L1 — Đơn là một aggregate độc lập.**

~~~text
Customer(customerId, name, ...)
Order(orderId, customerId, createdAt, status, items[])
~~~

Ưu điểm: một đơn có vòng đời, trạng thái và danh tính riêng; có thể cập nhật đơn bằng ID. Danh sách theo khách hàng cần chỉ mục hoặc bản chiếu phù hợp.

**Mô hình L2 — Nhúng danh sách đơn vào khách hàng.**

~~~text
Customer(
  customerId,
  name,
  orders: [Order, Order, ...]
)
~~~

L2 có vẻ tiện cho màn hình hồ sơ khách hàng, nhưng lịch sử đơn có thể tăng mãi, một khách hàng có nhiều yêu cầu ghi đồng thời, và một đơn cần được xử lý độc lập. Đây là **vấn đề chọn ranh giới logic của aggregate**, trước khi bàn đến SSD hay replica. Có thể chọn L1 cùng bản chiếu danh sách để tránh một document tăng vô hạn.

Giữ L1, những lựa chọn vật lý như **index trên \`(customerId, createdAt)\`**, **shard key**, **số replica** và **cấu hình cache** có thể được thay đổi để đạt mục tiêu hiệu năng, thường không cần đổi hình dạng \`Order\` trả về cho ứng dụng. Một số thay đổi như shard key vẫn đòi hỏi di chuyển dữ liệu, thời gian vận hành và kiểm tra tính tương thích truy vấn.

### Tách quyết định dưới dạng bảng

| Phát biểu thiết kế | Tầng chủ yếu | Vì sao? |
| --- | --- | --- |
| Mỗi đơn có một \`orderId\` duy nhất | Logic | Định danh và ràng buộc nghiệp vụ |
| \`items[]\` nằm trong \`Order\` | Logic | Chọn cấu trúc và ranh giới cập nhật |
| \`nameAtPurchase\` giữ tên lúc mua | Logic | Ý nghĩa lịch sử và tính đúng đắn dữ liệu |
| Dùng chỉ mục \`customerId, createdAt\` | Vật lý | Tối ưu đường truy cập và sắp xếp |
| Chia shard theo \`customerId\` | Giao điểm logic/vật lý | Khóa có mặt trong schema, đồng thời quyết định phân bố |
| Dùng ba replica ở các vùng khả dụng khác nhau | Vật lý/triển khai | Khả năng chịu lỗi và phân bố bản sao |
| Cập nhật bản chiếu danh sách đơn qua sự kiện | Cả hai tầng | Thêm cấu trúc đọc logic và cơ chế đồng bộ vật lý |

## 10. Các nhầm lẫn phổ biến

### “Mỗi document sẽ được lưu thành một file JSON”

Document là **đơn vị biểu diễn mà API phơi bày**. Hệ quản trị có thể dùng encoding nhị phân, page, segment và các file chỉ mục riêng. Định dạng JSON trong ví dụ chỉ để con người đọc được.

### “Có trường \`userId\` thì dữ liệu sẽ nằm cùng shard theo người dùng”

Chỉ khi chiến lược phân vùng thực sự dùng \`userId\` (hoặc một khóa phù hợp) và cách triển khai bảo đảm điều đó. Một trường trong document không tự biến thành partition key; index trên trường đó cũng không mặc định quyết định nơi lưu dữ liệu.

### “Tạo index là đã giải quyết phân mảnh dữ liệu”

Index giúp tìm dữ liệu theo thuộc tính. Sharding quyết định phân bố dữ liệu. Một truy vấn có index nhưng không được định tuyến tới shard cụ thể vẫn có thể phải fan-out đến nhiều shard.

### “Đổi engine lưu trữ là đổi mô hình nghiệp vụ”

Không nhất thiết. Cùng tập thực thể và API logic có thể chạy trên nhiều storage engine khác nhau. Tuy nhiên, thay engine có thể làm đổi bảo đảm giao dịch, khả năng truy vấn, cú pháp và hiệu năng; vì thế sự tương đương cần được xác minh trên từng sản phẩm.

### “Nhúng dữ liệu là một tối ưu thuần vật lý”

Trong document modeling, nhúng dữ liệu thay đổi cấu trúc mà ứng dụng nhìn thấy và thường thay đổi ranh giới cập nhật. Vì vậy đây là **quyết định logic chịu ảnh hưởng bởi mẫu truy cập**, dù mục tiêu có thể là giảm số lần đọc vật lý.

### “Replication đồng nghĩa với dữ liệu luôn mới nhất”

Bản sao phục vụ khả năng chịu lỗi và/hoặc mở rộng khả năng đọc. Mức nhất quán phụ thuộc cách ghi, cách đọc, cấu hình, lỗi mạng và sản phẩm. Nếu nghiệp vụ yêu cầu đọc-sau-ghi, phải xác định cách hệ quản trị bảo đảm tính chất đó.

### “Cùng kiểu NoSQL thì tối ưu vật lý giống nhau”

Hai document database có thể khác cơ chế index, transaction, sharding hoặc layout. Hai wide-column database có thể khác cách tổ chức file, replication và giới hạn partition. Không nên chuyển nguyên cấu hình của sản phẩm này sang sản phẩm khác chỉ vì cùng nhãn mô hình.

## 11. Quy trình thiết kế đi từ logic đến vật lý

### Bước 1 — Mô tả dữ liệu và bất biến nghiệp vụ

Xác định thực thể, định danh, thuộc tính, quan hệ và quy tắc không được vi phạm: đơn không được có số lượng âm, sự kiện không được tính hai lần, mỗi đặt chỗ có vòng đời rõ ràng. Nêu dữ liệu nào là nguồn sự thật và dữ liệu nào có thể tái tạo.

### Bước 2 — Viết mẫu truy cập trước khi chọn index và shard

Với mỗi truy vấn, ghi lại khóa lọc, điều kiện khoảng, sort, phân trang, số bản ghi dự kiến, tần suất và độ trễ yêu cầu. Tương tự, mô tả thao tác ghi: thay đổi một object hay nhiều object, có cạnh tranh không, cần đọc lại giá trị mới ngay không.

Ví dụ:

~~~text
GET /orders/{orderId}
GET /customers/{customerId}/orders?before=...&limit=20
POST /orders/{orderId}/cancel
~~~

### Bước 3 — Chọn cấu trúc logic và ranh giới aggregate

Quyết định dùng document lồng nhau, tham chiếu, record sự kiện, đỉnh/cạnh hay cặp key–value. Tính tới sự phát triển kích thước, vòng đời bản ghi và phần dữ liệu được cập nhật cùng nhau. Không nhúng một danh sách không có giới hạn chỉ để giảm một truy vấn.

### Bước 4 — Ánh xạ xuống cơ chế vật lý của sản phẩm

Xác định primary/partition key, sort/clustering key, index, TTL, replication, storage engine và bộ đệm phù hợp với tính năng thực sự của sản phẩm. Dự kiến trường hợp cần đọc nhiều shard, hot key, đồng bộ bản chiếu và các thao tác sửa/xóa.

### Bước 5 — Đo đường thực thi, không chỉ đo API

Kiểm tra với dữ liệu và phân bố khóa gần thực tế: độ trễ p50/p95/p99, độ trễ ghi, tỉ lệ cache hit, số partition/shard được đọc, I/O, dung lượng index, lag bản sao, lưu lượng mạng và thời gian compaction. Nếu truy vấn chậm, tìm nguyên nhân là mô hình logic, thiếu index, shard key không phù hợp hay giới hạn hạ tầng trước khi thay đổi cả kiến trúc.

### Bước 6 — Kiểm tra tính đúng đắn và khả năng phục hồi

Diễn tập thao tác ghi đồng thời, retry, duplicate event, thay đổi schema, lỗi một nút, backup/restore và tái dựng bản chiếu. Tối ưu vật lý chỉ có ý nghĩa nếu vẫn bảo vệ được những bất biến logic đã đặt ra.

## 12. Bài tập phân loại quyết định

Hãy xác định mỗi quyết định sau chủ yếu thuộc **logic**, **vật lý** hay **giao điểm giữa hai tầng**, và giải thích:

1. Sự kiện có \`deviceId\`, \`measuredAt\`, \`temperatureC\`; không cho phép một phép đo có hai \`eventId\` khác nhau để biểu diễn cùng sự kiện nguồn.
2. Lưu mỗi đơn hàng dưới dạng một document chứa \`items[]\`.
3. Phân phối document lên các shard bằng hash của \`tenantId\`.
4. Xây index phụ theo \`status, createdAt\`.
5. Đặt replica ở ba vùng khả dụng.
6. Xây thêm bản chiếu \`ordersByCustomer\` từ nguồn đơn hàng.
7. Sắp các phép đo trong partition theo timestamp.
8. Đổi định dạng \`customerAddress\` từ chuỗi thành object.

**Gợi ý đáp án:**

| Mục | Phân loại | Giải thích |
| --- | --- | --- |
| 1 | Logic | Ý nghĩa sự kiện, danh tính và quy tắc dữ liệu |
| 2 | Logic | Cấu trúc object và ranh giới aggregate mà ứng dụng thao tác |
| 3 | Vật lý, với khóa ở giao điểm | Cách phân bố dữ liệu dùng một thuộc tính có ý nghĩa logic |
| 4 | Vật lý | Cấu trúc phụ để tăng tốc truy vấn |
| 5 | Vật lý/triển khai | Vị trí các bản sao và khả năng chịu lỗi |
| 6 | Giao điểm | Thêm cách nhìn dữ liệu logic, cần cơ chế duy trì/đồng bộ vật lý |
| 7 | Vật lý, với khóa ở giao điểm | Thứ tự lưu phục vụ truy vấn khoảng theo thuộc tính logic |
| 8 | Logic | Thay đổi hợp đồng cấu trúc dữ liệu mà ứng dụng đọc/ghi |

## Kết luận

**Mô hình logic** trả lời “dữ liệu là gì, liên hệ ra sao, ứng dụng truy cập và cần bảo vệ điều gì”. **Tổ chức vật lý** trả lời “hệ quản trị đặt, sắp, tìm, sao chép và lưu các byte ấy thế nào”. Trong NoSQL, ranh giới giữa hai tầng có thể giao nhau tại partition key, clustering key và các bản chiếu theo truy vấn, nhưng hai câu hỏi vẫn cần được phân tích riêng.

Thiết kế tốt bắt đầu từ ý nghĩa nghiệp vụ và mẫu truy cập, sau đó chọn cấu trúc logic, ánh xạ xuống khả năng vật lý của sản phẩm, đo hiệu năng và kiểm chứng tính đúng đắn. Một biểu diễn document, key–value, wide-column hay graph **không tự động bảo đảm** một kiểu lưu trữ hay hiệu năng cụ thể; chính ánh xạ từ logic sang vật lý mới quyết định chi phí của các thao tác trong thực tế.
