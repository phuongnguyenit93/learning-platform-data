# Quan hệ song song, vòng tự nối và những trường hợp mô hình cần lưu ý

## 1. Mục tiêu và bối cảnh

Neo4j là cơ sở dữ liệu đồ thị sử dụng **property graph** để biểu diễn thực thể bằng **node**, liên kết bằng **relationship**, dữ kiện bằng **property** và truy vấn bằng **Cypher**. Trong chương **Thành phần đồ thị** của module `DATABASE_ENGINE_GRAPH_NEO4J`, bài này phân tích hai cấu trúc hợp lệ nhưng rất dễ bị hiểu sai:

- **Quan hệ song song** (*parallel relationships*): có **nhiều relationship riêng biệt** cùng nối một cặp nút.
- **Vòng tự nối** (*self-loop*): một relationship có **nút bắt đầu và nút kết thúc là cùng một nút**.

Hiểu hai cấu trúc này giúp thiết kế mô hình chính xác, nhập dữ liệu không trùng ngoài ý muốn, kiểm soát kết quả khi truy vấn quan hệ/đường đi, dùng index và constraint phù hợp, đồng thời tránh lỗi khi tích hợp bằng **Neo4j Java Driver** hoặc **Spring Data Neo4j**.

Sau bài học, bạn có thể:

1. Phân biệt **nhiều cạnh hợp lệ** với **nhiều cạnh trùng dữ liệu**.
2. Giải thích cách **loại quan hệ**, **hướng**, **hai đầu mút** và **thuộc tính** quyết định ý nghĩa của cạnh.
3. Dùng Cypher tạo, đếm, lọc và phát hiện các quan hệ song song, self-loop.
4. Lựa chọn giữa relationship có thuộc tính và **nút sự kiện trung gian** khi một hành động xảy ra nhiều lần.
5. Thiết kế quy tắc tính duy nhất, loại bỏ self-loop không hợp lệ và tránh suy diễn sai từ số dòng kết quả.

> Hai cấu trúc được giới thiệu ở đây **không phải lỗi kỹ thuật mặc định** của Neo4j. Chúng chỉ trở thành lỗi nếu vi phạm quy tắc nghiệp vụ của hệ thống.

## 2. Ôn lại cấu tạo relationship trong property graph

Mỗi relationship trong Neo4j có:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Start node** | Nút bắt đầu theo hướng lưu | Tài khoản A |
| **End node** | Nút kết thúc theo hướng lưu | Tài khoản B |
| **Relationship type** | Loại liên kết, đúng **một type trên mỗi relationship** | `TRANSFERRED` |
| **Properties** | Thuộc tính mô tả riêng liên kết | `amount`, `eventId`, `occurredAt` |
| **Danh tính riêng** | Mỗi relationship là một phần tử độc lập trong đồ thị | Hai lần chuyển tiền là hai relationship khác nhau |

Một mẫu Cypher:

```cypher
(a:Account)-[r:TRANSFERRED {eventId: 'T001', amount: 200000}]->(b:Account)
```

Nghĩa là **tài khoản A đã chuyển một khoản tiền đến B**. Biến `r` tham chiếu một relationship; `a` và `b` là các biến nút. Hướng `->` thể hiện chiều của quan hệ được lưu, không phụ thuộc vị trí vẽ trên màn hình.

**Lưu ý nền tảng:** Neo4j **không tự giới hạn** “giữa hai nút chỉ có tối đa một relationship” hay “một nút không được nối với chính nó”. Nếu cần những giới hạn này, ứng dụng phải thiết kế rõ cách ghi và kiểm tra dữ liệu.

## 3. Quan hệ song song là gì?

Giả sử tài khoản A chuyển tiền cho B **hai lần khác nhau**. Hai hành động có cùng hai đầu mút, cùng type và cùng hướng, nhưng **khác sự kiện**:

```text
                [:TRANSFERRED {eventId: 'T001', amount: 200000}]
(:Account A) ──────────────────────────────────────────────→ (:Account B)
             ──────────────────────────────────────────────→
                [:TRANSFERRED {eventId: 'T002', amount: 350000}]
```

Đây là **hai relationship song song**. Chúng không tự hợp nhất vì có cùng hướng, type và hai nút đầu–cuối.

### 3.1. Các trường hợp thường được gọi là nhiều cạnh

Xét hai nút `a` và `b`:

| Cấu trúc | Ví dụ | Cách hiểu |
| --- | --- | --- |
| Cùng hướng, cùng type | `(a)-[:TRANSFERRED {eventId: 'T1'}]->(b)` và `(a)-[:TRANSFERRED {eventId: 'T2'}]->(b)` | Hai bản ghi liên kết cùng loại, có thể là hai sự kiện độc lập |
| Cùng hướng, **khác type** | `(a)-[:FOLLOWS]->(b)` và `(a)-[:MENTORS]->(b)` | Hai kiểu quan hệ nghiệp vụ giữa cùng một cặp nút |
| **Ngược hướng** | `(a)-[:FOLLOWS]->(b)` và `(b)-[:FOLLOWS]->(a)` | Hai hành động có hướng khác nhau, chẳng hạn theo dõi lẫn nhau |
| Cùng hai đầu mút, type, hướng và property | Hai lần `CREATE (a)-[:FOLLOWS]->(b)` | Hai relationship vật lý khác nhau; có thể là lỗi trùng nếu nghiệp vụ chỉ cho một lượt theo dõi |

Theo nghĩa mô hình đồ thị tổng quát, những cạnh khác type hoặc ngược chiều cũng là nhiều cạnh liên hệ cùng cặp nút. Khi **kiểm tra dữ liệu trùng**, cần nói rõ ta đang xét **cùng hướng, cùng type** hay chỉ xét cặp nút bất kể chiều/type.

