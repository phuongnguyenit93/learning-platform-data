# Phân chia truy vấn phức tạp thành các khối có thể kiểm chứng

## 1. Vì sao cần chia nhỏ truy vấn Cypher?

Trong Neo4j, dữ liệu được biểu diễn bằng **property graph**: các node mang nhãn và thuộc tính, còn relationship thể hiện liên kết có hướng giữa các node. Cypher cho phép đi qua nhiều loại quan hệ, lọc, tổng hợp và trả kết quả trong một truy vấn. Khi yêu cầu nghiệp vụ gồm nhiều phép tính độc lập, một câu lệnh dài dễ gây ra ba vấn đề:

- **Khó kiểm tra tính đúng đắn:** không biết số liệu sai từ bước tìm node, bước mở rộng quan hệ hay bước tổng hợp.
- **Nhân số dòng ngoài ý muốn:** ghép nhiều nhánh quan hệ một-nhiều có thể tạo tích số dòng, làm sai `count()`, `sum()`, `avg()`.
- **Khó kiểm soát phạm vi biến và chi phí:** một phép lọc hoặc phép tổng hợp đặt sai vị trí có thể thay đổi tập kết quả và số dòng phải xử lý.

**Truy vấn con (subquery)**, đặc biệt `CALL { ... }` và biến thể khai báo phạm vi `CALL (p) { ... }`, giúp tách truy vấn thành những khối có hợp đồng rõ ràng: nhận đầu vào gì, tạo đầu ra gì và tạo bao nhiêu dòng. Mục tiêu của bài này là hình thành quy trình *viết một khối → chạy riêng → so với kết quả kỳ vọng → ghép các khối → kiểm chứng toàn bộ*.

Sau bài học, bạn có thể:

1. Chỉ ra nguyên nhân làm sai thống kê khi hai nhánh quan hệ độc lập được `MATCH` trong cùng luồng dòng.
2. Thiết kế truy vấn con trả đúng một dòng trên mỗi node đầu vào và xác minh được cả trường hợp không có quan hệ.
3. Ghép các khối truy vấn, giữ rõ phạm vi biến, rồi dùng `EXPLAIN`/`PROFILE` để kiểm tra hiệu năng.

## 2. Bài toán minh họa và dữ liệu kiểm thử

Giả sử một hệ thống phim cần thống kê, với **mỗi người**, số phim họ tham gia diễn xuất và số phim họ đạo diễn từ năm 2020 trở đi. Hệ thống cũng cần danh sách tựa phim họ diễn xuất và chỉ chọn những người có ít nhất hai phim diễn xuất trong giai đoạn này.

Mô hình đơn giản:

```text
(:SQ007Person {id, name})
       | \
       |  \--[:SQ007_DIRECTED]--> (:SQ007Film {id, title, year})
       |
       +-----[:SQ007_ACTED_IN]--> (:SQ007Film {id, title, year})
```

Các nhãn và loại quan hệ có tiền tố `SQ007` chỉ phục vụ ví dụ, giúp hạn chế trùng với dữ liệu có sẵn. Chạy đoạn Cypher dưới đây trong cơ sở dữ liệu thực hành để tạo bộ dữ liệu nhỏ; `MERGE` giúp có thể chạy lại mà không tự tạo thêm quan hệ giống hệt.

```cypher
MERGE (an:SQ007Person {id: 'an'})
SET an.name = 'An'
MERGE (binh:SQ007Person {id: 'binh'})
SET binh.name = 'Bình'
MERGE (chi:SQ007Person {id: 'chi'})
SET chi.name = 'Chi'
MERGE (dung:SQ007Person {id: 'dung'})
SET dung.name = 'Dũng'

MERGE (alpha:SQ007Film {id: 'alpha'})
SET alpha.title = 'Alpha', alpha.year = 2021
MERGE (beta:SQ007Film {id: 'beta'})
SET beta.title = 'Beta', beta.year = 2023
MERGE (legacy:SQ007Film {id: 'legacy'})
SET legacy.title = 'Legacy', legacy.year = 2018
MERGE (delta:SQ007Film {id: 'delta'})
SET delta.title = 'Delta', delta.year = 2024

MERGE (an)-[:SQ007_ACTED_IN]->(alpha)
MERGE (an)-[:SQ007_ACTED_IN]->(beta)
MERGE (an)-[:SQ007_ACTED_IN]->(legacy)
MERGE (binh)-[:SQ007_ACTED_IN]->(beta)
MERGE (binh)-[:SQ007_ACTED_IN]->(delta)
MERGE (chi)-[:SQ007_ACTED_IN]->(legacy)

MERGE (an)-[:SQ007_DIRECTED]->(alpha)
MERGE (binh)-[:SQ007_DIRECTED]->(beta)
MERGE (binh)-[:SQ007_DIRECTED]->(delta)
MERGE (chi)-[:SQ007_DIRECTED]->(delta);
```

