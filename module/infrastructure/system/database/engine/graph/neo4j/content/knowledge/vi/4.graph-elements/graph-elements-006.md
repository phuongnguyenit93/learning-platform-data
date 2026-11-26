# Khóa nghiệp vụ, định danh bên ngoài và giới hạn của định danh nội bộ

## 1. Mục tiêu và bối cảnh

Trong **property graph** của Neo4j, một **node** có danh tính riêng, có thể mang nhiều nhãn (*label*), nhiều thuộc tính (*property*) và nối với các node khác thông qua **relationship**. Khi ứng dụng đọc, nhập, cập nhật hoặc đồng bộ đồ thị, câu hỏi quan trọng là: **Làm sao biết hai bản ghi đang đề cập đến cùng một thực thể?**

Bài này thuộc chương **Thành phần đồ thị** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Module hướng đến mô hình hóa dữ liệu liên kết, truy vấn quan hệ/đường đi bằng **Cypher**, thiết kế **index, constraint**, tối ưu truy vấn, nhập dữ liệu và tích hợp với **Neo4j Java Driver** hoặc **Spring Data Neo4j**. Việc chọn đúng định danh là nền tảng của tất cả các công việc đó.

Sau bài học, bạn có thể:

1. Phân biệt **khóa nghiệp vụ**, **định danh bên ngoài** và **định danh nội bộ** do Neo4j quản lý.
2. Giải thích tại sao hai node có thuộc tính giống nhau vẫn có thể là **hai node khác nhau** và tại sao `elementId()` không nên trở thành khóa API lâu dài.
3. Chọn khóa bền vững cho các thực thể `Person`, `Customer`, `Order`, `Product` hoặc sự kiện có định danh riêng.
4. Tạo **uniqueness constraint** trên khóa đơn hay khóa ghép và dùng `MERGE` an toàn hơn khi nhập dữ liệu.
5. Thiết kế ánh xạ từ mã của nhiều hệ thống nguồn về **một thực thể chuẩn** trong đồ thị.
6. Xử lý các trường hợp mã thiếu, trùng, thay đổi hoặc có phạm vi duy nhất theo tenant/nguồn.
7. Đưa định danh nghiệp vụ vào truy vấn Cypher, Java Driver và mô hình Spring Data Neo4j.

## 2. Ba loại định danh cần phân biệt

Giả sử hệ thống lưu một khách hàng tên **An**:

```text
(:Customer {
  customerId: 'CUST-00042',
  crmId: 'CRM-872',
  fullName: 'Nguyễn An'
})
```

Tại một thời điểm, Neo4j còn có định danh kỹ thuật cho node đó, có thể đọc bằng `elementId(n)`. Ba giá trị phục vụ ba mục đích khác nhau:

| Khái niệm | Ai cấp/quản lý? | Ví dụ | Dùng cho việc gì? |
| --- | --- | --- | --- |
| **Khóa nghiệp vụ** (*business key*) | Hệ thống ứng dụng hoặc miền nghiệp vụ | `customerId = 'CUST-00042'` | Nhận diện khách hàng trong vòng đời dữ liệu, API, trao đổi dữ liệu |
| **Định danh bên ngoài** (*external identifier*) | Hệ thống nguồn/đối tác | `crmId = 'CRM-872'` | Liên kết bản ghi Neo4j với bản ghi ở CRM |
| **Định danh nội bộ Neo4j** | Cơ sở dữ liệu Neo4j | Giá trị do `elementId(n)` trả về | Tham chiếu phần tử ở ngữ cảnh kỹ thuật phù hợp, kiểm tra/truy vấn ngắn hạn |

**Một giá trị có thể đóng nhiều vai trò**, tùy hợp đồng dữ liệu: nếu CRM là hệ thống quản lý danh tính chính và mã CRM được bảo đảm ổn định, mã đó có thể là khóa nghiệp vụ của một ứng dụng. Nhưng khi nhiều hệ thống cùng tham gia, nên chủ động phân biệt **ID chuẩn của ứng dụng** với **ID theo từng nguồn**.

Không nên suy ra “hai bản ghi cùng tên Nguyễn An” là một người, hoặc “hai bản ghi khác email” là hai người. **Tên/email là thuộc tính mô tả**, còn việc đồng nhất thực thể phải dựa trên khóa đáng tin cậy và quy tắc nghiệp vụ.

## 3. Danh tính node khác với giá trị property

Hai lệnh tạo node sau đây tạo **hai phần tử đồ thị riêng biệt**:

```cypher
CREATE (:Person {fullName: 'Nguyễn An'});
CREATE (:Person {fullName: 'Nguyễn An'});
```

Dù hai node có cùng nhãn và property, chúng không tự được hợp nhất. Ngược lại, nếu cập nhật `fullName` của một node từ `'Nguyễn An'` thành `'Nguyễn Văn An'`, node vẫn là **cùng một node**.

### 3.1. Điều gì làm nên danh tính thực thể?

Trong nghiệp vụ, danh tính nên trả lời được câu hỏi:

- Đây có phải **cùng một người** sau khi đổi tên, email hay số điện thoại?
- Đây có phải **cùng một đơn hàng** sau khi trạng thái đổi từ `PENDING` sang `SHIPPED`?
- Đây có phải **cùng một sản phẩm** sau khi đổi tên hiển thị hoặc giá bán?
- Đây có phải **cùng một giao dịch** khi job nhập dữ liệu được chạy lại?
- Một mã có thể xuất hiện ở **hai tenant** hay **hai hệ thống nguồn** khác nhau không?

Một thuộc tính làm khóa phù hợp thường phải có **phạm vi duy nhất được định nghĩa rõ**, đủ **ổn định**, có thể **tra cứu** và được **bảo vệ bằng quy tắc dữ liệu**.

