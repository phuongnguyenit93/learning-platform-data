# Database per Service: Cô lập dữ liệu logic không đồng nghĩa máy chủ vật lý riêng

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Quyền sở hữu dữ liệu.
>
> **Mục tiêu học tập:** giải thích chính xác mô hình Database per Service, phân biệt ranh giới sở hữu dữ liệu với mức cô lập triển khai vật lý, lựa chọn mức cô lập phù hợp, ngăn các service truy cập dữ liệu riêng của nhau, hiểu chi phí giao dịch/truy vấn liên service và có lộ trình áp dụng từ hệ thống dùng database chung.

## 1. Vấn đề cần giải quyết

Một hệ thống có nhiều microservices nhưng toàn bộ service đều đọc, sửa và tự thay đổi cùng các bảng thường **chưa thực sự có ranh giới dữ liệu độc lập**.

Giả sử hệ thương mại điện tử có:

- **Order Service:** xử lý vòng đời đơn hàng và các trạng thái của đơn.
- **Inventory Service:** quản lý số lượng tồn, giữ chỗ và giải phóng reservation.
- **Payment Service:** xác nhận thanh toán, hoàn tiền và đối soát.
- **Catalog Service:** mô tả và công bố thông tin sản phẩm.

Nếu Order truy cập trực tiếp bảng inventory.reservations và tự giảm tồn, quy tắc giữ hàng đã bị phân tán sang Order. Inventory đổi thiết kế schema sẽ có thể làm Order lỗi; nhiều service còn có khả năng thay đổi dữ liệu theo các thứ tự không được kiểm soát.

~~~text
             THIẾT KẾ COUPLING CAO

Order Service ----------+
Inventory Service ------+----> Shared database
Payment Service --------+       orders
Catalog Service --------+       reservations
                                payments
                                products

Nhiều service có thể SELECT/UPDATE cùng bảng của nhau.
~~~

Trong mô hình **Database per Service**, mỗi service sở hữu một **kho dữ liệu logic được bảo vệ**, chứa những dữ liệu và quy tắc lưu trữ mà service đó có quyền quyết định. Service khác tương tác thông qua **API, command hoặc integration event công khai**, thay vì truy vấn/sửa trực tiếp dữ liệu nội bộ.

~~~text
          RANH GIỚI SỞ HỮU DỮ LIỆU

Order Service    ---> Order data owner
Inventory Service---> Inventory data owner
Payment Service  ---> Payment data owner
Catalog Service  ---> Catalog data owner

Order ---- ReserveStock command ----> Inventory
Order <--- ReservationConfirmed event - Inventory

Không có quyền UPDATE trực tiếp bảng reservation của Inventory
từ tài khoản ứng dụng Order.
~~~

**Điểm then chốt:** “per service” mô tả **quyền sở hữu, quyền truy cập và vòng đời thay đổi của dữ liệu**, không bắt buộc mỗi service phải có một máy chủ vật lý độc lập.

## 2. Database per Service thực sự đòi hỏi điều gì?

Một cách hiểu thực dụng của pattern:

1. **Mỗi loại dữ liệu có một owner rõ ràng.** Owner định nghĩa schema, ý nghĩa, ràng buộc và quy tắc cập nhật.
2. **Chỉ owner có quyền ghi dữ liệu có thẩm quyền** trong phạm vi đó. Consumer không tự cập nhật các bảng nội bộ của service khác.
3. **Không coi bảng nội bộ là public contract.** Các service trao đổi qua API/event được công bố và version rõ.
4. **Schema và migration của owner có thể tiến hóa độc lập** trong giới hạn các contract đã cam kết.
5. **Transaction cục bộ chỉ bảo vệ dữ liệu bên trong ranh giới có thẩm quyền.** Workflow qua nhiều service phải xử lý thành công một phần, idempotency và trạng thái chưa chắc chắn.
6. **Quyền truy cập phải được cưỡng chế**, không chỉ dựa vào quy ước “đội này không nên chạm bảng kia”.

Để đạt các mục tiêu ấy, dữ liệu của nhiều service có thể cùng chạy trên một database server/instance, miễn hệ thống tạo được **isolation logic và ranh giới truy cập có thể thực thi**.

### 2.1. Ba câu hỏi phải tách riêng

**Câu 1 — Ai sở hữu dữ liệu?** Ví dụ Inventory sở hữu reservation và lượng tồn có thể bán. Quyết định “có được giữ một đơn vị hàng?” thuộc Inventory.

**Câu 2 — Dữ liệu được ngăn truy cập trực tiếp bằng cách nào?** Có thể dùng schema riêng và database roles/permissions, database riêng trên cùng DBMS instance, hoặc instance riêng.

**Câu 3 — Tài nguyên vật lý được triển khai ở đâu?** Có thể là cùng VM, cùng managed DB instance/cluster, các node khác nhau, một cluster chuyên biệt hoặc một dịch vụ managed độc lập.

Một nhóm có thể trả lời tốt câu 1 và 2 mà chưa cần đầu tư cô lập vật lý hoàn toàn ở câu 3.

## 3. Phân biệt các mức cô lập

### 3.1. Mức 0 — Dùng chung database và chung bảng

~~~text
One DB instance
  └── application_db
        ├── orders       <- Order và Payment đều sửa
        ├── reservations <- Order và Inventory đều sửa
        └── payments     <- Order, Payment, Billing đều đọc/sửa
~~~

Ở mức này, nhiều service có thể biết trực tiếp internal schema của nhau. Dữ liệu có thể vẫn nhất quán nếu mọi thay đổi đều phối hợp chặt, nhưng khả năng triển khai độc lập yếu; việc đổi schema rất dễ kéo theo thay đổi đồng loạt.

Không nên xem đây là Database per Service đúng nghĩa chỉ vì mỗi service có connection string riêng hoặc đã được tách thành Docker container.

### 3.2. Mức 1 — Một database, schema riêng cho từng service

~~~text
                SAME DATABASE INSTANCE
                         |
                    application_db
                         |
         +---------------+----------------+
         |               |                |
     order_data      inventory_data    payment_data
         |               |                |
    orders table     stock_balance     payments table
    order_lines      reservations      payment_attempts
         |               |                |
    order_app role  inventory_app role  payment_app role

Mỗi role chỉ có quyền cần thiết trong schema của mình.
~~~

Ưu điểm:

- Tiết kiệm công sức hạ tầng, backup infrastructure và tài nguyên khi hệ còn nhỏ.
- Dễ dùng một DBMS chung và công cụ migration hiện có.
- Có thể tạo ranh giới dữ liệu thật nếu **quyền database được phân tách đúng**.
- Dễ chuyển từ một monolith sang modular monolith hoặc các service có ownership rõ.

Giới hạn:

- CPU, RAM, disk I/O, connection limits, log/WAL, backup window và khả năng lỗi vật lý vẫn chia sẻ.
- Quyền superuser/DB admin, cấu hình instance và upgrade ảnh hưởng nhiều service.
- Một lỗi query nặng của service này có thể ảnh hưởng service khác (noisy neighbor).
- Cùng engine/version, khó tùy biến cấu hình riêng theo workload.
- Nếu các service được cấp quyền đọc/ghi qua lại, schema riêng **chỉ là cách đặt tên**, không phải isolation thực sự.

Một số DBMS có khái niệm schema khác nhau; không nên mặc định cách tạo schema/quyền trong PostgreSQL áp dụng nguyên xi cho MySQL, SQL Server hay các datastore phi quan hệ.

### 3.3. Mức 2 — Database riêng trên cùng DBMS instance/server

~~~text
                SHARED DBMS INSTANCE
                        |
             +----------+----------+
             |          |          |
         order_db   inventory_db  payment_db
             |          |          |
         order_app  inventory_app payment_app
~~~

Ở đây mỗi service có database riêng nhưng các database cùng chạy trên một DBMS server hoặc một managed instance. Cách này thường cho boundary về metadata và quyền rõ hơn so với schema trong cùng database, tùy DBMS. Mỗi service có thể có migration, tên object và credentials riêng.

**Nhưng phần cứng và tài nguyên vận hành vẫn dùng chung.** Việc tên database khác nhau không đồng nghĩa CPU, memory, disk, backup storage, network và failure domain tách nhau.

