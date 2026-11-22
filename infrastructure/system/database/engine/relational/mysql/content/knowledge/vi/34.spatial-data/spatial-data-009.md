# Thiết kế truy vấn vị trí có dữ liệu biên và kiểm chứng sai số

Bài học thuộc chương **Dữ liệu không gian** của module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Truy vấn vị trí thường phải trả lời những câu hỏi tưởng như đơn giản: một điểm có thuộc vùng phục vụ không, điểm nằm đúng đường biên được tính vào vùng nào, hai vùng có chạm nhau không, hoặc một địa điểm cách ranh giới bao nhiêu mét. Kết quả sai thường đến từ việc nhầm thứ tự kinh độ/vĩ độ, gán sai SRID, dùng MBR thay cho hình học thật, hoặc so sánh tọa độ với độ chính xác không phù hợp.

Sau bài này, bạn có thể chọn geometry type và SRID đúng, tạo điểm và polygon với trục tọa độ có chủ đích, phân biệt quan hệ strict interior với boundary-inclusive, dùng MBR làm bước lọc ứng viên rồi xác minh bằng predicate hình học chính xác, kiểm tra hình học không hợp lệ, đo khoảng cách theo mét, đặt tolerance có ý nghĩa nghiệp vụ và dùng EXPLAIN để xác nhận spatial index thực sự được khai thác.

## 1. Mô hình dữ liệu không gian trong MySQL

MySQL hỗ trợ các kiểu hình học chính:

| Kiểu | Biểu diễn | Ví dụ nghiệp vụ |
|---|---|---|
| GEOMETRY | Kiểu tổng quát | Một cột chứa nhiều loại geometry |
| POINT | Một tọa độ | Vị trí cửa hàng, thiết bị, khách hàng |
| LINESTRING | Một đường gồm nhiều điểm | Tuyến đường, ranh giới dạng đường |
| POLYGON | Vùng có một vòng ngoài và có thể có lỗ | Khu giao hàng, quận, khu bảo vệ |
| MULTIPOINT | Nhiều điểm | Các điểm quan trắc |
| MULTILINESTRING | Nhiều đường | Mạng lưới tuyến |
| MULTIPOLYGON | Nhiều polygon | Khu vực gồm nhiều vùng tách rời |
| GEOMETRYCOLLECTION | Tập nhiều geometry | Dữ liệu hỗn hợp |

Dữ liệu không gian được lưu trong cột có kiểu geometry. Không nên chỉ lưu longitude và latitude trong hai cột số nếu nghiệp vụ cần phép toán hình học, quan hệ vùng, khoảng cách hoặc spatial index.

Ví dụ bảng địa điểm:

~~~sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    place_name VARCHAR(150) NOT NULL,
    location POINT NOT NULL SRID 4326
) ENGINE=InnoDB;
~~~

Cột location lưu một POINT trong hệ quy chiếu địa lý SRID 4326. Việc khai báo SRID ngay trong định nghĩa cột giới hạn dữ liệu được lưu vào cột ở đúng hệ quy chiếu đó.

### Geometry khác Geography ở cách diễn giải tọa độ

MySQL dùng cùng họ kiểu geometry nhưng cách tính toán phụ thuộc spatial reference system (SRS):

- Cartesian SRS: tọa độ X/Y nằm trên mặt phẳng; đơn vị phụ thuộc SRS.
- Geographic SRS: tọa độ biểu diễn vị trí trên Trái Đất; khoảng cách địa lý được tính theo mô hình ellipsoid hoặc sphere tùy hàm.

SRID 0 là mặt phẳng Cartesian đặc biệt không có đơn vị trục được định nghĩa. Không lấy kết quả khoảng cách SRID 0 rồi gọi đó là mét nếu chưa tự quy định đơn vị.

SRID 4326 là WGS 84, thường dùng với dữ liệu GPS. Tọa độ được biểu diễn bằng góc, không phải mét.

## 2. SRID và thứ tự trục longitude/latitude

Một lỗi dữ liệu phổ biến là truyền nhầm latitude và longitude.

Trong cách biểu diễn thông dụng của ứng dụng bản đồ:

- X là longitude (kinh độ).
- Y là latitude (vĩ độ).

Ví dụ một điểm tại Thành phố Hồ Chí Minh có thể có longitude khoảng 106.7 và latitude khoảng 10.78.

Tuy nhiên, định nghĩa EPSG:4326 trong MySQL có thứ tự trục mặc định là latitude trước, longitude sau. Các hàm tạo geometry từ WKT theo mặc định tuân theo thứ tự trục được định nghĩa trong SRS.

Vì vậy, nếu WKT được truyền theo quy ước longitude/latitude quen thuộc, hãy chỉ rõ:

~~~sql
SET @p = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);
~~~

Tùy chọn axis-order=long-lat nói rõ tọa độ trong WKT được cung cấp theo longitude rồi latitude.

Nếu dùng mặc định SRID-defined, thứ tự tọa độ phải theo định nghĩa trục của SRS:

~~~sql
SET @p = ST_GeomFromText(
    'POINT(10.7800 106.7000)',
    4326
);
~~~

Hai biểu thức trên mô tả cùng vị trí nếu thứ tự trục được khai báo đúng. Không trộn hai convention trong cùng pipeline nhập dữ liệu.

### Kiểm tra tọa độ sau khi tạo geometry

~~~sql
SELECT
    ST_SRID(@p) AS srid,
    ST_Longitude(@p) AS longitude,
    ST_Latitude(@p) AS latitude,
    ST_AsText(@p, 'axis-order=long-lat') AS wkt_long_lat;
~~~

Đối với geographic SRS, MySQL kiểm tra phạm vi tọa độ:

- Longitude thuộc khoảng (-180, 180].
- Latitude thuộc khoảng [-90, 90].

Nếu vượt phạm vi, hàm spatial có thể phát sinh lỗi longitude/latitude out of range.

Đừng chỉ kiểm tra số có nằm trong phạm vi hay không. Một cặp tọa độ bị hoán đổi đôi khi vẫn hợp lệ về số học nhưng trỏ đến một vị trí hoàn toàn khác.

### ST_SRID() không chuyển đổi tọa độ

Hai thao tác sau khác nhau:

- ST_SRID(geom, srid): thay SRID được gắn vào geometry, không chuyển đổi giá trị tọa độ.
- ST_Transform(geom, target_srid): chuyển đổi tọa độ từ SRS nguồn sang SRS đích.

Không dùng ST_SRID() để sửa dữ liệu khi tọa độ thực tế đang ở một hệ quy chiếu khác. Gán nhãn SRID sai có thể làm mọi phép tính sau đó sai mà không nhất thiết phát sinh lỗi ngay.

## 3. Tạo vùng và điểm bằng WKT

