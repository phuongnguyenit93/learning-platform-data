# Dữ liệu trùng, vi phạm ràng buộc và MERGE không như mong đợi

## 1. Vì sao MERGE không phải “lệnh chống trùng tuyệt đối”?

Trong Neo4j, dữ liệu được tổ chức theo **property graph**: node có label và property, relationship có type, hướng và property. Ứng dụng dùng Cypher để tìm, tạo và cập nhật đồ thị; Java Driver hoặc Spring Data Neo4j gửi những truy vấn đó vào transaction.

Khi tích hợp dữ liệu, nhiều nhóm chọn `MERGE` với mong muốn:

- Nếu node/relationship đã có thì sử dụng lại.
- Nếu chưa có thì tạo.
- Dù chạy lại bao nhiêu lần, graph cũng không bị trùng.
- Nếu có constraint, Neo4j sẽ tự kết hợp mọi thực thể giống nhau.
- Nếu hai worker ghi đồng thời, tất cả sẽ tự thành công mà không cần xử lý lỗi.

**Chỉ hai ý đầu đúng với phạm vi mẫu mà MERGE khớp; các kỳ vọng còn lại không tự được bảo đảm.**

Ví dụ:

~~~cypher
MERGE (c:Customer {customerId: $customerId})
RETURN c;
~~~

Cypher tìm node `Customer` khớp **toàn bộ mẫu và property được chỉ định**; nếu không thấy, nó cố tạo một node mới. Nhưng nếu dữ liệu có sẵn **hai node cùng `customerId`**, truy vấn có thể khớp nhiều node, **không hợp nhất** chúng thành một.

Nếu hai transaction đồng thời chạy `MERGE` mà **không có uniqueness constraint phù hợp**, chúng có thể cùng không tìm thấy node và tạo hai bản ghi giống khóa nghiệp vụ.

Bài này tập trung vào xử lý sự cố: **nhận diện trùng ở đâu, phân biệt nguyên nhân, đọc các constraint/index, sửa Cypher, bảo vệ ghi đồng thời và làm sạch dữ liệu an toàn**. Những ví dụ dùng mô hình Customer, Order, User và relationship FOLLOWS; thay label/type cho phù hợp ứng dụng thực tế.

## 2. Bản đồ triệu chứng và nguyên nhân thường gặp

| Triệu chứng | Khả năng cần kiểm tra trước | Hướng xử lý |
|---|---|---|
| Có hai node `Customer` cùng email | Không có unique key; khác chuẩn hóa; import song song | Xác định business key, tìm trùng và đặt constraint |
| `MERGE` báo constraint validation | Mẫu MERGE không khớp node cũ nhưng CREATE vi phạm unique key | Thu hẹp khóa MERGE, kiểm tra thuộc tính bổ sung |
| `MERGE` trả nhiều hàng | Có nhiều node/relationship cùng mẫu hoặc đầu vào nhiều hàng | Đếm node/relationship thực; kiểm tra `UNWIND`/`MATCH` |
| Cùng cặp User có hai FOLLOWS | MERGE theo property thay đổi; nhiều writer; dữ liệu cũ trùng | Khóa nhận diện cạnh ổn định, kiểm soát concurrency |
| Thực thi lại MERGE tạo bản mới | Khóa thay đổi, null/format khác, label/type khác | Chuẩn hóa input, dùng business key không đổi |
| `MERGE` không tạo gì | `MATCH` hoặc `WHERE` trước MERGE trả 0 hàng | Kiểm tra cardinality đầu vào |
| `MERGE` cố tạo cả node đã tồn tại | MERGE một mẫu đường đi chưa khớp đầy đủ | Ràng buộc node trước, MERGE relationship sau |
| Tạo constraint bị từ chối | Đã tồn tại dữ liệu trùng theo property được ràng buộc | Tìm và xử lý trùng trước migration |
| MERGE chạy chậm | Thiếu index/constraint hoặc key kém chọn lọc | Kiểm tra `EXPLAIN` và chỉ số phù hợp |
| Cập nhật bị lặp dù chỉ có một node | `SET counter = counter + 1` nằm ngoài cơ chế idempotency | Dùng command receipt và khóa lệnh ổn định |
| Driver retry nhưng request lỗi liên tục | Lỗi dữ liệu bền vững, constraint hoặc transaction conflict | Phân loại lỗi, không retry vô hạn |

**Quy trình triage:** trước tiên xác định **thực thể graph có trùng thật không**, sau đó kiểm tra **MERGE đang dùng mẫu nào**, **constraint nào đang có hiệu lực**, **đầu vào có bao nhiêu hàng**, cuối cùng mới phân tích cạnh tranh ghi.

## 3. Hiểu chính xác đơn vị khớp của MERGE

`MERGE` có nghĩa: cố **khớp toàn bộ pattern** được chỉ định; nếu không có pattern khớp, cố **tạo pattern đó**.

### 3.1. MERGE node theo một property

~~~cypher
MERGE (u:User {userId: $userId})
RETURN u.userId AS userId;
~~~

Với constraint duy nhất cho `User.userId` và giá trị `$userId` hợp lệ/ổn định, đây là điểm khởi đầu tốt để tìm hoặc tạo một User theo ID nghiệp vụ.

Tuy nhiên:

- Nếu không có constraint và nhiều transaction cùng ghi, trùng vẫn có thể xuất hiện.
- Nếu trước đó đã có hai User cùng khóa, MERGE không làm sạch chúng.
- Nếu `$userId` bị thay giữa các lần retry, mỗi giá trị là một khóa khác.
- Nếu `userId` thuộc các label khác nhau, constraint trên `:User` không tự áp dụng sang label khác.

### 3.2. MERGE theo nhiều property: tất cả đều tham gia định danh

~~~cypher
MERGE (u:User {
    userId: $userId,
    status: $status
})
RETURN u;
~~~

Giả sử node đã có `userId = 'U-100'` nhưng `status = 'ACTIVE'`. Lần sau client truyền `status = 'BLOCKED'`, toàn bộ mẫu không khớp, vì status khác nhau.

Nếu chưa có constraint, MERGE có thể tạo **User thứ hai cùng userId**. Nếu có unique constraint trên `User.userId`, lệnh tạo sẽ bị từ chối do vi phạm ràng buộc. **Cả hai đều không phải mong muốn “cập nhật status của User cũ”.**

Cách thiết kế tốt hơn:

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET u.createdAt = datetime()
SET u.status = $status
RETURN u.userId AS userId, u.status AS status;
~~~

Ở đây, `userId` là khóa định danh, còn `status` là thuộc tính **có thể thay đổi**. Câu `SET` luôn cập nhật status theo yêu cầu; điều đó hợp lý cho một phép “đặt status”, nhưng vẫn cần quy tắc thứ tự/version khi các sự kiện tới muộn.

### 3.3. ON CREATE SET và ON MATCH SET không giống nhau

~~~cypher
MERGE (p:Product {sku: $sku})
ON CREATE SET
    p.createdAt = datetime(),
    p.priceInCents = $price
ON MATCH SET
    p.lastSeenAt = datetime()
RETURN p.sku AS sku;
~~~

- `ON CREATE SET` chạy trên nhánh tạo mới.
- `ON MATCH SET` chạy trên nhánh khớp mẫu hiện có.
- `SET` không điều kiện chạy cho cả hai trường hợp khi dòng được xử lý.

`ON CREATE SET` **không phải** “chỉ chạy đúng một lần trên toàn hệ thống” nếu dữ liệu bị xóa rồi import lại với cùng khóa hoặc nếu các node với khóa tương đương đã được tạo ngoài chính sách. Cần hiểu vòng đời khóa và constraint.

### 3.4. MERGE không hợp nhất những node đã trùng

Giả sử có hai node:

~~~text
(:User {userId: "U-7", name: "Lan"})  # node A
(:User {userId: "U-7", name: "Lan"})  # node B
~~~

Khi chạy:

~~~cypher
MERGE (u:User {userId: 'U-7'})
RETURN u.name AS name;
~~~

truy vấn có thể trả hai hàng cho hai node cùng khớp. Neo4j **không xóa node dư, không di chuyển relationship và không gộp property**. Việc dọn dữ liệu là một quy trình riêng, có thể ảnh hưởng các đường đi tới node bị trùng.

## 4. Đừng nhầm hàng kết quả trùng với node trùng

Một query có thể trả một Order nhiều lần vì Order có nhiều OrderLine:

~~~cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
MATCH (o)-[:HAS_LINE]->(l:OrderLine)
RETURN c.customerId AS customerId,
       o.orderId AS orderId,
       l.lineId AS lineId;
~~~

Nếu Order O1 có ba dòng hàng, O1 xuất hiện trong **ba hàng kết quả** là hoàn toàn đúng theo pattern. Điều này **không chứng minh** database có ba node Order O1.

### 4.1. Đếm entity phân biệt

~~~cypher
MATCH (o:Order)
RETURN count(o) AS rawMatches,
       count(DISTINCT o) AS distinctNodes;
