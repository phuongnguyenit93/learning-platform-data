# Kết hợp deconstruction với điều kiện (Java 21+)

## 1. Mục tiêu của bài

**Deconstruction** trong Java là thao tác **tách các thành phần của một `record` bằng record pattern**. Khi kết hợp với **điều kiện Boolean**, ta có thể diễn đạt quy tắc “dữ liệu phải có đúng cấu trúc này **và** các giá trị bên trong phải đạt tiêu chí kia” mà không phải gọi lần lượt từng accessor rồi ép kiểu thủ công.

Ví dụ, từ `record Point(int x, int y)`, ta muốn nhận một điểm chỉ khi cả hai tọa độ dương:

```java
if (value instanceof Point(var x, var y) && x > 0 && y > 0) {
    System.out.println("Điểm ở góc phần tư I");
}
```

Ở đây, **`Point(var x, var y)` kiểm tra cấu trúc và tách giá trị**, còn **`x > 0 && y > 0` kiểm tra quy tắc trên các giá trị vừa tách**. Hai phần phối hợp nhờ phép toán `&&` có đánh giá ngắn mạch (short-circuit) và quy tắc phạm vi biến pattern.

Tính năng **Record Patterns (JEP 440)** và **Pattern Matching for `switch` (JEP 441)** đều là tính năng ổn định từ **Java 21**. Các ví dụ bên dưới dùng **JDK 21+**, không cần `--enable-preview`. Java 17 đã hỗ trợ `record` nhưng chưa có cú pháp record pattern ổn định như trong bài này.

Sau bài học, bạn sẽ phân biệt được:
- **Kiểm tra cấu trúc** bằng record pattern và **kiểm tra giá trị** bằng biểu thức điều kiện.
- Cách kết hợp record pattern với `instanceof ... && ...` và `case ... when ...`.
- Cách dùng biến vừa deconstruct trong điều kiện, guard và phần thân nhánh.
- Tình huống nested record không khớp, component `null`, guard sai, thứ tự `case` và nhánh dự phòng.
- Khi nào dùng guard, khi nào xác thực dữ liệu ở constructor hoặc phương thức nghiệp vụ.

## 2. Hai bước: tách cấu trúc trước, kiểm tra điều kiện sau

Xét khai báo:

```java
record Point(int x, int y) {}
```

Record pattern:

```java
Point(var x, var y)
```

có ý nghĩa:

1. Giá trị cần so khớp phải là một đối tượng `Point` không-null.
2. Record có đúng hai component theo khai báo là `x` và `y`. Pattern con `var x` nhận component thứ nhất; `var y` nhận component thứ hai.
3. Java suy luận `x` và `y` đều có kiểu `int`, vì khai báo record có hai component kiểu `int`.
4. Sau khi pattern **khớp hoàn toàn**, các biến được dùng trong điều kiện và nhánh xử lý mà quy tắc phạm vi cho phép.

Deconstruction **không tự xác thực** “điểm phải có tọa độ dương”, “tuổi phải đủ 18” hay “mã không được bỏ trống”. Các điều kiện này được thêm bằng biểu thức Boolean, thường là `&&` trong `if` hoặc `when` trong `switch`.

Có thể đọc một nhánh điều kiện theo thứ tự:

```text
Giá trị đầu vào
     |
     v
Khớp kiểu record ngoài cùng?
     | không
     +--------------------------> Nhánh khác
     |
    có
     v
Khớp mọi component pattern?
     | không
     +--------------------------> Nhánh khác
     |
    có
     v
Ràng buộc các biến được tách
     |
     v
Điều kiện Boolean/guard đúng?
     | không
     +--------------------------> Nhánh khác
     |
    có
     v
Thực hiện phần thân nhánh
```

Đây là **mô hình đọc logic**; không nên dựa vào đó để suy đoán chi tiết tối ưu hóa của JVM. Record pattern đọc component thông qua accessor; không tự tạo record mới, không tự biến dữ liệu thành immutable nếu component tham chiếu tới đối tượng có thể thay đổi.

