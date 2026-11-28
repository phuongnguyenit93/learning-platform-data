# Chỉ mục range, text, point và token lookup theo nhu cầu truy vấn

Trong Neo4j, truy vấn thường bắt đầu bằng việc tìm node hoặc relationship phù hợp, sau đó đi theo các cạnh để lấy phần graph cần thiết. Chỉ mục (index) giúp database tìm điểm bắt đầu nhanh hơn bằng cách tạo access path từ label, relationship type hoặc giá trị property đến các thực thể tương ứng.

Neo4j có bốn loại performance index chính: **range**, **text**, **point** và **token lookup**. Mỗi loại phục vụ một dạng điều kiện khác nhau. Chọn đúng index giúp Cypher planner tìm dữ liệu hiệu quả; tạo index không phù hợp chỉ làm tăng dung lượng và chi phí ghi mà không cải thiện truy vấn.

Với Spring Data Neo4j (SDN), repository và `@Query` vẫn gửi Cypher đến Neo4j. Database tự chọn index phù hợp dựa trên truy vấn và schema hiện có. Vì vậy, thiết kế index cần bắt đầu từ các truy vấn thực tế của ứng dụng, sau đó được quản lý như một phần của schema database.

## 1. Index giải quyết phần nào của truy vấn graph?

Giả sử ứng dụng quản lý phim, diễn viên, địa điểm và lượt đánh giá:

- Tìm phim theo `status`, `releaseYear` hoặc `title`.
- Tìm tên phim có chứa một đoạn ký tự.
- Tìm địa điểm trong bán kính quanh tọa độ người dùng.
- Duyệt tất cả node `Movie` hoặc relationship `ACTED_IN`.

Các truy vấn này có hình dạng khác nhau. Một index property không thể tối ưu mọi dạng điều kiện:

| Nhu cầu truy vấn | Index phù hợp |
|---|---|
| So sánh bằng, `IN`, điều kiện lớn/nhỏ, khoảng giá trị, tiền tố | Range |
| Tìm chuỗi có chứa đoạn con hoặc kết thúc bằng hậu tố | Text |
| Lọc điểm địa lý theo khoảng cách hoặc hộp tọa độ | Point |
| Tìm node theo label hoặc relationship theo type | Token lookup |

Index không lưu kết quả truy vấn hoàn chỉnh. Nó cung cấp đường truy cập nhanh đến các node hoặc relationship thỏa điều kiện. Sau khi tìm được điểm bắt đầu, Neo4j vẫn phải đọc property và duyệt relationship cần thiết để hoàn thành truy vấn.

Ví dụ, nếu tìm một phim theo ID rồi duyệt các diễn viên tham gia, index trên ID giúp tìm node `Movie`; index không thay thế việc duyệt `ACTED_IN` để lấy `Actor`.

## 2. Range index: lựa chọn mặc định cho phần lớn điều kiện property

Range index là performance index tổng quát và là loại mặc định khi dùng lệnh `CREATE INDEX` mà không chỉ định loại. Nó phù hợp với nhiều kiểu property và các phép so sánh phổ biến:

- Equality: `m.status = $status`.
- Membership: `m.status IN $statuses`.
- Range: `m.releaseYear >= $fromYear`.
- Existence: `m.title IS NOT NULL`.
- Prefix: `m.title STARTS WITH $prefix`.

Tạo range index cho label `Movie` và property `status`:

```cypher
CREATE RANGE INDEX movie_status_range IF NOT EXISTS
FOR (m:Movie) ON (m.status);
```

Truy vấn tương ứng:

```cypher
MATCH (m:Movie)
WHERE m.status = $status
RETURN m
ORDER BY m.title;
```

Range index cũng phù hợp với truy vấn lọc theo khoảng số:

```cypher
MATCH (m:Movie)
WHERE m.releaseYear >= $fromYear
  AND m.releaseYear < $toYear
RETURN m.title, m.releaseYear
ORDER BY m.releaseYear;
```

Với khoảng `[fromYear, toYear)`, cận dưới được lấy còn cận trên không được lấy. Cách biểu diễn này tiện khi chia dữ liệu theo năm hoặc khoảng thời gian liên tiếp.

### Range index cho nhiều property

Nếu ứng dụng thường xuyên lọc đồng thời theo trạng thái và năm phát hành, có thể cân nhắc composite range index:

```cypher
CREATE RANGE INDEX movie_status_year_range IF NOT EXISTS
FOR (m:Movie) ON (m.status, m.releaseYear);
```

