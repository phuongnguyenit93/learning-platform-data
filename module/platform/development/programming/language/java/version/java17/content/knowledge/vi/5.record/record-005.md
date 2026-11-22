# Constructor bổ sung và quy tắc gọi canonical constructor trong record (Java 17)

> **Chủ đề:** Java 17  
> **Chương:** Record  
> **Phạm vi:** Các quy tắc đã ổn định trong Java 17. Toàn bộ ví dụ được thiết kế cho `javac --release 17`, không cần bật tính năng preview.

## 1. Vấn đề cần giải quyết

Giả sử ứng dụng lưu cấu hình kết nối gồm tên máy chủ, cổng và chế độ bảo mật:

```java
record Endpoint(String host, int port, boolean secure) { }
```

Bạn có thể tạo đối tượng bằng cách truyền đủ ba giá trị:

```java
Endpoint endpoint = new Endpoint("api.example.com", 443, true);
```

Nhưng nếu phần lớn kết nối HTTPS dùng cổng 443, người viết chương trình có thể muốn cách gọi ngắn hơn:

```java
new Endpoint("api.example.com");      // Mặc định HTTPS, cổng 443
new Endpoint("api.example.com", 8443); // HTTPS, cổng được chỉ định
new Endpoint();                       // Cấu hình cục bộ mặc định
```

Trong Java 17, `record` **được phép khai báo nhiều constructor** giống lớp thông thường, với một ràng buộc rất quan trọng: **mọi constructor bổ sung (non-canonical constructor) phải bắt đầu bằng lệnh gọi một constructor khác của chính record bằng `this(...)`**. Chuỗi gọi cuối cùng phải đi tới **canonical constructor**, nơi các record component được khởi tạo.

Bài học này làm rõ ba hình thức cần phân biệt:

1. **Canonical constructor được Java sinh tự động** nếu bạn không tự khai báo.
2. **Canonical constructor được viết tường minh**, dưới dạng đầy đủ hoặc dạng rút gọn (*compact canonical constructor*).
3. **Constructor bổ sung (overloaded/non-canonical)**, cung cấp cách khởi tạo tiện lợi nhưng phải chuyển tiếp qua `this(...)`.

## 2. Canonical constructor là gì?

Mỗi record có một danh sách **record components** nằm trong phần header:

```java
record Student(String name, int age) { }
```

Với header này, constructor chuẩn có hai tham số, **đúng thứ tự và kiểu tương ứng**:

```java
Student(String name, int age)
```

Nó được gọi là **canonical constructor**. Khi không tự khai báo, trình biên dịch cung cấp constructor có tác dụng khởi tạo trường tương ứng với từng component:

```java
Student student = new Student("Lan", 20);
System.out.println(student.name()); // Lan
System.out.println(student.age());  // 20
```

Mỗi record có đúng **một canonical constructor** (được sinh ngầm hoặc được khai báo tường minh). Java **không tự tạo constructor không tham số** cho record có component. Chẳng hạn, `new Student()` không hợp lệ nếu bạn chưa viết một constructor bổ sung `Student()`.

Với `record Student(String name, int age)`, Java còn cung cấp:

- Hai trường component tương ứng: `private final String name` và `private final int age`.
- Accessor: `name()` và `age()`.
- Các phương thức `equals(Object)`, `hashCode()` và `toString()` phù hợp với record.

**Canonical constructor chịu trách nhiệm khởi tạo toàn bộ các trường component**, không phải chỉ khởi tạo một phần. Đây là nền tảng khiến mọi constructor bổ sung phải đi qua nó.

### 2.1. Ba dạng canonical constructor

**Dạng A — Để Java sinh tự động:**

```java
record Student(String name, int age) { }
```

Thích hợp khi dữ liệu đầu vào đã hợp lệ và không cần chuẩn hóa.

**Dạng B — Tự viết canonical constructor đầy đủ:**

```java
import java.util.Objects;

record Student(String name, int age) {
    Student(String name, int age) {
        this.name = Objects.requireNonNull(name, "name").strip();
        if (this.name.isBlank()) {
            throw new IllegalArgumentException("name không được rỗng");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age phải >= 0");
        }
        this.age = age;
    }
}
```

Ở dạng này, ta khai báo đầy đủ các tham số và **tự gán từng trường component** qua `this.name = ...`, `this.age = ...`; trình biên dịch yêu cầu mọi trường component được khởi tạo hợp lệ. Dạng đầy đủ hữu ích khi muốn kiểm soát các phép gán một cách tường minh.

**Dạng C — Viết compact canonical constructor:**

```java
import java.util.Objects;

record Student(String name, int age) {
    Student {
        name = Objects.requireNonNull(name, "name").strip();
        if (name.isBlank()) {
            throw new IllegalArgumentException("name không được rỗng");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age phải >= 0");
        }
    }
}
```

