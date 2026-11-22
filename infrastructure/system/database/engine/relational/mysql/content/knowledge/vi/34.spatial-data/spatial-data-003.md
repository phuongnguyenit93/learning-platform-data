# Tạo dữ liệu từ WKT/WKB và kiểm tra cấu trúc hình học

MySQL cung cấp các kiểu dữ liệu không gian như POINT, LINESTRING, POLYGON và các kiểu MULTI*. Để đưa dữ liệu từ ứng dụng hoặc tệp GIS vào các cột này, hai định dạng trao đổi thường gặp là WKT (Well-Known Text) và WKB (Well-Known Binary). WKT biểu diễn hình học bằng văn bản dễ đọc; WKB biểu diễn cùng cấu trúc bằng dữ liệu nhị phân gọn hơn cho việc truyền và lưu trao đổi.

Trong module DATABASE_MYSQL, bài học này hướng dẫn tạo geometry bằng ST_GeomFromText và ST_GeomFromWKB, xuất dữ liệu bằng ST_AsText và ST_AsWKB, gắn đúng SRID và hiểu thứ tự trục tọa độ. Sau khi tạo dữ liệu, bạn sẽ kiểm tra loại hình học, số thành phần, tọa độ bao, số điểm và tính hợp lệ bằng các hàm không gian của MySQL.

## 1. Geometry, WKT và WKB

Geometry là đối tượng không gian có cấu trúc và hệ quy chiếu tọa độ. WKT và WKB là hai cách biểu diễn đối tượng đó:

| Định dạng | Đặc điểm | Khi thường dùng |
|---|---|---|
| WKT | Văn bản có tên kiểu hình học và tọa độ | Debug, log, nhập dữ liệu thủ công, trao đổi dễ đọc |
| WKB | Chuỗi byte nhị phân theo cấu trúc hình học | Truyền dữ liệu nhị phân giữa ứng dụng và database, trao đổi GIS |
| Geometry trong MySQL | Giá trị không gian được lưu trong cột kiểu spatial | Truy vấn và phân tích không gian trong database |

WKT/WKB không phải kiểu cột để khai báo thay cho POINT hay POLYGON. Chúng là định dạng đầu vào/đầu ra; cột trong MySQL vẫn khai báo bằng một kiểu geometry cụ thể hoặc kiểu tổng quát GEOMETRY.

Ví dụ cùng một điểm:

~~~text
POINT(10 20)
~~~

WKT có thể đọc trực tiếp là một điểm với hai tọa độ. WKB chứa mã kiểu, thứ tự byte và các giá trị tọa độ dưới dạng nhị phân; không nên tự tạo WKB bằng cách ghép chuỗi byte nếu chưa nắm chuẩn mã hóa.

## 2. Các kiểu hình học thường gặp

MySQL hỗ trợ các kiểu hình học cơ bản và kiểu tập hợp:

| Kiểu | Ý nghĩa | Ví dụ WKT |
|---|---|---|
| POINT | Một vị trí | POINT(10 20) |
| LINESTRING | Chuỗi điểm nối thành đường | LINESTRING(0 0, 5 5, 10 5) |
| POLYGON | Vùng có vòng ngoài và có thể có lỗ | POLYGON((0 0, 10 0, 10 10, 0 10, 0 0)) |
| MULTIPOINT | Nhiều điểm | MULTIPOINT((1 1), (2 2)) |
| MULTILINESTRING | Nhiều đường | MULTILINESTRING((0 0, 1 1), (2 2, 3 3)) |
| MULTIPOLYGON | Nhiều vùng polygon | MULTIPOLYGON(((0 0, 4 0, 4 4, 0 4, 0 0))) |
| GEOMETRYCOLLECTION | Tập hợp các geometry có thể khác kiểu | GEOMETRYCOLLECTION(POINT(1 1), LINESTRING(0 0, 2 2)) |

