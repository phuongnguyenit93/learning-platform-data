# TOCTOU regression test

## 1. Mục tiêu bài học

Trong chương **TOCTOU Defense** của module bảo mật logic nghiệp vụ, một bản sửa lỗi chỉ có giá trị lâu dài khi có kiểm thử bắt được việc lỗi quay trở lại. Bài học này hướng dẫn biến tình huống “hai yêu cầu cùng vượt qua kiểm tra” thành một regression test có lịch thực thi kiểm soát được và tiêu chí đúng sai dựa trên dữ liệu đã commit.

Sau bài học, bạn có thể:

- Viết rõ bất biến nghiệp vụ mà một race condition có thể phá vỡ.
- Đặt điểm đồng bộ đúng giữa bước kiểm tra và bước sử dụng dữ liệu.
- Kiểm tra kết quả của từng yêu cầu, dữ liệu cuối cùng và tác dụng phụ.
- Phân biệt kiểm thử tranh chấp tài nguyên với kiểm thử idempotency.
- Mở rộng kịch bản sang thu hồi quyền, thay đổi giá và vô hiệu hóa phê duyệt.
- Đưa kiểm thử vào CI với timeout, dữ liệu độc lập và thông tin chẩn đoán hữu ích.

Ví dụ xuyên suốt dùng Java, JDBC, JUnit 5 và PostgreSQL. Cơ chế kiểm thử có thể áp dụng cho những stack khác, nhưng hành vi khóa và isolation phải được xác nhận trên hệ quản trị dữ liệu thực tế.

## 2. Regression test cần bắt điều gì?

