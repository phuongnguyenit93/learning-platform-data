# Cartesian/geographic spatial reference system và SRID

Dữ liệu không gian chỉ có ý nghĩa khi hệ tọa độ của nó được xác định rõ. Hai giá trị POINT có cùng cặp số nhưng có thể biểu diễn hai vị trí hoàn toàn khác nhau nếu một giá trị là kinh độ/vĩ độ còn giá trị kia là mét trên mặt phẳng chiếu. MySQL gắn một Spatial Reference System (SRS) với mỗi geometry thông qua Spatial Reference System Identifier (SRID). SRID cho MySQL biết cách diễn giải trục tọa độ, đơn vị và mô hình hình học của dữ liệu.

Hai nhóm SRS cần phân biệt là Cartesian và geographic. Cartesian mô tả tọa độ trên mặt phẳng; geographic mô tả vị trí trên bề mặt Trái Đất theo hệ tọa độ địa lý. SRID 0 là hệ Cartesian mặc định của MySQL khi geometry không được gắn SRS cụ thể. EPSG:4326 thường được dùng cho WGS 84 latitude/longitude; EPSG:3857 là hệ chiếu Web Mercator thường gặp trong bản đồ web. Các hệ này không thể thay thế lẫn nhau chỉ bằng cách đổi nhãn SRID.

Trong module DATABASE_MYSQL, bạn cần chọn SRS phù hợp với nguồn dữ liệu và phép tính, xác định thứ tự trục rõ ràng, lưu geometry với SRID nhất quán, và phân biệt thao tác gán SRID với chuyển đổi tọa độ. Một SRID sai có thể khiến truy vấn không gian trả kết quả sai dù SQL chạy không báo lỗi.

Các ví dụ DDL và truy vấn trong bài hướng tới MySQL 8.0.13 trở lên để sử dụng SRID restriction, thứ tự trục tường minh và ST_Transform(). Với phiên bản cũ hơn, kiểm tra tính năng thực tế trước khi dùng cú pháp tương ứng.

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích SRS, SRID, EPSG code và vai trò của metadata tọa độ.
- Phân biệt Cartesian SRS với geographic SRS.
- Hiểu SRID 0 và rủi ro khi dùng nó cho dữ liệu địa lý thực.
- Chọn SRID phù hợp cho longitude/latitude, dữ liệu bản đồ và phép đo cục bộ.
- Tra cứu SRS được MySQL hỗ trợ trong INFORMATION_SCHEMA.
- Tạo geometry với SRID tường minh bằng WKT.
- Kiểm tra SRID, kiểu geometry, thứ tự trục và phạm vi tọa độ.
- Phân biệt ST_SRID() dùng để gán nhãn với ST_Transform() dùng để đổi hệ tọa độ.
- Thiết kế cột geometry có SRID restriction và spatial index.
- Hiểu giới hạn của MBR predicate và cách kết hợp bộ lọc gần đúng với phép kiểm tra chính xác.
- Xây dựng quy trình nhập, chuẩn hóa, kiểm tra và chuyển đổi dữ liệu không gian.

## 1. Spatial Reference System là gì?

Spatial Reference System (SRS) là định nghĩa toán học và metadata mô tả cách diễn giải tọa độ. Tùy hệ, định nghĩa có thể mô tả:

- Loại hệ tọa độ: Cartesian (mặt phẳng) hay geographic (trái đất).
- Trục tọa độ và thứ tự trục.
- Đơn vị đo, ví dụ degree hoặc metre.
- Datum, ellipsoid và phép chiếu nếu có.
- Các tham số cần thiết để chuyển đổi sang hệ tọa độ khác.

SRID là mã định danh của một SRS trong MySQL. Một geometry mang SRID cho biết tọa độ của nó phải được hiểu theo SRS nào. SRID không phải một con số trang trí và cũng không tự sửa các tọa độ đang có.

Ví dụ, cặp số (106.7, 10.8) có thể được hiểu là longitude 106.7 độ và latitude 10.8 độ trong một geographic SRS. Nếu lại gắn nó với một projected SRS có đơn vị metre, MySQL sẽ hiểu các con số theo định nghĩa của hệ chiếu đó. Việc gắn nhầm SRID làm sai ý nghĩa dữ liệu.

## 2. Cartesian và geographic SRS

### 2.1. Cartesian: hình học trên mặt phẳng

Cartesian SRS mô tả vị trí bằng các trục phẳng, thường là X và Y. Các phép toán hình học được thực hiện theo hình học phẳng:

