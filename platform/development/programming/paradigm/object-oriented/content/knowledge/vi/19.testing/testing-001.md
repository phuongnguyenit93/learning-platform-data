# Kiểm thử hành vi công khai và hợp đồng đối tượng trong Java OOP

> **Chủ đề:** OOP → Kiểm thử → Kiểm thử hành vi công khai và hợp đồng đối tượng.  
> **Mục tiêu:** Viết kiểm thử theo những gì client thực sự nhìn thấy và được phép yêu cầu, thay vì bám vào field/private method; mô tả hợp đồng bằng tiền điều kiện, hậu điều kiện, bất biến và cách xử lý lỗi; dùng cùng một bộ test để kiểm tra nhiều implementation của một interface; phát hiện lỗi khi thay implementation mà vẫn biên dịch được.

## 1. Kiểm thử đối tượng là kiểm thử điều gì?

Một đối tượng không đơn thuần là tập hợp field. Nó đưa ra một **giao diện hành vi** cho bên ngoài: những thao tác có thể gọi, dữ liệu trả về, tác dụng phụ, trạng thái sau mỗi thao tác và trường hợp bị từ chối.

Giả sử một kho vé còn 10 chỗ. Client yêu cầu:

~~~text
Kho vé sức chứa 10
    ├─ tryReserve(4)  → true   → đã đặt 4, còn 6
    ├─ tryReserve(7)  → false  → vẫn đã đặt 4, còn 6
    └─ cancel(2)      → thành công → đã đặt 2, còn 8
~~~

Đây là **hành vi quan sát được**. Một bài test tốt không cần biết kho vé dùng `int reserved`, `AtomicInteger`, `HashMap` hay database; test cần xác nhận **kết quả và các quy tắc mà API đã cam kết**.

**Hợp đồng đối tượng (object contract)** mô tả nghĩa của API chứ không chỉ chữ ký Java. Ví dụ chữ ký `boolean tryReserve(int count)` chưa đủ để biết:

- `count = 0` có hợp lệ không?
- Không đủ chỗ thì trả `false` hay ném exception?
- Thất bại có làm thay đổi state không?
- Khi thành công, số vé đã đặt tăng chính xác bao nhiêu?
- Có cho phép nhiều thread đặt đồng thời không?
- Nếu một implementation mới thay cho implementation cũ, điều gì phải giữ nguyên?

Kiểm thử hợp đồng biến những cam kết này thành **các ví dụ có thể thực thi** và giúp phát hiện thay đổi phá vỡ tính thay thế (*substitutability*).

## 2. Public behavior khác implementation detail

| Nên kiểm thử qua hành vi công khai | Không nên phụ thuộc nếu không có lý do đặc biệt |
|---|---|
| `tryReserve(4)` trả `true` và snapshot phản ánh đúng 4 vé | Tên field nội bộ là `reserved` hay `taken` |
| `tryReserve(7)` trả `false` và không đổi trạng thái | Có gọi private method `hasEnoughSeats()` không |
| `cancel(2)` giảm số vé đã đặt từ 4 còn 2 | Cấu trúc source dùng một hay hai private helpers |
| Input không hợp lệ bị từ chối theo exception đã hứa | Dòng source nào ném exception |
| Hai implementation cùng thoả một bộ contract | Có dùng `synchronized`, CAS hay lock cụ thể trong nội bộ |
| Event/cộng tác viên bên ngoài được gọi theo hợp đồng, nếu đó là observable effect | Số lần một private helper bị gọi khi không ảnh hưởng kết quả |

Một phép refactor chỉ đổi `int reserved` thành `AtomicInteger reserved` mà **không đổi hành vi** đáng lẽ không làm phần lớn unit test thất bại. Nếu test luôn thất bại mỗi khi đổi cấu trúc nội bộ, chúng đang **couple với implementation** quá chặt.

**Không có nghĩa mọi test đều phải black-box tuyệt đối.** Unit test cho một thuật toán thuần hoặc adapter nội bộ vẫn hợp lý; integration test có thể xác nhận tương tác DB/HTTP. Nhưng test cho **hợp đồng đối tượng** nên dùng API mà client thật dùng và chỉ xác nhận những cam kết cần giữ ổn định.

## 3. Bốn phần của một hợp đồng có thể kiểm thử

Một hợp đồng thường được mô tả qua:

| Phần | Câu hỏi | Kho vé |
|---|---|---|
| **Precondition** | Người gọi cần đáp ứng điều gì? | Số lượng đặt/hủy phải dương |
| **Postcondition thành công** | Sau lời gọi thành công, điều gì đúng? | Đặt 3 vé thì số đã đặt tăng đúng 3 |
| **Postcondition thất bại** | Khi bị từ chối/lỗi, đối tượng còn hợp lệ thế nào? | Thiếu chỗ trả `false`, state không đổi |
| **Invariant** | Điều kiện nào phải luôn đúng ở ranh giới quan sát? | `0 ≤ reserved ≤ capacity` |

Trong chương trình thực tế còn có những **bảo đảm phi chức năng** cần chỉ rõ theo nhu cầu: thread safety, độ trễ, tính nhất quán khi ghi dữ liệu, idempotency, thứ tự callback hoặc ràng buộc quyền truy cập. Không phải mọi interface tự động cam kết mọi tính chất đó.

### Ví dụ đặc tả hợp đồng

Định nghĩa một interface quản lý số vé, với quy tắc như sau:

- Constructor của implementation yêu cầu `capacity > 0`.
- Ban đầu số vé đã đặt bằng `0`.
- `tryReserve(n)`: nếu `n <= 0`, ném `IllegalArgumentException`; nếu đủ chỗ, tăng số đã đặt lên `n` và trả `true`; nếu không đủ, trả `false` và giữ nguyên state.
- `cancel(n)`: yêu cầu `n > 0` và `n <= reserved`; nếu không đúng, ném `IllegalArgumentException` **không sửa state**; nếu đúng, trừ `n`.
- `snapshot()` trả ảnh chụp bất biến, nhất quán của `capacity` và `reserved` tại thời điểm method thực hiện.
- Mọi implementation có thể được gọi từ nhiều thread trong cùng JVM; mỗi lời gọi đặt/hủy phải hoạt động như một thay đổi nguyên tử trên **một instance**.

**Lưu ý:** Đây là hợp đồng được lựa chọn cho ví dụ, không phải luật bắt buộc của mọi hệ thống đặt vé. Có hệ thống chọn trả đối tượng `Result` thay vì boolean, hoặc xử lý hủy vượt số lượng như lỗi domain khác. Test phải theo hợp đồng thật, không theo sở thích tùy tiện của người viết test.

## 4. Java 17 hoàn chỉnh: một interface, hai implementation

Để thấy giá trị của contract test, ta xây dựng hai implementation có **cơ chế lưu state khác nhau**, nhưng dùng **cùng API công khai**:

- `MonitorSeatInventory` sử dụng `synchronized`.
- `AtomicSeatInventory` sử dụng `AtomicInteger` và vòng lặp compare-and-set (CAS).

Cả hai phải giữ được cùng quy tắc nghiệp vụ, bất kể cách đồng bộ.

Tạo tệp **`SeatInventoryDemo.java`**, chỉ dùng JDK 17+:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

// Dữ liệu quan sát được, immutable nhờ record với thành phần primitive.
record SeatSnapshot(int capacity, int reserved) {
    SeatSnapshot {
        if (capacity <= 0 || reserved < 0 || reserved > capacity) {
            throw new IllegalArgumentException("Invalid seat snapshot");
        }
    }

    int available() {
        return capacity - reserved;
    }
}

// Hợp đồng mà client phụ thuộc: không tiết lộ cách lưu state.
interface SeatInventory {
    boolean tryReserve(int count);
    void cancel(int count);
    SeatSnapshot snapshot();
}

// Cách A: khóa bảo vệ toàn bộ check + update trên một instance.
final class MonitorSeatInventory implements SeatInventory {
    private final int capacity;
    private int reserved;

    MonitorSeatInventory(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
    }

    @Override
    public synchronized boolean tryReserve(int count) {
        requirePositive(count);

        if (count > capacity - reserved) {
            return false;
        }

        reserved += count;
        return true;
    }

    @Override
    public synchronized void cancel(int count) {
        requirePositive(count);

        if (count > reserved) {
            throw new IllegalArgumentException(
                    "Cannot cancel more than reserved");
        }

        reserved -= count;
    }

    @Override
    public synchronized SeatSnapshot snapshot() {
        return new SeatSnapshot(capacity, reserved);
    }

    private static void requirePositive(int count) {
        if (count <= 0) {
            throw new IllegalArgumentException("count must be positive");
        }
    }
}

// Cách B: CAS đảm bảo không làm mất cập nhật trên một biến.
final class AtomicSeatInventory implements SeatInventory {
    private final int capacity;
    private final AtomicInteger reserved = new AtomicInteger();

    AtomicSeatInventory(int capacity) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }
        this.capacity = capacity;
    }

    @Override
    public boolean tryReserve(int count) {
        requirePositive(count);

        while (true) {
            int current = reserved.get();

            // Trừ trước để không làm tràn số nguyên do cộng.
            if (count > capacity - current) {
                return false;
            }

            if (reserved.compareAndSet(current, current + count)) {
                return true;
            }
            // Có cập nhật cạnh tranh: đọc lại và thử.
        }
    }

    @Override
    public void cancel(int count) {
        requirePositive(count);

        while (true) {
            int current = reserved.get();

            if (count > current) {
                throw new IllegalArgumentException(
                        "Cannot cancel more than reserved");
            }

            if (reserved.compareAndSet(current, current - count)) {
                return;
            }
        }
    }

    @Override
    public SeatSnapshot snapshot() {
        // capacity không đổi; reserved.get là một phép đọc atomic.
        return new SeatSnapshot(capacity, reserved.get());
    }

    private static void requirePositive(int count) {
        if (count <= 0) {
            throw new IllegalArgumentException("count must be positive");
        }
    }
}

public class SeatInventoryDemo {
    public static void main(String[] args) {
        SeatInventory inventory = new MonitorSeatInventory(10);

        System.out.println("Start: " + inventory.snapshot());
        System.out.println("Reserve 4: " + inventory.tryReserve(4));
        System.out.println("Reserve 7: " + inventory.tryReserve(7));
        System.out.println("After refusal: " + inventory.snapshot());

        inventory.cancel(2);
        System.out.println("After cancel: " + inventory.snapshot());

        // Không sửa nghiệp vụ client khi đổi implementation:
        SeatInventory another = new AtomicSeatInventory(10);
        System.out.println("Atomic reserve 4: " + another.tryReserve(4));
        System.out.println("Atomic snapshot: " + another.snapshot());
    }
}
~~~

Chạy:

~~~bash
javac SeatInventoryDemo.java
java SeatInventoryDemo
~~~

Kết quả:

~~~text
Start: SeatSnapshot[capacity=10, reserved=0]
Reserve 4: true
Reserve 7: false
After refusal: SeatSnapshot[capacity=10, reserved=4]
After cancel: SeatSnapshot[capacity=10, reserved=2]
Atomic reserve 4: true
Atomic snapshot: SeatSnapshot[capacity=10, reserved=4]
~~~

