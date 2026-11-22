# Ước lượng kích thước bản ghi, nhóm dữ liệu và phân vùng

## 1. Vì sao thiết kế theo truy vấn phải tính cả kích thước?

Trong hệ NoSQL, một câu hỏi quan trọng không chỉ là **“lưu dữ liệu bằng document, key–value, cột rộng hay graph?”** mà còn là **“mỗi lần đọc phải tìm đến bao nhiêu dữ liệu, và mỗi lần ghi làm phần dữ liệu nào lớn thêm?”**.

Giả sử ứng dụng lưu dữ liệu nhiệt độ từ cảm biến. Đặt toàn bộ lịch sử của một thiết bị vào một document có thể giúp đọc một số màn hình dễ dàng, nhưng document sẽ tăng liên tục. Ngược lại, tách mỗi số đo thành một bản ghi nhỏ giúp ghi độc lập nhưng có thể làm tăng số khóa, index entry và request cần xử lý. Nếu chọn phân vùng chỉ theo `tenantId`, một tenant lớn có thể dồn phần lớn lưu lượng vào một vùng dữ liệu nóng. Nếu chia theo giờ, truy vấn nhiều ngày phải đọc nhiều nhóm rồi hợp nhất.

Để quyết định có cơ sở, cần **ước lượng từ workload và kích thước dữ liệu**, sau đó kiểm chứng bằng phép đo trên sản phẩm thực tế.

Bài học này làm rõ ba cấp độ:

1. **Bản ghi (record/item/document/row):** một đơn vị dữ liệu mà ứng dụng lưu và truy cập.
2. **Nhóm dữ liệu (aggregate/collection of related records):** dữ liệu được gom theo một nhu cầu đọc/ghi, ví dụ đơn hàng và các dòng hàng, hoặc chuỗi số đo trong một khoảng thời gian.
3. **Phân vùng (partition/shard/key range):** phạm vi dữ liệu được hệ quản trị sử dụng để định tuyến và phân phối lưu trữ hay xử lý; cách xác định phụ thuộc sản phẩm.

Điểm cần tránh là dùng một từ “partition” để nói đồng thời về **bucket logic trong tên khóa**, **một partition của Cassandra**, **partition key trong DynamoDB** và **shard vật lý của MongoDB**. Các khái niệm này liên quan nhưng **không có ngữ nghĩa hoàn toàn giống nhau**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Ước lượng dung lượng của một bản ghi từ encoding, metadata và các cấu trúc phụ.
- Tính số bản ghi và dung lượng tăng trưởng từ tốc độ ghi, thời gian lưu và số lượng thực thể.
- Xác định khi nào nên gom hoặc tách các phần dữ liệu theo access pattern.
- Chọn kích thước nhóm và khoảng bucket thời gian dựa vào tốc độ dữ liệu, giới hạn đọc/ghi và khả năng phân phối tải.
- Nhận diện partition quá lớn, hot partition, nhiều partition quá nhỏ và truy vấn phải fan-out.
- Phân biệt dung lượng logic với dung lượng vật lý sau replication, indexing, compression và quá trình vận hành.
- Lập giả thuyết thiết kế, đo số liệu thật và điều chỉnh theo phân bố tải.

## 2. Bắt đầu bằng mẫu truy cập, không bằng công thức

Giả sử hệ thống IoT có các thiết bị gửi sự kiện đo nhiệt độ. Bốn câu hỏi nghiệp vụ:

| Mẫu truy vấn | Dữ kiện đã biết | Kết quả mong muốn | Hàm ý thiết kế |
|---|---|---|---|
| Q1: số đo gần nhất | `tenantId`, `deviceId` | Một sự kiện gần nhất | Đường truy cập nhanh theo ID thiết bị |
| Q2: 100 số đo gần nhất trong ngày | `tenantId`, `deviceId`, ngày | Một nhóm sự kiện theo thời gian | Gom dữ liệu để đọc tuần tự trong một phạm vi phù hợp |
| Q3: lịch sử của thiết bị trong 30 ngày | `tenantId`, `deviceId`, khoảng thời gian | Nhiều nhóm sự kiện, phân trang | Bucket theo thời gian, cơ chế đọc qua nhiều bucket |
| Q4: trung bình nhiệt độ toàn hệ thống theo tháng | Tháng, tập thiết bị | Kết quả tổng hợp | Có thể cần dữ liệu aggregate hoặc hệ phân tích thay vì quét toàn bộ bản ghi phục vụ Q2 |

Nếu chỉ nhìn Q1, đặt một key cho trạng thái hiện tại là hợp lý:

```text
latest-reading:t17:d42 -> { timestamp, temperature }
```

Nếu chỉ nhìn Q2, có thể ưu tiên một cấu trúc sắp theo thời gian trong partition/bucket. Q3 đòi hỏi đọc nhiều khoảng thời gian; Q4 đòi hỏi tính toán trên phạm vi rất rộng. **Không có một cấu trúc vật lý duy nhất luôn tối ưu cho cả bốn câu hỏi.**

Một bản thiết kế phải ghi rõ thêm:

- **Write rate:** mỗi thiết bị phát bao nhiêu sự kiện/giây, mức tăng đột biến (burst) bao nhiêu?
- **Độ lớn value:** kích thước trung bình, p95/p99, tối đa và tốc độ tăng theo thời gian?
- **Cardinality:** có bao nhiêu thiết bị, tenant và các nhóm có độ lớn chênh lệch thế nào?
- **Retention:** lưu mấy giờ, ngày, tháng hoặc năm? Dữ liệu có thể bị xóa sớm hay bắt buộc giữ lại?
- **Read rate:** mỗi mẫu truy vấn được gọi bao nhiêu lần và có cần sắp thứ tự/phân trang không?
- **Consistency:** sau ghi, lần đọc tiếp theo cần thấy ngay hay chấp nhận trễ?
- **Mục tiêu hệ thống:** độ trễ, thông lượng, chi phí, RPO/RTO và ngân sách vận hành.

Các công thức dưới đây chỉ có ý nghĩa khi đầu vào phản ánh **kiểu tải thực tế**.

## 3. Kích thước bản ghi: payload không phải toàn bộ chi phí

### 3.1. Ba cách đo kích thước khác nhau

Cần phân biệt:

| Khái niệm | Bao gồm | Dùng để |
|---|---|---|
| **Payload phía ứng dụng** | Số byte của JSON, Protobuf, BSON hoặc định dạng value trước khi gửi | Ước lượng băng thông và lượng dữ liệu ứng dụng tạo ra |
| **Kích thước logic trong database** | Dữ liệu và cách biểu diễn khóa, thuộc tính, metadata theo định dạng của sản phẩm | Ước lượng đơn vị dữ liệu/giới hạn item, document, row |
| **Dung lượng vật lý** | Dữ liệu thực lưu sau compression, replication, index, WAL/commit log, tombstone và các cấu trúc vận hành | Dự báo dung lượng đĩa, chi phí hạ tầng và capacity |

