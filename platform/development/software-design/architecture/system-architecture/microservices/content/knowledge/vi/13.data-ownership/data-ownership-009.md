# Quản lý dữ liệu dùng chung và dữ liệu tham chiếu trong Microservices

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Quyền sở hữu dữ liệu.  
> **Mục tiêu:** Phân biệt dữ liệu tham chiếu, dữ liệu chủ, dữ liệu giao dịch và cấu hình; xác định nguồn có thẩm quyền, chủ sở hữu và quyền ghi; lựa chọn cách phân phối qua API, snapshot, cache và event; xử lý phiên bản, thời gian hiệu lực, nhất quán, bảo mật, đồng bộ và migration khỏi shared database.

## 1. Dữ liệu “dùng chung” không đồng nghĩa “cùng được sửa”

Một hệ thống thương mại điện tử thường cần những dữ liệu được nhiều nhóm sử dụng: mã quốc gia, loại tiền tệ, phương thức giao hàng, danh mục sản phẩm, khu vực vận chuyển, loại thuế, nhóm khách hàng hoặc bảng lý do từ chối.

Trong monolith, các module có thể truy cập một bảng chung và JOIN dữ liệu tại chỗ. Khi chuyển sang Microservices, nếu nhiều dịch vụ cùng truy cập SQL trực tiếp, bảng ấy trở thành một điểm coupling:

~~~text
Ordering ----\
Pricing ------> shared_lookup_database
Shipping -----/
Reporting ---/
~~~

Các vấn đề nảy sinh:

- Một service đổi nghĩa một code làm service khác áp sai nghiệp vụ.
- Các nhóm chia sẻ quyền UPDATE mà không có owner rõ ràng.
- Schema migration đòi triển khai đồng bộ nhiều ứng dụng.
- Consumer phải hiểu cột và join private database của provider.
- Lỗi DB hoặc query tốn tài nguyên gây ảnh hưởng đồng thời nhiều capability.
- Không biết ai chịu trách nhiệm sửa một bản ghi sai và phát lại thay đổi.
- Giá trị mới xuất hiện mà consumer cũ không hỗ trợ.
- Giao dịch lịch sử bị diễn giải lại bằng định nghĩa danh mục hiện tại.

Nguyên tắc trung tâm:

**Một thông tin có thể được nhiều service sử dụng nhưng phải có một nơi có thẩm quyền xác định ý nghĩa và một đường ghi được kiểm soát.**

Không bắt buộc mọi tập giá trị phải nằm trong một service ReferenceData riêng. Ranh giới ownership phụ thuộc vào **năng lực nghiệp vụ** và những bất biến cần bảo vệ.

## 2. Bốn loại dữ liệu không nên trộn thành một bảng

| Loại | Bản chất | Ví dụ | Cách nhìn về owner |
|---|---|---|---|
| **Reference data** | Bộ giá trị, phân loại hoặc định nghĩa được dùng lặp lại | Currency, Country, ShippingMethod, ProductCategory | Steward/Domain owner có quyền quản lý code list |
| **Master data** | Thực thể nghiệp vụ có định danh và vòng đời riêng | Customer, Product, Supplier, Warehouse | Service sở hữu capability |
| **Transactional data** | Trạng thái và lịch sử một giao dịch hoặc hành động | Order, Payment, Reservation, Invoice | Service chịu trách nhiệm thực thi transaction |
| **Configuration/policy** | Giá trị điều khiển hành vi ứng dụng hoặc nghiệp vụ | Feature flag, retry limit, discount rule | Platform hoặc domain policy owner |

Một nhóm “order statuses” thường không chỉ là reference table. Quy tắc khi nào DRAFT được chuyển sang CONFIRMED thuộc **Ordering state machine**. Không thể cho một công cụ quản trị chung thêm trạng thái bất kỳ mà không kiểm tra các chuyển trạng thái.

Tương tự, một bảng “discount tiers” có thể chứa vài dòng nhưng nếu quyết định số tiền khách phải trả, nó thuộc **Pricing/Promotion policy**, không phải lookup table vô chủ.

### Phân loại bằng câu hỏi

- Giá trị này chỉ phục vụ nhận diện/hiển thị hay có quy tắc nghiệp vụ phức tạp?
- Có identity và lifecycle riêng không?
- Ai có quyền quyết định giá trị mới được dùng?
- Có transaction nào phải bảo vệ invariant khi cập nhật?
- Có cần dữ liệu hiện hành hay snapshot đã chốt trong quá khứ?
- Giá trị thay đổi có thể ảnh hưởng tiền, quyền truy cập, tuân thủ hoặc vận hành không?

Tên bảng, số lượng dòng hoặc tần suất thay đổi không đủ để xác định owner.

## 3. Những ví dụ cụ thể về quyền sở hữu

| Dataset | Owner gợi ý | Consumer | Điều phải bảo vệ |
|---|---|---|---|
| ProductCategory | Catalog/Merchandising | Search, Product, Analytics | Taxonomy và ý nghĩa category |
| ShippingMethod | Fulfillment | Ordering, Checkout, Support | Method nào được cung cấp ở khu vực nào |
| PaymentMethodType | Payment | Checkout, Billing | Các loại thanh toán hợp lệ |
| Currency display metadata | Reference steward | UI, Reporting | Bộ mã và nhãn |
| PricingTier | Pricing | Sales, Ordering | Quy tắc áp giá |
| Country labels | Reference steward | Address UI, CRM | Tên, mã và locale |
| CustomerSegment | CRM/Customer domain | Campaign, Sales | Ý nghĩa và eligibility |
| WarehouseType | Inventory/Logistics | Inventory, Reporting | Phân loại vận hành kho |
| Retry policy | Service/Platform owner | Runtime | Giới hạn tải và khôi phục |
| OrderStatus | Ordering | Support, Reporting | Vòng đời đơn và transition hợp lệ |

Các owner ở đây chỉ là ví dụ. Tổ chức thực tế phải xem boundary hiện có và ra quyết định rõ ràng.

Một điểm dễ nhầm: **Currency code** và **exchange rate** không nhất thiết cùng owner. Metadata VND/USD có thể là reference data ổn định, trong khi tỷ giá, thời điểm chốt tỷ giá và cách làm tròn là nghiệp vụ tài chính riêng.

## 4. Source of truth, snapshot, projection và cache

Các bản sao của cùng một mã không nhất thiết là nhiều nguồn sự thật.

| Dạng lưu trữ | Ý nghĩa | Ai được ghi? |
|---|---|---|
| **Authoritative dataset** | Định nghĩa chính thức, trạng thái và hiệu lực | Owner được ủy quyền |
| **Consumer snapshot** | Bản phát hành immutable đã chấp nhận | Consumer tải hoặc đồng bộ từ owner |
| **Read projection** | Bản tối ưu truy vấn, join hoặc phân loại | Projection writer theo contract |
| **Cache** | Bản tạm để tăng tốc và giảm dependency | Cơ chế refresh/invalidate |
| **Historical business snapshot** | Giá trị đúng tại thời điểm giao dịch chốt | Service sở hữu giao dịch |
| **Data warehouse copy** | Dữ liệu phục vụ phân tích | Data pipeline quản lý, không sửa transaction nguồn |