### 3.2. Vì sao quan hệ song song có thể là dữ liệu đúng?

Nhiều nghiệp vụ có sự kiện lặp lại:

- **Giao dịch:** A chuyển tiền cho B nhiều lần; mỗi lần có mã giao dịch, số tiền và thời điểm riêng.
- **Di chuyển:** Người dùng đi từ địa điểm A đến B nhiều lần; mỗi hành trình có ngày và phương tiện riêng.
- **Truy cập:** Người dùng mở tài liệu nhiều lần; mỗi lần truy cập có thời điểm và nguồn.
- **Tương tác:** Hai người gửi tin nhắn cho nhau nhiều lần; mỗi tin nhắn là một sự kiện riêng.
- **Quan hệ đa dạng:** Một người vừa `FOLLOWS` vừa `MENTORS` người khác, dù hai nút đầu–cuối giống nhau.

Trong các trường hợp này, **chỉ giữ một relationship duy nhất** có thể làm mất thông tin lịch sử, tần suất hoặc chi tiết từng sự kiện.

### 3.3. Khi nào nhiều cạnh lại là lỗi?

Giả sử một hệ thống quy định: **mỗi người chỉ có một quan hệ `FOLLOWS` đi đến cùng một người tại một thời điểm**. Nếu chạy nhiều lần:

```cypher
MATCH (a:Person {personId: 'P001'})
MATCH (b:Person {personId: 'P002'})
CREATE (a)-[:FOLLOWS]->(b);
```

Mỗi lần `CREATE` sẽ tạo một relationship mới. Nếu hai nút được tìm thấy và thao tác được thực thi ba lần, giữa chúng có thể tồn tại **ba cạnh `FOLLOWS` song song**, dù nghiệp vụ chỉ muốn một.

Ngược lại, `CREATE` hai quan hệ `TRANSFERRED` với **hai `eventId` khác nhau** có thể hoàn toàn đúng. Vì thế, câu hỏi đầu tiên không phải “có nhiều cạnh không?” mà là **“mỗi cạnh đang đại diện cho một sự thật nghiệp vụ nào?”**.

## 4. Tạo và quan sát quan hệ song song bằng Cypher

Ví dụ thực hành dưới đây sử dụng mã bắt đầu bằng `GE004-`. Hãy chạy trong **database thử nghiệm**, chỉ chạy khối `CREATE` khởi tạo **một lần**. Chạy lại sẽ tạo thêm nút và relationship mới; mã hiển thị trong ví dụ không tự bảo đảm tính duy nhất.

### 4.1. Chuẩn bị dữ liệu

```cypher
CREATE (a:Account {accountId: 'GE004-A', ownerName: 'An'})
CREATE (b:Account {accountId: 'GE004-B', ownerName: 'Bình'})
CREATE (a)-[:TRANSFERRED {
  eventId: 'GE004-T001',
  amount: 200000,
  occurredAt: datetime('2026-01-10T10:00:00+07:00')
}]->(b)
CREATE (a)-[:TRANSFERRED {
  eventId: 'GE004-T002',
  amount: 350000,
  occurredAt: datetime('2026-01-11T09:30:00+07:00')
}]->(b)
CREATE (b)-[:TRANSFERRED {
  eventId: 'GE004-T003',
  amount: 50000,
  occurredAt: datetime('2026-01-12T08:00:00+07:00')
}]->(a)
RETURN a, b;
```

Kết quả mong đợi: **2 nút `Account`** và **3 quan hệ `TRANSFERRED`**:

```text
Account A -- T001, 200000 --> Account B
Account A -- T002, 350000 --> Account B
Account A <-- T003,  50000 -- Account B
```

Hai cạnh đầu là **song song cùng hướng**; cạnh thứ ba đi theo **chiều ngược lại**.

### 4.2. Liệt kê từng relationship riêng biệt

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]->
      (b:Account {accountId: 'GE004-B'})
RETURN
  type(r) AS relationshipType,
  startNode(r).accountId AS fromAccount,
  endNode(r).accountId AS toAccount,
  r.eventId AS eventId,
  r.amount AS amount,
  r.occurredAt AS occurredAt
ORDER BY eventId;
```

Hai hàng dự kiến:

| fromAccount | toAccount | eventId | amount |
| --- | --- | --- | ---: |
| GE004-A | GE004-B | GE004-T001 | 200000 |
| GE004-A | GE004-B | GE004-T002 | 350000 |

`MATCH` không tự chọn một cạnh đại diện và cũng không loại bớt cạnh song song. Mỗi relationship khớp mẫu có thể đóng góp một hàng kết quả.

### 4.3. Đếm **số cạnh** và **số nút đích**

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]->(b:Account)
RETURN
  count(r) AS transferCount,
  count(DISTINCT b) AS distinctDestinations,
  sum(r.amount) AS totalTransferred;
```

Với dữ liệu khởi tạo chưa thay đổi:

| transferCount | distinctDestinations | totalTransferred |
| ---: | ---: | ---: |
| 2 | 1 | 550000 |

`count(r)` đếm **hai relationship**; `count(DISTINCT b)` đếm **một nút B** được nối đến. Đây là hai phép đo khác nhau. Nếu hỏi “A đã chuyển bao nhiêu lần?”, dùng số cạnh/sự kiện. Nếu hỏi “A đã chuyển cho bao nhiêu tài khoản khác nhau?”, dùng số nút đích duy nhất.

### 4.4. Truy vấn không ràng buộc hướng

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]-
      (other:Account)
RETURN
  r.eventId AS eventId,
  startNode(r).accountId AS actualFrom,
  endNode(r).accountId AS actualTo
