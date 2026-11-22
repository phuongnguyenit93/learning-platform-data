# Kiểm soát ngẫu nhiên, UUID và bộ sinh định danh trong unit test nghiệp vụ

## 1. Vì sao sự ngẫu nhiên làm bài kiểm thử khó tin cậy?

Giả sử ứng dụng Spring Boot phát mã giảm giá, tạo mã đơn hàng hoặc cấp token. Mỗi lần chạy có thể cho kết quả khác nhau vì dùng `Math.random()`, `new Random()`, `UUID.randomUUID()` hoặc `SecureRandom`. Nếu bài kiểm thử khẳng định một giá trị cụ thể mà production code tự sinh ngẫu nhiên, test sẽ **chập chờn (flaky)**: có lúc PASS, có lúc FAIL dù mã nguồn không thay đổi.

Ví dụ về cách viết dễ gây lỗi:

~~~java
class CouponService {
    int discountPercent() {
        return Math.random() < 0.1 ? 25 : 5;
    }
}

// Sai mục tiêu: test này đôi khi FAIL, dù production code đúng.
// assertEquals(25, new CouponService().discountPercent());
~~~

Đoạn code trên chỉ minh họa vấn đề, **chưa phải file test độc lập**. Khi thực thi, `Math.random()` không có giá trị cố định mà unit test có thể chủ động chọn. Nếu 10% lượt trả 25 và 90% trả 5, assertion cố định `25` không thể bảo đảm PASS.

Ta cần tách hai trách nhiệm:

- **Nguồn dữ liệu biến thiên**: số ngẫu nhiên, UUID, số thứ tự, token, timestamp hoặc ID từ hệ thống ngoài.
- **Quy tắc nghiệp vụ**: kết quả phải là gì khi nguồn trả giá trị A, B hoặc lỗi.

Unit test tập trung vào **quy tắc nghiệp vụ chạy thật**, còn nguồn biến thiên được **tiêm vào (dependency injection)** để test thay bằng giá trị xác định. Việc production có sinh UUID chuẩn, database có chống trùng khóa hay token có đủ entropy cần những bài test khác với phạm vi rõ ràng.

Sau bài này, bạn cần có khả năng thiết kế thành phần nhận `RandomGenerator`/`IdGenerator`, chọn mock/stub/fake/seed hợp lý, kiểm các ranh giới, hiểu UUID v4 và ID tuần tự, tránh dùng số ngẫu nhiên có thể đoán được cho bảo mật, và xây suite lặp lại được trong CI.

## 2. Ba khái niệm khác nhau: random source, UUID và ID generator

| Khái niệm | Công việc | Ví dụ Java 17+ | Điều unit test nên kiểm |
| --- | --- | --- | --- |
| **Random source** | Cung cấp lựa chọn hoặc giá trị biến thiên, thường nằm trong một miền cụ thể | `RandomGenerator.nextInt(100)` | Ứng dụng phản ứng đúng khi nhận 0, 9, 10, 99… |
| **UUID** | Kiểu giá trị định danh 128-bit, có quy tắc format và nhiều phiên bản | `UUID.randomUUID()`, `UUID.fromString(...)` | Ứng dụng xử lý/lưu/trả đúng ID được cấp; nếu kiểm adapter, xác nhận version/variant |
| **ID generator** | Chính sách cấp định danh: random UUID, sequence, ID do DB cấp, hoặc ID theo thời gian/phân vùng | `IdGenerator.nextId()` hoặc `Supplier<UUID>` | SUT lấy ID đúng lúc, dùng đúng ID; lỗi hoặc trùng ID được xử lý theo hợp đồng |

**Ngẫu nhiên không đồng nghĩa duy nhất.** UUID v4 được thiết kế để xác suất trùng cực nhỏ khi nguồn ngẫu nhiên tốt, nhưng không có bảo đảm tuyệt đối. Một ID tăng dần có thể duy nhất trong **phạm vi của bộ đếm**, nhưng không tự duy nhất giữa nhiều instance hoặc sau khi restart nếu không có phối hợp.

**Duy nhất không đồng nghĩa bí mật.** Mã đơn hàng và ID trong URL thường dùng để nhận diện đối tượng; chúng không phải bằng chứng người gọi được phép truy cập. Không dùng “khó đoán UUID” để thay thế xác thực/phân quyền.

**Tái hiện được không đồng nghĩa an toàn bảo mật.** `Random` với seed cố định thích hợp để chạy lại một phép mô phỏng trong test; không phù hợp để tạo token đăng nhập, API key, password-reset secret hoặc mã OTP production.

## 3. Các nguồn số ngẫu nhiên trong Java 17+

### 3.1 RandomGenerator là ranh giới tốt cho logic nghiệp vụ

Từ Java 17, `java.util.random.RandomGenerator` là interface mô tả nhiều phương thức sinh ngẫu nhiên như `nextInt(bound)`, `nextLong()` và `nextDouble()`. Một lớp nghiệp vụ nhận interface này qua constructor sẽ dễ thay thế trong test.

~~~java
import java.util.random.RandomGenerator;

final class LuckyDraw {
    private final RandomGenerator random;

    LuckyDraw(RandomGenerator random) {
        this.random = random;
    }

    boolean isWinner() {
        return random.nextInt(100) < 10;
    }
}
~~~

Đây là **mã minh họa lớp**, chưa có file test hay phương thức `main`. `nextInt(100)` theo hợp đồng trả số nguyên từ **0 đến 99** (100 là cận trên loại trừ). Vì vậy, điều kiện `< 10` có 10 kết quả thắng trên 100 giá trị khả dĩ nếu nguồn phân phối đều: 0 đến 9.

Trong unit test, có thể mock interface để chủ động chọn ranh giới:

~~~java
RandomGenerator random = mock(RandomGenerator.class);

when(random.nextInt(100)).thenReturn(9);
assertTrue(new LuckyDraw(random).isWinner());

when(random.nextInt(100)).thenReturn(10);
assertFalse(new LuckyDraw(random).isWinner());
~~~

Đoạn trên thuộc **bên trong test có Mockito/JUnit và lớp LuckyDraw đã khai báo**; không phải file tự biên dịch một mình. Mỗi giá trị cố định tương ứng một nhánh nghiệp vụ cần chứng minh. Không cần gọi random hàng nghìn lần rồi trông chờ tần suất xấp xỉ 10%.

