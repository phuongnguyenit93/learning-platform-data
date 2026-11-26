# GeoResult, GeoResults và kiểu kết quả do store hỗ trợ

## Mục tiêu và phạm vi

Truy vấn “tìm địa điểm gần đây” có thể trả về nhiều hơn một danh sách địa điểm. Mỗi kết quả có thể mang khoảng cách tới tâm truy vấn; cả tập kết quả có thể có thông tin khoảng cách trung bình hoặc phân trang.

Trong module **SPRING_DATA_COMMONS**, các kiểu `GeoResult`, `GeoResults` và `GeoPage` cung cấp cấu trúc dùng chung để biểu diễn những thông tin đó. Chúng không tự thêm chức năng tìm kiếm không gian cho mọi repository.

Bài học thuộc chương **Kiểu dữ liệu dùng chung**. Mục tiêu là:

1. Đọc đúng phần tử, khoảng cách và metadata của kết quả geo.
2. Phân biệt đơn vị khoảng cách với giá trị số.
3. Hiểu giới hạn của average, limit, thứ tự và phân trang.
4. Chọn kiểu trả về theo module store và mô hình thực thi.
5. Chuyển kết quả geo thành DTO mà không làm sai ngữ nghĩa.

Các ví dụ Commons dùng Java 17 trở lên và không cần database để minh họa value object. Các ví dụ MongoDB hoặc Redis được ghi rõ phạm vi; để chạy chúng cần module, driver, dữ liệu, mapping và chỉ mục phù hợp.

## 1. Commons biểu diễn kết quả; store thực thi truy vấn

Luồng truy vấn có thể nhìn như sau:

~~~mermaid
flowchart LR
    A["Tâm và phạm vi tìm kiếm"] --> B["Repository hoặc template theo store"]
    B --> C["Toán tử geo và chỉ mục"]
    C --> D["Nội dung cùng khoảng cách"]
    D --> E["GeoResult hoặc wrapper được hỗ trợ"]
    E --> F["Service và DTO đầu ra"]
~~~

Một interface xuất hiện trên classpath chỉ chứng minh ứng dụng có thể dùng kiểu Java đó. Nó không chứng minh:

- Store hiểu query keyword `Near` hoặc `Within`.
- Driver có API tương ứng.
- Dữ liệu vị trí đã được mapping đúng.
- Chỉ mục không gian đã tồn tại.
- Repository hỗ trợ cùng kiểu trả về ở cả imperative và reactive.

