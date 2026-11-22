# UUID, định danh có thứ tự và tác động đến phân phối tải

Trong một hệ thống NoSQL, mỗi sản phẩm, đơn hàng hoặc sự kiện thường cần một **định danh ổn định** để truy cập, đối chiếu và liên kết dữ liệu. Tuy nhiên, hai định danh đều duy nhất chưa chắc có cùng ảnh hưởng đến hiệu năng. ID tăng dần có thể giúp một chỉ mục lưu theo thứ tự ghi tuần tự hơn, nhưng cũng có thể dồn toàn bộ ghi mới vào một vùng dữ liệu. ID ngẫu nhiên có thể trải rộng các khóa, nhưng khiến một số cấu trúc chỉ mục phải cập nhật tại nhiều vị trí. ID chứa thời gian như UUIDv7 đem lại khả năng sắp xếp gần theo thời gian, song **không tự động giải quyết phân phối tải**.

Bài học này đặt vấn đề định danh trong ngữ cảnh **Khóa và định danh** của Database No SQL: phân biệt ID với khóa dùng để phân vùng, hiểu các họ UUID và ID có thứ tự, rồi chọn cách lưu và thử nghiệm theo truy vấn và tải thực tế.

## 1. Phân biệt định danh, khóa chính, khóa phân vùng và khóa sắp xếp

Trước khi so sánh UUIDv4 với UUIDv7, cần tách bốn khái niệm:

| Khái niệm | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Định danh thực thể (entity ID)** | Gọi tên ổn định một thực thể, không đổi khi thuộc tính thay đổi | `orderId = UUIDv7(...)` |
| **Khóa chính (primary key)** | Phân biệt bản ghi theo quy tắc duy nhất của kho dữ liệu | `orderId`, hoặc cặp `(tenantId, orderId)` |
| **Khóa phân vùng (partition/shard key)** | Quyết định bản ghi hoặc yêu cầu sẽ đi tới vùng/node nào | `hash(orderId)`, `tenantId`, `(day, bucket)` |
| **Khóa sắp xếp (sort/clustering key)** | Xác định thứ tự bản ghi bên trong phạm vi được tổ chức theo khóa đó | `createdAt#orderId` |

Trong một số NoSQL, khóa chính chỉ có một thành phần và cũng là khóa phân vùng. Ở hệ thống khác, khóa chính gồm **partition key + sort key**. Có cơ sở dữ liệu quyết định shard bằng phép hash trên một trường do người dùng chọn, có hệ thống dùng khoảng khóa (*range partitioning*), và có hệ thống quản lý việc phân vùng khác. **Không có một quy tắc định tuyến chung cho mọi NoSQL.**

Hãy xét hai tài liệu:

~~~json
{
  "orderId": "0196...-7...-...",
  "tenantId": "shop-17",
  "createdAt": "2026-11-14T08:20:00Z",
  "total": 350000
}
~~~

Một thiết kế có thể dùng `orderId` làm cả ID và partition key. Thiết kế khác dùng `tenantId` để đặt đơn cùng cửa hàng gần nhau. Thiết kế thứ ba dùng `day#bucket` để phân tán ghi theo ngày. **Cùng một giá trị `orderId` có thể dẫn đến phân phối tải rất khác** tùy cách kho dữ liệu sử dụng nó.

## 2. Chọn ID cần cân bằng những thuộc tính nào?

Không thể đánh giá ID chỉ bằng câu hỏi “có trùng nhau không?”. Cần xem đồng thời:

1. **Duy nhất trong phạm vi nào?** Một tiến trình, một node, một vùng, nhiều vùng hay toàn hệ thống?
2. **Sinh ở đâu?** Ứng dụng, client offline, một dịch vụ cấp phát ID tập trung, hay cơ sở dữ liệu?
3. **Có thứ tự không?** Thứ tự tăng toàn cục, gần theo thời gian, chỉ tăng trong một node, hay hoàn toàn ngẫu nhiên?
4. **ID được lưu và so sánh thế nào?** Dạng nhị phân 16 byte, dạng chuỗi, số 64 bit; phép so sánh byte, số hay collation của chuỗi?
5. **ID là khóa định tuyến hay chỉ là một thuộc tính?** Hash partition, range partition và index theo thứ tự có kết quả khác nhau.
6. **Người dùng có thấy ID không?** ID chứa thời gian hoặc thông tin máy có thể tiết lộ metadata; ID đoán được không được thay thế phân quyền.
7. **Có cần tạo trước khi lưu không?** Hệ thống phân tán hoặc offline thường muốn tạo ID mà không gọi bộ cấp phát chung.

Các thuộc tính này tạo ra những đánh đổi, không có “kiểu ID tốt nhất cho mọi NoSQL”.

## 3. UUID là gì và có những phiên bản quan trọng nào?

**UUID (Universally Unique Identifier)** là định danh 128 bit. Dạng biểu diễn văn bản quen thuộc có 32 chữ số thập lục phân, thêm bốn dấu gạch ngang:

~~~text
xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
           ^         ^
     vùng version   vùng variant
~~~

Ví dụ một UUIDv4 hợp lệ:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

Dạng văn bản canonical dài **36 ký tự**, nhưng giá trị UUID gồm **16 byte**. Nếu kho dữ liệu/driver hỗ trợ kiểu UUID nhị phân hoặc kiểu UUID chuyên dụng, nên xem xét sử dụng thay vì mặc định lưu dạng chuỗi dài. Cần nhất quán trong cách encode và so sánh giữa các ứng dụng.

Các phiên bản đáng biết:

| Dạng ID | Cách hình thành ở mức khái quát | Thứ tự thường thấy | Điểm cần cân nhắc |
| --- | --- | --- | --- |
| **UUIDv4** | Chủ yếu là bit ngẫu nhiên; có 122 bit ngẫu nhiên | Không mang thứ tự thời gian | Dễ sinh phân tán; kém tính cục bộ trong index sắp xếp theo ID |
| **UUIDv1** | Thời gian cùng thông tin/giá trị nhận dạng node và clock sequence | Không sắp xếp theo thời gian tự nhiên khi so chuỗi canonical trong mọi trường hợp | Có rủi ro lộ thông tin thời gian/node tùy cách sinh |
| **UUIDv6** | Sắp lại bố cục kiểu thời gian từ v1 để hỗ trợ thứ tự | Gần theo thời gian nếu biểu diễn/so sánh đúng | Cần kiểm tra hỗ trợ ở thư viện và kho dữ liệu |
| **UUIDv7** | Dấu thời gian mili giây ở phần đầu, phần sau phục vụ ngẫu nhiên/chống trùng và có thể dùng counter | **Gần theo thời gian** ở cách so sánh tương thích | Chèn tập trung vào cuối vùng ID nếu lưu theo thứ tự; không bảo đảm đúng thứ tự xảy ra của mọi sự kiện |
| **UUIDv8** | Bố cục tùy biến theo quy tắc phiên bản | Tùy thiết kế | Chỉ dùng khi có hợp đồng định danh và khả năng tương thích rõ ràng |

UUIDv4 và UUIDv7 thường là hai lựa chọn được đem so sánh nhất trong các thiết kế mới cần ID độc lập giữa các tiến trình. Tiêu chuẩn hiện đại cho các phiên bản này là **RFC 9562**.

### 3.1. UUIDv4: ngẫu nhiên, không mã hóa thời gian

UUIDv4 có các bit version/variant cố định và **122 bit dành cho ngẫu nhiên**. Nếu dùng bộ sinh ngẫu nhiên phù hợp, nguy cơ va chạm rất thấp ở nhiều khối lượng sử dụng thực tế; điều này **không phải chứng minh toán học rằng sẽ không bao giờ trùng**.

Ưu điểm:

- Không cần đồng hồ đồng bộ hoặc server cấp phát ID chung.
- Có thể sinh trước khi gửi yêu cầu, kể cả khi thiết bị mất kết nối.
- Khi **hash chính ID** để định tuyến và có nhiều ID khác nhau, các khóa thường được phân bổ khá đều.
- Không trực tiếp mã hóa thời điểm tạo vào ID.

Nhược điểm:

- Không xác định được thứ tự tạo qua ID; muốn “mới nhất trước” cần trường thời gian hoặc một cấu trúc chỉ mục khác.
- Nếu lưu vào **B-tree/B+tree sắp theo ID**, giá trị mới thường rơi vào nhiều vùng khác nhau, có thể gây ghi rải rác, cache page kém hiệu quả hoặc split page.
- Trong một số hệ thống, việc lưu chuỗi UUID thay vì kiểu binary/UUID chuyên dụng làm tăng kích thước khóa và index.

Ví dụ Java:

~~~java
import java.util.UUID;

public class OrderIdExample {
    public static void main(String[] args) {
        UUID orderId = UUID.randomUUID(); // UUID phiên bản 4
        System.out.println(orderId);
    }
}
~~~

`UUID.randomUUID()` trong Java cung cấp UUIDv4. Không nên suy luận rằng Java 21 mặc định có API tạo UUIDv7 tương đương; muốn UUIDv7 cần chọn thư viện/triển khai thích hợp và kiểm tra tính đúng của generator.

### 3.2. UUIDv7: chứa thời gian ở phần đầu

UUIDv7 dùng **48 bit đầu cho Unix timestamp tính bằng mili giây**. Sau đó là các bit version, variant và những bit còn lại được sử dụng cho phần ngẫu nhiên, counter hoặc trường phụ theo cách sinh tuân thủ tiêu chuẩn. Tổng lượng bit khả dụng cho phần sau timestamp và các bit cố định là **74 bit**.

~~~text
UUIDv7 — 128 bit

| 48 bit timestamp (milliseconds) | version=0111 | 12 bit rand_a |
| variant=10 | 62 bit rand_b |

Trong một số phương án generator, một phần rand_a/rand_b có thể
được sử dụng theo quy tắc counter/monotonicity của tiêu chuẩn.
~~~

Vì timestamp nằm ở vùng bit có ý nghĩa cao, UUIDv7 **thường sắp xếp gần với thời gian sinh**, miễn là hệ thống so sánh UUID bằng thứ tự byte/binary tương thích hoặc biểu diễn canonical thống nhất. Nhưng lưu ý:

- Hai ID được tạo **cùng mili giây** không mặc nhiên có thứ tự tạo nếu generator không hỗ trợ monotonicity trong khoảng đó.
- Hai máy có **clock lệch** có thể tạo ID có thứ tự khác với thứ tự sự kiện thực tế.
- ID có thể được tạo trước khi dữ liệu được ghi/commit; thứ tự ID vì thế **không phải thứ tự commit**.
- Timestamp trong ID do bên sinh cung cấp; không thể coi là thời gian nghiệp vụ đáng tin nếu client có thể can thiệp.

UUIDv7 hữu ích khi muốn **sinh ID phân tán** đồng thời có tính gần theo thời gian. Nó không thay thế `createdAt` do hệ thống có thẩm quyền quản lý, cũng không thay thế event sequence/offset khi cần thứ tự chính xác.

### 3.3. Các ID có thứ tự khác

Một số hệ sinh thái còn dùng:

| Kiểu | Bố cục điển hình | Khả năng sắp xếp | Đánh đổi |
| --- | --- | --- | --- |
| **ULID** | 128 bit: 48 bit thời gian mili giây và 80 bit ngẫu nhiên; thường biểu diễn 26 ký tự Base32 | Tăng gần theo thời gian khi encode/compare đúng; một số generator có chế độ monotonic | Không phải UUID theo format/version UUID; cần thống nhất cách chuyển đổi và xử lý khi nhiều ID cùng mili giây |
| **KSUID** | 160 bit: timestamp độ phân giải giây với epoch riêng và 128 bit ngẫu nhiên; thường chuỗi Base62 27 ký tự | Gần theo thời gian ở độ phân giải giây | Lớn hơn UUID; trong cùng giây không có thứ tự chính xác nếu dùng ngẫu nhiên |
| **Snowflake-like ID** | Thường 64 bit chứa thời gian, ID máy/worker và sequence trong một bố cục tự định nghĩa | Có thể tăng gần theo thời gian hoặc theo producer | Cần quản lý worker ID, clock rollback, giới hạn throughput/sequence; không có một bố cục Snowflake thống nhất cho mọi hệ thống |
| **Số nguyên tăng dần từ một bộ cấp phát** | Sequence/counter | Có thứ tự theo bộ cấp phát | Đơn giản nhưng dễ tạo điểm tranh chấp hoặc phụ thuộc vào dịch vụ cấp phát; không phải timestamp của nghiệp vụ |

Với Snowflake, không nên mặc định mỗi hệ thống đều dùng đúng một số bit cố định. Ví dụ cấu hình “41 bit thời gian, 10 bit worker, 12 bit sequence” là một bố cục phổ biến, nhưng có thể thay đổi. Phải xét ngưỡng sequence mỗi khoảng thời gian, phạm vi worker và cách xử lý clock rollback của triển khai cụ thể.

## 4. Vì sao thứ tự ID ảnh hưởng đến ghi và phân phối tải?

Có hai cơ chế độc lập nhưng dễ bị gộp làm một:

1. **Vị trí lưu trong cấu trúc chỉ mục:** các ID mới chèn vào vùng nào của B-tree, LSM tree, clustered index hoặc cấu trúc nội bộ?
2. **Vị trí mạng và xử lý:** key được đưa đến node/partition nào theo quy tắc định tuyến?

ID có thứ tự có thể làm thay đổi cơ chế thứ nhất. Cơ chế thứ hai chỉ thay đổi khi **partition key, thuật toán hash/range và cấu hình phân vùng có sử dụng đặc tính của ID**.

### 4.1. Chỉ mục theo thứ tự: tăng tính cục bộ nhưng có nguy cơ dồn ghi

Giả sử một index giữ các khóa ở dạng tăng dần:

~~~text
UUIDv4 mới:
... [00-1F] ... [20-3F] ... [40-5F] ... [60-7F] ... [80-FF]
          ↑              ↑                       ↑
         ghi            ghi                     ghi

UUIDv7 được sinh liên tục:
... [giờ cũ] ... [phút trước] ... [thời điểm mới nhất]
                                               ↑↑↑
                                         ghi nối tiếp
~~~

Với B-tree/B+tree, ID gần tăng có thể tạo **tính cục bộ ghi** vào các trang gần nhau, giảm thao tác chèn ngẫu nhiên và cải thiện cách cache những trang hiện hoạt. Tuy vậy, nếu một trang/vùng cuối chịu quá nhiều ghi cùng lúc, có thể phát sinh **tranh chấp trang hoặc điểm ghi nóng**. Kết quả phụ thuộc vào thiết kế engine, kích thước trang, buffer pool, cơ chế lock/latch và tốc độ ghi.

Với engine theo kiểu **LSM-tree**, dữ liệu thường được ghi vào memtable và WAL trước khi flush/compact; so sánh random-vs-sequential có cơ chế và độ lớn hiệu ứng khác B-tree. Vì vậy không thể nói “UUIDv7 chắc chắn nhanh hơn UUIDv4 trên mọi NoSQL” chỉ dựa trên thứ tự ID.

### 4.2. Hash partition: thời gian trong UUIDv7 không tự sinh điểm nóng

Trong mô hình minh họa:

~~~text
partition = HASH(orderId) MOD N
~~~

Nếu hàm hash phân bố tốt, cả UUIDv4 và UUIDv7 có nhiều giá trị ID khác nhau đều **có thể trải đều** qua N partition. Phần timestamp nằm ở đầu UUIDv7 không còn được dùng nguyên trạng để quyết định partition vì đã qua hash.

~~~mermaid
flowchart LR
    G["Sinh ID\nUUIDv4 hoặc UUIDv7"] --> H["Hash toàn bộ ID"]
    H --> P0["Partition 0"]
    H --> P1["Partition 1"]
    H --> P2["Partition 2"]
    H --> P3["Partition 3"]
~~~

Tuy nhiên, hash chỉ phân phối **các giá trị khóa khác nhau**. Nếu 40% traffic cùng truy cập `productId = P123`, mọi lần truy cập khóa đó vẫn thường đến cùng một partition/đầu mối xử lý. UUID ngẫu nhiên hay có thứ tự **không thể tự tách một hot key đang bị đọc/ghi lặp lại**.

Ví dụ cụ thể: 100.000 thao tác/giây được gửi tới bốn partition. Trong đó **30.000 thao tác/giây cùng một key**, 70.000 thao tác còn lại phân đều. Partition chứa hot key có thể nhận khoảng **47.500 thao tác/giây** (30.000 + 70.000/4), các partition khác khoảng **17.500 thao tác/giây**. Cụm nhìn chung chưa chắc đầy CPU, nhưng partition nóng có thể bị throttling.