### 3.2. Khóa nghiệp vụ tự nhiên và khóa do ứng dụng cấp

Có hai nhóm thường gặp:

| Loại khóa | Ví dụ | Ưu điểm | Giới hạn |
| --- | --- | --- | --- |
| **Khóa tự nhiên** (*natural key*) | Mã số thuế doanh nghiệp trong một phạm vi quản lý cụ thể; ISBN của ấn bản sách | Có ý nghĩa ngoài hệ thống | Có thể thay đổi, được tái cấp, có ngoại lệ hoặc chỉ duy nhất trong phạm vi cụ thể |
| **Khóa do ứng dụng cấp** (*application-assigned/surrogate key*) | `customerId` là UUID hoặc mã sinh từ dịch vụ | Ít phụ thuộc thay đổi thuộc tính mô tả | Cần cơ chế cấp mã, chống trùng và duy trì ánh xạ |

Từ “khóa nghiệp vụ” trong bài này chỉ **định danh ứng dụng dùng lâu dài để nhận diện thực thể**, không bắt buộc là một chuỗi có ý nghĩa với con người. Một UUID do ứng dụng cấp và lưu làm `customerId` vẫn có thể là định danh bền vững cho API và tích hợp.

**Tránh dùng làm khóa mặc định:** tên người, tên sản phẩm, email dễ thay đổi, số điện thoại, địa chỉ hoặc giá trị có thể được nhiều thực thể chia sẻ. Các trường này có thể được index để tra cứu, nhưng tra cứu thuận tiện **khác** với bảo đảm danh tính.

## 4. Giới hạn của định danh nội bộ Neo4j

Neo4j có các hàm liên quan đến danh tính phần tử đồ thị:

```cypher
MATCH (p:Person {personId: 'P001'})
RETURN
  p.personId AS businessId,
  elementId(p) AS technicalElementId;
```

`elementId(p)` trả về **một chuỗi nhận diện phần tử do Neo4j cung cấp**. Giá trị đó hữu ích cho những thao tác kỹ thuật ngắn hạn, nhưng **không có hợp đồng ổn định như một ID nghiệp vụ** khi dữ liệu thay đổi, được xuất/nhập hoặc được truy cập giữa các thời điểm/giao dịch khác nhau.

### 4.1. `elementId()` không phải khóa nghiệp vụ bền vững

Theo hợp đồng của Neo4j, `elementId()` bảo đảm tính duy nhất của phần tử **trong phạm vi giao dịch**; không nên suy diễn từ đó một cam kết giữ nguyên mã vĩnh viễn giữa các giao dịch. Đặc biệt:

- Khi **xóa và tạo lại** node/relationship, phần tử mới là một thực thể kỹ thuật khác dù mang cùng dữ liệu nghiệp vụ.
- Khi **sao chép, tái tạo, xuất/nhập hoặc di chuyển** đồ thị, không nên giả định giá trị `elementId()` vẫn giống trước.
- Ứng dụng **không nên phân tích cấu trúc** bên trong chuỗi `elementId()` để suy ra ID số, vị trí lưu trữ, database hay thứ tự tạo.
- Nếu dùng `elementId()` trong URL/API như `/customers/{elementId}`, một thao tác chuyển dữ liệu có thể làm liên kết cũ không còn dùng được như kỳ vọng.

Vì vậy, API nên nhận một khóa được quản lý ở cấp ứng dụng:

```text
GET /customers/CUST-00042       ← ID nghiệp vụ
GET /orders/ORDER-2026-00017    ← ID nghiệp vụ
```

Việc hiển thị `elementId()` trong Neo4j Browser hoặc công cụ chẩn đoán không sai; vấn đề là **xem nó như hợp đồng định danh lâu dài** cho dữ liệu bên ngoài.

### 4.2. `id()` và tính tương thích phiên bản

Trong nhiều phiên bản Neo4j, hàm truyền thống `id(n)` trả về một **định danh số nội bộ**. Ở các phiên bản Cypher hiện đại, `id()` được xem là **cơ chế cũ/đã bị deprecate**; không nên thiết kế ứng dụng mới dựa vào nó. Định danh số có thể bị **tái sử dụng** sau khi phần tử bị xóa, nên đặc biệt nguy hiểm nếu lưu ở hệ thống ngoài như một khóa vĩnh viễn.

Ví dụ chỉ để nhận biết mã cũ trong truy vấn legacy:

```cypher
// Chỉ dùng khi phiên bản Neo4j đang vận hành còn hỗ trợ id()
MATCH (p:Person)
RETURN id(p) AS legacyInternalId
LIMIT 5;
```

Khi làm việc với phiên bản mới, kiểm tra tài liệu hàm được hỗ trợ; dù dùng `id()` hay `elementId()`, **định danh nội bộ không thay thế mã nghiệp vụ**.

### 4.3. Tại sao không tự chuyển kiểu `elementId()`?

Không làm:

```text
elementId = "..." 
→ cắt chuỗi, lấy phần số
→ lưu như customerId
→ truyền sang hệ thống khác
```

Định dạng nội bộ không phải một giao thức ID nghiệp vụ công khai. Hãy coi `elementId()` là một **chuỗi opaque**: đọc hoặc so sánh khi cần trong ngữ cảnh được hỗ trợ, không bóc tách hoặc tái định nghĩa.

## 5. Định danh bên ngoài: luôn xác định nguồn và phạm vi

Một khách hàng có thể xuất hiện đồng thời trong hệ thống CRM, hỗ trợ khách hàng và nền tảng thương mại điện tử:

```text
CRM:         customerId = "42"
Support:     contactId  = "42"
Commerce:    buyerId    = "C-4200"
```

Hai giá trị `'42'` ở hai hệ thống **không nhất thiết** biểu diễn cùng một người. Bản thân chuỗi ID chưa đủ: phải biết **nó được cấp bởi hệ thống nào**.

### 5.1. Khóa ngoài có namespace

Thay vì chỉ lưu `externalId`, dùng khóa ghép:

```text
(sourceSystem, externalId)
('crm',     '42')
('support', '42')
('shop',    'C-4200')
```

Từng cặp có thể là duy nhất trong phạm vi hệ thống nguồn. Nếu dữ liệu còn phân chia theo khách hàng doanh nghiệp (*tenant*), có thể cần:

```text
(tenantId, sourceSystem, externalId)
('TENANT-A', 'crm', '42')
('TENANT-B', 'crm', '42')
```

Đó là **khóa ghép**: tính duy nhất được xác định bởi **tổ hợp các giá trị**, không phải từng giá trị riêng lẻ.

### 5.2. Hai cách biểu diễn external ID trong đồ thị

**Cách A – Property trên node chính** khi nguồn ít và hợp đồng tương đối ổn định:

```cypher
(:Customer {
  customerId: 'CUST-00042',
  crmId: 'CRM-872',
  commerceId: 'BUY-390'
})
```

Ưu điểm: dễ tra cứu trong ứng dụng nhỏ. Nhược điểm: khi thêm nhiều nhà cung cấp, nhiều tài khoản trên cùng nguồn hoặc lịch sử thay đổi ID, node dễ tích lũy các property đặc thù của từng nguồn.

**Cách B – Node ánh xạ định danh** khi một thực thể có nhiều mã ngoài:

```text
(:ExternalIdentity {source: 'crm', externalId: 'CRM-872'})
                     |
                     | [:IDENTIFIES]
                     v
          (:Customer {customerId: 'CUST-00042'})
                     ^
                     | [:IDENTIFIES]
                     |
(:ExternalIdentity {source: 'shop', externalId: 'BUY-390'})
```

Ở cách B, mỗi `ExternalIdentity` là một ánh xạ có thể lưu thêm `firstSeenAt`, `verifiedAt` hoặc trạng thái của nguồn. Khóa nghiệp vụ `Customer.customerId` vẫn là định danh chuẩn được ứng dụng dùng trong các truy vấn liên kết.

**Không tự động hợp nhất** hai khách hàng chỉ vì cùng tên/email. Việc kết luận hai mã ngoài chỉ đến cùng một khách hàng cần quy tắc đối soát đủ tin cậy, bởi nhập nhầm ánh xạ sẽ dẫn đến nối dữ liệu của hai người khác nhau.

## 6. Constraint: định danh được bảo vệ bằng quy tắc dữ liệu

Chỉ viết `personId` trong property **không khiến Neo4j tự bảo đảm giá trị duy nhất**. Nếu lặp `CREATE`, có thể tạo hai node trùng `personId`. Để hệ thống bảo vệ khóa, dùng **uniqueness constraint** phù hợp.

### 6.1. Khóa duy nhất trên một property

```cypher
CREATE CONSTRAINT person_id_unique IF NOT EXISTS
FOR (p:Person)
REQUIRE p.personId IS UNIQUE;
```

Ý nghĩa: không thể có **hai node mang nhãn `Person`** với cùng giá trị `personId` khi constraint đang có hiệu lực.

Ví dụ:

```cypher
CREATE (:Person {personId: 'P001', fullName: 'An'});
```

Nếu đã có `:Person {personId: 'P001'}` và constraint trên được áp dụng, thao tác tạo một node `Person` khác cùng `personId` sẽ bị từ chối.

**Giới hạn phạm vi:** Constraint `Person.personId` áp dụng cho node **có nhãn `Person`**. Một node chỉ mang `:Customer` nhưng không có `:Person` không nằm trong phạm vi này. Neo4j không tự hiểu `Customer` là “nhãn con” của `Person`.

### 6.2. Uniqueness chưa bắt buộc property tồn tại

Uniqueness constraint có ý nghĩa **“các giá trị khóa đã có không được trùng nhau”**, không nhất thiết bảo đảm **mọi node đều có property khóa**.

Ví dụ, nếu chỉ có uniqueness constraint trên `Person.personId`, node sau có thể tồn tại mà **không có `personId`**:

```cypher
CREATE (:Person {fullName: 'Người chưa xác định'});
```

Muốn yêu cầu cả **tồn tại** lẫn **duy nhất**, cần xem xét property existence constraint hoặc node key constraint tương ứng và điều kiện hỗ trợ của phiên bản, edition Neo4j đang sử dụng.

Lựa chọn trong ứng dụng:

- Kiểm tra bắt buộc ID **trước khi gọi Cypher**.
- Dùng constraint phù hợp ở database để bảo vệ toàn vẹn dữ liệu.
- Định nghĩa quy tắc cho bản ghi chưa xác minh danh tính, thay vì tự gán mã giả trùng nhau.

### 6.3. Khóa ghép cho dữ liệu đa tenant

Khi `customerId` chỉ duy nhất **trong một tenant**, dùng:

```cypher
CREATE CONSTRAINT customer_tenant_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
```

Giờ đây:

```text
(:Customer {tenantId: 'TENANT-A', customerId: '42'})
(:Customer {tenantId: 'TENANT-B', customerId: '42'})
```

có thể cùng tồn tại vì hai **tổ hợp** khác nhau.

Khi thao tác với khách hàng, phải dùng **đầy đủ khóa ghép**:

```cypher
MATCH (c:Customer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c;
```