Ví dụ giá niêm yết hiện hành do Pricing xác định. Nhưng Ordering lưu giá đã chốt trên đơn tại thời điểm submit. Khi Pricing thay đổi giá mới, **đơn cũ không tự thay đổi**. Hai giá khác nhau có thể cùng đúng vì trả lời hai câu hỏi khác nhau.

Quyền sở hữu luôn gắn với **mệnh đề nghiệp vụ cụ thể**, không chỉ tên field hoặc giá trị trông giống nhau.

## 5. Reference data cũng có vòng đời và thay đổi

Reference data thường thay đổi chậm hơn transactions, nhưng không phải bất biến:

~~~text
DRAFT / PROPOSED
         |
         v
    REVIEWED
         |
         v
     APPROVED
         |
         v
      ACTIVE
         |
         +------> DEPRECATED
         |             |
         |             v
         +----------> RETIRED
~~~

Một mã có thể được thêm, sửa label, điều chỉnh metadata, đổi quan hệ phân cấp, ngừng nhận giao dịch mới hoặc có replacement code.

Cần phân biệt:

- **Label change:** tên hiển thị đổi, semantics giữ nguyên.
- **Metadata change:** mô tả bổ sung có thể thay đổi nhưng không nhất thiết là breaking.
- **Semantic change:** ý nghĩa code thay đổi, có rủi ro lớn với consumer.
- **Deprecation:** code cũ còn hợp lệ trong lịch sử nhưng không dùng cho giao dịch mới.
- **Retirement:** kết thúc vòng đời sử dụng theo chính sách.
- **Correction:** sửa dữ liệu sai, có thể ảnh hưởng kết quả trước đó.

Không đặt giả định “reference data hiếm đổi nên không cần versioning”. Chỉ một dòng sai trong danh mục khu vực giao hàng có thể ảnh hưởng nhiều đơn.

## 6. Vai trò owner, steward, publisher và consumer

| Vai trò | Trách nhiệm |
|---|---|
| **Business owner** | Quyết định ý nghĩa, chính sách sử dụng và tác động nghiệp vụ |
| **Data steward** | Chuẩn hóa code, duyệt thay đổi, chất lượng và lifecycle |
| **Service owner** | Xây API, lưu dữ liệu, backup, migration và availability |
| **Publisher** | Phát hành snapshot/event hoặc query API |
| **Consumer** | Dùng dữ liệu đúng contract, quản lý cache và bản sao |
| **Platform team** | Cung cấp hạ tầng DB, broker, catalog, IAM và observability |
| **Security/privacy** | Phân loại mức nhạy cảm, quyền, retention và auditing |

Một nhóm có thể kiêm nhiều vai trò. Quan trọng là biết **ai có quyền phê duyệt việc đổi nghĩa mã**, ai sửa dữ liệu và ai chịu trách nhiệm khi consumer bị lệch.

Một service catalog nên lưu: dataset, owner, steward, code namespace, API/schema version, publish mechanism, consumer list, SLO, security level, deprecation policy và runbook.

## 7. Chọn owner theo năng lực nghiệp vụ

Ba cách tổ chức phổ biến:

**A. Domain owner trực tiếp sở hữu danh mục.** Fulfillment quản lý shipping methods, Catalog quản lý product categories, Payment quản lý payment types. Dùng khi semantics của danh mục gắn chặt quy tắc domain.

**B. Reference Data capability có steward chung.** Một đội quản trị những code lists chuẩn hóa toàn doanh nghiệp, công bố snapshot/API và kiểm soát phiên bản. Dùng khi dataset thực sự có chung lifecycle và governance.

**C. Versioned dataset/package.** Bộ mã rất ổn định được phân phối như tệp được version/checksum hoặc package runtime. Dùng khi không cần network lookup cho mỗi request và thời gian cập nhật qua deployment được chấp nhận.

Không gom mọi bảng có ít dòng vào một ReferenceDataService khổng lồ. Làm vậy có thể biến nó thành một **God Service** và single point of failure cho nhiều capability.

Không tạo một microservice riêng cho từng bảng chỉ vì nguyên tắc database-per-service. Boundary phải có ý nghĩa nghiệp vụ và chi phí vận hành hợp lý.

## 8. Chỉ một writer có thẩm quyền

Một anti-pattern:

~~~text
Shared DB: lookup_values
  type = SHIPPING_METHOD
  code = STANDARD

Ordering service: UPDATE lookup_values ...
Fulfillment service: UPDATE lookup_values ...
Support tool: UPDATE lookup_values ...
Pricing job: UPDATE lookup_values ...
~~~

Các ứng dụng có thể sửa field của nhau mà không có validation/audit thống nhất.

Thay bằng:

~~~text
Fulfillment Owner
      |
      | command: Propose/Approve/Publish/Deprecate
      v
Authoritative Shipping Method Store
      |
      +---- Query API ------> Ordering / Checkout
      |
      +---- Change Event ---> Local projections
      |
      +---- Snapshot ------> Reporting / offline consumers
~~~

Chỉ service owner hoặc công cụ quản trị được ủy quyền ghi tập dữ liệu có thẩm quyền. Consumer không trực tiếp UPDATE table hoặc dùng credentials superuser của owner.

Đọc SQL trực tiếp cũng có thể tạo coupling với schema và tải database. Nếu dùng trong giai đoạn chuyển tiếp, cần scope, thời hạn loại bỏ và kiểm soát quyền.

## 9. Public code, internal ID và display label

Một record có thể có:

~~~json
{
  "id": "sm-542",
  "code": "STANDARD",
  "displayName": "Giao tiêu chuẩn",
  "status": "ACTIVE",
  "version": 7
}
~~~

- **id:** identity ổn định trong domain.
- **code:** mã được công bố trong API và data contracts.
- **displayName:** nhãn cho con người, thay đổi theo locale.
- **status:** ACTIVE/DEPRECATED/RETIRED theo contract.
- **version:** bản sửa đổi có ý nghĩa.

Client không nên xử lý nghiệp vụ bằng so sánh displayName hoặc dùng enum ordinal. Label có thể chuyển từ “Giao tiêu chuẩn” thành “Giao thường” mà identity không đổi.

Nếu code đã được nhiều consumer lưu và truyền, việc đổi code có thể là breaking change. Có thể dùng alias và deprecation, nhưng phải kiểm tra ngữ nghĩa tương đương thực sự.

## 10. Namespace và uniqueness của code

Một code “STANDARD” có thể tồn tại trong shipping methods và customer levels với nghĩa hoàn toàn khác nhau.

Nên định nghĩa identity theo:

~~~text
dataset / namespace
+ scope (global, tenant, region)
+ code
+ effective period (nếu có)
~~~

Ví dụ:

~~~text
shipping-method:GLOBAL:STANDARD
customer-tier:tenant-A:STANDARD
~~~

Không nối các phần tùy tiện nếu dấu phân cách có thể xuất hiện trong input; dùng encoding/escaping hoặc cấu trúc được chuẩn hóa. Cần xác định code phân biệt chữ hoa/thường và quy tắc Unicode normalization.

