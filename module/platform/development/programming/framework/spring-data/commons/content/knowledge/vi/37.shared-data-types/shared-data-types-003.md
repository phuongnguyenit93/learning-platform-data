# Point, Box, Circle và Polygon trong mô hình không gian

## 1. Các kiểu dùng chung mô tả hình dạng, không thay thế hệ thống GIS

Trong chương **Kiểu dữ liệu dùng chung** của module **SPRING_DATA_COMMONS**, package org.springframework.data.geo cung cấp các giá trị như Point, Box, Circle và Polygon để diễn đạt dữ liệu hoặc vùng truy vấn không gian.

Chúng giúp chữ ký Java thể hiện rõ ý định hơn một mảng double không có ngữ nghĩa. Tuy nhiên, việc tạo được một object không chứng minh:

- Tọa độ đang thuộc hệ quy chiếu đúng.
- Đơn vị khoảng cách đã được hiểu đúng.
- Hình học hợp lệ theo yêu cầu nghiệp vụ.
- Store có thể lưu hoặc truy vấn trực tiếp kiểu đó.
- Một derived query có cùng ý nghĩa trên mọi module.

Luồng cần phân biệt:

~~~mermaid
flowchart LR
    A["Tọa độ và yêu cầu nghiệp vụ"] --> B["Kiểm tra hệ tọa độ, đơn vị, hình học"]
    B --> C["Point / Box / Circle / Polygon"]
    C --> D["Mapping và query của module dữ liệu"]
    D --> E["Toán tử, index và dữ liệu của backend"]
~~~

Bài viết minh họa API Spring Data Commons 3.5.1. Các ví dụ trên mặt phẳng được tách khỏi ví dụ longitude/latitude để tránh trộn ngữ nghĩa.

## 2. Chọn kiểu theo câu hỏi cần biểu diễn

| Kiểu | Thành phần chính | Ví dụ ý định |
| --- | --- | --- |
| Point | Hai tọa độ x, y | Một vị trí cửa hàng hoặc một điểm trên sơ đồ kho |
| Box | Hai điểm xác định góc đối diện | Khung nhìn hình chữ nhật theo trục tọa độ |
| Circle | Tâm và bán kính dạng Distance | Vùng quanh một vị trí |
| Polygon | Danh sách điểm có thứ tự | Một vùng ranh giới không nhất thiết là hình chữ nhật |

Box, Circle và Polygon triển khai Shape. Point là giá trị tọa độ và không phải cùng một kiểu Shape trong API này.

Đừng suy rằng Shape cung cấp sẵn mọi phép toán hình học. Những class trong bài chủ yếu mang dữ liệu; các phép kiểm tra chứa điểm, giao nhau, tính diện tích hoặc biến đổi hệ tọa độ cần một cơ chế khác phù hợp.

## 3. Chốt hệ tọa độ trước khi tạo Point

### 3.1. x, y chưa nói lên đơn vị

~~~java
import org.springframework.data.geo.Point;

Point position = new Point(106.7, 10.8);

double x = position.getX();
double y = position.getY();
~~~

Point chỉ giữ x và y; nó không có thuộc tính CRS/SRID hoặc đơn vị để tự xác định hai số trên là longitude/latitude, mét hay ô trên sơ đồ.