~~~

Với một lần `MATCH (o:Order)` đơn giản, hai số sẽ bằng nhau. Hãy dùng phép đếm này trong truy vấn **đã mở rộng nhiều relationship** để phát hiện số hàng bị nhân:

~~~cypher
MATCH (o:Order)-[:HAS_LINE]->(l:OrderLine)
RETURN count(*) AS matchedRows,
       count(DISTINCT o) AS distinctOrders,
       count(DISTINCT l) AS distinctLines;
~~~

Nếu `matchedRows` lớn hơn số Order, đó có thể là bội số relationship hợp lệ.

### 4.2. DISTINCT thay đổi kết quả, không xóa dữ liệu

~~~cypher
MATCH (o:Order)-[:HAS_LINE]->(:OrderLine)
RETURN DISTINCT o.orderId AS orderId;
~~~

`DISTINCT` chỉ loại hàng kết quả trùng theo biểu thức trả về; nó **không gộp node thật**. Nếu có hai node Order khác nhau nhưng cùng `orderId`, câu trên vẫn có thể trả **một ID duy nhất**, khiến người quan sát bỏ sót dữ liệu trùng.

Khi debug, cần đếm **node phân biệt** và **khóa nghiệp vụ trùng** riêng.

### 4.3. OPTIONAL MATCH cũng nhân hàng

~~~cypher
MATCH (u:User {userId: $userId})
OPTIONAL MATCH (u)-[:LIKED]->(p:Post)
OPTIONAL MATCH (u)-[:FOLLOWS]->(v:User)
RETURN u.userId, p.postId, v.userId;
~~~

Nếu User thích 10 Post và theo dõi 20 User, phép ghép có thể tạo tới **200 tổ hợp hàng**. Đó không phải 200 relationship mới, mà là tích cardinality của các mẫu.

Cách giảm việc nhân hàng là tính từng tập kết quả hoặc tổng hợp ở các giai đoạn thích hợp; kiểm tra bằng `count(DISTINCT ...)` khi câu hỏi là số thực thể phân biệt. Không dùng `DISTINCT` để che lỗi mô hình vì sẽ mất khả năng phát hiện trùng thật.

## 5. Tìm node trùng bằng Cypher trước khi sửa

Chạy các truy vấn **chỉ đọc** trong môi trường được phép. Với graph lớn, scan toàn bộ có thể tốn tài nguyên; nên chạy trên bản sao/staging hoặc cửa sổ vận hành phù hợp.

### 5.1. Tìm Customer trùng theo customerId

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IS NOT NULL
WITH c.customerId AS customerId, count(c) AS nodeCount
WHERE nodeCount > 1
RETURN customerId, nodeCount
ORDER BY nodeCount DESC, customerId
LIMIT 50;
~~~

Ý nghĩa:

- Gom theo giá trị `customerId`.
- Chỉ báo nhóm có **nhiều node cùng khóa**.
- Bỏ giá trị null để nhóm null không bị coi là một business key thật.
- Giới hạn kết quả; điều này **không giới hạn toàn bộ công việc phải quét** nếu engine cần xem nhiều node.

Nếu nhãn `Customer` đã có uniqueness constraint hoạt động đúng trên `customerId`, không thể tồn tại hai node mang nhãn này với cùng giá trị `customerId` không-null đã được commit. Nếu truy vấn vẫn báo trùng, cần xác minh database/label/constraint thực sự đang áp dụng.

### 5.2. Tìm null và khóa không hợp lệ

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IS NULL
RETURN count(c) AS customersWithoutId;
~~~

~~~cypher
MATCH (c:Customer)
WHERE c.customerId IS NOT NULL
  AND trim(c.customerId) = ''
RETURN count(c) AS customersWithBlankId;
~~~

Hai mẫu giả định `customerId` là chuỗi với những node có property khác null. Nếu dữ liệu có kiểu hỗn hợp, `trim` trên giá trị không phải chuỗi có thể gây lỗi; nên kiểm tra kiểu dữ liệu và phân loại trước khi dùng hàm string.

**Uniqueness constraint** thông thường ngăn hai giá trị trùng nhau nhưng **không tự bắt buộc mọi node phải có property**. Khi nghiệp vụ bắt buộc ID, cần input validation và, với phiên bản/edition hỗ trợ, lựa chọn constraint về tồn tại hoặc key.

### 5.3. Tìm khóa chỉ khác chữ hoa, khoảng trắng

~~~cypher
MATCH (c:Customer)
WHERE c.email IS NOT NULL
WITH toLower(trim(c.email)) AS normalizedEmail,
     collect(c) AS matches
WHERE size(matches) > 1
RETURN normalizedEmail,
       size(matches) AS nodeCount,
       [c IN matches | c.customerId] AS customerIds
ORDER BY nodeCount DESC
LIMIT 50;
~~~

Đây là **truy vấn chẩn đoán**, không phải quy tắc chuẩn hóa email tuyệt đối. Trong nghiệp vụ thật, cần xem quy ước case, Unicode, khoảng trắng, nhà cung cấp email, tenant và chính sách dữ liệu; không tự gom hai địa chỉ chỉ vì trông giống nhau.

Truy vấn dùng `collect(c)` có thể tốn bộ nhớ nếu một nhóm email rất lớn. Khi chỉ cần thống kê, ưu tiên `count(*)` theo khóa đã chuẩn hóa:

~~~cypher
MATCH (c:Customer)
WHERE c.email IS NOT NULL
WITH toLower(trim(c.email)) AS normalizedEmail,
     count(*) AS nodeCount
WHERE nodeCount > 1
RETURN normalizedEmail, nodeCount
ORDER BY nodeCount DESC
LIMIT 50;
~~~

### 5.4. Tìm node trùng trong phạm vi nhiều tenant

Nếu `customerId` chỉ duy nhất **trong mỗi tenant**, không được coi hai Customer ở hai tenant khác nhau là trùng.

~~~cypher
MATCH (c:Customer)
WHERE c.tenantId IS NOT NULL
  AND c.customerId IS NOT NULL
WITH c.tenantId AS tenantId,
     c.customerId AS customerId,
     count(*) AS nodeCount
WHERE nodeCount > 1
RETURN tenantId, customerId, nodeCount
ORDER BY nodeCount DESC
LIMIT 50;
~~~

Khi xác định uniqueness constraint, phải chọn đúng **phạm vi định danh nghiệp vụ**: toàn hệ thống, theo tenant, theo nguồn nhập hay theo phiên bản.

## 6. Kiểm tra schema: constraint và index

Đối với Neo4j 5.x và các bản hỗ trợ lệnh tương ứng:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

~~~cypher
SHOW INDEXES
YIELD name, type, entityType, labelsOrTypes, properties, state
RETURN name, type, entityType, labelsOrTypes, properties, state
ORDER BY name;
~~~

**Lưu ý phiên bản:** cột hiển thị, loại constraint, khả năng tạo constraint về sự tồn tại/property type, node key/relationship key và quyền chạy lệnh có thể khác theo phiên bản hoặc edition.

### 6.1. Uniqueness constraint cho một khóa node

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

Constraint này bảo vệ các node `:Customer` có giá trị `customerId` khỏi việc tồn tại **hai giá trị không-null trùng nhau**. Nó cũng hỗ trợ việc tìm node theo khóa trong nhiều tình huống.

**Trước khi tạo:** tìm nhóm trùng. Nếu có hai Customer đang cùng `customerId`, câu tạo constraint có thể thất bại. Neo4j không tự quyết định Customer nào là bản chuẩn rồi xóa bản dư.

### 6.2. Composite uniqueness theo tenant

~~~cypher
CREATE CONSTRAINT customer_tenant_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

Cặp `(tenantId, customerId)` mới là khóa trong ví dụ. Hai tenant khác nhau có thể dùng cùng customerId nếu đó là nghiệp vụ mong muốn.

**Không nhầm composite uniqueness với hai constraint đơn lẻ.** Hai constraint độc lập:

~~~cypher
CREATE CONSTRAINT customer_tenant_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.tenantId IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT customer_external_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

sẽ áp đặt ý nghĩa **mỗi tenant chỉ có một Customer** và **mỗi customerId phải duy nhất toàn hệ thống**, thường sai với bài toán multi-tenant. Hai constraint này là ví dụ **không nên áp dụng** cho mô hình đó; không chạy chúng trên database nghiệp vụ.

### 6.3. Index thường không đồng nghĩa constraint duy nhất

Một range index trên `Customer.email` có thể giúp truy vấn lọc nhanh hơn nhưng **không ngăn** hai Customer cùng email.

Để bảo đảm tính duy nhất ở mức database, cần constraint phù hợp. Chỉ dựa vào bước Java “tìm trước rồi mới tạo” cũng không bảo đảm an toàn khi hai worker thao tác đồng thời.

### 6.4. Có constraint rồi vẫn cần kiểm tra input

Constraint không thay thế cho:

- Không cho ID null/blank.
- Chuẩn hóa chuỗi theo hợp đồng nghiệp vụ.
- Kiểm soát tenant/source.
- Xác định bản ghi cần cập nhật khi có nhiều property thay đổi.
- Xử lý lỗi uniqueness và retry tại tầng ứng dụng.

Nếu khóa nghiệp vụ phải **bắt buộc tồn tại**, tìm hiểu constraint node key/property existence tương ứng với phiên bản/edition, và vẫn validate input ở biên hệ thống.

## 7. MERGE và nhiều constraint: xung đột vì mẫu không khớp

Giả sử `:User` có constraint duy nhất trên `email` và trên `username`:

~~~cypher
CREATE CONSTRAINT user_email_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.email IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT user_username_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.username IS UNIQUE;
~~~

Database đã có:

~~~text
User A: email = "a@example.invalid", username = "alice"
User B: email = "b@example.invalid", username = "bob"
~~~

Request mới gửi email của A và username của B:

~~~cypher
MERGE (u:User {
    email: 'a@example.invalid',
    username: 'bob'
})
RETURN u;
~~~

**Không có node nào khớp cả hai property đồng thời**. MERGE không thể lấy email từ A và username từ B rồi tự hợp nhất hai User. Nó có thể cố tạo node mới, vi phạm một hoặc cả hai uniqueness constraint, rồi thất bại.

Ngay cả khi hai giá trị thuộc cùng một node nhưng một field đã được thay đổi, mẫu MERGE với cả hai field cũng có thể không khớp và gây constraint conflict.

### 7.1. Chọn một business key chính rồi kiểm tra field khác

Nếu `userId` là định danh ổn định:

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET u.createdAt = datetime()
SET u.displayName = $displayName
RETURN u.userId AS userId;
~~~

Email/username có constraint riêng nhưng không đưa chúng vào **khóa MERGE** nếu nghiệp vụ cho phép thay đổi. Khi yêu cầu cập nhật email, cần kiểm tra quyền, xác minh uniqueness và xử lý xung đột với User khác.

Nếu không có userId mà email là khóa tìm, cần chính sách rõ ràng khi người dùng đổi email và khi username trùng. Không thể dùng một MERGE “mọi property” thay thế quá trình giải quyết danh tính.

### 7.2. Không nuốt lỗi constraint và cho rằng đã xử lý

Khi bị constraint violation:

1. Xem **constraint nào** bị vi phạm.
2. Xác định đó là duplicate của **cùng đối tượng nghiệp vụ** hay xung đột với đối tượng khác.
3. Đọc lại theo khóa chính ổn định nếu cần.
4. So payload và owner/tenant.
5. Chỉ coi là idempotent duplicate khi đúng hợp đồng.
6. Nếu dữ liệu khác hoặc quan hệ sở hữu khác, báo conflict và điều tra.

**Không** catch mọi lỗi uniqueness rồi trả HTTP 200; cách đó có thể che việc gán email của khách hàng khác hoặc vi phạm tenant isolation.

## 8. Null, chuỗi rỗng, kiểu dữ liệu và chuẩn hóa

Cypher phân biệt `null` với chuỗi rỗng và với giá trị thuộc kiểu khác. Một lỗi phổ biến là coi chúng tương đương.

### 8.1. MERGE không chấp nhận property có giá trị null trong key map

Ví dụ đầu vào thiếu `userId`:

~~~cypher
MERGE (u:User {userId: $userId})
RETURN u;
~~~

Nếu `$userId = null`, MERGE có thể báo lỗi vì không thể khớp/tạo node bằng property có giá trị null trong mẫu MERGE. Không nên giải quyết bằng cách âm thầm biến null thành chuỗi `'null'` vì nó tạo ra **business key giả**.

Trước khi ghi:

- Validate property bắt buộc.
- Từ chối null/blank/kiểu sai bằng lỗi input phù hợp.
- Phân biệt “không có property” và “property có giá trị khác”.
- Bảo đảm ID được tạo trước khi callback transaction có thể retry.

### 8.2. Các biểu diễn nhìn giống nhau có thể là các khóa khác nhau

~~~text
"C-100"
"c-100"
"C-100 "
100
"100"
~~~

Những biểu diễn này không nhất thiết khớp cùng một khóa theo so sánh dữ liệu trong Neo4j. Tùy kiểu và hợp đồng nghiệp vụ, chúng có thể tạo nhiều node.

Nếu business key là chuỗi, hãy chuẩn hóa **trước khi gọi MERGE**, ví dụ trim/normalization/case-folding theo quy tắc của domain. Việc chuẩn hóa phải nhất quán giữa Java API, batch import, CDC và mọi luồng ghi khác.

### 8.3. Tránh chuẩn hóa cứng trong mọi query không nhất quán

Ví dụ:

~~~cypher
MERGE (c:Customer {email: toLower(trim($email))})
RETURN c;
~~~

Mẫu có thể phù hợp nếu **emailNormalized** là khóa chính thức của ứng dụng, nhưng cần cân nhắc dữ liệu có sẵn và quy tắc chuẩn hóa.

Tốt hơn là xác định hai trường rõ mục đích:

~~~text
emailOriginal    = dữ liệu nhập được duyệt để hiển thị
emailLookupKey   = khóa tìm kiếm đã chuẩn hóa theo chính sách
~~~

Sau đó đặt uniqueness constraint trên khóa tra cứu nếu nghiệp vụ yêu cầu một tài khoản cho mỗi khóa. Tránh đổi quy tắc chuẩn hóa đột ngột mà chưa migration dữ liệu cũ.

## 9. MERGE toàn mẫu đường đi: dễ tạo node dư

Đây là một trong những lỗi khó nhận biết nhất khi dùng `MERGE` trên nhiều node và relationship cùng lúc.

Giả sử User A và B đã tồn tại nhưng chưa có cạnh `FOLLOWS`.

### 9.1. Phản ví dụ

~~~cypher
MERGE (a:User {userId: $fromId})
      -[:FOLLOWS]->
      (b:User {userId: $toId})
RETURN a, b;
~~~

Cypher thử tìm **toàn bộ pattern có cả hai node và cạnh**. Vì relationship chưa tồn tại, toàn pattern chưa khớp. Nếu chưa có uniqueness constraint phù hợp, MERGE có thể cố tạo **những phần chưa được bound của mẫu**, dẫn đến User trùng; nếu có constraint, nó có thể gặp lỗi khi cố tạo các node với userId đã tồn tại.

### 9.2. Cách viết đúng cho “hai User tồn tại thì tạo cạnh”

~~~cypher
MATCH (a:User {userId: $fromId})
MATCH (b:User {userId: $toId})
WHERE a <> b
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.followedAt = datetime()
RETURN a.userId AS sourceId,
       b.userId AS targetId;
~~~

Ở đây:

1. `MATCH` bind a và b vào những node đã có.
2. `WHERE a <> b` chặn self-follow nếu nghiệp vụ yêu cầu.
3. `MERGE` chỉ cần tìm/tạo relationship giữa hai node đã được bind.

Nếu a hoặc b không tồn tại, query trả **0 hàng**, không tạo User. Application service phải kiểm tra điều này và xử lý lỗi không tìm thấy; không coi “không có exception” là đã tạo cạnh.

### 9.3. Khi cần tạo cả hai User nếu thiếu

~~~cypher
MERGE (a:User {userId: $fromId})
WITH a
MERGE (b:User {userId: $toId})
WITH a, b
WHERE a <> b
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.followedAt = datetime()
RETURN a.userId AS sourceId,
       b.userId AS targetId;
~~~

Đây là **ba MERGE riêng**, nên các node được bind trước khi tạo relationship. Để an toàn trước ghi đồng thời, cần uniqueness constraint trên `User.userId`. Nếu fromId = toId, hai MERGE node có thể vẫn tạo một User rồi WHERE chặn edge; hãy validate từ input nếu muốn từ chối toàn bộ yêu cầu self-follow.

**Quan trọng:** ngay cả với node unique, trường hợp relationship trùng dưới concurrency phải được xem xét riêng theo phiên bản và chiến lược khóa/idempotency.

## 10. MERGE relationship: đừng đưa property thay đổi vào khóa khớp

Giả sử một User theo dõi người khác và trạng thái quan hệ có thể thay đổi từ `PENDING` sang `ACTIVE`.

### 10.1. Phản ví dụ: property trạng thái tham gia pattern

~~~cypher
MATCH (a:User {userId: $fromId})
MATCH (b:User {userId: $toId})
MERGE (a)-[r:FOLLOWS {status: $status}]->(b)
RETURN r;
~~~

Nếu đã có `FOLLOWS {status:'PENDING'}` và request mới đưa `status:'ACTIVE'`, pattern mới **không khớp relationship cũ**. MERGE có thể tạo **relationship thứ hai** giữa cùng hai User thay vì cập nhật trạng thái của cạnh cũ.

### 10.2. Cách phù hợp hơn khi mỗi cặp chỉ có một FOLLOWS

