# Phân biệt kiểm tra đầu vào với ràng buộc tại nơi lưu

Một ứng dụng Java cho phép người dùng đăng ký một chỗ tại hội thảo. Giao diện kiểm tra rằng email hợp lệ, hội thảo đã được chọn và số lượng chỗ còn lại lớn hơn 0. Hai người đồng thời nhìn thấy “còn 1 chỗ” và cùng bấm đăng ký. Nếu hệ thống chỉ kiểm tra dữ liệu trước khi ghi, cả hai yêu cầu có thể cùng vượt qua bước kiểm tra và tạo ra **hai đăng ký cho một chỗ**.

Tình huống này cho thấy cần phân biệt:

- **Kiểm tra đầu vào (input validation)**: đánh giá dữ liệu hoặc yêu cầu trước khi thực hiện thao tác, để phát hiện lỗi sớm, diễn đạt lỗi dễ hiểu và hạn chế dữ liệu không hợp lệ đi sâu vào hệ thống.
- **Ràng buộc tại nơi lưu (storage constraints)**: các điều kiện được kho dữ liệu bảo vệ trong quá trình ghi, nhằm duy trì tính toàn vẹn của trạng thái đã lưu ngay cả khi có nhiều luồng, nhiều ứng dụng hoặc nhiều tiến trình truy cập.

Bài học thuộc chương **Lược đồ và ràng buộc** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Ngoài việc chọn mô hình dữ liệu và lược đồ, người học cần thiết kế ranh giới persistence cho Java, bảo vệ bất biến nghiệp vụ trước cạnh tranh đồng thời, xử lý lỗi kết nối, tiến hóa schema và kiểm chứng tính nhất quán khi khôi phục dữ liệu. Ví dụ SQL dùng PostgreSQL; khi đổi hệ quản trị, phải kiểm tra cú pháp và khả năng bảo đảm tương ứng.

## 1. Hai lớp bảo vệ phục vụ hai mục đích

Xét yêu cầu tạo đăng ký:

~~~json
{
  "workshopId": "9b0ca713-7d30-45a8-9cd5-1666e7ccca8d",
  "attendeeEmail": " An@Example.org "
}
~~~

**Kiểm tra đầu vào** có thể xác nhận mã hội thảo đúng định dạng UUID, email không rỗng, độ dài hợp lý và thực hiện chuẩn hóa email theo quy tắc được công bố. Nó có thể trả thông báo cụ thể: “Email không đúng định dạng”, “Bạn chưa chọn hội thảo” hoặc “Email vượt quá độ dài cho phép”.

**Ràng buộc tại nơi lưu** sẽ bảo vệ các điều kiện như: không tồn tại hai đăng ký trùng khóa nghiệp vụ trong cùng hội thảo, đăng ký phải tham chiếu một hội thảo tồn tại, số chỗ không được âm và một giao dịch lỗi không thể để lại số chỗ đã trừ nhưng chưa có đăng ký.

Một cách ghi nhớ là đặt hai câu hỏi độc lập:

1. **Yêu cầu này có nên được chấp nhận và xử lý tiếp không?** Đây là vùng trách nhiệm của xác thực, phân quyền, kiểm tra dữ liệu đầu vào và quy tắc nghiệp vụ.
2. **Trạng thái dữ liệu sau khi ghi có còn đúng với các điều kiện bắt buộc không?** Đây là vùng trách nhiệm của schema, constraint, thao tác ghi có điều kiện và transaction.

Hai câu hỏi có phần giao nhau nhưng không trùng nhau. Ví dụ cùng một quy tắc “email đăng ký là duy nhất trong hội thảo” có thể được kiểm tra trước để hiện thông báo dễ hiểu, nhưng **chỉ kiểm tra trước không bảo đảm duy nhất khi có cạnh tranh**. Cơ sở dữ liệu vẫn cần ràng buộc duy nhất.

~~~mermaid
flowchart TD
    A["Request từ client"] --> B["Xác thực và phân quyền"]
    B --> C["Kiểm tra cú pháp, kiểu, độ dài"]
    C --> D["Quy tắc nghiệp vụ trước ghi"]
    D --> E["Giao dịch persistence"]
    E --> F["Constraint / atomic write tại storage"]
    F -->|Thành công| G["Commit và phản hồi"]
    F -->|Vi phạm| H["Rollback và ánh xạ lỗi"]
    H --> I["Thông báo có ý nghĩa cho client"]
~~~

Sơ đồ mô tả một luồng phổ biến, không bắt buộc mọi ứng dụng phải có từng tầng vật lý riêng. Quan trọng là **không đặt toàn bộ trách nhiệm bảo vệ dữ liệu vào một endpoint**: batch job, consumer của message queue, công cụ quản trị hoặc dịch vụ khác cũng có thể ghi vào cùng nơi lưu.

## 2. Validation kiểm tra những gì?

Validation có nhiều cấp độ, vì không phải mọi dữ liệu sai đều là lỗi định dạng.

