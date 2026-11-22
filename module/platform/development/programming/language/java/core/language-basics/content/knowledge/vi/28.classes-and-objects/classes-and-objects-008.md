# Giới thiệu `enum`, `record` và `interface` — đọc hiểu cú pháp Java 17+

## 1. Nhận diện nhanh ba kiểu khai báo

Java không chỉ có `class`. Khi đọc mã nguồn, bạn thường gặp:

~~~java
enum Priority { LOW, MEDIUM, HIGH }

record Point(int x, int y) {}

interface Printable {
    String label();
}
~~~

| Từ khóa | Mục đích chính | Đọc hiểu nhanh |
|---|---|---|
| `enum` | Biểu diễn tập giá trị cố định có tên | `Priority.MEDIUM` là một hằng kiểu `Priority` |
| `record` | Khai báo kiểu dữ liệu mang các thành phần (*components*) | `new Point(2, 3)` có các accessor `x()`, `y()` |
| `interface` | Định nghĩa hợp đồng mà các kiểu khác có thể thực hiện | `class/record X implements Printable` cam kết cung cấp `label()` |

Cả ba tạo ra **kiểu tham chiếu**, không phải kiểu nguyên thủy như `int`. Bài này tập trung **đọc đúng cú pháp và sử dụng cơ bản** trên Java 17, chưa đi sâu thiết kế OOP.

## 2. `enum`: tập hằng có tên và kiểu rõ ràng

~~~java
enum Priority {
    LOW, MEDIUM, HIGH
}

Priority current = Priority.MEDIUM;
System.out.println(current);
~~~

**Exact stdout:**

~~~text
MEDIUM
~~~

- `Priority` là tên kiểu `enum`, còn `LOW`, `MEDIUM`, `HIGH` là các hằng của kiểu đó.
- `Priority.MEDIUM` không phải chuỗi `"MEDIUM"`; nó là một giá trị kiểu `Priority`.
- `Priority.values()` trả mảng chứa các hằng theo thứ tự khai báo; `Priority.valueOf("MEDIUM")` tìm đúng hằng có tên này.
- `current.name()` trả tên hằng; `current.ordinal()` là vị trí bắt đầu từ 0, nhưng **không nên lưu ordinal làm mã nghiệp vụ bền vững** vì đổi thứ tự hằng sẽ đổi số.
- `enum` có thể có field, method và constructor, nhưng ở mức cơ bản có thể chỉ cần liệt kê các hằng.

~~~java
String action = switch (current) {
    case LOW -> "read";
    case MEDIUM -> "review";
    case HIGH -> "urgent";
};
System.out.println(action);
~~~

**Exact stdout:**

~~~text
review
~~~

Đây là **switch expression** hợp lệ trong Java 17: các nhánh bao phủ mọi hằng hiện có của `Priority`. Không thể viết `new Priority()` để tùy ý tạo thêm hằng enum.

## 3. `record`: cách khai báo gọn một kiểu dữ liệu

~~~java
record Point(int x, int y) {}

Point p = new Point(2, 3);
System.out.println(p.x());
System.out.println(p.y());
System.out.println(p);
~~~

**Exact stdout:**

~~~text
2
3
Point[x=2, y=3]
~~~

`record Point(int x, int y)` khai báo hai **record components** `x` và `y`. Java tự cung cấp nhiều thành phần thường phải viết thủ công:

- Constructor chuẩn theo các components, ví dụ `new Point(2, 3)`.
- Các accessor tên `x()` và `y()`, **không mặc định là** `getX()`/`getY()`.
- `equals`, `hashCode`, `toString` dựa trên các components.
- Các trường component là `private final` trong record, không được gán lại sau khi khởi tạo.

Record vẫn có thể có method riêng và **kiểm tra dữ liệu lúc tạo** bằng compact constructor:

~~~java
record Lesson(String title, int minutes) {
    Lesson {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("blank title");
        }
        if (minutes < 0) {
            throw new IllegalArgumentException("negative minutes");
        }
        title = title.strip();
    }
}
~~~

`Lesson { ... }` là **compact canonical constructor**: viết logic kiểm tra/chuẩn hóa, không phải khai báo một method tên `Lesson`. Sau phần thân này, Java gán các giá trị tham số component đã xử lý vào các trường tương ứng.

**Quan trọng:** record không đồng nghĩa *deep immutable*. Nếu component là một mảng hoặc object mutable, bản ghi vẫn có thể giữ tham chiếu tới dữ liệu có thể bị sửa. Record là `final` (không thể được kế thừa bằng `extends`); nó có thể `implements interface`.

## 4. `interface`: hợp đồng hành vi

~~~java
interface Describable {
    String label();

    default String summary() {
        return "Named:" + label();
    }

