# SPATIAL index, bounding rectangle và điều kiện khai thác

MySQL lưu dữ liệu không gian bằng các kiểu hình học như POINT, LINESTRING, POLYGON và các kiểu tập hợp tương ứng. Khi cần tìm điểm nằm trong một vùng, vùng giao nhau hoặc đối tượng gần một khu vực, quét toàn bộ bảng và tính quan hệ hình học cho từng hàng có thể rất tốn kém. SPATIAL index giúp thu hẹp tập ứng viên bằng cấu trúc R-tree.

SPATIAL index không lập chỉ mục toàn bộ hình dạng chính xác của mỗi geometry. Nó lập chỉ mục minimum bounding rectangle (MBR), tức hình chữ nhật nhỏ nhất bao quanh geometry. Vì vậy, truy vấn thường có hai bước: dùng MBR để tìm các ứng viên nhanh, sau đó dùng hàm ST_* để kiểm tra quan hệ hình học chính xác nếu nghiệp vụ cần điều đó.

Trong module **DATABASE_MYSQL**, cần hiểu rõ điều kiện tạo index, SRID, thứ tự tham số của các hàm MBR và giới hạn của bounding rectangle. Bài học này hướng dẫn thiết kế cột không gian, tạo R-tree index, viết truy vấn có khả năng khai thác index, đọc EXPLAIN và tránh nhầm kết quả MBR với quan hệ hình học thực.

## 1. Geometry, SRID và dữ liệu không gian

MySQL hỗ trợ hệ kiểu geometry theo mô hình OpenGIS. Những kiểu thường gặp:

| Kiểu | Biểu diễn | Ví dụ sử dụng |
|---|---|---|
| GEOMETRY | Kiểu tổng quát | Cột nhận nhiều loại hình học |
| POINT | Một tọa độ | Vị trí cửa hàng, trạm, thiết bị |
| LINESTRING | Chuỗi điểm nối tiếp | Tuyến đường, đường ống |
| POLYGON | Vùng khép kín | Ranh giới khu vực, vùng giao hàng |
| MULTIPOINT | Tập hợp điểm | Nhiều vị trí |
| MULTILINESTRING | Tập hợp đường | Mạng tuyến |
| MULTIPOLYGON | Tập hợp vùng | Khu vực gồm nhiều mảnh |
| GEOMETRYCOLLECTION | Tập hợp nhiều loại geometry | Dữ liệu tổng hợp |

Ví dụ WKT (Well-Known Text):

```text
POINT(106.7009 10.7769)
LINESTRING(106.68 10.75, 106.70 10.78, 106.73 10.80)
POLYGON((106.65 10.70, 106.80 10.70, 106.80 10.85,
         106.65 10.85, 106.65 10.70))
```

WKT thuận tiện để tạo, đọc và trao đổi geometry. MySQL cũng hỗ trợ WKB (Well-Known Binary), GeoJSON và các hàm chuyển đổi tương ứng.

### 1.1. SRID xác định hệ quy chiếu

SRID (Spatial Reference System Identifier) xác định hệ quy chiếu không gian của geometry. SRID cho biết tọa độ thuộc hệ Cartesian hay geographic, trục tọa độ được định nghĩa thế nào và đơn vị của hệ quy chiếu là gì.

Một số ví dụ:

- SRID 0: hệ Cartesian mặc định của MySQL, không gắn với hệ quy chiếu địa lý cụ thể.
- SRID 4326: hệ tọa độ địa lý WGS 84, thường dùng cho longitude/latitude.
- Các SRID khác có thể mô tả hệ chiếu hoặc hệ quy chiếu địa phương.

Không được coi hai geometry có SRID khác nhau là cùng hệ tọa độ chỉ vì chúng chứa các con số giống nhau. Các phép toán không gian giữa geometry khác SRS thường trả lỗi khác SRID.

Kiểm tra SRID:

```sql
SELECT
    ST_SRID(ST_GeomFromText('POINT(10 20)', 0)) AS cartesian_srid,
    ST_SRID(
        ST_GeomFromText(
            'POINT(106.7009 10.7769)',
            4326,
            'axis-order=long-lat'
        )
    ) AS geographic_srid;
```

### 1.2. Thứ tự trục và longitude/latitude

