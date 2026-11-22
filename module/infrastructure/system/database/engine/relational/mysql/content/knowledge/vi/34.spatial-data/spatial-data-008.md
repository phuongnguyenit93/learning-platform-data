# Chuyển hệ tọa độ, kiểm tra tính hợp lệ và giới hạn theo phiên bản

Dữ liệu không gian (spatial data) mô tả vị trí, hình dạng và quan hệ hình học của các đối tượng như điểm giao hàng, tuyến đường, vùng phục vụ hoặc ranh giới hành chính. Trong MySQL, các giá trị này được lưu bằng kiểu dữ liệu hình học như POINT, LINESTRING, POLYGON và các kiểu MULTI/GEOMETRYCOLLECTION.

Một giá trị geometry không chỉ có tọa độ. Nó còn gắn với hệ quy chiếu không gian (Spatial Reference System - SRS), được nhận diện bằng SRID. Nếu hai hình học dùng hệ tọa độ khác nhau, phép đo khoảng cách hoặc phép kiểm tra giao nhau có thể sai hoặc bị MySQL từ chối. Việc đổi nhãn SRID cũng không giống chuyển đổi tọa độ; cần phân biệt rõ \`ST_SRID()\` và \`ST_Transform()\`.

Ngoài hệ tọa độ, dữ liệu còn phải hợp lệ về cấu trúc hình học. Một POLYGON có thể chứa tọa độ số hợp lệ nhưng vẫn sai topology, chẳng hạn vòng tự cắt. MySQL cung cấp các hàm kiểm tra như \`ST_IsValid()\`, nhưng kiểm tra hợp lệ không tự động sửa hình học. Quy trình nhập dữ liệu cần xác minh SRID, thứ tự trục, miền tọa độ, topology và giới hạn tính năng của phiên bản server.

Bài học thuộc phạm vi DATABASE_MYSQL: hiểu SRS/SRID, chuyển đổi hệ tọa độ, phân biệt gán SRID với transform, kiểm tra geometry, thiết kế cột SRID-restricted và spatial index, đồng thời xây quy trình migration an toàn giữa các phiên bản MySQL.

## 1. Geometry, SRS và SRID

Geometry biểu diễn hình dạng bằng tọa độ. SRS định nghĩa cách diễn giải các tọa độ đó trên Trái Đất hoặc trên một mặt phẳng. SRID (Spatial Reference System Identifier) là mã định danh SRS.

Ví dụ:

- EPSG:4326 là WGS 84, hệ tọa độ địa lý thường dùng cho longitude/latitude.
- EPSG:3857 là WGS 84 / Pseudo-Mercator, hệ tọa độ phẳng thường gặp trong bản đồ web.
- Các hệ UTM có SRID riêng theo múi và datum; chúng thường phù hợp hơn cho đo đạc cục bộ trong vùng tương ứng.

Một geometry có thể chứa cùng một cặp số nhưng ý nghĩa hoàn toàn khác tùy SRID. POINT(106.7 10.8) có thể được hiểu là kinh độ/vĩ độ nếu dùng hệ địa lý và thứ tự trục phù hợp; cùng cặp số đó trong hệ tọa độ phẳng có thể biểu thị một vị trí cách gốc tọa độ 106,7 đơn vị theo trục X và 10,8 đơn vị theo trục Y.

### 1.1. SRID 0

Nếu không chỉ định SRID, nhiều geometry constructor tạo geometry với SRID 0. SRID 0 biểu thị hệ tọa độ Cartesian mặc định không gắn với một hệ quy chiếu địa lý cụ thể.

Ví dụ:

~~~sql
SET @g0 = ST_GeomFromText('POINT(106.7 10.8)');

SELECT ST_SRID(@g0) AS srid;
~~~

Kết quả SRID là 0. Không nên xem những số này mặc nhiên là longitude/latitude hoặc dùng chúng để tính khoảng cách địa lý.

### 1.2. SRID không phải đơn vị đo

SRID xác định hệ quy chiếu và đơn vị/ý nghĩa trục theo định nghĩa SRS. Tùy hệ:
- Tọa độ địa lý thường biểu diễn góc, thường theo độ.
- Tọa độ chiếu thường biểu diễn khoảng cách, thường theo mét.
- Một số hệ tọa độ địa phương có đơn vị hoặc datum khác.

Không so sánh trực tiếp số đo từ hai SRS khác nhau. Chuyển đổi về một SRS chung trước khi thực hiện phép đo hoặc quan hệ hình học.

## 2. Xem danh mục hệ quy chiếu trong MySQL

MySQL cung cấp metadata SRS trong INFORMATION_SCHEMA.

~~~sql
SELECT
    SRS_ID,
    SRS_NAME,
    ORGANIZATION,
    ORGANIZATION_COORDSYS_ID,
    DEFINITION,
    DESCRIPTION
FROM information_schema.st_spatial_reference_systems
WHERE SRS_ID IN (0, 4326, 3857);
~~~

Các trường thường dùng:

| Trường | Ý nghĩa |
|---|---|
| SRS_ID | SRID của hệ quy chiếu |
| SRS_NAME | Tên hệ quy chiếu |
| ORGANIZATION | Tổ chức công bố, ví dụ EPSG |
| ORGANIZATION_COORDSYS_ID | Mã hệ tọa độ trong tổ chức |
| DEFINITION | Định nghĩa SRS, thường chứa thông tin WKT |
| DESCRIPTION | Mô tả |

Kiểm tra một SRID có tồn tại:

~~~sql
SELECT
    SRS_ID,
    SRS_NAME,
    ORGANIZATION,
    ORGANIZATION_COORDSYS_ID
FROM information_schema.st_spatial_reference_systems
WHERE SRS_ID = 4326;
~~~

Nếu không có hàng tương ứng, server không có định nghĩa SRS đó trong danh mục đang dùng. Không tự suy diễn rằng mọi mã EPSG mới nhất đều đã có sẵn trên mọi phiên bản MySQL.

### 2.1. Đọc axis order từ SRS definition

Định nghĩa SRS có thể chỉ rõ thứ tự trục. Với một số hệ địa lý, thứ tự trục chính thức không giống thứ tự longitude/latitude mà nhiều API bản đồ thường truyền.

Đây là nguồn gây lỗi phổ biến: dữ liệu nhập theo longitude-latitude nhưng MySQL diễn giải theo latitude-longitude, hoặc ngược lại. Luôn xác định:
- SRS đang dùng.
- Thứ tự trục theo định nghĩa SRS.
- Thứ tự trục trong file nguồn/API.
- Tùy chọn axis-order khi tạo geometry.

## 3. Thứ tự trục: latitude-longitude hay longitude-latitude?

Nhiều định dạng và thư viện bản đồ dùng thứ tự longitude, latitude. Tuy nhiên, định nghĩa EPSG:4326 có thứ tự trục latitude rồi longitude theo định nghĩa chính thức. MySQL tôn trọng axis order của SRS trong các thao tác WKT, trừ khi có tùy chọn chỉ định thứ tự khác.

Vì vậy, với MySQL cần phân biệt:

- \`axis-order=lat-long\`: số thứ nhất là latitude, số thứ hai là longitude.
- \`axis-order=long-lat\`: số thứ nhất là longitude, số thứ hai là latitude.
- Nếu không chỉ định, MySQL dùng thứ tự trục được định nghĩa trong SRS.

Ví dụ tạo điểm bằng longitude-latitude:

~~~sql
SET @hcm = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);

SELECT ST_SRID(@hcm) AS srid;
~~~

Ví dụ diễn giải WKT theo thứ tự trục mặc định của EPSG:4326:

~~~sql
SET @hcm_lat_long = ST_GeomFromText(
    'POINT(10.7769 106.7009)',
    4326
);
~~~

Hai ví dụ trên biểu diễn cùng một vị trí nếu thứ tự trục được dùng đúng.

### 3.1. Vì sao đảo trục có thể gây lỗi nghiêm trọng?

Nếu longitude 106.7 bị hiểu là latitude, giá trị latitude vượt miền hợp lệ [-90, 90]. MySQL có thể báo lỗi out-of-range cho SRS địa lý. Trong trường hợp cả hai số vẫn nằm trong miền hợp lệ, điểm có thể được lưu nhưng nằm ở một vị trí khác hoàn toàn, khó phát hiện hơn.

Ví dụ một điểm có hai tọa độ đều nằm trong [-90,90] có thể bị đảo trục mà không phát sinh lỗi. Do đó, chỉ kiểm tra miền số không đủ; cần kiểm thử vị trí trên bản đồ hoặc đối chiếu với dữ liệu chuẩn.

### 3.2. Tạo geometry từ WKT cần ghi rõ hợp đồng trục

Một quy ước nhập liệu nên xác định:
- API gửi longitude trước hay latitude trước.
- WKT constructor có dùng axis-order option không.
- Cột lưu SRID nào.
- Cách xuất WKT/GeoJSON để ứng dụng đọc lại.
- Bộ test cho các vị trí đã biết.

Không dựa vào thói quen của một thư viện khác để suy ra hành vi của MySQL. Hãy kiểm thử cả chiều ghi và chiều đọc.

## 4. Gán SRID khác với chuyển đổi tọa độ

Đây là phân biệt quan trọng nhất khi làm việc với spatial data.

### 4.1. ST_SRID(): gán hoặc đọc SRID

Dạng đọc:

~~~sql
SELECT ST_SRID(@hcm) AS srid;
~~~

Dạng gán SRID:

~~~sql
SET @raw_point = ST_GeomFromText('POINT(106.7009 10.7769)');

SET @tagged_point = ST_SRID(@raw_point, 4326);
~~~

\`ST_SRID(geometry, srid)\` trả về geometry có SRID được đặt theo tham số. Nó không biến đổi các giá trị tọa độ.

Nếu geometry ban đầu là POINT(106.7009 10.7769) trong SRID 0, gán SRID 4326 chỉ gắn nhãn rằng cặp số được hiểu theo SRS 4326. Điều đó chỉ đúng nếu tọa độ nguồn thực sự đã được biểu diễn theo hệ đó và đúng axis order.

Không dùng ST_SRID để chuyển dữ liệu từ UTM sang WGS 84. Làm vậy chỉ đổi metadata, không đổi tọa độ.

### 4.2. ST_Transform(): chuyển tọa độ giữa các SRS

\`ST_Transform(geometry, target_srid)\` thực hiện chuyển đổi tọa độ từ SRS hiện tại sang SRS đích, khi MySQL có đủ định nghĩa và phép biến đổi được hỗ trợ.

Ví dụ chuyển một điểm từ WGS 84 sang Web Mercator:

~~~sql
SET @point_4326 = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);

SET @point_3857 = ST_Transform(@point_4326, 3857);

SELECT
    ST_SRID(@point_4326) AS source_srid,
    ST_SRID(@point_3857) AS target_srid,
    ST_AsText(@point_3857) AS projected_point;
~~~

Tọa độ kết quả không còn là độ longitude/latitude; với EPSG:3857, các trục là tọa độ chiếu. Không diễn giải giá trị kết quả như độ.

### 4.3. Bảng so sánh

| Thao tác | SRID | Tọa độ | Dùng khi |
|---|---|---|---|
| ST_SRID(g) | Đọc SRID hiện tại | Giữ nguyên | Kiểm tra metadata |
| ST_SRID(g, n) | Gán SRID mới | Giữ nguyên | Nguồn đã đúng tọa độ nhưng thiếu/sai nhãn SRID và đã xác minh |
| ST_Transform(g, n) | Chuyển sang SRID đích | Tính lại tọa độ | Chuyển dữ liệu thật giữa hai hệ quy chiếu |

Nếu không chắc dữ liệu nguồn thuộc SRS nào, dừng migration và xác minh nguồn. Không có hàm nào có thể tự suy ra chính xác SRS chỉ từ một cặp tọa độ tùy ý.

## 5. Chuyển đổi dữ liệu hiện có theo quy trình an toàn

Giả sử bảng cũ lưu điểm giao hàng trong geometry SRID 0 nhưng ứng dụng thực tế đã ghi longitude/latitude theo WGS 84.

Trước khi chuyển:
1. Xác minh hệ tọa độ thực tế của dữ liệu nguồn.
2. Xác minh thứ tự trục.
3. Lấy một tập mẫu và đối chiếu vị trí trên bản đồ.
4. Kiểm tra miền longitude/latitude.
5. Sao lưu và thử trên staging.
6. Phân biệt dữ liệu đã có SRID đúng với dữ liệu chỉ bị gắn SRID sai.

Nếu dữ liệu thực sự là longitude/latitude WGS 84 nhưng đang mang SRID 0, có thể gắn nhãn SRID 4326 sau khi xác minh:

~~~sql
UPDATE delivery_location
SET position = ST_SRID(position, 4326)
WHERE ST_SRID(position) = 0;
~~~

Lệnh trên chỉ phù hợp nếu các tọa độ đang lưu đã đúng theo quy ước của SRS đích. Nó không chuyển đổi tọa độ.

Nếu dữ liệu nguồn là một hệ chiếu khác, ví dụ UTM zone cụ thể, cần gắn đúng SRID nguồn rồi transform sang SRID đích:

~~~sql
UPDATE delivery_location
SET position = ST_Transform(
    ST_SRID(position, 32648),
    4326
)
WHERE ST_SRID(position) = 0;
~~~

SRID 32648 ở đây chỉ là ví dụ UTM zone 48N; chỉ dùng nếu dữ liệu thật sự thuộc hệ đó. Không sao chép SRID ví dụ vào production nếu chưa xác minh datum, zone và phạm vi.

### 5.1. Không cập nhật trực tiếp cả bảng lớn mà chưa đo

Với bảng lớn:
- Ước lượng số hàng cần chuyển.
- Thử theo batch có khóa chính.
- Theo dõi undo/redo, binlog, replication lag và thời gian khóa.
- Lưu bản sao hoặc cột geometry cũ để đối chiếu trong giai đoạn chuyển.
- Xác minh một số điểm trước/sau bằng công cụ GIS độc lập.
- Có kế hoạch rollback hoặc phục hồi backup.

Một UPDATE transform hàng triệu geometry có thể tạo lượng ghi lớn và làm replica chậm. Chuyển đổi nên được triển khai như migration dữ liệu có kiểm soát.

## 6. Tạo cột spatial có SRID cố định

Trong MySQL 8.0, có thể khai báo cột geometry bị giới hạn ở một SRID cụ thể. Điều này giúp bảo đảm mọi giá trị trong cột dùng cùng hệ quy chiếu.

Ví dụ bảng điểm cửa hàng:

~~~sql
CREATE TABLE store_location (
    store_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    store_name VARCHAR(150) NOT NULL,
    position POINT NOT NULL SRID 4326,
    PRIMARY KEY (store_id),
    SPATIAL INDEX sx_store_position (position)
) ENGINE = InnoDB;
~~~

Cột \`position\` chỉ chấp nhận geometry có SRID 4326. Giá trị khác SRID bị từ chối thay vì âm thầm trộn nhiều hệ tọa độ trong cùng cột.

Thêm dữ liệu:

~~~sql
INSERT INTO store_location(store_name, position)
VALUES (
    'Cửa hàng trung tâm',
    ST_GeomFromText(
        'POINT(106.7009 10.7769)',
        4326,
        'axis-order=long-lat'
    )
);
~~~

Kiểm tra:

~~~sql
SELECT
    store_id,
    store_name,
    ST_SRID(position) AS srid,
    ST_AsText(position, 'axis-order=long-lat') AS position_wkt
FROM store_location;
~~~

SRID-restricted column hữu ích khi toàn bộ dữ liệu trong cột phải theo cùng SRS. Nếu ứng dụng cần lưu nhiều hệ tọa độ, nên chuyển về một SRS chuẩn trước khi ghi hoặc tách thành các cột/bảng có contract rõ ràng.

### 6.1. Spatial index và SRID restriction

Spatial index của InnoDB dùng cấu trúc R-tree để tìm kiếm theo minimum bounding rectangle (MBR). Với MySQL, để optimizer sử dụng spatial index hiệu quả, cột nên được khai báo SRID-restricted và NOT NULL. Kiểm tra điều kiện hỗ trợ trên đúng phiên bản trước khi triển khai.

Không coi spatial index như B-tree thông thường:
- R-tree phục vụ truy vấn không gian theo vùng bao.
- Spatial index giúp thu hẹp candidate.
- Phép kiểm tra hình học chính xác có thể cần bước kiểm tra tiếp theo.
- Một geometry có thể có MBR lớn dù hình dạng thật hẹp hoặc phức tạp.

## 7. Hệ địa lý và hệ chiếu: chọn đúng cho truy vấn

### 7.1. EPSG:4326

EPSG:4326 thường dùng để lưu vị trí địa lý WGS 84. Tọa độ biểu diễn góc, không phải mét. Dùng nó cho lưu trữ vị trí toàn cầu là phổ biến.

Tuy nhiên, phép tính khoảng cách/diện tích phải hiểu semantics của geographic SRS. Không tự lấy chênh lệch longitude/latitude rồi coi đó là khoảng cách mét.

### 7.2. EPSG:3857

EPSG:3857 thường dùng cho tile bản đồ web. Nó thuận tiện khi hiển thị bản đồ dạng Web Mercator, nhưng méo diện tích và khoảng cách tăng mạnh ở vĩ độ cao.

Không dùng EPSG:3857 như lựa chọn mặc định cho mọi phép đo chính xác. Với bài toán diện tích/khoảng cách địa phương, chọn projected CRS phù hợp khu vực hoặc dùng phép đo địa lý theo chức năng được MySQL hỗ trợ.

### 7.3. UTM và hệ chiếu địa phương

UTM chia Trái Đất thành các múi. Dữ liệu nằm trong một vùng địa lý cụ thể có thể phù hợp với UTM zone tương ứng để đo khoảng cách theo mét. Nhưng phải chọn đúng:
- Zone.
- Hemisphere.
- Datum.
- EPSG/SRID.
- Phạm vi sử dụng.

Không dùng một UTM zone cho dữ liệu trải rộng qua nhiều múi hoặc toàn cầu nếu không đánh giá sai số.

## 8. Chuyển đổi SRS và các lỗi có thể gặp

\`ST_Transform()\` có thể thất bại khi:
- SRID nguồn không có định nghĩa SRS.
- SRID đích không tồn tại.
- MySQL không có phép biến đổi cần thiết giữa hai SRS.
- Hình học chứa tọa độ ngoài miền hợp lệ.
- Geometry không hợp lệ hoặc không được hỗ trợ bởi phép biến đổi.
- Phiên bản server không hỗ trợ ST_Transform.
- Trục/đơn vị đầu vào bị hiểu sai.

Ví dụ kiểm tra SRID trước:

~~~sql
SELECT
    ST_SRID(position) AS srid,
    COUNT(*) AS row_count
FROM delivery_location
GROUP BY ST_SRID(position);
~~~

Nếu một cột chứa nhiều SRID, phải phân loại và xử lý từng nhóm. Không transform toàn bộ bằng một SRID nguồn giả định.

### 8.1. Không biến đổi từ SRID 0 theo phỏng đoán

SRID 0 không có định nghĩa địa lý cụ thể để MySQL biết tọa độ đang ở hệ nào. Không thể chuyển đúng từ SRID 0 sang 4326 chỉ bằng cách gọi ST_Transform; cần xác định SRS nguồn trước.

Nếu biết các tọa độ thực tế là longitude/latitude WGS 84 nhưng bị gắn SRID 0, có thể gắn nhãn 4326 sau khi kiểm chứng. Nếu biết dữ liệu thuộc hệ chiếu khác, gắn đúng SRID nguồn rồi transform.

## 9. Kiểm tra tính hợp lệ của geometry

Một geometry có thể được lưu dưới dạng WKB/WKT hợp lệ về cú pháp nhưng không hợp lệ theo quy tắc hình học.

Ví dụ:
- POLYGON có vòng không đóng.
- Vòng polygon tự cắt.
- Lỗ (interior ring) nằm ngoài vòng ngoài.
- Các vòng hoặc thành phần có quan hệ topology không hợp lệ.
- Geometry collection chứa thành phần không phù hợp với cấu trúc mong muốn.

Cần phân biệt:
- **Syntactic validity**: dữ liệu WKT/WKB có thể parse được.
- **Coordinate validity**: tọa độ nằm trong miền hợp lệ của SRS.
- **Topological validity**: hình dạng tuân theo quy tắc hình học.
- **Business validity**: hình dạng đáp ứng quy tắc nghiệp vụ, ví dụ vùng giao hàng phải nằm trong địa bàn cho phép.

Một polygon có thể hợp lệ theo OGC nhưng vẫn không hợp lệ về nghiệp vụ.

### 9.1. ST_IsValid()

Dùng \`ST_IsValid()\` để kiểm tra tính hợp lệ hình học:

~~~sql
SELECT
    area_id,
    ST_IsValid(service_area) AS is_valid
FROM service_area;
~~~

Kết quả:
- 1: geometry hợp lệ theo quy tắc kiểm tra của MySQL.
- 0: geometry không hợp lệ.
- NULL: đầu vào NULL.

Hàm kiểm tra không sửa geometry. Không diễn giải kết quả 1 là dữ liệu đã đúng với nghiệp vụ hoặc đúng vị trí địa lý; vẫn cần kiểm tra SRID, miền tọa độ và vùng bao.

### 9.2. Tìm các geometry không hợp lệ

~~~sql
SELECT area_id
FROM service_area
WHERE ST_IsValid(service_area) = 0;
~~~

Có thể thống kê:

~~~sql
SELECT
    COUNT(*) AS total_rows,
    SUM(ST_IsValid(service_area) = 1) AS valid_rows,
    SUM(ST_IsValid(service_area) = 0) AS invalid_rows
FROM service_area;
~~~

Nếu cột nullable, cần thống kê riêng các giá trị NULL. Không gộp NULL thành hợp lệ hoặc không hợp lệ khi báo cáo chất lượng.

### 9.3. Kiểm tra trước khi ghi

Ví dụ ứng dụng gửi polygon WKT:

~~~sql
SET @candidate = ST_GeomFromText(
    'POLYGON((
        106.60 10.70,
        106.80 10.70,
        106.80 10.90,
        106.60 10.90,
        106.60 10.70
    ))',
    4326,
    'axis-order=long-lat'
);

SELECT
    ST_SRID(@candidate) AS srid,
    ST_IsValid(@candidate) AS is_valid;
~~~

Nếu candidate hợp lệ và SRID đúng, có thể INSERT vào cột SRID-restricted. Trong ứng dụng, nên kiểm tra cả lỗi parse/constructor vì geometry có thể bị từ chối trước khi ST_IsValid được gọi.

## 10. Kiểm tra miền tọa độ và topology

Với EPSG:4326 theo quy ước longitude-latitude:
- Longitude thường nằm trong [-180, 180].
- Latitude thường nằm trong [-90, 90].

Nhưng MySQL có thể áp dụng axis order theo SRS. Nếu dùng thứ tự latitude-longitude, miền của giá trị thứ nhất là [-90, 90] và thứ hai là [-180, 180]. Không kiểm tra miền theo vị trí số mà bỏ qua axis order.

### 10.1. Kiểm tra điểm bằng ứng dụng

Với POINT:
- Kiểm tra SRID.
- Kiểm tra thứ tự trục.
- Kiểm tra miền giá trị.
- Đối chiếu một số vị trí mẫu với nguồn GPS/geocoder.
- Kiểm tra điểm có nằm trong khu vực nghiệp vụ hay không.

Không thể phát hiện mọi lỗi đảo trục chỉ bằng miền số, vì một cặp số có thể nằm trong miền hợp lệ theo cả hai thứ tự.

### 10.2. Kiểm tra polygon

Với POLYGON:
- Vòng ngoài phải đóng.
- Các vòng không được tự cắt theo quy tắc hợp lệ.
- Lỗ phải nằm đúng bên trong vùng ngoài.
- Các lỗ không được chồng lấn trái phép.
- Polygon phải nằm trong phạm vi địa lý nghiệp vụ.
- Geometry không vượt qua biên/antimeridian theo cách hệ thống chưa xử lý.

ST_IsValid kiểm tra topology theo quy tắc geometry, nhưng không biết một vùng có bao phủ đúng quận/huyện hoặc vùng phục vụ hay không. Quy tắc nghiệp vụ cần kiểm tra riêng.

## 11. Không nhầm ST_IsValid với sửa geometry

\`ST_IsValid()\` trả về kết quả kiểm tra. Nó không tự động:
- Đóng vòng polygon bị thiếu điểm cuối.
- Sửa self-intersection.
- Xóa lỗ sai.
- Đổi thứ tự tọa độ.
- Chuyển SRID.
- Di chuyển geometry về vùng hợp lệ.

Nếu dữ liệu không hợp lệ:
1. Giữ bản gốc để truy vết.
2. Xác định lỗi cú pháp, tọa độ hay topology.
3. Chọn công cụ sửa hình học phù hợp và có kiểm soát.
4. Lưu geometry đã sửa vào staging.
5. Kiểm tra ST_IsValid và đối chiếu hình dạng.
6. Xác minh SRID và vị trí.
7. Chỉ thay thế dữ liệu chính sau khi được chấp nhận.

Có thể dùng thư viện GIS chuyên dụng ở tầng ETL/ứng dụng để sửa geometry, nhưng phải ghi lại thuật toán, phiên bản và thay đổi hình dạng. Không âm thầm sửa polygon có thể làm thay đổi ranh giới pháp lý hoặc vùng nghiệp vụ.

## 12. Phép đo và quan hệ hình học yêu cầu cùng SRS

Các phép toán spatial thường yêu cầu hai geometry có cùng SRID. Nếu hai geometry khác SRID, MySQL có thể trả lỗi SRS mismatch.

Ví dụ:

~~~sql
SELECT ST_Distance(point_a, point_b)
FROM route_test;
~~~

Trước khi tính, kiểm tra:

~~~sql
SELECT
    ST_SRID(point_a),
    ST_SRID(point_b)
FROM route_test;
~~~

Nếu khác SRID, transform một geometry về SRS chung phù hợp rồi mới tính:

~~~sql
SELECT ST_Distance(
    ST_Transform(point_a, 4326),
    point_b
)
FROM route_test;
~~~

Ví dụ này chỉ đúng nếu phép transform từ SRID của point_a sang 4326 được hỗ trợ và point_b thực sự là 4326.

### 12.1. Đơn vị khoảng cách

Đơn vị của phép đo phụ thuộc SRS và hàm được dùng. Với Cartesian SRS, ST_Distance trả khoảng cách theo đơn vị tọa độ. Với geographic SRS, MySQL áp dụng semantics đo theo SRS, thường là mét đối với hệ địa lý có đơn vị góc được hỗ trợ.

Không lấy ST_Distance trên tọa độ độ rồi coi kết quả là mét. Đọc tài liệu hàm và SRS cụ thể, nhất là khi tính diện tích hoặc khoảng cách ở vùng rộng.

### 12.2. ST_Distance_Sphere

Đối với hai điểm địa lý, có thể dùng ST_Distance_Sphere để tính khoảng cách trên mặt cầu, kết quả tính theo mét:

~~~sql
SELECT ST_Distance_Sphere(
    ST_GeomFromText(
        'POINT(106.7009 10.7769)',
        4326,
        'axis-order=long-lat'
    ),
    ST_GeomFromText(
        'POINT(106.6800 10.8000)',
        4326,
        'axis-order=long-lat'
    )
) AS distance_meters;
~~~

Đây là khoảng cách xấp xỉ trên mặt cầu, không phải phép đo geodesic chính xác trên ellipsoid. Dùng cho bài toán gần đúng phù hợp; nếu yêu cầu đo đạc chính xác cao, cần chọn phương pháp và SRS phù hợp.

## 13. Spatial index và truy vấn theo vùng

Spatial index trong InnoDB sử dụng R-tree trên MBR (minimum bounding rectangle). MBR là hình chữ nhật nhỏ nhất bao quanh geometry. Nó giúp thu hẹp candidate nhưng có thể bao gồm vùng không thuộc hình dạng thực.

Ví dụ:

~~~sql
CREATE TABLE service_area (
    area_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    area_name VARCHAR(120) NOT NULL,
    boundary POLYGON NOT NULL SRID 4326,
    PRIMARY KEY (area_id),
    SPATIAL INDEX sx_service_area_boundary (boundary)
) ENGINE = InnoDB;
~~~

Tạo điểm cần kiểm tra:

~~~sql
SET @customer_point = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);
~~~

Tìm vùng có MBR chứa điểm:

~~~sql
SELECT area_id, area_name
FROM service_area
WHERE MBRContains(boundary, @customer_point);
~~~

MBRContains chỉ kiểm tra hình chữ nhật bao. Với polygon lõm hoặc có lỗ, một điểm có thể nằm trong MBR nhưng nằm ngoài polygon thật.

Để kiểm tra chính xác, dùng predicate hình học:

~~~sql
SELECT area_id, area_name
FROM service_area
WHERE ST_Contains(boundary, @customer_point);
~~~

Có thể kết hợp MBR prefilter và exact predicate:

~~~sql
SELECT area_id, area_name
FROM service_area
WHERE MBRContains(boundary, @customer_point)
  AND ST_Contains(boundary, @customer_point);
~~~

Optimizer có thể tận dụng spatial index cho các dạng truy vấn được hỗ trợ. Kiểm tra EXPLAIN trên phiên bản thực tế. Điều kiện MBR không thay thế phép kiểm tra chính xác.

### 13.1. Xem kế hoạch

~~~sql
EXPLAIN
SELECT area_id, area_name
FROM service_area
WHERE ST_Contains(boundary, @customer_point);
~~~

Kiểm tra:
- possible_keys và key.
- access type.
- rows ước lượng.
- Extra.
- Optimizer có sử dụng spatial index hay quét bảng.

Nếu không dùng index:
- Xác minh cột có SRID restriction và NOT NULL.
- Xác minh SRID hai geometry giống nhau.
- Xem predicate có được hỗ trợ để spatial range scan không.
- Kiểm tra bảng có đủ lớn để index có lợi không.
- Cập nhật thống kê khi cần.
- Thử MBR predicate phù hợp rồi xác nhận kết quả bằng exact predicate.

## 14. SRID restriction và migration schema

Khi thêm SRID restriction vào bảng cũ, dữ liệu hiện có phải thỏa điều kiện. Nếu bảng đang chứa nhiều SRID hoặc NULL, thay đổi có thể thất bại.

Trước khi ALTER:
~~~sql
SELECT
    ST_SRID(position) AS srid,
    COUNT(*) AS rows_per_srid
FROM store_location_legacy
GROUP BY ST_SRID(position);
~~~

Kiểm tra NULL:
~~~sql
SELECT COUNT(*) AS null_positions
FROM store_location_legacy
WHERE position IS NULL;
~~~

Sau khi xác định dữ liệu:
- Chuẩn hóa tất cả hàng về SRS đích.
- Sửa hoặc loại dữ liệu không hợp lệ theo quy trình nghiệp vụ.
- Tạo cột mới SRID-restricted nếu cần chuyển đổi online theo giai đoạn.
- Kiểm tra index và query plan sau migration.

Không ép SRID restriction trước khi hiểu dữ liệu cũ. Một bảng có dữ liệu trộn SRID có thể đang che giấu lỗi thiết kế cần giải quyết trước.

## 15. Kiểm tra tính tương thích theo phiên bản MySQL

Spatial functionality đã thay đổi đáng kể giữa các thế hệ MySQL.

| Nhóm tính năng | Ghi chú phiên bản |
|---|---|
| Kiểu dữ liệu geometry cơ bản và các hàm spatial | Có từ các phiên bản MySQL cũ; tập hàm và engine hỗ trợ đã mở rộng theo thời gian |
| InnoDB spatial index | Được hỗ trợ trong các bản MySQL 5.7; kiểm tra yêu cầu engine/cột theo bản cụ thể |
| SRS metadata và geographic SRS-aware behavior | Thuộc nhóm tính năng hiện đại của MySQL 8.0; khác với cách xử lý Cartesian/SRID 0 cũ |
| SRID-restricted columns | Kiểm tra phiên bản 8.0 cụ thể và cú pháp DDL trước khi triển khai |
| ST_Transform() | Có từ MySQL 8.0.13 |
| Spatial index optimization với SRID-restricted column | Khả năng optimizer sử dụng phụ thuộc phiên bản và điều kiện cột/predicate |
| CHECK constraint enforcement | MySQL thực thi CHECK từ 8.0.16; trước đó có khác biệt về enforcement |
| Các hàm GIS bổ sung và sửa lỗi | Có thể thay đổi giữa minor release 8.0 và các nhánh mới |

Kiểm tra server:

~~~sql
SELECT VERSION();
~~~

Kiểm tra engine và cột:

~~~sql
SHOW CREATE TABLE store_location;
SHOW INDEX FROM store_location;
~~~

Kiểm tra SRS tồn tại:

~~~sql
SELECT SRS_ID, SRS_NAME
FROM information_schema.st_spatial_reference_systems
WHERE SRS_ID IN (4326, 3857);
~~~

Không dựa vào cú pháp MySQL 8.4 để kết luận MySQL 5.7 hoặc một dịch vụ tương thích MySQL hỗ trợ giống hệt. Luôn kiểm tra tài liệu đúng phiên bản đang triển khai và thử migration trên staging.

### 15.1. ST_Transform và dữ liệu legacy

Nếu hệ thống đang ở phiên bản chưa có ST_Transform, không thể thay bằng ST_SRID để đạt cùng kết quả. Có thể:
- Thực hiện transform ở ETL/application bằng thư viện GIS có hỗ trợ CRS.
- Lưu dữ liệu vào bảng staging.
- Kiểm tra SRID, axis order và validity.
- Import geometry đã chuyển đổi vào MySQL.
- Xác minh vị trí mẫu và số lượng hàng.

Không tự viết công thức transform thủ công cho mọi hệ tọa độ. Phép chuyển có thể cần datum transformation, grid shift hoặc thông tin projection mà phép nhân/chia đơn giản không thể thay thế.

## 16. Kiểm soát chất lượng trước và sau chuyển đổi

Một báo cáo migration spatial nên có:

| Kiểm tra | Trước chuyển | Sau chuyển |
|---|---:|---:|
| Tổng số hàng | Ghi nhận | So sánh |
| Số hàng NULL | Ghi nhận | Theo contract |
| Phân bố SRID | Ghi nhận | Chỉ còn SRID mục tiêu nếu yêu cầu |
| Geometry hợp lệ | Đếm ST_IsValid | Đếm lại |
| Tọa độ ngoài miền | Đếm | Đếm lại |
| Điểm mẫu đã xác minh | Lưu danh sách | So sánh vị trí |
| Polygon mẫu | Lưu kết quả | So sánh diện tích/biên |
| Spatial index | Định nghĩa cũ | Xác nhận đã tạo |
| EXPLAIN | Lưu kế hoạch | Xác nhận access path |
| Replication lag | Baseline | Theo dõi khi migration |

Đối với điểm, có thể so sánh khoảng cách trước/sau sau khi đưa hai geometry về cùng SRS. Đối với polygon, có thể so sánh diện tích, envelope, số thành phần và kiểm tra topology bằng công cụ GIS phù hợp.

Không chỉ so sánh WKT text vì cùng một hình học có thể được serialize khác thứ tự ring/vertex mà vẫn biểu diễn cùng hình dạng.

## 17. Các lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| ST_SRID(g, 4326) chuyển tọa độ sang WGS 84 | Hàm chỉ đổi SRID, giữ nguyên tọa độ | Dùng ST_Transform khi biết SRS nguồn |
| SRID 0 mặc nhiên là longitude/latitude | SRID 0 là Cartesian mặc định | Xác minh SRS nguồn trước khi gắn nhãn |
| EPSG:4326 luôn dùng longitude trước trong MySQL | MySQL tôn trọng axis order SRS nếu không override | Dùng axis-order rõ ràng |
| Hai cặp tọa độ cùng số nghĩa là cùng vị trí | SRID và axis order có thể khác | So sánh sau khi đưa về cùng SRS |
| ST_Transform hoạt động trên mọi SRID | Cần SRS và phép chuyển được hỗ trợ | Kiểm tra danh mục SRS và version |
| Có thể tính khoảng cách độ rồi đổi thành mét bằng hằng số | Longitude scale phụ thuộc vĩ độ và phép đo địa lý phức tạp | Dùng hàm/SRS đo phù hợp |
| EPSG:3857 phù hợp cho mọi phép đo | Web Mercator méo khoảng cách/diện tích | Dùng projected CRS cục bộ hoặc phép đo địa lý phù hợp |
| ST_IsValid sửa polygon | Hàm chỉ kiểm tra validity | Sửa qua pipeline GIS có kiểm soát |
| Geometry parse được thì chắc chắn hợp lệ | Cú pháp và topology khác nhau | Dùng ST_IsValid và validation nghiệp vụ |
| MBRContains là phép kiểm tra polygon chính xác | MBR là hình chữ nhật bao | Kết hợp exact predicate như ST_Contains |
| Spatial index hoạt động với mọi geometry column | SRID restriction, NOT NULL và predicate ảnh hưởng optimizer | Kiểm tra DDL và EXPLAIN |
| Có thể trộn SRID trong một cột rồi so sánh | Spatial operation có thể báo SRS mismatch | Chuẩn hóa SRID hoặc tách schema |
| Transform cả bảng không có rủi ro vận hành | Có thể tạo write amplification và replication lag | Batch, staging, backup và theo dõi |
| MySQL 5.7 hỗ trợ mọi tính năng GIS 8.0 | Tính năng thay đổi theo phiên bản | Kiểm tra VERSION và manual tương ứng |
| Thay DDL spatial là transaction có thể rollback | DDL có thể implicit commit | Triển khai migration riêng |

## 18. Quy trình xử lý dữ liệu không gian an toàn

1. Xác định kiểu geometry và ý nghĩa nghiệp vụ của từng cột.
2. Xác định SRS thật của dữ liệu nguồn, không chỉ đọc SRID đang lưu.
3. Xác định axis order của nguồn và của MySQL.
4. Kiểm tra SRID có trong INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS.
5. Kiểm tra phân bố SRID hiện tại.
6. Kiểm tra NULL, tọa độ ngoài miền và ST_IsValid.
7. Chọn SRS đích phù hợp cho lưu trữ, hiển thị hoặc đo lường.
8. Nếu chỉ thiếu nhãn SRID và tọa độ đã đúng, dùng ST_SRID sau khi xác minh.
9. Nếu hệ tọa độ thực sự khác, dùng ST_Transform hoặc ETL GIS tương ứng.
10. Không dùng SRID 0 làm nguồn transform khi chưa biết hệ tọa độ.
11. Tạo cột SRID-restricted và NOT NULL nếu mô hình yêu cầu một SRS duy nhất.
12. Tạo spatial index trên cột phù hợp.
13. Kiểm tra predicate MBR và exact spatial predicate.
14. Chạy EXPLAIN và benchmark với dữ liệu đại diện.
15. Migration theo batch/staging, theo dõi binlog, replica lag và lock.
16. Đối chiếu điểm/polygon mẫu bằng nguồn độc lập.
17. Ghi lại phiên bản MySQL, SRID, axis order, pipeline và thời điểm migration.
18. Chỉ chuyển ứng dụng sang đọc cột mới sau khi kiểm tra chất lượng đạt yêu cầu.

## 19. Bài tập thực hành

### Bài 1: Đọc SRID

Tạo geometry POINT không khai báo SRID. Dùng ST_SRID kiểm tra kết quả. Giải thích SRID 0 khác EPSG:4326 như thế nào.

### Bài 2: Axis order

Tạo một điểm ở TP.HCM bằng WKT longitude-latitude với axis-order=long-lat. Tạo một điểm tương đương theo axis order mặc định của EPSG:4326. So sánh vị trí sau khi xuất WKT.

### Bài 3: Gán SRID và transform

Tạo geometry SRID 0 có tọa độ đã biết thuộc WGS 84. Dùng ST_SRID gắn nhãn 4326. Sau đó transform sang 3857. So sánh tọa độ trước/sau và giải thích vì sao hai thao tác khác nhau.

### Bài 4: Danh mục SRS

Truy vấn INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS cho 4326 và 3857. Đọc ORGANIZATION, SRS_NAME và DEFINITION. Xác định axis order của SRS.

### Bài 5: SRID-restricted column

Tạo bảng POINT NOT NULL SRID 4326 và spatial index. Thử insert geometry SRID 0 và một SRID khác. Ghi lại lỗi.

### Bài 6: Geometry validity

Tạo một POLYGON hợp lệ và một polygon tự cắt. Dùng ST_IsValid để kiểm tra. Phân biệt lỗi parse với lỗi topology.

### Bài 7: Spatial index

Tạo bảng vùng dịch vụ có POLYGON SRID 4326. Chạy MBRContains và ST_Contains. So sánh kết quả trên điểm nằm trong MBR nhưng ngoài polygon lõm.

### Bài 8: SRS mismatch

Tạo hai geometry có SRID khác nhau rồi thử ST_Distance/ST_Intersects. Ghi lại lỗi. Transform một geometry về cùng SRS và chạy lại.

### Bài 9: Kiểm tra migration

Tạo bảng legacy chứa nhiều SRID hoặc SRID 0. Viết truy vấn thống kê theo SRID và validity. Lập kế hoạch chuyển dữ liệu sang một SRID chuẩn mà không ghi đè dữ liệu gốc.

### Bài 10: Đo khoảng cách

Tính ST_Distance trên Cartesian geometry và ST_Distance_Sphere trên hai điểm địa lý. So sánh đơn vị và sai số của phép đo mặt cầu.

### Bài 11: Version compatibility

Kiểm tra VERSION() trên server lab. Xác minh ST_Transform, SRID-restricted column và spatial index optimizer có được hỗ trợ. Viết migration tương thích cho server cũ bằng ETL ngoài database nếu cần.

### Bài 12: Báo cáo chất lượng spatial

Tạo báo cáo gồm tổng hàng, SRID distribution, NULL, invalid geometry, tọa độ ngoài miền, index definition, EXPLAIN và điểm kiểm chứng mẫu. Đề xuất điều kiện chấp nhận migration.

## 20. Checklist trước khi triển khai

- [ ] Đã xác định SRS thật của dữ liệu, không suy ra chỉ từ SRID đang lưu.
- [ ] Đã phân biệt SRID 0 với hệ địa lý có định nghĩa.
- [ ] Đã kiểm tra SRS trong INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS.
- [ ] Đã xác định axis order của nguồn và của MySQL.
- [ ] Đã dùng axis-order rõ ràng khi WKT/API có thứ tự khác SRS.
- [ ] Đã phân biệt ST_SRID với ST_Transform.
- [ ] Không dùng ST_SRID để thay thế phép chuyển tọa độ.
- [ ] Đã kiểm tra miền tọa độ và đơn vị đo.
- [ ] Đã kiểm tra ST_IsValid và validation nghiệp vụ.
- [ ] Đã có quy trình sửa geometry không hợp lệ và giữ bản gốc.
- [ ] Đã chuẩn hóa SRID trước khi thực hiện phép spatial giữa hai geometry.
- [ ] Đã chọn SRS phù hợp cho hiển thị và đo lường.
- [ ] Đã hiểu EPSG:3857 có biến dạng và không mặc định dùng cho đo chính xác.
- [ ] Đã khai báo SRID restriction/NOT NULL khi cần.
- [ ] Đã tạo spatial index và xác minh bằng EXPLAIN.
- [ ] Đã phân biệt MBR predicate với exact spatial predicate.
- [ ] Đã kiểm tra hành vi DDL và giới hạn phiên bản.
- [ ] Đã thử migration trên staging và có backup.
- [ ] Đã theo dõi write amplification, lock và replication lag.
- [ ] Đã đối chiếu vị trí/hình dạng mẫu bằng công cụ GIS độc lập.
- [ ] Đã lưu lại phiên bản MySQL, SRS, axis order và quy trình chuyển đổi.

## 21. Kết luận

Một geometry chỉ có ý nghĩa khi tọa độ, SRID, SRS và axis order được hiểu thống nhất. \`ST_SRID()\` dùng để đọc hoặc gắn nhãn SRID nhưng không thay đổi tọa độ; \`ST_Transform()\` mới thực hiện phép chuyển tọa độ khi MySQL hỗ trợ SRS nguồn và đích. Đặc biệt với EPSG:4326, phải xác định rõ latitude-longitude hay longitude-latitude để tránh đảo trục.

Kiểm tra \`ST_IsValid()\` giúp phát hiện geometry sai topology, nhưng không sửa dữ liệu và không thay thế validation nghiệp vụ. Spatial index R-tree hỗ trợ tìm candidate theo MBR; phép kiểm tra chính xác như ST_Contains vẫn cần thiết khi hình dạng phức tạp. Cột SRID-restricted, NOT NULL và spatial index giúp dữ liệu nhất quán hơn và tạo điều kiện cho optimizer sử dụng index.

Trước khi migration, hãy thống kê SRID, xác minh nguồn, kiểm tra validity, thử transform trên staging, đối chiếu vị trí mẫu và đo ảnh hưởng vận hành. Tính năng GIS thay đổi theo phiên bản; luôn kiểm tra VERSION(), SRS metadata và tài liệu đúng bản MySQL triển khai.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Spatial Data Types](https://dev.mysql.com/doc/refman/8.4/en/spatial-types.html)
- [MySQL 8.4 Reference Manual – Spatial Reference System Support](https://dev.mysql.com/doc/refman/8.4/en/spatial-reference-systems.html)
- [MySQL 8.4 Reference Manual – Spatial Reference System Functions](https://dev.mysql.com/doc/refman/8.4/en/spatial-relation-functions.html)
- [MySQL 8.4 Reference Manual – Geometry Constructors](https://dev.mysql.com/doc/refman/8.4/en/gis-geometry-construction-functions.html)
- [MySQL 8.4 Reference Manual – Geometry Property Functions](https://dev.mysql.com/doc/refman/8.4/en/gis-general-property-functions.html)
- [MySQL 8.4 Reference Manual – Spatial Convenience Functions](https://dev.mysql.com/doc/refman/8.4/en/spatial-convenience-functions.html)
- [MySQL 8.4 Reference Manual – Spatial Relation Functions](https://dev.mysql.com/doc/refman/8.4/en/spatial-relation-functions.html)
- [MySQL 8.4 Reference Manual – Spatial Index Optimization](https://dev.mysql.com/doc/refman/8.4/en/optimizing-spatial-analysis.html)
- [MySQL 8.4 Reference Manual – INFORMATION_SCHEMA ST_SPATIAL_REFERENCE_SYSTEMS](https://dev.mysql.com/doc/refman/8.4/en/information-schema-st-spatial-reference-systems-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Spatial Indexes](https://dev.mysql.com/doc/refman/8.4/en/innodb-spatial-indexes.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)

