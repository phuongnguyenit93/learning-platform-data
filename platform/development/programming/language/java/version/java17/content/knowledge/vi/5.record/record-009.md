# Record cục bộ, record lồng nhau và ngữ cảnh `static` trong Java 17

Trong Java 17, `record` là một dạng khai báo lớp phù hợp để biểu diễn một nhóm giá trị có cấu trúc rõ ràng. Bên cạnh `record` ở mức cao nhất của tệp nguồn (*top-level record*), bạn có thể khai báo **record cục bộ** (*local record*) ngay trong một khối lệnh và **record lồng nhau** (*nested/member record*) bên trong một lớp hoặc interface.

Điểm cần hiểu rõ là: **record cục bộ và record thành viên đều ngầm định mang tính `static`**. Vì vậy, chúng khác một lớp nội bộ thông thường (*inner class*) ở cách truy cập biến cục bộ, trạng thái của đối tượng bao ngoài và tham số kiểu generic.

Bài học sử dụng cú pháp ổn định của **Java 17**, giải thích phạm vi, khả năng truy cập, các lỗi biên dịch hay gặp và cách chọn vị trí khai báo record khi thiết kế mã nguồn.

## 1. Nhắc lại: một `record` cung cấp những gì?

Ví dụ:

```java
public record Point(int x, int y) {
}
```

Khai báo này có **hai record component** là `x` và `y`. Java tự cung cấp các thành phần cơ bản:

- Các trường thành viên tương ứng, có tính chất `private final`.
- Constructor chuẩn (*canonical constructor*) nhận giá trị cho các component.
- Hai phương thức đọc dữ liệu `x()` và `y()`, gọi là **accessor**.
- Các phương thức `equals(Object)`, `hashCode()` và `toString()` dựa trên trạng thái của các component.

Ví dụ:

```java
Point point = new Point(3, 7);
System.out.println(point.x());            // 3
System.out.println(point.y());            // 7
System.out.println(point);                // Point[x=3, y=7]
System.out.println(point.equals(new Point(3, 7))); // true
```

`record` được chuẩn hóa từ Java 16 (JEP 395) và có thể sử dụng trực tiếp trong Java 17 mà không cần bật preview.

Record là **lớp** với các ràng buộc của ngôn ngữ: nó ngầm định `final`, kế thừa `java.lang.Record` và không thể kế thừa một lớp tùy ý khác. Record có thể triển khai interface, viết thêm phương thức, constructor bổ sung hợp lệ và khai báo thành viên `static`.

Record không đồng nghĩa với “đối tượng bất biến sâu”: nếu một component chứa đối tượng có thể thay đổi, ví dụ một `List` có khả năng sửa phần tử, record không tự sao chép hoặc khóa danh sách đó. Người thiết kế cần bảo vệ dữ liệu bằng các biện pháp phù hợp như `List.copyOf(...)` khi cần.

## 2. Ba vị trí khai báo record trong Java 17

| Vị trí | Ví dụ cú pháp | Phạm vi truy cập theo tên | Đặc điểm đáng nhớ |
| --- | --- | --- | --- |
| **Top-level record** | `record Point(int x, int y) {}` ở mức ngoài cùng | Theo package và modifier truy cập của kiểu | Có thể dùng như một kiểu dữ liệu độc lập. |
| **Member/nested record** | `class Geometry { record Point(int x, int y) {} }` | Theo phạm vi và quyền truy cập của kiểu bao ngoài/thành viên | **Ngầm định `static`**, không gắn với từng instance `Geometry`. |
| **Local record** | `void run() { record Point(int x, int y) {} }` | Trong khối lệnh nơi khai báo, sau vị trí khai báo | **Ngầm định `static`**, không capture biến của phương thức hoặc instance bao ngoài. |

Hình dung cấu trúc:

```text
Point.java
└── record Point(...)              ← top-level

Geometry.java
└── class Geometry
    ├── record Point(...)          ← nested/member record
    └── void inspect()
        └── record LocalPoint(...) ← local record
```

Từ khóa `static` ở đây nói về **quan hệ với ngữ cảnh khai báo bao ngoài**. Nó **không có nghĩa** bản thân record chỉ có một instance duy nhất, tất cả component là biến tĩnh, hoặc các instance phải dùng chung giá trị.

