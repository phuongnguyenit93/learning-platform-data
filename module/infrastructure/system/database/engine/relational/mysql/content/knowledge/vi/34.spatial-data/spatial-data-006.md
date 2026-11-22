# Khoảng cách, đơn vị đo và điều kiện hệ tọa độ hỗ trợ

Khi tính khoảng cách giữa hai vị trí, kết quả chỉ có ý nghĩa nếu hai geometry dùng cùng một hệ tọa độ và đơn vị đo được hiểu đúng. Hai điểm có tọa độ (10, 20) và (11, 21) có thể biểu diễn hai vị trí trên một mặt phẳng trừu tượng, hai điểm trên bản đồ chiếu hoặc hai kinh/vĩ độ trên Trái Đất. Cùng một cặp số nhưng phép tính và đơn vị kết quả không giống nhau.

Trong MySQL, hàm thường dùng là ST_Distance(). Hàm này trả khoảng cách theo đơn vị chiều dài của spatial reference system (SRS) hoặc theo đơn vị được truyền vào. Với geographic SRS, MySQL tính khoảng cách địa trắc trên ellipsoid. Với trường hợp cần mô hình quả cầu và dữ liệu là điểm, có thể dùng ST_Distance_Sphere(), hàm trả kết quả bằng mét.

Các lỗi thường gặp xuất phát từ việc:

- Lưu kinh độ/vĩ độ nhưng để SRID mặc định 0.
- Dùng ST_Distance() trên SRID 0 rồi diễn giải số đo thành mét.
- Trộn geometry có SRID khác nhau trong cùng phép tính.
- Gán SRID mới bằng ST_SRID() mà không chuyển đổi tọa độ.
- Đưa kinh độ và vĩ độ sai thứ tự theo định nghĩa trục của SRS.
- Dùng ST_Distance_Sphere() với projected SRS hoặc geometry không phải Point/MultiPoint.
- Yêu cầu đơn vị không được MySQL hỗ trợ hoặc chuyển đổi đơn vị khi SRS không xác định đơn vị chiều dài.

Bài học này hướng dẫn chọn SRS, hiểu SRID, kiểm tra đơn vị, chọn hàm khoảng cách, chuyển đổi hệ tọa độ, thiết kế cột và spatial index, rồi kiểm thử các điều kiện đầu vào trước khi đưa phép tính vào ứng dụng.

Các ví dụ tập trung vào MySQL 8.4. SRS, đơn vị và khả năng chuyển đổi có thể phụ thuộc định nghĩa được cài trong data dictionary và phiên bản server; hãy truy vấn metadata trên server thực tế thay vì đoán theo tên SRID.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt Cartesian SRS, projected SRS và geographic SRS.
- Giải thích SRID 0 và vì sao nó không có đơn vị chiều dài.
- Hiểu SRID 4326 (WGS 84), kinh độ, vĩ độ và thứ tự trục theo SRS.
- Phân biệt ST_SRID() với ST_Transform().
- Chọn ST_Distance() hay ST_Distance_Sphere() theo mô hình đo.
- Hiểu đơn vị mặc định và đối số unit của ST_Distance().
- Tra cứu các đơn vị hợp lệ trong INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE.
- Nhận biết lỗi khi geometry có SRID khác nhau hoặc SRS không được định nghĩa.
- Nhận biết giới hạn geometry type và SRS của ST_Distance_Sphere().
- Kiểm tra kinh độ/vĩ độ nằm trong miền hợp lệ.
- Thiết kế cột spatial có SRID cố định và spatial index.
- Tách lọc ứng viên bằng bounding box khỏi tính khoảng cách chính xác.
- Viết truy vấn tìm địa điểm gần nhất có đơn vị và điều kiện rõ ràng.
- Xây dựng checklist kiểm thử hệ tọa độ trước khi phát hành.

## 1. Khoảng cách không chỉ là phép trừ tọa độ

Giả sử hai điểm có tọa độ:

    POINT(10 20)
    POINT(13 24)

Nếu đây là hai điểm trên mặt phẳng Cartesian, khoảng cách Euclid là:

    SQRT((13 - 10)^2 + (24 - 20)^2)
    = 5

Con số 5 có đơn vị nào? Điều đó phụ thuộc SRS:

- Nếu trục đo bằng mét, kết quả là 5 mét.
- Nếu trục đo bằng feet, kết quả là 5 feet.
- Nếu dùng SRID 0, hai trục không có đơn vị được gán; kết quả chỉ là 5 đơn vị tọa độ trừu tượng.
- Nếu hai số là longitude/latitude, không thể xem chênh lệch độ kinh/vĩ là khoảng cách tuyến tính cố định trên mặt phẳng.

Ở geographic SRS, khoảng cách giữa hai vị trí phải xét hình dạng ellipsoid của Trái Đất. Một độ kinh độ ở xích đạo có chiều dài khác một độ kinh độ ở vĩ độ cao. Một độ vĩ độ cũng không được hiểu là cùng một đơn vị chiều dài tùy ý.

Vì vậy, trước khi chọn hàm khoảng cách, hãy trả lời ba câu hỏi:

1. Geometry được lưu trong SRS nào?
2. Các trục tọa độ dùng đơn vị gì và thứ tự trục ra sao?
3. Nghiệp vụ cần khoảng cách phẳng, địa trắc trên ellipsoid hay xấp xỉ trên quả cầu?

## 2. SRS, SRID và ba mô hình tọa độ

Spatial reference system (SRS) mô tả hệ tọa độ dùng để định vị geometry. SRID là mã số gắn với geometry để xác định SRS đó.

MySQL hỗ trợ các SRS Cartesian, projected và geographic. Các loại này khác nhau về cách diễn giải tọa độ và đơn vị.

