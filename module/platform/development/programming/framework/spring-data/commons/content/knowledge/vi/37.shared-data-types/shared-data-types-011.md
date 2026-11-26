# Serialization, chuyển đổi đơn vị và tương thích dữ liệu đầu vào

## 1. Mục tiêu và phạm vi

Trong chương **Kiểu dữ liệu dùng chung** của module **Spring Data Commons**, những kiểu như Range, Distance, Point, Vector hoặc Score giúp biểu diễn dữ liệu có ngữ nghĩa. Khi chúng đi qua HTTP, message queue, file hoặc một store, ứng dụng phải quyết định cách mã hóa và khôi phục ngữ nghĩa đó.

Một giá trị số đứng riêng không đủ cho mọi trường hợp:

~~~text
distance = 1500
timestamp = 1795568400
score = 0.9
~~~

Các câu hỏi còn thiếu là: đơn vị gì, mốc thời gian theo cách biểu diễn nào, điểm thuộc function nào, và bên nhận sẽ diễn giải ra sao?

Sau bài học, bạn cần:

- Tách hợp đồng dữ liệu bên ngoài khỏi implementation Java.
- Giữ giá trị cùng đơn vị hoặc metadata cần thiết.
- Chuẩn hóa đơn vị trước khi so sánh và xây truy vấn.
- Giữ chính xác biên đóng/mở của Range.
- Phân biệt JSON conversion, query-parameter conversion và store conversion.
- Thiết kế tương thích đầu vào có chủ đích.
- Kiểm tra round-trip theo ý nghĩa dữ liệu thay vì chỉ so chuỗi.

Ví dụ Java dùng Java 17 trở lên. Các đoạn Jackson nói rõ nhánh Jackson 2; nếu dự án dùng nhánh API khác, cần dùng cấu hình tương ứng. Việc có kiểu dữ liệu trong Commons không bảo đảm mọi serializer hoặc store tự hỗ trợ kiểu đó theo cùng một cách.

## 2. Bốn bước khác nhau thường bị gọi chung là conversion

~~~text
Dữ liệu bên ngoài
        |
        v
Đọc cấu trúc và kiểu cú pháp
        |
        v
Chuẩn hóa đơn vị, thời gian và quy ước
        |
        v
Kiểm tra miền và hợp đồng
        |
        v
Kiểu dùng trong nghiệp vụ/truy vấn
        |
        v
Adapter của store
~~~

Phân biệt các bước:

| Bước | Ví dụ | Câu hỏi chính |
| --- | --- | --- |
| Deserialize | Đọc JSON value và unit vào DTO | Tài liệu có đúng cấu trúc/kiểu không |
| Normalize | Chuyển 1.5 km thành 1500 m | Giá trị có cùng ý nghĩa sau chuyển đổi không |
| Validate | Bán kính không âm và không vượt giới hạn | Đầu vào có được phép không |
| Store conversion | Ghi kiểu ứng dụng sang biểu diễn database | Mô-đun/driver lưu và đọc thế nào |
| Serialize response | Tạo JSON theo schema công khai | Client có nhận đủ ngữ nghĩa không |

Một bước deserialize thành công không chứng minh đầu vào hợp lệ về nghiệp vụ.

Ngược lại, một object Java hợp lệ chưa chứng minh serializer sẽ tạo đúng schema mà client đang dùng.

## 3. Serializable không phải một hợp đồng JSON

Một số kiểu thư viện triển khai java.io.Serializable. Điều đó không tự quy định:

- Tên field JSON.
- Cách biểu diễn enum hoặc metric.
- Format ngày giờ.
- Đơn vị của giá trị số.
- Khả năng deserialize bằng constructor/factory.
- Tính tương thích của schema với client cũ.

Không suy ra `ObjectMapper` sẽ khôi phục được một kiểu chỉ vì nó serialize được các getter của kiểu đó.

Tương tự, `toString()` chủ yếu phục vụ biểu diễn dạng chuỗi của object; không dùng output đó làm định dạng lưu trữ lâu dài nếu API không công bố một hợp đồng parse ổn định.

Đối với dữ liệu trao đổi bên ngoài, một DTO do ứng dụng sở hữu thường giúp quyết định rõ thông tin nào được công bố và cách thay đổi về sau.

Native Java serialization cũng là một cơ chế khác với JSON. Nó không phải lựa chọn mặc định để nhận object từ HTTP chỉ vì một lớp có marker Serializable.

## 4. Chọn schema công khai giữ đủ ngữ nghĩa

Thay vì chỉ công bố:

~~~json
{
  "radius": 1500
}
~~~

một hợp đồng rõ ràng hơn là:

~~~json
{
  "radius": {
    "value": 1500,
    "unit": "m"
  }
}
~~~

DTO:

~~~java
import java.math.BigDecimal;

public record DistancePayload(BigDecimal value, String unit) {
}
~~~

Tên `m` và `km` trong bài là quy ước công khai của ứng dụng. Không yêu cầu client gửi tên enum Java đầy đủ chỉ vì server dùng một enum bên trong.

Các quyết định schema cần được viết ra:

| Quy tắc | Lựa chọn minh họa |
| --- | --- |
| Unit được nhận | m hoặc km |
| Có cho bỏ unit không | Không |
| Có nhận chữ hoa/khoảng trắng không | Không trong ví dụ strict |
| Giá trị âm | Từ chối |
| Bán kính tối đa | 200.000 m theo policy ví dụ |
| Đơn vị chuẩn hóa | m |
| Đơn vị trả ra | m |

Không đoán unit từ độ lớn của value. Giá trị 2 có thể là 2 m hoặc 2 km; không có quy tắc toán học nào suy ra ý định của client từ con số đó.

## 5. Distance và chuyển đổi metric của Spring Data

Distance thuộc:

~~~java
org.springframework.data.geo.Distance
~~~

Ví dụ dùng metric tường minh:

~~~java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

Distance kilometers =
        new Distance(5.0, Metrics.KILOMETERS);

Distance miles = kilometers.in(Metrics.MILES);

double displayedValue = miles.getValue();
~~~

Phương thức in tạo một Distance theo metric đích, giữ giá trị normalized tương ứng. Xem [API Distance](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/Distance.html).

Ba constant phổ biến của Metrics là KILOMETERS, MILES và NEUTRAL. Xem [API Metrics](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/Metrics.html).

### 5.1. Không thay nhãn mà giữ nguyên giá trị

Nếu thay metric của một giá trị từ kilometer sang mile nhưng giữ nguyên numeric value, bạn thường đã thay đổi khoảng cách.

Cần một phép chuyển đổi đúng, không chỉ đổi trường unit trong JSON.

Tương tự:

~~~json
{
  "value": 1500,
  "unit": "km"
}
~~~

không phải cùng ý nghĩa với value 1500 và unit m.

### 5.2. NEUTRAL không có nghĩa mặc định là meter

Constructor `new Distance(value)` dùng neutral metric, với giá trị đầu vào theo dạng normalized của metric. `getNormalizedValue()` cũng không phải lời hứa “trả số meter”. Điều này được nêu trong [hợp đồng Distance](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/geo/Distance.html).

Vì vậy, không nhận radiusMeters rồi tạo:

~~~java
new Distance(radiusMeters);
~~~

với giả định đã diễn đạt đúng khoảng cách theo meter.

Nếu boundary của ứng dụng chuẩn hóa theo meter, hãy chuyển sang metric được chọn một cách tường minh khi tạo kiểu domain.

### 5.3. Quy tắc thư viện và quy tắc nghiệp vụ cần nhất quán

Khi dùng metric conversion của thư viện, hãy giữ nó trong cùng đường tính toán và kiểm tra sai số phù hợp.

Nếu sản phẩm có quy tắc đo lường hoặc làm tròn riêng, quy tắc đó phải được xác định tại adapter. Không dùng nhiều bảng hệ số khác nhau rải rác trong controller, service và serializer rồi mong round-trip luôn trùng từng bit.

## 6. Ví dụ codec chuẩn hóa m và km

Đoạn code sau dùng BigDecimal ở biên HTTP để giữ phép đổi m/km theo hệ số thập phân rõ ràng. Chỉ khi tạo Distance mới chuyển sang double theo API đó.

~~~java
import java.math.BigDecimal;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

public final class DistancePayloads {

    private static final BigDecimal MAX_METERS =
            new BigDecimal("200000");

    private DistancePayloads() {
    }

    public static BigDecimal toMeters(DistancePayload input) {
        if (input == null
                || input.value() == null
                || input.unit() == null) {

            throw new IllegalArgumentException(
                    "Distance phải có value và unit");
        }

        BigDecimal factor = switch (input.unit()) {
            case "m" -> BigDecimal.ONE;
            case "km" -> new BigDecimal("1000");
            default -> throw new IllegalArgumentException(
                    "Unit chỉ được là m hoặc km");
        };

        BigDecimal meters = input.value().multiply(factor);

        if (meters.signum() < 0
                || meters.compareTo(MAX_METERS) > 0) {

            throw new IllegalArgumentException(
                    "Khoảng cách phải nằm trong 0..200000 m");
        }

        return meters;
    }