    static String kind() {
        return "describable";
    }
}
~~~

Đọc cú pháp:

- `String label();` khai báo một phương thức trừu tượng (implicit `public abstract`); không có thân ở đây.
- `default String summary() { ... }` có **thân mặc định** để các lớp thực hiện interface có thể sử dụng hoặc override.
- `static String kind() { ... }` là phương thức static của interface, gọi bằng `Describable.kind()`.
- Một class hoặc record dùng `implements Describable` và phải cung cấp cách cài đặt các phương thức abstract chưa được thực hiện.
- Phương thức cài đặt `label()` từ interface phải là `public`; không được giảm quyền truy cập thành package-private hay `private`.

~~~java
record Lesson(String title, int minutes) implements Describable {
    @Override
    public String label() {
        return title;
    }
}
~~~

Ví dụ trên chỉ minh họa hình dạng khai báo; chương trình hoàn chỉnh ở mục 6 có thêm compact constructor để xác thực dữ liệu.

**Không viết** `new Describable()`: interface không phải class cụ thể để khởi tạo trực tiếp. Nhưng biến kiểu interface có thể **tham chiếu tới object của lớp/record cài đặt nó**:

~~~java
Describable item = new Lesson("Java", 30);
System.out.println(item.label());
System.out.println(item.summary());
~~~

**Exact stdout:**

~~~text
Java
Named:Java
~~~

Java cũng hỗ trợ class `implements` nhiều interface, và interface `extends` một hoặc nhiều interface khác. Đừng nhầm từ khóa `implements` (thực hiện hợp đồng) với `extends` (quan hệ kế thừa được phép giữa các kiểu).

## 5. Đặt ba kiểu cạnh nhau

| Điểm khác biệt | `enum` | `record` | `interface` |
|---|---|---|---|
| Thường dùng để | Trạng thái/tùy chọn hữu hạn | Gói dữ liệu có tên trường | Hợp đồng hành vi |
| Tạo giá trị | Dùng hằng khai báo sẵn | Thường `new RecordName(...)` | Không tạo object trực tiếp |
| Ví dụ truy cập | `Priority.HIGH` | `lesson.title()` | `item.label()` |
| Phương thức có thân | Có thể khai báo | Có thể khai báo | `default`, `static` (và helper `private` trên Java hiện đại) |
| Có thể thực hiện interface | Có | Có | Interface khác có thể mở rộng nó |

Khi đọc chữ ký `record Lesson(...) implements Describable`, hiểu theo thứ tự: định nghĩa **kiểu record** `Lesson`, khai báo components trong ngoặc, rồi xác nhận nó **cung cấp hành vi** theo `Describable`.

Trong Java 17, cả ba cú pháp trên đều **ổn định, không cần bật preview features**. Record trở thành tính năng chính thức từ Java 16; enum và interface đã có từ các phiên bản Java trước đó.

## 6. Chương trình Java 17+ hoàn chỉnh

Lưu đúng file **`EnumRecordInterfaceDemo.java`**:

~~~java
public final class EnumRecordInterfaceDemo {
    private EnumRecordInterfaceDemo() {}

    enum Priority {
        LOW, MEDIUM, HIGH
    }

    interface Describable {
        String label();

        default String summary() {
            return "Named:" + label();
        }

        static String kind() {
            return "describable";
        }
    }

    record Lesson(String title, int minutes) implements Describable {
        Lesson {
            if (title == null || title.isBlank()) {
                throw new IllegalArgumentException("blank title");
            }
            if (minutes < 0) {
                throw new IllegalArgumentException("negative minutes");
            }
            title = title.strip();
        }

        @Override
        public String label() {
            return title;
        }
    }

    static final class Folder implements Describable {
        private final String name;

        Folder(String name) {
            this.name = name;
        }

        @Override
        public String label() {
            return name;
        }
    }

    public static void main(String[] args) {
        Priority priority = Priority.MEDIUM;
        System.out.println("enum value=" + priority);
        System.out.println("enum name=" + priority.name());
        System.out.println("enum count=" + Priority.values().length);
        System.out.println("enum lookup=" + (Priority.valueOf("MEDIUM") == priority));

        String action = switch (priority) {
            case LOW -> "read";
            case MEDIUM -> "review";
            case HIGH -> "urgent";
        };
        System.out.println("enum switch=" + action);

        Lesson first = new Lesson(" Java ", 30);
        Lesson second = new Lesson("Java", 30);
        System.out.println("record=" + first);
        System.out.println("record title=" + first.title());
        System.out.println("record minutes=" + first.minutes());
        System.out.println("record equals=" + first.equals(second));
        System.out.println("record identity=" + (first == second));

        Describable item = first;
        System.out.println("interface label=" + item.label());
        System.out.println("interface default=" + item.summary());
        System.out.println("interface static=" + Describable.kind());

        Describable folder = new Folder("Basics");
        System.out.println("class implements=" + folder.summary());

        try {
            new Lesson(" ", 5);
        } catch (IllegalArgumentException ex) {
            System.out.println("record invalid=" + ex.getMessage());
        }
    }
}
~~~

