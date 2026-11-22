
# Lựa chọn thứ tự triển khai khi có phụ thuộc giữa các cơ sở dữ liệu

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Khi một hệ thống dùng nhiều database, một thay đổi có thể cần database khác chuẩn bị trước: service đơn hàng chỉ có thể ghi customer reference sau khi database khách hàng cung cấp mã định danh ổn định; kho phân tích chỉ có thể đọc cột mới sau khi database nguồn đã phát hành; hoặc một luồng đồng bộ chỉ chạy đúng khi cả schema nguồn và schema đích đã sẵn sàng.

Bài thuộc chương **Nhiều cơ sở dữ liệu** này hướng dẫn lựa chọn **thứ tự triển khai khi có phụ thuộc giữa các cơ sở dữ liệu**. Trọng tâm là lập đồ thị phụ thuộc, xác định database cung cấp và database tiêu thụ dữ liệu, sắp xếp thứ tự bằng topological sort, triển khai theo các đợt, xử lý phụ thuộc vòng, điều phối các Liquibase job độc lập và phục hồi khi chỉ một phần database đã cập nhật.

Mục tiêu là tổ chức migration có thể dự đoán và tiếp tục an toàn: database tiên quyết được chuẩn bị trước, consumer chỉ chuyển sang sử dụng cấu trúc mới khi provider đã sẵn sàng, còn những database độc lập vẫn có thể triển khai song song để rút ngắn thời gian release.

Phạm vi được xác định bởi **SERVICE_NAME=DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Theo **SERVICE_NAME_DESCRIBE**, module tập trung quản lý thay đổi schema và dữ liệu qua changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

## 1. Vì sao thứ tự triển khai quan trọng?

Một ứng dụng có thể dùng nhiều database vì phân vùng theo domain, tách workload giao dịch và báo cáo, cô lập tenant, hoặc phục vụ các hệ thống cũ và mới cùng tồn tại.

Ví dụ:

- `customer_db` lưu hồ sơ khách hàng và phát hành `customer_id`.
- `order_db` lưu đơn hàng và cần lưu customer reference.
- `billing_db` nhận dữ liệu đơn hàng để tính hóa đơn.
- `analytics_db` tổng hợp dữ liệu từ customer, order và billing.

Nếu migration của `order_db` tạo cột mới trỏ đến dữ liệu khách hàng, nhưng `customer_db` chưa có mã định danh hoặc dữ liệu chuẩn, ứng dụng có thể ghi tham chiếu không hợp lệ. Nếu analytics triển khai query mới trước khi producer tạo cột nguồn, job ETL có thể lỗi.

**Thứ tự migration là thứ tự thỏa mãn các điều kiện phụ thuộc**, không đơn giản là sắp xếp tên database theo alphabet hay chạy tất cả changelog cùng lúc.

## 2. Phân biệt database, service và migration job

Ba khái niệm cần được tách riêng:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Database | Nơi lưu schema, dữ liệu và lịch sử Liquibase riêng | `customer_db` |
| Service | Ứng dụng sở hữu hoặc tiêu thụ dữ liệu | Customer Service, Order Service |
| Migration job | Tiến trình chạy Liquibase trên một database đích | `liquibase-update-customer` |

Một service có thể dùng nhiều database; một database có thể được nhiều service đọc; một migration job có thể triển khai một changelog lên một database. Quan hệ sở hữu phải được thống nhất trước khi sắp thứ tự.

Không nên để nhiều service cùng sửa một bảng trong cùng database mà không có owner rõ ràng. Với database dùng chung, cần xác định nhóm chịu trách nhiệm changelog, quyền DDL, quy trình review và cách phối hợp release.

## 3. Phân loại phụ thuộc giữa các database

Không phải mọi liên kết dữ liệu đều tạo ra cùng một yêu cầu thứ tự. Hãy phân loại:

| Loại phụ thuộc | Ví dụ | Điều kiện trước khi triển khai consumer |
|---|---|---|
| Schema/API dữ liệu | Consumer cần cột mới ở database provider | Cột/contract mới tồn tại và tương thích |
| Reference data | Order cần mã customer tier đã có | Mã tham chiếu được tạo và xác minh |
| Data pipeline | Analytics cần trường mới từ CDC/ETL | Producer phát dữ liệu; pipeline hiểu schema mới |
| Quy trình nghiệp vụ | Billing cần order đã được chuẩn hóa | Migration và backfill nghiệp vụ hoàn tất |
| Khóa/định danh | Database đích lưu khóa từ database nguồn | Quy tắc định danh ổn định và mapping đầy đủ |
| Tương thích ứng dụng | Service mới cần schema mới | Schema đã expand và các phiên bản đang chạy đều tương thích |

Một phụ thuộc chỉ là **thứ tự bắt buộc** khi consumer không thể hoạt động đúng nếu prerequisite chưa đạt. Nếu hai migration độc lập và không có contract chung, chúng có thể triển khai song song.

## 4. Xác định producer và consumer

Với mỗi luồng dữ liệu, xác định:

- **Producer:** database/service tạo ra dữ liệu hoặc contract.
- **Consumer:** database/service đọc, sao chép hoặc tham chiếu dữ liệu đó.
- **Contract:** tên trường, kiểu dữ liệu, semantics, khóa, quy tắc nullability và thời điểm dữ liệu sẵn sàng.
- **Readiness condition:** điều kiện đo được để cho phép consumer tiếp tục.

