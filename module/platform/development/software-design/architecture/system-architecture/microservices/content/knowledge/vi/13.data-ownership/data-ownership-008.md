# Thay đổi lược đồ mà không buộc dịch vụ khác cùng phát hành

## Mục tiêu bài học

Một lợi ích quan trọng của Microservices là các nhóm có thể phát triển, triển khai và vận hành những năng lực nghiệp vụ với nhịp độ khác nhau. Nhưng tính độc lập này dễ mất đi nếu nhiều dịch vụ đọc chung bảng database, phụ thuộc trực tiếp vào cấu trúc JSON nội bộ hoặc buộc phải đổi đồng thời khi một trường dữ liệu được thêm, đổi tên hay loại bỏ.

Ví dụ: Customer Service đổi cột customer_name thành full_name trong cơ sở dữ liệu. Nếu Ordering, Billing và Notification đều đọc trực tiếp bảng customers hoặc deserialize một cấu trúc không có hợp đồng ổn định, việc thay đổi nhỏ ở Customer trở thành một đợt phát hành chung. Khi một trong các dịch vụ chưa sẵn sàng, toàn hệ thống có thể ngừng triển khai hoặc xảy ra lỗi runtime.

Mục tiêu của thiết kế đúng là: **dịch vụ sở hữu dữ liệu có thể tiến hóa lược đồ mà không buộc tất cả consumer phải triển khai cùng thời điểm**, trong một giới hạn tương thích đã được công bố và kiểm thử.

Sau bài này, người học có thể:

1. Phân biệt database schema nội bộ với API contract, event schema và read model.
2. Giải thích vì sao ownership và quyền truy cập dữ liệu quyết định khả năng phát hành độc lập.
3. Áp dụng chiến lược **expand → migrate → contract** cho những thay đổi có nguy cơ phá tương thích.
4. Tổ chức zero-downtime migration khi nhiều phiên bản ứng dụng cùng chạy.
5. Quản lý schema version, consumer contract, event evolution và quá trình chuyển đổi dữ liệu.
6. Xử lý rollback, backfill, dữ liệu cũ và thay đổi không tương thích một cách có kiểm soát.
7. Minh họa bằng SQL, Java/Spring Boot, Flyway và kế hoạch rollout liên dịch vụ.

## 1. Phân biệt bốn lớp lược đồ

Từ schema có thể chỉ nhiều thứ khác nhau:

| Lớp | Ví dụ | Ai nên sở hữu |
| --- | --- | --- |
| Database schema nội bộ | Bảng customers, cột full_name, index, constraint | Customer Service |
| API contract | GET /customers/{id} trả customerDisplayName | Service công bố API |
| Event/integration schema | CustomerProfileUpdated v1 có customerId, displayName | Service phát sự kiện, quản trị cùng consumer |
| Read model/projection | Bảng customer_snapshot trong Ordering | Ordering sở hữu bản sao phục vụ use case của mình |

Một dịch vụ có thể thay đổi database schema **mà không đổi public API**. Ngược lại, thay đổi API hoặc event schema vẫn có thể phá consumer dù không hề đổi bảng database.

Ví dụ:

~~~text
Customer database:
  customers(id, first_name, last_name)

Customer public API:
  CustomerProfile { id, displayName }

Ordering projection:
  order_customer_snapshot(order_id, display_name_at_purchase)
~~~

Customer có thể tách first_name/last_name thành cấu trúc khác nhưng tiếp tục trả displayName qua API. Ordering không cần biết sự thay đổi của các cột nội bộ.

### 1.1. Vì sao database shared làm mất tự chủ?

Giả sử nhiều service cùng query một bảng:

~~~text
Customer Service -----------+
Ordering Service -----------+----> Shared DB: customers
Billing Service ------------+
Notification Service -------+
~~~

Các service bị kết dính với:
- Tên bảng và tên cột.
- Kiểu dữ liệu, nullability và constraint.
- Join, index và transaction assumptions.
- Semantics: cột status có nghĩa gì ở từng thời điểm.
- Lịch bảo trì, migration và quyền truy cập của cùng database.

Một thay đổi có thể chạy tốt trong Customer nhưng làm hỏng một SQL query chưa được biết trong Billing. Đó là **coupling ngầm qua storage**, không thể giải quyết chỉ bằng CI/CD riêng.

### 1.2. Quyền sở hữu dữ liệu không đòi một server database vật lý riêng

Database-per-service là nguyên tắc ownership và isolation, không bắt buộc mỗi service có một máy chủ database riêng.

Có thể dùng:
- Database instance riêng.
- Database/schema riêng trên cùng cluster được kiểm soát quyền.
- Tập bảng riêng nhưng có ranh giới quyền truy cập chặt, như bước chuyển tiếp.

Điều quyết định là **service khác không tự đọc/ghi bảng nội bộ của service sở hữu**. Shared physical cluster có thể hợp lý về vận hành, nhưng phải giảm coupling ở logical schema, quyền database, migration và transaction.

Một quy tắc hữu ích: chỉ service sở hữu dữ liệu được phép thay đổi schema và định nghĩa bất biến của dữ liệu đó. Service khác lấy thông tin qua API, event hoặc read model được công bố.

## 2. Mục tiêu là tương thích theo thời gian, không phải bất biến mãi mãi

Trong Microservices, các phiên bản thường cùng tồn tại:

~~~text
Time ─────────────────────────────────────────────>

Customer v1 ────────── Customer v2 ───────── v3
Ordering v1 ────────────────── Ordering v2 ─────
Billing v1 ─────────────────────────────────── v2
Events   E1 ─────────── E1 + E2 ───── E2 ───────
~~~

Trong rolling deployment, ngay cả cùng một service cũng có thể có instance code v1 và v2 chạy đồng thời. Vì vậy việc migration database không chỉ phải phù hợp code mới; nó phải hoạt động trong **khoảng thời gian chồng lấn giữa các phiên bản**.

Một thay đổi chỉ an toàn khi các trạng thái triển khai thực sự có thể xuất hiện đều tương thích:
- Code cũ trên schema đã expand.
- Code mới trên schema đã expand nhưng chưa backfill xong.
- Code cũ và mới cùng ghi dữ liệu.
- Consumer cũ đọc event từ producer mới.
- Consumer mới đọc event lịch sử hoặc message được replay.
- Rollback ứng dụng khi database đã được migrate.

Không cần giữ mọi phiên bản vô hạn. Cần **định nghĩa cửa sổ tương thích và chính sách ngừng hỗ trợ** rõ, sau đó kiểm tra bằng dữ liệu triển khai.

## 3. Tương thích ngược, tương thích xuôi và tương thích khi rollout

**Backward compatibility** trong API/event thường nghĩa là consumer mới vẫn hiểu dữ liệu/hợp đồng cũ, hoặc producer mới không phá consumer cũ, tùy bối cảnh. Để tránh hiểu nhầm thuật ngữ, hãy nêu cặp vai trò cụ thể:

- **Old consumer + new producer:** consumer đang chạy có xử lý được response/event do phiên bản mới phát không?
- **New consumer + old producer:** consumer mới có xử lý được response/event từ phiên bản cũ không?
- **Old application + expanded database:** code cũ có tiếp tục đọc/ghi bình thường không?
- **New application + partially migrated data:** code mới có xử lý được dòng chưa backfill không?

Có thể xem rollout thành một ma trận:

| Nhà cung cấp / người tiêu thụ | Consumer cũ | Consumer mới |
| --- | --- | --- |
| Producer cũ | Phải hoạt động trước migration | Nên hỗ trợ trong giai đoạn chuyển tiếp |
| Producer mới | Phải hoạt động trong giai đoạn coexistence | Là trạng thái đích |

Nếu chỉ test ô góc dưới bên phải (producer mới với consumer mới), bạn chưa chứng minh hệ thống cho phép triển khai độc lập.

### 3.1. Thay đổi tương thích thường gặp

- Thêm một trường tùy chọn trong response nếu consumer không phụ thuộc vào schema đóng.
- Thêm cột nullable trong database khi code cũ vẫn INSERT bình thường.
- Thêm index không làm thay đổi semantics dữ liệu.
- Phát thêm một event type mới song song với event cũ.
- Thêm endpoint API mới, giữ endpoint cũ.
- Chấp nhận cả format cũ lẫn mới trong khoảng chuyển tiếp.

### 3.2. Thay đổi dễ phá tương thích

- Đổi tên hoặc xóa một cột đang được code cũ sử dụng.
- Thêm cột NOT NULL không có default khi code cũ không ghi cột đó.
- Đổi ý nghĩa business của một trường mà không đổi tên.
- Đổi kiểu string sang integer khi consumer cũ chỉ hiểu string.
- Bỏ field bắt buộc trong API/event.
- Thay enum bằng giá trị mới khi consumer cũ dùng switch exhaustive.
- Đổi tên event/topic rồi dừng phát loại cũ ngay.
- Đổi timezone hoặc đơn vị tiền tệ mà không đổi contract.

Câu hỏi không chỉ là “JSON còn parse được không?”, mà là **semantics cũ có còn đúng không**. Một field amount tiếp tục tồn tại nhưng đổi từ đồng sang cent mà không thông báo vẫn là breaking change.

## 4. Chiến lược expand → migrate → contract

Đây là khuôn mẫu phổ biến để thay đổi schema mà không buộc tất cả ứng dụng/consumer triển khai đồng thời.

~~~text
Phase 1: EXPAND
  Thêm cấu trúc mới, giữ cấu trúc cũ.
  Code cũ vẫn chạy.

Phase 2: MIGRATE
  Chuyển dần dữ liệu, code đọc/ghi và consumer.
  Có thể tồn tại cả cũ và mới.

Phase 3: CONTRACT
  Sau khi chứng minh không còn người dùng cấu trúc cũ,
  mới xóa field/bảng/endpoint hoặc ngừng event cũ.
~~~

Điểm mấu chốt: **bước xóa/sửa phá tương thích xảy ra sau, không phải cùng lúc thêm cấu trúc mới**.

### 4.1. Ví dụ đổi tên cột

Ban đầu:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    customer_name VARCHAR(255) NOT NULL
);
~~~

Mục tiêu cuối:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL
);
~~~

Lệnh trực tiếp:

~~~sql
ALTER TABLE customers RENAME COLUMN customer_name TO full_name;
~~~

có thể làm code cũ lỗi ngay nếu nó còn query customer_name. Cách phù hợp cho zero-downtime rollout có thể chia thành nhiều bước.

**Expand:** thêm cột mới tạm cho phép NULL.

~~~sql
ALTER TABLE customers
ADD COLUMN full_name VARCHAR(255);
~~~

**Migrate:** code phiên bản chuyển tiếp tiếp tục phục vụ contract cũ, đồng thời bảo đảm full_name được ghi đúng cho dữ liệu mới; backfill dữ liệu lịch sử thành các batch có kiểm soát.

**Contract:** sau khi code và job cũ không còn dùng customer_name, kiểm tra dữ liệu, thêm constraint phù hợp và xóa cột cũ trong migration riêng.

Đối với database có table lớn, câu ALTER có thể tạo lock hoặc rewrite dữ liệu. Kỹ thuật thực hiện online DDL, batch migration và index online phụ thuộc engine/version, phải đánh giá thực tế trước khi chạy production.

## 5. Ví dụ đầy đủ: đổi trường tên khách hàng qua nhiều bản phát hành

Giả sử Customer Service sở hữu bảng customers, còn API công khai vẫn trả displayName. Trước đây DB có cột customer_name; đội phát triển muốn tách tên thành first_name và last_name để phục vụ quy tắc hiển thị đa quốc gia.

### 5.1. Trạng thái ban đầu

~~~text
DB:
  customers(id, customer_name)

API:
  GET /customers/42
  { "id":42, "displayName":"Nguyen Van An" }

Consumer:
  Ordering lưu displayName tại thời điểm tạo đơn.
  Notification dùng displayName trong nội dung tin.
~~~

**Điều quan trọng:** Consumer chỉ biết displayName, không biết cột customer_name. Đây là ranh giới bảo vệ sự độc lập.

### 5.2. Bước A — Expand database

~~~sql
ALTER TABLE customers
ADD COLUMN first_name VARCHAR(120);

ALTER TABLE customers
ADD COLUMN last_name VARCHAR(120);
~~~

Giữ customer_name để Customer v1 tiếp tục đọc/ghi. Không đặt NOT NULL quá sớm nếu code cũ vẫn có thể insert row mà không biết cột mới.

### 5.3. Bước B — Triển khai phiên bản chuyển tiếp

Customer v2 có thể:
- Khi ghi profile mới, ghi customer_name và các trường mới theo một transaction cục bộ.
- Khi đọc, ưu tiên first_name/last_name nếu có dữ liệu hợp lệ, nếu không dùng customer_name.
- Tiếp tục trả displayName trong API như trước.
- Phát event CustomerProfileUpdated với contract ổn định.

**Dual-write không tự an toàn** nếu hai nguồn có thể bị ghi lệch bởi code cũ và code mới. Cần xác định nguồn có thẩm quyền, cách đồng bộ, kiểm tra consistency và xử lý trường hợp rollout có đồng thời v1/v2.

Nếu còn v1 có thể ghi customer_name mà không cập nhật first_name/last_name, v2 phải có fallback khi đọc và một backfill/reconcile liên tục hoặc cơ chế đồng bộ thích hợp. Không được tuyên bố “đã backfill xong” khi vẫn còn writer cũ làm tạo dữ liệu chỉ có format cũ.

### 5.4. Bước C — Backfill dữ liệu lịch sử

Tách tên người theo dấu cách là bài toán nghiệp vụ phức tạp, không nên tự động coi token đầu là first_name và token cuối là last_name cho mọi quốc gia. Có thể dùng quy tắc dữ liệu đã xác minh, yêu cầu người dùng cập nhật hoặc lưu fullDisplayName riêng nếu không đủ thông tin.

Một backfill có thể chạy theo khóa chính:

~~~text
for each batch of customers ordered by id:
    find rows missing new fields
    transform using verified business rule
    update only if current version still matches
    record checkpoint and metrics
    continue until complete
~~~

Backfill nên có:
- Batch size và tốc độ giới hạn.
- Cursor/checkpoint có thể resume.
- Query dùng index phù hợp.
- Idempotency: chạy lại không làm sai dữ liệu.
- Optimistic locking hoặc điều kiện UPDATE tránh ghi đè chỉnh sửa mới.
- Tỷ lệ lỗi và dead-letter/manual review cho dữ liệu không chuyển đổi được.
- Metrics số dòng còn thiếu và thời gian dự kiến hoàn tất.

