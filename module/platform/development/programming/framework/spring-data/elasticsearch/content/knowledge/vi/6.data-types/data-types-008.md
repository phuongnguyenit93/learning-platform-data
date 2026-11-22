# Flattened và giới hạn khi cấu trúc thuộc tính thay đổi

## 1. Vấn đề khi object có cấu trúc thay đổi liên tục

Trong Elasticsearch, một JSON object thông thường thường được ánh xạ thành kiểu `object`. Mỗi thuộc tính con có thể trở thành một field riêng trong mapping.

Ví dụ document sự kiện:

~~~json
{
  "id": "evt-100",
  "message": "Service started",
  "attributes": {
    "host": "api-01",
    "region": "ap-southeast-1",
    "environment": "production"
  }
}
~~~

Nếu `attributes` dùng mapping object với dynamic mapping mặc định, Elasticsearch sẽ tạo mapping cho các key như `attributes.host`, `attributes.region` và `attributes.environment` khi nhận document.

Điều này phù hợp khi cấu trúc dữ liệu đã biết và ổn định. Nhưng nhiều ứng dụng có metadata do người dùng, dịch vụ bên ngoài hoặc từng loại sự kiện tự định nghĩa. Document tiếp theo có thể có những key hoàn toàn khác:

~~~json
{
  "id": "evt-101",
  "message": "Payment processed",
  "attributes": {
    "merchant": "shop-42",
    "payment_provider": "gateway-x",
    "retry_count": 2,
    "risk_level": "low",
    "device": {
      "type": "mobile",
      "os": "Android"
    }
  }
}
~~~

Sau một thời gian, hàng nghìn key khác nhau có thể xuất hiện. Elasticsearch phải tạo thêm mapping cho từng key và các field con. Khi số lượng field tăng cao, cluster phải quản lý mapping lớn hơn, tốn tài nguyên bộ nhớ và có thể chạm giới hạn tổng số field của index. Hiện tượng này thường được gọi là **mapping explosion**.

Kiểu field `flattened` được thiết kế cho tình huống object có nhiều key không biết trước hoặc thay đổi thường xuyên. Nó ánh xạ toàn bộ object thành một field duy nhất và lập chỉ mục các giá trị lá theo cách gần với `keyword`. Nhờ đó, key mới có thể xuất hiện trong dữ liệu mà không làm mapping phát sinh một field riêng cho mỗi key.

## 2. Flattened là gì?

`flattened` là một kiểu mapping của Elasticsearch dành cho JSON object có cấu trúc linh hoạt. Thay vì ánh xạ mỗi thuộc tính con thành một field độc lập, Elasticsearch coi toàn bộ object là một field và lập chỉ mục các giá trị lá dưới dạng keyword.

Mapping:

~~~json
{
  "mappings": {
    "properties": {
      "message": {
        "type": "text"
      },
      "attributes": {
        "type": "flattened"
      }
    }
  }
}
~~~

Document:

~~~json
{
  "message": "Service started",
  "attributes": {
    "host": "api-01",
    "region": "ap-southeast-1",
    "environment": "production",
    "retry_count": 2,
    "device": {
      "type": "mobile",
      "os": "Android"
    }
  }
}
~~~

Ở đây, mapping chỉ cần một field `attributes`. Các key `host`, `region`, `environment`, `retry_count`, `device.type` và `device.os` không tạo ra các mapping field riêng theo cơ chế dynamic mapping thông thường.

Elasticsearch vẫn lập chỉ mục các giá trị để có thể tìm kiếm theo key hoặc trên toàn object. Các key lồng nhau được truy cập bằng đường dẫn có dấu chấm, ví dụ `attributes.device.type`.

Điểm quan trọng là `flattened` không biến object thành một chuỗi JSON duy nhất. Elasticsearch tách các giá trị lá và lưu chỉ mục theo key tương ứng, nhưng coi các giá trị đó như keyword. Cấu trúc object ban đầu vẫn có thể được đọc từ `_source` theo cách lưu source của index.

## 3. Cách flattened xử lý key và value

Giả sử document có object:

~~~json
{
  "attributes": {
    "priority": "urgent",
    "release": ["v1.2.5", "v1.3.0"],
    "timestamp": {
      "created": 1541458026,
      "closed": 1541457010
    }
  }
}
~~~