Yêu cầu **JDK 17 trở lên**, không cần Maven/Gradle, thư viện bên ngoài hay `--enable-preview`.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 EnumRecordInterfaceDemo.java
java -cp . EnumRecordInterfaceDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\EnumRecordInterfaceDemo.java
java -cp . EnumRecordInterfaceDemo
~~~

### Exact expected stdout

~~~text
enum value=MEDIUM
enum name=MEDIUM
enum count=3
enum lookup=true
enum switch=review
record=Lesson[title=Java, minutes=30]
record title=Java
record minutes=30
record equals=true
record identity=false
interface label=Java
interface default=Named:Java
interface static=describable
class implements=Named:Basics
record invalid=blank title
~~~

Đọc luồng kết quả: biến `priority` giữ một hằng enum; `Lesson` tạo hai object có cùng nội dung (`equals=true`) nhưng khác tham chiếu (`==false`); object record có thể được gán cho biến interface `Describable` vì đã `implements`; lớp `Folder` cũng có thể thực hiện cùng interface.

## 7. Lỗi đọc cú pháp thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Coi `Priority.HIGH` là `String` | Nó là hằng kiểu `Priority`; dùng `.name()` nếu cần tên |
| Dùng `new Priority()` | Không thể tự tạo enum constant bằng `new` |
| Dùng `new Describable()` | Interface không được khởi tạo trực tiếp |
| Gọi `lesson.getTitle()` theo mặc định | Record component có accessor `title()` |
| Nghĩ record luôn deep immutable | Component tham chiếu mutable vẫn có thể bị thay đổi |
| Gọi `Describable.summary()` như static | `summary()` là instance default method; chỉ `kind()` mới static |
| Cài đặt `label()` không `public` | Không được giảm quyền truy cập của phương thức interface |
| Dùng `extends` thay `implements` khi record cài đặt interface | Viết `record Lesson(...) implements Describable` |
| Coi `record` là class có thể kế thừa | Record ngầm `final`, không được lớp khác `extends` |
| Lưu `enum.ordinal()` như mã cố định | Thứ tự hằng thay đổi sẽ làm ordinal đổi |

## 8. Bài tập có đáp án

**A.** Với `enum Traffic { RED, YELLOW, GREEN }`, biến `Traffic light = Traffic.RED;` giữ kiểu gì? **`Traffic`**; `RED` là một hằng của enum, không phải chuỗi.

**B.** Với `record Size(int width, int height) {}`, tạo `new Size(2, 5)` rồi đọc chiều rộng thế nào? **`size.width()`** với biến `Size size`; Java không tự tạo `getWidth()`.

**C.** Interface khai báo `void run();`, class thực hiện nó phải viết phương thức với quyền truy cập nào? **`public void run() { ... }`** (nếu class cụ thể cung cấp cài đặt trực tiếp).

**D.** Hai record cùng giá trị components có thể `equals` true nhưng `==` false không? **Có**: `equals` dựa vào nội dung components, `==` so object identity.

**E.** `record Lesson(String name) implements Describable` có thể có thêm method riêng không? **Có**; record vẫn là kiểu lớp đặc biệt có thể khai báo method và thực hiện interface.

## 9. Checklist và kết luận

- [ ] Nhận diện `enum`, danh sách hằng và cách viết `Type.CONSTANT`.
- [ ] Hiểu `record X(T component)` khai báo dữ liệu và accessor `component()`.
- [ ] Biết `equals` và `==` của record mang ý nghĩa khác nhau.
- [ ] Hiểu interface khai báo hợp đồng; `implements` là thực hiện hợp đồng.
- [ ] Phân biệt abstract, default và static method trong interface.
- [ ] Biết record có thể `implements interface`.
- [ ] Không nhầm record là deep immutable hay enum là `String`.
- [ ] Biên dịch, chạy `EnumRecordInterfaceDemo.java` bằng JDK 17+ và đối chiếu exact stdout.

**Kết luận:** `enum` phù hợp với **tập lựa chọn có tên**, `record` thuận tiện để biểu diễn **dữ liệu có cấu trúc**, còn `interface` biểu diễn **hợp đồng hành vi**. Đọc đúng ba cú pháp giúp hiểu cách các kiểu Java kết hợp với nhau mà chưa cần học sâu các kỹ thuật OOP nâng cao.