Không giữ một transaction khổng lồ hoặc lock cả bảng nếu không thật sự cần.

### 5.5. Bước D — Chuyển toàn bộ code đọc sang format mới

Triển khai Customer v3:
- Đọc các trường mới làm nguồn chính khi đã có dữ liệu đầy đủ.
- Tiếp tục trả displayName cho API.
- Theo dõi request/feature/job cũ còn truy cập customer_name hay không.
- Dừng ghi customer_name **chỉ sau khi** không còn writer cũ và cơ chế rollback được đánh giá.

### 5.6. Bước E — Contract database

Sau khi:
- Dữ liệu mới đã đầy đủ.
- Không còn code cũ đọc/ghi customer_name.
- Consumer không có truy cập trực tiếp tới bảng.
- Các job, report và pipeline dữ liệu đã được kiểm kê.
- Khả năng rollback không còn phụ thuộc customer_name.

mới thực hiện migration riêng để thêm constraint/index cần thiết và loại bỏ cột cũ:

~~~sql
-- Chỉ minh họa, áp dụng khi dữ liệu đã hợp lệ và engine cho phép.
ALTER TABLE customers
DROP COLUMN customer_name;
~~~

Tại mỗi giai đoạn, các service khác vẫn gọi API Customer hoặc xử lý event contract cũ; chúng không cần cùng phát hành chỉ để Customer đổi schema nội bộ.

## 6. Một bảng quyết định trước khi sửa database

| Thay đổi | Rủi ro chính | Chiến lược thường dùng |
| --- | --- | --- |
| Thêm cột nullable | Code cũ có tiếp tục insert? | Expand trước, code đọc sau |
| Thêm NOT NULL | Dữ liệu cũ thiếu giá trị, writer cũ không biết trường | Add nullable → backfill → validate → enforce |
| Đổi tên cột | Code cũ còn dùng tên cũ | Add new → bridge reads/writes → backfill → drop old |
| Đổi kiểu dữ liệu | Mất dữ liệu, conversion không tương thích | Cột mới, chuyển dần, kiểm tra domain |
| Tách một bảng thành hai | Read/write path cũ không còn đúng | Shadow schema, sync, cutover có kiểm soát |
| Gộp hai trường | Semantics và dữ liệu lịch sử có thể mất | Chuyển dữ liệu có kiểm chứng, giữ bridge |
| Thêm index | Lock/rewrite, disk/IO tăng | Online/concurrent index nếu engine hỗ trợ |
| Xóa index | Query cũ còn phụ thuộc | Quan sát query plan và usage trước khi xóa |
| Đổi primary/business key | FK, cache, event và API cùng ảnh hưởng | Mapping và transition kéo dài, có unique constraint |
| Xóa bảng/field | Dependency ẩn và rollback thất bại | Chỉ contract sau evidence không còn consumer |

Một phép ALTER “chạy được trong staging” không tự bảo đảm chạy không khóa lớn trong production. Dataset, query plan và hoạt động ghi thực có thể khác nhau.

## 7. Database migration và application deployment là hai lịch khác nhau

Trong quá trình phát hành:
- Schema có thể được migrate trước khi code mới chạy.
- Replica ứng dụng cũ và mới có thể tồn tại đồng thời.
- Migration tool có thể hoàn thành trong vài giây nhưng backfill cần hàng giờ.
- Rollback code không có nghĩa rollback dữ liệu sẽ an toàn.
- Một feature flag có thể bật trên một nhóm người dùng trước khi toàn bộ rollout hoàn tất.

Nên thiết kế **mỗi bước có thể chạy độc lập** và có preconditions đo được.

Ví dụ:

~~~text
Release 1:
  DB expand: add new nullable column
  Deploy code đọc cũ, có thể ghi song song theo policy
  Không đổi contract công khai

Release 2:
  Deploy bridge code hỗ trợ cả old/new
  Backfill dữ liệu lịch sử theo batch
  Theo dõi consistency

Release 3:
  Khi writers/readers cũ đã rời hệ thống
  Chuyển đọc chính sang cột mới
  Giữ đường fallback ngắn hạn

Release 4:
  Sau compatibility window và bằng chứng không còn dependency
  Contract: xóa cột cũ, thêm ràng buộc cuối cùng
~~~

Không nhất thiết phải đúng bốn release; số bước phụ thuộc độ rủi ro và môi trường. Mục tiêu là mỗi bước có đường đi an toàn trong khoảng chồng lấn phiên bản.

### 7.1. Migration tool làm gì?

Flyway/Liquibase giúp version hóa migration và chạy chúng theo thứ tự, nhưng công cụ không quyết định một thay đổi có backward-compatible hay không. Một migration DROP COLUMN vẫn phá code cũ dù được Flyway chạy thành công.

Đảm bảo:
- Migrations được quản lý trong repository của service sở hữu schema.
- Một owner chịu trách nhiệm phê duyệt thay đổi phá tương thích.
- Migration ordering rõ ràng.
- Có kế hoạch chạy trên database production đang có lưu lượng.
- Có metrics thời gian chạy, lock wait và trạng thái hoàn tất.
- Không để nhiều service cùng quản lý cùng một schema lịch sử.

## 8. Ví dụ Flyway trong Spring Boot

Cấu trúc ví dụ:

~~~text
customer-service/
  src/main/resources/
    db/migration/
      V1__create_customers.sql
      V2__add_name_components.sql
      V3__add_profile_indexes.sql
  src/main/java/
    customer/
      domain/
      application/
      adapter/
~~~

Migration expand:

~~~sql
-- V2__add_name_components.sql
ALTER TABLE customers
ADD COLUMN first_name VARCHAR(120);

ALTER TABLE customers
ADD COLUMN last_name VARCHAR(120);
~~~

Cấu hình minh họa:

~~~yaml
spring:
  flyway:
    enabled: true
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Không để Hibernate tự ý thay đổi schema production bằng chế độ update khi muốn kiểm soát migration lịch sử. Cần lưu ý môi trường, engine và Flyway configuration; không phải mọi hệ thống đều nên tự chạy migration khi mọi pod khởi động đồng thời.

### 8.1. Ai chạy migration?

Lựa chọn triển khai:
- Một CI/CD migration job có quyền hạn tối thiểu phù hợp.
- Một init/migration container có cơ chế đảm bảo chỉ một owner thực hiện.
- Một migration service chuyên trách thuộc cùng domain.
- App startup migration chỉ khi cơ chế lock và quy trình rollout đã được chứng minh an toàn.

Dù chọn cách nào, schema expand phải sẵn sàng **trước khi** code cần cấu trúc mới nhận traffic. Không phải mọi migration đều nên chạy tự động cùng lúc với mỗi pod mới.

### 8.2. Không dùng migration SQL cho backfill cực lớn một cách tùy tiện

Một câu UPDATE toàn bảng có thể tạo transaction lớn, lock lâu, tăng WAL/binlog và replication lag. Backfill phức tạp thường cần worker riêng, phân batch, giới hạn tốc độ và checkpoint. Migration DDL và migration dữ liệu có thể là các pha tách biệt.

## 9. Quyền sở hữu data đi cùng quyền database

Mô hình:

~~~text
Customer Service
    |
    +---- writes/reads ----> Customer database/schema
    |
    +---- API / event -----> Ordering, Billing, Notification