**Điều quan trọng không nằm ở việc thuật toán lock hay CAS tốt hơn.** Ví dụ có hai giải pháp kỹ thuật khác nhau để test xác minh **một hành vi được cam kết duy nhất**.

### Sơ đồ nhìn từ phía client

~~~mermaid
classDiagram
    class SeatInventory {
        <<interface>>
        +tryReserve(count) boolean
        +cancel(count) void
        +snapshot() SeatSnapshot
    }
    class MonitorSeatInventory {
        -int reserved
        +tryReserve(count) boolean
        +cancel(count) void
        +snapshot() SeatSnapshot
    }
    class AtomicSeatInventory {
        -AtomicInteger reserved
        +tryReserve(count) boolean
        +cancel(count) void
        +snapshot() SeatSnapshot
    }
    class SeatSnapshot {
        <<record>>
        +capacity() int
        +reserved() int
        +available() int
    }

    SeatInventory <|.. MonitorSeatInventory
    SeatInventory <|.. AtomicSeatInventory
    SeatInventory ..> SeatSnapshot : công bố
~~~

## 5. Viết test từ hợp đồng trước, rồi áp dụng cho cả hai lớp

Nếu viết hai bộ test tách rời hoàn toàn, một implementation dễ bị bỏ quên test đường lỗi. Cách đáng học là viết **một bộ contract tests tái sử dụng**: test chỉ biết interface `SeatInventory`, còn lớp con của test cung cấp cách tạo implementation.

Trong JUnit Jupiter 5, các phương thức `@Test` ở lớp cha có thể được kế thừa bởi test subclass. Chúng ta tận dụng tính năng này để chạy cùng bộ luật cho cả Monitor và Atomic.

Tạo tệp **`SeatInventoryContractTest.java`** trong test source set, cùng package với `SeatInventoryDemo.java`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

// Abstract contract test: không biết field/lock/CAS của implementation.
abstract class SeatInventoryContractTest {
    protected abstract SeatInventory create(int capacity);

    @Test
    void startsEmptyAndExposesConsistentSnapshot() {
        SeatInventory inventory = create(10);

        SeatSnapshot initial = inventory.snapshot();

        assertEquals(10, initial.capacity());
        assertEquals(0, initial.reserved());
        assertEquals(10, initial.available());
    }

    @Test
    void acceptsReservationAndChangesObservableState() {
        SeatInventory inventory = create(10);

        assertTrue(inventory.tryReserve(4));

        SeatSnapshot snapshot = inventory.snapshot();
        assertEquals(4, snapshot.reserved());
        assertEquals(6, snapshot.available());
    }

    @Test
    void insufficientCapacityReturnsFalseWithoutMutation() {
        SeatInventory inventory = create(10);
        assertTrue(inventory.tryReserve(4));

        SeatSnapshot before = inventory.snapshot();
        assertFalse(inventory.tryReserve(7));
        SeatSnapshot after = inventory.snapshot();

        assertEquals(before, after); // So sánh record theo giá trị.
    }

    @Test
    void cancellationDecreasesReservation() {
        SeatInventory inventory = create(10);
        assertTrue(inventory.tryReserve(4));

        inventory.cancel(2);

        SeatSnapshot after = inventory.snapshot();
        assertEquals(2, after.reserved());
        assertEquals(8, after.available());
    }

    @Test
    void invalidArgumentsThrowAndDoNotChangeState() {
        SeatInventory inventory = create(10);
        assertTrue(inventory.tryReserve(3));

        SeatSnapshot before = inventory.snapshot();

        assertThrows(IllegalArgumentException.class,
                () -> inventory.tryReserve(0));
        assertThrows(IllegalArgumentException.class,
                () -> inventory.tryReserve(-1));
        assertThrows(IllegalArgumentException.class,
                () -> inventory.cancel(0));
        assertThrows(IllegalArgumentException.class,
                () -> inventory.cancel(4));

        assertEquals(before, inventory.snapshot());
    }

    @Test
    void exactCapacityAndReleaseAllAreAllowed() {
        SeatInventory inventory = create(2);

        assertTrue(inventory.tryReserve(2));
        assertFalse(inventory.tryReserve(1));
        assertEquals(0, inventory.snapshot().available());

        inventory.cancel(2);

        assertEquals(0, inventory.snapshot().reserved());
        assertEquals(2, inventory.snapshot().available());
    }

    @Test
    void invalidCapacityIsRejected() {
        assertThrows(IllegalArgumentException.class, () -> create(0));
        assertThrows(IllegalArgumentException.class, () -> create(-1));
    }
}

// Hai implementation được kiểm tra bằng CÙNG bộ @Test.
class MonitorSeatInventoryTest extends SeatInventoryContractTest {
    @Override
    protected SeatInventory create(int capacity) {
        return new MonitorSeatInventory(capacity);
    }
}

class AtomicSeatInventoryTest extends SeatInventoryContractTest {
    @Override
    protected SeatInventory create(int capacity) {
        return new AtomicSeatInventory(capacity);
    }
}
~~~

**Kết quả mong muốn:** JUnit chạy cùng các test được kế thừa cho cả hai lớp con. Mỗi implementation phải đáp ứng toàn bộ contract. Lớp cha abstract chỉ mô tả các yêu cầu quan sát được; không kiểm tra `reserved` có là `int` hay `AtomicInteger`.

Để chạy cần thêm JUnit Jupiter vào test dependencies và dùng test runner của Maven/Gradle/IDE. Hai class test cụ thể là **package-private**, hợp lệ trong JUnit Jupiter 5; tùy cấu hình discovery của công cụ build, bảo đảm source nằm trong test source set và được nhận diện đúng tên `*Test`.

