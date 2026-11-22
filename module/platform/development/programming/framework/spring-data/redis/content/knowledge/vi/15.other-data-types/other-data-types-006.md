# Tìm điểm lân cận theo khả năng API và Redis Server

Một hệ thống cửa hàng, giao hàng hoặc dịch vụ theo vị trí thường cần tính năng **“tìm các điểm gần tọa độ hiện tại”**: người dùng gửi kinh độ/vĩ độ, ứng dụng tìm những cửa hàng nằm trong phạm vi vài kilômét, có thể sắp xếp từ gần đến xa và giới hạn số kết quả.

**Spring Data Redis** cung cấp `GeoOperations` để thao tác với dữ liệu địa lý của Redis. Tuy nhiên, việc một method tồn tại trong thư viện Java không có nghĩa mọi **Redis Server** đều hiểu command phía dưới. Redis 3.2 đã hỗ trợ `GEOADD` và truy vấn bán kính kiểu cũ; đến Redis **6.2** mới xuất hiện `GEOSEARCH` và `GEOSEARCHSTORE` với cú pháp thống nhất cho hình tròn và hình chữ nhật.

Bài học tập trung vào ba vấn đề: cách sử dụng API Spring Data Redis, giới hạn theo phiên bản Redis Server, và cách trả lời chính xác câu hỏi “điểm gần nhất” mà không nhầm khoảng cách địa lý, kết quả bất kỳ hoặc điểm thỏa thêm điều kiện nghiệp vụ.

> **Phạm vi kỹ thuật:** Ví dụ Java hướng tới Spring Boot 3.3.x / Spring Data Redis 3.3.x, dùng Lettuce qua `spring-boot-starter-data-redis`. Ví dụ `GEOSEARCH` giả định Redis Server **6.2+**. Các tọa độ `store:1`, `store:2` trong bài chỉ là dữ liệu thử, không phải cửa hàng thực tế.

## 1. Redis lưu dữ liệu GEO như thế nào?

Redis không có một kiểu dữ liệu được báo tên là `geo` qua lệnh `TYPE`. Dữ liệu địa lý được mã hóa vào một **Sorted Set (ZSET)**. Mỗi member của ZSET là một ID, còn score chứa biểu diễn vị trí địa lý do Redis tạo ra.

~~~text
demo:shops (Redis type = zset)
  member store:1 → vị trí 106.7000, 10.7760
  member store:2 → vị trí 106.7050, 10.7780
  member store:3 → vị trí 106.7250, 10.7950
~~~

Để ghi đúng định dạng, hãy dùng `GEOADD`, không tự gán score qua `ZADD` bằng một giá trị bất kỳ.

~~~redis
GEOADD demo:shops 106.7000 10.7760 store:1
GEOADD demo:shops 106.7050 10.7780 store:2
GEOADD demo:shops 106.7250 10.7950 store:3
TYPE demo:shops
ZCARD demo:shops
~~~

`TYPE` trả `zset` và `ZCARD` trả số member của index. Redis có thể xử lý hàng loạt member bằng một `GEOADD`:

~~~redis
GEOADD demo:shops 106.7000 10.7760 store:1 106.7050 10.7780 store:2
~~~

Khi ghi lại tọa độ cho một member đã có, Redis cập nhật vị trí của member đó, thay vì tạo bản sao thứ hai. **Số trả về của `GEOADD` thường là số member mới được thêm**, vì vậy giá trị 0 không nhất thiết nghĩa là cập nhật vị trí thất bại.

### 1.1. Một GEO index lưu những gì?

~~~mermaid
flowchart LR
    A["GEOADD key longitude latitude member"] --> B["Redis ZSET"]
    B --> C["member ID"]
    B --> D["score mã hóa tọa độ"]
    C --> E["GEOSEARCH"]
    D --> E
    E --> F["ID gần tâm truy vấn"]
~~~

Redis GEO phù hợp cho:

- Lọc các điểm trong **bán kính** quanh tọa độ.
- Lọc các điểm trong **hình chữ nhật** quanh tọa độ, trên Redis Server hỗ trợ.
- Lấy khoảng cách giữa các member đã lưu.
- Xem tọa độ của member.
- Lấy các member gần nhất theo khoảng cách và giới hạn kết quả.

Nó **không** tự giải quyết việc tìm tuyến đường, thời gian chạy xe, dữ liệu giao thông, tìm trong đa giác địa lý phức tạp, điều kiện “cửa hàng đang mở” hoặc truy vấn đa tiêu chí kiểu SQL.

## 2. Thứ tự tọa độ: longitude trước, latitude sau

Một nguồn lỗi rất phổ biến là đảo thứ tự tọa độ.

Redis dùng:

~~~text
longitude latitude
kinh độ   vĩ độ
~~~

Ví dụ:

~~~redis
GEOADD demo:shops 106.7000 10.7760 store:1
~~~

Trong Spring Data Redis:

~~~java
import org.springframework.data.geo.Point;

Point location = new Point(106.7000, 10.7760);
~~~

`Point.getX()` tương ứng **longitude**, `Point.getY()` là **latitude**. Một số SDK bản đồ biểu diễn thứ tự là `[latitude, longitude]`; không được bê nguyên thứ tự đó sang `new Point(x, y)`.

### 2.1. Phạm vi hợp lệ

| Thành phần | Phạm vi Redis GEO | Lưu ý |
|---|---|---|
| Longitude | `-180` đến `180` | Kinh độ |
| Latitude | Khoảng `-85.05112878` đến `85.05112878` | Không phải toàn bộ `-90` đến `90` |
| Radius | Số dương và đơn vị hợp lệ | Giới hạn tối đa nên do ứng dụng đặt |
| Đơn vị | `m`, `km`, `ft`, `mi` | Phải thống nhất khi hiển thị |