Ordering Service
    |
    +---- writes/reads ----> Ordering database/schema
~~~

Ở mức quyền truy cập:
- Customer app credential được đọc/ghi bảng sở hữu cần thiết.
- Ordering app credential không có quyền SELECT trực tiếp trên bảng Customer.
- Migration credential có quyền DDL riêng, không nhất thiết dùng trong runtime.
- Analytics và reporting nên qua data pipeline, read replica có chính sách hoặc event/read models được thiết kế, tránh đường truy cập lén thành dependency vận hành.

Nếu service A vẫn có quyền đọc trực tiếp DB của B, một thay đổi lược đồ “nội bộ” có thể phá A mà chủ sở hữu B không hay biết.

### 9.1. Không tạo foreign key xuyên ranh giới service

Một database có thể cho phép FK giữa các bảng, nhưng trong Microservices mỗi service sở hữu dữ liệu và transaction riêng. FK xuyên database hoặc một join trực tiếp qua owner boundaries là hình thức coupling.

Thay vì Ordering có FK trực tiếp đến Customer database:
- Ordering lưu customerId như một reference nghiệp vụ.
- Customer Service là nguồn có thẩm quyền về hồ sơ khách.
- Ordering có thể gọi Customer API khi cần xác minh điều kiện nghiệp vụ.
- Ordering lưu snapshot các thuộc tính cần thiết tại thời điểm đặt hàng.
- Những phản ứng thay đổi profile có thể được chuyển qua event/projection.

Tính nhất quán giữa service phải được định nghĩa ở cấp nghiệp vụ, không giả định một transaction SQL bao phủ toàn bộ.

## 10. API contract là bức tường bảo vệ schema nội bộ

Một DB migration tốt vẫn có thể gây release coupling nếu API trả trực tiếp JPA entity:

~~~java
@GetMapping("/customers/{id}")
public CustomerEntity getCustomer(@PathVariable long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Khi CustomerEntity đổi cột, đổi quan hệ hoặc thêm field nhạy cảm, serialization có thể đổi ngoài ý muốn. API nên trả DTO được version và duy trì có chủ đích:

~~~java
public record CustomerProfileResponse(
    String id,
    String displayName,
    String preferredLanguage
) {}

@GetMapping("/customers/{id}")
public CustomerProfileResponse getCustomer(@PathVariable String id) {
    Customer customer = queryUseCase.find(id);
    return new CustomerProfileResponse(
        customer.id(),
        customer.displayName(),
        customer.preferredLanguage()
    );
}
~~~

DTO không phải entity. DB có thể chuyển từ một cột name sang nhiều cột mà DTO vẫn giữ displayName. Consumer không phải redeploy.

### 10.1. Thêm trường không phải lúc nào cũng an toàn

Thêm optional JSON field thường dễ tương thích hơn xóa field, nhưng một consumer cấu hình JSON parser strict để reject unknown fields có thể lỗi. Cần biết tính chất consumer thực tế và có contract tests cho các client quan trọng.

Không nên đưa field mới có ý nghĩa nhạy cảm hoặc yêu cầu consumer bắt buộc xử lý vào response cũ chỉ vì schema parser có thể bỏ qua nó. Khi semantics của nghiệp vụ thay đổi, cần plan migration có communication.

### 10.2. Đổi tên field public

Thay vì ngay lập tức:
- Bỏ name.
- Thêm displayName.
- Yêu cầu mọi consumer deploy cùng ngày.

Có thể:
1. Response tạm chứa cả name và displayName.
2. Thông báo deprecation và đo consumers còn dùng name.
3. Consumer chuyển dần sang displayName.
4. Sau compatibility window, công bố phiên bản API mới hoặc bỏ field cũ ở thời điểm phù hợp.

Khi field cũ và mới cùng tồn tại, phải xác định semantic tương đương và nguồn dữ liệu, không để chúng hiển thị giá trị khác nhau.

## 11. API versioning không phải câu trả lời duy nhất

Có thể version bằng:
- URL, ví dụ /v1/customers và /v2/customers.
- Header hoặc content negotiation.
- GraphQL schema với deprecation/field evolution.
- Consumer-specific BFF hoặc adapter.
- Contract theo feature capability.

Không nên tạo v2 cho mọi lần thêm một trường tùy chọn. Mục tiêu là tương thích thực tế và quản lý vòng đời hợp đồng. Version chỉ hữu ích khi:
- Có document hóa hành vi cũ/mới.
- Có ownership và kế hoạch ngừng hỗ trợ.
- Có metrics về usage.
- Có test cho phiên bản song song.
- Không dùng một code path chung vô tình làm thay đổi semantics của cả v1 và v2.

Một dịch vụ có thể giữ API v1 ổn định dù database schema đã trải qua nhiều migration.

## 12. Tính tương thích của event schema

Trong kiến trúc event-driven, producer phát các integration events; consumer xử lý sau, có thể đang chạy phiên bản cũ hoặc replay dữ liệu lịch sử. Event schema vì vậy có lifecycle khác với database schema.

Ví dụ event cũ:

~~~json
{
  "eventId":"evt-71",
  "eventType":"CustomerUpdated",
  "schemaVersion":1,
  "customerId":"c-42",
  "name":"Nguyen Van An"
}
~~~

Producer mới muốn chuyển sang:

~~~json
{
  "eventId":"evt-72",
  "eventType":"CustomerUpdated",
  "schemaVersion":2,
  "customerId":"c-42",
  "displayName":"Nguyen Van An",
  "locale":"vi-VN"
}
~~~

Nếu xóa name ngay, consumer v1 có thể lỗi hoặc mất thông tin. Một kế hoạch chuyển tiếp:
- Thêm displayName trong event schema mới theo chính sách tương thích.
- Trong thời gian migrate, có thể phát payload chứa cả hai fields hoặc hai event versions trên các channel được quy định.
- Consumer mới chấp nhận event cũ trong khoảng replay cần thiết.
- Đo tỷ lệ consumer v1 còn hoạt động.
- Chỉ ngừng field/event cũ sau khi contract của tất cả consumer cần thiết đã chuyển hoặc hết thời hạn đã công bố.

### 12.1. Đừng nhầm internal domain event với public integration event

Một domain event nội bộ có thể chứa object/domain types tiện dùng trong cùng một service. Integration event phải là hợp đồng ổn định hơn, không serialize trực tiếp ORM entity hoặc cấu trúc database.

Ví dụ:
- Nội bộ Customer: NamePartsChanged(firstName, lastName).
- Công khai: CustomerProfileUpdated(customerId, displayName, occurredAt).

Khi cách lưu tên đổi, consumer không cần biết các thành phần nội bộ.

### 12.2. Compatibility theo serialization format

JSON, Avro, Protobuf và các format khác có quy tắc tương thích khác nhau.

Ví dụ:
- Với JSON, không nên tự giả định consumer có thể bỏ qua unknown fields nếu parser strict.
- Với Protobuf, tránh tái sử dụng field number đã xóa cho ý nghĩa mới; quản lý reserved fields/numbers.
- Với Avro, thay đổi schema cần xem reader/writer compatibility và default values theo rules cụ thể.
- Với schema registry, thiết lập compatibility policy phải phù hợp producer/consumer rollout và replay horizon.

Đừng coi “registry báo compatible” là bằng chứng semantics nghiệp vụ tương thích. Schema registry thường kiểm tra cấu trúc; một trường đổi ý nghĩa kinh doanh có thể vẫn vượt qua kiểm tra kỹ thuật.

## 13. Thêm enum value cũng có thể phá consumer

Giả sử PaymentStatus ban đầu có:
- PENDING
- SUCCEEDED
- FAILED

Producer thêm REVIEW_REQUIRED, consumer cũ có switch chỉ xử lý ba giá trị và throw khi gặp giá trị khác.

Đây là breaking behavior dù field status vẫn là string. Các chiến lược:
- Contract công bố rằng enum có thể mở rộng và consumer phải xử lý UNKNOWN/fallback.
- Có default branch cho giá trị chưa biết khi nghiệp vụ cho phép.
- Không tự mapping trạng thái mới thành SUCCEEDED hoặc FAILED nếu gây hậu quả.
- Thêm schema version hoặc capability negotiation nếu consumer bắt buộc hiểu semantics mới.
- Rollout consumer trước khi producer bắt đầu phát enum mới.

Không phải mọi enum đều có thể coi là extensible. Với thanh toán hoặc quyền truy cập, giá trị chưa biết có thể cần fail-safe thay vì fallback tùy tiện.

## 14. Consumer-driven contract tests

Để phát hành độc lập, mỗi producer cần biết **consumer đang thực sự dựa vào phần nào của hợp đồng**. Không nên dựa vào cảm giác “chỉ thêm một field thôi”.

Consumer-driven contract testing cho phép:
1. Consumer mô tả request/response/event tối thiểu mà nó cần.
2. Provider verify các contract ấy ở pipeline của mình.
3. Hệ thống biết provider version mới có tương thích với consumer version đã triển khai hay không.
4. Phát hiện sớm thay đổi phá field, type hoặc status handling.

Ví dụ:
- Ordering cần customerId và displayName ở GET /customers/{id}.
- Billing cần customerId và billingAddress.
- Notification cần locale và preferredChannel.

Customer có thể đổi schema nội bộ không ảnh hưởng các contract; khi đổi public response, CI phải chạy các provider contract tests tương ứng.

### 14.1. Contract tests không thay integration tests

Contract tests kiểm tra shape và một phần semantics đã mô tả. Vẫn cần:
- Integration tests với database migration thật.
- Test các trạng thái v1/v2 coexist.
- Tests cho backfill và dữ liệu chưa chuyển đổi.
- Event compatibility/replay tests.
- End-to-end smoke tests cho flow trọng yếu.
- Performance/lock tests trên dữ liệu đủ đại diện.

Một API trả đúng field vẫn có thể gây bug nếu giá trị sai về nghiệp vụ hoặc latency tăng sau migration.

## 15. Transactional outbox giữ event và DB nhất quán cục bộ

Khi Customer Service cập nhật profile và cần thông báo cho Ordering qua event, có lỗi kinh điển:

~~~text
1. UPDATE customers ... thành công
2. COMMIT DB
3. Process crash trước khi publish CustomerUpdated
4. Consumer không bao giờ biết có thay đổi
~~~

Nếu publish trước DB commit, consumer có thể thấy một thay đổi chưa thực sự được lưu. Transactional outbox giải quyết khoảng trống bằng cách ghi thay đổi domain và record outbox trong cùng local DB transaction:

~~~sql
BEGIN;

UPDATE customers
SET first_name = :first_name,
    last_name = :last_name
WHERE id = :customer_id;

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, schema_version, payload
) VALUES (
    :event_id, :customer_id, 'CustomerProfileUpdated', 1, :payload
);

