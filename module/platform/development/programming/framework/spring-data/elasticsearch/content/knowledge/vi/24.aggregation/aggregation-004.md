# Date histogram, histogram và khoảng giá trị

Elasticsearch aggregation có thể gom document thành các nhóm (bucket) để phân tích dữ liệu. Ba kiểu bucket aggregation thường dùng là:

- **date_histogram**: chia dữ liệu theo các khoảng thời gian như giờ, ngày, tuần hoặc tháng.
- **histogram**: chia giá trị số thành các khoảng đều nhau, ví dụ mỗi 100.000 đồng hoặc mỗi 5 đơn vị.
- **range**: gom dữ liệu vào các khoảng giá trị do ứng dụng định nghĩa, ví dụ dưới 100.000, từ 100.000 đến dưới 500.000 và từ 500.000 trở lên.

Các aggregation này không trả về một document cho mỗi bucket. Chúng trả về thống kê của từng nhóm, chẳng hạn số document, tổng doanh thu, giá trung bình hoặc aggregation con.

Trong Spring Data Elasticsearch, có thể gửi bucket aggregation bằng NativeQuery và Elasticsearch Java API Client, sau đó đọc kết quả từ aggregation container của SearchHits hoặc API aggregate tương ứng. Bài này giải thích cách chọn loại bucket, quy tắc biên, interval, timezone, empty bucket, nested aggregation và cách áp dụng vào báo cáo.

## 1. Bucket aggregation là gì?

Bucket aggregation chia tập document thành các nhóm dựa trên giá trị của một field hoặc một quy tắc. Mỗi document có thể thuộc một hoặc nhiều bucket tùy loại aggregation.

Ví dụ index orders:

~~~json
{
  "orderId": "O-1001",
  "createdAt": "2026-11-13T08:30:00Z",
  "totalInCents": 259900,
  "status": "PAID"
}
~~~

Một báo cáo có thể cần:

- Số đơn hàng theo tháng.
- Doanh thu theo từng ngày.
- Số sản phẩm theo khoảng giá.
- Giá trị đơn hàng trung bình trong từng nhóm.
- Số đơn PAID và CANCELLED trong mỗi khoảng thời gian.

Aggregation giúp Elasticsearch thực hiện phép gom nhóm ở phía cluster thay vì tải toàn bộ document về Java rồi tự nhóm trong bộ nhớ ứng dụng.

Luồng xử lý:

~~~text
Search request
    |
    v
Query chọn tập document cần phân tích
    |
    v
Bucket aggregation
    |
    +--> Bucket 1
    |      +--> doc_count
    |      +--> metric sub-aggregations
    |
    +--> Bucket 2
    |      +--> doc_count
    |      +--> metric sub-aggregations
    |
    +--> Bucket N
           +--> doc_count
           +--> metric sub-aggregations
    |
    v
Aggregation response
    |
    v
DTO / báo cáo / biểu đồ
~~~

Phần query và aggregation có nhiệm vụ khác nhau:

- Query giới hạn document nào tham gia phân tích.
- Bucket aggregation chia các document đã chọn thành nhóm.
- Metric aggregation tính số liệu trong từng nhóm.

Ví dụ, filter orders có status = PAID trước, sau đó date_histogram nhóm các đơn đã thanh toán theo tháng và sum tính doanh thu từng tháng.

## 2. Chuẩn bị dữ liệu và mapping

Giả sử entity Order:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    @Field(type = FieldType.Long)
    private Long totalInCents;

    @Field(type = FieldType.Keyword)
    private String status;

    // constructors, getters and setters
}
~~~

Mapping Elasticsearch tương ứng:

~~~json
{
  "mappings": {
    "properties": {
      "createdAt": {
        "type": "date"
      },
      "totalInCents": {
        "type": "long"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

Một số nguyên tắc:

- Field dùng date_histogram phải có mapping date hoặc kiểu ngày được Elasticsearch hỗ trợ.
- Field dùng histogram phải là kiểu số có thể aggregate, chẳng hạn integer, long, float hoặc double.
- Field dùng range aggregation phải có kiểu dữ liệu tương thích với khoảng được khai báo.
- Các field cần aggregation phải có doc values; đây là mặc định với phần lớn field keyword, số và date.
- Text field thông thường không phù hợp để histogram hoặc range số. Với text cần phân nhóm theo giá trị chính xác, dùng multi-field keyword.

Kiểm tra mapping thực tế:

~~~http
GET /orders/_mapping?pretty
~~~

Annotation Java chỉ mô tả mapping metadata cho index được tạo theo cấu hình tương ứng. Nếu index đã tồn tại với mapping cũ, thay đổi annotation không tự động sửa mapping. Cần kiểm tra index thực tế và thực hiện migration/reindex nếu cần.

## 3. Date histogram: nhóm document theo thời gian

date_histogram chia giá trị date thành các bucket theo interval. Ví dụ:

- Mỗi giờ.
- Mỗi ngày.
- Mỗi tuần.
- Mỗi tháng.
- Mỗi quý.
- Mỗi năm.

Ví dụ đếm đơn hàng theo ngày:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day"
      }
    }
  }
}
~~~

Response rút gọn:

~~~json
{
  "aggregations": {
    "orders_per_day": {
      "buckets": [
        {
          "key_as_string": "2026-11-11T00:00:00.000Z",
          "key": 1794355200000,
          "doc_count": 12
        },
        {
          "key_as_string": "2026-11-12T00:00:00.000Z",
          "key": 1794441600000,
          "doc_count": 18
        },
        {
          "key_as_string": "2026-11-13T00:00:00.000Z",
          "key": 1794528000000,
          "doc_count": 9
        }
      ]
    }
  }
}
~~~

Mỗi bucket có:

- key: thời điểm bắt đầu bucket dưới dạng epoch milliseconds.
- key_as_string: biểu diễn thời gian theo format đã chọn hoặc mặc định.
- doc_count: số document thuộc bucket.

Các bucket được xác định từ interval và timezone. key đại diện mốc bắt đầu của bucket, không phải timestamp của một document cụ thể.

### 3.1. Calendar interval và fixed interval

date_histogram có hai cách xác định khoảng thời gian:

- **calendar_interval**: theo lịch.
- **fixed_interval**: theo độ dài thời gian cố định.

Ví dụ calendar interval:

~~~json
{
  "date_histogram": {
    "field": "createdAt",
    "calendar_interval": "month"
  }
}
~~~

Ví dụ fixed interval:

~~~json
{
  "date_histogram": {
    "field": "createdAt",
    "fixed_interval": "30m"
  }
}
~~~

Calendar interval phù hợp với ngày, tuần, tháng, quý và năm theo lịch. Fixed interval phù hợp với khoảng thời gian có độ dài cố định như 15 phút, 30 phút, 6 giờ hoặc 24 giờ.

Không thể thay mọi calendar interval bằng fixed interval tương ứng một cách máy móc. Tháng có 28, 29, 30 hoặc 31 ngày; ngày tại vùng có DST có thể dài 23 hoặc 25 giờ. Calendar interval giữ ranh giới lịch, còn fixed interval giữ độ dài cố định.

| Nhu cầu | Lựa chọn |
|---|---|
| Mỗi tháng dương lịch | calendar_interval: month |
| Mỗi quý | calendar_interval: quarter |
| Mỗi tuần theo lịch | calendar_interval: week |
| Mỗi 15 phút chính xác | fixed_interval: 15m |
| Mỗi 6 giờ chính xác | fixed_interval: 6h |
| Mỗi ngày theo lịch địa phương | calendar_interval: day cùng time_zone |
| Cửa sổ đúng 24 giờ | fixed_interval: 24h |

Các giá trị interval được Elasticsearch hỗ trợ phụ thuộc loại calendar/fixed. Không dùng các đơn vị lịch biến thiên như month hoặc year trong fixed_interval.

### 3.2. Các calendar interval thường dùng

Ví dụ:

~~~json
{
  "date_histogram": {
    "field": "createdAt",
    "calendar_interval": "week"
  }
}
~~~

Các đơn vị lịch phổ biến gồm:

- minute
- hour
- day
- week
- month
- quarter
- year

Tên đơn vị dùng trong JSON DSL là dạng singular như day, month, quarter. Hãy kiểm tra phiên bản Elasticsearch nếu dùng đơn vị hoặc cú pháp mới.

### 3.3. fixed_interval

fixed_interval biểu diễn độ dài cố định:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_30_minutes": {
      "date_histogram": {
        "field": "createdAt",
        "fixed_interval": "30m"
      }
    }
  }
}
~~~

Một số đơn vị thường dùng:

| Ký hiệu | Khoảng thời gian |
|---|---|
| ms | Millisecond |
| s | Second |
| m | Minute |
| h | Hour |
| d | Day |

Ví dụ 90m là khoảng cố định 90 phút. 1d là 24 giờ cố định, khác với một ngày lịch địa phương trong vùng có thay đổi DST.

## 4. Timezone trong date_histogram

Timestamp trong Elasticsearch thường được lưu và xử lý theo UTC. Nhưng báo cáo nghiệp vụ thường cần ranh giới theo timezone địa phương.

Ví dụ một hệ thống bán hàng ở Việt Nam muốn nhóm đơn theo ngày địa phương. Có thể cấu hình:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_local_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "Asia/Ho_Chi_Minh"
      }
    }
  }
}
~~~

Với timezone UTC+7, bucket ngày bắt đầu theo nửa đêm địa phương. Mốc key vẫn được biểu diễn dưới dạng epoch UTC tương ứng với thời điểm đó.

Nếu không đặt time_zone, ranh giới bucket mặc định dựa trên UTC. Điều này có thể khiến đơn hàng gần nửa đêm địa phương rơi vào ngày khác so với báo cáo nghiệp vụ.

### 4.1. Timezone không thay đổi timestamp gốc

time_zone chỉ điều khiển cách Elasticsearch làm tròn và diễn giải ranh giới bucket. Nó không sửa timestamp được lưu trong document.

Nếu document được lưu là 2026-11-13T08:00:00Z, đó vẫn là cùng một thời điểm. Khi nhóm theo Asia/Ho_Chi_Minh, thời điểm này tương ứng 15:00 ngày 13/11/2026 tại Việt Nam.

Không cộng thêm 7 giờ vào source rồi đồng thời đặt time_zone Asia/Ho_Chi_Minh; làm vậy có thể gây dịch thời gian hai lần nếu dữ liệu ban đầu đã biểu diễn đúng instant.

### 4.2. DST và calendar interval

Với timezone có daylight saving time, calendar day có thể dài 23 hoặc 25 giờ. Calendar interval xử lý theo lịch và timezone, còn fixed interval giữ khoảng thời gian cố định.

Nếu báo cáo cần "mỗi ngày địa phương", calendar_interval day cùng timezone thường là lựa chọn đúng. Nếu hệ thống cần cửa sổ đúng 24 giờ từ một mốc, fixed_interval phù hợp hơn.

## 5. Offset và format của date_histogram

offset dịch ranh giới bucket so với mốc làm tròn mặc định. Ví dụ muốn bucket ngày bắt đầu lúc 06:00 thay vì nửa đêm, có thể dùng offset:

~~~http
POST /events/_search
{
  "size": 0,
  "aggs": {
    "business_day": {
      "date_histogram": {
        "field": "eventTime",
        "calendar_interval": "day",
        "time_zone": "Asia/Ho_Chi_Minh",
        "offset": "+6h"
      }
    }
  }
}
~~~