Redis GEO hỗ trợ latitude hẹp hơn phạm vi vĩ độ lý thuyết. Khi nhận tọa độ từ API, cần kiểm tra giá trị hữu hạn, phạm vi đúng và chiều tọa độ đúng **trước khi ghi vào Redis hoặc truy vấn**.

### 2.2. Redis tính khoảng cách nào?

Redis GEO trả khoảng cách địa lý gần đúng, thường được hiểu là **đường chim bay** giữa hai vị trí trên bề mặt Trái Đất. Nó không đo quãng đường thực tế qua cầu, đường một chiều, giao thông hay địa hình.

Vì vậy:

- `1.5 km` từ Redis không chứng minh lái xe chỉ đi 1.5 km.
- Redis không biết vận tốc hay tình trạng tắc đường.
- Nếu yêu cầu ETA, thời gian giao hàng hoặc đường đi, cần dịch vụ định tuyến riêng.

Dữ liệu tọa độ cũng được mã hóa với độ chính xác hữu hạn, nên `GEOPOS` có thể trả số hơi khác tọa độ input.

## 3. Khả năng Redis Server theo phiên bản

Đây là bảng cần xem trước khi lựa chọn method Spring Data Redis:

| Redis command | Có từ Redis OSS | Công dụng |
|---|---|---|
| `GEOADD` | 3.2 | Thêm/cập nhật member và tọa độ |
| `GEOPOS` | 3.2 | Lấy tọa độ của member |
| `GEODIST` | 3.2 | Khoảng cách giữa hai member |
| `GEOHASH` | 3.2 | Xem giá trị geohash của member |
| `GEORADIUS` | 3.2 | Tìm theo bán kính từ tọa độ, legacy |
| `GEORADIUSBYMEMBER` | 3.2 | Tìm theo bán kính từ member, legacy |
| `GEOSEARCH` | **6.2** | Tìm theo hình tròn hoặc hình chữ nhật, tâm tọa độ hoặc member |
| `GEOSEARCHSTORE` | **6.2** | Tìm và lưu kết quả vào destination |

Từ Redis 6.2, `GEORADIUS` và `GEORADIUSBYMEMBER` được đánh dấu **deprecated**. Chúng không biến mất ngay khỏi mọi phiên bản Redis mới, nhưng lệnh khuyến nghị cho code mới là `GEOSEARCH` và `GEOSEARCHSTORE`.

### 3.1. Kiểm tra version và command thật

Ví dụ với Redis local mà bạn được phép kiểm tra:

~~~bash
redis-cli -h localhost -p 6379 INFO server
redis-cli -h localhost -p 6379 COMMAND INFO GEOSEARCH
redis-cli -h localhost -p 6379 COMMAND INFO GEOSEARCHSTORE
~~~

Dòng `redis_version` cho biết version server. `COMMAND INFO` giúp xác định command được server nhận diện; trên server không có command, kết quả có thể là null/không có thông tin theo phiên bản.

Một ứng dụng dùng **Spring Data Redis 3.3** vẫn có thể kết nối đến **Redis 5.x**. Khi đó gọi `GEOSEARCH` trực tiếp sẽ gặp lỗi kiểu `ERR unknown command 'GEOSEARCH'`.

### 3.2. Ba tầng phải cùng đáp ứng

~~~mermaid
flowchart TD
    A["Ứng dụng gọi GeoOperations.search"] --> B{"Thư viện Spring Data Redis có search()?"}
    B -->|Không| C["Dùng API tương thích hoặc nâng cấp thư viện"]
    B -->|Có| D{"Driver/connection hỗ trợ mapping?"}
    D -->|Không| E["Thay đổi implementation phù hợp"]
    D -->|Có| F{"Redis Server hỗ trợ GEOSEARCH từ 6.2?"}
    F -->|Không| G["Dùng đường legacy radius() khi đủ yêu cầu"]
    F -->|Có| H["Thực thi GEOSEARCH"]
~~~

**API có trong Java ≠ command có trên server**. Không nên giả định Spring Data Redis sẽ tự động đổi `GEOSEARCH` thành `GEORADIUS` khi server báo không hiểu lệnh. Muốn hỗ trợ server cũ thì cần chọn chiến lược tương thích một cách tường minh.

## 4. Dùng Spring Data Redis để lưu và quản lý vị trí

Starter phổ biến trong dự án Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Với `StringRedisTemplate`:

~~~java
import org.springframework.data.geo.Point;
import org.springframework.data.redis.core.GeoOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ShopLocationStore {

    private static final String KEY = "demo:shops";

    private final GeoOperations<String, String> geo;

    public ShopLocationStore(StringRedisTemplate template) {
        this.geo = template.opsForGeo();
    }

    public void save(String shopId, double lon, double lat) {
        validate(lon, lat);
        geo.add(KEY, new Point(lon, lat), shopId);
    }

    public void delete(String shopId) {
        geo.remove(KEY, shopId);
    }

    private void validate(double lon, double lat) {
        if (!Double.isFinite(lon) || !Double.isFinite(lat)
                || lon < -180 || lon > 180
                || lat < -85.05112878 || lat > 85.05112878) {
            throw new IllegalArgumentException("Invalid GEO coordinate");
        }
    }
}
~~~

Lưu:

~~~java
store.save("store:1", 106.7000, 10.7760);
store.save("store:2", 106.7050, 10.7780);
store.save("store:3", 106.7250, 10.7950);
~~~

`GeoOperations<String, String>` có hai generic:

- `K = String`: Redis key ngoài cùng, ví dụ `demo:shops`.
- `M = String`: member ID trong GEO index, ví dụ `store:1`.