    public static Distance toDistance(DistancePayload input) {
        BigDecimal meters = toMeters(input);
        double kilometers = meters.movePointLeft(3).doubleValue();

        return new Distance(
                kilometers,
                Metrics.KILOMETERS);
    }

    public static DistancePayload canonical(
            DistancePayload input) {

        return new DistancePayload(toMeters(input), "m");
    }
}
~~~

Bán kính tối đa trong code là policy minh họa, không phải trần chung do Spring Data áp đặt.

Ví dụ đầu vào tương đương:

~~~java
DistancePayload a =
        new DistancePayload(
                new BigDecimal("1.5"), "km");

DistancePayload b =
        new DistancePayload(
                new BigDecimal("1500"), "m");

boolean equivalent =
        DistancePayloads.toMeters(a)
                .compareTo(DistancePayloads.toMeters(b)) == 0;
~~~

compareTo kiểm tra giá trị số của BigDecimal. Không dùng equals nếu mục tiêu chỉ là tương đương số, vì scale có thể khác nhau.

### 6.1. Nơi làm tròn phải được xác định

Nếu hợp đồng chỉ cho độ chính xác đến centimeter, ứng dụng cần chọn:

- Từ chối đầu vào có độ chính xác cao hơn.
- Hoặc làm tròn theo một rounding mode đã công bố.

Ví dụ trên chưa áp đặt giới hạn scale đó; nó chỉ đổi đơn vị và kiểm tra miền.

Không làm tròn sớm nhiều lần khi đi từ m sang km rồi sang unit hiển thị. Hãy giữ một biểu diễn chuẩn hóa đủ chính xác và làm tròn ở điểm cần thiết theo hợp đồng.

## 7. Serialization Range phải giữ cả giá trị và loại bound

Hai khoảng:

~~~text
[100, 500]
[100, 500)
~~~

có cùng giá trị đầu mút nhưng khác ý nghĩa tại 500.

Chỉ serialize:

~~~json
{
  "min": 100,
  "max": 500
}
~~~

chưa diễn đạt được sự khác nhau đó, trừ khi hợp đồng đã cố định loại bound cho endpoint.

Một schema linh hoạt hơn:

~~~json
{
  "unit": "kg",
  "lower": {
    "kind": "INCLUSIVE",
    "value": 100.00
  },
  "upper": {
    "kind": "EXCLUSIVE",
    "value": 500.00
  }
}
~~~

Khoảng không có biên trên:

~~~json
{
  "unit": "kg",
  "lower": {
    "kind": "INCLUSIVE",
    "value": 100.00
  },
  "upper": {
    "kind": "UNBOUNDED",
    "value": null
  }
}
~~~

Trong hợp đồng minh họa, đối tượng lower và upper đều bắt buộc. UNBOUNDED mới biểu diễn một phía không bị chặn; bỏ hẳn upper không tự được suy ra cùng ý nghĩa.

### 7.1. DTO cho bound

~~~java
public enum BoundKind {
    INCLUSIVE,
    EXCLUSIVE,
    UNBOUNDED
}
~~~

~~~java
import java.math.BigDecimal;

public record DecimalBoundPayload(
        BoundKind kind,
        BigDecimal value) {
}
~~~

~~~java
public record WeightRangePayload(
        String unit,
        DecimalBoundPayload lower,
        DecimalBoundPayload upper) {
}
~~~

Mỗi kiểu public đặt trong file Java tương ứng khi triển khai. Các snippet không phải một file Java duy nhất và không yêu cầu tạo thêm source file tại bước viết bài này.

### 7.2. Chuyển sang Range<BigDecimal> có kiểm tra

~~~java
import java.math.BigDecimal;
import java.util.Optional;

import org.springframework.data.domain.Range;

public final class WeightRanges {

    private WeightRanges() {
    }

    public static Range<BigDecimal> decode(
            WeightRangePayload input) {

        if (input == null || !"kg".equals(input.unit())) {
            throw new IllegalArgumentException(
                    "Khoảng khối lượng phải dùng unit kg");
        }

        Range.Bound<BigDecimal> lower =
                bound(input.lower());
        Range.Bound<BigDecimal> upper =
                bound(input.upper());

        Optional<BigDecimal> from = lower.getValue();
        Optional<BigDecimal> to = upper.getValue();

        if (from.isPresent() && to.isPresent()) {
            int order = from.get().compareTo(to.get());

            if (order > 0) {
                throw new IllegalArgumentException(
                        "Lower không được lớn hơn upper");
            }

            if (order == 0
                    && (!lower.isInclusive()
                        || !upper.isInclusive())) {

                throw new IllegalArgumentException(
                        "Khoảng rỗng không được phép trong policy này");
            }
        }

        return Range.of(lower, upper);
    }

