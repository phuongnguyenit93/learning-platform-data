# Bộ dữ liệu mẫu nhỏ thể hiện đầy đủ quan hệ và trường hợp biên trong Neo4j

Kiểm thử cơ sở dữ liệu đồ thị không thể chỉ tạo hai node rồi kiểm tra một relationship. Một truy vấn Cypher có thể đúng trên đường đi đơn giản nhưng sai khi có **hai đường tới cùng đích**, **relationship song song**, **chu trình**, **self-loop**, **node cô lập**, **thuộc tính thiếu**, hoặc hai tenant sử dụng **cùng một mã nghiệp vụ**. Những trường hợp đó tác động đến số hàng của `MATCH`, ngữ nghĩa `OPTIONAL MATCH`, `DISTINCT`, phép đếm, traversal, mapping Java và logic cập nhật.

Bài học thuộc chương **Kiểm thử** trong module `DATABASE_ENGINE_GRAPH_NEO4J`. Chúng ta thiết kế một **fixture** (bộ dữ liệu kiểm thử nhỏ, cố định) cho property graph Neo4j, mô tả kỳ vọng chính xác rồi sử dụng Cypher, Neo4j Java Driver và Spring Data Neo4j để xác minh kết quả. Fixture có thể được dựng lại trong database thử nghiệm, giúp phát hiện lỗi truy vấn trước khi tối ưu index, constraint hoặc triển khai hệ thống.

**Mục tiêu:** dữ liệu đủ nhỏ để con người đếm được bằng tay, nhưng đủ đa dạng để kiểm thử **node, relationship, hướng đi, nhiều mẫu kết hợp, đường đi, giá trị null/thiếu, tính đa tenant và điều kiện biên**.

## 1. Một fixture tốt phải chứng minh được điều gì?

Một tập dữ liệu kiểm thử hiệu quả có ba thuộc tính:

1. **Tính xác định:** biết trước số node, số relationship, từng khóa và từng kết quả cần trả. Không phụ thuộc dữ liệu cũ hoặc thứ tự duyệt ngẫu nhiên.
2. **Độ bao phủ có chủ đích:** mỗi trường hợp biên tồn tại vì có một truy vấn hoặc quy tắc cần kiểm tra, không phải thêm dữ liệu vô tội vạ.
3. **Cô lập và dễ dựng lại:** không làm thay đổi dữ liệu production, không để một test làm ô nhiễm test khác, không yêu cầu ID nội bộ của Neo4j giữ nguyên.

Ma trận bao phủ của bài:

| Trường hợp | Tác dụng kiểm thử | Dữ liệu minh họa |
| --- | --- | --- |
| Node bình thường và node có nhiều label | Lọc label, mapping entity | Bình có `Test001Person` và `Test001Mentor` |
| Relationship có hướng | Không nhầm chiều đi/chiều đến | An → Bình |
| Nhiều relationship cùng cặp node | `count(*)` khác `count(DISTINCT ...)` | Hai cạnh An → Bình |
| Hai đường đi đến một đích | Tránh nhân số node khi đếm path | An → Bình → Dũng và An → Chi → Dũng |
| Chu trình | Traversal có thể quay về điểm bắt đầu | An → Chi → An |
| Self-loop | Hệ thống không giả định hai đầu mút khác nhau | Dũng → Dũng |
| Node cô lập | Phát hiện lỗi `MATCH` bỏ sót node không có cạnh | Hạnh không có relationship nào |
| Hai loại relationship giữa các Person | Lọc theo type, không coi mọi cạnh như nhau | `FOLLOWS` và `MENTORS` |
| Relationship có thuộc tính | Lọc, đếm, test giá trị biên | `score = 0`; `score` vắng mặt |
| Property node thiếu, rỗng, bằng 0 | Phân biệt `IS NULL`, chuỗi rỗng và số không | Chi thiếu `email`, Hạnh `email = ''`, Dũng `age = 0` |
| Hai tenant có cùng ID | Kiểm thử khóa tổ hợp và cách ly dữ liệu | T1/P01 và T2/P01 |
| Đường không kết nối | Không tự suy ra reachability | T2 không có cạnh `FOLLOWS` sang T1 |

Không cần mô phỏng hàng triệu bản ghi để kiểm tra ngữ nghĩa. Dữ liệu lớn dành cho **kiểm thử hiệu năng**; fixture nhỏ phục vụ **kiểm thử tính đúng**.

## 2. Bài toán và đồ thị mục tiêu

Giả sử hệ thống có người học (`Person`), khóa học (`Course`), quan hệ theo dõi (`FOLLOWS`), cố vấn (`MENTORS`) và đăng ký học (`ENROLLED`). Mỗi thực thể thuộc một tenant.

Quy ước khóa nghiệp vụ:

- Person: `(tenantId, personId)`.
- Course: `(tenantId, courseId)`.
- Relationship `FOLLOWS` có thêm `edgeId` để phân biệt các cạnh song song trong fixture.
- Relationship `ENROLLED` có `status`, có thể có `score`; việc **không có score** khác với **score bằng 0**.

Sơ đồ lõi ở tenant T1:

```text
          ┌──────── FOLLOWS ─────────┐
          │                          ▼
An (P01) ──FOLLOWS×2──► Bình (P02) ──FOLLOWS──► Dũng (P04)
   │                         │                       ▲ │
   │                         └──FOLLOWS──► Chi (P03)│ │ SELF-LOOP
   └────FOLLOWS─────────────────────────► Chi ───────┘ │
                  ▲                      │              │
                  └──────── FOLLOWS ─────┘              └──► Dũng

Bình (P02) ──MENTORS──► An (P01) [type khác]

Hạnh (P05) [không có quan hệ]
```

