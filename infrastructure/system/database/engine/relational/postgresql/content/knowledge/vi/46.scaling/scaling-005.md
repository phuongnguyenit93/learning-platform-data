# PostGIS và ranh giới giữa kiểu hình học tích hợp với dữ liệu không gian

## 1. Vì sao PostgreSQL có kiểu hình học nhưng vẫn cần PostGIS?

PostgreSQL có sẵn các kiểu hình học như `point`, `line`, `lseg`, `box`, `path`, `polygon` và `circle`. Chúng biểu diễn các hình trên một mặt phẳng tọa độ hai chiều và đi kèm các toán tử cơ bản. Với ứng dụng lưu vị trí tương đối, vùng trên sơ đồ hoặc hình dạng đơn giản trong một hệ tọa độ nội bộ, các kiểu này có thể đủ dùng.

Dữ liệu địa lý thực tế thường cần nhiều hơn việc lưu một cặp số X/Y. Ứng dụng phải biết tọa độ thuộc hệ quy chiếu nào, đơn vị là độ hay mét, khoảng cách trên Trái Đất được tính ra sao, hai vùng có giao nhau không, điểm có nằm trong polygon không, làm thế nào truy vấn hàng triệu đối tượng hiệu quả và chuyển đổi giữa các hệ tọa độ.

**PostGIS** là extension không gian bổ sung các kiểu dữ liệu, hàm, toán tử, hệ quy chiếu và cơ chế index chuyên dụng cho PostgreSQL. Nó mở rộng PostgreSQL thành một spatial database, đồng thời vẫn sử dụng các cơ chế quen thuộc như transactions, constraints, WAL, backup, SQL, roles và replication.

Sự khác biệt cốt lõi:

- Kiểu hình học tích hợp của PostgreSQL biểu diễn các hình trên mặt phẳng, không gắn sẵn hệ quy chiếu địa lý hoặc đơn vị đo.
- PostGIS geometry biểu diễn đối tượng không gian có thể gắn SRID và dùng các phép toán hình học phong phú.
- PostGIS geography hỗ trợ tính toán geodetic trên bề mặt Trái Đất cho các loại đối tượng và hàm được hỗ trợ.

```text
PostgreSQL built-in geometric types
   |
   +-- point / line / lseg / box
   +-- path / polygon / circle
   |
   +-- Planar coordinates
   +-- No built-in SRID metadata
   +-- Basic geometric operators
   |
   v
Good for simple local geometry

PostGIS extension
   |
   +-- geometry + SRID
   +-- geography + geodetic calculations
   +-- spatial functions and predicates
   +-- spatial indexes and reference systems
   |
   v
Good for GIS and earth-referenced spatial data
```

Bài học này giúp xác định ranh giới phù hợp giữa hai nhóm, tránh dùng tọa độ độ như mét, tránh gắn SRID sai và chọn đúng kiểu dữ liệu/index cho từng bài toán.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Liệt kê và giải thích các kiểu hình học tích hợp của PostgreSQL.
2. Hiểu giới hạn của mặt phẳng tọa độ không có SRID.
3. Phân biệt built-in geometry, PostGIS geometry và PostGIS geography.
4. Giải thích SRID, CRS, EPSG và đơn vị tọa độ.
5. Phân biệt ST_SetSRID và ST_Transform.
6. Chọn geometry hay geography theo bài toán.
7. Tạo geometry columns với type/SRID constraints.
8. Dùng spatial predicates và measurement functions phổ biến.
9. Tạo và sử dụng GiST spatial indexes.
10. Hiểu bounding-box filtering và exact spatial predicates.
11. Kiểm tra geometry validity, dimensionality và coordinate order.
12. Cài đặt, kiểm tra và nâng cấp PostGIS extension.
13. Thiết kế schema, migration và backup cho dữ liệu không gian.
14. Chuyển đổi từ built-in point sang PostGIS geometry an toàn.
15. Chọn đúng công cụ cho sơ đồ nội bộ, GIS, geofencing, proximity và spatial joins.

---

## 2. Các kiểu hình học tích hợp của PostgreSQL

PostgreSQL cung cấp các kiểu hình học trên mặt phẳng tọa độ:

| Kiểu | Mô tả | Ví dụ sử dụng |
|---|---|---|
| `point` | Một điểm (x, y) | Node trên sơ đồ |
| `line` | Đường thẳng vô hạn | Quan hệ đường thẳng toán học |
| `lseg` | Đoạn thẳng có hai đầu | Cạnh của sơ đồ |
| `box` | Hình chữ nhật từ hai góc đối diện | Vùng chữ nhật |
| `path` | Chuỗi điểm có thứ tự, mở hoặc đóng | Đường đi trên sơ đồ |
| `polygon` | Đa giác đóng | Vùng trên mặt phẳng |
| `circle` | Hình tròn với tâm và bán kính | Vùng bán kính nội bộ |

### 2.1. point

`point` lưu hai tọa độ số thực dấu phẩy động:

```sql
SELECT point '(1, 2)' AS position;
```

Điểm này chỉ có nghĩa X = 1, Y = 2 trong hệ tọa độ do ứng dụng tự định nghĩa. PostgreSQL không biết nó là longitude/latitude, mét, pixel hay đơn vị tùy ý.

### 2.2. line

`line` biểu diễn đường thẳng vô hạn, thường được xác định bởi phương trình:

\[
A x + B y + C = 0
\]

Nó không phải một đoạn đường có điểm đầu/cuối và không tự biểu diễn tuyến đường địa lý.

### 2.3. lseg

`lseg` là line segment hữu hạn với hai đầu mút:

```sql
SELECT lseg '[(0, 0), (4, 3)]' AS segment;
```

Dùng khi cần biểu diễn một cạnh hoặc khoảng nối giữa hai điểm trên mặt phẳng.

### 2.4. box

`box` là hình chữ nhật song song với các trục tọa độ, xác định bởi hai góc đối diện:

```sql
SELECT box '((0, 0), (10, 5))' AS area;
```

Nó không phải polygon tùy ý; hình chữ nhật luôn có cạnh song song trục X/Y.

### 2.5. path

`path` biểu diễn chuỗi điểm có thứ tự. Dấu ngoặc vuông biểu diễn path mở, còn dấu ngoặc tròn biểu diễn path đóng:

```sql
SELECT
    path '[(0, 0), (2, 3), (5, 1)]' AS open_path,
    path '((0, 0), (2, 3), (5, 1))' AS closed_path;
```

Path là chuỗi điểm trên mặt phẳng; nó không có khái niệm tuyến đường thực tế, đường một chiều hay network routing.

### 2.6. polygon

`polygon` biểu diễn vùng đa giác đóng:

```sql
SELECT polygon '((0, 0), (5, 0), (4, 4), (0, 3))' AS region;
```

PostgreSQL có thể thực hiện một số phép toán trên polygon, nhưng không cung cấp đầy đủ GIS model như SRID, geometry validity rules và spatial transformation của PostGIS.

### 2.7. circle

`circle` biểu diễn hình tròn bởi tâm và bán kính:

```sql
SELECT circle '<(2, 3), 5>' AS coverage;
```

Nó hữu ích cho hình học phẳng đơn giản. Bán kính là đơn vị tọa độ của mặt phẳng, không tự động là mét trên Trái Đất.

## 3. Các kiểu tích hợp dùng hệ tọa độ phẳng

Built-in geometric types không mang metadata về:
- Hệ quy chiếu tọa độ (CRS).
- SRID/EPSG identifier.
- Đơn vị đo.
- Datum/ellipsoid.
- Trục longitude/latitude.
- Phép biến đổi giữa các CRS.

Ví dụ hai điểm `point '(106.7, 10.8)'` và `point '(106.8, 10.8)'` chỉ là hai vị trí cách nhau 0.1 đơn vị X. PostgreSQL không thể suy ra khoảng cách đó là độ kinh tuyến hay một đơn vị tùy ý.

### 3.1. Mọi phép đo phụ thuộc đơn vị ứng dụng

Nếu X/Y là mét trong một sơ đồ nội bộ, phép đo phẳng có thể mang ý nghĩa mét. Nếu X/Y là longitude/latitude theo độ, khoảng cách Euclidean không phải khoảng cách mét trên mặt đất.

### 3.2. Không tự biết Earth curvature

Một đoạn thẳng giữa hai cặp longitude/latitude không tự động là geodesic. Tính khoảng cách bằng định lý Pythagoras trên độ có thể sai đáng kể.

### 3.3. Không có SRID để ngăn trộn tọa độ

Ứng dụng có thể vô tình so sánh point từ hai hệ quy chiếu khác nhau. Database không có metadata để phát hiện sự không tương thích đó.

### 3.4. Khi nào built-in types vẫn phù hợp?

Dùng chúng cho sơ đồ nội bộ, game board, layout, hình học tương đối, vùng tọa độ nhỏ do ứng dụng định nghĩa hoặc một số phép toán phẳng đơn giản không cần GIS ecosystem.

## 4. Các toán tử hình học tích hợp

PostgreSQL cung cấp các toán tử hình học như:
- So sánh hai hình có bằng nhau hay không.
- Kiểm tra chồng lấn.
- Kiểm tra một hình chứa hoặc nằm trong hình khác.
- Kiểm tra vị trí tương đối trái/phải/trên/dưới.
- Tính một số phép giao, hợp hoặc khoảng cách tùy loại hình.