POINT có dimension 0, LINESTRING có dimension 1 và POLYGON có dimension 2. MULTI* gom nhiều đối tượng cùng kiểu; GEOMETRYCOLLECTION có thể chứa các kiểu khác nhau.

## 3. Cấu trúc WKT

WKT thường bắt đầu bằng tên kiểu geometry, theo sau là danh sách tọa độ hoặc danh sách thành phần. Một tọa độ hai chiều có hai số theo thứ tự trục mà hệ quy chiếu quy định.

Ví dụ POINT:

~~~text
POINT(106.70098 10.77689)
~~~

Ví dụ LINESTRING:

~~~text
LINESTRING(106.7000 10.7760, 106.7010 10.7770, 106.7020 10.7780)
~~~

Ví dụ POLYGON:

~~~text
POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))
~~~

Polygon có vòng ngoài; nếu có lỗ, thêm một vòng trong:

~~~text
POLYGON(
    (0 0, 10 0, 10 10, 0 10, 0 0),
    (2 2, 2 4, 4 4, 4 2, 2 2)
)
~~~

Mỗi vòng polygon phải khép kín: tọa độ cuối trùng tọa độ đầu. Một vòng thường cần ít nhất bốn vị trí tọa độ vì điểm đầu được lặp lại ở cuối. Vòng đầu là exterior ring; các vòng tiếp theo là interior ring (lỗ).

WKT dùng dấu phẩy để phân tách các điểm hoặc thành phần. Không đặt dấu phẩy giữa hai tọa độ của cùng một điểm. Chuỗi WKT sai cú pháp có thể bị constructor từ chối ngay khi phân tích.

## 4. Tạo geometry bằng ST_GeomFromText

ST_GeomFromText chuyển chuỗi WKT thành geometry:

~~~sql
ST_GeomFromText(wkt [, srid [, options]])
~~~

Tham số:

- wkt: văn bản WKT hợp lệ.
- srid: mã Spatial Reference System Identifier; nếu bỏ qua, geometry thường nhận SRID 0.
- options: tùy chọn phân tích, chẳng hạn axis-order cho hệ quy chiếu có thứ tự trục khác với dữ liệu nguồn.

Tạo một điểm Cartesian:

~~~sql
SET @point = ST_GeomFromText('POINT(10 20)');

SELECT
    ST_GeometryType(@point) AS geometry_type,
    ST_SRID(@point) AS srid,
    ST_AsText(@point) AS wkt;
~~~

Không truyền SRID làm geometry dùng SRID 0. SRID 0 thường biểu thị hệ Cartesian không xác định cụ thể; không dùng SRID 0 cho kinh độ/vĩ độ địa lý nếu cần các phép toán theo hệ địa lý.

Có thể tạo LINESTRING và POLYGON tương tự:

~~~sql
SET @route = ST_GeomFromText(
    'LINESTRING(0 0, 5 5, 10 5)',
    0
);

SET @area = ST_GeomFromText(
    'POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))',
    0
);

SELECT ST_AsText(@route), ST_AsText(@area);
~~~

Các ví dụ trên dùng tọa độ Cartesian để tập trung vào cấu trúc. Với dữ liệu địa lý, phải chọn SRID và thứ tự trục đúng với nguồn.

## 5. SRID xác định hệ quy chiếu tọa độ

SRID cho biết các tọa độ thuộc hệ tham chiếu nào. Hai geometry có cùng cặp số nhưng SRID khác nhau có thể biểu diễn các vị trí khác nhau vì hệ quy chiếu và đơn vị khác nhau.

Một số khái niệm:

- SRID 0 thường dùng cho Cartesian không gắn hệ tham chiếu địa lý cụ thể.
- SRID 4326 đại diện cho hệ địa lý WGS 84, thường gặp ở dữ liệu GPS.
- Các hệ chiếu phẳng khác có thể dùng đơn vị mét hoặc đơn vị theo định nghĩa SRS.