Ví dụ, một JSON dài 200 byte **không đồng nghĩa** với bản ghi chiếm chính xác 200 byte trên đĩa. Sản phẩm có thể thêm metadata, lưu index, nén dữ liệu, giữ nhiều phiên bản hoặc nhân bản dữ liệu. Ngược lại, compression có thể giảm số byte vật lý của dữ liệu có tính lặp.

### 3.2. Đếm byte UTF-8 thay vì đếm ký tự

Chuỗi tiếng Việt như `"Nhiệt độ phòng"` chứa ký tự UTF-8 có thể chiếm nhiều byte hơn số ký tự hiển thị. Emoji, escaping JSON và cách mã hóa số cũng làm thay đổi kích thước.

Với một record mẫu:

```json
{
  "tenantId": "t17",
  "deviceId": "d42",
  "observedAt": "2026-11-14T08:01:00Z",
  "temperatureC": 28.3,
  "batteryPct": 93,
  "status": "OK"
}
```

Nếu lưu dưới dạng JSON, cả **tên trường**, dấu câu và định dạng giá trị đều chiếm byte. Nếu mỗi record lặp lại `"temperatureC"` hàng tỷ lần, chi phí tên trường có thể đáng kể. Một định dạng nhị phân/schema-aware có thể giảm chi phí này, nhưng còn phải xem encoding và đường truy cập của sản phẩm.

Ví dụ Java với Jackson để đo **payload JSON thực tế**:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