Ví dụ PostgreSQL mặc định không cho một SQL query thông thường trực tiếp JOIN bảng ở database khác trong cùng connection. Tuy nhiên những cơ chế như foreign data wrapper, dblink hoặc lớp tích hợp vẫn có thể mở đường liên kết khi được cấp quyền. Kiến trúc vẫn phải quy định **không truy cập dữ liệu nội bộ của nhau**, thay vì dựa vào việc truy vấn trực tiếp khó hơn.

Ở một số hệ, khái niệm “database” có semantics gần với “schema”; phải xác minh trên DBMS đang dùng.

### 3.4. Mức 3 — Instance hoặc cluster riêng cho từng service

~~~text
Order Service     -> Order DB instance/cluster
Inventory Service -> Inventory DB instance/cluster
Payment Service   -> Payment DB instance/cluster
~~~

Ưu điểm:

- Cô lập tài nguyên và failure domain tốt hơn.
- Có thể cấu hình sizing, engine version, maintenance window và scaling khác nhau.
- Dễ áp dụng backup/restore, network policies và mã hóa theo mức độ nhạy cảm.
- Tránh một truy vấn nặng ở Inventory làm chiếm connection pool của Order database.

Đổi lại:

- Nhiều instance/cluster, metrics, alerts, backups, certificates, secret rotation và incident runbooks hơn.
- Chi phí hạ tầng, vận hành và quản trị tăng.
- Vấn đề transaction/truy vấn liên service vẫn tồn tại; đặt database ở máy riêng **không tạo ra** hợp đồng nghiệp vụ chuẩn.
- Nếu hai service vẫn chia sẻ account có quyền rộng hoặc gọi trực tiếp nhau để đọc bảng, physical isolation chưa chắc mang lại độc lập ứng dụng.

Instance riêng có thể chạy trên managed cloud DB hoặc hạ tầng ảo hóa. Nó không bắt buộc phải là một “máy chủ vật lý” có phần cứng riêng cho từng service.

### 3.5. Mức 4 — Hạ tầng vật lý/cụm chuyên biệt

Một service có thể có tập node, VPC/network segment, storage, backup system hoặc môi trường triển khai chuyên biệt. Mức này có thể cần thiết với yêu cầu bảo mật, pháp lý, throughput, dữ liệu có độ nhạy cao hoặc failure isolation nghiêm ngặt.

Đó là một quyết định **hạ tầng và phân vùng rủi ro**, không phải điều kiện cơ bản của Database per Service. Áp dụng máy chủ vật lý riêng cho mọi microservice thường quá tốn kém và khó vận hành nếu không có nhu cầu thật.

### 3.6. Bảng so sánh mức độ cô lập

| Phương án | Ownership logic | Cô lập quyền có thể thực thi | Cô lập CPU/I/O | Độc lập upgrade/maintenance DB | Chi phí |
| --- | --- | --- | --- | --- | --- |
| Một DB, bảng dùng chung | Thường mơ hồ | Thấp | Không | Thấp | Thấp |
| Một DB, schema per service | Có nếu thực thi ownership | Có thể tốt với roles riêng | Không | Thấp | Thấp |
| Database per service trên shared instance | Có thể tốt | Có thể tốt | Không | Instance còn phụ thuộc chung | Thấp–trung bình |
| Instance/cluster per service | Có thể tốt | Tốt hơn về hạ tầng | Cao hơn | Cao hơn | Trung bình–cao |
| Hạ tầng vật lý chuyên biệt | Có thể tốt | Có thể rất cao | Rất cao nếu cấu hình đúng | Cao | Cao nhất |

“Có thể” là từ quan trọng: **không phương án hạ tầng nào tự động tạo data ownership tốt** nếu ứng dụng vẫn biết và cập nhật dữ liệu nội bộ của service khác.

## 4. Database per Service là pattern về quyền sở hữu, không chỉ deployment

Giả sử Order và Inventory có database riêng, nhưng Order mỗi lần đặt hàng gửi SQL trực tiếp tới inventory_db để cập nhật reservations. Về mặt topology, chúng ở hai database khác nhau. Về mặt domain ownership, Order vẫn đang điều khiển dữ liệu của Inventory.

Ngược lại, Order và Inventory có schema riêng trong cùng application_db, mỗi service có role riêng và chỉ trao đổi qua API/event. Dù chia sẻ DBMS server, **ranh giới nghiệp vụ và truy cập dữ liệu vẫn rõ**.

### 4.1. Dấu hiệu ownership thực chất

- Inventory là nơi duy nhất có quyền xác nhận reservation thành công.
- Order không đọc hoặc UPDATE trực tiếp bảng reservation nội bộ.
- Payment là nơi duy nhất xác định giao dịch authorize/capture/refund hợp lệ.
- Catalog có thể thay cấu trúc lưu trữ product mà Order không phải triển khai lại.
- Mọi thay đổi schema có thể được owner triển khai trong phạm vi contract tương thích.
- Service khác có thể có bản sao phục vụ đọc nhưng không được nhầm bản sao với nguồn dữ liệu có thẩm quyền.

### 4.2. Quyền đọc trực tiếp cũng có thể gây coupling

Một số đội chỉ cấm UPDATE nhưng vẫn cho tất cả service SELECT bảng của nhau. Điều này giảm nguy cơ dữ liệu bị sửa trái phép, nhưng **không tạo độc lập thay đổi**:

- Bỏ/đổi tên cột Inventory có thể làm Order lỗi.
- Consumer có thể dựa vào trạng thái tạm thời của transaction nội bộ.
- Mô hình dữ liệu của Inventory bị kéo thành public contract không chính thức.
- Query trực tiếp có thể gây tải không kiểm soát lên database của owner.
- Quyền truy cập rộng gây rủi ro bảo mật và audit.

Có thể có trường hợp cần truy cập dữ liệu trực tiếp cho migration, analytics hoặc vận hành được kiểm soát. Nhưng nên phân biệt đó là **ngoại lệ có owner, thời hạn và quyền rõ**, không phải cách giao tiếp nghiệp vụ mặc định.

## 5. Ví dụ với PostgreSQL: schema per service

Giả sử doanh nghiệp muốn bắt đầu bằng một PostgreSQL instance và một application database, nhưng tách trách nhiệm Order/Inventory/Payment.

~~~text
postgres instance
  application_db
    schema order_data
      orders
      order_lines
    schema inventory_data
      stock_balance
      reservations
    schema payment_data
      payments
      payment_attempts
~~~

Về nguyên tắc, ứng dụng Order chỉ có quyền thao tác bảng của order_data; Inventory chỉ có quyền dữ liệu inventory_data; Payment tương tự.

### 5.1. Ví dụ tạo role/schema

SQL minh họa:

~~~sql
-- Role dùng để sở hữu schema, không dùng cho traffic ứng dụng.
CREATE ROLE order_owner NOLOGIN;

-- Role đăng nhập dùng bởi Order Service.
-- Cơ chế cấp credential phải do secret management quản trị.
CREATE ROLE order_app LOGIN;

CREATE SCHEMA order_data AUTHORIZATION order_owner;

-- Cho phép Order truy cập các object cần thiết.
GRANT USAGE ON SCHEMA order_data TO order_app;

-- Thực hiện sau khi các bảng đã được migration tạo.
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA order_data
TO order_app;
~~~

Trong thực tế còn phải xét quyền trên sequences, default privileges cho bảng được tạo về sau, owner của migration, quyền kết nối database, search_path, extension và quyền mặc định của các schema khác. Ví dụ trên không phải cấu hình hardening hoàn chỉnh.

**Không cấp superuser, quyền admin hoặc quyền ghi tất cả schema cho service application** chỉ để mọi câu SQL “chạy được”. Đặc biệt không dùng cùng một tài khoản database toàn quyền cho tất cả service.

### 5.2. Quy tắc cấp quyền

| Role | Quyền thông thường | Không nên có |
| --- | --- | --- |
| order_app | DML trên order_data và những quyền kỹ thuật thật cần | UPDATE bảng reservations/payments |
| inventory_app | DML trên inventory_data | UPDATE orders hoặc payments |
| payment_app | DML trên payment_data | SELECT dữ liệu cá nhân không cần thiết của Order |
| order_migrator | DDL trong phạm vi schema/order objects | DDL trên inventory_data |
| db_operator | Quyền vận hành được kiểm soát và audit | Dùng làm tài khoản application runtime |

