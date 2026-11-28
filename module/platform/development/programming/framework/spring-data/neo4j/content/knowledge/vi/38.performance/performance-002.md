# Đọc EXPLAIN và PROFILE: ước lượng so với thực thi thật

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt kế hoạch thực thi do `EXPLAIN` cung cấp với số liệu thực tế từ `PROFILE`.
- Đọc cây operator từ dưới lên trên và xác định luồng dữ liệu giữa các bước.
- So sánh `Estimated Rows` với `Rows` để phát hiện ước lượng cardinality sai lệch.
- Diễn giải `DB Hits`, `Memory`, `Page Cache Hits/Misses` và `Time` đúng phạm vi.
- Nhận biết các dấu hiệu như scan lớn, mở rộng relationship có fan-out cao, sort tốn bộ nhớ hoặc Cartesian product.
- Lấy đúng Cypher do Spring Data Neo4j (SDN) tạo ra và kiểm tra query plan bằng dữ liệu, tham số đại diện.
- Lặp lại quá trình đo sau khi thay đổi query, index hoặc mô hình graph.

## 1. Query plan cho biết điều gì?

Cypher mô tả kết quả mong muốn theo dạng khai báo. Người viết query nêu pattern graph, điều kiện lọc và dữ liệu cần trả về; Neo4j sẽ phân tích câu lệnh, dùng planner/optimizer để chọn cách truy xuất graph rồi tạo physical execution plan cho runtime thực thi.

Một query plan là cây các operator. Mỗi operator thực hiện một công việc như:

- Tìm node bắt đầu từ label hoặc index.
- Mở rộng từ node sang relationship và node kế tiếp.
- Lọc các hàng không thỏa điều kiện.
- Sắp xếp, gom nhóm hoặc loại kết quả trùng.
- Chiếu các property cần trả về cho client.

Đọc query plan giúp trả lời ba câu hỏi:

1. Neo4j bắt đầu truy xuất graph từ đâu?
2. Dữ liệu tăng lên hoặc bị lọc đi ở bước nào?
3. Operator nào tạo ra nhiều lần truy cập storage, tiêu thụ bộ nhớ hoặc thời gian?

Trong Spring Data Neo4j, repository có thể sinh Cypher từ tên method, còn `@Query`, `Neo4jClient` và `Neo4jTemplate` cho phép ứng dụng viết truy vấn rõ ràng. Dù query được tạo theo cách nào, Neo4j vẫn lập kế hoạch và thực thi bằng cùng cơ chế Cypher.

## 2. Phân biệt EXPLAIN và PROFILE

Hai từ khóa đều đặt trước câu Cypher để yêu cầu Neo4j cung cấp execution plan, nhưng chúng có tác động khác nhau.

| Đặc điểm | `EXPLAIN` | `PROFILE` |
| --- | --- | --- |
| Lập kế hoạch query | Có | Có |
| Thực thi query | Không | Có |
| Thay đổi dữ liệu | Không | Có thể |
| `Estimated Rows` | Có | Có |
| `Rows` thực tế | Không | Có |
| `DB Hits` thực tế | Không | Có |
| Memory và các số đo runtime | Không có số liệu thực thi | Có các số liệu được runtime hỗ trợ |
| Mục đích chính | Kiểm tra kế hoạch dự kiến | Đo công việc thực tế của các operator |

### 2.1. EXPLAIN chỉ lập kế hoạch

Ví dụ:

```cypher
EXPLAIN
MATCH (p:Person)
WHERE p.email = $email
RETURN p
```

Neo4j phân tích câu lệnh và trả về kế hoạch mà nó dự định sử dụng. Query không được thực thi, nên không có số hàng thực tế hoặc số DB Hits thực tế.

Dùng `EXPLAIN` khi muốn kiểm tra an toàn một câu lệnh ghi như `CREATE`, `SET` hoặc `DELETE` mà chưa muốn thay đổi dữ liệu. Nó cũng hữu ích để xem planner có nhận ra index, label hoặc pattern dự kiến hay không.

