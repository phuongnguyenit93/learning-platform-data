# Kiến trúc lục giác và cách cô lập phụ thuộc nền tảng

## 1. Vấn đề: nghiệp vụ bị buộc chặt vào framework và cloud

Khi xây dựng một ứng dụng trên cloud, nhóm thường phải chọn HTTP framework, hệ quản trị cơ sở dữ liệu, message broker, dịch vụ lưu trữ, công cụ xác thực và cách triển khai. Những lựa chọn này cần thiết để ứng dụng chạy được, nhưng **quy tắc nghiệp vụ không nên phụ thuộc trực tiếp vào chi tiết của từng nền tảng**.

Hãy tưởng tượng chức năng xác nhận đặt phòng có logic như sau: nhận request HTTP, đọc dữ liệu bằng ORM, kiểm tra lịch trống, ghi bản ghi vào database và gửi sự kiện bằng SDK của cloud. Nếu tất cả nằm trong một controller hoặc một service mang đầy annotation của framework, việc thay ORM, chuyển từ REST sang consumer hàng đợi hay kiểm thử nghiệp vụ sẽ trở nên khó khăn. Mỗi lần thay công nghệ có thể kéo theo việc sửa cả quy tắc đặt phòng.

**Hexagonal Architecture** (kiến trúc lục giác, còn gọi là **Ports and Adapters**) giải quyết vấn đề này bằng cách đặt nghiệp vụ ở trung tâm và cho các cơ chế giao tiếp, lưu trữ, hạ tầng kết nối qua những **hợp đồng được định nghĩa từ phía ứng dụng**. Đây là một mô hình kiến trúc ứng dụng trong module CLOUD_ARCHITECTURE, giúp tách việc quyết định *hệ thống phải làm gì* khỏi *nó giao tiếp với thế giới bên ngoài bằng cách nào*.

Sau bài học, bạn có thể:

- Giải thích rõ **domain, application use case, port, adapter, composition root** và hướng phụ thuộc mã nguồn.
- Phân biệt **driving adapter** và **driven adapter**, **inbound port** và **outbound port**.
- Thiết kế ví dụ Java có nghiệp vụ độc lập với HTTP, ORM và cloud SDK.
- Kiểm thử core bằng bộ nhớ giả lập, đồng thời nhận biết các tình huống cần kiểm thử tích hợp thật.
- Áp dụng mô hình để đánh đổi giữa **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành** theo tư duy Well-Architected.

### Đơn giản hóa đúng nghĩa

Một ứng dụng nhỏ không nhất thiết cần đầy đủ thư mục, interface và adapter cho mọi thao tác. Hexagonal Architecture là **cách quản lý hướng phụ thuộc và ranh giới**, không phải yêu cầu phải tạo nhiều lớp hoặc microservice. Giá trị của nó đến từ những thay đổi độc lập hơn, kiểm thử dễ hơn và khả năng thay hạ tầng với tác động đã được kiểm soát.

## 2. Sơ đồ tổng thể: lõi ở giữa, adapter ở ngoài

Sáu cạnh của hình lục giác chỉ là **ẩn dụ để minh họa nhiều cổng kết nối**; số lượng port hay adapter không bị giới hạn ở sáu.

~~~mermaid
flowchart LR
    Web["HTTP REST / Web UI"] -->|"gọi"| In["Inbound port: CreateBooking"]
    Job["CLI / Scheduler / Message consumer"] -->|"gọi"| In
    subgraph Hex["Lõi ứng dụng (hexagon)"]
        In --> Use["Application use case"]
        Use --> Domain["Domain model / business rules"]
        Use --> OutDB["Outbound port: BookingStore"]
        Use --> OutPay["Outbound port: PaymentGateway"]
    end
    OutDB -->|"triển khai"| DB["Adapter: JDBC / JPA / managed database"]
    OutPay -->|"triển khai"| Pay["Adapter: HTTP client / cloud SDK"]
~~~

Lưu ý: mũi tên trong sơ đồ thể hiện **luồng gọi lúc chạy**, nên ứng dụng có thể gọi port lưu trữ và được adapter thực thi. **Hướng phụ thuộc trong mã nguồn** là vấn đề khác: adapter bên ngoài phụ thuộc vào hợp đồng trong core; core **không import** framework, SDK hay lớp adapter bên ngoài.

### 2.1. Các thành phần

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Domain** | Quy tắc, khái niệm, bất biến nghiệp vụ không phụ thuộc hạ tầng | Booking, Room, điều kiện khoảng ngày hợp lệ |
| **Application use case** | Điều phối một tác vụ nghiệp vụ, kiểm soát quy trình và gọi các port | CreateBookingService |
| **Inbound port** (*primary port*) | Hợp đồng các tác vụ được phép yêu cầu hệ thống thực hiện | CreateBooking.execute(command) |
| **Driving adapter** (*primary adapter*) | Nhận tín hiệu bên ngoài, chuyển đổi input và gọi inbound port | REST controller, CLI, message consumer |
| **Outbound port** (*secondary port*) | Hợp đồng core cần từ bên ngoài để hoàn tất tác vụ | BookingStore, PaymentGateway, ObjectStorage |
| **Driven adapter** (*secondary adapter*) | Cụ thể hóa outbound port bằng công nghệ thực | PostgreSQL adapter, Kafka publisher, S3 adapter |
| **Composition root** | Lắp các implementation phù hợp tại điểm khởi động | Spring Configuration hoặc khởi tạo bằng tay |

Thuật ngữ *primary/secondary* không nói thành phần nào quan trọng hơn; chúng mô tả **bên nào khởi phát tương tác**. HTTP adapter điều khiển lời gọi vào use case, còn database adapter được use case gọi thông qua một port.

### 2.2. Dependency inversion: quy tắc cốt lõi

~~~mermaid
flowchart TB
    A["Adapters: REST, Kafka, CLI, JDBC, cloud SDK"] --> P["Application: use cases + ports"]
    P --> D["Domain: business rules"]
~~~

Trong Java, đây là điểm mấu chốt: interface mô tả một nhu cầu nghiệp vụ như **BookingStore.insertIfNoOverlap** được định nghĩa trong application/core; adapter PostgreSQL nằm ở hạ tầng và **implement** interface đó. Lớp CreateBookingService nhận một BookingStore qua constructor. Vì thế core biết **khả năng cần dùng**, nhưng không biết SQL driver, connection pool, Spring Data, REST endpoint hoặc region cloud.

Quy tắc phụ thuộc cần giữ khi tổ chức module/repository:

1. **Domain** không import application, adapter, framework hoặc cloud SDK.
2. **Application** chỉ phụ thuộc domain, các port và API ngôn ngữ chuẩn thực sự phù hợp.
3. **Adapters** được phép phụ thuộc vào application/domain để chuyển đổi dữ liệu và triển khai port.
4. **Composition root** biết cả interface và các implementation để lắp nối lúc chạy.

Hướng gọi ở runtime có thể đi **từ core ra adapter**, nhưng điều này **không tạo dependency mã nguồn từ core sang adapter**. Phân biệt hai loại mũi tên là chìa khóa để hiểu kiến trúc lục giác.

## 3. Đặt ranh giới ở đâu?

### 3.1. Domain: điều gì luôn đúng?

