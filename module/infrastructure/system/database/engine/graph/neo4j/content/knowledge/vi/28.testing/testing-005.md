# Kiểm thử ràng buộc, dữ liệu trùng và thuộc tính bị thiếu

Neo4j lưu dữ liệu theo mô hình **property graph**: node mang label và property, relationship có type, hướng và property riêng. Trong hệ thống thật, dữ liệu có thể được ghi đồng thời qua Java Driver, Spring Data Neo4j, Cypher trực tiếp hoặc quy trình nhập CSV. Vì vậy, việc một đoạn mã Java “đã kiểm tra đầu vào” không đủ để bảo đảm cơ sở dữ liệu không xuất hiện **mã định danh trùng, thuộc tính bắt buộc bị thiếu, giá trị sai kiểu hoặc relationship lặp ngoài ý muốn**.

Bài thuộc chương **Kiểm thử** của module `DATABASE_ENGINE_GRAPH_NEO4J` và tập trung vào ba câu hỏi: **ràng buộc nào đang được Neo4j thực thi, dữ liệu bất thường nào còn lọt qua, và bài kiểm thử nào chứng minh được điều đó?** Các ví dụ dùng Cypher của Neo4j 5.x, có lưu ý riêng cho tính năng Enterprise Edition. Phần Java sử dụng Neo4j Java Driver, JUnit 5 và Testcontainers để kiểm tra trên database thật.

> **Nguyên tắc:** Chạy lệnh tạo/xóa dữ liệu, tạo constraint và các thử nghiệm cố ý gây lỗi **chỉ trong database kiểm thử riêng**. Không thử tạo bản ghi trùng trên production, vì có thể làm hỏng dữ liệu nếu constraint mong đợi chưa tồn tại.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **property uniqueness**, **property existence**, **key constraint** và **property type constraint**; biết constraint nào cần Neo4j Enterprise Edition.
2. Viết truy vấn phát hiện **giá trị khóa trùng**, trùng sau chuẩn hóa, relationship trùng và property bị thiếu.
3. Kiểm tra bằng trường hợp **hợp lệ và không hợp lệ**, xác minh transaction thất bại không để lại dữ liệu ghi dở.
4. Giải thích tại sao một **uniqueness constraint** không đồng nghĩa property đó là bắt buộc.
5. Sử dụng `MERGE` đúng mục đích khi nhập dữ liệu, đồng thời hiểu tại sao `MERGE` không thay thế việc kiểm soát ràng buộc toàn vẹn.
6. Tạo kiểm thử tích hợp bằng Java Driver và Testcontainers, rồi kiểm tra trạng thái **dữ liệu thực** sau từng thao tác.

## 2. Hiểu đúng các loại ràng buộc

Giả sử mô hình có khách hàng `:QaCustomer` với thuộc tính `customerId`, `email`, `name` và đơn hàng `:QaOrder` với `orderId`, `amount`:

~~~text
(:QaCustomer {customerId: 'C01', email: 'an@example.test'})
        |
        | [:PLACED]
        v
(:QaOrder {orderId: 'O01', amount: 120000})
~~~

Ở mức nghiệp vụ, có thể có quy tắc “mỗi khách hàng phải có ID”, “không có hai khách hàng cùng ID” và “mỗi đơn hàng thuộc đúng một khách hàng”. **Không phải quy tắc nào cũng được bảo đảm bằng một constraint có sẵn.**

| Loại ràng buộc | Bảo đảm | Có yêu cầu property phải tồn tại? | Edition |
|---|---|---|---|
| **Property uniqueness** | Giá trị, hoặc **tổ hợp giá trị**, không trùng trong một label/type | **Không**; bản ghi thiếu property không vi phạm uniqueness | Community và Enterprise |
| **Property existence** | Property bắt buộc tồn tại trên mọi node/relationship có label/type tương ứng | **Có** | Enterprise |
| **Node/relationship key** | Property bắt buộc tồn tại **và** giá trị/tổ hợp giá trị phải duy nhất | **Có** | Enterprise |
| **Property type** | Property có kiểu được khai báo khi nó hiện hữu | **Không mặc nhiên** biến property thành bắt buộc | Enterprise |

**Điểm cần nhớ nhất:** nếu chỉ có unique constraint trên `customerId` thì một node không có `customerId` vẫn có thể được tạo. Nếu muốn mọi node `:QaCustomer` bắt buộc có ID, hãy kết hợp kiểm tra ở ứng dụng với **existence/key constraint** khi edition hỗ trợ.

Các phiên bản Neo4j mới có thể bổ sung loại constraint khác (chẳng hạn ràng buộc label/type ở mô hình schema mới). Khi thiết kế test cho Neo4j 5.x, hãy dựa vào đúng những loại mà bản cài đặt hỗ trợ.

### 2.1. Tạo uniqueness constraint

~~~cypher
CREATE CONSTRAINT qa_customer_id_unique IF NOT EXISTS
FOR (c:QaCustomer)
REQUIRE c.customerId IS UNIQUE;

CREATE CONSTRAINT qa_order_id_unique IF NOT EXISTS
FOR (o:QaOrder)
REQUIRE o.orderId IS UNIQUE;
~~~

Đây là constraint dựa trên property. Nó cũng có **index nền** giúp `MATCH`/`MERGE` tìm node theo khóa phù hợp. `IF NOT EXISTS` làm câu lệnh an toàn hơn khi chạy lại, nhưng không chứng minh database đã có **đúng tất cả các constraint nghiệp vụ** mong đợi.

Nếu dữ liệu hiện có đã vi phạm uniqueness, việc tạo constraint **không thể hoàn thành thành công**. Vì vậy, với dữ liệu cũ, cần chạy các truy vấn phát hiện trùng **trước khi migration tạo constraint**.

### 2.2. Property existence và node key (Enterprise)

Các câu lệnh sau là lựa chọn thiết kế thay thế hoặc bổ sung theo phiên bản/edition; **không chạy tất cả một cách máy móc**:

~~~cypher
// Neo4j Enterprise: mọi node QaRequiredCustomer phải có customerId.
CREATE CONSTRAINT qa_required_customer_id_exists IF NOT EXISTS
FOR (c:QaRequiredCustomer)
REQUIRE c.customerId IS NOT NULL;
~~~

~~~cypher
// Neo4j Enterprise: bắt buộc có customerId và không được trùng.
CREATE CONSTRAINT qa_required_customer_id_key IF NOT EXISTS
FOR (c:QaRequiredCustomer)
REQUIRE c.customerId IS NODE KEY;
~~~

**Node key** kết hợp ý nghĩa **existence + uniqueness**. Tùy phiên bản và schema đã có, hãy tránh tạo ràng buộc trùng nghĩa không cần thiết. Lỗi khi tạo constraint trên dữ liệu cũ không tự sửa bản ghi thiếu property.

