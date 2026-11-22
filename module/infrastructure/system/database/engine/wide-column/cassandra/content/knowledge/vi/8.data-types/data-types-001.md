# Chọn kiểu dữ liệu Apache Cassandra theo miền giá trị, độ chính xác và mẫu truy cập

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**. Dữ liệu được phân phối theo **partition key**, sắp xếp trong phân vùng theo **clustering columns**, lưu thành các cell và được đồng bộ giữa các replica theo cấu hình replication, consistency. Vì vậy, kiểu CQL không chỉ quyết định giá trị nào được lưu: nó còn ảnh hưởng đến kích thước bản ghi, cách so sánh khóa, thao tác cập nhật, khả năng truy vấn và chi phí lưu trữ khi hệ thống chạy lâu dài.

Bài học thuộc module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**. Trọng tâm là lựa chọn kiểu dữ liệu cho bảng được thiết kế theo truy vấn, làm rõ độ chính xác của số và thời gian, và nối lựa chọn đó với CQL và Java. Các khái niệm compaction, repair và mức nhất quán vẫn quan trọng cho vận hành Cassandra nhưng không thay thế được việc chọn miền giá trị và mô hình khóa đúng từ đầu.

## 1. Ba câu hỏi phải trả lời trước khi chọn kiểu

1. **Miền giá trị là gì?** Giá trị là định danh, số đo, tiền, thời điểm, địa chỉ IP, tập nhãn hay một thực thể con? Có số 0 ở đầu, ký tự Unicode, số âm, giá trị rất lớn hoặc cấu trúc lồng nhau không?
2. **Cần chính xác đến đâu?** Có chấp nhận sai số dấu phẩy động không? Dữ liệu thời gian cần độ phân giải ngày, mili giây hay nano giây? Có cần lưu múi giờ ban đầu hoặc phân biệt thời điểm xảy ra sự kiện với lúc ghi vào Cassandra không?
3. **Sẽ đọc và ghi theo mẫu nào?** Truy vấn theo định danh, theo khoảng thời gian trong một phân vùng, tra cứu phần tử của tập hợp hay cập nhật từng thuộc tính? Dữ liệu có tăng mãi không? Có retry thao tác ghi không?

Sau đó mới chọn kiểu. Chẳng hạn, chuỗi "001234" là mã khách hàng thì cần **text**; nếu là một đại lượng sẽ cộng trừ thì mới xem xét kiểu số. Một điểm số cảm biến có thể dùng **double**, nhưng số tiền thanh toán cần **decimal** hoặc số đơn vị nhỏ nhất bằng **bigint**.

## 2. Bản đồ lựa chọn nhanh các kiểu CQL

| Miền dữ liệu / nhu cầu | Kiểu thường phù hợp | Cần kiểm tra trước khi chốt |
|---|---|---|
| Văn bản Unicode, tên tiếng Việt, mã nghiệp vụ | **text** (hoặc **varchar**, tên tương đương) | Giữ nguyên số 0 đầu mã; độ dài và chuẩn hóa chuỗi |
| Chuỗi chỉ gồm ký tự ASCII | **ascii** | Không dùng cho nội dung có dấu hoặc Unicode |
| Đúng/sai | **boolean** | Phân biệt giá trị chưa biết với false trong nghiệp vụ |
| Số nguyên nhỏ | **tinyint**, **smallint**, **int** | Biên giá trị và nguy cơ tăng trưởng vượt miền |
| Bộ đếm/số nguyên lớn, số tiền ở đơn vị nhỏ nhất | **bigint** | Cần quy ước đơn vị, kiểm tra tràn 64 bit |
| Số nguyên tùy ý lớn | **varint** | Chi phí biểu diễn/tính toán, khả năng ánh xạ sang Java |
| Số thập phân phải chính xác | **decimal** | Quy ước scale, làm tròn và định dạng hiển thị |
| Số đo chấp nhận sai số | **float**, **double** | Sai số IEEE 754 và độ chính xác thực sự cần |
| Định danh kỹ thuật | **uuid** | Sinh một lần và giữ ổn định khi retry |
| Định danh gắn thứ tự thời gian | **timeuuid** | Có phù hợp với UUID version 1 và cách tạo ID không |
| Thời điểm tuyệt đối | **timestamp** | Lưu mili giây từ epoch; quản lý múi giờ ở ứng dụng |
| Chỉ có ngày / giờ trong ngày | **date** / **time** | Không dùng như thời điểm đầy đủ |
| Khoảng thời gian lịch | **duration** | Tháng/ngày/nano giây không phải số giây cố định |
| Địa chỉ IPv4/IPv6 | **inet** | Không thay cho host name hoặc dải CIDR |
| Dữ liệu nhị phân nhỏ | **blob** | Dữ liệu lớn nên cân nhắc lưu ngoài Cassandra |
| Danh sách có thứ tự / tập không trùng / ánh xạ khóa–giá trị | **list**, **set**, **map** | Chỉ dùng cho tập hợp nhỏ, có giới hạn tăng trưởng |
| Nhóm thuộc tính có cấu trúc | **UDT**, **tuple** | Cần cập nhật từng field hay toàn bộ giá trị? |
| Embedding có số chiều cố định, Cassandra 5.0+ | **vector<float, n>** | Phiên bản cluster, truy vấn vector và sai số float |

