# Dùng chung cơ sở dữ liệu và bỏ qua quyền sở hữu

> **Chủ đề:** Software Design · System Architecture · Microservices  
> **Nhóm kiến thức:** Sai lầm thiết kế  
> **Mục tiêu:** Nhận diện vì sao nhiều microservices cùng ghi và phụ thuộc trực tiếp vào một cơ sở dữ liệu có thể làm mất ranh giới domain, tăng coupling, tạo rủi ro bảo mật và khiến việc thay đổi dịch vụ trở nên khó khăn; hiểu cách thiết kế quyền sở hữu dữ liệu rõ ràng và chuyển đổi an toàn.

## 1. Shared database là gì?

Trong kiến trúc microservices, một database dùng chung có thể xuất hiện dưới nhiều hình thức:

- Nhiều service cùng truy cập một database và cùng đọc/ghi các bảng.
- Mỗi service có repository riêng nhưng cùng dùng một schema và không có quy tắc ownership.
- Service A gọi database trực tiếp để đọc hoặc cập nhật bảng thuộc nghiệp vụ của Service B.
- Một nhóm thay đổi column, index, constraint hoặc stored procedure làm service khác hỏng.
- Các service dùng chung một database user có quyền đọc/ghi toàn bộ schema.
- Một service ghi dữ liệu, các service khác dựa vào trigger hoặc query trực tiếp để nhận biết thay đổi.

Ví dụ:

~~~text
Order Service --------+
Payment Service ------+----> Shared Shop Database
Inventory Service ----+        |
Reporting Service ----+        +--> orders
                               +--> payments
                               +--> inventory
                               +--> customers
~~~

Điểm đáng lo không chỉ là các database vật lý nằm cùng một server. Vấn đề xuất hiện khi **nhiều service cùng có quyền quyết định cấu trúc, trạng thái và cách diễn giải dữ liệu của nhau**.

Một cụm PostgreSQL có thể phục vụ nhiều service mà vẫn giữ ownership nếu mỗi domain có schema, role, migration authority và access policy riêng. Ngược lại, mỗi service có một connection string riêng nhưng cùng sửa các bảng của nhau vẫn là shared database ở cấp kiến trúc.

**Database per service là quy tắc về quyền sở hữu và ranh giới truy cập dữ liệu.** Nó không nhất thiết đòi mỗi service phải có một máy chủ database vật lý riêng.

## 2. Vì sao shared database thường xuất hiện?

Các lý do ban đầu thường hợp lý:

- Dự án còn nhỏ, một database dễ thiết lập và backup.
- Team muốn tránh chi phí nhiều database instances.
- Nhiều service cần join dữ liệu và muốn query trực tiếp.
- Một ứng dụng cũ được tách thành nhiều service nhưng giữ nguyên schema.
- Đội ngũ muốn triển khai nhanh, chưa xác định bounded contexts.
- Reporting cần truy vấn nhiều bảng nghiệp vụ.
- Một số thao tác cần transaction xuyên qua các phần của ứng dụng.

Ở giai đoạn đầu, một database chung có thể giảm công việc vận hành. Nhưng khi số service và team tăng, các quyết định tưởng như tiện lợi tạo ra coupling khó nhìn thấy:

1. Một service không thể thay đổi schema nếu chưa biết mọi consumer.
2. Một team có thể vô tình phá query của team khác.
3. Quyền truy cập dữ liệu rộng hơn mức cần thiết.
4. Database trở thành điểm nghẽn về performance và release.
5. Các domain bị ràng buộc vào cùng mô hình dữ liệu.
6. Không rõ ai chịu trách nhiệm khi dữ liệu sai.
7. Việc tách service sau này trở thành một dự án data migration lớn.

**Shared database thường bắt đầu như một lựa chọn tiết kiệm, sau đó trở thành một ranh giới ownership không rõ ràng.**

## 3. Database per service không có nghĩa mỗi service phải tự quản một database server

Cần phân biệt các cấp độ:

| Cấp độ | Cách tổ chức | Ý nghĩa ownership |
|---|---|---|
| **Một cluster, một schema chung** | Nhiều service dùng cùng schema/tables | Ownership dễ bị trộn nếu quyền không giới hạn |
| **Một cluster, schema riêng** | Mỗi domain có schema và role riêng | Có thể giữ ownership logic nếu access được kiểm soát |
| **Một cluster, database riêng** | Mỗi service/domain có database riêng trong cùng engine cluster | Ranh giới rõ hơn, vẫn chia sẻ hạ tầng/failure domain |
| **Cluster riêng** | Mỗi service hoặc domain có cluster riêng | Isolation cao hơn, chi phí và vận hành tăng |
| **Managed database riêng** | Mỗi domain dùng instance/service managed riêng | Có thể tách scaling, security và lifecycle rõ hơn |

Một lựa chọn trung gian có thể phù hợp:

~~~text
PostgreSQL Cluster
  |
  +-- order_db
  |     +-- order role
  |     +-- order schema/migrations
  |
  +-- payment_db
  |     +-- payment role
  |     +-- payment schema/migrations
  |
  +-- inventory_db
        +-- inventory role
        +-- inventory schema/migrations
~~~

Các database vẫn chia sẻ CPU, memory, storage và failure domain của cluster. Nếu một workload làm cạn connection hoặc I/O, những database khác có thể bị ảnh hưởng. Tuy vậy, quyền truy cập và migration ownership đã có thể rõ hơn đáng kể.

**Tách ownership logic trước, tách hạ tầng vật lý theo nhu cầu.** Không cần tạo một cluster mới cho mọi service nếu chi phí và mức cô lập chưa tương xứng.

## 4. Nguyên tắc cốt lõi: Một nguồn sự thật cho mỗi dữ kiện nghiệp vụ

Một domain service phải có quyền quyết định dữ liệu thuộc nghiệp vụ của mình.

Ví dụ:

| Dữ kiện | Domain owner | Các service khác nên dùng |
|---|---|---|
| Order lifecycle, order items | Order | API hoặc Order events/read model |
| Payment attempts, captures, refunds | Payment | Payment API/events |
| Inventory reservation, stock adjustment | Inventory | Inventory API/events |
| Customer identity/profile | Customer | Customer API hoặc projection |
| Shipment lifecycle | Fulfillment | Fulfillment API/events |
| Search index | Search/derived-data owner | Rebuild từ nguồn được công bố |

