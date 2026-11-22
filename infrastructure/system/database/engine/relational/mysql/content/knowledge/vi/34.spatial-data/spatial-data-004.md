# Thứ tự trục, kinh độ/vĩ độ và xử lý SRID 4326

Khi lưu tọa độ địa lý trong MySQL, hai con số của một điểm có thể bị đảo vị trí dù cả hai đều là số hợp lệ. Nguyên nhân thường gặp là ứng dụng quen ghi kinh độ trước vĩ độ, trong khi hệ quy chiếu EPSG:4326 định nghĩa trục theo thứ tự vĩ độ rồi kinh độ. MySQL tôn trọng thứ tự trục được định nghĩa trong Spatial Reference System (SRS) khi đọc hoặc ghi WKT theo mặc định.

Để làm việc chính xác, cần phân biệt ba khái niệm:

- **SRID/CRS** cho biết tọa độ thuộc hệ quy chiếu nào, ví dụ SRID 4326 là WGS 84.
- **Thứ tự trục** cho biết mỗi thành phần trong một tọa độ đại diện cho trục nào, ví dụ latitude rồi longitude hoặc longitude rồi latitude.
- **Phép biến đổi tọa độ** thay đổi giá trị tọa độ để chuyển từ một hệ quy chiếu sang hệ khác.

Đặt SRID không tự hoán đổi kinh độ/vĩ độ và cũng không chuyển đổi tọa độ. Bài học này hướng dẫn cách đọc định nghĩa EPSG:4326, chỉ định thứ tự trục rõ ràng với WKT, kiểm tra tọa độ bằng các hàm địa lý và tránh nhầm lẫn khi trao đổi dữ liệu giữa MySQL với ứng dụng bản đồ.

## 1. SRID và Spatial Reference System

SRID là mã định danh của một Spatial Reference System. SRS mô tả cách diễn giải tọa độ: hệ tọa độ, trục, đơn vị đo, datum và các thông tin liên quan.

Một cặp số như (105.8, 21.0) chưa đủ để xác định một vị trí. Cần biết:

- Hai giá trị đó là kinh độ/vĩ độ hay một cặp tọa độ phẳng X/Y.
- Chúng được đo theo hệ quy chiếu nào.
- Đơn vị là độ, mét hay đơn vị khác.
- Thứ tự trục được áp dụng khi đọc và ghi dữ liệu.

### 1.1. SRID 0 và SRID 4326

MySQL dùng SRID 0 cho hệ tọa độ Cartesian mặc định, không gắn với một hệ quy chiếu địa lý cụ thể. Các giá trị thường được hiểu là tọa độ phẳng theo đơn vị do ứng dụng quy ước.

SRID 4326 tương ứng với hệ quy chiếu địa lý WGS 84, thường dùng cho dữ liệu GPS và bản đồ toàn cầu. Tọa độ là góc tính theo độ. Theo định nghĩa trục của EPSG:4326, thứ tự trục là:

1. Latitude (vĩ độ), hướng Bắc/Nam.
2. Longitude (kinh độ), hướng Đông/Tây.

Điểm quan trọng: nhiều API, thư viện bản đồ và định dạng trao đổi lại dùng thứ tự longitude trước latitude. Hai quy ước này cùng mô tả một vị trí nhưng thứ tự hai giá trị khác nhau.

### 1.2. SRID không phải thứ tự trục

SRID 4326 xác định hệ quy chiếu và định nghĩa trục của nó. Tùy chọn axis-order điều khiển cách một số hàm MySQL diễn giải hoặc xuất tọa độ WKT. Tùy chọn này không thay đổi SRID của geometry.

Ví dụ, hai biểu thức sau có thể mô tả cùng vị trí:

~~~sql
-- Thứ tự theo định nghĩa trục của EPSG:4326: latitude, longitude
ST_GeomFromText('POINT(21.0278 105.8342)', 4326)

-- Thứ tự thường gặp trong ứng dụng: longitude, latitude
ST_GeomFromText(
    'POINT(105.8342 21.0278)',
    4326,
    'axis-order=long-lat'
)
~~~

Trong ví dụ, cả hai cách đều biểu diễn một điểm gần Hà Nội. Cách thứ hai nói rõ rằng dữ liệu WKT đầu vào đang có longitude trước latitude.

## 2. Vì sao EPSG:4326 dễ gây nhầm lẫn?

Một tọa độ địa lý thường được viết theo một trong hai thứ tự:

| Quy ước | Thành phần thứ nhất | Thành phần thứ hai | Ví dụ điểm gần Hà Nội |
|---|---|---|---|
| EPSG:4326 theo thứ tự trục SRS | Latitude | Longitude | (21.0278, 105.8342) |
| Longitude/latitude phổ biến trong API và GeoJSON | Longitude | Latitude | (105.8342, 21.0278) |

Nếu một hệ thống gửi longitude trước latitude nhưng MySQL diễn giải theo thứ tự trục SRS, giá trị thứ nhất có thể bị hiểu thành vĩ độ. Với longitude lớn hơn 90 độ, giá trị đó nằm ngoài miền vĩ độ hợp lệ và có thể gây lỗi. Ở một số khu vực, cả hai số đều nằm trong miền hợp lệ của cả hai trục nên dữ liệu vẫn được chấp nhận nhưng vị trí bị sai.

### 2.1. Ví dụ đảo tọa độ

Giả sử ứng dụng gửi:

~~~text
longitude = 105.8342
latitude  = 21.0278
~~~

Đây là thứ tự longitude/latitude. Nếu truyền nguyên văn vào WKT với SRID 4326 mà không chỉ định thứ tự trục:

~~~sql
SELECT ST_GeomFromText('POINT(105.8342 21.0278)', 4326);
~~~