### 2.2. PROFILE thực thi và đo lường

Ví dụ:

```cypher
PROFILE
MATCH (p:Person)
WHERE p.email = $email
RETURN p
```

Neo4j thực sự chạy truy vấn và ghi nhận số liệu trong quá trình thực thi. Kế hoạch có thêm các thông tin như số hàng thực tế, DB Hits, memory và page cache nếu phiên bản/runtime/edition hỗ trợ.

**PROFILE có thể ghi dữ liệu.** Nếu đặt trước câu lệnh `CREATE`, `SET`, `MERGE` hoặc `DELETE`, các thay đổi đó vẫn được thực hiện. Hãy chỉ PROFILE câu lệnh ghi trong database thử nghiệm hoặc khi đã có quy trình kiểm soát rõ ràng. PROFILE cũng tốn thêm tài nguyên để thu thập số liệu; không nên dùng đại trà cho mọi query production.

## 3. Đọc phần đầu, bảng operator và phần tổng kết

Một query plan thường có ba phần.

| Phần | Nội dung cần xem |
| --- | --- |
| Header | Phiên bản Cypher, planner, runtime, batch size nếu có |
| Operator table | Cây operator, chi tiết từng bước và số liệu ước lượng/thực tế |
| Footer | Tổng DB Hits và một số tổng hợp như peak allocated memory hoặc thông tin worker |

Header giúp xác định bối cảnh của plan. Hai query plan chạy bằng runtime khác nhau có thể có cách trình bày số liệu khác nhau.

Operator table là phần quan trọng nhất khi chẩn đoán. Cột `Details` cho biết operator đang thao tác trên biến, label, relationship pattern hoặc predicate nào.

Footer cung cấp số tổng quan. Với `EXPLAIN`, tổng DB Hits chưa có nên thường hiển thị dấu hỏi. Với `PROFILE`, Neo4j báo tổng số lần truy cập database mà các operator đã thực hiện; nếu có operator không đo được đầy đủ, tổng có thể biểu diễn dưới dạng một giá trị tối thiểu cộng phần chưa xác định.

## 4. Đọc cây operator từ dưới lên trên

Query plan được trình bày như một cây. Operator ở dưới là leaf operator, thường là nơi bắt đầu truy xuất dữ liệu. Dữ liệu đi từ các operator con lên operator cha, cuối cùng tới root operator như `ProduceResults`.

Ví dụ cấu trúc đơn giản:

```text
ProduceResults
└── Filter
    └── Expand(All)
        └── NodeIndexSeek
```

Đọc theo luồng dữ liệu:

1. `NodeIndexSeek` tìm node bắt đầu bằng index.
2. `Expand(All)` đi theo relationship từ node tìm được.
3. `Filter` kiểm tra điều kiện trên các hàng đã mở rộng.
4. `ProduceResults` tạo kết quả gửi cho client.

Nếu một operator có hai nhánh con, chẳng hạn `Apply`, `Join` hoặc `CartesianProduct`, hãy xem cả hai nhánh và cách operator kết hợp chúng. Với nhóm operator kiểu `Apply`, một nhánh có thể được thực thi lặp lại theo từng hàng của nhánh còn lại. Một nhánh có ít hàng đầu vào nhưng nhánh con được gọi hàng nghìn lần vẫn có thể tạo ra chi phí lớn.

Không đọc bảng từ trên xuống theo thứ tự dòng. Hãy lần từ leaf operator lên root để hiểu dữ liệu được tìm, mở rộng, lọc và biến đổi như thế nào.

## 5. Estimated Rows và Rows: ước lượng so với thực tế

Đây là cặp số liệu quan trọng nhất khi tìm vấn đề về cardinality.

- `Estimated Rows` là số hàng planner dự đoán operator sẽ tạo ra.
- `Rows` là số hàng operator thực sự tạo ra khi query được PROFILE.

