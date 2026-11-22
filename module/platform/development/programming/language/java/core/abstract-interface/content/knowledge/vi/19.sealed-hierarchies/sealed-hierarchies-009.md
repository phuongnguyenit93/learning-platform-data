# Pattern matching switch và tính đầy đủ của phân cấp đóng

Java 21 trở lên cho phép dùng **pattern matching trong `switch`** để kiểm tra kiểu và lấy dữ liệu từ đối tượng ngay trong từng nhánh. Khi kiểu được xét là một **sealed hierarchy** (phân cấp lớp/interface đóng), trình biên dịch có thể kiểm tra xem các nhánh đã bao phủ mọi kiểu hợp lệ trong phân cấp hay chưa. Điều này giúp viết biểu thức `switch` an toàn hơn và làm lộ ra những trường hợp cần xử lý khi mô hình dữ liệu thay đổi.

Hai ý tưởng phối hợp với nhau:

- **Pattern matching switch** chọn nhánh dựa trên kiểu hoặc cấu trúc của giá trị, có thể gắn tên cho phần dữ liệu đã khớp.
- **Sealed type** giới hạn những lớp hoặc interface nào được phép trực tiếp mở rộng hoặc triển khai kiểu cha. Các kiểu con được khai báo trong `permits`, hoặc được suy ra khi chúng nằm cùng tệp nguồn theo quy tắc của Java.

## 1. Pattern matching trong switch

Với `switch` truyền thống, các nhãn thường là hằng số như `case 1`, giá trị enum hoặc chuỗi. Pattern matching cho phép nhãn mô tả kiểu của đối tượng:

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Chuỗi dài " + text.length();
        case Integer number -> "Số nguyên " + number;
        case null -> "Giá trị null";
        default -> "Kiểu khác";
    };
}
~~~

Khi giá trị là `String`, nhánh đầu khớp và biến mẫu `text` có kiểu `String` bên trong nhánh đó. Tương tự, nhánh `Integer` cung cấp biến `number`. Không cần tự kiểm tra bằng `instanceof` rồi ép kiểu thủ công.

Ví dụ trên là đoạn minh họa, không phải chương trình độc lập. Pattern matching switch được hoàn thiện trong **Java 21**. Nếu dùng phiên bản Java cũ hơn, cú pháp này có thể chưa được hỗ trợ hoặc cần cờ preview ở các phiên bản preview trước đó.

### Biểu thức switch và câu lệnh switch

Biểu thức `switch` tạo ra một giá trị và thường được dùng trong phép gán hoặc câu lệnh `return`:

~~~java
String label = switch (status) {
    case ACTIVE -> "Đang hoạt động";
    case INACTIVE -> "Đã dừng";
};
~~~

Câu lệnh `switch` thực hiện hành động trong từng nhánh. Java yêu cầu biểu thức `switch` phải đầy đủ (exhaustive), tức mọi giá trị có thể có đều phải khớp với một nhánh. Câu lệnh `switch` dùng pattern labels cũng phải đầy đủ. Với các dạng `switch` truyền thống khác, việc có cần nhánh mặc định hay không phụ thuộc vào loại switch và mục đích xử lý.

## 2. Sealed hierarchy đóng những kiểu nào?

Một kiểu được khai báo `sealed` giới hạn các kiểu con trực tiếp được phép kế thừa hoặc triển khai. Ví dụ:

~~~java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record Triangle(double base, double height) implements Shape {}
~~~

Đây là cấu trúc minh họa. Trong cùng một tệp Java, các kiểu con có thể được khai báo cạnh kiểu cha. Trong chương trình thực tế, các kiểu này cũng có thể được tổ chức thành những tệp riêng theo quy tắc của sealed types.

Một kiểu con trực tiếp được phép của sealed class/interface phải khai báo một trong ba trạng thái:

- `final`: không cho phép kế thừa tiếp.
- `sealed`: tiếp tục giới hạn danh sách kiểu con trực tiếp của nó.
- `non-sealed`: mở lại nhánh đó để các kiểu khác có thể kế thừa hoặc triển khai.

