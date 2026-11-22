# Geospatial: ghi tọa độ và tính khoảng cách trong Spring Data Redis

Khi ứng dụng cần tìm cửa hàng gần một khách hàng, kiểm tra khoảng cách giữa hai điểm giao hàng, hiển thị các chi nhánh trong bán kính vài kilômét hoặc lọc các thiết bị theo vị trí, việc chỉ lưu kinh độ/vĩ độ trong một JSON không đủ thuận tiện cho truy vấn. Redis hỗ trợ nhóm lệnh **Geospatial (GEO)** để lưu vị trí theo định danh, tra cứu tọa độ, tính khoảng cách và tìm các điểm nằm trong một vùng. Spring Data Redis cung cấp **`GeoOperations<K, M>`** để thao tác với nhóm lệnh này thông qua `RedisTemplate`.

Bài học tập trung vào hai thao tác cốt lõi: **ghi tọa độ bằng `GEOADD` / `GeoOperations.add(...)`** và **tính khoảng cách bằng `GEODIST` / `GeoOperations.distance(...)`**. Để vận dụng hiệu quả, cần hiểu thêm thứ tự kinh độ–vĩ độ, độ chính xác, trường hợp member không tồn tại, truy vấn bán kính, cách Redis thực sự lưu GEO, TTL, cập nhật vị trí và giới hạn Redis Cluster.

## 1. Bài toán thực tế: tìm khoảng cách giữa các chi nhánh

Giả sử một hệ thống bán lẻ có ba chi nhánh, mỗi chi nhánh có ID và vị trí địa lý. Dữ liệu minh họa dưới đây là tọa độ giả định trong khu vực Thành phố Hồ Chí Minh, dùng để giải thích API, không đại diện cho địa chỉ thực tế của cửa hàng nào.

| ID chi nhánh | Kinh độ (longitude) | Vĩ độ (latitude) |
|---|---:|---:|
| `branch-01` | 106.7010 | 10.7760 |
| `branch-02` | 106.7080 | 10.7810 |
| `branch-03` | 106.6950 | 10.7740 |

Nếu chỉ có Redis key:

```text
shop:dev:branch:branch-01 -> {"longitude":106.7010,"latitude":10.7760}
shop:dev:branch:branch-02 -> {"longitude":106.7080,"latitude":10.7810}
shop:dev:branch:branch-03 -> {"longitude":106.6950,"latitude":10.7740}
```

ứng dụng có thể đọc JSON và tự viết công thức tính khoảng cách. Nhưng để tìm **mọi chi nhánh trong bán kính 2 km**, nó sẽ phải duyệt nhiều bản ghi, giải mã tọa độ và tự lọc kết quả.

Redis GEO cho phép tạo một key chung:

```text
shop:dev:branches:geo
    member branch-01 -> (longitude=106.7010, latitude=10.7760)
    member branch-02 -> (longitude=106.7080, latitude=10.7810)
    member branch-03 -> (longitude=106.6950, latitude=10.7740)
```

Từ đó, có thể yêu cầu Redis tính khoảng cách giữa `branch-01` và `branch-02`, hoặc tìm các chi nhánh xung quanh một điểm bất kỳ mà không cần tải toàn bộ tập tọa độ về JVM.

## 2. Redis GEO thực chất lưu dưới cấu trúc nào?

Redis GEO **không phải một Redis data type độc lập** như List hay Hash. Redis lưu các điểm GEO trong một **Sorted Set (ZSET)**:

- **Redis key** là tên bộ dữ liệu địa lý, ví dụ `shop:dev:branches:geo`.
- **Member** là định danh vị trí, ví dụ `branch-01`.
- **Score** mã hóa vị trí theo biểu diễn geohash nội bộ mà Redis sử dụng để phục vụ tra cứu.
- Redis cung cấp các lệnh `GEOADD`, `GEOPOS`, `GEODIST`, `GEOSEARCH`, `GEOHASH`… để thao tác với biểu diễn này.

Ví dụ:

```redis
GEOADD shop:dev:branches:geo 106.7010 10.7760 branch-01
TYPE shop:dev:branches:geo
```

Lệnh `TYPE` trả:

```text
zset
```

Có thể dùng `ZCARD` để đếm số member trong key GEO và `ZREM` để loại một member. Tuy nhiên, không nên tùy tiện dùng `ZADD` với score nghiệp vụ trên cùng key GEO: score của GEO tuân theo quy tắc mã hóa tọa độ, không phải điểm xếp hạng thông thường.

### Một key GEO chứa nhiều vị trí

```text
                         Redis key
                shop:dev:branches:geo
                           |
                 Redis Sorted Set
                           |
     +---------------------+---------------------+
     |                     |                     |
  branch-01             branch-02             branch-03
  (lon, lat)            (lon, lat)            (lon, lat)
```

Đây là điểm khác biệt với cách tạo một key riêng cho mỗi vị trí. `GEODIST` tính khoảng cách giữa **hai member trong cùng một GEO key**. Nếu hai member nằm trong hai key khác nhau, không thể chỉ truyền hai tên member cho `GEODIST` rồi yêu cầu Redis tự tìm và tính khoảng cách xuyên key.

## 3. Hệ tọa độ và thứ tự tham số: longitude trước, latitude sau

Redis GEO sử dụng tọa độ địa lý theo kinh độ và vĩ độ. Quy tắc rất quan trọng:

> **Redis `GEOADD` nhận `longitude latitude member`, không phải `latitude longitude member`.**

- **Longitude (kinh độ)**: vị trí theo hướng Đông–Tây, trong khoảng `[-180, 180]` độ.
- **Latitude (vĩ độ)**: vị trí theo hướng Bắc–Nam; Redis GEO sử dụng phạm vi xấp xỉ `[-85.05112878, 85.05112878]` độ để phù hợp biểu diễn geospatial của nó.
- Cả hai được biểu diễn bằng số thập phân của **độ (degrees)**, không phải radian.
- Trong Spring Data Redis, `Point(x, y)` tương ứng **`x = longitude`**, **`y = latitude`**.

Ví dụ đúng:

```redis
GEOADD shop:dev:branches:geo 106.7010 10.7760 branch-01
```

Ví dụ Java đúng:

```java
Point point = new Point(106.7010, 10.7760);
```

Sai lầm thường gặp:

```java
// Sai: đưa latitude vào x và longitude vào y.
Point wrong = new Point(10.7760, 106.7010);
```

Trong ví dụ này, Redis có thể từ chối vì vĩ độ `106.7010` nằm ngoài phạm vi hỗ trợ. Nhưng tại những địa điểm mà cả hai số đều nằm trong phạm vi cho phép, đảo kinh/vĩ độ có thể không bị phát hiện ngay và khiến kết quả tìm kiếm sai hoàn toàn.

### Tại sao Redis không dùng vĩ độ tới 90°?

Redis GEO xây dựng chỉ mục không gian dựa trên biểu diễn tọa độ tương thích với phép chiếu Mercator giới hạn về vĩ độ. Do đó, vĩ độ GEO Redis không bao phủ hoàn toàn các vùng sát cực. Với ứng dụng bản đồ cửa hàng, giao nhận hoặc vị trí người dùng trong phạm vi thông thường, giới hạn này hiếm khi là vấn đề; với bài toán địa lý đặc biệt gần hai cực cần giải pháp thích hợp hơn.

## 4. Các lệnh Redis GEO quan trọng

