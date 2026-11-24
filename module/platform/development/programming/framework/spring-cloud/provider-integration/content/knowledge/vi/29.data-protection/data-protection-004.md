# Phân loại dữ liệu, giới hạn quyền đọc và che thông tin nhạy cảm

Một ứng dụng Spring Boot có thể mã hóa dữ liệu trong database và object storage nhưng vẫn làm lộ thông tin nếu nhân viên hỗ trợ đều đọc được hồ sơ khách hàng đầy đủ, API trả thừa trường nhạy cảm hoặc log ghi nguyên request. Bảo vệ dữ liệu cần bắt đầu từ ba câu hỏi: **dữ liệu nào nhạy cảm, ai thực sự cần đọc, và người đó cần nhìn thấy bao nhiêu**.

Ba hoạt động cần phối hợp là **phân loại dữ liệu**, **kiểm soát quyền đọc** và **che/loại bỏ thông tin nhạy cảm**. Phân loại giúp hiểu mức độ tác động nếu dữ liệu bị lộ. Authorization giới hạn principal được truy cập tài nguyên, hàng, cột hoặc trường nào. Masking, redaction và tokenization giảm lượng dữ liệu thật được hiển thị khi nghiệp vụ không cần giá trị đầy đủ.

Bài thuộc chương **Bảo vệ dữ liệu** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud, bao gồm danh tính/quyền, storage, messaging, dữ liệu, bảo vệ secret, kiểm thử và đánh giá khác biệt giữa các cloud provider. Trọng tâm bài là thiết kế chính sách dữ liệu từ lúc thu thập tới lúc xóa, enforce quyền ở API và data platform, đồng thời tránh rò rỉ qua response, log, cache, báo cáo và môi trường kiểm thử.

## 1. Mục tiêu học tập và tình huống xuyên suốt

Sau bài học, bạn có thể:

1. Phân loại dữ liệu theo mức độ nhạy cảm, tác động và nghĩa vụ xử lý.
2. Phân biệt data classification, sensitivity label, data discovery và authorization policy.
3. Thiết kế quyền đọc theo least privilege, RBAC, ABAC, tenant, row, column và field.
4. Phân biệt masking, redaction, pseudonymization, tokenization, hashing và encryption.
5. Áp dụng response DTO riêng cho người dùng có mức quyền khác nhau trong Spring Boot.
6. Dùng các khả năng của AWS, Azure và Google Cloud để phát hiện dữ liệu, lọc quyền và che giá trị.
7. Bảo vệ dữ liệu trong log, trace, cache, event, export và môi trường non-production.
8. Kiểm thử cả truy cập được phép, truy cập bị từ chối và kết quả đã được che.

Tình huống xuyên suốt: `customer-service` quản lý hồ sơ khách hàng gồm tên, email, số điện thoại, địa chỉ, mã định danh, lịch sử giao dịch và ghi chú hỗ trợ. Nhân viên hỗ trợ cần xác minh khách hàng nhưng thường không cần xem đầy đủ mã định danh hoặc số điện thoại. Nhân viên xử lý thanh toán cần một số trường bổ sung; nhân viên phân tích chỉ cần dữ liệu đã de-identify.

~~~mermaid
flowchart TD
    A["Thu thập dữ liệu"] --> B["Phân loại và gắn nhãn"]
    B --> C["Xác định mục đích, retention và owner"]
    C --> D["Thiết kế quyền: principal / tenant / row / column"]
    D --> E["API và database enforce authorization"]
    E --> F["Mask / redact / tokenize theo vai trò"]
    F --> G["Response, export, log và analytics"]
    G --> H["Audit, review quyền và xóa theo retention"]
~~~

**Phân loại cho biết dữ liệu cần được bảo vệ ở mức nào. Authorization quyết định ai được đọc. Masking quyết định giá trị nào được hiển thị.** Ba việc này liên quan nhưng không thay thế nhau.

## 2. Phân loại dữ liệu trước khi thiết kế quyền

### 2.1. Phân loại theo tác động

Một mô hình đơn giản có thể dùng bốn mức:

| Mức | Ý nghĩa | Ví dụ | Cách xử lý gợi ý |
| --- | --- | --- | --- |
| **Public** | Được phép công bố rộng rãi | Tài liệu hướng dẫn, bảng giá đã công bố | Kiểm soát tính toàn vẹn và phiên bản |
| **Internal** | Chỉ dùng trong tổ chức | Mã vận hành, tài liệu quy trình nội bộ | Chỉ tài khoản tổ chức được truy cập |
| **Confidential** | Lộ dữ liệu gây tác động đáng kể | Email, số điện thoại, hợp đồng, lịch sử mua hàng | Quyền theo vai trò/mục đích, mã hóa, audit, masking |
| **Restricted** | Lộ dữ liệu có thể gây tổn hại nghiêm trọng hoặc vi phạm nghĩa vụ | Mật khẩu, access token, khóa mã hóa, số định danh đầy đủ, dữ liệu thanh toán đặc biệt nhạy cảm | Rất ít principal được truy cập, không log, mã hóa phù hợp, kiểm soát và giám sát tăng cường |

Tên mức chỉ là ví dụ. Tổ chức cần định nghĩa tiêu chí, owner, thời hạn lưu và biện pháp xử lý cho từng mức. Không nên tự coi nhãn `CONFIDENTIAL` là tiêu chuẩn pháp lý hoặc mặc định đã đáp ứng mọi quy định.

### 2.2. Phân loại theo loại dữ liệu

| Loại | Ví dụ | Câu hỏi cần đặt ra |
| --- | --- | --- |
| Direct identifier | Họ tên, email, số điện thoại, số hộ chiếu | Có cần lưu/hiển thị giá trị đầy đủ không? |
| Indirect identifier | Ngày sinh, khu vực, chức danh, mã bưu chính | Kết hợp nhiều trường có thể nhận diện cá nhân không? |
| Authentication secret | Password, API key, access token, refresh token | Có cần lưu không? Có thể dùng secret manager thay thế? |
| Financial | Số tài khoản, thông tin thanh toán, giao dịch | Ai cần đọc? Có yêu cầu che hoặc tokenization không? |
| Health/special-category | Dữ liệu sức khỏe hoặc dữ liệu nhạy cảm theo pháp luật áp dụng | Cơ sở xử lý, mục đích, quyền và retention là gì? |
| Business confidential | Giá hợp đồng, chiến lược, dữ liệu đối tác | Nhóm nào cần biết? Có giới hạn chia sẻ không? |
| Technical sensitive | Private key, certificate private material, connection string | Có thể loại khỏi response/log và chuyển sang secret/key management không? |

