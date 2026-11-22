# Điều chỉnh chiến lược cho hệ thống nhiều tenant và nhiều cấu hình

Trong module **VALIDATION_TESTING_STRATEGY**, hệ thống nhiều tenant (multi-tenant) và nhiều cấu hình (multi-configuration) đặt ra thách thức kiểm thử riêng: cùng một phiên bản ứng dụng có thể phục vụ nhiều tổ chức, khách hàng hoặc không gian dữ liệu, trong khi mỗi tenant có thể có vai trò, gói dịch vụ, feature flag, locale, quy tắc nghiệp vụ và cấu hình tích hợp khác nhau. Một kiểm thử thành công với tenant mẫu và cấu hình mặc định không chứng minh các tenant khác được cô lập đúng, cũng không chứng minh mọi tổ hợp cấu hình quan trọng hoạt động chính xác.

**Tenant** là một phạm vi khách hàng hoặc tổ chức được hệ thống quản lý như một đơn vị riêng, có thể có người dùng, dữ liệu, quyền và cấu hình riêng. **Multi-configuration** là tình huống sản phẩm có nhiều biến thể cấu hình có ảnh hưởng đến hành vi, chẳng hạn gói dịch vụ, tính năng bật/tắt, chính sách, khu vực, tích hợp hoặc cách triển khai. Hai chiều này thường kết hợp: một tenant có thể dùng cấu hình riêng, nhưng vẫn chia sẻ mã nguồn, hạ tầng hoặc dịch vụ với các tenant khác.

Chiến lược kiểm thử cần xác minh cả hành vi chung và khác biệt theo tenant/cấu hình, đặc biệt là ranh giới dữ liệu, phân quyền, định tuyến, giới hạn tài nguyên, khả năng tùy biến, tương thích và vận hành. Không thể kiểm thử mọi tổ hợp nếu số tenant và tham số cấu hình lớn; nhóm cần phân loại biến thể, chọn tổ hợp theo rủi ro, dùng dữ liệu đại diện và kiểm tra các bất biến áp dụng cho mọi tenant.

Bài học này hướng dẫn cách mô hình hóa tenant và cấu hình, xác định rủi ro đặc thù, xây dựng ma trận kiểm thử, chọn chiến lược bao phủ tổ hợp, chuẩn bị dữ liệu và môi trường, kiểm tra cô lập và phân quyền, đánh giá thay đổi cấu hình, cũng như theo dõi chất lượng trong vận hành. Mục tiêu là có bằng chứng đủ tin cậy rằng hệ thống hoạt động đúng trong các biến thể được hỗ trợ và không làm lộ hoặc làm sai dữ liệu giữa các tenant.

## 1. Hiểu mô hình multi-tenant và multi-configuration

### 1.1. Các mô hình triển khai nhiều tenant

Các hệ thống nhiều tenant có thể dùng những mô hình khác nhau:

| Mô hình | Đặc điểm | Hệ quả kiểm thử |
|---|---|---|
| Shared application, shared database | Các tenant dùng chung ứng dụng và database; dữ liệu được phân biệt bằng tenant key hoặc cơ chế tương đương | Cần kiểm tra tenant scoping ở mọi truy vấn, cache, event và báo cáo |
| Shared application, separate schema | Ứng dụng dùng chung nhưng mỗi tenant có schema riêng | Cần kiểm tra định tuyến schema, migration và quyền truy cập |
| Shared application, separate database | Ứng dụng dùng chung, database tách theo tenant | Cần kiểm tra mapping tenant–database, connection pool và backup/restore riêng |
| Dedicated deployment | Tenant có cụm hoặc môi trường riêng | Cần kiểm tra cấu hình triển khai, drift giữa các tenant và quy trình nâng cấp |
| Hybrid | Kết hợp tenant dùng chung và tenant chuyên biệt | Cần kiểm tra cả luồng dùng chung, luồng chuyên biệt và chuyển đổi giữa mô hình |

Không có mô hình nào tự động bảo đảm cô lập. Shared database có thể an toàn nếu tenant scoping được áp dụng nhất quán; dedicated database vẫn có thể bị định tuyến nhầm hoặc dùng sai credential.

### 1.2. Tenant là một ranh giới nghiệp vụ và bảo mật

Tenant có thể đại diện cho tổ chức, khách hàng doanh nghiệp, nhóm người dùng hoặc workspace. Ranh giới tenant có thể áp dụng cho:

- Dữ liệu và tệp.
- Người dùng, nhóm và vai trò.
- API key, token và session.
- Cấu hình và feature flag.
- Hóa đơn, quota và mức sử dụng.
- Báo cáo, audit và lịch sử hoạt động.
- Tích hợp bên ngoài.
- Chính sách retention và lưu trữ.

Kiểm thử phải xác định rõ những tài nguyên nào thuộc tenant, tài nguyên nào được chia sẻ hợp lệ và thao tác nào cần quyền ở cấp nền tảng. Không nên giả định rằng mọi dữ liệu có tenant ID đều đã được bảo vệ; cần xác minh cơ chế kiểm soát tại các ranh giới thực tế.

### 1.3. Các chiều cấu hình thường gặp

Một tenant hoặc deployment có thể khác nhau theo:

- Gói dịch vụ hoặc subscription tier.
- Feature flag và quyền sử dụng tính năng.
- Vai trò, policy và giới hạn.
- Locale, timezone, tiền tệ và ngôn ngữ.
- Khu vực lưu trữ hoặc data residency.
- Tích hợp và endpoint của nhà cung cấp.
- Quy tắc nghiệp vụ do tenant quản trị.
- Giao diện, branding và tùy biến.
- Quota, rate limit và dung lượng.
- Phiên bản API hoặc khả năng tương thích.
- Cấu hình triển khai, topology và resource limit.

Cần phân biệt cấu hình do sản phẩm định nghĩa, cấu hình do tenant quản lý và cấu hình hạ tầng. Mỗi loại có nguồn sự thật, quyền thay đổi và quy trình xác minh khác nhau.

### 1.4. Shared behavior và tenant-specific behavior

Một chiến lược tốt chia hành vi thành hai nhóm:

- **Hành vi chung:** quy tắc áp dụng cho mọi tenant, chẳng hạn xác thực, ghi audit, xử lý lỗi, tenant isolation và các hợp đồng API chung.
- **Hành vi riêng:** quy tắc hoặc tính năng chỉ áp dụng cho một gói, khu vực, tenant hoặc cấu hình nhất định.

Hành vi chung cần được kiểm tra trên nhiều tenant đại diện để xác nhận không có rò rỉ hoặc phụ thuộc ngầm vào một tenant. Hành vi riêng cần kiểm tra cả trường hợp được phép, không được phép và chuyển đổi cấu hình.

## 2. Nhận diện rủi ro đặc thù

### 2.1. Rò rỉ dữ liệu giữa tenant

Đây là một trong những rủi ro nghiêm trọng nhất. Có thể xảy ra khi:

- Truy vấn database thiếu điều kiện tenant.
- API chấp nhận tenant ID do client gửi mà không xác minh quyền.
- Cache key không bao gồm tenant.
- File storage dùng đường dẫn hoặc object key có thể đoán.
- Search index hoặc analytics gộp dữ liệu sai.
- Background job xử lý bản ghi mà không giữ tenant context.
- Export hoặc report không áp dụng tenant filter.
- Log hoặc trace chứa dữ liệu của tenant khác.

Một test chỉ kiểm tra tenant A đọc được dữ liệu của A chưa đủ. Cần kiểm tra tenant A không thể đọc, sửa, xóa hoặc suy ra dữ liệu của B qua mọi đường truy cập phù hợp.

### 2.2. Sai phân quyền theo tenant và vai trò

Một người dùng có thể có quyền khác nhau theo tenant. Rủi ro gồm:

- User thuộc tenant A truy cập resource của tenant B.
- Role administrator trong một tenant bị hiểu thành administrator toàn nền tảng.
- Token cũ tiếp tục giữ quyền sau khi user bị loại khỏi tenant.
- Quyền ở API khác với quyền giao diện.
- Tenant owner có thể thay đổi cấu hình ngoài phạm vi.
- Service account được cấp quyền quá rộng.

Cần kiểm tra cả danh tính, tenant context, resource ownership và action permission. Ẩn nút trên UI không phải bằng chứng rằng API từ chối thao tác trái quyền.

### 2.3. Cấu hình sai hoặc drift giữa tenant

Cùng một thay đổi có thể được áp dụng cho một số tenant nhưng không phải tất cả. Rủi ro:

- Feature flag bật nhầm tenant.
- Tenant mới nhận cấu hình mặc định không đúng.
- Cấu hình giữa staging và production không đồng nhất.
- Một tenant chuyên biệt bị bỏ sót khi nâng cấp.
- Thay đổi cấu hình không có audit.
- Giá trị cấu hình cũ không còn tương thích với phiên bản mới.

Cần kiểm tra nguồn cấu hình, thứ tự ưu tiên, giá trị mặc định, kế thừa và lịch sử thay đổi.

### 2.4. Noisy neighbor và tranh chấp tài nguyên

Trong mô hình dùng chung, một tenant có tải lớn có thể ảnh hưởng tenant khác thông qua CPU, database connection, queue, cache, storage hoặc quota. Các biểu hiện:

- Latency của tenant khác tăng.
- Một tenant chiếm hết worker hoặc connection pool.
- Rate limit áp dụng sai phạm vi.
- Queue chung bị backlog.
- Cache eviction làm giảm hiệu năng của tenant ít hoạt động.
- Một tenant tạo dữ liệu lớn làm chậm report chung.

Kiểm thử cần xem xét công bằng tài nguyên, giới hạn theo tenant và hành vi khi một tenant vượt quota.

### 2.5. Sai lệch dữ liệu và quy tắc theo cấu hình

Một cấu hình có thể làm thay đổi:

- Cách tính thuế hoặc giá.
- Quy tắc phê duyệt.
- Ngày hết hạn hoặc timezone.
- Currency và rounding.
- Retention, export hoặc xóa dữ liệu.
- Quy tắc thông báo.
- Luồng nghiệp vụ và trạng thái.

Nếu test chỉ dùng cấu hình mặc định, lỗi có thể xuất hiện ở tenant có chính sách khác. Cần xác định cấu hình nào thay đổi logic nghiệp vụ và kiểm tra biên của từng quy tắc.

### 2.6. Rủi ro onboarding, offboarding và chuyển đổi tenant

Vòng đời tenant tạo nhiều trạng thái:

- Tạo tenant mới.
- Khởi tạo cấu hình và dữ liệu mặc định.
- Mời và gán người dùng.
- Nâng cấp hoặc hạ cấp gói.
- Tạm ngừng hoặc kích hoạt lại.
- Chuyển vùng hoặc thay mô hình lưu trữ.
- Xuất dữ liệu.
- Xóa hoặc đóng tenant.

Cần kiểm tra dữ liệu, quyền, subscription, job nền và tích hợp trong từng chuyển trạng thái. Đặc biệt, offboarding phải xác minh dữ liệu được giữ, xuất hoặc xóa theo chính sách mà không ảnh hưởng tenant khác.

## 3. Xây dựng mô hình tenant và cấu hình làm cơ sở kiểm thử

### 3.1. Lập hồ sơ tenant

Mỗi tenant test nên có hồ sơ tối thiểu:

| Thuộc tính | Nội dung |
|---|---|
| Tenant ID | Định danh ổn định, không trùng |
| Tenant type | Loại tổ chức hoặc phân khúc |
| Deployment model | Shared, schema riêng, database riêng hoặc dedicated |
| Subscription | Gói dịch vụ và giới hạn |
| Region | Khu vực hoặc data residency |
| Locale | Ngôn ngữ, timezone, currency |
| Feature set | Tính năng bật/tắt |
| Policy | Quy tắc và quyền riêng |
| Integrations | Nhà cung cấp hoặc endpoint |
| Data profile | Quy mô, trạng thái và phân bố dữ liệu |
| Lifecycle state | Active, suspended, trial, closing hoặc deleted |
| Owner | Nhóm quản lý tenant test |

Không cần dùng dữ liệu khách hàng thật để tạo hồ sơ đại diện. Có thể dùng dữ liệu tổng hợp với cấu trúc và phân bố phù hợp.