| Lệnh Redis | Chức năng | Điểm cần nhớ |
|---|---|---|
| `GEOADD key longitude latitude member` | Ghi hoặc cập nhật tọa độ member | Thứ tự longitude trước latitude |
| `GEOPOS key member...` | Lấy lại tọa độ của một hoặc nhiều member | Member không tồn tại trả nil |
| `GEODIST key member1 member2 [unit]` | Tính khoảng cách giữa hai member cùng key | Mặc định mét; hỗ trợ `m`, `km`, `mi`, `ft` |
| `GEOHASH key member...` | Lấy chuỗi geohash biểu diễn tọa độ | Không phải giá trị để tính chính xác mọi khoảng cách |
| `GEOSEARCH key ...` | Tìm member trong bán kính hoặc hình chữ nhật | Redis 6.2+; hỗ trợ khoảng cách, tọa độ, sắp xếp |
| `ZREM key member...` | Xóa member khỏi GEO key | GEO dùng Sorted Set |
| `ZCARD key` | Đếm tổng member của GEO key | Đếm vị trí, không phải số bản ghi chi tiết ở key khác |

Các lệnh cũ như `GEORADIUS` và `GEORADIUSBYMEMBER` vẫn có thể xuất hiện trong hệ thống hoặc API của thư viện. Redis khuyến nghị nhóm `GEOSEARCH`/`GEOSEARCHSTORE` cho chức năng tìm kiếm tương ứng trong các phiên bản hỗ trợ. Khi sử dụng Spring Data Redis, cần phân biệt API của framework và lệnh cụ thể do driver/server thực thi.

## 5. Ghi tọa độ với `GEOADD`

Cú pháp cơ bản:

```redis
GEOADD key longitude latitude member
```

Ví dụ tạo ba chi nhánh trong một lệnh:

```redis
GEOADD shop:dev:branches:geo \
  106.7010 10.7760 branch-01 \
  106.7080 10.7810 branch-02 \
  106.6950 10.7740 branch-03
```

Trong Redis CLI tương tác hoặc khi gọi thẳng command trong terminal, có thể viết thành một dòng:

```bash
redis-cli GEOADD shop:dev:branches:geo 106.7010 10.7760 branch-01 106.7080 10.7810 branch-02 106.6950 10.7740 branch-03
```

`GEOADD` thông thường trả về **số member mới được thêm**, không phải tổng số vị trí đang có. Nếu ba ID trước đó chưa tồn tại, giá trị trả về là `3`.

### 5.1. Cập nhật vị trí của member đã tồn tại

Giả sử `branch-01` chuyển sang vị trí mới:

```redis
GEOADD shop:dev:branches:geo 106.7020 10.7770 branch-01
```

Redis cập nhật tọa độ của member `branch-01`. Với cú pháp `GEOADD` thông thường, kết quả có thể là `0` vì **không có member mới**, dù tọa độ đã được cập nhật thành công.

Đây là lỗi diễn giải rất phổ biến:

- `1` khi thêm một member mới không có nghĩa lệnh tạo một Redis key mới.
- `0` khi upsert một member đã tồn tại **không có nghĩa ghi thất bại**.
- `ZCARD` phản ánh tổng số member hiện có sau các lần cập nhật.
- Khi cần biết số phần tử có thay đổi tọa độ, Redis có tùy chọn `CH` cho các dạng lệnh phù hợp; không mặc định `GeoOperations.add` trả “số tọa độ thay đổi”.

### 5.2. ID member phải ổn định

Nếu cùng một chi nhánh `branch-01` được ghi thành `branch-1` hoặc `Branch-01`, Redis coi đó là các member khác nhau. Việc đổi định dạng ID mà không xóa member cũ có thể khiến một chi nhánh xuất hiện hai lần trong kết quả.

Nên dùng ID nội bộ ổn định, không dùng số điện thoại hoặc địa chỉ người dùng làm member. Những định danh nhạy cảm có thể xuất hiện trong log, Redis CLI, metrics và bản sao lưu.

## 6. Lấy lại tọa độ với `GEOPOS`

Cú pháp:

```redis
GEOPOS key member [member ...]
```

Ví dụ:

```redis
GEOPOS shop:dev:branches:geo branch-01 branch-02 branch-missing
```

Redis trả tọa độ theo thứ tự member được yêu cầu. Nếu `branch-missing` chưa có trong GEO key, vị trí tương ứng là nil.

Một kết quả khái niệm:

```text
branch-01 -> [106.701..., 10.776...]
branch-02 -> [106.708..., 10.781...]
branch-missing -> nil
```

Các chữ số thập phân đọc lại có thể **không giống hệt** chuỗi số lúc ghi. Redis lưu biểu diễn geospatial đã lượng tử hóa theo độ phân giải chỉ mục; không nên dùng `GEOPOS` như nguồn lưu tọa độ nguyên gốc với độ chính xác tùy ý.

Nếu ứng dụng cần lưu vĩ độ/kinh độ gốc do GPS gửi tới cùng metadata khác (độ chính xác đo, thời điểm cập nhật, nguồn dữ liệu), có thể lưu bản ghi authoritative riêng và dùng GEO như **chỉ mục phục vụ truy vấn không gian**.

## 7. Tính khoảng cách với `GEODIST`

Cú pháp:

```redis
GEODIST key member1 member2 [m|km|ft|mi]
```

Ví dụ:

```redis
GEODIST shop:dev:branches:geo branch-01 branch-02
```

Khi không truyền đơn vị, Redis trả **mét (m)**. Để yêu cầu kilômét:

```redis
GEODIST shop:dev:branches:geo branch-01 branch-02 km
```

Redis còn hỗ trợ `mi` (dặm) và `ft` (feet) theo khả năng của lệnh. Không truyền chuỗi đơn vị tùy ý như `kilometer` cho Redis CLI khi lệnh chỉ chấp nhận mã đơn vị quy định.

### 7.1. Hai member phải nằm trong cùng key

Giả sử hệ thống tạo hai GEO key:

```text
shop:dev:branches:geo         -> branch-01
shop:dev:warehouses:geo       -> warehouse-01
```

Không thể dùng:

```redis
GEODIST shop:dev:branches:geo branch-01 warehouse-01 km
```

để tính khoảng cách nếu `warehouse-01` chỉ tồn tại trong `shop:dev:warehouses:geo`. Khi đó Redis không tìm được member thứ hai trong key được chỉ định nên không trả khoảng cách.

Có thể giải quyết bằng cách tổ chức cả hai thành viên trong một GEO index chung nếu ngữ nghĩa phù hợp, hoặc đọc tọa độ hai nơi rồi tính bằng thư viện địa lý ở ứng dụng. Chọn phương án phải xét ownership, vòng đời và nhu cầu truy vấn.

### 7.2. Nếu một hoặc cả hai member không tồn tại

`GEODIST` trả nil nếu không xác định được khoảng cách vì member không tồn tại trong key. Trong Spring Data Redis, đối tượng `Distance` trả về có thể là `null`.

Vì vậy, nên phân biệt:

- Khoảng cách `0`: hai vị trí trùng nhau hoặc tính ra khoảng cách bằng 0 ở độ phân giải hiện tại.
- Không có kết quả: một hoặc cả hai member chưa tồn tại; **không** tự động biến thành 0 km.
- Lỗi kết nối/timeout/serializer: là exception hoặc tình huống riêng, không nên bị che bằng một giá trị khoảng cách giả.

### 7.3. Khoảng cách Redis có phải quãng đường di chuyển không?