Không nên mặc định WKT luôn dùng longitude trước latitude. Một số SRS có thứ tự trục được định nghĩa theo latitude/longitude. MySQL hỗ trợ tùy chọn axis-order để chỉ rõ cách đọc tọa độ khi tạo geometry từ WKT.

Với dữ liệu ứng dụng đang dùng thứ tự longitude, latitude, có thể chỉ rõ:

```sql
SET @point = ST_GeomFromText(
    'POINT(106.7009 10.7769)',
    4326,
    'axis-order=long-lat'
);
```

Trong ví dụ này, x là kinh độ và y là vĩ độ. Hãy thống nhất thứ tự trục giữa API, file GeoJSON/WKT, ứng dụng và MySQL. Đảo hai trục có thể tạo geometry hợp lệ về cú pháp nhưng nằm sai vị trí.

### 1.3. SRID-restricted column

Một cột geometry có thể khai báo SRID để giới hạn mọi giá trị lưu trong cột vào cùng hệ quy chiếu. Ví dụ:

```sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL,
    place_name VARCHAR(150) NOT NULL,
    location POINT NOT NULL SRID 4326,
    PRIMARY KEY (place_id)
) ENGINE = InnoDB;
```

Với khai báo SRID 4326, MySQL yêu cầu geometry ghi vào location có SRID tương ứng. Điều này giúp dữ liệu trong cột nhất quán và cho optimizer biết hệ quy chiếu cần dùng khi tính bounding box.

Đối với InnoDB trong MySQL 8.0, SRID restriction là điều kiện quan trọng để optimizer khai thác SPATIAL index. Index trên cột không có SRID attribute có thể vẫn được duy trì để tương thích, nhưng optimizer bỏ qua index đó.

## 2. Minimum Bounding Rectangle (MBR)

MBR là hình chữ nhật nhỏ nhất song song với các trục tọa độ bao quanh geometry. Trong mặt phẳng hai chiều, có thể xác định MBR bằng:

- minX: tọa độ X nhỏ nhất.
- maxX: tọa độ X lớn nhất.
- minY: tọa độ Y nhỏ nhất.
- maxY: tọa độ Y lớn nhất.

Bốn góc hình chữ nhật được tạo từ các cặp min/max này.

Ví dụ một polygon có hình lõm:

```text
POLYGON((
  0 0,
  0 8,
  3 8,
  3 3,
  7 3,
  7 8,
  10 8,
  10 0,
  0 0
))
```

MBR của polygon là hình chữ nhật từ (0, 0) đến (10, 8). Vùng rỗng ở giữa polygon vẫn nằm trong MBR. Do đó, một điểm có thể nằm trong MBR nhưng nằm ngoài polygon thật.

### 2.1. MBR của các loại geometry

- POINT có MBR suy biến thành chính điểm đó.
- LINESTRING có MBR bao quanh mọi điểm trên đường; nếu đường nằm ngang hoặc thẳng đứng, MBR có thể suy biến thành đường.
- POLYGON có MBR bao quanh toàn bộ vùng và các vòng biên của nó.
- MULTI* và GEOMETRYCOLLECTION có MBR bao quanh toàn bộ thành phần.

MBR thường rộng hơn hình dạng thực. Với polygon lõm, polygon có lỗ hoặc đường cong phức tạp, khoảng trống giữa geometry và MBR có thể lớn.

### 2.2. Vì sao MBR tạo false positive?

Giả sử một polygon có hình chữ U. MBR của nó là hình chữ nhật bao trùm cả phần lõm ở giữa. Một điểm nằm trong phần lõm có thể thỏa MBRContains nhưng không thỏa ST_Contains.

Vì vậy:

- MBR predicate trả lời quan hệ giữa các bounding rectangle.
- ST_* predicate trả lời quan hệ giữa hình dạng geometry thực.
- MBR là bộ lọc ứng viên nhanh, không thay thế phép kiểm tra hình học chính xác.

Quy trình thường có dạng: geometry được lưu trong bảng, MBR được đưa vào R-tree, truy vấn tìm các MBR có khả năng thỏa điều kiện, rồi kiểm tra tập ứng viên bằng ST_* nếu cần quan hệ chính xác.

## 3. SPATIAL index dùng R-tree

SPATIAL index của MySQL dùng cấu trúc R-tree. Khác B-tree thường tổ chức khóa theo thứ tự một chiều, R-tree nhóm các vùng không gian bằng bounding rectangle để tìm những vùng có khả năng giao nhau hoặc chứa một vị trí.

