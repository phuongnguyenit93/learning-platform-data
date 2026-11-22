# Danh sách tiêu chí để chấp nhận một mô hình trước khi triển khai

Một nhóm đã hoàn thành sơ đồ ERD, bảng từ điển dữ liệu và vài câu SQL tạo bảng. Các đường nối trông hợp lý, tên cột nhất quán, mọi bảng đều có khóa chính. Có thể bắt đầu triển khai chưa?

**Chưa chắc.** Mô hình có thể vẫn cho phép một đơn hàng của tenant A tham chiếu khách hàng tenant B, ghi nhận doanh thu hai lần khi trả hàng, hoặc vượt số lượng tồn kho khi hai yêu cầu chạy đồng thời. Một cột có kiểu BIGINT có thể chứa giá trị tiền đúng cú pháp nhưng sai đơn vị. Một FK có thể đúng nhưng câu JOIN dùng cho dashboard làm nhân số hàng. Một mô hình document có thể rất nhanh ở bộ dữ liệu thử nhưng không chịu nổi khi document/series tăng gấp nhiều lần.

Vì vậy, **chấp nhận một mô hình trước khi triển khai** không phải việc “đồng ý với hình vẽ”. Đó là một quyết định có bằng chứng rằng mô hình đủ rõ về **nghiệp vụ, grain, định danh, quan hệ, ràng buộc, vòng đời, quyền truy cập, hiệu năng, thay đổi dữ liệu và khả năng vận hành** để nhóm phát triển có thể triển khai mà không phải tự suy đoán những điều quan trọng.

Bài này thuộc chương **Kiểm chứng thiết kế** của module **DATABASE_DATA_MODELING**. Mục tiêu là xây dựng **danh sách tiêu chí nghiệm thu (acceptance checklist)**, gắn từng tiêu chí với cách đo và bằng chứng, đồng thời so sánh yêu cầu nghiệm thu trong mô hình quan hệ, document, đồ thị và phân tích. Ví dụ SQL dùng PostgreSQL để minh họa việc biến quy tắc nghiệp vụ thành điều kiện có thể kiểm chứng.

> **Nguyên tắc:** Không chấp nhận mô hình vì “đã có ERD, đã có PK và chạy thử không lỗi”. Chỉ chấp nhận khi các **bất biến bắt buộc đã có cơ chế bảo vệ khả thi**, các lựa chọn chưa rõ được ghi nhận, và các rủi ro còn lại có người chịu trách nhiệm và tiêu chí xử lý cụ thể.

## 1. Chấp nhận thiết kế nghĩa là chấp nhận điều gì?

Cần phân biệt ba thời điểm:

| Thời điểm | Điều có thể kết luận | Điều chưa thể kết luận |
| --- | --- | --- |
| **Review thiết kế trước triển khai** | Mô hình có hợp đồng nghiệp vụ, cơ chế bảo vệ dự kiến, prototype/test plan đủ tin cậy | Hệ production chắc chắn đúng và đủ nhanh |
| **Kiểm thử sau triển khai trong môi trường đại diện** | DDL, truy vấn, migration và concurrency có hoạt động theo kế hoạch | Tải/môi trường production không bao giờ có bất thường |
| **Nghiệm thu vận hành sau phát hành** | SLO, chất lượng dữ liệu và giám sát thực tế đang đạt | Thiết kế không bao giờ cần tiến hóa |

Ở bước **trước triển khai**, bằng chứng có thể là yêu cầu nghiệp vụ được xác nhận, ERD và data dictionary, DDL prototype, tập dữ liệu mẫu, kết quả kiểm thử trên prototype, kế hoạch migration, ước lượng dung lượng hoặc kết quả thử tải ở quy mô đại diện nếu đã có. Không được báo “đã đạt SLA production” khi mới ước lượng bằng spreadsheet.

Một hồ sơ nghiệm thu tối thiểu phải trả lời:

1. **Mô hình dùng cho việc gì?** Phạm vi phiên bản đầu tiên, use case nằm ngoài phạm vi.
2. **Một hàng/document/node/edge đại diện điều gì?** Grain và lifetime.
3. **Khóa nào là danh tính?** Phạm vi duy nhất theo tenant/source/time và chính sách thay đổi.
4. **Bất biến nào phải đúng?** Cách thực thi và kiểm chứng từng bất biến.
5. **Hành vi khi dữ liệu thay đổi, đến muộn hoặc bị xóa?**
6. **Ai sẽ đọc/ghi, với tải, độ trễ và quyền hạn nào?**
7. **Hệ thống làm gì khi ghi trùng, có cạnh tranh và phụ thuộc thất bại?**
8. **Có thể chuyển dữ liệu cũ và quay lui/khôi phục không?**
9. **Phải có bằng chứng nào trước khi phát hành? Ai ký chấp nhận?**

### 1.1. Đầu ra của review phải có thể hành động

Một kết luận tốt không phải “Schema ổn” mà là:

~~~text
Decision: CONDITIONAL GO

Accepted scope:
  SalesOrder, OrderLine, Customer trong tenant;
  doanh thu dòng bán trước thuế.

Required before migration:
  - Xác nhận cách xử lý guest checkout.
  - Kiểm tra Order CONFIRMED luôn có ít nhất một Line.
  - Bổ sung index cho truy vấn Order theo customer và created_at.
  - Chạy thử race confirm/delete-last-line bằng hai session.

Evidence:
  Model version v1.4
  SQL prototype revision r17
  Test cases VAL-001..VAL-020

Owner:
  Domain owner, DBA, security reviewer, lead ứng dụng

Expiry:
  Phải review lại khi thêm guest checkout hoặc shard theo customer.
~~~

**CONDITIONAL GO** chỉ phù hợp khi các điều kiện chưa hoàn tất **không cho phép hành động rủi ro xảy ra trước khi chúng được đóng**. Nếu invariant bắt buộc chưa được bảo vệ mà nhóm vẫn định mở traffic ghi thật, đó phải là **NO-GO**, không thể gọi là “điều kiện nhỏ”.

## 2. Phân loại tiêu chí: bắt buộc, có điều kiện và tối ưu

Không phải mọi tiêu chí có cùng hậu quả khi thất bại.

| Mức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **P0 — cổng chặn** | Nếu không đạt thì không triển khai phạm vi liên quan | Vi phạm phân tách tenant, sai định danh giao dịch, không bảo vệ double-spend |
| **P1 — bắt buộc trước phát hành** | Có kế hoạch xử lý và chứng cứ đạt trước traffic thật | FK chưa validate, backfill còn ngoại lệ chưa xử lý, chưa thử rollback |
| **P2 — tối ưu có chủ sở hữu** | Có thể chấp nhận có điều kiện nếu rủi ro được đo và SLA vẫn đạt | Thêm materialized view, tinh chỉnh clustering, cải thiện tên index |
| **N/A có lý do** | Không áp dụng cho phạm vi mô hình | Không có dữ liệu cá nhân nên một số bước PII cụ thể N/A |

Mức ưu tiên phải xuất phát từ **nghĩa vụ nghiệp vụ và tác động**, không cố định máy móc. Chẳng hạn một index chưa tối ưu có thể thành P0 nếu latency là điều kiện an toàn của quy trình bắt buộc. Một vấn đề dữ liệu cá nhân không thể hạ xuống P2 chỉ vì nhóm chưa có thời gian.

### 2.1. Quy tắc quyết định Go / No-Go

Có thể dùng chính sách:

- **GO:** mọi P0/P1 liên quan đạt bằng chứng; các P2 còn lại được ghi rủi ro, owner và mốc xử lý.
- **CONDITIONAL GO:** phạm vi được thu hẹp hoặc rollout bị khóa sau điều kiện chấp nhận rõ; chưa phát hành phần cần tiêu chí chưa đạt.
- **NO-GO:** bất kỳ P0 chưa đạt; P1 chưa đạt mà chưa có cơ chế hạn chế rủi ro được phê duyệt; bằng chứng thiếu hoặc trái ngược.

Không dùng một **điểm trung bình** để bù rủi ro P0. Mô hình đạt 95/100 điểm nhưng cho phép một tenant đọc dữ liệu tenant khác vẫn **không đạt**.

## 3. Bộ hiện vật phải có trước cuộc review

| Hiện vật | Nội dung tối thiểu | Người xác nhận |
| --- | --- | --- |
| **Problem statement / scope** | User journeys, quyết định nghiệp vụ, out-of-scope | Domain/Product Owner |
| **Glossary / domain definitions** | Order, Line, Reservation, Payment, Refund, Customer, thời điểm | Business Analyst/Domain |
| **Conceptual model** | Thực thể, quan hệ và vai trò | Domain + Architect |
| **Logical model** | Grain, khóa, bội số, ràng buộc, lifecycle, version | Data Modeler |
| **Physical design proposal** | DDL/index/partition, query patterns, isolation, sizing | DBA/Data Engineer |
| **Data dictionary** | Nghĩa, kiểu, đơn vị, NULL, owner, nguồn, classification | Data Steward |
| **Invariant catalog** | Quy tắc, phạm vi, enforcement, test và severity | Domain + Engineering |
| **Workload/access matrix** | Ai đọc/ghi gì, tần suất, SLO, cardinality | Application + SRE |
| **Migration/rollout plan** | Expand/backfill/validate/contract, downtime, rollback | DBA + Release Owner |
| **Security/data lifecycle** | Tenant isolation, PII, roles, retention, deletion | Security/Privacy |
| **Verification pack** | Test dương/âm, query đối soát, fixture, acceptance report | QA/Data Engineering |
| **Decision log** | Lựa chọn, đánh đổi, điều kiện, giả định và người phê duyệt | Review Board |

Không nhất thiết phải có mười hai tệp riêng. Một tài liệu có version và nhiều bảng có thể chứa các hiện vật, miễn là **dễ truy vết** từ yêu cầu đến thiết kế, kiểm tra và người chịu trách nhiệm.

### 3.1. Traceability: một yêu cầu phải đi tới bằng chứng

Ví dụ:

~~~text
REQ-12:
  Không bán số lượng vượt tồn khả dụng của một kho/SKU.

Model:
  StockBalance(tenant, warehouse, sku, on_hand, reserved).

Invariant:
  0 <= reserved <= on_hand.

Write protocol:
  Atomic conditional UPDATE trong cùng transaction
  với idempotent Reservation.