Ví dụ: Customer Service là producer của mã khách hàng. Order Service là consumer. Contract không chỉ nói `customer_id` là BIGINT; nó cần xác định mã có duy nhất, bất biến, có thể xuất hiện ở các vùng khác nhau hay không, và dữ liệu nào được phép tham chiếu.

Nếu consumer lưu bản sao dữ liệu khách hàng, cần xác định bản sao đó cập nhật đồng bộ hay bất đồng bộ. Một row đã được insert trong provider chưa có nghĩa bản sao ở consumer đã nhận được qua CDC/event pipeline.

## 5. Mô hình phụ thuộc bằng đồ thị có hướng

Dùng đồ thị có hướng (Directed Acyclic Graph — DAG) để biểu diễn prerequisite:

- Mỗi node là một migration unit hoặc một giai đoạn triển khai database.
- Cạnh A → B có nghĩa A phải hoàn thành điều kiện đã định nghĩa trước khi B bắt đầu.
- Node không có đường phụ thuộc với nhau có thể nằm cùng một wave và triển khai song song.
- Đồ thị cần không có chu trình trước khi dùng topological ordering.

Ví dụ:

~~~text
customer_db: expand customer contract
             |
             +-------------------+
             |                   |
             v                   v
order_db: add customer_ref   analytics_db: accept customer field
             |                   |
             v                   |
billing_db: add customer link    |
             |                   |
             +---------+---------+
                       |
                       v
             analytics_db: consume order/billing fields
~~~

Sơ đồ cho thấy analytics có thể có hai giai đoạn: chuẩn bị khả năng nhận trường khách hàng sớm, sau đó mới tiêu thụ dữ liệu order/billing khi các producer tương ứng sẵn sàng.

Một cạnh không nên chỉ có tên mơ hồ như “phải chạy trước”. Hãy ghi rõ **điều kiện hoàn tất**: changeset cụ thể đã được ghi trong DATABASECHANGELOG, cột tồn tại đúng kiểu, backfill đạt invariant, hoặc CDC đã phát schema version cần thiết.

## 6. Topological sort: chuyển DAG thành thứ tự triển khai

**Topological sort** là cách sắp các node sao cho mọi prerequisite đều đứng trước node phụ thuộc.

Quy trình:

1. Tạo danh sách node migration.
2. Ghi cạnh phụ thuộc có hướng.
3. Đếm số prerequisite của từng node (in-degree).
4. Chọn các node có in-degree bằng 0.
5. Đưa chúng vào wave đầu; sau khi hoàn thành, bỏ các cạnh đi ra.
6. Những node mới có in-degree bằng 0 được đưa vào wave tiếp theo.
7. Tiếp tục đến khi hết node.
8. Nếu vẫn còn node nhưng không node nào có in-degree bằng 0, đồ thị có chu trình hoặc thiếu điều kiện được mô hình hóa.

Ví dụ:

| Node | Phụ thuộc | Wave |
|---|---|---|
| A: customer schema expand | Không | 1 |
| B: customer reference seed | A | 2 |
| C: order schema expand | A | 2 |
| D: billing schema expand | C | 3 |
| E: analytics consumer | B, D | 4 |

B và C độc lập sau A nên có thể chạy song song. E phải chờ cả B và D. Topological sort cho phép rút ngắn thời gian bằng cách song song hóa những việc không phụ thuộc nhau.

## 7. Thứ tự database khác thứ tự changeset trong một changelog

Liquibase xử lý changeset theo master changelog và cấu hình của lần chạy. Nhưng khi có nhiều database, mỗi database thường có:

- Kết nối và credentials riêng.
- Bảng DATABASECHANGELOG riêng.
- Bảng DATABASECHANGELOGLOCK riêng.
- Trạng thái pending và lịch sử thực thi riêng.
- Phiên bản schema và dữ liệu có thể khác nhau.

Một master changelog không tự biến nhiều database thành một transaction phân tán. Chạy update trên `customer_db` xong rồi chạy update trên `order_db` là **hai thao tác độc lập**, có thể một bên thành công và bên còn lại thất bại.

Vì vậy, cần một lớp orchestration bên ngoài Liquibase để điều phối thứ tự các job, kiểm tra readiness và lưu trạng thái từng database. Không dựa vào thứ tự include của một file để suy luận rằng nhiều database đã được cập nhật theo cùng một giao dịch.

## 8. Lập dependency manifest trước khi viết pipeline

Nên có một manifest ở cấp quy trình release (ví dụ trong hệ thống CI/CD hoặc tài liệu triển khai) với các thông tin:

| Trường | Ý nghĩa |
|---|---|
| database_id | Tên định danh ổn định của database đích |
| owner | Nhóm chịu trách nhiệm |
| changelog | Master changelog cần chạy |
| revision | Commit/artifact chứa changelog |
| prerequisites | Các database hoặc điều kiện phải hoàn thành trước |
| readiness_check | Truy vấn/API/metric kiểm tra prerequisite |
| migration_job | Tên job thực thi Liquibase |
| rollback_plan | Kế hoạch xử lý khi job hoặc wave thất bại |
| compatibility_window | Những phiên bản ứng dụng/schema có thể cùng tồn tại |