WKT (Well-Known Text) là cách biểu diễn geometry dưới dạng văn bản. Ví dụ:

~~~sql
SET @point = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);

SET @zone = ST_GeomFromText(
    'POLYGON((
        106.6800 10.7600,
        106.7200 10.7600,
        106.7200 10.8000,
        106.6800 10.8000,
        106.6800 10.7600
    ))',
    4326,
    'axis-order=long-lat'
);
~~~

Polygon có một vòng ngoài. Điểm đầu và điểm cuối của vòng phải trùng nhau để khép kín.

Một polygon có thể có các vòng trong biểu diễn lỗ (interior rings). Điểm nằm trong lỗ không thuộc phần diện tích của polygon.

### Điều kiện well-formed và validity

MySQL phân biệt hai khái niệm:

- Syntactically well-formed: dữ liệu tuân theo cấu trúc WKT/WKB hợp lệ, ví dụ polygon có vòng, vòng được đóng và có ít nhất bốn tọa độ tính cả điểm lặp cuối.
- Geometrically valid: hình học đáp ứng quy tắc topology, ví dụ polygon không tự cắt, các vòng trong nằm trong vòng ngoài, các polygon trong MultiPolygon không chồng lấn.

Một polygon có thể well-formed nhưng không valid. MySQL không tự kiểm tra đầy đủ geometric validity ở mọi lần ghi vì chi phí tính toán. Geometry không valid có thể làm spatial computation trả kết quả không xác định hoặc phát sinh lỗi.

Kiểm tra:

~~~sql
SELECT
    ST_IsValid(@zone) AS is_valid,
    ST_GeometryType(@zone) AS geometry_type,
    ST_SRID(@zone) AS srid;
~~~

Có thể dùng ST_Validate() để nhận geometry nếu hợp lệ; hàm trả NULL nếu geometry không hợp lệ hoặc không well-formed.

~~~sql
SELECT ST_Validate(@zone);
~~~

Trong quy trình nhập dữ liệu ranh giới, nên xác thực geometry trước khi ghi vào bảng chính. Lưu lại nguồn dữ liệu và phiên bản polygon để có thể đối soát khi ranh giới thay đổi.

## 4. Ranh giới có được tính là nằm trong vùng không?

Đây là quyết định nghiệp vụ phải được xác định trước khi viết query.

Giả sử một polygon là vùng phục vụ và một point là địa chỉ giao hàng. Điểm có thể nằm:

1. Bên trong vùng.
2. Chính xác trên đường biên.
3. Bên ngoài vùng.

Các predicate hình học có semantics khác nhau.

| Predicate | Điểm trong vùng | Điểm trên biên | Điểm ngoài |
|---|---:|---:|---:|
| ST_Contains(polygon, point) | 1 | 0 | 0 |
| ST_Within(point, polygon) | 1 | 0 | 0 |
| ST_Intersects(polygon, point) | 1 | 1 | 0 |
| ST_Disjoint(polygon, point) | 0 | 0 | 1 |
| ST_Touches(polygon, point) | 0 | 1 | 0 |

### ST_Contains: chỉ nhận phần trong

~~~sql
SELECT ST_Contains(@zone, @point);
~~~

ST_Contains trả về 1 khi geometry thứ nhất chứa geometry thứ hai và hai geometry không giao nhau tại biên theo định nghĩa contains. Với point nằm đúng trên cạnh polygon, kết quả là 0.

Dùng ST_Contains khi quy tắc yêu cầu điểm phải nằm hẳn trong vùng. Ví dụ điểm đặt thiết bị phải nằm trong khu vực được cấp phép và điểm đúng đường ranh được xử lý riêng.

### ST_Within: quan hệ ngược

~~~sql
SELECT ST_Within(@point, @zone);
~~~

ST_Within(point, polygon) kiểm tra quan hệ ngược với ST_Contains(polygon, point). Điểm nằm đúng trên biên cũng không được xem là within.

### ST_Intersects: nhận cả điểm trên biên

~~~sql
SELECT ST_Intersects(@zone, @point);
~~~

ST_Intersects trả về 1 nếu hai geometry có ít nhất một điểm chung. Với point và polygon, điểm nằm trong vùng hoặc đúng trên đường biên đều giao với polygon.

Dùng predicate này nếu chính sách nói rằng ranh giới thuộc vùng. Ví dụ vùng giao hàng bao gồm cả địa chỉ nằm trên đường ranh.

### ST_Touches: nhận diện trường hợp chạm biên

~~~sql
SELECT ST_Touches(@zone, @point);
~~~

ST_Touches trả về 1 khi phần trong của hai geometry không giao nhau nhưng biên của một geometry giao với biên hoặc phần trong của geometry kia. Với point nằm đúng trên biên polygon, đây là cách phân biệt trường hợp chạm biên với trường hợp nằm sâu bên trong.

Không dùng ST_Touches để thay cho ST_Intersects khi cần toàn bộ điểm nằm trong hoặc trên vùng.

### Định nghĩa chính sách trước khi triển khai

Ví dụ:

- Khu vực phục vụ: tính điểm trên biên là thuộc vùng.
- Khu vực cấm: điểm trên biên cũng bị xem là nằm trong khu vực cấm.
- Phân chia địa giới: hai polygon có thể cùng chạm một đường biên; cần quy tắc gán một điểm biên cho một đơn vị duy nhất nếu nghiệp vụ yêu cầu kết quả không trùng.
- Vùng thu phí: cần quy định cách xử lý điểm sát ranh, vì sai số GPS có thể khiến cùng một thiết bị dao động giữa hai vùng.

Không có một predicate phù hợp cho mọi nghiệp vụ. Hãy chọn semantics rồi kiểm thử bằng điểm trong, điểm biên và điểm ngoài.

## 5. MBR và hình dạng thực là hai phép kiểm tra khác nhau

MBR (Minimum Bounding Rectangle) là hình chữ nhật nhỏ nhất bao quanh geometry theo hai trục tọa độ.

Ví dụ một polygon lõm có thể có MBR hình chữ nhật lớn hơn nhiều phần diện tích thật. Một điểm có thể nằm trong MBR nhưng vẫn nằm ngoài polygon.

Các nhóm hàm:

- ST_Contains(), ST_Intersects(), ST_Touches(): kiểm tra quan hệ giữa hình dạng thực.
- MBRContains(), MBRIntersects(), MBRWithin(), MBRCovers(): kiểm tra quan hệ giữa các hình chữ nhật bao quanh geometry.

Ví dụ polygon hình chữ C:

~~~sql
SET @concave = ST_GeomFromText(
    'POLYGON((
        0 0,
        4 0,
        4 1,
        1 1,
        1 3,
        4 3,
        4 4,
        0 4,
        0 0
    ))'
);