public class PayloadSizeExample {
    public static void main(String[] args) throws Exception {
        Map<String, Object> reading = new LinkedHashMap<>();
        reading.put("tenantId", "t17");
        reading.put("deviceId", "d42");
        reading.put("observedAt", "2026-11-14T08:01:00Z");
        reading.put("temperatureC", 28.3);
        reading.put("batteryPct", 93);
        reading.put("status", "OK");

        ObjectMapper mapper = new ObjectMapper();
        byte[] payload = mapper.writeValueAsBytes(reading);
        System.out.println("JSON UTF-8 bytes = " + payload.length);

        // Chỉ là payload JSON; chưa gồm key/index/replica/metadata của DB.
        String json = mapper.writeValueAsString(reading);
        System.out.println(
            json.getBytes(StandardCharsets.UTF_8).length
        );
    }
}
```

Đoạn code giả định dự án có dependency Jackson. Đối với BSON hoặc định dạng lưu thực tế khác, hãy dùng serializer hay API đo kích thước tương ứng; số byte JSON chỉ là một trong các đầu vào.

### 3.3. Công thức ước lượng ban đầu

Ở mức thiết kế, có thể tách:

\[
S_{\text{record, logical}}
\approx
S_{\text{key}}
+
S_{\text{value}}
+
S_{\text{field/metadata overhead}}
\]

Trong đó:

- \(S_{\text{key}}\): khóa của bản ghi hoặc các thành phần partition/clustering key được lưu;
- \(S_{\text{value}}\): phần nội dung mã hóa;
- \(S_{\text{field/metadata overhead}}\): metadata, độ dài chuỗi, type marker, timestamp/TTL/version hoặc overhead khác tùy hệ.

**Không dùng công thức này như một cam kết về internal storage format**: một sản phẩm có thể lưu key trong nhiều cấu trúc, shared dictionary, index hoặc format nén theo block. Muốn biết dung lượng thật phải đo dữ liệu đã ghi.

Đối với hoạch định sơ bộ, ta có thể lấy một giả định rõ ràng, ví dụ:

> “Một sự kiện ước tính khoảng 320 byte logic, tính cả key và phần overhead giả định. Con số này cần được thay bằng số đo từ dữ liệu thật.”

Chính sự minh bạch về giả định mới giúp người khác đánh giá công thức.

### 3.4. Dùng phân bố thay cho một record “trung bình”

Hai tập dữ liệu cùng kích thước trung bình 320 byte có thể rất khác nhau:

- Tập A: hầu hết record 300–350 byte.
- Tập B: phần lớn 100 byte nhưng một số record chứa payload JSON hoặc danh sách dài 50 KB.

Tập B dễ phát sinh vấn đề giới hạn kích thước document, request, đột biến băng thông và thời gian deserialize. Vì vậy nên thu thập:

\[
S_{p50},\quad S_{p95},\quad S_{p99},\quad S_{\max}
\]

Cần tính riêng các nhóm dữ liệu có phân bố khác nhau: tenant lớn, thiết bị nhiều sensor, record chứa ảnh/tệp đính kèm hoặc sự kiện lỗi có stack trace dài. **Đừng lấy trung bình toàn hệ thống để đại diện cho partition nóng nhất.**

## 4. Từ kích thước bản ghi đến tăng trưởng toàn bộ dữ liệu

### 4.1. Công thức cơ bản

Giả sử:

- \(D\): số thiết bị hoạt động.
- \(r\): số record mỗi giây của một thiết bị.
- \(s\): số byte logic trung bình mỗi record.
- \(T\): số giây lưu dữ liệu.

Số record:

\[
N = D \times r \times T
\]

Dung lượng logic xấp xỉ:

\[
L = N \times s
\]

Tốc độ dữ liệu mới sinh ra mỗi giây:

\[
W_{\text{bytes/s}} = D \times r \times s
\]

Các công thức này giả định mỗi thiết bị phát cùng tốc độ và kích thước trung bình ổn định. Trong thực tế phải thêm phân bố tải, retry, duplicate, backfill, dữ liệu được xóa, metadata thay đổi và các bản sao phục vụ truy vấn.

### 4.2. Ví dụ đầy đủ với 100 thiết bị

Giả sử hệ thống có:

| Tham số | Giá trị minh họa |
|---|---:|
| Số thiết bị | 100 |
| Tốc độ ghi mỗi thiết bị | 12 record/giây |
| Kích thước logic ước tính mỗi record | 320 byte |
| Thời gian giữ dữ liệu nóng | 30 ngày |
| Replication factor để thử hoạch định | 3 bản sao |

Số record mỗi ngày của **một thiết bị**:

\[
12 \times 86{,}400 = 1{,}036{,}800\ \text{record/ngày}
\]

Dung lượng logic mỗi ngày của **một thiết bị**:

\[
1{,}036{,}800 \times 320
=
331{,}776{,}000\ \text{byte}
\]

Tức khoảng **331,8 MB** (hệ thập phân), tương đương khoảng **316,4 MiB**.

Với **100 thiết bị**:

\[
100 \times 331{,}776{,}000
=
33{,}177{,}600{,}000\ \text{byte/ngày}
\]

Tức khoảng **33,18 GB dữ liệu logic/ngày**.

Với **30 ngày** (giả sử có thể xóa dữ liệu cũ đúng hạn và tốc độ ổn định):

\[
33{,}177{,}600{,}000 \times 30
=
995{,}328{,}000{,}000\ \text{byte}
\]

Xấp xỉ **995,3 GB logic** hay **927 GiB**. Nếu tạm tính **ba bản sao đầy đủ**, phần dữ liệu cơ sở trước các chi phí bổ sung là khoảng:

\[
995{,}3\ \text{GB} \times 3 \approx 2{,}99\ \text{TB}
\]

Đây **không phải yêu cầu dung lượng đĩa chính xác**: replication, compression, index, ghi log, compaction, backup, tombstone, phần dữ liệu dự phòng và chi phí của dịch vụ quản lý đều có thể làm kết quả thay đổi.

### 4.3. Dung lượng là một đại lượng theo thời gian

Sự tăng trưởng hiếm khi chỉ là \(L = \text{ghi mới/ngày} \times \text{ngày giữ}\):

- Khi giữ dữ liệu 30 ngày bằng TTL, việc dọn vật lý có thể diễn ra **muộn hơn thời điểm hết hạn logic**.
- Khi có backfill từ dữ liệu cũ, lượng ghi của một ngày có thể gấp nhiều lần bình thường.
- Khi dùng index phụ hoặc materialized view, một sự kiện được lưu ở nhiều nơi.
- Khi thay schema làm record từ 320 byte lên 500 byte, tăng trưởng nhanh hơn.
- Khi nạp/lọc/chuyển đổi theo batch, cần vùng dung lượng tạm.
- Khi có backup và snapshot, dung lượng lưu trữ được giữ theo chính sách khác TTL của dữ liệu chính.

Vì vậy nên lập ba kịch bản: **bình thường**, **đỉnh tải**, và **tăng trưởng dài hạn**.

## 5. Nhóm dữ liệu: đơn vị đọc và đơn vị cập nhật

“Nhóm dữ liệu” ở đây là cách **đặt các dữ liệu liên quan gần nhau theo một access pattern**, không nhất thiết là partition vật lý của database.

### 5.1. Gom để đọc một lần

Trong hệ document, giả sử một đơn hàng thường được đọc cùng danh sách item:

```json
{
  "orderId": "O-1007",
  "customerId": "C-42",
  "status": "PAID",
  "items": [
    { "sku": "BK-01", "quantity": 2, "unitPrice": 120000 },
    { "sku": "PN-09", "quantity": 1, "unitPrice": 15000 }
  ]
}
```

Nếu hầu hết request đều đọc **đơn hàng kèm item**, việc nhúng `items` trong document có thể giảm số lần truy xuất. Tuy nhiên, cần hỏi:

- Số item trung bình và tối đa mỗi đơn là bao nhiêu?
- Các item thường được đọc cùng đơn hay cập nhật độc lập?
- Có cập nhật đồng thời từng item không?
- Khi số item tăng, document có đụng giới hạn kích thước sản phẩm không?
- Có phải sửa/ghi lại toàn bộ document trong một số thao tác không?

**Gom dữ liệu giúp truy vấn này không có nghĩa mọi trường hợp đều nên nhúng.**

### 5.2. Khi một nhóm tăng không giới hạn

Giả sử một người dùng có danh sách mọi lần đăng nhập, mỗi lần đăng nhập khoảng 250 byte. Sau 10 triệu lần:

\[
10{,}000{,}000 \times 250
= 2{,}500{,}000{,}000\ \text{byte}
\]

Khoảng **2,5 GB**, chưa tính metadata, trường bao và overhead biểu diễn danh sách. Đưa toàn bộ lịch sử đó vào một document/key duy nhất thường gây vấn đề về giới hạn, cập nhật, băng thông và cạnh tranh.

Giải pháp có thể là:

- Mỗi event là một bản ghi riêng.
- Nhóm event thành nhiều bucket theo tháng/ngày/giờ.
- Giữ trạng thái hiện tại trong một bản ghi nhỏ, lịch sử trong các bản ghi khác.
- Lưu tổng hợp theo cửa sổ thời gian, thay vì đọc lại toàn bộ lịch sử cho mỗi dashboard.

### 5.3. Quyết định gom hoặc tách theo thao tác

| Dấu hiệu | Hướng cân nhắc | Đánh đổi |
|---|---|---|
| Hai phần luôn đọc cùng nhau, kích thước nhỏ và ổn định | Gom/nhúng | Giảm read request; tăng kích thước cập nhật |
| Một tập con cập nhật độc lập với tần suất cao | Tách thành bản ghi khác | Giảm cạnh tranh; có thể thêm round trip |
| Mảng/danh sách tăng không giới hạn | Tách hoặc bucket | Phải phân trang và hợp nhất dữ liệu |
| Nhu cầu truy vấn theo nhiều thuộc tính khác nhau | Index hoặc cấu trúc phụ | Chi phí index và đồng bộ dữ liệu |
| Trạng thái hiện tại đọc nhiều, lịch sử ít đọc | Tách latest và history | Phải đồng bộ latest với sự kiện mới |
| Cần transaction trên nhiều phần | Xem phạm vi atomicity của sản phẩm | Gom có thể giúp ở một số hệ; không phải bảo đảm chung |

### 5.4. Tác động của cập nhật đồng thời

Một document lớn gộp nhiều phần dữ liệu có thể trở thành điểm tranh chấp nếu nhiều request cùng sửa. Tách dữ liệu giúp cập nhật độc lập, nhưng có thể mất atomicity vốn đạt được khi mọi thay đổi nằm trong cùng một đơn vị ghi.

Ngược lại, tạo nhiều bản ghi đại diện một aggregate nghiệp vụ có thể đòi transaction nhiều item hoặc cơ chế đồng bộ. **Kích thước và ranh giới cập nhật phải được xét cùng tính nhất quán**, không chỉ theo dung lượng.

## 6. Phân vùng và bucket: hai quyết định khác nhau

### 6.1. Bucket là cách nhóm logic tại tầng dữ liệu

Ví dụ đặt các sự kiện của mỗi thiết bị vào bucket một giờ:

```text
tenant=t17
device=d42
bucket=2026-11-14T08

    08:59:59 -> event 1
    08:59:58 -> event 2
    ...
    08:00:00 -> event N