MySQL mặc định diễn giải theo thứ tự trục của SRS. Giá trị 105.8342 bị xem là latitude và vượt miền vĩ độ hợp lệ. Cách đúng khi đầu vào là longitude/latitude:

~~~sql
SELECT ST_GeomFromText(
    'POINT(105.8342 21.0278)',
    4326,
    'axis-order=long-lat'
);
~~~

### 2.2. Vì sao không thể chỉ nhìn hai con số?

Một điểm như (10.5, 20.5) có thể nằm trong miền giá trị hợp lệ nếu đọc theo cả hai thứ tự:

- Latitude 10.5, longitude 20.5.
- Longitude 10.5, latitude 20.5.

Hai cách hiểu tạo ra hai vị trí khác nhau nhưng đều có thể hợp lệ về mặt số học. Vì vậy, kiểm tra geometry hợp lệ không đủ để phát hiện mọi trường hợp đảo trục. Cần giữ hợp đồng dữ liệu rõ ràng và kiểm tra bằng một điểm tham chiếu đã biết.

## 3. Tùy chọn axis-order của MySQL

Các hàm đọc/ghi WKT của MySQL hỗ trợ tùy chọn axis-order để xác định thứ tự tọa độ. Các giá trị thường dùng:

| Giá trị | Ý nghĩa |
|---|---|
| srid-defined | Dùng thứ tự trục được định nghĩa trong SRS; đây là mặc định |
| long-lat | Diễn giải hoặc xuất longitude trước latitude |
| lat-long | Diễn giải hoặc xuất latitude trước longitude |

Với EPSG:4326, srid-defined tương ứng latitude/longitude.

### 3.1. Đọc WKT theo thứ tự longitude/latitude

~~~sql
SET @hanoi = ST_GeomFromText(
    'POINT(105.8342 21.0278)',
    4326,
    'axis-order=long-lat'
);
~~~

Tham số thứ ba của ST_GeomFromText() cho biết thứ tự của hai giá trị trong chuỗi WKT đầu vào.

### 3.2. Đọc WKT theo thứ tự trục được định nghĩa trong SRS

~~~sql
SET @hanoi_srs_order = ST_GeomFromText(
    'POINT(21.0278 105.8342)',
    4326,
    'axis-order=srid-defined'
);
~~~

Với EPSG:4326, chuỗi trên đặt latitude trước longitude. Có thể bỏ tham số thứ ba nếu muốn dùng mặc định srid-defined.

### 3.3. Đọc WKT theo thứ tự latitude/longitude một cách tường minh

~~~sql
SET @hanoi_lat_lon = ST_GeomFromText(
    'POINT(21.0278 105.8342)',
    4326,
    'axis-order=lat-long'
);
~~~

Ví dụ này tương đương với thứ tự trục được định nghĩa cho EPSG:4326. Viết rõ tùy chọn có ích khi mã nguồn cần thể hiện hợp đồng dữ liệu ngay tại điểm chuyển đổi.

### 3.4. Xuất WKT theo thứ tự mong muốn

ST_AsText() có thể nhận tùy chọn axis-order để định dạng kết quả:

~~~sql
SELECT
    ST_AsText(@hanoi) AS srs_defined_order,
    ST_AsText(@hanoi, 'axis-order=long-lat') AS longitude_first,
    ST_AsText(@hanoi, 'axis-order=lat-long') AS latitude_first;
~~~

Khi xuất theo srid-defined, EPSG:4326 được hiển thị latitude trước longitude. Khi xuất long-lat, longitude được hiển thị trước latitude. Điều này giúp tạo dữ liệu WKT theo hợp đồng mà hệ thống nhận yêu cầu.

### 3.5. Phải nhất quán giữa chiều đọc và chiều ghi

Nếu ứng dụng gửi longitude/latitude, hãy dùng long-lat khi đọc WKT. Nếu ứng dụng nhận WKT, hãy chỉ định rõ thứ tự khi xuất. Không nên dựa vào mặc định ngầm ở một đầu và giả định đầu kia dùng cùng quy ước.

## 4. Kiểm tra tọa độ bằng các hàm địa lý

Với một POINT có SRID địa lý, MySQL cung cấp các hàm truy xuất longitude và latitude. Dùng chúng để kiểm tra ý nghĩa của tọa độ thay vì đoán dựa vào ST_X() hoặc ST_Y().

~~~sql
SELECT
    ST_SRID(@hanoi) AS srid,
    ST_Longitude(@hanoi) AS longitude,
    ST_Latitude(@hanoi) AS latitude,
    ST_AsText(@hanoi, 'axis-order=long-lat') AS wkt_long_lat;
~~~

Kết quả kỳ vọng:

| Biểu thức | Giá trị gần đúng |
|---|---:|
| srid | 4326 |
| longitude | 105.8342 |
| latitude | 21.0278 |
| wkt_long_lat | POINT(105.8342 21.0278) |

### 4.1. Longitude và latitude có miền giá trị riêng

Với SRID 4326:

- Longitude nằm trong khoảng -180 đến 180 độ.
- Latitude nằm trong khoảng -90 đến 90 độ.

Giá trị âm biểu thị phía Tây đối với longitude hoặc phía Nam đối với latitude. Giá trị dương biểu thị phía Đông hoặc phía Bắc.

Kiểm tra miền giá trị giúp phát hiện một số lỗi đảo trục, nhưng không phát hiện được mọi trường hợp. Một cặp số nhỏ có thể nằm trong cả hai miền; khi đó phải xác minh bằng dữ liệu tham chiếu.

### 4.2. Dùng ST_Longitude() và ST_Latitude()

