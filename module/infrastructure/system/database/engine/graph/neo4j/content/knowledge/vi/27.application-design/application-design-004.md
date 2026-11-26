# Định danh ổn định, tính lũy đẳng và kiểm soát trùng lặp yêu cầu

## 1. Vấn đề thực tế: một yêu cầu có thể được gửi nhiều lần

Trong ứng dụng dùng **Neo4j**, một thao tác thường không chỉ ghi một property. Ví dụ, API tạo đơn hàng cần tạo **Order**, nối với **Customer**, lưu trạng thái xử lý và phát sự kiện cho hệ thống thanh toán. Neo4j lưu các thực thể này trong **property graph** gồm node, relationship và property; Java Driver hoặc Spring Data Neo4j là lớp kết nối, còn Cypher thực thi thao tác ghi.

Giả sử ứng dụng nhận yêu cầu **POST /orders**:

1. Client gửi yêu cầu tạo đơn **A**.
2. Neo4j thực thi và **commit thành công**.
3. Kết nối bị ngắt trước khi client nhận phản hồi.
4. Client hoặc gateway gửi lại cùng yêu cầu.

Nếu mỗi lần gọi đều chạy **CREATE** trên một node mới, hệ thống có thể tạo **hai đơn hàng** hoặc gửi hai lần thông báo thanh toán. Đây là vấn đề phổ biến của mạng phân tán: **không nhận được phản hồi không đồng nghĩa giao dịch chưa commit**.

Trong chương **Thiết kế ứng dụng** của module **DATABASE_ENGINE_GRAPH_NEO4J**, ba cơ chế cần được kết hợp:

1. **Định danh ổn định:** cùng thực thể nghiệp vụ phải được nhận diện bằng cùng một khóa qua các lần gọi, import, restart và triển khai.
2. **Tính lũy đẳng (idempotency):** thực hiện lại cùng một yêu cầu hợp lệ không tạo thêm tác động nghiệp vụ.
3. **Kiểm soát trùng lặp:** dùng **constraint**, **transaction**, kiểm tra payload và chính sách retry để chống các yêu cầu tới đồng thời hoặc sau lỗi mạng.

Mục tiêu không phải buộc mạng chỉ gửi một lần; mục tiêu là làm cho **nhiều lần gửi có kết quả nghiệp vụ tương đương một lần xử lý thành công**.

## 2. Phân biệt ba loại định danh

| Loại định danh | Ví dụ | Mục đích | Vòng đời |
|---|---|---|---|
| **Khóa nghiệp vụ (business key)** | **tenantId + orderId**, **customerCode** | Tìm **cùng một thực thể** trong graph | Bền vững theo vòng đời thực thể và quy tắc domain |
| **Idempotency key** | **Idempotency-Key: 5b8...** | Nhận diện **một ý định yêu cầu** có thể được gửi lại | Giữ ít nhất bằng cửa sổ retry có cam kết |
| **Correlation/trace ID** | **trace-8f1...** | Theo dõi một request qua log và nhiều service | Phục vụ quan sát; một retry có thể có trace mới |

**Business key không nhất thiết là idempotency key.** Một khách hàng có thể đặt nhiều đơn; **customerId** không thể dùng làm khóa cho mọi yêu cầu tạo đơn. Ngược lại, một yêu cầu “tạo đơn” có thể chưa biết **orderId** khi client bắt đầu; server phải lưu quan hệ từ **idempotency key** sang đơn đã tạo.

### 2.1. Tránh dùng ID nội bộ Neo4j làm định danh nghiệp vụ

Neo4j có **elementId(n)** và các giá trị nhận dạng nội bộ phục vụ việc tham chiếu graph element trong ngữ cảnh của database. Chúng **không phải hợp đồng định danh bền vững** để phát hành ra API. Một node bị xóa, được nhập lại hoặc khôi phục từ nguồn khác có thể có nhận dạng nội bộ khác; giá trị nội bộ còn có những giới hạn vòng đời mà ứng dụng phải hiểu rõ.

Không lấy **id(n)** (hàm ID nội bộ đời cũ) làm mã khách hàng, mã đơn hoặc khóa trao đổi giữa các service. Thay vào đó:

~~~cypher
CREATE (:DemoAppCustomer {
  tenantId: 'shop-a',
  customerId: 'C-101',
  displayName: 'Nguyễn An'
});
~~~

Ở đây **tenantId + customerId** là định danh do nghiệp vụ quản lý. **C-101** vẫn giữ ý nghĩa khi chuyển dữ liệu giữa hệ thống hoặc khi node được tạo lại với đúng mã. Với khóa không có sẵn từ domain, ứng dụng có thể tạo **UUID/ULID** hoặc mã tương đương, lưu thành property và bảo vệ bằng constraint.

### 2.2. Yêu cầu đối với một business key tốt

- **Ổn định:** không đưa tên hiển thị, trạng thái, địa chỉ email có thể thay đổi vào khóa nếu nghiệp vụ không đảm bảo bất biến.
- **Có phạm vi rõ:** hai tenant có thể cùng có đơn **O-100**, nên khóa duy nhất thường là **(tenantId, orderId)**.
- **Chuẩn hóa nhất quán:** quy tắc trim, chữ hoa/thường, Unicode và định dạng mã phải thống nhất trước khi ghi, đọc, import và tạo index.
- **Không tùy tiện tái sử dụng:** nếu một mã đã gắn với thực thể bị xóa, việc cấp lại mã đó cho thực thể khác có thể khiến các sự kiện cũ bị liên kết nhầm.
- **Không dựa vào dữ liệu nhạy cảm:** tránh dùng email, số điện thoại hay thông tin cá nhân làm định danh công khai khi có thể dùng mã thay thế.

Ví dụ, **shop-a / O-100** và **shop-b / O-100** là hai đơn hợp lệ khác nhau. Nếu constraint chỉ đặt trên **orderId** mà bỏ **tenantId**, mô hình sẽ ngăn nhầm việc hai tenant có mã giống nhau.