Chỉ dùng `customerId = '42'` có thể khớp khách hàng của **nhiều tenant**, gây truy cập hoặc cập nhật sai đối tượng.

**Lưu ý:** Composite uniqueness constraint không tự giải quyết bản ghi **thiếu một trong các thành phần khóa**. Ứng dụng cần kiểm tra đầy đủ giá trị; cân nhắc node key/existence constraint nếu phù hợp.

### 6.4. Khóa ghép cho nguồn dữ liệu bên ngoài

Với cách dùng node `ExternalIdentity`:

```cypher
CREATE CONSTRAINT external_identity_unique IF NOT EXISTS
FOR (x:ExternalIdentity)
REQUIRE (x.source, x.externalId) IS UNIQUE;
```

Constraint này bảo vệ một mã của **một nguồn cụ thể**, không khẳng định rằng cùng chuỗi ID ở nguồn khác là cùng thực thể.

Đối với hệ thống đa tenant, có thể mở rộng thành `(x.tenantId, x.source, x.externalId)`; chọn đúng phạm vi theo hợp đồng dữ liệu.

### 6.5. Xem constraint và index hiện tại

```cypher
SHOW CONSTRAINTS;
SHOW INDEXES;
```

Uniqueness constraint thường có cơ chế index hỗ trợ để duy trì/tìm khóa. Đừng tạo thêm index trùng mục đích mà chưa xem các index hiện có. Với dữ liệu lớn, phân biệt **khóa để nhận diện thực thể** và **cột dùng để lọc báo cáo**; không phải trường lọc nào cũng cần uniqueness.

## 7. Dùng MERGE để nhập dữ liệu theo đúng danh tính

### 7.1. `CREATE` và `MERGE` không có cùng nghĩa

`CREATE` tạo phần tử mới:

```cypher
CREATE (p:Person {
  personId: 'P001',
  fullName: 'An'
})
RETURN p;
```

`MERGE` tìm mẫu phù hợp; nếu không tìm thấy thì tạo:

```cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.fullName = $fullName,
              p.createdAt = datetime()
RETURN p;
```

Khi nhập lại bản ghi `personId = 'P001'`, `MERGE` có thể tìm node đã có **thay vì tạo thêm**, nếu mẫu khớp. Để bảo đảm tính duy nhất trước tình huống ghi đồng thời, cần uniqueness constraint cho `Person.personId`.

### 7.2. Chỉ đưa khóa ổn định vào mẫu MERGE

Tránh dùng các trường thay đổi như tên/email trong mẫu định danh:

```cypher
// Dễ dẫn tới cố tạo node khác khi tên thay đổi
MERGE (p:Person {
  personId: $personId,
  fullName: $fullName
})
RETURN p;
```

Ví dụ node cũ có `personId = 'P001'` và `fullName = 'An'`; nguồn cập nhật thành `fullName = 'Nguyễn An'`. Mẫu trên **không khớp** với node cũ, vì yêu cầu cả ID và tên. Hệ quả:

- Nếu thiếu constraint: có thể tạo **node trùng danh tính nghiệp vụ**.
- Nếu đã có uniqueness constraint: có thể gặp lỗi xung đột thay vì cập nhật đúng node.

Giải pháp:

```cypher
MERGE (p:Person {personId: $personId})
ON CREATE SET p.createdAt = datetime()
SET p.fullName = $fullName,
    p.updatedAt = datetime()
RETURN p.personId AS personId, p.fullName AS fullName;
```

`MERGE` xác định **người nào**; `SET` xác định **thuộc tính hiện tại cần cập nhật**.

### 7.3. Với khóa ghép, đưa đủ thành phần vào MERGE

```cypher
MERGE (c:Customer {
  tenantId: $tenantId,
  customerId: $customerId
})
ON CREATE SET c.createdAt = datetime()
SET c.fullName = $fullName
RETURN c;
```

Đây là cách để một job đồng bộ phân biệt khách hàng `'42'` của `TENANT-A` và khách hàng `'42'` của `TENANT-B`.

**Quan trọng:** Trước khi chạy, bảo đảm `$tenantId` và `$customerId` không phải `null`. `MERGE` với property khóa bằng `null` có thể gây lỗi; chuẩn hóa/loại bỏ bản ghi thiếu khóa trước khi ghi.

### 7.4. MERGE không tự giải quyết toàn bộ dữ liệu trùng

Nếu đồ thị đã có **hai node `Person` cùng `personId`** từ trước, việc chuyển sang `MERGE` không tự gộp hai node đó hay di chuyển các relationship liên quan. Cần quy trình đối soát:

1. Xác minh bản ghi trùng thật sự đại diện **cùng thực thể**.
2. Chọn node chuẩn và xác định cách giữ thuộc tính/lịch sử.
3. Di chuyển hoặc tái tạo các relationship cần thiết theo quy tắc nghiệp vụ.
4. Loại bản ghi thừa sau khi kiểm tra tác động.
5. Tạo constraint để hạn chế tái diễn.

Việc hợp nhất không nên làm chỉ vì hai tên, email hoặc trường tìm kiếm giống nhau; một thao tác nhầm có thể trộn dữ liệu của **hai người khác nhau**.

## 8. Bài toán tích hợp: một khách hàng, nhiều ID nguồn

Giả sử ứng dụng có khách hàng chuẩn `'CUST-00042'` và bản ghi nguồn từ CRM `'CRM-872'`.

### 8.1. Tạo khóa chuẩn và khóa ngoại

```cypher
CREATE CONSTRAINT customer_canonical_id_unique IF NOT EXISTS
FOR (c:CanonicalCustomer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT identity_source_id_unique IF NOT EXISTS
FOR (x:ExternalIdentity)
REQUIRE (x.source, x.externalId) IS UNIQUE;
```

