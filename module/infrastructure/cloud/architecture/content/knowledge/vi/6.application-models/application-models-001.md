# Kiến trúc nguyên khối có mô đun và điều kiện phù hợp

Một ứng dụng đám mây không nhất thiết phải bắt đầu bằng hàng chục microservice. Nhiều hệ thống có nhu cầu nghiệp vụ phức tạp nhưng vẫn hoạt động tốt dưới dạng **một ứng dụng triển khai thống nhất**, miễn là mã nguồn được tổ chức thành những **mô đun có ranh giới rõ ràng**. Cách tiếp cận đó thường gọi là **kiến trúc nguyên khối có mô đun (modular monolith)**.

Trong chương **Mô hình ứng dụng** của lộ trình **Cloud Architecture**, bài học này trình bày cách thiết kế modular monolith từ yêu cầu nghiệp vụ, triển khai lên hạ tầng đám mây và đánh giá điều kiện phù hợp. Trọng tâm là các đánh đổi giữa **độ tin cậy, bảo mật, khả năng mở rộng, chi phí, khả năng thay đổi và vận hành**, cùng cách xem xét những đánh đổi đó theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Phân biệt monolith thông thường, modular monolith và microservices theo ranh giới mã nguồn, triển khai và dữ liệu.
- Tìm ranh giới mô đun dựa trên năng lực nghiệp vụ, quy tắc bất biến, quyền sở hữu dữ liệu và tần suất thay đổi.
- Thiết kế hợp đồng giao tiếp giữa mô đun mà không để các mô đun truy cập tùy tiện vào cấu trúc nội bộ của nhau.
- Xử lý giao dịch, sự kiện, đồng bộ và thay đổi cơ sở dữ liệu trong một ứng dụng nguyên khối.
- Triển khai modular monolith trên cloud với cân bằng tải, sao lưu, quan sát và mở rộng ngang.
- Nhận biết lúc nào nên tiếp tục duy trì modular monolith và lúc nào cần cân nhắc tách một số mô đun thành dịch vụ độc lập.

## 1. Modular monolith là gì?

**Monolith (ứng dụng nguyên khối)** thường được hiểu là hệ thống có các phần nghiệp vụ được đóng gói và triển khai cùng nhau thành một đơn vị vận hành chính. Đơn vị đó có thể là một ứng dụng Java chạy trên máy ảo, một container image hoặc một nhóm tiến trình cùng thuộc một bản phát hành. Monolith **không nhất thiết** phải chạy trên một máy chủ duy nhất.

**Modular monolith** là monolith trong đó mã nguồn được chia thành các mô đun có **trách nhiệm và giao diện rõ**, hạn chế phụ thuộc chéo, che giấu chi tiết triển khai và có quy tắc kiểm soát kiến trúc. Các mô đun vẫn thường được build và triển khai cùng nhau, giao tiếp chủ yếu trong cùng tiến trình, vì vậy không cần mạng nội bộ cho mọi lời gọi nghiệp vụ.

Ba điều cần phân biệt:

1. **Ranh giới mã nguồn:** mã được chia theo nghiệp vụ, ví dụ Khách hàng, Đặt thuê, Kho, Thanh toán; phần nội bộ chỉ được dùng trong mô đun sở hữu nó.
2. **Ranh giới triển khai:** cả ứng dụng thường có **một phiên bản phát hành**; khi nâng cấp mô đun Đặt thuê, cần triển khai bản ứng dụng có thay đổi đó.
3. **Ranh giới vận hành:** CPU, RAM, tiến trình, môi trường chạy và phần lớn chuỗi khởi động có thể được dùng chung; vấn đề tài nguyên hoặc sự cố tại một mô đun có thể ảnh hưởng toàn ứng dụng.

Một modular monolith có thể có nhiều Maven/Gradle module, nhưng **nhiều thư mục hoặc nhiều project build không tự động tạo ra tính mô đun**. Giá trị nằm ở khả năng kiểm soát sự phụ thuộc và thay đổi phần này mà không phải hiểu, sửa hoặc kiểm thử quá nhiều phần khác.

### 1.1. So sánh các mô hình thường gặp

| Tiêu chí | Monolith thiếu ranh giới | Modular monolith | Microservices |
| --- | --- | --- | --- |
| Đóng gói triển khai | Thường một đơn vị | Thường một đơn vị | Nhiều đơn vị độc lập |
| Ranh giới nghiệp vụ | Dễ chồng lấn | Rõ ràng và được kiểm soát | Rõ ràng ở cả mã nguồn, API và vận hành nếu thiết kế tốt |
| Lời gọi liên chức năng | Gọi trực tiếp, truy cập lẫn nhau | Qua API/hợp đồng trong tiến trình | Qua mạng hoặc thông điệp |
| Giao dịch giữa chức năng | Có thể chung DB nhưng phụ thuộc khó kiểm soát | Thường tận dụng được giao dịch trong một DB; vẫn cần ranh giới sở hữu | Thường phải cân nhắc nhất quán phân tán |
| Triển khai riêng từng phần | Không | Thường không | Có, nếu ranh giới thực sự độc lập |
| Mở rộng riêng từng phần | Khó | Khó ở mức tiến trình nếu chung bản triển khai | Có thể khi từng dịch vụ được thiết kế độc lập |
| Chi phí vận hành phân tán | Thấp hơn | Thấp hơn | Cao hơn do mạng, discovery, monitoring, IAM, tracing, deploy |
| Rủi ro chính | Code trở nên rối và khó thay đổi | Ranh giới bị phá vỡ theo thời gian, một sự cố có thể ảnh hưởng toàn bộ tiến trình | Phức tạp vận hành, độ trễ mạng, lỗi từng phần, quản trị dữ liệu |

Bảng mô tả xu hướng, không phải cam kết cho mọi hệ thống. Một microservice thiết kế kém có thể phụ thuộc chặt hơn cả monolith; một modular monolith đặt các workload nặng chung tiến trình có thể gặp giới hạn tài nguyên sớm.

### 1.2. Kiến trúc tầng không đồng nghĩa với kiến trúc mô đun

Tổ chức mã theo tầng kỹ thuật, chẳng hạn Controller → Service → Repository, vẫn có thể dẫn đến một lớp Service rất lớn gọi qua lại mọi phần. Modular monolith bổ sung một trục tổ chức **theo năng lực nghiệp vụ**; bên trong từng mô đun mới chia tiếp thành API, application, domain và infrastructure nếu cần.

~~~text
Chia theo tầng kỹ thuật toàn ứng dụng:
  controller/
    BookingController, InventoryController, BillingController
  service/
    BookingService, InventoryService, BillingService
  repository/
    BookingRepository, InventoryRepository, BillingRepository

Chia theo mô đun nghiệp vụ:
  booking/
    api/, application/, domain/, infrastructure/
  inventory/
    api/, application/, domain/, infrastructure/
  billing/
    api/, application/, domain/, infrastructure/
~~~

Hai cấu trúc đều có thể hoạt động, nhưng cấu trúc thứ hai giúp nhận biết **ai sở hữu nghiệp vụ và dữ liệu** của từng phần. Nó cũng giúp kiểm tra quy tắc rằng Booking không được tự ý sử dụng repository nội bộ của Inventory.

## 2. Hình dung ranh giới kiến trúc

Ví dụ một nền tảng đặt thuê thiết bị với bốn năng lực: quản lý khách hàng, danh mục/kho, đặt thuê và thanh toán.

~~~mermaid
flowchart TB
    USER["Ứng dụng web / mobile"] --> LB["Load Balancer / API entry"]
    LB --> APP

    subgraph APP["Một đơn vị ứng dụng triển khai: Modular Monolith"]
        API["HTTP API và xác thực đầu vào"]
        CUSTOMER["Customer module"]
        INVENTORY["Inventory module"]
        BOOKING["Booking module"]
        BILLING["Billing module"]
        API --> CUSTOMER
        API --> INVENTORY
        API --> BOOKING
        API --> BILLING
        BOOKING -->|"Contract: kiểm tra và giữ hàng"| INVENTORY
        BOOKING -->|"Contract: lập yêu cầu thanh toán"| BILLING
        BOOKING -->|"Contract: kiểm tra khách hàng"| CUSTOMER
    end

    APP --> DB[("Cơ sở dữ liệu dùng chung ở mức triển khai,\nphân quyền sở hữu bảng theo mô đun")]
    BILLING --> PSP["Đối tác thanh toán bên ngoài"]