Ví dụ kiểm tra điểm nằm trong box:

```sql
SELECT point '(3, 2)' <@ box '((0, 0), (10, 5))'
    AS inside_box;
```

### 4.1. Toán tử phụ thuộc loại hình

Không phải mọi toán tử áp dụng cho mọi cặp geometric types. Xem bảng toán tử trong tài liệu PostgreSQL trước khi dùng.

### 4.2. Overlap không giống intersects tổng quát

Với built-in types, ý nghĩa toán tử được định nghĩa cho các loại hình cụ thể. Không nên diễn giải một toán tử theo tên gần giống với OGC predicate của PostGIS mà không đọc semantics.

### 4.3. Index hỗ trợ một số toán tử

Các built-in geometric types có thể dùng GiST indexes cho một số truy vấn không gian. Điều này giúp tìm ứng viên theo đặc tính hình học, nhưng không bổ sung CRS hoặc geodesic calculations.

### 4.4. Built-in operators không phải toàn bộ GIS API

Chúng không cung cấp toàn bộ các hàm như ST_Transform, ST_Buffer, ST_Intersects, ST_Within, ST_DWithin hay geometry validity model của PostGIS.

## 5. PostGIS là gì?

PostGIS là extension bổ sung khả năng lưu trữ, lập chỉ mục và truy vấn dữ liệu không gian cho PostgreSQL.

Các thành phần chính có thể bao gồm:
- `geometry`: dữ liệu hình học theo tọa độ phẳng, có thể gắn SRID.
- `geography`: dữ liệu geodetic trên bề mặt Trái Đất cho các type/function được hỗ trợ.
- `raster`: dữ liệu raster qua thành phần PostGIS Raster khi được cài đặt.
- Spatial predicates và measurement functions.
- Spatial reference metadata.
- GiST/SP-GiST và các operator classes phù hợp.
- Các chức năng 2D/3D, linear referencing, clustering và nhiều tiện ích GIS.

### 5.1. PostGIS là extension, không phải một database server khác

PostGIS chạy bên trong PostgreSQL. Database vẫn dùng SQL, transactions, WAL, backup, roles, replication và PostgreSQL administration.

### 5.2. Cài ở cấp database

Extension cần có package/library tương thích trên host/container và được enable trong từng database bằng CREATE EXTENSION.

### 5.3. PostGIS có hệ sinh thái OGC

PostGIS hỗ trợ nhiều chuẩn/format không gian phổ biến như WKT, EWKT, WKB, EWKB, GeoJSON và các kiểu hình học theo mô hình OGC Simple Features ở phạm vi được hỗ trợ.

### 5.4. PostGIS không tự sửa dữ liệu sai

Extension cung cấp công cụ kiểm tra/chuyển đổi. Ứng dụng vẫn phải đảm bảo CRS, coordinate order, validity và semantics dữ liệu.

## 6. Cài đặt và bật PostGIS

Trước tiên cần cài package PostGIS tương thích với major version PostgreSQL và hệ điều hành đang dùng. Trong managed services, cần xác nhận extension được provider hỗ trợ.

Sau khi package có mặt, kết nối vào database đích và chạy:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

Kiểm tra:

```sql
SELECT PostGIS_Full_Version();
```

### 6.1. Extension được enable theo database

Chạy CREATE EXTENSION trong database A không tự enable PostGIS trong database B. Mỗi database cần trạng thái extension riêng.

### 6.2. Package và SQL extension là hai lớp

Cài OS package cung cấp shared libraries/control/update files. CREATE EXTENSION tạo các SQL objects trong database.

### 6.3. Kiểm tra extension inventory

```sql
SELECT
    extname,
    extversion,
    extnamespace::regnamespace AS extension_schema
FROM pg_extension
WHERE extname LIKE 'postgis%';
```

### 6.4. Quyền cài extension

Việc tạo extension cần quyền phù hợp và package đã được cài. Trong môi trường managed, user có thể cần role/provider permission riêng.

## 7. PostGIS geometry

`geometry` là kiểu không gian chính cho dữ liệu theo tọa độ phẳng. Geometry có thể biểu diễn:
- Point.
- LineString.
- Polygon.
- MultiPoint.
- MultiLineString.
- MultiPolygon.
- GeometryCollection.
- Một số kiểu curve/surface và dimension mở rộng theo hỗ trợ của PostGIS.

Ví dụ:

```sql
SELECT
    ST_GeomFromText('POINT(10 20)') AS p,
    ST_GeomFromText('LINESTRING(0 0, 2 3, 5 1)') AS route,
    ST_GeomFromText(
        'POLYGON((0 0, 5 0, 5 4, 0 4, 0 0))'
    ) AS region;
```

### 7.1. Geometry là planar

Các phép đo geometry sử dụng hệ tọa độ phẳng và đơn vị của CRS. Nếu SRID 4326, tọa độ là độ; ST_Distance trên geometry 4326 trả khoảng cách theo độ, không phải mét.

### 7.2. Geometry có SRID

Geometry có thể gắn Spatial Reference Identifier để xác định CRS. SRID giúp database và người dùng biết tọa độ thuộc hệ quy chiếu nào.

### 7.3. Geometry hỗ trợ dimensionality

Có thể lưu XY, XYZ, XYM hoặc XYZM tùy type và function. Z và M là ordinates bổ sung; không phải mọi hàm đều dùng chúng trong phép tính.

### 7.4. Geometry thường phù hợp với projected CRS

Khi dữ liệu thuộc một khu vực và cần tính khoảng cách/diện tích theo đơn vị phẳng phù hợp, chọn projected CRS thích hợp cho vùng đó.

## 8. PostGIS geography

`geography` biểu diễn các đối tượng trên bề mặt Trái Đất theo mô hình geodetic. Nó phù hợp với dữ liệu longitude/latitude khi muốn dùng các phép đo bề mặt Trái Đất mà không tự chọn projected CRS.

Ví dụ:

```sql
SELECT
    ST_Distance(
        'POINT(106.7009 10.7769)'::geography,
        'POINT(106.7100 10.7769)'::geography
    ) AS distance_meters;
```

### 8.1. Distance thường trả mét

Các phép đo geography như ST_Distance trả kết quả theo mét; mặc định sử dụng spheroid trong các hàm hỗ trợ tương ứng.

### 8.2. Geography có phạm vi type/function hẹp hơn geometry

Không phải mọi geometry type hoặc spatial function đều có overload geography. Kiểm tra signature và documentation của function.

### 8.3. Geography có thể tốn CPU hơn

Geodetic calculations phức tạp hơn planar calculations. Với workload khu vực nhỏ và lớn, geometry trong projected CRS phù hợp có thể nhanh và linh hoạt hơn.

### 8.4. Geography không thay thế CRS knowledge

Geography vẫn cần SRID phù hợp và tọa độ đúng thứ tự. Gắn nhầm SRID hoặc đổi longitude/latitude sẽ tạo kết quả sai.

## 9. Geometry và geography khác nhau thế nào?

| Tiêu chí | geometry | geography |
|---|---|---|
| Mô hình | Mặt phẳng tọa độ | Bề mặt Trái Đất |
| SRID | Có | Có |
| Đơn vị distance | Đơn vị CRS | Thường là mét |
| Diện tích | Đơn vị CRS bình phương | Mét vuông cho hàm tương ứng |
| Hiệu năng | Thường nhanh hơn | Thường tốn tính toán hơn |
| CRS projected | Rất phù hợp | Không phải mục tiêu chính |
| CRS geographic | Có thể lưu nhưng đo bằng độ | Phù hợp cho geodetic operations |
| Function coverage | Rộng hơn | Hẹp hơn |
| Use case | GIS planar/projected, local/regional analysis | Distance/area geodetic toàn cầu hoặc lat/lon |

### 9.1. Không chọn geography chỉ vì có latitude/longitude

Nếu workload chủ yếu ở một thành phố/vùng và cần nhiều overlay/buffer/union operations, projected geometry có thể phù hợp hơn.

### 9.2. Không dùng geometry 4326 để tính mét

ST_Distance giữa hai geometry 4326 trả đơn vị độ. Chuyển sang projected CRS phù hợp hoặc cast sang geography nếu bài toán phù hợp.

### 9.3. Geography không hỗ trợ mọi thao tác geometry

Nếu cần function không có geography overload, có thể transform/cast theo workflow phù hợp, nhưng phải hiểu thay đổi semantics và units.

### 9.4. Chọn theo workload và độ chính xác

Cân nhắc khu vực, khoảng cách, diện tích, loại phân tích, performance và tolerance. Ghi rõ quyết định trong schema/documentation.

## 10. CRS, SRID và EPSG

CRS (Coordinate Reference System) mô tả cách tọa độ ánh xạ tới vị trí thực tế, bao gồm datum, projection, axes và units.

SRID là mã nhận diện hệ quy chiếu trong PostGIS. Nhiều SRIDs tương ứng với mã EPSG, nhưng không phải mọi SRID đều là EPSG.

### 10.1. EPSG:4326

EPSG:4326 là geographic CRS phổ biến dựa trên WGS 84. Trong cách dùng X/Y của PostGIS, X là longitude và Y là latitude.

### 10.2. EPSG:3857

EPSG:3857 là Web Mercator, thường dùng cho bản đồ web tiles. Đơn vị tọa độ là mét nhưng distortion tăng mạnh ở vĩ độ cao; không dùng nó như phép đo diện tích/khoảng cách chính xác toàn cầu.

