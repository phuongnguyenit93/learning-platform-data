# Tạo collection Time Series bằng `@TimeSeries` hoặc `CollectionOptions`

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao cần **tạo Time Series collection trước khi ghi dữ liệu** thay vì chỉ khai báo một entity Java.
- Sử dụng `@TimeSeries` với `MongoTemplate.createCollection(Entity.class)`.
- Sử dụng `CollectionOptions.timeSeries(...)` khi cần khai báo collection bằng tên và cấu hình trong mã nguồn.
- Chọn `timeField`, `metaField`, `granularity`, thời gian lưu trữ (TTL), kiểm tra cấu hình đã được MongoDB áp dụng và xử lý một số lỗi thường gặp.

Bài học nằm trong phần **Time series** của **SPRING_DATA_MONGODB**: sử dụng Spring Data MongoDB để kết nối, ánh xạ document và thao tác MongoDB qua `MongoTemplate` hoặc repository. Trọng tâm là **khâu tạo collection đúng kiểu Time Series** để các thao tác ghi, truy vấn, aggregation, index và giám sát hiệu năng ở những bước tiếp theo có nền tảng chính xác.

## 1. Time Series collection khác collection thường ở đâu?

Một hệ thống giám sát kho lạnh nhận dữ liệu như sau sau mỗi 10 giây:

```json
{
  "observedAt": "2026-11-20T02:10:00Z",
  "sensor": { "deviceId": "sensor-17", "site": "warehouse-a" },
  "temperatureC": 3.8
}
```

Mỗi phép đo gắn với một mốc thời gian và thông tin nhận diện nguồn đo. MongoDB tối ưu Time Series collection cho kiểu dữ liệu này bằng cách tổ chức các phép đo thành **bucket**. Khi đọc theo khoảng thời gian và theo nguồn đo, bộ máy lưu trữ có thể xử lý hiệu quả hơn so với cách lưu sự kiện rời rạc trong một collection thông thường.

MongoDB 5.0 giới thiệu Time Series collection; cần MongoDB và `featureCompatibilityVersion` hỗ trợ tính năng này (từ 5.0). Điểm cốt lõi: **loại collection được quyết định tại thời điểm tạo collection**. Chỉ viết `@TimeSeries` lên lớp Java **không tự biến** một collection thường đã tồn tại thành Time Series. Nếu ghi dữ liệu trước khi tạo collection đúng cách, quá trình tự tạo collection ngầm có thể khiến bạn có collection thường.

Các tham số chính:

| Tham số | Bắt buộc? | Ý nghĩa và lựa chọn |
| --- | --- | --- |
| `timeField` | Có | Trường chứa mốc thời gian, ví dụ `observedAt`. Dữ liệu trên MongoDB phải là **BSON Date**; trong Java có thể dùng `Instant`. |
| `metaField` | Không | Trường nhận diện chuỗi đo, ví dụ `sensor` gồm `deviceId`, `site`. Nên tương đối ổn định theo thời gian. |
| `granularity` | Không | `SECONDS`, `MINUTES`, `HOURS` trong Spring Data; chọn gần với tần suất đo. Bỏ qua để máy chủ dùng mặc định. |
| `expireAfter` / `expireAfterSeconds` | Không | Chính sách tự loại bỏ phép đo cũ theo thời gian; cấu hình trong Spring Data được chuyển sang tùy chọn TTL phía MongoDB. |

**Thiết kế metadata:** Nếu hai phép đo liên tiếp đến từ cùng thiết bị và vị trí, nên đặt thông tin nhận diện vào `sensor`, còn giá trị biến động như `temperatureC` là trường phép đo. Không đưa thời gian hoặc giá trị thay đổi từng lần đo vào metadata nếu không có lý do cụ thể, vì nó làm giảm khả năng gom phép đo vào bucket hiệu quả.

## 2. Cách 1 — Khai báo `@TimeSeries` trên entity

`@TimeSeries` thuộc package `org.springframework.data.mongodb.core.mapping`. Nó chỉ rõ collection đích và các thông số Time Series gắn với kiểu dữ liệu Java. `timeField` là thuộc tính bắt buộc của annotation.

Ví dụ sử dụng Java 17+ (record `SensorMeta`) và Spring Data MongoDB:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.TimeSeries;
import org.springframework.data.mongodb.core.timeseries.Granularity;