- Tọa độ dùng đơn vị tuyến tính của SRS, chẳng hạn metre hoặc foot nếu hệ định nghĩa đơn vị đó.
- Khoảng cách là khoảng cách phẳng trong hệ tọa độ.
- Diện tích là diện tích phẳng theo bình phương đơn vị tuyến tính.
- Không tự tính đến độ cong của Trái Đất.

SRID 0 của MySQL là Cartesian SRS mặc định và không gắn một đơn vị địa lý cụ thể. Nó phù hợp với dữ liệu mặt bằng, sơ đồ trong nhà, bản vẽ kỹ thuật hoặc hệ tọa độ cục bộ khi ứng dụng tự quy định đơn vị. Không nên dùng SRID 0 cho kinh độ/vĩ độ thực rồi mong các phép tính hiểu được khoảng cách trên Trái Đất.

Một projected SRS như EPSG:3857 cũng có tọa độ phẳng, thường được biểu diễn bằng metre. Tuy nhiên, metre trong một phép chiếu bản đồ không có nghĩa mọi khoảng cách/diện tích đều chính xác trên mặt đất. Web Mercator có biến dạng tăng theo vĩ độ; nó chủ yếu hữu ích cho hiển thị bản đồ web.

### 2.2. Geographic: tọa độ trên Trái Đất

Geographic SRS biểu diễn vị trí theo kinh độ/vĩ độ hoặc các trục địa lý được SRS định nghĩa. Tọa độ thường là góc, ví dụ degree:

- Longitude mô tả vị trí đông/tây.
- Latitude mô tả vị trí bắc/nam.
- Giá trị latitude nằm trong phạm vi địa lý hợp lệ của hệ; với WGS 84 thường là -90 đến +90 độ.
- Longitude của WGS 84 thường nằm trong phạm vi -180 đến +180 độ.

Phép toán geographic cần xét mô hình ellipsoid và độ cong Trái Đất. Với geographic SRS được MySQL hỗ trợ, các hàm như ST_Distance() trả khoảng cách theo metre và ST_Area() trả diện tích theo square metre. Đây là khác biệt quan trọng so với geometry trong SRID 0, nơi đơn vị chỉ là đơn vị tọa độ do ứng dụng quy ước.

### 2.3. Bảng so sánh

| Tiêu chí | Cartesian SRS | Geographic SRS |
|---|---|---|
| Mô hình | Mặt phẳng | Bề mặt Trái Đất |
| Tọa độ thường gặp | X/Y | Longitude/latitude hoặc trục địa lý theo định nghĩa |
| Đơn vị tọa độ | Đơn vị tuyến tính của SRS | Đơn vị góc, thường là degree |
| Distance | Đơn vị tuyến tính của SRS; SRID 0 không có đơn vị địa lý | Metre với geographic SRS được hỗ trợ |
| Area | Bình phương đơn vị tuyến tính | Square metre với geographic SRS được hỗ trợ |
| Dùng cho | Mặt bằng, bản vẽ, hệ chiếu phẳng | Vị trí địa lý toàn cầu |
| Rủi ro chính | Dùng dữ liệu degree như tọa độ phẳng | Nhầm thứ tự trục, datum hoặc phạm vi tọa độ |

Không có một SRS tốt nhất cho mọi tình huống. Hãy chọn hệ theo mục tiêu: lưu vị trí toàn cầu, tính khoảng cách địa lý, đo đạc cục bộ hay hiển thị bản đồ.

## 3. SRID 0, EPSG và các mã thường gặp

### 3.1. SRID 0

Nếu tạo geometry mà không chỉ định SRID, MySQL thường gán SRID 0. Đây là Cartesian SRS mặc định. Hai geometry cùng SRID 0 có thể thực hiện các phép toán Cartesian, nhưng MySQL không thể suy ra chúng là longitude/latitude, metre hay feet.

Ví dụ:

~~~sql
SET @local_point = ST_GeomFromText('POINT(12.5 8.25)');

SELECT
    ST_SRID(@local_point) AS srid,
    ST_AsText(@local_point) AS wkt;
~~~

Geometry trên mang SRID 0 vì không truyền SRID. Hai con số 12.5 và 8.25 chỉ có ý nghĩa theo quy ước của ứng dụng.

### 3.2. EPSG code

EPSG là hệ thống đăng ký các định nghĩa tọa độ và phép tham chiếu. MySQL tích hợp một danh mục SRS, trong đó nhiều SRID tương ứng với mã EPSG quen thuộc. Không nên giả định mọi SRID trong mọi hệ thống đều là EPSG code; hãy kiểm tra organization và organization coordinate-system ID trong danh mục MySQL.