Domain chứa các khái niệm, bất biến (*invariants*), quy tắc và trạng thái mang ý nghĩa nghiệp vụ. Ví dụ, ngày trả phòng phải sau ngày nhận phòng; một đặt phòng có trạng thái xác nhận phải thuộc về một đơn vị phòng có thật; cùng một đơn vị phòng không được có hai đặt phòng xác nhận chồng lấn thời gian.

Cần phân biệt những quy tắc có thể kiểm tra trên một đối tượng với những quy tắc cần phối hợp nhiều bản ghi. **Khoảng ngày hợp lệ** có thể kiểm tra ngay trong đối tượng Booking; **không có hai booking chồng lấn** đòi hỏi cơ chế nguyên tử khi ghi dữ liệu, không thể đảm bảo chỉ bằng một câu kiểm tra trước khi lưu.

### 3.2. Application: quy trình nào diễn ra?

Use case quyết định thứ tự xử lý của một tác vụ: kiểm tra input có ý nghĩa nghiệp vụ, tạo domain object, gọi cổng lưu trữ, diễn giải kết quả và trả output. Use case không cần biết nó được gọi bởi REST hay message consumer.

Đặt các quy tắc giao dịch, phân quyền ở mức hành động và chính sách idempotency ở lớp phù hợp. Ví dụ quyền “người dùng này có được đặt phòng cho tài khoản đó hay không” là yêu cầu ứng dụng cần thực thi; chi tiết xác minh JWT có thể nằm ở adapter HTTP. Kiểm tra quyền không được biến mất chỉ vì một adapter đầu vào khác không dùng HTTP.

### 3.3. Adapter: giao tiếp với công nghệ cụ thể

Adapter chuyển đổi một hợp đồng vào/ra sang cách nói của nền tảng:

- HTTP controller chuyển JSON và header thành command, ánh xạ kết quả hoặc lỗi thành status code.
- JDBC/JPA adapter chuyển entity nghiệp vụ sang bảng, transaction, SQL và exception của driver.
- SDK object storage chuyển yêu cầu lưu tài liệu thành tên bucket, key, retry, mã hóa và API của nhà cung cấp.
- Message consumer chuyển event thành command, kiểm tra danh tính người gửi nếu cần, xử lý ack/nack, retry và dead-letter theo chính sách.

Adapter có thể mang logic **kỹ thuật** (pagination SQL, ký chữ ký callback, backoff, serialization), nhưng quy tắc **nghiệp vụ** chung không nên bị phân tán vào từng adapter.

## 4. Chọn port theo ngôn ngữ nghiệp vụ

Port không phải bản sao của SDK. Interface có tên kiểu **S3ClientWrapper.putObject** nhưng dùng trực tiếp các kiểu S3 ở tham số vẫn khiến core phụ thuộc nhà cung cấp dưới một lớp vỏ mỏng.

Thay vì tạo một port “đa năng” với hàng chục method tùy ý, hãy diễn tả khả năng mà use case cần:

| Nhu cầu của ứng dụng | Port có ý nghĩa | Chi tiết nên nằm trong adapter |
| --- | --- | --- |
| Lưu booking nếu không xung đột | BookingStore.insertIfNoOverlap(booking) | SQL, khóa, transaction, unique/exclusion constraint |
| Lấy trạng thái thanh toán | PaymentGateway.checkStatus(paymentId) | Endpoint, API key, HTTP timeout, response mapping |
| Lưu hóa đơn đã tạo | InvoiceArchive.save(document) | Bucket/container, region, multipart upload, SDK |
| Tra cứu tỷ giá phục vụ định giá | ExchangeRateProvider.currentRate(pair) | Nhà cung cấp API, cache, authentication |
| Gửi yêu cầu thông báo | NotificationRequests.enqueue(message) | Queue topic, serializer, retry, DLQ |

**Port phải mô tả ngữ nghĩa**, không chỉ chữ ký hàm: ví dụ thao tác ghi booking trả về thành công hay xung đột, có cần nguyên tử không, thời hạn phản hồi và loại lỗi nào ứng dụng có thể xử lý. Cùng một interface Java không bảo đảm các adapter có cùng hành vi nếu hợp đồng ngữ nghĩa bị bỏ qua.

Với các yêu cầu quá đơn giản, không cần tạo port riêng chỉ để bọc mỗi phép toán. Thêm port khi nó tạo ranh giới có giá trị: tách quy tắc nghiệp vụ khỏi công nghệ, hỗ trợ kiểm thử hoặc cho phép thay đổi triển khai ở điểm có khả năng thay đổi thực tế.

## 5. Ví dụ: thiết kế chức năng đặt phòng bằng Java

Giả sử ứng dụng phục vụ khách thuê phòng. Người dùng chọn phòng và khoảng ngày; hệ thống phải xác nhận đặt phòng **chỉ khi chưa có booking xác nhận bị chồng lấn**. Chúng ta xây dựng một lát cắt nhỏ để thấy hướng phụ thuộc, thay vì cố mô phỏng toàn bộ hệ thống khách sạn.

**Yêu cầu tối thiểu của ví dụ:**

- Ngày trả phòng sau ngày nhận phòng; roomId không trống.
- Với cùng roomId, hai khoảng ngày dạng **[checkIn, checkOut)** không được chồng lấn. CheckOut ngày 12 và booking tiếp theo CheckIn ngày 12 được coi là sát nhau, không chồng lấn.
- Ghi booking thành công hoặc bị từ chối phải có ý nghĩa **nguyên tử** khi có hai yêu cầu đồng thời.
- REST và database là adapter; use case có thể chạy trong unit test không có server hoặc cloud.

Ví dụ sử dụng Java 17+ cho cú pháp record. Các khối code có ghi rõ đường dẫn tương đối; mỗi khối là một file Java riêng trong dự án.

### 5.1. Tổ chức thư mục

~~~text
booking/
  domain/
    Booking.java
  application/
    port/in/
      CreateBooking.java
      CreateBookingCommand.java
    port/out/
      BookingStore.java
    service/
      CreateBookingService.java
      RoomUnavailableException.java
  adapters/
    in/http/
      BookingHttpController.java
    out/jdbc/
      PostgresBookingStore.java
  bootstrap/
    BookingConfiguration.java
~~~

Đường dẫn là cách tổ chức tham khảo. Có thể dùng Java modules, Maven modules hoặc packages tùy quy mô đội; điều phải được giữ là **hướng phụ thuộc thực tế**, không phải số lượng folder.

### 5.2. Domain không có import của framework

File **domain/Booking.java**:

~~~java
package example.booking.domain;

import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

public record Booking(
        UUID id,
        String roomId,
        LocalDate checkIn,
        LocalDate checkOut) {

    public Booking {
        Objects.requireNonNull(id, "id");
        if (roomId == null || roomId.isBlank()) {
            throw new IllegalArgumentException("roomId is required");
        }
        Objects.requireNonNull(checkIn, "checkIn");
        Objects.requireNonNull(checkOut, "checkOut");
        if (!checkOut.isAfter(checkIn)) {
            throw new IllegalArgumentException("checkOut must be after checkIn");
        }
    }
}
~~~

Đối tượng Booking chỉ sử dụng API chuẩn của Java; nó không biết PostgreSQL, JDBC, HTTP, Spring hay cloud provider. Validate ở domain giúp mọi đường vào hệ thống đều phải tuân theo cùng bất biến về ngày.

### 5.3. Inbound port và command

File **application/port/in/CreateBookingCommand.java**:

~~~java
package example.booking.application.port.in;

import java.time.LocalDate;

public record CreateBookingCommand(
        String roomId,
        LocalDate checkIn,
        LocalDate checkOut) {
}
~~~