Không chỉ dựa vào con số tọa độ để suy ra SRID. Cần biết dữ liệu nguồn dùng hệ tọa độ nào, đơn vị nào và thứ tự trục nào.

Kiểm tra SRID:

~~~sql
SELECT
    ST_SRID(@point) AS point_srid,
    ST_SRID(@route) AS route_srid;
~~~

Khi lưu vào cột có ràng buộc SRID, geometry đầu vào phải có SRID tương ứng. Không gắn một SRID mới chỉ để vượt qua kiểm tra schema: thay đổi nhãn SRID không tự chuyển đổi tọa độ sang hệ quy chiếu mới. Nếu cần chuyển hệ tọa độ, phải dùng phép biến đổi tọa độ phù hợp như ST_Transform khi SRS và phiên bản hỗ trợ.

## 6. Thứ tự trục tọa độ và SRID 4326

Một lỗi phổ biến là nhầm thứ tự longitude/latitude. Theo định nghĩa trục của EPSG:4326, thứ tự trục là latitude rồi longitude. Nhiều API bản đồ và GeoJSON lại truyền longitude rồi latitude.

MySQL mặc định diễn giải tọa độ theo thứ tự trục do SRS quy định. Với dữ liệu WKT lấy từ nguồn dùng longitude-latitude, có thể chỉ định tùy chọn axis-order:

Tùy chọn axis-order trong các hàm GIS được hỗ trợ từ MySQL 8.0.3. Trên phiên bản cũ hơn, không giả định có thể truyền options như ví dụ dưới; hãy chuẩn hóa thứ tự tọa độ ở tầng ứng dụng và kiểm tra tài liệu đúng phiên bản đang chạy.

~~~sql
-- Theo thứ tự trục SRID 4326: latitude, longitude.
SET @point_lat_lon = ST_GeomFromText(
    'POINT(10.77689 106.70098)',
    4326
);

-- Nguồn cung cấp longitude trước, latitude sau.
SET @point_lon_lat = ST_GeomFromText(
    'POINT(106.70098 10.77689)',
    4326,
    'axis-order=long-lat'
);
~~~

Khi xuất WKT cho ứng dụng cần longitude-latitude:

~~~sql
SELECT ST_AsText(
    @point_lon_lat,
    'axis-order=long-lat'
) AS point_wkt;
~~~

Tùy chọn axis-order giúp diễn giải thứ tự tọa độ; nó không thay đổi hệ quy chiếu hoặc thực hiện phép chiếu. Cần thống nhất quy ước giữa ứng dụng, file GIS và database. Hãy kiểm tra một vài điểm đã biết trước khi nạp dữ liệu hàng loạt.

## 7. Lưu geometry vào bảng

Ví dụ bảng lưu điểm địa lý:

~~~sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    place_name VARCHAR(150) NOT NULL,
    location POINT NOT NULL SRID 4326,
    PRIMARY KEY (place_id)
) ENGINE=InnoDB;
~~~

Thuộc tính SRID 4326 ràng buộc geometry trong cột theo hệ tham chiếu đó. Cú pháp SRID-restricted spatial column được hỗ trợ từ MySQL 8.0.13. Với phiên bản cũ hơn, kiểm tra khả năng và cú pháp tương ứng trước khi áp dụng; không giả định mọi phiên bản đều thực thi cùng mức ràng buộc.

Chèn điểm bằng WKT:

~~~sql
INSERT INTO places (place_name, location)
VALUES (
    'Office',
    ST_GeomFromText(
        'POINT(106.70098 10.77689)',
        4326,
        'axis-order=long-lat'
    )
);
~~~

Đọc lại:

~~~sql
SELECT
    place_id,
    place_name,
    ST_SRID(location) AS srid,
    ST_AsText(location, 'axis-order=long-lat') AS location_wkt
FROM places;
~~~

