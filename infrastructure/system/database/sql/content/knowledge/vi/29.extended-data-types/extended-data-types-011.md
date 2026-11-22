# Dữ liệu không gian và nhóm hàm truy vấn theo phần mở rộng trong SQL

Cơ sở dữ liệu quan hệ thường lưu **số, chuỗi, ngày giờ và khóa ngoại**. Nhưng các ứng dụng bản đồ, giao hàng, quản lý chi nhánh, quy hoạch hoặc theo dõi phương tiện còn cần trả lời những câu hỏi khác:

- Địa điểm nào nằm trong bán kính **1.000 mét** quanh một vị trí?
- Một điểm có nằm **trong vùng phục vụ** hay đúng trên ranh giới của vùng?
- Hai tuyến đường có **giao nhau** không?
- Kho hàng nào **gần khách hàng nhất**?
- Mỗi quận có bao nhiêu điểm giao hàng, nếu các vùng phục vụ **chồng lấn**?
- Làm sao tìm các đối tượng theo tọa độ mà không quét toàn bộ bảng?

SQL cơ bản có thể lưu hai cột `latitude` và `longitude`, nhưng hai cột số **không tự tạo ra phép toán không gian, phép biến đổi hệ tọa độ hay chỉ mục địa lý**. Nhiều hệ quản trị cung cấp kiểu dữ liệu và hàm mở rộng chuyên biệt: ví dụ **PostGIS cho PostgreSQL**, các kiểu hình học trong **MySQL**, `geometry`/`geography` của **SQL Server**, **Oracle Spatial**, hoặc **SpatiaLite cho SQLite**.

> **Điểm cốt lõi:** truy vấn không gian không chỉ là so sánh hai số tọa độ. Cần biết kiểu hình học, hệ quy chiếu tọa độ, đơn vị đo, quan hệ hình học, chỉ mục và cú pháp của phần mở rộng đang sử dụng.

Bài thuộc module **Database SQL**, chương **Dữ liệu mở rộng**, chủ đề **“Dữ liệu không gian và nhóm hàm truy vấn theo phần mở rộng”**. PostgreSQL + PostGIS là môi trường minh họa chính; phần sau đối chiếu MySQL, SQL Server, Oracle và SQLite/SpatiaLite.

Các tọa độ và vùng trong bài là **dữ liệu học tập gần Thành phố Hồ Chí Minh**, không đại diện cho ranh giới hành chính hoặc khoảng cách giao thông thực tế. Những phép đo tính theo đường thẳng trên bề mặt Trái Đất không thay thế thời gian di chuyển trên mạng đường.

## 1. Vì sao cần kiểu dữ liệu không gian?

Giả sử bảng địa điểm chỉ có hai cột:

```sql
CREATE TABLE places_simple (
    place_id INTEGER PRIMARY KEY,
    place_name TEXT NOT NULL,
    longitude NUMERIC(9, 6) NOT NULL,
    latitude NUMERIC(9, 6) NOT NULL
);
```

Ta có thể lọc đơn giản:

```sql
SELECT *
FROM places_simple
WHERE longitude BETWEEN 106.69 AND 106.71
  AND latitude BETWEEN 10.77 AND 10.79;
```

Đây là phép lọc trong **hình chữ nhật theo hai trục tọa độ**, không phải truy vấn “trong bán kính 1 km”:

- Khoảng chênh 1 độ kinh độ không bằng một khoảng cách mét cố định ở mọi vĩ độ.
- Một hình chữ nhật có thể chứa các góc nằm **ngoài vòng tròn bán kính** mong muốn.
- Câu SQL không thể tự xử lý đa giác có lỗ, đường đi, vùng chồng lấn hoặc giao cắt.
- Chỉ mục B-tree trên hai cột số không mang đầy đủ ngữ nghĩa của một chỉ mục hình học.
- Nếu dữ liệu dùng các hệ tọa độ khác nhau, so hai cặp số trực tiếp có thể vô nghĩa.

Kiểu `geometry` hoặc `geography` cho phép biểu diễn **điểm, đường, vùng và tập đối tượng**, còn các hàm không gian xử lý quan hệ và phép đo tương ứng.

### 1.1. Những bài toán điển hình

| Bài toán | Hình học | Nhóm hàm tiêu biểu |
|---|---|---|
| Cửa hàng gần nhất | Point | `ST_Distance`, KNN |
| Tìm cửa hàng trong bán kính | Point | `ST_DWithin` |
| Điểm thuộc vùng giao hàng | Point + Polygon | `ST_Contains`, `ST_Covers`, `ST_Intersects` |
| Hai tuyến đường giao cắt | LineString | `ST_Intersects`, `ST_Crosses` |
| Diện tích khu vực | Polygon | `ST_Area` |
| Chiều dài tuyến | LineString | `ST_Length` |
| Tạo vùng đệm | Point/Line/Polygon | `ST_Buffer` |
| Tính vùng hợp nhất | Polygon | `ST_Union` |
| Chuyển hệ tọa độ | Geometry | `ST_Transform` |
| Đưa dữ liệu lên bản đồ | Geometry | `ST_AsGeoJSON` |
| Làm sạch đa giác lỗi | Polygon | `ST_IsValid`, `ST_MakeValid` |
| Tối ưu tìm kiếm không gian | Geometry/Geography | GiST, R-tree, spatial index theo DBMS |

Tên hàm `ST_*` thường mang dấu ấn chuẩn **Simple Features**; nhưng **cú pháp, kiểu dữ liệu, đơn vị trả về và mức hỗ trợ vẫn khác nhau giữa hệ quản trị**.

## 2. Các loại hình học quan trọng

Một điểm và một vùng không chỉ là “chuỗi tọa độ”. Chúng có cấu trúc và ngữ nghĩa riêng.

| Kiểu | Ví dụ WKT | Ý nghĩa |
|---|---|---|
| `POINT` | `POINT(106.7 10.77)` | Một vị trí |
| `LINESTRING` | `LINESTRING(0 0, 1 1, 2 0)` | Một đường gấp khúc |
| `POLYGON` | `POLYGON((0 0, 2 0, 2 2, 0 2, 0 0))` | Một vùng khép kín |
| `MULTIPOINT` | `MULTIPOINT((0 0),(1 1))` | Nhiều điểm trong một đối tượng |
| `MULTILINESTRING` | `MULTILINESTRING((0 0,1 1),(1 0,2 1))` | Nhiều đường |
| `MULTIPOLYGON` | `MULTIPOLYGON(((0 0,1 0,1 1,0 1,0 0)))` | Nhiều vùng rời hoặc phức tạp |
| `GEOMETRYCOLLECTION` | `GEOMETRYCOLLECTION(POINT(0 0),LINESTRING(0 0,1 1))` | Một tập hình học khác loại |

**WKT** (*Well-Known Text*) là cách biểu diễn hình học bằng văn bản. Nó hữu ích để học và debug, nhưng không phải định dạng nội bộ tối ưu nhất để lưu/truyền ở mọi quy mô.

### 2.1. Cách đọc tọa độ

Trong chuỗi:

```text
POINT(106.7009 10.7769)
```

với cách dùng WGS84 phổ biến của PostGIS:

- `X = 106.7009`: kinh độ (*longitude*), theo hướng Đông/Tây.
- `Y = 10.7769`: vĩ độ (*latitude*), theo hướng Bắc/Nam.

**Đừng đảo thành `POINT(10.7769 106.7009)`** nếu dự định lưu `x=longitude, y=latitude` trong PostGIS.

Cần nhớ tiêu chuẩn EPSG có quy tắc trục tọa độ phức tạp hơn; một số DBMS/driver có cách diễn giải thứ tự trục riêng cho geographic SRID. **Thứ tự nhận tham số của hàm và thứ tự WKT không được suy đoán bằng tên “lat/lon”**.

### 2.2. Polygon phải đóng vòng

Một đa giác WKT có vòng ngoài, điểm đầu phải được lặp lại ở cuối:

```text
POLYGON((
    0 0,
    4 0,
    4 3,
    0 3,
    0 0
))
```

Đa giác có thể có vòng trong biểu diễn **lỗ**. Một điểm ở bên trong lỗ không được xem là nằm trong nội thất vùng, dù vẫn nằm trong **hộp bao** của đa giác.

### 2.3. Kiểu 2D, 3D và M

Một số hệ thống hỗ trợ tọa độ có:

- `X, Y`: vị trí trên mặt phẳng/hệ tọa độ.
- `Z`: độ cao hoặc tọa độ thứ ba.
- `M`: giá trị đo theo tuyến/chiều thứ tư trong một số quy ước.

Không mặc định hàm `ST_Distance` 2D sẽ tính độ chênh cao `Z`. PostGIS có các hàm chuyên biệt như `ST_3DDistance` cho geometry 3D, và **các trục phải có đơn vị tương thích**.

## 3. SRID, hệ tọa độ và đơn vị đo

**SRID** (*Spatial Reference System Identifier*) định danh một hệ tham chiếu không gian. Hai đối tượng có các con số X/Y trông tương tự chưa chắc so được nếu SRID khác nhau.

### 3.1. EPSG:4326 — WGS84 kinh/vĩ độ

Trong PostGIS:

```sql
SELECT
    ST_AsText(
        ST_SetSRID(
            ST_MakePoint(106.7009, 10.7769),
            4326
        )
    ) AS wkt,
    ST_SRID(
        ST_SetSRID(
            ST_MakePoint(106.7009, 10.7769),
            4326
        )
    ) AS srid;
```

Kết quả về bản chất là một `POINT(106.7009 10.7769)` có SRID `4326`.

Với `geometry(..., 4326)`:

- X/Y là tọa độ địa lý **theo độ**.
- `ST_Distance` giữa hai geometry này mặc định đo theo **đơn vị của hệ tọa độ**, tức độ trong trường hợp này.
- Không đọc kết quả `0.01` và gọi đó là “0,01 mét”.

### 3.2. EPSG:32648 — một hệ UTM dựa trên mét

Với ví dụ gần kinh độ 106–107° Đông ở miền Nam Việt Nam, **WGS84 / UTM zone 48N (EPSG:32648)** là ví dụ một hệ quy chiếu phẳng sử dụng **mét**; cần đánh giá độ phù hợp của phép chiếu với phạm vi nghiên cứu thực tế.

```sql
SELECT
    ST_AsText(
        ST_Transform(
            ST_SetSRID(
                ST_MakePoint(106.7009, 10.7769),
                4326
            ),
            32648
        )
    ) AS projected_point;
```

Kết quả có X/Y dạng giá trị tọa độ chiếu theo mét, không còn giống `106.7009`/`10.7769`.

### 3.3. ST_SetSRID không giống ST_Transform

Đây là sai lầm nghiêm trọng nhất khi bắt đầu làm GIS:

| Hàm | Làm gì? | Có tính lại X/Y? |
|---|---|---|
| `ST_SetSRID(geom, 4326)` | Gắn hoặc thay **nhãn hệ tọa độ** cho geometry | **Không** |
| `ST_Transform(geom, 32648)` | Biến đổi tọa độ sang hệ đích dựa trên thông tin hệ nguồn | **Có** |

Ví dụ đúng:

```sql
WITH p AS (
    SELECT ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    ) AS geom_wgs84
)
SELECT
    ST_SRID(geom_wgs84) AS source_srid,
    ST_SRID(ST_Transform(geom_wgs84, 32648)) AS target_srid,
    ST_AsText(ST_Transform(geom_wgs84, 32648))
        AS projected_wkt
FROM p;
```

Ví dụ sai về ý nghĩa:

```sql
-- SAI nếu tọa độ hiện đang là lon/lat theo độ:
SELECT ST_SetSRID(
    ST_MakePoint(106.7009, 10.7769),
    32648
);
```

Lệnh này không chuyển sang UTM: nó chỉ **gắn nhãn 32648 cho hai số độ**, khiến các phép tính tiếp theo sai.

### 3.4. Có thể nối hình học khác SRID bằng ST_Intersects không?

PostGIS thường yêu cầu các geometry tham gia nhiều phép toán như `ST_Intersects` có **cùng hệ tọa độ**; nếu không, có thể báo lỗi mixed SRID hoặc cho ngữ nghĩa không hợp lệ theo hàm.

Giải pháp là hiểu SRID gốc rồi **biến đổi đúng** một phía:

```sql
SELECT ST_Intersects(
    geom_4326,
    ST_Transform(geom_32648, 4326)
);
```

Đây là cú pháp ý tưởng: `geom_4326` và `geom_32648` phải là các giá trị hình học thật của những cột/bí danh tương ứng.

## 4. Geometry và geography trong PostGIS

PostGIS cung cấp hai kiểu hữu ích nhưng dễ bị nhầm.

| Vấn đề | `geometry` | `geography` |
|---|---|---|
| Mô hình | Hình học trong hệ tọa độ được khai báo, thường trên mặt phẳng | Tọa độ địa lý trên mô hình bề mặt Trái Đất |
| Đơn vị khoảng cách | Theo đơn vị của SRID geometry | **Mét** với các hàm đo phổ biến như `ST_Distance` |
| Với SRID 4326 | `ST_Distance` thường trả **độ** | `ST_Distance` trả **mét** |
| Phép đo | Phẳng theo hệ tọa độ | Dựa trên hình cầu/spheroid tùy hàm/tham số |
| Số lượng hàm | Rất phong phú | Một tập hàm hỗ trợ, không phải mọi hàm geometry đều có |
| Chỉ mục thường dùng | GiST/SP-GiST/BRIN theo loại và phiên bản | GiST và một số cơ chế phù hợp |
| Dùng khi | Topology, thao tác đa dạng, projection cục bộ | Khoảng cách gần đúng/đo địa lý theo mét trên WGS84 |

### 4.1. Hai phép đo trông giống nhưng đơn vị khác