    private static Range.Bound<BigDecimal> bound(
            DecimalBoundPayload input) {

        if (input == null || input.kind() == null) {
            throw new IllegalArgumentException(
                    "Mỗi bound phải có kind");
        }

        if (input.kind() == BoundKind.UNBOUNDED) {
            if (input.value() != null) {
                throw new IllegalArgumentException(
                        "UNBOUNDED không được có value");
            }

            return Range.Bound.unbounded();
        }

        if (input.value() == null
                || input.value().signum() < 0) {

            throw new IllegalArgumentException(
                    "Bound hữu hạn phải có value không âm");
        }

        return switch (input.kind()) {
            case INCLUSIVE ->
                    Range.Bound.inclusive(input.value());
            case EXCLUSIVE ->
                    Range.Bound.exclusive(input.value());
            case UNBOUNDED ->
                    throw new IllegalStateException(
                            "UNBOUNDED đã được xử lý");
        };
    }
}
~~~

Policy trên chọn một đơn vị, không nhận trọng lượng âm và từ chối một số khoảng rỗng theo thứ tự BigDecimal. Đây là quy tắc ứng dụng, không phải toàn bộ khả năng của Range.

Một codec serialize ngược lại cũng phải đọc từng Bound, giữ kind và value tương ứng. Không serialize unbounded thành một con số lớn giả.

### 7.3. Đổi đơn vị trước khi kiểm tra thứ tự

Nếu một hợp đồng khác cho lower và upper có unit riêng, phải chuẩn hóa hai phía về cùng đơn vị trước khi so sánh.

~~~text
lower = 2 kg
upper = 1500 g
~~~

không phải một khoảng tăng dần chỉ vì numeric value 2 nhỏ hơn 1500.

Tốt hơn, chọn một unit chung ở cấp range nếu điều đó phù hợp với API.

Nhân với hệ số dương giữ thứ tự. Một phép đổi có đảo chiều hoặc mất precision không thể được áp dụng bằng cách map hai đầu mút rồi mặc định mọi loại bound vẫn đúng.

## 8. Thời gian: giữ múi giờ, đơn vị và precision rõ ràng

### 8.1. Timestamp dạng số cần unit

Một số nguyên lớn có thể biểu diễn epoch second, epoch millisecond hoặc một quy ước khác.

Nếu chọn epoch, tên field hoặc schema phải chỉ rõ:

~~~json
{
  "createdAtEpochMillis": 1795568400000
}
~~~

Không dùng một heuristic kiểu “số đủ lớn thì là millisecond” làm hợp đồng dữ liệu mặc định. Nó dễ khiến dữ liệu hợp lệ bị diễn giải sai.

### 8.2. ISO-8601 và cùng một Instant

Một phương án khác là công bố timestamp có offset rõ ràng:

~~~json
{
  "createdAt": "2026-11-25T00:00:00Z"
}
~~~

Hai biểu diễn sau là cùng một thời điểm:

~~~java
import java.time.Instant;
import java.time.OffsetDateTime;

Instant a = Instant.parse(
        "2026-11-25T00:00:00Z");

Instant b = OffsetDateTime.parse(
        "2026-11-25T07:00:00+07:00")
        .toInstant();

boolean sameMoment = a.equals(b);
~~~

So chuỗi trực tiếp sẽ không nhận ra sự tương đương đó.

LocalDateTime không chứa offset hoặc zone. Nếu đầu vào là giờ cục bộ, ứng dụng phải có một quy tắc xác định zone thay vì tự gán một múi giờ không được công bố.

### 8.3. Range thời gian cần giữ cả ngữ nghĩa end

Một payload rõ ràng:

~~~json
{
  "fromInclusive": "2026-11-25T00:00:00Z",
  "untilExclusive": "2026-11-26T00:00:00Z"
}
~~~

có thể được chuyển sang:

~~~java
Range<Instant> period =
        Range.rightOpen(fromInclusive, untilExclusive);
~~~

Snippet giả định hai Instant đã được parse và kiểm tra thứ tự.

Không đổi untilExclusive thành một trường chung tên to rồi làm phía client hiểu là bao gồm cả đầu mút.

### 8.4. Precision qua store

Java có thể giữ mức precision khác với kiểu cột hoặc driver.

Nếu database cắt hoặc làm tròn timestamp, round-trip từ Java qua store không nhất thiết giữ mọi chữ số ban đầu.

Cần công bố precision được hỗ trợ, chuẩn hóa tại một điểm xác định và kiểm tra đọc lại. Không thêm một sai số tùy ý chỉ để làm test qua mà chưa hiểu store đã thay đổi giá trị thế nào.

