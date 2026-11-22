# Phạm vi giao dịch cần có để giữ khóa trong JPA

Khi nhiều người dùng cùng đặt chỗ, trừ tồn kho, duyệt một khoản thanh toán hoặc cập nhật một tài nguyên có giới hạn, chỉ đọc dữ liệu rồi quyết định trong Java có thể chưa đủ an toàn. Hai transaction có thể cùng thấy “còn chỗ”, cùng quyết định giữ chỗ và ghi kết quả cạnh tranh. Một cách kiểm soát là **khóa bi quan (pessimistic locking)**: yêu cầu cơ sở dữ liệu đặt khóa lên bản ghi/tài nguyên thích hợp trước khi đưa ra quyết định cập nhật.

Trong Jakarta Persistence (JPA), một thao tác điển hình:

~~~java
Seat seat = em.find(
    Seat.class,
    seatId,
    LockModeType.PESSIMISTIC_WRITE);
~~~

Điều dễ hiểu sai là cho rằng “chỉ cần gọi `find()` với lock mode thì khóa tồn tại cho đến khi Java không còn dùng entity”. **Không phải vậy.** Khóa do database quản lý, gắn với **transaction thực sự đang hoạt động**, và thường được giữ cho tới khi transaction đó **commit hoặc rollback**, theo ngữ nghĩa lock/DBMS tương ứng. Một đối tượng Java vẫn tồn tại sau commit không có nghĩa bản ghi database vẫn bị khóa.

Ngược lại, việc method Java return, gọi `em.flush()`, `em.clear()` hoặc `em.detach()` cũng **không mặc nhiên giải phóng các khóa database đang thuộc transaction chưa kết thúc**.

~~~text
Service bắt đầu transaction
      |
      v
BEGIN TRANSACTION
      |
      +--> SELECT Seat ... FOR UPDATE
      |          |
      |          +--> Database giữ khóa trong transaction
      |
      +--> Kiểm tra Seat AVAILABLE?
      |
      +--> Đổi Seat thành RESERVED
      |
      +--> INSERT Booking
      |
      v
COMMIT hoặc ROLLBACK
      |
      +--> Khóa được giải phóng theo semantics của DBMS
~~~

**Mục tiêu bài học:** hiểu chính xác transaction boundary nào cần bao trùm thời gian giữ khóa, cách gọi lock qua JPA, cách tránh những ranh giới transaction sai trong Spring/JTA, cách xử lý lock wait/deadlock/timeout và cách kiểm thử bằng hai transaction thật.

## 1. Phạm vi transaction mới là trung tâm của pessimistic locking

Có ba thứ khác nhau:

1. **Java scope:** thân method hoặc khối `try` trong source code.
2. **Persistence context:** tập entity được `EntityManager` quản lý, cùng first-level cache/dirty checking.
3. **Database transaction:** phạm vi BEGIN–COMMIT/ROLLBACK nơi database kiểm soát lock, visibility và atomicity.

Chúng có thể trùng nhau trong một ví dụ đơn giản, nhưng **không đồng nghĩa**.

Ví dụ:

~~~java
@Transactional
public void reserveSeat(long seatId) {
    Seat seat = em.find(
        Seat.class,
        seatId,
        LockModeType.PESSIMISTIC_WRITE);

    seat.reserve();
}
~~~

Với Spring transaction proxy cấu hình đúng, method body nằm trong transaction do Spring quản lý. Khi lời gọi được thực hiện qua proxy:

~~~text
Spring Transaction Interceptor
    BEGIN/participate transaction
         |
         v
    reserveSeat() body
       find(..., PESSIMISTIC_WRITE)
       seat.reserve()
         |
         v
    return from method body
         |
         v
    flush/commit transaction
         |
         v
    proxy trả kết quả cho caller
~~~

Đối với transaction mới do interceptor sở hữu, khóa có thể tiếp tục tồn tại **sau dòng return trong thân method**, cho đến khi interceptor thực sự hoàn thành commit/rollback.

Nếu method tham gia một **outer transaction** đã có, khóa có thể tiếp tục được giữ **sau khi method con return**, cho đến khi outer transaction kết thúc. Đó là điều thường gây bất ngờ khi code có nhiều service/repository layers.

## 2. Khóa bi quan thực sự là khóa ở đâu?

JPA đưa ra một giao diện trừu tượng:

~~~java
LockModeType.PESSIMISTIC_READ
LockModeType.PESSIMISTIC_WRITE
LockModeType.PESSIMISTIC_FORCE_INCREMENT
~~~

Provider chuyển yêu cầu thành cơ chế database thích hợp, ví dụ một dạng `SELECT ... FOR UPDATE`, `FOR SHARE` hoặc cú pháp locking riêng theo dialect/driver.

### Sơ đồ tầng

~~~text
Java code
   em.find(Seat.class, id, PESSIMISTIC_WRITE)
                 |
                 v
JPA provider / persistence context
   - Xác định entity và version
   - Yêu cầu lock phù hợp
                 |
                 v
JDBC / transaction-bound connection
                 |
                 v
Database engine
   - Điều phối row/key/range/table locks theo implementation
   - Chờ hoặc từ chối transaction cạnh tranh
   - Giải phóng lock theo kết thúc transaction hoặc rules đặc biệt
~~~

### Khóa có phải một object Java không?

Không. Một Java reference:

~~~java
Seat seat = em.find(...);
~~~

chỉ là object được quản lý trong persistence context. Khóa được **database** điều phối, không phụ thuộc vào việc còn một biến local trỏ đến `seat` hay không.

### Có chắc chỉ khóa đúng một row không?

Không thể hứa điều đó cho mọi DBMS/query. Cơ sở dữ liệu có thể dùng row lock, key-range lock, page/table lock, index locking hoặc escalation tùy engine, isolation, execution plan và loại câu SQL.

JPA mô tả **ý nghĩa concurrency**, không quy định chính xác mọi lock vật lý database phải lấy và giữ.

## 3. Khi nào bắt đầu giữ khóa?

Một kịch bản thường gặp:

~~~text
T0: tx.begin()
T1: em.find(Seat, 10, PESSIMISTIC_WRITE)
T2: Provider thực hiện locking SQL
T3: Database cấp khóa theo chế độ tương ứng
T4: Java code kiểm tra và cập nhật
T5: tx.commit()
T6: Database giải phóng lock
~~~

Trong ví dụ này, khóa chỉ bắt đầu bảo vệ row **khi database đã thực thi yêu cầu locking và cấp khóa**, không phải từ thời điểm Java chỉ khai báo một đối tượng `LockModeType`.

### Lock acquisition có thể phải chờ

Nếu transaction khác đang giữ lock xung đột:

~~~text
Transaction A                      Transaction B
--------------------------------   -----------------------------------
BEGIN                              BEGIN
Lock Seat#10 thành công
                                   Yêu cầu lock Seat#10
                                   -> WAIT
Thay đổi Seat
COMMIT
                                   DB cấp khóa cho B
                                   B đọc/kiểm tra state mới theo DB rules
~~~

Tùy DBMS/isolation, B có thể chờ, timeout, gặp deadlock hoặc thất bại vì conflict. Không cam kết B luôn chờ cho đến khi A commit.

## 4. Khóa thường được giữ đến khi transaction kết thúc

Với database transactional và pessimistic lock ở mức ghi phù hợp, quy tắc thực hành là:

> **Đảm bảo toàn bộ giai đoạn đọc dữ liệu, kiểm tra điều kiện nghiệp vụ, sửa dữ liệu và ghi các entity liên quan nằm trong một transaction còn hoạt động.** Không tách thành nhiều transaction nếu quyết định cần dựa trên một trạng thái đã được khóa.

Ví dụ đúng:

~~~text
BEGIN
  SELECT seat ... FOR UPDATE
  IF seat.available
      UPDATE seat = RESERVED
      INSERT booking
  ELSE
      báo đã có người đặt
COMMIT
~~~

Ví dụ sai:

~~~text
Transaction 1:
  SELECT seat ... FOR UPDATE
COMMIT  <-- Khóa được giải phóng.

Ứng dụng tính toán rất lâu.

Transaction 2:
  UPDATE seat = RESERVED
COMMIT
~~~

Giữa hai transaction, request khác có thể đã đặt chỗ.

### Lock không là một token được mang sang transaction sau

Java entity có thể vẫn chứa `status=AVAILABLE` trong RAM, nhưng lock của transaction trước đã mất. Dùng trạng thái ấy để quyết định ở transaction sau mà không đọc/khóa/kiểm tra lại tạo ra race condition.

## 5. TransactionRequiredException khi gọi pessimistic lock ngoài transaction

JPA yêu cầu một transaction phù hợp đang hoạt động cho thao tác pessimistic lock.

~~~java
EntityManager em = emf.createEntityManager();

// Không begin transaction.
Seat seat = em.find(
    Seat.class,
    seatId,
    LockModeType.PESSIMISTIC_WRITE);
~~~

Với một `RESOURCE_LOCAL` EntityManager và không có transaction active, thao tác yêu cầu pessimistic lock có thể ném `jakarta.persistence.TransactionRequiredException` theo hợp đồng JPA.

Tương tự:

~~~java
em.lock(seat, LockModeType.PESSIMISTIC_WRITE);
~~~

hoặc:

~~~java
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);
query.getResultList();
~~~

cần transaction phù hợp ở thời điểm thực hiện lock.

### Tại sao SELECT bình thường có thể chạy ngoài transaction nhưng lock thì không?

Một SELECT chỉ đọc có thể được provider thực thi theo cơ chế connection/autocommit của môi trường. Nhưng pessimistic lock cần một **transaction đủ dài để bảo vệ chuỗi thao tác**. Nếu database autocommit ngay sau SELECT, lock có thể được nhả trước khi code Java kiểm tra và cập nhật, khiến mục tiêu bảo vệ mất hiệu lực.

Vì vậy, JPA không coi “cứ thực hiện SELECT FOR UPDATE ngoài transaction và hy vọng connection giữ lock” là một giải pháp portable.

## 6. Ba lock mode pessimistic chính

| Lock mode | Ý nghĩa khái quát | Cần lưu ý |
| --- | --- | --- |
| `PESSIMISTIC_READ` | Yêu cầu ngăn một số thay đổi xung đột trong lúc đọc | Không phải DBMS nào cũng có shared row lock giống nhau |
| `PESSIMISTIC_WRITE` | Yêu cầu khóa phục vụ cập nhật độc quyền/xung đột ghi | Thường dùng cho read-check-update |
| `PESSIMISTIC_FORCE_INCREMENT` | Khóa bi quan và tăng version của entity versioned | Tạo thêm write/version conflict theo contract |

### PESSIMISTIC_READ

Thích hợp khi transaction cần đọc một trạng thái mà không muốn một transaction khác sửa xung đột trong phạm vi đang đọc.

~~~java
Seat seat = em.find(
    Seat.class,
    seatId,
    LockModeType.PESSIMISTIC_READ);
~~~

DBMS/provider có thể dùng shared lock nếu hỗ trợ, hoặc biện pháp mạnh hơn. Không suy ra hai readers luôn được phép cùng lock trong mọi provider/DBMS.

### PESSIMISTIC_WRITE

Thích hợp khi transaction sẽ **quyết định rồi cập nhật** dựa trên state của row:

~~~java
Seat seat = em.find(
    Seat.class,
    seatId,
    LockModeType.PESSIMISTIC_WRITE);
seat.reserveFor(userId);
~~~

### PESSIMISTIC_FORCE_INCREMENT