Mỗi service có thể dùng hai nhóm credentials: runtime tối thiểu và migration có quyền DDL trong phạm vi sở hữu. Migration credential không nên xuất hiện trong application traffic thường xuyên.

### 5.3. Ví dụ kiểm tra quyền vượt ranh giới

Một test ở staging có thể xác minh account order_app không thể sửa dữ liệu inventory_data:

~~~sql
-- Kết nối bằng order_app và thực hiện test không thay đổi production.
SELECT *
FROM inventory_data.reservations;
~~~

Nếu chính sách đặt ra là không truy cập chéo, truy vấn này phải bị chặn bởi quyền, dù bảng thực sự tồn tại. Khi viết test permission, nên thực hiện trong môi trường và dữ liệu thử phù hợp để tránh lộ dữ liệu thật.

Đừng chỉ kiểm tra ứng dụng Order “không có câu SQL ấy trong source code”. Ngày mai một thay đổi hoặc một lỗi injection có thể tạo đường truy cập mới; **database privileges là lớp phòng vệ độc lập**.

### 5.4. Schema riêng chưa bảo vệ khỏi shared-instance failures

Nếu cả ba schema dùng chung PostgreSQL instance, Inventory chạy một truy vấn nặng hoặc một transaction giữ lock/resource không hợp lý có thể tiêu thụ CPU, I/O hay connection limit của instance, ảnh hưởng Order và Payment. Tương tự, sự cố disk full hay failover của instance tác động tới toàn bộ schema.

Do đó phải phân biệt:

- **Logical isolation:** ai được đọc/ghi object nào.
- **Resource isolation:** ai chiếm CPU, memory, disk I/O, connections.
- **Failure isolation:** sự cố ở một thành phần lan sang những service nào.
- **Administrative isolation:** ai nâng version, backup, restore và thay đổi cấu hình.
- **Security isolation:** credential, encryption key, network, audit, quyền quản trị.

Schema per service giải quyết chủ yếu vấn đề **ownership và quyền logic**, không tự cung cấp tất cả những loại isolation còn lại.

## 6. Ví dụ database riêng nhưng cùng DBMS instance

~~~text
Managed DB instance: commerce-db-instance
    |
    +-- orders_db
    |     +-- orders
    |     +-- order_lines
    |
    +-- inventory_db
    |     +-- stock_balance
    |     +-- reservations
    |
    +-- payments_db
          +-- payment_attempts
          +-- refunds
~~~

Ứng dụng có connection string và credential dành cho database của mình. Mỗi service sở hữu migrations và bảng riêng. Các database này vẫn có thể dùng cùng compute instance, storage, network quota, backup facility và maintenance window.

**Không gọi đây là “mỗi microservice một máy chủ database riêng”**, vì cùng một instance vẫn có thể đặt nhiều database. Nếu hạ tầng dùng một cluster có nhiều node, một database riêng cũng chưa chắc có các node/storage riêng.

### 6.1. Vì sao chọn shared instance?

- Hệ còn ít tải và cần tránh tạo nhiều managed DB instances nhỏ.
- Đội vận hành chưa đủ nguồn lực quản lý hàng chục cụm riêng.
- Dữ liệu có yêu cầu backup/availability tương tự.
- Muốn thực thi data ownership trước khi tối ưu physical isolation.
- Cần tiến hóa từ monolith theo từng module mà không thay đổi hạ tầng ồ ạt.

### 6.2. Khi nào cần nâng cấp lên instance riêng?

- Workload một service bão hòa CPU/I/O hoặc connection limits của shared instance.
- Payment chứa dữ liệu nhạy cảm với yêu cầu bảo mật/audit nghiêm ngặt hơn.
- Một service cần RPO/RTO, replication topology, engine version hoặc maintenance window riêng.
- Restore một database có khả năng làm ảnh hưởng workload của service khác.
- Khối lượng dữ liệu hoặc mô hình truy vấn quá khác nhau, ví dụ time-series/analytical vs OLTP.
- Cần cô lập sự cố, blast radius hoặc hiệu năng theo SLO đã đo.

Đây là những lý do có thể kiểm chứng. **Không cần tách vật lý chỉ để bảng kiến trúc có thêm nhiều biểu tượng database.**

## 7. Cơ sở dữ liệu đa mô hình và polyglot persistence

Database per Service cho phép từng service cân nhắc loại lưu trữ phù hợp, nhưng không bắt buộc mỗi service dùng một engine khác nhau.

Ví dụ:

| Service | Nhu cầu chính | Một lựa chọn có thể phù hợp |
| --- | --- | --- |
| Order | Transaction và truy vấn theo trạng thái đơn | Relational OLTP |
| Inventory | Atomic reservation, kiểm soát invariant | Relational OLTP hoặc datastore có operation atomic phù hợp |
| Catalog | Dữ liệu sản phẩm linh hoạt, filter | Relational/document + search projection |
| Recommendation | Quan hệ gợi ý hoặc vector retrieval | Công cụ search/vector phù hợp |
| Analytics | Aggregate lượng lớn, truy vấn báo cáo | Data warehouse/OLAP |
| Notification | Lịch gửi và trạng thái xử lý | Relational + queue/broker |

Không nên mặc định chọn một loại datastore mới chỉ vì “microservices cần polyglot”. Mỗi engine thêm một hệ thống cần backup, observability, patching, security và đội vận hành có kiến thức phù hợp.

**Nguyên tắc:** chọn engine theo invariant, latency, scale, khả năng transaction/replication và chi phí vận hành, không theo số lượng microservices.

## 8. Data ownership khác với data location

Một record có thể có nhiều bản sao trong hệ thống nhưng chỉ một context có quyền xác định giá trị có thẩm quyền.

Ví dụ Catalog sở hữu dữ liệu mô tả hiện tại của sản phẩm. Order cần giữ tên, giá và thuế đã áp dụng tại thời điểm mua để lập lịch sử đơn. Vì thế Order có thể lưu ProductSnapshot trong order_data.

~~~text
Catalog (source of truth cho mô tả sản phẩm hiện tại)
      |
      +-- ProductPublished/ProductUpdated event
      |
      v
Order (lưu immutable PurchasedItemSnapshot khi đặt đơn)
      |
      v
Lịch sử đơn hàng độc lập với mô tả Catalog hiện tại
~~~

Dữ liệu tên sản phẩm có thể xuất hiện ở cả Catalog và Order nhưng không có nghĩa cả hai có cùng quyền sửa “sản phẩm hiện tại”. Order sở hữu snapshot của đơn; Catalog sở hữu mô tả hiện hành.

### 8.1. Shared identifier không đồng nghĩa shared table

Nhiều context cùng dùng customerId hoặc productId làm tham chiếu. Điều này có thể hợp lý nếu identifier là contract ổn định. Nhưng Order không cần phải import CustomerEntity hoặc trực tiếp JOIN bảng của Customer để hiểu tất cả trạng thái nội bộ.

### 8.2. Snapshot và cache cần freshness policy

Một service giữ bản sao dữ liệu đọc từ service khác phải nói rõ:

- Bản sao dùng cho quyết định nghiệp vụ nào?
- Chấp nhận cũ bao lâu?
- Ai publish cập nhật?
- Nếu event đến trễ hoặc mất, phát hiện bằng cách nào?
- Có cách rebuild/read model backfill không?
- Nếu quyết định yêu cầu dữ liệu mới nhất, có cần truy vấn owner trước khi commit không?

Đừng dùng một bản cache tồn kho cũ để xác nhận reservation khi invariant yêu cầu số lượng chính xác, trừ khi mô hình có cơ chế quota/escrow hoặc ownership phù hợp.

## 9. Vì sao không JOIN trực tiếp bảng của hai service?

Trong monolith, một SQL JOIN qua bảng orders và inventory thường tiện lợi. Khi ranh giới đã tách, việc để Order kết nối trực tiếp vào database Inventory để JOIN tạo **data coupling**, đặc biệt nếu Query dùng tên bảng/cột nội bộ của Inventory.

~~~text
Không nên làm ở application flow:

Order Service
    -> SELECT ... FROM order_data.orders o
       JOIN inventory_data.reservations r ON ...
~~~