### 10.3. Projected CRS theo khu vực

Một projected CRS phù hợp vùng nghiên cứu có thể cung cấp đơn vị mét và distortion nhỏ hơn cho khoảng cách/diện tích địa phương. Chọn đúng zone/datum theo dữ liệu.

### 10.4. SRID 0

Geometry không có hệ quy chiếu xác định thường có SRID 0. Không thể suy ra đơn vị hoặc transform đúng nếu không biết CRS nguồn.

## 11. ST_SetSRID và ST_Transform

Hai hàm này thường bị nhầm lẫn.

**ST_SetSRID** thay đổi metadata SRID, không thay đổi tọa độ.

**ST_Transform** chuyển đổi tọa độ từ CRS nguồn sang CRS đích, dựa trên định nghĩa coordinate reference systems và PROJ support.

```sql
-- Tọa độ đã là longitude/latitude WGS 84.
SELECT ST_SetSRID(
    ST_MakePoint(106.7009, 10.7769),
    4326
);

-- Chuyển tọa độ từ SRID 4326 sang SRID 3857.
SELECT ST_Transform(
    ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    ),
    3857
);
```

### 11.1. ST_SetSRID không phải phép đổi hệ tọa độ

Nếu tọa độ đang là UTM nhưng gán SRID 4326, giá trị số không tự trở thành longitude/latitude. Metadata sai làm mọi phép tính sau đó sai.

### 11.2. ST_Transform cần biết CRS nguồn

Nếu geometry có SRID 0 hoặc SRID sai, transform không thể đoán ý nghĩa tọa độ. Xác minh nguồn trước khi chuyển.

### 11.3. Chuyển đổi CRS không chỉ đổi units

Phép transform có thể thay đổi cả giá trị X/Y, projection và datum transformation. Một số phép chuyển đổi cần grid files hoặc PROJ resources phù hợp.

### 11.4. Kiểm tra kết quả

Dùng ST_SRID, ST_AsText và tọa độ bounding box để xác minh geometry sau transform nằm ở vùng mong đợi.

## 12. Coordinate order: longitude và latitude

Trong PostGIS geometry dùng quy ước X/Y:
- X thường là longitude với geographic CRS.
- Y thường là latitude.

Ví dụ một điểm có longitude 106.7 và latitude 10.8:

```sql
SELECT ST_SetSRID(
    ST_MakePoint(106.7, 10.8),
    4326
);
```

### 12.1. Đừng đảo latitude/longitude

`ST_MakePoint(latitude, longitude)` có thể tạo tọa độ sai vùng. Hãy kiểm tra contract của API/GeoJSON/client.

### 12.2. Axis order của tiêu chuẩn ngoài

Một số định nghĩa CRS/standards mô tả axis order khác X/Y convention thường dùng trong PostGIS. Khi tích hợp external tools, xác minh axis order mà giao thức cụ thể yêu cầu.

### 12.3. Range checks

Với longitude/latitude, kiểm tra longitude trong khoảng hợp lệ và latitude trong khoảng hợp lệ theo CRS. Range check không chứng minh điểm nằm đúng quốc gia/khu vực.

### 12.4. GeoJSON

RFC 7946 GeoJSON dùng WGS 84 longitude/latitude coordinate order. Khi export/import, xác minh CRS và axis order theo chuẩn.

## 13. WKT, EWKT, WKB và GeoJSON

PostGIS hỗ trợ các representation phổ biến:

| Format | Đặc điểm | Dùng khi |
|---|---|---|
| WKT | Text mô tả geometry | Debug, interchange |
| EWKT | WKT mở rộng có SRID | Debug/interchange với PostGIS |
| WKB | Binary geometry | Hiệu quả cho binary transport |
| EWKB | Binary mở rộng metadata PostGIS | Giữ SRID/dimensions theo format |
| GeoJSON | JSON geometry | Web APIs và map clients |

### 13.1. ST_AsText

```sql
SELECT ST_AsText(geom)
FROM places;
```

WKT thông thường không mang SRID. Không dùng WKT đơn lẻ như bằng chứng CRS.

### 13.2. ST_AsEWKT

```sql
SELECT ST_AsEWKT(geom)
FROM places;
```

EWKT có thể hiển thị SRID trong text representation của PostGIS.

### 13.3. ST_AsBinary

WKB phù hợp trao đổi binary geometry, nhưng WKB chuẩn không nhất thiết chứa SRID. Dùng EWKB khi cần metadata PostGIS theo contract.

### 13.4. ST_AsGeoJSON

```sql
SELECT ST_AsGeoJSON(geom)
FROM places;
```

Khi xuất GeoJSON, đưa geometry về CRS/axis order theo RFC 7946; thường là longitude/latitude WGS 84.

## 14. Tạo bảng geometry có type và SRID cố định

Một schema cho điểm địa điểm:

```sql
CREATE TABLE public.places (
    place_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    location geometry(Point, 4326) NOT NULL
);
```

Kiểu `geometry(Point, 4326)` ràng buộc geometry type là Point và SRID là 4326.

### 14.1. Typmod

PostGIS typmod có thể ràng buộc subtype, SRID và dimensionality. Ví dụ Point, PointZ hoặc Polygon theo nhu cầu.

### 14.2. Geometry tổng quát

`geometry(Geometry, 4326)` cho phép nhiều subtypes nhưng vẫn yêu cầu SRID 4326. Dùng khi một column chủ ý chứa nhiều loại hình.

### 14.3. Geography typmod

```sql
CREATE TABLE public.delivery_zones (
    zone_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    boundary geography(MultiPolygon, 4326) NOT NULL
);
```

Chọn MultiPolygon nếu domain có thể chứa nhiều polygon thành phần.

### 14.4. Constraint và application contract

Typmod bảo vệ type/SRID ở mức column, nhưng không tự xác nhận tọa độ có ý nghĩa đúng với địa điểm business. Cần validation dữ liệu đầu vào.

## 15. Chèn và tạo geometry

Dùng ST_MakePoint và gắn SRID:

```sql
INSERT INTO public.places (name, location)
VALUES (
    'Office',
    ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    )
);
```

Hoặc parse WKT:

```sql
INSERT INTO public.places (name, location)
VALUES (
    'Warehouse',
    ST_GeomFromText('POINT(106.7100 10.7800)', 4326)
);
```

### 15.1. ST_MakePoint

Tạo point từ X/Y (và có các overload dimension cao hơn). Hàm không tự biết CRS, vì vậy cần gắn SRID đúng.

### 15.2. ST_GeomFromText

Parse WKT và nhận SRID tùy overload. Kiểm tra input format và SRID.

### 15.3. Geometry collection

ST_GeomFromText có thể tạo nhiều geometry types. Column typmod sẽ từ chối type không phù hợp.

### 15.4. Input validation

Validate coordinate range, SRID, emptiness, geometry type và business region trước khi commit.

## 16. Các spatial predicates quan trọng

PostGIS có các predicates như:
- `ST_Intersects`: hai geometry có phần giao nhau.
- `ST_Contains`: A chứa B theo topology semantics.
- `ST_Within`: A nằm trong B.
- `ST_Covers`: A bao phủ B, semantics boundary khác Contains.
- `ST_Touches`: chạm tại boundary nhưng không có interior overlap.
- `ST_Crosses`: giao cắt theo định nghĩa geometry type.
- `ST_Disjoint`: không giao nhau.
- `ST_Equals`: cùng biểu diễn không gian theo topology semantics.

### 16.1. ST_Intersects

Trả true nếu hai geometry có ít nhất một điểm chung. Hữu ích cho spatial joins và vùng ảnh hưởng.

### 16.2. ST_Contains và ST_Within

Hai hàm có quan hệ đảo chiều về argument. Điểm nằm đúng trên boundary có semantics khác với trường hợp interior; hiểu rõ trước khi dùng geofence.

### 16.3. ST_Covers

Thường phù hợp khi boundary cũng được coi là thuộc vùng. Chọn theo business rule, ví dụ điểm trên ranh giới có được tính là bên trong hay không.

### 16.4. ST_Touches và ST_Crosses

Dùng khi cần phân biệt giao nhau ở biên với cắt xuyên interior. Test các trường hợp edge/corner.

### 16.5. ST_Equals không giống byte equality

Hai geometry có thể biểu diễn cùng không gian nhưng vertex ordering/representation khác. Dùng predicate phù hợp với ý nghĩa cần kiểm tra.

## 17. Spatial measurement functions

Một số hàm đo lường phổ biến:

| Hàm | Ý nghĩa |
|---|---|
| ST_Distance | Khoảng cách giữa hai geometry/geography |
| ST_DWithin | Kiểm tra trong ngưỡng khoảng cách |
| ST_Length | Độ dài lineal geometry |
| ST_Perimeter | Chu vi polygon |
| ST_Area | Diện tích polygon/surface |
| ST_Centroid | Tâm hình học |
| ST_PointOnSurface | Điểm nằm trên bề mặt geometry |
| ST_ClosestPoint | Điểm gần nhất trên geometry |
| ST_Azimuth | Góc phương vị giữa hai điểm |

### 17.1. Units phụ thuộc type và SRID

Với geometry, distance/length/area dùng đơn vị CRS. Với geography, các hàm geodetic tương ứng thường trả mét/mét vuông.