Kết quả cần đạt cho mốc năm `2020`:

| Người | Phim diễn xuất từ 2020 | Phim đạo diễn từ 2020 | Ghi chú |
|---|---:|---:|---|
| An | 2 | 1 | `Legacy` (2018) không được tính |
| Bình | 2 | 2 | Có hai nhánh quan hệ với hai phim mỗi nhánh |
| Chi | 0 | 1 | Chỉ diễn xuất trong phim năm 2018 |
| Dũng | 0 | 0 | Không có quan hệ nào |

**Quan trọng:** cả Chi và Dũng vẫn phải xuất hiện khi thống kê cho *mọi người*. Khi áp bộ lọc "ít nhất hai phim diễn xuất", chỉ An và Bình còn lại.

## 3. Nhận diện lỗi: hai nhánh `OPTIONAL MATCH` làm nhân dòng

Một cách viết tưởng như hợp lý:

```cypher
MATCH (p:SQ007Person)
OPTIONAL MATCH (p)-[:SQ007_ACTED_IN]->(acted:SQ007Film)
WHERE acted.year >= 2020
OPTIONAL MATCH (p)-[:SQ007_DIRECTED]->(directed:SQ007Film)
WHERE directed.year >= 2020
RETURN p.id AS personId,
       count(acted) AS actedCount,
       count(directed) AS directedCount
ORDER BY personId;
```

Với Bình, hai phim diễn xuất kết hợp với hai phim đạo diễn tạo **4 dòng** trước khi tổng hợp: `(Beta, Beta)`, `(Beta, Delta)`, `(Delta, Beta)`, `(Delta, Delta)`. Vì vậy truy vấn trên trả `actedCount = 4` và `directedCount = 4` cho Bình, trong khi đúng là `2` và `2`. Tương tự, An bị đếm `directedCount = 2` thay vì `1`.

Có thể dùng `count(DISTINCT acted)` và `count(DISTINCT directed)` để sửa **hai phép đếm node cụ thể này**, nhưng đó chưa phải giải pháp tổng quát. Chẳng hạn `sum(acted.revenue)` vẫn có thể cộng lặp khi cùng phim diễn xuất kết hợp với nhiều phim đạo diễn. Cách dễ kiểm chứng hơn là **tổng hợp từng nhánh trước khi ghép**.

## 4. Đặt hợp đồng đầu vào và đầu ra cho từng khối

Hãy mô tả từng khối trước khi viết mã:

| Khối | Đầu vào | Đầu ra | Số dòng mong muốn |
|---|---|---|---|
| Gốc | Nhãn `SQ007Person` | `p` | Một dòng trên mỗi người |
| A: diễn xuất | Một `p` | `actedCount`, `actedTitles` | **Đúng một dòng trên mỗi `p`** |
| B: đạo diễn | Một `p` | `directedCount` | **Đúng một dòng trên mỗi `p`** |
| Kết hợp | `p` và ba giá trị thống kê | Dòng kết quả người | Một dòng trên mỗi `p` |
| Lọc cuối | `actedCount` | Chỉ người có ít nhất hai phim | Có thể bớt dòng, theo yêu cầu |

Điểm mấu chốt là hai khối A và B phải trả **một dòng ngay cả khi không có phim phù hợp**. Để làm được vậy, mỗi khối dùng các hàm tổng hợp `count()` và `collect()` **mà không nhóm theo thuộc tính của phim**. Với tập `MATCH` rỗng, `count()` trả `0` và `collect()` trả `[]`.

