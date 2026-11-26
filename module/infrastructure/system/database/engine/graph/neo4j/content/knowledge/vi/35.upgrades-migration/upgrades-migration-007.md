# Di trú nhãn, thuộc tính và quan hệ mà vẫn giữ định danh nghiệp vụ

## 1. Bài toán: đổi graph model nhưng không đổi danh tính thực thể

Trong module **DATABASE_ENGINE_GRAPH_NEO4J**, Neo4j biểu diễn dữ liệu bằng **node**, **relationship** và **property**, được truy vấn bằng Cypher và thường được sử dụng qua Java Driver hoặc Spring Data Neo4j. Khi ứng dụng phát triển, graph model có thể cần thay đổi:

- Nhãn node **LegacyCustomer** được thay bằng **Customer**.
- Thuộc tính **accountNo** được đổi tên thành **customerId**.
- Thuộc tính **totalCents** chuyển sang **amountMinor**, vẫn lưu số nguyên theo đơn vị nhỏ nhất của tiền.
- Loại relationship **PURCHASED** đổi thành **PLACED**, cùng hướng từ Customer tới Order.
- Truy vấn và repository được cập nhật để dùng nhãn, tên thuộc tính và quan hệ mới.

Khó khăn không nằm ở việc đổi tên trong một câu Cypher. **Cùng một khách hàng phải tiếp tục là cùng một khách hàng**, dù hệ thống đã đổi model, deploy nhiều service hoặc chạy lại migration sau khi gặp lỗi.

Một lỗi di trú có thể khiến ứng dụng tạo **hai node Customer** cho cùng mã, làm mất quan hệ Customer–Order, liên kết đơn hàng sang tenant khác hoặc đặt lại trạng thái Order đã thanh toán. Đáng lo hơn, nhiều lỗi không gây exception: Cypher vẫn chạy nhưng trả sai graph.

**Mục tiêu bài học:** thiết kế và kiểm thử di trú **nhãn, property và relationship** theo cách bảo toàn **business key**, có thể chạy lại an toàn, hỗ trợ triển khai nhiều phiên bản ứng dụng cùng lúc, và chỉ xóa cấu trúc cũ khi đã có bằng chứng.

> **Phạm vi:** mọi lệnh tạo, cập nhật và xóa trong bài dành cho **database thử nghiệm riêng**. Với production, phải có backup, kế hoạch triển khai nhiều bước, giới hạn quyền và kiểm tra dữ liệu nguồn trước khi thay đổi.

## 2. Định danh nghiệp vụ khác ID nội bộ của Neo4j

### 2.1. Ba loại định danh thường gặp

| Khái niệm | Ví dụ | Công dụng | Có nên dùng làm hợp đồng API lâu dài? |
|---|---|---|---|
| **Business key** | **(tenantId, customerId)** | Nhận biết cùng một khách hàng qua các model và hệ thống | **Có**, khi được quản lý ổn định |
| **ID nội bộ của graph** | **elementId(n)** hoặc ID nội bộ đời cũ | Tham chiếu phần tử Neo4j theo quy tắc API tương ứng | **Không** coi là mã nghiệp vụ bền vững |
| **Request/event ID** | **eventId = ev-a-101** | Chống xử lý lại một sự kiện hoặc lần gửi yêu cầu | Có, nhưng theo **phạm vi sự kiện**, không thay cho customerId |

Trong bài này, định danh khách hàng là cặp **(tenantId, customerId)**; định danh đơn hàng là **(tenantId, orderId)**. Hai tenant được phép sử dụng cùng mã **C-1** hoặc **P-101** mà không tạo xung đột.

Một phép đổi nhãn **SET n:Customer** trên node hiện có không tạo node mới; node vẫn là cùng thực thể graph. Nhưng **không dựa vào điều đó để phát hành elementId ra hệ thống khác**. Khi thực hiện dump/restore, tạo lại dữ liệu hoặc hợp nhất graph, cách kiểm chứng chính vẫn phải dựa trên **business key**.

### 2.2. Bất biến nghiệp vụ trước và sau migration

Ký hiệu \(K_C=(tenantId,customerId)\) và \(K_O=(tenantId,orderId)\).

Một migration đạt yêu cầu khi:

1. **Bảo toàn khóa:** mỗi node Customer cũ tương ứng **đúng một** Customer mới mang cùng \(K_C\); mỗi Order cũ tương ứng đúng một Order mới cùng \(K_O\).
2. **Không tạo trùng:** không có hai node cùng nhãn đích có cùng khóa hợp lệ.
3. **Không mất liên kết:** nếu Customer A đặt Order B theo model cũ, model mới còn một quan hệ tương ứng với đúng hướng và tenant.
4. **Không đổi dữ liệu ngoài hợp đồng:** số tiền, trạng thái, thời gian và các thuộc tính cần giữ không bị mất hoặc ép kiểu sai.
5. **Chạy lại an toàn:** chạy migration lần thứ hai không tăng số thực thể/quan hệ hoặc ghi đè những thay đổi hợp lệ mới phát sinh.
6. **Tương thích chuyển tiếp:** trong thời gian hai phiên bản ứng dụng cùng hoạt động, không có khoảng trống ghi dữ liệu chỉ vào một phía mà phía kia không thể đọc.

**Lưu ý:** uniqueness constraint bảo vệ tính **duy nhất**, nhưng không mặc nhiên yêu cầu mọi node đều có đầy đủ các property trong khóa. Phải kiểm tra **khóa thiếu/null** riêng hoặc cân nhắc **node key constraint** nếu edition hỗ trợ.

## 3. Thiết kế sơ đồ cũ → mới trước khi viết Cypher

Giả sử dữ liệu xuất phát là:

~~~text
(:DemoMigLegacyCustomer {
    orgId: "shop-a",
    accountNo: "C-1",
    fullName: "An"
})-[:DEMO_MIG_PURCHASED {
    sourceEventId: "ev-a-101",
    createdAt: datetime(...)
}]->(:DemoMigLegacyPurchase {
    orgId: "shop-a",
    purchaseNo: "P-101",
    totalCents: 120000,
    orderState: "PAID"
})
~~~

Model đích:

~~~text
(:DemoMigCustomer {
    tenantId: "shop-a",
    customerId: "C-1",
    displayName: "An"
})-[:DEMO_MIG_PLACED {
    eventId: "ev-a-101",
    occurredAt: datetime(...)
}]->(:DemoMigOrder {
    tenantId: "shop-a",
    orderId: "P-101",
    amountMinor: 120000,
    status: "PAID"
})
~~~

Đây là các tên nhãn và loại relationship **dành cho bài thử**, tách biệt dữ liệu ứng dụng thực tế.

### 3.1. Bảng mapping bắt buộc

| Thành phần cũ | Thành phần đích | Phép chuyển | Bất biến phải kiểm tra |
|---|---|---|---|
| **DemoMigLegacyCustomer** | **DemoMigCustomer** | Thêm nhãn mới trên cùng node | Không tăng số Customer logic |
| **orgId** (Customer) | **tenantId** | Sao chép giá trị, không tự gán mặc định | Bằng nhau sau mapping |
| **accountNo** | **customerId** | Sao chép **STRING** | Giữ cả chữ, số 0 đầu và đúng tenant |
| **fullName** | **displayName** | Sao chép khi đích chưa có | Không ghi đè tên vừa được cập nhật |
| **DemoMigLegacyPurchase** | **DemoMigOrder** | Thêm nhãn mới trên cùng node | Không tăng số Order logic |
| **purchaseNo** | **orderId** | Sao chép STRING | Không tạo mã ngẫu nhiên mới |
| **totalCents** | **amountMinor** | Sao chép INTEGER theo đơn vị nhỏ nhất | Không mất độ chính xác tiền |
| **orderState** | **status** | Mapping trạng thái có chủ đích | PAID → PAID; CREATED → NEW theo ví dụ |
| **DEMO_MIG_PURCHASED** | **DEMO_MIG_PLACED** | Tạo relationship mới có hướng | Không tạo quan hệ sai endpoint |
| **sourceEventId** | **eventId** | Sao chép mã sự kiện | Bảo toàn định danh sự kiện |
| **createdAt** (relationship) | **occurredAt** | Sao chép kiểu thời gian | Không biến UTC thành ngày địa phương sai |