Trong **compact constructor**, các tham số được lấy ngầm từ record header. Sau khi phần thân thực thi bình thường, Java tự gán giá trị tham số (có thể đã được chuẩn hóa) vào từng trường component theo thứ tự khai báo. Vì vậy:

```java
name = name.strip(); // Hợp lệ: gán lại tham số trong compact constructor
```

nhưng:

```java
// Không hợp lệ trong compact constructor:
// this.name = name.strip();
```

Với việc chỉ cần kiểm tra, chuẩn hóa dữ liệu, **compact canonical constructor** thường là lựa chọn ngắn gọn và dễ đọc nhất.

| Dạng | Có khai báo danh sách tham số? | Ai gán trường component? | Dùng khi nào? |
|---|---|---|---|
| Sinh ngầm | Không viết constructor | Trình biên dịch | Dữ liệu đầu vào không cần xử lý |
| Canonical đầy đủ | Có, khớp component theo tên, kiểu, thứ tự | Lập trình viên | Muốn kiểm soát trực tiếp quá trình gán |
| Compact canonical | Không, dùng tham số ngầm từ header | Trình biên dịch, sau phần thân | Validate, chuẩn hóa và giữ mã súc tích |

**Không thể đồng thời khai báo canonical đầy đủ và compact canonical** trong cùng record: cả hai là một constructor chuẩn với cùng chữ ký, nên trình biên dịch báo lỗi trùng.

## 3. Constructor bổ sung và quy tắc `this(...)`

Constructor bổ sung là constructor có **danh sách tham số khác chữ ký canonical constructor**. Nó cho phép tạo record với giá trị mặc định, chuyển đổi đầu vào hoặc cung cấp cách gọi tiện lợi.

```java
record Point(int x, int y) {
    Point(int x) {
        this(x, 0);
    }
}
```

Ở đây:

- `Point(int x, int y)` là canonical constructor do Java sinh ngầm.
- `Point(int x)` là constructor bổ sung.
- `this(x, 0)` gọi canonical constructor, truyền `0` làm giá trị `y` mặc định.

Sử dụng:

```java
Point point = new Point(5);
System.out.println(point); // Point[x=5, y=0]
```

### 3.1. Quy tắc bắt buộc trong Java 17

**Trong Java 17, phần thân mỗi constructor không phải canonical phải bắt đầu bằng lệnh gọi một constructor khác của cùng record:**

```java
this(...);
```

`this(...)` là một *alternate constructor invocation*. Bạn được gọi trực tiếp canonical constructor **hoặc** một constructor bổ sung khác, miễn là toàn bộ chuỗi cuối cùng đến canonical constructor.

**Không được** dùng `super(...)` thay cho `this(...)`. Record kế thừa `java.lang.Record` theo cơ chế của ngôn ngữ; không được tự điều khiển khởi tạo trường component bằng cách gọi `super(...)` trong constructor bổ sung.

**Không được** viết các lệnh khác trước `this(...)` trong constructor bổ sung của Java 17. Các phiên bản Java mới hơn có thể có quy tắc constructor khác; bài này giữ đúng ngữ nghĩa ổn định của **JDK 17**.

Ví dụ hợp lệ:

```java
record Box(int width, int height) {
    Box(int side) {
        this(side, side);
    }
}
```

Ví dụ không hợp lệ:

```java
record Box(int width, int height) {
    // SAI: constructor bổ sung không bắt đầu bằng this(...).
    Box(int side) {
        int normalized = Math.max(0, side);
        this(normalized, normalized);
    }
}
```

Không thể di chuyển `this(...)` xuống sau bước chuẩn hóa. Thay vào đó, nên đặt kiểm tra/chuẩn hóa ở canonical constructor hoặc biểu diễn bằng biểu thức trong chính lời gọi `this(...)`.

### 3.2. Có thể gọi qua nhiều constructor bổ sung

```java
record Ticket(String code, int priority) {
    Ticket() {
        this("NEW");
    }

    Ticket(String code) {
        this(code, 0);
    }

    Ticket {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Mã vé không hợp lệ");
        }
        if (priority < 0) {
            throw new IllegalArgumentException("Độ ưu tiên phải >= 0");
        }
    }
}
```

Luồng thực thi của `new Ticket()`:

```text
new Ticket()
   |
   v
Ticket()                [constructor bổ sung]
   | this("NEW")
   v
Ticket(String code)     [constructor bổ sung]
   | this(code, 0)
   v
Ticket(String, int)     [compact canonical constructor]
   | kiểm tra code, priority
   | Java gán các trường component
   v
Ticket[code=NEW, priority=0]
```

Chuỗi này được gọi là **constructor chaining**. Trình biên dịch không cho phép một chuỗi `this(...)` quay về chính constructor ban đầu và tạo vòng lặp.

### 3.3. Constructor bổ sung có thể chứa mã sau `this(...)`

Điều kiện là **lệnh đầu tiên phải là `this(...)`**; Java không yêu cầu lời gọi đó phải là lệnh cuối:

```java
record Counter(int initial) {
    Counter() {
        this(0);
        System.out.println("Đã tạo Counter mặc định");
    }
}
```

Khi chạy lệnh sau `this(...)`, canonical constructor đã hoàn tất khởi tạo và kiểm tra record. Bạn có thể thực hiện những thao tác khác hợp lệ, nhưng **không thể gán lại các trường `final` của record**. Với đối tượng dữ liệu, nên hạn chế tác dụng phụ trong constructor và giữ các quy tắc hợp lệ tập trung ở canonical constructor.

## 4. Ví dụ thực hành hoàn chỉnh: Tạo cấu hình với nhiều cách gọi

Tạo file `ConstructorDemo.java`:

```java
import java.util.Locale;
import java.util.Objects;

public class ConstructorDemo {

    public record Endpoint(String host, int port, boolean secure) {

        // Compact canonical constructor: dùng cho MỌI đường tạo Endpoint.
        public Endpoint {
            host = Objects.requireNonNull(host, "host")
                    .strip()
                    .toLowerCase(Locale.ROOT);

            if (host.isBlank()) {
                throw new IllegalArgumentException("host không được để trống");
            }
            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException(
                        "port phải nằm trong khoảng 1..65535");
            }
        }

        // Chỉ cần host: mặc định dùng HTTPS trên cổng 443.
        public Endpoint(String host) {
            this(host, 443, true);
        }

        // Host và cổng, mặc định có TLS.
        public Endpoint(String host, int port) {
            this(host, port, true);
        }

        // Dùng cho thực hành trên máy cục bộ.
        public Endpoint() {
            this("localhost", 8080, false);
        }

        public String url() {
            return (secure ? "https://" : "http://")
                    + host + ":" + port;
        }
    }

    public static void main(String[] args) {
        Endpoint first = new Endpoint("  EXAMPLE.COM  ");
        Endpoint second = new Endpoint();
        Endpoint third = new Endpoint("API.LOCAL", 8443, true);

        System.out.println(first);
        System.out.println(second.url());
        System.out.println(third.url());
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac --release 17 ConstructorDemo.java
java ConstructorDemo
```

Kết quả:

```text
Endpoint[host=example.com, port=443, secure=true]
http://localhost:8080
https://api.local:8443
```

Điều cần quan sát:

1. `new Endpoint("  EXAMPLE.COM  ")` chọn constructor bổ sung **một tham số**.
2. Constructor đó gọi `this(host, 443, true)`, chuyển đến **compact canonical constructor**.
3. Canonical constructor xóa khoảng trắng, chuyển host về chữ thường bằng `Locale.ROOT` và kiểm tra cổng.
4. Java gán các tham số đã chuẩn hóa vào component fields. Kết quả hiển thị host là `example.com`.
5. Các cách gọi hai tham số, ba tham số và không tham số đều đi qua cùng logic xác thực dữ liệu.

Thử tạo giá trị không hợp lệ:

```java
new ConstructorDemo.Endpoint(" ", 443, true);
new ConstructorDemo.Endpoint("api.example.com", 70000, true);
```

Cả hai đều gây `IllegalArgumentException` từ canonical constructor. Đó là lợi ích chính của việc **tập trung invariant ở một nơi** thay vì sao chép kiểm tra ở từng constructor bổ sung.

> **Lưu ý:** Việc chuyển hostname thành chữ thường có thể phù hợp với tên DNS, nhưng không nên tự động áp dụng cùng cách chuẩn hóa cho mọi chuỗi nghiệp vụ. Chuẩn hóa giá trị theo yêu cầu cụ thể của miền dữ liệu.

## 5. So sánh constructor đầy đủ và compact khi có overload

Hai thiết kế sau có thể đạt cùng mục tiêu: constructor bổ sung dùng `this(...)` và canonical constructor giữ invariant.

### 5.1. Canonical đầy đủ: tự gán các trường

Trong file `InventoryItem.java`:

```java
import java.util.Objects;

public record InventoryItem(String sku, int quantity) {

    // Canonical constructor đầy đủ.
    public InventoryItem(String sku, int quantity) {
        String normalized = Objects.requireNonNull(sku, "sku").strip();
        if (normalized.isBlank()) {
            throw new IllegalArgumentException("sku không được để trống");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity phải >= 0");
        }

        this.sku = normalized;
        this.quantity = quantity;
    }

    public InventoryItem(String sku) {
        this(sku, 0);
    }
}
```

Khi tự viết canonical đầy đủ, tham số của nó phải có **đúng tên, đúng kiểu và đúng thứ tự** so với record header (`sku` rồi `quantity`). Bên trong constructor này, bạn phải khởi tạo trường component trực tiếp; không được bỏ qua một trường.

### 5.2. Compact canonical: Java gán các trường sau phần thân

Phiên bản tương đương trong file `InventoryItem.java`:

```java
import java.util.Objects;

public record InventoryItem(String sku, int quantity) {

    public InventoryItem {
        sku = Objects.requireNonNull(sku, "sku").strip();
        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku không được để trống");
        }
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity phải >= 0");
        }
    }

    public InventoryItem(String sku) {
        this(sku, 0);
    }
}
```

Ở đây, **không viết** `this.sku = sku` hoặc `this.quantity = quantity` trong compact constructor; Java tự thực hiện điều đó.

**Khi chọn giữa hai dạng:**

- Compact phù hợp phần lớn trường hợp: kiểm tra null, kiểm tra miền giá trị, chuẩn hóa chuỗi hoặc sao chép phòng vệ.
- Dạng đầy đủ hữu ích nếu bạn muốn trình bày rõ thứ tự xử lý và phép gán từng trường.
- Hai dạng có cùng vai trò **canonical**; constructor overload gọi tới chúng bằng `this(...)` theo cùng quy tắc.

## 6. Quy tắc chính xác về chữ ký và phạm vi truy cập

### 6.1. Constructor nào được xem là canonical?

Xét record:

```java
public record Coordinate(double latitude, double longitude) { }
```

Chữ ký canonical có hai tham số `double` theo đúng thứ tự:

```java
public Coordinate(double latitude, double longitude)
```

Các dạng sau không phải cùng chữ ký canonical:

```java
Coordinate(double latitude)             // Overload: ít tham số
Coordinate(String coordinateText)        // Overload: kiểu khác
Coordinate()                             // Overload: không tham số
```

**Chỉ đổi tên tham số không tạo overload mới.** Nếu cố viết:

```java
record Coordinate(double latitude, double longitude) {
    // SAI: chữ ký hai double vẫn là chữ ký canonical,
    // nhưng tên tham số không khớp record components.
    Coordinate(double x, double y) {
        this.latitude = x;
        this.longitude = y;
    }
}
```

Java sẽ từ chối do tham số canonical khai báo tường minh phải tương ứng tên component.

Tương tự, đổi thứ tự hai component **cùng kiểu** không làm thay đổi chữ ký overload và không được dùng để thêm constructor mới:

```java
record Range(int start, int end) {
    // SAI: vẫn là chữ ký (int, int), trùng với canonical constructor.
    // Range(int end, int start) { ... }
}
```

Khi cần diễn đạt hai kiểu ý nghĩa của cùng cặp tham số, dùng một **static factory method có tên rõ ràng** thay vì cố overload bằng cách đổi tên biến:

```java
record Range(int start, int end) {
    Range {
        if (start > end) {
            throw new IllegalArgumentException("start phải <= end");
        }
    }

    static Range startingAtZero(int end) {
        return new Range(0, end);
    }
}
```

### 6.2. Phạm vi truy cập của canonical constructor

Trong Java 17, canonical constructor được khai báo tường minh **không được có phạm vi truy cập hẹp hơn record**:

| Quyền truy cập của record | Quyền truy cập canonical constructor |
|---|---|
| `public` | Phải `public` |
| `protected` (record lồng được phép có phạm vi này) | `protected` hoặc `public` |
| Package-private | Package-private hoặc `public` |
| `private` (record lồng) | Có thể chọn phạm vi hợp lệ bất kỳ |

Ví dụ một public record:

```java
public record User(String name) {
    // ĐÚNG: cùng quyền truy cập với record.
    public User {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name không hợp lệ");
        }
    }
}
```

Nếu đổi `public User` thành `private User` trong record `public` thì lỗi biên dịch.

**Constructor bổ sung có thể chọn phạm vi truy cập riêng** tùy mục đích. Ví dụ, một overload `private` có thể chỉ được dùng bởi các static factory method ở bên trong record. Quy tắc “không hẹp hơn record” ở trên áp dụng riêng cho **canonical constructor**.

### 6.3. Ràng buộc riêng của canonical constructor

Một canonical constructor được khai báo tường minh theo dạng đầy đủ:

- Phải có tên và kiểu tham số tương ứng record components.
- **Không được là generic constructor** (không tự khai báo type parameter riêng).
- **Không được có `throws` clause**.
- **Không được chứa lời gọi constructor tường minh `this(...)` hoặc `super(...)`**.
- Nếu dùng dạng đầy đủ, phải khởi tạo các trường component đúng quy tắc definite assignment.

Với compact canonical constructor, cũng không được viết `return`, `this(...)`, `super(...)` hoặc trực tiếp gán vào trường component.

**Phân biệt:** Một record *generic* như `record Pair<T>(T value)` vẫn hoàn toàn hợp lệ; điều bị cấm là một **canonical constructor tự khai báo tham số kiểu riêng**, không phải record có type parameter.

### 6.4. Constructor bổ sung có thể khai báo `throws`