## 9. Point và thứ tự tọa độ

Một Point tổng quát giữ x và y. Khi ứng dụng dùng cho vị trí địa lý, phải xác định hai trục có nghĩa gì.

DTO công khai có thể chọn:

~~~json
{
  "longitude": 106.70,
  "latitude": 10.78
}
~~~

Nếu adapter quy định x là longitude và y là latitude:

~~~java
import org.springframework.data.geo.Point;

Point point = new Point(longitude, latitude);
~~~

Đây là quy ước được chọn cho adapter đó; không phải lời khẳng định mọi cặp số của Point đều là tọa độ địa lý theo cùng một hệ quy chiếu.

Đối với hợp đồng longitude/latitude theo độ, cần kiểm tra:

- Giá trị hữu hạn.
- Longitude nằm trong miền mà API quy định, thường từ -180 đến 180.
- Latitude nằm trong miền mà API quy định, thường từ -90 đến 90.
- Thứ tự khi chuyển sang định dạng store.
- Hệ quy chiếu và đơn vị góc tương ứng.

Không hoán đổi trục chỉ vì một UI gọi các biến là lat và lon theo một thứ tự khác.

Range của tọa độ hoặc một bounding box cũng không tự diễn tả mọi tình huống địa lý, chẳng hạn cửa sổ cắt qua kinh tuyến đổi ngày. Đây là vấn đề của mô hình truy vấn địa lý cụ thể.

## 10. Vector và Score cần metadata tương thích

### 10.1. Vector không chỉ là một mảng JSON

Vector có từ Spring Data Commons 3.5 và có thể được tạo từ các biểu diễn số được API hỗ trợ. Một số biểu diễn nội bộ không phù hợp để chuyển thành mảng float/double tùy ý. Xem [API Vector](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/Vector.html).

Một hợp đồng ứng dụng có thể chọn:

~~~json
{
  "model": "catalog-embedding-v1",
  "encoding": "float32",
  "dimensions": 3,
  "values": [0.1, 0.2, 0.3]
}
~~~

Ba chiều ở đây chỉ phục vụ ví dụ, không phải cấu hình embedding production.

Cần xác minh:

- Số phần tử thực tế khớp dimensions và index đích.
- Model/profile được phép cho đường truy vấn.
- Kiểu số và precision đúng hợp đồng.
- Các phần tử không null và không có giá trị đặc biệt không được phép.
- Payload không vượt kích thước được hỗ trợ.

Hai vector cùng số chiều nhưng sinh bởi hai embedding model khác nhau chưa chắc thuộc cùng một không gian có thể so sánh.

Không coi việc đổi nhãn model là chuyển đổi vector hợp lệ. Cũng không tự thêm zero hoặc cắt phần tử để làm cho số chiều khớp, trừ khi thuật toán và hợp đồng đã quy định rõ việc đó.

### 10.2. Score cần ngữ nghĩa, không chỉ scale

Một response tìm kiếm có thể chọn:

~~~json
{
  "score": 0.9,
  "scoreProfile": "catalog-search-v1",
  "higherIsBetter": true
}
~~~

Các nhãn là hợp đồng của ứng dụng. Chúng cần phản ánh đúng cách adapter tạo kết quả.

Không đổi score từ distance sang similarity bằng cách chỉ thay nhãn hoặc luôn dùng `1 - value`. Hàm chuẩn hóa phải phù hợp với định nghĩa và miền giá trị của score nguồn.

Cùng một giá trị số cũng không tự có nghĩa là xác suất. Việc serialize 0.9 thành 90% có thể làm thay đổi ý nghĩa mà client nhận được.

Nếu ứng dụng dùng Score, Similarity hoặc SearchResults, cần kiểm tra dòng Spring Data hỗ trợ các API đó; nhóm kiểu này có từ Commons 4.0. Đừng giả định mọi API trong cùng package đã có ở mọi phiên bản.

## 11. Cấu hình JSON và chuyển đổi ở các tầng không giống nhau

### 11.1. Ví dụ ObjectMapper cho DTO và Java time

Với nhánh Jackson 2 và dependency Java time tương ứng:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = JsonMapper.builder()
        .addModule(new JavaTimeModule())
        .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .build();
~~~

Đây là cấu hình minh họa một mapper riêng. Trong ứng dụng Spring Boot, cần tích hợp chính sách vào ObjectMapper thực sự được HTTP converter dùng, tránh tạo một mapper mặc định khác rồi kết luận endpoint đã có cùng cấu hình.

