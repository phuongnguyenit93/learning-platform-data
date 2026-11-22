# Nhà máy static cho các cách tạo có tên rõ ràng trong record

## Mục tiêu

Với một `record`, **canonical constructor** được xác định từ các component trong header. Khi có nhiều cách tạo dữ liệu mang những ý nghĩa khác nhau, bạn có thể bổ sung **static factory method** để tên lời gọi diễn đạt trực tiếp mục đích: tạo từ hai mốc ngày, tạo khoảng chỉ gồm một ngày, hoặc phân tích hai chuỗi ngày chuẩn ISO. Bài này giải thích cách thiết kế các factory rõ nghĩa, giữ bất biến dữ liệu ở một nơi, phân biệt factory với constructor và kiểm chứng hành vi bằng mã Java chạy được.

Mã ví dụ dùng **JDK 17 trở lên**, chỉ có tính năng đã ổn định. Record trở thành tính năng chuẩn từ Java 16; bài không sử dụng cách bật preview trên Java 14 hay bất kỳ API legacy nào. Các quy tắc này vẫn áp dụng cho Java hiện đại.

## 1. Vì sao record vẫn cần static factory?

Xét một record mô tả **khoảng ngày bao gồm cả hai đầu**:

```java
record DateRange(java.time.LocalDate start,
                 java.time.LocalDate end) {}
```

Java tự sinh canonical constructor nhận `(LocalDate start, LocalDate end)`. Khi nhìn `new DateRange(a, b)`, người đọc thấy hai tham số, nhưng có thể chưa biết liệu `end` có được tính là một ngày thuộc khoảng không, hoặc cách tạo khoảng chỉ có một ngày có phải truyền `a` hai lần không.

Những lời gọi sau truyền đạt ý định rõ hơn:

```java
DateRange.between(start, end);       // Khoảng ngày có hai đầu.
DateRange.singleDay(day);            // Khoảng đúng một ngày.
DateRange.parseIso("2026-11-07",
                   "2026-11-10");    // Tạo từ hai chuỗi ISO.
```

Đây là các **phương thức static do lập trình viên viết**, không phải phương thức Java tự sinh cho record. Mỗi factory có thể nhận **kiểu tham số khác nhau**, cung cấp giá trị mặc định, chuẩn hóa, chuyển đổi định dạng hoặc đặt tên cho một ý nghĩa mà các constructor overload không thể diễn đạt rõ.

Điểm mấu chốt: **static factory là cửa vào có tên; canonical constructor là đường khởi tạo record**. Một factory thường gọi `new RecordType(...)` hoặc gọi một factory khác để cuối cùng khởi tạo record. Factory không làm thay đổi header, không tự thêm component, và không phải một loại constructor đặc biệt.

## 2. Khi nào dùng factory, khi nào dùng constructor?

| Nhu cầu | API gợi ý | Lý do |
| --- | --- | --- |
| Tạo trực tiếp từ đúng các component, ý nghĩa hiển nhiên | `new Point(2, 3)` | Constructor đủ rõ, không cần bao bọc vô ích |
| Tạo một khoảng gồm đúng một ngày | `DateRange.singleDay(day)` | Không bắt người gọi lặp `day` hai lần |
| Tạo từ hai ngày đã là `LocalDate` | `DateRange.between(start, end)` | Tên nói rõ ý nghĩa của cặp mốc |
| Chuyển chuỗi ngày ISO thành ngày | `DateRange.parseIso(text1, text2)` | Người đọc biết có bước phân tích văn bản |
| Tạo từ một đối tượng dữ liệu khác | `Type.from(source)` / `Type.copyOf(source)` | Tên nói rõ chuyển đổi hay sao chép |
| Tạo cấu hình mặc định có ý nghĩa nghiệp vụ | `Type.defaultSettings()` | Không dùng các tham số “bí ẩn” như `0, null, false` |
| Chỉ kiểm tra/chuẩn hóa mọi đầu vào của record | Compact canonical constructor | Tất cả đường tạo, kể cả `new`, đều được kiểm tra |

Các tên `of`, `from`, `parse`, `copyOf`, `singleDay` hay `between` là **quy ước đặt tên API**, không phải từ khóa Java và không có ngữ nghĩa đặc biệt mà compiler tự thực thi. Hãy chọn tên dựa trên hành vi thật: `parse` gợi đầu vào là văn bản có thể sai định dạng; `copyOf` gợi một bản sao/snapshot; `singleDay` gợi một quy tắc riêng. Nếu factory chỉ có một tham số là ngày và không làm gì ngoài gọi constructor cũng có thể hữu ích khi **tên cung cấp ý nghĩa mới**.