### 2.1. Cartesian SRS

Cartesian SRS mô hình hóa mặt phẳng với các trục X/Y vuông góc. Phép tính khoảng cách là hình học phẳng.

Ví dụ:

    POINT(100 200)
    POINT(103 204)

Nếu SRS quy định đơn vị mét, khoảng cách Euclid là 5 mét. Nếu dùng một hệ Cartesian khác, kết quả theo đơn vị chiều dài của hệ đó.

Cartesian phù hợp với:

- Bản vẽ kỹ thuật và mặt bằng nhà xưởng.
- Tọa độ trong game hoặc mô hình mô phỏng.
- Bản đồ nội bộ đã chiếu về một hệ phẳng phù hợp.
- Bài toán hình học trên mặt phẳng không đại diện trực tiếp cho toàn bộ Trái Đất.

### 2.2. Projected SRS

Projected SRS chiếu bề mặt ellipsoid của Trái Đất lên một mặt phẳng bản đồ. Tọa độ thường là Easting/Northing hoặc X/Y theo đơn vị chiều dài như mét hay feet.

Ví dụ phổ biến:

- EPSG:3857 — WGS 84 / Pseudo-Mercator, thường gặp trong bản đồ web.
- Các hệ UTM theo zone — thường dùng cho đo đạc khu vực.
- Các hệ chiếu quốc gia hoặc địa phương có đơn vị và phép chiếu riêng.

Ưu điểm là phép tính trên mặt phẳng thuận tiện cho các tác vụ khu vực. Tuy nhiên, phép chiếu tạo biến dạng. EPSG:3857 tiện cho hiển thị bản đồ web nhưng khoảng cách đo trực tiếp có thể sai lệch đáng kể khi đi xa xích đạo. Không chọn projected SRS chỉ vì tọa độ của nó có đơn vị mét; hãy chọn phép chiếu phù hợp khu vực và độ chính xác cần thiết.

### 2.3. Geographic SRS

Geographic SRS biểu diễn vị trí trên ellipsoid bằng tọa độ góc, thường là longitude/latitude hoặc latitude/longitude theo định nghĩa trục.

Ví dụ phổ biến:

- EPSG:4326 — WGS 84.
- Một số SRS địa lý khác dùng datum/ellipsoid khác.

Trong geographic SRS, các tọa độ thường nằm trong miền:

- Longitude: lớn hơn -180 và nhỏ hơn hoặc bằng 180 độ.
- Latitude: từ -90 đến 90 độ.

MySQL kiểm tra miền longitude/latitude theo SRS. Nếu giá trị vượt miền, các hàm xử lý geographic geometry có thể phát lỗi.

### 2.4. SRID 0 là mặt phẳng không có đơn vị

SRID 0 trong MySQL là một mặt phẳng Cartesian vô hạn, không được gắn với Trái Đất và không có đơn vị trên trục. Đây là SRID mặc định khi tạo geometry mà không chỉ định SRID.

Ví dụ:

    SET @p1 = ST_GeomFromText('POINT(10 20)');
    SELECT ST_SRID(@p1);

Kết quả là 0.

Không diễn giải ST_Distance() giữa hai geometry SRID 0 thành mét hoặc kilomet. Kết quả chỉ là khoảng cách trong hệ tọa độ trừu tượng đó.

## 3. Kiểm tra SRS được MySQL hỗ trợ

MySQL lưu các định nghĩa SRS trong data dictionary và cung cấp view INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS.

### 3.1. Tra cứu WGS 84

    SELECT
        SRS_NAME,
        SRS_ID,
        ORGANIZATION,
        ORGANIZATION_COORDSYS_ID,
        DEFINITION,
        DESCRIPTION
    FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
    WHERE SRS_ID = 4326;

Kết quả cho biết SRID 4326 có tên WGS 84, tổ chức EPSG và định nghĩa WKT của SRS. Trong định nghĩa EPSG:4326, trục được mô tả theo latitude trước longitude.

### 3.2. Tìm các SRS geographic hoặc projected

    SELECT
        SRS_ID,
        SRS_NAME,
        ORGANIZATION,
        DEFINITION
    FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
    ORDER BY SRS_ID;

Có thể lọc theo tên hoặc tổ chức:

    SELECT
        SRS_ID,
        SRS_NAME,
        ORGANIZATION
    FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
    WHERE SRS_NAME LIKE '%WGS%'
       OR SRS_NAME LIKE '%UTM%';

View này phản ánh SRS có trong data dictionary của server. Không giả định mọi mã EPSG trong một hệ thống GIS bên ngoài đều đã được cài đặt hoặc có thể chuyển đổi trong MySQL.

### 3.3. Xem metadata cột spatial

    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        COLUMN_NAME,
        SRS_ID,
        SRS_NAME,
        GEOMETRY_TYPE_NAME
    FROM INFORMATION_SCHEMA.ST_GEOMETRY_COLUMNS
    WHERE TABLE_SCHEMA = DATABASE();

Truy vấn này giúp phát hiện cột nào đang dùng SRID nào và kiểu geometry được khai báo.

## 4. Thứ tự trục tọa độ: longitude/latitude hay latitude/longitude?

Đây là nguồn lỗi rất phổ biến khi nhập GPS hoặc dữ liệu từ API bản đồ.

Nhiều API và GeoJSON biểu diễn vị trí theo thứ tự:

    [longitude, latitude]

Tuy nhiên, một SRS có thể định nghĩa trục theo thứ tự:

    latitude, longitude

Với MySQL, các hàm tạo geometry từ WKT mặc định diễn giải tọa độ geographic theo thứ tự trục được định nghĩa trong SRS. Đối với EPSG:4326, trục định nghĩa là latitude trước longitude. Có thể ghi rõ lựa chọn bằng đối số options.