Không nên đưa toàn bộ object cửa hàng làm member nếu nghiệp vụ chỉ cần ID. Có thể lưu profile cửa hàng ở Hash/JSON hoặc database nguồn, còn GEO index giữ ID và vị trí.

### 4.1. Ghi nhiều tọa độ trong một lời gọi

~~~java
import java.util.Map;
import org.springframework.data.geo.Point;

Map<String, Point> coordinates = Map.of(
        "store:1", new Point(106.7000, 10.7760),
        "store:2", new Point(106.7050, 10.7780),
        "store:3", new Point(106.7250, 10.7950)
);

Long added = geo.add("demo:shops", coordinates);
~~~

Giá trị `added` phản ánh số member mới được thêm theo command, không nhất thiết là tổng số member được cập nhật. Trong pipeline/transaction, một số method Spring Data Redis có thể trả `null` khi chưa thu thập response.

### 4.2. Đọc tọa độ và khoảng cách

~~~java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

Distance distanceKm = geo.distance(
        "demo:shops",
        "store:1",
        "store:2",
        Metrics.KILOMETERS
);

java.util.List<Point> positions = geo.position(
        "demo:shops",
        "store:1",
        "store:2"
);
~~~

`GEODIST` cần **hai member đã lưu trong cùng GEO index**. Nếu một member không tồn tại, khoảng cách có thể là `null`. `position()` có thể trả phần tử null tương ứng với member chưa có; không được bỏ qua thứ tự phản hồi khi ánh xạ về ID.

## 5. Tìm điểm trong bán kính bằng Redis `GEOSEARCH`

Từ Redis 6.2, truy vấn từ tọa độ:

~~~redis
GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km
~~~

Điều này yêu cầu tất cả member trong index có vị trí nằm trong hình tròn tâm `(106.7000, 10.7760)`, bán kính 2 km.

Một lệnh có sắp xếp và trả chi tiết:

~~~redis
GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km ASC COUNT 10 WITHDIST WITHCOORD
~~~

Ý nghĩa các phần:

| Phần lệnh | Ý nghĩa |
|---|---|
| `FROMLONLAT lon lat` | Chọn tọa độ làm tâm |
| `FROMMEMBER id` | Chọn một member đã có làm tâm |
| `BYRADIUS 2 km` | Vùng tìm theo bán kính 2 km |
| `BYBOX 4 3 km` | Vùng hình chữ nhật rộng 4 km, cao 3 km |
| `ASC` | Sắp xếp gần tới xa |
| `DESC` | Sắp xếp xa tới gần |
| `COUNT 10` | Tối đa 10 kết quả |
| `WITHDIST` | Trả khoảng cách từ tâm theo đơn vị query |
| `WITHCOORD` | Trả longitude/latitude mỗi member |
| `WITHHASH` | Trả geohash score của member |

Nếu không chỉ định sort, **không nên giả định kết quả được sắp từ gần đến xa**. Nếu không chỉ định `WITHDIST`, cũng không nên giả định response chứa khoảng cách.

### 5.1. `COUNT` và `COUNT ... ANY` khác nhau

~~~redis
GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km ASC COUNT 10
~~~

Đây là lệnh thích hợp hơn nếu mục tiêu là **10 điểm gần nhất trong vùng** theo khả năng tìm kiếm/sắp xếp của Redis.

Tùy chọn:

~~~redis
GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km COUNT 10 ANY
~~~

cho phép Redis dừng tìm kiếm sau khi có đủ ứng viên. Điều này có thể giảm công tìm trên vùng lớn, nhưng **không bảo đảm đó là 10 điểm gần nhất tuyệt đối trong toàn bộ phạm vi**. Nếu kết hợp `ASC` với `ANY`, người dùng vẫn phải hiểu rằng tập ứng viên có thể bị giới hạn sớm.

| Nhu cầu | Lựa chọn |
|---|---|
| “10 điểm gần nhất” | `ASC COUNT 10`, không bật `ANY` |
| “Tối đa 10 điểm bất kỳ trong vùng” | Có thể dùng `COUNT 10 ANY` |
| “Tất cả điểm trong vùng” | Không đặt COUNT, nhưng phải giới hạn/đo tải |
| “10 điểm xa nhất trong vùng” | `DESC COUNT 10` |

`COUNT 10` là **số tối đa**, không bảo đảm vùng có đủ 10 member.

## 6. Tìm quanh một member đã lưu

Khi tâm là một member của index, dùng `FROMMEMBER`:

~~~redis
GEOSEARCH demo:shops FROMMEMBER store:1 BYRADIUS 1 km ASC WITHDIST
~~~

Redis dùng tọa độ đã lưu của `store:1`. Điều này hữu ích cho truy vấn “các điểm khác gần cửa hàng X” khi chưa có tọa độ cửa hàng tại code.

Những điểm cần lưu ý:

- `store:1` phải tồn tại trong index.
- Member làm tâm có thể xuất hiện trong kết quả với khoảng cách gần 0.
- Nếu chỉ muốn các cửa hàng **khác**, cần lọc member tâm theo quy tắc nghiệp vụ.
- Nếu yêu cầu 10 cửa hàng khác, việc yêu cầu `COUNT 10` có thể chỉ còn 9 sau khi loại tâm; có thể lấy thêm ứng viên và giới hạn lại ở Java.

Ví dụ:

~~~redis
GEOSEARCH demo:shops FROMMEMBER store:1 BYRADIUS 2 km ASC COUNT 11 WITHDIST
~~~

Sau đó loại `store:1` và giữ tối đa 10 member khác nếu có. Không tự giả định Redis có tùy chọn mặc định “exclude center”.

## 7. Spring Data Redis `GeoOperations.search()`

Spring Data Redis 3.3 có các overload `GeoOperations.search()` để diễn đạt `GEOSEARCH`:

- `search(key, GeoReference, Distance)`: tìm trong hình tròn với tâm được chỉ định.
- `search(key, GeoReference, Distance, GeoSearchCommandArgs)`: thêm sort, giới hạn, distance, coordinates.
- `search(key, GeoReference, BoundingBox)`: tìm trong hình chữ nhật.
- `search(key, GeoReference, BoundingBox, GeoSearchCommandArgs)`: tìm trong hình chữ nhật kèm tùy chọn.

Những class thường dùng:

| Class | Package | Vai trò |
|---|---|---|
| `GeoOperations` | `org.springframework.data.redis.core` | API Redis GEO |
| `GeoReference` | `org.springframework.data.redis.domain.geo` | Chọn tâm từ member hoặc tọa độ |
| `Point` | `org.springframework.data.geo` | Longitude/latitude |
| `Distance` | `org.springframework.data.geo` | Giá trị và đơn vị khoảng cách |
| `Metrics` | `org.springframework.data.geo` | Meters/kilometers... |
| `BoundingBox` | `org.springframework.data.geo` | Rộng/cao của vùng hình chữ nhật |
| `GeoResults` / `GeoResult` | `org.springframework.data.geo` | Danh sách kết quả và từng kết quả |
| `GeoLocation` | `RedisGeoCommands.GeoLocation` | Tên và vị trí member |
| `GeoSearchCommandArgs` | `RedisGeoCommands.GeoSearchCommandArgs` | Sort, limit, WITHDIST/WITHCOORD |

### 7.1. Ví dụ tìm gần nhất theo tọa độ

~~~java
import java.util.List;
import java.util.Objects;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoLocation;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoSearchCommandArgs;
import org.springframework.data.redis.core.GeoOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.domain.geo.GeoReference;
import org.springframework.stereotype.Service;

@Service
public class NearbyShopService {

    private static final String KEY = "demo:shops";
    private final GeoOperations<String, String> geo;

    public NearbyShopService(StringRedisTemplate redis) {
        this.geo = redis.opsForGeo();
    }

    public record NearbyShop(
            String id,
            double distanceKm,
            Point position
    ) {}

    public List<NearbyShop> findNearest(
            double longitude,
            double latitude,
            double radiusKm,
            int maxResults
    ) {
        if (!Double.isFinite(longitude)
                || !Double.isFinite(latitude)
                || longitude < -180 || longitude > 180
                || latitude < -85.05112878
                || latitude > 85.05112878) {
            throw new IllegalArgumentException("Invalid coordinate");
        }

        // Giới hạn minh họa của ứng dụng, không phải của Redis.
        if (!Double.isFinite(radiusKm)
                || radiusKm <= 0 || radiusKm > 20
                || maxResults < 1 || maxResults > 50) {
            throw new IllegalArgumentException(
                    "Invalid radius/limit"
            );
        }

        GeoSearchCommandArgs args =
                GeoSearchCommandArgs.newGeoSearchArgs()
                        .includeDistance()
                        .includeCoordinates()
                        .sortAscending()
                        .limit(maxResults);

        GeoResults<GeoLocation<String>> result = geo.search(
                KEY,
                GeoReference.fromCoordinate(
                        longitude,
                        latitude
                ),
                new Distance(
                        radiusKm,
                        Metrics.KILOMETERS
                ),
                args
        );

        if (result == null) {
            // Có thể chưa có response nếu đang queue trong
            // pipeline/transaction; ví dụ kỳ vọng direct call.
            throw new IllegalStateException(
                    "Expected direct GEO result"
            );
        }

        return result.getContent().stream()
                .map(item -> new NearbyShop(
                        item.getContent().getName(),
                        Objects.requireNonNull(
                                item.getDistance()
                        ).getValue(),
                        item.getContent().getPoint()
                ))
                .toList();
    }
}
~~~

Giải thích từng phần:

1. `GeoReference.fromCoordinate(longitude, latitude)` chỉ định tâm từ tọa độ.
2. `Distance(radiusKm, Metrics.KILOMETERS)` tránh nhập nhầm đơn vị.
3. `sortAscending()` yêu cầu kết quả gần nhất trước.
4. `limit(maxResults)` giới hạn response, ví dụ không dùng `ANY`.
5. `includeDistance()` yêu cầu khoảng cách trong `GeoResult`.
6. `includeCoordinates()` yêu cầu tọa độ member trong `GeoLocation`.
7. DTO `NearbyShop` giữ dữ liệu cần cho ứng dụng thay vì lan truyền object framework khắp business code.

Giới hạn 20 km và 50 kết quả trong ví dụ là **quy tắc ứng dụng đặt để kiểm soát tài nguyên**, không phải giới hạn cứng của Redis. Nên chọn ngưỡng dựa trên mật độ dữ liệu và nhu cầu sản phẩm.

### 7.2. Truy vấn đơn giản không cần tham số bổ sung

~~~java
GeoResults<GeoLocation<String>> results = geo.search(
        "demo:shops",
        GeoReference.fromCoordinate(106.7000, 10.7760),
        new Distance(2, Metrics.KILOMETERS)
);
~~~

Đây là một phương án ngắn gọn khi chỉ cần tìm các member trong vùng. Nếu cần top-N gần nhất hoặc khoảng cách cụ thể, đừng suy đoán thứ tự/response mặc định; hãy truyền `GeoSearchCommandArgs`.

### 7.3. Truy vấn từ member trong Spring Data Redis

~~~java
GeoResults<GeoLocation<String>> aroundStore = geo.search(
        "demo:shops",
        GeoReference.fromMember("store:1"),
        new Distance(1, Metrics.KILOMETERS),
        GeoSearchCommandArgs.newGeoSearchArgs()
                .includeDistance()
                .sortAscending()
                .limit(10)
);
~~~

