# Kiểm thử giá trị bằng nhau, null theo comparator và quy tắc miền

Khi sắp xếp dữ liệu theo thời gian và định danh, một `Comparator` phải thể hiện rõ thứ tự nghiệp vụ: thời điểm nào đứng trước, timestamp thiếu được xếp ở đâu, hai sự kiện cùng thời điểm được phân biệt bằng khóa nào, và hai giá trị được xem là tương đương trong thứ tự có thực sự là cùng một thực thể hay không. Các quy tắc này cần được kiểm thử trực tiếp; chỉ kiểm tra rằng `list.sort(...)` không ném exception là chưa đủ.

Trong Java, `compare(a, b) == 0` có nghĩa hai giá trị tương đương theo thứ tự do comparator định nghĩa. Điều đó không tự động có nghĩa `a.equals(b)` là `true`. Sự khác biệt này ảnh hưởng đến `TreeSet`, `TreeMap`, việc loại bỏ bản ghi trùng và cách xác định tie-breaker. `Comparator.nullsFirst`/`nullsLast` quy định vị trí của null; comparator cho khóa null và comparator cho chính object null là hai lớp xử lý riêng.

Các API dùng trong bài (`Comparator`, `Comparable`, `Instant`, `UUID`, `BigDecimal`, `TreeSet`, JUnit Jupiter) đều là API ổn định đang được sử dụng. Không có preview hoặc incubator feature riêng cho các phép kiểm thử này trong Java 26. Trọng tâm là kiểm thử hợp đồng và quy tắc miền, không gắn nhãn các API lâu đời thành tính năng mới của Java 26. [Java 26 `Comparator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html) · [Java 26 `Instant`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html) · [Java 26 `UUID`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/UUID.html).

## 1. `compare(a, b) == 0` thực sự có nghĩa gì?

`Comparator<T>` cung cấp thứ tự giữa hai giá trị bằng `compare(T a, T b)`. Kết quả là một số âm, số 0 hoặc số dương:

- Số âm: `a` đứng trước `b`.
- Số 0: `a` và `b` tương đương theo thứ tự của comparator.
- Số dương: `a` đứng sau `b`.

Không yêu cầu kết quả phải chính xác là `-1`, `0` hoặc `1`. Hãy kiểm tra dấu bằng `Integer.signum(result)` hoặc các phép so sánh `< 0`, `== 0`, `> 0`.

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);

int result = byLength.compare("cat", "dog");
// result == 0 vì cả hai chuỗi có độ dài bằng nhau.
// "cat".equals("dog") vẫn là false.
```

Comparator trên chỉ sắp xếp theo độ dài. Hai chuỗi khác nhau nhưng có cùng độ dài tạo thành một lớp tương đương trong thứ tự này. Đây là hành vi hợp lệ nếu mục tiêu là nhóm theo độ dài; nó có thể không phù hợp nếu comparator được dùng làm khóa duy nhất trong `TreeSet`.

### Phân biệt ba khái niệm

| Biểu thức | Câu hỏi được trả lời |
|---|---|
| `a.equals(b)` | Hai object có bằng nhau theo định nghĩa equality của class không? |
| `comparator.compare(a, b) == 0` | Hai object có cùng vị trí tương đương theo thứ tự đang xét không? |
| `comparator.equals(otherComparator)` | Hai comparator object có tự định nghĩa rằng chúng áp dụng cùng một thứ tự không? |

Không dùng `comparator.equals(otherComparator)` để so sánh hai giá trị dữ liệu. Đa số comparator được tạo bằng lambda hoặc factory không cung cấp phép so sánh comparator-object có ý nghĩa nghiệp vụ.

## 2. Hợp đồng mà comparator phải tuân thủ

Một comparator hợp lệ phải duy trì các quy tắc nhất quán sau:

1. **Đối xứng về dấu:** nếu `compare(a, b)` dương thì `compare(b, a)` phải âm, và ngược lại. Nếu một phía bằng 0 thì phía kia cũng phải bằng 0.
2. **Bắc cầu:** nếu `a` đứng trước `b` và `b` đứng trước `c`, thì `a` phải đứng trước `c`.
3. **Nhất quán với phần tử tương đương:** nếu `compare(a, b) == 0`, thì `a` và `b` phải có cùng quan hệ so sánh với mọi `c`.
4. **Tính xác định:** với cùng trạng thái đầu vào, comparator phải trả về quan hệ nhất quán. Không phụ thuộc vào thời gian hiện tại, số lần gọi, random hoặc mutable state thay đổi trong lúc sắp xếp.

Comparator không bắt buộc phải nhất quán với `equals`, nhưng Javadoc khuyến nghị điều đó khi phù hợp với mô hình dữ liệu. Nếu không nhất quán, phải hiểu tác động khi dùng trong sorted collections.

### Tránh phép trừ để so sánh số

Không viết:

```java
Comparator<Integer> unsafe = (a, b) -> a - b;
```

Phép trừ có thể overflow, ví dụ khi so sánh số nguyên rất lớn với số âm. Dùng factory hoặc phương thức compare:

```java
Comparator<Integer> safe = Integer::compare;
Comparator<Long> byLong = Long::compare;
record Sequenced(long sequence) {}
Comparator<Sequenced> bySequence = Comparator.comparingLong(Sequenced::sequence);
```

`Integer.compare`, `Long.compare` và các factory `comparingInt`/`comparingLong` biểu diễn đúng thứ tự mà không phụ thuộc phép trừ có thể tràn.

## 3. Null của object và null của khóa là hai trường hợp khác nhau

`Comparator.nullsFirst(c)` và `Comparator.nullsLast(c)` tạo comparator xử lý trường hợp **đối tượng được so sánh** là null:

```java
Comparator<String> FIRST = Comparator.nullsFirst(Comparator.naturalOrder());
Comparator<String> LAST  = Comparator.nullsLast(Comparator.naturalOrder());
```

- Với `FIRST`, null đứng trước mọi chuỗi không null.
- Với `LAST`, null đứng sau mọi chuỗi không null.
- Hai giá trị null so với nhau cho kết quả 0.
- Khi cả hai giá trị không null, comparator được truyền vào quyết định thứ tự.

Ví dụ:

```java
List<String> names = new ArrayList<>(Arrays.asList("Linh", null, "An"));
names.sort(Comparator.nullsLast(Comparator.naturalOrder()));
// [An, Linh, null]
```

### Null của trường timestamp

Giả sử event luôn tồn tại nhưng `occurredAt` có thể null vì dữ liệu thời gian chưa được đồng bộ. Khi đó, comparator cần xử lý khóa null:

```java
Comparator<Instant> INSTANT_NULLS_LAST =
        Comparator.nullsLast(Comparator.naturalOrder());

Comparator<Event> BY_TIME =
        Comparator.comparing(Event::occurredAt, INSTANT_NULLS_LAST);
```

Comparator này xử lý `occurredAt == null`, nhưng **không** xử lý `event == null`. Nếu chính phần tử event có thể null, cần bọc thêm comparator ở ngoài:

```java
Comparator<Event> NULL_EVENT_FIRST =
        Comparator.nullsFirst(BY_TIME);
```

Đây là hai lớp khác nhau:

| Đầu vào | Comparator cần xử lý |
|---|---|
| `event == null` | Comparator bao ngoài `Comparator.nullsFirst(...)` hoặc `nullsLast(...)`. |
| `event != null` nhưng `event.occurredAt() == null` | Comparator của khóa thời gian bên trong `Comparator.comparing(...)`. |
| Event và timestamp đều khác null | Comparator của kiểu khóa, ví dụ `Comparator.naturalOrder()`. |

Nếu domain không cho phép event null, nên từ chối null tại ranh giới nhận dữ liệu thay vì lặng lẽ xếp nó vào đầu hoặc cuối. Null policy phải xuất phát từ ý nghĩa dữ liệu, không chỉ để làm comparator tránh exception.

### Không dùng `nullsFirst(null)` một cách vô ý

Javadoc có một trường hợp đặc biệt: nếu comparator truyền vào `null`, comparator trả về bởi `nullsFirst(null)` hoặc `nullsLast(null)` xem **mọi giá trị không null là tương đương với nhau**. Nó chỉ phân biệt null với non-null:

```java
Comparator<String> nullOnly = Comparator.nullsFirst(null);

nullOnly.compare(null, "A");   // số âm
nullOnly.compare("A", null);   // số dương
nullOnly.compare("A", "Z");   // 0: tất cả non-null được xem là bằng nhau
```

Điều này hiếm khi là thứ tự mong muốn cho tên hoặc định danh. Nếu muốn sắp xếp non-null theo thứ tự tự nhiên, luôn truyền `Comparator.naturalOrder()` hoặc comparator nghiệp vụ rõ ràng.

## 4. Thứ tự null khi đảo comparator

`reversed()` đảo toàn bộ thứ tự, bao gồm vị trí của null. Vì thế, hai biểu thức dưới đây không tương đương:

```java
Comparator<Instant> ascendingNullLast =
        Comparator.nullsLast(Comparator.naturalOrder());

Comparator<Instant> descendingNullFirst = ascendingNullLast.reversed();

Comparator<Instant> descendingNullLast =
        Comparator.nullsLast(Comparator.reverseOrder());
```

| Comparator | Thời gian khác null | Timestamp null |
|---|---|---|
| `nullsLast(naturalOrder())` | Tăng dần | Cuối danh sách |
| `nullsLast(naturalOrder()).reversed()` | Giảm dần | Đầu danh sách |
| `nullsLast(reverseOrder())` | Giảm dần | Cuối danh sách |

Nếu yêu cầu nghiệp vụ là “mới nhất trước, thời gian chưa biết vẫn ở cuối”, hãy dùng `nullsLast(reverseOrder())`. Đừng đảo comparator đã có null policy rồi mới giả định null vẫn ở cuối.

## 5. Thứ tự thời gian: dùng đúng kiểu cho đúng quy tắc

Thời gian có nhiều biểu diễn với ngữ nghĩa khác nhau:

| Kiểu | Ý nghĩa | Dùng khi |
|---|---|---|
| `Instant` | Một thời điểm trên timeline UTC. | So sánh thứ tự xảy ra thực tế giữa các hệ thống/múi giờ. |
| `OffsetDateTime` | Ngày giờ cùng UTC offset. | Cần giữ offset đã nhận, đồng thời có thể chuẩn hóa sang `Instant` để so thời điểm. |
| `ZonedDateTime` | Ngày giờ theo vùng thời gian và quy tắc timezone. | Cần giữ zone như `Europe/Paris` hoặc `Asia/Ho_Chi_Minh`. |
| `LocalDateTime` | Ngày giờ trên đồng hồ địa phương, không có offset/zone. | Lịch hẹn hoặc giờ nghiệp vụ mà zone được xác định ở ngữ cảnh khác. |
| `LocalDate` | Ngày lịch, không có giờ và zone. | Ngày sinh, ngày hiệu lực, ngày kế toán. |

Nếu cần sắp xếp sự kiện xảy ra thực tế trên cùng timeline, ưu tiên `Instant` hoặc chuẩn hóa `OffsetDateTime`/`ZonedDateTime` sang `Instant`. Hai `LocalDateTime` giống nhau ở hai vùng khác nhau không nhất thiết là cùng một thời điểm. Không tự gán timezone mặc định của máy để biến một local date-time thành instant nếu domain chưa xác định zone.

### Kiểm thử hai offset biểu diễn cùng một instant

```java
Instant utc = Instant.parse("2026-11-27T10:00:00Z");
OffsetDateTime hcm = OffsetDateTime.parse("2026-11-27T17:00:00+07:00");

assertEquals(utc, hcm.toInstant());
assertEquals(0, Comparator.comparing(OffsetDateTime::toInstant)
        .compare(OffsetDateTime.ofInstant(utc, ZoneOffset.UTC), hcm));
```

Khi domain so sánh thời điểm thực, không so sánh chuỗi hiển thị hoặc local date-time chưa có zone. Khi domain so sánh giờ mở cửa “09:00 tại chi nhánh”, `LocalTime` hoặc `LocalDateTime` có thể đúng hơn; cần dùng zone của chi nhánh khi chuyển sang timeline.

### Độ chính xác thời gian và nguồn dữ liệu

`Instant` có độ phân giải nano giây, nhưng database, message broker hoặc hệ thống nguồn có thể chỉ lưu microsecond hoặc millisecond. Nếu domain coi hai timestamp đã được làm tròn về cùng độ chính xác là cùng thời điểm, hãy chuẩn hóa ở biên dữ liệu trước khi so sánh. Đừng âm thầm truncate trong comparator nếu những nơi khác vẫn dùng timestamp đầy đủ; khi đó equality, thứ tự và truy vấn database có thể không thống nhất.

## 6. Định danh là tie-breaker, không tự động là thời gian

Khi nhiều sự kiện có cùng timestamp, thêm một định danh ổn định làm tie-breaker giúp kết quả sắp xếp xác định:

```java
Comparator<Event> BY_TIME_THEN_ID =
        Comparator.comparing(Event::occurredAt,
                Comparator.nullsLast(Comparator.naturalOrder()))
                  .thenComparing(Event::id);
```

`UUID` có thể dùng làm khóa tie-breaker nếu domain cần thứ tự xác định. Tuy nhiên, thứ tự tự nhiên của UUID là thứ tự so sánh giá trị UUID, không phải cam kết về thời điểm tạo. Nếu nghiệp vụ cần thứ tự phát sinh, hãy dùng sequence/time field được định nghĩa rõ ràng thay vì suy ra chronology từ UUID.

Định danh dạng chuỗi cũng cần quy tắc rõ:

- Nếu ID phân biệt hoa/thường, dùng thứ tự phân biệt hoa/thường và kiểm thử `ABC` khác `abc`.
- Nếu ID không phân biệt hoa/thường theo domain, dùng comparator/canonicalization đúng quy tắc đó; đừng tự gọi `toLowerCase()` theo locale mặc định của máy.
- Nếu database dùng collation riêng, kiểm tra thứ tự Java có cần khớp collation database hay không. Thứ tự Java và thứ tự SQL có thể khác nhau.

### Ví dụ domain event

```java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

record Event(UUID id, Instant occurredAt, String description) {
    Event {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(description, "description");
        // occurredAt có thể null: domain định nghĩa là chưa rõ thời điểm.
    }
}
```

Quy tắc của ví dụ:

1. Sự kiện có thời điểm xác định đứng trước sự kiện chưa rõ thời điểm.
2. Thời điểm tăng dần.
3. Nếu thời điểm bằng nhau, UUID quyết định thứ tự ổn định.
4. ID bắt buộc khác null; description không tham gia thứ tự.

```java
static final Comparator<Instant> TIME_NULLS_LAST =
        Comparator.nullsLast(Comparator.naturalOrder());

static final Comparator<Event> EVENT_ORDER =
        Comparator.comparing(Event::occurredAt, TIME_NULLS_LAST)
                  .thenComparing(Event::id);
```

Nếu hai event có cùng timestamp và cùng ID nhưng description khác nhau, `EVENT_ORDER.compare(a, b)` trả về 0 trong khi record `equals` trả về false. Đây là lựa chọn có chủ ý nếu ID là identity nghiệp vụ và description chỉ là thuộc tính không tham gia thứ tự. Nếu hai record đó cần được giữ riêng trong `TreeSet`, phải mở rộng comparator bằng một tie-breaker nữa hoặc dùng collection phù hợp với equality mong muốn.

## 7. Kiểm thử giá trị bằng nhau và consistency với equals

Có hai kiểu comparator test thường cần:

- **Test quy tắc thứ tự:** xác nhận giá trị nào đứng trước/sau, null ở đâu và tie-breaker hoạt động.
- **Test consistency với equals:** xác nhận `compare(a, b) == 0` có tương ứng với `a.equals(b)` hay không, nếu domain/collection yêu cầu điều đó.

Ví dụ JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Instant;
import java.util.Comparator;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class EventOrderTest {
    private static final Comparator<Instant> TIME_NULLS_LAST =
            Comparator.nullsLast(Comparator.naturalOrder());

    private static final Comparator<Event> ORDER =
            Comparator.comparing(Event::occurredAt, TIME_NULLS_LAST)
                      .thenComparing(Event::id);

    @Test
    void sameTimestampUsesIdAsTieBreaker() {
        Instant time = Instant.parse("2026-11-27T10:00:00Z");
        Event first = new Event(id(1), time, "first");
        Event second = new Event(id(2), time, "second");

        assertTrue(ORDER.compare(first, second) < 0);
        assertTrue(ORDER.compare(second, first) > 0);
    }

    @Test
    void unknownTimestampIsAfterKnownTimestamp() {
        Event known = new Event(id(1), Instant.parse("2026-11-27T10:00:00Z"), "known");
        Event unknown = new Event(id(2), null, "unknown");

        assertTrue(ORDER.compare(known, unknown) < 0);
        assertTrue(ORDER.compare(unknown, known) > 0);
    }

    @Test
    void sameTimeAndIdAreEquivalentInOrdering() {
        Instant time = Instant.parse("2026-11-27T10:00:00Z");
        Event a = new Event(id(1), time, "old description");
        Event b = new Event(id(1), time, "new description");

        assertEquals(0, ORDER.compare(a, b));
        assertNotEquals(a, b); // Record equality còn xét description.
    }

    @Test
    void naturalOrderRejectsNullButNullsLastAcceptsIt() {
        Comparator<Instant> natural = Comparator.naturalOrder();
        assertThrows(NullPointerException.class, () -> natural.compare(null, null));

        Comparator<Instant> nullable = Comparator.nullsLast(natural);
        assertEquals(0, nullable.compare(null, null));
        assertTrue(nullable.compare(Instant.EPOCH, null) < 0);
    }

    private static UUID id(long lowBits) {
        return new UUID(0L, lowBits);
    }
}
```

Test `sameTimeAndIdAreEquivalentInOrdering` không phải lỗi nếu domain quy định ID là identity và description không tham gia thứ tự. Nhưng nếu collection được dùng để lưu mọi phiên bản description, comparator hiện tại có thể làm mất phần tử trong `TreeSet`. Điều cần kiểm thử là quyết định nghiệp vụ đã được thể hiện đúng, không phải ép mọi comparator phải nhất quán với record equality.

## 8. Kiểm thử hợp đồng comparator bằng các cặp và bộ ba

Một vài ví dụ đầu vào không đủ phát hiện comparator vi phạm bắc cầu hoặc consistency. Với tập dữ liệu kiểm thử hữu hạn, có thể duyệt mọi cặp và bộ ba để kiểm tra hợp đồng:

```java
static <T> void assertComparatorContract(
        Comparator<? super T> comparator,
        List<T> values) {

    for (T a : values) {
        assertEquals(0, Integer.signum(comparator.compare(a, a)),
                "compare(x, x) phải bằng 0");

        for (T b : values) {
            int ab = Integer.signum(comparator.compare(a, b));
            int ba = Integer.signum(comparator.compare(b, a));

            assertEquals(-ab, ba, "Tính đối xứng về dấu bị vi phạm");

            for (T c : values) {
                int bc = Integer.signum(comparator.compare(b, c));
                int ac = Integer.signum(comparator.compare(a, c));

                if (ab > 0 && bc > 0) {
                    assertTrue(ac > 0, "Tính bắc cầu bị vi phạm");
                }

                if (ab == 0) {
                    assertEquals(bc, ac,
                            "Các giá trị tương đương phải so sánh giống nhau với phần tử thứ ba");
                }
            }
        }
    }
}
```

Hàm kiểm tra có độ phức tạp `O(n^3)`, phù hợp với bộ dữ liệu kiểm thử nhỏ, không dùng trong production. Có thể tạo tập dữ liệu gồm timestamp tăng/giảm, timestamp trùng, null, ID đầu/cuối và các giá trị biên. Nếu comparator phụ thuộc vào mutable state hoặc môi trường, hãy cố định các yếu tố đó trong test để kết quả có thể lặp lại.

### Bộ dữ liệu cần có

- Hai phần tử hoàn toàn giống nhau.
- Hai phần tử có cùng sort key nhưng khác thuộc tính không tham gia comparator.
- Hai phần tử cùng timestamp nhưng ID khác nhau.
- Timestamp null và timestamp khác null.
- Hai timestamp biểu diễn cùng instant qua offset khác nhau.
- Giá trị thời gian ở hai đầu miền ứng dụng.
- ID null nếu domain cho phép; nếu không, test constructor từ chối null.
- Giá trị số lớn/nhỏ để phát hiện comparator dùng phép trừ bị overflow.

Không chỉ test thứ tự tăng dần. Hãy test `reversed()` hoặc comparator giảm dần riêng nếu ứng dụng thực sự cung cấp chức năng đó, nhất là khi null phải giữ ở đầu/cuối theo một chính sách cố định.

## 9. Tác động của compare bằng 0 trong TreeSet và TreeMap

Sorted collections dùng comparator để xác định hai key có cùng vị trí trong thứ tự. Nếu `compare(a, b) == 0`, `TreeSet` coi phần tử mới đã có trong set; `TreeMap` coi key mới là key tương đương với key hiện có và cập nhật mapping của key đó. Javadoc của `TreeSet` và `TreeMap` khuyến nghị thứ tự phải consistent with `equals` nếu muốn các collection này tuân thủ đầy đủ hợp đồng `Set`/`Map`; khi comparator không nhất quán với `equals`, hành vi theo thứ tự vẫn được định nghĩa nhưng có thể khác kỳ vọng của code sử dụng collection theo hợp đồng tổng quát.

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);

Set<String> values = new TreeSet<>(byLength);
values.add("cat");
boolean added = values.add("dog");

// added == false: cùng độ dài nên comparator trả 0.
// TreeSet chỉ giữ một phần tử trong lớp tương đương này.
```

Nếu mục tiêu là giữ mọi chuỗi khác nhau, dùng `HashSet` theo `equals` hoặc comparator có thêm tie-breaker:

```java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
```

Với `Event`, nếu `TreeSet` cần giữ hai event cùng timestamp và ID nhưng khác description, phải thêm description vào comparator hoặc xác định lại identity. Nếu ID là khóa duy nhất và hai event cùng ID phải được xem là cùng entity, việc `TreeSet` chỉ giữ một phần tử có thể đúng; cần test rằng dữ liệu trùng ID được xử lý theo quy tắc đó.

Đừng dùng `TreeSet` như một cách deduplicate tùy tiện nếu comparator chỉ sắp xếp theo một vài thuộc tính. Comparator không tự biết toàn bộ equality nghiệp vụ.

## 10. Quy tắc miền cho định danh và số có biểu diễn khác nhau

Comparator cần phản ánh semantics của domain, không chỉ kiểu Java.

### Định danh phân biệt hoa/thường

```java
Comparator<String> caseSensitiveId = Comparator.naturalOrder();
Comparator<String> caseInsensitiveId = String.CASE_INSENSITIVE_ORDER;
```

Hai comparator này tạo kết quả khác nhau với `"UserA"` và `"usera"`. Nếu hệ thống định danh phân biệt hoa/thường, dùng comparator không phân biệt hoa/thường sẽ gộp hai ID thành một lớp tương đương. Nếu hệ thống không phân biệt, hãy canonicalize theo quy tắc đã thống nhất ở biên nhập liệu và dùng cùng quy tắc ở database, cache và application.

Không dùng `String.toLowerCase()` không tham số để chuẩn hóa identifier: kết quả phụ thuộc default locale của JVM. Nếu domain thực sự yêu cầu chuyển chữ theo quy tắc locale-independent, dùng `toLowerCase(Locale.ROOT)` như một bước canonicalization được định nghĩa rõ; với collation ngôn ngữ tự nhiên, cân nhắc `Collator` và cấu hình locale cụ thể.

### `BigDecimal`: giá trị số và biểu diễn scale

`BigDecimal.compareTo` so sánh giá trị số, còn `BigDecimal.equals` xét cả giá trị lẫn scale:

```java
BigDecimal onePointZero = new BigDecimal("1.0");
BigDecimal onePointZeroZero = new BigDecimal("1.00");

assertEquals(0, onePointZero.compareTo(onePointZeroZero));
assertNotEquals(onePointZero, onePointZeroZero);
```

Nếu domain tiền tệ coi `1.0` và `1.00` là cùng giá trị, comparator theo `BigDecimal.compareTo` phù hợp với numeric equality. Nhưng `TreeSet<BigDecimal>` sẽ chỉ giữ một trong hai biểu diễn. Nếu scale có ý nghĩa nghiệp vụ hoặc cần giữ nguyên số chữ số thập phân nhập vào, không dùng comparator numeric làm identity duy nhất.

## 11. Kiểm thử comparator trong luồng sắp xếp thực tế

Sau khi kiểm tra hợp đồng, kiểm thử đầu ra của thao tác mà ứng dụng sử dụng:

```java
List<Event> events = new ArrayList<>(List.of(
        new Event(id(3), Instant.parse("2026-11-27T10:00:00Z"), "third"),
        new Event(id(1), Instant.parse("2026-11-27T09:00:00Z"), "first"),
        new Event(id(2), Instant.parse("2026-11-27T10:00:00Z"), "second")
));
events.add(new Event(id(4), null, "unknown time"));

events.sort(EVENT_ORDER);

assertEquals(List.of(id(1), id(2), id(3), id(4)),
        events.stream().map(Event::id).toList());
```

Test này xác nhận thời gian tăng dần, tie-breaker ID cho timestamp trùng và null timestamp nằm cuối. Nó không thay thế test hợp đồng cặp/bộ ba; hai lớp test tìm các loại lỗi khác nhau.

Nếu chỉ cần sắp xếp một list và giữ các phần tử tương đương, `List.sort` có tính ổn định: các phần tử compare bằng 0 giữ thứ tự tương đối ban đầu. Tuy nhiên, nếu đầu vào là collection không có encounter order xác định, stable sort không tạo ra thứ tự xác định cho các phần tử hòa. Muốn kết quả tái lập giữa các lần chạy, thêm tie-breaker đầy đủ.

## 12. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ `compare(a,b)==0` luôn tương đương `a.equals(b)` | `TreeSet` có thể bỏ phần tử mà ứng dụng muốn giữ. | Xác định equality domain và thêm tie-breaker nếu cần. |
| Dùng `Comparator.naturalOrder()` cho khóa có thể null | Có thể ném `NullPointerException`. | Chọn `nullsFirst`/`nullsLast` hoặc từ chối null tại biên. |
| Chỉ bọc comparator của timestamp nhưng không bọc event null | Method reference vẫn lỗi khi chính event là null. | Phân biệt null phần tử và null sort key. |
| Dùng `nullsFirst(null)` để sắp xếp chuỗi | Mọi giá trị non-null được xem là tương đương. | Truyền comparator thực sự, ví dụ `naturalOrder()`. |
| Đảo `nullsLast(naturalOrder())` rồi kỳ vọng null vẫn cuối | `reversed()` đưa null lên đầu. | Dùng `nullsLast(reverseOrder())` cho giảm dần nhưng null vẫn cuối. |
| Dùng `LocalDateTime` để so thời điểm giữa nhiều timezone | Hai giá trị local không xác định được thứ tự thực tế. | Dùng `Instant` hoặc chuyển offset/zoned date-time sang `Instant`. |
| Dùng UUID làm thứ tự thời gian | Thứ tự UUID không phải cam kết chronology. | Dùng timestamp/sequence theo domain; UUID chỉ làm tie-breaker ổn định. |
| So sánh số bằng phép trừ | Overflow làm sai thứ tự. | Dùng `Integer.compare`, `Long.compare`, `comparingInt` hoặc `comparingLong`. |
| Comparator đọc clock hoặc mutable state | Kết quả thay đổi giữa các lần so sánh; sort có thể lỗi hoặc không xác định. | Chụp giá trị sort key bất biến trước khi sort. |
| Dùng `TreeSet` để deduplicate theo comparator chỉ sắp xếp một trường | Các phần tử khác nhau bị gộp. | Dùng collection theo equality hoặc mở rộng comparator. |

## 13. Checklist kiểm thử theo quy tắc miền

- [ ] Đã xác định equality của domain và ý nghĩa của `compare(a, b) == 0`.
- [ ] Đã quyết định comparator có cần consistent with `equals` hay không.
- [ ] Đã quy định null ở đầu, cuối hoặc bị từ chối; đã phân biệt null object và null key.
- [ ] Đã kiểm thử `nullsFirst(null)` không bị dùng nhầm.
- [ ] Đã kiểm thử comparator giảm dần và vị trí null sau khi đảo thứ tự.
- [ ] Đã chọn `Instant`, `OffsetDateTime`, `ZonedDateTime`, `LocalDateTime` hoặc `LocalDate` đúng semantics.
- [ ] Đã xác định độ chính xác timestamp mà domain/database yêu cầu.
- [ ] Đã chọn tie-breaker ổn định cho các bản ghi có cùng thời điểm.
- [ ] Đã không giả định UUID biểu diễn thời gian tạo.
- [ ] Đã kiểm thử quy tắc hoa/thường và collation của identifier.
- [ ] Đã kiểm tra các cặp/bộ ba để phát hiện vi phạm hợp đồng comparator.
- [ ] Đã kiểm tra tác động compare bằng 0 trong `TreeSet`/`TreeMap` nếu dùng sorted collections.
- [ ] Đã dùng phép so sánh số an toàn, không trừ hai số có thể overflow.
- [ ] Comparator không phụ thuộc clock, random hoặc mutable state thay đổi khi sắp xếp.

## Tài liệu tham khảo chính thức

- [Java SE 26 — `Comparator`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html)
- [Java SE 26 — `Comparable`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Comparable.html)
- [Java SE 26 — `TreeSet`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeSet.html)
- [Java SE 26 — `TreeMap`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeMap.html)
- [Java SE 26 — `Instant`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/Instant.html)
- [Java SE 26 — `OffsetDateTime`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/OffsetDateTime.html)
- [Java SE 26 — `UUID`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/UUID.html)
- [Java SE 26 — `BigDecimal`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html)
- [JUnit 5 User Guide — Assertions](https://junit.org/junit5/docs/current/user-guide/)

*Cập nhật nội dung: 27-11-2026. Các ví dụ dùng API Java ổn định. Null policy, equality và tie-breaker phải được chọn theo quy tắc dữ liệu của ứng dụng; không có một thứ tự đúng cho mọi miền nghiệp vụ.*
