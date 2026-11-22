# Khóa lạc quan, phiên bản bản ghi và cập nhật có điều kiện

Trong hệ thống có nhiều người dùng, service hoặc worker cùng cập nhật một dữ liệu, một vấn đề phổ biến là **lost update**: hai bên đọc cùng một trạng thái, mỗi bên tính ra thay đổi riêng, rồi lần ghi sau vô tình ghi đè kết quả của lần ghi trước. Cả hai request có thể đều trả thành công, database vẫn hợp lệ về cú pháp, nhưng một thay đổi nghiệp vụ đã bị mất.

**Khóa lạc quan (optimistic locking)** giải quyết tình huống này bằng cách để mỗi lần đọc mang theo một **phiên bản bản ghi (record version)**. Khi ghi, caller chỉ được cập nhật nếu phiên bản trong database vẫn bằng phiên bản mà caller đã đọc. Nếu bản ghi đã đổi, câu lệnh cập nhật không khớp và thao tác bị báo conflict để ứng dụng đọc lại, hợp nhất hoặc yêu cầu người dùng quyết định.

Mẫu này thường được triển khai bằng cột version và câu lệnh UPDATE có điều kiện, annotation @Version của JPA, compare-and-swap (CAS), hoặc HTTP ETag kết hợp If-Match. Điểm chung là **kiểm tra và ghi phải diễn ra nguyên tử tại nơi sở hữu dữ liệu**.

Bài học đi từ lỗi ghi đè, nguyên tắc version, SQL và Java, REST conditional request, cách xử lý conflict, khác biệt với idempotency và pessimistic locking, đến transaction nhiều bản ghi, kiểm thử đồng thời, vận hành và các lỗi thiết kế thường gặp.

## 1. Lost update xảy ra như thế nào?

Giả sử một hồ sơ khách hàng có tên hiển thị là “An” và địa chỉ là “Quận 1”. Hai người dùng mở form gần như cùng lúc:

~~~text
Database ban đầu:
  display_name = "An"
  address      = "Quận 1"

User A đọc bản ghi
User B đọc cùng bản ghi

User A đổi display_name thành "An Nguyễn"
User B đổi address thành "Quận 3"

A ghi toàn bộ form:
  display_name = "An Nguyễn"
  address      = "Quận 1"

B ghi toàn bộ form dựa trên snapshot cũ:
  display_name = "An"
  address      = "Quận 3"

Kết quả cuối:
  display_name = "An"
  address      = "Quận 3"
~~~

Thay đổi tên của A đã bị B ghi đè dù hai người sửa hai trường khác nhau. Nếu cả hai cùng sửa số điện thoại, người cập nhật sau cũng có thể ghi đè dữ liệu người trước.

Một ví dụ khác là số lượng hàng tồn:

~~~text
available = 5

Worker A đọc 5
Worker B đọc 5
A tính 5 - 3 = 2
B tính 5 - 4 = 1
A ghi 2
B ghi 1

Kết quả 1, trong khi tổng yêu cầu là 7 và hệ thống đáng lẽ phải từ chối ít nhất một reservation.
~~~

Vấn đề không nằm ở việc hai request chạy song song tự thân. Vấn đề là **cả hai đều ra quyết định dựa trên cùng một snapshot cũ nhưng không kiểm tra snapshot còn hiện hành tại thời điểm ghi**.

## 2. Optimistic locking là gì?

Optimistic locking giả định xung đột không xảy ra thường xuyên, nên cho phép nhiều bên đọc mà không giữ khóa dài. Khi ghi, hệ thống kiểm tra phiên bản:

1. Đọc bản ghi cùng version hiện tại.
2. Tính toán thay đổi từ snapshot đó.
3. Gửi yêu cầu cập nhật kèm version kỳ vọng.
4. Database chỉ ghi nếu version vẫn khớp.
5. Nếu ghi thành công, tăng version.
6. Nếu không có hàng nào được cập nhật, báo conflict; caller phải quyết định đọc lại, merge hoặc dừng.

~~~text
Bản ghi ban đầu: version = 7

A đọc version 7
B đọc version 7

A: UPDATE ... WHERE version = 7
   -> 1 row updated
   -> version = 8

B: UPDATE ... WHERE version = 7
   -> 0 rows updated
   -> CONFLICT

B đọc lại version 8 và xử lý theo chính sách
~~~

Database không cần biết A hay B là người dùng nào. Nó chỉ đảm bảo một lần cập nhật dựa trên version 7 không thể âm thầm ghi đè một bản ghi đã lên version 8.

**Version check và data write phải là một thao tác nguyên tử**. Nếu ứng dụng SELECT version, kiểm tra trong Java, rồi UPDATE không có điều kiện version, một writer khác vẫn có thể thay đổi dữ liệu giữa hai bước.

## 3. Record version nên có dạng nào?

Cách phổ biến nhất là một số nguyên tăng đơn điệu theo từng bản ghi hoặc aggregate:

~~~sql
CREATE TABLE customer_profiles (
    customer_id UUID PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    address VARCHAR(300),
    version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Mỗi lần ghi thành công:

- Version hiện tại phải bằng expectedVersion.
- Thay đổi dữ liệu được áp dụng.
- Version tăng đúng một bước theo quy tắc đã định.
- UpdatedAt có thể được cập nhật cùng transaction để phục vụ hiển thị/quan sát.

Ví dụ ban đầu version 7, update thành công thì version 8. Lần cập nhật tiếp theo phải dùng version 8.

### 3.1. Vì sao dùng số version thay cho timestamp?

Timestamp có thể dùng làm token, nhưng một số nguyên version thường rõ ràng và an toàn hơn:

- Hai update có thể xảy ra trong cùng một đơn vị độ chính xác timestamp.
- Clock giữa các máy có thể lệch.
- Timestamp có thể được sửa hoặc lấy từ client không đáng tin.
- Hai lần update có thể cùng timestamp dù thứ tự commit khác nhau.
- Một timestamp mới hơn không nhất thiết chứng minh request đã đọc đủ dữ liệu phụ thuộc.

Một integer version được tăng bởi database/owner trong transaction thể hiện thứ tự thay đổi trong phạm vi bản ghi. Nó không phải version toàn cục của toàn hệ thống.

### 3.2. Version không phải số lần người dùng bấm Save

Một command có thể không làm thay đổi dữ liệu; policy có thể không tăng version nếu nội dung giống hệt. Hoặc một transaction thay đổi nhiều trường chỉ tăng version một lần. Hợp đồng cần định nghĩa version tăng theo **lần commit thay đổi có ý nghĩa** hay theo một quy tắc khác.

Không để client tự gửi version mới tùy ý. Client chỉ gửi version mà nó đã đọc; owner chịu trách nhiệm so sánh và tăng version.

## 4. Conditional UPDATE trong SQL

Mẫu cơ bản:

~~~sql
UPDATE customer_profiles
SET
    display_name = :display_name,
    address = :address,
    version = version + 1,
    updated_at = now()
WHERE customer_id = :customer_id
  AND version = :expected_version;
~~~

Ứng dụng kiểm tra số hàng được cập nhật:

- **1 row:** cập nhật thành công; version đã tăng.
- **0 rows:** bản ghi không tồn tại hoặc version đã thay đổi; cần phân biệt theo contract.
- **Nhiều hơn 1 row:** dấu hiệu sai về khóa hoặc điều kiện, cần được xem là lỗi thiết kế.

Điều kiện version và UPDATE nằm trong một câu SQL, vì vậy database thực hiện việc so sánh và thay đổi như một thao tác nguyên tử theo cơ chế transaction/isolation của nó.

### 4.1. Câu lệnh có điều kiện cho tồn kho

~~~sql
UPDATE inventory
SET
    available_quantity = available_quantity - :requested_quantity,
    version = version + 1,
    updated_at = now()
WHERE sku = :sku
  AND version = :expected_version
  AND available_quantity >= :requested_quantity;
~~~

Nếu một hàng được cập nhật, reservation bước này đã được chấp nhận theo invariant của hàng inventory. Nếu không, có thể vì version đã đổi, SKU không tồn tại hoặc số lượng không đủ. Ứng dụng có thể đọc lại trong transaction phù hợp để xác định business outcome; không nên mặc định mọi zero-row result đều là “hết hàng”.

### 4.2. Conditional update không cần đọc trước trong một số trường hợp

Nếu thao tác là tăng một counter, có thể dùng phép cập nhật nguyên tử:

~~~sql
UPDATE product_metrics
SET view_count = view_count + 1
WHERE product_id = :product_id;
~~~

Database tự thực hiện phép cộng trên giá trị hiện hành, tránh kiểu read-modify-write ở ứng dụng. Nếu cần kiểm tra hạn mức hoặc nhiều điều kiện, đưa điều kiện vào WHERE:

~~~sql
UPDATE accounts
SET daily_spend = daily_spend + :amount
WHERE account_id = :account_id
  AND daily_spend + :amount <= daily_limit;
~~~

Câu lệnh này bảo vệ một invariant trong phạm vi hàng được cập nhật. Nếu giới hạn phụ thuộc nhiều hàng, nhiều bảng hoặc dữ liệu bên ngoài, cần transaction/constraint/locking phù hợp hơn; một WHERE trên một hàng không tự bảo vệ toàn bộ miền nghiệp vụ.

## 5. CAS — compare-and-swap

Optimistic locking là một dạng ứng dụng của **compare-and-swap**:

~~~text
CAS(location, expected, newValue):
  nếu currentValue == expected:
      currentValue = newValue
      return SUCCESS
  ngược lại:
      return FAILURE
~~~

Database implementation:

~~~sql
UPDATE documents
SET body = :new_body,
    version = version + 1
WHERE document_id = :id
  AND version = :expected_version;
~~~

Nếu version hiện tại không bằng expected, CAS thất bại và không ghi. Các thao tác CAS cũng xuất hiện trong atomic variables, cache có conditional set, distributed coordination và API sử dụng ETag.

Một CAS thành công chỉ bảo đảm điều kiện so sánh tại vị trí được quản lý đã đúng trong thao tác nguyên tử đó. Nó không tự đảm bảo một workflow nhiều resource đã hoàn tất hoặc external side effect không bị lặp.

## 6. JPA/Hibernate với @Version

JPA hỗ trợ optimistic locking thông qua annotation @Version.

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class CustomerProfile {
    @Id
    private String customerId;

    private String displayName;
    private String address;

    @Version
    private Long version;

    protected CustomerProfile() {}

    public void changeDisplayName(String value) {
        this.displayName = value;
    }

    public void changeAddress(String value) {
        this.address = value;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

Khi load entity, Hibernate lưu version đã đọc. Khi flush/update, ORM tạo SQL tương đương:

~~~sql
UPDATE customer_profile
SET display_name = ?,
    address = ?,
    version = 8
WHERE customer_id = ?
  AND version = 7;
~~~

Nếu không có hàng nào được cập nhật do version đã thay đổi, ORM ném optimistic locking exception (ví dụ OptimisticLockException hoặc exception tương ứng của Hibernate/Spring). Transaction hiện tại không nên tiếp tục như thể update thành công.

### 6.1. Service layer

~~~java
@Service
public class CustomerProfileService {
    private final CustomerProfileRepository repository;

    public CustomerProfileService(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public ProfileResult update(
            String customerId,
            UpdateProfileCommand command) {

        CustomerProfile profile = repository.findById(customerId)
            .orElseThrow(() -> new ProfileNotFoundException(customerId));

        profile.changeDisplayName(command.displayName());
        profile.changeAddress(command.address());

        // ORM dirty checking sẽ flush khi transaction commit.
        return new ProfileResult(customerId, profile.getVersion());
    }
}
~~~

Version có thể chưa tăng trong object tại thời điểm return nếu ORM chỉ cập nhật khi flush/commit. Nếu API cần trả version mới ngay, có thể flush có chủ đích và đọc version sau flush, hoặc dùng cơ chế trả kết quả phù hợp. Cần nhớ transaction có thể vẫn thất bại khi commit; không gửi response “đã lưu” trước khi transaction thực sự hoàn tất.

### 6.2. Xử lý exception đúng ranh giới transaction

Không nên bắt OptimisticLockException trong cùng transaction, bỏ qua rồi tiếp tục ghi các thay đổi khác. Transaction có thể đã bị đánh dấu rollback-only và persistence context không còn an toàn để dùng như trước.

Một chiến lược rõ ràng:

1. Transaction cập nhật thất bại và rollback.
2. Application layer nhận biết conflict.
3. Nếu policy cho phép retry, bắt đầu **transaction mới**.
4. Đọc entity/version mới.
5. Tính lại thay đổi từ business intent, không áp nguyên snapshot cũ.
6. Thử lại có giới hạn; nếu vẫn conflict thì trả conflict cho caller.

Đừng retry toàn bộ transaction một cách mù quáng nếu command chứa quyết định đã dựa trên dữ liệu cũ hoặc có side effect ngoài database.

### 6.3. Bulk update có thể bỏ qua @Version

JPQL bulk UPDATE hoặc native SQL không đi qua dirty checking entity thông thường. Nó có thể không tự áp dụng @Version, không đồng bộ persistence context và làm entity đã load trở nên stale.

Nếu dùng bulk update, phải tự đưa version vào điều kiện và tăng version trong câu SQL, sau đó clear/refresh persistence context theo đúng thiết kế. Đừng giả định mọi câu update trong repository đều tự động có optimistic locking.

## 7. REST API với ETag và If-Match

Version nội bộ có thể được biểu diễn ra HTTP bằng ETag. Server trả một validator cho representation:

~~~http
GET /api/profiles/customer-71
Accept: application/json

HTTP/1.1 200 OK
ETag: "profile-v7"
Content-Type: application/json

{
  "customerId": "customer-71",
  "displayName": "An",
  "address": "Quận 1"
}
~~~

Client giữ ETag và gửi điều kiện khi cập nhật:

~~~http
PATCH /api/profiles/customer-71
If-Match: "profile-v7"
Content-Type: application/json

{
  "displayName": "An Nguyễn"
}
~~~

Nếu bản ghi vẫn ở version 7, server cập nhật và trả ETag mới:

~~~http
HTTP/1.1 200 OK
ETag: "profile-v8"

{
  "customerId": "customer-71",
  "displayName": "An Nguyễn",
  "address": "Quận 1"
}
~~~

Nếu một người khác đã cập nhật version 8, If-Match không còn khớp:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "type": "https://example.invalid/problems/version-conflict",
  "title": "Dữ liệu đã thay đổi",
  "status": 412,
  "detail": "Hãy tải phiên bản mới trước khi lưu."
}
~~~

412 Precondition Failed là status HTTP phù hợp khi điều kiện If-Match không thỏa. Một API cũng có thể dùng 409 Conflict cho conflict nghiệp vụ không gắn với HTTP precondition. Cần định nghĩa nhất quán thay vì trả 500 cho một xung đột đồng thời bình thường.

### 7.1. Thiếu If-Match thì sao?

Nếu API yêu cầu mọi lần cập nhật phải có version, có thể trả 428 Precondition Required khi client bỏ qua điều kiện. Điều này buộc caller đọc representation trước khi ghi, nếu chính sách của API chọn cách đó.

Không phải mọi endpoint đều cần If-Match. Một lệnh cộng số lượng nguyên tử hoặc command idempotent có thể có semantics khác. Chọn contract dựa trên thao tác và invariant.

### 7.2. ETag là token opaque

Client nên giữ và gửi lại ETag đúng nguyên văn, không tự tách số version từ chuỗi. Server có thể thay đổi cách tạo token, dùng hash representation hoặc mã hóa nhiều thành phần.

- ETag mạnh thường dùng cho phép so sánh representation theo HTTP semantics.
- ETag yếu có tiền tố W/ và không phù hợp cho If-Match theo strong comparison.
- ETag phải thay đổi khi representation cần bảo vệ thay đổi theo contract.
- Nếu API tổng hợp dữ liệu nhiều service, một ETag toàn trang không tự đảm bảo atomic snapshot giữa các nguồn.
- Không để client tự đặt ETag mới hoặc bỏ If-Match để vượt conflict.

## 8. Cập nhật một phần và merge thay đổi

Một conflict không nhất thiết phải yêu cầu người dùng nhập lại toàn bộ form. Nếu hai người sửa các field độc lập, server có thể merge có điều kiện theo policy.

Ví dụ:

- A thay displayName.
- B thay address.
- Hai bên đọc version 7.
- A ghi version 8.
- B gửi PATCH chỉ chứa address với If-Match version 7.
- Server trả 412 vì snapshot B đã cũ.

Có hai cách xử lý:

**Cách 1: yêu cầu client đọc lại và xác nhận.** An toàn và dễ giải thích; phù hợp dữ liệu có ý nghĩa liên quan.

**Cách 2: server rebase field-level patch.** Nếu command chỉ thay address và business rules chứng minh thay đổi tên không ảnh hưởng, server có thể đọc version 8, áp patch address lên bản mới và commit version 9. Phải xác định rõ semantics PATCH và invariant; không được merge mù quáng mọi field.

Ví dụ API có thể dùng command riêng UpdateAddress thay vì gửi toàn bộ object:

~~~json
{
  "operationId": "op-address-91",
  "address": "Quận 3",
  "expectedVersion": 7
}
~~~

Nếu chỉ một field được thay đổi, backend vẫn phải quyết định liệu thay đổi đó có phụ thuộc các field khác hay không. Một thay đổi địa chỉ có thể ảnh hưởng thuế, shipping eligibility hoặc fraud rules, vì vậy không phải lúc nào cũng an toàn để tự rebase.

## 9. Xử lý conflict ở client

Khi nhận 412/409, UI nên:

1. Giữ lại nội dung người dùng vừa nhập để không mất công sức.
2. Thông báo dữ liệu đã được người khác cập nhật.
3. Tải phiên bản hiện tại từ owner.
4. So sánh các field cũ, field mới và giá trị người dùng muốn ghi.
5. Cho phép chọn giữ bản mới, áp thay đổi của mình hoặc hợp nhất nếu policy cho phép.
6. Gửi request mới với ETag/version mới sau khi quyết định.
7. Không tự lặp lại cùng payload và version cũ vô hạn.

Mẫu thông báo:

~~~text
Thông tin đã được cập nhật trong lúc bạn chỉnh sửa.

Dữ liệu hiện tại:
  Địa chỉ: Quận 2

Thay đổi của bạn:
  Địa chỉ: Quận 3

Hãy tải lại hoặc xác nhận thay đổi trước khi lưu.
~~~

Với field độc lập và low-risk, sản phẩm có thể tự rebase có kiểm soát. Với hạn mức, tiền, trạng thái phê duyệt hay quyền truy cập, nên ưu tiên conflict rõ ràng để người có thẩm quyền quyết định.

## 10. Khi nào retry được và retry thế nào?

Optimistic conflict có thể xảy ra thường xuyên ở hot record. Retry có thể giúp nếu thay đổi mới vẫn hợp lệ sau khi đọc lại.

**Retry phù hợp:**

- Command là một phép biến đổi có thể tính lại từ state mới.
- Business intent vẫn còn hiệu lực.
- Không có side effect ngoài database đã thực hiện trước đó.
- Có giới hạn attempts và backoff/jitter.
- Mỗi lần retry chạy trong transaction mới và đọc lại dữ liệu.

Ví dụ tăng số lượng bộ đếm:

~~~text
Command: IncreaseViewCountBy(1)

Attempt 1 đọc version 7 -> conflict
Attempt 2 đọc version 8 -> tăng count và ghi version 9
~~~

**Retry không phù hợp:**

- Người dùng đã sửa cả form và muốn xác nhận đúng snapshot đã xem.
- Command dựa trên quote đã hết hạn.
- Thanh toán hoặc chuyển tiền đã gọi external provider mà kết quả chưa rõ.
- Reservation đã hết deadline.
- Business invariant thay đổi khiến ý định cũ không còn hợp lệ.
- Retry có thể tạo side effect khác hoặc bỏ qua approval.

### 10.1. Backoff và giới hạn

Một retry policy có thể:

- Giới hạn 2–3 lần thử lại nội bộ, tùy workload.
- Dùng jitter nhỏ để tránh nhiều writer xung đột lại cùng thời điểm.
- Dừng khi conflict liên tiếp vượt ngưỡng.
- Ghi metric và trả conflict có cấu trúc cho caller.
- Không retry tự động với mọi lỗi 409/412; phân biệt version conflict với business conflict.
- Tránh ngủ chờ lâu bên trong transaction hoặc giữ DB connection trong lúc backoff.

Nếu cùng một row luôn conflict, tăng số retry không chữa được contention. Có thể cần phân vùng dữ liệu, serialize command theo key, queue worker theo aggregate hoặc chuyển một số thao tác sang atomic SQL.

## 11. Optimistic locking khác idempotency

Hai khái niệm thường bị nhầm:

| Khía cạnh | Optimistic locking | Idempotency |
| --- | --- | --- |
| Vấn đề giải quyết | Ghi dựa trên snapshot/version đã cũ | Cùng một operation được gửi/nhận nhiều lần |
| Token | expectedVersion, ETag, row version | idempotencyKey, commandId, operationId |
| Điều kiện | Current version bằng version kỳ vọng | Operation key đã được xử lý hay chưa |
| Kết quả không khớp | Conflict; cần đọc lại/merge | Trả kết quả cũ hoặc bỏ tác động trùng |
| Ví dụ | Hai người cùng sửa hồ sơ | Client retry POST tạo đơn sau timeout |

Một request có thể cần **cả hai**:

- Idempotency-Key bảo đảm retry cùng PlaceOrder không tạo thêm Order.
- ExpectedVersion bảo đảm command ConfirmOrder chỉ cập nhật từ version mà caller dựa vào.
- Unique constraint bảo vệ operation key trong database.
- Version predicate bảo vệ snapshot.

Idempotency không giải quyết lost update giữa hai operation khác nhau. Optimistic locking không ngăn cùng một command bị gửi lại nhiều lần nếu mỗi lần retry dùng version mới và vô tình lặp side effect. Cần xác định rõ hai lớp.

## 12. Optimistic locking khác pessimistic locking

| Tiêu chí | Optimistic | Pessimistic |
| --- | --- | --- |
| Ý tưởng | Cho đọc song song, phát hiện conflict khi ghi | Khóa tài nguyên để ngăn writer khác cập nhật trong thời gian giữ khóa |
| Cơ chế | Version/ETag/conditional update | SELECT FOR UPDATE, row lock, lock manager |
| Chi phí khi ít conflict | Thường thấp, không giữ lock dài | Có chi phí lock/đợi |
| Khi conflict cao | Retry có thể tốn kém | Có thể giảm retry nhưng tăng wait/deadlock risk |
| Tác động khi client chậm | Không giữ DB lock trong lúc user chỉnh form | Không nên giữ transaction/lock qua tương tác người dùng |
| Use case | Hồ sơ, cấu hình, document, cập nhật tương đối thưa | Cập nhật số dư/hạn mức cần tuần tự, tranh chấp cao trong transaction ngắn |

Không nên mở transaction, SELECT FOR UPDATE rồi giữ database lock trong vài phút trong khi người dùng chỉnh form. Đó là cách dễ gây lock contention, timeout và ảnh hưởng người dùng khác.

Có thể dùng pessimistic lock bên trong một transaction ngắn khi thao tác cạnh tranh cao và invariant cần tuần tự. Optimistic locking phù hợp khi conflict hiếm và caller có thể xử lý 412/409.

Hai cách không loại trừ nhau ở cấp hệ thống; mỗi loại dữ liệu và workflow có thể chọn khác nhau.

## 13. Atomic SQL có thể tốt hơn read-modify-write

Không phải mọi update đều cần một lần GET rồi gửi expectedVersion. Nếu phép biến đổi có thể biểu diễn an toàn trong SQL, hãy cân nhắc atomic update.

**Tránh:**

~~~text
SELECT balance FROM accounts WHERE id = 1;  -- 100
Application tính 100 - 20 = 80
UPDATE accounts SET balance = 80 WHERE id = 1;
~~~

Hai request có thể cùng đọc 100 và ghi 80, khiến một lần trừ bị mất.

**Tốt hơn cho phép trừ có điều kiện:**

~~~sql
UPDATE accounts
SET balance_minor = balance_minor - :amount,
    version = version + 1
WHERE account_id = :account_id
  AND balance_minor >= :amount;
~~~

Nếu một hàng được cập nhật, khoản trừ thỏa điều kiện. Nếu không, có thể không đủ số dư hoặc tài khoản không tồn tại; cần xử lý outcome phù hợp.

Đối với chuyển tiền giữa hai account, chỉ một UPDATE không đủ. Cần transaction cập nhật cả hai account theo thứ tự khóa ổn định, kiểm tra đủ tiền, bảo vệ concurrent transfers và ghi ledger. Optimistic version từng row hoặc pessimistic locks có thể được dùng, nhưng phải bảo vệ invariant **tổng thể của giao dịch**.

## 14. Invariant nhiều hàng và phantom write

Version trên một row chỉ bảo vệ row đó. Giả sử quy định “mỗi ca trực tối đa hai nhân viên nghỉ”:

~~~text
A đọc: đang có 1 người nghỉ
B đọc: đang có 1 người nghỉ
A đăng ký nghỉ -> tổng 2
B đăng ký nghỉ -> tổng 3
~~~

Nếu mỗi người nghỉ là một row mới và hai request chỉ khóa version của row cá nhân, cả hai có thể cùng thành công. Invariant nằm trên **tập hợp nhiều hàng**, không có một record version chung để tự bảo vệ.

Giải pháp có thể gồm:

- Database constraint hoặc unique/partial index nếu biểu diễn được invariant.
- Một guard row/counter đại diện quota và conditional update nguyên tử.
- Pessimistic lock trên resource quản lý quota.
- Transaction isolation SERIALIZABLE với xử lý serialization failure.
- Một aggregate/service owner tuần tự hóa các command liên quan.
- Reservation model có capacity row và atomic decrement.

Chọn giải pháp dựa trên invariant thật. Không tuyên bố optimistic locking một row bảo vệ mọi thay đổi liên quan đến entity đó nếu các thao tác khác còn ghi vào bảng khác hoặc điều kiện phụ thuộc nhiều row.

## 15. Version của aggregate và event ordering

Trong DDD, một aggregate thường có version để kiểm soát thay đổi đồng thời. Khi commit event, có thể ghi aggregateVersion cùng transaction:

~~~text
Order version 7
  -> ConfirmOrder
  -> commit Order version 8
  -> outbox OrderConfirmed(version=8)

Consumer nhận:
  version 8 -> áp dụng nếu state/version phù hợp
  version 7 -> stale, bỏ qua hoặc xử lý theo policy
  version 10 khi đang ở 8 -> phát hiện gap, chờ/rebuild/fetch owner
~~~

Version của aggregate giúp:

- Phát hiện event stale hoặc out-of-order.
- Bảo vệ optimistic concurrency tại owner.
- Hỗ trợ consumer projection không ghi lùi trạng thái.
- Tạo điều kiện so sánh snapshot và command expected version.

Không nhầm aggregateVersion với schemaVersion:

- **aggregateVersion** nói bản ghi nghiệp vụ đã thay đổi đến lần nào.
- **schemaVersion** nói payload tuân theo cấu trúc hợp đồng nào.
- **eventId** định danh một event cụ thể.
- **commandId/idempotencyKey** định danh một yêu cầu hành động.

Bốn trường này giải quyết bốn vấn đề khác nhau.

## 16. Version trong cache và read model

Một read model có thể bị chậm hơn database owner. Client đọc version 7 từ projection, nhưng owner đã lên version 8. Nếu client gửi expectedVersion=7 đến owner, server trả conflict là đúng; caller phải đọc lại owner hoặc chờ projection.

Không nên lấy version từ cache stale rồi tự coi đó là version hiện tại. Hãy xác định:

- Version do owner phát hành hay projection tự tạo?
- Version thuộc aggregate nào?
- Read model có đảm bảo apply event theo version không?
- Có thể trả version 8 rồi sau đó trả version 7 do request đến replica khác không?
- Client có giữ minimumVisibleVersion để tránh UI lùi?
- Khi version gap, query service có fallback owner hay trả pending?

Với CQRS, write model và read model có thể có tiến độ khác nhau. Conditional write phải được xác thực ở **write owner**, không chỉ trên projection.

## 17. API contract cho conflict

Một API tốt giúp client phân biệt:

- Resource không tồn tại.
- Thiếu điều kiện version.
- Version không còn khớp.
- Business rule từ chối.
- Lỗi kỹ thuật tạm thời.

Ví dụ:

~~~http
PATCH /orders/ord-1001
If-Match: "order-v7"
Content-Type: application/json

{
  "shippingAddress": "Quận 3"
}
~~~

Conflict do version:

~~~http
HTTP/1.1 412 Precondition Failed
Content-Type: application/problem+json

{
  "code": "VERSION_MISMATCH",
  "resourceId": "ord-1001",
  "expectedVersion": 7,
  "currentVersion": 8,
  "message": "Đơn hàng đã được cập nhật."
}
~~~

Không phải lúc nào cũng nên tiết lộ currentVersion hoặc nội dung hiện tại cho caller không đủ quyền. Error body cần theo security policy, tránh lộ dữ liệu của tenant khác.

Một số status thường gặp:

| Status | Cách dùng gợi ý |
| --- | --- |
| 200/204 | Conditional update thành công |
| 404 | Resource không tồn tại hoặc không thể hiển thị theo policy |
| 409 | Conflict nghiệp vụ hoặc conflict theo API contract |
| 412 | HTTP precondition như If-Match không thỏa |
| 428 | Server yêu cầu client cung cấp precondition |
| 422 | Payload hợp lệ về cú pháp nhưng không thỏa validation/business rule |
| 429 | Quá tải/rate limit, không phải version conflict |
| 503 | Service tạm không sẵn sàng |

Đừng trả 500 cho version conflict bình thường; cũng đừng biến mọi 409 thành retry tự động.

## 18. Retry an toàn trong Spring

Có thể đặt retry ở application boundary, nhưng mỗi lần phải chạy transaction mới. Một cấu trúc minh họa:

~~~java
public ProfileResult updateWithRetry(
        String customerId,
        UpdateProfileCommand command) {

    int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return transactionalUpdater.updateOnce(customerId, command);
        } catch (OptimisticLockingFailureException ex) {
            if (attempt == maxAttempts) {
                throw new ProfileConflictException(customerId, ex);
            }

            backoffWithJitter(attempt);
        }
    }

    throw new IllegalStateException("Unreachable");
}
~~~

Service transactional riêng:

~~~java
@Service
public class TransactionalProfileUpdater {
    private final CustomerProfileRepository repository;

    public TransactionalProfileUpdater(CustomerProfileRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public ProfileResult updateOnce(
            String customerId,
            UpdateProfileCommand command) {

        CustomerProfile profile = repository.findById(customerId)
            .orElseThrow(() -> new ProfileNotFoundException(customerId));

        // Chỉ phù hợp nếu command mang business intent có thể
        // áp dụng lại lên state mới một cách an toàn.
        profile.changeDisplayName(command.displayName());

        repository.flush();
        return new ProfileResult(customerId, profile.getVersion());
    }
}
~~~

Trong Spring, gọi một phương thức @Transactional qua self-invocation trong cùng object có thể không đi qua proxy transaction như mong đợi. Tách bean hoặc dùng transaction template để mỗi lần thử có transaction boundary rõ. Đoạn code trên là ví dụ cấu trúc; cần imports, exception mapping, policy và kiểm tra version/command semantics theo dự án.

Đặc biệt, ví dụ retry thay displayName có thể ghi đè tên người khác vừa đặt nếu policy tự áp dụng command lên version mới. Đối với form cần xác nhận snapshot, **trả conflict cho người dùng** thường đúng hơn. Retry tự động phù hợp với phép biến đổi có thể tính lại như increment, recompute hoặc command idempotent theo business intent.

## 19. Cập nhật có điều kiện với MongoDB và document store

Mẫu version không chỉ áp dụng cho SQL. Một document có field version:

~~~json
{
  "_id": "customer-71",
  "displayName": "An",
  "address": "Quận 1",
  "version": 7
}
~~~

Cập nhật có điều kiện:

~~~javascript
db.customerProfiles.updateOne(
  { _id: "customer-71", version: 7 },
  {
    $set: { displayName: "An Nguyễn" },
    $inc: { version: 1 }
  }
);
~~~

Nếu matchedCount bằng 0, document không tồn tại hoặc version không còn 7. Cần phân biệt bằng một truy vấn/contract phù hợp và đảm bảo update filter cùng update operation được thực thi nguyên tử cho document theo semantics của database.

Với nhiều document, transaction/constraint hoặc thiết kế aggregate phù hợp vẫn cần thiết. Không suy ra atomicity của một document mở rộng sang nhiều collection hoặc service.

## 20. Không phải mọi version đều cần công khai

Ở tầng database, version có thể là BIGINT. Ở API, ETag opaque có thể phù hợp hơn. Ở event, aggregateVersion là một field metadata. Ở frontend, client giữ version token nhưng không cần tính toán hoặc hiển thị cho người dùng.

Một hợp đồng tốt:

- Server sinh version/token.
- Client gửi lại token khi muốn cập nhật snapshot đã đọc.
- Server kiểm tra token tại owner.
- Nếu không khớp, trả conflict rõ ràng.
- Client không tự tăng token hoặc bỏ điều kiện.
- Version không bị tái sử dụng theo cách khiến stale request tưởng là mới (tránh ABA nếu dùng CAS trên giá trị có thể quay lại).

### ABA problem

Giả sử một CAS so sánh giá trị trạng thái:

~~~text
A đọc state = READY
B đổi READY -> RUNNING -> READY
A gửi update với expectedState = READY
~~~

Giá trị hiện tại lại là READY, nên so sánh chỉ theo state không nhận ra đã có hai thay đổi xen giữa. Đây là ABA problem. Một version tăng đơn điệu giúp phát hiện:

~~~text
READY v7
RUNNING v8
READY v9
~~~

A vẫn gửi expectedVersion=7 và bị từ chối, dù giá trị state hiện tại trông giống ban đầu.

Không chỉ so sánh field business nếu lịch sử thay đổi cũng có ý nghĩa. Dùng version/token bao quát các thay đổi cần bảo vệ.

## 21. Version tăng ở đâu và khi nào?

Version nên được quản lý tại nơi sở hữu dữ liệu, thường trong database transaction:

- ORM tăng version khi flush/update thành công.
- SQL conditional update tăng version trong cùng câu lệnh.
- Stored procedure tăng version khi invariant được thỏa.
- Document store dùng atomic increment cùng filter expectedVersion.

Không nên:

- Client tự gửi version mới.
- Tăng version trước khi commit rồi publish event success dù transaction rollback.
- Chỉ tăng updatedAt mà không có quy tắc concurrency.
- Cập nhật dữ liệu qua một code path bỏ qua version trong khi code path khác dựa vào @Version.
- Để bulk update không tăng version nhưng các consumer vẫn tin version thể hiện mọi thay đổi.
- Dùng một counter chung toàn hệ thống gây contention không cần thiết.

Nếu nhiều code path cùng ghi bảng, phải thống nhất cơ chế. Có thể dùng database trigger hoặc stored procedure trong một số kiến trúc, nhưng cần tránh tăng version hai lần hoặc làm ORM persistence context không biết state mới.

## 22. Transaction nhiều bước và nhiều service

Optimistic locking chỉ kiểm tra cạnh tranh tại một ranh giới được bảo vệ. Một workflow liên service có thể cần version ở từng owner:

~~~text
Order v7
  -> ConfirmOrder(expectedVersion=7)
  -> Ordering commit Order v8

Inventory v12
  -> ReserveStock(expectedVersion=12)
  -> Inventory commit Reservation v13

Payment v4
  -> AuthorizePayment(operationId=...)
  -> Payments commit Payment v5
~~~

Không có một version toàn cục để khóa đồng thời cả Order, Inventory và Payment. Saga/process manager điều phối các command, theo dõi event kết quả và compensation. Mỗi service dùng optimistic locking/constraint riêng để bảo vệ dữ liệu của nó.

Nếu một bước conflict, workflow cần đọc state owner mới và quyết định tiếp tục hay hủy. Không tự replay cả saga từ đầu nếu một payment đã được authorize hoặc một reservation đã được giữ; các bước side effect cần idempotency và reconciliation.

## 23. Cập nhật một aggregate có nhiều child record

Giả sử Order có nhiều OrderLine. Nếu mọi thao tác thay đổi OrderLine đều phải làm tăng Order version, hãy xác định cách aggregate root quản lý concurrency.

Có thể:

- Mọi command đi qua Order aggregate và tăng version root.
- Có một sequence/version cho từng line nếu các line độc lập.
- Dùng transaction và constraint bảo vệ invariant tổng thể.
- Dùng event sequence của aggregate để consumer nhận biết thứ tự.

Nếu một service cập nhật child row trực tiếp mà không tăng version root, một command khác có thể đọc root version 7, không biết line đã thay đổi và ghi đè state cũ. Đây là lỗi consistency do đường ghi bypass aggregate boundary.

Ngược lại, tăng root version cho mọi thay đổi không liên quan có thể tạo conflict thừa. Cần chọn phạm vi version theo invariant thật: một aggregate, một row hay một phần độc lập.

## 24. Conflict không phải lỗi hệ thống bất thường

Trong mô hình optimistic, conflict là kết quả có thể dự đoán khi nhiều writer cạnh tranh. Không nên log mọi conflict thành ERROR nếu đây là hành vi bình thường và được xử lý. Nhưng tỷ lệ conflict tăng đột ngột có thể cho biết:

- Một record quá nóng.
- Nhiều request cùng cập nhật cùng aggregate.
- UI giữ form mở quá lâu.
- Client dùng snapshot cache quá cũ.
- Retry không backoff gây xung đột dây chuyền.
- Batch update lớn làm tăng thời gian transaction.
- Service có nhiều code path cập nhật cùng resource.

Metric hữu ích:

| Metric | Ý nghĩa |
| --- | --- |
| optimistic_conflict_count | Số lần conditional update thất bại do version |
| optimistic_conflict_rate | Tỷ lệ conflict trên tổng update |
| retry_attempts | Số lần retry trước khi hoàn tất |
| retry_exhausted_count | Số command hết retry budget |
| hot_aggregate_conflicts | Aggregate/key gây contention cao, log/trace thay vì label cardinality lớn |
| stale_client_version_age | Snapshot client giữ đã cũ bao lâu |
| update_latency_p95/p99 | Thời gian từ request đến commit |
| user_merge_rate | Tần suất cần người dùng hợp nhất conflict |
| version_gap_count | Consumer gặp event version bị thiếu hoặc đến sai thứ tự |

Theo dõi theo endpoint, loại command, service và environment. Không đưa customerId/orderId cardinality cao vào label metric; dùng log/trace có sampling và quyền phù hợp.

## 25. Kiểm thử concurrency có ý nghĩa

Một test chỉ gọi update tuần tự không chứng minh optimistic locking hoạt động. Cần ép hai transaction cùng đọc một version trước khi một bên commit.

Kịch bản:

~~~text
1. Tạo profile version 7.
2. Transaction A đọc version 7.
3. Transaction B đọc version 7.
4. Đồng bộ barrier để cả hai cùng sẵn sàng ghi.
5. A cập nhật và commit.
6. B thử update expectedVersion=7.
7. Xác nhận B conflict, không ghi đè dữ liệu A.
8. Đọc lại và xác nhận version/state cuối đúng.
~~~

Các assertion:

- Chỉ một update dựa trên version 7 thành công.
- Version tăng đúng theo quy tắc.
- Không mất thay đổi đã commit.
- Transaction conflict rollback sạch.
- API trả status conflict đã định nghĩa.
- Retry (nếu có) chạy transaction mới và tính lại từ state mới.
- Duplicate request cùng idempotency key không tạo side effect mới.

### 25.1. Test SQL integration

Dùng database thật hoặc Testcontainers phù hợp để xác nhận row count của conditional UPDATE. In-memory database có thể có semantics locking/isolation khác production; không nên chỉ dựa vào mock repository.

### 25.2. Test JPA

- Hai persistence context riêng cùng load một entity.
- Một context commit.
- Context còn lại flush và nhận optimistic locking exception.
- Transaction của context thứ hai rollback.
- Reload bằng transaction mới thấy version/state của context đầu.

### 25.3. Test REST ETag

- GET trả ETag v7.
- PATCH If-Match v7 thành công, trả v8.
- PATCH khác vẫn dùng v7 nhận 412.
- PATCH không có If-Match nhận 428 nếu API yêu cầu.
- Client giữ form và có thể đọc phiên bản mới để merge.
- Weak ETag không được chấp nhận cho If-Match theo contract.
- Cache/proxy không làm ETag của resource khác bị dùng nhầm.

### 25.4. Test tải và contention

Tạo nhiều writer cùng cập nhật một aggregate, đo throughput, conflict rate, p95/p99 và retry exhaustion. Nếu tỷ lệ conflict cao, đánh giá atomic SQL, queue theo key, sharding hoặc pessimistic lock ngắn. Đừng chỉ tăng max retry.

## 26. Những trường hợp cần chú ý với isolation level

Optimistic locking theo version bảo vệ các update có cùng version token, nhưng transaction isolation vẫn quyết định các hiện tượng đọc/ghi khác.

- READ COMMITTED có thể phù hợp với conditional UPDATE theo row version.
- REPEATABLE READ/SNAPSHOT có thể gây serialization/update conflict theo engine.
- SERIALIZABLE có thể abort transaction để bảo vệ invariant phức tạp, caller cần retry đúng.
- SELECT FOR UPDATE giữ lock và thay đổi concurrency behavior.
- Unique/check constraints vẫn là lớp bảo vệ mạnh cho invariant mà database biểu diễn được.

Tên isolation level giống nhau giữa các database không nhất thiết có implementation giống hệt. Cần thử trên engine production, đặc biệt với phantom rows, predicate updates, deadlocks và transaction retries.

Không nghĩ rằng thêm cột version thay thế mọi constraint. Nếu yêu cầu “mỗi customer chỉ có một active subscription”, unique partial index có thể là lớp bảo vệ trực tiếp hơn optimistic version ở một row không liên quan.

## 27. Batch update và nhiều bản ghi

Khi cập nhật nhiều bản ghi trong một batch, phải quyết định semantics:

**All-or-nothing:** mọi row đều phải có expectedVersion đúng; nếu một row conflict, rollback toàn batch. Phù hợp khi các thay đổi là một đơn vị nghiệp vụ không thể tách.

**Partial success:** row hợp lệ được cập nhật, row conflict được trả riêng. Phù hợp batch độc lập, nhưng API phải trả rõ kết quả từng item.

Ví dụ conditional update nhiều record:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :qty,
    version = version + 1
WHERE sku = :sku
  AND version = :expected_version
  AND available_quantity >= :qty;
~~~

Nếu một đơn hàng có nhiều SKU, chạy câu này cho từng row trong cùng transaction theo thứ tự SKU ổn định, kiểm tra tất cả kết quả và rollback toàn transaction nếu một mặt hàng không đủ. Thứ tự khóa ổn định giúp giảm deadlock khi nhiều đơn cùng reserve nhiều SKU. Một transaction đơn lẻ không tự bảo vệ external event; nếu phát ReservationCompleted, ghi outbox cùng transaction.

## 28. Optimistic locking trong workflow tồn kho

Tình huống hai đơn cùng tranh một SKU:

~~~text
SKU A100: available=5, version=12

Order 1 yêu cầu 4
Order 2 yêu cầu 3

Cả hai đọc v12
Order 1 UPDATE ... WHERE version=12 AND available>=4
  -> thành công: available=1, version=13

Order 2 UPDATE ... WHERE version=12 AND available>=3
  -> 0 rows: conflict

Order 2 đọc lại v13, available=1
  -> business rejection: không đủ hàng
~~~

Ở đây conflict lần đầu là kỹ thuật do snapshot cũ. Sau khi đọc lại, kết quả “không đủ hàng” là **business outcome**. Không nên tiếp tục retry vô hạn vì điều kiện nghiệp vụ đã rõ.

Nếu Inventory dùng một command queue có worker xử lý tuần tự theo SKU, có thể giảm contention, nhưng conditional update vẫn hữu ích để bảo vệ dữ liệu khi có nhiều đường ghi hoặc nhiều instance.

## 29. Optimistic locking cho document editing

Với tài liệu cộng tác, có thể có nhiều cấp độ:

- **Whole-document version:** bất kỳ thay đổi nào tăng version; dễ hiểu nhưng conflict nhiều.
- **Section/field version:** cho phép merge thay đổi độc lập; phức tạp hơn vì invariant liên trường.
- **Operation-based collaboration:** CRDT hoặc Operational Transformation cho chỉnh sửa đồng thời ở mức ký tự/operation; đây là mô hình khác, không chỉ thêm một cột version.

Optimistic locking phù hợp cho form CRUD thông thường. Với Google Docs-like collaborative editing, khóa cả document cho mỗi lần gõ sẽ tạo quá nhiều conflict và trải nghiệm kém; cần thuật toán cộng tác chuyên biệt.

## 30. Version và idempotency khi command retry

Một command có thể chứa cả hai token:

~~~json
{
  "commandId": "cmd-confirm-1001",
  "idempotencyKey": "confirm-order-1001-attempt-1",
  "orderId": "ord-1001",
  "expectedVersion": 7,
  "requestedAction": "CONFIRM"
}
~~~

Xử lý theo thứ tự logic:

1. Kiểm tra idempotency key đã có kết quả chưa. Nếu có cùng request semantics, trả lại kết quả đã lưu.
2. Nếu là operation mới, đọc/kiểm tra owner state.
3. So expectedVersion với version hiện tại.
4. Kiểm tra business invariant.
5. Commit state + version + outbox/result trong local transaction.
6. Lưu kết quả idempotency để request retry có thể lấy lại.
7. Nếu version conflict, lưu/không lưu kết quả conflict theo policy idempotency đã công bố; caller có thể cần tạo operation mới sau khi đọc lại.

Cần định nghĩa nếu cùng idempotency key nhưng payload/expectedVersion khác thì trả conflict. Không được dùng một key cho hai business intents khác nhau.

## 31. Security và tenant boundary

Version token không phải authorization token. Biết ETag v7 không cấp quyền sửa resource. Mỗi request vẫn cần:

- Xác thực người dùng/service.
- Kiểm tra tenant/owner và quyền trên resource.
- Kiểm tra field-level permissions nếu có.
- So version tại owner sau khi xác định đúng resource.
- Trả lỗi không làm lộ resource existence hoặc version của tenant khác theo policy.
- Chống replay request nhạy cảm bằng idempotency/nonce phù hợp.

Không dùng version như một bí mật; nó có thể được gửi công khai trong API. Nếu ETag chứa dữ liệu suy ra nội bộ, nên dùng token opaque hoặc hash đã thiết kế.

## 32. Lỗi triển khai thường gặp

**Lỗi 1 — SELECT rồi UPDATE không có version predicate.** Kiểm tra ở application nhưng writer khác chen giữa. Hãy đưa expectedVersion vào câu UPDATE.

**Lỗi 2 — Chỉ so timestamp độ phân giải thấp.** Hai lần ghi có thể trùng timestamp hoặc clock lệch. Dùng version do owner quản lý.

**Lỗi 3 — Không tăng version sau update.** Các client cũ tiếp tục nghĩ snapshot của mình còn hiện hành.

**Lỗi 4 — Có code path bỏ qua @Version.** Bulk update/native SQL không áp version; stale entity có thể ghi đè.

**Lỗi 5 — Catch conflict rồi tiếp tục transaction cũ.** Persistence context/transaction có thể đã rollback-only; retry trong transaction mới.

**Lỗi 6 — Retry cùng payload stale vô hạn.** Mỗi lần đều conflict và tăng tải. Đọc lại, rebase có chủ đích hoặc trả 412.

**Lỗi 7 — Merge toàn bộ form cũ.** Một field user không sửa có thể ghi đè thay đổi người khác. Dùng patch semantics và merge theo domain.

**Lỗi 8 — Dùng version để thay idempotency.** Cùng một POST retry có thể tạo hai operation mới. Dùng idempotency key/unique constraint.

**Lỗi 9 — Dùng idempotency để thay version.** Hai command khác nhau vẫn có thể ghi đè nhau. Dùng optimistic concurrency.

**Lỗi 10 — Chỉ bảo vệ một row nhưng invariant nằm trên nhiều row.** Cần constraint, guard row, serializable hoặc lock thích hợp.

**Lỗi 11 — Version của projection được coi là authoritative.** Projection có thể chậm. Conditional write phải kiểm tra tại owner.

**Lỗi 12 — Client tự tăng version.** Caller có thể vượt qua check. Server/database phải quản lý.

**Lỗi 13 — Version token không bao trùm mọi field liên quan.** Thay đổi child record không tăng root version khiến stale update lọt qua.

**Lỗi 14 — ETag không thay đổi khi representation thay đổi.** Client If-Match có thể được chấp nhận sai.

**Lỗi 15 — Dùng weak ETag với If-Match.** So sánh strong validator không thỏa semantics HTTP.

**Lỗi 16 — Trả 500 cho conflict bình thường.** Client retry sai, observability đếm lỗi hệ thống không chính xác.

**Lỗi 17 — Tăng retry để chữa hot row.** Conflict storm tăng. Cần xem lại serialization, data partitioning hoặc atomic update.

**Lỗi 18 — Không test bằng database thật.** Mock không thể hiện concurrency/isolation và số row updated.

**Lỗi 19 — Ghi event trước khi transaction commit.** Consumer thấy fact chưa được lưu. Ghi outbox trong transaction cùng state.

**Lỗi 20 — Không kiểm tra side effect ngoài transaction.** Retry transaction có thể gửi email/charge nhiều lần. Dùng outbox, operation key và reconciliation.

## 33. Bài thực hành: hai người cùng sửa hồ sơ khách hàng

Dữ liệu ban đầu:

~~~json
{
  "customerId": "customer-71",
  "displayName": "An",
  "address": "Quận 1",
  "version": 7
}
~~~

A đổi displayName, B đổi address. Cả hai GET cùng version 7.

### Nhiệm vụ

1. Mô tả lost update nếu server thay toàn bộ record không có version.
2. Viết câu UPDATE có điều kiện expectedVersion=7.
3. Xác định response cho writer đầu và writer thứ hai.
4. Thiết kế ETag/If-Match cho REST.
5. Quyết định khi nào server có thể merge field-level patch.
6. Thiết kế UX giữ nội dung người dùng khi nhận 412.
7. Viết test hai transaction cùng đọc version 7 rồi ghi đồng thời.
8. Phân biệt retry cùng idempotency key với update từ version mới.
9. Giải thích vì sao timestamp không đủ thay version.
10. Mô tả trường hợp child record thay đổi nhưng root version không tăng.

### Một kết quả mong đợi

~~~text
A: GET -> ETag profile-v7
B: GET -> ETag profile-v7

A: PATCH If-Match profile-v7
   -> 200, ETag profile-v8

B: PATCH If-Match profile-v7
   -> 412 Precondition Failed
   -> giữ input của B
   -> GET profile-v8
   -> hiển thị conflict/merge
   -> B xác nhận patch mới với ETag profile-v8
   -> 200, ETag profile-v9
~~~

Nếu thay đổi B độc lập và domain cho phép rebase, server có thể áp patch address lên state v8 rồi ghi v9 sau khi kiểm tra lại invariant. Nếu không, B phải xác nhận snapshot mới. Không có một chính sách merge đúng cho mọi dữ liệu.

## 34. Checklist thiết kế optimistic concurrency

1. **Invariant:** Dữ liệu nào cần bảo vệ khỏi lost update?
2. **Scope:** Version thuộc row, aggregate, document, hay stream?
3. **Owner:** Service/database nào có quyền tăng version?
4. **Read:** Client nhận expectedVersion/ETag ở đâu?
5. **Write:** Version check và update có cùng thao tác nguyên tử không?
6. **Increment:** Version tăng khi nào, một lần cho mỗi transaction hay mỗi field?
7. **All writers:** Mọi code path, bulk update và script có tuân thủ không?
8. **Conflict:** 0 row updated được diễn giải thế nào?
9. **HTTP:** Dùng 412, 409 hay 428 theo contract nào?
10. **Retry:** Command nào có thể tính lại? Có transaction mới và retry limit không?
11. **Merge:** Có thể merge field-level an toàn hay cần người dùng xác nhận?
12. **Idempotency:** Request retry có thể tạo operation/side effect trùng không?
13. **Multi-row:** Invariant có vượt khỏi một row/version không?
14. **Cache/read model:** Version có đến từ source authoritative không?
15. **Events:** AggregateVersion và schemaVersion có được phân biệt?
16. **External side effects:** Có outbox/operation key/reconciliation không?
17. **Security:** Version token có bị nhầm với quyền truy cập không?
18. **Metrics:** Có theo dõi conflict, retry exhaustion, hot key và latency?
19. **Tests:** Có concurrent transactions trên database thật không?
20. **UX:** Người dùng có giữ được nội dung khi conflict và biết cách giải quyết?
21. **Operations:** Có runbook khi conflict rate tăng hoặc record trở thành hot spot?
22. **Documentation:** API/command contract nói rõ expected version và conflict semantics?

---

**Nguyên tắc cần nhớ:** Khóa lạc quan cho phép nhiều bên đọc đồng thời nhưng chỉ chấp nhận ghi khi **phiên bản hiện tại vẫn khớp phiên bản caller đã đọc**. Hãy đặt version predicate ngay tại thao tác ghi, tăng version cùng transaction và trả conflict rõ khi không khớp. Dùng ETag/If-Match cho HTTP, @Version cho JPA hoặc conditional UPDATE/CAS ở database; xử lý conflict bằng đọc lại, merge có kiểm soát hoặc yêu cầu người dùng xác nhận. Optimistic locking bảo vệ snapshot khỏi lost update, còn idempotency bảo vệ operation khỏi xử lý lặp — các hệ thống quan trọng thường cần cả hai.