```sql
WITH points AS (
    SELECT
        ST_SetSRID(
            ST_MakePoint(106.7009, 10.7769), 4326
        ) AS a,
        ST_SetSRID(
            ST_MakePoint(106.7020, 10.7770), 4326
        ) AS b
)
SELECT
    ST_Distance(a, b) AS distance_in_degrees,
    ST_Distance(
        a::geography,
        b::geography
    ) AS distance_in_meters
FROM points;
```

- Cột `distance_in_degrees` là độ tọa độ theo geometry 4326, **không được gọi là mét**.
- Cột `distance_in_meters` là mét theo phép đo địa lý của geography.

### 4.2. Geometry đã chiếu sang mét

```sql
WITH points AS (
    SELECT
        ST_SetSRID(ST_MakePoint(106.7009, 10.7769), 4326) AS a,
        ST_SetSRID(ST_MakePoint(106.7020, 10.7770), 4326) AS b
)
SELECT ST_Distance(
    ST_Transform(a, 32648),
    ST_Transform(b, 32648)
) AS approximate_planar_meters
FROM points;
```

Kết quả là khoảng cách phẳng dựa trên phép chiếu, đơn vị mét. Nó có thể gần nhưng không phải **cùng đại lượng chính xác tuyệt đối** với phép đo địa lý trên spheroid.

### 4.3. Không phải chọn một kiểu cho mọi hệ thống

Một hệ thống thường lưu `geometry(Point,4326)` để tương tác nhiều hàm và chỉ mục, rồi ép sang `geography` khi đo mét:

```sql
geom::geography
```

Có hệ thống chọn lưu `geography(Point,4326)` trực tiếp nếu nhu cầu chủ yếu là khoảng cách địa lý. Thiết kế nên dựa vào các hàm sẽ dùng, vùng dữ liệu và khả năng đánh chỉ mục theo biểu thức.

## 5. Cài đặt và kích hoạt phần mở rộng PostGIS

PostgreSQL cơ bản không tự có đầy đủ những hàm PostGIS như `ST_DWithin`/`ST_Transform`.

Nếu server đã cài gói PostGIS và tài khoản đủ quyền:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
```

Kiểm tra:

```sql
SELECT PostGIS_Version();
```

hoặc:

```sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'postgis';
```

### 5.1. Cần phân biệt cài gói và CREATE EXTENSION

- **Cài gói PostGIS**: chuẩn bị thư viện/extension trên máy chủ hoặc dịch vụ PostgreSQL.
- **CREATE EXTENSION postgis**: kích hoạt các đối tượng SQL cần thiết trong **database hiện tại**, theo quyền và chính sách của hệ thống.
- **Kiểm tra PostGIS_Version()**: xác nhận phiên bản đang dùng trong database.

Nếu dịch vụ PostgreSQL quản lý không cho cài extension hoặc không cấp quyền, người học cần môi trường hỗ trợ sẵn hoặc nhờ DBA; **không tìm cách vượt quyền**.

### 5.2. Extension có thể thay đổi cách triển khai

Các nền tảng managed PostgreSQL có danh sách extension/phiên bản được hỗ trợ. Những hàm nâng cao như `ST_MakeValid`, raster, topology hoặc routing có thể phụ thuộc phiên bản và extension bổ sung.

**Bài này giả định PostGIS đang sẵn sàng**. Không nên chạy lệnh tạo bảng `geometry` trước khi kích hoạt phần mở rộng thành công.

## 6. Tạo dữ liệu thực hành PostGIS: địa điểm và vùng

Ta tạo một bộ dữ liệu nhỏ để mọi truy vấn đều có ý nghĩa quan sát.

### 6.1. Bảng địa điểm

```sql
CREATE TABLE lesson370_places (
    place_id INTEGER PRIMARY KEY,
    place_name TEXT NOT NULL,
    place_type TEXT NOT NULL,
    geom geometry(Point, 4326) NOT NULL
);
```

Cột `geom geometry(Point,4326)` yêu cầu mỗi giá trị là **Point** có SRID **4326** phù hợp kiểu cột.

### 6.2. Thêm bảy địa điểm

```sql
INSERT INTO lesson370_places (
    place_id,
    place_name,
    place_type,
    geom
)
SELECT
    v.place_id,
    v.place_name,
    v.place_type,
    ST_SetSRID(
        ST_MakePoint(v.longitude, v.latitude),
        4326
    )
FROM (
    VALUES
      (1, 'Quán Bờ Sông',       'cafe',      106.7020, 10.7770),
      (2, 'Hiệu sách Đông',     'bookstore', 106.7130, 10.7800),
      (3, 'Trạm phía Tây',      'stop',      106.6800, 10.7600),
      (4, 'Cửa hàng Xa',       'store',     106.7350, 10.8000),
      (5, 'Quán Gần',          'cafe',      106.6990, 10.7750),
      (6, 'Điểm ranh giới',    'marker',    106.6950, 10.7760),
      (7, 'Điểm giao hai vùng','store',     106.7080, 10.7770)
) AS v (
    place_id,
    place_name,
    place_type,
    longitude,
    latitude
);
```

Dữ liệu chỉ mang tính ví dụ: tên quán/địa điểm không đại diện cho cơ sở có thật.

### 6.3. Bảng hai vùng hình chữ nhật

```sql
CREATE TABLE lesson370_zones (
    zone_id INTEGER PRIMARY KEY,
    zone_name TEXT NOT NULL,
    priority INTEGER NOT NULL,
    geom geometry(Polygon, 4326) NOT NULL
);
```

Thêm hai vùng:

```sql
INSERT INTO lesson370_zones (
    zone_id,
    zone_name,
    priority,
    geom
)
VALUES
(
    10,
    'Vùng lõi',
    1,
    ST_MakeEnvelope(
        106.695, 10.772,
        106.710, 10.782,
        4326
    )
),
(
    20,
    'Vùng phía Đông',
    2,
    ST_MakeEnvelope(
        106.705, 10.770,
        106.740, 10.810,
        4326
    )
);
```

`ST_MakeEnvelope(xmin,ymin,xmax,ymax,srid)` tạo hình chữ nhật theo hệ tọa độ đã chọn.

Hai vùng **có giao nhau** ở một phần tọa độ từ kinh độ khoảng 106.705 đến 106.710. Địa điểm số 7 được đặt ở vùng chồng lấn; địa điểm số 6 đặt **đúng trên cạnh trái của vùng lõi**.

### 6.4. Một điểm gốc để tìm kiếm

Trong các ví dụ, tâm tìm kiếm được tạo bằng:

```sql
SELECT ST_SetSRID(
    ST_MakePoint(106.7009, 10.7769),
    4326
) AS reference_point;
```

Tọa độ gốc khác với các địa điểm trong bảng. Nó không phải địa chỉ người dùng hay vị trí thiết bị thực tế.

### 6.5. Kiểm tra dữ liệu

```sql
SELECT
    place_id,
    place_name,
    ST_AsText(geom) AS point_wkt,
    ST_SRID(geom) AS srid
FROM lesson370_places
ORDER BY place_id;

SELECT
    zone_id,
    zone_name,
    ST_AsText(geom) AS polygon_wkt
FROM lesson370_zones
ORDER BY zone_id;
```

Dự kiến có **7 địa điểm** và **2 vùng**. Các tọa độ điểm in ra theo WKT `POINT(x y)`.

## 7. Nhóm hàm tạo và chuyển đổi hình học

Đầu tiên nên phân biệt các nhóm hàm theo nhiệm vụ.

| Nhóm | Hàm PostGIS tiêu biểu | Mục đích |
|---|---|---|
| Tạo hình học | `ST_MakePoint`, `ST_MakeLine`, `ST_MakePolygon` | Xây Point, đường hoặc vùng |
| Đọc WKT/WKB | `ST_GeomFromText`, `ST_GeomFromWKB` | Chuyển dữ liệu đầu vào thành geometry |
| Xuất dữ liệu | `ST_AsText`, `ST_AsBinary`, `ST_AsEWKT`, `ST_AsGeoJSON` | Chuẩn bị hiển thị/giao tiếp |
| Thông tin hình học | `ST_SRID`, `ST_GeometryType`, `ST_X`, `ST_Y`, `ST_NPoints` | Kiểm tra kiểu, tọa độ và cấu trúc |
| Hệ tọa độ | `ST_SetSRID`, `ST_Transform` | Gắn nhãn SRID hoặc biến đổi tọa độ |

### 7.1. Tạo từ WKT

```sql
SELECT ST_AsText(
    ST_GeomFromText(
        'POINT(106.7009 10.7769)',
        4326
    )
) AS wkt;
```

`ST_GeomFromText(text,srid)` phân tích WKT và gắn SRID đã cung cấp cho hình học được tạo.

### 7.2. Tạo đường

```sql
SELECT ST_AsText(
    ST_GeomFromText(
        'LINESTRING(106.700 10.776, 106.705 10.780, 106.710 10.782)',
        4326
    )
) AS route_wkt;
```

Đường này là một tập đoạn nối các điểm trên hình học địa lý; **không được coi tự động là tuyến đường giao thông hợp lệ**.

### 7.3. Lấy X/Y của điểm

```sql
SELECT
    place_id,
    ST_X(geom) AS longitude,
    ST_Y(geom) AS latitude
FROM lesson370_places
WHERE place_id = 1;
```

Với điểm số 1, kết quả X/Y về bản chất là `106.7020` và `10.7770`.

### 7.4. Kiểu đối tượng và số điểm

```sql
SELECT
    place_id,
    ST_GeometryType(geom) AS geometry_type,
    ST_SRID(geom) AS srid
FROM lesson370_places
ORDER BY place_id;
```

`ST_GeometryType` của điểm trả dạng tên hình học tương ứng, ví dụ `ST_Point`.

Với đa giác hoặc đường, các hàm cấu trúc như `ST_NPoints` có thể cho biết số đỉnh được lưu; số đỉnh **không phải số đối tượng thực tế** và cũng không trực tiếp là diện tích hay độ dài.

## 8. Nhóm hàm đo khoảng cách

### 8.1. ST_Distance cho geometry 4326

```sql
WITH origin AS (
    SELECT ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    ) AS geom
)
SELECT
    p.place_id,
    p.place_name,
    ST_Distance(p.geom, o.geom) AS distance_in_degrees
FROM lesson370_places AS p
CROSS JOIN origin AS o
ORDER BY distance_in_degrees;
```

Đây là khoảng cách **phẳng theo độ tọa độ**. Không gắn nhãn “mét”.

### 8.2. ST_Distance cho geography: đo mét

```sql
WITH origin AS (
    SELECT ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    )::geography AS geog
)
SELECT
    p.place_id,
    p.place_name,
    ROUND(
        ST_Distance(p.geom::geography, o.geog)::numeric,
        1
    ) AS distance_meters
FROM lesson370_places AS p
CROSS JOIN origin AS o
ORDER BY distance_meters, p.place_id;
```

Ở đây `distance_meters` đúng đơn vị mét theo hàm geography. Giá trị cụ thể được tính bởi PostGIS và có thể khác đôi chút theo phương pháp phép đo và phiên bản thư viện.

### 8.3. ST_Distance không phải thời gian di chuyển

Khoảng cách giữa hai tọa độ có thể chỉ 300 m theo đường thẳng, nhưng đường đi thực tế có thể dài hơn vì:

- Sông, cầu, đường một chiều.
- Lối đi cấm xe hoặc người đi bộ.
- Mạng đường không kết nối trực tiếp.
- Ùn tắc và quy tắc giao thông.

Để tìm **tuyến đường ngắn nhất trên mạng giao thông**, cần mô hình đồ thị tuyến đường và công cụ routing phù hợp, chẳng hạn **pgRouting** kết hợp dữ liệu mạng đường và PostGIS; `ST_Distance` không tự thay thế thuật toán tìm đường.

## 9. Nhóm hàm lọc theo bán kính: ST_DWithin

Người dùng yêu cầu:

> “Tìm địa điểm trong vòng **1.000 mét** quanh tọa độ (106.7009, 10.7769).”

Cách viết PostGIS rõ ràng:

```sql
WITH origin AS (
    SELECT ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    )::geography AS geog
)
SELECT
    p.place_id,
    p.place_name,
    ROUND(
        ST_Distance(
            p.geom::geography,
            o.geog
        )::numeric,
        1
    ) AS distance_meters