### 3.2. Lập configuration profile

Cấu hình nên được gom thành profile có thể tái sử dụng, ví dụ:

- Standard: cấu hình mặc định phổ biến.
- Enterprise: nhiều người dùng, quyền phức tạp, tích hợp và quota lớn.
- Restricted: giới hạn tính năng hoặc chính sách nghiêm ngặt.
- Regional: timezone, locale, currency hoặc data residency riêng.
- Custom: cấu hình đặc biệt có lý do nghiệp vụ.

Tên profile chỉ là nhãn; cần ghi giá trị và quy tắc cụ thể. Hai tenant cùng profile có thể vẫn có khác biệt về dữ liệu, quyền hoặc tích hợp.

### 3.3. Xác định nguồn sự thật của cấu hình

Cần biết cấu hình được lấy từ đâu và có thứ tự ưu tiên thế nào:

1. Giá trị mặc định của sản phẩm.
2. Cấu hình cấp môi trường hoặc nền tảng.
3. Cấu hình cấp gói dịch vụ.
4. Cấu hình riêng của tenant.
5. Tùy chọn theo người dùng hoặc phiên.
6. Override tạm thời có thời hạn.

Thứ tự thực tế phải được tài liệu hóa. Kiểm thử cần xác nhận giá trị cuối cùng có đúng với quy tắc ưu tiên, đặc biệt khi nhiều lớp cấu hình cùng đặt một thuộc tính.

### 3.4. Kiểm tra cấu hình hiệu lực

Không chỉ kiểm tra file hoặc bản ghi cấu hình đã lưu. Cần xác minh cấu hình hiệu lực mà ứng dụng thực sự sử dụng:

- API hoặc admin view trả về giá trị nào?
- Feature flag được đánh giá theo tenant nào?
- Cache cấu hình có được làm mới đúng không?
- Instance khác nhau có cùng nhận giá trị không?
- Thay đổi có được áp dụng ngay hay ở phiên mới?
- Có audit record và version cấu hình không?

Nếu cấu hình được cache, kiểm tra invalidation và thời gian lan truyền. Một tenant có thể thấy cấu hình mới ở một instance nhưng cấu hình cũ ở instance khác.

## 4. Thiết kế chiến lược bao phủ tenant

### 4.1. Không kiểm thử chỉ với một tenant

Một tenant mẫu thường không đại diện cho các khác biệt về gói, quyền, dữ liệu và cấu hình. Tập tenant kiểm thử cần bao gồm các đặc trưng quan trọng, chẳng hạn:

- Tenant mới tạo với cấu hình mặc định.
- Tenant lâu năm có dữ liệu lịch sử.
- Tenant có nhiều user và role.
- Tenant có cấu hình tùy chỉnh.
- Tenant có quota thấp hoặc đã gần giới hạn.
- Tenant bị tạm ngừng.
- Tenant ở region hoặc locale khác.
- Tenant dùng tích hợp ngoài.
- Tenant dedicated hoặc hybrid nếu sản phẩm hỗ trợ.

Chọn tenant theo đặc tính rủi ro, không theo tên hoặc thứ tự tạo.

### 4.2. Kiểm tra tenant isolation theo cặp

Với các thao tác nhạy cảm, dùng ít nhất hai tenant độc lập:

- Tenant A tạo resource A.
- Tenant B tạo resource B.
- A chỉ thấy và thao tác được resource A.
- B chỉ thấy và thao tác được resource B.
- A thử truy cập resource B bằng ID trực tiếp.
- B thử cập nhật hoặc xóa resource A.
- Kiểm tra tìm kiếm, export, report, cache và file storage.
- Xác minh audit ghi đúng tenant và actor.

Nên kiểm tra cả trường hợp tenant ID bị thay đổi trong request, token có claim sai, resource ID được đoán và đường dẫn truy cập gián tiếp.

### 4.3. Kiểm tra tenant context qua các ranh giới

Tenant context cần được giữ đúng khi đi qua:

- API gateway.
- Service-to-service call.
- Message broker và event.
- Background job và scheduler.
- Cache.
- Search index.
- File storage.
- Data warehouse và reporting.
- Webhook hoặc callback.

Ví dụ, một event được phát từ tenant A cần mang tenant context đáng tin cậy và consumer phải dùng context đó khi đọc/ghi dữ liệu. Không nên tin một trường tenant ID tùy ý từ payload mà không xác thực nguồn và quyền.

### 4.4. Kiểm tra ranh giới tenant trong cache và tìm kiếm

Cache key thường cần chứa tenant scope nếu dữ liệu không chia sẻ. Test cần xác nhận:

- Cùng một key ở hai tenant không trả dữ liệu chéo.
- Cache invalidation chỉ ảnh hưởng phạm vi phù hợp.
- Search query luôn áp dụng tenant filter.
- Facet, suggestion và autocomplete không tiết lộ dữ liệu khác.
- Cache miss và fallback không bỏ qua tenant context.
- Dữ liệu cũ không còn truy cập sau khi tenant bị khóa hoặc quyền thay đổi.

### 4.5. Kiểm tra thao tác quản trị cấp nền tảng

Một số vai trò có thể truy cập nhiều tenant để hỗ trợ hoặc vận hành. Cần xác định:

- Vai trò nào được phép cross-tenant?
- Cần lý do hoặc approval nào?
- Có audit đầy đủ không?
- Quyền có thời hạn không?
- Có phân biệt support access và tenant owner không?
- Giao diện và API có cùng enforce policy không?

Test phải xác nhận quyền cross-tenant chỉ hoạt động với vai trò được phê duyệt và không bị kế thừa ngoài ý muốn.

## 5. Thiết kế chiến lược bao phủ cấu hình

### 5.1. Xác định tham số cấu hình ảnh hưởng hành vi

Không phải mọi setting đều cần tạo tổ hợp test. Phân loại:

- **Behavioral:** thay đổi logic hoặc kết quả nghiệp vụ.
- **Access control:** thay đổi quyền hoặc khả năng sử dụng.
- **Presentation:** thay đổi hiển thị, locale hoặc branding.
- **Operational:** thay đổi timeout, retry, quota hoặc resource.
- **Integration:** thay đổi endpoint, credential hoặc provider.
- **Deployment:** thay đổi topology, region hoặc storage.

