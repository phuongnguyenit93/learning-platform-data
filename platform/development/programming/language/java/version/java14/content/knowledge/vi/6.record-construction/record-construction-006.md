# Constructor bổ sung và ủy quyền tới canonical constructor trong Java record

## 1. Mục tiêu và phiên bản Java

Một **record** khai báo tập hợp dữ liệu bằng *record components* và có một **canonical constructor** (constructor chuẩn) chịu trách nhiệm khởi tạo đúng các thành phần đó. Ta vẫn có thể khai báo **constructor bổ sung** (*additional/overloaded/non-canonical constructor*) để tạo đối tượng bằng ít tham số hơn, nhận đầu vào ở định dạng khác hoặc cung cấp giá trị mặc định. Quy tắc then chốt: **mọi constructor không phải canonical trong một record phải gọi một constructor khác của chính record bằng `this(...)`, trực tiếp hoặc qua một chuỗi ủy quyền dẫn tới canonical constructor.** Nó không được tự khởi tạo các trường component để bỏ qua canonical constructor.

**Bối cảnh Java 14:** record được giới thiệu ở dạng *preview* trong Java 14 (JEP 359), tiếp tục hoàn thiện và **trở thành tính năng chính thức từ Java 16** (JEP 395). Mọi ví dụ chính dưới đây dùng **cú pháp ổn định của Java 17+** và có thể chạy trên JDK hiện đại mà không cần `--enable-preview`. Bài cũng lưu ý quy tắc **Flexible Constructor Bodies** đã được chuẩn hóa trong **Java 25** (JEP 513), vì tài liệu hiện đại không nên khẳng định sai rằng `this(...)` luôn phải là lệnh đầu tiên trong *mọi* phiên bản Java.

Sau bài học, bạn có thể:

- Phân biệt canonical constructor (ngầm định, khai báo đầy đủ, compact) với non-canonical constructor.
- Thiết kế các overload gọi `this(...)` theo chuỗi, duy trì chung một nơi kiểm tra và chuẩn hóa dữ liệu.
- Biết vị trí được phép xử lý tham số trước/sau `this(...)` theo phiên bản Java.
- Tránh các lỗi biên dịch do tự gán component field, gọi `super(...)`, đệ quy constructor hoặc khai báo trùng canonical constructor.
- Chọn giữa overloaded constructor và static factory method khi API có nhiều kiểu đầu vào.

## 2. Tại sao record luôn cần canonical constructor?

Xét khai báo ngắn nhất:

```java
record Coordinate(int x, int y) { }
```

Hai component `x` và `y` xác định trạng thái mà record phải mang. Compiler cung cấp các thành phần cần thiết, trong đó có một canonical constructor tương ứng với **chữ ký `Coordinate(int x, int y)`** và các accessor `x()`, `y()`. Khi gọi `new Coordinate(3, 4)`, canonical constructor khởi tạo các component field `private final` theo thứ tự từ header.

Record có thể có **một canonical constructor**, do compiler tạo hoặc do lập trình viên tự khai báo. Nếu lập trình viên tự khai báo canonical constructor, compiler không tạo thêm một canonical constructor khác. Khi muốn kiểm tra input hoặc chuẩn hóa dữ liệu, hãy thực hiện trong canonical constructor để **mọi đường khởi tạo đều nhất quán**.

Có ba cách xuất hiện canonical constructor:

| Cách | Ví dụ ngắn | Ai khởi tạo component fields? |
| --- | --- | --- |
| **Ngầm định** | `record Point(int x, int y) {}` | Compiler |
| **Compact canonical** | `Point { if (x < 0) throw ...; }` | Compiler tự gán sau khi thân compact constructor hoàn tất bình thường |
| **Normal canonical khai báo đầy đủ** | `Point(int x, int y) { this.x = x; this.y = y; }` | Lập trình viên gán từng component field trong thân constructor |