**Không nên tự động viết factory cho mọi record.** Với dữ liệu thuần đơn giản và constructor rõ nghĩa, thêm nhiều factory trùng nhau chỉ làm API khó đọc hơn.

## 3. Thiết kế đường khởi tạo: factory + canonical constructor

Khi có nhiều factory, một lỗi thiết kế thường gặp là kiểm tra đầu vào mỗi nơi một kiểu: `between` cấm khoảng ngược, `singleDay` chấp nhận `null`, `parseIso` bỏ qua ràng buộc. Để tránh việc đó, quy tắc **bắt buộc với trạng thái hợp lệ của record** nên được đặt trong canonical constructor. Các factory phụ trách **ý nghĩa và chuyển đổi đầu vào**.

Luồng xử lý:

```text
Đầu vào khác nhau
  |-- singleDay(LocalDate) -------------|
  |-- between(LocalDate, LocalDate) ----|--> new DateRange(start, end)
  |-- parseIso(String, String) ---------|         |
  |                                          canonical constructor
  |                                          kiểm tra null + start <= end
  |                                                    |
  '--------------------------------------------> record hợp lệ
```

Nếu factory nhận chuỗi, nó có thể kiểm tra null với tên tham số văn bản, chuyển chuỗi bằng `LocalDate.parse`, rồi tạo record. Nếu chuỗi sai định dạng, factory có thể để `DateTimeParseException` lan ra theo contract được công bố. Khi các mốc ngày đã chuyển được nhưng `start > end`, canonical constructor ném `IllegalArgumentException`.

### Giới hạn truy cập quan trọng của public record

Một **`public record`** có canonical constructor với mức truy cập **`public`** theo Java Language Specification; bạn **không thể** làm constructor chuẩn thành `private` rồi bắt mọi người chỉ được gọi static factory. Vì vậy:

- Static factory là một API có tên giúp diễn đạt ý định, **không phải cơ chế chặn hoàn toàn `new`** đối với public record.
- Nếu một bất biến quan trọng, hãy áp dụng nó ở canonical constructor để cả `new DateRange(...)` và các factory đều bị kiểm tra.
- Nếu API thật sự cần **kiểm soát độc quyền cách tạo đối tượng**, cần xem xét lại khả năng tiếp cận của kiểu và thiết kế API, thay vì giả định static factory của public record có thể khóa constructor chuẩn.

Record cũng là kiểu `final`; factory trả về chính kiểu record không thể bất ngờ trả về một subclass của record đó. Đừng gán cho factory những khả năng đa hình thông qua kế thừa mà record không hỗ trợ.

## 4. Chương trình đầy đủ, chạy bằng Java 17+

Tạo tệp **`NamedFactoryDemo.java`**:

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Objects;

public final class NamedFactoryDemo {
    public record DateRange(LocalDate start, LocalDate end) {
        // Public record -> public canonical constructor.
        // Invariants apply even when callers use "new" directly.
        public DateRange {
            Objects.requireNonNull(start, "start");
            Objects.requireNonNull(end, "end");

            if (start.isAfter(end)) {
                throw new IllegalArgumentException(
                        "start must be on or before end");
            }
        }

        // Explicitly names a one-day range.
        public static DateRange singleDay(LocalDate day) {
            Objects.requireNonNull(day, "day");
            return new DateRange(day, day);
        }

        // Explicitly names a range including both endpoints.
        public static DateRange between(LocalDate first, LocalDate last) {
            return new DateRange(first, last);
        }

        // Converts ISO-8601 yyyy-MM-dd strings to LocalDate first.
        public static DateRange parseIso(String first, String last) {
            Objects.requireNonNull(first, "first");
            Objects.requireNonNull(last, "last");

            LocalDate startDate = LocalDate.parse(first);
            LocalDate endDate = LocalDate.parse(last);
            return between(startDate, endDate);
        }

        public boolean contains(LocalDate day) {
            Objects.requireNonNull(day, "day");
            return !day.isBefore(start) && !day.isAfter(end);
        }
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        DateRange one = DateRange.singleDay(
                LocalDate.of(2026, 11, 7));
        DateRange period = DateRange.parseIso(
                "2026-11-07", "2026-11-10");