### 2.3. Uniqueness theo nhiều thuộc tính

Nếu một `externalId` chỉ phải duy nhất **trong từng tenant**, mô hình sau phù hợp hơn yêu cầu `externalId` duy nhất toàn bộ hệ thống:

~~~cypher
CREATE CONSTRAINT qa_tenant_customer_unique IF NOT EXISTS
FOR (c:QaTenantCustomer)
REQUIRE (c.tenantId, c.externalId) IS UNIQUE;
~~~

Hai node có cùng `externalId = 'U01'` nhưng tenant `T01` và `T02` khác nhau **không vi phạm** constraint này. Hai node có cùng **cả hai** giá trị sẽ vi phạm. Tuy nhiên, nếu một trong hai property **bị thiếu**, uniqueness theo tổ hợp **không bắt buộc** node đó phải có khóa đầy đủ. Với Enterprise, có thể dùng **composite node key** nếu yêu cầu cả hai property bắt buộc tồn tại:

~~~cypher
// Neo4j Enterprise, dùng khi yêu cầu đủ cả hai khóa.
CREATE CONSTRAINT qa_tenant_customer_key IF NOT EXISTS
FOR (c:QaTenantCustomer)
REQUIRE (c.tenantId, c.externalId) IS NODE KEY;
~~~

Trong một hệ thống thật, hãy chọn **một chiến lược constraint nhất quán**, không chạy cả hai lệnh trên cho cùng một schema mà không xem xét constraint/index hiện có.

### 2.4. Relationship và kiểu property

Neo4j cũng hỗ trợ ràng buộc trên **property của relationship** theo phiên bản phù hợp:

~~~cypher
CREATE CONSTRAINT qa_payment_id_unique IF NOT EXISTS
FOR ()-[r:QA_PAYMENT]-()
REQUIRE r.paymentId IS UNIQUE;
~~~

Điều này bảo đảm mỗi giá trị `paymentId` hiện hữu là duy nhất giữa các relationship type `QA_PAYMENT`, nhưng **không** có nghĩa mỗi cặp node chỉ được nối bởi một relationship `QA_PAYMENT`. Kiểm tra “nhiều cạnh cùng loại giữa cùng cặp node” là một quy tắc khác.

Với Enterprise và bản Neo4j hỗ trợ property type constraint, ví dụ:

~~~cypher
CREATE CONSTRAINT qa_order_amount_integer IF NOT EXISTS
FOR (o:QaOrder)
REQUIRE o.amount IS :: INTEGER;
~~~

Ràng buộc kiểu bảo vệ dạng dữ liệu khi `amount` **có mặt**; nếu nghiệp vụ còn yêu cầu không được thiếu `amount`, cần kiểm tra **existence** hoặc validation riêng. Ràng buộc kiểu `INTEGER` cũng **không tự bảo đảm số không âm**; quy tắc `amount >= 0` cần được xác minh riêng.

## 3. Hiểu `null` và thuộc tính không tồn tại trong Neo4j

Trong Cypher, truy cập property không có trên node thường cho kết quả `null`:

~~~cypher
MATCH (c:QaCustomer)
WHERE c.customerId IS NULL
RETURN elementId(c) AS nodeId, c.name AS name;
~~~

Neo4j không lưu giá trị property `null` giống như một giá trị thông thường: **gán `SET c.customerId = null` xóa property** đó khỏi node. Ví dụ minh họa trên node không bị ràng buộc existence:

~~~cypher
CREATE (c:QaCustomer {customerId: 'C-TEMP', name: 'Tạm'})
SET c.customerId = null
RETURN c.name AS name, c.customerId AS id;
// id = null vì property customerId đã bị xóa.
~~~

Nếu `:QaCustomer` chỉ có uniqueness constraint, đoạn trên có thể thành công (vì node thiếu khóa không vi phạm uniqueness); nếu label có existence hoặc key constraint thích hợp, thao tác xóa property bắt buộc sẽ bị từ chối.

**Không dùng `= null` hoặc `<> null` để tìm thiếu dữ liệu.** Trong Cypher, dùng `IS NULL` và `IS NOT NULL`:

~~~cypher
MATCH (c:QaCustomer)
WHERE c.email IS NULL
RETURN elementId(c) AS nodeId;
~~~

Property **rỗng** và property **bị thiếu** cũng khác nhau:

| Dữ liệu | `c.email IS NULL` | `c.email = ''` | Có thể vi phạm uniqueness trên email? |
|---|---|---|---|
| Không có `email` | `true` | `null` | Không, chỉ vì thiếu email |
| `email = ''` | `false` | `true` | Có nếu đã có node khác cùng chuỗi rỗng |
| `email = 'a@example.test'` | `false` | `false` | Có nếu trùng giá trị với node khác |
| `email = ' A@Example.test '` | `false` | `false` | Không mặc nhiên trùng `'a@example.test'` theo so sánh nguyên gốc |

Nếu nghiệp vụ coi email phân biệt/không phân biệt chữ hoa, có trim khoảng trắng hay không, hãy chuẩn hóa thành **khóa nghiệp vụ nhất quán** trước khi lập constraint. Uniqueness theo `email` nguyên gốc **không tự thực hiện chuẩn hóa**.

## 4. Chuẩn bị dữ liệu thử trên database cô lập

Trong database thử nghiệm mới, sau khi đã tạo constraint `qa_customer_id_unique` và `qa_order_id_unique` ở mục 2, chạy:

~~~cypher
CREATE (a:QaCustomer {
    customerId: 'C01',
    name: 'An',
    email: 'An@Example.test'
})
CREATE (b:QaCustomer {
    customerId: 'C02',
    name: 'Bình',
    email: ' binh@example.test '
})
CREATE (o1:QaOrder {orderId: 'O01', amount: 120000})
CREATE (o2:QaOrder {orderId: 'O02', amount: 180000})
CREATE (a)-[:PLACED]->(o1)
CREATE (a)-[:PLACED]->(o2)
RETURN a.customerId AS firstCustomer,
       b.customerId AS secondCustomer;
~~~

Đồ thị dự kiến:

~~~mermaid
flowchart LR
    C1["QaCustomer C01<br/>An"]
    C2["QaCustomer C02<br/>Bình"]
    O1["QaOrder O01<br/>120000"]
    O2["QaOrder O02<br/>180000"]
    C1 -->|PLACED| O1
    C1 -->|PLACED| O2
~~~

Khi chỉ có dữ liệu này:

~~~cypher
MATCH (c:QaCustomer)
WITH count(c) AS customerCount
MATCH (o:QaOrder)
RETURN customerCount, count(o) AS orderCount;
// customerCount = 2, orderCount = 2
~~~