Một cột dữ liệu có thể thuộc nhiều nhóm. Ví dụ, mã khách hàng không trực tiếp là PII nhưng vẫn có thể là indirect identifier khi ghép với bảng khác.

### 2.3. Phân loại không chỉ dựa trên tên cột

Không phải mọi cột có tên `email` đều chứa email thật; cũng không phải cột `note` luôn vô hại. Cần xem:

- Nội dung thực tế và ngữ cảnh nghiệp vụ.
- Khả năng liên kết với nguồn dữ liệu khác.
- Mức độ nhận diện cá nhân hoặc bí mật thương mại.
- Tác động khi bị đọc, sửa, mất hoặc không sẵn sàng.
- Đối tượng sử dụng và mục đích truy cập.
- Nghĩa vụ pháp lý, hợp đồng, khu vực lưu trữ và thời hạn retention.

Ghi chú hỗ trợ tự do có thể chứa số thẻ, mã OTP hoặc thông tin sức khỏe dù schema chỉ khai báo kiểu text. Cần scan và quy định cách nhập liệu, hiển thị, lưu trữ và log.

### 2.4. Data inventory và ownership

Tạo inventory tối thiểu cho từng dataset/table/object:

| Thuộc tính | Ví dụ |
| --- | --- |
| Data asset | `customer_profile` |
| Owner | Customer Operations |
| Data steward | Nhóm quản trị dữ liệu |
| Classification | Confidential |
| Sensitive fields | `email`, `phone`, `national_id` |
| Purpose | Chăm sóc khách hàng và xử lý yêu cầu |
| Consumers | Customer API, support portal, analytics |
| Storage | PostgreSQL, object storage |
| Retention | Theo chính sách nghiệp vụ/pháp lý |
| Access policy | Support đọc masked; compliance được cấp quyền đầy đủ theo phê duyệt |
| Protection | TLS, at-rest encryption, row/column authorization, masking |
| Audit | Ai đọc/export, khi nào, mục đích và kết quả |

Inventory phải được cập nhật khi schema, data flow, API, consumer hoặc mục đích xử lý thay đổi. Không chỉ scan một lần lúc triển khai.

## 3. Sensitivity label và data classification khác nhau thế nào?

**Data classification** thường nhận diện loại dữ liệu có trong asset, ví dụ email, passport number, bank account hoặc customer identifier.

**Sensitivity label** thể hiện mức độ nhạy cảm hoặc quy tắc xử lý theo ngữ cảnh doanh nghiệp, ví dụ Public, Internal, Confidential hoặc Highly Confidential.

**Data discovery** là quá trình tìm asset và phát hiện dữ liệu nhạy cảm trong asset. **Authorization** là cơ chế thực thi quyền truy cập ở runtime.

| Khái niệm | Câu hỏi trả lời | Ví dụ |
| --- | --- | --- |
| Discovery | Dữ liệu nhạy cảm đang nằm ở đâu? | Tìm bucket chứa số định danh |
| Classification | Asset có loại dữ liệu nào? | Cột `national_id` là government identifier |
| Sensitivity label | Asset cần được xử lý theo mức nào? | `Restricted` |
| Authorization | Principal nào được đọc? | `support-agent` chỉ đọc hồ sơ thuộc tenant được phân công |
| Masking | Người đọc thấy giá trị nào? | Hiển thị `•••• 4821` thay vì số đầy đủ |

Một label chỉ có giá trị khi được gắn với chính sách thực thi. Việc thêm metadata `Restricted` vào object không tự động chặn người có quyền `GetObject`. Cần IAM/bucket policy, database permissions, API authorization và quy trình kiểm tra.

## 4. Nguyên tắc thiết kế quyền đọc

### 4.1. Least privilege và default deny

Mỗi principal chỉ nhận quyền cần cho nhiệm vụ hiện tại:

- Mặc định từ chối nếu chưa có rule cho phép.
- Cấp quyền theo resource, hành động, phạm vi dữ liệu và thời gian cần thiết.
- Tách quyền đọc, ghi, export, chia sẻ, quản trị và decrypt.
- Ưu tiên role/group thay vì gán quyền thủ công cho từng user.
- Review và thu hồi quyền khi đổi vị trí, rời nhóm hoặc kết thúc công việc.
- Không cấp quyền rộng chỉ để tránh lỗi 403 trong quá trình phát triển.

Ví dụ, một support agent có thể xem tên và trạng thái đơn hàng, nhưng chỉ thấy email/số điện thoại đã che. Người xử lý thanh toán có thể cần một trường payment token; điều đó không có nghĩa họ cần đọc ghi chú hỗ trợ hoặc toàn bộ lịch sử khách hàng.

### 4.2. RBAC và ABAC

**RBAC (Role-Based Access Control):** quyền gắn với role, ví dụ `support-agent`, `payment-operator`, `compliance-auditor`.

**ABAC (Attribute-Based Access Control):** quyết định dựa trên thuộc tính của principal, resource, action và environment, ví dụ:

- Principal thuộc team `support`.
- Resource có `tenantId` tương ứng với tenant được phép.
- Record có classification `Confidential`.
- Action là `read`.
- Yêu cầu phát sinh trong giờ làm việc hoặc từ thiết bị được quản lý.

RBAC dễ vận hành cho quyền chung; ABAC phù hợp khi cần điều kiện theo tenant, region, classification hoặc trạng thái nghiệp vụ. Hai cách có thể kết hợp.

### 4.3. Phân biệt quyền ở các lớp

