# Static member trong inner class và khả năng khai báo nested record

## 1. Thay đổi quan trọng từ Java 16

Một inner class là class lồng bên trong class khác và không được khai báo `static`. Từ Java 16, inner class được phép khai báo các thành viên `static`, bao gồm static field, static method, static initializer và member type.

Thay đổi này được đưa vào cùng việc hoàn thiện record trong JEP 395. Nó đặc biệt hữu ích vì một member record vốn **ngầm định là static**. Từ Java 16, ta có thể khai báo record bên trong một inner class:

~~~java
class Outer {
    class Inner {
        record Snapshot(String value) {}
    }
}
~~~

`Snapshot` là member record của `Inner`, không gắn với một instance `Inner` hay `Outer` cụ thể. Có thể tạo nó qua tên kiểu lồng:

~~~java
Outer.Inner.Snapshot snapshot =
    new Outer.Inner.Snapshot("Java 16");
~~~

Không cần tạo `Outer` hoặc `Inner` trước khi tạo `Snapshot`.

Điểm cần phân biệt: thay đổi này cho phép inner class có static members; nó **không biến chính inner class thành static**. Một object `Inner` vẫn cần enclosing instance của `Outer`, còn nested record `Snapshot` thì không.

Mục tiêu bài học:

- Hiểu inner class và static member type.
- Nhận biết các static member được phép khai báo trong inner class từ Java 16.
- Khai báo nested record bên trong inner class.
- Tạo nested record mà không cần enclosing instance.
- Phân biệt static context với instance context.
- Hiểu giới hạn truy cập outer instance member và type parameter.
- Áp dụng nested record để tổ chức kiểu dữ liệu liên quan.

## 2. Inner class vẫn là class không static

Xét class lồng thông thường:

~~~java
class Outer {
    private final String outerId;

    Outer(String outerId) {
        this.outerId = outerId;
    }

    class Inner {
        String describe() {
            return "Outer id: " + Outer.this.outerId;
        }
    }
}
~~~

`Inner` không khai báo `static`, nên mỗi object `Inner` gắn với một object `Outer`. Muốn tạo `Inner`, phải có enclosing instance:

~~~java
Outer outer = new Outer("OUT-01");
Outer.Inner inner = outer.new Inner();

System.out.println(inner.describe());
~~~

`Inner` có thể truy cập trực tiếp trạng thái instance của `Outer` thông qua enclosing instance, ví dụ `Outer.this.outerId`.

Java 16 không thay đổi quan hệ này. `Inner` vẫn là inner class và vẫn cần một object `Outer` khi tạo instance.

## 3. Từ Java 16, inner class có thể khai báo static members

Từ Java 16, inner class có thể khai báo các thành viên static hợp lệ. Ví dụ:

~~~java
class Outer {
    class Inner {
        static final String KIND = "inner";
        static int createdCount;

        static String describeKind() {
            return KIND;
        }

        static {
            createdCount = 0;
        }
    }
}
~~~

Các thành viên trên thuộc về kiểu `Inner`, không thuộc một instance `Inner` cụ thể:

- `KIND` là static field.
- `createdCount` là static field có thể thay đổi.
- `describeKind()` là static method.
- `static { ... }` là static initializer.

Có thể truy cập thành viên static qua tên kiểu:

~~~java
String kind = Outer.Inner.describeKind();
int count = Outer.Inner.createdCount;
~~~

Không cần tạo `Outer` hoặc `Inner` để truy cập các thành viên static này.

### Không nhầm static member với việc biến Inner thành static

Đoạn sau vẫn yêu cầu một `Outer` instance:

~~~java
Outer outer = new Outer("OUT-01");
Outer.Inner inner = outer.new Inner();
~~~

Còn việc truy cập static member không yêu cầu object:

~~~java
String kind = Outer.Inner.KIND;
~~~

Hai quy tắc cùng tồn tại: `Inner` vẫn là inner class, nhưng bản thân nó có thể sở hữu static members.

### Static field không chỉ giới hạn ở compile-time constant

Inner class có thể khai báo static field không phải constant variable:

~~~java
class Outer {
    class Inner {
        static int instanceCount = 0;
    }
}
~~~

`instanceCount` là trạng thái dùng chung ở cấp class. Nếu nhiều luồng cùng cập nhật field này, cần cơ chế đồng bộ phù hợp. Việc Java cho phép khai báo không có nghĩa mọi static mutable state đều là lựa chọn thiết kế tốt.

## 4. Nested record trong inner class

Record declaration là member type và member record ngầm định `static`. Vì Java 16 cho phép inner class khai báo static member type, nested record có thể xuất hiện bên trong inner class:

~~~java
class Outer {
    class Inner {
        record Snapshot(String id, int version) {}
    }
}
~~~

`Snapshot` có các đặc điểm:

- Là member record của `Inner`.
- Ngầm định static, không cần viết modifier `static`.
- Không giữ tham chiếu ẩn đến object `Inner`.
- Không giữ tham chiếu ẩn đến object `Outer`.
- Có thể được tạo độc lập qua tên `Outer.Inner.Snapshot`.

Ví dụ:

~~~java
Outer.Inner.Snapshot snapshot =
    new Outer.Inner.Snapshot("DOC-01", 3);

System.out.println(snapshot.id());
System.out.println(snapshot.version());
~~~

Không dùng cú pháp tạo inner class `outer.new Inner()` cho record:

~~~java
Outer outer = new Outer("OUT-01");

// Không hợp lệ: Snapshot là static member type.
// Outer.Inner.Snapshot snapshot = outer.new Inner().new Snapshot("DOC-01", 3);
~~~

Cú pháp tạo `Snapshot` là `new Outer.Inner.Snapshot(...)`, không cần một `Inner` object.

## 5. Nested record không truy cập trực tiếp outer instance

Do `Snapshot` là static member type, nó không có enclosing instance. Vì vậy, nó không thể dùng `Inner.this` hoặc `Outer.this` để đọc field instance:

~~~java
class Outer {
    private final String outerId = "OUT-01";

    class Inner {
        private int revision = 3;

        record Snapshot(String id) {
            String label() {
                // Không hợp lệ: record không có Inner.this hoặc Outer.this.
                // return Outer.this.outerId + ":" + Inner.this.revision + ":" + id;
                return id;
            }
        }
    }
}
~~~

Ngay cả khi nested record được khai báo bên trong inner class, nó không tự kế thừa enclosing instance của `Inner`.

### Truyền dữ liệu cần thiết thành component

Nếu record cần lưu giá trị lấy từ outer object, hãy truyền giá trị đó tường minh:

~~~java
class Outer {
    private final String outerId;

    Outer(String outerId) {
        this.outerId = outerId;
    }

    class Inner {
        private final int revision;

        Inner(int revision) {
            this.revision = revision;
        }

        record Snapshot(String outerId, int revision, String id) {}

        Snapshot createSnapshot(String id) {
            return new Snapshot(Outer.this.outerId, revision, id);
        }
    }
}
~~~

Method `createSnapshot()` thuộc instance `Inner`, nên nó có thể đọc `Outer.this.outerId` và `revision`. Sau đó nó truyền các giá trị vào constructor của `Snapshot`.

Bản thân `Snapshot` chỉ giữ ba component đã khai báo. Không có quan hệ enclosing instance ngầm định.

### Truyền outer object trực tiếp khi thật sự cần

Có thể khai báo outer object thành một component:

~~~java
class Outer {
    private final String outerId;

    Outer(String outerId) {
        this.outerId = outerId;
    }

    class Inner {
        record Snapshot(Outer owner, String id) {
            String ownerId() {
                return owner.outerId;
            }
        }
    }
}
~~~

Đây là một tham chiếu dữ liệu tường minh. Tuy nhiên, record sẽ giữ object `Outer` như một component; nếu `Outer` có trạng thái mutable hoặc vòng đời dài, việc giữ tham chiếu có thể làm snapshot phụ thuộc vào object đó. Nếu chỉ cần một vài giá trị, truyền các giá trị cần thiết thành component thường dễ hiểu và ít liên kết hơn.

## 6. Nested record có thể truy cập static member của inner class

Nested record không truy cập được instance field của `Inner`, nhưng có thể dùng static member của kiểu khai báo nó:

~~~java
class Outer {
    class Inner {
        private static final String PREFIX = "SNAP-";

        record Snapshot(String id, int version) {
            String displayId() {
                return PREFIX + id + "-v" + version;
            }
        }
    }
}
~~~

Sử dụng:

~~~java
Outer.Inner.Snapshot snapshot =
    new Outer.Inner.Snapshot("100", 2);

System.out.println(snapshot.displayId()); // SNAP-100-v2
~~~

`PREFIX` thuộc kiểu `Inner`, nên nested record có thể truy cập mà không cần instance `Inner`.

Điều này cũng áp dụng cho static member của outer class:

~~~java
class Outer {
    private static final String GLOBAL_PREFIX = "APP-";

    class Inner {
        record Snapshot(String id) {
            String key() {
                return GLOBAL_PREFIX + id;
            }
        }
    }
}
~~~

Nested record có thể dùng static member có thể truy cập theo quy tắc visibility của Java. Nó không thể dùng field instance của `Outer` hoặc `Inner` nếu không nhận object đó qua component hay tham số.

## 7. Static context và giới hạn type parameter

Static member không gắn với một lần tham số hóa cụ thể của outer generic class. Vì nested record là static member type, nó không thể sử dụng trực tiếp type parameter của outer class.

