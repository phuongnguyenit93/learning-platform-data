# Distance, Metric và quy ước đơn vị

Một chức năng tìm cửa hàng trong bán kính 500 mét có thể cho kết quả sai hàng nghìn lần nếu một lớp hiểu số 500 là mét, còn lớp khác hiểu nó là kilômét. Lỗi này vẫn có thể biên dịch, truy vấn vẫn chạy và dữ liệu trả về vẫn trông hợp lý nếu chỉ quan sát một vài bản ghi.

Trong chương **Kiểu dữ liệu dùng chung** của **Spring Data Commons**, `Distance`, `Metric` và `Metrics` giúp biểu diễn giá trị khoảng cách cùng quy ước đơn vị. Chúng cung cấp abstraction để các module tích hợp, nhưng không tự làm mọi kho dữ liệu dùng chung hệ tọa độ, phép đo hoặc giao thức truy vấn geo. Bài học tập trung vào cách giữ ngữ nghĩa đơn vị từ API qua service đến module lưu trữ.

## 1. Distance gồm giá trị và Metric

Các kiểu thuộc package `org.springframework.data.geo`:

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metric;
import org.springframework.data.geo.Metrics;

Distance radius = new Distance(5, Metrics.KILOMETERS);

System.out.println(radius.getValue());
System.out.println(radius.getMetric());
```

`radius` mô tả giá trị 5 theo metric kilômét. Hai thành phần phải được hiểu cùng nhau:

| Thành phần | Vai trò |
|---|---|
| `getValue()` | Trị số trong metric hiện tại |
| `getMetric()` | Quy ước metric đi kèm trị số |
| `getNormalizedValue()` | Trị số đã chuẩn hóa theo multiplier của metric |
| `in(targetMetric)` | Tạo biểu diễn khoảng cách theo metric đích tương thích |

Chỉ lấy `getValue()` rồi truyền tiếp như một `double` làm mất thông tin đơn vị. Một biến tên `distance` chứa số 5 không thể tự nói đó là 5 km, 5 mile hay một giá trị trung lập theo ngữ cảnh.

`Distance` là một đối tượng biểu diễn đại lượng khoảng cách. Việc tạo `Distance` không tự tính khoảng cách giữa hai điểm, không tự truy vấn database và không tự xác định hệ tọa độ của dữ liệu.

## 2. Metric là quy ước chuyển đổi, Metrics là các lựa chọn có sẵn

`Metric` mô tả thông tin phục vụ quy đổi, trong đó có multiplier và tên viết tắt. `Metrics` cung cấp các metric thông dụng:

```java
Metric kilometers = Metrics.KILOMETERS;
Metric miles = Metrics.MILES;
Metric neutral = Metrics.NEUTRAL;
```

Ví dụ:

```java
Distance fiveKilometers = new Distance(5, Metrics.KILOMETERS);
Distance threeMiles = new Distance(3, Metrics.MILES);
```

Không nên coi `Metric` chỉ là nhãn hiển thị. Multiplier tham gia vào phép chuẩn hóa và chuyển đổi. Hai implementation có cùng abbreviation nhưng multiplier khác nhau không tự có cùng ý nghĩa số học.

Ngược lại, tên viết tắt cũng không phải một parser nhận mọi chuỗi từ HTTP. Một request gửi `unit=km` cần có quy tắc của ứng dụng để ánh xạ chuỗi đó sang metric được hỗ trợ.

Cơ chế này không phải một hệ thống đơn vị vật lý có kiểm tra chiều ở mức kiểu Java. Ứng dụng vẫn phải giữ nhất quán về ý nghĩa của các metric và cách module sử dụng chúng.

## 3. NEUTRAL không mặc định là mét

Hai cách tạo sau cần được phân biệt:

```java
Distance explicit = new Distance(500, Metrics.KILOMETERS);
Distance neutral = new Distance(500);
```

Constructor chỉ có trị số dùng metric trung lập. Không có căn cứ để kết luận `new Distance(500)` luôn mang nghĩa 500 mét.

Metric trung lập hữu ích khi đơn vị do ngữ cảnh hoặc thao tác cụ thể quy định. Tuy nhiên, phải có hợp đồng rõ ràng ở nơi sử dụng. Tùy module, mô hình dữ liệu và phép toán, một trị số thô có thể được hiểu theo đơn vị của tọa độ, theo quy ước truy vấn hoặc theo một dạng chuẩn hóa khác.

Các nhận định sau không an toàn khi chưa biết ngữ cảnh:

```text
Distance(500) chắc chắn là 500 m.
Distance(1) chắc chắn là 1 km.
NEUTRAL tự đọc hệ tọa độ để biết đơn vị.
```

Nếu API công khai nhận mét nhưng tầng truy vấn chọn kilômét, hãy chuyển 500 mét thành `new Distance(0.5, Metrics.KILOMETERS)` một cách tường minh.

Việc gắn nhãn rõ ràng ở biên ứng dụng giúp tránh truyền một giá trị trung lập qua nhiều lớp rồi để lớp cuối tự đoán đơn vị.

## 4. Giá trị chuẩn hóa được tính như thế nào?

Cơ chế của `Distance` sử dụng multiplier theo ý tưởng:

```text
normalizedValue = value / sourceMetric.multiplier