**Không.** `GEODIST` cho khoảng cách địa lý gần đúng giữa hai điểm trên bề mặt Trái Đất, dựa trên mô hình tính toán của Redis. Nó **không** tính lộ trình giao thông, cầu đường, sông ngòi, thời gian đi bộ, thời gian lái xe hoặc đường tránh kẹt xe.

Ví dụ hai địa điểm cách nhau 1 km theo đường thẳng có thể phải đi 3 km bằng đường bộ. Khi sản phẩm cần “quãng đường lái xe thực tế” hoặc “ETA”, nên dùng hệ thống định tuyến bản đồ phù hợp sau khi dùng GEO để lọc trước các ứng viên.

## 8. Tích hợp bằng Spring Boot và `GeoOperations`

Ví dụ dùng Spring Boot 3.x, Java 17+ và Spring Data Redis starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Cấu hình Redis standalone cho môi trường phát triển:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
```

Nếu điều kiện auto-configuration phù hợp, Spring Boot cung cấp `RedisConnectionFactory` và `StringRedisTemplate`. `StringRedisTemplate` phù hợp khi **key GEO và member ID** đều là chuỗi.

Nhận `GeoOperations` từ template:

```java
import org.springframework.data.redis.core.GeoOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

GeoOperations<String, String> geo = redis.opsForGeo();
```

Kiểu `K` là kiểu **Redis key**; kiểu `M` là kiểu **member** được lưu trong GEO Set. Trong ví dụ, cả hai đều là `String`.

Không cần tạo một connection mới mỗi lần thêm tọa độ. Bean template dùng `RedisConnectionFactory` do Spring quản lý và xử lý serialization, lifecycle của Redis connection.

## 9. Java: ghi tọa độ bằng `GeoOperations.add(...)`

`GeoOperations` hỗ trợ thêm vị trí theo member:

```java
Long added = geo.add(
        "shop:dev:branches:geo",
        new Point(106.7010, 10.7760),
        "branch-01"
);
```

Cần import:

```java
import org.springframework.data.geo.Point;
```

Chú ý:

- `new Point(x, y)` với `x=longitude`, `y=latitude`.
- `added` thường là số member **mới** trong lần ghi.
- Nếu member đã tồn tại, tọa độ có thể được cập nhật nhưng `added == 0`.
- Trong pipeline hoặc transaction, kết quả tức thời của một số API Spring Data Redis có thể là `null` do kết quả được trả sau; không đánh đồng `null` với lỗi nghiệp vụ.

Thêm nhiều điểm bằng các lần gọi:

```java
geo.add(KEY, new Point(106.7010, 10.7760), "branch-01");
geo.add(KEY, new Point(106.7080, 10.7810), "branch-02");
geo.add(KEY, new Point(106.6950, 10.7740), "branch-03");
```

Hoặc dùng overload nhận map member → point:

```java
Map<String, Point> points = Map.of(
        "branch-01", new Point(106.7010, 10.7760),
        "branch-02", new Point(106.7080, 10.7810),
        "branch-03", new Point(106.6950, 10.7740)
);

Long addedCount = geo.add(KEY, points);
```

Với map, key của map là member ID và value là `Point`. Đây là cách nạp trước nhiều vị trí khi ứng dụng có đủ dữ liệu. Không nên tạo một map vô hạn gồm hàng triệu phần tử trong JVM; hãy chia batch phù hợp với bộ nhớ, latency và quy tắc ghi dữ liệu của hệ thống.

## 10. Java: lấy tọa độ bằng `position(...)`

Đọc vị trí đã lưu:

```java
List<Point> points = geo.position(
        "shop:dev:branches:geo",
        "branch-01",
        "branch-02"
);
```

`position` tương ứng nhóm lệnh `GEOPOS`, trả danh sách vị trí theo thứ tự các member đầu vào. Với member không tồn tại, phần tử trong danh sách có thể là `null`.

Ví dụ xử lý một member:

```java
public Optional<Point> findPosition(String memberId) {
    List<Point> positions = geo.position(GEO_KEY, memberId);

    if (positions == null || positions.isEmpty()) {
        return Optional.empty();
    }

    return Optional.ofNullable(positions.get(0));
}
```

`Point.getX()` là longitude; `Point.getY()` là latitude. Nếu Redis đã lượng tử hóa tọa độ nội bộ, không nên dùng phép so sánh `double == double` để bắt buộc giá trị đọc lại giống từng chữ số trong input ban đầu.

## 11. Java: tính khoảng cách bằng `distance(...)`

Spring Data Redis dùng kiểu `org.springframework.data.geo.Distance` và đơn vị `org.springframework.data.geo.Metrics`.

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

Distance meters = geo.distance(
        GEO_KEY,
        "branch-01",
        "branch-02"
);

Distance kilometers = geo.distance(
        GEO_KEY,
        "branch-01",
        "branch-02",
        Metrics.KILOMETERS
);
```

Các overload có thể dùng:

- `distance(key, member1, member2)`: đo khoảng cách với đơn vị mặc định tương ứng của Redis (thường là mét).
- `distance(key, member1, member2, metric)`: yêu cầu đơn vị như `Metrics.KILOMETERS`.

Lấy giá trị:

```java
if (kilometers == null) {
    // Một hoặc cả hai member không tồn tại.
} else {
    double distanceKm = kilometers.getValue();
    System.out.println("Khoảng cách: " + distanceKm + " km");
}
```

Không nên in số vừa nhận thành km nếu trước đó đã gọi overload mặc định trả mét. Tên biến và đơn vị hiển thị phải nhất quán với `Metric` truyền vào.

### Cách thiết kế API trả về khoảng cách

Nếu một member không tồn tại, một service có thể trả `OptionalDouble.empty()`:

```java
public OptionalDouble distanceKm(String fromId, String toId) {
    Distance d = geo.distance(
            GEO_KEY, fromId, toId, Metrics.KILOMETERS);

    return d == null
            ? OptionalDouble.empty()
            : OptionalDouble.of(d.getValue());
}
```

Cách này tránh trả `0.0` khi Redis không có dữ liệu. Tuy nhiên, cần phân biệt “không có tọa độ” với lỗi Redis bị timeout; lỗi hạ tầng phải được xử lý theo cơ chế exception/observability thích hợp.

## 12. Ví dụ Spring service tự chứa: lưu chi nhánh và đo khoảng cách

Một DTO vị trí đơn giản:

```java
package com.example.shop.geo;

public record BranchLocation(
        String id,
        double longitude,
        double latitude
) {}
```

Service:

```java
package com.example.shop.geo;

import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalDouble;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.core.GeoOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class BranchGeoStore {

    private static final String GEO_KEY = "shop:dev:branches:geo";
    private static final double MAX_GEO_LATITUDE = 85.05112878;

    private final GeoOperations<String, String> geo;

    public BranchGeoStore(StringRedisTemplate template) {
        this.geo = template.opsForGeo();
    }

    public Long upsert(BranchLocation location) {
        Objects.requireNonNull(location, "location");
        validateId(location.id());
        validateCoordinates(location.longitude(), location.latitude());

        return geo.add(
                GEO_KEY,
                new Point(location.longitude(), location.latitude()),
                location.id()
        );
    }

    public Optional<Point> position(String id) {
        validateId(id);

        List<Point> result = geo.position(GEO_KEY, id);
        if (result == null || result.isEmpty()) {
            return Optional.empty();
        }

        return Optional.ofNullable(result.get(0));
    }

    public OptionalDouble distanceKm(String firstId, String secondId) {
        validateId(firstId);
        validateId(secondId);

        Distance distance = geo.distance(
                GEO_KEY,
                firstId,
                secondId,
                Metrics.KILOMETERS
        );

        return distance == null
                ? OptionalDouble.empty()
                : OptionalDouble.of(distance.getValue());
    }

    public Long remove(String id) {
        validateId(id);
        return geo.remove(GEO_KEY, id);
    }

    private static void validateId(String id) {
        Objects.requireNonNull(id, "branch id");
        if (!id.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid branch id");
        }
    }

    private static void validateCoordinates(double longitude, double latitude) {
        if (!Double.isFinite(longitude) ||
                !Double.isFinite(latitude) ||
                longitude < -180.0 ||
                longitude > 180.0 ||
                latitude < -MAX_GEO_LATITUDE ||
                latitude > MAX_GEO_LATITUDE) {
            throw new IllegalArgumentException(
                    "Coordinates outside Redis GEO range");
        }
    }
}
```