Sơ đồ chỉ mang tính gợi nhớ; **danh sách cạnh có `edgeId` ở mục 3 mới là nguồn chuẩn**. Phần đăng ký khóa học:

```text
T1/An     ──ENROLLED──► T1/C101 (Neo4j)
          └─ENROLLED──► T1/C102 (Java Driver)
T1/Bình   ──ENROLLED──► T1/C101
T1/Chi    ──ENROLLED──► T1/C102 [WITHDRAWN, score = 0]
T1/Dũng   [không đăng ký]
T1/Hạnh   [cô lập]

T2/Eva (personId = P01) ──ENROLLED──► T2/C101
```

Đáng chú ý, **T1/P01 và T2/P01 đều hợp lệ** vì `personId` chỉ duy nhất **trong tenant**. Tương tự, T1/C101 và T2/C101 là hai khóa học khác nhau.

## 3. Tạo fixture bằng Cypher

**Chỉ chạy trên database kiểm thử riêng, tốt nhất là database/container có thể hủy sau test.** Bài sử dụng label `Test001Person`, `Test001Course` và relationship type có tiền tố `TEST001_` để dễ nhận ra dữ liệu minh họa. Các lệnh `CREATE` dưới đây **không tự idempotent**: nếu chạy hai lần không dọn database, số lượng sẽ tăng hoặc gặp constraint. Đây là lựa chọn cố ý để test không che giấu hiện tượng dữ liệu được seed lặp.

### 3.1. Constraint kiểm tra đúng khóa tổ hợp

Tạo constraint trên database trống:

```cypher
CREATE CONSTRAINT test001_person_key IF NOT EXISTS
FOR (p:Test001Person)
REQUIRE (p.tenantId, p.personId) IS UNIQUE;
```

```cypher
CREATE CONSTRAINT test001_course_key IF NOT EXISTS
FOR (c:Test001Course)
REQUIRE (c.tenantId, c.courseId) IS UNIQUE;
```

Composite uniqueness không yêu cầu mọi node phải có đầy đủ property khóa. Với dữ liệu nghiệp vụ thật, cần xác thực thiếu khóa trong pipeline hoặc dùng loại constraint có yêu cầu tồn tại khi phiên bản/edition hỗ trợ. Fixture này cấp đầy đủ khóa cho từng node.

### 3.2. Tạo 6 Person, 3 Course và 14 relationship

Chạy **toàn bộ câu `CREATE` sau một lần**:

```cypher
CREATE
  // 5 Person ở T1, trong đó Bình mang thêm label Mentor.
  (an:Test001Person {
    tenantId: 'T1', personId: 'P01',
    name: 'An', email: 'an@example.test',
    active: true, age: 30
  }),
  (binh:Test001Person:Test001Mentor {
    tenantId: 'T1', personId: 'P02',
    name: 'Bình', email: 'binh@example.test',
    active: true, age: 22,
    skills: ['Cypher', 'Java']
  }),
  (chi:Test001Person {
    tenantId: 'T1', personId: 'P03',
    name: 'Chi', active: false, age: 23
    // Cố ý không có property email.
  }),
  (dung:Test001Person {
    tenantId: 'T1', personId: 'P04',
    name: 'Dũng', email: 'dung@example.test',
    active: true, age: 0
  }),
  (hanh:Test001Person {
    tenantId: 'T1', personId: 'P05',
    name: 'Hạnh', email: '', active: true
    // email rỗng; không có age; không có relationship.
  }),
  // Person T2 trùng personId với An nhưng khác tenantId.
  (eva:Test001Person {
    tenantId: 'T2', personId: 'P01',
    name: 'Eva', email: 'eva@example.test',
    active: true, age: 28
  }),

  (neo:Test001Course {
    tenantId: 'T1', courseId: 'C101', title: 'Neo4j', published: true
  }),
  (java:Test001Course {
    tenantId: 'T1', courseId: 'C102', title: 'Java Driver', published: false
  }),
  (neoT2:Test001Course {
    tenantId: 'T2', courseId: 'C101', title: 'Graph cho T2',
    published: true
  }),

  // 8 cạnh FOLLOWS (R01 và R08 là hai cạnh song song).
  (an)-[:TEST001_FOLLOWS {
    edgeId: 'R01', since: date('2026-01-01')
  }]->(binh),
  (an)-[:TEST001_FOLLOWS {
    edgeId: 'R02', since: date('2026-01-02')
  }]->(chi),
  (binh)-[:TEST001_FOLLOWS {edgeId: 'R03'}]->(chi),
  (chi)-[:TEST001_FOLLOWS {edgeId: 'R04'}]->(an),
  (binh)-[:TEST001_FOLLOWS {edgeId: 'R05'}]->(dung),
  (chi)-[:TEST001_FOLLOWS {edgeId: 'R06'}]->(dung),
  (dung)-[:TEST001_FOLLOWS {edgeId: 'R07'}]->(dung),
  (an)-[:TEST001_FOLLOWS {
    edgeId: 'R08', since: date('2026-02-01')
  }]->(binh),

  // Type khác: quan hệ Mentor đi ngược chiều FOLLOWS An→Bình.
  (binh)-[:TEST001_MENTORS {edgeId: 'M01'}]->(an),

  // 5 cạnh ENROLLED.
  (an)-[:TEST001_ENROLLED {
    enrollmentId: 'E01', status: 'ACTIVE', score: 94
  }]->(neo),
  (binh)-[:TEST001_ENROLLED {
    enrollmentId: 'E02', status: 'ACTIVE'
    // Cố ý không có property score.
  }]->(neo),
  (chi)-[:TEST001_ENROLLED {
    enrollmentId: 'E03', status: 'WITHDRAWN', score: 0
  }]->(java),
  (eva)-[:TEST001_ENROLLED {
    enrollmentId: 'E04', status: 'ACTIVE', score: 88
  }]->(neoT2),
  (an)-[:TEST001_ENROLLED {
    enrollmentId: 'E05', status: 'ACTIVE', score: 77
  }]->(java);
```

