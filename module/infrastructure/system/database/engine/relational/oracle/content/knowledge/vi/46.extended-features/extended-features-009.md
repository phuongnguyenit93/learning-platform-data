# Oracle Spatial: hình học, hệ tọa độ và truy vấn không gian

Oracle Spatial lưu trữ, lập chỉ mục và truy vấn dữ liệu có vị trí trong cùng Oracle Database với dữ liệu nghiệp vụ. Một cửa hàng có thể lưu tọa độ, một tuyến đường có thể lưu đường hình học, một quận có thể lưu polygon ranh giới; sau đó SQL có thể tìm cửa hàng nằm trong quận, tuyến đường giao với khu vực cấm hoặc các điểm gần một địa chỉ.

Kiểu dữ liệu trung tâm là `SDO_GEOMETRY`. Một geometry mô tả point, line, polygon hoặc tập hợp các phần tử hình học. Nhưng tọa độ chỉ có ý nghĩa khi biết **hệ tọa độ** (coordinate reference system - CRS), đơn vị, datum và quy tắc diễn giải. Cặp số `(106.7, 10.8)` có thể là longitude/latitude, tọa độ phẳng hoặc một hệ tọa độ cục bộ; nếu gắn sai SRID, kết quả khoảng cách và vị trí có thể sai dù geometry vẫn hợp lệ về cú pháp.

Quy trình xây dựng một lớp dữ liệu không gian thường gồm:

1. Chọn mô hình hình học và CRS đúng với nguồn dữ liệu.
2. Tạo cột `SDO_GEOMETRY`, nạp tọa độ và gắn SRID.
3. Khai báo metadata cho lớp trong `USER_SDO_GEOM_METADATA`.
4. Kiểm tra tính hợp lệ của geometry và phạm vi tọa độ.
5. Tạo spatial index, thường là R-tree với `MDSYS.SPATIAL_INDEX_V2`.
6. Dùng spatial operators để lọc và xác định quan hệ không gian.
7. Theo dõi tolerance, hiệu năng, dữ liệu CRS và quá trình cập nhật.

Tài liệu này tập trung vào ba nền tảng: **hình học**, **hệ tọa độ** và **truy vấn không gian** trong Oracle Spatial 19c.

## 1. Oracle Spatial và mô hình dữ liệu không gian

### 1.1 Dữ liệu không gian là gì?

Dữ liệu không gian mô tả vị trí, hình dạng và quan hệ của đối tượng trong không gian. Ví dụ:

| Đối tượng nghiệp vụ | Geometry thường dùng | Câu hỏi có thể trả lời |
|---|---|---|
| ATM, cửa hàng, trạm xe buýt | Point | Điểm nào gần khách hàng nhất? |
| Đường phố, đường ống, tuyến xe | LineString | Tuyến nào giao với khu vực thi công? |
| Quận, phường, khu bảo tồn | Polygon | Địa chỉ này thuộc phường nào? |
| Nhiều vùng rời rạc của một khu vực | MultiPolygon | Những vùng nào thuộc cùng một tỉnh? |
| Mô hình địa hình hoặc công trình | 3D surface/solid | Đối tượng có giao nhau trong không gian 3D không? |

Oracle Spatial hỗ trợ lưu geometry trong kiểu object-relational `SDO_GEOMETRY`, cùng với các operator, procedure và function để phân tích vị trí và quan hệ.

### 1.2 Layer, geometry và element

Mô hình dữ liệu có ba cấp:

- **Layer:** tập geometry trong một cột của một bảng, ví dụ `STORES.LOCATION`.
- **Geometry:** hình học của một đối tượng, ví dụ vị trí một cửa hàng hoặc ranh giới một quận.
- **Element:** thành phần của geometry, ví dụ một point, một line hoặc một ring của polygon.

Một layer thường có một primary key để nhận diện từng hàng. Mỗi geometry được lưu trong một hàng của bảng, trong cột kiểu `SDO_GEOMETRY`.

### 1.3 Hình học vector và raster

Oracle Spatial có hỗ trợ nhiều loại dữ liệu không gian. `SDO_GEOMETRY` chủ yếu mô tả dữ liệu vector gồm điểm, đường, vùng, bề mặt và khối. Dữ liệu raster, point cloud, topology, network hoặc graph có mô hình và API chuyên biệt; không nên ép mọi dữ liệu không gian vào một polygon hoặc một cột SDO_GEOMETRY.

## 2. Kiểu dữ liệu SDO_GEOMETRY

### 2.1 Cấu trúc object

Oracle định nghĩa `SDO_GEOMETRY` với năm thuộc tính:

~~~sql
CREATE TYPE sdo_geometry AS OBJECT (
    sdo_gtype      NUMBER,
    sdo_srid       NUMBER,
    sdo_point      SDO_POINT_TYPE,
    sdo_elem_info  SDO_ELEM_INFO_ARRAY,
    sdo_ordinates  SDO_ORDINATE_ARRAY
);
~~~

| Thuộc tính | Vai trò |
|---|---|
| `SDO_GTYPE` | Cho biết số chiều, vị trí measure dimension (nếu có) và loại geometry |
| `SDO_SRID` | Mã hệ tọa độ gắn với geometry; NULL nghĩa là chưa gắn CRS |
| `SDO_POINT` | Cấu trúc point đơn giản với X, Y, Z; dùng khi geometry là một point đơn giản |
| `SDO_ELEM_INFO` | Mô tả cách chia và diễn giải các element trong mảng ordinates |
| `SDO_ORDINATES` | Dãy số tọa độ của các vertex |

Một point đơn giản có thể dùng `SDO_POINT` và để hai mảng element/ordinate là NULL. Với line, polygon, multi-geometry hoặc geometry phức tạp, thông tin thường nằm trong `SDO_ELEM_INFO` và `SDO_ORDINATES`.

### 2.2 SDO_GTYPE theo mẫu DLTT

`SDO_GTYPE` là một số bốn chữ số có cấu trúc:

~~~text
D L T T
| | | |
| | +-- TT: loại geometry
| +---- L: vị trí chiều measure (LRS), hoặc 0 nếu không có
+------ D: số chiều
~~~

Ví dụ:

| GTYPE | Diễn giải |
|---:|---|
| 2001 | Point 2D |
| 2002 | LineString 2D |
| 2003 | Polygon 2D |
| 2004 | GeometryCollection 2D |
| 2005 | MultiPoint 2D |
| 2006 | MultiLine/MultiCurve 2D |
| 2007 | MultiPolygon/MultiSurface 2D |
| 3001 | Point 3D |
| 3002 | LineString 3D |
| 3003 | Polygon 3D |
| 3008 | Solid 3D |
| 3009 | MultiSolid 3D |

Chữ số đầu tiên `D` là số ordinates trên mỗi vertex: 2, 3 hoặc 4. Ví dụ `2003` là polygon 2D; `3001` là point 3D. Chữ số `L` chỉ vị trí measure trong LRS geometry, không phải một chiều không gian thông thường. Các geometry trong cùng một layer phải có cùng dimensionality phù hợp với metadata và spatial index.

### 2.3 Point 2D

Một point đơn giản có thể được tạo như sau:

~~~sql
SDO_GEOMETRY(
    2001,
    4326,
    SDO_POINT_TYPE(106.7000, 10.7800, NULL),
    NULL,
    NULL
)
~~~

Trong ví dụ SRID 4326, X là longitude và Y là latitude theo quy ước tọa độ SDO cho dữ liệu này. Cần xác nhận thứ tự trục của nguồn nhập; không tự động giả định mọi định dạng trao đổi đều dùng cùng thứ tự.