## 3. Dùng `instanceof` kết hợp `&&`

### 3.1. Biến pattern dùng được ở bên phải `&&`

```java
static boolean isPositivePoint(Object value) {
    return value instanceof Point(var x, var y)
        && x > 0
        && y > 0;
}
```

Giả sử `Point` đã được định nghĩa. Java xử lý theo logic sau:

- Nếu `value` không phải `Point`, biểu thức `instanceof` trả `false`; các vế `x > 0` và `y > 0` **không được đánh giá**.
- Nếu `value` là `Point`, record pattern tách `x` và `y`. Khi đó các biến được phép tham gia phần còn lại của biểu thức `&&`.
- Nếu `x <= 0`, phép `&&` dừng sớm; không cần kiểm tra `y > 0`.
- Chỉ khi mọi điều kiện đúng, kết quả mới là `true`.

**Vì sao compiler cho phép dùng `x` và `y` ở bên phải `&&`?** Vì vế phải chỉ được thực hiện khi vế trái đúng; compiler có bằng chứng rằng pattern đã khớp, nên hai biến đã được gán.

### 3.2. Phạm vi biến trong `if`

```java
if (value instanceof Point(var x, var y)
        && x > 0 && y > 0) {
    System.out.println("x=" + x + ", y=" + y);
}
```

`x` và `y` có thể dùng trong thân `if` vì thân chỉ chạy khi toàn bộ điều kiện đúng. Chúng không tự trở thành biến cục bộ có thể truy cập ở mọi dòng sau `if`.

Có thể đặt thêm điều kiện liên quan trực tiếp dữ liệu:

```java
record Employee(String name, int age) {}

// Đoạn mã minh họa trong phạm vi có biến value:
if (value instanceof Employee(var name, var age)
        && name != null
        && !name.isBlank()
        && age >= 18) {
    System.out.println(name + " đủ tuổi");
}
```

Điều kiện `name != null` phải đứng **trước** `!name.isBlank()` để tránh `NullPointerException`. Khi `name` là null, `&&` dừng ngay và không gọi phương thức trên null.

### 3.3. Không thay `&&` bằng `||` tùy ý

Ví dụ **cố ý sai, không biên dịch**:

```java
// SAI: nếu vế trái false thì x chưa được ràng buộc.
if (value instanceof Point(var x, var y) || x > 0) {
    System.out.println("...");
}
```

Vế phải của `||` được đánh giá khi vế trái **false**. Lúc đó pattern có thể chưa khớp nên không thể dùng `x` như trong ví dụ.

Nếu muốn kiểm tra “không phải điểm **hoặc** điểm có x dương”, có thể viết tách các nhánh rõ ràng:

```java
if (!(value instanceof Point(var x, var y))) {
    System.out.println("Không phải Point");
} else if (x > 0) {
    System.out.println("Point có x dương");
}
```

Trong `else if`, compiler biết nhánh `instanceof` đã khớp ở nhánh trước bị phủ định. Điều này minh họa **flow scoping**: phạm vi biến pattern phụ thuộc đường điều khiển bảo đảm pattern thành công.

## 4. Dùng `switch` với `when` sau record pattern