~~~

Sơ đồ nhấn mạnh sự khác biệt giữa hai đường ranh giới:

- **Bên ngoài ứng dụng:** client gọi một đơn vị triển khai thông qua load balancer; chỉ cần một lịch triển khai chính và một điểm quan sát ở mức ứng dụng.
- **Bên trong ứng dụng:** mô đun chỉ trao đổi qua hợp đồng công khai; mỗi mô đun bảo vệ quy tắc và dữ liệu của nó, kể cả khi cùng chia sẻ tiến trình và DB.

Đây là sơ đồ logic. Khi triển khai thật, một bản ứng dụng có thể chạy trên **nhiều replica**; các replica cùng dùng cơ sở dữ liệu hoặc dịch vụ lưu trữ phù hợp. Bản chất monolith nằm ở đơn vị mã nguồn và triển khai, không nằm ở số lượng máy chủ.

## 3. Xác định mô đun từ năng lực nghiệp vụ

Bắt đầu bằng câu hỏi **nghiệp vụ nào có trách nhiệm, quy tắc và vòng đời riêng?**, không bắt đầu bằng việc chia đều số lớp Java giữa các nhóm.

Những tín hiệu hữu ích để tách mô đun:

- **Một năng lực nghiệp vụ tương đối độc lập:** tính phí, quản lý tồn kho, quản lý người dùng, xử lý đặt thuê.
- **Quy tắc bất biến cần được bảo vệ tại một nơi:** không cho đặt trùng tài sản trong cùng khoảng thời gian; không thu tiền hai lần cùng giao dịch.
- **Từ vựng và dữ liệu có chủ sở hữu rõ:** trạng thái đơn thuê do Booking quản lý; trạng thái thanh toán do Billing quản lý.
- **Lý do thay đổi khác nhau:** cập nhật quy tắc tính phí không nhất thiết sửa luồng kiểm kê kho.
- **Ranh giới trách nhiệm của nhóm:** một nhóm hiểu và phê duyệt thay đổi đối với những quy tắc cốt lõi của mô đun.

Ý tưởng **bounded context** trong Domain-Driven Design (DDD) là công cụ hữu ích để thảo luận ranh giới ngôn ngữ và mô hình nghiệp vụ. Nhưng không nên mặc định mỗi bảng, mỗi thực thể hoặc mỗi bước của một quy trình là một bounded context; cũng không bắt buộc mỗi bounded context thành một microservice.

### 3.1. Bảng phân chia thử nghiệm

| Mô đun | Trách nhiệm chính | Dữ liệu sở hữu | Hợp đồng cung cấp |
| --- | --- | --- | --- |
| **Customer** | Đăng ký, trạng thái tài khoản, thông tin liên hệ | Hồ sơ khách hàng và quyền sử dụng dịch vụ | Kiểm tra khách hàng hợp lệ; trả thông tin tối thiểu được phép |
| **Inventory** | Tài sản, trạng thái sẵn có, giữ chỗ | Tài sản, khoảng thời gian chiếm dụng, bản ghi giữ chỗ | Kiểm tra và tạo giữ chỗ; hủy giữ chỗ |
| **Booking** | Vòng đời đơn thuê, quy tắc đặt và hủy | Đơn thuê, trạng thái đơn, dấu vết nghiệp vụ | Tạo đơn, xác nhận, hủy; truy vấn trạng thái |
| **Billing** | Giá, hóa đơn, thanh toán, hoàn tiền | Hóa đơn, giao dịch, mã tham chiếu thanh toán | Tạo yêu cầu thanh toán, ghi nhận kết quả, hoàn tiền theo quyền |

Ranh giới này chỉ là phương án ban đầu. Nếu chính sách giá gắn chặt vào từng cấu hình tài sản và thay đổi cùng quy tắc giữ hàng, có thể cần cân nhắc lại ranh giới giữa Inventory và Billing. Hãy kiểm tra bằng **use case và sự kiện nghiệp vụ thực tế** trước khi quyết định.

### 3.2. Chọn mức chi tiết phù hợp

Một mô đun quá lớn gây trở ngại vì nhiều trách nhiệm bị gộp; quá nhiều mô đun nhỏ tạo ra nhiều hợp đồng, phụ thuộc và thay đổi đồng thời mà không đem lại độc lập thực sự.

Các câu hỏi kiểm tra:

1. Có thể mô tả trách nhiệm mô đun trong vài câu rõ ràng không?
2. Những quy tắc quan trọng nhất có được thực thi trong mô đun sở hữu chúng không?
3. Mỗi thay đổi tính năng có thường xuyên phải sửa nhiều mô đun dù nghiệp vụ chỉ thuộc một nơi không?
4. Có giao diện đủ ổn định để mô đun khác sử dụng mà không phải biết cấu trúc DB nội bộ không?
5. Nếu tách mô đun này sau này, phần phụ thuộc dữ liệu và giao dịch nào sẽ làm việc đó khó khăn?

Không cần đạt “độc lập tuyệt đối”. Mục tiêu là **phụ thuộc có chủ đích, dễ hiểu và được kiểm soát**.

## 4. Quy tắc thiết kế ranh giới mô đun

### 4.1. Mô đun công bố hợp đồng, che giấu triển khai

Giữa hai mô đun nên có giao diện với ngữ nghĩa nghiệp vụ: **giữ hàng**, **xác nhận đơn**, **tạo hóa đơn**, thay vì cung cấp toàn bộ repository hoặc entity cho nhau.

Nguyên tắc:

- Phần khác chỉ phụ thuộc vào **API công khai** của mô đun; mã thực thi, repository, cấu trúc bảng và quy tắc nội bộ không được trở thành API ngầm.
- API mô tả thao tác và kết quả nghiệp vụ, tránh trả object nội bộ có thể bị thay đổi ngoài quyền kiểm soát.
- Các tham số và kết quả nên ổn định và đủ nhỏ; dùng định danh và DTO/value object rõ ràng.
- Mô đun sở hữu invariant phải tự kiểm tra invariant đó. Caller không được tự giả định “đã kiểm tra ở API gateway”.
- Các hướng phụ thuộc cần rõ ràng và tránh vòng tròn; không đưa một mô đun “common” lớn chứa toàn bộ domain object làm nơi né tránh ranh giới.

### 4.2. Ví dụ cấu trúc một ứng dụng Java

~~~text
com.example.rental
├── bootstrap/
│   └── RentalApplication.java
├── customer/
│   ├── api/
│   │   └── CustomerQuery.java
│   ├── application/
│   ├── domain/
│   └── infrastructure/
├── inventory/
│   ├── api/
│   │   ├── InventoryReservation.java
│   │   └── ReserveItemCommand.java
│   ├── application/
│   ├── domain/
│   └── infrastructure/
├── booking/
│   ├── api/
│   ├── application/
│   ├── domain/
│   └── infrastructure/
├── billing/
│   ├── api/
│   ├── application/
│   ├── domain/
│   └── infrastructure/
└── platform/
    ├── security/
    ├── database/
    └── observability/
~~~

Tên package chỉ là ví dụ. Có thể sử dụng một project với quy tắc phụ thuộc package hoặc nhiều build module để compiler giúp giới hạn truy cập. **Số project build không quyết định modularity**, nhưng quy tắc build và khả năng kiểm tra tự động có thể giúp ranh giới không bị phá vỡ.

### 4.3. Ví dụ hợp đồng Java

Một interface công khai của mô đun Inventory có thể là:

~~~java
package com.example.rental.inventory.api;

import java.time.Instant;
import java.util.UUID;

// Mô hình minh họa: contract công khai của Inventory
public interface InventoryReservation {
    ReservationResult reserve(
        UUID itemId,
        Instant startsAt,
        Instant endsAt,
        UUID bookingRequestId
    );

    void release(UUID reservationId, UUID bookingRequestId);
}

public record ReservationResult(
    UUID reservationId,
    boolean accepted,
    String reasonCode
) {}
~~~

