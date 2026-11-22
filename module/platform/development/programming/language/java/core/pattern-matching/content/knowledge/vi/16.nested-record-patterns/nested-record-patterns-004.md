# Pattern component chứa record khác

## 1. Khi một record chứa record khác

Trong dữ liệu thực tế, một record thường có component mang kiểu record khác. Ví dụ, một đơn giao hàng có nơi nhận, còn nơi nhận có tọa độ:

```java
record Point(int x, int y) {}
record Place(String name, Point coordinate) {}
record Delivery(String id, Place destination) {}
```

Ở đây, cấu trúc dữ liệu có ba tầng:

```text
Delivery
├── id: String
└── destination: Place
    ├── name: String
    └── coordinate: Point
        ├── x: int
        └── y: int
```

Nếu một biến có kiểu `Object` đang chứa `Delivery`, ta có thể muốn vừa xác nhận đúng loại dữ liệu, vừa lấy `id`, tên nơi nhận và hai tọa độ. **Nested record pattern** cho phép thực hiện việc đó ngay trong một mẫu khớp, thay cho nhiều lần kiểm tra kiểu và gọi phương thức truy cập.

Điểm cần hiểu là **component của record bên ngoài có thể chính là một record**. Ta đặt một *record pattern khác* vào vị trí component ấy để tiếp tục phân rã ở tầng bên trong.

## 2. Viết mẫu lồng đúng cấu trúc

Với ba khai báo trên, mẫu đầy đủ là:

```java
Delivery(String id, Place(String name, Point(int x, int y)))
```

Đọc từ trái sang phải:

1. `Delivery(...)` kiểm tra giá trị có phải một `Delivery` phù hợp hay không.
2. Component thứ nhất của `Delivery` là `id`, được ràng buộc vào biến `String id`.
3. Component thứ hai là `destination` có kiểu `Place`. Thay vì chỉ ràng buộc một biến `Place`, ta dùng tiếp `Place(...)` để phân rã nó.
4. Component đầu của `Place` là `name`; component thứ hai là một `Point`. Mẫu `Point(int x, int y)` lấy tiếp hai tọa độ.

Chẳng hạn:

```java
Object value = new Delivery(
        "D-01",
        new Place("Kho A", new Point(2, 7))
);

if (value instanceof Delivery(
        String id,
        Place(String name, Point(int x, int y)))) {
    System.out.println(id + ": " + name + ", " + (x + y));
}
```

Đoạn mã này in `D-01: Kho A, 9`. Các biến `id`, `name`, `x` và `y` chỉ được ràng buộc sau khi toàn bộ mẫu lồng khớp. Đây là đoạn minh họa, giả định ba kiểu record đã được khai báo trong cùng phạm vi.

**Thứ tự component quan trọng hơn tên biến.** Trong `Place(String name, Point coordinate)`, pattern ở vị trí thứ nhất ứng với `name`, ở vị trí thứ hai ứng với `coordinate`. Tên biến bên trong pattern có thể khác tên component gốc mà Java vẫn biên dịch được khi kiểu tương thích.

| Component thực tế | Pattern tại vị trí tương ứng | Giá trị được lấy trong ví dụ |
| --- | --- | --- |
| `Delivery.id` | `String id` | `"D-01"` |
| `Delivery.destination` | `Place(...)` | Tiếp tục phân rã `Place` |
| `Place.name` | `String name` | `"Kho A"` |
| `Place.coordinate` | `Point(...)` | Tiếp tục phân rã `Point` |
| `Point.x` | `int x` | `2` |
| `Point.y` | `int y` | `7` |

Nested record pattern không khởi tạo record mới, không sửa record ban đầu và không tự biến các component thành biến toàn cục. Nó biểu diễn các bước kiểm tra và trích xuất dữ liệu trong một biểu thức pattern matching.

## 3. Ví dụ Java 21 chạy hoàn chỉnh

Lưu toàn bộ chương trình dưới tên **`NestedRecordPatternDemo.java`**:

```java
public class NestedRecordPatternDemo {
    record Point(int x, int y) {}
    record Place(String name, Point coordinate) {}
    record Delivery(String id, Place destination) {}

    static String describe(Object input) {
        return switch (input) {
            case Delivery(String id,
                    Place(String name, Point(int x, int y))) ->
                    id + " đến " + name + " (" + x + ", " + y + ")";

            case Delivery(String id, Place place) ->
                    id + ": có Place nhưng chưa đủ dữ liệu";

            case Delivery delivery ->
                    delivery.id() + ": chưa khớp mẫu lồng";

            case null -> "Không có dữ liệu";
            default -> "Không phải Delivery";
        };
    }

    public static void main(String[] args) {
        Object first = new Delivery(
                "D-01", new Place("Kho A", new Point(2, 7)));

        if (first instanceof Delivery(
                String id, Place(String name, Point(int x, int y)))) {
            System.out.println("Tách được: " + id + ", "
                    + name + ", tổng = " + (x + y));
        }

        System.out.println(describe(first));
        System.out.println(describe(
                new Delivery("D-02", new Place("Kho B", null))));
        System.out.println(describe(new Delivery("D-03", null)));
        System.out.println(describe("khác"));
        System.out.println(describe(null));
    }
}
```

