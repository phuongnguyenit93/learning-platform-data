# Record lồng nhau và ngữ cảnh `static` trong Java hiện đại

## 1. Mục tiêu và bối cảnh phiên bản

Record là một kiểu lớp mang dữ liệu của Java: header của `record` khai báo các *record components*; Java cung cấp component fields `private final`, các accessor, canonical constructor, `equals`, `hashCode` và `toString` tương ứng. Record phù hợp với DTO, giá trị nghiệp vụ và dữ liệu trung gian cần một tập thành phần rõ ràng. Record là lớp `final`, có thể khai báo phương thức riêng, và chỉ bảo đảm **bất biến nông** nếu các component chứa object có thể thay đổi.

**Mốc lịch sử chính xác:** Java 14 giới thiệu record ở mức *preview* (JEP 359); đến **Java 16**, record mới chính thức (JEP 395). Bài này dùng ngữ nghĩa và cú pháp ổn định của **Java 17 trở lên**, không dùng cờ preview hay quy tắc hạn chế đã lỗi thời từ giai đoạn thử nghiệm.

Record có thể được khai báo ở ba vị trí:

| Dạng khai báo | Ví dụ | Có `static` ngầm định không? | Phạm vi dùng |
| --- | --- | --- | --- |
| **Top-level record** | `record Point(int x, int y) {}` | Không; không được thêm `static` ở top level | Tên kiểu cấp package |
| **Member record** trong một lớp/record/interface | `class Graph { record Edge(int from, int to) {} }` | **Có** | Thành viên của kiểu bao |
| **Local record** trong một block | `void run() { record Score(int value) {} }` | **Có** | Chỉ trong phạm vi block |

Theo **JLS 8.10**, *mọi nested record đều implicitly static*: điều này bao gồm **member record** và **local record**. Dù được viết trong một phương thức instance, trong inner class hoặc trong record khác, nested record không có tham chiếu ngầm tới đối tượng của lớp bao.

Sau bài này, bạn có thể phân biệt record lồng nhau với inner class, dùng member/local records đúng phạm vi, truy cập hợp lệ dữ liệu static của lớp bao, truyền rõ dữ liệu instance cần thiết, tổ chức records trong class generic/interface/inner class và đọc đúng các lỗi biên dịch.

## 2. `static` ngầm định nghĩa là gì?

Với member record:

```java
class Geometry {
    record Point(int x, int y) {
        int manhattan() {
            return Math.abs(x) + Math.abs(y);
        }
    }
}
```

Đây là một **khai báo kiểu** hợp lệ. Trong code có quyền truy cập `Geometry.Point`, ta có thể viết:

```java
Geometry.Point p = new Geometry.Point(3, 4);
System.out.println(p.manhattan()); // 7
```

Không cần khởi tạo `Geometry`. Việc thêm `static` trước `record Point(...)` trong thân lớp cũng hợp lệ, nhưng **thừa**, vì member record đã static. Tương tự, `record` bên trong một record khác cũng là một member record static.

Cần hiểu `static` ở đây nói về **kiểu lồng nhau và mối quan hệ với đối tượng bao**, chứ **không** nói rằng chỉ tồn tại một đối tượng record. Mỗi lần `new Geometry.Point(...)` vẫn tạo một đối tượng mới. Component fields `x`, `y` là trạng thái instance của từng `Point`. Chỉ những trường khai báo `static` trong body của record mới là biến lớp.

### 2.1. Khác biệt giữa member record và non-static inner class

```java
class Office {
    private final String name;

    Office(String name) {
        this.name = name;
    }

    class Employee {
        String officeName() {
            return name; // Inner class có enclosing Office instance.
        }
    }

    record Badge(String id) {
        String display() {
            return id; // Component thuộc chính Badge.
        }
    }
}
```

Đoạn này chỉ khai báo các kiểu, không chứa `main`.