| Cấp độ | Ví dụ | Tầng thường thực hiện | Lưu ý |
|---|---|---|---|
| **Cú pháp / kiểu** | UUID parse được, số lượng là số nguyên | API / parser / DTO | Phải xử lý cả field vắng mặt và giá trị null |
| **Hình dạng dữ liệu** | Email không rỗng, mã dài tối đa 254 ký tự | DTO / Bean Validation | Có thể bổ sung CHECK và NOT NULL ở nơi lưu |
| **Chuẩn hóa** | Cắt khoảng trắng, chuẩn hóa một mã không phân biệt hoa/thường | Biên ứng dụng / domain | Định nghĩa quy tắc trước khi áp UNIQUE |
| **Quan hệ giữa trường** | endTime sau startTime | Domain; có thể thêm CHECK nếu cùng hàng | Không chỉ kiểm tra từng field riêng lẻ |
| **Quy tắc nghiệp vụ động** | Hội thảo đã mở đăng ký, chưa bắt đầu | Domain và thao tác ghi có điều kiện | Giá trị có thể thay đổi giữa kiểm tra và ghi |
| **Duy nhất / tham chiếu** | Không đăng ký email trùng; workshop tồn tại | DB UNIQUE / FK, kết hợp kiểm tra sớm | Phải chịu được concurrent requests |
| **Quyền truy cập** | Người thuộc tenant T1 không sửa dữ liệu T2 | Authentication / authorization, có thể thêm RLS | Có dữ liệu hợp lệ vẫn có thể là yêu cầu trái phép |
| **Tính toàn vẹn đa bản ghi** | Một chỗ được bán đúng một lần | Transaction, atomic update, lock hoặc isolation thích hợp | Một CHECK đơn hàng không đủ bảo vệ tổng liên hàng |

Các lỗi xảy ra ở **những thời điểm khác nhau**. Parser có thể từ chối chuỗi không phải UUID trước khi chạy bất kỳ truy vấn nào. Ngược lại, vi phạm UNIQUE chỉ được kết luận chắc chắn tại thời điểm ghi theo cơ chế đồng thời của DB.

### Chuẩn hóa trước validation hay sau validation?

Quy tắc chuẩn hóa nên được định nghĩa thành một bước tường minh, nhất quán. Ví dụ ứng dụng quy định email đăng ký là case-insensitive và bỏ khoảng trắng ngoài cùng. Khi đó:

~~~text
Input:       " An@Example.org "
Canonical:   "an@example.org"
Stored:      "an@example.org"
~~~

Đây là **chính sách của ứng dụng minh họa**, không có nghĩa mọi địa chỉ email trên Internet có thể tự ý chuyển toàn bộ sang chữ thường mà không có hệ quả. Cần định nghĩa nhất quán với nhà cung cấp định danh và yêu cầu nghiệp vụ. Mã số, tên người, địa chỉ và dữ liệu Unicode cũng có quy tắc chuẩn hóa riêng; không “sanitize” bằng cách lặng lẽ xóa các ký tự có ý nghĩa.

Validation không thay thế thao tác **escape theo ngữ cảnh hiển thị**, truy vấn có tham số hoặc phân quyền. Dữ liệu có hình thức hợp lệ vẫn có thể độc hại nếu được ghép trực tiếp vào SQL hoặc HTML.

## 3. Một quy tắc có thể được kiểm tra ở nhiều lớp

Ví dụ với trường **quantity**:

- Client hạn chế nhập số lượng từ 1 đến 10 để người dùng dễ thao tác.
- Service kiểm tra số lượng theo sản phẩm, hạng vé, quyền lợi của người dùng và điều kiện kinh doanh hiện tại.
- Cơ sở dữ liệu đặt **CHECK (quantity > 0)** để không thể lưu số lượng không hợp lệ.
- Khi trừ tồn kho, DB phải bảo đảm tồn kho không âm bằng thao tác cập nhật nguyên tử hoặc cơ chế đồng thời phù hợp.

Cần phân biệt **quy tắc cần ổn định lâu dài** với **chính sách có thể thay đổi theo thời gian**. Quy định “số lượng không âm” thường là bất biến dữ liệu. Quy định “khuyến mãi hôm nay chỉ cho mua tối đa 3 vé” có thể là chính sách động tại dịch vụ, khó hoặc không thích hợp nhúng cứng vào CHECK.

Nếu chọn lặp một điều kiện ở API và DB, phải có **nguồn mô tả nghiệp vụ rõ ràng** và cách kiểm thử chúng thống nhất. Tránh tình trạng API cho phép mã dài 80 ký tự nhưng DB chỉ cho phép 40, hoặc hai nơi chuẩn hóa khác nhau khiến cùng một email được hiểu là hai khóa khác nhau.

## 4. Các ràng buộc phổ biến tại nơi lưu

Ví dụ dưới đây tập trung vào cơ sở dữ liệu quan hệ:

| Ràng buộc | Điều được bảo vệ | Điều **không** tự bảo vệ |
|---|---|---|
| **NOT NULL** | Cột không được thiếu giá trị SQL NULL | Chuỗi rỗng, khoảng trắng, ngữ nghĩa dữ liệu |
| **CHECK** | Biểu thức điều kiện trên hàng phù hợp phải thỏa | Bất biến phức tạp xuyên nhiều hàng/bảng |
| **UNIQUE** | Không có hai hàng cùng giá trị trong phạm vi khóa unique theo ngữ nghĩa DB | Dữ liệu nhập đã chuẩn hóa đúng hay chưa |
| **PRIMARY KEY** | Định danh duy nhất và không null cho hàng | Quyền đọc/ghi, tính duy nhất của các mã nghiệp vụ khác |
| **FOREIGN KEY** | Giá trị tham chiếu có đích hợp lệ theo ràng buộc | Chính sách cấp quyền hoặc vòng đời nghiệp vụ |
| **EXCLUDE** (PostgreSQL) | Cấm các cặp hàng thỏa điều kiện xung đột, ví dụ khoảng thời gian chồng lấn | Mọi bất biến liên bảng hoặc kiểm tra nghiệp vụ tùy ý |
| **Transaction + điều kiện ghi** | Các thay đổi phối hợp commit/rollback; giữ điều kiện biến đổi đồng thời khi thiết kế đúng | Mọi race condition bất kể isolation hoặc mã lệnh |

Đặc biệt, trong PostgreSQL, **CHECK được xem là đạt khi biểu thức trả TRUE hoặc NULL**. Vì vậy:

~~~sql
-- Một hàng có quantity=NULL có thể không bị CHECK này từ chối.
CHECK (quantity > 0)