**Điểm phân biệt:** constructor có tên và danh sách tham số khớp các component (về kiểu và thứ tự, kèm tên tham số đúng theo quy tắc canonical) là canonical constructor, kể cả khi bạn không gọi nó bằng tên “canonical”. Một overload như `Point(int x)` hoặc `Point()` là **non-canonical constructor**; nó có quy tắc riêng về ủy quyền.

Record không có *default no-arg constructor* tự động như lớp thường khi không khai báo constructor. Với record có hai component, muốn gọi `new Point()` thì **phải tự khai báo** overload không tham số và cung cấp giá trị cho cả hai component thông qua `this(...)`.

## 3. Mô hình ủy quyền: mọi con đường phải đi qua canonical

Ví dụ:

```java
record Coordinate(int x, int y) {
    Coordinate(int x) {
        this(x, 0);
    }

    Coordinate() {
        this(0);
    }
}
```

Ở đây canonical constructor `Coordinate(int x, int y)` do compiler sinh. Constructor `Coordinate(int x)` gọi trực tiếp canonical qua `this(x, 0)`. Constructor `Coordinate()` gọi overload một tham số trước, rồi overload đó mới dẫn đến canonical.

```text
new Coordinate(5, 7)
  └── canonical Coordinate(int x, int y)

new Coordinate(5)
  └── Coordinate(int x)
        └── this(x, 0) -> canonical Coordinate(int x, int y)

new Coordinate()
  └── Coordinate()
        └── this(0) -> Coordinate(int x)
              └── this(x, 0) -> canonical Coordinate(int x, int y)
```

**Vì sao Java bắt buộc như vậy?** Các component field của record là `final` và xác định trạng thái giá trị của đối tượng. Canonical constructor thiết lập điểm khởi tạo chung; nếu constructor bổ sung được tự gán trường, các overload có thể tạo ra trạng thái không tuân theo các quy tắc kiểm tra đầu vào. Delegation khiến mọi đối tượng đi qua canonical constructor.

**Quy tắc áp dụng:**

1. Non-canonical constructor phải có một lời gọi *alternate constructor invocation* bằng `this(...)` trong thân. Đích của `this(...)` có thể là canonical hoặc một overload khác.
2. Chuỗi `this(...)` **phải kết thúc ở canonical constructor**; các vòng gọi lẫn nhau vô hạn như A → B → A bị compiler từ chối.
3. Non-canonical constructor không được gọi `super(...)` để thay cho `this(...)` và không được tự gán giá trị vào component fields.
4. Constructor overload có thể làm việc với tham số của chính nó, hằng số và phương thức `static` để tính đối số; phải tôn trọng giới hạn truy cập đối tượng `this` chưa khởi tạo.
5. Có thể khai báo các overload có mức truy cập khác nhau, nhưng overload muốn được gọi từ bên ngoài phải đủ quyền truy cập. Quy tắc quyền truy cập của **canonical constructor** vẫn cần phù hợp với mức truy cập của bản thân record.

## 4. Ví dụ hoàn chỉnh: constructor overload, chuỗi ủy quyền và kiểm tra dữ liệu

**Tệp `RecordConstructorsDemo.java` — biên dịch/chạy được với Java 17+:**