Truy vấn thể hiện đúng hai điều kiện:

```cypher
MATCH (m:Movie)
WHERE m.status = $status
  AND m.releaseYear >= $fromYear
RETURN m;
```

Composite index có thứ tự property. Thứ tự khai báo ảnh hưởng cách planner sử dụng index, vì vậy nên đặt các property theo những tổ hợp điều kiện xuất hiện thường xuyên trong truy vấn. Không tạo composite index chỉ vì entity có nhiều field.

Khả năng sử dụng composite index phụ thuộc predicate và thứ tự property; không giả định index gồm `(status, releaseYear)` sẽ tối ưu truy vấn chỉ lọc `releaseYear`. Dùng `EXPLAIN` hoặc `PROFILE` để kiểm tra execution plan cho từng dạng query thực tế.

### Index trên relationship property

Neo4j cũng hỗ trợ range index trên property của relationship. Ví dụ, nếu truy vấn thường lọc các lần tham gia diễn xuất theo năm:

```cypher
CREATE RANGE INDEX acted_in_since_range IF NOT EXISTS
FOR ()-[r:ACTED_IN]-() ON (r.since);
```

```cypher
MATCH (a:Actor)-[r:ACTED_IN]->(m:Movie)
WHERE r.since >= $year
RETURN a.name, m.title, r.since;
```

Index relationship property có ích khi predicate trên relationship giúp thu hẹp đáng kể tập quan hệ cần xét. Nếu truy vấn luôn tìm một node `Movie` có ID chọn lọc trước rồi chỉ duyệt một số relationship kề nó, index relationship có thể không phải điểm tối ưu đầu tiên. Hãy đo execution plan và số lượng dữ liệu thực tế.

## 3. Text index: tìm substring và suffix trong property kiểu chuỗi

Text index được thiết kế cho predicate trên giá trị `STRING`, đặc biệt:

- `CONTAINS`: chuỗi có chứa đoạn con.
- `ENDS WITH`: chuỗi kết thúc bằng hậu tố.
- `STARTS WITH`: chuỗi bắt đầu bằng tiền tố.

Tạo text index cho tên phim:

```cypher
CREATE TEXT INDEX movie_title_text IF NOT EXISTS
FOR (m:Movie) ON (m.title);
```

Truy vấn tìm đoạn con:

```cypher
MATCH (m:Movie)
WHERE m.title CONTAINS $fragment
RETURN m.title;
```

Truy vấn tìm hậu tố:

```cypher
MATCH (m:Movie)
WHERE m.title ENDS WITH $suffix
RETURN m.title;
```

Text index cũng có thể giải quyết một số predicate equality, `IN` và prefix nếu planner biết property được so sánh là chuỗi. Tuy nhiên, khi có cả range index và text index trên cùng property, range index thường được ưu tiên cho equality hoặc `STARTS WITH`; text index được ưu tiên cho `CONTAINS` và `ENDS WITH`.

Text index không phải công cụ tìm kiếm toàn văn có xếp hạng. Nếu yêu cầu là tìm từ khóa trong nội dung dài, hỗ trợ tokenization, relevance score hoặc tìm kiếm gần đúng theo từ, hãy tìm hiểu **full-text index**. Full-text index thuộc nhóm search index, được gọi tường minh; nó khác performance text index được Cypher planner tự chọn.

Không tạo text index cho mọi property `String`. Nếu ứng dụng chủ yếu tìm bằng chính xác hoặc tiền tố, range index thường đáp ứng tốt. Chỉ thêm text index khi query thực tế có `CONTAINS` hoặc `ENDS WITH` và phép đo cho thấy cần thiết.

## 4. Point index: truy vấn dữ liệu không gian

Point index dành cho property có giá trị kiểu `POINT`. Nó tối ưu các truy vấn không gian như:

- Tìm địa điểm trong một bán kính quanh tọa độ.
- Tìm điểm nằm trong một bounding box.
- Lọc theo khoảng cách giữa điểm được lưu và điểm truy vấn.

Tạo index cho tọa độ của node `Place`:

```cypher
CREATE POINT INDEX place_location_point IF NOT EXISTS
FOR (p:Place) ON (p.location);
```

Giả sử property `location` lưu điểm WGS-84. Với CRS này, `longitude` là kinh độ, `latitude` là vĩ độ và khoảng cách được tính theo mét:

```cypher
MATCH (p:Place)
WHERE point.distance(
    p.location,
    point({
        longitude: $longitude,
        latitude: $latitude
    })
) <= $radiusMeters
RETURN p.name, p.location;
```