### Vì sao test “đường lỗi không đổi trạng thái” quan trọng?

Một implementation sai có thể làm:

~~~java
// CỐ Ý SAI: tăng reserved trước rồi mới kiểm tra.
reserved += count;
if (reserved > capacity) {
    return false;
}
~~~

Test chỉ xác nhận `tryReserve(7) == false` **sẽ pass**, dù `reserved` đã bị làm hỏng. Khi kiểm tra **snapshot trước và sau**, contract test phát hiện lỗi đó. Tương tự, hủy quá số lượng phải ném exception **mà không để lại state nửa vời**.

## 6. Tổ chức test theo Given–When–Then

Một test về hành vi sẽ dễ đọc hơn nếu có ba phần rõ ràng:

- **Given:** trạng thái ban đầu và dữ liệu dùng để tạo đối tượng.
- **When:** một lời gọi công khai được thực hiện.
- **Then:** kết quả, exception, observable state hoặc side effect đúng hợp đồng.

Ví dụ:

~~~java
@Test
void rejectedReservationKeepsPreviousState() {
    // Given
    SeatInventory inventory = new MonitorSeatInventory(5);
    inventory.tryReserve(4);
    SeatSnapshot before = inventory.snapshot();

    // When
    boolean accepted = inventory.tryReserve(2);

    // Then
    assertFalse(accepted);
    assertEquals(before, inventory.snapshot());
}
~~~

Cách đặt tên `rejectedReservationKeepsPreviousState` nói rõ **quy tắc** bị kiểm chứng hơn tên `testReserve` hay `test1`. Phần “Then” nên dùng API quan sát hợp lệ. Không cần tạo setter chỉ để test được; làm vậy có thể làm yếu encapsulation.

## 7. Kiểm thử chuỗi trạng thái, không chỉ từng method đơn lẻ

Một đối tượng có trạng thái thường có **nhiều đường đi hợp lệ**. Test từng method độc lập có thể bỏ qua bug chỉ xuất hiện sau một chuỗi thao tác.

~~~mermaid
stateDiagram-v2
    [*] --> Empty : new(10)
    Empty --> Partial : reserve(4) = true
    Partial --> Partial : reserve(7) = false
    Partial --> Partial : cancel(2)
    Partial --> Full : reserve(8) = true
    Full --> Full : reserve(1) = false
    Full --> Empty : cancel(all)
~~~

Sơ đồ minh họa với sức chứa 10: sau khi đặt 4 rồi hủy 2 thì còn đặt 2, tiếp tục đặt 8 sẽ đầy. Đó là **hành vi nhiều bước** chứ không phải một method isolated.

### Kiểm thử theo bảng trạng thái

| Trạng thái trước | Lệnh | Kết quả | Trạng thái sau |
|---|---|---|---|
| capacity=10, reserved=0 | `tryReserve(4)` | `true` | reserved=4 |
| capacity=10, reserved=4 | `tryReserve(7)` | `false` | reserved=4 |
| capacity=10, reserved=4 | `cancel(2)` | Thành công | reserved=2 |
| capacity=10, reserved=2 | `tryReserve(8)` | `true` | reserved=10 |
| capacity=10, reserved=10 | `tryReserve(1)` | `false` | reserved=10 |
| capacity=10, reserved=10 | `cancel(10)` | Thành công | reserved=0 |

Dữ liệu biên `0`, `1`, `capacity`, `capacity + 1` và số âm cũng đáng kiểm thử. Khi có nhiều trạng thái/đường đi, lập bảng giúp tránh việc một test chỉ kiểm tra “happy path” rồi bỏ quên quy tắc từ chối.

### Kiểm thử bằng mô hình tham chiếu đơn giản

Với loại API có state, có thể viết một **model trong test** chỉ lưu giá trị mong đợi và thử nhiều chuỗi thao tác. Model nên đơn giản hơn implementation thật và không dùng cùng thuật toán tối ưu, để tránh copy chung lỗi.

Đoạn sau là một test bổ sung, dùng các class và import JUnit ở phần trước; thêm `import java.util.Random;`:

~~~java
@Test
void sequenceOfOperationsAlwaysMatchesSimpleModel() {
    SeatInventory inventory = create(20);
    Random random = new Random(2026L);
    int expectedReserved = 0;

    for (int step = 0; step < 500; step++) {
        int quantity = 1 + random.nextInt(7);

        if (random.nextBoolean()) {
            boolean shouldAccept = quantity <= 20 - expectedReserved;
            assertEquals(shouldAccept,
                    inventory.tryReserve(quantity));

            if (shouldAccept) {
                expectedReserved += quantity;
            }
        } else if (quantity <= expectedReserved) {
            inventory.cancel(quantity);
            expectedReserved -= quantity;
        } else {
            // Với precondition sai, exception không đổi trạng thái.
            assertThrows(IllegalArgumentException.class,
                    () -> inventory.cancel(quantity));
        }

        SeatSnapshot snapshot = inventory.snapshot();
        assertEquals(20, snapshot.capacity());
        assertEquals(expectedReserved, snapshot.reserved());
        assertEquals(20 - expectedReserved, snapshot.available());
    }
}
~~~

**Ưu điểm:** một seed cố định tạo một chuỗi dễ tái hiện; các trạng thái khác nhau được đi qua mà không phải viết tay 500 test case. **Giới hạn:** một seed và 500 bước không phải bằng chứng hình thức cho mọi chuỗi; cần kết hợp các boundary cases, nhiều seed hoặc property-based testing khi rủi ro cao.

**Lưu ý:** Nếu phương thức có tác dụng phụ khác (ghi DB, gửi sự kiện), model phải mô tả những observable effects đó; chỉ so sánh state trong memory sẽ chưa đủ.