```java
import java.util.Objects;

public class RecordConstructorsDemo {
    record Account(String name, int level) {
        // Compact canonical constructor:
        // kiểm tra và chuẩn hóa đầu vào của MỌI cách khởi tạo.
        Account {
            name = Objects.requireNonNull(name, "name").strip();
            if (name.isEmpty()) {
                throw new IllegalArgumentException("Name must not be blank");
            }
            if (level < 1) {
                throw new IllegalArgumentException("Level must be >= 1");
            }
        }

        // Constructor bổ sung: chỉ truyền tên, mặc định level = 1.
        Account(String name) {
            this(name, 1);
        }

        // Constructor bổ sung: mặc định cả tên và level.
        // Chuỗi gọi: Account() -> Account(String) -> canonical.
        Account() {
            this("Guest");
        }

        // Constructor bổ sung: level ở dạng chuỗi.
        Account(String name, String levelText) {
            this(name, Integer.parseInt(levelText));
        }
    }

    record Range(int start, int end) {
        // Một normal canonical constructor, không phải overload.
        Range(int start, int end) {
            if (start > end) {
                throw new IllegalArgumentException("start > end");
            }
            this.start = start;
            this.end = end;
        }

        // Non-canonical: đưa giá trị mặc định vào canonical.
        Range(int end) {
            this(0, end);
        }
    }

    public static void main(String[] args) {
        Account a = new Account();
        Account b = new Account("  Mai  ");
        Account c = new Account("  Linh  ", "3");

        System.out.println(a);
        System.out.println(b);
        System.out.println(c);
        System.out.println(c.name());
        System.out.println(new Range(9));

        try {
            new Account("  ", 2);
        } catch (IllegalArgumentException e) {
            System.out.println("invalid=" + e.getMessage());
        }
        try {
            new Range(9, 3);
        } catch (IllegalArgumentException e) {
            System.out.println("range=" + e.getMessage());
        }
    }
}
```

Lệnh chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 RecordConstructorsDemo.java
java RecordConstructorsDemo
```

**Stdout chính xác:**

```text
Account[name=Guest, level=1]
Account[name=Mai, level=1]
Account[name=Linh, level=3]
Linh
Range[start=0, end=9]
invalid=Name must not be blank
range=start > end
```

### 4.1. Theo dõi từng đường khởi tạo

- `new Account()`: chạy overload không tham số → `this("Guest")` → overload `Account(String)` → `this("Guest", 1)` → **compact canonical**. Kết quả là `Account[name=Guest, level=1]`.
- `new Account("  Mai  ")`: overload một tham số gọi trực tiếp compact canonical; `name.strip()` loại khoảng trắng ở hai đầu. Giá trị cuối là `Mai`.
- `new Account("  Linh  ", "3")`: overload nhận chuỗi gọi `Integer.parseInt("3")` để tạo `int`, rồi chuyển sang canonical. Canonical tiếp tục chuẩn hóa tên và kiểm tra `level`.
- `new Account("  ", 2)`: gọi thẳng canonical; sau `strip()` tên rỗng nên ném `IllegalArgumentException`. **Không có instance hợp lệ nào được trả ra.**
- `new Range(9)`: gọi `Range(int end)` rồi `this(0, 9)`, tiến đến **normal canonical**. Ở đây hai phép gán `this.start = start` và `this.end = end` hợp lệ vì chúng nằm trong **normal canonical constructor**, khác với non-canonical hoặc compact canonical.

**Điểm quan trọng:** `Integer.parseInt(...)` có thể ném `NumberFormatException` **trước** khi canonical bắt đầu chạy (do Java đánh giá tham số truyền vào `this(...)`). Ví dụ không bắt lỗi đó để giữ đường đi rõ ràng; trong ứng dụng thật, hãy quyết định thông điệp lỗi đầu vào nào muốn trả về, rồi xử lý tại ranh giới API. Dù overload nào thành công thì các invariant của `Account` vẫn đi qua canonical constructor.

### 4.2. Compact canonical constructor hoạt động như thế nào?

Dạng:

```java
record Account(String name, int level) {
    Account {
        name = Objects.requireNonNull(name).strip();
        if (name.isEmpty() || level < 1) {
            throw new IllegalArgumentException();
        }
    }
}
```

được hiểu là canonical constructor với danh sách tham số **ngầm định** theo header. Tên `name` và `level` trong thân compact constructor trỏ đến các tham số đó; lập trình viên có thể **gán lại tham số** `name = ...` để chuẩn hóa. Nếu thân hoàn tất bình thường, compiler mới tự gán giá trị cuối cùng của các tham số vào các component field. Không viết `this.name = name;` trong compact constructor: đây là lỗi biên dịch.

Không được khai báo cả **compact canonical** và **normal canonical** có cùng chữ ký trong một record. Hãy chọn một trong hai cách theo mức độ rõ ràng cần thiết.

### 4.3. Normal canonical constructor có khác gì?

Trong `Range(int start, int end)`, chúng ta chủ động kiểm tra invariant rồi **gán đầy đủ component fields**. Khi khai báo normal canonical, các tham số phải tương ứng với component về tên, kiểu và thứ tự; constructor này không được gọi `this(...)` hoặc `super(...)` để chuyển trách nhiệm khởi tạo sang constructor khác. Compact canonical thường ngắn hơn cho validation/normalization; normal canonical hữu ích khi cần điều khiển việc gán field rõ ràng.

Một normal canonical constructor cũng không được có `throws` clause trong chữ ký; các lỗi validation thường được biểu diễn bằng unchecked exceptions như `IllegalArgumentException`. Overload không-canonical tuân theo quy tắc constructor thường và có thể khai báo `throws` nếu phù hợp, nhưng vẫn phải ủy quyền đúng luật.

## 5. Java 17–24 và Java 25+: vị trí của `this(...)`

Nội dung dễ bị học sai khi đọc tài liệu cũ là câu “`this(...)` **luôn** phải đứng đầu constructor”.

**Với Java 17–24 không bật preview**, khi viết non-canonical record constructor theo cú pháp chính thức, `this(...)` phải là lệnh đầu tiên trong thân constructor:

```java
record TimeRange(int start, int end) {
    TimeRange {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }

    TimeRange(int end) {
        this(0, end); // Cách viết tương thích Java 17+.
    }
}
```

Nếu cần xử lý giá trị trước khi truyền cho canonical ở những JDK này, hãy dùng phép tính ngay trong tham số `this(...)` hoặc phương thức hỗ trợ `static`:

```java
record Timeout(long milliseconds) {
    Timeout {
        if (milliseconds < 0) {
            throw new IllegalArgumentException("negative timeout");
        }
    }

    Timeout(String seconds) {
        this(Math.multiplyExact(Long.parseLong(seconds), 1_000L));
    }
}
```

Ví dụ `Timeout` là **đoạn mã có thể đặt ở cấp tệp hoặc lồng trong lớp**; `new Timeout("3").milliseconds()` trả `3000L`. `Math.multiplyExact` phát hiện tràn số; `Long.parseLong` có thể ném ngoại lệ khi đầu vào sai định dạng. Canonical vẫn kiểm tra điều kiện không âm.

**Từ Java 25, JEP 513 — Flexible Constructor Bodies — là tính năng chính thức.** Non-canonical constructor của record vẫn **bắt buộc có** `this(...)`, nhưng có thể chứa một số lệnh chuẩn bị tham số (*prologue*) **trước `this(...)`**, miễn tuân theo quy tắc *early construction context*. Ví dụ **chỉ dành cho JDK 25+**:

```java
record Window(int start, int end) {
    Window {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
    }