targetValue = normalizedValue × targetMetric.multiplier
```

Với các metric địa lý tiêu chuẩn, multiplier gắn với quy ước chuẩn hóa khoảng cách của thư viện; nó không chỉ là các số 1, 1000 như một bảng quy đổi mét/kilômét thông thường.

Trong cách diễn giải địa lý cầu tương ứng, giá trị chuẩn hóa liên hệ với khoảng cách góc theo mô hình và hệ số mà metric sử dụng. Không đọc `getNormalizedValue()` rồi mặc định đó là số mét.

Ví dụ:

```java
Distance radius = new Distance(5, Metrics.KILOMETERS);

double kilometers = radius.getValue();
double normalized = radius.getNormalizedValue();
```

Hai biến có ý nghĩa khác nhau. Biến thứ nhất là 5 theo metric km; biến thứ hai đã đi qua phép chia multiplier và không còn là trị số 5 km để hiển thị trực tiếp.

Module lưu trữ có thể cần trị số chuẩn hóa hoặc có converter riêng. Ứng dụng cần sử dụng đúng API của module, không tự truyền `normalized` vào mọi truy vấn geo chỉ vì nó có tên là chuẩn hóa.

## 5. Chuyển đổi bằng in thay vì đổi nhãn

Chuyển kilômét sang mile:

```java
Distance original = new Distance(5, Metrics.KILOMETERS);
Distance converted = original.in(Metrics.MILES);

System.out.println(original.getValue());
System.out.println(converted.getValue());
```

Trị số đầu vẫn là 5 km. Trị số sau xấp xỉ 3,107 mile theo phép quy đổi của metric.

Cách sau chỉ tạo một đại lượng khác, không phải phép đổi đơn vị:

```java
// 5 mile, không phải 5 km đã được đổi sang mile.
Distance relabeled = new Distance(original.getValue(), Metrics.MILES);
```

Phép chuyển đổi cần điều chỉnh trị số, không chỉ thay nhãn. `in(...)` trả biểu diễn ở metric đích; không nên giả định biến gốc đã tự được đổi metric nếu không dùng kết quả trả về.

Đổi qua lại có thể tạo sai số số thực nhỏ. Khi kiểm chứng giá trị, nên đưa về cùng metric và dùng sai số chấp nhận phù hợp, thay vì so sánh tuyệt đối hai số `double` sau nhiều phép quy đổi.

Không dùng giá trị đã làm tròn phục vụ hiển thị để quyết định lại ranh giới tìm kiếm. Cần giữ độ chính xác tính toán cho truy vấn và chỉ làm tròn ở lớp biểu diễn nếu hợp đồng yêu cầu.

## 6. Chuẩn hóa đơn vị ngay tại biên API

Một hợp đồng HTTP rõ ràng có thể yêu cầu cả trị số và đơn vị:

```json
{
  "radius": {
    "value": 500,
    "unit": "m"
  }
}
```

Ứng dụng chọn kilômét làm quy ước nội bộ, đồng thời công bố chỉ nhận `m`, `km` và `mi`.

Ví dụ bộ chuẩn hóa dùng cú pháp Java hiện đại:

```java
import java.util.Locale;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