Khi entity có `@Version` và business cần làm version tiến lên trong transaction có khóa, có thể cân nhắc:

~~~java
Seat seat = em.find(
    Seat.class,
    seatId,
    LockModeType.PESSIMISTIC_FORCE_INCREMENT);
~~~

Đây không phải yêu cầu chung cho mọi update; tăng version có thể tạo xung đột thêm và phải được thiết kế theo aggregate/concurrency policy.

## 7. API để yêu cầu khóa trong JPA

JPA hỗ trợ nhiều cách.

### find() với LockModeType

~~~java
Seat seat = em.find(
    Seat.class,
    seatId,
    LockModeType.PESSIMISTIC_WRITE);
~~~

Đây là cách thuận tiện khi biết primary key.

### lock() trên managed entity

~~~java
Seat seat = em.find(Seat.class, seatId);

em.lock(
    seat,
    LockModeType.PESSIMISTIC_WRITE);
~~~

Phải hiểu khoảng thời gian **giữa find không lock và lock**: transaction khác có thể đã thay đổi row, và provider có thể cần xác thực state/version tương ứng khi lấy lock. Nếu nghiệp vụ đòi hỏi state được bảo vệ ngay từ lần đọc đầu tiên, thường nên yêu cầu lock **ngay tại find/query**.

### TypedQuery.setLockMode()

~~~java
List<Seat> seats = em.createQuery(
        "SELECT s FROM Seat s " +
        "WHERE s.eventId = :eventId " +
        "AND s.status = :status " +
        "ORDER BY s.id",
        Seat.class)
    .setParameter("eventId", eventId)
    .setParameter("status", SeatStatus.AVAILABLE)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .setMaxResults(10)
    .getResultList();
~~~

Đây là một **JPA query** áp lock mode cho kết quả entity. Cách database khóa các row phù hợp, phạm vi lock và behavior khi pagination/JOIN phụ thuộc provider/dialect.

### Không áp lock mode tùy tiện lên bulk update hoặc scalar projection

`setLockMode()` có ngữ nghĩa với các query phù hợp trả entity; không phải cách “bọc” bất cứ native SQL, aggregate hoặc bulk UPDATE nào thành một transaction khóa tự động. Với scalar query hoặc native query, tính hỗ trợ và cách SQL lock được tạo cần kiểm chứng theo JPA/provider/DBMS.

## 8. Ví dụ xuyên suốt: giữ ghế cho một sự kiện

Ta xét một bảng sự kiện có các ghế đánh số:

~~~text
events
  id

event_seats
  id
  tenant_id
  event_id
  seat_code
  status (AVAILABLE / RESERVED)
  reserved_by_user_id
  version

bookings
  id
  tenant_id
  event_seat_id
  user_id
  status
~~~

Quy tắc nghiệp vụ:

1. Một ghế không được đặt bởi hai người cùng lúc.
2. Chỉ đặt ghế trong tenant/event đang được phép.
3. Cập nhật trạng thái ghế và tạo booking phải commit/rollback **cùng transaction**.
4. Không giữ lock trong lúc người dùng nhập thông tin thanh toán dài phút.

### Tình huống race

~~~text
Ghế A01: AVAILABLE

Request A                         Request B
--------------------------------  --------------------------------
SELECT ghế AVAILABLE               SELECT ghế AVAILABLE
quyết định giữ chỗ                 quyết định giữ chỗ
UPDATE RESERVED by user A          UPDATE RESERVED by user B
INSERT booking A                   INSERT booking B
COMMIT                             COMMIT
~~~

Nếu thiếu protocol concurrency hoặc database constraint, trạng thái cuối và booking records có thể không phù hợp invariant.

### Kỳ vọng với PESSIMISTIC_WRITE

~~~text
Request A                         Request B
--------------------------------  --------------------------------
BEGIN TX_A                        BEGIN TX_B
Lock A01 thành công                Lock A01 -> WAIT
Kiểm tra AVAILABLE
Đổi RESERVED by A
Tạo Booking A
COMMIT TX_A
                                  Lock A01 được cấp sau khi A kết thúc
                                  Kiểm tra ghế đã RESERVED
                                  Từ chối đặt lại
                                  ROLLBACK TX_B
~~~

**Điểm quan trọng:** B kiểm tra lại trạng thái ghế **sau khi đã lấy lock của chính transaction B**, không dùng trạng thái cũ từ một query/cache/HTTP request trước đó.

## 9. DDL minh họa và ràng buộc database

Ví dụ DDL theo PostgreSQL:

~~~sql
CREATE TABLE event_seats (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    event_id BIGINT NOT NULL,
    seat_code VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL,
    reserved_by_user_id BIGINT,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uq_event_seat
        UNIQUE (tenant_id, event_id, seat_code),
    CONSTRAINT ck_seat_status
        CHECK (status IN ('AVAILABLE', 'RESERVED')),
    CONSTRAINT ck_reserved_user
        CHECK (
            (status = 'AVAILABLE'
                AND reserved_by_user_id IS NULL)
            OR
            (status = 'RESERVED'
                AND reserved_by_user_id IS NOT NULL)
        )
);

CREATE TABLE bookings (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    event_seat_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_booking_seat
        FOREIGN KEY (event_seat_id) REFERENCES event_seats(id)
);
~~~

### Ràng buộc gì còn thiếu?

Nếu business cho phép nhiều lịch sử booking của một seat, cần một constraint trên **booking đang active** (ví dụ partial unique index theo DBMS) hoặc một mô hình booking status bảo đảm chỉ có một active reservation. Trong DDL tối giản này, nguồn quyết định đang là `event_seats.status` được cập nhật dưới lock.

Database constraints cung cấp **lớp bảo vệ cuối**; không nên giả định lock code luôn được dùng đúng bởi tất cả các writers (legacy SQL, batch job, procedure, service khác).

### Vì sao vẫn thêm @Version?

Khóa bi quan và optimistic version có thể cùng tồn tại. Version giúp phát hiện các đường cập nhật khác có sử dụng entity versioned khi không lấy khóa từ sớm và hỗ trợ cập nhật form cũ theo precondition. Không phải mọi native SQL tự tăng version, nên cần thống nhất protocol ở tất cả các writers.

## 10. Entity Seat

~~~java
package com.example.booking;

public enum SeatStatus {
    AVAILABLE,
    RESERVED
}
~~~

~~~java
package com.example.booking;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "event_seats")
public class Seat {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "event_id", nullable = false)
    private Long eventId;

    @Column(name = "seat_code", nullable = false)
    private String seatCode;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private SeatStatus status;

    @Column(name = "reserved_by_user_id")
    private Long reservedByUserId;

    @Version
    @Column(nullable = false)
    private Long version;

    protected Seat() {
    }

    public Long getId() {
        return id;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public Long getEventId() {
        return eventId;
    }

    public SeatStatus getStatus() {
        return status;
    }

    public Long getVersion() {
        return version;
    }

    public void reserveFor(long userId) {
        if (userId <= 0) {
            throw new IllegalArgumentException(
                "userId phải dương");
        }

        if (status != SeatStatus.AVAILABLE) {
            throw new SeatUnavailableException(
                "Ghế không còn trống");
        }

        status = SeatStatus.RESERVED;
        reservedByUserId = userId;
    }
}
~~~

Exception nghiệp vụ:

~~~java
package com.example.booking;

public class SeatUnavailableException
        extends RuntimeException {

    public SeatUnavailableException(String message) {
        super(message);
    }
}
~~~

### Tại sao reserveFor() cần kiểm tra lại status?

Lock không tự biết một ghế đã được RESERVED là trường hợp nghiệp vụ không hợp lệ. Lock chỉ điều phối truy cập cạnh tranh; sau khi đã lấy lock, service/domain **vẫn phải đọc và kiểm tra trạng thái mới nhất khả dụng trong transaction**.

Một transaction khác có thể đã đặt ghế trước đó và commit. Khi transaction của bạn lấy được lock, state không còn AVAILABLE.

## 11. Entity Booking

~~~java
package com.example.booking;

public enum BookingStatus {
    CONFIRMED,
    CANCELLED
}
~~~

~~~java
package com.example.booking;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "bookings")
public class Booking {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "event_seat_id", nullable = false)
    private Seat seat;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private BookingStatus status;

    protected Booking() {
    }

    public Booking(long tenantId, Seat seat, long userId) {
        this.tenantId = tenantId;
        this.seat = java.util.Objects.requireNonNull(seat);
        this.userId = userId;
        this.status = BookingStatus.CONFIRMED;
    }

    public Long getId() {
        return id;
    }
}
~~~

Trong ví dụ, Seat và Booking dùng cùng database transaction. Mapping `@ManyToOne(fetch=LAZY)` không quyết định loại lock của Seat: khóa được yêu cầu tường minh ở service qua `LockModeType.PESSIMISTIC_WRITE`.

### Những điểm ngoài phạm vi ví dụ

Một hệ thống bán vé thực còn cần giữ chỗ có hạn, thanh toán, hủy booking, thu hồi ghế khi timeout, idempotency key, kiểm soát quyền và dữ liệu lịch sử. **Không kéo dài database lock suốt quá trình thanh toán nhiều phút** để thay cho một workflow reservation có trạng thái.

## 12. RESOURCE_LOCAL: ví dụ transaction bao trùm lock và update

Với persistence unit `RESOURCE_LOCAL`:

~~~java
package com.example.booking;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.LockModeType;
import java.util.Objects;

public class BookingService {

    private final EntityManagerFactory emf;