- `Employee` là **inner class**: từ bên ngoài, thường phải tạo bằng `office.new Employee()`, trong đó `office` là một `Office` instance. Nó có thể truy cập `name` của enclosing instance.
- `Badge` là **nested member record**: tạo bằng `new Office.Badge("E01")` (khi được phép truy cập). Nó **không tự liên kết** tới một instance `Office`; `name` của `Office` không sẵn dùng bên trong `Badge`.
- `this` bên trong phương thức instance của `Badge` biểu thị đối tượng `Badge` hiện tại. Không có `Office.this` cho record này.
- Quyền truy cập member `private` giữa các kiểu cùng nest trong Java không tự sinh ra một đối tượng bao. Có quyền gọi member của `Office` khác với có một `Office` instance để gọi.

Do đó, **xóa từ khóa `static`** khỏi member record không biến nó thành inner class. Record lồng nhau không có phiên bản non-static để capture enclosing instance.

### 2.2. Nested record vẫn có phương thức instance của chính nó

```java
class IdFactory {
    private static final String PREFIX = "ID-";

    record Key(String code) {
        String label() {
            return PREFIX + code.strip();
        }
    }
}
```

`Key.label()` là phương thức **instance**, dùng component `code` của chính `Key` và trường `PREFIX` **static** của `IdFactory`. Hai quyền truy cập này đều hợp lệ. Nếu `PREFIX` là instance field của `IdFactory`, phương thức `label()` không thể dùng tên `PREFIX` trực tiếp như trên.

Record cũng có thể khai báo các phương thức static của **chính record**:

```java
record Metric(int count) {
    static final int UNIT = 10;

    int scaled() {
        return count * UNIT;
    }

    static Metric zero() {
        return new Metric(0);
    }
}
```

`scaled()` hoạt động trên một `Metric` instance; `zero()` là static factory. `static` của khai báo kiểu lồng nhau không hề buộc **mọi phương thức** trong record phải là static.

## 3. Local record: cấu trúc dữ liệu chỉ dùng trong một block

Local record được khai báo **bên trong block**, thường là thân phương thức, để mô hình hóa một bộ dữ liệu phục vụ một thuật toán nhỏ. Ví dụ một bước tổng hợp kết quả:

```java
void summarize(int bonus) {
    record Score(String student, int points) {
        int finalPoints() {
            return points + 1;
        }
    }

    Score score = new Score("An", bonus);
    System.out.println(score.finalPoints());
}
```

Đây là **một phương thức cần đặt trong lớp**. Với `bonus = 9`, nó in `10`. Dòng `new Score("An", bonus)` đọc `bonus` ngay trong phương thức bao ngoài rồi **truyền giá trị vào component `points`**. Trong `Score.finalPoints()`, mã đọc `points`, không đọc trực tiếp `bonus`.

**Đặc điểm của local record:**

1. **Implicitly static** kể cả được khai báo trong một instance method.
2. Không có enclosing instance ngầm định của lớp chứa phương thức.
3. **Không capture biến local** của phương thức bao ngoài, kể cả biến `final` hoặc *effectively final*. Nó cũng không trực tiếp tham chiếu các tham số phương thức bao ngoài.
4. Không truy cập trực tiếp instance fields/instance methods của lớp bao khi chưa có một đối tượng tường minh.
5. Có thể sử dụng thành viên `static` trong phạm vi và theo các quy tắc truy cập Java.
6. Tên local record chỉ có hiệu lực trong block, không tạo member type công khai dạng `Outer.Score`.
7. **Không được ghi modifier `static`** cho local record; mặc dù tính chất static là ngầm định, ngữ pháp local declaration không cho phép từ khóa này. Nó cũng không được khai báo `public`, `private` hoặc `protected` như một member class.

So sánh với **local class** thường: local class có thể capture một biến ngoài *effectively final*, còn **local record không thể**. Đây là khác biệt cần nắm khi đưa record vào thuật toán xử lý streams, grouping hoặc sorting.

## 4. Chương trình tổng hợp: member, local, generic và inner class

**Tệp `NestedRecordsDemo.java`, Java 17+:**