ORDER BY eventId;
```

Vì mẫu `-[r:TRANSFERRED]-` không chỉ định chiều, truy vấn từ A có thể thấy **cả ba giao dịch** A→B và B→A. Tuy nhiên, dữ liệu vẫn lưu chiều gốc; hai hàm `startNode(r)` và `endNode(r)` trả về đầu mút theo chiều thực sự của mỗi cạnh.

**Cẩn thận với đếm kết quả:** Khi cả hai biến đầu mút đều chưa được ràng buộc và sử dụng mẫu không có hướng, trình khớp mẫu có thể biểu diễn cùng cạnh qua các cách gán biến đối xứng. Khi cần thống kê mỗi relationship chính xác một lần, hãy chỉ định hướng rõ ràng hoặc chuẩn hóa cách đếm theo danh tính cạnh, thay vì suy số cạnh trực tiếp từ số hàng của một mẫu không hướng rộng.

## 5. Phát hiện nhiều quan hệ giữa cùng cặp nút

### 5.1. Tìm các cặp có nhiều cạnh cùng type và cùng hướng

```cypher
MATCH (from)-[r:TRANSFERRED]->(to)
WITH from, to, count(r) AS relationshipCount
WHERE relationshipCount > 1
RETURN
  from.accountId AS fromId,
  to.accountId AS toId,
  relationshipCount
ORDER BY relationshipCount DESC;
```

Nếu chỉ có dữ liệu thực hành ở mục 4, kết quả sẽ chứa cặp **GE004-A → GE004-B** với `relationshipCount = 2`.

Truy vấn này phù hợp với câu hỏi: “Những cặp nút nào có hơn một cạnh `TRANSFERRED` đi theo cùng hướng?”. Nó **không chứng minh các cạnh là trùng lỗi**: với giao dịch, mỗi cạnh mang `eventId` khác nhau.

Để tìm các trường hợp nhiều cạnh bất kể type, nhưng vẫn phân nhóm theo **cùng hướng và cùng type**:

```cypher
MATCH (from)-[r]->(to)
WITH from, to, type(r) AS relationshipType,
     count(r) AS relationshipCount
WHERE relationshipCount > 1
RETURN
  elementId(from) AS startElementId,
  elementId(to) AS endElementId,
  relationshipType,
  relationshipCount
ORDER BY relationshipCount DESC;
```

`elementId(n)` ở đây chỉ dùng **chẩn đoán trong kết quả truy vấn**. Không nên dùng nó làm ID nghiệp vụ dài hạn hoặc khóa trao đổi giữa hệ thống; hãy lưu mã thực thể riêng như `accountId`.

### 5.2. Kiểm tra trùng theo định danh sự kiện

Một nghiệp vụ chuyển tiền cần phân biệt “hai lần chuyển giữa cùng tài khoản” với “cùng một sự kiện bị nhập hai lần”. Kiểm tra `eventId`:

```cypher
MATCH ()-[r:TRANSFERRED]->()
WHERE r.eventId IS NOT NULL
WITH r.eventId AS eventId, count(r) AS copies
WHERE copies > 1
RETURN eventId, copies
ORDER BY copies DESC;
```

Nếu cùng một `eventId` xuất hiện trên nhiều relationship, đó là **dấu hiệu cần điều tra**. Không nên tự xóa chỉ dựa trên mẫu đếm vì còn phải xác minh dữ liệu đầu vào và nguồn sự kiện.

### 5.3. Lọc theo thời gian và nội dung

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]->
      (b:Account {accountId: 'GE004-B'})
WHERE r.occurredAt >= datetime('2026-01-11T00:00:00+07:00')
RETURN r.eventId AS eventId, r.amount AS amount
ORDER BY r.occurredAt;
```

Kết quả dự kiến: chỉ `GE004-T002`. Điều này cho thấy các cạnh song song có thể được **truy vấn theo property của từng sự kiện**, thay vì chỉ theo cặp nút.

## 6. Vòng tự nối (self-loop) là gì?

**Self-loop** là relationship có **start node và end node trùng nhau**. Neo4j cho phép self-loop; quan hệ vẫn có type, chiều lưu trữ và property.

```text
          ┌── [:CAN_TRANSITION_TO {event: 'RETRY'}] ──┐
          │                                          │
          ▼                                          │
       (:State {code: 'WAITING'}) ────────────────────┘
```

Ví dụ trên mô tả một trạng thái workflow `WAITING` có thể chuyển **trở lại chính trạng thái `WAITING`** khi xảy ra hành động thử lại. Một self-loop có **hai đầu mút về vai trò**, dù hai vai trò cùng tham chiếu **một node**.

### 6.1. Tạo và đọc self-loop

```cypher
CREATE (s:WorkflowState {
  code: 'GE004-WAITING',
  description: 'Đang chờ xử lý'
})
CREATE (s)-[:CAN_TRANSITION_TO {
  event: 'RETRY',
  maxAttempts: 3
}]->(s)
RETURN s;
```

Đọc self-loop:

```cypher
MATCH (s:WorkflowState {code: 'GE004-WAITING'})
      -[r:CAN_TRANSITION_TO]->(s)
RETURN
  type(r) AS type,
  startNode(r).code AS startState,
  endNode(r).code AS endState,
  r.event AS event,
  r.maxAttempts AS maxAttempts;
```

Kết quả:

| type | startState | endState | event | maxAttempts |
| --- | --- | --- | --- | ---: |
| CAN_TRANSITION_TO | GE004-WAITING | GE004-WAITING | RETRY | 3 |

Lệnh `MATCH` dùng cùng biến `s` ở hai đầu nên bắt buộc relationship phải nối **nút `s` với chính `s`**. Kiểm tra thêm bằng biểu thức:

```cypher
MATCH (s:WorkflowState {code: 'GE004-WAITING'})
      -[r:CAN_TRANSITION_TO]->(s)
RETURN startNode(r) = endNode(r) AS isSelfLoop;
```