MySQL xây dựng SPATIAL index trên MBR của geometry. Với InnoDB và MyISAM, R-tree hỗ trợ những truy vấn không gian phổ biến như:

- Tìm các đối tượng chứa một điểm.
- Tìm các đối tượng nằm trong một vùng chữ nhật.
- Tìm các đối tượng có bounding rectangle giao với một vùng.

R-tree giúp giảm số geometry cần kiểm tra. Sau bước lọc, MySQL hoặc ứng dụng có thể cần đánh giá chính xác hình dạng của các ứng viên.

### 3.1. So sánh B-tree và R-tree

| Đặc điểm | B-tree | R-tree trong SPATIAL index |
|---|---|---|
| Dữ liệu chính | Giá trị có thứ tự | Vùng/bounding rectangle |
| Truy vấn phù hợp | =, range, sort, prefix | Tìm kiếm vùng và quan hệ MBR |
| Cấu trúc | Các khóa theo thứ tự | Các rectangle phân cấp |
| Geometry | B-tree trên geometry có giới hạn sử dụng | Spatial index chuyên cho MBR |
| Tìm giao vùng | Không phải mục tiêu chính | Mục tiêu chính |

Một B-tree thông thường trên giá trị geometry có thể hữu ích cho exact-value lookup trong một số trường hợp, nhưng không thay thế R-tree cho spatial range search.

## 4. Điều kiện tạo SPATIAL index

MySQL có một số điều kiện quan trọng:

1. SPATIAL index chỉ được hỗ trợ trên bảng InnoDB và MyISAM.
2. Cột được index phải là kiểu dữ liệu không gian.
3. Cột geometry phải khai báo NOT NULL.
4. Một SPATIAL index chỉ áp dụng cho một cột không gian.
5. Không khai báo prefix length cho cột trong SPATIAL index.
6. Để optimizer khai thác index trong MySQL 8.0, cột phải được SRID-restricted: khai báo SRID rõ ràng và dữ liệu có cùng SRID.

Ví dụ tạo bảng và index:

```sql
CREATE TABLE places (
    place_id BIGINT UNSIGNED NOT NULL,
    place_name VARCHAR(150) NOT NULL,
    location POINT NOT NULL SRID 4326,
    PRIMARY KEY (place_id),
    SPATIAL INDEX spx_places_location (location)
) ENGINE = InnoDB;
```

Có thể thêm index sau khi tạo bảng:

```sql
ALTER TABLE places
ADD SPATIAL INDEX spx_places_location (location);
```

Hoặc:

```sql
CREATE SPATIAL INDEX spx_places_location
ON places (location);
```

### 4.1. Vì sao NOT NULL bắt buộc?

SPATIAL index của MySQL yêu cầu cột geometry được index là NOT NULL. Nếu vị trí chưa biết hoặc chưa có, cần chọn một mô hình dữ liệu phù hợp:

- Chưa tạo hàng location cho đối tượng chưa có vị trí.
- Dùng trạng thái nghiệp vụ riêng để biểu diễn chưa xác định.
- Dùng một bảng phụ chứa geometry chỉ khi đã có tọa độ.
- Không dùng tọa độ giả như POINT(0 0) để thay cho NULL, vì nó có thể bị hiểu là một vị trí thật.

Nếu bắt buộc phải lưu NULL trong cột geometry, cột đó không đáp ứng điều kiện tạo SPATIAL index. Hãy xác định rõ chính sách dữ liệu trước khi thiết kế schema.

### 4.2. Vì sao SRID-restricted quan trọng?

Optimizer cần biết hệ quy chiếu của cột để tính bounding box phù hợp. Nếu một cột chứa lẫn geometry Cartesian và geographic, cùng một cặp số có thể mang ý nghĩa khác nhau và phép tính bounding box không thể được diễn giải nhất quán.

Với cột có SRID attribute:

```sql
location POINT NOT NULL SRID 4326
```

MySQL biết tất cả giá trị location thuộc SRID 4326. Với cột không khai báo SRID, SPATIAL index vẫn có thể được duy trì trong một số trường hợp tương thích, nhưng optimizer không dùng nó để tối ưu truy vấn.

Kiểm tra SRID đang lưu:

```sql
SELECT DISTINCT ST_SRID(location) AS srid
FROM places;
```