```java
import java.util.Objects;

public class NestedRecordsDemo {
    private static final String PREFIX = "ID-";
    private final String owner;

    NestedRecordsDemo(String owner) {
        this.owner = owner;
    }

    // Member record: mặc nhiên static.
    public record Item(String name, int quantity) {
        public Item {
            name = Objects.requireNonNull(name, "name").strip();
            if (name.isEmpty() || quantity < 0) {
                throw new IllegalArgumentException("invalid item");
            }
        }

        public String label() {
            return PREFIX + name + ":" + quantity;
        }
    }

    private record Audit(String action, int number) {}

    void showLocal(int extra) {
        // Local record: mặc nhiên static ngay trong instance method.
        record Score(String student, int points) {
            String display() {
                return student + ":" + points + "@" + PREFIX;
            }
        }

        Score score = new Score("An", extra);
        System.out.println(score);
        System.out.println(score.display());
    }

    // Inner class không static vẫn được khai báo member record.
    public class Session {
        public record Task(String title, int size) {}

        void showTask() {
            System.out.println(new Task("compile", 3));
        }
    }

    // Kiểu generic bao không cấp type parameter cho nested record.
    static class Container<T> {
        record Cell<U>(U value) {}
    }

    public static void main(String[] args) {
        NestedRecordsDemo outer = new NestedRecordsDemo("Team");
        Item item = new Item("  Pen  ", 2);

        System.out.println(item);
        System.out.println(item.label());
        System.out.println(outer.owner);
        System.out.println(new Audit("created", 1));

        outer.showLocal(9);
        outer.new Session().showTask();

        Session.Task job = new Session.Task("review", 2);
        System.out.println(job);
        System.out.println(new Container.Cell<String>("ok"));
        System.out.println(Item.class.isRecord());
    }
}
```

Biên dịch bằng các quy tắc chuẩn Java 17 rồi chạy:

```bash
javac --release 17 -encoding UTF-8 NestedRecordsDemo.java
java NestedRecordsDemo
```

**Stdout chính xác:**

```text
Item[name=Pen, quantity=2]
ID-Pen:2
Team
Audit[action=created, number=1]
Score[student=An, points=9]
An:9@ID-
Task[title=compile, size=3]
Task[title=review, size=2]
Cell[value=ok]
true
```

### 4.1. Phân tích những cơ chế quan trọng

- `Item` là **member record public**. Phương thức instance `label()` dùng `PREFIX` static của lớp bao và hai component của chính `Item`. Nó không truy cập `owner`; `owner` thuộc một instance cụ thể của `NestedRecordsDemo`.
- Compact canonical constructor `public Item { ... }` của `Item` chuẩn hóa tên và kiểm tra số lượng. Do đó tên `"  Pen  "` được lưu thành `"Pen"`. Quy tắc canonical constructor áp dụng cho record lồng nhau như mọi record khác.
- `Audit` được khai báo `private`; lớp bao vẫn có thể dùng, nhưng ngoài phạm vi được quyền thì không. Implicit static **không** đồng nghĩa public.
- Local record `Score` đọc `PREFIX` static hợp lệ. Biến tham số `extra` chỉ được đọc trong `showLocal` để **truyền thành `points`**; `Score.display()` không capture `extra`.
- `Session` là **non-static inner class**. Để chạy phương thức của nó, mã tạo `outer.new Session()`. Ngược lại, `Task` là member record bên trong `Session` nên **static ngầm định**: `new Session.Task("review", 2)` **không cần một Session object**.
- `Container<T>` là class generic. `Cell<U>` khai báo type parameter `U` riêng, vì record static không tự dùng type parameter `T` của lớp bao.
- `Item.class.isRecord()` là reflection API báo object `Class` này biểu diễn một record. Việc chương trình in `true` chứng minh dạng lớp, không chứng minh có enclosing instance.

## 5. Record khai báo trong non-static inner class: Java 16+

Trường hợp `Session.Task` thường gây bất ngờ. Trước Java 16, các quy định cũ giới hạn việc khai báo static members trong inner class. **Java 16 trở lên đã nới quy tắc này**, bao gồm member record static ngầm định. Vì vậy trong Java hiện đại, ví dụ sau là hợp lệ:

```java
class Outer {
    class Inner {
        record Job(int id) {}
    }
}
```

Đây là **đoạn khai báo kiểu**, không có `main`. Trong nơi có quyền truy cập, có thể viết:

```java
Outer.Inner.Job job = new Outer.Inner.Job(7);
System.out.println(job.id()); // 7
```

Không cần `new Outer().new Inner()` để tạo `Job`, bởi `Job` **không phải inner class** dù được khai báo bên trong `Inner`. Đường dẫn tên `Outer.Inner.Job` chỉ nói **vị trí khai báo kiểu**.

**Không học lại giới hạn của Java 14 preview** như một quy tắc còn hiệu lực. Tài liệu chính thức Java 17/25 xác nhận record member nằm trong inner class là hợp lệ kể từ Java 16.

## 6. Lỗi không capture: từ “static context” đến cách truyền input rõ ràng

### 6.1. Ví dụ cố ý không biên dịch

**Tệp `InvalidCapture.java`:**

```java
class InvalidCapture {
    private int base = 10;

    void test(int delta) {
        record Sum(int value) {
            int total() {
                return value + base + delta;
            }
        }
    }
}
```

`javac` bác bỏ `base` và `delta` khi được tham chiếu trực tiếp trong local record. `base` là instance field của lớp bao; `delta` là tham số phương thức bao. Nested record static **không có đối tượng bao và không capture tham số**, cho dù record được khai báo ngay trong `test(...)`.

Không sửa bằng cách thêm `static` hay bỏ `static` khỏi record. Cách đúng là truyền các giá trị làm component, hoặc đưa vào một object ngữ cảnh được truyền **tường minh**.

### 6.2. Cách sửa chạy được: đưa ngữ cảnh thành record components

**Tệp `ExplicitStateDemo.java` — Java 17+:**

```java
public class ExplicitStateDemo {
    private static final int OFFSET = 100;
    private final String region;

    ExplicitStateDemo(String region) {
        this.region = region;
    }

    record Reading(String region, int raw) {
        String label() {
            return region + ":" + (raw + OFFSET);
        }
    }

    void print(int raw) {
        record Tag(String region, int raw) {
            String text() {
                return region + "=" + (raw + OFFSET);
            }
        }

        // Đây là phương thức instance, nên đọc region và raw hợp lệ.
        Tag tag = new Tag(region, raw);
        System.out.println(tag.text());
        System.out.println(new Reading(region, raw).label());
    }

    public static void main(String[] args) {
        new ExplicitStateDemo("north").print(7);
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ExplicitStateDemo.java
java ExplicitStateDemo
```

**Stdout chính xác:**

```text
north=107
north:107
```

Ở lời gọi `new Tag(region, raw)`, việc đọc `region` và `raw` diễn ra trong **phương thức instance `print`**, nơi chúng có nghĩa rõ ràng. Sau khi tạo `Tag`, mọi dữ liệu cần thiết đã nằm ở component `region` và `raw` của `Tag`. `Tag.text()` chỉ đọc các component của chính nó và `OFFSET` static.

Nếu cần record giữ một tham chiếu tới một object khác, có thể khai báo một component kiểu object, chẳng hạn `record Snapshot(Owner owner, String name) {}`; khi đó truy cập bằng `owner.someMethod()` sau khi bảo đảm `owner` hợp lệ. Đó là **phụ thuộc được truyền tường minh** và có thể ảnh hưởng tới vòng đời object, không phải tham chiếu `Outer.this` ngầm định.

### 6.3. Đối chiếu local class có capture

```java
void compare(int bonus) {
    class LocalClass {
        int sum(int n) {
            return n + bonus; // Hợp lệ nếu bonus effectively final.
        }
    }

    record LocalRecord(int n) {
        // int sum() { return n + bonus; } // Không hợp lệ.
    }

    System.out.println(new LocalClass().sum(3));
    System.out.println(new LocalRecord(3).n());
}
```