Cách này tương đương ý tưởng `FROMMEMBER store:1 BYRADIUS 1 km`. Nếu `store:1` vắng mặt, cần xử lý như một dữ liệu tâm không tồn tại, không xem như đang có một tọa độ mặc định.

## 8. Tìm trong hình chữ nhật: `BYBOX`

Redis 6.2+ hỗ trợ:

~~~redis
GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYBOX 4 3 km ASC WITHCOORD
~~~

`BYBOX 4 3 km` nghĩa là **hình chữ nhật rộng 4 km, cao 3 km**, không phải hình tròn bán kính 4 km.

Trong Java:

~~~java
import org.springframework.data.geo.BoundingBox;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoLocation;
import org.springframework.data.redis.domain.geo.GeoReference;

BoundingBox viewport = new BoundingBox(
        new Distance(4, Metrics.KILOMETERS),
        new Distance(3, Metrics.KILOMETERS)
);

GeoResults<GeoLocation<String>> points = geo.search(
        "demo:shops",
        GeoReference.fromCoordinate(106.7000, 10.7760),
        viewport
);
~~~

Dùng `BYBOX` khi yêu cầu là vùng chữ nhật quanh một tâm, ví dụ một viewport gần đúng. Dùng `BYRADIUS` khi yêu cầu thực sự là “điểm cách tôi không quá N km”.

Redis GEO cơ bản **không hỗ trợ truy vấn điểm nằm trong đa giác tùy ý** hoặc một vùng có lỗ/khe như nhiều bài toán GIS. Với polygon phức tạp, có thể dùng GEO để lấy ứng viên rồi áp bộ lọc hình học chính xác ở ứng dụng, hoặc sử dụng hệ thống geospatial search phù hợp.

## 9. API legacy `radius()` cho server trước Redis 6.2

Khi cần tương thích với Redis 3.2 đến 6.0, một truy vấn hình tròn có thể dùng `GeoOperations.radius()`:

~~~java
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.connection.RedisGeoCommands.GeoLocation;

Circle area = new Circle(
        new Point(106.7000, 10.7760),
        new Distance(2, Metrics.KILOMETERS)
);

GeoResults<GeoLocation<String>> legacy = geo.radius(
        "demo:shops",
        area
);
~~~

Ở cấp Redis, nhóm lệnh cũ gồm:

~~~redis
GEORADIUS demo:shops 106.7000 10.7760 2 km ASC WITHDIST
GEORADIUSBYMEMBER demo:shops store:1 2 km ASC WITHDIST
~~~

Redis 6.2 đánh dấu các lệnh này deprecated và khuyến nghị `GEOSEARCH`/`GEOSEARCHSTORE`. Nhưng code cần hỗ trợ server cũ vẫn có thể sử dụng đường legacy nếu server/driver tương ứng thực sự hỗ trợ.

| Nhu cầu | Server Redis 3.2–6.0 | Server Redis 6.2+ |
|---|---|---|
| Thêm vị trí | `GEOADD` | `GEOADD` |
| Đọc vị trí | `GEOPOS` | `GEOPOS` |
| Khoảng cách 2 member | `GEODIST` | `GEODIST` |
| Tìm bán kính tọa độ | `GEORADIUS` / `geo.radius()` | Ưu tiên `GEOSEARCH` / `geo.search()` |
| Tìm bán kính member | `GEORADIUSBYMEMBER` | `GEOSEARCH FROMMEMBER` |
| Hình chữ nhật | Không có `GEOSEARCH BYBOX` | `GEOSEARCH BYBOX` |
| Tìm và lưu kiểu mới | Không có `GEOSEARCHSTORE` | `GEOSEARCHSTORE` |

Đặc biệt, **không mặc định rằng `geo.search()` tự chuyển sang `geo.radius()` trên Redis 5**. Nếu hệ thống cần hỗ trợ nhiều version, có thể xác định capability ở thời điểm startup và chọn implementation, thay vì thử lệnh lỗi trên mọi request.

## 10. `GEOSEARCHSTORE`: tìm rồi lưu kết quả

`GEOSEARCH` trả danh sách member cho client, còn `GEOSEARCHSTORE` ghi kết quả vào một destination key dạng Sorted Set.

~~~redis
GEOSEARCHSTORE demo:shops:nearby demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km ASC COUNT 10
~~~

Trong đó:

- `demo:shops` là source GEO index.
- `demo:shops:nearby` là destination chứa kết quả tìm được.

Mặc định, score tại destination giữ thông tin vị trí địa lý theo encoding geospatial, nên có thể sử dụng như GEO index. Nếu thêm `STOREDIST`:

~~~redis
GEOSEARCHSTORE demo:shops:distances demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km ASC COUNT 10 STOREDIST
ZRANGE demo:shops:distances 0 -1 WITHSCORES
~~~

destination sẽ lưu **khoảng cách tới tâm làm score**. Nó là ZSET khoảng cách, không còn score vị trí theo cách GEO command mong đợi.

### 10.1. `GeoOperations.searchAndStore()`

~~~java
Long count = geo.searchAndStore(
        "demo:shops",
        "demo:shops:nearby",
        GeoReference.fromCoordinate(106.7000, 10.7760),
        new Distance(2, Metrics.KILOMETERS)
);
~~~

`count` là số member được lưu khi thực thi trực tiếp thành công. Trong pipeline/transaction, các operation có thể trả `null` tạm thời cho tới khi nhận response.

**Không ghi mọi kết quả người dùng vào cùng destination** nếu mỗi request có vị trí khác nhau. Khi cùng dùng `demo:shops:nearby`, request này có thể ghi đè kết quả của request kia. Với cache kết quả tạm, cần tên key theo phạm vi thích hợp, TTL và quy định quyền truy cập.

### 10.2. Hạn chế trong Redis Cluster