~~~sql
SELECT
    ST_Longitude(@hanoi),
    ST_Latitude(@hanoi);
~~~

Hai hàm này thể hiện trực tiếp ý nghĩa địa lý của tọa độ. Chúng yêu cầu đầu vào là POINT có SRS địa lý phù hợp. Không dùng chúng cho geometry Cartesian hoặc một geometry không phải POINT.

### 4.3. Cẩn thận với ST_X() và ST_Y()

ST_X() và ST_Y() trả về các thành phần tọa độ X và Y của điểm. Trong hệ quy chiếu địa lý có thứ tự trục khác với quy ước X/Y quen thuộc, không nên mặc định X luôn là longitude và Y luôn là latitude.

Khi mục tiêu là lấy kinh độ/vĩ độ của một điểm địa lý, ưu tiên ST_Longitude() và ST_Latitude(). Khi mục tiêu là làm việc với tọa độ phẳng, dùng X/Y theo định nghĩa của hệ Cartesian.

## 5. Gán SRID và biến đổi hệ tọa độ

Một trong những lỗi nghiêm trọng nhất khi xử lý dữ liệu không gian là xem việc gán SRID như một phép chuyển đổi tọa độ. Hai thao tác này có ý nghĩa hoàn toàn khác nhau.

### 5.1. ST_SRID() chỉ gán hoặc đọc mã SRS

ST_SRID(geometry) trả về SRID của geometry. Dạng có hai tham số ST_SRID(geometry, srid) gán một SRID mới cho geometry.

Việc gán SRID nói với MySQL rằng các giá trị hiện có phải được diễn giải theo hệ quy chiếu mới. Nó không tính lại hoặc đổi đơn vị các con số tọa độ.

Ví dụ, một geometry đang có SRID 0 nhưng dữ liệu thực chất đã được ghi theo thứ tự latitude/longitude của EPSG:4326 có thể được gắn nhãn SRID 4326:

~~~sql
SET @point_without_srs = ST_GeomFromText('POINT(21.0278 105.8342)');
SET @point_tagged = ST_SRID(@point_without_srs, 4326);

SELECT
    ST_SRID(@point_tagged) AS srid,
    ST_Longitude(@point_tagged) AS longitude,
    ST_Latitude(@point_tagged) AS latitude;
~~~

Ví dụ chỉ đúng khi các giá trị ban đầu thật sự là latitude 21.0278 và longitude 105.8342 theo EPSG:4326. Nếu dữ liệu nguồn dùng hệ tọa độ khác, chỉ gán SRID 4326 sẽ làm MySQL diễn giải sai vị trí.

### 5.2. ST_Transform() chuyển đổi tọa độ

ST_Transform(geometry, target_srid) chuyển đổi tọa độ từ SRS nguồn sang SRS đích khi MySQL có định nghĩa và phép biến đổi phù hợp. Khác với ST_SRID(), hàm này tính lại giá trị tọa độ.

Ví dụ chuyển điểm WGS 84 sang Web Mercator:

~~~sql
SET @hanoi_4326 = ST_GeomFromText(
    'POINT(105.8342 21.0278)',
    4326,
    'axis-order=long-lat'
);

SET @hanoi_3857 = ST_Transform(@hanoi_4326, 3857);

SELECT
    ST_SRID(@hanoi_4326) AS source_srid,
    ST_AsText(@hanoi_4326, 'axis-order=long-lat') AS source_wkt,
    ST_SRID(@hanoi_3857) AS target_srid,
    ST_AsText(@hanoi_3857) AS target_wkt;
~~~

EPSG:3857 là hệ tọa độ chiếu Web Mercator, thường biểu diễn vị trí bằng đơn vị mét trên mặt phẳng. Giá trị tọa độ sau chuyển đổi sẽ khác rõ rệt so với cặp kinh độ/vĩ độ theo độ.

### 5.3. Chọn đúng thao tác

| Tình huống | Thao tác |
|---|---|
| Geometry đã có tọa độ đúng theo EPSG:4326 nhưng SRID đang là 0 | Gán SRID 4326 sau khi xác minh nguồn |
| Geometry có SRID 4326 và cần xuất WKT theo longitude/latitude | ST_AsText() với axis-order=long-lat |
| Dữ liệu đầu vào là WKT longitude/latitude | ST_GeomFromText() với axis-order=long-lat |
| Geometry đang ở EPSG:3857 và cần tọa độ WGS 84 | ST_Transform(..., 4326) |
| Chỉ thay SRID để làm số liệu trông giống một CRS khác | Không làm như vậy; phải xác định CRS nguồn và phép biến đổi |

Không thể chuyển đổi một geometry không có thông tin về hệ tọa độ nguồn một cách đáng tin cậy. Trước khi gọi ST_Transform(), phải biết SRID hiện tại phản ánh đúng dữ liệu thực tế.

### 5.4. Đơn vị không tự thay đổi khi chỉ gán SRID

Tọa độ của EPSG:4326 là góc theo độ. Tọa độ của EPSG:3857 là tọa độ phẳng theo mét. Gán SRID 3857 cho một cặp số đang biểu diễn độ không biến chúng thành mét. Chỉ phép biến đổi tọa độ đúng mới tạo ra giá trị trong hệ đích.

## 6. Lưu điểm SRID 4326 trong bảng

Với MySQL 8.0.13 trở lên, có thể giới hạn SRID ngay trên cột geometry. Cột giới hạn SRID giúp đảm bảo các giá trị ghi vào đều thuộc cùng một SRS.

~~~sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL,
    name VARCHAR(200) NOT NULL,
    location POINT NOT NULL SRID 4326,
    PRIMARY KEY (place_id),
    SPATIAL INDEX spx_places_location (location)
) ENGINE = InnoDB;
~~~