Order có thể lưu payment reference và một projection trạng thái để hiển thị checkout. Nhưng Payment domain vẫn sở hữu ledger, provider transaction IDs và quy tắc refund.

Tương tự, Inventory có thể công bố số lượng khả dụng theo contract; Order không được tự cập nhật bảng reservation để ép một đơn hàng qua trạng thái confirmed.

**Một service có thể lưu bản sao hoặc projection của dữ liệu domain khác, nhưng phải biết bản sao đó được tạo từ đâu, cập nhật theo cách nào và không có thẩm quyền ghi ngược vào nguồn.**

## 5. Những dạng coupling do shared database tạo ra

### 5.1. Schema coupling

Service A thêm column, đổi kiểu dữ liệu hoặc rename table khiến Service B lỗi khi chạy query.

### 5.2. Query coupling

Service B phụ thuộc vào join giữa những bảng nội bộ của Service A. Cách tổ chức bảng trở thành một phần API không được công bố.

### 5.3. Transaction coupling

Một request cần transaction bao trùm các bảng thuộc nhiều domain. Team không thể thay đổi một phần mà không hiểu toàn bộ transaction.

### 5.4. Deployment coupling

Migration của một service phải chạy trước/sau migration của service khác theo thứ tự không rõ. Các release buộc phải phối hợp.

### 5.5. Security coupling

Service cần đọc một vài field nhưng credential lại có quyền đọc toàn bộ database. Lỗ hổng ở một service có thể làm lộ dữ liệu của nhiều domain.

### 5.6. Performance coupling

Query analytics hoặc batch job của một service chiếm connection, I/O, locks và CPU làm chậm service giao dịch khác.

### 5.7. Operational coupling

Một sự cố database, maintenance window hoặc failover cùng lúc ảnh hưởng tất cả service dù mức criticality khác nhau.

### 5.8. Semantic coupling

Các service cùng dùng một column nhưng hiểu ý nghĩa khác nhau. Ví dụ status PAID có thể bị diễn giải thành authorized, captured hoặc settled.

Những coupling này làm giảm khả năng thay đổi độc lập, một trong các lợi ích quan trọng của microservices.

## 6. Vì sao join trực tiếp qua database là một ranh giới nguy hiểm?

Giả sử Order Service cần tên khách hàng:

~~~sql
SELECT
    o.order_id,
    o.total_amount,
    c.full_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_id = :order_id;
~~~

Query có thể chạy tốt hôm nay. Nhưng Order đang phụ thuộc vào:

- Tên bảng customers.
- Tên và kiểu cột customer_id.
- Quy tắc xóa/ẩn hồ sơ khách hàng.
- Quyền truy cập PII.
- Cách Customer domain chuẩn hóa tên.
- Migration và index của Customer.
- Semantics của dữ liệu tại thời điểm hiện tại hay thời điểm đặt hàng.

Nếu Customer đổi mô hình từ một bảng sang nhiều bảng hoặc chuyển database, Order phải thay đổi theo.

Có thể thay bằng:

- Gọi Customer API khi cần dữ liệu mới và phù hợp latency.
- Lưu snapshot dữ liệu cần thiết tại thời điểm nghiệp vụ, ví dụ tên nhận hóa đơn.
- Duy trì một read model/projection được cập nhật qua events.
- Dùng data warehouse cho truy vấn phân tích liên domain.

Chọn cách nào phụ thuộc freshness, latency, consistency và quyền dữ liệu. Không phải mọi field đều cần gọi API theo từng request.

**Truy vấn trực tiếp bảng nội bộ của service khác biến schema database thành một API ngầm, không có versioning và compatibility policy.**

## 7. Quyền sở hữu dữ liệu phải bao gồm quyền ghi, migration và semantics

Ownership không chỉ là tên team đặt trong service catalog.

Một owner cần chịu trách nhiệm về:

- Định nghĩa nghiệp vụ của từng field và trạng thái.
- Quyền tạo, cập nhật, xóa hoặc điều chỉnh dữ liệu.
- Schema migrations và backward compatibility.
- Constraints, indexes và data retention.
- Data quality, audit và source of truth.
- Contract công bố cho consumers.
- SLO về availability và freshness.
- Backup/restore và reconciliation.
- Thông báo breaking changes và deprecation.
- Xử lý incident và remediation.

Một service khác có thể yêu cầu thay đổi dữ liệu qua API/command hoặc event có contract. Owner quyết định thao tác có hợp lệ theo domain rules hay không.

Ví dụ:

~~~text
Order Service
    |
    | Request inventory reservation
    v
Inventory API
    |
    +--> Check available quantity
    +--> Validate warehouse and SKU
    +--> Apply reservation policy
    +--> Write inventory transaction
    +--> Publish ReservationCreated
~~~

Order không cần quyền UPDATE trực tiếp vào inventory tables. Inventory giữ quyền thực thi invariant và audit của chính nó.

## 8. Database user chung là lỗi bảo mật phổ biến

Một tài khoản database dùng chung cho mọi service thường có quyền quá rộng:

~~~text
order-api       \
payment-api      \
inventory-api     +----> db_admin
reporting-api    /
batch-worker    /
~~~

Nếu một service bị khai thác, attacker có thể đọc hoặc sửa dữ liệu của các domain khác.

Cần phân tách:

- Runtime role theo service/domain.
- Migration role riêng, chỉ dùng trong pipeline được kiểm soát.
- Read-only role cho các tác vụ được duyệt.
- Backup role với quyền cần thiết và hạn chế xóa.
- Operator/admin role có kiểm soát, MFA và audit.
- Credentials riêng theo environment và workload identity khi phù hợp.

Ví dụ quyền ở PostgreSQL:

~~~sql
-- Ví dụ minh họa: role runtime của Order.
CREATE ROLE order_runtime LOGIN;
GRANT CONNECT ON DATABASE order_db TO order_runtime;
GRANT USAGE ON SCHEMA order_data TO order_runtime;
GRANT SELECT, INSERT, UPDATE
ON ALL TABLES IN SCHEMA order_data
TO order_runtime;