Nếu code là public contract, không dùng DB auto-increment ID đơn thuần khi việc di chuyển storage có thể làm ID thay đổi. Có thể sử dụng opaque stable ID, và public code với versioning phù hợp.

## 11. Dữ liệu tham chiếu không phải chỉ là một tập enum

Một shipping method có thể chứa:

~~~json
{
  "code": "EXPRESS",
  "status": "ACTIVE",
  "supportedRegions": ["REGION_A", "REGION_B"],
  "validFrom": "2026-11-20T00:00:00Z",
  "validTo": null,
  "labels": {
    "vi-VN": "Giao nhanh",
    "en-US": "Express delivery"
  }
}
~~~

Nhưng việc **đơn nào đủ điều kiện EXPRESS** có thể cần tính theo địa chỉ, trọng lượng, loại hàng, công suất vận hành và giờ cutoff. Đó là một quyết định nghiệp vụ của Fulfillment, không chỉ thao tác đọc một enum.

API liệt kê options có thể phục vụ UI; command tạo shipment hoặc query GetEligibleDeliveryOptions vẫn cần owner kiểm tra quy tắc trong context hiện tại.

## 12. Thiết kế schema có version và thời gian hiệu lực

Một bản ghi tham chiếu hữu ích có thể gồm:

| Trường | Mục đích |
|---|---|
| datasetId | Định danh tập dữ liệu |
| recordId | Identity bất biến của record |
| code | Mã tích hợp |
| status | ACTIVE/DEPRECATED/RETIRED |
| labels | Nhãn theo locale |
| description | Nghĩa nghiệp vụ |
| recordVersion | Phiên bản record |
| datasetVersion | Phiên bản tập công bố |
| schemaVersion | Kiểu representation |
| validFrom/validTo | Thời gian hiệu lực nghiệp vụ |
| createdAt/updatedAt | Thời gian hệ thống ghi |
| replacedBy | Mã thay thế, nếu có |
| parentId | Quan hệ phân cấp |
| ownerReference | Trách nhiệm và audit |
| attributes | Metadata có schema riêng |

Không nhét tất cả trường vào generic table với value1/value2/json mà không có validation. Mỗi dataset có thể có schema/domain DTO riêng trong khi dùng chung metadata convention.

### SQL minh họa