FROM lesson370_places AS p
CROSS JOIN origin AS o
WHERE ST_DWithin(
    p.geom::geography,
    o.geog,
    1000
)
ORDER BY distance_meters, p.place_id;
```

Các điểm trong bộ dữ liệu được chọn sao cho kết quả trong bán kính 1 km gồm **ID 1, 5, 6 và 7**. Những ID 2, 3, 4 ở xa hơn 1 km.

### 9.1. ST_DWithin khác ST_Distance ở mục đích truy vấn

- `ST_Distance(a,b)` trả **giá trị khoảng cách**.
- `ST_DWithin(a,b,r)` trả **boolean** cho biết khoảng cách có ở trong ngưỡng `r` hay không (theo định nghĩa, bao gồm trường hợp đúng bằng ngưỡng).

Một câu lọc bằng:

```sql
WHERE ST_Distance(
    p.geom::geography,
    o.geog
) <= 1000
```

có thể đúng về mặt điều kiện khoảng cách, nhưng thường **không tận dụng chỉ mục không gian hiệu quả** bằng dạng `ST_DWithin` được PostGIS hỗ trợ.

### 9.2. Tránh nhầm bán kính theo độ

Sai:

```sql
-- SAI khi 1000 có ý nghĩa là 1000 mét:
WHERE ST_DWithin(
    p.geom,
    origin_geom_4326,
    1000
)
```

Vì cả hai là `geometry(...,4326)` nên ngưỡng `1000` được hiểu theo **độ** (trên trục tọa độ geometry), không phải 1.000 m.

Đúng hơn:

```sql
WHERE ST_DWithin(
    p.geom::geography,
    origin_geom_4326::geography,
    1000
)
```

hoặc biến đổi cả hai geometry sang phép chiếu metric **phù hợp phạm vi địa lý** trước khi so ngưỡng mét.

### 9.3. Dùng index cho geography

Vì cột `geom` đang là geometry, có thể tạo GiST index trên biểu thức geography:

```sql
CREATE INDEX lesson370_places_geog_gix
ON lesson370_places
USING GIST ((geom::geography));
```

Sau đó:

```sql
ANALYZE lesson370_places;
```

Khi truy vấn dùng biểu thức tương ứng `p.geom::geography` với `ST_DWithin`, PostgreSQL/PostGIS có thể tận dụng **expression GiST index**.

**Không bảo đảm bảng 7 dòng sẽ xuất hiện Index Scan.** Planner có thể chọn Seq Scan vì quét bảy dòng rẻ hơn sử dụng index. Giá trị của chỉ mục rõ hơn ở dữ liệu lớn với điều kiện đủ chọn lọc.

## 10. Truy vấn “khoảng cách dưới 1 km” và “n địa điểm gần nhất” khác nhau

Hai yêu cầu thường bị nhầm:

1. **Trong bán kính 1 km:** có thể trả 0, 4 hoặc 10.000 địa điểm.
2. **5 địa điểm gần nhất:** cố lấy tối đa 5 địa điểm, kể cả nơi gần nhất cách rất xa nếu không có giới hạn bổ sung.

### 10.1. Lọc theo bán kính

```sql
SELECT *
FROM lesson370_places AS p
WHERE ST_DWithin(
    p.geom::geography,
    ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    )::geography,
    1000
);
```

Không có `LIMIT` thì số dòng do điều kiện khoảng cách quyết định.

### 10.2. N địa điểm gần nhất theo phép đo geography

```sql
WITH origin AS (
    SELECT ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    )::geography AS geog
)
SELECT
    p.place_id,
    p.place_name,
    ST_Distance(
        p.geom::geography,
        o.geog
    ) AS distance_meters
FROM lesson370_places AS p
CROSS JOIN origin AS o
ORDER BY distance_meters, p.place_id
LIMIT 5;
```

Câu này cho thứ tự theo `ST_Distance`, nhưng việc tính đầy đủ khoảng cách cho rất nhiều dòng có thể tốn chi phí.

### 10.3. KNN với toán tử <->

PostGIS cung cấp toán tử khoảng cách `<->` có thể được dùng với một số GiST index cho truy vấn **nearest neighbor**:

```sql
SELECT
    p.place_id,
    p.place_name
FROM lesson370_places AS p
ORDER BY
    p.geom::geography <->
    ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    )::geography
LIMIT 5;
```

Với geography, toán tử `<->` sử dụng **khoảng cách hình cầu** trong các trường hợp hỗ trợ KNN, còn `ST_Distance(geography,geography)` mặc định dùng phép đo theo **spheroid** trong PostGIS. Vì vậy **thứ tự KNN geography có thể không hoàn toàn trùng với thứ tự chính xác theo ST_Distance trên spheroid**.

Nếu cần xếp thứ tự chính xác theo mô hình đo đã chọn, phải tính và sắp xếp bằng hàm đo đó trên tập ứng viên thích hợp. Lấy shortlist KNN rồi sắp xếp lại thường hữu ích về hiệu năng, nhưng **không tự bảo đảm shortlist nhỏ luôn chứa tất cả top-N thật** ở mọi tình huống.

### 10.4. Geometry KNN theo SRID 4326 có giới hạn gì?

```sql
ORDER BY p.geom <-> origin_geom_4326
```

với geometry 4326 sử dụng **khoảng cách phẳng theo độ tọa độ**, không phải khoảng cách vật lý trên mặt đất.

Trong một vùng nhỏ điều này đôi khi đủ để sàng lọc gần đúng, nhưng muốn khoảng cách phẳng theo mét thì nên **biến đổi sang phép chiếu metric phù hợp** và thiết kế index tương ứng.

## 11. GiST index cho geometry và toán tử KNN

### 11.1. Chỉ mục geometry

```sql
CREATE INDEX lesson370_places_geom_gix
ON lesson370_places
USING GIST (geom);

CREATE INDEX lesson370_zones_geom_gix
ON lesson370_zones
USING GIST (geom);

ANALYZE lesson370_places;
ANALYZE lesson370_zones;
```

GiST là một trong những cấu trúc chỉ mục phổ biến giúp PostGIS tìm ứng viên theo vị trí và hình bao.

### 11.2. Chỉ mục biểu thức geometry đã biến đổi

Cho dữ liệu quanh Thành phố Hồ Chí Minh trong bài, minh họa index theo tọa độ UTM 48N:

```sql
CREATE INDEX lesson370_places_utm_gix
ON lesson370_places
USING GIST (ST_Transform(geom, 32648));
```

Truy vấn KNN theo hình học phẳng metric:

```sql
WITH origin AS (
    SELECT ST_Transform(
        ST_SetSRID(
            ST_MakePoint(106.7009, 10.7769),
            4326
        ),
        32648
    ) AS geom_utm
)
SELECT
    p.place_id,
    p.place_name
FROM lesson370_places AS p
CROSS JOIN origin AS o
ORDER BY
    ST_Transform(p.geom, 32648) <-> o.geom_utm
LIMIT 5;
```

Khi biểu thức phù hợp và planner thấy có lợi, **expression GiST index** có thể hỗ trợ thứ tự KNN trên phép chiếu đã chọn.

Với vùng dữ liệu khác, phải chọn phép chiếu metric tương ứng; EPSG:32648 **không phải hệ UTM chuẩn cho mọi khu vực trên thế giới**.

### 11.3. Expression index yêu cầu truy vấn khớp biểu thức

Index trên:

```sql
(geom::geography)
```

không hoàn toàn tương đương index trên:

```sql
geom
```

và index trên:

```sql
ST_Transform(geom, 32648)
```

là một cấu trúc khác nữa.

Nếu truy vấn đổi từ `geom::geography` sang `ST_Transform(geom,32648)`, không được mặc định index cũ sẽ phục vụ được biểu thức mới.

### 11.4. Đọc EXPLAIN cho truy vấn không gian

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.place_id, p.place_name
FROM lesson370_places AS p
WHERE ST_DWithin(
    p.geom::geography,
    ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    )::geography,
    1000
);
```

Xem:

- `Seq Scan`, `Index Scan` hay `Bitmap Heap Scan`?
- Có điều kiện index liên quan phép toán không gian không?
- Estimated rows và actual rows có lệch lớn không?
- Số block đọc/hit có cao không?
- Query đo trong điều kiện cache nào?

Bộ dữ liệu chỉ có bảy dòng, nên **Seq Scan không phải dấu hiệu index hỏng**.

## 12. Hộp bao không gian: toán tử &&

Một spatial index thường hỗ trợ bước lọc ứng viên qua **bounding box** (hộp chữ nhật bao hình học).

PostGIS có toán tử:

```sql
SELECT
    p.place_id,
    p.place_name
FROM lesson370_places AS p
WHERE p.geom && ST_MakeEnvelope(
    106.695, 10.772,
    106.710, 10.782,
    4326
);
```

`&&` kiểm tra **hộp bao giao nhau**, không phải mặc định một predicate hình học chính xác cho mọi loại hình phức tạp.

### 12.1. Với Point và rectangle thì sao?

Trong ví dụ điểm và hình chữ nhật, kết quả `&&` gần giống lọc theo biên tọa độ. Nhưng khi dùng:

- Một vùng chữ L.
- Đa giác lõm.
- Đa giác có lỗ.
- Đường cong hoặc tuyến chỉ đi qua vài vùng của bbox.

hộp bao có thể giao nhau dù **hình học thực tế không giao nhau**.

### 12.2. Lọc bbox rồi kiểm tra hình học thật

Mẫu an toàn khi cần phép giao hình học:

```sql
SELECT
    p.place_id,
    p.place_name
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON ST_Intersects(z.geom, p.geom)
WHERE z.zone_id = 10;
```

Trong PostGIS, các predicate như `ST_Intersects` thường tích hợp kiểm tra bbox/index bên trong quá trình chọn ứng viên khi có index phù hợp.

Không cần thay `ST_Intersects` bằng mỗi toán tử `&&` nếu yêu cầu là **đúng quan hệ hình học**.

## 13. Nhóm hàm quan hệ không gian

Những hàm sau trả boolean và diễn tả quan hệ giữa hai đối tượng hình học.

| Hàm | Câu hỏi nó trả lời |
|---|---|
| `ST_Intersects(a,b)` | Hai hình học có ít nhất một điểm chung? |
| `ST_Disjoint(a,b)` | Hai hình học hoàn toàn không giao nhau? |
| `ST_Contains(a,b)` | A chứa B theo định nghĩa topology, có điều kiện nội thất |
| `ST_Within(a,b)` | A nằm trong B theo quan hệ tương ứng |
| `ST_Covers(a,b)` | Không có điểm nào của B nằm ngoài A, gồm cả ranh giới |
| `ST_Touches(a,b)` | Hai hình học tiếp xúc ở biên mà không giao nhau tại nội thất theo nghĩa phù hợp |
| `ST_Overlaps(a,b)` | Hai đối tượng cùng chiều có phần chung và phần riêng theo định nghĩa overlap |
| `ST_Crosses(a,b)` | Hai hình học cắt qua nhau theo các điều kiện topology |
| `ST_Equals(a,b)` | Hai hình học bằng nhau về tập điểm/topology |
| `ST_Relate(a,b,pattern)` | Kiểm tra quan hệ topology theo mẫu DE-9IM |

Không nên gán `ST_Contains` = “bounding box của A bao bounding box của B”. Quan hệ topology xét **hình học thật**, có nhiều quy tắc về nội thất và ranh giới.

## 14. ST_Contains, ST_Covers và điểm trên ranh giới

Đây là khác biệt cần học bằng dữ liệu mẫu.

Vùng lõi:

```text
Kinh độ  106.695 ───────── 106.710
Vĩ độ   10.772  ───────── 10.782
```

Các điểm:

- ID 1: kinh độ 106.702 → **nằm bên trong** vùng lõi.
- ID 5: kinh độ 106.699 → **nằm bên trong**.
- ID 7: kinh độ 106.708 → **nằm bên trong**.
- ID 6: kinh độ **106.695**, vĩ độ 10.776 → **đúng trên cạnh trái** vùng lõi.

### 14.1. Truy vấn ST_Contains

```sql
SELECT
    p.place_id,
    p.place_name
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON ST_Contains(z.geom, p.geom)
WHERE z.zone_id = 10
ORDER BY p.place_id;
```

Với dữ liệu này, kết quả là các ID **1, 5, 7**. Điểm số 6 nằm trên ranh giới không được xem là thuộc **nội thất** theo cách `ST_Contains(Polygon,Point)` vận hành.

### 14.2. Truy vấn ST_Covers

```sql
SELECT
    p.place_id,
    p.place_name
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON ST_Covers(z.geom, p.geom)
WHERE z.zone_id = 10
ORDER BY p.place_id;
```

Kết quả gồm ID **1, 5, 6, 7**. `ST_Covers` cho phép điểm nằm trên ranh giới.

### 14.3. Truy vấn ST_Intersects

```sql
SELECT
    p.place_id,
    p.place_name
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON ST_Intersects(z.geom, p.geom)
WHERE z.zone_id = 10
ORDER BY p.place_id;
```

Với một **Point và Polygon** thông thường như bài mẫu, `ST_Intersects` cũng cho **1, 5, 6, 7**, vì điểm ranh giới vẫn có giao với polygon.

### 14.4. ST_Within đảo thứ tự đối số

```sql
SELECT p.place_id
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON ST_Within(p.geom, z.geom)
WHERE z.zone_id = 10
ORDER BY p.place_id;
```

Với điểm-vùng trong bài, `ST_Within(p,z)` tương ứng với `ST_Contains(z,p)`: các điểm trong nội thất là **1, 5, 7**.

### 14.5. ST_Touches và điểm ranh giới

```sql
SELECT p.place_id
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON ST_Touches(z.geom, p.geom)
WHERE z.zone_id = 10
ORDER BY p.place_id;
```

Kết quả có **ID 6** trong dữ liệu mẫu.

**Quy tắc nghiệp vụ mới quyết định predicate:**

- “Điểm ở **bên trong** vùng, không tính ranh” → cân nhắc `ST_Contains`.
- “Điểm ở trong **hoặc trên ranh** vùng” → cân nhắc `ST_Covers`.
- “Bất kỳ giao nhau nào” → `ST_Intersects`.
- “Chỉ ranh giới” → `ST_Touches` theo kiểu đối tượng phù hợp.

## 15. Spatial JOIN: nối bảng bằng vị trí thay vì khóa bằng nhau

JOIN quan hệ thông thường:

```sql
SELECT *
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id;
```

Spatial JOIN dùng điều kiện địa lý:

```sql
SELECT
    z.zone_id,
    z.zone_name,
    p.place_id,
    p.place_name
FROM lesson370_zones AS z
JOIN lesson370_places AS p
  ON ST_Covers(z.geom, p.geom)
ORDER BY z.zone_id, p.place_id;
```

Ở đây không có khóa `zone_id` được lưu trong bảng place; membership được **tính từ hình học**.

Với bộ dữ liệu:

- Vùng 10 có các ID **1, 5, 6, 7**.
- Vùng 20 có các ID **2, 4, 7**.

Địa điểm **7** nằm trong hai vùng, nên xuất hiện **hai lần** trong kết quả JOIN.

### 15.1. Đếm số địa điểm theo vùng

```sql
SELECT
    z.zone_id,
    z.zone_name,
    COUNT(p.place_id) AS place_count
FROM lesson370_zones AS z
LEFT JOIN lesson370_places AS p
  ON ST_Covers(z.geom, p.geom)
GROUP BY z.zone_id, z.zone_name
ORDER BY z.zone_id;
```