Planner ước lượng dựa trên thống kê label/index và mô hình selectivity. Nó không biết trước kết quả runtime của từng query, vì vậy ước lượng có thể sai khi dữ liệu lệch phân bố, quan hệ có độ kết nối không đồng đều hoặc predicate có tương quan mà mô hình không nắm bắt tốt.

Ví dụ bảng minh họa dưới đây dùng số giả định để giải thích cách đọc, không phải kết quả benchmark:

| Operator | Estimated Rows | Rows | Nhận xét |
| --- | ---: | ---: | --- |
| `NodeIndexSeek` | 1 | 1 | Điểm bắt đầu được ước lượng đúng |
| `Expand(All)` | 2 | 240 | Fan-out thực tế lớn hơn nhiều so với dự đoán |
| `Filter` | 1 | 18 | Bộ lọc giảm 240 hàng xuống còn 18 |
| `ProduceResults` | 1 | 18 | Query trả 18 hàng |

Chênh lệch lớn tại `Expand(All)` cho thấy planner đánh giá thấp số relationship hoặc số node được mở rộng. Điều này có thể khiến planner chọn thứ tự join hoặc điểm bắt đầu không phù hợp cho các phần tiếp theo của query.

Một cách đọc thực tế:

- Nếu Estimated Rows và Rows gần nhau ở các operator quan trọng, ước lượng cardinality tương đối sát.
- Nếu Rows lớn hơn nhiều, query có thể đang tạo nhiều hàng trung gian hơn dự kiến.
- Nếu Rows nhỏ hơn nhiều, predicate có thể chọn lọc mạnh hơn dự kiến hoặc dữ liệu có phân bố khác thống kê.
- Nếu sai lệch bắt đầu ở một operator cụ thể, hãy kiểm tra pattern và predicate tại đó trước khi sửa phần còn lại.

Không có một ngưỡng sai lệch cố định cho mọi query. Hãy quan tâm đến sai lệch có làm tăng công việc downstream, số lần mở rộng hoặc chi phí sort/aggregation hay không.

## 6. DB Hits: lượng công việc storage engine

`DB Hits` là đơn vị trừu tượng biểu diễn công việc mà operator yêu cầu storage engine thực hiện, chẳng hạn đọc entity, đọc property hoặc truy cập index entry.

Cần phân biệt:

- DB Hits không phải số hàng trả về.
- DB Hits không phải số network round-trip giữa ứng dụng và Neo4j.
- DB Hits không phải số lần đọc đĩa vật lý.
- Một hàng kết quả có thể cần nhiều DB Hits để tìm node, đọc property và kiểm tra relationship.
- Một operator trả nhiều hàng chưa chắc có DB Hits cao nếu dữ liệu được xử lý từ đầu vào đã có.

Khi PROFILE, hãy xem DB Hits theo từng operator và tổng ở footer. Một operator có nhiều DB Hits thường là nơi đáng kiểm tra, nhưng phải đọc cùng số hàng và vai trò của nó. Ví dụ một `NodeIndexSeek` có DB Hits nhỏ để tìm node ban đầu có thể là lựa chọn tốt; một `Expand(All)` chạy lặp lại trên hàng nghìn node có thể tạo phần lớn công việc storage.

Không kết luận query chậm chỉ vì DB Hits cao. Nếu dữ liệu lớn và query phải đọc nhiều node để tạo kết quả đầy đủ, số DB Hits có thể là hệ quả của yêu cầu nghiệp vụ. Hãy so sánh với query tương đương, dữ liệu tương đương và kết quả mong muốn.

## 7. Memory, Page Cache và Time

### 7.1. Memory (Bytes)

Cột `Memory (Bytes)` cho biết peak heap memory được dùng bởi một operator khi PROFILE. Nó đặc biệt hữu ích với các operator cần giữ dữ liệu trung gian như:

- `Sort`: cần giữ dữ liệu để sắp xếp.
- `Distinct`: cần theo dõi giá trị đã thấy.
- `Aggregation`: cần gom nhóm và giữ trạng thái tổng hợp.
- Các operator eager: cần buffer dữ liệu đầu vào trước khi phát kết quả.

Số memory của từng operator là peak theo operator, không phải một phần cộng dồn độc lập để cộng tất cả lại. Footer có thể cung cấp tổng peak memory của query; không cộng các giá trị operator một cách máy móc để suy ra tổng bộ nhớ.

### 7.2. Page Cache Hits/Misses

Page cache giữ các page dữ liệu/index trong bộ nhớ để giảm truy cập storage bên dưới.

- Hit: page cần đọc đã có trong page cache.
- Miss: page cần đọc chưa có trong cache và phải được nạp.

Một lần chạy đầu có thể có nhiều miss hơn; những lần sau có thể có nhiều hit hơn do cache đã nóng. Vì vậy, không so sánh hai lần PROFILE nếu một lần chạy với cache lạnh và lần còn lại với cache nóng mà không ghi nhận khác biệt này.

Cột page cache có thể phụ thuộc edition; tài liệu hiện hành ghi nhận số liệu này cho Enterprise Edition. Khi không có cột, không suy ra rằng query không truy cập page cache.

### 7.3. Time (ms)

Một số runtime hiển thị `Time (ms)`. Với pipelined hoặc parallel runtime, các operator có thể được fused thành pipeline. Khi đó thời gian được báo theo pipeline, không nhất thiết là thời gian riêng biệt của từng operator. Trong parallel runtime, thời gian có thể là tổng thời gian của các worker.

Không cộng các ô Time hoặc xem một dòng có số lớn là operator duy nhất chịu trách nhiệm. Hãy đọc cột Pipeline và hiểu phạm vi số liệu trước khi kết luận.

Thời gian PROFILE cũng không phải benchmark hoàn hảo. Nó chịu ảnh hưởng bởi cache, tải hệ thống, warm-up, JIT/runtime và overhead đo lường.

## 8. Nhận diện các operator thường gặp

| Operator | Ý nghĩa | Điều cần kiểm tra |
| --- | --- | --- |
| `NodeIndexSeek` | Tìm node qua index theo predicate | Index có phù hợp và đủ chọn lọc không? |
| `NodeIndexScan` | Quét entry của index | Query có thể dùng seek chọn lọc hơn không? |
| `NodeByLabelScan` | Quét các node mang label | Label có ít node hay đang tạo tập ứng viên quá lớn? |
| `AllNodesScan` | Quét toàn bộ node | Có thiếu label hoặc predicate để thu hẹp điểm bắt đầu không? |
| `Expand(All)` | Mở rộng relationship để tìm node kế tiếp | Degree/fan-out có lớn không? Có mở rộng lặp nhiều lần không? |
| `Expand(Into)` | Kiểm tra quan hệ giữa các node đã có binding | Có đang kiểm tra nhiều cặp node không cần thiết không? |
| `Filter` | Lọc hàng theo điều kiện | Có thể đẩy điều kiện vào index seek hoặc pattern sớm hơn không? |
| `Sort` | Sắp xếp hàng | Có sort tập dữ liệu lớn không? Có thể giới hạn hoặc tận dụng thứ tự index không? |
| `Top` / `Limit` | Giới hạn số hàng | Giới hạn có được áp dụng đủ sớm không? |
| `Distinct` | Loại hàng trùng | Vì sao query tạo duplicate; có thể tránh mở rộng thừa không? |
| `Aggregation` | Gom nhóm và tính aggregate | Số hàng đầu vào và memory có quá lớn không? |
| `Eager` | Buffer dữ liệu trước khi tiếp tục | Vì sao planner cần eager barrier và lượng dữ liệu phải buffer là bao nhiêu? |
| `CartesianProduct` | Kết hợp mọi hàng của hai nhánh đầu vào | Query có pattern rời rạc hoặc thiếu điều kiện liên kết không? |
| `ProduceResults` | Chuẩn bị hàng kết quả cuối | Có trả quá nhiều property hoặc dữ liệu không cần thiết không? |

