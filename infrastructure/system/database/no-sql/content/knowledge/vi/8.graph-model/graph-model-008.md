# Chỉ mục, ràng buộc và lựa chọn điểm bắt đầu truy vấn trong mô hình đồ thị

## 1. Bài toán: vì sao có đồ thị rồi vẫn cần chỉ mục?

Giả sử một hệ thống phát hiện gian lận lưu các loại đối tượng:

- `Account`: tài khoản người dùng.
- `Device`: thiết bị đăng nhập.
- `Card`: phương thức thanh toán được mã hóa thành token.
- `IP`: địa chỉ mạng.
- `Transaction`: giao dịch.

Các mối quan hệ thường gặp là `USES_DEVICE`, `PAID_WITH`, `LOGGED_IN_FROM` và `MADE_TRANSACTION`.

```text
(Account A1) --USES_DEVICE--> (Device D9) <--USES_DEVICE-- (Account A2)
     |                                                    |
     +--PAID_WITH--> (Card C7) <--PAID_WITH---------------+
     |
     +--MADE_TRANSACTION--> (Transaction T100)
```

Một nhân viên kiểm soát rủi ro hỏi:

> “Bắt đầu từ tài khoản A1, hãy tìm các tài khoản khác dùng chung thiết bị hoặc cùng thẻ thanh toán.”

Truy vấn trên đồ thị tự nhiên ở chỗ ta đi qua các cạnh kết nối đối tượng. Nhưng nếu hệ thống có hàng chục triệu tài khoản, cơ sở dữ liệu vẫn phải tìm được **nút A1 đầu tiên**. Nếu không có đường tìm nút bắt đầu hiệu quả, truy vấn có thể phải quét một lượng lớn nút chỉ để xác định nơi bắt đầu duyệt.

Ba thành phần phối hợp với nhau:

1. **Chỉ mục (index)** hỗ trợ tìm nhanh những nút hoặc quan hệ thỏa điều kiện theo thuộc tính.
2. **Ràng buộc (constraint)** giúp dữ liệu tuân thủ các quy tắc như định danh duy nhất, trường bắt buộc hoặc loại giá trị được phép, tùy khả năng sản phẩm.
3. **Điểm bắt đầu truy vấn (starting point/anchor)** là nút hoặc tập nút ban đầu để thực hiện các bước duyệt quan hệ.

Vì thế, thiết kế truy vấn graph không chỉ là viết một đường đi đẹp mắt. Ta cần giúp engine **tìm đúng điểm bắt đầu, giới hạn số nhánh phải mở rộng, và giữ dữ liệu đủ đúng để đường đi có ý nghĩa**.

Các ví dụ mã trong bài dùng **Cypher và Neo4j** để minh họa. Mỗi graph database có khả năng chỉ mục, ràng buộc và ngôn ngữ truy vấn khác nhau; một số tính năng Neo4j phụ thuộc phiên bản hoặc edition. Những nguyên tắc về độ chọn lọc, tính đúng và chi phí duyệt có thể áp dụng rộng hơn.

## 2. Nút, quan hệ, nhãn và thuộc tính

Mô hình **property graph** thường gồm:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| Node (nút/đỉnh) | `(:Account {accountId: "A1"})` | Đại diện cho một thực thể |
| Label (nhãn) | `Account`, `Device` | Phân loại nút |
| Relationship (cạnh/quan hệ) | `[:USES_DEVICE]` | Kết nối hai nút, có hướng và loại |
| Property (thuộc tính) | `accountId`, `email`, `createdAt` | Lưu dữ liệu trên nút hoặc cạnh |
| Pattern (mẫu quan hệ) | `(a)-[:USES_DEVICE]->(d)` | Mô tả phần đồ thị cần tìm |

Một truy vấn Cypher đơn giản:

```cypher
MATCH (a:Account {accountId: $accountId})
RETURN a.accountId, a.status;
```

Ở đây, `Account` là label, `accountId` là thuộc tính, còn `$accountId` là tham số do ứng dụng cung cấp.

Truy vấn theo liên kết:

```cypher
MATCH (a:Account {accountId: $accountId})-[:USES_DEVICE]->(d:Device)
RETURN d.deviceId;
```

Truy vấn thứ hai gồm hai công việc khác nhau:

1. **Tìm nút `a`** bằng điều kiện `Account.accountId`.
2. **Mở rộng các cạnh `USES_DEVICE` từ `a`**, đọc các nút thiết bị nối với nó.

Chỉ mục có thể giúp bước đầu tiên. Bước thứ hai thường sử dụng cấu trúc lưu quan hệ kề của graph engine. Lập chỉ mục trên `Account.accountId` không tự động làm mọi đường duyệt dài trở nên rẻ.

## 3. Chỉ mục trong graph database dùng để làm gì?

Chỉ mục là cấu trúc phụ cho phép database định vị nhanh những phần tử có thuộc tính phù hợp, thay vì kiểm tra từng nút hoặc cạnh trong tập dữ liệu lớn.

Giả sử có 20 triệu nút `Account` và người dùng tra cứu `accountId = "A1"`.

**Không có chỉ mục phù hợp:**

```text
Tập 20 triệu Account
       |
       v
Xem nhiều nút để tìm accountId = "A1"
       |
       v
Bắt đầu duyệt các cạnh liên quan
```

**Có chỉ mục phù hợp:**

```text
Index(Account.accountId)
       |
       v
Tìm nút có accountId = "A1"
       |
       v
Bắt đầu duyệt các cạnh liên quan
```

Cách tổ chức nội bộ và độ phức tạp thực tế tùy engine, nhưng ý tưởng chung là **chuyển từ tìm rộng sang tìm có định hướng**.

### 3.1. Chỉ mục thuộc tính và khả năng duyệt cạnh là hai cơ chế khác nhau

Trong property graph, thường có hai kiểu truy cập nổi bật:

- **Tìm phần tử bằng giá trị thuộc tính**: `Account.accountId`, `Device.deviceId`, `Transaction.amount`.
- **Đi theo cạnh đã có**: từ tài khoản A1 đến các thiết bị, rồi đến tài khoản khác.

Chỉ mục thuộc tính chủ yếu giúp xác định phần tử dựa trên điều kiện thuộc tính. Khi đã có nút A1, graph engine có thể sử dụng cấu trúc quan hệ kề để duyệt các cạnh, mà không nhất thiết cần chỉ mục `Device.deviceId` cho mỗi bước duyệt.

Ví dụ:

```cypher
MATCH (a:Account {accountId: $accountId})-[:USES_DEVICE]->(d:Device)
RETURN d.deviceId;
```

Chỉ mục trên `Account.accountId` thường quan trọng cho điểm xuất phát. Chỉ mục trên `Device.deviceId` **không nhất thiết được dùng** nếu engine đang đến `d` bằng cách duyệt cạnh trực tiếp.

Ngược lại, nếu câu hỏi là “Tìm thiết bị D9 rồi xem mọi tài khoản dùng thiết bị đó”, chỉ mục trên `Device.deviceId` lại giúp tìm **điểm xuất phát mới**.

### 3.2. Chỉ mục có giá vận hành

Tạo index không miễn phí. Khi thêm, xóa hoặc thay đổi giá trị thuộc tính được lập chỉ mục, hệ quản trị phải cập nhật cả cấu trúc chỉ mục.

Các chi phí thường gặp:

- Dung lượng đĩa và bộ nhớ.
- Thời gian tạo index ban đầu trên dữ liệu lớn.
- Tăng công ghi hoặc thời gian cập nhật.
- Bảo trì và giám sát index.
- Khả năng trùng lặp index khi ràng buộc duy nhất đã tạo cấu trúc hỗ trợ.

Không nên tạo index cho mọi thuộc tính. Hãy chọn theo **truy vấn thực tế, độ chọn lọc, tần suất sử dụng và chi phí ghi**.

## 4. Các loại chỉ mục thường gặp trong Neo4j

Neo4j hỗ trợ nhiều loại index, có thể thay đổi theo phiên bản. Dưới đây là những dạng hữu ích khi học cách lựa chọn.

### 4.1. Range index: tra cứu và lọc theo giá trị

Range index thường được xem xét cho điều kiện bằng nhau, so sánh hoặc khoảng giá trị trên thuộc tính phù hợp.

Ví dụ:

```cypher
CREATE RANGE INDEX account_created_at_idx IF NOT EXISTS
FOR (a:Account)
ON (a.createdAt);
```

Truy vấn:

```cypher
MATCH (a:Account)
WHERE a.createdAt >= datetime($fromTime)
  AND a.createdAt < datetime($toTime)
RETURN a.accountId, a.createdAt
ORDER BY a.createdAt DESC
LIMIT 50;
```

Nếu tham số là chuỗi thời gian ISO 8601 hợp lệ và `createdAt` lưu kiểu datetime tương thích, điều kiện có thể tận dụng chỉ mục phù hợp. Hãy kiểm tra kế hoạch thực thi, vì việc engine dùng index còn phụ thuộc số hàng phù hợp, hình dạng truy vấn và chi phí ước lượng.