**Không chạy lặp câu `CREATE` để tạo fixture** vì sẽ va vào uniqueness constraint; những test cần tạo lại nên xóa fixture trong database thử nghiệm, dùng transaction rollback hoặc khởi tạo một database/container mới. Hãy ghi rõ giả định mỗi ví dụ chạy từ trạng thái nào.

## 5. Test một constraint bằng ca hợp lệ và không hợp lệ

### 5.1. Ca hợp lệ: hai khóa khác nhau

Trên database thử nghiệm có uniqueness constraint và chưa tồn tại mã `C03`:

~~~cypher
CREATE (c:QaCustomer {customerId: 'C03', name: 'Chi'})
RETURN c.customerId AS id;
~~~

**Mong đợi:** tạo thành công một node `C03`. Đây là **positive test**; nếu nó thất bại, có thể do dữ liệu nền đã có `C03` hoặc do một constraint khác.

### 5.2. Ca không hợp lệ: cùng mã định danh

Giả sử `C01` đã tồn tại:

~~~cypher
CREATE (:QaCustomer {customerId: 'C01', name: 'Trùng ID'});
~~~

**Mong đợi:** Neo4j từ chối câu lệnh vì vi phạm uniqueness constraint. Sau lỗi, kiểm tra:

~~~cypher
MATCH (c:QaCustomer {customerId: 'C01'})
RETURN count(c) AS occurrences;
// occurrences = 1 nếu fixture ban đầu hợp lệ.
~~~

**Điều phải assert:** không chỉ “có exception” mà còn “**số node theo ID vẫn bằng 1**”. Mã lỗi/thông điệp cụ thể có thể khác nhau theo phiên bản, ví dụ nhóm `Neo.ClientError.Schema.*`; đừng viết test phụ thuộc câu văn của `getMessage()`.

### 5.3. Ca bất ngờ: bỏ property được unique

Trên database mới chỉ có **uniqueness** và **chưa có existence/key constraint** cho `:QaCustomer(customerId)`:

~~~cypher
CREATE (:QaCustomer {name: 'Khách chưa có ID'});
CREATE (:QaCustomer {name: 'Một khách khác chưa có ID'});
~~~

Hai câu lệnh có thể **đều thành công** dù đã có uniqueness constraint trên `customerId`. Đây là bài kiểm tra để tránh kết luận sai rằng “đã unique thì không thể thiếu ID”.

### 5.4. Ca bắt buộc ID: existence/key constraint

Trên **Neo4j Enterprise** và label riêng `:QaRequiredCustomer` đã có key constraint:

~~~cypher
CREATE (:QaRequiredCustomer {name: 'Thiếu ID'});
~~~

**Mong đợi:** giao dịch bị từ chối vì property `customerId` bắt buộc. Nếu dùng Community Edition, không có loại constraint này; phải kiểm thử validation ở ứng dụng hoặc cơ chế khác, không được ghi test là “database chặn thiếu ID” khi thực tế không có constraint.

## 6. Phát hiện dữ liệu trùng **trước** khi tạo constraint

Trong một hệ thống cũ, dữ liệu có thể đã được nhập khi chưa có constraint. Nếu bạn tạo uniqueness constraint ngay, migration có thể thất bại, còn các bản ghi trùng vẫn chưa được xử lý. Trước khi tạo constraint, kiểm tra theo đúng **khóa nghiệp vụ**.

### 6.1. Node có cùng ID

~~~cypher
MATCH (c:QaCustomer)
WHERE c.customerId IS NOT NULL
WITH c.customerId AS customerId, count(*) AS occurrences
WHERE occurrences > 1
RETURN customerId, occurrences
ORDER BY occurrences DESC, customerId;
~~~

Nếu không có constraint và hai node cùng `C01`, kết quả chứa `C01 | 2`. Truy vấn này không sửa dữ liệu; nó chỉ nêu các khóa xuất hiện quá một lần.

### 6.2. Trùng sau khi chuẩn hóa giá trị

Hai email `'An@Example.test'` và `' an@example.test '` không giống hệt nhau. Nếu nghiệp vụ coi chúng là cùng email sau `trim` và `toLower`:

~~~cypher
MATCH (c:QaCustomer)
WHERE c.email IS NOT NULL
WITH toLower(trim(c.email)) AS normalizedEmail,
     count(*) AS occurrences
WHERE normalizedEmail <> '' AND occurrences > 1
RETURN normalizedEmail, occurrences
ORDER BY occurrences DESC, normalizedEmail;
~~~

**Lưu ý:** truy vấn giả định `email` là **chuỗi**. Nếu nguồn nhập có property sai kiểu, phải làm sạch/kiểm tra kiểu trước khi dùng hàm chuỗi. Chuẩn hóa email thực tế có những quy tắc phức tạp hơn việc hạ chữ thường; không tự xóa dấu chấm, dấu cộng hoặc thay đổi phần local-part nếu nghiệp vụ chưa xác nhận.

Nếu cần uniqueness theo email chuẩn hóa, hãy lưu property riêng như `emailNormalized`, bảo đảm cập nhật nó theo cùng quy tắc, và tạo constraint trên property đó:

~~~cypher
CREATE CONSTRAINT qa_email_normalized_unique IF NOT EXISTS
FOR (c:QaCustomer)
REQUIRE c.emailNormalized IS UNIQUE;
~~~

Trước khi tạo constraint này trên dữ liệu cũ, phải điền property chuẩn hóa và **giải quyết các nhóm trùng**. Không tạo constraint trên một property chưa được các luồng ghi duy trì nhất quán.

### 6.3. Thiếu property và chuỗi chỉ có khoảng trắng

~~~cypher
MATCH (c:QaCustomer)
WHERE c.customerId IS NULL
RETURN elementId(c) AS nodeId, c.name AS name;
~~~

~~~cypher
MATCH (c:QaCustomer)
WHERE c.email IS NOT NULL
  AND trim(c.email) = ''
RETURN elementId(c) AS nodeId, c.customerId AS customerId;
~~~

Truy vấn đầu tìm property thiếu. Truy vấn sau tìm email chỉ có khoảng trắng hoặc rỗng. Số record của hai tập **không nhất thiết bằng nhau**, và không nên dùng `count(c.email)` để tính số node thiếu, vì `count(expression)` bỏ qua giá trị `null`.

### 6.4. Dữ liệu trùng theo nhiều tenant

~~~cypher
MATCH (c:QaTenantCustomer)
WHERE c.tenantId IS NOT NULL
  AND c.externalId IS NOT NULL
WITH c.tenantId AS tenantId,
     c.externalId AS externalId,
     count(*) AS occurrences
WHERE occurrences > 1
RETURN tenantId, externalId, occurrences
ORDER BY occurrences DESC, tenantId, externalId;
~~~