Nếu có nhiều SRID, cần chuẩn hóa hoặc chuyển đổi dữ liệu về một hệ quy chiếu trước khi định nghĩa lại cột và tạo lại index. Không chỉ thay metadata SRID nếu tọa độ chưa thực sự được chuyển đổi.

## 5. Thêm dữ liệu geometry đúng SRID

Có thể tạo geometry bằng các hàm từ WKT. Ví dụ thêm điểm vào bảng:

```sql
INSERT INTO places (
    place_id,
    place_name,
    location
)
VALUES (
    1,
    'Central Store',
    ST_GeomFromText(
        'POINT(106.7009 10.7769)',
        4326,
        'axis-order=long-lat'
    )
);
```

Với cột SRID 4326, geometry truyền vào phải mang SRID tương thích. Nếu đưa geometry SRID 0 vào, MySQL sẽ từ chối do SRID không khớp.

Đọc dữ liệu dạng WKT:

```sql
SELECT
    place_id,
    place_name,
    ST_AsText(location) AS location_wkt,
    ST_SRID(location) AS location_srid
FROM places;
```

### 5.1. Kiểm tra geometry trước khi index

Trước khi nạp dữ liệu lớn:

- Kiểm tra cú pháp WKT/WKB/GeoJSON.
- Kiểm tra SRID và thứ tự trục.
- Kiểm tra longitude/latitude có nằm trong miền hợp lệ của SRS.
- Kiểm tra polygon có khép kín và hợp lệ.
- Kiểm tra các geometry có cùng SRID.
- Kiểm tra dữ liệu NULL nếu cột sẽ được index.

Có thể dùng các hàm như ST_IsValid(), ST_GeometryType(), ST_SRID() và ST_AsText() để kiểm tra.

Ví dụ:

```sql
SELECT
    place_id,
    ST_GeometryType(location) AS geometry_type,
    ST_SRID(location) AS srid,
    ST_IsValid(location) AS is_valid
FROM places;
```

ST_IsValid kiểm tra tính hợp lệ hình học theo quy tắc của MySQL. Dữ liệu hợp lệ về cú pháp chưa chắc đã hợp lệ về topology.

## 6. Bounding rectangle và các hàm MBR

MySQL cung cấp các hàm quan hệ MBR để so sánh bounding rectangle của hai geometry:

| Hàm | Ý nghĩa |
|---|---|
| MBRContains(g1, g2) | MBR của g1 chứa MBR của g2 |
| MBRWithin(g1, g2) | MBR của g1 nằm trong MBR của g2 |
| MBRIntersects(g1, g2) | Hai MBR có giao nhau |
| MBROverlaps(g1, g2) | Hai MBR overlap theo quy tắc quan hệ |
| MBRCovers(g1, g2) | MBR của g1 bao phủ MBR của g2, kể cả biên |
| MBRCoveredBy(g1, g2) | MBR của g1 được MBR của g2 bao phủ |
| MBREquals(g1, g2) | Hai MBR bằng nhau |
| MBRTouches(g1, g2) | Hai MBR tiếp xúc |
| MBRDisjoint(g1, g2) | Hai MBR rời nhau |

Các hàm MBR trả 1 hoặc 0 cho quan hệ giữa bounding rectangle. Nếu đối số là SQL NULL hoặc geometry rỗng, kết quả có thể là NULL. Geometry không cùng SRS có thể gây lỗi.

### 6.1. MBRContains và MBRWithin

Hai hàm biểu diễn quan hệ ngược nhau:

```sql
SELECT
    MBRContains(@region, @point) AS region_contains_point,
    MBRWithin(@point, @region) AS point_within_region;
```

Cả hai đều có thể đúng khi điểm nằm trong MBR của vùng.

Thứ tự tham số có ý nghĩa. Khi truy vấn bảng có cột location được index, một mẫu thường dùng là geometry vùng truy vấn đứng trước, cột geometry được index đứng sau:

```sql
WHERE MBRContains(@search_window, location)
```

Đây là hình thức được MySQL minh họa cho optimizer sử dụng spatial index.

### 6.2. MBRIntersects cho truy vấn vùng giao nhau

Nếu cần tìm các geometry có MBR giao với vùng tìm kiếm:

```sql
SELECT place_id
FROM places
WHERE MBRIntersects(@search_window, location);
```