## 8. Kiểm thử tính thay thế của implementation (LSP)

**Liskov Substitution Principle (LSP)** yêu cầu implementation có thể được dùng ở nơi mong đợi abstraction mà **không làm sai điều client dựa vào**. Test contract là một bằng chứng thực nghiệm rất hữu ích: cùng một test được chạy trên mọi implementation.

Giả sử một implementation mới quyết định:

~~~java
// Vi phạm hợp đồng ví dụ:
boolean tryReserve(int count) {
    if (count <= 0) {
        return false; // Sai: contract yêu cầu IllegalArgumentException.
    }
    // ...
}
~~~

Compiler **không báo lỗi** vì chữ ký vẫn đúng. Nhưng contract test `invalidArgumentsThrowAndDoNotChangeState` sẽ thất bại. Tương tự, nếu thiếu chỗ mà implementation ném `IllegalStateException` thay vì trả `false`, client đang dựa vào boolean sẽ hoạt động khác.

Một interface **không tự bảo đảm LSP**. Chữ ký là một phần hợp đồng; ngữ nghĩa đầu vào, đầu ra, exception, tính nhất quán và bảo đảm side effect cũng quan trọng.

Một số nguyên tắc thực hành:

- Implementation không nên đột ngột **siết tiền điều kiện** nếu abstraction cho phép nhiều input hơn.
- Implementation không nên **làm yếu hậu điều kiện** mà client được hứa.
- Mọi invariant cần bảo toàn khi client sử dụng qua abstraction.
- Với exception, phân biệt lỗi lập trình của caller, lỗi nghiệp vụ dự kiến và lỗi hạ tầng; không tự ý đổi failure mode mà không cập nhật hợp đồng.

**Contract tests không chứng minh toán học LSP hoàn toàn.** Chúng kiểm tra một tập tình huống được chọn. Review thiết kế vẫn cần xem quan hệ subtype và những bảo đảm chưa được test, đặc biệt các khía cạnh hiệu năng, concurrency, transactional behavior và bảo mật.

## 9. Kiểm thử bất biến của value object: `equals`, `hashCode` và `toString`

Trong Java, các phương thức kế thừa từ `Object` cũng có những hợp đồng đáng quan tâm. Tuy nhiên không phải class nào cũng override chúng. Hai nhóm test khác nhau:

1. **Hợp đồng nghiệp vụ:** `SeatInventory` giữ `0 ≤ reserved ≤ capacity`.
2. **Hợp đồng về giá trị:** một value object có `equals`/`hashCode` đúng và biểu diễn chẩn đoán phù hợp.

Trong ví dụ, `SeatSnapshot` là một `record` chứa primitive, Java tự cung cấp `equals` và `hashCode` theo các component. Ta có thể kiểm thử qua API công khai:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;

class SeatSnapshotValueTest {
    @Test
    void equalSnapshotsAreEqualAndHaveEqualHashCodes() {
        SeatSnapshot a = new SeatSnapshot(10, 4);
        SeatSnapshot b = new SeatSnapshot(10, 4);
        SeatSnapshot different = new SeatSnapshot(10, 5);

        assertEquals(a, b);
        assertEquals(a.hashCode(), b.hashCode());
        assertNotEquals(a, different);

        Set<SeatSnapshot> set = new HashSet<>();
        set.add(a);
        assertTrue(set.contains(b));
    }

    @Test
    void rejectsBrokenInvariant() {
        assertThrows(IllegalArgumentException.class,
                () -> new SeatSnapshot(10, 11));
        assertThrows(IllegalArgumentException.class,
                () -> new SeatSnapshot(0, 0));
    }
}
~~~

Đây là kiểm thử hợp đồng **giá trị**. Đối với entity có **identity**, hai object khác nhau nhưng cùng dữ liệu hiển thị có thể không được xem là bằng nhau; cần xác định rõ quan hệ `equals` mong muốn trước khi viết test.

### Những quy tắc `equals` thường cần biết

| Quy tắc | Diễn đạt | Test đơn giản |
|---|---|---|
| Phản xạ | `x.equals(x) == true` | `assertEquals(x, x)` |
| Đối xứng | `x.equals(y) == y.equals(x)` | So sánh cả hai chiều |
| Bắc cầu | Nếu `x==y` và `y==z`, thì `x==z` theo `equals` | Tạo ba instance tương đương |
| Nhất quán | Không thay dữ liệu dùng để so sánh thì kết quả không tự đổi | Gọi lặp lại trên state ổn định |
| Không bằng null | `x.equals(null) == false` | `assertNotEquals(null, x)` |
| Tương thích hash | Nếu `x.equals(y)` thì `x.hashCode()==y.hashCode()` | So sánh hash và dùng `HashSet` |

Không được suy luận ngược rằng **hash code bằng nhau ⇒ object bằng nhau**. Hai đối tượng khác nhau vẫn có thể có cùng hash.

`toString()` thường dùng để quan sát/debug, không phải định dạng API ổn định trừ khi class công bố hợp đồng cụ thể. Đừng tạo test khớp toàn bộ dấu câu của `toString()` nếu tài liệu không hứa format ấy. Với dữ liệu nhạy cảm, nên kiểm thử những thông tin **không được lộ**, đồng thời xem xét các đường log khác.

## 10. Không mở private field hay thêm setter chỉ để “test được”

Một kiểu test dễ gây hại:

~~~java
// Ý tưởng KHÔNG NÊN làm mặc định:
Field field = MonitorSeatInventory.class
        .getDeclaredField("reserved");
field.setAccessible(true);
field.setInt(inventory, 4);
~~~