SET @point_in_notch = ST_GeomFromText('POINT(3 2)');

SELECT
    MBRIntersects(@concave, @point_in_notch) AS mbr_match,
    ST_Intersects(@concave, @point_in_notch) AS exact_match;
~~~

Điểm (3,2) nằm trong hình chữ nhật bao quanh nhưng ở phần lõm của polygon. MBRIntersects có thể trả 1 trong khi ST_Intersects trả 0.

Đây là false positive của bước MBR. Nó không phải lỗi nếu MBR chỉ dùng để lọc ứng viên.

### Contains và Covers ở cấp MBR

Với MBR:

- MBRContains yêu cầu geometry thứ hai nằm trong phần trong của MBR thứ nhất; điểm đúng cạnh không được tính là contained.
- MBRCovers nhận cả điểm nằm trên biên MBR.
- MBRIntersects nhận mọi trường hợp hai MBR có phần giao nhau.

Không nhầm MBRCovers với việc polygon thật cover point. MBRCovers chỉ nói hình chữ nhật bao quanh có quan hệ cover; phần hình dạng thật vẫn cần predicate ST_* để xác minh.

## 6. Hai bước truy vấn: lọc ứng viên rồi xác minh hình học

Với bảng có nhiều vùng, một truy vấn chính xác có thể phải kiểm tra nhiều polygon. Spatial index giúp giảm tập ứng viên bằng MBR.

Mẫu boundary-inclusive:

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@point, geom)
  AND ST_Intersects(geom, @point);
~~~

Hai điều kiện có nhiệm vụ khác nhau:

1. MBRIntersects lọc các polygon có bounding rectangle giao với bounding rectangle của điểm. Bước này có thể khai thác R-tree spatial index nếu optimizer chọn được kế hoạch phù hợp.
2. ST_Intersects xác minh điểm có thực sự nằm trong hoặc chạm hình dạng polygon hay không.

Với quy tắc chỉ nhận phần trong:

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRWithin(@point, geom)
  AND ST_Contains(geom, @point);
~~~

MBRWithin là bước lọc theo hình chữ nhật. ST_Contains là điều kiện cuối cùng theo hình dạng thực.

### Vì sao không chỉ dùng MBR?

Nếu chỉ dùng MBRIntersects, điểm nằm trong phần rỗng của một polygon lõm hoặc trong lỗ của polygon vẫn có thể bị trả về.

Nếu chỉ dùng MBRContains, điểm nằm trong MBR không có nghĩa là nằm trong polygon thật.

### Vì sao không chỉ dùng predicate exact?

ST_Intersects hoặc ST_Contains diễn tả chính xác nghiệp vụ, nhưng nếu không có bước lọc phù hợp, engine có thể phải đánh giá hình học trên nhiều hàng.

Spatial index là công cụ giảm ứng viên; exact predicate là công cụ bảo đảm kết quả đúng.

Không được bỏ exact predicate chỉ để query nhanh hơn.

## 7. Spatial index và điều kiện để optimizer sử dụng

MySQL tạo spatial index bằng R-tree. InnoDB và MyISAM hỗ trợ spatial index.

Cột được index phải:

- Có kiểu geometry.
- Được khai báo NOT NULL.
- Có SRID cụ thể trong định nghĩa cột để trở thành SRID-restricted.
- Mỗi spatial index chỉ áp dụng trên một spatial column.

Ví dụ:

~~~sql
CREATE TABLE service_zones (
    zone_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    zone_name VARCHAR(150) NOT NULL,
    geom POLYGON NOT NULL SRID 4326,
    SPATIAL INDEX sx_service_zones_geom (geom)
) ENGINE=InnoDB;
~~~

Không khai báo SRID-restricted:

~~~sql
CREATE TABLE zones_without_srid (
    zone_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    geom POLYGON NOT NULL,
    SPATIAL INDEX sx_geom (geom)
) ENGINE=InnoDB;
~~~

Trong MySQL 9.7, optimizer chỉ sử dụng spatial index cho các cột bị giới hạn bởi SRID. Một spatial index trên cột không có SRID attribute có thể vẫn được duy trì khi ghi, nhưng optimizer bỏ qua index đó.

### MySQL 9.7 xử lý geographic index theo SRS

Optimizer kiểm tra SRID của cột để chọn phép tính bounding box phù hợp với SRS:

- Cartesian SRID: dùng Cartesian bounding box.
- Geographic SRID: dùng geographic bounding box.

Trước MySQL 9.7, spatial index comparisons được thực hiện theo Cartesian calculation; kết quả với SRID địa lý không phải Cartesian có thể không xác định. Khi nâng cấp từ phiên bản cũ, cần kiểm tra schema có SRID attribute và dữ liệu có đồng nhất SRID hay không.

Kiểm tra SRID đang có:

~~~sql
SELECT DISTINCT ST_SRID(geom)
FROM service_zones;
~~~

Nếu cột có nhiều SRID, cần chuẩn hóa dữ liệu trước khi chuyển cột thành SRID-restricted.

### Kiểm tra bằng EXPLAIN

~~~sql
EXPLAIN
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@point, geom)
  AND ST_Intersects(geom, @point);
~~~

Quan sát:

| Trường | Cần kiểm tra |
|---|---|
| possible_keys | Spatial index có được xem xét không |
| key | Index nào được chọn |
| type | Access type có sử dụng range/index access không |
| rows | Số hàng ước lượng |
| filtered | Tỷ lệ còn lại sau điều kiện lọc |
| Extra | Các điều kiện còn phải kiểm tra |

Optimizer không bắt buộc dùng index trong mọi truy vấn. Bảng nhỏ, MBR quá rộng hoặc predicate có độ chọn lọc thấp có thể khiến table scan rẻ hơn.

Tài liệu MySQL minh họa việc dùng spatial index với MBRContains() và MBRWithin() trong WHERE. Với các biến thể MBR khác, hãy kiểm tra kế hoạch thực tế thay vì giả định mọi predicate đều được tối ưu giống nhau.

## 8. Tạo geometry hợp lệ trước khi ghi

Một polygon cần vòng ngoài được đóng kín. Ví dụ hợp lệ về cấu trúc:

~~~sql
SET @valid_polygon = ST_GeomFromText(
    'POLYGON((
        0 0,
        4 0,
        4 4,
        0 4,
        0 0
    ))'
);

SELECT ST_IsValid(@valid_polygon);
~~~

Một polygon dạng bow-tie tự cắt:

~~~sql
SET @invalid_polygon = ST_GeomFromText(
    'POLYGON((
        0 0,
        2 2,
        0 2,
        2 0,
        0 0
    ))'
);

SELECT
    ST_IsValid(@invalid_polygon) AS is_valid,
    ST_Validate(@invalid_polygon) AS validated_geometry;
