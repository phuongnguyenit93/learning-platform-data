# Ôn tập record như nền tảng để sử dụng Record Patterns

Trong Java 21, `record` là kiểu lớp được thiết kế để biểu diễn dữ liệu theo cấu trúc đã khai báo. Record Patterns tận dụng chính cấu trúc đó để kiểm tra một giá trị có thuộc kiểu record mong muốn hay không, đồng thời lấy các thành phần dữ liệu ra thành biến. Vì vậy, trước khi sử dụng Record Patterns, cần hiểu cách khai báo record, cách constructor và accessor hoạt động, cũng như những giới hạn của record trong mô hình dữ liệu.

Record được đưa vào Java dưới dạng tính năng chính thức từ Java 16. **Record Patterns là tính năng chính thức từ Java 21**, có thể dùng trong biểu thức `instanceof` và `switch` mà không cần bật chế độ preview. Bài viết sử dụng cú pháp Java 21 đã được hoàn thiện và tập trung vào những cách dùng còn phù hợp hiện nay.

## 1. Record là gì?

Record là một dạng lớp đặc biệt dùng để mô tả dữ liệu bằng danh sách các thành phần (record components). Từ khai báo ngắn gọn đó, trình biên dịch tự tạo những thành phần cơ bản như trường lưu trữ, constructor chính, accessor, `equals()`, `hashCode()` và `toString()`.

Ví dụ:

```java
public record Product(String code, String name, int price) {
}
```

Khai báo trên mô tả một `Product` có ba thành phần `code`, `name` và `price`. Khi tạo đối tượng:

```java
Product product = new Product("P-100", "Keyboard", 850_000);

System.out.println(product.code());
System.out.println(product.name());
System.out.println(product.price());
```

Các phương thức `code()`, `name()` và `price()` là accessor được sinh tự động. Tên accessor trùng với tên thành phần, không có tiền tố `get` theo quy ước JavaBeans. Constructor chính nhận các giá trị theo đúng thứ tự khai báo thành phần.

Nếu không cần xác thực hoặc xử lý bổ sung, record có thể chỉ gồm một dòng khai báo. Đây là cách biểu diễn rõ ràng cho những dữ liệu mà danh tính của đối tượng được xác định chủ yếu bởi các giá trị thành phần.

## 2. Những thành phần Java tạo cho record

Với khai báo:

```java
public record Point(int x, int y) {
}
```

Trình biên dịch tạo các thành phần tương đương về mặt sử dụng như sau:

| Thành phần | Vai trò |
|---|---|
| Trường `private final int x`, `private final int y` | Lưu giá trị của các record components |
| Constructor `Point(int x, int y)` | Khởi tạo record từ các giá trị đầu vào |
| `int x()` và `int y()` | Trả về giá trị từng thành phần |
| `equals(Object)` | So sánh dựa trên các thành phần record |
| `hashCode()` | Tạo mã băm dựa trên các thành phần record |
| `toString()` | Tạo chuỗi thể hiện tên record và các thành phần |

Đây là mô tả về hành vi do ngôn ngữ quy định, không phải mã nguồn mà lập trình viên cần tự viết lại. Các trường thành phần là `private final`; mã bên ngoài truy cập giá trị thông qua accessor.

Ví dụ về so sánh:

```java
Point first = new Point(3, 5);
Point second = new Point(3, 5);

System.out.println(first.equals(second)); // true
System.out.println(first);                // Point[x=3, y=5]
```

Hai đối tượng khác nhau vẫn có thể bằng nhau theo `equals()` nếu các thành phần tương ứng bằng nhau. Điều này hữu ích khi record biểu diễn tọa độ, khoảng thời gian, cấu hình hoặc một giá trị dữ liệu có cấu trúc.

## 3. Constructor và xác thực dữ liệu

Record có constructor chính (canonical constructor), với danh sách tham số tương ứng thứ tự và kiểu của các record components. Có thể để trình biên dịch tự sinh constructor hoặc tự khai báo để kiểm soát việc khởi tạo.