Câu truy vấn có thể hợp lệ về mặt SQL trong một shared database, nhưng vi phạm ownership nếu Order không phải owner của inventory_data. Một thay đổi schema phía Inventory trở thành breaking change cho Order mà không đi qua contract API.

### 9.1. API composition

Với các query cần dữ liệu hiện tại ở mức vừa phải, một API composition layer có thể gọi nhiều service rồi ghép kết quả:

~~~text
Order Detail API
   |
   +-- Order Service: order snapshot/status
   |
   +-- Inventory Service: trạng thái reservation được phép công bố
   |
   +-- Payment Service: payment status được phép công bố
   |
   v
Response tổng hợp cho giao diện
~~~

Ưu điểm: giữ ownership rõ. Đánh đổi: thêm network calls, latency, partial failure và nguy cơ N+1 requests. Cần batching, caching, timeout budget và graceful degradation.

### 9.2. CQRS/read model/materialized view

Với dashboard hoặc query tổng hợp thường xuyên, có thể xây read model chuyên dụng từ các event công khai:

~~~text
OrderConfirmed event ------+
                           |
PaymentCaptured event -----+----> Reporting Projection
                           |             |
StockReserved event -------+             v
                                   reporting_read_model
~~~

Projection có schema riêng cho mục đích truy vấn. Nó không trở thành nơi ra quyết định có thẩm quyền thay cho Order/Payment/Inventory.

Cần có event ID, version, idempotent consumer, replay/backfill, lag metrics và reconciliation. Khi read model chậm, dashboard có thể hiển thị timestamp dữ liệu gần nhất hoặc cảnh báo chưa cập nhật.

### 9.3. Data warehouse/analytics

Các quy trình phân tích, báo cáo đa miền có thể thu thập dữ liệu qua event/CDC hoặc pipeline được quản trị, thay vì bắt các service nghiệp vụ truy vấn chéo production tables theo thời gian thực.

Với CDC, cần nhớ đây vẫn là một **contract dữ liệu**: chọn những thay đổi nào được công bố, schema compatibility, phân loại dữ liệu nhạy cảm, lifecycle và khôi phục. Không tự động cho consumer quyền đọc mọi bảng nội bộ vì “CDC tiện hơn API”.

### 9.4. Không chuyển mọi JOIN thành hàng trăm HTTP calls

Một thiết kế khiến mỗi dòng Order phải gọi Catalog và Inventory riêng lẻ có thể bị N+1 network problem. Hãy dùng immutable snapshots, batch endpoints, read models hoặc thiết kế lại trách nhiệm hiển thị. Mục tiêu là **thay coupling ẩn vào schema bằng hợp đồng ổn định**, không phải thay một SQL JOIN bằng một chuỗi REST calls không kiểm soát.

## 10. Transaction boundary: hệ quả quan trọng của Database per Service

Trong một database cục bộ, transaction có thể cập nhật nhiều bảng và rollback nguyên tử. Khi dữ liệu do các service khác nhau sở hữu, một transaction SQL của Order **không tự bảo đảm** Inventory và Payment cũng commit đồng thời.

Ví dụ checkout:

~~~text
1. Order tạo đơn PENDING.
2. Inventory reserve hàng.
3. Payment authorize/capture theo chính sách.
4. Order chuyển CONFIRMED.
5. Notification gửi sự kiện xác nhận.
~~~

Có thể xảy ra:

- Inventory đã reserve nhưng Payment từ chối.
- Payment đã xử lý nhưng response bị mất.
- Order đã commit nhưng event cho Notification chưa publish.
- Một service offline khi bước tiếp theo bắt đầu.
- Message bị gửi lặp hoặc đến sai thứ tự.

Database per Service làm những ranh giới này hiện rõ. Nó không phải nguyên nhân duy nhất gây partial failure; **mạng và transaction scope khác nhau vốn đã tạo ra những khả năng đó**.

### 10.1. Không ngầm kéo transaction qua nhiều service

Một cách triển khai dễ gây vấn đề là mở Order DB transaction, giữ lock rồi gọi Inventory và Payment qua HTTP bên trong transaction đó. Khi downstream chậm, Order giữ DB connection/lock lâu và có thể làm cạn pool.

~~~text
Tránh:

BEGIN ORDER TRANSACTION
  INSERT order
  HTTP -> Inventory reserve (chờ)
  HTTP -> Payment capture (chờ)
COMMIT ORDER TRANSACTION
~~~

Cách này không tự mang lại tính atomic giữa ba database. Nó chỉ kéo dài transaction cục bộ và thêm failure coupling.

### 10.2. Giữ invariant cục bộ trong owner

Inventory phải bảo vệ invariant “reservation được xác nhận không vượt lượng có thể giữ” trong transaction hoặc cơ chế atomic của Inventory. Order gửi lệnh ReserveStock và nhận kết quả; không tự tính tồn bằng cách sửa bảng Inventory.

~~~text
Order                            Inventory
  | ReserveStock(sku, qty, key)      |
  |--------------------------------->|
  |                                  | transaction nội bộ
  |                                  | kiểm tra + giữ hàng
  |                                  | commit
  |<---------------------------------|
  | RESERVED / OUT_OF_STOCK / UNKNOWN |
~~~

Điều này giúp Inventory thay đổi schema hoặc thuật toán mà Order không cần truy cập những chi tiết ấy.

### 10.3. Saga và state machine cho workflow liên miền

Một luồng dài có thể quản lý bằng Saga orchestration hoặc choreography, tùy độ phức tạp.

~~~text
ORDER_PENDING
    |
    v
STOCK_RESERVED
    |
    +-- Payment thành công --> ORDER_CONFIRMED
    |
    +-- Payment thất bại ---> RELEASE_RESERVATION
                                 |
                                 v
                            ORDER_FAILED
~~~

Saga không phải transaction ACID xuyên service. Nó mô hình hóa chuỗi bước, các trạng thái trung gian và compensation, cho phép xử lý partial failure một cách có chủ đích. Compensation như hoàn tiền hoặc giải phóng reservation là **thao tác nghiệp vụ mới**, không phải rollback quá khứ như chưa từng xảy ra.

### 10.4. Transactional outbox và eventual consistency

Khi một service cập nhật database riêng và phải phát integration event, có nguy cơ DB commit thành công nhưng broker publish thất bại. Transactional Outbox giải quyết bằng cách ghi dữ liệu nghiệp vụ và bản ghi outbox **trong cùng transaction cục bộ**. Một dispatcher sau đó chuyển event tới broker.

~~~text
Order DB transaction
   +-- update order status
   +-- insert outbox event
COMMIT

Outbox dispatcher -> Message broker -> Consumer
~~~

Dispatcher có thể gửi trùng, vì vậy consumer cần idempotency/deduplication. Outbox giải quyết atomicity trong phạm vi DB và việc chuyển event tin cậy hơn, không tạo một transaction nguyên tử xuyên toàn bộ service.

## 11. Quyền sở hữu và dữ liệu có độ nhạy cao

Payment và Identity thường chứa dữ liệu cần chính sách truy cập chặt hơn Catalog. Mức isolation nên được chọn dựa trên **data classification và threat model**.

Cần xác định:

- Mã hóa khi truyền và lưu dữ liệu; ai quản lý key?
- Những role/service account nào được đọc các trường nhạy cảm?
- Ai có quyền chạy migration/restore/snapshot?
- Network isolation giữa database endpoints và application pods.
- Secret rotation, credential scope và audit.
- Chính sách retention, deletion, subject-access request và dữ liệu sao chép.
- Log, event, read model, backup có chứa dữ liệu nhạy cảm không?

Nếu Payment dùng instance riêng nhưng event của nó xuất toàn bộ card/payment payload cho mọi consumer, physical isolation không giải quyết được data minimization. Hợp đồng tích hợp phải giới hạn dữ liệu cần thiết.

### 11.1. Least privilege

Mỗi application role nên được cấp quyền tối thiểu, theo đúng schema/database và loại thao tác cần thực hiện. Database migration role có thể có quyền DDL nhưng không nên được dùng cho request runtime. Service không nên có quyền admin để “tiện bảo trì”.

### 11.2. Network segmentation bổ sung cho DB permissions

Network policy giúp giảm đường truy cập không mong muốn, nhưng **không thay quyền database**. Một service bị lỗi cấu hình hoặc có quyền đăng nhập rộng vẫn có thể gây ảnh hưởng nếu thiếu ranh giới permission. Các lớp phòng vệ nên bổ sung lẫn nhau.

