# Nhận diện record pattern để tách dữ liệu của `record` — Java 17+/21

**Record pattern** (*mẫu phân rã record*) cho phép kiểm tra một đối tượng có đúng kiểu `record` và **trích các thành phần của record thành biến** ngay trong phép kiểm tra. Đây là tính năng **chuẩn từ Java 21 (JEP 440)**. Trong Java 17, `record` đã là tính năng chuẩn, nhưng **cú pháp record pattern chưa phải tính năng chuẩn**.

~~~java
record Point(int x, int y) {}

Object value = new Point(2, 3);
if (value instanceof Point(int x, int y)) { // JDK 21+
    System.out.println(x + y);              // 5
}
~~~

`Point(int x, int y)` là **record pattern**, khác với `new Point(2, 3)` là biểu thức **tạo đối tượng**. Khi pattern khớp, nó lấy hai thành phần của record và ràng buộc vào biến `x`, `y` mà không cần ép kiểu rồi gọi riêng `point.x()` và `point.y()`.

## 1. Phân biệt record, type pattern và record pattern

| Cấu trúc | Ý nghĩa | Phiên bản chuẩn |
| --- | --- | --- |
| `record Point(int x, int y) {}` | Khai báo lớp record có hai component | Java 16+ |
| `obj instanceof Point p` | Kiểm tra kiểu, ràng buộc cả đối tượng vào `p` | Java 16+ |
| `obj instanceof Point(int x, int y)` | Kiểm tra kiểu **và phân rã hai component** | Java 21+ |
| `case Point(int x, int y) -> ...` | Dùng record pattern trong switch | Java 21+ |

Với **type pattern**, ta có biến `p` là cả record và đọc component qua `p.x()`, `p.y()`. Với **record pattern**, biến `x` và `y` đại diện trực tiếp cho từng component. Record pattern **không phải phép destructuring assignment** độc lập: nó cần xuất hiện trong ngữ cảnh hỗ trợ pattern, chẳng hạn `instanceof` hoặc `switch`.

**Quy tắc quan trọng:** số lượng, thứ tự và kiểu các nested pattern phải tương ứng với danh sách component của record. `Point(int x, int y)` dùng hai component theo **thứ tự khai báo**, không theo tên biến bạn đặt.

## 2. Chương trình chạy với JDK 21+

Tạo file UTF-8 tên **`RecordPattern21Demo.java`**:

~~~java
public class RecordPattern21Demo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record Person(String name, int age) {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "null";
            case Point(int x, int y) -> "point=" + x + "," + y;
            case Segment(Point(int sx, int sy), Point(int ex, int ey)) ->
                    "segment=" + sx + "," + sy + "->" + ex + "," + ey;
            case Person(String name, int age) when age >= 18 ->
                    "adult=" + name;
            case Person(String name, int age) ->
                    "minor=" + name;
            default -> "other";
        };
    }

    static int sum(Object value) {
        if (value instanceof Point(int x, int y)) {
            return x + y;
        }
        return -1;
    }

    static int squaredDistance(Object value) {
        if (value instanceof Segment(
                Point(int x1, int y1),
                Point(int x2, int y2))) {
            int dx = x2 - x1;
            int dy = y2 - y1;
            return dx * dx + dy * dy;
        }
        return -1;
    }

    public static void main(String[] args) {
        Object[] values = {
            null,
            new Point(2, 3),
            new Segment(new Point(0, 0), new Point(2, 3)),
            new Person("Mai", 20),
            new Person("Nam", 15),
            new Segment(null, new Point(1, 1)),
            42
        };

        for (Object value : values) {
            System.out.println(describe(value));
        }

        System.out.println("sum=" + sum(new Point(2, 3)));
        System.out.println("notPoint=" + sum("hello"));
        System.out.println("distance="
                + squaredDistance(new Segment(
                        new Point(0, 0), new Point(2, 3))));
        System.out.println("missingStart="
                + squaredDistance(new Segment(null, new Point(1, 1))));
    }
}
~~~

Dùng **JDK 21 trở lên** trong PowerShell (Windows) hoặc Bash (Linux/macOS):

~~~bash
java -version
javac -version
javac -encoding UTF-8 RecordPattern21Demo.java
java RecordPattern21Demo
~~~

**Exact expected stdout** của riêng lệnh `java RecordPattern21Demo`:

~~~text
null
point=2,3
segment=0,0->2,3
adult=Mai
minor=Nam
other
other
sum=5
notPoint=-1
distance=13
missingStart=-1
~~~