Với nhiều điều kiện phân loại, viết `switch` thường rõ hơn chuỗi `if/else if`.

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "Không có điểm";

        case Point(var x, var y) when x == 0 && y == 0 ->
            "Gốc tọa độ";

        case Point(var x, var y) when x > 0 && y > 0 ->
            "Góc phần tư I";

        case Point(var x, var y) ->
            "Điểm khác";

        default -> "Không phải Point";
    };
}
```

Đoạn này là **phương thức minh họa**, giả sử `Point` đã khai báo trong cùng phạm vi hợp lệ.

Cách đọc `case Point(var x, var y) when x > 0 && y > 0`:

1. Selector của `switch` phải khớp record pattern `Point(var x, var y)`.
2. Nếu khớp, `x` và `y` trở thành biến cho guard.
3. Java đánh giá `x > 0 && y > 0`.
4. Chỉ khi guard đúng, thực hiện phần sau `->`.
5. Guard false thì xem xét nhánh tiếp theo; vì thế `case Point(var x, var y)` không guard ở cuối xử lý các điểm còn lại.

**`when` chỉ dùng trong nhãn pattern `case` của `switch`**, không dùng sau `instanceof` trong `if`. Cặp công cụ tương ứng là:

| Mục đích | Cú pháp |
| --- | --- |
| Một điều kiện trong `if` | `value instanceof Point(var x, var y) && x > 0` |
| Chọn nhánh trong `switch` | `case Point(var x, var y) when x > 0 -> ...` |
| Nhận mọi `Point` còn lại | `case Point(var x, var y) -> ...` |

Guard phải có kiểu `boolean` (hoặc biểu thức có thể dùng làm điều kiện Boolean hợp lệ). Nó có thể gọi phương thức trên biến đã tách; nên ưu tiên điều kiện dễ đọc, không có tác dụng phụ.

## 5. Deconstruction lồng nhau rồi áp dụng điều kiện nghiệp vụ

Record pattern có thể **lồng nhau** để vừa kiểm tra cấu trúc đầu vào, vừa lấy dữ liệu nằm sâu trong nhiều record.

Cho dữ liệu:

```java
record Customer(String name, int age) {}
record Address(String city, String postalCode) {}
record Order(String code, Customer customer, Address address, long amount) {}
```

Pattern đầy đủ:

```java
Order(
    var code,
    Customer(var name, var age),
    Address(var city, var postalCode),
    var amount
)
```

Giải thích từ ngoài vào trong:

- `Order(...)`: selector phải là `Order` không-null.
- `var code`: lấy mã đơn hàng dưới dạng `String`.
- `Customer(var name, var age)`: component thứ hai phải là `Customer` không-null; lấy `String name` và `int age`.
- `Address(var city, var postalCode)`: component thứ ba phải là `Address` không-null; lấy hai chuỗi tương ứng.
- `var amount`: lấy `long amount`.

Sau khi **mọi tầng record khớp**, ta mới dùng guard kiểm tra điều kiện nghiệp vụ:

```java
case Order(
        var code,
        Customer(var name, var age),
        Address(var city, var postalCode),
        var amount)
        when age >= 18
            && name != null && !name.isBlank()
            && city != null && !city.isBlank()
            && postalCode != null && !postalCode.isBlank()
            && amount >= 1_000_000L ->
    "Đơn hàng ưu tiên: " + code;
```

Chú ý: **`Customer(...)` và `Address(...)` yêu cầu component record tương ứng không-null**; ngược lại `var name`, `var city`, `var postalCode` là các pattern vô điều kiện cho kiểu component, nên có thể nhận chính giá trị null. Vì vậy những chuỗi này vẫn cần kiểm tra trước khi gọi `isBlank()`.

Khi đọc guard dài, hãy chia theo nhóm ý nghĩa: (1) tuổi, (2) tên, (3) địa chỉ, (4) giá trị đơn hàng. Nếu quy tắc nghiệp vụ quá phức tạp, đặt tên cho điều kiện bằng một phương thức thuần (pure function) để người đọc hiểu nhanh.

## 6. Chương trình hoàn chỉnh: `instanceof`, `when` và nested deconstruction

Tạo tệp **`ConditionDeconstructionDemo.java`** với nội dung sau:

```java
public class ConditionDeconstructionDemo {
    record Point(int x, int y) {}
    record Customer(String name, int age) {}
    record Address(String city, String postalCode) {}
    record Order(String code, Customer customer,
                 Address address, long amount) {}

    // Một điều kiện Boolean: chỉ xem tọa độ khi pattern thành công.
    static boolean isInQuadrantI(Object value) {
        return value instanceof Point(var x, var y)
            && x > 0
            && y > 0;
    }

    // Nhiều nhóm kết quả: pattern -> guard -> nhánh.
    static String classifyPoint(Object value) {
        return switch (value) {
            case null -> "Không có điểm";
            case Point(var x, var y) when x == 0 && y == 0 ->
                "Gốc tọa độ";
            case Point(var x, var y) when x > 0 && y > 0 ->
                "Góc phần tư I";
            case Point(var x, var y) ->
                "Điểm khác (" + x + ", " + y + ")";
            default -> "Không phải Point";
        };
    }