## 12. Cô lập tài nguyên và noisy neighbor

Khi nhiều database cùng một DBMS instance, chúng có thể chia sẻ:

- CPU cores và scheduler.
- RAM/buffer cache.
- Storage throughput, IOPS và độ trễ đĩa.
- Connection/session limit.
- WAL/transaction log, replication bandwidth.
- Backup/maintenance windows.
- Failover/switchover procedure.
- Network throughput và network egress.

Một query analytics nặng của Catalog chạy trên shared instance có thể làm latency giao dịch Inventory tăng. Inventory còn có thể giữ nhiều connections khiến Order không mở đủ DB sessions.

### 12.1. Biện pháp khi chia sẻ instance

- Connection pool per service với max size rõ, không cấp tổng connection vượt ngưỡng DB.
- Query timeout, statement timeout, giới hạn transaction dài theo khả năng engine.
- Index, query plan monitoring và cảnh báo slow queries.
- Phân tách read replicas hoặc workload analytics nếu phù hợp.
- Resource quotas/workload groups nếu engine và hạ tầng hỗ trợ.
- Alerts cho CPU, I/O, memory, lock waits, storage utilization và connection saturation.
- Capacity planning khi tăng số pods: mỗi pod có DB pool riêng.
- Cơ chế escalation để chuyển service có tải khác biệt sang instance riêng.

Nếu shared DB instance có giới hạn 1000 connections mà chạy 30 Inventory pods với pool tối đa 40, riêng Inventory đã có khả năng mở đến 1200 connections trong điều kiện tải; phải xem xét toàn bộ hệ chứ không chỉ một pod.

### 12.2. Separate instance có phải hoàn toàn cô lập?

Không tuyệt đối. Hai instances vẫn có thể cùng cloud region, availability zone, network, storage service hoặc control plane, nên có common-mode failures. Cô lập cần được đánh giá theo fault domains thật, không chỉ theo sơ đồ có hai biểu tượng DB.

## 13. Backup, restore và khôi phục dữ liệu

Database per Service làm rõ ownership của backup/restore, nhưng nhiều database riêng có thể tăng chi phí vận hành.

### 13.1. RPO và RTO

- **RPO (Recovery Point Objective):** mức mất dữ liệu tối đa có thể chấp nhận theo thời gian.
- **RTO (Recovery Time Objective):** thời gian mục tiêu để khôi phục dịch vụ.

Order, Payment và Analytics có thể có nhu cầu khác nhau. Đưa tất cả lên một shared instance khiến backup/restore và failover có thể cùng chịu hạn chế chung.

### 13.2. Restore chỉ một service

Khi Order khôi phục về snapshot quá khứ nhưng Payment vẫn ở hiện tại, workflow có thể xuất hiện trạng thái lệch:

~~~text
Payment: đã capture giao dịch T
Order: restore về trước khi ghi T
~~~

Restore một database riêng **không tự khôi phục nhất quán xuyên service**. Cần có reconciliation, replay events, audit logs và cách xác định nguồn dữ liệu có thẩm quyền cho từng quyết định.

### 13.3. Phân biệt logical restore và physical restore

Với schema per service, việc phục hồi riêng một schema có thể phức tạp hơn restore toàn instance, phụ thuộc DBMS và công cụ backup. Với database/instance riêng, độ độc lập phục hồi có thể tốt hơn nhưng cũng phải xét WAL/transaction logs, snapshot granularity và sự phụ thuộc giữa các event.

Hãy diễn tập restore và reconciliation; không chỉ kiểm tra job backup báo thành công.

## 14. Schema migration không nên buộc triển khai đồng loạt

Một lợi ích lớn của data ownership là owner có thể đổi internal schema mà consumer không phải sửa nếu public contract vẫn giữ.

Ví dụ Inventory muốn chuyển từ một bảng stock_balance đơn giản sang mô hình stock_ledger + reservation. Nếu Order gọi ReserveStock API, các thay đổi có thể được thực hiện nội bộ. Nếu Order SELECT trực tiếp stock_balance, migration sẽ phá coupling.

### 14.1. Expand → migrate → contract

Quy trình phổ biến:

1. **Expand:** thêm schema field/table/index mới mà phiên bản cũ vẫn hoạt động.
2. **Migrate:** chuyển dữ liệu; code hỗ trợ đọc/ghi theo chiến lược tương thích.
3. **Contract:** sau khi các phiên bản cũ đã ngừng sử dụng, xóa cấu trúc cũ.

Cần phù hợp với từng engine và loại migration. Một số ALTER TABLE có thể khóa bảng hoặc tiêu hao tài nguyên; tách owner giúp quản trị rủi ro nhưng không loại bỏ vấn đề vận hành.

### 14.2. Migration identity và quyền DDL

Application runtime role không nhất thiết nên có quyền ALTER/DROP trên schema. Dùng migration account được quản lý, giới hạn quyền và kiểm soát release. Một pipeline của Order không được tùy tiện thay schema Inventory.

### 14.3. Contract bên ngoài phải ổn định

Đổi tên cột inventory.reserved_qty không nên buộc Order đổi code. Nhưng đổi ý nghĩa của ReserveStock hay các trạng thái kết quả **là thay đổi contract**, cần versioning, migration và consumer tests tương ứng. Data isolation logic không cho phép provider âm thầm thay đổi semantics API.

## 15. Từng service có thực sự cần database riêng?

Không phải mọi service đều có dữ liệu bền vững:

- API Gateway có thể phần lớn stateless.
- Một service xử lý notification có thể cần queue và bảng trạng thái gửi.
- Một service tính toán thuần có thể không cần database.
- Một projection/search service có thể sở hữu index nhưng không phải source of truth.
- Nhiều module cùng một bounded context có thể triển khai chung và dùng một database có owner chung.

Database per Service không có nghĩa **mỗi process đều phải mua một instance DB** hoặc mọi class/module có một schema. Đơn vị nên theo **quyền sở hữu dữ liệu và tính tự chủ của một business capability**.

### 15.1. Tránh nano services theo bảng

Tách OrderTableService, OrderLineTableService và OrderStatusTableService chỉ vì mỗi bảng một “database per service” thường làm một thao tác tạo đơn bị phân mảnh. Mọi invariant của order aggregate phải phối hợp qua nhiều network calls.

Nếu các bảng cùng bảo vệ một invariant, thay đổi vì cùng lý do và được cập nhật trong cùng transaction, chúng thường nên thuộc cùng một owner hoặc aggregate boundary. Không chia một domain entity thành nhiều microservices chỉ để số lượng “service và DB” tương ứng một-một.

## 16. Tradeoff với Shared Database Pattern

| Tiêu chí | Shared DB và bảng cùng dùng | Database per Service theo ownership |
| --- | --- | --- |
| Truy vấn JOIN đa miền | Dễ thực hiện trong cùng SQL | Cần API composition/projection/analytics |
| Transaction nhiều bảng | Có thể làm atomically trong cùng DB | Chỉ trong owner; liên service cần workflow |
| Thay đổi schema | Nhiều consumer bị ảnh hưởng | Owner thay internal schema độc lập hơn |
| Data ownership | Dễ mơ hồ | Rõ nếu permissions và contract tốt |
| Deploy độc lập | Có thể bị coordinated deployment | Có thể độc lập khi contract tương thích |
| Tối ưu vận hành ban đầu | Thường đơn giản | Thêm permission, migration và integration |
| Latency giao tiếp | JOIN/transaction cục bộ nhanh | Có thể thêm network hops và eventual consistency |
| Cô lập lỗi | Cùng DB thường chung failure domain | Tùy mức deployment vật lý |
| Khả năng chọn engine riêng | Hạn chế | Linh hoạt hơn nếu có lý do |
| Tổng chi phí | Thấp ở hệ nhỏ, coupling tăng theo quy mô | Chi phí đầu tư cao hơn nhưng giảm coupling khi thiết kế đúng |

Không có lựa chọn tốt tuyệt đối. Modular monolith với module boundary rõ và database chung có thể phù hợp hơn nhiều microservices ở giai đoạn sớm. Nếu chọn microservices, cần sẵn sàng trả chi phí distributed coordination để đổi lấy độc lập thay đổi, scale, ownership hoặc resilience.