~~~

Geometry trên có thể well-formed về cú pháp nhưng không valid về topology.

### Quy trình nhập dữ liệu ranh giới

1. Xác nhận nguồn dữ liệu và hệ quy chiếu.
2. Xác nhận thứ tự trục.
3. Kiểm tra longitude/latitude nằm trong phạm vi.
4. Kiểm tra SRID.
5. Kiểm tra cấu trúc WKT/WKB.
6. Chạy ST_IsValid().
7. Nếu không hợp lệ, cách ly bản ghi và xử lý nguồn hoặc sửa geometry theo quy trình có kiểm soát.
8. Chỉ ghi vào bảng chính khi đạt quy tắc chất lượng dữ liệu.

Không tự động gọi ST_Validate() rồi ghi đè mọi polygon invalid mà không lưu dữ liệu gốc. Một thao tác sửa hình học có thể làm thay đổi ranh giới nghiệp vụ.

## 9. Khoảng cách địa lý và đơn vị đo

Với SRID 4326, tọa độ đầu vào là độ góc, nhưng ST_Distance() trả khoảng cách địa lý theo mét nếu không truyền đơn vị khác.

Ví dụ:

~~~sql
SET @hcm_center = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);

SET @nearby_point = ST_GeomFromText(
    'POINT(106.7100 10.7800)',
    4326,
    'axis-order=long-lat'
);

SELECT ST_Distance(@hcm_center, @nearby_point) AS distance_m;
~~~

ST_Distance() phát hiện geographic SRS và tính geodetic distance trên ellipsoid. Hàm hỗ trợ tính khoảng cách cho các geometry type trong geographic SRS.

Có thể chỉ rõ đơn vị:

~~~sql
SELECT ST_Distance(
    @hcm_center,
    @nearby_point,
    'metre'
) AS distance_m;
~~~

Đơn vị phải tồn tại trong INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE.

### ST_Distance_Sphere() là khoảng cách trên hình cầu

~~~sql
SELECT ST_Distance_Sphere(
    @hcm_center,
    @nearby_point
) AS approximate_distance_m;
~~~

ST_Distance_Sphere() trả khoảng cách ngắn nhất trên sphere, đơn vị mét. Hàm hỗ trợ Point/Point hoặc Point/MultiPoint. Nó là phép tính xấp xỉ theo hình cầu, không phải geodetic distance trên ellipsoid.

Chọn hàm:

| Nhu cầu | Hàm phù hợp |
|---|---|
| Khoảng cách địa lý theo ellipsoid | ST_Distance() |
| Khoảng cách xấp xỉ trên sphere giữa các điểm | ST_Distance_Sphere() |
| Khoảng cách trong mặt phẳng có đơn vị đã định nghĩa | ST_Distance() với Cartesian SRS phù hợp |
| Kiểm tra có giao nhau không | ST_Intersects() |
| Kiểm tra điểm có nằm trong polygon không | ST_Contains() hoặc ST_Intersects() theo chính sách biên |

Không dùng SRID 0 cho bài toán địa lý nếu chưa có quy ước đơn vị và phép chiếu riêng.

## 10. Sai số tọa độ và tolerance

Tọa độ GPS, geocoding hoặc thiết bị đo không phải lúc nào cũng phản ánh vị trí thật tuyệt đối.

Một điểm được ghi là:

~~~text
POINT(106.700000 10.780000)
~~~

có thể chỉ là giá trị đã làm tròn từ thiết bị. Một lần đo khác có thể là:

~~~text
POINT(106.700004 10.780003)
~~~

Hai tọa độ rất gần nhau nhưng không bằng nhau theo phép so sánh số thực chính xác.

Không dùng điều kiện kiểu:

~~~sql
ST_X(location) = 106.700000
~~~

để kết luận hai vị trí là cùng một địa điểm nếu dữ liệu có sai số đo.

### Không đặt epsilon tùy ý theo độ

Một sai khác 0.00001 độ longitude không tương ứng cùng một số mét ở mọi vĩ độ. Sai khác latitude và longitude cũng không có cùng tỷ lệ khoảng cách.

Không áp dụng một hằng số kiểu:

~~~sql
ABS(ST_X(location) - 106.7) < 0.00001
~~~

rồi coi đó là tolerance một mét cho mọi khu vực.

Hãy biểu diễn tolerance bằng đơn vị đo có ý nghĩa, ví dụ 1 mét hoặc 5 mét, và dùng phép đo khoảng cách theo SRS thích hợp.

### Đo khoảng cách tới ranh giới

Với một polygon đơn giản không có lỗ, có thể lấy vòng ngoài bằng ST_ExteriorRing() rồi đo khoảng cách từ điểm tới đường biên:

~~~sql
SELECT ST_Distance(
    @point,
    ST_ExteriorRing(@zone),
    'metre'
) AS distance_to_outer_boundary_m;
~~~

Nếu polygon có interior rings, MultiPolygon hoặc hình học phức tạp, cần tính đến mọi thành phần biên; ST_ExteriorRing() chỉ trả vòng ngoài của một Polygon.

Ví dụ quy tắc nghiệp vụ: điểm cách ranh giới ngoài không quá 2 mét được xem là gần biên:

~~~sql
SELECT
    CASE
        WHEN ST_Intersects(@zone, @point) = 1
            THEN 'INSIDE_OR_ON_BOUNDARY'
        WHEN ST_Distance(
            @point,
            ST_ExteriorRing(@zone),
            'metre'
        ) <= 2
            THEN 'WITHIN_2M_OF_OUTER_BOUNDARY'
        ELSE 'OUTSIDE'
    END AS location_class;
~~~

Ví dụ trên chỉ xét một Polygon không có lỗ. Quy tắc tolerance có thể nhận cả điểm vừa nằm ngoài lẫn điểm vừa nằm trong vùng, miễn là khoảng cách tới vòng ngoài không quá 2 mét. Đây là chính sách nghiệp vụ, không phải thay đổi semantics của ST_Contains().

Không biến tolerance thành một con số kỹ thuật tùy tiện. Chọn nó dựa trên:

- Độ chính xác của thiết bị định vị.
- Độ chính xác của dữ liệu ranh giới.
- Nguồn và thời điểm đo.
- Sai số do phép chiếu hoặc chuyển đổi hệ tọa độ.
- Hậu quả khi phân loại sai một điểm.

## 11. Sai số từ phép chiếu và biến đổi hệ tọa độ

Một SRS geographic dùng độ góc. Một SRS projected có thể dùng mét trên mặt phẳng.

ST_Transform() chuyển tọa độ từ SRS này sang SRS khác:

~~~sql
SELECT ST_Transform(@hcm_center, 32648);
~~~