Trong thực tế Java, các public top-level type thường phải đặt trong **tệp .java riêng** phù hợp tên type. Đoạn trên được gộp để nhìn thấy hợp đồng cùng một chỗ; khi triển khai cần tách file và bổ sung kiểm tra dữ liệu đầu vào.

Booking chỉ biết InventoryReservation và ReservationResult. Booking **không** được import InventoryRepository hoặc đọc trực tiếp bảng lưu tài sản để tự làm chức năng giữ hàng. Quy tắc chống trùng thời gian đặt thuê phải đặt ở Inventory, được hỗ trợ bằng cách khóa/constraint/giao dịch phù hợp để tránh race condition khi hai request đến đồng thời.

Một ví dụ adapter sử dụng interface:

~~~java
package com.example.rental.booking.application;

import com.example.rental.inventory.api.InventoryReservation;
import com.example.rental.inventory.api.ReservationResult;
import java.time.Instant;
import java.util.UUID;

// Lược giản nhằm minh họa hướng phụ thuộc giữa các mô đun
public final class BookingApplicationService {
    private final InventoryReservation inventory;

    public BookingApplicationService(InventoryReservation inventory) {
        this.inventory = inventory;
    }

    public ReservationResult reserveForBooking(
            UUID itemId,
            Instant from,
            Instant to,
            UUID requestId) {
        return inventory.reserve(itemId, from, to, requestId);
    }
}
~~~

Ví dụ chỉ cho thấy **hướng phụ thuộc**. Nó chưa thực thi đầy đủ kiểm tra hợp lệ, transaction, ghi đơn thuê, idempotency hay xử lý trường hợp giữ hàng thất bại.

### 4.4. Phụ thuộc giữa các mô đun cần có quy tắc

Với bất kỳ quan hệ A → B, cần trả lời:

- Vì sao A cần B và có thể thu hẹp số thao tác được gọi không?
- Thao tác có cần cùng transaction để bảo vệ tính đúng đắn không?
- A có phụ thuộc vào bảng hoặc class nội bộ của B không?
- Nếu B thay đổi cấu trúc dữ liệu, A có phải thay đổi theo không?
- Có vòng phụ thuộc A → B → C → A không? Nếu có, liệu ranh giới hoặc cách phối hợp nghiệp vụ đang bị sai?

Dùng sơ đồ phụ thuộc, test kiến trúc hoặc rule ở thời điểm build để ngăn việc truy cập package nội bộ. Ví dụ quy tắc cần đạt: **booking không được phụ thuộc vào inventory.domain và inventory.infrastructure**; các module application khác chỉ có thể dùng inventory.api theo chính sách đã định.

Một bản modular monolith vẫn cần review kiến trúc liên tục. Nếu “gọi tạm repository cho nhanh” trở thành thói quen, ranh giới trên sơ đồ sẽ mất ý nghĩa.

## 5. Quyền sở hữu dữ liệu trong một cơ sở dữ liệu

Một modular monolith thường dùng **một cơ sở dữ liệu vật lý**. Đây là lợi thế vận hành và giao dịch, nhưng cần tránh hiểu “cùng database” thành “mọi mô đun có quyền thao tác mọi bảng”.

Phân biệt:

- **Chia sẻ hệ quản trị dữ liệu:** nhiều mô đun dùng một DB engine, cụm DB, pool kết nối và lịch backup.
- **Chia sẻ cấu trúc dữ liệu tùy tiện:** các mô đun trực tiếp đọc/ghi cùng bảng không có chủ sở hữu và tạo phụ thuộc ngầm.

Cách thứ hai phá vỡ khả năng thay đổi độc lập và gây khó khăn nếu cần tách dịch vụ sau này.

### 5.1. Gán bảng cho mô đun

| Mô đun | Bảng sở hữu ví dụ | Ai được thay đổi? | Cách bên khác truy vấn |
| --- | --- | --- | --- |
| Customer | customer_profile, customer_status | Customer | CustomerQuery hoặc bản chiếu dữ liệu được quản lý |
| Inventory | asset, asset_reservation | Inventory | InventoryAvailability/InventoryReservation |
| Booking | booking, booking_line, booking_history | Booking | BookingQuery |
| Billing | invoice, payment_attempt | Billing | BillingQuery, sự kiện nghiệp vụ |

Tổ chức có thể dùng schema riêng trong cùng database, quy ước tên bảng, quyền DB ở mức phù hợp và kiểm tra migration để làm rõ quyền sở hữu. Một số hệ quản trị có constraint liên bảng hữu ích; việc dùng chúng là đánh đổi giữa tính toàn vẹn dữ liệu và mức độ kết dính. Cần ghi lại chủ đích thay vì dùng mặc định ở mọi nơi.

### 5.2. Truy vấn báo cáo qua nhiều mô đun

Một yêu cầu báo cáo như “doanh thu của từng loại tài sản theo tháng” thường cần dữ liệu Booking, Inventory và Billing. Không nên để một endpoint bất kỳ trở thành nơi viết SQL tùy ý xuyên qua mọi bảng của các mô đun.

Các lựa chọn:

1. **Read model/reporting module:** mô đun báo cáo nhận dữ liệu đã được công bố hoặc sự kiện từ các mô đun nguồn; chấp nhận độ trễ đồng bộ nếu phù hợp.
2. **Query được phê duyệt:** một lớp truy vấn thống nhất với quyền sở hữu và kiểm soát thay đổi rõ; hữu ích khi báo cáo cần tính mới cao và dự án còn nhỏ.
3. **Data warehouse/analytics:** trích xuất có kiểm soát cho tải phân tích lớn; giảm ảnh hưởng của báo cáo lên DB giao dịch.

Mỗi lựa chọn có chi phí và độ trễ khác nhau. Nếu chọn cách đọc trực tiếp bảng nguồn, cần ghi nhận **nợ kết dính dữ liệu** và người phê duyệt trước khi mở rộng thành cơ chế chung.

## 6. Giao dịch, nhất quán và sự kiện giữa mô đun

Một ưu điểm thực tế của modular monolith là các mô đun có thể tham gia **cùng một transaction của một cơ sở dữ liệu** khi hoạt động nghiệp vụ cần tính nguyên tử. Tuy nhiên, điều này không tự xảy ra chỉ vì các lớp chạy trong cùng JVM; transaction phải được cấu hình đúng và các bước thực sự dùng cùng transaction manager/tài nguyên giao dịch.

### 6.1. Khi dùng lời gọi đồng bộ

Gọi trực tiếp qua interface trong tiến trình phù hợp khi:

- Caller cần câu trả lời ngay để hoàn thành use case.
- Có một invariant xuyên mô đun mà hệ thống phải kiểm tra trước khi commit.
- Không có chuỗi phụ thuộc quá dài làm tăng thời gian giữ lock và rủi ro lỗi dây chuyền.

Ví dụ: Booking yêu cầu Inventory giữ tài sản và chỉ tạo đơn ở trạng thái “đã giữ” nếu Inventory chấp nhận. Nếu cùng database và transaction manager, có thể dùng một giao dịch để đảm bảo cả bản ghi giữ chỗ và trạng thái đơn thuê được commit hoặc rollback cùng nhau.

Nhưng transaction lớn, gọi nhiều mô đun, khóa nhiều bảng và xử lý lâu có thể gây **lock contention**, deadlock, tăng thời gian phản hồi và khó mở rộng. Hãy đặt **ranh giới giao dịch theo invariant nghiệp vụ**, tránh mặc định bọc toàn bộ luồng dài trong một transaction.

### 6.2. Khi dùng sự kiện nội bộ

Sự kiện phù hợp khi một mô đun đã hoàn thành việc riêng và những mô đun khác cần biết để thực hiện phần việc **không bắt buộc xảy ra cùng transaction**.

Ví dụ:

~~~text
Booking xác nhận đơn
    |
    +--> Cập nhật dữ liệu do Booking sở hữu
    |
    +--> Phát sự kiện BookingConfirmed
              |
              +--> Notification chuẩn bị gửi thông báo
              +--> Reporting cập nhật số liệu
              +--> Loyalty cập nhật điểm thưởng (nếu có)
~~~