Nếu `createdAt` được lưu lúc là chuỗi, lúc là datetime hoặc có giá trị thiếu, ý nghĩa so sánh sẽ kém ổn định. **Kiểu dữ liệu và ràng buộc schema** ảnh hưởng trực tiếp đến kết quả truy vấn.

### 4.2. Index ghép theo nhiều thuộc tính

Trong hệ nhiều tenant, một tài khoản có thể được xác định bởi cặp `(tenantId, accountId)`.

```cypher
CREATE RANGE INDEX tenant_account_idx IF NOT EXISTS
FOR (a:Account)
ON (a.tenantId, a.accountId);
```

Truy vấn:

```cypher
MATCH (a:Account)
WHERE a.tenantId = $tenantId
  AND a.accountId = $accountId
RETURN a;
```

Index ghép giúp tối ưu những mẫu truy vấn tương ứng với các thuộc tính được khai báo. Tuy nhiên, **điều kiện nào dùng được chỉ mục ghép hiệu quả** phụ thuộc quy tắc prefix, toán tử và phiên bản engine. Truy vấn chỉ có `accountId` nhưng thiếu `tenantId` có thể không khai thác index ghép như mong đợi.

Cần quan sát plan và truy vấn thực tế. Nếu thường xuyên tìm chỉ theo `accountId` trên toàn hệ thống, cân nhắc đường truy cập khác hoặc quyết định lại mô hình định danh.

### 4.3. Text index và full-text index

Text index và full-text index giải quyết các nhu cầu văn bản khác nhau.

**Text index** được dùng để hỗ trợ một số phép lọc chuỗi, chẳng hạn điều kiện bắt đầu bằng tiền tố hoặc kết thúc bằng hậu tố, tùy khả năng của engine và cấu trúc truy vấn.

```cypher
CREATE TEXT INDEX account_display_name_idx IF NOT EXISTS
FOR (a:Account)
ON (a.displayName);
```

Một truy vấn ví dụ:

```cypher
MATCH (a:Account)
WHERE a.displayName STARTS WITH $prefix
RETURN a.accountId, a.displayName
LIMIT 20;
```

**Full-text index** xử lý tìm kiếm nội dung theo từ ngữ, phân tích từ và chấm điểm liên quan. Ví dụ:

```cypher
CREATE FULLTEXT INDEX account_search_idx IF NOT EXISTS
FOR (a:Account)
ON EACH [a.displayName, a.biography];
```

Truy vấn full-text theo thủ tục Neo4j:

```cypher
CALL db.index.fulltext.queryNodes("account_search_idx", $queryText)
YIELD node, score
RETURN node.accountId AS accountId, score
ORDER BY score DESC
LIMIT 20;
```

Một số môi trường/cấu hình có thể cho phép full-text index cập nhật bất đồng bộ, nên yêu cầu về độ mới của dữ liệu phải được xác định rõ. Full-text index không đồng nghĩa với ràng buộc duy nhất và không dùng thay chỉ mục tra cứu ID chính xác.

### 4.4. Point index cho vị trí địa lý

Nếu nút `Store` có thuộc tính `location` kiểu point, chỉ mục point có thể hỗ trợ truy vấn không gian tương ứng.

```cypher
CREATE POINT INDEX store_location_idx IF NOT EXISTS
FOR (s:Store)
ON (s.location);
```

Ví dụ lưu vị trí:

```cypher
CREATE (:Store {
  storeId: "S1",
  location: point({latitude: 10.7769, longitude: 106.7009})
});
```

Truy vấn khoảng cách địa lý là một nhu cầu khác với duyệt quan hệ giữa cửa hàng và khách hàng. Nếu phải tìm cửa hàng gần vị trí X rồi mới duyệt các mối quan hệ như `DELIVERS_TO` hoặc `PARTNERS_WITH`, index không gian có thể giúp **chọn tập cửa hàng bắt đầu**.

Cú pháp và khả năng sử dụng index cho từng phép tính không gian cần kiểm tra trong phiên bản sản phẩm thực tế.

### 4.5. Index trên thuộc tính quan hệ và các loại index khác

Một số phiên bản Neo4j hỗ trợ index trên **relationship properties**, chẳng hạn `firstSeenAt` hoặc `amount` của cạnh `TRANSFERRED_TO`. Điều này hữu ích khi điểm khởi đầu truy vấn là **quan hệ được lọc theo thuộc tính**, thay vì một nút đã biết.

Ví dụ mô hình dữ liệu:

```text
(Account A)-[:TRANSFERRED_TO {amount: 5000, at: ...}]->(Account B)
```

Nhưng nếu truy vấn bắt đầu bằng tài khoản A rồi chỉ duyệt vài giao dịch nối với A, engine có thể đọc danh sách cạnh kề và lọc trực tiếp, thay vì dùng index toàn cục cho thuộc tính cạnh.

Những khả năng chuyên dụng khác như **vector index** phù hợp với tìm kiếm tương đồng embedding. Chúng có thể giúp lấy những nút “gần nhau về ngữ nghĩa” làm ứng viên để tiếp tục duyệt đồ thị, nhưng không tự động tăng tốc một đường đi theo cạnh.

**Nguyên tắc:** loại index phải khớp **toán tử truy vấn và thuộc tính được dùng để xác định điểm bắt đầu**, không chỉ khớp tên trường.

## 5. Ràng buộc: bảo đảm đồ thị biểu diễn đúng dữ liệu

Chỉ mục hỗ trợ hiệu năng. **Constraint** nhằm bảo đảm các điều kiện dữ liệu được thực thi bởi database.

Trong graph, dữ liệu sai có thể gây hậu quả rõ rệt:

- Hai nút `Account` cùng mang `accountId = "A1"` khiến truy vấn bắt đầu ở hai tài khoản.
- Một nút `Device` thiếu `deviceId` làm hệ thống không thể liên kết theo ID thiết bị chuẩn.
- Một `tenantId` sai hoặc thiếu có thể dẫn đến truy vấn sai phạm vi tenant.
- Một quan hệ `USES_DEVICE` nhầm đầu mút khiến đồ thị biểu diễn sai sự thật.

Ràng buộc giúp giảm một số lỗi này ở mức dữ liệu lưu trữ. Tuy nhiên, không phải mọi quy tắc nghiệp vụ đều được thể hiện bằng constraint có sẵn.

### 5.1. Ràng buộc duy nhất (uniqueness constraint)

Giả sử tài khoản phải có `accountId` duy nhất:

```cypher
CREATE CONSTRAINT account_id_unique IF NOT EXISTS
FOR (a:Account)
REQUIRE a.accountId IS UNIQUE;
```

Ràng buộc này ngăn hai nút có nhãn `Account` cùng chứa cùng một giá trị `accountId`, theo ngữ nghĩa và phạm vi của constraint Neo4j.

Ví dụ:

```cypher
CREATE (:Account {accountId: "A1", status: "ACTIVE"});
```

Nếu lại tạo một nút khác với `accountId = "A1"`, thao tác sẽ bị từ chối do vi phạm ràng buộc.

**Điểm cần phân biệt:** ràng buộc unique trên một thuộc tính thường **không đồng nghĩa thuộc tính đó bắt buộc có mặt**. Một nút thiếu `accountId` không nhất thiết vi phạm uniqueness. Nếu ID phải luôn tồn tại, cần thêm cơ chế tồn tại thuộc tính hoặc node key phù hợp.

Trong Neo4j, tạo uniqueness constraint cũng tạo chỉ mục hỗ trợ tra cứu theo thuộc tính tương ứng; cần kiểm tra `SHOW INDEXES` để tránh tạo index tương đương không cần thiết.

### 5.2. Ràng buộc tồn tại thuộc tính

Nếu mọi nút tài khoản đều phải mang `accountId`:

```cypher
CREATE CONSTRAINT account_id_exists IF NOT EXISTS
FOR (a:Account)
REQUIRE a.accountId IS NOT NULL;
```

Loại ràng buộc tồn tại thuộc tính trong Neo4j có thể phụ thuộc **edition và phiên bản**. Trong môi trường không hỗ trợ, ứng dụng cần cơ chế validation hoặc lựa chọn triển khai khác; không nên giả định câu lệnh chạy được trên mọi bản Neo4j.

Tồn tại thuộc tính không đảm bảo giá trị thỏa mọi quy tắc nghiệp vụ. Chẳng hạn chuỗi rỗng `""` có thể vẫn là một giá trị tồn tại; cần validation riêng nếu cấm ID rỗng.

### 5.3. Node key và định danh ghép

Trong một số hệ thống nhiều tenant, ID chỉ duy nhất **bên trong tenant**. Khi đó, cặp `(tenantId, accountId)` mới là định danh nghiệp vụ.

Neo4j có **node key constraint** ở những edition/phiên bản hỗ trợ:

```cypher
CREATE CONSTRAINT tenant_account_key IF NOT EXISTS
FOR (a:TenantAccount)
REQUIRE (a.tenantId, a.accountId) IS NODE KEY;
```

Node key kết hợp ý tưởng **các thuộc tính khóa phải tồn tại** và **tổ hợp các giá trị phải duy nhất**. Ví dụ dùng nhãn `TenantAccount` riêng để minh họa một lựa chọn schema; không nên áp dụng đồng thời nhiều ràng buộc xung đột hoặc dư thừa vào môi trường có dữ liệu mà chưa đánh giá tác động.