Tests:
  VAL-12A: reserve hợp lệ thành công.
  VAL-12B: reserve vượt tồn bị từ chối.
  VAL-12C: hai request tranh hai chiếc cuối.
  VAL-12D: retry operation_id không giữ thêm.

Evidence:
  DDL, stored procedure/contract, kết quả race test,
  query đối soát Balance vs active Reservation.

Status:
  PASS / FAIL / NOT RUN / N/A cùng lý do.
~~~

Nếu một yêu cầu không có vị trí trong mô hình hoặc cách kiểm chứng, đó là **lỗ hổng thiết kế**, ngay cả khi ERD hoàn chỉnh.

## 4. Gate A — Hiểu đúng nghiệp vụ và giới hạn phạm vi

Review phải bắt đầu bằng **kịch bản sử dụng thực tế**, không mở IDE ngay.

### 4.1. Những câu hỏi nghiệm thu bắt buộc

- Có định nghĩa rõ các từ dễ nhầm như **đơn hàng, giao dịch, đặt chỗ, thanh toán, doanh thu, hoàn tiền, tồn kho** không?
- Có phân biệt **đối tượng nghiệp vụ** và **sự kiện xảy ra với đối tượng** không?
- Mỗi trạng thái và transition có nghĩa rõ, không dùng một cột status chứa đồng thời trạng thái giao hàng và thanh toán?
- Có xác định **tenant, vùng, nguồn dữ liệu và quyền sở hữu** không?
- Có chỉ ra nghiệp vụ nào **không hỗ trợ ở v1** và cách tránh lưu dữ liệu ngụy tạo cho nghiệp vụ ấy?
- Những trường hợp biên như guest checkout, split shipment, trả hàng một phần, đổi tiền tệ, ID đến muộn có được quyết định không?
- Có người chịu trách nhiệm **duyệt các quy tắc** trước khi developer triển khai không?

### 4.2. Ví dụ: “Mỗi Order có một Customer” chưa đủ

Nếu business hỗ trợ mua không đăng nhập, phát biểu trên có thể sai. Có ít nhất ba mô hình khác nhau:

1. Mọi Order tham chiếu Customer đã đăng ký: FK NOT NULL, guest checkout **ngoài phạm vi**.
2. Order có thể là guest: customer_id nullable **với discriminator** và guest contact snapshot hợp lệ.
3. Guest là một kiểu Customer nghiệp vụ đặc biệt: cần giải thích identity, privacy và vòng đời, tránh tạo một Customer giả duy nhất cho mọi guest.

Chỉ chọn một phương án sau khi xác định **bội số và nghĩa của NULL**. Không gắn Customer “Unknown” cho tất cả guest chỉ để FK hợp lệ nếu làm mất khả năng phân biệt khách, gây sai đối soát hoặc vi phạm quy tắc truy cập.

### 4.3. Cổng chặn của Gate A

**NO-GO** khi hai stakeholder còn hiểu khác nhau về một fact/thuộc tính ảnh hưởng tiền hoặc quyền; hoặc một trường quan trọng thiếu định nghĩa đơn vị và thời điểm. “Giải quyết trong lúc coding” không phải bằng chứng chấp nhận.

## 5. Gate B — Grain và danh tính của từng đối tượng

### 5.1. Phải viết đúng một câu grain cho từng bảng

Ví dụ:

| Thành phần | Grain một hàng | Không được nhầm |
| --- | --- | --- |
| Customer | Một danh tính khách trong một tenant | Một email không luôn là một người |
| SalesOrder | Một Order trong tenant | Một lần thanh toán không phải Order |
| OrderLine | Một dòng hàng trong một Order | Cùng SKU có thể xuất hiện trên hai Line hợp lệ |
| PaymentAttempt | Một lần yêu cầu thanh toán có ID nguồn ổn định | Retry cùng attempt không phải attempt mới |
| StockBalance | Một SKU tại một warehouse và tenant | Không phải tổng các warehouse |
| StockReservation | Một thao tác giữ hàng được chấp nhận | Không phải số tồn hiện tại |
| FactSalesLine | Một dòng bán theo định nghĩa báo cáo | Không phải một Event chỉnh sửa/Refund |
| FactInventoryDaily | Một snapshot sản phẩm–kho–ngày | Không được SUM qua ngày như transaction |

### 5.2. Kiểm tra khóa và phạm vi uniqueness

Mỗi thực thể phải có:

- **Candidate/business key:** vì sao tổ hợp đó duy nhất trong domain?
- **Primary key hoặc định danh vật lý:** có ổn định qua toàn vòng đời không?
- **Surrogate vs natural key:** sự lựa chọn có làm mất UNIQUE nghiệp vụ không?
- **Scope:** global, tenant, source_system, warehouse, order hay khoảng thời gian?
- **Mutation policy:** khóa có được đổi, tái sử dụng hay merge/split không?
- **Retry identity:** nguồn có event_id/operation_id ổn định để chống ingest trùng không?

Ví dụ:

~~~text
SalesOrder:
  PK: (tenant_id, order_id)
  AK: (tenant_id, order_code)

OrderLine:
  PK: (tenant_id, order_id, line_no)

PaymentAttempt:
  PK: (tenant_id, payment_attempt_id)
  AK: (tenant_id, provider_code, provider_attempt_ref)

StockReservation:
  AK: (tenant_id, operation_id)
~~~

Nếu Order ID có thể trùng giữa tenant, **FK chỉ dùng order_id là thiếu**. Nếu provider attempt reference chỉ duy nhất trong provider+tenant, UNIQUE(provider_attempt_ref) toàn hệ là quá chặt.

### 5.3. Tests chứng minh grain

- Một Order có hai Line cùng SKU với giá/khuyến mãi khác nhau: hai Line hợp lệ không bị hợp nhất.
- Cùng provider attempt được retry nhiều lần: không tạo thêm PaymentAttempt có hiệu ứng tài chính.
- Hai tenant có cùng order_code: được phép nếu uniqueness per-tenant.
- Cùng tenant/order_code: lần thứ hai bị từ chối, ngay cả khi hai request cùng chạy.
- Snapshot tồn kho được sửa thành version mới: không trở thành một “delta cộng thêm”.

**NO-GO** nếu không trả lời được một hàng đại diện điều gì hoặc có thể có hai hàng cùng danh tính nghiệp vụ mà không có cơ chế giải quyết.

## 6. Gate C — Quan hệ, bội số và tính toàn vẹn tham chiếu

Một ERD phải được kiểm chứng cả hai đầu.

| Quan hệ | Từ phía con tới cha | Từ phía cha tới con | Quy tắc đặc biệt |
| --- | --- | --- | --- |
| Order → Customer | 1..1 theo phạm vi registered | 0..N Order | Cùng tenant |
| OrderLine → Order | 1..1 | 0..N khi DRAFT | CONFIRMED phải 1..N |
| OrderLine → Product | 1..1 | 0..N Line | Product inactive vẫn giữ lịch sử |
| PaymentAttempt → Order | 1..1 | 0..N Attempt | Attempt có lifecycle riêng |
| Order ↔ Label | 0..N | 0..N | Cần bảng liên kết có khóa |
| Category → parent Category | 0..1 parent | 0..N child | Nếu là cây, phải cấm chu trình dài |

### 6.1. Các điều kiện phải được ghi

- Bội số min/max có phụ thuộc **trạng thái** hay **thời điểm hiệu lực** không?
- FK có gồm tenant_id và phạm vi source khi cần không?
- Quan hệ optional có dùng NULL hợp nghĩa, hay cần discriminator và trạng thái chờ?
- Một M:N có thuộc tính riêng (role, quantity, valid_from) cần entity liên kết không?
- Quan hệ lịch sử có được phép chồng lấp khoảng hiệu lực không?
- Khi parent archive/delete, child được giữ, bỏ liên kết hay xóa theo?
- Nếu reference xuyên service, đâu là owner/protocol kiểm chứng và xử lý orphan?

### 6.2. Trường hợp không thể bảo vệ chỉ bằng FK

Một OrderLine có FK tới Order không chứng minh **Order CONFIRMED có ít nhất một Line**. Trong PostgreSQL, FK con → cha bảo vệ con có cha, không tạo “minimum child count”.

Nếu invariant bắt buộc ở thời điểm xác nhận, cần **Order Owner** kiểm tra số Line, khóa Order và bảo đảm mọi lệnh xóa/sửa Line tuân theo cùng quy tắc. Nếu dữ liệu nằm ở hai database độc lập, cần thiết kế lại boundary hoặc protocol có bảo đảm phù hợp.

**NO-GO** khi tài liệu chỉ mô tả “có FK” nhưng quy tắc thật là **xuyên nhiều hàng, nhiều shard hoặc nhiều trạng thái** mà chưa có cách cưỡng chế.

## 7. Gate D — Ràng buộc, dữ liệu thiếu và ngữ nghĩa thuộc tính

### 7.1. Mỗi thuộc tính phải có hợp đồng

Ví dụ về tiền:

~~~text
Attribute: unit_price_vnd
Type: BIGINT
Unit: VND nguyên đồng
Nullability: NOT NULL
Valid range: >= 0 trong nghiệp vụ minh họa
Source: giá được chốt khi tạo OrderLine
Lifecycle: không sửa trực tiếp sau CONFIRMED
History: giữ giá đã bán, không lấy giá Product hiện hành
Verification: insert âm thất bại; đối soát line total
~~~

Kiểu BIGINT không tự nói đó là **VND hay USD**, giá trước hay sau thuế, số tiền có được âm hoặc làm tròn thế nào. Việc đặt hậu tố _vnd chỉ có ý nghĩa nếu mọi writer đảm bảo đơn vị.

### 7.2. CHECK, NOT NULL, FK và UNIQUE có bảo vệ đúng mức không?

- **NOT NULL:** giá trị có bắt buộc ở mọi trạng thái của đối tượng không?
- **CHECK:** biểu thức có vô tình cho qua NULL theo logic ba trị không?
- **FK:** có chọn đúng khóa cha, đúng tenant và chính sách xóa không?
- **UNIQUE:** có đúng scope, quy tắc NULL, chuẩn hóa mã và bản ghi archive không?
- **DEFAULT:** có phản ánh sự thật nghiệp vụ hay chỉ đang che dữ liệu thiếu?
- **Domain enum/status:** tập giá trị đã đủ? Các transition có được bảo vệ bên ngoài CHECK không?