### 2.4 LineString

Một đường thẳng gồm chuỗi vertex nối với nhau:

~~~sql
SDO_GEOMETRY(
    2002,
    4326,
    NULL,
    SDO_ELEM_INFO_ARRAY(1, 2, 1),
    SDO_ORDINATE_ARRAY(
        106.7000, 10.7800,
        106.7050, 10.7850,
        106.7100, 10.7900
    )
)
~~~

Triplet `(1, 2, 1)` có nghĩa element bắt đầu tại ordinate thứ nhất, ETYPE 2 là line, interpretation 1 là chuỗi đoạn thẳng nối các điểm liên tiếp.

### 2.5 Polygon

Polygon 2D có thể được biểu diễn bằng một ring khép kín:

~~~sql
SDO_GEOMETRY(
    2003,
    4326,
    NULL,
    SDO_ELEM_INFO_ARRAY(1, 1003, 1),
    SDO_ORDINATE_ARRAY(
        106.7000, 10.7800,
        106.7100, 10.7800,
        106.7100, 10.7900,
        106.7000, 10.7900,
        106.7000, 10.7800
    )
)
~~~

Polygon phải khép kín: tọa độ cuối cùng của ring trùng với tọa độ đầu tiên. Theo quy tắc Oracle, ring ngoài (ETYPE 1003) phải theo chiều ngược kim đồng hồ; ring trong (ETYPE 2003, lỗ) phải theo chiều kim đồng hồ.

### 2.6 Polygon có lỗ

Một polygon có thể có một ring ngoài và nhiều ring trong. Ring ngoài được khai báo trước, tiếp theo là các ring trong. Ví dụ cấu trúc:

~~~sql
SDO_ELEM_INFO_ARRAY(
    1, 1003, 1,   -- exterior ring
    11, 2003, 1   -- interior ring (hole)
)
~~~

Các offset trỏ đến vị trí bắt đầu của từng element trong `SDO_ORDINATES`. Khi tạo polygon có lỗ, phải kiểm tra thứ tự ring, chiều quay, tính khép kín và việc ring trong nằm đúng trong ring ngoài.

### 2.7 Rectangle và circle

Oracle có cách biểu diễn tối ưu cho một số hình đơn giản. Với hình chữ nhật được định nghĩa bởi hai góc đối diện, interpretation 3 có thể dùng hai điểm:

~~~sql
SDO_GEOMETRY(
    2003,
    NULL,
    NULL,
    SDO_ELEM_INFO_ARRAY(1, 1003, 3),
    SDO_ORDINATE_ARRAY(0, 0, 10, 5)
)
~~~

Với circle, interpretation 4 dùng ba điểm để xác định đường tròn theo mô hình Oracle:

~~~sql
SDO_GEOMETRY(
    2003,
    NULL,
    NULL,
    SDO_ELEM_INFO_ARRAY(1, 1003, 4),
    SDO_ORDINATE_ARRAY(8, 7, 10, 9, 8, 11)
)
~~~

Các ví dụ này dùng tọa độ Cartesian không gắn SRID. Với dữ liệu địa lý, hãy chọn CRS và mô hình đường cong phù hợp; không suy ra khoảng cách hoặc diện tích thực tế từ tọa độ phẳng tùy ý.

### 2.8 SDO_ELEM_INFO và SDO_ORDINATES

`SDO_ELEM_INFO` là mảng gồm các nhóm ba số (triplet):

1. `SDO_STARTING_OFFSET`: vị trí bắt đầu trong `SDO_ORDINATES`.
2. `SDO_ETYPE`: loại element.
3. `SDO_INTERPRETATION`: cách diễn giải chuỗi ordinates hoặc thành phần compound.

Offset bắt đầu từ **1**, không phải 0. Một geometry nhiều element có nhiều triplet; element tiếp theo bắt đầu tại offset đã khai báo. Các giá trị ETYPE thường gặp:

| ETYPE | Ý nghĩa |
|---:|---|
| 1 | Point hoặc multipoint element tùy interpretation |
| 2 | LineString |
| 1003 | Ring ngoài của polygon |
| 2003 | Ring trong của polygon |
| 1005 / 2005 | Compound polygon ring ngoài/trong |
| 1006 / 2006 | Surface element |
| 1007 | Solid element |

Với ETYPE 1003/2003, interpretation 1 thường là ring gồm các đoạn thẳng; interpretation 3 biểu diễn rectangle; interpretation 4 biểu diễn circle. Compound elements có quy tắc triplet riêng để mô tả các subelement liên tiếp.

Không nên tự sửa `SDO_ELEM_INFO` bằng cách đoán offset. Khi geometry phức tạp, hãy dùng constructor, WKT/WKB import, SDO_UTIL hoặc công cụ GIS để tạo đúng cấu trúc, sau đó xác thực bằng `SDO_GEOM.VALIDATE_GEOMETRY_WITH_CONTEXT`.

## 3. Hệ tọa độ và SRID

### 3.1 Vì sao tọa độ phải đi kèm CRS?

CRS định nghĩa cách diễn giải tọa độ và quan hệ của nó với thế giới thực. Một cặp số có thể là độ kinh/vĩ, mét trên mặt phẳng chiếu, feet trong hệ địa phương hoặc tọa độ mô hình công trình. Nếu gắn nhầm SRID, Oracle có thể thực hiện phép biến đổi hoặc tính khoảng cách sai mà không biết dữ liệu nguồn đã bị gán sai.

Một CRS thường xác định:

- Hệ trục và thứ tự trục.
- Đơn vị đo.
- Datum/ellipsoid nếu là hệ địa lý.
- Phép chiếu nếu là hệ tọa độ phẳng.
- Mã định danh SRID dùng trong Oracle.

### 3.2 Các loại hệ tọa độ

| Loại | Mô tả | Ví dụ dữ liệu |
|---|---|---|
| Geodetic/geographic | Kinh độ, vĩ độ góc gắn với datum của Trái Đất | Longitude/latitude theo WGS 84 |
| Projected | Tọa độ Cartesian trên mặt phẳng sau phép chiếu | UTM Easting/Northing, đơn vị mét |
| Cartesian/local | Hệ tọa độ cục bộ không gắn với Trái Đất | Sơ đồ nhà xưởng, tọa độ CAD |
| 3D CRS | Hệ có trục Z hoặc chiều cao theo datum/vertical CRS | Tọa độ không gian 3D |

### 3.3 Geodetic và projected không giống nhau

Geodetic coordinates thường lưu longitude/latitude theo đơn vị góc. Không thể coi một độ kinh độ luôn bằng một khoảng cách mét cố định: độ dài tương ứng thay đổi theo vĩ độ. Projected coordinates biểu diễn vị trí trên mặt phẳng, thường dùng mét hoặc feet; khoảng cách phẳng dễ tính hơn nhưng phép chiếu có biến dạng theo khu vực và mục tiêu.

Với dữ liệu toàn cầu, geodetic CRS phù hợp để lưu vị trí địa lý. Với phân tích khoảng cách/diện tích cục bộ, một projected CRS phù hợp với vùng nghiên cứu có thể thuận tiện hơn. Chọn CRS theo yêu cầu độ chính xác và phạm vi, không chỉ theo việc dữ liệu nhìn giống longitude/latitude.

### 3.4 SRID trong SDO_GEOMETRY

`SDO_SRID` nhận giá trị từ cột SRID trong `SDO_COORD_REF_SYS`. Nếu SRID NULL, geometry không được gắn CRS. Nếu SRID khác NULL, metadata của layer cũng phải khai báo cùng SRID.

Ví dụ:

~~~sql
SELECT srid,
       coord_ref_sys_name,
       coord_sys_name,
       datum_name,
       geogcs_datum_name
FROM sdo_coord_ref_sys
WHERE srid IN (4326, 3857);
~~~

SRID 4326 thường được dùng cho WGS 84 longitude/latitude; SRID 3857 là Web Mercator projected coordinates. Không được đổi SRID của geometry chỉ bằng cách thay số trong thuộc tính nếu ordinates vẫn đang ở CRS cũ.

### 3.5 Kiểm tra CRS trong Oracle

~~~sql
SELECT srid,
       coord_ref_sys_name,
       coord_sys_type,
       coord_sys_name,
       datum_name,
       geogcs_datum_name
FROM sdo_coord_ref_sys
WHERE srid = :p_srid;
~~~

Các cột cụ thể có thể khác theo release và metadata view. Có thể tra `SDO_COORD_REF_SYS`, `SDO_COORD_SYS`, `SDO_DATUMS` và các view liên quan để hiểu CRS và datum. Đối chiếu với nguồn EPSG hoặc metadata của nhà cung cấp dữ liệu.

### 3.6 Thứ tự trục và đơn vị

Trong SDO geometry thông thường, hai ordinates đầu tiên được hiểu là X rồi Y. Với SRID địa lý 4326, ví dụ point thường dùng X=longitude, Y=latitude. Tuy nhiên, một số định dạng và API bên ngoài có quy tắc axis order khác; hãy kiểm tra tài liệu trao đổi dữ liệu và chuyển đổi rõ ràng khi nhập.

Đối với geodetic data, các phép đo distance/area của Oracle có quy tắc đơn vị riêng và có thể chỉ định đơn vị qua tham số `unit`. Với projected/local data, đơn vị phụ thuộc CRS. Không so sánh một giá trị 100 với 100 mét nếu CRS thực tế đang dùng feet hoặc độ.

### 3.7 Tolerance

Tolerance biểu diễn độ chính xác không gian mà Oracle dùng để quyết định các điểm/đường gần nhau có được xem là trùng hoặc tiếp xúc hay không. Nó được khai báo cho từng chiều trong `SDO_DIM_ARRAY` metadata.

- Với geodetic data, tolerance được diễn giải theo mét.
- Với non-geodetic data, tolerance dùng đơn vị của CRS.
- Tolerance quá lớn có thể làm hai đối tượng gần nhau bị xem như trùng/tiếp xúc hoặc làm thay đổi kết quả khoảng cách.
- Tolerance quá nhỏ so với độ chính xác dữ liệu có thể khiến tính toán nhạy với sai số số thực và phát sinh geometry validation errors.

Chọn tolerance dựa trên độ chính xác của nguồn dữ liệu, yêu cầu nghiệp vụ và khoảng cách nhỏ nhất có ý nghĩa. Không sao chép một giá trị tolerance từ ví dụ khác mà không xem đơn vị và độ chính xác.

### 3.8 Biến đổi hệ tọa độ

`SDO_CS.TRANSFORM` chuyển tọa độ geometry từ CRS hiện tại sang SRID đích:

~~~sql
SELECT SDO_CS.TRANSFORM(shape, 3857) AS shape_3857
FROM city_locations;
~~~

Hãy chắc chắn `shape.SDO_SRID` xác định đúng CRS nguồn trước khi transform. Phép biến đổi cần dữ liệu định nghĩa CRS và datum transformation phù hợp trong database. Nếu dữ liệu gốc không có CRS đáng tin cậy, phải xác định CRS nguồn trước; gán SRID đích không phải là biến đổi tọa độ.

Khi hai geometry đầu vào có SRID khác nhau:

- Spatial operators có thể biến đổi tạm query window (tham số geometry thứ hai) về CRS của geometry column.
- Các function trong `SDO_GEOM` nhận hai geometry thường yêu cầu chúng cùng CRS.
- Nếu cần lưu dữ liệu ở một CRS thống nhất, hãy transform trước khi insert/update và kiểm tra kết quả.

## 4. Tạo bảng và metadata không gian

### 4.1 Tạo bảng có cột SDO_GEOMETRY

~~~sql
CREATE TABLE city_locations (
    location_id NUMBER PRIMARY KEY,
    location_name VARCHAR2(100) NOT NULL,
    location_type VARCHAR2(30),
    shape SDO_GEOMETRY
);
~~~

Mỗi geometry row được nhận diện bằng primary key `LOCATION_ID`. Cột geometry có thể NULL nếu nghiệp vụ cho phép, nhưng các row cần truy vấn không gian phải có geometry hợp lệ.

### 4.2 Khai báo USER_SDO_GEOM_METADATA

Trước khi tạo spatial index, khai báo dimensional metadata cho cặp table-column:

~~~sql
INSERT INTO user_sdo_geom_metadata (
    table_name,
    column_name,
    diminfo,
    srid
)
VALUES (
    'CITY_LOCATIONS',
    'SHAPE',
    SDO_DIM_ARRAY(
        SDO_DIM_ELEMENT('Longitude', -180, 180, 0.05),
        SDO_DIM_ELEMENT('Latitude',   -90,  90, 0.05)
    ),
    4326
);
~~~

`DIMINFO` chứa một `SDO_DIM_ELEMENT` cho mỗi chiều: tên chiều, lower bound, upper bound và tolerance. Ví dụ trên giả định layer là longitude/latitude WGS 84 2D. Tolerance 0.05 trong ví dụ tương ứng 5 cm đối với geodetic data theo quy ước Oracle; đây chỉ là giá trị minh họa và phải được chọn theo yêu cầu độ chính xác của ứng dụng.

Metadata được quản lý qua view `USER_SDO_GEOM_METADATA`, `ALL_SDO_GEOM_METADATA` hoặc `DBA_SDO_GEOM_METADATA`. Không cập nhật trực tiếp các bảng nội bộ của schema MDSYS.

### 4.3 Kiểm tra metadata

~~~sql
SELECT table_name,
       column_name,
       diminfo,
       srid
FROM user_sdo_geom_metadata
WHERE table_name = 'CITY_LOCATIONS'
  AND column_name = 'SHAPE';
~~~

Đảm bảo SRID metadata trùng với `SDO_SRID` của geometry. Tất cả geometry trong cùng một cột được spatial index phải có cùng SRID.

### 4.4 Nạp point data

~~~sql
INSERT INTO city_locations (
    location_id,
    location_name,
    location_type,
    shape
)
VALUES (
    1,
    'Central Office',
    'OFFICE',
    SDO_GEOMETRY(
        2001,
        4326,
        SDO_POINT_TYPE(106.7000, 10.7800, NULL),
        NULL,
        NULL
    )
);
~~~

Các tọa độ là dữ liệu minh họa. Khi nhập dữ liệu thực, xác nhận CRS, axis order, datum và phạm vi tọa độ. Một tọa độ bị đảo longitude/latitude vẫn có thể nằm trong range hợp lệ ở một số khu vực, nên validation hình học không thay thế kiểm tra chất lượng nguồn.

## 5. Kiểm tra geometry trước khi truy vấn

### 5.1 Validate một geometry

~~~sql
SELECT location_id,
       SDO_GEOM.VALIDATE_GEOMETRY_WITH_CONTEXT(
           shape,
           diminfo
       ) AS validation_result
FROM city_locations c,
     user_sdo_geom_metadata m
WHERE m.table_name = 'CITY_LOCATIONS'
  AND m.column_name = 'SHAPE';
~~~