File **application/port/in/CreateBooking.java**:

~~~java
package example.booking.application.port.in;

import java.util.UUID;

public interface CreateBooking {
    UUID execute(CreateBookingCommand command);
}
~~~

Use case nhận command thuần Java, không nhận **HttpServletRequest**, **ResponseEntity** hay DTO phụ thuộc thư viện web. Inbound port là hợp đồng mà REST controller, CLI hoặc một adapter nhận sự kiện đều có thể gọi.

### 5.4. Outbound port và hợp đồng nguyên tử

File **application/port/out/BookingStore.java**:

~~~java
package example.booking.application.port.out;

import example.booking.domain.Booking;

public interface BookingStore {
    /**
     * Atomically inserts a confirmed booking if no confirmed
     * booking for the same room overlaps [checkIn, checkOut).
     * Returns false on a booking conflict.
     * Other infrastructure failures must not be reported as conflicts.
     */
    boolean insertIfNoOverlap(Booking booking);
}
~~~

Chú ý từ **atomically**. Nếu port chỉ có hai hàm checkAvailable() rồi save(), use case dễ gặp race condition: hai request cùng đọc “còn chỗ” và cùng lưu. Hợp đồng port yêu cầu adapter cung cấp cơ chế bảo vệ khi ghi, ví dụ database constraint phù hợp hoặc transaction/lock đã được kiểm chứng.

### 5.5. Use case chỉ phụ thuộc vào port

File **application/service/RoomUnavailableException.java**:

~~~java
package example.booking.application.service;

public final class RoomUnavailableException extends RuntimeException {
    public RoomUnavailableException() {
        super("Room is not available for the requested dates");
    }
}
~~~

File **application/service/CreateBookingService.java**:

~~~java
package example.booking.application.service;

import example.booking.application.port.in.CreateBooking;
import example.booking.application.port.in.CreateBookingCommand;
import example.booking.application.port.out.BookingStore;
import example.booking.domain.Booking;
import java.util.Objects;
import java.util.UUID;

public final class CreateBookingService implements CreateBooking {
    private final BookingStore store;

    public CreateBookingService(BookingStore store) {
        this.store = Objects.requireNonNull(store);
    }

    @Override
    public UUID execute(CreateBookingCommand command) {
        Objects.requireNonNull(command);
        Booking booking = new Booking(
                UUID.randomUUID(),
                command.roomId(),
                command.checkIn(),
                command.checkOut());

        if (!store.insertIfNoOverlap(booking)) {
            throw new RoomUnavailableException();
        }
        return booking.id();
    }
}
~~~

Use case không import JDBC hay Spring. Nếu tuần sau REST được thay bằng message consumer, **không cần sửa** CreateBookingService. Nếu đội đổi Postgres sang hệ lưu trữ khác, core cũng không cần thay **nếu adapter mới giữ đúng hợp đồng nguyên tử**.

Ví dụ tập trung vào một tình huống nghiệp vụ. Trong production cần bổ sung xác thực chủ thể, phân quyền, trạng thái đặt phòng, idempotency cho yêu cầu gửi lại, chính sách giá và thời hạn giữ chỗ theo yêu cầu đã được duyệt.

## 6. Driving adapter: nhận HTTP nhưng không chứa nghiệp vụ

Giả sử ứng dụng dùng Spring Web ở lớp ngoài. REST controller chuyển đổi input HTTP thành CreateBookingCommand và ánh xạ output thành response; nó **không trực tiếp kiểm tra chỗ trống hoặc thao tác SQL**.

File **adapters/in/http/BookingHttpController.java**:

~~~java
package example.booking.adapters.in.http;

import example.booking.application.port.in.CreateBooking;
import example.booking.application.port.in.CreateBookingCommand;
import example.booking.application.service.RoomUnavailableException;
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/bookings")
public final class BookingHttpController {
    private final CreateBooking createBooking;

    public BookingHttpController(CreateBooking createBooking) {
        this.createBooking = createBooking;
    }

    @PostMapping
    public ResponseEntity<CreatedBookingResponse> create(
            @RequestBody CreateBookingRequest request) {
        UUID id = createBooking.execute(new CreateBookingCommand(
                request.roomId(),
                request.checkIn(),
                request.checkOut()));
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new CreatedBookingResponse(id));
    }

    @ExceptionHandler(RoomUnavailableException.class)
    public ResponseEntity<String> conflict(RoomUnavailableException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body("Room is not available");
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<String> invalid(IllegalArgumentException ex) {
        return ResponseEntity.badRequest().body("Invalid booking request");
    }

    public record CreateBookingRequest(
            String roomId, LocalDate checkIn, LocalDate checkOut) {}

    public record CreatedBookingResponse(UUID bookingId) {}
}
~~~

Các annotation **@RestController**, **@PostMapping**, **@RequestBody** và kiểu ResponseEntity chỉ xuất hiện trong adapter. Thay HTTP bằng gRPC hoặc CLI chỉ cần adapter đầu vào khác gọi cùng CreateBooking; chính sách nghiệp vụ không bị sao chép.

Code trên minh họa ánh xạ cơ bản. Trong thực tế cần giải quyết lỗi JSON sai định dạng, ngày không parse được, định dạng lỗi ổn định, logging an toàn, authentication/authorization, rate limiting và mapping exception theo hợp đồng API. Các lỗi ở tầng vận chuyển có thể xử lý bằng cơ chế chung của framework mà không đẩy chúng vào domain.

### Khi có nhiều kênh đầu vào

Một scheduled job có thể gọi use case để xử lý booking đã được chuẩn hóa từ file; một message consumer cũng có thể gọi use case khi nhận yêu cầu hợp lệ từ hệ thống đối tác. Các adapter đó chịu trách nhiệm **chuyển đổi dữ liệu và ngữ nghĩa giao nhận**. Nếu broker giao lặp, consumer phải dùng chính sách idempotency phù hợp; không được giả định một use case thuần Java tự động biết message đã được xử lý trước.

## 7. Driven adapter: PostgreSQL bảo đảm chống đặt trùng

### 7.1. Schema thực thi hợp đồng của outbound port

Với PostgreSQL, có thể dùng **exclusion constraint** để không cho hai booking ở trạng thái CONFIRMED chồng lấn khoảng ngày trên cùng roomId. Ví dụ:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE bookings (
    id          uuid PRIMARY KEY,
    room_id     text NOT NULL,
    check_in    date NOT NULL,
    check_out   date NOT NULL,
    status      text NOT NULL
                CHECK (status IN ('CONFIRMED', 'CANCELLED')),
    CHECK (check_out > check_in),
    CONSTRAINT no_overlapping_confirmed_bookings
      EXCLUDE USING gist (
        room_id WITH =,
        daterange(check_in, check_out, '[)') WITH &&
      )
      WHERE (status = 'CONFIRMED')
);
~~~

Ràng buộc trên thuộc về PostgreSQL và chỉ có tác dụng với **booking xác nhận** ở bảng này. Cần quản lý schema bằng migration có kiểm soát; DBA/đội vận hành phải đánh giá phiên bản PostgreSQL, extension, indexing, dữ liệu hiện hữu và hiệu năng ở tải thực.

Vì DB thực thi kiểm tra xung đột ngay trong thao tác ghi, hai transaction chạy đồng thời không thể cùng commit hai bản ghi CONFIRMED vi phạm exclusion constraint. Điều này khác với việc chỉ SELECT kiểm tra trống rồi INSERT bằng hai thao tác không có cơ chế bảo vệ.