Constructor bổ sung có thể tiếp nhận kiểu đầu vào khác và báo ngoại lệ được kiểm tra. Ví dụ file `DocumentText.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Objects;

public record DocumentText(String content) {

    public DocumentText {
        Objects.requireNonNull(content, "content");
    }

    public DocumentText(Path path) throws IOException {
        this(Files.readString(path));
    }
}
```

Ở đây `DocumentText(Path)` là constructor **bổ sung**, nên có thể khai báo `throws IOException`. Nó vẫn phải **bắt đầu** bằng `this(...)`. Java sẽ đánh giá `Files.readString(path)` trước khi gọi canonical constructor `DocumentText(String)`. Nếu việc đọc file thất bại, canonical constructor không được gọi.

Trong khi đó, **canonical constructor** `DocumentText(String)` không được khai báo `throws IOException`. Nếu cần báo lỗi kiểm tra ngay trong canonical, hãy sử dụng ngoại lệ không kiểm tra phù hợp (như `IllegalArgumentException`) hoặc thiết kế xử lý lỗi ở bước gọi.

## 7. Chuẩn hóa tham số trước `this(...)` thế nào cho đúng Java 17?

Một lỗi rất thường gặp là muốn tính giá trị trung gian rồi mới chuyển sang canonical:

```java
record Label(String text, String category) {
    Label(String text) {
        // SAI: Java 17 không cho phép lệnh này đứng trước this(...).
        String normalized = text.strip();
        this(normalized, "GENERAL");
    }
}
```

Có ba hướng xử lý hợp lệ.

### Cách 1 — Chuẩn hóa trực tiếp ở canonical constructor (thường nên dùng)

```java
import java.util.Objects;

record Label(String text, String category) {
    Label {
        text = Objects.requireNonNull(text, "text").strip();
        category = Objects.requireNonNull(category, "category").strip();
        if (text.isBlank() || category.isBlank()) {
            throw new IllegalArgumentException("Các trường không được rỗng");
        }
    }

    Label(String text) {
        this(text, "GENERAL");
    }
}
```

Mọi đường tạo `Label` đều sử dụng cùng logic chuẩn hóa; không ai có thể bỏ qua quy tắc chỉ bằng cách gọi constructor đủ tham số.

### Cách 2 — Gọi phương thức tĩnh trong đối số của `this(...)`

```java
import java.util.Locale;
import java.util.Objects;

record Label(String text, String category) {
    Label(String text) {
        this(normalize(text), "GENERAL");
    }

    private static String normalize(String value) {
        return Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);
    }
}
```

Trong Java 17, phương thức tĩnh không phụ thuộc đối tượng có thể được gọi khi **tính các biểu thức đối số** cho `this(...)`. Nếu quá trình chuẩn hóa là một invariant dùng cho mọi cách tạo, hãy đặt nó ở canonical constructor thay vì chỉ trong một overload.

### Cách 3 — Dùng static factory method có tên

```java
record Distance(double meters) {
    Distance {
        if (!Double.isFinite(meters) || meters < 0) {
            throw new IllegalArgumentException("meters không hợp lệ");
        }
    }

    static Distance fromKilometers(double kilometers) {
        return new Distance(kilometers * 1000);
    }
}
```

Sử dụng:

```java
Distance distance = Distance.fromKilometers(2.5);
System.out.println(distance.meters()); // 2500.0
```

Static factory method đặc biệt hữu ích khi nhiều cách tạo đều nhận **cùng kiểu tham số** nhưng khác ý nghĩa. Ví dụ, không nên cố thêm hai constructor `Distance(double)` để phân biệt “mét” và “kilômét”: Java phân biệt overload qua chữ ký chứ không qua tên tham số hay ý nghĩa nghiệp vụ.

## 8. Constructor bổ sung, danh sách mutable và tính bất biến của record

Record có các trường component dạng `final`, nhưng nếu component trỏ tới một danh sách mutable, đối tượng bên ngoài vẫn có thể sửa danh sách. Để record biểu diễn snapshot đáng tin cậy, hãy sao chép phòng vệ **ở canonical constructor**.

```java
import java.util.List;
import java.util.Objects;

record Basket(List<String> productCodes) {

    Basket {
        productCodes = List.copyOf(
                Objects.requireNonNull(productCodes, "productCodes"));
    }

    Basket() {
        this(List.of());
    }

    Basket(String firstProductCode) {
        this(List.of(firstProductCode));
    }
}
```

Sử dụng:

```java
import java.util.ArrayList;
import java.util.List;

class BasketDemo {
    public static void main(String[] args) {
        List<String> codes = new ArrayList<>();
        codes.add("P-1");

        Basket basket = new Basket(codes);
        codes.add("P-2");

        System.out.println(basket.productCodes()); // [P-1]
        System.out.println(new Basket());           // Basket[productCodes=[]]
        System.out.println(new Basket("P-3"));      // Basket[productCodes=[P-3]]
    }
}
```