Đây là cách nhóm theo ngày vận hành bắt đầu lúc 06:00. Cần hiểu offset được áp dụng cùng quy tắc làm tròn và timezone; hãy kiểm tra các mốc gần ranh giới bằng dữ liệu test.

format cho phép định dạng key_as_string:

~~~json
{
  "date_histogram": {
    "field": "createdAt",
    "calendar_interval": "month",
    "format": "yyyy-MM"
  }
}
~~~

Key số vẫn là mốc thời gian dạng epoch; format chỉ thay đổi chuỗi biểu diễn. Ứng dụng nên dùng key cho xử lý thời gian chính xác và key_as_string cho label hiển thị khi phù hợp.

## 6. Empty bucket: min_doc_count và extended_bounds

Theo mặc định, date_histogram thường chỉ trả bucket có document. Báo cáo theo ngày có thể muốn hiển thị cả ngày không phát sinh đơn hàng với doc_count = 0.

Dùng min_doc_count: 0 cùng extended_bounds:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "Asia/Ho_Chi_Minh",
        "min_doc_count": 0,
        "extended_bounds": {
          "min": "2026-11-01",
          "max": "2026-11-07"
        }
      }
    }
  }
}
~~~

Ý nghĩa:

- min_doc_count: 0 cho phép bucket rỗng được trả về.
- extended_bounds yêu cầu mở rộng phạm vi bucket tới các mốc min/max ngay cả khi không có document ở đó.
- Các bucket trong khoảng có thể xuất hiện với doc_count bằng 0.

extended_bounds không lọc document. Nếu cần chỉ phân tích document trong khoảng thời gian, hãy thêm range query ở phần query.

Ví dụ kết hợp:

~~~http
POST /orders/_search
{
  "size": 0,
  "query": {
    "range": {
      "createdAt": {
        "gte": "2026-11-01T00:00:00+07:00",
        "lt": "2026-11-08T00:00:00+07:00"
      }
    }
  },
  "aggs": {
    "orders_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "Asia/Ho_Chi_Minh",
        "min_doc_count": 0,
        "extended_bounds": {
          "min": "2026-11-01",
          "max": "2026-11-07"
        }
      }
    }
  }
}
~~~

Query range chọn document thuộc khoảng báo cáo. extended_bounds giúp tạo các bucket ngày rỗng bên trong phạm vi mong muốn.

### 6.1. extended_bounds và hard_bounds

Hai tùy chọn có mục đích khác nhau:

| Tùy chọn | Ý nghĩa |
|---|---|
| extended_bounds | Mở rộng bucket range để có thể tạo bucket rỗng tới các mốc chỉ định |
| hard_bounds | Giới hạn bucket được tạo, ngăn bucket nằm ngoài min/max đã chỉ định |

extended_bounds không phải bộ lọc dữ liệu và cũng không bảo đảm ngăn mọi bucket ngoài phạm vi do document thực tế tạo ra. Nếu cần giới hạn phạm vi bucket, dùng hard_bounds phù hợp; nếu cần giới hạn document, dùng query range.

Ví dụ:

~~~json
{
  "date_histogram": {
    "field": "createdAt",
    "calendar_interval": "day",
    "min_doc_count": 0,
    "extended_bounds": {
      "min": "2026-11-01",
      "max": "2026-11-30"
    },
    "hard_bounds": {
      "min": "2026-11-01",
      "max": "2026-11-30"
    }
  }
}
~~~

Hãy cẩn thận với khoảng thời gian rộng và min_doc_count = 0. Nếu yêu cầu tạo bucket cho nhiều năm theo phút, số lượng bucket có thể rất lớn.

## 7. Histogram: chia field số thành các khoảng đều nhau

histogram aggregation chia giá trị số thành bucket có cùng kích thước. Ví dụ nhóm đơn hàng theo tổng tiền, mỗi bucket rộng 100.000 đồng:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_by_amount": {
      "histogram": {
        "field": "totalInCents",
        "interval": 10000000
      }
    }
  }
}
~~~

Trong ví dụ, totalInCents được lưu bằng đơn vị cent. Interval 10.000.000 cent tương đương 100.000 đơn vị tiền nếu quy ước 100 cent = 1 đơn vị tiền.

Histogram tự tính các bucket đều nhau dựa trên interval. Mỗi bucket có key là mốc bucket và doc_count là số document thuộc khoảng đó.

### 7.1. Cách xác định bucket

Về khái niệm, histogram dùng interval và offset để xác định mốc bucket. Với giá trị x, interval i và offset o, bucket key được xác định bằng cách làm tròn xuống theo lưới interval đã dịch:

\[
key = \left\lfloor \frac{x-o}{i} \right\rfloor i + o
\]

Ví dụ interval = 100 và offset = 0:

| Giá trị | Bucket key |
|---:|---:|
| 12 | 0 |
| 99 | 0 |
| 100 | 100 |
| 175 | 100 |
| 250 | 200 |

Các bucket là khoảng nửa mở theo cách hiểu thông thường: [0,100), [100,200), [200,300), ... Giá trị đúng ở ranh giới thuộc bucket bắt đầu tại ranh giới đó.

### 7.2. Offset cho histogram

offset dịch các bucket số:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_buckets": {
      "histogram": {
        "field": "priceInCents",
        "interval": 100000,
        "offset": 50000
      }
    }
  }
}
~~~

Với interval 100.000 và offset 50.000, các bucket bắt đầu ở 50.000, 150.000, 250.000,... theo quy tắc làm tròn của histogram.

Offset hữu ích khi ranh giới nghiệp vụ không bắt đầu tại bội số 0 của interval. Cần kiểm tra giá trị âm và giá trị gần ranh giới nếu dữ liệu có thể chứa chúng.