### 3.2 Random(seed): có thể tái hiện nhưng phụ thuộc thuật toán và trình tự gọi

`java.util.Random` nhận seed khi khởi tạo:

~~~java
import java.util.Random;

Random first = new Random(42L);
Random second = new Random(42L);

for (int i = 0; i < 5; i++) {
    if (first.nextInt(100) != second.nextInt(100)) {
        throw new AssertionError("Sequences differ");
    }
}
~~~

Với cùng thuật toán, seed, giới hạn và **trình tự gọi**, hai generator cho cùng dãy kết quả. Cách này hữu ích khi muốn tái hiện một ca kiểm thử, mô phỏng nhiều bước hoặc debug dữ liệu tổng hợp. Tuy nhiên:

- Thêm một lần gọi `nextInt(...)` trong code có thể thay đổi toàn bộ các kết quả tiếp theo, dù luật nghiệp vụ không đổi.
- Hai thuật toán PRNG khác nhau không bắt buộc tạo cùng dãy chỉ vì có cùng seed.
- Chia sẻ một generator có state giữa test chạy song song làm thứ tự tiêu thụ không xác định.
- Seed cố định làm dãy **có thể đoán được**; đừng dùng nó để tạo secret production.

Khi mục tiêu là kiểm **một nhánh hoặc ranh giới**, stub giá trị đầu vào trực tiếp thường rõ hơn seed. Khi mục tiêu là kiểm **hành vi nhiều bước có thứ tự**, seed hoặc fake sequence có thể phù hợp hơn.

### 3.3 Math.random, ThreadLocalRandom và new Random() bên trong method

Những lời gọi như `Math.random()`, `ThreadLocalRandom.current()` hoặc `new Random()` đặt trực tiếp trong method làm test khó kiểm soát và tạo một dependency ẩn. Mockito có thể hỗ trợ một số kỹ thuật mock tĩnh, nhưng không nên biến việc điều khiển nguồn ngẫu nhiên thành nhiệm vụ phức tạp khi chỉ cần thiết kế constructor nhận collaborator.

Trong code có xử lý đồng thời, **khả năng an toàn giữa các thread** của từng implementation là một mối quan tâm riêng: không giả định mọi implementation của `RandomGenerator` đều thread-safe. Chọn generator phù hợp vòng đời bean và tính song song của ứng dụng, hoặc tạo generator theo phạm vi sử dụng; không để test phụ thuộc thứ tự truy cập một nguồn chung.

## 4. Điểm chèn dependency: chỉ thay nguồn, giữ nghiệp vụ chạy thật

Một thiết kế đơn giản:

~~~text
                   +------------------------+
HTTP/Command ----> | CouponService THẬT    |
                   | - kiểm input           |
                   | - áp dụng ngưỡng       |
                   | - tạo Coupon           |
                   +-----------+------------+
                               |
                   +-----------+-----------+
                   |                       |
                   v                       v
             IdGenerator              RandomGenerator
           production: UUID v4       production: PRNG phù hợp
           unit test: fixed/sequence unit test: mock 0,9,10,99
~~~

Không mock chính `CouponService`: nếu đó là đối tượng chứa logic cần kiểm, test phải gọi implementation thật. SUT quyết định **khi nào** cần ID, **giá trị ngẫu nhiên nào** được coi là trúng thưởng và **kết quả cuối** cần chứa gì.

Đối với dependency nhỏ, có hai lựa chọn thường gặp:

~~~java
// Interface có tên thể hiện hợp đồng nghiệp vụ:
interface IdGenerator {
    UUID nextId();
}

// Hoặc dùng interface thư viện khi đủ rõ:
Supplier<UUID> idSupplier = UUID::randomUUID;
~~~

Đây là **hai thiết kế thay thế**, không phải đoạn file đầy đủ: cần import `java.util.UUID` và `java.util.function.Supplier`. Interface chuyên biệt có ích khi đặt tên hợp đồng, gắn metric hoặc điều khiển trường hợp lỗi; `Supplier<UUID>` thích hợp cho thành phần chỉ có một thao tác và không cần nhiều quy tắc.

Trong Spring Boot, có thể cung cấp các implementation production dưới dạng bean và constructor-inject vào service. Unit test tạo service trực tiếp bằng mock/fake; nó không cần `@SpringBootTest` chỉ để điều khiển randomness.

## 5. UUID: giá trị, phiên bản, parse và tính duy nhất

### 5.1 UUID v4 trong Java

`UUID.randomUUID()` trên Java 17 tạo UUID **version 4** bằng nguồn pseudo-random có độ mạnh mật mã theo hợp đồng JDK. UUID chứa 128 bit, trong đó một số bit dành cho version và variant; UUID v4 điển hình có **122 bit ngẫu nhiên**. Chuỗi thường hiển thị thành 36 ký tự ở dạng hex có dấu gạch nối:

~~~text
xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx
~~~

Trong đó nibble version là `4` và nibble variant ở vị trí `y` thuộc nhóm `8`, `9`, `a`, `b`. Đây là mẫu định dạng, **không phải regex đầy đủ để kiểm tính hợp lệ**. Trong code Java, có thể kiểm `uuid.version() == 4` và `uuid.variant() == 2` hoặc sử dụng `UUID.fromString(...)` để parse.

Ví dụ ID cố định trong unit test:

~~~java
UUID fixed = UUID.fromString("00000000-0000-4000-8000-000000000001");
~~~

Giá trị cố định không làm nó trở thành ngẫu nhiên; nó chỉ là dữ liệu test có định dạng UUID v4 hợp lệ. Đừng tạo UUID mới trong test rồi so sánh với UUID mới khác từ service; hai lời gọi không có lý do phải trùng nhau.

**UUID v4 giúp giảm mạnh nguy cơ trùng, không thay thế unique constraint.** Database vẫn cần ràng buộc duy nhất khi tính duy nhất là invariant nghiệp vụ. Nếu xảy ra conflict, ứng dụng cần chính sách xử lý có giới hạn (ví dụ retry chọn lọc khi xác nhận đúng lỗi trùng ID), không làm một vòng lặp retry vô tận.