-- Không cấp quyền vào payment_data hoặc inventory_data.
~~~

Đây là ví dụ khái niệm. Cần thiết lập default privileges cho objects mới, sequence permissions, schema ownership, role inheritance và credential lifecycle theo phiên bản/thiết kế thực tế.

**Không dùng superuser cho application runtime.** Quyền runtime và quyền migration phải được tách để một lỗi trong ứng dụng không thể tự thay schema hoặc truy cập mọi dữ liệu.

## 9. Quyền đọc cũng cần ownership

Nhiều hệ thống chỉ hạn chế quyền ghi, nhưng đọc dữ liệu nhạy cảm cũng có rủi ro.

Ví dụ Reporting có thể cần số tiền tổng hợp nhưng không cần card data hoặc địa chỉ cá nhân. Thay vì cấp SELECT toàn bộ Payment tables, có thể:

- Công bố dataset được phép dùng.
- Mask/tokenize fields nhạy cảm.
- Cấp view có column-level access.
- Dùng aggregate/event contract.
- Cấp quyền theo tenant và mục đích sử dụng.
- Audit các truy vấn đặc quyền.

Một service đọc được database không có nghĩa dữ liệu đó được phép dùng cho mọi mục đích. Data classification, retention và privacy policy vẫn áp dụng cho projections và exports.

## 10. Migration coupling: Một thay đổi column có thể phá nhiều team

Ví dụ Payment đổi tên cột:

~~~text
Before:
  payments.status

After:
  payments.payment_state
~~~

Nếu Order, Reporting và Support Dashboard đều query bảng trực tiếp, migration có thể làm nhiều consumer hỏng cùng lúc.

Một cách chuyển đổi an toàn:

1. Thêm field mới trong schema.
2. Cập nhật owner service để ghi/đọc tương thích trong giai đoạn chuyển.
3. Cung cấp API/view/event contract mới.
4. Chuyển consumers từng nhóm.
5. Đo usage của field cũ.
6. Xác nhận không còn consumer.
7. Xóa field cũ theo deprecation policy.

Đây là mô hình expand–migrate–contract. Nó cần compatibility window đủ dài cho các phiên bản consumer đang chạy.

Nếu consumer query trực tiếp bảng, không thể dễ dàng biết ai còn dùng field. Khi chuyển sang contract được quản lý, usage và version có thể được quan sát rõ hơn.

## 11. Database migration ownership

Mỗi schema cần một nhóm có thẩm quyền thay đổi. Một mô hình:

~~~text
Database cluster
  |
  +-- order_db
  |     owner: order-domain
  |     migrations: order repository
  |
  +-- payment_db
  |     owner: payment-domain
  |     migrations: payment repository
  |
  +-- inventory_db
        owner: inventory-domain
        migrations: inventory repository
~~~

Quy tắc:

- Mỗi schema có migration owner.
- Runtime service không tự chạy DDL.
- Migration được version trong repository phù hợp.
- Pipeline kiểm tra thứ tự và khả năng tương thích.
- Dùng expand–migrate–contract cho rolling deployments.
- Có backup/restore strategy trước thay đổi phá dữ liệu.
- Có kiểm soát lock duration và impact trên production.
- Không cho team khác tự sửa schema owner để giải quyết query tạm thời.

Nếu dùng một database cluster chung, platform team có thể quản lý engine upgrades, backups và capacity; domain teams quản lý schema thuộc domain. Phân chia này phải được ghi trong ownership model.

## 12. Transaction xuyên domain và cám dỗ dùng shared database

Một lý do thường được đưa ra để dùng chung database là cần transaction ACID xuyên nhiều bảng.

Ví dụ:

~~~text
BEGIN
  INSERT order
  UPDATE inventory
  INSERT payment
COMMIT
~~~

Nếu cả ba bảng cùng nằm trong một database, transaction đơn giản. Nhưng điều đó có thể trộn ba domain với state machines và quyền sở hữu khác nhau.

Cần hỏi:

- Đây có thực sự là một invariant phải commit atomically?
- Các dữ kiện có cùng bounded context không?
- Có external side effect không?
- Có thể chấp nhận trạng thái trung gian không?
- Có thể dùng reservation, saga hoặc outbox không?
- Có cần một domain orchestration owner không?

Với Order, Inventory và Payment độc lập, một workflow có thể là:

~~~text
Create Order (PENDING)
      |
      v
Reserve Inventory
      |
      v
Authorize Payment
      |
      v
Confirm Order
      |
      +--> On failure: release reservation / compensate
~~~

Đây là một saga hoặc workflow có bước và hành động bù. Nó phức tạp hơn local transaction, nhưng giữ ownership và cho phép từng domain thực thi quy tắc riêng.

Không phải mọi transaction phân tán đều cần saga phức tạp; có thể có orchestration hoặc choreography tùy workflow. Quan trọng là trạng thái trung gian, timeout, retry, idempotency và compensation phải được thiết kế rõ.

## 13. Transactional outbox thay cho đọc bảng của nhau

Nếu một service cần thông báo thay đổi, không nên yêu cầu consumer query trực tiếp bảng nguồn để phát hiện.

Một pattern phổ biến:

~~~text
Order DB transaction
  |
  +--> INSERT orders
  +--> INSERT outbox_events
  |
  +--> COMMIT
          |
          v
      Outbox relay / CDC
          |
          v
      Message broker
          |
          +--> Inventory consumer
          +--> Notification consumer
          +--> Reporting consumer
~~~

Outbox record được commit cùng transaction với thay đổi nghiệp vụ. Relay có thể publish event theo delivery semantics đã chọn. Consumers xử lý idempotent và duy trì projection riêng.

Lợi ích:

- Consumer không cần đọc bảng nội bộ.
- Producer kiểm soát event semantics.
- Có thể quan sát delivery lag và retry.
- Consumers không phải deploy cùng database migration.
- Data ownership rõ hơn.