TOCTOU là tình huống chương trình kiểm tra trạng thái một tài nguyên, rồi sử dụng tài nguyên sau khi trạng thái đó đã thay đổi khiến kết quả kiểm tra không còn hợp lệ. Đây là dạng điểm yếu được mô tả trong [CWE-367 của MITRE](https://cwe.mitre.org/data/definitions/367.html).

Trong nghiệp vụ, “tài nguyên” có thể là lượt dùng mã giảm giá, số dư, hạn mức hoàn tiền, trạng thái đơn hàng, quyền trên một đối tượng hoặc phiên bản nội dung đã được phê duyệt.

Xét một mã giảm giá còn đúng một lượt sử dụng:

~~~java
// Minh họa cách làm có lỗi; không dùng làm bản sửa.
int remaining = repository.readRemaining(couponId);

if (remaining <= 0) {
    return SOLD_OUT;
}

repository.setRemaining(couponId, remaining - 1);
repository.insertRedemption(couponId, actorId);
return GRANTED;
~~~

Nếu hai transaction cùng đọc được giá trị 1, cả hai có thể ghi giá trị 0 và cùng tạo bản ghi sử dụng mã. Số lượt còn lại không âm, nhưng hệ thống đã cấp hai lợi ích từ một lượt.

Lịch gây lỗi:

~~~mermaid
sequenceDiagram
    participant A as Yêu cầu A
    participant DB as Cơ sở dữ liệu
    participant B as Yêu cầu B
    A->>DB: Đọc remaining
    DB-->>A: 1
    B->>DB: Đọc remaining
    DB-->>B: 1
    Note over A,B: Cả hai đã vượt qua kiểm tra
    A->>DB: Ghi remaining = 0, tạo redemption A
    A->>DB: COMMIT
    B->>DB: Ghi remaining = 0, tạo redemption B
    B->>DB: COMMIT
    Note over DB: remaining = 0 nhưng có 2 redemption
~~~

Một regression test tốt phải tạo được lịch này ở phiên bản có lỗi và phát hiện rằng số lợi ích được cấp vượt quá số lượt ban đầu. Chỉ kiểm tra “không có exception” hoặc “remaining không âm” sẽ bỏ sót lỗi.

## 3. Viết hợp đồng trước khi viết luồng song song

### 3.1. Bất biến và kết quả được phép

Giả sử dữ liệu được cô lập cho một mã giảm giá mới:

- Ban đầu có một lượt.
- Mỗi yêu cầu hợp lệ tiêu thụ đúng một lượt và tạo đúng một redemption.
- Không có thao tác nạp thêm lượt, hoàn lượt hay xóa redemption trong lúc kiểm thử.
- Hai người dùng hợp lệ gửi hai yêu cầu nghiệp vụ độc lập.
- Không có lỗi hạ tầng được chủ động đưa vào kịch bản này.

Gọi R là số lượt còn lại và N là số redemption đã commit cho mã giảm giá đó. Bất biến là:

~~~text
R >= 0
N <= 1
R + N = 1
~~~

Sau khi cả hai yêu cầu kết thúc bình thường, kỳ vọng cụ thể là:

~~~text
Số kết quả GRANTED  = 1
Số kết quả SOLD_OUT = 1
R                  = 0
N                  = 1
~~~

Hai phía của hợp đồng đều cần kiểm tra. Nếu tất cả yêu cầu bị từ chối, dữ liệu có thể vẫn an toàn nhưng chức năng hợp lệ đã bị phá vỡ. Nếu một yêu cầu trả lỗi sau khi vẫn tạo redemption, chỉ đếm kết quả trả về cũng không phát hiện được sai lệch.

### 3.2. Phân biệt yêu cầu độc lập và yêu cầu gửi lại

| Kịch bản | Quan hệ giữa các yêu cầu | Kỳ vọng chính |
|---|---|---|
| Tranh chấp lượt cuối | Hai thao tác độc lập, có thể dùng hai idempotency key khác nhau | Chỉ một thao tác được cấp lượt |
| Gửi lại cùng thao tác | Cùng principal, cùng phạm vi key, cùng payload chuẩn hóa | Không tạo thêm tác dụng nghiệp vụ |
| Dùng lại key với payload khác | Cùng phạm vi key nhưng nội dung khác | Phát hiện xung đột theo hợp đồng API |
| Hai người dùng khác nhau dùng cùng chuỗi key | Phụ thuộc phạm vi key do hệ thống định nghĩa | Không trả nhầm dữ liệu hoặc kết quả giữa các principal |

Với một API hỗ trợ phát lại kết quả idempotent, hai phản hồi thành công cho cùng một thao tác có thể hoàn toàn hợp lệ. Điều phải giữ là cùng một kết quả nghiệp vụ và một tác dụng đã commit.

Ngược lại, cơ chế chống trùng theo key không tự bảo vệ được lượt cuối khi hai yêu cầu dùng hai key khác nhau.

## 4. Điều khiển lịch thực thi thay vì hy vọng xảy ra race

### 4.1. Vì sao sleep và gửi đồng thời chưa đủ?

Hai thread bắt đầu gần nhau không có nghĩa chúng cùng đi qua cửa sổ TOCTOU. Một thread có thể đọc, cập nhật và commit xong trước khi thread còn lại được cấp connection.

Những cách sau tạo cảm giác có kiểm thử đồng thời nhưng bằng chứng còn yếu:

- Gọi hai lần liên tiếp trên cùng thread.
- Thêm một khoảng sleep rồi hy vọng request kia đã đến đúng chỗ.
- Gửi nhiều request nhưng dùng connection pool chỉ có một connection khả dụng.
- Chạy hai task bên trong một transaction do fixture quản lý.
- Chỉ dùng mock repository, không thực thi hành vi tranh chấp của database.

Cần một **điểm đồng bộ sau lần đọc dễ bị lỗi**, không chỉ một điểm xuất phát chung.

### 4.2. Lịch kiểm thử có kiểm soát

Với cách bảo vệ bằng cập nhật có điều kiện, lịch mong muốn là:

1. A đọc thấy remaining = 1 và dừng tại test hook.
2. B đọc thấy remaining = 1 và cũng dừng tại hook.
3. Thread điều phối xác nhận cả hai đã đến đúng điểm.
4. Điều phối mở cổng để cả hai tiếp tục.
5. Database phân xử hai thao tác cập nhật.
6. Chờ cả hai transaction hoàn tất rồi đọc trạng thái bằng connection mới.

Trong Java, CountDownLatch có thể làm bộ đếm “hai worker đã sẵn sàng” và cổng “cho phép tiếp tục”. Đây là cơ chế dùng một lần; mỗi lượt kiểm thử phải tạo bộ latch mới. Xem [tài liệu CountDownLatch của Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

Test hook chỉ phục vụ điều phối lịch thực thi. Nó không được thay thế câu SQL bảo vệ, nuốt lỗi hoặc tự biến mọi kết quả thành thành công.

Trong ứng dụng có hook kiểm thử, bản chạy thông thường dùng triển khai không làm gì. Không mở một endpoint công khai cho phép người gọi tùy ý giữ transaction ở trạng thái chờ.

### 4.3. Hook phải phù hợp với cách sửa

Nếu bản sửa dùng SELECT FOR UPDATE trước khi đọc, worker A có thể giữ khóa khiến B chưa thể đọc xong. Một barrier đòi cả A và B cùng vượt qua lần đọc sẽ tự tạo bế tắc trong test.

Với khóa bi quan, hãy điều phối theo lịch khác:

~~~text
A lấy khóa và đọc trạng thái.
Điều phối cho B bắt đầu thao tác tranh chấp.
A được phép tiếp tục và commit.
B tiếp tục sau khi có thể lấy khóa, rồi đánh giá lại điều kiện.
Kiểm tra kết quả và bất biến.
~~~

Nếu cần khẳng định B thực sự đã chờ khóa, dùng quan sát trạng thái chờ của database hoặc instrumentation phù hợp. Việc B chưa trả kết quả sau một khoảng thời gian ngắn chưa đủ để chứng minh nó đang chờ đúng loại khóa.

Mục tiêu của test là tái hiện nguy cơ và xác minh hợp đồng. Test không nên bắt buộc mọi cách sửa phải có cùng vị trí khóa.

## 5. Chuẩn bị dữ liệu và ranh giới transaction

Dùng một database PostgreSQL dành riêng cho kiểm thử, cùng loại isolation và các constraint liên quan với môi trường triển khai.

Schema tối thiểu của ví dụ:

~~~sql
CREATE TABLE coupon (
    id UUID PRIMARY KEY,
    remaining INTEGER NOT NULL CHECK (remaining >= 0)
);

CREATE TABLE coupon_redemption (
    id UUID PRIMARY KEY,
    coupon_id UUID NOT NULL REFERENCES coupon(id),
    actor_id UUID NOT NULL
);
~~~

Không thêm unique constraint trên riêng coupon_id: một mã có nhiều lượt hoàn toàn có thể được nhiều người dùng sử dụng. Hai người dùng trong test cũng có actor_id khác nhau, để không vô tình kiểm thử một quy tắc “mỗi người dùng chỉ được dùng một lần”.

Các điều kiện chạy cần rõ ràng:

- Fixture được commit trước khi tạo hai tác vụ.
- Mỗi tác vụ mở connection và transaction riêng.
- Pool phải cho phép ít nhất hai connection làm việc đồng thời.
- Thread điều phối không giữ khóa trên dữ liệu fixture.
- Dữ liệu được đọc lại từ database sau khi hai tác vụ hoàn tất.
- Timeout có giới hạn ở cả tầng điều phối, câu lệnh và kết nối mạng.
- Mỗi test có coupon_id riêng và chỉ dọn dữ liệu thuộc coupon_id đó.

Nếu dùng Spring, transaction gắn với thread điều phối không tự trở thành transaction của worker. Cần cấu hình đường gọi service sao cho mỗi worker thực sự đi qua transaction boundary dự kiến. Tránh self-invocation làm bỏ qua proxy transaction.

Không dùng dữ liệu fixture chưa commit rồi chờ worker “nhìn thấy” nó. Worker có thể không đọc được dữ liệu hoặc bị chặn bởi transaction của chính test.

## 6. Cơ chế bảo vệ được kiểm thử trong ví dụ

Bước quyết định cấp lượt dùng câu lệnh sau:

~~~sql
UPDATE coupon
SET remaining = remaining - 1
WHERE id = ?
  AND remaining > 0;
~~~

Chỉ khi số dòng cập nhật bằng 1, transaction mới được tạo redemption. Nếu bằng 0, yêu cầu không được cấp lượt. Cập nhật lượt và tạo redemption phải nằm trong cùng transaction.

Ở PostgreSQL với Read Committed, khi một UPDATE gặp dòng đang được cập nhật, nó có thể phải chờ transaction kia; sau khi transaction kia commit, điều kiện WHERE được đánh giá lại trên phiên bản dòng mới. Xem [tài liệu transaction isolation của PostgreSQL](https://www.postgresql.org/docs/current/transaction-iso.html).

Lần SELECT trước UPDATE trong ví dụ được giữ lại để tạo điểm điều phối và minh họa kết quả kiểm tra cũ. Quyết định có thẩm quyền vẫn là số dòng của UPDATE có điều kiện. Trong một triển khai đơn giản hơn, có thể bỏ SELECT này nếu không cần dữ liệu cho mục đích khác.

Giới hạn của cơ chế cũng phải rõ: điều kiện remaining > 0 trên dòng coupon chỉ bảo vệ lượng lượt của dòng đó. Nó không tự bảo vệ quyền đang nằm ở bảng khác, giá vừa thay đổi, hoặc bất biến tổng hợp qua nhiều dòng.

## 7. Ví dụ integration test bằng Java và JDBC

### 7.1. Phạm vi của mã mẫu

Đoạn mã sau là một lớp kiểm thử JUnit 5 dùng JDBC thật. Cần có PostgreSQL JDBC driver, JUnit 5 và schema ở phần trước.

Cấu hình ba biến môi trường cho database kiểm thử:

~~~text
TOCTOU_TEST_JDBC_URL
TOCTOU_TEST_DB_USER
TOCTOU_TEST_DB_PASSWORD
~~~

Cấu hình giới hạn thời gian thiết lập kết nối và thời gian chờ socket theo driver đang dùng. Timeout của Future không tự dừng một truy vấn đang mắc kẹt do mạng.

Ví dụ kiểm tra bất biến cấp lượt tại ranh giới database; nó không thay thế kiểm thử HTTP, xác thực principal hoặc quyền truy cập coupon. actorId ở đây là hai danh tính đã hợp lệ trong phạm vi fixture.

~~~java
import org.junit.jupiter.api.Test;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Collections;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

final class CouponToctouTest {
    enum Outcome {
        GRANTED, SOLD_OUT
    }

    record DbState(int remaining, long redemptions) {}

    static final class RaceGate {
        final CountDownLatch checked = new CountDownLatch(2);
        final CountDownLatch release = new CountDownLatch(1);

        void afterEligibleRead() {
            checked.countDown();

            try {
                if (!release.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "Không được mở cổng sau bước đọc"
                    );
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(
                    "Worker bị ngắt tại điểm đồng bộ", e
                );
            }
        }
    }

    @Test
    void lastUseAllowsExactlyOneCommittedRedemption() throws Exception {
        UUID couponId = UUID.randomUUID();
        UUID actorA = UUID.randomUUID();
        UUID actorB = UUID.randomUUID();

        createCoupon(couponId, 1);

        RaceGate gate = new RaceGate();
        ExecutorService workers = Executors.newFixedThreadPool(2);
        Future<Outcome> first = null;
        Future<Outcome> second = null;

        try {
            first = workers.submit(
                () -> redeem(couponId, actorA, gate)
            );
            second = workers.submit(
                () -> redeem(couponId, actorB, gate)
            );

            assertTrue(
                gate.checked.await(5, TimeUnit.SECONDS),
                "Hai worker chưa cùng đọc được trạng thái hợp lệ: "
                    + couponId
            );

            gate.release.countDown();

            List<Outcome> outcomes = List.of(
                first.get(10, TimeUnit.SECONDS),
                second.get(10, TimeUnit.SECONDS)
            );

            DbState state = readCommittedState(couponId);

            assertAll(
                () -> assertEquals(
                    1, Collections.frequency(outcomes, Outcome.GRANTED),
                    "Phải có đúng một yêu cầu được cấp lượt"
                ),
                () -> assertEquals(
                    1, Collections.frequency(outcomes, Outcome.SOLD_OUT),
                    "Yêu cầu còn lại phải nhận kết quả hết lượt"
                ),
                () -> assertEquals(0, state.remaining()),
                () -> assertEquals(1L, state.redemptions()),
                () -> assertEquals(
                    1L, state.remaining() + state.redemptions(),
                    "Phải bảo toàn số lượt ban đầu"
                )
            );
        } finally {
            // Mở cổng cả khi assertion hoặc Future thất bại.
            gate.release.countDown();

            if (first != null) {
                first.cancel(true);
            }
            if (second != null) {
                second.cancel(true);
            }

            workers.shutdownNow();

            if (!workers.awaitTermination(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                    "Worker chưa dừng; giữ fixture để chẩn đoán: "
                        + couponId
                );
            }

            deleteFixture(couponId);
        }
    }

    static Outcome redeem(
        UUID couponId,
        UUID actorId,
        RaceGate gate
    ) throws SQLException {
        try (Connection c = open()) {
            c.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
            c.setAutoCommit(false);

            try {
                int seen;

                try (PreparedStatement s = statement(
                    c, "SELECT remaining FROM coupon WHERE id = ?"
                )) {
                    s.setObject(1, couponId);

                    try (ResultSet rows = s.executeQuery()) {
                        if (!rows.next()) {
                            throw new IllegalStateException(
                                "Thiếu coupon fixture"
                            );
                        }
                        seen = rows.getInt(1);
                    }
                }

                if (seen <= 0) {
                    c.rollback();
                    return Outcome.SOLD_OUT;
                }

                gate.afterEligibleRead();

                int changed;
                try (PreparedStatement s = statement(
                    c,
                    "UPDATE coupon SET remaining = remaining - 1 "
                        + "WHERE id = ? AND remaining > 0"
                )) {
                    s.setObject(1, couponId);
                    changed = s.executeUpdate();
                }

                if (changed == 0) {
                    c.rollback();
                    return Outcome.SOLD_OUT;
                }

                try (PreparedStatement s = statement(
                    c,
                    "INSERT INTO coupon_redemption "
                        + "(id, coupon_id, actor_id) VALUES (?, ?, ?)"
                )) {
                    s.setObject(1, UUID.randomUUID());
                    s.setObject(2, couponId);
                    s.setObject(3, actorId);
                    s.executeUpdate();
                }

                c.commit();
                return Outcome.GRANTED;
            } catch (SQLException | RuntimeException e) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    e.addSuppressed(rollbackFailure);
                }
                throw e;
            }
        }
    }

    static Connection open() throws SQLException {
        Connection c = DriverManager.getConnection(
            requiredEnv("TOCTOU_TEST_JDBC_URL"),
            requiredEnv("TOCTOU_TEST_DB_USER"),
            requiredEnv("TOCTOU_TEST_DB_PASSWORD")
        );

        try (Statement s = c.createStatement()) {
            s.setQueryTimeout(5);
            s.execute("SET statement_timeout = '5s'");
            s.execute("SET lock_timeout = '3s'");
        } catch (SQLException e) {
            try {
                c.close();
            } catch (SQLException closeFailure) {
                e.addSuppressed(closeFailure);
            }
            throw e;
        }

        return c;
    }

    static PreparedStatement statement(
        Connection c,
        String sql
    ) throws SQLException {
        PreparedStatement s = c.prepareStatement(sql);
        s.setQueryTimeout(5);
        return s;
    }

    static void createCoupon(UUID couponId, int remaining)
        throws SQLException {
        try (
            Connection c = open();
            PreparedStatement s = statement(
                c, "INSERT INTO coupon (id, remaining) VALUES (?, ?)"
            )
        ) {
            s.setObject(1, couponId);
            s.setInt(2, remaining);
            s.executeUpdate();
            // Connection mới ở chế độ auto-commit.
        }
    }

    static DbState readCommittedState(UUID couponId)
        throws SQLException {
        try (
            Connection c = open();
            PreparedStatement s = statement(
                c,
                "SELECT c.remaining, "
                    + "(SELECT count(*) FROM coupon_redemption r "
                    + "WHERE r.coupon_id = c.id) "
                    + "FROM coupon c WHERE c.id = ?"
            )
        ) {
            s.setObject(1, couponId);

            try (ResultSet rows = s.executeQuery()) {
                if (!rows.next()) {
                    throw new IllegalStateException(
                        "Coupon biến mất trước khi xác minh"
                    );
                }
                return new DbState(rows.getInt(1), rows.getLong(2));
            }
        }
    }

    static void deleteFixture(UUID couponId) throws SQLException {
        try (Connection c = open()) {
            c.setAutoCommit(false);

            try {
                try (PreparedStatement s = statement(
                    c, "DELETE FROM coupon_redemption WHERE coupon_id = ?"
                )) {
                    s.setObject(1, couponId);
                    s.executeUpdate();
                }

                try (PreparedStatement s = statement(
                    c, "DELETE FROM coupon WHERE id = ?"
                )) {
                    s.setObject(1, couponId);
                    s.executeUpdate();
                }

                c.commit();
            } catch (SQLException e) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    e.addSuppressed(rollbackFailure);
                }
                throw e;
            }
        }
    }

    static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                "Thiếu cấu hình kiểm thử: " + name
            );
        }
        return value;
    }
}
~~~