Biên dịch và chạy với JDK 21 trở lên:

```bash
javac NestedRecordPatternDemo.java
java NestedRecordPatternDemo
```

Kết quả chuẩn:

```text
Tách được: D-01, Kho A, tổng = 9
D-01 đến Kho A (2, 7)
D-02: có Place nhưng chưa đủ dữ liệu
D-03: chưa khớp mẫu lồng
Không phải Delivery
Không có dữ liệu
```

Diễn giải từng trường hợp:

- **`D-01`:** `Delivery`, `Place` và `Point` đều tồn tại nên mẫu ba tầng khớp. Biến `x` bằng `2`, `y` bằng `7`; phép cộng cho kết quả `9`.
- **`D-02`:** `destination` là một `Place`, nhưng `coordinate` là `null`. Mẫu `Point(int x, int y)` bên trong không khớp, nên nhánh đầu bị bỏ qua; nhánh `Delivery(String id, Place place)` xử lý giá trị còn lại vì `Place` vẫn tồn tại.
- **`D-03`:** `destination` là `null`. Cả mẫu lồng ba tầng lẫn mẫu yêu cầu một `Place` không null đều không khớp. Nhánh `case Delivery delivery` nhận record `Delivery` còn lại.
- **`"khác"`:** Không phải `Delivery` nên đi vào `default`.
- **`null`:** Được xử lý riêng bằng `case null`, không đi vào các mẫu record.

Lưu ý rằng nhánh `case Delivery delivery` là **nhánh dự phòng tổng quát cho mọi `Delivery` chưa khớp hai nhánh trên**. Chuỗi “chưa khớp mẫu lồng” mô tả đúng điều đó; không được suy luận mọi giá trị vào nhánh này đều có `destination == null`.

## 4. Cần lồng đến đâu?

Không bắt buộc phân rã tất cả các tầng. Chọn độ sâu đúng với dữ liệu cần xử lý.

**Chỉ kiểm tra record ngoài và giữ nguyên record trong:**

```java
if (value instanceof Delivery(String id, Place place)) {
    // id là String; place vẫn là một đối tượng Place.
    System.out.println(id + " -> " + place.name());
}
```

**Phân rã thêm một tầng nhưng giữ nguyên `Point`:**

```java
if (value instanceof Delivery(
        String id, Place(String name, Point point))) {
    // point vẫn là một Point; có thể gọi point.x(), point.y().
    System.out.println(id + " -> " + name + ": " + point.x());
}
```

**Phân rã cả ba tầng:**

```java
if (value instanceof Delivery(
        String id, Place(String name, Point(int x, int y)))) {
    // x và y đã là hai biến int.
    System.out.println(id + " -> " + name + ": " + x + ", " + y);
}
```

Ba đoạn trên là ví dụ độc lập về cú pháp trong ngữ cảnh đã khai báo các record và một biến `value`. Mẫu càng sâu càng nêu rõ những thành phần phải khớp. Nếu code chỉ cần `place` để truyền cho phương thức khác, việc giữ nguyên `Place` thường dễ đọc hơn.

Có thể dùng `var` để Java suy luận kiểu tại vị trí component:

```java
if (value instanceof Delivery(
        var id, Place(var name, Point(var x, var y)))) {
    System.out.println(id + " -> " + name + ": " + (x + y));
}
```

Với các khai báo ở đầu bài, `id` và `name` được suy luận là `String`, còn `x` và `y` là `int`. `var` **không có nghĩa là bỏ qua một component**: đây vẫn là một pattern ràng buộc biến. Mỗi vị trí component trong dấu ngoặc của record pattern phải có một pattern tương ứng.

## 5. Null và tính khớp của toàn bộ mẫu

Mẫu phân rã nhiều tầng chỉ thành công khi **mọi record pattern lồng bên trong cũng khớp**. Nếu `destination` là `null` thì không thể khớp `Place(...)`. Nếu `destination` tồn tại nhưng `coordinate` là `null` thì không thể khớp `Point(...)`.

Đây là một khác biệt hữu ích so với cách truy cập nối tiếp bằng accessor:

```java
Delivery delivery = new Delivery("D-02", new Place("Kho B", null));

// Cách này có thể ném NullPointerException:
// int x = delivery.destination().coordinate().x();

// Cách này kiểm tra cấu trúc trước khi dùng x, y:
if (delivery instanceof Delivery(
        String id, Place(String name, Point(int x, int y)))) {
    System.out.println(x + y);
} else {
    System.out.println("Thiếu thông tin tọa độ");
}
```

Với `D-02`, đoạn `if` không vào nhánh đúng và in ra `Thiếu thông tin tọa độ`. Không có thao tác gọi `x()` trên một tham chiếu `null` trong pattern.