Kết quả mong đợi:

| zone_id | zone_name | place_count |
|---:|---|---:|
| 10 | Vùng lõi | 4 |
| 20 | Vùng phía Đông | 3 |

### 15.2. Vì sao tổng 4 + 3 không nhất thiết bằng số địa điểm duy nhất?

Vì địa điểm 7 nằm trong cả hai vùng:

\[
4 + 3 = 7
\]

là **tổng số membership (quan hệ điểm-vùng)**, không phải số địa điểm khác nhau.

Tập ID thuộc ít nhất một vùng là `{1,2,4,5,6,7}`, có **6 địa điểm duy nhất**. ID 3 nằm ngoài cả hai vùng.

Nếu báo cáo cần đếm thực thể không lặp, phải nêu rõ **grain** của số liệu và dùng cách khử trùng phù hợp.

### 15.3. Đếm địa điểm duy nhất nằm trong bất kỳ vùng nào

```sql
SELECT COUNT(*) AS unique_places_in_any_zone
FROM lesson370_places AS p
WHERE EXISTS (
    SELECT 1
    FROM lesson370_zones AS z
    WHERE ST_Covers(z.geom, p.geom)
);
```

Kết quả là **6**.

`EXISTS` tránh nhân dòng do một điểm khớp nhiều vùng nếu mục đích chỉ là kiểm tra “có nằm trong ít nhất một vùng không”.

### 15.4. Gán mỗi điểm vào đúng một vùng theo ưu tiên

Nếu yêu cầu nghiệp vụ là **mỗi địa điểm có đúng một vùng phụ trách**, đừng tùy tiện `GROUP BY` sau JOIN rồi lấy một giá trị bất kỳ.

Ta có thể định nghĩa **priority thấp hơn được ưu tiên**, sau đó chọn một vùng:

```sql
SELECT
    p.place_id,
    p.place_name,
    assigned.zone_id,
    assigned.zone_name
FROM lesson370_places AS p
LEFT JOIN LATERAL (
    SELECT
        z.zone_id,
        z.zone_name
    FROM lesson370_zones AS z
    WHERE ST_Covers(z.geom, p.geom)
    ORDER BY z.priority, z.zone_id
    LIMIT 1
) AS assigned ON TRUE
ORDER BY p.place_id;
```

Vì vùng 10 có `priority=1` và vùng 20 có `priority=2`, điểm 7 được gán về vùng 10. Điểm 3 không thuộc vùng nào nên `zone_id` là `NULL`.

**Quy tắc ưu tiên phải xuất phát từ yêu cầu nghiệp vụ**, không phải từ thứ tự dòng ngẫu nhiên của DBMS.

## 16. Lọc trước khi JOIN và vấn đề sử dụng chỉ mục

Một ví dụ tìm các quán cafe nằm trong vùng 10:

```sql
SELECT
    p.place_id,
    p.place_name
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON ST_Covers(z.geom, p.geom)
WHERE z.zone_id = 10
  AND p.place_type = 'cafe'
ORDER BY p.place_id;
```

Kết quả là ID **1** và **5**.

### 16.1. Vì sao spatial JOIN có thể tốn chi phí?

Nếu có:

- 1 triệu điểm,
- 50 nghìn vùng,

một phép thử hình học trên mọi cặp điểm-vùng sẽ quá lớn nếu không có cách giảm ứng viên.

PostGIS dùng spatial index và bounding-box filtering để loại bớt rất nhiều cặp trước khi thực hiện kiểm tra hình học chính xác. Nhưng hiệu năng còn phụ thuộc:

- Độ chọn lọc của vùng.
- Hình dạng/độ phức tạp của polygon.
- Mức chồng lấn giữa các vùng.
- Thống kê PostgreSQL.
- Cấu trúc JOIN và các điều kiện bổ sung.
- Chỉ mục ở phía geometry thích hợp.

### 16.2. Không dùng mỗi bbox khi cần quy tắc đúng

Sai về mục tiêu:

```sql
-- Chỉ lọc theo bounding box, có thể nhận false positives.
SELECT p.place_id
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON p.geom && z.geom;
```

Đúng theo quan hệ nghiệp vụ “vùng chứa cả điểm ranh giới”:

```sql
SELECT p.place_id
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON ST_Covers(z.geom, p.geom);
```

Khi có index phù hợp, predicate chính xác có thể dùng cơ chế lọc bbox nội bộ trước khi kiểm tra topology.

## 17. Nhóm hàm đo diện tích và chiều dài

### 17.1. ST_Area với geometry 4326

```sql
SELECT
    zone_id,
    ST_Area(geom) AS area_in_square_degrees
FROM lesson370_zones;
```

Ở đây diện tích là **độ vuông** trên hệ tọa độ hình học 4326, **không phải m²**.

### 17.2. ST_Area với geography trả m²

```sql
SELECT
    zone_id,
    zone_name,
    ROUND(
        (ST_Area(geom::geography) / 1000000.0)::numeric,
        3
    ) AS area_km2
FROM lesson370_zones
ORDER BY zone_id;
```

Hàm `ST_Area(geography)` trả m² theo phép đo địa lý phù hợp; chia cho 1.000.000 để đổi sang km².

### 17.3. Diện tích theo phép chiếu metric

```sql
SELECT
    zone_id,
    ST_Area(ST_Transform(geom, 32648))
        AS projected_area_m2
FROM lesson370_zones
ORDER BY zone_id;
```

Đây là diện tích theo phép chiếu phẳng UTM 48N. Không mong phép đo này trùng hoàn toàn `ST_Area(geography)` vì khác mô hình phép đo.

### 17.4. Chiều dài đường

```sql
WITH route AS (
    SELECT ST_GeomFromText(
        'LINESTRING(106.700 10.776, 106.705 10.780, 106.710 10.782)',
        4326
    ) AS geom
)
SELECT
    ST_Length(geom) AS length_degrees,
    ST_Length(geom::geography) AS length_meters
FROM route;
```

Với geometry 4326, phép tính `ST_Length` cho LineString dùng đơn vị tọa độ (độ); với geography, trả mét theo định nghĩa hàm.

Đường gấp khúc trong WKT chỉ là các đoạn hình học; không phải lộ trình giao thông có giới hạn tốc độ hoặc luật đi đường.

## 18. ST_Buffer: tạo vùng quanh một hình

Một yêu cầu khác là tạo vùng trong phạm vi xấp xỉ 500 m quanh một địa điểm.

### 18.1. Sai lầm nguy hiểm

```sql
-- SAI nếu 500 có nghĩa là 500 mét:
SELECT ST_Buffer(geom, 500)
FROM lesson370_places
WHERE place_id = 1;
```

Với `geom geometry(Point,4326)`, tham số buffer dùng **đơn vị độ**, không phải mét. Bán kính 500 độ là hoàn toàn sai với bài toán này.

### 18.2. Dùng geography cho khoảng cách mét

```sql
SELECT
    place_id,
    ST_AsText(
        ST_Buffer(geom::geography, 500)::geometry
    ) AS buffer_wkt
FROM lesson370_places
WHERE place_id = 1;
```

PostGIS hỗ trợ `ST_Buffer(geography, meters)` bằng cách chọn một phép chiếu phẳng thích hợp nội bộ rồi biến đổi kết quả trở lại; vùng đệm là **xấp xỉ hình học**, không phải một hình tròn địa lý hoàn hảo với mọi sai số bằng 0.

### 18.3. Dùng projection metric tường minh

```sql
SELECT
    place_id,
    ST_AsText(
        ST_Buffer(
            ST_Transform(geom, 32648),
            500
        )
    ) AS buffer_utm_wkt
FROM lesson370_places
WHERE place_id = 1;
```

Kết quả buffer ở SRID 32648, đơn vị mét; muốn dùng với các hình học 4326 thì phải `ST_Transform(...,4326)` trở lại.

### 18.4. Đừng dùng buffer thay ST_DWithin khi chỉ cần lọc

Nếu chỉ cần kiểm tra điểm trong bán kính, thường dùng:

```sql
ST_DWithin(point_a::geography, point_b::geography, 500)
```

thay vì tạo buffer polygon cho mỗi dòng và kiểm tra intersects. Hàm chuyên biệt `ST_DWithin` có thể sử dụng chỉ mục hiệu quả hơn.

## 19. Nhóm hàm tổng hợp hình học

PostGIS có các hàm tổng hợp và biến đổi hình học, nhưng không được đánh đồng ý nghĩa.

| Hàm | Ý nghĩa chính |
|---|---|
| `ST_Collect` | Gom nhiều geometry thành một đối tượng tập hợp, không nhất thiết hợp nhất topology |
| `ST_Union` | Hợp nhất hình học theo topology, có thể làm tan đường biên chung |
| `ST_Envelope` | Hộp bao chữ nhật của một geometry |
| `ST_Extent` | Tổng hợp bounding box trên một tập geometry |
| `ST_Centroid` | Tính trọng tâm hình học, có thể nằm ngoài đa giác lõm |
| `ST_PointOnSurface` | Chọn một điểm trên bề mặt của geometry theo ngữ nghĩa hàm |
| `ST_Intersection` | Lấy phần giao hình học |
| `ST_Difference` | Phần A không thuộc B |
| `ST_SymDifference` | Phần thuộc một trong hai hình nhưng không thuộc cả hai |

### 19.1. ST_Collect không bằng ST_Union

Gộp hai vùng:

```sql
SELECT ST_AsText(
    ST_Collect(geom)
) AS combined_geometry
FROM lesson370_zones;
```

Có thể cho một MultiPolygon/GeometryCollection chứa cả hai polygon, kể cả khi chúng chồng lấn.

Trong khi:

```sql
SELECT ST_AsText(
    ST_Union(geom)
) AS dissolved_geometry
FROM lesson370_zones;
```

thực hiện **hợp nhất theo topology**, loại bỏ ranh giới chồng lấn phù hợp để biểu diễn vùng phủ chung.

Đối với diện tích phủ của hai vùng giao nhau:

```sql
SELECT
    ST_Area(
        ST_Union(geom)::geography
    ) / 1000000.0 AS union_area_km2
FROM lesson370_zones;
```

Không cộng đơn thuần diện tích mỗi vùng rồi gọi đó là diện tích phủ duy nhất, vì phần giao nhau sẽ bị **đếm hai lần**.

### 19.2. Trọng tâm và điểm đặt nhãn

```sql
SELECT
    zone_id,
    ST_AsText(ST_Centroid(geom)) AS centroid_wkt,
    ST_AsText(ST_PointOnSurface(geom)) AS interior_label_wkt
FROM lesson370_zones
ORDER BY zone_id;
```

Với rectangle, cả hai thường nằm bên trong. Nhưng với polygon dạng móng ngựa hoặc có lỗ, `ST_Centroid` có thể nằm **ngoài nội thất vùng**.

Nếu cần một điểm đặt nhãn **nằm trên bề mặt polygon**, `ST_PointOnSurface` thường phù hợp hơn.

### 19.3. ST_Extent

```sql
SELECT ST_Extent(geom) AS all_places_bbox
FROM lesson370_places;
```

`ST_Extent` trả một dạng hộp bao tổng hợp (box) của tất cả địa điểm. Bbox **không thay thế vùng phủ chính xác** nếu dữ liệu có nhiều vùng rời.

## 20. Nhóm hàm kiểm tra và sửa hình học

Một polygon không phải cứ có chuỗi WKT đúng ngữ pháp là hợp lệ về topology.

### 20.1. Polygon tự cắt

Ví dụ một hình dạng “nơ” có các cạnh cắt nhau:

```sql
SELECT
    ST_IsValid(
        ST_GeomFromText(
            'POLYGON((0 0, 2 2, 0 2, 2 0, 0 0))',
            4326
        )
    ) AS is_valid,
    ST_IsValidReason(
        ST_GeomFromText(
            'POLYGON((0 0, 2 2, 0 2, 2 0, 0 0))',
            4326
        )
    ) AS reason;
```

Đa giác tự cắt có thể bị `ST_IsValid` báo FALSE và `ST_IsValidReason` chỉ vị trí/lý do lỗi.

### 20.2. ST_MakeValid

```sql
WITH broken AS (
    SELECT ST_GeomFromText(
        'POLYGON((0 0, 2 2, 0 2, 2 0, 0 0))',
        4326
    ) AS geom
)
SELECT
    ST_AsText(ST_MakeValid(geom)) AS repaired_wkt,
    ST_GeometryType(ST_MakeValid(geom))
        AS repaired_type
FROM broken;
```

**ST_MakeValid có thể đổi kiểu hình học**: từ Polygon lỗi thành MultiPolygon hoặc GeometryCollection tùy trường hợp và phiên bản.

Không gán kết quả vào cột `geometry(Polygon,4326)` mà không kiểm tra rằng đầu ra có đúng kiểu và đáp ứng invariant nghiệp vụ.

### 20.3. ST_Simplify và topology

Khi polygon có quá nhiều đỉnh, một số quy trình hiển thị có thể dùng `ST_Simplify` hoặc `ST_SimplifyPreserveTopology` để giảm độ phức tạp.

Nhưng:

- Việc làm đơn giản có thể thay đổi đường biên.
- Có thể làm thay đổi quan hệ điểm-trong-vùng gần ranh giới.
- Tolerances dùng **đơn vị của hệ tọa độ geometry**, nên `0.001` với SRID 4326 là **độ**, không phải 0,001 m.
- Không được đơn giản hóa dữ liệu gốc pháp lý/đo đạc mà không đánh giá yêu cầu độ chính xác.

Nếu mục đích chỉ là tăng hiệu năng hiển thị, thường nên tách **geometry cho phân tích chính xác** và **geometry rút gọn cho biểu diễn**.

### 20.4. ST_Subdivide cho polygon lớn