    static String routeOrder(Object value) {
        return switch (value) {
            case null -> "Không có đơn hàng";

            // Đủ cấu trúc và đạt các điều kiện được ưu tiên.
            case Order(
                    var code,
                    Customer(var name, var age),
                    Address(var city, var postalCode),
                    var amount)
                    when age >= 18
                        && name != null && !name.isBlank()
                        && city != null && !city.isBlank()
                        && postalCode != null
                        && !postalCode.isBlank()
                        && amount >= 1_000_000L ->
                "Ưu tiên: " + code + " - " + name + " - " + city;

            // Đủ thông tin Customer, nhưng tuổi dưới 18.
            case Order(
                    var code,
                    Customer(var name, var age),
                    var address,
                    var amount)
                    when age < 18 ->
                "Cần xác minh tuổi: " + code;

            // Không đi sâu vào component thiếu; nhận chúng bằng var.
            case Order(var code, var customer, var address, var amount)
                    when customer == null || address == null ->
                "Thiếu hồ sơ hoặc địa chỉ: " + code;

            // Các Order còn lại đều được xử lý ở đây.
            case Order(var code, var customer, var address, var amount) ->
                "Thông thường: " + code;

            default -> "Không phải đơn hàng";
        };
    }

    public static void main(String[] args) {
        System.out.println(isInQuadrantI(new Point(2, 3)));
        System.out.println(isInQuadrantI(new Point(-1, 3)));

        System.out.println(classifyPoint(new Point(0, 0)));
        System.out.println(classifyPoint(new Point(2, 3)));
        System.out.println(classifyPoint(new Point(-1, 3)));
        System.out.println(classifyPoint("abc"));

        System.out.println(routeOrder(new Order(
            "DH-01",
            new Customer("An", 22),
            new Address("Hà Nội", "10000"),
            1_200_000L)));

        System.out.println(routeOrder(new Order(
            "DH-02",
            new Customer("Bình", 16),
            new Address("Huế", "53000"),
            1_500_000L)));

        System.out.println(routeOrder(new Order(
            "DH-03",
            null,
            new Address("Đà Nẵng", "50000"),
            2_000_000L)));

        System.out.println(routeOrder(new Order(
            "DH-04",
            new Customer("", 27),
            new Address("TP.HCM", "70000"),
            1_200_000L)));

        System.out.println(routeOrder(null));
    }
}
```

Biên dịch trong thư mục chứa tệp bằng **JDK 21 hoặc mới hơn**:

```bash
javac --release 21 -encoding UTF-8 ConditionDeconstructionDemo.java
java ConditionDeconstructionDemo
```

Đầu ra:

```text
true
false
Gốc tọa độ
Góc phần tư I
Điểm khác (-1, 3)
Không phải Point
Ưu tiên: DH-01 - An - Hà Nội
Cần xác minh tuổi: DH-02
Thiếu hồ sơ hoặc địa chỉ: DH-03
Thông thường: DH-04
Không có đơn hàng
```

### Vì sao mỗi đơn hàng vào đúng nhánh?

- **DH-01:** `Order` có `Customer` và `Address` không-null; `age = 22`, tên/thành phố/mã bưu chính không rỗng và `amount = 1_200_000L`. Nested pattern và tất cả điều kiện guard đều đúng, nên vào nhánh **Ưu tiên**.
- **DH-02:** cấu trúc đầy đủ nhưng `age = 16` khiến guard ưu tiên sai. Guard nhánh thứ hai là `age < 18` đúng, nên vào **Cần xác minh tuổi**.
- **DH-03:** `customer == null` làm pattern `Customer(...)` của nhánh đầu và nhánh thứ hai **không khớp**. Nhánh thứ ba chỉ dùng `var customer` nên nhận null; guard `customer == null || address == null` đúng và in **Thiếu hồ sơ hoặc địa chỉ**.
- **DH-04:** cấu trúc đầy đủ nhưng `name` là chuỗi rỗng, khiến `!name.isBlank()` sai. Tuổi không dưới 18, các component record không thiếu, nên vào nhánh `Order(...)` tổng quát **Thông thường**.
- `routeOrder(null)`: xử lý trực tiếp ở `case null`. Đừng kỳ vọng `default` là nhánh bắt null trong `switch` pattern matching.

Ví dụ được viết để phơi bày **thứ tự ưu tiên của các quy tắc**, không phải đề xuất rằng đơn hàng có tên rỗng luôn được chấp nhận trong hệ thống thực tế. Trong phần mềm thật, tính hợp lệ của hồ sơ cần một quy tắc validation thống nhất.

## 7. Guard thất bại khác với pattern không khớp

Đây là phân biệt quan trọng nhất khi kết hợp deconstruction với điều kiện.

| Trường hợp | Record pattern | Guard | Kết quả |
| --- | --- | --- | --- |
| Đầu vào không phải `Order` | Không khớp ngay tầng ngoài | Không được đánh giá | Xét nhánh khác |
| `Order.customer() == null` với pattern `Customer(...)` | Không khớp tại tầng `Customer` | Không được đánh giá | Xét nhánh nông hơn hoặc nhánh khác |
| `Customer.name() == null` với `Customer(var name, var age)` | Vẫn có thể khớp; `name` nhận null | Kiểm tra `name != null` trả false | Xét nhánh khác |
| `age = 16` với nested pattern đầy đủ | Khớp | `age >= 18` trả false | Xét nhánh khác |
| `age = 22`, tên hợp lệ, số tiền đạt ngưỡng | Khớp | True | Chạy nhánh ưu tiên |

**Một record pattern lồng nhau chỉ thành công khi từng record pattern ở từng tầng thành công.** Điều kiện guard được xét sau khi toàn bộ pattern khớp. Guard false có nghĩa là “dữ liệu phù hợp hình dạng nhưng không đạt quy tắc của nhánh này”.

Với chuỗi Boolean:

```java
when name != null && !name.isBlank() && age >= 18
```

nếu `name == null`, các phần còn lại không được đánh giá. Với `||`, thứ tự cũng là ngắn mạch, nhưng nội dung logic khác:

```java
when customer == null || address == null
```

Chỉ cần **một** trong hai component thiếu là guard đúng. Dấu `||` trong guard này hợp lệ vì `customer` và `address` đều đã được ràng buộc bởi `var` ở pattern bên trái `when`. Không nên nhầm với cách dùng `||` **sau một `instanceof`** khiến biến pattern chưa chắc tồn tại.

## 8. Thứ tự nhánh, dominance và exhaustiveness

Khi nhiều `case` cùng có thể nhận một record, thứ tự từ trên xuống dưới quyết định nhánh được chọn. Nên ưu tiên nhánh **cụ thể và có guard**, rồi cuối cùng mới đến nhánh **tổng quát**.

Ví dụ **cố ý sai, không biên dịch**:

```java
// Minh họa lỗi dominance.
return switch (value) {
    case Point(var x, var y) -> "Mọi điểm";
    case Point(var x, var y) when x > 0 -> "Điểm có x dương";
    default -> "Khác";
};
```

Nhánh `Point(var x, var y)` không guard ở trước đã nhận mọi `Point` không-null; nhánh sau vì thế bị che. Hãy đổi thứ tự:

```java
return switch (value) {
    case Point(var x, var y) when x > 0 -> "Điểm có x dương";
    case Point(var x, var y) -> "Mọi điểm còn lại";
    default -> "Khác";
};
```

Đoạn trên là ví dụ **bổ sung trong phương thức có `value` và khai báo `Point`**, không phải tệp độc lập; nếu `value` có thể null, vẫn cần chính sách `case null` khi chạy.

**Không coi guard là bao phủ đầy đủ kiểu.** Ví dụ:

```java
// SAI: switch expression không exhaustive cho mọi Object.
return switch (value) {
    case Point(var x, var y) when x > 0 -> "x dương";
};
```

Selector kiểu `Object` có thể nhận `String`, `Point` với `x <= 0`, v.v. Cần các nhánh tiếp theo hoặc `default` để expression có kết quả trên mọi đường đi được yêu cầu. Nếu dùng một hệ phân cấp `sealed`, compiler có thể kiểm tra đầy đủ các biến thể theo khai báo; các guard tùy ý thường không thay được nhánh tổng quát bao phủ từng kiểu.

Với `switch` expression, một nhánh có nhiều câu lệnh có thể dùng khối và `yield`:

```java
case Point(var x, var y) when x > 0 -> {
    String text = "x dương: " + x;
    yield text;
}
```

Biến `x`, `y` dùng được trong guard và phần thân nhánh, nhưng không còn trong phạm vi một `case` khác hay bên ngoài `switch`.

## 9. Phân biệt lọc dữ liệu và xác thực dữ liệu

**Pattern + guard phù hợp để lựa chọn cách xử lý** dựa trên cấu trúc và giá trị hiện tại. **Constructor hoặc lớp nghiệp vụ phù hợp để chặn đối tượng không hợp lệ từ lúc tạo**.

Ví dụ record có bất biến về tên khách hàng:

```java
record ValidCustomer(String name, int age) {
    ValidCustomer {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name is required");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age must be nonnegative");
        }
    }
}
```

Đây là **đoạn khai báo record độc lập về mặt cú pháp**, có thể đặt trong một lớp/đơn vị Java phù hợp. Khi constructor đã chặn tên null/rỗng và tuổi âm, code ở nhánh khác có thể dựa trên bất biến đó. Dù vậy, guard vẫn hữu ích cho **quy tắc theo ngữ cảnh** như “khách hàng phải đủ 18 tuổi để thực hiện hành động này”.

Một số lưu ý thực tế:

- Nếu điều kiện phức tạp, trích ra phương thức có tên rõ nghĩa, ví dụ `isEligibleCustomer(name, age)`, thay vì đặt hàng chục phép so sánh khó đọc trong `when`.
- Hạn chế điều kiện có tác dụng phụ trong guard. `switch` có thể xét guard của nhiều nhánh; hành vi nên dễ dự đoán.
- Record pattern gọi accessor để lấy component. Accessor record được tùy biến có thể có hành vi bất thường hoặc ném ngoại lệ. Đừng dùng guard như cách “bắt” mọi lỗi từ accessor.
- Tránh dùng pattern rất sâu nếu chỉ cần một thành phần. Có thể dừng ở `var address` rồi gọi phương thức phụ, giúp cấu trúc điều kiện rõ hơn.
- `var` trong record pattern **suy luận từ kiểu khai báo của component**; nó không biến `int` thành `Object` hoặc tự ép kiểu một giá trị tham chiếu không tương thích.
- Việc Java cho phép pattern khớp cấu trúc không có nghĩa toàn bộ đối tượng luôn hợp lệ cho nghiệp vụ. Chọn nhánh dự phòng phù hợp với chính sách hệ thống.

## 10. Lỗi hay gặp và cách sửa

| Lỗi | Vì sao xảy ra | Cách sửa |
| --- | --- | --- |
| Viết `case Point(var x, var y) && x > 0` | `case` không dùng cách nối Boolean của `if` | Viết `case Point(var x, var y) when x > 0 -> ...`. |
| Viết `value instanceof Point(var x, var y) when x > 0` | `when` dành cho nhãn `case` của `switch` | Dùng `instanceof ... && x > 0`. |
| Dùng biến tách được bên phải `||` sau `instanceof` | Pattern có thể thất bại nên biến chưa chắc được ràng buộc | Dùng `&&` khi cần điều kiện sau pattern thành công; tách nhánh cho logic khác. |
| Gọi `name.isBlank()` khi `name` có thể null | `var name` trên component tham chiếu có thể nhận null | Viết `name != null && !name.isBlank()`. |
| Nhầm `Customer(...)` với `var customer` | Record pattern lồng đòi `Customer` không-null, còn `var` có thể nhận nguyên component null | Chọn độ sâu phù hợp và thêm nhánh xử lý thiếu. |
| Guard bị bỏ qua | Một tầng record pattern không khớp trước đó | Kiểm tra kiểu record ngoài, từng component và record con trước khi xem guard. |
| Case cụ thể không thể tới | Nhánh tổng quát đứng trước gây dominance | Sắp xếp nhánh có điều kiện trước nhánh tổng quát. |
| `switch` expression không exhaustive | Chỉ có case có guard hoặc thiếu kiểu dữ liệu đầu vào khác | Bổ sung các trường hợp còn lại, `default` hoặc bao phủ tập kiểu `sealed`. |
| `switch` ném `NullPointerException` với selector null | Không có nhánh `case null` thích hợp | Thêm `case null` khi chính sách cần xử lý null. |
| Java báo lỗi cú pháp record pattern/`when` | Dùng JDK trước Java 21 hoặc cờ nguồn cũ | Kiểm tra `javac -version` và dùng JDK 21+ với `--release 21`. |
| Giả định guard tự xác thực dữ liệu cho toàn ứng dụng | Guard chỉ áp dụng tại nhánh được xét | Đặt invariant quan trọng tại constructor/validation layer. |

## 11. Bài tập có đáp án gợi ý

**Bài 1 — Điều kiện sau tách.** Với `record Rectangle(int width, int height) {}`, viết biểu thức trả `true` nếu đầu vào là `Rectangle` với hai cạnh dương. Gợi ý:

```java
static boolean isValidRectangle(Object value) {
    return value instanceof Rectangle(var width, var height)
        && width > 0
        && height > 0;
}
```

**Bài 2 — Hai guard cùng khớp.** Với `Point(2, 3)`, nếu nhánh đầu kiểm tra `x > 0` và nhánh sau kiểm tra `y > 0`, nhánh nào chạy? Đáp án: **nhánh đầu** nếu nó xuất hiện trước và pattern khớp; `switch` chọn nhánh đầu tiên thỏa điều kiện.

**Bài 3 — Nested component null.** Với `Order("A", null, address, 2_000_000L)`, guard của nhánh `Order(var code, Customer(...), Address(...), var amount) when ...` có được đánh giá không? Đáp án: **không**, vì record pattern `Customer(...)` đã không khớp; cần một nhánh nông hơn như `Order(var code, var customer, var address, var amount)` để xử lý trường hợp này.

**Bài 4 — Điều kiện an toàn với chuỗi.** Viết lại guard nhận khách hàng tên không rỗng, không null, đủ 18 tuổi. Gợi ý: `name != null && !name.isBlank() && age >= 18`.

**Bài 5 — Thiết kế nhánh.** Thêm một nhánh cho `amount < 0` để báo dữ liệu không hợp lệ. Đặt nhánh này **trước** nhánh `Order(...)` tổng quát và cân nhắc ưu tiên của nó so với nhánh khách hàng chưa đủ tuổi. Đó là quyết định về **quy tắc nghiệp vụ**, khác với khả năng khớp record pattern.

## 12. Ghi nhớ và tài liệu chính thức

- **Deconstruction** kiểm tra kiểu/record và tách component.
- `instanceof Record(...) && condition` giúp xét một điều kiện tổng hợp theo kiểu ngắn mạch.
- `case Record(...) when condition -> ...` chọn nhánh `switch` khi vừa khớp record vừa thỏa guard.
- **Record pattern lồng nhau** yêu cầu từng record ở tầng tương ứng khớp và không-null; **`var` trên component** có thể nhận null nếu kiểu pattern vô điều kiện.
- **Guard false khác pattern thất bại**: cả hai đều khiến nhánh không được chọn, nhưng ở hai bước khác nhau.
- Giữ nhánh có điều kiện ở trước nhánh tổng quát; xử lý `null` và tính exhaustive có chủ đích.

Tài liệu chuẩn để tra cứu:
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
- [Java Language Specification 21 — Patterns, `14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
