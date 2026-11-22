# So sánh type pattern với record pattern trên cùng một record

Trong Java 21, cả type pattern và record pattern đều có thể kiểm tra một đối tượng có thuộc kiểu record hay không. Điểm khác nhau nằm ở dữ liệu được ràng buộc sau khi khớp: type pattern giữ tham chiếu đến toàn bộ đối tượng, còn record pattern phân rã record thành các component để chương trình sử dụng trực tiếp.

Ví dụ xuyên suốt bài dùng cùng một kiểu:

~~~java
record Point(int x, int y) {}
~~~

Với một giá trị có kiểu khai báo rộng như Object, hai cách viết sau đều nhận diện một Point:

~~~java
if (value instanceof Point point) {
    System.out.println(point.x() + ", " + point.y());
}

if (value instanceof Point(int x, int y)) {
    System.out.println(x + ", " + y);
}
~~~

Điều kiện đầu tiên tạo biến point chứa tham chiếu đến record. Điều kiện thứ hai kiểm tra kiểu record rồi lấy hai component theo thứ tự khai báo, tạo các biến x và y.

## 1. Type pattern: kiểm tra kiểu và giữ toàn bộ đối tượng

Type pattern kết hợp phép kiểm tra kiểu với việc khai báo một biến có kiểu tương ứng. Khi biểu thức bên trái instanceof khớp với kiểu được chỉ định, biến pattern được gán đối tượng đó và có thể dùng trong phạm vi mà trình biên dịch xác định là an toàn.

~~~java
record Point(int x, int y) {}

static void printPoint(Object value) {
    if (value instanceof Point point) {
        System.out.println("Point = " + point);
        System.out.println("x = " + point.x());
        System.out.println("y = " + point.y());
    }
}
~~~

Ở đây:

- value instanceof Point kiểm tra đối tượng có phải là một Point hay không.
- point là biến pattern, có kiểu Point và tham chiếu đến chính đối tượng đã khớp.
- Chương trình gọi point.x() và point.y() khi cần đọc component.
- Có thể tiếp tục gọi các phương thức khác của record hoặc truyền toàn bộ point cho một phương thức khác.

Type pattern phù hợp khi xử lý cần giữ đối tượng như một đơn vị: truyền record cho tầng khác, gọi nhiều phương thức, hoặc dùng đối tượng trong một biểu thức phức tạp hơn.

## 2. Record pattern: kiểm tra kiểu và phân rã component

Record pattern cũng kiểm tra kiểu record, nhưng đồng thời khớp các component với những pattern được viết bên trong dấu ngoặc. Các biến component nhận giá trị tương ứng và có kiểu theo khai báo component hoặc theo kiểu suy luận nếu dùng var.

~~~java
record Point(int x, int y) {}

static void printPoint(Object value) {
    if (value instanceof Point(int x, int y)) {
        System.out.println("x = " + x);
        System.out.println("y = " + y);
        System.out.println("sum = " + (x + y));
    }
}
~~~

Trong pattern Point(int x, int y):

1. Point xác định kiểu record cần khớp.
2. int x khớp component thứ nhất và tạo biến x.
3. int y khớp component thứ hai và tạo biến y.
4. Cả record pattern chỉ khớp khi đối tượng là Point và các component pattern bên trong đều khớp.

Record pattern đọc component thông qua accessor tương ứng của record. Với Point, các giá trị được lấy qua x() và y(), nhưng phần gọi accessor được thể hiện ngay trong pattern nên mã xử lý không cần viết lặp lại các lời gọi đó.

Nếu muốn để trình biên dịch suy luận kiểu component, có thể viết:

~~~java
if (value instanceof Point(var x, var y)) {
    // x và y đều có kiểu int
    System.out.println(x + y);
}
~~~

Record pattern không tạo ra một bản sao Point; nó ràng buộc các biến với giá trị component của đối tượng đã khớp. Nếu phần xử lý cần chính tham chiếu đến record, type pattern thường diễn đạt ý định trực tiếp hơn.

## 3. Đặt hai pattern cạnh nhau trên cùng dữ liệu

Chương trình sau chạy cả hai cách trên cùng một giá trị Point, giúp thấy rõ biến nào được tạo ra và dữ liệu nào có thể truy cập:

~~~java
public class PatternComparison {
    record Point(int x, int y) {}

    static void describe(Object value) {
        if (value instanceof Point point) {
            System.out.println("Type pattern:");
            System.out.println("  record = " + point);
            System.out.println("  coordinates = " + point.x() + ", " + point.y());
        }

        if (value instanceof Point(int x, int y)) {
            System.out.println("Record pattern:");
            System.out.println("  x = " + x);
            System.out.println("  y = " + y);
        }
    }

    public static void main(String[] args) {
        describe(new Point(3, 4));
        describe("not a point");
        describe(null);
    }
}
~~~

Biên dịch bằng JDK có hỗ trợ Java 21:

~~~shell
javac --release 21 PatternComparison.java
java PatternComparison
~~~

Với new Point(3, 4), cả hai điều kiện đều khớp. Type pattern cung cấp point, còn record pattern cung cấp x và y. Với chuỗi hoặc null, cả hai điều kiện đều không khớp và phần thân tương ứng không chạy.

| Tiêu chí | Type pattern Point point | Record pattern Point(int x, int y) |
|---|---|---|
| Mục đích | Kiểm tra kiểu và ràng buộc toàn bộ đối tượng | Kiểm tra kiểu và phân rã component |
| Biến được tạo | Một biến point kiểu Point | Các biến component x, y |
| Đọc component | Gọi point.x(), point.y() khi cần | Giá trị component được ràng buộc ngay trong pattern |
| Giữ tham chiếu record | Có, qua point | Không tạo biến đại diện cho toàn bộ record |
| Pattern lồng nhau | Cần truy cập component rồi kiểm tra tiếp | Có thể viết trực tiếp pattern cho record lồng nhau |
| Phù hợp khi | Cần dùng đối tượng như một đơn vị | Chủ yếu cần các giá trị component để xử lý |

Hai cách không loại trừ nhau trong toàn bộ chương trình. Chọn pattern theo dữ liệu mà phần xử lý cần sử dụng.

## 4. Phân rã record lồng nhau

Khác biệt trở nên rõ hơn khi một record chứa một record khác. Với type pattern, chương trình lấy component lồng nhau rồi tiếp tục kiểm tra kiểu. Với record pattern, có thể mô tả toàn bộ cấu trúc cần khớp trong một pattern.

~~~java
record Address(String city, String country) {}
record Customer(String name, Address address) {}

static void printCustomer(Object value) {
    // Type pattern: giữ Customer, sau đó truy cập Address.
    if (value instanceof Customer customer
            && customer.address() instanceof Address address) {
        System.out.println(customer.name());
        System.out.println(address.city());
        System.out.println(address.country());
    }

    // Record pattern: phân rã Customer và Address ngay trong điều kiện.
    if (value instanceof Customer(
            String name,
            Address(String city, String country))) {
        System.out.println(name);
        System.out.println(city);
        System.out.println(country);
    }
}
~~~

Pattern lồng nhau thể hiện rõ cấu trúc dữ liệu mà nhánh xử lý yêu cầu. Trình biên dịch kiểm tra kiểu record và số lượng component theo khai báo của từng record. Mỗi component pattern tiếp tục phải khớp với giá trị component tương ứng.

Nếu cần cả tham chiếu Customer lẫn các giá trị lồng nhau, có thể dùng type pattern cho Customer, sau đó dùng record pattern ở biểu thức kiểm tra component:

~~~java
if (value instanceof Customer customer
        && customer.address() instanceof Address(String city, String country)) {
    // Dùng customer cho toàn bộ đối tượng,
    // đồng thời dùng city và country đã được phân rã.
    System.out.println(customer.name() + " lives in " + city + ", " + country);
}
~~~

## 5. Phạm vi biến pattern

Biến được khai báo trong type pattern và record pattern đều tuân theo flow scoping: biến chỉ dùng được tại những vị trí mà luồng thực thi bảo đảm pattern đã khớp.

Ví dụ với type pattern:

~~~java
if (value instanceof Point point && point.x() > 0) {
    System.out.println(point.y());
}
~~~