Đây là **đoạn phương thức minh họa**, không phải chương trình độc lập. `LocalClass` có thể capture `bonus` vì biến effectively final. `LocalRecord` không thể capture `bonus` vì nó implicitly static. Muốn dùng `bonus` trong record, đổi header thành `record LocalRecord(int n, int bonus)`, rồi tạo `new LocalRecord(3, bonus)`.

## 7. Generic outer class và giới hạn của static context

Một member record trong class generic **không tự thừa hưởng** type parameter của lớp bao.

**Mã sai, bị compiler từ chối:**

```java
class OuterGeneric<T> {
    record Entry(T value) {}
}
```

Lỗi có ý nghĩa: `non-static type variable T cannot be referenced from a static context`. `T` ở đây là type parameter của `OuterGeneric<T>`; nested record không phụ thuộc vào instance hoặc cách tham số hóa của outer.

**Cách đúng: khai báo tham số kiểu riêng ở record.**

```java
class OuterGeneric<T> {
    record Entry<U>(U value) {}

    Entry<T> wrap(T value) {
        return new Entry<>(value);
    }
}
```

`Entry<U>` có type parameter `U` độc lập. Phương thức `wrap` thuộc outer generic class được phép sử dụng `T`, nên nó có thể gọi `new Entry<>(value)` để tạo `Entry<T>`. Đối với static member record, kiểu sử dụng thường có dạng `OuterGeneric.Entry<String>` (nếu quyền truy cập cho phép), không cần một instance `OuterGeneric<String>`.

Tương tự, local record bên trong generic method không được đọc trực tiếp type parameter `T` của phương thức bao; nó có thể tự khai báo `record Cell<U>(U value) {}` và nhận đầu vào từ mã bên ngoài record.

## 8. Record trong interface và record trong record khác

### 8.1. Interface có thể chứa record

**Tệp `InterfaceRecordDemo.java` (Java 17+):**

```java
interface Requests {
    record Command(String name) {}
}

public class InterfaceRecordDemo {
    public static void main(String[] args) {
        Requests.Command value = new Requests.Command("send");
        System.out.println(value.name());
    }
}
```

```bash
javac --release 17 InterfaceRecordDemo.java
java InterfaceRecordDemo
```

Kết quả:

```text
send
```

Một **member type khai báo trong interface** có nghĩa `public static` ngầm định. Do vậy `Requests.Command` là một nested member record public/static trong phạm vi mà `Requests` itself được phép truy cập. Với API dùng từ package khác, cần đặt interface `public` trong file riêng theo quy tắc Java; việc `Command` public không khiến một interface package-private tự trở thành public.

### 8.2. Record chứa member record

```java
record Order(String orderId, int amount) {
    record Line(String sku, int units) {}
}
```

`Order.Line` cũng implicitly static; `new Order.Line("P01", 2)` không đòi hỏi một đối tượng `Order`. Nếu yêu cầu nghiệp vụ thực sự gắn `Line` với một order cụ thể, hãy đưa `orderId` hoặc một thông tin liên kết rõ vào component, thay vì suy ra quan hệ từ cách đặt kiểu.

Nested record còn có thể có constructor kiểm tra điều kiện, static helpers, implement interface hoặc khai báo member type khác. Các quy tắc chuẩn của record vẫn áp dụng: final class, component fields final và không tự thêm instance fields ngoài components.

## 9. Quy tắc phạm vi và quyền truy cập

Một record lồng nhau có thể là **public, protected, private hoặc package-private** nếu vị trí khai báo member type cho phép. `private record CacheKey(String key)` hợp lý khi một lớp cần kiểu khóa cache nội bộ; việc implicitly static không làm nó được truy cập ở mọi nơi. Record public lồng trong một class public có thể trở thành một phần của API, người gọi dùng tên kiểu như `Api.Response`.

Ngược lại, local record nằm trong một block có **scope cục bộ** và không thể dùng làm kiểu được đặt tên bên ngoài block theo cú pháp thông thường. Không cố dùng modifier `public`/`private` cho local record. Nếu phải truyền dữ liệu của local record ra khỏi phương thức một cách công khai, cân nhắc chuyển contract thành member hoặc top-level record để API rõ ràng.