### 7.2. Vì sao các chi tiết này quan trọng?

**Hai transaction độc lập.** Mỗi lần redeem mở connection riêng. Hai worker không chia sẻ một đối tượng Connection và không dựa vào transaction của thread chạy test.

**Điểm hẹn sau lần đọc.** checked chỉ giảm sau khi worker đọc được trạng thái hợp lệ. Khi bộ đếm về 0, lịch đã xác nhận cả hai đều thấy còn lượt.

**Không quyết định theo giá trị cũ.** Biến seen giúp tạo kịch bản. Số dòng UPDATE mới quyết định ai được cấp lượt.

**Chỉ trả GRANTED sau commit.** Một lỗi khi INSERT hoặc commit không được chuyển thành kết quả thành công.

**Đọc bằng connection mới.** Kết quả xác minh không đến từ entity cache hoặc một đối tượng đã đọc trước khi tranh chấp.

**Không nuốt lỗi worker.** Future.get đưa lỗi SQL và lỗi runtime về thread test. Lock timeout hoặc mất kết nối làm test thất bại; chúng không được coi như một kết quả SOLD_OUT hợp lệ.

**Dọn dẹp sau khi worker dừng.** Nếu một assertion thất bại, cổng vẫn được mở và worker được yêu cầu dừng. Nếu worker không dừng trong giới hạn, test báo lỗi thay vì xóa fixture trong khi thao tác còn đang chạy.