-- Cần kết hợp khi quantity là bắt buộc:
quantity INTEGER NOT NULL CHECK (quantity > 0)
~~~

Tương tự, một UNIQUE thông thường trong PostgreSQL cho phép nhiều giá trị NULL vì NULL được coi là khác nhau khi kiểm tra unique theo mặc định; có thể dùng NOT NULL hoặc những cơ chế unique khác tùy mục tiêu và phiên bản DB.

**Chỉ thêm điều kiện kiểm tra trong Java không tạo constraint cho DB.** Một tập lệnh nhập dữ liệu, migration hoặc dịch vụ thứ hai vẫn có thể ghi thẳng vào bảng nếu tài khoản được phép.

## 5. Ví dụ lược đồ: đăng ký hội thảo nhiều tenant

Giả sử mỗi hội thảo có sức chứa cố định và số chỗ còn lại. Một email được phép đăng ký **tối đa một lần cho mỗi hội thảo** theo quy tắc nghiệp vụ hiện tại. Mỗi hội thảo và đăng ký đều thuộc một tenant.

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE workshops (
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    id UUID NOT NULL,
    title TEXT NOT NULL CHECK (length(btrim(title)) > 0),
    capacity INTEGER NOT NULL CHECK (capacity >= 0),
    remaining_seats INTEGER NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft', 'open', 'closed')),
    PRIMARY KEY (tenant_id, id),
    CONSTRAINT ck_workshops_remaining
        CHECK (remaining_seats >= 0 AND remaining_seats <= capacity)
);

CREATE TABLE registrations (
    tenant_id UUID NOT NULL,
    id UUID NOT NULL,
    workshop_id UUID NOT NULL,
    attendee_email TEXT NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, id),
    CONSTRAINT ck_registrations_email
        CHECK (
            length(attendee_email) BETWEEN 1 AND 254
            AND attendee_email = lower(btrim(attendee_email))
        ),
    CONSTRAINT fk_registrations_workshop
        FOREIGN KEY (tenant_id, workshop_id)
        REFERENCES workshops (tenant_id, id),
    CONSTRAINT uq_registration_per_workshop_email
        UNIQUE (tenant_id, workshop_id, attendee_email)
);

CREATE INDEX idx_registrations_workshop
    ON registrations (tenant_id, workshop_id, registered_at);
~~~

Cần đọc schema theo các **bất biến cụ thể**:

1. **PK ghép (tenant_id, id)** định danh hội thảo/đăng ký theo tenant.
2. **FK ghép (tenant_id, workshop_id)** không cho một đăng ký thuộc T1 trỏ tới hội thảo T2. Chỉ có cột tenant_id trong bảng mà không gắn vào FK vẫn có thể bỏ lọt quan hệ sai tenant.
3. **UNIQUE (tenant_id, workshop_id, attendee_email)** là giới hạn đăng ký trùng trong một hội thảo. Hai tenant hoặc hai hội thảo có thể dùng cùng email.
4. **CHECK remaining_seats** chặn lưu số chỗ âm hoặc lớn hơn sức chứa vào một hàng.
5. **CHECK email** bảo vệ dạng canonical tối thiểu theo chính sách minh họa; nó không chứng minh email thuộc về người đăng ký, tồn tại thực tế, hay hoàn toàn đúng theo mọi quy tắc cú pháp email.
6. **Status** được giới hạn tập giá trị. Việc chuyển từ **draft** sang **open** hay **closed** có hợp lệ hay không là quy tắc chuyển trạng thái cần được xử lý thêm, không được giải quyết chỉ bằng CHECK.

**Sức chứa và số chỗ còn lại có thể liên quan đến nhiều đăng ký**, nhưng schema chỉ bảo vệ những điều đã được diễn đạt. Ví dụ, CHECK không tự bảo đảm tổng số đăng ký bằng **capacity - remaining_seats**; điều này phụ thuộc luồng ghi, transaction và các trường hợp hủy/chuyển chỗ. Khi nghiệp vụ mở rộng, cần thiết kế lại ranh giới bất biến và quy trình đối soát.

### Ràng buộc và hiệu năng

PK, UNIQUE và FK có thể cần index phục vụ lookup; trong PostgreSQL, PK/UNIQUE tạo index tương ứng, còn cột ở **phía tham chiếu FK** không tự động có index chỉ vì nó là FK. Chỉ mục hỗ trợ query phải được lựa chọn theo đường truy cập và khối lượng dữ liệu. Thêm index quá nhiều sẽ tăng chi phí ghi, kích thước backup và thời gian migration.

Schema trên dùng riêng **idx_registrations_workshop** cho truy vấn danh sách đăng ký theo workshop và thời gian; nếu workload khác, cần đo kế hoạch truy vấn trước khi thêm index.

## 6. Vì sao kiểm tra trước không ngăn được race condition?

Giả sử ứng dụng gọi:

~~~sql
SELECT 1
FROM registrations
WHERE tenant_id = $1
  AND workshop_id = $2
  AND attendee_email = $3;
~~~

Nếu không có kết quả, ứng dụng kết luận “email chưa đăng ký” và tiếp tục INSERT. Hai request có thể chạy:

~~~text
Thời điểm | Request A                    | Request B
----------+------------------------------+------------------------------
t1        | SELECT: chưa tồn tại         |
t2        |                              | SELECT: chưa tồn tại
t3        | INSERT email=X thành công    |
t4        |                              | INSERT email=X: trùng!
~~~

**Kiểm tra trước (check then act)** không tạo atomicity. Dù SELECT chạy rất nhanh, khoảng giữa hai câu lệnh vẫn đủ để dữ liệu thay đổi.