Ví dụ rút gọn:

~~~yaml
deployment:
  release: orders-2026-11
  databases:
    customer_db:
      changelog: db/changelog/customer-master.yaml
      prerequisites: []
      readiness: customer-schema-v2-ready
    order_db:
      changelog: db/changelog/order-master.yaml
      prerequisites:
        - customer_db
      readiness: order-customer-ref-ready
    billing_db:
      changelog: db/changelog/billing-master.yaml
      prerequisites:
        - order_db
      readiness: billing-order-contract-ready
~~~

Đây là **manifest minh họa cho orchestration**, không phải cấu hình YAML built-in mà Liquibase tự đọc. Công cụ CI/CD hoặc deployment controller phải diễn giải các prerequisite, chạy job tương ứng và xác minh readiness.

Không lưu mật khẩu trong manifest; chỉ tham chiếu secret/connection profile được cấp ở runtime.

## 9. Xây dựng changelog riêng cho từng database

Khi mỗi database có schema và vòng đời riêng, cách dễ kiểm soát là dùng master changelog riêng:

~~~text
db/changelog/
  customer/
    db.changelog-customer.yaml
    changes/
  order/
    db.changelog-order.yaml
    changes/
  billing/
    db.changelog-billing.yaml
    changes/
  analytics/
    db.changelog-analytics.yaml
    changes/
~~~

Customer master:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-expand-customer.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-seed-customer-tier.yaml
      relativeToChangelogFile: true
~~~

Order master:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-add-customer-ref.yaml
      relativeToChangelogFile: true
~~~

Tách master giúp xác định rõ database nào sở hữu changeset. Không bắt buộc mọi dự án phải có một thư mục cho mỗi database; có thể dùng changelog chung khi cấu trúc thực sự giống nhau. Nhưng mỗi lần chạy phải xác định chính xác database đích, DBMS, schema và bộ lọc.

Không include cùng một changeset vào nhiều database rồi cho rằng lịch sử và checksum của chúng sẽ tự đồng bộ. Mỗi database có lịch sử độc lập; cùng một revision được chạy ở các thời điểm khác nhau vẫn có thể có trạng thái khác nhau.

## 10. Một changelog dùng cho nhiều DBMS hoặc nhiều database?

Có hai trục cần phân biệt:

1. **Nhiều database instance cùng loại DBMS:** có thể dùng cùng changelog nếu schema và migration giống nhau.
2. **Nhiều DBMS khác nhau:** có thể dùng change type chung, hoặc tách changeset theo dbms/SQL dialect khi cần.

Ví dụ một thay đổi chung:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-add-customer-status
      author: customer-team
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: status
                  type: varchar(20)
~~~

Nếu một DBMS cần SQL riêng, có thể dùng changeset được lọc bằng thuộc tính `dbms` hoặc changelog riêng. Cần bảo đảm mọi database mục tiêu đều có đường migration phù hợp.

Không dùng `context` hay `label` như cách thay thế tự động cho DBMS compatibility. Bộ lọc được chọn theo cấu hình của lần chạy và semantics của phiên bản Liquibase; nếu không truyền filter như dự kiến, changeset có thể vẫn được xét.

## 11. Phụ thuộc schema: mở rộng provider trước consumer

Giả sử `customer_db` sẽ cung cấp thêm cột `external_ref`, còn `order_db` cần lưu mã tham chiếu tương ứng.

Thứ tự an toàn thường là:

1. **Provider expand:** thêm cột optional hoặc bảng mapping mới trong customer_db.
2. Triển khai provider code có thể ghi/đọc cả cấu trúc cũ và mới.
3. **Consumer expand:** thêm cột customer_ref nullable trong order_db.
4. Triển khai consumer code hỗ trợ cả dữ liệu cũ và mới.
5. Backfill/mirror dữ liệu nếu cần.
6. Xác minh contract và dữ liệu.
7. Chỉ sau đó mới thêm constraint hoặc loại bỏ đường cũ.

Không tạo NOT NULL hoặc constraint bắt buộc ở provider trước khi mọi producer/consumer đã tương thích. Một release nhiều service có thể có thời gian chạy song song các phiên bản ứng dụng khác nhau.

## 12. Phụ thuộc dữ liệu: schema có trước chưa có nghĩa dữ liệu đã sẵn sàng

Giả sử `customer_db` đã có bảng customer_tier, nhưng mã `PREMIUM` chưa được seed. Order Service cần mã đó để phân loại đơn hàng.

Prerequisite của `order_db` không chỉ là “customer_tier tồn tại”; nó là:

- Mã PREMIUM tồn tại.
- Mã có trạng thái active phù hợp.
- Quy tắc business key ổn định.
- Dữ liệu được đồng bộ tới nơi consumer truy cập.
- Không có bản ghi trùng hoặc mapping không nhất quán.

Một readiness query tham khảo trên database provider:

~~~sql
SELECT COUNT(*)
FROM customer_tier
WHERE code = 'PREMIUM'
  AND active = TRUE;
~~~