Ví dụ SRID 32648 là WGS 84 / UTM zone 48N, một hệ chiếu phù hợp cho khu vực kinh độ của Thành phố Hồ Chí Minh. Khi dùng hệ chiếu cục bộ, khoảng cách Cartesian có đơn vị mét và phù hợp cho nhiều phép đo cự ly ngắn trong vùng đó.

Không dùng một projected SRS cho mọi địa điểm trên toàn thế giới. Phép chiếu có biến dạng; sai số tăng khi ra khỏi vùng thiết kế của projection.

Một số nguyên tắc:

- Dữ liệu toàn cầu: dùng geographic SRS phù hợp và geodetic distance.
- Dữ liệu trong một khu vực nhỏ: cân nhắc projected SRS phù hợp với khu vực.
- Tính diện tích, chiều dài, buffer hoặc tolerance: kiểm tra đơn vị và loại SRS.
- Khi chuyển đổi qua nhiều SRS: ghi rõ pipeline, phiên bản dữ liệu và độ chính xác mong đợi.
- Không thay SRID bằng ST_SRID() khi cần chuyển đổi tọa độ; dùng ST_Transform().

## 12. Truy vấn vùng phục vụ có tính cả điểm biên

Giả sử bảng service_zones lưu polygon vùng giao hàng.

~~~sql
CREATE TABLE service_zones (
    zone_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    zone_name VARCHAR(150) NOT NULL,
    geom POLYGON NOT NULL SRID 4326,
    SPATIAL INDEX sx_service_zones_geom (geom)
) ENGINE=InnoDB;
~~~

Thêm vùng mẫu:

~~~sql
INSERT INTO service_zones (
    zone_id,
    zone_name,
    geom
)
VALUES (
    1,
    'Central test zone',
    ST_GeomFromText(
        'POLYGON((
            106.6800 10.7600,
            106.7200 10.7600,
            106.7200 10.8000,
            106.6800 10.8000,
            106.6800 10.7600
        ))',
        4326,
        'axis-order=long-lat'
    )
);
~~~

Tạo một điểm bên trong:

~~~sql
SET @point_inside = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);
~~~

Tạo điểm đúng cạnh phía Tây:

~~~sql
SET @point_edge = ST_GeomFromText(
    'POINT(106.6800 10.7800)',
    4326,
    'axis-order=long-lat'
);
~~~

Tạo điểm bên ngoài:

~~~sql
SET @point_outside = ST_GeomFromText(
    'POINT(106.7300 10.7800)',
    4326,
    'axis-order=long-lat'
);
~~~

So sánh:

~~~sql
SELECT
    ST_Contains(geom, @point_inside) AS inside_contains,
    ST_Intersects(geom, @point_inside) AS inside_intersects,
    ST_Contains(geom, @point_edge) AS edge_contains,
    ST_Intersects(geom, @point_edge) AS edge_intersects,
    ST_Touches(geom, @point_edge) AS edge_touches,
    ST_Intersects(geom, @point_outside) AS outside_intersects
FROM service_zones
WHERE zone_id = 1;
~~~

Kết quả kỳ vọng:

| Kiểm tra | Kết quả |
|---|---:|
| Điểm trong: ST_Contains | 1 |
| Điểm trong: ST_Intersects | 1 |
| Điểm biên: ST_Contains | 0 |
| Điểm biên: ST_Intersects | 1 |
| Điểm biên: ST_Touches | 1 |
| Điểm ngoài: ST_Intersects | 0 |

Nếu vùng phục vụ tính cả biên, query:

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE ST_Intersects(geom, @point_edge);
~~~

Nếu vùng phục vụ chỉ tính phần trong:

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE ST_Contains(geom, @point_edge);
~~~

Query thứ hai không trả vùng cho điểm đúng trên cạnh.

## 13. Tối ưu truy vấn vùng bằng spatial index

Với một bảng lớn, thêm MBR candidate predicate:

~~~sql
EXPLAIN
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@point_edge, geom)
  AND ST_Intersects(geom, @point_edge);
~~~

Sau đó chạy truy vấn thực:

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@point_edge, geom)
  AND ST_Intersects(geom, @point_edge);
~~~

MBRIntersects bao gồm trường hợp MBR chạm nhau, nên điểm nằm trên cạnh MBR không bị loại ở bước candidate. ST_Intersects xác minh quan hệ hình dạng thực.

Với một query strict-interior:

~~~sql
EXPLAIN
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRWithin(@point_inside, geom)
  AND ST_Contains(geom, @point_inside);
~~~

Điểm trong MBR được đưa vào tập ứng viên; ST_Contains loại các điểm nằm trong MBR nhưng ngoài polygon thật.

### Đọc EXPLAIN

Nếu optimizer dùng spatial index, trường key sẽ hiển thị tên spatial index và access type phản ánh cách truy cập phù hợp. Nếu key là NULL và type là ALL, truy vấn đang quét bảng.

Nếu bảng chỉ có một vài vùng, table scan có thể là lựa chọn rẻ hơn. Hãy kiểm thử trên dữ liệu có số lượng, phân bố và độ chọn lọc gần production.

Không dùng FORCE INDEX như bước đầu tiên. Trước hết kiểm tra:

- Cột đã khai báo SRID chưa.
- Các hàng có cùng SRID không.
- Predicate MBR có đặt đúng thứ tự geometry không.
- Hình chữ nhật tìm kiếm có quá rộng không.
- Thống kê và cardinality có phù hợp không.
- Query có thực sự cần spatial index không.

## 14. Tìm địa điểm trong bán kính

Bài toán tìm các điểm cách một vị trí không quá 5 km:

~~~sql
SET @origin = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);

SELECT
    place_id,
    place_name,
    ST_Distance(location, @origin, 'metre') AS distance_m
FROM places
WHERE ST_Distance(location, @origin, 'metre') <= 5000
ORDER BY distance_m, place_id
LIMIT 50;
~~~

ST_Distance() trên geographic SRS trả geodetic distance trên ellipsoid. Điều kiện <= 5000 có nghĩa khoảng cách không quá 5.000 mét.

Tuy nhiên, biểu thức khoảng cách không phải một range lookup đơn giản trên B-tree. Với tập dữ liệu rất lớn, có thể cần một bước candidate bounding box trước, sau đó tính khoảng cách chính xác.

Candidate bounding box phải được tạo theo SRS phù hợp. Với geographic coordinates, độ rộng longitude tương ứng với một khoảng cách mét thay đổi theo latitude. Không lấy một delta longitude cố định rồi dùng cho mọi vĩ độ.

Nếu dùng ST_Distance_Sphere(), kết quả là khoảng cách xấp xỉ trên sphere và chỉ hỗ trợ Point/MultiPoint. Chọn hàm dựa trên mức sai số chấp nhận được.

