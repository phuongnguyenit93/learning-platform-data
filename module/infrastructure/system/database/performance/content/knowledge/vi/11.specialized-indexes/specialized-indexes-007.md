# Chỉ mục cho JSON, dữ liệu không gian và yêu cầu toán tử phù hợp

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Phân biệt chỉ mục tổng quát với chỉ mục chuyên biệt và giải thích vì sao toán tử truy vấn phải tương thích với access method.
- Chọn chỉ mục phù hợp cho JSON khi truy vấn tìm theo khóa, giá trị scalar, cấu trúc lồng nhau hoặc phép containment.
- Phân biệt GIN, GiST, B-tree và chỉ mục biểu thức trong các trường hợp JSON và dữ liệu không gian.
- Hiểu cách chỉ mục không gian lọc ứng viên bằng bounding box trước khi kiểm tra hình học chính xác.
- Đọc execution plan và đo lợi ích, chi phí ghi, dung lượng cũng như độ chính xác của kết quả sau khi tạo chỉ mục.

## 1. Vì sao cần chỉ mục chuyên biệt?

Chỉ mục B-tree thông thường rất hiệu quả cho các phép so sánh có thứ tự như bằng, nhỏ hơn, lớn hơn, khoảng giá trị và sắp xếp theo khóa. Tuy nhiên, dữ liệu JSON và dữ liệu không gian có cấu trúc truy vấn khác với một giá trị scalar đơn giản.

Một cột JSON có thể chứa object, array, scalar và cấu trúc lồng nhau. Ứng dụng có thể tìm một khóa, kiểm tra một object có chứa các cặp khóa/giá trị hay không, hoặc kiểm tra một phần tử có xuất hiện trong array. Một cột hình học có thể chứa điểm, đường hoặc đa giác; truy vấn có thể hỏi hai hình có giao nhau, một điểm có nằm trong vùng hay hình nào gần một vị trí nhất.

Chỉ mục chuyên biệt được thiết kế để hỗ trợ những phép toán này. Ví dụ:

- **B-tree** hỗ trợ tốt so sánh và sắp thứ tự trên giá trị scalar được trích xuất từ JSON.
- **GIN** trong PostgreSQL có thể lập chỉ mục các thành phần của JSONB để hỗ trợ một số phép containment và kiểm tra khóa.
- **GiST** trong PostgreSQL/PostGIS hỗ trợ các chiến lược truy cập không gian dựa trên bounding box và các toán tử hình học.
- **R-tree** là cấu trúc cây thường dùng cho chỉ mục không gian trong một số hệ quản trị.
- Các hệ quản trị khác có thể dùng generated column, computed column, spatial index hoặc cơ chế nội bộ riêng.

Không có một chỉ mục duy nhất tối ưu cho mọi toán tử JSON hoặc mọi phép toán không gian. Cần xác định biểu thức truy vấn, toán tử, kiểu dữ liệu và access method mà hệ quản trị hỗ trợ.

## 2. Bắt đầu từ toán tử truy vấn

Chỉ mục chỉ giúp tăng tốc khi truy vấn sử dụng biểu thức và toán tử tương thích với chỉ mục. Hai truy vấn cùng đọc một cột JSON nhưng dùng hai phép toán khác nhau có thể cần hai loại chỉ mục khác nhau.

| Kiểu truy vấn | Ví dụ | Hướng chỉ mục thường xem xét |
| --- | --- | --- |
| So sánh một giá trị JSON scalar | `payload->>'status' = 'PAID'` | B-tree trên biểu thức hoặc cột sinh |
| Kiểm tra JSON chứa cấu trúc | `payload @> '{"status":"PAID"}'` | GIN với operator class phù hợp trong PostgreSQL |
| Kiểm tra khóa tồn tại | `payload ? 'customerId'` | GIN `jsonb_ops` trong PostgreSQL |
| Kiểm tra hình học giao nhau | `ST_Intersects(geom, area)` | Spatial index như GiST/PostGIS hoặc spatial index của hệ quản trị |
| Tìm đối tượng trong vùng | `ST_Within(geom, area)` hoặc phép toán tương đương | Spatial index nếu toán tử có hỗ trợ lọc bounding box |
| Tìm đối tượng gần nhất | `ORDER BY geom <-> point LIMIT n` trong PostGIS | GiST với toán tử KNN phù hợp và phiên bản hỗ trợ |