**Lưu ý về cú pháp comment:** một số client/phiên bản Cypher có thể nhạy với comment ở cuối dòng trong literal map. Nếu gặp lỗi parse do comment nội tuyến, chuyển comment ra ngoài map mà không thay đổi dữ liệu. Các đoạn `CREATE` trên chủ đích tạo **9 node và 14 relationship**.

### 3.3. Kiểm kê dữ liệu kỳ vọng

| Loại dữ liệu | Số lượng |
| --- | ---: |
| `Test001Person` | 6 |
| `Test001Course` | 3 |
| Node tổng | **9** |
| `TEST001_FOLLOWS` | 8 |
| `TEST001_MENTORS` | 1 |
| `TEST001_ENROLLED` | 5 |
| Relationship tổng | **14** |

Các cạnh thuộc type `FOLLOWS` có mã R01–R08; cạnh cố vấn M01; cạnh đăng ký E01–E05. Dựa vào mã cạnh giúp xác minh chính xác khi hai relationship có cùng đầu/cuối, thay vì nhìn vào hình vẽ.

## 4. Assert số lượng thay vì chỉ xem graph bằng mắt

Neo4j Browser hiển thị graph hữu ích nhưng **không phải oracle kiểm thử**: các nút có thể chồng nhau và quan hệ song song khó phân biệt. Đưa kết quả về bảng và so sánh với giá trị dự kiến.

```cypher
MATCH (p:Test001Person)
RETURN count(p) AS actual,
       count(p) = 6 AS passed;
```

```cypher
MATCH (c:Test001Course)
RETURN count(c) AS actual,
       count(c) = 3 AS passed;
```

```cypher
MATCH ()-[r:TEST001_FOLLOWS]->()
RETURN count(r) AS actual,
       count(r) = 8 AS passed;
```

```cypher
MATCH ()-[r:TEST001_ENROLLED]->()
RETURN count(r) AS actual,
       count(r) = 5 AS passed;
```

Trong môi trường test có fixture riêng, mọi trường `passed` phải là `true`. Ở framework tự động, **phải assert** rằng `passed == true` hoặc `actual == expected`; chỉ chạy câu truy vấn và không đọc kết quả **không** được tính là kiểm thử.

Để kiểm tra các label bổ sung không làm tăng số node, phân biệt:

```cypher
MATCH (p:Test001Person:Test001Mentor)
RETURN collect(p.personId) AS mentorIds;
```

Trả `['P02']`. Bình là **một node mang hai label**, không phải hai node riêng.

## 5. Quan hệ có hướng, nhiều type và cạnh song song

### 5.1. Không nhầm số cạnh với số node đích

```cypher
MATCH (an:Test001Person {
  tenantId: 'T1', personId: 'P01'
})-[r:TEST001_FOLLOWS]->(target:Test001Person)
RETURN count(r) AS relationships,
       count(DISTINCT target) AS uniqueTargets;
```

Kết quả mong đợi:

| relationships | uniqueTargets |
| ---: | ---: |
| **3** | **2** |

Hai cạnh R01 và R08 đều từ An đến Bình. Nếu ứng dụng hỏi “An theo dõi bao nhiêu người?”, đáp án là **2**; nếu hỏi “có bao nhiêu bản ghi quan hệ theo dõi chiều đi ra?”, đáp án là **3**.

Lấy danh sách cạnh để nhìn rõ:

```cypher
MATCH (an:Test001Person {
  tenantId: 'T1', personId: 'P01'
})-[r:TEST001_FOLLOWS]->(target:Test001Person)
RETURN r.edgeId AS edgeId,
       target.personId AS targetId,
       r.since AS since
ORDER BY edgeId;
```

Kỳ vọng R01→P02, R02→P03, R08→P02. `r.since` giúp kiểm tra property ngày của relationship.

### 5.2. Kiểm thử chiều đi/chiều đến

```cypher
MATCH (binh:Test001Person {
  tenantId: 'T1', personId: 'P02'
})
OPTIONAL MATCH (follower:Test001Person)
  -[r:TEST001_FOLLOWS]->(binh)
RETURN count(r) AS incomingRelationships,
       count(DISTINCT follower) AS incomingPeople;
```

Trả **2 relationship** nhưng chỉ **1 follower** là An. Nếu viết nhầm `(binh)-[:TEST001_FOLLOWS]->(...)`, tập dữ liệu và số lượng sẽ khác. Không nên dùng pattern vô hướng `-[:TYPE]-` nếu nghiệp vụ phân biệt “theo dõi” và “được theo dõi”.

### 5.3. Kiểm thử lọc theo relationship type

```cypher
MATCH (binh:Test001Person {
  tenantId: 'T1', personId: 'P02'
})-[r]->(target:Test001Person)
RETURN type(r) AS relationshipType,
       target.personId AS targetId,
       count(*) AS n
ORDER BY relationshipType, targetId;
```