Giá trị dự kiến là `true`.

### 6.2. Một số self-loop có ý nghĩa thực tế

| Miền bài toán | Mẫu | Khi nào hợp lý? |
| --- | --- | --- |
| Máy trạng thái/workflow | `(s)-[:CAN_TRANSITION_TO]->(s)` | Trạng thái có thể được thử lại mà chưa đổi sang trạng thái mới |
| Hạ tầng mạng | `(device)-[:CONNECTS_TO]->(device)` | Thiết bị có kết nối loopback hoặc đường kết nối tự quay về chính thiết bị trong mô hình cụ thể |
| Phụ thuộc phần mềm | `(module)-[:DEPENDS_ON]->(module)` | Có thể biểu thị phụ thuộc vào chính mình, thường là dấu hiệu lỗi cần kiểm tra |
| Mạng xã hội | `(u)-[:FOLLOWS]->(u)` | Thường nên cấm nếu nghiệp vụ không cho phép theo dõi chính mình |
| Thực thể phân cấp | `(person)-[:MANAGES]->(person)` | Thường không hợp lệ khi một người không được tự quản lý chính mình |

**Self-loop hợp lệ về cấu trúc** không đồng nghĩa **hợp lệ trong mọi nghiệp vụ**. Hãy đặt quy tắc theo type: cho phép `CAN_TRANSITION_TO` tự nối trong một số trạng thái, nhưng từ chối `MANAGES` tự nối nếu mô hình tổ chức không cho phép.

### 6.3. Truy vấn phát hiện self-loop trong toàn đồ thị

```cypher
MATCH (n)-[r]->(n)
RETURN
  type(r) AS relationshipType,
  elementId(n) AS nodeElementId,
  properties(n) AS nodeProperties,
  properties(r) AS relationshipProperties
LIMIT 100;
```

Truy vấn chỉ dùng để **khảo sát** và nên giới hạn kết quả ở đồ thị lớn. Nếu muốn kiểm tra một loại cụ thể:

```cypher
MATCH (p:Person)-[r:FOLLOWS]->(p)
RETURN p.personId AS personId, count(r) AS selfFollowCount;
```

Lưu ý: do có `count(r)` và không có `GROUP BY` tường minh, Cypher nhóm theo các biểu thức không tổng hợp trong `RETURN`, ở đây là `p.personId`. Nếu không có nút `Person` tự theo dõi, truy vấn sẽ không trả về hàng cho mẫu đó.

## 7. Quan hệ song song kết hợp self-loop

Một nút có thể có **nhiều self-loop**, kể cả cùng type:

```text
(:State {code: 'WAITING'})
     ↺ [:CAN_TRANSITION_TO {event: 'RETRY'}]
     ↺ [:CAN_TRANSITION_TO {event: 'RECHECK'}]
```

Cypher:

```cypher
MATCH (s:WorkflowState {code: 'GE004-WAITING'})
CREATE (s)-[:CAN_TRANSITION_TO {
  event: 'RECHECK',
  maxAttempts: 1
}]->(s)
RETURN s;
```

Sau khi chạy thêm lệnh này **một lần**, nút `GE004-WAITING` có hai self-loop cùng type `CAN_TRANSITION_TO`, nhưng khác `event`:

```cypher
MATCH (s:WorkflowState {code: 'GE004-WAITING'})
      -[r:CAN_TRANSITION_TO]->(s)
RETURN count(r) AS selfLoopCount,
       collect(r.event) AS events;
```

Dự kiến `selfLoopCount = 2` và `events` chứa `RETRY`, `RECHECK` (không dựa vào thứ tự phần tử nếu không có `ORDER BY` thích hợp).

Nếu nghiệp vụ yêu cầu **mỗi loại hành động chỉ có một self-loop trên cùng trạng thái**, cần quy tắc ghi hoặc định danh sự kiện. Neo4j không tự suy ra tính duy nhất từ cặp nút + type + property `event`.

## 8. Tác động đến truy vấn và phân tích đường đi

### 8.1. Nhiều cạnh có thể tạo nhiều hàng kết quả

Giả sử:

```text
(A) -- r1:TRANSFERRED --> (B)
(A) -- r2:TRANSFERRED --> (B)
```

Truy vấn:

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]->
      (b:Account {accountId: 'GE004-B'})
RETURN a.accountId AS fromId, b.accountId AS toId;
```

Trên dữ liệu mục 4, câu lệnh có **hai hàng** cùng `fromId` và `toId` vì khớp hai relationship khác nhau. Nếu câu hỏi chỉ quan tâm **các cặp tài khoản có liên kết**, dùng:

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[:TRANSFERRED]->
      (b:Account)
RETURN DISTINCT a.accountId AS fromId, b.accountId AS toId;
```

`DISTINCT` khử các hàng có cùng giá trị chiếu ra. Nó **không xóa relationship** và cũng không nên dùng để “sửa” nghiệp vụ cần đếm từng giao dịch.

### 8.2. Hai đường đi có cùng chuỗi nút nhưng khác relationship

Một *path* trong Neo4j chứa trình tự các nút **và** các relationship đã đi qua. Nếu A có hai cạnh khác nhau đến B, có thể có **hai đường đi một bước** A→B:

```cypher
MATCH p = (a:Account {accountId: 'GE004-A'})
          -[:TRANSFERRED]->(b:Account {accountId: 'GE004-B'})
RETURN
  length(p) AS numberOfHops,
  [r IN relationships(p) | r.eventId] AS traversedEvents
ORDER BY traversedEvents;
```