Ưu tiên tham số có thể thay đổi kết quả, ranh giới bảo mật hoặc khả năng vận hành.

### 5.2. Kiểm tra giá trị mặc định, tùy chỉnh và biên

Với mỗi setting quan trọng, kiểm tra:

- Không được cấu hình: hệ thống dùng default đúng không?
- Giá trị hợp lệ tối thiểu và tối đa.
- Giá trị ngoài miền hoặc sai định dạng.
- Giá trị null, rỗng hoặc bị thiếu nếu được phép.
- Hai setting xung đột.
- Thay đổi khi tenant đang hoạt động.
- Giá trị cũ sau nâng cấp.
- Giá trị bị ghi đè bởi lớp cấu hình khác.

Ví dụ, với session timeout, cần kiểm tra default, tenant override, giới hạn tối thiểu/tối đa và hiệu lực trên các instance. Không chỉ xác nhận admin UI lưu được giá trị.

### 5.3. Kiểm tra tương tác giữa cấu hình

Hai setting riêng lẻ có thể đúng nhưng kết hợp lại gây lỗi. Ví dụ:

- Feature flag bật nhưng gói dịch vụ không có entitlement.
- Locale và currency không tương thích quy tắc tính tiền.
- Retry cao kết hợp timeout thấp gây tải tăng.
- Quota thấp kết hợp batch job lớn gây xử lý dở dang.
- Region và data residency khiến service định tuyến sai.
- Role override xung đột với policy mặc định.

Xác định các cặp hoặc nhóm cấu hình có quan hệ logic và kiểm thử tương tác. Không cần kiểm tra mọi tổ hợp ngẫu nhiên nếu không có khả năng kết hợp thực tế.

### 5.4. Feature flag và entitlement

Phân biệt:

- Feature flag: bật/tắt triển khai hoặc thử nghiệm tính năng.
- Entitlement: quyền tenant được sử dụng tính năng theo gói hoặc hợp đồng.
- Authorization: người dùng cụ thể có quyền thực hiện thao tác hay không.

Một tính năng chỉ nên hoạt động khi tất cả điều kiện liên quan đều thỏa mãn. Test cần bao phủ flag bật/tắt, entitlement có/không, role được phép/không được phép và trạng thái tenant.

Ví dụ, flag bật toàn hệ thống không được làm tenant chưa mua gói có thể sử dụng tính năng trả phí.

## 6. Chọn tổ hợp kiểm thử khi số chiều lớn

### 6.1. Vì sao không thể brute-force mọi tổ hợp?

Giả sử hệ thống có:

- 4 gói dịch vụ.
- 5 region.
- 3 locale.
- 6 nhóm feature flag.
- 4 role.
- 3 mô hình triển khai.

Số tổ hợp lý thuyết là tích của các chiều này và có thể lên đến hàng nghìn hoặc nhiều hơn. Khi thêm tenant lifecycle, dữ liệu và tích hợp, số trường hợp tăng rất nhanh.

Chạy toàn bộ tổ hợp thường không khả thi. Cần phân tích quan hệ và chọn tập đại diện có mục tiêu.

### 6.2. Equivalence partitioning

Chia giá trị thành các nhóm có hành vi tương đương theo quy tắc. Ví dụ, gói dịch vụ có thể chia thành:

- Không có entitlement.
- Có entitlement cơ bản.
- Có entitlement nâng cao.
- Gói tùy chỉnh.

Chọn đại diện từ mỗi nhóm, sau đó bổ sung giá trị biên và ngoại lệ. Không nên coi hai tenant tương đương chỉ vì cùng subscription nếu họ khác region, policy hoặc integration có liên quan.

### 6.3. Pairwise và combinatorial testing

Pairwise testing chọn tập tổ hợp sao cho mỗi cặp giá trị của các tham số xuất hiện ít nhất một lần. Cách này hữu ích khi nhiều lỗi phát sinh từ tương tác hai chiều.

Ví dụ các chiều:

- Plan: Basic, Enterprise.
- Region: APAC, EU.
- Locale: vi-VN, en-US.
- Feature: Enabled, Disabled.

Pairwise có thể giảm số trường hợp so với kiểm tra toàn bộ tổ hợp. Tuy nhiên, pairwise không bảo đảm phát hiện lỗi chỉ xuất hiện khi ba hoặc nhiều điều kiện kết hợp. Với rủi ro cao, cần kiểm thử t-way cao hơn hoặc tổ hợp cụ thể theo kiến thức miền.

### 6.4. Risk-based combination

Chọn tổ hợp dựa trên:

- Mức hậu quả nếu sai.
- Tần suất sử dụng.
- Độ phổ biến của cấu hình.
- Số lượng tenant bị ảnh hưởng.
- Độ phức tạp của tương tác.
- Lịch sử lỗi.
- Mức độ khác biệt giữa môi trường.
- Khả năng phát hiện và phục hồi.

Một tổ hợp hiếm nhưng có thể làm lộ dữ liệu giữa region cần được ưu tiên hơn một tổ hợp hiếm chỉ làm sai màu giao diện.

### 6.5. Bộ tenant và cấu hình đại diện

Có thể tạo một ma trận tối thiểu:

| Profile | Đặc trưng | Mục tiêu chính |
|---|---|---|
| T1 Standard | Gói phổ biến, default config | Hành vi cơ bản |
| T2 Enterprise | Nhiều user, role và quota lớn | Phân quyền, tải và quản trị |
| T3 Restricted | Entitlement hạn chế, quota thấp | Deny path và giới hạn |
| T4 Regional | Locale, timezone, data residency riêng | Định dạng, định tuyến và dữ liệu |
| T5 Customized | Override và integration riêng | Cấu hình tùy chỉnh và hợp đồng |
| T6 Lifecycle | Tenant suspended hoặc closing | Trạng thái vòng đời và quyền |

Đây là profile minh họa. Chọn profile thực tế theo kiến trúc và phân khúc được hỗ trợ; không cần tạo tenant cho mọi tổ hợp nếu có thể kiểm tra setting bằng fixture hoặc môi trường cô lập.