Hàm trả `TRUE` nếu geometry hợp lệ; nếu không, trả mã lỗi và context giúp xác định coordinate/edge/ring gây lỗi. Dạng gọi dùng DIMINFO cũng kiểm tra geometry nằm trong bounds đã khai báo.

### 5.2 Validate toàn layer

Có thể dùng `SDO_GEOM.VALIDATE_LAYER_WITH_CONTEXT` để kiểm tra toàn bộ geometry trong một layer. Thủ tục ghi các row không hợp lệ vào một result table đã tạo trước.

~~~sql
CREATE TABLE spatial_validation_errors (
    sdo_rowid ROWID,
    result VARCHAR2(4000)
);

BEGIN
    SDO_GEOM.VALIDATE_LAYER_WITH_CONTEXT(
        'CITY_LOCATIONS',
        'SHAPE',
        'SPATIAL_VALIDATION_ERRORS'
    );
END;
/
~~~

Sau đó đọc `SPATIAL_VALIDATION_ERRORS` và xử lý từng loại lỗi. Quyền thực thi và schema/table names phải phù hợp với cách gọi package trong môi trường.

### 5.3 Một số nguyên nhân geometry invalid

- Polygon không khép kín.
- Ring ngoài/ring trong có chiều quay không đúng.
- Polygon tự cắt (self-intersection).
- Hai vertex liên tiếp trùng nhau hoặc gần nhau trong tolerance.
- ETYPE không phù hợp với GTYPE.
- Offset hoặc interpretation trong ELEM_INFO sai.
- Geometry vượt bounds khai báo trong DIMINFO.
- Geometry có số chiều không khớp layer metadata.

Oracle khuyến nghị validate geometry trước khi chạy spatial operations. Một số lỗi có thể sửa bằng `SDO_UTIL.RECTIFY_GEOMETRY`; lỗi khác cần sửa nguồn dữ liệu hoặc chuyển đổi bằng quy trình có kiểm soát. Không tự động rectification trên dữ liệu production nếu chưa lưu bản gốc và kiểm tra ý nghĩa hình học sau sửa.

## 6. Spatial index và mô hình truy vấn hai tầng

### 6.1 R-tree spatial index

Spatial index mặc định thường là R-tree. R-tree tổ chức bounding rectangles của geometry để tìm nhanh những candidate có thể liên quan đến query window.

Tạo index:

~~~sql
CREATE INDEX city_locations_spx
ON city_locations(shape)
INDEXTYPE IS MDSYS.SPATIAL_INDEX_V2;
~~~

`SPATIAL_INDEX_V2` là lựa chọn được Oracle khuyến nghị cho spatial index mới trong các release hiện đại vì hỗ trợ system-managed index và đơn giản hóa quản lý, đặc biệt với partitioning. Kiểm tra điều kiện, quyền, tablespace và version trước khi tạo.

### 6.2 Điều kiện quan trọng của spatial index

- Geometry column phải có metadata phù hợp.
- Tất cả geometry trong một indexed column phải có cùng SRID.
- Dimensionality của metadata, geometry và index phải tương thích.
- Geometry cần hợp lệ trước khi dùng trong truy vấn.
- Khi tạo index thất bại, index có thể ở trạng thái invalid; xử lý theo lỗi và tạo lại sau khi sửa nguyên nhân.

### 6.3 Primary filter và secondary filter

Oracle dùng mô hình truy vấn hai tầng:

1. **Primary filter:** dùng spatial index và minimum bounding rectangle (MBR) để tìm candidate có thể tương tác. Bước này nhanh nhưng có thể trả false positives vì MBR không luôn trùng với hình dạng thật.
2. **Secondary filter:** kiểm tra quan hệ chính xác trên geometry candidate, ví dụ polygon thực có giao với polygon truy vấn hay không.

`SDO_FILTER` thực hiện primary filter. `SDO_RELATE` và các operator quan hệ khác có thể dùng spatial index để lọc candidate rồi đánh giá quan hệ hình học chính xác theo mask.

### 6.4 Không nhầm bounding box với geometry thật

Một đường cong hoặc polygon lõm có thể có bounding rectangle lớn hơn nhiều so với hình thật. Hai MBR có thể giao nhau dù hai geometry thực tế không giao nhau. Nếu nghiệp vụ cần quan hệ chính xác, dùng `SDO_RELATE` hoặc operator thích hợp, không chỉ dựa vào `SDO_FILTER`.

## 7. Spatial operators và truy vấn không gian

Spatial operators được dùng trong mệnh đề `WHERE` và trả về chuỗi `'TRUE'` hoặc `'FALSE'`. Khi so sánh, dùng chính xác `= 'TRUE'` viết hoa. Oracle khuyến nghị dùng spatial operator thay vì function tương đương khi operator đáp ứng yêu cầu vì operator có thể tận dụng spatial index.

### 7.1 SDO_FILTER: tìm candidate theo MBR

~~~sql
SELECT location_id,
       location_name
FROM city_locations c
WHERE SDO_FILTER(
          c.shape,
          SDO_GEOMETRY(
              2003,
              4326,
              NULL,
              SDO_ELEM_INFO_ARRAY(1, 1003, 3),
              SDO_ORDINATE_ARRAY(106.68, 10.76, 106.73, 10.81)
          )
      ) = 'TRUE';
~~~

`SDO_FILTER` chỉ kiểm tra primary filter (MBR). Kết quả là tập candidate; geometry có thể không giao nhau thật. Dùng nó khi cần lọc nhanh hoặc khi primary filter là đủ cho nghiệp vụ. Nếu cần kết quả chính xác, thêm secondary filter.

### 7.2 SDO_RELATE: kiểm tra quan hệ topology

`SDO_RELATE` kiểm tra quan hệ topology giữa geometry trong cột và query geometry. Ví dụ tìm các vùng có tương tác với một cửa sổ truy vấn:

~~~sql
SELECT location_id,
       location_name
FROM city_locations c
WHERE SDO_RELATE(
          c.shape,
          :query_geometry,
          'mask=ANYINTERACT'
      ) = 'TRUE';
~~~

Một số mask phổ biến:

| Mask | Ý nghĩa khái quát |
|---|---|
| ANYINTERACT | Hai geometry có bất kỳ tương tác không gian nào |
| CONTAINS | Geometry thứ nhất chứa geometry thứ hai |
| INSIDE | Geometry thứ nhất nằm bên trong geometry thứ hai |
| COVEREDBY / COVERS | Quan hệ bao phủ theo topology |
| EQUAL | Hai geometry bằng nhau về topology |
| TOUCH | Chạm biên nhưng phần trong không giao theo định nghĩa topology |
| OVERLAPBDYINTERSECT | Ranh giới giao nhau theo mask tương ứng |
| OVERLAPBDYDISJOINT | Các phần trong giao nhau nhưng ranh giới có quan hệ rời nhau theo mask |

Mask có hướng: `CONTAINS(A,B)` không tương đương `CONTAINS(B,A)`. Hãy kiểm tra định nghĩa topology cho đúng chiều của `geometry1` và `geometry2`.

### 7.3 SDO_WITHIN_DISTANCE: tìm trong bán kính

Ví dụ tìm các điểm cách query point không quá 5 km:

~~~sql
SELECT location_id,
       location_name
FROM city_locations c
WHERE SDO_WITHIN_DISTANCE(
          c.shape,
          :query_point,
          'distance=5 unit=KM'
      ) = 'TRUE';
~~~

Query geometry cần có CRS phù hợp. Với geodetic data, đơn vị mặc định của distance là mét; có thể chỉ định `unit=KM`, `unit=MILE` hoặc đơn vị được Oracle hỗ trợ. Tham số là chuỗi, nên dấu thập phân phải dùng dấu chấm bất kể NLS locale, ví dụ `'distance=2.5 unit=KM'`.