Đây là các lựa chọn khởi đầu. Không có quy tắc “kiểu càng nhỏ càng tốt”: miền dữ liệu có thể mở rộng, mã phải tương thích với Java driver, và giới hạn truy vấn thường quan trọng hơn vài byte tiết kiệm trên một giá trị.

## 3. Miền giá trị và tính chính xác

### 3.1. Định danh khác với số lượng

Một mã đơn hàng "00007342" không có ý nghĩa cộng trừ. Nếu lưu bằng **int**, các số 0 đầu sẽ mất; nếu mã về sau có ký tự, schema sẽ phải đổi. Lưu mã nghiệp vụ bằng **text** và kiểm soát định dạng ở tầng ứng dụng.

Dùng **uuid** khi muốn định danh nhị phân 128 bit, có thể sinh độc lập giữa các node. Dùng **timeuuid** khi cần một UUID version 1 mang thông tin thời gian và thường được sử dụng làm clustering key cho dòng sự kiện. **timeuuid** không tương đương với **timestamp**: timestamp biểu diễn một thời điểm, còn timeuuid là một định danh chứa thông tin thời gian. Nếu yêu cầu giữ thứ tự sự kiện theo thời gian do thiết bị gốc cung cấp, cần lưu thêm **timestamp** nghiệp vụ; một timeuuid sinh lúc nhận dữ liệu không thay thế được thời điểm đã xảy ra.

Số điện thoại, mã bưu chính, SKU và số thẻ có ký tự đặc biệt đều là **text**, bất kể bề ngoài chỉ gồm chữ số. Với tiếng Việt, chọn **text**, không chọn **ascii**.

### 3.2. Số nguyên: chọn theo biên tương lai

Các kiểu số nguyên có dấu phổ biến:

| Kiểu | Kích thước / miền giá trị |
|---|---|
| **tinyint** | 8 bit: −128 đến 127 |
| **smallint** | 16 bit: −32.768 đến 32.767 |
| **int** | 32 bit: −2.147.483.648 đến 2.147.483.647 |
| **bigint** | 64 bit: −2^63 đến 2^63 − 1 |
| **varint** | Số nguyên độ dài biến thiên, có thể lớn hơn 64 bit |

Ví dụ: **smallint** có thể đủ cho điểm trong phạm vi −100 đến 100; **bigint** hợp lý hơn cho tổng số byte đã truyền hoặc số tiền tính bằng đồng/cent khi giá trị dài hạn có thể lớn. Không chọn **tinyint** chỉ vì hiện tại mới có 30 trạng thái nếu danh mục có khả năng mở rộng tới vài trăm giá trị.

