# Comparator.nullsFirst, nullsLast và chính sách xử lý null trong Java

## 1. Vì sao cần quy định chính sách null trước khi sắp xếp?

Trong dữ liệu thực tế, một danh sách có thể chứa **phần tử null** hoặc các đối tượng hợp lệ nhưng **khóa sắp xếp của chúng là null**. Ví dụ: danh sách tên có phần tử null; một nhân viên tồn tại nhưng trường `name` chưa được nhập; một đơn hàng chưa có `deliveryDate`.

Nếu chỉ gọi `Comparator.naturalOrder()` hoặc `Comparator.comparing(Person::getName)` mà không cân nhắc dữ liệu thiếu, thao tác sort có thể gặp `NullPointerException`. Java cung cấp hai factory method chuẩn để mô tả rõ thứ tự cho giá trị null:

- **`Comparator.nullsFirst(otherComparator)`**: null được xem là **nhỏ hơn** mọi giá trị non-null nên được đưa lên trước khi sắp tăng dần.
- **`Comparator.nullsLast(otherComparator)`**: null được xem là **lớn hơn** mọi giá trị non-null nên được đưa về sau khi sắp tăng dần.

Hai phương thức này đã xuất hiện từ Java 8 và **vẫn là API chính thức trong Java hiện đại**. Chúng không quyết định giúp nghiệp vụ nên coi null là gì: người thiết kế dữ liệu phải chọn một **chính sách null** thích hợp.

**Mục tiêu bài học:** hiểu thứ tự so sánh, phân biệt null ở phần tử và null ở thuộc tính, kết hợp `comparing`/`thenComparing`, sắp giảm dần mà vẫn giữ null cuối, tránh lỗi với `TreeSet`/`TreeMap`, và biết khi nào nên **từ chối hoặc lọc dữ liệu null** thay vì cố sắp xếp.

## 2. Ôn lại hợp đồng Comparator

`Comparator<T>` định nghĩa thứ tự giữa hai giá trị `T` thông qua:

```java
// Chữ ký API minh họa; không phải chương trình độc lập.
int compare(T left, T right);
```

Theo contract:

- Kết quả **âm**: `left` đứng trước `right`.
- Kết quả **0**: `left` và `right` tương đương **về thứ tự** đối với comparator đó.
- Kết quả **dương**: `left` đứng sau `right`.

Không được giả định comparator bắt buộc trả chính xác `-1`, `0` hoặc `1`; chỉ **dấu** của giá trị là điều cần dựa vào.

Một comparator hợp lệ phải duy trì các ràng buộc như **tính đối xứng dấu**, **tính bắc cầu** và nhất quán với những giá trị mà nó coi là ngang hàng. Ví dụ, nếu so sánh `a < b` và `b < c` thì phải suy ra `a < c`. Những quy tắc này quan trọng với thuật toán sort và các cấu trúc dạng cây.

### 2.1. Comparator có được nhận null không?

Có, **nếu implementation của comparator hỗ trợ**. `Comparator` cho phép chính sách xử lý null, nhưng nhiều comparator thông dụng không chấp nhận null:

```java
// Đoạn minh họa.
Comparator<String> natural = Comparator.naturalOrder();
Comparator<String> reverse = Comparator.reverseOrder();
```

`natural.compare(null, "An")` sẽ ném `NullPointerException`; `reverseOrder` cũng không so sánh null một cách an toàn.

Việc `List<String>` có thể lưu một phần tử null không có nghĩa comparator dùng để sort danh sách đó tự động xử lý được null. **Khả năng chứa null của collection** và **khả năng so sánh null của comparator** là hai contract khác nhau.

## 3. nullsFirst và nullsLast: ý nghĩa chính xác

Chữ ký API:

```java
static <T> Comparator<T> nullsFirst(
    Comparator<? super T> comparator
);

static <T> Comparator<T> nullsLast(
    Comparator<? super T> comparator
);
```

Các hàm này tạo một comparator **bao bọc** comparator có sẵn. Khi có null, lớp bao xử lý ngay mà không yêu cầu comparator con phải hiểu null. Khi **cả hai giá trị đều non-null**, comparator con quyết định thứ tự.

### 3.1. Bảng so sánh

Giả sử comparator con là `Comparator.naturalOrder()`:

| Hai giá trị so sánh | `nullsFirst` | `nullsLast` |
| --- | --- | --- |
| `null` với `null` | `0`: tương đương | `0`: tương đương |
| `null` với `"An"` | Âm: null trước | Dương: null sau |
| `"An"` với `null` | Dương: "An" sau | Âm: "An" trước |
| `"An"` với `"Binh"` | Dựa vào natural order | Dựa vào natural order |
| `"Binh"` với `"An"` | Dựa vào natural order | Dựa vào natural order |

Dữ liệu ví dụ: `["Zoe", null, "An", null, "Binh"]`.

```text
Comparator.nullsFirst(naturalOrder()):
[null, null, An, Binh, Zoe]

Comparator.nullsLast(naturalOrder()):
[An, Binh, Zoe, null, null]
```

Điều cần nhấn mạnh: `nullsFirst` không tự sắp theo bảng chữ cái nếu không có comparator con phù hợp. Nó chỉ thiết lập vị trí của null **so với các giá trị không null**; comparator con chịu trách nhiệm so sánh những giá trị còn lại.

### 3.2. Đặc biệt: tham số comparator con có thể là null

Javadoc cho phép:

```java
// Đoạn minh họa.
Comparator<String> c = Comparator.nullsFirst(null);
```

Khi comparator con là `null`:

- Cả hai phần tử null được coi là bằng nhau.
- Null luôn đứng trước các giá trị non-null.
- **Mọi giá trị non-null được coi là tương đương nhau về thứ tự**, tức `c.compare("An", "Zoe") == 0`.