Nếu cùng `externalId` xuất hiện ở hai tenant khác nhau, truy vấn này **không báo trùng**; đó là hành vi đúng cho ràng buộc duy nhất trên tổ hợp `(tenantId, externalId)`.

## 7. Phát hiện relationship trùng và dữ liệu tham chiếu bất thường

Neo4j cho phép nhiều relationship cùng type giữa cùng hai node khi dữ liệu/schema cho phép. Uniqueness constraint trên **property của relationship** không tự ngăn hai cạnh `PLACED` nếu chúng không có mã quan hệ hoặc có các mã khác nhau.

Giả sử graph có hai cạnh `PLACED` từ khách hàng `C01` đến đơn hàng `O01`:

~~~cypher
MATCH (c:QaCustomer {customerId: 'C01'}),
      (o:QaOrder {orderId: 'O01'})
CREATE (c)-[:PLACED]->(o);
// Chỉ chạy trên database thử nghiệm để tạo cố ý một cạnh lặp.
~~~

Kiểm tra số cạnh theo cặp node:

~~~cypher
MATCH (c:QaCustomer)-[r:PLACED]->(o:QaOrder)
WITH c.customerId AS customerId,
     o.orderId AS orderId,
     count(r) AS edgeCount
WHERE edgeCount > 1
RETURN customerId, orderId, edgeCount
ORDER BY edgeCount DESC;
~~~

Với dữ liệu mẫu và lệnh tạo cạnh trùng ở trên, kết quả dự kiến là `C01 | O01 | 2`.

**Quan trọng:** xác định đúng “trùng” theo nghiệp vụ. Hai giao dịch mua lặp lại cùng một sản phẩm có thể là **hai hành động khác nhau**, không phải cạnh trùng cần xóa. Chỉ coi hai relationship là bất hợp lệ khi mô hình yêu cầu **tối đa một quan hệ theo cặp node/type** hoặc cùng một định danh sự kiện.

### Đơn hàng không có khách hàng

~~~cypher
MATCH (o:QaOrder)
WHERE NOT EXISTS {
    MATCH (:QaCustomer)-[:PLACED]->(o)
}
RETURN o.orderId AS orderWithoutCustomer;
~~~

### Đơn hàng có nhiều khách hàng sở hữu

~~~cypher
MATCH (c:QaCustomer)-[:PLACED]->(o:QaOrder)
WITH o.orderId AS orderId, count(DISTINCT c) AS owners
WHERE owners > 1
RETURN orderId, owners;
~~~

Hai bài kiểm tra này thể hiện quy tắc **cardinality** của mô hình (nếu mỗi đơn phải thuộc đúng một khách hàng). Chúng không được thay thế chỉ bằng unique constraint của `orderId`. Trong Neo4j 5, hãy kiểm tra chúng bằng Cypher và ở tầng nghiệp vụ; ở các phiên bản mới hơn, một số ràng buộc schema nâng cao có thể có phạm vi khác, cần đối chiếu tài liệu phiên bản.

## 8. `MERGE` giúp nhập lại an toàn, nhưng cần kiểm thử

Khi nhập dữ liệu từ CSV/Java Driver, dùng `MERGE` theo khóa định danh đã có unique constraint:

~~~cypher
MERGE (c:QaCustomer {customerId: $customerId})
ON CREATE SET c.createdAt = datetime()
SET c.name = $name
RETURN c.customerId AS id, c.name AS name;
~~~

Với cùng `customerId`, lặp lại query thường **khớp node có sẵn** thay vì tạo node mới. Tuy nhiên:

- `MERGE` trên nhiều property đồng thời, ví dụ `{customerId, name}`, có thể coi hai phiên bản tên khác nhau là hai mẫu khác nhau và tạo/xung đột. Nên `MERGE` bằng **khóa ổn định**, rồi `SET` các property cập nhật.
- Nếu khóa `customerId` **rỗng/thiếu**, `MERGE` có thể không tạo được mẫu phù hợp. Cần validation đầu vào trước khi gọi.
- `MERGE` không thay constraint trong trường hợp nhiều transaction cùng ghi cạnh tranh. Uniqueness constraint giúp bảo vệ tính duy nhất ở database.
- Với relationship, `MERGE (c)-[:PLACED]->(o)` khi cả `c` và `o` đã được **bind** phù hợp giúp tránh tạo cùng một mẫu relationship khi chạy lại. Nhưng cần xác định nghiệp vụ có cho phép nhiều cạnh cùng type giữa cùng cặp node không.
- Lặp lại transaction có các phép cộng dồn như `SET c.balance = c.balance + $amount` có thể **không idempotent**, dù dùng `MERGE` node.

Một bài test import có ích là chạy cùng snapshot **hai lần**, sau đó đối chiếu:

| Chỉ số | Sau lần 1 | Sau lần 2 mong đợi |
|---|---:|---:|
| Số node cho `C01` | 1 | 1 |
| Số node cho `O01` | 1 | 1 |
| Số cạnh `C01 -[:PLACED]-> O01` | 1 | 1 |
| Tổng doanh thu | Theo dữ liệu nguồn | Không tăng nếu không có nghiệp vụ cộng dồn mới |

Đừng dùng việc câu lệnh `MERGE` chạy thành công làm bằng chứng toàn bộ nguồn đã được nạp: `MATCH` thiếu node tham chiếu có thể làm một hàng nhập **không tạo relationship** mà không phát sinh exception.

## 9. Kiểm tra transaction rollback khi một câu lệnh thất bại

Neo4j hỗ trợ transaction ACID. Nếu **một transaction** chứa nhiều thao tác mà thao tác sau vi phạm constraint khiến transaction thất bại, **những thay đổi chưa commit trong transaction đó phải bị rollback**. Những transaction đã commit trước đó không tự bị rollback.

Ví dụ logic:

~~~text
Transaction A:
  1. CREATE QaCustomer {customerId: 'C-NEW'}   // hợp lệ
  2. CREATE QaCustomer {customerId: 'C01'}     // trùng khóa đã tồn tại
  3. COMMIT                                   // không thể commit thành công

Kết quả cần kiểm tra:
  - Node C01 cũ vẫn có đúng một bản.
  - Node C-NEW không tồn tại sau rollback.
~~~

**Cảnh báo:** nếu chạy từng câu `CREATE` ở trên thành hai auto-commit transaction riêng biệt, câu đầu có thể đã commit trước khi câu thứ hai lỗi. Muốn kiểm thử rollback **toàn khối**, phải đặt cả hai trong cùng một transaction (qua Java Driver `executeWrite`, hoặc explicit transaction trong môi trường thử).

Khi test, không chỉ `assertThrows(...)`. Hãy truy vấn lại số node `C-NEW` và `C01` **sau khi transaction lỗi được rollback**, bằng một transaction/session đọc mới.