Các record mặc định là `final`, vì vậy chúng phù hợp làm những nhánh lá của phân cấp đóng. Nếu một nhánh con là `sealed`, trình biên dịch có thể tiếp tục xét phân cấp con của nhánh đó. Nếu nhánh là `non-sealed`, có thể có những kiểu con mới mà mã nguồn hiện tại chưa liệt kê; một pattern khớp chính kiểu nhánh đó có thể bao phủ toàn bộ các kiểu con của nó.

Sealed hierarchy tạo ra một tập kiểu có thể phân tích được ở thời điểm biên dịch. Đây là nền tảng để trình biên dịch xác nhận tính đầy đủ của pattern switch.

## 3. Tính đầy đủ của switch trên sealed hierarchy

Giả sử `Shape` chỉ cho phép ba kiểu con trực tiếp là `Circle`, `Rectangle` và `Triangle`. Khi xử lý cả ba kiểu trong một biểu thức switch, có thể không cần `default`:

~~~java
static double area(Shape shape) {
    return switch (shape) {
        case Circle c -> Math.PI * c.radius() * c.radius();
        case Rectangle r -> r.width() * r.height();
        case Triangle t -> rBaseArea(t.base(), t.height());
    };
}

static double rBaseArea(double base, double height) {
    return base * height / 2.0;
}
~~~

Mỗi nhánh xử lý một kiểu con được cho phép, nên biểu thức switch đầy đủ. Trong ví dụ này, `rBaseArea` chỉ tách phép tính diện tích tam giác thành một hàm nhỏ để làm rõ cách viết; chương trình hoàn chỉnh bên dưới dùng trực tiếp công thức đó.

Nếu bỏ nhánh `Triangle`, trình biên dịch báo lỗi vì không thể chứng minh rằng biểu thức switch trả về giá trị cho mọi trường hợp của `Shape`. Lỗi được phát hiện khi biên dịch thay vì chờ đến khi dữ liệu có kiểu còn thiếu xuất hiện trong production.

### Trình biên dịch xác định tính đầy đủ ra sao?

Với một sealed type, trình biên dịch xét các kiểu con được phép:

1. Nếu một kiểu con là `final`, nó là một nhánh đóng.
2. Nếu một kiểu con tiếp tục là `sealed`, trình biên dịch có thể xét các kiểu con được phép của nó.
3. Nếu một kiểu con là `non-sealed`, phân cấp mở tại nhánh đó. Pattern khớp kiểu của nhánh có thể bao phủ các lớp con của nó; nếu chỉ liệt kê một số lớp con đã biết thì chưa đủ để chứng minh tính đầy đủ.
4. Mỗi giá trị có thể có của kiểu selector phải được bao phủ bởi ít nhất một nhãn phù hợp.

Một pattern kiểu cha có thể bao phủ cả các kiểu con của nó. Ví dụ, nhánh `case Shape s` khớp mọi đối tượng không null có kiểu tương thích với `Shape`; tuy nhiên, đặt nhánh rộng như vậy trước các nhánh `Circle`, `Rectangle` hoặc `Triangle` sẽ khiến các nhánh sau trở nên không thể đạt tới và gây lỗi dominance.

## 4. Ví dụ hoàn chỉnh với Java 21+

Ví dụ dưới đây sử dụng sealed interface, record, record patterns, guard `when` và switch expression. Ba record đại diện cho ba hình; cả hai phương thức xử lý đều bao phủ đầy đủ phân cấp mà không cần `default`.

Lưu toàn bộ nội dung vào tệp `SealedSwitchDemo.java`:

~~~java
import java.util.List;
import java.util.Locale;