    Window(String input) {
        String[] parts = input.split(",", -1);
        if (parts.length != 2) {
            throw new IllegalArgumentException("Expected start,end");
        }
        int start = Integer.parseInt(parts[0].trim());
        int end = Integer.parseInt(parts[1].trim());
        this(start, end); // Java 25+: được phép có prologue phía trước.
    }
}
```

Đây là ví dụ tính năng ngôn ngữ **Java 25+**, không phải chương trình độc lập có phương thức `main`. Dùng `new Window("2,5")` với JDK 25+ cho ra `Window[start=2, end=5]`. Trên JDK 17–24 ở chế độ chuẩn, **không dùng nguyên cú pháp prologue này**; ví dụ `TimeRange` và `Timeout` phía trên mới là cách viết portable. Không dùng `--enable-preview` để duy trì mã nguồn cũ khi dự án đã có JDK hỗ trợ tính năng chính thức.

Trong prologue Java 25+, không được truy cập instance đang xây dựng bằng `this`, tham chiếu trường/phương thức instance của nó hoặc dùng `super` tùy ý. Chỉ sử dụng tham số, biến cục bộ, hằng và phép tính hoặc phương thức `static` hợp lệ cho giai đoạn sớm. **Sự nới lỏng vị trí câu lệnh không hề nới lỏng nghĩa vụ ủy quyền tới canonical constructor.**

## 6. Kiểm tra và chuẩn hóa dữ liệu ở đâu là hợp lý?

Đặt các **invariant của record** tại canonical constructor. Các overload có thể hỗ trợ chuyển đổi biểu diễn và cung cấp default, nhưng cần bảo đảm mọi cách xây dựng đều tuân theo cùng một quy tắc.

**Mẫu nên dùng:**

```java
record Profile(String displayName, int roleLevel) {
    Profile {
        displayName = java.util.Objects
                .requireNonNull(displayName, "displayName")
                .strip();
        if (displayName.isEmpty()) {
            throw new IllegalArgumentException("Blank displayName");
        }
        if (roleLevel < 1 || roleLevel > 5) {
            throw new IllegalArgumentException("Invalid roleLevel");
        }
    }

    Profile(String displayName) {
        this(displayName, 1);
    }
}
```

*Đây là khai báo record độc lập về cú pháp; bạn có thể đặt nó trong `Profile.java` với quyền truy cập package-private, hoặc lồng trong lớp.* Dù gọi `new Profile("Alice")` hay `new Profile("Alice", 4)`, cả hai đều kiểm tra tên và `roleLevel` ở cùng chỗ.

**Mẫu dễ gây lỗi:** chỉ kiểm tra trong overload một tham số, còn canonical không kiểm tra; khi code khác gọi trực tiếp canonical với tham số lỗi, invariant sẽ bị vi phạm. Cũng không nên để một overload tự làm sạch tên còn overload kia bỏ qua, khiến hai cách khởi tạo có kết quả khác nhau cho cùng dữ liệu.

Phân công trách nhiệm gợi ý:

| Nơi đặt logic | Việc nên làm |
| --- | --- |
| Non-canonical constructor | Cấp giá trị mặc định; chuyển đổi input như `String` → `int`; gọi `this(...)` |
| Canonical constructor (compact hoặc normal) | Kiểm tra invariant bắt buộc; chuẩn hóa component; bảo đảm đối tượng hợp lệ |
| Static helper | Parse phức tạp, tính giá trị cần cho `this(...)` trên JDK 17–24 |
| Static factory | Đặt tên rõ cho lựa chọn xây dựng phức tạp, khi số overload dễ gây mơ hồ |
| Service hoặc validator bên ngoài | Kiểm tra quy tắc nghiệp vụ phụ thuộc I/O, database hoặc trạng thái môi trường; hạn chế đẩy side effects vào record |

Nếu constructor phụ thuộc mạng/database hoặc có nhiều tác dụng phụ, việc tạo đối tượng sẽ khó dự đoán và khó kiểm thử. Một record thường thích hợp nhất cho dữ liệu đã có đủ thông tin để kiểm tra invariant ngay trong bộ nhớ.

## 7. Record bất biến nông: overload và canonical có thể phòng vệ dữ liệu mutable

Component field trong record là `final`, nhưng nếu nó chứa tham chiếu `List` hoặc array thì đối tượng được tham chiếu vẫn có thể thay đổi. Mọi overload nên dẫn tới canonical constructor có phép sao chép phòng vệ khi cần.

**Tệp `LabelsDemo.java` — Java 17+:**

```java
import java.util.ArrayList;
import java.util.List;