**varint** dành cho miền số nguyên thật sự không vừa 64 bit, không phải lựa chọn mặc định cho mọi số nguyên. Java thường đọc/ghi varint bằng **BigInteger**; bigint bằng **long**. Đổi kiểu cột hoặc khóa sau khi đã đưa vào vận hành có thể đòi hỏi tạo bảng mới và di chuyển dữ liệu.

### 3.3. Tiền và số đo: decimal khác float/double

**float** (32 bit) và **double** (64 bit) dùng dấu phẩy động nhị phân IEEE 754. Chúng phù hợp cho nhiệt độ, xác suất, đại lượng khoa học hoặc embedding khi sai số xấp xỉ được chấp nhận. **double** thường chính xác hơn float, nhưng cả hai đều không biểu diễn chính xác mọi phân số thập phân.

~~~java
double observed = 0.1 + 0.2;
// observed thường là 0.30000000000000004

BigDecimal exact = new BigDecimal("0.1")
    .add(new BigDecimal("0.2"));
// exact là 0.3
~~~

Với tiền, có hai chiến lược phổ biến:

- **decimal** lưu giá trị thập phân chính xác, ví dụ 19.90; Java sử dụng **BigDecimal**. Hãy quy định scale, rounding mode và quy tắc làm tròn tại biên nghiệp vụ.
- **bigint** lưu số **đơn vị nhỏ nhất** như 1.990 cent cho 19.90 USD. Phải lưu/biết loại tiền và đơn vị vì các tiền tệ có số chữ số thập phân khác nhau; kiểm tra tràn 64 bit khi tính tổng.

~~~cql
CREATE TABLE invoice_amounts_by_id (
    invoice_id uuid PRIMARY KEY,
    currency text,
    amount_exact decimal,
    amount_minor bigint
);

INSERT INTO invoice_amounts_by_id
    (invoice_id, currency, amount_exact, amount_minor)
VALUES
    (11111111-1111-4111-8111-111111111111, 'USD', 19.90, 1990);
~~~

Hai cột ở ví dụ nhằm so sánh chiến lược; trong thiết kế thực tế thường chọn **một biểu diễn tiền làm nguồn chân lý**, tránh ghi song song hai giá trị có thể lệch. Không dùng **double** cho phép tính tiền, giá sản phẩm hay khoản nợ cần đối soát chính xác.

### 3.4. Thời gian: phân biệt date, time, timestamp, timeuuid và duration

- **date**: một ngày theo lịch, không kèm giờ hay múi giờ; hợp cho ngày sinh, ngày chốt kỳ, **bucket_day**.
- **time**: giờ trong ngày với độ phân giải nano giây; không có ngày và múi giờ; hợp cho khung giờ làm việc.
- **timestamp**: một thời điểm tuyệt đối, biểu diễn ở độ phân giải mili giây kể từ Unix epoch. Cassandra không giữ tên múi giờ ban đầu; khi nhập/hiển thị, ứng dụng phải áp dụng quy ước múi giờ.
- **timeuuid**: định danh có thành phần thời gian (UUID version 1), có thể làm clustering key theo thứ tự thời gian.
- **duration**: một khoảng gồm tháng, ngày và nano giây. Một tháng không phải luôn là 30 ngày; kiểu này không thay thế cho phép đo thời lượng cố định bằng mili giây hay nano giây.