Ví dụ không hợp lệ:

~~~java
class Container<T> {
    class Inner {
        // Không hợp lệ: T thuộc Container<T>, còn Snapshot là static member type.
        // record Snapshot(T value) {}
    }
}
~~~

Nếu nested record cần kiểu dữ liệu tổng quát, hãy khai báo type parameter riêng:

~~~java
class Container<T> {
    class Inner {
        record Snapshot<U>(U value) {}
    }
}
~~~

`U` thuộc `Snapshot`, không phải type parameter được capture từ `Container<T>`.

Nếu cần mang một giá trị có kiểu tương ứng với `T`, có thể khai báo type parameter tường minh cho record:

~~~java
class Container<T> {
    class Inner {
        record Snapshot<V, U>(V outerValue, U detail) {}
    }
}
~~~

Khi tạo record từ ngữ cảnh biết `T`, truyền giá trị kiểu `T` vào tham số `V`. Quan hệ kiểu trở nên rõ ràng qua header thay vì phụ thuộc vào outer generic instance.

## 8. Kết hợp nested record với inner instance method

Inner class vẫn có instance method truy cập cả trạng thái của chính nó và outer object. Method đó có thể tạo nested record rồi truyền dữ liệu cần thiết vào:

~~~java
class OrderService {
    private final String serviceId;

    OrderService(String serviceId) {
        this.serviceId = serviceId;
    }

    class Processor {
        private final int attempt;

        Processor(int attempt) {
            this.attempt = attempt;
        }

        record ProcessingResult(
            String serviceId,
            int attempt,
            String status
        ) {}

        ProcessingResult complete() {
            return new ProcessingResult(
                OrderService.this.serviceId,
                attempt,
                "COMPLETED"
            );
        }
    }
}
~~~

Sử dụng:

~~~java
OrderService service = new OrderService("ORDER-SVC");
OrderService.Processor processor = service.new Processor(2);

OrderService.Processor.ProcessingResult result =
    processor.complete();

System.out.println(result);
~~~

Ở đây:

- `Processor` là inner class, nên phải tạo qua `service.new Processor(2)`.
- `ProcessingResult` là nested record, nên có thể tạo độc lập nếu đã biết các component.
- `complete()` có quyền đọc `OrderService.this.serviceId` và `attempt`, sau đó truyền giá trị vào record.
- `ProcessingResult` không tự giữ `OrderService` hoặc `Processor`.

Đây là cách kết hợp inner object có trạng thái với record kết quả có semantics giá trị.

## 9. Ví dụ hoàn chỉnh: inner class quản lý snapshot

Ví dụ sau thể hiện static field, static method và nested record bên trong inner class:

~~~java
public class Document {
    private final String documentId;

    public Document(String documentId) {
        this.documentId = documentId;
    }

    public class Editor {
        private final int revision;

        private static final String SNAPSHOT_PREFIX = "DOC-SNAPSHOT";
        private static int snapshotsCreated;

        public Editor(int revision) {
            this.revision = revision;
        }

        public static String snapshotPrefix() {
            return SNAPSHOT_PREFIX;
        }

        public static int snapshotsCreated() {
            return snapshotsCreated;
        }

        record Snapshot(String documentId, int revision, String prefix) {
            String label() {
                return prefix + ":" + documentId + ":v" + revision;
            }
        }

        public Snapshot snapshot() {
            snapshotsCreated++;
            return new Snapshot(
                Document.this.documentId,
                revision,
                SNAPSHOT_PREFIX
            );
        }
    }

    public static void main(String[] args) {
        Document document = new Document("D-100");
        Document.Editor editor = document.new Editor(4);

        Document.Editor.Snapshot fromEditor = editor.snapshot();

        // Có thể tạo Snapshot mà không tạo Document hoặc Editor instance.
        Document.Editor.Snapshot independent =
            new Document.Editor.Snapshot("D-200", 1, "MANUAL");

        System.out.println(fromEditor.label());
        System.out.println(independent.label());
        System.out.println(Document.Editor.snapshotPrefix());
        System.out.println(Document.Editor.snapshotsCreated());
    }
}
~~~

Biên dịch bằng JDK 16 trở lên:

~~~bash
javac --release 16 Document.java
java Document
~~~

Điểm cần quan sát:

1. `Editor` vẫn là inner class và cần `document.new Editor(4)` để tạo instance.
2. `Editor` có static field và static method từ Java 16.
3. `Snapshot` là member record ngầm định static bên trong `Editor`.
4. `Snapshot` không truy cập `Document.this` hoặc `Editor.this`.
5. Method `snapshot()` của `Editor` đọc outer instance và truyền giá trị vào component.
6. `Snapshot` có thể được tạo độc lập bằng `new Document.Editor.Snapshot(...)`.
7. `snapshotsCreated` là trạng thái static dùng chung, không phải trạng thái của từng editor.