Một vùng rất phức tạp có thể được chia thành các phần nhỏ bằng `ST_Subdivide` để giúp một số phép lọc/index có bounding box hẹp hơn.

Điều này có thể cải thiện một số spatial join lớn, nhưng phải xử lý đúng việc một đối tượng gốc bị chia thành **nhiều phần** để tránh đếm trùng thực thể.

**Chia polygon làm nhiều dòng không đồng nghĩa đã thay đổi số vùng nghiệp vụ.**

## 21. GeoJSON, WKT, WKB và trao đổi dữ liệu

### 21.1. WKT dễ đọc nhưng không lưu SRID theo chuẩn WKT thường

```sql
SELECT
    ST_AsText(geom) AS wkt,
    ST_AsEWKT(geom) AS ewkt
FROM lesson370_places
WHERE place_id = 1;
```

`ST_AsText` xuất WKT hình học; `ST_AsEWKT` là dạng PostGIS mở rộng có thể chứa thông tin `SRID=...`.

Đừng mong chuỗi `POINT(...)` thông thường tự nói rõ đang là EPSG:4326 hay EPSG:32648.

### 21.2. WKB là dạng nhị phân

`ST_AsBinary(geom)` cung cấp WKB, phù hợp một số giao thức và thư viện. EWKB là dạng mở rộng PostGIS có thể lưu thêm thông tin như SRID.

Khi giao tiếp giữa DBMS, cần xác định **định dạng chuẩn, byte order, SRID và khả năng hỗ trợ Z/M**, không chỉ truyền bytes và giả định hệ nhận luôn hiểu giống nhau.

### 21.3. Xuất GeoJSON

```sql
SELECT
    place_id,
    place_name,
    ST_AsGeoJSON(geom)::jsonb AS geometry_json
FROM lesson370_places
ORDER BY place_id;
```

Một Point GeoJSON có dạng:

```json
{
  "type": "Point",
  "coordinates": [106.702, 10.777]
}
```

**Trong dữ liệu bài**, phần tử đầu là kinh độ, phần tử sau là vĩ độ. Không đổi thành lat/lon vì thói quen hiển thị trên giao diện.

### 21.4. Đọc GeoJSON geometry

```sql
SELECT
    ST_AsText(
        ST_GeomFromGeoJSON(
            '{"type":"Point","coordinates":[106.702,10.777]}'
        )
    ) AS parsed_wkt;
```

Trong các phiên bản PostGIS hiện đại, `ST_GeomFromGeoJSON` có thể gán SRID mặc định cho GeoJSON phù hợp. Hãy **kiểm tra `ST_SRID`** sau khi parse và xác nhận hệ quy chiếu thực của dữ liệu đầu vào thay vì giả định.

Hàm này dùng cho **fragment geometry GeoJSON**, không được mặc định cho rằng bạn có thể đưa trực tiếp mọi `FeatureCollection` với properties vào mà không xử lý cấu trúc ở tầng ứng dụng.

### 21.5. Chuyển về WGS84 khi xuất bản đồ

Nếu geometry lưu trong một hệ chiếu như 32648, hãy biến đổi đúng trước khi xuất GeoJSON theo quy ước tọa độ địa lý cần thiết:

```sql
SELECT ST_AsGeoJSON(
    ST_Transform(geom_utm, 4326)
);
```

`geom_utm` là giá trị geometry giả định có SRID nguồn đúng; không dùng chuỗi này như câu SELECT hoàn chỉnh nếu chưa có cột hoặc biểu thức tương ứng.

### 21.6. Độ chính xác và bảo mật

Một điểm có 6 chữ số sau dấu thập phân có thể chỉ ra vị trí rất cụ thể. Không công bố tọa độ riêng tư trong log, báo cáo hoặc API công khai nếu nghiệp vụ không cần.

Việc giảm số chữ số của GeoJSON để tiết kiệm băng thông cũng có thể ảnh hưởng topology. Với các đa giác chính xác, cần cân nhắc biến đổi đơn giản hóa/làm tròn theo công cụ phù hợp và kiểm tra tính hợp lệ.

## 22. Tìm tuyến giao cắt và quan hệ đường-vùng

Không chỉ Point, các hàm không gian xử lý LineString/Polygon.

### 22.1. Đường đi qua vùng

```sql
WITH route AS (
    SELECT ST_GeomFromText(
        'LINESTRING(106.690 10.776, 106.720 10.776)',
        4326
    ) AS geom
)
SELECT
    z.zone_id,
    z.zone_name
FROM lesson370_zones AS z
CROSS JOIN route AS r
WHERE ST_Intersects(z.geom, r.geom)
ORDER BY z.zone_id;
```

Tuyến minh họa đi từ kinh độ 106.690 đến 106.720 ở vĩ độ 10.776, cắt qua cả vùng lõi và vùng phía Đông.

### 22.2. Giao phần đường nằm trong vùng

```sql
WITH route AS (
    SELECT ST_GeomFromText(
        'LINESTRING(106.690 10.776, 106.720 10.776)',
        4326
    ) AS geom
)
SELECT
    z.zone_id,
    ST_AsText(
        ST_Intersection(z.geom, r.geom)
    ) AS clipped_route_wkt
FROM lesson370_zones AS z
CROSS JOIN route AS r
WHERE ST_Intersects(z.geom, r.geom)
ORDER BY z.zone_id;
```

`ST_Intersection` có thể trả một hình học khác loại (Point/LineString/MultiLineString/GeometryCollection) tùy vị trí giao. Không mặc định kết quả luôn là LineString.

### 22.3. ST_Crosses, ST_Touches và ST_Intersects

- `ST_Intersects` chỉ cần có giao.
- `ST_Touches` nhấn mạnh giao ở ranh giới theo topology.
- `ST_Crosses` nhấn mạnh quan hệ cắt qua giữa các loại hình phù hợp.
- Nếu một đường hoàn toàn nằm trong polygon, có thể `ST_Intersects=TRUE` nhưng `ST_Crosses` không nhất thiết TRUE.

Từ “cắt” trong ngôn ngữ tự nhiên không luôn tương đương hàm `ST_Crosses`. Hãy diễn đạt chính xác điều kiện nghiệp vụ cần.

## 23. Các nhóm phần mở rộng không gian nâng cao

Không gian không chỉ có Point/Polygon.

### 23.1. PostGIS geometry/geography

Phù hợp:

- Tìm kiếm điểm gần.
- Vùng phục vụ.
- Giao nhau, chứa nhau.
- Đo khoảng cách/diện tích/độ dài.
- Spatial index, chuyển SRID.
- Xử lý và trao đổi dữ liệu vector.

Đây là phần mở rộng cốt lõi của bài.

### 23.2. PostGIS raster

**Raster** biểu diễn dữ liệu dạng lưới ô, ví dụ độ cao, nhiệt độ, mưa hoặc lớp ảnh.

Một số phiên bản/cài đặt PostGIS phân tách khả năng raster thành extension tương ứng như `postgis_raster`, với các hàm như `ST_Value`, `ST_SummaryStats`.

Không áp dụng nguyên xi logic Point/Polygon cho raster; raster có kích thước pixel, georeference, band, NODATA và phép lấy mẫu riêng.

### 23.3. PostGIS Topology

Khả năng topology dùng các đối tượng như node, edge, face và quy tắc chia sẻ ranh giới, phù hợp một số nghiệp vụ quản lý bản đồ và mạng lưới.

Extension `postgis_topology` có mục tiêu khác với truy vấn `ST_Intersects` đơn giản giữa hai geometry.

### 23.4. pgRouting

**pgRouting** bổ sung các thuật toán đồ thị cho bài toán routing trên mạng đường, ví dụ tìm đường ngắn nhất dựa trên đỉnh/cạnh và chi phí.

Nó không tự biến mọi LineString thành tuyến đường có thể đi. Cần dữ liệu mạng:

- Đỉnh và cạnh kết nối đúng.
- Hướng di chuyển một chiều/hai chiều.
- Trọng số chiều dài, thời gian hoặc chi phí.
- Điểm đầu/cuối được ánh xạ lên mạng.

### 23.5. Hệ lưới ô và không gian phân cấp

Một số hệ sinh thái hỗ trợ H3, geohash hoặc các mã ô không gian. Các công cụ này hữu ích cho gom nhóm và phân mảnh theo ô, nhưng:

- Ô lưới không thay thế geometry gốc trong mọi bài toán.
- Ranh giới ô tạo sai số xấp xỉ.
- Phải hiểu cấp độ phân giải.
- Có thể cần spatial predicate chính xác sau bước lọc.

Không đánh đồng **vector embedding** (ví dụ extension dùng cho tìm kiếm ngữ nghĩa) với dữ liệu không gian địa lý: cả hai có thể gọi là “vector” nhưng metric và ý nghĩa khác nhau.

## 24. MySQL Spatial: cùng ý tưởng, khác chi tiết SRID và hàm

MySQL 8.x hỗ trợ các kiểu không gian như `POINT`, `LINESTRING`, `POLYGON` và các hàm `ST_*`. Tuy nhiên không được giả định chức năng y hệt PostGIS.

### 24.1. Tạo bảng có POINT theo SRID

Ví dụ MySQL 8.x:

```sql
CREATE TABLE lesson370_mysql_places (
    place_id INT PRIMARY KEY,
    place_name VARCHAR(100) NOT NULL,
    location POINT NOT NULL SRID 4326,
    SPATIAL INDEX location_spidx (location)
) ENGINE = InnoDB;
```

Khả năng tạo spatial index và điều kiện SRID phụ thuộc phiên bản/kiểu bảng/engine. Ở MySQL 8.0+ việc khai báo SRID và tính phù hợp của dữ liệu đặc biệt quan trọng với truy vấn không gian theo hệ tọa độ địa lý.

### 24.2. Thứ tự trục khi đọc WKT

MySQL có những quy tắc liên quan **axis order theo hệ tham chiếu**. Một dạng minh họa rõ ý định kinh độ-vĩ độ là:

```sql
INSERT INTO lesson370_mysql_places (
    place_id,
    place_name,
    location
)
VALUES (
    1,
    'Điểm A',
    ST_GeomFromText(
        'POINT(106.7009 10.7769)',
        4326,
        'axis-order=long-lat'
    )
);
```

Tham số `axis-order=long-lat` của MySQL trên các phiên bản hỗ trợ giúp tránh nhầm với thứ tự trục mà SRS định nghĩa. **Không chuyển cú pháp tùy chọn thứ ba này sang PostgreSQL `ST_GeomFromText`**.

### 24.3. Khoảng cách hình cầu

MySQL cung cấp hàm như `ST_Distance_Sphere` cho phép tính khoảng cách trên hình cầu theo đơn vị tuyến tính thích hợp:

```sql
SELECT
    place_id,
    ST_Distance_Sphere(
        location,
        ST_GeomFromText(
            'POINT(106.7020 10.7770)',
            4326,
            'axis-order=long-lat'
        )
    ) AS distance_meters
FROM lesson370_mysql_places;
```

Phải kiểm tra **loại geometry, SRID, phương pháp đo và phiên bản**. Không suy rằng `ST_Distance_Sphere` và PostGIS `ST_Distance(geography)` luôn cho cùng kết quả đến từng phần nhỏ mét: một bên có thể dựa trên mô hình hình cầu, một bên mặc định dùng spheroid.

### 24.4. Quan hệ topology và spatial index

MySQL hỗ trợ các predicate như `ST_Intersects`, `ST_Contains` và các phép toán bounding box trong nhóm `MBR*`.

**MBR** (*minimum bounding rectangle*) là phép so theo hộp bao. Không dùng `MBRContains` thay cho `ST_Contains` khi cần quan hệ hình học chính xác trên polygon phức tạp.

### 24.5. Không giả định PostGIS syntax tồn tại trong MySQL

Ví dụ PostGIS:

```sql
geom::geography
```

là cú pháp cast PostgreSQL, **không phải cú pháp MySQL**. MySQL cũng không tự hỗ trợ tất cả hàm PostGIS như `ST_DWithin` với cùng signature/đơn vị/index strategy.

Muốn port query phải xác minh chức năng, mô hình đo và cách tối ưu hóa trên MySQL, không chỉ thay tên bảng.

## 25. SQL Server: geometry và geography là kiểu native

SQL Server hỗ trợ hai kiểu không gian:

- `geometry`: dữ liệu hình học trên hệ tọa độ phẳng.
- `geography`: dữ liệu địa lý trên bề mặt Trái Đất.

Đây là khả năng tích hợp của SQL Server, **không phải phần mở rộng PostGIS**.

### 25.1. Tạo geography point bằng latitude, longitude

Trong T-SQL:

```sql
DECLARE @origin geography =
    geography::Point(10.7769, 106.7009, 4326);

DECLARE @place geography =
    geography::Point(10.7770, 106.7020, 4326);

SELECT @origin.STDistance(@place) AS distance_meters;
```

**Điểm rất dễ nhầm:** constructor `geography::Point(latitude, longitude, SRID)` nhận **vĩ độ trước, kinh độ sau**. Điều này **khác với `ST_MakePoint(longitude, latitude)` của PostGIS**.

### 25.2. STDistance, STIntersects

SQL Server dùng cú pháp method trên đối tượng:

```sql
SELECT
    @origin.STDistance(@place) AS distance_meters,
    @origin.STIntersects(@place) AS intersects_flag;
```

Khi hai đối tượng chỉ là hai điểm khác nhau, `STIntersects` cho giá trị không giao. Quan hệ vùng-điểm có thể dùng `STIntersects` trên polygon/geography tương ứng.

Các phép đo của geography có ngữ nghĩa/đơn vị theo hệ tham chiếu và phương thức SQL Server; không dùng quy tắc `geom::geography` của PostgreSQL.

### 25.3. SRID phải tương thích