Điều này khác hoàn toàn `Comparator.nullsFirst(Comparator.naturalOrder())`: trường hợp thứ hai **vẫn** sắp các chuỗi non-null theo natural order.

Khả năng truyền comparator con `null` là một hành vi API hợp lệ, nhưng **không nên dùng vô tình**. Nó có thể tạo hậu quả nghiêm trọng với `TreeSet` hoặc `TreeMap`, nơi việc `compare(a,b)==0` ảnh hưởng trực tiếp đến việc xem hai phần tử/khóa có trùng nhau hay không.

## 4. Ví dụ 1 — sắp xếp null trước và null sau

Tạo file **NullPlacementDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullPlacementDemo {
    public static void main(String[] args) {
        List<String> source = Arrays.asList(
            "Zoe", null, "An", null, "Binh"
        );

        List<String> first = new ArrayList<>(source);
        List<String> last = new ArrayList<>(source);

        first.sort(
            Comparator.nullsFirst(Comparator.naturalOrder())
        );

        last.sort(
            Comparator.nullsLast(Comparator.naturalOrder())
        );

        System.out.println("first=" + first);
        System.out.println("last=" + last);

        Comparator<String> c =
            Comparator.nullsFirst(String::compareTo);

        System.out.println("bothNull=" +
            c.compare(null, null));

        System.out.println("nullBefore=" +
            (c.compare(null, "An") < 0));
    }
}
```

Dùng JDK 17+ (các API liên quan đã có từ Java 8):

```bash
javac NullPlacementDemo.java
java NullPlacementDemo
```

Đầu ra:

```text
first=[null, null, An, Binh, Zoe]
last=[An, Binh, Zoe, null, null]
bothNull=0
nullBefore=true
```

**Giải thích:**

1. Hai bản sao `first` và `last` được tạo để so sánh hai chính sách mà không sửa đổi danh sách `source`.
2. `nullsFirst(naturalOrder())` tách null lên đầu, còn các chuỗi còn lại theo thứ tự tự nhiên.
3. `nullsLast(naturalOrder())` đưa null về cuối, còn các chuỗi non-null vẫn theo thứ tự tự nhiên.
4. `c.compare(null, null) == 0` vì hai null được coi là ngang nhau.
5. `c.compare(null, "An") < 0` vì null được định nghĩa đứng trước mọi giá trị non-null.

**Cẩn thận khi khởi tạo danh sách:** `Arrays.asList(...)` và `new ArrayList<>(...)` trong ví dụ có thể chứa null. Ngược lại, `List.of(...)` (Java 9+) **không chấp nhận phần tử null**; truyền null vào factory method đó gây `NullPointerException` ngay khi tạo danh sách, trước khi có cơ hội sắp xếp.

## 5. Chính sách null: phải lựa chọn theo nghiệp vụ

`nullsFirst` và `nullsLast` là giải pháp kỹ thuật, **không phải tiêu chuẩn nghiệp vụ áp dụng cho mọi dữ liệu**. Một hệ thống nên xác định rõ null nghĩa là gì, được phép ở đâu và cần phản ứng thế nào.

| Chính sách | Khi thích hợp | Cách thực hiện |
| --- | --- | --- |
| **Reject** — từ chối null | Trường bắt buộc: ID, mã giao dịch, khóa phân loại yêu cầu đầy đủ | Xác thực đầu vào, `Objects.requireNonNull`, báo lỗi rõ nguyên nhân |
| **Omit** — bỏ bản ghi null khỏi kết quả | Báo cáo chỉ xử lý các giá trị hiện hữu và được phép loại bản ghi thiếu | `filter(Objects::nonNull)` trước `sorted` |
| **Null first** | UI muốn nhóm dữ liệu chưa nhập lên đầu để xử lý bổ sung | `Comparator.nullsFirst(comparator)` |
| **Null last** | UI muốn dữ liệu đầy đủ đứng trước, mục thiếu dữ liệu ở cuối | `Comparator.nullsLast(comparator)` |
| **Null key first/last** | Đối tượng tồn tại, nhưng một thuộc tính để sort có thể thiếu | `Comparator.comparing(extractor, nullsLast(keyComparator))` |
| **Normalize/derive** | Nghiệp vụ có giá trị mặc định có ý nghĩa rõ ràng | Chuẩn hóa dữ liệu trước khi sort theo quy tắc công bố |
| **Distinguish error vs absence** | Thiếu dữ liệu và lỗi hệ thống là hai trạng thái khác nhau | Dùng kiểu kết quả hoặc validation mang nguyên nhân, không chỉ một null |

Ví dụ, ngày giao hàng `deliveryDate == null` có thể mang nghĩa “chưa lên lịch”. Nếu giao diện muốn các đơn hàng đã lên lịch xuất hiện trước, **nullsLast** thường phù hợp. Nhưng nếu màn hình nhằm xử lý các đơn hàng **chưa lên lịch**, **nullsFirst** có thể đúng hơn.

**Không gán mặc định giả như ngày `1970-01-01` hoặc số `0` chỉ để tránh null nếu điều đó gây hiểu sai nghiệp vụ**. Biện pháp này có thể biến dữ liệu thiếu thành dữ liệu hợp lệ giả, ảnh hưởng các báo cáo sau này.

### 5.1. Ba tình huống cần phân biệt

1. **Phần tử null:** `List<Person>` có một vị trí mà chính giá trị `Person` là `null`.
2. **Khóa sort null:** `Person` là object hợp lệ nhưng `person.name() == null`.
3. **Dữ liệu invalid khác null:** chuỗi `""` hoặc `"   "` không phải null, nhưng có thể không đạt quy tắc tên hợp lệ.

`Comparator.nullsLast(...)` xử lý thứ nhất hoặc thứ hai **tùy vị trí bạn đặt nó**. Nó không tự biến chuỗi rỗng thành null và cũng không tự kiểm tra tính hợp lệ của toàn bộ record.

## 6. null ở thuộc tính: dùng comparing(keyExtractor, keyComparator)

Một lỗi phổ biến là object không null nhưng khóa sắp xếp có thể null.

Giả sử:

```java
// Đoạn minh họa: employee không null, nhưng email có thể null.
Comparator<Employee> byEmail = Comparator.comparing(
    Employee::email
);
```

Nếu `email()` trả null và comparator được tạo dựa trên natural order của `String`, việc so sánh với chuỗi có thể gây `NullPointerException`.

Cách chính xác:

```java
// Đoạn minh họa.
Comparator<Employee> byEmail = Comparator.comparing(
    Employee::email,
    Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
);
```

Ở đây:

- `Employee::email` **được phép trả null**.
- `Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)` so sánh **khóa String**, không phải object Employee.
- Hai khóa null được coi là bằng nhau theo bước so sánh này; có thể thêm tiêu chí khác để phá thế hòa.

### 6.1. Nối thenComparing để phân định các giá trị bằng nhau

Nếu hai nhân viên cùng tên hoặc tên chỉ khác chữ hoa/chữ thường, comparator tên không phân biệt hoa thường có thể trả `0`. Ta có thể bổ sung khóa ID:

```java
// Mã minh họa.
Comparator<Employee> comparator = Comparator
    .comparing(Employee::name,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER))
    .thenComparingInt(Employee::id);