## 10. Phân biệt các loại thành viên và instance

| Thành phần | Có enclosing instance? | Cách tạo/truy cập |
| --- | --- | --- |
| Inner class `Outer.Inner` | Có | `outer.new Inner()` |
| Static member của inner class | Không gắn với instance cụ thể | `Outer.Inner.member` |
| Nested record trong inner class | Không; member record ngầm định static | `new Outer.Inner.Snapshot(...)` |
| Instance method của inner class | Chạy trên một `Inner` object | `inner.method()` |
| Static method của inner class | Thuộc kiểu `Inner` | `Outer.Inner.method()` |
| Static field của inner class | Thuộc kiểu `Inner` | `Outer.Inner.FIELD` |

Cần nhớ nested record là một kiểu member static. Nó không biến toàn bộ `Inner` thành static và không làm thay đổi cách tạo object `Inner`.

## 11. Lỗi thường gặp và cách khắc phục

1. **Nghĩ inner class vẫn bị cấm khai báo static member:** từ Java 16, inner class được phép khai báo static member theo JEP 395.
2. **Nghĩ nested record cần outer instance:** member record ngầm định static; tạo qua `Outer.Inner.Snapshot`.
3. **Dùng `outer.new Snapshot(...)`:** sai vì nested record không phải inner class; dùng `new Outer.Inner.Snapshot(...)`.
4. **Nghĩ inner class tự trở thành static:** chỉ các static member được khai báo là static; `Inner` vẫn cần `Outer` instance.
5. **Truy cập `Outer.this` trong nested record:** record không có enclosing instance; truyền dữ liệu thành component hoặc tham số.
6. **Dùng type parameter của outer generic class trong nested record:** nested record là static member type; khai báo type parameter riêng.
7. **Cho rằng static field trong inner class luôn là compile-time constant:** từ Java 16, các static field khác cũng được phép; cần phân biệt constant variable với mutable static state.
8. **Dùng static mutable state thiếu kiểm soát:** field static được chia sẻ giữa các instance và có thể cần đồng bộ khi nhiều luồng truy cập.
9. **Nhầm nested record với component của outer record:** khai báo kiểu lồng không tự lưu object; chỉ component trong header mới tạo trạng thái instance.

## 12. Bài tập thực hành

1. Khai báo `class Library` có inner class `Catalog`. Đặt nested record `Book(String isbn, String title)` trong `Catalog` và tạo `Library.Catalog.Book` mà không cần tạo `Library` hoặc `Catalog`.
2. Khai báo static field và static method trong inner class từ Java 16. Gọi chúng qua tên kiểu và giải thích vì sao không cần instance.
3. Tạo nested record trong inner class với một phương thức instance. Thử truy cập `Outer.this` và giải thích lỗi.
4. Viết instance method của inner class đọc dữ liệu từ outer object rồi truyền các giá trị đó vào nested record.
5. Khai báo generic outer class có inner class chứa nested record. Giải thích vì sao nested record phải khai báo type parameter riêng.
6. Tạo một nested record trong inner class và một instance `Inner`. So sánh cách tạo hai object.
7. Dùng nested record làm snapshot của trạng thái inner object. Xác định những component nào nên được sao chép vào snapshot.
8. Giải thích vì sao Java 16 cho phép static member trong inner class nhưng inner class vẫn không trở thành static nested class.

## Ghi nhớ

Từ Java 16, inner class được phép khai báo static field, static method, static initializer và member type. Điều này cho phép khai báo nested record bên trong inner class, vì member record ngầm định static. Nested record không giữ enclosing instance, không dùng `Outer.this` hoặc `Inner.this`, và không truy cập trực tiếp instance field của outer object. Muốn tạo snapshot từ dữ liệu outer object, hãy đọc dữ liệu trong instance method của inner class rồi truyền vào component. Nested record có thể dùng static member của kiểu bao ngoài và phải khai báo type parameter riêng thay vì dùng type parameter của outer generic class. Quan trọng nhất, thay đổi Java 16 không biến inner class thành static: tạo instance `Inner` vẫn cần outer instance, trong khi tạo nested record thì không. Đây là khả năng ngôn ngữ ổn định được hoàn thiện trong Java 16 và tiếp tục áp dụng trong Java hiện đại.

**Tài liệu tham khảo chính thức:**

- [OpenJDK JEP 395 – Records](https://openjdk.org/jeps/395)
- [Java Language Specification – Inner Classes and Static Members, mục 8.1.3](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.1.3)
- [Java Language Specification – Record Classes, mục 8.10](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html#jls-8.10)
- [Java Language Specification – Static Contexts, mục 8.1.3 và 8.4.3.2](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-8.html)