Kết quả dự kiến gồm đường đi dùng `GE004-T001` và đường đi dùng `GE004-T002`. Hai đường đi này có **cùng hai nút** nhưng **khác relationship**; nếu bài toán tối ưu đường đi chỉ quan tâm liên thông, bạn phải cân nhắc cách xử lý các cạnh song song.

### 8.3. Self-loop tạo bước đi mà không đổi nút

Một self-loop đóng góp **một quan hệ/bước** vào đường đi, nhưng **không chuyển sang nút khác**. Ví dụ đường đi từ trạng thái `WAITING` trở về chính nó theo `CAN_TRANSITION_TO` có thể là đường đi độ dài 1.

Với truy vấn độ dài biến thiên, vòng tự nối và cạnh song song có thể làm tăng số đường đi khớp. Cần quyết định:

- Có cho phép xét self-loop khi phân tích đường đi không?
- Quan tâm **từng sự kiện cạnh** hay chỉ quan tâm nút có thể tới?
- Hướng của type có mang ý nghĩa cần giữ không?
- Nên giới hạn độ dài hoặc tập nút/quan hệ trước khi duyệt không?

Ví dụ giới hạn số bước:

```cypher
MATCH p = (a:Account {accountId: 'GE004-A'})
          -[:TRANSFERRED*1..2]->
          (b:Account {accountId: 'GE004-B'})
RETURN length(p) AS hops,
       [r IN relationships(p) | r.eventId] AS events;
```

`*1..2` là cú pháp đường đi độ dài biến thiên truyền thống trong Cypher, phù hợp để minh họa giới hạn 1–2 quan hệ. Neo4j/Cypher mới còn có các biểu thức đường đi định lượng; lựa chọn phụ thuộc phiên bản. Ở dữ liệu mẫu, hai cạnh song song một bước góp phần tạo **hai path khác nhau**.

**Hiệu năng:** Duyệt đồ thị có nhiều cạnh song song hoặc self-loop có thể làm tăng số kết quả/nhánh duyệt. Khi tối ưu, ưu tiên bắt đầu ở nút có ID cụ thể, chỉ rõ type và hướng, giới hạn số bước, rồi kiểm tra `EXPLAIN`/`PROFILE`.

## 9. Chọn relationship hay nút sự kiện trung gian?

Mặc dù Neo4j hỗ trợ nhiều relationship giữa hai nút, **không phải mọi hành động lặp lại đều nên được mô hình hóa thành nhiều cạnh**.

### 9.1. Mô hình dùng relationship có thuộc tính

```text
(:Account A)
     ├──[:TRANSFERRED {eventId: 'T001', amount: 200000}]──→ (:Account B)
     └──[:TRANSFERRED {eventId: 'T002', amount: 350000}]──→ (:Account B)
```

Phù hợp khi mỗi sự kiện có tập thuộc tính vừa phải, chủ yếu cần đọc theo hai đầu mút, và **bản thân sự kiện không cần nhiều relationship khác**.

### 9.2. Mô hình dùng nút sự kiện

```text
(:Account A)
   ├──[:SENT]──→ (:Transfer {eventId: 'T001'}) ──[:TO]──→ (:Account B)
   └──[:SENT]──→ (:Transfer {eventId: 'T002'}) ──[:TO]──→ (:Account B)
```

Khi mỗi giao dịch có trạng thái, kiểm toán, phí, kiểm tra gian lận, chứng từ, quy trình phê duyệt hay nhiều nút liên quan, hãy cân nhắc **nút `Transfer`** có định danh riêng.

| Tiêu chí | Nhiều relationship | Nút sự kiện trung gian |
| --- | --- | --- |
| Mô hình ngắn gọn | Thường ngắn hơn với dữ liệu sự kiện đơn giản | Cần thêm nút và các quan hệ |
| Chi tiết nhiều trường | Có thể lưu property trên cạnh | Dễ mở rộng thuộc tính và liên kết |
| Sự kiện kết nối thêm thực thể khác | Bất tiện nếu muốn nối relationship đến nút khác | Thuận tiện vì sự kiện đã là nút |
| Truy vấn theo hai đầu mút | Rất trực tiếp | Cần đi qua nút sự kiện |
| Danh tính và vòng đời độc lập | Có thể dùng mã sự kiện trên relationship | Rõ ràng hơn nếu sự kiện là thực thể nghiệp vụ |

**Nguyên tắc:** Chọn mô hình từ **yêu cầu truy vấn và vòng đời dữ liệu**. Không tách sự kiện thành node chỉ vì hai cạnh có cùng đầu–cuối; cũng không ép mọi sự kiện nhiều thông tin thành cạnh chỉ để giảm số nút.

## 10. Kiểm soát tạo trùng bằng CREATE, MERGE và định danh

### 10.1. CREATE không kiểm tra trùng

Với hai nút đã xác định:

```cypher
MATCH (a:Person {personId: $followerId})
MATCH (b:Person {personId: $followedId})
CREATE (a)-[:FOLLOWS]->(b);
```

Mỗi lần thực thi thành công, câu lệnh tạo **một relationship mới**. Đây là lựa chọn đúng nếu mỗi lần tạo đại diện cho **một sự kiện mới**; nhưng không phù hợp cho liên kết trạng thái chỉ nên có một bản ghi.

### 10.2. MERGE cho mô hình liên kết đơn

Giả sử mỗi người chỉ theo dõi một người khác qua tối đa **một** relationship `FOLLOWS` cùng hướng, và nghiệp vụ cấm tự theo dõi:

```cypher
MATCH (a:Person {personId: $followerId})
MATCH (b:Person {personId: $followedId})
WHERE a <> b
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.since = date()
RETURN r;
```

Câu lệnh này:

1. Tìm hai nút theo **định danh nghiệp vụ**.
2. Không xử lý nếu hai biến trỏ vào cùng một nút.
3. `MERGE` cố khớp cạnh `FOLLOWS` **đúng type, đúng hướng và hai nút**, nếu không có thì tạo.
4. `ON CREATE SET` chỉ gán ngày khi cạnh vừa được tạo.

**Giới hạn quan trọng:** `MERGE` **không tự dọn** các cạnh trùng đã tồn tại. Khi nhiều giao dịch chạy đồng thời, `MERGE` cũng không thay thế cơ chế ràng buộc/đồng bộ cần thiết để bảo đảm mọi quy tắc duy nhất. Hãy thiết kế giao dịch ghi và bảo vệ định danh theo nghiệp vụ.

### 10.3. Định danh sự kiện và constraint trên relationship

Với sự kiện có mã `eventId`, Neo4j hỗ trợ uniqueness constraint trên property của relationship trong các phiên bản phù hợp, ví dụ cú pháp Neo4j 5:

```cypher
CREATE CONSTRAINT transferred_event_id_unique IF NOT EXISTS
FOR ()-[r:TRANSFERRED]-()
REQUIRE r.eventId IS UNIQUE;
```

Constraint này giới hạn **các relationship `TRANSFERRED` có cùng giá trị `eventId`**: nếu đã tồn tại một mã, không thể tạo một relationship thứ hai cùng type mang chính mã đó.

Phân biệt:

- **Giới hạn theo `eventId`** không có nghĩa “mỗi cặp A→B chỉ được có một cạnh”. Hai giao dịch khác ID vẫn được phép.
- **Uniqueness constraint** thường không mặc định yêu cầu mọi relationship của type đó phải có `eventId`. Các cơ chế bắt buộc property tồn tại hoặc relationship key phụ thuộc phiên bản/edition.
- Với các ràng buộc nâng cao hoặc phiên bản cũ, phải xác minh **tính năng và cú pháp** của Neo4j đang dùng.

Một quy trình nhập giao dịch có thể dùng `eventId` làm khóa idempotency để tránh ghi lại cùng sự kiện. Nhưng nếu mỗi lần chuyển tiền thực sự khác nhau, cần cấp **mã mới**, không tái sử dụng mã của lần trước.

### 10.4. Dùng MERGE theo mã sự kiện đã có

Khi đã có uniqueness constraint phù hợp và tìm được hai nút:

```cypher
MATCH (a:Account {accountId: $fromAccountId})
MATCH (b:Account {accountId: $toAccountId})
MERGE (a)-[r:TRANSFERRED {eventId: $eventId}]->(b)
ON CREATE SET
  r.amount = $amount,
  r.occurredAt = datetime()
RETURN r.eventId AS eventId, r.amount AS amount;
```

**Lưu ý nghiệp vụ:** `MERGE` khớp cả **hai đầu mút, hướng, type và `eventId`**. Nếu `eventId` đã được gắn cho giao dịch **khác hai đầu mút**, câu lệnh có thể gặp lỗi constraint thay vì tự “chuyển” sự kiện sang cặp mới. Đây thường là điều nên phát hiện, bởi cùng mã sự kiện không được âm thầm đổi người gửi/người nhận. Ứng dụng cần xử lý lỗi và quy trình đối soát phù hợp.

## 11. Phát hiện và ngăn self-loop ngoài ý muốn

### 11.1. Kiểm tra trước khi tạo

Ví dụ không cho người dùng tự theo dõi:

```cypher
MATCH (a:Person {personId: $followerId})
MATCH (b:Person {personId: $followedId})
WHERE a <> b
MERGE (a)-[r:FOLLOWS]->(b)
RETURN r;
```

`a <> b` so sánh **danh tính hai nút**, không chỉ so sánh các chuỗi tên hiển thị. Nếu hai ID cùng trỏ vào một nút, phần `WHERE` loại bỏ trường hợp self-loop.

Nếu muốn kiểm tra ngay từ API trước khi gửi truy vấn, có thể so sánh `followerId` và `followedId` ở tầng ứng dụng, nhưng vẫn nên kiểm tra khi ghi để giữ an toàn nếu dữ liệu đầu vào đến từ nhiều nguồn.

### 11.2. Tìm dữ liệu có dấu hiệu vi phạm

```cypher
MATCH (p:Person)-[r:FOLLOWS]->(p)
RETURN p.personId AS personId,
       count(r) AS selfFollows;
```

Với type `MANAGES`:

```cypher
MATCH (p:Person)-[r:MANAGES]->(p)
RETURN p.personId AS managerId, count(r) AS selfManagementLinks;
```

Truy vấn chỉ **phát hiện**. Nếu dữ liệu đang sử dụng trong sản xuất, không nên xóa hàng loạt trước khi xác nhận quy tắc nghiệp vụ, nguồn phát sinh và tác động lên các hệ thống đang đọc cạnh.

### 11.3. Self-loop và chu trình dài hơn là hai trường hợp khác nhau

**Self-loop** có độ dài **một cạnh**:

```text
A ──[:DEPENDS_ON]──→ A
```

**Chu trình** (*cycle*) có thể gồm nhiều nút, ví dụ:

```text
A ──[:DEPENDS_ON]──→ B
↑                     │
└────[:DEPENDS_ON]─────┘
```

Truy vấn phát hiện self-loop chỉ tìm dạng `A → A`. Nó **không** phát hiện hết các chu trình dài hơn như `A → B → A`. Khi kiểm tra phụ thuộc vòng trong hệ thống, cần thêm các truy vấn đường đi/thuật toán đồ thị phù hợp, chứ không dừng ở kiểm tra `startNode(r) = endNode(r)`.

## 12. Những trường hợp mô hình cần đặc biệt lưu ý

### 12.1. “Bạn bè” không nhất thiết là hai cạnh có hướng