Điều kiện NOT NULL và SRID restriction có ý nghĩa khi sử dụng spatial index trong InnoDB. Một cột geometry không giới hạn SRID có thể chứa dữ liệu thuộc nhiều hệ tọa độ khác nhau; khi đó phép so sánh không gian có thể không nhất quán và chỉ mục không gian không thể được sử dụng theo cách mong đợi.

### 6.1. Chèn tọa độ từ ứng dụng longitude/latitude

~~~sql
INSERT INTO places (place_id, name, location)
VALUES (
    1001,
    'Điểm tham chiếu Hà Nội',
    ST_GeomFromText(
        'POINT(105.8342 21.0278)',
        4326,
        'axis-order=long-lat'
    )
);
~~~

Đầu vào là longitude trước latitude nên câu lệnh chỉ định long-lat. Trong ứng dụng, hãy bind cả chuỗi WKT như một tham số prepared statement thay vì nối dữ liệu người dùng vào câu SQL.

### 6.2. Đọc tọa độ theo ý nghĩa địa lý

~~~sql
SELECT
    place_id,
    name,
    ST_SRID(location) AS srid,
    ST_Longitude(location) AS longitude,
    ST_Latitude(location) AS latitude,
    ST_AsText(location, 'axis-order=long-lat') AS wkt_long_lat
FROM places;
~~~

Kết quả cho thấy SRID, longitude, latitude và WKT được xuất theo đúng hợp đồng của ứng dụng. Không cần tự tách chuỗi WKT để lấy kinh độ/vĩ độ.

### 6.3. Cập nhật vị trí

~~~sql
UPDATE places
SET location = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
)
WHERE place_id = 1001;
~~~

Ví dụ thay vị trí bằng một điểm gần Thành phố Hồ Chí Minh. Giá trị đầu vào vẫn là longitude trước latitude. Điều kiện WHERE dùng khóa chính để cập nhật đúng bản ghi.

### 6.4. Kiểm tra SRID và loại geometry

~~~sql
SELECT
    place_id,
    ST_GeometryType(location) AS geometry_type,
    ST_SRID(location) AS srid,
    ST_IsValid(location) AS is_valid
FROM places;
~~~

Kết quả mong đợi là POINT, SRID 4326 và geometry hợp lệ. ST_IsValid() kiểm tra tính hợp lệ hình học; nó không chứng minh rằng dữ liệu đã được nhập đúng thứ tự trục hoặc đúng vị trí địa lý.

## 7. Xem định nghĩa SRS trong MySQL

MySQL lưu các Spatial Reference System được hỗ trợ trong data dictionary. Có thể tra cứu SRS bằng INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS:

~~~sql
SELECT
    SRS_ID,
    SRS_NAME,
    ORGANIZATION,
    ORGANIZATION_COORDSYS_ID,
    DEFINITION
FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
WHERE SRS_ID IN (0, 4326, 3857);
~~~

Các cột quan trọng:

- SRS_ID: mã SRID được MySQL dùng.
- SRS_NAME: tên hệ quy chiếu.
- ORGANIZATION: tổ chức định nghĩa, thường là EPSG với các SRID tương ứng.
- ORGANIZATION_COORDSYS_ID: mã hệ tọa độ trong tổ chức đó.
- DEFINITION: định nghĩa SRS, bao gồm thông tin trục và hệ tọa độ.

### 7.1. Xác minh SRID của dữ liệu đang lưu

~~~sql
SELECT
    ST_SRID(location) AS srid,
    COUNT(*) AS row_count
FROM places
GROUP BY ST_SRID(location);
~~~

Với cột đã giới hạn SRID 4326, kết quả chỉ nên có SRID đó. Với cột geometry không giới hạn SRID, truy vấn này giúp phát hiện dữ liệu bị trộn hệ quy chiếu.

### 7.2. Không suy luận thứ tự trục chỉ từ tên SRID

Tên EPSG:4326 thường khiến lập trình viên nghĩ ngay đến longitude/latitude. Hãy đọc định nghĩa SRS hoặc chỉ định axis-order tường minh tại biên tích hợp. Tên CRS không làm cho mọi định dạng trao đổi sử dụng cùng thứ tự tọa độ.

## 8. Tích hợp với GeoJSON và API bản đồ

WKT và GeoJSON có quy tắc biểu diễn tọa độ khác nhau. Theo quy ước GeoJSON phổ biến của RFC 7946, một position địa lý 2D có thứ tự longitude trước latitude:

~~~json
{
  "type": "Point",
  "coordinates": [105.8342, 21.0278]
}
~~~

Với EPSG:4326, thứ tự trục được định nghĩa trong SRS là latitude/longitude. Khi trao đổi dữ liệu, không được suy luận rằng GeoJSON sẽ dùng thứ tự giống WKT mặc định của MySQL.

### 8.1. Đọc GeoJSON

MySQL cung cấp ST_GeomFromGeoJSON() để chuyển GeoJSON thành geometry. Ví dụ:

~~~sql
SET @geojson = ST_GeomFromGeoJSON(
    '{"type":"Point","coordinates":[105.8342,21.0278]}',
    1,
    4326
);

SELECT
    ST_SRID(@geojson) AS srid,
    ST_Longitude(@geojson) AS longitude,
    ST_Latitude(@geojson) AS latitude,
    ST_AsGeoJSON(@geojson) AS geojson_output;
~~~

GeoJSON position được viết longitude trước latitude. Dùng đúng quy tắc của định dạng GeoJSON khi trao đổi; không lấy chuỗi coordinates rồi truyền thẳng vào WKT mà bỏ qua axis-order.

### 8.2. Xuất GeoJSON cho frontend