## 17. Lộ trình chuyển từ database chung sang Database per Service

Giả sử hệ đang có commerce_db gồm orders, customers, inventory, payments và báo cáo; nhiều service hiện cùng query.

### Bước 1 — Vẽ data ownership map

Liệt kê từng bảng/aggregate và câu hỏi:

- Ai là owner business rule?
- Ai có quyền ghi hiện tại?
- Consumer nào đọc trực tiếp và vì sao?
- Những JOIN/transaction nào đi qua nhiều ownership dự kiến?
- Có dữ liệu nhạy cảm hoặc regulatory requirements nào?
- Thay đổi schema gần đây đã làm những service nào lỗi?

Bắt đầu với miền có ownership và invariant rõ, ví dụ Inventory reservation.

### Bước 2 — Chọn ranh giới dữ liệu theo domain

Nhóm dữ liệu theo bounded context/business capability, không tách từng bảng CRUD. Order và OrderLine có thể cùng một aggregate; StockBalance và Reservation cần cùng owner nếu bảo vệ invariant chung.

### Bước 3 — Công bố API/event trước

Thay những consumer đang SELECT trực tiếp bảng Inventory bằng query API, batch API hoặc read model phù hợp. Thay những nơi đang UPDATE trực tiếp bằng command ReserveStock/ReleaseStock có contract kết quả và idempotency.

Chưa cần ngay lập tức chuyển database sang máy chủ riêng. **Đầu tiên loại bỏ sự phụ thuộc vào internal schema.**

### Bước 4 — Phân role và schema/database logic

Tạo role runtime/migration per service, giảm quyền truy cập chéo. Khi consumer đã chuyển qua contract, thu hồi quyền đọc/ghi trực tiếp vào bảng owner.

Lưu ý chạy thử trên staging và có rollback plan; nếu còn consumer cũ dùng quyền trực tiếp, việc REVOKE đột ngột có thể gây downtime.

### Bước 5 — Chuyển dữ liệu nếu cần

Nếu muốn tách sang database riêng:

1. Tạo database/instance đích và cấu hình security/backups.
2. Backfill dữ liệu với snapshot nhất quán hoặc cơ chế migration phù hợp.
3. Đồng bộ thay đổi trong giai đoạn chuyển, có audit/watermark/CDC nếu cần.
4. Chạy kiểm tra dữ liệu và đối chiếu invariant.
5. Chuyển owner writer sang nơi mới theo một kế hoạch cutover an toàn.
6. Kiểm tra readers, rollback strategy và xử lý events/operations in-flight.
7. Chỉ gỡ đường cũ sau khi xác minh không còn consumer phụ thuộc.

Không nên mặc định “dual write” trực tiếp hai database là an toàn. Nếu một ghi thành công và ghi còn lại lỗi, trạng thái phân kỳ phải được xử lý. Dùng outbox/CDC/controlled cutover hoặc giao thức phù hợp thay vì cập nhật hai nơi mà không có quy tắc.

### Bước 6 — Chuyển truy vấn tổng hợp

Những dashboard trước đây JOIN nhiều bảng có thể dùng reporting projection hoặc data warehouse. Phải nêu freshness và cơ chế rebuild, không làm các service lại tự đọc database riêng của nhau.

### Bước 7 — Đo và cô lập vật lý khi có bằng chứng

Giữ các database trên shared instance nếu capacity và rủi ro chấp nhận được. Tách Inventory/Payment sang instance riêng khi SLO, security, throughput, RPO/RTO hoặc noisy neighbor chứng minh cần thiết.

## 18. Bài toán ví dụ: Checkout với Order, Inventory và Payment

### 18.1. Cấu trúc dữ liệu có owner

~~~text
Order Service
  order_data
    orders
    order_lines
    order_outbox

Inventory Service
  inventory_data
    stock_balance
    reservations
    inventory_outbox

Payment Service
  payment_data
    payment_attempts
    refunds
    payment_outbox
~~~

Các schema có thể đặt trong một PostgreSQL application_db trên một shared instance. Account mỗi service chỉ được ghi schema riêng. Về sau Payment có thể chuyển sang database/instance riêng mà contract business không thay đổi.

### 18.2. Luồng xử lý

~~~text
Client -> Order: PlaceOrder(key=K)
              |
              v
          Order PENDING
              |
              v
          Inventory.reserve(orderId,sku,qty,key)
              |
       +------+------+
       |             |
    RESERVED      OUT_OF_STOCK
       |             |
       v             v
  Payment.authorize  Order FAILED
       |
  +----+---------+
  |              |
SUCCESS       FAILED / UNKNOWN
  |              |
  v              v
CONFIRMED    COMPENSATE / RECONCILE
~~~

Order không cần biết các bảng bên trong Inventory hay Payment; nó phải biết **contract trạng thái nghiệp vụ và hành vi khi lỗi**.

### 18.3. Những bất biến cần giữ

- Inventory không reserve vượt lượng có thể bán theo policy.
- Payment không charge trùng cùng ý định giao dịch.
- Order không báo CONFIRMED khi không có bằng chứng các điều kiện được đáp ứng.
- Khi Order chuyển trạng thái, event tương ứng không bị bỏ sót ngoài khả năng phục hồi.
- Nếu cần hủy reservation hoặc hoàn tiền, compensation có idempotency và theo dõi được.

Các bất biến được bảo vệ tại owner và phối hợp bằng workflow, không bằng việc Order sửa trực tiếp các bảng của hai service khác.

### 18.4. Khi Payment timeout

Payment có thể đã authorize thành công nhưng response bị mất. Order phải đánh dấu trạng thái chưa chắc chắn, tra cứu theo paymentId/idempotency key hoặc chờ event xác thực, không tự xác định “FAILED” rồi charge lần nữa bằng khóa mới.

Đây là hệ quả thực tế của ranh giới dữ liệu và lỗi mạng: một database per service không thể biến timeout thành một kết quả giao dịch chắc chắn.

## 19. Khi nào một service được dùng bản sao dữ liệu service khác?

Một consumer có thể cần truy vấn nhanh hoặc hoạt động khi producer tạm mất kết nối. Nó có thể giữ một read model riêng nếu:

- Nguồn dữ liệu có thẩm quyền được xác định.
- Dữ liệu được sao chép qua API/event/CDC có contract rõ.
- Mức freshness/staleness được công bố.
- Có event ordering/version/idempotency và cách rebuild.
- Có quy tắc xóa/ẩn dữ liệu nhạy cảm và đồng bộ retention.
- Consumer không nhầm read model với quyền ghi vào nguồn.
- Các quyết định cần consistency mạnh vẫn đến đúng owner hoặc có cơ chế phân quyền phù hợp.

Ví dụ Recommendation lưu ProductDisplayProjection để gợi ý sản phẩm. Nó không được tự sửa bảng ProductCatalog và không trở thành nơi định giá chính thức.

### 19.1. Bản sao phục vụ đọc khác distributed multi-master

Cho phép mọi service cập nhật cùng một đối tượng dữ liệu rồi hợp nhất sau khi mạng phục hồi là một lựa chọn concurrency/consistency rất khác. Nếu thực sự cần multi-master, phải có conflict resolution, invariant và mô hình dữ liệu phù hợp, không được coi đó là hệ quả mặc định của Database per Service.

## 20. Kiểm thử ranh giới dữ liệu

Kiểm thử có ý nghĩa không chỉ xác minh request API trả 200; cần kiểm tra ownership và failure behavior.

### 20.1. Kiểm tra quyền database

- Account order_app không SELECT/UPDATE được bảng private của inventory_data theo policy đã đặt.
- Account inventory_app không sửa được orders/payment_attempts.
- Runtime account không có quyền DDL ngoài phạm vi cần thiết.
- Migration pipeline mỗi service chỉ thay schema/database do mình sở hữu.
- Không tồn tại credentials toàn quyền bị copy vào mọi deployment.

### 20.2. Kiểm tra phát hành độc lập

- Thay tên cột nội bộ Inventory mà Order không build/deploy lại nếu public contract không đổi.
- Chạy consumer/provider contract tests trong giai đoạn API versions trộn.
- Migration expand/migrate/contract không làm hỏng pod phiên bản cũ.
- Bản rollback của Inventory không yêu cầu Order rollback vì dùng trực tiếp schema.