Sau đó ghi liên kết:

```cypher
MERGE (c:CanonicalCustomer {customerId: $customerId})
ON CREATE SET c.createdAt = datetime()
SET c.fullName = $fullName
MERGE (x:ExternalIdentity {
  source: $source,
  externalId: $externalId
})
ON CREATE SET x.firstSeenAt = datetime()
MERGE (x)-[:IDENTIFIES]->(c)
RETURN c.customerId AS customerId,
       x.source AS source,
       x.externalId AS externalId;
```

Ví dụ tham số:

```json
{
  "customerId": "CUST-00042",
  "fullName": "Nguyễn An",
  "source": "crm",
  "externalId": "CRM-872"
}
```

Đây là một **mô hình minh họa**. Trong thực tế, trước khi tạo `IDENTIFIES` phải xác minh rằng mã ngoài đó thực sự thuộc về `customerId` tương ứng.

### 8.2. Tra từ mã nguồn sang ID chuẩn

```cypher
MATCH (x:ExternalIdentity {
  source: $source,
  externalId: $externalId
})-[:IDENTIFIES]->(c:CanonicalCustomer)
RETURN c.customerId AS customerId,
       c.fullName AS fullName;
```

Đường truy vấn này trả lời: **bản ghi CRM có mã `CRM-872` tương ứng với khách hàng chuẩn nào?**

### 8.3. Lưu ý về ánh xạ một–một

`MERGE (x)-[:IDENTIFIES]->(c)` tìm hoặc tạo **mối liên kết đến node `c`**, nhưng bản thân nó không tự bảo đảm rằng `x` không đồng thời có thêm `IDENTIFIES` đến một khách hàng chuẩn **khác**.

Nếu nghiệp vụ yêu cầu một external ID tại một thời điểm chỉ ánh xạ đến **một** khách hàng chuẩn, cần áp đặt quy tắc ở quy trình ghi và kiểm tra:

```cypher
MATCH (x:ExternalIdentity)-[:IDENTIFIES]->(c:CanonicalCustomer)
WITH x, count(DISTINCT c) AS canonicalCount
WHERE canonicalCount > 1
RETURN x.source AS source,
       x.externalId AS externalId,
       canonicalCount;
```

Đây là truy vấn **phát hiện** ánh xạ bất thường, không tự khắc phục. Nên đưa logic xác thực và xử lý xung đột vào giao dịch ghi; nếu cần, thiết kế lưu lịch sử đổi ánh xạ tách khỏi quan hệ đang có hiệu lực.

## 9. Định danh cho relationship và sự kiện

Không chỉ node mới cần định danh nghiệp vụ. Nếu relationship đại diện cho **một sự kiện độc lập**, chẳng hạn `TRANSFERRED`, `PURCHASED` hoặc `BOOKED`, mỗi sự kiện có thể cần ID riêng.

```text
(:Account {accountId: 'A'})
   ├──[:TRANSFERRED {transferId: 'T001', amount: 100000}]──→ (:Account {accountId: 'B'})
   └──[:TRANSFERRED {transferId: 'T002', amount: 250000}]──→ (:Account {accountId: 'B'})
```

Hai relationship cùng type, cùng chiều và cùng hai đầu mút là **hai giao dịch hợp lệ** vì có `transferId` khác nhau.

### 9.1. Constraint trên định danh relationship

Trong các phiên bản Neo4j hỗ trợ uniqueness constraint cho relationship:

```cypher
CREATE CONSTRAINT transfer_id_unique IF NOT EXISTS
FOR ()-[r:TRANSFERRED]-()
REQUIRE r.transferId IS UNIQUE;
```

Constraint ngăn hai relationship `TRANSFERRED` cùng mang một giá trị `transferId`. Nó **không cấm** hai giao dịch khác ID giữa cùng hai tài khoản.

Với sự kiện chỉ duy nhất trong một nguồn, có thể xem xét khóa ghép `(r.source, r.transferId)` nếu phiên bản hỗ trợ và hợp đồng dữ liệu yêu cầu.

### 9.2. MERGE phải thể hiện danh tính sự kiện

```cypher
MATCH (from:Account {accountId: $fromAccountId})
MATCH (to:Account {accountId: $toAccountId})
MERGE (from)-[r:TRANSFERRED {transferId: $transferId}]->(to)
ON CREATE SET
  r.amount = $amount,
  r.occurredAt = datetime($occurredAt)
RETURN r.transferId AS transferId;
```

Nếu chỉ dùng `MERGE (from)-[:TRANSFERRED]->(to)`, các giao dịch khác nhau giữa cùng hai tài khoản có thể bị hiểu là **một quan hệ**, làm mất thông tin về những lần giao dịch tiếp theo.

Nếu `transferId` đã tồn tại nhưng gắn với hai tài khoản **khác** dữ liệu mới, nên coi đó là **xung đột cần đối soát**; uniqueness constraint có thể khiến giao dịch mới báo lỗi. Không được tự chuyển đầu mút chỉ để thao tác thành công.

### 9.3. Khi nên dùng node sự kiện riêng?

Nếu sự kiện có vòng đời riêng, nhiều trạng thái hoặc cần liên kết với hóa đơn, thanh toán, đối soát, cân nhắc:

```text
(:Account A)-[:SENT]->(:Transfer {transferId: 'T001'})-[:RECEIVED_BY]->(:Account B)
```

Nút `Transfer` có thể được nhận diện bằng `transferId` và có thêm relationship đến `PaymentMethod`, `Invoice` hoặc `AuditRecord`. Chọn node hay relationship dựa trên yêu cầu mô hình; cả hai đều có thể lưu property định danh nghiệp vụ.