Đây là định hướng ban đầu. Khả năng sử dụng chỉ mục còn phụ thuộc phiên bản, kiểu cột, operator class, SRID, biểu thức và cách viết truy vấn. Luôn kiểm tra execution plan.

## 3. Chỉ mục cho JSON: cấu trúc và các kiểu truy vấn

JSON phù hợp khi dữ liệu có cấu trúc linh hoạt hoặc thuộc tính thay đổi theo loại bản ghi. Nhưng nếu ứng dụng thường lọc hoặc nối theo một số trường ổn định, cần quyết định trường nào nên được trích xuất và lập chỉ mục.

Ví dụ bảng sự kiện:

```sql
CREATE TABLE events (
    event_id BIGINT PRIMARY KEY,
    occurred_at TIMESTAMP NOT NULL,
    payload JSONB NOT NULL
);
```

Một payload có thể có dạng:

```json
{
  "type": "payment",
  "status": "completed",
  "customerId": 4201,
  "attributes": {
    "channel": "mobile",
    "currency": "VND"
  },
  "tags": ["priority", "online"]
}
```

Trước khi tạo chỉ mục, hãy phân loại cách ứng dụng sử dụng dữ liệu:

- Trường nào được lọc trong phần lớn truy vấn?
- Trường nào cần so sánh theo khoảng hoặc sắp xếp?
- Có truy vấn tìm một cấu trúc con hay chỉ tìm một scalar?
- Array được kiểm tra sự tồn tại phần tử hay cần thứ tự và vị trí?
- Thuộc tính nào ổn định đủ để trở thành cột quan hệ?
- Payload lớn đến mức chỉ mục toàn bộ JSON sẽ chiếm nhiều bộ nhớ và chi phí ghi không?

## 4. PostgreSQL JSONB: GIN và operator class

PostgreSQL cung cấp kiểu `jsonb` cùng các toán tử để truy vấn object và array. GIN thường phù hợp khi truy vấn cần tìm thành phần hoặc cấu trúc con trong JSONB.

### GIN với jsonb_ops

`jsonb_ops` là operator class GIN mặc định cho JSONB. Nó lập chỉ mục các khóa và giá trị theo cách hỗ trợ nhiều toán tử, bao gồm:

- `?` kiểm tra khóa hoặc phần tử cấp cao nhất có tồn tại.
- `?|` kiểm tra có ít nhất một khóa/phần tử trong danh sách hay không.
- `?&` kiểm tra tất cả khóa/phần tử trong danh sách có tồn tại hay không.
- `@>` kiểm tra JSONB bên trái có chứa cấu trúc JSONB bên phải hay không.
- Các toán tử JSONPath được hỗ trợ theo phiên bản PostgreSQL.

Tạo chỉ mục:

```sql
CREATE INDEX ix_events_payload_gin
    ON events USING GIN (payload);
```

Truy vấn ví dụ:

```sql
SELECT event_id, occurred_at
FROM events
WHERE payload ? 'customerId';

SELECT event_id
FROM events
WHERE payload @> '{"type":"payment","status":"completed"}'::jsonb;
```

Chỉ mục GIN có thể tìm tập ứng viên nhanh hơn so với quét toàn bộ JSONB, nhưng không có nghĩa mọi biểu thức truy cập JSON đều được tăng tốc. Hãy kiểm tra toán tử được dùng có nằm trong tập toán tử mà operator class hỗ trợ hay không.

### GIN với jsonb_path_ops

`jsonb_path_ops` là lựa chọn khác khi workload chủ yếu dùng containment `@>` và các toán tử JSONPath được hỗ trợ. Nó tạo cách biểu diễn chỉ mục khác, thường nhỏ hơn và có tính chọn lọc tốt hơn cho một số workload containment.

```sql
CREATE INDEX ix_events_payload_path_gin
    ON events USING GIN (payload jsonb_path_ops);

SELECT event_id
FROM events
WHERE payload @> '{"attributes":{"channel":"mobile"}}'::jsonb;
```