~~~sql
SELECT
    place_id,
    name,
    ST_AsGeoJSON(location) AS geometry_json
FROM places;
~~~

Frontend bản đồ thường nhận coordinates theo thứ tự longitude/latitude. Khi xuất GeoJSON, dùng hàm chuyên biệt ST_AsGeoJSON() thay vì tự tạo JSON từ ST_X(), ST_Y() hoặc chuỗi WKT.

### 8.3. Quy ước tại biên tích hợp

Một hợp đồng dữ liệu tốt cần xác định rõ:

- API nhận hai trường có tên longitude và latitude.
- Thứ tự của mảng GeoJSON là longitude, latitude.
- SRID được lưu trong database là 4326.
- WKT đầu vào dùng axis-order=long-lat nếu ứng dụng gửi longitude trước latitude.
- Khi trả WKT cho ứng dụng, chọn axis-order rõ ràng.
- Khi trả GeoJSON, dùng ST_AsGeoJSON().
- Không dùng số tọa độ không kèm SRID hoặc mô tả CRS trong các luồng trao đổi nội bộ.

Tên trường rõ ràng thường an toàn hơn một mảng hai phần tử không có mô tả. Nếu API bắt buộc dùng mảng, tài liệu API phải nêu thứ tự tọa độ.

## 9. Kiểm tra dữ liệu trước và sau khi ghi

Tọa độ sai có thể được lưu mà không làm câu lệnh SQL thất bại, đặc biệt khi hai giá trị đều nằm trong miền hợp lệ. Cần kết hợp kiểm tra cấu trúc, miền giá trị và đối chiếu vị trí.

### 9.1. Kiểm tra tại tầng ứng dụng

Trước khi ghi:

1. Xác nhận dữ liệu có cả longitude và latitude.
2. Chuyển chúng thành kiểu số, từ chối chuỗi rỗng hoặc giá trị không hữu hạn.
3. Kiểm tra longitude trong khoảng -180 đến 180.
4. Kiểm tra latitude trong khoảng -90 đến 90.
5. Xác định rõ nguồn tọa độ dùng WGS 84/EPSG:4326 hay một CRS khác.
6. Xây dựng WKT/geometry với thứ tự trục tường minh.

Kiểm tra miền giá trị không thay thế việc xác minh CRS. Một cặp số nằm trong hai khoảng hợp lệ vẫn có thể mô tả vị trí sai nếu hai trục bị đảo.

### 9.2. Kiểm tra tại database

Với cột location đã giới hạn SRID 4326:

~~~sql
SELECT
    place_id,
    ST_SRID(location) AS srid,
    ST_Longitude(location) AS longitude,
    ST_Latitude(location) AS latitude,
    ST_IsValid(location) AS geometry_valid
FROM places
WHERE ST_SRID(location) <> 4326
   OR ST_Longitude(location) NOT BETWEEN -180 AND 180
   OR ST_Latitude(location) NOT BETWEEN -90 AND 90
   OR ST_IsValid(location) = 0;
~~~

Nếu cột được khai báo SRID 4326, điều kiện kiểm tra SRID chủ yếu hữu ích khi kiểm tra dữ liệu từ bảng hoặc luồng cũ. Nếu cột cho phép nhiều SRID, hãy phân nhóm và xử lý từng loại CRS trước khi so sánh hoặc biến đổi.

### 9.3. ST_IsValid() không phát hiện mọi lỗi nghiệp vụ

Một POINT có thể hợp lệ về hình học nhưng vẫn nằm sai quốc gia hoặc sai thành phố do đảo trục, sai SRID hoặc lỗi nguồn dữ liệu. Tính hợp lệ OGC không xác nhận ý nghĩa nghiệp vụ của vị trí.

Đối với dữ liệu quan trọng, hãy kiểm thử bằng các điểm kiểm soát đã biết:

- Một điểm có longitude/latitude đã được xác nhận.
- Một điểm gần biên miền longitude hoặc latitude nếu hệ thống cần xử lý.
- Một điểm có giá trị âm ở một hoặc cả hai trục.
- Một điểm từ mỗi nguồn tích hợp bên ngoài.

Đối chiếu kết quả ST_Longitude(), ST_Latitude() và hiển thị trên bản đồ thử nghiệm.

### 9.4. Phát hiện dữ liệu đảo trục trong bảng cũ

Không có một truy vấn tổng quát nào xác định chắc chắn mọi điểm bị đảo trục. Có thể lọc các trường hợp đáng ngờ dựa trên miền địa lý mà ứng dụng phục vụ.

Ví dụ, nếu dữ liệu chỉ thuộc Việt Nam, có thể kiểm tra sơ bộ vùng longitude và latitude mong đợi:

~~~sql
SELECT
    place_id,
    ST_Longitude(location) AS longitude,
    ST_Latitude(location) AS latitude
FROM places
WHERE ST_Longitude(location) NOT BETWEEN 102 AND 110
   OR ST_Latitude(location) NOT BETWEEN 8 AND 24;
~~~

Đây chỉ là bộ lọc kiểm tra dữ liệu theo vùng dự kiến, không phải quy tắc hợp lệ chung cho mọi ứng dụng. Hãy điều chỉnh miền theo phạm vi nghiệp vụ và rà soát các điểm ngoại lệ trước khi sửa dữ liệu.

## 10. SRID và các phép đo khoảng cách

Thứ tự trục và SRID ảnh hưởng đến cách MySQL diễn giải geometry trong các phép toán không gian. Hai geometry cần có hệ quy chiếu phù hợp để so sánh có ý nghĩa.

### 10.1. Đơn vị của phép đo phụ thuộc SRS