```

`thenComparingInt` chỉ xét ID khi tiêu chí tên cho kết quả bằng nhau. Việc thêm ID (giả sử ID duy nhất) tạo thứ tự chi tiết hơn và tránh vô tình coi hai nhân viên khác nhau là cùng một khóa thứ tự.

### Ví dụ 2 — NullableKeyDemo.java

Tạo file **NullableKeyDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullableKeyDemo {
    static final class Employee {
        private final int id;
        private final String name;

        Employee(int id, String name) {
            this.id = id;
            this.name = name;
        }

        int id() {
            return id;
        }

        String name() {
            return name;
        }

        @Override
        public String toString() {
            return id + ":" + name;
        }
    }

    public static void main(String[] args) {
        List<Employee> employees = new ArrayList<>(Arrays.asList(
            new Employee(3, "ana"),
            new Employee(2, null),
            new Employee(1, "ANA"),
            new Employee(4, "bob")
        ));

        Comparator<Employee> byName = Comparator
            .comparing(
                Employee::name,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
            )
            .thenComparingInt(Employee::id);

        employees.sort(byName);

        System.out.println("employees=" + employees);
    }
}
```

```bash
javac NullableKeyDemo.java
java NullableKeyDemo
```

Đầu ra:

```text
employees=[1:ANA, 3:ana, 4:bob, 2:null]
```

**Giải thích kết quả:**

- Hai giá trị tên `"ANA"` và `"ana"` được `String.CASE_INSENSITIVE_ORDER` xem là bằng nhau, nên `thenComparingInt` dùng ID và đưa nhân viên ID `1` trước ID `3`.
- Tên `"bob"` đứng sau nhóm `ana`.
- Employee ID `2` có tên null nên xuống cuối, mặc dù ID `2` nhỏ hơn ID `4`, vì ID là **tiêu chí phụ**.
- Không có `Employee` nào null trong danh sách này; chỉ **khóa tên** có null.

**Ghi chú:** `String.CASE_INSENSITIVE_ORDER` dùng quy tắc không phân biệt hoa/thường của `String`, không phải bộ so sánh ngôn ngữ theo locale cho mọi quốc gia. Nếu cần thứ tự theo ngôn ngữ tự nhiên của người dùng, xem xét `Collator` với locale phù hợp và xác định rõ kỳ vọng của nghiệp vụ.

## 7. Null object và null key: cần hai lớp xử lý

Điểm phân biệt quan trọng nhất khi viết Comparator cho object:

```java
// Chỉ an toàn cho NAME null khi Person object không null.
Comparator<Person> byName = Comparator.comparing(
    Person::name,
    Comparator.nullsFirst(String.CASE_INSENSITIVE_ORDER)
);
```

Nếu bản thân phần tử `Person` là null, `Person::name` không thể chạy trên nó. Comparator khóa bên trong **chưa đủ**.

Một comparator xử lý **cả hai tầng**:

```java
// Mã minh họa: null Person cuối; null name của Person lên đầu.
Comparator<Person> safe = Comparator.nullsLast(
    Comparator.comparing(
        Person::name,
        Comparator.nullsFirst(String.CASE_INSENSITIVE_ORDER)
    ).thenComparingInt(Person::id)
);
```

- **Lớp ngoài:** `Comparator.nullsLast(...)` kiểm tra **cả đối tượng Person**. Nếu Person null, nó được đưa cuối và không gọi key extractor.
- **Lớp trong:** `Comparator.nullsFirst(...)` kiểm tra **khóa name** lấy từ một Person đã xác định non-null.
- **Tiêu chí phụ:** `thenComparingInt(Person::id)` giải quyết hai Person có tên ngang nhau, bao gồm cả hai tên null.

Do đó việc gói ở tầng nào **thay đổi chính sách**; không chỉ là một cách viết khác.

### Ví dụ 3 — NullElementAndKeyDemo.java