`jsonb_path_ops` không hỗ trợ các toán tử kiểm tra sự tồn tại khóa như `?`, `?|` và `?&`. Nếu truy vấn cần các phép toán đó, hãy chọn `jsonb_ops` hoặc một chỉ mục khác phù hợp. Đừng tạo cả hai GIN index chỉ để phòng hờ; mỗi chỉ mục làm tăng dung lượng và chi phí cập nhật JSON.

### JSONPath và toán tử phù hợp

PostgreSQL hỗ trợ toán tử JSONPath như `@?` và `@@` trên JSONB ở các phiên bản tương ứng. Một số truy vấn có thể dùng GIN nếu biểu thức và operator class phù hợp.

```sql
SELECT event_id
FROM events
WHERE payload @? '$.tags[*] ? (@ == "priority")';
```

JSONPath biểu đạt truy vấn linh hoạt, nhưng không phải mọi biểu thức JSONPath đều được chỉ mục hóa như nhau. Hãy kiểm tra tài liệu đúng phiên bản và execution plan với dữ liệu thực tế.

## 5. B-tree trên trường scalar của JSON

GIN phù hợp với các phép tìm thành phần, nhưng truy vấn thường xuyên lọc theo một scalar có thể phù hợp hơn với B-tree trên biểu thức.

Ví dụ:

```sql
CREATE INDEX ix_events_customer_id
    ON events ((payload->>'customerId'));

SELECT event_id, occurred_at
FROM events
WHERE payload->>'customerId' = '4201';
```

Chỉ mục biểu thức (expression index) cần khớp với biểu thức truy vấn. Nếu chỉ mục được tạo trên `payload->>'customerId'` nhưng truy vấn dùng một phép ép kiểu hoặc hàm khác, hệ quản trị có thể không dùng được chỉ mục đó.

Nếu cần so sánh số học, hãy chuyển giá trị về kiểu số nhất quán:

```sql
CREATE INDEX ix_events_customer_id_num
    ON events (((payload->>'customerId')::BIGINT));

SELECT event_id
FROM events
WHERE (payload->>'customerId')::BIGINT = 4201;
```

Ví dụ này giả định mọi giá trị được lập chỉ mục có thể chuyển thành BIGINT. Nếu payload có giá trị thiếu, NULL hoặc chuỗi không hợp lệ, phép ép kiểu có thể gây lỗi khi tạo hoặc duy trì chỉ mục. Cần kiểm soát dữ liệu, dùng biểu thức an toàn phù hợp hoặc chuyển trường quan trọng sang cột có kiểu rõ ràng.

Với truy vấn lọc theo scalar, sắp xếp hoặc range như `customerId >= 4000`, B-tree thường phù hợp hơn GIN. B-tree cũng có thể hỗ trợ ORDER BY và range scan trên giá trị đã trích xuất.

## 6. Generated column và computed column cho JSON

Nếu một thuộc tính JSON được dùng thường xuyên, có kiểu rõ ràng và cần join hoặc lọc nhiều, cân nhắc tạo cột sinh (generated column) hoặc computed column. Cách này làm rõ kiểu dữ liệu và cho phép tạo chỉ mục thông thường trên trường đó.

### Ví dụ với MySQL

MySQL có kiểu JSON và có thể tạo generated column trích xuất một đường dẫn JSON rồi lập chỉ mục cột đó:

```sql
ALTER TABLE events
  ADD COLUMN customer_id BIGINT
    GENERATED ALWAYS AS (
      CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.customerId')) AS UNSIGNED)
    ) STORED,
  ADD INDEX ix_events_customer_id (customer_id);
```

Truy vấn nên dùng cột sinh:

```sql
SELECT event_id, occurred_at
FROM events
WHERE customer_id = 4201;
```

Kiểu cột phải phản ánh đúng dữ liệu. Nếu JSON chứa giá trị không hợp lệ hoặc vượt miền kiểu, việc chuyển đổi có thể tạo lỗi hoặc giá trị không mong muốn tùy SQL mode và phiên bản. Hãy xác định quy tắc kiểm tra dữ liệu đầu vào.