Mọi constructor bổ sung đều chuyển đến canonical constructor và qua `List.copyOf(...)`, vì vậy không có overload nào vô tình bỏ qua việc sao chép. `List.copyOf` tạo một danh sách không thể sửa cấu trúc và không chấp nhận phần tử `null`. Nếu danh sách chứa **đối tượng con mutable** thì cần chiến lược bất biến sâu riêng; `List.copyOf` không tự sao chép sâu các phần tử.

Điểm thiết kế đáng nhớ: **quy tắc kiểm tra và bảo vệ dữ liệu thuộc canonical constructor**, còn constructor bổ sung chủ yếu chọn giá trị mặc định hoặc định dạng đầu vào.

## 9. Generic record và các constructor bổ sung

Record có thể khai báo tham số kiểu, và constructor overload có thể dùng chúng một cách bình thường:

```java
import java.util.Objects;

record Response<T>(T data, String source) {

    Response {
        Objects.requireNonNull(data, "data");
        Objects.requireNonNull(source, "source");
    }

    Response(T data) {
        this(data, "unknown");
    }
}
```

Sử dụng:

```java
Response<String> text = new Response<>("Hello");
Response<Integer> number = new Response<>(42, "cache");

System.out.println(text);   // Response[data=Hello, source=unknown]
System.out.println(number); // Response[data=42, source=cache]
```

Khi record có type parameter `T`, canonical constructor tương ứng vẫn là `Response(T data, String source)` và `Response(T data)` là overload. Java thực hiện kiểm tra kiểu khi biên dịch; không cần viết lại constructor với một tên kiểu cụ thể cho mỗi `T`.

Một điểm cần lưu ý: record có constructor nhận các kiểu tham chiếu gần nhau có thể gây **nhập nhằng overload**, đặc biệt khi truyền literal `null`. Ví dụ:

```java
record Code(String value) {
    Code(Integer number) {
        this(String.valueOf(number));
    }
}

// new Code(null); // SAI: không biết chọn Code(String) hay Code(Integer)
```

Hãy truyền giá trị có kiểu cụ thể, dùng ép kiểu rõ ràng khi thật sự cần, hoặc thiết kế static factory method mang tên mô tả đầu vào như `Code.fromNumber(123)`. Đừng lạm dụng overload nếu nó làm API khó dự đoán.

## 10. Những lỗi biên dịch thường gặp

### 10.1. Không gọi `this(...)` ở constructor bổ sung

```java
record Person(String name, int age) {
    Person(String name) {
        // SAI: không thể tự gán field và kết thúc tại đây.
        // this.name = name;
        // this.age = 0;
    }
}
```

**Cách sửa:**

```java
record Person(String name, int age) {
    Person(String name) {
        this(name, 0);
    }
}
```

### 10.2. Đặt lệnh trước `this(...)` trong JDK 17

```java
record Point(int x, int y) {
    Point(int x) {
        // SAI trong Java 17:
        // System.out.println("Tạo Point");
        // this(x, 0);
        this(x, 0);
    }
}
```

Lệnh `this(...)` phải đứng đầu; nếu cần kiểm tra hoặc biến đổi giá trị trước khi khởi tạo, ưu tiên canonical constructor.

### 10.3. Canonical constructor và compact constructor khai báo trùng

```java
record Name(String value) {
    // Không thể khai báo cả hai dạng canonical sau cùng lúc:
    //
    // Name(String value) {
    //     this.value = value;
    // }
    //
    // Name {
    //     value = value.strip();
    // }
}
```

Chọn **một** trong hai dạng. Không có hai canonical constructor cùng tồn tại.

### 10.4. Gán trực tiếp trường component trong compact constructor

```java
record Name(String value) {
    Name {
        // SAI: this.value = value.strip();
        value = value.strip(); // ĐÚNG
    }
}
```

Java tự gán tham số `value` đã chuẩn hóa vào trường `this.value` khi compact constructor hoàn thành bình thường.

### 10.5. Constructor gọi vòng qua lại

```java
record Pair(int left, int right) {
    Pair(int only) {
        // SAI nếu overload không tham số gọi ngược về đây.
        // this();
        this(only, 0);
    }

    Pair() {
        this(0);
    }
}
```

Phiên bản hiện tại hợp lệ vì `Pair() → Pair(int) → Pair(int, int)`. Nếu thay `this(only, 0)` thành `this()` trong `Pair(int)`, sẽ tạo vòng lặp `Pair() ↔ Pair(int)` và bị từ chối khi biên dịch.

### 10.6. Không thể đặt trường instance tùy ý trong record

```java
record Session(String id) {
    // SAI: record không cho tự thêm instance field.
    // private int retries;

    static final int MAX_RETRIES = 3; // HỢP LỆ: static field
}
```

Constructor overload không biến record thành một lớp mutable thông thường. Nếu dữ liệu là trạng thái bản ghi, hãy biểu diễn bằng component. Nếu cần lifecycle/stateful object phức tạp, cân nhắc class thông thường.