@TimeSeries(
    collection = "sensor_readings",
    timeField = "observedAt",
    metaField = "sensor",
    granularity = Granularity.SECONDS,
    expireAfter = "30d"
)
public class SensorReading {

    @Id
    private String id;
    private Instant observedAt;
    private SensorMeta sensor;
    private double temperatureC;

    protected SensorReading() {
        // Phục vụ cơ chế ánh xạ document.
    }

    public SensorReading(Instant observedAt, SensorMeta sensor, double temperatureC) {
        this.observedAt = observedAt;
        this.sensor = sensor;
        this.temperatureC = temperatureC;
    }

    public String getId() { return id; }
    public Instant getObservedAt() { return observedAt; }
    public SensorMeta getSensor() { return sensor; }
    public double getTemperatureC() { return temperatureC; }

    public record SensorMeta(String deviceId, String site) {}
}
```

Trong ví dụ:

- `collection = "sensor_readings"`: tên collection sẽ được sử dụng cho `SensorReading`.
- `timeField = "observedAt"`: Spring Data ánh xạ thuộc tính `Instant` sang trường BSON Date để MongoDB xử lý theo thời gian.
- `metaField = "sensor"`: cả object metadata được dùng để nhận diện chuỗi đo; không nên trỏ đến `_id`, `timeField` hoặc thuộc tính kiểu mảng/collection.
- `granularity = Granularity.SECONDS`: hợp lý khi có nhiều mẫu trong mỗi phút; đây là **độ hạt bucket**, không phải yêu cầu làm tròn timestamp đến từng giây.
- `expireAfter = "30d"`: yêu cầu xóa dữ liệu quá thời hạn 30 ngày. Spring Data MongoDB 4.4+ hỗ trợ thuộc tính này; cũng có thể sử dụng chuỗi ISO-8601, biểu thức Spring hoặc property placeholder.

### Tạo collection từ annotation

Sau khi có `MongoTemplate`, gọi **tường minh**:

```java
import org.springframework.data.mongodb.core.MongoTemplate;

MongoTemplate template = /* bean được Spring quản lý */;

// Chỉ tạo khi collection chưa tồn tại.
if (!template.collectionExists(SensorReading.class)) {
    template.createCollection(SensorReading.class);
}
```

`createCollection(SensorReading.class)` đọc metadata của entity, bao gồm `@TimeSeries`, rồi gửi lệnh tạo Time Series collection tới MongoDB. Nó là bước tạo **cấu trúc lưu trữ**; sau đó mới nên ghi các phép đo.

Trong ứng dụng Spring Boot, có thể dùng `ApplicationRunner` để tạo collection lúc khởi động:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.core.MongoTemplate;

@Configuration
public class MongoCollectionConfig {

    @Bean
    ApplicationRunner ensureTimeSeriesCollection(MongoTemplate template) {
        return args -> {
            if (!template.collectionExists(SensorReading.class)) {
                template.createCollection(SensorReading.class);
            }
        };
    }
}
```

Với một ứng dụng có nhiều instance khởi động đồng thời, kiểm tra `collectionExists` rồi tạo collection **không bảo đảm nguyên tử**: hai instance có thể cùng thấy collection chưa tồn tại. Trong thực tế, nên tạo collection ở bước triển khai/migration có điều phối, hoặc xử lý trường hợp collection vừa được instance khác tạo và **đối chiếu lại cấu hình thực tế**. Cũng cần kiểm tra cấu hình nếu collection *đã* tồn tại: `collectionExists == true` không có nghĩa collection đó là Time Series với các tùy chọn mong muốn.

### Thêm một phép đo sau khi collection đã được tạo

```java
SensorReading reading = new SensorReading(
    Instant.parse("2026-11-20T02:10:00Z"),
    new SensorReading.SensorMeta("sensor-17", "warehouse-a"),
    3.8
);

template.insert(reading);
```

Khi dùng repository cho `SensorReading`, repository vẫn xử lý việc lưu và đọc document qua Spring Data; **bước tạo collection Time Series vẫn cần được bảo đảm trước khi ghi**.

## 3. Cách 2 — Tạo collection bằng `CollectionOptions`

Có lúc bạn chưa có entity cụ thể, đang xây công cụ quản trị dữ liệu, hoặc muốn kiểm soát việc tạo collection ngay tại tầng khởi tạo cơ sở dữ liệu. Khi đó sử dụng `CollectionOptions` của Spring Data MongoDB:

```java
import java.time.Duration;

import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.timeseries.Granularity;

CollectionOptions options = CollectionOptions.timeSeries(
    "observedAt",
    ts -> ts.metaField("sensor")
            .granularity(Granularity.SECONDS)
            .expireAfter(Duration.ofDays(30))
);

if (!template.collectionExists("sensor_readings")) {
    template.createCollection("sensor_readings", options);
}
```

Lưu ý hai đối số của `createCollection`: **tên collection** và **tùy chọn Time Series**. Nếu chỉ gọi `createCollection("sensor_readings")` mà không truyền các tùy chọn, bạn sẽ tạo collection thường.

Ví dụ trên dùng overload `CollectionOptions.timeSeries(String, Function)`, có từ **Spring Data MongoDB 4.4**. Với thiết lập tối giản, sử dụng API từ Spring Data MongoDB 3.3:

```java
template.createCollection(
    "sensor_readings",
    CollectionOptions.timeSeries("observedAt")
);
```

Lời gọi tối giản chỉ khai báo `timeField`; không khai báo `metaField`, `granularity` hay TTL. Nếu cần thêm tùy chọn trên các bản Spring Data cũ hơn overload lambda, có thể dùng đối tượng `CollectionOptions.TimeSeriesOptions`:

```java
CollectionOptions.TimeSeriesOptions ts =
    CollectionOptions.TimeSeriesOptions.timeSeries("observedAt")
        .metaField("sensor")
        .granularity(Granularity.SECONDS);

CollectionOptions options = CollectionOptions.empty().timeSeries(ts);
template.createCollection("sensor_readings", options);
```

`expireAfter(Duration)` và `@TimeSeries(expireAfter = ...)` được bổ sung từ Spring Data MongoDB 4.4. Khi sử dụng phiên bản khác, hãy kiểm tra Javadoc khớp với dependency trong dự án. Với cùng tên collection, **chọn một đường tạo collection** rồi dùng thống nhất; không chạy hai câu lệnh tạo sau nhau.

### Liên hệ với lệnh MongoDB gốc

Tương đương về ý tưởng, `CollectionOptions` của ví dụ đầy đủ tạo cấu hình như:

```javascript
db.createCollection("sensor_readings", {
  timeseries: {
    timeField: "observedAt",
    metaField: "sensor",
    granularity: "seconds"
  },
  expireAfterSeconds: 2592000
});
```

`2592000` giây tương ứng 30 ngày. Đây là **lệnh minh họa để đối chiếu**; nếu ứng dụng đã tạo collection bằng Spring Data, không chạy thêm lệnh Mongo shell này trên cùng tên.

## 4. Chọn `@TimeSeries` hay `CollectionOptions`?

| Tiêu chí | `@TimeSeries` | `CollectionOptions` |
| --- | --- | --- |
| Điểm khai báo | Ngay trên entity Java | Trong code khởi tạo/migration |
| API tạo tương ứng | `template.createCollection(SensorReading.class)` | `template.createCollection(name, options)` |
| Tên collection | Qua `collection` hoặc quy ước tên entity | Chuỗi tên truyền trực tiếp |
| Cấu hình time/meta/granularity | Thuộc tính annotation | Cấu hình bằng Java API |
| TTL | `expireAfter = "30d"` (Spring Data 4.4+) | `expireAfter(Duration.ofDays(30))` (Spring Data 4.4+) |
| Phù hợp | Entity cố định, muốn cấu hình đặt gần model | Tạo collection theo cấu hình triển khai hoặc thao tác quản trị |

**Quy tắc lựa chọn:** Nếu mỗi collection tương ứng một domain entity rõ ràng, ưu tiên `@TimeSeries` vì dễ đọc và đồng bộ với mapping. Nếu ứng dụng quản lý nhiều collection theo tên cấu hình, hoặc không muốn gắn lựa chọn lưu trữ vào domain class, ưu tiên `CollectionOptions`.

Một điểm cần giữ nhất quán: nếu entity ánh xạ trường bằng `@Field("...")`, phải xác nhận tên field **thực sự lưu trong MongoDB**. Spring Data có thể dịch tên thuộc tính Java sang tên field đã ánh xạ khi xử lý tùy chọn Time Series. Sự không thống nhất giữa tên trường trong dữ liệu ghi và cấu hình collection sẽ gây lỗi hoặc ghi sai schema.