Với hệ Cartesian, khoảng cách được tính theo đơn vị của hệ tọa độ. Với các SRS địa lý được hỗ trợ, ST_Distance() trả khoảng cách theo mét. Không được coi mọi kết quả khoảng cách là mét nếu geometry có SRID 0 hoặc dùng hệ tọa độ phẳng với đơn vị khác.

Ví dụ:

~~~sql
SELECT ST_Distance(
    ST_GeomFromText(
        'POINT(105.8342 21.0278)',
        4326,
        'axis-order=long-lat'
    ),
    ST_GeomFromText(
        'POINT(105.85 21.03)',
        4326,
        'axis-order=long-lat'
    )
) AS distance_meters;
~~~

Đối với hai điểm cùng SRID 4326, MySQL xử lý chúng như tọa độ địa lý và kết quả ST_Distance() có đơn vị mét trên các phiên bản hỗ trợ phép đo địa lý.

### 10.2. Không tự đổi thứ tự trục trước mọi phép toán

Khi geometry đã được tạo với SRID và thứ tự trục đúng, các phép toán không gian làm việc trên geometry đó. Không hoán đổi các giá trị một lần nữa chỉ vì một hàm có tên chứa X hoặc Y.

Nếu cần kiểm tra vị trí đầu vào, dùng ST_Longitude() và ST_Latitude(). Nếu cần chuyển CRS, dùng ST_Transform(). Nếu chỉ cần định dạng WKT, dùng ST_AsText() với axis-order phù hợp.

### 10.3. Tránh so sánh geometry khác SRID

Không trộn geometry SRID 4326 và 3857 trong cùng một phép toán khoảng cách hoặc quan hệ không gian mà không chuyển chúng về một hệ quy chiếu phù hợp. Trước khi gọi các hàm như ST_Distance(), ST_Contains() hoặc ST_Intersects(), hãy xác minh SRID và ý nghĩa của tọa độ.

## 11. Khác biệt phiên bản MySQL cần lưu ý

Khả năng xử lý SRS địa lý được mở rộng đáng kể trong MySQL 8.0. Nếu ứng dụng chạy trên nhiều phiên bản, hãy xác định phiên bản tối thiểu trước khi dùng các hàm và cú pháp liên quan đến axis order.

| Khả năng | Mốc phiên bản MySQL |
|---|---|
| Hỗ trợ SRS địa lý và phép toán theo SRID ngoài SRID 0 | MySQL 8.0 |
| Tùy chọn axis-order trong các hàm WKT/WKB liên quan | MySQL 8.0.12 |
| ST_Longitude() và ST_Latitude() | MySQL 8.0.12 |
| Cột geometry giới hạn SRID và ST_Transform() | MySQL 8.0.13 |
| ST_Distance() hỗ trợ các SRS địa lý | MySQL 8.0.18 |

Các mốc này giúp xác định khả năng có mặt của tính năng; vẫn cần kiểm tra Reference Manual của đúng phiên bản đang triển khai, đặc biệt khi dùng SRS tùy chỉnh hoặc phép biến đổi CRS cụ thể.

### 11.1. Không giả định máy chủ cũ hiểu axis-order

Nếu ứng dụng hỗ trợ MySQL trước 8.0.12, không được mặc định rằng tùy chọn axis-order trong WKT/WKB sẽ hoạt động. Cần thiết kế lớp chuyển đổi tương thích với phiên bản hoặc nâng cấp máy chủ trước khi sử dụng cú pháp đó.

### 11.2. Kiểm tra khả năng của môi trường triển khai

~~~sql
SELECT VERSION() AS mysql_version;

SELECT
    SRS_ID,
    SRS_NAME
FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
WHERE SRS_ID IN (4326, 3857);
~~~

Kiểm tra cả phiên bản server lẫn SRS cần dùng. Có phiên bản hỗ trợ hàm nhưng dữ liệu nguồn hoặc hệ quy chiếu cụ thể vẫn không đáp ứng yêu cầu chuyển đổi.

## 12. Các lỗi thường gặp và cách xử lý

### 12.1. Nhập longitude trước latitude nhưng không chỉ định axis-order

**Triệu chứng:** câu lệnh báo tọa độ ngoài miền hợp lệ hoặc điểm xuất hiện sai vị trí.

**Nguyên nhân:** MySQL dùng thứ tự trục được định nghĩa trong EPSG:4326, trong khi đầu vào của ứng dụng là longitude/latitude.

**Cách xử lý:** truyền axis-order=long-lat cho hàm đọc WKT hoặc chuyển đổi đầu vào theo một hợp đồng rõ ràng.

### 12.2. Xuất WKT rồi ứng dụng đảo ngược tọa độ

**Triệu chứng:** điểm được ghi đúng nhưng khi đọc ra, ứng dụng lại đặt marker ở vị trí khác.

**Nguyên nhân:** ST_AsText() mặc định xuất theo thứ tự trục của SRS, có thể khác thứ tự mà API mong đợi.

**Cách xử lý:** dùng ST_AsText() với axis-order=long-lat nếu API yêu cầu longitude trước latitude; hoặc trả longitude và latitude thành hai trường riêng.

### 12.3. Dùng ST_SRID() thay cho ST_Transform()

**Triệu chứng:** tọa độ vẫn giữ nguyên con số dù SRID đã đổi; phép đo hoặc vị trí trên bản đồ không chính xác.

**Nguyên nhân:** ST_SRID() chỉ gán mã hệ quy chiếu. Nó không chuyển đổi tọa độ hoặc đơn vị.

**Cách xử lý:** xác định đúng SRS nguồn rồi dùng ST_Transform() sang SRID đích. Chỉ gán SRID khi biết chắc tọa độ hiện tại đã được biểu diễn trong SRS đó.

