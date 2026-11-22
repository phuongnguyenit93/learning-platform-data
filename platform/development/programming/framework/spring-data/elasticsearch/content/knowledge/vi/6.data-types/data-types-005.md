# Kiểu date, date_nanos, định dạng và múi giờ

Elasticsearch cung cấp hai kiểu dữ liệu thời gian chính là date và date_nanos. Cả hai đều biểu diễn một thời điểm trên dòng thời gian, hỗ trợ lọc theo khoảng, sắp xếp và các phép tổng hợp thời gian. Điểm khác biệt quan trọng nhất là độ chính xác: date lưu thời gian ở mức mili giây, còn date_nanos hỗ trợ đến nano giây.

Khi làm việc với Spring Data Elasticsearch, việc chọn đúng kiểu field mới chỉ là bước đầu. Ứng dụng còn phải thống nhất định dạng chuỗi ngày giờ, cách chuyển đổi kiểu Java, múi giờ khi ghi và khi truy vấn. Nếu các quy ước này không rõ ràng, dữ liệu có thể bị lệch thời gian, mất phần mili giây hoặc được lọc sai ở ranh giới ngày.

## 1. Hai kiểu dữ liệu thời gian của Elasticsearch

### 1.1. Kiểu date

Kiểu date phù hợp với phần lớn dữ liệu nghiệp vụ có độ chính xác đến mili giây, chẳng hạn:

- Thời điểm tạo hoặc cập nhật bản ghi.
- Ngày xuất bản bài viết.
- Thời điểm tạo đơn hàng hoặc thanh toán.
- Thời gian bắt đầu và kết thúc một phiên làm việc.
- Thời hạn hợp đồng hoặc lịch hẹn.

Elasticsearch chuyển giá trị date thành số nguyên biểu diễn mili giây kể từ Unix epoch, tức 1970-01-01T00:00:00Z. Vì vậy, dữ liệu có thể được sắp xếp và so sánh hiệu quả như một giá trị số.

Một field date có thể nhận chuỗi ngày giờ theo format được khai báo hoặc số epoch mili giây. Khi trả kết quả, định dạng hiển thị phụ thuộc vào API và cách ứng dụng chuyển đổi dữ liệu; Elasticsearch không giữ nguyên văn bản đầu vào như một chuỗi gốc.

### 1.2. Kiểu date_nanos

Kiểu date_nanos lưu thời gian với độ chính xác đến nano giây. Nó hữu ích khi các sự kiện có thể xảy ra rất gần nhau và thứ tự ở mức mili giây là chưa đủ, ví dụ:

- Dữ liệu đo đạc tần suất cao.
- Sự kiện giao dịch hoặc log cần phân biệt thời điểm rất sát nhau.
- Dữ liệu quan sát hệ thống có timestamp độ phân giải cao.
- Dữ liệu khoa học hoặc thiết bị có đồng hồ xuất ra nano giây.

date_nanos dùng biểu diễn epoch nano giây dựa trên số nguyên 64-bit. Vì phạm vi của số nguyên này hữu hạn, khoảng ngày hỗ trợ hẹp hơn date; trong tài liệu Elasticsearch, giới hạn thực tế của date_nanos thường được nêu từ năm 1970 đến năm 2262. Nếu hệ thống cần lưu ngày lịch sử rất xa trước epoch hoặc ngày rất xa trong tương lai, hãy kiểm tra giới hạn của phiên bản Elasticsearch đang triển khai trước khi chọn kiểu này.

### 1.3. So sánh date và date_nanos

| Tiêu chí | date | date_nanos |
|---|---|---|
| Độ chính xác | Mili giây | Nano giây |
| Biểu diễn nội bộ | Epoch mili giây | Epoch nano giây |
| Phạm vi ngày | Rộng, phù hợp ngày lịch thông thường | Hẹp hơn do giới hạn số nguyên 64-bit |
| Kích thước và chi phí | Thường phù hợp hơn cho timestamp phổ thông | Có thể tốn tài nguyên hơn tùy workload |
| Trường hợp sử dụng | Thời điểm nghiệp vụ, ngày tạo/cập nhật, lịch | Telemetry hoặc sự kiện cần độ phân giải nano giây |