### 7.2. JDBC adapter triển khai outbound port

File **adapters/out/jdbc/PostgresBookingStore.java**:

~~~java
package example.booking.adapters.out.jdbc;

import example.booking.application.port.out.BookingStore;
import example.booking.domain.Booking;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class PostgresBookingStore implements BookingStore {
    private final DataSource dataSource;

    public PostgresBookingStore(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public boolean insertIfNoOverlap(Booking booking) {
        String sql = """
            INSERT INTO bookings
                (id, room_id, check_in, check_out, status)
            VALUES (?, ?, ?, ?, 'CONFIRMED')
            """;
        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement(sql)) {
            statement.setObject(1, booking.id());
            statement.setString(2, booking.roomId());
            statement.setObject(3, booking.checkIn());
            statement.setObject(4, booking.checkOut());
            statement.executeUpdate();
            return true;
        } catch (SQLException ex) {
            // PostgreSQL SQLSTATE 23P01: exclusion_violation
            if ("23P01".equals(ex.getSQLState())) {
                return false;
            }
            throw new IllegalStateException("Cannot persist booking", ex);
        }
    }
}
~~~

Chỉ lỗi **23P01** mới được diễn giải là xung đột đặt chỗ trong adapter minh họa. Timeout, hết connection, lỗi mạng, sai schema hay lỗi quyền truy cập phải được báo như lỗi hạ tầng; **không được biến mọi SQLException thành “phòng hết chỗ”**. Với các tình huống transaction phức tạp hơn, cần kiểm soát commit/rollback và ranh giới transaction tường minh.

Một số lưu ý quan trọng về ngữ nghĩa:

- Ví dụ SQL dùng khoảng ngày **[checkIn, checkOut)**, tránh đánh dấu trùng vào ngày trả phòng.
- **Không tự suy ra tính tương đương giữa adapter**: đổi từ PostgreSQL sang key-value database không có nghĩa một conditional write theo khóa đơn giản sẽ phát hiện mọi khoảng ngày chồng lấn. Adapter mới phải có chiến lược nguyên tử khác, có thể là thiết kế khóa theo đơn vị ngày, transaction hoặc một cơ chế phù hợp đã kiểm thử.
- Yêu cầu đặt chỗ mới có thể bị gửi lại sau khi client mất response. UUID sinh mới cho mỗi request trong ví dụ **chưa chống tạo lặp giữa các lần gửi lại**. Production cần idempotency key gắn với tác nhân và nội dung yêu cầu, với kết quả được lưu và truy xuất an toàn.
- Nếu có thanh toán và gửi sự kiện đi kèm, một INSERT thành công **không tự động làm các hệ thống bên ngoài cập nhật cùng lúc**; xem mục nhất quán và outbox bên dưới.

### 7.3. Composition root lắp nối lúc khởi động

File **bootstrap/BookingConfiguration.java**:

~~~java
package example.booking.bootstrap;

import example.booking.application.port.in.CreateBooking;
import example.booking.application.port.out.BookingStore;
import example.booking.application.service.CreateBookingService;
import example.booking.adapters.out.jdbc.PostgresBookingStore;
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class BookingConfiguration {
    @Bean
    BookingStore bookingStore(DataSource dataSource) {
        return new PostgresBookingStore(dataSource);
    }

    @Bean
    CreateBooking createBooking(BookingStore bookingStore) {
        return new CreateBookingService(bookingStore);
    }
}
~~~

Lớp bootstrap biết cả core và adapter nên được phép phụ thuộc vào chúng. Use case không cần annotation để được khởi tạo; framework được dùng ở biên để kết nối các thành phần. Trong ứng dụng nhỏ, **khởi tạo bằng constructor thủ công** cũng có thể là composition root hợp lý.

## 8. Kiểm thử ở các ranh giới khác nhau

Một lợi ích lớn của hexagonal architecture là use case **có thể chạy mà không cần khởi động web server, database hay cloud SDK**. Tuy nhiên, không nên kết luận từ unit test rằng mọi hợp đồng adapter ngoài đời đều đúng.

### 8.1. Unit test cho use case với fake adapter

Ví dụ JUnit 5:

~~~java
package example.booking.application.service;

import example.booking.application.port.in.CreateBookingCommand;
import example.booking.application.port.out.BookingStore;
import example.booking.domain.Booking;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CreateBookingServiceTest {
    @Test
    void refusesOverlappingDateRanges() {
        List<Booking> saved = new ArrayList<>();
        BookingStore fakeStore = candidate -> {
            boolean conflict = saved.stream().anyMatch(existing ->
                existing.roomId().equals(candidate.roomId())
                && existing.checkIn().isBefore(candidate.checkOut())
                && candidate.checkIn().isBefore(existing.checkOut())
            );
            if (conflict) return false;
            saved.add(candidate);
            return true;
        };
        var useCase = new CreateBookingService(fakeStore);
        var start = LocalDate.of(2027, 3, 10);
        var end = LocalDate.of(2027, 3, 12);

        useCase.execute(new CreateBookingCommand("R-101", start, end));

        assertThrows(RoomUnavailableException.class,
            () -> useCase.execute(new CreateBookingCommand(
                "R-101", start.plusDays(1), end.plusDays(1))));
        assertEquals(1, saved.size());
    }
}
~~~

Test không cần database và tập trung vào **hành vi use case** khi port báo xung đột. Fake ở đây chạy tuần tự, **không chứng minh an toàn khi concurrency**. Phép kiểm tra đó thuộc về kiểm thử tích hợp trên adapter/database thật.

### 8.2. Bản đồ kiểm thử theo hợp đồng

| Tầng kiểm thử | Đối tượng và câu hỏi | Ví dụ |
| --- | --- | --- |
| Domain unit test | Bất biến nghiệp vụ có luôn đúng? | Từ chối checkOut trước/equal checkIn; chấp nhận hai khoảng sát nhau |
| Application unit test | Use case diễn giải kết quả port đúng? | Khi store trả false thì báo RoomUnavailable |
| Adapter integration test | Driver, SQL, constraint, serialization có đúng với hợp đồng? | Hai INSERT đồng thời với các khoảng chồng lấn, tối đa một commit |
| Contract test | Adapter khác có thực thi cùng ngữ nghĩa port? | Cùng tập ca lỗi, biên ngày và mã trạng thái với Postgres hoặc store thay thế |
| API test | HTTP mapping, authentication, lỗi input có đúng? | 201 khi tạo thành công, 409 khi xung đột, 400 khi ngày không hợp lệ |
| End-to-end / resilience | Toàn chuỗi xử lý lỗi mạng, timeout, retry, sự cố ra sao? | Mất kết nối thanh toán, giao sự kiện trùng, phục hồi sau restart |

Trong thực tế, có thể dùng PostgreSQL chạy trong container dành cho test hoặc môi trường tích hợp cô lập để xác nhận constraint và transaction. Nếu dùng bản giả của managed queue/object storage, vẫn cần một số phép kiểm chứng với dịch vụ thật vì emulator không nhất thiết có cùng semantics, giới hạn, IAM hay hành vi lỗi.

### 8.3. Fake và mock không được che lấp lỗi hợp đồng