## 5. Kiểm tra collection sau khi tạo

Đừng chỉ dựa vào việc không có exception. Mở `mongosh` trên đúng database và xem metadata:

```javascript
const info = db.getCollectionInfos({ name: "sensor_readings" })[0];
printjson({
  name: info?.name,
  type: info?.type,
  timeseries: info?.options?.timeseries,
  expireAfterSeconds: info?.options?.expireAfterSeconds
});
```

Kết quả mong đợi có dạng:

```json
{
  "name": "sensor_readings",
  "type": "timeseries",
  "timeseries": {
    "timeField": "observedAt",
    "metaField": "sensor",
    "granularity": "seconds"
  },
  "expireAfterSeconds": 2592000
}
```

Đây là hình dạng kết quả minh họa; một số phiên bản MongoDB có thể hiển thị thêm thuộc tính bucket. Nếu `type` trả về `collection`, bạn đang có collection thông thường. Nếu `timeseries` không đúng, cần giải quyết sai lệch cấu hình trước khi tiếp tục sử dụng.

Sau đó kiểm tra dữ liệu và truy vấn theo thiết bị/khoảng thời gian:

```javascript
db.sensor_readings.find(
  {
    "sensor.deviceId": "sensor-17",
    observedAt: {
      $gte: ISODate("2026-11-20T00:00:00Z"),
      $lt:  ISODate("2026-11-21T00:00:00Z")
    }
  },
  { _id: 0, observedAt: 1, sensor: 1, temperatureC: 1 }
).sort({ observedAt: 1 });
```

Với Spring Data, truy vấn tương đương:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

Query query = Query.query(
    Criteria.where("sensor.deviceId").is("sensor-17")
        .and("observedAt")
        .gte(Instant.parse("2026-11-20T00:00:00Z"))
        .lt(Instant.parse("2026-11-21T00:00:00Z"))
).with(Sort.by(Sort.Direction.ASC, "observedAt"));

List<SensorReading> readings =
    template.find(query, SensorReading.class);
```

Truy vấn theo nguồn đo và dải thời gian là mẫu truy cập điển hình. Khi lượng dữ liệu lớn, hãy kiểm tra `explain()`, thống kê bucket và các index được MongoDB tạo hoặc cho phép trên Time Series collection trước khi thêm index mới.

## 6. Với `ReactiveMongoTemplate`: việc tạo phải được thực thi

API reactive có các phương thức tương ứng nhưng trả về `Mono`. Chỉ tạo một biến `Mono` rồi bỏ qua sẽ **không gửi lệnh tạo collection**. Ghép thao tác tạo vào chuỗi xử lý để việc ghi diễn ra sau khi tạo xong:

```java
import reactor.core.publisher.Mono;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;

Mono<Void> ensureCreated = reactiveTemplate
    .collectionExists("sensor_readings")
    .flatMap(exists -> exists
        ? Mono.<Void>empty()
        : reactiveTemplate.createCollection("sensor_readings", options).then()
    );

Mono<SensorReading> saved =
    ensureCreated.then(reactiveTemplate.insert(reading));