## 10. Nhập dữ liệu: chống trùng, chống mất liên kết

Định danh ổn định đặc biệt quan trọng khi nhập dữ liệu CSV, qua API hoặc chạy job định kỳ.

### 10.1. Nguyên tắc tái chạy idempotent

Một job tải cùng bản ghi khách hàng **hai lần** không nên tạo ra hai khách hàng; một sự kiện thanh toán có cùng mã không nên được ghi thành hai giao dịch.

Với node:

```cypher
UNWIND $customers AS row
WITH row
WHERE row.customerId IS NOT NULL
  AND trim(row.customerId) <> ''
MERGE (c:Customer {customerId: row.customerId})
ON CREATE SET c.createdAt = datetime()
SET c.fullName = row.fullName,
    c.updatedAt = datetime();
```

Đây là một mẫu nhập đơn giản, giả sử `$customers` là danh sách map đã được kiểm tra kiểu dữ liệu. Trong hệ thống thực tế, còn phải **ghi nhận/loại riêng** các bản ghi thiếu hoặc không hợp lệ để không mất dữ liệu trong im lặng. Cần có uniqueness constraint trên `Customer.customerId` và xử lý lỗi khi nhiều job ghi đồng thời.

### 10.2. Tránh nối theo tên hiển thị

Không nên nối đơn hàng với khách hàng bằng cách tìm tên:

```cypher
// Mẫu nguy hiểm: fullName có thể trùng hoặc thay đổi
MATCH (c:Customer {fullName: $customerName})
MATCH (o:Order {orderId: $orderId})
CREATE (c)-[:PLACED]->(o);
```

Nếu hai người trùng tên, truy vấn có thể nối đơn tới **nhiều node khách hàng**. Thay vào đó:

```cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (o:Order {orderId: $orderId})
MERGE (c)-[:PLACED]->(o);
```

Giả định nghiệp vụ mỗi đơn hàng có đúng **một quan hệ `PLACED` từ khách hàng sở hữu** và quy tắc này được bảo vệ ở tầng ghi. `MERGE` không tự bảo đảm một đơn không bị nối từ **hai khách hàng khác nhau**; hãy có quy trình kiểm tra quyền sở hữu đơn.

### 10.3. Export/import phải giữ khóa nghiệp vụ

Ví dụ dữ liệu xuất:

```csv
customerId,fullName
CUST-00042,Nguyễn An
CUST-00043,Trần Bình
```

Quan hệ đơn hàng nên tham chiếu qua khóa nghiệp vụ:

```csv
orderId,customerId
ORDER-00017,CUST-00042
ORDER-00018,CUST-00043
```

Không dựa vào `elementId()`/`id()` của database nguồn để tạo lại liên kết tại database đích. Khi import sang môi trường mới, hãy tìm hoặc tạo node theo **`customerId`/`orderId`**, sau đó tạo relationship theo các mã đó.

### 10.4. Chuẩn hóa khóa có quy tắc

Hãy xác định trước:

- Có phân biệt `'ABC'` và `'abc'` không?
- Có cho phép khoảng trắng ở đầu/cuối không?
- ID có thể chứa số `0` ở đầu, như `'00042'`, không?
- ID được lưu dạng **chuỗi** hay **số**?
- Có cần namespace theo tenant, nguồn, quốc gia hoặc phiên bản hệ thống không?

Không được tùy tiện chuyển `'00042'` thành số `42` nếu mã nguồn yêu cầu giữ số 0. Cũng không nên tự `toLower()` mọi ID vì có hệ thống coi chữ hoa/chữ thường là **hai mã khác nhau**.

Chuẩn hóa phải dựa trên **quy ước của nơi cấp mã** và áp dụng nhất quán cho quá trình nhập, truy vấn, API và constraint.

## 11. Tích hợp Neo4j Java Driver và Spring Data Neo4j

### 11.1. Java Driver: tham số là khóa nghiệp vụ

Ứng dụng Java nên truyền ID qua **parameters**, không nối giá trị người dùng vào câu Cypher:

```cypher
MATCH (c:Customer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c.customerId AS id, c.fullName AS fullName;
```

Map tham số tương ứng:

```json
{
  "tenantId": "TENANT-A",
  "customerId": "CUST-00042"
}
```

Khóa ở đây là **hai property thuộc node**, nên khi API yêu cầu khách hàng theo tenant, phải truyền đầy đủ hai giá trị. Việc dùng tham số giúp phân biệt cấu trúc câu truy vấn với dữ liệu đầu vào và hỗ trợ tái sử dụng truy vấn.

### 11.2. Spring Data Neo4j: nhận diện entity bằng ID ứng dụng

Với Spring Data Neo4j, có thể ánh xạ một khóa ID do ứng dụng cấp vào property của node:

```java
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Customer")
public class Customer {
    @Id
    private String customerId;

    private String fullName;

    protected Customer() {
    }

    public Customer(String customerId, String fullName) {
        this.customerId = customerId;
        this.fullName = fullName;
    }
}
```

Trong ví dụ này, `customerId` được **ứng dụng cung cấp** và lưu như property của `:Customer`. `@Id` giúp Spring Data Neo4j nhận diện entity khi ánh xạ, nhưng **không tự tạo uniqueness constraint trên database**; cần khai báo constraint tương ứng.

Spring Data Neo4j còn có cơ chế ID do framework/database tạo, tùy phiên bản. Nếu dùng định danh kỹ thuật nội bộ cho mapping, vẫn cần một **mã ứng dụng bền vững** riêng khi dữ liệu phải xuất/nhập hoặc liên kết qua API. Với khóa ghép, cần thiết kế cách ánh xạ và nhận diện trong repository theo khả năng của phiên bản thư viện; không mặc định annotation `@Id` đơn lẻ hỗ trợ mọi dạng composite key.