## 10. Kiểm thử tích hợp Java Driver với Testcontainers

Một unit test dùng mock `Session` có thể kiểm tra xử lý lỗi trong Java, nhưng không xác nhận được constraint thật trên Neo4j. Với các bài kiểm tra dữ liệu trùng/rollback, nên chạy **integration test trên database thật**.

### 10.1. Phụ thuộc kiểm thử

Ví dụ Gradle (Java 17+, JUnit 5; quản lý phiên bản theo BOM của dự án):

~~~groovy
dependencies {
    implementation 'org.neo4j.driver:neo4j-java-driver'
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:neo4j'
}

test {
    useJUnitPlatform()
}
~~~

Ví dụ dưới đây dùng **Testcontainers 1.x** (package `org.testcontainers.containers.Neo4jContainer`) và **Neo4j Java Driver 5.x/6.x**. Nếu dự án dùng Testcontainers 2.x, package của container Neo4j có thể khác; hãy điều chỉnh theo phiên bản đã chọn và bảo đảm dependencies được resolve chính xác. Không đoán mã chạy được khi chưa kiểm tra BOM.

### 10.2. Lớp integration test đầy đủ

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;
import org.neo4j.driver.exceptions.ClientException;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class CustomerConstraintsIT {
    private static final String PASSWORD = "local-test-only";

    @Container
    static final Neo4jContainer<?> neo4j =
            new Neo4jContainer<>("neo4j:5.26")
                    .withAdminPassword(PASSWORD);

    private static Driver driver;

    @BeforeAll
    static void prepareSchema() {
        driver = GraphDatabase.driver(
                neo4j.getBoltUrl(),
                AuthTokens.basic("neo4j", PASSWORD));
        driver.verifyConnectivity();

        try (Session session = driver.session()) {
            session.run("""
                    CREATE CONSTRAINT qa_customer_id_unique IF NOT EXISTS
                    FOR (c:QaCustomer)
                    REQUIRE c.customerId IS UNIQUE
                    """).consume();
        }
    }

    @BeforeEach
    void clearTestNodes() {
        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run("""
                        MATCH (c:QaCustomer)
                        DETACH DELETE c
                        """).consume();
                return null;
            });
        }
    }

    @Test
    void rejectsDuplicateAndPreservesOriginal() {
        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run("""
                        CREATE (:QaCustomer {
                            customerId: 'C01', name: 'An'
                        })
                        """).consume();
                return null;
            });

            ClientException error = assertThrows(
                    ClientException.class,
                    () -> session.executeWrite(tx -> {
                        tx.run("""
                                CREATE (:QaCustomer {
                                    customerId: 'C01',
                                    name: 'Duplicate'
                                })
                                """).consume();
                        return null;
                    }));

            assertTrue(error.code().startsWith("Neo.ClientError."));

            long count = session.executeRead(tx -> tx.run("""
                    MATCH (c:QaCustomer {customerId: 'C01'})
                    RETURN count(c) AS n
                    """).single().get("n").asLong());

            assertEquals(1L, count);
        }
    }

    @Test
    void uniquenessDoesNotRequirePropertyToExist() {
        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run("""
                        CREATE (:QaCustomer {name: 'No ID 1'})
                        CREATE (:QaCustomer {name: 'No ID 2'})
                        """).consume();
                return null;
            });

            long missing = session.executeRead(tx -> tx.run("""
                    MATCH (c:QaCustomer)
                    WHERE c.customerId IS NULL
                    RETURN count(c) AS n
                    """).single().get("n").asLong());

            assertEquals(2L, missing);
        }
    }

    @Test
    void failureRollsBackWholeTransaction() {
        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run("""
                        CREATE (:QaCustomer {
                            customerId: 'C01'
                        })
                        """).consume();
                return null;
            });

            assertThrows(ClientException.class,
                    () -> session.executeWrite(tx -> {
                        tx.run("""
                                CREATE (:QaCustomer {
                                    customerId: 'C-NEW'
                                })
                                """).consume();
                        tx.run("""
                                CREATE (:QaCustomer {
                                    customerId: 'C01'
                                })
                                """).consume();
                        return null;
                    }));

            Map<String, Object> counts = session.executeRead(tx -> {
                var record = tx.run("""
                        MATCH (c:QaCustomer)
                        RETURN
                          count(CASE WHEN c.customerId = 'C01'
                                THEN 1 END) AS oldCount,
                          count(CASE WHEN c.customerId = 'C-NEW'
                                THEN 1 END) AS newCount
                        """).single();
                return Map.of(
                        "old", record.get("oldCount").asLong(),
                        "new", record.get("newCount").asLong());
            });

            assertEquals(1L, counts.get("old"));
            assertEquals(0L, counts.get("new"));
        }
    }

    @AfterAll
    static void closeDriver() {
        if (driver != null) {
            driver.close();
        }
    }
}
~~~

Trong lớp trên, dữ liệu test được xóa trước mỗi test và container dùng riêng cho lớp. **Mọi câu truy vấn ghi đều được `consume()`** để lỗi của truy vấn xuất hiện trước khi callback kết thúc. Với managed transaction `executeWrite`, driver có thể retry **lỗi tạm thời** theo chính sách, nhưng constraint validation error không thể tự sửa bằng retry.

**Ý nghĩa các assertion:**

| Test | Điều kiện đầu vào | Kết quả bắt buộc |
|---|---|---|
| `rejectsDuplicateAndPreservesOriginal` | Đã tồn tại `C01`, cố `CREATE` thêm `C01` | Exception; còn đúng 1 node `C01` |
| `uniquenessDoesNotRequirePropertyToExist` | Chỉ có uniqueness, tạo hai node không có ID | Thành công; có 2 node thiếu property |
| `failureRollsBackWholeTransaction` | Trong cùng transaction tạo `C-NEW` rồi tạo `C01` trùng | Exception; `C-NEW` không còn; `C01` vẫn 1 |

**Không chạy lớp test minh họa trên DB chia sẻ:** `clearTestNodes` xóa toàn bộ node mang label `QaCustomer` trong database hiện tại. Điều đó chỉ phù hợp với **Neo4j Testcontainers cô lập** mà bài kiểm thử tự tạo. Trên hệ thống thật, test phải có namespace/fixture riêng và cleanup dựa trên ID của chính test.

## 11. Kiểm thử thêm thuộc tính bắt buộc ở Enterprise

Nếu dùng Enterprise và đã tạo constraint:

~~~cypher
CREATE CONSTRAINT qa_required_customer_key IF NOT EXISTS
FOR (c:QaRequiredCustomer)
REQUIRE c.customerId IS NODE KEY;
~~~

Hãy có hai ca:

~~~cypher
// Hợp lệ: có ID và chưa trùng.
CREATE (:QaRequiredCustomer {customerId: 'R01', name: 'An'});
~~~

~~~cypher
// Không hợp lệ: thiếu property customerId.
CREATE (:QaRequiredCustomer {name: 'Không có ID'});
~~~

Ở Java, dạng assertion cơ bản:

~~~java
assertThrows(ClientException.class, () ->
    session.executeWrite(tx -> {
        tx.run("""
            CREATE (:QaRequiredCustomer {name: 'No ID'})
            """).consume();
        return null;
    })
);
~~~

Đoạn Java này giả định `session` là session đang mở trên database **Enterprise test** đã có constraint. Nếu dùng Community, test này phải được phân nhóm/skip có chủ đích theo edition, thay vì báo lỗi do thiếu chức năng là một thất bại của logic ứng dụng.

Ngoài thử tạo node thiếu ID, hãy thử:

1. Gán `SET c.customerId = null` trên node đã tồn tại, mong đợi bị từ chối.
2. Đổi `customerId` thành giá trị đã thuộc node khác, mong đợi bị từ chối.
3. Ghi node hợp lệ, mong đợi thành công.
4. Kiểm tra lại dữ liệu sau từng transaction thất bại.

### Property type và dữ liệu trống

Nếu cần `QaOrder.amount` là `INTEGER` và `>= 0`:

- Property type constraint (Enterprise, phiên bản hỗ trợ) kiểm tra **kiểu** của value, không thay phép kiểm tra **miền giá trị**.
- Existence/key constraint kiểm tra property bắt buộc khi áp dụng.
- Validation ở Java/Spring Data Neo4j phải từ chối `amount < 0` nếu nghiệp vụ không cho phép, kể cả khi không có constraint trực tiếp cho miền số.

Một bài test tốt không chỉ kiểm tra **đúng kiểu** mà còn giá trị biên `0`, số âm, số rất lớn và trường hợp null/thiếu.

## 12. Kiểm thử trùng trong import theo lô

Một nguồn CSV có thể chứa ba dòng:

~~~csv
customerId,name
C01,An
C02,Bình
C01,An cập nhật
~~~

Nếu dùng `CREATE` cho mọi dòng trên database có uniqueness constraint, transaction chứa dòng thứ ba có thể thất bại. Nếu import bằng **nhiều transaction/lô**, những lô trước đã commit sẽ **không tự rollback**. Nếu dùng `MERGE` theo `customerId`, dữ liệu có thể được cập nhật theo chính sách `SET`.

Hãy xác định **đúng mục tiêu**:

| Chính sách nhập | Kỳ vọng với `C01` lặp lại |
|---|---|
| Từ chối nguồn có khóa trùng | Báo lỗi trước khi ghi hoặc cách ly những dòng trùng |
| Upsert, lấy bản ghi sau theo thứ tự nghiệp vụ | Có một node `C01`, dữ liệu theo chính sách mới nhất **được xác định rõ** |
| Chỉ ghi lần đầu | Có một node `C01`, các dòng sau không ghi đè giá trị quan trọng |
| Ghi lịch sử nhiều phiên bản | Tạo entity/version có định danh khác; không dùng `customerId` làm khóa duy nhất cho mỗi lịch sử |

Đừng dựa vào “dòng cuối CSV sẽ thắng” khi xử lý đồng thời hoặc khi các hàng bị `UNWIND`/tối ưu hóa mà **thứ tự áp dụng không được bảo đảm**. Nếu business rule cần bản ghi mới nhất, dữ liệu nên mang timestamp/version và logic chọn bản ghi phải được thiết kế/kiểm thử rõ ràng.

### Kế hoạch kiểm thử sau một lượt import

1. **Đếm dòng nguồn:** có bao nhiêu dòng, khóa trùng, dòng thiếu khóa, dữ liệu sai kiểu?
2. **Kiểm tra số node theo khóa:** những ID hợp lệ có đúng một node mỗi ID không?
3. **Kiểm tra số relationship theo cặp node:** có cạnh trùng hoặc quan hệ thiếu node đích không?
4. **Đối chiếu tổng hợp:** số node, số đơn và tổng tiền có đúng quy tắc nghiệp vụ, không bị nhân hàng?
5. **Chạy lại cùng snapshot nguồn:** số node và cạnh có tăng ngoài mong muốn không?
6. **Thử lỗi một lô:** các lô đã commit giữ nguyên; lô lỗi rollback; có thể tiếp tục theo checkpoint nếu pipeline yêu cầu.

Các chỉ số trong báo cáo import như **số dòng đã đọc** hoặc **số transaction commit** không đồng nghĩa số node mới được tạo. Test phải xác nhận **trạng thái graph**, không chỉ mã thoát thành công của job.

## 13. Spring Data Neo4j: test schema và dữ liệu thật

Với Spring Data Neo4j, annotation `@Node`, `@Id` và `@Relationship` giúp map entity Java, nhưng **không chứng minh Neo4j đã có uniqueness/existence constraint** mong đợi. Repository có thể hoạt động bình thường ngay cả khi database chưa thiết lập ràng buộc nghiệp vụ.

Ví dụ:

~~~java
@Node("QaCustomer")
public class Customer {
    @Id
    private String customerId;
    private String email;
    // getters, constructor và mapping khác...
}
~~~

`@Id` xác định định danh của entity trong mapping SDN; nó không thay thế bước schema migration để tạo:

~~~cypher
CREATE CONSTRAINT qa_customer_id_unique IF NOT EXISTS
FOR (c:QaCustomer)
REQUIRE c.customerId IS UNIQUE;
~~~

Nếu dùng `@DataNeo4jTest` với Testcontainers, hãy có riêng:

- **Schema test:** dùng `SHOW CONSTRAINTS` để kiểm tra constraint thực sự tồn tại trên database test.
- **Negative write test:** thử ghi ID trùng hoặc thiếu bắt buộc, assert exception và trạng thái graph sau rollback.
- **Mapping test:** lưu/đọc entity và relationship để kiểm tra field mapping.
- **Repository query test:** gọi method thực tế, xác minh kết quả theo fixture có dữ liệu trùng/thiếu/property null.

Test chỉ mock `Neo4jRepository` không đủ phát hiện constraint chưa triển khai trong database. Đặc biệt, nếu test `@DataNeo4jTest` được Spring quản lý transaction và rollback cuối test, cần biết transaction nào nhìn thấy dữ liệu chưa commit khi query đối chiếu từ driver ngoài.

## 14. Kiểm tra schema đang có bằng `SHOW CONSTRAINTS`

Trước khi kết luận hệ thống bảo vệ được dữ liệu, kiểm tra trạng thái schema bằng tài khoản có quyền:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, entityType, labelsOrTypes, properties
RETURN name, type, entityType, labelsOrTypes, properties
ORDER BY name;
~~~