COMMIT;
~~~

Một relay/CDC đọc outbox và publish. Relay có thể phát lặp khi restart, nên consumers cần idempotent processing.

### 15.1. Outbox không thay versioning

Outbox đảm bảo intent phát event được lưu cùng local transaction; nó không chứng minh event schema mới tương thích. Khi Customer thay cấu trúc DB, adapter mapping sang integration event phải được giữ ổn định có chủ đích.

### 15.2. CDC trực tiếp trên bảng có thể rò rỉ schema nội bộ

Nếu Ordering tự subscribe vào raw CDC của bảng customers, việc đổi tên cột lại phá consumer. CDC nên được xem là cơ chế kỹ thuật thu thập thay đổi, không tự trở thành hợp đồng nghiệp vụ ổn định. Một layer mapping/contract hoặc outbox event rõ ràng giúp bảo vệ consumer khỏi biến động nội bộ.

## 16. Read model và dữ liệu sao chép không phải shared schema

Ordering có thể cần tên khách tại thời điểm đặt hàng. Gọi Customer cho mọi lần đọc đơn sẽ tạo coupling runtime và có thể làm lịch sử đơn thay đổi khi khách sửa tên.

Một thiết kế:

~~~text
Customer owns:
  CustomerProfile(customerId, currentDisplayName)

Ordering owns:
  Order(orderId, customerId, displayNameAtPurchase)
~~~

Ordering tạo snapshot khi tạo đơn. Customer vẫn sở hữu hồ sơ hiện tại, còn Ordering sở hữu cách hiển thị lịch sử đơn theo thời điểm mua.

Nếu cần projection của dữ liệu Customer để tìm kiếm:
- Ordering/Reporting có thể subscribe integration event được version.
- Từng consumer sở hữu bảng projection riêng.
- Event handler có idempotency và xử lý out-of-order theo contract.
- Projection có thể eventual consistent và có cơ chế rebuild/replay.

Một read model được tạo từ event **không có nghĩa consumer được quyền can thiệp schema nội bộ của producer**. Consumer có thể đổi schema projection của mình độc lập với producer.

## 17. Những thay đổi khó: split và merge bảng

Giả sử Order Service ban đầu có:

~~~text
orders(id, customer_id, address, payment_status, ...)
~~~

Đội phát triển muốn chuyển thông tin thanh toán nội bộ sang bảng order_payments hoặc một Payment Service riêng. Đây không chỉ là rename column; có thể đổi cả ownership, transaction boundary và logic truy vấn.

Một quá trình chuyển đổi:
1. Thiết kế owner mới và contract giữa các service.
2. Expand: thêm bảng/read model/adapter mới.
3. Bắt đầu ghi dữ liệu mới theo một đường có thứ tự và audit.
4. Backfill dữ liệu lịch sử theo batch/checkpoint.
5. Đối soát counts và business invariants.
6. Chuyển read path theo feature flag hoặc canary.
7. Quan sát tính đúng và latency.
8. Chuyển write ownership một cách có kiểm soát.
9. Loại bỏ đường cũ sau compatibility window.

Không nên mặc định **dual-write xuyên hai database** là atomic. Nếu cần giữ hai nơi đồng bộ, phải chọn mô hình nhất quán/eventual consistency, outbox, retry, idempotency và reconciliation rõ ràng.

### 17.1. Strangler pattern

Một endpoint cũ có thể tiếp tục hoạt động trong khi logic được chuyển dần sang service mới qua adapter/anti-corruption layer. Client cũ vẫn dùng contract quen thuộc; gateway/BFF/service adapter điều hướng sang triển khai mới theo quy tắc có kiểm soát.

Strangler giúp tách nhịp phát hành nhưng tăng thời gian vận hành hai đường. Cần migration completion criteria và kế hoạch dọn contract cũ.

## 18. Backfill an toàn: tránh ghi đè dữ liệu mới