MBRIntersects chỉ xác nhận hai bounding rectangle giao nhau. Với geometry phức tạp, nó có thể trả các ứng viên mà hình dạng thật không giao nhau. Cần kiểm tra execution plan và thêm exact predicate nếu nghiệp vụ yêu cầu quan hệ chính xác.

Không nên suy ra rằng mọi hàm MBR đều được optimizer khai thác như nhau. MySQL mô tả rõ các mẫu MBRContains() và MBRWithin() cho spatial index; hãy dùng EXPLAIN để xác nhận predicate và phiên bản cụ thể.

## 7. Truy vấn khai thác SPATIAL index

Ví dụ bảng places đã có SPATIAL index trên location.

Tạo một cửa sổ hình chữ nhật tìm kiếm:

```sql
SET @search_window = ST_GeomFromText(
    'POLYGON((
        106.65 10.70,
        106.80 10.70,
        106.80 10.85,
        106.65 10.85,
        106.65 10.70
    ))',
    4326,
    'axis-order=long-lat'
);
```

Tìm các điểm nằm trong bounding rectangle:

```sql
SELECT
    place_id,
    place_name
FROM places
WHERE MBRContains(@search_window, location);
```

Với cột location được SRID-restricted và SPATIAL index hợp lệ, optimizer có thể dùng R-tree để thu hẹp ứng viên. Kết quả của MBRContains là quan hệ MBR; trong ví dụ query window là rectangle, MBR của nó trùng với hình chữ nhật tìm kiếm.

### 7.1. Kiểm tra bằng EXPLAIN

```sql
EXPLAIN
SELECT
    place_id,
    place_name
FROM places
WHERE MBRContains(@search_window, location);
```

Các trường cần chú ý:

- possible_keys: spatial index có nằm trong danh sách index khả dụng không.
- key: index optimizer thực sự chọn.
- type: access type, ví dụ range nếu truy vấn dùng spatial index.
- rows: số hàng ước lượng cần đọc.
- Extra: điều kiện lọc bổ sung.

Không chỉ nhìn thấy index tồn tại trong SHOW INDEX. Phải kiểm tra key trong EXPLAIN và so sánh với truy vấn khi bỏ index hoặc khi thay đổi điều kiện.

### 7.2. MBR filter kết hợp exact geometry predicate

Với polygon lõm hoặc có lỗ, MBR có thể chứa nhiều điểm nằm ngoài polygon thật. Trong trường hợp đó, có thể dùng MBR làm bước lọc nhanh và ST_Contains làm bước kiểm tra chính xác:

```sql
SELECT
    place_id,
    place_name
FROM places
WHERE MBRContains(@search_window, location)
  AND ST_Contains(@search_window, location);
```

Trong ví dụ này:

1. MBRContains tìm các điểm có khả năng nằm trong vùng.
2. ST_Contains kiểm tra điểm có thực sự nằm trong polygon hay không.
3. Các false positive do phần trống trong MBR bị loại.

ST_Contains áp dụng semantics hình học chính xác và có quy tắc riêng đối với điểm nằm trên biên polygon. Nếu nghiệp vụ muốn tính cả điểm trên biên, hãy chọn predicate chính xác phù hợp, chẳng hạn ST_Intersects, và thiết kế bước MBR prefilter không loại mất các điểm biên cần giữ.

### 7.3. Tìm các vùng có thể giao với vùng yêu cầu

Giả sử bảng districts lưu polygon ranh giới:

```sql
CREATE TABLE districts (
    district_id BIGINT UNSIGNED NOT NULL,
    district_name VARCHAR(150) NOT NULL,
    boundary POLYGON NOT NULL SRID 4326,
    PRIMARY KEY (district_id),
    SPATIAL INDEX spx_district_boundary (boundary)
) ENGINE = InnoDB;
```

Tìm các ranh giới có MBR giao với vùng truy vấn:

```sql
SELECT district_id, district_name
FROM districts
WHERE MBRIntersects(@search_window, boundary);
```

Nếu cần xác nhận polygon thực sự giao nhau, bổ sung ST_Intersects:

```sql
SELECT district_id, district_name
FROM districts
WHERE MBRIntersects(@search_window, boundary)
  AND ST_Intersects(boundary, @search_window);
```