### 7.3. min_doc_count và empty bucket cho histogram

Tương tự date_histogram, histogram có thể bỏ bucket rỗng theo mặc định. Có thể yêu cầu bucket rỗng:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_buckets": {
      "histogram": {
        "field": "priceInCents",
        "interval": 100000,
        "min_doc_count": 0,
        "extended_bounds": {
          "min": 0,
          "max": 500000
        }
      }
    }
  }
}
~~~

extended_bounds giúp tạo bucket trong khoảng mong muốn, còn min_doc_count = 0 cho phép bucket không có document xuất hiện với doc_count = 0.

Nếu muốn không có bucket vượt khỏi phạm vi đã chỉ định, cân nhắc hard_bounds. Nếu cần chỉ chọn document có giá trong khoảng, thêm range query riêng.

### 7.4. Histogram và giá trị thiếu

Document không có field số thường không được xếp vào bucket. Nếu nghiệp vụ muốn xem document thiếu giá như giá trị mặc định, có thể dùng missing:

~~~json
{
  "histogram": {
    "field": "priceInCents",
    "interval": 100000,
    "missing": 0
  }
}
~~~

Khi đó document không có priceInCents được xem như có giá trị 0 cho aggregation này. Đây chỉ là cách xử lý trong aggregation, không ghi giá trị 0 vào document.

Chỉ dùng missing nếu giá trị thay thế có ý nghĩa nghiệp vụ. Giá thiếu và giá bằng 0 có thể là hai trạng thái khác nhau; gộp chúng có thể làm sai báo cáo.

## 8. Range aggregation: khoảng giá trị do ứng dụng định nghĩa

histogram tạo bucket đều nhau theo interval. Range aggregation cho phép định nghĩa các khoảng không đều, ví dụ:

- Giá dưới 100.000.
- Giá từ 100.000 đến dưới 500.000.
- Giá từ 500.000 đến dưới 2.000.000.
- Giá từ 2.000.000 trở lên.

REST DSL:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_ranges": {
      "range": {
        "field": "priceInCents",
        "ranges": [
          { "to": 10000000 },
          { "from": 10000000, "to": 50000000 },
          { "from": 50000000, "to": 200000000 },
          { "from": 200000000 }
        ]
      }
    }
  }
}
~~~

Mỗi range có thể khai báo from, to hoặc cả hai:

| Range | Ý nghĩa |
|---|---|
| Chỉ có to | Không có giới hạn dưới, nhỏ hơn to |
| from và to | Từ from đến trước to |
| Chỉ có from | Từ from trở lên |

Với range aggregation thông thường, from là biên bao gồm (inclusive), còn to là biên không bao gồm (exclusive). Do đó các khoảng liền kề như [0,100), [100,500) không bị chồng lấn ở ranh giới 100.

### 8.1. Đặt key cho từng range

Có thể đặt key tùy chỉnh:

~~~http
POST /products/_search
{
  "size": 0,
  "aggs": {
    "price_ranges": {
      "range": {
        "field": "priceInCents",
        "keyed": true,
        "ranges": [
          {
            "key": "budget",
            "to": 10000000
          },
          {
            "key": "standard",
            "from": 10000000,
            "to": 50000000
          },
          {
            "key": "premium",
            "from": 50000000
          }
        ]
      }
    }
  }
}
~~~

keyed: true làm response bucket được trả về dưới dạng object theo key thay vì danh sách. Điều này tiện khi ứng dụng cần ánh xạ bucket theo tên nghiệp vụ, nhưng cần kiểm tra kiểu response trong Java client.

Nếu không đặt key, Elasticsearch thường tạo key từ giới hạn range. Đặt key rõ ràng giúp response dễ đọc và ổn định hơn khi ứng dụng tiêu thụ.

### 8.2. Range có thể chồng lấn

Khác với histogram, range aggregation cho phép định nghĩa các khoảng chồng lấn:

~~~json
{
  "range": {
    "field": "priceInCents",
    "ranges": [
      { "key": "under_500k", "to": 50000000 },
      { "key": "under_1m", "to": 100000000 },
      { "key": "premium", "from": 50000000 }
    ]
  }
}
~~~

Một document có giá 300.000 đơn vị tiền có thể thuộc cả under_500k và under_1m. Một document có giá 700.000 có thể thuộc under_1m và premium.

Điều này hữu ích cho các nhóm phân tích chồng lấn, nhưng tổng doc_count của các bucket có thể lớn hơn tổng số document duy nhất. Nếu muốn các nhóm phân chia không chồng lấn, hãy thiết kế from/to liền kề và rõ ràng.

## 9. Date range aggregation: nhóm theo khoảng thời gian nghiệp vụ

Date range aggregation tương tự range nhưng dành cho field date. Nó hữu ích khi khoảng thời gian không đều hoặc theo kỳ nghiệp vụ, chẳng hạn:

- Trước tháng hiện tại.
- Trong tháng hiện tại.
- Trong quý hiện tại.
- Sau ngày bắt đầu chiến dịch.

Ví dụ:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "order_periods": {
      "date_range": {
        "field": "createdAt",
        "time_zone": "Asia/Ho_Chi_Minh",
        "format": "yyyy-MM-dd",
        "ranges": [
          {
            "key": "before_november",
            "to": "2026-11-01"
          },
          {
            "key": "november",
            "from": "2026-11-01",
            "to": "2026-12-01"
          },
          {
            "key": "december_onward",
            "from": "2026-12-01"
          }
        ]
      }
    }
  }
}
~~~

Date range phù hợp khi các mốc ranh giới do nghiệp vụ quyết định. Nếu cần mỗi ngày hoặc mỗi tháng liên tục, date_histogram thường gọn hơn.