## 7. Kiểm thử phân quyền và bảo mật nhiều tenant

### 7.1. Ma trận actor–tenant–resource–action

Mỗi kiểm tra quyền cần xác định bốn yếu tố:

- Actor: người dùng hoặc service account.
- Tenant context: tenant đang được xác thực.
- Resource: tài nguyên và tenant owner của nó.
- Action: read, create, update, delete, export hoặc administer.

Ví dụ:

| Actor | Tenant context | Resource | Action | Kết quả mong đợi |
|---|---|---|---|---|
| User A | Tenant A | Resource A | Read | Allow nếu role có quyền |
| User A | Tenant A | Resource B | Read | Deny |
| Admin A | Tenant A | Resource B | Update | Deny nếu không có quyền nền tảng |
| Platform support | Support context được phê duyệt | Resource B | Read | Allow có audit và phạm vi |
| Suspended user | Tenant A | Resource A | Update | Deny |

Cần kiểm tra cả API trực tiếp và giao diện. Nếu API từ chối nhưng UI hiển thị dữ liệu nhạy cảm từ cache, vẫn là lỗi.

### 7.2. Tenant context đáng tin cậy

Tenant context có thể được lấy từ token, session, host/domain, header hoặc routing layer. Cần xác định nguồn có thẩm quyền và cách xác minh:

- Client không thể tự chọn tenant tùy ý.
- Token được phát hành cho đúng tenant.
- Tenant claim được xác minh và không bị thay đổi.
- Session không bị tái sử dụng giữa tenant.
- Host/domain mapping đúng.
- Service-to-service identity mang context đúng.
- Background job không dùng tenant context mặc định sai.

Không nên tin tenant ID do request body cung cấp nếu chưa kiểm tra actor có quyền với tenant đó.

### 7.3. Kiểm tra dữ liệu phụ và kênh rò rỉ

Ngoài API chính, kiểm tra:

- Export CSV/PDF.
- Search và autocomplete.
- Notification và email.
- Attachment và file download.
- Audit log.
- Analytics và dashboard.
- Cache và CDN.
- Error message.
- URL, metadata và object storage.
- Backup và restore theo tenant.

Rò rỉ có thể xuất hiện trong metadata, tên file hoặc thông báo dù nội dung chính đã được lọc.

### 7.4. Kiểm tra lifecycle và thu hồi quyền

Khi user bị xóa khỏi tenant hoặc tenant bị suspended:

- Token và session cũ còn hiệu lực không?
- API có từ chối request mới không?
- Job đang chạy có tiếp tục ghi dữ liệu không?
- Cache quyền có được invalidated không?
- Link chia sẻ hoặc file download còn truy cập được không?
- Audit và lịch sử được giữ theo policy không?

Cần xác định độ trễ cho phép giữa thay đổi quyền và hiệu lực thực tế. Test nên bao gồm ngay sau thay đổi và sau thời gian cache/propagation được quy định.

## 8. Kiểm thử dữ liệu, migration và vòng đời tenant

### 8.1. Dữ liệu cô lập và dữ liệu chia sẻ

Phân loại:

- Dữ liệu riêng của tenant.
- Dữ liệu danh mục dùng chung.
- Dữ liệu tham chiếu toàn nền tảng.
- Dữ liệu được chia sẻ có kiểm soát.
- Dữ liệu tổng hợp hoặc ẩn danh.
- Metadata vận hành.

Với mỗi loại, xác định ai được đọc/ghi, nơi lưu, cách phân vùng và retention. Test phải xác nhận dữ liệu dùng chung không vô tình cho phép truy cập vào dữ liệu riêng.

### 8.2. Tenant provisioning

Khi tạo tenant mới, kiểm tra:

- Tenant ID duy nhất và được cấp đúng.
- Default config đúng theo plan và region.
- Schema/database hoặc partition được tạo nếu cần.
- Role và owner ban đầu đúng.
- Entitlement được khởi tạo.
- Quota và billing context chính xác.
- Audit record được ghi.
- Tenant chỉ hoạt động khi các thành phần cần thiết sẵn sàng.

Kiểm tra provisioning thất bại giữa chừng, retry và chạy lại. Quy trình cần idempotent để không tạo tenant hoặc tài nguyên trùng.

### 8.3. Nâng cấp, hạ cấp và thay đổi cấu hình

Khi plan hoặc cấu hình đổi:

- Tính năng nào được bật hoặc tắt?
- Dữ liệu hiện có được giữ hay chuyển đổi?
- User đang dùng tính năng bị ảnh hưởng thế nào?
- Quota vượt mức được xử lý ra sao?
- Có job nền cần dừng hoặc tiếp tục không?
- Các instance có nhận cấu hình nhất quán không?
- Có audit và khả năng khôi phục cấu hình không?

Hạ cấp không nên âm thầm xóa dữ liệu nếu chính sách chỉ yêu cầu chặn tạo mới. Cần xác định rõ hành vi với dữ liệu vượt quota và quyền đã cấp.

### 8.4. Migration theo tenant

Migration có thể chạy toàn hệ thống hoặc từng tenant. Cần kiểm tra:

- Tenant nào đã migrate và tenant nào chưa?
- Có thể chạy lại an toàn không?
- Một tenant lỗi có chặn tất cả tenant không?
- Có giới hạn tốc độ để tránh ảnh hưởng tải chung không?
- Có thể pause/resume theo checkpoint không?
- Schema cũ và mới có thể cùng tồn tại trong giai đoạn chuyển tiếp không?
- Báo cáo tiến độ và lỗi có phân tách theo tenant không?

Với migration hàng loạt, cần kiểm tra cả tenant lớn, tenant nhỏ, tenant có dữ liệu bất thường và tenant đang suspended nếu quy trình hỗ trợ.

### 8.5. Offboarding và xóa tenant

Kiểm tra:

- Ai có quyền yêu cầu đóng tenant?
- Có thời gian chờ hoặc export trước xóa không?
- Dữ liệu nào được xóa, lưu trữ hoặc giữ vì nghĩa vụ?
- Backup và replica xử lý thế nào?
- Cache, search index, file và queue có được dọn đúng không?
- Tenant ID có bị tái sử dụng không?
- Xóa một tenant có ảnh hưởng dữ liệu dùng chung hoặc tenant khác không?