Hãy kiểm tra EXPLAIN để xác nhận MBR predicate cụ thể được optimizer khai thác. Nếu query plan không chọn spatial index, xem lại SRID restriction, argument order, kiểu geometry, độ chọn lọc của vùng và số lượng hàng.

## 8. Bounding rectangle trong hệ tọa độ địa lý

Với SRID 4326, tọa độ là longitude/latitude theo đơn vị độ. Một MBR địa lý không giống hình chữ nhật trên bản đồ phẳng trong mọi tình huống.

Một số điểm cần lưu ý:

- Longitude có miền giá trị khoảng (-180, 180].
- Latitude có miền giá trị [-90, 90].
- Độ dài một độ longitude thay đổi theo latitude.
- Gần cực, cách diễn giải bounding box cần chú ý.
- Vùng tìm kiếm cắt qua kinh tuyến 180 độ (antimeridian) có thể cần chia thành nhiều vùng truy vấn.
- Không dùng phép tính Euclidean trên longitude/latitude để thay thế khoảng cách địa lý.

Với hệ Cartesian hoặc hệ chiếu phẳng, MBR có thể được diễn giải theo đơn vị của hệ quy chiếu đó. Với hệ geographic, MySQL thực hiện bounding-box computation theo SRS và quy tắc geographic.

### 8.1. Không nhầm bounding rectangle với bán kính

Một vùng tìm kiếm hình chữ nhật và một vùng tìm kiếm theo bán kính là hai yêu cầu khác nhau.

- MBRContains có thể lọc các điểm trong bounding rectangle.
- ST_Distance_Sphere hoặc hàm khoảng cách phù hợp có thể kiểm tra khoảng cách theo mét.
- R-tree không tự biến bán kính thành vòng tròn chính xác.

Mẫu thiết kế thường là tạo bounding box bao quanh vùng bán kính để thu hẹp ứng viên, sau đó tính khoảng cách chính xác cho các ứng viên. Việc tính bounding box phải xét latitude, longitude, đơn vị và trường hợp gần cực/antimeridian.

## 9. Vì sao spatial index có thể không được dùng?

Các nguyên nhân thường gặp:

1. Cột geometry không khai báo NOT NULL.
2. Cột không có SRID attribute nên không SRID-restricted.
3. Dữ liệu có SRID không thống nhất hoặc truy vấn truyền geometry khác SRID.
4. Bảng dùng storage engine không hỗ trợ SPATIAL index.
5. Câu WHERE không dùng predicate MBR phù hợp với optimizer.
6. Đặt sai thứ tự đối số trong predicate MBR được dùng để truy vấn.
7. Cột geometry bị bọc trong biểu thức làm optimizer không nhận diện được access path.
8. Vùng tìm kiếm quá rộng, index không chọn lọc và full scan có thể rẻ hơn.
9. Dữ liệu ít hoặc thống kê/ước lượng chi phí khiến optimizer chọn phương án khác.
10. Index chưa được tạo hoặc bị drop trong quá trình migration.

### 9.1. Kiểm tra metadata cột

```sql
SHOW CREATE TABLE places;
```

Xác nhận cột có dạng:

```sql
location POINT NOT NULL SRID 4326
```

Kiểm tra SRID thực tế:

```sql
SELECT DISTINCT ST_SRID(location)
FROM places;
```

Kiểm tra index:

```sql
SHOW INDEX FROM places;
```

### 9.2. Kiểm tra kế hoạch thực thi

```sql
EXPLAIN FORMAT = JSON
SELECT place_id
FROM places
WHERE MBRContains(@search_window, location);
```

So sánh với truy vấn không có spatial predicate hoặc có IGNORE INDEX trong môi trường thử nghiệm để hiểu tác động. Không áp dụng hint trên production nếu chưa đo lường và đánh giá.

## 10. Bảo trì SPATIAL index

SPATIAL index được cập nhật khi INSERT, UPDATE hoặc DELETE geometry. Nếu cột location thay đổi, R-tree phải cập nhật MBR tương ứng.

Với dữ liệu lớn:

- Dự trù thời gian tạo index.
- Theo dõi CPU, I/O và dung lượng khi rebuild.
- Nạp dữ liệu theo batch có kiểm soát nếu phù hợp.
- Kiểm tra SRID và tính hợp lệ geometry trước khi nạp.
- Dùng EXPLAIN sau migration.
- Kiểm tra chất lượng kết quả bằng bộ truy vấn chuẩn.