Nếu cột được khai báo SRID 4326 nhưng đầu vào dùng SRID 0 hoặc một SRID khác, thao tác ghi sẽ không thỏa ràng buộc. Hãy tạo geometry với đúng SRID ngay từ constructor.

## 8. Tạo geometry từ WKB bằng ST_GeomFromWKB

WKB là dữ liệu nhị phân, không phải chuỗi WKT. Dùng ST_GeomFromWKB để phân tích:

~~~sql
ST_GeomFromWKB(wkb [, srid [, options]])
~~~

Ví dụ tạo WKB từ một geometry hiện có rồi đọc lại:

~~~sql
SET @original_geometry = ST_GeomFromText(
    'LINESTRING(0 0, 5 5, 10 5)',
    0
);

SET @wkb_value = ST_AsWKB(@original_geometry);

SET @geometry_from_wkb = ST_GeomFromWKB(
    @wkb_value,
    ST_SRID(@original_geometry)
);

SELECT ST_AsText(@geometry_from_wkb) AS round_trip_wkt;
~~~

ST_AsWKB trả binary WKB. Biến @wkb_value giữ chuỗi byte nhị phân để truyền lại cho ST_GeomFromWKB.

WKB chuẩn không mang theo SRID như metadata riêng của MySQL geometry. Vì vậy, khi trao đổi WKB, ứng dụng cần truyền SRID riêng hoặc lưu SRID trong metadata của giao thức. Đừng giả định ST_AsWKB đã đóng gói SRID vào payload.

## 9. Hiển thị WKB dưới dạng hexadecimal

WKB có thể chứa byte không in được. Để quan sát trong log hoặc tài liệu, dùng HEX:

~~~sql
SELECT HEX(ST_AsWKB(@original_geometry)) AS wkb_hex;
~~~

Nếu có chuỗi hex WKB hợp lệ và muốn chuyển về binary trước khi parse:

~~~sql
SET @wkb_hex = HEX(ST_AsWKB(@original_geometry));
SET @wkb_binary = UNHEX(@wkb_hex);

SELECT ST_AsText(
    ST_GeomFromWKB(@wkb_binary, 0)
) AS geometry_text;
~~~

HEX chỉ là cách biểu diễn byte để con người xem hoặc truyền qua kênh chỉ hỗ trợ text. Khi gọi ST_GeomFromWKB, phải đưa dữ liệu binary thực tế; không truyền chuỗi ký tự hex thô nếu chưa chuyển bằng UNHEX.

Trong ứng dụng, ưu tiên prepared statement và bind tham số binary để tránh chuyển đổi qua text không cần thiết. Kiểm tra encoding và kích thước payload khi nhận dữ liệu từ client.

## 10. Xuất geometry bằng ST_AsText và ST_AsWKB

Hai hàm xuất dữ liệu:

~~~sql
ST_AsText(geometry [, options])
ST_AsWKB(geometry [, options])
~~~

ST_AsText chuyển geometry thành WKT dễ đọc. ST_AsWKB chuyển thành WKB binary. Với SRID địa lý có thứ tự trục đặc biệt, có thể chỉ định axis-order khi xuất WKT/WKB để khớp giao thức trao đổi.

Ví dụ:

~~~sql
SELECT
    ST_AsText(location, 'axis-order=long-lat') AS wkt_value,
    HEX(ST_AsWKB(location, 'axis-order=long-lat')) AS wkb_hex
FROM places;
~~~

Kết quả WKT thuận tiện cho debug. Kết quả WKB phù hợp để ứng dụng nhận dữ liệu nhị phân. Nếu dùng HEX trong API, kích thước biểu diễn sẽ lớn hơn binary vì mỗi byte được đổi thành hai ký tự hexadecimal.

## 11. WKT/WKB round-trip

Round-trip là quy trình xuất geometry ra định dạng trao đổi rồi tạo lại geometry từ định dạng đó. Ví dụ WKT:

~~~sql
SET @source_geometry = ST_GeomFromText(
    'POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))',
    0
);