final class SearchRadiusPolicy {

    private static final double MAX_RADIUS_KM = 50.0;

    static Distance toKilometers(Double value, String unit) {
        if (value == null || !Double.isFinite(value) || value <= 0) {
            throw new InvalidRadiusException(
                    "Bán kính phải là số hữu hạn lớn hơn 0");
        }
        if (unit == null || unit.isBlank()) {
            throw new InvalidRadiusException("Phải chỉ rõ đơn vị bán kính");
        }

        String normalizedUnit = unit.strip().toLowerCase(Locale.ROOT);

        Distance radius = switch (normalizedUnit) {
            case "m" -> new Distance(value / 1000.0, Metrics.KILOMETERS);
            case "km" -> new Distance(value, Metrics.KILOMETERS);
            case "mi" -> new Distance(value, Metrics.MILES)
                    .in(Metrics.KILOMETERS);
            default -> throw new InvalidRadiusException(
                    "Đơn vị được hỗ trợ: m, km, mi");
        };

        double kilometers = radius.getValue();
        if (!Double.isFinite(kilometers)
                || kilometers <= 0
                || kilometers > MAX_RADIUS_KM) {
            throw new InvalidRadiusException(
                    "Bán kính sau quy đổi phải lớn hơn 0 và không vượt 50 km");
        }

        return radius;
    }
}

final class InvalidRadiusException extends RuntimeException {

    InvalidRadiusException(String message) {
        super(message);
    }
}
```

Giới hạn 50 km là chính sách minh họa, không phải giới hạn của Spring Data Commons. Ví dụ chọn từ chối bán kính 0; một nghiệp vụ khác có thể cho phép 0 nếu đã xác định ý nghĩa và khả năng truy vấn tương ứng.

Kiểm tra sau quy đổi bảo vệ hợp đồng nội bộ trước giá trị quá lớn, tràn số hoặc giá trị quá nhỏ bị mất độ chính xác khi đổi đơn vị. Đừng chỉ dựa vào việc constructor `Distance` tạo được object để kết luận input phù hợp nghiệp vụ.

Ở tầng HTTP, `InvalidRadiusException` cần được ánh xạ thành lỗi đầu vào theo chính sách API. Không bắt mọi lỗi geo/database rồi chuyển thành cùng một lỗi “đơn vị không hợp lệ”.

## 7. Kiểm tra giới hạn sau khi thống nhất đơn vị

Giả sử chính sách cho phép tối đa 50 km. Hai request sau có thể tương đương về độ lớn dù trị số rất khác:

```text
value=1000, unit=m
value=1, unit=km
```

Nếu chỉ so sánh trị số thô `value <= 50`, request 1000 m bị từ chối trong khi request 1 km được nhận. Ngược lại, một request theo mile có thể vượt giới hạn km dù trị số nhìn nhỏ hơn 50.

Trình tự hợp lý:

1. Kiểm tra có trị số, có đơn vị và trị số hữu hạn.
2. Ánh xạ đơn vị theo tập được hỗ trợ.
3. Chuyển về quy ước nội bộ.
4. Áp dụng giới hạn nghiệp vụ trên cùng quy ước đó.
5. Truyền `Distance` với metric tường minh vào lớp truy vấn.

Không nên dựa vào tên biến, ngôn ngữ giao diện hoặc một mặc định không được công bố để quyết định đơn vị. Nếu muốn mặc định, hãy ghi rõ mặc định ấy trong hợp đồng API và dùng nhất quán.

## 8. Có thể định nghĩa Metric mét, nhưng cần hiểu phạm vi

`Metrics` không phải một bảng liệt kê mọi đơn vị có thể tồn tại. Có thể triển khai `Metric` riêng khi cần phép quy đổi tương thích.

Ví dụ metric mét dựa trên cùng hệ quy đổi với kilômét:

```java
import org.springframework.data.geo.Metric;
import org.springframework.data.geo.Metrics;