Không có operator nào luôn tốt hoặc luôn xấu. Ví dụ `NodeByLabelScan` có thể hợp lý nếu label chỉ chứa vài node; `NodeIndexSeek` có thể vẫn đắt nếu predicate trả về phần lớn graph. Hãy đọc operator cùng Estimated Rows, Rows và DB Hits.

## 9. Ví dụ: từ label scan đến index seek

Giả sử ứng dụng tìm người theo email:

```cypher
MATCH (p:Person)
WHERE p.email = $email
RETURN p
```

Nếu chưa có index phù hợp, một plan có thể dùng `NodeByLabelScan` rồi `Filter`. Neo4j phải xem xét các node có label `Person` trước khi giữ lại node có email phù hợp.

Nếu truy vấn này phổ biến và email có độ chọn lọc cao, có thể tạo index:

```cypher
CREATE INDEX person_email_idx
IF NOT EXISTS
FOR (p:Person)
ON (p.email)
```

Sau khi index ở trạng thái `ONLINE`, chạy lại `EXPLAIN`:

```cypher
EXPLAIN
MATCH (p:Person)
WHERE p.email = $email
RETURN p
```

Planner có thể chọn `NodeIndexSeek` thay cho label scan. Đây là dấu hiệu tốt nếu query thực sự tìm được ít node từ index.

Tiếp theo chạy `PROFILE` trong môi trường phù hợp:

```cypher
PROFILE
MATCH (p:Person)
WHERE p.email = $email
RETURN p
```

So sánh:

- Operator truy xuất đầu tiên.
- Estimated Rows và Rows tại điểm bắt đầu.
- Tổng DB Hits.
- Số hàng đi qua các operator phía trên.
- Memory và thời gian nếu có.

Index không đảm bảo query luôn nhanh hơn. Nếu dữ liệu nhỏ hoặc predicate trả về hầu hết node, planner có thể chọn scan vì chi phí ước lượng thấp hơn. Hãy dùng query plan và dữ liệu thực tế để xác nhận.

## 10. Ví dụ: fan-out lớn khi mở rộng relationship

Giả sử tìm bạn bè của một người:

```cypher
MATCH (p:Person {id: $personId})-[:FOLLOWS]->(friend:Person)
WHERE friend.active = true
RETURN friend.id, friend.name
```

Plan có thể gồm:

```text
ProduceResults
└── Filter
    └── Expand(All)
        └── NodeIndexSeek
```

Điểm bắt đầu có thể tìm nhanh bằng index trên `Person.id`, nhưng node đó có thể có hàng trăm nghìn relationship `FOLLOWS`. Khi đó `Expand(All)` tạo rất nhiều hàng rồi `Filter` mới loại các người không active.

Hãy xem:

- Rows đầu ra của `Expand(All)`.
- DB Hits tại operator mở rộng.
- Chênh lệch Estimated Rows và Rows.
- Có thể giới hạn pattern, hướng relationship hoặc thêm điều kiện vào điểm bắt đầu không.
- Có cần một property/label/index bổ sung để bắt đầu từ tập node phù hợp hơn không.

Không phải lúc nào cũng có thể đẩy predicate trên node đích vào index seek của node nguồn. Nếu điều kiện nghiệp vụ chỉ áp dụng sau khi traverse, cần xem xét lại mô hình graph, hướng truy vấn, relationship type và mức độ fan-out.

Với variable-length path, hãy đặc biệt cẩn thận với độ dài không giới hạn. Số đường đi có thể tăng nhanh theo branching factor. Dùng giới hạn độ dài hoặc mô hình truy vấn khác khi nghiệp vụ cho phép.

## 11. Nhận biết Sort, Eager và CartesianProduct

### Sort và Eager

Một query như:

```cypher
MATCH (p:Person)
RETURN p.name
ORDER BY p.name
```