`java -version` và `javac -version` in phiên bản phụ thuộc JDK cài trên máy. Với JDK 21, ví dụ trên **không cần `--enable-preview`**.

## 3. Nested record pattern: phân rã nhiều tầng

`Segment` chứa hai component kiểu `Point`, nên có thể viết pattern lồng:

~~~java
if (value instanceof Segment(
        Point(int x1, int y1),
        Point(int x2, int y2))) {
    System.out.println(x1 + "," + y1);
    System.out.println(x2 + "," + y2);
}
~~~

Khi thành công, `value` phải là `Segment` và cả `start` lẫn `end` phải khớp hai pattern `Point(...)`. Các component được trích thành **bốn biến `int`**.

Nếu `Segment` chứa `start == null`, pattern `Point(int x1, int y1)` cho component đó **không khớp**, nên toàn bộ nested pattern thất bại. Đó là lý do demo in `missingStart=-1` thay vì phát sinh lỗi do gọi `start.x()` trên null.

Có thể đọc kết quả phân rã theo sơ đồ:

~~~mermaid
flowchart TD
    A["value"] --> B{"Segment?"}
    B -- Không --> F["Pattern không khớp"]
    B -- Có --> C{"start khớp Point?"}
    C -- Không --> F
    C -- Có --> D{"end khớp Point?"}
    D -- Không --> F
    D -- Có --> E["Ràng buộc x1, y1, x2, y2"]
~~~

Với component là kiểu tham chiếu, Java có thể dùng các pattern thích hợp như `String name` để kiểm tra/ràng buộc thêm. Record pattern được kết hợp từ nhiều pattern con chứ không chỉ cho phép primitive `int`.

## 4. `null`, `when` và thứ tự pattern trong `switch`

Pattern `Point(int x, int y)` không khớp với selector `null`. Trong **switch Java 21**, ta có thể xử lý rõ ràng:

~~~java
String label = switch (value) {
    case null -> "missing";
    case Point(int x, int y) when x == 0 && y == 0 -> "origin";
    case Point(int x, int y) -> "point";
    default -> "other";
};
~~~

Ở đây:

- `case null` xử lý riêng selector null; **`default` không tự thay thế `case null`**.
- `when` bổ sung điều kiện **sau khi pattern khớp**.
- Nhánh origin phải đặt **trước** nhánh `Point(...)` chung. Đảo thứ tự có thể khiến nhánh origin bị một pattern rộng hơn chiếm hết (*dominated case*) và không biên dịch.
- Dạng `case ... ->` không rơi tiếp xuống nhãn khác.

**Record pattern không giải quyết mọi trường hợp `null`:** selector null cần `case null` hoặc kiểm tra từ trước; component null có thể làm nested pattern không khớp, tùy pattern bên trong. Việc phân rã component dùng các accessor của record; tránh tạo accessor có tác dụng phụ hoặc ném ngoại lệ nếu muốn phép kiểm tra dễ dự đoán.

## 5. Cách tương thích JDK 17 — dùng record accessor và type pattern

Để chạy trên **JDK 17** mà không dùng record pattern, kiểm tra kiểu bằng `instanceof Point p`, rồi đọc component bằng `p.x()` và `p.y()`.

Tạo tệp UTF-8 **`RecordPattern17Compat.java`**:

~~~java
public class RecordPattern17Compat {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record Person(String name, int age) {}

    static String describe(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof Point point) {
            return "point=" + point.x() + "," + point.y();
        }
        if (value instanceof Segment segment
                && segment.start() != null
                && segment.end() != null) {
            Point start = segment.start();
            Point end = segment.end();
            return "segment=" + start.x() + "," + start.y()
                    + "->" + end.x() + "," + end.y();
        }
        if (value instanceof Person person) {
            return (person.age() >= 18 ? "adult=" : "minor=")
                    + person.name();
        }
        return "other";
    }

    static int sum(Object value) {
        if (value instanceof Point point) {
            return point.x() + point.y();
        }
        return -1;
    }

    static int squaredDistance(Object value) {
        if (value instanceof Segment segment
                && segment.start() != null
                && segment.end() != null) {
            int dx = segment.end().x() - segment.start().x();
            int dy = segment.end().y() - segment.start().y();
            return dx * dx + dy * dy;
        }
        return -1;
    }

    public static void main(String[] args) {
        Object[] values = {
            null,
            new Point(2, 3),
            new Segment(new Point(0, 0), new Point(2, 3)),
            new Person("Mai", 20),
            new Person("Nam", 15),
            new Segment(null, new Point(1, 1)),
            42
        };

        for (Object value : values) {
            System.out.println(describe(value));
        }
        System.out.println("sum=" + sum(new Point(2, 3)));
        System.out.println("notPoint=" + sum("hello"));
        System.out.println("distance="
                + squaredDistance(new Segment(
                        new Point(0, 0), new Point(2, 3))));
        System.out.println("missingStart="
                + squaredDistance(new Segment(null, new Point(1, 1))));
    }
}
~~~