### 4.1. Kiểm tra riêng khối A — diễn xuất

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS actedCount,
         collect(DISTINCT m.title) AS actedTitles
}
RETURN p.id AS personId, actedCount, actedTitles
ORDER BY personId;
```

Kết quả kỳ vọng: `an = 2` với tựa `Alpha`, `Beta`; `binh = 2` với `Beta`, `Delta`; `chi = 0`, `dung = 0` và cả hai có danh sách rỗng `[]`. **Thứ tự phần tử của `collect()` không được bảo đảm** nếu không sắp xếp tường minh; hãy kiểm tra nội dung danh sách thay vì mặc định thứ tự.

Điều cần kiểm chứng ngay tại đây: câu truy vấn trả **bốn dòng**, mỗi `personId` xuất hiện đúng một lần. Nếu một người xuất hiện nhiều dòng, khối A chưa đạt hợp đồng và không nên ghép tiếp.

### 4.2. Kiểm tra riêng khối B — đạo diễn

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_DIRECTED]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS directedCount
}
RETURN p.id AS personId, directedCount
ORDER BY personId;
```

Kỳ vọng: `an = 1`, `binh = 2`, `chi = 1`, `dung = 0`; vẫn là **bốn dòng**. Như vậy khối B được kiểm chứng độc lập trước khi kết hợp với A.

### 4.3. Ghép hai khối đã kiểm chứng

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS actedCount,
         collect(DISTINCT m.title) AS actedTitles
}
CALL {
  WITH p
  MATCH (p)-[:SQ007_DIRECTED]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS directedCount
}
RETURN p.id AS personId,
       p.name AS personName,
       actedCount,
       directedCount,
       actedTitles
ORDER BY personId;
```

Mỗi `CALL` nhận người `p` do luồng bên ngoài cung cấp. Vì mỗi khối trả đúng một dòng, ghép hai khối **không làm nhân số dòng**. Truy vấn cuối trả bốn người với đúng số liệu ở bảng kỳ vọng.

Để áp yêu cầu *chỉ chọn người có ít nhất hai phim diễn xuất*, thay phần `RETURN` cuối bằng:

```cypher
WITH p, actedCount, directedCount, actedTitles
WHERE actedCount >= 2
RETURN p.id AS personId,
       p.name AS personName,
       actedCount,
       directedCount,
       actedTitles
ORDER BY personId;
```

Đoạn trên là **phần tiếp nối** của truy vấn đã ghép, không phải một câu lệnh độc lập: đặt ngay sau `CALL` thứ hai. Kết quả lúc này chỉ còn `an` và `binh`, mỗi người đúng một dòng.

## 5. Tự động kiểm chứng hợp đồng bằng truy vấn Cypher

Ngoài kiểm tra bằng mắt, có thể dùng một câu lệnh trả về giá trị Boolean để xác minh dữ liệu mẫu và hợp đồng hai khối:

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(a:SQ007Film)
  WHERE a.year >= 2020
  RETURN count(DISTINCT a) AS actedCount
}
CALL {
  WITH p
  MATCH (p)-[:SQ007_DIRECTED]->(d:SQ007Film)
  WHERE d.year >= 2020
  RETURN count(DISTINCT d) AS directedCount
}
WITH collect({
  id: p.id,
  acted: actedCount,
  directed: directedCount
}) AS actual
RETURN
  size(actual) = 4
  AND any(x IN actual WHERE x.id = 'an'   AND x.acted = 2 AND x.directed = 1)
  AND any(x IN actual WHERE x.id = 'binh' AND x.acted = 2 AND x.directed = 2)
  AND any(x IN actual WHERE x.id = 'chi'  AND x.acted = 0 AND x.directed = 1)
  AND any(x IN actual WHERE x.id = 'dung' AND x.acted = 0 AND x.directed = 0)
  AS passed;
```

`passed = true` nghĩa là phép kiểm tra dữ liệu mẫu đạt. Truy vấn này cố ý kiểm tra cả trường hợp có nhiều quan hệ lẫn trường hợp không có phim, vì chỉ kiểm tra người có dữ liệu rất dễ bỏ sót lỗi làm mất dòng.

Với dữ liệu thật, nên bổ sung các bất biến: số dòng trước và sau các khối tổng hợp bằng nhau; mỗi định danh đầu vào xuất hiện một lần; các giá trị đếm không âm; kết quả không phụ thuộc vào thứ tự `collect()` trừ khi đã sắp xếp.

## 6. Những điểm dễ sai khi viết truy vấn con

### 6.1. Truy vấn con có thể làm rơi dòng của truy vấn ngoài