Sự kiện giảm phụ thuộc trực tiếp giữa bên phát và bên nhận, nhưng mang theo vấn đề **thứ tự, trùng sự kiện, giao nhận thất bại, xử lý lại và khả năng quan sát**. Không nên thêm hàng đợi phân tán chỉ vì thấy microservices sử dụng. Trong một tiến trình, cơ chế event nội bộ có thể đơn giản hơn; khi nghiệp vụ cần bảo đảm không mất sự kiện sau khi DB commit, phải xem xét cơ chế lưu bền vững.

### 6.3. Tại sao chỉ phát sự kiện trong bộ nhớ có thể không đủ?

Giả sử ứng dụng ghi “đơn đã xác nhận” vào DB và sau đó đưa sự kiện vào một executor trong JVM. Nếu JVM dừng ở giữa, đơn có thể đã được commit nhưng sự kiện chưa kịp xử lý. Đối với một thông báo không quan trọng có thể chấp nhận điều đó; với cập nhật nghĩa vụ tài chính, cần cơ chế đáng tin cậy hơn.

**Transactional outbox** là một lựa chọn: ghi bản ghi nghiệp vụ và bản ghi sự kiện vào một transaction DB, sau đó worker đọc outbox để chuyển đến nơi nhận; worker phải retry và xử lý idempotent. Outbox làm tăng sự phức tạp, vì vậy chỉ nên áp dụng nơi có nhu cầu thực tế.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant B as Booking module
    participant DB as Database
    participant W as Outbox worker
    participant N as Notification/Consumer

    C->>B: Xác nhận đặt thuê
    B->>DB: Transaction: update booking + insert outbox
    DB-->>B: Commit
    B-->>C: Đã xác nhận
    W->>DB: Đọc outbox chưa xử lý
    W->>N: Gửi BookingConfirmed(eventId)
    N-->>W: Xác nhận xử lý
    W->>DB: Đánh dấu outbox đã gửi
~~~

Giữa lúc N xử lý thành công và W ghi nhận trạng thái, worker có thể lỗi; lần retry sau sẽ gửi lại. Vì thế, consumer vẫn cần khóa chống trùng như eventId hoặc khóa nghiệp vụ, thay vì mặc định “exactly once” ở toàn bộ luồng.

### 6.4. Tương tác với dịch vụ ngoài ứng dụng

Lời gọi HTTP tới đối tác thanh toán, email hoặc SaaS **không** nằm trong cùng giao dịch ACID của database ứng dụng. Không nên giữ transaction DB dài trong khi chờ bên ngoài phản hồi nếu có thể tránh. Thay vào đó, dùng trạng thái nghiệp vụ rõ (PENDING_PAYMENT, CONFIRMED, FAILED, CANCELLED), idempotency key, retry có giới hạn và quy trình bù trừ hoặc hòa giải khi cần.

Điểm khác biệt với microservices là modular monolith có thể giữ đơn giản **những phần thực sự thuộc cùng transaction nội bộ**; nhưng mọi biên giới ra dịch vụ bên ngoài vẫn đòi hỏi thiết kế lỗi phân tán.

## 7. Cách modular monolith chạy trên cloud

Modular monolith **không đồng nghĩa với một máy duy nhất**. Một bản artifact có thể chạy trên nhiều VM, container hoặc pod. Load balancer phân phối request tới các replica; dữ liệu bền vững được đặt trong managed database và object storage phù hợp.

~~~mermaid
flowchart TB
    CLIENT["Người dùng / ứng dụng khách"] --> LB["Load Balancer"]
    LB --> A1["Replica 1: toàn bộ modular monolith"]
    LB --> A2["Replica 2: toàn bộ modular monolith"]
    LB --> A3["Replica N: toàn bộ modular monolith"]
    A1 --> DB[("Managed relational database")]
    A2 --> DB
    A3 --> DB
    A1 --> CACHE[("Cache / session storage nếu cần")]
    A2 --> CACHE
    A3 --> CACHE
    A1 --> OBJ[("Object storage")]
    A2 --> OBJ
    A3 --> OBJ
    A1 --> OBS["Logs / metrics / traces"]
    A2 --> OBS
    A3 --> OBS
~~~

Để chạy nhiều replica an toàn, cần:

- **Không phụ thuộc vào RAM cục bộ của một replica cho trạng thái phiên quan trọng.** Dùng token, storage phiên phù hợp hoặc mô hình trạng thái được chia sẻ theo yêu cầu.
- **Không ghi dữ liệu nghiệp vụ quan trọng chỉ vào filesystem của container.** Dùng DB/object storage; hiểu rõ ổ đĩa tạm và chính sách backup.
- **Quản lý migration schema** để phiên bản cũ/mới có thể tồn tại cùng nhau trong khoảng rollout nếu cần.
- **Kiểm tra tác vụ nền:** một scheduler chạy trong cả ba replica có thể thực thi ba lần nếu không có cơ chế phân quyền, khóa hoặc work-queue đúng.
- **Giới hạn pool kết nối:** tăng số replica cũng tăng tổng số connection; có thể làm nghẽn DB.
- **Đặt readiness và liveness hợp lý:** lỗi phụ thuộc không cần thiết trong health check có thể làm toàn bộ replica bị loại khỏi cân bằng tải.

### 7.1. Mở rộng ngang và giới hạn thực tế

Ví dụ một ứng dụng có 4 mô đun, trong đó Booking chiếm 70% CPU còn Catalog chỉ chiếm 5%. Khi scale từ 2 lên 6 replica, hệ thống vẫn chạy **toàn bộ các mô đun trên cả 6 replica**. Cách này thường đơn giản và vẫn hiệu quả khi lưu lượng các phần tăng tương đối cùng nhau.

Tuy nhiên, nếu có tác vụ tạo báo cáo dùng nhiều RAM hoặc chạy AI inference làm bão hòa CPU, việc scale toàn bộ monolith có thể tốn kém và ảnh hưởng latency của chức năng khác. Trước khi quyết định tách microservice, có thể xem xét:

1. Đưa tác vụ nặng sang **job/worker** riêng trong cùng codebase nhưng có **đơn vị triển khai riêng** nếu tổ chức chấp nhận mô hình hybrid; lúc đó cần mô tả rõ kiến trúc đã mở rộng khỏi một đơn vị triển khai thuần túy.
2. Tối ưu truy vấn, cache và hàng đợi để tách tải đồng bộ khỏi tác vụ batch.
3. Đặt resource limit và concurrency limit theo luồng xử lý; giám sát mức ảnh hưởng chéo.
4. Chỉ tách thành dịch vụ độc lập khi lợi ích vận hành/scale đủ lớn so với chi phí phân tán.

**Điểm cốt lõi:** nhân bản nguyên khối có thể tăng throughput nhưng không xóa được giới hạn DB, dữ liệu nóng hoặc lock contention. Cần đo nút thắt trước khi nhân thêm replica.

### 7.2. Độ tin cậy khi có nhiều replica

Chạy nhiều replica ở các availability zone phù hợp giúp giảm rủi ro một process hoặc một zone bị lỗi. Tuy nhiên, **một lỗi logic trong bản phát hành** có thể ảnh hưởng tất cả replica; **DB dùng chung** có thể là điểm lỗi tập trung nếu không được thiết kế HA/backup đúng.

Các câu hỏi phải đo:

- Khi một replica dừng đột ngột, request dở dang được retry thế nào và có xảy ra ghi trùng không?
- Khi DB chậm hoặc mất kết nối, mô đun nào lỗi, có circuit breaker/timeouts đối với phụ thuộc ngoài tiến trình không?
- Khi phát hành có lỗi, có thể rollback ứng dụng và xử lý tình huống schema đã migrate không?
- RTO/RPO của DB, object storage và queue là bao nhiêu? Thử khôi phục dữ liệu đã được thực hiện chưa?
- Khi tăng replica, năng lực database có theo kịp không?

Một modular monolith có thể đạt độ sẵn sàng cao khi triển khai tốt. Nhưng do chung tiến trình, **fault isolation** kém hơn mô hình có các dịch vụ thực sự độc lập; không nên nói mỗi mô đun có SLA độc lập nếu hạ tầng chưa bảo đảm được điều đó.

## 8. Bảo mật và tuân thủ theo ranh giới nghiệp vụ

Phân chia thành mô đun giúp dễ quản lý trách nhiệm và chính sách nhưng **ranh giới package trong JVM không phải ranh giới bảo mật tương đương tiến trình hoặc network**.