Chạy với **JDK 17+**:

~~~bash
javac -encoding UTF-8 RecordPattern17Compat.java
java RecordPattern17Compat
~~~

**Exact expected stdout** của lệnh `java RecordPattern17Compat` **giống hệt** khối stdout trong mục 2. Bản Java 17 truy cập accessor tường minh và kiểm tra null cho nested record, nhưng không có cú pháp phân rã trực tiếp của Java 21.

## 6. Giới hạn và lỗi thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Có `record` ở Java 17 thì đã có `record pattern`.” | Record chuẩn từ Java 16; record pattern chuẩn từ Java 21 |
| “`new Point(2,3)` giống `Point(int x,int y)`.” | Một bên tạo record, một bên là pattern để khớp và phân rã |
| “Record pattern thay đổi hoặc sao chép record.” | Chỉ kiểm tra và ràng buộc component, không tạo record mới |
| “`Point(int y,int x)` tự lấy đúng tên component theo tên biến.” | Pattern ánh xạ **theo vị trí**, không theo tên biến |
| “Nested pattern tự bỏ qua component null.” | Pattern con phải khớp; null có thể khiến cả pattern thất bại |
| “Đặt `case Point(...)` trước `case Point(...) when ...`.” | Nhánh tổng quát có thể làm nhánh đặc biệt bị dominance |
| “`default` luôn bắt selector null.” | Cần xử lý null riêng khi nghiệp vụ yêu cầu |
| “JDK 17 biên dịch file có `case Point(int x,int y)`.” | Không ở chế độ Java 17 chuẩn |
| “Biến `x`, `y` luôn dùng được sau phép kiểm tra thất bại.” | Biến chỉ hợp lệ trong **flow scope** đã chứng minh pattern khớp |

Các component record là thành phần của mô hình dữ liệu; đừng lạm dụng record pattern quá dài nhiều tầng nếu việc đặt biến trung gian hoặc gọi accessor sẽ dễ đọc hơn.

## 7. Bài tập tự kiểm tra

1. `Object p = new Point(4, 5);`, nếu khớp `Point(int x, int y)` thì `x + y` bằng gì?  
   *Đáp án:* `9`.
2. Record pattern kiểm tra kiểu runtime hay chỉ tên biến?  
   *Đáp án:* Kiểm tra kiểu rồi phân rã component theo thứ tự khai báo.
3. Với `Segment(null, new Point(1,1))`, nested pattern cần cả hai `Point(...)` có khớp không?  
   *Đáp án:* Không.
4. Trong switch Java 21, có thể dùng `case Point(int x,int y) when x == 0` không?  
   *Đáp án:* Có, đặt trước nhánh Point tổng quát.
5. `record Point` có chạy được JDK 17 không? Record pattern có chuẩn ở JDK 17 không?  
   *Đáp án:* Có record, nhưng chưa có record pattern chuẩn.
6. Muốn lấy component Point với JDK 17, làm thế nào?  
   *Đáp án:* `if (obj instanceof Point p)` rồi `p.x()` và `p.y()`.

## Checklist

- [ ] Phân biệt khai báo `record` với cú pháp `record pattern`.
- [ ] Nhớ record pattern chuẩn từ **Java 21**, còn record/type pattern `instanceof` đã có trên Java 17.
- [ ] Đọc đúng component theo thứ tự và phạm vi biến sau khi pattern khớp.
- [ ] Hiểu nested record pattern và tình huống component null.
- [ ] Dùng `when` và `case null` có chủ đích trong switch Java 21.
- [ ] Biết cách thay bằng `instanceof` + accessor nếu môi trường còn dùng JDK 17.

**Kết luận:** Record pattern giúp tách các component của record **ngay trong bước kiểm tra kiểu**, kể cả khi các record lồng nhau. Dùng JDK 21+ để chạy cú pháp này; với dự án JDK 17, vẫn có thể làm cùng công việc thông qua type pattern `instanceof` và các phương thức accessor.