## 15. Kiểm chứng các trường hợp biên và sai số

Một bài kiểm thử spatial không nên chỉ có một điểm ở giữa polygon.

Cần có tối thiểu các trường hợp:

| Trường hợp | Mục tiêu |
|---|---|
| Điểm ở sâu trong vùng | Xác nhận strict containment |
| Điểm đúng trên cạnh | Xác nhận boundary semantics |
| Điểm đúng tại đỉnh | Xác nhận vertex boundary |
| Điểm vừa bên trong biên | Đánh giá độ ổn định với tọa độ gần biên |
| Điểm vừa bên ngoài biên | Đánh giá tolerance |
| Điểm trong MBR nhưng ngoài polygon lõm | Phát hiện false positive MBR |
| Điểm trong lỗ polygon | Đảm bảo phần rỗng không bị coi là vùng |
| Điểm có SRID khác | Kiểm tra lỗi mismatch |
| Điểm có longitude/latitude sai phạm vi | Kiểm tra input validation |
| Polygon tự cắt | Kiểm tra geometry validity |

### Tạo điểm gần biên

~~~sql
SET @point_near_inside = ST_GeomFromText(
    'POINT(106.680010 10.7800)',
    4326,
    'axis-order=long-lat'
);

SET @point_near_outside = ST_GeomFromText(
    'POINT(106.679990 10.7800)',
    4326,
    'axis-order=long-lat'
);

SELECT
    ST_Contains(@zone, @point_near_inside) AS near_inside,
    ST_Contains(@zone, @point_near_outside) AS near_outside,
    ST_Distance(
        @point_near_inside,
        ST_ExteriorRing(@zone),
        'metre'
    ) AS inside_distance_to_boundary_m,
    ST_Distance(
        @point_near_outside,
        ST_ExteriorRing(@zone),
        'metre'
    ) AS outside_distance_to_boundary_m;
~~~

Trong ví dụ này @zone phải là polygon đơn giản đã tạo ở phần trước. Hai điểm có longitude chênh nhau rất nhỏ, nhưng một điểm nằm trong và điểm còn lại nằm ngoài.

Không suy ra một số mét chính xác từ delta longitude bằng phép nhân cố định. Hãy dùng ST_Distance() trên geographic SRS để đo.

### Kiểm tra kết quả ở cấp ứng dụng

Nên kiểm thử cùng một tập tọa độ qua:

1. Hàm tạo geometry trong MySQL.
2. ST_AsText() với axis order được khai báo.
3. ST_SRID().
4. ST_IsValid().
5. Predicate exact.
6. Kết quả khoảng cách.
7. Kết quả trên API hoặc bản đồ hiển thị.

Nếu kết quả SQL đúng nhưng marker trên bản đồ bị lệch, kiểm tra cách serializer GeoJSON/WKB và thứ tự trục ở tầng ứng dụng.

## 16. Xử lý lỗi SRID và dữ liệu hình học

Các lỗi thường gặp:

### Hai geometry khác SRID

Các hàm nhận nhiều geometry thường yêu cầu cùng SRS. Nếu một geometry là 4326 và một geometry là 3857, MySQL có thể phát sinh ER_GIS_DIFFERENT_SRIDS.

Kiểm tra:

~~~sql
SELECT
    ST_SRID(@point_inside) AS point_srid,
    ST_SRID(@zone) AS zone_srid;
~~~

Chỉ thực hiện spatial relation sau khi hai geometry cùng hệ quy chiếu. Nếu cần chuyển đổi, dùng ST_Transform() khi source và target SRS được hỗ trợ.

### Longitude hoặc latitude ngoài phạm vi

Ví dụ tạo point có latitude 106:

~~~sql
SELECT ST_GeomFromText(
    'POINT(10 106)',
    4326,
    'axis-order=long-lat'
);
~~~

Ở đây longitude = 10 hợp lệ nhưng latitude = 106 vượt phạm vi. MySQL phát sinh lỗi latitude out of range.

### Geometry không well-formed

Polygon không đóng vòng hoặc có quá ít điểm sẽ không được tạo từ WKT. Đây là lỗi cấu trúc.

### Geometry well-formed nhưng không valid

Polygon tự giao có thể được parse và lưu nếu cú pháp hợp lệ, nhưng spatial computation có thể trả kết quả không xác định hoặc lỗi. Dùng ST_IsValid() và ST_Validate() trong quy trình nhập dữ liệu.

### SRID được gán sai

ST_SRID(geom, 4326) không sửa tọa độ. Nếu geometry đang chứa tọa độ mét nhưng bị gán SRID 4326, MySQL sẽ diễn giải những con số đó như độ và có thể phát sinh lỗi phạm vi hoặc cho kết quả sai.

Phải biết nguồn dữ liệu đang dùng SRS nào trước khi gán nhãn hoặc chuyển đổi.

## 17. Hạn chế và lưu ý khi dùng spatial index

| Hạn chế | Ý nghĩa |
|---|---|
| Chỉ index một spatial column trong mỗi spatial index | Không tạo composite SPATIAL index trên nhiều geometry column |
| Cột phải NOT NULL | Cột nullable không đủ điều kiện tạo SPATIAL index |
| Cần SRID-restricted để optimizer sử dụng | Khai báo SRID attribute trong column |
| R-tree lưu MBR | Index không biểu diễn đầy đủ hình dạng phức tạp |
| MBR có false positive | Cần exact predicate để lọc cuối |
| Query phụ thuộc SRS | SRID khác nhau không thể so sánh trực tiếp |
| Geometry invalid | Spatial result có thể không xác định hoặc lỗi |
| Tập dữ liệu nhỏ | Table scan có thể rẻ hơn index |
| MBR quá rộng | Candidate set lớn, giảm lợi ích của index |
| Thay đổi ranh giới | Cần quản lý phiên bản geometry và thời điểm hiệu lực |

Spatial index không thay thế dữ liệu ranh giới chính xác, không tự xác định chính sách điểm biên và không giải quyết sai số từ nguồn tọa độ.

## 18. Bài thực hành: vùng phục vụ, điểm biên và sai số 2 mét

Lab tạo một vùng mẫu, một số điểm kiểm thử và các truy vấn exact/MBR để quan sát sự khác nhau.

### Bước 1: tạo database

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_spatial_boundary_lab;
USE mysql_spatial_boundary_lab;
~~~

### Bước 2: tạo bảng vùng

~~~sql
CREATE TABLE service_zones (
    zone_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    zone_name VARCHAR(150) NOT NULL,
    geom POLYGON NOT NULL SRID 4326,
    SPATIAL INDEX sx_service_zones_geom (geom)
) ENGINE=InnoDB;
~~~

### Bước 3: tạo vùng thử nghiệm

