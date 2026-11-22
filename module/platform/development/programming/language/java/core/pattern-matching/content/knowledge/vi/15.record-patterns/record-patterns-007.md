# Record pattern trong `instanceof` (Java 21+)

## 1. Record pattern giải quyết vấn đề gì?

Một `record` mô tả dữ liệu bằng các thành phần (record components). Khi nhận một giá trị kiểu rộng như `Object`, ta thường muốn vừa kiểm tra nó có phải record mong đợi hay không, vừa lấy ngay các thành phần bên trong để xử lý. **Record pattern** cho phép làm cả hai việc trực tiếp trong toán tử `instanceof`, kể cả khi các thành phần tiếp tục là record lồng nhau.

Tính năng record patterns được chuẩn hóa từ **Java 21** (JEP 440). Trên Java 21 trở lên, các ví dụ dưới đây dùng ngôn ngữ chuẩn, không cần `--enable-preview`. Java 17 hỗ trợ `record` nhưng **chưa hỗ trợ cú pháp record pattern**; Java 19–20 từng cung cấp tính năng ở trạng thái preview.

## 2. Cú pháp và cách khớp

Giả sử khai báo:

```java
record Point(int x, int y) {}
```

Có thể kiểm tra và tách dữ liệu như sau:

```java
Object value = new Point(2, 5);
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y); // 7
}
```

Trong `value instanceof Point(int x, int y)`:

- `Point` là **kiểu record cần khớp**, còn `(int x, int y)` là **danh sách pattern của các thành phần** theo đúng thứ tự khai báo; đây không phải lệnh gọi constructor.
- Java trước hết kiểm tra giá trị có thể được xem là một `Point` hay không. Nếu đúng, hệ thống lấy giá trị từ các accessor `x()` và `y()` rồi khớp lần lượt với hai pattern thành phần.
- Khi toàn bộ pattern khớp, biểu thức trả về `true` và các biến `x`, `y` đã được gán giá trị để dùng trong nhánh phù hợp; nếu không khớp, kết quả là `false`.
- Danh sách pattern phải tương ứng **đủ số lượng và kiểu thành phần** của record; không thể viết `Point(var x)` để bỏ qua thành phần `y`.

Có ba cách tiếp cận liên quan nhưng khác nhau:

| Cách viết | Ý nghĩa |
| --- | --- |
| `value instanceof Point` | Chỉ kiểm tra kiểu, không khai báo biến lấy thành phần. |
| `value instanceof Point p` | Type pattern: kiểm tra và gán cả record cho `p`; cần gọi `p.x()`, `p.y()` khi muốn lấy dữ liệu. |
| `value instanceof Point(int x, int y)` | Record pattern: kiểm tra, đồng thời tách trực tiếp các thành phần thành `x` và `y`. |

Có thể dùng `var` để trình biên dịch suy luận kiểu thành phần tĩnh của record:

```java
if (value instanceof Point(var x, var y)) {
    System.out.println(x * x + y * y);
}
```

Ở đây `x` và `y` vẫn có kiểu `int`, vì hai thành phần của `Point` có kiểu `int`. `var` không có nghĩa là kiểu động hay `Object`.

## 3. Ví dụ hoàn chỉnh có thể chạy

Tạo file **`RecordPatternInstanceofDemo.java`**:

```java
public class RecordPatternInstanceofDemo {
    record Point(int x, int y) {}
    record Marker(String label, Point point) {}

    public static void main(String[] args) {
        Object candidate = new Point(3, 4);

        if (candidate instanceof Point(int x, int y)) {
            System.out.println("Point: (" + x + ", " + y + ")");
            System.out.println("Distance squared: " + (x * x + y * y));
        }

        Object other = new Marker("A", new Point(7, 9));

        if (other instanceof Marker(var label, Point(var x, var y))) {
            System.out.println(label + " at (" + x + ", " + y + ")");
        }

        Object withNullNested = new Marker("B", null);
        System.out.println(
            withNullNested instanceof Marker(var label, Point(var x, var y))
        );

        Object absent = null;
        System.out.println(absent instanceof Point(var x, var y));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac --release 21 RecordPatternInstanceofDemo.java
java RecordPatternInstanceofDemo
```

Kết quả chuẩn:

```text
Point: (3, 4)
Distance squared: 25
A at (7, 9)
false
false
```

Hai dòng cuối trả về `false` vì lần lượt có record `Point` lồng bên trong bằng `null` và toàn bộ giá trị được kiểm tra bằng `null`. Chương trình không gặp `NullPointerException` chỉ vì thực hiện `instanceof` trên biến `null`.

## 4. Record pattern lồng nhau

Với record chứa record:

```java
record Address(String city, String street) {}
record Customer(String name, Address address) {}
```

Ta có thể lấy thành phố ngay khi kiểm tra đối tượng:

```java
Object input = new Customer(
    "Lan",
    new Address("Da Nang", "Bach Dang")
);

if (input instanceof Customer(var name, Address(var city, var street))) {
    System.out.println(name + " - " + city + " - " + street);
    // Lan - Da Nang - Bach Dang
}
```

Pattern ngoài `Customer(...)` và pattern trong `Address(...)` phải **đồng thời khớp**. Mức lồng sâu có thể tăng theo cấu trúc record, nhưng nên giữ code dễ đọc; nếu điều kiện quá dài, có thể dùng type pattern rồi truy cập record theo từng bước.

Lưu ý về `null`:

- Nếu **đối tượng bên trái `instanceof`** là `null`, record pattern không khớp.
- Nếu thành phần `address` là `null`, pattern `Address(...)` bên trong không khớp.
- Một pattern thành phần dùng `var`, chẳng hạn `Customer(var name, var address)`, **có thể gán `null` cho `address`**. Đừng suy diễn rằng mọi thành phần tham chiếu `null` đều làm record pattern thất bại; kết quả tùy pattern con. Hãy kiểm tra `null` khi định sử dụng thành phần đó.

## 5. Kết hợp điều kiện và phạm vi biến

Pattern variables tuân theo cơ chế **flow scoping**: chỉ dùng được ở những vị trí mà trình biên dịch biết pattern đã khớp.

```java
record Point(int x, int y) {}

static boolean isInFirstQuadrant(Object value) {
    return value instanceof Point(var x, var y)
            && x >= 0
            && y >= 0;
}
```

Vế phải của `&&` chỉ được đánh giá nếu vế trái khớp, nên `x` và `y` sử dụng hợp lệ. Với `if`, có thể dùng biến trong nhánh đúng:

```java
if (value instanceof Point(var x, var y) && x == y) {
    System.out.println("Trên đường chéo: " + x);
}
```

Cũng có thể sử dụng kiểu **guard clause** để biến khả dụng sau lệnh `if` kết thúc sớm:

```java
static int sumCoordinates(Object value) {
    if (!(value instanceof Point(int x, int y))) {
        return 0;
    }
    return x + y;
}
```

Ngược lại, đoạn sau **không biên dịch** vì nhánh phải của `||` có thể chạy khi record pattern chưa khớp, nên `x` chưa được gán:

```java
// Sai: x không khả dụng sau || theo cách này.
if (value instanceof Point(var x, var y) || x > 0) {
    // ...
}
```

Không nên dùng `x` hay `y` ở các nhánh không bảo đảm pattern đã khớp.

## 6. Generic record và giới hạn của `instanceof`

Record có thể là generic:

```java
record Box<T>(T value) {}
```

Do **type erasure**, một biểu thức đang có kiểu `Object` không thể được kiểm tra an toàn trực tiếp bằng `Box<String>(var item)` trong `instanceof`: kiểm tra đó đòi hỏi chuyển đổi generic không được bảo đảm. Có thể kiểm tra record với wildcard rồi kiểm tra tiếp kiểu của thành phần:

```java
Object obj = new Box<>("hello");

if (obj instanceof Box<?>(var item) && item instanceof String text) {
    System.out.println(text.toUpperCase()); // HELLO
}
```

Trong tình huống biến đã có kiểu `Box<String>`, trình biên dịch cũng có thể suy luận tham số kiểu cho `Box(var item)`. Hãy phân biệt **kiểu tĩnh của biểu thức** với kiểu thực tế của phần tử khi chọn pattern generic.

## 7. Khi nào nên sử dụng?

Record pattern trong `instanceof` đặc biệt phù hợp khi:

- Dữ liệu đầu vào có kiểu tổng quát (`Object`, interface, hoặc kiểu cha), nhưng cần xử lý một dạng record cụ thể.
- Logic cần **các trường thành phần** ngay lập tức, nhất là cấu trúc lồng nhau.
- Cần kết hợp việc khớp kiểu với ràng buộc nghiệp vụ trong `&&`, chẳng hạn `Point(var x, var y) && x >= 0`.

Nếu chỉ cần biết “có phải `Point` không”, một phép `instanceof Point` thông thường đã đủ. Nếu cần truy cập record nhiều lần, giữ đối tượng nguyên vẹn với `instanceof Point p` đôi khi dễ hiểu hơn.

## 8. Lỗi thường gặp và cách tránh

1. **Chạy trên JDK cũ:** Java 17 không hiểu `Point(var x, var y)`; dùng JDK 21+ cho cú pháp đã ổn định.
2. **Dùng pattern với class thường:** `Point(...)` yêu cầu `Point` là `record`; class Java thông thường không tự hỗ trợ cú pháp tách này.
3. **Thiếu/sai thứ tự thành phần:** record pattern khớp theo danh sách component của record, không theo tên tự chọn của biến. Số lượng component phải đúng; kiểu pattern cũng phải tương thích.
4. **Nhầm `var` với ép kiểu động:** `var` suy luận kiểu khai báo của component; muốn thu hẹp kiểu thực tế bên trong component thì dùng thêm type pattern thích hợp.
5. **Sử dụng biến ở đường đi không bảo đảm khớp:** biến pattern không tự nhiên có phạm vi toàn phương thức; chú ý `&&`, `||`, phủ định và nhánh `if`.
6. **Đồng nhất mọi trường hợp `null`:** record pattern ngoài không khớp `null`; record pattern lồng nhau cũng không khớp một record con `null`; riêng pattern thành phần như `var` có thể nhận giá trị `null`.
7. **Cho rằng record pattern chỉ là cú pháp đọc field trực tiếp:** lúc thực thi Java lấy component thông qua accessor của record. Với accessor tự định nghĩa có hành vi bất thường, việc khớp có thể bị ảnh hưởng.

## 9. Tự kiểm tra

Cho `record Result(int code, String message) {}` và `Object response = new Result(200, "OK");`:

- Viết `instanceof` lấy `code`, `message` trong cùng một biểu thức.
- Chỉ in `message` nếu `code == 200`, bằng `&&`.
- Thử `response = null` và lý giải vì sao nhánh xử lý không chạy.

Lời giải mẫu:

```java
if (response instanceof Result(var code, var message) && code == 200) {
    System.out.println(message); // OK
}
```

**Tài liệu đối chiếu:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440) và [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).