Mỗi lần gọi `new Point(1, 2)` vẫn tạo ra một instance record với các giá trị component của riêng nó.

## 3. Record cục bộ: khai báo kiểu ngay trong khối lệnh

**Local record** là record được khai báo trong một khối mã, chẳng hạn thân phương thức. Kiểu record đó phục vụ một xử lý cụ thể và không cần xuất hiện trong API của lớp bao ngoài.

### 3.1. Ví dụ hoàn chỉnh: giữ dữ liệu trung gian ở phạm vi nhỏ

Tạo tệp **`LocalRecordDemo.java`**:

```java
import java.util.List;

public class LocalRecordDemo {
    static void printMeasurements() {
        // Kiểu này chỉ có tên và phạm vi sử dụng trong phương thức.
        record Measurement(String sensor, int value) {
            Measurement {
                if (sensor == null || sensor.isBlank()) {
                    throw new IllegalArgumentException("sensor must not be blank");
                }
            }

            boolean isAbove(int threshold) {
                return value > threshold;
            }
        }

        List<Measurement> values = List.of(
                new Measurement("A", 17),
                new Measurement("B", 25));

        for (Measurement measurement : values) {
            System.out.println(measurement.sensor() + ": "
                    + measurement.isAbove(20));
        }
    }

    public static void main(String[] args) {
        printMeasurements();
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 LocalRecordDemo.java
java LocalRecordDemo
```

Kết quả:

```text
A: false
B: true
```

Trong ví dụ:

1. `Measurement` chỉ cần thiết để biểu diễn từng phép đo trong `printMeasurements()`.
2. Compiler sinh accessor `sensor()`, `value()`, cùng `equals`, `hashCode` và `toString` cho `Measurement`.
3. Constructor ngắn gọn `Measurement { ... }` là **compact canonical constructor**, dùng để kiểm tra điều kiện dữ liệu trước khi record hoàn tất khởi tạo.
4. Phương thức `isAbove(int threshold)` là một **hành vi của chính record**, không phải hàm static; nó dùng component `value` của instance hiện tại.
5. Sau khi kết thúc khối chứa khai báo, không thể gọi kiểu `Measurement` bằng tên từ phương thức khác như một kiểu dùng chung.

Đặt record gần nơi dùng làm rõ rằng đây là **cấu trúc dữ liệu trung gian**, không phải hợp đồng công khai của toàn bộ hệ thống.

### 3.2. Phạm vi của tên record cục bộ

Ví dụ:

```java
public class ScopeDemo {
    static void first() {
        record Pair(int left, int right) {}

        Pair pair = new Pair(2, 5);
        System.out.println(pair.left() + pair.right());
    }

    static void second() {
        // Pair pair = new Pair(4, 6); // KHÔNG BIÊN DỊCH:
        // Pair là kiểu cục bộ của first(), không hiện diện tại đây.
    }
}
```

Khai báo record cục bộ có hiệu lực trong phạm vi khối lệnh thích hợp kể từ khai báo; không xuất hiện như một member type mà mọi phương thức của lớp đều nhìn thấy.

Vì vậy, **không nên dùng local record nếu nhiều phương thức cần cùng một kiểu dữ liệu**. Khi đó, nested record hoặc top-level record thường rõ ràng hơn.

### 3.3. Có thể khai báo local record trong những ngữ cảnh nào?

Một local record có thể xuất hiện trong khối lệnh của:

- Phương thức instance hoặc phương thức `static`.
- Constructor.
- Khối khởi tạo hợp lệ của lớp.
- Một khối lệnh lồng bên trong phương thức, ví dụ thân một nhánh hoặc vòng lặp.

Việc nằm bên trong một **phương thức instance** không biến local record thành một inner class gắn với `this`. Tính `static` ngầm định của local record vẫn giữ nguyên.

## 4. Vì sao local record không capture biến cục bộ?

Đây là khác biệt quan trọng giữa **local class thông thường** và **local record**.

Một lớp cục bộ thông thường có thể sử dụng biến bên ngoài nếu biến đó là `final` hoặc *effectively final*:

```java
public class CaptureDemo {
    static void run() {
        int threshold = 10; // effectively final

        class Checker {
            boolean passes(int value) {
                return value >= threshold; // Hợp lệ với local class.
            }
        }

        System.out.println(new Checker().passes(12));
    }
}
```

Ngược lại, **local record không được capture biến của phương thức hoặc khối bao ngoài**:

```java
public class InvalidLocalRecord {
    static void run() {
        int threshold = 10;

        record Score(int value) {
            boolean passes() {
                return value >= threshold; // LỖI BIÊN DỊCH.
            }
        }
    }
}
```

Ngay cả khi `threshold` là `final` hoặc effectively final, local record vẫn không được dùng nó theo cách trên. Lý do: local record **ngầm định `static`**, nên không có cơ chế mang theo môi trường biến cục bộ như một local inner class.

### 4.1. Cách đúng: truyền dữ liệu cần thiết vào record

Bạn có thể chuyển biến phụ thuộc thành một **record component**:

```java
public class LocalRecordFixed {
    static void run() {
        int threshold = 10;

        record Score(int value, int limit) {
            boolean passes() {
                return value >= limit;
            }
        }

        Score score = new Score(12, threshold);
        System.out.println(score.passes()); // true
    }

    public static void main(String[] args) {
        run();
    }
}
```

Hoặc truyền tham số cho phương thức thay vì lưu threshold trong mỗi record:

```java
static void process(int threshold) {
    record Score(int value) {
        boolean passes(int limit) {
            return value >= limit;
        }
    }

    Score score = new Score(12);
    System.out.println(score.passes(threshold));
}
```

Hai cách thể hiện hai ý nghĩa khác nhau:

- `limit` là **một phần dữ liệu của kết quả**: đặt trong component của `Score`.
- `limit` là **tham số của phép đánh giá tại thời điểm gọi**: truyền vào `passes(limit)`.

Đừng thêm component chỉ để lách lỗi biên dịch nếu giá trị đó thực tế không phải dữ liệu của đối tượng.

## 5. Record cục bộ và trạng thái instance của lớp bao ngoài

Local record khai báo trong phương thức instance **không có tham chiếu bao ngoài ngầm định (`Outer.this`)**.

Ví dụ không hợp lệ:

```java
public class InstanceCaptureDemo {
    private final String prefix = "MEASURE-";

    void report() {
        record Result(int value) {
            String label() {
                return prefix + value; // LỖI: truy cập instance field bao ngoài.
            }
        }
    }
}
```

Để sử dụng `prefix`, bạn có thể:

**Cách 1 — Truyền giá trị vào component nếu thuộc trạng thái record:**

```java
public class InstanceValueDemo {
    private final String prefix = "MEASURE-";

    void report() {
        record Result(String prefix, int value) {
            String label() {
                return prefix + value;
            }
        }

        Result result = new Result(prefix, 42);
        System.out.println(result.label()); // MEASURE-42
    }
}
```

**Cách 2 — Giữ định dạng ở phương thức bao ngoài nếu record chỉ cần mang dữ liệu:**

```java
public class InstanceFormatterDemo {
    private final String prefix = "MEASURE-";

    void report() {
        record Result(int value) {}

        Result result = new Result(42);
        System.out.println(prefix + result.value()); // MEASURE-42
    }
}
```

Cách thứ hai thường phù hợp nếu `prefix` là cấu hình của dịch vụ trình bày, còn `Result` chỉ cần lưu giá trị kết quả.

### 5.1. Có thể truy cập thành viên `static` của kiểu bao ngoài

Không capture instance **không đồng nghĩa với cấm dùng mọi thành viên bên ngoài**. Một local record có thể tham chiếu các thành viên `static` truy cập được theo quy tắc thông thường.

```java
public class StaticMemberAccess {
    private static final int MINIMUM = 18;

    static void evaluate() {
        record Applicant(int age) {
            boolean eligible() {
                return age >= MINIMUM;
            }
        }

        System.out.println(new Applicant(20).eligible()); // true
    }
}
```

`MINIMUM` là thành viên `static` của lớp bao ngoài. Đây là một phụ thuộc vào giá trị tĩnh có thể truy cập được, **khác với việc capture một biến cục bộ `final` của phương thức**.