### 5.2 Random UUID và name-based UUID khác nhau

Java còn có `UUID.nameUUIDFromBytes(byte[])` để sinh UUID **deterministic** từ mảng byte: cùng nội dung byte tạo cùng UUID (trong JDK, phương thức này là UUID version 3 dựa trên MD5). Ví dụ:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.UUID;

UUID first = UUID.nameUUIDFromBytes(
        "coupon:user-1".getBytes(StandardCharsets.UTF_8));
UUID again = UUID.nameUUIDFromBytes(
        "coupon:user-1".getBytes(StandardCharsets.UTF_8));

assertEquals(first, again);   // Cùng input -> cùng UUID.
assertEquals(3, first.version());
~~~

Đây là **đoạn mã trong phương thức JUnit test**; `assertEquals` cần import từ JUnit Jupiter. Nó minh họa khác biệt: *name-based* khi bài toán muốn cùng khóa logic tạo cùng ID; *random v4* khi cần cấp ID mới cho mỗi thực thể. Deterministic UUID không tự đảm bảo tính bí mật, không phù hợp làm reset token hay ID chống đoán.

Khi serialize API/JSON hoặc lưu database, chọn cách biểu diễn ID nhất quán. Chuỗi UUID cần parse và validate ở ranh giới; so sánh ID theo giá trị `UUID` thay vì so sánh các chuỗi bị khác chữ hoa/chữ thường. Mọi loại ID cần được kết hợp với kiểm tra quyền truy cập đối tượng.

### 5.3 UUID v7, sequence và các ID dạng khác

Một số hệ thống ưu tiên ID gần theo thời gian để hỗ trợ sắp xếp/index locality; **UUID v7** là một định dạng theo thời gian được chuẩn hóa. Ví dụ code trong bài này dùng API Java 17: `UUID.randomUUID()` tạo **v4**, không tự tạo UUID v7. Nếu cần v7, hãy chọn thư viện/generator hỗ trợ và kiểm rõ version đầu ra, quy tắc clock và collision. Không giả định gọi `UUID.randomUUID()` sẽ tự đổi thành v7.

| Kiểu ID | Điểm mạnh | Điều phải kiểm |
| --- | --- | --- |
| UUID v4 | Không cần cấp phát tập trung, khó trùng, phù hợp hệ phân tán | Unique constraint, format, cách index, không dùng như secret |
| UUID theo tên | Cùng input tạo cùng ID, hữu ích cho mapping xác định | Định nghĩa canonical input, encoding, trùng logic, rủi ro lộ input |
| Sequence/IDENTITY do database cấp | Duy nhất trong DB và dễ quản lý vòng đời bảng | Khóa DB, transaction, concurrency; không test bằng mock nếu cần tính chất sequence thật |
| Bộ đếm trong tiến trình (AtomicLong) | Dễ giả lập trong unit test, cấp ID tuần tự | Reset khi restart, nhiều instance dễ trùng; không thay DB sequence cho production phân tán |
| ID thời gian/phân vùng (ví dụ snowflake-style) | Tạo nhanh và có phần thứ tự thời gian | Clock rollback, node ID, giới hạn counter, đồng bộ instance |
| UUID v7 hoặc ID sortable khác | Có thể cải thiện tính gần theo thời gian | Trật tự thời gian không nhất thiết tuyệt đối, version/library, collision và clock |

Một **business reference** như `ORD-2026-000123` có thể cần định dạng riêng cho khách hàng, trong khi bảng vẫn dùng UUID/sequence làm khóa kỹ thuật. Tách trách nhiệm này nếu quy tắc đổi khác nhau; không sử dụng phép random thuần để “đảm bảo” số đơn hàng tăng dần.

## 6. Ví dụ hoàn chỉnh Java 17+: kiểm CouponService với ID và random kiểm soát được

Bài toán: service phát coupon cho một user hợp lệ. Mỗi coupon phải mang ID do `IdGenerator` cung cấp; một lần rút số `nextInt(100)` quyết định mức giảm: giá trị 0–9 được **25%**, giá trị 10–99 được **5%**. User rỗng bị từ chối trước khi dùng các dependency.

Ta sẽ kiểm **code nghiệp vụ thật** với:

- `Mockito.mock(RandomGenerator.class)` để stub đúng các ranh giới 0, 9, 10, 99.
- `IdGenerator` mock khi cần một ID duy nhất cố định.
- `SequenceIds` là fake phát hai ID theo thứ tự; test không cần source ngẫu nhiên thật.
- `Random(42L)` minh họa tính tái hiện của một dãy.
- `UUID.fromString(...)` làm fixture test, và một test riêng kiểm tính chất của UUID generator từ JDK.

Đặt toàn bộ nội dung dưới đây trong một file `src/test/java/example/CouponServiceTest.java`. File là **ví dụ tự chứa**, yêu cầu Java 17+, JUnit Jupiter và Mockito. Nó không cần Spring ApplicationContext, database, Docker hay network.

~~~java
package example;

import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.Objects;
import java.util.Random;
import java.util.UUID;
import java.util.random.RandomGenerator;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@DisplayName("CouponService: ngẫu nhiên và định danh xác định")
class CouponServiceTest {

    private static final UUID ID_A = UUID.fromString(
            "00000000-0000-4000-8000-000000000001");
    private static final UUID ID_B = UUID.fromString(
            "00000000-0000-4000-8000-000000000002");

    interface IdGenerator {
        UUID nextId();
    }

    record Coupon(UUID id, String userId, int discountPercent) {
    }

    static final class CouponService {
        private final IdGenerator ids;
        private final RandomGenerator random;

        CouponService(IdGenerator ids, RandomGenerator random) {
            this.ids = Objects.requireNonNull(ids);
            this.random = Objects.requireNonNull(random);
        }

        Coupon issue(String userId) {
            if (userId == null || userId.isBlank()) {
                throw new IllegalArgumentException("userId is required");
            }

            UUID id = Objects.requireNonNull(
                    ids.nextId(), "generated ID");

            // nextInt(100) nhận các giá trị 0..99.
            int draw = random.nextInt(100);
            int discount = draw < 10 ? 25 : 5;

            return new Coupon(id, userId, discount);
        }
    }