Với UNIQUE constraint, DB xử lý cạnh tranh ở bước ghi: một transaction có thể phải chờ transaction khác hoàn tất, rồi bị từ chối nếu xung đột còn tồn tại. Ứng dụng chuyển lỗi đó thành thông báo “Email đã đăng ký hội thảo này”.

Tương tự, đọc số ghế trước rồi trừ bằng lệnh chỉ dùng giá trị cũ có thể gây lost update hoặc oversell. Cần kết hợp **cập nhật có điều kiện tại DB**:

~~~sql
UPDATE workshops
SET remaining_seats = remaining_seats - 1
WHERE tenant_id = $1
  AND id = $2
  AND status = 'open'
  AND starts_at > CURRENT_TIMESTAMP
  AND remaining_seats >= 1;
~~~

Chỉ tiếp tục tạo đăng ký khi kết quả cập nhật là **1 hàng**. Nếu là 0 hàng, hội thảo có thể không tồn tại, không còn mở hoặc đã hết chỗ. Với PostgreSQL, các UPDATE đồng thời trên cùng hàng phải phối hợp qua row lock; điều kiện WHERE được kiểm tra theo quy tắc đồng thời của mức cô lập đang dùng. Nếu backend khác, cần xác minh thao tác này có bảo đảm tương đương.

**CHECK (remaining_seats >= 0)** là phòng tuyến cuối để chặn trạng thái âm; chính câu UPDATE có điều kiện mới diễn đạt phép **“chỉ lấy chỗ nếu còn chỗ”**. CHECK đơn lẻ không tự quyết định ai được chỗ cuối cùng.

## 7. Transaction kết nối hai bất biến

Một lần đăng ký thay đổi **hai chỗ lưu**: giảm remaining_seats và tạo hàng registrations. Hai thao tác cần nằm trong **cùng transaction**.

~~~mermaid
sequenceDiagram
    participant S as Java service
    participant D as PostgreSQL
    S->>D: BEGIN
    S->>D: UPDATE workshops ... remaining_seats >= 1
    D-->>S: 1 row changed
    S->>D: INSERT registrations (...)
    alt INSERT thành công
        S->>D: COMMIT
        D-->>S: Đã lưu đăng ký và trừ chỗ
    else INSERT vi phạm UNIQUE/FK/CHECK
        D-->>S: Constraint violation
        S->>D: ROLLBACK
        D-->>S: Hoàn tác cả phần giảm chỗ
    end
~~~

Nếu email đã đăng ký nhưng vẫn còn chỗ, bước UPDATE có thể thành công trước, sau đó INSERT bị UNIQUE từ chối. **Rollback** phải khôi phục số chỗ. Ngược lại, nếu hai email khác nhau tranh chỗ cuối, chỉ request lấy được chỗ theo điều kiện cập nhật mới tiếp tục; request còn lại không được tự INSERT.

Một số vấn đề cần thiết kế rõ:

- Nếu transaction gồm cả gọi HTTP sang hệ thanh toán, **DB rollback không tự hoàn tác** tác dụng ở hệ thống bên ngoài. Có thể cần outbox, state machine, idempotency và cơ chế bù trừ.
- Nếu client timeout khi đang COMMIT, không thể mặc định kết luận đăng ký thất bại. Có thể giao dịch đã commit dù phản hồi bị mất; retry cần một **idempotency key** hoặc cách truy vấn kết quả đã ghi.
- Nếu yêu cầu hủy đăng ký, phải định nghĩa giao dịch xóa/đổi trạng thái và hoàn chỗ tương ứng. Quy tắc hiện tại cho phép đăng ký một lần trọn đời trong mỗi hội thảo; nếu được phép hủy rồi đăng ký lại, mô hình unique và trạng thái phải được thiết kế lại có chủ đích.

### Isolation và các bất biến phức tạp

Với bất biến **chỉ liên quan một hàng**, một UPDATE có điều kiện thường đủ nếu DB bảo đảm cập nhật nguyên tử. Bất biến **liên quan nhiều hàng hoặc phạm vi** (ví dụ “không có hai lịch cùng chiếm một phòng trong khoảng thời gian chồng nhau”) có thể cần:

- Constraint chuyên biệt, như **EXCLUDE** trên kiểu range của PostgreSQL nếu bài toán phù hợp.
- Khóa các hàng/đơn vị đại diện cần bảo vệ bằng **SELECT ... FOR UPDATE** trong transaction.
- **Serializable isolation** cùng cơ chế retry khi transaction bị từ chối, nếu backend hỗ trợ và application đã được thiết kế cho lỗi serialization.
- Một mô hình dữ liệu khác biến bất biến liên hàng thành một phép cập nhật nguyên tử có thể bảo vệ tại nơi lưu.

Không viết CHECK chứa truy vấn liên bảng rồi mặc định DB sẽ kiểm tra lại khi hàng khác thay đổi. Trong PostgreSQL, CHECK không được thiết kế để duy trì điều kiện tổng quát phụ thuộc các hàng khác.

## 8. Java: validation ở ranh giới API

Trong ứng dụng dùng **Jakarta Bean Validation**, có thể mô tả điều kiện hình dạng dữ liệu ngay trên DTO. Ví dụ Java 17:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import java.util.UUID;

public record RegisterRequest(
    @NotNull UUID workshopId,
    @NotBlank @Email @Size(max = 254) String attendeeEmail
) {}
~~~

Điều này yêu cầu thư viện Jakarta Validation và provider tương ứng (chẳng hạn trong framework có hỗ trợ). Annotation **@Email** hữu ích cho thông báo đầu vào; nó không chứng minh địa chỉ thuộc quyền kiểm soát của người dùng, không thay xác minh email và có thể khác cách DB chuẩn hóa.

Service nên tiếp nhận **tenantId từ ngữ cảnh xác thực**, không tin một tenantId do client tự gửi. Có thể xây một command đã chuẩn hóa:

~~~java
import java.util.Locale;
import java.util.UUID;

public record RegistrationCommand(
    UUID tenantId,
    UUID workshopId,
    String canonicalEmail
) {
    public RegistrationCommand {
        if (tenantId == null || workshopId == null || canonicalEmail == null) {
            throw new IllegalArgumentException("missing required field");
        }
        canonicalEmail = canonicalEmail.strip().toLowerCase(Locale.ROOT);
        if (canonicalEmail.isBlank() || canonicalEmail.length() > 254) {
            throw new IllegalArgumentException("invalid email length");
        }
    }
}
~~~

Đoạn ví dụ này **chỉ chuẩn hóa và kiểm tra một phần**: điều kiện cú pháp email đã được API/validator kiểm tra; không dùng nó như thư viện email validation hoàn chỉnh. Chính sách chuyển email thành chữ thường phải thống nhất với miền nghiệp vụ. Sau chuẩn hóa, DB vẫn là nơi bảo vệ UNIQUE.

### Trình tự trách nhiệm

~~~text
Controller / API
  parse JSON, dùng Bean Validation, xác thực người dùng
      |
      v
Service / Domain
  lấy tenant tin cậy, chuẩn hóa, kiểm tra quyền và quy tắc nghiệp vụ
      |
      v
Repository / Adapter
  câu SQL có tham số, transaction, atomic update, mapping lỗi
      |
      v
Database
  PK / FK / UNIQUE / CHECK / NOT NULL và cơ chế đồng thời
~~~

Không nên đặt logic nghiệp vụ quan trọng trong một **custom validator** gắn vào DTO nếu validator đó phải cập nhật dữ liệu hoặc mở transaction. Validation DTO nên nhẹ, có thể chạy nhiều lần mà không gây side effect; hành vi lấy chỗ phải thuộc command nghiệp vụ có transaction.

## 9. Java JDBC: ghi an toàn khi nhiều yêu cầu cạnh tranh

Một adapter JDBC thuần có thể dùng **PreparedStatement** và một transaction để giữ thống nhất số chỗ và đăng ký.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

public final class JdbcRegistrationRepository {
    private final DataSource dataSource;

    public JdbcRegistrationRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public UUID register(RegistrationCommand command) throws SQLException {
        UUID registrationId = UUID.randomUUID();

        try (Connection connection = dataSource.getConnection()) {
            boolean oldAutoCommit = connection.getAutoCommit();

            try {
                connection.setAutoCommit(false);

                try (PreparedStatement update = connection.prepareStatement("""
                    UPDATE workshops
                    SET remaining_seats = remaining_seats - 1
                    WHERE tenant_id = ?
                      AND id = ?
                      AND status = 'open'
                      AND starts_at > CURRENT_TIMESTAMP
                      AND remaining_seats >= 1
                    """)) {
                    update.setObject(1, command.tenantId());
                    update.setObject(2, command.workshopId());

                    if (update.executeUpdate() != 1) {
                        throw new IllegalStateException(
                            "Workshop unavailable or full");
                    }
                }

                try (PreparedStatement insert = connection.prepareStatement("""
                    INSERT INTO registrations
                        (tenant_id, id, workshop_id, attendee_email)
                    VALUES (?, ?, ?, ?)
                    """)) {
                    insert.setObject(1, command.tenantId());
                    insert.setObject(2, registrationId);
                    insert.setObject(3, command.workshopId());
                    insert.setString(4, command.canonicalEmail());
                    insert.executeUpdate();
                }

                connection.commit();
                return registrationId;
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            } finally {
                connection.setAutoCommit(oldAutoCommit);
            }
        }
    }
}
~~~

Điểm quan trọng của đoạn mã:

- **Tham số hóa SQL** bảo vệ giá trị khỏi bị diễn giải như cú pháp SQL; không ghép chuỗi email, UUID hoặc tenantId vào câu lệnh.
- **executeUpdate() == 1** cho biết đã trừ chỗ trên đúng một hàng phù hợp; còn 0 hàng thì từ chối thao tác.
- **INSERT** sẽ bị DB từ chối nếu email trùng trong cùng hội thảo hoặc vi phạm constraint khác.
- Nếu INSERT thất bại, **rollback** hoàn lại lần giảm chỗ trước đó.
- **UUID** ở đây là ID lưu trữ, không phải bằng chứng rằng retry của cùng nghiệp vụ chỉ tạo một đăng ký; có thể cần khóa idempotency riêng.

Đây là ví dụ minh họa về transaction và constraint, không phải tầng persistence production đầy đủ. Ứng dụng thực tế còn cần chính sách lỗi kết nối, kiểm soát timeout, đóng/khôi phục trạng thái connection pool, idempotency, giới hạn tài nguyên và ranh giới transaction cấp service. Nếu **setAutoCommit** hoặc **commit** lỗi do mất kết nối, trạng thái cuối có thể chưa xác định; client cần chiến lược kiểm tra hậu điều kiện trước khi lặp lại yêu cầu.

### Ánh xạ lỗi lưu trữ thành lỗi nghiệp vụ

PostgreSQL dùng **SQLSTATE** để phân loại lỗi. Một số mã thường gặp:

| SQLSTATE | Ý nghĩa | Hướng xử lý tại ứng dụng |
|---|---|---|
| **23502** | not_null_violation | Dữ liệu không đáp ứng schema; xem lỗi validation hoặc bug mapper |
| **23503** | foreign_key_violation | Tham chiếu không hợp lệ; có thể do dữ liệu thay đổi hoặc sai tenant |
| **23505** | unique_violation | Conflict, ví dụ email đã đăng ký; kiểm tra constraint bị vi phạm |
| **23514** | check_violation | Dữ liệu vượt bất biến định nghĩa trong CHECK |
| **40001** | serialization_failure | Có thể retry **toàn bộ transaction** theo chính sách giới hạn |
| **40P01** | deadlock_detected | Có thể retry transaction theo chính sách phù hợp |
| **08xxx** | Nhóm lỗi kết nối | Phân loại trạng thái không xác định; tránh tự retry tác dụng nghiệp vụ |