    public BookingService(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public Long reserve(
            long tenantId,
            long eventId,
            long seatId,
            long userId) {

        EntityManager em = emf.createEntityManager();
        EntityTransaction tx = em.getTransaction();

        try {
            tx.begin();

            Seat seat = em.find(
                Seat.class,
                seatId,
                LockModeType.PESSIMISTIC_WRITE);

            if (seat == null
                    || !Objects.equals(
                        seat.getTenantId(), tenantId)
                    || !Objects.equals(
                        seat.getEventId(), eventId)) {
                throw new IllegalArgumentException(
                    "Không tìm thấy ghế trong phạm vi yêu cầu");
            }

            // Trạng thái này được kiểm tra khi đang giữ khóa.
            seat.reserveFor(userId);

            Booking booking =
                new Booking(tenantId, seat, userId);
            em.persist(booking);

            // Gửi SQL, phát hiện lỗi sớm khi có thể.
            em.flush();

            tx.commit();
            return booking.getId();

        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                try {
                    tx.rollback();
                } catch (RuntimeException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
            }
            throw ex;
        } finally {
            em.close();
        }
    }
}
~~~

### Ranh giới đáng chú ý

~~~text
tx.begin()
  |
  v
em.find(... PESSIMISTIC_WRITE)
  |
  +-- DB cấp khóa cho Seat
  |
  v
validate tenant/event/status
  |
  v
seat.reserveFor(...)
  |
  v
em.persist(booking)
  |
  v
em.flush()
  |
  v
tx.commit() / tx.rollback()
  |
  +-- DB hoàn tất transaction và xử lý giải phóng lock
~~~

### Tại sao không mở transaction sau khi find()?

Vì thao tác `find(..., PESSIMISTIC_WRITE)` đã yêu cầu lock. Một transaction phù hợp phải hoạt động **trước khi** gọi lock và kéo dài qua kiểm tra/cập nhật liên quan.

### Tại sao return sau commit?

Method chỉ trả booking ID khi transaction đã commit thành công. `flush()` gửi SQL nhưng không bảo đảm commit, và một số lỗi có thể xuất hiện ở commit.

### Rollback có giải phóng lock không?

Theo mô hình transactional locking thông thường, rollback kết thúc transaction và giải phóng các transaction-held locks. Từng engine có những tài nguyên/loại lock và quy tắc riêng, nhưng ứng dụng phải **kết thúc transaction lỗi**, không để nó treo vì chỉ log exception.

## 13. Mô hình sai: đọc với lock trong transaction rồi ghi ở transaction khác

Giả sử repository:

~~~java
@Transactional(readOnly = true)
public Seat loadAndLock(long id) {
    return em.find(
        Seat.class,
        id,
        LockModeType.PESSIMISTIC_WRITE);
}
~~~

Service:

~~~java
public void reserve(long id, long userId) {
    Seat seat = repository.loadAndLock(id);

    // Transaction repository đã kết thúc.
    // Khóa có thể đã được nhả.

    if (seat.getStatus() == SeatStatus.AVAILABLE) {
        repository.updateSeat(id, userId);
    }
}
~~~

Đây là một lỗi **transaction boundary**:

1. Repository transaction nạp/khóa Seat.
2. Repository method return; transaction của nó kết thúc nếu không có outer transaction.
3. Service kiểm tra trạng thái ghế khi khóa không còn được giữ.
4. Repository khác bắt đầu transaction mới để UPDATE.

Giữa bước 2 và 4, transaction cạnh tranh có thể cập nhật ghế.

### Cách sửa

Đặt một transaction bao trùm **read-lock, validate, update, persist Booking và commit** ở tầng application service.

Việc repository có `@Transactional` không tự bảo đảm toàn bộ workflow của caller được bảo vệ.

## 14. Spring: transaction boundary ở service

Trong Spring Data JPA, một service có thể:

~~~java
package com.example.booking;

import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import jakarta.persistence.PersistenceContext;
import java.util.Objects;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SpringBookingService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public Long reserve(
            long tenantId,
            long eventId,
            long seatId,
            long userId) {

        Seat seat = em.find(
            Seat.class,
            seatId,
            LockModeType.PESSIMISTIC_WRITE);

        if (seat == null
                || !Objects.equals(
                    seat.getTenantId(), tenantId)
                || !Objects.equals(
                    seat.getEventId(), eventId)) {
            throw new IllegalArgumentException(
                "Không tìm thấy ghế trong tenant/event");
        }

        seat.reserveFor(userId);

        Booking booking =
            new Booking(tenantId, seat, userId);
        em.persist(booking);

        // Không bắt buộc nếu commit sẽ flush,
        // nhưng có thể phát hiện lỗi trong method.
        em.flush();

        return booking.getId();
    }
}
~~~

Ở đây `@Transactional` là `org.springframework.transaction.annotation.Transactional`. Khi method được gọi qua cơ chế transaction proxy phù hợp:

- Spring tạo/tham gia transaction theo propagation.
- Transaction-bound EntityManager tham gia resource đang được quản lý.
- Lock và các thay đổi thuộc phạm vi transaction đó.
- Nếu Spring **tạo transaction mới cho method**, transaction sẽ commit sau khi method body return và trước khi proxy trả kết quả.
- Nếu method tham gia **outer transaction**, việc commit có thể xảy ra lâu hơn, tại outer boundary.

### Không gọi em.getTransaction() trong service này

Với EntityManager do Spring quản lý bằng transaction manager:

~~~java
em.getTransaction().commit();
~~~

không phải cách đúng để kết thúc transaction. Để Spring transaction manager làm chủ commit/rollback.

### Rollback rule

Spring mặc định rollback với unchecked exception (và `Error`), còn checked exception cần rule phù hợp như `rollbackFor` nếu muốn rollback. Khi service ném một checked business exception nhưng transaction manager lại commit, khóa sẽ được nhả sau commit và thay đổi trước đó có thể đã được xác nhận — điều đó thường không phải ý đồ.

**Thiết kế exception propagation cùng transaction boundary.**

## 15. Method return không nhất thiết làm lock được nhả

Xem luồng:

~~~java
@Transactional
public void checkout(long seatId) {
    bookingService.reserveSeat(seatId);
    paymentRecordRepository.persist(...);
    auditRepository.persist(...);
}
~~~

Và:

~~~java
@Transactional
public void reserveSeat(long seatId) {
    em.find(
        Seat.class,
        seatId,
        LockModeType.PESSIMISTIC_WRITE);

    // Đổi status...
}
~~~

Nếu hai service methods dùng cùng transaction manager/resource và propagation mặc định `REQUIRED`:

~~~text
checkout BEGIN TX
    |
    +-- reserveSeat() JOIN TX
    |     -> lock Seat
    |     -> method return
    |     -> TX vẫn mở, lock vẫn có thể đang được giữ
    |
    +-- paymentRecordRepository...
    |
    +-- auditRepository...
    |
checkout COMMIT TX
    -> lock được giải phóng
~~~

**Đây là lý do không nên đặt các thao tác chậm/không cần thiết sau khi lấy khóa** trong cùng outer transaction.

## 16. @Transactional self-invocation: annotation có thể không được áp dụng

Ví dụ:

~~~java
@Service
public class BookingFacade {

    public void checkout(long seatId) {
        this.reserveInternal(seatId);
    }

    @Transactional
    public void reserveInternal(long seatId) {
        em.find(
            Seat.class,
            seatId,
            LockModeType.PESSIMISTIC_WRITE);
    }
}
~~~

Trong mô hình Spring proxy-based AOP thông dụng, `this.reserveInternal()` là **lời gọi nội bộ cùng object**, không đi qua transaction proxy. Annotation ở method con có thể không được áp dụng như mong đợi.

Kết quả có thể là:

- Không có active transaction khi gọi pessimistic lock.
- Nhận `TransactionRequiredException`.
- Hoặc vẫn có outer transaction từ một lời gọi khác, nhưng không phải nhờ annotation ở method nội bộ này.

### Cách khắc phục

Đặt `@Transactional` trên **entrypoint được gọi qua Spring proxy**, hoặc tách transactional service thành bean được inject và gọi qua proxy phù hợp. Không đánh giá transaction boundary chỉ bằng cách nhìn một annotation mà không biết đường gọi thực tế.

## 17. Propagation.REQUIRED giữ khóa đến outer boundary

`Propagation.REQUIRED` của Spring:

- Nếu chưa có transaction: mở transaction mới.
- Nếu đã có transaction: tham gia transaction hiện tại.

Ví dụ:

~~~text
Outer service A @Transactional(REQUIRED)
  BEGIN TX_1
      |
      +-- service B @Transactional(REQUIRED)
      |       PESSIMISTIC_WRITE Seat
      |       return B
      |
      +-- service C ghi thêm dữ liệu
      |
  COMMIT TX_1
~~~

Khóa được yêu cầu ở B **không tự nhả khi B return**, bởi transaction thực của B là TX_1.

### Định nghĩa “lock scope” theo transaction thực

Không hỏi chỉ:

> Method nào có `@Transactional`?

Hãy hỏi:

> Ở thời điểm gọi lock, **physical database transaction nào** đang active, và **nơi nào thực sự commit/rollback** transaction ấy?

Đây mới là cách xác định thời gian khóa.

## 18. Propagation.REQUIRES_NEW tạo transaction độc lập

Một service:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void reserveSeat(...) {
    // Lock Seat và UPDATE.
}
~~~

thường tạm ngưng outer transaction và bắt đầu một transaction vật lý mới khi transaction manager hỗ trợ.

~~~text
Outer TX_A
   |
   +-- Inner TX_B (REQUIRES_NEW)
   |      Lock Seat
   |      Update Seat
   |      COMMIT TX_B
   |      -> lock của TX_B được nhả
   |
   +-- Outer sau đó ROLLBACK TX_A
~~~

### Khi nào nguy hiểm?

Nếu nghiệp vụ muốn **Seat reservation và Order/payment record cùng commit hoặc rollback**, TX_B commit độc lập có thể tạo trạng thái không nhất quán khi TX_A rollback.

### Khi nào có thể phù hợp?

Khi thật sự cần một operation độc lập, ví dụ ghi một audit attempt có thể tồn tại dù transaction ngoài rollback. Nhưng đây là **contract khác**, không phải một cách tăng hiệu quả lock mặc định.

### Outer lock có thể chặn inner REQUIRES_NEW

Nếu TX_A đã giữ lock một row mà TX_B cũng muốn khóa, chúng là hai transaction khác nhau. TX_B có thể **chờ lock của TX_A**, trong khi thread đang đợi TX_B hoàn thành để quay lại TX_A. Thiết kế này có thể dẫn đến timeout/deadlock hoặc nghẽn tài nguyên.

**Không xem REQUIRES_NEW là giải pháp “refresh lock” hoặc “nhả rồi lấy lock an toàn” trong một workflow.**

## 19. Các propagation khác và khả năng có transaction

| Spring propagation | Tác động cần lưu ý khi gọi pessimistic lock |
| --- | --- |
| `REQUIRED` | Tạo mới nếu chưa có; tham gia outer nếu có |
| `REQUIRES_NEW` | Transaction độc lập; có thể phá outer atomicity |
| `MANDATORY` | Yêu cầu caller đã có transaction; hữu ích để làm rõ contract |
| `SUPPORTS` | Có transaction thì tham gia, không có thì chạy không transaction; **không đủ làm bảo đảm cho lock** |
| `NOT_SUPPORTED` | Chạy ngoài transaction hiện có; không phù hợp khi method yêu cầu pessimistic lock |
| `NEVER` | Báo lỗi nếu đang có transaction; không phù hợp với pessimistic locking |
| `NESTED` | Phụ thuộc savepoint/manager, không phải transaction vật lý độc lập mặc định |

### MANDATORY cho adapter chỉ được gọi trong transaction

Nếu muốn bảo đảm method đọc khóa phải được gọi từ một service đã mở transaction:

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public Seat lockSeat(long id) {
    return em.find(
        Seat.class,
        id,
        LockModeType.PESSIMISTIC_WRITE);
}
~~~

Khi gọi qua proxy, Spring sẽ báo lỗi nếu không có transaction hiện hành thay vì vô tình chạy một repository operation mà không có outer unit of work.

Lưu ý: trả entity managed ra khỏi adapter **không tự bảo vệ** caller nếu transaction kết thúc ngay sau đó; MANDATORY nhằm đảm bảo đã có transaction, còn caller phải giữ transaction đó qua phần logic cần khóa.

## 20. Flush không giải phóng lock

Giả sử:

~~~java
Seat seat = em.find(
    Seat.class, id,
    LockModeType.PESSIMISTIC_WRITE);

seat.reserveFor(userId);
em.flush();

performOtherDatabaseWork();
~~~

`flush()` đồng bộ pending changes của persistence context xuống database, nhưng **không commit transaction**.

~~~text
BEGIN
  SELECT FOR UPDATE -> lock acquired
  UPDATE Seat
  FLUSH -> SQL đã thực thi trong transaction
  ... thêm nhiều thao tác ...
COMMIT -> transaction kết thúc, lock được nhả
~~~

Không viết:

~~~java
em.flush(); // “Đã nhả lock để người khác làm”.
~~~

vì đó là một hiểu nhầm.

### Flush có thể làm thời điểm lock xuất hiện sớm hơn?

Provider có thể flush pending changes trước khi một số query/lock để đảm bảo consistency, tùy flush mode, loại query và implementation. Một flush cũng có thể phát UPDATE và lấy **additional write locks** ngay trước bước lock dự định. Thứ tự SQL thực tế phải được quan sát ở database.