~~~cypher
MATCH (a:User {userId: $fromId})
MATCH (b:User {userId: $toId})
MERGE (a)-[r:FOLLOWS]->(b)
ON CREATE SET r.followedAt = datetime()
SET r.status = $status
RETURN r.status AS status;
~~~

Khi nghiệp vụ coi **(source User, relationship type, target User)** là một quan hệ duy nhất, chỉ pattern của cặp/hướng/type tham gia MERGE; status là thuộc tính có thể cập nhật.

**Không được coi câu này là bảo đảm tuyệt đối khi có nhiều writer cạnh tranh.** Neo4j không tự tạo uniqueness constraint cho “một FOLLOWS trên mỗi cặp” chỉ vì User có unique key. Khi cần bất biến mạnh dưới concurrency, phải thiết kế cơ chế bảo vệ đầu mút/khóa quan hệ/định danh cạnh phù hợp và thử nghiệm trên phiên bản thực.

### 10.3. MERGE không dọn relationship đã tồn tại trùng

Nếu trước đó có hai FOLLOWS giống cặp/hướng/type, MERGE có thể khớp cả hai. `ON MATCH SET` có thể chạy với nhiều hàng phù hợp, và đoạn query tiếp theo có thể bị nhân bản kết quả.

Trước khi tuyên bố MERGE “đã sửa duplicate”, phải đếm relationship thật theo source/target/type và kiểm tra tính nhất quán.

### 10.4. Relationship có khóa nghiệp vụ riêng

Một số relationship là **sự kiện có ID riêng**, ví dụ `TRANSFERRED` hoặc `IMPORTED_AS`, cho phép nhiều cạnh giữa hai node nhưng phân biệt bằng `eventId`. Khi đó, “một cạnh trên một cặp User” **không phải** bất biến đúng.

Cần mô hình khác:

~~~text
(source)-[:TRANSFERRED {eventId: E1, amount: 10}]->(target)
(source)-[:TRANSFERRED {eventId: E2, amount: 20}]->(target)
~~~

Nếu dùng identity theo event, cân nhắc uniqueness constraint trên relationship property hoặc node sự kiện riêng theo tính năng phiên bản/edition. Không ép tất cả relationship thành duy nhất trên cặp đầu mút.

## 11. Chẩn đoán relationship trùng theo đầu mút và hướng

Giả sử `User.userId` đã là khóa duy nhất. Tìm cặp có nhiều FOLLOWS:

~~~cypher
MATCH (a:User)-[r:FOLLOWS]->(b:User)
WHERE a.userId IS NOT NULL
  AND b.userId IS NOT NULL
WITH a.userId AS fromId,
     b.userId AS toId,
     count(r) AS relationshipCount
WHERE relationshipCount > 1
RETURN fromId, toId, relationshipCount
ORDER BY relationshipCount DESC
LIMIT 50;
~~~

Lưu ý:

- Nếu User đã trùng ID, gom theo ID có thể gộp **những cặp node vật lý khác nhau**. Trước khi quyết định xóa relationship dư, xác định node nào là đầu mút thật.
- Hướng quan hệ quan trọng: `(a)-[:FOLLOWS]->(b)` và `(b)-[:FOLLOWS]->(a)` là hai ý nghĩa khác nhau, không mặc định trùng.
- Hai relationship cùng cặp/type có thể hợp lệ nếu domain cho phép bản ghi nhiều lần; không xóa chỉ dựa trên một thống kê.

### 11.1. Xem relationship cụ thể trong một cặp

~~~cypher
MATCH (a:User {userId: $fromId})
      -[r:FOLLOWS]->
      (b:User {userId: $toId})
RETURN elementId(r) AS diagnosticElementId,
       properties(r) AS relationshipProperties
ORDER BY diagnosticElementId;
~~~

`elementId(r)` hữu ích trong một lần chẩn đoán để phân biệt relationship. **Không dùng elementId như business key ổn định lâu dài** hoặc giả định ID được giữ nguyên qua mọi export/import/restore.

### 11.2. Dùng count(*) và count(DISTINCT r) cho đúng câu hỏi

Khi relationship `r` bị nhân hàng vì có thêm MATCH khác, `count(r)` có thể đếm lặp cùng relationship. Muốn đếm relationship thực thể:

~~~cypher
MATCH (a:User)-[r:FOLLOWS]->(b:User)
OPTIONAL MATCH (a)-[:AUTHORED]->(p:Post)
WITH a, b,
     count(DISTINCT r) AS distinctFollowEdges,
     count(DISTINCT p) AS distinctPosts
RETURN a.userId AS fromId,
       b.userId AS toId,
       distinctFollowEdges,
       distinctPosts
ORDER BY distinctFollowEdges DESC
LIMIT 50;
~~~

Nếu đang cần kiểm tra fan-out, hiểu rằng `OPTIONAL MATCH` cũng có thể nhân hàng; dùng DISTINCT với **biến relationship**, không chỉ DISTINCT trên giá trị status của nó.

## 12. Ghi đồng thời: MERGE không thay thế ràng buộc dữ liệu

Xem hai worker gần như đồng thời:

~~~text
Worker A                    Database                    Worker B
    |                           |                            |
    | -- tìm Customer K -------->|<--------- tìm Customer K --|
    |         chưa thấy          |          chưa thấy         |
    | -- cố tạo Customer K ----->|<------ cố tạo Customer K --|
    |                           |                            |
    +---------------------------+----------------------------+
~~~

Khi **không có constraint**, cả hai có thể tạo node cùng key. Khi có **unique constraint phù hợp**, database phải bảo vệ bất biến không cho hai node cùng key commit; một transaction có thể thành công, transaction khác có thể chờ, khớp dữ liệu hiện có hoặc nhận lỗi tùy lịch thực thi/phiên bản.

### 12.1. Mẫu an toàn hơn cho node

~~~cypher
CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User)
REQUIRE u.userId IS UNIQUE;
~~~

~~~cypher
MERGE (u:User {userId: $userId})
ON CREATE SET u.createdAt = datetime()
SET u.displayName = $displayName
RETURN u.userId AS userId;
~~~

Ở đây business key **cố định** và có constraint. Nếu xảy ra transient contention hoặc duplicate theo request, ứng dụng phân loại rồi xử lý theo chính sách; **không** mặc định tất cả worker đều phải thành công trong lần thử đầu.

### 12.2. “Tìm rồi CREATE” trong hai transaction là race

Phản ví dụ:

~~~text
Transaction 1: MATCH User K -> 0 hàng
Application:   quyết định cần tạo
Transaction 2: CREATE User K
~~~

Một worker khác có thể tạo K ở giữa hai bước. Nếu cần nguyên tử “tìm hoặc tạo”, đặt thao tác trong transaction với MERGE/constraint phù hợp. Nếu bất biến đòi hỏi nhiều bước, gom đúng ranh giới giao dịch nghiệp vụ.

### 12.3. Ranh giới transaction và khóa khi cập nhật quan hệ

Trường hợp tạo relationship giữa hai node có thể gây tranh chấp trên những node/cấu trúc liên quan. Để bảo đảm quy tắc cấm trùng cạnh, có thể cần:

- Một định danh relationship ổn định với constraint nếu mô hình/phiên bản hỗ trợ.
- Node trung gian biểu diễn sự kiện/quan hệ với unique business key.
- Quy trình ghi được serialize theo khóa nghiệp vụ trong ứng dụng hoặc cơ chế khóa được kiểm chứng.
- Kiểm thử hai hoặc nhiều transaction đồng thời.
- Xử lý deadlock/transient errors với retry có giới hạn.

Không dùng một cuộc thử tuần tự `MERGE` hai lần làm bằng chứng không có race khi production chạy nhiều worker.

## 13. UNWIND, LOAD CSV và nhập hàng loạt: duplicate từ nguồn

Trong pipeline import, duplicate có thể xuất hiện ngay **trong cùng batch** hoặc giữa nhiều batch, không chỉ do concurrency.

Ví dụ input:

~~~json
[
  {"customerId": "C-1", "name": "An"},
  {"customerId": "C-1", "name": "An"},
  {"customerId": "C-2", "name": "Binh"}
]
~~~

Khi dùng:

~~~cypher
UNWIND $rows AS row
MERGE (c:Customer {customerId: row.customerId})
SET c.name = row.name
RETURN count(c) AS processedRows;
~~~

`processedRows` có thể là 3 do có **ba dòng input được xử lý**, không có nghĩa đã tạo ba node. Nếu có unique constraint và MERGE đúng khóa, có thể chỉ tồn tại hai Customer phân biệt.

### 13.1. Dedupe theo khóa trước khi MERGE

~~~cypher
UNWIND $rows AS row
WITH row.customerId AS customerId
WHERE customerId IS NOT NULL AND trim(customerId) <> ''
WITH DISTINCT customerId
MERGE (c:Customer {customerId: customerId})
ON CREATE SET c.createdAt = datetime()
RETURN count(c) AS distinctKeysProcessed;
~~~