Đây là mô hình số học minh họa, chưa tính replica, caching, adaptive splitting, giới hạn tài nguyên hay cách route thật của từng sản phẩm.

### 4.3. Range partition: ID tăng có thể làm một vùng chịu phần lớn ghi

Một hệ thống chia khóa theo khoảng:

~~~text
Partition A: 0000 ... 2999
Partition B: 3000 ... 5999
Partition C: 6000 ... 8999
Partition D: 9000 ... +∞
~~~

Nếu khóa mới luôn tăng, những ghi mới có thể liên tục đi vào **partition ở cuối dải**. Đây là hiện tượng *moving hot spot*: khi vùng cuối bị chia, đỉnh ghi lại di chuyển sang vùng cuối mới. Cơ chế tách/phân phối tự động của một số engine có thể giảm tác động, nhưng phải đo trên sản phẩm và cấu hình thực tế.

UUIDv4 trên một range index có thể phân bố ghi rộng hơn theo khoảng khóa, đánh đổi tính cục bộ trong chỉ mục. UUIDv7, ULID hoặc sequence có thể ghi tập trung theo thời gian. Cái nào tốt hơn phụ thuộc **tải, index, cách split, giới hạn throughput mỗi partition và câu truy vấn**.

### 4.4. Nhìn bảng để tránh suy luận sai

| ID / định tuyến | Hướng phân bố ghi mới | Khả năng truy vấn theo thời gian | Lưu ý |
| --- | --- | --- | --- |
| UUIDv4 + hash toàn ID | Thường đều với nhiều ID riêng biệt | Cần thuộc tính/index thời gian khác | Hot key vẫn nóng |
| UUIDv7 + hash toàn ID | Thường đều với nhiều ID riêng biệt | ID chứa thời gian nhưng thứ tự toàn cụm vẫn cần cách truy vấn/merge | Không mặc nhiên hot partition chỉ vì ID tăng |
| UUIDv7 + range theo ID | Có thể tập trung vào vùng khóa mới nhất | Có thể thuận lợi cho range scan theo ID nếu thiết kế phù hợp | Dễ xuất hiện vùng ghi nóng, tùy engine |
| Sequence tăng dần + range | Có xu hướng dồn vào vùng cuối | Thứ tự dễ hiểu hơn trong phạm vi sequence | Cần cấp phát sequence và xử lý bottleneck |
| `tenantId` + hash tenant | Tập trung toàn bộ dữ liệu của tenant trên partition tương ứng | Sort key bên trong tenant có thể dùng UUIDv7/createdAt | Tenant lớn có thể gây hot partition |
| `day` + range/hash ngày | Mọi ghi “hôm nay” có thể tập trung theo day | Thuận tiện đọc theo ngày | Thường phải thêm bucket nếu throughput theo ngày quá cao |

**Quy tắc cốt lõi:** đánh giá đồng thời *giá trị ID*, *partition key*, *kiểu phân vùng* và *các index phụ*. Không thể dự đoán độ lệch tải chỉ từ chuỗi UUID.

## 5. Thiết kế từ truy vấn thực tế: ví dụ đơn hàng

Giả sử nền tảng có các yêu cầu:

- Tìm một đơn theo `orderId`.
- Liệt kê đơn của một cửa hàng theo thời gian, mới nhất trước.
- Ghi nhiều đơn mỗi giây; ngày khuyến mãi có cửa hàng lớn chiếm phần lớn giao dịch.
- Tìm đơn cần độ trễ thấp; không được tạo trùng do retry.

### 5.1. Phương án A: ID là partition key

~~~text
PK = orderId (UUIDv4 hoặc UUIDv7)
attributes = tenantId, createdAt, total, status, ...
~~~

Nếu định tuyến bằng hash toàn `orderId`, ghi của nhiều đơn khác nhau có thể được trải đều. Truy cập theo ID thuận tiện. Nhưng liệt kê **đơn của một cửa hàng theo thời gian** đòi một index hoặc read model khác; quét toàn kho để lọc/sắp xếp là không hợp lý ở quy mô lớn.

Một phương án là xây index đọc phụ:

~~~text
INDEX:
    partitionKey = tenantId
    sortKey      = createdAt#orderId
~~~

Index giúp truy vấn theo cửa hàng, nhưng nếu một `tenantId` rất nóng, **index phụ có thể là nơi nghẽn**, dù bảng chính đã phân phối ghi đều. Không nên chỉ đo primary table rồi kết luận toàn bộ thiết kế cân bằng.

### 5.2. Phương án B: tenant là partition key, UUIDv7 là sort key

~~~text
PK = tenantId
SK = orderId (UUIDv7)
~~~

Trong phạm vi một tenant, UUIDv7 có thể giúp trả đơn gần theo thời gian (với điều kiện cách so sánh phù hợp và sự sai lệch giờ không làm hỏng yêu cầu). Tuy nhiên, một cửa hàng có lưu lượng lớn sẽ dồn truy cập về cùng khóa phân vùng logic. Phương án này có thể hiệu quả với nhiều tenant nhỏ, nhưng phải kiểm tra khả năng tách vùng logic và giới hạn mỗi partition của sản phẩm cụ thể.

Khi thật sự cần thứ tự commit hoặc thời gian nhận đơn từ server, nên có **trường `createdAt` tin cậy và tie-breaker ổn định**, thay vì chỉ dựa vào ID sinh trên thiết bị khách hàng.

### 5.3. Phương án C: chia bucket cho tenant nóng

~~~text
PK = tenantId#bucket
SK = createdAt#orderId

bucket = stableHash(orderId) % 16
~~~

Mỗi đơn được đưa tới một trong 16 bucket logic. Ví dụ:

~~~text
shop-17#00  -> các đơn nhóm 00, sắp theo thời gian
shop-17#01  -> các đơn nhóm 01, sắp theo thời gian
...
shop-17#15  -> các đơn nhóm 15, sắp theo thời gian
~~~

**Lợi ích:** ghi từ một tenant có nhiều `orderId` khác nhau có thể phân tán qua nhiều partition key logic.

**Chi phí:** để lấy 20 đơn mới nhất của shop-17, ứng dụng có thể phải truy vấn nhiều bucket rồi **merge theo `(createdAt, orderId)`**, quản lý phân trang/cursor ở nhiều nhánh và tránh trả lặp. Nếu truy cập bằng `orderId` nhưng không biết tenant hoặc bucket, cần một cách suy ra bucket hay một bảng tra cứu phụ. Đổi số bucket từ 16 lên 32 cũng cần một kế hoạch di trú/phiên bản khóa: các bản ghi cũ không tự di chuyển.

Hàm `stableHash` ở đây là một **hợp đồng deterministic được thống nhất giữa các ngôn ngữ và phiên bản**; không dùng tùy tiện một hàm hash của runtime mà không kiểm chứng tính ổn định giữa các service. Bucket chỉ nên được thêm khi có dữ liệu tải chứng minh cần thiết.

### 5.4. Khi nào cần hai khóa khác nhau cho cùng thực thể?

Có thể giữ một ID công khai `orderId` bất biến và dùng một khóa lưu trữ khác để tối ưu truy cập:

~~~json
{
  "orderId": "<UUIDv7>",
  "partitionKey": "shop-17#08",
  "sortKey": "2026-11-14T08:20:00.123Z#<UUIDv7>",
  "tenantId": "shop-17",
  "createdAt": "2026-11-14T08:20:00.123Z"
}
~~~

Không nhất thiết phải “nhét” tenant, thời gian, loại thực thể, shard và môi trường vào một ID công khai. Duy trì **ID độc lập** giúp hợp đồng API ổn định khi chiến lược lưu trữ thay đổi; khóa định tuyến và index có thể được thiết kế theo câu hỏi dữ liệu thực tế.

## 6. UUIDv7 có thực sự thay thế trường thời gian?

Không hoàn toàn. Cần phân biệt ít nhất bốn mốc thời gian:

1. **Thời điểm ID được sinh**: đối với UUIDv7, timestamp được mã hóa ngay trong ID.
2. **Thời điểm yêu cầu đến server**: có thể khác lúc ID được tạo, nhất là client offline/retry.
3. **Thời điểm giao dịch được commit**: dữ liệu có thể nằm trong queue hoặc chờ tranh chấp trước khi được chấp nhận.
4. **Thời điểm nghiệp vụ có hiệu lực**: ví dụ lịch đặt phòng bắt đầu ngày mai, khác hoàn toàn thời điểm tạo bản ghi.

Một ví dụ:

~~~text
08:00:00  Thiết bị A tạo UUIDv7-X khi đang offline.
08:01:00  Thiết bị B gửi và lưu UUIDv7-Y thành công.
08:10:00  Thiết bị A kết nối lại, gửi X và lưu thành công.

Theo timestamp trong ID: X có thể đứng trước Y.
Theo commit time:        Y đứng trước X.
~~~

Nếu yêu cầu là “các bản ghi được tạo trên thiết bị theo thời gian gần đúng”, UUIDv7 có thể hữu ích. Nếu yêu cầu là “đơn được hệ thống xác nhận gần nhất”, phải định nghĩa **thời gian server hoặc sequence của luồng commit**. Với các bản ghi trùng timestamp, cần tie-breaker để phân trang ổn định.

Ví dụ một con trỏ truy vấn theo thứ tự giảm:

~~~text
ORDER BY createdAt DESC, orderId DESC
cursor = (lastCreatedAt, lastOrderId)
~~~

Đây là ý tưởng logic; cú pháp và cấu trúc index/khóa trong từng NoSQL sẽ khác nhau. Dùng **keyset pagination** theo cùng cặp khóa thường giúp ổn định hơn việc dùng offset lớn, nhưng vẫn phải xét bản ghi mới đến, xóa/sửa và snapshot consistency.

## 7. Sinh ID phân tán: va chạm, đồng hồ và thứ tự

### 7.1. Duy nhất không đồng nghĩa với một thứ tự toàn cục

Với UUIDv4, không có cơ chế thứ tự. Với UUIDv7 và ULID, timestamp giúp nhóm những ID sinh gần nhau, nhưng không cung cấp một **total order đúng theo sự kiện/commit giữa nhiều node**. Một generator kiểu Snowflake có thể gắn worker ID và sequence để giảm va chạm, nhưng các node vẫn chịu ảnh hưởng của clock skew nếu không có giao thức phối hợp chặt.

Đòi hỏi “mọi sự kiện từ mọi nơi phải có thứ tự duy nhất, tăng tuyệt đối theo commit” là một bài toán phân tán khác với “các ID không bị trùng”. Khi thực sự cần thứ tự toàn cục, phải xét một sequencer/consensus log hoặc thiết kế nghiệp vụ giới hạn phạm vi cần thứ tự; đánh đổi sẽ là chi phí phối hợp và khả năng mở rộng.

### 7.2. Điều gì xảy ra khi đồng hồ lùi?

Giả sử node sinh UUIDv7 trong mili giây `T`, sau đó đồng hồ hệ thống lùi về `T-500` ms. Những ID sinh tiếp có thể nhỏ hơn ID trước đó trong thứ tự từ điển. Chuyện này tác động tới việc coi ID là dấu thời gian tăng.