        DateRange direct = new DateRange(
                LocalDate.of(2026, 11, 7),
                LocalDate.of(2026, 11, 10));

        check(one.start().equals(one.end()), "single-day range");
        check(period.equals(direct), "same value");
        check(period.contains(LocalDate.of(2026, 11, 9)), "inside");
        check(!period.contains(LocalDate.of(2026, 11, 11)), "outside");

        System.out.println("single = " + one);
        System.out.println("period = " + period);
        System.out.println("same value = " + period.equals(direct));
        System.out.println("contains 2026-11-09 = "
                + period.contains(LocalDate.of(2026, 11, 9)));
        System.out.println("contains 2026-11-11 = "
                + period.contains(LocalDate.of(2026, 11, 11)));

        try {
            DateRange.between(
                    LocalDate.of(2026, 11, 10),
                    LocalDate.of(2026, 11, 7));
            throw new AssertionError("Inverted range must fail");
        } catch (IllegalArgumentException ex) {
            System.out.println("inverted = " + ex.getMessage());
        }

        try {
            DateRange.parseIso("2026-13-01", "2026-11-10");
            throw new AssertionError("Invalid ISO date must fail");
        } catch (DateTimeParseException ex) {
            System.out.println("bad date = "
                    + ex.getClass().getSimpleName());
        }