**Không dùng** tên property thay đổi được như **status**, **displayName** hoặc **lastUpdatedAt** làm một phần của **MERGE key**. Chúng là dữ liệu của thực thể, không phải định danh.

### 3.2. Sơ đồ hướng quan hệ

~~~mermaid
flowchart LR
  subgraph OLD["Model cũ"]
    LC["LegacyCustomer<br/>orgId + accountNo"] -->|"DEMO_MIG_PURCHASED"| LP["LegacyPurchase<br/>orgId + purchaseNo"]
  end
  subgraph NEW["Model mới"]
    C["Customer<br/>tenantId + customerId"] -->|"DEMO_MIG_PLACED"| O["Order<br/>tenantId + orderId"]
  end
  LC -.->|"Giữ cùng business key"| C
  LP -.->|"Giữ cùng business key"| O
~~~

Trong lựa chọn **di trú tại chỗ** của bài, LC và C là **cùng node có hai nhãn trong thời gian chuyển tiếp**; tương tự với LegacyPurchase và Order. Mũi tên nét đứt là **mapping logic**, không phải relationship Neo4j cần tạo thêm.

## 4. Tạo fixture có thể phát hiện lỗi nhầm tenant

### 4.1. Chuẩn bị schema nguồn và schema đích

Chạy những constraint dưới đây trên **database thử nghiệm sạch**:

~~~cypher
CREATE CONSTRAINT demo_mig_old_customer_key IF NOT EXISTS
FOR (c:DemoMigLegacyCustomer)
REQUIRE (c.orgId, c.accountNo) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_mig_old_purchase_key IF NOT EXISTS
FOR (o:DemoMigLegacyPurchase)
REQUIRE (o.orgId, o.purchaseNo) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_mig_customer_key IF NOT EXISTS
FOR (c:DemoMigCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_mig_order_key IF NOT EXISTS
FOR (o:DemoMigOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

Các constraint đích được tạo **trước khi thêm nhãn mới**, giúp phát hiện xung đột khi di trú. Nếu graph đã có node **DemoMigCustomer** của một nguồn nhập khác với cùng business key, quá trình gắn nhãn mới có thể bị từ chối thay vì âm thầm tạo hai thực thể logic. Phải phân loại và giải quyết xung đột đó trước khi tiếp tục.

Các lệnh **CREATE CONSTRAINT** cần quyền quản trị schema. Với **Enterprise Edition**, có thể xem xét **node key constraint** để buộc cả **tồn tại + duy nhất**; loại uniqueness thông thường ở ví dụ không tự cấm property rỗng/null.

### 4.2. Tạo dữ liệu nguồn mẫu

~~~cypher
CREATE
  (c1:DemoMigLegacyCustomer {
    orgId: 'shop-a', accountNo: 'C-1', fullName: 'An'
  }),
  (c2:DemoMigLegacyCustomer {
    orgId: 'shop-b', accountNo: 'C-1', fullName: 'Bình'
  }),
  (p1:DemoMigLegacyPurchase {
    orgId: 'shop-a', purchaseNo: 'P-101',
    totalCents: 120000, orderState: 'PAID'
  }),
  (p2:DemoMigLegacyPurchase {
    orgId: 'shop-a', purchaseNo: 'P-102',
    totalCents: 69000, orderState: 'CREATED'
  }),
  (p3:DemoMigLegacyPurchase {
    orgId: 'shop-b', purchaseNo: 'P-101',
    totalCents: 27000, orderState: 'CREATED'
  }),
  (c1)-[:DEMO_MIG_PURCHASED {
    sourceEventId: 'ev-a-101',
    createdAt: datetime('2026-10-01T08:00:00Z')
  }]->(p1),
  (c1)-[:DEMO_MIG_PURCHASED {
    sourceEventId: 'ev-a-102',
    createdAt: datetime('2026-10-01T09:00:00Z')
  }]->(p2),
  (c2)-[:DEMO_MIG_PURCHASED {
    sourceEventId: 'ev-b-101',
    createdAt: datetime('2026-10-01T10:00:00Z')
  }]->(p3);
~~~

Kỳ vọng:

| Tenant | Customer | Order | totalCents | orderState | Event |
|---|---|---|---:|---|---|
| shop-a | C-1 | P-101 | 120000 | PAID | ev-a-101 |
| shop-a | C-1 | P-102 | 69000 | CREATED | ev-a-102 |
| shop-b | C-1 | P-101 | 27000 | CREATED | ev-b-101 |

Hai tenant cùng có **Customer C-1** và **Order P-101**. Chính trường hợp này giúp phát hiện truy vấn hoặc migration quên **tenantId/orgId**.

**Không chạy lại CREATE fixture** khi dữ liệu đã có; uniqueness constraint có thể gây lỗi. Để làm lại bài, dùng database test mới hoặc quy trình reset fixture đã được cô lập. Không dùng **MATCH (n) DETACH DELETE n** trên database dùng chung.

## 5. Preflight: xác minh dữ liệu nguồn trước khi sửa graph

Một migration tốt **dừng trước khi ghi** nếu nguồn chứa dữ liệu vi phạm bất biến. Không biến dữ liệu lỗi thành một kết quả có vẻ hợp lệ bằng cách lặng lẽ bỏ qua những dòng không khớp.

### 5.1. Kiểm tra business key bị thiếu

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WHERE trim(coalesce(c.orgId, '')) = ''
   OR trim(coalesce(c.accountNo, '')) = ''
RETURN c.orgId AS orgId, c.accountNo AS accountNo
LIMIT 50;
~~~

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
WHERE trim(coalesce(o.orgId, '')) = ''
   OR trim(coalesce(o.purchaseNo, '')) = ''
RETURN o.orgId AS orgId, o.purchaseNo AS purchaseNo
LIMIT 50;
~~~

Với fixture hợp lệ, cả hai truy vấn **không trả hàng**. Nếu còn dòng lỗi, phải sửa/loại/quarantine theo chính sách nghiệp vụ trước khi gắn nhãn đích.

**Chú ý:** business ID là STRING. Không dùng **toInteger('00042')** nếu cần giữ số 0 đầu; không tự xóa dấu cách hoặc chuyển chữ hoa/thường nếu hệ thống chưa thống nhất cách chuẩn hóa định danh.

### 5.2. Kiểm tra khóa trùng trong dữ liệu đã tồn tại

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WITH c.orgId AS orgId, c.accountNo AS accountNo, count(*) AS copies
WHERE copies > 1
RETURN orgId, accountNo, copies;
~~~

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
WITH o.orgId AS orgId, o.purchaseNo AS purchaseNo, count(*) AS copies
WHERE copies > 1
RETURN orgId, purchaseNo, copies;
~~~

Nếu constraint nguồn có hiệu lực, các bản ghi trùng khóa đầy đủ thông thường đã bị ngăn. Nhưng trên dữ liệu di trú từ hệ thống cũ chưa có constraint, cần chạy các truy vấn này **trước khi tạo constraint mới**. Thêm **IF NOT EXISTS** không tự hợp nhất dữ liệu trùng.

### 5.3. Kiểm tra quan hệ xuyên tenant hoặc thiếu endpoint đúng

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
      -[r:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase)
WHERE c.orgId IS NULL OR o.orgId IS NULL
   OR c.orgId <> o.orgId
RETURN c.orgId AS customerTenant, c.accountNo AS customerId,
       o.orgId AS orderTenant, o.purchaseNo AS orderId,
       r.sourceEventId AS eventId;
~~~

Kết quả kỳ vọng **0 hàng**. Nếu lấy node theo **accountNo** mà không kèm **orgId**, tenant shop-a có thể bị nối nhầm tới đơn của shop-b.

Đối với mỗi Order, kiểm tra số quan hệ đặt hàng hợp lệ:

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
OPTIONAL MATCH (c:DemoMigLegacyCustomer)
  -[r:DEMO_MIG_PURCHASED]->(o)
WITH o, count(r) AS incoming
WHERE incoming <> 1
RETURN o.orgId AS tenantId, o.purchaseNo AS orderId, incoming;
~~~

Trong ví dụ, mỗi Order có **đúng một** Customer đặt. Nếu domain cho phép nhiều nguồn đặt hoặc nhiều sự kiện cho một Order, **không dùng** quy tắc “một quan hệ cho mỗi cặp” của ví dụ; cần thiết kế một mô hình sự kiện có **eventId** riêng.

### 5.4. Kiểm tra property, kiểu và trạng thái trước mapping

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
WHERE o.totalCents IS NULL
   OR o.totalCents < 0
   OR o.orderState IS NULL
   OR NOT o.orderState IN ['PAID', 'CREATED']
RETURN o.orgId AS tenantId, o.purchaseNo AS orderId,
       o.totalCents AS amount, o.orderState AS state;
~~~

Đoạn này kiểm tra thiếu tiền, giá trị âm và trạng thái ngoài bảng mapping. Trong dữ liệu thật phải xác minh thêm **kiểu INTEGER**, đơn vị tiền, trường hợp trả tiền/hoàn tiền âm theo domain và tính hợp lệ của ngày giờ.

**Không biến trạng thái không nhận diện được thành PAID/NEW tùy tiện.** Nếu gặp giá trị **REFUNDED**, **CANCELLED** hoặc **PENDING**, cần bổ sung mapping đã được nghiệp vụ phê duyệt trước khi chạy migration.

### 5.5. Kiểm tra va chạm với model đích đã tồn tại

Nếu database đã có node đích do một deployment thử nghiệm trước đó tạo:

~~~cypher
MATCH (old:DemoMigLegacyCustomer)
MATCH (other:DemoMigCustomer {
  tenantId: old.orgId,
  customerId: old.accountNo
})
WHERE old <> other
RETURN old.orgId AS tenantId, old.accountNo AS customerId,
       count(other) AS conflictingNodes;
~~~

Các hàng được trả là **xung đột identity**: hai node vật lý cùng đại diện một business key. Không tự động dùng **MERGE** để tạo node thứ ba, không xóa một bên khi chưa xác định property và relationship nào đang tham chiếu nó. Phải quyết định giữ node nào và chuyển toàn bộ liên kết bằng quy trình merge dữ liệu được kiểm chứng.

## 6. Chọn chiến lược: di trú tại chỗ hay tạo node mới?

### 6.1. Di trú tại chỗ — phù hợp khi chỉ đổi cách biểu diễn

Nếu thực thể **Customer vẫn là cùng Customer**, chỉ đổi label và tên property, phương pháp đơn giản và ít rủi ro thường là:

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WHERE c.orgId IS NOT NULL AND c.accountNo IS NOT NULL
SET c.tenantId = coalesce(c.tenantId, c.orgId),
    c.customerId = coalesce(c.customerId, c.accountNo),
    c.displayName = coalesce(c.displayName, c.fullName)
SET c:DemoMigCustomer;
~~~

Ở đây:

- **SET c:DemoMigCustomer** thêm nhãn mới, **không** tạo node.
- Các property mới được backfill từ property cũ **khi đích còn null**.
- Nhãn/thuộc tính cũ vẫn tồn tại để ứng dụng cũ tiếp tục đọc trong giai đoạn chuyển tiếp.
- Cặp **(tenantId, customerId)** vẫn là định danh nghiệp vụ từ **(orgId, accountNo)**, không được thay bằng ID ngẫu nhiên.

**Điều kiện trước khi chạy:** các truy vấn preflight đã PASS, không có xung đột target identity, không có property đích khác giá trị nguồn do lỗi di trú trước. Nếu node đã có **c.customerId** nhưng mang mã sai, **coalesce** sẽ giữ mã sai; bước kiểm tra lệch dữ liệu phải phát hiện điều này, không coi sự kiện query chạy thành công là PASS.

### 6.2. Khi nào phải tạo node mới?

Cần cân nhắc tạo node mới khi **bản chất domain đổi**, ví dụ:

- Một **LegacyAccount** được tách thành **Person** và **Organization**.
- Hai node nguồn được hợp nhất thành một Customer canonical.
- Quan hệ nhiều–nhiều được nâng thành **PurchaseEvent** có trạng thái/vòng đời riêng.
- Dữ liệu di chuyển sang một database hoặc cụm độc lập, không thể giữ node vật lý.

Khi đó mới dùng **MERGE (target:NewLabel {businessKey: ...})** với uniqueness constraint phù hợp, sao chép dữ liệu, tái gắn relationship và đối soát ánh xạ một–một hoặc nhiều–một. Không giả định **elementId** của node mới trùng với node cũ.

**Quy tắc:** thay đổi presentation/schema không mặc nhiên đòi tạo thực thể mới. Tạo node mới thiếu một chiến lược chuyển liên kết dễ dẫn đến “hai nguồn sự thật” trong graph.

## 7. Di trú thuộc tính Customer và Order đúng kiểu

### 7.1. Backfill Customer không ghi đè cập nhật mới

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WHERE c.orgId IS NOT NULL AND c.accountNo IS NOT NULL
SET c.tenantId = coalesce(c.tenantId, c.orgId),
    c.customerId = coalesce(c.customerId, c.accountNo),
    c.displayName = coalesce(c.displayName, c.fullName)
SET c:DemoMigCustomer
RETURN count(c) AS migratedCustomers;
~~~

Với fixture, kết quả **2**. Chạy lại không tạo thêm Customer. Nếu phiên bản ứng dụng mới đã đổi **displayName**, truy vấn không đặt lại từ **fullName**.

Đây chỉ là ví dụ **backfill giá trị null**. Nếu nhu cầu thật phân biệt **chuỗi rỗng** và **NULL**, phải chuẩn hóa và quyết định rõ: chuỗi rỗng có được xem như thiếu dữ liệu hay là giá trị cần giữ? Không dùng **coalesce** để sửa mọi trường hợp thiếu/không hợp lệ.

### 7.2. Backfill Order với mapping trạng thái tường minh

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
WHERE o.orgId IS NOT NULL
  AND o.purchaseNo IS NOT NULL
  AND o.totalCents IS NOT NULL
  AND o.orderState IN ['PAID', 'CREATED']
SET o.tenantId = coalesce(o.tenantId, o.orgId),
    o.orderId = coalesce(o.orderId, o.purchaseNo),
    o.amountMinor = coalesce(o.amountMinor, o.totalCents),
    o.status = coalesce(
      o.status,
      CASE o.orderState
        WHEN 'PAID' THEN 'PAID'
        WHEN 'CREATED' THEN 'NEW'
      END
    )
SET o:DemoMigOrder
RETURN count(o) AS migratedOrders;
~~~

Với fixture, **migratedOrders = 3**:

| tenantId | orderId | amountMinor | status |
|---|---|---:|---|
| shop-a | P-101 | 120000 | PAID |
| shop-a | P-102 | 69000 | NEW |
| shop-b | P-101 | 27000 | NEW |

**Giữ nguyên đơn vị:** **totalCents → amountMinor** trong ví dụ là **INTEGER → INTEGER** và cùng đơn vị nhỏ nhất, nên không cần qua FLOAT. Nếu mô hình mới lưu đơn vị khác (ví dụ tiền chính thay cho cent), phải định nghĩa công thức, làm tròn, tiền tệ, giới hạn và test chính xác. Không suy đoán đơn vị chỉ từ tên property.

**Chạy lại an toàn:** một Order có **status** mới được cập nhật sau migration sẽ không bị trả về NEW khi chạy lại câu backfill. Nếu nghiệp vụ muốn đồng bộ trạng thái hai chiều trong giai đoạn dual-write, phải có một quy tắc source-of-truth riêng, không dựa vào một lệnh **coalesce** đơn lẻ.

### 7.3. Không thay toàn bộ map khi chỉ cần đổi vài property

Cypher hỗ trợ:

~~~cypher
// Không dùng cho migration này nếu không có bản đồ đủ mọi property.
MATCH (o:DemoMigOrder {tenantId: 'shop-a', orderId: 'P-101'})
SET o = {tenantId: 'shop-a', orderId: 'P-101'};
~~~

**SET o = {...}** thay **toàn bộ** property map của node, nên các property không liệt kê sẽ bị xóa. Ví dụ đó sẽ xóa **amountMinor** và **status** và có thể làm hỏng dữ liệu. Đoạn trên được đưa vào **để cảnh báo, không chạy**.

Khi chỉ backfill một vài trường, dùng **SET o.property = ...**. Nếu thực sự cần trộn thêm map, **SET o += {...}** giữ các property không được đề cập, nhưng vẫn cần xem xét null/ghi đè theo hợp đồng dữ liệu.

### 7.4. Kiểm tra lệch property mới và cũ

Sau backfill, tìm những bản ghi khác identity:

~~~cypher
MATCH (c:DemoMigLegacyCustomer:DemoMigCustomer)
WHERE c.tenantId IS NULL
   OR c.customerId IS NULL
   OR c.tenantId <> c.orgId
   OR c.customerId <> c.accountNo
RETURN c.orgId AS orgId, c.accountNo AS accountNo,
       c.tenantId AS tenantId, c.customerId AS customerId;
~~~

~~~cypher
MATCH (o:DemoMigLegacyPurchase:DemoMigOrder)
WHERE o.tenantId IS NULL
   OR o.orderId IS NULL
   OR o.tenantId <> o.orgId
   OR o.orderId <> o.purchaseNo
RETURN o.orgId AS oldTenant, o.purchaseNo AS oldOrderId,
       o.tenantId AS newTenant, o.orderId AS newOrderId;
~~~

Cả hai phải trả **0 hàng**. Những sai khác tên hiển thị hoặc trạng thái có thể hợp lệ khi ứng dụng đã dual-write và cho phép cập nhật mới; vì thế cần xác minh bằng **quy tắc phiên bản dữ liệu/timestamp và source-of-truth**, không so bằng nhau một cách máy móc với mọi property.

## 8. Di trú relationship type, hướng và thuộc tính

### 8.1. Không có phép SET để đổi type trực tiếp của relationship

Trong Cypher, một relationship có **một type**. **SET r:NEW_TYPE** không phải cú pháp tương đương với việc đổi nhãn node. Để đổi **DEMO_MIG_PURCHASED → DEMO_MIG_PLACED**, tạo relationship mới giữa các endpoint đã xác định, kiểm tra dữ liệu, sau đó mới xóa relationship cũ.

**Điều kiện nghiệp vụ của ví dụ:** mỗi Order có đúng **một** sự kiện đặt hàng nối với **một** Customer. Nếu cùng một cặp node có nhiều sự kiện khác nhau, dùng **event node/relationship có khóa sự kiện** và schema tương ứng; không gộp chúng vào một cạnh chỉ vì endpoint giống nhau.

### 8.2. Preflight đặc biệt cho source relationship

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase)
WITH c, o, count(old) AS copies
WHERE copies <> 1
RETURN c.orgId AS tenantId,
       c.accountNo AS customerId,
       o.purchaseNo AS orderId, copies;
~~~

Kết quả kỳ vọng **0 hàng**: không có hai cạnh cũ giữa cùng cặp node. Kiểm tra ID sự kiện thiếu:

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase)
WHERE trim(coalesce(old.sourceEventId, '')) = ''
   OR old.createdAt IS NULL