Trong test schema của module, có thể lọc constraint cụ thể:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
WHERE name = 'qa_customer_id_unique'
RETURN name, type, labelsOrTypes, properties;
~~~

**Điều cần kiểm tra:** đúng **label/type**, đúng property, đúng **kiểu constraint**, không chỉ có một tên giống dự kiến. Tên constraint có thể thay đổi qua migration, còn ngữ nghĩa schema phải được bảo toàn.

Truy vấn `SHOW CONSTRAINTS` cần quyền tương ứng. Nếu test bị từ chối vì thiếu quyền schema, đó là vấn đề **thiết lập môi trường hoặc đặc quyền**, không phải bằng chứng constraint không tồn tại.

### Dữ liệu trùng có thể làm migration thất bại

Nếu hệ thống cũ chưa có constraint, trước khi chạy migration:

~~~cypher
MATCH (c:QaCustomer)
WHERE c.customerId IS NOT NULL
WITH c.customerId AS id, count(*) AS occurrences
WHERE occurrences > 1
RETURN id, occurrences;
~~~

Khi phát hiện dữ liệu trùng, **không tự động xóa “node dư”** bằng `LIMIT 1` mà chưa xét relationship, quyền sở hữu và lịch sử nghiệp vụ. Hai node trùng khóa có thể có cạnh khác nhau; thao tác hợp nhất cần quy tắc xử lý relationship, property xung đột và kế hoạch rollback. Bài này dừng ở **phát hiện và kiểm chứng**, không hướng dẫn gộp dữ liệu sản xuất theo phỏng đoán.

## 15. Ma trận ca kiểm thử nên có trong CI

| Nhóm | Fixture | Điều mong đợi | Cách xác minh |
|---|---|---|---|
| **Unique – hợp lệ** | Hai khách hàng khác ID | Ghi thành công | `count` theo ID |
| **Unique – trùng** | Hai khách hàng cùng ID | Giao dịch sau bị từ chối | Exception + còn 1 node |
| **Unique – thiếu** | Hai node không có ID | Nếu **chỉ uniqueness**, có thể tồn tại | `IS NULL` + số node |
| **Existence/key – thiếu** | Node thiếu property bắt buộc | Bị từ chối trên Enterprise khi constraint tồn tại | Exception + không tạo node |
| **Composite unique** | Cùng externalId, khác tenant | Thành công | Đếm theo cặp khóa |
| **Composite unique – trùng cặp** | Cùng tenant và externalId | Bị từ chối | Exception + đếm cặp |
| **Property rỗng** | `email = ''` hoặc khoảng trắng | Theo validation nghiệp vụ | Dò rỗng/trim |
| **Sai kiểu** | `amount = '1000'` dưới kiểu số bắt buộc | Bị từ chối nếu có type constraint | Exception hoặc validation |
| **Giá trị âm** | `amount = -1` | Bị từ chối theo nghiệp vụ | Service validation/test |
| **Relationship trùng** | Hai `PLACED` cùng cặp node | Phát hiện/không cho phép theo mô hình | `count(r)` theo cặp |
| **Thiếu relationship** | Order không có customer | Phát hiện nếu nghiệp vụ yêu cầu | `NOT EXISTS { MATCH ... }` |
| **Rollback** | Tạo node hợp lệ rồi vi phạm constraint trong cùng tx | Không có ghi dở | Query sau khi rollback |
| **Retry import** | Nhập lại cùng snapshot | Không thêm node/cạnh ngoài ý muốn | Đối chiếu trước/sau |

**Không gộp tất cả test vào một transaction rồi mong hệ thống tự giữ dữ liệu sau lỗi**. Test phải chủ động xác định transaction nào bị rollback, transaction nào đã commit và test nào cần một graph sạch.

## 16. Những lỗi kiểm thử dễ khiến kết luận sai

| Sai lầm | Vì sao sai? | Cách sửa |
|---|---|---|
| Chỉ kiểm tra có `@Id` trong Java | Không chứng minh DB có unique constraint | Kiểm tra `SHOW CONSTRAINTS` và thử ghi trùng |
| Cho rằng uniqueness bắt buộc property | Node thiếu property vẫn có thể hợp lệ | Dùng existence/key constraint khi hỗ trợ |
| Xem `null` là một giá trị property đã lưu | `SET property = null` xóa property | Dùng `IS NULL`, kiểm tra migration và validation |
| Chỉ assert `assertThrows` | Có thể đã ghi dở nếu code dùng nhiều transaction | Query lại graph và trạng thái commit |
| Assert lỗi bằng nguyên văn `getMessage()` | Nội dung có thể thay đổi theo phiên bản | Kiểm tra nhóm exception/code ổn định |
| Tạo constraint sau khi nhập dữ liệu trùng | Migration thất bại | Kiểm tra/giải quyết trùng trước |
| Dùng `MERGE` trên toàn bộ map property | Một field thay đổi có thể tạo mẫu mới | Dùng khóa ổn định, `SET` field cập nhật |
| Giả định email khác chữ hoa là cùng giá trị | Constraint so sánh giá trị nguyên gốc | Chuẩn hóa thành property riêng trước khi lập unique |
| Xem hai cạnh cùng type là luôn trùng | Có thể là hai sự kiện nghiệp vụ khác nhau | Xác định khóa/cấp độ quan hệ mong muốn |
| Test trên DB có dữ liệu nền không xác định | Count và constraint có thể thất bại ngẫu nhiên | Testcontainers/DB fixture cô lập |
| Test bằng cùng repository để seed và verify | Hai đoạn mapping có thể cùng mắc lỗi | Đối chiếu qua Cypher độc lập |
| Xóa toàn label trong database chia sẻ | Làm mất dữ liệu của người khác | Chỉ cleanup trên test DB do test sở hữu |

## 17. Bài luyện tập

### Bài 1 — Uniqueness và property thiếu

Đã có:

~~~cypher
CREATE CONSTRAINT qa_user_id_unique IF NOT EXISTS
FOR (u:QaUser)
REQUIRE u.userId IS UNIQUE;
~~~

Hãy dự đoán hai lệnh dưới đây có vi phạm constraint hay không trên một database trống:

~~~cypher
CREATE (:QaUser {name: 'A'});
CREATE (:QaUser {name: 'B'});
~~~

<details>
<summary>Đáp án tham khảo</summary>

Hai lệnh không vi phạm **uniqueness** vì không có `userId`. Nếu nghiệp vụ bắt buộc có `userId`, dùng validation ở ứng dụng và cân nhắc existence/key constraint trên Enterprise. Không kết luận uniqueness tự bảo vệ property thiếu.

</details>

### Bài 2 — Trùng theo tenant

Thiết kế constraint cho dữ liệu:

| tenantId | externalId |
|---|---|
| T01 | U01 |
| T02 | U01 |
| T01 | U02 |

Sau đó mô tả điều gì xảy ra nếu chèn tiếp `(T01, U01)`.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
CREATE CONSTRAINT qa_user_tenant_ext_unique IF NOT EXISTS
FOR (u:QaTenantUser)
REQUIRE (u.tenantId, u.externalId) IS UNIQUE;
~~~

Ba dòng đầu hợp lệ do mỗi **cặp** khóa khác nhau. Dòng `(T01, U01)` lặp sẽ bị từ chối nếu được ghi với cùng label/property sau khi constraint hoạt động. Cần kiểm thử thêm property thiếu vì composite uniqueness không tự bắt buộc đủ hai trường.

</details>

### Bài 3 — Phân biệt null và chuỗi rỗng

Cho ba node `:QaUser`: một node thiếu `email`, một node có `email = ''`, một node có `email = '  '`. Viết câu Cypher tìm tất cả bản ghi thiếu hoặc email chỉ có khoảng trắng.

<details>
<summary>Đáp án tham khảo</summary>

~~~cypher
MATCH (u:QaUser)
WHERE u.email IS NULL
   OR (u.email IS NOT NULL AND trim(u.email) = '')
RETURN elementId(u) AS nodeId, u.email AS email;
~~~

Truy vấn giả định email hiện hữu có kiểu chuỗi. Nếu dữ liệu sai kiểu, cần kiểm tra/chuẩn hóa trước khi dùng `trim`.

</details>

### Bài 4 — Rollback khi constraint thất bại

Đã tồn tại khách hàng `C01`. Một transaction mới tạo `C03` rồi cố tạo thêm `C01`. Sau lỗi, bạn mong đợi những node nào còn tồn tại? Nếu hai lệnh ở hai transaction khác nhau, kết luận có thay đổi không?

<details>
<summary>Đáp án tham khảo</summary>

Trong **cùng transaction**, lỗi unique làm rollback cả transaction; `C01` cũ còn, `C03` mới không tồn tại. Nếu lệnh tạo `C03` đã commit trong **transaction riêng**, nó vẫn tồn tại dù transaction tạo `C01` sau đó thất bại.

</details>

### Bài 5 — Trùng node hay trùng relationship?

Một đơn hàng `O01` chỉ có một node `QaOrder` nhưng nhận hai cạnh `PLACED` từ cùng khách hàng `C01`. Uniqueness trên `orderId` có ngăn được hai cạnh này không? Viết câu kiểm tra.

<details>
<summary>Đáp án tham khảo</summary>

Không. Uniqueness của node `QaOrder.orderId` bảo đảm không có hai **node đơn hàng** cùng giá trị ID, không ngăn hai **relationship** cùng type giữa hai node.

~~~cypher
MATCH (c:QaCustomer)-[r:PLACED]->(o:QaOrder)
WITH c.customerId AS customerId,
     o.orderId AS orderId,
     count(r) AS edges
WHERE edges > 1
RETURN customerId, orderId, edges;
~~~

Chỉ xử lý những cặp bị coi là trùng sau khi xác định quy tắc nghiệp vụ.

</details>

### Bài 6 — Thiết kế kiểm thử nhập dữ liệu

Một file CSV có hai dòng `C01`, một dòng thiếu ID và một dòng `C02` hợp lệ. Hãy đề xuất ba bước kiểm tra trước khi nhập, ba chỉ số cần đối chiếu sau nhập và một phép thử chạy lại.

<details>
<summary>Gợi ý đáp án</summary>

Trước nhập: phát hiện khóa trùng, khóa thiếu và kiểu/giá trị bất hợp lệ; lựa chọn reject hay upsert. Sau nhập: số khóa hợp lệ duy nhất, số node thực tồn tại theo khóa, số relationship/tổng nghiệp vụ. Chạy lại cùng snapshot và xác minh không tăng số node/cạnh nếu nghiệp vụ yêu cầu idempotency. Phân biệt số dòng nguồn với số bản ghi mới được tạo.

</details>

## 18. Tài liệu chính thức

- [Neo4j Cypher — Tổng quan constraint](https://neo4j.com/docs/cypher-manual/current/schema/constraints/)
- [Neo4j Cypher — Tạo các loại constraint](https://neo4j.com/docs/cypher-manual/current/schema/constraints/create-constraints/)
- [Neo4j Cypher — Cú pháp constraint](https://neo4j.com/docs/cypher-manual/current/schema/syntax/)
- [Neo4j Cypher — Liệt kê constraint bằng SHOW CONSTRAINTS](https://neo4j.com/docs/cypher-manual/current/schema/constraints/list-constraints/)
- [Neo4j Cypher — Xử lý null](https://neo4j.com/docs/cypher-manual/current/values-and-types/working-with-null/)
- [Neo4j Java Driver — Managed và explicit transaction](https://neo4j.com/docs/java-manual/current/transactions/)
- [Neo4j Java Driver — Query và error handling](https://neo4j.com/docs/java-manual/current/query-simple/)
- [Testcontainers — Neo4j module](https://java.testcontainers.org/modules/databases/neo4j/)

Các đường dẫn `current` phản ánh tài liệu mới nhất khi người đọc mở trang. Khi học hoặc triển khai, cần chọn **đúng Neo4j version/edition** và phiên bản thư viện Java/Testcontainers của dự án; một số constraint đặc biệt chỉ có trong Enterprise.

## 19. Ghi nhớ

- **Uniqueness bảo vệ giá trị không trùng, không tự bắt buộc property tồn tại.** Existence/key constraint bảo vệ property bắt buộc khi edition hỗ trợ.
- **`IS NULL` phát hiện property thiếu; chuỗi rỗng và giá trị chỉ có khoảng trắng phải kiểm tra riêng.**
- **Kiểm thử cả hai chiều:** dữ liệu hợp lệ được chấp nhận, dữ liệu vi phạm bị từ chối, và trạng thái graph sau lỗi vẫn đúng.
- **Dữ liệu trùng có nhiều cấp:** node theo khóa nghiệp vụ, khóa sau chuẩn hóa, tổ hợp tenant, relationship theo cặp node/type, và tham chiếu thiếu.
- **`MERGE` hỗ trợ import idempotent nếu dùng khóa ổn định**, nhưng không thay constraint, validation và chính sách xử lý xung đột.
- **Giao dịch là ranh giới rollback.** Khi một transaction lỗi, kiểm tra cả dữ liệu đã commit trước đó và dữ liệu chưa commit của transaction thất bại.
- **Integration test trên Neo4j thực** và truy vấn đối chiếu độc lập giúp xác minh constraint, dữ liệu trùng và thuộc tính bị thiếu tốt hơn chỉ dùng mock.