// Trả về 'saved' cho luồng xử lý ở tầng trên;
// WebFlux hoặc subscriber thực sự sẽ kích hoạt chuỗi thao tác.
```

Đoạn code giả định `reactiveTemplate`, `options`, `reading` đã được khởi tạo như các ví dụ trước. Vấn đề khởi động đồng thời nhiều instance và kiểm tra cấu hình collection tồn tại vẫn áp dụng với reactive.

## 7. Giới hạn quan trọng và tình huống lỗi

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| Đã có `@TimeSeries` nhưng kết quả `type: "collection"` | Collection thường đã được tạo trước đó | Tạo **collection mới** với cấu hình Time Series và chuyển dữ liệu; không thể đổi loại collection tại chỗ. |
| Tạo collection báo đã tồn tại | Tên đã được sử dụng, hoặc hai instance cùng tạo | Đọc metadata bằng `getCollectionInfos`; xác nhận type và các tùy chọn, xử lý race ở bước khởi tạo. |
| Insert báo lỗi liên quan `timeField` | Thiếu trường, dữ liệu là chuỗi thay vì BSON Date, hoặc mapping sai tên field | Kiểm tra `Instant`/Java Date được ánh xạ thành BSON Date đúng tên `observedAt`. |
| Dữ liệu chưa bị xóa ngay khi quá 30 ngày | TTL xử lý theo bucket và tác vụ nền | Xem `expireAfterSeconds`, timestamp thực tế và chu kỳ dọn bucket; TTL không phải lịch xóa chính xác từng giây. |
| Truy vấn chậm khi số lượng phép đo tăng | `metaField` không hữu ích, `granularity` không phù hợp hoặc truy vấn thiếu điều kiện thời gian | Thiết kế lại truy vấn theo `metaField` + thời gian; kiểm tra index/giải thích thực thi. |
| Muốn đổi `timeField` hoặc `metaField` sau khi tạo | Đây là cấu hình gắn với collection khi tạo | Tạo collection Time Series mới và migrate dữ liệu. |

Một số giới hạn của MongoDB Time Series cần tính trước khi chọn mô hình này:

- Không thể dùng các thao tác update tùy ý như collection thường: MongoDB chỉ cho cập nhật metadata với điều kiện nhất định; các trường phép đo không phù hợp cho mô hình thường xuyên chỉnh sửa.
- MongoDB không hỗ trợ **ghi vào Time Series collection bên trong transaction**; đọc trong transaction có thể được hỗ trợ theo ràng buộc máy chủ.
- Không hỗ trợ change streams hoặc unique indexes trên Time Series collection. Không mặc định có index `_id` như collection thường.
- Không thể tạo Time Series collection dạng `capped`; các kiểu index/validation khác cũng có giới hạn theo phiên bản MongoDB.
- TTL dọn **bucket** khi toàn bộ phép đo trong bucket đã hết hạn, vì vậy một document có thể còn xuất hiện sau thời điểm hết hạn lý thuyết.

Các giới hạn và khả năng index, update phụ thuộc phiên bản MongoDB. Khi thiết kế production, đối chiếu tài liệu của đúng phiên bản server đang vận hành.

## 8. Bài thực hành tự kiểm tra

Hãy tạo một ứng dụng Spring Boot có `spring-boot-starter-data-mongodb` và MongoDB hỗ trợ Time Series; hoàn thành theo thứ tự:

1. Viết entity `SensorReading` như mục 2 và tạo collection bằng `MongoTemplate.createCollection(SensorReading.class)` trước khi insert.
2. Dùng `getCollectionInfos` xác nhận `type: "timeseries"`, `timeField: "observedAt"`, `metaField: "sensor"` và TTL 30 ngày.
3. Ghi ít nhất ba phép đo cho `sensor-17` ở các thời điểm khác nhau và một phép đo cho `sensor-18`.
4. Truy vấn các phép đo của `sensor-17` theo khoảng thời gian; giải thích vì sao `sensor` là metadata còn `temperatureC` là dữ liệu đo.
5. Trong một database thử nghiệm khác, tạo collection tương đương bằng `CollectionOptions`, kiểm tra kết quả và so sánh metadata với cách dùng annotation.
6. Thử thay đổi lựa chọn `granularity` trong bài tập thiết kế: nếu thay vì 10 giây/lần, thiết bị chỉ gửi một mẫu mỗi giờ thì cấu hình nào phù hợp hơn, và bạn sẽ đánh giá tác động bằng chỉ số nào?

**Tiêu chí hoàn thành:** Bạn giải thích được lệnh nào thực sự tạo collection, xác nhận được loại collection từ MongoDB, chỉ rõ được 4 tham số cấu hình và biết vì sao collection thường đã tồn tại không thể chuyển thành Time Series chỉ bằng cách sửa annotation.

## Tài liệu tham khảo chính thức

- [Spring Data MongoDB — Index and Collection Management / Time Series](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-collection-management.html)
- [Javadoc `@TimeSeries`](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/mapping/TimeSeries.html)
- [Javadoc `CollectionOptions`](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/CollectionOptions.html)
- [Javadoc `CollectionOptions.TimeSeriesOptions`](https://docs.spring.io/spring-data/mongodb/reference/api/java/org/springframework/data/mongodb/core/CollectionOptions.TimeSeriesOptions.html)
- [MongoDB — Create and Query a Time Series Collection](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-procedures/)
- [MongoDB — Time Series Collection Limitations](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-limitations/)
- [MongoDB — Automatic Removal (TTL)](https://www.mongodb.com/docs/manual/core/timeseries/timeseries-automatic-removal/)