Cờ FAIL_ON_UNKNOWN_PROPERTIES thể hiện lựa chọn từ chối property lạ. Nó chưa đồng thời quy định mọi loại coercion, duplicate key hoặc quy tắc miền dữ liệu.

Ví dụ đọc DTO rồi chuẩn hóa:

~~~java
DistancePayload input = mapper.readValue(
        """
        {
          "value": 1.5,
          "unit": "km"
        }
        """,
        DistancePayload.class);

DistancePayload output =
        DistancePayloads.canonical(input);

String json = mapper.writeValueAsString(output);
~~~

Serializer xuất dữ liệu của DTO công khai. Codec quyết định unit và miền giá trị. Hai trách nhiệm vẫn được phân biệt.

### 11.2. Query parameter không luôn dùng cùng đường với JSON body

Một converter trong Spring ConversionService có thể phục vụ việc chuyển chuỗi query parameter sang một kiểu Java.

Jackson deserializer lại xử lý JSON qua HTTP message converter. Cấu hình một trong hai không tự chứng minh cấu hình còn lại đã thay đổi.

Tương tự, một custom converter phục vụ mapping database thuộc cấu hình của mô-đun lưu trữ. Nó không tự biến thành bộ đọc JSON input.

| Dữ liệu đi qua | Điểm cần kiểm tra |
| --- | --- |
| Query parameter | Argument resolver, ConversionService hoặc formatter tương ứng |
| JSON body | HttpMessageConverter và ObjectMapper thực tế |
| XML body | Converter/parser XML được chọn |
| Database | Mapping và custom conversion của mô-đun store |
| Message queue/cache | Serializer và version của message/cache đó |

Có thể dùng chung hàm chuẩn hóa miền như toMeters giữa các adapter. Nhưng mỗi đường vào vẫn cần được nối đúng với hàm đó.

### 11.3. Module hỗ trợ thư viện không thay thế schema ứng dụng

Một mô-đun Jackson có thể cung cấp serializer/deserializer cho một số kiểu Spring Data. Phải xác nhận đúng thư viện và dòng phiên bản đang dùng.

Không suy ra rằng đăng ký một mô-đun sẽ:

- Hỗ trợ mọi kiểu Commons.
- Chọn unit nghiệp vụ cho ứng dụng.
- Áp dụng validation.
- Giữ tương thích với schema do một client cũ đã tự suy ra.
- Đồng bộ cách lưu của mọi loại store.

Nếu public API phải giữ schema ổn định, DTO và mapper tường minh giúp hạn chế phụ thuộc vào chi tiết serialization nội bộ.

## 12. Tương thích đầu vào cũ theo một adapter rõ ràng

Giả sử phiên bản cũ nhận:

~~~json
{
  "radiusKm": 1.5
}
~~~

Phiên bản mới muốn nhận:

~~~json
{
  "radius": {
    "value": 1500,
    "unit": "m"
  }
}
~~~

Trong giai đoạn tương thích, có thể dùng một DTO boundary nhận hai dạng nhưng từ chối việc gửi đồng thời.

~~~java
import java.math.BigDecimal;

public record NearbyRequest(
        DistancePayload radius,
        BigDecimal radiusKm) {
}
~~~

~~~java
public final class NearbyRequests {

    private NearbyRequests() {
    }

    public static DistancePayload normalize(
            NearbyRequest request) {

        if (request == null) {
            throw new IllegalArgumentException(
                    "Request không được rỗng");
        }

        boolean hasCurrent = request.radius() != null;
        boolean hasLegacy = request.radiusKm() != null;

        if (hasCurrent == hasLegacy) {
            throw new IllegalArgumentException(
                    "Phải gửi đúng một trong radius hoặc radiusKm");
        }

        DistancePayload selected = hasCurrent
                ? request.radius()
                : new DistancePayload(
                        request.radiusKm(), "km");

        return DistancePayloads.canonical(selected);
    }
}
~~~

Chính sách này không đoán đơn vị từ numeric value. Field cũ có tên radiusKm và hợp đồng đã xác định unit, nên adapter có căn cứ để chuyển đổi.

Ngay cả khi hai dạng cùng gửi một khoảng cách tương đương, ví dụ vẫn chọn từ chối. Mục tiêu là tránh một nguồn input có hai cách mô tả cùng dữ liệu. Ứng dụng khác có thể chọn quy tắc khác, nhưng phải công bố và kiểm tra.

### 12.1. Một số thay đổi vẫn có thể phá hợp đồng