Tạo file **NullElementAndKeyDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class NullElementAndKeyDemo {
    static final class Person {
        private final int id;
        private final String name;

        Person(int id, String name) {
            this.id = id;
            this.name = name;
        }

        int id() {
            return id;
        }

        String name() {
            return name;
        }

        @Override
        public String toString() {
            return id + ":" + name;
        }
    }

    public static void main(String[] args) {
        List<Person> values = new ArrayList<>(Arrays.asList(
            new Person(1, "Bob"),
            null,
            new Person(2, null),
            new Person(3, "Alice")
        ));

        Comparator<Person> byName = Comparator.nullsLast(
            Comparator.comparing(
                Person::name,
                Comparator.nullsFirst(String.CASE_INSENSITIVE_ORDER)
            ).thenComparingInt(Person::id)
        );

        values.sort(byName);
        System.out.println("objectsAndKeys=" + values);
    }
}
```

```bash
javac NullElementAndKeyDemo.java
java NullElementAndKeyDemo
```

Đầu ra:

```text
objectsAndKeys=[2:null, 3:Alice, 1:Bob, null]
```

**Đọc đúng chính sách:**

1. `Person(2, null)` là object hợp lệ nhưng khóa name null. Lớp so sánh khóa `nullsFirst` đưa nó lên đầu **trong nhóm Person non-null**.
2. `Person(3, "Alice")` và `Person(1, "Bob")` được sắp theo tên.
3. Phần tử `null` (không có object Person) được lớp ngoài `nullsLast` đặt cuối cùng.
4. Nếu bỏ lớp ngoài, khi sort chạm phần tử null, `Person::name` có thể gây NPE.
5. Nếu bỏ lớp trong, khi so sánh tên null với tên non-null, comparator chuỗi thông thường có thể gây NPE.

Đây là một ví dụ điển hình về **khác biệt giữa giá trị đối tượng null và một thuộc tính của đối tượng có null**.

## 8. Sort giảm dần mà vẫn giữ null ở cuối

Nhiều ứng dụng muốn số/ngày **giảm dần** nhưng các giá trị null vẫn luôn ở cuối. Có hai cách viết trông gần nhau nhưng kết quả **khác nhau**:

```java
// Đúng khi muốn NON-NULL giảm dần, NULL vẫn ở cuối.
Comparator<Integer> descendingNullLast =
    Comparator.nullsLast(Comparator.reverseOrder());

// Khác mục tiêu: đảo toàn bộ comparator đã có nullsLast.
Comparator<Integer> reversedWhole =
    Comparator.nullsLast(Comparator.<Integer>naturalOrder())
              .reversed();
```

`reversed()` **đảo dấu toàn bộ kết quả so sánh**, tức không chỉ đảo thứ tự non-null mà còn đảo vị trí null.

Với `[null, 5, 2, null, 8]`:

```text
nullsLast(reverseOrder())           -> [8, 5, 2, null, null]
nullsLast(naturalOrder()).reversed() -> [null, null, 8, 5, 2]
```

**Quy tắc:** Nếu chính sách nghiệp vụ là “null luôn ở cuối” dù thứ tự tăng hay giảm, hãy đặt `nullsLast` **bên ngoài comparator mô tả thứ tự của giá trị non-null**; không đảo cả lớp bao xử lý null.

### Ví dụ 4 — ReversalDemo.java

Tạo file **ReversalDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

public class ReversalDemo {
    public static void main(String[] args) {
        List<Integer> source = Arrays.asList(
            null, 5, 2, null, 8
        );

        List<Integer> keepLast = new ArrayList<>(source);
        keepLast.sort(
            Comparator.nullsLast(Comparator.reverseOrder())
        );

        List<Integer> reverseWhole = new ArrayList<>(source);
        reverseWhole.sort(
            Comparator.nullsLast(
                Comparator.<Integer>naturalOrder()
            ).reversed()
        );

        System.out.println("descNullLast=" + keepLast);
        System.out.println("reverseWhole=" + reverseWhole);
    }
}
```

```bash
javac ReversalDemo.java
java ReversalDemo
```

Đầu ra:

```text
descNullLast=[8, 5, 2, null, null]
reverseWhole=[null, null, 8, 5, 2]
```

Trong bảng hiển thị doanh thu, điểm số hoặc mốc thời gian, lựa chọn thứ tự non-null và vị trí null nên là **hai quyết định độc lập**. Đảo chiều toàn bộ comparator là đúng **chỉ khi thực sự muốn đảo luôn chính sách null**.

## 9. Lọc, từ chối hoặc chuẩn hóa null trước khi sort

Không phải mọi kết quả sắp xếp cần giữ các phần tử null. Đôi khi nghiệp vụ yêu cầu chỉ xử lý những giá trị thực sự hợp lệ.

### 9.1. Filter trước sorted

```java
// Mã minh họa: input là List<String> có thể có null.
List<String> result = input.stream()
    .filter(Objects::nonNull)
    .map(String::trim)
    .filter(s -> !s.isEmpty())
    .sorted(String.CASE_INSENSITIVE_ORDER)
    .collect(Collectors.toList());
```

- `Objects::nonNull` bỏ **chính phần tử null**.
- `trim` loại khoảng trắng đầu/cuối.
- `filter(s -> !s.isEmpty())` bỏ cả chuỗi rỗng sau chuẩn hóa.
- `sorted` không cần `nullsLast` vì các phần tử null đã bị loại.

**Nhưng:** nếu null trong dữ liệu là lỗi bắt buộc phải được thông báo, filter âm thầm sẽ che lỗi. Chọn lọc chỉ phù hợp khi nghiệp vụ **cho phép loại bỏ giá trị thiếu**.

### 9.2. Reject dữ liệu không hợp lệ

Có thể kiểm tra bằng `Objects.requireNonNull(value, "message")`. Nếu giá trị null, nó ném `NullPointerException` với thông điệp rõ ràng. Ở boundary nhập liệu, dự án có thể chọn exception nghiệp vụ riêng thay vì NPE; cốt lõi vẫn là **phát hiện sớm và công khai contract dữ liệu**.