Một fake store có thể lưu booking bằng List và trả true/false, nhưng nếu fake luôn thành công còn database thực tế có transaction conflict thì unit test có thể tạo cảm giác an toàn giả. Định nghĩa rõ **contract tests** cho từng outbound port; phân biệt lỗi nghiệp vụ, lỗi tạm thời và lỗi không thể khôi phục. Với các adapter có tính nhất quán hoặc yêu cầu thời gian đặc biệt, hãy thêm kiểm thử dưới tải và kịch bản lỗi thật.

## 9. Cô lập phụ thuộc cloud bằng cổng có ngữ nghĩa

Port là cơ chế thích hợp để giới hạn phạm vi mà SDK và API cloud ảnh hưởng tới core. Ví dụ ứng dụng cần lưu hóa đơn sau khi sinh PDF. Use case quan tâm đến **lưu, lấy lại và tham chiếu hóa đơn**, chứ không cần biết bucket S3, blob container Azure hay thư viện Google Cloud Storage.

### 9.1. Thiết kế port lưu tài liệu

Một ví dụ nhỏ:

~~~java
package example.invoice.application.port.out;

public interface InvoiceArchive {
    StoredInvoice save(String invoiceId, byte[] pdfContent);

    record StoredInvoice(String reference, String checksum) {}
}
~~~

Các adapter tương ứng có thể là:

- **S3InvoiceArchive** dùng SDK AWS, tự xử lý bucket, object key, metadata và API lỗi.
- **GcsInvoiceArchive** dùng SDK Google Cloud Storage, chuyển đổi cùng hợp đồng nghiệp vụ.
- **LocalFileInvoiceArchive** dùng filesystem để phát triển cục bộ hoặc một môi trường thử nghiệm thích hợp.

Use case vẫn gọi **InvoiceArchive.save** và nhận một tham chiếu được hiểu theo hợp đồng. Nếu core lưu nguyên đường dẫn s3://... và mọi logic phía trên phải parse bucket/key theo cú pháp S3, sự cô lập chỉ là hình thức. Hãy cân nhắc **opaque reference** hoặc định danh nghiệp vụ khi use case không cần biết biểu diễn lưu trữ.

**Chú ý giới hạn của ví dụ:** dùng byte[] có thể không phù hợp với hóa đơn rất lớn vì phải nạp cả nội dung vào bộ nhớ. Với tài liệu lớn, cần port cung cấp streaming hoặc upload theo luồng, đồng thời định nghĩa chính xác lỗi giữa chừng, checksum và quyền truy cập. Đừng trừu tượng hóa bằng API không đáp ứng ràng buộc hiệu năng thực tế.

### 9.2. Không thể loại bỏ hoàn toàn phụ thuộc nền tảng

Port giúp thay đổi SDK hoặc backend ít ảnh hưởng đến nghiệp vụ, nhưng không xóa được những sự khác nhau có ý nghĩa:

| Khác biệt nền tảng | Hệ quả cần đánh giá |
| --- | --- |
| Tính nhất quán đọc/ghi, mô hình khóa | Có đáp ứng read-after-write, xử lý cạnh tranh và nghiệp vụ nhạy cảm không? |
| Chính sách định danh, IAM và khóa mã hóa | Ai có quyền truy cập, audit và quản lý secret; chuyển đổi quyền ra sao? |
| Giới hạn kích thước, tốc độ, rate limit | Cần phân mảnh, streaming, retry, throttle hay backpressure không? |
| Tính năng sự kiện, thời hạn giữ/xóa dữ liệu | Port có cần khả năng riêng hay phải thay đổi quy trình nghiệp vụ? |
| Vùng địa lý, pháp lý và phí egress | Ảnh hưởng đến vị trí dữ liệu, độ trễ, chi phí và DR thế nào? |
| SLA, timeout và hành vi lỗi | Adapter phải phân loại lỗi, retry và đo SLO theo đúng sản phẩm thật |

Nếu một chức năng chỉ có trong một nền tảng và là yêu cầu cốt lõi, **đừng giả vờ các cloud tương đương** bằng cách che tất cả dưới interface chung. Có thể ghi rõ capability, dùng một port chuyên biệt hoặc chấp nhận phụ thuộc nhà cung cấp có chủ đích, được ghi ADR. Mục tiêu là **kiểm soát và làm rõ phụ thuộc**, không phải hứa hẹn di chuyển cloud không tốn công.

### 9.3. Chọn mức độ trừu tượng vừa đủ

Một port chỉ có ích khi cho phép diễn đạt nghiệp vụ độc lập với cơ chế. Nếu mọi lần gọi chỉ chuyển tiếp 1:1 vào SDK, interface có thể tăng số lớp mà không giảm coupling. Ngược lại, nếu mọi adapter dùng chung một interface quá rộng bao gồm upload, ký URL, ACL, nhân bản đa vùng và streaming dù use case chỉ cần lưu hóa đơn, thiết kế đã tự tạo độ phức tạp mới.

Ưu tiên **interface nhỏ theo khả năng mà một use case thực sự cần**, kèm hợp đồng về lỗi, kết quả và bảo mật. Không bắt buộc tạo một interface cho từng lời gọi hoặc từng dịch vụ cloud.

## 10. Triển khai trên cloud: ranh giới mã nguồn và ranh giới vận hành

Hexagonal Architecture nói về **cấu trúc và phụ thuộc của ứng dụng**, không quy định số process, container, VPC, AZ hoặc region. Một modular monolith gồm domain, application và adapters có thể được đóng gói thành một ứng dụng rồi chạy trên VM, container, PaaS hoặc serverless nếu ràng buộc cho phép.

~~~mermaid
flowchart TB
    Internet["Web / Partner"] --> Gateway["HTTPS Load Balancer / API Gateway"]
    Gateway --> App["Một hoặc nhiều instance ứng dụng: Core + REST adapter + JDBC adapter"]
    App --> DB["Managed PostgreSQL"]
    App --> Storage["Cloud Object Storage"]
    App --> Broker["Managed Queue, nếu có tác vụ nền"]
    Broker --> Worker["Worker: Message adapter + cùng use case liên quan"]
    App -.-> Telemetry["Centralized logs, metrics, traces"]
    Worker -.-> Telemetry
~~~

Hình trên cho thấy **tách lớp logic không bắt buộc tách triển khai**. Có thể chạy core và adapter trong cùng một tiến trình để giảm round trip và chi phí, trong khi worker nền là tiến trình khác khi thực sự cần. Sau này một use case có thể được triển khai riêng nếu có yêu cầu rõ ràng về tải, ownership hoặc lịch phát hành.

Nếu chuyển từ VM sang container/serverless, core ít phải sửa khi hợp đồng giữ nguyên; tuy vậy vẫn phải xem xét cold start, thời hạn xử lý, kết nối database, giới hạn concurrency, networking, IAM và vận hành. **Port không tự làm những giới hạn nền tảng biến mất**.

## 11. Độ tin cậy và tính nhất quán khi nhiều adapter cùng tham gia

Phân tách phụ thuộc không có nghĩa hệ thống tự động trở nên nhất quán hoặc đáng tin cậy. Các lời gọi từ một use case đến database, message broker, payment gateway và object storage thường là **những giao dịch độc lập**, không có một transaction toàn cục dễ dùng. Thiết kế port giúp thấy rõ ranh giới, nhưng nhóm vẫn phải quyết định cách xử lý lỗi.

### 11.1. Tại sao ghi database rồi publish có thể mất sự kiện?

Xét use case xác nhận booking và thông báo:

~~~text
1. Ghi booking CONFIRMED vào database       -> commit thành công
2. Publish BookingConfirmed lên queue        -> timeout hoặc process crash
3. Không có sự kiện thông báo, dù booking đã tồn tại
~~~

Nếu đảo thứ tự và publish trước khi ghi database, có thể sinh sự kiện cho một booking mà transaction sau đó thất bại. Mô hình hexagonal không bảo đảm atomicity giữa hai tài nguyên.

### 11.2. Transactional outbox và tiêu thụ có thể lặp

Một phương án thường dùng khi cần bảo đảm **sự kiện không bị quên sau commit**:

~~~mermaid
sequenceDiagram
    participant A as Use case
    participant DB as Database
    participant R as Outbox relay
    participant Q as Queue
    participant C as Consumer
    A->>DB: Transaction: ghi booking + outbox event
    DB-->>A: Commit
    R->>DB: Đọc outbox chưa chuyển
    R->>Q: Publish BookingConfirmed
    Q-->>R: Ack
    R->>DB: Đánh dấu đã chuyển
    Q->>C: Deliver event
    C->>C: Idempotent handling
~~~

Outbox giảm rủi ro mất sự kiện giữa DB và broker bằng cách ghi booking và bản ghi outbox trong **cùng transaction DB**. Tuy nhiên, relay có thể publish thành công rồi crash trước khi đánh dấu đã chuyển; vì vậy sự kiện **có thể được giao lặp**. Consumer phải xử lý idempotent, ví dụ lưu eventId đã xử lý hoặc dùng thao tác cập nhật có tính idempotency.

Để giữ port rõ ngữ nghĩa, có thể thiết kế outbound port **BookingCommitPort.confirmAndRecordEvent** với yêu cầu nguyên tử; adapter database thực hiện ghi booking và outbox trong cùng transaction. Một lựa chọn khác là quản lý transaction ở adapter phối hợp phù hợp. Không được tạo hai port độc lập rồi giả định Spring transaction tự động bao phủ một queue bên ngoài.

### 11.3. Phân loại lỗi và retry theo hợp đồng

| Tình huống | Core cần biết điều gì? | Adapter cần xử lý điều gì? |
| --- | --- | --- |
| Phòng đã có booking trùng | Xung đột nghiệp vụ, trả kết quả từ chối | Phát hiện SQL constraint hoặc quy tắc nguyên tử tương đương |
| Database tạm mất kết nối | Kết quả chưa chắc đã được commit, cần chính sách thử lại thích hợp | Phân loại timeout/connection, observability, tránh báo sai xung đột |
| Payment gateway timeout | Trạng thái giao dịch **chưa xác định**, cần đối soát | Kiểm soát deadline, idempotency key, truy vấn trạng thái khi được hỗ trợ |
| Queue giao cùng message hai lần | Không phát sinh tác dụng phụ trùng | Deduplication/idempotency, ack/nack, DLQ phù hợp |
| Đối tượng lưu trữ không truy cập được | Use case xử lý trạng thái lỗi hoặc trì hoãn theo yêu cầu | Retry có giới hạn, cảnh báo, quy tắc bảo mật và mã lỗi |

**Retry mù quáng có thể làm hại tính đúng đắn.** Không retry mọi lỗi, không tự động lặp lại thanh toán nếu chưa biết lệnh trước đã được chấp nhận hay chưa. Việc phân loại lỗi cần phản ánh hành vi nghiệp vụ và điều khoản của nhà cung cấp.

## 12. Phân bổ trách nhiệm bảo mật, quan sát và hiệu năng

### 12.1. Bảo mật đi qua nhiều ranh giới

Hexagonal không xóa trách nhiệm bảo mật của core. Nên phân biệt:

- **Xác thực ở biên**: HTTP adapter hoặc gateway xác minh JWT/session; message adapter kiểm tra danh tính producer theo cơ chế broker.
- **Ủy quyền theo nghiệp vụ**: application quyết định chủ thể có quyền thao tác trên tài nguyên nào. Một adapter khác gọi cùng use case không được vô tình bỏ qua kiểm soát này.
- **Quyền hệ thống**: adapter được cấp IAM role, secret và quyền mạng tối thiểu để đọc/ghi đúng tài nguyên.
- **Bảo vệ dữ liệu**: adapter mã hóa truyền tải, ghi log an toàn, xử lý dữ liệu nhạy cảm; domain/application xác định loại dữ liệu và quy tắc truy cập/lưu giữ có ý nghĩa nghiệp vụ.

Đối với hệ thống nhiều tenant, một command thường cần ngữ cảnh actor/tenant từ lớp biên đã được xác thực. **Đừng tin tenantId do client tùy ý cung cấp** nếu nó chưa được gắn với danh tính và quyền truy cập. Có thể định nghĩa một kiểu ActorContext trong application độc lập với JWT claim của framework.

### 12.2. Quan sát xuyên lớp nhưng không rò rỉ SDK

| Nhu cầu | Cách triển khai hợp lý |
| --- | --- |
| Truy vết một booking từ REST đến database/broker | Correlation/trace ID truyền qua các adapter, telemetry tại biên và các điểm I/O |
| Đo tỷ lệ lỗi và độ trễ | Metrics theo use case và port, dashboard kèm SLI/SLO |
| Điều tra lỗi hạ tầng | Log chi tiết driver/SDK trong adapter, phân loại lỗi và liên kết với request ID |
| Tránh lộ dữ liệu nhạy cảm | Redaction, kiểm soát trường log, không ghi token, mật khẩu, dữ liệu thẻ |
| Phân tích tải | Đo latency và throughput thực của từng adapter; đánh giá pool, retry, cache, network hops |

Thông thường instrumentation dùng framework hoặc agent tại adapter/biên. Core có thể ghi sự kiện nghiệp vụ hoặc gọi một port telemetry **khi thực sự có lý do**; không nên buộc domain model phải import OpenTelemetry SDK hoặc cloud logging SDK chỉ để phục vụ log kỹ thuật.

### 12.3. Hiệu năng và chi phí của các ranh giới

Một interface Java gọi trong cùng tiến trình có chi phí khác rất nhiều so với một service gọi qua HTTP. **Hexagonal không đòi hỏi mỗi adapter là một dịch vụ độc lập**, vì vậy không nên quy mọi vấn đề network latency cho mô hình này.

Khi sử dụng adapter từ xa, cần tính **timeout, retry budget, connection pool, rate limit, serialization, kích thước dữ liệu và failure domain**. Khi biến một port nội bộ thành lời gọi sang microservice, hợp đồng lỗi và thời gian phản hồi thường phải thay đổi; không thể xem đó chỉ là thay tên implementation.

Ví dụ object storage adapter có thể dùng streaming thay vì byte[] nếu tài liệu lớn. Một port tra cứu cần pagination để tránh tải toàn bộ dữ liệu lên RAM; các yêu cầu pagination và consistency phải được xác định theo hành vi nghiệp vụ thay vì chỉ bọc method query của DB.

## 13. Đặt Hexagonal cạnh Layered, Clean, Onion và microservices

Các khái niệm này liên quan nhưng không đồng nghĩa:

| Mô hình | Trọng tâm | Quan hệ với hexagonal |
| --- | --- | --- |
| **Layered Architecture** | Chia thành presentation, business, data access | Có thể rất tốt nếu hướng phụ thuộc rõ; dễ lỗi nếu business phụ thuộc implementation DAO/framework |
| **Hexagonal / Ports and Adapters** | Cô lập lõi bằng các hợp đồng vào/ra và adapter | Nhấn mạnh tính độc lập của nghiệp vụ với kênh giao tiếp, persistence và nền tảng |
| **Onion Architecture** | Lõi domain ở tâm, dependency hướng vào | Cùng nguyên tắc phụ thuộc vào phần bên trong, thường phân tầng theo domain/application/infrastructure |
| **Clean Architecture** | Entities, use cases, interface adapters, frameworks/drivers | Có nhiều điểm tương đồng, khác về thuật ngữ và cách diễn đạt ranh giới |
| **DDD** (*Domain-Driven Design*) | Mô hình nghiệp vụ, bounded context, ngôn ngữ chung | Hỗ trợ xác định domain và ranh giới port; không bắt buộc dùng đủ mọi tactical pattern |
| **Microservices** | Đơn vị triển khai và vận hành độc lập theo ranh giới nghiệp vụ | Mỗi microservice có thể dùng hexagonal; monolith cũng có thể dùng |

Không cần tranh cãi xem một sơ đồ có “hexagonal thuần” hay “clean thuần”. Mấu chốt là **quy tắc nghiệp vụ nằm đâu, dependency đi theo hướng nào và điều gì phải thay đổi khi một nền tảng bên ngoài đổi**.

### Khi nào kiến trúc lục giác đáng dùng?

Phù hợp khi ứng dụng có quy tắc nghiệp vụ đáng kể, nhiều kênh đầu vào, tích hợp ngoài, dự kiến thay DB hoặc cloud provider, yêu cầu test use case tách khỏi hạ tầng hoặc cần giảm coupling do framework.

Với một endpoint CRUD rất đơn giản, chỉ chuyển dữ liệu không có chính sách nghiệp vụ và vòng đời ngắn, một số abstraction có thể chưa mang lại lợi ích. Có thể bắt đầu với cấu trúc tối giản và trích xuất port khi xuất hiện phụ thuộc hoặc nhu cầu kiểm thử cụ thể. **Đừng tạo interface cho mọi class theo thói quen.**

## 14. Chuyển đổi từng bước từ ứng dụng framework-centric

Giả sử hệ thống cũ có controller gọi ORM repository, gọi SDK cloud và chứa kiểm tra nghiệp vụ. Việc chuyển đổi an toàn nên theo **một lát cắt nghiệp vụ**:

1. **Chọn một use case có giá trị rõ**, ví dụ tạo booking; liệt kê đường gọi và trường hợp lỗi hiện tại. Bổ sung phép kiểm tra hành vi cốt lõi trước khi thay đổi cấu trúc.
2. **Nhận diện quy tắc nghiệp vụ** đang nằm trong controller, repository hoặc stored procedure; xác định bất biến và ngữ nghĩa transaction thực tế.
3. **Tạo command và inbound port** cho hành vi nghiệp vụ; giữ lớp HTTP mỏng, chỉ chuyển đổi request và response.
4. **Rút quy tắc ra domain/application**. Định nghĩa outbound port theo nhu cầu thực của use case, không copy toàn bộ interface ORM.
5. **Bọc đường truy cập dữ liệu hiện tại bằng adapter**. Đảm bảo adapter mới giữ nguyên tính nguyên tử, lỗi và transaction của hệ cũ.
6. **Tách phần cấu hình và assembly** về composition root; bảo đảm core không còn import framework cụ thể.
7. **Đo và kiểm chứng**: chạy unit test cho use case, integration test cho adapter, test luồng API, thử tải và so sánh log/metrics.
8. **Xóa đường gọi cũ sau khi xác nhận** không còn consumer phụ thuộc; cập nhật sơ đồ, runbook, quyền truy cập và ADR.

Không cần đổi toàn bộ repository sang cấu trúc mới trong một lần. Trong giai đoạn chuyển đổi, adapter có thể gọi repository cũ phía ngoài; điều quan trọng là dependency từ application vào repository cụ thể được loại bỏ dần.

### Ví dụ tác động của thay đổi

| Sự thay đổi | Nếu business dính chặt công nghệ | Với port/adapter phù hợp |
| --- | --- | --- |
| REST chuyển sang gRPC | Phải sao chép quy tắc xử lý trong endpoint mới | Viết gRPC driving adapter, gọi inbound port |
| PostgreSQL driver / ORM thay đổi | Domain service phụ thuộc entity/annotation bị ảnh hưởng | Thay JDBC/JPA adapter, giữ contract và integration test |
| S3 chuyển sang lưu trữ khác | Mọi use case thao tác bucket/key và SDK cần sửa | Thay InvoiceArchive adapter nếu backend mới đáp ứng hợp đồng |
| Thêm scheduled job | Phải tái sử dụng controller hoặc chép code nghiệp vụ | Viết CLI/job adapter gọi use case |
| Đổi cách xác thực | Kiểm tra nghiệp vụ phụ thuộc JWT type phải thay | Ánh xạ thông tin xác thực sang ActorContext ở biên; giữ ủy quyền nghiệp vụ |
| Thay chiến lược đặt chỗ | Quy tắc và persistence phải được đánh giá lại | Sửa domain/use case và hợp đồng port khi ngữ nghĩa thay đổi |

Hàng cuối nhấn mạnh giới hạn quan trọng: **Hexagonal cô lập thay đổi cơ chế tốt hơn thay đổi quy tắc nghiệp vụ**. Nếu doanh nghiệp đổi từ booking theo ngày sang booking theo giờ hoặc yêu cầu giữ chỗ có hạn, domain, port và data model đều có thể phải đổi hợp lý.

## 15. Đánh đổi theo tư duy Well-Architected

Hexagonal Architecture **không phải** một chứng nhận tự động rằng ứng dụng đáng tin cậy, an toàn hay rẻ. Nó tạo cấu trúc để đội dễ kiểm tra, thay đổi và chịu trách nhiệm đối với những thuộc tính chất lượng đó.

| Trụ cột / mục tiêu | Lợi ích có thể có | Điều phải chủ động thực hiện |
| --- | --- | --- |
| **Operational Excellence** | Core dễ kiểm thử; adapter có owner; thay đổi độc lập hơn | CI/CD, logs/metrics/traces, runbook, kiểm soát cấu hình, quản lý phiên bản |
| **Security** | Tách business rule khỏi cơ chế IAM và mã hóa; giảm import SDK vào core | Phân quyền ở đúng lớp, quyền tối thiểu, dữ liệu nhạy cảm, kiểm thử chính sách giữa các adapter |
| **Reliability** | Hợp đồng port nêu rõ ngữ nghĩa lỗi và retry; dễ giả lập sự cố trong test | Transaction, outbox/idempotency, backup, DR, diễn tập và SLO |
| **Performance Efficiency** | Có thể thay adapter có bottleneck; lựa chọn backend theo đo đạc | Giữ đúng semantics, thử tải thật, connection pool, timeout, cache đúng chỗ |
| **Cost Optimization** | Giảm chi phí chuyển đổi khi công nghệ thay; tiết kiệm thời gian test | Cân nhắc chi phí tạo interface/adapter, công sức vận hành và ngân sách cloud |
| **Sustainability** | Có thể thay giải pháp lưu trữ/compute để giảm tài nguyên không cần thiết | Đo hiệu quả thực tế, tránh tạo tầng và xử lý lặp dư thừa |