Ví dụ CHECK(quantity > 0) không tự cấm quantity = NULL nếu không có NOT NULL. UNIQUE(tenant_id,external_reference) thông thường cho phép nhiều NULL ở external_reference trong PostgreSQL; nếu reference bắt buộc phải có, cần quy tắc riêng.

### 7.3. Dữ liệu thiếu khác số 0

- Không có một lần đo nhiệt độ ≠ nhiệt độ 0 °C.
- Không có giá bán ≠ giá bán 0 VND.
- Không biết Product ≠ Product “Unknown” là một sản phẩm thực.
- Chưa nhận xác nhận Payment ≠ Payment FAILED.
- Không có snapshot tồn kho ≠ còn 0 chiếc.

**NO-GO** nếu data dictionary chưa phân biệt **unknown, not applicable, missing, invalid và zero hợp lệ** cho thuộc tính ảnh hưởng báo cáo hoặc quyết định.

## 8. Gate E — Lịch sử, thời gian và vòng đời

Một mô hình được chấp nhận phải nêu rõ **cái gì được phép thay đổi** và **điều gì phải giữ lịch sử**.

### 8.1. Phân biệt các trục thời gian

| Mốc | Ý nghĩa | Truy vấn mẫu |
| --- | --- | --- |
| event_time / occurred_at | Lúc sự kiện xảy ra | Bán ngày nào? |
| valid_from / valid_to | Khoảng một giá trị/quan hệ có hiệu lực | Product thuộc Category nào khi bán? |
| posting_date | Kỳ được ghi nhận/hạch toán | Khoản chỉnh sửa ghi sổ kỳ nào? |
| received_at / loaded_at | Lúc hệ nhận được bản tin | Đến hôm qua hệ đã biết gì? |
| calculation_version | Phiên bản công thức tổng hợp | KPI lần công bố này tính theo quy tắc nào? |

Nếu Product đổi Category, báo cáo **as-sold** có thể cần SCD2 hoặc snapshot. Nếu fact đến muộn, không được tự gán chiều hiện hành theo ngày nạp rồi coi đó là danh mục lúc giao dịch.

### 8.2. Lifecycle và xóa

Với Customer/Product/Order/PaymentAttempt phải nêu:

- Có hard delete không, hay chỉ archived/soft delete?
- Khi parent bị xóa, child có bị CASCADE, SET NULL, RESTRICT không?
- Có dữ liệu cá nhân cần ẩn danh hoặc xóa theo chính sách không?
- Kho lưu lịch sử, bản sao tìm kiếm, analytics và backup xử lý thế nào?
- Có lưu trạng thái trước/sau và lý do correction không?
- Có cần replay từ event log hoặc as-known-at report không?

Không tự bật ON DELETE CASCADE cho Customer có Order cần lưu chứng từ. Ngược lại, không tự giữ PII vô thời hạn chỉ vì FK RESTRICT. Hai yêu cầu **toàn vẹn lịch sử** và **quản trị dữ liệu cá nhân** phải được giải quyết cùng nhau.

### 8.3. Snapshot và event không được cộng như nhau

Một hàng FactInventoryDaily chứa **tồn cuối ngày 20 chiếc** và bản revision sau là **18 chiếc**: không được SUM thành 38. Một FactSalesMovement chứa +200.000, -20.000 adjustment và -180.000 reversal: có thể SUM delta thành 0 nếu cùng scope và measure phù hợp.

**NO-GO** nếu grain và quy tắc aggregate chưa phân biệt transactional event, periodic snapshot, accumulating snapshot, revision và dimension version.

## 9. Gate F — Khả năng ghi đúng khi có cạnh tranh và hệ phân tán

Một schema có thể đúng trong quá trình test tuần tự nhưng sai khi nhiều request đồng thời.

### 9.1. Hai request cùng sử dụng nguồn lực còn lại

Giả sử StockBalance của một SKU có on_hand = 10, reserved = 8. Hai request cùng muốn giữ 2 chiếc. Nếu cả hai đọc “còn 2” từ cache/replica rồi chấp nhận độc lập, kết quả có thể oversell.

Đường ghi an toàn cần:

1. Owner xác định theo **tenant, warehouse, sku**.
2. Một điều kiện atomic trên balance hiện hành, chẳng hạn reserved + quantity <= on_hand.
3. Reservation được ghi cùng transaction với cập nhật balance, hoặc protocol bảo vệ invariant tương đương.
4. Idempotency key không tạo thêm một lần giữ hàng khi retry.
5. Release/consume thay đổi trạng thái đúng một lần, có đối soát.
6. Không có writer khác được bypass owner.

Một query dashboard chỉ đọc available_stock không thể thay thế quyết định nguyên tử của Stock Owner.

### 9.2. Chỗ nào cần test concurrency?

| Tình huống | Điều muốn chứng minh |
| --- | --- |
| Hai INSERT cùng business key | Chỉ một hàng hợp lệ được commit |
| Hai ReserveStock cùng sử dụng số còn lại | Không vượt tồn; retry không giữ thêm |
| ConfirmOrder cùng DeleteLastLine | Không có CONFIRMED thiếu Line |
| Hai RedeemVoucher cùng code | Không đổi voucher hai lần |
| PaymentAttempt được gửi lại | Không capture/ghi nhận hai lần |
| Hai update SCD2 gần nhau | Không tạo khoảng hiệu lực chồng lấp |
| Shard cutover có client dùng route cũ | Không có hai owner cùng commit |
| Worker fail sau DB commit nhưng trước khi ACK | Replay không nhân hiệu ứng |

Chọn isolation level không đủ nếu không mô phỏng lịch cạnh tranh thực. PostgreSQL SERIALIZABLE trong **một database** không chứng minh hai database độc lập có thể cùng duy trì invariant toàn cục.

### 9.3. Transaction, Saga và giới hạn bảo đảm

Một lệnh checkout chạm Stock, Payment và Order ở ba service không mặc nhiên có all-or-nothing. Nếu dùng Saga, phải mô tả **trạng thái trung gian, bù trừ idempotent, timeout, unknown outcome** và khi nào Order được coi là CONFIRMED.

Nếu nghiệp vụ không cho phép sai lệch tạm thời và hành động không thể bù, cần transaction/coordination mạnh hơn hoặc thay lại ranh giới. Không chấp nhận mô hình bằng khẩu hiệu “eventual consistency” khi chính bất biến phải đúng ngay lúc trả thành công.

**NO-GO** nếu một invariant bắt buộc có thể bị phá bởi hai request hợp lệ chạy đồng thời mà không có owner, transaction hoặc protocol được chỉ ra.

## 10. Gate G — Mô hình truy cập, chỉ mục và khả năng mở rộng

Thiết kế vật lý phải bắt đầu từ **các truy vấn quan trọng**.

### 10.1. Workload matrix trước khi tạo index

| Đường truy cập | Filter/join/group dự kiến | Hành vi mong muốn | Chứng cứ cần |
| --- | --- | --- | --- |
| Tra Order của khách | tenant_id, customer_id, created_at DESC | Phân trang ổn định | Index đề xuất + plan |
| Tra một Order và các Line | tenant_id, order_id | Số ít hàng, đúng tenant | PK/FK + EXPLAIN |
| Đối soát doanh thu ngày | Ngày nghiệp vụ, Product/Store | Tổng đúng, tải lớn có thể vào mart | Grain/KPI test + plan |
| Xử lý Payment callback | tenant, provider, provider_attempt_ref | Idempotent lookup | Unique key và race test |
| Query lịch sử Product | product code + event time | Đúng SCD version | Kiểm tra overlap/gap |
| Dữ liệu time series | series_id, observed_at range | Range scan/partition pruning | Dữ liệu mẫu tỷ lệ thực |
| Xóa dữ liệu hết retention | tenant/time window | Không gây khóa dài vượt SLO | Retention/partition plan |

### 10.2. Chỉ mục nào cần, và tại sao?

Index B-tree theo (tenant_id, customer_id, created_at DESC) có thể phục vụ tìm Order của khách; PK theo (tenant_id, order_id) phục vụ tìm đúng Order. Không vì một cột xuất hiện trong WHERE mà tự tạo index riêng nếu thiếu độ chọn lọc hoặc thứ tự khóa không phù hợp.

Trên bảng rất lớn, thiết kế có thể dùng partition theo tenant/time, BRIN trên event time, clustering hoặc công nghệ OLAP dạng cột. Cần xem:

- Dữ liệu phân bố đều hay có **hot tenant/hot SKU**?
- Có truy vấn xuyên tenant không, và có được phép về bảo mật không?
- Event đến muộn có ghi ngược vào partition cũ không?
- Unique key có thể được cưỡng chế xuyên partition/shard không?
- Tăng index có làm write throughput/lock/bloat xấu đi không?
- Có kế hoạch retention, compression và backfill khi quy mô tăng không?

### 10.3. Capacity và acceptance threshold

Thiết lập các giả định bằng số, ví dụ:

~~~text
Scenario (giả định để review, chưa đo thực tế):
  10 triệu Order hiện có
  3 Line/Order trung bình
  100 nghìn Order/ngày
  30% Order từ tenant lớn nhất
  p95 GET /orders dưới 150 ms theo SLO được duyệt
  p95 ConfirmOrder dưới 300 ms theo SLO được duyệt
  Retention Order tối thiểu theo policy được phê duyệt

Evidence required:
  Query plan trên dữ liệu có skew phù hợp
  Index size và write overhead
  Concurrency test với hot tenant
  Backup/recovery và backfill estimates
~~~

Các số trên **chỉ là giả định minh họa**, không phải benchmark hoặc quy định chung. Khi review phải thay bằng dữ liệu sản phẩm và SLO thực tế, xác nhận người chịu trách nhiệm.

**NO-GO** nếu không có kế hoạch truy cập cho luồng trọng yếu hoặc nguy cơ hotspot/scan vượt giới hạn không được lượng hóa và xử lý.

## 11. Gate H — Dữ liệu hiện hữu, migration và khả năng tiến hóa

Một mô hình rất tốt cho bảng mới có thể không phù hợp nếu **không chuyển được dữ liệu cũ** hoặc không hỗ trợ nhiều phiên bản writer đang hoạt động.

### 11.1. Data profile bắt buộc trước migration

Đối với dữ liệu tồn tại, cần biết:

- Số hàng, NULL, giá trị sai miền, overflow, duplicate business keys.
- Orphan FK và tham chiếu sai tenant/source.
- Các mã/trạng thái cũ không map được sang định nghĩa mới.
- Đơn vị tiền, thời gian và timezone có thay đổi không.
- Dữ liệu lịch sử và dimension version có thiếu/sai khoảng hiệu lực không.
- Tập ngoại lệ thuộc tenant/source/khoảng thời gian nào, có thể sửa thế nào.
- Consumer và writer nào còn phụ thuộc schema cũ.

Không giả định đổi TEXT thành BIGINT sẽ thành công nếu tiền cũ có chuỗi “1,000”, “-100”, NULL hoặc trộn USD/VND. Phải phân loại theo **ngữ nghĩa** trước khi CAST.

### 11.2. Lộ trình expand → backfill → validate → contract

~~~mermaid
flowchart LR
    A["Profile"] --> B["Expand schema"]
    B --> C["Compatible writers/readers"]
    C --> D["Backfill theo batch"]
    D --> E["Validate và reconcile"]
    E --> F["Enforce constraints"]
    F --> G["Contract old schema"]
~~~

Trong PostgreSQL, CHECK/FK có thể có lộ trình ADD NOT VALID rồi VALIDATE CONSTRAINT để tránh xác minh tất cả hàng cũ ngay khi thêm constraint; UNIQUE/PK cần một lộ trình khác, như xây unique index concurrently khi phù hợp. CREATE INDEX CONCURRENTLY không được chạy trong transaction block.

Backfill phải **idempotent**, có checkpoint, giới hạn tài nguyên và không ghi đè thay đổi mới của writer. Nếu writer cũ tiếp tục ghi biểu diễn cũ mà không đồng bộ cột mới, một lần kiểm tra “100% chuyển xong” không đủ.

### 11.3. Rollback khác forward-fix

Trước khi bỏ cột cũ, có thể quay reader về cách đọc cũ nếu dữ liệu cũ vẫn được giữ đồng bộ. Sau khi DROP cột hoặc nhận giá trị không thể biểu diễn bằng schema trước, **rollback ứng dụng không đồng nghĩa rollback dữ liệu**. Phải có restore/backfill ngược/forward-fix hợp lệ và xác định điểm không thể quay lại trực tiếp.

### 11.4. Migration là một tiêu chí thiết kế

**NO-GO** nếu dữ liệu bắt buộc không thể chuyển mà chưa có phương án; chưa có kế hoạch xử lý orphan/duplicate; hoặc migration có khả năng tạo **hai nguồn sự thật cùng quyền ghi** khi chuyển shard/service mà không có fencing/cutover protocol.

## 12. Gate I — Bảo mật, quyền truy cập và dữ liệu nhạy cảm

Một schema có khóa đúng nhưng cho phép user của tenant A đọc dữ liệu tenant B **không đạt nghiệm thu**.

### 12.1. Kiểm tra phân tách tenant

- Tenant có phải thành phần của **khóa và FK** ở mọi bảng liên quan không?
- API/ORM có luôn lọc tenant_id từ **ngữ cảnh xác thực**, không tin tenant_id tùy ý do client gửi?
- Các truy vấn analytics, export, search index, cache key và job batch có phân tách tenant tương ứng không?
- DB role, view, row-level security hoặc service authorization có áp dụng đúng với mọi đường đọc/ghi không?
- Super-admin và hoạt động hỗ trợ có audit, phạm vi quyền, thời gian hiệu lực và cơ chế phê duyệt không?
- Tình huống đổi owner, merge tenant hoặc migrate shard có làm lộ dữ liệu không?

Một khóa (tenant_id, order_id) giúp ngăn tham chiếu nhầm tenant, **nhưng không tự đảm bảo mọi SELECT đều có WHERE tenant_id**. Đó là hai lớp bảo vệ khác nhau. Nếu sử dụng PostgreSQL Row-Level Security (RLS), phải kiểm chứng chính sách cho từng role thực tế; quyền owner, BYPASSRLS hoặc cách cấu hình có thể ảnh hưởng mức cưỡng chế.

### 12.2. Phân loại dữ liệu và vòng đời

Từ điển dữ liệu phải chỉ rõ thuộc tính nào thuộc các nhóm:

| Nhóm | Ví dụ | Câu hỏi nghiệm thu |
| --- | --- | --- |
| **Định danh cá nhân** | Email, điện thoại, tên, địa chỉ | Ai được đọc, bao lâu, có cần masking/ẩn danh? |
| **Dữ liệu thanh toán** | Token provider, trạng thái, tham chiếu | Có đang lưu dữ liệu nhạy cảm không cần thiết? |
| **Thông tin doanh nghiệp** | Giá vốn, ngân sách, thỏa thuận | Role và tenant nào được phép xem? |
| **Dữ liệu công khai** | Danh mục Product công khai | Có thực sự công khai trong mọi tenant? |
| **Dữ liệu suy diễn** | Điểm rủi ro, phân khúc khách | Nguồn, mục đích sử dụng và quyền truy cập? |

Không suy ra mọi dữ liệu phải được giữ vô thời hạn chỉ vì có FK hoặc yêu cầu audit. Cũng không xóa mù một Order còn cần đối soát theo nghĩa vụ đã được phê duyệt. Cần xác định **phạm vi retention, backup, bản sao analytics và quy trình xóa/ẩn danh** theo chính sách phù hợp.

### 12.3. Bằng chứng P0

- Negative authorization test: tenant A cố lấy Order tenant B phải bị từ chối/không tìm thấy theo hợp đồng API.
- Test truy vấn report/export không làm rò dòng của tenant khác.
- Test database role của job vận hành không có quyền sửa invariant ngoài owner.
- Checklist mã hóa khi truyền/lưu, quản lý secret, logging không lộ PII theo chính sách.
- Chủ sở hữu và quy trình phản hồi yêu cầu xóa/ẩn danh có thể triển khai.

**NO-GO** nếu một đường đọc/ghi được hỗ trợ có thể vượt quyền, hoặc nhóm chưa biết dữ liệu nhạy cảm được nhân bản/giữ ở đâu.

## 13. Gate J — Chất lượng dữ liệu, vận hành và tính quan sát được

Mô hình không kết thúc ở CREATE TABLE. Một khi chạy, dữ liệu sẽ sai, muộn, trùng, mất nguồn, và job có thể dừng giữa chừng.

### 13.1. Các quy tắc chất lượng phải có chỉ số

| Chỉ tiêu | Ý nghĩa | Tín hiệu phải quan sát |
| --- | --- | --- |
| **Completeness** | Các đối tượng/sự kiện bắt buộc đã đến đủ chưa? | Missing IDs/partitions, expected vs accepted |
| **Uniqueness** | Một sự kiện/khóa không được nhân | Duplicate business key, retry conflicts |
| **Validity** | Giá trị thuộc miền, đúng đơn vị/format | CHECK failures, invalid amount/currency |
| **Referential integrity** | Child trỏ tới parent đúng tenant và version | Orphan count, pending references |
| **Freshness** | Dữ liệu có được cập nhật đúng SLA? | Current lag, last successful load |
| **Consistency** | Bảng trạng thái và sự kiện nền khớp nhau? | Balance vs reservations, Order vs Lines |
| **Accuracy** | Giá trị có khớp nguồn kiểm chứng? | Control totals, sample reconciliation |
| **History fidelity** | Có tái hiện được kết quả đã biết/tại thời điểm? | As-of queries, revision completeness |

Một pipeline có thể nhận 100% số event **đã gửi đến** nhưng nguồn còn 10% event chưa phát. Vì vậy completeness phải so với **nguồn điều khiển/sequence/contract**, không chỉ số hàng trong kho.

### 13.2. Ownership của lỗi và quy trình hồi phục

Bản review phải trả lời:

1. Event có source ID ổn định không? Khi retry cùng ID nhưng payload khác thì xử lý thế nào?
2. FK/Dimension chưa có thì **reject, pending hay unknown member**? Khi nào backfill?
3. Một order bị sửa sau kỳ báo cáo khóa thì restate hay ghi kỳ hiện tại?
4. Nếu job aggregate lỗi giữa hai mart, dashboard có thể thấy hai version khác nhau không?
5. Dữ liệu vượt threshold có tự chặn publish hay chỉ cảnh báo?
6. Ai nhận alert, thời hạn xử lý và cách đối soát sau phục hồi?
7. Backup/restore và replay có giữ danh tính/phiên bản đủ để tránh nạp lặp không?

**NO-GO** nếu không có cách phát hiện và khôi phục sai lệch P0 hoặc không ai sở hữu dữ liệu bị lỗi. Với những bất biến phải đúng khi chấp nhận lệnh, kiểm tra hậu kỳ chỉ là **hàng rào bổ sung**, không thay cơ chế ghi đúng.

## 14. Gate K — Lựa chọn mô hình: relational, document, graph, analytical

Không có một bộ công nghệ tối ưu cho mọi dạng dữ liệu. Cần chấp nhận **logic nghiệp vụ trước**, rồi đánh giá cách ánh xạ phù hợp.

### 14.1. Bảng đánh đổi

| Mô hình | Phù hợp khi | Điểm nghiệm thu quan trọng | Rủi ro thường bị bỏ quên |
| --- | --- | --- | --- |
| **Quan hệ** | PK/FK, giao dịch, joins có cấu trúc, chuẩn hóa | Cơ chế ràng buộc, transaction, query plan | Cross-shard FK không tự có, JOIN fan-out |
| **Document** | Một aggregate được đọc/ghi gần như toàn khối | Kích thước document, atomic update, versioning | Embedded array tăng vô hạn; tham chiếu xuyên document |
| **Graph** | Traversal nhiều bước, quan hệ đa dạng | Node/edge identity, cardinality, cycle constraints | Multi-path counting, kiểm tra chu trình xuyên shard |
| **Time series** | Dòng đo theo timestamp và metric labels | Series key, sample grain, late data, retention | High-cardinality tags, duplicate timestamp |
| **OLAP/warehouse** | Tổng hợp lịch sử trên nhiều chiều | Fact grain, conformed dimensions, SCD, additive measures | SUM snapshot/gauge, drill-across nhân số |

### 14.2. Cùng một câu hỏi nghiệp vụ, các cách biểu diễn

Giả sử Order gồm các Line.

**Relational:** SalesOrder và OrderLine là hai bảng với FK ghép. Nếu cùng database/owner, kiểm tra và commit nhiều hàng trong transaction. Phù hợp khi cần cập nhật Line riêng lẻ, truy vấn sâu và ràng buộc liên hệ.