### 12.4. Nhầm SRID 4326 với hệ tọa độ mét

**Triệu chứng:** ứng dụng xem các giá trị longitude/latitude như X/Y theo mét hoặc tính khoảng cách bằng phép trừ trực tiếp hai tọa độ.

**Nguyên nhân:** EPSG:4326 dùng đơn vị góc theo độ, không phải mét.

**Cách xử lý:** dùng phép toán không gian hỗ trợ SRS địa lý hoặc chuyển đổi sang hệ chiếu thích hợp khi bài toán cần tọa độ phẳng. Không tự nhân độ với một hệ số cố định để giả lập mét cho mọi vị trí.

### 12.5. Dùng ST_X()/ST_Y() để tạo API longitude/latitude

**Triệu chứng:** hai trường trong API có tên longitude và latitude nhưng dữ liệu bị đảo theo định nghĩa trục.

**Nguyên nhân:** X/Y là tên thành phần tọa độ; không nên suy luận chúng luôn mang ý nghĩa longitude/latitude cho mọi SRS.

**Cách xử lý:** dùng ST_Longitude() và ST_Latitude() cho POINT địa lý.

### 12.6. Geometry hợp lệ nhưng vị trí sai

**Triệu chứng:** ST_IsValid() trả 1 nhưng marker nằm sai khu vực.

**Nguyên nhân:** ST_IsValid() kiểm tra tính hợp lệ hình học, không kiểm tra hợp đồng tọa độ, CRS hoặc vị trí nghiệp vụ.

**Cách xử lý:** kiểm tra SRID, thứ tự trục, miền địa lý dự kiến và đối chiếu với điểm tham chiếu đã biết.

### 12.7. Ghi geometry vào cột bị giới hạn SRID khác

**Triệu chứng:** INSERT hoặc UPDATE thất bại do SRID không khớp.

**Nguyên nhân:** cột được khai báo chỉ chấp nhận một SRID, ví dụ 4326, nhưng geometry đầu vào mang SRID 0 hoặc 3857.

**Cách xử lý:** xác minh SRS nguồn. Nếu tọa độ thực sự đã ở EPSG:4326, gán đúng SRID; nếu tọa độ thuộc CRS khác, dùng phép biến đổi thích hợp. Không thay SRID chỉ để vượt qua lỗi ghi.

### 12.8. Phép biến đổi không được hỗ trợ

**Triệu chứng:** ST_Transform() báo lỗi hoặc không thể thực hiện phép chuyển đổi.

**Nguyên nhân:** thiếu SRS nguồn/đích, dùng SRID 0 không có định nghĩa địa lý hoặc phép chuyển đổi không được MySQL hỗ trợ trong môi trường đó.

**Cách xử lý:** xác nhận hai SRS tồn tại trong data dictionary, xác định SRID nguồn đúng và kiểm tra khả năng chuyển đổi của phiên bản MySQL.

### 12.9. Trộn GeoJSON và WKT mà không chuẩn hóa

**Triệu chứng:** cùng một điểm nhưng dữ liệu từ API và dữ liệu nhập WKT lệch nhau.

**Nguyên nhân:** GeoJSON thường dùng longitude/latitude, còn WKT mặc định với EPSG:4326 trong MySQL theo thứ tự trục SRS.

**Cách xử lý:** dùng ST_GeomFromGeoJSON() cho GeoJSON và chỉ định axis-order rõ ràng khi đọc/ghi WKT.

## 13. Quy trình chuẩn cho dữ liệu địa lý

Một luồng xử lý nhất quán giúp tránh lỗi trục ngay từ đầu:

1. **Xác định nguồn:** biết dữ liệu đến từ GPS, GeoJSON, WKT, hệ thống GIS hay một phép chiếu khác.
2. **Xác định CRS:** xác nhận SRID thật của tọa độ nguồn, không suy đoán từ độ lớn con số.
3. **Xác định thứ tự:** ghi rõ nguồn dùng longitude/latitude hay thứ tự trục theo SRS.
4. **Kiểm tra miền:** xác thực longitude và latitude theo miền hợp lệ khi dữ liệu là EPSG:4326.
5. **Chuyển đổi đầu vào:** dùng hàm đọc phù hợp và axis-order tường minh.
6. **Giới hạn SRID ở schema:** nếu toàn bộ cột dùng một CRS, khai báo SRID restriction và chọn kiểu geometry thích hợp.
7. **Đọc lại để xác minh:** kiểm tra ST_SRID(), ST_Longitude(), ST_Latitude() và một WKT được xuất theo hợp đồng.
8. **Đối chiếu thực địa:** xác minh một số điểm tham chiếu trên bản đồ.
9. **Biến đổi khi cần:** dùng ST_Transform() nếu cần đổi sang CRS khác cho phân tích hoặc hiển thị.
10. **Theo dõi chất lượng:** phát hiện SRID lẫn lộn, tọa độ ngoài vùng nghiệp vụ và sai lệch từ các nguồn tích hợp.

### 13.1. Ví dụ pipeline ghi và đọc

~~~sql
-- 1. Tạo geometry từ dữ liệu ứng dụng gửi longitude/latitude.
SET @incoming = ST_GeomFromText(
    'POINT(105.8342 21.0278)',
    4326,
    'axis-order=long-lat'
);

-- 2. Xác minh ý nghĩa trước khi ghi.
SELECT
    ST_SRID(@incoming) AS srid,
    ST_Longitude(@incoming) AS longitude,
    ST_Latitude(@incoming) AS latitude;

-- 3. Ghi geometry vào cột có SRID restriction 4326.
INSERT INTO places (place_id, name, location)
VALUES (2001, 'Điểm kiểm soát', @incoming);