~~~sql
INSERT INTO service_zones (
    zone_id,
    zone_name,
    geom
)
VALUES (
    1,
    'HCM test rectangle',
    ST_GeomFromText(
        'POLYGON((
            106.6800 10.7600,
            106.7200 10.7600,
            106.7200 10.8000,
            106.6800 10.8000,
            106.6800 10.7600
        ))',
        4326,
        'axis-order=long-lat'
    )
);
~~~

### Bước 4: xác thực polygon

~~~sql
SELECT
    zone_id,
    ST_SRID(geom) AS srid,
    ST_IsValid(geom) AS is_valid,
    ST_AsText(geom, 'axis-order=long-lat') AS polygon_wkt
FROM service_zones;
~~~

Kết quả kỳ vọng: SRID 4326 và is_valid = 1.

### Bước 5: tạo điểm bên trong, trên biên và bên ngoài

~~~sql
SET @inside = ST_GeomFromText(
    'POINT(106.7000 10.7800)',
    4326,
    'axis-order=long-lat'
);

SET @edge = ST_GeomFromText(
    'POINT(106.6800 10.7800)',
    4326,
    'axis-order=long-lat'
);

SET @outside = ST_GeomFromText(
    'POINT(106.7300 10.7800)',
    4326,
    'axis-order=long-lat'
);
~~~

### Bước 6: so sánh boundary semantics

~~~sql
SELECT
    ST_Contains(geom, @inside) AS inside_contains,
    ST_Intersects(geom, @inside) AS inside_intersects,
    ST_Contains(geom, @edge) AS edge_contains,
    ST_Intersects(geom, @edge) AS edge_intersects,
    ST_Touches(geom, @edge) AS edge_touches,
    ST_Intersects(geom, @outside) AS outside_intersects
FROM service_zones
WHERE zone_id = 1;
~~~

Kết quả kỳ vọng:

- Điểm trong: Contains = 1, Intersects = 1.
- Điểm trên biên: Contains = 0, Intersects = 1, Touches = 1.
- Điểm ngoài: Intersects = 0.

### Bước 7: tìm vùng có tính cả biên

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@edge, geom)
  AND ST_Intersects(geom, @edge);
~~~

Kết quả phải có zone_id = 1.

### Bước 8: tìm vùng chỉ nhận phần trong

~~~sql
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRWithin(@edge, geom)
  AND ST_Contains(geom, @edge);
~~~

Kết quả không có hàng vì điểm nằm trên biên, không nằm hẳn trong phần trong của polygon.

### Bước 9: xác minh MBR false positive

~~~sql
SET @concave = ST_GeomFromText(
    'POLYGON((
        0 0,
        4 0,
        4 1,
        1 1,
        1 3,
        4 3,
        4 4,
        0 4,
        0 0
    ))'
);

SET @notch = ST_GeomFromText('POINT(3 2)');

SELECT
    MBRIntersects(@concave, @notch) AS mbr_intersects,
    ST_Intersects(@concave, @notch) AS exact_intersects;
~~~

Kết quả kỳ vọng: MBRIntersects = 1, ST_Intersects = 0. Đây là lý do cần exact predicate sau MBR candidate.

### Bước 10: đo khoảng cách tới biên

~~~sql
SELECT
    ST_Distance(
        @inside,
        ST_ExteriorRing(geom),
        'metre'
    ) AS inside_to_outer_boundary_m,
    ST_Distance(
        @outside,
        ST_ExteriorRing(geom),
        'metre'
    ) AS outside_to_outer_boundary_m
FROM service_zones
WHERE zone_id = 1;
~~~

Kết quả được tính bằng mét theo geographic SRS. Điểm ngoài có khoảng cách dương tới vòng ngoài; điểm trong cũng có khoảng cách dương tới vòng ngoài vì phép tính đang đo tới đường biên, không phải tới phần diện tích polygon.

### Bước 11: kiểm tra EXPLAIN

~~~sql
EXPLAIN
SELECT zone_id, zone_name
FROM service_zones
WHERE MBRIntersects(@edge, geom)
  AND ST_Intersects(geom, @edge);
~~~

Bảng lab nhỏ nên optimizer có thể chọn table scan. Hãy quan sát key và rows, sau đó thử lại trên tập dữ liệu lớn hơn với phân bố vùng đa dạng.

### Bước 12: mô phỏng geometry không valid

~~~sql
SET @bowtie = ST_GeomFromText(
    'POLYGON((
        0 0,
        2 2,
        0 2,
        2 0,
        0 0
    ))'
);

SELECT
    ST_IsValid(@bowtie) AS is_valid,
    ST_Validate(@bowtie) AS validated;
~~~

Kết quả kỳ vọng: is_valid = 0; ST_Validate trả NULL.

### Bước 13: dọn dẹp

~~~sql
DROP DATABASE mysql_spatial_boundary_lab;
~~~

Chỉ chạy DROP DATABASE trên database lab vừa tạo.

## 19. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Điểm nằm trên biên nhưng ST_Contains trả 0 | Contains yêu cầu phần trong, không nhận boundary | Dùng ST_Intersects nếu nghiệp vụ tính cả biên |
| Điểm trên biên không xuất hiện sau MBRContains | MBRContains cũng không nhận điểm ở biên MBR | Dùng MBRIntersects/MBRCovers phù hợp rồi exact-check |
| Điểm trong MBR nhưng ngoài polygon vẫn được trả | Chỉ dùng MBR predicate | Thêm ST_Contains hoặc ST_Intersects |
| Tọa độ hiển thị lệch vị trí | Nhầm longitude/latitude hoặc axis order | Dùng axis-order rõ ràng và kiểm tra ST_Longitude/ST_Latitude |
| Spatial function báo SRID khác nhau | Hai geometry dùng SRS khác nhau | Chuyển đổi bằng ST_Transform khi phù hợp |
| Gán SRID nhưng kết quả vẫn sai | Dùng ST_SRID thay vì transform tọa độ | Dùng ST_Transform và xác minh nguồn SRS |
| Không dùng được spatial index | Cột nullable hoặc không SRID-restricted | Khai báo NOT NULL và SRID cụ thể |
| Optimizer bỏ qua spatial index | SRID chưa khai báo hoặc predicate không phù hợp | Kiểm tra column definition, MBR predicate và EXPLAIN |
| EXPLAIN chọn table scan | Bảng nhỏ hoặc candidate predicate ít chọn lọc | Đánh giá trên dữ liệu thực; không ép index khi không có lợi |
| Polygon được lưu nhưng spatial query lỗi | Geometry well-formed nhưng không valid | Kiểm tra ST_IsValid và xử lý nguồn dữ liệu |
| Điểm gần biên lúc trong lúc ngoài | Sai số thiết bị hoặc tọa độ đã làm tròn | Định nghĩa tolerance theo mét |
| Dùng epsilon độ nhưng kết quả lệch theo vĩ độ | Độ không tương ứng khoảng cách cố định | Dùng ST_Distance hoặc projected SRS phù hợp |
| Khoảng cách SRID 0 bị hiểu là mét | SRID 0 không có đơn vị trục | Dùng geographic/projected SRS có đơn vị rõ |
| Dùng ST_Distance_Sphere với polygon | Hàm chỉ hỗ trợ Point/MultiPoint | Dùng ST_Distance hoặc hàm phù hợp với geometry |
| Vùng có lỗ nhưng điểm trong lỗ vẫn là candidate | MBR bao cả phần lỗ | Exact ST_Intersects/Contains sẽ loại false positive |
| Dữ liệu mới import có nhiều SRID | Nguồn không chuẩn hóa | Rà soát ST_SRID trước khi tạo index |
| Ranh giới thay đổi nhưng query vẫn dùng dữ liệu cũ | Không quản lý phiên bản geometry | Lưu version, effective date và nguồn dữ liệu |