Không nên chọn date_nanos chỉ vì nó có độ chính xác cao hơn. Nếu nguồn dữ liệu chỉ cung cấp mili giây, lưu thành nano giây không tạo thêm thông tin thời gian. Hãy chọn độ chính xác dựa trên yêu cầu nghiệp vụ, chất lượng timestamp đầu vào, phạm vi ngày và chi phí lưu trữ/truy vấn.

## 2. Định dạng ngày giờ (format)

Mapping của Elasticsearch quy định những định dạng nào được chấp nhận khi phân tích giá trị đầu vào. Một field có thể khai báo một format hoặc nhiều format được nối bằng dấu phân cách ||. Elasticsearch thử các format theo thứ tự để đọc giá trị.

### 2.1. Format mặc định

Nếu không khai báo format, kiểu date dùng mặc định:

~~~text
strict_date_optional_time||epoch_millis
~~~

Nghĩa là field có thể nhận chuỗi ngày giờ theo định dạng ISO nghiêm ngặt hoặc số epoch mili giây.

Kiểu date_nanos có mặc định tương ứng cho chuỗi có độ chính xác nano giây:

~~~text
strict_date_optional_time_nanos||epoch_millis
~~~

Ví dụ các chuỗi ngày giờ có thể đọc được theo format ISO:

~~~text
2025-04-18
2025-04-18T09:30:00Z
2025-04-18T09:30:00.123Z
2025-04-18T09:30:00.123456789Z
2025-04-18T16:30:00+07:00
~~~

Giá trị có phần thập phân nano giây cần kiểu date_nanos nếu muốn giữ đủ độ chính xác. Với date, phần thời gian được lưu ở mức mili giây.

### 2.2. Khai báo format trong mapping

Có thể khai báo mapping rõ ràng bằng REST API:

~~~http
PUT /application-events
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "createdAt": {
        "type": "date",
        "format": "strict_date_optional_time||epoch_millis"
      },
      "measuredAt": {
        "type": "date_nanos",
        "format": "strict_date_optional_time_nanos||epoch_millis"
      }
    }
  }
}
~~~

Ví dụ document:

~~~http
POST /application-events/_doc
Content-Type: application/json

{
  "createdAt": "2025-04-18T09:30:00.123Z",
  "measuredAt": "2025-04-18T09:30:00.123456789Z"
}
~~~

Field createdAt phù hợp với timestamp thông thường. Field measuredAt có thể giữ phần nano giây do kiểu date_nanos hỗ trợ.

### 2.3. Kết hợp nhiều format

Ứng dụng có thể phải nhận dữ liệu từ nhiều nguồn, ví dụ một nguồn gửi ISO-8601 còn nguồn khác gửi epoch mili giây. Có thể khai báo nhiều format:

~~~json
{
  "mappings": {
    "properties": {
      "eventTime": {
        "type": "date",
        "format": "strict_date_optional_time||epoch_millis"
      }
    }
  }
}
~~~

Không nên mở rộng danh sách format một cách tùy tiện. Mỗi format bổ sung làm tăng số cách biểu diễn mà ứng dụng phải hiểu và kiểm thử. Tốt nhất là chuẩn hóa dữ liệu tại biên hệ thống để các producer gửi một định dạng thống nhất.

### 2.4. Format tùy chỉnh

Nếu dữ liệu đầu vào có định dạng riêng, có thể khai báo pattern tương ứng. Ví dụ, hệ thống cũ gửi ngày giờ như năm-tháng-ngày, dấu cách, giờ-phút-giây:

~~~http
PUT /legacy-events
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "eventTime": {
        "type": "date",
        "format": "yyyy-MM-dd HH:mm:ss"
      }
    }
  }
}
~~~

Document:

~~~json
{
  "eventTime": "2025-04-18 09:30:00"
}
~~~

Pattern phải phù hợp với dữ liệu thực tế và cách Elasticsearch diễn giải ký hiệu ngày giờ. Một số ký hiệu có ý nghĩa khác nhau, ví dụ:

| Ký hiệu | Ý nghĩa thường dùng |
|---|---|
| yyyy | Năm theo lịch |
| MM | Tháng |
| dd | Ngày trong tháng |
| HH | Giờ theo hệ 24 giờ |
| mm | Phút |
| ss | Giây |
| S | Phần thập phân của giây |
| XXX | Offset múi giờ dạng như +07:00 |

Không nhầm MM (tháng) với mm (phút). Nếu pattern không chứa offset hoặc zone, chuỗi đầu vào không tự mang thông tin múi giờ; Elasticsearch sẽ áp dụng quy tắc mặc định khi phân tích.

Với hệ thống mới, ưu tiên định dạng ISO-8601 có offset rõ ràng, chẳng hạn 2025-04-18T16:30:00+07:00 hoặc UTC với hậu tố Z. Pattern tùy chỉnh chỉ nên dùng khi phải tích hợp dữ liệu legacy.

## 3. Epoch time: giây và mili giây

Unix epoch là mốc 1970-01-01T00:00:00Z. Một timestamp epoch biểu diễn khoảng thời gian tính từ mốc này.

Hai đơn vị thường gặp:

- Epoch second: số giây kể từ epoch.
- Epoch millisecond: số mili giây kể từ epoch.

Ví dụ:

~~~text
2025-01-01T00:00:00Z

epoch seconds      = 1735689600
epoch milliseconds = 1735689600000
~~~

Chênh lệch đơn vị là 1.000 lần. Nếu gửi giá trị giây vào field đang chờ mili giây, Elasticsearch sẽ hiểu nó là số mili giây và tạo ra thời điểm gần đầu năm 1970. Đây là lỗi phổ biến khi tích hợp giữa JavaScript, Java, thiết bị và các API bên ngoài.

Nếu muốn nhận epoch second, mapping phải khai báo format phù hợp, ví dụ:

~~~json
{
  "eventTime": {
    "type": "date",
    "format": "epoch_second"
  }
}
~~~

Nếu hệ thống cần cả chuỗi ISO và epoch second, có thể khai báo:

~~~json
{
  "eventTime": {
    "type": "date",
    "format": "strict_date_optional_time||epoch_second"
  }
}
~~~

Hãy thống nhất đơn vị tại API contract. Tên thuộc tính như createdAt không cho biết số nguyên đi kèm là giây hay mili giây; tài liệu API và kiểu dữ liệu nên thể hiện rõ đơn vị.

## 4. Múi giờ và cách Elasticsearch chuẩn hóa thời gian

### 4.1. Thời điểm tuyệt đối và giờ địa phương

Một thời điểm tuyệt đối xác định một vị trí duy nhất trên dòng thời gian. Ví dụ:

~~~text
2025-04-18T09:30:00Z
2025-04-18T16:30:00+07:00
~~~

Hai biểu diễn trên chỉ cùng một thời điểm: 09:30 UTC tương đương 16:30 ở múi giờ UTC+07:00.

Ngược lại, chuỗi 2025-04-18 16:30:00 không có offset hoặc zone. Nó chỉ cho biết đồng hồ địa phương hiển thị 16:30; không thể xác định chính xác thời điểm tuyệt đối nếu không biết múi giờ quy ước.

Elasticsearch chuẩn hóa giá trị date/date_nanos thành biểu diễn epoch theo UTC. Offset được cung cấp trong chuỗi được dùng để tính thời điểm tương ứng. Thông tin tên múi giờ ban đầu, chẳng hạn Asia/Ho_Chi_Minh, không được giữ lại như một phần của giá trị date sau khi chuẩn hóa.

Nếu nghiệp vụ cần biết múi giờ gốc mà người dùng đã chọn, hãy lưu riêng mã zone, ví dụ:

~~~json
{
  "scheduledAt": "2025-04-18T09:30:00Z",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

Ở đây scheduledAt biểu diễn thời điểm tuyệt đối; timeZone lưu ngữ cảnh lịch địa phương để có thể hiển thị hoặc tính toán lại theo quy tắc nghiệp vụ.

### 4.2. Chuỗi không có múi giờ

Nếu chuỗi ngày giờ không có offset hoặc zone, Elasticsearch mặc định diễn giải theo UTC. Ví dụ:

~~~text
2025-04-18T16:30:00
~~~

Giá trị này được hiểu là 16:30 UTC, không tự động là 16:30 theo múi giờ của máy chạy ứng dụng hoặc người dùng.

Vì vậy, không nên gửi local date-time không có offset nếu producer và consumer không thống nhất quy ước. Hãy chuyển thành thời điểm có offset/UTC trước khi gửi, hoặc khai báo rõ zone trong quy trình chuyển đổi ở ứng dụng.

### 4.3. Chuyển đổi giữa giờ Việt Nam và UTC

Việt Nam sử dụng múi giờ UTC+07:00. Ví dụ, 2025-04-18T16:30:00+07:00 tương ứng 2025-04-18T09:30:00Z.

Khi lưu thời điểm từ ứng dụng Việt Nam, nên gửi chuỗi ISO-8601 có offset hoặc chuyển về Instant/UTC trước khi ghi. Khi hiển thị, chuyển thời điểm UTC sang ZoneId phù hợp với người dùng.

Không nên cộng hoặc trừ cố định bảy giờ ở nhiều tầng khác nhau. Hãy để thư viện thời gian thực hiện chuyển đổi từ Instant sang ZoneId; cách làm này rõ ràng và tránh lỗi khi ứng dụng phục vụ người dùng ở nhiều quốc gia.

## 5. Dùng múi giờ trong range query

Khi lọc dữ liệu theo một khoảng thời gian địa phương, ranh giới ngày cần được chuyển đổi theo đúng múi giờ. Range query của Elasticsearch hỗ trợ tham số time_zone.

Ví dụ tìm các sự kiện trong ngày 18-04-2025 theo giờ Việt Nam:

~~~http
POST /application-events/_search
Content-Type: application/json

{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2025-04-18T00:00:00",
        "lt": "2025-04-19T00:00:00",
        "time_zone": "+07:00"
      }
    }
  }
}
~~~

Elasticsearch diễn giải hai mốc địa phương theo offset +07:00 rồi chuyển thành thời điểm UTC để so sánh. Khoảng dùng gte ở đầu và lt ở cuối giúp tránh đếm trùng một sự kiện nằm đúng nửa đêm của ngày tiếp theo.

Nếu gửi các mốc có offset rõ ràng, chẳng hạn:

~~~json
{
  "gte": "2025-04-17T17:00:00Z",
  "lt": "2025-04-18T17:00:00Z"
}
~~~

thì các giá trị đã thể hiện rõ thời điểm tuyệt đối. Không cần thêm time_zone chỉ để chuyển đổi lại cùng các mốc đó.

Tham số format của range query có thể được dùng để phân tích giá trị đầu vào theo format cụ thể. Nếu không truyền, Elasticsearch dùng format của field mapping. Cần phân biệt format trong mapping (quy định dữ liệu field chấp nhận) với format của query (quy định cách đọc các giá trị trong request tìm kiếm).

## 6. Date math và thời điểm hiện tại

Elasticsearch hỗ trợ date math trong truy vấn thời gian. Ký hiệu now đại diện thời điểm hiện tại. Có thể cộng/trừ đơn vị thời gian và làm tròn theo đơn vị:

| Biểu thức | Ý nghĩa |
|---|---|
| now | Thời điểm hiện tại |
| now-1d | Lùi một ngày tính từ hiện tại |
| now-15m | Lùi 15 phút |
| now/d | Làm tròn xuống đầu ngày |
| now-7d/d | Lùi bảy ngày rồi làm tròn xuống đầu ngày |
| now+2h | Cộng hai giờ |

Ví dụ tìm sự kiện trong bảy ngày gần nhất:

~~~http
POST /application-events/_search
Content-Type: application/json