RETURN c.accountNo AS customerId,
       o.purchaseNo AS orderId,
       old.sourceEventId AS eventId;
~~~

Nếu event ID không unique hoặc nhiều event đi qua cùng cặp node, phải giải quyết theo model đúng. Không dùng **MERGE (c)-[:PLACED]->(o)** để vô tình làm mất nhiều event khác nhau.

### 8.3. Tạo relationship mới theo endpoint đã bind

Sau khi cả node Customer và Order đã có nhãn đích:

~~~cypher
MATCH (c:DemoMigLegacyCustomer:DemoMigCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase:DemoMigOrder)
WHERE c.orgId = o.orgId
  AND old.sourceEventId IS NOT NULL
MERGE (c)-[fresh:DEMO_MIG_PLACED]->(o)
ON CREATE SET
  fresh.eventId = old.sourceEventId,
  fresh.occurredAt = old.createdAt
RETURN count(fresh) AS processedRelationships;
~~~

Với fixture, kết quả **3**. Tại thời điểm này, trong cùng graph có thể đồng thời tồn tại **hai type relationship**, nhưng chúng cùng nối tới những node nguồn/đích.

**Vì sao bind endpoint trước MERGE?** Hai node c và o đã được MATCH. MERGE chỉ kiểm tra/tạo **relationship** giữa đúng hai node đó, tránh vô tình tạo Customer/Order mới khi một mẫu dài không khớp.

**Vì sao ON CREATE SET?** Chỉ sao chép metadata khi tạo cạnh mới; chạy lại không tự ghi đè **occurredAt** của cạnh mới. Với trường hợp cạnh đích đã tồn tại nhưng metadata khác, migration **không âm thầm sửa nó** mà để truy vấn validation bên dưới phát hiện.

### 8.4. Kiểm tra metadata relationship

~~~cypher
MATCH (c:DemoMigLegacyCustomer:DemoMigCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase:DemoMigOrder)
OPTIONAL MATCH (c)-[fresh:DEMO_MIG_PLACED]->(o)
WITH c, o, old,
     count(fresh) AS freshCount,
     collect(fresh.eventId) AS eventIds,
     collect(fresh.occurredAt) AS eventTimes
WHERE freshCount <> 1
   OR NOT old.sourceEventId IN eventIds
   OR NOT old.createdAt IN eventTimes
RETURN c.tenantId AS tenantId,
       c.customerId AS customerId,
       o.orderId AS orderId,
       old.sourceEventId AS oldEvent,
       freshCount, eventIds, eventTimes;
~~~

Kỳ vọng **0 hàng**. Vì sử dụng **collect** nên mỗi đầu–cuối có thể có nhiều cạnh đích; **freshCount <> 1** sẽ phát hiện quan hệ thừa hoặc thiếu. Trong production, nên đối soát thêm **eventId** trên toàn tenant, schema uniqueness của event nếu hỗ trợ, và số lượng relationship theo type.

**Đừng xóa cạnh cũ ngay sau MERGE**. Mô hình mới phải được kiểm tra trước và tất cả consumer còn dùng **DEMO_MIG_PURCHASED** phải có đường chuyển đổi đã thống nhất.

### 8.5. Nếu cần đảo chiều quan hệ

Một thay đổi mô hình có thể muốn từ **(Order)-[:PLACED_BY]->(Customer)** thay vì **(Customer)-[:PLACED]->(Order)**. Khi đó bắt buộc viết rõ:

~~~cypher
MATCH (c:DemoMigCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigOrder)
MERGE (o)-[r:DEMO_MIG_PLACED_BY]->(c)
ON CREATE SET r.eventId = old.sourceEventId;
~~~