`SDO_WITHIN_DISTANCE` định nghĩa khoảng cách giữa hai geometry mở rộng (line/polygon) là khoảng cách ngắn nhất giữa các điểm trên hai bề mặt; hai polygon kề nhau có khoảng cách bằng 0. Operator cần spatial index trên geometry column; với geodetic data, index phải là R-tree.

### 7.4 SDO_NN: nearest neighbors

`SDO_NN` tìm các geometry gần nhất với query geometry. Ví dụ lấy 5 cửa hàng gần nhất:

~~~sql
SELECT c.location_id,
       c.location_name,
       SDO_NN_DISTANCE(1) AS distance_value
FROM city_locations c
WHERE SDO_NN(
          c.shape,
          :query_point,
          'sdo_num_res=5',
          1
      ) = 'TRUE'
ORDER BY distance_value;
~~~

Tham số cuối cùng `1` của `SDO_NN` phải trùng với tham số của `SDO_NN_DISTANCE(1)`. Với geodetic data, khoảng cách trả về mặc định là mét; với non-geodetic data, đơn vị theo CRS. `SDO_NN` cần spatial index trên geometry column.

Nếu có thêm điều kiện thuộc tính, ví dụ chỉ lấy cửa hàng loại `PHARMACY`, dùng `sdo_batch_size` để Oracle tìm đủ số candidate gần nhất thỏa điều kiện:

~~~sql
SELECT *
FROM (
    SELECT c.location_id,
           c.location_name,
           SDO_NN_DISTANCE(1) AS distance_value
    FROM city_locations c
    WHERE SDO_NN(
              c.shape,
              :query_point,
              'sdo_batch_size=30',
              1
          ) = 'TRUE'
      AND c.location_type = 'PHARMACY'
    ORDER BY distance_value
)
WHERE ROWNUM <= 5;
~~~

Không thay `sdo_batch_size` bằng `sdo_num_res=5` trong ví dụ có filter loại cửa hàng rồi giả định luôn nhận được 5 pharmacy gần nhất. `sdo_num_res` giới hạn số geometry nearest neighbor trước khi các điều kiện thuộc tính khác được áp dụng; có thể trả ít hơn 5 hoặc không có dòng.

### 7.5 SDO_JOIN: spatial join giữa hai layer

Spatial join so sánh geometry của hai bảng. Ví dụ tìm cặp vùng và tuyến đường có quan hệ tương tác:

~~~sql
SELECT p.area_id,
       r.road_id
FROM service_areas p,
     road_segments r
WHERE SDO_RELATE(
          r.shape,
          p.shape,
          'mask=ANYINTERACT'
      ) = 'TRUE';
~~~

Đây là spatial join sử dụng operator quan hệ. Với trường hợp cần spatial join chuyên biệt trên hai layer, `SDO_JOIN` là operator dành cho join theo quan hệ topology. Đảm bảo CRS và dimensionality của hai layer tương thích.

### 7.6 SDO_POINTINPOLYGON

`SDO_POINTINPOLYGON` phù hợp với một số trường hợp bảng có hai cột X/Y và cần kiểm tra điểm có nằm trong polygon hay không. Nếu dữ liệu đã lưu trong `SDO_GEOMETRY`, các operator như `SDO_RELATE` hoặc `SDO_CONTAINS` thường tự nhiên hơn.

### 7.7 SDO_FILTER kết hợp SDO_RELATE

Trong một số truy vấn phức tạp, có thể viết rõ hai bước:

~~~sql
SELECT c.location_id,
       c.location_name
FROM city_locations c
WHERE SDO_FILTER(c.shape, :query_geometry) = 'TRUE'
  AND SDO_RELATE(
          c.shape,
          :query_geometry,
          'mask=ANYINTERACT'
      ) = 'TRUE';
~~~

Thông thường `SDO_RELATE` đã bao gồm logic primary/secondary filter cần thiết. Việc thêm `SDO_FILTER` riêng có thể dư thừa; chỉ giữ khi có lý do đo được từ execution plan và workload.

### 7.8 Query window lấy từ bảng

Khi query window lấy từ một bảng thay vì một bind geometry đơn, Oracle khuyến nghị dùng optimizer hint `/*+ ORDERED */` trong các trường hợp cần đảm bảo thứ tự xử lý phù hợp cho spatial operator. Ví dụ:

~~~sql
SELECT /*+ ORDERED */
       q.query_id,
       c.location_id
FROM query_windows q,
     city_locations c
WHERE SDO_RELATE(
          c.shape,
          q.shape,
          'mask=ANYINTERACT'
      ) = 'TRUE';
~~~

Hãy xem usage notes của operator và execution plan cụ thể. Hint không phải giải pháp mặc định cho mọi query; chỉ dùng khi thứ tự join cần được kiểm soát theo khuyến nghị Oracle.

## 8. Spatial operators và SDO_GEOM functions

Oracle cung cấp hai nhóm API có vai trò khác nhau:

| Nhóm | Ví dụ | Spatial index |
|---|---|---|
| Spatial operators | SDO_FILTER, SDO_RELATE, SDO_NN, SDO_WITHIN_DISTANCE | Có thể tận dụng index; operator phải xuất hiện trong WHERE clause |
| PL/SQL functions/procedures | SDO_GEOM.SDO_DISTANCE, SDO_GEOM.SDO_AREA, SDO_GEOM.RELATE, SDO_CS.TRANSFORM | Không cần index và không dùng spatial index nếu đã có |

### 8.1 Tính diện tích polygon

~~~sql
SELECT a.area_id,
       SDO_GEOM.SDO_AREA(a.shape, m.diminfo, 'unit=SQ_KM') AS area_sq_km
FROM service_areas a
JOIN user_sdo_geom_metadata m
  ON m.table_name = 'SERVICE_AREAS'
 AND m.column_name = 'SHAPE';
~~~

Với geometry có georeferenced SRID, có thể chỉ định đơn vị đo. Kiểm tra unit được hỗ trợ trong `MDSYS.SDO_AREA_UNITS`/tài liệu Oracle. Không dùng diện tích Cartesian của độ kinh/vĩ như thể là km².

### 8.2 Tính khoảng cách giữa hai geometry

~~~sql
SELECT SDO_GEOM.SDO_DISTANCE(
           :geometry_a,
           :geometry_b,
           0.05,
           'unit=KM'
       ) AS distance_km
FROM dual;
~~~

Hai geometry truyền vào các function `SDO_GEOM` phải cùng coordinate system. Tolerance phải có ý nghĩa với CRS và độ chính xác dữ liệu.

### 8.3 Kiểm tra quan hệ bằng function

~~~sql
SELECT SDO_GEOM.RELATE(
           :geometry_a,
           'ANYINTERACT',
           :geometry_b,
           0.05
       ) AS relation
FROM dual;
~~~

Function hữu ích khi cần kết quả quan hệ dạng scalar hoặc xử lý một số geometry cụ thể. Nếu truy vấn một bảng lớn và operator đáp ứng nghiệp vụ, ưu tiên operator để tận dụng spatial index.

## 9. Biến đổi và chuẩn hóa hệ tọa độ

### 9.1 Transform geometry sang SRID khác

Ví dụ chuyển một point từ WGS 84 sang Web Mercator:

~~~sql
SELECT SDO_CS.TRANSFORM(
           SDO_GEOMETRY(
               2001,
               4326,
               SDO_POINT_TYPE(106.7000, 10.7800, NULL),
               NULL,
               NULL
           ),
           3857
       ) AS projected_geometry