Có thể hình dung các giá trị lá được lập chỉ mục theo những đường dẫn:

~~~text
attributes.priority          -> "urgent"
attributes.release           -> "v1.2.5", "v1.3.0"
attributes.timestamp.created -> "1541458026"
attributes.timestamp.closed  -> "1541457010"
~~~

Tên key và value đều tham gia vào cách Elasticsearch tổ chức dữ liệu để tìm kiếm. Các giá trị được coi là chuỗi keyword, không tự động phân tích theo analyzer của text và không tự động chuyển số thành kiểu số hay ngày thành kiểu date.

Có hai cách tìm kiếm thường gặp:

- Truy vấn field gốc để tìm một giá trị ở bất kỳ key nào trong object.
- Truy vấn một key cụ thể bằng đường dẫn có dấu chấm.

Ví dụ truy vấn trên field gốc:

~~~json
{
  "query": {
    "term": {
      "attributes": "urgent"
    }
  }
}
~~~

Truy vấn này tìm document có giá trị `urgent` ở một vị trí bất kỳ trong object `attributes`.

Truy vấn theo key cụ thể:

~~~json
{
  "query": {
    "term": {
      "attributes.priority": "urgent"
    }
  }
}
~~~

Truy vấn này chỉ tìm giá trị `urgent` tại key `priority` trong object `attributes`.

Với object lồng nhau, có thể dùng đường dẫn đầy đủ:

~~~json
{
  "query": {
    "term": {
      "attributes.device.type": "mobile"
    }
  }
}
~~~

Đường dẫn key giúp phân biệt các giá trị giống nhau nằm ở những vị trí khác nhau. Ví dụ `attributes.owner` và `attributes.reviewer` có thể cùng chứa tên người nhưng vẫn là hai key riêng biệt.

## 4. Khai báo flattened trong Spring Data Elasticsearch

Spring Data Elasticsearch có kiểu `FieldType.Flattened` trong annotation `@Field`. Một thuộc tính Java dạng `Map<String, Object>` phù hợp để biểu diễn object có key/value linh hoạt.

Ví dụ entity:

~~~java
import java.util.Map;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "events")
public class EventDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String message;

    @Field(type = FieldType.Flattened)
    private Map<String, Object> attributes;

    // Constructors, getters và setters
}
~~~

`@Field(type = FieldType.Flattened)` yêu cầu Spring Data tạo mapping flattened cho thuộc tính `attributes` khi mapping được tạo từ metadata entity.

Ứng dụng có thể gán các key khác nhau theo loại sự kiện:

~~~java
import java.util.HashMap;

Map<String, Object> attributes = new HashMap<>();
attributes.put("host", "api-01");
attributes.put("region", "ap-southeast-1");
attributes.put("retry_count", 2);

EventDocument event = new EventDocument();
event.setId("evt-100");
event.setMessage("Service started");
event.setAttributes(attributes);
~~~

Document được gửi đến Elasticsearch có dạng JSON object:

~~~json
{
  "id": "evt-100",
  "message": "Service started",
  "attributes": {
    "host": "api-01",
    "region": "ap-southeast-1",
    "retry_count": 2
  }
}
~~~

Spring Data xử lý việc chuyển đổi giữa map Java và document. Elasticsearch mapping mới quyết định cách các key/value trong object được lập chỉ mục.

Lưu ý: chỉ khai báo annotation trong entity không tự sửa mapping của index đã tồn tại. Nếu index đã được tạo với `attributes` kiểu `object`, cần tạo index mới hoặc thực hiện quy trình migration phù hợp để thay mapping thành `flattened`. Hãy kiểm tra mapping thực tế sau khi tạo index.

## 5. Truy vấn flattened bằng Query DSL

Vì các giá trị được lập chỉ mục theo dạng keyword, flattened hỗ trợ các truy vấn cơ bản như `term`, `terms`, `terms_set`, `prefix`, `wildcard`, `regexp`, `fuzzy`, `range`, `match`, `multi_match`, `query_string`, `simple_query_string` và `exists`.

### Tìm một giá trị chính xác

~~~json
{
  "query": {
    "term": {
      "attributes.environment": "production"
    }
  }
}
~~~