Truy vấn trong một bounding box:

```cypher
MATCH (p:Place)
WHERE point.withinBBox(
    p.location,
    point({longitude: $west, latitude: $south}),
    point({longitude: $east, latitude: $north})
)
RETURN p.name, p.location;
```

`point.withinBBox()` nhận góc dưới bên trái và góc trên bên phải. Nếu vùng truy vấn đi qua kinh tuyến 180 độ, cần chia vùng thành hai hộp phù hợp thay vì giả định một hộp kinh độ thông thường sẽ bao phủ đúng khu vực đó.

### Phân biệt Point index và Range index

Range index có thể hỗ trợ equality trên một số giá trị point, nhưng không thay thế point index cho truy vấn khoảng cách và bounding box. Không dùng phép so sánh `<`, `>` để lọc tọa độ point. Hãy dùng `point.distance()` hoặc `point.withinBBox()` theo đúng ý nghĩa không gian.

Point index là index đơn property, không phải composite index để ghép nhiều thuộc tính tùy ý. Nếu query vừa lọc trạng thái địa điểm vừa lọc khoảng cách, planner có thể kết hợp các access path hoặc áp dụng một điều kiện sau khi tìm điểm; hãy kiểm tra execution plan.

## 5. Token lookup index: tìm theo label và relationship type

Token lookup index khác ba loại index property. Nó lập đường tra cứu từ:

- Label đến node mang label đó.
- Relationship type đến relationship thuộc type đó.

Ví dụ, truy vấn chỉ yêu cầu tất cả node `Movie`:

```cypher
MATCH (m:Movie)
RETURN m
LIMIT 20;
```

Hoặc truy vấn relationship theo type:

```cypher
MATCH ()-[r:ACTED_IN]->()
RETURN r
LIMIT 20;
```

Token lookup index giúp Neo4j tìm node theo label `Movie` hoặc relationship theo type `ACTED_IN`. Nó **không** lập chỉ mục property như `title`, `status`, `since` hoặc `location`.

Hai token lookup index — một cho node label và một cho relationship type — được tạo mặc định khi tạo database Neo4j. Thông thường ứng dụng không cần tự tạo lại. Nếu index đã bị xóa và cần khôi phục, cú pháp là:

```cypher
CREATE LOOKUP INDEX node_label_lookup IF NOT EXISTS
FOR (n) ON EACH labels(n);

CREATE LOOKUP INDEX relationship_type_lookup IF NOT EXISTS
FOR ()-[r]-() ON EACH type(r);
```

Không xóa token lookup index để tiết kiệm dung lượng nếu chưa hiểu ảnh hưởng. Nó hỗ trợ truy vấn theo label/type và cả quá trình population của các index khác.

Nếu truy vấn có điều kiện property chọn lọc như `m.id = $id`, range index trên `id` thường hữu ích hơn việc chỉ bắt đầu từ token lookup rồi lọc property. Planner có thể chọn access path phù hợp nhất.

## 6. So sánh bốn loại performance index

| Loại index | Dữ liệu được lập chỉ mục | Predicate tiêu biểu | Ví dụ nhu cầu |
|---|---|---|---|
| Range | Property trên node hoặc relationship | `=`, `IN`, `>`, `<`, `STARTS WITH`, `IS NOT NULL` | Tìm phim theo trạng thái/năm |
| Text | Property chuỗi | `CONTAINS`, `ENDS WITH`; cũng hỗ trợ một số equality/prefix | Tìm tên có chứa cụm ký tự |
| Point | Property kiểu `POINT` | `point.distance`, `point.withinBBox` | Tìm địa điểm gần tọa độ |
| Token lookup | Node label hoặc relationship type | `MATCH (n:Label)`, `MATCH ()-[r:TYPE]-()` | Bắt đầu từ một loại node hoặc relationship |

Không nhầm các loại sau:

- **Text index** tối ưu một số phép so khớp chuỗi theo predicate; **full-text index** phục vụ tìm kiếm từ khóa và relevance.
- **Point index** phục vụ dữ liệu không gian; range index không thay thế được truy vấn distance/bounding box.
- **Token lookup index** chỉ xử lý label/type; nó không thể thay index trên property.
- **Constraint** bảo đảm quy tắc dữ liệu như uniqueness; index thuần túy chủ yếu cung cấp access path. Một số constraint có index hỗ trợ riêng.