Consumer chỉ được phép tiếp tục khi kết quả bằng giá trị mong đợi. Nếu dữ liệu được chuyển qua CDC/event bus, cần kiểm tra cả checkpoint/offset hoặc trạng thái pipeline; việc query provider trực tiếp không chứng minh consumer đã nhận được dữ liệu.

## 13. Phụ thuộc giữa database không nhất thiết là foreign key

Khi hai bảng nằm trong cùng một database, foreign key có thể bảo vệ tham chiếu ở mức DBMS. Khi dữ liệu nằm ở hai database/instance khác nhau, ràng buộc foreign key trực tiếp có thể không được hỗ trợ hoặc không phù hợp kiến trúc.

Ví dụ `order_db.order.customer_id` tham chiếu đến `customer_db.customer.id`. Nếu hai database tách biệt, ứng dụng hoặc luồng đồng bộ phải duy trì tính hợp lệ. Cần định nghĩa:

- Business key/ID có duy nhất trên toàn hệ thống không?
- Điều gì xảy ra khi customer bị xóa hoặc hợp nhất?
- Có soft delete hoặc tombstone không?
- Consumer xử lý event đến trễ hoặc lặp lại thế nào?
- Có quy trình reconcile định kỳ các tham chiếu mồ côi không?

Không viết precondition trên order_db để giả định nó có thể kiểm tra trực tiếp customer_db nếu không có kết nối/extension được thiết kế rõ. Thông thường orchestrator hoặc ứng dụng kiểm tra prerequisite ở provider, sau đó mới cho phép migration consumer.

## 14. Phụ thuộc giữa producer, CDC và analytics

Một pipeline analytics có thể nhận schema từ nhiều nguồn. Thứ tự triển khai nên chia thành các pha:

1. Provider database mở rộng schema theo hướng backward-compatible.
2. Producer ứng dụng bắt đầu ghi trường mới hoặc phát event version mới.
3. CDC connector/schema registry/pipeline được cập nhật để hiểu schema mới.
4. Consumer database mở rộng schema đích và chấp nhận dữ liệu cũ/mới.
5. Backfill lịch sử nếu cần.
6. Kiểm tra độ trễ, số bản ghi và tính nhất quán.
7. Chuyển query/report sang trường mới.
8. Sau thời gian ổn định, contract cấu trúc cũ.

Với luồng bất đồng bộ, readiness có thể là “consumer đã xử lý tới watermark X” hoặc “schema version Y đã được đăng ký và pipeline healthy”, không chỉ là job Liquibase thành công.

Đừng đặt dependency DAG chỉ theo database; có thể cần node cho connector, topic/schema registry, batch job và ứng dụng. Đồ thị phản ánh **toàn bộ contract phát hành**, không chỉ DDL.

## 15. Phụ thuộc vòng: phát hiện và phá chu trình

Ví dụ:

- `customer_db` cần mã order đầu tiên để hoàn tất onboarding.
- `order_db` lại cần customer được kích hoạt trước khi tạo order.
- Cả hai database đợi dữ liệu của nhau.

Đồ thị có chu trình:

~~~text
customer_db --needs--> order_db
     ^                    |
     |                    v
     +--------------------+
~~~

Không thể giải quyết bằng cách chọn một database chạy trước tùy ý. Cần thay đổi thiết kế hoặc chia quá trình thành nhiều giai đoạn:

- Tạo cấu trúc nullable/optional ở cả hai phía trước.
- Seed các mã tham chiếu độc lập với giao dịch nghiệp vụ.
- Cho phép trạng thái tạm thời như PENDING/PROVISIONING.
- Triển khai code tương thích để không bắt buộc hai phía hoàn tất đồng thời.
- Dùng event/outbox hoặc workflow orchestration để hoàn thiện quan hệ sau.
- Thêm constraint/contract cuối cùng khi cả hai phía đã đạt điều kiện.

Một chu trình trong DAG thường là dấu hiệu **phụ thuộc nghiệp vụ chưa được phân giai đoạn**, không phải vấn đề có thể khắc phục bằng thêm retry hoặc tăng timeout.

## 16. Expand–migrate–contract cho nhiều database

Khi nhiều database và nhiều phiên bản ứng dụng cùng tồn tại, dùng ba giai đoạn:

**Expand**

- Thêm cột/bảng/index mới theo cách tương thích.
- Chưa xóa hoặc đổi nghĩa trường cũ.
- Provider có thể cung cấp cả contract cũ và mới.
- Consumer có thể chấp nhận cả dữ liệu cũ và mới.

**Migrate**

- Triển khai code mới theo thứ tự dependency.
- Backfill hoặc đồng bộ dữ liệu.
- Chạy kiểm tra invariant ở cả nguồn và đích.
- Chuyển dần traffic/query sang contract mới.

**Contract**

- Xác nhận không còn producer/consumer cũ.
- Dừng ghi/đọc trường cũ.
- Xóa constraint, cột hoặc bảng cũ theo thứ tự phụ thuộc.
- Kiểm tra rollback và khả năng phục hồi dữ liệu trước thao tác phá hủy.

Không gộp cả ba giai đoạn vào một release nếu ứng dụng được triển khai rolling hoặc các database không thể cập nhật nguyên tử.

## 17. Điều phối nhiều Liquibase job theo wave

Một release có thể chia thành các wave:

| Wave | Database/job | Điều kiện bắt đầu | Cách chạy |
|---|---|---|---|
| 1 | customer_db expand | Không có prerequisite | Một job |
| 2 | customer_db reference data và order_db expand | Wave 1 hoàn tất; hai job độc lập | Có thể song song |
| 3 | billing_db expand | order_db contract đã sẵn sàng | Sau readiness check |
| 4 | analytics_db consumer | Producer và pipeline đã đạt watermark | Sau xác nhận dữ liệu |
| 5 | contract các database | Ứng dụng cũ không còn dùng schema cũ | Theo thứ tự dependency ngược |

Có thể chạy song song những job cùng wave, nhưng cần giới hạn concurrency theo tài nguyên database, không chỉ theo số lượng job. Nhiều migration nặng trên cùng cluster có thể cạnh tranh I/O, CPU, lock và replication.

Trong một database, nên giữ **một migration owner** tại một thời điểm. Giữa các database độc lập, có thể có nhiều job đồng thời nếu dependency và năng lực vận hành cho phép.

## 18. Liquibase lock là theo từng database, không phải khóa phân tán toàn hệ thống

Mỗi database thường có bảng DATABASECHANGELOG và DATABASECHANGELOGLOCK riêng (trừ khi cấu hình đặc biệt). Lock ở customer_db không tự khóa order_db hay billing_db.

Điều này có nghĩa:

- Hai job cùng chạy Liquibase trên một database và dùng cùng bảng lock có thể được điều phối.
- Hai job trên hai database khác nhau có thể chạy đồng thời.
- Một job trên customer_db không tự ngăn một job trên order_db chạy quá sớm.
- Liquibase lock không điều phối thứ tự giữa Flyway, script thủ công, ETL hoặc ứng dụng.
- Lock không thay thế DAG, readiness check hay release orchestration.

Do đó, **cơ chế dependency phải nằm ở pipeline/controller hoặc quy trình phát hành**, không nằm trong giả định rằng Liquibase tự biết trạng thái database khác.

## 19. Chạy update với nhiều connection/configuration

Mỗi lần chạy Liquibase cần xác định rõ URL, credentials, changelog và schema đích. Ví dụ dạng CLI minh họa:

~~~text
liquibase
  --url=jdbc:postgresql://db-host/customer_db
  --username=customer_migrator
  --changelog-file=db/changelog/customer/db.changelog-customer.yaml
  update
~~~

Sau đó một job khác kết nối order_db với master changelog tương ứng. Cú pháp option chính xác có thể khác theo phiên bản CLI, Maven/Gradle plugin hoặc cách cung cấp properties.

Không nên để pipeline dùng một biến URL chung nhưng vô tình trỏ mọi job về cùng database. Trước update cần in/log an toàn thông tin định danh đích như database/schema/host alias; **không log mật khẩu hoặc secret**.

Nếu ứng dụng Spring Boot có nhiều DataSource, việc chạy Liquibase trên từng datasource cần cấu hình rõ bean/connection tương ứng và thứ tự phụ thuộc. Auto-configuration mặc định thường gắn với một datasource; nhiều datasource thường cần cấu hình Liquibase riêng hoặc migration job độc lập. Kiểm tra chính xác theo Spring Boot version và cấu hình dự án.

## 20. Một database có thể có nhiều changelog hay một changelog dùng nhiều database?

Có hai mô hình phổ biến:

**Mô hình A — Master riêng từng database:** phù hợp khi schema, owner và lịch sử độc lập. Mỗi master include changeset riêng của database.

**Mô hình B — Changelog dùng chung:** phù hợp khi nhiều database có cùng cấu trúc và cần cùng thay đổi. Cùng một artifact được chạy riêng trên từng database, với DBMS filter/contexts/labels khi cần.

| Tiêu chí | Master riêng | Changelog chung |
|---|---|---|
| Schema khác nhau | Dễ tách phạm vi | Cần filter/nhánh rõ |
| Lịch sử riêng | Rõ ràng | Vẫn có history riêng từng DB |
| Tái sử dụng | Thấp hơn | Cao hơn nếu schema tương đồng |
| Nguy cơ chạy nhầm | Giảm nếu connection rõ | Cần guard/filter và kiểm tra target |
| Quản lý phụ thuộc | Dễ biểu diễn theo database | Orchestrator vẫn phải điều phối |

Không tạo một master khổng lồ chứa mọi database và hy vọng một lệnh update tự cập nhật tất cả. Liquibase update chạy trên một connection/database cụ thể; orchestrator phải lặp hoặc fan-out tới từng đích.

## 21. Precondition cho prerequisite cục bộ và điều kiện liên database

Precondition phù hợp để kiểm tra điều kiện trên **database mà Liquibase đang kết nối**, ví dụ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-order-customer-ref
      author: order-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: order
      changes:
        - addColumn:
            tableName: order
            columns:
              - column:
                  name: customer_ref
                  type: varchar(64)
                  constraints:
                    nullable: true
~~~

Precondition này chỉ kiểm tra bảng order trên database đích. Nó không chứng minh customer_db đã có contract cần thiết.