Ví dụ có một triệu rows cần điền giá trị mới. Nếu worker đọc lúc 10:00, đến 10:05 mới UPDATE mà người dùng vừa sửa lúc 10:04, backfill có thể ghi đè dữ liệu mới.

Có thể bảo vệ bằng:
- Optimistic locking version.
- UPDATE ... WHERE version = :observed_version.
- UPDATE chỉ khi trường mới vẫn NULL và row thỏa điều kiện nguồn.
- Batch nhỏ có checkpoint và rate limit.
- Quản lý các row cần manual review.
- Đảm bảo transformation là idempotent.

Ví dụ:

~~~sql
UPDATE customers
SET new_normalized_name = :converted_value,
    version = version + 1
WHERE id = :id
  AND version = :observed_version
  AND new_normalized_name IS NULL;
~~~

SQL minh họa cần điều chỉnh theo engine/schema thật. Nếu updatedRows=0, worker không nên cứ ghi đè; nó có thể nạp lại state và quyết định có cần chạy lại.

### 18.1. Dữ liệu chưa migrate phải được xử lý tường minh

Trong giai đoạn chuyển tiếp, ứng dụng mới cần chịu được:
- Rows chưa có cột mới.
- Rows chứa giá trị không parse được.
- Values được tạo từ writer cũ.
- Dữ liệu có định dạng cũ trong cache hoặc message queue.
- Sự kiện lịch sử sẽ được replay sau này.

Đừng đổi NOT NULL trước khi chắc chắn **writer mới, writer cũ và backfill** đều đáp ứng constraint trong mọi thời điểm có thể xảy ra.

## 19. Rollout order: ai triển khai trước?

Với một thay đổi có nguy cơ phá consumer, nguyên tắc an toàn thường là **mở rộng khả năng chấp nhận trước, thay đổi hành vi phát sau**.

Ví dụ event schema:
1. Deploy consumer hỗ trợ cả format cũ lẫn mới.
2. Producer bắt đầu phát format mới khi đủ consumer đã sẵn sàng.
3. Quan sát lỗi, backlog và event replay.
4. Sau compatibility window, ngừng hỗ trợ format cũ theo kế hoạch.

Với database schema:
1. Expand database.
2. Deploy code có thể đọc/ghi cả schema cũ và mới.
3. Backfill.
4. Xác nhận không còn code cũ.
5. Contract.

Nhưng cần phân tích dựa vào từng contract: nếu producer mới chỉ thêm một field optional và consumer cũ thực sự bỏ qua unknown fields, có thể không cần release consumer trước. Không nên biến mọi thay đổi thành một đợt phối hợp lớn khi tính tương thích đã được chứng minh.

### 19.1. Không tạo chuỗi phụ thuộc phát hành dài

Anti-pattern:
- Team Customer mở pull request yêu cầu Billing, Ordering, Notification đổi parser.
- Phải merge/deploy toàn bộ vào một “release train”.
- Một team chậm làm tất cả team còn lại chờ.
- Khi sự cố, không biết rollback nhóm phiên bản nào.

Thiết kế tốt sử dụng compatibility window và contracts để các team có thể chuyển dần, không cần lockstep deployment.

## 20. Rollback khi schema đã thay đổi

Đây là lý do quan trọng nhất để chọn expand–migrate–contract. Rollback ứng dụng không đồng nghĩa rollback database an toàn.

Ví dụ:
- DB đã thêm cột: code cũ thường có thể tiếp tục chạy nếu cột optional.
- DB đã xóa cột: code cũ có thể lỗi ngay khi rollback.
- Đã chuyển type mất thông tin: rollback data có thể không phục hồi được giá trị ban đầu.
- New writer đã tạo dữ liệu mà old reader không hiểu: rollback ứng dụng có thể gây lỗi dù schema còn.

**Phương án ưu tiên:** forward-compatible schema và **roll forward** hoặc rollback ứng dụng trong khi schema expanded vẫn được giữ. Contract/drop nên làm ở đợt sau, khi rollback window của phiên bản cũ đã kết thúc.

Một rollback plan cần:
- Những app versions nào vẫn chạy được với schema hiện tại.
- Event/API versions nào producer đã phát.
- Dữ liệu mới có thể được code cũ đọc không.
- Có cần tắt feature flag trước khi rollback không.
- Nếu migration DDL thất bại giữa chừng, trạng thái DB là gì.
- Ai quyết định giữ expanded schema và tiếp tục khắc phục.

Không chạy down migration xóa dữ liệu production một cách tự động chỉ để “quay lại version cũ”. Một down migration có thể phá dữ liệu mới hoặc gây lock kéo dài.

## 21. Feature flags và traffic shifting

Feature flag có thể tách **triển khai code** khỏi **bật hành vi dùng schema mới**.

Ví dụ:
- Release v2 đã hỗ trợ đọc cả old và new.
- Flag newNameRead bật cho 1% user.
- Theo dõi số lỗi, độ trễ, tỷ lệ missing fields.
- Tăng 10%, 50%, 100% theo tiêu chí.
- Sau khi tất cả writer dùng format mới, mới contract.

Tuy nhiên feature flag **không thay thế DB migration**. Nếu schema chưa có cột mới, bật flag sẽ lỗi. Phải thiết kế ordering và guardrails. Flag quá lâu không dọn sẽ tạo code path phức tạp và phụ thuộc khó biết; cần owner và thời điểm cleanup.

### 21.1. Canary deployment

Một canary producer mới nên được kiểm thử với consumer versions đang chạy, đặc biệt với event phát rộng. Nếu canary phát event schema mới lên topic chung, một lượng nhỏ canary vẫn có thể khiến mọi consumer cũ nhìn thấy payload không tương thích.

Vì vậy traffic shifting ở producer không đủ bảo đảm an toàn cho event schema. Cần compatibility proof hoặc versioned event routing/feature gate rõ.

## 22. Chống coupling qua shared library

Một số tổ chức đưa JPA entities và DTO vào một thư viện Java chung:

~~~text
shared-model.jar
  CustomerEntity.java
  OrderEntity.java
  CustomerUpdatedEvent.java
~~~

Sau đó mọi service phụ thuộc cùng version. Điều này có thể tạo **distributed monolith ở tầng thư viện**: thay đổi entity hoặc field dẫn tới cần nâng version và deploy nhiều service.

Các lựa chọn tốt hơn:
- Service sở hữu domain model và entity nội bộ của mình.
- Công bố OpenAPI/AsyncAPI/Protobuf/Avro contract ổn định.
- Consumer sinh client/DTO theo contract nếu phù hợp.
- Chia sẻ những type rất ổn định, đơn giản khi có lý do rõ, nhưng không chia sẻ database entity.
- Dùng adapter/anti-corruption layer để bảo vệ bounded context.

Không nhất thiết cấm mọi shared library. Logging, tracing, authentication utilities có thể chia sẻ hợp lý. Vấn đề nằm ở shared model tạo dependency phát hành và chảy domain rules xuyên các service.

## 23. Schema registry và governance

Với event-driven systems, schema registry có thể giúp:
- Lưu và version schemas.
- Kiểm tra compatibility theo policy.
- Đảm bảo producer/consumer dùng schema đã đăng ký.
- Ngăn vô tình đổi field type hoặc required fields ngoài quy định.