Date range có thể dùng date math trong các biểu thức được Elasticsearch hỗ trợ. Với báo cáo tái lập, nên xác định rõ mốc thời gian hoặc truyền khoảng ngày cụ thể thay vì phụ thuộc now mà không ghi nhận thời điểm chạy báo cáo.

### 9.1. Date range và timezone

Khi dùng date_range, hãy xác định format và timezone phù hợp. Chuỗi ngày không có offset có thể được diễn giải theo timezone hoặc quy tắc parser của request. Dùng timestamp có timezone rõ ràng hoặc cấu hình time_zone để tránh ranh giới ngày bị lệch.

Với báo cáo theo tháng tại Việt Nam, khoảng tháng 11 có thể viết dưới dạng:

~~~text
from = 2026-11-01T00:00:00+07:00
to   = 2026-12-01T00:00:00+07:00
~~~

Biên to là exclusive, vì vậy document đúng lúc nửa đêm ngày 1/12 thuộc khoảng tháng 12 chứ không thuộc tháng 11.

## 10. So sánh date_histogram, histogram và range

| Tiêu chí | date_histogram | histogram | range / date_range |
|---|---|---|---|
| Field | Date | Số | Số hoặc date |
| Bucket | Theo lịch hoặc thời lượng cố định | Theo interval số đều nhau | Theo from/to do ứng dụng đặt |
| Ranh giới | Calendar/fixed rounding | Interval và offset | Biên tùy chỉnh |
| Bucket rỗng | min_doc_count, extended_bounds | min_doc_count, extended_bounds | Không tự sinh mọi khoảng ngoài danh sách khai báo |
| Timezone | Có | Không áp dụng | date_range có thể dùng time_zone |
| Chồng lấn | Không theo cách bucket histogram thông thường | Không | Có thể chồng lấn |
| Dùng cho | Báo cáo theo thời gian | Phân bố giá trị số | Phân nhóm theo ngưỡng nghiệp vụ |

Chọn theo câu hỏi cần trả lời:

- Doanh thu theo ngày/tháng: date_histogram.
- Phân bố giá sản phẩm theo các bước đều nhau: histogram.
- Nhóm khách hàng theo các dải chi tiêu định nghĩa sẵn: range.
- Số đơn trong các giai đoạn chiến dịch: date_range.
- Nhóm theo ngày địa phương: date_histogram calendar_interval day cùng time_zone.

## 11. Metric sub-aggregation bên trong bucket

Bucket aggregation thường kết hợp với metric aggregation để tính số liệu cho từng nhóm.

Ví dụ đếm đơn và tính tổng doanh thu theo tháng:

~~~http
POST /orders/_search
{
  "size": 0,
  "query": {
    "term": {
      "status": "PAID"
    }
  },
  "aggs": {
    "orders_by_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month",
        "time_zone": "Asia/Ho_Chi_Minh"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "totalInCents"
          }
        },
        "average_order_value": {
          "avg": {
            "field": "totalInCents"
          }
        },
        "max_order_value": {
          "max": {
            "field": "totalInCents"
          }
        }
      }
    }
  }
}
~~~

Response mỗi bucket có doc_count, revenue.value, average_order_value.value và max_order_value.value.

Có thể lồng nhiều cấp bucket:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "orders_by_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month",
        "time_zone": "Asia/Ho_Chi_Minh"
      },
      "aggs": {
        "by_status": {
          "terms": {
            "field": "status"
          },
          "aggs": {
            "revenue": {
              "sum": {
                "field": "totalInCents"
              }
            }
          }
        }
      }
    }
  }
}
~~~

Kết quả có cấu trúc tháng → trạng thái → doanh thu. Đây là dạng phù hợp cho báo cáo nhiều chiều.

Không lồng quá nhiều tầng bucket trên cardinality cao nếu chưa đánh giá chi phí. Số bucket kết hợp có thể tăng rất nhanh.

## 12. Filter trước khi aggregation

Có thể giới hạn tập document bằng query ở cấp request:

~~~http
POST /orders/_search
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "status": "PAID"
          }
        },
        {
          "range": {
            "createdAt": {
              "gte": "2026-01-01T00:00:00Z",
              "lt": "2027-01-01T00:00:00Z"
            }
          }
        }
      ]
    }
  },
  "aggs": {
    "orders_per_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month"
      }
    }
  }
}
~~~

Query cấp cao giới hạn toàn bộ document tham gia aggregation. Nếu cần nhiều nhóm có điều kiện lọc khác nhau trong cùng một response, có thể dùng filter aggregation hoặc filters aggregation.

Ví dụ nhóm doanh thu theo trạng thái:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "paid_orders": {
      "filter": {
        "term": {
          "status": "PAID"
        }
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "totalInCents"
          }
        }
      }
    },
    "cancelled_orders": {
      "filter": {
        "term": {
          "status": "CANCELLED"
        }
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "totalInCents"
          }
        }
      }
    }
  }
}
~~~

Filter aggregation chỉ tác động đến nhánh aggregation của nó, không loại document khỏi các aggregation nhánh khác.

## 13. Tính tỷ lệ và số liệu tổng hợp theo bucket

Có thể dùng pipeline aggregation trên kết quả bucket, ví dụ tính tỷ lệ hoặc thay đổi giữa các bucket liên tiếp. Một số pipeline phổ biến:

- bucket_script: tính biểu thức từ metric của bucket.
- bucket_selector: loại bucket dựa trên điều kiện.
- derivative: tính mức thay đổi giữa các bucket.
- cumulative_sum: tính tổng tích lũy.
- moving_fn: tính cửa sổ trượt với hàm tùy chỉnh.