Sử dụng:

```java
store.upsert(new BranchLocation(
        "branch-01", 106.7010, 10.7760));

store.upsert(new BranchLocation(
        "branch-02", 106.7080, 10.7810));

Optional<Point> first = store.position("branch-01");

OptionalDouble km = store.distanceKm(
        "branch-01", "branch-02");
```

Đây là ví dụ service đồng bộ, mỗi method gửi một Redis command cơ bản. Giá trị trả về của `upsert` là số member mới được thêm, **không phải version** của vị trí và cũng không phải số điểm đang lưu.

Trong hệ thống thực tế, namespace `shop:dev` nên được bind từ cấu hình triển khai để không trộn môi trường. Nếu dịch vụ có multi-tenancy, cần kiểm soát cả nguồn tenant ID và chính sách phân tách index, thay vì để client tự chọn bất kỳ GEO key nào.

## 13. Tìm các địa điểm trong bán kính

Ghi tọa độ và tính khoảng cách giữa hai member đã biết là bước đầu. Bài toán phổ biến hơn là:

> “Từ tọa độ hiện tại của người dùng, có những chi nhánh nào nằm trong vòng 3 km?”

Redis hỗ trợ tìm kiếm theo khoảng cách từ **một tọa độ** hoặc **một member đã lưu**.

Ví dụ Redis 6.2+:

```redis
GEOSEARCH shop:dev:branches:geo \
  FROMLONLAT 106.7009 10.7769 \
  BYRADIUS 3 km \
  WITHDIST WITHCOORD ASC COUNT 10
```

Nếu chạy trong shell không hỗ trợ xuống dòng như trên, dùng lệnh một dòng:

```bash
redis-cli GEOSEARCH shop:dev:branches:geo FROMLONLAT 106.7009 10.7769 BYRADIUS 3 km WITHDIST WITHCOORD ASC COUNT 10
```

Ý nghĩa các phần:

| Thành phần | Vai trò |
|---|---|
| `FROMLONLAT 106.7009 10.7769` | Điểm trung tâm là một tọa độ không nhất thiết đã lưu |
| `BYRADIUS 3 km` | Tìm trong bán kính 3 km |
| `WITHDIST` | Trả thêm khoảng cách từ tâm đến mỗi member |
| `WITHCOORD` | Trả thêm tọa độ của từng member |
| `ASC` | Sắp xếp từ gần đến xa |
| `COUNT 10` | Giới hạn số kết quả trả về |

Trong API tìm kiếm vị trí, nên yêu cầu sắp xếp rõ ràng nếu muốn hiển thị “gần nhất trước”. Khi không chỉ định sort, không nên suy đoán Redis sẽ trả theo khoảng cách tăng dần.

### Tìm quanh một member đã lưu

Nếu muốn tìm những chi nhánh gần `branch-01`:

```redis
GEOSEARCH shop:dev:branches:geo \
  FROMMEMBER branch-01 \
  BYRADIUS 2 km \
  WITHDIST ASC COUNT 10
```

Theo ngữ nghĩa tìm kiếm, `branch-01` cũng có thể xuất hiện trong kết quả với khoảng cách 0 nếu nó nằm trong bán kính. Nếu yêu cầu là “các chi nhánh **khác** gần branch-01”, ứng dụng cần loại member gốc ra khi tạo danh sách kết quả.

### Tìm theo hình chữ nhật

Ngoài `BYRADIUS`, Redis GEO còn hỗ trợ `BYBOX width height unit`:

```redis
GEOSEARCH shop:dev:branches:geo \
  FROMLONLAT 106.7009 10.7769 \
  BYBOX 4 2 km \
  WITHDIST ASC
```

Với hình chữ nhật, cách hiểu là chiều rộng và chiều cao theo đơn vị yêu cầu. Hình tròn và hình chữ nhật là hai kiểu vùng tìm kiếm; không đồng nghĩa với ranh giới hành chính, tuyến giao thông hay polygon bất kỳ.

## 14. Tìm kiếm theo bán kính trong Spring Data Redis

`GeoOperations` hỗ trợ thao tác `radius(...)`, dùng các kiểu:

- `Point`: tọa độ trung tâm.
- `Distance`: bán kính và đơn vị.
- `Circle`: ghép tâm và bán kính.
- `GeoResults<GeoLocation<M>>`: danh sách kết quả địa lý.
- `GeoRadiusCommandArgs`: tùy chọn trả khoảng cách, tọa độ, sắp xếp và giới hạn.

Ví dụ:

```java
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.connection.RedisGeoCommands;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoLocation;
import org.springframework.data.redis.core.GeoOperations;

Point center = new Point(106.7009, 10.7769);
Distance radius = new Distance(3.0, Metrics.KILOMETERS);
Circle area = new Circle(center, radius);

RedisGeoCommands.GeoRadiusCommandArgs args =
        RedisGeoCommands.GeoRadiusCommandArgs
            .newGeoRadiusArgs()
            .includeDistance()
            .includeCoordinates()
            .sortAscending()
            .limit(10);

GeoResults<GeoLocation<String>> results =
        geo.radius("shop:dev:branches:geo", area, args);
```

Đọc kết quả:

```java
if (results != null) {
    for (GeoResult<GeoLocation<String>> hit : results) {
        String memberId = hit.getContent().getName();
        Point point = hit.getContent().getPoint();
        Distance distance = hit.getDistance();

        System.out.println(
                "ID=" + memberId +
                ", point=" + point +
                ", distance=" +
                (distance == null ? "n/a" : distance.getValue()));
    }
}
```

Khi yêu cầu `includeDistance()`, Spring Data Redis có thể cung cấp khoảng cách trong `GeoResult.getDistance()`. Khi không yêu cầu, kết quả không nhất thiết có khoảng cách; nên kiểm tra `null` nếu API của ứng dụng dựa vào trường này.

Ví dụ gọi `radius(...)` nêu trên minh họa API ổn định của `GeoOperations` trong Spring Data Redis. Trong các phiên bản mới, Spring Data Redis cũng cung cấp API `search(...)` sử dụng khả năng `GEOSEARCH` của Redis; lựa chọn API/lệnh chính xác nên theo phiên bản Redis server, Spring Data Redis và driver trong dự án. Khi yêu cầu chức năng mới như truy vấn vùng chữ nhật, `GEOSEARCH` là hướng phù hợp ở Redis 6.2+.

### Khác nhau giữa tìm bán kính và `distance(...)`