Nhưng cần thêm governance:
- Ai là owner của event?
- Ai được quyền phát event?
- Có semantic version hoặc schema version nào?
- Cửa sổ consumer support và replay horizon là bao lâu?
- Khi xóa field, có phải xác nhận consumer usage không?
- Sự kiện nào chứa dữ liệu nhạy cảm hoặc bị giới hạn retention?
- Thay đổi ý nghĩa business được thông báo ra sao?

Một schema registry kỹ thuật không phát hiện tất cả semantic break. Ví dụ customerTier vẫn là string nhưng đổi từ “bronze/silver/gold” sang nhãn mới với quy tắc giảm giá khác có thể phá consumer dù type không đổi.

## 24. CI/CD kiểm soát contract và migration

Một pipeline của service sở hữu dữ liệu có thể chạy:

~~~text
Developer changes Customer Service
              |
              v
       Compile / Unit Tests
              |
              v
      Migration Test on DB
              |
              v
    Compatibility Check with
    old app + expanded schema
              |
              v
    Provider Contract Tests
              |
              v
      Event Schema Checks
              |
              v
     Integration / Replay Tests
              |
              v
     Deploy expand migration
              |
              v
       Canary application
              |
              v
      Observe and promote
~~~

Cần dữ liệu test đại diện:
- Database production cũ có NULL/legacy values.
- Dữ liệu khi nhiều version writer cùng chạy.
- Consumers đã triển khai và phiên bản còn được hỗ trợ.
- Messages/event lịch sử từ broker hoặc archive.
- Schema với row count lớn để đánh giá lock và duration.

### 24.1. Kiểm thử migration tiến và tương thích

Các test có giá trị:
1. Migrate database version N lên N+1 thành công.
2. Old app vẫn chạy trên DB expanded.
3. New app đọc được dữ liệu trước backfill.
4. Old writer và new reader cùng tồn tại.
5. Backfill chạy lại không thay đổi kết quả sai.
6. Một row bị update giữa backfill không bị ghi đè.
7. Migration chạy trên bảng lớn không vượt lock budget.
8. Rollback app được khi schema còn expanded.
9. Contract cũ vẫn được producer mới đáp ứng.
10. Event cũ replay qua consumer mới hợp lệ.

Không xem migration thành công trên database trống là bằng chứng production migration an toàn.

## 25. Quan sát khi chuyển schema

Những chỉ số nên có:

| Nhóm | Ví dụ |
| --- | --- |
| Data readiness | Số rows thiếu field mới, số rows chuyển đổi lỗi |
| Read path | Tỷ lệ fallback đọc field cũ, lỗi parse dữ liệu |
| Write path | Số writes còn sử dụng cột cũ, dual-write mismatch |
| Backfill | Rows/s, checkpoint, retries, lock wait |
| DB performance | p95 query latency, slow queries, replication lag |
| API compatibility | 4xx/5xx, contract failures, usage v1/v2 |
| Event compatibility | Deserialize errors, DLQ, schema versions in use |
| Rollout | Active app versions, traffic share, config/feature flags |
| Migration safety | DDL duration, locks, affected row count |
| Business correctness | Số lượng khách có tên hiển thị sai, đơn thiếu snapshot |

Không dùng metric label chứa ID riêng từng khách hoặc từng order vì cardinality cao và có thể gây lộ dữ liệu. Audit chi tiết nên nằm ở hệ thống phù hợp quyền truy cập và retention.

### 25.1. Dùng bằng chứng để quyết định contract

Một thời điểm loại bỏ cột cũ nên dựa trên:
- Không còn instance code cũ.
- Không còn cron job/query dùng tên cột cũ.
- Backfill hoàn tất theo điều kiện nghiệp vụ.
- Lỗi compatibility của consumer không xuất hiện trong cửa sổ quan sát phù hợp.
- Khả năng rollback đã được thay thế bằng release mới hơn.
- Đã xác nhận dependency ngoài như BI/reporting/CDC.

Không nên drop field chỉ vì “đã qua hai tuần” nếu vẫn có consumer và job cũ chưa được nhận diện.

## 26. Quy trình phối hợp giữa các đội mà vẫn giữ triển khai độc lập

Triển khai độc lập không có nghĩa không cần giao tiếp giữa các nhóm.

Producer/team sở hữu contract nên:
- Công bố đề xuất thay đổi và phạm vi tương thích.
- Giữ contract cũ trong compatibility window.
- Cung cấp tài liệu migration và ví dụ payload.
- Công bố deprecation timeline khi có breaking change.
- Có contract tests với consumer quan trọng.
- Quan sát usage trước khi contract.
- Có phương án xử lý consumer không thể nâng cấp đúng hạn.

Consumer/team sử dụng contract nên:
- Không đọc trực tiếp database của producer.
- Không phụ thuộc vào field ngoài contract.
- Xử lý unknown optional fields và enum evolution theo policy.
- Cập nhật contract tests khi thực sự cần semantics mới.
- Xây projection/adapter của mình nếu cần view riêng.
- Đánh giá replay và retention khi dùng event.

Sự phối hợp này là **phối hợp giao kèo**, không phải “mọi team phải deploy cùng ngày”.

## 27. Các sai lầm phổ biến

### “Mỗi service có database riêng nên luôn deploy độc lập”

Không hẳn. Nếu public API, event schema hoặc shared model vẫn thay đổi phá tương thích, consumer vẫn buộc deploy cùng thời điểm.

### “Cứ dùng Flyway là migration zero downtime”

Flyway version hóa migration; một lệnh DROP COLUMN có thể vẫn phá code cũ. Độ an toàn phụ thuộc trình tự triển khai, loại DDL, traffic và compatibility.

### “Rename column là thay đổi nội bộ nhỏ”

Chỉ đúng nếu không còn code cũ và không có consumer truy cập trực tiếp schema. Trong rolling rollout, rename trực tiếp thường là breaking.

### “Thêm NOT NULL một bước là vô hại”

Code cũ có thể không ghi trường mới và bị lỗi INSERT. Cần expand nullable/default theo contract, backfill và enforce sau.

### “Event schema compatible nghĩa là business semantics compatible”

Không đúng. Đổi đơn vị tiền, nghĩa trạng thái hoặc chính sách nghiệp vụ có thể phá consumer dù serializer chấp nhận format.

### “Consumer nào cần dữ liệu cứ query database chung”

Điều đó tạo coupling rất mạnh với schema và transaction. Nên dùng API, event hoặc projection có ownership rõ.

### “Dual-write hai database là một transaction”

Không đúng nếu không có distributed transaction thích hợp. Thực tế thường cần outbox, idempotency, reconciliation hoặc quy trình chuyển ownership rõ.

### “Đã backfill thì có thể drop cột cũ”

Chưa chắc vì writer cũ có thể vẫn tạo dữ liệu theo format cũ hoặc job batch còn dùng field cũ. Cần xác nhận consumer/writer usage.

### “Rollback code chỉ cần chạy down migration”

Có thể mất dữ liệu mới, phá constraint hoặc lock lớn. Expand schema thường được giữ khi rollback ứng dụng; contract nên là bước sau.

### “Thêm optional field chắc chắn an toàn”

Consumer strict parser hoặc semantics đặc thù có thể lỗi. Cần biết các consumer thực tế và kiểm thử.

### “Schema registry thay thế contract tests”

Registry chủ yếu kiểm tra cấu trúc và chính sách serializer; contract tests và integration tests vẫn cần để bảo vệ hành vi nghiệp vụ.

### “Một thư viện entities dùng chung giúp giảm coupling”

