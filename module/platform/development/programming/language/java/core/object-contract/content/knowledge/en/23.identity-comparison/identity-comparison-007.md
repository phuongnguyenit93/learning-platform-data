# Đối tượng value-based và lý do không dựa vào danh tính thể hiện trong Java

Trong Java, hai biến tham chiếu có thể chỉ tới **hai đối tượng khác nhau** nhưng mô tả **cùng một giá trị**. Với các lớp *value-based* (lớp dựa trên giá trị), sự khác biệt về đối tượng nào được cấp phát, tái sử dụng hay chia sẻ không phải là điều chương trình nên dựa vào. Điều quan trọng là **giá trị theo hợp đồng của lớp**.

Bài này nằm trong chủ đề **so sánh theo danh tính** của Java Core: nhận diện khi nào phải dùng so sánh theo giá trị và vì sao những phép kiểm tra dựa vào danh tính có thể làm hỏng logic, khóa đồng bộ, hoặc cấu trúc dữ liệu.

## 1. Phân biệt danh tính tham chiếu và tính bằng nhau về giá trị

Xét hai tham chiếu kiểu đối tượng:

- `a == b`, nếu cả hai toán hạng đều là **tham chiếu**, hỏi liệu chúng có trỏ tới **cùng một đối tượng** ở thời điểm đó không. Đây là so sánh theo danh tính (*reference identity*).
- `a.equals(b)` hỏi liệu chúng có **bằng nhau theo hợp đồng `equals`** của lớp không. Với value-based class, hợp đồng này dựa vào giá trị.
- `Objects.equals(a, b)` thực hiện so sánh theo `equals` có xử lý `null`: cả hai `null` thì `true`, một bên `null` thì `false`.
- `System.identityHashCode(a)` cung cấp mã băm liên quan đến danh tính tham chiếu, **không** thay thế cho `a.hashCode()` khi cần nhận diện một giá trị.

Ví dụ, ngày 23/10/2026 là **một giá trị lịch**. Hai lời gọi `LocalDate.of(2026, 10, 23)` mô tả cùng ngày, dù cách JVM thể hiện và quản lý các đối tượng trả về có thể khác nhau. Do đó, câu hỏi nghiệp vụ là *có cùng ngày không?*; kiểm tra đúng là `equals`.

> Cần phân biệt: trong Java 17, nhiều thể hiện value-based vẫn là các đối tượng tham chiếu bình thường ở cấp JVM. Khái niệm *value-based* không có nghĩa mọi phép `==` đều bị cấm biên dịch hoặc lớp đó chưa từng có danh tính vật lý. Nó có nghĩa **mã ứng dụng không được lấy danh tính đó làm một phần của hợp đồng xử lý giá trị**.

## 2. Thế nào là một value-based class?

Theo tài liệu Java SE 17, lớp value-based có các đặc điểm cốt lõi:

1. Là lớp `final`, không thiết kế để kế thừa tùy ý; các trường thể hiện được khai báo `final`. Trường có thể tham chiếu tới đối tượng mutable, vì vậy phải hiểu tính bất biến theo đúng hợp đồng từng API.
2. `equals`, `hashCode` và `toString` được tính từ trạng thái giá trị thích hợp, không từ danh tính đối tượng.
3. Các phương thức của lớp xem hai thể hiện có `equals` bằng nhau là **có thể thay thế cho nhau** (*freely substitutable*) đối với hành vi được lớp bảo đảm.
4. Bản thân lớp không dùng monitor của thể hiện làm cơ chế đồng bộ.
5. Không cung cấp constructor công khai mang nghĩa “mỗi lần tạo chắc chắn được một danh tính mới”; constructor truy cập được sẽ không có hoặc đã bị đánh dấu deprecated.
6. Factory không cam kết luôn trả về đối tượng mới hay luôn trả về đối tượng cũ: với cùng giá trị, các lần tạo độc lập **có thể** nhận lại cùng tham chiếu hoặc tham chiếu khác.