## 3. Uniqueness constraint là hàng rào cuối chống tạo trùng node

**MERGE** tìm mẫu trước rồi tạo nếu chưa thấy. Neo4j khuyến nghị đặt **uniqueness constraint** trên thuộc tính định danh vì **MERGE một mình chỉ bảo đảm mẫu tồn tại, không bảo đảm tính duy nhất của node dưới tải ghi đồng thời**.

### 3.1. Tạo constraint trước khi mở API ghi

Các ví dụ tiếp theo dùng database **thử nghiệm**, nhãn **DemoAppOrder**, **DemoAppCustomer** và **DemoAppRequest** để tránh tác động dữ liệu thật:

~~~cypher
CREATE CONSTRAINT demo_app_order_unique IF NOT EXISTS
FOR (o:DemoAppOrder)
REQUIRE (o.tenantId, o.orderId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_app_customer_unique IF NOT EXISTS
FOR (c:DemoAppCustomer)
REQUIRE (c.tenantId, c.customerId) IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT demo_app_request_unique IF NOT EXISTS
FOR (r:DemoAppRequest)
REQUIRE (r.tenantId, r.operation, r.requestKey) IS UNIQUE;
~~~

Mỗi constraint sẽ không cho phép **hai node cùng nhãn** có cùng tổ hợp giá trị thuộc tính được chỉ định. Constraint hỗ trợ việc thực thi **MERGE** và có index đi kèm để tìm các node theo khóa.

**Giới hạn quan trọng:** uniqueness constraint **không bắt buộc mọi node có đủ property**. Một **DemoAppOrder** thiếu **tenantId** hoặc **orderId** chưa bị uniqueness constraint này tự động loại. Ứng dụng phải kiểm tra giá trị bắt buộc trước khi ghi. Nếu cần kết hợp **tồn tại + duy nhất** ở tầng database, xét **node key constraint** trong **Neo4j Enterprise Edition** và khả năng của phiên bản đang chạy.

Tạo constraint trên dữ liệu đã có **trùng khóa** sẽ thất bại. Trước khi triển khai trên graph có sẵn, cần rà soát và hợp nhất hoặc xử lý dữ liệu trùng theo quy trình nghiệp vụ. **IF NOT EXISTS** không chữa dữ liệu trùng và không đảm bảo một constraint khác tên nhưng sai ý nghĩa là tương đương.

### 3.2. Kiểm tra constraint

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
WHERE name STARTS WITH 'demo_app_'
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

Kết quả phải cho thấy cả ba constraint đã tạo thành công trước khi thử các giao dịch đồng thời. Với database có nhiều tenant, đặc biệt kiểm tra composite key đã chứa đúng **tenantId**.

## 4. CREATE, MERGE và ON CREATE/ON MATCH

### 4.1. CREATE luôn tạo node mới nếu constraint cho phép

~~~cypher
CREATE (:DemoAppOrder {
  tenantId: 'shop-a',
  orderId: 'O-100',
  status: 'CREATED'
});
~~~

Chạy lại câu này khi đã có node cùng khóa sẽ **vi phạm constraint**; nếu không có constraint, việc chạy lại có thể tạo node trùng. **CREATE** phù hợp khi chắc chắn đây là thực thể mới và đã có lớp bảo vệ tính duy nhất.

### 4.2. MERGE trên khóa ổn định

~~~cypher
MERGE (o:DemoAppOrder {
  tenantId: 'shop-a',
  orderId: 'O-101'
})
ON CREATE SET
  o.status = 'CREATED',
  o.createdAt = datetime()
RETURN o.orderId AS orderId, o.status AS status;
~~~

Chạy lại câu trên sẽ **khớp node đã có**, không tạo node mới hoặc đặt lại **createdAt**. **ON CREATE SET** chỉ chạy khi tạo mới. Nếu yêu cầu cập nhật có chủ đích, dùng **ON MATCH SET** cho những thuộc tính mà nghiệp vụ cho phép cập nhật lại.

**Sai lầm cần tránh:**

~~~cypher
// Không dùng trạng thái biến đổi làm một phần của khóa MERGE.
MERGE (o:DemoAppOrder {
  tenantId: 'shop-a',
  orderId: 'O-101',
  status: 'CREATED'
});
~~~

Nếu đơn **O-101** đã chuyển thành **PAID**, mẫu có **status: 'CREATED'** không còn khớp. Neo4j sẽ cố tạo một node khác cùng **tenantId + orderId** và có thể bị uniqueness constraint từ chối. Thiết kế đúng là **MERGE theo định danh**, sau đó **SET trạng thái** theo quy tắc nghiệp vụ.

### 4.3. Không dùng MERGE toàn bộ mẫu phức tạp khi endpoint chưa được xác định

Nếu muốn tạo quan hệ giữa Customer và Order, hãy xác định từng node trước:

~~~cypher
MERGE (c:DemoAppCustomer {
  tenantId: 'shop-a',
  customerId: 'C-101'
})
ON CREATE SET c.displayName = 'Nguyễn An'
MERGE (o:DemoAppOrder {
  tenantId: 'shop-a',
  orderId: 'O-101'
})
ON CREATE SET o.status = 'CREATED'
MERGE (c)-[:DEMO_APP_PLACED]->(o);
~~~

**MERGE (c)-[:DEMO_APP_PLACED]->(o)** với hai đầu mút đã được bind có hành vi tìm hoặc tạo relationship; Neo4j dùng khóa phù hợp để xử lý trường hợp nhiều transaction đồng thời cùng merge quan hệ giữa hai node đó. Tuy nhiên, không có constraint tự động cấm mọi quan hệ cùng loại giữa cùng hai node trên toàn graph; các thao tác **CREATE** độc lập hoặc mẫu khác vẫn có thể tạo thêm quan hệ.

Nếu một Customer có thể thực hiện **nhiều lần mua cùng Product**, không mô hình hóa tất cả sự kiện bằng một quan hệ duy nhất **[:BOUGHT]** nếu cần giữ riêng từng lần mua. Hãy dùng **Order/Purchase/Event node có khóa nghiệp vụ riêng**, hoặc relationship mang khóa sự kiện được ràng buộc theo yêu cầu.

## 5. Idempotency: “gọi lại” khác “tạo nghiệp vụ mới”

Một thao tác **f** là lũy đẳng nếu về mặt trạng thái quan sát được:

\[
f(f(x))=f(x)
\]

Tuy nhiên, đối với **HTTP POST**, hai yêu cầu có cùng payload **chưa chắc** là cùng một ý định. Một khách hàng có thể chủ động đặt hai đơn giống hệt nhau. Ngược lại, một lần đặt đơn bị retry với cùng **Idempotency-Key** phải được nhận ra là **cùng một ý định**.

Thiết kế hợp đồng API, ví dụ:

~~~http
POST /v1/orders
Idempotency-Key: 5b8f2f3f-3a4e-4d17-8b0c-72e2c4e02a21
Content-Type: application/json

{"customerId":"C-101","amountMinor":159900,"currency":"VND"}
~~~

Quy tắc hợp lý:

| Trường hợp | Hành vi mong đợi |
|---|---|
| Key mới, payload hợp lệ | Tạo **một** đơn, lưu quan hệ key → orderId, trả kết quả |
| Cùng key, **cùng payload có ý nghĩa** | Trả lại kết quả của cùng đơn; không tạo mới hay phát side effect mới |
| Cùng key, **payload khác** | Từ chối, ví dụ **HTTP 409 Conflict**, không biến key cũ thành yêu cầu mới |
| Key khác, payload giống | Có thể tạo đơn khác vì là **ý định khác**, trừ khi domain có quy tắc dedupe riêng |
| Không có key tại endpoint yêu cầu idempotency | Từ chối trước khi ghi, hoặc áp dụng chính sách API đã công bố |

**Idempotency key** nên được ràng buộc với **tenant** và **loại thao tác/endpoint**, không chỉ là một chuỗi toàn hệ thống. Ví dụ key **K1** trong **shop-a / CREATE_ORDER** khác key **K1** của **shop-b / CREATE_ORDER** hoặc **shop-a / CANCEL_ORDER**.

### 5.1. Fingerprint của payload

Không chỉ kiểm tra key. Nếu client vô tình tái sử dụng key cho hai yêu cầu khác nhau, ứng dụng phải phát hiện xung đột.

Tầng API tính **fingerprint** từ dạng dữ liệu chuẩn hóa (canonical) của **các trường có ý nghĩa nghiệp vụ**: tenant, operation, customerId, amountMinor, currency, danh sách item đã chuẩn hóa... Có thể dùng **SHA-256** trên biểu diễn canonical, hoặc cách khác được thiết kế có kiểm soát.

- Không hash trực tiếp JSON tùy ý nếu thứ tự key, khoảng trắng hoặc chuẩn hóa số làm hai payload tương đương có hash khác nhau.
- Không lấy fingerprint từ **traceId**, timestamp nhận request hoặc access token nếu các trường này thay đổi qua retry.
- Không tin một fingerprint do client tự cung cấp mà không xác thực payload.
- Chuẩn hóa đơn vị tiền, loại tiền, ID, biểu diễn null và thứ tự tập hợp nếu nghiệp vụ coi thứ tự đó không quan trọng.

Fingerprint không thay thế validation. Hai yêu cầu có cùng key nhưng khác dữ liệu quan trọng phải bị từ chối ngay cả khi client khẳng định đây là retry.

## 6. Một giao dịch nguyên tử cho request key và đơn hàng

### 6.1. Tại sao kiểm tra trước bằng hai truy vấn độc lập là sai?

Mẫu rủi ro:

~~~text
T1: MATCH requestKey K -> chưa thấy
T2: MATCH requestKey K -> chưa thấy
T1: CREATE Order O1
T2: CREATE Order O2
~~~

Hai luồng có thể cùng quan sát “chưa có key”, vì **MATCH** chỉ đọc không phải cơ chế đặt chỗ độc quyền. Việc kiểm tra bằng cache hoặc câu **MATCH** riêng rồi mới tạo node ở transaction khác tạo ra **race condition**. Dù client chỉ bấm nút một lần, gateway và worker vẫn có thể gửi hai bản sao.

Giải pháp là **MERGE node yêu cầu** dưới **uniqueness constraint**, xác thực fingerprint, rồi ghi kết quả nghiệp vụ **trong cùng một transaction**. Khi một transaction đầu tiên tạo key đang hoạt động, constraint và cơ chế khóa của Neo4j bảo vệ không thể commit hai node có cùng khóa đã ràng buộc.

### 6.2. Mô hình graph tối thiểu

~~~mermaid
flowchart LR
  R["DemoAppRequest<br/>tenantId, operation, requestKey<br/>fingerprint, orderId"] -.-> O["DemoAppOrder<br/>tenantId, orderId<br/>status, amountMinor"]
  C["DemoAppCustomer<br/>tenantId, customerId"] -->|"DEMO_APP_PLACED"| O
~~~

**DemoAppRequest** là bản ghi theo dõi một lần **ý định API**, còn **DemoAppOrder** là thực thể của domain. Có thể lưu một relationship tham chiếu nếu cần; ví dụ đơn giản chỉ dùng property **orderId** để tra cứu kết quả đã ghi.

Đối với bước ghi trong cùng transaction:

1. **MERGE request guard** bằng khóa **(tenantId, operation, requestKey)**.
2. **ON CREATE SET** fingerprint và **candidateOrderId** lần đầu.
3. Đọc fingerprint đã lưu; nếu khác yêu cầu hiện tại thì **throw** và rollback.
4. **MERGE Order** bằng **(tenantId, orderId)** lấy từ request guard.
5. **ON CREATE SET** trạng thái và dữ liệu ban đầu; không tạo lại side effect khi replay.
6. Commit **cả request guard và Order** cùng nhau.

Nếu transaction lỗi giữa bước 2 và bước 5, cả hai đều rollback. Nếu commit thành công nhưng client không nhận response, lần gọi lại cùng key sẽ tìm được guard và **orderId** cũ.

### 6.3. Ví dụ Java Driver: tạo đơn có thể retry

Đoạn sau minh họa Neo4j Java Driver hiện đại. Giả sử các constraint ở mục 3 đã được tạo; **fingerprint phải do server tính từ payload đã validate**. Đặt tên database đúng với môi trường thử nghiệm.

~~~java
import java.util.Map;
import java.util.UUID;
import org.neo4j.driver.Driver;
import org.neo4j.driver.SessionConfig;

public final class DemoOrderWriter {

    public static String createOrder(
            Driver driver,
            String dbName,
            String tenantId,
            String requestKey,
            String fingerprint,
            String customerId,
            long amountMinor) {

        if (tenantId == null || tenantId.isBlank()
                || requestKey == null || requestKey.isBlank()
                || fingerprint == null || fingerprint.isBlank()
                || customerId == null || customerId.isBlank()
                || amountMinor < 0) {
            throw new IllegalArgumentException("Invalid order request");
        }

        // Tạo một lần cho lời gọi Java này, ngoài callback có thể retry.
        String candidateOrderId = UUID.randomUUID().toString();

        try (var session = driver.session(
                SessionConfig.forDatabase(dbName))) {

            return session.executeWrite(tx -> {
                var gate = tx.run("""
                    MERGE (r:DemoAppRequest {
                      tenantId: $tenantId,
                      operation: 'CREATE_ORDER',
                      requestKey: $requestKey
                    })
                    ON CREATE SET
                      r.fingerprint = $fingerprint,
                      r.orderId = $candidateOrderId,
                      r.createdAt = datetime()
                    RETURN r.fingerprint AS storedFingerprint,
                           r.orderId AS storedOrderId
                    """, Map.of(
                        "tenantId", tenantId,
                        "requestKey", requestKey,
                        "fingerprint", fingerprint,
                        "candidateOrderId", candidateOrderId
                    )).single();

                if (!fingerprint.equals(
                        gate.get("storedFingerprint").asString())) {
                    // Tầng API nên ánh xạ thành HTTP 409 Conflict.
                    throw new IllegalArgumentException(
                        "Idempotency key reused with different payload");
                }

                // Quan trọng: lấy ID đã lưu, không dùng ID mới
                // của lần retry nếu key này đã tồn tại.
                String orderId = gate.get("storedOrderId").asString();

                var order = tx.run("""
                    MERGE (o:DemoAppOrder {
                      tenantId: $tenantId,
                      orderId: $orderId
                    })
                    ON CREATE SET
                      o.customerId = $customerId,
                      o.amountMinor = $amountMinor,
                      o.status = 'CREATED',
                      o.createdAt = datetime()
                    RETURN o.orderId AS orderId
                    """, Map.of(
                        "tenantId", tenantId,
                        "orderId", orderId,
                        "customerId", customerId,
                        "amountMinor", amountMinor
                    )).single();

                return order.get("orderId").asString();
            });
        }
    }
}
~~~

**Giải thích tính lũy đẳng:**

- **requestKey** được ràng buộc duy nhất theo tenant và operation. Hai request đồng thời cùng key không thể commit hai request guard khác nhau.
- **fingerprint** cho phép trả lại kết quả khi payload tương đương và từ chối khi payload thay đổi.
- **r.orderId** được tạo ở **ON CREATE**, nên retry HTTP sau commit vẫn sử dụng ID cũ dù Java tạo một **candidateOrderId** mới.
- **MERGE Order** dưới constraint bảo đảm cùng **orderId** không tạo hai node. **ON CREATE SET** tránh ghi lại **status = CREATED** nếu đơn đã chuyển sang trạng thái khác.
- Hai lệnh Cypher nằm trong **một executeWrite transaction**, nên không có trạng thái “đã lưu key nhưng chưa commit đơn” do lỗi giữa hai lệnh.

**Phạm vi ví dụ:** phương thức trả về **orderId**, chưa cài đặt HTTP controller, xác thực tenant, fingerprint canonical, outbox, nghiệp vụ giỏ hàng hay lưu toàn bộ HTTP response. Sản phẩm thật có thể cần lưu **responseStatus**, **responseBody/responseReference** và timestamp để replay đúng hợp đồng API.

Nếu triển khai tạo Order phải gắn với một Customer đã có, trong **cùng transaction** còn cần **MATCH customer** và xác nhận tồn tại; **không** tự tạo customer rác khi không tìm thấy. Khi có nhiều dòng hàng, tiền, thuế, quan hệ hoặc constraint, tất cả thay đổi bắt buộc phải nhất quán phải cùng thuộc transaction.

### 6.4. Vì sao câu lệnh có uniqueness vẫn có thể trả lỗi?

Uniqueness constraint ngăn **commit dữ liệu trùng**, nhưng không cam kết **mọi client đều thành công ngay từ lần đầu** khi đua tranh ghi. Một transaction có thể phải đợi khóa, bị deadlock hoặc gặp transient error; nếu dữ liệu trùng với một business key khác, constraint có thể trả lỗi cố định. Driver có thể retry lỗi tạm thời, nhưng **constraint violation do dữ liệu thực sự xung đột** cần được giải quyết theo quy tắc nghiệp vụ.

Vì vậy, API cần phân biệt:

- **Cùng key, cùng fingerprint:** replay kết quả cũ.
- **Cùng key, khác fingerprint:** conflict.
- **Business orderId đụng một đơn khác:** xử lý xung đột business key, không tự ghi đè đơn hiện có.
- **Transient error:** retry có giới hạn.
- **Lỗi validate:** trả lỗi đầu vào, không retry mù.

## 7. Retry, commit chưa rõ và ranh giới side effect

### 7.1. Managed transaction có thể chạy callback nhiều lần

**Session.executeWrite(...)** của Java Driver tự retry transaction khi gặp một số lỗi **transient**. Vì callback có thể được gọi lại, mọi hành động trong callback phải an toàn khi thực hiện lại.

**Không đặt các side effect bên ngoài Neo4j** vào callback:

~~~java
// Không áp dụng mẫu này trong production:
session.executeWrite(tx -> {
    tx.run("CREATE (:DemoAppOrder {orderId: $id})", params)
      .consume();
    paymentGateway.charge(card, amount); // Không rollback cùng Neo4j.
    return "ok";
});
~~~

Nếu Neo4j rollback rồi driver retry, **charge** có thể đã xảy ra ở hệ thống thanh toán. Nếu Neo4j commit nhưng phản hồi bị mất, client có thể gửi lại API và gọi **charge** lần nữa. Transaction Neo4j chỉ có ACID trên phạm vi những thay đổi trong database đó.

### 7.2. “Exactly once” ở cấp nghiệp vụ cần thiết kế thêm

Không thể chỉ dựa vào lời hứa “mỗi callback chạy một lần” trên đường truyền có thể mất kết nối. Một cách triển khai phổ biến:

1. Trong transaction tạo Order, đồng thời ghi một **outbox event** với **eventId duy nhất**.
2. Sau commit, một worker đọc các event pending và gửi tới hệ thống ngoài.
3. Worker có thể gửi lại sau timeout, nên bên nhận **cũng phải hỗ trợ idempotency key/eventId**.
4. Worker cập nhật trạng thái giao nhận; log và kiểm soát retry theo giới hạn, dead-letter nếu cần.

Ví dụ một event được sinh từ ID đơn đã xác định (thực hiện trong **cùng transaction** tạo đơn):

~~~cypher
CREATE CONSTRAINT demo_app_outbox_event_unique IF NOT EXISTS
FOR (e:DemoAppOutboxEvent)
REQUIRE e.eventId IS UNIQUE;
~~~

~~~cypher
// Chạy trong transaction đã xác định biến $orderId,
// không phải một transaction rời không liên kết với việc tạo Order.
MERGE (e:DemoAppOutboxEvent {
  eventId: 'ORDER_CREATED:' + $tenantId + ':' + $orderId
})
ON CREATE SET
  e.tenantId = $tenantId,
  e.orderId = $orderId,
  e.eventType = 'ORDER_CREATED',
  e.deliveryState = 'PENDING',
  e.createdAt = datetime()
RETURN e.eventId AS eventId;
~~~

**Quan trọng:** hai câu minh họa trên có mục đích khác nhau: **CREATE CONSTRAINT** là bước **chuẩn bị schema**, còn **MERGE event** phải được đưa vào transaction ghi đơn của ứng dụng. Không chạy lệnh tạo constraint bên trong callback transaction nghiệp vụ.

Ngay cả với outbox, worker có thể gửi event rồi mất kết nối trước khi đánh dấu **SENT**. Vì vậy, **giao nhận lặp lại vẫn có thể xảy ra**; bên thanh toán/thông báo phải dùng **eventId** để chống thực hiện side effect hai lần. Đừng mô tả outbox một mình như bảo đảm “exactly once” trên hai hệ thống độc lập.

### 7.3. Dùng sự kiện thay vì tăng counter lặp lại

Phép cập nhật:

~~~cypher
MATCH (s:DemoAppStatistics {key: 'orders'})
SET s.total = s.total + 1;
~~~

có thể **nguyên tử** trong một transaction, nhưng **không lũy đẳng** nếu cùng một yêu cầu nghiệp vụ chạy lại trong transaction khác: tổng sẽ tăng hai lần. **An toàn dưới ghi đồng thời** và **an toàn khi replay** là hai yêu cầu khác nhau.

Một phương án là lấy **Order** hoặc **OrderCreated event** có khóa duy nhất làm nguồn sự thật rồi tổng hợp; phương án khác là cập nhật counter **chỉ khi một event mới được tạo**, trong cùng transaction có cơ chế xác định nhánh tạo mới. Không dùng **MERGE Event** rồi **SET counter = counter + 1** vô điều kiện, vì lệnh tăng đó vẫn chạy cả khi MERGE chỉ khớp event đã có.

## 8. Idempotency ở tầng relationship: không tạo liên kết trùng

Trong graph, sự trùng lặp có thể nằm ở **node**, **relationship** hoặc cả hai.

### 8.1. Một quan hệ logic giữa hai node đã xác định

~~~cypher
MATCH (c:DemoAppCustomer {
  tenantId: $tenantId,
  customerId: $customerId
})
MATCH (o:DemoAppOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
MERGE (c)-[:DEMO_APP_PLACED]->(o);
~~~

Khi **Customer** và **Order** đã được bind theo khóa riêng, **MERGE relationship** phù hợp với yêu cầu “một Customer **PLACED** một Order”. Neo4j có cơ chế khóa và kiểm tra lại trên hai endpoint khi concurrent relationship MERGE chưa tìm thấy mẫu. Tuy nhiên, vẫn nên kiểm soát phiên bản, dữ liệu trùng có sẵn và các đường ghi khác dùng **CREATE**.

### 8.2. Một cặp node có nhiều sự kiện khác nhau

Với quan hệ **VIEWED** giữa Customer và Product, cùng một người có thể xem cùng một sản phẩm nhiều lần. Nếu nghiệp vụ muốn lưu **từng lượt xem**, không dùng một relationship **[:VIEWED]** duy nhất để nhận diện mọi lượt. Mô hình rõ ràng hơn:

~~~cypher
CREATE CONSTRAINT demo_app_view_event_unique IF NOT EXISTS
FOR (v:DemoAppViewEvent)
REQUIRE (v.tenantId, v.eventId) IS UNIQUE;
~~~

~~~cypher
MERGE (v:DemoAppViewEvent {
  tenantId: $tenantId,
  eventId: $eventId
})
ON CREATE SET
  v.customerId = $customerId,
  v.productId = $productId,
  v.viewedAt = datetime();
~~~

Mỗi **eventId** biểu diễn một lượt xem, nên gửi lại cùng event không tạo node sự kiện mới. **EventId khác** vẫn có thể biểu diễn lượt xem thực sự khác, dù Customer và Product không đổi.

Relationship cũng có thể mang property và một số kiểu **relationship uniqueness/key constraint** trong phiên bản Neo4j hỗ trợ; chọn dựa theo ngữ nghĩa và edition. Không giả định “mỗi loại relationship giữa hai node chỉ được phép có một cạnh” là quy tắc mặc định của Neo4j.

## 9. Phân biệt trùng kỹ thuật với trùng nghiệp vụ

| Trùng lặp | Ví dụ | Cơ chế chính |
|---|---|---|
| **Retry cùng request** | HTTP timeout rồi POST lại với cùng key | Idempotency key + fingerprint + kết quả đã lưu |
| **Hai worker xử lý cùng event** | Broker gửi event E10 hai lần | EventId duy nhất, kiểm soát tiêu thụ |
| **Import chạy lại** | Nhập lại danh sách khách hàng | Business key + constraint + MERGE |
| **Dữ liệu nghiệp vụ thực sự trùng** | Hai customer records khác ID nhưng cùng người | Quy tắc matching/deduplication nghiệp vụ; không thể suy ra chỉ từ request key |
| **Hai thao tác hợp lệ cùng payload** | Khách hàng đặt hai đơn giống nhau | Phải cho phép nếu là hai ý định khác, có key riêng |
| **Hai dịch vụ cùng tạo cùng thực thể** | Sync ERP và API cùng tạo mã khách C-101 | Chuẩn hóa business key, uniqueness constraint, giải quyết dữ liệu xung đột |

Ví dụ **email giống nhau** không tự khẳng định hai hồ sơ khách hàng là cùng một thực thể. Người dùng có thể chia sẻ email hoặc đổi email theo thời gian. Nếu cần hợp nhất bản ghi, hãy định nghĩa **quy tắc identity resolution** riêng, quyền chỉnh sửa và cơ chế audit; không ghép node chỉ vì một trường trùng.

**Trùng kỹ thuật** thường có thể chặn bằng khóa và transaction. **Trùng nghiệp vụ** cần sự định nghĩa của domain, có thể liên quan xác suất, duyệt thủ công hoặc quy trình hợp nhất dữ liệu.

## 10. Spring Data Neo4j: đặt transaction ở đâu?

Với **Spring Data Neo4j**, service method có **@Transactional** có thể bao trùm nhiều thao tác repository và Neo4jClient cùng một giao dịch khi cấu hình transaction manager đúng:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderGraphRepository orders;
    private final RequestGraphRepository requests;

    public OrderApplicationService(OrderGraphRepository orders,
                                   RequestGraphRepository requests) {
        this.orders = orders;
        this.requests = requests;
    }

    @Transactional
    public String createOrder(CreateOrderCommand command) {
        // Minh họa ranh giới transaction.
        // 1. Dùng uniqueness constraint cho idempotency request.
        // 2. Kiểm tra fingerprint của request đã tồn tại.
        // 3. Ghi Order + request result + outbox trong cùng transaction.
        // 4. Trả ID bền vững của Order.
        throw new UnsupportedOperationException(
            "Implement using the domain's repositories");
    }
}
~~~

Đây là **khung ranh giới transaction**, không phải đoạn mã tạo đơn có thể chạy độc lập; nó cần model, repository, mapper và policy retry của dự án. Với nghiệp vụ có tranh chấp request key, có thể dùng **Neo4jClient** hoặc câu Cypher cụ thể để diễn đạt thao tác **MERGE** và nhánh tạo mới rõ ràng, thay vì mặc định **repository.save(...)** tự giải quyết toàn bộ tính lũy đẳng.

**Lưu ý cần tách rõ:**

- **@Transactional** giúp gộp thao tác thành một giao dịch; nó **không tự tạo uniqueness constraint**.
- **@Transactional** **không mặc nhiên tự retry** deadlock hoặc transient error như **Java Driver executeWrite**. Muốn retry ở Spring phải thiết kế sao cho **mỗi lần thử là transaction mới** và kiểm soát số lần thử.
- Entity ID do framework quản lý cần được cấu hình đúng. Đừng lẫn **ID nội bộ của node** với **business key** hoặc **request key**.
- Việc gọi method nội bộ **cùng một bean** có thể không đi qua Spring proxy áp dụng transaction, tùy cách cấu hình.
- Không thực hiện side effect ngoài database trong callback hoặc service transaction có thể bị retry nếu không có cơ chế idempotency thích hợp.

Khi sử dụng Java Driver trực tiếp **bên trong Spring transaction** do SDN quản lý, cần hiểu rõ nó có tham gia cùng transaction hay mở một session/transaction riêng. Đừng tự tạo transaction thứ hai rồi mặc định toàn bộ công việc vẫn nguyên tử.

## 11. Cửa sổ lưu idempotency key và vòng đời kết quả

Lưu idempotency key **mãi mãi** làm tăng dung lượng; xóa quá sớm có thể khiến retry muộn bị xem là yêu cầu mới. Phải định nghĩa rõ **retention window**:

- HTTP client/gateway được retry tối đa bao lâu?
- Broker có thể redeliver event muộn bao lâu?
- Khách hàng có thể khiếu nại hoặc replay một thanh toán sau bao lâu?
- Sau thời hạn, key cũ có được dùng lại không, hay domain vẫn phải ngăn phát sinh trùng?

Ví dụ, nếu hợp đồng API chỉ đảm bảo chống trùng trong **24 giờ**, ghi chính sách đó trong tài liệu API; nhưng với thanh toán hoặc các side effect quan trọng, cần cân nhắc **khóa nghiệp vụ bền vững** và dấu vết đối soát dài hơn. Không làm mất liên kết key → kết quả khi vẫn còn khả năng xảy ra retry được hỗ trợ.

Tách hai vòng đời:

| Dữ liệu | Vai trò | Cách quản lý |
|---|---|---|
| **DemoAppOrder** | Bản ghi nghiệp vụ | Giữ theo chính sách dữ liệu và kiểm toán |
| **DemoAppRequest** | Trạng thái xử lý yêu cầu / replay | Giữ theo SLA idempotency, bảo đảm không xóa khi còn retry hợp lệ |
| **DemoAppOutboxEvent** | Giao nhận sự kiện ra ngoài | Giữ cho tới khi giao nhận/đối soát đã hoàn tất và hết kỳ lưu |
| **Trace/log** | Chẩn đoán một lần gọi mạng | Có thể có thời gian lưu khác với idempotency record |

Nếu phải xóa request guard, cần đảm bảo khách hàng không dùng lại key cũ ngoài chính sách; với hệ thống có rủi ro cao, giữ **tombstone** hoặc ràng buộc business key dài hạn để ngăn tác dụng lặp ngoài ý muốn.

## 12. Quan sát, chẩn đoán và thử nghiệm đối kháng

### 12.1. Kiểm tra số thực thể sau nhiều lần gọi

Sau khi gọi API nhiều lần với cùng key trong môi trường thử nghiệm:

~~~cypher
MATCH (r:DemoAppRequest {
  tenantId: $tenantId,
  operation: 'CREATE_ORDER',
  requestKey: $requestKey
})
RETURN r.fingerprint AS fingerprint, r.orderId AS orderId;
~~~

~~~cypher
MATCH (o:DemoAppOrder {
  tenantId: $tenantId,
  orderId: $orderId
})
RETURN count(o) AS orderCount;
~~~

Kỳ vọng **orderCount = 1**. Với ràng buộc duy nhất đã tạo, không thể có hai node cùng **tenantId + orderId**. Để phát hiện dữ liệu thiếu ID, kiểm tra thêm:

~~~cypher
MATCH (o:DemoAppOrder)
WHERE o.tenantId IS NULL OR o.orderId IS NULL
RETURN count(o) AS missingBusinessIds;
~~~

Kỳ vọng bằng **0** nếu mọi đường tạo node đều tuân thủ validation. Uniqueness constraint đơn thuần không bảo đảm điều này.

### 12.2. Những ca kiểm thử có ý nghĩa

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Gọi lần đầu với key K, payload P | Tạo đúng một đơn, trả ID ổn định |
| Gửi lại K + P sau commit | Trả **cùng orderId**, không thêm đơn hoặc outbox event |
| Gửi lại K + payload Q khác | Conflict; không làm thay đổi đơn cũ |
| Hai request **đồng thời** với K + P | Cuối cùng chỉ một đơn được commit; lỗi tạm thời có thể được retry hợp lệ |
| Hai request với key khác nhau, payload giống | Hai ý định hợp lệ được xử lý theo quy tắc domain |
| Mất phản hồi ngay sau commit | Retry tìm được request guard và trả kết quả đã lưu |
| Lỗi giữa ghi guard và ghi order | Rollback cả hai vì nằm trong một transaction |
| Broker gửi một event hai lần | Chỉ một tác động nghiệp vụ, theo khóa eventId |
| API nhận business ID null/trống | Bị chặn trước MERGE; không tạo node thiếu ID |

Với bài kiểm thử đồng thời, chạy hai hoặc nhiều client có cùng key trong một **database thử nghiệm**, dùng cổng đồng bộ để các yêu cầu thực sự tranh chấp. Sau khi mọi transaction kết thúc, kiểm tra cả **request guard**, **Order** và **outbox event**. Không chỉ dựa vào một phản hồi HTTP để kết luận dữ liệu không trùng.

### 12.3. Các chỉ số cần theo dõi

- Tỷ lệ yêu cầu **new / replay / conflict / invalid** theo endpoint và tenant.
- Số lần retry do transient error, deadlock, timeout hoặc lỗi mất kết nối.
- Số request guard còn ở trạng thái bất thường theo quy trình thực thi (nếu có mô hình trạng thái).
- Số outbox event pending, số lần gửi lại, tỷ lệ xác nhận từ hệ thống ngoài.
- Các lần vi phạm uniqueness constraint trên khóa nghiệp vụ, phân biệt lỗi concurrency với dữ liệu trùng thật.
- p95/p99 transaction ghi và mức contention trên những node hay key được gọi thường xuyên.

Không log toàn bộ payload, thông tin thanh toán hoặc idempotency key không cần thiết. Ưu tiên correlation ID và fingerprint được chuẩn hóa, kiểm soát quyền truy cập log theo chính sách bảo mật.

## 13. Các sai lầm phổ biến

1. **Dùng elementId(node) làm orderId công khai.** Nhận dạng nội bộ không thay cho định danh domain.
2. **Dùng CREATE không có constraint** cho dữ liệu có thể được nhập/gửi lại. Dễ tạo trùng node.
3. **MERGE nhiều property có thể thay đổi** như status, name, lastSeenAt. Khi property đổi, MERGE không khớp thực thể cũ.
4. **Tin rằng MERGE một mình chống trùng dưới tải đồng thời.** Node cần uniqueness/key constraint thích hợp.
5. **Kiểm tra requestKey ở một transaction, ghi Order ở transaction khác.** Tạo khoảng trống cạnh tranh và có thể tạo trạng thái nửa chừng.
6. **Dùng payload hash như ID yêu cầu duy nhất.** Hai đơn chủ động đặt giống nhau vẫn là hai ý định.
7. **Cho cùng key với payload khác tiếp tục chạy.** Có thể trả sai kết quả hoặc thay đổi đơn cũ.
8. **Gán lại trạng thái trong ON MATCH một cách vô điều kiện.** Retry tạo đơn không được đặt một đơn đã thanh toán trở về CREATED.
9. **Đặt side effect ngoài database trong callback có retry.** Thanh toán/email/webhook có thể chạy nhiều lần.
10. **Cho rằng counter tăng nguyên tử là đã idempotent.** Retry nghiệp vụ vẫn có thể làm tăng hai lần.
11. **Dùng một request key toàn cục cho mọi tenant và operation.** Dẫn tới chặn nhầm hoặc liên kết sai yêu cầu.
12. **Xóa idempotency record trước khi hết cửa sổ retry.** Yêu cầu cũ có thể bị xử lý như mới.
13. **Mặc định uniqueness cũng bảo đảm property tồn tại.** Neo4j có phân biệt uniqueness với key/existence constraint.
14. **Không kiểm tra dữ liệu trùng trước khi thêm constraint.** Lệnh tạo schema có thể thất bại trên dữ liệu cũ.

## 14. Bài tập thực hành

### Bài 1 — Chọn khóa ổn định

Một SaaS phục vụ nhiều tenant, mỗi tenant có thể tự cấp mã đơn **O-100**. Hãy thiết kế khóa duy nhất phù hợp cho **Order**; giải thích vì sao chỉ dùng **orderId** hoặc **email khách hàng** có thể sai.

### Bài 2 — Đánh giá MERGE

Giải thích hành vi khi đơn **O-100** đã có **status = PAID** mà chương trình chạy:

~~~cypher
MERGE (o:DemoAppOrder {
  tenantId: 'shop-a',
  orderId: 'O-100',
  status: 'CREATED'
});
~~~

Viết lại bằng **MERGE theo khóa ổn định** và **ON CREATE SET**. Thử chạy lại sau khi thay đổi trạng thái; xác định tình huống nào có thể vi phạm uniqueness constraint.

### Bài 3 — Tự kiểm thử Idempotency-Key

Trong database thử nghiệm, tạo ba constraint ở mục 3 và thực hiện một luồng API tương đương ví dụ Java ở mục 6:

- Gửi key K và payload P lần đầu.
- Gửi lại key K + payload P sau khi lần đầu commit.
- Gửi key K + payload Q khác.
- Gửi payload P với key K2 mới.

Đối chiếu **requestKey**, **fingerprint**, **orderId** và số node cuối cùng. Trình bày vì sao hai lần gửi K + P là một ý định, còn K2 + P có thể là ý định mới.

### Bài 4 — Thiết kế khi mất phản hồi commit

Client timeout ngay sau khi Neo4j đã commit Order O-501, nhưng không nhận được body HTTP. Trình bày cách client gửi lại cùng key, cách server tra request guard, phát hiện payload khác và trả về ID đã lưu. Không dùng timestamp để đoán đơn đã tạo.

### Bài 5 — Side effect bên ngoài

Một transaction callback vừa tạo Order vừa gọi **paymentGateway.charge(...)**. Hãy chỉ ra hai trường hợp có thể dẫn đến thanh toán trùng, rồi đề xuất **outbox + eventId**, yêu cầu idempotency ở cổng thanh toán và cơ chế đối soát.

### Bài 6 — Quan hệ sự kiện

Cùng Customer C-1 xem Product P-1 ba lần khác nhau. Vì sao **MERGE (c)-[:VIEWED]->(p)** có thể mất thông tin? Thiết kế **ViewEvent** có khóa ổn định, cho phép ba lượt xem khác nhau nhưng chống việc broker gửi trùng một lượt.

### Bài 7 — Tính toán độ trễ và tranh chấp

Hai mươi worker đồng thời nhận một key K. Hãy chỉ ra vai trò của uniqueness constraint, khóa transaction, retry và phép kiểm tra sau commit. Những chỉ số nào giúp xác định điểm nghẽn nếu p95 tăng?

## 15. Ghi nhớ

Định danh ổn định là nền tảng để Neo4j biết **đâu là cùng một thực thể**; idempotency key và fingerprint cho biết **đâu là cùng một yêu cầu**; uniqueness constraint, **MERGE** và transaction giúp thực thi các quy tắc đó an toàn khi nhiều client cùng ghi.

Đối với API tạo dữ liệu, một thiết kế có thể kiểm chứng thường đi theo chuỗi:

**Chuẩn hóa business key → kiểm tra payload → xác lập request key có scope → MERGE guard dưới constraint → so fingerprint → ghi graph và outbox cùng transaction → commit → trả hoặc replay kết quả đã lưu.**

Neo4j Java Driver hỗ trợ transaction và retry lỗi tạm thời, nhưng không thể tự bảo đảm tác động ngoài database chỉ diễn ra một lần. Đối với Spring Data Neo4j, cần xác định đúng transaction boundary và chính sách retry. Cuối cùng, kiểm thử đồng thời và trường hợp **mất phản hồi sau commit** mới chứng minh được tính lũy đẳng ở cấp ứng dụng.

### Tài liệu Neo4j chính thức

- [Cypher Manual – MERGE, uniqueness constraints và concurrent relationship merges](https://neo4j.com/docs/cypher-manual/current/clauses/merge/)
- [Cypher Manual – CREATE và so sánh CREATE với MERGE](https://neo4j.com/docs/cypher-manual/current/clauses/create/)
- [Cypher Manual – Constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Cypher Manual – Create constraints](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Java Driver Manual – Run your own transactions](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver Manual – Performance recommendations](https://neo4j.com/docs/java-manual/current/performance/)
- [Spring Data Neo4j Reference – Neo4jClient](https://docs.spring.io/spring-data/neo4j/reference/appendix/neo4j-client.html)
- [Spring Data Neo4j API – Neo4jTransactionManager](https://docs.spring.io/spring-data/neo4j/reference/api/java/org/springframework/data/neo4j/core/transaction/Neo4jTransactionManager.html)