### 4.1. Dùng thứ tự theo định nghĩa SRS

Ví dụ tọa độ địa lý có latitude 10.8 và longitude 106.7:

    SET @hcm = ST_GeomFromText(
        'POINT(10.8 106.7)',
        4326
    );

Vì không truyền options, MySQL dùng thứ tự trục theo SRS-defined.

### 4.2. Ghi rõ longitude trước latitude

Nếu dữ liệu đầu vào của ứng dụng luôn theo thứ tự longitude/latitude, chỉ định:

    SET @hcm = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

Các lựa chọn được hỗ trợ:

- axis-order=srid-defined: dùng thứ tự trục do SRS quy định; đây là mặc định.
- axis-order=lat-long: đọc tọa độ theo latitude rồi longitude.
- axis-order=long-lat: đọc tọa độ theo longitude rồi latitude.

Không thay đổi thứ tự tọa độ bằng cách chỉ đảo hai con số mà không hiểu SRS. Hãy thống nhất hợp đồng dữ liệu ở API, ETL, WKT/WKB và cột lưu trữ.

### 4.3. Xác minh geometry sau khi tạo

    SELECT
        ST_AsText(@hcm),
        ST_SRID(@hcm),
        ST_Longitude(@hcm),
        ST_Latitude(@hcm);

Với Point geographic, ST_Longitude() và ST_Latitude() giúp đọc hai thành phần theo ý nghĩa địa lý. Nếu kết quả không đúng khu vực mong đợi, kiểm tra axis-order trước khi lưu dữ liệu hàng loạt.

## 5. ST_Distance(): khoảng cách theo SRS

Cú pháp:

    ST_Distance(g1, g2 [, unit])

Hàm trả khoảng cách giữa hai geometry:

- Nếu SRS là Cartesian, phép đo theo đơn vị chiều dài của Cartesian SRS.
- Nếu SRS là geographic, MySQL tính khoảng cách địa trắc trên ellipsoid.
- Nếu có đối số unit, kết quả được chuyển sang đơn vị chiều dài được chỉ định.
- Nếu không chỉ định unit, kết quả theo đơn vị chiều dài của SRS. Các SRS MySQL hiện hỗ trợ đều biểu diễn đơn vị chiều dài theo mét.

Các geometry đầu vào phải dùng cùng SRS. Nếu khác SRID, MySQL phát lỗi ER_GIS_DIFFERENT_SRIDS.

### 5.1. Khoảng cách trên mặt phẳng SRID 0

    SET @a = ST_GeomFromText('POINT(1 1)', 0);
    SET @b = ST_GeomFromText('POINT(4 5)', 0);

    SELECT ST_Distance(@a, @b) AS coordinate_distance;

Kết quả là 5. Đây là 5 đơn vị tọa độ trừu tượng, không phải 5 mét.