Với `FRIENDS_WITH` mang ý nghĩa đối xứng, Neo4j vẫn lưu một **hướng kỹ thuật**. Có thể chọn:

- Lưu **một cạnh** và dùng mẫu `(a)-[:FRIENDS_WITH]-(b)` để truy vấn cả hai chiều; cần quy ước tránh trùng theo cặp không thứ tự.
- Lưu **hai cạnh ngược chiều** nếu mỗi cạnh biểu diễn một hành động, trạng thái xác nhận hoặc quyền riêng biệt.

Đừng mặc định lưu hai cạnh chỉ vì tình bạn mang ý nghĩa “hai chiều”; điều này có thể khiến số lượng kết nối bị đếm gấp đôi nếu truy vấn thống kê không chuẩn hóa.

### 12.2. Nhiều phiên giao dịch giữa cùng cặp nút

Một `Customer` có thể đặt nhiều `Order`. Cân nhắc mô hình:

```text
(:Customer)-[:PLACED]->(:Order)-[:CONTAINS]->(:Product)
```

Mỗi đơn hàng có **nút `Order` riêng**, nên không cần tạo nhiều cạnh `PLACED` đến **cùng một nút đơn** chỉ để biểu diễn các lần đặt khác nhau. Nếu một khách hàng có hai đơn, tạo **hai node Order**, mỗi node mang một mã nghiệp vụ, rồi nối bằng relationship phù hợp.

### 12.3. Quan hệ kiểu “đã tham gia sự kiện”

Nếu cùng người tham dự cùng sự kiện nhiều ngày khác nhau, có thể dùng nhiều cạnh `ATTENDED` với property thời gian. Tuy nhiên, nếu mỗi lần tham dự còn có vé, check-in, thanh toán, chứng chỉ, lịch sử sửa đổi, một nút `Attendance` riêng sẽ giúp giữ danh tính và vòng đời của từng lần tham dự.

### 12.4. Nhập dữ liệu lặp và tái chạy job

Khi chạy lại job nhập dữ liệu, bản ghi mới có thể tạo:

1. **Node trùng** vì `CREATE` liên tục tạo lại người/công ty.
2. **Relationship trùng** vì `CREATE` liên tục nối cùng hai node.
3. **Đường đi tăng bất thường** vì graph có nhiều cạnh dư.

Để quản lý, dùng **ID nghiệp vụ ổn định** cho node, constraint phù hợp, câu lệnh ghi có tính idempotent theo **ý nghĩa nghiệp vụ** và quy trình đối soát. Đừng dùng `DISTINCT` ở mọi truy vấn để che giấu dữ liệu trùng thực sự.

### 12.5. Mô hình hóa và ánh xạ Java

Khi dùng Neo4j Java Driver, hãy truyền ID qua **tham số** thay vì nối chuỗi Cypher:

```cypher
MATCH (a:Account {accountId: $fromId})
MATCH (b:Account {accountId: $toId})
MERGE (a)-[r:TRANSFERRED {eventId: $eventId}]->(b)
ON CREATE SET r.amount = $amount
RETURN r;
```

Ứng dụng phải xác định rõ thao tác là **tạo sự kiện mới** hay **thử ghi lại sự kiện cũ**. Với Spring Data Neo4j, cần xem xét kiểu ánh xạ quan hệ và thuộc tính quan hệ để phản ánh **nhiều cạnh cùng loại** hoặc **self-loop** nếu nghiệp vụ sử dụng; đặc biệt không được giả định một cặp entity chỉ có một relationship trong cơ sở dữ liệu.

## 13. Lưu ý về index, constraint và hiệu năng

Trong Neo4j, **label** của node và **type** của relationship cùng với property có thể tham gia vào các cấu hình index/constraint được hỗ trợ. Chúng giúp tìm phần tử theo thuộc tính và bảo vệ một số quy tắc dữ liệu, nhưng cần phân biệt:

| Mục tiêu | Cơ chế thường áp dụng | Giới hạn cần nhớ |
| --- | --- | --- |
| Không trùng mã tài khoản | Uniqueness constraint trên `Account.accountId` | Chỉ áp dụng cho nút mang nhãn `Account` trong phạm vi constraint |
| Không trùng mã giao dịch | Uniqueness constraint trên `TRANSFERRED.eventId` nếu phiên bản hỗ trợ | Hai lần chuyển khác mã vẫn có thể cùng cặp đầu–cuối |
| Không tự theo dõi | Điều kiện `a <> b` trong truy vấn ghi và quy tắc ứng dụng | Không tự động suy ra từ type `FOLLOWS` |
| Chỉ một cạnh FOLLOWS cho mỗi cặp có hướng | Quy ước ID/định danh liên kết, giao dịch ghi, kiểm soát trùng | `MERGE` đơn thuần không làm sạch cạnh trùng cũ và không thay thế mọi cơ chế đồng thời |
| Tra cứu nhanh theo property | Index phù hợp và truy vấn có điều kiện | Cần kiểm tra kế hoạch với `EXPLAIN`/`PROFILE` và dữ liệu thực |
| Tránh bùng nổ đường đi | Lọc nút đầu, type, hướng và giới hạn độ dài | Self-loop và cạnh song song vẫn có thể làm tăng số đường đi hợp lệ |

Với đồ thị lớn, truy vấn khảo sát toàn bộ như `MATCH (a)-[r]->(b)` có thể duyệt rất nhiều cạnh. Hãy khoanh vùng theo nhãn, ID, relationship type và thời gian nếu phù hợp:

```cypher
EXPLAIN
MATCH (a:Account {accountId: $accountId})-[r:TRANSFERRED]->(b)
WHERE r.occurredAt >= $fromDateTime
RETURN b.accountId AS destination, count(r) AS transferCount;
```