- `distance(key, a, b)` tính khoảng cách giữa **hai member đã lưu** trong cùng GEO key.
- `radius(key, circle, args)` tìm **những member nằm quanh một điểm bất kỳ**, không cần điểm trung tâm là member đã lưu.
- `radius(key, member, radius, args)` theo overload thích hợp tìm quanh **member đã lưu**.
- `position(key, members...)` chỉ lấy tọa độ, không tính khoảng cách.

Khi có một tọa độ GPS hiện tại của người dùng chưa được ghi vào Redis, không cần tạo một member tạm cho người dùng chỉ để tìm các chi nhánh gần họ; dùng truy vấn với **tọa độ trung tâm** sẽ phù hợp hơn.

## 15. Sắp xếp kết quả theo khoảng cách và giới hạn số lượng

Một service hiển thị “10 chi nhánh gần nhất trong 5 km” cần hai điều kiện khác nhau:

1. **Vùng lọc:** bán kính tối đa là 5 km.
2. **Thứ tự và số lượng:** sắp xếp từ gần tới xa, chỉ lấy 10 kết quả.

Với Redis CLI:

```redis
GEOSEARCH shop:dev:branches:geo \
  FROMLONLAT 106.7009 10.7769 \
  BYRADIUS 5 km ASC COUNT 10 WITHDIST
```

Trong Spring Data Redis, `sortAscending()` và `limit(10)` giải thích yêu cầu tương tự khi dùng `GeoRadiusCommandArgs`.

Một số biến thể GEOSEARCH hỗ trợ `COUNT count ANY`. Tùy chọn `ANY` cho phép Redis dừng sớm sau khi tìm đủ số lượng phù hợp trong các tình huống nhất định, có thể giảm chi phí nhưng **không nên dùng khi hợp đồng yêu cầu chắc chắn 10 điểm gần nhất**. Nếu sản phẩm cần thứ tự chính xác từ gần nhất, hãy cân nhắc việc áp dụng `ASC` và không dùng những tối ưu cho phép dừng sớm không đảm bảo nearest-N.

Điều kiện lọc thời gian mở cửa, tình trạng cửa hàng còn hoạt động hay mức tồn kho không tự động nằm trong GEO index. Redis GEO trả ứng viên theo **vị trí**; cần kết hợp dữ liệu nghiệp vụ sau đó:

```text
GEOSEARCH (bán kính 5 km)
          |
          v
    Danh sách member ID
          |
          v
  Đọc branch status / opening hours / stock
          |
          v
   Lọc điều kiện nghiệp vụ
          |
          v
   Trả danh sách địa điểm cho người dùng
```

Nếu chỉ lấy `COUNT 10` trước rồi mới lọc “đang mở”, có thể còn ít hơn 10 kết quả dù trong bán kính vẫn có chi nhánh hợp lệ khác. Khi đó cần chiến lược mở rộng số ứng viên hoặc query planner phù hợp, không giả định 10 kết quả GEO đầu tiên đã thỏa mọi điều kiện nghiệp vụ.

## 16. Một API hoàn chỉnh: tìm các chi nhánh gần điểm người dùng

Mở rộng service ở phần trước với record kết quả:

```java
package com.example.shop.geo;

public record NearbyBranch(
        String branchId,
        Double distanceKm
) {}
```

Thêm phương thức vào `BranchGeoStore`:

```java
import java.util.List;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.connection.RedisGeoCommands;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoLocation;

public List<NearbyBranch> findNearby(
        double longitude,
        double latitude,
        double radiusKm,
        int limit) {

    validateCoordinates(longitude, latitude);
    if (!Double.isFinite(radiusKm) || radiusKm <= 0.0) {
        throw new IllegalArgumentException("Invalid radius");
    }
    if (limit <= 0 || limit > 100) {
        throw new IllegalArgumentException("Invalid result limit");
    }

    var args = RedisGeoCommands.GeoRadiusCommandArgs
            .newGeoRadiusArgs()
            .includeDistance()
            .sortAscending()
            .limit(limit);

    var area = new Circle(
            new Point(longitude, latitude),
            new Distance(radiusKm, Metrics.KILOMETERS)
    );

    GeoResults<GeoLocation<String>> hits =
            geo.radius(GEO_KEY, area, args);

    if (hits == null) {
        return List.of();
    }

    return hits.getContent().stream()
            .map(hit -> new NearbyBranch(
                    hit.getContent().getName(),
                    hit.getDistance() == null
                            ? null
                            : hit.getDistance().getValue()
            ))
            .toList();
}
```

Gọi:

```java
List<NearbyBranch> branches =
        store.findNearby(106.7009, 10.7769, 3.0, 10);
```

Record dùng `Double` thay vì `double` cho khoảng cách để cho phép biểu diễn “không có distance” nếu driver/framework không trả khoảng cách; ví dụ đã yêu cầu `includeDistance()` nên bình thường giá trị này được cung cấp. Khi xây dựng API HTTP, nên quyết định trường khoảng cách bắt buộc hay tùy chọn và cách serialize giá trị `null`.

### Vì sao phải giới hạn bán kính và kết quả từ input?

API truy vấn vị trí có thể bị lạm dụng với yêu cầu “toàn bộ điểm trong bán kính cực lớn” hoặc hàng nghìn request mỗi giây. Giới hạn `radiusKm`, `limit` và rate limit giúp kiểm soát CPU, network và kích thước response. Giá trị trong ví dụ `limit <= 100` là chính sách demo, không phải giới hạn do Redis bắt buộc.

Nếu hệ thống có hàng triệu điểm, cần đo với dữ liệu thực để quyết định radius/candidate limit hợp lý. Việc dùng GEO không tự bảo đảm mọi truy vấn không gian đều rẻ.

## 17. Xóa hoặc đổi vị trí member

### 17.1. Xóa member khỏi GEO key

Vì dữ liệu GEO nằm trong Redis Sorted Set, Redis sử dụng `ZREM` để xóa:

```redis
ZREM shop:dev:branches:geo branch-03
```

Trong Spring Data Redis:

```java
Long removed = geo.remove(GEO_KEY, "branch-03");
```

Giá trị trả về thể hiện số member thực sự bị xóa. Nếu member không tồn tại, thường là `0`. Không cần xóa cả GEO key chỉ để loại một điểm.

### 17.2. Cập nhật vị trí bằng cùng ID

Khi một chi nhánh đổi địa điểm, gọi `GEOADD` hoặc `geo.add(...)` với **cùng member ID** và tọa độ mới. Không tạo `branch-01-new` rồi quên xóa `branch-01` nếu đó chỉ là một chi nhánh đã di chuyển, vì truy vấn có thể thấy hai điểm là một.

### 17.3. Dữ liệu chi tiết và GEO index có thể lệch nhau

Một hệ thống thường lưu:

```text
shop:dev:branches:geo
  -> GEO index gồm tọa độ các branch

shop:dev:branches:details:branch-01
  -> tên, địa chỉ, trạng thái, giờ mở cửa, version
```

Nếu cập nhật Redis GEO thành công nhưng ghi details thất bại, tọa độ trong index và bản ghi chi tiết có thể lệch. Ngược lại, nếu xóa details mà quên `geo.remove` thì kết quả tìm kiếm có thể chứa ID không còn hợp lệ.

Khi cần nhất quán chặt, hãy thiết kế một đường cập nhật quản lý cả hai; có thể dùng Lua script/transaction phù hợp với cùng Redis server hoặc xử lý sự kiện và reconciliation nếu dữ liệu nguồn nằm ở hệ thống khác.

## 18. TTL và vòng đời dữ liệu GEO