Với nhiều UNIQUE constraint, SQLSTATE **23505** không đủ để xác định tên lỗi dành cho người dùng; nên kiểm tra **constraint name** hoặc dùng API lỗi của driver phù hợp. Các đoạn mã thông báo chi tiết từ DB có thể chứa schema/table/key nhạy cảm; API nên ánh xạ sang lỗi domain có mã và thông điệp ổn định thay vì trả nguyên SQL exception.

Một quy tắc hữu ích là: **validation failure** được phản hồi sớm với chi tiết field; **constraint failure** trở thành lỗi nghiệp vụ hoặc cảnh báo lập trình phù hợp; **lỗi hạ tầng** không được diễn giải nhầm là “dữ liệu người dùng sai”.

## 10. Validation vẫn cần thiết dù DB có constraint

Nếu DB đã có UNIQUE, vì sao còn kiểm tra xem email đã đăng ký? Có ba lợi ích, miễn là hiểu đúng giới hạn:

1. **Trải nghiệm sử dụng:** trả thông báo rõ ràng trước khi người dùng điền xong form, giảm thao tác không cần thiết.
2. **Giảm tải:** loại yêu cầu chắc chắn sai kiểu, quá dài hoặc thiếu trường trước khi dùng kết nối DB.
3. **Diễn đạt quy tắc domain:** ví dụ không cho đăng ký hội thảo đã hủy, cảnh báo giới hạn quyền lợi hoặc giải thích điều kiện đăng ký.

Tuy vậy, **kết quả của một SELECT trước INSERT chỉ là ảnh chụp tại thời điểm đọc**. Nó không cấp quyền độc quyền với dữ liệu. Chỉ transaction và constraint/atomic operation mới quyết định hành vi ghi cuối cùng.

Tương tự, nếu service có validation tốt, tại sao cần DB CHECK? Vì có thể tồn tại đường ghi khác, bug trong mapper, một phiên bản cũ của service hoặc job migration. Constraint bảo vệ **điều kiện bắt buộc của trạng thái lưu**, bất kể đường gọi nào.

## 11. Cẩn thận với NULL, chuỗi rỗng và uniqueness

Xét bảng khách hàng:

~~~sql
CREATE TABLE customers (
    tenant_id UUID NOT NULL,
    id UUID NOT NULL,
    external_code TEXT,
    display_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, external_code)
);
~~~

Trong PostgreSQL với unique mặc định, **nhiều khách hàng trong cùng tenant có external_code = NULL** có thể tồn tại. Điều đó phù hợp khi mã chưa được cấp và “chưa biết mã” không được xem là trùng. Nếu nghiệp vụ bắt buộc mọi khách hàng có mã, thêm **NOT NULL**.

Ngược lại, chuỗi rỗng **''** không giống NULL. Unique có thể cho nhiều NULL nhưng không cho hai dòng có cùng chuỗi rỗng trong một tenant; còn CHECK như **length(display_name) > 0** vẫn cho phép chuỗi gồm khoảng trắng. Phải xác định rõ cách chuẩn hóa và biểu diễn dữ liệu thiếu.

### Unique theo trạng thái

Giả sử một email được phép có nhiều đăng ký trong lịch sử nhưng chỉ **một đăng ký đang hoạt động**. Lúc này UNIQUE trên mọi hàng không còn diễn đạt đúng quy tắc. PostgreSQL cho phép **partial unique index**:

~~~sql
-- Minh họa khi bảng registrations có cột state phù hợp.
CREATE UNIQUE INDEX uq_active_registration
ON registrations (tenant_id, workshop_id, attendee_email)
WHERE state = 'active';
~~~

Nếu thay đổi từ schema hiện tại, phải **bỏ constraint unique cũ hoặc thay thiết kế**, thêm cột state, làm sạch dữ liệu và xác định chính sách khôi phục/hủy. Không thể chỉ thêm partial index mà giữ nguyên UNIQUE cũ rồi mong cho phép nhiều bản ghi lịch sử.

Chú ý: partial unique index là cơ chế có tính năng riêng của PostgreSQL, không phải mọi DB đều hỗ trợ hoặc có cùng cú pháp. Nếu nhiều thao tác đồng thời chuyển trạng thái active/canceled, transaction và invariant vẫn phải được kiểm tra theo đúng ngữ nghĩa kinh doanh.

## 12. Những bất biến không thể giao hết cho một CHECK

Một CHECK trong bảng **orders** có thể bảo vệ **total_minor >= 0**, nhưng không thể tự xác minh tổng của mọi dòng đơn bằng đúng trường total ở đơn nếu các dòng nằm ở bảng khác. Tương tự:

- “Tổng số vé đã bán không vượt capacity” là bất biến nhiều hàng nếu vé lưu riêng.
- “Một phòng chỉ có một cuộc họp ở mỗi thời điểm” là bất biến giữa các khoảng thời gian.
- “Mỗi tài khoản chỉ có một yêu cầu rút tiền đang xử lý” là bất biến theo tập trạng thái.
- “Số dư hai tài khoản sau chuyển khoản vẫn bảo toàn tổng” là bất biến xuyên bản ghi.

Có thể chọn:

- **Thiết kế lại dữ liệu** để điều kiện được bảo vệ bởi UNIQUE, FK, EXCLUDE hoặc một hàng tổng hợp cập nhật nguyên tử.
- **Transaction với khóa hoặc isolation phù hợp**, kiểm tra rồi cập nhật trong cùng phạm vi có bảo đảm.
- **Trigger** khi thật sự cần, với hiểu biết về lock, thứ tự thao tác, kiểm thử và khả năng quan sát; trigger sai cũng có thể tạo race condition.
- **Ràng buộc ở cấp domain cộng cơ chế đối soát**, khi hệ lưu trữ phân tán không có giao dịch bao trùm và nghiệp vụ cho phép nhất quán cuối cùng.

Không nên viết “đã có transaction” rồi mặc định tất cả các bất biến đều an toàn. Với isolation yếu, hai transaction có thể đọc cùng trạng thái và ghi hai hàng khác nhau dẫn đến **write skew** nếu không có constraint hoặc locking thích hợp.

## 13. Schema evolution: thêm constraint cho dữ liệu đang chạy

Thêm một quy tắc mới thường phải xử lý dữ liệu cũ. Ví dụ muốn yêu cầu mọi customer có mã không rỗng:

~~~sql
-- Bước khảo sát trước khi thêm ràng buộc:
SELECT COUNT(*) AS invalid_rows
FROM customers
WHERE external_code IS NULL OR btrim(external_code) = '';
~~~

Nếu có bản ghi cũ không đạt, áp constraint ngay có thể thất bại hoặc làm gián đoạn ghi. Một lộ trình migration an toàn thường gồm:

1. **Định nghĩa chính xác quy tắc mới** và phạm vi áp dụng; phân biệt bản ghi lịch sử với bản ghi mới.
2. **Triển khai code ghi mới phù hợp** và kiểm tra các đường ghi từ API, batch, consumer và công cụ quản trị.
3. **Đo/kiểm kê dữ liệu cũ**, xác định cách làm sạch hoặc ngoại lệ hợp lệ, tránh sửa sai ngữ nghĩa.
4. **Backfill theo lô** có khả năng chạy lại nếu bảng lớn; giám sát lock, I/O, replication lag và tiến độ.
5. **Thêm và xác minh constraint** theo khả năng DB và chiến lược giảm lock tương ứng.
6. **Cập nhật code đọc và loại bỏ tương thích cũ** khi dữ liệu và tất cả phiên bản ứng dụng đã sẵn sàng.
7. **Kiểm thử rollback/restore**, đặc biệt khi có phiên bản ứng dụng cũ vẫn đang chạy.

PostgreSQL có cơ chế **ADD CONSTRAINT ... NOT VALID** và **VALIDATE CONSTRAINT** cho một số loại constraint như CHECK và FOREIGN KEY, giúp tách việc áp điều kiện với quét dữ liệu cũ trong các tình huống phù hợp. Không áp dụng máy móc **NOT VALID** cho mọi constraint, ví dụ UNIQUE. Với yêu cầu unique trên bảng lớn, có thể cân nhắc tạo unique index concurrently rồi dùng index để thiết lập constraint, theo đúng cú pháp, điều kiện và quy trình vận hành của PostgreSQL. Phải xử lý dữ liệu trùng trước khi bảo đảm unique.

**Constraint là một phần của hợp đồng dữ liệu lâu dài.** Nếu triển khai code validation trước nhưng chưa deploy migration tương ứng, trong khoảng chuyển tiếp DB vẫn có thể nhận dữ liệu mà code mới cho là sai. Cần chủ động thiết kế thứ tự deploy và compatibility giữa phiên bản cũ/mới.

## 14. Bảo mật và toàn vẹn dữ liệu là hai vấn đề liên quan

Một bản ghi thỏa NOT NULL, UNIQUE và FK vẫn có thể bị **đọc hoặc sửa trái phép**. Ví dụ một người dùng T1 biết đúng ID của hội thảo T2. Hệ thống không được cho phép đăng ký thay người của tenant khác chỉ vì FK tới T2 hợp lệ.

- **Authentication** xác định chủ thể gọi; **authorization** quyết định họ có quyền với tenant và thực thể đó không.
- Chỉ nên nhận tenantId từ **ngữ cảnh tin cậy**, không cho client tùy ý lựa chọn rồi dùng luôn trong SQL.
- Có thể dùng **Row-Level Security (RLS)** trên PostgreSQL khi kiến trúc phù hợp, nhưng phải cấu hình policy, vai trò truy cập và session context đúng cách; RLS không thay thế validation hoặc constraint.
- Ràng buộc DB không chống **SQL injection** nếu lập trình viên vẫn ghép dữ liệu đầu vào vào câu SQL. Dùng tham số cho giá trị và danh sách cho phép với các phần không thể tham số hóa như tên cột.
- Không đưa toàn bộ nội dung lỗi SQL hoặc giá trị nhạy cảm vào response/log. Ghi mã lỗi, request ID và thông tin đủ để chẩn đoán theo quyền truy cập.

Một hệ thống bền vững cần cả **toàn vẹn dữ liệu**, **kiểm soát truy cập** và **khả năng phục hồi**. Sao lưu/khôi phục phải kiểm tra constraint còn hoạt động và không phát sinh tham chiếu mồ côi, bản ghi trùng hoặc dữ liệu chưa được backfill.

## 15. Kiểm chứng và quan sát trong vận hành

Chất lượng thiết kế được xác nhận bằng tình huống thực tế, đặc biệt là các trường hợp cạnh tranh. Một kế hoạch kiểm thử có ý nghĩa:

| Tình huống | Kết quả mong muốn |
|---|---|
| Email trống, workshopId thiếu, dữ liệu sai kiểu | Bị từ chối trước khi dùng transaction |
| Hai request cùng email/hội thảo gửi đồng thời | Chỉ tối đa một đăng ký được commit theo UNIQUE |
| Hai email khác nhau tranh chỗ cuối | Chỉ một request trừ được chỗ và tạo đăng ký |
| UPDATE trừ chỗ thành công nhưng INSERT trùng | Cả transaction rollback; số chỗ không đổi |
| Đăng ký tham chiếu workshop tenant khác | FK ghép từ chối thao tác ghi |
| Ghi email chưa chuẩn hóa qua đường import | CHECK hoặc quy tắc ingest thống nhất từ chối/chuẩn hóa đúng |
| Client mất kết nối ngay lúc commit | Không tự kết luận “chưa ghi”; kiểm tra trạng thái/idempotency |
| Dữ liệu cũ vi phạm constraint mới | Migration báo chính xác dòng lỗi và có phương án xử lý |
| Restore backup trên môi trường kiểm tra | Dữ liệu, constraint, index và quan hệ được xác minh |

Trong production, theo dõi **tỷ lệ validation error theo trường**, **UNIQUE/FK/CHECK violation**, **số transaction rollback**, **serialization/deadlock retry**, **timeout**, **p95/p99 latency của ghi**, **tỷ lệ conflict**, và **số bản ghi không đạt kiểm tra đối soát**. Phân biệt những lỗi do người dùng nhập sai với lỗi do code hoặc migration, tránh dùng một biểu đồ “database errors” duy nhất.

Không nên coi constraint violation luôn là sự cố hạ tầng: trùng email có thể là một conflict nghiệp vụ bình thường. Ngược lại, tăng đột biến FK violation sau deploy có thể chỉ ra bug nghiêm trọng về tenant hoặc thứ tự ghi.

## 16. Bài thực hành: bảo vệ đăng ký trong hệ thống Java

Một hệ thống nhiều tenant có hội thảo với **capacity**, **remaining_seats** và danh sách đăng ký. Quy tắc:

- Email đăng ký phải đáp ứng định dạng và chính sách chuẩn hóa của ứng dụng.
- Trong một hội thảo chỉ có tối đa một đăng ký cho mỗi email đã chuẩn hóa.
- Mỗi đăng ký thuộc cùng tenant với hội thảo.
- Hội thảo phải ở trạng thái mở, chưa bắt đầu và còn chỗ mới nhận đăng ký.
- Khi tạo đăng ký lỗi, không được mất chỗ trong bảng workshops.

**Nhiệm vụ:**

1. Chia các quy tắc trên thành **validation API**, **quy tắc domain** và **constraint/transaction nơi lưu**. Giải thích các quy tắc cần bảo vệ ở nhiều lớp.
2. Viết DDL gồm **NOT NULL**, **CHECK**, **UNIQUE**, **PK** và **FK ghép tenant** thích hợp.
3. Mô tả timeline hai request cùng đăng ký email và giải thích vì sao **SELECT trước INSERT** không bảo đảm kết quả.
4. Viết câu UPDATE chỉ trừ chỗ khi còn chỗ; giải thích tại sao phải kiểm tra **affected rows**.
5. Đưa UPDATE và INSERT vào cùng transaction; trình bày kết quả khi INSERT vi phạm UNIQUE.
6. Đề xuất cách ánh xạ SQLSTATE **23505** và **23503** sang lỗi domain; không để lộ thông tin nhạy cảm.
7. Đề xuất giải pháp retry khi commit timeout và cách tránh đăng ký trùng do yêu cầu gửi lại.
8. Mô tả migration từ schema cũ không có UNIQUE theo email, bao gồm dọn dữ liệu trùng và chiến lược triển khai.
9. Thiết kế một kiểm thử đồng thời cho chỗ cuối cùng, kiểm tra cả số đăng ký và remaining_seats sau khi hai request kết thúc.

**Gợi ý hướng giải:** API kiểm tra dạng UUID và email, service chuẩn hóa và lấy tenant từ auth, domain xác nhận người dùng đủ quyền. DB bảo vệ khóa và quan hệ bằng PK/FK/UNIQUE/CHECK. Luồng ghi dùng UPDATE có điều kiện **remaining_seats >= 1** và **INSERT registrations** trong cùng transaction; nếu INSERT thất bại, rollback trả lại chỗ. Để xử lý retry sau lỗi kết nối, cần lưu một định danh yêu cầu/idempotency key phù hợp và đọc lại kết quả trước khi thử lại tác dụng nghiệp vụ. Migration phải xử lý dữ liệu trùng hiện hữu trước khi thiết lập UNIQUE.

### Câu hỏi tự kiểm tra

- Nếu đã kiểm tra email chưa tồn tại bằng SELECT, vì sao vẫn có thể xảy ra đăng ký trùng?
- Khi nào **CHECK (quantity > 0)** không chặn được một hàng có quantity thiếu?
- Tại sao CHECK của một hàng không đủ để bảo vệ số chỗ dựa trên nhiều hàng đăng ký?
- Transaction có thể rollback lệnh giảm chỗ trong trường hợp nào?
- Vì sao không nên tự động retry mọi câu INSERT khi client báo timeout?
- Khi triển khai constraint mới, vì sao cần khảo sát dữ liệu cũ và các đường ghi không đi qua API?
- Trong một hệ thống nhiều tenant, UNIQUE theo email đơn lẻ khác gì UNIQUE theo tenant, workshop và email?
- Validation, constraint và authorization phối hợp như thế nào, và mỗi lớp có giới hạn gì?

Sau bài học, người học cần phân biệt được **kiểm tra đầu vào để phản hồi yêu cầu** với **ràng buộc tại nơi lưu để bảo vệ trạng thái dữ liệu**, thiết kế schema và transaction tương ứng, triển khai xử lý lỗi persistence trong Java, và kiểm chứng rằng các bất biến vẫn được giữ khi nhiều tác vụ ghi đồng thời.