        try {
            new DateRange(null, LocalDate.of(2026, 11, 10));
            throw new AssertionError("Null start must fail");
        } catch (NullPointerException ex) {
            System.out.println("null start = " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp với **JDK 17 trở lên**:

```bash
javac --release 17 NamedFactoryDemo.java
java NamedFactoryDemo
```

**Stdout mong đợi chính xác:**

```text
single = DateRange[start=2026-11-07, end=2026-11-07]
period = DateRange[start=2026-11-07, end=2026-11-10]
same value = true
contains 2026-11-09 = true
contains 2026-11-11 = false
inverted = start must be on or before end
bad date = DateTimeParseException
null start = start
```

### Giải thích từng đường tạo

1. `singleDay(day)` thực hiện ý định “một ngày” bằng cách truyền cùng giá trị hai lần đến canonical constructor. Không yêu cầu người gọi nhớ dùng `new DateRange(day, day)`. Factory kiểm tra `day` để thông báo tham số nguồn rõ ràng; constructor vẫn kiểm tra `start` và `end` để bảo vệ mọi đường khác.
2. `between(first, last)` nhận trực tiếp hai `LocalDate`, rồi gọi canonical constructor. Hàm có tên rõ và giữ cùng ràng buộc khoảng ngày hợp lệ.
3. `parseIso(first, last)` chấp nhận hai chuỗi ISO, phân tích bằng `LocalDate.parse` rồi ủy quyền qua `between`. Chuỗi `"2026-13-01"` có tháng không hợp lệ nên ném `DateTimeParseException`, khác lỗi thứ tự mốc ngày.
4. Lời gọi `new DateRange(...)` trong chương trình **vẫn hợp lệ**. Giá trị của nó bằng record tạo qua factory `parseIso` bởi hai component `LocalDate` bằng nhau; `record` cung cấp `equals` dựa trên các component.
5. Ca đảo mốc ngày bị chặn bởi **compact canonical constructor**, dù người gọi đang thông qua `between`. Ca `new DateRange(null, ...)` cho thấy không thể bỏ qua kiểm tra bằng cách gọi `new` trực tiếp.
6. `contains` dùng phép so sánh gồm cả hai đầu. Đây là một **quy tắc nghiệp vụ của ví dụ** và cần được mô tả rõ trong API; không phải tất cả date range trong mọi hệ thống đều inclusive.

Lệnh `check` ném `AssertionError` nếu hành vi đúng như contract không còn được giữ. Chương trình kết hợp quan sát stdout với kiểm chứng tự động để không chỉ dựa vào việc nhìn thấy chuỗi được in ra.

## 5. Đặt tên factory để tránh mơ hồ

Không có một bộ từ khóa tên factory bắt buộc trong Java. Tuy nhiên, cách đặt tên thường nhất quán theo **loại biến đổi**:

| Tên gợi ý | Ý nghĩa nên truyền đạt | Điều cần làm rõ trong tài liệu |
| --- | --- | --- |
| `of(...)` | Tạo từ các giá trị đã ở gần cấu trúc đích | Kiểm tra nào được áp dụng, tham số nào tương ứng component |
| `from(...)` | Tạo từ một đối tượng hoặc biểu diễn khác | Có chuyển đổi dữ liệu, sao chép hoặc chuẩn hóa không |
| `parse(...)` / `parseIso(...)` | Chuyển văn bản thành giá trị | Định dạng chấp nhận, locale/zone nếu có, ngoại lệ khi sai cú pháp |
| `copyOf(...)` | Tạo giá trị từ collection hay nguồn có thể thay đổi | Snapshot ở mức nào, có bất biến sâu không |
| `singleDay(day)` | Một cách tạo có ý nghĩa nghiệp vụ riêng | Có bao gồm toàn bộ ngày đó không |
| `between(start, end)` | Tạo khoảng từ hai biên | `end` inclusive hay exclusive; xử lý khi `start > end` |
| `empty()` | Tạo giá trị rỗng theo contract | “Rỗng” hợp lệ hay vi phạm bất biến |
| `defaultXxx()` | Tạo giá trị mặc định có ý nghĩa | Mặc định cố định hay phụ thuộc cấu hình |

**Không dùng tên che giấu hành vi.** Nếu factory gọi `LocalDate.parse`, tên `parseIso` rõ hơn một tên chung như `create`, nhất là khi record có cả đầu vào `String` và `LocalDate`. Nếu tính “gồm cả hai đầu” quan trọng, mô tả rõ trong Javadoc hoặc đặt tên còn cụ thể hơn theo chuẩn nội bộ. Với ngày tháng, tránh phương thức âm thầm phụ thuộc múi giờ hiện tại hoặc locale máy nếu đó không phải một phần contract.

Một factory có thể tự ném ngoại lệ đối với **đầu vào dạng nguồn** (ví dụ chuỗi sai định dạng); canonical constructor giữ **bất biến đối tượng sau chuyển đổi** (ví dụ ngày bắt đầu không được sau ngày kết thúc). Sự phân công này giúp lỗi dễ chẩn đoán và các overload không vận hành mỗi nơi một khác.

### `Optional` và factory kiểu `tryParse`

Một số API muốn coi văn bản người dùng nhập sai là tình huống bình thường. Khi đó có thể thiết kế `Optional<DateRange> tryParseIso(String, String)`. Tuy nhiên, **chỉ nên trả `Optional.empty()` cho những lỗi được contract quy định là “không phân tích được”**; không bắt `RuntimeException` chung rồi giấu cả bug lập trình, lỗi null hoặc vi phạm logic khác.

Trong bài này, `parseIso` chủ động **ném ngoại lệ có loại rõ ràng**, phù hợp khi input sai cần được báo ngay. Bạn nên chọn một contract cụ thể rồi kiểm chứng các đường sai dữ liệu; không nhất thiết cung cấp cả `parse` và `tryParse` khi API không có nhu cầu.

## 6. Static factory với collection: cần lưu ý về bất biến nông

Một use case phổ biến là record có component kiểu `List`. Canonical constructor của record sẽ lưu **tham chiếu** truyền vào nếu bạn không tự xử lý; field `final` không ngăn collection bên trong bị sửa. Một factory tên `copyOf` có thể diễn đạt việc tạo snapshot, nhưng bất biến phải được giữ ngay cả khi người gọi dùng constructor trực tiếp.

Đoạn sau là **mã minh họa độc lập ở mức khai báo record**, chưa có method `main`:

```java
import java.util.List;

public record Tags(List<String> values) {
    public Tags {
        values = List.copyOf(values);
    }

    public static Tags empty() {
        return new Tags(List.of());
    }

    public static Tags copyOf(List<String> source) {
        return new Tags(source);
    }
}
```

Ý nghĩa:

- `Tags.copyOf(list)` có tên thể hiện nguồn dữ liệu là danh sách; canonical constructor dùng `List.copyOf` để lưu một danh sách không thể sửa cấu trúc. Đây là **snapshot về tập phần tử tại thời điểm tạo**.
- `new Tags(list)` cũng đi qua canonical constructor và được bảo vệ tương tự. Không có đường vào thứ hai có thể lách kiểm tra null hoặc sao chép.
- `List.copyOf` từ chối `null` ở collection nguồn hoặc các phần tử của nó; đây là contract mà lớp phải chấp nhận hoặc diễn đạt rõ.
- Với phần tử là đối tượng có trạng thái thay đổi, `List.copyOf` **không sao chép sâu** chính các phần tử đó. Muốn bất biến sâu cần một chính sách riêng cho từng phần tử.
- `empty()` tạo bản rỗng, nhưng chỉ nên có phương thức này nếu record thực sự chấp nhận trạng thái rỗng.

Chương trình ở mục 4 dùng `LocalDate`, một kiểu bất biến, nên không có vấn đề aliasing của một collection mutable. Mục này mở rộng cách suy nghĩ khi component là dữ liệu phức tạp.

## 7. Bẫy thường gặp khi kết hợp record và static factory

### Bẫy 1: Kiểm tra bất biến chỉ tại factory

```java
record NonNegative(int value) {
    static NonNegative of(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("negative");
        }
        return new NonNegative(value);
    }
}
```

Code **biên dịch được**, nhưng `new NonNegative(-5)` vẫn tạo được record có giá trị âm, vì canonical constructor ngầm không có kiểm tra. Nếu `value >= 0` là bất biến bắt buộc, phải chuyển kiểm tra vào compact canonical constructor:

```java
record NonNegative(int value) {
    NonNegative {
        if (value < 0) {
            throw new IllegalArgumentException("negative");
        }
    }

    static NonNegative of(int value) {
        return new NonNegative(value);
    }
}
```

Đây là ví dụ sửa lỗi, vẫn là **mã minh họa kiểu record** chứ không phải chương trình có `main`. Hai khai báo cùng tên là **hai phương án thay thế**, không đặt cùng nhau trong một tệp.

### Bẫy 2: Thử ẩn canonical constructor của public record

```java
public record ProductCode(String value) {
    private ProductCode(String value) { // Compile-time error.
        this.value = value;
    }
}
```

Với `public record`, canonical constructor phải `public`. Static factory **không thay thế** quy tắc mức truy cập này. Có thể giữ canonical constructor `public` và kiểm tra mọi giá trị tại đó. Đừng ghi tài liệu rằng chỉ factory mới tạo được instance của `public record` khi người gọi vẫn có `new` hợp lệ.

### Bẫy 3: Dùng overload constructor để giả làm factory có tên

```java
record Port(int value) {
    Port() {
        this(8080);
    }
}
```

Overload `new Port()` có thể dùng để cung cấp mặc định, nhưng cú pháp này không truyền đạt mặc định ấy là gì. Nếu giá trị mặc định mang ý nghĩa như `http()` hoặc `development()`, một **factory tên cụ thể** thường dễ hiểu hơn. Ngoài ra, theo quy tắc record, một constructor **không chuẩn** phải ủy quyền qua `this(...)` đến một constructor khác để cuối cùng đi qua canonical constructor.

### Bẫy 4: Dùng cache hoặc so sánh danh tính

Factory **có thể** lựa chọn trả về một instance được tái sử dụng nếu thích hợp, nhưng không được mặc định rằng mọi factory đều cache. Record hướng tới ngữ nghĩa dữ liệu: kiểm tra bằng `equals`/`hashCode` khi quan tâm thành phần, không dùng `==` để kết luận hai record có cùng giá trị.

Trong ví dụ `DateRange`, không có cache: `period.equals(direct)` là `true` dù đây là hai instance được khởi tạo riêng. Đừng dựa vào danh tính tham chiếu để viết kiểm thử giá trị.

### Bẫy 5: Factory không diễn đạt chính xác định dạng

Tên `fromText` chưa chắc cho biết phải truyền ngày ISO, ngày theo locale hay timestamp. Dùng `parseIso` và `LocalDate.parse` khiến kỳ vọng về định dạng rõ ràng. Nếu sản phẩm yêu cầu locale hoặc timezone, đưa chúng vào contract một cách tường minh, hoặc dùng API `java.time` với formatter/zone được truyền rõ; tránh phụ thuộc cấu hình máy không kiểm soát được.

### Bẫy 6: Phép chuyển đổi làm mất dữ liệu

Factory có quyền chuyển đầu vào, nhưng không được âm thầm làm biến mất thông tin quan trọng nếu contract không quy định. Ví dụ ép kiểu số lớn về số nhỏ, làm tròn tiền tệ không có quy tắc, hoặc bỏ mọi phần tử trùng khi chuyển list thành set đều có thể thay đổi ý nghĩa dữ liệu. Hãy tách **bất biến record** khỏi **quy tắc chuyển đổi của từng factory** và kiểm thử độc lập hai phần đó.

## 8. Cách kiểm chứng đúng hành vi của từng factory

| Ca kiểm chứng | Đầu vào | Kết quả mong đợi |
| --- | --- | --- |
| Factory tạo khoảng đơn | `singleDay(2026-11-07)` | `start == end == 2026-11-07` (so sánh giá trị) |
| Factory tạo khoảng bình thường | `between(2026-11-07, 2026-11-10)` | Chứa cả hai ngày đầu và cuối |
| Factory chuyển văn bản | `parseIso("2026-11-07","2026-11-10")` | Bằng về giá trị với record tạo trực tiếp từ `LocalDate` |
| Sai thứ tự ngày | `between(2026-11-10, 2026-11-07)` | `IllegalArgumentException` từ canonical constructor |
| Sai định dạng | `parseIso("2026-13-01","2026-11-10")` | `DateTimeParseException` khi parse |
| Null component | `new DateRange(null, validEnd)` | `NullPointerException` từ canonical constructor |
| Null đầu vào văn bản | `parseIso(null, "2026-11-10")` | `NullPointerException` từ factory, theo contract |
| Bỏ qua factory | `new DateRange(later, earlier)` | Vẫn phải bị canonical constructor từ chối |
| Ranh giới bao gồm | `contains(start)` và `contains(end)` | Đều `true` |
| Ngoài khoảng | `contains(end.plusDays(1))`, khi hợp lệ | `false` |

**Bộ test tốt cần kiểm tra cả API factory và constructor** bởi người gọi public record không bị giới hạn chỉ dùng static factory. Với đầu vào có thể biến đổi, kiểm tra thêm hành vi phòng vệ sau khi nguồn bị sửa.

Đừng dùng `equals` trên định dạng văn bản để thay cho kiểm tra nghiệp vụ khi cần xác nhận thành phần cụ thể. Record tự cung cấp `equals` theo component, nhưng phép so sánh giá trị chỉ đúng theo ngữ nghĩa của **kiểu component**: nếu component chứa array thì `equals` của array là so sánh tham chiếu; nếu chứa `BigDecimal` thì `equals` còn xét scale; nếu chứa collection mutable thì giá trị có thể đổi sau khi tạo nếu không sao chép phòng vệ.

## 9. Bài tự luyện: factory đặt tên cho cách khởi tạo

Thiết kế `record TimeSlot(LocalTime start, LocalTime end)` với quy tắc **start phải trước end trong cùng ngày** và cả hai mốc không `null`. Xây dựng:

1. Canonical constructor (ưu tiên compact) từ chối `start >= end`.
2. `TimeSlot.between(LocalTime start, LocalTime end)` để diễn đạt khoảng giờ thông thường.
3. `TimeSlot.morning()` trả khoảng `09:00` đến `12:00`.
4. `TimeSlot.parseIso(String start, String end)` nhận chuỗi định dạng ISO như `"09:00"` và `"12:00"`, chuyển bằng `LocalTime.parse` rồi qua constructor chuẩn.
5. Một phương thức `contains(LocalTime time)` có contract **start inclusive, end exclusive**. Hãy ghi rõ vì sao quy tắc này khác `DateRange` ở mục 4.

Kiểm tra `morning()`, `between(09:00, 12:00)`, `parseIso("09:00", "12:00")` cho cùng dữ liệu; kiểm tra `start == end`, `start > end`, chuỗi thời gian sai và `null`. Đồng thời thử `new TimeSlot(...)` với dữ liệu không hợp lệ để chứng minh kiểm tra không chỉ nằm ở factory.

Một lời giải tốt sẽ khiến mỗi lời gọi có **mục đích đọc được từ tên**, mỗi đầu vào lỗi có hành vi được mô tả rõ, và dù chọn đường tạo nào thì record cũng giữ một bộ bất biến nhất quán.

## Tài liệu tham khảo

- [Java Language Specification (Java SE 26), `8.10: Record Classes và `8.10.4: Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-8.html#jls-8.10.4): quy tắc canonical constructor, mức truy cập và constructor overload.
- [Oracle Java SE 17 — Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): mô hình record và compact constructor.
- [Java SE 17 API — LocalDate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDate.html): phân tích ISO date và so sánh ngày.

**Kết luận áp dụng:** Static factory đặt tên cho **cách tạo** và có thể chuyển đổi đầu vào; canonical constructor xác lập **đối tượng hợp lệ**. Khi record được dùng như kiểu dữ liệu công khai, tên factory giúp API dễ đọc, còn validation trong canonical constructor giữ quy tắc đúng cho cả factory lẫn `new`.