FROM dual;
~~~

SDO_CS.TRANSFORM thay đổi ordinates theo phép biến đổi CRS và trả geometry có SRID đích. Nó khác hoàn toàn với việc tạo lại object và chỉ thay SDO_SRID.

### 9.2 Không gán SRID mới nếu chưa transform tọa độ

Giả sử dữ liệu đang ở CRS A nhưng chỉ đổi SDO_SRID từ A sang B. Oracle sẽ diễn giải các ordinates cũ như tọa độ B; nó không tự tính lại tọa độ. Hậu quả có thể là vị trí bị dịch chuyển rất xa, khoảng cách sai hoặc dữ liệu nằm ngoài bounds của metadata.

Quy tắc:

- Biết CRS nguồn và CRS đích, dùng SDO_CS.TRANSFORM.
- Không biết CRS nguồn, xác minh từ nhà cung cấp dữ liệu hoặc nguồn khảo sát trước khi gán SRID.
- Không dùng một SRID chỉ vì dữ liệu nhìn giống kinh/vĩ độ.
- Sau transform, kiểm tra geometry, bounds, đơn vị và kết quả hiển thị trên bản đồ.

### 9.3 Chuẩn hóa layer về một CRS

Để tạo spatial index và truy vấn ổn định, nên chuẩn hóa geometry trong một cột về cùng SRID. Nếu nguồn có nhiều CRS:

1. Nhận diện CRS nguồn của từng batch.
2. Kiểm tra geometry và SRID nguồn.
3. Transform sang CRS đích chuẩn.
4. Lưu geometry đã transform vào layer đích.
5. Cập nhật DIMINFO/SRID metadata phù hợp.
6. Validate layer và tạo spatial index.

Nếu cần giữ nguyên dữ liệu nguồn, lưu raw geometry hoặc bản sao trước transform để có thể truy vết và chạy lại.

### 9.4 Query window có SRID khác

Spatial operators có thể tự transform query window (geometry thứ hai) về CRS của geometry column khi cần. Tuy nhiên, không nên dựa vào implicit transform cho mọi workload mà không đo hiệu năng và kiểm tra phép biến đổi. Với truy vấn lặp lại nhiều lần, chuẩn hóa query geometry trước thường giúp dễ kiểm soát hơn.

Các function trong SDO_GEOM nhận hai geometry thường yêu cầu cùng coordinate system. Nếu SRID khác, transform một geometry trước khi gọi function.

## 10. WKT, WKB và trao đổi dữ liệu

### 10.1 Well-Known Text (WKT)

WKT là định dạng văn bản mô tả geometry, ví dụ:

~~~text
POINT (106.7 10.78)
LINESTRING (106.7 10.78, 106.71 10.79)
POLYGON ((106.7 10.78, 106.71 10.78, 106.71 10.79, 106.7 10.79, 106.7 10.78))
~~~

Có thể tạo geometry từ WKT bằng constructor tương ứng:

~~~sql
INSERT INTO city_locations (
    location_id,
    location_name,
    shape
)
VALUES (
    2,
    'WKT Imported Point',
    SDO_GEOMETRY('POINT (106.7 10.78)', 4326)
);
~~~

WKT thường không mang đầy đủ metadata CRS theo cách thống nhất giữa các nguồn. Hãy cung cấp SRID rõ ràng và xác nhận axis order.

### 10.2 Well-Known Binary (WKB)

WKB biểu diễn geometry dưới dạng nhị phân, thường phù hợp với trao đổi dữ liệu có kích thước lớn hoặc API GIS. Oracle hỗ trợ constructor từ BLOB WKB/WKB hex theo tài liệu. Khi nhập, cần bảo đảm byte order, geometry type, dimensionality và SRID được xử lý đúng.

### 10.3 Xuất geometry thành WKT/WKB

SDO_GEOMETRY có các method như GET_WKT() và GET_WKB():

~~~sql
SELECT location_id,
       shape.GET_WKT() AS geometry_wkt
FROM city_locations
WHERE location_id = :p_location_id;
~~~

WKT thuận tiện để đọc/debug, nhưng có thể lớn và không phải định dạng tối ưu cho mọi trao đổi. Với dữ liệu nhiều vertex hoặc yêu cầu bảo toàn binary representation, cân nhắc WKB.

### 10.4 GeoJSON

Oracle Spatial hỗ trợ JSON/GeoJSON trong các luồng làm việc phù hợp. Khi trao đổi GeoJSON, chú ý:

- coordinates thường dùng longitude trước latitude cho dữ liệu địa lý 2D.
- GeoJSON mặc định gắn với WGS 84 theo đặc tả hiện đại; không nhầm với tọa độ projected mét.
- Kiểm tra cách API/database map GeoJSON sang SRID nội bộ.
- Xác nhận geometry type, ring closure, coordinate precision và null/empty geometry.

Không chỉ đổi đuôi file hoặc đổi tên trường để biến một geometry thành GeoJSON hợp lệ; phải tuân theo schema và quy tắc tọa độ của định dạng.

## 11. 3D geometry và dimensionality

Oracle Spatial hỗ trợ geometry 3D như point, line, polygon, surface và solid. Một vertex 3D có ba ordinates X, Y, Z:

~~~sql
SDO_GEOMETRY(
    3001,
    4979,
    SDO_POINT_TYPE(106.7, 10.78, 25),
    NULL,
    NULL
)
~~~

SRID trong ví dụ cần được xác minh theo CRS 3D mong muốn. Không gắn SRID 2D vào geometry 3D chỉ vì hai chiều X/Y có vẻ giống nhau.

### 11.1 Metadata 3D

Layer 3D cần ba SDO_DIM_ELEMENT trong DIMINFO, theo thứ tự X, Y, Z. Bounds và đơn vị chiều Z phải khớp CRS/vertical datum của dữ liệu.

### 11.2 Spatial index 3D

Mặc định spatial index dùng hai chiều. Với dữ liệu cần lập chỉ mục 3D, cấu hình số chiều index theo hướng dẫn:

~~~sql
CREATE INDEX buildings_3d_spx
ON buildings(shape)
INDEXTYPE IS MDSYS.SPATIAL_INDEX_V2
PARAMETERS('sdo_indx_dims=3');
~~~

### 11.3 Không phải mọi operator đều xử lý Z

Một số spatial operator/function chỉ xét hai chiều đầu tiên; một số tổ hợp 2D/3D được hỗ trợ, một số không. Geometry có Z không đồng nghĩa truy vấn tự động trở thành truy vấn 3D. Kiểm tra bảng dimensionality và danh sách operator hỗ trợ 3D của đúng release trước khi triển khai.

### 11.4 3D, LRS và measure

LRS (Linear Referencing System) dùng một dimension làm measure để biểu diễn vị trí dọc tuyến, ví dụ kilometer marker trên đường. Measure dimension không giống Z elevation. Nếu geometry có LRS, cần khai báo vị trí measure trong SDO_GTYPE và dùng API SDO_LRS tương ứng.

## 12. Hiệu năng và tối ưu truy vấn không gian

### 12.1 Spatial index chỉ có ích khi query dùng đúng operator

Một truy vấn WHERE SDO_GEOM.SDO_DISTANCE(...) < ... có thể tính toán trên từng row và không tận dụng spatial index. Nếu bài toán phù hợp, dùng SDO_WITHIN_DISTANCE hoặc SDO_NN để khai thác index.

### 12.2 Giới hạn candidate sớm

Kết hợp predicate thuộc tính có chọn lọc với spatial operator. Ví dụ:

~~~sql
SELECT location_id,
       location_name
FROM city_locations c
WHERE c.location_type = 'PHARMACY'
  AND SDO_WITHIN_DISTANCE(
          c.shape,
          :query_point,
          'distance=3 unit=KM'
      ) = 'TRUE';
~~~

Đánh giá execution plan và cardinality. Optimizer có thể chọn thứ tự predicate khác nhau; không giả định điều kiện viết trước luôn chạy trước.

### 12.3 Sử dụng ORDERED khi query window đến từ bảng

Oracle khuyến nghị /*+ ORDERED */ trong một số spatial operator queries khi query window lấy từ bảng, đặc biệt khi có nhiều query windows. Hãy xem usage notes của operator và kiểm tra plan trước khi giữ hint.

### 12.4 Tối ưu SDO_NN

- Dùng sdo_num_res khi cần đúng N geometry gần nhất, không có filter thuộc tính làm thay đổi tập kết quả.
- Dùng sdo_batch_size và ROWNUM khi cần N kết quả gần nhất thỏa thêm predicate thuộc tính.
- Với partitioned spatial index, sdo_num_res có thể trả số lượng kết quả theo từng partition; cần giới hạn kết quả toàn cục bằng ROWNUM trong query ngoài khi phù hợp.
- Nếu khoảng cách có thể bằng nhau, tập kết quả giữa các lần gọi có thể khác nhau ở các row đồng hạng.

### 12.5 Spatial index statistics và execution plan

Sau khi tạo index hoặc nạp lượng lớn dữ liệu, cập nhật optimizer statistics theo chính sách DBA. Kiểm tra:

~~~sql
EXPLAIN PLAN FOR
SELECT location_id
FROM city_locations
WHERE SDO_WITHIN_DISTANCE(
          shape,
          :query_point,
          'distance=2 unit=KM'
      ) = 'TRUE';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Tìm dấu hiệu domain index access và xem số candidate/rows thực tế nếu có SQL Monitor hoặc runtime plan statistics phù hợp. Không chỉ dựa vào elapsed time của một lần chạy; cache, bind, concurrency và dữ liệu phân bố có thể ảnh hưởng kết quả.

### 12.6 SPATIAL_VECTOR_ACCELERATION

Oracle có tham số SPATIAL_VECTOR_ACCELERATION để tăng tốc một số spatial operators. Giá trị mặc định là FALSE trong tài liệu 19c. Đây là tính năng cần xác nhận quyền sử dụng/licensing và kiểm thử trên workload cụ thể; không bật trong production chỉ vì thấy tên tham số.

### 12.7 Chọn tolerance và độ phức tạp geometry

Geometry có hàng trăm nghìn vertex, ring nhỏ hoặc dữ liệu sai số lớn có thể làm spatial query tốn CPU. Có thể cân nhắc:

- Dọn vertex trùng và geometry invalid.
- Simplify geometry theo mức sai số nghiệp vụ cho phép.
- Dùng generalized geometry cho truy vấn hiển thị ở scale nhỏ.
- Lưu geometry chi tiết riêng cho phân tích chính xác.
- Chọn tolerance hợp lý và thống nhất theo layer.
- Tránh transform lặp lại cùng một query geometry trong mỗi row nếu có thể chuẩn hóa trước.

Không simplify ranh giới pháp lý, cadastral hoặc dữ liệu yêu cầu độ chính xác cao nếu chưa đánh giá tác động.

## 13. Quy trình nạp và quản lý dữ liệu spatial

### 13.1 Pipeline nạp dữ liệu

~~~text
Nguồn GIS / CSV / WKT / WKB / GeoJSON
                |
                v
       Xác định CRS và axis order
                |
                v
       Parse thành SDO_GEOMETRY
                |
                v
       Kiểm tra SRID / dimensionality
                |
                v
       Validate geometry và bounds
                |
                v
       Transform sang CRS chuẩn (nếu cần)
                |
                v
       Nạp vào staging table
                |
                v
       Ghi nhận lỗi và số lượng hợp lệ
                |
                v
       Merge vào spatial layer
                |
                v
       Cập nhật statistics / index
                |
                v
       Chạy truy vấn kiểm chứng
~~~

### 13.2 Staging trước khi nạp production

Nên nạp dữ liệu ngoài vào staging table trước. Lưu source file/batch ID, CRS nguồn, thời điểm nạp, số row, số geometry lỗi và lý do lỗi. Chỉ merge các geometry đã xác minh vào layer production.

### 13.3 Cập nhật geometry

Khi sửa geometry:

- Đảm bảo SRID và dimensionality không thay đổi ngoài dự kiến.
- Validate geometry mới.
- Kiểm tra ảnh hưởng đến spatial index.
- Ghi lại nguồn và lý do sửa.
- Nếu thay CRS, cập nhật metadata tương ứng và kiểm tra index.

### 13.4 Partitioning

Spatial Index V2 hỗ trợ quản lý index cho nhiều mô hình partitioning. Chọn partition key theo access pattern nghiệp vụ (ví dụ tenant, vùng hoặc thời gian), không phân vùng chỉ theo geometry nếu chưa đánh giá spatial query. Khi dùng partitioned index, hiểu rõ hành vi nearest neighbor và giới hạn kết quả toàn cục.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| ORA-13203 khi tạo index | Không tìm thấy metadata layer/cột | Kiểm tra USER_SDO_GEOM_METADATA và tên table/column |
| ORA-13214/metadata mismatch | SRID hoặc dimensionality không khớp | Đối chiếu SDO_SRID, DIMINFO và geometry |
| ORA-13349/invalid polygon | Ring tự cắt hoặc hình học không hợp lệ | Validate with context, sửa nguồn hoặc rectification có kiểm soát |
| Không trả kết quả gần đúng vị trí | Gán nhầm SRID, đảo X/Y hoặc transform sai | Xác minh CRS nguồn, axis order và bounds |
| Distance/area có đơn vị bất ngờ | CRS hoặc unit không đúng | Xem SRID và chỉ định unit rõ ràng |
| SDO_FILTER trả quá nhiều dòng | MBR giao nhau nhưng geometry thật không giao | Dùng SDO_RELATE cho secondary filter |
| SDO_NN không dùng được | Thiếu spatial index hoặc mismatch dimensionality | Kiểm tra index và số chiều query window |
| Spatial index invalid sau khi tạo | Index creation bị lỗi giữa chừng | Đọc lỗi, drop index invalid và tạo lại sau khi sửa |
| Query chậm dù có index | Function không dùng index, metadata sai hoặc geometry quá phức tạp | Dùng operator phù hợp, xem plan và validate dữ liệu |
| SDO_GEOM function báo CRS mismatch | Hai geometry có SRID khác nhau | Transform một geometry về cùng CRS |
| Geometry ngoài bounds | Metadata bounds không khớp dữ liệu hoặc dữ liệu nhập sai | Xác minh CRS và cập nhật DIMINFO theo dữ liệu đúng |
| Kết quả 3D giống 2D | Operator chỉ xét hai chiều | Kiểm tra 3D support và tạo index 3D nếu phù hợp |

## 15. Bài lab: tạo layer, index và truy vấn không gian

Lab dùng hệ tọa độ Cartesian cục bộ để minh họa topology và spatial index mà không phụ thuộc dữ liệu địa lý thực. Tọa độ là đơn vị tùy ý của ví dụ.

### 15.1 Tạo bảng và dữ liệu

~~~sql
CREATE TABLE lab_areas (
    area_id NUMBER PRIMARY KEY,
    area_name VARCHAR2(30),
    shape SDO_GEOMETRY
);