SET @source_wkt = ST_AsText(@source_geometry);

SET @copy_from_wkt = ST_GeomFromText(
    @source_wkt,
    ST_SRID(@source_geometry)
);

SELECT
    ST_AsText(@source_geometry) AS source_wkt,
    ST_AsText(@copy_from_wkt) AS copied_wkt,
    ST_IsValid(@copy_from_wkt) AS copied_is_valid;
~~~

Round-trip WKB:

~~~sql
SET @source_wkb = ST_AsWKB(@source_geometry);
SET @copy_from_wkb = ST_GeomFromWKB(
    @source_wkb,
    ST_SRID(@source_geometry)
);

SELECT
    ST_AsText(@copy_from_wkb) AS copied_wkt,
    ST_SRID(@copy_from_wkb) AS copied_srid;
~~~

Khi so sánh kết quả, hãy kiểm tra kiểu geometry, SRID, tọa độ và tính hợp lệ. Không dùng so sánh chuỗi WKT làm tiêu chí duy nhất cho tương đương hình học vì cách định dạng số hoặc thứ tự biểu diễn có thể khác.

## 12. Kiểm tra loại geometry và SRID

Các hàm cơ bản:

~~~sql
SELECT
    ST_GeometryType(location) AS geometry_type,
    ST_SRID(location) AS srid,
    ST_Dimension(location) AS dimension
FROM places;
~~~

- ST_GeometryType trả loại hình học như POINT, LINESTRING hoặc POLYGON.
- ST_SRID trả mã hệ quy chiếu.
- ST_Dimension trả dimension không gian của geometry.

Kiểm tra kiểu geometry trước khi dùng hàm chuyên biệt. Ví dụ ST_ExteriorRing và ST_NumInteriorRings áp dụng cho POLYGON; ST_NumPoints phù hợp với LINESTRING. Gọi hàm không đúng loại đối tượng có thể trả NULL hoặc phát lỗi tùy hàm và phiên bản.

## 13. Kiểm tra số điểm, số thành phần và vòng polygon

Với LINESTRING:

~~~sql
SET @route = ST_GeomFromText(
    'LINESTRING(0 0, 5 5, 10 5)',
    0
);

SELECT ST_NumPoints(@route) AS point_count;
~~~

Với POLYGON:

~~~sql
SET @area = ST_GeomFromText(
    'POLYGON((0 0, 10 0, 10 10, 0 10, 0 0),
             (2 2, 2 4, 4 4, 4 2, 2 2))',
    0
);

SELECT
    ST_NumInteriorRings(@area) AS hole_count,
    ST_AsText(ST_ExteriorRing(@area)) AS outer_ring;
~~~

Với GEOMETRYCOLLECTION:

~~~sql
SET @collection = ST_GeomFromText(
    'GEOMETRYCOLLECTION(POINT(1 1), LINESTRING(0 0, 2 2))',
    0
);

SELECT
    ST_GeometryType(@collection) AS collection_type,
    ST_NumGeometries(@collection) AS component_count,
    ST_GeometryType(ST_GeometryN(@collection, 1)) AS first_component_type;
~~~

ST_NumGeometries đếm số thành phần của collection hoặc multi-geometry; ST_GeometryN lấy thành phần theo vị trí bắt đầu từ 1. Các hàm kiểm tra cấu trúc giúp phát hiện tài liệu thiếu thành phần hoặc sai loại so với yêu cầu ứng dụng.

## 14. Kiểm tra envelope và phạm vi tọa độ

Envelope là hình chữ nhật bao nhỏ nhất song song với trục tọa độ, bao phủ geometry:

~~~sql
SELECT
    ST_AsText(ST_Envelope(@route)) AS route_envelope
;
~~~

Envelope hữu ích để kiểm tra nhanh phạm vi dữ liệu hoặc debug tọa độ bị lệch. Tuy nhiên, envelope không mô tả chính xác hình dạng đường/vùng; hai polygon khác nhau có thể có cùng envelope.