Nếu sản phẩm không hỗ trợ node key, có thể cần kết hợp ràng buộc duy nhất/tồn tại khi được phép, hoặc quy ước định danh duy nhất toàn cục từ ứng dụng.

### 5.4. Ràng buộc kiểu dữ liệu

Một số phiên bản/edition Neo4j hỗ trợ property type constraint, giúp đảm bảo thuộc tính có kiểu được chỉ định. Đây là khả năng hữu ích khi `amount` phải là kiểu số, `createdAt` phải là kiểu thời gian hoặc `accountId` phải là chuỗi.

Tuy vậy, quy tắc kiểu **không tự bảo đảm**:

- `amount > 0`;
- `status` nằm trong danh sách trạng thái hợp lệ;
- Một account phải có chính xác một quan hệ `BELONGS_TO`;
- Quan hệ `TRANSFERRED_TO` chỉ được tạo nếu nghiệp vụ cho phép;
- `riskScore` thay đổi theo quy tắc đã được phê duyệt.

Những quy tắc đó có thể cần thêm lớp ứng dụng, mô hình giao dịch hoặc giải pháp constraint chuyên dụng của sản phẩm.

### 5.5. Graph constraint khác khóa ngoại SQL như thế nào?

Trong database quan hệ, khóa ngoại có thể bảo đảm một cột tham chiếu đến một hàng tồn tại. Trong property graph, một cạnh trực tiếp kết nối **hai nút đang tồn tại**. Cơ chế lưu graph thường không tạo một quan hệ tới nút không có thật theo cách một cột `customer_id` có thể chứa một giá trị không tham chiếu hợp lệ nếu thiếu foreign key.

Nhưng điều đó **không tự bảo đảm mọi quy tắc quan hệ nghiệp vụ**. Ví dụ:

- Một tài khoản có thể thiếu quan hệ `BELONGS_TO_TENANT`.
- Một tài khoản có thể vô tình nối với hai tenant.
- Một nút `Transaction` có thể thiếu `MADE_BY`.
- Một thiết bị có thể liên kết nhầm tài khoản.

Phải phân biệt **toàn vẹn tham chiếu ở tầng cấu trúc graph** và **ràng buộc nghiệp vụ về loại, số lượng và ngữ nghĩa cạnh**.

## 6. Định nghĩa một schema mẫu cho hệ phát hiện gian lận

Một mô hình ban đầu:

```text
(:Account {accountId, status, createdAt})
(:Device  {deviceId, riskFlag})
(:Card    {token})
(:IP      {address})

(:Account)-[:USES_DEVICE {firstSeenAt}]->(:Device)
(:Account)-[:PAID_WITH]->(:Card)
(:Account)-[:LOGGED_IN_FROM]->(:IP)
```

Ta muốn truy vấn chính xác theo ID của từng loại nút, nên thiết lập ràng buộc định danh duy nhất:

```cypher
CREATE CONSTRAINT account_id_unique IF NOT EXISTS
FOR (a:Account)
REQUIRE a.accountId IS UNIQUE;

CREATE CONSTRAINT device_id_unique IF NOT EXISTS
FOR (d:Device)
REQUIRE d.deviceId IS UNIQUE;

CREATE CONSTRAINT card_token_unique IF NOT EXISTS
FOR (c:Card)
REQUIRE c.token IS UNIQUE;

CREATE CONSTRAINT ip_address_unique IF NOT EXISTS
FOR (i:IP)
REQUIRE i.address IS UNIQUE;
```

Tùy nhu cầu thực tế, có thể thêm index trên `Account.createdAt` hoặc `Account.status` cho những truy vấn thường bắt đầu từ tập tài khoản theo thời gian/trạng thái. Không bắt buộc index `riskFlag` nếu chỉ có hai giá trị và phần lớn truy vấn không bắt đầu từ tất cả thiết bị có cờ đó.

### 6.1. Tạo nút bằng MERGE

Sau khi có uniqueness constraint, việc nhập một tài khoản theo ID có thể dùng:

```cypher
MERGE (a:Account {accountId: $accountId})
ON CREATE SET a.createdAt = datetime(),
              a.status = "ACTIVE"
RETURN a;
```

`MERGE` tìm hoặc tạo mẫu khi chưa có, nhưng **không thay thế** ràng buộc duy nhất trong mọi kịch bản ghi đồng thời. Constraint giúp database phát hiện/xử lý xung đột tính duy nhất theo đúng bảo đảm của hệ.

Khi đồng thời có nhiều writer, ứng dụng phải chuẩn bị xử lý lỗi vi phạm constraint và có chính sách retry an toàn.

### 6.2. Tạo quan hệ khi hai nút đã tồn tại

```cypher
MATCH (a:Account {accountId: $accountId})
MATCH (d:Device {deviceId: $deviceId})
MERGE (a)-[r:USES_DEVICE]->(d)
ON CREATE SET r.firstSeenAt = datetime()
RETURN a.accountId, d.deviceId, r.firstSeenAt;
```

Hai lệnh `MATCH` giúp định vị các nút dựa trên ID, sau đó `MERGE` quan hệ giữa hai nút đã tìm.

Nếu không tồn tại tài khoản hoặc thiết bị được tham chiếu, các `MATCH` sẽ không tạo ra dòng kết quả để thực hiện `MERGE` quan hệ. Ứng dụng phải quyết định **tự tạo node**, báo lỗi hay đưa sự kiện vào hàng chờ xử lý.

Tránh viết `MERGE` trên một mẫu lớn có nhiều thuộc tính biến đổi mà không hiểu rõ hành vi: nếu **toàn mẫu** không khớp, engine có thể tìm cách tạo các thành phần mới không mong đợi. Thường dễ kiểm soát hơn khi xác định các node bằng khóa duy nhất rồi thao tác quan hệ rõ ràng.

## 7. “Điểm bắt đầu truy vấn” là gì?

**Điểm bắt đầu (anchor)** là nút hoặc tập nút được định vị đầu tiên để từ đó duyệt các cạnh và mở rộng kết quả.

Xét hai câu hỏi:

**Câu A:** “Những tài khoản nào dùng chung thiết bị với A1?”

**Câu B:** “Tất cả cặp tài khoản nào dùng chung thiết bị trong toàn bộ hệ thống?”

Câu A có anchor rõ ràng là **A1**. Nếu `Account.accountId` được đánh index hoặc bảo đảm unique, engine có thể tìm một nút rồi duyệt các cạnh liên quan.

Câu B không có một anchor chọn lọc; engine có thể phải khảo sát nhiều thiết bị, nhiều tài khoản và tạo lượng lớn cặp kết quả. Đây là bài toán nặng hơn đáng kể dù cùng dùng quan hệ `USES_DEVICE`.

### 7.1. Độ chọn lọc của anchor

Một điều kiện **có độ chọn lọc cao** loại bỏ gần hết các phần tử và chỉ giữ ít ứng viên. Ví dụ:

| Điều kiện tìm nút | Số nút khớp minh họa | Độ chọn lọc |
|---|---:|---|
| `accountId = "A1"` | 1 | Rất cao |
| `email = "a@example.com"` | 1–vài | Cao, nếu dữ liệu được quản lý |
| `tenantId = "T42"` | 10.000 | Tùy quy mô tenant |
| `status = "ACTIVE"` | 8.000.000 | Thấp nếu hầu hết đang hoạt động |
| `riskFlag = true` | 300.000 | Trung bình/thấp tùy tập dữ liệu |

Những số liệu chỉ minh họa; một trường tên “ID” cũng chưa chắc duy nhất nếu dữ liệu không có ràng buộc.

Nếu truy vấn có nhiều điểm bắt đầu tiềm năng, engine thường dựa vào thống kê và bộ tối ưu để quyết định kế hoạch. Người viết nên cung cấp **nhãn và điều kiện chính xác**, sau đó kiểm tra kế hoạch thực thi thay vì đoán chỉ từ thứ tự chữ trong câu Cypher.

### 7.2. Anchor tốt chưa đủ nếu nút có bậc rất cao

**Degree (bậc nút)** là số cạnh liên quan đến nút; có thể xét theo hướng và loại quan hệ.

Ví dụ:

- A1 đã dùng 3 thiết bị;
- mỗi thiết bị có 2–10 tài khoản khác từng dùng;
- truy vấn mở rộng hai bước có thể tạo vài chục kết quả trước khi khử trùng lặp.

Trường hợp khác:

- A1 từng đăng nhập qua một địa chỉ IP công cộng;
- IP đó được hàng triệu người dùng chung;
- duyệt `Account -> IP -> Account` có thể mở rộng ra hàng triệu ứng viên.

**Một anchor duy nhất nhưng nối tới supernode** vẫn có thể tạo truy vấn rất chậm. Cần xem cả **độ chọn lọc của điểm bắt đầu** và **mức phân nhánh trên đường duyệt**.

### 7.3. Điểm bắt đầu còn có thể là cạnh