## 6. Nested record: record là thành viên của lớp hoặc interface

**Nested/member record** được khai báo ở thân một lớp hoặc interface. Record đó tồn tại như một **kiểu thành viên có tên** và có thể được dùng từ nhiều phương thức ở những nơi có quyền truy cập thích hợp.

Ví dụ tạo tệp **`OrderReport.java`**:

```java
import java.util.List;

public class OrderReport {
    private static final String CURRENCY = "VND";

    public record Line(String productCode, int quantity, long unitPrice) {
        public Line {
            if (productCode == null || productCode.isBlank()) {
                throw new IllegalArgumentException("productCode is required");
            }
            if (quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("invalid quantity or price");
            }
        }

        public long lineTotal() {
            return Math.multiplyExact(quantity, unitPrice);
        }

        public String displayTotal() {
            return lineTotal() + " " + CURRENCY;
        }
    }

    public static void main(String[] args) {
        List<Line> lines = List.of(
                new OrderReport.Line("P-17", 2, 50_000),
                new OrderReport.Line("P-21", 1, 30_000));

        for (Line line : lines) {
            System.out.println(line.productCode() + ": " + line.displayTotal());
        }
    }
}
```

Chạy:

```bash
javac --release 17 OrderReport.java
java OrderReport
```

Đầu ra:

```text
P-17: 100000 VND
P-21: 30000 VND
```

Các điểm đáng chú ý:

1. `Line` được khai báo **bên trong `OrderReport`**, nên tên đầy đủ khi tham chiếu từ nơi khác là `OrderReport.Line`.
2. `Line` **ngầm định `static`**. Tạo `new OrderReport.Line(...)` không đòi hỏi tạo một đối tượng `new OrderReport()`.
3. `Line` có thể truy cập `CURRENCY` là một thành viên `static` của `OrderReport`.
4. `Line` có constructor kiểm tra dữ liệu và có thể thêm các phương thức instance như `lineTotal()`.
5. `public` cho phép kiểu `Line` được truy cập ở những nơi có quyền truy cập lớp bao ngoài; bạn có thể dùng `private` hoặc quyền khác tùy mục đích thiết kế.

**Không bắt buộc** viết từ khóa `static` trước một member record: record thành viên đã mặc định mang tính static.

## 7. Nested record không gắn với instance của lớp bao ngoài

Hãy so sánh hai khai báo trong cùng lớp:

```java
public class Container {
    private final int offset;

    public Container(int offset) {
        this.offset = offset;
    }

    public class InnerCounter {
        public int add(int value) {
            return offset + value;
        }
    }

    public record Snapshot(int value) {
    }
}
```

Khởi tạo:

```java
Container container = new Container(10);

Container.InnerCounter counter = container.new InnerCounter();
System.out.println(counter.add(5)); // 15

Container.Snapshot snapshot = new Container.Snapshot(5);
System.out.println(snapshot.value()); // 5
```

**`InnerCounter`** là một *non-static inner class*, nên instance của nó gắn với một `Container` và truy cập được `offset`.

**`Snapshot`** là member record, ngầm định static, **không có instance `Container` bao ngoài**. Vì vậy, code sau không hợp lệ:

```java
public class InvalidOuterAccess {
    private int offset = 10;

    record Snapshot(int value) {
        int total() {
            return value + offset; // LỖI BIÊN DỊCH.
        }
    }
}
```

Nếu tổng thật sự cần offset, hãy truyền nó vào component hoặc phương thức:

```java
public class ValidOuterAccess {
    private int offset = 10;

    record Snapshot(int value) {
        int totalWith(int offset) {
            return value + offset;
        }
    }

    void show() {
        Snapshot snapshot = new Snapshot(5);
        System.out.println(snapshot.totalWith(offset)); // 15
    }
}
```

Quy tắc này áp dụng cho **cả local record lẫn member record**: đặt tên bên trong một lớp không tự động tạo liên kết đến trạng thái của instance lớp đó.

## 8. Nested record trong interface và trong một inner class

### 8.1. Record lồng trong interface