| Thay đổi | Rủi ro tương thích |
| --- | --- |
| Đổi m thành km nhưng không đổi value | Thay ý nghĩa dữ liệu |
| Thêm unit bắt buộc | Client cũ thiếu field |
| Đổi min/max đóng thành khoảng nửa mở | Thay tập kết quả truy vấn |
| Đổi epoch millis thành seconds cùng tên field | Mốc thời gian bị hiểu sai |
| Đổi tên enum nhận từ client | Payload cũ có thể không đọc được |
| Đổi model vector | Cùng số chiều chưa bảo đảm tương thích |
| Đổi score profile | Ngưỡng hoặc chiều xếp hạng cũ có thể không còn đúng |
| Thêm field response | Reader strict cũ có thể từ chối |

“Tương thích” cần xét cả producer và consumer, không chỉ xem server mới có đọc một JSON cũ hay không.

### 12.2. Ma trận reader/writer

| Writer | Reader | Cần kiểm tra |
| --- | --- | --- |
| Cũ | Mới | Adapter legacy đọc và chuẩn hóa đúng |
| Mới | Cũ | Reader cũ nhận được schema nào, có cần phiên bản endpoint không |
| Mới | Mới | Schema hiện tại và validation đúng |
| Dữ liệu đã lưu từ phiên bản cũ | Code mới | Có nhận diện version và chuyển đổi có căn cứ không |

Việc đọc nhiều dạng input không yêu cầu server mãi mãi trả nhiều dạng output. Một output canonical có thể đơn giản hóa client mới, nhưng thay đổi output cho client cũ phải được xử lý theo chiến lược phiên bản phù hợp.

Không âm thầm đổi ý nghĩa field cũ rồi coi tên field không đổi là tương thích.

### 12.3. Missing, null và giá trị bằng 0

Với một DTO record thông thường, một field bị bỏ qua và một field được gửi null có thể cùng trở thành null khi deserialize theo cấu hình tương ứng.

Nếu API PATCH cần phân biệt:

- Không gửi: giữ nguyên.
- Gửi null: xóa.
- Gửi 0: đặt giá trị 0.

thì cần mô hình presence hoặc cơ chế patch rõ ràng. Không dùng một Double primitive hoặc null đơn lẻ để thay thế mọi trạng thái.

NearbyRequest trong ví dụ là request chọn một dạng bán kính hoàn chỉnh, không phải một implementation PATCH.

## 13. Dữ liệu lưu trữ, message và cache cũng cần hợp đồng

Một store có thể lưu Distance dưới dạng số cùng unit, số normalized, object nhúng hoặc một kiểu native mà mô-đun hỗ trợ.

Cần quyết định:

- Biểu diễn nào là canonical ở lớp lưu trữ.
- Phiên bản schema được nhận diện bằng cách nào.
- Precision và unit được giữ đến đâu.
- Index/truy vấn đọc đúng ý nghĩa nào.
- Dữ liệu cũ được chuyển đổi hoặc đọc tương thích thế nào.

Không thay đổi biểu diễn lưu trữ chỉ bằng một thay đổi serializer HTTP rồi mặc định mọi truy vấn vẫn đúng.

Đối với message hoặc cache, tên class Java và cấu trúc field nội bộ của một dependency không tự tạo một schema bền vững qua mọi lần nâng cấp.

Một envelope do ứng dụng quản lý có thể có schemaVersion cùng dữ liệu cụ thể. Version đó cần có quy tắc reader/writer thực tế, không chỉ thêm một con số nhưng không xử lý khác biệt.

## 14. Kiểm tra round-trip theo ý nghĩa

### 14.1. JSON DTO round-trip

~~~java
DistancePayload canonical =
        DistancePayloads.canonical(
                new DistancePayload(
                        new BigDecimal("1.5"), "km"));

String encoded =
        mapper.writeValueAsString(canonical);

DistancePayload decoded =
        mapper.readValue(
                encoded, DistancePayload.class);

assertEquals("m", decoded.unit());
assertEquals(
        0,
        new BigDecimal("1500")
                .compareTo(decoded.value()));
~~~

Snippet giả định mapper Jackson 2 và các import assertion đã được cấu hình.

Test không ép JSON phải chứa đúng chuỗi số `1500.0` hay `1500` nếu hợp đồng chỉ yêu cầu tương đương giá trị số.

Nếu schema cố ý dùng chuỗi thập phân với format cụ thể, khi đó định dạng chuỗi lại là một phần cần kiểm tra riêng.

### 14.2. Chuyển metric và sai số

Một kiểm tra qua metric có thể dùng tolerance theo chính sách đã chọn:

~~~java
Distance original =
        new Distance(5.0, Metrics.KILOMETERS);

Distance restored = original
        .in(Metrics.MILES)
        .in(Metrics.KILOMETERS);

assertEquals(
        original.getValue(),
        restored.getValue(),
        1e-9);
~~~