Với `instanceof`, biểu thức bên trái bằng `null` luôn làm mẫu record không khớp. Với `switch`, nên có `case null` nếu dữ liệu đầu vào có thể là `null`; thiếu xử lý thích hợp có thể dẫn đến `NullPointerException`. Khi một pattern lồng thất bại, các nhánh `case` sau có thể tiếp tục được xét theo thứ tự.

Record **có thể chứa component tham chiếu bằng null**, trừ khi lập trình viên tự thêm quy tắc kiểm tra trong constructor. Bản thân việc khai báo `record Place(String name, Point coordinate)` không tự cấm `coordinate == null`.

## 6. So sánh với code truy cập thủ công

Trước khi dùng nested record pattern, một cách viết dựa trên type pattern và accessor là:

```java
if (value instanceof Delivery delivery) {
    Place place = delivery.destination();
    if (place != null && place.coordinate() != null) {
        Point point = place.coordinate();
        System.out.println(delivery.id() + " -> " + place.name()
                + " (" + point.x() + ", " + point.y() + ")");
    }
}
```

Cách này hợp lệ khi `value` là một biến đã khai báo và các record ở đầu bài tồn tại. Người đọc phải theo dõi biến trung gian `delivery`, `place`, `point` và điều kiện null. Nested record pattern đặt chính cấu trúc cần kiểm tra ngay trong điều kiện:

```java
if (value instanceof Delivery(
        String id, Place(String name, Point(int x, int y)))) {
    System.out.println(id + " -> " + name + " (" + x + ", " + y + ")");
}
```

Ưu điểm là ít lời gọi accessor và thể hiện rõ cấu trúc dữ liệu cần thiết. Tuy nhiên, mẫu lồng quá sâu có thể khó đọc; khi cấu trúc phức tạp, nên phân rã theo từng bước hoặc tạo phương thức xử lý riêng thay vì cố nén toàn bộ logic vào một dòng.

## 7. Lỗi thường gặp và giới hạn

1. **Dùng JDK cũ.** Record patterns, bao gồm nested record patterns, là tính năng chính thức từ **Java 21**. Record thông thường xuất hiện chính thức sớm hơn, nhưng cú pháp `Delivery(String id, Place(...))` không hoạt động trên Java 17 theo chế độ biên dịch thông thường. Ví dụ chạy bằng JDK 21 không cần `--enable-preview`.
2. **Viết thiếu pattern cho component.** `record Delivery(String id, Place destination)` có hai component, vì vậy `Delivery(Place(...))` không hợp lệ: không thể bỏ qua vị trí của `id`. Có thể viết `Delivery(var id, Place(...))` khi không quan tâm giá trị `id`.
3. **Nhầm vị trí.** `Place(Point point, String name)` không phù hợp với khai báo `Place(String name, Point coordinate)`. Mẫu luôn dựa vào thứ tự và kiểu component, không dựa vào việc hai tên biến trông có ý nghĩa giống nhau.
4. **Cho rằng mọi component con đều luôn tồn tại.** Record không tự bảo đảm giá trị tham chiếu khác `null`. Mẫu lồng `Point(...)` không khớp nếu component chứa `Point` là `null`; cần nhánh dự phòng khi dữ liệu có thể thiếu.
5. **Cố dùng cú pháp phân rã với class thường.** `Place(...)` chỉ là record pattern nếu `Place` là kiểu record phù hợp. Class có getter giống hệt component không tự được hỗ trợ cú pháp này.
6. **Dùng biến sau khi đã ra khỏi phạm vi.** Những biến như `id`, `name`, `x`, `y` trong `instanceof` chỉ khả dụng ở nhánh mà Java biết mẫu đã khớp. Biến trong một nhánh `case` không trở thành biến dùng chung cho mọi nhánh `switch`.
7. **Đặt nhánh tổng quát trước nhánh cụ thể.** Trong `switch`, một `case Delivery delivery` đặt trước mẫu `case Delivery(String id, Place(...))` sẽ bao phủ các `Delivery` và làm nhánh cụ thể phía sau bị thống trị (*dominated*), dẫn tới lỗi biên dịch. Hãy xếp mẫu cụ thể trước mẫu tổng quát.

## 8. Tự kiểm tra

Cho khai báo:

```java
record Engine(String model, int power) {}
record Car(String brand, Engine engine) {}
```

Với:

```java
Object vehicle = new Car("A", new Engine("E-1", 120));

if (vehicle instanceof Car(
        String brand, Engine(String model, int power))) {
    System.out.println(brand + "/" + model + "/" + power);
}
```

Chương trình in `A/E-1/120` vì `vehicle` là một `Car`, component `engine` là một `Engine` và cả hai component `model`, `power` được ràng buộc thành công. Nếu đổi thành `new Car("A", null)` thì toàn bộ mẫu lồng không khớp và thân `if` không chạy.

**Ghi nhớ:** Khi một component chứa record khác, ta có thể đặt record pattern vào đúng vị trí component đó và phân rã đệ quy qua nhiều tầng. Kết quả khớp phụ thuộc vào đúng kiểu, đúng thứ tự component và việc các record cần phân rã có tồn tại hay không; các biến được ràng buộc chỉ dùng được trong phạm vi mà mẫu đã khớp.