-- 4. Đọc theo hợp đồng longitude/latitude.
SELECT
    ST_Longitude(location) AS longitude,
    ST_Latitude(location) AS latitude,
    ST_AsText(location, 'axis-order=long-lat') AS wkt
FROM places
WHERE place_id = 2001;
~~~

Pipeline này thể hiện rõ điểm chuyển đổi giữa dữ liệu ứng dụng và geometry MySQL. Trong mã ứng dụng thực tế, hãy dùng prepared statement để bind WKT và các giá trị khác.

## 14. Bài thực hành

### 14.1. Phân biệt thứ tự trục

Tạo hai biến geometry cùng mô tả một điểm gần Hà Nội:

- WKT latitude/longitude với axis-order=lat-long.
- WKT longitude/latitude với axis-order=long-lat.

So sánh ST_SRID(), ST_Longitude(), ST_Latitude() và ST_AsText() theo cả hai thứ tự xuất.

### 14.2. Tìm lỗi đảo trục

Thử nhập POINT(105.8342 21.0278) vào SRID 4326 mà không chỉ định axis-order. Quan sát lỗi hoặc cách diễn giải của server. Sau đó thêm long-lat và so sánh.

### 14.3. Gán SRID và biến đổi SRID

Tạo một geometry SRID 0 có tọa độ đã biết theo EPSG:4326. Gán SRID 4326 bằng ST_SRID() và đọc longitude/latitude. Sau đó biến đổi sang SRID 3857 bằng ST_Transform(). Giải thích vì sao hai thao tác cho kết quả khác nhau.

### 14.4. Lưu điểm với SRID restriction

Tạo bảng places với cột POINT NOT NULL SRID 4326 và SPATIAL INDEX. Chèn điểm bằng ST_GeomFromText() với long-lat. Thử ghi geometry SRID 0 và geometry SRID 3857 để quan sát lỗi không khớp SRID.

### 14.5. Đọc GeoJSON

Dùng ST_GeomFromGeoJSON() để đọc một Point có coordinates [longitude, latitude]. Kiểm tra ST_Longitude() và ST_Latitude(), sau đó xuất lại bằng ST_AsGeoJSON().

### 14.6. Kiểm tra dữ liệu theo vùng

Viết truy vấn tìm điểm nằm ngoài vùng tọa độ dự kiến của một khu vực nghiệp vụ. Nêu rõ vì sao đây chỉ là kiểm tra chất lượng theo miền, không phải xác nhận CRS.

### 14.7. Xem định nghĩa SRS

Truy vấn INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS để xem SRS 4326 và 3857. Xác định đơn vị và thứ tự trục từ định nghĩa thay vì suy luận từ tên.

### 14.8. Thiết kế hợp đồng API

Viết tài liệu ngắn cho API nhận longitude và latitude, lưu POINT SRID 4326 và trả GeoJSON. Ghi rõ thứ tự mảng, SRID, miền giá trị và cách xử lý dữ liệu thiếu.

## 15. Checklist trước khi phát hành

- [ ] Đã xác định CRS/SRID thực của nguồn dữ liệu.
- [ ] Đã xác định thứ tự trục của nguồn và đích.
- [ ] Không nhầm EPSG:4326 với quy ước longitude/latitude của mọi API.
- [ ] Dùng axis-order=long-lat hoặc lat-long tường minh khi đọc WKT nếu cần.
- [ ] Dùng ST_AsText() với axis-order phù hợp khi xuất WKT.
- [ ] Dùng ST_Longitude() và ST_Latitude() để đọc tọa độ địa lý.
- [ ] Không mặc định ST_X() luôn là longitude và ST_Y() luôn là latitude.
- [ ] Đã kiểm tra longitude trong -180..180 và latitude trong -90..90 khi dùng SRID 4326.
- [ ] Đã phân biệt ST_SRID() với ST_Transform().
- [ ] Không gán SRID mới để giả lập phép chuyển đổi CRS.
- [ ] Cột geometry có SRID restriction phù hợp với dữ liệu lưu trữ.
- [ ] Spatial index được tạo trên cột đáp ứng yêu cầu của InnoDB.
- [ ] Đã kiểm tra SRID, geometry type và tính hợp lệ sau khi ghi.
- [ ] Đã đối chiếu điểm kiểm soát trên bản đồ hoặc nguồn tham chiếu.
- [ ] Đã xác định quy tắc longitude/latitude của GeoJSON.
- [ ] Đã kiểm tra phiên bản MySQL và khả năng của các hàm cần dùng.
- [ ] Đã kiểm tra đơn vị kết quả của các phép đo không gian.
- [ ] Đã kiểm thử dữ liệu biên, dữ liệu âm và dữ liệu từ mọi nguồn tích hợp.

## Kết luận

EPSG:4326 là hệ quy chiếu WGS 84 có thứ tự trục latitude rồi longitude theo định nghĩa SRS. Nhiều ứng dụng và GeoJSON lại gửi longitude trước latitude. Trong MySQL, hãy dùng axis-order để diễn giải hoặc xuất WKT đúng hợp đồng; dùng ST_Longitude() và ST_Latitude() để lấy giá trị địa lý; dùng ST_SRID() để đọc/gán SRID và ST_Transform() để chuyển đổi tọa độ thực sự.

SRID, thứ tự trục và phép biến đổi tọa độ là ba việc riêng biệt. Một geometry hợp lệ về hình học vẫn có thể mang tọa độ sai về nghiệp vụ. Hãy xác minh nguồn CRS, chuẩn hóa thứ tự tại biên tích hợp, giới hạn SRID trong schema khi phù hợp và đối chiếu bằng các điểm tham chiếu đã biết trước khi đưa dữ liệu không gian vào sản xuất.