### Compact constructor

Compact constructor cho phép kiểm tra hoặc chuẩn hóa tham số mà không cần viết lại danh sách tham số và các lệnh gán trường:

```java
import java.util.Objects;

public record Customer(String name, int age) {
    public Customer {
        Objects.requireNonNull(name, "name must not be null");
        name = name.strip();

        if (name.isEmpty()) {
            throw new IllegalArgumentException("name must not be empty");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must not be negative");
        }
    }
}
```

Trong compact constructor, `name` và `age` là các tham số ngầm định. Có thể kiểm tra hoặc gán lại tham số để chuẩn hóa giá trị. Sau khi phần thân constructor kết thúc bình thường, Java tự gán các tham số cuối cùng vào trường tương ứng. Vì vậy, không viết `this.name = name` hoặc `this.age = age` trong compact constructor.

Nếu cần viết rõ danh sách tham số và tự gán trường, có thể khai báo canonical constructor đầy đủ:

```java
public record Range(int start, int end) {
    public Range(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("start must not exceed end");
        }
        this.start = start;
        this.end = end;
    }
}
```

Hai cách khai báo trên phục vụ cùng mục đích: bảo đảm mọi đối tượng record được tạo ra đều thỏa mãn các bất biến dữ liệu đã đặt ra.

## 4. Record có bất biến không?

Record có các trường thành phần `final`, vì vậy sau khi đối tượng được khởi tạo, không thể thay thế giá trị tham chiếu hoặc giá trị nguyên thủy được lưu trong những trường đó. Tuy nhiên, điều này **không đồng nghĩa với bất biến sâu (deep immutability)**.

Ví dụ:

```java
import java.util.List;

public record Team(String name, List<String> members) {
}
```

Trường `members` không thể được gán sang một danh sách khác thông qua tham chiếu bên trong record sau khi khởi tạo. Nhưng nếu danh sách ban đầu có thể thay đổi, nội dung danh sách vẫn có thể thay đổi:

```java
var names = new java.util.ArrayList<>(List.of("An", "Binh"));
Team team = new Team("Platform", names);

names.add("Chi");
System.out.println(team.members()); // [An, Binh, Chi]
```

Nếu mô hình dữ liệu cần bảo vệ danh sách khỏi thay đổi từ bên ngoài, có thể tạo bản sao bất biến trong compact constructor:

```java
import java.util.List;
import java.util.Objects;

public record Team(String name, List<String> members) {
    public Team {
        Objects.requireNonNull(name);
        members = List.copyOf(members);
    }
}
```

`List.copyOf` tạo một danh sách không thể sửa đổi và tách cấu trúc danh sách khỏi nguồn đầu vào. Nếu phần tử bên trong là đối tượng có thể thay đổi, việc sao chép danh sách vẫn không tự tạo bản sao sâu của từng phần tử. Cần thiết kế tiếp các kiểu thành phần nếu yêu cầu bất biến sâu.

Record Patterns đọc các giá trị qua accessor của record. Vì vậy, cần thiết kế thành phần dữ liệu có ý nghĩa và có hành vi truy cập ổn định; không nên xem record là bảo đảm rằng toàn bộ đồ thị đối tượng bên trong đều bất biến.

## 5. Record phù hợp với loại dữ liệu nào?

Record phù hợp khi cấu trúc dữ liệu đã xác định và giá trị của các thành phần là điều quan trọng nhất khi so sánh đối tượng. Một số trường hợp thường gặp:

- Giá trị tọa độ, khoảng thời gian, khoảng số hoặc đơn vị đo.
- Dữ liệu đầu vào và đầu ra của một thao tác nghiệp vụ.
- Kết quả truy vấn hoặc dữ liệu trung gian có cấu trúc rõ ràng.
- Thông tin cấu hình được tạo một lần và truyền qua nhiều tầng xử lý.
- Thành phần lồng nhau trong một mô hình dữ liệu lớn hơn.

Ví dụ:

```java
public record Address(String city, String country) {
}

public record Employee(String id, String name, Address address) {
}
```

`Employee` chứa một record khác là `Address`. Cấu trúc lồng nhau này sẽ hữu ích khi dùng Record Patterns để lấy thông tin nhân viên và địa chỉ trong cùng một biểu thức mẫu.

Record không phải lựa chọn mặc định cho mọi lớp. Nếu đối tượng cần thay đổi trạng thái trong suốt vòng đời, cần kế thừa từ một lớp cơ sở khác, hoặc có danh tính và vòng đời độc lập với các giá trị của nó, một class thông thường thường phù hợp hơn. Record luôn là lớp `final`, kế thừa trực tiếp từ `java.lang.Record`, không thể mở rộng một lớp khác; tuy vậy, record có thể triển khai interface và khai báo phương thức.

Record có thể khai báo phương thức instance, phương thức static, trường static và constructor bổ sung. Record không được khai báo thêm trường instance ngoài các record components. Nếu record được khai báo bên trong một lớp khác, nó có tính chất static ngầm định.

## 6. Record Patterns trong Java 21 hoạt động như thế nào?

Record Pattern cho phép kiểm tra một đối tượng record và phân rã các thành phần của nó thành những pattern biến. Thay vì kiểm tra kiểu, ép kiểu rồi gọi từng accessor, có thể mô tả cấu trúc cần khớp ngay trong mẫu.

Ví dụ với `Point`:

```java
public record Point(int x, int y) {
}

static String describe(Object value) {
    if (value instanceof Point(int x, int y)) {
        return "x=" + x + ", y=" + y;
    }
    return "Not a point";
}
```

Trong biểu thức `value instanceof Point(int x, int y)`:

1. Java kiểm tra giá trị có phải một `Point` phù hợp hay không.
2. Nếu khớp, các accessor thành phần được sử dụng để lấy `x` và `y`.
3. Các giá trị lấy được được gán cho pattern biến `x` và `y` trong phạm vi nhánh khớp.

Kiểu của pattern biến được suy ra từ kiểu thành phần record. Trong ví dụ trên, `x` và `y` có kiểu `int`. Tên biến trong mẫu do người viết chọn; không bắt buộc trùng tên thành phần record.

Record Pattern không tạo đối tượng record mới và cũng không so sánh toàn bộ đối tượng bằng `equals()`. Nó kiểm tra kiểu record rồi lấy giá trị thành phần để tiếp tục khớp các mẫu con.

## 7. Dùng Record Patterns trong switch

Java 21 cho phép sử dụng Record Patterns trong nhãn `case` của switch. Có thể kết hợp mẫu record với guard `when` để kiểm tra thêm điều kiện trên các pattern biến.

```java
public record Customer(String name, int age) {
}

static String classify(Object value) {
    return switch (value) {
        case null -> "No customer";
        case Customer(String name, int age) when age >= 18 ->
            name + " is an adult";
        case Customer(String name, int age) ->
            name + " is under 18";
        default -> "Unsupported value";
    };
}
```

Các nhãn `case` được xét theo thứ tự. Trường hợp có guard được đặt trước trường hợp tổng quát hơn để đối tượng trưởng thành được xử lý đúng nhánh. `case null` xử lý rõ ràng giá trị `null`; nếu không có nhãn này, switch trên selector `null` sẽ ném `NullPointerException`.

Trong `instanceof`, giá trị `null` không khớp với record pattern. Với các dữ liệu có thể null, cần xử lý null riêng trước khi sử dụng giá trị đã phân rã.

## 8. Phân rã record lồng nhau

Một record component có thể tự nó là một record. Record Pattern cho phép lồng mẫu để truy cập cấu trúc nhiều cấp trong cùng một biểu thức.

```java
public record Address(String city, String country) {
}

public record Employee(String id, String name, Address address) {
}

static String describe(Object value) {
    if (value instanceof Employee(
            String id,
            String name,
            Address(String city, String country))) {
        return name + " (" + id + ") works in " + city + ", " + country;
    }
    return "Not an employee";
}
```