Một interface có thể khai báo member record. Điều này hữu ích khi gom các dạng dữ liệu kết quả hoặc thông điệp vào một không gian tên có chung ý nghĩa.

```java
public sealed interface OperationResult
        permits OperationResult.Success, OperationResult.Failure {

    record Success(String message) implements OperationResult {
    }

    record Failure(int code, String reason) implements OperationResult {
    }
}
```

Sử dụng:

```java
OperationResult result = new OperationResult.Success("Saved");
System.out.println(result);
```

Hai record thành viên trong interface **ngầm định `public static`** theo quy tắc member type của interface. Bạn có thể tham chiếu `OperationResult.Success` mà không cần instance của `OperationResult`.

Điều này còn kết hợp được với `sealed interface`: chỉ các kiểu được cho phép mới trực tiếp triển khai interface.

### 8.2. Record lồng trong non-static inner class vẫn hợp lệ ở Java 17

Ví dụ:

```java
public class Dashboard {
    public class Panel {
        public record Coordinate(int x, int y) {
        }
    }
}
```

Đây là cú pháp hợp lệ ở Java 17: `Coordinate` là **record thành viên, ngầm định static**, dù `Panel` là non-static inner class.

Sự khác biệt thường khiến người học nhầm là: trong các phiên bản Java rất cũ, việc khai báo static member trong inner class từng chịu các hạn chế khác. Với Java 17, các hạn chế đã được điều chỉnh để cho phép những member type static như nested record. Không nên áp dụng máy móc các quy tắc cũ khi học Java 17.

Không cần giữ một instance `Dashboard` hoặc `Panel` để dữ liệu `Coordinate` tồn tại như một kiểu. Mặc dù tên `Dashboard.Panel.Coordinate` có nhiều cấp, tên dài **không** biểu thị chuỗi tham chiếu instance lồng nhau.

## 9. Ngữ cảnh static và tham số kiểu generic

Một vấn đề tương tự biến instance xảy ra với **tham số kiểu generic của lớp/phương thức bao ngoài**.

### 9.1. Nested record không lấy được type parameter của lớp bao ngoài

Ví dụ **không biên dịch**:

```java
public class GenericBox<T> {
    record Item(T value) {  // LỖI: T của GenericBox thuộc ngữ cảnh bao ngoài.
    }
}
```

`Item` ngầm định static, vì vậy không được sử dụng trực tiếp tham số kiểu `T` thuộc instance generic `GenericBox<T>`.

Giải pháp là cho record **tham số kiểu riêng**:

```java
public class GenericBox<T> {
    record Item<U>(U value) {
    }

    void show(T value) {
        Item<T> item = new Item<>(value);
        System.out.println(item.value());
    }
}
```

`U` thuộc khai báo `Item<U>` và hoàn toàn hợp lệ. `T` được truyền qua cách sử dụng `Item<T>` trong phương thức `show`, thay vì được record capture ở định nghĩa thành viên.

### 9.2. Local record không lấy được type parameter của phương thức bao ngoài

Ví dụ cũng không hợp lệ:

```java
public class LocalGenericDemo {
    static <T> void print(T value) {
        record Holder(T item) { // LỖI: local record không capture T.
        }
    }
}
```

Sửa bằng cách khai báo type parameter của riêng record:

```java
public class LocalGenericDemo {
    static <T> void print(T value) {
        record Holder<U>(U item) {
        }

        Holder<T> holder = new Holder<>(value);
        System.out.println(holder.item());
    }

    public static void main(String[] args) {
        print("Java 17");
        print(17);
    }
}
```

Như vậy, **`record` có thể là generic**, nhưng local/member record không được tham chiếu tùy ý đến type parameter của ngữ cảnh bao ngoài như một inner class gắn với ngữ cảnh đó.

## 10. `static` có nghĩa gì đối với component và method của record?

Không nên nhầm **record ngầm định static so với lớp bao ngoài** với việc toàn bộ thành viên bên trong record đều static.

Xét:

```java
public class RecordMembersDemo {
    record Reading(int value) {
        private static final String UNIT = "ms";

        String display() {
            return value + " " + UNIT;
        }

        static Reading zero() {
            return new Reading(0);
        }
    }

    public static void main(String[] args) {
        Reading first = new Reading(12);
        Reading second = Reading.zero();

        System.out.println(first.display());  // 12 ms
        System.out.println(second.display()); // 0 ms
    }
}
```