Ví dụ Billing có thể chỉ cho phép vai trò Kế toán hoàn tiền; Booking có thể được yêu cầu “tạo yêu cầu thanh toán” nhưng không được gọi tùy tiện “hoàn tiền”. Nếu mọi mô đun đều chạy dưới cùng danh tính DB, không thể trông đợi DB tự phát hiện câu lệnh truy cập sai tầng nghiệp vụ; cần kiểm soát tại application layer và có thể dùng thêm DB permissions theo thiết kế.

Các nguyên tắc:

- **Authentication** xác định ai/cái gì gọi hệ thống; **authorization** kiểm tra đúng quyền cho thao tác và đối tượng dữ liệu.
- Mỗi mô đun phải xác thực quyền và invariant tại ranh giới hành vi quan trọng; không dựa hoàn toàn vào việc UI ẩn nút thao tác.
- Các endpoint nghiệp vụ phải kiểm tra giới hạn tenant và quyền đối với bản ghi, tránh lỗi truy cập dữ liệu giữa khách hàng.
- Cần tách thông tin nhạy cảm khỏi log; chỉ ghi dấu vết cần thiết cho kiểm toán với retention và quyền phù hợp.
- Quản lý secrets qua cơ chế bảo mật phù hợp, không đặt vào code hoặc artifact; mã hóa dữ liệu khi truyền và khi lưu theo phân loại.
- Khi cùng database, nên phân quyền truy vấn, người vận hành và công cụ migration theo trách nhiệm, không cấp quyền quản trị rộng không cần thiết.

**Tuân thủ** phụ thuộc loại dữ liệu, địa bàn, ngành và hợp đồng. Dù dùng một database, vẫn cần danh mục dữ liệu, nơi lưu bản chính/bản sao/log, lịch lưu giữ và quy trình xóa. Việc tách package không đủ để chứng minh đáp ứng một yêu cầu pháp lý.

## 9. Khả năng quan sát: nhìn được cả toàn hệ thống và từng mô đun

Đặc tính “một tiến trình” giúp tracing nội bộ đơn giản hơn lời gọi qua mạng, nhưng có thể che giấu mô đun nào đang tiêu thụ tài nguyên hoặc làm tăng lỗi. Hệ thống cần quan sát theo **module, use case, dependency và dữ liệu**.

Các tín hiệu quan trọng:

| Phạm vi | Chỉ số hoặc bằng chứng |
| --- | --- |
| Toàn ứng dụng | Throughput, p95/p99 latency, tỷ lệ lỗi, uptime, memory, GC, CPU |
| Từng use case | Thời gian tạo đơn, tỷ lệ đặt thành công, tỷ lệ hủy và xử lý thanh toán |
| Từng mô đun | Thời gian thực thi, lỗi nghiệp vụ, số request, pool/queue liên quan |
| Cơ sở dữ liệu | Query latency, slow queries, lock wait, connection pool, replication lag |
| Tác vụ nền | Độ dài hàng đợi, retry, số lượng job lỗi hoặc chạy trùng |
| Sự kiện/outbox | Tuổi bản ghi chưa gửi, tỷ lệ gửi thành công, số event trùng và xử lý chậm |
| Thay đổi bản phát hành | Phiên bản build, thời gian deploy, lỗi sau deploy, rollback |

Đặt trường **moduleName**, **operation**, **correlationId/traceId** và **outcome** phù hợp trong log/trace; tránh lộ PII. Một request đi từ Booking qua Inventory và Billing cần theo dõi được ranh giới mô đun. Nên đặt SLO theo nghiệp vụ, chẳng hạn tỷ lệ tạo đơn thành công và p95 thời gian tạo đơn, thay vì chỉ đo “JVM đang chạy”.

## 10. Tổ chức kiểm thử và bảo vệ kiến trúc

Một modular monolith thành công khi ranh giới mô đun được duy trì qua nhiều lần thay đổi và nhiều người tham gia, không chỉ trong sơ đồ lúc khởi tạo.

### 10.1. Những lớp kiểm chứng cần thiết

- **Unit test theo mô đun:** kiểm tra invariant và hành vi nghiệp vụ trong một mô đun.
- **Contract test nội bộ:** kiểm tra giao diện và các tình huống lỗi mà mô đun khác phụ thuộc vào.
- **Integration test:** kiểm tra repository, transaction và dữ liệu với DB có hành vi sát môi trường thực.
- **End-to-end test trọng yếu:** tạo đơn, giữ hàng, thanh toán, hủy/hoàn tiền với xử lý lỗi.
- **Architecture test:** không cho module khác truy cập package nội bộ, phát hiện vòng phụ thuộc, phát hiện truy cập repository xuyên mô đun.
- **Load/failure test:** kiểm chứng p95/p99, khả năng tăng replica, nghẽn DB và hành vi khi đối tác lỗi.

Không cần viết test đơn giản chỉ để chứng minh một getter trả lại một field. Thử đúng các chỗ có nguy cơ làm sai nghiệp vụ, phá ranh giới hoặc gây sự cố vận hành.

### 10.2. Kiểm tra dependency rule

Một quy tắc ở mức khái niệm:

~~~text
Allowed:
  booking.application  -> inventory.api
  booking.application  -> customer.api
  booking.application  -> billing.api

Forbidden:
  booking.*            -> inventory.infrastructure
  booking.*            -> inventory.domain
  billing.*            -> booking.infrastructure
  inventory.*          -> booking.infrastructure

No cyclic module dependencies.
~~~

Có thể dùng ArchUnit, Java module rules, build dependency constraints hoặc công cụ tương đương để tự động hóa những quy tắc này. Cấu hình cụ thể tùy cấu trúc project; cần kiểm chứng hướng phụ thuộc thực tế thay vì chỉ kiểm tra tên thư mục.

### 10.3. Cấu trúc CI/CD

Một pipeline điển hình:

~~~mermaid
flowchart LR
    C["Commit / Pull Request"] --> L["Compile, lint và kiến trúc"]
    L --> T["Unit + integration + contract"]
    T --> B["Build một artifact ứng dụng"]
    B --> SEC["Quét cấu hình, thư viện, container"]
    SEC --> ST["Deploy staging"]
    ST --> E2E["E2E + smoke + kiểm tra migration"]
    E2E --> P["Canary/rolling deploy production"]
    P --> O["Theo dõi SLO, rollback nếu cần"]
~~~

Vì nhiều mô đun cùng một bản phát hành, cần đặc biệt coi trọng **tác động của thay đổi schema, cấu hình và khả năng rollback**. Triển khai nhiều replica theo đợt thường khiến phiên bản cũ/mới cùng dùng DB một lúc; nên dùng thay đổi schema tương thích ngược trong giai đoạn chuyển tiếp.

## 11. Quy tắc thay đổi cơ sở dữ liệu an toàn

Giả sử Billing cần đổi tên cột biểu diễn trạng thái thanh toán. Nếu đổi ngay trong một migration và deploy code mới, bản cũ còn chạy có thể lỗi.

Một chu trình **expand–migrate–contract**:

1. **Expand:** thêm cột/cấu trúc mới trong khi cột cũ vẫn hợp lệ; phát hành code có thể đọc được trạng thái cũ và mới theo kế hoạch.
2. **Migrate:** chuyển dữ liệu hiện có và hành vi ghi theo từng giai đoạn; kiểm tra tính nhất quán, giám sát lỗi và các job cũ.
3. **Contract:** khi toàn bộ tiến trình dùng cấu trúc mới và rollback window đã đóng, mới xóa phần cấu trúc cũ.

Chu trình giúp giảm rủi ro khi chạy nhiều replica nhưng **không bảo đảm luôn có thể rollback mọi thay đổi dữ liệu**. Với dữ liệu cần bảo toàn, phải có kế hoạch migration một chiều, backup và kịch bản khôi phục được thử trước.

Quy tắc quyền sở hữu migration: **mô đun nào sở hữu dữ liệu thì mô đun đó chịu trách nhiệm thay đổi schema**, ngay cả khi tất cả migration được đóng gói trong cùng một deployment pipeline.

## 12. Khi nào modular monolith phù hợp?