### 11.3. Khi ID thay đổi thì sao?

Trong API, nên coi khóa chuẩn là **bất biến** nếu có thể. Nếu nguồn yêu cầu đổi mã, không nên cập nhật mã ở mọi node một cách tùy tiện. Cần:

1. Xác minh đó là **đổi mã của cùng thực thể** hay **một thực thể mới**.
2. Giữ ánh xạ từ mã cũ sang mã mới trong giai đoạn chuyển tiếp nếu cần.
3. Cập nhật tham chiếu ở các hệ thống tích hợp theo kế hoạch.
4. Kiểm tra constraint, cache, API và các job đồng bộ.

Nếu mã ngoài thường xuyên thay đổi, đây là thêm một lý do để duy trì **ID chuẩn ổn định** và mô hình `ExternalIdentity` có lịch sử.

## 12. Định danh và tối ưu truy vấn

Truy vấn theo một khóa rõ ràng thường là điểm bắt đầu tốt cho đồ thị lớn:

```cypher
MATCH (c:Customer {customerId: $customerId})
MATCH (c)-[:PLACED]->(o:Order)
RETURN o.orderId AS orderId
ORDER BY orderId;
```

Khi có constraint/index phù hợp cho `Customer.customerId`, bộ tối ưu **có thể** bắt đầu bằng thao tác tra cứu node theo khóa trước khi duyệt relationship `PLACED`.

So sánh với truy vấn thiếu khóa:

```cypher
MATCH (c:Customer)-[:PLACED]->(o:Order)
WHERE c.fullName CONTAINS $nameFragment
RETURN o.orderId;
```

Truy vấn tên mơ hồ có thể khớp **nhiều khách hàng** và duyệt nhiều quan hệ; nó phục vụ nhu cầu tìm kiếm khác với tra cứu theo ID.

Để kiểm tra kế hoạch:

```cypher
EXPLAIN
MATCH (c:Customer {customerId: $customerId})-[:PLACED]->(o:Order)
RETURN o.orderId;
```

`EXPLAIN` chỉ lập kế hoạch; `PROFILE` thực thi truy vấn để thu thập số liệu. Không phải cứ tạo index là mọi truy vấn đều dùng index; quyết định phụ thuộc bộ tối ưu, thống kê và điều kiện lọc.

**Điểm thiết kế:** Định danh ổn định giúp xác định chính xác **nút xuất phát** cho các truy vấn mối quan hệ/đường đi, đồng thời hỗ trợ truy vết và điều tra lỗi khi hệ thống vận hành.

## 13. Những lỗi thường gặp và cách phòng tránh

| Sai lầm | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Dùng `elementId(n)` như khóa API, khóa CSV hoặc ID liên hệ dài hạn | Liên kết có thể mất tính ổn định khi dữ liệu được tái tạo/di chuyển | Sử dụng mã ứng dụng bền vững |
| Dùng `id(n)` làm mã khách hàng | ID số nội bộ có thể được tái sử dụng; API phụ thuộc chi tiết lưu trữ | Dùng `customerId` riêng |
| Xem hai node cùng `fullName` là cùng người | Gộp nhầm người trùng tên | Đối soát bằng khóa đáng tin cậy |
| Dùng `MERGE` theo cả ID lẫn tên/email | Đổi giá trị mô tả có thể làm mẫu không khớp | `MERGE` theo khóa, `SET` thuộc tính thay đổi |
| Không đặt uniqueness constraint cho khóa | Nhập lại hoặc ghi đồng thời có thể tạo node trùng | Thêm constraint phù hợp với nhãn và phạm vi |
| Cho rằng uniqueness luôn bắt buộc property tồn tại | Có node thiếu ID nhưng vẫn hợp lệ theo constraint duy nhất | Kiểm tra dữ liệu đầu vào, cân nhắc existence/node key constraint |
| Dùng `externalId = '42'` mà không ghi nguồn | Nhầm ID CRM với ID support | Khóa ghép `(source, externalId)` |
| Quên tenant trong `MATCH` hoặc `MERGE` | Cập nhật/đọc nhầm thực thể ở tenant khác | Luôn dùng đủ khóa ghép |
| Tự bỏ số 0 đầu, đổi chữ hoa–thường của mã | Tạo xung đột hoặc tìm sai bản ghi | Chuẩn hóa theo hợp đồng nguồn |
| Dùng một quan hệ cho nhiều giao dịch khác nhau | Mất lịch sử sự kiện | Gắn mã giao dịch hoặc dùng node sự kiện |
| Cho rằng `MERGE` tự xóa dữ liệu trùng đã có | Node/cạnh trùng vẫn tồn tại | Đối soát, dọn dữ liệu có kiểm soát rồi đặt constraint |
| Tự tạo `IDENTIFIES` sang nhiều khách hàng cho cùng mã nguồn | Một ID ngoài dẫn đến nhiều thực thể chuẩn | Ràng buộc quy trình ghi, kiểm tra ánh xạ, xử lý xung đột |

## 14. Bài tập thực hành có đáp án

Nên thực hành trên **database thử nghiệm**. Các ví dụ dùng nhãn riêng hoặc mã có tiền tố `GE006-` để tránh nhầm với dữ liệu nghiệp vụ khác.

### Bài 1. Chọn khóa cho sản phẩm

Một sản phẩm có `name`, `price`, `sku` và `supplierId`. Tên và giá có thể thay đổi, `sku` chỉ duy nhất **trong một nhà cung cấp**. Khóa nào phù hợp?