## 21. clear(), detach(), refresh() không phải API unlock

Các API:

~~~java
em.clear();
em.detach(seat);
em.refresh(seat);
~~~

điều khiển trạng thái persistence context:

- `clear()` detach tất cả managed entities.
- `detach(entity)` đưa một entity ra khỏi managed context.
- `refresh(entity)` nạp lại persistent state của entity.

Chúng **không phải** các lệnh database `UNLOCK ROW` portable.

### Kịch bản

~~~text
BEGIN TX
    find Seat + PESSIMISTIC_WRITE
    em.clear()
    // Java context không còn quản lý Seat
    // Database transaction vẫn đang mở.
COMMIT
    -> các lock transaction-held được giải phóng
~~~

### Đừng nhầm với close()

`EntityManager.close()` không nên được dùng như một cơ chế chủ động nhả một lock trong transaction do container/transaction manager bên ngoài quản lý. Trong RESOURCE_LOCAL, đóng EntityManager khi transaction vẫn active là một lỗi quản lý lifecycle; hành vi cleanup/rollback của provider có thể khác và không phải cách thiết kế an toàn.

**Kết thúc đúng transaction qua commit/rollback**, không dựa vào side effect của việc đóng context.

## 22. Persistence context vẫn có thể mở sau khi transaction đã kết thúc

Một EntityManager `RESOURCE_LOCAL` có thể sống qua hơn một transaction. Extended persistence context trong một số môi trường cũng giữ entities lâu hơn một transaction. Điều này dẫn tới:

~~~text
EntityManager mở
  |
  +-- Transaction 1
  |     Lock Seat
  |     Commit
  |     -> DB lock của TX1 không còn
  |
  +-- Java Seat vẫn managed/detached tùy lifecycle
  |
  +-- Transaction 2
        Nếu cần khóa lại, phải yêu cầu lock trong TX2.
~~~

**Managed state không đồng nghĩa database lock vẫn còn.**

### LockModeType trong EntityManager không phải chứng cứ khóa vật lý

JPA có API như `em.getLockMode(entity)` để xem lock mode được gắn với entity trong context phù hợp, nhưng không dùng giá trị này để chứng minh một DB transaction vẫn đang giữ row lock trên server sau khi transaction đã kết thúc.

Nếu cần biết tranh chấp thực, dùng database lock views/monitoring và integration test.

## 23. JTA: ai quản lý phạm vi giữ khóa?

Trong Jakarta EE/JTA, transaction có thể được quản lý bởi container:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import jakarta.persistence.PersistenceContext;
import jakarta.transaction.Transactional;

public class SeatApplicationService {

    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void reserveSeat(long id, long userId) {
        Seat seat = em.find(
            Seat.class,
            id,
            LockModeType.PESSIMISTIC_WRITE);

        seat.reserveFor(userId);
    }
}
~~~

Ở đây `@Transactional` thuộc `jakarta.transaction`. Container/JTA transaction manager quyết định begin/commit/rollback.

### Không dùng getTransaction() trên JTA-managed EntityManager

Sai:

~~~java
EntityTransaction tx = em.getTransaction();
tx.begin();
~~~

Đây là API của `RESOURCE_LOCAL`, không phải cách quản lý một JTA-managed persistence context.

### Unsynchronized persistence context

Một unsynchronized EntityManager có thể cần `joinTransaction()` trong tình huống thích hợp để tham gia JTA transaction. Chỉ có JTA transaction active ở nơi khác **không tự bảo đảm mọi EntityManager, DataSource hoặc JDBC connection đã enlist đúng**.

Nếu pessimistic lock không được thực hiện trên transactional resource đúng, mục tiêu giữ khóa qua toàn unit of work có thể không đạt.

## 24. Cùng database nhưng khác connection có cùng lock scope không?

Không được suy luận rằng hai connection cùng JDBC URL sẽ chia sẻ cùng một transaction.

~~~text
JPA EntityManager
  -> Connection A
  -> Transaction A
  -> Lock Seat#10

JdbcTemplate / DriverManager
  -> Connection B
  -> Transaction B hoặc auto-commit
  -> UPDATE Seat#10
~~~

Nếu Connection B không được enlist vào transaction A, UPDATE có thể:

- Bị chặn bởi lock của A.
- Timeout/deadlock vì B đợi A nhưng thread đang đợi B hoàn thành.
- Commit độc lập và phá atomicity nếu nó thao tác row khác.

### Cách phối hợp

- Dùng chính transaction-bound EntityManager khi thao tác thuộc JPA unit of work.
- Nếu kết hợp JDBC, bảo đảm `DataSource` và transaction manager cấu hình đúng để JDBC tham gia transaction/resource tương ứng.
- Nếu dùng nhiều databases, cần thiết kế JTA/XA hoặc saga/outbox phù hợp; một annotation `@Transactional` không tự làm mọi connection thuộc cùng transaction vật lý.

### Không mở Connection autoCommit riêng để “giữ khóa”

Một `SELECT ... FOR UPDATE` trên connection auto-commit có thể nhả lock ngay khi statement transaction hoàn tất, không còn bảo vệ logic Java tiếp theo. Đây không phải thay thế portable cho một JPA transaction boundary đúng.

## 25. Pessimistic locking và isolation level

Database isolation level điều chỉnh những gì transaction khác có thể đọc/thấy và cách các anomaly được xử lý. Pessimistic lock là cơ chế được **yêu cầu tường minh** cho những row/tài nguyên cụ thể.

| Isolation | Điều cần hiểu khi dùng lock |
| --- | --- |
| READ COMMITTED | Những statement có thể thấy các committed versions khác nhau; lock giúp điều phối row đang thao tác |
| REPEATABLE READ | Snapshot/locking semantics tùy DBMS; vẫn cần hiểu các conflict và predicate reads |
| SERIALIZABLE | DBMS có thể từ chối transaction gây lịch sử không serializable; cần retry theo quy tắc |

### Có thể bỏ lock nếu isolation là SERIALIZABLE không?

Không thể trả lời chung cho mọi use case. SERIALIZABLE có thể bảo vệ nhiều invariant bằng cách buộc một transaction rollback, nhưng có chi phí và phụ thuộc DBMS. Nếu ứng dụng cần **chủ động claim một tài nguyên**, pessimistic locking vẫn có thể là một lựa chọn thiết kế hợp lý.

### Lock không tự làm mọi query của transaction ổn định

Khóa một Seat không tự khóa mọi Booking, mọi Event hoặc mọi Seat khác. Một invariant liên quan **nhiều rows hoặc một predicate** có thể cần thêm lock scope, unique constraints, isolation hoặc mô hình ghi khác.

## 26. JPA lock trên entity không có nghĩa khóa mọi association

Giả sử:

~~~text
Event#10
  |
  +-- Seat#1
  +-- Seat#2
  +-- Seat#3
~~~

Một lời gọi:

~~~java
Event event = em.find(
    Event.class,
    eventId,
    LockModeType.PESSIMISTIC_WRITE);
~~~

không cho phép khẳng định “mọi Seat của Event đều đã được khóa” trên mọi provider/DBMS. Pessimistic lock scope thông thường áp lên entity và những database rows phù hợp theo rules của JPA, **không tự động khóa toàn bộ object graph của tất cả quan hệ**.

### Tại sao nguy hiểm?

Nếu business invariant là “Event chỉ còn 100 ghế chưa bán”, khóa một row Event nhưng những writers khác cập nhật Seat mà không tuân thủ cùng protocol có thể phá invariant.

### Cách thiết kế

- Khóa chính row Seat mà operation định claim.
- Hoặc mọi writer cùng khóa một row Event trước khi điều chỉnh counter chung.
- Hoặc dùng atomic UPDATE trên counter/seat state cùng constraints.
- Hoặc các transaction isolation/invariant mechanisms khác đã kiểm thử.

**Một khóa chỉ có ý nghĩa khi các transaction cạnh tranh chạm những tài nguyên/điều kiện được database điều phối tương ứng.**

## 27. Lock scope NORMAL và EXTENDED

JPA có khái niệm phạm vi khóa bi quan như `PessimisticLockScope.NORMAL` và `PessimisticLockScope.EXTENDED` trong các phiên bản/API phù hợp.

Ví dụ lock hint:

~~~java
Map<String, Object> hints = new HashMap<>();
hints.put(
    "jakarta.persistence.lock.scope",
    PessimisticLockScope.EXTENDED);

Seat seat = em.find(
    Seat.class,
    seatId,
    LockModeType.PESSIMISTIC_WRITE,
    hints);
~~~

### Ý tưởng

- **NORMAL:** tập trung vào row(s) liên quan đến identity/state của entity được khóa theo JPA semantics.
- **EXTENDED:** có thể mở rộng tới một số cấu trúc collection/association được lưu trong join table hoặc collection table theo hợp đồng đặc tả, thay vì chỉ root rows.

### Không hiểu EXTENDED là “khóa tất cả”

EXTENDED **không biến một EntityGraph bất kỳ thành lock cho toàn bộ tree các entity liên kết**. Khả năng áp dụng và semantics cụ thể còn phụ thuộc provider, mapping và DBMS. Một số hints có thể bị provider bỏ qua khi không hỗ trợ.

### Khi nào nên dùng?

Chỉ sau khi xác định rõ invariant liên quan cấu trúc nào và kiểm chứng SQL/lock behavior trên provider dùng thật. Nếu phải bảo vệ cả một graph phức tạp, đôi khi cách rõ hơn là khóa một aggregate root được tất cả writers tuân thủ hoặc dùng constraint/lock theo danh sách rows cụ thể.

## 28. Lock khi query có JOIN

Ví dụ:

~~~jpql
SELECT s
FROM Seat s JOIN s.event e
WHERE e.id = :eventId
  AND s.status = :status
ORDER BY s.id
~~~

Khi gắn:

~~~java
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);
~~~

đừng mặc định mọi row của Event và tất cả bảng JOIN đều có cùng lock. Cách SQL sinh ra, lock aliases, WHERE predicate, row granularity và hỗ trợ của database khác nhau.

Một số DBMS hạn chế `FOR UPDATE` trong query có `DISTINCT`, `GROUP BY`, outer joins hoặc pagination. Provider có thể dùng secondary locking SELECT hay báo lỗi.

### Cách làm thực tế

Với use case claim một Seat biết trước ID:

~~~java
em.find(Seat.class, id, PESSIMISTIC_WRITE);
~~~

dễ suy luận hơn một query JOIN phức tạp vừa tìm, vừa sort, vừa lock nhiều rows.

Nếu cần claim một trong nhiều tài nguyên rảnh, phải thiết kế query lock và transaction theo semantics DBMS, có thể cần cơ chế SKIP LOCKED hoặc atomic conditional UPDATE.

## 29. Timeout khi chờ khóa

Một transaction có thể phải chờ khóa:

~~~text
TX_A: Lock Seat#10, xử lý trong 2 giây
TX_B: yêu cầu Lock Seat#10
      -> chờ TX_A
~~~

Để tránh chờ quá lâu, JPA có hint phổ biến:

~~~java
Map<String, Object> props = Map.of(
    "jakarta.persistence.lock.timeout", 2_000);

Seat seat = em.find(
    Seat.class,
    seatId,
    LockModeType.PESSIMISTIC_WRITE,
    props);
~~~

Giá trị ví dụ là **mili giây** theo contract của hint JPA tương ứng. Tuy nhiên, JPA provider/DBMS không phải luôn hỗ trợ mọi timeout hint chính xác như nhau.

### Timeout có được bảo đảm là đúng 2 giây?