Trong một số truy vấn, điều kiện chọn lọc nhất nằm trên **thuộc tính quan hệ**, chẳng hạn giao dịch có `transactionId` hoặc một cạnh chuyển tiền có thời điểm trong khoảng rất hẹp. Khi engine hỗ trợ index thích hợp trên quan hệ, nó có thể bắt đầu từ tập cạnh thỏa điều kiện rồi tìm hai đầu mút.

Tuy nhiên, việc truy vấn theo cạnh hiệu quả đến đâu phụ thuộc loại index, storage engine và toán tử cụ thể. Nếu chỉ cần đọc cạnh nối với một account đã biết, bắt đầu từ account vẫn có thể hiệu quả hơn.

## 8. Truy vấn có anchor rõ ràng: đi từ một tài khoản đến tài khoản liên quan

### 8.1. Bước một: định vị tài khoản

```cypher
MATCH (a:Account {accountId: $accountId})
RETURN a;
```

Với ràng buộc unique, engine có thể sử dụng index để tìm nút theo `accountId`. Nếu không tồn tại A1, kết quả rỗng; ứng dụng có thể trả trạng thái phù hợp.

### 8.2. Bước hai: mở rộng qua thiết bị

```cypher
MATCH (a:Account {accountId: $accountId})
MATCH (a)-[:USES_DEVICE]->(d:Device)
RETURN d.deviceId;
```

Nhiều khả năng engine định vị A1 rồi duyệt các cạnh `USES_DEVICE` đi ra. Nếu A1 chỉ có vài thiết bị, truy vấn này thường có đường duyệt ngắn.

### 8.3. Bước ba: tìm các tài khoản dùng chung thiết bị

```cypher
MATCH (a:Account {accountId: $accountId})
MATCH (a)-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(other:Account)
WHERE other.accountId <> a.accountId
RETURN DISTINCT other.accountId AS relatedAccountId
LIMIT 50;
```

Các điểm đáng chú ý:

- `a` là anchor được chọn theo `accountId`.
- Hai cạnh có loại và hướng rõ ràng.
- `other` đại diện tài khoản cùng sử dụng một thiết bị.
- `DISTINCT` loại các ID trùng nếu hai tài khoản cùng chia sẻ nhiều thiết bị.
- `LIMIT 50` giới hạn kết quả trả về; **không bảo đảm** database chỉ phải duyệt 50 cặp trước khi có kết quả cuối, nhất là khi cần khử trùng lặp hoặc sắp xếp.

Nếu một thiết bị rất phổ biến, bước từ `d` sang `other` có thể vẫn tốn kém. Nên xem phân phối degree của Device, mục tiêu nghiệp vụ và giới hạn fan-out.

### 8.4. Tìm từ thiết bị D9 thay vì tài khoản A1

Nếu yêu cầu là “Ai đã dùng D9?”:

```cypher
MATCH (d:Device {deviceId: $deviceId})
MATCH (d)<-[:USES_DEVICE]-(a:Account)
RETURN a.accountId
LIMIT 100;
```

Lúc này anchor tốt là **Device D9**, không phải Account. Nếu cần một tài khoản cụ thể và một thiết bị cụ thể, engine có thể cân nhắc bắt đầu từ điều kiện chọn lọc hơn trong hai điều kiện.

**Điểm cốt lõi:** cùng một loại cạnh nhưng câu hỏi khác nhau dẫn đến **anchor và index quan trọng khác nhau**.

## 9. Khi có nhiều điểm bắt đầu tiềm năng

Xét truy vấn:

> “Trong các tài khoản có status S, tìm những tài khoản dùng thiết bị D9.”

Có thể xuất phát từ:

- Tất cả tài khoản có `status = S` rồi đi tới thiết bị D9;
- Thiết bị D9 rồi duyệt tới các tài khoản và kiểm tra trạng thái.

Nếu `status = "ACTIVE"` khớp hàng triệu tài khoản, trong khi D9 chỉ có 4 tài khoản dùng, thường hợp lý khi bắt đầu từ thiết bị. Nếu D9 là thiết bị dùng chung bởi hàng triệu tài khoản nhưng status S chỉ có vài tài khoản, kế hoạch có thể khác.

Ví dụ Cypher:

```cypher
MATCH (d:Device {deviceId: $deviceId})<-[:USES_DEVICE]-(a:Account)
WHERE a.status = $status
RETURN a.accountId;
```

Việc đặt `d` trước trong cú pháp **không đảm bảo** engine bắt đầu từ `d` trong mọi trường hợp. Bộ tối ưu Cypher có thể thay đổi thứ tự thực thi theo thống kê, index và plan. Quan sát `EXPLAIN` hoặc `PROFILE` để xác nhận.

### 9.1. Composite index và môi trường nhiều tenant

Giả sử một app SaaS có hàng triệu tài khoản và `accountId` chỉ duy nhất trong tenant. Để tìm đúng tài khoản, truy vấn cần cả hai điều kiện:

```cypher
MATCH (a:Account)
WHERE a.tenantId = $tenantId
  AND a.accountId = $accountId
RETURN a;
```

Một index/constraint ghép phù hợp có thể giúp anchor mang tính duy nhất.

Nhưng **lọc tenant ở điểm đầu chưa tự đảm bảo mọi nút đi qua trên đường duyệt thuộc cùng tenant**. Nếu hệ thống cho phép các quan hệ liên tenant hoặc dữ liệu bị nhập sai, bước duyệt có thể đến tài khoản tenant khác. Ứng dụng phải xác định chính sách phân tách tenant ở cả schema, ghi dữ liệu, truy vấn và quyền truy cập.

Ví dụ điều kiện kiểm soát phạm vi ở các nút kết quả:

```cypher
MATCH (a:Account {tenantId: $tenantId, accountId: $accountId})
MATCH (a)-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(other:Account)
WHERE other.tenantId = $tenantId
RETURN DISTINCT other.accountId;
```

Đây là minh họa giới hạn theo tenant ở tài khoản kết quả; **chưa đủ** thay cho mô hình bảo mật đầy đủ nếu Device hoặc các loại nút trung gian có chính sách phân tách riêng.

## 10. Mở rộng cạnh: đường đi ngắn và đường đi dài khác nhau

### 10.1. Giới hạn loại và hướng quan hệ

So sánh:

```cypher
// Mẫu rộng: có thể đi qua nhiều loại quan hệ và cả hai hướng
MATCH (a:Account {accountId: $accountId})--(n)
RETURN n
LIMIT 50;
```

với:

```cypher
// Mẫu hẹp: chỉ lấy thiết bị mà tài khoản sử dụng
MATCH (a:Account {accountId: $accountId})-[:USES_DEVICE]->(d:Device)
RETURN d.deviceId
LIMIT 50;
```

Mẫu thứ hai cung cấp nhiều thông tin hơn về **loại cạnh, hướng và label đích**. Điều này giúp giới hạn các đường đi không liên quan và thể hiện đúng nghiệp vụ.

Không nên dùng mẫu quan hệ không có loại/hướng nếu bài toán vốn có quan hệ được định nghĩa rõ.

### 10.2. Truy vấn nhiều bước và bùng nổ tổ hợp

Ví dụ tìm tài khoản có thể liên quan qua tối đa ba quan hệ `TRANSFERRED_TO`:

```cypher
MATCH (a:Account {accountId: $accountId})
MATCH (a)-[:TRANSFERRED_TO*1..3]->(other:Account)
WHERE other.accountId <> a.accountId
RETURN DISTINCT other.accountId
LIMIT 100;
```

Cú pháp đường đi biến độ dài cụ thể thay đổi theo phiên bản Cypher, nhưng ý nghĩa ở đây là **duyệt từ một đến ba cạnh**.

Giả sử từ mỗi tài khoản trung bình có 20 cạnh phù hợp và chưa loại trùng:

```text
Mức 1:           20 ứng viên
Mức 2:       20 × 20 = 400 ứng viên
Mức 3:  20 × 20 × 20 = 8.000 ứng viên
```

Kết quả sau `DISTINCT` có thể chỉ còn vài trăm tài khoản, nhưng engine vẫn có thể phải xử lý rất nhiều đường đi trung gian.

Trong dữ liệu thật, degree phân phối không đều; một vài supernode có thể làm số đường đi tăng đột biến. Giới hạn độ sâu giúp giảm phạm vi nhưng không thay thế kiểm soát bùng nổ.

### 10.3. Đường đi ngắn nhất không luôn rẻ

Một câu hỏi “đường đi ngắn nhất từ A đến B” có thể được tối ưu bằng thuật toán chuyên biệt khi đã biết hai đầu mút. Nhưng chi phí còn phụ thuộc số cạnh, tập loại quan hệ cho phép, ràng buộc đường đi và cách engine tìm kiếm.

Nếu cả A và B đều có ID duy nhất, hãy mô tả rõ hai anchor. Nếu chỉ biết “mọi cặp tài khoản có đường đi dưới K bước”, phạm vi bài toán lớn hơn nhiều.

Tránh suy luận rằng mọi truy vấn `shortestPath` hoặc mọi truy vấn dùng thuật toán graph đều hiệu quả chỉ vì engine chuyên về đồ thị.

### 10.4. Supernode và lựa chọn mô hình

Một số nút tự nhiên có bậc rất cao:

- Địa chỉ IP của mạng công cộng.
- Thiết bị được dùng ở cửa hàng hoặc kiosk dùng chung.
- Tài khoản trung gian của hệ thống thanh toán.
- Tác giả nổi tiếng hoặc nội dung được hàng triệu người theo dõi.

Khi đánh giá gian lận, chia sẻ một IP công cộng không có ý nghĩa giống chia sẻ thiết bị cá nhân. Có thể cần mô hình phân loại rủi ro, giới hạn độ sâu, bỏ qua một số loại supernode hoặc xử lý theo thuật toán chuyên biệt. Những quyết định này phải xuất phát từ **ngữ nghĩa nghiệp vụ**, không đơn thuần từ thủ thuật tối ưu.

## 11. Tránh các mẫu truy vấn làm tăng chi phí không cần thiết

### 11.1. Truy vấn không có anchor

```cypher
MATCH (a:Account)-[:USES_DEVICE]->(d:Device)
      <-[:USES_DEVICE]-(b:Account)
WHERE a.accountId <> b.accountId
RETURN a.accountId, b.accountId
LIMIT 100;
```

Truy vấn tìm các cặp tài khoản cùng thiết bị trên toàn graph. Nó có thể phải mở rộng từ rất nhiều tài khoản hoặc thiết bị; không phù hợp để chạy thường xuyên như một request đơn giản nếu dữ liệu lớn.

Nếu mục tiêu chỉ là tìm trường hợp liên quan đến một tài khoản, thêm `accountId` vào truy vấn và bảo đảm có index phù hợp để giảm phạm vi.

Nếu cần báo cáo toàn hệ thống, nên cân nhắc:

- Chạy tác vụ nền theo lô.
- Phân vùng theo tập thiết bị hoặc khoảng thời gian.
- Lưu kết quả phân tích đã tính sẵn.
- Dùng graph analytics hoặc công cụ phù hợp với khối lượng xử lý.
- Đặt giới hạn thời gian và tài nguyên.

### 11.2. Cartesian product không cần thiết

Hai mẫu không có quan hệ nối nhau:

```cypher
MATCH (a:Account), (d:Device)
WHERE a.status = "ACTIVE"
  AND d.riskFlag = true
RETURN a.accountId, d.deviceId;
```

có thể tạo ra **tích Descartes** giữa hai tập nút. Nếu có 10.000 tài khoản và 5.000 thiết bị, số cặp lý thuyết là 50 triệu, dù bài toán thật không cần mọi cặp.

Nếu muốn tìm **thiết bị rủi ro được tài khoản đang hoạt động sử dụng**, phải mô tả quan hệ:

```cypher
MATCH (a:Account)-[:USES_DEVICE]->(d:Device)
WHERE a.status = "ACTIVE"
  AND d.riskFlag = true
RETURN DISTINCT a.accountId, d.deviceId;
```

Truy vấn này vẫn có thể rộng nếu thiếu anchor, nhưng ngữ nghĩa đúng là các cặp có quan hệ, thay vì mọi tổ hợp.

### 11.3. Bỏ qua kiểu dữ liệu và phép biến đổi thuộc tính

Nếu `Account.createdAt` lưu dưới dạng datetime, nên truyền tham số thời gian tương thích. Những biểu thức biến đổi một thuộc tính trong điều kiện lọc có thể khiến engine khó tận dụng index hơn, tùy planner và phiên bản.

Ví dụ, thiết kế dễ đọc hơn thường là:

```cypher
MATCH (a:Account)
WHERE a.createdAt >= $fromDateTime
  AND a.createdAt < $toDateTime
RETURN a.accountId;
```

với `$fromDateTime` và `$toDateTime` đã được driver bind thành kiểu datetime phù hợp.

Nếu database chứa kiểu string lẫn datetime, cần xử lý schema/migration; thêm index không tự sửa các giá trị đã lưu sai kiểu.

### 11.4. Sử dụng DISTINCT và ORDER BY thiếu chủ đích

`DISTINCT` loại trùng kết quả nhưng có thể yêu cầu lưu trạng thái trung gian; `ORDER BY` thường có chi phí sắp xếp nếu engine không thể sử dụng thứ tự từ index. Khi graph fan-out quá lớn, đặt `LIMIT` cuối truy vấn chưa chắc làm giảm số phần tử phải mở rộng trước đó.

Cần xác định rõ có cần:

- Mọi đường đi hay chỉ danh sách các nút đích không trùng?
- Xếp hạng theo điểm rủi ro hay chỉ lấy một số kết quả?
- Kết quả sắp xếp ổn định để phân trang?
- Tính số lượng đúng tuyệt đối hay chấp nhận một tập ứng viên?

Đổi cách sắp xếp hoặc loại trùng có thể đổi **ngữ nghĩa kết quả**, vì vậy tối ưu phải bắt đầu từ yêu cầu nghiệp vụ.

## 12. Đọc kế hoạch truy vấn bằng EXPLAIN và PROFILE

Neo4j cho phép xem kế hoạch truy vấn bằng `EXPLAIN` và đo một lần thực thi bằng `PROFILE`.

### 12.1. EXPLAIN: xem kế hoạch dự kiến

```cypher
EXPLAIN
MATCH (a:Account {accountId: $accountId})-[:USES_DEVICE]->(d:Device)
RETURN d.deviceId;
```

`EXPLAIN` hiển thị plan mà không thực thi truy vấn như thông thường. Với môi trường và thống kê phù hợp, ta có thể quan sát các bước đại loại:

```text
ProduceResults
     |
Projection
     |
Expand(...)
     |
NodeUniqueIndexSeek / NodeIndexSeek
```

Tên operator và cách hiển thị cụ thể phụ thuộc phiên bản Neo4j, loại index và cấu trúc câu truy vấn.

Điểm cần nhận biết là liệu engine có sử dụng **index seek** cho `Account.accountId`, rồi **expand** sang `Device`, hay đang thực hiện **label scan** trên lượng nút lớn.

### 12.2. PROFILE: xem điều gì xảy ra khi thực thi

```cypher
PROFILE
MATCH (a:Account {accountId: $accountId})-[:USES_DEVICE]->(d:Device)
RETURN d.deviceId;
```

`PROFILE` chạy truy vấn và thu thập số liệu thực thi, có thể bao gồm số dòng qua từng operator, DB hits, bộ nhớ và các metric tùy phiên bản.

Cần cẩn trọng: nếu `PROFILE` được dùng với truy vấn `CREATE`, `MERGE`, `DELETE` hay `SET`, **truy vấn ghi vẫn được thực thi**. Nên dùng môi trường kiểm thử và hiểu tác động trước khi profile câu lệnh thay đổi dữ liệu.

### 12.3. Những operator thường gặp

| Operator/nhóm thao tác | Thường có ý nghĩa |
|---|---|
| NodeByLabelScan | Duyệt các nút có label, có thể tốn kém khi label rất lớn |
| AllNodesScan | Duyệt toàn bộ nút |
| NodeIndexSeek | Dùng chỉ mục tìm các nút theo điều kiện |
| NodeUniqueIndexSeek | Tìm nút qua chỉ mục hỗ trợ tính duy nhất |
| Expand | Duyệt từ nút qua các cạnh phù hợp |
| Filter | Kiểm tra điều kiện |
| Sort | Sắp xếp các dòng trung gian |
| Distinct / Aggregation | Loại trùng hoặc tính toán theo nhóm |
| CartesianProduct | Ghép mọi cặp từ hai tập độc lập |
| Apply / Subquery | Thực hiện biểu thức phụ hoặc phần kế hoạch phụ |

Không phải mọi `NodeByLabelScan` đều là lỗi. Nếu label nhỏ hoặc truy vấn muốn đọc tất cả nút thuộc nhãn đó, scan có thể là lựa chọn hợp lý. Tương tự, không phải mọi `NodeIndexSeek` đều đảm bảo truy vấn cuối nhanh; bước expand sau đó có thể chiếm phần lớn chi phí.

### 12.4. Điều cần đọc trên PROFILE

1. **Số dòng vào/ra mỗi bước:** dòng tăng vọt ở `Expand` hoặc `CartesianProduct`?
2. **DB hits/reads:** bước nào truy cập dữ liệu nhiều?
3. **Điểm đầu tiên:** có seek theo ID duy nhất hay scan tập lớn?
4. **Kích thước kết quả trung gian:** có nhiều dòng bị loại sau khi đã duyệt?
5. **Sort/Distinct/Aggregation:** có xử lý hàng triệu dòng trước `LIMIT`?
6. **Chi phí thực tế:** p95/p99, thời gian phản hồi và tài nguyên dưới tải đại diện.

Nên so sánh plan trước/sau khi thay đổi index hoặc cách viết truy vấn trên dữ liệu có kích thước và phân phối gần thực tế.

## 13. Sử dụng nhãn, tham số và index một cách chủ đích

### 13.1. Luôn ghi rõ label khi biết loại nút

So sánh:

```cypher
MATCH (n {accountId: $accountId})
RETURN n;
```

với:

```cypher
MATCH (n:Account {accountId: $accountId})
RETURN n;
```