enum ExtraMetric implements Metric {

    METERS;

    @Override
    public double getMultiplier() {
        return Metrics.KILOMETERS.getMultiplier() * 1000.0;
    }

    @Override
    public String getAbbreviation() {
        return "m";
    }
}
```

Khi đó:

```java
Distance meters = new Distance(500, ExtraMetric.METERS);
Distance kilometers = meters.in(Metrics.KILOMETERS);
```

Trị số đích là khoảng 0,5 km theo phép quy đổi tương ứng.

Điểm quan trọng là multiplier phải cùng nền chuẩn hóa với các metric dùng để quy đổi. Chỉ trả abbreviation `m` mà chọn multiplier tùy ý không tạo ra metric mét đúng nghĩa.

Metric tùy biến hoạt động trong phép toán `Distance` không đồng nghĩa mọi module, converter, serializer hoặc giao thức của kho dữ liệu đều hiểu nó. Cần xác nhận khả năng hỗ trợ trước khi truyền metric mới vào một truy vấn cụ thể.

Với API chỉ cần nhận mét từ người dùng, cách đổi sang `Metrics.KILOMETERS` ngay ở biên như phần 6 thường đơn giản hơn việc yêu cầu cả chuỗi tích hợp nhận biết metric mới.

## 9. Distance không xác định hệ tọa độ của Point

Ví dụ một điểm:

```java
import org.springframework.data.geo.Point;

Point origin = new Point(106.7009, 10.7769);
```

`Point` biểu diễn các giá trị x và y. Ý nghĩa kinh độ/vĩ độ, hệ quy chiếu và thứ tự tọa độ cần được xác định bởi hợp đồng của ứng dụng và module.

Không được suy ra rằng:

```text
Point luôn có tọa độ theo mét.
Khoảng cách giữa hai Point có thể lấy bằng hiệu tọa độ rồi gắn KILOMETERS.
Distance mang metric km sẽ tự chuyển mọi Point sang một hệ tọa độ phù hợp.
```

Với dữ liệu kinh độ/vĩ độ, một độ không phải một khoảng cách mét cố định ở mọi vị trí và mọi hướng. Với hệ tọa độ phẳng đã chiếu, đơn vị có thể là mét nhưng vẫn cần biết chính xác hệ quy chiếu và phép toán đang dùng.

`Distance` không tự cung cấp CRS hoặc SRID cho toàn bộ truy vấn. Nếu backend yêu cầu các thông tin đó, ứng dụng phải cấu hình và truyền dữ liệu đúng theo API của backend/module.

Đổi đơn vị khoảng cách và đổi hệ tọa độ là hai thao tác khác nhau. Đổi 500 m sang 0,5 km không chuyển một cặp kinh độ/vĩ độ thành tọa độ phẳng.

## 10. Tích hợp với truy vấn geo của module

Một hợp đồng ứng dụng có thể giữ rõ kiểu đầu vào:

```java
import java.util.List;

import org.springframework.data.geo.Distance;
import org.springframework.data.geo.GeoResult;
import org.springframework.data.geo.Point;

interface NearbyShopReader {