Với một geometry, có thể xuất envelope để kiểm tra min/max tọa độ bằng WKT. Đừng dùng envelope thay cho kiểm tra tính hợp lệ topology hoặc phép kiểm tra giao nhau chính xác.

## 15. Kiểm tra tính hợp lệ bằng ST_IsValid

WKT đúng cú pháp chưa chắc geometry đúng topology. Ví dụ một polygon có vòng tự cắt có thể được biểu diễn bằng WKT hợp lệ về mặt cú pháp nhưng không hợp lệ theo quy tắc hình học.

ST_IsValid kiểm tra tính hợp lệ:

~~~sql
SELECT ST_IsValid(@area) AS is_valid;
~~~

Kết quả thường là:

- 1: geometry hợp lệ.
- 0: geometry không hợp lệ.
- SQL NULL: đầu vào là SQL NULL.

Ví dụ polygon dạng bow-tie có vòng tự cắt:

~~~sql
SET @bow_tie = ST_GeomFromText(
    'POLYGON((0 0, 2 2, 0 2, 2 0, 0 0))',
    0
);

SELECT ST_IsValid(@bow_tie) AS is_valid;
~~~

Đây là ví dụ về cấu trúc polygon không hợp lệ về topology. Hãy kiểm tra kết quả trên phiên bản MySQL mục tiêu trước khi dùng làm test tự động, vì hành vi của các thao tác GIS có thể thay đổi theo phiên bản và loại SRS.

ST_IsValid là phép kiểm tra, không tự sửa dữ liệu. Nếu geometry không hợp lệ, cần xác định quy tắc nghiệp vụ để sửa hoặc từ chối dữ liệu ở bước ingest.

## 16. Quy tắc hợp lệ cơ bản của các geometry

Một số điều kiện cấu trúc quan trọng:

### POINT

- Có một vị trí tọa độ.
- Tọa độ phải phù hợp với miền tọa độ của SRS nếu dùng geographic SRS.

### LINESTRING

- Có ít nhất hai điểm.
- Các điểm được nối theo thứ tự trong danh sách.
- Một đường tự giao cắt không nên bị nhầm với polygon không hợp lệ; khái niệm đơn giản (simple) và hợp lệ (valid) là hai kiểm tra khác nhau.

### POLYGON

- Vòng ngoài phải khép kín.
- Mỗi vòng phải có đủ vị trí tọa độ để tạo ranh giới.
- Vòng trong phải nằm trong vùng của vòng ngoài.
- Các vòng không được cắt nhau theo cách vi phạm quy tắc topology.
- Vòng tự cắt như bow-tie là ví dụ polygon không hợp lệ.

### MULTIPOLYGON

- Mỗi thành phần là polygon hợp lệ.
- Các vùng thành phần phải tuân thủ quy tắc topology của MultiPolygon; phần bên trong các polygon không được chồng lấn theo cách làm đối tượng không hợp lệ.

### GEOMETRYCOLLECTION

- Mỗi thành phần phải là geometry hợp lệ.
- Các thành phần có thể khác kiểu geometry.
- Khi lưu vào cột có SRID cố định, các geometry thành phần phải phù hợp SRID của cột.

Các quy tắc này là nền tảng; dùng ST_IsValid trên dữ liệu thực tế thay vì chỉ dựa vào việc chuỗi WKT parse thành công.

## 17. Phân biệt lỗi cú pháp, lỗi SRID và lỗi topology

Ba nhóm lỗi thường bị gộp nhầm:

| Nhóm lỗi | Ví dụ | Nơi phát hiện |
|---|---|---|
| WKT/WKB không hợp lệ | Thiếu dấu ngoặc, sai cấu trúc byte, thiếu tọa độ | Constructor ST_GeomFromText/ST_GeomFromWKB |
| SRID hoặc tọa độ không phù hợp SRS | Cột yêu cầu 4326 nhưng geometry mang SRID khác; tọa độ ngoài miền SRS | Constructor, thao tác gán cột hoặc phép toán không gian |
| Topology không hợp lệ | Polygon tự cắt, vòng trong nằm ngoài vòng ngoài | ST_IsValid và các phép kiểm tra topology |