Không. Lock timeout có thể bị giới hạn bởi:

- Driver/database khả năng hỗ trợ.
- Provider mapping timeout xuống SQL/JDBC/session settings.
- Transaction timeout từ transaction manager.
- Statement/query timeout.
- Thời gian network, scheduling và DB queuing.

**Kiểm thử trên DBMS/provider/version thực tế**, không chỉ đặt một hint rồi coi đó là SLA chắc chắn.

### Giá trị đặc biệt

Một số JPA/provider/DBMS dùng cấu hình `0` để yêu cầu không chờ và những giá trị khác cho wait policy; semantics không hoàn toàn portable khi backend không hỗ trợ. Không suy đoán “-1 luôn là chờ vô hạn” ở mọi tổ hợp khi chưa xác minh.

## 30. Phân biệt lock timeout và query timeout

Hai loại hint thường gặp:

~~~java
query.setHint("jakarta.persistence.lock.timeout", 1000);
query.setHint("jakarta.persistence.query.timeout", 3000);
~~~

| Hint | Mục tiêu |
| --- | --- |
| `jakarta.persistence.lock.timeout` | Giới hạn thời gian chờ khóa theo khả năng hỗ trợ |
| `jakarta.persistence.query.timeout` | Giới hạn thời gian thực thi query theo khả năng hỗ trợ |

Một query có thể chậm vì:

- Chờ lock.
- Scan/sort nhiều rows.
- Database thiếu index.
- Truyền dữ liệu lớn.
- External resource hoặc DB server tải cao.

Không coi mọi query timeout là “có transaction khác giữ lock” nếu chưa xem database wait events.

## 31. PessimisticLockException và LockTimeoutException

JPA có các exception liên quan khóa:

| Exception | Ý nghĩa khái quát |
| --- | --- |
| `TransactionRequiredException` | Yêu cầu lock nhưng thiếu transaction phù hợp |
| `PessimisticLockException` | Lỗi lấy pessimistic lock dẫn đến transaction-level rollback theo contract |
| `LockTimeoutException` | Lỗi lock mà provider phân loại là statement-level rollback theo contract |
| `OptimisticLockException` | Version check không hợp lệ; cũng có thể liên quan versioned entity với locking |

### Tại sao phải phân biệt?

JPA có phân biệt trường hợp database/provider rollback **toàn transaction** với trường hợp chỉ rollback **statement** khi lock thất bại. Nhưng ứng dụng không nên kết luận chỉ từ tên exception rằng mọi database vẫn cho phép tiếp tục transaction an toàn.

Ví dụ:

~~~java
try {
    em.find(
        Seat.class, seatId,
        LockModeType.PESSIMISTIC_WRITE);
} catch (LockTimeoutException ex) {
    // Đánh giá transaction status theo provider/manager.
    // Không mặc định tiếp tục mọi business write.
}
~~~

Đối với workflow đặt ghế cần all-or-nothing, một chính sách đơn giản là **rollback attempt, trả conflict/busy hoặc retry transaction mới khi phù hợp**.

### Spring exception translation

Trong Spring Data JPA, provider exception có thể được chuyển thành `DataAccessException` hoặc dạng exception tương ứng. Nếu xử lý retry theo loại lỗi, classifier cần hiểu cấu hình stack thực, không chỉ catch một class JPA duy nhất.

## 32. Deadlock: hai transaction khóa tài nguyên ngược thứ tự

Giả sử chuyển ghế giữa hai khu:

~~~text
TX_A                               TX_B
--------------------------------   --------------------------------
Lock Seat#10 thành công             Lock Seat#20 thành công
Muốn Lock Seat#20                   Muốn Lock Seat#10
  -> chờ TX_B                        -> chờ TX_A

                DEADLOCK
~~~

Database có thể phát hiện chu trình chờ và chọn một transaction làm victim, buộc rollback hoặc báo lỗi theo semantics của engine.

### Giảm rủi ro

Nếu phải khóa nhiều rows trong một transaction, yêu cầu khóa theo **thứ tự ổn định**:

~~~text
Seat IDs = [20, 10, 30]
Sắp xếp -> [10, 20, 30]
Lấy lock theo thứ tự ID tăng
~~~

Ví dụ Java:

~~~java
List<Long> sortedIds = seatIds.stream()
    .distinct()
    .sorted()
    .toList();

for (Long id : sortedIds) {
    em.find(
        Seat.class,
        id,
        LockModeType.PESSIMISTIC_WRITE);
}
~~~

### Có bảo đảm không deadlock không?

Không. Deadlocks còn đến từ FK constraints, triggers, index operations, các tables khác và SQL do provider sinh ra. Thứ tự khóa nhất quán **giảm rủi ro**, không loại bỏ mọi deadlock.

## 33. Không giữ transaction mở khi gọi hệ thống chậm bên ngoài

Một anti-pattern:

~~~text
BEGIN TRANSACTION
  Lock Seat#10
  Call payment gateway qua HTTP (3–30 giây)
  Chờ email service
  Gọi API xác minh khách hàng
  Update Seat
COMMIT
~~~

Trong lúc đó, các requests khác có thể phải chờ lock, và connection/transaction đang chiếm resource. Nếu external API treo, lock có thể bị giữ rất lâu.

### Thay bằng workflow nhiều giai đoạn

~~~text
Transaction 1 (ngắn):
  Lock Seat
  Nếu còn trống -> tạo reservation HELD, expires_at
  COMMIT, giải phóng lock

Ngoài transaction:
  Gọi payment gateway

Transaction 2 (ngắn):
  Lock reservation/Seat liên quan
  Kiểm tra payment/reservation chưa hết hạn
  CONFIRM hoặc RELEASE theo state machine
  COMMIT
~~~

Những trạng thái `HELD`/`CONFIRMED`/`EXPIRED` và timeout release là **quy tắc nghiệp vụ được lưu trong database**, không phải lock database giữ liên tục từ Transaction 1 sang Transaction 2.

### Atomicity với thanh toán

Payment gateway không tự tham gia database transaction. Khi có sự cố giữa payment và booking confirmation, cần idempotency/compensation/reconciliation theo chính sách. Khóa bi quan không biến HTTP thành một XA transaction.

## 34. Không giữ lock xuyên nhiều HTTP requests

Người dùng mở giao diện:

~~~text
GET /seats/10 -> status AVAILABLE
Người dùng suy nghĩ 2 phút
POST /bookings -> đặt Seat#10
~~~

**Không giữ database transaction mở từ GET cho đến POST** chỉ để “giữ khóa cho người dùng”.

Lý do:

- Thời gian người dùng không giới hạn.
- Connection/transaction và lock bị giữ lâu.
- Request khác bị chặn.
- App node có thể restart hoặc mạng mất.
- DB timeout sẽ giải phóng lock theo thất bại, nên UI không có contract đáng tin.

### Cách đúng

Trong POST, bắt đầu **transaction ngắn**, lấy pessimistic lock, kiểm tra Seat còn AVAILABLE, xác nhận booking rồi commit. Nếu cần giữ chỗ có thời hạn, dùng **reservation record với expires_at**, không dùng transaction lock làm timer.

## 35. Open Session in View không phải là transaction giữ lock

Trong một số ứng dụng Spring web, Open Session/EntityManager in View có thể giữ persistence context mở qua quá trình render response.

~~~text
Request bắt đầu
  |
  +-- Service @Transactional BEGIN
  |      Lock Seat
  |      Update Seat
  |      COMMIT -> database lock được giải phóng
  |
  +-- Controller/Serializer
  |      EntityManager có thể vẫn mở để lazy-load
  |
Request kết thúc
~~~

**EntityManager còn mở không có nghĩa transaction và lock vẫn đang được giữ.**

Ngược lại, nếu code giữ một outer transaction qua nhiều operations rồi chỉ trả response sau cùng, lock có thể dài hơn bạn tưởng. Cần quan sát transaction boundaries thực, không suy luận từ “session open/closed”.

## 36. Read-only transaction có phù hợp PESSIMISTIC_WRITE không?

Một method:

~~~java
@Transactional(readOnly = true)
public Seat getSeatWithLock(long id) {
    return em.find(
        Seat.class,
        id,
        LockModeType.PESSIMISTIC_WRITE);
}
~~~

đặt ra mâu thuẫn về mục đích: `readOnly=true` thường báo **intention đọc**, trong khi PESSIMISTIC_WRITE yêu cầu khóa phục vụ ghi/độc quyền.

### Có chắc thất bại không?

Không thể khẳng định trên mọi stack. Spring read-only có thể ảnh hưởng flush mode và JDBC connection hint, DBMS có thể chặn locking/write trong read-only transaction hoặc không.

### Khuyến nghị

Nếu method muốn **read-check-write**, dùng transaction writable thông thường. Với `PESSIMISTIC_READ` chỉ đọc, vẫn cần active transaction đủ dài, và phải hiểu read-only semantics/lock support của DBMS cụ thể.

**Đừng dùng readOnly=true như một chiến lược giảm lock contention.**

## 37. Lock scope của query và pagination

Khi cần khóa một ghế trống bất kỳ:

~~~java
List<Seat> candidate = em.createQuery(
        "SELECT s FROM Seat s " +
        "WHERE s.eventId = :eventId " +
        "AND s.status = :available " +
        "ORDER BY s.id",
        Seat.class)
    .setParameter("eventId", eventId)
    .setParameter("available", SeatStatus.AVAILABLE)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .setMaxResults(1)
    .getResultList();
~~~

Nghe có vẻ “khóa đúng một ghế đầu tiên”, nhưng provider/database có thể có cách thực thi pagination + locking khác nhau; một số database giới hạn kết hợp `LIMIT/OFFSET` với locking SQL phức tạp. Locking predicate/rows phụ thuộc plan và dialect.

### Khi nào cần nghiên cứu SKIP LOCKED?

Nếu nhiều worker cần claim nhiều bản ghi/job khác nhau và không muốn cùng chờ row đang bị khóa, một số DBMS hỗ trợ cơ chế **SKIP LOCKED**. Nhưng đây không phải một hành vi portable của `PESSIMISTIC_WRITE` mặc định.

### Không dùng OFFSET để claim công việc trong tập đang thay đổi

Một worker cập nhật status từ AVAILABLE thành RESERVED khiến tập kết quả đang lọc thay đổi. Nếu worker khác tăng offset giữa các lần claim, có thể bỏ sót rows. Với queue/claim workflow, ưu tiên atomic claim hoặc SKIP LOCKED theo DBMS thay vì pagination UI thông thường.

## 38. NOWAIT và SKIP LOCKED là tính năng tùy DBMS/provider

Một số database hỗ trợ SQL như:

~~~sql
-- Ví dụ PostgreSQL, không phải JPQL portable.
SELECT id, status
FROM event_seats
WHERE event_id = :eventId
  AND status = 'AVAILABLE'
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 1;
~~~

Hoặc:

~~~sql
SELECT id, status
FROM event_seats
WHERE id = :seatId
FOR UPDATE NOWAIT;
~~~

**NOWAIT** thường yêu cầu không chờ lock đã bị transaction khác giữ; **SKIP LOCKED** bỏ qua những row đang bị khóa để tìm row khác. Cú pháp và semantics không giống nhau giữa PostgreSQL, Oracle, SQL Server, MySQL hoặc provider JPA.

### Trường hợp phù hợp

- Job queue nhiều workers.
- Worker claim một task chưa ai xử lý.
- Batch processing muốn tránh chờ cùng một row.

### Trường hợp không phù hợp