Điều kiện ví dụ giả định `row.customerId` là chuỗi. Nếu input có kiểu sai, validate/chuẩn hóa trước khi gửi tới Neo4j.

Quan trọng:

- `WITH DISTINCT` loại các **dòng có cùng khóa** trong batch hiện tại; không thay uniqueness constraint cho nhiều worker.
- Nếu cùng customerId có hai tên khác nhau, việc loại trùng theo ID **không quyết định tên nào đúng**. Cần chính sách chọn bản thắng/merge dữ liệu đầu vào trước.
- `count(c)` sau MERGE vẫn đếm các khóa đã xử lý, không phải số node mới tạo.

### 13.2. Không để thứ tự input quyết định kết quả âm thầm

~~~cypher
UNWIND $rows AS row
MERGE (c:Customer {customerId: row.customerId})
SET c.status = row.status;
~~~

Nếu cùng khóa có hai status khác nhau, giá trị cuối cùng phụ thuộc thứ tự ghi/thực thi. Đừng dựa vào thứ tự danh sách JSON như một cơ chế version nghiệp vụ bảo đảm trong mọi cách viết.

Chọn một chính sách có thể kiểm chứng: timestamp/version do nguồn cấp, trạng thái được phép chuyển, hoặc từ chối batch khi payload cùng khóa mâu thuẫn.

### 13.3. LOAD CSV không tự chống trùng

`LOAD CSV` đọc dòng từ nguồn; nó không đồng nghĩa dedupe. Một file có nhiều dòng cùng ID sẽ cần cùng quy tắc MERGE, constraint, normalized key và xử lý lỗi như `UNWIND`.

Trong các import có parallelism hoặc transaction batching, cần kiểm tra:

- Có cùng một khóa xuất hiện ở nhiều batch không?
- Đã tạo constraint trước khi nhập chưa?
- Mỗi transaction nhập bao nhiêu dòng?
- Nếu batch thất bại, replay có giữ business key và idempotency không?
- Có bỏ sót dòng do MATCH không tìm thấy đầu mút?
- Đếm created/matched/failed/ignored có tách bạch không?

## 14. MERGE báo lỗi vì MATCH/WHERE trước đó không còn hàng

Một trường hợp ngược với duplicate là **MERGE không chạy**:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (p:Product {sku: $sku})
MERGE (c)-[:BOUGHT]->(p)
RETURN c, p;
~~~

Nếu Customer hoặc Product không tồn tại, `MATCH` trả 0 hàng, nên MERGE **không được thực hiện**. Truy vấn có thể không ném exception và vẫn không tạo relationship nào.

### 14.1. Phân biệt chính sách “phải tồn tại” và “được tạo nếu thiếu”

Nếu hai node **bắt buộc đã tồn tại**, dùng MATCH và kiểm tra số hàng trả về. Nếu chính sách cho phép tạo mới, dùng MERGE cho từng node theo khóa ổn định có constraint rồi MERGE cạnh.

Không thay mọi MATCH bằng MERGE khi gặp 0 hàng: có thể tạo dữ liệu không hợp lệ, ví dụ Product không tồn tại trong danh mục nhưng được sinh ra chỉ vì đơn hàng tham chiếu đến nó.

### 14.2. OPTIONAL MATCH và WHERE đặt sai vị trí

~~~cypher
MATCH (u:User {userId: $userId})
OPTIONAL MATCH (u)-[r:HAS_PHONE]->(p:Phone)
WHERE p.verified = true
RETURN u.userId, p.number;
~~~

`WHERE` trong ví dụ được gắn với `OPTIONAL MATCH` để giới hạn mẫu tùy chọn. Nếu viết lại thành:

~~~cypher
MATCH (u:User {userId: $userId})
OPTIONAL MATCH (u)-[r:HAS_PHONE]->(p:Phone)
WITH u, p
WHERE p.verified = true
RETURN u.userId, p.number;
~~~

thì dòng có `p = null` bị loại ở giai đoạn `WITH/WHERE`, khiến query không trả User dù ban đầu MATCH User thành công. Khi MERGE ở phía sau, nó cũng không chạy.

**Bài học:** trước khi quy kết MERGE lỗi, đo cardinality ở từng bước `MATCH`, `OPTIONAL MATCH`, `WITH` và `WHERE`.

## 15. Đọc lỗi constraint và phân loại đúng

Khi database ném lỗi, ứng dụng nên lưu **mã loại lỗi được cho phép và tên operation**, tránh log parameter chứa email/token. Tên code/messages có thể thay đổi theo phiên bản Neo4j/Java Driver và loại constraint.

Một số nhóm cần phân biệt:

| Nhóm | Ví dụ | Hành động |
|---|---|---|
| **Constraint violation** | Cố tạo User có email đã được node khác dùng | Kiểm tra identity/payload, trả conflict hoặc xử lý duplicate đúng nghĩa |
| **MERGE null property** | User ID thiếu | Trả lỗi input, không retry |
| **Syntax/type error** | Tham số sai kiểu, lệnh Cypher lỗi | Sửa request/query, không retry vô hạn |
| **Transient transaction failure** | Deadlock, lock conflict được driver nhận diện | Retry transaction có giới hạn |
| **No matching row** | MATCH không thấy Customer | Xử lý not found, không mặc định thành công |
| **Ambiguous commit** | Client mất response trong khi commit có thể thành công | Đọc lại theo khóa ổn định trước replay |
| **Permission/schema change** | Không được tạo constraint hoặc label | Kiểm tra quyền/migration, không sửa dữ liệu tùy tiện |

### 15.1. Đừng retry lỗi bền vững

Nếu unique constraint trên `User.email` đã bị vi phạm vì email thuộc User khác, gửi lại **cùng request mười lần** không làm tình trạng tự biến mất. Retry chỉ phù hợp khi lỗi được xác định là tạm thời hoặc khi có cơ chế giải quyết tranh chấp/idempotency rõ ràng.

### 15.2. Constraint exception có thể là kết quả bảo vệ dữ liệu

Lỗi đôi khi là **bằng chứng constraint đang làm việc đúng**: database từ chối transaction có khả năng tạo một key trùng. Không nên “sửa” bằng cách xóa constraint để import chạy hết nếu ràng buộc đó phản ánh bất biến nghiệp vụ.

Hành động đúng thường là điều tra dữ liệu nguồn, khóa MERGE hoặc duplicate đã tồn tại trước migration.

## 16. Java Driver: MERGE ổn định và xử lý kết quả đúng

Ứng dụng Java nên dùng **parameter** thay vì ghép string vào Cypher, và giữ business key cố định trước khi gọi managed transaction.

Ví dụ service upsert Customer theo khóa composite:

~~~java
import java.util.Map;

import org.neo4j.driver.Driver;
import org.neo4j.driver.Result;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public final class CustomerUpsertService {
    public record CustomerKey(
        String tenantId,
        String customerId
    ) {}

    private final Driver driver;

    public CustomerUpsertService(Driver driver) {
        this.driver = driver;
    }

    public CustomerKey upsert(
            String tenantId,
            String customerId,
            String displayName) {

        if (tenantId == null || tenantId.isBlank()
                || customerId == null || customerId.isBlank()
                || displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("Invalid customer input");
        }

        String cypher = """
            MERGE (c:Customer {
                tenantId: $tenantId,
                customerId: $customerId
            })
            ON CREATE SET c.createdAt = datetime()
            SET c.displayName = $displayName
            RETURN c.tenantId AS tenantId,
                   c.customerId AS customerId
            """;

        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {

            return session.executeWrite(tx -> {
                Result result = tx.run(cypher, Map.of(
                    "tenantId", tenantId,
                    "customerId", customerId,
                    "displayName", displayName
                ));
                var row = result.single();

                return new CustomerKey(
                    row.get("tenantId").asString(),
                    row.get("customerId").asString()
                );
            });
        }
    }
}
~~~

Ví dụ giả định constraint `(tenantId, customerId)` đã được triển khai trước, mọi luồng ghi dùng cùng chính sách và hai ID đầu vào đã được chuẩn hóa theo hợp đồng.

### 16.1. Điều ví dụ bảo vệ và chưa bảo vệ

**Có:**

- Không ghép input vào query text.
- Sử dụng key ổn định trong MERGE.
- Upsert node và SET trong một managed transaction.
- Ánh xạ kết quả thành DTO bên trong callback.
- Driver có cơ chế retry các lỗi transient phù hợp.

**Chưa tự giải quyết:**

- Thứ tự cập nhật tên khi hai event gửi đến không đúng thứ tự.
- Conflict khi một constraint khác trên email/username bị vi phạm.
- Duplicate đã tồn tại trước khi tạo constraint.
- Tác dụng phụ email/broker ở các hệ thống ngoài.
- Tính đúng của input normalization ở nhiều service.

### 16.2. Managed transaction callback có thể chạy lại