Timeout 3, 5 và 10 giây là cấu hình minh họa. Điều chỉnh theo môi trường CI để đủ thời gian cho công việc hợp lệ; không tăng chúng nhằm che một lịch bị bế tắc.

Trong dự án thực, nên gọi service hoặc repository đang được ứng dụng sử dụng thay vì duy trì một bản sao thuật toán trong lớp test. Tách phần điều phối và fixture khỏi phần triển khai nghiệp vụ, rồi đưa hook vào đúng vị trí cần quan sát.

## 8. Chứng minh test thực sự bắt được lỗi cũ

Một test luôn xanh có thể chưa từng tái hiện được nguy cơ. Trong bước xác nhận hiệu lực của bộ kiểm thử, có thể dùng một phiên bản lỗi có kiểm soát để chứng minh assertion thất bại.

Với ví dụ trên, thay riêng khối UPDATE có điều kiện bằng:

~~~java
// Biến thể cố ý có lỗi, chỉ dùng để xác nhận năng lực phát hiện.
try (PreparedStatement s = statement(
    c, "UPDATE coupon SET remaining = ? WHERE id = ?"
)) {
    s.setInt(1, seen - 1);
    s.setObject(2, couponId);
    changed = s.executeUpdate();
}
~~~

Do hai worker đều đã đọc seen = 1, cả hai ghi remaining = 0. Với schema và isolation đã nêu, cả hai có thể commit redemption, và các assertion về số kết quả GRANTED, số redemption và bảo toàn lượt phải thất bại.