Redis GEO dùng một Sorted Set key, vì vậy TTL được đặt trên **toàn bộ GEO key**, không phải từng member.

Ví dụ:

```redis
EXPIRE shop:dev:branches:geo 600
```

Sau khoảng 600 giây, toàn bộ bộ tọa độ `shop:dev:branches:geo` có thể hết hạn, không chỉ những vị trí đã quá 10 phút.

Điều này thường **không phù hợp** nếu key chứa danh sách chi nhánh ổn định của cả hệ thống và cần có mặt lâu dài. Một chi nhánh riêng lẻ đóng cửa hoặc bị xóa nên được xử lý bằng cập nhật member/metadata, thay vì để toàn bộ index hết TTL vì một quy tắc hết hạn chung.

### Cập nhật một member có reset TTL không?

`GEOADD` cập nhật Sorted Set hiện có và nhìn chung **không tự xóa TTL** của key. Nếu Redis key hết hạn hoặc bị xóa hoàn toàn, `GEOADD` tạo lại key mới và key mới không tự kế thừa TTL cũ.

Đối với tọa độ **chuyển động liên tục**, chẳng hạn vị trí tài xế:

```text
shop:prod:drivers:geo
  driver-101 -> vị trí ghi cách đây 2 giây
  driver-102 -> vị trí ghi cách đây 25 phút
```

Không thể chỉ đặt `EXPIRE shop:prod:drivers:geo 60` mà mong Redis tự xóa `driver-102` sau 60 giây nhưng giữ `driver-101`. TTL của key sẽ xóa **cả hai** nếu hết hạn.

Một hướng thiết kế là duy trì timestamp heartbeat riêng cho từng driver, rồi loại các driver quá cũ khỏi GEO index bằng một worker hoặc kết hợp bộ lọc sau truy vấn. Với quy mô lớn, cần cân nhắc mô hình dữ liệu, bộ lọc thời gian, backpressure và thao tác dọn stale dữ liệu có giới hạn.

## 19. GEO không thay thế nguồn dữ liệu vị trí authoritative

Redis lưu tọa độ GEO dưới biểu diễn tối ưu cho tìm kiếm, có **độ phân giải hữu hạn**. Khi gọi `GEOPOS`, tọa độ có thể khác rất nhỏ so với input ban đầu do lượng tử hóa.

Dữ liệu cần cho các nghiệp vụ khác có thể bao gồm:

- Tọa độ gốc đúng như thiết bị gửi.
- Timestamp của lần cập nhật.
- Độ chính xác GPS (accuracy radius).
- Độ cao hoặc tầng của tòa nhà.
- Người/thiết bị gửi dữ liệu.
- Trạng thái xác minh và quy tắc quyền riêng tư.

Redis GEO không tự lưu các metadata này. Có thể lưu chúng ở Hash/JSON/dữ liệu nguồn khác, rồi dùng GEO như **secondary index** để tìm ID gần một tọa độ.

Ví dụ:

```text
shop:prod:drivers:geo
    driver-101 -> (lon, lat) phục vụ tìm kiếm

shop:prod:drivers:state:driver-101
    -> {longitude, latitude, updatedAt, accuracyMeters, status}
```

Khi client truy vấn gần đây, Redis trả candidate driver ID; ứng dụng có thể kiểm tra `updatedAt` và `status` để tránh trả tọa độ cũ.

Nếu cần độ chính xác cao bất thường, xử lý đo đạc, địa chính, khoảng cách ba chiều hoặc định tuyến theo mạng đường, chọn thư viện địa lý/hệ thống GIS chuyên biệt thay vì giả định GEO đủ cho mọi phép tính.

## 20. Redis Cluster và thiết kế GEO key

### 20.1. Một GEO key chỉ thuộc một hash slot

Trong Redis Cluster, một key được ánh xạ tới một hash slot và một primary node tại một thời điểm. Vì `GEOADD`, `GEODIST`, `GEOPOS`, `GEOSEARCH` cùng làm việc với **một GEO key**, những thao tác này thường có thể được định tuyến tới node sở hữu key bởi client hỗ trợ Cluster.

Ví dụ:

```text
shop:prod:geo:branches:hcm
shop:prod:geo:branches:hn
shop:prod:geo:branches:dn
```

Ba GEO key có thể nằm ở các slot khác nhau. Truy vấn theo một key chỉ tìm member **trong key đó**.

Không có lệnh `GEOSEARCH` native đơn giản nào tự gộp toàn bộ ba GEO key để trả “top 10 gần nhất trên toàn quốc” bằng một truy vấn xuyên nhiều slot. Ứng dụng có thể cần truy vấn từng nhóm liên quan, ghép kết quả và sắp xếp lại theo distance.

### 20.2. Một GEO key toàn quốc hay nhiều key theo khu vực?

**Một GEO key chung:**

```text
shop:prod:geo:branches:all
```

Ưu điểm là mọi member trong cùng key, đơn giản khi tính `GEODIST` giữa hai chi nhánh và truy vấn một vùng. Nhược điểm là một key nóng lớn vẫn được xử lý trên một primary của Cluster, có thể tạo giới hạn throughput và memory đối với workload rất lớn.

**Nhiều GEO key theo khu vực:**

```text
shop:prod:geo:branches:region-a
shop:prod:geo:branches:region-b
```

Có thể phân phối key lên nhiều slot, nhưng việc truy vấn **gần ranh giới khu vực** trở nên phức tạp: một vị trí ở region-a có thể gần chi nhánh thuộc region-b. Nếu chỉ tìm trong region-a, API sẽ bỏ sót địa điểm hợp lệ ở bên kia ranh giới.

Cần thiết kế cách phát hiện các vùng giao với bán kính tìm kiếm, truy vấn nhiều index và loại bỏ trùng ID. Không có lựa chọn nào luôn tốt cho mọi hệ thống; cần cân đối số điểm, tần suất cập nhật, độ trễ, topology và yêu cầu truy vấn.

### 20.3. Hash tag không biến một key thành dữ liệu phân tán

Redis Cluster có hash tag `{...}` để đặt nhiều key vào cùng slot, nhưng một key GEO bản thân đã có cùng slot cho mọi member. Thêm `{branches}` vào một key không làm nó trải trên nhiều node.

Nếu cần transaction cập nhật đồng thời GEO key và metadata key trong Cluster, cả các key tham gia phải đáp ứng quy tắc cùng slot. Hash tag giúp đồng vị trí có chủ đích, nhưng dùng hash tag quá rộng sẽ làm tập trung tải lên một slot.

## 21. Tính nhất quán khi cập nhật vị trí

Giả sử service nhận cập nhật vị trí liên tiếp của một driver:

```text
t1: driver-101 -> (106.7000, 10.7700)
t2: driver-101 -> (106.7010, 10.7710)
```

Cùng member ID được `GEOADD` hai lần. Redis lưu vị trí ở lần cập nhật **được thực thi sau cùng**, nhưng nó không tự biết timestamp của thiết bị. Nếu event t1 đến muộn sau t2 do network/retry, tọa độ cũ có thể ghi đè tọa độ mới.

Để tránh điều này, có thể duy trì timestamp/version đáng tin cậy cùng vị trí và áp dụng quy tắc “chỉ chấp nhận event mới hơn”. Nếu cần kiểm tra version và cập nhật GEO atomically, phải thiết kế thao tác thích hợp (chẳng hạn script trên cùng slot/server, kiểm soát input và lỗi) chứ không chỉ gọi hai Redis command rời rạc.

Tương tự:

```text
1. GEOADD cập nhật location
2. HSET cập nhật updatedAt
```