INSERT INTO lab_areas VALUES (
    1,
    'AREA_A',
    SDO_GEOMETRY(
        2003, NULL, NULL,
        SDO_ELEM_INFO_ARRAY(1, 1003, 3),
        SDO_ORDINATE_ARRAY(0, 0, 10, 10)
    )
);

INSERT INTO lab_areas VALUES (
    2,
    'AREA_B',
    SDO_GEOMETRY(
        2003, NULL, NULL,
        SDO_ELEM_INFO_ARRAY(1, 1003, 1),
        SDO_ORDINATE_ARRAY(8, 8, 14, 8, 14, 14, 8, 14, 8, 8)
    )
);

INSERT INTO lab_areas VALUES (
    3,
    'AREA_C',
    SDO_GEOMETRY(
        2003, NULL, NULL,
        SDO_ELEM_INFO_ARRAY(1, 1003, 3),
        SDO_ORDINATE_ARRAY(20, 20, 25, 25)
    )
);

COMMIT;
~~~

### 15.2 Khai báo metadata

~~~sql
INSERT INTO user_sdo_geom_metadata (
    table_name,
    column_name,
    diminfo,
    srid
)
VALUES (
    'LAB_AREAS',
    'SHAPE',
    SDO_DIM_ARRAY(
        SDO_DIM_ELEMENT('X', -100, 100, 0.001),
        SDO_DIM_ELEMENT('Y', -100, 100, 0.001)
    ),
    NULL
);
~~~

### 15.3 Validate geometry

~~~sql
SELECT a.area_id,
       SDO_GEOM.VALIDATE_GEOMETRY_WITH_CONTEXT(
           a.shape,
           m.diminfo
       ) AS validation_result
FROM lab_areas a,
     user_sdo_geom_metadata m
WHERE m.table_name = 'LAB_AREAS'
  AND m.column_name = 'SHAPE';
~~~

### 15.4 Tạo spatial index

~~~sql
CREATE INDEX lab_areas_spx
ON lab_areas(shape)
INDEXTYPE IS MDSYS.SPATIAL_INDEX_V2;
~~~

### 15.5 Tìm polygon giao với query window

~~~sql
SELECT area_id,
       area_name
FROM lab_areas a
WHERE SDO_RELATE(
          a.shape,
          SDO_GEOMETRY(
              2003, NULL, NULL,
              SDO_ELEM_INFO_ARRAY(1, 1003, 3),
              SDO_ORDINATE_ARRAY(9, 9, 12, 12)
          ),
          'mask=ANYINTERACT'
      ) = 'TRUE';
~~~

### 15.6 So sánh primary filter và exact relation

~~~sql
SELECT area_id, area_name
FROM lab_areas a
WHERE SDO_FILTER(
          a.shape,
          SDO_GEOMETRY(
              2003, NULL, NULL,
              SDO_ELEM_INFO_ARRAY(1, 1003, 3),
              SDO_ORDINATE_ARRAY(9, 9, 12, 12)
          )
      ) = 'TRUE';
~~~

So sánh kết quả với SDO_RELATE. Primary filter có thể trả thêm candidate do chỉ so sánh bounding rectangles.

### 15.7 Dọn lab

~~~sql
DROP INDEX lab_areas_spx;
DELETE FROM user_sdo_geom_metadata
WHERE table_name = 'LAB_AREAS'
  AND column_name = 'SHAPE';
DROP TABLE lab_areas PURGE;
~~~

Chỉ chạy các lệnh dọn nếu đây là schema lab vừa tạo và không chứa dữ liệu cần giữ.

## 16. Checklist thiết kế Oracle Spatial

### Geometry và CRS

1. Geometry type có phù hợp đối tượng nghiệp vụ không?
2. SDO_GTYPE, dimensionality và LRS measure position có đúng không?
3. ELEM_INFO offset, ETYPE và interpretation có đúng không?
4. Polygon đã khép kín và đúng hướng ring chưa?
5. SRID có phản ánh đúng CRS nguồn không?
6. Axis order, datum, projection và đơn vị đã xác nhận chưa?
7. Tolerance có phù hợp độ chính xác và đơn vị không?

### Metadata và index

1. USER_SDO_GEOM_METADATA đã có đúng table/column chưa?
2. DIMINFO bounds và tolerance có phù hợp dữ liệu không?
3. Metadata SRID có trùng geometry SRID không?
4. Geometry đã được validate trước khi index chưa?
5. Spatial index có được tạo trên đúng geometry column không?
6. Số chiều index có phù hợp với workload 2D/3D không?

### Truy vấn và hiệu năng

1. Bài toán cần primary filter hay exact topology?
2. Operator nào phù hợp: FILTER, RELATE, WITHIN_DISTANCE hay NN?
3. Query window có cùng CRS/dimensionality phù hợp không?
4. Có cần transform trước để tránh chuyển đổi lặp không?
5. Distance/area unit đã được ghi rõ chưa?
6. SDO_NN có filter thuộc tính và batch size hợp lý không?
7. Execution plan có sử dụng spatial index không?
8. Geometry có quá nhiều vertex hoặc tolerance quá lớn không?

## 17. Tổng kết

Oracle Spatial cho phép lưu và phân tích geometry trong Oracle Database bằng kiểu SDO_GEOMETRY, CRS/SRID, metadata và spatial index. Để có kết quả đúng và nhanh:

- Chọn đúng geometry type và hiểu cấu trúc SDO_GTYPE, SDO_ELEM_INFO, SDO_ORDINATES.
- Gắn đúng SRID; CRS là một phần của ý nghĩa tọa độ, không phải nhãn tùy ý.
- Khai báo USER_SDO_GEOM_METADATA với DIMINFO, bounds, tolerance và SRID đúng.
- Validate geometry trước khi tạo index và chạy spatial operations.
- Dùng R-tree spatial index với SPATIAL_INDEX_V2 cho layer cần truy vấn hiệu quả.
- Dùng SDO_FILTER cho candidate filtering; dùng SDO_RELATE, SDO_WITHIN_DISTANCE, SDO_NN và operator phù hợp cho nghiệp vụ.
- Phân biệt spatial operators có thể dùng index với function SDO_GEOM không dùng spatial index.
- Transform tọa độ thật bằng SDO_CS.TRANSFORM; không chỉ đổi thuộc tính SRID.
- Chọn tolerance và đơn vị dựa trên CRS và độ chính xác của dữ liệu.
- Với 3D, xác minh hỗ trợ dimensionality của index và từng operator.

Thiết kế không gian đúng bắt đầu từ dữ liệu nguồn và hệ tọa độ, sau đó mới đến metadata, index và query. Một spatial index tốt không thể sửa dữ liệu sai CRS; một geometry hợp lệ về cấu trúc cũng không bảo đảm vị trí đúng ngoài thực tế. Hãy quản lý CRS, geometry validity và semantics của truy vấn như các phần không thể tách rời.

## 18. Tài liệu Oracle tham khảo

- Oracle Database 19c Spatial and Graph Developer's Guide, “Spatial Concepts”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/spatial-concepts.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “SDO_GEOMETRY Object Type”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/spatial-datatypes-metadata.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “Coordinate Systems (Spatial Reference Systems)”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/coordinate-systems-concepts.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “Indexing and Querying Spatial Data”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/indexing-querying-spatial-data.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “Spatial Operators”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/spatial-operators-reference.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “SDO_GEOM Package”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/SDO_GEOM-reference.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “SDO_CS Package”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/SDO_CS-reference.html
- Oracle Database 19c Spatial and Graph Developer's Guide, “Loading Spatial Data”: https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/loading-spatial-data.html