Trong Java Driver, `session.executeWrite(...)` có thể thực hiện lại callback khi lỗi phù hợp. Vì vậy **không** tạo UUID mới cho business key ngay trong callback, không gửi email hay gọi thanh toán trong callback.

Nếu dùng explicit transaction qua `session.beginTransaction()`, chính sách retry toàn bộ transaction khác với managed transaction; cần ứng dụng chủ động xử lý dựa trên lỗi và tính lũy đẳng.

### 16.3. Không ghi toàn bộ exception/parameters vào log

Khi debug constraint trong production, map input có thể chứa email hoặc dữ liệu nhạy cảm. Ưu tiên log:

~~~text
operation=customer.upsert
errorCategory=CONSTRAINT_CONFLICT
tenantAlias=approved-safe-code
durationMs=18
~~~

Không log raw Cypher parameter map, token hoặc toàn bộ `Node`/`Record`. Với dữ liệu nhạy cảm, dùng correlation ID và hệ thống truy dấu được phân quyền, thay vì in business key lên dashboard chung.

## 17. Spring Data Neo4j: repository save không thay thế uniqueness

Với Spring Data Neo4j, entity thường có annotation `@Node`, `@Id`, `@GeneratedValue`, `@Relationship` và repository. Nhưng việc `save(...)` hoạt động không có nghĩa database tự biết đâu là khóa nghiệp vụ duy nhất.

Một entity có ID kỹ thuật được cấp mới ở mỗi lần nhập có thể tạo hai node cho cùng `externalCustomerId` nếu ứng dụng không có constraint hoặc chiến lược tìm/upsert ổn định.

### 17.1. Chọn ID và business key có chủ đích

- **ID kỹ thuật** có thể phù hợp cho quản lý vòng đời entity trong một service.
- **Business key** là thứ nhận diện cùng thực thể qua import, CDC, API retry và tích hợp.
- Nếu business key phải unique, áp dụng constraint ở Neo4j.
- Nếu một entity có nhiều label hoặc nhiều tenant, xác định scope của constraint.
- Khi dùng DTO/repository cho nested relationships, kiểm tra hành vi mapping để không tạo các node liên quan mới ngoài dự định.

Không coi `@Id` của Java entity là tuyên bố DDL “CREATE CONSTRAINT” đã chắc chắn được chạy thành công trong database. Cần migration/schema verification riêng.

### 17.2. Transaction boundary ở application service