**Document:** một Order document nhúng mảng Lines. Có thể cập nhật nguyên tử theo document khi DBMS hỗ trợ, nhưng phải đánh giá kích thước khi một Order có hàng chục nghìn Line và cách các consumer truy vấn theo Product.

**Graph:** Order và Line/Product là node/cạnh khi cần duyệt mạng quan hệ phức tạp; phải quyết định Line là node riêng có danh tính hay cạnh có thuộc tính, và chống nhân số liệu khi có nhiều đường.

**Warehouse:** FactOrderLine và DimProduct phục vụ phân tích; không dùng một mart có độ trễ để quyết định giữ hàng ngay lúc checkout. Cần chọn grain, khóa phiên bản và tính additive của measure.

Không chọn document chỉ vì “không cần migration” — khi JSON thay hình dạng, reader/index/validator vẫn cần version và backfill. Không chọn graph chỉ vì có FK — đa số quan hệ 1–N đơn giản không tự cần graph DB.

### 14.3. Cổng chấp nhận lựa chọn công nghệ

Bản quyết định phải có:

- Mẫu truy vấn/ghi tiêu biểu; ước lượng kích thước, bội số và thay đổi.
- Cơ chế cưỡng chế invariant trên công nghệ đã chọn.
- Thử nghiệm ít nhất một đường ghi cạnh tranh và một đường đọc quan trọng.
- Chi phí vận hành, backup, migration, phân quyền, tổ chức team và khả năng truy vết.
- Phương án khi mô hình tiến hóa: thêm chiều, tăng kết nối, thay retention hoặc cần báo cáo lịch sử.

**NO-GO** nếu lý do chọn mô hình chỉ là xu hướng công nghệ hoặc sơ đồ trông gọn mà chưa chứng minh được ràng buộc và truy vấn thiết yếu.

## 15. Ca nghiệm thu xuyên suốt: hệ đặt hàng đa tenant

### 15.1. Phạm vi v1 được chốt

Mô hình minh họa một hệ đặt hàng có các quy tắc:

- Một **registered Customer** có thể đặt 0..N Order; mỗi Order bắt buộc thuộc 1 Customer trong cùng tenant. **Guest checkout không thuộc v1**.
- Một Order DRAFT có thể có 0..N Line; Order CONFIRMED phải có ít nhất một Line.
- Mỗi Line thuộc đúng một Order và trỏ tới một Product trong cùng tenant.
- Product có thể inactive; Line lịch sử không bị xóa theo Product.
- Mỗi Line giữ **unit_price_vnd** tại thời điểm bán; không lấy giá Product hiện tại cho chứng từ.
- Mỗi Order có mã hiển thị **duy nhất trong tenant**, không yêu cầu duy nhất toàn SaaS.
- PaymentAttempt là một **lần thử** có ID provider ổn định; callback retry không tạo thêm attempt.
- Version v1 chỉ dùng **VND nguyên đồng**, chưa có refund, multi-currency, split shipment hoặc phê duyệt tồn kho xuyên nhiều warehouse. Các nghiệp vụ này cần review lại khi bổ sung.

Đây là **quyết định scope**, không phải lời khẳng định những tính năng bị loại là không quan trọng. Nếu sản phẩm thực tế phải hỗ trợ guest, ngoại tệ hoặc nhiều lần capture, cần thay contract và dữ liệu thử ngay trước khi chấp nhận.

### 15.2. Mô hình logic và bội số

~~~mermaid
erDiagram
    TENANT ||--o{ CUSTOMER : owns
    TENANT ||--o{ PRODUCT : owns
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--o{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : referenced_by
    SALES_ORDER ||--o{ PAYMENT_ATTEMPT : has
~~~

Sơ đồ chỉ thể hiện cấu trúc. Ghi chú đi kèm bắt buộc:

~~~text
Order -> Customer:         1..1, cùng tenant
Customer -> Order:         0..N
Line -> Order:             1..1, cùng tenant
Order DRAFT -> Line:       0..N
Order CONFIRMED -> Line:   1..N
Line -> Product:           1..1, cùng tenant
Product -> Line:           0..N, kể cả khi inactive
PaymentAttempt -> Order:   1..1
Order -> PaymentAttempt:   0..N
~~~

### 15.3. Bất biến ưu tiên

| ID | Bất biến | Mức | Cơ chế dự kiến |
| --- | --- | --- | --- |
| INV-01 | Không tham chiếu Customer/Product/Order khác tenant | P0 | Composite FK và authorization |
| INV-02 | Không trùng order_code trong tenant | P0 | UNIQUE(tenant_id,order_code) |
| INV-03 | Một Line không có quantity <= 0 hoặc giá âm | P0 | CHECK + NOT NULL |
| INV-04 | Order CONFIRMED có tối thiểu một Line | P0 | Order owner transaction và mọi writer theo cùng lock |
| INV-05 | Không sửa Line sau khi Order CONFIRMED | P0 | Write owner và quyền DB |
| INV-06 | Callback PaymentAttempt retry không nhân bản | P0 | Unique provider reference, payload validation |
| INV-07 | Product inactive không được chọn cho Line mới | P1 | Transactional owner check |
| INV-08 | Truy vấn lịch sử không lấy giá Product mới làm giá bán cũ | P1 | Snapshot unit_price_vnd và test |
| INV-09 | Không xóa cứng Product/Customer còn Line/Order | P1 | FK RESTRICT + archive policy |
| INV-10 | Query Order list đáp ứng SLO trên workload đại diện | P1 | Index/query plan/load test |
| INV-11 | Có số đo ingest lag/quality và cách recovery | P1 | Metrics, audit, runbook |
| INV-12 | Schema có khả năng tiến hóa cho guest/multi-currency | P2 | ADR và change triggers |

**Các mức P0/P1 chỉ là phân loại minh họa cho ca học.** Trong dự án thực tế, người phụ trách nghiệp vụ, security và SRE phải cùng duyệt mức ưu tiên.

## 16. Prototype DDL PostgreSQL và giới hạn bảo vệ

Đây là thiết kế **đủ nhỏ để thử nghiệm**, không phải một hệ thống order/payment production hoàn chỉnh. Chạy trên database thử, không trên dữ liệu thật.

### 16.1. Bảng định danh

~~~sql
CREATE TABLE dv_tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_code TEXT NOT NULL UNIQUE
);

CREATE TABLE dv_customers (
    tenant_id BIGINT NOT NULL REFERENCES dv_tenants(tenant_id),
    customer_id BIGINT NOT NULL,
    customer_code TEXT NOT NULL,
    archived_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, customer_code)
);

CREATE TABLE dv_products (
    tenant_id BIGINT NOT NULL REFERENCES dv_tenants(tenant_id),
    product_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (tenant_id, product_id),
    UNIQUE (tenant_id, sku)
);
~~~

**Nhận xét:** Customer/Product đều có PK ghép theo tenant, và business code được bảo vệ trong tenant. archived_at / is_active không kích hoạt ON DELETE và không tự cấm Order/Line mới; đó là invariant khi ghi.

### 16.2. Order, Line và PaymentAttempt

~~~sql
CREATE TABLE dv_sales_orders (
    tenant_id BIGINT NOT NULL REFERENCES dv_tenants(tenant_id),
    order_id BIGINT NOT NULL,
    order_code TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT','CONFIRMED','CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,

    PRIMARY KEY (tenant_id, order_id),
    UNIQUE (tenant_id, order_code),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES dv_customers(tenant_id, customer_id)
        ON DELETE RESTRICT,
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL),
    CHECK (status <> 'CANCELLED' OR cancelled_at IS NOT NULL)
);

CREATE TABLE dv_order_lines (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd >= 0),

    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES dv_sales_orders(tenant_id, order_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES dv_products(tenant_id, product_id)
        ON DELETE RESTRICT
);

CREATE TABLE dv_payment_attempts (
    tenant_id BIGINT NOT NULL,
    payment_attempt_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    provider_code TEXT NOT NULL,
    provider_attempt_ref TEXT NOT NULL,
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd > 0),
    status TEXT NOT NULL CHECK (
        status IN ('INITIATED','AUTHORIZED','CAPTURED','FAILED')
    ),

    PRIMARY KEY (tenant_id, payment_attempt_id),
    UNIQUE (tenant_id, provider_code, provider_attempt_ref),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES dv_sales_orders(tenant_id, order_id)
        ON DELETE RESTRICT
);
~~~

### 16.3. Index truy vấn

~~~sql
-- Truy vấn danh sách Order của một Customer, newest first.
CREATE INDEX idx_dv_orders_customer_created
ON dv_sales_orders (tenant_id, customer_id, created_at DESC, order_id DESC);

-- Tra PaymentAttempt theo Order; UNIQUE provider ref phục vụ
-- đường callback, index này phục vụ đọc theo Order.
CREATE INDEX idx_dv_payment_attempts_order
ON dv_payment_attempts (tenant_id, order_id);

-- PK(tenant_id,order_id,line_no) đã hỗ trợ lấy Line theo Order.
-- Chỉ thêm index cho Product nếu truy vấn thực tế yêu cầu.
~~~

Trong PostgreSQL, bảng con có FK không mặc định được tạo mọi index cần thiết. Index có chi phí ghi và lưu trữ; chỉ chấp nhận khi có mẫu truy vấn/công suất chứng minh công dụng.

### 16.4. Dữ liệu thử mang tính phân biệt tenant

~~~sql
INSERT INTO dv_tenants(tenant_id,tenant_code)
VALUES (1,'SHOP-A'), (2,'SHOP-B');

INSERT INTO dv_customers
    (tenant_id,customer_id,customer_code)
VALUES (1,11,'C-11'), (2,11,'C-11');

INSERT INTO dv_products
    (tenant_id,product_id,sku)
VALUES (1,101,'P-101'), (2,101,'P-101');

INSERT INTO dv_sales_orders
    (tenant_id,order_id,order_code,customer_id,status)
VALUES (1,1001,'O-1001',11,'DRAFT');

INSERT INTO dv_order_lines
    (tenant_id,order_id,line_no,product_id,quantity,unit_price_vnd)
VALUES
    (1,1001,1,101,2,150000),
    (1,1001,2,101,1,130000);
~~~

Hai Line cùng Product 101 **không phải duplicate**: grain là từng Line trong Order, có giá tại giao dịch khác nhau. Tổng giá trị dòng theo dữ liệu mẫu là **2 × 150.000 + 1 × 130.000 = 430.000 VND**. Không lấy Product hiện hành rồi thay đơn giá đã chốt.