Ví dụ quen thuộc trong Java 17 gồm `java.time.LocalDate`, `java.time.Instant`, `java.util.Optional` và những lớp bao kiểu nguyên thủy như `java.lang.Integer`. Luôn xem Javadoc của lớp cụ thể để xác nhận nó được tài liệu công bố là *value-based*.

**Hệ quả thiết kế:** API cho phép thay thế một thể hiện bằng thể hiện khác có cùng giá trị mà không làm thay đổi hành vi được bảo đảm. Người dùng API không nên đòi hỏi một danh tính ổn định hoặc duy nhất cho mỗi lời gọi factory.

## 3. Vì sao `==` không thể là tiêu chí về giá trị?

Giả sử:

```java
LocalDate first  = LocalDate.of(2026, 10, 23);
LocalDate second = LocalDate.of(2026, 10, 23);

// Đúng: kiểm tra cùng giá trị ngày.
boolean sameDate = first.equals(second);

// Sai về mặt hợp đồng: dựa vào cách hai tham chiếu được thể hiện.
boolean sameReference = (first == second);
```

Biến `sameDate` phù hợp với bài toán; `sameReference` chỉ là quan sát một chi tiết thể hiện. Không được suy ra rằng với value-based class, `==` *luôn* là `true` hoặc *luôn* là `false` khi hai giá trị bằng nhau.

Các lớp bao kiểu nguyên thủy cũng dễ gây ngộ nhận:

```java
Integer x = Integer.valueOf(1000);
Integer y = Integer.valueOf(1000);
boolean equalValue = x.equals(y); // true
boolean sameObject = (x == y);    // Đừng dùng để suy ra bằng nhau về số.
```

Factory có thể cache hoặc dùng lại thể hiện theo giá trị và triển khai. Quan sát `==` ở một môi trường không phải cam kết cho những môi trường hay phiên bản sau.

**Lưu ý về autoboxing:** `Integer a == Integer b` so sánh tham chiếu vì hai bên là đối tượng; `int a == int b` so sánh giá trị số; `int a == Integer b` thường unbox `b` rồi so sánh số, và có thể ném `NullPointerException` nếu `b` là `null`. Vì vậy phải xem **kiểu thực tế của hai toán hạng**, không chỉ nhìn ký hiệu `==`.

## 4. Ví dụ Java 17 chạy được: so sánh, Set và Map

Lưu đoạn sau vào tệp `ValueBasedDemo.java`:

```java
import java.time.LocalDate;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

public class ValueBasedDemo {
    public static void main(String[] args) {
        LocalDate first = LocalDate.of(2026, 10, 23);
        LocalDate second = LocalDate.of(2026, 10, 23);

        System.out.println("LocalDate.equals: " + first.equals(second));

        Set<LocalDate> days = new HashSet<>();
        days.add(first);
        days.add(second);
        System.out.println("Distinct day values: " + days.size());

        Map<LocalDate, String> descriptions = new HashMap<>();
        descriptions.put(first, "ngay hoc");
        System.out.println("Lookup with equal key: " + descriptions.get(second));

        Optional<String> one = Optional.of("Java");
        Optional<String> two = Optional.of("Java");
        System.out.println("Optional.equals: " + one.equals(two));

        Integer x = Integer.valueOf(1000);
        Integer y = Integer.valueOf(1000);
        System.out.println("Integer.equals: " + x.equals(y));

        System.out.println("Null-safe equals: " + Objects.equals(null, null));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac ValueBasedDemo.java
java ValueBasedDemo
```

Kết quả chuẩn:

```text
LocalDate.equals: true
Distinct day values: 1
Lookup with equal key: ngay hoc
Optional.equals: true
Integer.equals: true
Null-safe equals: true
```

Giải thích:

- `LocalDate.equals` kiểm tra ngày; cả hai thể hiện mô tả cùng ngày nên bằng nhau.
- `HashSet` dựa trên `equals` và `hashCode`, nên không giữ hai phần tử tương đương về giá trị ngày.
- `HashMap` tìm lại được dữ liệu bằng khóa khác tham chiếu nhưng bằng nhau theo `equals` và có `hashCode` tương ứng.
- Hai `Optional` chứa cùng chuỗi có `equals` bằng nhau; `Optional.empty()` cũng phải được kiểm tra bằng API như `isEmpty()`, không dựa vào `==`.
- `Integer.equals` biểu đạt bình đẳng của giá trị số đóng hộp. Ví dụ cố ý không in `first == second` hay `x == y` vì chúng không có kết luận giá trị hữu ích.

## 5. Những thao tác nhạy với danh tính cần tránh

| Thao tác | Vấn đề khi dùng với value-based object | Hướng thay thế |
| --- | --- | --- |
| `a == b` hoặc `a != b` để so giá trị | Thực chất kiểm tra cùng tham chiếu; factory không hứa cách cấp phát/tái sử dụng | `a.equals(b)`, `Objects.equals(a, b)` hoặc API so sánh theo miền |
| `System.identityHashCode(a)` làm khóa giá trị | Dựa vào danh tính, không theo hợp đồng giá trị | `a.hashCode()` đi cùng `equals()`; hoặc dùng trực tiếp `a` làm khóa `HashMap` |
| `IdentityHashMap<ValueType, ...>` | Map dùng `==` cho khóa nên hai giá trị tương đương không nhất thiết được coi là một khóa | `HashMap` / `ConcurrentHashMap` khi khóa là giá trị |
| `synchronized (value)`, `value.wait()`, `value.notify()` | Monitor thuộc thể hiện cụ thể, dễ bị dùng chung ngoài ý muốn hoặc thay đổi qua các phiên bản Java | Khóa riêng kiểu `Object` hoặc cấu trúc đồng bộ của `java.util.concurrent` |
| Dùng số lượng object / danh tính cấp phát làm dấu hiệu nghiệp vụ | Tối ưu cache, factory hoặc đặc tính runtime có thể thay đổi cách thể hiện | Lưu một ID miền nghiệp vụ rõ ràng nếu cần định danh thực thể |

Một `IdentityHashMap` có thể hoàn toàn phù hợp khi bạn chủ ý theo dõi **danh tính của các đối tượng thông thường** (ví dụ duyệt đồ thị object). Vấn đề ở đây là dùng nó để biểu diễn **bản đồ theo giá trị** của các lớp value-based.

Không nên sử dụng `WeakReference` hoặc hình thức lưu/truy vết dựa trên từng thể hiện cụ thể để tự tạo cam kết danh tính cho một giá trị. Vòng đời tham chiếu yếu và vòng đời của giá trị là hai khái niệm khác nhau; hãy chọn dữ liệu khóa/định danh đúng với mục tiêu.

## 6. Đặc biệt nguy hiểm: dùng value-based object làm khóa `synchronized`

Mã dưới là **phản ví dụ minh họa**, không phải lời khuyên sử dụng:

```java
// Giả sử day là một LocalDate.
synchronized (day) {
    // Tránh đồng bộ theo một value-based object.
}
```

Có hai rủi ro đối nghịch nhưng đều thực tế:

1. Nếu hai bên xử lý cùng giá trị ngày nhưng nhận **tham chiếu khác nhau**, chúng sẽ khóa **hai monitor khác nhau**, nên không bảo vệ cùng tài nguyên.
2. Nếu factory chia sẻ tham chiếu, những phần code **không liên quan** có thể vô tình cùng khóa một monitor, gây tranh chấp hoặc deadlock.