Ở đây:

- `Reading` là **member record ngầm định static**.
- `value` là trạng thái **của từng instance**, đọc qua `first.value()` hoặc `second.value()`.
- `display()` là **instance method**, hoạt động theo giá trị của đối tượng hiện tại.
- `UNIT` là **static field** dùng chung, hợp lệ vì đó là trường `static`.
- `zero()` là **static factory method**, có thể tạo và trả về instance của `Reading`.

Một record **không được tự khai báo thêm instance field** ngoài những trường tương ứng với record component:

```java
record InvalidReading(int value) {
    // private int extra; // LỖI: instance field bổ sung không được phép.
}
```

Nếu `extra` thực sự thuộc trạng thái dữ liệu, hãy đưa nó thành một record component. Nếu là giá trị chung không phụ thuộc instance, có thể cân nhắc một hằng số `static final`.

## 11. Bảng đối chiếu: local class, local record và member record

| Đặc điểm | Local class thông thường | Local record | Member/nested record |
| --- | --- | --- | --- |
| Khai báo bên trong phương thức/khối | Có | Có | Không, khai báo ở mức thành viên kiểu bao ngoài |
| Ngầm định static | Không | **Có** | **Có** |
| Capture biến cục bộ final/effectively final | **Có thể** | **Không** | Không có phạm vi biến cục bộ để capture |
| Truy cập instance bao ngoài theo quan hệ inner class | Có thể ở ngữ cảnh thích hợp | **Không** | **Không** |
| Truy cập thành viên static bao ngoài | Có, nếu truy cập được | Có, nếu truy cập được | Có, nếu truy cập được |
| Có sẵn accessor, `equals`, `hashCode`, `toString` dựa trên component | Không tự động | Có | Có |
| Định nghĩa lại kiểu để dùng ở phương thức khác | Không trực tiếp | Không trực tiếp | Có, theo phạm vi truy cập |
| Dùng cho cấu trúc dữ liệu phục vụ một thuật toán riêng | Có thể | **Phù hợp** | Có thể, nhưng phạm vi rộng hơn |
| Dùng làm kiểu dữ liệu chia sẻ giữa các phương thức | Không phù hợp | Không phù hợp | **Phù hợp** |

Điểm mấu chốt là **phạm vi sống của tên kiểu** và **quan hệ với ngữ cảnh bao ngoài**, không phải việc bạn có phải thêm từ khóa `static` khi viết khai báo hay không.

## 12. Ví dụ thực tế: local record cho bước tính, nested record cho dữ liệu kết quả

Giả sử một chức năng cần tính tổng số lượng sản phẩm trong đơn hàng. Dữ liệu đầu vào và kết quả có thể dùng ở nhiều nơi nên đặt chúng thành **member record**. Một cấu trúc phụ giúp chuẩn hóa từng dòng chỉ phục vụ thuật toán nên khai báo **local record**.

Tạo tệp **`OrderSummaryDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class OrderSummaryDemo {
    public record Order(String id, List<Integer> quantities) {
        public Order {
            Objects.requireNonNull(id, "id");
            quantities = List.copyOf(quantities);
        }
    }

    public record Summary(
            String orderId,
            int lineCount,
            int totalUnits) {
    }

    public static Summary summarize(Order order) {
        Objects.requireNonNull(order, "order");

        // Dùng riêng ở bước duyệt từng dòng hàng.
        record IndexedQuantity(int index, int quantity) {
            IndexedQuantity {
                if (quantity <= 0) {
                    throw new IllegalArgumentException(
                            "Invalid quantity at line " + index);
                }
            }
        }

        int total = 0;
        for (int i = 0; i < order.quantities().size(); i++) {
            IndexedQuantity line =
                    new IndexedQuantity(i, order.quantities().get(i));
            total = Math.addExact(total, line.quantity());
        }

        return new Summary(order.id(), order.quantities().size(), total);
    }

    public static void main(String[] args) {
        Order order = new Order("OD-17", List.of(2, 3, 1));
        Summary summary = summarize(order);

        System.out.println(summary);
    }
}
```