public class SealedSwitchDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    record Circle(double radius) implements Shape {}
    record Rectangle(double width, double height) implements Shape {}
    record Triangle(double base, double height) implements Shape {}

    static double area(Shape shape) {
        return switch (shape) {
            case Circle(double radius) -> Math.PI * radius * radius;
            case Rectangle(double width, double height) -> width * height;
            case Triangle(double base, double height) -> base * height / 2.0;
        };
    }

    static String kind(Shape shape) {
        return switch (shape) {
            case Circle(double radius) when radius == 0.0 -> "Đường tròn suy biến";
            case Circle(double radius) -> "Đường tròn";
            case Rectangle(double width, double height) when width == height -> "Hình vuông";
            case Rectangle(double width, double height) -> "Hình chữ nhật";
            case Triangle(double base, double height) -> "Tam giác";
        };
    }

    public static void main(String[] args) {
        List<Shape> shapes = List.of(
            new Circle(2.0),
            new Rectangle(3.0, 3.0),
            new Triangle(4.0, 5.0)
        );

        for (Shape shape : shapes) {
            System.out.printf(Locale.ROOT, "%s: %.2f%n", kind(shape), area(shape));
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 21 trở lên:

~~~text
javac SealedSwitchDemo.java
java SealedSwitchDemo
~~~

Kết quả chuẩn:

~~~text
Đường tròn: 12.57
Hình vuông: 9.00
Tam giác: 10.00
~~~

Giải thích:

- `Shape` giới hạn các kiểu con được phép thành ba record.
- Record patterns như `Circle(double radius)` vừa kiểm tra kiểu vừa lấy thành phần `radius` từ record.
- `area` tính diện tích theo kiểu hình và phải xử lý đủ ba kiểu.
- Trong `kind`, nhãn có guard `when` kiểm tra trường hợp đặc biệt trước. Nhãn `Circle(double radius)` không có guard tiếp theo sẽ xử lý các hình tròn còn lại. Tương tự, hình chữ nhật có chiều rộng bằng chiều cao được mô tả là hình vuông trước khi xét hình chữ nhật thông thường.
- Các kiểu lồng trong lớp công khai có thể nằm chung một tệp; tên tệp phải trùng với lớp `public SealedSwitchDemo`.

## 5. Guard, dominance và thứ tự nhãn

Guard `when` thêm điều kiện vào một pattern. Nó hữu ích khi kiểu đã khớp nhưng hành vi cần phân biệt theo dữ liệu:

~~~java
return switch (shape) {
    case Rectangle(double w, double h) when w == h -> "Hình vuông";
    case Rectangle(double w, double h) -> "Hình chữ nhật";
    case Circle(double r) -> "Hình tròn";
    case Triangle(double b, double h) -> "Tam giác";
};
~~~

Đoạn trên giả định `shape` có kiểu `Shape` như trong ví dụ. Nhánh hình chữ nhật có guard phải đứng trước nhánh tổng quát cho `Rectangle`; nếu đảo thứ tự, nhánh tổng quát sẽ bắt mọi hình chữ nhật và nhánh có guard không bao giờ được chạy.

**Dominance** là tình huống một nhãn đứng trước đã bao phủ tất cả giá trị mà nhãn phía sau có thể khớp. Ví dụ, một nhãn kiểu `Shape` không có guard đứng trước các nhãn kiểu con sẽ khiến các nhãn con bị thống trị. Trình biên dịch phát hiện trường hợp này để tránh nhánh chết.

Các nguyên tắc thực hành:

- Đặt nhánh hẹp hoặc có điều kiện cụ thể trước nhánh rộng.
- Sau một nhánh có guard, thường cần một nhánh không có guard để xử lý những giá trị còn lại của cùng kiểu.
- Không thêm `default` chỉ để che lỗi thiếu nhánh nếu mục tiêu là để compiler phát hiện phân cấp sealed đã thay đổi.
- Chỉ dùng guard cho điều kiện có ý nghĩa nghiệp vụ; tránh sao chép logic phức tạp vào nhiều nhãn.

## 6. Giá trị null và nhánh default

Tính đầy đủ của sealed hierarchy mô tả những đối tượng thuộc các kiểu trong phân cấp. Nó không tự động có nghĩa là `null` được xử lý. Với pattern switch, nếu selector là `null` và không có nhãn `case null`, switch sẽ ném `NullPointerException`.

Nếu `null` là một đầu vào hợp lệ, hãy xử lý tường minh:

~~~java
static String describe(Shape shape) {
    return switch (shape) {
        case null -> "Không có hình";
        case Circle(double radius) -> "Hình tròn";
        case Rectangle(double width, double height) -> "Hình chữ nhật";
        case Triangle(double base, double height) -> "Tam giác";
    };
}
~~~

Ở đây, `case null` xử lý riêng giá trị null; các nhãn còn lại vẫn bao phủ đầy đủ những kiểu con của `Shape`.

`default` hữu ích khi cần một nhánh dự phòng có chủ ý, chẳng hạn xử lý kiểu chưa biết trong một API mở. Nhưng với sealed hierarchy, một nhánh `default` có thể làm trình biên dịch không còn báo thiếu kiểu mới khi danh sách `permits` thay đổi. Nếu muốn tận dụng tính an toàn khi phân cấp phát triển, nên liệt kê các nhánh cụ thể và để compiler kiểm tra.

Nếu các thành phần được biên dịch riêng rồi phiên bản sealed hierarchy thay đổi mà mã switch chưa được biên dịch lại, giả định về tính đầy đủ có thể không còn đúng ở runtime. Với switch expression, trường hợp không nhánh nào khớp có thể dẫn đến `MatchException`. Nên biên dịch lại các module liên quan khi thay đổi danh sách kiểu con được phép.

## 7. Khi nào nên dùng và những lỗi thường gặp

Dùng pattern matching switch kết hợp sealed hierarchy khi:

- Một kiểu cha đại diện cho một tập trường hợp nghiệp vụ hữu hạn, chẳng hạn trạng thái đơn hàng, biểu thức trong AST, thông điệp giao thức hoặc hình học.
- Mỗi kiểu con cần một nhánh xử lý riêng.
- Muốn thay đổi mô hình dữ liệu khiến compiler chỉ ra các vị trí cần cập nhật.
- Cần trích xuất thành phần của record mà không viết nhiều câu lệnh `instanceof` và ép kiểu.

Những lỗi thường gặp:

1. **Bỏ sót kiểu con:** biểu thức switch không đầy đủ sẽ không biên dịch. Thêm nhánh còn thiếu hoặc một nhánh dự phòng có chủ ý.
2. **Dùng `default` quá sớm:** code vẫn biên dịch khi kiểu con mới được thêm, nhưng logic nghiệp vụ có thể chưa được cập nhật. Ưu tiên liệt kê các kiểu con đã biết khi phân cấp thực sự đóng.
3. **Nhầm sealed với final:** `sealed` không có nghĩa là không có lớp con; nó có nghĩa là các kiểu con trực tiếp được kiểm soát bởi danh sách cho phép. Kiểu con có thể là `sealed`, `final` hoặc `non-sealed`.
4. **Quên nhánh mở rộng `non-sealed`:** nếu chỉ liệt kê các lớp con đã biết của một nhánh mở, những kiểu mới có thể không được bao phủ. Dùng pattern cho chính kiểu nhánh mở hoặc default khi có lý do.
5. **Nhầm null với một kiểu con:** null không khớp với pattern kiểu. Nếu cần hỗ trợ null, thêm `case null` và quyết định rõ hành vi.
6. **Sắp xếp nhãn sai:** nhánh tổng quát có thể thống trị nhánh cụ thể phía sau. Đặt pattern cụ thể và guard trước pattern rộng.
7. **Biên dịch bằng JDK quá cũ:** ví dụ dùng record patterns và pattern matching switch cần JDK 21 trở lên. Kiểm tra `java -version` và `javac -version` để chắc chắn compiler phù hợp.

Khi thêm một kiểu con mới vào sealed hierarchy, hãy tìm những switch đang xử lý kiểu cha, cập nhật các nhánh cần thiết rồi biên dịch và chạy lại các kiểm thử. Cách này biến thay đổi mô hình dữ liệu thành lỗi biên dịch có thể phát hiện sớm, thay vì để một trường hợp mới âm thầm rơi vào logic không phù hợp.