### 17.2. ST_Distance

Dùng để lấy khoảng cách theo semantics của type/CRS. Nếu chỉ cần lọc theo bán kính, ST_DWithin thường phù hợp hơn vì có thể tận dụng spatial index.

### 17.3. ST_Length

Với geometry trong projected CRS có đơn vị mét, kết quả có thể là mét. Với geometry 4326, kết quả là độ tọa độ, không phải mét.

### 17.4. ST_Area

Diện tích geometry 4326 không phải mét vuông. Dùng projected CRS phù hợp hoặc geography cho diện tích geodetic.

### 17.5. Centroid không luôn nằm trong polygon

Với polygon lõm hoặc hình phức tạp, centroid có thể nằm ngoài. Nếu cần điểm chắc chắn nằm trên surface, xem ST_PointOnSurface.

## 18. Buffer và các phép biến đổi hình học

`ST_Buffer` tạo vùng cách geometry đầu vào một khoảng theo units tương ứng.

```sql
SELECT ST_Buffer(
    ST_Transform(location, 32648),
    500
)
FROM public.places;
```

Ví dụ giả định SRID 32648 phù hợp khu vực và dữ liệu đầu vào có SRID 4326; phải chọn CRS thực tế theo vùng.

### 18.1. Buffer geometry

Khoảng buffer dùng units của CRS. Buffer 500 trên geometry 4326 là 500 độ, không phải 500 mét.

### 18.2. Buffer geography

PostGIS có overload geography cho buffer theo khoảng cách geodetic, nhưng implementation có thể transform nội bộ sang planar CRS phù hợp. Với vùng rộng hoặc hình phức tạp, kiểm tra kết quả và giới hạn.

### 18.3. ST_Intersection

Tạo phần giao của hai geometry. Input validity và CRS compatibility cần được kiểm tra.

### 18.4. ST_Union

Gộp các geometries. Union nhiều polygons lớn có thể tốn CPU/memory; dùng batch/aggregate strategy và đo workload.

### 18.5. ST_Difference

Lấy phần của geometry A không nằm trong B. Hữu ích cho overlay nhưng cần kiểm tra output type/emptiness.

## 19. Kiểm tra geometry validity

Một geometry có thể parse được nhưng không hợp lệ về topology. Ví dụ polygon có self-intersection hoặc ring cấu trúc sai.

```sql
SELECT
    id,
    ST_IsValid(geom) AS is_valid,
    ST_IsValidReason(geom) AS reason
FROM spatial_features;
```

### 19.1. ST_IsValid

Kiểm tra validity theo rules áp dụng cho geometry. Geometry type khác nhau có quy tắc khác nhau.

### 19.2. ST_IsValidReason

Trả lý do geometry invalid, hữu ích cho data cleaning.

### 19.3. ST_MakeValid

Có thể sửa geometry invalid nhưng output type/structure có thể thay đổi, ví dụ thành MultiPolygon hoặc GeometryCollection. Không giả định output luôn cùng type input.

### 19.4. ST_IsEmpty

Geometry empty khác NULL. Empty geometry là giá trị geometry không chứa điểm; xử lý rõ trong business logic.

### 19.5. Validity không chứng minh dữ liệu đúng nghiệp vụ

Một polygon hợp lệ vẫn có thể ở sai quốc gia, sai SRID hoặc có tọa độ bị đảo.

## 20. Spatial indexes

Spatial queries trên hàng triệu geometries cần index. PostGIS thường sử dụng GiST index:

```sql
CREATE INDEX places_location_gix
ON public.places
USING GIST (location);
```

Index hỗ trợ lọc candidate nhanh theo bounding boxes, sau đó exact predicate kiểm tra quan hệ hình học.

### 20.1. GiST

Generalized Search Tree là framework index extensible của PostgreSQL. PostGIS cung cấp operator classes cho các spatial types.

### 20.2. Bounding box

Index thường dùng bounding-box approximation để tìm candidates. Candidate cần được kiểm tra chính xác bởi spatial predicate.

### 20.3. Index không lưu mọi topology answer

Một bounding box overlap không có nghĩa hai polygons thực sự intersect. Exact predicate vẫn cần thiết.

### 20.4. Selectivity

Nếu query trả về phần lớn bảng, planner có thể chọn sequential scan vì index không hiệu quả hơn. Index tồn tại không bảo đảm mọi query dùng index.

### 20.5. SP-GiST và BRIN

PostGIS có thể cung cấp thêm operator classes/index strategies theo version và data characteristics. Chọn sau khi đo; GiST là điểm bắt đầu phổ biến.

## 21. Bounding-box filter và exact predicate

Toán tử `&&` kiểm tra bounding boxes có overlap. Nó không phải phép kiểm tra giao nhau chính xác của toàn bộ hình.

Ví dụ:

```sql
SELECT id
FROM spatial_features
WHERE geom && ST_MakeEnvelope(
    106.60, 10.70,
    106.80, 10.90,
    4326
);
```

Đây là bounding-box filter.

Để lấy exact intersections:

```sql
SELECT id
FROM spatial_features
WHERE ST_Intersects(
    geom,
    ST_MakeEnvelope(
        106.60, 10.70,
        106.80, 10.90,
        4326
    )
);
```

### 21.1. Index-aware predicates

Nhiều PostGIS predicates như ST_Intersects và ST_DWithin tự thêm bounding-box condition để planner có thể dùng index.

### 21.2. && là candidate filter

Nếu chỉ dùng &&, kết quả có thể chứa false positives do bounding boxes overlap nhưng hình thật không giao nhau.

### 21.3. EXPLAIN xác nhận index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id
FROM spatial_features
WHERE ST_Intersects(geom, :query_geom);
```

Tìm Index Scan/Bitmap Index Scan phù hợp và so với actual rows/loops.

### 21.4. Transform đúng phía

Nếu column được index ở SRID 4326, thường transform query geometry sang 4326 thay vì bọc column trong ST_Transform mỗi row. Nếu workload luôn query ở CRS khác, cân nhắc functional index.

## 22. KNN spatial search

PostGIS hỗ trợ nearest-neighbor search với toán tử distance ordering như `<->` trên các index/operator classes phù hợp.

Ví dụ tìm các điểm gần query point:

```sql
SELECT
    place_id,
    name,
    location <-> ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    ) AS planar_distance
FROM public.places
ORDER BY location <-> ST_SetSRID(
    ST_MakePoint(106.7009, 10.7769),
    4326
)
LIMIT 10;
```

### 22.1. KNN dựa trên operator semantics

Distance ordering cho geometry là planar theo CRS. Với geography, KNN semantics/accuracy có thể khác với distance spheroid tùy operator/version.

### 22.2. KNN không tự sửa units

Geometry 4326 sẽ cho thứ tự theo distance trong coordinate plane, không phải mét geodesic.

### 22.3. Exact re-ranking

Một pattern là dùng KNN/index để lấy candidate set rồi tính lại distance chính xác theo geography/spheroid nếu business yêu cầu.

### 22.4. EXPLAIN

Xác nhận planner dùng index ordering thay vì sort toàn bộ table. Kiểm tra số candidates và kết quả exact.

## 23. ST_DWithin cho radius search

Một pattern thường dùng để tìm địa điểm trong bán kính:

```sql
SELECT
    place_id,
    name
FROM public.places
WHERE ST_DWithin(
    location::geography,
    ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    )::geography,
    1000
);
```

Ở đây khoảng cách là 1.000 mét theo geography semantics.

### 23.1. DWithin phù hợp lọc theo ngưỡng

Thường hiệu quả hơn tính ST_Distance cho mọi row rồi lọc bằng WHERE distance < threshold.

### 23.2. Index trên geography

Nếu workload thường truy vấn geography, cân nhắc column geography hoặc index phù hợp trên expression cast. Index phải khớp expression trong query.

### 23.3. Không cast tùy tiện mỗi row

Cast geometry sang geography trong query có thể cần expression index để đạt performance tốt. Đo EXPLAIN và cân nhắc lưu geography trực tiếp nếu đó là domain model.

### 23.4. Boundary semantics

DWithin dùng khoảng cách nhỏ hơn hoặc bằng ngưỡng theo semantics của hàm. Test threshold edge cases và tolerance.

## 24. Spatial joins

Spatial join nối các records dựa trên quan hệ hình học thay vì chỉ equality keys.

Ví dụ tìm các điểm nằm trong vùng:

```sql
SELECT
    p.place_id,
    p.name,
    z.zone_id,
    z.name AS zone_name
FROM public.places AS p
JOIN public.zones AS z
  ON ST_Within(p.location, z.boundary);