Kết quả gồm FOLLOWS→P03, FOLLOWS→P04 và MENTORS→P01. Truy vấn không khóa type sẽ bao gồm cả quan hệ cố vấn, làm sai logic nếu ứng dụng chỉ muốn các kết nối theo dõi.

## 6. Chu trình, self-loop và các đường đi dài hai bước

### 6.1. Self-loop không phải lỗi của Cypher

```cypher
MATCH (p:Test001Person)-[r:TEST001_FOLLOWS]->(p)
RETURN p.personId AS personId,
       r.edgeId AS edgeId;
```

Chỉ có **P04/R07**. Nếu miền nghiệp vụ không cho phép một người tự theo dõi, fixture này phải là **negative case** để lớp service từ chối tạo. Nhưng nó vẫn có giá trị cho truy vấn tổng quát: kiểm tra thuật toán không treo, không suy rằng điểm đầu khác điểm cuối, và không bỏ qua một cạnh hiện hữu một cách vô ý.

### 6.2. Chu trình quay về node bắt đầu

```cypher
MATCH path =
  (an:Test001Person {tenantId: 'T1', personId: 'P01'})
  -[:TEST001_FOLLOWS]->
  (:Test001Person)
  -[:TEST001_FOLLOWS]->
  (an)
RETURN [n IN nodes(path) | n.personId] AS route;
```

Trả đường `P01 → P03 → P01`. Một path có thể bắt đầu và kết thúc ở **cùng node**. Khi test code dùng `nodes(path)`, số node trong danh sách là **3** (có P01 ở đầu và cuối), nhưng chỉ có **2 node phân biệt**.

### 6.3. Đếm đường đi khác đếm đích

Mẫu đúng hai cạnh theo chiều FOLLOWS:

```cypher
MATCH path =
  (an:Test001Person {tenantId: 'T1', personId: 'P01'})
  -[:TEST001_FOLLOWS]->
  (:Test001Person)
  -[:TEST001_FOLLOWS]->
  (dest:Test001Person)
RETURN count(path) AS paths,
       count(DISTINCT dest) AS uniqueDestinations;
```

Kết quả theo đúng dữ liệu mẫu:

| paths | uniqueDestinations |
| ---: | ---: |
| **6** | **3** |

Giải thích bằng tay:

- Hai cạnh An→Bình, mỗi cạnh có hai lựa chọn tiếp Bình→Chi hoặc Bình→Dũng: **4 path**.
- Một cạnh An→Chi, tiếp Chi→An hoặc Chi→Dũng: **2 path**.
- Tổng **6 path**; đích phân biệt là `P01`, `P03` và `P04`.

Nếu chỉ tìm đường đến Dũng ở đúng hai bước:

```cypher
MATCH path =
  (an:Test001Person {tenantId: 'T1', personId: 'P01'})
  -[:TEST001_FOLLOWS]->
  (:Test001Person)
  -[:TEST001_FOLLOWS]->
  (dung:Test001Person {tenantId: 'T1', personId: 'P04'})
RETURN count(path) AS waysToDung;
```

Đáp án là **3**: An→Bình→Dũng bằng R01, bằng R08, và An→Chi→Dũng.

**Lưu ý:** các ví dụ dùng đúng **hai mẫu cạnh tường minh**, không phụ thuộc cú pháp variable-length mới/cũ của Cypher. Với đường đi biến độ dài, cần xác nhận thêm ngữ nghĩa uniqueness và những relationship được phép lặp lại theo phiên bản Cypher.

## 7. Node cô lập, OPTIONAL MATCH và giá trị null

### 7.1. Node cô lập phải xuất hiện khi truy vấn yêu cầu “tất cả”

Kiểm tra node không có bất kỳ relationship nào bằng một pattern existence subquery:

```cypher
MATCH (p:Test001Person {tenantId: 'T1'})
WHERE NOT EXISTS {
  MATCH (p)--()
}
RETURN p.personId AS personId, p.name AS name;
```

Kỳ vọng chỉ có **P05/Hạnh**, vì Hạnh không tham gia relationship nào. `EXISTS` ở đây kiểm tra mọi relationship bất kể hướng/type; vì thế Dũng không cô lập dù có self-loop. Một truy vấn `MATCH (p)-[:TEST001_ENROLLED]->(...)` sẽ **bỏ qua** Dũng và Hạnh. Nếu API cần danh sách mọi Person kèm số khóa học, dùng `OPTIONAL MATCH`:

```cypher
MATCH (p:Test001Person)
OPTIONAL MATCH (p)-[e:TEST001_ENROLLED]->(c:Test001Course)
RETURN p.tenantId AS tenantId,
       p.personId AS personId,
       count(e) AS enrollments
ORDER BY tenantId, personId;
```

Kỳ vọng:

| tenantId | personId | enrollments |
| --- | --- | ---: |
| T1 | P01 | 2 |
| T1 | P02 | 1 |
| T1 | P03 | 1 |
| T1 | P04 | 0 |
| T1 | P05 | 0 |
| T2 | P01 | 1 |

**Bẫy đếm:** với hàng do `OPTIONAL MATCH` giữ lại khi không có quan hệ, `count(*)` vẫn tính **1 hàng**. `count(e)` chỉ tính các `e` khác `null` nên đúng cho yêu cầu số đăng ký.

### 7.2. Property vắng mặt khác chuỗi rỗng

Chi (T1/P03) **không có property `email`**; Hạnh (T1/P05) có `email = ''`. Hai trường hợp đều có thể gây lỗi validation nhưng **không tương đương trong Cypher**:

```cypher
MATCH (p:Test001Person {tenantId: 'T1'})
WHERE p.email IS NULL
RETURN p.personId AS id;
```

Kỳ vọng: **P03**.

```cypher
MATCH (p:Test001Person {tenantId: 'T1'})
WHERE p.email = ''
RETURN p.personId AS id;
```

Kỳ vọng: **P05**.

Một câu như `p.email = null` không được dùng để kiểm tra thiếu property: dùng `IS NULL` hoặc `IS NOT NULL`. Neo4j không lưu một property có giá trị `null` như một giá trị thông thường của node; `SET p.email = null` có ý nghĩa loại property đó.

### 7.3. Giá trị 0 khác property không tồn tại

Dũng (T1/P04) có `age = 0`, Hạnh không có `age`:

```cypher
MATCH (p:Test001Person {tenantId: 'T1'})
WHERE p.age = 0
RETURN p.personId AS id;
```

Trả **P04**.

```cypher
MATCH (p:Test001Person {tenantId: 'T1'})
WHERE p.age IS NULL
RETURN p.personId AS id;
```

Trả **P05**. Trong Java mapper, không nên dùng primitive `int` cho một trường số có thể thiếu mà không có quy tắc mặc định rõ: dùng `Integer` hoặc DTO tùy yêu cầu.

### 7.4. Relationship có score bằng 0 và score vắng mặt

```cypher
MATCH (:Test001Person)-[e:TEST001_ENROLLED]->(:Test001Course)
RETURN e.enrollmentId AS id, e.status AS status, e.score AS score
ORDER BY id;
```

Kỳ vọng:

| id | status | score |
| --- | --- | ---: |
| E01 | ACTIVE | 94 |
| E02 | ACTIVE | `null` |
| E03 | WITHDRAWN | 0 |
| E04 | ACTIVE | 88 |
| E05 | ACTIVE | 77 |

Test phải phân biệt: `e.score IS NULL` trả **E02**; `e.score = 0` trả **E03**. Khi tổng hợp số lượng có điểm, `count(e.score)` trả **4**, còn `count(*)` trả **5**. Trường `null` có thể được ứng dụng hiểu là “chưa chấm”; số 0 có thể là điểm thực hoặc giá trị biên hợp lệ tùy nghiệp vụ.

## 8. Cách ly tenant và khóa trùng nhau giữa tenant

Fixture cố tình dùng `personId = 'P01'` cho **An (T1)** và **Eva (T2)**; course `C101` cũng xuất hiện ở cả hai tenant. Điều này buộc các test phải nhắm vào **khóa tổ hợp**.

Truy vấn thiếu điều kiện tenant:

```cypher
MATCH (p:Test001Person {personId: 'P01'})
RETURN p.tenantId AS tenantId, p.name AS name
ORDER BY tenantId;
```

Trả hai hàng: **T1/An** và **T2/Eva**. Đó không phải lỗi của dữ liệu; chính là dấu hiệu cho thấy `personId` không phải khóa toàn cục.

Truy vấn có tenant:

```cypher
MATCH (p:Test001Person {
  tenantId: 'T1', personId: 'P01'
})-[e:TEST001_ENROLLED]->(c:Test001Course)
RETURN p.name AS name,
       c.tenantId AS courseTenant,
       c.courseId AS courseId
ORDER BY courseId;
```

Kỳ vọng có **C101 và C102 của T1**, không lẫn C101 của T2. Nên xác minh các quan hệ đăng ký không nối hai tenant:

```cypher
MATCH (p:Test001Person)-[e:TEST001_ENROLLED]->(c:Test001Course)
WHERE p.tenantId <> c.tenantId
RETURN count(e) AS crossTenantEnrollments;
```

Trả **0**. Constraint uniqueness trên mỗi label **không tự bảo đảm** hai đầu mút relationship phải cùng tenant; cần kiểm tra bằng quy tắc nghiệp vụ ở service/pipeline hoặc bằng audit.

## 9. Phép kiểm thử âm: dữ liệu sai phải bị phát hiện

Fixture nhỏ không nhất thiết chứa sẵn mọi bản ghi không hợp lệ: một số trường hợp biên cần **thử tạo dữ liệu lỗi trong transaction riêng** rồi xác nhận bị từ chối/rollback. Điều này đặc biệt quan trọng đối với constraint và transaction.

### 9.1. Vi phạm uniqueness của khóa Person

Sau khi tạo constraint ở mục 3, câu sau cố tình tạo Person T1/P01 thứ hai:

```cypher
// NEGATIVE TEST: dự kiến vi phạm uniqueness constraint
CREATE (:Test001Person {
  tenantId: 'T1', personId: 'P01', name: 'Trùng khóa'
});
```

**Kỳ vọng:** Neo4j báo lỗi constraint; không có node mới được commit. Chỉ chạy trong transaction/test riêng khi đang kiểm thử lỗi, không chen lệnh này vào batch seed. Nếu câu lệnh thành công, nghĩa là constraint chưa tồn tại/không được tạo đúng hoặc nhãn/khóa test khác dự kiến.

### 9.2. Cùng personId nhưng khác tenant là hợp lệ

Ngược lại, việc An và Eva có cùng `personId='P01'` là **hợp lệ** theo composite uniqueness. Một test tự động không được khẳng định “`personId` chỉ xuất hiện một lần trên toàn graph”.

### 9.3. Validation của ứng dụng và constraint là hai lớp riêng

Các quy tắc sau **không được đảm bảo chỉ nhờ uniqueness constraint**:

- `Person.email` bắt buộc có giá trị không rỗng.
- `ENROLLED.score` phải trong khoảng `0..100` nếu không null.
- `FOLLOWS` không được tự nối `p→p` nếu nghiệp vụ cấm self-follow.
- Một cặp Person–Person chỉ được có một `FOLLOWS` nếu nghiệp vụ cấm cạnh song song.
- `ENROLLED` không được nối hai tenant khác nhau.

Fixture có **một số trường hợp cố tình vi phạm các quy tắc nghiệp vụ tùy chọn** (ví dụ self-loop, cạnh song song, email rỗng) để xem truy vấn xử lý thế nào. Nếu hệ thống thật **cấm** các tình huống đó, test command tạo mới phải **từ chối** chúng, trong khi test truy vấn dữ liệu bẩn có thể dùng một fixture/transaction riêng để kiểm tra khả năng phát hiện.

Đừng bật rule tự động “làm sạch” trong lúc seed khiến các trường hợp biên biến mất; khi đó bộ test có thể xanh nhưng không kiểm chứng được hành vi mong muốn.

## 10. Assertion tổng hợp: bảng oracle ổn định

Một bộ test tốt có **oracle**: các kết quả đã tính được bằng tay, không phải được suy từ chính truy vấn cần test.

| Assertion | Kết quả kỳ vọng |
| --- | --- |
| Số Person | **6** |
| Số Course | **3** |
| Số FOLLOWS | **8** |
| Số MENTORS | **1** |
| Số ENROLLED | **5** |
| Tổng relationship | **14** |
| Person mang label Mentor | **1** (T1/P02) |
| FOLLOWS đi ra từ T1/P01 | **3 cạnh**, **2 đích** |
| FOLLOWS đi vào T1/P02 | **2 cạnh**, **1 người** |
| Self-loop FOLLOWS | **1** (R07) |
| Path đúng 2 FOLLOWS từ T1/P01 | **6** |
| Đích phân biệt sau đúng 2 FOLLOWS từ T1/P01 | **3** |
| Path đúng 2 FOLLOWS từ T1/P01 tới T1/P04 | **3** |
| Person không có bất kỳ relationship nào | **1** (T1/P05) |
| Person ở T1 thiếu email | **1** (P03) |
| Person ở T1 có email rỗng | **1** (P05) |
| Relationship ENROLLED thiếu score | **1** (E02) |
| Relationship ENROLLED score = 0 | **1** (E03) |
| Enrollment ACTIVE | **4** |
| ENROLLED nối khác tenant | **0** |

Mọi test tương ứng nên assert trên **giá trị hoặc tập kết quả ổn định**. Không cố assert thứ tự các node/path nếu câu Cypher không có `ORDER BY`.

## 11. Viết truy vấn kiểm tra thành test tự động

### 11.1. Cypher trả về cờ pass/fail

Ví dụ kiểm tra số Person:

```cypher
MATCH (p:Test001Person)
WITH count(p) AS actual
RETURN actual,
       6 AS expected,
       actual = 6 AS passed;
```

Kiểm tra tập người theo dõi của An **không phụ thuộc thứ tự** bằng cách đếm node đích:

```cypher
MATCH (an:Test001Person {
  tenantId: 'T1', personId: 'P01'
})-[:TEST001_FOLLOWS]->(p:Test001Person)
RETURN count(DISTINCT p) AS uniqueTargetCount;
```

Expected = **2**. Nếu cần so đúng tập `P02, P03`, hãy `RETURN DISTINCT p.personId ORDER BY p.personId`, rồi trong Java assert so với danh sách đã sắp hoặc so sánh tập ID.

### 11.2. JUnit 5 + Neo4j Java Driver

Ví dụ phần test **sau khi fixture mục 3 được seed vào database kiểm thử**:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

class FixtureQueryTest {

    private final Driver driver;

    FixtureQueryTest(Driver driver) {
        this.driver = driver; // Được test configuration cấp vào.
    }

    @Test
    void followsFromAnHasThreeEdgesButTwoDestinations() {
        try (Session session = driver.session()) {
            var record = session.run("""
                MATCH (:Test001Person {
                    tenantId: 'T1', personId: 'P01'
                })-[r:TEST001_FOLLOWS]->(p:Test001Person)
                RETURN count(r) AS edges,
                       count(DISTINCT p) AS destinations
                """).single();

            assertEquals(3L, record.get("edges").asLong());
            assertEquals(2L, record.get("destinations").asLong());
        }
    }

    @Test
    void isolatedPersonStillExists() {
        try (Session session = driver.session()) {
            var record = session.run("""
                MATCH (p:Test001Person {
                    tenantId: 'T1', personId: 'P05'
                })
                RETURN NOT EXISTS { MATCH (p)--() } AS isolated
                """).single();

            assertTrue(record.get("isolated").asBoolean());
        }
    }
}
```

Đây là **mẫu test minh họa phần assertion**, không phải class test hoàn chỉnh để JUnit tự inject `Driver`. Trong project thực, tạo Driver qua fixture/test configuration, `@BeforeAll`/`@AfterAll` hoặc dùng Spring Test và đóng nó đúng lifecycle. Quan trọng là từng assertion đọc giá trị trả về và kiểm tra bằng **expected đã định trước**.

### 11.3. Testcontainers và Spring Data Neo4j

Đối với integration test, Testcontainers có thể khởi động **Neo4j container tạm thời**, seed fixture rồi thực thi repository hoặc `Neo4jClient`. Một ví dụ khung kết nối:

```java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.testcontainers.containers.Neo4jContainer;