Không xử lý tất cả lỗi bằng cách thay SRID hoặc sửa chuỗi WKT. Cần xác định lỗi thuộc định dạng, hệ tọa độ hay cấu trúc hình học.

## 18. Quy trình ingest WKT/WKB an toàn

Một luồng nạp dữ liệu có thể thực hiện theo các bước:

1. Nhận biết định dạng đầu vào là WKT hay WKB.
2. Xác nhận hệ quy chiếu nguồn và SRID.
3. Xác định thứ tự trục; kiểm tra nguồn dùng latitude-longitude hay longitude-latitude.
4. Parse bằng ST_GeomFromText hoặc ST_GeomFromWKB với SRID/options phù hợp.
5. Kiểm tra ST_GeometryType và ST_SRID.
6. Kiểm tra cấu trúc bằng ST_NumPoints, ST_NumGeometries hoặc các hàm phù hợp với loại geometry.
7. Kiểm tra ST_IsValid.
8. Từ chối hoặc đưa dữ liệu lỗi vào vùng staging để xử lý; không âm thầm sửa SRID.
9. Ghi geometry hợp lệ vào cột có kiểu và SRID phù hợp.
10. Lưu metadata nguồn như thời điểm nhập, hệ quy chiếu và phiên bản quy trình nếu cần truy vết.

Với dữ liệu số lượng lớn, hãy nạp vào staging table trước, thống kê lỗi theo nhóm rồi mới chuyển dữ liệu hợp lệ sang bảng chính. Điều này giúp tránh một lô dữ liệu sai làm gián đoạn toàn bộ quy trình.

## 19. Prepared statement và dữ liệu WKB từ ứng dụng

Ứng dụng không nên nối chuỗi WKT/WKB trực tiếp vào SQL từ dữ liệu người dùng. Dùng prepared statement để bind tham số:

~~~sql
INSERT INTO places (place_name, location)
VALUES (
    ?,
    ST_GeomFromWKB(?, 4326)
);
~~~

Tham số thứ nhất là tên địa điểm; tham số thứ hai phải được bind dưới dạng binary WKB. Nếu payload nguồn dùng thứ tự trục khác mặc định của SRID, dùng tham số options phù hợp hoặc chuẩn hóa trước khi gửi.

Với WKT:

~~~sql
INSERT INTO places (place_name, location)
VALUES (
    ?,
    ST_GeomFromText(?, 4326, 'axis-order=long-lat')
);
~~~

Prepared statement tách dữ liệu khỏi cú pháp SQL và giúp tránh lỗi escape. Nó không thay thế việc kiểm tra SRID, kích thước payload và tính hợp lệ geometry.

## 20. Ví dụ kiểm tra dữ liệu sau khi nạp

Giả sử bảng places đã có dữ liệu:

~~~sql
SELECT
    place_id,
    place_name,
    ST_GeometryType(location) AS geometry_type,
    ST_SRID(location) AS srid,
    ST_IsValid(location) AS is_valid,
    ST_AsText(location, 'axis-order=long-lat') AS location_wkt
FROM places;
~~~

Nếu cột location được khai báo POINT SRID 4326, có thể kiểm tra thêm:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(ST_IsValid(location) = 1) AS valid_rows,
    SUM(ST_IsValid(location) = 0) AS invalid_rows,
    SUM(ST_SRID(location) <> 4326) AS wrong_srid_rows
FROM places;
~~~

Nếu cột đã có SRID restriction, wrong_srid_rows thường phải bằng 0 vì dữ liệu sai SRID bị từ chối khi ghi. Truy vấn thống kê vẫn hữu ích khi kiểm tra bảng cũ chưa có restriction hoặc dữ liệu được nhập từ quy trình khác.