{
  "query": {
    "range": {
      "createdAt": {
        "gte": "now-7d",
        "lte": "now"
      }
    }
  }
}
~~~

now được đánh giá theo thời điểm hiện tại của Elasticsearch trên dòng thời gian UTC. Trong truy vấn có time_zone, tham số này không thay đổi chính thời điểm tuyệt đối now; tuy nhiên múi giờ có thể ảnh hưởng cách làm tròn ngày/giờ trong date math và cách diễn giải các mốc không có offset. Khi nghiệp vụ yêu cầu “hôm nay theo giờ của người dùng”, cần chỉ định múi giờ và kiểm thử ranh giới ngày.

## 7. Múi giờ trong date histogram

Date histogram nhóm document theo khoảng thời gian. Với dữ liệu theo ngày, múi giờ ảnh hưởng thời điểm bắt đầu của bucket. Nếu muốn báo cáo ngày theo giờ địa phương, hãy truyền time_zone vào aggregation.

Ví dụ:

~~~http
POST /application-events/_search
Content-Type: application/json

{
  "size": 0,
  "aggs": {
    "events_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "+07:00"
      }
    }
  }
}
~~~

calendar_interval day tạo bucket theo ngày lịch. Đây là lựa chọn phù hợp cho báo cáo ngày, tháng hoặc năm theo lịch. fixed_interval biểu diễn khoảng thời gian cố định, ví dụ 24h, 60m hoặc 15m.

Không nên luôn thay calendar_interval day bằng fixed_interval 24h. Ở các múi giờ có quy tắc daylight saving time, một ngày lịch có thể dài 23 hoặc 25 giờ. Dùng calendar interval cùng time_zone giúp bucket bám theo ngày địa phương. Với fixed interval, khoảng thời gian được tính theo độ dài cố định.

## 8. Ánh xạ kiểu thời gian trong Spring Data Elasticsearch

Spring Data Elasticsearch dùng mapping metadata và MappingElasticsearchConverter để chuyển đổi entity Java thành document và ngược lại. Các kiểu thời gian Java thường gặp gồm:

| Kiểu Java | Ý nghĩa | Lưu ý |
|---|---|---|
| Instant | Một thời điểm tuyệt đối trên UTC timeline | Thường là lựa chọn rõ ràng cho timestamp sự kiện |
| OffsetDateTime | Ngày giờ kèm offset UTC | Elasticsearch chuẩn hóa thành thời điểm; offset gốc không được giữ như một zone riêng |
| ZonedDateTime | Ngày giờ gắn với ZoneId | Nếu cần giữ ZoneId, lưu thêm trường zone riêng |
| LocalDateTime | Ngày giờ không có offset/zone | Chỉ dùng khi nghiệp vụ thực sự là giờ địa phương và đã quy định zone ở nơi chuyển đổi |
| LocalDate | Ngày lịch, không có thời điểm trong ngày | Phù hợp ngày sinh, ngày hiệu lực theo lịch nếu không cần giờ |
| java.util.Date | Thời điểm theo độ chính xác mili giây | Kiểu cũ; API mới thường ưu tiên java.time |

Với timestamp sự kiện, Instant thường giúp biểu diễn ý nghĩa rõ nhất. LocalDateTime không chứa thông tin múi giờ; không nên dùng nó như một Instant nếu ứng dụng chưa xác định zone để chuyển đổi.

### 8.1. Khai báo field date

Ví dụ entity:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "application-events")
public class ApplicationEvent {

    @Id
    private String id;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // constructors, getters and setters
}
~~~

FieldType.Date khai báo kiểu date trong mapping Elasticsearch. Instant biểu diễn thời điểm tuyệt đối, thuận tiện cho việc chuẩn hóa và so sánh thời gian.

### 8.2. Khai báo field date_nanos

Nếu cần giữ độ chính xác nano giây, có thể dùng FieldType.Date_Nanos trong các phiên bản Spring Data Elasticsearch hỗ trợ kiểu này:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "sensor-readings")
public class SensorReading {

    @Id
    private String id;

    @Field(type = FieldType.Date_Nanos)
    private Instant measuredAt;