Điều kiện liên database nên được xác minh bởi orchestrator hoặc một readiness service có kết nối được cấp quyền phù hợp. Ví dụ trước job order_db, pipeline kiểm tra customer_db đã có changeset provider và query contract trả về trạng thái sẵn sàng.

Không nhúng credentials của database khác vào precondition SQL để tạo một cơ chế kiểm tra liên database tùy tiện. Điều đó làm tăng coupling, khó audit và có thể không được DBMS hỗ trợ.

## 22. Readiness gate: điều kiện để mở wave tiếp theo

Một readiness gate là phép kiểm tra có kết quả đo được, quyết định wave sau có được bắt đầu hay không.

Ví dụ gate cho order_db:

- customer_db có changeset mở rộng schema đã được ghi nhận.
- Cột/đối tượng có kiểu và constraint mong đợi.
- Mã tham chiếu cần thiết đã tồn tại.
- CDC/event pipeline đã đồng bộ tới watermark cần thiết (nếu có).
- Không còn job migration provider đang chạy.
- Ứng dụng provider đang healthy và contract tương thích.

Gate có thể được thực hiện bằng SQL read-only, API health/contract, metric, event offset hoặc bước kiểm tra tự động. Cần có timeout và trạng thái fail rõ ràng.

**Job trước exit code 0 không phải lúc nào cũng đủ.** Nếu changeset dùng MARK_RAN, có thể không có thao tác SQL nào được thực thi; nếu data migration bất đồng bộ, dữ liệu có thể chưa tới consumer. Gate nên kiểm tra kết quả cuối thay vì chỉ kiểm tra job đã kết thúc.

## 23. Partial failure: khi database đầu thành công, database sau thất bại

Giả sử customer_db và order_db đã cập nhật, nhưng billing_db thất bại vì thiếu quyền tạo index.

Trạng thái sau release:

| Database | Trạng thái | Việc cần làm |
|---|---|---|
| customer_db | Thành công | Giữ nguyên; kiểm tra provider contract |
| order_db | Thành công | Xác nhận consumer tương thích và dữ liệu |
| billing_db | Thất bại | Điều tra quyền/index, xác định có thực thi một phần không |
| analytics_db | Chưa chạy | Giữ ở trạng thái blocked do prerequisite chưa đạt |

Không thể giả định toàn bộ release được rollback như một transaction duy nhất. Mỗi database có DATABASECHANGELOG và transaction riêng; DDL có thể commit độc lập. Khi một wave thất bại:

1. Dừng các wave downstream.
2. Giữ lại bằng chứng log, revision và trạng thái từng database.
3. Xác định database thất bại đã thực thi được những gì.
4. Kiểm tra schema/data/history, không chỉ exit code.
5. Quyết định sửa lỗi rồi resume, forward fix hay rollback một số database.
6. Kiểm tra tương thích giữa các service trong trạng thái trung gian.
7. Ghi nhận release state để lần chạy sau tiếp tục đúng nơi.

## 24. Retry và resume: không chạy lại toàn bộ một cách mù quáng

Liquibase sử dụng DATABASECHANGELOG để xác định changeset đã được ghi nhận. Nếu một database đã hoàn thành, update tiếp theo thông thường sẽ bỏ qua changeset đã áp dụng và xử lý pending changeset còn lại.

Tuy nhiên, retry chỉ an toàn khi:

- Identity id/author/filename và checksum changelog không bị thay đổi ngoài ý muốn.
- Changeset trước không để lại trạng thái thực thi một phần.
- DDL transaction/implicit commit đã được kiểm tra.
- Các thay đổi ngoài Liquibase không làm lệch schema.
- Precondition và dữ liệu đầu vào vẫn thỏa điều kiện.
- Pipeline giữ đúng revision release.

Không đổi id/author/path của changeset đã triển khai để “chạy lại”. Nếu migration một phần cần sửa, tạo changeset sửa tiếp hoặc recovery script được review. Không xóa row DATABASECHANGELOG để ép update chạy lại.

## 25. Rollback nhiều database không phải thao tác nguyên tử

Khi một release thay đổi ba database, rollback từng database cũng là những thao tác độc lập. Không có transaction phân tán tự động chỉ vì tất cả job dùng Liquibase.

Nếu dependency là A → B → C, khi rollback toàn bộ có thể cần xem xét thứ tự ngược C → B → A, nhưng **không phải lúc nào rollback ngược thứ tự cũng an toàn**. C có thể đã tạo dữ liệu mà A không thể khôi phục; hoặc code đã ghi dữ liệu mới trong khi release đang hoạt động.

Trước khi rollback:

- Xác định những database đã update và những database chưa update.
- Xác định các service đang chạy phiên bản nào.
- Kiểm tra dữ liệu phát sinh kể từ khi migration hoàn tất.
- Preview rollback SQL cho từng database.
- Đánh giá lock, transaction, backup/PITR và dependency.
- Chọn rollback, forward fix hoặc giữ schema mở rộng.

Có thể cần dùng **compensating action** ở cấp nghiệp vụ thay vì cố rollback DDL. Ví dụ vô hiệu hóa tính năng mới hoặc ngừng consumer trước, rồi mới thay đổi schema sau khi không còn ghi dữ liệu.

## 26. Tránh phụ thuộc phiên bản ứng dụng không tương thích