### 5.2. Khoảng cách geographic với WGS 84

    SET @p1 = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SET @p2 = ST_GeomFromText(
        'POINT(106.71 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SELECT ST_Distance(@p1, @p2) AS distance_m;

Đây là khoảng cách địa trắc trên ellipsoid WGS 84. Vì SRS dùng mét làm đơn vị chiều dài, kết quả mặc định là mét.

### 5.3. Yêu cầu đơn vị khác

    SELECT
        ST_Distance(@p1, @p2, 'metre') AS distance_m,
        ST_Distance(@p1, @p2, 'foot') AS distance_ft,
        ST_Distance(@p1, @p2, 'kilometre') AS distance_km;

Tên đơn vị phải nằm trong danh sách MySQL hỗ trợ. Nếu đơn vị không tồn tại, hàm phát lỗi ER_UNIT_NOT_FOUND.

Không tự đoán tên đơn vị từ ký hiệu hiển thị như m, km hoặc mi. Hãy tra cứu danh sách chính xác trong INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE.

### 5.4. SRID 0 không thể đổi đơn vị chiều dài

Ví dụ:

    SELECT ST_Distance(@a, @b, 'metre');

Với geometry SRID 0, MySQL không biết một đơn vị tọa độ tương ứng bao nhiêu mét. Truyền một linear unit có thể phát lỗi ER_GEOMETRY_IN_UNKNOWN_LENGTH_UNIT.

Không thể sửa lỗi này bằng cách truyền 'metre'. Phải tạo geometry từ đầu trong SRS có đơn vị được xác định hoặc chuyển đổi dữ liệu bằng một phép biến đổi tọa độ có căn cứ.

## 6. Tra cứu đơn vị đo được hỗ trợ

MySQL cung cấp view INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE để liệt kê các đơn vị được chấp nhận bởi ST_Distance() và một số hàm spatial có đối số unit.

### 6.1. Xem toàn bộ đơn vị

    SELECT
        UNIT_NAME,
        UNIT_TYPE,
        CONVERSION_FACTOR,
        DESCRIPTION
    FROM INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE
    ORDER BY UNIT_TYPE, UNIT_NAME;

Các cột có ý nghĩa:

- UNIT_NAME: tên dùng trong đối số unit.
- UNIT_TYPE: loại đơn vị, ví dụ LINEAR.
- CONVERSION_FACTOR: hệ số chuyển đổi nội bộ.
- DESCRIPTION: mô tả đơn vị.

### 6.2. Lọc đơn vị chiều dài

    SELECT
        UNIT_NAME,
        CONVERSION_FACTOR,
        DESCRIPTION
    FROM INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE
    WHERE UNIT_TYPE = 'LINEAR'
    ORDER BY UNIT_NAME;

Danh sách có thể bao gồm các đơn vị như metre, kilometre, foot hoặc nautical mile. Hãy dùng chính xác UNIT_NAME từ server.

### 6.3. Đơn vị và SRS

Đối số unit của ST_Distance() là đơn vị chiều dài, không phải đơn vị góc. Không truyền degree để yêu cầu khoảng cách địa lý theo độ.

Với geographic SRS, MySQL tính khoảng cách địa trắc rồi trả kết quả theo đơn vị chiều dài. Với projected SRS, đơn vị mặc định là đơn vị chiều dài của hệ chiếu. Với SRID 0, không có đơn vị chiều dài để chuyển đổi.

## 7. ST_Distance_Sphere(): khoảng cách trên quả cầu

Cú pháp:

    ST_Distance_Sphere(g1, g2 [, radius])

Hàm trả khoảng cách ngắn nhất giữa các geometry Point hoặc MultiPoint trên một quả cầu. Kết quả luôn tính bằng mét. Đối số radius nếu có cũng phải là mét.

### 7.1. Với SRID 0

Khi hai geometry là Point hoặc MultiPoint hợp lệ có SRID 0:

- X được hiểu là longitude.
- Y được hiểu là latitude.
- Đơn vị tọa độ góc là độ.
- Bán kính mặc định là 6.370.986 mét.

Ví dụ:

    SET @p1 = ST_GeomFromText('POINT(106.7 10.8)', 0);
    SET @p2 = ST_GeomFromText('POINT(106.71 10.8)', 0);

    SELECT ST_Distance_Sphere(@p1, @p2) AS distance_m;

Trong trường hợp này, SRID 0 không mô tả SRS địa lý; hàm có quy tắc riêng diễn giải Point X/Y là longitude/latitude trên quả cầu. Không áp dụng quy tắc đặc biệt này cho ST_Distance().

### 7.2. Với geographic SRS

Nếu hai geometry là Point hoặc MultiPoint thuộc geographic SRS:

- MySQL sử dụng bán kính mặc định bằng mean radius của ellipsoid SRS, được tính (2a+b)/3.
- Có thể truyền radius tùy chỉnh theo mét.
- Kết quả là khoảng cách trên quả cầu, không phải geodesic chính xác trên ellipsoid.

Ví dụ:

    SET @p1 = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SET @p2 = ST_GeomFromText(
        'POINT(106.71 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SELECT
        ST_Distance_Sphere(@p1, @p2) AS default_radius_m,
        ST_Distance_Sphere(@p1, @p2, 6371000) AS custom_radius_m;

### 7.3. Giới hạn geometry type và SRS

ST_Distance_Sphere() chỉ hỗ trợ các tổ hợp:

- Point và Point.
- Point và MultiPoint.
- MultiPoint và Point.

Hàm không hỗ trợ Polygon, LineString hoặc GeometryCollection. Nếu geometry dùng projected SRS, MySQL phát lỗi ER_NOT_IMPLEMENTED_FOR_PROJECTED_SRS.

Khi cần khoảng cách giữa đường, vùng hoặc geometry tổng hợp, dùng ST_Distance() nếu SRS và loại geometry được hỗ trợ.

### 7.4. Chọn hàm nào?

| Nhu cầu | Hàm phù hợp | Kết quả |
|---|---|---|
| Khoảng cách giữa hai geometry trên Cartesian plane | ST_Distance | Đơn vị của SRS |
| Khoảng cách địa trắc trên ellipsoid | ST_Distance với geographic SRS | Đơn vị chiều dài của SRS hoặc unit chỉ định |
| Khoảng cách Point/MultiPoint xấp xỉ trên quả cầu | ST_Distance_Sphere | Mét |
| Khoảng cách từ Point đến Polygon/LineString | ST_Distance nếu geometry hợp lệ và cùng SRS | Đơn vị chiều dài của SRS |
| Tính trên SRID 0 rồi gọi kết quả là mét | Không có hàm nào tự suy ra được | Cần SRS có đơn vị xác định |

ST_Distance_Sphere() có thể đủ cho tìm kiếm lân cận thông thường, nhưng nếu cần độ chính xác địa trắc cao hơn, hãy dùng ST_Distance() với geographic SRS.

## 8. ST_SRID() không chuyển đổi tọa độ

Hai hàm có mục đích khác nhau:

- ST_SRID(g, srid) gán SRID mới cho geometry nhưng giữ nguyên các con số tọa độ.
- ST_Transform(g, target_srid) chuyển đổi tọa độ sang hệ đích và trả geometry với target SRID.

### 8.1. Ví dụ đổi nhãn SRID

    SET @g = ST_GeomFromText('POINT(106.7 10.8)', 0);

    SELECT ST_AsText(ST_SRID(@g, 4326));

Lệnh trên gán SRID 4326 cho các con số hiện có. Nó không tính lại tọa độ theo WGS 84 và không kiểm chứng rằng các con số ban đầu thực sự là longitude/latitude.

Chỉ dùng ST_SRID() khi geometry đã có tọa độ đúng nhưng SRID bị gắn sai và bạn hiểu rõ cách sửa metadata. Không dùng nó như phép chuyển đổi hệ tọa độ.

### 8.2. Dùng ST_Transform()

    SET @web_point = ST_GeomFromText(
        'POINT(11886500 1220000)',
        3857
    );

    SET @wgs84_point = ST_Transform(@web_point, 4326);

    SELECT
        ST_SRID(@wgs84_point),
        ST_AsText(@wgs84_point);

ST_Transform() thực hiện phép biến đổi tọa độ theo định nghĩa SRS. Nếu nguồn hoặc đích không được hỗ trợ chuyển đổi, MySQL có thể phát lỗi như:

- ER_SRS_NOT_FOUND.
- ER_TRANSFORM_SOURCE_SRS_NOT_SUPPORTED.
- ER_TRANSFORM_TARGET_SRS_NOT_SUPPORTED.
- ER_TRANSFORM_SOURCE_SRS_MISSING_TOWGS84.
- ER_TRANSFORM_TARGET_SRS_MISSING_TOWGS84.

MySQL 8.4 hỗ trợ các SRS EPSG, ngoại trừ một số định nghĩa được liệt kê trong tài liệu, và việc chuyển đổi còn phụ thuộc tham số datum/transform của SRS. Hãy thử trên một vài tọa độ kiểm soát trước khi chuyển đổi cả bảng.

### 8.3. Kiểm tra SRID trước khi tính

    SELECT
        ST_SRID(location) AS srid,
        COUNT(*) AS row_count
    FROM places
    GROUP BY ST_SRID(location);

Nếu một cột chứa nhiều SRID, không dùng trực tiếp các giá trị đó trong một phép tính khoảng cách nhiều geometry. Hãy chuẩn hóa dữ liệu về cùng SRS hoặc chuyển đổi từng giá trị sang SRS đích.

## 9. Điều kiện SRID của các phép tính nhiều geometry

Các hàm spatial nhận nhiều geometry thường yêu cầu mọi geometry có cùng SRS. Nếu một geometry có SRID 4326 và geometry còn lại có SRID 3857, MySQL phát lỗi ER_GIS_DIFFERENT_SRIDS.

Ví dụ không hợp lệ:

    SET @a = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SET @b = ST_GeomFromText(
        'POINT(11886500 1220000)',
        3857
    );

    SELECT ST_Distance(@a, @b);

Phải chuyển một geometry sang SRS của geometry còn lại:

    SET @b_4326 = ST_Transform(@b, 4326);

    SELECT ST_Distance(@a, @b_4326);

Không giải quyết lỗi bằng cách thay SRID của một đối tượng bằng ST_SRID() nếu tọa độ vẫn thuộc hệ cũ. Điều đó làm MySQL diễn giải các con số theo một hệ tọa độ sai.

## 10. Hệ tọa độ được hỗ trợ và giới hạn theo storage engine

MySQL hỗ trợ spatial data type trên các storage engine khác nhau, nhưng hỗ trợ SRS và spatial index không giống nhau.

| Storage engine | Spatial columns | SRID được hỗ trợ theo tài liệu MySQL | SPATIAL index |
|---|---|---|---|
| InnoDB | Có | Cartesian và geographic SRS | Có |
| MyISAM | Có | Cartesian SRS | Có |
| NDB | Có | Kiểm tra giới hạn riêng của engine | Không |
| ARCHIVE | Có | Kiểm tra giới hạn riêng của engine | Không |

Spatial index chỉ được hỗ trợ trên InnoDB và MyISAM. NDB và ARCHIVE hỗ trợ spatial data types nhưng không hỗ trợ SPATIAL index. Đối với hệ thống mới cần geographic coordinates cùng spatial index, InnoDB thường là lựa chọn thực tế. Đừng chỉ nhìn thấy cột POINT được hỗ trợ rồi kết luận engine đó hỗ trợ mọi SRS và mọi loại index.

### 10.1. Geometry type được hỗ trợ

MySQL hỗ trợ các geometry type:

- GEOMETRY
- POINT
- LINESTRING
- POLYGON
- MULTIPOINT
- MULTILINESTRING
- MULTIPOLYGON
- GEOMETRYCOLLECTION

Không phải mọi hàm khoảng cách đều nhận mọi loại geometry. ST_Distance() hỗ trợ geographic SRS cho mọi geometry type theo quy tắc hàm; ST_Distance_Sphere() chỉ nhận Point/MultiPoint.

### 10.2. SRS không xác định

Nếu SRID tham chiếu đến SRS không tồn tại trong data dictionary, nhiều spatial function phát lỗi ER_SRS_NOT_FOUND. Kiểm tra:

    SELECT *
    FROM INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS
    WHERE SRS_ID = 999999;

Nếu không có dòng kết quả, server không có định nghĩa SRS đó. Không tự dùng mã SRID chỉ vì nó tồn tại trong dữ liệu bên ngoài.

## 11. Cột spatial cố định SRID và spatial index

Spatial index trong MySQL dùng R-tree. Để optimizer có thể sử dụng index, cột phải:

- Được khai báo NOT NULL.
- Có SRID cố định trong định nghĩa cột.
- Chỉ chứa geometry phù hợp với SRID đó.

Ví dụ:

    CREATE TABLE delivery_point (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(150) NOT NULL,
        location POINT NOT NULL SRID 4326,
        SPATIAL INDEX sx_delivery_location (location)
    ) ENGINE=InnoDB;

Thuộc tính SRID 4326 khiến cột chỉ nhận geometry có SRID 4326. Khi insert một geometry có SRID khác, MySQL từ chối.

### 11.1. Cột không giới hạn SRID

Một cột geometry không có thuộc tính SRID có thể chứa giá trị thuộc nhiều SRS. Tuy nhiên, optimizer không thể sử dụng spatial index trên cột chưa bị giới hạn SRID. Nếu cột đã có dữ liệu, cần kiểm tra tất cả giá trị và chuẩn hóa về cùng SRID trước khi thêm thuộc tính.

Kiểm tra:

    SELECT DISTINCT ST_SRID(location)
    FROM delivery_point;

Nếu kết quả có nhiều SRID, cần xử lý dữ liệu trước khi thay đổi định nghĩa cột.

### 11.2. Giới hạn spatial index

Spatial index:

- Chỉ áp dụng trên một spatial column.
- Cột được index phải NOT NULL.
- Không hỗ trợ prefix length.
- Không dùng làm PRIMARY KEY hoặc UNIQUE index.
- Có thể dùng R-tree để lọc theo minimum bounding rectangle.

Spatial index không tự biến mọi phép ST_Distance() thành truy vấn index seek. Thường cần dùng điều kiện không gian có thể tận dụng bounding box hoặc relation phù hợp, rồi tính khoảng cách chính xác trên tập ứng viên nhỏ hơn.

## 12. Tìm điểm gần nhất với đơn vị rõ ràng

Ví dụ bảng địa điểm:

    CREATE TABLE places (
        place_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        tenant_id BIGINT UNSIGNED NOT NULL,
        place_name VARCHAR(150) NOT NULL,
        status ENUM('ACTIVE', 'INACTIVE') NOT NULL DEFAULT 'ACTIVE',
        location POINT NOT NULL SRID 4326,
        INDEX ix_places_tenant_status (tenant_id, status),
        SPATIAL INDEX sx_places_location (location)
    ) ENGINE=InnoDB;

Thêm điểm:

    INSERT INTO places(tenant_id, place_name, location)
    VALUES (
        10,
        'Office A',
        ST_GeomFromText(
            'POINT(106.7 10.8)',
            4326,
            'axis-order=long-lat'
        )
    );

Tìm khoảng cách tới điểm truy vấn:

    SET @origin = ST_GeomFromText(
        'POINT(106.69 10.79)',
        4326,
        'axis-order=long-lat'
    );

    SELECT
        place_id,
        place_name,
        ST_Distance(location, @origin, 'metre') AS distance_m
    FROM places
    ORDER BY distance_m, place_id
    LIMIT 10;

Ví dụ này rõ đơn vị và có tie-breaker ổn định theo place_id. Tuy nhiên, nó vẫn có thể tính khoảng cách cho nhiều hàng; với bảng lớn, cần thêm bước lọc ứng viên và kiểm tra execution plan.

### 12.1. Lọc ứng viên trước, tính khoảng cách sau

Một mẫu truy vấn thực tế có thể:

1. Lọc theo tenant, trạng thái hoặc khu vực nghiệp vụ bằng B-tree index.
2. Dùng spatial predicate/bounding rectangle để thu hẹp ứng viên.
3. Tính ST_Distance() trên ứng viên.
4. Sắp xếp theo khoảng cách và khóa duy nhất.

Ví dụ:

    SELECT
        place_id,
        place_name,
        ST_Distance(location, @origin, 'metre') AS distance_m
    FROM places
    WHERE tenant_id = 10
      AND status = 'ACTIVE'
    ORDER BY distance_m, place_id
    LIMIT 20;

Nếu cần truy vấn bán kính với spatial index, hãy thiết kế điều kiện MBR hoặc spatial relation phù hợp, rồi dùng ST_Distance() để xác nhận khoảng cách thực. Bounding rectangle chỉ là bước lọc ứng viên; góc của hình chữ nhật có thể nằm ngoài vòng tròn bán kính nên phải tính khoảng cách chính xác sau đó.

### 12.2. Tránh đổi SRID trong từng hàng của WHERE

Không nên biến đổi mọi row trong cột spatial ở mỗi lần truy vấn nếu có thể chuẩn hóa dữ liệu trước. Ví dụ:

    WHERE ST_Distance(
        ST_Transform(location, 4326),
        @origin
    ) < 1000

biểu thức biến đổi theo từng hàng có thể khiến optimizer khó sử dụng spatial index trên cột gốc. Nên chuẩn hóa về một SRS lưu trữ nhất quán, hoặc tạo bước xử lý trước phù hợp.

## 13. Điều kiện đầu vào và lỗi khoảng cách thường gặp

Trước khi gọi hàm khoảng cách, kiểm tra:

- Geometry có hợp lệ và well-formed không?
- SRID có được định nghĩa không?
- Các geometry có cùng SRS không?
- Longitude/latitude có nằm trong miền hợp lệ không?
- Geometry type có được hàm hỗ trợ không?
- Unit có tồn tại trong ST_UNITS_OF_MEASURE không?
- SRS có đơn vị chiều dài không?

### 13.1. Kiểm tra SRID

    SELECT
        id,
        ST_SRID(location) AS srid
    FROM places
    WHERE id <= 20;

### 13.2. Kiểm tra geometry hợp lệ

    SELECT
        id,
        ST_IsValid(location) AS is_valid
    FROM places;

ST_IsValid() kiểm tra tính hợp lệ hình học theo OGC. Nó không thay thế kiểm tra SRID, axis-order hoặc ý nghĩa nghiệp vụ của tọa độ.

### 13.3. Kiểm tra unit

    SELECT UNIT_NAME, UNIT_TYPE
    FROM INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE
    WHERE UNIT_NAME IN ('metre', 'foot', 'kilometre');

Nếu unit không xuất hiện, không truyền nó vào ST_Distance().

### 13.4. Các lỗi phổ biến

| Tình huống | Lỗi/hành vi |
|---|---|
| Hai geometry khác SRID | ER_GIS_DIFFERENT_SRIDS |
| SRID không có trong data dictionary | ER_SRS_NOT_FOUND |
| Unit không hỗ trợ | ER_UNIT_NOT_FOUND |
| Dùng linear unit với SRID 0 | ER_GEOMETRY_IN_UNKNOWN_LENGTH_UNIT |
| Longitude/latitude ngoài miền | Lỗi longitude/latitude out of range |
| ST_Distance_Sphere nhận projected SRS | ER_NOT_IMPLEMENTED_FOR_PROJECTED_SRS |
| ST_Distance_Sphere nhận geometry type không hỗ trợ | Lỗi NOT IMPLEMENTED tương ứng |
| Radius không dương | ER_NONPOSITIVE_RADIUS |

## 14. Bài toán thực tế: giao hàng trong bán kính 5 km

Giả sử ứng dụng cần tìm tài xế trong phạm vi 5 km quanh một điểm giao hàng. Bảng lưu tọa độ WGS 84:

    CREATE TABLE driver (
        driver_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        tenant_id BIGINT UNSIGNED NOT NULL,
        driver_name VARCHAR(120) NOT NULL,
        status ENUM('ONLINE', 'OFFLINE', 'BUSY') NOT NULL,
        location POINT NOT NULL SRID 4326,
        SPATIAL INDEX sx_driver_location (location),
        INDEX ix_driver_tenant_status (tenant_id, status)
    ) ENGINE=InnoDB;

Tạo điểm đơn hàng:

    SET @pickup = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

Truy vấn cơ bản:

    SELECT
        driver_id,
        driver_name,
        ST_Distance(location, @pickup, 'metre') AS distance_m
    FROM driver
    WHERE tenant_id = 10
      AND status = 'ONLINE'
      AND ST_Distance(location, @pickup, 'metre') <= 5000
    ORDER BY distance_m, driver_id
    LIMIT 20;

Truy vấn này diễn đạt đúng điều kiện nghiệp vụ nhưng không nên mặc định optimizer sử dụng spatial index cho predicate ST_Distance(...) <= 5000. Khi số tài xế lớn, hãy tạo một bước candidate filter có thể tận dụng spatial index hoặc một bounding box đã tính trước, sau đó xác nhận lại bằng khoảng cách địa trắc.

Không dùng chênh lệch độ latitude/longitude nhân một hằng số duy nhất để thay thế chính xác cho phép tính địa trắc trên mọi vị trí. Nếu dùng bounding box xấp xỉ, hãy tính biên theo latitude/longitude, xử lý vĩ độ cao và đường đổi ngày quốc tế, rồi xác nhận lại bằng ST_Distance().

## 15. Chọn mô hình đo theo yêu cầu nghiệp vụ

| Bài toán | SRS gợi ý | Hàm/kỹ thuật | Ghi chú |
|---|---|---|---|
| Tọa độ GPS toàn cầu | Geographic, thường WGS 84 (4326) | ST_Distance | Geodetic trên ellipsoid |
| Tìm nhanh khoảng cách điểm gần nhau, chấp nhận mô hình cầu | Geographic hoặc SRID 0 theo quy tắc riêng | ST_Distance_Sphere | Point/MultiPoint, mét |
| Đo đạc khu vực trong hệ chiếu phù hợp | Projected SRS | ST_Distance | Đơn vị chiều dài của SRS |
| Mặt bằng nhà máy | Cartesian SRS có đơn vị rõ ràng | ST_Distance | Khoảng cách phẳng |
| Dữ liệu GIS hỗn hợp SRID | Chuẩn hóa về SRS chung | ST_Transform rồi ST_Distance | Không chỉ gán nhãn bằng ST_SRID |
| Tìm đối tượng trong khu vực | SRID-restricted column + SPATIAL index | MBR/spatial predicate, sau đó distance chính xác | Bounding box chỉ lọc ứng viên |

SRS phải phản ánh cách dữ liệu được thu thập và cách nghiệp vụ đo. Không chọn EPSG:4326 cho mọi bài toán chỉ vì đó là SRID GPS phổ biến; nếu cần đo chính xác trên một vùng địa phương, một projected SRS phù hợp có thể thích hợp hơn.

## 16. Lab thực hành: so sánh SRID 0, geographic và sphere

Chạy trong schema thử nghiệm.

### Bước 1: tạo hai điểm Cartesian

    SET @c1 = ST_GeomFromText('POINT(1 1)', 0);
    SET @c2 = ST_GeomFromText('POINT(4 5)', 0);

    SELECT
        ST_SRID(@c1) AS srid,
        ST_Distance(@c1, @c2) AS coordinate_distance;

Kỳ vọng khoảng cách là 5 đơn vị tọa độ, không có đơn vị mét.

### Bước 2: thử yêu cầu metre với SRID 0

    SELECT ST_Distance(@c1, @c2, 'metre');

Quan sát lỗi về unknown length unit. Giải thích vì sao MySQL không thể tự quy đổi.

### Bước 3: tạo hai điểm WGS 84

    SET @g1 = ST_GeomFromText(
        'POINT(106.7 10.8)',
        4326,
        'axis-order=long-lat'
    );

    SET @g2 = ST_GeomFromText(
        'POINT(106.71 10.8)',
        4326,
        'axis-order=long-lat'
    );

### Bước 4: so sánh ST_Distance và ST_Distance_Sphere

    SELECT
        ST_Distance(@g1, @g2) AS ellipsoid_m,
        ST_Distance_Sphere(@g1, @g2) AS sphere_m;

Hai kết quả gần nhau nhưng không nhất thiết bằng nhau vì một hàm đo trên ellipsoid, hàm kia dùng mô hình quả cầu.

### Bước 5: thử đổi đơn vị

    SELECT
        ST_Distance(@g1, @g2, 'metre') AS distance_m,
        ST_Distance(@g1, @g2, 'foot') AS distance_ft,
        ST_Distance(@g1, @g2, 'kilometre') AS distance_km;

Đối chiếu tỷ lệ quy đổi và truy vấn ST_UNITS_OF_MEASURE để xác nhận unit name.

### Bước 6: thử lỗi SRID khác nhau

    SET @p3857 = ST_GeomFromText(
        'POINT(11886500 1220000)',
        3857
    );

    SELECT ST_Distance(@g1, @p3857);

Quan sát lỗi khác SRID. Sau đó:

    SET @p4326 = ST_Transform(@p3857, 4326);
    SELECT ST_Distance(@g1, @p4326);

### Bước 7: xác minh trục tọa độ

    SELECT
        ST_AsText(@g1),
        ST_Longitude(@g1),
        ST_Latitude(@g1),
        ST_SRID(@g1);

Tạo lại cùng vị trí bằng axis-order=srid-defined và axis-order=long-lat với đầu vào phù hợp; xác nhận hai cách biểu diễn cho ra cùng một vị trí.

## 17. Các sai lầm thường gặp

- Nghĩ mọi tọa độ số đều có đơn vị mét.
- Dùng SRID 0 cho longitude/latitude rồi gọi ST_Distance và xem kết quả là mét.
- Dùng ST_Distance_Sphere cho projected SRS.
- Dùng ST_Distance_Sphere cho Polygon hoặc LineString.
- Dùng đơn vị degree trong đối số unit của ST_Distance.
- Dùng tên đơn vị tự nghĩ ra mà không kiểm tra ST_UNITS_OF_MEASURE.
- Quên rằng geometry đầu vào phải cùng SRS.
- Dùng ST_SRID như thể nó chuyển đổi tọa độ.
- Dùng ST_Transform mà không xác minh SRS nguồn/đích được hỗ trợ.
- Đảo longitude/latitude không đúng axis-order của SRS.
- Coi EPSG:3857 là hệ đo khoảng cách chính xác trên toàn cầu.
- Tạo spatial index nhưng cột không NOT NULL hoặc không có SRID cố định.
- Cho rằng optimizer luôn dùng spatial index khi WHERE có ST_Distance.
- Dùng bounding rectangle làm kết quả cuối mà không kiểm tra khoảng cách chính xác.
- Không kiểm tra dữ liệu sai miền longitude/latitude.
- Không kiểm tra SRID hỗn hợp trước khi thêm SRID restriction.

## 18. Checklist trước khi triển khai

- Đã xác định loại SRS: Cartesian, projected hay geographic.
- Đã xác định SRID của tất cả geometry đầu vào.
- Đã xác nhận SRID tồn tại trong INFORMATION_SCHEMA.ST_SPATIAL_REFERENCE_SYSTEMS.
- Đã thống nhất thứ tự longitude/latitude hay axis order theo SRS.
- Đã kiểm tra longitude/latitude trong miền hợp lệ.
- Đã chọn ST_Distance hay ST_Distance_Sphere theo yêu cầu độ chính xác.
- Đã xác định đơn vị trả về và kiểm tra unit trong ST_UNITS_OF_MEASURE.
- Đã tránh chuyển đổi đơn vị chiều dài từ SRID 0.
- Đã chuyển đổi geometry bằng ST_Transform khi cần đổi SRS.
- Đã không dùng ST_SRID để thay thế phép biến đổi tọa độ.
- Đã kiểm tra geometry type mà hàm khoảng cách hỗ trợ.
- Đã khai báo cột spatial NOT NULL SRID cố định nếu cần SPATIAL index.
- Đã kiểm tra execution plan thay vì giả định spatial index được dùng.
- Đã dùng bounding box làm candidate filter và khoảng cách chính xác làm bước xác nhận.
- Đã kiểm thử dữ liệu biên, vị trí xa nhau và vĩ độ cao.
- Đã ghi lại SRS, đơn vị và quy tắc axis order trong hợp đồng API/schema.

## 19. Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Spatial Reference System Support: https://dev.mysql.com/doc/refman/8.4/en/spatial-reference-systems.html
- MySQL 8.4 Reference Manual — Spatial Data Types: https://dev.mysql.com/doc/refman/8.4/en/spatial-type-overview.html
- MySQL 8.4 Reference Manual — Functions That Create Geometry Values from WKT: https://dev.mysql.com/doc/refman/8.4/en/gis-wkt-functions.html
- MySQL 8.4 Reference Manual — Spatial Relation Functions That Use Object Shapes (ST_Distance): https://dev.mysql.com/doc/refman/8.4/en/spatial-relation-functions-object-shapes.html
- MySQL 8.4 Reference Manual — Spatial Convenience Functions (ST_Distance_Sphere): https://dev.mysql.com/doc/refman/8.4/en/spatial-convenience-functions.html
- MySQL 8.4 Reference Manual — INFORMATION_SCHEMA.ST_UNITS_OF_MEASURE: https://dev.mysql.com/doc/refman/8.4/en/information-schema-st-units-of-measure-table.html
- MySQL 8.4 Reference Manual — Creating Spatial Indexes: https://dev.mysql.com/doc/refman/8.4/en/creating-spatial-indexes.html
- MySQL 8.4 Reference Manual — Spatial Operator Functions (ST_Transform): https://dev.mysql.com/doc/refman/8.4/en/spatial-operator-functions.html

Khoảng cách chỉ có ý nghĩa khi geometry dùng đúng SRS và đơn vị được hiểu đúng. ST_Distance() đo theo SRS, tính geodetic trên geographic SRS và cho phép chỉ định linear unit được MySQL hỗ trợ. ST_Distance_Sphere() trả mét theo mô hình quả cầu và chỉ nhận Point/MultiPoint trên các SRS được hỗ trợ. SRID 0 là mặt phẳng không có đơn vị; ST_SRID() chỉ đổi nhãn, còn ST_Transform() mới chuyển tọa độ. Trước khi tính, hãy kiểm tra SRID, axis-order, geometry type, unit và khả năng chuyển đổi; nếu cần hiệu năng, dùng spatial index để lọc ứng viên rồi xác nhận bằng khoảng cách chính xác.