có thể cần `Sort` nếu plan không thể tận dụng thứ tự có sẵn. Khi số hàng lớn, sort cần memory để giữ dữ liệu. Nếu chỉ cần top 20 kết quả, query có thể được viết với `ORDER BY ... LIMIT 20` để planner cân nhắc operator `Top` và giảm công việc.

`Eager` xuất hiện khi Neo4j cần materialize một tập dữ liệu trước khi tiếp tục, chẳng hạn để bảo đảm đúng ngữ nghĩa khi query vừa đọc vừa ghi dữ liệu có liên quan. Eager không mặc nhiên là lỗi, nhưng cần xem lý do trong Details và số hàng đang được buffer.

### CartesianProduct

Ví dụ query có hai pattern độc lập:

```cypher
MATCH (p:Person), (d:Department)
RETURN p, d
```

Nếu có 1.000 Person và 100 Department, Cartesian product có thể tạo 100.000 cặp. Nếu nghiệp vụ không cần mọi cặp kết hợp, hãy bổ sung pattern relationship hoặc điều kiện nối đúng domain:

```cypher
MATCH (p:Person)-[:MEMBER_OF]->(d:Department)
RETURN p, d
```

Nếu Cartesian product là chủ đích, hãy xác nhận số hàng hai nhánh đủ nhỏ và kết quả thực sự cần tổ hợp đó.

## 12. Lấy Cypher thực tế từ Spring Data Neo4j

Khi dùng SDN, câu lệnh cần PROFILE phải đúng với query mà ứng dụng gửi. Derived query có thể sinh Cypher phức tạp hơn tên method; mapping graph, projection, pagination và các relationship fetch đều có thể ảnh hưởng đến câu lệnh.

Có thể bật logger của SDN để xem các statement được gọi và các notification từ server. Từ SDN 7.1.5, logger `org.springframework.data.neo4j.cypher` bao gồm các statement do SDN gọi cùng notification. Có các logger con để phân loại performance, hint, deprecation và các loại notification khác.

Ví dụ cấu hình logging:

```yaml
logging:
  level:
    org.springframework.data.neo4j.cypher: DEBUG
    org.springframework.data.neo4j.cypher.performance: INFO
```

Tùy logging backend và cấu hình ứng dụng, điều chỉnh mức log cho phù hợp. Không bật log quá chi tiết lâu dài nếu nó làm lộ dữ liệu nhạy cảm hoặc tạo lượng log lớn.

Với derived query, repository có thể chỉ khai báo method:

```java
import java.util.List;

import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface PersonRepository
        extends Neo4jRepository<Person, String> {

    List<Person> findAllByEmail(String email);
}
```

Để kiểm tra query này:

1. Gọi method trong môi trường dev/test và lấy statement từ log SDN.
2. Giữ nguyên cấu trúc Cypher và tên parameter mà SDN đã sinh.
3. Đặt giá trị parameter tương ứng trong Neo4j Browser hoặc công cụ Cypher tương ứng. Ví dụ Browser hỗ trợ khai báo parameter bằng `:param email => 'alice@example.com'`; tên thực tế phải khớp query đã lấy từ log.
4. Chạy `EXPLAIN` trước để xem plan dự kiến.
5. Chạy `PROFILE` nếu cần số liệu thực tế và query an toàn để thực thi.
6. So sánh kết quả với plan của query trước khi thay đổi.

Với custom `@Query`, áp dụng cùng quy trình: lấy statement đã gửi, giữ nguyên tên parameter và chạy `EXPLAIN`/`PROFILE` bên ngoài repository trong môi trường phù hợp.

Không thay giá trị parameter bằng cách nối chuỗi vào Cypher. Dùng parameter giữ query shape ổn định và tránh đưa dữ liệu đầu vào thành cú pháp query.

## 13. Quy trình phân tích một query chậm

Có thể dùng quy trình sau cho derived query, `@Query`, `Neo4jClient` hoặc `Neo4jTemplate`.