Cần xác minh xóa theo tenant scope và kiểm tra không còn đường truy cập ngoài ý muốn sau khi hoàn tất.

## 9. Kiểm thử quota, hiệu năng và tính công bằng tài nguyên

### 9.1. Quota và rate limit theo tenant

Kiểm tra:

- Giới hạn request theo tenant.
- Dung lượng lưu trữ.
- Số user hoặc project tối đa.
- Số job đồng thời.
- Giới hạn API provider.
- Quota theo gói và override.
- Hành vi ở ngay dưới, đúng tại và vượt giới hạn.
- Reset quota theo chu kỳ và timezone.

Đảm bảo một tenant vượt quota không làm các tenant khác bị từ chối sai. Thông báo giới hạn cần chính xác và không tiết lộ dữ liệu tenant khác.

### 9.2. Noisy-neighbor testing

Tạo tải có kiểm soát từ một tenant và quan sát tenant còn lại:

1. Thiết lập baseline cho tenant A và B.
2. Chạy tải bình thường trên cả hai.
3. Tăng tải tenant A đến ngưỡng hoặc vượt quota.
4. Đo latency, error rate và resource của B.
5. Xác minh rate limit, queue isolation hoặc scheduling policy.
6. Giảm tải A và quan sát phục hồi.

Không nên chỉ đo tổng throughput toàn hệ thống. Cần có metric theo tenant hoặc cách phân tách đủ tin cậy để thấy tác động chéo.

### 9.3. Kiểm tra fairness và isolation tài nguyên

Tùy kiến trúc, có thể kiểm tra:

- Connection pool có giới hạn theo tenant hoặc workload không?
- Một tenant có thể chiếm hết worker không?
- Queue có phân vùng hoặc cơ chế ưu tiên không?
- Cache có quota hoặc eviction policy phù hợp không?
- Autoscaling có bị một tenant kích hoạt quá mức không?
- Storage và bandwidth có giới hạn riêng không?

Fairness không nhất thiết có nghĩa chia đều tuyệt đối. Nó phải phù hợp với gói dịch vụ, hợp đồng và chính sách ưu tiên đã công bố.

### 9.4. Kiểm thử dữ liệu quy mô khác nhau

Chọn tenant có:

- Dữ liệu nhỏ và mới.
- Dữ liệu lớn hoặc lịch sử dài.
- Phân bố lệch.
- Nhiều quan hệ và attachment.
- Nhiều user đồng thời.
- Số lượng event hoặc job lớn.

Kiểm tra truy vấn, export, report, migration và cleanup ở quy mô đại diện. Dữ liệu nhỏ của tenant test mặc định không chứng minh hiệu năng với tenant lớn.

## 10. Kiểm thử locale, region và tích hợp theo tenant

### 10.1. Locale và timezone

Với tenant ở khu vực khác nhau, xác minh:

- Ngày giờ hiển thị theo timezone đã chọn.
- Timestamp lưu trữ và chuyển đổi đúng.
- DST và ranh giới ngày nếu region có áp dụng.
- Currency và rounding.
- Định dạng số, địa chỉ và tên.
- Ngôn ngữ thông báo và email.
- Lịch làm việc hoặc ngày nghỉ nếu có.

Không suy ra timezone chỉ từ ngôn ngữ. Một tenant có thể dùng ngôn ngữ tiếng Việt nhưng hoạt động ở múi giờ khác.

### 10.2. Data residency và region routing

Nếu dữ liệu phải lưu ở khu vực xác định, kiểm tra:

- Tenant được định tuyến đến region đúng.
- Dữ liệu chính, backup, log và file có tuân thủ phạm vi.
- Replication có theo policy.
- Service-to-service call không chuyển dữ liệu sai region.
- Failover có giữ ràng buộc residency không.
- Export và support access có được kiểm soát.

Cần phân biệt vị trí xử lý, lưu trữ, backup và telemetry. Một database nằm đúng region không đủ chứng minh toàn bộ dữ liệu của tenant không đi ra ngoài khu vực.

### 10.3. Tích hợp riêng theo tenant

Tenant có thể cấu hình endpoint, credential hoặc mapping riêng. Test cần xác minh:

- Credential thuộc đúng tenant và có phạm vi tối thiểu.
- Request được gửi đến đúng endpoint.
- Retry và timeout không gây giao dịch trùng.
- Webhook xác thực đúng nguồn.
- Lỗi của tích hợp tenant A không ảnh hưởng tenant B.
- Secret rotation không làm lộ hoặc dùng chéo credential.
- Sandbox và production config không bị nhầm.

Khi một provider chung phục vụ nhiều tenant, cần kiểm tra mapping tenant–account–credential và giới hạn quota riêng.

## 11. Quản lý ma trận kiểm thử và tự động hóa

### 11.1. Ma trận tenant–configuration–test

Một ma trận có thể ghi:

| Tenant profile | Plan | Region | Feature | Role | Test focus |
|---|---|---|---|---|---|
| T1 | Standard | APAC | Default | Member/Admin | Luồng cơ bản |
| T2 | Enterprise | EU | Advanced | Multi-role | Quyền, data residency, quota |
| T3 | Restricted | APAC | Limited | Read-only | Deny path và entitlement |
| T4 | Custom | US | Custom flags | Tenant admin | Override và integration |
| T5 | Suspended | APAC | Disabled | Former member | Thu hồi quyền và lifecycle |

Không nhất thiết mọi test chạy trên mọi dòng. Ma trận phải chỉ ra test nào cần chạy ở profile nào và vì sao.

### 11.2. Tách test dùng chung và test đặc thù

Có thể tổ chức:

- Shared tenant contract tests.
- Tenant isolation tests.
- Role/permission matrix tests.
- Configuration behavior tests.
- Plan/entitlement tests.
- Region/locale tests.
- Tenant lifecycle tests.
- Noisy-neighbor và quota tests.
- Dedicated deployment tests.

Tách nhóm giúp chọn test theo thay đổi và giảm việc chạy toàn bộ suite không cần thiết.

### 11.3. Parameterize thay vì nhân bản test