### 20.3. Kiểm tra transaction và lỗi mạng

- Inventory commit reservation nhưng response bị mất.
- Payment thành công nhưng event bị gửi lặp.
- Broker tạm ngừng sau Order DB commit.
- Order nhận event sai thứ tự và duplicate.
- Saga compensation thất bại, được retry idempotent và có alert.
- Một service mất database nhưng các service khác hoạt động ở phạm vi không phụ thuộc.

### 20.4. Kiểm tra resource isolation

- Một query nặng trong schema Catalog ảnh hưởng thế nào tới Order khi cùng instance?
- Database connection limits có bị vượt khi autoscaling pod?
- Shared instance failover có tác động cùng lúc tới bao nhiêu service?
- Khi chuyển Inventory sang instance khác, SLO/backup/restore có cải thiện như kỳ vọng?
- Backup và restore một DB có làm mất tính khớp với event stream bên ngoài không?

## 21. Giám sát và trách nhiệm vận hành

Một service nên có owner của cả dữ liệu lẫn sự cố liên quan. Các metrics gợi ý:

| Nhóm | Tín hiệu | Câu hỏi |
| --- | --- | --- |
| Database access | Audit log, denied cross-schema access | Có consumer truy cập sai boundary? |
| Query | p95/p99 duration, slow queries, lock wait | Rule/query nội bộ có gây nghẽn? |
| Connections | Active, idle, waiting, max, per-pod | Autoscaling có làm cạn DB sessions? |
| Capacity | CPU, RAM, IOPS, disk throughput | Shared instance có noisy neighbor? |
| Reliability | DB failover, error rate, lag | Một sự cố ảnh hưởng bao nhiêu owner? |
| Migration | Failed migrations, long locks | Release có độc lập thật không? |
| Events | Outbox backlog, consumer lag, duplicate rate | Cross-service projections có hội tụ? |
| Workflow | PENDING quá hạn, reconciliation drift | Partial failure có được xử lý? |
| Backup | Last successful backup, restore drill, RPO/RTO | Khôi phục được trạng thái đáng tin không? |
| Security | Secret age, permission changes, abnormal reads | Least privilege có được giữ? |

Cần tách metric theo service, database, schema và instance nếu có thể. Khi ba service ở cùng instance, một alert CPU toàn instance cần giúp chỉ ra workload nào gây tải và owner nào phối hợp khắc phục.

## 22. Quyết định mức cô lập dựa trên tiêu chí

Hãy lập bảng cho mỗi service:

| Câu hỏi | Nếu trả lời “có” | Ảnh hưởng quyết định |
| --- | --- | --- |
| Có dữ liệu nhạy cảm cần isolation riêng? | Payment/Identity có thể cần boundary chặt | Cân nhắc instance/network/key riêng |
| Có SLO/latency đặc biệt? | Inventory quyết định checkout | Cân nhắc capacity và failure isolation |
| Tải có khác biệt lớn với service khác? | Search/analytics rất nặng | Tách workload/engine hoặc instance |
| Cần transaction mạnh với bảng bên trong? | Reservation + stock | Giữ trong cùng owner, không tách theo bảng |
| Thường xuyên đổi schema riêng? | Inventory phát triển nhanh | Ít nhất cần ownership logic và contract |
| Có hàng chục consumer đang JOIN bảng? | Data coupling cao | Ưu tiên API/read model migration |
| Có đội platform vận hành nhiều DB? | Có automation tốt | Có thể tách instance/cluster dễ hơn |
| Chi phí bị giới hạn? | Hệ nhỏ, chưa có tải | Bắt đầu từ schema/database logic cùng instance |
| RPO/RTO khác biệt? | Payment cần khôi phục đặc biệt | Xem xét backup/replication độc lập |

Đừng chỉ chấm “schema” hay “instance” là tốt nhất. Quyết định cần cân bằng **bất biến nghiệp vụ, mức rủi ro, năng lực vận hành, chi phí và lộ trình tăng trưởng**.

## 23. Những hiểu lầm thường gặp

### Hiểu lầm 1 — “Database per Service bắt buộc mỗi service có một máy chủ vật lý”

Sai. Ranh giới cơ bản là logical data ownership và quyền truy cập. Nhiều schema/database có thể cùng tồn tại trên một DBMS instance. Máy chủ/cluster riêng là mức isolation hạ tầng nâng cao, không phải điều kiện định nghĩa pattern.

### Hiểu lầm 2 — “Schema riêng là đủ, dù service nào cũng có superuser”

Sai. Nếu mọi service đều có quyền đọc/ghi tất cả schema, tính cô lập dựa trên quy ước và có thể bị phá rất dễ. Cần least privilege và migration ownership rõ.

### Hiểu lầm 3 — “Database riêng bảo đảm deploy độc lập”

Không tự động. Nếu service A vẫn truy vấn bảng nội bộ của service B qua tài khoản có quyền, hoặc A/B chia sẻ entity JPA, change coupling vẫn lớn. Cần API/event contracts và migration compatibility.

### Hiểu lầm 4 — “Không được sao chép bất kỳ dữ liệu nào giữa các service”

Sai. Read models, snapshots, caches và reporting projections có thể cần thiết. Vấn đề là **ai có thẩm quyền ghi**, mức độ cũ và cơ chế đồng bộ.

### Hiểu lầm 5 — “Microservices bắt buộc một service = một database engine khác”

Sai. Nhiều service có thể cùng dùng PostgreSQL. Polyglot persistence chỉ có ích khi yêu cầu kỹ thuật và vận hành thực sự biện minh.

### Hiểu lầm 6 — “Cứ có service riêng là mỗi bảng nên tách riêng”

Sai. Những bảng cùng invariant và transaction boundary thường cần ở cùng owner. Tách theo CRUD entity có thể tạo nano services, giao tiếp chéo và distributed transaction không cần thiết.

### Hiểu lầm 7 — “Bỏ JOIN giữa bảng là đủ để có low coupling”

Không đủ. Thay JOIN bằng 100 HTTP calls nối tiếp có thể tạo temporal coupling rất cao. Cần batch API, read model, snapshot và hợp đồng rõ.

### Hiểu lầm 8 — “Outbox khiến cả workflow transaction nguyên tử”

Sai. Outbox hỗ trợ atomically ghi business state và pending event trong một database; các bước ở service khác vẫn diễn ra sau và có thể thất bại, gửi lặp hoặc trễ.

### Hiểu lầm 9 — “Tách instance giải quyết mọi lỗi lan truyền”

Sai. Các service vẫn phụ thuộc mạng, broker, auth, gateway và downstream. Nhiều instances còn có thể chung vùng cloud/control plane. Phải đo fault domain và dependency graph thực tế.

### Hiểu lầm 10 — “Một service có thể tùy tiện dùng dữ liệu consumer đã cache để commit quyết định quan trọng”

Không nên. Cache có thể cũ. Quyết định về tồn kho, số dư, quyền truy cập hoặc giá chính thức cần consistency/invariant theo owner và business policy đã định.

### Hiểu lầm 11 — “Database per Service có nghĩa tránh mọi coordination giữa team”

Sai. Team vẫn cần phối hợp về public contract, event semantics, versioning, SLO, migrations liên quan và workflows. Mục tiêu là giảm **phối hợp không cần thiết** khi thay đổi internal schema hoặc rules.

### Hiểu lầm 12 — “Chỉ cần tạo database riêng là đã có backup/restore độc lập”

Chưa chắc. Shared instance có thể có snapshot/failover chung; phục hồi Order về quá khứ khi Payment hiện tại đòi reconciliation. Phải diễn tập restore theo kiến trúc.

## 24. Bài tập thực hành: thiết kế ranh giới dữ liệu cho hệ thống đặt vé

Một hệ thống bán vé gồm:

- Show Catalog lưu show, venue, sơ đồ ghế.
- Seat Reservation giữ chỗ trong 5 phút và chống bán trùng.
- Payment xử lý thanh toán với gateway.
- Ticket Issuance phát hành mã vé sau khi thanh toán.
- Notification gửi email.
- Analytics tổng hợp doanh thu và số ghế đã bán.

### Bài 1 — Chọn owner

Hãy phân nhóm dữ liệu theo owner, chỉ rõ ai được ghi trạng thái seat reservation, trạng thái payment, QR ticket và lịch sử gửi email. Đánh dấu những bảng cần cập nhật atomically trong một bounded context.