`term` phù hợp khi cần so khớp giá trị keyword đã được lập chỉ mục.

### Tìm một trong nhiều giá trị

~~~json
{
  "query": {
    "terms": {
      "attributes.region": [
        "ap-southeast-1",
        "ap-northeast-1"
      ]
    }
  }
}
~~~

Truy vấn tìm document có region thuộc một trong các giá trị được cung cấp.

### Tìm theo tiền tố

~~~json
{
  "query": {
    "prefix": {
      "attributes.host": "api-"
    }
  }
}
~~~

Truy vấn này có thể tìm các host bắt đầu bằng `api-`.

### Kiểm tra key có giá trị được lập chỉ mục

~~~json
{
  "query": {
    "exists": {
      "field": "attributes.retry_count"
    }
  }
}
~~~

`exists` hữu ích khi key có thể xuất hiện ở một số document nhưng không xuất hiện ở các document khác.

Có thể truy vấn field gốc nếu chỉ quan tâm một giá trị xuất hiện ở đâu đó trong object. Tuy nhiên, truy vấn theo key cụ thể thường rõ nghĩa hơn và giảm kết quả ngoài ý muốn.

## 6. Giới hạn quan trọng: mọi giá trị đều là keyword

Đây là giới hạn cần nhớ nhất khi chọn flattened. Các giá trị trong object được lập chỉ mục như chuỗi keyword, kể cả khi JSON ban đầu chứa số, boolean hoặc timestamp.

Ví dụ document:

~~~json
{
  "attributes": {
    "retry_count": 10,
    "enabled": true,
    "created_at": 1735689600000
  }
}
~~~

Với flattened mặc định:

- `retry_count` được xem như chuỗi `"10"`.
- `enabled` được xem như chuỗi `"true"`.
- `created_at` được xem như chuỗi biểu diễn số timestamp.

Elasticsearch không tự hiểu `retry_count` là integer, `enabled` là boolean hoặc `created_at` là date. Vì vậy, các truy vấn range trên flattened cũng so sánh giá trị theo thứ tự từ vựng của chuỗi, không phải thứ tự số học hay thời gian.

Ví dụ, so sánh chuỗi `"100"` và `"20"` theo thứ tự từ vựng có thể cho kết quả khác so với so sánh hai số 100 và 20. Do đó, không dùng range query trên flattened để kiểm tra ngưỡng số hoặc khoảng thời gian nếu chưa có kiểu dữ liệu chuyên biệt.

Ví dụ sau không có semantics số học như field integer:

~~~json
{
  "query": {
    "range": {
      "attributes.retry_count": {
        "gte": "10",
        "lte": "20"
      }
    }
  }
}
~~~

Nếu cần lọc số lượng retry từ 10 đến 20 theo giá trị số, nên ánh xạ key đó thành field `integer` hoặc `long` riêng, hoặc dùng một thuộc tính số có mapping rõ ràng.

Tương tự, nếu cần truy vấn ngày tháng, IP, tọa độ địa lý hoặc giá trị range, hãy dùng field type chuyên biệt. Flattened phù hợp với metadata linh hoạt mà các thao tác chủ yếu là tìm kiếm giá trị dạng keyword.

## 7. Sort và aggregation trên flattened

Flattened hỗ trợ sắp xếp và các aggregation dạng keyword như `terms`, nhưng các thao tác này vẫn làm việc trên giá trị keyword.

Ví dụ aggregation đếm số document theo môi trường:

~~~json
{
  "size": 0,
  "aggs": {
    "environments": {
      "terms": {
        "field": "attributes.environment"
      }
    }
  }
}
~~~

Ví dụ sắp xếp theo một key:

~~~json
{
  "sort": [
    {
      "attributes.region": {
        "order": "asc"
      }
    }
  ]
}
~~~

Với giá trị số hoặc ngày đang được lưu theo flattened mặc định, thứ tự sort là thứ tự từ vựng. Không nên dùng kết quả đó như thứ tự số học hoặc thời gian.

Nếu cần sort theo số, date hoặc IP, hãy định nghĩa key quan trọng thành typed sub-field hoặc field riêng có mapping phù hợp.

Một số giới hạn khác:

- Không hỗ trợ highlighting trên flattened field.
- Không thể dùng wildcard để tham chiếu tên key trong đường dẫn field, ví dụ không thể truy vấn `attributes.time*` như một tên field động.
- Các key phải được chỉ rõ khi truy vấn sub-field.
- Không hỗ trợ mapping parameter `store` cho flattened field.
- Các chức năng nâng cao của field type chuyên biệt không tự động có trên flattened.

Vì vậy, flattened có thể đáp ứng tìm kiếm và thống kê đơn giản trên metadata, nhưng không thay thế toàn bộ khả năng của các field được định kiểu rõ ràng.

## 8. Mapped sub-fields: giữ typed mapping cho các key quan trọng

Không phải mọi key trong object đều cần xử lý giống nhau. Một số key có thể thay đổi linh hoạt, nhưng một số key khác lại có ý nghĩa nghiệp vụ ổn định và cần truy vấn theo kiểu dữ liệu chuyên biệt.

Elasticsearch hỗ trợ khai báo `properties` bên trong mapping flattened để ánh xạ một số key cụ thể thành typed sub-field. Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "attributes": {
        "type": "flattened",
        "properties": {
          "host.name": {
            "type": "keyword"
          },
          "host.ip": {
            "type": "ip"
          },
          "retry_count": {
            "type": "long"
          },
          "created_at": {
            "type": "date"
          }
        }
      }
    }
  }
}
~~~

Trong ví dụ:

- `host.name` là keyword field.
- `host.ip` là IP field, hỗ trợ truy vấn IP-aware.
- `retry_count` là long field, hỗ trợ range số học.
- `created_at` là date field, hỗ trợ truy vấn thời gian.

Các key đã được khai báo trong `properties` được lập chỉ mục thông qua typed sub-field tương ứng và không còn được xử lý như giá trị flattened thông thường. Những key khác vẫn dùng cơ chế keyword mặc định của flattened.

Ví dụ document:

~~~json
{
  "attributes": {
    "host": {
      "name": "web-1",
      "ip": "192.168.1.10"
    },
    "retry_count": 12,
    "created_at": "2026-11-13T09:30:00Z",
    "region": "ap-southeast-1"
  }
}
~~~

Truy vấn range số học trên key đã được ánh xạ:

~~~json
{
  "query": {
    "range": {
      "attributes.retry_count": {
        "gte": 10,
        "lte": 20
      }
    }
  }
}
~~~

Truy vấn IP:

~~~json
{
  "query": {
    "term": {
      "attributes.host.ip": "192.168.1.10"
    }
  }
}
~~~

Mapped sub-fields giúp kết hợp object linh hoạt với một số key có kiểu dữ liệu rõ ràng. Tuy nhiên, đây không phải cách biến mọi key động thành typed field. Chỉ những key đã biết và khai báo trước mới có typed mapping. Các typed sub-field chỉ được dùng cho kiểu field lá; không thể khai báo `object`, `nested` hoặc một `flattened` khác bên trong `properties` này.

Trong Spring Data Elasticsearch, `@Field(type = FieldType.Flattened)` khai báo field gốc. Nếu cần cấu hình chi tiết `properties` cho các key bên trong flattened, có thể quản lý mapping bằng JSON mapping resource hoặc cơ chế tạo mapping phù hợp của ứng dụng. Ví dụ dùng annotation `@Mapping` để nạp mapping từ classpath:

~~~java
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Mapping;

@Document(indexName = "events")
@Mapping(mappingPath = "/mappings/events-mapping.json")
public class EventDocument {
    // Entity fields
}
~~~

Trong cách triển khai này, file mapping phải chứa đầy đủ mapping của index, bao gồm field `attributes` kiểu flattened và các typed sub-fields đã chọn. `@Mapping` cung cấp mapping resource cho quá trình tạo mapping của entity. Nếu index được provisioning hoàn toàn bên ngoài và ứng dụng đặt `createIndex = false`, hãy triển khai file mapping bằng công cụ provisioning riêng; annotation không tự cập nhật index đã tồn tại. Khi dùng mapping resource thay cho mapping sinh từ annotation, cần bảo đảm cấu hình resource và metadata entity nhất quán.