Ví dụ tính tổng doanh thu tích lũy theo tháng:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "revenue_by_month": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "month"
      },
      "aggs": {
        "revenue": {
          "sum": {
            "field": "totalInCents"
          }
        },
        "cumulative_revenue": {
          "cumulative_sum": {
            "buckets_path": "revenue"
          }
        }
      }
    }
  }
}
~~~

Pipeline aggregation hoạt động trên kết quả aggregation khác. Nó không thay thế query filter hoặc bucket aggregation ban đầu. Một số pipeline yêu cầu parent bucket aggregation và có quy tắc xử lý bucket rỗng riêng.

## 14. Giới hạn bucket và hiệu năng

Aggregation có thể tạo ra nhiều bucket. Một query nhóm theo từng giây trên vài năm dữ liệu có thể tạo hàng chục triệu khoảng về mặt lý thuyết nếu ép sinh empty bucket.

Các yếu tố cần xem xét:

- Số shard và số index được truy vấn.
- Số bucket tạo ra.
- Số tầng nested aggregation.
- Cardinality của field terms nằm bên trong mỗi bucket.
- Số lượng metric sub-aggregation.
- min_doc_count = 0 và extended_bounds.
- Kích thước response.
- Mức độ song song và tải cluster.

Elasticsearch có giới hạn search.max_buckets cho tổng số bucket trong một search response (mặc định phổ biến là 65.536, có thể cấu hình khác). Khi vượt giới hạn, request có thể bị từ chối.

Một số cách kiểm soát:

- Giới hạn khoảng thời gian bằng query range.
- Chọn interval phù hợp với độ chi tiết cần hiển thị.
- Không tạo bucket rỗng cho phạm vi quá rộng.
- Giảm số tầng aggregation.
- Dùng composite aggregation khi cần duyệt nhiều bucket theo trang.
- Tránh terms aggregation có cardinality cao lồng trong từng date bucket nếu không cần.
- Chỉ trả metric cần thiết.

### 14.1. Histogram không phải cách phân trang bucket lớn

Nếu cần duyệt tất cả bucket theo nhiều chiều với số lượng lớn, composite aggregation thường phù hợp hơn. Composite cho phép paginate qua bucket bằng after_key, nhưng có semantics và cấu hình khác histogram/range.

Không nên tăng search.max_buckets vô hạn chỉ để làm query lớn chạy được. Hãy xem xét lại thiết kế báo cáo và phạm vi dữ liệu.

## 15. Composite aggregation và after_key

Composite aggregation tạo bucket từ một hoặc nhiều nguồn (terms, histogram, date_histogram) và hỗ trợ phân trang. Ví dụ:

~~~http
POST /orders/_search
{
  "size": 0,
  "aggs": {
    "by_month_and_status": {
      "composite": {
        "size": 500,
        "sources": [
          {
            "month": {
              "date_histogram": {
                "field": "createdAt",
                "calendar_interval": "month"
              }
            }
          },
          {
            "status": {
              "terms": {
                "field": "status"
              }
            }
          }
        ]
      }
    }
  }
}
~~~

Nếu response có after_key, request tiếp theo truyền giá trị đó vào after:

~~~json
{
  "composite": {
    "size": 500,
    "after": {
      "month": 1793491200000,
      "status": "PAID"
    },
    "sources": [
      {
        "month": {
          "date_histogram": {
            "field": "createdAt",
            "calendar_interval": "month"
          }
        }
      },
      {
        "status": {
          "terms": {
            "field": "status"
          }
        }
      }
    ]
  }
}
~~~

Giá trị after phải lấy từ after_key response trước, không tự suy ra từ bucket cuối. Giữ nguyên thứ tự và định nghĩa sources giữa các trang.

Composite aggregation phù hợp khi cần duyệt toàn bộ tổ hợp bucket để xuất báo cáo lớn hoặc xử lý batch. Nó không thay thế mọi date_histogram/histogram đơn giản.

## 16. NativeQuery trong Spring Data Elasticsearch

Spring Data Elasticsearch 5.x dùng NativeQuery để truyền aggregation được xây dựng bằng Elasticsearch Java API Client.

Ví dụ date_histogram theo tháng:

~~~java
import co.elastic.clients.elasticsearch._types.aggregations.Aggregation;
import co.elastic.clients.elasticsearch._types.aggregations.CalendarInterval;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Aggregation byMonth = Aggregation.of(a -> a
    .dateHistogram(h -> h
        .field("createdAt")
        .calendarInterval(CalendarInterval.Month)
        .timeZone("Asia/Ho_Chi_Minh")
    )
);

NativeQuery query = NativeQuery.builder()
    .withAggregation("orders_by_month", byMonth)
    .withMaxResults(0)
    .build();

SearchHits<Order> hits =
    operations.search(query, Order.class);
~~~

Trong ví dụ:

- Aggregation là kiểu từ Elasticsearch Java API Client.
- dateHistogram tạo bucket theo tháng.
- calendarInterval(CalendarInterval.Month) dùng tháng lịch.
- timeZone đặt ranh giới theo giờ Việt Nam.
- withAggregation gắn aggregation vào NativeQuery.
- withMaxResults(0) yêu cầu không trả document hits khi chỉ cần aggregation, nếu overload này được hỗ trợ trong phiên bản dự án.

Tên enum, builder method và API đặt max results có thể thay đổi giữa các phiên bản. Hãy kiểm tra Javadoc của Spring Data Elasticsearch và Elasticsearch Java API Client thực tế. Nếu không có withMaxResults(0), dùng tùy chọn size = 0 tương ứng trong query API của phiên bản.

### 16.1. Histogram bằng NativeQuery

Java API Client biểu diễn histogram aggregation qua builder:

~~~java
Aggregation byPrice = Aggregation.of(a -> a
    .histogram(h -> h
        .field("totalInCents")
        .interval(10000000.0)
        .minDocCount(0)
    )
);
~~~

Có thể gắn aggregation vào NativeQuery:

~~~java
NativeQuery query = NativeQuery.builder()
    .withAggregation("orders_by_amount", byPrice)
    .withMaxResults(0)
    .build();
~~~

Kiểu interval là số. Chọn đơn vị phù hợp với cách ứng dụng lưu giá trị. Nếu field lưu cent mà interval được hiểu như đơn vị tiền chính, bucket sẽ rộng sai 100 lần.

### 16.2. Range aggregation bằng NativeQuery

Elasticsearch Java API Client có các kiểu builder cho range aggregation. Cấu trúc Java cụ thể thay đổi theo phiên bản client và loại field; nên đối chiếu Javadoc của Aggregation.Builder, RangeAggregation.Builder và các range expression tương ứng.

Về mặt DSL, cấu hình cần tạo ra dạng:

~~~json
{
  "range": {
    "field": "totalInCents",
    "ranges": [
      { "key": "low", "to": 10000000 },
      { "key": "medium", "from": 10000000, "to": 50000000 },
      { "key": "high", "from": 50000000 }
    ]
  }
}
~~~

Nếu phiên bản client dùng RangeExpression hoặc kiểu range union riêng, hãy dùng đúng kiểu được IDE gợi ý. Không trộn kiểu Range của Java API Client với Range query của Spring Data Criteria.

### 16.3. Kết hợp query filter với aggregation

Có thể thêm query vào NativeQuery cùng aggregation:

~~~java
NativeQuery query = NativeQuery.builder()
    .withQuery(paidOrdersQuery)
    .withAggregation("orders_by_month", byMonth)
    .withMaxResults(0)
    .build();
~~~

Trong đó paidOrdersQuery là query từ Elasticsearch Java API Client, ví dụ bool/filter theo status và createdAt. Query giới hạn document cho aggregation.

## 17. Đọc kết quả aggregation trong Spring Data

SearchHits<T> chứa kết quả hits và aggregation container. Với Spring Data Elasticsearch 5.x, kiểu container thường là ElasticsearchAggregations khi dùng Elasticsearch Java API Client.

Ví dụ dạng đọc thường gặp:

~~~java
SearchHits<Order> hits =
    operations.search(query, Order.class);

ElasticsearchAggregations aggregations =
    (ElasticsearchAggregations) hits.getAggregations();

ElasticsearchAggregation byMonth =
    aggregations.get("orders_by_month");
~~~

Từ aggregation wrapper, có thể lấy aggregate cụ thể của Elasticsearch Java API Client và đọc bucket list tương ứng. Tên accessor và kiểu union aggregate phụ thuộc client version.

Ví dụ khái niệm cho date histogram:

~~~java
// Pseudocode: accessor cụ thể phụ thuộc Elasticsearch Java API Client version.
DateHistogramAggregate dateHistogram =
    byMonth.aggregation().getAggregate().dateHistogram();

for (DateHistogramBucket bucket : dateHistogram.buckets().array()) {
    long timestamp = bucket.key();
    long count = bucket.docCount();
}
~~~

Nếu response dùng keyed buckets thay vì array buckets, cần đọc biến thể keyed tương ứng. Không giả định mọi aggregation đều trả bucket array.

### 17.1. Giữ kiểu aggregation đúng

Elasticsearch Java API Client dùng các union type cho aggregate. Một aggregate có thể là dateHistogram, histogram, range, terms, sum, avg hoặc loại khác. Khi đọc kết quả, phải lấy đúng variant tương ứng với aggregation đã khai báo.

Ví dụ:

- date_histogram → DateHistogramAggregate.
- histogram → HistogramAggregate.
- range → RangeAggregate.
- date_range → DateRangeAggregate.
- sum → SumAggregate.
- avg → AvgAggregate.

Nếu lấy sai variant, code có thể trả null hoặc phát sinh lỗi tùy API. Hãy kiểm tra tên aggregation trong response và kiểu bucket thực tế.

### 17.2. SearchHits hay aggregate-only API?

Nếu cần cả document hits và aggregation, dùng search để nhận SearchHits cùng aggregation metadata.

Nếu chỉ cần aggregation, có thể dùng API aggregate/query phù hợp được Spring Data expose trong phiên bản đang dùng. Chữ ký trả về có thể là AggregationsContainer<?> hoặc wrapper tương ứng. Hãy kiểm tra ElasticsearchOperations của dependency thực tế.

Không tải hàng chục document chỉ để lấy aggregation. Đặt size = 0 hoặc max results = 0 theo API hỗ trợ để giảm response hits khi báo cáo chỉ cần bucket.

## 18. Xây dựng DTO cho báo cáo

Không nên trả trực tiếp các kiểu aggregation nội bộ của Elasticsearch ra API. Hãy map bucket thành DTO:

~~~java
public record TimeBucket(
    long timestamp,
    String label,
    long documentCount,
    double revenue
) {
}
~~~

Ví dụ logic mapping:

~~~java
List<TimeBucket> result = buckets.stream()
    .map(bucket -> new TimeBucket(
        bucket.key(),
        formatBucketLabel(bucket.key()),
        bucket.docCount(),
        readRevenueMetric(bucket)
    ))
    .toList();
~~~

formatBucketLabel và readRevenueMetric là hàm ứng dụng dựa trên kiểu bucket/aggregate cụ thể. Với date_histogram, key thường là epoch milliseconds. Với histogram số, key là mốc số của bucket. Với range, bucket thường chứa key, from và to.

DTO nên biểu đạt đơn vị rõ ràng. Nếu doanh thu lưu cent, field response có thể là revenueInCents hoặc được chuyển đổi sang đơn vị hiển thị theo quy ước API. Không để người dùng hiểu nhầm đơn vị.