```

### 24.1. Chọn predicate theo business rule

ST_Within không luôn tương đương ST_CoveredBy ở boundary. Nếu điểm nằm đúng ranh giới phải được tính trong vùng, đánh giá ST_Covers/ST_CoveredBy.

### 24.2. Index hai phía

Index trên cả point và polygon columns có thể hỗ trợ planner. Kiểm tra plan và table size.

### 24.3. Spatial join cardinality

Một point có thể thuộc nhiều polygons nếu zones overlap. Nếu business yêu cầu một zone duy nhất, cần rule ưu tiên hoặc constraint dữ liệu.

### 24.4. Precompute khi cần

Nếu point-zone relation ít thay đổi nhưng được query rất thường xuyên, materialize mapping có thể giảm spatial join cost; phải cập nhật khi geometry thay đổi.

## 25. Built-in point và PostGIS geometry(Point) không giống nhau

Hai kiểu đều có thể biểu diễn một cặp tọa độ, nhưng metadata và function ecosystem khác nhau.

| Tiêu chí | PostgreSQL point | PostGIS geometry(Point) |
|---|---|---|
| Giá trị | X/Y | Spatial point |
| SRID | Không | Có thể có |
| CRS | Do ứng dụng tự quản lý | Gắn metadata SRID |
| Functions | Built-in geometric functions/operators | Spatial functions phong phú |
| Geometry model | Điểm phẳng cơ bản | OGC-style geometry model |
| Spatial joins | Hạn chế | Predicates phong phú |
| Coordinate transform | Không có GIS transform built-in | ST_Transform |
| Geography | Không | Có type geography riêng |
| Spatial indexing | Built-in geometric index support | PostGIS operator classes |
| Interchange | Tọa độ đơn giản | WKT/WKB/GeoJSON và nhiều format |

### 25.1. Không thay thế chỉ vì tên gần giống

Một column point không tự có semantics của geometry(Point,4326). Cần chuyển dữ liệu và xác minh CRS.

### 25.2. Conversion phải rõ ràng

Nếu point X/Y đã được xác định là longitude/latitude WGS 84:

```sql
SELECT ST_SetSRID(
    ST_MakePoint(
        (legacy_point)[0],
        (legacy_point)[1]
    ),
    4326
)
FROM legacy_locations;
```

Cú pháp truy cập tọa độ và cast cần được kiểm tra theo version/type context; mục tiêu là chuyển X/Y bằng ST_MakePoint rồi gắn SRID đã xác minh.

### 25.3. Không đoán SRID từ giá trị số

Tọa độ 106.7, 10.8 có vẻ giống longitude/latitude nhưng không chứng minh CRS. Kiểm tra nguồn dữ liệu và contract.

### 25.4. Giữ source data trong migration

Trong migration lớn, thêm cột mới, backfill, validate, chuyển application và chỉ drop cột cũ ở phase sau.

## 26. Khi nào dùng built-in geometric types?

Built-in types phù hợp khi:
- Ứng dụng chỉ cần geometry phẳng đơn giản.
- Tọa độ là đơn vị nội bộ đã được định nghĩa.
- Không cần SRID/CRS transformations.
- Không cần đo khoảng cách địa lý trên Trái Đất.
- Cần lưu point/box/path/circle đơn giản.
- Dữ liệu không cần GIS interchange hoặc spatial analytics phong phú.
- Muốn tránh dependency extension cho một bài toán nhỏ.

### 26.1. Sơ đồ giao diện

Một node tại pixel (x, y) hoặc rectangle trên canvas có thể dùng point/box nếu application tự quản lý units và bounds.

### 26.2. Game board

Vị trí quân cờ trong grid có thể dùng point hoặc integer coordinate pairs; không cần PostGIS chỉ vì dữ liệu có hai chiều.

### 26.3. Geometry nội bộ

Một ứng dụng mô phỏng mặt phẳng cục bộ có thể dùng built-in types nếu không cần CRS/earth semantics.

### 26.4. Hạn chế tăng trưởng

Nếu roadmap có geofencing, map layers, spatial joins hoặc import GIS data, chọn PostGIS sớm có thể tránh migration sau này.

## 27. Khi nào dùng PostGIS?

PostGIS phù hợp khi:
- Lưu địa chỉ/địa điểm với CRS rõ ràng.
- Tìm địa điểm trong bán kính.
- Xác định point thuộc polygon/administrative boundary.
- Tính diện tích, chiều dài, buffer.
- Spatial joins giữa nhiều lớp dữ liệu.
- Import/export GeoJSON, WKT, WKB hoặc GIS formats.
- Lưu road segments, routes, parcels, zones.
- Cần reprojection/coordinate transformation.
- Cần spatial indexing ở quy mô lớn.
- Cần các phân tích địa lý và topology.

### 27.1. Store locator

Tìm cửa hàng gần vị trí người dùng, giới hạn radius và sắp xếp theo distance.

### 27.2. Geofencing

Kiểm tra vị trí thiết bị có nằm trong vùng delivery/service boundary hay không.

### 27.3. Land parcels

Lưu polygon thửa đất, kiểm tra overlap, adjacency và diện tích.

### 27.4. Logistics

Phân tích vùng phục vụ, khoảng cách, điểm giao nhận và spatial relationships. Routing trên road network có thể cần thêm pgRouting hoặc routing service; PostGIS không tự là routing engine.

## 28. Ranh giới giữa spatial database và routing/topology systems

PostGIS cung cấp spatial data types, predicates, measurements và nhiều GIS functions. Tuy nhiên một số bài toán cần thêm extension hoặc hệ thống chuyên biệt.

### 28.1. Road routing

Tìm shortest path trên graph đường đi thường cần pgRouting hoặc một routing engine. ST_Distance giữa hai points không phải thời gian/độ dài tuyến đường thực tế.

### 28.2. Network topology

Một số bài toán quản lý topology có thể dùng PostGIS Topology extension. Geometry polygon/line bình thường không tự đảm bảo topology toàn bộ dataset.

### 28.3. Raster analysis

Raster workflows cần PostGIS Raster component và các công cụ phù hợp. Không nhầm geometry vector với raster grid.

### 28.4. Geocoding

Chuyển địa chỉ văn bản thành tọa độ thường cần geocoding dataset/service. PostGIS lưu và truy vấn kết quả, nhưng không tự cung cấp mọi địa chỉ thế giới.

## 29. SRID constraints và schema design

Thiết kế column theo domain:

```sql
CREATE TABLE public.delivery_points (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    location geometry(Point, 4326) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

### 29.1. Một column nên có một CRS contract

Giữ SRID nhất quán giúp query/index và application behavior rõ ràng. Tránh trộn 4326 và 3857 trong cùng column nếu không có lý do.

### 29.2. Type constraints

Dùng Point, MultiPolygon hoặc type cụ thể theo domain thay vì geometry tổng quát khi schema yêu cầu một loại hình.

### 29.3. Dimensionality

Chọn XY/XYZ/XYM/XYZM theo ý nghĩa dữ liệu. Đừng thêm Z chỉ vì client gửi altitude nếu ứng dụng không định nghĩa vertical CRS/units.

### 29.4. Null và empty

Quy định location có thể NULL hay không. Empty geometry không tương đương NULL; xử lý rõ.

### 29.5. Business constraints

Có thể thêm CHECK để giới hạn vùng tọa độ hoặc validity, nhưng kiểm tra performance và semantics trước khi áp trên bảng lớn.

## 30. Geometry validity và data quality pipeline

Một pipeline ingest dữ liệu không gian nên:
1. Kiểm tra định dạng WKT/WKB/GeoJSON.
2. Kiểm tra coordinate order và CRS nguồn.
3. Transform về CRS lưu trữ.
4. Kiểm tra type/dimension.
5. Kiểm tra NULL/empty.
6. Kiểm tra validity.
7. Kiểm tra bounds/domain region.
8. Ghi nhận reject reason.
9. Insert vào bảng chính sau validation.

### 30.1. ST_IsValidReason

Giúp giải thích invalid polygon, ví dụ ring self-intersection.

### 30.2. ST_MakeValid không phải business decision

Sửa geometry có thể tạo nhiều components hoặc thay đổi hình dạng. Cần kiểm tra output và quy tắc nghiệp vụ.

### 30.3. Precision

Tọa độ dùng floating-point. Không so sánh tọa độ bằng equality tuyệt đối khi domain cần tolerance; dùng ST_DWithin hoặc precision normalization phù hợp.

### 30.4. Outlier detection

Tọa độ nằm ngoài vùng dự kiến có thể do lat/lon đảo, CRS sai hoặc input corruption. Dùng bounds checks và monitoring.

## 31. Geometry và dimensionality Z/M

PostGIS có thể lưu:
- XY: hai chiều.
- XYZ: thêm Z coordinate.
- XYM: thêm measure M.
- XYZM: cả Z và M.

### 31.1. Z không tự động là altitude chính xác

Z chỉ là ordinate thứ ba. Cần xác định vertical datum, units và nguồn độ cao nếu cần ý nghĩa địa lý.

### 31.2. M là measure

M có thể biểu diễn chainage, route measure hoặc một đại lượng tuyến tính do ứng dụng định nghĩa.

### 31.3. Không phải mọi hàm dùng Z/M

Nhiều predicates/measurements truyền thống là 2D hoặc có behavior riêng. Xem hàm 3D tương ứng như ST_3DDistance khi cần.

### 31.4. Typmod dimensionality

Column geometry(PointZ,4326) có thể ràng buộc dimension. Kiểm tra input và function outputs phù hợp.

## 32. Geography và geometry cho distance search

Nếu cần tìm điểm trong 2 km:
- Geography: dùng longitude/latitude và distance meters.
- Geometry: transform dữ liệu/query sang projected CRS phù hợp và dùng meters theo CRS.

### 32.1. Geography example

```sql
SELECT id
FROM delivery_points
WHERE ST_DWithin(
    location::geography,
    :origin_geography,
    2000
);
```

### 32.2. Projected geometry example

```sql
SELECT id
FROM delivery_points_projected
WHERE ST_DWithin(
    location,
    :origin_projected,
    2000
);
```

### 32.3. Chọn CRS phù hợp vùng

Projected CRS có distortion. Chọn projection theo khu vực và use case, không chọn SRID chỉ vì đơn vị tên là meter.

### 32.4. Global queries

Nếu query xuyên nhiều vùng/quốc gia, geography có thể tiện hơn cho geodetic distance, nhưng phải xem performance và function coverage.

## 33. Geography và geometry cho area

Diện tích có thể được tính theo hai cách:

```sql
-- Geometry: result units are CRS units squared.
SELECT ST_Area(ST_Transform(boundary, 32648))
FROM zones;

-- Geography: result is square meters for the supported calculation.
SELECT ST_Area(boundary::geography)
FROM zones;
```

### 33.1. Geometry projected

Phù hợp phân tích diện tích trong một khu vực với projection được chọn phù hợp.

### 33.2. Geometry geographic

ST_Area trên geometry 4326 trả square degrees, không phải diện tích vật lý. Không hiển thị như m².

### 33.3. Geography

Tính diện tích geodetic theo spheroid mặc định trong hàm geography tương ứng.

### 33.4. Đơn vị output

Đặt tên cột/alias có units như area_m2, length_m để tránh người dùng downstream hiểu nhầm.

## 34. ST_Transform và index strategy

Giả sử table có index trên geometry SRID 4326, query nên transform query geometry sang SRID của column:

```sql
SELECT id
FROM spatial_features
WHERE ST_Intersects(
    geom_4326,
    ST_Transform(:query_geom_3857, 4326)
);
```

### 34.1. Tránh transform từng row nếu không cần

`ST_Transform(geom_4326, 3857)` trong predicate có thể ngăn dùng index thông thường trên geom_4326.

### 34.2. Functional index

Nếu query thường xuyên dùng cùng expression, có thể tạo functional index:

```sql
CREATE INDEX spatial_features_3857_gix
ON spatial_features
USING GIST (ST_Transform(geom_4326, 3857));
```

### 34.3. Query expression phải khớp

Planner cần nhận diện expression phù hợp với functional index. Kiểm tra EXPLAIN.

### 34.4. Chi phí lưu nhiều representations

Lưu thêm projected column có thể tăng storage và yêu cầu đồng bộ khi geometry gốc thay đổi. Chỉ làm khi workload justify.

## 35. Partitioning và spatial data

Partitioning có thể hữu ích khi spatial data được phân vùng theo thời gian, tenant hoặc vùng nghiệp vụ.

### 35.1. Time partitioning

Location events có timestamp có thể partition theo thời gian để retention/archive và query pruning.

### 35.2. Spatial partitioning

Chia theo tile/grid/geohash hoặc region có thể giảm phạm vi dữ liệu, nhưng partition key cần phù hợp query patterns.

### 35.3. Spatial index per partition

Mỗi partition cần indexes phù hợp; theo dõi index coverage và partition pruning.

### 35.4. Partition boundary

Một geometry có thể cắt qua nhiều tiles/regions. Chọn quy tắc lưu một bản, duplicate với identity hoặc phân mảnh geometry có kiểm soát.

## 36. Performance và query planning

Spatial query performance phụ thuộc:
- Spatial index.
- Geometry complexity/vertex count.
- CRS và function choice.
- Query selectivity.
- Spatial data distribution.
- Table statistics.
- Join order.
- Reprojection cost.
- Validity/precision.
- Number of candidate geometries.

### 36.1. EXPLAIN ANALYZE

Kiểm tra index scan, rows removed by filter, recheck conditions, loops và buffer reads.

### 36.2. Geometry complexity

Một vài geometries cực lớn có thể chi phối latency. Có thể simplify theo tolerance phù hợp cho display, giữ dữ liệu gốc cho legal/authoritative use.

### 36.3. Subdivision

ST_Subdivide có thể chia geometry lớn thành parts nhỏ để spatial indexing/filtering hiệu quả hơn trong một số workloads. Cần quản lý identity/aggregation để trả kết quả business đúng.

### 36.4. Statistics

Chạy ANALYZE sau bulk load/update và theo dõi planner estimates. Data distribution không gian có thể lệch mạnh.

### 36.5. Avoid unnecessary transforms

Transform query geometry một lần thay vì transform mọi row, hoặc dùng functional index khi phù hợp.

## 37. Import và export spatial data

PostGIS thường tích hợp với các công cụ như ogr2ogr/GDAL, shp2pgsql và các client GIS.

Các formats phổ biến:
- GeoJSON.
- Shapefile.
- GeoPackage.
- WKT/WKB.
- GeoParquet qua tooling phù hợp.
- Raster formats qua PostGIS Raster/GDAL.

### 37.1. Kiểm tra CRS khi import

Source file có CRS metadata hay không? Nếu không, không đoán SRID chỉ từ giá trị tọa độ.

### 37.2. Reproject trước hoặc trong quá trình import

Chọn target CRS và xác minh transform pipeline. Kiểm tra PROJ grids nếu datum transformation yêu cầu.

### 37.3. Field/type mapping

Tên field, string encoding, numeric precision, geometry type và null handling cần kiểm tra.

### 37.4. Validate sau import

So row counts, extent, SRID, geometry type, validity, nulls và sample visual output.

## 38. Migration từ built-in point sang PostGIS geometry

Giả sử legacy table:

```sql
CREATE TABLE legacy_locations (
    id bigint PRIMARY KEY,
    position point NOT NULL
);
```

Nếu application đã xác nhận X/Y là longitude/latitude WGS 84, có thể mở rộng schema:

```sql
ALTER TABLE legacy_locations
ADD COLUMN location geometry(Point, 4326);
```

Backfill:

```sql
UPDATE legacy_locations
SET location = ST_SetSRID(
    ST_MakePoint(
        (position)[0],
        (position)[1]
    ),
    4326
)
WHERE location IS NULL;
```

### 38.1. Xác minh nguồn trước khi gắn SRID

Nếu legacy point dùng local units hoặc projected CRS, không gắn 4326. Phải xác định CRS nguồn và transform đúng.

### 38.2. Backfill theo batch cho bảng lớn

Không chạy một UPDATE toàn bảng trong production nếu table lớn. Chia batch theo primary key, commit và theo dõi WAL/replication lag.

### 38.3. Validate

So row counts, NULL count, coordinate bounds, sample points và expected geography. Đối chiếu với source system.

### 38.4. Dual-write và cutover

Deploy application ghi cả hai columns hoặc chuyển đổi theo phase. Sau khi mọi consumers dùng geometry, mới bỏ legacy point trong migration sau.

### 38.5. Index và rollback

Tạo GiST index, test queries, giữ legacy column trong rollback window. Với CREATE INDEX CONCURRENTLY, migration runner cần non-transactional support.

## 39. Migration và extension lifecycle

PostGIS version cần tương thích với PostgreSQL major, OS package, PROJ/GDAL dependencies và các extensions liên quan.

### 39.1. Kiểm tra version

```sql
SELECT PostGIS_Full_Version();
```

### 39.2. Upgrade SQL extension

Khi target package cung cấp update path:

```sql
ALTER EXTENSION postgis UPDATE;
```

Kiểm tra available versions và release notes của PostGIS trước khi chạy. Có thể cần update các PostGIS companion extensions riêng.

### 39.3. Major PostgreSQL upgrade

Cần target-compatible PostGIS binaries trên cluster mới. Với pg_upgrade, extension libraries phải sẵn sàng theo requirements của target major.

### 39.4. Managed service

Provider có thể hỗ trợ một tập extension/version cụ thể. Xác minh availability trước khi chọn target PostgreSQL major.

### 39.5. Backup/restore

Restore database có PostGIS cần extension files tương thích trên target host/service và SQL extension objects được restore đúng cách.

## 40. Security và access control

Spatial data có thể tiết lộ vị trí nhà ở, khách hàng, nhân viên, tài sản hoặc tuyến giao hàng.

### 40.1. Least privilege

Application role chỉ cần quyền trên schema/tables/functions phù hợp. Không cấp superuser chỉ để gọi spatial functions.

### 40.2. Sensitive coordinates

Áp dụng row-level security, tenant filters và data minimization khi cần. Không đưa tọa độ nhạy cảm vào logs/metrics labels.

### 40.3. Query text and GeoJSON logs

GeoJSON/coordinates có thể chứa vị trí cá nhân. Redact hoặc hạn chế retention khi logging requests.

### 40.4. Extension trust

Cài PostGIS từ package source tin cậy, cập nhật security fixes và kiểm tra extension versions.

## 41. Monitoring spatial workloads

Theo dõi:
- Query p50/p95/p99.
- Calls/s và slow spatial queries.
- GiST index scans/hit behavior.
- Rows removed by spatial filter.
- Buffer reads and temp I/O.
- Geometry complexity/vertex counts.
- Invalid geometry count.
- Import/backfill throughput.
- Index build duration.
- Table/index growth.
- Replication lag/WAL rate.
- Extension version and upgrade status.

### 41.1. Không chỉ nhìn index tồn tại

Một index có thể không được dùng do query expression, selectivity, stats hoặc operator mismatch.

### 41.2. Geometry complexity

Một vài geometries cực lớn có thể chi phối latency. Track distribution of vertex counts và query outliers.

### 41.3. Invalid input

Đếm rejected/invalid geometries và phân loại reason. Không âm thầm bỏ dữ liệu sai.

### 41.4. Upgrade monitoring

Sau extension/server upgrade, theo dõi function errors, plan changes, index behavior và query latency.

## 42. Troubleshooting: khoảng cách trả kết quả sai

Triệu chứng: hai điểm gần nhau nhưng ST_Distance trả số rất lớn/nhỏ bất thường.

Kiểm tra:
1. Type là geometry hay geography?
2. SRID của cả hai có giống và đúng?
3. Geometry 4326 có bị đo bằng units degrees?
4. Longitude/latitude có bị đảo?
5. ST_SetSRID có bị dùng thay cho ST_Transform?
6. Source CRS có đúng metadata?
7. Geography cast có phù hợp?
8. Projection có distortion phù hợp khu vực?
9. Query output có alias/unit rõ ràng?

### 42.1. Geometry 4326

Khoảng cách trả theo độ tọa độ. Đổi sang geography hoặc transform sang projected CRS phù hợp.

### 42.2. SRID mismatch

Không gắn một SRID giả để làm query chạy. Xác minh nguồn và transform.

### 42.3. Coordinate order

Kiểm tra một vài points đã biết vị trí. X/Y đảo có thể đặt geometry sang vùng khác.

### 42.4. Test known distance

Dùng cặp tọa độ có khoảng cách tham chiếu để xác minh units/CRS.

## 43. Troubleshooting: spatial query không dùng index

Triệu chứng: EXPLAIN cho thấy sequential scan trên bảng lớn.

Kiểm tra:
1. GiST index có tồn tại/valid?
2. Query dùng spatial predicate/operator có index support?
3. Column có bị bọc trong function/CAST khác expression?
4. SRID có mismatch?
5. Query có trả phần lớn table không?
6. Statistics có cập nhật?
7. Planner estimates có hợp lý?
8. Functional index có cần thiết?
9. Geometry complexity và table size?
10. EXPLAIN ANALYZE/BUFFERS ra sao?

### 43.1. Index-aware predicate

Ưu tiên ST_Intersects/ST_DWithin hoặc pattern được PostGIS tài liệu hóa khi phù hợp.

### 43.2. Transform query side

Transform query geometry về SRID của indexed column khi có thể.

### 43.3. Functional index

Nếu query luôn transform column, tạo functional index tương ứng sau khi đánh giá storage/maintenance.

### 43.4. Sequential scan có thể đúng

Nếu query lấy gần hết table hoặc table nhỏ, sequential scan có thể rẻ hơn index.

## 44. Những hiểu lầm phổ biến

1. **PostgreSQL có point nên không cần PostGIS.** Chỉ đúng cho bài toán hình học phẳng đơn giản.
2. **Built-in point biết longitude/latitude.** Không; nó chỉ lưu X/Y.
3. **Gắn SRID là đổi tọa độ.** Sai; ST_SetSRID chỉ thay metadata.
4. **ST_Transform chỉ đổi label.** Sai; nó chuyển tọa độ qua CRS.
5. **Geometry 4326 đo khoảng cách bằng mét.** Sai; units là degrees.
6. **Geography hỗ trợ mọi PostGIS functions.** Sai; function coverage/type support hẹp hơn.
7. **EPSG:3857 luôn chính xác cho diện tích.** Sai; distortion có thể lớn.
8. **&& là exact intersection.** Sai; nó kiểm tra bounding-box overlap.
9. **Có GiST index thì mọi spatial query dùng index.** Sai; predicate, expression, selectivity và plan quyết định.
10. **ST_Centroid luôn nằm trong polygon.** Sai với polygon lõm hoặc phức tạp.
11. **ST_MakeValid luôn trả cùng geometry type.** Sai; output có thể đổi type/collection.
12. **Z tự động là altitude theo mét.** Sai; cần vertical CRS/units contract.
13. **PostGIS là server database riêng.** Sai; là extension của PostgreSQL.
14. **CREATE EXTENSION ở một database áp dụng cho mọi database.** Sai; extension state theo database.
15. **PostGIS tự geocode địa chỉ.** Không; cần geocoding dataset/service.
16. **ST_Distance rồi WHERE < radius luôn tận dụng index tốt.** Thường nên dùng ST_DWithin để lọc candidate.
17. **Transform column trong WHERE không ảnh hưởng index.** Có thể làm index thường không dùng được nếu không có functional index.
18. **Một polygon valid chắc chắn đúng vị trí.** Không; SRID/coordinates/business extent vẫn có thể sai.
19. **Logical migration tự đồng bộ mọi spatial metadata.** Không; schema/extensions/objects cần migration riêng.
20. **Spatial index thay thế validation.** Không; vẫn cần validity, CRS và domain checks.

## 45. Bài tập thực hành có đáp án

### Bài 1. PostgreSQL built-in geometric types gồm những loại nào?

**Đáp án:** point, line, lseg, box, path, polygon và circle.

### Bài 2. point lưu thông tin gì?

**Đáp án:** Hai tọa độ X/Y trên một mặt phẳng do ứng dụng định nghĩa.

### Bài 3. Built-in point có SRID không?

**Đáp án:** Không. Nó không tự mang metadata CRS.

### Bài 4. line khác lseg thế nào?

**Đáp án:** line là đường thẳng vô hạn; lseg là đoạn thẳng có hai đầu mút.

### Bài 5. box biểu diễn hình gì?

**Đáp án:** Hình chữ nhật song song trục tọa độ, xác định bởi hai góc đối diện.

### Bài 6. path mở và đóng được biểu diễn ra sao?

**Đáp án:** Path mở dùng square brackets; path đóng dùng parentheses trong input representation.

### Bài 7. circle có đơn vị bán kính tự động là mét?

**Đáp án:** Không. Bán kính dùng đơn vị của mặt phẳng tọa độ ứng dụng.

### Bài 8. PostGIS là gì?

**Đáp án:** Extension bổ sung spatial types, functions, operators, indexes và CRS support cho PostgreSQL.

### Bài 9. PostGIS có phải database server riêng?

**Đáp án:** Không. Nó chạy trong PostgreSQL database.

### Bài 10. CREATE EXTENSION postgis áp dụng ở đâu?

**Đáp án:** Trong database mà lệnh được chạy; từng database cần enable riêng.

### Bài 11. geometry khác geography thế nào?

**Đáp án:** geometry dùng planar coordinate model; geography hỗ trợ geodetic calculations trên bề mặt Trái Đất.

### Bài 12. Geometry 4326 có distance units gì?

**Đáp án:** Đơn vị tọa độ angular, thường là degrees, không phải meters.

### Bài 13. Geography ST_Distance thường trả đơn vị gì?

**Đáp án:** Meters cho geography overload tương ứng.

### Bài 14. EPSG:4326 thường mô tả gì?

**Đáp án:** Geographic CRS WGS 84 với longitude/latitude coordinates.

### Bài 15. Trong PostGIS X/Y cho 4326 thường là thứ tự nào?

**Đáp án:** X = longitude, Y = latitude.

### Bài 16. EPSG:3857 dùng phổ biến ở đâu?

**Đáp án:** Web map tiles/Web Mercator; không phải lựa chọn chính xác cho mọi phép đo toàn cầu.

### Bài 17. SRID có vai trò gì?

**Đáp án:** Nhận diện coordinate reference system của geometry/geography.

### Bài 18. ST_SetSRID có thay đổi tọa độ không?

**Đáp án:** Không. Nó thay metadata SRID.

### Bài 19. ST_Transform làm gì?

**Đáp án:** Chuyển tọa độ từ CRS nguồn sang CRS đích.

### Bài 20. Vì sao không được gắn SRID đoán mò?

**Đáp án:** Metadata sai làm distance, area, overlay và transform cho kết quả sai.

### Bài 21. ST_MakePoint(106.7,10.8) tự có SRID 4326?

**Đáp án:** Không. Cần gắn SRID đúng bằng ST_SetSRID hoặc cách tạo phù hợp.

### Bài 22. WKT có luôn chứa SRID?

**Đáp án:** Không. WKT thông thường không chứa SRID; EWKT có thể chứa metadata PostGIS.

### Bài 23. GeoJSON RFC 7946 dùng coordinate order nào?

**Đáp án:** Longitude trước, latitude sau trong WGS 84 coordinate order.

### Bài 24. geometry(Point,4326) ràng buộc điều gì?

**Đáp án:** Geometry subtype Point và SRID 4326, cùng dimensionality theo typmod.

### Bài 25. geography(Point,4326) phù hợp khi nào?

**Đáp án:** Lưu điểm địa lý để dùng geography operations như distance theo meters.

### Bài 26. ST_Intersects trả lời câu hỏi gì?

**Đáp án:** Hai geometries có ít nhất một điểm chung hay không.

### Bài 27. ST_Contains và ST_Within liên hệ thế nào?

**Đáp án:** Chúng có quan hệ đảo chiều về argument, với boundary semantics cần hiểu rõ.

### Bài 28. Khi điểm nằm trên boundary và vẫn được tính thuộc vùng, nên xem hàm nào?

**Đáp án:** ST_Covers hoặc ST_CoveredBy tùy hướng argument.

### Bài 29. ST_DWithin có lợi gì so với lọc bằng ST_Distance?

**Đáp án:** Nó kiểm tra trong ngưỡng và có thể tận dụng spatial index.

### Bài 30. ST_Area trên geometry 4326 trả gì?

**Đáp án:** Diện tích theo units bình phương của CRS, thường là square degrees, không phải m².

### Bài 31. ST_Centroid có luôn nằm trong polygon?

**Đáp án:** Không. ST_PointOnSurface phù hợp hơn khi cần điểm trên surface.

### Bài 32. ST_IsValid dùng để làm gì?

**Đáp án:** Kiểm tra topology validity của geometry.

### Bài 33. ST_MakeValid có thể thay đổi geometry type?

**Đáp án:** Có. Output có thể là MultiGeometry hoặc GeometryCollection.

### Bài 34. GiST spatial index dùng để làm gì?

**Đáp án:** Tìm candidate geometries nhanh theo spatial index strategy, thường dựa trên bounding boxes.

### Bài 35. && có phải exact intersection không?

**Đáp án:** Không. Nó kiểm tra bounding-box overlap.

### Bài 36. ST_Intersects có thể dùng spatial index không?

**Đáp án:** Có, PostGIS có index-aware behavior cho predicate này khi query/planner phù hợp.

### Bài 37. Vì sao index không được dùng trong mọi query?

**Đáp án:** Predicate/operator, expression, selectivity, statistics và planner cost quyết định.

### Bài 38. KNN operator <-> giúp gì?

**Đáp án:** Hỗ trợ nearest-neighbor ordering trên operator classes/index phù hợp.

### Bài 39. KNN geometry 4326 có distance bằng mét không?

**Đáp án:** Không. Geometry distance vẫn theo planar coordinate units.

### Bài 40. Khi nào built-in point phù hợp?

**Đáp án:** Sơ đồ/canvas/game board hoặc local planar coordinates không cần CRS/GIS functions.

### Bài 41. Khi nào PostGIS phù hợp?

**Đáp án:** Geofencing, radius search, GIS layers, spatial joins, coordinate transformation và spatial analytics.

### Bài 42. PostGIS có tự geocode địa chỉ?

**Đáp án:** Không. Cần geocoding service/dataset; PostGIS lưu và truy vấn tọa độ.

### Bài 43. PostGIS tự tính road route nhanh nhất?

**Đáp án:** Không. Routing thường cần pgRouting hoặc routing engine chuyên biệt.

### Bài 44. Vì sao nên tạo functional index cho ST_Transform khi cần?

**Đáp án:** Query dùng expression transform column có thể không sử dụng index thường trên column gốc; functional index có thể hỗ trợ expression đó.

### Bài 45. Vì sao cần kiểm tra geometry type và SRID khi ingest?

**Đáp án:** Để ngăn dữ liệu sai CRS/type làm spatial calculations và joins sai.

### Bài 46. Migration từ point sang geometry nên làm theo pattern nào?

**Đáp án:** Add column, backfill có xác minh CRS, validate, dual-write/cutover rồi drop legacy column sau.

### Bài 47. Vì sao PostGIS package phải tương thích PostgreSQL major?

**Đáp án:** Extension shared libraries và package dependencies cần build/runtime tương thích với server major/platform.

### Bài 48. CREATE INDEX CONCURRENTLY có chạy trong transaction block thông thường không?

**Đáp án:** Không. Migration runner phải hỗ trợ non-transactional execution.

### Bài 49. Sau import spatial data cần kiểm tra gì?

**Đáp án:** Row counts, SRID, geometry type, bounds, validity, NULLs và sample output.

### Bài 50. Một quyết định chọn built-in type hay PostGIS cần dựa trên gì?

**Đáp án:** Có cần CRS, Earth distance/area, spatial predicates, transformations, GIS formats, indexing và khả năng mở rộng spatial workload hay không.

## 46. Checklist thiết kế dữ liệu không gian

| Câu hỏi | Điều cần xác định |
|---|---|
| Domain | Đây là sơ đồ phẳng hay vị trí trên Trái Đất? |
| Type | point/box built-in, geometry hay geography? |
| CRS | SRID nguồn và đích là gì? |
| Units | degrees, meters hay local units? |
| Axis | X/Y có đúng longitude/latitude order? |
| Dimension | XY, XYZ, XYM hay XYZM? |
| Type constraint | Point, LineString, Polygon, MultiPolygon? |
| Validity | Có kiểm tra ST_IsValid và domain bounds? |
| Boundary | Điểm trên ranh giới được coi inside hay outside? |
| Measurements | Distance/area cần planar hay geodetic? |
| Index | GiST/SP-GiST/functional index phù hợp? |
| Query | ST_DWithin/ST_Intersects có dùng index? |
| Performance | Geometry complexity/selectivity/EXPLAIN? |
| Migration | Backfill/dual-write/cutover có an toàn? |
| Operations | Extension package/version/backup/restore? |
| Security | Coordinates có nhạy cảm? |
| Integration | GeoJSON axis order/CRS contract? |
| Validation | Có known-point/reference-distance tests? |

## 47. Tài liệu PostgreSQL và PostGIS chính thức

- [PostgreSQL Geometric Types](https://www.postgresql.org/docs/current/datatype-geometric.html) — point, line, lseg, box, path, polygon và circle.
- [PostgreSQL Geometric Functions and Operators](https://www.postgresql.org/docs/current/functions-geometry.html) — built-in geometric operators/functions.
- [PostgreSQL Index Types](https://www.postgresql.org/docs/current/indexes-types.html) — GiST và các index methods.
- [PostGIS Documentation](https://postgis.net/documentation/) — hướng dẫn cài đặt và sử dụng PostGIS.
- [PostGIS Geometry](https://postgis.net/docs/geometry.html) — geometry type.
- [PostGIS Geography](https://postgis.net/docs/geography.html) — geography type.
- [PostGIS ST_SetSRID](https://postgis.net/docs/ST_SetSRID.html) — gắn SRID metadata.
- [PostGIS ST_Transform](https://postgis.net/docs/ST_Transform.html) — chuyển đổi tọa độ giữa CRS.
- [PostGIS Spatial Relationships](https://postgis.net/docs/reference.html#Spatial_Relationships) — predicates như ST_Intersects/ST_Contains.
- [PostGIS Measurement Functions](https://postgis.net/docs/reference.html#Measurement_Functions) — distance, area, length và measurement.
- [PostGIS Spatial Indexing](https://postgis.net/workshops/postgis-intro/indexing.html) — GiST, bounding boxes và query patterns.
- [PostGIS FAQ](https://postgis.net/documentation/faq/) — các câu hỏi triển khai phổ biến.

Function overloads, operator classes, CRS definitions và extension packaging thay đổi theo PostgreSQL/PostGIS/PROJ versions. Kiểm tra tài liệu đúng phiên bản, PostGIS_Full_Version() và execution plan thực tế trước khi triển khai production.

## 48. Tổng kết: kiểu dữ liệu phải phản ánh hệ tọa độ và bài toán

```text
Do we need Earth-referenced spatial data?
             |
       +-----+-----+
       |           |
      No          Yes
       |           |
       v           v
Built-in planar  Do we need geodetic
geometric types  calculations?
                   |
              +----+----+
              |         |
             Yes        No / local region
              |         |
              v         v
          geography   geometry + suitable CRS
              |         |
              +----+----+
                   |
                   v
      SRID + type + validity + units
                   |
                   v
          Spatial predicates/indexes
                   |
                   v
       Validate results and performance
```

Những nguyên tắc cần nhớ:

1. **PostgreSQL built-in geometric types là hình học phẳng.** Chúng phù hợp với point, line, box, path, polygon và circle trong hệ tọa độ do ứng dụng định nghĩa.
2. **Built-in point không biết CRS hoặc đơn vị.** Một cặp X/Y không tự là longitude/latitude.
3. **PostGIS bổ sung spatial model đầy đủ hơn.** Geometry, geography, SRID, functions, predicates và spatial indexes hỗ trợ GIS workloads.
4. **Geometry dùng planar coordinate units.** Với geometry 4326, distance/length/area không tự là meters/meters².
5. **Geography hỗ trợ geodetic measurements.** Nó tiện cho khoảng cách/diện tích trên Trái Đất nhưng function coverage và performance khác geometry.
6. **ST_SetSRID gắn metadata; ST_Transform đổi tọa độ.** Không dùng hai hàm thay thế cho nhau.
7. **Spatial index thường lọc candidate bằng bounding box.** Exact predicates vẫn cần để xác nhận quan hệ hình học.
8. **ST_DWithin thường phù hợp radius search.** Dùng EXPLAIN để xác nhận index và units.
9. **Validity không đồng nghĩa dữ liệu đúng nghiệp vụ.** Kiểm tra CRS, coordinate order, bounds và business semantics.
10. **PostGIS là extension theo database.** Cần package tương thích, CREATE EXTENSION, backup/restore và upgrade plan.
11. **Migration phải bảo toàn ý nghĩa tọa độ.** Xác minh CRS nguồn trước khi chuyển built-in point sang geometry.
12. **Chọn theo bài toán, không theo tên kiểu dữ liệu.** Sơ đồ phẳng có thể chỉ cần built-in types; GIS thực tế thường cần PostGIS.

**Một câu để nhớ:** *Kiểu hình học tích hợp của PostgreSQL mô tả hình trên mặt phẳng; PostGIS bổ sung hệ quy chiếu, mô hình địa lý, phép đo và index để làm việc với dữ liệu không gian thực tế.*