    // Fake chỉ cấp đúng các ID test đã chuẩn bị theo thứ tự.
    static final class SequenceIds implements IdGenerator {
        private final Deque<UUID> remaining;

        SequenceIds(UUID... values) {
            remaining = new ArrayDeque<>(Arrays.asList(values));
        }

        @Override
        public UUID nextId() {
            if (remaining.isEmpty()) {
                throw new IllegalStateException("No IDs remaining");
            }
            return remaining.removeFirst();
        }
    }

    @Test
    @DisplayName("Số rút 0 nhận 25% và ID cố định được giữ nguyên")
    void zeroDrawGetsBonusAndFixedId() {
        IdGenerator ids = mock(IdGenerator.class);
        RandomGenerator random = mock(RandomGenerator.class);
        when(ids.nextId()).thenReturn(ID_A);
        when(random.nextInt(100)).thenReturn(0);

        Coupon actual = new CouponService(ids, random).issue("user-1");

        assertAll(
                () -> assertEquals(ID_A, actual.id()),
                () -> assertEquals("user-1", actual.userId()),
                () -> assertEquals(25, actual.discountPercent()));

        verify(ids).nextId();
        verify(random).nextInt(100);
    }

    @Test
    @DisplayName("Số rút 9 vẫn thuộc nhóm 25%")
    void nineIsLastBonusValue() {
        RandomGenerator random = mock(RandomGenerator.class);
        when(random.nextInt(100)).thenReturn(9);

        Coupon coupon = new CouponService(
                new SequenceIds(ID_A), random).issue("user-2");

        assertEquals(25, coupon.discountPercent());
    }

    @Test
    @DisplayName("Số rút 10 chuyển sang nhóm 5%")
    void tenIsFirstBaseValue() {
        RandomGenerator random = mock(RandomGenerator.class);
        when(random.nextInt(100)).thenReturn(10);

        Coupon coupon = new CouponService(
                new SequenceIds(ID_A), random).issue("user-3");

        assertEquals(5, coupon.discountPercent());
    }

    @Test
    @DisplayName("Số rút 99 vẫn thuộc nhóm 5%")
    void ninetyNineIsValidUpperValue() {
        RandomGenerator random = mock(RandomGenerator.class);
        when(random.nextInt(100)).thenReturn(99);

        Coupon coupon = new CouponService(
                new SequenceIds(ID_A), random).issue("user-4");

        assertEquals(5, coupon.discountPercent());
    }

    @Test
    @DisplayName("User trống bị từ chối trước khi sinh ID hoặc rút số")
    void invalidUserConsumesNoRandomnessOrId() {
        IdGenerator ids = mock(IdGenerator.class);
        RandomGenerator random = mock(RandomGenerator.class);

        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> new CouponService(ids, random).issue("  "));

        assertEquals("userId is required", error.getMessage());
        verifyNoInteractions(ids, random);
    }

    @Test
    @DisplayName("Hai lần gọi dùng đúng chuỗi ID và số rút")
    void sequenceMakesMultipleIssuesPredictable() {
        RandomGenerator random = mock(RandomGenerator.class);
        when(random.nextInt(100)).thenReturn(9, 10);
        CouponService service = new CouponService(
                new SequenceIds(ID_A, ID_B), random);

        Coupon first = service.issue("user-1");
        Coupon second = service.issue("user-2");

        assertAll(
                () -> assertEquals(ID_A, first.id()),
                () -> assertEquals(25, first.discountPercent()),
                () -> assertEquals(ID_B, second.id()),
                () -> assertEquals(5, second.discountPercent()));
        verify(random, times(2)).nextInt(100);
    }

    @Test
    @DisplayName("Bộ sinh ID trả null bị từ chối trước khi rút số")
    void nullGeneratedIdDoesNotConsumeRandomness() {
        IdGenerator ids = mock(IdGenerator.class);
        RandomGenerator random = mock(RandomGenerator.class);
        when(ids.nextId()).thenReturn(null);

        NullPointerException error = assertThrows(
                NullPointerException.class,
                () -> new CouponService(ids, random).issue("user-1"));

        assertEquals("generated ID", error.getMessage());
        verifyNoInteractions(random);
    }

    @Test
    @DisplayName("Cùng seed và cùng trình tự gọi sinh cùng dãy")
    void sameSeedReplaysSequence() {
        Random first = new Random(42L);
        Random second = new Random(42L);

        for (int i = 0; i < 8; i++) {
            assertEquals(first.nextInt(100), second.nextInt(100));
        }
    }

    @Test
    @DisplayName("Name-based UUID lặp lại được từ cùng bytes")
    void nameBasedUuidIsDeterministic() {
        byte[] key = "coupon:user-1".getBytes(StandardCharsets.UTF_8);
        UUID first = UUID.nameUUIDFromBytes(key);
        UUID second = UUID.nameUUIDFromBytes(key);

        assertEquals(first, second);
        assertEquals(3, first.version());
    }

    @Test
    @DisplayName("UUID.randomUUID tạo UUID v4, variant RFC")
    void randomUuidHasExpectedFormatVersion() {
        UUID id = UUID.randomUUID();

        assertEquals(4, id.version());
        assertEquals(2, id.variant());
    }
}
~~~

### Giải thích điều test thật sự chứng minh