Một số hệ thường gặp:

| SRID | Tên thường dùng | Loại | Trường hợp phổ biến |
|---:|---|---|---|
| 0 | MySQL default Cartesian | Cartesian | Dữ liệu phẳng/cục bộ không có SRS địa lý |
| 4326 | WGS 84 | Geographic 2D | Longitude/latitude toàn cầu |
| 3857 | WGS 84 / Pseudo-Mercator | Projected Cartesian | Hiển thị bản đồ web |

EPSG:4326 không phải hệ tọa độ phẳng. EPSG:3857 là hệ chiếu phẳng được xây dựng từ dữ liệu địa lý. Không ghi longitude/latitude trực tiếp vào cột SRID 3857 nếu chưa chuyển đổi tọa độ.

### 3.3. Tra cứu danh mục SRS của MySQL

MySQL cung cấp INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS để tra cứu các hệ tọa độ được cài đặt:

~~~sql
SELECT
    SRS_ID,
    SRS_NAME,
    ORGANIZATION,
    ORGANIZATION_COORDSYS_ID,
    DEFINITION
FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
WHERE SRS_ID IN (4326, 3857);
~~~

Các cột cho biết ID trong MySQL, tên hệ, tổ chức định nghĩa, ID trong tổ chức đó và định nghĩa SRS. Có thể đọc DEFINITION để xác nhận loại hệ, đơn vị và trục tọa độ. Không cần sao chép toàn bộ định nghĩa vào ứng dụng nếu chỉ cần tra cứu; hãy quản lý SRID được chọn như một phần của hợp đồng dữ liệu.

SRID 0 là hệ mặc định đặc biệt của MySQL; không nên phụ thuộc vào việc nó xuất hiện giống các SRS EPSG trong danh mục.

## 4. Thứ tự trục: longitude/latitude hay latitude/longitude?

Đây là nguồn lỗi phổ biến. Nhiều API bản đồ truyền tọa độ theo thứ tự longitude, latitude (X/Y). Tuy nhiên, định nghĩa chính thức của EPSG:4326 mô tả trục theo thứ tự latitude, longitude. MySQL mặc định diễn giải trục geographic theo định nghĩa SRS, trừ khi bạn chỉ định tùy chọn thứ tự trục.

Ví dụ, khi truyền dữ liệu theo cách phổ biến longitude trước, hãy nói rõ điều đó:

~~~sql
SET @hcm_point = ST_GeomFromText(
    'POINT(106.7000 10.8000)',
    4326,
    'axis-order=long-lat'
);

SELECT
    ST_SRID(@hcm_point) AS srid,
    ST_AsText(@hcm_point, 'axis-order=long-lat') AS longitude_latitude;
~~~

Trong ví dụ, 106.7000 là longitude và 10.8000 là latitude. Tùy chọn axis-order làm rõ thứ tự các giá trị WKT. Nếu bỏ tùy chọn, MySQL sử dụng thứ tự trục mặc định do SRS quy định.

Các tùy chọn axis-order có thể dùng khi đọc/ghi WKT hoặc các định dạng được hàm hỗ trợ:

- axis-order=srid-defined: dùng thứ tự trục trong định nghĩa SRS.
- axis-order=lat-long: diễn giải latitude trước, longitude sau.
- axis-order=long-lat: diễn giải longitude trước, latitude sau.

Hãy dùng cùng một quy ước xuyên suốt ingestion, API, migration và truy vấn. Đừng đảo hai con số để “sửa” một kết quả sai mà chưa kiểm tra định nghĩa trục.

### 4.1. Kiểm tra phạm vi tọa độ

Với WGS 84, longitude và latitude phải nằm trong phạm vi hợp lệ. Ví dụ latitude 106.7 độ là không hợp lệ; thường điều này xảy ra khi truyền longitude/latitude theo thứ tự ngược với thứ tự mà parser đang hiểu.

Khi tạo geometry geographic, MySQL có thể từ chối tọa độ vượt phạm vi của SRS. Đừng biến lỗi phạm vi thành cách sửa dữ liệu bằng cách hoán đổi trục tùy tiện; xác nhận nguồn dữ liệu và quy ước trước.

## 5. Geometry mang SRID như thế nào?

MySQL có các kiểu geometry cơ bản:

- POINT: một vị trí.
- LINESTRING: một đường gồm các điểm theo thứ tự.
- POLYGON: vùng đóng bởi các vòng tuyến tính.
- MULTIPOINT, MULTILINESTRING, MULTIPOLYGON: tập hợp các geometry cùng loại.
- GEOMETRYCOLLECTION: tập hợp geometry có thể khác loại.