MySQL cũng có các khả năng lập chỉ mục nhiều giá trị cho một số truy vấn JSON array ở các phiên bản hỗ trợ. Cú pháp và điều kiện áp dụng phụ thuộc phiên bản; không nên giả định một chỉ mục scalar thông thường có thể tăng tốc phép tìm phần tử trong mọi array.

### Ví dụ với SQL Server

SQL Server có thể trích xuất scalar từ JSON bằng `JSON_VALUE` và dùng computed column để tạo chỉ mục nếu biểu thức đáp ứng các yêu cầu về tính xác định và kiểu dữ liệu của phiên bản:

```sql
ALTER TABLE dbo.Events
ADD CustomerId AS TRY_CONVERT(BIGINT, JSON_VALUE(Payload, '$.customerId'));

CREATE INDEX IX_Events_CustomerId
ON dbo.Events(CustomerId);
```

Truy vấn dùng computed column:

```sql
SELECT EventId, OccurredAt
FROM dbo.Events
WHERE CustomerId = 4201;
```

Khả năng lập chỉ mục computed column phụ thuộc kiểu biểu thức, collation, tùy chọn kết nối và phiên bản. Kiểm tra tài liệu SQL Server tương ứng và actual execution plan. Nếu biểu thức `TRY_CONVERT` trả NULL cho dữ liệu lỗi, hãy quyết định cách xử lý những bản ghi đó trong nghiệp vụ.

## 7. Khi nào nên chuyển thuộc tính JSON thành cột quan hệ?

JSON giúp lưu cấu trúc linh hoạt, nhưng không phải mọi thuộc tính đều nên giữ bên trong payload.

Cân nhắc cột riêng khi thuộc tính:

- Được lọc hoặc JOIN thường xuyên trong nhiều truy vấn.
- Có kiểu dữ liệu rõ ràng và quy tắc kiểm tra ổn định.
- Cần ràng buộc UNIQUE, FOREIGN KEY hoặc NOT NULL.
- Cần sắp xếp, lọc theo khoảng hoặc thống kê thường xuyên.
- Là khóa định danh hoặc chiều phân vùng.

Giữ trong JSON khi thuộc tính ít được truy vấn, thay đổi theo loại sự kiện hoặc được xử lý như một payload nguyên khối.

Ví dụ, `customer_id` có thể là cột quan hệ vì được JOIN với bảng khách hàng, trong khi `device_metadata` có thể giữ trong JSON nếu chỉ phục vụ hiển thị hoặc lưu trữ linh hoạt.

Chuyển trường ra cột làm thay đổi schema và luồng ghi; nếu dữ liệu vẫn được lưu song song ở JSON và cột riêng, cần có một nguồn sự thật và quy tắc đồng bộ rõ ràng. Tránh hai nơi chứa cùng một giá trị nhưng có thể lệch nhau.

## 8. Chỉ mục không gian và bounding box

Dữ liệu không gian thường lưu hình học như POINT, LINESTRING hoặc POLYGON. Các phép toán phổ biến gồm giao nhau, chứa, nằm trong, chạm, khoảng cách và tìm lân cận.

Chỉ mục không gian thường không lập chỉ mục toàn bộ hình học theo cách B-tree sắp một scalar. Một cấu trúc như R-tree hoặc GiST tổ chức các vùng bao (bounding boxes) để nhanh chóng loại bỏ phần lớn đối tượng không thể phù hợp.

Bounding box là hình chữ nhật tối thiểu song song với trục tọa độ bao quanh một hình học. Nếu bounding box của hai đối tượng không giao nhau, hai hình học chắc chắn không giao nhau. Nếu bounding box giao nhau, hai hình học có thể giao nhau hoặc chỉ có vùng bao chồng lấn; cần bước kiểm tra hình học chính xác.

<escape>Luồng xử lý khái quát:</escape>

```text
Điều kiện không gian
        |
        v
Tìm các bounding box có khả năng phù hợp
        |
        v
Tập ứng viên (có thể có false positive)
        |
        v
Kiểm tra hình học chính xác
        |
        v
Kết quả cuối cùng
```

Vì có bước lọc ứng viên, execution plan có thể thể hiện một điều kiện bounding-box hoặc index recheck trước khi áp dụng predicate chính xác. Đây là hành vi bình thường của nhiều spatial index.