Có thể xóa index khi không còn workload cần dùng:

```sql
ALTER TABLE places
DROP INDEX spx_places_location;
```

Hoặc:

```sql
DROP INDEX spx_places_location
ON places;
```

Không nên drop spatial index chỉ vì một truy vấn không dùng nó. Trước tiên kiểm tra điều kiện SRID, NOT NULL, predicate và độ chọn lọc.

## 11. SPATIAL index và truy vấn kết hợp điều kiện thuộc tính

Nhiều truy vấn thực tế cần lọc theo cả thuộc tính thường và vị trí. Ví dụ tìm cửa hàng đang hoạt động trong một vùng:

```sql
SELECT
    place_id,
    place_name
FROM places
WHERE MBRContains(@search_window, location)
  AND status = 'ACTIVE';
```

Spatial index thu hẹp ứng viên theo vùng. Điều kiện status lọc thêm theo thuộc tính. SPATIAL index không phải composite index nhiều cột như B-tree; nó chỉ index một cột geometry. Nếu status có selectivity cao, có thể cần đánh giá kế hoạch truy vấn và các index B-tree riêng.

Đừng giả định MySQL sẽ kết hợp mọi index theo cách mong muốn. Dùng EXPLAIN để xem access path và số hàng ước lượng. Với truy vấn rất chọn lọc theo status, optimizer có thể chọn index thuộc tính trước hoặc phương án khác tùy dữ liệu.

## 12. Những giới hạn và hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| SPATIAL index lưu hình dạng polygon chính xác | Index dựa trên MBR | Dùng ST_* để kiểm tra hình dạng thật |
| Có SPATIAL index là mọi truy vấn địa lý đều nhanh | Chỉ predicate phù hợp và cột đúng điều kiện mới có thể dùng | Đọc EXPLAIN |
| Chỉ cần NOT NULL | Optimizer MySQL 8.0 còn cần SRID restriction | Khai báo SRID attribute |
| Geometry khác SRID vẫn so sánh bình thường | Phép toán có thể lỗi do khác SRS | Chuyển đổi về cùng SRS |
| MBRContains tương đương ST_Contains | Một bên so MBR, một bên so hình dạng | Dùng MBR làm prefilter, ST_* làm exact filter |
| MBR false positive là lỗi dữ liệu | Đó là hệ quả bình thường của bounding rectangle | Lọc chính xác ở bước sau |
| Mọi storage engine hỗ trợ SPATIAL index | InnoDB và MyISAM hỗ trợ; engine khác có giới hạn | Kiểm tra engine |
| Có thể index nhiều geometry trong một SPATIAL index | SPATIAL index chỉ áp dụng một cột không gian | Tạo index riêng nếu cần |
| Có thể dùng prefix length | Prefix length bị cấm cho SPATIAL index | Khai báo index trên cột geometry |
| Longitude luôn là trục đầu tiên | Thứ tự trục phụ thuộc SRS và options | Dùng axis-order phù hợp |
| MBR địa lý luôn là rectangle phẳng đơn giản | Geographic SRS có quy tắc bounding box riêng | Xét SRID, antimeridian và vùng cực |
| Khoảng cách mét bằng MBRContains | MBR kiểm tra vùng, không tính radius | Dùng hàm distance cho bước chính xác |

## 13. Quy trình thiết kế truy vấn không gian

1. Xác định loại geometry: POINT, LINESTRING, POLYGON hay tập hợp.
2. Chọn SRS/SRID phù hợp với dữ liệu và phép đo.
3. Chuẩn hóa thứ tự trục và đơn vị tọa độ.
4. Khai báo cột geometry NOT NULL nếu cần SPATIAL index.
5. Khai báo SRID attribute để optimizer sử dụng index.
6. Tạo SPATIAL index trên một cột geometry.
7. Dùng MBRContains hoặc MBRWithin cho truy vấn vùng/điểm phù hợp.
8. Dùng ST_* nếu cần kiểm tra topology chính xác.
9. Đọc EXPLAIN và kiểm tra key được chọn.
10. Benchmark trên dữ liệu đại diện và vùng tìm kiếm thực tế.
11. Kiểm tra các trường hợp biên, SRID sai và geometry không hợp lệ.
12. Theo dõi chi phí ghi và bảo trì index.

## 14. Checklist trước khi đưa vào production

**Schema và dữ liệu:**