Điều đáng chú ý là constraint remaining >= 0 vẫn không bị vi phạm. Test cần kiểm tra cả lịch sử cấp lợi ích, thay vì chỉ kiểm tra giá trị của một cột.

Sau khi xác nhận test bắt lỗi, khôi phục triển khai an toàn và giữ test trong bộ regression. Không nới assertion để chấp nhận hai lần cấp lượt, không thêm sleep để làm lỗi khó xuất hiện và không retry test đến khi có một lần xanh.

Nếu test thất bại ngay vì không đến được điểm hẹn, đó là lỗi điều phối hoặc thiết lập môi trường; chưa phải bằng chứng rằng nó đã phát hiện vi phạm nghiệp vụ.

## 9. Các lịch cần bổ sung cho bảo mật logic nghiệp vụ

Test lượt cuối chỉ là một mẫu. Mỗi thay đổi giữa check và use cần được chuyển thành lịch cụ thể, có thứ tự commit và hợp đồng riêng.

### 9.1. Thu hồi quyền giữa bước kiểm tra và thao tác

Ví dụ người dùng A có quyền phê duyệt hồ sơ D. Hợp đồng được chọn là: **quyền phải còn hợp lệ tại điểm chuyển trạng thái phê duyệt được bảo vệ**.

Lịch cần kiểm tra:

~~~text
A đọc được quyền phê duyệt D.
A dừng trước bước chuyển trạng thái có thẩm quyền.
B thu hồi quyền của A trên D và commit.
A tiếp tục thao tác phê duyệt.
~~~

Nếu việc thu hồi đã commit trước điểm chuyển trạng thái theo hợp đồng, A phải bị từ chối và không tạo bản ghi phê duyệt thành công.

Nếu thiết kế khóa khiến B không thể commit trước khi A hoàn tất, đó là một thứ tự khác: A có thể được phép hoàn tất trước B. Test phải ghi nhận được thứ tự đó, thay vì giả định mọi thao tác đã bắt đầu đều đã có hiệu lực.

Cần xác minh:

- Trạng thái và phiên bản của đúng hồ sơ D.
- Principal, tenant và quyền trên đối tượng D.
- Không có audit record loại “phê duyệt thành công” hoặc outbox event tương ứng khi bị từ chối.
- Có thể có audit record “bị từ chối” nếu đó là chính sách của hệ thống.