Một số phép toán spatial của SQL Server với hai đối tượng khác SRID có thể trả `NULL` thay vì tự biến đổi hệ tọa độ.

Đừng coi `NULL` nghĩa là “khoảng cách bằng 0” hoặc “không giao nhau”. Cần kiểm tra SRID của cả hai phía và cách tạo/biến đổi dữ liệu.

### 25.4. Spatial index

SQL Server có `CREATE SPATIAL INDEX` với các điều kiện schema/index riêng, khác cú pháp PostgreSQL:

```sql
-- Cú pháp khái niệm, chỉ thực hiện khi đã chuẩn bị
-- đúng bảng, khóa và các yêu cầu spatial index SQL Server.
CREATE SPATIAL INDEX place_geo_index
ON dbo.places(geo_location);
```

Hãy đối chiếu tài liệu phiên bản SQL Server vì spatial index có yêu cầu về khóa chỉ mục và đối tượng, cùng những tùy chọn/phương pháp tessellation.

## 26. Oracle Spatial: SDO_GEOMETRY và nhóm SDO_*

Oracle Spatial thường dùng kiểu `SDO_GEOMETRY` và những hàm/toán tử trong họ `SDO_*`.

### 26.1. Một điểm SDO_GEOMETRY

Ví dụ SQL Oracle:

```sql
SELECT SDO_GEOMETRY(
    2001,
    4326,
    SDO_POINT_TYPE(106.7009, 10.7769, NULL),
    NULL,
    NULL
) AS point_geom
FROM dual;
```

Trong kiểu geometry này, `2001` chỉ hình học Point 2D theo mã gtype tương ứng; `4326` là SRID; `SDO_POINT_TYPE` chứa tọa độ.

### 26.2. Lọc trong khoảng cách

Oracle cung cấp hàm/toán tử như `SDO_WITHIN_DISTANCE`:

```sql
SELECT p.place_id
FROM lesson370_oracle_places AS p
WHERE SDO_WITHIN_DISTANCE(
    p.geom,
    SDO_GEOMETRY(
        2001, 4326,
        SDO_POINT_TYPE(106.7009, 10.7769, NULL),
        NULL, NULL
    ),
    'distance=1000 unit=M'
) = 'TRUE';
```

Đây là ví dụ cấu trúc. Bảng `lesson370_oracle_places` giả định đã có cột `geom SDO_GEOMETRY` hợp lệ với metadata/index phù hợp; **không phải bảng được tạo bởi phần PostGIS**.

### 26.3. Quan hệ không gian

Oracle còn có:

- `SDO_RELATE` với mask tương ứng.
- `SDO_FILTER` cho bước lọc sơ bộ.
- `SDO_NN` cho nearest neighbor theo ngữ nghĩa Oracle.
- `SDO_DISTANCE` cho khoảng cách.
- `SDO_AREA`, `SDO_LENGTH` và các nhóm tiện ích khác.

Ví dụ ý tưởng:

```sql
WHERE SDO_RELATE(
    p.geom,
    :zone_geom,
    'mask=ANYINTERACT'
) = 'TRUE'
```

Oracle Spatial có cơ chế metadata hệ tọa độ, spatial index và tham số đơn vị riêng. Đừng thay `ST_Intersects` bằng `SDO_RELATE` mà không xác định mask và kiểu đối tượng.

## 27. SQLite và SpatiaLite

SQLite core **không có đầy đủ các hàm GIS và hệ SRID** như PostGIS. Khi cần truy vấn hình học, nhiều hệ thống dùng **SpatiaLite** hoặc một extension chuyên dụng được hỗ trợ.

### 27.1. Nạp extension cần được phép

Tùy môi trường, công cụ SQLite có thể dùng:

```sql
SELECT load_extension('mod_spatialite');
```

Nhưng việc nạp extension động **không phải lúc nào cũng bật mặc định**, và có yêu cầu bảo mật/đường dẫn thư viện. Không tự bật việc nạp thư viện tùy ý trên ứng dụng không tin cậy.

### 27.2. Kiểu geometry và metadata

Trong một thiết lập SpatiaLite phù hợp, có thể tạo bảng thông thường rồi dùng các thủ tục/hàm của extension để thêm cột geometry và đăng ký metadata.

Một luồng minh họa:

```sql
CREATE TABLE lesson370_sqlite_places (
    place_id INTEGER PRIMARY KEY,
    place_name TEXT NOT NULL
);

SELECT AddGeometryColumn(
    'lesson370_sqlite_places',
    'geom',
    4326,
    'POINT',
    'XY'
);
```

Những bước như khởi tạo spatial metadata hoặc tính sẵn có của `AddGeometryColumn` phụ thuộc phiên bản SpatiaLite và môi trường. Đây là ví dụ về **mô hình triển khai**, không phải script cài extension chạy được trong mọi SQLite nguyên bản.

### 27.3. Truy vấn và chỉ mục

SpatiaLite có các hàm mang tên quen thuộc như `ST_Intersects`, `ST_Distance`, `Transform` và cơ chế spatial index dựa trên R-tree/MBR theo cấu hình.

Nhưng:

- Cú pháp index không tương đương PostgreSQL `USING GIST`.
- Kiểu đơn vị phụ thuộc SRID/hàm, không thể mặc định là mét.
- Cần kiểm tra extension đã thực sự được nạp.
- SQLite nguyên bản chỉ với hai cột lat/lon **không tự có ST_DWithin của PostGIS**.

### 27.4. R-tree core và GIS là hai tầng khác nhau

SQLite có R-tree extension phục vụ index theo các dải tọa độ hoặc hộp chữ nhật. Một R-tree giúp tìm **ứng viên theo bounding box**, nhưng không tự cung cấp mọi phép đo geodesic, kiểm tra polygon có lỗ và chuyển SRID chính xác.

**Spatial index không thay thế spatial semantics.**

## 28. Bảng đối chiếu SQL không gian giữa hệ quản trị

| Khía cạnh | PostgreSQL + PostGIS | MySQL Spatial | SQL Server | Oracle Spatial | SQLite + SpatiaLite |
|---|---|---|---|---|---|
| Kiểu chính | `geometry`, `geography` | `POINT`/`GEOMETRY` và SRID | `geometry`, `geography` | `SDO_GEOMETRY` | Geometry của extension |
| Tạo điểm WGS84 | `ST_SetSRID(ST_MakePoint(lon,lat),4326)` | `ST_GeomFromText`, chú ý axis order | `geography::Point(lat,lon,4326)` | `SDO_GEOMETRY(... SDO_POINT_TYPE(lon,lat,...))` | Hàm khởi tạo geometry của SpatiaLite |
| Khoảng cách | `ST_Distance` | `ST_Distance`/`ST_Distance_Sphere` theo ngữ nghĩa SRID | `.STDistance()` | `SDO_DISTANCE` | `ST_Distance` nếu extension hỗ trợ |
| Lọc bán kính | `ST_DWithin` | Chọn hàm khoảng cách/MBR phù hợp phiên bản | `STDistance() <= r` và spatial optimization theo engine | `SDO_WITHIN_DISTANCE` | Hàm và spatial index tùy extension |
| Quan hệ giao | `ST_Intersects` | `ST_Intersects` | `.STIntersects()` | `SDO_RELATE` | `ST_Intersects` |
| Chỉ mục | GiST và các phương án khác | `SPATIAL INDEX` | `CREATE SPATIAL INDEX` | Oracle spatial index | R-tree/spatial index của extension |
| Biến đổi SRID | `ST_Transform` | Theo hàm/phiên bản SRS hỗ trợ | Không suy có cùng `ST_Transform` của PostGIS | Công cụ/hàm transform của Oracle | `Transform` nếu extension hỗ trợ |
| Cài extension? | Cần PostGIS | Thường tích hợp MySQL | Native | Native/feature Oracle Spatial | Cần SpatiaLite hoặc tương đương |

**Không tồn tại một câu SQL không gian phức tạp chạy nguyên văn trên tất cả DBMS.** Khi chuyển hệ, phải đối chiếu cả **cú pháp lẫn đơn vị, mô hình đo, axis order, ranh giới hình học và cách dùng index**.

## 29. Phân biệt dữ liệu không gian và dữ liệu bản đồ

Một database lưu Point/Polygon không tự có:

- Ảnh nền bản đồ.
- Tên đường và địa chỉ chuẩn hóa.
- Tuyến đường nhanh nhất.
- Giao thông theo thời gian thực.
- Địa giới hành chính chính xác và có hiệu lực theo ngày.
- Dữ liệu nâng cao về độ cao, sông, đường, công trình.

Những khả năng đó cần **nguồn dữ liệu bên ngoài hoặc mô hình khác**, như mạng đường, dữ liệu raster hoặc dịch vụ geocoding.

### 29.1. Geocoding và reverse geocoding

- **Geocoding:** chuyển địa chỉ như “số nhà, đường, quận” thành tọa độ.
- **Reverse geocoding:** từ tọa độ suy ra địa chỉ/địa danh phù hợp.

`ST_Contains` và `ST_Distance` **không tự giải quyết geocoding**. Cần bảng địa chỉ được chuẩn hóa hoặc dịch vụ dữ liệu vị trí.

### 29.2. Dữ liệu địa giới có phiên bản

Nếu vùng phục vụ hoặc ranh giới hành chính thay đổi theo thời gian, một spatial JOIN trên polygon **hiện tại** không tự trả lời câu hỏi “địa điểm này thuộc vùng nào vào tháng trước?”.

Có thể cần:

- `effective_from`, `effective_to`.
- Bản ghi version của polygon.
- Khóa phiên bản và truy vấn temporal + spatial.
- Chính sách xử lý biến động vùng.

### 29.3. Location data có thể nhạy cảm

Tọa độ nơi ở, nơi làm việc, lịch sử di chuyển hoặc vị trí thiết bị có thể là dữ liệu cá nhân nhạy cảm.

Một thiết kế có trách nhiệm cần xem:

- Quyền truy cập theo vai trò.
- Mức chính xác thật sự cần lưu.
- Thời hạn lưu giữ.
- Mục tiêu sử dụng đã xác định.
- Cách ẩn/làm mờ vị trí ở báo cáo công khai.

Không mặc định mọi tọa độ đều có thể xuất ra GeoJSON cho mọi người dùng.

## 30. Hiệu năng và quản lý dữ liệu lớn

### 30.1. Spatial index không bảo đảm mọi query nhanh

Có GiST index nhưng planner có thể vẫn chọn Seq Scan khi:

- Bảng rất nhỏ.
- Điều kiện trả phần lớn bảng.
- Predicate không sử dụng index theo dạng viết.
- Có cast/transform trên cột nhưng index không khớp.
- Thống kê không phù hợp.
- Hình học rất phức tạp hoặc có bbox lớn bao phủ gần hết dữ liệu.

Cần đọc `EXPLAIN (ANALYZE, BUFFERS)` và workload thật.

### 30.2. Bbox của vùng quá lớn làm index kém chọn lọc

Một Polygon lớn có lỗ hoặc hình chữ C có thể có bbox bao phủ rất nhiều điểm **không thật sự nằm trong vùng**. Chỉ mục vẫn lấy nhiều ứng viên rồi phải kiểm tra chính xác.

Giải pháp có thể là phân chia geometry phức tạp (`ST_Subdivide`), tối ưu dữ liệu hoặc thay chiến lược truy vấn, nhưng phải giữ khóa định danh gốc và ngăn đếm trùng.

### 30.3. Geometry validity ảnh hưởng phép toán

Polygon không hợp lệ có thể làm `ST_Intersection`, `ST_Union` hoặc các phép topology báo lỗi hay cho kết quả không mong muốn. Nên kiểm tra dữ liệu tại bước nhập và xác định chính sách xử lý invalid geometry.

### 30.4. ST_Transform trên từng dòng có thể tốn CPU

```sql
WHERE ST_DWithin(
    ST_Transform(p.geom, 32648),
    reference_utm,
    1000
)
```

nếu chạy trên hàng triệu dòng mà **không có expression index phù hợp**, có thể rất tốn.

Các lựa chọn:

- Index trên geometry ở hệ được dùng nhiều.
- Expression index trên `ST_Transform(geom,target_srid)`.
- Lưu thêm geometry đã chiếu nếu nhu cầu cố định và quản lý đồng bộ đúng.
- Dùng geography + index tương ứng cho truy vấn khoảng cách.

Không nhân đôi dữ liệu không gian chỉ vì “trông nhanh hơn” mà chưa đo lợi ích và chi phí cập nhật.

### 30.5. Spatial JOIN cần rõ grain

Một vùng có nhiều điểm và một điểm có thể nằm trong nhiều vùng, tạo quan hệ **N:N**. Khi cộng tổng doanh thu theo vùng, một đơn hàng/điểm có thể bị tính lặp.

Nếu yêu cầu là tính theo **membership**, cộng lặp có thể có chủ đích. Nếu yêu cầu là tổng doanh thu duy nhất toàn hệ thống, cần chính sách gán vùng/khử trùng.

### 30.6. GeoJSON quá lớn là vấn đề khác với SQL index

Một SELECT trả hàng nghìn polygon với hàng triệu đỉnh có thể tốn:

- CPU xuất JSON.
- Băng thông.
- Bộ nhớ client.
- Thời gian render bản đồ.

Cần phân trang, cắt theo vùng nhìn, phân cấp độ phóng, rút gọn geometry biểu diễn hoặc dùng vector tiles theo kiến trúc phù hợp.

## 31. Những sai lầm thường gặp

### Lỗi 1. Nhầm kinh độ và vĩ độ

PostGIS `ST_MakePoint(x,y)` thường nhận `lon,lat` cho WGS84. SQL Server `geography::Point(lat,lon,srid)` nhận **lat,lon**. Không có một quy tắc vị trí tham số áp dụng cho mọi hàm.

### Lỗi 2. ST_Distance geometry 4326 là mét