`EXPLAIN` lập kế hoạch, không thực thi câu lệnh. Khi truyền `$fromDateTime`, ứng dụng nên truyền **kiểu thời gian phù hợp**, thay vì phụ thuộc vào so sánh chuỗi không đồng nhất. Sự lựa chọn index thực tế tùy phiên bản và thống kê dữ liệu.

## 14. Bài tập thực hành có đáp án

Các câu hỏi sau giả định dữ liệu ở mục 4 và một self-loop `RETRY` ở mục 6 đã được tạo, chưa thực thi các thao tác ghi khác ngoài phạm vi được nói đến.

### Bài 1. Đếm số lần chuyển và số người nhận

Tài khoản `GE004-A` có hai cạnh `TRANSFERRED` đến `GE004-B`. Viết truy vấn trả về **số giao dịch** và **số tài khoản đích phân biệt**.

**Đáp án:**

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]->(b:Account)
RETURN count(r) AS transactions,
       count(DISTINCT b) AS distinctRecipients;
```

Kết quả: `transactions = 2`, `distinctRecipients = 1`.

### Bài 2. Phân biệt cạnh song song hợp lệ và cạnh trùng lỗi

Cho:

```text
A --[:TRANSFERRED {eventId: 'T1'}]--> B
A --[:TRANSFERRED {eventId: 'T2'}]--> B
A --[:FOLLOWS]---------------------> B
A --[:FOLLOWS]---------------------> B
```

Hỏi: Tại sao không nên xóa tất cả cạnh “bị lặp cặp đầu–cuối”?

**Đáp án:** Hai `TRANSFERRED` có `eventId` riêng biểu thị **hai giao dịch hợp lệ**. Hai `FOLLOWS` cùng type/hướng/đầu–cuối có thể là **hai bản ghi trùng**, nếu nghiệp vụ chỉ cho một quan hệ theo dõi mỗi cặp. Phải đánh giá theo loại quan hệ và định danh nghiệp vụ, không chỉ theo cặp nút.

### Bài 3. Phát hiện người tự theo dõi

Viết truy vấn tìm các node `Person` có cạnh `FOLLOWS` nối chính chúng.

**Đáp án:**

```cypher
MATCH (p:Person)-[r:FOLLOWS]->(p)
RETURN p.personId AS personId, count(r) AS countOfSelfFollows;
```

### Bài 4. Truy vấn các giao dịch theo cả hai hướng

Từ tài khoản `GE004-A`, liệt kê mọi giao dịch `TRANSFERRED` liên quan đến nó, bao gồm **gửi và nhận**, giữ đúng hướng thực tế trong kết quả.

**Đáp án:**

```cypher
MATCH (a:Account {accountId: 'GE004-A'})-[r:TRANSFERRED]-
      (other:Account)
RETURN
  r.eventId AS eventId,
  startNode(r).accountId AS sender,
  endNode(r).accountId AS receiver
ORDER BY eventId;
```

Với dữ liệu mẫu, sẽ có ba giao dịch `T001`, `T002`, `T003` theo đúng hai chiều lưu.

### Bài 5. Quyết định mô hình

Hệ thống lưu nhiều lần đặt phòng của một người tại cùng khách sạn, mỗi lần có mã đặt, trạng thái, hóa đơn, thanh toán và hủy/hoàn tiền riêng. Nên chọn nhiều `BOOKED` relationship giữa `Person` và `Hotel` hay nút `Booking` riêng?

**Đáp án gợi ý:** Nút `Booking` có định danh riêng thường phù hợp hơn vì mỗi lần đặt có vòng đời và nhiều đối tượng liên kết. Ví dụ:

```text
(:Person)-[:MADE]->(:Booking)-[:AT_HOTEL]->(:Hotel)
```

Có thể nối thêm `(:Booking)-[:HAS_PAYMENT]->(:Payment)` và các quan hệ khác mà không làm phức tạp property của một cạnh đơn lẻ.

## 15. Tổng kết

- **Quan hệ song song** cho phép nhiều relationship độc lập giữa cùng cặp nút; chúng có thể cùng hoặc khác type, cùng hoặc khác hướng tùy định nghĩa đang xét.
- **Self-loop** có hai đầu mút **trùng một nút**; đây là cấu trúc hợp lệ trong property graph, nhưng phải kiểm tra sự phù hợp với nghiệp vụ.
- **Cạnh song song hợp lệ** thường đại diện cho nhiều sự kiện khác nhau; **cạnh trùng lỗi** xảy ra khi một sự thật nghiệp vụ bị ghi lại ngoài ý muốn.
- `CREATE` luôn tạo thêm relationship; `MERGE` tìm hoặc tạo theo mẫu và không tự loại cạnh trùng đã có. Dùng ID nghiệp vụ, constraint phù hợp và quy tắc ghi để kiểm soát nhập trùng.
- `count(r)` đếm cạnh, còn `count(DISTINCT b)` đếm nút đích khác nhau. `DISTINCT` thay đổi kết quả truy vấn, **không xóa dữ liệu trùng**.
- Cạnh song song và self-loop ảnh hưởng đến số hàng kết quả, số đường đi và hiệu năng duyệt đồ thị; cần chọn hướng, type, điều kiện lọc và giới hạn đường đi đúng mục tiêu.
- Với sự kiện có danh tính, vòng đời và nhiều liên kết riêng, cân nhắc chuyển từ relationship có property sang **nút sự kiện trung gian**.

Nắm chắc các trường hợp biên này giúp bạn phát triển mô hình Neo4j đáng tin cậy, viết truy vấn Cypher đúng ngữ nghĩa, nhập dữ liệu có kiểm soát, tối ưu truy vấn và tích hợp đồ thị vào ứng dụng Java Driver hoặc Spring Data Neo4j.