- Một người muốn đặt **đúng Seat A01** mà transaction khác đang giữ lock. “Skip” row này rồi chọn Seat B01 có thể vi phạm yêu cầu người dùng nếu không có permission/UX xác nhận.

Không áp dụng `SKIP LOCKED` theo thói quen mà không hiểu semantics “bỏ qua tài nguyên đang bị giữ”.

## 39. Khóa một row không bảo đảm predicate nhiều rows

Giả sử invariant:

~~~text
Sự kiện chỉ được bán tối đa 500 vé.
~~~

Hai transaction cùng đếm:

~~~text
SELECT COUNT(*) FROM bookings
WHERE event_id = 10 AND status = 'CONFIRMED';
~~~

cả hai thấy 499 rồi cùng insert một Booking vào **hai rows khác nhau**. Khóa một Seat riêng của từng transaction **không tự bảo vệ tổng số 500**.

### Cách giải

- Dùng một row counter ở Event, mọi writer phải lock/update cùng row.
- Dùng atomic conditional UPDATE `sold_count < capacity`.
- Dùng constraint hoặc thiết kế allocation slots hữu hạn.
- Hoặc SERIALIZABLE isolation với retry transaction theo DBMS thích hợp.

Đây là ví dụ **invariant trên tập dữ liệu**, không chỉ trên một row.

### Quy tắc

> Khóa những tài nguyên thực sự bảo vệ invariant mà bạn đang kiểm tra, không chỉ entity thuận tiện nhất để gọi `em.find()`.

## 40. Khóa bi quan và @Version có thể phối hợp

Một Seat có:

~~~java
@Version
private Long version;
~~~

và một transaction đọc:

~~~java
Seat seat = em.find(
    Seat.class, id,
    LockModeType.PESSIMISTIC_WRITE);
~~~

Hai cơ chế không loại trừ nhau:

- **Pessimistic lock:** điều phối thời điểm các transactions cạnh tranh được phép truy cập/ghi theo DB lock semantics.
- **Optimistic version:** kiểm tra rằng entity versioned vẫn nhất quán với state đang được ghi.

JPA có thể thực hiện kiểm tra version liên quan khi lấy pessimistic lock đối với entity versioned và báo conflict nếu phát hiện stale state.

### Sau commit

Khóa được giải phóng theo DB transaction, còn `version` là **dữ liệu persistent** phản ánh write theo quy tắc provider. Version không phải lock. Một client đang giữ version cũ có thể cần precondition kiểm tra khi submit request sau.

### Native SQL cần protocol

Một stored procedure/native UPDATE thay status Seat nhưng không tăng version có thể làm optimistic writers khác không phát hiện thay đổi theo kỳ vọng. Mọi writers cần cùng tuân thủ constraints/versioning/locking policy.

## 41. Atomic conditional UPDATE như một lựa chọn khác

Với nhiệm vụ đơn giản “claim một Seat nếu còn trống”, một câu SQL có điều kiện có thể đủ để tránh check-then-act:

~~~sql
UPDATE event_seats
SET status = 'RESERVED',
    reserved_by_user_id = :userId,
    version = version + 1
WHERE id = :seatId
  AND tenant_id = :tenantId
  AND event_id = :eventId
  AND status = 'AVAILABLE';
~~~

Kết quả:

~~~text
affectedRows = 1 -> claim thành công.
affectedRows = 0 -> không có seat phù hợp hoặc không AVAILABLE.
~~~

Database thực hiện kiểm tra điều kiện và cập nhật trong **cùng một statement** theo semantics isolation/locking của DBMS, giảm khoảng race giữa SELECT và UPDATE.

### Có thay thế transaction cho cả Booking không?

Không. Nếu sau UPDATE cần INSERT Booking, **cả hai phải nằm trong một transaction** để bảo đảm atomicity. Một native UPDATE auto-commit rồi một JPA INSERT thất bại vẫn có thể tạo ghế RESERVED không có Booking.

### Trade-off

- Giảm round trips nếu chỉ cần claim row.
- Tránh tải full entity khi không cần domain object.
- Phải tự xử lý affectedRows, version, tenant, persistence context stale.
- Không tự chạy entity lifecycle callbacks như managed dirty checking.

Chọn giữa PESSIMISTIC_WRITE và atomic conditional SQL dựa trên **độ phức tạp nghiệp vụ, hiệu năng, khả năng bảo vệ invariant và portability**, không dựa vào khẩu hiệu “khóa càng mạnh càng an toàn”.

## 42. Một số lỗi có thể xuất hiện trước commit

Trong giao dịch đặt ghế:

~~~java
Seat seat = em.find(
    Seat.class, id,
    LockModeType.PESSIMISTIC_WRITE);
seat.reserveFor(userId);
em.persist(new Booking(...));
em.flush();
tx.commit();
~~~

Các lỗi có thể xảy ra ở:

| Giai đoạn | Ví dụ |
| --- | --- |
| Lấy lock | Lock timeout, deadlock, TransactionRequiredException |
| Kiểm tra domain | Ghế không còn trống, tenant không khớp |
| Flush | FK/UNIQUE/CHECK constraint, optimistic version conflict |
| Commit | Deferred constraint, serialization, DB resource failure |

Không tuyên bố thành công ngay khi nhận được entity từ `find()` hay khi `flush()` không ném lỗi. **Commit thành công mới xác nhận unit of work**, trừ những outcome không rõ do network/resource errors cần reconciliation.

## 43. Lỗi nào được retry?

Một transaction có thể thất bại vì:

- Deadlock victim.
- Lock timeout.
- Serialization failure.
- Optimistic version conflict.
- Database resource timeout.
- Business rejection vì Seat đã RESERVED.

Không được gom tất cả vào “retry thêm ba lần”.

### Phân loại

| Trường hợp | Hướng xử lý thường phù hợp |
| --- | --- |
| Seat đã RESERVED | Business conflict; không retry ngay trên cùng ghế |
| Lock timeout ngắn do contention | Có thể retry transaction mới với giới hạn |
| Deadlock | Có thể retry toàn transaction mới, giữ lock order ổn định |
| Serialization failure | Retry toàn unit of work khi idempotent |
| Invalid input/tenant | Không retry |
| SQL syntax/mapping lỗi | Không retry |
| Commit outcome không rõ | Xác minh idempotency/outcome trước khi thử lại |

### Retry đúng ở đâu?

Nếu retry sau một database failure, thường phải:

1. Rollback transaction thất bại.
2. Không tiếp tục với EntityManager/context dirty hoặc rollback-only.
3. Backoff bên ngoài transaction nếu cần.
4. Bắt đầu transaction mới và context phù hợp.
5. Lấy lock lại.
6. Đọc/kiểm tra state mới.
7. Thực hiện lại **toàn unit of work** nếu nghiệp vụ cho phép.

Không retry riêng `em.find(... PESSIMISTIC_WRITE)` trong một transaction đã lỗi mà vẫn giữ các quyết định từ snapshot trước.

## 44. Transaction timeout và lock timeout không phải một thứ

Giả sử:

~~~text
Transaction timeout: 5 giây
Lock wait timeout: 2 giây
Query timeout: 3 giây
~~~

Các giới hạn này có thể tương tác theo framework/DBMS/provider nhưng không đồng nghĩa:

- **Transaction timeout**: giới hạn thời gian toàn transaction tồn tại/được phép hoàn thành.
- **Lock wait timeout**: giới hạn chờ để lấy lock.
- **Query timeout**: giới hạn thực thi một query/statement.

Nếu transaction timeout xảy ra trước lock timeout, transaction có thể bị rollback dù lock hint còn thời gian. Ngược lại, lock timeout có thể xảy ra nhưng transaction manager vẫn cho phép một số xử lý theo semantics được hỗ trợ.

### Không đặt timeout mà bỏ quên cleanup

Sau timeout, mã Java phải xử lý exception và kết thúc transaction phù hợp. Một lock hoặc transaction treo có thể gây lan rộng contention; ứng dụng cần monitoring và connection pool handling.

## 45. Kiểm thử bằng hai EntityManager và hai transaction

Một unit test mock repository không chứng minh rằng database đã giữ row lock. Cần integration test với **hai transaction thật**.

Fixture:

~~~text
Seat#10:
  status = AVAILABLE
  version = 1
~~~

Kiểm thử:

~~~text
Thread A / EM_A / TX_A            Thread B / EM_B / TX_B
--------------------------------  -----------------------------------
BEGIN                             BEGIN
find Seat#10 with WRITE lock
  -> lock acquired
                                  find Seat#10 with WRITE lock
                                    -> chờ hoặc timeout tùy policy
reserveFor(userA)
flush()
                                  Không được “đặt ghế thành công”
                                  trước khi có state được bảo vệ.
COMMIT
                                  Sau khi có lock:
                                  thấy RESERVED hoặc conflict
                                  ROLLBACK
~~~

Kết quả mong muốn: **chỉ có một Booking confirmed/active cho Seat#10**, trạng thái Seat consistent với Booking và không có hai user cùng nhận xác nhận thành công.

### Không trông chờ test chạy bằng H2 mặc định mô phỏng mọi DBMS production

Lock modes, transaction isolation, timeout và SQL dialect khác nhau theo database. Để xác nhận behavior cần thiết, chạy integration test trên **DBMS/dialect/version tương đương production**, ví dụ PostgreSQL Testcontainers nếu đó là stack thực.

## 46. Skeleton JUnit-style: giữ khóa ở transaction A

Một test harness có thể sử dụng hai EntityManager, chạy B trong một thread riêng và điều phối bằng latch:

~~~java
// Pseudocode mô tả; dùng executor/latches/fixture JUnit phù hợp.
EntityManager emA = emf.createEntityManager();
EntityManager emB = emf.createEntityManager();

try {
    emA.getTransaction().begin();

    Seat a = emA.find(
        Seat.class,
        seatId,
        LockModeType.PESSIMISTIC_WRITE);

    // Lúc này transaction A đã yêu cầu lock.

    Future<SeatStatus> future = executor.submit(() -> {
        emB.getTransaction().begin();
        try {
            Seat b = emB.find(
                Seat.class,
                seatId,
                LockModeType.PESSIMISTIC_WRITE);

            SeatStatus observed = b.getStatus();
            emB.getTransaction().commit();
            return observed;
        } catch (RuntimeException ex) {
            if (emB.getTransaction().isActive()) {
                emB.getTransaction().rollback();
            }
            throw ex;
        }
    });

    // Dùng barrier/latch xác nhận B đã bắt đầu,
    // đừng chỉ Thread.sleep rồi kết luận B đang blocked.

    a.reserveFor(userA);
    emA.flush();
    emA.getTransaction().commit();

    SeatStatus seenByB =
        future.get(5, TimeUnit.SECONDS);

    assertEquals(SeatStatus.RESERVED, seenByB);

} finally {
    if (emA.getTransaction().isActive()) {
        emA.getTransaction().rollback();
    }
    if (emB.getTransaction().isActive()) {
        emB.getTransaction().rollback();
    }
    emA.close();
    emB.close();
}
~~~

Đây là skeleton minh họa, không phải một test file độc lập chạy ngay. Những đối tượng `executor`, `seatId`, `userA` và assertions phải được tạo bởi test harness, và cần chờ/cancel/close executor đúng cách.

### Rủi ro trong test

- B có thể chưa đến lời gọi locking query trước lúc A commit nếu scheduler chậm.
- `Future.get()` timeout không đồng nghĩa database lock timeout.
- EM_B không được sử dụng đồng thời bởi thread main và worker trong cùng khoảng thời gian; phần cleanup phải xảy ra sau khi task kết thúc.
- Query plan/provider có thể dùng SQL khác.
- Một test đúng phải kiểm soát điểm đạt được lock và transaction states thay vì dựa vào timing ngẫu nhiên.