Từ JDK 16, JEP 390 bổ sung cảnh báo của `javac` cho việc đồng bộ trên các lớp value-based do JDK nhận biết. Có thể dùng `-Xlint:synchronization` để yêu cầu loại chẩn đoán này khi rà soát. Cảnh báo là công cụ tìm lỗi; việc một đoạn mã không phát cảnh báo **không chứng minh** rằng cách khóa của nó đúng (ví dụ nếu đối tượng được giữ dưới biến kiểu `Object`). Một số JDK hỗ trợ tùy chọn chẩn đoán runtime `-XX:DiagnoseSyncOnValueBasedClasses`; đây là tùy chọn phụ thuộc HotSpot/JDK, không phải giải pháp thiết kế.

Khi cần monitor để bảo vệ trạng thái riêng, hãy dùng một đối tượng khóa có chủ sở hữu rõ ràng:

```java
// Đoạn minh họa là thành viên trong một lớp quản lý trạng thái.
private final Object lock = new Object();

void updateState() {
    synchronized (lock) {
        // Đọc/ghi trạng thái cần bảo vệ.
    }
}
```

Nếu cần đồng bộ theo một khóa *nghiệp vụ* dùng chung giữa nhiều luồng, chọn cấu trúc dữ liệu đồng bộ có quản lý khóa/tính nguyên tử theo **giá trị khóa**, chẳng hạn `ConcurrentHashMap.compute(...)`. Không thay thế bằng cách `synchronized (LocalDate.of(...))` rồi kỳ vọng toàn bộ luồng sẽ được tuần tự hóa.

## 7. Ví dụ áp dụng: đếm tác vụ theo ngày một cách an toàn

Kịch bản: các lời gọi có thể tạo những `LocalDate` khác tham chiếu nhưng cùng ngày; toàn bộ tác vụ trong ngày phải tăng cùng bộ đếm. Chương trình sau dùng tính bằng nhau của khóa và cấu trúc concurrent:

```java
import java.time.LocalDate;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class DailyCountDemo {
    private static final ConcurrentHashMap<LocalDate, AtomicInteger> COUNTS =
            new ConcurrentHashMap<>();

    public static void main(String[] args) {
        LocalDate first = LocalDate.of(2026, 10, 23);
        LocalDate second = LocalDate.of(2026, 10, 23);

        COUNTS.computeIfAbsent(first, k -> new AtomicInteger()).incrementAndGet();
        COUNTS.computeIfAbsent(second, k -> new AtomicInteger()).incrementAndGet();

        System.out.println("Count: " + COUNTS.get(first).get());
        System.out.println("Distinct date keys: " + COUNTS.size());
    }
}
```

Lưu thành `DailyCountDemo.java` và chạy:

```bash
javac DailyCountDemo.java
java DailyCountDemo
```

Kết quả:

```text
Count: 2
Distinct date keys: 1
```

`computeIfAbsent` chọn/lưu một bộ đếm cho mỗi **giá trị khóa**, còn `AtomicInteger.incrementAndGet()` cập nhật bộ đếm nguyên tử. Đây là hướng phù hợp khi truy cập đồng thời; không có giả định nào về việc hai lời gọi `LocalDate.of` trả về cùng đối tượng. Trong ứng dụng thật, quản lý kích thước/vòng đời map phù hợp với số lượng ngày cần giữ.

## 8. Khi nào so sánh theo danh tính vẫn đúng?

Không có quy tắc rằng Java phải loại bỏ hoàn toàn `==` cho đối tượng. Điều quan trọng là **ý định so sánh**:

- Với **primitive** `int`, `long`, `boolean`..., `==` là so sánh giá trị theo quy tắc của toán tử.
- Với **enum**, `==` là cách so sánh hằng enum thường dùng, vì mỗi hằng là thể hiện xác định do ngôn ngữ quản lý.
- Với **đối tượng thường** có ý nghĩa danh tính (cùng thực thể/một node đồ thị/một instance đang được theo dõi), `==` có thể là lựa chọn chủ đích.
- Với **value-based class**, so sánh quan hệ giá trị bằng `equals` hoặc API miền chuyên biệt; không dùng danh tính như bằng chứng rằng hai giá trị bằng/khác.
- Một `record` do người dùng khai báo có `equals/hashCode` dựa trên components, nhưng **không tự động trở thành lớp value-based của Java Platform** theo nghĩa tài liệu JDK. Đừng đồng nhất “immutable”, “record”, “value object” trong thiết kế miền với nhãn kỹ thuật *value-based class*.

Khi cần phân biệt *hai thực thể nghiệp vụ* tình cờ có cùng thuộc tính (chẳng hạn hai đơn hàng khác nhau cùng tổng tiền), hãy lưu ID thực thể riêng; khi cần so sánh *một giá trị* (ngày, khoảng thời gian, số đóng hộp), dùng hợp đồng giá trị. Không suy ra ID nghiệp vụ từ địa chỉ đối tượng hoặc mã băm danh tính.

## 9. Lỗi thường gặp và cách tự kiểm

**Lỗi 1: “Tôi thử trên máy và `==` đúng.”** Một lần thực thi chỉ chứng minh hai tham chiếu tình cờ trùng nhau tại thời điểm đó. Kết quả có thể bị tác động bởi cache, factory, môi trường hoặc thay đổi triển khai. Viết kiểm thử theo `equals` và hành vi, không theo `assertSame` / `assertNotSame` cho value-based objects.

**Lỗi 2: “Cùng giá trị thì `synchronized(value)` khóa cùng tài nguyên.”** Bằng nhau về giá trị không đảm bảo chung monitor; ngược lại việc chia sẻ đối tượng có thể tạo liên hệ khóa ngoài ý muốn. Chọn khóa riêng hoặc công cụ concurrent.

**Lỗi 3: “Có `hashCode()` thì dùng `identityHashCode()` cũng được.”** `hashCode` của lớp value-based phục vụ giao ước `equals/hashCode`; `identityHashCode` theo danh tính. Không trộn hai hệ quy chiếu này khi dùng tập hợp hoặc map.

**Lỗi 4: “Immutable nào cũng được JDK công bố value-based.”** Tính bất biến là một thuộc tính; hợp đồng value-based còn liên quan factory, danh tính và tính thay thế tự do. Kiểm tra Javadoc trước khi áp dụng kết luận cho một lớp.

**Checklist khi review code:** Nếu logic đang kiểm tra `==`, chọn khóa `IdentityHashMap`, dùng `identityHashCode`, monitor `synchronized` hoặc tham chiếu yếu trên một đối tượng mô tả giá trị, hãy hỏi: *Mình thực sự cần danh tính instance hay cần giá trị?* Nếu cần giá trị, đổi sang `equals/hashCode` hoặc API nghiệp vụ phù hợp; nếu cần danh tính, chọn một thực thể/ID có hợp đồng danh tính rõ ràng.

## 10. Tóm lược và tài liệu chuẩn

**Nguyên tắc nhớ:** Với value-based class, **hai thể hiện có cùng giá trị phải được đối xử tương đương theo hợp đồng của lớp**. Danh tính mà JVM biểu hiện ở một lần chạy là chi tiết không nên phụ thuộc để quyết định so sánh, phân nhóm, khóa hay nhận diện thực thể.

Tài liệu tham khảo chính thức:

- [Java SE 17 — Value-based Classes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/doc-files/ValueBased.html): định nghĩa và những thao tác nhạy với danh tính cần tránh.
- [Java SE 17 — Optional](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): nhấn mạnh các thể hiện bằng nhau có thể thay thế và không dùng cho đồng bộ.
- [OpenJDK JEP 390 — Warnings for Value-Based Classes](https://openjdk.org/jeps/390): cảnh báo liên quan đến đồng bộ và định hướng tránh phụ thuộc danh tính.