Sai. Phép đo geometry 4326 theo tọa độ **độ**. Dùng geography hoặc projection metric phù hợp.

### Lỗi 3. ST_SetSRID được dùng để biến đổi tọa độ

Sai. `ST_SetSRID` chỉ gắn nhãn. `ST_Transform` mới tính lại tọa độ.

### Lỗi 4. Hai hình khác SRID được so trực tiếp

Không an toàn. Cần xác định hệ nguồn và biến đổi đúng. Không tự thay SRID metadata để “hết lỗi”.

### Lỗi 5. Lọc theo bbox coi như điểm nằm trong polygon

Bbox có thể chứa vùng ngoài hình thật, nhất là polygon lõm/có lỗ. Dùng predicate topology chính xác khi nghiệp vụ yêu cầu.

### Lỗi 6. ST_Contains tính cả điểm trên ranh

Với Point trên ranh Polygon, `ST_Contains(Polygon,Point)` là FALSE theo định nghĩa thường dùng. `ST_Covers` phù hợp hơn khi cần tính cả ranh.

### Lỗi 7. ST_Intersects đồng nghĩa hai vùng chồng lấn nội thất

Không. Hai hình chỉ chạm ở biên vẫn có thể intersects.

### Lỗi 8. SUM/COUNT sau spatial JOIN luôn là số thực thể duy nhất

Không. Điểm có thể thuộc nhiều vùng; JOIN tạo nhiều membership. Chọn grain và quy tắc khử trùng.

### Lỗi 9. ST_DWithin geometry 4326 với radius 1000 được hiểu là 1 km

Không. Đó là 1000 **độ** nếu dùng geometry 4326.

### Lỗi 10. ST_Buffer(geom,500) luôn là 500 m

Chỉ khi geometry dùng hệ tọa độ có đơn vị mét phù hợp. Với geometry 4326, giá trị 500 dùng đơn vị độ.

### Lỗi 11. ST_Distance trong WHERE luôn tối ưu như ST_DWithin

Không. `ST_DWithin` có cơ chế spatial index hỗ trợ lọc bán kính; dùng `ST_Distance <= r` có thể phải tính quá nhiều khoảng cách.

### Lỗi 12. Chỉ mục geometry tự hỗ trợ mọi phép cast geography

Không. Expression index `(geom::geography)` và geometry index `(geom)` là các cấu trúc khác.

### Lỗi 13. Bảng bảy dòng không dùng GiST nghĩa index lỗi

Không. Seq Scan có thể rẻ hơn trên bảng nhỏ. Đọc plan trong bối cảnh dữ liệu.

### Lỗi 14. Nearest neighbor KNN geography luôn bằng thứ tự spheroid ST_Distance

Không hoàn toàn. `<->` có cách đo hình cầu trong các trường hợp PostGIS hỗ trợ, còn `ST_Distance(geography)` mặc định theo spheroid.

### Lỗi 15. Điểm gần theo đường thẳng đồng nghĩa giao hàng nhanh nhất

Không. Mạng đường, vận tốc và hướng di chuyển quyết định đường đi thực tế; cần routing.

### Lỗi 16. Polygon WKT đúng cú pháp thì chắc chắn hợp lệ

Không. Polygon tự cắt có thể parse được nhưng `ST_IsValid` = FALSE.

### Lỗi 17. ST_MakeValid giữ nguyên kiểu Polygon

Không nhất thiết. Có thể trả MultiPolygon hoặc GeometryCollection, cần kiểm tra kiểu đầu ra.

### Lỗi 18. ST_Centroid luôn nằm trong Polygon

Không. Với vùng lõm hoặc có lỗ, trọng tâm có thể ở ngoài vùng; cân nhắc `ST_PointOnSurface`.

### Lỗi 19. ST_Collect giống ST_Union

Không. `ST_Collect` gom hình; `ST_Union` hợp nhất topology và xử lý vùng chồng lấn.

### Lỗi 20. MySQL WKT luôn dùng thứ tự trục y hệt PostGIS

Không nên giả định. Geographic SRS và tùy chọn axis order của MySQL cần được xác minh.

### Lỗi 21. SQL Server geography dùng cùng cú pháp ::geography của PostgreSQL

Không. SQL Server có kiểu và method `geography::Point`, `.STDistance()`; không port cú pháp trực tiếp.

### Lỗi 22. SQLite core tự có đủ bộ hàm PostGIS

Không. Cần extension như SpatiaLite hoặc triển khai GIS khác, theo khả năng môi trường.

### Lỗi 23. R-tree index tự tính được mọi quan hệ polygon

R-tree chủ yếu giúp truy cập theo bounding box, không thay thế phép đo geodesic hay topology chính xác.

### Lỗi 24. GeoJSON luôn có cùng SRID và ý nghĩa trục ở mọi pipeline

Cần kiểm tra định dạng, hệ nguồn và cách sinh dữ liệu; dữ liệu geometry đầu vào có thể cần `ST_Transform` về hệ quy chiếu phù hợp.

### Lỗi 25. 3D Point dùng ST_Distance là tính cả độ cao

Không mặc định. Nhiều phép đo geometry là 2D; dùng hàm 3D phù hợp và đảm bảo đơn vị X/Y/Z nhất quán.

### Lỗi 26. Khi polygon chồng lấn, spatial JOIN vẫn là 1:N từ vùng sang điểm

Không. Khi điểm nằm trong nhiều vùng, quan hệ là N:N về mặt membership, có thể nhân dòng và số liệu.

### Lỗi 27. Đổi SRID mà không ghi lại dữ liệu nguồn

Khi ETL nhầm hệ quy chiếu, việc gắn lại nhãn mà không xác minh hệ tọa độ thật có thể làm sai toàn bộ dữ liệu không gian.

### Lỗi 28. Bỏ qua tính riêng tư của tọa độ

Vị trí chính xác có thể tiết lộ nơi ở/di chuyển. Thiết kế quyền và độ chính xác xuất dữ liệu theo nhu cầu.

## 32. Bài tập có lời giải

Các bài dùng dữ liệu `lesson370_places` và `lesson370_zones` trên PostgreSQL + PostGIS, trừ khi bài ghi rõ DBMS khác. Kết quả đếm đã được xác định theo dữ liệu học tập; kết quả thời gian đo, cost và plan phụ thuộc môi trường.

### Bài 1. Xây điểm WGS84

**Yêu cầu:** tạo Point ở kinh độ 106.7009, vĩ độ 10.7769, SRID 4326.

**Đáp án:**

```sql
SELECT ST_SetSRID(
    ST_MakePoint(106.7009, 10.7769),
    4326
);
```

Tham số `ST_MakePoint` theo thứ tự **X=lon, Y=lat** trong cách dùng PostGIS này.

### Bài 2. Đọc SRID từ một cột

**Đáp án:**

```sql
SELECT
    place_id,
    ST_SRID(geom) AS srid
FROM lesson370_places
ORDER BY place_id;
```

Các giá trị đều có SRID `4326` vì kiểu cột yêu cầu như vậy.

### Bài 3. SetSRID có chuyển mét không?

**Câu hỏi:** `ST_SetSRID(geom_4326,32648)` có chuyển kinh/vĩ độ thành mét không?

**Đáp án:** **Không**. Nó chỉ thay nhãn SRID. Phải `ST_Transform(geom_4326,32648)` nếu nguồn thật là 4326.

### Bài 4. Tính khoảng cách theo mét

```sql
SELECT
    ST_Distance(
        a.geom::geography,
        b.geom::geography
    ) AS distance_meters
FROM lesson370_places AS a
JOIN lesson370_places AS b
  ON a.place_id = 1
 AND b.place_id = 5;
```

**Đáp án:** kết quả theo **mét** (địa lý), không phải độ. Giá trị chính xác do PostGIS tính.

### Bài 5. Tìm nơi trong bán kính 1 km

**Đáp án:**

```sql
SELECT place_id
FROM lesson370_places
WHERE ST_DWithin(
    geom::geography,
    ST_SetSRID(
        ST_MakePoint(106.7009, 10.7769),
        4326
    )::geography,
    1000
)
ORDER BY place_id;
```

Kết quả: **1, 5, 6, 7**.

### Bài 6. Vì sao dùng ST_DWithin thay ST_Distance <= 1000?

**Đáp án:** `ST_DWithin` diễn đạt trực tiếp lọc bán kính và có cơ chế tận dụng spatial index phù hợp, trong khi tính `ST_Distance` cho mọi dòng rồi so ngưỡng có thể tốn tài nguyên hơn.

### Bài 7. Chỉ mục cho geography cast

**Đáp án:**

```sql
CREATE INDEX lesson370_places_geog_gix
ON lesson370_places
USING GIST ((geom::geography));
```

Nếu index đã được tạo ở phần trước, không tạo trùng tên. Bảng rất nhỏ có thể vẫn Seq Scan.

### Bài 8. Có những loại địa điểm nào?

```sql
SELECT
    place_type,
    COUNT(*) AS n
FROM lesson370_places
GROUP BY place_type
ORDER BY place_type;
```

**Đáp án:** `cafe=2`, `store=2`, `bookstore=1`, `stop=1`, `marker=1`.

### Bài 9. Điểm nào nằm trong nội thất vùng 10?

```sql
SELECT p.place_id
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON ST_Contains(z.geom, p.geom)
WHERE z.zone_id = 10
ORDER BY p.place_id;
```

**Đáp án:** **1, 5, 7**. Điểm 6 ở biên không tính.

### Bài 10. Cần tính cả ranh giới vùng

**Đáp án:**

```sql
SELECT p.place_id
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON ST_Covers(z.geom, p.geom)
WHERE z.zone_id = 10
ORDER BY p.place_id;
```

Kết quả: **1, 5, 6, 7**.

### Bài 11. Tìm riêng điểm tiếp xúc ranh

```sql
SELECT p.place_id
FROM lesson370_places AS p
JOIN lesson370_zones AS z
  ON ST_Touches(z.geom, p.geom)
WHERE z.zone_id = 10
ORDER BY p.place_id;
```

**Đáp án:** **6**.

### Bài 12. Đếm theo vùng

```sql
SELECT
    z.zone_id,
    COUNT(p.place_id) AS total
FROM lesson370_zones AS z
LEFT JOIN lesson370_places AS p
  ON ST_Covers(z.geom, p.geom)
GROUP BY z.zone_id
ORDER BY z.zone_id;
```

**Đáp án:** vùng 10 có **4**, vùng 20 có **3** membership.

### Bài 13. Vì sao tổng vùng bằng 7 nhưng chỉ có 6 địa điểm thuộc vùng?

**Đáp án:** địa điểm 7 nằm trong **cả hai vùng**. Tổng mỗi vùng đếm quan hệ điểm-vùng, không phải tổng thực thể duy nhất.

### Bài 14. Đếm điểm trong ít nhất một vùng

```sql
SELECT COUNT(*) AS unique_places
FROM lesson370_places AS p
WHERE EXISTS (
    SELECT 1
    FROM lesson370_zones AS z
    WHERE ST_Covers(z.geom, p.geom)
);
```

**Đáp án:** **6**, vì ID 3 ở ngoài và ID 7 chỉ được đếm một lần.

### Bài 15. Gán một vùng theo ưu tiên

**Đáp án:** dùng `LEFT JOIN LATERAL` chọn `ORDER BY z.priority,z.zone_id LIMIT 1` như phần 15.4. Với điểm 7, vùng được chọn là **10**.

### Bài 16. ST_Area của geometry 4326 có đơn vị gì?

**Đáp án:** đơn vị theo tọa độ phẳng, về mặt bài này là **độ vuông**, không phải m².

### Bài 17. Tính km² của vùng

```sql
SELECT
    zone_id,
    ST_Area(geom::geography) / 1000000.0
        AS area_km2
FROM lesson370_zones
ORDER BY zone_id;
```

**Đáp án:** hàm trả m² và phép chia đổi thành km².

### Bài 18. ST_Buffer 500 m

**Đáp án:**

```sql
SELECT ST_Buffer(
    geom::geography,
    500
)
FROM lesson370_places
WHERE place_id = 1;
```

Không dùng `ST_Buffer(geom,500)` trực tiếp trên geometry 4326 nếu `500` có nghĩa mét.

### Bài 19. Tại sao ST_Collect và ST_Union khác nhau?

**Đáp án:** `ST_Collect` gom các geometry thành tập, có thể giữ phần chồng lấn; `ST_Union` thực hiện hợp nhất topology, phù hợp khi muốn vùng phủ duy nhất.

### Bài 20. Tìm trọng tâm và điểm nội thất vùng

```sql
SELECT
    zone_id,
    ST_AsText(ST_Centroid(geom)),
    ST_AsText(ST_PointOnSurface(geom))
FROM lesson370_zones;
```

**Đáp án:** với rectangle cả hai thường nằm trong; với polygon phức tạp, centroid có thể nằm ngoài, còn point-on-surface được dùng để chọn điểm trên hình.

### Bài 21. Polygon tự cắt có hợp lệ không?

```sql
SELECT ST_IsValid(
    ST_GeomFromText(
        'POLYGON((0 0, 2 2, 0 2, 2 0, 0 0))',
        4326
    )
);
```

**Đáp án:** **FALSE** cho hình nơ tự cắt. Có thể dùng `ST_IsValidReason` để tìm nguyên nhân.

### Bài 22. ST_MakeValid luôn trả Polygon?

**Đáp án:** **Không**. Có thể trả MultiPolygon hoặc GeometryCollection. Kiểm tra `ST_GeometryType` trước khi ghi trở lại cột hạn chế kiểu.

### Bài 23. KNN geography và spheroid

**Câu hỏi:** `ORDER BY geom::geography <-> ref_geog` luôn cùng thứ tự với `ORDER BY ST_Distance(geom::geography,ref_geog)`?

**Đáp án:** Không bảo đảm tuyệt đối: KNN geography sử dụng phép đo hình cầu trong các trường hợp hỗ trợ, còn `ST_Distance` geography mặc định theo spheroid.