### 10.7. Không dùng `return` hoặc `this(...)` trong compact canonical constructor

```java
record Quantity(int value) {
    Quantity {
        if (value < 0) {
            throw new IllegalArgumentException("value phải >= 0");
        }

        // SAI:
        // return;
        // this(value);
    }
}
```

Compact constructor hoàn tất theo cơ chế khởi tạo ngầm của compiler. Để báo dữ liệu không hợp lệ, dùng exception phù hợp.

## 11. Tổ chức constructor trong API thật

Với một public record phục vụ nhiều lớp khác nhau, cấu trúc khuyến nghị:

```java
import java.math.BigDecimal;
import java.util.Objects;

public record OrderLine(String productId,
                        int quantity,
                        BigDecimal unitPrice) {

    // Bảo vệ dữ liệu bất kể người gọi chọn constructor nào.
    public OrderLine {
        productId = Objects.requireNonNull(
                productId, "productId").strip();
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (productId.isEmpty()) {
            throw new IllegalArgumentException("productId không được rỗng");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải > 0");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice phải >= 0");
        }
    }

    // Một sản phẩm, số lượng mặc định 1.
    public OrderLine(String productId, BigDecimal unitPrice) {
        this(productId, 1, unitPrice);
    }

    // Chỉ dùng khi phía gọi đưa đơn giá dưới dạng chuỗi thập phân.
    public OrderLine(String productId, int quantity, String unitPrice) {
        this(productId, quantity, new BigDecimal(unitPrice));
    }

    public BigDecimal total() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

Ba cách khởi tạo tương ứng:

```java
OrderLine full = new OrderLine("P-1", 3, new BigDecimal("12.50"));
OrderLine defaultQuantity = new OrderLine("P-2", new BigDecimal("8.00"));
OrderLine parsedPrice = new OrderLine("P-3", 2, "7.25");

System.out.println(full.total());            // 37.50
System.out.println(defaultQuantity.total()); // 8.00
System.out.println(parsedPrice.total());     // 14.50
```

Constructor nhận `String unitPrice` sẽ ném `NumberFormatException` nếu chuỗi không phải số thập phân hợp lệ; đó là hành vi phù hợp với cách `BigDecimal(String)` chuyển đổi. Nếu API cần thông báo lỗi riêng, có thể thay bằng static factory method có xử lý lỗi rõ ràng hoặc helper tĩnh trong biểu thức `this(...)`.

### Nguyên tắc thiết kế để tránh lỗi lâu dài

- Giữ danh sách overload **ít và có ý nghĩa**. Mỗi constructor nên cung cấp một phương thức khởi tạo mà người sử dụng dễ đoán.
- Đưa invariant và chuẩn hóa chung vào **canonical constructor**, tránh kiểm tra lặp ở nhiều overload.
- Cho mỗi constructor bổ sung gọi `this(...)` ngay đầu, ưu tiên lời gọi ngắn gọn, dễ đọc.
- Tránh các overload chỉ khác những tham số cùng kiểu với ý nghĩa dễ nhầm; dùng **static factory có tên** khi cần.
- Kiểm soát dữ liệu mutable qua defensive copy ngay tại canonical constructor.
- Đảm bảo chính sách truy cập: public record phải có canonical constructor đủ phạm vi `public` nếu tự khai báo.
- Với serialization, mapping JSON, ORM hay framework, cần kiểm tra cách thư viện tạo record và hỗ trợ canonical constructor. Không nên dựa vào một constructor tiện ích để thực thi invariant bắt buộc: thư viện có thể gọi canonical constructor trực tiếp.

## 12. Bài tập thực hành

### Bài 1 — Constructor mặc định

Viết record `Page(int number, int size)` có:

1. Compact canonical constructor kiểm tra `number >= 1` và `1 <= size <= 100`.
2. Constructor `Page(int number)` tự đặt `size = 20`.
3. Constructor `Page()` tự tạo trang đầu tiên, kích thước mặc định 20.
4. Chạy `new Page()`, `new Page(3)`, `new Page(2, 50)`; in từng record.

**Gợi ý lời giải:**

```java
record Page(int number, int size) {
    Page {
        if (number < 1) {
            throw new IllegalArgumentException("number phải >= 1");
        }
        if (size < 1 || size > 100) {
            throw new IllegalArgumentException("size phải nằm trong 1..100");
        }
    }

    Page(int number) {
        this(number, 20);
    }

    Page() {
        this(1);
    }
}
```

Chú ý chuỗi gọi của `new Page()` là `Page() → Page(int) → Page(int, int)`.

### Bài 2 — Phát hiện constructor không hợp lệ

Cho mã:

```java
record UserProfile(String username, int age) {
    UserProfile(String username) {
        username = username.trim();
        this(username, 18);
    }
}
```

**Câu hỏi:** Vì sao mã không biên dịch trong Java 17? Hãy sửa để mọi đường khởi tạo đều kiểm tra username không rỗng.

**Gợi ý:** Di chuyển bước chuẩn hóa vào compact canonical constructor; thay overload thành một lời gọi `this(username, 18)` đứng đầu.

**Lời giải:**

```java
record UserProfile(String username, int age) {
    UserProfile {
        username = java.util.Objects.requireNonNull(
                username, "username").strip();
        if (username.isBlank()) {
            throw new IllegalArgumentException("username không hợp lệ");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age không hợp lệ");
        }
    }