Một database có thể đã expand nhưng ứng dụng consumer chưa được deploy. Đó thường là trạng thái trung gian an toàn nếu schema mới backward-compatible.

Ngược lại, nếu migration contract xóa cột cũ trong khi một service cũ vẫn đang chạy, release có thể làm hỏng truy vấn đang hoạt động.

Hãy lập ma trận tương thích:

| Schema | App cũ | App mới | Trạng thái |
|---|---|---|---|
| Schema cũ | Hỗ trợ | Có thể chưa hỗ trợ | Trạng thái trước release |
| Schema expand | Hỗ trợ nếu backward-compatible | Hỗ trợ | Thường là giai đoạn an toàn để rollout |
| Schema migrate | Cần kiểm tra dữ liệu/dual-read-write | Hỗ trợ | Giai đoạn chuyển tiếp |
| Schema contract | Có thể không hỗ trợ | Hỗ trợ | Chỉ khi không còn app cũ |

Dependency DAG nên bao gồm cả bước deploy application, backfill và consumer switch, không chỉ Liquibase update. Thứ tự an toàn có thể là database expand → provider app → consumer schema expand → consumer app → backfill/verify → contract.

## 27. Thiết kế pipeline CI/CD theo DAG

Một pipeline có thể chạy các node độc lập song song và đợi prerequisite:

~~~yaml
stages:
  - customer_expand
  - consumer_expand
  - billing_expand
  - analytics_enable

customer_migration:
  stage: customer_expand
  script:
    - run-liquibase-customer-update

order_migration:
  stage: consumer_expand
  needs:
    - customer_migration
  script:
    - check-customer-contract-ready
    - run-liquibase-order-update

billing_migration:
  stage: billing_expand
  needs:
    - order_migration
  script:
    - check-order-contract-ready
    - run-liquibase-billing-update

analytics_migration:
  stage: analytics_enable
  needs:
    - customer_migration
    - billing_migration
  script:
    - check-source-watermarks
    - run-liquibase-analytics-update
~~~

Đây là ví dụ khái niệm theo cú pháp pipeline tương tự một số CI system; trường `needs`, `stages` và script phải được điều chỉnh theo nền tảng thực tế. Không phải cấu hình Liquibase trực tiếp.

Pipeline cần thêm:

- Target database alias và secret riêng.
- Revision artifact cố định cho mọi job trong release.
- Serialization/lock theo database để tránh hai migration owner cùng chạy.
- Timeout và retry có giới hạn.
- Readiness gate sau từng wave.
- Lưu trạng thái và log cho từng database.
- Quy trình manual approval ở bước phá hủy hoặc production.
- Dừng downstream khi prerequisite fail.

## 28. Spring Boot với nhiều DataSource

Spring Boot thường tự cấu hình Liquibase cho datasource được chọn theo cấu hình auto-configuration. Nếu ứng dụng có nhiều DataSource, không nên giả định Liquibase tự biết phải chạy trên tất cả database và theo đúng thứ tự.

Các lựa chọn kiến trúc:

1. **Migration job riêng:** mỗi database có một job Liquibase độc lập; CI/CD điều phối DAG. Đây thường là cách dễ kiểm soát thứ tự và quyền.
2. **Nhiều Liquibase bean:** ứng dụng cấu hình bean/connection riêng cho từng datasource, chỉ rõ changelog, schema và thứ tự phụ thuộc. Cần cẩn trọng lifecycle, transaction manager và auto-configuration theo Spring Boot version.
3. **Tách service/database ownership:** mỗi service tự quản lý database của mình, còn release orchestration đảm bảo provider trước consumer.

Nếu dùng nhiều Liquibase bean trong một tiến trình, thứ tự bean khởi tạo không nên là cơ chế dependency ngầm. Hãy khai báo dependency rõ ràng và có readiness check; khi migration dài hoặc phá hủy, job riêng thường dễ quan sát và kiểm soát hơn.

Không để cả pipeline migration job và mọi replica Spring Boot cùng auto-run trên cùng database mà chưa có chính sách single-writer. DATABASECHANGELOGLOCK giúp điều phối Liquibase trên cùng bảng lock, nhưng không điều phối các database khác nhau hoặc công cụ ngoài Liquibase.

## 29. Quan sát trạng thái triển khai trên từng database

Một dashboard release nên hiển thị trạng thái theo database và theo node DAG:

| Database | Liquibase job | Readiness | Schema/data check | Release state |
|---|---|---|---|---|
| customer_db | Success | Pass | Pass | Ready |
| order_db | Success | Pass | Pass | Ready |
| billing_db | Failed | Blocked | Unknown/partial | Needs recovery |
| analytics_db | Not started | Blocked | Not checked | Waiting |

Những thông tin hữu ích:

- Release ID, commit SHA và changelog revision.
- DBMS/version, database/schema alias.
- Thời điểm bắt đầu/kết thúc, người/job owner.
- Changeset pending/đã chạy và EXECTYPE.
- Liquibase lock wait và DBMS lock wait nếu có.
- Kết quả readiness query, row count và watermark.
- Tình trạng ứng dụng/CDC/consumer.
- Lỗi, retry, quyết định resume/rollback và người phê duyệt.