## 7. Index và constraint: hai mục tiêu khác nhau

Nếu `Movie.id` phải duy nhất, yêu cầu đó nên được mô hình hóa bằng uniqueness constraint:

```cypher
CREATE CONSTRAINT movie_id_unique IF NOT EXISTS
FOR (m:Movie)
REQUIRE m.id IS UNIQUE;
```

Unique constraint vừa bảo đảm không có hai node `Movie` cùng ID, vừa có backing range index để hỗ trợ tra cứu. Không tạo thêm một range index trùng trên cùng label/property chỉ để tìm theo ID.

Index thông thường không ngăn dữ liệu trùng lặp. Nếu ứng dụng cần bảo đảm uniqueness hoặc existence, hãy dùng constraint phù hợp với phiên bản và edition Neo4j thay vì kỳ vọng một index đơn lẻ thực hiện điều đó.

Trước khi thêm index, kiểm tra xem constraint đã tạo backing index cùng schema hay chưa. Một index dư thừa làm tăng chi phí ghi, dung lượng và thời gian bảo trì.

## 8. Planner tự chọn index như thế nào?

Performance indexes được Cypher planner lựa chọn tự động. Ứng dụng thường chỉ cần viết predicate đúng và bảo đảm index phù hợp đã ở trạng thái sử dụng được.

Ví dụ repository SDN có thể dùng derived query hoặc `@Query`:

```java
public interface MovieRepository
        extends Neo4jRepository<Movie, String> {

    @Query("""
        MATCH (m:Movie)
        WHERE m.status = $status
          AND m.releaseYear >= $fromYear
        RETURN m
        ORDER BY m.releaseYear
        """)
    List<Movie> findReleasedSince(
            String status,
            int fromYear);
}
```

Index không được chọn bởi tên method Java hay annotation repository. Planner xem Cypher đã sinh, label, property, kiểu predicate, kiểu giá trị, thống kê và các index đang tồn tại.

Trong đa số trường hợp, không cần viết index hint. `USING INDEX` có thể ép planner xem xét một access path cụ thể, nhưng chỉ nên dùng khi đã đo execution plan và hiểu vì sao lựa chọn tự động chưa phù hợp. Hint có thể trở nên bất lợi khi dữ liệu hoặc thống kê thay đổi.

## 9. Kiểm tra index đã được tạo và sẵn sàng

Sau khi tạo index, kiểm tra trạng thái:

```cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties,
      state, populationPercent, lastRead, readCount
RETURN name, type, entityType, labelsOrTypes, properties,
       state, populationPercent, lastRead, readCount
ORDER BY name;
```

Các cột cần chú ý:

- `type`: `RANGE`, `TEXT`, `POINT`, `LOOKUP` hoặc loại khác.
- `labelsOrTypes` và `properties`: schema mà index phục vụ.
- `state`: trạng thái hiện tại.
- `populationPercent`: tiến độ tạo index nếu đang population.
- `lastRead` và `readCount`: tín hiệu hỗ trợ đánh giá index có được truy vấn dùng hay không.

Index ở trạng thái `POPULATING` chưa sẵn sàng phục vụ truy vấn. Chờ đến khi `ONLINE` rồi mới đánh giá hiệu quả. Nếu `FAILED`, cần xem lỗi population và xử lý trước khi kỳ vọng planner dùng index.

Có thể lọc theo loại:

```cypher
SHOW RANGE INDEXES;
SHOW TEXT INDEXES;
SHOW POINT INDEXES;
SHOW LOOKUP INDEXES;
```

Không xóa index chỉ vì `readCount` thấp trong một khoảng ngắn. Hãy xét chu kỳ sử dụng ứng dụng, truy vấn hiếm nhưng quan trọng và thời gian theo dõi trước khi kết luận index không cần thiết.

## 10. Dùng EXPLAIN và PROFILE để xác minh

Không thể kết luận một index có ích chỉ từ việc nó tồn tại. Cần xem execution plan của query thật.

`EXPLAIN` lập kế hoạch nhưng không thực thi query:

```cypher
EXPLAIN
MATCH (m:Movie)
WHERE m.status = $status
RETURN m;
```

`PROFILE` thực thi query và bổ sung số liệu thực tế:

```cypher
PROFILE
MATCH (m:Movie)
WHERE m.status = $status
RETURN m;
```

Khi đọc plan, quan sát:

- Planner có bắt đầu bằng index seek/scan phù hợp không?
- Có đang quét toàn bộ label rồi mới lọc property không?
- Số hàng thực tế có chênh lệch lớn so với ước lượng không?
- Số DB hits và lượng dữ liệu trung gian có hợp lý không?
- Sau khi tìm điểm bắt đầu, phần traversal có tạo quá nhiều hàng không?

Tên operator cụ thể có thể khác theo phiên bản và hình dạng truy vấn. Mục tiêu là xác nhận access path thực tế, số hàng và chi phí, không chỉ tìm một tên operator cố định.

`PROFILE` thực sự chạy query. Với truy vấn ghi hoặc truy vấn có side effect, hãy hiểu tác động trước khi chạy; dùng `EXPLAIN` khi chỉ muốn xem kế hoạch mà không thực thi.

## 11. Từ truy vấn đến index: ví dụ thiết kế cho một ứng dụng

Giả sử ứng dụng có các use case sau:

| Use case | Cypher predicate/pattern | Index nên xem xét |
|---|---|---|
| Tìm phim theo ID | `m.id = $id` | Range hoặc uniqueness constraint trên `Movie.id` |
| Lọc phim theo trạng thái và năm | `m.status = $status AND m.releaseYear >= $year` | Composite range nếu đây là pattern thường xuyên |
| Tìm tiêu đề chứa đoạn ký tự | `m.title CONTAINS $fragment` | Text |
| Tìm địa điểm trong bán kính | `point.distance(p.location, $center) <= $radius` | Point |
| Lấy node theo label | `MATCH (m:Movie)` | Token lookup mặc định |
| Lấy relationship theo type | `MATCH ()-[r:ACTED_IN]-()` | Token lookup mặc định |

Không nhất thiết phải tạo tất cả index ngay khi thiết kế entity. Bắt đầu từ truy vấn có tần suất cao hoặc độ trễ quan trọng, đo trên dữ liệu gần với production rồi bổ sung index có bằng chứng.

### Quy trình quyết định

1. Viết query đại diện với đúng label, relationship type và predicate.
2. Xác định predicate là equality/range/prefix, substring/suffix, spatial hay label/type.
3. Kiểm tra index hoặc constraint hiện có bằng `SHOW INDEXES`.
4. Tạo index đúng loại nếu thiếu.
5. Chờ index ở trạng thái `ONLINE`.
6. Chạy `EXPLAIN` để xem planner dự kiến dùng access path nào.
7. Chạy `PROFILE` trên dữ liệu đại diện để so sánh DB hits, rows và thời gian.
8. Theo dõi tác động lên tốc độ ghi, dung lượng và các query khác.

## 12. Quản lý index trong dự án Spring Data Neo4j

Với SDN 6 trở lên, các annotation index cũ của Neo4j-OGM như `@Index`, `@CompositeIndex` và `@Required` đã bị loại bỏ, không có thay thế trực tiếp trong entity mapping. SDN tách mô hình domain khỏi việc tạo schema và khuyến nghị quản lý index/constraint bằng database migration có kiểm soát.

Điều này quan trọng khi triển khai nhiều phiên bản ứng dụng song song. Nếu mỗi lần khởi động ứng dụng tự ý tạo hoặc xóa schema theo entity metadata, các phiên bản khác nhau có thể tranh chấp trạng thái database. Migration giúp thay đổi schema có phiên bản, có thể review và triển khai theo môi trường.

Ví dụ migration Cypher có thể chứa:

```cypher
CREATE RANGE INDEX movie_status_range IF NOT EXISTS
FOR (m:Movie) ON (m.status);

CREATE TEXT INDEX movie_title_text IF NOT EXISTS
FOR (m:Movie) ON (m.title);

CREATE POINT INDEX place_location_point IF NOT EXISTS
FOR (p:Place) ON (p.location);
```

Các lệnh có thể được đặt trong công cụ migration Neo4j mà dự án lựa chọn. Cần bảo đảm migration chạy trên đúng database, dùng tài khoản có quyền tạo index và được theo dõi đến khi index `ONLINE`.

Repository SDN không cần biết index được tạo bởi migration nào. Repository khai báo truy vấn bằng method hoặc `@Query`; Neo4j planner sử dụng schema đã triển khai.

### Tương thích với SDN 5.x

SDN 5.x dựa trên Neo4j-OGM từng có cơ chế index management và annotation như `@Index`/`@CompositeIndex`. Không sao chép hướng dẫn đó sang SDN 6+ vì annotation đã bị loại bỏ. Khi nâng cấp, kiểm kê các index thực tế trong database và chuyển chúng thành migration Cypher rõ ràng.