Với hành vi chung, dùng test data hoặc profile parameterized để chạy cùng một test trên nhiều tenant/cấu hình. Lợi ích:

- Giảm duplicate test logic.
- Giữ assertion nhất quán.
- Dễ thêm profile.
- Dễ so sánh kết quả.

Tuy nhiên, không ép mọi biến thể vào một test chung nếu setup hoặc oracle khác nhau đáng kể. Các hành vi đặc thù cần test riêng để thể hiện quy tắc rõ ràng.

### 11.4. Tạo tenant và dữ liệu cô lập cho từng test run

Test automation cần tránh trạng thái chia sẻ gây nhiễu:

- Tạo tenant hoặc namespace riêng cho run khi phù hợp.
- Dùng ID duy nhất và seed xác định.
- Không dùng chung tài khoản admin nếu có thể tránh.
- Dọn dữ liệu theo tenant scope.
- Xử lý cleanup khi test fail giữa chừng.
- Không để test song song thay đổi cùng một cấu hình.
- Ghi tenant ID, profile và config version vào report.

Cleanup phải được kiểm tra để không xóa dữ liệu của tenant khác. Với test cần giữ bằng chứng, lưu artifact trước khi dọn.

### 11.5. Chạy test theo phạm vi thay đổi

Khi một thay đổi chỉ ảnh hưởng một nhóm cấu hình, có thể chọn test liên quan. Nhưng nếu thay đổi nằm ở tenant context, authorization, cache hoặc shared library, cần mở rộng sang nhiều profile và đường đi.

Quy tắc lựa chọn nên dựa trên dependency và rủi ro, không chỉ dựa vào tên thư mục hoặc nhãn tenant.

## 12. Kiểm soát thay đổi cấu hình và rollout

### 12.1. Version hóa cấu hình

Cần có cách nhận diện:

- Version hoặc revision cấu hình.
- Ai thay đổi và khi nào.
- Giá trị cũ và mới.
- Phạm vi tenant áp dụng.
- Lý do và approval.
- Kết quả validation.
- Cách rollback hoặc khôi phục.

Nếu cấu hình thay đổi mà không có version, khó xác định test run nào đã dùng giá trị nào.

### 12.2. Kiểm tra rollout theo tenant

Khi bật tính năng theo tenant hoặc cohort:

- Tenant nào được chọn?
- Điều kiện chọn có đúng không?
- Có tenant bị bật ngoài danh sách không?
- Có thể dừng hoặc đảo flag nhanh không?
- Có theo dõi metric theo cohort không?
- Tenant có cấu hình đặc biệt có bị bỏ sót không?

Canary theo tenant cần chọn nhóm đủ đại diện và có khả năng giới hạn tác động. Không nên chỉ chọn tenant nội bộ nếu hành vi khách hàng khác đáng kể.

### 12.3. Thay đổi cấu hình khi hệ thống đang chạy

Kiểm tra:

- Thay đổi có hiệu lực tức thì hay ở request/session tiếp theo?
- Các instance có nhận cùng revision không?
- Cache được invalidated đúng không?
- Request đang chạy xử lý theo config cũ hay mới?
- Có race condition khi đổi nhiều setting liên quan không?
- Rollback cấu hình có khôi phục đúng trạng thái không?

Cần xác định hành vi nhất quán khi cấu hình cập nhật giữa chừng. Với thay đổi có thể ảnh hưởng dữ liệu, cân nhắc áp dụng theo từng tenant và có checkpoint.

## 13. Báo cáo kết quả và đánh giá mức sẵn sàng

### 13.1. Báo cáo theo profile và rủi ro

Không chỉ báo tổng số test pass. Cần thể hiện:

- Tenant profile và config version đã kiểm tra.
- Những profile chưa được kiểm tra.
- Kết quả isolation và authorization.
- Các cấu hình có hành vi khác nhau.
- Quota, performance và noisy-neighbor results.
- Migration và lifecycle evidence.
- Lỗi theo severity/priority.
- Giới hạn do mock, môi trường hoặc dữ liệu.
- Rủi ro còn lại và owner.

### 13.2. Tránh kết luận từ tenant mẫu

Nếu chỉ kiểm thử tenant Standard ở APAC, không nên kết luận hệ thống đã được xác minh cho Enterprise ở EU hoặc tenant dedicated. Báo cáo cần ghi rõ profile được đại diện và khoảng trống.

Có thể đưa ra kết luận theo phạm vi: “Hành vi chung đã được kiểm tra trên các profile T1, T2 và T3; cấu hình tích hợp riêng của T4 chưa được xác minh.” Đây là kết luận rõ hơn một câu “multi-tenant tests passed”.

### 13.3. Quality gate đặc thù

Một gate cho hệ thống multi-tenant có thể yêu cầu:

- Không có lỗi cross-tenant access.
- Các role và entitlement trọng yếu được xác minh.
- Cấu hình mặc định và override quan trọng đúng.
- Migration và provisioning không ảnh hưởng tenant khác.
- Quota và isolation tài nguyên đạt mục tiêu.
- Các region hoặc data residency bắt buộc được kiểm tra.
- Không có tenant profile quan trọng bị bỏ qua mà không có quyết định rủi ro.
- Artifact và config version có thể truy vết.

Điều kiện cụ thể phải theo yêu cầu sản phẩm, hợp đồng và chính sách bảo mật.

## 14. Ví dụ tổng hợp: thay đổi feature flag cho tenant Enterprise

Giả sử tính năng báo cáo nâng cao được bật cho tenant Enterprise ở một số region. Thay đổi lần này bổ sung một flag mới và nâng giới hạn export.

### 14.1. Các chiều cần đánh giá

- Tenant plan: Standard, Enterprise.
- Region: APAC, EU.
- Flag: Enabled, Disabled.
- Role: Tenant Admin, Analyst, Member.
- Quota: dưới, sát và vượt giới hạn.
- Data size: nhỏ và lớn.

### 14.2. Rủi ro chính

- Tenant Standard truy cập được tính năng chưa có entitlement.
- Member có quyền export vượt policy.
- Flag bật nhầm tenant hoặc sai region.
- Export chứa dữ liệu tenant khác.
- Quota mới gây tải hoặc làm đầy storage.
- Cấu hình cũ không có flag mới nhận default sai.
- Cache cấu hình giữa các instance không nhất quán.