`GEOSEARCH` đọc một GEO index key, thường có thể được cluster-aware driver định tuyến tới slot của key đó. Nhưng `GEOSEARCHSTORE` truy cập **source và destination**, nên liên quan quy tắc multi-key của Redis Cluster.

Dùng hash tag khi cần hai key cùng slot:

~~~redis
GEOADD shops:{hcm} 106.7000 10.7760 store:1
GEOSEARCHSTORE shops:{hcm}:nearby shops:{hcm} FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km
~~~

Các key chứa tag `{hcm}` có cùng hash slot. Không nên đặt mọi geo index lớn vào cùng một tag toàn cầu; điều đó có thể tạo hot slot và làm mất lợi ích sharding.

## 11. Diễn giải kết quả `GeoResults` đúng ngữ nghĩa

`GeoOperations.search()` thường trả:

~~~java
GeoResults<GeoLocation<String>>
~~~

Mỗi phần tử là `GeoResult<GeoLocation<String>>`, với:

- `item.getContent().getName()`: ID member.
- `item.getContent().getPoint()`: tọa độ member khi được yêu cầu/được trả.
- `item.getDistance()`: khoảng cách tới tâm khi response cung cấp.

Khi không yêu cầu `WITHDIST` hoặc `WITHCOORD`, các thông tin tương ứng có thể không có. Không nên unbox/cast bừa một trường mà command không trả.

### 11.1. Không có kết quả không đồng nghĩa có lỗi

Nếu vùng tìm kiếm không chứa điểm nào, truy vấn thành công có thể trả **danh sách rỗng**. Điều này khác với:

- Redis Server không biết `GEOSEARCH`.
- Key chứa dữ liệu sai type.
- Tọa độ hoặc khoảng cách không hợp lệ.
- Redis mất kết nối, timeout hoặc ACL từ chối.
- Sai serializer của member/key.
- Đang gọi trong pipeline/transaction và method trả `null` trước khi response sẵn sàng.

Đừng bắt mọi exception rồi trả một danh sách rỗng; cách đó che mất vấn đề triển khai hay dữ liệu.

### 11.2. Member tâm có thể xuất hiện trong kết quả

Truy vấn `FROMMEMBER store:1` có thể trả chính `store:1`. Nếu sản phẩm cần “5 cửa hàng **khác** gần store:1”, phải loại member này và xử lý quota cẩn thận.

### 11.3. Khoảng cách không phải thời gian di chuyển

Khoảng cách GEO không bao gồm giao thông và tuyến đường thực tế. Nếu giao diện yêu cầu thời gian di chuyển, cần hệ thống routing/ETA độc lập. Không được chuyển thẳng `distanceKm` thành “số phút lái xe” với một tốc độ tùy ý rồi coi là ETA chính xác.

## 12. Chỉ GEO là chưa đủ để lọc điều kiện nghiệp vụ

Một yêu cầu thường gặp:

> “Tìm 10 cửa hàng gần nhất trong 3 km **đang mở cửa**, có hàng tồn kho.”

GEOSEARCH tìm theo vị trí. Nó không tự biết field `isOpen` hoặc tồn kho của mỗi member. Một luồng đơn giản:

~~~mermaid
flowchart TD
    A["Tọa độ người dùng"] --> B["GEOSEARCH trả ID ứng viên"]
    B --> C["Đọc profile/trạng thái/tồn kho"]
    C --> D["Lọc điều kiện nghiệp vụ"]
    D --> E["Trả tối đa 10 kết quả"]
~~~

Nhưng lưu ý:

~~~text
GEOSEARCH ASC COUNT 10 → 10 điểm gần nhất
Lọc theo "đang mở"      → còn 3 điểm
~~~

Có thể còn nhiều điểm đang mở khác trong bán kính, nhưng nằm ngoài 10 ứng viên đầu tiên. Vì vậy lấy 10 điểm gần nhất **trước khi lọc** không bảo đảm có đúng “10 điểm gần nhất thỏa điều kiện”.

Cách tiếp cận tùy độ chính xác yêu cầu:

1. **Lấy dư ứng viên**, rồi lọc và giữ tối đa 10 — nhanh trong một số tình huống nhưng vẫn có thể bỏ sót.
2. **Duy trì GEO index chuyên biệt** theo trạng thái/loại ít biến động, chấp nhận chi phí cập nhật index.
3. **Dùng bộ máy tìm kiếm/geospatial query** có thể phối hợp bộ lọc theo thuộc tính và khoảng cách.
4. **Materialized read model** được cập nhật từ nguồn dữ liệu chuẩn, nếu chấp nhận nhất quán cuối cùng.

Không có một lệnh GEO đơn giản nào tự thực hiện mọi điều kiện SQL/kinh doanh.

## 13. Hiệu năng, giới hạn và độ chính xác

`GEOSEARCH` sử dụng index vị trí, không cần quét từng Redis key rồi tính toán ở Java. Nhưng chi phí vẫn phụ thuộc vào vùng truy vấn và số lượng điểm.

Tài liệu Redis mô tả độ phức tạp lệnh theo số phần tử trong vùng bao và số kết quả thực sự phù hợp, không phải `O(1)` cho mọi bán kính. Truy vấn rộng trong khu vực cực kỳ dày đặc có thể tốn nhiều CPU và trả về một lượng dữ liệu lớn.