Đây là **phương án khác**, không chạy song song với phương án mục 8.3 rồi coi ba loại cạnh như cùng một schema. Cần chọn **một hướng đích** và kiểm tra mọi truy vấn dùng mũi tên **-> / <-** trong Java Driver/SDN.

## 9. Migration quy mô lớn: batch, checkpoint và tính lặp lại

### 9.1. Vì sao không cập nhật hàng triệu node trong một transaction?

Một transaction quá lớn có thể tăng áp lực bộ nhớ, khóa, transaction log, thời gian commit và rủi ro rollback khi có một bản ghi lỗi. Neo4j hỗ trợ **CALL { ... } IN TRANSACTIONS** để chia đầu vào thành các nhóm transaction.

Đối với Neo4j hỗ trợ **variable scope clause** (Neo4j 5.23+), ví dụ batch Customer:

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WHERE c.orgId IS NOT NULL
  AND c.accountNo IS NOT NULL
CALL (c) {
  SET c.tenantId = coalesce(c.tenantId, c.orgId),
      c.customerId = coalesce(c.customerId, c.accountNo),
      c.displayName = coalesce(c.displayName, c.fullName)
  SET c:DemoMigCustomer
} IN TRANSACTIONS OF 1000 ROWS;
~~~

**Điều kiện quan trọng:** câu có **IN TRANSACTIONS** phải chạy trong **implicit transaction**. Trong Neo4j Browser, dùng **:auto**; trong Java Driver dùng **session.run(...)** và chờ consume kết quả. Không bọc lệnh vào **executeWrite(...)**, explicit transaction hay **@Transactional** do Spring quản lý, vì những ngữ cảnh đó không chấp nhận kiểu chia inner transaction này.

Với các bản Cypher cũ chưa có variable scope clause, dùng importing **WITH** theo hướng dẫn phiên bản; đừng tự thay cú pháp trước khi xác định server hỗ trợ.

### 9.2. Transaction đã commit trước lỗi sẽ được giữ lại

Nếu batch đầu đã commit 1.000 Customer và batch hai gặp giá trị vi phạm constraint, Neo4j **không tự rollback batch đầu**. Do đó:

1. Preflight phải phát hiện dữ liệu xấu trước khi ghi.
2. Mỗi bước backfill phải có khả năng **chạy lại** mà không tạo trùng.
3. Lưu số hàng đọc, đã cập nhật, lỗi, bị bỏ qua và checkpoint ứng dụng/manifest.
4. Ghi lại những batch thành công để tiếp tục từ điểm hợp lý, nhưng đừng dựa vào **SKIP/LIMIT** thiếu thứ tự ổn định khi dữ liệu nguồn còn thay đổi.
5. Sau khi chạy lại, **đối soát toàn bộ tập nguồn–đích**, không chỉ nhìn log của batch cuối.

Không mặc định **IN CONCURRENT TRANSACTIONS** luôn nhanh hơn. Các batch sửa những node/relationship có chung endpoint có thể tạo **tranh chấp khóa hoặc deadlock**; cần thử trên workload thật, đặc biệt ở bước tạo relationship.

### 9.3. Chỉ dùng LIMIT khi có chiến lược phân trang đúng

Một câu:

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WITH c LIMIT 1000
SET c:DemoMigCustomer;
~~~

**Không phải** chiến lược phân trang an toàn nếu cứ chạy lại mà không lọc phần đã xử lý: truy vấn có thể cứ chọn những node đầu tiên và bỏ qua các node khác. Khi cần xử lý theo lô, dùng **CALL ... IN TRANSACTIONS** hoặc chiến lược đánh dấu trạng thái và khóa ổn định được thiết kế riêng.

## 10. Deploy không dừng ghi: expand → migrate → verify → switch → contract

Di trú mô hình thường diễn ra trong hệ thống đang phục vụ nhiều phiên bản ứng dụng. Nếu chỉ chạy một script rồi lập tức xóa nhãn cũ, các instance Java/SDN chưa được nâng sẽ lỗi.

~~~mermaid
flowchart LR
  A["1. Expand schema & compatibility"] --> B["2. Dual-write / bảo đảm dữ liệu mới"]
  B --> C["3. Backfill node & relationship"]
  C --> D["4. Verify & reconcile"]
  D --> E["5. Switch readers và API"]
  E --> F["6. Contract: xóa legacy có kiểm soát"]
~~~

### 10.1. Expand — cho phép cả hai model tồn tại

- Tạo constraint/index đích trước.
- Mở code ứng dụng biết đọc được **cả legacy và model mới** khi cần.
- Không xóa property/label cũ nếu còn reader đang dùng chúng.
- Xác định business key bất biến được **cả hai phiên bản** dùng chung.
- Chốt phiên bản Neo4j/Java Driver/SDN/APOC/GDS nếu những thành phần đó có ảnh hưởng tới migration.

**Không chuyển toàn bộ query sang label mới** khi dữ liệu đích mới chỉ được tạo cho một phần node.

### 10.2. Bảo đảm các write mới không bị mất trong lúc backfill

Nếu ứng dụng vẫn nhận đơn trong lúc script chạy, có thể xảy ra:

~~~text
T1: Migration backfill Order P-101
T2: Ứng dụng cũ tạo Order P-103 chỉ với nhãn LegacyPurchase
T3: Migration báo hoàn tất vì đã đọc các hàng trước T2
T4: Ứng dụng mới chỉ MATCH :DemoMigOrder -> không thấy P-103
~~~

Hai lựa chọn phổ biến:

1. **Dừng/đóng băng ghi có kế hoạch** trong cửa sổ migration khi downtime được phép.
2. **Dual-write giao dịch** hoặc một luồng thay đổi **CDC/queue có checkpoint** để bảo đảm mọi ghi sau mốc bắt đầu backfill cũng xuất hiện ở model đích.

Với dual-write trong **cùng database**, một giao dịch Neo4j có thể cập nhật **cả property/label cũ và mới** trước khi commit; ứng dụng mới thấy hai biểu diễn cùng lúc. Nếu hai model được duy trì qua các service hoặc database độc lập, cần cơ chế đồng bộ với event ID, retry/idempotency và xác nhận tiến độ; không giả định transaction của Neo4j tự bao trùm những hệ thống khác.

**Bẫy quan trọng:** lệnh backfill dùng **coalesce** sẽ không tự sửa trường hợp nguồn cũ được cập nhật sau khi thuộc tính đích đã có giá trị. Trong giai đoạn dual-write, phải có một source-of-truth và quy tắc cập nhật rõ ràng; hoặc áp dụng các thay đổi mới qua luồng đồng bộ đáng tin cậy trước khi hoàn tất cutover.

### 10.3. Verify — chứng minh cả hai model trả cùng ý nghĩa

Một bài migration không PASS chỉ vì số node đã cập nhật khớp số node nguồn. Cần:

- So sánh **tập business key** nguồn–đích, bao gồm tenant.
- So danh sách Order theo Customer và ngược lại.
- Kiểm tra relationship cùng hướng, đúng type, đủ metadata.
- Kiểm tra property/kiểu tiền, status và ngày giờ.
- Đảm bảo các khóa thiếu, trùng, quan hệ xuyên tenant bằng **0**.
- Kiểm tra những ghi đã xảy ra **sau khi backfill bắt đầu** đều có mặt ở model mới.
- Chạy migration lần hai trên staging để kiểm tra tính lặp lại.

### 10.4. Switch — chuyển traffic theo từng giai đoạn

Ứng dụng mới có thể:

1. Đọc một số request từ schema mới và so sánh ngầm với schema cũ (*shadow read*) trên staging/canary.
2. Chuyển **5% → 25% → 100%** lưu lượng nếu các mức này phù hợp hạ tầng.
3. Theo dõi p95 query, DB Hits, kết quả bất biến và lỗi mapping SDN.
4. Ngừng dùng property/label legacy trong ứng dụng sau khi tất cả instance đã cập nhật.

**Không dựa vào tỉ lệ traffic duy nhất**: một worker chạy lịch hằng đêm hoặc connector chưa nâng cấp vẫn có thể đọc schema cũ dù không tham gia đường API chính.

### 10.5. Contract — dọn cấu trúc cũ sau khi có bằng chứng

Chỉ bắt đầu xóa relationship type, property hoặc label cũ khi:

- Mọi writer đã ngừng ghi schema legacy.
- Mọi reader/consumer/report/ETL đã chuyển sang model mới.
- Data reconciliation PASS và có giám sát trong một cửa sổ đủ dài.
- Backup và phương án restore/migration bù đã được thử.
- Người chịu trách nhiệm dữ liệu chấp thuận xóa, nhất là khi có thông tin lịch sử cần lưu.

Contract thường là bước **khó rollback nhất**, do nó xóa đường truy vấn cũ và có thể xóa dữ liệu không có ở schema mới.

## 11. Kiểm thử Cypher trước khi xóa schema cũ

### 11.1. So kết quả nghiệp vụ của truy vấn cũ và mới

Truy vấn cũ:

~~~cypher
MATCH (c:DemoMigLegacyCustomer {
  orgId: $tenantId,
  accountNo: $customerId
})-[:DEMO_MIG_PURCHASED]->(o:DemoMigLegacyPurchase)
RETURN o.purchaseNo AS orderId
ORDER BY orderId;
~~~

Truy vấn mới:

~~~cypher
MATCH (c:DemoMigCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})-[:DEMO_MIG_PLACED]->(o:DemoMigOrder)
WHERE o.tenantId = $tenantId
RETURN o.orderId AS orderId
ORDER BY orderId;
~~~

Với **shop-a/C-1**, cả hai phải trả **[P-101, P-102]**. Với **shop-b/C-1**, cả hai phải trả **[P-101]** của shop-b. Nếu chỉ kiểm tra tên Order **P-101** mà không so tenant, lỗi nối nhầm có thể lọt qua.

**Cypher không tự bảo đảm thứ tự kết quả nếu thiếu ORDER BY.** Khi viết test so list, phải dùng ORDER BY hoặc so tập hợp không phụ thuộc thứ tự.

### 11.2. Kiểm tra tỷ lệ phủ nhãn mới

~~~cypher
MATCH (c:DemoMigLegacyCustomer)
WHERE NOT c:DemoMigCustomer
   OR c.tenantId IS NULL
   OR c.customerId IS NULL
RETURN count(c) AS unmigratedCustomers;
~~~

~~~cypher
MATCH (o:DemoMigLegacyPurchase)
WHERE NOT o:DemoMigOrder
   OR o.tenantId IS NULL
   OR o.orderId IS NULL
RETURN count(o) AS unmigratedOrders;
~~~

Kỳ vọng **0**, nhưng vẫn cần kiểm tra giá trị có **đúng** không, không chỉ có mặt.

### 11.3. Kiểm tra số lượng và tính duy nhất

~~~cypher
MATCH (c:DemoMigCustomer)
WITH c.tenantId AS tenantId, c.customerId AS customerId,
     count(*) AS copies
WHERE copies > 1
RETURN tenantId, customerId, copies;
~~~

~~~cypher
MATCH (o:DemoMigOrder)
WITH o.tenantId AS tenantId, o.orderId AS orderId,
     count(*) AS copies
WHERE copies > 1
RETURN tenantId, orderId, copies;
~~~

Cả hai phải **không trả hàng**. Trên fixture cố định, số Customer **2**, Order **3**, quan hệ cũ **3** và quan hệ mới **3** sau khi migration xong. Trong production đang ghi, tổng số node/relationship có thể đổi trong lúc truy vấn; cần so cùng **mốc dữ liệu hoặc watermark** thay vì snapshot lệch thời gian.

### 11.4. Kiểm tra relationship thiếu, thừa hoặc sai tenant

~~~cypher
MATCH (o:DemoMigOrder)
OPTIONAL MATCH (c:DemoMigCustomer)-[r:DEMO_MIG_PLACED]->(o)
WITH o, count(r) AS incoming
WHERE incoming <> 1
RETURN o.tenantId AS tenantId,
       o.orderId AS orderId, incoming;
~~~

~~~cypher
MATCH (c:DemoMigCustomer)-[r:DEMO_MIG_PLACED]->
      (o:DemoMigOrder)
WHERE c.tenantId IS NULL
   OR o.tenantId IS NULL
   OR c.tenantId <> o.tenantId
RETURN c.customerId AS customerId,
       o.orderId AS orderId, type(r) AS relationshipType;
~~~

Kỳ vọng cả hai **0 hàng**. Đây là invariant của domain minh họa; nếu một Order có nhiều Customer hợp lệ, phải sửa điều kiện chứ không ép dữ liệu thực về mẫu bài tập.

### 11.5. Kiểm tra schema và kế hoạch truy vấn

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name STARTS WITH 'demo_mig_'
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

~~~cypher
SHOW INDEXES
YIELD name, state, type, labelsOrTypes, properties
RETURN name, state, type, labelsOrTypes, properties
ORDER BY name;
~~~

Khi thêm uniqueness constraint, Neo4j tạo index hỗ trợ. Với những index quan trọng vừa tạo, đợi trạng thái **ONLINE** rồi mới kết luận query mới đủ điều kiện phục vụ tải. Index **POPULATING** hoặc **FAILED** chưa đạt gate.