Một điều kiện kiểm tra quyền ở bảng khác không mặc nhiên được bảo vệ bởi khóa trên dòng hồ sơ. Cần cơ chế phối hợp dữ liệu quyền và chuyển trạng thái phù hợp; regression test phải tác động vào đúng nguồn quyền đó.

### 9.2. Thay giá hoặc nội dung sau khi đã phê duyệt

Giả sử đơn hàng được duyệt ở phiên bản 7, với tổng tiền do server tính. Sau đó nội dung hoặc giá của đơn bị thay đổi thành phiên bản 8.

Lịch thử:

~~~text
A đọc đơn phiên bản 7 và bằng chứng phê duyệt phiên bản 7.
A dừng trước bước chốt đơn.
B sửa thông tin ảnh hưởng số tiền, tăng phiên bản lên 8 và commit.
A tiếp tục với dữ liệu phiên bản 7.
~~~

Nếu hợp đồng yêu cầu phê duyệt đúng phiên bản hiện tại, A phải nhận xung đột hoặc yêu cầu duyệt lại. Không được dùng phê duyệt phiên bản 7 để chốt tùy ý nội dung phiên bản 8.

Ngoài trạng thái cuối, kiểm tra số tiền thực sự ghi vào giao dịch, phiên bản được duyệt và việc không phát sinh thanh toán cho một phiên bản chưa được chấp thuận.

Nếu nghiệp vụ chủ động khóa một báo giá bất biến đến thời hạn nhất định, kỳ vọng có thể khác. Khi đó test phải xác minh giao dịch gắn với đúng báo giá còn hiệu lực, thay vì mặc định mọi thay đổi giá hiện tại đều làm thao tác cũ bất hợp lệ.

### 9.3. Hai nhánh của state machine tranh chấp

Một đơn đang ở trạng thái APPROVED có thể nhận đồng thời thao tác CAPTURE và CANCEL.

Không chỉ assert rằng trạng thái cuối thuộc tập CAPTURED hoặc CANCELLED. Cần kiểm tra lịch sử:

- Chỉ một chuyển trạng thái thắng theo hợp đồng.
- Nhánh bị từ chối không tạo tác dụng phụ của nhánh đó.
- Không tồn tại cả tác vụ thu tiền thành công và hủy trước thu tiền nếu mô hình không cho phép.
- Nếu có hoàn tiền bù trừ sau thu tiền, đó phải là một chuỗi trạng thái hợp lệ riêng.

Một giá trị trạng thái cuối có vẻ đúng vẫn có thể che giấu hai tác dụng phụ mâu thuẫn.

### 9.4. Gửi lại sau khi mất phản hồi

Lịch này kiểm tra sự kết hợp giữa transaction và idempotency:

~~~text
A được cấp lượt, tạo redemption và commit.
Phản hồi tới client bị mất hoặc bị ngắt có chủ đích.
Client gửi lại cùng thao tác với cùng idempotency key.
~~~

Kỳ vọng không phải “chỉ có một HTTP 2xx”. Kỳ vọng là cùng một kết quả nghiệp vụ được phát lại hoặc trạng thái xử lý phù hợp với hợp đồng, không có redemption hay thanh toán mới.

Thêm một test dùng hai key khác nhau để bảo đảm cơ chế chống trùng không che mất race của bất biến tài nguyên.

### 9.5. Rollback sau khi đã chiếm tài nguyên

Đặt fault injection ngay sau UPDATE thành công nhưng trước INSERT redemption, rồi chủ động ném lỗi.

Sau khi transaction thất bại:

~~~text
remaining = 1
redemption_count = 0
outbox_success_count = 0, nếu có outbox
~~~

Một yêu cầu hợp lệ tiếp theo phải vẫn dùng được lượt đó. Kịch bản này bắt lỗi chia transaction sai hoặc trừ lượt thành công nhưng mất bản ghi nghiệp vụ.

Nếu có retry tự động cho lỗi transaction, fault injection phải kiểm soát được phạm vi lần thử. Không để retry tự động biến kịch bản “rollback phải được quan sát” thành một lần thực thi thành công mà test không biết.

## 10. Kiểm tra tác dụng phụ và tiến trình bất đồng bộ

Với luồng thực tế, một thao tác thành công có thể tạo bản ghi nghiệp vụ, audit, outbox event và yêu cầu tới hệ thống thanh toán.

Tách các mốc xác minh:

| Mốc | Cách quan sát | Điều cần giữ |
|---|---|---|
| Transaction nghiệp vụ kết thúc | Đọc dữ liệu đã commit | Không cấp vượt tài nguyên; dữ liệu liên quan nhất quán |
| Outbox được tạo | Đếm theo business operation ID và loại event | Một ý định nghiệp vụ thành công theo hợp đồng |
| Consumer hoàn tất | Chờ có giới hạn theo trạng thái xử lý hoặc correlation ID | Không áp dụng trùng tác dụng nghiệp vụ |
| Đối soát bên ngoài | Tra cứu bằng operation ID hoặc key của provider | Không tạo thêm khoản thu hay lợi ích độc lập |

Một outbox event có thể được giao nhiều lần. Không dùng số lần consumer nhận message làm đại diện cho số lần nghiệp vụ được áp dụng.