### Cách tăng độ chắc chắn

Dùng latch/barrier ở những điểm trước/đang gọi lock, cùng instrumentation của JDBC/database để chứng minh B thực sự phải chờ, hoặc dùng DB lock timeout cấu hình rõ và assert loại lỗi. Test cuối phải đọc bằng EntityManager mới sau commit/rollback để tránh first-level cache cũ.

## 47. Test lock được nhả khi commit hoặc rollback

Hai test độc lập:

### A. Khi commit

~~~text
TX_A:
    Lock Seat#10
    Reserve
    COMMIT

TX_B:
    Lấy lock Seat#10
    Kiểm tra thấy RESERVED
    Không reserve lại
    ROLLBACK
~~~

### B. Khi rollback

~~~text
TX_A:
    Lock Seat#10
    Reserve
    ROLLBACK

TX_B:
    Lấy lock Seat#10
    Kiểm tra thấy AVAILABLE
    Reserve được nếu nghiệp vụ cho phép
    COMMIT
~~~

**Kỳ vọng:** transaction B không bị treo mãi sau khi A đã kết thúc. Nhưng khi A rollback, state của B phụ thuộc fixture/trạng thái đã commit trước đó và isolation/database rules; không suy luận mọi update trung gian từ A có thể nhìn thấy khi A chưa commit.

### Test không dùng cùng EntityManager

Hai transaction phải có **hai context độc lập**; nếu dùng cùng EntityManager hoặc cùng transaction, test không kiểm tra tranh chấp giữa hai transaction.

## 48. Test boundary của Spring service

Một integration test Spring nên xác minh:

- Entry service thực sự được gọi qua proxy.
- Transaction active tại thời điểm gọi `PESSIMISTIC_WRITE`.
- Repository/helper dùng cùng transaction manager/resource.
- Lock không được giải phóng giữa phương thức con và outer commit.
- `REQUIRES_NEW` không làm tách atomicity ngoài ý định.
- Read-only flag không vô tình áp cho workflow ghi.
- Timeout/deadlock được xử lý bằng rollback theo policy.

### Cẩn trọng với @Transactional trên test

Nhiều Spring tests mặc định chạy trong một test-managed transaction và rollback cuối test. Nếu test muốn tạo **hai transaction vật lý cạnh tranh**, đừng vô tình để cả fixture/test operation trong một outer transaction làm bề mặt kiểm thử không còn phản ánh luồng production.

Có thể dùng transaction templates/executors/test transaction controls để tạo boundaries rõ, và kiểm tra committed state bằng context mới.

## 49. Transaction visibility khi một khóa đang được giữ

Lock được giữ không có nghĩa transaction khác luôn không thể đọc row:

~~~text
TX_A:
    Lock Seat#10 FOR UPDATE
    Change Seat.status to RESERVED
    chưa COMMIT

TX_B:
    SELECT Seat#10 không lock
~~~

Ở nhiều DBMS có MVCC, TX_B vẫn có thể đọc **phiên bản committed trước đó** của row thay vì bị chặn. Với locking SELECT hoặc UPDATE, TX_B có thể phải chờ.

### Vì sao quan trọng?

Một màn hình GET có thể vẫn hiển thị AVAILABLE trong lúc TX_A chưa commit. Điều đó không chứng minh lock đã mất. Khi user bấm Reserve, **POST phải tự lấy lock và kiểm tra lại trong transaction của nó**.

### Đừng dùng GET đọc trước làm điều kiện duy nhất cho POST

Giá trị hiển thị cho người dùng là state tham khảo tại thời điểm đọc. Nó không thể bảo vệ một quyết định ghi được thực hiện sau hàng giây/phút.

## 50. Lock contention ảnh hưởng throughput thế nào?

Giả sử một Seat nóng:

~~~text
Một transaction giữ lock 100 ms.
100 requests khác muốn lock cùng row.
~~~

Tùy DBMS và lịch xử lý, những requests khác có thể xếp hàng/chờ, gây tăng latency. Nếu transaction giữ lock 5 giây vì gọi dịch vụ ngoài, độ trễ có thể tăng mạnh và connection pool bị chiếm.

### Các cách giảm contention

1. Tối giản thời gian giữa lock acquisition và commit.
2. Làm validation **không phụ thuộc state được khóa** trước khi lấy lock.
3. Không gọi HTTP/SMTP/payment gateway trong transaction giữ lock.
4. Dùng index phù hợp để tìm đúng rows.
5. Lock theo thứ tự ổn định khi cần nhiều rows.
6. Chỉ khóa tài nguyên thực sự bảo vệ invariant.
7. Xem atomic conditional UPDATE thay cho read-check-write phức tạp khi phù hợp.
8. Dùng queue/partition/sharding khi một row trở thành hotspot.
9. Theo dõi wait time, timeout, deadlock và lock holder transaction.
10. Retry có giới hạn và backoff theo loại lỗi.

### Không phải lock càng lâu càng an toàn

Lock giữ quá dài có thể bảo vệ một invariant cục bộ nhưng làm hệ thống **không còn đáp ứng được tải**, thậm chí tăng nguy cơ timeout và lỗi dây chuyền.

## 51. Những lỗi phổ biến khi xác định phạm vi giữ khóa

| Lỗi | Vì sao nguy hiểm | Hướng xử lý |
| --- | --- | --- |
| Gọi `find(...PESSIMISTIC_WRITE)` ngoài transaction | JPA có thể ném TransactionRequiredException | Bắt đầu/tham gia transaction trước lock |
| Repository có transaction riêng, service kiểm tra sau khi method return | Lock đã nhả trước quyết định | Đặt transaction ở application service |
| Nghĩ Java variable còn sống nghĩa lock còn giữ | Lock thuộc database transaction | Xác định begin/commit/rollback |
| Nghĩ `flush()` giải phóng lock | Flush không commit | Commit/rollback tại transaction boundary |
| Nghĩ `clear()`/`detach()` unlock row | Chỉ đổi persistence context | Kết thúc transaction |
| Nghĩ `close()` thay commit | Cleanup không phải transaction semantics rõ | Commit/rollback tường minh/qua manager |
| Nested Spring method return nhưng outer TX còn mở | Lock vẫn giữ làm tăng wait | Rút ngắn outer transaction |
| Self-invocation `@Transactional` | Annotation có thể không qua proxy | Gọi qua entrypoint/proxy phù hợp |
| `SUPPORTS` để yêu cầu lock | Có thể chạy không TX | Dùng REQUIRED/MANDATORY đúng contract |
| `REQUIRES_NEW` trong outer checkout | Inner commit riêng, phá atomicity | Giữ toàn unit trong cùng TX |
| Dùng readOnly=true cho operation ghi có lock | Flush/write/lock behavior khó đoán | Transaction writable |
| JTA EntityManager dùng `getTransaction()` | Sai API transaction type | JTA/container quản lý |
| JDBC connection khác với JPA | Không cùng transaction, dễ deadlock/commit riêng | Enlist đúng resource |
| Khóa Event rồi tin mọi Seats đã khóa | Association không tự thành graph-wide lock | Xác định row/invariant cần khóa |
| Chỉ khóa một Seat khi giới hạn tổng 500 vé | Predicate/count invariant chưa bảo vệ | Counter chung/constraint/isolation |
| Bắt LockTimeoutException rồi tiếp tục mọi SQL | Transaction có thể không còn sử dụng an toàn | Kiểm tra status, rollback theo policy |
| Retry trong transaction lỗi | Rollback-only/stale context | TX/context mới |
| Không timeout | Request có thể chờ lock dài | Cấu hình timeout và monitoring |
| Timeout quá thấp và retry dồn dập | Retry storm | Backoff/jitter, giới hạn |
| Giữ lock khi gọi payment API | Contention/timeout | Reservation workflow nhiều TX ngắn |
| Giữ TX giữa GET và POST | Người dùng chờ lâu, resource bị chiếm | Lock lại trong POST |
| Chỉ kiểm thử với mock JPA | Không xác nhận DB lock behavior | Integration test hai TX thật |
| Test hai threads dùng chung EntityManager | Không thread-safe/sai phạm vi | Mỗi thread một EM |
| Một session OSIV vẫn mở nên tưởng lock giữ | EM lifetime khác TX lifetime | Quan sát transaction manager |
| Không scope tenant khi lock theo ID | Có nguy cơ thao tác tài nguyên sai quyền | Validate tenant/ACL trước quyết định |
| Commit thất bại nhưng API báo thành công | Side effect chưa được xác nhận | Chỉ xác nhận sau boundary thành công |

## 52. Quy trình xác định transaction boundary trước khi viết code

Khi một service cần pessimistic locking, làm lần lượt:

1. **Định nghĩa invariant** phải bảo vệ, ví dụ “một Seat chỉ một active Booking”.
2. **Xác định resource** cần khóa, thường là row Seat hoặc counter chung.
3. **Xác định entrypoint** của unit of work, ví dụ POST /bookings.
4. **Đặt transaction boundary ngoài** toàn bộ read-lock, validate, update và persist liên quan.
5. **Xác minh EntityManager enlistment**, DataSource và transaction manager đúng.
6. **Lấy khóa trước khi đưa ra quyết định** phụ thuộc state có thể đổi.
7. **Kiểm tra lại trạng thái sau khi có khóa**.
8. **Áp domain logic và DB constraints**.
9. **Không đưa thao tác network chậm** vào khoảng giữ khóa.
10. **Commit/rollback toàn bộ** theo semantics business.
11. **Đặt timeout và phân loại lỗi**, tránh retry vô hạn.
12. **Kiểm thử bằng hai transactions** trên database thật.

### Sơ đồ quyết định

~~~text
Cần đọc state rồi ghi mà không bị transaction khác chen vào?
                           |
                           v
Invariant nằm trên một row cụ thể?
               |                       |
              Có                      Không
               |                       |
               v                       v
PESSIMISTIC_WRITE row             Xác định counter/aggregate,
hoặc atomic conditional UPDATE    predicate, constraints/isolation
               |                       |
               +-----------+-----------+
                           |
                           v
Đã có transaction phù hợp bao trùm operation?
               |                       |
              Không                    Có
               |                       |
               v                       |
Mở transaction tại service            |
               +-----------+-----------+
                           |
                           v
Yêu cầu lock trên transaction-bound resource
                           |
                           v
Đã lấy được lock?
           |                             |
          Không                          Có
           |                             |
           v                             v
Timeout/deadlock policy           Re-read/check current state
rollback/retry nếu an toàn                 |
                                         v
                                 Apply changes + constraints
                                         |
                                         v
                                 Commit hoặc rollback
                                         |
                                         v
                                 Lock được giải phóng
~~~

## 53. Bài tập thực hành

### Bài 1 — Có transaction không?

Một `RESOURCE_LOCAL` EntityManager gọi:

~~~java
em.find(Seat.class, 10L, LockModeType.PESSIMISTIC_WRITE);
~~~

trước `tx.begin()`. Điều gì có thể xảy ra?

**Gợi ý:** `TransactionRequiredException` vì pessimistic lock cần transaction active.

### Bài 2 — Khi nào lock được nhả?

Service begin transaction, lấy PESSIMISTIC_WRITE, thay đổi Seat, gọi `em.flush()` rồi còn thực thi ba query khác trước commit. Lock thường được giữ tới thời điểm nào?