1. **Xác định query thật:** lấy Cypher và tên parameter mà SDN gửi.
2. **Tái tạo workload:** dùng cùng database, cùng dữ liệu đại diện và giá trị parameter tương tự production.
3. **Chạy EXPLAIN:** xem planner bắt đầu từ đâu, có dùng index không và các operator dự kiến.
4. **Đọc bottom-up:** lần từ leaf operator lên root để hiểu dữ liệu được tìm và mở rộng.
5. **Chạy PROFILE an toàn:** lấy Rows, DB Hits, memory, page cache và thời gian nếu runtime cung cấp.
6. **Tìm điểm sai lệch:** so Estimated Rows với Rows ở từng operator; chú ý nơi cardinality tăng mạnh.
7. **Xác định công việc đắt:** scan, expand, filter, sort, eager hoặc Cartesian product.
8. **Thử một thay đổi:** ví dụ tạo index, thu hẹp pattern, thêm điều kiện chọn lọc, giới hạn variable-length traversal hoặc giảm dữ liệu trả về.
9. **Đo lại:** dùng cùng query, parameter và dữ liệu để so sánh.
10. **Kiểm tra kết quả nghiệp vụ:** xác nhận query mới vẫn trả đúng dữ liệu và không làm thay đổi semantics.

Không sửa nhiều yếu tố cùng lúc. Nếu đồng thời thay index, query pattern và dữ liệu, bạn sẽ khó xác định thay đổi nào thực sự tạo ra cải thiện.

## 14. So sánh trước và sau khi tối ưu

Khi đánh giá một thay đổi, nên ghi lại các thông tin theo cùng một bộ điều kiện:

| Chỉ số | Trước | Sau | Cách diễn giải |
| --- | --- | --- | --- |
| Operator bắt đầu | Label scan | Index seek | Có thể giảm tập node ban đầu |
| Estimated Rows | Ghi từ plan | Ghi từ plan mới | Planner đang ước lượng cardinality ra sao |
| Rows | Ghi từ PROFILE | Ghi từ PROFILE mới | Query thực sự xử lý bao nhiêu hàng |
| DB Hits | Tổng và operator chính | Tổng và operator chính | Công việc storage engine thay đổi thế nào |
| Memory | Peak theo operator/query | Peak theo operator/query mới | Sort/aggregation/buffer có giảm không |
| Page cache | Hits/misses | Hits/misses | So sánh chỉ khi trạng thái cache tương đồng |
| Time | Ghi cùng điều kiện chạy | Ghi cùng điều kiện chạy | Thời gian quan sát được, cần nhiều lần đo |
| Kết quả | Số hàng và nội dung | Số hàng và nội dung mới | Bảo đảm semantics không đổi |

Để so sánh đáng tin cậy:

- Dùng cùng database snapshot hoặc dataset không thay đổi giữa hai lần đo.
- Dùng cùng parameter và kiểu dữ liệu parameter.
- Ghi nhận trạng thái cache nóng/lạnh.
- Chạy đủ lần để tránh kết luận từ một lần đo ngẫu nhiên.
- Không so sánh thời gian giữa môi trường có cấu hình CPU, memory hoặc tải khác nhau như thể đó là benchmark trực tiếp.
- Kiểm tra cả số hàng trả về và nội dung kết quả, không chỉ nhìn thời gian.

## 15. Các lỗi diễn giải thường gặp