Vế bên phải của && chỉ được đánh giá khi vế trái đúng, vì vậy point đã được khởi tạo và có thể sử dụng ở đó. Trong thân if, biến cũng còn trong phạm vi hợp lệ.

Record pattern hoạt động tương tự:

~~~java
if (value instanceof Point(int x, int y) && x < y) {
    System.out.println("x is smaller than y");
}
~~~

Các biến x và y chỉ khả dụng sau khi record pattern khớp. Không thể sử dụng chúng sau một điều kiện có thể kết thúc mà không xác lập việc khớp pattern.

Có thể dùng dạng phủ định với lệnh thoát sớm:

~~~java
if (!(value instanceof Point(int x, int y))) {
    return;
}

System.out.println(x + y);
~~~

Sau câu lệnh if, luồng thực thi chỉ tiếp tục khi pattern đã khớp, nên x và y có thể được sử dụng.

## 6. Những điểm cần kiểm tra khi dùng record pattern

- **Đúng kiểu record:** record pattern chỉ áp dụng cho record type đã khai báo; nó không phải cơ chế khớp cấu trúc cho mọi class có các accessor giống nhau.
- **Đúng thứ tự component:** các pattern bên trong tương ứng với component theo thứ tự khai báo trong record. Cần xem khai báo record khi đọc một pattern dài.
- **Đủ component:** pattern phải thể hiện số component tương ứng với record type. Khi không cần đặt kiểu tường minh cho component, dùng var để mã gọn hơn.
- **Giá trị null:** biểu thức instanceof không khớp với null. Do đó, cả value instanceof Point point và value instanceof Point(int x, int y) đều bỏ qua nhánh khi value là null.
- **Accessor của record:** việc phân rã lấy giá trị thông qua accessor của component. Nếu record khai báo accessor tùy chỉnh, accessor đó vẫn là mã được gọi khi component được đọc; nên giữ accessor đơn giản và ổn định.
- **Không nhầm phân rã với sao chép:** các biến component nhận giá trị do accessor trả về; record pattern không tạo một record mới và cũng không thay đổi đối tượng ban đầu.

## 7. Record pattern trong switch

Java 21 cũng hỗ trợ record pattern trong pattern matching for switch. Điều này hữu ích khi cần chọn nhánh theo cấu trúc record và xử lý component ngay trong nhánh:

~~~java
static String describe(Object value) {
    return switch (value) {
        case Point(int x, int y) -> "Point(" + x + ", " + y + ")";
        case null -> "null";
        default -> "another value";
    };
}
~~~

Nếu nhánh chỉ cần toàn bộ record, có thể dùng type pattern:

~~~java
static String describePoint(Object value) {
    return switch (value) {
        case Point point -> "Point(" + point.x() + ", " + point.y() + ")";
        case null -> "null";
        default -> "another value";
    };
}
~~~

Hai ví dụ là hai cách viết độc lập. Trong cùng một switch, không thể đặt một type pattern bao quát mọi Point trước một record pattern cũng khớp mọi Point, vì nhánh sau sẽ bị nhánh trước chi phối (dominated). Hãy sắp xếp các pattern theo mức độ cụ thể và bảo đảm mỗi nhánh còn có thể được tiếp cận.

## 8. Chọn pattern phù hợp

| Nhu cầu xử lý | Cách viết nên chọn |
|---|---|
| Chỉ cần xác nhận giá trị là Point và giữ đối tượng | value instanceof Point point |
| Cần hai tọa độ để tính toán hoặc so sánh | value instanceof Point(int x, int y) |
| Cần gọi nhiều phương thức hoặc truyền toàn bộ record đi nơi khác | Type pattern |
| Cần kiểm tra cấu trúc record lồng nhau | Record pattern lồng nhau |
| Cần giữ record cha đồng thời lấy component của record con | Kết hợp type pattern và record pattern |
| Cần phân nhánh theo component trong switch | Record pattern trong case |

Type pattern tập trung vào danh tính kiểu và tham chiếu đến đối tượng. Record pattern bổ sung khả năng phân rã dữ liệu theo cấu trúc record. Khi hiểu rõ biến nào được tạo ra và component nào được khớp, có thể chọn cách viết ngắn gọn mà vẫn thể hiện chính xác dữ liệu mà nhánh xử lý cần.