## 19. Missing values và document không có field

Các bucket aggregation thường bỏ qua document không có giá trị field được dùng làm nguồn bucket. Ví dụ document không có createdAt không thuộc date_histogram.

Một số aggregation cho phép cấu hình missing để thay thế giá trị thiếu trong phạm vi aggregation:

~~~json
{
  "histogram": {
    "field": "priceInCents",
    "interval": 100000,
    "missing": 0
  }
}
~~~

Với date_histogram, có thể cung cấp giá trị missing theo định dạng ngày phù hợp nếu API hỗ trợ. Tuy nhiên, hãy cân nhắc semantics: ngày thiếu không nhất thiết đồng nghĩa ngày epoch hoặc một ngày mặc định nào đó.

Nếu muốn báo cáo số document thiếu ngày/giá, có thể dùng filter aggregation hoặc missing aggregation riêng để đo số lượng document thiếu field thay vì gộp chúng vào bucket giả.

## 20. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| date_histogram báo field không phải date | Mapping field không phải date hoặc sai field name | Đọc mapping và kiểm tra document |
| Bucket ngày lệch một ngày | Timezone mặc định UTC hoặc ranh giới query sai | Đặt time_zone và dùng timestamp có offset |
| Báo cáo theo tháng lệch ranh giới | Dùng fixed interval thay calendar interval | Dùng calendar_interval month |
| Bucket rỗng không xuất hiện | min_doc_count vẫn là mặc định hoặc extended_bounds thiếu | Đặt min_doc_count: 0 và extended_bounds |
| Bucket ngoài phạm vi vẫn xuất hiện | extended_bounds không phải filter/hard limit | Dùng query range và hard_bounds khi phù hợp |
| Histogram có khoảng sai đơn vị | Interval không cùng đơn vị với field | Kiểm tra field lưu cent, đồng, millisecond... |
| Giá trị đúng ranh giới vào bucket không mong muốn | Hiểu sai quy tắc làm tròn hoặc offset | Kiểm tra interval, offset và các giá trị biên |
| Range bucket bị chồng lấn | from/to được khai báo chồng nhau | Xem lại biên inclusive/exclusive |
| Tổng doc_count lớn hơn tổng document | Range bucket chồng lấn hoặc document thuộc nhiều bucket | Kiểm tra các khoảng đã khai báo |
| Không đọc được aggregation trong Java | Lấy sai wrapper/variant hoặc version khác | Kiểm tra SearchHits.getAggregations và client type |
| Request vượt search.max_buckets | Quá nhiều bucket hoặc nested aggregation | Giảm interval/phạm vi/tầng bucket |
| Aggregation trả số liệu thiếu | Document thiếu field hoặc mapping không có doc values phù hợp | Kiểm tra source, mapping và missing behavior |

## 21. Quy trình thiết kế báo cáo

Khi thiết kế aggregation, xác định lần lượt:

1. Field dùng để nhóm có kiểu date hay numeric?
2. Muốn nhóm theo lịch, khoảng cố định hay ngưỡng nghiệp vụ?
3. Có cần timezone địa phương không?
4. Có cần hiển thị bucket rỗng không?
5. Khoảng thời gian/giá trị nào được đưa vào phân tích?
6. Có cần lọc document trước aggregation không?
7. Trong mỗi bucket cần metric nào: count, sum, avg, min, max?
8. Có cần bucket lồng nhau theo status, category hoặc tenant không?
9. Số bucket dự kiến có vượt giới hạn cluster không?
10. Ứng dụng cần đọc key, key_as_string, from/to hay metric nào?
11. Đơn vị tiền/thời gian đã được ghi rõ trong DTO chưa?
12. Có cần composite aggregation để phân trang bucket không?

Một cấu hình đúng về mặt cú pháp vẫn có thể tạo báo cáo sai nếu timezone, đơn vị hoặc biên khoảng không khớp quy tắc nghiệp vụ.

## 22. Bảng tra cứu nhanh

| Nhu cầu | Aggregation |
|---|---|
| Đếm đơn theo ngày | date_histogram với calendar_interval day |
| Doanh thu theo tháng | date_histogram month + sum |
| Nhóm sự kiện mỗi 15 phút | date_histogram với fixed_interval 15m |
| Nhóm giá theo bước đều | histogram với interval |
| Tạo bucket rỗng | min_doc_count: 0 + extended_bounds |
| Giới hạn bucket được tạo | hard_bounds |
| Nhóm giá theo các ngưỡng riêng | range |
| Nhóm thời gian theo kỳ chiến dịch | date_range |
| Nhóm nhiều chiều theo tháng và status | Nested bucket aggregations |
| Duyệt số lượng bucket rất lớn | composite aggregation + after_key |
| Lọc tập document trước khi nhóm | Query hoặc filter aggregation |
| Tính doanh thu mỗi bucket | sum sub-aggregation |
| Tính giá trị trung bình mỗi bucket | avg sub-aggregation |

date_histogram phù hợp với phân tích theo lịch hoặc thời lượng thời gian cố định; histogram chia giá trị số thành các bucket đều nhau; range/date_range dùng các biên do nghiệp vụ định nghĩa và có thể chồng lấn. Hãy chọn interval đúng với ý nghĩa lịch hay độ dài cố định, đặt timezone và offset rõ ràng, phân biệt extended_bounds với query filter/hard_bounds, và kết hợp metric sub-aggregation để tạo báo cáo. Trong Spring Data Elasticsearch, dùng NativeQuery với aggregation của Elasticsearch Java API Client, đọc đúng aggregation wrapper/variant theo phiên bản và giới hạn số bucket để giữ request trong khả năng vận hành của cluster.