Outbox không tự bảo đảm exactly-once end-to-end. Publish có thể lặp, consumer phải deduplicate hoặc idempotent; event contract cần event ID, aggregate ID/version và schema evolution policy.

## 14. Read models và dữ liệu sao chép có kiểm soát

Một consumer cần dữ liệu từ nhiều domain có thể xây read model:

~~~text
Order events --------+
Payment events ------+--> Projection builder --> Customer Order View
Shipment events -----+                         |
Customer events -----+                         v
                                               Query API
~~~

Read model được sở hữu bởi team tiêu thụ hoặc một domain phù hợp, với contract nguồn rõ ràng.

Cần quy định:

- Fields được lấy từ nguồn nào.
- Freshness objective và watermark.
- Cách xử lý late/duplicate/out-of-order events.
- Rebuild/backfill và schema version.
- Reconciliation với source of truth.
- Quyền truy cập và data minimization.
- Owner chịu trách nhiệm khi projection sai.

Bản sao có thể stale trong một cửa sổ chấp nhận. Nếu workflow cần quyết định tài chính hoặc reservation, phải truy vấn/ủy quyền qua domain có thẩm quyền theo semantics phù hợp.

**Read model không phải một nguồn sự thật thứ hai.** Nó là phép chiếu có mục đích, có thể tái tạo và có quy tắc freshness.

## 15. CQRS: Tách mô hình ghi và đọc mà không phá ownership

CQRS có thể hữu ích khi write model cần invariants chặt chẽ, còn read model cần dữ liệu tổng hợp từ nhiều nguồn.

~~~text
Commands
   |
   v
Domain write model
   |
   +--> Own database
   +--> Outbox/events
              |
              v
         Read projections
              |
              v
            Queries
~~~

Write model sở hữu state và quyết định hợp lệ. Read model phục vụ query theo nhu cầu consumer.

CQRS không bắt buộc phải dùng event sourcing hoặc nhiều database server. Có thể dùng một database với read views nếu quy mô nhỏ, miễn là ownership và write paths rõ.

Không áp CQRS chỉ để tránh một query join. Cần cân nhắc thêm pipeline, eventual consistency, backfill, monitoring và data lifecycle.

## 16. Reporting và analytics không nên đọc tùy tiện OLTP tables

Reporting query trực tiếp các bảng giao dịch có thể gây:

- Full scans và locks ảnh hưởng API.
- Query phụ thuộc schema nội bộ.
- PII được đọc vượt mục đích.
- Join logic lặp lại trong nhiều dashboard.
- Kết quả không nhất quán khi các bảng cập nhật khác thời điểm.
- Không có data freshness hoặc lineage rõ.

Các lựa chọn:

- Read replica chuyên cho reporting nếu phù hợp.
- CDC pipeline vào warehouse.
- Domain events và analytical model.
- Published views với owner và contract.
- Snapshot/export theo lịch.

Read replica vẫn là bản sao của database; nếu consumer phụ thuộc trực tiếp vào schema nội bộ, coupling schema chưa được giải quyết. Cần một contract cho dataset, views hoặc warehouse model.

## 17. Shared database và performance coupling

Một database chung tạo resource contention:

~~~text
Shared DB
  |
  +-- Order API: short OLTP transactions
  +-- Payment API: critical ledger writes
  +-- Reporting: long analytical scans
  +-- Batch jobs: large updates
~~~

Một báo cáo chạy lâu có thể chiếm CPU, I/O, memory, locks hoặc connections khiến payment/order latency tăng.

Các biện pháp giảm tác động:

- Giới hạn connection pools theo service.
- Tách workload bằng read replicas hoặc warehouse.
- Query timeout và resource governance.
- Index/partition phù hợp.
- Tránh transaction dài.
- Schedule batch vào thời điểm phù hợp.
- Theo dõi locks, IOPS, CPU, replication lag và connection saturation.
- Tách cluster khi yêu cầu isolation đủ lớn.

Tuy nhiên, tối ưu tài nguyên không thay thế ownership. Hai service có connection pool riêng nhưng cùng ghi bảng của nhau vẫn bị coupling ở schema và semantics.

## 18. Shared database làm tăng blast radius

Một sự cố có thể tác động nhiều domain:

- Migration lỗi làm cả Order và Payment không khởi động.
- Database failover làm tất cả service mất kết nối.
- Credential bị lộ cho phép truy cập nhiều domain.
- Một query sai làm khóa bảng dùng chung.
- Một batch delete xóa dữ liệu nhiều service.
- Một schema change phá nhiều consumers.
- Một database quota hoặc storage full làm toàn bộ hệ thống ngừng ghi.

Có thể giảm blast radius bằng:

- Schema/database roles riêng.
- Quota và connection limits.
- Workload isolation.
- Backup và restore ownership.
- Maintenance/deployment windows có kiểm soát.
- Database cluster separation theo criticality.
- Independent failure domains khi cần.

Nếu Payment có criticality cao hơn Reporting, dùng cùng một cluster có thể vẫn chấp nhận được nhưng phải có capacity isolation, backup policy, access boundary và recovery priority rõ ràng.

## 19. Shared database và testing

Khi service test dùng chung database hoặc schema với nhiều service:

- Test có thể phụ thuộc dữ liệu do test khác tạo.
- Cleanup có thể xóa dữ liệu của team khác.
- Migration order khó xác định.
- Integration tests trở nên chậm và flaky.
- Khó chạy nhiều test song song.
- Test fixture bị phụ thuộc vào schema toàn hệ thống.

Cách cải thiện:

- Database/schema riêng theo service hoặc test suite.
- Ephemeral database cho integration tests khi phù hợp.
- Migration fixtures được version hóa.
- Contract tests cho API/events.
- Synthetic test data và tenant isolation.
- Không dùng production PII trong môi trường test nếu chưa có chính sách bảo vệ.
- Test migration theo cả upgrade và compatibility window.

Một service có thể cần integration với database shared infrastructure, nhưng test phải xác định rõ dữ liệu và schema nào thuộc quyền sở hữu của nó.

## 20. Những trường hợp dùng chung hạ tầng database vẫn hợp lý

Không phải mọi chia sẻ vật lý đều là anti-pattern. Các tình huống có thể hợp lý:

- Nhiều database riêng trên một managed cluster để giảm chi phí.
- Nhiều schema có ownership rõ và role tách biệt.
- Một modular monolith có nhiều module cùng bounded context và cùng owner.
- Một read-only analytics user truy cập published views được duyệt.
- Shared database platform cung cấp engine, backup, monitoring và patching.
- Một hệ thống nhỏ đang trong giai đoạn chuyển tiếp, có kế hoạch ownership rõ.

Điều kiện quan trọng:

1. Mỗi dataset có owner.
2. Runtime roles chỉ có quyền cần thiết.
3. Schema migration có người chịu trách nhiệm.
4. Service khác không sửa bảng nội bộ tùy ý.
5. Consumer dùng API, event hoặc published data contract.
6. Performance và failure isolation được đo.
7. Có lộ trình tách khi workload/criticality tăng.

**Chia sẻ máy chủ database có thể là quyết định hạ tầng. Chia sẻ quyền quyết định dữ liệu giữa các domain là vấn đề kiến trúc.**

## 21. Nhận diện shared database anti-pattern trong thực tế

Các dấu hiệu cần điều tra:

- Repository của nhiều service chứa query tới cùng bảng.
- Migration của service A được đặt trong repository service B.
- Nhiều database users có quyền owner/superuser.
- Có stored procedures được nhiều domain gọi và sửa.
- Một team không thể release vì chờ migration của team khác.
- Incident database thường ảnh hưởng nhiều domain.
- Có bảng chứa cột của nhiều bounded contexts.
- Service gọi database trực tiếp để đọc dữ liệu domain khác.
- Team dùng database triggers để đồng bộ sang service khác mà không có contract.
- Không có catalog chỉ rõ table/schema owner.
- Không thể biết consumer nào đang sử dụng một column.
- Một report query làm chậm API production.
- Việc restore một domain đòi hỏi restore toàn bộ database.
- Không có audit xác định service nào đã sửa record.

Một dấu hiệu đơn lẻ chưa chứng minh phải tách database ngay. Cần xem ownership, criticality, workload và mức độ coupling thực tế.

## 22. Quy trình kiểm kê ownership hiện tại

Có thể bắt đầu bằng một inventory:

| Dataset/Table | Domain | Writer | Readers | Owner | Classification |
|---|---|---|---|---|---|
| orders | Order | Order API | Order, Reporting | Order team | Internal |
| payment_ledger | Payment | Payment API | Payment, Finance projection | Payment team | Restricted |
| inventory_reservations | Inventory | Inventory API | Inventory, Order projection | Inventory team | Internal |
| customer_profiles | Customer | Customer API | Customer, approved consumers | Customer team | Personal data |
| search_documents | Search | Search indexer | Search API | Search team | Derived |

Đây là ví dụ. Khi kiểm kê thực tế, cần xác định:

- Schema/table/view/procedure nào tồn tại.
- Service principal nào có quyền đọc/ghi.
- Query patterns và application dependencies.
- Migration history và repository owner.
- Data lineage và event producers/consumers.
- Retention, backup và restore dependencies.
- PII/financial classification.
- Peak query volume và resource consumption.

Có thể dùng database catalog, query logs, IAM grants, code search và deployment metadata để thu thập bằng chứng. Không suy luận owner chỉ từ tên bảng.

## 23. Phân loại quyền truy cập theo ownership

Một ma trận tham khảo:

| Vai trò | Quyền thường cần |
|---|---|
| Order runtime | DML trên order schema theo use cases |
| Payment runtime | DML trên payment schema theo domain rules |
| Reporting runtime | SELECT trên published datasets/views |
| Migration pipeline | DDL theo schema owner, chỉ trong release path |
| Backup agent | Đọc/backup theo policy, không có quyền xóa tùy tiện |
| Operator | Quyền hỗ trợ có thời hạn và audit |
| Developer local | Synthetic/test database, không tự động có production access |

Cần cân nhắc:

- Role inheritance có thể vô tình cấp quyền rộng.
- Default privileges cho objects mới.
- Sequence privileges và stored procedures.
- Views có thể chạy với owner privileges tùy cấu hình engine.
- Row-level security cần test cả owner/bypass roles.
- Connection pooling phải giữ đúng database identity/tenant context.
- Secrets rotation và audit.
- Emergency access phải có expiry.

**Một schema riêng nhưng mọi service dùng cùng admin credential không tạo isolation thực chất.**

## 24. Chiến lược chuyển từ shared database sang ownership rõ ràng

Không cần tách mọi thứ cùng lúc. Một lộ trình:

1. **Inventory:** xác định tables, writers, readers, dependencies và owners.
2. **Boundaries:** xác định domain nào sở hữu từng dữ kiện và invariant.
3. **Stop new coupling:** không cho thêm cross-domain writes; mọi ngoại lệ cần owner.
4. **Separate permissions:** tạo roles và thu hẹp grants theo domain.
5. **Publish contracts:** tạo API/events/views cho consumers.
6. **Move writes:** chuyển write path về domain owner.
7. **Build projections:** chuyển consumers sang read models hoặc events.
8. **Migrate schema/data:** backfill và đồng bộ incremental có kiểm chứng.
9. **Cut over:** chọn một write authority tại thời điểm rõ.
10. **Remove legacy access:** thu hồi quyền đọc/ghi trực tiếp khi usage bằng zero.
11. **Separate infrastructure:** nếu cần, chuyển database sang cluster riêng.
12. **Observe:** kiểm tra SLO, lag, query cost và recurrence.

Bước 3 rất quan trọng: nếu tiếp tục tạo cross-domain writes trong khi đang tách, migration sẽ luôn phải chạy theo một mục tiêu thay đổi.

## 25. Strangler pattern cho quyền sở hữu dữ liệu

Có thể chuyển từng bảng hoặc capability qua một façade:

~~~text
Consumers
   |
   v
Published Data/API Boundary
   |
   +---- legacy path ----> Shared Database
   |
   +---- new path ------> Domain-owned Database
~~~

Ban đầu façade có thể đọc từ shared database. Sau khi domain owner nhận quyền ghi, façade chuyển sang API hoặc projection mới.