Nếu ứng dụng chết giữa hai bước, GEO index và timestamp không khớp. Với trạng thái cần nhất quán cao, cần một cơ chế ghi quản lý cả hai và khôi phục lỗi; với tracking eventual consistency, có thể dùng message/outbox và worker sửa dữ liệu stale.

### Tính idempotent của `GEOADD`

Gọi `GEOADD` lặp lại với **cùng member và cùng tọa độ** sẽ giữ trạng thái cuối cùng như nhau. Đây là đặc tính thuận tiện cho retry khi gửi cập nhật vị trí. Nhưng nếu hai event khác nhau đến sai thứ tự, lặp lại một event cũ vẫn có thể làm vị trí đi lùi; idempotency không thay thế việc quản lý version/time ordering.

## 22. Hiệu năng truy vấn GEO: những điều cần đo

Redis dùng chỉ mục không gian nội bộ để giảm công việc so với quét từng tọa độ bằng code thông thường. Tuy vậy, không nên suy ra mỗi lệnh `GEOSEARCH` đều có độ trễ cố định khi số điểm tăng.

Các yếu tố ảnh hưởng:

- **Số member trong GEO key:** index nhiều điểm cần nhiều RAM, đặc biệt nếu payload metadata nằm ở các key khác.
- **Mật độ điểm:** bán kính 2 km trong khu vực đông điểm có thể trả rất nhiều candidate.
- **Bán kính tìm kiếm:** vùng lớn thường phải xét nhiều điểm hơn.
- **`WITHDIST`/`WITHCOORD`:** thêm dữ liệu vào response; ảnh hưởng băng thông và xử lý kết quả.
- **`ASC`/`DESC` và `COUNT`:** sắp xếp, giới hạn kết quả và tối ưu có thể đổi chi phí thực tế.
- **Tần suất `GEOADD`:** GPS update liên tục có thể tạo nhiều lệnh ghi.
- **Redis Cluster:** một GEO key nóng bị giới hạn bởi primary sở hữu slot của nó.
- **Đọc metadata sau GEO:** việc tìm chi nhánh rồi đọc 50 bản ghi chi tiết có thể tốn thêm round-trip.

Đo latency Redis, kích thước response, số candidate và thời gian deserialize/logic Java. Có thể batch đọc metadata theo ID nếu mô hình lưu trữ phù hợp và cân nhắc giới hạn Cluster cho lệnh đa key. Đừng chuyển vấn đề N+1 Redis requests từ việc tìm vị trí sang việc lấy dữ liệu chi tiết mà không đo.

### Dùng khoảng cách địa lý để xếp hạng chưa đủ

“Gần nhất theo `GEODIST`” là gần nhất theo khoảng cách đường thẳng ước lượng. Một điểm gần về tọa độ có thể xa hơn theo lộ trình giao hàng thực tế. Nhiều ứng dụng dùng hai bước:

```text
Redis GEO
    |
    | lọc nhanh 20–50 điểm gần theo đường thẳng
    v
Routing / business rules
    |
    | tính quãng đường thực tế, thời gian, trạng thái
    v
Kết quả xếp hạng cuối cùng
```

Số candidate là quyết định theo tải và độ chính xác mong muốn; không có ngưỡng chuẩn cho mọi nơi.

## 23. Bảo mật và quyền riêng tư của dữ liệu vị trí

Tọa độ có thể là dữ liệu nhạy cảm, đặc biệt khi gắn với một người dùng, tài xế hoặc thiết bị. Dù Redis lưu GEO trong Sorted Set, nó **không phải một hình thức mã hóa bảo vệ thông tin**. Người có quyền truy cập key và lệnh thích hợp có thể lấy vị trí member.

Các biện pháp thực tế:

- Dùng member ID nội bộ thay vì email, số điện thoại hoặc token.
- Kiểm soát ai được ghi `GEOADD` và đọc `GEOPOS`/`GEOSEARCH` theo quyền nghiệp vụ.
- Dùng credential/ACL Redis và TLS khi môi trường yêu cầu.
- Không trả danh sách mọi tài xế/khách hàng trong bán kính nếu người gọi không được phép nhìn thấy họ.
- Giới hạn độ chính xác được chia sẻ theo mục đích; đôi khi chỉ cần khu vực gần đúng.
- Quy định thời gian lưu trạng thái, cơ chế xóa dữ liệu khi không còn cần thiết, và chính sách log/backup phù hợp.
- Không in tọa độ người dùng thật, lịch sử di chuyển hoặc vị trí chính xác vào log debug không có kiểm soát.

Namespace như `shop:prod:drivers:geo` giúp tổ chức key, nhưng **không tự tạo ranh giới bảo mật** nếu cùng credential có quyền truy cập rộng.

## 24. Lỗi phổ biến và cách điều tra

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `GEOADD` bị từ chối tọa độ | Kinh/vĩ độ đảo, vĩ độ vượt giới hạn Redis, NaN/Infinity | Kiểm tra `longitude latitude` và miền giá trị |
| `geo.add` trả `0` | Member đã có và được cập nhật tọa độ | Không coi 0 là lỗi; xem `GEOPOS` nếu cần quan sát |
| `geo.distance` trả `null` | Một hoặc cả hai member không có trong cùng GEO key | Kiểm tra key, ID và `GEOPOS` |
| Khoảng cách hiển thị lớn/gấp 1.000 lần | Nhầm mét với kilômét | Gắn rõ `Metrics.KILOMETERS` hoặc quy đổi đúng |
| Vị trí lệch nhiều kilômét | Đảo longitude/latitude hoặc sai hệ tọa độ/input | So sánh số gốc, xác minh thứ tự `Point(x,y)` |
| Tọa độ `GEOPOS` khác vài chữ số | Redis lượng tử hóa tọa độ GEO | Không dùng GEO thay lưu trữ tọa độ gốc khi cần chính xác tuyệt đối |
| `TYPE key` trả `zset` thay vì `geo` | Đúng thiết kế Redis GEO | Dùng GEO commands; tránh `ZADD` score tùy ý |
| `GEOSEARCH` không thấy member dù có metadata | GEO index không được cập nhật hoặc key/member khác | Kiểm tra `ZCARD`, `GEOPOS`, namespace, TTL |
| Cửa hàng đã xóa vẫn xuất hiện | Quên `geo.remove` khi xóa metadata | Dọn index và thiết lập reconciliation |
| Truy vấn quá rộng trả rất nhiều điểm | Bán kính lớn, mật độ điểm cao, không giới hạn kết quả | Giới hạn input và đo chi phí truy vấn |
| Lỗi `CROSSSLOT` khi đồng thời cập nhật nhiều key | GEO key và metadata/index key ở slot khác nhau | Thiết kế co-location hoặc eventual consistency |
| GPS cũ ghi đè GPS mới | Event đến sai thứ tự, không có version check | Lưu timestamp/version và xác thực trước upsert |

Một số lệnh quan sát trên môi trường được phép:

```bash
redis-cli TYPE shop:dev:branches:geo
redis-cli ZCARD shop:dev:branches:geo
redis-cli GEOPOS shop:dev:branches:geo branch-01
redis-cli GEODIST shop:dev:branches:geo branch-01 branch-02 km
redis-cli TTL shop:dev:branches:geo
```

Không cần dùng `KEYS *` để kiểm tra một GEO key cụ thể. Tránh tải dữ liệu vị trí của người dùng thật vào môi trường không được phép hoặc chia sẻ log chứa tọa độ nhạy cảm.