| Nhu cầu | Nơi khai báo phù hợp | Lý do |
| --- | --- | --- |
| DTO dùng ở nhiều module | Top-level record | Tên kiểu cấp package độc lập |
| Kiểu kết quả gắn chặt với một API | Member record trong class/interface | Tên như `Service.Result` thể hiện nhóm logic |
| Kiểu khóa/giá trị chỉ lớp bao dùng | `private` member record | Giữ API bên ngoài gọn |
| Dữ liệu tạm cho một phép tính/stream | Local record trong phương thức | Scope nhỏ; không phát sinh kiểu thành viên toàn lớp |
| Dữ liệu chỉ có trong non-static inner class | Member record trong inner class (Java 16+) | Không giữ outer instance, phù hợp Java 17+ |
| Cần capture state của phương thức | Truyền qua record components hoặc xem xét local class | Record không capture state ngầm |
| Cần nhiều kiểu generic | Khai báo type parameter trên record | Nested record không nhận type variable outer tự động |

**Nguyên tắc thiết kế:** Hãy khai báo record ở scope nhỏ nhất đủ phục vụ người dùng của nó. Việc record static ngầm định giúp giảm sự phụ thuộc vào vòng đời của outer object, nhưng một component chứa object mutable vẫn cần kiểm soát sao chép phòng vệ khi yêu cầu bất biến thực sự.

## 10. Lỗi thường gặp và cách sửa

### Lỗi A — Đọc instance field của outer class bằng tên trực tiếp

```java
class CustomerView {
    private String title = "VIP";

    record Label(String text) {
        // String full() { return title + text; } // SAI
    }
}
```

`Label` không có `CustomerView.this`. Sửa bằng `record Label(String title, String text)` và truyền `title` vào constructor trong phương thức của `CustomerView`.

### Lỗi B — Cho rằng local record capture biến effectively final

```java
void render(String prefix) {
    record Piece(String text) {
        // String show() { return prefix + text; } // SAI
    }

    Piece ok = new Piece(prefix + "A"); // HỢP LỆ.
}
```

Không thể dùng `prefix` trực tiếp trong phương thức của `Piece`; phép truyền value từ `render` khi gọi constructor thì hợp lệ. Muốn record giữ cả `prefix`, khai báo component riêng.

### Lỗi C — Ghi `static` trong khai báo local record

```java
void demo() {
    // static record Item(int id) {} // SAI: static modifier ở local.
    record Item(int id) {}           // ĐÚNG.
}
```

Trong **member declaration**, `static record Item(...)` được phép nhưng thừa. Trong **local declaration**, từ khóa `static` bị cấm dù local record implicitly static.

### Lỗi D — Dùng `T` từ generic outer

```java
class Store<T> {
    // record Box(T value) {} // SAI.
    record Box<U>(U value) {} // ĐÚNG.
}
```

Nested record static phải khai báo generic parameter của chính nó hoặc nhận một kiểu cụ thể. `T` của outer generic class không được capture.

### Lỗi E — Hiểu sai record trong inner class

```java
class Enclosing {
    class Inner {
        record Code(int value) {}
    }
}

// Khi được phép truy cập:
// Enclosing.Inner.Code code = new Enclosing.Inner.Code(42);
```

Đây là cú pháp hợp lệ trên Java 17+. Không cần tạo `new Enclosing().new Inner()` chỉ để khởi tạo `Code`. `Inner` là inner class, còn `Code` là nested record static ngầm định.

### Lỗi F — Tưởng mọi `static` đều là state dùng chung

Hai object `new Metric(1)` và `new Metric(2)` có component `count` khác nhau. `record Metric(int count)` có component instance; nested static chỉ nói không có outer instance, không biến `count` thành một static field chung.

### Lỗi G — Bỏ qua invariant và mutability khi record lồng nhau

Lồng record bên trong một lớp không tự động bảo đảm dữ liệu “đúng” hoặc bất biến sâu. Nếu có `record Group(List<String> members)`, list nguồn vẫn có thể bị sửa nếu chỉ lưu tham chiếu. Với invariant phù hợp, dùng compact canonical constructor và `List.copyOf(members)` để sao chép cấu trúc list, đồng thời cân nhắc phần tử mutable.