Khi biết thực thể phải là `Account`, thêm label giúp thể hiện đúng ngữ nghĩa và có thể mở đường cho index theo label/thuộc tính tương ứng.

Nếu nhiều loại nút đều có trường `accountId`, câu truy vấn không label còn có nguy cơ trả những thực thể không phải tài khoản.

### 13.2. Dùng tham số thay vì nối chuỗi Cypher

Trong mã Java, nên truyền tham số cho driver thay vì nối `accountId` vào câu truy vấn.

Mẫu khái niệm:

```java
String cypher = """
    MATCH (a:Account {accountId: $accountId})
    MATCH (a)-[:USES_DEVICE]->(d:Device)
    RETURN d.deviceId AS deviceId
    """;

var params = Map.of("accountId", accountId);
// Truyền cypher và params cho Neo4j Java Driver theo API phiên bản đang dùng.
```

Truyền tham số giúp tách dữ liệu khỏi câu truy vấn, dễ kiểm soát kiểu và tránh chèn mã truy vấn từ input. Nó cũng hữu ích cho việc sử dụng lại query plan ở những trường hợp phù hợp.

Đoạn trên mô tả cách tạo `cypher` và `params`, không phải một chương trình hoàn chỉnh; dự án cần import `java.util.Map` và sử dụng API driver thực tế.

### 13.3. Index nên đặt theo truy vấn chính

Ví dụ các màn hình:

| Màn hình/tác vụ | Điều kiện đầu vào | Index/constraint nên xem xét |
|---|---|---|
| Trang tài khoản | `accountId` | Uniqueness constraint trên `Account.accountId` |
| Tra cứu thiết bị | `deviceId` | Uniqueness constraint trên `Device.deviceId` |
| Tìm giao dịch trong khoảng ngày | `createdAt` trên `Transaction` | Range index |
| Tìm tài khoản theo tenant và mã | `tenantId + accountId` | Composite range hoặc node key phù hợp |
| Tra cứu tên theo tiền tố | `displayName STARTS WITH ...` | Text/range index theo khả năng engine |
| Tìm hồ sơ theo nội dung tự do | Từ khóa, mức liên quan | Full-text index |
| Tìm địa điểm gần tọa độ | Điểm và khoảng cách | Point index |

Không nhất thiết mọi màn hình cần index riêng. Hãy kiểm tra xem constraint đã tạo index hỗ trợ chưa và workload ghi có chịu được chi phí bảo trì không.

## 14. Liên hệ ràng buộc với thao tác MERGE và cập nhật

### 14.1. Tạo nút trùng có thể làm sai kết quả graph

Giả sử dịch vụ nhập sự kiện thiết bị theo nguồn khác nhau. Nếu không có uniqueness constraint cho `Device.deviceId`, hai luồng có thể tạo hai nút cùng ID `"D9"`.

```text
Account A1 --> Device "D9" (node 1)
Account A2 --> Device "D9" (node 2)
```

Một truy vấn đi qua nút thiết bị không tìm được mối liên hệ giữa A1 và A2, vì thực tế graph có hai nút D9 khác nhau. Bài toán gian lận có thể **bỏ sót liên kết thật**, dù thông tin bên ngoài cho thấy hai tài khoản dùng cùng thiết bị.

Ràng buộc uniqueness cùng quy trình nhập idempotent giúp ngăn loại lỗi này.

### 14.2. Duy nhất không có nghĩa mọi phép MERGE đều an toàn

Ví dụ:

```cypher
MERGE (a:Account {accountId: $accountId, status: $status})
RETURN a;
```

Nếu `accountId` đã tồn tại nhưng `status` khác, toàn mẫu thuộc tính trong `MERGE` không khớp. Engine có thể cố tạo nút có cùng ID, dẫn tới lỗi uniqueness constraint.

Một cách rõ hơn:

```cypher
MERGE (a:Account {accountId: $accountId})
SET a.status = $status
RETURN a;
```

Ở đây, **chỉ trường định danh bất biến** được dùng để xác định đối tượng; trạng thái là thuộc tính cần cập nhật.

Trong thực tế, một trạng thái nghiệp vụ không nhất thiết được phép chuyển tùy ý. Có thể cần kiểm tra phiên bản, giao dịch hoặc điều kiện chuyển trạng thái ở lớp nghiệp vụ.

### 14.3. Quan hệ trùng lặp và ràng buộc nghiệp vụ

`MERGE (a)-[:USES_DEVICE]->(d)` có thể giúp tránh tạo trùng một quan hệ cùng loại/hướng giữa cùng hai nút khi được dùng phù hợp. Nhưng đồ thị cũng có trường hợp cần nhiều cạnh giữa cùng một cặp nút, chẳng hạn các lần chuyển tiền khác nhau.

Do đó, **không nên xóa mọi cạnh trùng đầu mút** nếu mỗi cạnh là một sự kiện riêng. Với giao dịch chuyển tiền, có thể tạo nút `Transaction` có ID duy nhất và nối hai đầu, hoặc dùng mô hình cạnh có định danh sự kiện với ràng buộc thích hợp.

Cần định nghĩa rõ sự khác nhau giữa:

- Quan hệ biểu diễn **trạng thái tồn tại**: “A đang sử dụng D”.
- Quan hệ biểu diễn **sự kiện**: “A đã chuyển tiền cho B tại thời điểm T với transactionId X”.

Hai loại quan hệ có chiến lược tạo, cập nhật, xác định duy nhất và truy vấn khác nhau.

## 15. Không thể giải quyết mọi ràng buộc nghiệp vụ bằng schema

Một hệ giao dịch có thể yêu cầu:

> “Mỗi tài khoản phải thuộc đúng một tenant, và không được dùng một thiết bị bị cấm.”

Uniqueness constraint trên `Account.accountId` hoặc `Device.deviceId` chưa tự thực thi các quy tắc này. Cần xác định:

1. Ai tạo hoặc sửa quan hệ `BELONGS_TO`?
2. Làm sao kiểm tra tài khoản có đúng một tenant?
3. Quy tắc “thiết bị bị cấm” có thay đổi theo thời gian không?
4. Cần giao dịch nguyên tử giữa kiểm tra và tạo quan hệ không?
5. Cần audit lịch sử thay đổi quan hệ không?
6. Có thể xảy ra ghi đồng thời từ hai dịch vụ không?

Nếu quy tắc phải đúng ngay lúc ghi, nên thực thi bằng cơ chế giao dịch và kiểm tra phù hợp thay vì chỉ rà soát sau. Nếu quy tắc là phân tích rủi ro có thể cập nhật bất đồng bộ, có thể dùng xử lý sự kiện và các job kiểm tra định kỳ.

Ràng buộc ở database là lớp phòng vệ rất hữu ích nhưng **không thay thế thiết kế tính đúng đắn nghiệp vụ**.

## 16. Chi phí mở rộng graph khi anchor có độ chọn lọc thấp

### 16.1. Một phép ước lượng sơ bộ

Giả sử:

- 1 triệu tài khoản có `status = "ACTIVE"`.
- Mỗi tài khoản dùng trung bình 3 thiết bị.
- Mỗi thiết bị được 10 tài khoản dùng.
- Câu truy vấn bắt đầu từ **mọi tài khoản active** rồi đi hai cạnh qua thiết bị.

Số lần mở rộng trung gian thô có thể lên đến:

```text
1.000.000 tài khoản
  × 3 thiết bị/tài khoản
  × 10 tài khoản/thiết bị
≈ 30.000.000 lượt kết nối trung gian
```

Con số này chỉ minh họa và có thể có nhiều kết quả trùng; phân phối degree thật thường khác trung bình.

Nếu chỉ bắt đầu từ **một** tài khoản theo ID:

```text
1 tài khoản
  × 3 thiết bị
  × 10 tài khoản/thiết bị
≈ 30 lượt kết nối trung gian
```

Sự khác biệt không nằm ở số nhãn hay số dòng Cypher. Nó nằm ở **số nút ban đầu và fan-out trên đường duyệt**.

### 16.2. Dùng điều kiện lọc càng sớm càng tốt, nhưng giữ đúng ngữ nghĩa

Nếu chỉ muốn thiết bị có `riskFlag = true`, hãy mô tả điều kiện đó:

```cypher
MATCH (a:Account {accountId: $accountId})-[:USES_DEVICE]->(d:Device)
WHERE d.riskFlag = true
MATCH (d)<-[:USES_DEVICE]-(other:Account)
WHERE other.accountId <> a.accountId
RETURN DISTINCT other.accountId
LIMIT 50;
```

Bộ tối ưu có thể áp dụng filter theo kế hoạch thích hợp. Tuy nhiên, từ một tài khoản đã biết, engine vẫn có thể phải duyệt các thiết bị của tài khoản đó để kiểm tra `riskFlag`. Index trên `Device.riskFlag` không có nghĩa nó luôn được dùng cho trường hợp này.

Nếu điều kiện lọc quá kém chọn lọc, tạo index chỉ để hỗ trợ một cờ boolean có thể không đem lại lợi ích đáng kể. Cần đo cụ thể.

### 16.3. Tối ưu mà không làm sai câu hỏi