~~~cql
CREATE TABLE events_by_user (
    user_id uuid,
    event_id timeuuid,
    occurred_at timestamp,
    action text,
    PRIMARY KEY ((user_id), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);

INSERT INTO events_by_user (user_id, event_id, occurred_at, action)
VALUES (
    22222222-2222-4222-8222-222222222222,
    now(),
    '2026-11-21T01:15:00Z',
    'login'
);
~~~

Hàm **now()** sinh timeuuid mới tại thời điểm thực thi. Nếu ghi lại cùng sự kiện bằng một lệnh sinh **now()** mới, khóa có thể khác và tạo dòng trùng. Với ingest cần idempotent, sinh ID sự kiện một lần trước khi retry rồi tái sử dụng ID đó. Khi thời gian có thể đến trễ hoặc lệch đồng hồ, cần xác định rõ thứ tự hiển thị dựa trên **occurred_at** của nguồn hay thời gian nhận được.

**Lưu ý quan trọng:** giá trị CQL **timestamp** của cột nghiệp vụ không phải *write timestamp* dùng để Cassandra giải quyết xung đột last-write-wins. Giá trị ghi bằng **USING TIMESTAMP** và kết quả **WRITETIME()** liên quan metadata ghi, có đơn vị micro giây; còn CQL **timestamp** lưu thời điểm đến mili giây. Nhầm hai khái niệm này có thể gây sai logic cập nhật.

## 4. Kiểu dữ liệu gắn với mô hình truy vấn

Cassandra tối ưu cho truy vấn có partition key xác định và, khi cần, các điều kiện trên clustering columns theo thứ tự phù hợp. Chọn kiểu tốt không cứu được một bảng có partition key không khớp truy vấn.

Giả sử hệ thống thanh toán cần: “Lấy 50 khoản thanh toán mới nhất của một khách hàng trong ngày, có thể lọc theo khoảng thời gian”. Bảng phù hợp:

~~~cql
CREATE TABLE payments_by_customer_day (
    customer_id uuid,
    bucket_day date,
    occurred_at timestamp,
    payment_id uuid,
    amount_minor bigint,
    currency text,
    state text,
    PRIMARY KEY ((customer_id, bucket_day), occurred_at, payment_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, payment_id ASC);
~~~

Ý nghĩa từng lựa chọn:

- **customer_id uuid** làm phần đầu của partition key vì truy vấn xác định khách hàng; **bucket_day date** giới hạn sự tăng trưởng của phân vùng theo ngày. Định nghĩa phân vùng gồm hai cột, không phải hai phân vùng riêng.
- **occurred_at timestamp** là clustering column, hỗ trợ lấy bản ghi theo khoảng và trả kết quả từ mới đến cũ trong một ngày. **payment_id uuid** phân biệt các giao dịch có cùng mili giây.
- **amount_minor bigint** cho số nguyên chính xác ở đơn vị nhỏ nhất; **currency text** mang quy ước đơn vị; **state text** thích hợp khi tập trạng thái là mã nghiệp vụ và có thể mở rộng.
- Khóa chính xác định sự duy nhất của dòng trong một phân vùng; muốn chống ghi trùng phải sử dụng lại cùng bộ khóa khi retry.

~~~cql
SELECT occurred_at, payment_id, amount_minor, currency, state
FROM payments_by_customer_day
WHERE customer_id = 22222222-2222-4222-8222-222222222222
  AND bucket_day = '2026-11-21'
  AND occurred_at >= '2026-11-21T01:00:00Z'
  AND occurred_at <  '2026-11-21T02:00:00Z'
LIMIT 50;
~~~

Truy vấn cung cấp **đầy đủ partition key** và giới hạn **clustering column**. Nếu nghiệp vụ yêu cầu “tìm mọi thanh toán theo state trên toàn bộ khách hàng”, cần thiết kế thêm đường truy cập phù hợp (chẳng hạn một bảng theo truy vấn khác, hoặc chỉ mục được cân nhắc theo phiên bản và tải thực tế); đổi **state** từ text sang một kiểu khác không làm truy vấn toàn cluster trở nên hiệu quả.

**Kích thước và độ rộng phân vùng:** chia bucket theo ngày chỉ là ví dụ. Khách hàng có hàng triệu sự kiện/ngày có thể cần bucket theo giờ hoặc thêm shard, còn lưu lượng thấp có thể dùng bucket tuần/tháng. Chọn theo số dòng và dung lượng mỗi phân vùng, throughput, retention và mẫu truy vấn. Kiểu **date** của bucket không tự giới hạn kích thước phân vùng.

**Khóa và sắp xếp:** partition key được băm để xác định vị trí phân phối; clustering columns quyết định thứ tự trong phân vùng. Chọn **uuid** hay **text** cho ID phải theo miền giá trị và giao thức tích hợp, không dựa vào suy đoán rằng thứ tự từ điển của chuỗi sẽ làm phân vùng được sắp xếp theo thời gian. Không dùng **float/double** làm khóa cho số liệu cần so sánh bằng tuyệt đối, vì sai số có thể khiến hai giá trị tưởng như giống nhau trở thành khóa khác nhau.

## 5. Collections, UDT, tuple: linh hoạt nhưng phải có giới hạn

### 5.1. List, set, map có các tính chất khác nhau

| Kiểu | Dùng khi | Rủi ro nếu dùng sai |
|---|---|---|
| **list<T>** | Vài phần tử có thứ tự và có thể trùng | Cập nhật theo vị trí / thay đổi nhiều, danh sách tăng vô hạn |
| **set<T>** | Vài nhãn không trùng, không cần thứ tự chèn | Không phù hợp lưu lịch sử sự kiện hoặc đếm số lần xuất hiện |
| **map<K,V>** | Tập thuộc tính nhỏ, khóa biết trước hoặc có giới hạn | Không phù hợp làm bảng con có hàng triệu khóa |

~~~cql
CREATE TYPE customer_address (
    line1 text,
    city text,
    postal_code text
);

CREATE TABLE profiles_by_id (
    user_id uuid PRIMARY KEY,
    display_name text,
    labels set<text>,
    preferences map<text, text>,
    shipping_address frozen<customer_address>
);
~~~

**set** không lưu thứ tự chèn của nhãn; **map** không tương đương một bảng chỉ mục để lọc nhanh theo mọi giá trị. CQL hỗ trợ thay đổi phần tử/entry của những collection không frozen, nhưng các thao tác thêm/xóa liên tục và giá trị phình to có thể làm tăng cell, tombstone, compaction và chi phí đọc. **list** đặc biệt cần thận trọng với thao tác theo chỉ số và cập nhật có tính phụ thuộc trạng thái.

Nếu yêu cầu “tất cả hành động của khách hàng trong 90 ngày”, hãy lưu **mỗi hành động thành một row có clustering key**, không đưa toàn bộ hành động vào một **list** trong duy nhất một row. Nếu cần tìm khách hàng theo nhãn, cần thiết kế đường truy cập/tra cứu tương ứng, không mặc nhiên truy vấn **set CONTAINS** trên toàn bộ dữ liệu.

### 5.2. UDT, tuple và frozen

**UDT (user-defined type)** đặt tên cho cấu trúc có ý nghĩa nghiệp vụ, chẳng hạn địa chỉ gồm line1/city/postal_code. **tuple** phù hợp một nhóm giá trị vị trí cố định khi mỗi vị trí có kiểu rõ ràng, nhưng khó đọc và tiến hóa schema hơn UDT có tên field.

**frozen<customer_address>** đóng gói toàn bộ UDT thành một giá trị; cập nhật phải thay thế cả giá trị, không cập nhật từng field bên trong. Dùng frozen khi cấu trúc con được ghi/đọc nguyên khối, khá nhỏ và ít thay đổi; UDT không frozen có thể phù hợp hơn nếu cần cập nhật riêng field (tùy phiên bản CQL và quy tắc lồng nhau).

**Nguyên tắc:** collection/UDT giúp biểu diễn một *giá trị có cấu trúc* nằm trong row, không thay cho quan hệ một-nhiều tăng không giới hạn. Cần cân nhắc số lượng phần tử, tốc độ cập nhật, cách xóa và tổng kích thước cell/partition sau compaction.

### 5.3. Counter, blob, inet, vector: các trường hợp riêng

**counter** phục vụ các thao tác tăng/giảm kiểu bộ đếm phân tán, với quy tắc bảng riêng: cột không phải khóa chính trong bảng counter phải là counter, không trộn với cột thường; không dùng TTL như dữ liệu thông thường. Tăng counter rồi retry khi timeout có thể cộng thêm lần nữa; không dùng counter như một sổ cái chính xác cần bảo đảm mỗi sự kiện được tính đúng một lần.

**blob** phù hợp payload nhị phân nhỏ. Với ảnh/video/file lớn, thường hiệu quả hơn khi lưu đối tượng ở hệ lưu trữ chuyên dụng và để Cassandra giữ URI/metadata. **inet** nhận IPv4 hoặc IPv6; muốn lưu hostname, dải IP/CIDR hay diễn giải mạng thì cần kiểu/mô hình khác.

Từ Cassandra **5.0**, **vector<float, n>** hỗ trợ vector có số chiều cố định cho các bài toán như embedding và tìm kiếm gần đúng khi hạ tầng/chỉ mục phù hợp. Vì dựa trên float, nó không dành cho dữ liệu cần độ chính xác thập phân tuyệt đối. Khi triển khai, phải kiểm tra cluster và Java driver có hỗ trợ kiểu này; không tự thêm vector vào schema của cluster phiên bản cũ.

## 6. Ánh xạ CQL sang Java và thao tác an toàn

Khi kết nối bằng Apache Cassandra Java Driver 4.x, một số ánh xạ thông dụng:

| CQL | Java thường dùng |
|---|---|
| **text**, **ascii** | **String** |
| **boolean** | **boolean/Boolean** |
| **int**, **bigint** | **int/Integer**, **long/Long** |
| **varint**, **decimal** | **BigInteger**, **BigDecimal** |
| **float**, **double** | **float/Float**, **double/Double** |
| **uuid**, **timeuuid** | **UUID** |
| **date**, **time**, **timestamp** | **LocalDate**, **LocalTime**, **Instant** |
| **inet**, **blob** | **InetAddress**, **ByteBuffer** |
| **list**, **set**, **map** | **List**, **Set**, **Map** với kiểu phần tử tương thích |
| **UDT**, **tuple** | **UdtValue**, **TupleValue** (hoặc codec được cấu hình) |

Ví dụ dùng bảng **payments_by_customer_day** đã tạo ở trên. Giả sử biến **session** là một **CqlSession** đã cấu hình contact points, local datacenter và credentials phù hợp:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;

// session đã được khởi tạo; ID phải được lưu và dùng lại khi retry.
UUID customerId = UUID.fromString("22222222-2222-4222-8222-222222222222");
UUID paymentId = UUID.fromString("33333333-3333-4333-8333-333333333333");
Instant occurredAt = Instant.parse("2026-11-21T01:15:00Z");
LocalDate bucketDay = occurredAt.atZone(ZoneOffset.UTC).toLocalDate();
long amountMinor = 1990L; // 19.90 USD = 1990 cent

PreparedStatement ps = session.prepare(
    "INSERT INTO payments_by_customer_day "
  + "(customer_id, bucket_day, occurred_at, payment_id, "
  + " amount_minor, currency, state) "
  + "VALUES (?, ?, ?, ?, ?, ?, ?)");

BoundStatement statement = ps.boundStatementBuilder()
    .setUuid(0, customerId)
    .setLocalDate(1, bucketDay)
    .setInstant(2, occurredAt)
    .setUuid(3, paymentId)
    .setLong(4, amountMinor)
    .setString(5, "USD")
    .setString(6, "CAPTURED")
    .build();

session.execute(statement);
~~~

**Prepared statement** giúp bind đúng kiểu và tránh nối giá trị đầu vào thành chuỗi CQL. Biến **bucketDay** được tính theo UTC để mọi dịch vụ phân bucket nhất quán; nếu nghiệp vụ muốn “ngày theo múi giờ cửa hàng” thì phải định nghĩa rõ và áp dụng cùng một quy tắc khi ghi lẫn truy vấn.

Với **decimal**, Java dùng **BigDecimal** được tạo từ chuỗi hoặc nguồn có độ chính xác tương đương; tránh khởi tạo từ một **double** đã làm tròn nhị phân. Với **timestamp**, dùng **Instant** để biểu diễn thời điểm; không đưa **LocalDateTime** không có offset vào hệ thống phân tán mà chưa quy định timezone.

Một thao tác ghi Cassandra có thể trả về timeout dù một số replica đã nhận được dữ liệu. Cùng khóa và cùng giá trị được ghi lại có tính chất idempotent phù hợp hơn là sinh ID mới ở mỗi lần thử. Tuy nhiên, cập nhật cùng một cell với timestamp ghi khác nhau vẫn tuân theo quy tắc last-write-wins; **tính chính xác nghiệp vụ không tự động được bảo đảm chỉ bằng kiểu dữ liệu hay consistency level**.

## 7. Bốn tình huống thiết kế cần phân biệt

**Tình huống A — Giá niêm yết và tổng thanh toán.** Cần đối soát chính xác đến phần nhỏ nhất của tiền. Dùng **decimal** nếu làm việc với số thập phân theo quy tắc scale, hoặc **bigint** với đơn vị nhỏ nhất và currency rõ ràng. Không chọn **double**, dù phép cộng thử nghiệm ban đầu có vẻ đúng.

**Tình huống B — Telemetry 50.000 bản ghi/giây.** Giá trị cảm biến có thể dùng **double**, thời điểm đo **timestamp**, định danh thiết bị **uuid/text** theo domain. Đọc theo thiết bị và thời gian cần partition bucket và clustering column; không dùng một **list<double>** không giới hạn cho mọi mẫu đo.

**Tình huống C — Hồ sơ người dùng có vài nhãn.** Dùng **set<text>** nếu nhãn nhỏ, có giới hạn và không cần thứ tự. Nếu cần tìm mọi người dùng có nhãn "vip" ở quy mô lớn, thiết kế bảng truy vấn theo nhãn hoặc chiến lược index đã đo đạc, vì kiểu set tự nó không tạo truy vấn toàn cục hiệu quả.

**Tình huống D — Số lượt xem.** **counter** có thể phù hợp một chỉ số tăng giảm gần thời gian thực và chấp nhận đặc tính retry của counter. Nếu số lượt xem dùng để tính tiền, cần ghi nhận sự kiện có ID ổn định, xử lý trùng và tổng hợp theo quy trình kiểm soát; counter đơn lẻ không chứng minh mỗi sự kiện được tính một lần.

## 8. Checklist khi review schema Cassandra

- Giá trị đang biểu diễn **định danh** hay **số lượng**? Chuỗi mã có cần Unicode hoặc giữ số 0 ở đầu?
- Các cột số có miền giá trị đủ cho tương lai và có quy tắc xử lý tràn không? Số tiền đang dùng **decimal** hoặc **minor units**, không dùng float/double?
- Các mốc thời gian đã phân biệt **ngày**, **giờ trong ngày**, **thời điểm** và **thời lượng**? Múi giờ và độ phân giải đã được quy định?
- Query quan trọng có cung cấp **partition key** đầy đủ và lọc theo **clustering columns** hợp lệ? Sắp xếp và khoảng thời gian có theo đúng thứ tự khóa?
- Phân vùng và collection có giới hạn tăng trưởng theo dữ liệu thực tế? Có nguy cơ tạo quá nhiều tombstone khi cập nhật/xóa?
- Các thao tác retry có tái sử dụng ID/khóa? Có thao tác **counter**, append list hoặc sinh **now()** mới làm kết quả không idempotent?
- Kiểu dữ liệu có ánh xạ Java driver ổn định, tương thích phiên bản Cassandra đang chạy và cho phép chuyển đổi schema có kế hoạch?

**Điểm cần nhớ:** trong Cassandra, loại dữ liệu, thiết kế khóa và truy vấn là ba quyết định liên quan chặt chẽ. Miền giá trị đúng giúp dữ liệu không bị mất nghĩa; độ chính xác đúng giúp phép tính không sai; mẫu truy cập đúng giúp đọc/ghi tập trung vào những phân vùng có thể dự đoán được.