| Vấn đề | Hậu quả | Hướng xử lý |
|---|---|---|
| Radius không giới hạn | Query nặng, lượng kết quả lớn | Đặt ngưỡng theo nghiệp vụ |
| Không có COUNT | Trả nhiều member | Cấu hình page/limit phù hợp |
| Sort `ASC` trên vùng quá lớn | Tốn chi phí chọn/sắp xếp | Đo độ trễ, giới hạn vùng |
| `COUNT n ANY` | Có thể nhanh hơn nhưng không đảm bảo top-N gần nhất | Chỉ dùng khi chấp nhận |
| Một GEO key rất lớn | Có thể tạo điểm nóng bộ nhớ/CPU | Đánh giá sharding/phân vùng |
| Lọc sau khi giới hạn | Top-N sau lọc thiếu kết quả | Thiết kế filter/index đúng |
| Vị trí thay đổi liên tục | Data stale, nhiều write | Xác định tần suất cập nhật |
| Log tọa độ chính xác | Rủi ro quyền riêng tư | Giảm ghi log và kiểm soát retention |

Redis GEO dùng biểu diễn geohash hữu hạn, nên số tọa độ đọc lại không nhất thiết trùng từng chữ số với input. Đây không phải cơ sở dữ liệu GIS chính xác tùy ý hay công cụ đo đạc địa chính.

### 13.1. Partition theo vùng địa lý có đánh đổi

Có thể dùng:

~~~text
shops:geo:region-a
shops:geo:region-b
~~~

thay cho một GEO index toàn cục. Điều này giúp giảm độ lớn index hoặc phân bố tải trong một số hệ thống, nhưng điểm gần biên vùng có thể nằm trong index vùng kế bên.

Nếu tìm trong bán kính quanh ranh giới, ứng dụng có thể phải truy vấn nhiều vùng rồi gộp và sắp xếp lại. Nếu không, kết quả có thể bỏ sót cửa hàng gần nhất ở phía bên kia đường phân vùng.

Do đó, không nên coi ranh giới hành chính hoặc partition là ranh giới tuyệt đối của truy vấn bán kính.

## 14. Quy trình chẩn đoán khi không tìm được điểm

Một bảng phân biệt nguyên nhân:

| Hiện tượng | Khả năng cao | Điều nên kiểm tra |
|---|---|---|
| `unknown command GEOSEARCH` | Redis Server dưới 6.2 | `INFO server`, `COMMAND INFO` |
| GEOADD bị từ chối | Tọa độ sai thứ tự/phạm vi | Longitude trước, latitude sau |
| Trả rỗng dù có dữ liệu | Sai key/DB/radius/tọa độ | `TYPE`, `ZCARD`, `GEOPOS` |
| Không có thứ tự gần nhất | Quên `ASC` | `sortAscending()` hoặc `ASC` |
| Khoảng cách không xuất hiện | Chưa yêu cầu `WITHDIST` | `includeDistance()` |
| Có ít hơn `COUNT n` | Vùng có ít member, hoặc lọc thêm | COUNT chỉ là giới hạn tối đa |
| Kết quả khác mong đợi với `ANY` | Dừng sớm | Bỏ `ANY` khi cần top-N gần nhất |
| GEOSEARCHSTORE báo `CROSSSLOT` | Source và destination ở slot khác | Đặt hash tag/kiểm tra slot |
| `WRONGTYPE` | Key không phải GEO-compatible ZSET | `TYPE key` |
| Kết quả cũ | Member chưa được update/remove | Quy trình đồng bộ vị trí |
| Giá trị Java `null` trong pipeline | Chưa thu response | Đọc kết quả sau pipeline/transaction |

Chạy các lệnh trong môi trường thử nghiệm:

~~~bash
redis-cli -h localhost -p 6379 INFO server
redis-cli -h localhost -p 6379 TYPE demo:shops
redis-cli -h localhost -p 6379 ZCARD demo:shops
redis-cli -h localhost -p 6379 GEOPOS demo:shops store:1
redis-cli -h localhost -p 6379 GEOSEARCH demo:shops FROMLONLAT 106.7000 10.7760 BYRADIUS 2 km ASC WITHDIST
~~~

Nếu câu lệnh cuối báo `unknown command` thì không thể khắc phục bằng cách tăng radius: trước hết cần chọn server/command tương thích.

Với Redis Cluster, dùng client có khả năng theo topology để gửi lệnh tới node sở hữu key. Với lệnh lưu kết quả, phải chú ý source/destination cùng slot.

## 15. Kịch bản triển khai chức năng “địa điểm gần tôi”

Yêu cầu:

> Nhận tọa độ từ người dùng, trả tối đa 10 cửa hàng trong bán kính 3 km, sắp gần nhất trước. Vị trí cửa hàng có thể thay đổi.

Một quy trình thực tế:

**Bước 1 — Chọn key/index.** Đặt key `shops:active:geo` hoặc một key theo partition đã được cân nhắc. Member là ID ổn định của cửa hàng.

**Bước 2 — Đồng bộ dữ liệu.** Sử dụng `GEOADD` khi tạo hoặc sửa vị trí, `GeoOperations.remove()` khi cửa hàng ngừng được tìm kiếm. Không để member mồ côi tồn tại vô hạn nếu business yêu cầu chỉ điểm đang active.

**Bước 3 — Khóa cấu hình capability.** Với Redis 6.2+, gọi `GeoOperations.search()`; nếu bắt buộc giữ server cũ, dùng đường `radius()` cho hình tròn với giới hạn tính năng được công bố. Không retry `GEOSEARCH` không được hỗ trợ trên từng request.

**Bước 4 — Validate input.** Giới hạn kinh/vĩ độ hợp lệ, bán kính 3 km, tối đa 10 kết quả, ID/key do server định nghĩa thay vì nhận tùy ý từ client.

**Bước 5 — Truy vấn.** Dùng `GeoReference.fromCoordinate(lon, lat)`, `new Distance(3, Metrics.KILOMETERS)` và `GeoSearchCommandArgs.sortAscending().limit(10)`. Thêm `includeDistance()` khi UI muốn hiển thị khoảng cách.