Thực hiện:

```bash
javac --release 17 OrderSummaryDemo.java
java OrderSummaryDemo
```

Kết quả:

```text
Summary[orderId=OD-17, lineCount=3, totalUnits=6]
```

Phân tích vai trò:

1. **`Order`** là dữ liệu đầu vào có khả năng tái sử dụng, nên là member record. Canonical constructor sao chép danh sách bằng `List.copyOf` để tránh việc sửa từ bên ngoài thông qua danh sách đã truyền.
2. **`Summary`** là kiểu kết quả mà caller có thể dùng để lấy `totalUnits()` hoặc `lineCount()`, nên cũng là member record.
3. **`IndexedQuantity`** chỉ giúp ràng buộc và gọi tên dữ liệu từng dòng bên trong `summarize`, không cần trở thành kiểu công khai.
4. Local record **nhận trực tiếp** `index` và `quantity` qua constructor; nó không cần capture biến `i` hoặc `order` của phương thức.
5. `Math.addExact` phát hiện tràn số nguyên thay vì trả một giá trị tổng sai âm thầm; đây là lựa chọn minh họa cách kiểm soát ràng buộc tính toán.

Nếu sau này `IndexedQuantity` được dùng ở nhiều phương thức, bạn có thể chuyển nó thành **member record** với mức truy cập phù hợp mà không thay đổi ý nghĩa cơ bản của các component.

## 13. Chọn vị trí đặt record thế nào?

| Câu hỏi thiết kế | Vị trí thường phù hợp | Lý do |
| --- | --- | --- |
| Cấu trúc chỉ giúp xử lý trong một phương thức? | **Local record** | Giới hạn phạm vi, tránh xuất hiện trong API rộng hơn. |
| Nhiều phương thức của cùng một lớp cần một loại dữ liệu phụ? | **`private` member record** | Chia sẻ trong lớp nhưng vẫn giữ chi tiết triển khai kín. |
| Kiểu là một phần API của lớp/module? | **Member record có mức truy cập phù hợp** hoặc top-level record | Cho caller đặt tên và sử dụng loại dữ liệu rõ ràng. |
| Kiểu đại diện dữ liệu miền dùng rộng khắp package/module? | **Top-level record** | Tránh phụ thuộc tên lớp bao ngoài nếu không có mối quan hệ thực sự. |
| Dữ liệu cần giá trị cấu hình của service bao ngoài? | **Truyền giá trị rõ ràng hoặc giữ xử lý ở service** | Không giả định record capture được `this`. |
| Kiểu cần thêm generic parameter? | **Khai báo type parameter riêng cho record** | Record local/member không dùng được type parameter bao ngoài theo kiểu capture. |
| Cần một đối tượng có bản sắc thay đổi, nhiều trường có thể gán lại? | **Class thông thường** | Record phù hợp hơn với biểu diễn trạng thái dữ liệu cố định theo component. |

Việc lồng record vào một lớp chỉ vì “muốn dùng ở cùng file” chưa đủ là lý do thiết kế. Hãy hỏi kiểu đó có thực sự thuộc phạm vi của lớp bao ngoài hay không.

Ngược lại, dùng top-level record cho mọi cấu trúc tạm cũng khiến namespace bị phân tán và khó nhận ra record nào chỉ là chi tiết xử lý.

## 14. Những lỗi phổ biến trong Java 17

### 14.1. Nhầm local record với local inner class

Sai:

```java
void calculate() {
    int extra = 5;
    record Value(int amount) {
        int total() {
            return amount + extra; // Không capture được extra.
        }
    }
}
```

Sửa: chuyển `extra` thành component hoặc tham số của `total(...)`.

### 14.2. Nhầm member record với inner class cần instance bao ngoài

Sai:

```java
class Outer {
    record Data(int id) {}
}

// Outer outer = new Outer();
// Outer.Data value = outer.new Data(1); // Sai cú pháp khởi tạo.
```

Đúng:

```java
Outer.Data value = new Outer.Data(1);
```

### 14.3. Nghĩ `static` làm component thành biến dùng chung