### 16.5. Đọc ràng buộc nào thực sự được DBMS bảo vệ

| Invariant | Được DDL cưỡng chế? | Điểm còn thiếu |
| --- | --- | --- |
| Composite tenant references | Có, trong một PostgreSQL database | Không thay authorization ở API |
| UNIQUE order_code trong tenant | Có | Chuẩn hóa order_code theo nghiệp vụ |
| Quantity/price hợp lệ | Có, phạm vi cột đã nêu | Tiền tệ và quy tắc thuế không có trong ví dụ |
| Order CONFIRMED có Line | **Chưa** | Transaction/owner kiểm tra xuyên hàng |
| Product active tại lúc thêm Line | **Chưa** | Kiểm tra trạng thái Product khi ghi |
| Không sửa Line sau CONFIRMED | **Chưa** | Write path/roles/trigger nếu cần |
| Callback trùng provider ref | Unique key có | Cùng ID khác payload phải phân loại lỗi |
| Payment đã được capture đúng một lần ngoài gateway | **Chưa** | Giao thức với provider và idempotency |
| Lịch sử Product name/category | **Chưa** | Snapshot/version dimension khi cần |

**Không được** đánh dấu toàn bộ INV-01..INV-12 PASS chỉ vì DDL trên tạo thành công. DDL là **một phần** của bộ bằng chứng.

## 17. Truy vấn đối soát và kiểm thử tiền triển khai

### 17.1. Phát hiện Order CONFIRMED thiếu Line

~~~sql
SELECT o.tenant_id, o.order_id
FROM dv_sales_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM dv_order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
-- Kỳ vọng: không có hàng.
~~~

Đây là **test đối soát**, không phải cơ chế bảo vệ khi ghi. Nếu hai session cập nhật status và xóa Line cuối mà không chung quy ước khóa, query này có thể phát hiện lỗi sau khi đã xảy ra.

### 17.2. Quy trình xác nhận Order có điều kiện

~~~sql
BEGIN;

-- Bước 1: khóa Order làm điểm tuần tự hóa quyết định.
SELECT status
FROM dv_sales_orders
WHERE tenant_id = 1 AND order_id = 1001
FOR UPDATE;

-- Bước 2: kiểm tra có Line.
SELECT EXISTS (
    SELECT 1
    FROM dv_order_lines
    WHERE tenant_id = 1 AND order_id = 1001
) AS has_line;

-- Bước 3: CHỈ KHI status hiện tại = DRAFT,
-- has_line = true và các điều kiện nghiệp vụ khác đạt:
UPDATE dv_sales_orders
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE tenant_id = 1
  AND order_id = 1001
  AND status = 'DRAFT'
RETURNING tenant_id, order_id, status;

-- Nếu không đủ điều kiện hoặc update sai số hàng: ROLLBACK.
-- Nếu điều kiện đã kiểm tra và update đúng một hàng: COMMIT.
COMMIT;
~~~

**Đây là mẫu quy trình có nhánh điều kiện, không phải script được phép chạy mù tới COMMIT.** Cần hiện thực trong application service/stored procedure, và **mọi writer thêm/sửa/xóa Line** phải khóa Order trước, kiểm tra trạng thái và commit cùng transaction. Nếu chỉ ConfirmOrder lấy khóa mà DeleteLine không theo quy ước, invariant vẫn có thể bị phá.

### 17.3. Truy vấn đối soát tổng giá trị dòng

~~~sql
SELECT tenant_id, order_id,
       SUM(quantity * unit_price_vnd) AS line_total_vnd,
       COUNT(*) AS line_count
FROM dv_order_lines
GROUP BY tenant_id, order_id
ORDER BY tenant_id, order_id;
-- Với Order (1,1001): 430000 VND, 2 Line.
~~~

Không JOIN Line với PaymentAttempt rồi SUM cùng lúc khi cả hai đều là quan hệ 1–N của Order. Hai PaymentAttempt và hai Line sẽ sinh bốn hàng ghép; tổng tiền có thể bị nhân. Khi cần drill-across, **aggregate từng tập con theo đúng grain trước khi JOIN**.

### 17.4. Phát hiện dữ liệu trạng thái sai lifecycle

~~~sql
SELECT tenant_id, order_id, status,
       confirmed_at, cancelled_at
FROM dv_sales_orders
WHERE (status = 'CONFIRMED' AND confirmed_at IS NULL)
   OR (status = 'CANCELLED' AND cancelled_at IS NULL);
-- Các dòng này đã được CHECK cấm khi DDL đang hoạt động.
~~~

Nhưng query trên **không thể phát hiện** mọi transition sai như CANCELLED → CONFIRMED nếu writer tự điền confirmed_at. Cần test state machine và audit các transition.

### 17.5. Kiểm tra logical FK khi không có FK vật lý

Nếu mô hình phân tán Customer và Order ở hai service, có thể xây một tập đối soát đã làm sạch từ cả hai nguồn:

~~~sql
-- Chỉ là phép kiểm chứng trên các bản sao đã gom chung trong môi trường
-- đối soát; không tự có distributed FK xuyên hai database độc lập.
SELECT o.tenant_id, o.order_id, o.customer_id
FROM dv_sales_orders AS o
LEFT JOIN dv_customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

Bộ kiểm chứng phải tính tới **độ trễ giữa hai nguồn**: orphan tạm thời do event Customer đến muộn không có cùng mức độ với orphan sau cutoff đã cam kết. Cần có quy tắc về thời điểm kiểm tra và cách phân loại.

### 17.6. Kiểm tra SQL có diễn giải đúng tenant

~~~sql
-- ĐÚNG phạm vi: ID một Order được xác định bởi tenant và order.
SELECT *
FROM dv_sales_orders
WHERE tenant_id = 1
  AND order_id = 1001;
~~~

Một truy vấn chỉ lọc order_id có thể trả nhiều Order ở các tenant khác nhau khi mỗi tenant có một mã 1001. Không được dựa vào trường hợp dữ liệu mẫu nhỏ chỉ có một Order để suy rằng order_id là khóa toàn cục.

### 17.7. EXPLAIN và đo hiệu năng

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, order_id, status, created_at
FROM dv_sales_orders
WHERE tenant_id = 1
  AND customer_id = 11
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Trên bảng thử rất nhỏ, PostgreSQL có thể chọn Seq Scan vì đọc hết bảng rẻ hơn dùng index. Điều này **không có nghĩa index chắc chắn sai**. Phải kiểm tra trên dữ liệu đủ đại diện với phân bố tenant lớn/nhỏ và so sánh kế hoạch thực tế, buffers, rows và latency.

EXPLAIN ANALYZE **thực thi truy vấn**; chỉ chạy INSERT/UPDATE/DELETE kèm EXPLAIN ANALYZE nếu cố ý thử thao tác ghi trong môi trường an toàn. Không suy ra SLA production từ một lần EXPLAIN trên fixture mười hàng.

## 18. Ma trận kiểm thử trước quyết định chấp nhận

Một danh sách checkbox không đủ nếu không chỉ ra **dữ liệu đầu vào, thao tác, kết quả mong đợi và bằng chứng**.

### 18.1. Kiểm thử dương, âm và cạnh tranh

| ID | Tình huống | Kết quả kỳ vọng | Bằng chứng |
| --- | --- | --- | --- |
| T01 | Tạo Order hợp lệ trong tenant 1 | Thành công | Integration result |
| T02 | Tạo Order trùng order_code trong tenant 1 | UNIQUE từ chối | Negative SQL test |
| T03 | Hai tenant cùng order_code | Được phép theo policy | Positive test |
| T04 | Line tham chiếu Order chỉ tồn tại ở tenant khác | FK ghép từ chối | Negative SQL test |
| T05 | Line có quantity = 0 | CHECK từ chối | Negative SQL test |
| T06 | Line có unit_price_vnd âm | CHECK từ chối | Negative SQL test |
| T07 | Xóa Product đã có Line | FK RESTRICT từ chối | Negative SQL test |
| T08 | Archive Product đã có Line | Line lịch sử vẫn còn | Lifecycle test |
| T09 | Confirm Order không có Line | Owner từ chối | Domain test |
| T10 | Confirm Order có Line | Commit đúng một lần | Domain test |
| T11 | Confirm đồng thời xóa Line cuối | Không có CONFIRMED thiếu Line | Race test hai session |
| T12 | Payment callback retry cùng ID/payload | Không nhân hiệu ứng | Idempotency test |
| T13 | Callback cùng ID nhưng payload khác | Báo conflict; không ghi đè âm thầm | Conflict test |
| T14 | API tenant A đọc Order tenant B | Từ chối/không tìm thấy | Authorization test |
| T15 | JOIN Order có nhiều Line và Attempt | Tổng không bị nhân | Reconciliation |
| T16 | Backfill gặp orphan/duplicate | Quarantine; không công bố là sạch | Migration dry run |
| T17 | Writer cũ chạy cùng backfill | Không divergence sau cutoff | Compatibility test |
| T18 | Worker lỗi sau DB commit trước khi ACK | Replay không nhân tác động | Failure injection |
| T19 | Product đổi Category và fact đến muộn | Dùng version đúng nếu cần as-sold | Temporal test |
| T20 | Restore/replay sau sự cố | Đúng identity và RTO/RPO đã duyệt | Recovery drill |

**Trạng thái của test phải là PASS, FAIL, NOT RUN hoặc N/A có lý do.** Việc đã viết test case không được coi là PASS. Tương tự, khi chưa có prototype chạy được, có thể ghi “DESIGNED” hoặc “READY TO TEST”, nhưng không được tự báo đã kiểm chứng thực nghiệm.

### 18.2. Test âm phải cô lập transaction

~~~sql
-- Chạy trong database thử với dữ liệu mẫu ở phần 16.
-- Tenant 2 có Product 101 nhưng chưa có Order 1001.
INSERT INTO dv_order_lines
    (tenant_id, order_id, line_no, product_id,
     quantity, unit_price_vnd)
VALUES (2, 1001, 1, 101, 1, 150000);
-- Kỳ vọng: foreign_key_violation.
~~~

Nếu test harness chạy nhiều câu SQL dự kiến thất bại trong **một transaction PostgreSQL** mà không dùng SAVEPOINT, sau lỗi đầu tiên transaction có thể rơi vào trạng thái aborted. Các câu sau không còn kiểm chứng riêng từng invariant. Tổ chức mỗi negative test trong một transaction được quản lý độc lập hoặc dùng savepoint và rollback về savepoint tương ứng.