### 14.3. Tập kiểm thử đại diện

| Trường hợp | Cấu hình | Kết quả cần xác minh |
|---|---|---|
| A | Enterprise, APAC, flag on, Admin | Có thể dùng báo cáo trong quota |
| B | Standard, APAC, flag on nhưng không entitlement | Bị từ chối theo policy |
| C | Enterprise, EU, flag on, Analyst | Chỉ truy cập dữ liệu tenant và region được phép |
| D | Enterprise, flag off | Tính năng không khả dụng |
| E | Enterprise, flag on, Member | Quyền export bị giới hạn |
| F | Enterprise, export vượt quota | Từ chối rõ ràng, không tạo dữ liệu dở dang |
| G | Tenant khác cố truy cập export ID | Bị từ chối |
| H | Thay đổi flag khi nhiều instance chạy | Cấu hình hiệu lực nhất quán theo quy tắc |

Bổ sung test noisy-neighbor nếu export có thể chiếm tài nguyên dùng chung.

### 14.4. Điều kiện chấp nhận

- Không có truy cập chéo tenant hoặc vượt role.
- Entitlement và flag được áp dụng đúng.
- Export tuân thủ quota và region policy.
- Cấu hình hiệu lực có thể truy vết.
- Các trường hợp lỗi không tạo artifact hoặc job dở dang ngoài dự kiến.
- Các profile quan trọng có bằng chứng.
- Rủi ro của tổ hợp chưa kiểm tra được ghi rõ trước rollout.

## 15. Những sai lầm thường gặp

1. **Chỉ dùng một tenant mẫu:** bỏ sót khác biệt về plan, role, region và lifecycle.
2. **Coi tenant ID là cơ chế bảo mật:** không kiểm tra enforcement ở API, cache, storage và job nền.
3. **Chỉ kiểm tra UI:** bỏ qua request trực tiếp và service-to-service.
4. **Không kiểm tra cross-tenant negative path:** chỉ chứng minh tenant đọc được dữ liệu của chính mình.
5. **Tin tenant context từ client:** cho phép request giả mạo tenant.
6. **Bỏ qua cache và search:** dữ liệu có thể rò rỉ ngoài database.
7. **Không phân biệt feature flag với entitlement:** tenant không có gói vẫn truy cập tính năng.
8. **Kiểm thử mọi tổ hợp máy móc:** tốn tài nguyên mà không tập trung rủi ro.
9. **Dùng pairwise như bảo đảm đầy đủ:** bỏ qua lỗi cần tương tác ba hoặc nhiều chiều.
10. **Không kiểm tra giá trị mặc định và override:** tenant mới hoặc cấu hình cũ nhận hành vi sai.
11. **Không kiểm tra tenant lớn và noisy neighbor:** bỏ sót ảnh hưởng tài nguyên chéo.
12. **Bỏ qua provisioning và offboarding:** dữ liệu, quyền hoặc tài nguyên còn sót.
13. **Không version hóa cấu hình:** khó tái hiện kết quả và điều tra drift.
14. **Dùng dữ liệu chung cho test song song:** tạo xung đột hoặc cleanup nhầm tenant.
15. **Kết luận toàn hệ thống từ một profile:** mở rộng kết luận vượt quá bằng chứng.
16. **Không kiểm tra migration theo từng tenant:** một tenant lỗi có thể làm dừng hoặc làm sai cả batch.

## 16. Checklist điều chỉnh chiến lược cho hệ thống nhiều tenant và nhiều cấu hình

- [ ] Mô hình tenant và mô hình triển khai được xác định rõ.
- [ ] Ranh giới dữ liệu, quyền và tài nguyên của từng tenant được mô tả.
- [ ] Các chiều cấu hình có ảnh hưởng hành vi được liệt kê.
- [ ] Nguồn sự thật, thứ tự ưu tiên và version cấu hình được xác định.
- [ ] Có tenant profile đại diện cho gói, region, role, quota và lifecycle.
- [ ] Hành vi chung và hành vi riêng theo tenant được phân biệt.
- [ ] Có kiểm tra positive và negative cho tenant isolation.
- [ ] Tenant context được xác minh qua API, event, job, cache, search và storage.
- [ ] Role, entitlement và feature flag được kiểm tra độc lập và kết hợp.
- [ ] Giá trị mặc định, override, giá trị biên và xung đột cấu hình được kiểm tra.
- [ ] Tổ hợp được chọn theo equivalence, pairwise hoặc rủi ro có căn cứ.
- [ ] Tổ hợp nhiều chiều có rủi ro cao được kiểm tra sâu hơn khi cần.
- [ ] Dữ liệu và fixture được cô lập theo test run hoặc tenant scope.
- [ ] Provisioning, upgrade, downgrade, suspension và offboarding được kiểm tra.
- [ ] Migration và cleanup được xác minh theo tenant.
- [ ] Quota, rate limit và noisy-neighbor behavior được đo theo tenant.
- [ ] Locale, timezone, region và data residency được kiểm tra.
- [ ] Tích hợp riêng theo tenant có credential và endpoint đúng.
- [ ] Cấu hình rollout, cache propagation và rollback được xác minh.
- [ ] Báo cáo nêu rõ profile đã kiểm tra, profile chưa kiểm tra và rủi ro còn lại.
- [ ] Quality gate có điều kiện rõ cho isolation, entitlement, migration và cấu hình trọng yếu.

Điều chỉnh chiến lược cho hệ thống nhiều tenant và nhiều cấu hình đòi hỏi kiểm thử vượt ra ngoài tenant mặc định và luồng thành công phổ biến. Khi tenant được mô hình hóa rõ, cấu hình được version hóa, ranh giới dữ liệu và quyền được kiểm tra theo cả chiều cho phép lẫn từ chối, còn tổ hợp được chọn theo rủi ro, nhóm có thể tạo bằng chứng đại diện mà vẫn kiểm soát chi phí. Điều quan trọng là mọi kết luận phải nêu đúng profile và cấu hình đã được xác minh, đồng thời chỉ rõ khoảng trống còn lại trước khi mở rộng triển khai.