Ví dụ dưới đây **không giữ người không có phim diễn xuất từ 2020**:

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN m.title AS title
}
RETURN p.id AS personId, title;
```

Khối này trả **một dòng cho mỗi phim** tìm được, hoặc **không dòng nào** nếu không tìm được phim. Vì vậy An và Bình xuất hiện nhiều lần, còn Chi và Dũng biến mất. Khác biệt không nằm ở `CALL` tự thân mà nằm ở **số dòng mà phần `RETURN` bên trong tạo ra**. Khi cần một dòng trên mỗi người, hãy tổng hợp như khối A/B hoặc thiết kế truy vấn con có cơ chế duy trì dòng phù hợp.

### 6.2. Phạm vi biến phải minh bạch

Trong cú pháp tương thích rộng:

```cypher
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  RETURN count(m) AS n
}
RETURN p.id, n;
```

`WITH p` đầu khối nhập biến `p` từ truy vấn ngoài vào truy vấn con. Chỉ các giá trị được xuất qua `RETURN` của truy vấn con mới có thể dùng sau `CALL` (ngoài các biến vốn có ở phạm vi ngoài). Tránh đặt tên đầu ra trùng với biến đã tồn tại ở phạm vi ngoài. Đặt `WITH` để giữ hoặc lọc biến giữa các bước khi cần.

Từ **Neo4j 5.23**, có thể dùng cú pháp khai báo phạm vi biến rõ ràng hơn:

```cypher
MATCH (p:SQ007Person)
CALL (p) {
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS n
}
RETURN p.id, n;
```

Cú pháp `CALL (p) { ... }` khai báo trực tiếp biến được nhập vào khối. Nếu đang học trên phiên bản Neo4j cũ hơn 5.23, dùng mẫu `CALL { WITH p ... }` trong các ví dụ chính của bài. Kiểm tra phiên bản Neo4j và Cypher được hệ thống của bạn hỗ trợ trước khi sao chép cú pháp mới.

### 6.3. Phân biệt giá trị đếm, số node khác nhau và tổng

- `count(*)` đếm số dòng khớp mẫu; `count(m)` đếm số giá trị `m` không null; `count(DISTINCT m)` đếm số node phim phân biệt.
- Khi có nhiều relationship đến cùng một phim, `count(m)` có thể lớn hơn số phim thực tế. Hãy định nghĩa rõ đang đếm *quan hệ*, *lần xuất hiện* hay *phim riêng biệt*.
- `collect()` gom giá trị thành danh sách; `collect(DISTINCT ...)` loại phần tử trùng nhau. `avg()` có thể trả `null` nếu không có dữ liệu, nên xử lý tường minh khi nghiệp vụ yêu cầu giá trị mặc định.
- Nếu tổng hợp theo thuộc tính của phim trong một khối (ví dụ `WITH m.year AS year, count(*) AS n`), khối có thể trả **nhiều dòng cho mỗi người**, phá vỡ hợp đồng một dòng. Chỉ thực hiện khi kết quả nhiều dòng là chủ đích.

### 6.4. Chọn loại subquery phù hợp với đầu ra

Ngoài `CALL` cho khối có nhiều cột đầu ra, Cypher còn có các dạng diễn đạt ý định trực tiếp (khả dụng tùy phiên bản):

```cypher
MATCH (p:SQ007Person)
RETURN p.id AS personId,
       EXISTS {
         MATCH (p)-[:SQ007_DIRECTED]->(m:SQ007Film)
         WHERE m.year >= 2020
       } AS hasRecentDirectedFilm,
       COUNT {
         MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
         WHERE m.year >= 2020
       } AS recentActingMatches,
       COLLECT {
         MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
         WHERE m.year >= 2020
         RETURN m.title
       } AS recentActingTitles