### Lỗi H — Dùng lại tài liệu preview Java 14

Record đã là tính năng chính thức từ Java 16; trên Java 17+ không cần `--enable-preview`. Cũng đừng lặp lại hạn chế cũ cho rằng inner class không được chứa record: quy tắc đã thay đổi từ Java 16.

## 11. Bài tập tự kiểm tra

1. **Member record:** tạo `class Warehouse` có `static final String ZONE = "A"` và member `record Location(String shelf, int number)`. Viết `label()` sử dụng `ZONE` và components; chứng minh không cần instance `Warehouse`.
2. **So sánh inner class:** thêm `class Scanner` (non-static) trong `Warehouse`. Viết code tạo `Scanner` rồi tạo `Location`; xác định trường hợp nào cần outer object.
3. **Local record:** trong phương thức `calculate(int bonus)`, tạo `record Item(int base, int bonus)`. Truyền `bonus` qua constructor và dùng trong phương thức của `Item`.
4. **Cố ý gây lỗi:** đổi phương thức của `Item` để truy cập trực tiếp `bonus` từ enclosing method thay vì component; dùng `javac` tìm lỗi, rồi sửa.
5. **Generic:** khai báo `class Holder<T>`, bên trong có `record Cell<U>(U value)` và `Cell<T> wrap(T item)`. Giải thích vì sao `record Cell(T value)` lỗi.
6. **Inner class chứa record:** viết `class Outer { class Inner { record Job(int id) {} } }` rồi tạo `new Outer.Inner.Job(7)`. Xác định phiên bản Java thấp nhất nơi cú pháp là tính năng chính thức.
7. **Scope:** so sánh dùng `private record CacheKey(...)` bên trong một service với local record chỉ dùng trong một phép map. Nêu lý do đặt từng kiểu.
8. **Interface:** khai báo `interface Commands { record Request(String action) {} }` và gọi `new Commands.Request("run")` từ cùng package.
9. **Nâng cao:** chuyển một record phụ thuộc trường instance của outer class sang giải pháp truyền context vào constructor; kiểm tra dữ liệu không bị tham chiếu ngầm.

**Đáp án định hướng:** (1) member record static dùng thành viên static; (2) inner class cần outer instance, member record không; (3–4) local record không capture biến phương thức, nhưng constructor có thể nhận giá trị đó; (5) khai báo generic riêng; (6) record chính thức Java 16, ví dụ chạy Java 17+; (7) dùng scope nhỏ nhất đủ cho contract; (8) member type của interface public/static ngầm định; (9) dependency tường minh qua component.

## 12. Tài liệu chính thức

- **Java Language Specification, Java SE 25, `8.10 — Record Classes:** phân loại top-level/member/local record và quy tắc **nested record implicitly static**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.10
- **JLS `8.1.3 — Inner Classes and Enclosing Instances:** phân biệt inner class, nested class và liên hệ tới outer instance: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.1.3
- **JLS `14.3 — Local Class and Interface Declarations:** phạm vi, modifier và quy tắc local record: https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.3
- **Oracle Java 25, Record Classes**, phần *Local Record Classes* và *Static Members of Inner Classes*: https://docs.oracle.com/en/java/javase/25/language/records.html
- **Oracle Java 17, Record Classes:** hướng dẫn về record ổn định trên JDK 17: https://docs.oracle.com/en/java/javase/17/language/records.html
- **OpenJDK JEP 395 — Records:** tính năng chính thức từ Java 16 và việc nới quy tắc static member của inner class: https://openjdk.org/jeps/395

**Ghi nhớ:** *Vị trí khai báo lồng nhau không có nghĩa record sở hữu một enclosing instance.* Member và local records đều **static ngầm định**, không tự capture state bên ngoài. Truyền mọi dữ liệu cần thiết qua components hoặc đối số rõ ràng để mã dễ kiểm chứng và phù hợp với Java hiện đại.