### Ví dụ 5 — NullPolicyDemo.java

Tạo file **NullPolicyDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public class NullPolicyDemo {
    public static void main(String[] args) {
        List<String> raw = Arrays.asList(
            " beta ", null, "Alpha", " ", "gamma"
        );

        List<String> cleaned = raw.stream()
            .filter(Objects::nonNull)
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .sorted(String.CASE_INSENSITIVE_ORDER)
            .collect(Collectors.toList());

        System.out.println("normalized=" + cleaned);

        System.out.println("containsNull=" +
            raw.stream().anyMatch(Objects::isNull));

        try {
            raw.forEach(v ->
                Objects.requireNonNull(v, "name required"));
        } catch (NullPointerException e) {
            System.out.println("reject=" + e.getMessage());
        }
    }
}
```

```bash
javac NullPolicyDemo.java
java NullPolicyDemo
```

Đầu ra:

```text
normalized=[Alpha, beta, gamma]
containsNull=true
reject=name required
```

**Phân tích:** cùng một nguồn dữ liệu, chính sách “lọc bỏ null” tạo ba tên hợp lệ, còn chính sách “từ chối null” phát hiện lỗi. Hai nhánh **không tương đương về mặt nghiệp vụ**. Khi xây API, phải chọn một nhánh theo yêu cầu và ghi rõ cho người dùng, không tùy tiện thay thế.

### 9.3. Ranh giới chuẩn hóa dữ liệu

Null, chuỗi rỗng, chuỗi chỉ có khoảng trắng và mã đặc biệt `"UNKNOWN"` là những trạng thái **khác nhau**. Nếu hệ thống cần gộp chúng, phải có quy tắc rõ ràng; không mặc định rằng `Comparator.nullsLast` tự giải quyết mọi dạng dữ liệu thiếu.

Nếu dữ liệu đến từ database, cũng cần phân biệt ngữ nghĩa của `ORDER BY ... NULLS LAST` trong SQL và ngữ nghĩa comparator Java: kết quả cụ thể của mỗi hệ thống phải được thống nhất ở boundary. Không tự giả định thứ tự null của database mặc định giống Java.

## 10. Quan hệ giữa Comparator, List.sort và Stream.sorted

Có thể dùng comparator null-safe với nhiều API hiện hành:

```java
// Mã minh họa: values là List<String> có thể chứa null.
Comparator<String> cmp =
    Comparator.nullsLast(Comparator.naturalOrder());

// Cách 1: Sắp xếp ngay trên list có thể sửa được.
values.sort(cmp);

// Cách 2: Tạo list kết quả, không thay đổi collection nguồn.
List<String> sorted = values.stream()
    .sorted(cmp)
    .collect(Collectors.toList());
```

**Khác biệt:**

- `List.sort(cmp)` sắp xếp **chính list**; có thể thất bại nếu list không hỗ trợ cập nhật phần tử, ví dụ list không chỉnh sửa được.
- `Stream.sorted(cmp)` là intermediate operation tạo một pipeline sắp xếp; công việc được thực thi khi có terminal operation. Nó không tự sửa danh sách nguồn.
- `Collections.sort(list, cmp)` là API hợp lệ khác vẫn được hỗ trợ, nhưng khi đã có `List.sort`, gọi trực tiếp trên list thường dễ đọc hơn.
- `Arrays.sort(array, cmp)` dùng cho mảng đối tượng. Overload comparator không dùng cho mảng primitive như `int[]`.

### 10.1. Tính ổn định khi sort

Với một **List** và comparator đã cho, `List.sort` được quy định là **stable**: những phần tử được comparator coi là ngang nhau không bị đảo thứ tự tương đối do phép sắp xếp đó. `Stream.sorted` cũng stable đối với **ordered streams**; với unordered stream, không có bảo đảm ổn định tương tự.

Ví dụ nếu comparator chỉ so sánh tên không phân biệt hoa thường, hai record `"ANA"` và `"ana"` có thể được coi là ngang nhau. Sort ổn định giữ thứ tự tương đối, nhưng đó **không thay thế** việc dùng `thenComparing` khi nghiệp vụ cần một thứ tự phụ có ý nghĩa.

**Không phụ thuộc vào lần chạy cụ thể để suy ra thứ tự của `HashSet` hoặc các nguồn unordered**. Nếu thứ tự là yêu cầu, sử dụng nguồn ordered và comparator mô tả đầy đủ quy tắc.

## 11. Cạm bẫy lớn: nullsFirst(null) và TreeSet/TreeMap

`TreeSet` và `TreeMap` dùng comparator không chỉ để trình bày thứ tự mà còn để **xác định tính tương đương của các phần tử/khóa**. Khi comparator trả `0` cho hai object, cấu trúc cây xem chúng là cùng một vị trí khóa theo ordering.

Vì `Comparator.nullsFirst(null)` coi **mọi giá trị non-null là ngang nhau**, dùng nó làm comparator của TreeSet có thể làm mất dữ liệu.

### Ví dụ 6 — TreeSetPitfallDemo.java

Tạo file **TreeSetPitfallDemo.java**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.TreeSet;

public class TreeSetPitfallDemo {
    public static void main(String[] args) {
        Comparator<String> allNonNullEqual =
            Comparator.nullsFirst(null);

        List<String> list = new ArrayList<>(Arrays.asList(
            "beta", null, "alpha", "gamma"
        ));
        list.sort(allNonNullEqual);

        System.out.println("stableList=" + list);

        TreeSet<String> set = new TreeSet<>(allNonNullEqual);
        set.add("alpha");
        set.add("beta");
        set.add(null);

        System.out.println("set=" + set);
        System.out.println("setSize=" + set.size());
    }
}
```