| Lớp | Ví dụ quyền | Điều cần kiểm tra |
| --- | --- | --- |
| API endpoint | `customer:read` | Người gọi có được dùng chức năng không? |
| Resource/object | `customerId=123` | Người gọi có quyền với hồ sơ cụ thể không? |
| Tenant | `tenant_id` | Dữ liệu có thuộc tenant hiện tại không? |
| Row | Đơn hàng của region được phân công | Query có lọc đúng tập bản ghi không? |
| Column | Không đọc `national_id` | DB/query/view có giới hạn cột không? |
| Field/API response | Chỉ trả email masked | DTO có loại bỏ trường không cần thiết không? |
| Export/report | Chỉ export dữ liệu đã duyệt | Có quyền riêng, audit và giới hạn số lượng không? |
| Logs/traces | Không ghi PII/token | Logging pipeline có redaction và access control không? |

Một endpoint được bảo vệ bằng role không đủ nếu người dùng có thể thay `customerId` trong URL và đọc hồ sơ của tenant khác. Luôn kiểm tra authorization ở cấp object/tenant.

### 4.4. Tenant isolation

Không lấy tenant ID từ request body/query rồi tin tưởng trực tiếp. Tenant context nên được suy ra từ authenticated principal hoặc một cơ chế delegation đã xác minh.

Ví dụ repository query:

~~~java
public interface CustomerRepository extends JpaRepository<Customer, UUID> {
    Optional<Customer> findByIdAndTenantId(UUID id, UUID tenantId);
}
~~~

Service:

~~~java
@Service
public class CustomerQueryService {
    private final CustomerRepository repository;
    private final CurrentTenant currentTenant;

    public CustomerQueryService(
            CustomerRepository repository,
            CurrentTenant currentTenant) {
        this.repository = repository;
        this.currentTenant = currentTenant;
    }

    @PreAuthorize("hasAuthority('customer:read')")
    public Customer findVisibleCustomer(UUID customerId) {
        UUID tenantId = currentTenant.requiredTenantId();

        return repository.findByIdAndTenantId(customerId, tenantId)
                .orElseThrow(() -> new CustomerNotFoundException(customerId));
    }
}
~~~

Ví dụ cần bật method security bằng `@EnableMethodSecurity` và cung cấp `CurrentTenant` lấy tenant từ security context đã xác thực. Không cho client truyền `tenantId` tùy ý để vượt qua ranh giới dữ liệu.

### 4.5. Row-level security ở database

Với dữ liệu multi-tenant, có thể bổ sung Row-Level Security (RLS) ở database để giảm nguy cơ query thiếu tenant predicate. RLS không thay authorization ở ứng dụng; nó là một lớp phòng vệ bổ sung.

Ví dụ PostgreSQL minh họa:

~~~sql
ALTER TABLE customer_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE customer_profile FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_customer_read
ON customer_profile
FOR SELECT
USING (
  tenant_id = current_setting('app.tenant_id', true)::uuid
);
~~~

Ứng dụng phải đặt tenant context an toàn trong cùng transaction/connection trước query, ví dụ bằng `SET LOCAL` hoặc `set_config(..., true)` trong transaction. Với connection pool, không để session variable của tenant trước rò sang request tiếp theo. Role ứng dụng không nên có quyền owner/superuser hoặc `BYPASSRLS`, vì các quyền đó có thể vượt qua policy. Kiểm thử với đúng database role mà production dùng.

## 5. Giới hạn quyền ở row, column và field

### 5.1. Row-level access

Row-level access giới hạn **bản ghi nào** principal có thể đọc.

Ví dụ:

- Support team chỉ đọc khách hàng thuộc region được phân công.
- Tenant A không đọc được row của tenant B.
- Nhân viên chỉ xem ticket đang được assign cho mình.
- Analyst chỉ xem dữ liệu thuộc business unit được duyệt.

Có thể thực thi tại database (RLS), data warehouse, API query layer hoặc nhiều lớp cùng lúc. Không dùng filter ở giao diện làm biện pháp bảo mật; client có thể tự gọi API hoặc thay query.

### 5.2. Column-level access

Column-level access giới hạn **trường nào** được phép truy vấn:

- Nhóm vận hành đọc `customer_id`, `status`, `created_at`.
- Nhóm chăm sóc khách hàng đọc `name`, `email`, `phone` nhưng theo chính sách masking.
- Nhóm compliance có quyền xem một số trường nhạy cảm theo phê duyệt.
- Analyst không được truy cập `national_id`, `payment_token` hoặc free-text note.

Có thể dùng database grants, secure views, column policy tags hoặc data lake permissions. Cần kiểm tra cả `SELECT *`, view, stored procedure, export và query engine tích hợp.

### 5.3. Field-level authorization trong API

API nên trả DTO phù hợp với use case. Không serialize trực tiếp entity JPA chứa toàn bộ cột nhạy cảm.

~~~java
public record CustomerSupportView(
        UUID id,
        String displayName,
        String maskedEmail,
        String maskedPhone,
        String accountStatus) {
}

public record CustomerComplianceView(
        UUID id,
        String displayName,
        String email,
        String phone,
        String nationalId) {
}
~~~

Service có thể tách rõ quyền:

~~~java
@Service
public class CustomerViewService {

    @PreAuthorize("hasAuthority('customer:read')")
    public CustomerSupportView supportView(UUID customerId) {
        Customer customer = loadAuthorizedCustomer(customerId);

        return new CustomerSupportView(
                customer.getId(),
                customer.getDisplayName(),
                Masking.maskEmail(customer.getEmail()),
                Masking.maskPhone(customer.getPhone()),
                customer.getAccountStatus().name());
    }

    @PreAuthorize("hasAuthority('customer:read:restricted')")
    public CustomerComplianceView complianceView(UUID customerId) {
        Customer customer = loadAuthorizedCustomer(customerId);

        return new CustomerComplianceView(
                customer.getId(),
                customer.getDisplayName(),
                customer.getEmail(),
                customer.getPhone(),
                customer.getNationalId());
    }
}
~~~

`loadAuthorizedCustomer` vẫn phải kiểm tra tenant/object ownership. `customer:read:restricted` phải được cấp theo quy trình phê duyệt và audit. DTO không thay authorization; nó giúp giới hạn dữ liệu thực sự được serialize.

### 5.4. Không dựa vào ẩn trường ở giao diện

Ẩn cột hoặc thay giá trị bằng dấu sao ở frontend không bảo vệ API nếu JSON vẫn chứa dữ liệu đầy đủ. Một người dùng có thể xem Network tab, gọi endpoint trực tiếp hoặc tải file export.

