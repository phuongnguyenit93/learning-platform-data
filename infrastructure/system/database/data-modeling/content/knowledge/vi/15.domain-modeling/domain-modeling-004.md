# Chọn ranh giới aggregate từ bất biến thay vì sao chép cấu trúc bảng

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định ranh giới **aggregate** từ các **bất biến nghiệp vụ** và thao tác ghi thay vì nhìn vào quan hệ khóa ngoại hay sơ đồ ERD.
- Viết điều kiện trước và sau của command; phân biệt ràng buộc phải đúng ngay lúc commit với mục tiêu cần phối hợp qua nhiều bước.
- So sánh các phương án aggregate theo khả năng giữ bất biến, vòng đời, quy mô dữ liệu, mức cạnh tranh ghi và chi phí thay đổi.
- Thiết kế aggregate root điều phối thay đổi, kiểm soát tham chiếu sang aggregate khác và bảo vệ cập nhật đồng thời.
- Ánh xạ thiết kế sang lược đồ quan hệ, constraint, chỉ mục, transaction; nhận biết khi cần đồng bộ hóa hoặc quy trình bất đồng bộ.
- Kiểm chứng quyết định ranh giới bằng tình huống cạnh tranh, yêu cầu thay đổi và phản ví dụ.

Trong module **DATABASE_DATA_MODELING**, mục tiêu là chuyển một yêu cầu nghiệp vụ thành mô hình có thực thể, quan hệ và ràng buộc rõ ràng, rồi chọn cấu trúc vật lý phù hợp. Một lỗi thường gặp là lấy ERD làm khuôn cho mô hình miền: mỗi bảng trở thành một aggregate, hoặc mọi bảng liên kết bằng khóa ngoại được gom vào một aggregate lớn. Cả hai cách đều bỏ qua câu hỏi quan trọng nhất: **những dữ liệu nào phải thay đổi cùng nhau để một quy tắc vẫn đúng sau mỗi giao dịch?**

## 1. Bắt đầu bằng vấn đề: lớp học có giới hạn chỗ

Xét nền tảng đăng ký khóa học trực tuyến, mỗi đợt mở lớp (*offering*) có số lượng chỗ hữu hạn:

- Lớp Java nâng cao có **30 chỗ**.
- Một học viên chỉ được có **một đăng ký còn hiệu lực** cho cùng đợt mở lớp.
- Học viên được **giữ chỗ** trong 10 phút trước khi thanh toán; giữ chỗ hết hạn sẽ giải phóng suất.
- Không được xác nhận vượt quá 30 chỗ, kể cả khi hàng trăm yêu cầu đến cùng lúc.
- Hồ sơ học viên có thể đổi tên hoặc email mà không làm thay đổi danh tính lượt đăng ký.
- Thanh toán được xử lý bởi một hệ thống khác; phản hồi có thể chậm, lặp hoặc thất bại.

Những danh từ dễ nhận ra gồm Course, Offering, Student, Enrollment, SeatHold và Payment. Ta có thể vẽ các quan hệ:

~~~mermaid
erDiagram
    COURSE ||--o{ OFFERING : opens
    OFFERING ||--o{ ENROLLMENT : has
    STUDENT ||--o{ ENROLLMENT : registers
    ENROLLMENT ||--o{ PAYMENT_ATTEMPT : requests
~~~

**Đây là sơ đồ liên hệ dữ liệu, chưa phải sơ đồ aggregate.** Nó cho biết những bản ghi nào liên quan; nó chưa trả lời ai có quyền xác nhận chỗ, kiểm tra đủ suất, hoặc ngăn hai yêu cầu đồng thời lấy chỗ cuối cùng.

Nếu gom cả Course, Offering, Student, Enrollment và Payment vào một root chỉ vì có đường liên kết, ta sẽ có một mô hình khổng lồ, nhiều vòng đời xung đột. Ngược lại, nếu mỗi bảng là một aggregate độc lập và chỉ kiểm tra chỗ bằng một câu SELECT rồi INSERT, hai request đồng thời đều có thể nhìn thấy "còn một chỗ" và cùng ghi thành công.

## 2. Bất biến là đầu vào của quyết định ranh giới

**Bất biến (invariant)** là điều kiện không được sai tại những trạng thái nghiệp vụ hợp lệ mà hệ thống cam kết duy trì. Khi phân tích, cần viết chính xác **phạm vi**, **thời điểm phải đúng** và **bên có quyền quyết định**.

| Quy tắc | Phạm vi dữ liệu tối thiểu | Khi nào phải đúng? | Chủ sở hữu dự kiến |
| --- | --- | --- | --- |
| Số chỗ đã chiếm không vượt sức chứa | Một Offering/nguồn chỗ tương ứng | Ngay khi cấp hoặc giải phóng chỗ commit | Seat Capacity / Enrollment |
| Một học viên không có hai đăng ký hoạt động cho cùng Offering | Cặp (offeringId, studentId) | Ngay sau khi ghi đăng ký | Enrollment/đăng ký học |
| Lượt giữ chỗ hết hạn không còn quyền xác nhận | Một lượt giữ và thời điểm hiệu lực | Trước khi cho phép xác nhận | Seat Hold / Enrollment |
| Đăng ký đã xác nhận không được sửa thông tin giá cam kết | Một đăng ký và giá tại thời điểm chốt | Ngay sau mỗi thay đổi đăng ký | Enrollment |
| Hệ thống chỉ phát hành quyền học sau khi thanh toán hợp lệ | Enrollment + thông tin Payment | Khi hoàn thành quy trình đăng ký | Workflow phối hợp |
| Email học viên là email hiện hành trong hồ sơ | Một Student | Khi hồ sơ được cập nhật | Student |

Quy tắc "không vượt sức chứa" là ví dụ về **bất biến tức thời**: dù màn hình có hiển thị dữ liệu chậm, kho chỗ không được bán vượt 30. Quy tắc "thanh toán rồi cấp quyền học" có thể là **quy trình nhiều bước**: hệ thống có thể tồn tại trạng thái HELD hoặc PAYMENT_PENDING trước khi hoàn tất. Không được lấy việc chấp nhận nhất quán cuối cùng ở luồng thanh toán làm lý do cho phép vượt sức chứa.

### Câu hỏi quan trọng: "ngay lập tức" nghĩa là gì?

Trong một hệ quản trị có transaction ACID, một thao tác nguyên tử có thể làm nhiều hàng thay đổi cùng lúc. Nhưng giới hạn của transaction **không tự động bằng** giới hạn aggregate:

- Aggregate là **quyết định thiết kế miền** về một đơn vị chịu trách nhiệm bảo vệ bất biến.
- Transaction là **cơ chế lưu trữ** giúp duy trì tính nguyên tử khi ghi.
- Một transaction có thể ghi nhiều bảng của cùng aggregate.
- Trong một số hệ thống đơn khối, transaction cũng có thể ghi **nhiều aggregate** nếu có bất biến thật sự cần điều đó; đây là quyết định có chi phí liên kết, không phải quy tắc mặc định.
- Nếu dữ liệu nằm ở những dịch vụ hoặc database độc lập, không được giả định transaction địa phương bao phủ tất cả.

Mục tiêu là **định nghĩa đúng cam kết nghiệp vụ trước**, rồi chọn cơ chế thực thi thực tế đáp ứng cam kết ấy.

## 3. Vì sao cấu trúc bảng không xác định ranh giới aggregate?

### Sai lầm A: Một bảng tương ứng một aggregate

Giả sử bảng Offering giữ sức chứa, bảng Enrollment giữ học viên đăng ký. Nếu cả hai được ghi độc lập mà không có cơ chế đồng bộ, có thể xảy ra:

1. Transaction T1 đọc lớp còn 1 chỗ.
2. Transaction T2 cũng đọc lớp còn 1 chỗ.
3. T1 ghi một Enrollment hoạt động.
4. T2 cũng ghi một Enrollment hoạt động.
5. Tổng đăng ký vượt capacity dù từng INSERT đều hợp lệ.

Khóa ngoại từ Enrollment đến Offering chỉ bảo đảm Offering tồn tại. **Khóa ngoại không áp dụng điều kiện "COUNT(enrollment hoạt động) không quá capacity".** Vì vậy không thể quyết định rằng hai thao tác được ghi tùy ý chỉ vì chúng ở hai bảng khác nhau.

### Sai lầm B: Mọi bảng nối FK đều thuộc một aggregate

Student có thể tham gia nhiều lớp; Course có thể mở nhiều Offering; Payment có vòng đời xử lý/hoàn tiền riêng. Nếu root Offering phải nạp và sửa cả hồ sơ học viên, chương trình học và giao dịch thanh toán, mọi thay đổi sẽ kéo theo dữ liệu không liên quan và phá ranh giới trách nhiệm.

Một thực thể thuộc aggregate không chỉ vì có FK đến root. Hỏi thêm:

- Thực thể có **vòng đời độc lập** hay chỉ tồn tại như một phần của root?
- Root có thực sự cần điều phối **mọi thao tác sửa** thực thể đó để bảo vệ bất biến không?
- Thực thể có cần được cập nhật mà không đọc/khóa root hay không?
- Nếu chia riêng, có thể bảo vệ bất biến bằng constraint hoặc một command nguyên tử khác không?

### Sai lầm C: Dùng độ tiện của truy vấn đọc để chia ranh giới ghi

Trang "chi tiết lớp học" có thể ghép tên khóa học, giảng viên, số chỗ và danh sách học viên. Nhu cầu hiển thị chung không có nghĩa chúng phải commit chung. Có thể sử dụng JOIN, read model, projection hoặc truy vấn nhiều nguồn. **Ranh giới đọc và ranh giới nhất quán ghi phục vụ hai mục đích khác nhau.**

## 4. Quy trình sáu bước để thiết kế từ bất biến

### Bước 1 — Ghi command bằng ngôn ngữ nghiệp vụ

Thay cho "cập nhật bảng Enrollment", hãy liệt kê hành động:

| Command | Người/nguồn phát lệnh | Kết quả cần tạo |
| --- | --- | --- |
| HoldSeat(offeringId, studentId, requestId) | Học viên | Một lượt giữ chỗ còn hiệu lực hoặc lời từ chối rõ ràng |
| ConfirmEnrollment(enrollmentId, paymentReference) | Quy trình đăng ký | Đăng ký đã xác nhận, không cấp thêm chỗ lần nữa |
| CancelEnrollment(enrollmentId) | Học viên/quản trị theo quyền | Trạng thái hủy và quyền giữ chỗ được giải phóng nếu phù hợp |
| ExpireSeatHold(enrollmentId) | Bộ xử lý thời hạn | Lượt giữ quá hạn mất quyền chiếm chỗ |
| ChangeCapacity(offeringId, newCapacity) | Quản trị | Sức chứa mới hợp lệ, không thấp hơn chỗ đang chiếm |

Command mô tả mục đích nghiệp vụ, điều kiện trước/sau và phản ứng khi thất bại. Phân biệt command với CRUD sẽ làm rõ aggregate nào cần nhận trách nhiệm.

### Bước 2 — Viết điều kiện sau một giao dịch thành công

Ví dụ với HoldSeat:

- Nếu thành công, tồn tại đúng một lượt giữ hoạt động cho học viên tại Offering.
- Tổng chỗ chiếm (HELD + CONFIRMED) không vượt capacity.
- Retry của cùng requestId không làm tăng số chỗ đã chiếm.
- Nếu hết chỗ, command thất bại và không tạo bản ghi giữ chỗ nửa vời.

Nếu chưa mô tả được những điều này, việc chọn root hay viết bảng mới còn quá sớm.

### Bước 3 — Phân loại bất biến theo phạm vi sở hữu

Một Enrollment tự kiểm soát chuyển trạng thái HELD → CONFIRMED và giá đã chốt. Một Seat Capacity/Offering phải quyết định có còn chỗ hay không. Hạng thành viên hoặc trạng thái Payment là dữ liệu từ một chủ sở hữu khác.

Đánh dấu:

1. **Nội bộ một thực thể/value object:** số lượng dương, thời hạn hợp lệ.
2. **Liên nhiều thành viên cần commit chung:** sức chứa và quyền giữ chỗ.
3. **Liên nhiều aggregate nhưng cùng nơi lưu:** có thể dùng transaction cục bộ có kiểm soát, đồng thời cân nhắc chi phí ghép.
4. **Xuyên dịch vụ/cơ sở dữ liệu:** phải thiết kế trạng thái trung gian, hợp đồng, retry và bù nếu không có cơ chế giao dịch phân tán được chủ động lựa chọn.

### Bước 4 — Chọn root điều phối thay đổi

Root cần có danh tính có ý nghĩa (ví dụ offeringId) và thao tác như holdSeat, releaseSeat, changeCapacity. Bên ngoài không được sửa trực tiếp trạng thái thành viên rồi bỏ qua kiểm tra sức chứa.

Quan hệ với Student được giữ qua studentId; quan hệ với Payment qua paymentReference và kết quả đã được xác thực. Root không cần nhúng toàn bộ hồ sơ Student hay trạng thái nội bộ của cổng thanh toán.

### Bước 5 — Đánh giá quy mô và tranh chấp

Nếu một lớp chỉ có tối đa 30 học viên, nạp các bản ghi giữ chỗ đang hiệu lực cùng Offering có thể hợp lý. Nếu một sự kiện trực tuyến có 100.000 suất và hàng chục nghìn yêu cầu/giây, cùng cách nạp toàn bộ danh sách vào root có thể trở thành điểm nghẽn.

Đừng chia nhỏ chỉ để né khóa: khi sức chứa là **một giới hạn chung**, mọi lệnh cấp chỗ phải vẫn được phân xử bởi một cơ chế giữ được giới hạn chung. Chia shard theo học viên mà không có hạn mức mỗi shard có thể bán vượt số chỗ.

### Bước 6 — Ánh xạ xuống lưu trữ, kiểm chứng rồi điều chỉnh

Chỉ sau khi hiểu command và bất biến, thiết kế khóa, bảng, constraint, phiên bản, chỉ mục, transaction và hợp đồng tích hợp. Kiểm thử hai người lấy chỗ cuối cùng, một request được gửi hai lần, hủy và xác nhận đồng thời, giảm sức chứa trong lúc có giữ chỗ. Nếu kiểm thử bộc lộ xung đột hoặc phải nạp quá nhiều dữ liệu, điều chỉnh ranh giới.

## 5. Phương án A: Offering là root với các lượt đăng ký con

Với lớp quy mô nhỏ và quy tắc đăng ký đơn giản, có thể xem **Offering** là aggregate root. Những lượt giữ và đăng ký cho chính Offering đó là thành viên do Offering quản lý:

~~~mermaid
flowchart TB
    App["Use case đăng ký"]
    App -->|"holdSeat(studentId)"| Root

    subgraph B["Aggregate Offering"]
      Root["Offering (root)"]
      SeatA["Enrollment A (entity con)"]
      SeatB["Enrollment B (entity con)"]
      Root -->|"quản lý quyền giữ"| SeatA
      Root -->|"quản lý quyền giữ"| SeatB
    end

    Student["Student aggregate"]
    Payment["Payment aggregate"]
    Root -.->|"studentId"| Student
    Root -.->|"payment reference"| Payment
~~~

Một lần holdSeat hợp lệ đọc trạng thái root, kiểm tra số chỗ còn lại, chống trùng học viên, thêm Enrollment và commit tất cả như một thao tác. Root kiểm soát:

- capacity và tổng số lượt giữ/xác nhận hợp lệ;
- không trùng học viên còn hiệu lực;
- chuyển trạng thái và thời hạn giữ;
- không giảm capacity thấp hơn số chỗ đang chiếm.

**Ưu điểm:** mô hình gần quy tắc nghiệp vụ, dễ nhìn thấy mọi thay đổi ảnh hưởng giới hạn chỗ; có thể lưu nhiều bảng nhưng transaction chung. **Nhược điểm:** root có thể phình lớn khi số đăng ký tăng hoặc giữ lịch sử vô hạn; mọi yêu cầu tranh chấp cùng Offering, gây lock/contention.

Không phải vì bảng enrollment có khóa ngoại offering_id mà nó mặc nhiên là entity con. Lý do gộp là **những command đang bảo vệ bất biến của chính Offering** và số thành viên có thể quản lý được.

### Cách triển khai quan hệ cho phương án A

Có thể dùng bảng offering và enrollment, nhưng tất cả đường ghi enrollment phải thực hiện thông qua thao tác Offering trong cùng transaction. Một lựa chọn khi số hàng nhỏ:

~~~text
BEGIN
  Khóa hàng Offering bằng SELECT ... FOR UPDATE
  Đọc số Enrollment đang HELD hoặc CONFIRMED
  Kiểm tra còn chỗ và học viên chưa có đăng ký đang hiệu lực
  Thêm Enrollment/đổi trạng thái qua thao tác miền
COMMIT
~~~

Việc khóa hàng Offering **chỉ bảo vệ đúng** khi mọi đường ghi ảnh hưởng tới số chỗ đều tuân thủ cùng quy trình khóa. Một ứng dụng khác có quyền INSERT trực tiếp enrollment mà không khóa root có thể phá bất biến; cần giới hạn quyền ghi và bổ sung constraint/kiểm soát ở tầng database.

## 6. Phương án B: SeatPool và Enrollment có vòng đời riêng

Với lưu lượng lớn hoặc nghiệp vụ Enrollment phải tồn tại lâu dài để quản lý chứng chỉ, hoàn tiền và chuyển lớp, có thể tách:

- **SeatPool** có danh tính offeringId, quản lý capacity và số chỗ đang chiếm. Bất biến cục bộ: 0 ≤ seatsTaken ≤ seatsTotal.
- **Enrollment** có enrollmentId, studentId, offeringId, trạng thái HELD/CONFIRMED/CANCELLED/EXPIRED, snapshot giá và lịch sử nghiệp vụ.
- **Student** và **Payment** vẫn là aggregate khác với quyền sở hữu riêng.

~~~mermaid
flowchart LR
    C["HoldSeat command"] --> P["SeatPool root<br/>cấp quyền chiếm chỗ"]
    C --> E["Enrollment root<br/>vòng đời đăng ký"]
    E -.->|"offeringId"| P
    E -.->|"studentId"| S["Student"]
    E -.->|"paymentReference"| T["Payment"]
~~~

**Điểm cần thừa nhận:** hai root riêng không tự giữ bất biến "seatsTaken bằng số đăng ký đang chiếm chỗ". Nếu SeatPool và Enrollment cùng ở một PostgreSQL database, ứng dụng có thể cập nhật hai root trong **một transaction cục bộ** để bảo vệ quan hệ đó. Đây là một lựa chọn có ý thức, dù hướng dẫn thiết kế aggregate thường khuyến khích giảm transaction xuyên root.

Nếu hai root nằm ở hai database độc lập, cần thay đổi giao thức: SeatPool có thể cấp một **reservationId/token** duy nhất và giữ bất biến sức chứa ngay tại nguồn; Enrollment lưu kết quả bằng một quy trình có trạng thái, retry/idempotency và bù khi thất bại. Không biến quy tắc "không vượt sức chứa" thành quy tắc nhất quán cuối cùng chỉ vì chia service.

| Tiêu chí | Offering chứa Enrollment (A) | SeatPool + Enrollment (B) |
| --- | --- | --- |
| Chủ sở hữu sức chứa | Offering root | SeatPool root |
| Vòng đời đăng ký | Phụ thuộc Offering | Enrollment độc lập hơn |
| Chi phí nạp/thay đổi | Có thể tăng theo lượng thành viên | Có thể thay đổi bộ đếm nhỏ, xử lý Enrollment riêng |
| Tranh chấp ghi | Tập trung ở Offering | Quyền cấp chỗ vẫn có điểm phân xử chung ở SeatPool |
| Quy tắc liên bản ghi | Nhất quán trong aggregate | Cần transaction hoặc giao thức cấp quyền rõ ràng |
| Khi phù hợp | Nhóm hữu hạn, nghiệp vụ ít thay đổi | Tải cao, lịch sử dài, trách nhiệm tách biệt |

Không có phương án nào đúng cho mọi hệ thống. Lý do chọn B phải là nhu cầu độc lập vòng đời, quy mô hoặc thông lượng **đã được phân tích**, không đơn thuần vì hai bảng đang tồn tại.

## 7. Hiện thực phương án B bằng PostgreSQL

Ví dụ sau giới hạn phạm vi vào một database để minh họa **một giao dịch giữ chỗ không vượt capacity**. Thông tin Course, Student và Payment được quản lý bởi những mô hình khác và không có DDL trong ví dụ.

~~~sql
CREATE SCHEMA IF NOT EXISTS academy;

CREATE TABLE academy.offering_capacity (
    offering_id UUID PRIMARY KEY,
    seats_total INTEGER NOT NULL CHECK (seats_total > 0),
    seats_taken INTEGER NOT NULL DEFAULT 0 CHECK (seats_taken >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    CONSTRAINT capacity_not_exceeded CHECK (seats_taken <= seats_total)
);

CREATE TABLE academy.enrollment (
    enrollment_id UUID PRIMARY KEY,
    offering_id UUID NOT NULL
        REFERENCES academy.offering_capacity(offering_id),
    student_id UUID NOT NULL,
    request_id UUID NOT NULL UNIQUE,
    status VARCHAR(12) NOT NULL
        CHECK (status IN ('HELD', 'CONFIRMED', 'CANCELLED', 'EXPIRED')),
    hold_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Không có hai Enrollment hoạt động cho cùng học viên và Offering.
CREATE UNIQUE INDEX one_active_enrollment_per_student
    ON academy.enrollment (offering_id, student_id)
    WHERE status IN ('HELD', 'CONFIRMED');

-- Giúp tìm và xử lý các lượt giữ cần hết hạn.
CREATE INDEX enrollment_held_expiry
    ON academy.enrollment (hold_expires_at)
    WHERE status = 'HELD';
~~~

**Ý nghĩa ràng buộc:**

- CHECK trên offering_capacity bảo vệ giới hạn của hàng nguồn: số chỗ đang chiếm không vượt số chỗ công bố.
- Chỉ mục UNIQUE có điều kiện ngăn hai đăng ký **đang hoạt động** cho cùng học viên ở cùng Offering, nhưng vẫn có thể lưu lịch sử CANCELLED/EXPIRED. Nếu nghiệp vụ cấm đăng ký lại sau khi hủy, cần thay quy tắc duy nhất.
- request_id hỗ trợ phân biệt lệnh giữ chỗ mới với yêu cầu retry cùng một thao tác. Một lệnh tạo mới sau khi hủy phải dùng request_id mới.
- hold_expires_at cần được kiểm tra khi xác nhận giữ chỗ và bởi tác vụ giải phóng quá hạn. Lưu thời hạn không có nghĩa DB tự chuyển trạng thái khi đồng hồ chạy.
- Chỉ mục hết hạn giúp công việc định kỳ tìm HELD dễ hơn; chỉ mục cần được đánh giá với số lượng hàng và workload thực tế.

### Giao dịch lấy một chỗ

Quy trình dưới đây chạy trong **một transaction**. Ứng dụng bắt buộc kiểm tra kết quả của từng câu lệnh trước khi tiếp tục:

~~~sql
BEGIN;

-- 1. Đăng ký một yêu cầu đang giữ chỗ.
INSERT INTO academy.enrollment
    (enrollment_id, offering_id, student_id, request_id,
     status, hold_expires_at)
VALUES
    (:enrollment_id, :offering_id, :student_id, :request_id,
     'HELD', :hold_expires_at)
ON CONFLICT DO NOTHING
RETURNING enrollment_id;

-- Nếu trả 0 hàng: ROLLBACK ngay; không chạy bước 2.
-- Phân biệt retry theo request_id với xung đột học viên đã đăng ký,
-- rồi trả kết quả hiện có hoặc lỗi nghiệp vụ thích hợp.

-- 2. Chỉ cấp chỗ nếu nguồn còn chỗ; UPDATE là thao tác nguyên tử.
UPDATE academy.offering_capacity
SET seats_taken = seats_taken + 1,
    version = version + 1
WHERE offering_id = :offering_id
  AND seats_taken < seats_total
RETURNING offering_id, seats_taken;

-- Nếu trả 0 hàng: ROLLBACK cả INSERT và UPDATE; báo đã hết chỗ
-- hoặc Offering không tồn tại.

COMMIT;
~~~

Khi hai học viên tranh chỗ thứ 30, hai câu UPDATE có điều kiện trên **cùng một hàng** sẽ được PostgreSQL đồng bộ hóa. Sau khi giao dịch đầu tiên cập nhật, giao dịch thứ hai sẽ đánh giá điều kiện trên trạng thái mới và không thể tăng vượt seats_total. Điều này áp dụng khi những thao tác liên quan đều sử dụng quy trình/constraint tương ứng, không có đường ghi bỏ qua.

Khi cùng request_id được gửi lại sau khi commit nhưng client mất phản hồi, INSERT trả 0 hàng vì xung đột UNIQUE. Ứng dụng **không tăng seats_taken lần nữa**; thay vào đó tra cứu đăng ký của request_id ấy và trả kết quả phù hợp. Hai request_id khác nhau cho cùng học viên được chỉ mục duy nhất có điều kiện bảo vệ.

**Giới hạn của ví dụ:** CHECK chỉ xác minh seats_taken nằm trong khoảng hợp lệ; nó **không** so sánh seats_taken với số dòng HELD/CONFIRMED. Đẳng thức giữa bộ đếm và các bản ghi phải được bảo vệ bằng transaction cùng mọi lệnh đổi trạng thái, quyền ghi hạn chế và cơ chế kiểm tra/đối soát. Nếu hệ thống cần bảo vệ cả khi có người chạy SQL tùy ý, phải thiết kế thêm cơ chế ở database và kiểm soát quyền thao tác.

### Giải phóng chỗ không được trừ hai lần

Khi hủy hoặc để lượt giữ quá hạn, cần thay trạng thái Enrollment và giảm bộ đếm trong **cùng transaction**, chỉ khi lượt giữ trước đó còn chiếm chỗ:

~~~sql
BEGIN;

UPDATE academy.enrollment
SET status = 'EXPIRED'
WHERE enrollment_id = :enrollment_id
  AND status = 'HELD'
  AND hold_expires_at <= CURRENT_TIMESTAMP
RETURNING offering_id;

-- Nếu trả 0 hàng: không giảm seats_taken; ROLLBACK/kết thúc phù hợp.
-- Nếu trả 1 hàng: dùng offering_id được trả về cho bước sau.

UPDATE academy.offering_capacity
SET seats_taken = seats_taken - 1,
    version = version + 1
WHERE offering_id = :returned_offering_id
  AND seats_taken > 0;

-- Kiểm tra đúng 1 hàng; nếu không, ROLLBACK để tránh lệch dữ liệu.
COMMIT;
~~~

Hai tác vụ cùng cố hết hạn một Enrollment sẽ tranh khóa trên chính hàng Enrollment; chỉ tác vụ chuyển thành công từ HELD sang EXPIRED mới được giảm bộ đếm. Khi CONFIRMED, thao tác đổi trạng thái từ HELD sang CONFIRMED **không tăng thêm chỗ đã chiếm**, vì chỗ đã được tính khi giữ.

Nếu đồng thời có lệnh xác nhận và lệnh hết hạn, phải xác định kết quả dựa trên trạng thái và **thời hạn tại thời điểm xử lý**. Xác nhận chỉ hợp lệ nếu vẫn HELD, chưa quá hạn và đã có bằng chứng thanh toán theo chính sách. Không được chấp nhận một sự kiện Payment cũ để phục hồi quyền giữ đã hết hạn.

### Đổi sức chứa cũng là command cần bất biến

Quản trị viên không thể tùy ý đặt seats_total = 20 khi đã có 25 chỗ đang chiếm. Thao tác có điều kiện:

~~~sql
UPDATE academy.offering_capacity
SET seats_total = :new_total,
    version = version + 1
WHERE offering_id = :offering_id
  AND :new_total > 0
  AND :new_total >= seats_taken
  AND version = :expected_version;
~~~

Ứng dụng phải kiểm tra số hàng được cập nhật, xử lý xung đột và thông báo rõ lý do không thể giảm. Nếu thay đổi capacity ảnh hưởng hợp đồng đã bán, có thể cần thêm quy trình phê duyệt/hoàn tiền ngoài quy tắc số học.

## 8. Khi bất biến đi qua ranh giới database hoặc dịch vụ

Giả sử Payment là một service độc lập. Lệnh HoldSeat chỉ cấp **quyền giữ** trong SeatPool; nó không ghi thẳng trạng thái ngân hàng. Quy trình có thể như sau:

~~~mermaid
sequenceDiagram
    participant U as User
    participant A as Enrollment
    participant S as SeatPool
    participant P as Payment

    U->>A: Yêu cầu đăng ký (requestId)
    A->>S: HoldSeat (offeringId, studentId)
    S-->>A: Reserved (reservationId, expiresAt)
    A-->>U: HELD, chờ thanh toán
    A->>P: AuthorizePayment (paymentRequestId)
    P-->>A: PaymentAuthorized (paymentId)
    A->>S: ConfirmHold (reservationId)
    S-->>A: Confirmed hoặc Expired
    A-->>U: Đã xác nhận hoặc cần xử lý thất bại
~~~

Trong kịch bản này, SeatPool phải bảo vệ **số chỗ được cấp** ngay ở bước HoldSeat. Enrollment có thể tạm ở HELD/PAYMENT_PENDING. Khi Payment phản hồi thành công nhưng giữ chỗ đã hết hạn, quy trình phải xử lý thất bại một cách nghiệp vụ (ví dụ hủy ủy quyền hoặc hoàn tiền) thay vì cấp quyền học không có chỗ.

Những yếu tố bắt buộc thiết kế:

- **Idempotency:** requestId và reservationId giúp retry không cấp hai chỗ; paymentRequestId giúp lệnh thanh toán không thu nhiều lần.
- **Trạng thái trung gian:** HELD, CONFIRMED, EXPIRED, CANCELLED và các trạng thái Payment theo hợp đồng của hệ thống thanh toán.
- **Thời hạn:** thời điểm hết hạn được kiểm tra bởi nguồn quản lý quyền giữ, không tin riêng đồng hồ của trình duyệt.
- **Thông điệp:** dùng eventId, version hoặc sequence thích hợp để nhận biết lặp và lỗi thứ tự.
- **Đảm bảo phát sự kiện:** khi có broker, transactional outbox/inbox có thể giúp ghi dữ liệu và ghi nhận thông điệp theo transaction cục bộ, đồng thời xử lý retry.
- **Bù và đối soát:** giải phóng giữ chỗ, hủy ủy quyền hoặc hoàn tiền tùy việc thực sự đã xảy ra; bù không phải rollback xuyên hệ thống.

Một quy trình chấp nhận nhất quán cuối cùng ở trạng thái Enrollment vẫn có thể giữ bất biến tuyệt đối tại SeatPool. Hai mức nhất quán này không mâu thuẫn nếu ranh giới trách nhiệm được xác định rõ.

## 9. Thử quyết định ranh giới bằng các phản ví dụ

| Tình huống | Phân tích cần thực hiện | Hệ quả với thiết kế |
| --- | --- | --- |
| Hai học viên lấy chỗ cuối cùng | Kiểm tra cùng nguồn capacity, thao tác nguyên tử, không tin SELECT cũ | Root/cơ chế khóa tại nguồn cấp chỗ |
| Một học viên gửi hai requestId khác nhau | UNIQUE theo (offeringId, studentId) với điều kiện trạng thái | Bảo vệ quy tắc học viên song song với capacity |
| Client retry cùng requestId | Lệnh phải trả cùng kết quả, không tăng bộ đếm lại | Ghi nhận idempotency và đối chiếu kết quả |
| Payment thành công sau khi giữ chỗ hết hạn | Cần kiểm tra quyền giữ khi xác nhận | Quy trình bù/hoàn tiền, không tái tạo chỗ tùy tiện |
| Quản trị giảm capacity lúc đang ghi giữ chỗ | Cùng nguồn ghi với điều kiện seats_taken ≤ seats_total | Dùng lock/version và UPDATE có điều kiện |
| Lớp có 100.000 học viên | Root chứa toàn bộ Enrollment khó tải/lưu | Cân nhắc SeatPool nhỏ và Enrollment root riêng |
| Bộ phận kế toán cần báo cáo theo khóa học | Nhiều bảng/aggregate cần được JOIN khi đọc | Read model riêng, không ép aggregate lớn hơn |
| Chuyển học viên từ Offering A sang B | Nếu phải cấp B và trả A cùng lúc, có ràng buộc liên hai nguồn chỗ | Transaction nhiều hàng cùng DB hoặc workflow bù |

Hai câu hỏi quyết định:

1. Nếu một giao dịch **thành công cục bộ** nhưng bước sau chưa xong, dữ liệu nào vẫn bắt buộc đúng?
2. Nếu hai request đến **cùng thời điểm**, điểm phân xử nào ngăn hệ thống chấp nhận hai kết quả xung đột?

Nếu không chỉ ra được câu trả lời cụ thể, ranh giới aggregate còn thiếu cơ sở kiểm chứng.

## 10. Cách lựa chọn ảnh hưởng đến mô hình vật lý

Ranh giới aggregate là một quyết định miền; cách lưu trữ cần phục vụ nó thay vì dẫn dắt ngược:

| Hướng lưu trữ | Mô hình ví dụ | Rủi ro cần xét |
| --- | --- | --- |
| **Quan hệ** | Offering/SeatPool và Enrollment ở một hoặc nhiều bảng; transaction, UNIQUE, CHECK, FK | Đường ghi bỏ qua root, lost update, khóa lâu và contention |
| **Document** | Một Offering document chứa các lượt giữ nếu phạm vi nhỏ; hoặc tách document SeatPool và Enrollment | Kích thước document, mức nguyên tử của cập nhật, xung đột sửa cùng document |
| **Đồ thị** | Student, Offering, Enrollment có quan hệ nhiều chiều để khai thác mạng học tập | Duyệt cạnh không tự giải quyết bất biến capacity hay transaction |
| **Phân tích/cột** | FactEnrollment, dimension Course/Student và dữ liệu lịch sử | Projection có thể chậm và không nên làm nguồn quyết định cấp suất |

Khi thiết kế bảng vật lý, hãy kiểm tra:

- **Khóa chính:** ID của root hay danh tính của entity con trong phạm vi root là gì?
- **Khóa ngoại:** quan hệ nào được DB kiểm soát trong cùng ranh giới sở hữu, quan hệ nào là tham chiếu sang nguồn khác?
- **Ràng buộc:** UNIQUE, CHECK, FK và chỉ mục có điều kiện giúp bảo vệ bất biến nào, còn bất biến nào cần giao dịch?
- **Chỉ mục:** truy vấn theo offeringId/studentId, tra cứu requestId, hết hạn giữ chỗ và các báo cáo có thực sự cần hỗ trợ không?
- **Dữ liệu lịch sử:** giá đã cam kết, phiên bản chính sách và thời điểm đăng ký có cần snapshot không?
- **Chi phí ghi:** một root có tạo hàng nóng (*hot row*), deadlock, transaction dài hoặc xung đột version quá nhiều không?

**Không suy ra rằng cần microservice cho mỗi aggregate.** Một hệ thống nguyên khối với những module có quyền sở hữu rõ ràng và transaction cục bộ có thể là thiết kế rất phù hợp. Tách triển khai chỉ khi lợi ích độc lập vận hành vượt chi phí tích hợp.

## 11. Bài tập: chọn ranh giới cho thuê thiết bị

**Bối cảnh:** Công ty cho thuê máy quay có nhiều kho. Một hợp đồng có thể thuê nhiều thiết bị; từng thiết bị có số serial riêng, ngày bắt đầu/kết thúc thuê và tình trạng bảo trì. Một thiết bị không được cấp cho hai hợp đồng có **khoảng thuê giao nhau**. Khách có thể thanh toán cọc qua cổng thanh toán bên ngoài. Báo cáo quản trị cần xem doanh thu, tình trạng thiết bị và hợp đồng theo từng kho.

**Yêu cầu:**

1. Liệt kê tối thiểu bốn command nghiệp vụ và viết bất biến tương ứng.
2. Chọn aggregate root cho hợp đồng và cho quyền cấp một thiết bị trong một khoảng thời gian. Có cần gộp tất cả hợp đồng, khách hàng, thiết bị và thanh toán vào cùng aggregate không?
3. Đề xuất cách chống hai hợp đồng cùng thuê một thiết bị trùng thời gian khi hai yêu cầu ghi đồng thời.
4. Khi hợp đồng thuê ba thiết bị và khách yêu cầu **chỉ xác nhận nếu đủ cả ba**, cách nào bảo vệ điều kiện này?
5. Nếu hệ thống dùng PostgreSQL và tách quyền cấp thiết bị khỏi hợp đồng, cần constraint/transaction và bước bù nào? Báo cáo quản trị nên đọc dữ liệu ra sao?

**Hướng giải định hướng:**

- Command có thể gồm CreateRental, ReserveDevice, ConfirmRental, CancelRental, ReturnDevice. Bất biến: khoảng thuê bắt đầu trước kết thúc; một serial không có hai quyền cấp còn hiệu lực với thời gian giao nhau; hợp đồng đã xác nhận không được tự ý đổi giá/cấu hình thuê; thiết bị bảo trì không được cấp nếu chính sách cấm.
- RentalContract là root cho dòng thuê và giá đã chốt. Quyền đặt giữ/cấp thiết bị nên được quản lý bởi nguồn có thẩm quyền về lịch thiết bị, có thể là aggregate DeviceSchedule hoặc DeviceAllocation tùy quy mô và chiến lược cạnh tranh. Customer và Payment có vòng đời độc lập.
- Với PostgreSQL, có thể cân nhắc **exclusion constraint** trên serialId và khoảng thời gian đối với các bản ghi đang chiếm thiết bị; hoặc giao dịch và khóa nhất quán trên nguồn cấp. Chỉ kiểm tra "không trùng" bằng SELECT rồi INSERT không được bảo vệ cạnh tranh là không đủ.
- Yêu cầu đủ ba thiết bị là điều kiện **liên nhiều quyền giữ**. Nếu cùng một database và các bản ghi được cập nhật trong một transaction với thứ tự khóa ổn định, có thể commit đồng thời. Nếu ở nhiều dịch vụ, cần quy trình đặt giữ từng phần, giới hạn thời gian, bù và chỉ xác nhận hợp đồng khi đã có đủ quyền giữ.
- Payment cần idempotency và xử lý hoàn/hủy cọc khi đặt thiết bị thất bại. Báo cáo có thể dùng JOIN hoặc projection theo kho và thời gian; nhu cầu báo cáo không quyết định aggregate ghi.

**Tự kiểm tra:** nếu một giải pháp tạo aggregate "Warehouse" chứa toàn bộ thiết bị, hợp đồng và lịch sử khách hàng, hãy chỉ rõ bất biến nào thật sự cần mọi dữ liệu đó trong một transaction. Nếu không có, đó là dấu hiệu aggregate bị phóng đại do quan hệ bảng hoặc yêu cầu báo cáo.

## 12. Checklist quyết định ranh giới

- Các command nghiệp vụ đã được ghi theo **mục đích**, điều kiện trước/sau và kết quả lỗi chưa?
- Mỗi bất biến có phạm vi dữ liệu, thời điểm phải đúng và người sở hữu rõ ràng chưa?
- Root nào có quyền nhận command và bảo vệ bất biến? Entity con có bị sửa trực tiếp qua đường ghi khác không?
- Sự nhất quán được giữ bằng **một aggregate**, transaction nhiều root có chủ đích, constraint DB hay một giao thức liên dịch vụ? Tại sao?
- Có nhầm quan hệ FK, nhu cầu JOIN hoặc màn hình hiển thị với quan hệ thuộc aggregate không?
- Quy mô thành viên, tần suất sửa và điểm tranh chấp có phù hợp với root được chọn không?
- Lệnh lặp, lỗi giữa chừng, hết hạn, xung đột ghi và thay đổi sức chứa có được kiểm thử không?
- Dữ liệu lịch sử và quyền sở hữu ngoài ngữ cảnh đã được giải quyết bằng ID, snapshot và hợp đồng thích hợp chưa?
- Mô hình vật lý quan hệ/document/đồ thị/phân tích có phục vụ các bất biến và truy vấn thực tế không?

**Kết luận:** Aggregate được chọn từ **những bất biến phải được bảo vệ trong các thao tác nghiệp vụ**, chứ không được suy ra máy móc từ số bảng, đường khóa ngoại hay nhu cầu JOIN. Khi ranh giới hợp lý, aggregate root kiểm soát thay đổi đủ chặt, giao dịch/constraint thực thi được cam kết, còn các quan hệ bên ngoài được tích hợp có chủ đích. Cách tiếp cận này làm mô hình dữ liệu rõ ràng, dễ kiểm chứng, và có thể tiến hóa khi quy mô hoặc cách triển khai thay đổi.