```bash
javac TreeSetPitfallDemo.java
java TreeSetPitfallDemo
```

Đầu ra:

```text
stableList=[null, beta, alpha, gamma]
set=[null, alpha]
setSize=2
```

**Vì sao list có bốn phần tử mà set chỉ có hai?**

- Trong `list.sort`, mọi chuỗi non-null có kết quả so sánh `0`, nên sort stable giữ thứ tự `beta, alpha, gamma` trong nhóm non-null. Null được chuyển lên đầu.
- Trong `TreeSet`, sau khi thêm `"alpha"`, giá trị `"beta"` được so sánh và nhận `0`; set coi nó là phần tử đã có và **không thêm**.
- `null` được comparator chấp nhận và khác với giá trị non-null, nên có mặt như một khóa riêng.
- Tổng số phần tử `2` là hệ quả của contract ordering, không phải do TreeSet “tự bỏ bớt ngẫu nhiên”.

Muốn giữ đủ những giá trị non-null phân biệt theo tự nhiên, dùng:

```java
// Đoạn minh họa.
Comparator<String> correct =
    Comparator.nullsFirst(Comparator.naturalOrder());
```

**Cảnh báo tương tự** với `Comparator.comparing(..., String.CASE_INSENSITIVE_ORDER)`: hai chuỗi chỉ khác hoa/thường có thể được coi là bằng nhau theo comparator nhưng khác theo `String.equals`. Nếu đưa comparator không nhất quán với equals vào `TreeSet`/`TreeMap`, cần hiểu và công bố chính sách “khóa trùng” tương ứng.

### 11.1. TreeMap và null key

Một `TreeMap` sử dụng comparator **chấp nhận null** có thể hỗ trợ khóa null theo ordering của comparator. Ngược lại, `TreeMap` dùng natural ordering thông thường không chấp nhận null key.

Ví dụ về ý định:

```java
// Mã minh họa, không phải chương trình độc lập.
Map<String, Integer> counts = new TreeMap<>(
    Comparator.nullsLast(Comparator.naturalOrder())
);

counts.put(null, 1);
counts.put("A", 2);
```

Nhưng chỉ nên cho phép khóa null nếu **nghiệp vụ thực sự xem null là một khóa hợp lệ**. Dù comparator cho phép null, các phương thức của map và các lớp bao/đoạn xử lý khác vẫn phải được đánh giá theo contract riêng.

## 12. Comparator.comparingInt, null và giá trị primitive

`Comparator.comparingInt(ToIntFunction<T>)` rất tiện khi khóa kiểu primitive `int`. Nhưng nếu thuộc tính ban đầu là `Integer` nullable và bị autounboxing thành `int`, việc lấy khóa null sẽ gây `NullPointerException`.

Mẫu có rủi ro:

```java
// Đoạn minh họa; age() trả Integer có thể null.
Comparator<Person> byAge =
    Comparator.comparingInt(p -> p.age()); // null -> NPE do unboxing
```

Nếu tuổi có thể null và cần giữ bản ghi:

```java
// Mã minh họa đúng cho Person không null, age nullable.
Comparator<Person> byAge = Comparator.comparing(
    Person::age,
    Comparator.nullsLast(Comparator.<Integer>naturalOrder())
);
```

Lúc này khóa giữ kiểu `Integer` nên comparator null-safe có thể phân biệt null. Cũng có thể thêm lớp `Comparator.nullsLast(...)` **bên ngoài** nếu bản thân `Person` trong list cũng có thể null.

**Không dùng giá trị sentinel tùy ý** (như `Integer.MAX_VALUE` hoặc `-1`) để thay cho null nếu giá trị đó có thể là một dữ liệu nghiệp vụ hợp lệ. Điều này làm thay đổi thứ tự và có thể làm mất phân biệt giữa “thiếu dữ liệu” với “giá trị thật”.

### 12.1. Không viết Comparator bằng phép trừ tùy tiện

Mẫu so sánh số sai:

```java
// Minh họa sai: có thể overflow khi các số cách nhau quá lớn.
Comparator<Integer> unsafe = (a, b) -> a - b;
```

Dùng `Integer.compare(a, b)`, `Comparator.naturalOrder()` hoặc `Comparator.comparingInt(...)` theo kiểu dữ liệu thực tế. Nếu có null, gói comparator thích hợp bằng `nullsFirst`/`nullsLast`; phép trừ tự viết vừa không xử lý null vừa có rủi ro tràn.

## 13. thenComparing và quy tắc ưu tiên khi khóa null

Thứ tự trong comparator nhiều tiêu chí là thứ tự **ưu tiên từ trái sang phải**:

```java
// Đoạn minh họa.
Comparator<Employee> cmp =
    Comparator.comparing(
        Employee::department,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
    ).thenComparing(
        Employee::name,
        Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER)
    ).thenComparingInt(Employee::id);
```

Quy tắc này:

1. Sắp theo department, null department cuối.
2. **Chỉ khi department ngang nhau**, so theo name, null name cuối trong nhóm department đó.
3. **Chỉ khi cả hai khóa ngang nhau**, so ID tăng dần.

Nói cách khác, null name không nhất thiết nằm ở **cuối toàn bộ danh sách** nếu department vẫn là khóa ưu tiên cao nhất. Nếu mong muốn “mọi record thiếu name đều ở cuối bất kể department”, phải đưa phép so sánh **thiếu name hay không** lên làm tiêu chí đầu tiên, rồi mới sắp các trường khác.