Hai instance `new Outer.Data(1)` và `new Outer.Data(2)` có giá trị `id` khác nhau. Ngầm định static chỉ mô tả **cách kiểu dữ liệu được lồng**, không biến `id` thành static field.

### 14.4. Tham chiếu generic type parameter của lớp bao ngoài

Sai:

```java
class Container<T> {
    record Entry(T data) {} // Không hợp lệ.
}
```

Đúng:

```java
class Container<T> {
    record Entry<U>(U data) {}
}
```

### 14.5. Cố truy cập local record từ phương thức khác

Local record không thể được dùng làm kiểu tham số/trả về ở khai báo phương thức khác nằm ngoài phạm vi của nó. Nếu cần một hợp đồng như `Summary summarize(Order input)` có thể gọi từ các nơi khác, hãy khai báo `Summary` là member record hoặc top-level record.

### 14.6. Thêm access modifier vào local record

Khai báo cục bộ không phải khai báo member; không được thêm `private`, `protected` hoặc `public` để cố điều chỉnh phạm vi của record.

Không hợp lệ:

```java
void run() {
    // private record Pair(int x, int y) {} // LỖI.
}
```

Nếu cần điều khiển quyền truy cập ở phạm vi lớp, hãy chuyển kiểu thành member record rồi chọn modifier phù hợp.

### 14.7. Coi record là bất biến sâu

```java
record Tags(List<String> names) {}
```

Trường tham chiếu `names` là `final`, nhưng danh sách được truyền vào có thể là một `ArrayList` thay đổi được. Nếu yêu cầu snapshot bất biến, sao chép khi khởi tạo:

```java
record Tags(List<String> names) {
    Tags {
        names = List.copyOf(names);
    }
}
```

`List.copyOf` tạo danh sách không cho phép sửa bằng các thao tác thông thường. Với component chứa đối tượng có trạng thái mutable bên trong, còn cần xem xét mức bảo vệ sâu hơn theo nhu cầu.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao `record` khai báo trong một phương thức instance vẫn không truy cập được field instance bao ngoài?**  
Vì local record ngầm định static và không có tham chiếu `Outer.this`. Nếu cần dữ liệu, hãy truyền rõ ràng qua constructor hoặc phương thức.

**2. Local record có capture biến local `final` giống local class không?**  
Không. Local record không capture biến trong khối bao ngoài, kể cả khi biến đó `final` hoặc effectively final.

**3. Một member record trong lớp có cần viết từ khóa `static` mới khởi tạo được bằng `new Outer.Record(...)` không?**  
Không. Member record vốn ngầm định static.

**4. Có được đặt record trong interface không?**  
Có. Member record trong interface ngầm định `public static`.

**5. Có được đặt record trong một non-static inner class ở Java 17 không?**  
Có. Record thành viên vẫn ngầm định static và không gắn với instance của inner class chứa nó.

**6. Vì sao `class Box<T> { record Item(T value) {} }` không hợp lệ?**  
Vì member record static không sử dụng trực tiếp type parameter thuộc instance của `Box<T>`. Có thể sửa thành `record Item<U>(U value) {}`.

**7. Khi nào nên nâng local record thành nested record?**  
Khi nhiều phương thức hoặc một hợp đồng API cần nhắc tới chính kiểu đó bằng tên và chia sẻ cấu trúc dữ liệu của nó.

**8. Một local record có thể có instance method dùng component không?**  
Có. Ví dụ `record Pair(int a, int b) { int sum() { return a + b; } }` hoàn toàn hợp lệ; ngầm định static so với kiểu bao ngoài không biến mọi method của record thành static.

## Tài liệu tham khảo

- [JEP 395 — Records](https://openjdk.org/jeps/395): records trong Java, bao gồm local records và việc member records ngầm định static.
- [Java Language Specification — Java SE 17, `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record components, constructor, member/local record và các ràng buộc.
- [Java Language Specification — Java SE 17, `8.1.3 Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): quan hệ instance bao ngoài, khác biệt giữa inner class và nested static class.
- [Java Language Specification — Java SE 17, `14.3 Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3): phạm vi và quy tắc khai báo kiểu cục bộ.
- [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): lớp cơ sở của record.