~~~sql
CREATE TABLE reference_method_versions (
    method_id VARCHAR(80) NOT NULL,
    code VARCHAR(50) NOT NULL,
    business_version BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP NULL,
    display_label VARCHAR(255) NOT NULL,
    PRIMARY KEY (method_id, business_version),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

Cần ràng buộc bổ sung để tránh hai phiên bản cùng code/scope có **khoảng thời gian hiệu lực chồng lấn** nếu domain cấm. CHECK trên từng dòng không tự chặn overlap giữa hai dòng; có thể dùng exclusion constraint hoặc transaction validation theo DB thực tế.

## 13. Effective dating: dữ liệu đúng tại thời điểm nào?

Ví dụ một shipping zone thay đổi vào ngày 20/11:

~~~text
Version 4: valid until 2026-11-20
Version 5: valid from 2026-11-20
~~~

Một đơn đặt trước mốc đó nhưng giao sau mốc đó nên áp phiên bản nào? Phải hỏi domain owner.

Các lựa chọn:

- Phiên bản có hiệu lực khi khách tạo yêu cầu.
- Phiên bản khi quote được chốt.
- Phiên bản lúc thực hiện fulfillment.
- Phiên bản được pin xuyên workflow.
- Một quy tắc migration cụ thể cho đơn đang chờ.

Không suy từ updatedAt rằng đó là business effective time. Các thay đổi có thể được **công bố trước ngày hiệu lực**, hoặc được sửa hồi tố sau khi phát hiện sai.

Nếu dữ liệu ảnh hưởng tính tiền, hạn mức hoặc trạng thái hợp đồng, lưu snapshot/version trên transaction để không tự đổi nghĩa lịch sử.

## 14. Bitemporal: valid time khác recorded time

Hai mốc có thể cần phân biệt:

1. **Valid time:** khi bản ghi có hiệu lực trong nghiệp vụ.
2. **System/transaction time:** khi hệ thống thực sự ghi nhận thông tin đó.

Ví dụ ngày 15/11 mới phát hiện một quy tắc đáng lẽ có hiệu lực ngày 01/11. Correction record có thể được ghi ngày 15/11 nhưng validFrom là 01/11.

Nhờ phân biệt hai thời gian, có thể trả lời:

- Theo dữ liệu đã sửa, quy tắc nào đúng vào 05/11?
- Ngày 05/11 hệ thống khi ấy đã tin điều gì?
- Giao dịch nào bị ảnh hưởng và cần đối soát?

Không phải bộ mã đơn giản nào cũng cần bitemporal database. Chỉ dùng khi yêu cầu audit, đối soát hoặc semantics lịch sử thực sự biện minh cho độ phức tạp đó.

## 15. Snapshot lịch sử không phải bản sao sai

Ví dụ Order lưu:

~~~json
{
  "orderId": "O-101",
  "shippingMethodCode": "STANDARD",
  "shippingMethodVersion": 7,
  "shippingMethodLabelSnapshot": "Giao tiêu chuẩn",
  "shippingFeeSnapshot": {
    "amount": "35000",
    "currency": "VND"
  },
  "acceptedAt": "2026-11-01T10:00:00Z"
}
~~~

Ngày mai label STANDARD thay đổi. Ordering không nên tự cập nhật phí và label đã chốt nếu contract yêu cầu chứng cứ lịch sử.

Để báo cáo, cần phân biệt:

- Doanh thu phân loại theo taxonomy **tại thời điểm bán**.
- Doanh thu được quy đổi theo taxonomy **hiện hành**.

Hai phép tính có thể hợp lệ nhưng trả lời câu hỏi khác nhau. Thiết kế dữ liệu phải giữ được semantics chứ không chỉ bảo đảm mọi bảng có cùng giá trị mới nhất.

## 16. Dữ liệu phân cấp và taxonomy

Product categories, geographic zones và organization units có quan hệ cây hoặc đồ thị:

~~~text
Electronics
  |
  +-- Computers
  |      |
  |      +-- Laptops
  |
  +-- Audio
         |
         +-- Headphones
~~~

Cần xác định:

- Một node có thể có nhiều parent hay chỉ một?
- Có cấm cycle và giới hạn depth không?
- Đổi parent có giữ node identity không?
- Một node có effective period hay không?
- Consumer cần full tree, breadcrumb hay descendant lookup?
- Phân loại lịch sử có dùng taxonomy lúc bán không?
- Một code bị merge hoặc split thì các references cũ được xử lý thế nào?

Một công ty có thể dùng taxonomy hiển thị sản phẩm và classification cho tài chính, với hai owner và hai semantics khác nhau. Không ép chúng thành một cây “chung cho mọi phòng ban” nếu điều đó đánh mất nhu cầu nghiệp vụ.

## 17. Đa ngôn ngữ và đa khu vực

Một code có thể có labels:

~~~json
{
  "code": "STANDARD",
  "labels": {
    "vi-VN": "Giao tiêu chuẩn",
    "en-US": "Standard delivery"
  }
}
~~~

Contract cần nêu:

- Locale format và fallback khi thiếu bản dịch.
- Nhãn có thể thay đổi độc lập với mã không?
- Display metadata có cache theo locale không?
- Label nào là legal copy và phải version riêng?
- Có country/region availability tách với language preference không?
- Có sử dụng dữ liệu nhạy cảm theo khu vực không?

Không dùng label tiếng Việt làm business key. Consumer có thể bản địa hóa bằng code ổn định, nhưng không được suy business eligibility từ tên hiển thị.

## 18. Multi-tenancy: global default và tenant override

Một ứng dụng SaaS có:

~~~text
Global methods:
  STANDARD
  EXPRESS

Tenant A:
  enabled = STANDARD only

Tenant B:
  enabled = both
  custom display label for EXPRESS
~~~

Phân biệt:

- Định nghĩa global của code và semantics.
- Tenant được bật/tắt option nào.
- Tenant-specific override nào được phép (label, cutoff, preference).
- Một extension code riêng của tenant có được hỗ trợ không.
- Quyền ai được thay đổi cấu hình tenant.

Một cache key chỉ có dataset=shipping-methods có thể trả dữ liệu Tenant A cho Tenant B. Cache cần phân biệt tenant/scope, locale, filters và policy version khi response thay đổi theo các chiều đó.

Không tin tenantId trong payload tự do thay cho authorization. Owner phải kiểm tra workload identity, tenant scope và quyền sử dụng reference record.

## 19. Business policy khác danh mục

CustomerTier có thể gồm SILVER, GOLD, PLATINUM. Đó là một danh mục. Nhưng quy tắc ai đủ điều kiện GOLD và chiết khấu bao nhiêu thuộc domain chính sách.

Một thiết kế nguy hiểm:

~~~text
Checkout reads tier = GOLD
Checkout assumes discount = 20%
Checkout calculates final price
~~~

nếu Pricing đang sở hữu discount policy. Tốt hơn:

~~~text
CRM provides customer segment
Pricing calculates quote using current policy
Ordering stores accepted quote snapshot
~~~

Một reference value có thể là input của một quy tắc, không tự trở thành toàn bộ quy tắc. Nếu consumer phải tự viết lại cùng business logic, quyền sở hữu năng lực nghiệp vụ bị phân tán.

## 20. Cách phân phối reference data

| Phương án | Phù hợp | Đổi lại |
|---|---|---|
| **Sync API** | Cần dữ liệu mới, query động hoặc owner validation | Network latency và dependency |
| **Local cache** | Truy vấn nhiều, stale budget có thể chấp nhận | Invalidation và stampede |
| **Immutable snapshot** | Danh mục tương đối nhỏ, cần một release nhất quán | Download/activation version |
| **Change event** | Nhiều consumer cần cập nhật gần realtime | Duplicate, lag, ordering, gap |
| **Versioned package** | Dữ liệu rất ổn định, cập nhật theo deploy | Version drift giữa applications |
| **Read projection** | Query tổng hợp hoặc UI cần dữ liệu từ nhiều owners | Eventual consistency |
| **CDC bridge** | Di chuyển dữ liệu từ legacy DB | Coupling schema, không nên dùng mãi |

Chọn theo freshness, reliability, số consumer, kích thước dataset, tần suất thay đổi và rủi ro stale. Không dùng một ReferenceData HTTP service trong hot path của mọi request chỉ vì tất cả code lists “nằm chung”.

## 21. Sync API và HTTP cache semantics

Một endpoint danh mục:

~~~http
GET /v1/reference-data/shipping-methods?locale=vi-VN
Accept: application/json
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "shipping-methods-v17-viVN"
Cache-Control: private, max-age=300

{
  "dataset": "shipping-methods",
  "datasetVersion": 17,
  "items": [
    {"code": "STANDARD", "label": "Giao tiêu chuẩn", "status": "ACTIVE"},
    {"code": "EXPRESS", "label": "Giao nhanh", "status": "ACTIVE"}
  ]
}
~~~

Client gửi:

~~~http
GET /v1/reference-data/shipping-methods?locale=vi-VN
If-None-Match: "shipping-methods-v17-viVN"
~~~

Nếu representation không đổi, server có thể trả **304 Not Modified**. ETag giúp giảm băng thông, nhưng phải phản ánh đủ các chiều làm response thay đổi: locale, tenant, permission, filters, data version và trường được phép hiển thị.

Cache-Control public/private phải phù hợp tính nhạy cảm; không cache thông tin tenant riêng trong shared cache nếu không có partition/access control an toàn.

**ETag của HTTP representation không mặc nhiên là business policy version.** Cần đặt tên và mục đích riêng cho những loại version khác nhau.

## 22. Không dùng danh mục global để thay quyết định nghiệp vụ

GET /shipping-methods có thể trả mọi loại phương thức được định nghĩa. Nhưng Checkout cần **options hợp lệ cho đơn cụ thể**.

Ví dụ:

~~~http
POST /v1/delivery-options/quote
Content-Type: application/json

{
  "deliveryAddressId": "A-90",
  "items": [
    {"sku": "BOOK-21", "quantity": 2}
  ]
}
~~~

Fulfillment/Pricing owner kiểm tra vị trí, trọng lượng, hàng hóa, năng lực vận chuyển và chính sách giá. Trả eligible options hoặc quote với thời hạn.

Khi submit order, owner kiểm tra quote/version còn hiệu lực. Frontend không được đưa code=EXPRESS từ cache cũ rồi tự kết luận giao hàng hợp lệ.

API danh mục giải quyết **nhận diện dữ liệu**, không tự giải quyết **ra quyết định domain**.

## 23. Cache: TTL là quyết định về độ mới dữ liệu

Các lựa chọn cache:

- Local in-memory cache, Redis hoặc snapshot file.
- Read-through load khi miss.
- Refresh-ahead trước khi TTL hết.
- ETag conditional fetch.
- Invalidation qua change event.
- Coalescing để tránh stampede khi nhiều request cùng miss.
- Stale-while-revalidate cho dữ liệu không nhạy cảm.
- Stale-if-error trong một cửa sổ đã công bố.
- Cache warming khi deploy.

Các tham số cần định nghĩa:

| Tham số | Ý nghĩa |
|---|---|
| Fresh TTL | Trong bao lâu cache được coi là mới |
| Maximum stale age | Tuổi tối đa cho phép trả dữ liệu cũ |
| Refresh interval | Chu kỳ cập nhật |
| Cache key scope | Dataset, tenant, locale, version, query |
| Negative cache TTL | Bao lâu được nhớ rằng code không tồn tại |
| Refresh timeout | Deadline gọi nguồn |
| Eviction policy | Khi bộ nhớ đầy |
| Failure fallback | Khi owner unavailable |

TTL=24 giờ có thể phù hợp hiển thị label nhưng không phù hợp khi một payment method bị disable khẩn cấp. **Không dùng một TTL toàn hệ thống cho mọi dataset.**

## 24. Stale cache: có thể và không thể

| Tác vụ | Có thể dùng dữ liệu cũ? | Ghi chú |
|---|---|---|
| Hiển thị tên quốc gia | Thường có | Chủ yếu UI |
| Hiển thị category label | Có trong hạn mức | Không ra quyết định kinh doanh từ stale |
| Xem order snapshot đã chốt | Có | Snapshot giữ ý nghĩa lịch sử |
| Tính shipping fee cuối | Không nên dựa riêng cache | Cần quote của owner |
| Quyết định quyền refund | Không | Domain owner xác nhận |
| Kiểm tra tenant permissions | Hạn chế nghiêm ngặt | Theo security consistency policy |
| Analytics theo taxonomy cũ | Có nếu cố ý | Ghi rõ historical vs current |
| Chọn phương thức giao hàng | Có cho UI, không đủ cho submit | Owner validate khi command |

Nếu cache unavailable, service có thể degrade read-only, dùng last-known-good, fail closed hoặc ghi operation pending. Chính sách fallback phải đi theo hậu quả nghiệp vụ, không chỉ kỳ vọng availability.

## 25. Versioned snapshot và atomic activation

Với danh mục có 1.000 dòng, owner có thể công bố:

~~~json
{
  "dataset": "shipping-methods",
  "datasetVersion": 18,
  "schemaVersion": 2,
  "generatedAt": "2026-11-11T10:00:00Z",
  "effectiveFrom": "2026-11-20T00:00:00Z",
  "checksum": "sha256-canonical-dataset-content",
  "items": [
    {"code": "STANDARD", "status": "ACTIVE"},
    {"code": "EXPRESS", "status": "ACTIVE"}
  ]
}
~~~

Consumer nên:

1. Tải snapshot vào nơi tạm.
2. Kiểm tra checksum/signature nếu có, schema, kích thước và version.
3. Validate code uniqueness và quan hệ tham chiếu.
4. Lưu bản phát hành mới bền vững nếu cần.
5. Kích hoạt bằng **atomic pointer swap** khi đến effective time.
6. Ghi active version và freshness metric.
7. Duy trì rollback pointer/historical version trong retention hợp lý.

Tránh update từng record vào cache đang phục vụ traffic khiến một request thấy nửa dataset cũ, nửa dataset mới. **Atomic snapshot swap** là cơ chế đơn giản giúp bảo vệ tính nhất quán của một bản phát hành.

## 26. Incremental events, dedup và gap detection

Một event:

~~~json
{
  "eventId": "refevt-920",
  "eventType": "ReferenceDatasetPublished",
  "dataset": "shipping-methods",
  "schemaVersion": 2,
  "datasetVersion": 18,
  "occurredAt": "2026-11-11T10:00:00Z",
  "publisher": "fulfillment-service"
}
~~~

Consumer nhận event và tải snapshot v18 hoặc áp delta theo contract.

Rủi ro:

- Event được giao trùng.
- Consumer nhận v19 trước v18.
- Version v18 bị thiếu do lỗi pipeline.
- Retry v17 xuất hiện sau v19.
- Dữ liệu đã được publish trước khi snapshot sẵn sàng.
- Consumer chỉ subscribe một phần events nhưng giả định version liên tục.

Biện pháp:

- Idempotency theo eventId/datasetVersion.
- Không ghi đè snapshot mới bằng version cũ.
- Phát hiện version gap theo sequence thực sự được contract bảo đảm.
- Re-fetch full snapshot từ owner khi cần.
- Có retention, replay và reconciliation.
- Phân biệt schema version với dataset version.
- Monitor outbox lag, broker lag và active version theo consumer.

Sự kiện cập nhật là **tín hiệu phân phối**, không phải lý do để consumer tự tạo nguồn ghi mới.

## 27. Transactional Outbox cho publication đáng tin

Tình huống lỗi:

~~~text
Reference DB commits datasetVersion=18
Message broker publish fails
Consumers remain at v17
~~~

Outbox pattern:

~~~text
BEGIN TRANSACTION
  Update authoritative records
  Increase dataset version
  Insert outbox event: DatasetVersionPublished(18)
COMMIT

Dispatcher:
  Publish event
  Mark outbox as published
~~~

Publisher có thể phát trùng khi broker ACK nhưng dispatcher crash trước mark-published. Consumer phải idempotent. Nếu nhiều dispatchers hoạt động song song, cần đảm bảo event ordering per dataset khi consumer phụ thuộc sequence.

Một bản cập nhật lớn nên được publish như **một dataset release nhất quán** thay vì đẩy hàng trăm record delta không có atomic activation, nếu business yêu cầu các bản ghi thay đổi cùng lúc.

## 28. ReferenceData API ghi phải có workflow

Một API generic PUT /lookup/{type}/{code} cho mọi service rất dễ bypass governance.

Ví dụ đề xuất phương thức giao hàng mới:

~~~http
POST /v1/shipping-method-proposals
Content-Type: application/json

{
  "code": "SAME_DAY",
  "displayName": "Giao trong ngày",
  "requestedEffectiveFrom": "2026-11-20T00:00:00Z",
  "reason": "Fulfillment capacity expanded"
}
~~~

Tùy mức độ ảnh hưởng, có các hành vi:

~~~text
Propose
  |
  v
Validate
  |
  v
Approve
  |
  v
Build versioned dataset
  |
  v
Publish
  |
  v
Monitor consumer adoption
~~~

Nếu danh mục đơn giản, CRUD có validation/audit có thể đủ. Nhưng với code có tác động hàng nghìn giao dịch, cần approval, effective date và rollback policy.

Không để một Admin UI sửa trực tiếp database của nhiều service chỉ vì người dùng có quyền quản trị giao diện.

## 29. Dataset release phải có tính tương thích

Các thay đổi thường tương thích hơn:

- Thêm nhãn tùy chọn.
- Thêm metadata mới với default rõ.
- Thêm code mới khi consumers chịu được unknown values.
- Thêm một API/query mới.
- Cải thiện implementation storage mà không đổi public semantics.

Các thay đổi có nguy cơ phá consumer:

- Đổi nghĩa một code đang được dùng.
- Xóa code trong historical references.
- Đổi unit, precision hoặc format identifier.
- Đổi status semantics.
- Thêm giá trị enum khi client dùng exhaustive switch không có fallback.
- Đổi validFrom làm thay đổi hành vi của transaction đang chờ.
- Đổi key normalization, namespace hoặc cách lập compound ID.
- Thay field bắt buộc hoặc xóa field cũ quá sớm.

Versioning không chỉ là tăng một số. Cần consumer impact analysis, contract tests, deprecation notice, telemetry và migration plan.

## 30. Deprecation và alias

Một code cũ có thể đi theo:

~~~text
ACTIVE
  |
  v
DEPRECATED
  |
  v
RETIRED
  |
  v
ARCHIVED (if allowed by retention policy)
~~~

Khi thay code:

1. Công bố code mới và semantics.
2. Xác định code cũ có thực sự tương đương không.
3. Giữ historical decoding trong thời gian cần thiết.
4. Cho phép hoặc cấm tạo giao dịch mới với code cũ theo policy.
5. Hỗ trợ alias/mapping có thời hạn khi phù hợp.
6. Theo dõi consumer nào còn gửi old code.
7. Có sunset date hoặc criteria.
8. Kiểm tra ảnh hưởng tới reports, ETL, warehouse và snapshots.
9. Không tự đổi code trên transaction đã chốt mà thiếu migration nghiệp vụ.

Một code không còn active có thể vẫn **phải đọc được mãi trong hồ sơ lưu giữ**. Ngừng cho phép sử dụng mới khác với xóa hoàn toàn lịch sử.

## 31. Chất lượng dữ liệu trước khi phát hành

Các validation phổ biến:

- Code không rỗng, đúng pattern và unique theo scope.
- Không có hai bản ACTIVE xung đột trong cùng effective period.
- validFrom trước validTo.
- Parent code tồn tại, không có cycle trong taxonomy.
- ReplacedBy không tạo vòng thay thế.
- Đủ nhãn bắt buộc theo locale.
- Enum/code mới không phá consumer quan trọng.
- Effective dating tuân thủ policy.
- Không có PII/secret vô tình được xuất bản.
- Có owner, approver, audit reference.
- Checksum/schema serialization nhất quán.
- Business policy có integration/contract tests phù hợp.

Một dataset 30 dòng có thể gây thiệt hại lớn nếu chứa sai shipping fee classification. Data quality phải được xem như một phần của **release pipeline**, không chỉ thao tác nhập liệu.

## 32. Reconciliation khi các bản sao bị lệch

Một consumer bị mất DatasetPublished v18, hiện ở v17 trong khi owner đã v19.

Một quy trình:

~~~text
Consumer reports active datasetVersion
Owner reports published datasetVersion
         |
         v
Compare version and checksum
         |
         +--> equal: healthy
         |
         +--> mismatch:
                fetch canonical snapshot
                validate
                atomically replace local version
                record reconciliation outcome
~~~

Không chỉ so số dòng. Hai datasets có cùng 100 records vẫn có thể khác status, effective period hoặc parent hierarchy.

Với dataset rất lớn, dùng partition checksums và incremental backfill. Với dataset vừa/nhỏ, định kỳ tải full snapshot thường đơn giản hơn xây CDC phức tạp.

Một hệ thống đáng tin phải có cách **khôi phục dữ liệu từ authority**, không chỉ kỳ vọng stream events không bao giờ thiếu.

## 33. Java/Spring Boot: query API và ETag

DTO minh họa:

~~~java
import java.util.List;

public record ReferenceItem(
    String code,
    String label,
    String status,
    long recordVersion
) {}

public record DatasetResponse(
    String dataset,
    long datasetVersion,
    List<ReferenceItem> items
) {}
~~~

Controller:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/reference-data")
public final class ReferenceController {
    private final ReferenceQueryService query;

    public ReferenceController(ReferenceQueryService query) {
        this.query = query;
    }

    @GetMapping("/{dataset}")
    public ResponseEntity<DatasetResponse> get(
            @PathVariable String dataset,
            @RequestParam(defaultValue = "vi-VN") String locale,
            @RequestHeader(
                value = "If-None-Match",
                required = false
            ) String currentEtag) {

        DatasetResponse data = query.publishedDataset(dataset, locale);
        String etag = "\"" + dataset + "-" +
            data.datasetVersion() + "-" + locale + "\"";

        if (etag.equals(currentEtag)) {
            return ResponseEntity.status(304).eTag(etag).build();
        }
        return ResponseEntity.ok().eTag(etag).body(data);
    }
}
~~~

Đây là skeleton, chưa gồm auth, tenant scope, schema validation và cache-control. Production phải đảm bảo ETag phản ánh **đúng representation của từng locale/tenant và mọi field liên quan**. Nếu một label thay đổi nhưng datasetVersion không tăng, ETag này không còn hợp lệ. Có thể dùng hash của canonical representation.

Không gọi public API ở mỗi phép tra cứu nội bộ nếu local snapshot có đủ freshness và contract cho phép.

## 34. Java: atomic local snapshot

~~~java
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

public record ReferenceSnapshot(
    long version,
    Map<String, ReferenceItem> values
) {}

public final class ReferenceCache {
    private final AtomicReference<ReferenceSnapshot> current =
        new AtomicReference<>(
            new ReferenceSnapshot(0, Map.of())
        );

    public ReferenceItem find(String code) {
        return current.get().values().get(code);
    }

    public long currentVersion() {
        return current.get().version();
    }

    public boolean activate(ReferenceSnapshot next) {
        ReferenceSnapshot prev = current.get();
        if (next.version() <= prev.version()) {
            return false;
        }
        return current.compareAndSet(prev, next);
    }
}
~~~

AtomicReference giúp tránh đọc bản cache đang bị cập nhật nửa chừng. Nhưng để dùng production cần:

- Map bất biến hoặc defensive copy.
- Validate checksum/schema trước activate.
- Giữ version bằng durable store nếu cần qua restart.
- Retry khi compareAndSet thất bại do concurrent refresh.
- Effective date activation, không kích hoạt bản future sớm.
- Tenant/locale cache isolation.
- Stale policy, metrics và refresh backoff.
- Không để local cache thay authority của domain command.

Mẫu code chỉ minh họa cơ chế atomically switching một snapshot trong process; không tự cung cấp distributed coordination cho toàn hệ thống.

## 35. Multi-service ví dụ: phương thức giao hàng

Giả sử:

- Fulfillment sở hữu ShippingMethod và DeliveryZone.
- Pricing sở hữu ShippingQuote.
- Ordering sở hữu Order snapshot và lifecycle.
- Billing sở hữu Invoice.

Luồng:

~~~text
Client requests eligible options
             |
             v
      Fulfillment owner
             |
             v
    Client selects method
             |
             v
      Ordering SubmitOrder
          /     |     \
         v      v      v
    Pricing  Fulfillment  Payment
     quote    capacity     auth
         \      |      /
              v
         OrderConfirmed
              |
              v
            Billing
~~~

Nếu EXPRESS bị tạm disable:

- UI cache có thể vẫn thấy EXPRESS trong một khoảng cho phép.
- Fulfillment phải reject command không hợp lệ.
- Ordering không tự ghi EXPRESS=ACTIVE để “giúp” user.
- Order cũ đã chốt giữ reference snapshot theo contract.
- Billing không thay invoice quá khứ khi current label đổi.
- Consumer projection phải refresh khi nhận version mới.

Reference data dùng chung không làm biến mất ownership của từng business capability.

## 36. Migration khỏi shared lookup table

Một hệ monolith có bảng lookup_values chứa COUNTRY, SHIPPING, CURRENCY, PRODUCT_CATEGORY, CUSTOMER_TIER và RETRY_POLICY.

Lộ trình:

1. **Inventory:** liệt kê types, rows, owner candidates, SQL readers/writers, business usage.
2. **Classify:** phân biệt reference, master, business policy và technical config.
3. **Assign ownership:** business steward và service chịu trách nhiệm writer.
4. **Define contract:** ID, code, status, version, temporal semantics, auth.
5. **Single writer:** chuyển write path sang owner; dừng quyền sửa tùy ý từ consumers.
6. **Backfill:** tải dữ liệu sang storage mới, bảo lưu mapping legacy codes.
7. **Publish:** API/snapshot/event; dùng outbox nếu cần reliable propagation.
8. **Shadow reads:** so sánh nguồn mới và cũ mà chưa đổi quyết định nghiệp vụ.
9. **Cutover:** chuyển consumers từng nhóm, đo mismatch/stale/error.
10. **Revoke legacy grants:** cấm direct writes, giảm dần direct reads.
11. **Retire bridge:** loại bỏ bảng cũ và CDC path theo kế hoạch.
12. **Operate:** monitoring, contract tests, reconciliation, ownership catalog.

Không để hai nơi cùng authoritative write khi cutover trừ khi có conflict/transaction protocol được thiết kế rõ. **Một writer chính tại mỗi thời điểm** giảm đáng kể nguy cơ data drift.

## 37. CDC là cầu nối, không phải API hợp đồng lý tưởng

Change Data Capture có thể chuyển thay đổi legacy table sang broker:

~~~json
{
  "table": "lookup_values",
  "operation": "UPDATE",
  "before": {"type": "SHIPPING", "value1": "STANDARD"},
  "after": {"type": "SHIPPING", "value1": "EXPRESS"}
}
~~~

Consumer sẽ phải hiểu schema nội bộ value1, type. Khi owner đổi storage, mọi consumer có thể hỏng.

Dùng CDC có kiểm soát cho migration hoặc pipeline chuyên biệt. Sau khi domain owner ổn định, ưu tiên **semantic events** như ShippingDatasetPublished hoặc ShippingMethodDeprecated với schema/version và contract cụ thể.

Nếu legacy history không có validFrom/validTo, không bịa quá khứ khi chuyển đổi. Đánh dấu nguồn và mức tin cậy, dùng audit log/historical evidence khi có.

## 38. Privacy, security và tenant isolation

Reference data có thể có thông tin nhạy cảm: customer risk categories, fraud reasons, vùng hoạt động chưa công bố hoặc tenant-specific entitlements.

Yêu cầu:

- Phân loại public/internal/confidential/restricted.
- Authentication/authorization cho mọi query và write.
- Tenant-aware filtering và cache partitioning.
- Least-privilege quyền đọc, propose, approve, publish, rollback.
- Encrypt in transit/at rest khi cần.
- Audit ai sửa code nào, version và thời điểm.
- Retention cho snapshots, event logs, DLQ, caches và backups.
- Không đưa secrets hoặc API tokens vào “shared config” public.
- Không cho frontend quyết định rule bảo mật từ một enum stale.
- Kiểm thử cross-tenant cache leakage và field-level access.

Data catalog chỉ giúp discover dữ liệu, không tự cấp quyền đọc. Platform quản trị hạ tầng không mặc nhiên sở hữu semantics của dataset.

## 39. Failure scenario: catalog bị phát hành sai

Người quản trị thay đổi ShippingZone làm 10.000 đơn mới bị báo sai phí.

Khôi phục cần:

1. Xác định dataset version, changed records và thời gian có hiệu lực.
2. Dừng publication mới nếu nguồn lỗi.
3. Xuất bản correction version hoặc rollback release với quy trình rõ.
4. Invalidate/refresh consumer caches.
5. Đánh giá giao dịch đã phát sinh trong khoảng sai.
6. Thực hiện data repair/compensation nếu domain quyết định cần.
7. Đo mức phục hồi theo datasetVersion, error rate và business outcomes.
8. Giữ audit trail, không xóa dấu vết sai.
9. Thêm validation/approval/contract tests để tránh lặp.

**Rollback data không giống rollback code.** Hành vi nghiệp vụ đã xảy ra có thể không tự đảo khi reference code trở về giá trị cũ.

## 40. Failure scenario: một consumer mất event

Owner đã phát v21, Search projection mới ở v19.

- Đọc active version và checksum.
- Kiểm tra outbox/broker/consumer lag.
- Replay v20/v21 nếu còn lịch sử và semantics cho phép.
- Nếu thiếu event, tải canonical snapshot v21.
- Validate và swap atomically.
- Đo freshness age và SLO phục hồi.
- Không tự sửa owner DB từ phía Search.
- Với client critical, có thể fail closed khi stale vượt budget.

Một dashboard “service healthy” chưa đủ; cần metric **consumer version lag**.

## 41. Failure scenario: cache trộn tenants

Cache key:

~~~text
shipping-methods:vi-VN
~~~

không đủ nếu Tenant A và Tenant B có enablement khác nhau.

Phải xét:

~~~text
dataset
+ tenant scope
+ locale
+ authorization or eligibility dimensions
+ dataset/policy version
~~~

Không nhất thiết mọi chiều đều cần trong key, nhưng tất cả biến nào làm response khác phải được xử lý. Cùng với cache key, service vẫn phải thực hiện authorization; biết ID hoặc code không đồng nghĩa có quyền truy cập dữ liệu tenant.

Test cache hit, miss, refresh, eviction và concurrent requests từ nhiều tenants.

## 42. Observability và SLO

Các tín hiệu nên có:

| Metric | Mục đích |
|---|---|
| publishedDatasetVersion | Bản mới nhất ở owner |
| consumerActiveVersion | Mức độ cập nhật của consumer |
| versionAdoptionLag | Chậm đồng bộ bao lâu |
| snapshotAge | Tuổi dữ liệu đang sử dụng |
| refreshFailures | Đường đồng bộ đang lỗi |
| checksumMismatch | Bản sao lệch dù version có vẻ đúng |
| invalidCodeRate | Client gửi mã lạ hoặc lỗi thời |
| deprecatedCodeUsage | Consumer chưa migration |
| publicationLeadTime | Quy trình duyệt và phát hành |
| outbox/brokerLag | Event đến trễ |
| cacheHit/staleServeRate | Hiệu quả và rủi ro stale |
| contractCompatibilityFailures | Breaking changes |
| businessRejectionRate | User bị từ chối vì reference stale |

SLO minh họa:

~~~text
99.9% critical consumers apply a published
ShippingMethod dataset within 60 seconds.

99.9% of reference API reads succeed within
the agreed latency budget.

All new shipping commands are validated
against effective rules by the authoritative capability.
~~~

Đây là ngưỡng ví dụ, không phải chuẩn áp dụng cho mọi hệ thống. Chọn theo business deadline và năng lực vận hành.

Không gắn raw userId/orderId/tenantId làm metric labels bùng cardinality; dùng aggregate metrics và logs/traces có quyền truy cập phù hợp.

## 43. Contract testing và data quality testing

Test cần có:

- API schema và code type compatibility.
- Consumer xử lý unknown code/new optional fields.
- Validation duplicate code, overlapping time periods.
- Hierarchy cycle, missing parent và replacedBy loops.
- Locale fallback và nhãn bắt buộc.
- Tenant isolation khi cache hit.
- Outbox publish failure rồi retry/duplicate event.
- Consumer nhận dataset v19 trước v18.
- Snapshot refresh gặp checksum mismatch.
- EffectiveFrom tương lai và timezone boundaries.
- Command submit với stale code.
- Transaction lịch sử giữ snapshot sau reference update.
- Deprecation alias trong cửa sổ chuyển đổi.
- Cutover shared DB với chỉ một authoritative writer.
- Correction/rollback release có audit và không xóa giao dịch.
- Provider/Reference API unavailable và stale-if-error/fail-closed đúng policy.

Test không chỉ hỏi server trả HTTP 200. Phải chứng minh semantics, version adoption và tính đúng đắn của hành vi nghiệp vụ khi dữ liệu bị trễ.

## 44. ADR mẫu

~~~text
ADR: Ownership of ShippingMethod reference data

Context:
  Ordering, Checkout, Support and Reporting use delivery codes.
  Legacy systems share a writable lookup table.

Decision:
  Fulfillment owns ShippingMethod semantics and lifecycle.
  Only Fulfillment has authoritative write privileges.
  Consumers use versioned snapshots, a query API and change events.

Contract:
  Stable code, record ID, status, locale labels,
  datasetVersion, schemaVersion, validFrom/validTo.

Consistency:
  UI may serve last-known-good labels within a bounded stale window.
  Business commands must be validated by the owner.
  Orders retain accepted shipping snapshots.

Publishing:
  Approved releases are immutable and checksummed.
  Outbox publishes DatasetVersionPublished.
  Consumers deduplicate and re-fetch snapshots on gaps.

Migration:
  Single-writer cutover, backfill, shadow-read,
  consumer adoption, revoke direct SQL grants.

Security:
  Least privilege, tenant-aware caching, publication audit.

Observability:
  Version adoption lag, refresh failures, unknown codes,
  deprecated usage and business command rejection.

Rejected:
  Shared SQL write access and runtime lookup for every UI request.
~~~

ADR phải được hiện thực hóa bằng quyền database, API/contracts, deployment, tests và runbook. Một tài liệu không đủ ngăn service khác UPDATE bảng riêng.

## 45. Bài tập thực hành

**Tình huống:** Một công ty có bảng chung:

~~~sql
CREATE TABLE common_codes (
  type VARCHAR(50),
  code VARCHAR(50),
  label VARCHAR(255),
  value1 VARCHAR(255),
  value2 VARCHAR(255)
);
~~~

Các loại gồm COUNTRY, SHIPPING_ZONE, DISCOUNT_TIER, ORDER_STATUS, CURRENCY, CUSTOMER_SEGMENT. Nhiều services đọc/ghi trực tiếp.

**Yêu cầu:** Đề xuất kế hoạch ownership, dữ liệu nào phân phối bằng snapshot/API, cách đổi mã và migration.

### Gợi ý

1. COUNTRY/CURRENCY metadata: steward được chỉ định, versioned dataset nếu phù hợp.
2. SHIPPING_ZONE: Fulfillment, có effective dating và policy liên quan.
3. DISCOUNT_TIER: Pricing/Promotion, tách reference code khỏi quy tắc tính giá.
4. ORDER_STATUS: Ordering state machine, không để bảng common_codes quyết định transition.
5. CUSTOMER_SEGMENT: CRM/Customer capability, với chính sách tenant/PII phù hợp.
6. Cấm các writers không sở hữu sau khi đã chuyển API/command.
7. Backfill với mapping legacy codes, shadow-read và reconcile.
8. Consumer sử dụng snapshot/API/event, không JOIN SQL private.
9. Đặt deprecation window, unknown-code fallback và compatibility tests.
10. Giữ historical snapshots, audit và SLO version adoption.

### Câu hỏi tự kiểm tra

- Khi đổi nhãn SHIPPING_ZONE, đơn cũ có đổi không?
- Ai quyết định một option bị disable ngay?
- UI có thể hiển thị cache cũ nhưng submit vẫn đúng bằng cách nào?
- Nếu một consumer bỏ lỡ version mới, nó khôi phục thế nào?
- Có cần ReferenceDataService chung cho tất cả dataset không?
- Nếu two tenants có labels khác nhau, cache key cần những gì?
- Thay code nhưng giữ nghĩa có luôn an toàn không?
- Khi rollback dataset sai, giao dịch đã tạo có được tự động rollback không?

Mỗi câu trả lời cần chỉ rõ **authority, semantics, version, thời gian, consumer và failure recovery**.

## 46. Checklist triển khai

### Ownership và định nghĩa

- [ ] Phân biệt reference, master, transaction, config và business policy.
- [ ] Mỗi dataset có business owner/steward.
- [ ] Có một authoritative writer và quyền được thực thi.
- [ ] Code/ID có semantics, namespace và uniqueness scope rõ.
- [ ] Display label không dùng làm business key.
- [ ] Có lifecycle ACTIVE/DEPRECATED/RETIRED khi cần.
- [ ] Có record/dataset/schema/policy version phân biệt.
- [ ] Có effective time và historical snapshot policy nếu cần.
- [ ] Không để universal lookup table che giấu business rules.

### Phân phối và nhất quán

- [ ] Chọn API, cache, snapshot, event hoặc package theo freshness.
- [ ] Cache key xét tenant, locale, query và version phù hợp.
- [ ] Snapshot tải và activate atomically.
- [ ] Event dedup, gap detection và reconciliation được thiết kế.
- [ ] Outbox được dùng khi cần đảm bảo DB và publish intent nhất quán.
- [ ] Consumer có bounded stale policy và fallback rõ.
- [ ] Domain owner validate mọi command quan trọng.
- [ ] Consumer không trực tiếp sửa storage private của owner.
- [ ] Đã thiết kế migration khi tăng schema/dataset version.

### Quản trị, bảo mật và vận hành

- [ ] Có approve/publish/audit phù hợp mức ảnh hưởng.
- [ ] Có deprecation/alias/mapping và migration window.
- [ ] Có contract tests và data quality checks.
- [ ] Có authorization và tenant isolation.
- [ ] Không đưa secrets/PII vào snapshots/events không cần thiết.
- [ ] Theo dõi published version, consumer lag và cache stale.
- [ ] Có snapshot checksum và cơ chế refresh khi gap.
- [ ] Có runbook khi publication sai hoặc consumer mất event.
- [ ] Lịch sử giao dịch không bị viết lại bởi danh mục hiện hành.
- [ ] Migration khỏi shared DB có một writer và kế hoạch revoke grants.

## 47. Kết luận

Dữ liệu dùng chung trong Microservices cần được quản lý như **một hợp đồng có owner và ngữ nghĩa**, không phải bảng SQL mà mọi service được tự do sửa. Danh mục tham chiếu có thể nhỏ nhưng ảnh hưởng rộng: identity và code phải ổn định, thay đổi có vòng đời, thời gian hiệu lực và kiểm soát tương thích, còn dữ liệu giao dịch lịch sử cần giữ đúng phiên bản/snapshot đã chốt.

Hệ thống có thể chia sẻ qua API, immutable snapshot, cache, event hoặc read model tùy độ mới và độ tin cậy cần thiết. Một authoritative writer, quyền truy cập phù hợp, publication đáng tin cậy, idempotency, reconciliation và domain validation giúp consumer dùng chung thông tin mà không tạo ra nhiều nguồn sự thật cạnh tranh.

**Giữ ownership theo năng lực nghiệp vụ, chia sẻ có contract, và quản trị thay đổi theo phiên bản.** Đó là nền tảng để các service độc lập triển khai, dữ liệu vẫn giải thích được và hệ thống có thể phục hồi khi một bản phát hành hoặc một consumer gặp lỗi.