## 21. Lỗi thường gặp khi tạo và kiểm tra geometry

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Constructor báo WKT không hợp lệ | Sai tên kiểu, dấu ngoặc hoặc dấu phẩy | Kiểm tra cú pháp WKT và từng vòng tọa độ |
| Geometry nằm sai vị trí bản đồ | Đảo latitude/longitude | Kiểm tra axis-order và dùng tùy chọn phù hợp |
| Ghi vào cột spatial bị lỗi SRID | SRID đầu vào không khớp ràng buộc cột | Tạo geometry với SRID đúng từ nguồn |
| WKB parse thất bại | Truyền chuỗi hex thay vì binary hoặc payload bị cắt | Dùng UNHEX cho hex text hoặc bind binary đúng độ dài |
| WKT parse được nhưng ST_IsValid trả 0 | Topology không hợp lệ | Sửa geometry theo quy tắc nghiệp vụ hoặc từ chối |
| Polygon không hợp lệ | Vòng không khép kín, tự cắt hoặc lỗ sai vị trí | Kiểm tra exterior/interior ring |
| ST_NumPoints trả NULL hoặc lỗi | Gọi hàm không đúng loại geometry | Kiểm tra ST_GeometryType trước |
| Kết quả WKB không kèm SRID mong đợi | WKB chuẩn không mang metadata SRID của MySQL | Truyền SRID riêng khi parse và trong giao thức |
| Gắn SRID mới nhưng vị trí vẫn sai | Đổi metadata không chuyển tọa độ | Dùng phép chuyển hệ tọa độ phù hợp |
| WKT round-trip khác chuỗi ban đầu | Khác cách format số hoặc thứ tự trục | So sánh cấu trúc, SRID và tọa độ theo quy tắc phù hợp |

## 22. Bài tập thực hành

1. Tạo POINT từ WKT và kiểm tra ST_GeometryType, ST_SRID, ST_AsText.
2. Tạo LINESTRING từ WKT và đếm điểm bằng ST_NumPoints.
3. Tạo POLYGON có một lỗ; kiểm tra ST_NumInteriorRings và ST_ExteriorRing.
4. Tạo GEOMETRYCOLLECTION gồm POINT và LINESTRING; đếm thành phần bằng ST_NumGeometries.
5. Xuất một geometry thành WKB, hiển thị HEX và parse lại bằng ST_GeomFromWKB.
6. Thực hiện round-trip WKT và WKB; so sánh loại geometry, SRID và kết quả ST_IsValid.
7. Tạo POINT SRID 4326 với axis-order mặc định và với axis-order=long-lat; xác nhận vị trí bằng dữ liệu đã biết.
8. Tạo bảng có cột POINT SRID 4326; thử ghi geometry SRID 0 và quan sát lỗi.
9. Tạo polygon dạng bow-tie; kiểm tra ST_IsValid và giải thích vì sao WKT parse thành công không đảm bảo topology hợp lệ.
10. Tạo một WKT polygon có vòng ngoài không khép kín; quan sát lỗi parse và phân biệt với lỗi topology.
11. Viết truy vấn thống kê số geometry hợp lệ, không hợp lệ và sai SRID trong bảng staging.
12. Thiết kế prepared statement nhận WKB binary từ ứng dụng và nêu rõ cách truyền SRID cùng thứ tự trục.

Bạn hoàn thành bài khi tạo được geometry từ WKT và WKB, giải thích được vai trò của SRID và axis order, xuất dữ liệu về hai định dạng trao đổi, đồng thời kiểm tra được loại, thành phần, phạm vi và tính hợp lệ của geometry trước khi lưu vào bảng nghiệp vụ. Parse thành công mới chỉ xác nhận định dạng đọc được; kiểm tra cấu trúc và hệ tọa độ mới giúp dữ liệu không gian đáng tin cậy.