- Cột geometry có đúng kiểu dữ liệu.
- Cột được index khai báo NOT NULL.
- SRID attribute được khai báo rõ.
- Tất cả geometry có cùng SRID.
- Thứ tự longitude/latitude hoặc axis-order được thống nhất.
- Polygon và geometry collection được kiểm tra validity.
- Không dùng tọa độ giả để thay NULL.

**Index và truy vấn:**

- SPATIAL index chỉ đặt trên một cột geometry.
- Không dùng prefix length.
- Predicate MBR có đúng thứ tự đối số.
- Exact predicate ST_* được thêm khi cần.
- EXPLAIN cho thấy optimizer có thể chọn spatial index.
- Đã thử vùng nhỏ, vùng lớn, biên vùng và geometry phức tạp.
- Đã so sánh MBR result với exact geometry result.

**Vận hành:**

- Đã ước lượng thời gian tạo/rebuild index.
- Đã đo CPU, I/O, dung lượng và write overhead.
- Có quy trình chuyển đổi SRID nếu dữ liệu thay đổi.
- Có bộ truy vấn hồi quy cho migration.
- Có giám sát latency và số hàng ứng viên.
- Có phương án xử lý dữ liệu lỗi và geometry ngoài phạm vi.

## 15. Ghi nhớ

- SPATIAL index của MySQL dùng R-tree và lập chỉ mục MBR của geometry.
- MBR là hình chữ nhật nhỏ nhất bao quanh geometry, không phải hình dạng chính xác.
- MBR predicate có thể tạo false positive, đặc biệt với polygon lõm, polygon có lỗ hoặc geometry phức tạp.
- InnoDB và MyISAM hỗ trợ SPATIAL index.
- Cột được index phải là geometry và NOT NULL.
- Một SPATIAL index chỉ áp dụng cho một cột geometry; không dùng prefix length.
- Để optimizer khai thác SPATIAL index trong MySQL 8.0, cột phải SRID-restricted.
- SRID attribute và dữ liệu thực tế phải thống nhất.
- MBRContains/MBRWithin là các mẫu truy vấn quan trọng để optimizer xem xét spatial index.
- Dùng EXPLAIN để xác nhận index thực sự được chọn.
- Dùng ST_Contains, ST_Within, ST_Intersects và các hàm ST_* tương ứng khi cần quan hệ hình học chính xác.
- Không nhầm MBR với phép tính khoảng cách hoặc bán kính.
- Với SRID địa lý, cần chú ý longitude/latitude, thứ tự trục, đơn vị độ và vùng qua antimeridian.
- Spatial index làm tăng chi phí ghi và dung lượng, nên cần benchmark cả đọc lẫn ghi.

SPATIAL index giúp thu hẹp tập geometry cần xét bằng R-tree và bounding rectangle. Thiết kế đúng phải thống nhất SRID, khai báo NOT NULL, viết predicate MBR phù hợp và xác nhận bằng EXPLAIN. Khi nghiệp vụ yêu cầu chính xác theo hình dạng, hãy dùng MBR làm bước lọc ứng viên rồi kiểm tra bằng ST_* để loại false positive.

## Tài liệu tham khảo

- MySQL 8.0 Reference Manual — Creating Spatial Indexes: https://dev.mysql.com/doc/refman/8.0/en/creating-spatial-indexes.html
- MySQL 8.0 Reference Manual — SPATIAL Index Optimization: https://dev.mysql.com/doc/refman/8.0/en/spatial-index-optimization.html
- MySQL 8.0 Reference Manual — Using Spatial Indexes: https://dev.mysql.com/doc/refman/8.0/en/using-spatial-indexes.html
- MySQL 8.0 Reference Manual — Optimizing Spatial Analysis: https://dev.mysql.com/doc/refman/8.0/en/optimizing-spatial-analysis.html
- MySQL 8.0 Reference Manual — Spatial Relation Functions Using MBRs: https://dev.mysql.com/doc/refman/8.0/en/spatial-relation-functions-mbr.html
- MySQL 8.0 Reference Manual — Spatial Relation Functions Using Object Shapes: https://dev.mysql.com/doc/refman/8.0/en/spatial-relation-functions-object-shapes.html
- MySQL 8.0 Reference Manual — Creating Spatial Columns: https://dev.mysql.com/doc/refman/8.0/en/creating-spatial-columns.html