Thay vì đặt câu hỏi “microservices có hiện đại hơn không?”, hãy kiểm tra yêu cầu kinh doanh và khả năng vận hành.

### 12.1. Những điều kiện thường nghiêng về modular monolith

1. **Miền nghiệp vụ còn thay đổi và cần học nhanh.** Ranh giới thực tế chưa ổn định; một ứng dụng thống nhất giúp refactor hợp đồng và dữ liệu dễ hơn.
2. **Một nhóm hoặc vài nhóm cùng làm sản phẩm.** Chưa có nhu cầu triển khai và vận hành độc lập với tần suất cao.
3. **Các use case cần giao dịch mạnh giữa nhiều năng lực.** Có thể tận dụng một DB và transaction manager nếu kiểm soát tốt ranh giới.
4. **Lưu lượng có thể đáp ứng bằng tối ưu ứng dụng, DB và scale nguyên bản ứng dụng.** Không có yêu cầu khác biệt cực lớn giữa các phần.
5. **Ngân sách vận hành có hạn.** Chưa cần gánh chi phí service discovery, mạng nội bộ, tracing phân tán, service mesh hoặc nhiều pipeline độc lập.
6. **Yêu cầu độ tin cậy không bắt buộc cô lập lỗi nghiêm ngặt theo từng năng lực.** Toàn ứng dụng có thể chung vòng đời triển khai và phạm vi ảnh hưởng khi lỗi.
7. **Nhóm có kỷ luật giữ ranh giới mô đun.** Có chủ sở hữu, code review, architecture test và quy tắc dependency thực thi.

Modular monolith cũng phù hợp với sản phẩm đã trưởng thành nếu nhu cầu vận hành và tốc độ thay đổi vẫn thống nhất. Đây **không chỉ là bước trung gian bắt buộc** trước microservices.

### 12.2. Dấu hiệu cần cân nhắc tách dịch vụ độc lập

- Một phần hệ thống cần **scale với hệ số lớn** so với các phần còn lại, làm chi phí scale cả monolith tăng không hợp lý.
- Các nhóm cần phát hành độc lập nhưng lịch deploy chung liên tục tạo xung đột hoặc trễ giao hàng đo được.
- Một tác vụ có rủi ro sự cố cao cần **cô lập tiến trình/tài nguyên** hoặc mục tiêu khả dụng khác biệt.
- Có nhu cầu pháp lý, dữ liệu hoặc mạng phải cách ly ở mức cơ sở hạ tầng và danh tính độc lập.
- Một phần phải dùng runtime, công nghệ hoặc vòng đời tài nguyên khác biệt đáng kể.
- Một mô đun đã có API và dữ liệu đủ tách biệt để chi phí thay đổi thấp hơn lợi ích độc lập.

Những dấu hiệu này là **tín hiệu đánh giá**, không phải điều kiện tự động dẫn đến microservices. Trước khi tách, cần đo: tỷ lệ CPU/RAM từng phần, ảnh hưởng của lỗi, tần suất deploy và số công việc bị trì hoãn vì deploy chung, chi phí infra và nhân sự vận hành.

### 12.3. Những lý do chưa đủ để tách microservices

- Ứng dụng có “rất nhiều dòng code” nhưng chưa đo được vấn đề về cấu trúc hoặc vận hành.
- Có nhiều nhóm phát triển, trong khi cách cộng tác và quyền sở hữu vẫn có thể được giải quyết bằng mô đun.
- Một endpoint chậm do query thiếu index, chưa được profile và tối ưu.
- Muốn dùng Kubernetes hoặc container; modular monolith vẫn triển khai trên container/Kubernetes được.
- Muốn dùng event-driven; modular monolith vẫn có sự kiện nội bộ và outbox khi cần.
- Muốn hệ thống chịu lỗi; bản nguyên khối nhiều replica, đa AZ và DB HA vẫn có thể đáp ứng nhiều mục tiêu khả dụng.

## 13. Bảng quyết định mô hình ứng dụng

| Câu hỏi | Modular monolith thường phù hợp khi… | Nên đánh giá tách dịch vụ khi… |
| --- | --- | --- |
| Các mô đun có cần release độc lập? | Có thể phát hành cùng nhịp | Lịch release khác nhau thường xuyên làm chậm thay đổi |
| Có cần scale riêng từng năng lực? | Tải tương đối đồng đều hoặc tổng tải trong giới hạn | Tải/chi phí giữa các phần chênh lệch lớn và kéo dài |
| Độ phức tạp dữ liệu và transaction? | Nhiều invariant cần transaction cục bộ | Dữ liệu đã độc lập, giao tiếp bất đồng bộ chấp nhận được |
| Khả năng vận hành của đội? | Nhóm nhỏ, chưa có nền tảng vận hành dịch vụ phân tán | Có SRE/platform, observability và tự động hóa phù hợp |
| Cô lập lỗi/tài nguyên? | Lỗi một phần có thể xử lý trong một tiến trình | Cần ranh giới sự cố, tài nguyên hoặc tuân thủ riêng |
| Độ ổn định ranh giới nghiệp vụ? | Đang khám phá, cần refactor nhanh | Đã tương đối ổn định và có hợp đồng đủ rõ |
| Chi phí tổng thể? | Chi phí phát triển và vận hành phân tán không xứng đáng | Lợi ích độc lập được chứng minh lớn hơn chi phí bổ sung |

**Quy tắc đánh giá:** dùng yêu cầu có thể đo thay cho số lượng team, số người dùng hoặc số dòng code như một ngưỡng tuyệt đối. Không có con số “trên X request/giây bắt buộc dùng microservices”; kết quả phụ thuộc công việc xử lý, DB, cache, tài nguyên và mục tiêu SLO.

## 14. Ví dụ thực hành: nền tảng đặt thuê thiết bị

Giả sử một sản phẩm cho phép khách xem thiết bị, kiểm tra lịch trống, tạo đơn thuê, thanh toán và nhận thông báo. Đây là **tình huống minh họa** để chọn mô hình, không phải mô tả hệ thống của một doanh nghiệp cụ thể.

### 14.1. Yêu cầu giả định

| Yêu cầu | Giả định thiết kế | Tác động |
| --- | --- | --- |
| Phát triển | Hai nhóm cùng xây dựng và phát hành hàng tuần | Một pipeline phát hành chung vẫn chấp nhận được |
| Lưu lượng | Tải chủ yếu đến từ tra cứu danh mục và tìm lịch trống | Cần tách đường đọc, cache và tối ưu query |
| Nghiệp vụ | Không được cho thuê trùng một thiết bị trong cùng khoảng thời gian | Cần invariant và xử lý race condition tại Inventory |
| Thanh toán | Thanh toán qua nhà cung cấp bên ngoài | Cần trạng thái, idempotency, retry và reconciliation |
| Khả dụng | Mục tiêu được định nghĩa qua SLO nghiệp vụ và lịch bảo trì | Cần replica, health check, database HA và kiểm thử |
| Dữ liệu | Có thông tin cá nhân và hồ sơ đơn thuê | Cần phân quyền, mã hóa, retention, log phù hợp |

Yêu cầu còn thiếu như RTO/RPO, mức tải thực tế, khu vực dữ liệu và giới hạn chi phí phải được thu thập trước khi chốt phương án triển khai cuối cùng.

### 14.2. Phương án modular monolith ban đầu

- **Catalog:** công bố danh mục, tra cứu và lọc; có thể sử dụng cache cho dữ liệu đọc nhiều.
- **Inventory:** quyết định khả dụng và giữ chỗ theo thời gian; bảo vệ chống giữ trùng khi có concurrency.
- **Booking:** điều phối vòng đời đơn thuê; ghi trạng thái có ý nghĩa nghiệp vụ.
- **Billing:** quản lý hóa đơn và kết quả thanh toán; tích hợp đối tác bằng idempotency key.
- **Customer:** cung cấp trạng thái hợp lệ và thông tin khách được phép dùng.
- **Notification:** tiêu thụ sự kiện nghiệp vụ sau khi commit để gửi email/SMS, không làm chậm giao dịch cốt lõi.

Cả sáu mô đun có thể build thành một artifact và chạy nhiều replica phía sau load balancer. Database dùng chung ở mức hạ tầng nhưng bảng có **mô đun sở hữu**. Tác vụ nền dùng hàng đợi/outbox và checkpoint phù hợp để không chạy trùng khi tăng replica.