Nếu test biết tên field và dùng reflection để thay đổi nó, bản thân test đã vượt qua ranh giới mà class cần bảo vệ. Refactor tên field hoặc chuyển sang `AtomicInteger` khiến test hỏng, dù client không bị ảnh hưởng.

Tương tự, thêm `setReserved(int)` chỉ để dựng trạng thái nhanh có thể làm API production yếu đi, cho phép client bỏ qua quy tắc đặt chỗ. Thay vào đó, dựng trạng thái hợp lệ bằng **public operations**:

~~~java
SeatInventory inventory = new MonitorSeatInventory(10);
assertTrue(inventory.tryReserve(4));
// Bây giờ có trạng thái reserved = 4, hợp lệ và tạo qua API thật.
~~~

Nếu setup quá dài vì mỗi test phải chạy qua nhiều hệ thống ngoài, cân nhắc **test fixture/builder** để tạo dependency hoặc dữ liệu phù hợp. Fixture không nên tạo ra những trạng thái bất khả thi mà hành vi thực không thể đạt được, trừ khi đang cố ý kiểm thử khả năng hồi phục từ dữ liệu legacy hỏng.

### Không bám quá mức vào số lần gọi nội bộ

Mock có ích khi một tương tác với dependency **là phần của hợp đồng**, chẳng hạn chỉ phát một sự kiện sau khi thanh toán thành công. Nhưng nếu chỉ kiểm tra `verify(calculator).calculate(...)` mà không khẳng định kết quả hoặc hệ quả quan sát được, test có thể pass ngay cả khi business result sai.

Phân biệt:

- **State-based test:** kiểm tra state/result được công bố.
- **Interaction-based test:** kiểm tra những tương tác với cộng tác viên có ý nghĩa ra bên ngoài, như gửi thông báo đúng một lần.
- **Implementation-coupled test:** kiểm tra thứ tự private helper hoặc số lần gọi một thuật toán thuần mà caller không biết tới.

Không phải interaction test luôn kém. Điều quan trọng là tương tác ấy **được hợp đồng yêu cầu hay chỉ là cách triển khai hiện tại**.

## 11. Kiểm thử lỗi và exception: kết quả thất bại cũng là hành vi

Một hợp đồng công khai tốt cần nói rõ input sai sẽ được xử lý thế nào:

| Tình huống | Hành vi theo ví dụ | Điều test cần xác nhận |
|---|---|---|
| Tạo kho `capacity = 0` | Ném `IllegalArgumentException` | Không tạo đối tượng hợp lệ giả |
| Đặt `0` hoặc số âm | Ném `IllegalArgumentException` | State không đổi |
| Đặt vượt số chỗ còn | Trả `false` | State không đổi |
| Hủy nhiều hơn số đã đặt | Ném `IllegalArgumentException` | State không đổi |
| Hủy đúng số đã đặt | Thành công | State quay về reserved=0 |
| Chuyển implementation Monitor sang Atomic | Giữ toàn bộ ngữ nghĩa công khai | Bộ contract test vẫn pass |

`assertThrows` kiểm tra đúng loại exception trong trường hợp contract hứa. Nếu exception message không được coi là API ổn định, không nên khóa cứng nguyên văn message trong test. Nếu mã lỗi là một phần hợp đồng giao tiếp, hãy kiểm tra mã lỗi có cấu trúc thay vì phụ thuộc câu chữ.

### Phạm vi nguyên tử của đường lỗi

Trong ví dụ, exception được ném **trước khi** state bị cập nhật khi số lượng không hợp lệ. Với các thao tác phức tạp hơn, nếu đã ghi database rồi mới ném exception do gửi email thất bại, "throw exception" không đồng nghĩa "mọi side effect đều rollback". Test cần định nghĩa trạng thái sau lỗi theo tính nhất quán thực tế: transaction, outbox, retry hoặc compensation.

## 12. Contract test và kiểm thử đồng thời

Nếu abstraction công bố rằng hai thread có thể gọi `tryReserve(1)` trên cùng instance, tính nguyên tử cũng là **một phần hợp đồng**, không chỉ chi tiết implement.

Ví dụ JUnit Jupiter 5 kiểm tra **một implementation bất kỳ** qua interface. Có thể đặt đoạn này trong `SeatInventoryContractTest` và thêm các import cần thiết:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

@Test
void concurrentReservationsNeverOversellOneInstance()
        throws Exception {
    SeatInventory inventory = create(5);
    int attempts = 12;

    CountDownLatch ready = new CountDownLatch(attempts);
    CountDownLatch start = new CountDownLatch(1);
    ExecutorService pool = Executors.newFixedThreadPool(attempts);

    try {
        List<Future<Boolean>> results = new ArrayList<>();

        for (int i = 0; i < attempts; i++) {
            results.add(pool.submit(() -> {
                ready.countDown();
                start.await();
                return inventory.tryReserve(1);
            }));
        }

        assertTrue(ready.await(5, TimeUnit.SECONDS));
        start.countDown();

        int accepted = 0;
        for (Future<Boolean> future : results) {
            if (future.get(5, TimeUnit.SECONDS)) {
                accepted++;
            }
        }

        assertEquals(5, accepted);
        assertEquals(5, inventory.snapshot().reserved());
        assertEquals(0, inventory.snapshot().available());
    } finally {
        start.countDown(); // Không để task chờ vô hạn nếu assert fail.
        pool.shutdownNow();
    }
}
~~~

Điều này kiểm tra **kết quả cuối cùng** sau khi mọi lời gọi hoàn tất và hai thread/nhóm thread cùng tranh chỗ. `CountDownLatch` giúp bắt đầu gần nhau, nhưng **không tạo bằng chứng toán học về mọi lịch thực thi**. Nếu rủi ro concurrency cao, cần kết hợp stress test, review memory model, công cụ kiểm thử concurrency chuyên biệt và/hoặc mô hình hóa.