Một use case tạo Order, OrderLine và các relationship cần nguyên tử nên gom các bước trong transaction được Spring quản lý đúng cấu hình:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerImportWorkflow {
    private final CustomerRepository repository;

    public CustomerImportWorkflow(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void handle(CustomerImportCommand command) {
        repository.upsertByBusinessKey(command);
        repository.attachRelationships(command);
    }
}
~~~

Đây là **ví dụ kiến trúc**, giả định interface `CustomerRepository` và `CustomerImportCommand` đã được định nghĩa. Nó không tự thực thi nếu chưa cài repository, transaction manager và schema.

Nếu MERGE trong repository đã thay key theo status, `@Transactional` không biến mẫu sai thành đúng. Nếu có constraint violation, cần phân loại lỗi ở service, không nuốt exception rồi để transaction commit một phần ngoài ý định.

### 17.3. Repository tự tạo quan hệ trùng

Nếu mỗi lần `save` xây một collection relationship object mới mà không nhận diện đúng quan hệ hiện có, ứng dụng có thể tạo/mapping dữ liệu không như kỳ vọng. Kiểm tra query mà framework phát ra, phiên bản Spring Data Neo4j và định danh relationship entity khi mô hình dùng relationship có property/ID.

**Không mặc định** mọi repository đều ghi giống một câu `MERGE (a)-[:REL]->(b)` tự viết. Hành vi phụ thuộc mapping và cách lưu graph.

## 18. MERGE và lệnh cộng dồn: cần idempotency riêng

Một trường hợp duplicate **tác dụng nghiệp vụ** có thể xảy ra dù database không có node trùng:

~~~cypher
MERGE (a:Account {accountId: $accountId})
SET a.points = coalesce(a.points, 0) + 100;
~~~

Nếu cùng command được commit hai lần, điểm tăng **200**, mặc dù vẫn chỉ một Account. MERGE nhận diện **node**, không nhận diện **lệnh cộng điểm**.

### 18.1. Dùng receipt/ledger theo commandId

~~~cypher
CREATE CONSTRAINT applied_command_unique IF NOT EXISTS
FOR (cmd:AppliedCommand)
REQUIRE cmd.commandId IS UNIQUE;
~~~

Một mô hình ghi command mới:

~~~cypher
MATCH (a:Account {accountId: $accountId})
CREATE (cmd:AppliedCommand {
    commandId: $commandId,
    accountId: $accountId,
    delta: $delta,
    appliedAt: datetime()
})
SET a.points = coalesce(a.points, 0) + $delta
SET cmd.resultPoints = a.points
CREATE (cmd)-[:APPLIED_TO]->(a)
RETURN cmd.commandId AS commandId,
       cmd.resultPoints AS resultPoints;
~~~

Receipt và thay đổi Account thuộc **cùng transaction**. Nếu commandId đã tồn tại và unique constraint từ chối CREATE, transaction đó không được commit phép cộng.

Sau lỗi/timeout không rõ kết quả, ứng dụng tìm receipt theo commandId, so accountId/delta/payload rồi mới quyết định trả kết quả cũ hay retry. Không tự tạo commandId mới cho cùng thao tác.

### 18.2. Không dùng MERGE receipt rồi SET delta vô điều kiện

Phản ví dụ:

~~~cypher
MERGE (cmd:AppliedCommand {commandId: $commandId})
WITH cmd
MATCH (a:Account {accountId: $accountId})
SET a.points = coalesce(a.points, 0) + $delta;
~~~

Dù receipt đã có, câu SET vẫn cộng thêm. Cần một ranh giới transaction chỉ cho **lệnh mới** tạo tác dụng nghiệp vụ, không dựa vào suy luận “có MERGE thì toàn query tự lũy đẳng”.

## 19. Kiểm tra EXPLAIN/PROFILE khi MERGE chậm

Một MERGE đúng ngữ nghĩa vẫn có thể chậm khi thiếu index, scan nhiều node hoặc đầu vào tạo nhiều hàng.

### 19.1. EXPLAIN để xem kế hoạch mà không chạy ghi

~~~cypher
EXPLAIN
MERGE (c:Customer {customerId: $customerId})
RETURN c.customerId;
~~~

Xem planner có sử dụng index/constraint để tìm key không; chú ý cardinality ước lượng và số hàng đầu vào. Khi constraint và index phù hợp, Neo4j thường có khả năng tìm theo key hiệu quả hơn việc scan toàn bộ label.

### 19.2. PROFILE thực thi lệnh thật

~~~cypher
PROFILE
MATCH (c:Customer {customerId: $customerId})
RETURN c.customerId;
~~~

Ở đây PROFILE chỉ đọc. Nhưng nếu PROFILE áp dụng cho `MERGE`, `CREATE`, `SET`, `DELETE`, **nó sẽ thực hiện tác dụng ghi**. Không chạy PROFILE trên truy vấn ghi ở production chỉ để xem query plan.

### 19.3. Điều tra cardinality thay vì chỉ tăng index

Nếu query nhập qua `UNWIND` nhận 50.000 dòng, một MERGE vẫn được gọi theo số dòng. Nếu bước MATCH trước nó nhân hàng, có thể thực thi nhiều phép ghi hơn dự kiến.

Đo từng giai đoạn bằng truy vấn đọc an toàn trên input thử:

~~~cypher
UNWIND $rows AS row
RETURN count(*) AS inputRows,
       count(DISTINCT row.customerId) AS distinctCustomerIds;
~~~

Phép đếm distinct chỉ là chẩn đoán; nếu nhiều dòng cùng ID có payload khác, cần phân loại xung đột nguồn, không tự bỏ qua.

## 20. Quy trình làm sạch duplicate an toàn

Khi phát hiện dữ liệu trùng đã tồn tại, **không lập tức chạy DETACH DELETE**. Một node dư có thể có những relationship hoặc property quan trọng mà node chuẩn chưa có.

### 20.1. Bước 1 — Khoanh vùng và dừng nguồn phát sinh

- Xác định label, key, tenant/source và khoảng thời gian phát sinh.
- Tìm API/batch/CDC nào ghi MERGE không có constraint hoặc dùng key sai.
- Dừng/giới hạn đường ghi gây trùng theo quy trình vận hành.
- Lấy backup/restore point phù hợp; cân nhắc làm việc trên bản sao thử.
- Giới hạn quyền truy cập dữ liệu nhạy cảm trong log điều tra.

Không vừa dọn duplicate vừa để writer không được sửa tiếp tục tạo trùng.

### 20.2. Bước 2 — Chọn canonical node theo quy tắc nghiệp vụ

Với nhóm Customer trùng ID, cần quyết định node chuẩn dựa trên:

- ID nguồn tin cậy và thời điểm tạo.
- Khả năng truy vết đơn hàng/giao dịch.
- Tính đầy đủ của property và quan hệ.
- Những bản ghi đã được hệ thống khác tham chiếu.
- Quy định giữ lịch sử/audit.

Không chọn “node đầu tiên” tùy ý rồi xóa phần còn lại. Một node có thể chứa đơn hàng duy nhất hoặc relationship được coi là chứng cứ nghiệp vụ.

### 20.3. Bước 3 — Kiểm kê relationship và property trước khi merge

Truy vấn minh họa trên một khóa:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
OPTIONAL MATCH (c)-[r]-()
RETURN elementId(c) AS diagnosticNodeId,
       labels(c) AS labels,
       properties(c) AS nodeProperties,
       count(r) AS attachedRelationships;
~~~

**Chỉ chạy trong môi trường/phạm vi được phép** vì `properties(c)` có thể chứa PII và toàn bộ property. Kết quả phải được xử lý trong kênh bảo mật; khi xuất báo cáo nên dùng những trường đã được duyệt.

Nếu cần biết chi tiết source/target/relationship type, tiếp tục kiểm kê bằng những truy vấn chỉ đọc phù hợp, không xóa trước khi biết mọi cạnh cần chuyển tới đâu.

### 20.4. Bước 4 — Thiết kế phép chuyển quan hệ có bảo toàn ngữ nghĩa

Việc “gộp hai node” trong property graph thường gồm:

1. Chọn canonical node.
2. Giải quyết xung đột property.
3. Xác định relationship nào cần chuyển về canonical node.
4. Với mỗi relationship, kiểm tra type, hướng, thuộc tính, bội số cho phép.
5. Đảm bảo không tạo self-loop hoặc duplicate trái nghiệp vụ khi chuyển.
6. Giữ lịch sử nếu cần audit.
7. Chỉ xóa node dư sau khi kiểm tra dữ liệu đã được bảo toàn.

Nếu dùng procedure mở rộng (ví dụ thư viện graph utility), phải kiểm tra **phiên bản, tính năng, chính sách merge và quyền** trên môi trường thử. Không mặc định một procedure “merge nodes” có thể quyết định đúng mọi xung đột domain.

### 20.5. Bước 5 — Thử trên bản sao và kiểm chứng bất biến

Với graph quan hệ phức tạp, tạo test mô phỏng:

~~~text
Customer C1 (canonical) --[:PLACED]--> Order O1
Customer C1 (duplicate) --[:PLACED]--> Order O2
Customer C1 (duplicate) --[:HAS_CASE]-> Case K
~~~

Sau gộp, cần xác nhận canonical C1 giữ những liên kết nghiệp vụ cần thiết đến O1/O2/K, và không tạo một relationship sai chiều hoặc mất thuộc tính lịch sử.

Kiểm tra:

- Số entity theo business key.
- Số relationship theo type/hướng.
- Các bất biến như mỗi Order thuộc Customer hợp lệ.
- Mức khớp với bảng đối soát/nguồn dữ liệu.
- Query đọc ứng dụng quan trọng.
- Ảnh hưởng của constraint được tạo sau cleanup.

### 20.6. Bước 6 — Tạo constraint và triển khai ghi đúng

Sau khi dữ liệu đã được xử lý và không còn xung đột:

~~~cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;
~~~

Dùng constraint đúng theo scope; nếu khóa cần là (tenantId, customerId), tạo composite constraint tương ứng thay vì chỉ trên customerId.

**IF NOT EXISTS không phải lệnh bảo đảm schema hiện có chính xác với mong muốn.** Kiểm tra `SHOW CONSTRAINTS` sau migration và xác nhận tên, label, properties, type phù hợp; việc “lệnh không lỗi” chưa đủ nếu schema khác ý định.

## 21. Runbook xử lý MERGE/constraint ở production

Có thể vận hành theo trình tự:

### 21.1. Nhận diện

1. Lấy tên operation và nhóm lỗi an toàn (không log PII).
2. Xác định database, phiên bản, thời điểm và phạm vi endpoint.
3. Phân biệt lỗi chỉ một request hay hàng loạt import/API.
4. Xác định có ghi lặp thật hay chỉ kết quả query bị nhân hàng.
5. Xem constraint/index hiệu lực, không suy ra từ migration source code.

### 21.2. Khoanh vùng

1. Reproduce với input synthetic có cùng hình dạng.
2. Chạy truy vấn đọc đếm duplicate theo business key.
3. Kiểm tra key normalization và null.
4. Chạy EXPLAIN để xem plan, cardinality.
5. Xem có nhiều worker/batch/CDC cùng ghi không.
6. Với relationship, xác định hướng/type/property nào đang nằm trong MERGE.
7. Nếu query có nhiều MATCH, đo số hàng sau từng bước.

### 21.3. Khắc phục

1. Sửa khóa MERGE cho phù hợp domain.
2. Thiết lập constraint đúng sau khi xử lý dữ liệu trùng.
3. Xử lý concurrency/retry/idempotency.
4. Dọn dữ liệu cũ qua change plan, backup và test.
5. Thử cả case chạy lại request, hai worker đồng thời và cùng key khác payload.
6. Quan sát lỗi constraint, số duplicate và bất biến sau deploy.

### 21.4. Không được làm khi chưa có phương án

- Xóa constraint để “hết lỗi”.
- `DETACH DELETE` node được xem là dư mà chưa kiểm kê relationship.
- Chạy import lại với business ID mới để tránh collision.
- Bắt mọi exception rồi trả success.
- Mở retry vô hạn cho lỗi schema/validation.
- Chuyển ứng dụng sang database khác và bỏ qua bản ghi không khớp.
- Dùng PROFILE với lệnh ghi trên dữ liệu thật chỉ để debug.

## 22. Kiểm thử regression và concurrency

Một bộ test hiệu quả phải xác minh **dữ liệu cuối cùng** chứ không chỉ code trả về HTTP 200.

| Kịch bản | Kết quả mong đợi |
|---|---|
| MERGE node mới với ID hợp lệ | Có đúng một node theo business key |
| MERGE cùng ID lần thứ hai | Không phát sinh node thứ hai |
| Hai thread cùng MERGE một ID | Constraint không cho hai node cùng key commit |
| Khóa null/blank | Từ chối input hoặc xử lý theo chính sách; không sinh key giả |
| Cùng ID nhưng status đổi | Cập nhật node đã có, không tạo node mới |
| Cùng ID ở hai tenant | Đúng theo composite key (được phép hoặc bị từ chối theo thiết kế) |
| MERGE User–FOLLOWS–User khi hai User đã có | Không tạo thêm User |
| MERGE relationship với status thay đổi | Không tạo cạnh mới chỉ vì status đổi nếu domain chỉ cho một cạnh |
| Input `UNWIND` có 10 dòng trùng key | Dedupe/matched count đúng; không tạo 10 node |
| Một lệnh cộng điểm được retry | Chỉ áp dụng tác dụng nghiệp vụ một lần theo commandId |
| Query nhiều OrderLine | Không kết luận Order trùng chỉ vì nhiều kết quả |
| Tạo constraint trên dữ liệu đã trùng | Migration fail có kiểm soát, không tự xóa dữ liệu |
| Cleanup duplicate có relationship | Giữ đầy đủ liên kết/bất biến sau chuyển |
| Hai worker cập nhật cùng entity | Kiểm tra contention, lost update và version nếu cần |

### 22.1. Test hai thread không dùng chung Session tùy tiện

Trong Java Driver, Driver thường được tái sử dụng, còn Session có vòng đời ngắn và không nên chia sẻ bừa bãi giữa nhiều thread. Với mỗi worker test, dùng Session/transaction riêng.

Chạy đồng thời cùng một `customerId` nhiều lần, sau đó kiểm tra:

~~~cypher
MATCH (c:Customer {customerId: $customerId})
RETURN count(c) AS nodeCount;
~~~

Kỳ vọng `nodeCount = 1` khi hợp đồng định danh và constraint đã cấu hình đúng. Cũng cần kiểm tra tất cả payload/relationship hợp lệ; số node bằng 1 không chứng minh những thuộc tính khác không bị ghi sai.

### 22.2. Test đường đi có nhiều relationship

Với User A theo dõi User B, chạy thao tác tạo FOLLOWS nhiều lần, cả tuần tự và song song. Sau đó:

~~~cypher
MATCH (a:User {userId: $fromId})
      -[r:FOLLOWS]->
      (b:User {userId: $toId})
RETURN count(r) AS relationshipCount;
~~~

Kỳ vọng count = 1 **nếu** domain quy định một cạnh FOLLOWS mỗi cặp và giải pháp concurrency đã được thiết kế tương ứng.

### 22.3. Đảm bảo không xóa nhầm trong cleanup test

Mọi bài kiểm thử có `DETACH DELETE`, sửa relationship hay merge node cần chạy trên database test riêng, với ID/nội dung giả. Không dùng dữ liệu khách hàng production trong bài thử dọn duplicate.

## 23. Những ngộ nhận cần tránh

**“MERGE tương đương unique constraint.”** Không. MERGE là thao tác tìm/tạo theo pattern; constraint là bất biến enforced khi ghi.

**“Hai node giống property sẽ tự hợp nhất khi MERGE.”** Không. MERGE không chuyển relationship hoặc xóa node dư.

**“Đưa mọi property vào MERGE để chắc khớp.”** Sai với property thay đổi như status, name, price, lastSeenAt.

**“MERGE đường đi sẽ chỉ tạo relationship còn thiếu.”** Không thể dựa vào điều đó khi các node chưa được bind trong mẫu đầy đủ.

**“Hai hàng có cùng customerId nghĩa là có hai node.”** Có thể chỉ do JOIN graph qua nhiều relationship.

**“DISTINCT đã sửa dữ liệu trùng.”** Không. Nó chỉ ảnh hưởng tập hàng kết quả.

**“Nếu có index là không thể tạo trùng.”** Không; index thường không mang ràng buộc uniqueness.

**“Constraint tạo lỗi nên cứ xóa constraint.”** Không; lỗi thường phản ánh bất biến đang được bảo vệ hoặc input sai.

**“MERGE relationship có status trong map sẽ cập nhật status cũ.”** Không; thay đổi status làm pattern khác, có thể tạo cạnh mới.

**“MERGE Account rồi tăng counter là idempotent.”** Không; mỗi lần commit có thể tăng tiếp.

**“@Transactional hoặc executeWrite luôn sửa duplicate.”** Không; transaction atomicity/retry không thay thế business key và constraint.

**“Xóa node dư là an toàn nếu cùng email.”** Không; có thể mất relationship, audit và dữ liệu hợp lệ.

## 24. Bài tập vận dụng

### Bài 1 — Trùng do status

Database có:

~~~text
(:User {userId: "U1", status: "ACTIVE"})
~~~

Ứng dụng chạy:

~~~cypher
MERGE (:User {userId: 'U1', status: 'BLOCKED'});
~~~

**Câu hỏi:** Nếu không có uniqueness constraint, điều gì có thể xảy ra?

**Đáp án:** Một User mới có cùng userId nhưng status BLOCKED có thể được tạo vì toàn bộ pattern không khớp User ACTIVE. Nên MERGE theo userId rồi SET status, có uniqueness constraint trên key.

### Bài 2 — Constraint nhưng MERGE vẫn lỗi

`User.userId` có uniqueness constraint. User U1 đã tồn tại với status ACTIVE; MERGE với U1 và status BLOCKED báo lỗi.

**Câu hỏi:** Constraint có hoạt động sai không?

**Đáp án:** Không. Constraint từ chối tạo User thứ hai cùng userId. Mẫu MERGE đang sử dụng thuộc tính mutable làm khóa khớp.

### Bài 3 — Hai node được trả trong một truy vấn

Một Order có hai OrderLine và query RETURN Order sau khi MATCH HAS_LINE trả hai hàng.

**Câu hỏi:** Làm thế nào phân biệt node trùng và cardinality?

**Đáp án:** Đếm `count(DISTINCT o)`, kiểm tra `count(o)`/số hàng; tìm business key trùng trong `MATCH (o:Order)` độc lập.

### Bài 4 — MERGE toàn mẫu

Hai User A/B có sẵn, chưa có FOLLOWS. Một MERGE duy nhất trên pattern cả hai node và relationship gây lỗi unique.

**Câu hỏi:** Sửa query thế nào?

**Đáp án:** MATCH hoặc MERGE từng User theo khóa có constraint trước, rồi MERGE relationship giữa hai biến đã được bind.

### Bài 5 — Quan hệ đổi status

Đã có FOLLOWS status PENDING, sau đó chạy MERGE với status ACTIVE.

**Câu hỏi:** Vì sao có thể xuất hiện hai relationship?

**Đáp án:** Status tham gia mẫu MERGE, nên relationship cũ không khớp. MERGE theo đầu mút/type rồi SET status, cùng giải pháp concurrency nếu chỉ được phép một cạnh.

### Bài 6 — Multi-tenant

Customer ID C1 xuất hiện trong tenant T1 và T2.

**Câu hỏi:** Nên tạo unique constraint trên một trường hay hai trường?

**Đáp án:** Nếu business key chỉ duy nhất trong mỗi tenant, dùng composite uniqueness `(tenantId, customerId)`. Unique trên `customerId` toàn hệ thống sẽ từ chối một trường hợp hợp lệ.

### Bài 7 — Null trong MERGE

Batch import chứa một dòng không có externalId.

**Câu hỏi:** Có nên dùng `coalesce(row.externalId, 'unknown')` để tránh lỗi?

**Đáp án:** Thường không. Nó biến nhiều dòng thiếu ID thành cùng khóa giả và có thể gộp nhầm dữ liệu. Validate, phân loại, cách ly dòng lỗi hoặc tạo ID theo hợp đồng nguồn trước khi MERGE.

### Bài 8 — Retry cộng điểm

API dùng MERGE Account rồi SET points = points + 50. Client timeout và gửi lại.

**Câu hỏi:** Có thể bị cộng 100 dù chỉ có một Account không?

**Đáp án:** Có. Cần commandId ổn định, receipt có uniqueness constraint và cập nhật Account trong cùng transaction.

### Bài 9 — Import 1.000 dòng

Một batch có 1.000 dòng nhưng chỉ 800 customerId phân biệt; `RETURN count(c)` sau MERGE báo 1.000.

**Câu hỏi:** Có 1.000 Customer mới không?

**Đáp án:** Không thể kết luận như vậy. Count phản ánh số dòng kết quả; cần đếm node theo business key, kiểm tra duplicate key và thống kê tạo/match riêng.

### Bài 10 — Cleanup nhanh bằng DETACH DELETE

Hai Customer có cùng email nhưng một node giữ OrderLine liên quan gián tiếp qua Order.

**Câu hỏi:** Có thể xóa node đến sau không?

**Đáp án:** Không trước khi xác định canonical, property và toàn bộ relationship cần giữ. Cần backup, kiểm thử chuyển cạnh, xác minh bất biến và chỉ xóa theo change plan.

## 25. Checklist trước khi đóng sự cố

- [ ] Xác nhận trùng **node**, **relationship** hay chỉ trùng hàng kết quả.
- [ ] Ghi rõ business key, phạm vi tenant/source và quy tắc normalization.
- [ ] Kiểm tra giá trị null, blank, type và case/whitespace.
- [ ] Xem `SHOW CONSTRAINTS` và `SHOW INDEXES` ở database đang chạy.
- [ ] MERGE chỉ dùng thuộc tính nhận diện ổn định, không dùng status/name/lastSeenAt như key nếu có thể thay đổi.
- [ ] Với đường đi, bind node trước rồi MERGE relationship.
- [ ] Với relationship, xác định domain cho phép bao nhiêu cạnh theo cặp/hướng/type.
- [ ] Kiểm tra cardinality qua `MATCH`, `OPTIONAL MATCH`, `WITH` và `UNWIND`.
- [ ] Có uniqueness constraint phù hợp trước khi mở nhiều writer đồng thời.
- [ ] Java Driver/Spring Data Neo4j xử lý đúng transient failure, constraint conflict và ambiguous commit.
- [ ] Dùng command receipt nếu phép cộng/ghi sự kiện phải áp dụng một lần.
- [ ] Với cleanup, có backup, canonical rule và kiểm kê relationship/property.
- [ ] Chạy test cả tuần tự lẫn concurrency, bao gồm input mâu thuẫn và retry.
- [ ] Không log dữ liệu nhạy cảm trong parameter/exception/query diagnostic.
- [ ] Đã đối chiếu dữ liệu sau sửa và ghi nhận nguyên nhân phát sinh trùng.

## 26. Ghi nhớ

**MERGE trong Neo4j là thao tác khớp hoặc tạo theo một pattern được chỉ định**, không phải công cụ gộp dữ liệu trùng và cũng không thay thế **uniqueness constraint**. Dùng **khóa nghiệp vụ ổn định**, tách property thay đổi ra khỏi mẫu MERGE, và khi thao tác trên đường đi hãy **bind node trước rồi MERGE relationship**. Các trường hợp node trùng, relationship trùng và hàng kết quả bị nhân cần những cách chẩn đoán khác nhau.

Khi gặp lỗi constraint, đừng xóa ràng buộc hoặc retry vô hạn: xác định key, scope, payload và lịch ghi đồng thời. Với batch import, chuẩn hóa/dedupe theo nguồn; với Java Driver/Spring Data Neo4j, giữ ranh giới transaction và xử lý lỗi rõ ràng; với phép cộng dồn, dùng **commandId/receipt để chống áp dụng lặp**. Đối với dữ liệu đã trùng, **kiểm kê và bảo toàn relationship trước khi xóa node**, kiểm chứng graph trên môi trường thử rồi mới đặt constraint bảo vệ lâu dài.