    // constructors, getters and setters
}
~~~

Hãy xác nhận FieldType.Date_Nanos có trong phiên bản Spring Data Elasticsearch mà dự án sử dụng. Nếu phiên bản cũ chưa hỗ trợ enum hoặc mapping tương ứng, cần nâng cấp đồng bộ theo ma trận tương thích hoặc cấu hình mapping bằng cách khác.

Instant có thể chứa nano giây, nhưng nếu field đích là date thì phần dưới mili giây không được lưu với độ chính xác tương ứng. Muốn giữ phần nano giây, cả kiểu mapping Elasticsearch và đường chuyển đổi dữ liệu phải hỗ trợ độ chính xác đó.

### 8.3. Khai báo format tùy chỉnh trong annotation

Spring Data Elasticsearch cho phép khai báo format và pattern trên @Field. Ví dụ:

~~~java
@Field(
    type = FieldType.Date,
    pattern = "yyyy-MM-dd HH:mm:ss"
)
private LocalDateTime importedAt;
~~~

Pattern cần khớp dữ liệu thực tế. Ví dụ trên không có offset, vì vậy nó biểu diễn giờ địa phương theo quy ước của ứng dụng chứ không tự xác định được thời điểm tuyệt đối. Nếu dữ liệu có offset, pattern phải bao gồm phần offset và kiểu Java nên phản ánh được thông tin đó.

Với dữ liệu mới, ưu tiên ISO-8601 và kiểu thời gian có ý nghĩa rõ ràng. Pattern riêng thường dành cho hệ thống legacy hoặc hợp đồng tích hợp đã cố định.

## 9. Chuẩn hóa thời gian ở biên ứng dụng

Một kiến trúc ổn định nên thống nhất cách xử lý thời gian ở nơi nhận dữ liệu:

~~~text
Client / hệ thống bên ngoài
        |
        | ISO-8601 có offset hoặc epoch có đơn vị rõ
        v
API boundary
        |
        | parse và kiểm tra
        | chuyển thành Instant
        v
Spring Data Elasticsearch
        |
        | mapping date hoặc date_nanos
        v
Elasticsearch (UTC timeline)
        |
        | range query / sort / aggregation
        v
API response
        |
        | chuyển Instant sang ZoneId hiển thị
        v
Người dùng
~~~

Quy tắc thực tế:

1. Xác định rõ dữ liệu là một thời điểm tuyệt đối hay một ngày/giờ lịch địa phương.
2. Với thời điểm tuyệt đối, yêu cầu client gửi ISO-8601 có offset hoặc epoch có đơn vị rõ ràng.
3. Parse dữ liệu tại API boundary và chuyển thành Instant nếu nghiệp vụ làm việc với thời điểm tuyệt đối.
4. Chọn date hay date_nanos theo độ chính xác thật sự cần thiết.
5. Khi tìm theo ngày địa phương, chuyển ranh giới ngày sang UTC hoặc truyền time_zone phù hợp trong query.
6. Khi hiển thị, chuyển Instant sang ZoneId của người dùng.
7. Nếu cần giữ múi giờ gốc hoặc lịch địa phương, lưu thêm zone ID hoặc thông tin nghiệp vụ cần thiết.

## 10. Các lỗi thường gặp

### 10.1. Gửi epoch second vào field đang chờ epoch millisecond

Giá trị 1735689600 có thể được hiểu là mili giây nếu mapping dùng epoch_millis. Kết quả sẽ nằm gần năm 1970 thay vì năm 2025. Cần kiểm tra đơn vị ở API contract và chuyển đổi rõ ràng.

### 10.2. Dùng date nhưng mong giữ nano giây

Kiểu date có độ chính xác mili giây. Nếu ứng dụng gửi timestamp có chín chữ số phần thập phân, không nên kỳ vọng date giữ được toàn bộ độ chính xác. Hãy dùng date_nanos khi thật sự cần.

### 10.3. Dùng LocalDateTime như một thời điểm UTC