Trong quy ước địa lý được ứng dụng chọn, có thể đặt x là longitude và y là latitude. Khi dữ liệu đi qua GeoJSON theo RFC 7946, thứ tự hai tọa độ là longitude rồi latitude, với WGS 84 và đơn vị độ thập phân. [API Point](https://docs.spring.io/spring-data/commons/docs/3.5.1/api/org/springframework/data/geo/Point.html), [RFC 7946](https://www.rfc-editor.org/rfc/rfc7946.html)

Không áp dụng quy ước này cho mọi Point. Một sơ đồ kho nội bộ có thể dùng x và y tính bằng mét từ một gốc cục bộ.

| Ngữ cảnh | x | y | Cách hiểu khoảng cách |
| --- | --- | --- | --- |
| Sơ đồ cục bộ đã quy ước mét | Tọa độ ngang | Tọa độ dọc | Theo hình học mặt phẳng trong hệ đó |
| Địa lý longitude/latitude | Kinh độ | Vĩ độ | Cần mô hình khoảng cách địa lý phù hợp |
| Tọa độ từ một nguồn chưa rõ | Chưa xác định | Chưa xác định | Chưa đủ thông tin để truy vấn đáng tin cậy |

### 3.2. Không đổi hệ tọa độ bằng cách đổi nhãn

Nếu một nguồn trả tọa độ theo mét còn nguồn khác trả độ, cùng tạo new Point(x, y) không làm chúng trở nên tương thích.

Ứng dụng cần xác định:

- Nguồn và hệ tọa độ của dữ liệu.
- Thứ tự trục.
- Đơn vị.
- Việc biến đổi có cần thiết không và được thực hiện ở đâu.
- Hệ tọa độ mà backend/query mong đợi.

Nếu ứng dụng chứa nhiều không gian tọa độ, có thể dùng DTO hoặc wrapper có tên thể hiện ngữ nghĩa, thay vì để mọi method nhận hai double không phân biệt.

Point của Commons chỉ có hai chiều. Không giấu altitude vào một trong hai giá trị rồi tiếp tục gọi đó là longitude/latitude.

## 4. Point: vị trí và cách so sánh

Có thể tạo bản sao từ một Point khác:

~~~java
Point original = new Point(2.0, 3.0);
Point copy = new Point(original);
~~~

Tuy nhiên, copy không biến đổi hệ tọa độ, không làm tròn và không tính lại vị trí.

Trong bản 3.5.1, constructor nhận hai double gán trực tiếp giá trị. Nó không tự kiểm tra miền longitude/latitude hoặc bắt buộc số hữu hạn. Việc kiểm tra tại biên ứng dụng là cần thiết khi hợp đồng yêu cầu. [Mã nguồn Point 3.5.1](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/geo/Point.java)

### 4.1. Equality không phải phép đo “đủ gần”

Point.equals trong phiên bản minh họa so biểu diễn double của các tọa độ, không dùng sai số khoảng cách theo nghiệp vụ.

Vì vậy:

- Dùng equals khi cần so đúng giá trị theo hợp đồng của type.
- Dùng assertion có sai số thích hợp khi kiểm tra kết quả tính toán số thực.
- Không dùng một epsilon tùy ý trên longitude/latitude để thay thế một khoảng cách tính bằng mét.
- Không coi hai điểm cùng ô làm tròn là cùng vị trí nếu nghiệp vụ cần độ chính xác cao hơn.

Ngưỡng sai số cần gắn với dữ liệu và phép toán. Nó không được chọn chỉ để làm test qua.

## 5. Box: khung hình chữ nhật theo hai trục

Ví dụ trên mặt phẳng cục bộ:

~~~java
import org.springframework.data.geo.Box;
import org.springframework.data.geo.Point;

Box viewport = new Box(
        new Point(0.0, 0.0),
        new Point(6.0, 4.0));

Point first = viewport.getFirst();
Point second = viewport.getSecond();
~~~

Một cách đọc theo chính sách min/max của ứng dụng:

~~~text
y
^
4   +------------------+
    |                  |
    |                  |
0   +------------------+
    0                  6  → x
~~~

Box phù hợp cho khung nhìn hoặc vùng chữ nhật song song với các trục trong không gian đang xét. Nó không trực tiếp mô tả một hình chữ nhật xoay tự do.

Có constructor nhận hai mảng double, mỗi mảng chứa hai phần tử. Cách dùng Point thường dễ đọc hơn vì tránh nhầm vị trí phần tử.

### 5.1. Constructor không tự chuẩn hóa hai góc

Trong Box 3.5.1, constructor nhận Point kiểm tra null rồi giữ nguyên first và second. Nó không tự đổi chúng thành cặp min/max. [Mã nguồn Box 3.5.1](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/geo/Box.java)

Ví dụ:

~~~java
Box direct = new Box(
        new Point(0.0, 0.0),
        new Point(6.0, 4.0));

Box reversed = new Box(
        new Point(6.0, 4.0),
        new Point(0.0, 0.0));
~~~

Không dựa vào giả định rằng hai object sẽ bằng nhau hoặc được mọi adapter diễn giải giống nhau.

Nếu hợp đồng chỉ dùng mặt phẳng thông thường, ứng dụng có thể chuẩn hóa:

~~~text
minX = min(x1, x2)
minY = min(y1, y2)
maxX = max(x1, x2)
maxY = max(y1, y2)
~~~

Việc cho phép Box có chiều rộng hoặc chiều cao bằng 0 là một quyết định khác. Một API vùng tìm kiếm có thể từ chối trường hợp đó dù type vẫn tạo được.

### 5.2. Không chuẩn hóa mù quáng vùng qua đường đổi ngày

Với longitude, một vùng nhỏ đi qua kinh tuyến đổi ngày không nhất thiết có thể biểu diễn bằng cách lấy min/max số học như một khung không cắt.

Nếu hợp đồng có trường hợp này, cần quy tắc tách vùng hoặc biểu diễn địa lý mà backend hỗ trợ. Đổi chỗ west/east để làm số nhỏ đứng trước có thể vô tình biến một vùng nhỏ thành một vùng rất lớn.

Helper chuẩn hóa mặt phẳng ở phần sau không giải quyết trường hợp địa lý đó.

## 6. Circle: tâm, bán kính và metric

### 6.1. Circle trên mặt phẳng cục bộ

~~~java
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Point;

Circle localArea = new Circle(new Point(3.0, 2.0), 2.0);
~~~

Trong ví dụ này, ứng dụng quy ước tọa độ và bán kính dùng cùng đơn vị của mặt phẳng cục bộ.

Constructor nhận bán kính double dùng Distance có metric trung tính. Số 2.0 không tự mang nghĩa 2 km hoặc 2 m.

### 6.2. Circle có bán kính ghi rõ metric

~~~java
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

Point center = new Point(106.7, 10.8);

Circle requestedArea = new Circle(
        center,
        new Distance(5.0, Metrics.KILOMETERS));
~~~

Object diễn đạt một tâm và bán kính mang metric kilometer. Nó chưa tự chạy truy vấn, chưa tính quãng đường giữa hai vị trí và chưa bảo đảm adapter sẽ dùng phép toán cầu đúng yêu cầu.

Circle.getRadius trả Distance. Khi đọc giá trị, phải giữ cả metric:

~~~java
Distance radius = requestedArea.getRadius();

double value = radius.getValue();
String unit = radius.getUnit();
~~~

Không chỉ lấy getValue rồi truyền sang một API khác đang mong đơn vị khác. [API Circle](https://docs.spring.io/spring-data/commons/docs/3.5.1/api/org/springframework/data/geo/Circle.html), [API Distance](https://docs.spring.io/spring-data/commons/docs/3.5.1/api/org/springframework/data/geo/Distance.html)

### 6.3. Không mặc định có Metrics.METERS

Trong Metrics của bản 3.5.1 có KILOMETERS, MILES và NEUTRAL. Nếu input của API là mét, một cách chuyển đổi có chủ đích sang kilometer là:

~~~java
double radiusMeters = 1500.0;

Distance radius = new Distance(
        radiusMeters / 1000.0,
        Metrics.KILOMETERS);
~~~

Đây là đổi đơn vị của bán kính, không phải biến đổi tọa độ tâm. [Metrics 3.5.1](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/geo/Metrics.java)

### 6.4. Giới hạn của kiểm tra constructor

Circle kiểm tra tâm, radius không null và giá trị bán kính không âm. Bán kính 0 được type cho phép, nhưng API nghiệp vụ có thể chọn yêu cầu lớn hơn 0.

Ứng dụng vẫn cần kiểm tra giá trị hữu hạn và giới hạn tối đa khi phù hợp. Không coi “constructor không ném lỗi” là toàn bộ validation của vùng truy vấn. [Mã nguồn Circle 3.5.1](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/geo/Circle.java)

Không lấy công thức khoảng cách Euclid trên hai giá trị longitude/latitude rồi gọi kết quả là kilometer. Cần giữ đúng mô hình không gian từ dữ liệu đến toán tử của backend.

## 7. Polygon: các đỉnh phải có thứ tự

Ví dụ một vùng hình thang trong hệ tọa độ cục bộ:

~~~java
import java.util.List;

import org.springframework.data.geo.Point;
import org.springframework.data.geo.Polygon;

Point a = new Point(0.0, 0.0);
Point b = new Point(6.0, 0.0);
Point c = new Point(5.0, 4.0);
Point d = new Point(1.0, 4.0);

Polygon serviceArea = new Polygon(List.of(a, b, c, d));
~~~

Thứ tự A → B → C → D mô tả đường đi theo biên. Một tập cùng các điểm nhưng nối theo thứ tự khác có thể tạo hình khác hoặc tự cắt.

Có thể dùng constructor nhận ba Point đầu tiên cùng varargs các điểm tiếp theo:

~~~java
Polygon sameSequence = new Polygon(a, b, c, d);
~~~

getPoints và iterator cho phép đọc chuỗi điểm. Không dùng Collections.sort lên các đỉnh để “chuẩn hóa” polygon: sắp theo x hoặc y có thể thay đổi các cạnh.

### 7.1. Tạo object chưa đồng nghĩa polygon hợp lệ

Constructor Polygon(List) của bản 3.5.1 kiểm tra danh sách và từng phần tử không null rồi giữ một bản danh sách chỉ đọc. Nó không tự kiểm tra đủ ba đỉnh, diện tích, tự giao hoặc toàn bộ quy tắc topology.

Constructor varargs buộc caller cung cấp ba điểm đầu tiên theo chữ ký, nhưng điều đó cũng chưa chứng minh ba điểm phân biệt hoặc không thẳng hàng. [Mã nguồn Polygon 3.5.1](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.1/src/main/java/org/springframework/data/geo/Polygon.java)

Một chính sách vùng nghiệp vụ thường phải xét:

- Đủ số đỉnh phân biệt.
- Mọi tọa độ hợp lệ trong hệ đang dùng.
- Không có cạnh hoặc diện tích suy biến ngoài hợp đồng.
- Không tự cắt nếu chỉ hỗ trợ polygon đơn.
- Quy tắc đóng vòng và hướng vòng theo định dạng/backend.
- Giới hạn số đỉnh và độ phức tạp.

Không nên tự viết vài phép so sánh rồi gọi đó là validator hình học đầy đủ cho mọi hệ tọa độ. Với topology phức tạp, dùng cơ chế hình học phù hợp và kiểm thử theo backend thực tế.

### 7.2. Đóng vòng không phải một hành vi tự động chung

Trong ví dụ List.of(a, b, c, d), danh sách của Commons Polygon có bốn điểm đã truyền; nó không tự thêm a vào cuối.

Điều kiện của representation đích có thể yêu cầu khác. Adapter phải chuyển rõ ràng, không dựa vào việc mọi kiểu Polygon đều dùng cùng quy tắc.

Equality của Polygon trong phiên bản minh họa dựa trên danh sách điểm. Hai chuỗi quay vòng điểm bắt đầu hoặc đảo chiều có thể mô tả cùng miền hình học nhưng không được coi là cùng giá trị Java theo cách so đó.

Nếu cần cache key hoặc so tương đương hình học, phải có chính sách chuẩn hóa riêng thích hợp.

## 8. Phân biệt hình dạng, phép toán và điều kiện biên

Một vùng có thể được dùng cho các câu hỏi khác nhau:

| Ý định | Câu hỏi |
| --- | --- |
| Chứa một điểm | Điểm có thuộc vùng không? |
| Nằm hoàn toàn trong vùng | Toàn bộ hình cần xét có nằm trong vùng không? |
| Giao nhau | Hai hình có phần giao không? |
| Gần một điểm | Khoảng cách có trong ngưỡng và có cần xếp theo độ gần không? |

Không đổi các ý định trên chỉ bằng cách thay kiểu tham số. Within, intersects và near là những semantics truy vấn khác nhau, còn lớp Commons chủ yếu mô tả giá trị đầu vào.

Với polygon hình thang ở phần trước, Box bao của nó có thể là từ (0, 0) tới (6, 4). Điểm (0.5, 3.8) nằm trong Box đó nhưng ở ngoài phần hình thang theo mô hình mặt phẳng đã chọn.

Vì vậy, dùng bounding box để lọc sơ bộ không đồng nghĩa đã thực hiện kiểm tra polygon chính xác. Nếu backend hoặc thiết kế query dùng hai bước, phải giữ bước kiểm tra hình học cuối cùng khi nghiệp vụ yêu cầu.

### 8.1. Điểm trên biên cần một hợp đồng riêng

Các ca biên nên được chỉ rõ:

- Điểm đúng trên cạnh Box.
- Điểm trùng một đỉnh Polygon.
- Điểm nằm trên một cạnh Polygon.
- Điểm cách tâm đúng bằng bán kính Circle.
- Hai vùng chỉ chạm nhau tại một điểm hoặc một cạnh.

Không suy rằng mọi toán tử cùng tên ở các backend đều có cùng quy tắc bao gồm biên. Kết luận phải gắn với kiểu dữ liệu được lưu, toán tử và mô hình hình học thực tế.

Nếu ranh giới nghiệp vụ có dung sai, dung sai cần được xác định theo đơn vị và mục đích của dữ liệu, không phải một số epsilon đặt tùy ý trong mọi phép so sánh.

## 9. Helper kiểm tra đầu vào theo một chính sách cụ thể

Ví dụ sau chọn ba chính sách:

1. Điểm địa lý nhận longitude/latitude theo miền giá trị đã quy định.
2. Box cục bộ được chuẩn hóa min/max và phải có diện tích dương.
3. Vùng tìm kiếm địa lý có bán kính lớn hơn 0 và không quá 50 km.

Mốc 50 km là quyết định của API minh họa, không phải giới hạn của Circle.

~~~java
package com.example.geo;

import java.util.Objects;

import org.springframework.data.geo.Box;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Distance;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

public final class GeoInputs {

    private GeoInputs() {
    }

    public static Point wgs84(
            double longitude, double latitude) {

        requireFinite(longitude, latitude);

        if (longitude < -180 || longitude > 180) {
            throw new IllegalArgumentException(
                    "Longitude ngoài miền cho phép");
        }

        if (latitude < -90 || latitude > 90) {
            throw new IllegalArgumentException(
                    "Latitude ngoài miền cho phép");
        }

        return new Point(longitude, latitude);
    }

    public static Box localBox(Point first, Point second) {
        Objects.requireNonNull(first, "first");
        Objects.requireNonNull(second, "second");

        requireFinite(
                first.getX(), first.getY(),
                second.getX(), second.getY());

        double minX = Math.min(first.getX(), second.getX());
        double minY = Math.min(first.getY(), second.getY());
        double maxX = Math.max(first.getX(), second.getX());
        double maxY = Math.max(first.getY(), second.getY());

        if (minX == maxX || minY == maxY) {
            throw new IllegalArgumentException(
                    "Box phải có chiều rộng và chiều cao dương");
        }

        return new Box(
                new Point(minX, minY),
                new Point(maxX, maxY));
    }

    public static Circle geographicCircle(
            double longitude, double latitude, double radiusKm) {

        requireFinite(radiusKm);

        if (radiusKm <= 0 || radiusKm > 50) {
            throw new IllegalArgumentException(
                    "Bán kính phải trong khoảng (0, 50] km");
        }

        return new Circle(
                wgs84(longitude, latitude),
                new Distance(radiusKm, Metrics.KILOMETERS));
    }

    private static void requireFinite(double... values) {
        for (double value : values) {
            if (!Double.isFinite(value)) {
                throw new IllegalArgumentException(
                        "Tọa độ và bán kính phải là số hữu hạn");
            }
        }
    }
}
~~~

Helper wgs84 kiểm tra input theo hợp đồng, không chuyển một hệ tọa độ khác sang WGS 84. Caller vẫn phải biết nguồn dữ liệu thực sự dùng hệ nào.

localBox không nên được dùng để xử lý vùng longitude cắt qua đường đổi ngày. Vì Point không mang context, helper không thể tự phát hiện một Point cục bộ đã bị thay bằng một Point địa lý. Ở ứng dụng có nhiều không gian tọa độ, nên bổ sung type hoặc context đủ mạnh để hạn chế dùng nhầm.

Code trên không có validator topology cho Polygon. Phần đó cần được thiết kế theo loại vùng mà ứng dụng cho phép, thay vì tạo cảm giác rằng một kiểm tra số đỉnh là đã đủ.

## 10. Commons types và GeoJSON là hai lớp khác nhau

Một GeoJSON Point có thể có hình thức:

~~~json
{
  "type": "Point",
  "coordinates": [106.7, 10.8]
}
~~~

Đây không phải lời hứa rằng serialize một Commons Point bằng mọi mapper sẽ tự tạo JSON như trên.

GeoJSON Polygon chứa các vòng; một vòng cần ít nhất bốn vị trí và vị trí cuối trùng vị trí đầu. Circle và Box không phải geometry type độc lập của GeoJSON. Một Box của Commons cũng không đồng nhất với field bbox của GeoJSON. [Quy tắc geometry của GeoJSON](https://www.rfc-editor.org/rfc/rfc7946.html)

Ứng dụng cần phân biệt:

| Giá trị trong Java | Representation đích có thể cần |
| --- | --- |
| Commons Point | Một cặp x/y theo mapping, hoặc GeoJSON Point khi adapter hỗ trợ |
| Commons Box | Vùng truy vấn chữ nhật, không mặc nhiên là một GeoJSON geometry |
| Commons Circle | Truy vấn tâm/bán kính hoặc một biểu diễn vùng được thiết kế riêng |
| Commons Polygon | Danh sách đỉnh; adapter có thể cần đóng vòng và biểu diễn theo định dạng đích |

Polygon của Commons trong bài chỉ cung cấp một danh sách điểm, không cung cấp mô hình đầy đủ cho nhiều vòng, lỗ hoặc nhiều polygon rời nhau.

Nếu xấp xỉ Circle bằng một Polygon để chuyển qua một định dạng, số đỉnh và sai số xấp xỉ trở thành một phần của thiết kế. Không gọi đó là phép chuyển đổi giữ nguyên hình học tuyệt đối.

Các kiểu chuyên biệt của module, chẳng hạn GeoJsonPoint hoặc GeoJsonPolygon trong Spring Data MongoDB, có hợp đồng khác với các kiểu dùng chung. Kiểm tra đúng type, package và representation được backend nhận.

## 11. Ví dụ sử dụng trong một module có hỗ trợ: MongoDB

Spring Data MongoDB có hỗ trợ các query không gian với Near và Within. Tài liệu của module minh họa Within với Box, Circle và Polygon. Đây là khả năng của module MongoDB, không phải lời bảo đảm từ CrudRepository cho mọi store. [Query methods của Spring Data MongoDB](https://docs.spring.io/spring-data/mongodb/reference/mongodb/repositories/query-methods.html)

Giả sử Store là document đã được mapping, có property location theo representation phù hợp:

~~~java
import java.util.List;

import org.springframework.data.geo.Box;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Polygon;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface StoreRepository
        extends MongoRepository<Store, String> {

    List<Store> findByLocationWithin(Box area);

    List<Store> findByLocationWithin(Circle area);

    List<Store> findByLocationWithin(Polygon area);
}
~~~

Đoạn code mô tả các chữ ký theo tính năng của module. Để thực thi đúng, cần xác nhận:

- Property location thực sự được lưu theo kiểu nào.
- Query sử dụng mô hình phẳng hay địa lý phù hợp.
- Radius/metric được chuyển sang đơn vị toán tử mong đợi.
- Index không gian cần thiết đã được tạo đúng.
- Fixture thuộc cùng quy ước tọa độ với vùng truy vấn.

Đặc biệt, một Circle mang Distance kilometer không tự chứng minh mọi đường Within sẽ có cùng semantics với truy vấn khoảng cách địa lý mà bạn cần. Phải kiểm tra query được module sinh và kết quả trên backend.

Trong MongoDB, dữ liệu tọa độ legacy, GeoJSON và các toán tử không gian có những khác biệt về representation, khoảng cách và index. Không chỉ đổi Java type rồi mặc định dữ liệu đã lưu tương thích.

### 11.1. Khi dùng store khác

| Nền tảng | Điều cần xác minh trước khi dùng |
| --- | --- |
| Spring Data MongoDB | Representation, toán tử Within/Near, metric và index phù hợp |
| JPA/SQL có tính năng không gian | Kiểu geometry của provider/database và đường query được hỗ trợ |
| JDBC/R2DBC | Mapping cột, converter hoặc query tùy biến cho backend |
| Một store có tập lệnh GEO riêng | Những hình dạng và phép toán mà module thực sự cung cấp |
| Bộ nhớ ứng dụng | Thuật toán/engine hình học và đơn vị được dùng |

Không khai báo findByLocationWithin trên một repository bất kỳ rồi coi việc có method đó trong source là bằng chứng backend hỗ trợ.

Nếu module không có abstraction trực tiếp cho kiểu truy vấn cần thiết, có thể cần repository fragment hoặc adapter query riêng. Phải giữ rõ phần nào dùng chung và phần nào phụ thuộc store.

## 12. Kiểm thử chính sách tọa độ và đơn vị của ứng dụng

Ví dụ JUnit 5 cho GeoInputs:

~~~java
package com.example.geo;

import org.junit.jupiter.api.Test;
import org.springframework.data.geo.Box;
import org.springframework.data.geo.Circle;
import org.springframework.data.geo.Metrics;
import org.springframework.data.geo.Point;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GeoInputsTest {

    @Test
    void keepsLongitudeInXAndLatitudeInY() {
        // Cả hai số đều nằm trong miền latitude;
        // chỉ kiểm tra range không phát hiện được việc đổi chỗ.
        Point point = GeoInputs.wgs84(20.1, 40.2);

        assertEquals(20.1, point.getX(), 1e-12);
        assertEquals(40.2, point.getY(), 1e-12);
    }

    @Test
    void normalizesLocalBoxCorners() {
        Box box = GeoInputs.localBox(
                new Point(6, 4),
                new Point(0, 0));

        assertEquals(new Point(0, 0), box.getFirst());
        assertEquals(new Point(6, 4), box.getSecond());
    }

    @Test
    void keepsKilometerMetricOnCoverage() {
        Circle circle = GeoInputs.geographicCircle(
                106.7, 10.8, 5.0);

        assertEquals(5.0,
                circle.getRadius().getValue(), 1e-12);
        assertEquals(Metrics.KILOMETERS,
                circle.getRadius().getMetric());
    }

    @Test
    void rejectsInvalidOrNonFiniteInput() {
        assertThrows(IllegalArgumentException.class,
                () -> GeoInputs.wgs84(106.7, 100.0));

        assertThrows(IllegalArgumentException.class,
                () -> GeoInputs.wgs84(Double.NaN, 10.8));

        assertThrows(IllegalArgumentException.class,
                () -> GeoInputs.geographicCircle(
                        106.7, 10.8, Double.POSITIVE_INFINITY));

        assertThrows(IllegalArgumentException.class,
                () -> GeoInputs.geographicCircle(
                        106.7, 10.8, 50.1));

        assertThrows(IllegalArgumentException.class,
                () -> GeoInputs.localBox(
                        new Point(0, 0), new Point(0, 4)));
    }
}
~~~

Các test trên bảo vệ lựa chọn của ứng dụng về trục, min/max và giới hạn bán kính. Chúng không chứng minh một Circle đã được backend truy vấn đúng về mặt địa lý.

Các đoạn code trong bài là tài liệu minh họa thiết kế và kiểm thử, không xác nhận đã chạy thành công trong một môi trường cụ thể.

### 12.1. Test tích hợp phải có các điểm phân biệt kết quả

Một bộ fixture hữu ích:

| Fixture | Mục tiêu |
| --- | --- |
| Điểm chắc chắn ở trong vùng | Chứng minh đường query tìm được dữ liệu đúng |
| Điểm chắc chắn ở ngoài vùng | Phát hiện sai radius hoặc vùng quá rộng |
| Điểm trong Box bao nhưng ngoài Polygon | Phát hiện việc chỉ dùng bounding box |
| Điểm trên cạnh và tại đỉnh | Xác nhận quy tắc biên |
| Tọa độ cùng hợp lệ khi đảo trục | Phát hiện mapping longitude/latitude bị đổi |
| Hai bán kính khác nhau rõ rệt | Phát hiện sai đơn vị |
| Vùng suy biến hoặc tự giao | Xác nhận chính sách từ chối/chuẩn hóa |
| Vùng gần đường đổi ngày khi API hỗ trợ | Xác nhận semantics địa lý đặc biệt |
| Dữ liệu của tenant khác | Kiểm tra query không gian vẫn giữ phạm vi quyền |

Nên xác nhận cả representation đã lưu, query thực tế và tập ID kết quả. Một mock repository trả sẵn danh sách không kiểm tra được converter hoặc toán tử không gian.

Với các ca đo khoảng cách, chọn dữ liệu và ngưỡng có ý nghĩa theo mô hình backend. Không đặt mọi fixture sát ranh giới rồi dùng sai số lớn để làm kết quả qua.

## 13. Lưu trữ và trao đổi dữ liệu cần giữ đủ ngữ nghĩa

Một dữ liệu không gian có thể cần thông tin ngoài chính object Commons:

| Nội dung | Ví dụ |
| --- | --- |
| Không gian tọa độ | Mặt phẳng kho nội bộ hay longitude/latitude |
| Thứ tự trục | x/y hoặc longitude/latitude theo hợp đồng |
| Đơn vị | Mét cục bộ, degree hoặc kilometer cho bán kính |
| Representation | Cặp tọa độ, GeoJSON hoặc kiểu geometry của database |
| Precision và dung sai | Theo nhu cầu của vị trí hoặc phép đo |
| Nguồn/thời điểm | Vị trí được ghi nhận từ đâu và lúc nào nếu nghiệp vụ cần |

Hai tọa độ bằng nhau nhưng đến từ hai không gian khác nhau không tự là cùng một vị trí.

Đối với API tìm theo tâm và bán kính, DTO có thể chọn hình thức tường minh:

~~~json
{
  "center": {
    "longitude": 106.7,
    "latitude": 10.8
  },
  "radius": {
    "value": 5,
    "unit": "km"
  }
}
~~~

Đây là payload do ứng dụng thiết kế, không phải GeoJSON Circle.

Không dùng toString của Point, Circle hoặc Polygon làm định dạng lưu trữ hay hợp đồng HTTP lâu dài. Getter hoặc serializer mặc định cũng không thay thế việc quyết định hợp đồng dữ liệu.

Nếu dùng Spring Data Jackson modules, cần bật đúng tích hợp và kiểm thử mapper/converter đang thực sự dùng. Serialization đọc lại được object chưa đủ chứng minh store hiểu đúng hệ tọa độ hoặc toán tử.

## 14. Chi phí truy vấn, giới hạn kết quả và quyền truy cập

Các shape chỉ là dữ liệu đầu vào; một vùng hợp lệ về hình học vẫn có thể tạo truy vấn quá rộng.

Một API tìm kiếm nên xác định:

- Giới hạn bán kính hoặc phạm vi vùng theo nghiệp vụ.
- Giới hạn số đỉnh và độ phức tạp Polygon.
- Giới hạn kết quả, phân trang hoặc cách duyệt tiếp được module hỗ trợ.
- Có cần tổng số kết quả hay chỉ cần phần tiếp theo.
- Có cần sắp xếp theo khoảng cách hay một sort nghiệp vụ khác.
- Phạm vi tenant/quyền phải đi cùng predicate không gian.

Within không tự có nghĩa “trả gần nhất trước”. Nếu cần độ gần hoặc khoảng cách trong kết quả, phải chọn đường truy vấn và kiểu kết quả phù hợp với module.

Không đọc toàn bộ cửa hàng rồi lọc bằng Java chỉ vì đã có Point và Polygon, trừ khi phạm vi dữ liệu và chi phí của thiết kế đó đã được lựa chọn rõ ràng.

Query by Example không tự biến một Point trong probe thành phép tìm gần hoặc phép nằm trong vùng. Cần dùng đúng khả năng query của store thay vì suy từ tên type.

Một projection chỉ trả ID và tên có thể giảm dữ liệu được đưa ra API, nhưng không tự sửa một predicate không gian sai hoặc một query thiếu giới hạn quyền.

## 15. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể |
| --- | --- |
| Vị trí xuất hiện rất xa nơi dự định | Đảo longitude/latitude hoặc dùng sai hệ tọa độ |
| Radius nhỏ nhưng kết quả bao trùm vùng lớn | Nhầm unit hoặc metric không được adapter hiểu đúng |
| Box đảo góc tạo kết quả khác dự kiến | Dựa vào chuẩn hóa mà constructor không thực hiện |
| Polygon tạo được nhưng backend từ chối | Không đủ đỉnh hợp lệ, tự giao hoặc sai representation |
| Điểm nằm trong Box nhưng query Polygon không trả | Box bao rộng hơn miền Polygon |
| Hai Polygon cùng vùng nhưng equals trả false | Chuỗi đỉnh hoặc hướng/start point khác nhau |
| Circle nhận được nhưng không có query phù hợp | Module không hỗ trợ đường truy vấn đang khai báo |
| JSON có x/y nhưng backend chờ coordinates | Nhầm Java representation với định dạng đích |
| Kết quả Within không theo độ gần | Nhầm predicate vùng với truy vấn nearest |
| Chỉ sai ở dữ liệu thực tế | Test chưa đi qua mapping, index và engine của store |

Khi chẩn đoán, ghi nhận có kiểm soát hệ tọa độ, đơn vị, kiểu representation và toán tử đã dùng. Không chỉ nhìn giá trị double rồi kết luận lớp Commons đã “tính sai”.

## 16. Tự kiểm tra

1. Point giữ thông tin gì và thiếu những metadata nào để tự xác định hệ tọa độ?
2. Khi dùng longitude/latitude theo hợp đồng trong bài, x và y tương ứng với giá trị nào?
3. Vì sao Circle(point, 5) không tự có nghĩa là bán kính 5 km?
4. Box có tự đổi hai góc sang min/max không? Khi nào chuẩn hóa min/max là sai về ý nghĩa địa lý?
5. Constructor Polygon(List) có đủ để xác nhận một polygon nghiệp vụ hợp lệ không?
6. Vì sao không nên sort các đỉnh Polygon theo x để chuẩn hóa?
7. GeoJSON Polygon và Commons Polygon có thể khác nhau ở quy tắc đóng vòng như thế nào?
8. Vì sao test tạo được object chưa chứng minh backend truy vấn đúng?
9. Một query Within có tự trả kết quả theo khoảng cách không?
10. Cần giữ những điều kiện gì khi kết hợp vùng không gian với tenant và phân trang?

Point, Box, Circle và Polygon cung cấp một ngôn ngữ giá trị chung để diễn đạt vị trí và vùng. Chúng phát huy tác dụng khi hệ tọa độ, đơn vị, validation và semantics truy vấn được xác định xuyên suốt từ đầu vào đến mapping và backend của từng module.