**Đừng dùng `thenComparing` để chữa lỗi null ở tiêu chí đầu.** Nếu comparator đầu tiên ném NPE trước khi trả kết quả, tiêu chí sau không có cơ hội chạy. Cần bảo đảm **mỗi tiêu chí nullable** có comparator phù hợp ngay tại tầng của nó.

### 13.1. Thứ tự rỗng, null và lỗi có thể cần tách riêng

Khi nghiệp vụ cần thứ tự cụ thể như:

```text
valid values -> blank strings -> null -> invalid records
```

thì `nullsLast` một mình không đủ. Bạn phải định nghĩa một **phân loại có ý nghĩa** (ví dụ trạng thái dữ liệu), sau đó so sánh trạng thái và giá trị trong mỗi nhóm. Chính sách này nên được kiểm thử bằng những ví dụ biên thay vì dựa vào vị trí null như một mẹo.

## 14. Sai lầm thường gặp

### Lỗi 1 — dùng naturalOrder() trực tiếp với danh sách có null

`Comparator.naturalOrder()` không chấp nhận null. Nếu nghiệp vụ cần giữ null, gói bằng `Comparator.nullsFirst/Last`. Nếu null là dữ liệu lỗi, validate rồi từ chối thay vì cố sort.

### Lỗi 2 — dùng nullsLast ở tầng object khi chỉ khóa bị null

`Comparator.nullsLast(Comparator.comparing(Person::name))` bảo vệ **Person null**, nhưng nếu Person non-null mà `name() == null`, comparator key vẫn có thể ném NPE. Đặt `nullsLast` ở **key comparator** cho trường hợp khóa nullable.

### Lỗi 3 — chỉ bảo vệ khóa khi bản thân phần tử có thể null

`Comparator.comparing(Person::name, nullsLast(...))` không xử lý object Person null. Nếu danh sách cho phép null Person, cần thêm lớp bao ngoài.

### Lỗi 4 — gọi reversed() ở ngoài làm đổi cả chính sách null

`nullsLast(naturalOrder()).reversed()` đưa null lên đầu. Nếu muốn non-null giảm dần mà null vẫn cuối, dùng `nullsLast(reverseOrder())`.

### Lỗi 5 — truyền null làm comparator con rồi tưởng đó là natural order

`nullsFirst(null)` coi **mọi non-null là ngang nhau**; nó không sắp chúng theo bảng chữ cái. Với TreeSet/TreeMap, đây là rủi ro mất các phần tử/khóa được xem là trùng.

### Lỗi 6 — lọc null âm thầm khi nghiệp vụ cần phát hiện lỗi

`filter(Objects::nonNull)` làm mất phần tử. Chỉ dùng nếu việc loại bỏ hợp lệ; nếu null vi phạm contract dữ liệu, phải báo lỗi.

### Lỗi 7 — nghĩ blank string cũng được nullsLast xử lý như null

`""`, `"  "` và `null` là ba trạng thái khác nhau. Muốn quy về một trạng thái hoặc sắp theo mức ưu tiên, phải định nghĩa chính sách chuẩn hóa cụ thể.

### Lỗi 8 — dùng comparingInt với trường Integer nullable

Unboxing `null` gây NPE. Với khóa nullable, dùng `comparing(extractor, nullsLast(Comparator.naturalOrder()))` và giữ kiểu boxed.

### Lỗi 9 — tưởng comparator trả 0 nghĩa là equals() phải true

Comparator trả 0 nghĩa “ngang nhau theo ordering”. Với `TreeSet`/`TreeMap`, nó còn ảnh hưởng tính duy nhất của phần tử/khóa. Cần cân nhắc tính nhất quán với `equals`.

### Lỗi 10 — viết comparator bằng a - b

Dễ overflow, có thể vi phạm contract và sai sort. Dùng `Integer.compare` hoặc comparator dựng sẵn, bổ sung null policy riêng.

### Lỗi 11 — dùng List.of(null) rồi chờ comparator xử lý

`List.of(...)` không chấp nhận null. Comparator không thể bảo vệ lỗi xảy ra **trước khi sort**. Dùng cấu trúc dữ liệu và validation phù hợp với yêu cầu thực tế.

### Lỗi 12 — sort trên list không chỉnh sửa được

`List.sort` yêu cầu list hỗ trợ việc cập nhật các vị trí khi sắp xếp. Nếu source là danh sách không chỉnh sửa được, tạo `new ArrayList<>(source)` rồi sort, hoặc dùng `stream().sorted(comparator).collect(...)`.

### Lỗi 13 — kỳ vọng nullsLast tự xử lý lỗi trong key extractor

Comparator wrapper xử lý các giá trị null được đưa vào đúng tầng. Nếu `extractor` tự ném exception, truy cập object khác null sai, hoặc thực hiện side effect, `nullsLast` không tự bắt/sửa lỗi đó.

### Lỗi 14 — không kiểm thử tính bắc cầu và thế hòa

Một comparator có nhiều nhánh if không đối xứng hoặc khác quy tắc với null có thể vi phạm contract. Ưu tiên factory methods chuẩn và kiểm thử với các bộ ba giá trị, null, và các key bằng nhau.

### Lỗi 15 — kỳ vọng sort ổn định cứu thứ tự nghiệp vụ còn thiếu

Stable sort chỉ giữ thứ tự tương đối khi comparator trả 0. Nếu cần thứ tự cụ thể cho mỗi record, thêm tiêu chí phụ `thenComparing` thích hợp.

## 15. Checklist thiết kế chính sách null

Trước khi triển khai chức năng sắp xếp:

1. Null là trạng thái hợp lệ hay lỗi dữ liệu phải chặn?
2. Cần **giữ**, **bỏ**, **ưu tiên đầu**, hay **ưu tiên cuối** các phần tử thiếu dữ liệu?
3. Null xuất hiện ở **cả object**, ở **khóa sắp xếp**, hay cả hai?
4. Comparator của từng trường non-null là natural order, reverse order, case-insensitive hay thứ tự theo locale?
5. Khi đổi từ tăng sang giảm, null **vẫn ở cuối** hay đảo cùng các giá trị khác?
6. Có tiêu chí phụ khi các khóa bằng nhau để tạo thứ tự xác định không?
7. Có dùng comparator trong `List.sort` hay trong `TreeSet`/`TreeMap`, nơi `compare()==0` ảnh hưởng tính duy nhất?
8. Có dữ liệu rỗng/blank/sentinel cần chính sách riêng không?
9. Có nguy cơ unboxing khóa nullable hoặc overflow từ comparator số tự viết không?
10. Có kiểm thử input rỗng, toàn null, một null, nhiều null, hai khóa bằng nhau, và các trường hợp đảo chiều không?
11. Nếu sắp xếp từ Stream, có đang bảo toàn hoặc cố ý từ bỏ encounter order không?
12. Chính sách này đã được thể hiện trong tên comparator hoặc mô tả API đủ rõ cho người dùng chưa?

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `Comparator.nullsFirst(Comparator.naturalOrder())` xử lý `[3, null, 1]` thế nào?

**Đáp án:** `[null, 1, 3]`. Null được coi là nhỏ hơn mọi số non-null.

**Câu 2.** `Comparator.nullsLast(Comparator.naturalOrder())` xử lý dãy trên thế nào?

**Đáp án:** `[1, 3, null]`. Null được coi là lớn hơn mọi số non-null.

**Câu 3.** Hai null được so sánh bằng `nullsLast(...)` trả giá trị nào?

**Đáp án:** Trả `0`, tức hai giá trị null ngang nhau theo thứ tự.

**Câu 4.** `Comparator.nullsFirst(null)` có sắp `"An"` trước `"Zoe"` theo alphabet không?

**Đáp án:** Không. Mọi giá trị **non-null** đều được comparator đó coi là ngang nhau (trả 0).

**Câu 5.** `Comparator.comparing(Person::name, nullsLast(...))` có đủ an toàn khi danh sách chứa **Person null** không?

**Đáp án:** Không. Nó bảo vệ khóa name null, không bảo vệ object Person null. Cần lớp `Comparator.nullsFirst/Last(...)` bên ngoài.

**Câu 6.** Muốn sắp số giảm dần nhưng null vẫn cuối, chọn `nullsLast(reverseOrder())` hay `nullsLast(naturalOrder()).reversed()`?

**Đáp án:** Chọn `nullsLast(reverseOrder())`. Dạng `reversed()` ngoài đảo cả vị trí null.

**Câu 7.** Vì sao `TreeSet` có thể chỉ giữ một chuỗi non-null khi dùng `nullsFirst(null)`?

**Đáp án:** Vì comparator trả 0 cho mọi cặp chuỗi non-null, nên TreeSet xem chúng là trùng khóa thứ tự.

**Câu 8.** Một object có `Integer age == null`; có nên dùng `comparingInt(Person::age)`?

**Đáp án:** Không, nếu age nullable. Autounboxing có thể ném NPE; nên dùng `comparing(Person::age, nullsLast(naturalOrder()))`.

**Câu 9.** `filter(Objects::nonNull)` và `nullsLast(...)` có cùng ý nghĩa không?

**Đáp án:** Không. `filter` loại phần tử null khỏi kết quả; `nullsLast` giữ lại nhưng đặt cuối.

**Câu 10.** `List.sort` có giữ thứ tự tương đối của hai phần tử khi comparator trả 0 không?

**Đáp án:** Có, `List.sort` là phép sort stable. Tuy nhiên nếu cần thứ tự nghiệp vụ cho hai phần tử, nên dùng `thenComparing`.

**Câu 11.** Nếu source là `List.of("A", "B")`, có thể sort trực tiếp bằng `list.sort(cmp)` không?

**Đáp án:** `List.of` trả danh sách không chỉnh sửa được; sort có thể ném `UnsupportedOperationException`. Tạo `new ArrayList<>(list)` trước nếu cần sửa thứ tự.

**Câu 12.** Chính sách null nên nằm trong comparator hay validation?

**Đáp án:** Tùy yêu cầu. Nếu null hợp lệ và cần vị trí hiển thị, dùng comparator. Nếu null vi phạm dữ liệu đầu vào, dùng validation; comparator không thay thế quy tắc hợp lệ của dữ liệu.

## 17. Tham khảo tài liệu Java hiện hành

- [Oracle Java SE 25 — Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html): contract `compare`, `nullsFirst`, `nullsLast`, `naturalOrder`, `reverseOrder`, `comparing`, `thenComparing` và `reversed`.
- [Oracle Java SE 25 — List](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): `List.sort`, tính ổn định của sắp xếp và các thao tác cập nhật danh sách.
- [Oracle Java SE 25 — Stream](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html): `sorted(Comparator)`, lazy pipeline và bảo đảm thứ tự cho ordered stream.
- [Oracle Java SE 25 — TreeSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html): ngữ nghĩa uniqueness theo ordering và yêu cầu tương thích với `equals`.
- [Oracle Java SE 25 — TreeMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html): comparator và khả năng xử lý khóa null khi comparator cho phép.

**Ghi nhớ:** `nullsFirst`/`nullsLast` chỉ định rõ **vị trí null** trong thứ tự, còn comparator con quy định **thứ tự non-null**. Đặt wrapper đúng tầng (đối tượng hay khóa), cẩn thận khi `reversed()`, không dùng `nullsFirst(null)` nhầm với natural order, và luôn chọn chính sách null dựa trên nghiệp vụ trước khi sort.