    UserProfile(String username) {
        this(username, 18);
    }
}
```

### Bài 3 — Phân biệt overload với factory

Bạn muốn tạo `Temperature(double celsius)` từ Celsius và Fahrenheit. Việc viết hai constructor `Temperature(double)` với ý nghĩa khác nhau là không thể vì chúng trùng chữ ký.

**Yêu cầu:** giữ canonical constructor để nhận Celsius và thêm một static factory `fromFahrenheit(double)`:

```java
record Temperature(double celsius) {
    Temperature {
        if (!Double.isFinite(celsius)) {
            throw new IllegalArgumentException("Nhiệt độ không hữu hạn");
        }
    }

    static Temperature fromFahrenheit(double fahrenheit) {
        return new Temperature((fahrenheit - 32.0) * 5.0 / 9.0);
    }
}
```

Thử `Temperature.fromFahrenheit(212)` và quan sát giá trị Celsius xấp xỉ `100.0`.

### Bài 4 — Constructor nhận dữ liệu từ file

Từ ví dụ `DocumentText(String content)`, thêm constructor `DocumentText(Path path) throws IOException` và giải thích:

- Vì sao constructor này được phép khai báo `throws IOException`?
- Vì sao lời gọi `this(Files.readString(path))` hợp lệ trong Java 17?
- Khi `Files.readString` thất bại, canonical constructor có chạy không?

**Định hướng:** Đây là constructor bổ sung, `this(...)` là lệnh đầu tiên và đối số được tính trước khi constructor đích được gọi. Nếu việc đọc file phát sinh exception, chuỗi gọi dừng tại đó.

## 13. Ghi nhớ nhanh

| Câu hỏi | Quy tắc Java 17 |
|---|---|
| Record có bao nhiêu canonical constructor? | Đúng một; được sinh ngầm, viết đầy đủ hoặc viết compact |
| Constructor không có đủ component có được phép không? | Có; đó là constructor bổ sung với chữ ký khác canonical |
| Constructor bổ sung bắt buộc làm gì? | **Bắt đầu** bằng `this(...)` đến constructor khác trong cùng record |
| Có thể gọi `this(...)` qua nhiều overload? | Có, nhưng chuỗi phải kết thúc ở canonical, không được tạo vòng gọi |
| Có thể đặt lệnh trước `this(...)`? | **Không trong Java 17** |
| Có thể gọi `super(...)` trong overload? | Không |
| Compact constructor có được gán `this.field`? | Không; gán vào tham số component, Java tự gán field |
| Có thể vừa khai báo compact vừa canonical đầy đủ? | Không; trùng canonical constructor |
| Canonical constructor có được `throws` checked exception? | Không được khai báo `throws` clause |
| Constructor bổ sung có được khai báo `throws`? | Có, theo quy tắc constructor thông thường |
| `public record` tự khai báo canonical có thể dùng `private`? | Không; canonical constructor phải `public` |
| Nên đặt validation ở đâu? | Canonical constructor để mọi đường tạo đều tuân thủ |

## 14. Tài liệu chính thức của Java 17

- [Java Language Specification 17 — `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): cú pháp và các giới hạn của record.
- [JLS 17 — `8.10.4 Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): canonical constructor, constructor bổ sung và yêu cầu constructor bổ sung **bắt đầu** bằng alternate constructor invocation.
- [JLS 17 — `8.10.4.1 Normal Canonical Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4.1): tên/kiểu tham số, giới hạn `throws`, loại trừ `this(...)` và `super(...)`.
- [JLS 17 — `8.10.4.2 Compact Canonical Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4.2): chuẩn hóa tham số và phép gán ngầm cho field.
- [JLS 17 — `8.8.7.1 Explicit Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8.7.1): `this(...)` và `super(...)`.
- [JEP 395 — Records](https://openjdk.org/jeps/395): tính năng record chính thức từ Java 16 và được hỗ trợ đầy đủ trong Java 17.
- [dev.java — Using Records to Model Immutable Data](https://dev.java/learn/using-record-to-model-immutable-data/): ví dụ và hướng dẫn về canonical/compact constructor.

**Điểm cốt lõi:** Constructor bổ sung giúp record thuận tiện hơn khi khởi tạo, nhưng không thay thế canonical constructor. Trong **Java 17**, mỗi overload phải mở đầu bằng `this(...)`; canonical constructor là nơi hoàn tất khởi tạo tất cả record components và là nơi thích hợp để giữ những quy tắc dữ liệu luôn đúng.