Cần xác định rõ:

- Bảng nào là source of truth trong từng giai đoạn.
- Ai được ghi trong mỗi giai đoạn.
- Cách đồng bộ dữ liệu thay đổi.
- Khi nào chuyển consumer.
- Cách đối soát trước cutover.
- Cách rollback nếu target sai.
- Khi nào thu hồi legacy permissions.

Không để façade duy trì hai nơi cùng được quyền ghi vô thời hạn. Nó chỉ là công cụ chuyển đổi.

## 26. Data migration: Snapshot, backfill và change capture

Một quy trình điển hình:

~~~text
Legacy shared table
       |
       +--> consistent snapshot
       |
       +--> CDC/change log
                 |
                 v
           New domain database
                 |
                 v
          Backfill historical rows
                 |
                 v
          Apply incremental changes
                 |
                 v
          Reconcile keys and values
                 |
                 v
          Controlled write cutover
~~~

Những điều kiện cần:

- Stable primary keys và tenant scope.
- Mapping rõ cho IDs, enum, nulls và units.
- Snapshot nhất quán theo database engine.
- CDC checkpoint và ordering semantics.
- Idempotent import/upsert.
- Xử lý deletes/tombstones.
- Reconciliation count, keyed values và business invariants.
- Cutover window có write freeze hoặc cơ chế đồng bộ đã chứng minh.
- Backup và rollback/compensation.
- Quy trình retire old writers.

Không dùng row count duy nhất để xác nhận migration. Một bảng có thể đủ số dòng nhưng amount, tenant mapping hoặc status sai.

## 27. Tránh dual-write khi tách database

Một cách nguy hiểm:

~~~text
Order API
   |
   +--> write shared database
   |
   +--> write new order database
~~~

Nếu write đầu thành công và write thứ hai thất bại, hai nguồn lệch nhau. Nếu retry, có thể duplicate. Nếu thứ tự ngược lại, legacy consumer có thể đọc dữ liệu chưa được đồng bộ.

Các lựa chọn an toàn hơn tùy tình huống:

- Transactional outbox ở nguồn có thẩm quyền và consumer cập nhật target.
- CDC từ database cũ tới database mới.
- Một write authority duy nhất, các hệ khác là read-only projection.
- Change log bền vững và replay có checkpoint.
- Domain command chuyển write path sau cutover.
- Reconciliation và repair có audit trong giai đoạn chuyển.

Nếu buộc phải dual-write, cần idempotency, failure recovery, reconciliation, monitoring và thời hạn kết thúc. Không coi hai lệnh SQL trong cùng một application method là atomic khi chúng đi tới hai database độc lập.

## 28. Xử lý deletes và dữ liệu lịch sử

Khi chuyển dữ liệu, cần hiểu:

- Hard delete có được phát hiện qua CDC không?
- Soft delete có semantics nào?
- Tombstone được giữ bao lâu?
- Có record bị xóa theo yêu cầu privacy không?
- Historical snapshot có được phép phục hồi record đã xóa không?
- Consumer có cần biết một entity đã bị xóa?
- Có legal hold hoặc retention obligation?
- Các ID có thể được tái sử dụng không?

Nếu target nhận snapshot cũ nhưng không nhận delete events, nó có thể tái sinh dữ liệu không còn hợp lệ.

**Deletion là một phần của data contract.** Không chỉ insert/update mới cần đồng bộ.

## 29. Transaction boundary sau khi ownership được tách

Khi mỗi domain sở hữu database riêng, transaction chỉ bảo đảm atomicity trong boundary mà nó quản lý. Workflow liên domain cần mô hình rõ:

- **Saga orchestration:** một coordinator điều phối các bước và compensation.
- **Choreography:** services phản ứng với events theo contract.
- **Reservation/hold:** domain tạo trạng thái tạm có expiry để bảo vệ tài nguyên.
- **Idempotent commands:** retry không tạo side effect trùng.
- **Reconciliation:** phát hiện và sửa trạng thái cuối không khớp.
- **Outbox/inbox:** giữ tính bền vững giữa database và broker.

Ví dụ inventory reservation:

~~~text
Order Created (PENDING)
      |
      v
Inventory Reserve
      |
      +--> RESERVED
      |       |
      |       v
      |    Payment succeeds
      |       |
      |       v
      |    Order confirmed
      |
      +--> REJECTED / timeout
              |
              v
         Order cancelled or retry policy
~~~

Reservation có expiry và state transitions rõ. Order không cập nhật trực tiếp cột reserved trong database Inventory.

## 30. Reporting cần dữ liệu liên domain nhưng không cần quyền sở hữu nguồn

Một data warehouse có thể nhận dữ liệu từ nhiều domains:

~~~text
Order events ----+
Payment events --+--> Raw/Staging --> Curated warehouse --> BI
Inventory events-+
Customer events -+
~~~

Warehouse team có thể sở hữu transformations và analytical models, nhưng domain owners vẫn sở hữu ý nghĩa nguồn. Cần contract về:

- Schema và semantic definitions.
- Freshness/watermark.
- Deletion và correction events.
- Data classification.
- Lineage và source references.
- Reconciliation.
- Consumer access và retention.

Không cho BI dashboard sửa nguồn chỉ để số liệu khớp. Sai lệch phải được sửa ở domain owner hoặc transformation owner đúng chỗ.

## 31. Khi nào shared database vẫn có thể chấp nhận?

Có thể chấp nhận nếu:

- Các module cùng một bounded context và cùng owner.
- Ứng dụng thực chất là modular monolith.
- Chưa có nhu cầu deploy/scale/security isolation độc lập.
- Schema ownership và migration process rõ.
- Runtime access được giới hạn.
- Shared resource impact được đo và chấp nhận.
- Có lộ trình thay đổi khi quy mô tăng.

Ví dụ một modular monolith có Order, Pricing và Tax modules cùng dùng một database transaction. Đây có thể là thiết kế tốt nếu module boundaries rõ và team chịu trách nhiệm thống nhất.

Shared database trở thành anti-pattern khi nhiều domain độc lập **đọc/ghi bảng nội bộ của nhau và thay đổi không thể tiến hành độc lập**.