Với tác vụ bất đồng bộ, dùng polling có deadline và điều kiện hoàn tất rõ ràng. Sau một khoảng sleep tùy ý, việc chưa thấy event thứ hai không chứng minh rằng event ấy sẽ không xuất hiện.

Muốn kiểm tra “không có thêm tác dụng”, cần biết các worker và consumer liên quan đã xử lý xong cửa sổ kiểm thử, hoặc có cơ chế xác định tất cả message thuộc kịch bản đã được đối soát.

Không suy ra database rollback sẽ hủy được lời gọi đã thành công tới hệ thống bên ngoài. Các lịch lỗi giữa gọi dịch vụ bên ngoài, ghi dữ liệu và retry phải được kiểm tra theo giao thức tích hợp cụ thể.

## 11. Ma trận regression tối thiểu

| Ca kiểm thử | Lịch được ép | Assertion chính |
|---|---|---|
| Một yêu cầu hợp lệ | Không có tranh chấp | Chức năng vẫn thành công, tiêu thụ đúng một lượt |
| Hai yêu cầu cho lượt cuối | Cả hai đọc hợp lệ trước UPDATE | Một GRANTED, một SOLD_OUT, một redemption |
| Hai lượt còn lại, hai yêu cầu | Cả hai cùng đọc trước UPDATE | Hai thao tác thành công nếu các điều kiện khác hợp lệ |
| Hai yêu cầu cùng key | Tranh chấp bản ghi idempotency | Một tác dụng nghiệp vụ, kết quả phản hồi đúng hợp đồng |
| Cùng key, payload khác | Gửi xen kẽ hai nội dung | Phát hiện xung đột, không ghi sai nội dung |
| Thu hồi quyền | Revoke commit trước điểm thao tác theo hợp đồng | Không chuyển trạng thái hoặc tạo tác dụng trái quyền |
| Sửa giá sau phê duyệt | Phiên bản mới commit trước bước chốt | Không dùng phê duyệt cũ sai phạm vi |
| Lỗi giữa hai lần ghi | UPDATE xong rồi lỗi trước INSERT | Rollback đầy đủ, lượt dùng được trở lại |
| Mất phản hồi sau commit | Commit trước khi retry cùng key | Không tạo thêm tác dụng nghiệp vụ |
| Hai instance ứng dụng | Mỗi instance xử lý một yêu cầu tranh chấp | Bất biến vẫn giữ qua ranh giới tiến trình |
| Hai đối tượng độc lập | Hai thao tác trên hai ID khác nhau | Không bị từ chối chỉ vì chia sẻ bộ điều phối test hoặc khóa sai phạm vi |

Với hệ thống nhiều instance, một kiểm thử hai thread trong cùng JVM chưa chứng minh cơ chế hoạt động qua nhiều tiến trình. Đặc biệt, một khóa synchronized trong JVM có thể làm test cục bộ xanh nhưng không điều phối được hai instance.

Nếu dùng nhiều request hơn số lượt, chỉ khẳng định “có đúng K thao tác thành công” khi tất cả đều hợp lệ, được xử lý đến kết quả cuối và hợp đồng không cho phép bỏ cuộc do timeout. Nếu chưa có những điều kiện đó, tách assertion an toàn “không vượt K” khỏi assertion về khả năng phục vụ.

## 12. Những lỗi khiến regression test đánh giá sai

### 12.1. Test xanh nhưng không tạo tranh chấp

Dấu hiệu: hai worker cùng bắt đầu nhưng không có bằng chứng chúng đã cùng đọc dữ liệu cũ.

Cách khắc phục: đặt hook tại vị trí cần quan sát, ghi nhận số worker đến điểm đó và tách timeout điều phối khỏi thất bại nghiệp vụ.

### 12.2. Chỉ kiểm tra phản hồi HTTP

Hai phản hồi có thể là một thành công và một lỗi, trong khi cả hai transaction đã tạo lợi ích.

Cách khắc phục: assert thêm dữ liệu đã commit và tác dụng phụ có thể truy xuất theo business operation ID.

### 12.3. Biến mọi exception thành từ chối hợp lệ

Cách làm có lỗi:

~~~java
try {
    return service.redeem(request);
} catch (Exception e) {
    return SOLD_OUT; // Che lỗi SQL, timeout và lỗi lập trình.
}
~~~

Chỉ những nhánh lỗi đã được hợp đồng định nghĩa mới được ánh xạ thành kết quả nghiệp vụ tương ứng. Mất kết nối, timeout và lỗi fixture phải hiện lên là lỗi của test.

Nếu hệ thống dùng Serializable với retry, kiểm thử cần đi qua chính sách retry thực tế. Không coi mọi serialization failure là một lần từ chối nghiệp vụ hợp lệ, cũng không khẳng định một cặp mã lỗi áp dụng được cho mọi isolation level.

### 12.4. Fixture vô tình tuần tự hóa tất cả yêu cầu

Connection pool một connection, executor một thread, transaction fixture chưa kết thúc hoặc mock có khóa toàn cục đều có thể làm biến mất lịch gây lỗi.

Cách khắc phục: kiểm tra tính độc lập của session và khả năng cả hai worker thực sự đi đến điểm hẹn.

### 12.5. Khóa bi quan nhưng vẫn dùng barrier sau khóa cho cả hai worker