LocalDateTime không có offset hoặc ZoneId. Cùng một giá trị 09:00 có thể chỉ nhiều thời điểm khác nhau tùy múi giờ. Hãy chuyển đổi sang Instant bằng một ZoneId xác định trước khi ghi nếu nghiệp vụ cần thời điểm tuyệt đối.

### 10.4. Lưu UTC nhưng lọc theo ngày địa phương như thể đó là UTC

Một ngày theo UTC+07:00 bắt đầu lúc 17:00 UTC của ngày trước đó. Nếu dùng 00:00 UTC làm mốc đầu ngày Việt Nam, truy vấn sẽ bỏ sót hoặc lấy thừa dữ liệu quanh ranh giới. Hãy chuyển đổi ranh giới hoặc dùng time_zone.

### 10.5. Nghĩ Elasticsearch giữ nguyên tên múi giờ

Offset giúp xác định thời điểm và được chuẩn hóa về UTC. Nếu cần biết lịch gốc thuộc Asia/Ho_Chi_Minh, Europe/Paris hoặc zone khác, hãy lưu ZoneId riêng.

### 10.6. Dùng format quá rộng hoặc không nhất quán

Chấp nhận nhiều pattern không cần thiết khiến dữ liệu khó chuẩn hóa và tăng khả năng nhập sai. Hãy chọn một định dạng chuẩn cho producer, chỉ giữ format legacy khi có nhu cầu tương thích thực tế.

### 10.7. Dùng inclusive end ở ranh giới khoảng thời gian

Khi truy vấn một ngày, điều kiện gte đầu ngày và lt đầu ngày kế tiếp thường an toàn hơn gte/lte với thời điểm cuối ngày giả định như 23:59:59.999. Cách dùng khoảng nửa mở không phụ thuộc độ chính xác date hay date_nanos.

## 11. Ví dụ: lưu và tìm sự kiện theo ngày tại Việt Nam

Giả sử hệ thống nhận sự kiện từ một thiết bị ở Việt Nam. Thiết bị gửi:

~~~json
{
  "measuredAt": "2025-04-18T16:30:00.123456789+07:00"
}
~~~

Ứng dụng parse giá trị thành Instant. Thời điểm tương ứng là:

~~~text
2025-04-18T09:30:00.123456789Z
~~~

Nếu sự kiện cần độ chính xác nano giây, entity dùng FieldType.Date_Nanos và index mapping có kiểu date_nanos. Nếu chỉ cần độ chính xác mili giây, dùng FieldType.Date.

Để tìm tất cả sự kiện trong ngày 18-04-2025 theo giờ Việt Nam, API có thể gửi range query với time_zone +07:00 và khoảng nửa mở từ đầu ngày đến đầu ngày tiếp theo. Elasticsearch sẽ so sánh các thời điểm đã chuẩn hóa trên cùng UTC timeline.

Khi trả dữ liệu cho giao diện, ứng dụng chuyển Instant về ZoneId.of("Asia/Ho_Chi_Minh") để hiển thị. Nếu người dùng thay đổi múi giờ, cùng một Instant có thể được hiển thị thành giờ địa phương khác mà không cần thay đổi dữ liệu đã lưu.

## 12. Kết luận

date là lựa chọn phù hợp cho hầu hết timestamp nghiệp vụ với độ chính xác mili giây. date_nanos dành cho dữ liệu thực sự cần độ chính xác nano giây và có phạm vi ngày hẹp hơn. Format quy định cách Elasticsearch đọc chuỗi hoặc epoch; múi giờ xác định cách diễn giải các giá trị địa phương và ranh giới truy vấn.

Trong Spring Data Elasticsearch, hãy chọn kiểu Java phù hợp với ý nghĩa dữ liệu, thường dùng Instant cho thời điểm tuyệt đối, rồi ánh xạ sang FieldType.Date hoặc FieldType.Date_Nanos. Chuẩn hóa đầu vào theo ISO-8601 có offset hoặc epoch có đơn vị rõ ràng, lưu thời điểm theo UTC và chỉ chuyển sang múi giờ người dùng khi truy vấn hoặc hiển thị.