Hãy bảo đảm server chỉ gửi trường người nhận được phép xem. Kiểm tra response body, GraphQL resolver, WebSocket event, search endpoint và export file.

## 6. Masking, redaction, tokenization và pseudonymization

| Kỹ thuật | Cách hoạt động | Có khôi phục giá trị gốc? | Dùng khi |
| --- | --- | --- | --- |
| **Masking** | Thay một phần/toàn bộ giá trị bằng ký tự thay thế | Thường không từ kết quả đã mask | Hiển thị cho support hoặc báo cáo |
| **Redaction** | Xóa hẳn trường/đoạn nhạy cảm khỏi output | Không, nếu không có bản gốc riêng | Log, chia sẻ tài liệu, response |
| **Static masking** | Tạo bản dữ liệu đã thay đổi trước khi cấp cho môi trường khác | Thường không | Test/dev, data sandbox |
| **Dynamic masking** | Che giá trị lúc truy vấn/hiển thị dựa trên quyền | Dữ liệu gốc vẫn tồn tại | Support portal, database query |
| **Pseudonymization** | Thay identifier bằng giá trị giả có thể liên kết qua mapping/key | Có thể, nếu còn mapping/key | Analytics, nghiên cứu |
| **Tokenization** | Thay giá trị bằng token, mapping nằm trong vault/dịch vụ riêng | Có, qua token service được kiểm soát | Payment/account identifier |
| **Hashing** | Tạo digest một chiều | Không trực tiếp | So sánh/đối chiếu khi thiết kế phù hợp |
| **Encryption** | Mã hóa bằng key | Có, khi có key | Lưu trữ/truyền dữ liệu cần khôi phục |

### 6.1. Partial masking

Ví dụ:

| Giá trị gốc | Giá trị hiển thị |
| --- | --- |
| `phuong@example.com` | `p•••••@example.com` |
| `0901234821` | `••••••4821` |
| `4111111111111234` | `••••••••••••1234` |
| `AB1234567` | `•••••4567` |

Chỉ hiển thị phần cần thiết để người dùng nhận diện. Với một số loại dữ liệu, ngay cả bốn ký tự cuối cũng có thể là thông tin nhạy cảm; quyết định dựa trên threat model và quy định áp dụng.

### 6.2. Redaction

Redaction loại bỏ giá trị khỏi bản được chia sẻ:

~~~text
Request body:
{"email":"phuong@example.com","accessToken":"eyJ..."}

Log đã redacted:
{"email":"[REDACTED]","accessToken":"[REDACTED]"}
~~~

Redaction phù hợp với log, error message, support bundle và tài liệu gửi ra ngoài. Nếu hệ thống vẫn cần correlation, có thể dùng request ID ngẫu nhiên hoặc identifier giả đã được kiểm soát.

### 6.3. Pseudonymization và tokenization

Pseudonymization thay identifier bằng mã thay thế:

~~~text
customerId: 8421 -> customerRef: CUST-7F2A
~~~

Mapping phải được bảo vệ riêng, quyền truy cập hạn chế và audit. Nếu cùng một token xuất hiện ở nhiều dataset, người nhận có thể liên kết bản ghi; deterministic tokenization có lợi cho join nhưng tăng khả năng liên kết.

Tokenization thường dùng một vault hoặc dịch vụ quản lý mapping. Không đặt bảng mapping trong cùng database/schema và cùng quyền đọc với dữ liệu đã token hóa nếu mục tiêu là giảm khả năng re-identification.

### 6.4. Hashing không mặc định là anonymization

Hash email, số điện thoại hoặc mã định danh có thể bị dò ngược bằng dictionary/brute force vì không gian giá trị nhỏ và có cấu trúc. Hash không salt còn dễ bị so khớp giữa các hệ thống.

- Dùng password hashing chuyên dụng (Argon2id, bcrypt hoặc PBKDF2 theo policy) cho mật khẩu.
- Với identifier cần deterministic lookup, cân nhắc keyed HMAC với key được bảo vệ thay vì hash thuần.
- Nếu cần khôi phục giá trị, dùng tokenization hoặc encryption có quản lý khóa.
- Không gọi dữ liệu là anonymous chỉ vì đã bỏ tên; các trường kết hợp vẫn có thể tái nhận diện.

### 6.5. Encryption và masking có mục đích khác nhau

Encryption bảo vệ giá trị lưu trữ/truyền khi không có key; ứng dụng được cấp quyền decrypt vẫn nhìn thấy plaintext. Masking giới hạn giá trị được hiển thị trong một ngữ cảnh; dữ liệu gốc vẫn có thể tồn tại ở database. Có thể dùng cả hai: encrypt at rest, authorize người đọc, sau đó mask response.

## 7. Masking trong Spring Boot

### 7.1. Viết masking function có mục tiêu

Ví dụ đơn giản cho email và phone:

~~~java
package com.example.customer;

public final class Masking {
    private Masking() {
    }

    public static String maskEmail(String value) {
        if (value == null || value.isBlank()) {
            return value;
        }

        int at = value.indexOf('@');
        if (at <= 0 || at == value.length() - 1) {
            return "[REDACTED]";
        }

        String local = value.substring(0, at);
        String domain = value.substring(at + 1);
        return local.substring(0, 1) + "••••@" + domain;
    }

    public static String maskPhone(String value) {
        if (value == null || value.isBlank()) {
            return value;
        }

        String digits = value.replaceAll("\\D", "");
        if (digits.length() < 4) {
            return "[REDACTED]";
        }

        return "••••••" + digits.substring(digits.length() - 4);
    }
}
~~~

Đây là ví dụ hiển thị, không phải thư viện xử lý mọi định dạng quốc tế. Trước khi mask, xác định dữ liệu đã normalize ra sao và người nhận có cần giữ mã quốc gia, extension hoặc domain hay không. Không dùng kết quả mask làm identifier chính hoặc làm dữ liệu đối chiếu chính xác.

### 7.2. Authorization trước, masking sau

Một flow phù hợp:

1. Xác thực caller và xác định tenant.
2. Kiểm tra quyền đọc object/record.
3. Tải đúng tập trường được phép.
4. Chọn response DTO theo quyền và mục đích.
5. Mask các trường cần che.
6. Serialize response.
7. Ghi audit event không chứa plaintext.