### Bài 2 — Chọn mức cô lập

Nếu team chỉ có 5 kỹ sư và database có tải thấp, hãy so sánh một PostgreSQL instance với schema riêng theo service và sáu database instances riêng. Nêu lý do về chi phí, quyền truy cập, backup và scalability.

### Bài 3 — Xử lý truy vấn đa miền

Trang quản trị cần thống kê doanh thu theo show và số ghế đã bán. Có nên cho Analytics JOIN trực tiếp bảng Payment và Seat Reservation? Đề xuất read model/event pipeline, freshness policy và cơ chế rebuild.

### Bài 4 — Sự cố mạng

Payment đã xử lý nhưng Ticket Issuance chưa nhận event. Hãy mô tả trạng thái PENDING/UNKNOWN, idempotency, outbox, retries và reconciliation để không phát hành hai vé hoặc mất giao dịch.

### Bài 5 — Test quyền truy cập

Tạo user roles riêng trong staging; kiểm chứng runtime role của Notification không thể UPDATE bảng Payment, và runtime role Payment không có quyền SELECT toàn bộ dữ liệu định danh trong Catalog/Identity nếu không cần thiết.

### Bài 6 — Kịch bản scale

Một show nổi tiếng làm Seat Reservation tăng tải lên gấp 20 lần, các schema còn lại vẫn bình thường. Hãy nêu số liệu nào cần thu trước khi quyết định chuyển Seat Reservation sang instance/cluster riêng.

## 25. Mẫu ADR rút gọn

~~~markdown
# ADR: Ranh giới dữ liệu Order / Inventory / Payment

Bối cảnh:
- Hệ đang dùng một PostgreSQL instance.
- Nhiều service đang đọc hoặc sửa chung bảng.
- Cần ownership và triển khai độc lập hơn, nhưng tải chưa lớn.

Quyết định:
- Mỗi bounded context sở hữu schema riêng trong application_db.
- Runtime role có quyền tối thiểu trong schema của mình.
- Không direct SELECT/UPDATE bảng private của service khác.
- API/event contract thay cho truy cập chéo.
- Giữ chung DB instance ở giai đoạn đầu.

Chi phí/chấp nhận:
- Shared CPU/I/O/connection limits, backup/failover còn chung.
- Cross-service queries cần API composition/read model.
- Workflow nhiều service cần state machine/outbox/idempotency.

Điều kiện xem xét tách instance:
- Noisy neighbor, SLO hoặc security isolation có bằng chứng.
- RPO/RTO và maintenance needs khác biệt đáng kể.
- Engine/workload khác nhau hoặc khả năng scale độc lập thực sự cần.

Kiểm chứng:
- Permission test, contract test, integration fault test.
- Metrics latency, connections, query load, event lag.
- Restore drill và reconciliation sau sự cố.
~~~

ADR giúp phân biệt **điều đang cam kết (ownership logic)** với **điều chưa cam kết (máy chủ/cluster riêng)**, tránh việc mọi người hiểu cùng một biểu đồ database theo những nghĩa khác nhau.

## 26. Checklist trước khi áp dụng

1. Service nào sở hữu từng dữ liệu có thẩm quyền?
2. Bảng nào cần chung transactional boundary để bảo vệ invariant?
3. Các service khác có đọc hoặc ghi trực tiếp bảng nội bộ không?
4. Permissions và roles có thực sự chặn quyền trái ranh giới không?
5. Có contract API/event được công bố cho nhu cầu tích hợp không?
6. Khi API timeout sau commit, có idempotency và cách query trạng thái không?
7. Có Saga/state machine cho workflow liên miền không?
8. Có outbox hoặc cơ chế tin cậy tương ứng cho event sau DB commit không?
9. Read model/cache có freshness, replay và reconciliation không?
10. Schema migrations có expand/migrate/contract và independent release không?
11. Shared instance có đủ CPU/I/O/connection headroom khi scale pod không?
12. Có risk assessment cho noisy neighbor và shared failure domain không?
13. Backup/restore per service có được diễn tập cùng event replay không?
14. Security/data classification có cần instance/network/key riêng không?
15. Chi phí database/cluster riêng có được biện minh bằng nhu cầu thật không?
16. Có quyền owner và runbook cho metrics, alerts, backups và incident không?

## 27. Câu hỏi tự kiểm tra

1. “Database per Service” nói về ranh giới sở hữu dữ liệu hay bắt buộc về phần cứng? Giải thích.
2. Một instance PostgreSQL chứa ba schema, mỗi schema có runtime role riêng và không thể truy cập chéo. Điều gì đã được cô lập, và điều gì vẫn chia sẻ?
3. Một instance chứa ba database. Vì sao điều đó chưa có nghĩa là ba failure domains độc lập?
4. Nếu Order chỉ có SELECT vào bảng Inventory nhưng không có UPDATE, vẫn còn coupling nào?
5. Vì sao mỗi bảng một microservice có thể làm tăng distributed transaction complexity?
6. Nếu Inventory có database riêng nhưng Order vẫn dùng SQL trực tiếp để sửa reservations, có đạt mục tiêu data ownership chưa?
7. Khi cần dashboard nối dữ liệu Order và Payment, những phương án nào thay direct JOIN?
8. API composition và reporting projection đánh đổi latency/freshness khác nhau thế nào?
9. Saga có giống transaction ACID giữa Order, Inventory và Payment không?
10. Outbox giải quyết vấn đề gì, và vì sao consumer vẫn cần idempotency?
11. Khi tách schema nhưng dùng chung CPU/I/O, điều gì gây noisy neighbor?
12. Vì sao account runtime không nên có quyền DDL hoặc superuser?
13. Tại sao restore riêng Order có thể đòi đối soát với Payment hiện tại?
14. Khi nào chuyển Inventory từ shared instance sang instance riêng là hợp lý?
15. Tại sao polyglot persistence là quyền lựa chọn chứ không phải nghĩa vụ của mọi microservice?
16. Nếu Product name xuất hiện trong Catalog và Order snapshot, có nghĩa data ownership bị vi phạm không?
17. Vì sao đổi một cột private trong Inventory không nên buộc Order deploy, và cần contract gì để đạt được?
18. Điều gì khiến logical isolation trở thành một bảo đảm kỹ thuật thay vì một thỏa thuận bằng lời?

## 28. Tóm tắt và nguyên tắc áp dụng

- **Database per Service trước hết là data ownership và isolation logic**: một service sở hữu mô hình, quy tắc và quyền cập nhật dữ liệu có thẩm quyền.
- **Không bắt buộc một server vật lý, VM, container hoặc managed instance riêng cho mỗi service**. Schema per service hay database per service trên shared DBMS instance đều có thể là bước triển khai hợp lệ nếu permissions và contract tạo ranh giới thật.
- **Các mức cô lập không tương đương**: tách schema/database logic không tự tách CPU, I/O, backup, upgrade, failover và common-mode failures.
- **Không cho consumer truy cập bảng private như public API ngầm định**; dùng command/query API, public events, snapshots hoặc read models với semantics rõ.
- **Transaction mạnh cần owner rõ**. Giao dịch qua nhiều service đòi thiết kế partial failure, state machine/Saga, idempotency, outbox và reconciliation.
- **Sao chép dữ liệu phục vụ đọc không đồng nghĩa nhiều owner**. Phải chỉ ra nguồn có thẩm quyền và mức freshness.
- **Độc lập triển khai xuất phát từ contract và migrations tương thích**, không chỉ từ số lượng database instances.
- **Tách vật lý khi có bằng chứng** về tải, security, RPO/RTO, isolation, backup hoặc SLO; không tách bằng cảm tính.
- **Kiểm chứng bằng permission tests, contract tests, fault tests, metrics và restore drills**, không chỉ bằng sơ đồ hạ tầng.

**Câu hỏi quyết định cuối cùng:** *Nếu ngày mai Inventory đổi toàn bộ schema nội bộ nhưng vẫn giữ hành vi ReserveStock được công bố, Order có tiếp tục chạy mà không sửa code và không có quyền truy cập trực tiếp vào bảng Inventory không?* Nếu có, ranh giới sở hữu dữ liệu đang phát huy tác dụng — bất kể hai service hiện chạy trên cùng hay khác máy chủ database.