### 18.3. Race test phải có lịch giao cắt

~~~text
Session A:
  BEGIN
  Lock Order 1001
  Check Line exists
  PAUSE

Session B:
  BEGIN
  Attempt delete last Line
  Must follow same parent-lock protocol
  Wait or reject based on Order state

Session A:
  Commit transition to CONFIRMED

Session B:
  Re-check state
  Reject deletion when illegal
  ROLLBACK / business error

Final validation:
  No CONFIRMED Order without Line.
~~~

Cần thử cả chiều ngược lại: DeleteLine lấy khóa và commit trước, ConfirmOrder kiểm tra lại rồi từ chối nếu hết Line. Chạy hai transaction tuần tự trong một session **không phải** kiểm thử concurrency.

### 18.4. Tập dữ liệu thử phải có trường hợp biên

Một fixture tối thiểu nên chứa hai tenant dùng cùng numeric ID, hai Line cùng SKU khác giá, Order DRAFT không Line, Product inactive vẫn được OrderLine lịch sử tham chiếu, hai PaymentAttempt khác nhau trên một Order, callback retry, NULL/duplicate/orphan từ dữ liệu cũ và tập dữ liệu có tenant nóng. Không chỉ dựng một tenant–một Order–một Line rồi kết luận mô hình đúng.

## 19. Biên bản review và cổng GO / NO-GO

### 19.1. Mẫu hồ sơ có thể dùng lại

~~~text
MODEL ACCEPTANCE RECORD

Model:
  Multi-tenant Sales Order v1

Model revision:
  [version / DDL revision]

Review date:
  [ngày review]

Scope:
  Registered Customer, Order, Line, Product,
  PaymentAttempt; VND; chưa hỗ trợ guest/multi-currency.

Decision:
  GO | CONDITIONAL GO | NO-GO

P0 evidence:
  Tenant FK + authorization
  Grain and uniqueness
  Order/Line lifecycle and concurrency
  Payment idempotency

P1 evidence:
  Migration and rollback
  Representative workload/query plans
  Retention/access controls
  Quality/observability and recovery

Supporting artifacts:
  Domain glossary, ERD, data dictionary,
  invariant catalog, test logs, migration dry run,
  security approval, query/capacity estimates.

Open issues:
  [ID, severity, impact, owner, due date,
   exact release-blocking condition]

Reason for decision:
  [bằng chứng nào đạt/chưa đạt]

Permitted activities:
  [prototype only / staging / canary / production]

Prohibited activities:
  [những đường ghi/tính năng chưa được bật]

Sign-off:
  Domain Owner; Data Modeler; DBA;
  Application Owner; Security; Release Owner

Triggers for re-review:
  Guest checkout, currency/refund expansion,
  sharding changes, history/retention changes,
  significant workload increase.
~~~

Nếu chưa có người thực sự xác nhận **ngữ nghĩa nghiệp vụ**, khóa/mô hình hoặc bảo mật, không tự điền PASS chỉ để hồ sơ hoàn chỉnh.

### 19.2. Ví dụ kết luận trung thực khi chưa chạy đủ test

Giả sử nhóm có DDL prototype nhưng **chưa chạy T11 race test** và chưa đo SLO trên dữ liệu có skew:

~~~text
Decision:
  NO-GO for production write traffic.

Accepted for prototype work:
  Identity/grain of Order and Line.
  Composite tenant-aware FK/UNIQUE proposal.
  Data dictionary for money and lifecycle.

Pending:
  T11 concurrency: NOT RUN.
  T18 failure/retry: NOT RUN.
  p95 under hot-tenant load: NOT MEASURED.
  PII retention: OWNER APPROVAL PENDING.

Allowed:
  Continue implementation in isolated environment.
  Run concurrency/load/security/migration tests.

Not allowed:
  Open production traffic for CONFIRMED Order.
  Claim end-to-end invariants are proven.

Re-review:
  After required evidence and sign-offs exist.
~~~

Một review **trước triển khai** có thể cho phép **bắt đầu xây prototype**, nhưng chưa cho phép **phát hành production**. Cần ghi rõ quyết định đang chấp thuận hành động nào. CONDITIONAL GO chỉ hợp lý nếu phạm vi hạn chế **thực sự ngăn rủi ro chưa được đóng**.

### 19.3. Khi nào một quyết định chấp nhận hết hiệu lực?

Phải review lại khi thay:

- Bội số: ví dụ thêm guest checkout.
- Phạm vi unique: order_code từ per-tenant thành global.
- Đơn vị: từ chỉ VND sang nhiều currency.
- Quy tắc vòng đời: thêm refund, partial capture hoặc split fulfillment.
- Ranh giới nhất quán: tách Order/Line hoặc Customer sang database khác.
- Grain fact hoặc phiên bản SCD/late correction.
- Quy mô: hot tenant, phân vùng/sharding hoặc data volume tăng nhiều lần.
- Chính sách bảo mật, xóa dữ liệu, thời hạn retention.
- Công nghệ lưu hoặc DBMS/version có hành vi constraint/index khác.

Một dấu “Approved” ở v1 **không áp dụng vô thời hạn** cho v2 đã đổi hợp đồng.

## 20. Checklist nghiệm thu có thể sử dụng trực tiếp

Với mỗi dòng, thêm cột **Severity, Owner, Evidence ID, Status, Due Date** trong hồ sơ thực tế. Chỉ chọn PASS nếu có bằng chứng đạt.

### A. Phạm vi và nghiệp vụ

- [ ] A01. Use case, scope v1 và chức năng ngoài phạm vi đã được xác nhận.
- [ ] A02. Thuật ngữ và KPI quan trọng có định nghĩa không mâu thuẫn.
- [ ] A03. Các ngoại lệ nghiệp vụ, trạng thái và transition được làm rõ.
- [ ] A04. Invariant có ID, scope, thời điểm phải đúng và mức nghiêm trọng.
- [ ] A05. Có owner ký xác nhận ngữ nghĩa trước khi coding.

### B. Grain, khóa và quan hệ

- [ ] B01. Mỗi bảng/document/fact có câu grain rõ.
- [ ] B02. Candidate/business/surrogate keys, phạm vi tenant/source/time và quy tắc đổi mã được nêu.
- [ ] B03. Retry cùng event không trở thành hai sự kiện nghiệp vụ.
- [ ] B04. PK/FK/UNIQUE/CHECK/NOT NULL phản ánh đúng phạm vi và logic NULL.
- [ ] B05. Quan hệ có predicate, role và bội số min..max ở cả hai phía.
- [ ] B06. M:N, 1:1 optional và tự tham chiếu có cách bảo vệ phù hợp.
- [ ] B07. Reference xuyên service/shard được ghi là logical khi không có FK vật lý.
- [ ] B08. Invariant cần nhiều hàng có owner/transaction/protocol rõ.
- [ ] B09. Có cách phát hiện orphan, duplicate, sai tenant và lệch dimension version.

### C. Ngữ nghĩa, thời gian, vòng đời

- [ ] C01. Các trường có kiểu, đơn vị, miền hợp lệ, NULL semantics và source.
- [ ] C02. Missing, zero, invalid, unknown, not-applicable được phân biệt.
- [ ] C03. Event/valid/posting/ingest time và timezone được chọn theo câu hỏi nghiệp vụ.
- [ ] C04. History, SCD, revision, late events và as-of queries có chính sách.
- [ ] C05. Fact transaction/snapshot/delta và measure aggregate rules tách biệt.
- [ ] C06. ON DELETE/UPDATE, archive, ẩn danh và retention có lý do.
- [ ] C07. Correction/restate không làm thay đổi số đã công bố mà không có dấu vết.

### D. Ghi và cạnh tranh

- [ ] D01. Mọi bất biến P0 được bảo vệ ở đúng thời điểm nhận command.
- [ ] D02. Có một owner có thẩm quyền cho từng quyết định quan trọng.
- [ ] D03. Race tests gây xung đột thực sự đã chạy hoặc là release blocker.
- [ ] D04. Retry sau timeout/commit không nhân tác động.
- [ ] D05. Saga/2PC/compensation được mô tả đúng khả năng hỗ trợ thực tế.
- [ ] D06. Partition/shard key không phá global unique hoặc cross-row invariant.
- [ ] D07. Batch/admin/CDC và mọi writer khác tuân thủ cùng hợp đồng.

### E. Hiệu năng và vận hành

- [ ] E01. Access matrix có truy vấn chính, filter, join, sort, SLO.
- [ ] E02. Index/partition/clustering có lý do và kế hoạch đo.
- [ ] E03. Đã xét skew, hot keys, late arrivals, high-cardinality labels.
- [ ] E04. Dung lượng, tăng trưởng, lưu trữ và write overhead được ước lượng.
- [ ] E05. Có kế hoạch backup, restore, backfill, migration, rollback.
- [ ] E06. Có monitoring freshness/completeness/duplicate/orphan/consistency.
- [ ] E07. Có runbook và owner xử lý lỗi, replay, phục hồi theo RTO/RPO.

### F. An toàn, migration và bằng chứng

- [ ] F01. Tenant isolation được kiểm tra ở DB, API, cache, export và BI.
- [ ] F02. Dữ liệu nhạy cảm, quyền truy cập, masking và xóa/retention rõ ràng.
- [ ] F03. Negative tests về constraint, authorization và vòng đời có kết quả.
- [ ] F04. Data profiling và ngoại lệ cũ được giải quyết/giới hạn chính thức.
- [ ] F05. Expand–backfill–validate–contract có thể chạy với writer đang hoạt động.
- [ ] F06. Rollback/forward-fix và điểm không thể quay lại trực tiếp được phê duyệt.
- [ ] F07. Yêu cầu được trace tới model, enforcement, test và bằng chứng.
- [ ] F08. Mỗi FAIL/NOT RUN có owner, severity và trạng thái chặn release.
- [ ] F09. GO/CONDITIONAL GO/NO-GO có scope, hạn hiệu lực và sign-off.
- [ ] F10. Change triggers buộc review lại được ghi rõ.

**Cách đánh giá:** một lỗi P0 không thể được bù bằng nhiều mục P2 hoàn thành. Mục N/A phải có lý do. Nếu chỉ có mô tả dự kiến nhưng chưa chạy test, ghi **NOT RUN**; có thể chấp nhận thiết kế cho mục đích xây thử, nhưng không tuyên bố sẵn sàng phát hành.