```

Bucket có thể trở thành một thành phần của khóa hoặc một thuộc tính được index. Nó giúp tạo phạm vi dữ liệu dự đoán được và có thể phục vụ retention theo khoảng thời gian.

Nhưng một “bucket = giờ” trong ứng dụng **không bảo đảm** được lưu thành một đơn vị vật lý duy nhất. Sản phẩm có thể dùng hash, range, split/merge hoặc phân phối dữ liệu theo chính sách riêng.

### 6.2. Partition là khái niệm do sản phẩm định nghĩa

| Sản phẩm/họ | Điều cần hiểu | Không nên suy diễn |
|---|---|---|
| **Apache Cassandra** | Partition key chọn partition logic, clustering columns sắp hàng trong partition | Partition key chỉ là ID bình thường hoặc mọi truy vấn đều lọc được mọi cột |
| **Amazon DynamoDB** | Partition key/sort key định nghĩa cấu trúc khóa và cách truy cập item; dịch vụ quản lý phân vùng vật lý | Một giá trị partition key luôn tương ứng một node vật lý hoặc một giới hạn dung lượng cố định cho mọi trường hợp |
| **MongoDB sharding** | Shard key và chunks/ranges định hướng phân phối document | Tên field nhóm theo thời gian tự chia dữ liệu tốt nếu chọn shard key chưa phù hợp |
| **Bigtable/HBase** | Row key và key range ảnh hưởng truy cập, phân bố tablet/region | Các hàng gần nhau theo nghiệp vụ tự động cân tải |
| **Redis Cluster** | Key được ánh xạ vào hash slot và phân phối giữa các node | Prefix giống nhau khiến key luôn nằm cùng node, hoặc mọi lệnh multi-key hoạt động trên nhiều slot |
| **Một document DB không sharded** | Có thể tổ chức document và index mà không phân phối ngang | Đã có “collection” thì dữ liệu tự phân bố đều trên nhiều node |

Các cơ chế partition thực tế, giới hạn và cách tự động chia nhỏ thay đổi theo phiên bản/dịch vụ. Bài này dùng “partition” theo nghĩa khái niệm khi không chỉ rõ sản phẩm.

## 7. Tính kích thước partition từ tần suất ghi và khoảng thời gian

### 7.1. Công thức một partition theo thiết bị và bucket thời gian

Nếu một partition logic chứa dữ liệu của **một thiết bị** trong một bucket dài \(\Delta t\) giây:

\[
N_{\text{partition}} \approx r_{\text{device}} \times \Delta t
\]

\[
S_{\text{partition}} \approx
N_{\text{partition}} \times S_{\text{record}}
\]

Đây là kích thước **logic sơ bộ**. Trong hệ Cassandra, còn cần tính kích thước partition key, clustering, cell metadata, tombstone và cách lưu thực; trong hệ khác công thức có thể không ánh xạ trực tiếp đến một partition vật lý.

### 7.2. Tiếp tục ví dụ thiết bị ghi 12 event/giây

Với một thiết bị, 320 byte/record:

| Bucket | Số record một bucket | Dung lượng logic ước tính |
|---|---:|---:|
| 1 phút | 720 | 230.400 byte ≈ 0,23 MB |
| 15 phút | 10.800 | 3.456.000 byte ≈ 3,46 MB |
| 1 giờ | 43.200 | 13.824.000 byte ≈ 13,82 MB |
| 6 giờ | 259.200 | 82.944.000 byte ≈ 82,94 MB |
| 1 ngày | 1.036.800 | 331.776.000 byte ≈ 331,78 MB |

Nếu dùng bucket ngày, một nhóm chứa hơn một triệu event. Nếu dùng bucket một giờ, nhóm chứa 43.200 event. **Không thể chỉ từ bảng trên kết luận bucket nào là “đúng”**: còn phải tính thiết bị cao điểm, kích thước value p99, read pattern, khả năng xử lý partition lớn và giới hạn của sản phẩm.

### 7.3. Bucket nhỏ giải quyết vấn đề gì, tạo vấn đề gì?

Bucket nhỏ có thể:

- Giảm số record và dung lượng của từng nhóm.
- Giới hạn phạm vi đọc khi người dùng truy vấn một khoảng ngắn.
- Giúp quản lý retention, cleanup hoặc compaction theo từng khoảng trong một số thiết kế.
- Giảm nguy cơ mọi sự kiện lịch sử chồng vào một partition khổng lồ.

Nhưng cũng có thể:

- Làm tăng số partition/key/index entry.
- Khi đọc 24 giờ phải đi qua nhiều bucket.
- Tăng số request và số bước merge kết quả.
- Tăng metadata và chi phí quản lý những bucket rất ít dữ liệu.
- Làm truy vấn “100 event mới nhất” phải kiểm tra nhiều bucket nếu thời điểm hiện tại ít event.

**Bucket càng nhỏ không có nghĩa càng tối ưu.** Phải tìm điểm cân bằng giữa kích thước nhóm và chi phí đọc qua nhiều nhóm.

### 7.4. Số bucket/partition cũng cần ước lượng

Với 100 thiết bị, bucket một giờ và retention 30 ngày:

\[
100 \times 24 \times 30 = 72{,}000\ \text{bucket logic}
\]

Nếu bucket 15 phút:

\[
100 \times 96 \times 30 = 288{,}000\ \text{bucket logic}
\]

Số lượng này chưa phải số shard vật lý. Với nhiều sản phẩm, hàng trăm nghìn partition logic có thể là việc bình thường nếu mỗi partition hợp lý. Tuy nhiên, metadata và chi phí truy cập nhiều partition vẫn phải đo.

### 7.5. Không dùng mức trung bình cho thiết bị nóng nhất

Giả sử 99 thiết bị ghi 12 event/giây nhưng một thiết bị đặc biệt ghi **240 event/giây**. Với bucket một giờ, thiết bị đó có:

\[
240 \times 3{,}600 = 864{,}000\ \text{record/bucket}
\]

\[
864{,}000 \times 320
= 276{,}480{,}000\ \text{byte}
\]

Tức khoảng **276,48 MB logic** trong một giờ. Cấu hình bucket có vẻ ổn với thiết bị bình thường có thể không phù hợp với thiết bị này.

Do đó cần lấy **phân bố tốc độ ghi theo key/tenant**, đặc biệt p95/p99 và top-N thiết bị nóng nhất.

## 8. Ví dụ schema phục vụ truy vấn bằng Cassandra

Với mẫu Q2 “100 số đo mới nhất của một thiết bị trong một giờ”, có thể xây bảng Cassandra:

```sql
-- CQL minh họa; xem tài liệu Cassandra và workload thực.
CREATE TABLE readings_by_device_hour (
    tenant_id      text,
    device_id      text,
    bucket_hour    text,
    event_time     timestamp,
    event_id       uuid,
    temperature_c  decimal,
    battery_pct    int,
    PRIMARY KEY (
        (tenant_id, device_id, bucket_hour),
        event_time,
        event_id
    )
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
```

Ở đây:

- `(tenant_id, device_id, bucket_hour)` là **partition key ghép**.
- `event_time` và `event_id` là **clustering columns**.
- Mỗi tổ hợp tenant–device–giờ định danh một partition logic.
- Thứ tự clustering giúp truy cập dữ liệu theo thời gian trong partition.
- `event_id` phân biệt các sự kiện có cùng timestamp theo cách ứng dụng cấp ID.

Truy vấn trong một giờ:

```sql
SELECT event_time, event_id, temperature_c, battery_pct
FROM readings_by_device_hour
WHERE tenant_id = 't17'
  AND device_id = 'd42'
  AND bucket_hour = '2026-11-14T08'
LIMIT 100;
```

Ví dụ dùng kiểu `text` cho bucket để dễ minh họa; hệ thực tế cần nhất quán về UTC, định dạng và cách chuyển time bucket.

### 8.1. Khi yêu cầu đọc băng qua ranh giới bucket

Nếu muốn “100 sự kiện mới nhất” vào lúc 09:00:03, bucket 09 có thể mới chứa vài chục sự kiện. Client có thể cần:

1. Đọc bucket 09.
2. Nếu chưa đủ 100, đọc bucket 08.
3. Nếu vẫn chưa đủ, tiếp tục bucket trước.
4. Ghép theo `event_time` và `event_id`, đảm bảo giới hạn 100 và loại trùng nếu cần.

Nếu 100 event là một cửa sổ rất nhỏ, việc phải đọc 2 bucket gần ranh giới có thể chấp nhận được. Nếu thiết bị chỉ phát một event/ngày, bucket giờ trở thành lựa chọn bất tiện. **Phân bố tần suất ghi và access pattern quyết định chiều dài bucket.**

### 8.2. Không tự dùng `ALLOW FILTERING` để bù thiết kế key

Nếu ứng dụng đột ngột hỏi “tất cả event có `temperature_c > 40` trên mọi tenant trong tháng”, bảng trên không được thiết kế cho truy vấn đó. Việc cố quét mọi partition có thể tốn tài nguyên.

Có thể cần:

- Bảng/luồng dữ liệu riêng cho cảnh báo.
- Chỉ mục phù hợp với giới hạn thực tế của phiên bản sản phẩm.
- Pipeline tính aggregate hoặc hệ phân tích.
- Thay đổi access pattern nếu mục tiêu nghiệp vụ cho phép.

Một thiết kế “đọc theo thiết bị và giờ” không tự động phục vụ truy vấn phân tích đa chiều.

## 9. Khi partition key phân bố không đều

### 9.1. Hot partition gây vấn đề gì?

Giả sử hệ multi-tenant dùng partition key chỉ là `tenantId`. Một tenant lớn chiếm 90% sự kiện, trong khi hàng nghìn tenant nhỏ chỉ chiếm 10%. Khi tất cả ghi vào partition logic của tenant lớn, có thể xảy ra:

- Một vùng dữ liệu nhận phần lớn thao tác đọc/ghi.
- Tăng latency và tỷ lệ throttling khi giới hạn theo key/partition bị chạm.
- Khó khai thác hết khả năng phân tán của cluster.
- Tăng công việc compaction/repair hoặc xử lý dữ liệu ở một nhóm quá lớn.
- Thao tác quét lịch sử tenant lớn trở nên nặng.

**Tăng số node không tự sửa được một khóa nóng nếu cách phân phối không chia được công việc của khóa ấy.**

### 9.2. Chọn khóa ghép để phân tán

Ví dụ thay vì:

```text
partitionKey = tenantId
```

thiết kế:

```text
partitionKey = (tenantId, deviceId, bucketHour)
```

có thể phân nhỏ dữ liệu thành nhiều partition. Tuy nhiên, truy vấn “lấy mọi sự kiện của tenant trong giờ” giờ phải tìm nhiều device/bucket. Đó là **read fan-out**.

Lựa chọn khóa ghép nên xuất phát từ câu hỏi **ứng dụng luôn biết những định danh nào lúc truy vấn**.

### 9.3. Hash/salt để chia điểm nóng

Nếu một key đặc biệt vẫn quá nóng, có thể thêm một **shard suffix**:

```text
counter:campaign42:0
counter:campaign42:1
counter:campaign42:2
counter:campaign42:3
```

Mỗi write chọn một shard theo quy tắc xác định/ngẫu nhiên có kiểm soát. Khi đọc tổng, ứng dụng phải đọc tất cả shard và cộng kết quả.

Cách làm này đổi:

- **Write:** phân tải, giảm cạnh tranh trên một key.
- **Read:** phải truy cập nhiều key và tổng hợp.
- **Consistency:** cần xác định tổng chính xác đến thời điểm nào, dữ liệu trùng và retry ra sao.

Chỉ nên dùng khi đã chứng minh có hot key/hot partition và hiểu yêu cầu đọc. Thêm salt vô tội vạ có thể làm truy vấn theo khóa hoặc duyệt range trở nên tốn kém.

### 9.4. Hash và range có đặc tính khác nhau

- **Hash partitioning** thường hỗ trợ phân bố theo hàm hash, nhưng các key liền nhau theo tên có thể không nằm cùng vị trí.
- **Range partitioning** có thể phục vụ truy vấn theo khoảng khóa thuận tiện hơn, nhưng nếu key tăng đơn điệu có thể dồn write vào vùng đuôi.
- **Composite key / sort key** giúp tổ chức đường đọc trong phạm vi một khóa phân vùng, nhưng ngữ nghĩa cụ thể phụ thuộc từng database.

Không dùng tên các chiến lược như lời bảo đảm hiệu năng. Cần đo tốc độ mỗi partition vật lý hoặc logical group theo API quan sát của sản phẩm.

## 10. Chi phí của đọc qua nhiều nhóm

Một truy vấn phải đọc \(k\) bucket có chi phí không chỉ là tổng byte dữ liệu cuối cùng. Có thể ước lượng:

\[
C_{\text{read}} \approx
k \times C_{\text{request}}
+
C_{\text{data transfer}}
+
C_{\text{merge/sort}}
\]

Trong đó \(C_{\text{request}}\) là thành phần overhead trung bình của mỗi request. Đây là mô hình để suy nghĩ, không phải công thức latency chính xác, vì các request có thể chạy song song, tranh tài nguyên và chịu ảnh hưởng từ mạng/cache.

### 10.1. Ví dụ đọc lịch sử 30 ngày

Nếu một thiết bị dùng bucket một giờ, truy vấn 30 ngày có thể liên quan đến tối đa:

\[
30 \times 24 = 720\ \text{bucket}
\]

Với bucket một ngày: 30 bucket. Số bucket ít hơn không đảm bảo tổng thời gian nhỏ hơn; mỗi bucket ngày có thể chứa hơn một triệu record và rất lớn. Cần xem:

- Query có lấy **tất cả record** hay chỉ một vài điểm?
- Có phân trang và giới hạn bản ghi không?
- Có cần thứ tự toàn cục giữa các bucket không?
- Nếu chỉ muốn chart, có nên đọc dữ liệu đã tổng hợp theo phút/giờ?
- Có thể giải quyết trên hệ phân tích thay vì đọc 720 partition từ hệ giao dịch không?

### 10.2. Cân nhắc dữ liệu tổng hợp

Nếu dashboard chỉ cần nhiệt độ trung bình mỗi 5 phút, không nhất thiết phải đọc mọi event 12 lần/giây.

Có thể duy trì:

```text
raw-reading:t17:d42:<hour>  -> sự kiện gốc
avg-5min:t17:d42:<day>     -> giá trị tổng hợp mỗi 5 phút
latest-reading:t17:d42     -> số đo gần nhất
```

Đây là ví dụ **nhiều đường truy cập phục vụ nhiều mẫu truy vấn**, đổi thêm chi phí lưu và cập nhật lấy việc đọc hiệu quả hơn. Muốn bảo đảm đúng đắn phải xác định cách cập nhật aggregate, xử lý event đến muộn, retry, dữ liệu trùng và rebuild.

## 11. Dung lượng index, bản sao và chi phí ghi bổ sung

### 11.1. Một record có thể được ghi vào nhiều cấu trúc

Giả sử cần ba đường truy cập:

1. Theo `eventId`.
2. Theo `deviceId` và thời gian.
3. Theo `status` và ngày.

Nếu lưu mỗi event một lần ở bảng nguồn và thêm các index/bản sao phục vụ truy vấn, lượng dữ liệu vật lý và chi phí ghi sẽ tăng. Một mô hình hoạch định:

\[
S_{\text{stored}} \approx
\left(S_{\text{primary}}
+ S_{\text{secondary}}
+ S_{\text{metadata}}\right)
\times F_{\text{replication}}
\times F_{\text{storage}}
\]

Trong đó:

- \(S_{\text{primary}}\): dữ liệu chính;
- \(S_{\text{secondary}}\): index, materialized view hoặc cấu trúc phụ;
- \(S_{\text{metadata}}\): overhead tương ứng;
- \(F_{\text{replication}}\): hệ số nhân bản áp dụng cho phần dữ liệu được nhân bản;
- \(F_{\text{storage}}\): hệ số điều chỉnh thô cho nén/compaction và chi phí vận hành.

Đây **chỉ là mô hình ước lượng**, không phải một đẳng thức tổng quát. Một số cấu trúc index được nhân bản theo cách khác, dữ liệu được nén khác nhau và managed service có cách tính bill riêng.

### 11.2. Write amplification

Một yêu cầu ghi logic có thể dẫn đến nhiều công việc vật lý:

- Viết vào write-ahead log/commit log.
- Cập nhật memtable hoặc buffer.
- Ghi SSTable hoặc page trên đĩa.
- Duy trì index và materialized view.
- Nén, gộp hoặc compact dữ liệu trong background.
- Gửi dữ liệu cho replica.
- Ghi tombstone khi xóa.

Không nên tính dung lượng và thông lượng chỉ từ “mỗi event = một write” rồi bỏ qua các cấu trúc bên dưới. Với hệ LSM, compaction có thể tạo I/O lớn ngay cả khi tốc độ dữ liệu logic không đổi.

### 11.3. Capacity phải có khoảng dự phòng

Nếu dung lượng cơ sở ước tính là 3 TB cho dữ liệu replicated, việc cấp đúng 3 TB vật lý có thể không đủ cho hoạt động bình thường. Cần dự phòng cho:

- Nén có thể kém hơn dự đoán.
- Node mất khả năng phục vụ và cần rebalancing.
- Compaction và dữ liệu tạm thời.
- Snapshot/backup.
- Dữ liệu tăng đột biến.
- Quota/hạn mức không cho sử dụng hết tài nguyên theo cách tuyến tính.

Mức dự phòng cụ thể phải dựa vào kiến trúc, SLA và khuyến nghị sản phẩm. Không có một phần trăm “đúng cho mọi NoSQL database”.

## 12. TTL, retention và việc xóa không tức thời

Khi dữ liệu chỉ cần 30 ngày, ứng dụng có thể sử dụng TTL hoặc chính sách retention. Tuy nhiên:

- **Hết hạn logic** không phải luôn là thời điểm bytes được giải phóng ngay.
- Một số hệ đánh dấu xóa bằng **tombstone**, dọn vật lý sau các chu kỳ compaction/garbage collection.
- Dữ liệu có thể vẫn tồn tại trong backup/snapshot theo chính sách riêng.
- TTL trên từng record khác việc drop cả bảng/partition/bucket cũ.
- Một record được cập nhật có thể giữ, mất hoặc đặt lại TTL tùy thao tác và sản phẩm.

### 12.1. Dữ liệu theo bucket giúp hoạch định retention

Nếu một bucket chứa sự kiện của ngày đã hết hạn, một số thiết kế cho phép xóa dữ liệu theo nhóm hoặc theo time partition hiệu quả hơn là phát lệnh xóa từng event. Nhưng cơ chế thật tùy database:

- Có sản phẩm hỗ trợ table partition pruning và drop partition.
- Có sản phẩm dùng TTL từng item.
- Có hệ cột rộng cần cân nhắc tombstone và compaction.
- Có hệ tự động quản lý lifecycle theo service policy.

Không được suy ra rằng **đặt `bucketDay` vào key sẽ làm dữ liệu tự được xóa vật lý theo ngày**. Đó mới là cấu trúc logic; phải thiết kế retention và vận hành tương ứng.

### 12.2. Backfill có thể phá dự đoán TTL

Nếu nạp lại sự kiện 90 ngày trước vào bảng có TTL “30 ngày kể từ lúc ghi”, sự kiện cũ có thể sống thêm 30 ngày, khác mong muốn “chỉ giữ sự kiện có `eventTime` trong 30 ngày gần nhất”. Một số hệ hỗ trợ TTL tùy record hoặc expiration timestamp; cần đối chiếu đặc tả.

Ứng dụng phải phân biệt **event time** (lúc sự kiện xảy ra), **ingest time** (lúc database nhận) và **expiration time** (mốc hết hiệu lực). Chính sách retention nên nêu rõ dùng mốc nào.

## 13. Một worksheet hoạch định có thể dùng lại

Trước khi viết schema, lập bảng như sau:

| Biến | Giá trị minh họa | Nguồn hoặc cách đo |
|---|---:|---|
| Số thiết bị đang hoạt động | 100 | Số liệu nghiệp vụ |
| Ghi trung bình mỗi thiết bị | 12/s | Telemetry |
| Ghi p99 mỗi thiết bị | Cần đo | Metrics theo device |
| Kích thước record trung bình | 320 B | Giả định ban đầu; đo serializer/DB |
| Kích thước p99 | Cần đo | Sample dữ liệu |
| Retention | 30 ngày | Yêu cầu nghiệp vụ |
| Đọc “latest” | Cần đo QPS | API metrics |
| Đọc 100 sự kiện gần nhất | Cần đo QPS | API metrics |
| Lịch sử cần truy xuất | 30 ngày | Yêu cầu người dùng |
| Latency p99 mục tiêu | Theo SLA | Yêu cầu hệ thống |
| Replication | Giả định 3 | Topology của sản phẩm |
| Bucket dự kiến | 1 giờ | Tính toán/benchmark |
| Index/bản sao phụ | Theo access pattern | Thiết kế dữ liệu |
| Dự phòng dung lượng | Theo engine/SLA | Capacity planning |

Có thể lưu giả định ở dạng YAML:

```yaml
workload:
  devices: 100
  events_per_device_per_second_avg: 12
  events_per_device_per_second_peak: null
  record_bytes_estimated: 320
  record_bytes_p99: null
  retention_days: 30

access_patterns:
  - name: latest_reading
    key_inputs: [tenant_id, device_id]
    result_size: 1
  - name: last_100_in_hour
    key_inputs: [tenant_id, device_id, bucket_hour]
    result_size: 100
  - name: historical_chart
    key_inputs: [tenant_id, device_id, time_range]
    result_size: aggregated

design_hypothesis:
  bucket_duration_hours: 1
  partition_key: [tenant_id, device_id, bucket_hour]
  clustering: [event_time_desc, event_id]
  replica_count_assumed: 3

validation_needed:
  - record_size_distribution
  - hottest_device_write_rate
  - partition_size_actual
  - read_latency_p99
  - read_fanout_across_buckets
  - disk_and_index_overhead
  - compaction_and_retention_behavior
```

Các trường `null` thể hiện **chưa có số đo**, không nên điền số tùy tiện để làm bảng “đầy đủ”.

## 14. Quy trình thử nghiệm và hiệu chỉnh

### Bước 1 — Lấy dữ liệu đại diện

Chọn mẫu có:

- Record thông thường và record lớn.
- Thiết bị/tenant có tốc độ cao và thấp.
- Payload có các loại chuỗi, số, tùy chọn và cấu trúc lồng nhau.
- Event đến trễ, trùng, lỗi và backfill nếu có.
- Các trường hợp xảy ra nhiều cập nhật/xóa.

Đo payload bằng serializer và đo kích thước logic/physical bằng công cụ thích hợp của database.

### Bước 2 — Tính dung lượng theo các kịch bản

Ít nhất:

- **Base:** số thiết bị và tốc độ hiện tại.
- **Peak:** tốc độ burst, tenant lớn, data record p99.
- **Growth:** số thiết bị hoặc retention tăng sau 6–12 tháng.

Với mỗi kịch bản, tính **tổng bản ghi, dung lượng mỗi partition, số lượng partition, số request và fan-out đọc**.

### Bước 3 — Dựng hai hoặc ba phương án key/bucket

Ví dụ:

| Phương án | Partition key | Điểm mạnh | Rủi ro |
|---|---|---|---|
| A | (`tenantId`, `deviceId`) | Đọc lịch sử một thiết bị theo một key logic | Partition tăng lâu dài |
| B | (`tenantId`, `deviceId`, `day`) | Ít bucket khi đọc theo ngày | Bucket của thiết bị nóng có thể rất lớn |
| C | (`tenantId`, `deviceId`, `hour`) | Giới hạn mỗi bucket tốt hơn | Nhiều bucket và fan-out khi đọc lịch sử |

Cần kiểm tra trên workload thật thay vì chọn từ bảng chỉ bằng trực giác.

### Bước 4 — Benchmark đọc và ghi đồng thời

Quan sát:

- p50/p95/p99 latency theo từng access pattern.
- Write throughput và tỷ lệ throttle/retry.
- Số byte đọc/ghi thực tế và kích thước request/response.
- Dung lượng partition lớn nhất, phân bố theo tenant/device.
- CPU, memory, disk I/O, network.
- Scan/read amplification, compaction và tombstone.
- Mức cân bằng dữ liệu giữa các node/shard/partition vật lý.
- Thời gian và chi phí của query fan-out qua nhiều bucket.

### Bước 5 — Kiểm tra tình huống tăng trưởng và lỗi

Một thiết kế có thể chạy tốt khi data nhỏ nhưng xuống cấp khi:

- Một tenant tăng 100 lần lưu lượng.
- Một partition có hàng triệu record.
- Ghi đồng thời dồn vào một key/bucket.
- Data retention kéo dài hơn ban đầu.
- Rebalancing và failover xảy ra.
- Cache bị làm trống và mọi request cùng đọc nguồn.
- Một job backfill trùng với peak traffic.

Khi cần đổi key hoặc bucket, hãy lập kế hoạch migration; thay đổi partition key thường không đơn thuần là thay một câu query.

## 15. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| “JSON dài 300 ký tự nên record nặng 300 byte” | UTF-8, encoding và overhead khác nhau | Đếm byte serializer và đo DB |
| “Mỗi record 320 B, tổng đĩa = số record × 320” | Chưa tính index, replica, log, compaction, backup | Ước lượng nhiều lớp và đo thực tế |
| Chọn bucket theo ngày mà không tính tốc độ ghi | Thiết bị nóng có thể tạo partition quá lớn | Tính \(r \times 86.400 \times s\) theo peak |
| Chọn bucket cực nhỏ vì muốn mỗi partition nhỏ | Quá nhiều bucket, fan-out và metadata | Đo cả đọc nhiều bucket |
| Dùng `tenantId` làm partition key cho mọi loại dữ liệu | Tenant lớn thành điểm nóng | Xem khóa ghép, phân bố tải và mẫu đọc |
| Giả định record trung bình đại diện mọi tenant | Skew lớn khiến p99 và hot partition bị bỏ qua | Phân tích top-N keys và p95/p99 |
| Nhúng lịch sử không giới hạn vào một document | Chạm giới hạn, ghi lại khối lớn, contention | Tách history, bucket hoặc paginate |
| Tạo index/bảng phụ miễn phí | Tăng write amplification và dung lượng | Tính chi phí duy trì mỗi đường truy cập |
| Tính TTL thành xóa vật lý ngay | Dữ liệu/tombstone có thể còn trong storage | Đọc chính sách dọn dữ liệu của sản phẩm |
| Cho rằng bucket = shard vật lý | Database có chiến lược phân vùng riêng | Tách thiết kế logic và topology thực |
| Chỉ benchmark khi hệ trống | Không thấy compaction, phân bố skew và write/read contention | Nạp dữ liệu và workload đại diện |

## 16. Bài tập ứng dụng

### Bài tập A — Ước lượng dữ liệu theo thời gian

Một hệ thống có 250 thiết bị, mỗi thiết bị ghi 4 event/giây. Mỗi event có kích thước logic trung bình 500 byte. Retention là 14 ngày.

**Yêu cầu:**

1. Tính số event/ngày của một thiết bị.
2. Tính dung lượng logic mỗi ngày của toàn hệ.
3. Tính dung lượng logic trong 14 ngày.
4. Nếu lưu ba bản sao đầy đủ, tính dung lượng cơ sở trước các overhead khác.

**Gợi ý lời giải:**

- Một thiết bị: \(4 \times 86.400 = 345.600\) event/ngày.
- Toàn hệ: \(250 \times 345.600 = 86.400.000\) event/ngày.
- Logic/ngày: \(86.400.000 \times 500 = 43.200.000.000\) byte ≈ **43,2 GB**.
- Logic/14 ngày: \(43,2 \times 14 = 604,8\) GB.
- Ba bản sao: khoảng **1.814,4 GB = 1,8144 TB** trước compression/index/log/backup và dự phòng.

Các con số là ước lượng, không phải chỉ tiêu capacity chính xác.

### Bài tập B — Chọn bucket hợp lý

Một thiết bị phát 10 event/giây, mỗi event 400 byte logic. So sánh bucket **1 giờ** và **1 ngày**.

**Gợi ý:**

- 1 giờ: \(10 \times 3.600 \times 400 = 14.400.000\) byte ≈ **14,4 MB**.
- 1 ngày: \(10 \times 86.400 \times 400 = 345.600.000\) byte ≈ **345,6 MB**.

Nếu người dùng chủ yếu đọc 100 event mới nhất thì bucket giờ có thể giúp giới hạn nhóm; nếu thường đọc cả ngày, bucket giờ phải đọc tới 24 nhóm. Chọn phương án bằng đo thực tế, không chỉ bằng dung lượng.

### Bài tập C — Vì sao cùng kích thước trung bình vẫn có rủi ro khác?

Hai loại event đều trung bình 1 KB. Loại A luôn dưới 2 KB. Loại B có 99,9% event chỉ 100 B nhưng đôi khi có payload vài MB.

**Câu hỏi:** loại nào dễ gặp vấn đề giới hạn kích thước bản ghi và latency đột biến? Cần đo thêm chỉ số nào?

**Gợi ý:** loại B có đuôi phân bố lớn, cần p99/p99.9, max, kích thước request, serialization time và giới hạn item/document của sản phẩm. Trung bình không cho biết các trường hợp hiếm nhưng rất nặng.

### Bài tập D — Thiết kế theo hai truy vấn

Ứng dụng lưu tin nhắn:

- Q1: lấy 50 tin mới nhất của một cuộc trò chuyện.
- Q2: tìm tất cả tin chứa một từ khóa trong mọi cuộc trò chuyện.

Nếu lưu theo `conversationId` và thời gian, Q1 thuận lợi nhưng Q2 có thể phải quét rộng. Hãy đề xuất một mô hình lưu cho Q1 và cơ chế search/index phục vụ Q2, rồi liệt kê chi phí đồng bộ.

**Gợi ý:** partition theo conversation và bucket thời gian có thể phù hợp Q1; Q2 có thể cần full-text index/search engine riêng. Cần xử lý tin sửa/xóa, cập nhật chỉ mục, độ trễ search và quyền truy cập.

### Bài tập E — Hot tenant

Một dịch vụ có 1.000 tenant. Tenant A chiếm 75% lưu lượng ghi, còn các tenant khác chia nhau 25%. Nếu chọn `tenantId` làm partition key, vấn đề nào có thể xảy ra?

**Gợi ý:** một partition/key group chịu tải áp đảo. Cân nhắc thêm entity ID, bucket hoặc salt có chủ đích; đánh giá read fan-out và yêu cầu query theo tenant. Nhiều tenant không tự đảm bảo phân bố đều.

## 17. Nguồn tham khảo theo hệ quản trị

Các khái niệm ở trên cần đối chiếu với tài liệu chính thức khi quyết định giới hạn và cách tính của một sản phẩm:

- [MongoDB Manual](https://www.mongodb.com/docs/manual/) — giới hạn document BSON, embedding, indexes, shard keys và quản lý dữ liệu.
- [Apache Cassandra Documentation](https://cassandra.apache.org/doc/latest/) — partition key, clustering, giới hạn và khuyến nghị thiết kế partition, compaction, tombstones.
- [Amazon DynamoDB Developer Guide](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html) — partition key, sort key, item size, capacity, read/write và design patterns.
- [Google Cloud Bigtable Documentation](https://cloud.google.com/bigtable/docs) — row key, data layout, hotspot, tablet và schema design.
- [Redis Documentation](https://redis.io/docs/latest/) — memory, data types, expiration, persistence và cluster key distribution.
- [Apache Parquet Documentation](https://parquet.apache.org/docs/) — row groups, column chunks và cách bố trí dữ liệu trong hệ phân tích dạng cột.

Khi tài liệu ghi “giới hạn kích thước”, phải xác định đó là **mỗi item, document, cell, row, partition, batch hay request**. Những giới hạn khác nhau không thể dùng thay thế cho nhau. Cũng cần phân biệt giới hạn cứng với khuyến nghị tối ưu hiệu năng.

## 18. Điều cần nhớ

Ước lượng kích thước trong NoSQL là một phần của **thiết kế đường truy cập**: kích thước bản ghi quyết định byte mỗi thao tác, cách gom dữ liệu quyết định đơn vị đọc/ghi, còn partition/bucket quyết định phạm vi dữ liệu và khả năng phân phối tải.

Hãy đi theo trình tự **mẫu truy vấn → số bản ghi và phân bố kích thước → kích thước nhóm/partition → chi phí đọc qua nhóm → overhead lưu trữ và replication → đo thực tế**. Công thức giúp phát hiện thiết kế có rủi ro ngay từ đầu, nhưng quyết định cuối cần dựa trên sản phẩm, phiên bản và workload đang chạy.

Một thiết kế NoSQL tốt không chỉ trả lời “truy vấn này đọc được không?”, mà còn trả lời **“khi dữ liệu tăng gấp 10 hoặc 100 lần, mỗi bản ghi, mỗi nhóm, mỗi partition và mỗi đường truy cập sẽ tốn bao nhiêu tài nguyên?”**