## 32. Decision matrix: Nên tách hay giữ chung?

| Tiêu chí | Có thể giữ chung | Nên tách ownership/database |
|---|---|---|
| Domain | Cùng bounded context | Khác domain |
| Team | Cùng owner/lifecycle | Nhiều team có trách nhiệm riêng |
| Writes | Một module sở hữu | Nhiều service cùng ghi |
| Transactions | Cùng invariant nội bộ | Transaction xuyên domain thường xuyên |
| Security | Cùng classification/trust | Quyền hoặc dữ liệu nhạy cảm khác |
| Scaling | Workload tương tự | Một workload ảnh hưởng workload khác |
| Release | Cùng release unit chấp nhận được | Migration/release liên tục khóa nhau |
| Failure domain | Chấp nhận chung | Cần isolation/DR riêng |
| Data access | Module APIs rõ | Query bảng nội bộ lẫn nhau |
| Cost | Cluster chung tiết kiệm và đủ headroom | Contention/incident cost cao |

Không có điểm số tuyệt đối. Một điều kiện bảo mật hoặc compliance có thể buộc tách dù chi phí cao. Ngược lại, cùng cluster vẫn có thể đáp ứng nếu ownership logic và isolation được kiểm chứng.

## 33. Ví dụ: Order và Payment

Một shared schema:

~~~text
shop_db
  orders
  order_items
  payments
  payment_attempts
  refunds
  customers
~~~

Order API có thể UPDATE payments.status; Payment API có thể UPDATE orders.status. Reporting join mọi bảng.

Các vấn đề:

- Không rõ ai được quyết định trạng thái cuối.
- Payment migration có thể phá Order.
- Order có thể bỏ qua refund/chargeback semantics.
- Credentials có thể cho phép sửa ledger.
- Khó audit ai tạo trạng thái PAID.
- Một transaction SQL có thể che giấu external provider side effect đã xảy ra.

Thiết kế rõ hơn:

~~~text
Order database
  orders
  order_items
  payment_reference
       |
       | API / events
       v
Payment database
  payment_attempts
  ledger_entries
  refunds
  provider_references
~~~

Order sở hữu lifecycle đơn hàng. Payment sở hữu giao dịch tiền. Payment công bố events như PaymentCaptured hoặc PaymentRefunded theo contract; Order cập nhật projection/state qua domain handler hợp lệ.

Nếu Order cần hiển thị payment status, nó có thể lưu projection và thời điểm cập nhật. Khi quyết định refund, phải gọi Payment domain.

## 34. Ví dụ: Customer data và snapshot nghiệp vụ

Một order đã được đặt có thể cần giữ tên và địa chỉ tại thời điểm mua để phục vụ hóa đơn/giao hàng. Customer profile hiện tại có thể thay đổi sau đó.

Nếu Order luôn join trực tiếp bảng Customer, hóa đơn lịch sử có thể hiển thị địa chỉ mới thay vì địa chỉ tại thời điểm giao dịch.

Thiết kế có thể:

- Customer service sở hữu hồ sơ hiện tại.
- Order lưu snapshot các field cần thiết tại thời điểm đặt hàng theo contract.
- Snapshot có source/version/timestamp phù hợp.
- Các field nhạy cảm được bảo vệ và retention đúng policy.
- Thay đổi hồ sơ mới không tự sửa chứng từ lịch sử.

Đây là ví dụ cho thấy **data duplication có chủ đích có thể đúng**, miễn là semantics rõ: snapshot là sự thật tại thời điểm order, không phải bản sao live của customer profile.

## 35. Ví dụ: Tách shared reporting queries

Một báo cáo doanh thu hiện query trực tiếp orders và payments trên OLTP database:

~~~sql
SELECT
    DATE(o.created_at) AS order_day,
    SUM(p.captured_amount_minor) AS captured_total
FROM orders o
JOIN payments p
  ON p.order_id = o.order_id
WHERE p.status = 'CAPTURED'
GROUP BY DATE(o.created_at);
~~~

Nếu query này chạy liên tục trên database giao dịch, có thể ảnh hưởng latency và gắn Reporting với schema nội bộ của hai domain.

Một hướng khác:

1. Payment phát settlement/capture events.
2. Order phát order lifecycle events.
3. Warehouse ingest dữ liệu theo contract.
4. Transformation áp dụng business rules và reconciliation.
5. Dashboard đọc curated dataset.
6. Domain owners xác nhận semantics, Finance xác nhận quy tắc doanh thu.

Query phân tích vẫn có thể tồn tại, nhưng chạy trên hệ thống được thiết kế cho analytical workloads và có freshness/data quality SLO riêng.

## 36. Testing khi chuyển ownership

Bộ kiểm tra cần gồm:

### Schema và quyền

- Runtime role của Order không ghi được payment tables.
- Runtime role của Payment không ghi được order tables.
- Migration role có quyền đúng phạm vi.
- Views/roles không vô tình mở quyền rộng.
- Tenant isolation vẫn hoạt động.

### Data migration

- Count và keyed records khớp trong phạm vi.
- Amount, currency, status và timestamps đúng semantics.
- Deletes/tombstones được xử lý.
- CDC không bỏ gap hoặc duplicate không kiểm soát.
- Backfill restart vẫn idempotent.
- Cutover có một write authority.

### Application behavior

- APIs/events tương thích.
- Retry không tạo duplicate side effects.
- Outbox/inbox và consumer offsets đúng.
- Workflow liên domain xử lý timeout/compensation.
- Read models có freshness đúng SLO.

### Performance/resilience

- Query load không làm quá tải source.
- Connection pools có giới hạn.
- Database failover và restore được thử.
- Consumer backlog có thể catch up.
- Một domain failure không gây outage ngoài phạm vi dự kiến.

## 37. Runbook khi phát hiện service ghi vào database của domain khác