### 14.3. Luồng tạo đơn cần kiểm soát

~~~mermaid
sequenceDiagram
    participant U as Khách hàng
    participant B as Booking
    participant C as Customer
    participant I as Inventory
    participant DB as Database
    participant P as Payment provider
    participant N as Notification

    U->>B: Tạo yêu cầu thuê(requestId)
    B->>C: Kiểm tra tài khoản hợp lệ
    C-->>B: Kết quả
    B->>I: Giữ tài sản / khoảng thời gian
    I->>DB: Kiểm tra và tạo giữ chỗ trong transaction phù hợp
    DB-->>I: Kết quả
    I-->>B: reservationId hoặc từ chối
    B->>DB: Lưu đơn PENDING_PAYMENT
    DB-->>B: Thành công
    B-->>U: Mã đơn + trạng thái cần thanh toán
    U->>P: Thanh toán theo luồng đối tác
    P-->>B: Callback/webhook kết quả
    B->>DB: Xác minh, ghi trạng thái idempotent
    B-->>N: Sự kiện sau commit / qua outbox
~~~

Sơ đồ cố ý lược giản cách giữ chỗ và lưu đơn. Nếu hệ thống yêu cầu việc giữ chỗ và tạo đơn phải thành công hoặc thất bại cùng nhau, chúng phải được đặt trong **một ranh giới transaction đúng** và được kiểm thử. Đồng thời phải có thời hạn giữ chỗ, quy tắc trả hàng khi quá hạn/thanh toán thất bại và cách xử lý callback đến chậm hoặc đến trùng.

### 14.4. Điều gì xảy ra khi tải tăng?

Giả sử trong đợt khuyến mãi, request tìm kiếm danh mục tăng mạnh và DB trở thành nút thắt. Không nên mặc định “phải tách Catalog thành microservice”.

Trình tự đánh giá hợp lý:

1. Xác định p95/p99 và truy vấn chậm; phân biệt CPU ứng dụng, DB, I/O và lock contention.
2. Tối ưu chỉ mục, phân trang, cache và giới hạn request; xác minh cache invalidation.
3. Scale replica ứng dụng và pool kết nối trong giới hạn DB; kiểm tra tác động tới Booking.
4. Khi đã có dữ liệu chứng minh Catalog có vòng đời tải khác biệt dài hạn, đánh giá tách khả năng đọc hoặc đưa một phần tìm kiếm ra dịch vụ riêng.
5. Tính thêm chi phí dữ liệu đồng bộ, cache invalidation, deploy, observability và quyền truy cập trước khi chốt.

Nhờ ranh giới mô đun từ đầu, Catalog có thể được tách có kiểm soát nếu thật sự cần, nhưng tách service **không tự chữa** một thiết kế dữ liệu hay thuật toán truy vấn kém.

### 14.5. Khi lỗi thanh toán ảnh hưởng cả ứng dụng

Nếu đối tác thanh toán chậm, các lời gọi đồng bộ giữ thread quá lâu có thể ảnh hưởng Booking và các mô đun khác trong cùng tiến trình. Biện pháp trước mắt là timeout, bulkhead/concurrency limit, retry phù hợp và tách phần chờ bên ngoài khỏi transaction DB. Nếu sau khi áp dụng vẫn có yêu cầu cô lập cao, có thể cân nhắc tách Billing hoặc adapter thanh toán thành đơn vị triển khai độc lập. Quyết định cần dựa trên **tần suất và phạm vi sự cố thực tế**.

## 15. Lộ trình chuyển từ modular monolith sang dịch vụ khi cần

Một kiến trúc modular monolith tốt tạo ra khả năng tách **có lựa chọn**; mục tiêu không phải biến mọi mô đun thành microservice.

Quy trình gợi ý:

1. **Đo điểm đau:** xác định lý do tách và tiêu chí thành công, ví dụ giảm chi phí scale hoặc giảm số lần lỗi thanh toán ảnh hưởng tạo đơn.
2. **Chọn mô đun có ranh giới ổn:** hợp đồng được sử dụng rõ, ít phụ thuộc vào transaction và truy vấn dữ liệu xuyên mô đun.
3. **Loại phụ thuộc nội bộ:** chuyển caller dùng API hợp đồng, thu hẹp shared library và các truy vấn SQL chéo.
4. **Tách quyền sở hữu dữ liệu:** mô đun mới là bên duy nhất ghi dữ liệu thuộc quyền; thiết kế cơ chế truy vấn, sao chép và chuyển dữ liệu an toàn.
5. **Thêm biên giới mạng:** chuẩn hóa authn/authz, timeout, retry, idempotency, tracing và quản lý phiên bản API.
6. **Di chuyển lưu lượng theo giai đoạn:** thử nghiệm, canary, quan sát và có phương án quay lại nếu gặp lỗi.
7. **Đánh giá giao dịch:** thay transaction cục bộ trước đây bằng trạng thái nghiệp vụ, outbox và cơ chế nhất quán phù hợp nếu cần.
8. **Xóa đường cũ:** khi dữ liệu và lưu lượng đã chuyển hoàn tất, dọn những điểm truy cập chéo không còn dùng.

Một dạng **strangler pattern** có thể được dùng: đặt giao diện ổn định trước hệ thống cũ, chuyển từng năng lực sang dịch vụ mới và dần tắt đường thực thi cũ. Nhưng nếu dữ liệu bị chia đôi không có nguồn có thẩm quyền, việc tách sẽ gây lỗi khó phục hồi.

### 15.1. Điều thay đổi sau khi tách

Trước đó, Booking gọi InventoryReservation như một method trong tiến trình. Sau khi tách Inventory:

- Mỗi lời gọi có **độ trễ mạng** và có thể timeout trong khi phía nhận đã xử lý thành công.
- Hai phía có thể triển khai **khác phiên bản** trong thời gian dài.
- Giao dịch chung một DB có thể không còn khả thi hoặc không mong muốn.
- Cần quyền dịch vụ–dịch vụ và chính sách dữ liệu riêng.
- Cần quan sát được lỗi từng phần và trạng thái eventual consistency.

Vì vậy việc có interface nội bộ tốt **giúp giảm phụ thuộc**, nhưng không biến quá trình tách thành thao tác đổi transport đơn giản.

## 16. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Chia thư mục theo nghiệp vụ nhưng mọi class đều public | Các phần import tùy tiện, ranh giới chỉ có trên sơ đồ | Che giấu implementation, kiểm tra dependency ở build |
| Một Shared/Common module chứa toàn bộ entity và service | Mọi thay đổi lan khắp ứng dụng | Chỉ chia sẻ giá trị nền tảng thật sự chung; để domain model có chủ sở hữu |
| Booking đọc/ghi trực tiếp bảng Inventory | Phá invariant và khó thay đổi mô đun | Truy cập qua hợp đồng và để Inventory thực thi quy tắc |
| Mọi mô đun gọi vòng tròn nhau | Dễ tạo coupling, khó kiểm thử và tách dịch vụ | Xem lại ranh giới, tách orchestration và hợp đồng rõ |
| Dùng event cho mọi thao tác | Khó hiểu nhất quán và debug dù chỉ cần trả kết quả ngay | Dùng gọi đồng bộ cho thao tác cần kết quả; event cho công việc sau commit |
| Phát event chỉ trong RAM nhưng đòi hỏi không mất | Crash sau commit gây thất lạc tác vụ | Dùng outbox hoặc cơ chế bền vững khi nghiệp vụ yêu cầu |
| Tạo transaction rất dài, gọi HTTP bên ngoài bên trong | Lock lâu, timeout, tạo lỗi dây chuyền | Thiết kế trạng thái và transaction ngắn phù hợp |
| Cho nhiều replica chạy cùng scheduler không kiểm soát | Job bị thực thi nhiều lần | Dùng leader election/lease/queue phù hợp, xử lý idempotent |
| Nghĩ monolith không thể scale | Thiếu tối ưu và thiết kế HA | Scale replica, tối ưu DB/cache, đo nút thắt |
| Nghĩ modular monolith có cách ly lỗi như microservices | Một lỗi RAM/GC ảnh hưởng toàn ứng dụng | Đo blast radius, resource limit và tách khi thực sự cần |
| Tách microservices theo từng bảng | Nhiều lời gọi mạng, phụ thuộc vòng, dữ liệu khó nhất quán | Tách theo năng lực nghiệp vụ và quyền sở hữu dữ liệu |
| Bỏ qua migration/rollback của DB | Deploy mới làm hỏng bản cũ và không thể quay lại | Thay đổi schema có giai đoạn, backup, test phục hồi |