## 13. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng range index cho `CONTAINS` mà không đo | Substring query có thể không dùng access path tối ưu | Xem xét text index |
| Dùng text index cho equality/prefix dù range đã phù hợp | Tạo index dư thừa, tăng chi phí ghi | Ưu tiên range cho phần lớn predicate thông thường |
| Dùng text index như full-text search | Không có hành vi tokenization/relevance như mong đợi | Dùng full-text index cho tìm kiếm từ khóa |
| Dùng range index cho distance/bounding box | Không tối ưu truy vấn không gian | Dùng point index và spatial predicate |
| Mong token lookup index lọc property | Index chỉ tìm label/type, không tìm property value | Tạo range/text/point index đúng property |
| Tạo index cho mọi field | Tăng storage, chi phí ghi và thời gian population | Chỉ index các query đã xác định |
| Tạo range index trùng backing index của constraint | Schema dư thừa hoặc xung đột | Kiểm tra `SHOW INDEXES` trước |
| Tạo composite index nhưng truy vấn không theo pattern tương ứng | Planner có thể không sử dụng như mong muốn | Thiết kế theo predicate thực tế và kiểm tra plan |
| Đánh giá index khi còn `POPULATING` | Query chưa được hưởng lợi từ index mới | Chờ trạng thái `ONLINE` |
| Tin rằng index luôn làm query nhanh hơn | Có thể chọn sai index hoặc tăng chi phí ghi | So sánh bằng `PROFILE` trên dữ liệu đại diện |
| Dùng annotation Neo4j-OGM trong SDN 6+ | Không biên dịch hoặc không quản lý schema như kỳ vọng | Dùng migration Cypher |

## 14. Checklist chọn index

1. Query cần tìm theo label/type hay theo property?
2. Nếu theo property, predicate là equality, range, prefix, substring hay suffix?
3. Property có kiểu dữ liệu `POINT` và query có dùng distance/bounding box không?
4. Query có lọc nhiều property cùng lúc đủ thường xuyên để cần composite range index không?
5. Đã có uniqueness constraint hoặc backing index tương ứng chưa?
6. Index có đúng label/relationship type và property không?
7. Index đã ở trạng thái `ONLINE` chưa?
8. `EXPLAIN`/`PROFILE` có cho thấy planner dùng access path phù hợp không?
9. Index có cải thiện truy vấn mà không làm chi phí ghi/storage tăng quá mức không?
10. Index được quản lý qua migration phù hợp với phiên bản SDN và Neo4j không?

## 15. Tự kiểm tra

1. Range index phù hợp với những loại predicate property nào?
2. Khi nào nên thêm text index cho một property kiểu chuỗi?
3. Text index khác full-text index ở mục tiêu và cách sử dụng như thế nào?
4. Point index tối ưu hai dạng truy vấn không gian phổ biến nào?
5. Token lookup index lập chỉ mục label và relationship type ra sao?
6. Vì sao token lookup index không thay thế range index trên property `id`?
7. Composite range index cần được thiết kế theo thứ tự property và query pattern như thế nào?
8. Uniqueness constraint khác index thuần túy ở điểm nào?
9. Vì sao phải đợi index ở trạng thái `ONLINE` trước khi đo hiệu năng?
10. `EXPLAIN` khác `PROFILE` như thế nào?
11. Vì sao SDN 6+ khuyến nghị quản lý index bằng migration thay vì annotation Neo4j-OGM?

Khi liên hệ từng index với predicate và hình dạng truy vấn cụ thể, người học có thể thiết kế access path phù hợp cho node, relationship và dữ liệu không gian; kiểm tra lựa chọn của Cypher planner; đồng thời quản lý schema có phiên bản trong ứng dụng Spring Data Neo4j.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Performance indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/)
- [Neo4j Cypher Manual — Create indexes](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/create-indexes/)
- [Neo4j Cypher Manual — The impact of indexes on query performance](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/using-indexes/)
- [Neo4j Cypher Manual — Spatial values and indexes](https://neo4j.com/docs/cypher-manual/current/values-and-types/spatial/)
- [Spring Data Neo4j 6.0 — Automatic creation of constraints and indexes](https://docs.spring.io/spring-data/neo4j/docs/6.0.x/reference/html/)
- [Spring Data Neo4j 6.1 — Schema migration recommendation](https://docs.spring.io/spring-data/neo4j/docs/6.1.2/reference/html/)