Mẫu ngoài kiểm tra `Employee`, còn mẫu lồng bên trong kiểm tra và phân rã `Address`. Nếu `address` là `null`, mẫu record lồng không khớp và nhánh `if` không được thực hiện. Cách phân rã này giúp thể hiện cấu trúc dữ liệu ngay tại nơi xử lý, đặc biệt hữu ích với các kết quả truy vấn hoặc mô hình dữ liệu có nhiều thành phần lồng nhau.

Có thể dùng `var` trong các vị trí thành phần để trình biên dịch suy ra kiểu:

```java
if (value instanceof Employee(var id, var name, var address)) {
    System.out.println(name + " - " + address);
}
```

Khi cần thể hiện rõ cấu trúc sâu hoặc muốn kiểm soát kiểu tại từng cấp, có thể viết kiểu tường minh như ví dụ trước. Chọn cách viết sao cho người đọc dễ hiểu dữ liệu đang được lấy ra.

## 9. Những điểm cần nhớ khi thiết kế record cho Record Patterns

Record Patterns làm việc hiệu quả nhất khi record có cấu trúc dữ liệu rõ ràng, tên thành phần có ý nghĩa và accessor trả về giá trị phù hợp với mô hình đã công bố. Khi thiết kế, cần chú ý:

1. **Chọn thành phần có ý nghĩa:** chỉ đưa vào record những giá trị thực sự mô tả trạng thái dữ liệu của nó.
2. **Đặt tên thành phần rõ ràng:** tên tốt giúp mẫu như `Employee(var id, var name, Address(var city, var country))` dễ đọc.
3. **Bảo vệ bất biến:** dùng compact constructor để xác thực hoặc chuẩn hóa đầu vào; sao chép các collection nếu cần tránh thay đổi cấu trúc từ bên ngoài.
4. **Hiểu tính bất biến nông:** `final` bảo vệ tham chiếu thành phần, không tự bảo vệ đối tượng mutable được tham chiếu.
5. **Xử lý null có chủ đích:** đặc biệt với record lồng nhau hoặc dữ liệu đầu vào không được bảo đảm đầy đủ.
6. **Giữ accessor ổn định:** Record Pattern lấy dữ liệu thông qua accessor, vì vậy accessor được tùy biến cần giữ đúng ý nghĩa của thành phần.
7. **Chọn đúng loại:** dùng record cho dữ liệu có cấu trúc và class thông thường cho đối tượng cần trạng thái mutable, kế thừa lớp hoặc danh tính riêng.

## 10. Tổng kết

Record cung cấp cách khai báo dữ liệu ngắn gọn với các thành phần `final`, constructor chính, accessor và những phương thức cơ bản được sinh tự động. Compact constructor giúp bảo vệ điều kiện hợp lệ của dữ liệu, còn các phương thức và interface cho phép record tham gia vào thiết kế ứng dụng như những kiểu Java khác trong phạm vi mà record hỗ trợ.

Trong Java 21, Record Patterns dùng cấu trúc record để kiểm tra kiểu và lấy các thành phần ra thành pattern biến. Có thể dùng chúng với `instanceof`, `switch`, guard `when` và các record lồng nhau. Hiểu rõ record, accessor, constructor, null và tính bất biến nông sẽ giúp thiết kế mô hình dữ liệu dễ đọc, an toàn và phù hợp với Record Patterns.

## Tài liệu tham khảo

- [JEP 395: Records](https://openjdk.org/jeps/395) — đặc tả tính năng record được hoàn thiện trong Java 16.
- [JEP 440: Record Patterns](https://openjdk.org/jeps/440) — Record Patterns được hoàn thiện trong Java 21.
- [Java Language Specification, Java SE 21 — Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10) — quy tắc ngôn ngữ cho record class.
- [Java Language Specification, Java SE 21 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30) — cú pháp và ngữ nghĩa pattern trong Java 21.