## 17. Ghi Architecture Decision Record (ADR)

Khi chọn mô hình, lưu quyết định và điều kiện đánh giá lại. Đây là ví dụ giả định:

~~~yaml
decision_id: ADR-001
title: Use a modular monolith for the initial rental platform
status: accepted
context:
  teams: 2
  release_cadence: weekly
  business_domains:
    - customer
    - inventory
    - booking
    - billing
  transactional_consistency: required_for_booking_and_inventory
decision:
  application_model: modular_monolith
  deployment_unit: single_application_artifact
  data_platform: shared_relational_database_with_module_ownership
  internal_communication: explicit_module_contracts
  external_side_effects: durable_events_where_required
constraints:
  - no_cross_module_repository_access
  - no_cyclic_module_dependencies
  - mandatory_architecture_tests
  - independently_owned_data_migrations
consequences:
  benefits:
    - simple_initial_deployment
    - local_transactions_where_appropriate
    - reduced_distributed_operations
  limitations:
    - shared_release_cycle
    - shared_process_failure_domain
    - scaling_whole_application
review_triggers:
  - sustained_module_specific_scale_cost
  - measured_release_coordination_delay
  - repeated_cross_module_incidents
  - new_data_isolation_requirement
owner: architecture_team
review_date: project_defined
~~~

Đây là tài liệu quyết định, không phải tệp cấu hình của một dịch vụ cloud. Giá trị nằm ở **giả định, đánh đổi và trigger đánh giá lại**. Khi số nhóm, chi phí, SLO hoặc ràng buộc dữ liệu thay đổi, tổ chức có cơ sở kiểm tra lại quyết định thay vì tranh luận bằng cảm tính.

## 18. Đánh giá theo tư duy Well-Architected

| Khía cạnh | Câu hỏi thực hành |
| --- | --- |
| **Bảo mật** | Mỗi mô đun có chính sách quyền cho từng hành vi? Có nguy cơ lộ dữ liệu giữa tenant? Những nơi ghi log/backup có được kiểm soát? |
| **Độ tin cậy** | Một lỗi process ảnh hưởng bao nhiêu năng lực? Có nhiều replica/zone, DB HA, backup và thử restore? Những lời gọi tới dịch vụ ngoài có timeout và cách xử lý lại? |
| **Hiệu quả hiệu năng** | p95/p99 ở các use case trọng yếu đạt mục tiêu? Nút thắt nằm ở DB, CPU hay external dependency? Scale cả ứng dụng có hiệu quả? |
| **Tối ưu chi phí** | Một pipeline chung và DB chung tiết kiệm được gì? Có phải nhân bản quá nhiều mô đun ít dùng để scale mô đun tải cao không? |
| **Khả năng vận hành** | Deploy/rollback có dễ và đáng tin cậy? Có metric và log theo mô đun? Ai sở hữu migration, contract và xử lý sự cố? |

Một số phiên bản Well-Architected Framework còn nêu riêng các trụ cột như **Operational Excellence, Sustainability**; số trụ cột và cách gọi phụ thuộc khung của nhà cung cấp được chọn. Bảng trên tập trung vào những đánh đổi có ảnh hưởng trực tiếp tới chủ đề bài học, không khẳng định thay thế toàn bộ framework chính thức.

### Checklist nghiệm thu thiết kế

- [ ] Mỗi mô đun có trách nhiệm nghiệp vụ, chủ sở hữu và hợp đồng công khai được ghi rõ.
- [ ] Không có phụ thuộc vòng hoặc truy cập repository/implementation tùy tiện giữa mô đun.
- [ ] Các invariant quan trọng và quyền sở hữu dữ liệu nằm trong mô đun chịu trách nhiệm.
- [ ] Giao dịch nội bộ, sự kiện sau commit và tích hợp bên ngoài có ngữ nghĩa lỗi được thiết kế.
- [ ] Các replica hoạt động không phụ thuộc vào trạng thái RAM hoặc file cục bộ để bảo toàn dữ liệu.
- [ ] Có kế hoạch scale ứng dụng/DB, tránh chạy trùng job và giới hạn pool connection.
- [ ] Có cơ chế authn/authz, kiểm tra tenant, quản lý secrets và audit phù hợp.
- [ ] Quy trình migration tương thích khi rolling deploy; rollback và restore được xem xét.
- [ ] Đo được latency, lỗi, resource, queue/outbox và các SLO nghiệp vụ theo mô đun.
- [ ] Quyết định modular monolith có ADR, đánh đổi và điều kiện đánh giá lại rõ ràng.

## 19. Bài tập tư duy kiến trúc

Một nền tảng SaaS đang có **một nhóm 8 kỹ sư**, phát hành hai lần mỗi tuần. Các tính năng gồm tài khoản, hóa đơn, tìm kiếm, xử lý tệp đính kèm và báo cáo. Tải tìm kiếm tăng mạnh vào giờ cao điểm, còn báo cáo tổng hợp nặng chỉ chạy mỗi đêm. Dữ liệu hóa đơn cần tính đúng đắn cao; đội chưa có hệ thống tracing phân tán hoàn chỉnh.

Hãy đề xuất mô hình ứng dụng ban đầu bằng cách trả lời:

1. Bạn sẽ tách những mô đun nghiệp vụ nào? Các mô đun sở hữu bảng và quy tắc gì?
2. Giao tiếp nào nên dùng lời gọi đồng bộ, giao tiếp nào phù hợp event sau commit? Tác vụ nào cần idempotency?
3. Nếu dùng modular monolith, bạn sẽ triển khai nhiều replica trên cloud ra sao, và xử lý báo cáo chạy theo lịch thế nào để tránh tải đêm ảnh hưởng API?
4. Điều kiện và số liệu gì khiến bạn cân nhắc tách tính năng tìm kiếm hoặc báo cáo thành deployment độc lập?
5. Bạn sẽ làm những kiểm tra nào để chứng minh hệ thống đạt yêu cầu bảo mật, khả dụng và chi phí?

Một phương án có cơ sở có thể bắt đầu với modular monolith để đơn giản hóa giao dịch và vận hành, đồng thời tách workload báo cáo nặng bằng hàng đợi/job phù hợp. Nếu cần tách thêm đơn vị triển khai, cần mô tả rõ tác động đến transaction, dữ liệu và vận hành. Không nên chỉ kết luận dựa trên số kỹ sư hoặc số chức năng.

## 20. Ghi nhớ

Modular monolith là lựa chọn thiết kế **một ứng dụng có cấu trúc mô đun chặt chẽ**, triển khai thống nhất nhưng giữ các năng lực nghiệp vụ độc lập ở mức mã và hợp đồng. Nó phù hợp khi cần phát triển nhanh, có nhiều giao dịch cần tính đúng đắn, quy mô hạ tầng chưa đòi hỏi mở rộng riêng từng phần và nhóm muốn giữ chi phí vận hành thấp.

Tính mô đun không tự tồn tại nhờ cách đặt tên package. Nó phải được giữ bằng **quyền sở hữu dữ liệu, API công khai, hướng phụ thuộc có kiểm soát, kiểm thử kiến trúc và kỷ luật phát hành**. Khi nhu cầu tách riêng tăng lên, những ranh giới này giúp chuyển đổi có phương pháp, nhưng vẫn phải xử lý các vấn đề mới của hệ phân tán như timeout, versioning, sự kiện trùng và dữ liệu nhất quán theo thời gian.

Trong thiết kế Cloud Architecture, câu hỏi quyết định không phải “monolith hay microservices đang phổ biến hơn?”, mà là **mô hình nào đáp ứng các yêu cầu nghiệp vụ, SLO và ràng buộc dữ liệu với độ phức tạp và tổng chi phí hợp lý nhất ở thời điểm này**.