Đây có thể là lỗi thiết kế lịch kiểm thử, không phải bằng chứng hệ thống có deadlock nghiệp vụ.

Cách khắc phục: xác định worker nào phải giữ khóa, worker nào phải chờ và thời điểm nào được mở cổng.

### 12.6. Dùng lại dữ liệu hoặc latch giữa các test

Một redemption cũ, fixture bị thay đổi hoặc latch đã mở có thể làm kết quả phụ thuộc thứ tự chạy.

Cách khắc phục: tạo ID và bộ điều phối mới cho mỗi ca; chỉ cleanup theo dữ liệu của ca đó.

### 12.7. Chỉ chạy stress test nhiều lần

Chạy 10.000 request không đảm bảo một lịch quan trọng đã xảy ra. Stress test vẫn hữu ích để mở rộng độ phủ tải, tài nguyên và lịch thực thi, nhưng nên bổ sung cho ca có điều phối rõ ràng.

## 13. Đưa kiểm thử vào CI và điều tra thất bại

Các ca có lịch kiểm soát nên chạy trong bộ integration test thường xuyên. Kịch bản nhiều instance hoặc fault injection phức tạp có thể nằm trong nhóm kiểm thử riêng với môi trường được chuẩn bị phù hợp.

Khi thất bại, thu thập đủ thông tin để phân biệt ba nhóm:

1. **Không tạo được lịch:** worker không đến hook, thiếu connection, fixture chưa commit.
2. **Lịch đã tạo nhưng vi phạm hợp đồng:** cấp hai lượt, ghi sai phiên bản hoặc tác dụng phụ bị trùng.
3. **Không hoàn tất được thao tác:** SQL timeout, deadlock, serialization failure vượt chính sách retry hoặc sự cố kết nối.

Thông tin chẩn đoán nên gồm:

- Test name, coupon/order ID và correlation ID của từng yêu cầu.
- Principal hoặc tenant định danh theo chính sách log của hệ thống.
- Các mốc vào hook, mở cổng, bắt đầu cập nhật, commit hoặc rollback.
- Isolation level, số lần retry, SQLState và loại timeout nếu có.
- Kết quả từng Future, dữ liệu cuối và operation ID của tác dụng phụ.

Không log mật khẩu, token hoặc payload nhạy cảm chỉ để chẩn đoán race.

Nếu cần thử nhiều lịch ngẫu nhiên, ghi seed và đầu vào đủ để tái hiện. Không tự động chạy lại đến khi xanh rồi bỏ qua một lần đã vi phạm bất biến.

Một ca thất bại do deadlock cần được đọc cùng đồ thị khóa và thứ tự thực thi. Cần xác định lỗi nằm trong nghiệp vụ, chính sách retry hay chính hook kiểm thử trước khi thay đổi timeout.

## 14. Thực hành mở rộng

### Bài tập 1: Bắt lỗi ghi đè giá trị cũ

Dùng lịch hai worker cùng đọc remaining = 1. So sánh hai cách cập nhật:

~~~sql
-- Cách A: ghi giá trị được tính từ lần đọc trước.
UPDATE coupon SET remaining = ? WHERE id = ?;

-- Cách B: quyết định trên điều kiện tại bước cập nhật.
UPDATE coupon
SET remaining = remaining - 1
WHERE id = ? AND remaining > 0;
~~~

Giải thích vì sao constraint không âm có thể không bắt được lỗi của cách A, trong khi assertion đếm redemption có thể bắt được.

### Bài tập 2: Kiểm tra phê duyệt gắn với phiên bản

Thiết kế một test có A phê duyệt hoặc chốt hồ sơ phiên bản 7, B sửa thành phiên bản 8. Viết rõ điểm nào làm thao tác có hiệu lực, rồi chọn vị trí hook để thứ tự commit đúng với điều kiện cần kiểm tra.

Kết quả phải xác minh cả trạng thái, phiên bản được phê duyệt và số tác vụ thanh toán được tạo.

### Bài tập 3: Thay cơ chế bảo vệ

Giả sử bản sửa chuyển từ conditional UPDATE sang khóa dòng trước khi đọc.

Thiết kế lại lịch để A giữ khóa, B tranh chấp và A được mở cổng đúng lúc. Giữ nguyên bất biến đầu ra; thay phần điều phối phù hợp với vị trí khóa mới.

### Bài tập 4: Mở rộng sang hai instance

Gửi hai yêu cầu qua hai instance khác nhau nhưng dùng chung database kiểm thử. Chọn cơ chế điều phối kiểm thử có thể phối hợp qua tiến trình, rồi xác nhận test không dựa vào một khóa chỉ tồn tại trong JVM.

## 15. Điểm cần nhớ

Một TOCTOU regression test có sức phát hiện cần bốn thành phần gắn với nhau: **bất biến rõ ràng, lịch thực thi có bằng chứng, kết quả sau commit và xác minh tác dụng phụ**.

Với ví dụ lượt dùng cuối, việc remaining vẫn bằng 0 không đủ. Phải kiểm tra chỉ một yêu cầu thực sự được cấp lợi ích và chỉ một redemption được lưu. Khi chuyển sang quyền, phê duyệt, giá hoặc state machine, hãy giữ cách làm đó: chỉ rõ dữ liệu nào có thể đổi giữa check và use, ép đúng thứ tự thay đổi, rồi xác minh hợp đồng nghiệp vụ tại điểm thao tác có hiệu lực.