- **`CouponService` là SUT thật.** Nếu ngưỡng đổi từ `draw < 10` thành `draw <= 10`, test cho `10` sẽ FAIL. Nếu bỏ validation user, test user rỗng sẽ FAIL. Các thay đổi nghiệp vụ bị bắt đúng chỗ.
- **`RandomGenerator` mock đang đóng vai trò stub dữ liệu.** `when(random.nextInt(100)).thenReturn(9)` không “kiểm random có thật sự phân phối đều”; nó tạo một giá trị ranh giới để kiểm quy tắc. `verify(random).nextInt(100)` có thêm giá trị khi hợp đồng yêu cầu rút đúng một số trong miền 100.
- **`SequenceIds` là fake có trạng thái.** Lần gọi đầu trả `ID_A`, lần sau trả `ID_B`; khi hết giá trị, fake ném lỗi rõ ràng. Test được một chuỗi thao tác mà không phải phụ thuộc UUID mới của hệ điều hành.
- **`UUID.randomUUID()` chỉ có mặt ở bài test đặc tính adapter/JDK.** Test kiểm version/variant, không so UUID tạo mới với chuỗi cố định và không khẳng định hai UUID bất kỳ chắc chắn khác nhau.
- **`Random(42L)` kiểm replay của cùng thuật toán.** Test không hardcode dãy số cụ thể của thuật toán; nó chỉ so hai generator có cùng seed và cùng thứ tự gọi.
- **`nullGeneratedIdDoesNotConsumeRandomness()`** thể hiện cả hợp đồng lỗi và việc không tiêu thụ random sau một ID lỗi. Thứ tự gọi trong SUT là một phần thiết kế có chủ đích của ví dụ.
- **Không có test nào cần đợi `Thread.sleep`**, cố thử hàng nghìn lần để đủ xác suất hay gọi mạng. Chúng kiểm nhánh bằng giá trị do test chủ động cấp.

Kết quả mong đợi khi JUnit Platform chạy file này là **10 phương thức kiểm thử PASS**. Test không in stdout; tên hiển thị và thứ tự trong IDE/Gradle có thể khác, nhưng tổng số test do file khai báo là 10.

**Giới hạn của ví dụ tự chứa:** `CouponService` và các domain type nằm trong file test để ai cũng đọc được hợp đồng đầy đủ. Trong dự án thực tế, **implementation nghiệp vụ phải ở `src/main/java`** và test import chính lớp đó; không viết lại một bản sao “production service” trong `src/test/java` rồi tưởng đã kiểm production code.

## 7. Chạy ví dụ bằng Gradle trong dự án Spring Boot