Không nên dùng `Thread.sleep` với khoảng chờ tùy ý để quyết định test pass/fail. Cũng không nên kiểm tra `reserved + available == capacity` bằng **hai lời gọi snapshot ở hai thời điểm khác nhau** trong khi các thread còn đang cập nhật; hãy lấy **một snapshot nhất quán**, rồi tính từ dữ liệu của snapshot ấy.

### Giới hạn một JVM

Một contract về thread safety trên một Java object không tự bảo đảm điều kiện bán vé khi hai JVM cùng cập nhật **một bản ghi trong database**. Khi API triển khai trên nhiều node, contract ở cấp service cần được xác minh bằng transaction, update có điều kiện hoặc optimistic locking ở tầng persistence. Unit test của `AtomicSeatInventory` không thay thế integration test DB.

## 13. Các tầng kiểm thử: cùng một hợp đồng, bằng chứng khác nhau

| Tầng | Mục tiêu | Ví dụ |
|---|---|---|
| **Unit test đối tượng** | Hợp đồng hành vi công khai của một object | `tryReserve`, `cancel`, `snapshot` |
| **Contract test cho interface** | Mọi implementation giữ cùng ngữ nghĩa | Monitor và Atomic chạy chung bộ test |
| **Component/integration test** | Tương tác giữa nhiều class hoặc hệ thống thực | Kho vé lưu trong repository/JDBC |
| **API test** | Hợp đồng HTTP/JSON/status code | Hết vé trả mã lỗi nghiệp vụ phù hợp |
| **Concurrency test** | Tính nhất quán khi thao tác đan xen | Nhiều yêu cầu không thể cùng chiếm một chỗ |
| **End-to-end test** | Luồng người dùng qua nhiều thành phần | Chọn vé → đặt → xác nhận hiển thị |

Một bài unit test nhanh có thể chứng minh `SeatInventory` đúng logic trong memory, nhưng không chứng minh DB lock, rollback, API serializer hay trải nghiệm người dùng cuối đúng. Hãy chọn **mức kiểm thử tương ứng với ranh giới hợp đồng**.

## 14. Các lỗi thiết kế test thường làm giảm giá trị kiểm thử

### Lỗi A: Test implementation thay vì contract

~~~java
// Đáng ngờ:
assertEquals("java.util.concurrent.atomic.AtomicInteger",
        inventory.getClass()
                .getDeclaredFields()[0]
                .getType()
                .getName());
~~~

Test này không nói kho vé có đúng hay không, chỉ khóa lựa chọn triển khai. Đổi state từ atomic sang lock có thể là refactor hợp lý nhưng test sẽ hỏng vô ích.

### Lỗi B: Chỉ assert kết quả trả về, bỏ qua state

~~~java
assertFalse(inventory.tryReserve(100));
~~~

Nếu implementation vẫn tăng `reserved` rồi trả `false`, test sẽ không phát hiện. Nên lấy snapshot trước/sau và xác minh invariant.

### Lỗi C: Thử đường lỗi bằng cách làm hỏng private state

Nếu test đặt `reserved = -5` bằng reflection rồi yêu cầu `tryReserve` tự sửa, test đang áp đặt một trường hợp **không đi qua API hợp lệ**. Trừ khi yêu cầu thật là phục hồi dữ liệu cũ bị hỏng, tốt hơn nên kiểm tra tất cả **đường thay đổi công khai** không bao giờ tạo được trạng thái ấy.

### Lỗi D: Các test phụ thuộc thứ tự hoặc state chung

Một `static SeatInventory shared` được mọi test mutate khiến kết quả thay đổi khi JUnit chạy song song hoặc đổi thứ tự. Mỗi test nên có **fixture độc lập**, dựng một instance mới. Khi cần DB chung, phải có chiến lược cô lập/cleanup rõ ràng.

### Lỗi E: Mock chính đối tượng đang muốn kiểm chứng

Nếu mock toàn bộ `SeatInventory` và cấu hình `when(tryReserve(4)).thenReturn(true)`, ta chỉ kiểm tra hành vi do test **tự cài đặt**, chứ không kiểm tra implementation thật. Dùng mock/fake cho collaborator ngoài phạm vi test, không thay thế system under test khi mục tiêu là contract của chính nó.

### Lỗi F: Quá phụ thuộc implementation của logger, thời gian hay ngẫu nhiên

Nếu hợp đồng không yêu cầu ghi log một câu cụ thể, test nên xác nhận kết quả quan sát được thay vì nguyên văn log. Với đồng hồ/ngẫu nhiên thực sự là đầu vào nghiệp vụ, inject `Clock` hoặc random generator/fake có kiểm soát để test không flaky.

## 15. Viết contract tests cho adapter thực tế

Mẫu kiểm thử chung không chỉ áp dụng cho hai kiểu lưu state trong bộ nhớ. Ví dụ một `DocumentStore` có implementation dùng file hoặc database:

~~~java
interface DocumentStore {
    void save(String id, byte[] bytes);
    java.util.Optional<byte[]> find(String id);
}
~~~

Một hợp đồng có thể yêu cầu:

- Không nhận ID null hoặc rỗng.
- Lưu dữ liệu rồi tìm lại được cùng **nội dung byte**.
- Khi không có ID thì trả `Optional.empty()`.
- Sửa `byte[]` truyền vào sau `save` không được âm thầm sửa dữ liệu đã lưu.
- Sửa `byte[]` trả ra từ `find` không được âm thầm sửa dữ liệu được lưu, nếu API cam kết snapshot.
- Khi lưu trùng ID, phải có quy tắc rõ là **overwrite** hay **reject**; cả hai implementation phải thống nhất.