1. Xác định principal, query, bảng và operation thực tế.
2. Xác nhận service nào sở hữu dữ liệu và business invariant liên quan.
3. Xác định consumers/queries phụ thuộc vào schema hiện tại.
4. Đánh giá impact bảo mật và dữ liệu đã bị thay đổi.
5. Tạm dừng hoặc giới hạn write path nếu có nguy cơ đang tiếp diễn, theo incident policy.
6. Ghi nhận audit evidence và transaction IDs.
7. Chuyển thao tác về API/command của domain owner.
8. Nếu cần sửa dữ liệu, dùng correction workflow có phê duyệt.
9. Thu hẹp grants và credentials sau khi xác nhận không còn dependency hợp lệ.
10. Thêm tests/policy ngăn tái diễn.
11. Cập nhật catalog, contract và runbook.
12. Đối soát dữ liệu liên quan và đóng incident khi có bằng chứng.

Không thu hồi quyền production một cách đột ngột nếu chưa hiểu dependency và có kế hoạch xử lý; nhưng quyền rộng bất thường cần được đánh giá theo security incident policy.

## 38. Các anti-pattern cần tránh

**1. Một database user admin cho mọi service.** Một credential bị lộ có thể ảnh hưởng toàn bộ domain.

**2. Nhiều service cùng ghi một bảng.** Không có một owner quyết định invariants và trạng thái cuối.

**3. Query trực tiếp bảng của service khác.** Schema nội bộ trở thành API ngầm.

**4. Stored procedure dùng chung chứa business logic của nhiều domain.** Ownership và versioning khó xác định.

**5. Dùng trigger để đồng bộ domain mà không có contract.** Side effects khó quan sát và kiểm thử.

**6. Shared schema không có migration owner.** Một thay đổi có thể phá nhiều service.

**7. Gộp transaction chỉ để tránh saga.** Có thể làm mờ domain boundary và external side effects.

**8. Dùng read replica nhưng vẫn phụ thuộc schema nội bộ.** Giảm tải primary nhưng không giải quyết coupling.

**9. Reporting full-scan OLTP.** Analytical workload có thể gây contention.

**10. Dual-write không có outbox/reconciliation.** Hai database có thể lệch sau partial failure.

**11. Chỉ so row counts khi migration.** Không phát hiện sai values, units hoặc tenant mappings.

**12. Cấp quyền đọc rộng vì “chỉ đọc thì an toàn”.** PII và financial data vẫn có thể bị lộ.

**13. Một cluster được coi là một ownership boundary.** Hạ tầng chung không đồng nghĩa dữ liệu chung.

**14. Mỗi service có connection string riêng nhưng vẫn sửa bảng nhau.** Tên credential không tạo ra ownership.

**15. Chuyển schema nhưng không chuyển migration history.** Không biết version nào là nguồn chuẩn.

**16. Giữ legacy writers vô thời hạn.** Không thể kết thúc migration và thu hồi quyền.

**17. Tái sinh dữ liệu đã xóa từ snapshot cũ.** Không áp dụng tombstone/privacy deletion policy.

**18. Không có reconciliation sau cutover.** Sai lệch có thể tồn tại mà không ai phát hiện.

## 39. Checklist thiết kế quyền sở hữu dữ liệu

1. Mỗi dataset/table có một domain owner được ghi nhận?
2. Mỗi field quan trọng có semantics và source of truth?
3. Service nào được phép ghi và vì sao?
4. Runtime roles có least privilege?
5. Migration role có tách khỏi runtime role?
6. Service khác truy cập dữ liệu qua contract hoặc published projection?
7. Cross-domain writes có bị ngăn hoặc được phê duyệt rõ?
8. Read access có data classification và mục đích?
9. Schema changes có owner, compatibility window và deprecation?
10. Có transaction boundary đúng với bounded context?
11. Có outbox/inbox hoặc cơ chế delivery phù hợp?
12. Consumer có idempotency và xử lý duplicate/late events?
13. Read models có freshness SLO và lineage?
14. Reporting workload có tách khỏi OLTP khi cần?
15. Database resource contention được theo dõi?
16. Backup/restore có thể thực hiện theo criticality?
17. Migration có snapshot, CDC, checkpoint và reconciliation?
18. Có một write authority rõ trong cutover?
19. Deletes/tombstones và privacy lifecycle được giữ?
20. Có audit cho privileged reads/writes và correction?
21. Service catalog có owner, consumers và data dependencies?
22. Tests có chứng minh service không ghi vào domain khác?
23. Incident runbook xác định ai quyết định và ai thực hiện sửa?
24. Có review khi workload/team/security boundary thay đổi?

## 40. Kết luận

**Dùng chung cơ sở dữ liệu trở thành sai lầm thiết kế khi các microservices cùng truy cập và thay đổi dữ liệu thuộc domain của nhau mà không có quyền sở hữu rõ ràng.** Hệ quả là schema, transaction, bảo mật, performance và release bị liên kết chặt, làm mất nhiều lợi ích mà việc tách service hướng tới.

Một thiết kế bền vững cần:

- **Một owner cho mỗi nguồn sự thật:** owner định nghĩa semantics, write permissions, migration và correction.
- **Ranh giới truy cập rõ:** service dùng API, commands, events hoặc published read models.
- **Least privilege:** tách runtime, migration, reporting, backup và operator identities.
- **Transaction đúng domain:** dùng local ACID khi cùng bounded context; dùng saga/outbox/idempotency khi workflow thực sự xuyên domain.
- **Migration có kiểm soát:** inventory, snapshot/CDC, backfill, reconciliation, cutover và thu hồi legacy access.
- **Chia sẻ hạ tầng có chủ đích:** một cluster có thể phục vụ nhiều database nếu ownership và isolation logic được bảo vệ.

**Câu hỏi tự kiểm tra:** *Nếu Order Service có thể UPDATE trực tiếp payment_ledger và Payment Service có thể sửa orders.status, khi một giao dịch sai trạng thái hoặc bị ghi trùng, ai có thẩm quyền quyết định dữ liệu đúng, service nào chịu trách nhiệm sửa, và những consumer nào có thể bị ảnh hưởng bởi migration tiếp theo?*

Khi câu trả lời được thể hiện bằng **data ownership, permissions, contracts, migration history và audit evidence**, hệ thống có thể chia sẻ hạ tầng database mà vẫn giữ được ranh giới domain và quyền kiểm soát dữ liệu.