public class LabelsDemo {
    record Labels(List<String> values) {
        Labels {
            values = List.copyOf(values);
        }

        Labels(String singleValue) {
            this(List.of(singleValue));
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Labels first = new Labels(source);
        source.add("B");
        System.out.println(first.values());

        Labels second = new Labels("X");
        System.out.println(second.values());

        try {
            first.values().add("C");
        } catch (UnsupportedOperationException e) {
            System.out.println("cannot modify labels");
        }
    }
}
```

```bash
javac LabelsDemo.java
java LabelsDemo
```

**Stdout chính xác:**

```text
[A]
[X]
cannot modify labels
```

Nhánh `new Labels(source)` đi thẳng vào canonical constructor. Nhánh `new Labels("X")` gọi `this(List.of("X"))` trước khi vào canonical. Cả hai đều được xử lý bằng `List.copyOf(values)`, do đó thay đổi list nguồn bên ngoài không làm thay đổi list bên trong record. Lưu ý `List.copyOf` tạo snapshot bất biến của **cấu trúc list**, không tự biến mọi phần tử kiểu tham chiếu bên trong thành bất biến sâu.

## 8. Những lỗi biên dịch điển hình

### 8.1. Constructor bổ sung tự gán component fields, không gọi `this(...)`

```java
// SAI — ví dụ cố ý không biên dịch.
record InvalidRecord(int x, int y) {
    InvalidRecord(int x) {
        this.x = x;
        this.y = 0;
    }
}
```

`InvalidRecord(int x)` không có chữ ký canonical và không gọi một constructor khác bằng `this(...)`. Lỗi cốt lõi: **non-canonical constructor thiếu alternate constructor invocation**. Việc hai trường đều được gán không làm mất lỗi. Dạng đúng:

```java
record ValidRecord(int x, int y) {
    ValidRecord(int x) {
        this(x, 0);
    }
}
```

### 8.2. Đệ quy vòng constructor

```java
// SAI — vòng ủy quyền.
record Cycle(int n) {
    Cycle() {
        this("default");
    }

    Cycle(String label) {
        this();
    }
}
```

Hai constructor bổ sung gọi qua lại, không có đường đi tới canonical `Cycle(int n)`. Compiler phát hiện và từ chối lời gọi constructor đệ quy trực tiếp hoặc gián tiếp. Hãy thay một mắt xích bằng `this(0)` hoặc giá trị `int` phù hợp để tới canonical.

### 8.3. Canonical constructor lại gọi `this(...)`

```java
// SAI — đây là canonical vì chữ ký khớp header.
record BadCanonical(int x) {
    BadCanonical(int x) {
        this(x + 1);
    }
}
```

Canonical constructor không được có lời gọi explicit constructor invocation. Hãy thực hiện kiểm tra/chuyển đổi tham số rồi gán field trực tiếp trong **normal canonical**, hoặc dùng **compact canonical** để compiler gán field.

### 8.4. Gán component field trong compact constructor

```java
// SAI — trong compact canonical không được gán field.
record WrongCompact(String name) {
    WrongCompact {
        this.name = name.trim();
    }
}
```

Sửa thành `name = name.trim();` để thay đổi **tham số ngầm định**; compiler gán giá trị tham số cuối cùng vào field sau khi compact constructor kết thúc bình thường.

### 8.5. Cố thay `this(...)` bằng `super(...)`

Record kế thừa `java.lang.Record` một cách ngầm định; record không được mở rộng một lớp cha tùy ý. Non-canonical record constructor **không được** gọi `super(...)` thay cho `this(...)`. Chỉ `this(...)` bảo đảm đường đi dẫn tới canonical và khởi tạo component fields đúng quy tắc.

### 8.6. Nhầm “không tham số” với “mặc định tự sinh”

`record Connection(String host, int port) {}` chỉ có canonical với hai tham số. Lệnh `new Connection()` lỗi vì không có overload không tham số. Muốn hỗ trợ, phải khai báo rõ:

```java
record Connection(String host, int port) {
    Connection() {
        this("localhost", 8080);
    }
}
```

### 8.7. Khai báo đồng thời hai canonical constructor

Nếu record đã có `record R(int value) { R { ... } }`, bạn không thể khai báo thêm `R(int value) { ... }`, vì cả compact và normal đều là canonical cho cùng header. Chỉ giữ **một** cách hiện thực canonical.

### 8.8. Overload mơ hồ hoặc truyền sai kiểu

Java chọn constructor overload dựa trên **chữ ký tham số**, không dựa vào tên biến, lời ghi chú hay kiểu giá trị trả về (constructor không có kiểu trả về). Ví dụ khi một record có đồng thời `R(String)` và `R(java.nio.file.Path)`, lời gọi `new R(null)` có thể mơ hồ. Hãy truyền đối số có kiểu rõ, dùng factory có tên hoặc thiết kế API để tránh overload khó hiểu.

## 9. Khi nào nên dùng static factory thay cho overload?

Constructor overload rất hợp lý cho **giá trị mặc định đơn giản** và đầu vào được phân biệt tự nhiên bằng kiểu hoặc số tham số. Khi có nhiều cách tạo giá trị với cùng chữ ký, hoặc quá nhiều bước parse phức tạp, static factory thể hiện ý nghĩa rõ hơn.

Ví dụ khác biệt về đơn vị đo:

```java
record DurationValue(long millis) {
    DurationValue {
        if (millis < 0) {
            throw new IllegalArgumentException("negative duration");
        }
    }