## 21. Dấu hiệu mô hình chưa sẵn sàng

| Phát biểu nghe có vẻ hợp lý | Vì sao chưa đủ |
| --- | --- |
| “Đã có ERD và mọi bảng đều có ID” | Chưa xác định grain và business uniqueness |
| “FK đã có nên CONFIRMED chắc chắn có Line” | FK con → cha không ép cha có con |
| “Để NULL cho linh hoạt” | NULL có thể che trạng thái và dữ liệu thiếu |
| “Cùng một ID ở hai tenant chắc không xảy ra” | Chưa chứng minh phạm vi khóa |
| “Dùng Product.price hiện hành để tính lịch sử” | Sai giá khi Product đổi |
| “Cộng tất cả metric số” | Gauge/snapshot/ratio không luôn additive |
| “SELECT kiểm tra tồn rồi mới UPDATE là an toàn” | Hai request đồng thời có thể oversell |
| “Mỗi shard SERIALIZABLE nên tổng toàn cục cũng đúng” | Không có conflict validation xuyên shard |
| “Dùng dữ liệu từ replica để duyệt đơn” | Replica có thể chậm |
| “Backfill 99% là đủ” | 1% còn lại có thể quan trọng nhất |
| “Nhiều index chắc chắn giúp nhanh” | Chi phí ghi/index bloat và thiếu workload |
| “Backup tồn tại thì rollback dễ” | Dữ liệu mới có thể không chuyển ngược được |
| “Test case đã viết nên PASS” | Chưa có evidence đã thực thi |
| “Được duyệt v1 nên v2 tự động được duyệt” | Điều kiện nghiệp vụ và công nghệ có thể đã đổi |

Một câu phản biện tốt của reviewer là: **“Hãy chỉ ra dữ liệu và lịch chạy cụ thể khiến thiết kế này sai, rồi cho thấy constraint hoặc protocol nào ngăn tình huống ấy.”**

## 22. Bài tập tình huống kèm hướng dẫn giải

### Bài 1. Khóa kỹ thuật nhưng thiếu grain

**Đề bài:** OrderLine có id tự tăng, nhưng chưa biết cùng SKU có thể xuất hiện hai lần trong một Order không. Có thể PASS grain chưa?

**Gợi ý:** Chưa. PK kỹ thuật không xác định “một dòng đại diện điều gì”. Phải chốt nghiệp vụ và khóa/đối soát ở đúng grain.

### Bài 2. Khóa theo tenant

**Đề bài:** Order O-1001 được phép xuất hiện ở hai tenant. UNIQUE(order_code) toàn bảng có hợp lệ không?

**Gợi ý:** Không. Nếu mã chỉ duy nhất theo tenant, dùng UNIQUE(tenant_id,order_code), thử trùng trong tenant bị chặn và trùng khác tenant được phép.

### Bài 3. Bội số theo trạng thái

**Đề bài:** Order DRAFT có thể không Line, CONFIRMED phải có Line. FK Line → Order đã đủ chưa?

**Gợi ý:** Chưa. Cần owner/transaction kiểm tra khi confirm, mọi writer của Line phối hợp, và race test.

### Bài 4. Gửi lại Payment callback

**Đề bài:** Provider gửi callback ba lần với cùng attempt ID. Có thể tạo ba PaymentAttempt mới rồi xử lý sau?

**Gợi ý:** Có thể lưu ba receipt trong audit, nhưng không tạo ba hiệu ứng thanh toán. Unique provider ref và idempotency phải phân biệt retry với event mới.

### Bài 5. Zero và missing

**Đề bài:** Product chưa có giá, nhóm điền unit_price_vnd=0 để đạt NOT NULL. Có PASS không?

**Gợi ý:** Chỉ khi 0 là giá có ý nghĩa được chấp nhận. Thiếu giá phải xử lý khác zero; không gán mặc định giả.

### Bài 6. Bảo mật khác FK

**Đề bài:** FK ghép ngăn OrderLine tham chiếu sai tenant, nhưng API GET Order chỉ lọc order_id. Gate security có đạt không?

**Gợi ý:** Không. Authorization phải dựa trên tenant của người gọi, có test đọc chéo tenant, và có thể dùng DB roles/RLS nếu phù hợp.

### Bài 7. Không biết timezone

**Đề bài:** Nguồn lưu “2026-11-22 08:00” không có offset/timezone. Có đổi ngay sang TIMESTAMPTZ không?

**Gợi ý:** Chưa. Xác định nguồn giờ UTC, giờ cửa hàng hay nguồn khác; nếu không biết cần xử lý ngoại lệ, tránh suy diễn theo timezone session.

### Bài 8. Snapshot tồn kho

**Đề bài:** Snapshot tồn cuối ngày revision 1 = 20, revision 2 = 18. KPI SUM = 38 có đúng không?

**Gợi ý:** Không. Chọn revision hợp lệ mới nhất theo cutoff, không SUM hai phiên bản trạng thái.

### Bài 9. Đua tranh giữ hàng

**Đề bài:** Hai request cùng xin hai chiếc cuối, đều đọc cache còn hai. Lỗi nằm ở gate nào?

**Gợi ý:** Gate F về tính đúng khi cạnh tranh. Cần owner với thao tác reserve atomic và idempotent.

### Bài 10. Quan hệ xuyên service

**Đề bài:** Customer ở DB A, Order ở DB B, tài liệu ghi FK đảm bảo tham chiếu. Chấp nhận được không?

**Gợi ý:** Không nếu không có distributed FK thật sự. Phải ghi logical reference, owner, protocol và orphan reconciliation.

### Bài 11. Sai tiền tệ trong migration

**Đề bài:** amount_text="100" có currency=USD, cột mới là total_amount_vnd BIGINT. Chỉ CAST thành 100 có đạt không?

**Gợi ý:** Không. Cần giữ currency gốc hoặc tỷ giá/nguồn/thời điểm quy đổi; đúng kiểu số chưa đủ đúng đơn vị.

### Bài 12. JOIN làm nhân số

**Đề bài:** Một Order có 3 Line và 2 PaymentAttempt. JOIN trực tiếp rồi SUM PaymentAttempt có thể sai như thế nào?

**Gợi ý:** JOIN tạo 6 hàng, mỗi Attempt có thể bị nhân 3 lần. Aggregate mỗi tập con về một hàng theo tenant/order trước khi JOIN.

### Bài 13. Index theo cảm tính

**Đề bài:** Team tạo index mỗi cột vì bảng sẽ lớn, chưa có workload matrix. Gate vật lý đã PASS chưa?

**Gợi ý:** Chưa. Cần query/access patterns, đo plan và write/storage overhead trên dữ liệu đại diện.

### Bài 14. Backfill xong nhưng writer cũ còn chạy

**Đề bài:** Đã chuyển amount_text sang total_amount_vnd, nhưng batch cũ chỉ ghi amount_text. Có thể DROP cột cũ không?

**Gợi ý:** Chưa. Writer cũ tạo divergence; phải nâng cấp writer/bridge, đối soát và contract khi không còn phụ thuộc.

### Bài 15. Test chưa chạy

**Đề bài:** T11 Confirm/DeleteLastLine đã được lên kế hoạch nhưng chưa thực thi. Reviewer có thể đánh PASS không?

**Gợi ý:** Không. Phải ghi NOT RUN; có thể chấp nhận xây prototype, không GO traffic production nếu đây là invariant P0.

### Bài 16. Không có phê duyệt retention

**Đề bài:** Mọi test SQL đều PASS, nhưng policy retention của dữ liệu cá nhân chưa được phê duyệt. Có thể GO production không?

**Gợi ý:** Không nếu đây là gate bắt buộc. Cần owner/phạm vi rõ và điều kiện chặn phát hành, không chỉ ghi “sửa sau”.

### Bài 17. Chọn graph DB theo sở thích

**Đề bài:** Team chọn graph DB vì Order liên hệ Customer và Product, chưa có query traversal hay thử transaction. Gate công nghệ có PASS không?

**Gợi ý:** Chưa. Phải so mẫu truy cập và khả năng cưỡng chế invariant với relational/document/graph, kèm lý do và thử nghiệm.

### Bài 18. Mở guest checkout sau khi được duyệt

**Đề bài:** v1 yêu cầu Order có Customer, v2 thêm guest và chuyển customer_id nullable. Có cần review lại?

**Gợi ý:** Có. Phải xét discriminator, PII/retention, API, bội số, quyền, báo cáo và lịch sử; thay nullable chưa đủ.

## 23. Ghi nhớ và quyết định cuối cùng

Trước khi ký nghiệm thu, reviewer cần có câu trả lời rõ ràng:

1. **Một bản ghi đại diện điều gì; khóa nào phân biệt nó trong scope nào?**
2. **Bội số và các mối quan hệ thay đổi ra sao theo trạng thái/thời gian?**
3. **Ai bảo vệ các bất biến khi nhiều command chạy đồng thời?**
4. **Các giá trị có đúng kiểu, đơn vị, NULL semantics và thời điểm không?**
5. **Lịch sử và phép tổng hợp có giữ đúng grain, tránh nhân hoặc mất số liệu không?**
6. **Luồng đọc/ghi đáp ứng bảo mật, tải, SLO và khả năng tăng trưởng bằng chứng nào?**
7. **Có thể migration, backfill, replay, restore và xử lý lỗi theo kế hoạch không?**
8. **Test nào đã chạy và test nào chỉ mới được thiết kế?**
9. **Nếu còn vấn đề, có blocker/owner/hạn xử lý và giới hạn rollout minh bạch không?**

**Chấp nhận thiết kế không có nghĩa mô hình hoàn hảo hoặc không cần tiến hóa.** Nó có nghĩa rằng **scope và bất biến đã rõ, các lựa chọn grain/khóa/quan hệ/vòng đời có lý do, cơ chế bảo vệ khả thi, rủi ro còn lại được minh bạch, và mỗi gate trọng yếu có bằng chứng cùng người chịu trách nhiệm**.

Một mô hình đủ điều kiện bước sang triển khai là mô hình mà kỹ sư có thể chuyển thành code không phải tự bịa quy tắc, QA có thể chứng minh đúng/sai bằng tình huống cụ thể, DBA/SRE có thể kiểm chứng chi phí vận hành, và người phụ trách nghiệp vụ có thể khẳng định **dữ liệu được lưu, thay đổi và sử dụng đúng với cam kết của hệ thống**.