SRID được gắn vào giá trị geometry. Hai geometry dùng trong phép toán không gian nên có cùng SRID và cùng hệ tọa độ tương thích. Nếu một geometry là 4326 và geometry còn lại là 3857, không thể coi các con số của chúng có cùng ý nghĩa. MySQL có thể phát sinh lỗi khác SRID thay vì tự chuyển đổi.

### 5.1. Tạo geometry từ WKT

Well-Known Text (WKT) là định dạng văn bản mô tả geometry. Có thể truyền SRID khi tạo giá trị:

~~~sql
SET @point = ST_GeomFromText(
    'POINT(106.7000 10.8000)',
    4326,
    'axis-order=long-lat'
);

SET @line = ST_GeomFromText(
    'LINESTRING(106.70 10.80, 106.71 10.81)',
    4326,
    'axis-order=long-lat'
);

SELECT
    ST_SRID(@point) AS point_srid,
    ST_GeometryType(@point) AS geometry_type,
    ST_AsText(@point, 'axis-order=long-lat') AS point_wkt;
~~~

Các hàm dựng WKT khác như ST_PointFromText() cũng nhận SRID theo cú pháp được hỗ trợ. Với geographic SRS, nên truyền tùy chọn axis-order khi nguồn tọa độ dùng quy ước longitude/latitude.

### 5.2. POLYGON phải đóng vòng

Một polygon WKT cần có vòng ngoài đóng, nghĩa là điểm cuối trùng điểm đầu. Ví dụ hình chữ nhật:

~~~sql
SET @district = ST_GeomFromText(
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

SELECT ST_SRID(@district), ST_GeometryType(@district);
~~~

Các đỉnh được viết theo longitude/latitude nhờ tùy chọn đã nêu. Một polygon tự cắt hoặc có vòng không hợp lệ có thể gây lỗi hoặc tạo kết quả không mong đợi trong phép toán hình học; cần kiểm tra validity khi nhập dữ liệu.

### 5.3. Kiểm tra geometry

~~~sql
SELECT
    ST_SRID(@district) AS srid,
    ST_GeometryType(@district) AS geometry_type,
    ST_IsValid(@district) AS is_valid,
    ST_AsText(@district, 'axis-order=long-lat') AS wkt;
~~~

ST_IsValid() kiểm tra tính hợp lệ hình học theo quy tắc OGC mà MySQL hỗ trợ. Kiểm tra validity không chứng minh geometry thuộc đúng địa điểm hoặc đúng tenant; đó là những quy tắc nghiệp vụ riêng.

## 6. Gán SRID khác với chuyển đổi tọa độ

Hai thao tác này tuyệt đối không được nhầm lẫn.

### 6.1. ST_SRID() đọc hoặc gán nhãn SRID

Với một đối số, ST_SRID(geometry) trả SRID hiện tại. Với đối số thứ hai, ST_SRID(geometry, srid) gán SRID mới cho geometry nhưng không tính lại các tọa độ.

~~~sql
-- SRID 0: các số chưa có trục địa lý; ta lưu chúng theo thứ tự
-- latitude, longitude mà SRS đích 4326 định nghĩa.
SET @point_without_srs = ST_GeomFromText('POINT(10.8 106.7)');

SELECT ST_SRID(@point_without_srs) AS original_srid;

SET @point_tagged = ST_SRID(@point_without_srs, 4326);

SELECT
    ST_SRID(@point_tagged) AS assigned_srid,
    ST_AsText(@point_tagged, 'axis-order=long-lat') AS longitude_latitude;
~~~

Đoạn mã trên chỉ phù hợp nếu các số đã được lưu theo thứ tự trục của SRS đích (latitude trước, longitude sau đối với EPSG:4326) và trước đó chỉ thiếu metadata. Khi xuất theo long-lat, kết quả hiển thị 106.7 và 10.8. Nó không chuyển một điểm Cartesian bất kỳ sang vị trí WGS 84.

Nếu dữ liệu gốc thực ra là metre trong một hệ chiếu, gán 4326 sẽ làm MySQL hiểu nhầm metre thành degree. Tọa độ không đổi nhưng ý nghĩa bị thay đổi, dẫn tới sai vị trí hoặc lỗi phạm vi.

### 6.2. ST_Transform() chuyển đổi tọa độ

ST_Transform(geometry, target_srid) thực hiện chuyển đổi từ SRS hiện tại sang SRS đích khi MySQL hỗ trợ phép biến đổi tương ứng. Hàm thay đổi tọa độ và SRID kết quả.

~~~sql
SET @hcm_wgs84 = ST_GeomFromText(
    'POINT(106.7000 10.8000)',
    4326,
    'axis-order=long-lat'
);

SET @hcm_web_mercator = ST_Transform(@hcm_wgs84, 3857);

SELECT
    ST_SRID(@hcm_wgs84) AS source_srid,
    ST_AsText(@hcm_wgs84, 'axis-order=long-lat') AS source_coordinates,
    ST_SRID(@hcm_web_mercator) AS target_srid,
    ST_AsText(@hcm_web_mercator) AS projected_coordinates;
~~~

Kết quả đầu tiên giữ longitude/latitude theo degree. Kết quả sau là tọa độ projected của hệ 3857. Không tự nhân hoặc chia tọa độ để giả lập một phép chiếu; hãy dùng phép biến đổi SRS được hỗ trợ.

### 6.3. Khi ST_Transform() thất bại

Phép biến đổi có thể thất bại nếu:

- Geometry nguồn không có SRS hợp lệ hoặc mang SRID 0.
- SRID đích không tồn tại trong danh mục SRS.
- MySQL không có thông tin hoặc phép biến đổi cần thiết giữa hai SRS.
- Geometry chứa tọa độ ngoài phạm vi mà SRS nguồn/đích chấp nhận.
- Dữ liệu có axis order hoặc datum không đúng với khai báo.

Không sửa lỗi bằng cách đổi SRID trên geometry. Kiểm tra SRS nguồn, SRS đích, trục, đơn vị và phạm vi trước khi thử lại.

### 6.4. Bảng phân biệt

| Hàm | Tác dụng | Tọa độ có thay đổi? | Dùng khi |
|---|---|---:|---|
| ST_SRID(g) | Đọc SRID | Không | Kiểm tra metadata |
| ST_SRID(g, srid) | Gán SRID mới | Không | Tọa độ vốn đúng hệ nhưng thiếu/sai metadata |
| ST_Transform(g, srid) | Chuyển SRS và tọa độ | Có | Cần đổi hệ tọa độ thực sự |

## 7. Khai báo SRID restriction cho cột geometry

Một geometry column không giới hạn SRID có thể chứa các geometry thuộc nhiều SRS khác nhau. Điều đó làm khó việc truy vấn, index và bảo đảm tính nhất quán.

MySQL 8.0.13+ hỗ trợ chỉ định SRID restriction ngay trong định nghĩa cột. Khi đó mọi geometry được ghi vào cột phải mang đúng SRID đã khai báo.

~~~sql
CREATE TABLE delivery_point (
    point_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    point_name VARCHAR(120) NOT NULL,
    position POINT NOT NULL SRID 4326,
    PRIMARY KEY (point_id)
) ENGINE=InnoDB;
~~~

Cột position chỉ chấp nhận POINT mang SRID 4326. Nếu ứng dụng gửi geometry SRID 0 hoặc 3857, MySQL từ chối thay vì âm thầm trộn các hệ tọa độ.

### 7.1. Ghi dữ liệu với SRID đúng

~~~sql
INSERT INTO delivery_point (point_name, position)
VALUES (
    'Ben Thanh',
    ST_GeomFromText(
        'POINT(106.6983 10.7725)',
        4326,
        'axis-order=long-lat'
    )
);
~~~

### 7.2. Kiểm tra dữ liệu sau khi ghi

~~~sql
SELECT
    point_id,
    point_name,
    ST_SRID(position) AS srid,
    ST_AsText(position, 'axis-order=long-lat') AS longitude_latitude
FROM delivery_point;
~~~

Kết quả phải cho SRID 4326. Kiểm tra metadata ở cả tầng database và application để phát hiện lỗi mapping sớm.

## 8. Spatial index và SRID

MySQL InnoDB hỗ trợ spatial index dựa trên R-tree. Spatial index lưu Minimum Bounding Rectangle (MBR) của geometry để tìm ứng viên theo vùng không gian.

Với MySQL 8.0, optimizer sử dụng spatial index trên geometry column khi cột được giới hạn bằng SRID cụ thể; cột geometry trong spatial index phải NOT NULL. Hãy khai báo SRID restriction và NOT NULL ngay từ đầu, sau đó xác nhận kế hoạch bằng EXPLAIN trên phiên bản MySQL đang triển khai.

~~~sql
ALTER TABLE delivery_point
    ADD SPATIAL INDEX sx_delivery_position (position);

SHOW CREATE TABLE delivery_point;
~~~

Spatial index không thay thế việc chọn SRS đúng. Một index nhanh trên dữ liệu gắn nhầm SRID vẫn trả về kết quả theo một hệ tọa độ sai.

### 8.1. MBR là gì?

MBR là hình chữ nhật nhỏ nhất song song với trục tọa độ bao quanh geometry. Với một POINT, MBR suy ra từ chính điểm đó. Với một POLYGON phức tạp, MBR có thể bao gồm nhiều vùng nằm ngoài polygon thực.

Các hàm MBR như MBRContains(), MBRWithin(), MBRIntersects() và MBROverlaps() làm việc trên bounding rectangle. Chúng phù hợp để lọc ứng viên và có thể khai thác spatial index.

Các predicate hình học chính xác như ST_Contains() hoặc ST_Intersects() xét hình dạng thực. Với geometry phức tạp, MBR filter có thể trả thêm false positive; cần phép kiểm tra chính xác nếu yêu cầu nghiệp vụ cần ranh giới thực.

### 8.2. Truy vấn vùng: lọc MBR rồi kiểm tra chính xác

~~~sql
SET @search_area = ST_GeomFromText(
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

SELECT point_id, point_name
FROM delivery_point
WHERE MBRContains(@search_area, position)
  AND ST_Contains(@search_area, position);
~~~

MBRContains() tạo bước lọc theo bounding rectangle; ST_Contains() kiểm tra hình học chính xác. Trong ví dụ vùng là hình chữ nhật nên MBR trùng với vùng; với polygon phức tạp, bước chính xác có thể loại ứng viên nằm trong MBR nhưng ngoài polygon.

### 8.3. Xác nhận optimizer dùng index

~~~sql
EXPLAIN
SELECT point_id, point_name
FROM delivery_point
WHERE MBRContains(@search_area, position);
~~~

Đọc access type, key và estimated rows. Nếu optimizer không dùng spatial index, kiểm tra:

- Cột geometry có NOT NULL không?
- Cột có SRID restriction không?
- Predicate có phải một MBR predicate được hỗ trợ không?
- Hai geometry có cùng SRID không?
- Bảng có đủ lớn để optimizer thấy index có lợi không?
- Thống kê và phiên bản MySQL có phù hợp không?

Không kết luận index hỏng chỉ vì một truy vấn nhỏ chọn table scan. Dùng dữ liệu đại diện và kiểm tra EXPLAIN sau khi cập nhật thống kê nếu cần.

## 9. Khoảng cách và diện tích phụ thuộc SRS

Không thể diễn giải một kết quả distance nếu không biết SRS và đơn vị.

### 9.1. Distance với geographic SRS

Với hai điểm WGS 84, ST_Distance() trả khoảng cách theo metre:

~~~sql
SET @p1 = ST_GeomFromText(
    'POINT(106.7000 10.8000)',
    4326,
    'axis-order=long-lat'
);

SET @p2 = ST_GeomFromText(
    'POINT(106.7100 10.8100)',
    4326,
    'axis-order=long-lat'
);

SELECT ST_Distance(@p1, @p2) AS distance_metres;
~~~

Đây là phép đo geographic theo SRS, không phải lấy hiệu longitude/latitude rồi tính Euclidean. Độ dài một degree longitude thay đổi theo latitude; vì thế không thể dùng một hệ số cố định để đổi degree thành metre cho mọi nơi.

### 9.2. Distance với Cartesian SRS

Với SRID 0 hoặc Cartesian SRS, ST_Distance() trả khoảng cách theo đơn vị của hệ tọa độ. Nếu tọa độ là (0,0) và (3,4), khoảng cách phẳng là 5 đơn vị. Nếu đơn vị chưa được quy định, kết quả chỉ là 5 coordinate units, không thể gọi là 5 metre.

### 9.3. Area và phép chiếu

ST_Area() với geographic SRS được hỗ trợ trả diện tích theo square metre; với Cartesian SRS trả diện tích theo bình phương đơn vị tuyến tính của hệ. Một projected SRS có thể thuận tiện cho đo đạc khu vực nhỏ nhưng vẫn có biến dạng phụ thuộc vị trí và phép chiếu.

Đối với báo cáo địa chính, quy hoạch hoặc đo đạc pháp lý, chọn hệ chiếu chuyên dụng phù hợp khu vực và yêu cầu độ chính xác. Không dùng Web Mercator chỉ vì ứng dụng hiển thị bản đồ bằng tile Web Mercator.

## 10. Quy trình nhập dữ liệu không gian

Một pipeline đáng tin cậy nên ghi rõ SRS ở mọi điểm giao tiếp:

1. Xác định SRS và datum của nguồn dữ liệu, không suy đoán chỉ từ tên file hoặc cặp số.
2. Xác định thứ tự trục nguồn: longitude/latitude hay latitude/longitude.
3. Xác thực phạm vi tọa độ, kiểu geometry, số chiều và tính hợp lệ hình học.
4. Parse WKT/WKB với SRID nguồn đúng và axis-order tường minh.
5. Nếu cần lưu theo SRS khác, dùng ST_Transform() và kiểm tra SRID kết quả.
6. Ghi vào cột geometry có SRID restriction phù hợp.
7. Dùng spatial index cho truy vấn vùng nếu workload cần.
8. Kiểm tra một số mẫu bằng WKT, SRID và bản đồ trực quan.
9. Lưu provenance: nguồn, SRID gốc, SRID đích, thời điểm và phiên bản pipeline.

Không nhận một geometry chỉ vì nó parse thành công. Parser chỉ xác nhận định dạng và các kiểm tra cơ bản; nó không biết điểm đó có nằm đúng thành phố hoặc đúng vùng nghiệp vụ hay không.

## 11. Chuyển đổi schema và migration SRID

Khi hệ thống đang lưu dữ liệu SRID 0 nhưng cần chuyển sang 4326, trước hết phải xác định tọa độ cũ thực sự là gì. Nếu tọa độ cũ vốn là longitude/latitude nhưng thiếu SRID, có thể gán metadata đúng sau khi kiểm chứng. Nếu tọa độ cũ là projected coordinates, phải biết chính xác SRS nguồn trước khi transform.

Quy trình migration an toàn:

1. Dừng hoặc kiểm soát writer để không phát sinh dữ liệu theo quy ước cũ trong lúc chuyển đổi.
2. Sao lưu và lấy mẫu geometry hiện tại.
3. Xác định SRS nguồn, trục và đơn vị từ hệ thống tạo dữ liệu.
4. Chia dữ liệu thành nhóm có nguồn gốc rõ ràng; cách ly các bản ghi không xác định.
5. Tạo geometry mới bằng ST_Transform() nếu cần chuyển hệ.
6. Kiểm tra phạm vi, validity, SRID và vị trí mẫu.
7. Tạo cột mới có SRID restriction; nạp dữ liệu theo batch.
8. Tạo spatial index và kiểm tra EXPLAIN.
9. Chuyển ứng dụng sang cột mới, theo dõi sai lệch và latency.
10. Chỉ loại bỏ cột cũ sau khi xác nhận rollback window đã hết.

Không chạy ST_SRID(old_geom, 4326) hàng loạt chỉ để làm cho dữ liệu qua được cột SRID 4326. Nếu tọa độ chưa phải WGS 84, thao tác đó là relabel chứ không phải chuyển đổi.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Điểm xuất hiện ở sai quốc gia hoặc đại dương | Đảo latitude/longitude hoặc gán sai SRID | Kiểm tra nguồn, axis-order và SRS definition |
| Tọa độ 106.7/10.8 bị báo ngoài phạm vi | Parser đang hiểu trục theo thứ tự latitude/longitude | Dùng axis-order tường minh nếu nguồn là longitude/latitude |
| Distance trả số rất nhỏ hoặc rất lớn | Degree bị hiểu như đơn vị phẳng hoặc metre bị hiểu là degree | Xác định SRS nguồn và dùng ST_Transform nếu cần |
| Spatial operation báo khác SRID | Hai geometry không cùng SRS | Chuyển một bên sang SRID thống nhất trước khi so sánh |
| ST_Transform() lỗi | SRID nguồn/đích hoặc phép biến đổi không được hỗ trợ | Tra SRS catalog và kiểm tra định nghĩa/phạm vi |
| Spatial index không được dùng | Cột thiếu SRID restriction, nullable hoặc predicate không phù hợp | Kiểm tra DDL, predicate và EXPLAIN |
| MBR query trả nhiều điểm ngoài polygon | MBR chỉ là hình chữ nhật bao quanh | Kết hợp predicate chính xác như ST_Contains() |
| Dữ liệu cũ có SRID 0 | Ứng dụng tạo geometry không chỉ định SRID | Xác định SRS thực của tọa độ trước khi migration |
| Một số polygon bị từ chối | WKT sai, ring chưa đóng hoặc geometry invalid | Kiểm tra WKT và ST_IsValid() |

## 13. Checklist thiết kế

Trước khi đưa spatial column vào production, xác nhận:

- SRS đã được chọn từ nguồn dữ liệu có thẩm quyền.
- Geographic hay Cartesian phù hợp với phép tính cần làm.
- SRID và organization coordinate-system ID đã được kiểm tra trong catalog.
- Axis order đã được ghi trong hợp đồng API.
- Đơn vị distance/area đã được ghi rõ.
- Cột geometry có SRID restriction và NOT NULL nếu phù hợp.
- Spatial index đã được tạo và EXPLAIN xác nhận với truy vấn đại diện.
- MBR prefilter được kết hợp với predicate chính xác khi cần.
- Pipeline có kiểm tra validity và phạm vi tọa độ.
- Migration phân biệt relabel SRID và transform tọa độ.
- Có dữ liệu mẫu để kiểm chứng vị trí trực quan.
- Có kế hoạch rollback khi chuyển SRID hoặc thay đổi projection.

## 14. Bài thực hành

Thực hiện trong MySQL 8.0.13+ với schema lab:

1. Tạo POINT không truyền SRID; đọc SRID bằng ST_SRID() và giải thích vì sao là SRID 0.
2. Tra cứu EPSG:4326 và EPSG:3857 trong INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS.
3. Tạo POINT WGS 84 theo axis-order=long-lat và đọc lại bằng ST_AsText() với cùng thứ tự trục.
4. Tạo một điểm bằng thứ tự trục mặc định; so sánh với kết quả dùng axis-order=long-lat.
5. Thử một cặp tọa độ đảo trục; xác định lỗi phạm vi hoặc vị trí sai.
6. Tạo LINESTRING và POLYGON trong SRID 4326; xác minh geometry type và validity.
7. Dùng ST_SRID(g, 4326) để gán SRID cho geometry có tọa độ đã biết là WGS 84; giải thích vì sao tọa độ không đổi.
8. Dùng ST_Transform() chuyển một điểm 4326 sang 3857; so sánh SRID và tọa độ trước/sau.
9. Thử ST_Distance() giữa hai điểm 4326 và diễn giải kết quả theo metre.
10. Tạo bảng có POINT NOT NULL SRID 4326; thử insert geometry mang SRID 0 để quan sát constraint.
11. Tạo SPATIAL INDEX cho cột POINT và xác nhận DDL bằng SHOW CREATE TABLE.
12. Viết truy vấn MBRContains() cho vùng chữ nhật; đọc EXPLAIN và kiểm tra spatial index.
13. Dùng ST_Contains() làm điều kiện chính xác sau bước MBR prefilter.
14. Tạo polygon phức tạp có MBR rộng; minh họa vì sao MBR filter có false positive.
15. Lập kế hoạch migration cho dữ liệu legacy SRID 0, phân biệt trường hợp chỉ thiếu metadata với trường hợp cần chuyển tọa độ thực.

## 15. Nguyên tắc cần ghi nhớ

- SRS mô tả hệ tọa độ; SRID định danh SRS gắn với geometry.
- SRID 0 của MySQL là Cartesian mặc định, không tự có ý nghĩa longitude/latitude.
- Cartesian dùng hình học phẳng; geographic xét bề mặt Trái Đất và đơn vị geographic phù hợp.
- EPSG:4326 là geographic WGS 84; EPSG:3857 là projected Web Mercator.
- Trục EPSG:4326 được định nghĩa latitude/longitude; nếu nguồn gửi longitude/latitude, dùng axis-order=long-lat rõ ràng.
- ST_SRID(g, srid) chỉ gán nhãn SRID, không chuyển tọa độ.
- ST_Transform(g, srid) chuyển đổi tọa độ sang SRS đích khi phép biến đổi được hỗ trợ.
- Không so sánh geometry khác SRID như thể chúng ở cùng hệ tọa độ.
- SRID restriction giúp ngăn trộn hệ tọa độ trong một cột.
- Spatial index InnoDB dựa trên R-tree/MBR; geometry column cần NOT NULL và SRID restriction để optimizer sử dụng theo yêu cầu của MySQL 8.0.
- MBR predicate là bước lọc theo bounding rectangle; dùng predicate hình học chính xác khi nghiệp vụ yêu cầu.
- Distance và area phải được diễn giải theo loại SRS và đơn vị.
- Chọn projection theo mục tiêu đo đạc; không mặc định Web Mercator là hệ đo chính xác.
- Trước migration, xác định SRS nguồn và phân biệt relabel metadata với transform tọa độ.