## 9. PostgreSQL/PostGIS: GiST cho dữ liệu không gian

PostGIS bổ sung kiểu hình học và các hàm không gian cho PostgreSQL. Chỉ mục GiST là lựa chọn phổ biến cho cột geometry:

```sql
CREATE INDEX ix_places_geom
    ON places USING GIST (geom);
```

Truy vấn tìm địa điểm giao với một vùng:

```sql
SELECT place_id, name
FROM places
WHERE ST_Intersects(
    geom,
    ST_MakeEnvelope(105.75, 21.00, 105.90, 21.10, 4326)
);
```

`ST_Intersects` là một trong các predicate không gian có thể tận dụng chỉ mục thông qua lọc bounding box khi điều kiện phù hợp. PostGIS sẽ kiểm tra chính xác các ứng viên để loại bỏ false positive.

### Phân biệt geometry và geography

`geometry` biểu diễn tọa độ trong một hệ tham chiếu phẳng hoặc hệ tọa độ được khai báo. Khoảng cách và diện tích được tính theo đơn vị của hệ tọa độ đó. `geography` phù hợp hơn cho một số phép toán trên bề mặt Trái Đất, nhưng có chi phí và tập toán tử khác.

SRID (Spatial Reference System Identifier) mô tả hệ quy chiếu tọa độ. Hai hình học cần có hệ tọa độ tương thích để so sánh có ý nghĩa.

- `ST_SetSRID` gắn metadata SRID, không chuyển đổi giá trị tọa độ.
- `ST_Transform` chuyển tọa độ từ một hệ quy chiếu sang hệ khác.

Không dùng `ST_SetSRID` thay cho chuyển đổi tọa độ. Nếu gán nhầm SRID, truy vấn có thể trả kết quả sai dù chỉ mục vẫn được sử dụng.

### Tìm các đối tượng gần nhất

PostGIS hỗ trợ toán tử KNN `<->` với các chỉ mục GiST trong các trường hợp và kiểu dữ liệu được hỗ trợ:

```sql
SELECT place_id, name
FROM places
ORDER BY geom <-> ST_SetSRID(ST_MakePoint(105.85, 21.03), 4326)
LIMIT 10;
```

Đây là mẫu tìm ứng viên gần nhất theo toán tử khoảng cách của kiểu hình học. Nếu nghiệp vụ cần khoảng cách địa lý chính xác theo mét trên bề mặt Trái Đất, hãy chọn geometry/geography và phép toán phù hợp, kiểm tra SRID, đơn vị và khả năng KNN của phiên bản PostGIS.

## 10. Chỉ mục không gian trong các hệ quản trị khác

Các sản phẩm có cách triển khai khác nhau:

| Hệ quản trị | Cơ chế thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| MySQL InnoDB | Spatial index dựa trên R-tree cho kiểu dữ liệu không gian | Cột hình học, SRID, điều kiện NOT NULL và giới hạn phiên bản; toán tử phải hỗ trợ spatial index |
| SQL Server | Spatial index dùng cấu trúc tessellation để chia không gian thành các ô | Geometry/geography, tessellation scheme, bounding box và predicate được hỗ trợ |
| Oracle Spatial | Spatial index thường dựa trên R-tree hoặc cơ chế được cấu hình | Metadata, dimension, SRID, loại hình học và toán tử Spatial được dùng |

Không nên sao chép cú pháp hoặc giả định của PostGIS sang hệ quản trị khác. Hãy dùng công cụ tạo spatial index của sản phẩm, xác nhận SRID và đọc execution plan theo đúng phiên bản.

## 11. Predicate không gian và điều kiện dùng chỉ mục

Toán tử không gian thể hiện ngữ nghĩa khác nhau. Một chỉ mục có thể hỗ trợ bước lọc sơ bộ cho một số predicate nhưng không phải tất cả.