Ví dụ lọc bỏ IP công cộng để giảm số cặp tài khoản có thể là quyết định nghiệp vụ hợp lý nếu hệ thống chỉ coi IP riêng tư là dấu hiệu mạnh. Nhưng nếu bài toán thật yêu cầu phát hiện mọi liên kết thông qua mọi IP, tự ý bỏ IP phổ biến sẽ thay đổi độ bao phủ.

Mọi giới hạn độ sâu, lọc node, cắt đường đi hoặc sampling cần được giải thích bằng **yêu cầu kết quả**, sau đó mới đánh giá lợi ích hiệu năng.

## 17. Quy trình thiết kế index, constraint và anchor từ đầu

### Bước 1: Viết câu hỏi nghiệp vụ chính xác

Ví dụ:

> “Cho một accountId, tìm các tài khoản cùng tenant dùng chung thiết bị trong 90 ngày gần nhất; trả tối đa 50 tài khoản khác nhau.”

Tách thành:

- Đầu vào: `accountId`, `tenantId`, mốc thời gian.
- Điểm xuất phát: một tài khoản cụ thể.
- Mẫu quan hệ: `Account -> Device <- Account`.
- Bộ lọc: cùng tenant, quan hệ hoặc sự kiện trong 90 ngày.
- Kết quả: tài khoản khác nhau, giới hạn 50.
- Yêu cầu đúng: dữ liệu thiết bị mới đến chậm bao lâu là chấp nhận được?

### Bước 2: Chọn định danh và ràng buộc

Nếu ID toàn cục duy nhất, dùng `Account.accountId`. Nếu chỉ duy nhất trong tenant, dùng cặp `tenantId, accountId` và constraint/index ghép phù hợp.

Đảm bảo các node `Device` có định danh chuẩn thống nhất, tránh việc cùng thiết bị bị tạo thành nhiều node.

### Bước 3: Chọn anchor có độ chọn lọc cao

Nếu truy vấn đã có một accountId, đây thường là điểm bắt đầu tốt. Nếu yêu cầu thay đổi thành “mọi tài khoản của thiết bị D9”, anchor đổi sang Device D9.

### Bước 4: Mô tả chính xác các cạnh cần duyệt

Chọn label, loại quan hệ, hướng, giới hạn độ sâu, trường thời gian và cách loại trùng. Không dùng mẫu quá rộng nếu không cần.

### Bước 5: Xem index hiện có

Trong Neo4j có thể kiểm tra:

```cypher
SHOW INDEXES;
```

và:

```cypher
SHOW CONSTRAINTS;
```

Cú pháp xuất thông tin và cột kết quả thay đổi theo phiên bản. Mục tiêu là xác nhận index/constraint cần dùng đã tồn tại, online và có loại phù hợp.

### Bước 6: Xem kế hoạch và đo dữ liệu thật

Dùng `EXPLAIN` để xem dự kiến, `PROFILE` để đo một lần thực thi trên dữ liệu đại diện. Quan sát:

- Index seek hay label scan?
- Số dòng tăng tại bước expand nào?
- DB hits có tập trung ở các node bậc cao?
- `DISTINCT` hoặc `ORDER BY` có xử lý quá nhiều dòng?
- Truy vấn chậm ở p95/p99 khi có nhiều client đồng thời?

### Bước 7: Tối ưu dựa trên nút thắt được đo

Một số lựa chọn:

- Thêm index phù hợp nếu tìm điểm bắt đầu đang quét nhiều nút.
- Đổi anchor nếu một điều kiện khác chọn lọc hơn.
- Giới hạn loại/hướng quan hệ hoặc độ sâu theo yêu cầu.
- Đưa điều kiện lọc hợp lý vào truy vấn.
- Tạo một tập ứng viên đã tính trước cho bài toán phân tích lớn.
- Chạy một số báo cáo graph theo lô thay vì trong request tương tác.
- Điều chỉnh mô hình nếu có supernode và fan-out quá lớn.

Không tăng số index chỉ vì query chậm; nếu plan đã seek một nút duy nhất nhưng bước expand tạo hàng triệu dòng, vấn đề chính không nằm ở bước tìm anchor.

## 18. Quản lý thay đổi chỉ mục và ràng buộc

### 18.1. Thêm uniqueness constraint khi dữ liệu đã có

Nếu database đang có hai nút `Account` cùng `accountId = "A1"`, việc tạo constraint unique có thể thất bại vì dữ liệu hiện tại đã vi phạm quy tắc.

Trước khi thêm constraint trong hệ thống có dữ liệu, cần quy trình:

1. Phân tích những bản ghi trùng hoặc thiếu khóa.
2. Xác định node nào là bản ghi chuẩn và cách hợp nhất các cạnh.
3. Chuẩn hóa định danh và các kiểu thuộc tính.
4. Sửa ứng dụng ghi để không tiếp tục tạo dữ liệu sai.
5. Tạo constraint trong thời điểm và môi trường vận hành phù hợp.
6. Quan sát lỗi nhập dữ liệu sau thay đổi.

Không thể chỉ “xóa node trùng” mà không xét các cạnh đang nối với chúng; xóa nhầm có thể làm mất mối liên hệ có giá trị.

### 18.2. Phân biệt thay đổi index và đổi quy tắc nghiệp vụ

Thêm index thường không làm thay đổi câu trả lời đúng/sai của truy vấn, nhưng làm tăng chi phí ghi và thay đổi kế hoạch thực thi.

Thêm uniqueness constraint có thể khiến những thao tác ghi trước đây thành công giờ bị từ chối. Đây là **thay đổi hợp đồng dữ liệu**, cần được phối hợp giữa các producer và service.

### 18.3. Theo dõi index đã tạo nhưng ít dùng

Index không được sử dụng có thể chiếm tài nguyên mà không giúp hiệu năng. Nên theo dõi sử dụng index và workload, nhưng không xóa index chỉ vì trong một khoảng đo ngắn không thấy sử dụng: nó có thể phục vụ công việc định kỳ hoặc truy vấn hiếm nhưng quan trọng.

Đặc biệt, index được tạo để hỗ trợ uniqueness constraint có vai trò bảo vệ tính đúng; không nên coi nó tương đương một index phụ tùy chọn.

## 19. Tình huống so sánh lựa chọn điểm bắt đầu

### Tình huống A: tìm tài khoản qua email

**Yêu cầu:** “Tìm tài khoản có email cụ thể rồi xem các thiết bị đã đăng nhập.”

- Anchor: `Account.email` nếu email có quy tắc lưu nhất quán.
- Index: index hoặc uniqueness constraint phù hợp với chính sách email duy nhất.
- Duyệt: `Account -[:USES_DEVICE]-> Device`.
- Lưu ý: email có thể thay đổi; nếu email không đảm bảo duy nhất, kết quả có thể gồm nhiều tài khoản.

**Bài học:** dùng thuộc tính làm anchor cần hiểu tính duy nhất, khả năng thay đổi và validation.

### Tình huống B: tìm người dùng cùng thiết bị công cộng

**Yêu cầu:** “Tìm toàn bộ tài khoản dùng chung thiết bị kiosk K.”

- Anchor: `Device.deviceId = K`, có index định danh.
- Duyệt: `Device <-[:USES_DEVICE]- Account`.
- Rủi ro: kiosk có thể có hàng trăm nghìn tài khoản.
- Hướng thiết kế: giới hạn thời gian/khoảng kết quả, làm báo cáo nền hoặc điều chỉnh tiêu chí nghiệp vụ.

**Bài học:** anchor có tính duy nhất vẫn có thể là supernode.

### Tình huống C: từ một giao dịch tới chuỗi chuyển tiền

**Yêu cầu:** “Từ giao dịch T100, tìm những tài khoản đã nhận tiền qua tối đa 3 bước.”

- Anchor: `Transaction.transactionId` hoặc tài khoản nguồn có liên kết giao dịch.
- Index: unique transaction ID để xác định điểm đầu.
- Duyệt: loại cạnh chuyển tiền, hướng, giới hạn độ sâu.
- Rủi ro: chuỗi chuyển tiền rẽ nhánh mạnh; cần nhận diện giao dịch trùng và điều kiện thời gian.

**Bài học:** thiết kế ràng buộc giao dịch và mô hình hóa các cạnh ảnh hưởng khả năng giải thích đường đi.

### Tình huống D: tìm sản phẩm giống nội dung tìm kiếm rồi duyệt graph gợi ý

**Yêu cầu:** “Từ câu tìm kiếm văn bản, lấy một số sản phẩm liên quan rồi gợi ý sản phẩm cùng được mua.”

- Anchor: các nút sản phẩm được full-text/vector index tìm làm ứng viên.
- Duyệt: các cạnh `BOUGHT_WITH` hoặc `VIEWED_WITH` đã thiết kế.
- Rủi ro: quá nhiều ứng viên và sản phẩm phổ biến có degree cao; xếp hạng có thể tốn kém.
- Đánh đổi: cần xác định cách kết hợp điểm tìm kiếm và điểm graph.

**Bài học:** điểm bắt đầu không nhất thiết là một ID duy nhất; có thể là **một tập ứng viên nhỏ** do index chuyên dụng cung cấp.