### Bài 24. SQL Server tạo geography point

**Đáp án:**

```sql
SELECT geography::Point(
    10.7769,
    106.7009,
    4326
).STAsText() AS wkt;
```

Constructor nhận **latitude trước, longitude sau**.

### Bài 25. MySQL có ép kiểu ::geography như PostgreSQL?

**Đáp án:** không. Cú pháp cast `::geography` là PostgreSQL/PostGIS, không dùng nguyên xi trên MySQL. Cần chọn hàm spatial phù hợp MySQL và lưu ý axis order/SRID.

### Bài 26. SQLite mặc định hỗ trợ ST_DWithin PostGIS?

**Đáp án:** không. SQLite core không cung cấp đầy đủ hàm GIS này; cần SpatiaLite hoặc công cụ tương đương được cài và hỗ trợ.

### Bài 27. Hộp bao có thay ST_Intersects?

**Đáp án:** không khi cần quan hệ chính xác. Bounding box có thể cho **false positives**, đặc biệt polygon lõm hoặc có lỗ.

### Bài 28. Truy vấn nào cần pgRouting?

**Câu hỏi:** “5 cửa hàng gần nhất theo đường thẳng” và “tuyến đi xe nhanh nhất từ kho đến khách” dùng cùng `ST_Distance` được không?

**Đáp án:** không đủ. Bài toán tuyến đi xe cần mạng đường và thuật toán routing, có thể dùng pgRouting hoặc hệ thống dẫn đường phù hợp.

### Bài 29. Vì sao expression index có thể không được dùng?

**Đáp án:** biểu thức trong query có thể không khớp index, dữ liệu quá nhỏ, predicate không đủ chọn lọc hoặc planner đánh giá Seq Scan rẻ hơn. Cần xem `EXPLAIN` và thống kê.

### Bài 30. Chọn đúng loại hàm cho yêu cầu

| Yêu cầu | Gợi ý |
|---|---|
| Đọc WKT | `ST_GeomFromText` |
| Gắn đúng SRID cho tọa độ đã biết | `ST_SetSRID` |
| Biến đổi sang hệ khác | `ST_Transform` |
| Đo khoảng cách địa lý theo mét | `ST_Distance(geography,geography)` |
| Tìm trong bán kính | `ST_DWithin` |
| Kiểm tra giao nhau | `ST_Intersects` |
| Bao gồm điểm ranh giới | `ST_Covers` |
| Điểm phải ở nội thất polygon | `ST_Contains(Polygon,Point)` |
| Diện tích địa lý | `ST_Area(geography)` |
| Kiểm tra polygon | `ST_IsValid`/`ST_IsValidReason` |
| Xuất dữ liệu cho bản đồ | `ST_AsGeoJSON` |
| Hợp nhất nhiều vùng | `ST_Union` |

**Đáp án:** đúng theo cột gợi ý; luôn kiểm tra **đơn vị, SRID và signature của DBMS** trước khi sử dụng thật.

## 33. Quy trình giải quyết một yêu cầu địa lý thực tế

Giả sử nhóm phát triển cần xây API:

> “Cho tọa độ khách hàng và bán kính tối đa 2 km, trả các điểm phục vụ thuộc khu vực được phép, xếp theo khoảng cách và không đếm trùng.”

Một quy trình thiết kế có cơ sở:

1. **Xác định ngữ nghĩa bán kính:** đường thẳng địa lý theo mét hay thời gian di chuyển?
2. **Xác định hệ tọa độ nguồn:** thiết bị gửi lon/lat WGS84 hay hệ khác?
3. **Lưu kiểu có SRID rõ:** ví dụ PostGIS `geometry(Point,4326)`.
4. **Chuẩn hóa thứ tự tọa độ:** `ST_MakePoint(longitude,latitude)`.
5. **Chọn hàm đo:** `ST_DWithin(geom::geography,ref::geography,2000)` nếu bán kính địa lý mét.
6. **Đánh chỉ mục đúng biểu thức:** GiST trên `(geom::geography)` nếu workload phù hợp.
7. **Áp điều kiện vùng:** `ST_Covers(zone.geom,place.geom)` nếu tính cả ranh.
8. **Xác định xử lý vùng chồng lấn:** `EXISTS` để không nhân dòng hoặc gán vùng theo ưu tiên.
9. **Chọn thứ tự:** `ST_Distance` nếu cần thứ tự theo phép đo spheroid; cân nhắc KNN index và đặc tính phép đo.
10. **Giới hạn kết quả hợp lý:** pagination/limit, nhưng không thay đổi semantics của bộ lọc.
11. **Đo hiệu năng:** `EXPLAIN (ANALYZE,BUFFERS)` trên dữ liệu đại diện.
12. **Kiểm tra trường hợp biên:** SRID sai, tọa độ đảo, điểm đúng ranh, không có điểm, polygon lỗi, vùng giao nhau.
13. **Bảo vệ vị trí riêng tư:** quyền API, log, độ chính xác cần trả.
14. **Theo dõi dữ liệu và phiên bản vùng:** khi vùng phục vụ thay đổi, kết quả cũ có thể không còn đúng theo polygon mới.

### 33.1. Một query mẫu kết hợp bán kính và vùng

Ví dụ tìm địa điểm trong **1 km** từ tâm và nằm trong **ít nhất một vùng**, không đếm trùng:

```sql
WITH origin AS (
    SELECT
        ST_SetSRID(
            ST_MakePoint(106.7009, 10.7769),
            4326
        )::geography AS geog
)
SELECT
    p.place_id,
    p.place_name,
    ROUND(
        ST_Distance(
            p.geom::geography,
            o.geog
        )::numeric,
        1
    ) AS distance_meters
FROM lesson370_places AS p
CROSS JOIN origin AS o
WHERE ST_DWithin(
    p.geom::geography,
    o.geog,
    1000
)
  AND EXISTS (
      SELECT 1
      FROM lesson370_zones AS z
      WHERE ST_Covers(z.geom, p.geom)
  )
ORDER BY distance_meters, p.place_id;
```

Với dữ liệu mẫu, các địa điểm **1, 5, 6, 7** đều ở trong 1 km và thuộc ít nhất một vùng; mỗi điểm xuất hiện **một lần** vì `EXISTS` không nhân dòng.

### 33.2. Nếu thay EXISTS bằng JOIN trực tiếp?

Một JOIN với tất cả vùng có thể nhân địa điểm 7 thành **hai dòng** vì nó thuộc hai polygon. Điều đó có thể đúng nếu muốn xuất một dòng **cho mỗi quan hệ điểm-vùng**, nhưng không đúng nếu API hứa **mỗi địa điểm duy nhất một dòng**.

## 34. Bảng ghi nhớ cuối bài

| Nội dung | Ghi nhớ |
|---|---|
| Dữ liệu không gian | Point, LineString, Polygon và các loại Multi/Collection |
| WKT | Biểu diễn geometry dạng text, thường không tự nói SRID |
| GeoJSON | Định dạng giao tiếp bản đồ, phải kiểm tra hệ tọa độ/thứ tự |
| EPSG:4326 | Lon/lat theo độ trong cách dùng PostGIS |
| EPSG:32648 | Một phép chiếu UTM zone 48N theo mét cho vùng phù hợp |
| `ST_SetSRID` | Gắn nhãn SRID, **không** chuyển tọa độ |
| `ST_Transform` | Biến đổi tọa độ |
| `geometry` | Phép toán theo hệ tọa độ khai báo |
| `geography` | Nhiều phép đo địa lý theo mét |
| `ST_Distance` | Trả khoảng cách; **đơn vị theo kiểu dữ liệu/SRID** |
| `ST_DWithin` | Lọc trong bán kính, có thể tận dụng spatial index |
| `ST_Contains` | Điểm phải thuộc nội thất khi xét Polygon-Point |
| `ST_Covers` | Có thể gồm điểm trên ranh giới |
| `ST_Intersects` | Có phần giao bất kể chạm biên |
| `ST_Touches` | Quan hệ tiếp xúc biên theo topology |
| `ST_Buffer` | Tạo vùng đệm, tham số theo đơn vị phù hợp |
| `ST_Area` | Diện tích, cần kiểm tra đơn vị (độ²/m²) |
| `ST_Collect` | Gom geometry, chưa hợp nhất topology |
| `ST_Union` | Hợp nhất vùng theo topology |
| `ST_IsValid` | Kiểm tra topology của hình |
| `ST_MakeValid` | Sửa lỗi, có thể đổi kiểu geometry |
| `ST_Centroid` | Trọng tâm, có thể nằm ngoài polygon |
| `ST_PointOnSurface` | Điểm trên bề mặt hình |
| GiST index | Index không gian PostgreSQL/PostGIS |
| Bounding box `&&` | Lọc ứng viên, không luôn chính xác về topology |
| KNN `<->` | Gợi ý nearest neighbor index, chú ý mô hình khoảng cách |
| Spatial JOIN | JOIN bằng quan hệ vị trí, có thể nhân dòng khi vùng chồng lấn |
| MySQL | Spatial types, MBR, axis-order cần kiểm tra |
| SQL Server | `geography::Point(lat,lon,srid)` |
| Oracle | `SDO_GEOMETRY` và nhóm `SDO_*` |
| SQLite | SpatiaLite cho spatial SQL nâng cao |
| pgRouting | Đường đi trên mạng giao thông, không phải chỉ ST_Distance |
| Privacy | Tọa độ chính xác có thể là dữ liệu cá nhân |

## 35. Kết luận

Dữ liệu không gian đưa SQL từ bài toán **lọc theo giá trị thuộc tính** sang các câu hỏi về **khoảng cách, quan hệ vị trí, vùng và mạng lưới**. Khả năng này thường đến từ kiểu dữ liệu và nhóm hàm riêng của DBMS hoặc phần mở rộng GIS.

Để truy vấn đúng, hãy luôn nắm bốn tầng:

1. **Hình học:** điểm, đường, vùng, hình hợp lệ và ý nghĩa ranh giới.
2. **Hệ tọa độ:** SRID và thứ tự tọa độ đúng; `ST_SetSRID` không phải `ST_Transform`.
3. **Phép toán:** khoảng cách theo mét hay độ, chứa nội thất hay tính cả biên, bounding box hay quan hệ chính xác.
4. **Tối ưu và ứng dụng:** spatial index, KNN, spatial JOIN có thể nhân dòng, định dạng trao đổi và tính riêng tư.

**PostGIS** là ví dụ rất rõ cho việc mở rộng SQL bằng các nhóm hàm `ST_*` và chỉ mục GiST. Nhưng khi chuyển sang **MySQL Spatial, SQL Server geography, Oracle Spatial hay SQLite/SpatiaLite**, cần kiểm tra lại **cú pháp, đơn vị, thứ tự trục, SRID và cách engine sử dụng index**, thay vì giả định mọi hệ có hành vi như nhau.

Một truy vấn “tìm cửa hàng trong bán kính 1 km” chỉ thật sự đúng khi bạn có thể trả lời: **tọa độ thuộc hệ nào, 1 km được đo bằng mô hình nào, điểm trên ranh giới được tính ra sao, dữ liệu có được đánh chỉ mục phù hợp không và kết quả có đếm trùng thực thể không?**

## Tài liệu tham khảo

- [PostGIS — Introduction / Reference](https://postgis.net/docs/): kiểu `geometry`/`geography` và nhóm hàm không gian.
- [PostGIS — ST_SetSRID](https://postgis.net/docs/ST_SetSRID.html): gắn SRID mà không biến đổi tọa độ.
- [PostGIS — ST_Transform](https://postgis.net/docs/ST_Transform.html): chuyển hệ tọa độ.
- [PostGIS — ST_Distance](https://postgis.net/docs/ST_Distance.html): khoảng cách theo geometry/geography.
- [PostGIS — ST_DWithin](https://postgis.net/docs/ST_DWithin.html): lọc bán kính và tối ưu bằng chỉ mục.
- [PostGIS — ST_Contains](https://postgis.net/docs/ST_Contains.html): quan hệ chứa.
- [PostGIS — ST_Covers](https://postgis.net/docs/ST_Covers.html): quan hệ phủ gồm ranh giới.
- [PostGIS — ST_Intersects](https://postgis.net/docs/ST_Intersects.html): quan hệ giao.
- [PostGIS — ST_Buffer](https://postgis.net/docs/ST_Buffer.html): vùng đệm và đơn vị.
- [PostGIS — ST_AsGeoJSON](https://postgis.net/docs/ST_AsGeoJSON.html): xuất GeoJSON.
- [PostGIS — Spatial Indexes](https://postgis.net/docs/using_postgis_dbmanagement.html#build-indexes): cách dùng chỉ mục không gian.
- [PostgreSQL — GiST Indexes](https://www.postgresql.org/docs/current/gist.html): nền tảng index GiST.
- [MySQL — Spatial Data Types](https://dev.mysql.com/doc/refman/8.4/en/spatial-types.html): các kiểu hình học và SRID.
- [MySQL — Spatial Function Reference](https://dev.mysql.com/doc/refman/8.4/en/spatial-function-reference.html): nhóm hàm spatial.
- [Microsoft Learn — Spatial Data (SQL Server)](https://learn.microsoft.com/en-us/sql/relational-databases/spatial/spatial-data-sql-server): geometry, geography, method và index.
- [Oracle Database — Spatial and Graph](https://docs.oracle.com/en/database/oracle/oracle-database/19/spatl/): kiểu SDO và truy vấn không gian.
- [SpatiaLite](https://www.gaia-gis.it/fossil/libspatialite/index): extension GIS cho SQLite.
- [SQLite — R*Tree Module](https://www.sqlite.org/rtree.html): index hộp bao.
- [pgRouting](https://pgrouting.org/): routing trên mạng đường và cơ sở dữ liệu không gian.