## 25. Thực hành Redis CLI từ đầu đến cuối

Phần này dùng key thử nghiệm `demo:lesson158:geo`. Chỉ chạy trên Redis được phép sử dụng cho thực hành.

### Bước 1 — Ghi ba vị trí

```bash
redis-cli GEOADD demo:lesson158:geo 106.7010 10.7760 branch-01 106.7080 10.7810 branch-02 106.6950 10.7740 branch-03
```

Kiểm tra loại dữ liệu và số member:

```bash
redis-cli TYPE demo:lesson158:geo
# zset

redis-cli ZCARD demo:lesson158:geo
# 3
```

### Bước 2 — Đọc tọa độ

```bash
redis-cli GEOPOS demo:lesson158:geo branch-01 branch-02
```

Quan sát Redis trả về **longitude trước, latitude sau**. Tọa độ trả về có thể khác một chút so với input do độ phân giải của GEO index.

### Bước 3 — Tính khoảng cách

```bash
redis-cli GEODIST demo:lesson158:geo branch-01 branch-02 m
redis-cli GEODIST demo:lesson158:geo branch-01 branch-02 km
redis-cli GEODIST demo:lesson158:geo branch-01 branch-02 mi
```

Các kết quả thể hiện cùng một khoảng cách vật lý được quy đổi sang những đơn vị khác nhau. Không cần tự viết công thức Haversine chỉ để đo khoảng cách giữa hai member nằm trong GEO key của Redis.

### Bước 4 — Tìm trong bán kính

```bash
redis-cli GEOSEARCH demo:lesson158:geo FROMLONLAT 106.7009 10.7769 BYRADIUS 3 km ASC COUNT 10 WITHDIST WITHCOORD
```

Kiểm tra danh sách ID, khoảng cách và tọa độ. Với dữ liệu minh họa, kết quả phụ thuộc vị trí và bán kính đã chọn; không cần suy ra quãng đường giao thông thực tế từ kết quả này.

### Bước 5 — Cập nhật một vị trí

```bash
redis-cli GEOADD demo:lesson158:geo 106.7020 10.7770 branch-01
redis-cli GEOPOS demo:lesson158:geo branch-01
redis-cli ZCARD demo:lesson158:geo
```

Dù `GEOADD` trả `0` vì `branch-01` đã tồn tại, vị trí được ghi cập nhật và tổng số member không tăng.

### Bước 6 — Xóa member và kiểm tra trường hợp thiếu

```bash
redis-cli ZREM demo:lesson158:geo branch-03
redis-cli GEOPOS demo:lesson158:geo branch-03
redis-cli GEODIST demo:lesson158:geo branch-01 branch-03 km
```

`GEOPOS`/`GEODIST` với member đã xóa sẽ cho kết quả nil tương ứng; đó là trường hợp không có dữ liệu, không phải khoảng cách bằng 0.

### Bước 7 — Quan sát TTL

```bash
redis-cli TTL demo:lesson158:geo
# Thường là -1 vì key tồn tại và chưa được đặt expiry.
```

Đối với dữ liệu chi nhánh tĩnh, thông thường không cần đặt TTL ngắn cho toàn bộ GEO key. Nếu thực hành TTL:

```bash
redis-cli EXPIRE demo:lesson158:geo 60
redis-cli TTL demo:lesson158:geo
```

Cả GEO key sẽ hết hạn khi TTL kết thúc; nó không xóa các member lần lượt dựa trên thời điểm được thêm.

## 26. Câu hỏi tự kiểm tra

**1. Redis `GEOADD` yêu cầu kinh độ hay vĩ độ trước?**

Kinh độ trước, vĩ độ sau: `GEOADD key longitude latitude member`. Trong Spring Data Redis, `new Point(longitude, latitude)`.

**2. `TYPE` của một Redis key GEO trả `geo` hay `zset`?**

`zset`. Redis lưu member địa lý dưới dạng Sorted Set có score mã hóa vị trí.

**3. Vì sao `GEOADD` có thể trả 0 nhưng vị trí đã đổi?**

Vì lệnh mặc định đếm member **mới**. Ghi lại member cũ với tọa độ mới có thể cập nhật thành công mà không tăng số member.

**4. `GEODIST` có thể đo giữa hai member trong hai GEO key khác nhau không?**

Không theo API native của một lệnh `GEODIST`. Cả hai member phải tồn tại trong cùng key được truyền vào lệnh, hoặc ứng dụng phải lấy tọa độ và tính theo cách khác.

**5. Khi `distance(...)` trả `null`, có nên hiển thị 0 km không?**

Không. `null` có thể có nghĩa một hoặc cả hai member không tồn tại; 0 km là khoảng cách hợp lệ của hai vị trí trùng nhau.

**6. Khoảng cách Redis GEO có phải lộ trình lái xe không?**

Không. Redis trả khoảng cách địa lý theo mô hình của nó, không xét đường sá, cầu, kẹt xe hoặc tốc độ di chuyển.

**7. Muốn tìm địa điểm trong bán kính 3 km quanh tọa độ khách hàng chưa có member, dùng gì?**

Dùng `GEOSEARCH ... FROMLONLAT ... BYRADIUS 3 km`, hoặc API `GeoOperations.radius` với `Circle(Point, Distance)`; không cần ghi một member tạm cho khách hàng.

**8. TTL có áp dụng riêng từng member GEO không?**

Không theo cơ chế TTL thông thường. TTL áp dụng trên toàn bộ GEO key (Sorted Set); cần giải pháp riêng để phát hiện và loại những member quá cũ.

**9. Khi tracking GPS liên tục, vì sao cần timestamp/version?**

Vì cập nhật đến sai thứ tự có thể làm tọa độ cũ ghi đè tọa độ mới. `GEOADD` không tự hiểu timestamp thiết bị hoặc tự loại event cũ.

**10. Vì sao một GEO key cực lớn có thể là điểm nóng trong Redis Cluster?**

Một Redis key chỉ thuộc một hash slot và một primary node tại một thời điểm. Chia dữ liệu thành nhiều key có thể phân phối tải nhưng làm phức tạp truy vấn xuyên khu vực và ranh giới địa lý.

## 27. Kết luận

Redis Geospatial cho phép lưu tọa độ và truy vấn khoảng cách theo member một cách thuận tiện. Trong Spring Data Redis, **`GeoOperations.add(...)`** tương ứng việc ghi/cập nhật vị trí bằng `GEOADD`, **`position(...)`** đọc tọa độ thông qua `GEOPOS`, còn **`distance(...)`** đo khoảng cách qua `GEODIST` với đơn vị được lựa chọn rõ ràng. Truy vấn bán kính có thể dùng `GEOSEARCH` ở Redis hiện đại hoặc API `GeoOperations.radius(...)` của Spring Data Redis.

Khi thiết kế, phải đặc biệt chú ý **longitude trước latitude**, tính đúng đơn vị mét/kilômét, member phải nằm trong cùng key khi tính `GEODIST`, và việc Redis lưu GEO bằng Sorted Set chứ không phải kiểu dữ liệu riêng. Khoảng cách GEO không phải khoảng cách đường bộ; vị trí đọc lại có độ chính xác hữu hạn; TTL áp dụng cho toàn bộ key chứ không từng điểm. Cuối cùng, GEO index chỉ thực sự đáng tin cậy khi ứng dụng quản lý tốt cập nhật member, dữ liệu chi tiết, timestamp, quyền truy cập và cách phân vùng Redis Cluster.