Một generator phù hợp có thể duy trì trạng thái monotonic, xử lý clock rollback, tăng counter hoặc chờ đồng hồ, nhưng cách xử lý cụ thể là **hợp đồng triển khai**. Cần kiểm tra:

- Phạm vi monotonicity: trong một tiến trình, một node hay toàn hệ thống?
- Số ID tối đa sinh trong cùng một mili giây có vượt cấu hình counter/random không?
- Restart tiến trình có thể làm mất trạng thái chống trùng hay không?
- Khi đồng hồ lùi hoặc không đồng bộ, generator báo lỗi, chờ hay tiếp tục theo chiến lược nào?

Với Snowflake-like ID, còn cần bảo đảm hai worker không vô tình sử dụng cùng một ID máy trong cùng khoảng thời gian và không quay lui counter/clock theo cách gây trùng.

### 7.3. Xử lý va chạm và retry ở lớp nghiệp vụ

Mặc dù xác suất trùng UUIDv4/v7 được tạo đúng rất thấp, hệ thống vẫn cần **ràng buộc duy nhất** ở phạm vi thực thể được lưu nếu yêu cầu nghiệp vụ đòi hỏi. Nếu một yêu cầu ghi thất bại vì trùng khóa, phải phân biệt trùng do sinh ID với **retry của cùng một thao tác**.

Ví dụ khi tạo đơn:

~~~text
POST /orders
Idempotency-Key: req-abc-123
Body: {...}

Client timeout sau khi server đã commit.
Client retry cùng Idempotency-Key.
Server phải trả kết quả của thao tác trước,
không tạo thêm đơn mới chỉ vì lần retry đã sinh ID khác.
~~~

ID duy nhất giải quyết bài toán **định danh bản ghi**; *idempotency key* và cơ chế ghi nguyên tử giải quyết bài toán **một lệnh nghiệp vụ bị gọi lặp**. Hai loại khóa có thể cùng giá trị trong một thiết kế cụ thể, nhưng không được đồng nhất trách nhiệm một cách mặc định.

## 8. Kích thước và cách biểu diễn ID cũng có chi phí

Nhiều người chỉ nhìn số byte của bản ghi chính mà quên rằng khóa có thể xuất hiện ở nhiều nơi:

- Primary index và secondary index.
- Khóa ngoại logic hoặc trường tham chiếu trong tài liệu khác.
- Cache key, message payload, log, tracing và API.
- Các bản sao/replica, WAL và dữ liệu chuyển qua mạng.

Một UUID có kích thước giá trị **16 byte**; biểu diễn canonical text gồm **36 ký tự ASCII**, và khi lưu dạng chuỗi trong một sản phẩm cụ thể còn có thể phát sinh chi phí lưu trữ/metadata. Số nguyên 64 bit có kích thước giá trị **8 byte**. Không thể từ đó kết luận index sẽ có kích thước chính xác theo tỷ lệ 16:36:8, vì còn header, alignment, cấu trúc trang, nén, con trỏ và số bản sao của khóa.

### 8.1. Thứ tự biểu diễn phải thống nhất

Nếu cùng UUID được lưu một nơi dạng binary, nơi khác dạng chuỗi:

- Phải xác nhận thứ tự byte và cách chuyển đổi tại driver/database.
- Không trộn collation chuỗi phân biệt chữ hoa/thường hoặc quy tắc locale với kỳ vọng so sánh UUID.
- Với UUIDv7, tính “time-sortable” chỉ có ý nghĩa khi cách so sánh thực tế bảo toàn thứ tự phần timestamp ở đầu.
- Nếu dùng ULID/KSUID, cần biết cách encode có bảo toàn thứ tự mong muốn hay không.

Đặc biệt, không nên thiết kế một hệ thống dựa vào thứ tự hiển thị của ID khi database lưu và so sánh dữ liệu theo kiểu khác mà chưa thử nghiệm. Sử dụng một chuẩn serialization thống nhất giữa ứng dụng, event, backup và index.

### 8.2. ID không thay thế phân quyền

Một ID khó đoán không phải là chính sách kiểm soát truy cập. API `GET /orders/{orderId}` vẫn phải kiểm tra người gọi có quyền đọc đơn đó hay không. UUIDv7 tiết lộ **xấp xỉ thời gian tạo**; sequence hoặc Snowflake-like ID có thể cho phép suy đoán nhịp sinh ID hoặc hạ tầng phát sinh tùy bố cục.

Nếu ID xuất hiện công khai và metadata thời gian là nhạy cảm trong bài toán cụ thể, hãy đánh giá UUIDv4 hoặc một public token độc lập. Đừng coi tính ngẫu nhiên của UUID là cơ chế bảo mật duy nhất, và đừng dùng UUIDv7 timestamp làm bằng chứng đáng tin về thời điểm sự kiện.

## 9. Thử nghiệm tác động thật của ID lên tải NoSQL

Một quyết định giữa UUIDv4 và UUIDv7 nên được xác nhận trong **điều kiện phân vùng, chỉ mục và truy vấn thực tế**. Thử nghiệm chỉ sinh 1 triệu UUID để đo tốc độ generator không nói được nhiều về throughput của database.

### 9.1. Thiết kế ma trận thử nghiệm

Giữ dữ liệu và cơ cấu thao tác tương đương khi so các phương án:

| Thử nghiệm | ID và khóa lưu trữ | Câu hỏi |
| --- | --- | --- |
| A | UUIDv4, hash toàn ID | Mức phân phối ghi, độ trễ read-by-ID và dung lượng index là bao nhiêu? |
| B | UUIDv7, hash toàn ID | Có khác biệt gì với A khi vẫn dùng cùng cơ chế shard? |
| C | UUIDv7, range theo ID | Tính cục bộ chèn cải thiện bao nhiêu, có moving hot spot không? |
| D | UUIDv7, partition theo tenant | Tenant lớn có chiếm một vùng quá tải không? |
| E | UUIDv7, tenant + bucket | Độ cân bằng cải thiện đến đâu và truy vấn liệt kê phải fan-out bao nhiêu? |
| F | Bất kỳ ID nào + secondary index thời gian | GSI/index phụ có trở thành cổ chai khi ghi tập trung không? |

Với một sản phẩm NoSQL không hỗ trợ cả hash và range, **chỉ so các phương án mà sản phẩm thật sự hỗ trợ**. Đừng quy kết chênh lệch kết quả cho UUID nếu đồng thời thay đổi số node, replica, cấu hình index hoặc loại máy.

### 9.2. Tạo workload đại diện

Một kịch bản mẫu:

~~~yaml
dataset:
  records: 5000000
  avgDocumentBytes: 1800
  largeDocumentPercent: 5
workload:
  sustainedWritesPerSecond: 12000
  pointReadsPerSecond: 24000
  listByTenantPerSecond: 2500
  peakMultiplier: 3
  hotTenantShareOfWritesPercent: 40
  hotKeyShareOfReadsPercent: 15
tests:
  - uniform_key_distribution
  - time_ordered_insert
  - hot_tenant
  - one_hot_key
  - new_node_or_rebalance
  - index_build_during_writes
~~~

Tất cả số liệu trên chỉ là **dữ liệu minh họa cho mẫu thử**. Khi đo thật, cần lấy phân bố khóa, kích thước tài liệu và đỉnh tải từ log/tracing của ứng dụng, hoặc ghi rõ những giả định chưa có số liệu.

Các chỉ số đáng theo dõi:

- Offered/achieved throughput, p50/p95/**p99** API và latency của câu truy vấn cơ sở dữ liệu.
- Phần trăm lỗi, timeout, throttling, retry và queue depth.
- Tải **từng partition/node**, thay vì chỉ CPU trung bình của cụm.
- Kích thước index, disk I/O, page split/cache hit nếu engine cung cấp metric, compaction nếu có.
- Độ trễ truy vấn theo thời gian và số partition bị đọc trên mỗi request.
- Hiệu quả của secondary index, số lần scan, fan-out và merge.
- Khi cần: chi phí tạo ID tại client, tỷ lệ va chạm, ổn định trước clock rollback và hành vi retry.

Để kết luận, nên chạy nhiều vòng trong môi trường cố định, xác định thời gian warm-up, giới hạn của load generator và ghi lại version database/driver. Đặt **ngưỡng p99, throughput và chi phí** trước khi xem kết quả; nếu thử nghiệm quá tải, cần ghi cả lượng request đã bị từ chối, không chỉ latency các request thành công.

### 9.3. Tình huống kết quả minh họa

Giả sử một thử nghiệm có cùng 20.000 lần ghi/giây với kết quả sau:

| Cấu hình | p99 ghi | Partition có tải cao nhất | Ý nghĩa |
| --- | ---: | --- | --- |
| UUIDv4 + hash ID | 65 ms | 1,2 lần trung vị | Phân bố tương đối đều trong kịch bản mẫu |
| UUIDv7 + hash ID | 62 ms | 1,3 lần trung vị | ID có timestamp không làm hash route mất cân bằng rõ rệt |
| UUIDv7 + range ID | 240 ms | 5,8 lần trung vị | Có dấu hiệu dồn ghi vào vùng khóa mới |
| UUIDv7 + hash ID + index theo ngày | 180 ms | Index ngày bị throttling | Nút nghẽn nằm ở index phụ, không nhất thiết ở bảng chính |

Các số này **hoàn toàn minh họa, không phải benchmark của một sản phẩm cụ thể**. Bài học từ ví dụ là: cần xem **đường đi đầy đủ của ghi**, đặc biệt index phụ và partition key, để tìm nguyên nhân. Đổi ID có thể không giải quyết được vấn đề nếu đường ghi vẫn dồn vào một khóa `day` hoặc một tenant nóng.

## 10. Cách chọn trong các tình huống thường gặp

### 10.1. Sản phẩm đọc nhiều theo ID và muốn sinh ID phân tán

Chọn UUIDv4 thường đơn giản khi không cần sắp theo thời gian bằng ID. UUIDv7 phù hợp nếu muốn ID mới có tính gần theo thời gian cho log, truy vết hoặc một số truy vấn. Nếu khóa được **hash toàn ID**, cả hai đều có thể phân phối tốt cho nhiều ID khác nhau.

**Đừng suy luận:** UUIDv4 luôn giúp phân tải hơn UUIDv7. Trong hash partition, quyết định phụ thuộc hash và phân bố workload; thử nghiệm mới xác nhận được.

### 10.2. Ghi log hoặc sự kiện append nhiều, thường đọc theo khoảng thời gian

UUIDv7, ULID hoặc các sort key có timestamp có thể hữu ích. Tuy nhiên, **partition theo ngày/giờ** dễ nóng ở thời điểm hiện tại. Có thể cần bucket theo nguồn, tenant hoặc giá trị hash, rồi merge khi đọc khoảng thời gian. Nếu yêu cầu thứ tự sự kiện chính xác, nên dùng offset/sequence của luồng có thẩm quyền.

### 10.3. Hệ thống đa tenant với tenant có tải rất khác nhau

Định danh sự kiện có thể dùng UUIDv7 nhưng **partition key theo `tenantId` mới là yếu tố gây lệch**. Với tenant rất nóng, cần cân nhắc bucket, giới hạn tải, cách truy vấn nhiều bucket và khả năng quản lý tenant lớn riêng. Không kỳ vọng chỉ đổi từ UUIDv4 sang UUIDv7 sẽ xử lý vấn đề.

### 10.4. Cần cấp phát ID khi offline

UUIDv4 hoặc UUIDv7 có thể được tạo tại client mà không gọi server, nhưng khi tái kết nối cần xử lý **trùng thao tác, thời gian client sai, quyền sửa dữ liệu và thứ tự đồng bộ**. Dùng UUIDv7 cho thời gian gợi ý; nếu cần sắp theo thời gian server xác nhận thì lưu thêm timestamp server.

### 10.5. Muốn ID ngắn và gần tăng

Snowflake-like 64-bit ID có thể giảm kích thước so với UUID và cho thứ tự gần theo thời gian, đổi lại vận hành generator phức tạp hơn (worker ID, đồng hồ, sequence, restart). Việc tiết kiệm 8 byte trên giá trị ID chỉ thực sự quan trọng khi đã đo chi phí tổng thể của index, lưu trữ và luồng API.

## 11. Những nhầm lẫn cần tránh

1. **“UUIDv7 luôn nhanh hơn UUIDv4.”** Chưa chắc: random-vs-ordered ảnh hưởng khác nhau với B-tree, LSM, hash partition và range partition.
2. **“UUIDv7 có thứ tự nên tự động cân bằng shard.”** Sai: phân tải do partition key và cơ chế định tuyến quyết định.
3. **“UUIDv4 ngẫu nhiên thì không có hot key.”** Sai: một giá trị ID bị truy cập lặp vẫn là hot key.
4. **“ID tăng có nghĩa mọi bản ghi nằm đúng thứ tự nghiệp vụ.”** Sai: thời điểm sinh ID khác lúc nhận, commit và có hiệu lực; đồng hồ có thể lệch.
5. **“Đã hash khóa chính thì không thể có hotspot.”** Sai: index phụ, khóa tenant/ngày, khóa nóng và giới hạn partition vẫn có thể tạo nghẽn.
6. **“Lưu UUID thành chuỗi hay nhị phân đều như nhau.”** Không hẳn: kích thước khóa, serialization và thứ tự so sánh có thể ảnh hưởng index/truy vấn.
7. **“UUID không trùng nên không cần constraint hoặc idempotency.”** Sai: bảo toàn duy nhất khi ghi và xử lý retry là các yêu cầu khác với xác suất va chạm.
8. **“Có thể dùng timestamp trong UUIDv7 làm audit time tuyệt đối.”** Không an toàn: timestamp do generator cung cấp, có thể sinh ở client và bị ảnh hưởng bởi đồng hồ.
9. **“ID khó đoán đủ để bảo vệ tài nguyên.”** Sai: phải xác thực và phân quyền từng request.

## 12. Bài tập tình huống

Một ứng dụng nhận 30.000 sự kiện mỗi giây từ 5.000 thiết bị. Mỗi sự kiện được gắn ID và thời gian. Giao diện cần xem 100 sự kiện mới nhất của một thiết bị; quy trình xử lý cần đối soát chính xác sự kiện đã được server chấp nhận. Một số thiết bị gửi dữ liệu với tốc độ cao gấp 100 lần số còn lại.

Hãy cân nhắc ba thiết kế:

**Thiết kế A**

~~~text
eventId   = UUIDv4
PK        = deviceId
SK        = createdAt#eventId
~~~

**Thiết kế B**

~~~text
eventId   = UUIDv7
PK        = hash(eventId)
SK        = eventId
~~~

**Thiết kế C**

~~~text
eventId   = UUIDv7
PK        = deviceId#bucket
SK        = serverAcceptedAt#eventId
bucket    = stableHash(eventId) % 8
~~~

Các câu hỏi cần trả lời:

1. Với A, một thiết bị nóng có thể gây nghẽn partition bằng cách nào dù ID là UUIDv4?
2. Với B, ghi có thể được phân bố tốt hơn, nhưng muốn đọc 100 sự kiện mới nhất của một thiết bị cần index/read model nào?
3. Với C, làm thế nào để đọc và merge 8 bucket cho cùng thiết bị, giữ phân trang ổn định và xử lý tăng số bucket theo thời gian?
4. Nếu eventId được sinh trên thiết bị mất đồng bộ đồng hồ 10 phút, có thể coi thứ tự UUIDv7 là thứ tự server nhận/commit không?
5. Cần thử nghiệm những chỉ số nào để chọn phương án: p99 ghi, hot partition, số nhánh phải đọc, chi phí index, mất/trùng sự kiện và thời gian phục hồi?

Một cách tiếp cận hợp lý là giữ **ID ổn định, sinh phân tán** để nhận diện sự kiện; dùng **khóa lưu trữ và chỉ mục** phục vụ truy vấn theo thiết bị/thời gian; đồng thời có **serverAcceptedAt hoặc sequence/offset có thẩm quyền** khi cần thứ tự xử lý chính xác. Chỉ thêm bucketing hoặc read model phụ sau khi đo được vấn đề và hiểu chi phí của việc đọc/di trú.

Ý chính của bài học: **UUIDv4, UUIDv7 và các ID có thứ tự giải quyết bài toán định danh với những đặc tính khác nhau; phân phối tải là kết quả của cả ID, khóa phân vùng, cách lưu chỉ mục và hành vi truy cập.** Thiết kế tốt không bắt đầu bằng chọn “UUID nào nhanh nhất”, mà bắt đầu từ truy vấn, mức độ nóng của khóa, thứ tự cần bảo đảm và phép đo trên chính hệ thống NoSQL sẽ dùng.