    List<GeoResult<Shop>> findNearby(Point origin, Distance maximumDistance);
}
```

Đây là **port của ứng dụng minh họa**, không phải interface có sẵn được Spring Data tự triển khai. Adapter của module cần thực hiện truy vấn geo bằng repository, template hoặc API phù hợp.

Service có thể gọi:

```java
Distance radius = SearchRadiusPolicy.toKilometers(500.0, "m");
List<GeoResult<Shop>> matches = nearbyShopReader.findNearby(origin, radius);
```

Adapter cần biết:

| Câu hỏi | Vì sao cần xác định |
|---|---|
| Backend có hỗ trợ near/within mong muốn không? | Commons không tự cung cấp mọi phép toán geo |
| Dữ liệu dùng mô hình tọa độ nào? | Ảnh hưởng cách đo và tạo truy vấn |
| Query nhận đơn vị hoặc trị số chuẩn hóa nào? | Tránh truyền nhầm `getValue()` và `getNormalizedValue()` |
| Index và mapping geo đã đúng chưa? | Chữ ký Java không tự tạo đúng khả năng thực thi |
| Khoảng cách kết quả dùng metric gì? | Cần biểu diễn và so sánh đúng đơn vị |

Một số module có derived query geo hoặc converter nhận `Distance`; một số trường hợp cần template, fragment hoặc truy vấn riêng. Không đặt một tên phương thức `Near` trên mọi repository rồi suy ra module đã hỗ trợ nó.

Đặc biệt, API gốc của một kho dữ liệu có thể nhận mét cho một toán tử, nhưng một API hoặc kiểu tọa độ khác lại có quy ước khác. Khi dùng abstraction Spring Data, phải đối chiếu đúng tầng chuyển đổi đang áp dụng.

## 11. Giữ metric của khoảng cách kết quả

`GeoResult<T>` có thể đi kèm `Distance` cho một đối tượng kết quả. Khi tạo response, không nên chỉ gửi một số không có đơn vị:

```json
{
  "shopId": 101,
  "distance": 0.48
}
```

Client không biết 0,48 là km, mile hay một trị số khác. Một hợp đồng rõ hơn:

```json
{
  "shopId": 101,
  "distance": {
    "value": 0.48,
    "unit": "km"
  }
}
```

DTO có thể chuẩn hóa về km nếu adapter đã cung cấp metric địa lý tương thích và được hợp đồng chấp nhận:

```java
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;

record DistanceView(double value, String unit) {

    static DistanceView fromGeographicDistance(Distance distance) {
        if (distance.getMetric() != Metrics.KILOMETERS
                && distance.getMetric() != Metrics.MILES) {
            throw new IllegalArgumentException(
                    "Ví dụ response chỉ nhận khoảng cách đã xác định là km hoặc mi");
        }

        Distance kilometers = distance.in(Metrics.KILOMETERS);
        return new DistanceView(kilometers.getValue(), "km");
    }
}
```

Giới hạn metric trong ví dụ là một lựa chọn hợp đồng. Nếu ứng dụng hỗ trợ metric khác, cần mở rộng chính sách có chủ đích.

Nếu adapter nhận một trị số thô được backend quy định là mét, hãy chuyển nó thành metric tường minh theo hợp đồng adapter trước khi tạo DTO. Không lấy `Distance` trung lập rồi gọi `in(KILOMETERS)` như thể `NEUTRAL` tự mang nghĩa mét.

Cách JSON mặc định serialize trực tiếp một kiểu thư viện không nhất thiết là schema API mà ứng dụng muốn duy trì. DTO giúp công bố trị số, đơn vị và chính sách làm tròn một cách rõ ràng.

## 12. Bán kính và khoảng cách trả về là hai vai trò

Một request dùng bán kính 5 km, nhưng mỗi cửa hàng có thể cách điểm gốc 0,48 km, 1,2 km hoặc 4,9 km. Không điền bán kính request vào trường khoảng cách của từng kết quả.

Cần phân biệt:

| Đại lượng | Ý nghĩa |
|---|---|
| Bán kính tìm kiếm | Giới hạn/phạm vi truy vấn do người dùng yêu cầu |
| Khoảng cách đến từng kết quả | Giá trị do phép đo hoặc truy vấn xác định cho đối tượng đó |
| Khoảng cách trung bình nếu có | Đại lượng tổng hợp của một tập kết quả theo hợp đồng cụ thể |

Đơn vị bán kính và đơn vị hiển thị kết quả có thể khác nếu có quy đổi rõ ràng. Ví dụ API nhận mét, service dùng km và giao diện hiển thị mile.

Tuy nhiên, mỗi lần đổi cần giữ được ý nghĩa của nguồn. Một giá trị backend đã chuẩn hóa không được gắn nhãn là khoảng cách kết quả theo km chỉ vì bán kính request dùng km.

Nếu kho dữ liệu tính khoảng cách theo mô hình cầu hoặc một phép xấp xỉ khác, kết quả không tự là độ dài đường đi trên mạng đường bộ. `Distance` không biến khoảng cách địa lý thành quãng đường lái xe hay thời gian di chuyển.

## 13. So sánh, làm tròn và ranh giới tìm kiếm

Khi so sánh các trị số bằng mã ứng dụng, trước hết cần thống nhất metric:

```java
Distance limit = new Distance(5, Metrics.KILOMETERS);
Distance candidate = new Distance(3, Metrics.MILES);