Nó có thể khiến mọi service phải nâng version đồng bộ. Chỉ chia sẻ contract phù hợp, không chia sẻ domain persistence model nội bộ.

## 28. Architecture Decision Record mẫu

~~~text
Title:
  Customer Service đổi dữ liệu tên từ một cột sang cấu trúc mới.

Context:
  Customer Service sở hữu profile, Ordering và Notification
  chỉ dùng API/event công khai.
  Có nhiều instance ứng dụng v1/v2 coexist khi rollout.

Decision:
  - Dùng expand-migrate-contract.
  - Expand schema bằng các trường mới nullable.
  - Bridge code hỗ trợ old/new trong compatibility window.
  - Backfill theo batch với checkpoint và optimistic locking.
  - Giữ API displayName và integration event contract ổn định.
  - Verify consumer contracts và event replay.
  - Chỉ drop cột cũ khi không còn old writers/readers.

Trade-offs:
  - Duy trì tạm thời hai dạng dữ liệu và logic chuyển tiếp.
  - Tăng công sức monitor/backfill.
  - Giảm rủi ro deploy lockstep và rollback failure.

Exit criteria:
  - New columns có dữ liệu hợp lệ theo policy.
  - No old app/job dependencies.
  - Consumer compatibility tests passing.
  - Rollback window đã được giải quyết.
  - Có kế hoạch contract migration và backup.

Owner:
  Customer Service team.
~~~

ADR không thay kế hoạch vận hành chi tiết; nó lưu bối cảnh, quyết định và tiêu chí kết thúc.

## 29. Checklist triển khai thay đổi schema độc lập

Trước khi sửa schema:
- [ ] Đã xác định service sở hữu bảng/dữ liệu?
- [ ] Các service khác có đang query bảng này trực tiếp không?
- [ ] Có đường API/event/read model bảo vệ consumer không?
- [ ] Đã phân loại thay đổi additive hay breaking?
- [ ] Có danh sách app versions, batch jobs và integrations phụ thuộc?
- [ ] Đã mô tả old/new coexistence và compatibility window?
- [ ] Có cách expand schema mà code cũ vẫn chạy?
- [ ] Có test old app trên expanded database?
- [ ] Có kế hoạch backfill dữ liệu lớn theo batch/checkpoint?
- [ ] Có cách bảo vệ concurrent writes và tránh dual-write mismatch?
- [ ] Có test API/event contract với consumers đang chạy?
- [ ] Event schema có version/replay compatibility đúng policy?
- [ ] Có kiểm tra DDL lock, disk và replication lag?
- [ ] Có feature flag, canary hoặc rollback path an toàn?
- [ ] Có metrics về old field usage và dữ liệu chưa migrate?
- [ ] Đã xác định điều kiện nào mới cho phép drop field cũ?
- [ ] Có owner cho migration, monitoring và sự cố?
- [ ] Kế hoạch có cho phép teams triển khai khác thời điểm?

## 30. Bài tập tình huống

### Bài 1 — Đổi cột tên khách hàng

Customer Service đổi customer_name thành full_name. Ordering vẫn gọi API GET /customers/{id} để nhận displayName, không có quyền truy cập DB.

**Câu hỏi:** Ordering có cần phát hành khi Customer đổi cột không?

**Gợi ý:** Không, nếu API contract và semantics displayName vẫn được bảo đảm. Customer cần expand-migrate-contract trong DB của mình vì code cũ/mới có thể coexist.

### Bài 2 — Consumer đọc bảng trực tiếp

Billing chạy SQL JOIN vào bảng customers của Customer. Customer muốn tách bảng thành customer_profiles và customer_addresses.

**Câu hỏi:** Tại sao khó phát hành độc lập?

**Gợi ý:** Billing bị kết dính vào schema nội bộ. Thiết kế API/event/projection ổn định, đưa Billing khỏi quyền đọc trực tiếp rồi mới làm breaking schema migration.

### Bài 3 — Thêm NOT NULL không có default

Customer thêm cột preferred_language NOT NULL; v1 INSERT không ghi cột đó.

**Câu hỏi:** Điều gì xảy ra và trình tự nên thay ra sao?

**Gợi ý:** INSERT của v1 có thể lỗi. Expand nullable hoặc default có semantics phù hợp; deploy writer mới, backfill, verify, enforce constraint ở bước sau.

### Bài 4 — Event thêm enum status

Payments phát PaymentStatus mới REVIEW_REQUIRED. Consumer v1 chỉ có switch trên PENDING, SUCCEEDED, FAILED và throw khi gặp giá trị lạ.

**Câu hỏi:** Thêm enum value có phải luôn tương thích?

**Gợi ý:** Không. Cần contract về enum extensibility hoặc rollout consumer hỗ trợ trước khi producer phát value mới.

### Bài 5 — Backfill đè lên dữ liệu mới

Một worker đọc profile vào 10:00, user sửa lúc 10:01, worker UPDATE lúc 10:02.

**Câu hỏi:** Ngăn mất dữ liệu bằng cách nào?

**Gợi ý:** Optimistic locking/version, conditional UPDATE, checkpoint và retry có kiểm soát.

### Bài 6 — Cần rollback code

Customer v2 gặp lỗi nên phải rollback về v1, nhưng migration đã DROP customer_name.

**Câu hỏi:** Vì sao rollback khó và thiết kế nào nên dùng?

**Gợi ý:** V1 không còn cột cần đọc. Giữ schema expanded trong rollback window; contract/drop cột ở release muộn hơn.

### Bài 7 — Thêm field vào API

Producer thêm field locale. Một consumer Java dùng Jackson strict unknown-property mode và bắt đầu throw.

**Câu hỏi:** Vì sao “additive” vẫn có thể phá consumer?

**Gợi ý:** Parser và behavior thực tế quyết định. Cần provider contract tests hoặc policy ignore unknown fields được thống nhất.

### Bài 8 — CDC làm lộ database

Analytics subscribe raw CDC của bảng customers và dựa vào tên cột customer_name. Customer muốn rename column.

**Câu hỏi:** Dùng CDC có giúp tách coupling chưa?

**Gợi ý:** Chưa, vì raw table CDC làm lộ schema nội bộ. Cần mapping sang integration event hoặc data product có contract và version.

## 31. Kết luận

**Quyền sở hữu dữ liệu** là nền tảng cho khả năng tiến hóa schema độc lập trong Microservices. Nếu một service thực sự sở hữu database/schema nội bộ và các service khác chỉ tiêu thụ **API hoặc event contract ổn định**, thay đổi bảng/cột không buộc mọi service phải phát hành cùng thời điểm.

Đối với những thay đổi phá tương thích, chiến lược **expand → migrate → contract** cho phép code cũ và code mới cùng hoạt động trong một cửa sổ chuyển tiếp: thêm cấu trúc mới trước, chuyển read/write và backfill có kiểm soát, cuối cùng mới xóa cấu trúc cũ. Cần kết hợp với **contract tests, event schema governance, idempotent backfill, monitoring và rollback plan**.

Nguyên tắc thực hành: **dịch vụ sở hữu dữ liệu được quyền thay đổi cách lưu trữ, miễn nó giữ lời hứa với các consumer trong khoảng tương thích đã công bố; hãy thay đổi hợp đồng theo từng bước có thể triển khai độc lập, không dùng một đợt phát hành đồng loạt để che giấu coupling.**