~~~cypher
EXPLAIN
MATCH (o:DemoMigOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN o.status AS status;
~~~

**EXPLAIN** chỉ tạo kế hoạch, không chạy truy vấn. **PROFILE** chạy thật, nên chỉ profile truy vấn đọc an toàn ở production, và so **Rows, DB Hits, index seek, latency** với baseline; đừng buộc tên toán tử giống hệt giữa các phiên bản Neo4j.

## 12. Java Driver và Spring Data Neo4j trong giai đoạn chuyển đổi

### 12.1. API phải giữ nguyên business key

Nếu API trước migration trả:

~~~json
{
  "tenantId": "shop-a",
  "customerId": "C-1",
  "orders": ["P-101", "P-102"]
}
~~~

thì API sau migration vẫn phải trả cùng mã khách và đơn theo hợp đồng, dù câu Cypher nội bộ đã đổi nhãn và type relationship. **Không đổi contract thành ID nội bộ của Neo4j** chỉ vì đó là giá trị tiện lấy qua Java Driver.

### 12.2. Truy vấn Java Driver giữ param theo business key

~~~java
import java.util.List;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;

public final class DemoMigratedQuery {

    public static List<String> findOrders(
            Driver driver,
            String database,
            String tenantId,
            String customerId) {

        try (var session = driver.session(
                SessionConfig.forDatabase(database))) {
            return session.executeRead(tx ->
                tx.run("""
                    MATCH (c:DemoMigCustomer {
                      tenantId: $tenantId,
                      customerId: $customerId
                    })-[:DEMO_MIG_PLACED]->(o:DemoMigOrder)
                    WHERE o.tenantId = $tenantId
                    RETURN o.orderId AS orderId
                    ORDER BY orderId
                    """, Map.of(
                        "tenantId", tenantId,
                        "customerId", customerId
                    ))
                  .list(record -> record.get("orderId").asString())
            );
        }
    }
}
~~~

Kỳ vọng **findOrders(driver, dbName, "shop-a", "C-1")** trả **["P-101", "P-102"]** trên fixture. Query chỉ đọc được chạy bằng **executeRead**; Driver được quản lý vòng đời ở tầng ứng dụng, còn Session được đóng sau công việc.

Nếu sau một transaction ghi, ứng dụng phải đọc ngay dữ liệu vừa tạo trên **reader của cluster**, chú ý **bookmarks** để bảo đảm **read-your-writes**. Việc liên kết nhân quả không thay thế kiểm tra migration, nhưng tránh chẩn đoán nhầm replica lag là mất dữ liệu.

### 12.3. Spring Data Neo4j: thay nhãn và type cần cập nhật mapping

Khi thay model, kiểm tra đồng thời:

- **@Node** / nhãn node đích được mapping.
- **@Relationship(type = ..., direction = ...)** có đúng type và chiều mới.
- **@Id** và cách ánh xạ định danh. Nếu business key gồm **tenantId + customerId**, cần thiết kế mapping/custom repository phù hợp; không cho rằng mọi phiên bản SDN tự ghép một composite key từ hai property.
- **@Query** tùy chỉnh vẫn dùng nhãn/thuộc tính cũ hay đã đổi.
- Transaction boundary: các bước dual-write cần nguyên tử trong **một database transaction** nếu hai biểu diễn nằm cùng Neo4j database.
- Repository save có thể cập nhật/xóa relationship khi mapping không khớp; phải kiểm tra trên fixture và cân nhắc dùng **Neo4jClient/custom Cypher** cho migration phức tạp.

Không đặt toàn bộ script **CALL ... IN TRANSACTIONS** dưới **@Transactional** rồi mong batch commit riêng; đây là hai mô hình transaction khác nhau. Spring service bình thường xử lý một nghiệp vụ có thể dùng **@Transactional**, còn migration batch nên có công cụ/job phù hợp.

## 13. Bước contract: dọn legacy chỉ sau khi nghiệm thu

**Các lệnh trong mục này có tính phá hủy** đối với schema cũ. Chỉ dùng trên database test sau khi xác minh:

1. Mọi query mới và invariant đã PASS.
2. Không còn writer/reader phụ thuộc nhãn, property hoặc relationship cũ.
3. Có backup đã kiểm tra restore và có người phụ trách quyết định go/no-go.
4. Đã đối soát dữ liệu ghi mới phát sinh trong giai đoạn chuyển đổi.

### 13.1. Xóa relationship cũ sau khi đã có cạnh thay thế

~~~cypher
MATCH (c:DemoMigLegacyCustomer:DemoMigCustomer)
      -[old:DEMO_MIG_PURCHASED]->
      (o:DemoMigLegacyPurchase:DemoMigOrder)
MATCH (c)-[fresh:DEMO_MIG_PLACED]->(o)
WHERE old.sourceEventId = fresh.eventId
DELETE old;
~~~

Đoạn này chỉ xóa cạnh cũ **khi tìm thấy cạnh đích có eventId tương ứng**, không xóa mù mọi relationship. Tuy nhiên vẫn phải **đối soát toàn bộ trước đó**: nếu còn một số cạnh cũ không có cạnh mới, câu lệnh không xóa chúng, và gate dọn legacy vẫn chưa đạt.

**Không chạy lại phần backfill relationship sau khi đã xóa toàn bộ cạnh cũ** nếu cần bảo đảm provenance; hãy giữ log/checkpoint kiểm tra và quy trình migration có phiên bản.

### 13.2. Xóa nhãn và thuộc tính nguồn ở cuối

~~~cypher
MATCH (c:DemoMigLegacyCustomer:DemoMigCustomer)
REMOVE c:DemoMigLegacyCustomer
REMOVE c.orgId, c.accountNo, c.fullName;
~~~

~~~cypher
MATCH (o:DemoMigLegacyPurchase:DemoMigOrder)
REMOVE o:DemoMigLegacyPurchase
REMOVE o.orgId, o.purchaseNo, o.totalCents, o.orderState;
~~~

**REMOVE label** không xóa node; **REMOVE property** khiến property biến mất. Đây không phải việc tự động “đổi tên property”: trước đó phải đã **sao chép và xác minh** property mới.

Ví dụ, nếu một consumer vẫn MATCH theo **DemoMigLegacyPurchase**, sau lệnh này consumer không còn tìm thấy node, dù node vẫn tồn tại dưới **DemoMigOrder**. Vì vậy, bước contract phải được triển khai **sau** thay đổi code và giai đoạn giám sát.

### 13.3. Dọn constraint/index legacy sau khi xác minh dependency

~~~cypher
DROP CONSTRAINT demo_mig_old_customer_key IF EXISTS;
DROP CONSTRAINT demo_mig_old_purchase_key IF EXISTS;
~~~

Đây là bước **sau cùng**, khi đã xác định schema cũ không còn được sử dụng. Không DROP constraint legacy trước khi các writer cũ ngừng ghi vì có thể làm mất lớp bảo vệ chống trùng ở schema cũ.

**Không** sử dụng **DETACH DELETE** để “đổi nhãn” hoặc “đổi model”; nó xóa node cùng toàn bộ relationship. Với di trú tại chỗ, thao tác đúng là **SET label mới, backfill property, tạo relationship mới, verify, rồi REMOVE/DELETE đúng thành phần cũ**.

## 14. Rollback và phục hồi nếu migration gặp lỗi

| Thời điểm lỗi | Tình huống | Phương án thông thường |
|---|---|---|
| **Trước khi ghi** | Preflight phát hiện ID thiếu/trùng | Dừng, sửa dữ liệu nguồn, chưa triển khai |
| **Sau khi expand** | Mới tạo constraint/index đích | Giữ schema mới vô hại hoặc gỡ theo kế hoạch; ứng dụng cũ vẫn dùng schema cũ |
| **Giữa backfill batch** | Một số batch đã commit, một số lỗi | Sửa nguyên nhân, chạy lại an toàn, đối soát toàn bộ |
| **Sau backfill, trước switch** | Query mới trả sai, schema cũ còn nguyên | Giữ reader cũ, sửa script/mapping rồi verify lại |
| **Sau khi switch, trước contract** | API mới lỗi, schema legacy vẫn còn | Rollback code khi writer/dual-write tương thích; kiểm tra ghi mới và đối soát |
| **Sau contract** | Nhãn/property/cạnh cũ đã xóa | Có thể cần migration bù hoặc **restore backup** đã diễn tập; rollback code đơn thuần không đủ |

Trong môi trường production có batch commit nhiều lần, **không có một transaction đơn lẻ** để rollback toàn bộ migration sau khi các batch đã được commit. Việc hoàn nguyên phải được **thiết kế** chứ không phụ thuộc vào may mắn.

### 14.1. Không đảo ngược mọi dữ liệu mới bằng cách copy property cũ

Ví dụ, sau khi switch, một Order đã được cập nhật từ **NEW → PAID** ở model mới. Nếu rollback một script bằng lệnh **SET o.status = o.orderState** với source legacy còn là CREATED, bạn có thể làm mất sự kiện thanh toán. Do đó:

- Ghi rõ **mốc chuyển source-of-truth**.
- Có version hoặc timestamp cho dữ liệu mới nếu việc hòa giải cần xét “cập nhật nào mới hơn”.
- Tránh dùng câu **SET ... = legacyProperty** vô điều kiện trong quá trình rollback.
- Với tác vụ liên service, có outbox/event ID, checkpoint và cơ chế replay có kiểm soát.

### 14.2. Backup phải gắn với điểm phục hồi

Một bản backup trước migration chỉ hữu ích nếu có thể restore và bạn chấp nhận được khoảng dữ liệu phát sinh từ lúc backup đến khi sự cố được nhận diện. Nếu yêu cầu **RPO gần bằng 0**, cần thiết kế tính liên tục của ghi, chuỗi log/backup và quy trình reconcile riêng. Không giả định chỉ cần có backup là có thể rollback trong vài giây.

## 15. Những sai lầm điển hình

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| Tạo node mới cho Customer khi chỉ đổi label | Hai node cùng một khách hàng | **SET label** trên node hiện có khi domain không đổi |
| Dùng **elementId** làm khóa kết nối qua hệ thống | Khóa không đủ ổn định cho contract nghiệp vụ | Dùng business key, composite tenant scope |
| Chỉ dùng **accountNo** mà không có **orgId** | Nối nhầm hai tenant | Khóa gồm **(tenantId, customerId)** |
| Đưa status/name vào MERGE key | Khi status đổi, MERGE không khớp node cũ | MERGE theo khóa bất biến |
| Thêm nhãn mới nhưng chưa thêm property định danh | Node đích không được tìm bằng query mới | Backfill property cùng bước, verify |
| Dùng SET n = {...} thiếu property | Xóa dữ liệu không được liệt kê | SET từng trường hoặc += có kiểm soát |
| Dùng COALESCE và coi lỗi đã tự sửa | Dữ liệu sai có thể tiếp tục tồn tại | Query đối soát và source-of-truth |
| Đổi type relationship bằng cách xóa cạnh cũ trước | Mất thông tin hướng/metadata/sự kiện | Tạo cạnh mới, verify rồi DELETE cạnh cũ |
| Gộp nhiều event vào một MERGE theo endpoints | Mất lịch sử nhiều lần tương tác | Model Event có khóa **eventId** |
| Chạy batch rồi nghĩ lỗi cuối rollback tất cả | Dữ liệu nửa chuyển đổi | Idempotent batch + checkpoint + đối soát |
| Backfill một lần trong khi writer cũ tiếp tục tạo mới | Thiếu các bản ghi mới tạo | Dual-write/CDC hoặc khóa cửa sổ ghi |
| Chuyển toàn bộ query mới trước khi migration hoàn tất | Query trả thiếu node/relationship | Cutover có gate và canary |
| DROP constraint legacy khi service cũ còn ghi | Có thể tạo trùng dữ liệu nguồn | Chỉ dọn sau contract và kiểm tra consumer |
| Chỉ so node count trước/sau | Đúng count nhưng sai khóa hoặc tenant | So tập business key và quan hệ |
| Rollback code sau khi đã REMOVE legacy | Code cũ không còn dữ liệu để đọc | Thiết kế rollback/restore trước contract |

## 16. Bài tập thực hành

### Bài 1 — Giữ định danh khi đổi nhãn

Chạy fixture ở mục 4. Viết Cypher backfill **DemoMigLegacyCustomer → DemoMigCustomer** mà không tạo node mới. Chứng minh sau khi chạy hai lần vẫn chỉ có **2** Customer logic và business key **shop-a/C-1**, **shop-b/C-1** không đổi.

### Bài 2 — Phân tích lỗi dùng mã không có tenant

Một truy vấn migration tìm Customer bằng **accountNo = 'C-1'** nhưng không dùng **orgId**. Giải thích vì sao nó có thể gắn Order shop-a với Customer shop-b. Viết lại MATCH theo **(orgId, accountNo)** và truy vấn đếm quan hệ xuyên tenant.

### Bài 3 — Kiểm tra mapping trạng thái

Đưa thêm một Order có **orderState = 'REFUNDED'** vào nguồn. Chạy preflight và giải thích vì sao không được tự gán NEW. Thêm quy tắc mapping được domain phê duyệt, sau đó sửa truy vấn backfill và viết assertion kiểm tra từng trạng thái.

### Bài 4 — Đổi relationship mà không mất event

Chuyển ba cạnh **DEMO_MIG_PURCHASED** sang **DEMO_MIG_PLACED**, giữ **sourceEventId → eventId** và **createdAt → occurredAt**. Chạy lại migration lần hai. Dùng truy vấn kiểm tra số cạnh đích, event ID và hướng.

### Bài 5 — Hai sự kiện cùng một cặp node

Giả sử một Customer đặt hai lần cùng Product và hệ thống cần giữ hai event riêng. Vì sao **MERGE (c)-[:BOUGHT]->(p)** không giữ đủ lịch sử? Thiết kế **PurchaseEvent** có eventId duy nhất, nối tới Customer và Product, đồng thời cho phép retry một event không tạo bản sao.

### Bài 6 — Backfill trong hệ thống còn nhận ghi

Migration bắt đầu lúc 10:00, worker cũ tạo Order mới lúc 10:01, còn script quét dữ liệu kết thúc 10:02. Đề xuất cơ chế dual-write, watermark/CDC hoặc cửa sổ đóng băng ghi để chứng minh Order mới không bị thiếu khi chuyển query sang model mới.

### Bài 7 — Rollback sau contract

Ứng dụng đã chuyển sang model mới, các property **orgId/accountNo/purchaseNo** và cạnh cũ đã bị xóa. Một service chưa cập nhật phát sinh lỗi. Giải thích vì sao rollback image đơn thuần chưa đủ; đề xuất rollback dữ liệu, migration bù hoặc restore có giới hạn RPO/RTO.

### Bài 8 — Java Driver và SDN

Viết hàm Java Driver đọc danh sách order theo **tenantId + customerId**, sau đó thiết kế một bài repository/integration test trong Spring Data Neo4j để xác minh **label**, **relationship type**, **direction** và business ID không thay đổi qua migration.

## 17. Tổng kết

**Di trú nhãn, thuộc tính và quan hệ an toàn phải bảo toàn định danh nghiệp vụ, không chỉ bảo toàn số lượng node.**

Với cùng một thực thể, ưu tiên **thêm label mới trên node hiện có**, backfill property bằng quy tắc rõ ràng và duy trì **business key**. Với relationship đổi type, cần **tạo cạnh mới đúng hướng và metadata**, kiểm tra đầy đủ rồi mới xóa cạnh cũ. Nếu nghiệp vụ có nhiều sự kiện trên cùng một cặp node, không gộp chúng bằng một MERGE không có khóa sự kiện.

Quy trình nên áp dụng cho sản phẩm thật:

**Preflight và thống nhất mapping → Backup → Tạo constraint/index đích → Expand/dual-write → Backfill theo batch → So business key và relationship → Switch Java Driver/SDN queries → Canary/monitor → Contract và dọn legacy.**

Hãy dừng rollout khi phát hiện thiếu khóa, xung đột identity, mismatch tenant, dữ liệu bị bỏ sót hoặc index không sẵn sàng. Chỉ xóa cấu trúc legacy sau khi có bằng chứng, và nhớ rằng **rollback mã ứng dụng không tự hoàn tác những transaction migration đã commit**.

### Tài liệu Neo4j chính thức

- [Neo4j Cypher Manual – SET node labels and properties](https://neo4j.com/docs/cypher-manual/current/clauses/set/)
- [Neo4j Cypher Manual – REMOVE properties and labels](https://neo4j.com/docs/cypher-manual/current/clauses/remove/)
- [Neo4j Cypher Manual – MERGE and concurrent relationship merges](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Neo4j Cypher Manual – CREATE CONSTRAINT and composite uniqueness](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher Manual – Constraints and key constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Neo4j Cypher Manual – CALL subqueries in transactions](https://neo4j.com/docs/cypher-manual/current/subqueries/subqueries-in-transactions/)
- [Neo4j Cypher Manual – SHOW CONSTRAINTS](https://neo4j.com/docs/cypher-manual/current/schema/constraints/list-constraints/)
- [Neo4j Cypher Manual – SHOW INDEXES](https://neo4j.com/docs/cypher-manual/current/indexes/performance-indexes/list-indexes/)
- [Neo4j Java Driver Manual – Run transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Bookmarks](https://neo4j.com/docs/java-manual/current/bookmarks/)
- [Spring Data Neo4j Reference](https://docs.spring.io/spring-data/neo4j/reference/)
- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/)