Tolerance trong snippet chỉ là giá trị minh họa cho phép tính đó, không phải một sai số mặc định cho mọi khoảng cách hoặc mọi store.

Không so double bằng chuỗi được làm tròn ở một bước hiển thị rồi dùng nó để kết luận phép chuyển đổi domain chính xác.

### 14.3. Range round-trip

Với schema bound, phải kiểm tra đủ:

- Lower value.
- Lower kind.
- Upper value.
- Upper kind.
- Unit.
- Trạng thái unbounded.

Kiểm tra thêm `contains` tại đúng đầu mút giúp phát hiện lỗi đổi EXCLUSIVE thành INCLUSIVE dù hai số vẫn giống nhau.

### 14.4. Ma trận kiểm tra bổ sung

| Nhóm | Các tình huống quan trọng |
| --- | --- |
| Distance | m/km tương đương, âm, vượt trần, unit thiếu/lạ |
| Range | Mọi loại bound, unbounded, lower lớn hơn upper |
| Thời gian | Cùng Instant khác offset, epoch đúng unit, precision qua store |
| Point | Trục đúng thứ tự, giá trị hữu hạn, miền tọa độ |
| Vector | Dimensions không khớp, model sai, phần tử không hợp lệ |
| Score | Profile và chiều điểm đúng hợp đồng |
| JSON parser | Coercion, property lạ, duplicate key theo policy |
| Compatibility | Dạng cũ, dạng mới, cả hai cùng gửi, không có dạng nào |
| Runtime | ObjectMapper/converter thật của endpoint |
| Store | Lưu, đọc lại và truy vấn đúng sau chuyển đổi |

Test codec trong bộ nhớ kiểm tra chuẩn hóa. Test HTTP kiểm tra serializer và wiring thật. Test store kiểm tra mapping cùng precision thực tế. Không dùng một loại kiểm tra để kết luận thay cho tất cả các đường dữ liệu.

## 15. Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Serialize mỗi numeric value | Mất unit hoặc profile | Dùng schema giữ đủ metadata |
| Coi Serializable là hỗ trợ JSON | Deserialize hoặc contract không đúng | Kiểm tra serializer và DTO |
| Coi normalized distance là meter | Query dùng sai khoảng cách | Chọn metric và adapter tường minh |
| Đổi unit nhưng không đổi số | Thay giá trị vật lý | Dùng phép chuyển đổi nhất quán |
| So BigDecimal bằng equals cho mọi mục đích | Khác scale bị coi khác giá trị số | Dùng phép so sánh theo mục tiêu |
| Chỉ giữ min/max của Range linh hoạt | Mất loại bound | Encode kind và unbounded rõ ràng |
| Đoán seconds/millis theo độ lớn | Diễn giải sai timestamp | Ghi unit trong tên/schema |
| Coi cùng dimensions là cùng model vector | Tìm kiếm sai không gian | Kiểm tra model/index/profile |
| Converter database được coi như JSON converter | Một đường chạy, đường khác lỗi | Cấu hình từng adapter đúng chỗ |
| Fallback unit không công bố | Che lỗi input hoặc hiểu sai client cũ | Dùng adapter legacy có căn cứ |
| Chỉ test output string | Không phát hiện thay đổi ngữ nghĩa | Kiểm tra round-trip và đầu mút |
| Thay output mà không kiểm tra reader cũ | Phá client dù schema mới hợp lý | Kiểm tra ma trận tương thích |

## 16. Bài thực hành

1. Thiết kế DTO khoảng cách có value và unit, chọn unit canonical.
2. Chuẩn hóa m/km và áp dụng giới hạn trước khi tạo Distance.
3. Mô tả Range giữ đầy đủ loại bound và trạng thái unbounded.
4. Chọn định dạng thời gian có unit/offset rõ ràng.
5. Nếu dùng tọa độ, xác định thứ tự trục và hệ quy chiếu.
6. Nếu dùng vector hoặc score, xác định metadata tương thích của model/profile.
7. Viết một adapter nhận dạng input cũ có đơn vị đã biết.
8. Từ chối dữ liệu mâu thuẫn thay vì âm thầm chọn một giá trị.
9. Kiểm tra codec, HTTP và store bằng các round-trip phù hợp.
10. Giải thích thay đổi nào chỉ đổi biểu diễn và thay đổi nào làm đổi ý nghĩa dữ liệu.

Bài thực hành đạt yêu cầu khi dữ liệu qua các tầng vẫn giữ đúng **giá trị, đơn vị, biên, precision và ngữ cảnh**, đồng thời các dạng input được hỗ trợ có **quy tắc đọc và chuẩn hóa rõ ràng**.