**Bước 6 — Bổ sung dữ liệu.** Lấy profile và trạng thái cho các ID trả về. Nếu “đang mở” là điều kiện bắt buộc, thiết kế lại giới hạn ứng viên để tránh bỏ sót top-10 sau lọc.

**Bước 7 — Trả DTO ổn định.** Ví dụ `id`, `name`, `distanceKm`, `location`; tránh trả các cấu trúc driver trực tiếp cho frontend.

**Bước 8 — Theo dõi vận hành.** Quan sát latency p95/p99 theo radius, số member, tỉ lệ cache miss, số lần cập nhật vị trí, lỗi command và yêu cầu vượt giới hạn.

~~~mermaid
flowchart TD
    A["Request longitude/latitude"] --> B["Validate bán kính và limit"]
    B --> C{"Redis hỗ trợ GEOSEARCH >= 6.2?"}
    C -->|Có| D["GeoOperations.search()"]
    C -->|Không nhưng có lệnh legacy| E["GeoOperations.radius()"]
    C -->|Không có cách phù hợp| F["Báo unsupported capability"]
    D --> G["ID, distance, location"]
    E --> G
    G --> H["Lấy profile, lọc nghiệp vụ"]
    H --> I["Trả DTO ứng dụng"]
~~~

## 16. Các hiểu lầm cần tránh

**“Cứ có `GeoOperations.search()` là Redis 5 chạy được.”** Không. `GEOSEARCH` yêu cầu Redis Server từ 6.2.

**“`GEORADIUS` deprecated nghĩa là không bao giờ dùng được.”** Không; nó vẫn có thể tồn tại để phục vụ compatibility, nhưng Redis 6.2+ khuyến nghị `GEOSEARCH`.

**“Redis GEO là một kiểu Redis riêng.”** Không. Data được lưu dưới dạng ZSET có geospatial scores.

**“`Point(x, y)` là latitude, longitude.”** Trong trường hợp này `x` là longitude và `y` là latitude.

**“`ASC COUNT 10 ANY` luôn cho 10 điểm gần nhất.”** `ANY` cho phép dừng sớm, nên không bảo đảm top-N toàn vùng giống truy vấn không bật ANY.

**“`BYBOX 4 3 km` là một vòng tròn.”** Đó là một hình chữ nhật chiều rộng 4 km, chiều cao 3 km.

**“Khoảng cách GEO là số km đường bộ.”** Không; đó là khoảng cách địa lý gần đúng.

**“`GEOSEARCHSTORE` không liên quan quy tắc nhiều key của Cluster.”** Nó có source và destination, cần thiết kế slot đúng.

**“Lấy 10 điểm bằng GEO rồi lọc sẽ luôn ra 10 điểm gần nhất đáp ứng điều kiện.”** Không nhất thiết; giới hạn ứng viên trước khi lọc có thể gây bỏ sót.

**“GEO index tự hết hạn từng member.”** TTL thông thường áp vào toàn bộ Redis key, còn member cần vòng đời cập nhật/xóa riêng.

## 17. Ghi nhớ

- **Redis 3.2+**: `GEOADD`, `GEODIST`, `GEOPOS` và truy vấn bán kính legacy.
- **Redis 6.2+**: `GEOSEARCH` tìm theo **BYRADIUS** hoặc **BYBOX**, tâm từ tọa độ hoặc member; `GEOSEARCHSTORE` lưu kết quả.
- **Spring Data Redis 3.3**: `GeoOperations.search()`, `GeoReference`, `Distance`, `BoundingBox` và `GeoSearchCommandArgs`.
- **Khả năng API và Redis Server khác nhau**: phải kiểm tra command đang có ở endpoint thật.
- **Longitude trước latitude**, đơn vị bán kính phải rõ ràng và đầu vào phải được validate.
- **`ASC COUNT n`** là lựa chọn rõ hơn cho top-N gần nhất; `ANY` đánh đổi tính đầy đủ để tăng tốc.
- **GEO là chỉ mục ứng viên theo vị trí**, không phải engine định tuyến, đa giác tùy ý hoặc truy vấn thuộc tính SQL.
- **Redis Cluster**: query một GEO key tương đối trực tiếp; lưu kết quả qua `GEOSEARCHSTORE` cần xét source/destination cùng slot.
- **Vận hành cần giới hạn và vòng đời**: radius, limit, phân vùng, update, remove và dữ liệu vị trí nhạy cảm.

Tìm điểm lân cận hiệu quả không chỉ là biết gọi `geo.search()`. Cần xác định **server có lệnh phù hợp**, dữ liệu vị trí được lưu và cập nhật ra sao, khoảng cách được hiểu thế nào, và kết quả truy vấn có đáp ứng đúng điều kiện nghiệp vụ hay không.

## Tài liệu tham khảo

- [Spring Data Redis 3.3.7 API — GeoOperations](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/core/GeoOperations.html)
- [Spring Data Redis 3.3.7 API — GeoSearchCommandArgs](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/connection/RedisGeoCommands.GeoSearchCommandArgs.html)
- [Spring Data Redis 3.3.7 API — GeoReference](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/domain/geo/GeoReference.html)
- [Spring Data Redis — GEO](https://docs.spring.io/spring-data/redis/reference/redis/geo.html)
- [Redis — GEOADD](https://redis.io/docs/latest/commands/geoadd/)
- [Redis — GEOSEARCH](https://redis.io/docs/latest/commands/geosearch/)
- [Redis — GEOSEARCHSTORE](https://redis.io/docs/latest/commands/geosearchstore/)
- [Redis — GEORADIUS](https://redis.io/docs/latest/commands/georadius/)
- [Redis — GEOPOS](https://redis.io/docs/latest/commands/geopos/)
- [Redis — GEODIST](https://redis.io/docs/latest/commands/geodist/)
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