**Đáp án gợi ý:** Có thể dùng khóa ghép `(supplierId, sku)` nếu hợp đồng với nguồn bảo đảm duy nhất và ổn định. Nếu sản phẩm có mã chuẩn do ứng dụng cấp, dùng `productId` làm khóa bền vững rồi lưu `supplierId`/`sku` làm tham chiếu nguồn. Không chọn `name` hoặc `price` làm khóa.

### Bài 2. Viết constraint theo tenant

Cho `Customer` có `tenantId` và `customerId`; một `customerId` được phép lặp giữa hai tenant nhưng không được lặp trong cùng tenant.

**Đáp án:**

```cypher
CREATE CONSTRAINT ge006_customer_tenant_key IF NOT EXISTS
FOR (c:Customer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
```

Khi truy vấn:

```cypher
MATCH (c:Customer {
  tenantId: $tenantId,
  customerId: $customerId
})
RETURN c;
```

### Bài 3. Nhận diện lỗi MERGE

Đã có `(:Person {personId: 'GE006-P001', fullName: 'An'})`. Job nhập lần sau:

```cypher
MERGE (:Person {personId: 'GE006-P001', fullName: 'Nguyễn An'});
```

Vì sao không phù hợp?

**Đáp án:** `MERGE` phải khớp **toàn bộ map**, nhưng tên đã khác. Nó có thể cố tạo node mới hoặc gặp lỗi constraint. Hãy `MERGE` theo `personId`, sau đó `SET p.fullName = ...`.

### Bài 4. Chọn giữa ID nội bộ và ID ứng dụng

Ứng dụng cần tạo URL xem khách hàng, đồng bộ sang hệ thống thứ ba và nhập lại dữ liệu trong môi trường thử nghiệm. Nên truyền `elementId(c)` hay `c.customerId`?

**Đáp án:** Chọn `c.customerId` được quản lý ổn định ở cấp ứng dụng. `elementId()` chỉ thích hợp cho ngữ cảnh kỹ thuật phù hợp, không có cam kết duy trì như khóa nghiệp vụ xuyên giao dịch/môi trường.

### Bài 5. ID từ nhiều hệ thống

CRM có `customerId = '42'` và hệ thống hỗ trợ có `contactId = '42'`. Có được tự động kết luận đây là cùng người không?

**Đáp án:** Không. Cần xem hai mã thuộc **hai namespace khác nhau**. Dùng tổ hợp `(source, externalId)` để nhận diện bản ghi nguồn và chỉ liên kết với cùng node chuẩn sau khi đã có bằng chứng đối soát.

### Bài 6. Cùng hai tài khoản, hai giao dịch

A chuyển B lần đầu với `transferId = 'T001'`, lần hai với `transferId = 'T002'`. Có nên `MERGE (a)-[:TRANSFERRED]->(b)` cho cả hai lần không?

**Đáp án:** Không nếu muốn giữ hai sự kiện riêng. Dùng định danh `transferId` trên từng relationship hoặc tạo node `Transfer` cho mỗi giao dịch. Có thể thiết lập uniqueness constraint trên mã giao dịch để job chạy lại không ghi trùng cùng một sự kiện.

### Bài 7. Viết truy vấn phát hiện khóa trùng đã có

Trong database thử nghiệm **chưa có uniqueness constraint**, viết truy vấn tìm những giá trị `Person.personId` đang xuất hiện trên hơn một node.

**Đáp án:**

```cypher
MATCH (p:Person)
WHERE p.personId IS NOT NULL
WITH p.personId AS personId, count(p) AS occurrences
WHERE occurrences > 1
RETURN personId, occurrences
ORDER BY occurrences DESC;
```

Đây là truy vấn **phát hiện**, không tự gộp node hay sửa quan hệ.

## 15. Tổng kết

- **Khóa nghiệp vụ** là định danh bền vững được ứng dụng sử dụng để nhận biết một thực thể, **định danh bên ngoài** thuộc phạm vi của hệ thống nguồn, còn **định danh nội bộ** do Neo4j quản lý phục vụ nhu cầu kỹ thuật.
- `elementId()` (và `id()` ở những phiên bản còn hỗ trợ) **không phải khóa nghiệp vụ được bảo đảm ổn định lâu dài**; tránh dùng để tạo URL, khóa API hoặc dữ liệu trao đổi xuyên môi trường.
- Hai node có cùng property vẫn là **hai phần tử riêng** nếu được tạo riêng. Hãy dùng khóa đáng tin cậy và uniqueness constraint phù hợp để bảo vệ danh tính.
- Dùng `MERGE` theo **khóa ổn định**, `SET` cho property có thể đổi; thêm **tenant** hoặc **source** vào khóa ghép khi phạm vi duy nhất yêu cầu.
- Với nhiều nguồn dữ liệu, có thể lưu ID ngoài dưới dạng property hoặc node `ExternalIdentity`, nhưng chỉ nối về **cùng node chuẩn** sau khi xác minh thực thể.
- Cả node và relationship đại diện cho sự kiện đều có thể cần ID nghiệp vụ riêng để hỗ trợ nhập dữ liệu idempotent và truy vấn chính xác.
- Thiết kế định danh đúng giúp **tạo mối liên kết**, **truy vấn đường đi**, **tối ưu index**, **nhập dữ liệu** và **tích hợp Java Driver/Spring Data Neo4j** ổn định hơn.

Khi định danh được đặt đúng cấp và được kiểm soát bằng constraint cùng quy trình ghi, property graph có thể mở rộng qua nhiều ứng dụng và hệ thống nguồn mà vẫn duy trì được ý nghĩa **“đây là cùng một thực thể”** theo thời gian.