// Ví dụ định hướng; vòng đời có thể do JUnit @Container quản lý.
String testPassword = "test-only-password";
try (Neo4jContainer<?> neo4j =
         new Neo4jContainer<>("neo4j:5")
             .withAdminPassword(testPassword)) {

    neo4j.start();

    try (Driver driver = GraphDatabase.driver(
            neo4j.getBoltUrl(),
            AuthTokens.basic("neo4j", testPassword))) {

        driver.verifyConnectivity();

        // Seed các câu Cypher ở mục 3.
        // Chạy queries và assert các kỳ vọng trong mục 10.
    }
}
```

**Ví dụ này chỉ minh họa kết nối và vòng đời**; để dùng thật cần dependency Testcontainers tương thích, Docker hoạt động, bổ sung đoạn seed và test assertion. Đặt image tag **đã kiểm chứng** thay cho một tag động `neo4j:5` khi cần tái lập kết quả trong CI. Khi test SDN, phiên bản image nên phù hợp với Spring Boot/SDN, Java Driver và Cypher đang triển khai.

Với Spring Boot test, có thể dùng `@DataNeo4jTest` hoặc `@SpringBootTest` kết hợp container/config test theo mục đích: repository mapping, cập nhật graph, transaction hay toàn bộ application context.

**Nhất thiết phải test mapping và persistence riêng:** một truy vấn Cypher trả đúng dữ liệu không tự chứng minh `@Node`, `@Relationship`, `@RelationshipProperties` và `repository.save()` hoạt động đúng, nhất là khi entity chỉ được tải một phần graph.

## 12. Cô lập test, reset fixture và chống flaky test

Fixture tốt không chỉ có dữ liệu đúng: **test phải chạy lại được mà không ảnh hưởng nhau**.

### 12.1. Các phương án cô lập

| Phương án | Điểm mạnh | Điều cần chú ý |
| --- | --- | --- |
| Database/Neo4j container mới cho suite | Không lẫn dữ liệu cũ, schema/tài nguyên dự đoán được | Chi phí khởi động container |
| Database riêng cho từng nhóm test | Dễ phân tách quyền và lược đồ | Neo4j edition/quyền có thể giới hạn tạo database |
| Transaction rollback cho từng test | Tốc độ nhanh khi framework cho phép | Không áp dụng cho thao tác commit ở transaction khác; DDL có thể khác hành vi |
| Namespace bằng `testRunId` | Nhiều nhóm test chia sẻ một DB mà vẫn định danh riêng | Mọi truy vấn và cleanup phải luôn lọc đúng namespace |
| Xóa dữ liệu bằng label test sau suite | Tái sử dụng DB kiểm thử | **Chỉ an toàn trong DB test riêng**, phải kiểm soát liên kết ngoài label |

Ưu tiên container/database dùng riêng vì dễ khẳng định số lượng tuyệt đối. Một câu `MATCH (p:Test001Person) RETURN count(*)` không còn đáng tin nếu nhiều test cùng tạo node mang label này trong một database chung.

### 12.2. Cleanup có chủ đích

**Chỉ trong database chuyên dùng cho fixture này**, sau khi đã xác nhận không có dữ liệu khác dùng chung node, có thể dọn:

```cypher
MATCH (p:Test001Person)
DETACH DELETE p;
```

```cypher
MATCH (c:Test001Course)
DETACH DELETE c;
```

Lệnh `DETACH DELETE` xóa node **và mọi relationship kề nó**. Không chạy các câu trên với label trùng dữ liệu nghiệp vụ thật hoặc một graph dùng chung có liên kết ngoài phạm vi test. Trên Testcontainers, hủy container sau suite thường an toàn và đơn giản hơn tự viết cleanup rộng.

Các constraint `test001_person_key` và `test001_course_key` vẫn còn sau khi chỉ xóa node; nếu cần database hoàn toàn mới, quản lý cả schema qua lifecycle của môi trường kiểm thử.

### 12.3. Các nguyên nhân test không ổn định

- Dựa vào `elementId()` hoặc ID nội bộ giữa các lần dựng graph.
- Dựa vào thứ tự Neo4j trả node/relationship khi thiếu `ORDER BY`.
- Dựa vào thời gian hệ thống (`date()`, `datetime()`) thay vì ngày cố định trong fixture.
- Dùng `MERGE` để seed rồi vô tình che duplicate seed; hoặc dùng `CREATE` nhiều lần trên DB chưa reset.
- Dùng chung database cho test chạy song song và assert tổng số node toàn graph.
- Không đợi index/constraint hoàn tất khi test có phụ thuộc vào schema.
- Kiểm tra tối ưu query bằng `PROFILE` rồi mặc định plan/DB Hits không thay đổi giữa phiên bản server.

## 13. Phân biệt test tính đúng và test hiệu năng

Dùng cùng một fixture nhỏ để kiểm chứng cấu trúc và ngữ nghĩa; **không dùng nó làm bằng chứng hiệu năng production**.

| Loại test | Bộ dữ liệu phù hợp | Assertion phù hợp |
| --- | --- | --- |
| Unit test service | Object/DTO giả lập | Mapping đầu vào, điều kiện nghiệp vụ |
| Integration test Cypher | Fixture 9 node/14 relationship | Số hàng, tập ID, hướng/type, path, null |
| Integration test SDN | Fixture nhỏ trên Neo4j thật | Mapping và tránh thêm/xóa cạnh ngoài ý muốn |
| Constraint/negative test | Fixture + giao dịch lỗi riêng | Duplicate bị từ chối, rollback đúng |
| Performance/load test | Graph lớn, phân bố và degree đại diện | Latency percentile, DB Hits, CPU/memory và throughput |

Một planner có thể chọn `NodeByLabelScan` trên graph chỉ có 9 node, và điều đó hoàn toàn hợp lý. Đừng viết test cố định rằng query **bắt buộc** dùng `NodeIndexSeek` hoặc phải tốn một lượng DB Hits chính xác trên tập nhỏ. Với tối ưu truy vấn, dùng `EXPLAIN`/`PROFILE` để hiểu kế hoạch; các ngưỡng hiệu năng cần lấy từ môi trường và workload đại diện.

## 14. Quy trình thiết kế fixture cho một tính năng mới

Khi phát triển truy vấn như “gợi ý người theo dõi trong hai bước” hoặc “khóa học người dùng đang học”, có thể đi theo trình tự:

1. **Liệt kê ngữ nghĩa mong đợi:** trả node duy nhất hay tất cả path? Có tính relationship song song không? Có lọc tenant không?
2. **Chọn kích thước nhỏ:** đủ để đếm bằng tay, ví dụ 5–10 node và một số cạnh được đặt mã.
3. **Thêm đối chứng:** một node không nối, một node có property thiếu, một node cùng business ID khác tenant.
4. **Thêm cấu trúc khó:** ít nhất hai đường tới cùng đích, chu trình, self-loop và type cạnh không liên quan.
5. **Thêm dữ liệu biên:** chuỗi rỗng, giá trị 0, property vắng mặt, trạng thái ACTIVE/WITHDRAWN.
6. **Viết oracle trước code:** bảng count, tập khóa, các đường cụ thể được phép và không được phép.
7. **Seed theo một hợp đồng:** constraint trước, dữ liệu sau; không chèn ngẫu nhiên, không dùng thời gian hiện tại.
8. **Assert với Cypher hoặc Java:** không chỉ mở Browser để xem graph.
9. **Tách test lỗi khỏi seed chung:** negative constraint test trong transaction/DB riêng.
10. **Cô lập và dọn dẹp:** dùng Testcontainers hoặc một phạm vi test được kiểm soát; không chạy cleanup trên production.

### Bài tự luyện

**Câu 1.** Vì sao test “An theo dõi 3 người” là sai với fixture, dù An có ba relationship `FOLLOWS` đi ra?

**Câu 2.** Có bao nhiêu path dài đúng hai cạnh `FOLLOWS` từ T1/P01 tới T1/P04? Giải thích vai trò cạnh song song.

**Câu 3.** `count(*)` và `count(e)` khác nhau thế nào khi dùng `OPTIONAL MATCH` cho Hạnh?

**Câu 4.** Vì sao `p.email IS NULL` tìm Chi nhưng không tìm Hạnh?

**Câu 5.** Nếu dùng `MATCH (p:Test001Person {personId:'P01'})` mà quên `tenantId`, kết quả nào sẽ xuất hiện và rủi ro là gì?

**Câu 6.** Vì sao kiểm thử trên 9 node không thể chứng minh index seek luôn nhanh hơn label scan?

**Câu 7.** Nếu một truy vấn trả 6 path mà chỉ có 3 node đích phân biệt, API phải trả kiểu nào khi câu hỏi nghiệp vụ là “những người nào có thể tới”?

**Đáp án gợi ý:** (1) An có ba cạnh nhưng chỉ hai đích: Bình, Chi. (2) Ba path: hai đường qua Bình dùng R01/R08, một đường qua Chi. (3) `count(*)` tính hàng null do optional giữ lại, `count(e)` chỉ tính cạnh có thật. (4) Hạnh có email rỗng, Chi không có property email. (5) Cả An T1 và Eva T2; nguy cơ rò/chồng dữ liệu tenant. (6) Dataset quá nhỏ và planner phụ thuộc thống kê/tải thực. (7) Trả node đích duy nhất bằng `DISTINCT` hoặc cơ chế reachability phù hợp.

## Tài liệu tham khảo

- [Neo4j Cypher Manual — Patterns](https://neo4j.com/docs/cypher-manual/current/patterns/): node, relationship, hướng và cách khớp mẫu.
- [Neo4j Cypher Manual — OPTIONAL MATCH](https://neo4j.com/docs/cypher-manual/current/clauses/optional-match/): hàng có giá trị null khi không tìm thấy relationship.
- [Neo4j Cypher Manual — Aggregating functions](https://neo4j.com/docs/cypher-manual/current/functions/aggregating/): `count()`, `collect()` và `DISTINCT`.
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/): uniqueness và kiểm tra khóa nghiệp vụ.
- [Neo4j Java Driver Manual](https://neo4j.com/docs/java-manual/current/): chạy truy vấn và đọc kết quả trong test Java.
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/): integration test, mapping entity/relationship và lưu graph.

**Ghi nhớ:** fixture Neo4j tốt không cần nhiều dữ liệu; nó cần **đúng những trường hợp dễ khiến truy vấn sai**. Hãy có khóa nghiệp vụ và số lượng rõ ràng, cạnh song song, chu trình, node cô lập, null/empty/zero, hai tenant và một bảng kết quả mong đợi trước khi viết test. Từ đó, mỗi thay đổi Cypher, Java Driver hoặc Spring Data Neo4j đều có thể được kiểm chứng về **tính đúng** mà không phụ thuộc hình vẽ hay dữ liệu ngẫu nhiên.