## 9. Flattened, object và nested khác nhau như thế nào?

Ba kiểu này phục vụ những mục đích khác nhau:

| Tiêu chí | `object` | `nested` | `flattened` |
|---|---|---|---|
| Mục đích | JSON object có cấu trúc field tương đối rõ | Mảng object cần giữ quan hệ giữa các thuộc tính của từng phần tử | Object có số lượng key lớn hoặc khó dự đoán |
| Mapping | Field con được ánh xạ riêng | Field con được ánh xạ riêng trong nested scope | Toàn object là một field |
| Key mới | Dynamic mapping có thể tạo field mới | Dynamic mapping có thể tạo field con mới | Không tạo mapping field riêng cho mỗi key |
| Kiểu value | Có thể dùng text, keyword, số, date, IP... | Có thể dùng các kiểu field chuyên biệt | Mặc định các giá trị lá là keyword |
| Quan hệ giữa các object trong mảng | Có thể bị làm phẳng và mất tương quan | Được giữ trong từng nested document | Không phải mô hình thay thế nested để giữ quan hệ object |
| Query | Query field thông thường | Cần nested query | Query cơ bản trên root hoặc key path |
| Phù hợp | Schema tương đối ổn định | Các phần tử có nhiều thuộc tính phải khớp cùng nhau | Metadata, labels, attributes linh hoạt |

Ví dụ lựa chọn:

- Hồ sơ khách hàng có `name`, `birthDate`, `status`: dùng các field riêng với kiểu rõ ràng.
- Danh sách biến thể sản phẩm có `color`, `size`, `stock` và cần lọc các điều kiện trên cùng một biến thể: cân nhắc `nested`.
- Metadata sự kiện có hàng trăm key do nhiều dịch vụ tự gửi: cân nhắc `flattened`.
- Một số key trong metadata cần lọc số học hoặc IP: dùng typed sub-fields hoặc tách chúng thành field riêng.

Không nên dùng flattened cho mọi object chỉ để tránh mapping explosion. Nếu cấu trúc dữ liệu đã ổn định, mapping object có kiểu rõ ràng giúp Elasticsearch thực hiện nhiều loại truy vấn và phân tích hơn.

## 10. Dynamic mapping: object có thể được kiểm soát theo cách khác

Khi dùng object, có thể điều chỉnh dynamic mapping để kiểm soát key mới.

Ví dụ:

~~~json
{
  "mappings": {
    "properties": {
      "attributes": {
        "type": "object",
        "dynamic": false
      }
    }
  }
}
~~~

Với `dynamic: false`, các key chưa được khai báo không được thêm vào mapping và không được lập chỉ mục, nhưng vẫn có thể được giữ trong `_source`. Cách này phù hợp nếu ứng dụng chỉ cần lưu lại metadata để đọc về sau, không cần tìm kiếm theo key mới.

Nếu đặt `dynamic: strict`, document có field mới không được phép theo mapping sẽ bị từ chối khi lập chỉ mục. Cách này phù hợp khi schema phải được kiểm soát nghiêm ngặt.

So sánh:

- `object` với dynamic mặc định: key mới có thể tạo mapping field mới và được truy vấn theo kiểu được suy luận.
- `object` với `dynamic: false`: key mới được giữ trong source nhưng không được lập chỉ mục.
- `object` với `dynamic: strict`: key không được khai báo có thể khiến document bị từ chối.
- `flattened`: key mới vẫn được lập chỉ mục theo cơ chế keyword mà không tạo mapping field riêng cho từng key.

Vì vậy, chọn flattened hay dynamic false phụ thuộc vào việc có cần tìm kiếm trên những key chưa biết trước hay không.

## 11. Giới hạn về cấu trúc và quan hệ dữ liệu

Flattened giúp xử lý số lượng key lớn, nhưng không giữ đầy đủ semantics của một mô hình object có kiểu dữ liệu.

### Không thay thế nested cho quan hệ giữa phần tử

Giả sử object có danh sách các biến thể:

~~~json
{
  "variants": [
    {
      "color": "black",
      "stock": 0
    },
    {
      "color": "white",
      "stock": 12
    }
  ]
}
~~~