Không tải toàn bộ entity, ghi entity vào log rồi mới mask ở controller. Plaintext đã đi qua các thành phần trung gian có thể bị lưu lại.

### 7.3. Dùng method security

Bật method security:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Dùng quyền riêng cho dữ liệu bị hạn chế:

~~~java
@PreAuthorize("hasAuthority('customer:read:restricted')")
public CustomerComplianceView readRestrictedProfile(UUID customerId) {
    // Kiểm tra tenant/object ownership trước khi đọc field nhạy cảm.
    return customerViewService.loadComplianceView(customerId);
}
~~~

Quyền `customer:read:restricted` phải đến từ identity provider/authorization server hoặc policy engine đã được tin cậy. Không cho client tự gửi role hoặc authority trong request header.

### 7.4. Jackson và serialization

Không coi `@JsonIgnore`, `@JsonView` hoặc một Jackson filter là authorization đầy đủ. Chúng có thể hữu ích cho serialization, nhưng dữ liệu vẫn có thể bị truy cập qua endpoint khác, log, mapper hoặc code nội bộ.

Ưu tiên:

- DTO tách theo use case.
- Explicit mapping từ entity sang DTO.
- Không serialize entity trực tiếp.
- Không trả raw database projection cho controller mà không review field.
- Test JSON thực tế để bảo đảm field nhạy cảm không xuất hiện.
- Không dùng một global serializer để che tất cả field nếu một số endpoint cần quyền khác nhau.

## 8. Giới hạn quyền và masking trên các cloud provider

Các dịch vụ cloud có thể hỗ trợ discovery, classification, fine-grained access hoặc masking ở các lớp khác nhau. Chúng không thay thế authorization của Spring Boot API.

### 8.1. AWS: Macie, Lake Formation và IAM

**Amazon Macie** giúp phát hiện dữ liệu nhạy cảm trong Amazon S3:

- Duy trì inventory bucket và đánh giá cấu hình bảo mật/access.
- Dùng automated sensitive data discovery hoặc discovery jobs để phân tích object.
- Nhận diện loại dữ liệu theo managed identifiers và custom identifiers.
- Tạo finding để nhóm bảo mật điều tra và xử lý.

Macie là công cụ discovery/monitoring; nó không tự động biến mọi object có finding thành object bị từ chối đọc. Cần xử lý kết quả bằng IAM, bucket policy, lifecycle, encryption và quy trình remediation.

**AWS Lake Formation** cung cấp data filters để kiểm soát dữ liệu trong Data Catalog:

- Column-level filtering: chỉ cấp một số cột.
- Row-level filtering: chỉ trả về hàng khớp biểu thức.
- Cell-level filtering: kết hợp giới hạn row và column.
- Có thể áp dụng với các query engine tích hợp như Amazon Athena và Redshift Spectrum theo hỗ trợ của dịch vụ/region.

Ví dụ data filter về mặt ý tưởng:

~~~json
{
  "Name": "support-orders",
  "DatabaseName": "sales",
  "TableName": "orders",
  "RowFilter": {
    "FilterExpression": "tenant_id='tenant-42'"
  },
  "ColumnWildcard": {
    "ExcludedColumnNames": ["national_id", "payment_token"]
  }
}
~~~

Đây là minh họa cấu trúc filter, không phải chính sách hoàn chỉnh để áp dụng trực tiếp. Cần tạo filter qua Lake Formation API/console và grant `SELECT` cho principal tương ứng. Lake Formation data filtering chỉ áp dụng cho các engine/luồng được hỗ trợ; S3 object access vẫn cần IAM và bucket policy.

Với ứng dụng Spring Boot đọc S3 trực tiếp, dùng IAM role/task role/workload identity phù hợp, giới hạn bucket/prefix và action cần thiết. Không kỳ vọng Lake Formation tự giới hạn mọi request `GetObject` từ SDK.

### 8.2. Azure: Microsoft Purview và SQL Dynamic Data Masking

**Microsoft Purview** hỗ trợ data discovery/classification và sensitivity labeling cho các nguồn được hỗ trợ:

- Classification nhận diện loại dữ liệu như tên người, số giấy phép hoặc thông tin tài khoản.
- Sensitivity label mô tả mức độ nhạy cảm theo chính sách tổ chức.
- Scan/catalog giúp biết dữ liệu đang nằm ở đâu và ai là owner.
- Label/classification là metadata quản trị; phải nối chúng với quyền, policy và quy trình bảo vệ phù hợp.

Cần kiểm tra nguồn dữ liệu, licensing, trạng thái preview/GA và lộ trình sản phẩm trước khi chọn tính năng Purview cụ thể cho hệ thống mới. Không giả định một nhãn trong catalog tự động chặn API đọc dữ liệu.

**Azure SQL Dynamic Data Masking (DDM)** che giá trị trong query result cho principal không có quyền xem unmasked data:

~~~sql
ALTER TABLE dbo.Customer
ALTER COLUMN Email
ADD MASKED WITH (FUNCTION = 'email()');

ALTER TABLE dbo.Customer
ALTER COLUMN Phone
ADD MASKED WITH (FUNCTION = 'partial(0, "XXXXXX", 4)');
~~~

Người dùng được cấp quyền đọc nhưng không có `UNMASK` sẽ nhận kết quả đã mask theo policy. Có thể cấp quyền `UNMASK` ở database/schema/table/column scope tùy phiên bản và cú pháp được hỗ trợ.

~~~sql
GRANT UNMASK ON dbo.Customer (Email) TO CustomerComplianceReader;
~~~

DDM **không thay đổi dữ liệu lưu trong bảng** và không phải cơ chế ngăn mọi truy cập đặc quyền: các principal có quyền quản trị như server admin, Entra admin hoặc `db_owner` có thể thấy dữ liệu gốc. DDM giúp giảm lộ dữ liệu cho người dùng truy vấn không đặc quyền; vẫn cần database permissions, row/column security và kiểm soát quyền admin.

### 8.3. Google Cloud: Sensitive Data Protection và BigQuery

**Sensitive Data Protection** giúp inspect, classify và de-identify dữ liệu trong text, storage và một số data platform:

- Built-in infoType detectors và custom detectors.
- Redaction và replacement.
- Masking một phần giá trị.
- Crypto-based tokenization/pseudonymization.
- De-identification cho dataset phân tích hoặc payload ứng dụng.

Chọn transformation theo nhu cầu. Redaction loại bỏ dữ liệu; masking thay một phần ký tự; tokenization có thể reversible nếu giữ key/mapping phù hợp. Không mặc định mọi transformation đều anonymize dữ liệu hoàn toàn.

**BigQuery** hỗ trợ kiểm soát quyền ở nhiều mức:

- IAM cho project/dataset/table.
- Row-level security để lọc hàng theo policy.
- Column-level access control bằng policy tags để giới hạn cột nhạy cảm.
- Data masking policy cho người dùng được phép query nhưng chỉ thấy giá trị đã che, theo cấu hình được hỗ trợ.

Ví dụ row access policy minh họa:

~~~sql
CREATE ROW ACCESS POLICY region_support
ON `analytics-prod.sales.orders`
GRANT TO ("group:support-north@example.com")
FILTER USING (region = "north");
~~~

Cú pháp/định danh principal phải được điều chỉnh theo project, dataset, table và group thực tế. Policy tags cần được gắn vào cột và cấp quyền taxonomy tương ứng; việc gắn nhãn đơn thuần chưa đủ nếu chưa có data policy và IAM phù hợp.

### 8.4. So sánh nhanh

| Nhu cầu | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Phát hiện dữ liệu nhạy cảm | Amazon Macie cho S3 | Microsoft Purview và SQL discovery/classification | Sensitive Data Protection |
| Row-level access | Lake Formation data filters/RLS cho engine tích hợp | Database RLS và các data service policy phù hợp | BigQuery row-level security |
| Column-level access | Lake Formation column filters | SQL permissions/views và khả năng dịch vụ | BigQuery policy tags |
| Dynamic masking | Tùy query/data service; Lake Formation filters là access filtering, không phải mask value | Azure SQL Dynamic Data Masking | BigQuery data masking policies |
| De-identification/tokenization | Dùng ứng dụng/dịch vụ phù hợp và KMS | Dùng ứng dụng/Key Vault hoặc dịch vụ phù hợp | Sensitive Data Protection transformations |
| API authorization | IAM role cho workload + Spring Security/API policy | Managed Identity/Entra ID + Spring Security/API policy | Workload Identity/service account + Spring Security/API policy |

## 9. Bảo vệ log, trace, event và error response

Một ứng dụng có thể bảo vệ database nhưng vô tình tạo thêm bản sao plaintext ở log aggregator, tracing backend, message queue hoặc support bundle.

### 9.1. Dữ liệu không nên log trực tiếp

Thông thường không log:

- Password, access token, refresh token, API key.
- Private key, encryption key, connection string.
- Số thẻ thanh toán, số định danh, ngày sinh đầy đủ.
- Email/số điện thoại đầy đủ nếu không có mục đích và quyền rõ.
- Nội dung request/response có PII hoặc dữ liệu restricted.
- SQL bind parameter chứa dữ liệu nhạy cảm.
- Toàn bộ entity/DTO hoặc exception message có payload.

Có thể log actor ID giả danh, resource ID nội bộ, request ID, action, classification, outcome, policy decision và correlation ID.

Ví dụ:

~~~java
log.info(
        "customer_read actorRef={} customerRef={} view={} outcome={}",
        actorReference,
        customerReference,
        "SUPPORT_MASKED",
        "ALLOWED");
~~~

Không log object customer đầy đủ để tiện debug. Audit log cần đủ thông tin điều tra nhưng phải tuân theo classification của chính hệ thống log.

### 9.2. Redact trước khi log

Không dựa vào việc log aggregator sẽ che dữ liệu sau khi thu thập. Nếu raw PII đã đi vào collector, buffer, disk hoặc third-party telemetry, dữ liệu đã bị sao chép.

- Chỉ log các trường allowlist.
- Dùng structured logging thay cho nối toàn bộ object vào message.
- Redact request header như `Authorization`, cookie và API key.
- Tắt logging body cho endpoint nhận dữ liệu nhạy cảm.
- Kiểm tra exception, validation error và SQL logging.
- Giới hạn quyền đọc log và retention.
- Test log output bằng dữ liệu sentinel để phát hiện leak.

### 9.3. Tracing và metrics

Distributed tracing có thể tự động capture URL, header, query parameter và exception. Không đưa email, token hoặc account number vào span attribute. Metric label không nên chứa user ID hoặc giá trị nhạy cảm vì vừa lộ dữ liệu vừa tạo cardinality cao.

### 9.4. Event và dead-letter queue

Message broker thường giữ payload để retry, replay hoặc xử lý lỗi. Nếu event chứa PII:

- Chỉ đưa field cần cho consumer.
- Cân nhắc token/reference thay vì payload đầy đủ.
- Phân quyền topic/subscription và DLQ riêng.
- Áp dụng retention, encryption và audit.
- Mask dữ liệu trong event dành cho analytics.
- Không đưa secret hoặc authentication token vào message.
- Kiểm soát quyền replay/export vì đây là cách trích xuất dữ liệu hàng loạt.

## 10. Cache, search, export và môi trường non-production

### 10.1. Cache có thể làm rò dữ liệu giữa người dùng

Nếu cache một response đã được mask theo quyền người dùng, cache key phải phản ánh tenant, principal/role hoặc view type phù hợp. Nếu cache key chỉ là `customerId`, response đầy đủ từ người có quyền cao có thể bị trả lại cho người có quyền thấp.

Các nguyên tắc:

- Authorization phải được kiểm tra trước khi trả cache hit.
- Không dùng cùng cache entry cho full view và masked view nếu không có partition rõ.
- Tenant phải nằm trong cache key và lookup path.
- TTL phù hợp với thời gian thu hồi quyền và cập nhật dữ liệu.
- Invalidate cache khi role/permission thay đổi.
- Không cache plaintext restricted lâu hơn mức cần thiết.

### 10.2. Search index

Search engine có thể tạo bản sao dữ liệu từ database. Phân loại và quyền đọc phải theo tới index:

- Loại field nhạy cảm khỏi index nếu không cần tìm kiếm.
- Nếu cần lookup, dùng token/keyed hash có kiểm soát.
- Không trả snippet/highlight chứa field mà caller không được đọc.
- Áp dụng tenant filter và authorization trên từng query.
- Kiểm soát export, autocomplete, suggestion và debug endpoint.

### 10.3. Export và báo cáo

Export thường có rủi ro cao vì tạo file lâu dài, có thể tải về và chia sẻ. Cần:

- Quyền riêng cho export, không kế thừa mặc định quyền đọc từng record.
- Giới hạn row count, field, tenant và thời gian.
- Mask hoặc loại field theo classification.
- Audit người tạo, mục đích, phạm vi và người tải.
- Link tải có thời hạn và quyền truy cập được kiểm tra lại.
- Retention và xóa file tạm.
- Bảo vệ file đã tải xuống theo mức nhạy cảm.

### 10.4. Dữ liệu test và staging

Không copy nguyên database production sang môi trường dev rồi dựa vào việc mạng nội bộ để bảo vệ.

- Dùng synthetic data khi có thể.
- Static masking trước khi tạo snapshot non-production.
- Tokenize hoặc pseudonymize identifier nếu cần giữ quan hệ join.
- Giữ nguyên phân phối/format cần cho test nhưng không giữ giá trị thật.
- Kiểm tra dữ liệu trong backup, object, log và event sau khi tạo bản test.
- Hạn chế quyền và retention của bản sao.

## 11. Retention, deletion và data minimization

Phân loại cần gắn với vòng đời dữ liệu:

1. Thu thập đúng mục đích và chỉ các trường cần thiết.
2. Gắn owner, classification, retention và access policy.
3. Lưu ở nơi có quyền và bảo vệ phù hợp.
4. Chỉ chia sẻ với consumer có mục đích được phê duyệt.
5. Mask/de-identify khi chuyển sang analytics, support hoặc test.
6. Xóa hoặc anonymize khi hết mục đích/retention, theo nghĩa vụ pháp lý và hợp đồng.
7. Xác minh bản sao trong cache, index, export, event, backup và replica theo chính sách.

Không lưu dữ liệu “phòng khi sau này cần” nếu chưa có mục đích, căn cứ xử lý và thời hạn. Bản backup có retention riêng; quy trình xóa phải mô tả rõ cách xử lý backup/archive theo khả năng dịch vụ.

## 12. Kiểm thử phân loại, quyền và masking

### 12.1. Role matrix

Lập ma trận quyền trước khi viết test:

| Actor | Hồ sơ cùng tenant | Hồ sơ tenant khác | Email/phone | National ID | Export |
| --- | --- | --- | --- | --- | --- |
| Support agent | Đọc | Từ chối | Masked | Không có field | Không |
| Payment operator | Chỉ field cần cho payment | Từ chối | Theo mục đích | Không có field | Không |
| Compliance reader | Theo scope phê duyệt | Theo scope phê duyệt | Full nếu được duyệt | Full nếu được duyệt | Có audit/phê duyệt |
| Analyst | Dataset de-identified | Theo dataset policy | Tokenized/removed | Removed | Dataset được duyệt |
| Anonymous | Từ chối | Từ chối | Không có | Không có | Không |

Ma trận phải khớp với policy ở IdP, Spring Security, database, cloud storage và data warehouse.

### 12.2. Test authorization dương và âm

Kiểm thử:

- Support đọc record cùng tenant và nhận DTO masked.
- Support thay `customerId` sang tenant khác bị từ chối hoặc nhận 404 theo chính sách chống enumeration.
- Support không thể gọi restricted endpoint.
- Payment operator chỉ đọc field cần thiết.
- Compliance reader cần quyền cụ thể và hành động được audit.
- Anonymous/expired identity không truy cập.
- Tenant context không bị giữ lại qua connection pool hoặc async executor.

Không chỉ test HTTP status; kiểm tra response body không chứa trường nhạy cảm dù endpoint trả 200.

### 12.3. Test masking và serialization

Ví dụ unit test:

~~~java
@Test
void masksEmailForSupportView() {
    assertThat(Masking.maskEmail("phuong@example.com"))
            .isEqualTo("p••••@example.com");
}

@Test
void masksPhoneAndKeepsOnlyLastFourDigits() {
    assertThat(Masking.maskPhone("0901234821"))
            .isEqualTo("••••••4821");
}
~~~

Ngoài unit test, serialize DTO và kiểm tra JSON:

- Không có `nationalId`.
- Không có email/phone gốc.
- Không có access token hoặc internal key reference không cần thiết.
- Không có field ẩn chỉ vì frontend không hiển thị.

### 12.4. Test database policy và cloud policy

- Chạy query bằng đúng runtime database role; xác minh RLS.
- Dùng principal thiếu `UNMASK` để xác minh Azure SQL trả masked result.
- Dùng principal BigQuery không có policy tag permission để xác minh column bị chặn/mask và row policy lọc đúng.
- Với Lake Formation, kiểm tra query qua đúng engine tích hợp và principal được grant filter.
- Xác minh Macie finding được chuyển thành remediation/action; không giả định finding tự chặn truy cập.
- Test IAM/bucket policy trực tiếp nếu Spring Boot gọi object storage.

### 12.5. Test log, cache và export

- Gửi request sentinel có email/token giả; assert log không chứa raw value.
- Đọc masked response rồi đổi role; đảm bảo cache không trả sai view.
- Thử cache key giữa hai tenant; không có cross-tenant hit.
- Export phải áp dụng cùng authorization/masking như API.
- DLQ, trace và error response không chứa payload restricted.
- Xác minh retention và xóa dữ liệu test.