Trong một module Spring Boot có plugin và dependency management phù hợp, `build.gradle` thường có cấu hình sau (đây là **đoạn cấu hình trong project đang tồn tại**, không phải build file độc lập):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` thường bao gồm JUnit Jupiter và Mockito. Ví dụ dùng phương thức `mock(...)` trực tiếp, vì vậy **không cần `MockitoExtension`** để cấp fields `@Mock`. Nếu chuyển sang `@Mock`, dùng `@ExtendWith(MockitoExtension.class)` hoặc cơ chế khởi tạo phù hợp.

Từ thư mục root Gradle thích hợp của module:

~~~bash
./gradlew test --tests example.CouponServiceTest
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.CouponServiceTest
~~~

**Kết quả dự kiến:** cả 10 test PASS và tác vụ Gradle kết thúc thành công nếu môi trường/build hợp lệ. Không đưa ra stdout cụ thể cho test vì các assertion không in gì và định dạng thông báo của Gradle có thể thay đổi theo phiên bản/cấu hình.

**Nếu test không được phát hiện**, kiểm `org.junit.jupiter.api.Test`, `useJUnitPlatform()`, vị trí `src/test/java/example/CouponServiceTest.java`, đúng package `example` và dependency JUnit Jupiter. Không cần thêm `@SpringBootTest` chỉ để chạy test Java thuần.

### Chuyển ví dụ sang code production

Trong production có thể tạo một implementation của `IdGenerator`:

~~~java
// Bên trong production code, sau khi đã khai báo interface IdGenerator:
final class UuidV4Ids implements IdGenerator {
    @Override
    public UUID nextId() {
        return UUID.randomUUID();
    }
}
~~~

Đoạn trên **chỉ minh họa implementation**, cần import `UUID` và sử dụng interface `IdGenerator` của ứng dụng; không phải file độc lập. Với Spring Boot, có thể đăng ký nó như bean rồi constructor-inject vào service. Trên unit test, thay bằng `SequenceIds` hoặc mock. Mục tiêu là code nghiệp vụ dùng một hợp đồng duy nhất, còn cách cấp ID quyết định ở tầng cấu hình.

## 8. ID dạng số, sequence và concurrency: không nhầm giữa fake với production

Có những bài toán không muốn dùng UUID: ID là số tăng dần, dễ đọc hoặc do database tự sinh. Một fake có thể phát ID theo thứ tự trong unit test:

~~~java
import java.util.concurrent.atomic.AtomicLong;

final class InMemoryIds {
    private final AtomicLong next = new AtomicLong(1000);

    long nextId() {
        return next.getAndIncrement();
    }
}
~~~

Đây là **đoạn class minh họa**, không có `main`. Nó làm test có ID 1000, 1001, 1002… nếu dùng riêng một instance và gọi theo thứ tự. `AtomicLong` giúp tăng số an toàn giữa các thread của **cùng tiến trình**, nhưng **không** biến nó thành bộ sinh ID phân tán:

- Hai JVM có cùng giá trị khởi đầu có thể phát cùng ID.
- Sau restart, counter trong RAM không tự khôi phục vị trí.
- Nếu nhiều instance chia sẻ database, phải có phương thức phối hợp (sequence do DB cấp, service cấp ID, thuật toán theo node/time có đảm bảo cụ thể).
- Nếu dùng DB `GENERATED IDENTITY`, việc cấp ID là hành vi của database; unit test nên giả lập giá trị trả về từ repository, còn integration test xác minh generator thực của DB.

**Không kiểm tính duy nhất dưới cạnh tranh bằng việc gọi fake tuần tự hai lần.** Unit test tuần tự chỉ chứng minh logic dùng nguồn ID theo hợp đồng. Kiểm concurrency phải diễn ra ở mức có nhiều luồng/transaction và hệ lưu trữ thật khi business invariant phụ thuộc chúng.

### Xử lý trùng ID đúng chỗ

Nếu ứng dụng tự cấp UUID và lưu vào database, hãy có **unique constraint** ở khóa tương ứng. Chỉ kiểm `repository.existsById(id)` rồi `save(...)` là chưa đủ vì hai request cạnh tranh có thể cùng thấy “chưa có” rồi ghi. Ràng buộc database phải là điểm phân xử cuối; nếu hợp đồng cho phép retry, chỉ retry lỗi trùng khóa xác định với số lần giới hạn và đảm bảo thao tác trước đó chưa gây side effect không thể lặp lại.

Unit test có thể dùng fake generator cấp theo chuỗi “ID đã tồn tại → ID mới” và fake persistence ném lỗi trùng đã mô hình hóa để kiểm logic retry. Tuy nhiên **không coi test đó là bằng chứng transaction/concurrency DB đã đúng**. Cần integration test với database cùng loại production để xác minh constraint và hành vi transaction thực.

## 9. Ngẫu nhiên trong bảo mật: SecureRandom và token

Ngẫu nhiên cho bốc thăm trong trò chơi và ngẫu nhiên cho **bí mật xác thực** có yêu cầu khác nhau.

- `Random` và nhiều PRNG thông thường có thể dự đoán hoặc phục hồi dãy từ state; không phù hợp làm nguồn tạo session secret, reset token, OTP production hay API key.
- `SecureRandom` là API JDK dùng nguồn pseudo-random phù hợp mục đích mật mã. Java `UUID.randomUUID()` tạo UUID v4 bằng nguồn có độ mạnh mật mã theo tài liệu JDK, nhưng **UUID không tự trở thành session token an toàn chỉ vì khó đoán**. Mô hình token cần entropy, TTL, chính sách lưu trữ, rotation và quyền hạn.
- **Không cố định seed của `SecureRandom` trong production hoặc test để “đoán” kết quả byte chính xác.** `SecureRandom.setSeed(...)` có thể bổ sung vào entropy pool và thuật toán/provider có khác biệt; cùng seed không là hợp đồng sẽ sinh cùng byte trên mọi máy.
- Muốn unit test nghiệp vụ phát token thành một giá trị xác định, **tiêm `TokenGenerator`/`Supplier<String>` vào service** rồi stub giá trị token. Đặt kiểm thử format/token entropy ở test riêng cho generator thật.

Ví dụ class production độc lập cho token URL-safe:

File `src/main/java/example/ResetTokenGenerator.java`:

~~~java
package example;

import java.security.SecureRandom;
import java.util.Base64;
import java.util.Objects;

public final class ResetTokenGenerator {
    private final SecureRandom random;

    public ResetTokenGenerator(SecureRandom random) {
        this.random = Objects.requireNonNull(random);
    }

    public String nextToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(bytes);
    }
}
~~~

Đây là **class production biên dịch độc lập trên Java 17+** với JDK, nhưng không có `main` nên không tự in stdout. 32 byte ngẫu nhiên tạo 256 bit đầu vào; Base64 URL-safe không padding có độ dài **43 ký tự** cho 32 byte.

Một test adapter kiểm **bất biến về format**, thay vì đoán chính xác token:

File `src/test/java/example/ResetTokenGeneratorTest.java`:

~~~java
package example;

import java.security.SecureRandom;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ResetTokenGeneratorTest {
    @Test
    void generatesUrlSafeTokenOfExpectedLength() {
        String token = new ResetTokenGenerator(
                new SecureRandom()).nextToken();

        assertEquals(43, token.length());
        assertTrue(token.matches("[A-Za-z0-9_-]{43}"));
    }
}
~~~

Test này chỉ kiểm độ dài và bảng ký tự, **không chứng minh định lượng entropy**. Để đánh giá bảo mật cần xem xét thuật toán, key management, lưu hash token, TTL, rate limit, khả năng revoke và luồng xác thực thực. Không ghi secret vào log hoặc dùng UUID như bằng chứng authorization.

Trong unit test của use case sử dụng token, ưu tiên:

~~~java
// Chỉ là ví dụ tiêm port tại test của service, không phải file độc lập:
Supplier<String> fakeTokenSource = () -> "fixed-token-for-test";
~~~

Muốn dùng trong code thật cần import `java.util.function.Supplier` và tạo interface/constructor phù hợp. Giá trị cố định chỉ dùng trong kiểm thử để assert email gửi đi, hash được lưu hoặc thời hạn gắn đúng token; production phải dùng generator an toàn.

## 10. Những chiến lược kiểm thử randomness có giá trị khác nhau

| Mục tiêu | Chiến lược | Assertion nên dùng |
| --- | --- | --- |
| Kiểm nhánh xác suất: 0–9 khác 10–99 | Mock/stub giá trị `nextInt(100)` | 0 và 9 → 25%; 10 và 99 → 5% |
| Kiểm nhiều bước theo chuỗi rõ ràng | Fake sequence cho random và ID | Các output ứng với từng lần cấp |
| Tái hiện một lỗi mô phỏng | PRNG có seed và thuật toán cố định | Kết quả replay của cùng input/chuỗi lời gọi |
| Kiểm business service dùng UUID được cấp | Stub `IdGenerator` trả UUID cố định | ID kết quả đúng bằng ID được tiêm |
| Kiểm adapter UUID v4 | Dùng generator thật | `version() == 4` và `variant() == 2` |
| Kiểm name-based ID | Input bytes được canonical hóa | Cùng input cho cùng UUID |
| Kiểm database có unique constraint | DB thật trong integration test | Ghi trùng bị từ chối ở tầng persistence |
| Kiểm token format | `SecureRandom` thật, assert format | Độ dài, tập ký tự, parse hợp lệ |
| Kiểm service gửi token | Stub `TokenGenerator` ở ranh giới | Thông điệp/trạng thái chứa đúng token đã cấp |
| Kiểm phân phối thống kê | Thử nghiệm thống kê thiết kế riêng nếu thật sự cần | Tiêu chí/tolerance được xác định, tránh phụ thuộc nhỏ mẫu |

**Tránh các assertion ngẫu nhiên không có cơ sở:**

~~~java
// KHÔNG nên:
// assertNotEquals(UUID.randomUUID(), UUID.randomUUID());
// assertEquals(25, service.discountPercent()); // nếu không kiểm soát nguồn
// assertEquals(100, uniqueIds.size());         // dựa vào xác suất 100 lần không trùng
~~~

Các đoạn trên chỉ minh họa **anti-pattern**. Xác suất hai UUID v4 trùng rất nhỏ, nhưng một xác nhận “100 lượt phải khác nhau” không chứng minh chống trùng tuyệt đối và tạo một điều kiện fail không giải thích được nếu nguồn có sự cố. Test quy tắc cấp ID, hợp đồng retry và constraint database mới đem lại bằng chứng rõ ràng.

### Có nên kiểm đúng 10% kết quả?

Nếu luật là “giá trị nhỏ hơn 10 được 25%”, unit test nên kiểm **ngưỡng** bằng input cố định. Việc một PRNG có phân phối gần đều là mối quan tâm khác. Một test lấy 10 hoặc 100 mẫu rồi assert chính xác 10% có xác suất fail rất lớn dù random đúng; một phép kiểm thống kê nghiêm túc cần giả thuyết, cỡ mẫu, sai số và chính sách false positive phù hợp. Thông thường không đưa test thống kê khó ổn định vào mỗi lần CI chạy.

## 11. Kiểm soát trạng thái dùng chung, async và seed trong CI

Ngay cả khi có seed, một bài test vẫn có thể không quyết định được nếu nhiều luồng cùng dùng generator hoặc cùng ghi một storage:

- Nếu hai thread gọi cùng PRNG stateful, thứ tự lấy số có thể thay đổi, làm kết quả gán cho mỗi request khác nhau.
- Nếu dùng static mutable `Random` trong test, các method có thể ảnh hưởng nhau theo thứ tự chạy.
- Nếu service lấy ID một lần nhưng refactor thêm lời gọi trước đó, kết quả seed được cấp về sau sẽ đổi.
- Nếu test tự tạo `UUID.randomUUID()` rồi dùng ID đó trong nhiều assertion nhưng không lưu giá trị, rất dễ so sánh hai ID khác nhau.
- Nếu fake generator có số lượng phần tử hạn chế, phải khởi tạo lại theo từng test; không chia sẻ một fake giữa những bài test độc lập.

Cách làm:

1. Tạo generator/fake mới **cho từng test** hoặc inject state riêng. Trong JUnit Jupiter, `@BeforeEach` phù hợp để khởi tạo fixture.
2. Đặt seed trong **Arrange**, ghi lại seed khi một bài mô phỏng dùng dữ liệu phức tạp thất bại; không thay seed tùy ý khi debug.
3. Cố định cả thuật toán, tham số và số lần gọi nếu cần replay; không chỉ ghi “seed = 42” rồi đổi generator giữa các phiên bản.
4. Với async/concurrency, cấp nguồn ngẫu nhiên theo request/thread/worker hoặc thiết kế thứ tự kết quả không phụ thuộc thứ tự truy cập; kiểm concurrency bằng test riêng có phối hợp.
5. Khi cần định danh của workflow, cấp ID ở một ranh giới rõ ràng rồi **truyền cùng giá trị** qua service/repository/event; tránh mỗi tầng tự gọi `UUID.randomUUID()` một lần.
6. Dùng `Clock` hoặc thời gian ảo cho phần logic liên quan thời gian; **seed của Random không kiểm soát được `Instant.now()`**. Khi định danh phụ thuộc thời gian, tiêm cả nguồn thời gian.
7. Với Spring singleton bean, xét thread-safety và state lifecycle của generator; không giả định mọi `RandomGenerator` implementation có cùng bảo đảm concurrency.

**Một nguyên tắc thực tế:** test thường ổn định hơn khi assert **hợp đồng đầu ra** (ID được cấp, ngưỡng giảm giá, số lần yêu cầu cấp ID) thay vì assert chính xác toàn bộ dãy random của một thuật toán không liên quan trực tiếp đến nghiệp vụ.

## 12. Tích hợp vào Spring Boot mà không làm unit test nặng

Trong production, có thể khai báo `IdGenerator` thành bean và inject vào service bằng constructor. Với random dùng cho lựa chọn nghiệp vụ không bảo mật, tạo một `RandomGenerator` implementation phù hợp yêu cầu concurrency. Ví dụ minh họa cấu hình (cần định nghĩa interface `IdGenerator` và `CouponService` trong code ứng dụng):

~~~java
@Configuration
class GeneratorConfig {

    @Bean
    IdGenerator idGenerator() {
        return UUID::randomUUID;
    }

    @Bean
    RandomGenerator drawRandomGenerator() {
        return new Random();
    }
}
~~~

Đoạn này là **mã cấu hình minh họa**, không phải file độc lập. Cần import `Configuration`/`Bean` từ Spring, `UUID`, `Random` và `RandomGenerator`. Một instance `Random` dùng chung là thread-safe theo đặc tính JDK, nhưng có thể gặp contention ở tải cao; có thể chọn thiết kế khác dựa trên yêu cầu throughput và concurrency. Đừng sử dụng bean PRNG nghiệp vụ này cho token bảo mật.

**Unit test** khởi tạo `new CouponService(fakeIds, mockRandom)` như mục 6; không cần container hay context. **Spring integration test** dùng ApplicationContext khi muốn xác minh bean wiring, configuration profile hoặc transaction. Một unit test với mock `IdGenerator` không tự chứng minh `@Bean` production có được nạp đúng hay không.

Cũng không nên cấu hình seed cố định cho PRNG production chỉ để unit test dễ viết. Seed là một đầu vào dành cho bài thử có chủ đích hoặc mô phỏng tái hiện; khả năng kiểm soát nên đến từ **dependency boundary**.

## 13. Mười lỗi thường gặp và cách sửa

**1. Gọi `UUID.randomUUID()` ngay trong logic rồi so với một UUID khác trong test.** Hai lần tạo UUID không có quan hệ bằng nhau. Tiêm `IdGenerator` và stub trả ID cố định; assert SUT dùng ID đó.

**2. Dùng `Math.random()` để điều khiển nhánh nghiệp vụ trong test.** Không thể ép nó trả đúng 0 hoặc 0,1 theo ý muốn. Tách `RandomGenerator`, stub giá trị 0, 9, 10, 99 tùy ngưỡng.

**3. Đặt seed và tin mọi thay đổi code vẫn cho cùng kết quả.** Nếu thay thuật toán hoặc thứ tự gọi, dãy đổi. Dùng seed khi cần replay, dùng stub giá trị khi cần kiểm nhánh nghiệp vụ.

**4. Dùng `Random(42)` hoặc `Math.random()` để sinh reset token.** Dữ liệu có thể đoán. Production cần `SecureRandom` và luồng quản lý token đúng; test use case nên stub một token port.

**5. Cho rằng UUID không bao giờ trùng.** Xác suất trùng thấp không phải ràng buộc tuyệt đối. Dùng unique constraint ở storage và xử lý conflict có giới hạn.

**6. Coi name-based UUID là ID mới mỗi lượt.** `UUID.nameUUIDFromBytes(...)` cùng bytes sẽ cho cùng ID; hợp lý cho cùng khóa logic nhưng sai khi nghiệp vụ cần tạo ID mới cho từng lần phát hành.

**7. Viết test kiểm “100 lần không trùng” rồi kết luận generator đủ an toàn.** Một mẫu nhỏ không chứng minh unique trong hệ phân tán hay entropy bảo mật. Cần kiểm thuật toán, constraint và hành vi lỗi đúng lớp.

**8. Dùng fake `AtomicLong` để chứng minh ID production duy nhất qua nhiều instance.** AtomicLong chỉ bảo đảm trong phạm vi state và tiến trình đang chạy. Dùng integration test cho DB sequence hoặc cơ chế cấp ID phân tán.

**9. Chia sẻ RNG state trong parallel tests.** Kết quả phụ thuộc thứ tự. Mỗi test cần fixture riêng; tránh static mutable state và kiểm rõ cách generator được dùng trong concurrency.

**10. Mock quá mức và bỏ quên nghiệp vụ.** Mock chính service rồi stub coupon mong muốn chỉ kiểm Mockito, không kiểm luật ngưỡng hoặc validation. Giữ SUT thật, chỉ thay nguồn biến thiên.

**11. Dùng UUID như cơ chế phân quyền.** Một UUID trong URL không thay cho kiểm owner/tenant/role; vẫn phải kiểm quyền ở mỗi request.

**12. Ngầm bỏ qua lỗi trả null hoặc trùng ID từ generator.** Tùy hợp đồng, fail sớm, retry có giới hạn hoặc chuyển lỗi có ngữ cảnh; unit test các nhánh này và kiểm storage thật tại nơi thực thi constraint.

## 14. Quy trình áp dụng cho một tính năng mới

Giả sử cần bổ sung “phát coupon cho 10% lượt yêu cầu”:

1. **Viết hợp đồng:** người dùng hợp lệ nhận một coupon có ID và mức giảm 25% khi rút 0–9, 5% khi rút 10–99.
2. **Đặt biến thiên ngoài service:** constructor nhận `IdGenerator` và `RandomGenerator`.
3. **Xác định hành vi lỗi:** input rỗng không tiêu thụ ID/random; ID null bị từ chối; storage conflict cần chính sách rõ.
4. **Lập bảng ranh giới:** rút 0, 9, 10 và 99; không cần test hàng nghìn lượt.
5. **Test chuỗi cấp ID:** fake sequence `ID_A` rồi `ID_B` để bảo đảm output gắn đúng ID.
6. **Test adapter riêng:** UUID v4 version/variant, generator name-based nếu nghiệp vụ thật sự cần.
7. **Test tích hợp đúng chỗ:** repository với unique constraint và transaction thật; bean configuration khi mục tiêu là Spring wiring.
8. **Phân loại an toàn:** random bốc thăm có thể dùng PRNG thông thường; token bảo mật dùng `SecureRandom` và chính sách an toàn.
9. **Kiểm CI:** test không dựa vào thời gian, thread scheduling, xác suất cụ thể hoặc nguồn random dùng chung.
10. **Review sau refactor:** assertion vẫn thể hiện hành vi nghiệp vụ dù số lần gọi nội bộ hoặc tổ chức class thay đổi.

### Checklist nhanh trước khi hoàn tất

- [ ] SUT chạy logic production thật; randomness và ID được tiêm thành dependency rõ ràng.
- [ ] Dùng stub/mock để chọn giá trị tại các **ranh giới**; không kiểm ngẫu nhiên bằng may rủi.
- [ ] Fake sequence có state riêng mỗi test và lỗi rõ nếu dùng hết phần tử.
- [ ] Seed chỉ dùng khi thực sự cần replay; không phụ thuộc cùng dãy giữa các thuật toán khác nhau.
- [ ] Test UUID tập trung vào ID được truyền đúng; version/variant kiểm ở adapter khi có giá trị.
- [ ] Database có unique constraint cho định danh cần duy nhất; xử lý collision và concurrency ở tầng phù hợp.
- [ ] Không dùng UUID/ID như token authorization; secrets được tạo bằng nguồn mật mã an toàn.
- [ ] Cấu hình Spring Boot bean, thread-safety và lifecycle của generator được xét ở integration level.
- [ ] Test độc lập, không dựa vào static RNG dùng chung, clock thật hoặc tần suất mẫu nhỏ.
- [ ] Ví dụ Java được chạy qua JUnit Platform; các assertions mô tả đúng hợp đồng nghiệp vụ.

**Điểm cần nhớ:** điều quan trọng nhất không phải “làm cho số ngẫu nhiên giống nhau mọi lần chạy”, mà là **thiết kế nguồn biến thiên như một dependency để unit test chọn được đúng input cần kiểm**. Khi đó nghiệp vụ vẫn chạy thật, test ổn định và những đặc tính riêng của UUID, database sequence hoặc SecureRandom có nơi kiểm chứng riêng.

### Tài liệu tham khảo

- [Java 17 API — RandomGenerator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/random/RandomGenerator.html): các phương thức sinh số và giới hạn của `nextInt(bound)`.
- [Java 17 API — Random](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Random.html): seed và quy tắc về dãy pseudo-random.
- [Java 17 API — UUID](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/UUID.html): UUID v4, `randomUUID`, `nameUUIDFromBytes`, version và variant.
- [Java 17 API — SecureRandom](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/SecureRandom.html): nguồn pseudo-random dành cho mật mã.
- [RFC 9562 — Universally Unique IDentifiers](https://www.rfc-editor.org/rfc/rfc9562): định dạng, phiên bản UUID bao gồm UUID v7.
- [Mockito Documentation](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/org/mockito/Mockito.html): stub giá trị và xác minh tương tác.
- [JUnit Jupiter User Guide](https://docs.junit.org/5.11.4/user-guide/): tổ chức unit test và assertions.