| Nhu cầu | Predicate ví dụ | Câu hỏi khi thiết kế |
| --- | --- | --- |
| Hai hình có giao nhau? | `ST_Intersects(a, b)` | Chỉ mục có lọc được các bounding box ứng viên không? |
| Hình A chứa hình B? | `ST_Contains(a, b)` | Hướng tham số có đúng ngữ nghĩa và hệ quản trị có hỗ trợ index-aware predicate không? |
| Điểm nằm trong vùng? | `ST_Within(point, polygon)` | Geometry có cùng SRID và predicate có thể tận dụng spatial index không? |
| Hình chạm biên? | `ST_Touches(a, b)` | Có bước exact predicate sau bounding-box filter không? |
| Tìm gần nhất | KNN hoặc hàm khoảng cách | Có thể dùng index-assisted ordering hay phải tính khoảng cách cho nhiều đối tượng? |

Trong một số hệ quản trị, viết `ST_Distance(geom, query_geom) < radius` có thể không tận dụng chỉ mục tốt như predicate được thiết kế cho index filtering. Có thể cần thêm điều kiện bounding-box hoặc dùng hàm distance-aware phù hợp. Với PostGIS, `ST_DWithin` là lựa chọn thường được ưu tiên cho truy vấn trong một khoảng cách nhất định vì có thể tận dụng chỉ mục.

Ví dụ:

```sql
SELECT place_id, name
FROM places
WHERE ST_DWithin(
    geom::geography,
    ST_SetSRID(ST_MakePoint(105.85, 21.03), 4326)::geography,
    1000
);
```

Ví dụ giả định `geom` có tọa độ longitude/latitude trong SRID phù hợp. `1000` là khoảng cách tính bằng mét khi dùng geography. Cần kiểm tra dữ liệu, SRID và kiểu cột thực tế; cast trong truy vấn có thể ảnh hưởng việc dùng chỉ mục nếu chỉ mục được tạo trên kiểu khác. Có thể cân nhắc chỉ mục trên biểu thức geography hoặc lưu cột geography riêng nếu workload yêu cầu.

## 12. Kết hợp chỉ mục JSON và chỉ mục quan hệ

Một bảng có thể chứa JSON nhưng vẫn cần chỉ mục quan hệ cho thời gian, tenant hoặc khóa chính. Có thể dùng nhiều chỉ mục để hỗ trợ các phần khác nhau của truy vấn, nhưng bộ tối ưu quyết định có kết hợp chúng hay không.

Ví dụ trong PostgreSQL:

```sql
CREATE INDEX ix_events_occurred_at
    ON events (occurred_at);

CREATE INDEX ix_events_payload_gin
    ON events USING GIN (payload jsonb_path_ops);

SELECT event_id
FROM events
WHERE occurred_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND payload @> '{"type":"payment"}'::jsonb;
```

PostgreSQL có thể cân nhắc bitmap combination giữa các chỉ mục phù hợp, nhưng không bảo đảm luôn kết hợp. Nếu điều kiện thời gian loại bỏ phần lớn dữ liệu, B-tree có thể đủ; nếu JSON containment chọn lọc cao, GIN có thể là đường chính; nếu cả hai đều có ích, bitmap plan có thể giảm số hàng cần đọc.

Nếu một trường JSON scalar được dùng cùng tenant và thời gian ở hầu hết truy vấn, cột sinh hoặc expression index có thể cho phép tạo composite B-tree phù hợp. Hãy thiết kế theo mẫu truy vấn phổ biến thay vì tạo một chỉ mục riêng cho từng điều kiện tùy chọn.

## 13. Chi phí và giới hạn của chỉ mục chuyên biệt

Chỉ mục chuyên biệt có thể lớn và đắt để duy trì:

- GIN có thể chứa nhiều mục cho một hàng JSON, đặc biệt khi payload có nhiều khóa và phần tử array.
- Cập nhật một phần nhỏ JSON vẫn có thể phải duy trì nhiều mục GIN.
- Một số cấu hình GIN dùng pending list để gom cập nhật; việc dọn pending list có thể tạo dao động độ trễ nếu không được quản lý phù hợp.
- Spatial index phải duy trì cấu trúc bounding box khi hình học thay đổi; hình học phức tạp hoặc có bounding box rộng có thể làm tăng số ứng viên.
- Chỉ mục biểu thức hoặc cột sinh cần tính toán giá trị khi ghi hoặc cập nhật.
- Nhiều chỉ mục làm tăng dung lượng, buffer cache footprint, log ghi và thời gian bảo trì.