ORDER BY personId;
```

`EXISTS { ... }` trả Boolean, `COUNT { ... }` đếm số dòng khớp mẫu, `COLLECT { ... }` trả danh sách. `COUNT` và `COLLECT` subquery expression có từ Neo4j 5.6; không giả định mọi phiên bản đều hỗ trợ. Ở dữ liệu mẫu, các quan hệ diễn xuất không trùng nên số dòng khớp bằng số phim; khi có quan hệ trùng hoặc đường đi nhiều nhánh, phải xem lại đơn vị đếm. Dùng `CALL` khi cần một khối kiểm thử độc lập với nhiều phép tổng hợp; dùng expression subquery khi đầu ra phù hợp với giá trị đơn, Boolean hoặc danh sách.

## 7. Kiểm tra kế hoạch thực thi và hiệu năng

Một truy vấn dễ đọc vẫn cần chạy hiệu quả trên đồ thị lớn. Dùng:

```cypher
EXPLAIN
MATCH (p:SQ007Person)
CALL {
  WITH p
  MATCH (p)-[:SQ007_ACTED_IN]->(m:SQ007Film)
  WHERE m.year >= 2020
  RETURN count(DISTINCT m) AS actedCount
}
RETURN p.id, actedCount;
```

`EXPLAIN` hiển thị kế hoạch **mà không chạy truy vấn**. Khi có môi trường đo thích hợp, thay bằng `PROFILE` để xem dữ liệu thực thi như số dòng qua từng toán tử và số lần truy cập cơ sở dữ liệu (`DB Hits`). Đặc biệt quan sát nơi số dòng tăng mạnh sau các bước mở rộng quan hệ hoặc trước khi tổng hợp.

Để cải thiện hiệu năng:

1. Chọn tập node gốc có điều kiện lọc thích hợp trước khi gọi nhiều khối. Nếu lọc theo `id` hoặc thuộc tính thường xuyên, cân nhắc index/constraint phù hợp với schema thực tế.
2. Chỉ trả biến cần dùng từ mỗi khối; tổng hợp càng sớm càng tốt khi không cần giữ từng dòng quan hệ.
3. Đo từng khối riêng rồi đo bản ghép. Một truy vấn con chạy một lần trên **mỗi dòng đầu vào**, nên khối có chi phí nhỏ nhưng nhận quá nhiều dòng vẫn có thể tốn tài nguyên.
4. Đọc kế hoạch thực tế trước khi kết luận index sẽ được dùng; hướng duyệt quan hệ, độ chọn lọc và thống kê dữ liệu đều ảnh hưởng lựa chọn của bộ tối ưu.

## 8. Quy trình áp dụng cho truy vấn nghiệp vụ khác

Với một truy vấn Neo4j phức tạp, có thể áp dụng chu trình sau:

1. **Viết câu hỏi nghiệp vụ thành đầu ra kiểm chứng được.** Ví dụ: mỗi khách hàng có bao nhiêu đơn hàng, tổng tiền bao nhiêu, có ít nhất một đơn đang xử lý hay không.
2. **Xác định khóa và số dòng của luồng gốc.** Ví dụ một dòng cho mỗi `Customer`; ghi lại số lượng và một vài khách hàng không có đơn.
3. **Tách các nhánh quan hệ độc lập.** Mỗi nhánh như đơn hàng, địa chỉ, phiên thanh toán có đầu vào và đầu ra rõ ràng.
4. **Kiểm chứng từng nhánh bằng dữ liệu nhỏ.** So sánh số dòng, giá trị biên, trùng quan hệ, thuộc tính thiếu và các trường hợp không có kết quả.
5. **Ghép khối, rồi mới lọc theo kết quả tổng hợp.** Kiểm tra lại số dòng để tránh sai lệch do nhân dòng hoặc rơi dòng.
6. **Dùng `EXPLAIN`/`PROFILE` và đo trên dữ liệu đại diện.** Chọn cách viết vừa đúng kết quả vừa phù hợp chi phí.

### Bài tập thực hành

1. Thay mốc năm cố định bằng tham số `$fromYear` và truyền `2023`. Hãy dự đoán lại kết quả từng người trước khi chạy.
2. Bổ sung một relationship `SQ007_ACTED_IN` từ An đến một phim đã có qua một dữ liệu thử riêng; so sánh `count(m)` với `count(DISTINCT m)`. Giải thích vì sao hợp đồng cần quy định rõ đơn vị đếm.
3. Thêm yêu cầu "chỉ chọn người có ít nhất một phim đạo diễn từ năm 2020 và có ít nhất hai phim diễn xuất". Nên đặt điều kiện ở đâu để không làm thay đổi phép tổng hợp?

**Tiêu chí hoàn thành:** bạn chỉ ra được số dòng đầu vào/đầu ra của từng khối; hai truy vấn con A/B trả đúng kết quả cho cả bốn người, kể cả Dũng; câu kiểm tra tự động trả `true`; bản lọc cuối trả đúng hai người; và giải thích được vì sao truy vấn `OPTIONAL MATCH` ban đầu đếm sai.