## 20. Checklist thiết kế truy vấn vị trí

- [ ] Đã xác định geometry type phù hợp.
- [ ] Đã xác định SRID của nguồn dữ liệu.
- [ ] Đã thống nhất quy ước longitude/latitude.
- [ ] Đã dùng axis-order rõ ràng khi tạo geometry từ WKT.
- [ ] Đã kiểm tra ST_SRID, longitude và latitude.
- [ ] Đã xác thực geometry bằng ST_IsValid hoặc ST_Validate.
- [ ] Đã quyết định điểm trên biên được tính trong hay ngoài.
- [ ] Đã phân biệt ST_Contains với ST_Intersects và ST_Touches.
- [ ] Đã hiểu MBR là bounding rectangle, không phải hình dạng thật.
- [ ] Đã dùng MBR làm candidate filter khi có lợi.
- [ ] Đã xác minh candidate bằng exact predicate.
- [ ] Cột spatial index là NOT NULL và SRID-restricted.
- [ ] Đã kiểm tra EXPLAIN để xác nhận spatial index được sử dụng.
- [ ] Đã đo khoảng cách theo đơn vị có ý nghĩa.
- [ ] Đã chọn ST_Distance hoặc ST_Distance_Sphere theo độ chính xác cần thiết.
- [ ] Đã xác định tolerance theo mét hoặc đơn vị SRS, không dùng epsilon độ tùy ý.
- [ ] Đã kiểm thử điểm trong, biên, ngoài, gần biên và trong lỗ polygon.
- [ ] Đã kiểm thử polygon lõm để phát hiện MBR false positive.
- [ ] Đã kiểm thử SRID mismatch và tọa độ ngoài phạm vi.
- [ ] Đã quản lý phiên bản và nguồn dữ liệu ranh giới.

## 21. Nguyên tắc cần ghi nhớ

1. Geometry biểu diễn điểm, đường, vùng và các tập hình học.
2. SRID xác định hệ quy chiếu; không được coi mọi tọa độ là cùng một hệ.
3. SRID 4326 dùng geographic coordinates; cần kiểm soát axis order khi tạo WKT.
4. ST_SRID() chỉ thay nhãn SRID; ST_Transform() mới chuyển đổi tọa độ.
5. ST_Contains() không nhận point nằm đúng trên boundary.
6. ST_Intersects() nhận cả điểm trong và điểm trên boundary.
7. ST_Touches() giúp nhận diện trường hợp chỉ chạm biên.
8. MBR chỉ mô tả hình chữ nhật bao quanh; nó có thể trả false positive.
9. Dùng MBR để lọc ứng viên, rồi exact ST_* predicate để xác minh hình dạng.
10. Spatial index là R-tree; cột phải NOT NULL và SRID-restricted để optimizer sử dụng.
11. MySQL 9.7 dùng SRS của cột để tính bounding box phù hợp cho spatial index.
12. Geometry well-formed không đồng nghĩa geometry valid.
13. ST_IsValid() và ST_Validate() hỗ trợ kiểm tra topology.
14. ST_Distance() trên geographic SRS tính geodetic distance trên ellipsoid.
15. ST_Distance_Sphere() tính khoảng cách trên sphere và chỉ hỗ trợ Point/MultiPoint.
16. Sai số tọa độ phải được xử lý bằng tolerance có đơn vị và ý nghĩa nghiệp vụ.
17. Kiểm thử phải bao gồm điểm trong, điểm biên, điểm ngoài, điểm gần biên và hình học lõm/có lỗ.

## Tài liệu tham khảo chính thức

Các cú pháp và hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual**:

1. [Spatial Data Types](https://dev.mysql.com/doc/refman/9.7/en/spatial-type-overview.html): geometry types, SRID attribute và điều kiện spatial index.
2. [Spatial Reference System Support](https://dev.mysql.com/doc/refman/9.7/en/spatial-reference-systems.html): hệ quy chiếu, SRID và trục tọa độ.
3. [Functions That Create Geometry Values from WKT Values](https://dev.mysql.com/doc/refman/9.7/en/gis-wkt-functions.html): ST_GeomFromText(), axis-order và phạm vi longitude/latitude.
4. [Geometry Well-Formedness and Validity](https://dev.mysql.com/doc/refman/9.7/en/geometry-well-formedness-validity.html): well-formed geometry, validity, ST_IsValid() và ST_Validate().
5. [Spatial Relation Functions That Use Object Shapes](https://dev.mysql.com/doc/refman/9.7/en/spatial-relation-functions-object-shapes.html): ST_Contains(), ST_Intersects(), ST_Touches() và ST_Distance().
6. [Spatial Relation Functions That Use Minimum Bounding Rectangles](https://dev.mysql.com/doc/refman/9.7/en/spatial-relation-functions-mbr.html): MBRContains, MBRCovers, MBRIntersects và semantics boundary.
7. [Creating Spatial Indexes](https://dev.mysql.com/doc/refman/9.7/en/creating-spatial-indexes.html): R-tree, NOT NULL, SRID và cú pháp SPATIAL INDEX.
8. [Using Spatial Indexes](https://dev.mysql.com/doc/refman/9.7/en/using-spatial-indexes.html): dùng MBR predicates và EXPLAIN để kiểm tra spatial index.
9. [SPATIAL Index Optimization](https://dev.mysql.com/doc/refman/9.7/en/spatial-index-optimization.html): cách optimizer xử lý Cartesian/geographic SRID và yêu cầu SRID-restricted.
10. [Spatial Convenience Functions](https://dev.mysql.com/doc/refman/9.7/en/spatial-convenience-functions.html): ST_Distance_Sphere(), ST_IsValid() và giới hạn của các hàm tiện ích.