Độ chọn lọc và chất lượng dữ liệu rất quan trọng. Nếu phần lớn JSON có cùng một giá trị trạng thái, chỉ mục trên trạng thái đó có thể ít hữu ích hơn dự kiến. Nếu đa số polygon có bounding box lớn chồng lấn nhau, spatial index có thể trả về nhiều ứng viên và phải kiểm tra hình học chính xác nhiều lần.

Chỉ mục chuyên biệt cũng không thay thế việc chuẩn hóa dữ liệu khi quan hệ và ràng buộc cần được bảo đảm. Nếu ứng dụng thường xuyên JOIN một mã khách hàng được lưu trong JSON với bảng khách hàng, cột quan hệ có kiểu và FK rõ ràng có thể dễ kiểm soát hơn.

## 14. Đọc execution plan và đo hiệu quả

Để xác minh chỉ mục có thực sự được dùng và đem lại lợi ích, hãy thu thập:

- Loại access method và operator class của chỉ mục.
- Số dòng ước lượng và số dòng thực tế.
- Số ứng viên sau bước bounding-box hoặc GIN filtering và số dòng sau exact recheck nếu công cụ cung cấp.
- Logical reads, physical reads, buffer hit/read, CPU và elapsed time.
- Kích thước chỉ mục, tốc độ tăng trưởng và chi phí ghi khi cập nhật JSON/hình học.
- p50/p95/p99, throughput và tỷ lệ lỗi trong workload đại diện.

### Kiểm tra JSON trong PostgreSQL

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id
FROM events
WHERE payload @> '{"type":"payment"}'::jsonb;
```

Kiểm tra kế hoạch có dùng Bitmap Index Scan/Bitmap Heap Scan hoặc đường truy cập GIN phù hợp không. Xem số hàng thực tế, số buffer, thời gian và phần recheck nếu có. Với truy vấn scalar dùng expression index, xác nhận biểu thức trong điều kiện khớp biểu thức chỉ mục.

### Kiểm tra không gian trong PostGIS

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT place_id
FROM places
WHERE ST_Intersects(
    geom,
    ST_MakeEnvelope(105.75, 21.00, 105.90, 21.10, 4326)
);
```

Kiểm tra chỉ mục GiST có được sử dụng để lọc ứng viên, số dòng bị loại ở recheck và lượng buffer được đọc. Nếu phần lớn bounding box giao nhau, spatial index có thể không chọn lọc tốt; cần đánh giá phân bố hình học và kích thước vùng truy vấn.

`EXPLAIN ANALYZE` thực thi truy vấn. Hãy chạy trong môi trường phù hợp và lưu ý chi phí của truy vấn nặng; không bật đo đạc chi tiết trên tải sản xuất mà chưa cân nhắc overhead.

## 15. Quy trình chọn và triển khai chỉ mục chuyên biệt

1. **Thu thập workload.** Xác định các truy vấn JSON hoặc không gian có tần suất cao, độ trễ lớn hoặc chi phí đọc đáng kể.
2. **Phân loại toán tử.** Ghi rõ containment, key existence, scalar equality/range, spatial intersection, containment, distance hoặc nearest-neighbor.
3. **Xác định kiểu dữ liệu và hệ quản trị.** Kiểm tra JSON/JSONB, geometry/geography, SRID, phiên bản và operator class.
4. **Chọn access method.** Cân nhắc GIN, B-tree expression, generated/computed column, GiST, R-tree hoặc spatial index của sản phẩm.
5. **Kiểm tra tính tương thích.** Đảm bảo biểu thức truy vấn và toán tử có thể dùng chỉ mục; kiểm tra cast, collation, SRID và kiểu tham số.
6. **Tạo chỉ mục thử nghiệm.** Dùng dữ liệu có phân bố, kích thước JSON và hình học tương tự môi trường cần phục vụ.
7. **Đọc execution plan.** Xác nhận index scan/filter/recheck, số dòng ứng viên, số buffer và ước lượng.
8. **Đo trước/sau.** So sánh độ trễ, throughput, CPU, I/O, kích thước chỉ mục và chi phí INSERT/UPDATE/DELETE.
9. **Kiểm tra độ đúng.** So sánh tập kết quả với truy vấn không dùng chỉ mục hoặc cách tính chuẩn; đặc biệt kiểm tra SRID, ranh giới hình học và dữ liệu JSON bất thường.
10. **Theo dõi vận hành.** Quan sát index bloat, GIN pending list, spatial index maintenance, thay đổi phân bố dữ liệu và plan regression.