double candidateKm = candidate.in(Metrics.KILOMETERS).getValue();
boolean within = candidateKm <= limit.getValue();
```

Ví dụ chỉ minh họa so sánh số học giữa hai khoảng cách đã có ý nghĩa tương thích. Nó không thay thế phép kiểm tra địa lý của backend hoặc chính sách sai số ở ranh giới.

Không so sánh trực tiếp `3 <= 5` rồi kết luận chỉ vì trị số 3 mile nhỏ hơn trị số 5 km. Các con số phải ở cùng đơn vị trước khi so sánh bằng toán tử số học thông thường.

Đối với điểm gần đúng ranh giới bán kính, cần hiểu phép đo, độ chính xác lưu trữ và chính sách bao gồm biên của toán tử truy vấn. Không tự thêm một epsilon tùy ý rồi coi đó là cách sửa mọi sai lệch geo.

Việc làm tròn để hiển thị cũng cần được công bố. Nếu một kết quả được làm tròn từ giá trị gần 0,500 km xuống một số hiển thị, client không nên dùng số đã làm tròn để suy ngược chính xác kết luận inclusion của truy vấn.

Giữ giá trị đủ chính xác trong tính toán; làm tròn ở response hoặc giao diện khi có yêu cầu, và dùng cùng một quy tắc hiển thị cho các kết quả tương đương.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `new Distance(500)` để diễn tả mét mà không có hợp đồng | Backend có thể hiểu một đơn vị khác | Chuyển sang metric tường minh trước truy vấn |
| Đổi metric bằng cách giữ nguyên trị số | 5 km thành 5 mile | Dùng phép chuyển đổi `in(...)` phù hợp |
| Hiển thị `getNormalizedValue()` như mét | Trị số và nhãn không cùng nghĩa | Hiển thị `getValue()` sau khi đổi về metric công khai |
| So sánh số km với số mile | Kết luận bán kính sai | Chuẩn hóa về cùng metric |
| Truyền `getValue()` vào API gốc không cùng đơn vị | Query quá rộng hoặc quá hẹp | Đặt quy tắc chuyển đổi ở adapter |
| Metric tùy biến chỉ đổi abbreviation | Phép quy đổi sai | Dùng multiplier tương thích và xác nhận module hỗ trợ |
| Cho rằng Point tự có CRS | Sai cách hiểu tọa độ | Công bố hệ tọa độ và quy ước của module |
| Làm tròn trước khi truy vấn | Thay đổi ranh giới tìm kiếm | Giữ độ chính xác đến bước biểu diễn |
| Lấy bán kính request làm distance của mọi kết quả | Response sai ý nghĩa | Dùng khoảng cách thật của từng kết quả |
| Công khai số distance không có đơn vị | Client phải tự đoán | Trả trị số cùng đơn vị hoặc schema có quy ước rõ |

Một lỗi đơn vị thường không tạo exception. Vì vậy, chỉ kiểm tra “query không lỗi” hoặc “có dữ liệu trả về” là chưa đủ để xác nhận hợp đồng đã đúng.

## 15. Tình huống kiểm chứng hợp đồng đơn vị

Các tình huống học tập hữu ích:

| Đầu vào/điều kiện | Kỳ vọng cần xác định |
|---|---|
| 500 m | Quy đổi thành 0,5 km theo chính sách nội bộ |
| 1 km và 1000 m | Tạo phạm vi tương đương sau quy đổi |
| 1 mi | Quy đổi xấp xỉ 1,609 km theo metric tương ứng |
| Thiếu đơn vị | Từ chối hoặc dùng mặc định đã công bố, không tự đoán |
| Đơn vị không được hỗ trợ | Phản hồi lỗi đầu vào có chủ đích |
| Số âm hoặc 0 | Theo chính sách bán kính đã chọn |
| NaN/vô cực nếu xuất hiện ở biên nội bộ | Không đi vào truy vấn như bán kính hợp lệ |
| Giá trị vượt giới hạn sau quy đổi | Từ chối theo cùng một đơn vị chuẩn |
| Kết quả trả metric trung lập | Adapter phải xác định ý nghĩa trước khi tạo response |
| Điểm gần ranh giới | Đối chiếu đúng mô hình và ngữ nghĩa toán tử backend |
| Metric tùy biến | Kiểm chứng phép đổi và khả năng hỗ trợ của chuỗi tích hợp |

Với các cặp input tương đương, nên so sánh giá trị sau quy đổi trong sai số chấp nhận phù hợp. Với kết quả truy vấn, cần dùng dữ liệu có vị trí và khoảng cách đã được xác định theo mô hình của backend, không chỉ so sánh số lượng bản ghi.

Các tình huống này cũng cần giữ nguyên bộ lọc tenant/quyền. Chuẩn hóa bán kính đúng không tự bảo đảm truy vấn chỉ đọc dữ liệu được phép xem.

## 16. Bài tập tự kiểm tra

### Tình huống 1: Request gửi radius=500 nhưng không có unit

Frontend hiểu mét, backend tạo `new Distance(500)`.

**Phân tích:** hợp đồng đơn vị đang thiếu. `NEUTRAL` không tự là mét. Cần công bố đơn vị, chuẩn hóa ở biên và truyền metric rõ ràng vào đường truy vấn.

### Tình huống 2: Đổi 5 km thành mile bằng constructor mới

Mã dùng `new Distance(old.getValue(), Metrics.MILES)`.

**Phân tích:** mã đã tạo 5 mile. Để giữ cùng độ dài biểu diễn, phải dùng phép quy đổi thích hợp như `old.in(Metrics.MILES)`.

### Tình huống 3: Gửi normalizedValue trong response với nhãn m

Nhóm phát triển cho rằng chuẩn hóa luôn có nghĩa chuẩn hóa về mét.

**Phân tích:** giá trị chuẩn hóa của `Distance` dựa trên multiplier, không phải cam kết đơn vị mét. Cần đổi sang metric công khai và lấy trị số trong metric đó.

### Tình huống 4: Metric mét mới tạo hoạt động trong phép in nhưng query lỗi

Adapter backend không xử lý metric mới như dự kiến.

**Phân tích:** khả năng quy đổi của Commons và khả năng tích hợp module là hai điều kiện khác nhau. Có thể chuẩn hóa sang metric tiêu chuẩn trước khi gọi adapter, hoặc bổ sung hỗ trợ có chủ đích.

### Tình huống 5: Hai tọa độ chênh nhau 0,01 nên gọi đó là 0,01 km

Dữ liệu thực tế là kinh độ/vĩ độ.

**Phân tích:** độ tọa độ không thể đổi thành km chỉ bằng cách gắn nhãn. Cần phép đo phù hợp với hệ tọa độ và mô hình địa lý được chọn.

### Tình huống 6: Kết quả cách 480 m được trả distance=500 vì request tìm trong 500 m

Response dùng lại bán kính đầu vào.

**Phân tích:** bán kính là giới hạn truy vấn, còn distance của kết quả là khoảng cách đến đối tượng đó. Phải giữ riêng nguồn và ý nghĩa của hai đại lượng.

Dùng `Distance` hiệu quả bắt đầu từ việc giữ trị số và metric đi cùng nhau. Hãy thống nhất đơn vị ở biên, phân biệt trị số hiện tại với giá trị chuẩn hóa, và để adapter của module xử lý đúng quy ước geo trước khi công khai kết quả với đơn vị rõ ràng.