Không đưa password, token hoặc dữ liệu nhạy cảm vào dashboard. Log cần đủ thông tin để chẩn đoán nhưng vẫn tuân thủ quyền truy cập.

## 30. Bài thực hành: sắp xếp ba database theo phụ thuộc

Thực hành trên database thử nghiệm hoặc môi trường disposable.

### Bối cảnh

- `customer_db` sở hữu customer và customer_tier.
- `order_db` sở hữu order và lưu customer_ref.
- `analytics_db` tổng hợp dữ liệu customer và order.

### Bước 1 — Viết dependency graph

~~~text
customer_db expand
       |
       v
customer_db seed/reference data
       |
       +------------------+
       |                  |
       v                  v
order_db expand       analytics_db expand
       |
       v
order_db backfill/verify
       |
       v
analytics_db consume order data
~~~

### Bước 2 — Chia wave

| Wave | Công việc | Điều kiện hoàn tất |
|---|---|---|
| 1 | Customer schema expand | Cột/bảng mới tồn tại, ứng dụng cũ vẫn tương thích |
| 2 | Seed customer reference; order schema expand; analytics schema expand | Provider data sẵn sàng; các thay đổi độc lập hoàn tất |
| 3 | Order backfill và verify | customer_ref hợp lệ, không còn giá trị sai |
| 4 | Analytics consume order data | CDC/ETL đạt watermark, dữ liệu được đối chiếu |
| 5 | Contract cấu trúc cũ | Không còn ứng dụng/consumer sử dụng contract cũ |

### Bước 3 — Chuẩn bị changelog

Tạo master changelog riêng cho từng database, mỗi database có DATABASECHANGELOG riêng. Không dùng một URL chung cho mọi job. Ghim cùng revision release và credentials được cấp riêng.

### Bước 4 — Chạy trên clone

Chạy wave 1, kiểm tra schema và ứng dụng. Chỉ khi gate pass mới chạy wave 2. Thử cố ý làm order migration fail vì thiếu quyền; quan sát analytics downstream bị giữ ở trạng thái blocked.

### Bước 5 — Resume

Sửa quyền trên database thử nghiệm, giữ nguyên changelog revision, xác minh trạng thái order_db trước khi retry. Không xóa lịch sử customer_db hoặc chạy lại migration đã thành công.

### Bước 6 — Thử partial failure và rollback

Mô phỏng analytics migration thất bại sau khi customer/order đã thành công. Quyết định giữ schema expand và forward fix analytics hay rollback theo kế hoạch. Ghi rõ vì sao không có một transaction chung cho cả ba database.

## 31. Checklist trước khi chọn thứ tự triển khai

- [ ] Đã liệt kê tất cả database, schema, owner, service producer và consumer.
- [ ] Đã phân loại phụ thuộc schema, reference data, CDC/ETL, khóa và ứng dụng.
- [ ] Mỗi cạnh dependency có readiness condition đo được.
- [ ] Đồ thị phụ thuộc không có chu trình chưa được giải quyết.
- [ ] Đã topological sort và chia wave; node độc lập được cân nhắc chạy song song.
- [ ] Đã xác định database nào cần master changelog riêng và database nào dùng chung changelog.
- [ ] Mỗi Liquibase job có URL/schema/credentials đích rõ ràng.
- [ ] Revision/artifact changelog được ghim nhất quán trong một release.
- [ ] Mỗi database chỉ có một migration owner tại một thời điểm.
- [ ] Không giả định DATABASECHANGELOGLOCK khóa các database khác hoặc công cụ ngoài Liquibase.
- [ ] Provider expand trước consumer switch; contract diễn ra sau khi consumer cũ đã ngừng.
- [ ] Data readiness được kiểm tra riêng với schema readiness.
- [ ] CDC/ETL có watermark/offset và tiêu chí lag phù hợp.
- [ ] Precondition chỉ kiểm tra đúng database kết nối; cross-database gate do orchestrator xử lý.
- [ ] Pipeline dừng downstream khi prerequisite fail.
- [ ] Có trạng thái partial failure, resume và recovery rõ ràng cho từng database.
- [ ] Rollback được đánh giá theo dependency ngược và dữ liệu phát sinh, không giả định atomic.
- [ ] Đã thử trên clone có schema/data đại diện.
- [ ] Spring Boot nhiều DataSource có cấu hình Liquibase và thứ tự rõ ràng.
- [ ] Dashboard lưu trạng thái từng database, readiness, changeset và release revision.
- [ ] Secrets được quản lý riêng; log không lộ thông tin nhạy cảm.
- [ ] Có owner, approval, runbook và hậu kiểm sau release.

**Ghi nhớ:** Khi có phụ thuộc giữa nhiều database, hãy mô hình hóa provider, consumer và điều kiện sẵn sàng thành **DAG**, sau đó dùng topological order để chia các wave triển khai. Liquibase quản lý changeset và lịch sử trên từng database; nó không tạo transaction phân tán hay tự điều phối thứ tự giữa nhiều database. Một pipeline đáng tin cậy cần single-writer cho mỗi database, readiness gate giữa các wave, schema/data migration tương thích trong giai đoạn chuyển tiếp, cùng kế hoạch resume hoặc forward fix khi một phần release thất bại. Đó là cách phối hợp migration có kiểm chứng qua nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