## 16. Những sai lầm thường gặp

- **Dùng GIN cho mọi truy vấn JSON.** Scalar equality hoặc range có thể phù hợp hơn với B-tree trên biểu thức hoặc cột sinh.
- **Chọn sai operator class.** `jsonb_path_ops` không hỗ trợ các toán tử kiểm tra sự tồn tại khóa như `?`, `?|`, `?&`.
- **Giả định mọi JSONPath đều được tăng tốc.** Chỉ các toán tử và dạng biểu thức được hỗ trợ mới có thể tận dụng chỉ mục.
- **Truy vấn không khớp biểu thức chỉ mục.** Khác biệt về cast, hàm hoặc đường dẫn JSON có thể khiến chỉ mục biểu thức không được dùng.
- **Lập chỉ mục toàn bộ payload mà không cân nhắc chi phí.** JSON lớn và nhiều khóa có thể làm GIN rất lớn và cập nhật đắt.
- **Dùng spatial index nhưng bỏ qua SRID.** Hệ quy chiếu sai có thể tạo kết quả không đúng dù kế hoạch có dùng chỉ mục.
- **Coi bounding box là kết quả hình học chính xác.** Bounding box chỉ lọc ứng viên; cần exact predicate để xác nhận.
- **Dùng ST_SetSRID để chuyển tọa độ.** Hàm này gắn nhãn SRID, không biến đổi tọa độ; cần ST_Transform khi phải đổi hệ quy chiếu.
- **Ép dùng index scan cho mọi truy vấn.** Quét tuần tự có thể rẻ hơn khi điều kiện chọn lọc thấp hoặc nhiều ứng viên.
- **Chỉ đo SELECT.** GIN, spatial index và expression index làm tăng chi phí ghi, log và bảo trì.

## 17. Danh sách kiểm tra trước khi triển khai

- [ ] Đã phân loại truy vấn theo JSON scalar, containment, key existence hoặc phép toán không gian.
- [ ] Đã xác định toán tử và operator class/access method tương thích.
- [ ] Đã cân nhắc B-tree expression hoặc generated/computed column cho scalar thường xuyên dùng.
- [ ] Đã chọn `jsonb_ops` hoặc `jsonb_path_ops` theo đúng toán tử thực tế nếu dùng PostgreSQL.
- [ ] Dữ liệu JSON có kiểu và quy tắc kiểm tra phù hợp với biểu thức chỉ mục.
- [ ] Cột hình học có SRID đúng và thống nhất với hình học truy vấn.
- [ ] Đã phân biệt bounding-box candidate filter với phép kiểm tra chính xác.
- [ ] Execution plan xác nhận chỉ mục được dùng và số ứng viên ở mức hợp lý.
- [ ] Đã đo p95/p99, throughput, CPU, I/O, kích thước chỉ mục và chi phí ghi.
- [ ] Đã kiểm tra kết quả đúng với dữ liệu biên và trường hợp bất thường.
- [ ] Đã xác định chính sách bảo trì và theo dõi chỉ mục sau triển khai.

## Kết luận

Chỉ mục cho JSON và dữ liệu không gian cần được chọn theo toán tử mà ứng dụng thực sự sử dụng. Với JSON, GIN phù hợp cho một số phép tìm thành phần hoặc containment, còn B-tree trên biểu thức hay generated/computed column thường phù hợp hơn cho scalar equality, range và sort. Với dữ liệu không gian, GiST, R-tree hoặc spatial index của hệ quản trị thường dùng bounding box để lọc ứng viên trước khi kiểm tra hình học chính xác. Hãy xác nhận kiểu dữ liệu, operator class, SRID và biểu thức truy vấn, đọc execution plan rồi đo cả lợi ích đọc lẫn chi phí ghi, dung lượng và bảo trì trên workload đại diện.