## 13. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| UI che email nhưng API trả email đầy đủ | Chỉ masking ở frontend | Mask/loại field ở server response |
| User đọc được record tenant khác | Thiếu object/tenant authorization | Tenant-scoped query và database RLS |
| `SELECT *` lộ cột nhạy cảm | DB role quá rộng hoặc thiếu column policy | Grant theo cột/view, giảm quyền |
| Azure DDM vẫn trả plaintext | Caller có `UNMASK` hoặc quyền admin đặc biệt | Review role, `UNMASK` scope và admin principal |
| BigQuery user thấy mọi hàng | Row access policy chưa gắn hoặc IAM principal quá rộng | Kiểm tra policy, principal và quyền table |
| Lake Formation filter không có tác dụng | Query engine/đường truy cập không tích hợp hoặc caller có đường S3 trực tiếp | Kiểm tra engine, Lake Formation grants và IAM/S3 access |
| Macie tìm thấy PII nhưng object vẫn đọc được | Macie là discovery/monitoring, không phải enforcement | Remediate bằng IAM, bucket policy và workflow |
| Log chứa request body | Logging interceptor/trace capture quá rộng | Allowlist log field, tắt body logging, redact trước collector |
| Cache trả dữ liệu full cho support | Cache key không phân biệt role/view | Partition cache hoặc cache dữ liệu theo quyền |
| Tokenized data vẫn tái nhận diện | Mapping/token key bị lộ hoặc token deterministic dùng quá rộng | Bảo vệ vault/key, giới hạn linkability và quyền re-identify |
| Dữ liệu staging còn PII thật | Masking chưa chạy trên backup/export/index | Kiểm tra toàn bộ data flow và tạo lại bản non-production |

## 14. Bài tập thực hành tổng hợp

`customer-service` lưu hồ sơ nhiều tenant trên PostgreSQL và object storage. Ứng dụng chạy trên Spring Boot, dùng một cloud provider cho object storage và một data warehouse để phân tích.

Dữ liệu gồm tên, email, phone, national ID, địa chỉ, payment token, support note và lịch sử đơn hàng.

**Nhiệm vụ:**

1. Phân loại từng field thành Public/Internal/Confidential/Restricted và ghi rõ owner, purpose, retention.
2. Thiết kế role matrix cho support, payment, compliance, analyst và anonymous.
3. Bảo đảm query luôn lọc tenant theo identity đã xác thực; cân nhắc database RLS.
4. Tạo `CustomerSupportView` chỉ chứa field cần thiết và email/phone đã mask.
5. Tạo endpoint restricted có quyền riêng, audit và kiểm tra tenant/object ownership.
6. Thiết kế redaction cho log, trace, exception và DLQ.
7. Tạo dataset analytics đã tokenized hoặc de-identified; hạn chế quyền re-identify.
8. Đối chiếu khả năng discovery, row/column policy và masking của AWS, Azure hoặc Google Cloud đang sử dụng.
9. Viết test dương/âm cho tenant isolation, `UNMASK`, column policy, cache, export và log.
10. Tạo quy trình review quyền và xóa dữ liệu khi hết retention.

**Câu hỏi tự đánh giá:**

- Classification khác authorization như thế nào?
- Vì sao sensitivity label không tự động chặn API đọc dữ liệu?
- Vì sao tenant ID không nên được tin tưởng nếu chỉ lấy từ query parameter?
- Row-level security và column-level security giải quyết hai vấn đề gì?
- Dynamic masking khác encryption và static masking ra sao?
- Vì sao hash email không mặc định là anonymization?
- Macie có tự động chặn `GetObject` khi phát hiện PII không?
- Vì sao Azure SQL DDM không thay thế database authorization?
- BigQuery policy tags và row-level security kiểm soát phần dữ liệu nào?
- Vì sao cache key cần xét tenant và quyền?
- Vì sao không nên log raw request rồi mới mask ở log aggregator?

**Đáp án định hướng:** classification mô tả độ nhạy và loại dữ liệu; authorization quyết định principal được đọc; label chỉ là metadata nếu chưa gắn enforcement; tenant lấy từ identity đã xác thực; RLS giới hạn hàng, column security giới hạn cột; DDM che query result nhưng dữ liệu gốc vẫn tồn tại; hash identifier có thể bị dò; Macie discovery không phải enforcement; DDM không ngăn principal đặc quyền; policy tags giới hạn cột còn row policy lọc hàng; cache phải tách tenant/view; redaction cần diễn ra trước khi dữ liệu vào log pipeline.

## 15. Tài liệu tham khảo chính thức

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên log, masking/sanitization, quyền đọc và retention của log.
- [Amazon Macie – Discovering sensitive data](https://docs.aws.amazon.com/macie/latest/user/data-classification.html): automated discovery và targeted discovery jobs cho S3.
- [Amazon Macie – Monitoring data security and privacy](https://docs.aws.amazon.com/macie/latest/user/monitoring-s3.html): inventory bucket, access/security findings và sensitive data findings.
- [AWS Lake Formation – Data filtering and cell-level security](https://docs.aws.amazon.com/lake-formation/latest/dg/data-filtering.html): row-level, column-level và cell-level filtering.
- [AWS Lake Formation – Row-level security policies](https://docs.aws.amazon.com/lake-formation/latest/dg/rls-policies.html): policy filter và tương tác với column permissions.
- [Microsoft Purview – Data classification](https://learn.microsoft.com/azure/purview/concept-classification): system/custom classifications và phân biệt classification với sensitivity labels.
- [Azure SQL – Dynamic Data Masking](https://learn.microsoft.com/en-us/azure/azure-sql/database/dynamic-data-masking-overview): masking query result, granular `UNMASK` và giới hạn của DDM.
- [Google Cloud – Sensitive Data Protection overview](https://docs.cloud.google.com/sensitive-data-protection/docs/sensitive-data-protection-overview): inspect, classify và de-identify dữ liệu.
- [Google Cloud – De-identify and re-identify sensitive data](https://docs.cloud.google.com/sensitive-data-protection/docs/inspect-sensitive-text-de-identify): pseudonymization/tokenization và re-identification.
- [Google Cloud – BigQuery row-level security](https://docs.cloud.google.com/bigquery/docs/row-level-security-intro): lọc hàng theo user/group.
- [Google Cloud – BigQuery data masking and policy tags](https://docs.cloud.google.com/bigquery/docs/column-level-security-intro): kiểm soát cột và masking trong query.

**Ghi nhớ:** phân loại dữ liệu là nền tảng để quyết định quyền và cách hiển thị; quyền phải được enforce ở server/data layer; masking phải diễn ra trước khi dữ liệu đi vào response, log, cache hoặc export. Một hệ thống bảo vệ tốt không chỉ giữ dữ liệu mã hóa mà còn bảo đảm **đúng người, đúng mục đích, đúng phạm vi và đúng mức thông tin**.