### Tình huống E: người dùng thuộc tenant nào?

**Yêu cầu:** “Cho tenantId và userId, tìm các vai trò và quyền của người dùng trong tenant đó.”

- Anchor: cặp định danh `tenantId + userId`.
- Constraint/index: composite key phù hợp, có kiểm tra tồn tại.
- Duyệt: `Account -[:HAS_ROLE]-> Role -[:GRANTS]-> Permission`.
- Rủi ro: quan hệ liên tenant hoặc quyền có phạm vi khác nhau.

**Bài học:** đúng kiểu khóa chưa đủ; đường duyệt phải giữ đúng phạm vi bảo mật và nghiệp vụ.

## 20. Các sai lầm thường gặp

**“Graph có cạnh nên không cần index.”** Sai. Cần index hoặc cấu trúc truy cập phù hợp để tìm được nút/cạnh bắt đầu khi đồ thị lớn.

**“Có index thì truy vấn nhiều bước luôn nhanh.”** Sai. Index có thể chỉ giảm chi phí tìm anchor; phần expand qua nhiều cạnh và supernode vẫn tốn kém.

**“Chỉ mục thuộc tính của nút đích được sử dụng ở mọi bước duyệt.”** Không nhất thiết. Đi đến nút qua cạnh thường dùng cấu trúc kề, khác với tìm nút theo thuộc tính từ đầu.

**“Viết nút nào trước trong Cypher thì engine chắc chắn chạy nút đó trước.”** Không đúng trong mọi tình huống. Query planner chọn kế hoạch dựa trên thống kê và index; phải kiểm tra bằng `EXPLAIN`/`PROFILE`.

**“Uniqueness constraint tự buộc trường phải tồn tại.”** Không phải mặc định; cần hiểu quy tắc riêng của constraint hoặc dùng node key/existence nếu sản phẩm hỗ trợ.

**“MERGE tự giải quyết mọi trường hợp trùng dữ liệu và ghi đồng thời.”** Không. Cách chọn thuộc tính trong `MERGE` và constraint xác định tính đúng; xung đột đồng thời vẫn cần xử lý lỗi.

**“DISTINCT và LIMIT giải quyết hoàn toàn bùng nổ kết quả.”** Không. Chúng có thể chỉ xử lý sau khi rất nhiều đường đi trung gian đã được tạo.

**“Mỗi thuộc tính đều nên có index.”** Không. Chỉ mục làm tăng dung lượng và chi phí cập nhật; nhiều chỉ mục có thể trùng chức năng.

**“Quan hệ có sẵn nghĩa là mọi quy tắc nghiệp vụ đều đã được bảo đảm.”** Không. Graph engine giúp duy trì cạnh giữa những nút tồn tại nhưng không tự đảm bảo quan hệ đúng loại, đúng tenant và đúng số lượng theo nghiệp vụ.

**“Đọc nhanh từ graph là đủ để xác nhận một hành động nhạy cảm.”** Không. Với thao tác tài chính, phân quyền hoặc cập nhật trạng thái quan trọng, cần kiểm tra tính đúng và bảo đảm giao dịch phù hợp.

## 21. Bài tập tự vận dụng

### Bài tập 1: chọn index và anchor

Một đồ thị có 30 triệu nút `Customer`, mỗi nút có `customerId` duy nhất, kết nối với các nút `Store` bằng quan hệ `VISITED`. Câu hỏi: “Khách C123 đã ghé những cửa hàng nào?”.

**Yêu cầu:** Xác định anchor, ràng buộc và truy vấn.

**Gợi ý:**

```cypher
CREATE CONSTRAINT customer_id_unique IF NOT EXISTS
FOR (c:Customer)
REQUIRE c.customerId IS UNIQUE;

MATCH (c:Customer {customerId: $customerId})-[:VISITED]->(s:Store)
RETURN DISTINCT s.storeId;
```

Anchor là một nút Customer được tra cứu theo ID. Sau đó truy vấn duyệt các cạnh VISITED của khách.

### Bài tập 2: nhận diện supernode

Tất cả tài khoản đều được gắn với `IP = "0.0.0.0"` do một lỗi nhập dữ liệu. Truy vấn tìm tài khoản chia sẻ IP từ A1 đột nhiên trả hàng triệu kết quả.

**Câu hỏi:** Thêm index `IP.address` có giải quyết được toàn bộ chi phí không?

**Gợi ý:** Index có thể giúp tìm nút IP, nhưng không giảm số cạnh kề của node IP đã bị gắn sai. Cần xử lý chất lượng dữ liệu và định nghĩa IP hợp lệ, sau đó đánh giá fan-out.

### Bài tập 3: ràng buộc duy nhất khác tồn tại

CSDL có các nút:

```cypher
(:Account {accountId: "A1"})
(:Account {accountId: "A2"})
(:Account {status: "ACTIVE"})
```

**Câu hỏi:** Uniqueness constraint trên `Account.accountId` có đảm bảo tài khoản thứ ba luôn có accountId không?

**Gợi ý:** Không. Uniqueness và property existence là hai yêu cầu riêng; node key có thể kết hợp trong phạm vi edition hỗ trợ.

### Bài tập 4: sửa MERGE

Một ứng dụng viết:

```cypher
MERGE (a:Account {accountId: $id, status: $status})
RETURN a;
```

Khi trạng thái thay đổi, thao tác gặp lỗi uniqueness.

**Câu hỏi:** Cần sửa gì?

**Gợi ý:**

```cypher
MERGE (a:Account {accountId: $id})
SET a.status = $status
RETURN a;
```

Đồng thời cần quy tắc chuyển trạng thái hợp lệ nếu nghiệp vụ yêu cầu.

### Bài tập 5: phân tích truy vấn không có anchor

```cypher
MATCH (a:Account)-[:USES_DEVICE]->(d:Device)
      <-[:USES_DEVICE]-(b:Account)
RETURN a, b
LIMIT 10;
```

**Câu hỏi:** Vì sao `LIMIT 10` chưa chắc là cách kiểm soát chi phí tốt?

**Gợi ý:** Query planner có thể phải tạo lượng lớn ứng viên trước khi tìm được 10 kết quả theo điều kiện mong muốn; nếu thêm `DISTINCT`/`ORDER BY` thì có thể còn tốn hơn. Nếu yêu cầu là một tài khoản cụ thể, hãy thêm điều kiện anchor theo ID. Nếu cần báo cáo toàn hệ, dùng phương án phù hợp với khối lượng phân tích.

### Bài tập 6: đa tenant

Một người dùng có `accountId = "U100"` trong tenant `T1` và một người khác có `accountId = "U100"` trong tenant `T2`.

**Câu hỏi:** Vì sao unique trên mỗi `accountId` toàn graph có thể không đúng nghiệp vụ? Nên dùng gì?

**Gợi ý:** Nếu ID chỉ duy nhất trong tenant, khóa logic là cặp `(tenantId, accountId)`. Hãy dùng constraint/index ghép hỗ trợ quy tắc đó và bảo đảm truy vấn/quan hệ không đi sai phạm vi tenant.

### Bài tập 7: đọc plan

Một truy vấn có `NodeUniqueIndexSeek` để tìm một tài khoản, sau đó `Expand` trả ra 2 triệu dòng và `Distinct` còn 500 dòng.

**Câu hỏi:** Có nên ưu tiên tạo thêm index trên `Account.accountId`?

**Gợi ý:** Không có bằng chứng cần thêm index cho anchor vì đã có unique index seek. Nút thắt có khả năng ở fan-out qua cạnh, supernode hoặc điều kiện lọc/độ sâu; cần phân tích phần expand và yêu cầu nghiệp vụ.

## 22. Kết luận

Trong mô hình đồ thị, **index giúp định vị nút hoặc quan hệ theo thuộc tính**, **constraint giữ các định danh và quy tắc dữ liệu quan trọng**, còn **điểm bắt đầu truy vấn quyết định phạm vi phải duyệt**. Ba yếu tố này gắn chặt với nhau: một ràng buộc định danh đúng có thể cung cấp index để tìm anchor duy nhất; từ anchor đó, graph engine dùng cấu trúc quan hệ để mở rộng đến kết quả.

Một truy vấn graph hiệu quả thường bắt đầu từ **một đối tượng hoặc tập ứng viên đủ chọn lọc**, duyệt **đúng loại cạnh và hướng**, có **giới hạn phù hợp với nghiệp vụ**, rồi dùng kế hoạch `EXPLAIN`/`PROFILE` để kiểm chứng chi phí. Nếu anchor đã được tìm rất nhanh mà truy vấn vẫn chậm, cần xem **bậc nút, fan-out, độ sâu và kích thước kết quả trung gian** trước khi thêm index.

Thiết kế constraint cũng là phần của thiết kế graph: cùng một ID bị tạo thành nhiều nút, thiếu thuộc tính bắt buộc hoặc kết nối sai phạm vi có thể làm **kết quả đường đi sai**, dù câu truy vấn Cypher chạy nhanh. Kết hợp mô hình dữ liệu chính xác, chỉ mục đúng mục tiêu và truy vấn có anchor rõ ràng là nền tảng để sử dụng graph database hiệu quả và đáng tin cậy.