Điểm kiểm tra kiến trúc là: **một quyết định cloud giúp đạt yêu cầu nào, port mô tả hợp đồng gì, adapter có chứng minh được hợp đồng đó và chi phí vận hành lâu dài là bao nhiêu?**

## 16. Các sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Xem hexagon là sơ đồ sáu service | Phân tách triển khai không có căn cứ | Hiểu lục giác là ẩn dụ ranh giới ứng dụng; chọn số process theo yêu cầu |
| Interface nằm ở infrastructure, core phải import SDK DTO | Hướng phụ thuộc vẫn sai | Chuyển interface vào application, dùng kiểu dữ liệu phù hợp ngôn ngữ nghiệp vụ |
| Port sao chép tất cả method của ORM/cloud SDK | Thay API nhưng coupling không giảm | Thiết kế theo thao tác nghiệp vụ và ngữ nghĩa của use case |
| Domain object chứa annotation web, ORM hoặc cloud client | Domain khó test và khó đổi hạ tầng | Dùng mapper ở adapter; chỉ chấp nhận thư viện trong core khi đã chủ động đánh đổi |
| Mỗi method tạo một interface và một lớp chuyển tiếp | Thêm code nhưng không tạo ranh giới đáng giá | Ưu tiên port ở ranh giới thay đổi hoặc kiểm thử thực sự |
| Dồn mọi logic vào adapter | REST và consumer xử lý nghiệp vụ khác nhau | Đưa chính sách chung vào domain/application |
| Kiểm tra phòng trống rồi INSERT hai bước | Race condition, tạo booking trùng | Hợp đồng ghi nguyên tử và DB constraint/transaction đã kiểm chứng |
| Coi mock/fake là bằng chứng tương thích database | Không phát hiện lỗi concurrency, driver, schema | Contract và integration test trên backend thật |
| Dùng transaction DB để suy ra queue cũng atomic | Mất hoặc lặp sự kiện | Transactional outbox khi phù hợp, idempotent consumer |
| Thay cloud chỉ bằng đổi implementation | Bỏ qua IAM, consistency, giới hạn, chi phí egress | Đánh giá capability và SLA; ghi ngoại lệ/ADR khi cần |
| Đưa JWT, HTTP status, exception của SDK vào domain | Nghiệp vụ khó tái sử dụng qua kênh khác | Chuyển đổi tại adapter; giữ ngữ nghĩa ứng dụng độc lập |
| Đẩy mọi concern qua port cho “thuần kiến trúc” | Mất khả năng quan sát đơn giản, tăng ceremony | Dùng instrumentation ở biên; thêm port chỉ khi mang ý nghĩa nghiệp vụ |

## 17. Bài tập thực hành

Một nền tảng thương mại điện tử Java đang lưu hóa đơn trong object storage của một nhà cung cấp cloud, thanh toán qua API đối tác và lưu đơn hàng bằng PostgreSQL. Hiện tại **OrderController** gọi cả ba SDK, đồng thời quyết định giảm tồn kho và chuyển trạng thái đơn hàng. Doanh nghiệp muốn thêm consumer Kafka để nhận đơn từ đối tác và xem xét đổi dịch vụ lưu trữ hóa đơn.

Hãy làm các việc sau:

1. Vẽ **một sơ đồ hexagonal** với domain, application use cases, inbound/outbound ports, các adapter HTTP, Kafka, PostgreSQL, thanh toán và lưu trữ hóa đơn.
2. Chọn **ít nhất hai bất biến nghiệp vụ** cần được bảo vệ trong domain/application, và một bất biến cần cơ chế nguyên tử ở database.
3. Thiết kế chữ ký cho **CreateOrder** (inbound), **OrderStore**, **PaymentGateway** và **InvoiceArchive** (outbound) mà không dùng DTO hay kiểu SDK.
4. Chỉ ra bên nào chịu trách nhiệm ánh xạ JSON/Kafka message, xác minh callback thanh toán, lựa chọn IAM role, timeout/retry và chống sự kiện trùng.
5. Viết một unit test dùng fake OrderStore và một integration test có thể phát hiện race condition của inventory/đơn hàng.
6. So sánh **hai giải pháp**: giữ controller hiện tại và thêm nhánh Kafka, hoặc trích xuất use case/port rồi viết adapter Kafka. Đánh giá chi phí thay đổi, test, độ tin cậy và rủi ro chuyển đổi.
7. Viết một **ADR ngắn** về việc có nên dùng port InvoiceArchive trước khi đổi object storage; nêu rõ contract, giả định, trường hợp phải sửa lại và chỉ số đánh giá.

### Gợi ý chấm bài

Phương án tốt cần cho thấy rõ **mũi tên phụ thuộc vào core**, input port có thể được gọi từ cả HTTP lẫn Kafka, outbound adapter triển khai hợp đồng có ngữ nghĩa thực tế, và core không biết chi tiết SDK. Bài làm phải giải thích được giao dịch nào cần nguyên tử trong database, điều gì có thể trở thành bất đồng bộ, và cách xử lý khi payment hoặc queue trả kết quả không chắc chắn.

Một sơ đồ nhiều hộp chưa đủ: cần giải thích *vì sao* ranh giới tồn tại, ai sở hữu, kiểm tra ra sao và tác động tới Well-Architected.

## 18. Checklist đánh giá một thiết kế hexagonal

Trước khi chấp nhận thiết kế, kiểm tra:

- [ ] **Domain** biểu diễn quy tắc nghiệp vụ và không import framework, transport hoặc cloud SDK.
- [ ] **Application use case** có đầu vào/đầu ra rõ, quản lý luồng nghiệp vụ và chỉ phụ thuộc các port cần thiết.
- [ ] **Inbound adapters** chuyển đổi giao thức, xác thực đầu vào và không lặp lại quy tắc nghiệp vụ.
- [ ] **Outbound ports** nêu ngữ nghĩa về transaction, consistency, lỗi, timeout và kết quả, không sao chép API nhà cung cấp.
- [ ] **Outbound adapters** triển khai hợp đồng với kỹ thuật cụ thể và mapping lỗi đúng.
- [ ] **Composition root** lắp implementation và kiểm soát cấu hình theo môi trường.
- [ ] **Concurrency/idempotency** được kiểm chứng ở nơi lưu trạng thái thật; fake test không được dùng thay integration test.
- [ ] **Bảo mật** có kiểm soát danh tính, quyền trên tài nguyên và cloud IAM; mọi adapter tuân thủ chính sách bắt buộc.
- [ ] **Vận hành** có telemetry, logging an toàn, cảnh báo, backup và DR theo yêu cầu được phê duyệt.
- [ ] **Mỗi abstraction có lý do** về kiểm thử, thay đổi công nghệ hoặc kiểm soát ranh giới; tránh interface và mapper dư thừa.
- [ ] **ADR** ghi lựa chọn, đánh đổi và điều kiện xem lại khi yêu cầu hoặc nền tảng thay đổi.

**Ghi nhớ:** Kiến trúc lục giác giúp giữ phần **chính sách nghiệp vụ** ổn định trước những thay đổi ở **cơ chế giao tiếp và hạ tầng**. Sức mạnh nằm ở hợp đồng port được thiết kế theo ngữ nghĩa thực, hướng phụ thuộc đi vào core và adapter có thể kiểm thử độc lập. Trên cloud, hãy kết hợp mô hình này với các yêu cầu rõ về nhất quán, bảo mật, hiệu năng, vận hành và chi phí để có kiến trúc linh hoạt mà vẫn đáng tin cậy.