**Gợi ý:** tới khi database transaction commit/rollback, không phải tới flush.

### Bài 3 — Repository method return

Repository method có `@Transactional` tự mở transaction để SELECT FOR UPDATE rồi return Seat cho service không có outer transaction. Service tiếp tục quyết định đặt ghế. Điểm hở concurrency ở đâu?

**Gợi ý:** lock đã được giải phóng khi repository transaction kết thúc; quyết định service dựa trên state không còn được bảo vệ.

### Bài 4 — Outer REQUIRED

Outer CheckoutService có transaction; inner SeatService REQUIRED lấy lock rồi return. Lock có tự nhả khi inner return không?

**Gợi ý:** không; nó tham gia outer transaction.

### Bài 5 — REQUIRES_NEW

Outer Order transaction gọi inner REQUIRES_NEW reserve Seat, inner commit, outer rollback. Vì sao trạng thái có thể sai?

**Gợi ý:** reservation đã commit trong transaction khác.

### Bài 6 — Clear

Sau `em.lock(seat, PESSIMISTIC_WRITE)`, gọi `em.clear()` rồi sleep. Các transaction khác có chắc được phép UPDATE Seat ngay không?

**Gợi ý:** không; clear không kết thúc database transaction.

### Bài 7 — Close

Có nên gọi `em.close()` thay `tx.commit()` để chủ động nhả lock không?

**Gợi ý:** không; kết thúc transaction tường minh/qua transaction manager.

### Bài 8 — JTA

EntityManager JTA-managed có nên gọi `em.getTransaction().begin()` không?

**Gợi ý:** không; dùng JTA/container transaction boundary.

### Bài 9 — Pessimistic read/write

PESSIMISTIC_READ có bảo đảm DBMS dùng shared row lock cho phép mọi readers chạy đồng thời không?

**Gợi ý:** không; provider/DBMS có thể triển khai khác.

### Bài 10 — Lock timeout

Một query có hint `jakarta.persistence.lock.timeout=2000`. Có được hứa nó luôn thất bại đúng sau 2 giây không?

**Gợi ý:** không; phụ thuộc provider/driver/DBMS và timeout khác.

### Bài 11 — Exception

Một `PessimisticLockException` xảy ra. Nên tiếp tục thao tác khác và commit transaction cũ như không có lỗi?

**Gợi ý:** không; xử lý rollback/trạng thái transaction theo contract.

### Bài 12 — Deadlock

A khóa Seat#10 rồi Seat#20; B khóa Seat#20 rồi Seat#10. Rủi ro gì và làm sao giảm?

**Gợi ý:** deadlock; khóa theo thứ tự ID ổn định.

### Bài 13 — HTTP

Người dùng mở trang Seat trong ba phút. Có nên giữ PESSIMISTIC_WRITE từ GET tới POST?

**Gợi ý:** không; dùng lock trong transaction ngắn của POST hoặc trạng thái reservation có expiry.

### Bài 14 — OSIV

EntityManager vẫn mở ở lúc JSON serialization. Lock của service transaction đã commit có còn mặc nhiên không?

**Gợi ý:** không; EntityManager lifetime khác database transaction.

### Bài 15 — Kiểm tra status

Sau khi Transaction B chờ A commit rồi lấy lock, có được dùng trạng thái Seat đã đọc trước khi chờ để quyết định ngay?

**Gợi ý:** không; cần state được bảo vệ/current theo transaction và DB rules.

### Bài 16 — Lock Event

Khóa Event root bằng PESSIMISTIC_WRITE có mặc nhiên khóa mọi Seat trong collection không?

**Gợi ý:** không; cần xem scope/mapping/DBMS và bảo vệ đúng invariant.

### Bài 17 — Extended scope

`PessimisticLockScope.EXTENDED` có phải một lời hứa khóa toàn bộ entity graph vô hạn không?

**Gợi ý:** không; chỉ có semantics cụ thể và provider-dependent.

### Bài 18 — COUNT(*) invariant

Hai transaction lock hai Seat khác nhau nhưng cùng đọc COUNT(booking)=499, đều insert và vượt limit 500. Vì sao khóa Seat không đủ?

**Gợi ý:** invariant là một predicate/tổng nhiều rows; cần tài nguyên chung hoặc constraint/isolation.

### Bài 19 — Atomic SQL

Viết SQL claim một Seat nếu còn AVAILABLE và tenant đúng. Vì sao affectedRows=1 có ý nghĩa?

**Gợi ý:** `UPDATE ... WHERE status='AVAILABLE' AND tenant_id=?` giúp check-and-set trong một statement.

### Bài 20 — Atomicity

Atomic UPDATE Seat thành RESERVED xong auto-commit; INSERT Booking sau đó lỗi. Transaction boundary đã đúng chưa?

**Gợi ý:** chưa; Seat và Booking phải cùng một transaction khi cần nguyên tử.

### Bài 21 — Spring proxy

Một bean gọi `this.lockSeat()`, trong đó lockSeat có `@Transactional`. Có chắc transaction được tạo theo annotation không?

**Gợi ý:** không trong mô hình proxy thông thường.

### Bài 22 — Read-only

Một method `@Transactional(readOnly=true)` gọi PESSIMISTIC_WRITE và đổi Seat. Có nên xem đó là cấu hình mặc định đúng?

**Gợi ý:** không; dùng writable transaction và kiểm tra DB behavior.

### Bài 23 — Connection khác

JPA Transaction A giữ Seat lock, helper dùng DriverManager connection khác để UPDATE chính Seat ấy và chờ. Thread A đang đợi helper return trước commit. Có thể xảy ra gì?

**Gợi ý:** chờ lock gây timeout/deadlock do hai transaction khác nhau.

### Bài 24 — Kiểm thử

Test dùng hai Java threads nhưng chia sẻ cùng EntityManager. Có kiểm thử đúng pessimistic locking giữa hai transaction không?

**Gợi ý:** không; mỗi thread/transaction có EntityManager riêng.

### Bài 25 — Timeout test

Vì sao `Thread.sleep(100)` ở test không đủ chứng minh transaction B đang blocked trên database row?

**Gợi ý:** scheduling khác nhau; dùng latch/instrumentation/DB observation hoặc timeout policy có kiểm soát.

### Bài 26 — Lock và version

Seat có cả `@Version` và PESSIMISTIC_WRITE. Khi transaction commit, version có còn lưu trong DB không, còn row lock thì sao?

**Gợi ý:** version persistent theo update rules; transaction-held lock được giải phóng.

### Bài 27 — Query JOIN

JPQL JOIN Event và Seat với `setLockMode(PESSIMISTIC_WRITE)` có được mặc định khóa tất cả entities xuất hiện trong FROM/JOIN không?

**Gợi ý:** không; xem provider SQL, alias lock scope và semantics DBMS.

### Bài 28 — SKIP LOCKED

Một worker queue muốn claim task khác nếu task đầu đang bị khóa. SKIP LOCKED có thể giúp thế nào? Có portable JPA không?

**Gợi ý:** có thể bỏ qua locked rows ở DBMS hỗ trợ; không phải hành vi JPA portable mặc định.

### Bài 29 — Side effects

Service giữ PESSIMISTIC_WRITE rồi gửi email báo “đặt thành công”, nhưng commit sau đó thất bại. Điều gì sai?

**Gợi ý:** email đã gửi không rollback; dùng outbox/confirm sau commit.

### Bài 30 — Transaction duration

Trong một service đặt ghế, có thể chuyển validation không phụ thuộc dữ liệu cạnh tranh ra trước lock không?

**Gợi ý:** có; giảm thời gian lock. Nhưng validation phụ thuộc state ghế phải được kiểm tra khi đang được bảo vệ.

## 54. Bảng ghi nhớ nhanh

| Câu hỏi | Quy tắc |
| --- | --- |
| Pessimistic lock yêu cầu gì? | Transaction active, resource đã enlist phù hợp |
| Lock được giữ ở đâu? | Database transaction, không phải Java object |
| Khi nào nhả lock? | Thường lúc COMMIT/ROLLBACK của transaction giữ khóa |
| Method con return có nhả lock không? | Không nếu outer transaction vẫn đang mở |
| `em.flush()` nhả lock không? | Không |
| `em.clear()`/`detach()` nhả lock không? | Không |
| `EntityManager.close()` thay commit được không? | Không, cần quản lý transaction đúng |
| Gọi PESSIMISTIC_WRITE không có transaction? | TransactionRequiredException |
| `PESSIMISTIC_READ` luôn shared lock? | Không, DBMS/provider-dependent |
| `PESSIMISTIC_WRITE` là SQL cố định? | Không; provider/dialect chọn cách thực hiện |
| Spring REQUIRED tham gia outer? | Có khi có outer transaction |
| REQUIRES_NEW có giúp giữ atomicity outer? | Không mặc định |
| MANDATORY có thể hữu ích? | Có, yêu cầu caller có transaction |
| Spring self-invocation? | Có thể bỏ qua transaction proxy |
| JTA EntityManager dùng getTransaction? | Không |
| Lock Event có khóa mọi Seat? | Không mặc định |
| Lock timeout hint có luôn được hỗ trợ? | Không hoàn toàn portable |
| Deadlock xử lý thế nào? | Rollback/retry transaction mới khi an toàn, thứ tự lock |
| Dùng lock xuyên HTTP user think time? | Không; reservation workflow |
| OSIV mở lâu nghĩa lock giữ lâu? | Không; context và TX khác nhau |
| Chỉ cần khóa một row cho invariant nhiều rows? | Chưa chắc |
| Atomic UPDATE claim ghế? | Một lựa chọn tốt nếu logic đơn giản |
| Đặt ghế và tạo Booking cần gì? | Cùng transaction nếu phải atomic |
| Kiểm thử đúng? | Hai EM, hai TX, DBMS thật, observable locking |

## Kết luận

**Phạm vi giao dịch cần có để giữ khóa** là nền tảng của pessimistic locking trong JPA. Khi yêu cầu `LockModeType.PESSIMISTIC_WRITE` hoặc `PESSIMISTIC_READ`, ứng dụng phải có **transaction phù hợp đang hoạt động**, và mọi quyết định nghiệp vụ cần được bảo vệ phải diễn ra **trong cùng transaction ấy**. Khóa được database quản lý; nó không gắn với thời gian sống của một biến Java, một method hoặc một EntityManager. `flush()`, `clear()`, `detach()` và việc method con return không phải thao tác giải phóng database lock. Ranh giới commit/rollback thực sự mới là mốc quan trọng.

Đối với Spring hoặc JTA, hãy xác định **ai sở hữu transaction**, transaction nào được repository/helper tham gia và có outer boundary hay không. `REQUIRED` có thể khiến lock giữ lâu tới outer commit; `REQUIRES_NEW` có thể làm một bước commit độc lập và phá tính nguyên tử nếu dùng sai. Bên cạnh đó, lock không tự bảo vệ mọi association hoặc invariant nhiều rows, nên phải kết hợp domain validation, database constraints, lock scope hợp lý và isolation phù hợp.

Một thiết kế đáng tin cậy sẽ **bắt đầu transaction trước khi lấy khóa, lấy đúng khóa cho tài nguyên/invariant, kiểm tra lại state khi đã được bảo vệ, cập nhật toàn unit of work rồi commit hoặc rollback càng sớm càng tốt**. Giữ transaction ngắn, không chờ người dùng hay API ngoài khi đang giữ lock, đặt timeout và kiểm thử bằng hai transaction thực sẽ giúp hệ thống tránh double booking mà không tạo ra lock contention không cần thiết.