    static DurationValue fromSeconds(long seconds) {
        return new DurationValue(Math.multiplyExact(seconds, 1_000L));
    }

    static DurationValue fromMillis(long millis) {
        return new DurationValue(millis);
    }
}
```

Cả hai factory trả về object thông qua canonical constructor `DurationValue(long millis)`, không lặp lại logic kiểm tra giá trị âm. Ta không thể tạo hai overload `DurationValue(long seconds)` và `DurationValue(long millis)` chỉ nhờ đổi tên tham số, vì chúng có cùng chữ ký. Tên `fromSeconds` / `fromMillis` làm API dễ hiểu hơn nhiều.

Dù dùng overload hay factory, mọi invariant quan trọng vẫn nên được kiểm tra trong canonical constructor (hoặc hàm hỗ trợ được canonical gọi) để tránh lối xây dựng không được kiểm soát.

## 10. Quy tắc về quyền truy cập và khả năng bảo trì

- Với `public record` ở cấp top-level, canonical constructor khai báo rõ phải có quyền truy cập `public`, không thể giảm xuống package-private hoặc private. Khi record là package-private, constructor cần tuân theo quy tắc truy cập tương ứng; các ví dụ record lồng trong `public class` dùng quyền truy cập phù hợp cho phạm vi bài.
- Constructor bổ sung có thể là `private` khi chỉ dùng nội bộ hoặc `public` khi là API bên ngoài. Nhưng một overload public không “chữa” được một canonical constructor vi phạm quy tắc quyền truy cập.
- Nếu một record thay đổi **thứ tự, kiểu hoặc số lượng component**, chữ ký canonical constructor sẽ thay đổi. Xem lại tất cả các `this(...)` và người gọi bên ngoài; đây có thể là thay đổi không tương thích source/binary của API công khai.
- Đặt default hợp lý theo ngữ nghĩa nghiệp vụ; đừng chọn `null`, `0` hoặc chuỗi rỗng một cách tùy ý rồi khiến canonical phải chấp nhận đối tượng không hợp lệ.
- Đặt normalization chung ở canonical; tránh mỗi overload làm cùng việc theo cách khác nhau. Nếu phải parse đầu vào nhiều lần hoặc overload khó đọc, cân nhắc factory rõ tên.
- Constructor là phần tạo trạng thái; record thích hợp với data carrier gọn. Không cố biến nó thành entity có trạng thái thay đổi hoặc vòng đời phức tạp bằng nhiều constructor và side effect.

## 11. Bài tập tự thực hành

1. Tạo `record Rectangle(int width, int height)`, compact canonical kiểm tra hai giá trị lớn hơn 0; thêm overload `Rectangle(int side)` gọi `this(side, side)`. Giải thích vì sao cả rectangle thường và hình vuông đều qua cùng validation.
2. Thêm overload không tham số `Rectangle()` với default `1 x 1` và vẽ chuỗi `this(...)` từ overload tới canonical.
3. Thêm overload `Rectangle(String width, String height)` chuyển chuỗi bằng `Integer.parseInt`. Thử một chuỗi không hợp lệ rồi chỉ rõ ngoại lệ xảy ra khi đánh giá đối số hay trong canonical.
4. Viết một record có **normal canonical** thay vì compact canonical, thực hiện kiểm tra rồi gán đầy đủ component fields. Xác định vì sao không được thêm compact canonical cùng lúc.
5. Cố viết constructor bổ sung gán `this.width` và `this.height` trực tiếp; biên dịch để quan sát lỗi thiếu `this(...)`, sau đó sửa đúng.
6. Viết hai overload gọi nhau tuần hoàn; quan sát compiler từ chối rồi thiết kế một nhánh kết thúc tại canonical.
7. Dùng `record Names(List<String> names)` có canonical `List.copyOf(names)` và overload nhận một tên; kiểm tra khả năng sửa list nguồn sau khi tạo record.
8. **Nâng cao Java 25+:** viết overload nhận `"2,5"`, tách chuỗi trong prologue trước `this(start, end)`. Nêu giới hạn *early construction context*. Với Java 17–24, chuyển việc parse vào static helper hoặc static factory để cùng code chạy không cần preview.

**Đáp án định hướng:** (1–2) mọi đường tạo dẫn tới canonical; (3) `parseInt` được đánh giá trước khi constructor đích chạy, nên lỗi format có thể phát sinh trước validation canonical; (4) chỉ một canonical; (5) non-canonical không được tự khởi tạo field; (6) không được có chuỗi đệ quy không tới canonical; (7) `List.copyOf` bảo vệ cấu trúc list khỏi sửa đổi; (8) quy tắc Java 25 nới vị trí `this(...)` nhưng không bỏ nghĩa vụ ủy quyền.

## 12. Tài liệu chính thức đối chiếu

- **Java Language Specification (Java SE 25), `8.10.4 — Record Constructor Declarations**: phân loại canonical và non-canonical; ràng buộc `this(...)` và component fields: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10.4
- **Java Language Specification, `8.8.7.1 — Explicit Constructor Invocations**: quy tắc alternate constructor invocation, giới hạn early construction và đệ quy: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7.1
- **Oracle Java 17 — Record Classes**: ví dụ normal và compact canonical constructors, quy tắc component fields: https://docs.oracle.com/en/java/javase/17/language/records.html
- **Oracle Java 25 — Flexible Constructor Bodies**, có mục riêng về record constructors với lệnh trước `this(...)`: https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html
- **OpenJDK JEP 395 — Records** (chính thức từ Java 16): https://openjdk.org/jeps/395
- **OpenJDK JEP 513 — Flexible Constructor Bodies** (chính thức từ Java 25): https://openjdk.org/jeps/513

**Ghi nhớ:** *Constructor bổ sung cung cấp đường vào thuận tiện; canonical constructor quyết định trạng thái hợp lệ cuối cùng của record.* Mọi overload phải ủy quyền qua `this(...)` tới canonical, dù trực tiếp hay qua một overload khác. Với Java 25+, lệnh chuẩn bị có thể đứng trước `this(...)` theo quy tắc mới, nhưng nguyên tắc ủy quyền vẫn giữ nguyên.