Với mảng `byte[]` mutable, cần **defensive copy** ở cả đường vào và đường ra nếu đó là cam kết của API. Một `InMemoryDocumentStore` giữ tham chiếu byte array gốc sẽ dễ vi phạm hợp đồng dù method có đúng chữ ký.

Đây là ví dụ vì sao **contract test chứa giá trị lớn hơn việc test có đúng số method**: nó giữ cả hành vi mà Java type system không biểu diễn trực tiếp, như **ownership của mutable buffer** và thất bại khi lưu trùng.

## 16. Checklist thiết kế kiểm thử hành vi công khai

Trước khi viết test, trả lời:

1. **Đối tượng hứa điều gì?** Viết precondition, postcondition, invariant, failure mode.
2. **API nào là public contract?** Đừng mở private field chỉ vì test setup khó.
3. **Trạng thái ban đầu là gì?** Mỗi test phải dựng fixture nhất quán, độc lập.
4. **Những observable results nào cần so sánh?** Return value, snapshot, exception, event, persisted data.
5. **Có đường từ chối không?** Khi thất bại, state và side effect phải ra sao?
6. **Đâu là trường hợp biên?** Zero, negative, max, empty, null, trùng lặp, overflow, chuyển trạng thái.
7. **Có nhiều implementation không?** Dùng cùng contract suite để kiểm tra khả năng thay thế.
8. **Có yếu tố thời gian/concurrency/I/O?** Dùng clock/fake/test fixture, integration tests và synchronization đúng phạm vi.
9. **Test có giòn khi refactor nội bộ không?** Xóa assert không thuộc hợp đồng, giữ những gì client cần.
10. **Thay đổi hợp đồng đã được phê duyệt chưa?** Khi business rule đổi, cập nhật đặc tả và test có chủ đích, không sửa test chỉ để đèn xanh.

Một kỹ thuật hữu ích là viết tên test thành câu **“Khi X, hệ thống phải Y”** rồi yêu cầu một reviewer không biết implementation vẫn hiểu được câu ấy. Nếu tên test chỉ nói `testPrivateHelperA`, có lẽ chưa nhắm đúng hành vi client quan tâm.

## 17. Bài tập thực hành: hợp đồng ví điện tử

Thiết kế một interface:

~~~java
interface Wallet {
    long balanceCents();
    void deposit(long amountCents);
    boolean tryWithdraw(long amountCents);
}
~~~

Các quy tắc giả định:

- Ví khởi tạo với số dư không âm.
- `deposit(n)` yêu cầu `n > 0`; khi thành công tăng đúng `n`.
- `tryWithdraw(n)` yêu cầu `n > 0`; khi đủ tiền, trừ đúng `n` và trả `true`; khi không đủ tiền, trả `false` và giữ nguyên số dư.
- Không bao giờ có số dư âm; xử lý overflow khi nạp tiền (`Math.addExact` hoặc kiểm tra trước).
- Các thao tác trên **một instance** hỗ trợ nhiều thread; hai lệnh rút tiền không thể cùng dùng một số dư cũ để đều thành công.
- Test nên dùng số nguyên biểu diễn **đơn vị tiền nhỏ nhất** để tránh sai số nhị phân trong phạm vi ví dụ.

Yêu cầu:

1. Viết `SynchronizedWallet` và `AtomicWallet`.
2. Viết một abstract contract test dùng cùng `@Test` cho cả hai implementation.
3. Có test cho `deposit(0)`, rút âm, rút vượt số dư, nạp tràn `long`, và xác nhận state giữ nguyên sau lỗi.
4. Có test cho chuỗi `deposit(100) → withdraw(30) → withdraw(80 bị từ chối)`.
5. Có test hai thread cùng rút 80 từ ví có 100; **chỉ một thành công**.
6. Giải thích tại sao unit test này chưa chứng minh tính đúng đắn của giao dịch tiền thật trên database hoặc dịch vụ thanh toán.

### Câu hỏi tự kiểm tra

1. “Kiểm thử hành vi công khai” khác kiểm tra private field ra sao?
2. Vì sao cùng một method signature không bảo đảm hai implementation có thể thay thế nhau?
3. Tiền điều kiện, hậu điều kiện và invariant khác nhau thế nào?
4. Tại sao chỉ assert `tryReserve(7) == false` là chưa đủ?
5. Vì sao nên chạy cùng contract suite cho mọi implementation của một interface?
6. Khi nào test `equals/hashCode` cần thiết, và vì sao không suy ra `hashCode` bằng nhau là object bằng nhau?
7. Có nên dùng reflection để thay private state chỉ nhằm rút ngắn test setup không?
8. Vì sao assert chính xác thông điệp log dễ làm test giòn nếu log không thuộc hợp đồng?
9. Test concurrency cùng JVM có đủ để chứng minh không bán quá số vé trong môi trường nhiều node không?
10. Những observable effects nào cần kiểm tra khi method vừa cập nhật DB vừa phát sự kiện?

**Ghi nhớ:** Kiểm thử tốt cho OOP trả lời câu hỏi **“Đối tượng có giữ lời hứa với client không?”**. Hãy mô tả hợp đồng một cách quan sát được, kiểm tra cả thành công lẫn thất bại, dùng state snapshots và test chuỗi thao tác, rồi áp dụng cùng bộ test cho những implementation thay thế. Việc tách test khỏi chi tiết nội bộ làm refactor dễ hơn **mà không giảm tiêu chuẩn đúng đắn của hành vi**.