Nếu mục tiêu là tìm một biến thể vừa có màu đen vừa còn hàng, cần giữ quan hệ giữa `color` và `stock` trong cùng một phần tử. Flattened không phải lựa chọn thay thế cho nested query trong trường hợp này.

Nếu dữ liệu có quan hệ phức tạp, hãy thiết kế bằng nested hoặc tách thành document riêng tùy cách truy vấn.

### Không bảo đảm semantics của kiểu dữ liệu gốc

Một số key hôm nay chứa số, ngày hoặc boolean, nhưng ngày mai có thể nhận chuỗi do một nguồn dữ liệu khác gửi tới. Flattened chấp nhận các giá trị này dưới dạng keyword, nhưng điều đó cũng có nghĩa ứng dụng phải tự quản lý quy ước giá trị.

Ví dụ `created_at` có lúc là epoch millis, có lúc là chuỗi ISO-8601. Nếu cần truy vấn thời gian chính xác, hãy chuẩn hóa dữ liệu trước khi ghi và ánh xạ thành date field riêng hoặc typed sub-field.

### Độ sâu object có giới hạn

Flattened có tham số `depth_limit` để giới hạn độ sâu object lồng nhau. Mặc định hiện tại là 20 cấp. Nếu dữ liệu đầu vào có cấu trúc lồng quá sâu, Elasticsearch có thể từ chối document. Không nên xem flattened là nơi chứa một JSON tree sâu vô hạn.

### Mảng giá trị lá và synthetic source

Trong cấu hình `_source` thông thường, Elasticsearch giữ JSON source gốc theo cách lưu source của index. Với synthetic `_source`, việc tái tạo mảng giá trị lá của flattened có thể sắp xếp và loại bỏ giá trị trùng hoặc null theo cấu hình mặc định. Mapping parameter `preserve_leaf_arrays` có thể điều chỉnh chế độ này, nhưng giữ thứ tự, phần tử trùng và null có thể làm tăng chi phí lưu doc values.

Nếu thứ tự và số lần xuất hiện của từng phần tử mảng có ý nghĩa nghiệp vụ, hãy kiểm tra chính xác chế độ `_source` đang dùng và cân nhắc lưu một biểu diễn riêng phù hợp.

## 12. Thiết kế entity và mapping trong ứng dụng Spring

Một cách tổ chức thực tế là tách field nghiệp vụ ổn định khỏi metadata linh hoạt.

~~~java
import java.time.Instant;
import java.util.Map;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "events")
public class EventDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String serviceName;

    @Field(type = FieldType.Date)
    private Instant occurredAt;

    @Field(type = FieldType.Text)
    private String message;

    @Field(type = FieldType.Flattened)
    private Map<String, Object> attributes;

    // Constructors, getters và setters
}
~~~

Trong thiết kế này:

- `serviceName` là field keyword riêng vì thường cần lọc chính xác hoặc aggregation.
- `occurredAt` là date riêng để range và sort theo thời gian có semantics đúng.
- `message` là text để full-text search.
- `attributes` chứa metadata linh hoạt như host, region, deployment, labels hoặc thông tin riêng của từng dịch vụ.

Khi một key trong attributes trở nên quan trọng và cần truy vấn theo kiểu dữ liệu chuyên biệt, có thể nâng nó thành field rõ ràng hoặc khai báo typed sub-field trong mapping.

Đây là cách tiến hóa schema thường gặp: ban đầu key chỉ là metadata linh hoạt, sau đó một số key được sử dụng rộng rãi và trở thành thuộc tính nghiệp vụ có kiểu rõ ràng. Không nhất thiết phải giữ mãi mọi dữ liệu trong flattened.

## 13. Quy trình lựa chọn và triển khai flattened

Có thể áp dụng theo các bước sau:

1. **Xác định độ ổn định của schema.** Liệt kê field nào có cấu trúc cố định và field nào có key thay đổi theo nguồn dữ liệu.
2. **Giữ field nghiệp vụ riêng.** Các thuộc tính cần full-text, numeric range, date range, sort hoặc aggregation có kiểu chuyên biệt nên được ánh xạ riêng.
3. **Chọn object hay flattened.** Dùng object khi schema đã biết; dùng flattened khi cần lập chỉ mục các key động mà không tạo mapping mới cho từng key.
4. **Chọn kiểu Java.** Dùng `Map<String, Object>` cho object linh hoạt và đánh dấu bằng `@Field(type = FieldType.Flattened)`.
5. **Khai báo typed sub-fields nếu cần.** Xác định trước các key quan trọng như IP, date, long hoặc keyword và cấu hình mapping cho chúng.
6. **Tạo index với mapping đúng.** Không dựa vào annotation để tự sửa mapping của index đã tồn tại.
7. **Kiểm tra dữ liệu thực tế.** Thử key lồng nhau, key không xuất hiện, giá trị null, mảng, số và chuỗi.
8. **Kiểm tra query.** Xác nhận term, prefix, range, sort và aggregation có semantics đúng với dữ liệu.
9. **Theo dõi số lượng field mapping.** Đảm bảo các key linh hoạt không tiếp tục làm mapping tăng không kiểm soát.
10. **Nâng cấp schema có chủ đích.** Khi một key trở thành dữ liệu quan trọng, chuyển nó thành typed sub-field hoặc field riêng, sau đó migration/reindex nếu mapping hiện tại cần thay đổi.

## 14. Những lỗi thường gặp

**Dùng flattened cho dữ liệu cần range số học.** Giá trị số được xử lý như chuỗi keyword; range và sort có thể cho kết quả từ vựng. Dùng typed sub-field hoặc field số riêng.

**Cho rằng key động có kiểu tự động.** Flattened không suy luận `long`, `date`, `boolean` hay `ip` cho từng key. Nếu cần typed semantics, phải khai báo mapping riêng.

**Dùng flattened để giữ quan hệ giữa các object.** Flattened giải quyết mapping linh hoạt, không thay thế nested cho các truy vấn cần điều kiện cùng thuộc một object con.

**Truy vấn field gốc khi cần một key cụ thể.** Query root có thể tìm giá trị ở bất kỳ key nào. Dùng đường dẫn như `attributes.region` khi điều kiện thuộc một key cụ thể.

**Kỳ vọng analyzer hoặc highlighting như text.** Giá trị flattened không được phân tích như text thông thường và không hỗ trợ highlighting.

**Để mọi dữ liệu vào một Map.** Các field nghiệp vụ quan trọng sẽ mất lợi ích của mapping chuyên biệt nếu chỉ được lưu trong flattened. Hãy tách field ổn định và metadata động.

**Chỉ sửa annotation sau khi index đã tạo.** Mapping hiện tại không tự chuyển từ object sang flattened. Tạo index mới và reindex khi cần thay kiểu mapping.

**Không kiểm tra dữ liệu từ nhiều nguồn.** Cùng một key có thể được gửi dưới nhiều định dạng. Cần thống nhất quy ước dữ liệu trước khi lập chỉ mục.

## Kết luận

`flattened` là lựa chọn phù hợp cho JSON object có nhiều key không biết trước hoặc thay đổi thường xuyên. Nó ánh xạ toàn object thành một field, lập chỉ mục các giá trị lá theo dạng keyword và giúp tránh mapping explosion khi metadata phát triển.

Đổi lại, các giá trị mặc định không còn semantics chuyên biệt của số, ngày, boolean hoặc IP; truy vấn range và sort theo giá trị flattened là theo thứ tự từ vựng, không phải số học. Flattened cũng không thay thế nested khi cần giữ quan hệ giữa các object trong mảng và không cung cấp toàn bộ tính năng của text field.

Trong Spring Data Elasticsearch, có thể dùng `Map<String, Object>` cùng `@Field(type = FieldType.Flattened)`. Thiết kế tốt thường giữ các field nghiệp vụ ổn định với mapping chuyên biệt, còn flattened dành cho metadata linh hoạt. Khi một key động trở thành quan trọng, hãy nâng nó thành typed sub-field hoặc field riêng theo nhu cầu truy vấn.

## Tài liệu tham khảo

- [Elasticsearch — Flattened field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/flattened)
- [Elasticsearch — Field data types](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/field-data-types)
- [Spring Data Elasticsearch — Object Mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch — Field annotation API](https://docs.spring.io/spring-data/elasticsearch/docs/current/api/org/springframework/data/elasticsearch/annotations/Field.html)