Tài liệu [Repository query return types](https://docs.spring.io/spring-data/commons/reference/repositories/query-return-types-reference.html) nêu rõ kiểu geo chỉ có ở các store hỗ trợ truy vấn không gian; một số module có wrapper riêng.

Cần phân biệt hai tình huống:

1. Ứng dụng tự tạo một `GeoResults<T>` từ dữ liệu đã biết.
2. Hạ tầng repository tự tạo `GeoResults<T>` khi thực thi một query.

Tình huống thứ nhất chỉ cần các class Commons. Tình huống thứ hai cần khả năng thực sự của module store và loại query đó.

## 2. GeoResult là một phần tử cùng khoảng cách

`GeoResult<T>` chứa:

| Thành phần | Ý nghĩa |
|---|---|
| `T content` | Đối tượng kết quả |
| `Distance distance` | Khoảng cách gắn với kết quả trong ngữ cảnh truy vấn |

Ví dụ:

~~~java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Metrics;

public class OneGeoResultExample {

    public record PlaceView(
        String id,
        String name
    ) {
    }

    public static void main(String[] args) {
        PlaceView place = new PlaceView(
            "p-101",
            "Central Coffee"
        );

        GeoResult<PlaceView> hit = new GeoResult<>(
            place,
            new Distance(0.8, Metrics.KILOMETERS)
        );

        String name = hit.getContent().name();
        double value = hit.getDistance().getValue();
        String unit = hit.getDistance().getUnit();

        System.out.println(name);
        System.out.println(value + " " + unit);
    }
}
~~~

Khoảng cách trong ví dụ được gán để minh họa cách dùng value object. Chương trình này không tính khoảng cách từ tọa độ và không chứng minh địa điểm có thật ở cách tâm 0,8 km.

`T` không bắt buộc là entity. Nó có thể là projection, DTO nội bộ hoặc một loại phần tử mà API của store trả về.

Định nghĩa chính thức nằm trong [GeoResult](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/GeoResult.html). Constructor yêu cầu content và distance khác null.

### Khoảng cách gắn với một ngữ cảnh

Một địa điểm không có “khoảng cách cố hữu” bằng 0,8 km. Nó cách **một điểm tham chiếu**, theo **một cách đo**, trong **một truy vấn**.

Nếu cùng địa điểm được tìm từ một tâm khác, khoảng cách thay đổi. Vì vậy, không lưu hoặc cache một `GeoResult` như thể distance là thuộc tính bất biến của địa điểm.

Distance cũng không tự bao gồm:

- Tọa độ tâm.
- Bán kính tìm kiếm ban đầu.
- Thời điểm dữ liệu được đọc.
- Khoảng cách di chuyển theo đường bộ.
- Thời gian đi lại.

Nếu nghiệp vụ cần những thông tin đó, chúng phải nằm trong hợp đồng truy vấn hoặc response bổ sung.

## 3. Distance luôn cần được đọc cùng Metric

`Distance` biểu diễn một giá trị gắn với `Metric`:

~~~java
Distance kilometers = new Distance(1.0, Metrics.KILOMETERS);
Distance miles = new Distance(1.0, Metrics.MILES);
~~~

Hai giá trị cùng có `getValue() == 1.0` nhưng không biểu diễn cùng khoảng cách.

Một phép chuyển đổi rõ ràng là:

~~~java
Distance oneMile = new Distance(1.0, Metrics.MILES);
Distance inKilometers = oneMile.in(Metrics.KILOMETERS);

double kilometers = inKilometers.getValue();
~~~

Không đổi đơn vị bằng cách tạo lại một Distance từ cùng số:

~~~java
// Gán lại ý nghĩa cho số 1.0, không phải chuyển 1 mile sang km.
Distance relabeled = new Distance(
    oneMile.getValue(),
    Metrics.KILOMETERS
);
~~~

Xem [Distance](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/Distance.html) và [Metrics](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/Metrics.html).

### NEUTRAL không có nghĩa mặc định là mét

Constructor một tham số:

~~~java
Distance distance = new Distance(5);
~~~

dùng metric trung tính. Không được tự hiểu đây là 5 mét hoặc 5 km.

Giá trị normalized và ý nghĩa mà store sử dụng phải được xác định theo API đang gọi. Với các truy vấn dùng mô hình cầu, dữ liệu normalized có thể mang ý nghĩa khác một số đo độ dài thông thường.

Cũng không lấy `getNormalizedValue()` rồi đưa ra client với tên `distanceKm`. Giá trị đó là biểu diễn theo base scale của metric, không tự là đơn vị hiển thị.

### Metric tùy biến cần cùng cơ sở đo

`Metric` mô tả multiplier so với một base scale. Vì vậy, chuyển đổi chỉ có ý nghĩa khi các metric tham gia có cơ sở tương thích.

Không chỉ nhìn abbreviation giống nhau rồi giả định một metric của API store có thể chuyển đổi đúng với mọi metric Commons. Adapter phải hiểu đơn vị và base scale mà nó nhận được.

Trong helper ở phần sau, ví dụ chỉ chấp nhận `Metrics.KILOMETERS` và `Metrics.MILES` rồi chuẩn hóa về km. Metric trung tính hoặc metric khác phải được adapter xử lý có chủ đích.

Hợp đồng của base scale được mô tả trong [Metric](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/Metric.html).

## 4. GeoResults là danh sách các GeoResult và average

`GeoResults<T>` triển khai `Iterable<GeoResult<T>>`. Có thể duyệt trực tiếp hoặc lấy danh sách bằng `getContent()`.

Ví dụ không cần store:

~~~java
import java.util.List;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;

public class GeoResultsExample {

    public record PlaceView(
        String id,
        String name
    ) {
    }

    public static GeoResults<PlaceView> sample() {
        List<GeoResult<PlaceView>> hits = List.of(
            new GeoResult<>(
                new PlaceView("p-101", "Central Coffee"),
                new Distance(0.8, Metrics.KILOMETERS)
            ),
            new GeoResult<>(
                new PlaceView("p-102", "Garden Coffee"),
                new Distance(2.2, Metrics.KILOMETERS)
            )
        );

        return new GeoResults<>(
            hits,
            Metrics.KILOMETERS
        );
    }

    public static void main(String[] args) {
        GeoResults<PlaceView> results = sample();

        for (GeoResult<PlaceView> hit : results) {
            System.out.println(
                hit.getContent().name()
                    + ": "
                    + hit.getDistance().getValue()
                    + " "
                    + hit.getDistance().getUnit()
            );
        }

        int returnedCount = results.getContent().size();

        Distance average = results.getAverageDistance();

        System.out.println("Returned: " + returnedCount);
        System.out.println(
            "Average: " + average.getValue()
                + " " + average.getUnit()
        );
    }
}
~~~

Trong fixture này, hai khoảng cách cùng đơn vị km nên trung bình là 1,5 km.

Dữ liệu minh họa được dựng sẵn. `GeoResults` không tìm vị trí, không suy ra khoảng cách từ content và không gọi database.

API các constructor và accessor được mô tả trong [GeoResults](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/GeoResults.html).

### GeoResults không phải Page

`results.getContent().size()` là số phần tử trong danh sách đang có. Nó không tự là tổng số địa điểm thỏa query trên toàn store.

Bản thân `GeoResults` không cung cấp số trang, kích thước trang hay tổng số trang. Một kết quả đã bị limit vẫn có thể được đóng gói thành GeoResults.

Cũng không gọi `results.stream()` hoặc `results.map(...)` như thể nó là Streamable. Khi muốn dùng Stream API, bắt đầu từ:

~~~java
results.getContent().stream()
~~~

## 5. Average không tự giải quyết mọi vấn đề đơn vị và phạm vi

Có ba cách tạo GeoResults đáng phân biệt:

~~~java
new GeoResults<>(hits);

new GeoResults<>(hits, Metrics.KILOMETERS);

new GeoResults<>(
    hits,
    new Distance(1.5, Metrics.KILOMETERS)
);
~~~

Hai cách đầu yêu cầu tính average từ danh sách. Cách cuối nhận average do caller cung cấp.

Không vì một object có `getAverageDistance()` mà kết luận average đó đã được kiểm chứng với toàn bộ tập dữ liệu của store.

### Chuẩn hóa phần tử trước khi tính trung bình

Khi tự dựng kết quả, không đưa trực tiếp các giá trị khác đơn vị vào cùng phép trung bình.

Ví dụ:

~~~text
Phần tử A: 1 km
Phần tử B: 1 mile

Trung bình các số thô: (1 + 1) / 2 = 1
Trung bình sau đổi về km: khoảng 1,304672 km
~~~

Trong implementation được đối chiếu ở mã nguồn Spring Data Commons, phần tính average lấy trung bình của `Distance.getValue()`, rồi tạo Distance với metric đầu ra. Không có bước đổi từng phần tử sang metric đó trước phép trung bình.

Vì vậy, chỉ truyền `Metrics.KILOMETERS` vào constructor không thay thế việc chuẩn hóa các distance đầu vào. Constructor chỉ nhận danh sách còn dùng metric trung tính cho average trong implementation được đối chiếu.

Chi tiết có thể xem trong [mã nguồn GeoResults](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/geo/GeoResults.java). Khi làm việc với một phiên bản cụ thể, cần đối chiếu hợp đồng/implementation tương ứng; ví dụ của bài chủ động chuẩn hóa để không dựa vào giả định chuyển đổi ngầm.

### Trung bình của danh sách nào?

Nếu query trả 20 kết quả gần nhất, average của 20 phần tử đó không phải average của mọi địa điểm trong bán kính.

Nếu chỉ lấy một trang, average của trang không tự là average của toàn bộ các trang.

Nếu sau đó lọc bớt phần tử vì nghiệp vụ, average cũ có thể không còn khớp tập được trả ra. Phải xác định metadata được tính trên tập nào và tính lại khi cần.

### Tập rỗng và giá trị zero

Ở constructor tính average được đối chiếu, danh sách rỗng tạo average bằng 0 theo metric được truyền. Đó là một quy ước biểu diễn của implementation.

Ở hợp đồng nghiệp vụ, “không có địa điểm” khác “địa điểm có khoảng cách bằng 0”. DTO ví dụ ở phần sau sẽ trả `averageDistanceKm: null` khi tập rỗng và giữ `returnedCount: 0`.

### Snapshot danh sách

Khi tự tạo wrapper, nên cấp một danh sách snapshot và tránh thay đổi dữ liệu nguồn sau đó. Một view không cho sửa không đồng nghĩa toàn bộ object graph đã được deep copy.

Average cũng có thể đã được lưu tại thời điểm tạo wrapper. Thay đổi nội dung danh sách hoặc đối tượng nguồn sau đó có thể làm các thông tin không còn nhất quán theo thiết kế của ứng dụng.


## 6. GeoPage bổ sung phân trang nhưng không tự đếm dữ liệu

`GeoPage<T>` kế thừa `PageImpl<GeoResult<T>>`. Vì vậy, phần tử của trang là `GeoResult<T>`, không chỉ là `T`.

Ví dụ chữ ký và kiểu:

~~~java
GeoPage<PlaceView> geoPage = /* kết quả từ API có hỗ trợ */;
Page<GeoResult<PlaceView>> page = geoPage;
~~~

Đây là minh họa quan hệ kiểu, không phải câu lệnh khởi tạo hoàn chỉnh.

Khi tự dựng trang từ một danh sách đã biết và một tổng đã được xác định:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.geo.GeoPage;
import org.springframework.data.geo.GeoResults;

GeoResults<PlaceView> currentResults = /* danh sách trang hiện tại */;

GeoPage<PlaceView> page = new GeoPage<>(
    currentResults,
    PageRequest.of(0, 2),
    12
);
~~~

Đoạn này giả định caller thực sự có tổng phù hợp bằng 12. Constructor không tự chạy count để xác minh con số đó và cũng không tự cắt một danh sách lớn xuống đúng hai phần tử.

`getAverageDistance()` lấy metadata từ GeoResults dùng để dựng trang. Đừng tự hiểu đó là average của toàn bộ 12 địa điểm nếu nguồn chỉ chứa phần tử của trang hiện tại.

Xem [GeoPage](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/GeoPage.html) và [mã nguồn GeoPage](https://raw.githubusercontent.com/spring-projects/spring-data-commons/main/src/main/java/org/springframework/data/geo/GeoPage.java).

### Không tạo tổng giả từ kích thước danh sách

Nếu truy vấn chỉ trả 20 kết quả gần nhất, `total = 20` không chứng minh chỉ có 20 địa điểm phù hợp trong store.

Nếu không biết tổng, chọn hợp đồng đầu ra không hứa tổng thay vì bọc dữ liệu vào Page với một con số đoán.

Khi map trang sang DTO, phần tử mapper nhận được vẫn là GeoResult:

~~~java
Page<PlaceView> placesOnly = geoPage.map(
    GeoResult::getContent
);
~~~

Phép map trên bỏ distance khỏi kiểu phần tử đầu ra. Nó có thể phù hợp nếu API không cần khoảng cách, nhưng phải là một quyết định có chủ đích.

Thông tin average đặc thù không nằm trong hợp đồng chung của `Page`. Nếu response cần nó, hãy đưa metadata đó vào representation đã thiết kế thay vì mặc định mọi phép map giữ nguyên mọi metadata chuyên biệt.

## 7. MongoDB: kiểu trả về gắn với query và mô hình thực thi

Với Spring Data MongoDB imperative, một repository có thể có phương thức:

~~~java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface PlaceRepository
    extends MongoRepository<Place, String> {

    GeoResults<Place> findByLocationNear(
        Point center,
        Distance radius
    );
}
~~~

Trong chữ ký này, `Place` là aggregate đã được mapping cho MongoDB và có property `location` phù hợp. Đoạn repository chưa định nghĩa model hoặc cấu hình database.

Một lời gọi có thể dùng:

~~~java
Point center = new Point(106.70, 10.78);
Distance radius = new Distance(5, Metrics.KILOMETERS);

GeoResults<Place> results =
    repository.findByLocationNear(center, radius);
~~~

Với hệ tọa độ địa lý mà ví dụ giả định, `x` là longitude và `y` là latitude. `Point` của Commons bản thân chỉ biểu diễn x/y; quy ước địa lý thuộc cách dùng với store.

Spring Data MongoDB tài liệu hóa các geo query trả entity hoặc GeoResults, và cách metric ảnh hưởng truy vấn. Không cần sao chép trực tiếp toán tử cấp thấp của một ví dụ khác vào repository Commons. Xem [MongoDB-specific Query Methods — Geo-spatial Queries](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html#mongodb.repositories.queries.geo-spatial).

### Dữ liệu vị trí và chỉ mục phải phù hợp

Cần xác định:

- Dữ liệu là GeoJSON hay dạng tọa độ được API đó hỗ trợ.
- Thứ tự tọa độ và hệ tọa độ.
- Loại geo index cần cho query.
- Khoảng cách đầu vào và đầu ra được biểu diễn theo đơn vị nào.
- Những ràng buộc hoặc giới hạn của phiên bản server/module.

Annotation như `@GeoSpatialIndexed` cung cấp metadata chỉ mục. Sự tồn tại của annotation không chứng minh database đang có chỉ mục tương ứng.

Spring Data MongoDB yêu cầu chính sách tạo chỉ mục được bật hoặc thực hiện tường minh theo cấu hình ứng dụng. Xem [MongoDB Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html).

### Không ghép hai phương thức chỉ khác return type

Một query có thể có các lựa chọn kiểu kết quả khác nhau theo tài liệu store. Tuy nhiên, Java không cho khai báo hai phương thức cùng tên và cùng tham số mà chỉ khác return type.

Nếu so sánh phương án `List<Place>` với `GeoResults<Place>`, hãy coi chúng là những lựa chọn thiết kế hoặc dùng các phương thức hợp lệ khác nhau. Không đặt nguyên hai chữ ký trùng nhau vào cùng interface.

## 8. Reactive MongoDB không dùng cùng mọi wrapper imperative

Reactive repository có thể trả:

~~~java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Point;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

import reactor.core.publisher.Flux;

public interface ReactivePlaceRepository
    extends ReactiveMongoRepository<Place, String> {

    Flux<GeoResult<Place>> findByLocationNear(
        Point center,
        Distance radius
    );
}
~~~

Tài liệu Spring Data MongoDB nêu rằng truy vấn geo reactive hỗ trợ domain type và `GeoResult<T>` bên trong reactive wrapper. `GeoResults` và `GeoPage` không được hỗ trợ như các wrapper tương ứng ở repository geo reactive vì chúng gắn với việc tính trước average.

Có thể truyền `Pageable` cho những query được hỗ trợ để điều khiển phần kết quả, nhưng điều đó không tự tạo tổng hoặc biến Flux thành GeoPage. Giới hạn này được mô tả trong [MongoDB geo repository queries](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html).

### Tính average trong reactive là một quyết định xử lý

Nếu ứng dụng cần average trên một nguồn hữu hạn, nó phải tổng hợp các khoảng cách trong phạm vi đã chọn. Việc đó có thể cần chờ nguồn hoàn tất.

Nếu dùng `collectList()` để tự tạo GeoResults, ứng dụng đã chủ động materialize danh sách. Cách làm đó không biến chữ ký `Mono<GeoResults<T>>` thành một return type tự động được mọi repository hỗ trợ.

Không gọi `block()` chỉ để chuyển đường đi reactive sang dạng imperative cho tiện bọc wrapper. Hãy chọn hợp đồng đầu ra và cách xử lý phù hợp vòng đời thực thi.

Với một nguồn lớn hoặc không hoàn tất, khái niệm “average cuối cùng của toàn bộ nguồn” cần được thiết kế lại theo phạm vi, cửa sổ hoặc giới hạn cụ thể.

## 9. Redis: cùng GeoResults nhưng content có thể là GeoLocation

Spring Data Redis có API geo ở tầng template/operations. Kết quả có thể mang dạng:

~~~java
GeoResults<RedisGeoCommands.GeoLocation<String>>
~~~

Trong đó, content của mỗi GeoResult là một GeoLocation chứa tên member và thông tin vị trí theo dữ liệu được yêu cầu, không phải tự động là entity `Place` của ứng dụng.

Ví dụ API search:

~~~java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Point;
import org.springframework.data.redis.connection.RedisGeoCommands;
import org.springframework.data.redis.core.GeoOperations;
import org.springframework.data.redis.domain.geo.GeoReference;

public final class RedisNearbyExample {

    private RedisNearbyExample() {
    }

    public static GeoResults<
        RedisGeoCommands.GeoLocation<String>
    > find(
        GeoOperations<String, String> operations,
        Point center,
        Distance radius
    ) {
        RedisGeoCommands.GeoSearchCommandArgs options =
            RedisGeoCommands.GeoSearchCommandArgs
                .newGeoSearchArgs()
                .includeDistance()
                .includeCoordinates()
                .sortAscending()
                .limit(20);

        return operations.search(
            "places:geo",
            GeoReference.<String>fromCoordinate(center),
            radius,
            options
        );
    }
}
~~~

Đoạn mã giả định Redis server và driver hỗ trợ lệnh đang dùng, và key đã chứa dữ liệu geo phù hợp. Ví dụ minh họa API operations, không phải lời khẳng định mọi Redis repository derived query có cùng kiểu trả về.

Vai trò từng tùy chọn:

| Tùy chọn | Mục đích |
|---|---|
| `includeDistance()` | Yêu cầu trả khoảng cách từ tâm |
| `includeCoordinates()` | Yêu cầu trả tọa độ |
| `sortAscending()` | Yêu cầu thứ tự gần đến xa |
| `limit(20)` | Giới hạn số phần tử được trả |

Nếu query không yêu cầu khoảng cách, không diễn giải giá trị thiếu hoặc giá trị thay thế của adapter thành một khoảng cách đã được đo bằng 0.

Các API được mô tả trong [GeoOperations](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/GeoOperations.html), [GeoSearchCommandArgs](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/RedisGeoCommands.GeoSearchCommandArgs.html) và [GeoReference](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/domain/geo/GeoReference.html).

### GeoLocation không tự là domain object

Có thể lấy member bằng `hit.getContent().getName()`. Nếu member là ID, ứng dụng cần đọc dữ liệu chi tiết theo nhu cầu.

Không cast:

~~~java
GeoResults<GeoLocation<String>>
~~~

thành:

~~~java
GeoResults<Place>
~~~

Chúng có cấu trúc content khác nhau. Adapter cần ánh xạ tường minh, đồng thời giữ khoảng cách đi cùng đúng member.

Nếu bổ sung dữ liệu chi tiết theo lô và loại một số member không còn tồn tại, average của tập cuối cùng cần được xem xét lại. Đừng giữ metadata cũ cho một danh sách đã thay đổi mà không có quy ước rõ.

Cấu trúc member/point được mô tả trong [GeoLocation](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/RedisGeoCommands.GeoLocation.html).

## 10. Thứ tự gần nhất là hợp đồng của query

Một danh sách `GeoResults` có thể được tạo từ danh sách theo bất kỳ thứ tự nào. Wrapper không tự sắp xếp lại theo distance khi khởi tạo.

Do đó:

~~~java
GeoResult<PlaceView> first = results.getContent().get(0);
~~~

chỉ lấy phần tử đầu. Nó chưa chứng minh đó là địa điểm gần nhất.

Muốn dùng cách đọc này, phải:

1. Kiểm tra danh sách không rỗng.
2. Có hợp đồng query hoặc một bước xử lý đã bảo đảm thứ tự gần đến xa.
3. Giữ đúng distance gắn với từng phần tử trong các bước ánh xạ.

Nếu tự sort, phải so sánh theo các distance có ngữ nghĩa/đơn vị tương thích. Không so `getValue()` của một giá trị km với một giá trị mile như các số cùng đơn vị.

### Limit và sort phải đi cùng ý nghĩa nghiệp vụ

Lấy một tập bất kỳ rồi sort trong bộ nhớ không luôn tương đương lấy N kết quả gần nhất tại store.

Khi query có option ưu tiên tìm nhanh một số kết quả mà không bảo đảm tập gần nhất toàn cục, không tự quảng bá response là “N địa điểm gần nhất” nếu hợp đồng đó chưa được đáp ứng.

Nếu khoảng cách bằng nhau, thứ tự tiếp theo có thể cần một quy tắc bổ sung. Wrapper không tự cung cấp tie-breaker theo ID.


## 11. Chuẩn hóa kết quả trước khi sử dụng chung

Helper sau chọn một hợp đồng hẹp:

- Chỉ nhận distance đo được bằng `Metrics.KILOMETERS` hoặc `Metrics.MILES`.
- Chuyển từng phần tử về km.
- Từ chối số không hữu hạn hoặc âm.
- Giữ thứ tự và content của từng phần tử.
- Tính lại average trên chính danh sách đã chuẩn hóa.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metric;
import org.springframework.data.geo.Metrics;

public final class GeoResultNormalizer {

    private GeoResultNormalizer() {
    }

    public static <T> GeoResults<T> toKilometers(
        Iterable<GeoResult<T>> source
    ) {
        Objects.requireNonNull(source, "source is required");

        List<GeoResult<T>> normalized = new ArrayList<>();

        for (GeoResult<T> hit : source) {
            Objects.requireNonNull(hit, "geo result is required");

            Distance distance = hit.getDistance();
            Metric metric = distance.getMetric();

            if (metric != Metrics.KILOMETERS
                    && metric != Metrics.MILES) {
                throw new IllegalArgumentException(
                    "The adapter must provide a supported measured distance"
                );
            }

            if (!Double.isFinite(distance.getValue())
                    || distance.getValue() < 0) {
                throw new IllegalArgumentException(
                    "Distance must be finite and non-negative"
                );
            }

            Distance kilometers = distance.in(
                Metrics.KILOMETERS
            );

            if (!Double.isFinite(kilometers.getValue())) {
                throw new IllegalArgumentException(
                    "Converted distance must be finite"
                );
            }

            normalized.add(new GeoResult<>(
                hit.getContent(),
                kilometers
            ));
        }

        return new GeoResults<>(
            List.copyOf(normalized),
            Metrics.KILOMETERS
        );
    }
}
~~~

Đây là chính sách của helper, không phải khẳng định mọi metric khác đều sai. Nếu store trả một đơn vị hoặc biểu diễn normalized khác, adapter phải chuyển nó theo đúng hợp đồng của store trước khi đưa vào luồng dùng helper này.

Không gán lại metric km cho một số chưa biết đơn vị chỉ để vượt qua kiểm tra.

Helper cố ý không lấy average có sẵn của nguồn. Nó định nghĩa average đầu ra là trung bình của các phần tử sau chuẩn hóa đang được trả về. Nếu nghiệp vụ cần average trên một tập rộng hơn, phải dùng một metadata khác với phạm vi được mô tả rõ.

### Giữ distance khi đổi content

Nếu chuyển entity sang DTO, giữ khoảng cách của chính kết quả đó:

~~~java
GeoResult<PlaceView> mapped = new GeoResult<>(
    toPlaceView(hit.getContent()),
    hit.getDistance()
);
~~~

Đây là đoạn minh họa, trong đó `toPlaceView` là mapper nội dung của ứng dụng. Không tính lại distance chỉ vì đổi kiểu của content, trừ khi nghiệp vụ thực sự thay đổi cách đo.

Nếu ánh xạ nhiều nguồn, phải giữ liên hệ member/ID với distance. Ghép hai danh sách bằng vị trí sau khi một danh sách đã đổi thứ tự có thể tạo khoảng cách của địa điểm khác.

## 12. Thiết kế cổng truy vấn theo khả năng thực tế

Có thể giữ service độc lập với MongoDB hoặc Redis bằng một port:

~~~java
import org.springframework.data.geo.GeoResults;

public interface NearbyPlacePort {

    GeoResults<PlaceView> findNear(NearbyQuery query);
}
~~~

~~~java
public record PlaceView(
    String id,
    String name
) {
}
~~~

Một model đầu vào cho tìm kiếm tọa độ địa lý:

~~~java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

public record NearbyQuery(
    double longitude,
    double latitude,
    double maxDistanceKm,
    int limit
) {
    public NearbyQuery {
        if (!Double.isFinite(longitude)
                || longitude < -180
                || longitude > 180) {
            throw new IllegalArgumentException(
                "Invalid longitude"
            );
        }

        if (!Double.isFinite(latitude)
                || latitude < -90
                || latitude > 90) {
            throw new IllegalArgumentException(
                "Invalid latitude"
            );
        }

        if (!Double.isFinite(maxDistanceKm)
                || maxDistanceKm <= 0
                || maxDistanceKm > 50) {
            throw new IllegalArgumentException(
                "Distance must be in (0, 50] kilometers"
            );
        }

        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException(
                "Limit must be between 1 and 100"
            );
        }
    }

    public Point center() {
        return new Point(longitude, latitude);
    }

    public Distance radius() {
        return new Distance(
            maxDistanceKm,
            Metrics.KILOMETERS
        );
    }
}
~~~

Giới hạn 50 km và 100 kết quả là chính sách minh họa. Module store có thể có giới hạn tọa độ hoặc query chặt hơn và adapter phải kiểm tra thêm khi cần.

`Point` không tự trở thành một kiểu có đầy đủ thông tin CRS. Ví dụ chọn rõ quy ước tọa độ địa lý ngay ở tên field và ở port. Xem API [Point](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/Point.html).

### Hợp đồng cần ghi rõ cho adapter

Trong ví dụ, implementation của port phải:

1. Tìm theo tâm và bán kính từ query.
2. Áp dụng giới hạn kết quả theo khả năng store.
3. Trả kết quả gần đến xa nếu đó là yêu cầu của chức năng.
4. Cung cấp khoảng cách thực sự được query trả hoặc được tính theo quy tắc đã xác định.
5. Chuyển nội dung sang `PlaceView` và distance sang các metric helper chấp nhận.
6. Áp dụng các điều kiện phạm vi/nghiệp vụ trong truy vấn khi cần.
7. Báo lỗi phù hợp nếu capability cần thiết không tồn tại, thay vì trả distance giả.

Đây là hợp đồng do ứng dụng thiết kế. Tạo interface không tự thực hiện bất kỳ bước nào trong số đó.

Nếu một store không hỗ trợ cùng thao tác repository nhưng có API template phù hợp, adapter có thể dùng API đó. Nếu cần extension spatial hoặc query riêng, phải triển khai và xác minh ở module tương ứng.

Không lấy việc `GeoResults` nằm trong Commons làm bằng chứng JPA/JDBC repository thông thường tự hiểu toàn bộ geo query.

## 13. DTO đầu ra thể hiện khoảng cách và phạm vi average

DTO có thể tránh công khai toàn bộ cấu trúc nội bộ của Distance hoặc entity:

~~~java
import java.util.List;
import java.util.Objects;

import com.fasterxml.jackson.annotation.JsonInclude;

import org.springframework.data.geo.GeoResults;

public record NearbyResponse(
    List<Hit> content,
    Summary summary
) {
    public NearbyResponse {
        content = List.copyOf(content);
        Objects.requireNonNull(summary, "summary is required");
    }

    public static NearbyResponse from(
        GeoResults<PlaceView> source
    ) {
        GeoResults<PlaceView> normalized =
            GeoResultNormalizer.toKilometers(source);

        List<Hit> content = normalized.getContent()
            .stream()
            .map(hit -> new Hit(
                hit.getContent().id(),
                hit.getContent().name(),
                hit.getDistance().getValue()
            ))
            .toList();

        Double average = content.isEmpty()
            ? null
            : normalized.getAverageDistance().getValue();

        return new NearbyResponse(
            content,
            new Summary(content.size(), average)
        );
    }

    public record Hit(
        String id,
        String name,
        double distanceKm
    ) {
    }

    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record Summary(
        int returnedCount,
        Double averageDistanceKm
    ) {
    }
}
~~~

Tên field chỉ rõ đơn vị km. `returnedCount` là số phần tử trả về; nó không được đặt tên thành `totalElements` vì port chưa hứa cung cấp tổng toàn bộ tập phù hợp.

Annotation trên Summary thể hiện lựa chọn giữ field average khi null với JSON converter Jackson phù hợp. Khi dùng converter khác hoặc cấu hình serialization riêng, cần kiểm tra representation thực tế.

Với fixture hai địa điểm, output mong muốn là:

~~~json
{
  "content": [
    {
      "id": "p-101",
      "name": "Central Coffee",
      "distanceKm": 0.8
    },
    {
      "id": "p-102",
      "name": "Garden Coffee",
      "distanceKm": 2.2
    }
  ],
  "summary": {
    "returnedCount": 2,
    "averageDistanceKm": 1.5
  }
}
~~~

Khi rỗng:

~~~json
{
  "content": [],
  "summary": {
    "returnedCount": 0,
    "averageDistanceKm": null
  }
}
~~~

Service có thể sử dụng cùng representation:

~~~java
import java.util.Objects;

public final class NearbyPlaceService {

    private final NearbyPlacePort places;

    public NearbyPlaceService(NearbyPlacePort places) {
        this.places = Objects.requireNonNull(places);
    }

    public NearbyResponse search(NearbyQuery query) {
        Objects.requireNonNull(query, "query is required");

        return NearbyResponse.from(
            places.findNear(query)
        );
    }
}
~~~

Service này vẫn cần một adapter thực thi port. Nó không tự tạo geospatial index, sửa đơn vị của dữ liệu không rõ nguồn hoặc tính đường đi giao thông.

Không làm tròn khoảng cách quá sớm rồi dùng số đã làm tròn để lọc hoặc tính average. Nếu muốn số chữ số hiển thị cố định, hãy chọn chính sách trình bày và độ chính xác phù hợp.

## 14. Kiểm thử value object và kiểm thử tích hợp là hai lớp khác nhau

Có thể kiểm tra luồng chuẩn hóa mà chưa cần database:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.GeoResults;
import org.springframework.data.geo.Metrics;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GeoResultsContractTest {

    @Test
    void normalizesBeforeAveraging() {
        List<GeoResult<PlaceView>> hits = List.of(
            new GeoResult<>(
                new PlaceView("p-1", "One"),
                new Distance(1, Metrics.KILOMETERS)
            ),
            new GeoResult<>(
                new PlaceView("p-2", "Two"),
                new Distance(1, Metrics.MILES)
            )
        );

        GeoResults<PlaceView> normalized =
            GeoResultNormalizer.toKilometers(hits);

        assertEquals(
            Metrics.KILOMETERS,
            normalized.getContent().get(1)
                .getDistance().getMetric()
        );

        assertEquals(
            1.609344,
            normalized.getContent().get(1)
                .getDistance().getValue(),
            0.00001
        );

        assertEquals(
            1.304672,
            normalized.getAverageDistance().getValue(),
            0.00001
        );
    }

    @Test
    void doesNotInventAClosestFirstOrder() {
        GeoResults<PlaceView> source = new GeoResults<>(
            List.of(
                new GeoResult<>(
                    new PlaceView("far", "Far"),
                    new Distance(2.2, Metrics.KILOMETERS)
                ),
                new GeoResult<>(
                    new PlaceView("near", "Near"),
                    new Distance(0.8, Metrics.KILOMETERS)
                )
            ),
            Metrics.KILOMETERS
        );

        GeoResults<PlaceView> normalized =
            GeoResultNormalizer.toKilometers(source);

        assertEquals(
            "far",
            normalized.getContent().get(0)
                .getContent().id()
        );
    }

    @Test
    void distinguishesEmptyFromZeroDistance() {
        GeoResults<PlaceView> empty = new GeoResults<>(
            List.<GeoResult<PlaceView>>of(),
            Metrics.KILOMETERS
        );

        NearbyResponse response = NearbyResponse.from(empty);

        assertEquals(0, response.content().size());
        assertEquals(0, response.summary().returnedCount());
        assertNull(response.summary().averageDistanceKm());
    }

    @Test
    void requiresTheAdapterToDeclareDistanceMeaning() {
        List<GeoResult<PlaceView>> hits = List.of(
            new GeoResult<>(
                new PlaceView("p-1", "One"),
                new Distance(1)
            )
        );

        assertThrows(
            IllegalArgumentException.class,
            () -> GeoResultNormalizer.toKilometers(hits)
        );
    }
}
~~~

Đây là mẫu kiểm thử cho người học, không phải báo cáo đã chạy trên một database cụ thể. Sai số trong kiểm tra chuyển đổi nhằm tránh so sánh số thực bằng chuỗi hoặc bằng tuyệt đối không phù hợp.

Các test trên không chứng minh:

- Store tìm đúng các địa điểm trong bán kính.
- Tọa độ được lưu đúng thứ tự.
- Chỉ mục geo tồn tại và được sử dụng.
- Query thực sự trả khoảng cách theo đơn vị dự kiến.
- Limit và sort đáp ứng yêu cầu nghiệp vụ.
- Một reactive repository hỗ trợ wrapper đã khai báo.

Những điều đó cần kiểm thử tích hợp của adapter/store.

### Ma trận tích hợp nên có

| Kịch bản | Điều cần quan sát |
|---|---|
| Một điểm đúng tại tâm | Khoảng cách bằng hoặc gần 0 theo độ chính xác store |
| Một điểm ở xa đã biết | Đơn vị và phép chuyển đổi đúng trong sai số chấp nhận |
| Đảo longitude/latitude | Dữ liệu sai được phát hiện bằng fixture rõ ràng |
| Không có điểm phù hợp | Tập rỗng và metadata đúng hợp đồng |
| Có nhiều điểm hơn limit | Count đầu ra không bị hiểu thành tổng |
| Hai khoảng cách bằng nhau | Thứ tự có đáp ứng quy tắc đã chọn không? |
| Query thiếu distance option | Adapter không công khai một distance đo được giả |
| Thiếu geo index cần thiết | Lỗi được nhận diện ở tầng tích hợp |
| Reactive query | Kiểu phần tử và vòng đời thực thi đúng khả năng module |
| Làm giàu dữ liệu theo member ID | Distance vẫn gắn đúng đối tượng sau mapping |
| Loại bớt một phần tử | Average cuối cùng có cùng phạm vi với content |

## 15. Chọn kiểu trả về theo thông tin cần có

| Nhu cầu | Kiểu có thể cân nhắc | Điều phải kiểm tra |
|---|---|---|
| Chỉ cần địa điểm | `List<T>` hoặc wrapper tương ứng | Query có cần giữ distance không? |
| Một phần tử kèm khoảng cách | `GeoResult<T>` trong API được hỗ trợ | Cardinality và ngữ cảnh điểm tham chiếu |
| Một tập kết quả cùng distance | `GeoResults<T>` | Metric và phạm vi average |
| Kết quả geo có thông tin trang | `GeoPage<T>` nếu API hỗ trợ | Nguồn tổng và average của tập nào |
| Geo reactive trên MongoDB | `Flux<GeoResult<T>>` hoặc domain stream được hỗ trợ | Không giả định GeoResults/GeoPage được hỗ trợ tương tự imperative |
| Redis GEO operations | `GeoResults<GeoLocation<M>>` theo API | Member, distance option và mapping sang domain |
| Store có wrapper chuyên biệt | Kiểu do module định nghĩa | Không ép mọi metadata vào một wrapper khác |

Chọn return type sau khi xác định thông tin cần giữ. Nếu chọn `List<T>` từ đầu, khoảng cách có thể không còn trong mô hình đầu ra dù store đã tính nó.

Ngược lại, thêm `GeoResults` vào chữ ký không tạo ra distance đúng nếu query và adapter không cung cấp dữ liệu đó.

## 16. Bài thực hành và chẩn đoán nhanh

Thực hành:

1. Tạo hai GeoResult cùng đơn vị và đọc content/distance.
2. Tạo GeoResults với metric tường minh, kiểm tra average của fixture.
3. Trộn km và mile, sau đó chuẩn hóa từng phần tử trước khi tính average.
4. Xử lý tập rỗng mà không trình bày average 0 như một số đo thực.
5. Chọn một store được hỗ trợ và xác định API thực thi geo query.
6. Kiểm tra mapping tọa độ, chỉ mục, đơn vị, sort và limit.
7. Nếu dùng Redis, ánh xạ member về DTO mà vẫn giữ đúng distance.
8. Nếu dùng reactive, chọn wrapper đúng và tránh materialize toàn bộ chỉ vì muốn tái sử dụng một DTO.
9. Khi cần phân trang, xác định nguồn total trước khi công bố nó.
10. Viết rõ average tính trên trang, danh sách trả về hay một tập khác.

Chẩn đoán:

| Hiện tượng | Điều cần kiểm tra |
|---|---|
| Khoảng cách sai hàng nghìn lần | Đang nhầm mét, km hoặc normalized value? |
| Average không khớp các phần tử | Có trộn metric, đổi danh sách hoặc dùng average nguồn khác phạm vi? |
| Phần tử đầu không gần nhất | Query đã bảo đảm thứ tự chưa? |
| Đổi return type làm repository lỗi | Module và mô hình imperative/reactive có hỗ trợ wrapper đó không? |
| Có GeoLocation nhưng thiếu tên địa điểm | Content là member metadata, chưa phải domain object? |
| Có annotation geo index nhưng query vẫn lỗi | Chỉ mục đã thực sự được tạo trên store chưa? |
| Tập rỗng được hiểu thành mọi điểm ở tâm | Có đang công khai average zero như một số đo thực? |
| Trang có “tổng” bằng đúng limit | Tổng đó có được xác định hay chỉ là kích thước danh sách? |

Điều cần giữ rõ là: **GeoResult giữ nội dung cùng khoảng cách; GeoResults giữ danh sách và metadata; đơn vị cùng phạm vi quyết định ý nghĩa của con số; module store quyết định query và kiểu kết quả nào thực sự được hỗ trợ.**