| Nhầm lẫn | Thực tế | Cách đọc đúng |
| --- | --- | --- |
| Estimated Rows là số hàng query đã trả | Đây là ước lượng của planner | So với Rows trong PROFILE |
| Rows nhỏ nghĩa là query rẻ | Operator có thể đã đọc nhiều dữ liệu để tạo ít hàng | Xem DB Hits và operator phía dưới |
| DB Hits là số lần đọc đĩa | Đây là đơn vị công việc storage engine | Dùng page-cache metrics và hệ thống monitoring để hiểu I/O |
| Index seek luôn nhanh | Index có thể trả về quá nhiều candidate | Kiểm tra độ chọn lọc và số hàng thực tế |
| Label scan luôn xấu | Scan label nhỏ có thể hợp lý | Đánh giá cardinality và DB Hits |
| Dòng Time lớn nhất là operator chậm nhất | Runtime có thể gộp số liệu theo pipeline | Xem cột Pipeline và runtime |
| Cộng Memory của mọi operator là tổng memory query | Memory mỗi operator là peak riêng | Dùng query-wide peak ở footer nếu có |
| PROFILE chỉ đọc dữ liệu | PROFILE thực thi cả query ghi | Dùng môi trường an toàn và kiểm tra câu lệnh trước |
| EXPLAIN chứng minh query chạy nhanh | EXPLAIN không thực thi query | Dùng PROFILE và benchmark workload |
| Chỉ nhìn tổng DB Hits là đủ | Một operator cụ thể có thể là nút thắt | Đọc số liệu theo operator từ dưới lên |
| Query plan giống nhau nghĩa hiệu năng giống nhau | Cache, dữ liệu và tải hệ thống vẫn ảnh hưởng | Đo trong điều kiện tương đồng |

## 16. Câu hỏi tự kiểm tra

1. `EXPLAIN` và `PROFILE` khác nhau ở điểm nào?
2. Vì sao `PROFILE` có thể làm thay đổi dữ liệu?
3. Query plan được đọc theo hướng nào?
4. `Estimated Rows` được planner dùng vào việc gì?
5. `Rows` trong PROFILE cho biết điều gì?
6. Vì sao Estimated Rows chênh lệch lớn với Rows có thể dẫn tới kế hoạch kém?
7. DB Hits có phải số lần đọc đĩa hoặc số network round-trip không?
8. Page Cache Hits/Misses cho biết điều gì và có giới hạn edition nào?
9. Vì sao không cộng Memory của tất cả operator để suy ra tổng peak?
10. Khi nào `NodeByLabelScan` vẫn có thể là lựa chọn hợp lý?
11. `Expand(All)` có thể trở thành nút thắt trong trường hợp nào?
12. Vì sao `CartesianProduct` thường là dấu hiệu cần kiểm tra query pattern?
13. `Sort` và `Top` khác nhau như thế nào khi query có `ORDER BY` và `LIMIT`?
14. Làm thế nào lấy Cypher thực tế từ một derived query của SDN?
15. Khi so sánh hai PROFILE, cần giữ những điều kiện nào giống nhau?

## Tài liệu tham khảo

- [Neo4j Cypher Manual – Understanding query plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/)
- [Neo4j Cypher Manual – Execution plan operators in detail](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/operators/operators-detail/)
- [Neo4j Cypher Manual – Query tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)
- [Neo4j Cypher Manual – Query caches](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/caching/)
- [Spring Data Neo4j – Logging](https://docs.spring.io/spring-data/neo4j/reference/appendix/logging.html)

## Kết luận

`EXPLAIN` cho biết kế hoạch Neo4j dự kiến sử dụng và số hàng planner ước lượng; nó không chạy query. `PROFILE` thực thi query và cung cấp số hàng thực tế, DB Hits cùng các số liệu runtime khác. Vì PROFILE có thể chạy cả câu lệnh ghi, hãy kiểm tra query trước và dùng môi trường an toàn.

Khi đọc plan, đi từ leaf operator dưới cùng lên root, so sánh Estimated Rows với Rows và xác định nơi cardinality tăng mạnh. Đọc DB Hits cùng số hàng, memory, page cache và pipeline time để hiểu chi phí thật. Trong SDN, hãy lấy đúng Cypher do repository/client gửi, giữ nguyên parameter và đo lại sau mỗi thay đổi. Query plan là công cụ chẩn đoán; kết luận tối ưu cần được xác nhận bằng dữ liệu đại diện, kết quả đúng và các lần đo trong điều kiện tương đồng.
