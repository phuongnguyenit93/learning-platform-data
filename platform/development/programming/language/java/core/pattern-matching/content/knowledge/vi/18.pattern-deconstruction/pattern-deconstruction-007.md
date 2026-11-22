# Đặt tên component variable khi deconstruct record trong Java

Một **record pattern** cho phép kiểm tra kiểu record của một giá trị, sau đó **phân rã các component thành những biến có tên** để sử dụng ngay. Việc chọn tên cho những biến ấy quyết định đoạn code có dễ hiểu hay không, đặc biệt khi record chứa nhiều component cùng kiểu hoặc có record lồng nhau.

Trong ngữ cảnh **Java Core Pattern Matching → Deconstruction**, bài này giải thích cách đặt tên **component pattern variable**, dùng `var` hoặc kiểu tường minh, phạm vi tồn tại của biến, nguyên tắc đặt tên và những lỗi thường gặp. Record patterns là tính năng chính thức từ **Java 21** (JEP 440), không cần bật preview trong Java 21 trở lên.

## 1. Phân biệt tên record component và tên component variable

Khai báo record:

```java
record Point(int x, int y) {}
```

`x` và `y` ở đây là **record components**. Chúng xác định dữ liệu của record và tạo các accessor `x()`, `y()`. Khi phân rã một `Point`, ta có thể đặt tên biến mới:

```java
// Trích đoạn minh họa: 'input' là Object đã khai báo.
if (input instanceof Point(var horizontal, var vertical)) {
    System.out.println(horizontal + ", " + vertical);
}
```

Trong `Point(var horizontal, var vertical)`:

- `Point` là kiểu record cần kiểm tra.
- `var horizontal` là **component pattern** đầu tiên, lấy component `x` vào **pattern variable** tên `horizontal`.
- `var vertical` là component pattern thứ hai, lấy component `y` vào pattern variable tên `vertical`.
- Tên `horizontal` và `vertical` **không bắt buộc trùng** với tên component `x` và `y`. Việc ánh xạ dựa trên **thứ tự** component được khai báo, không dựa trên tên biến.
- Record vẫn giữ nguyên các accessor `x()` và `y()`; đặt tên biến trong pattern không đổi cấu trúc hay tên thành phần của record.

Ví dụ khác với tên theo ý nghĩa sử dụng:

```java
record Range(int startInclusive, int endExclusive) {}

// Trích đoạn: 'candidate' có kiểu Object.
if (candidate instanceof Range(var from, var to)) {
    System.out.println("[" + from + ", " + to + ")");
}
```

Ở đây `from` lấy `startInclusive` và `to` lấy `endExclusive`. Vì biến sẽ dùng trong ngữ cảnh tạo khoảng giá trị, ta chọn tên ngắn mà vẫn dễ hiểu; nhưng đừng chọn tên làm người đọc hiểu sai ý nghĩa biên đầu/cuối.

## 2. Cú pháp: `var` hoặc kiểu tường minh

Có hai cách thường gặp để đặt tên biến trong record pattern:

```java
record Point(int x, int y) {}

// Cách 1: var — compiler suy luận kiểu của biến từ component.
if (input instanceof Point(var px, var py)) {
    int sum = px + py;
}

// Cách 2: kiểu tường minh.
if (input instanceof Point(int px, int py)) {
    int sum = px + py;
}
```

Cả hai ví dụ đều là những trích đoạn có biến `input` kiểu `Object` đã được khai báo. Với `Point(int x, int y)`, `px` và `py` đều có kiểu `int` trong hai cách viết.

**Chọn `var` khi** kiểu của component đã rõ từ tên record, ngữ cảnh ngắn gọn và không cần kiểm tra kiểu cụ thể hơn. **Chọn kiểu tường minh khi** cần nhấn mạnh hoặc kiểm tra một kiểu cụ thể của component.

Ví dụ một component được khai báo rộng hơn kiểu cần xử lý:

```java
record Message(Object content) {}

// Trích đoạn; 'input' có kiểu Object.
if (input instanceof Message(String text)) {
    System.out.println(text.toUpperCase());
}
```

`Message(String text)` chỉ khớp khi `content` chứa một đối tượng `String` khác `null`. `text` có kiểu `String`, nên gọi `toUpperCase()` được compiler cho phép. Nếu dùng `Message(var text)` thì `text` được suy luận là `Object`; không thể gọi trực tiếp `toUpperCase()` nếu chưa kiểm tra hoặc chuyển kiểu phù hợp.

**Lưu ý:** `var` trong record pattern là cú pháp **khai báo pattern variable**, không phải chỗ để viết tên component tự do. Phải có đúng một component pattern cho mỗi vị trí cần phân rã.

## 3. Đặt tên theo thứ tự và theo vai trò

Trong record:

```java
record Transfer(String sender, String receiver, long amount) {}
```

Có ba vị trí, theo thứ tự: `sender`, `receiver`, `amount`. Mẫu sau hợp lệ:

```java
// Trích đoạn; 'item' có kiểu Object.
if (item instanceof Transfer(var fromAccount, var toAccount, var cents)) {
    System.out.println(fromAccount + " -> " + toAccount + ": " + cents);
}
```

Các biến được ràng buộc theo **vị trí**: `fromAccount ← sender`, `toAccount ← receiver`, `cents ← amount`. Không có cơ chế liên kết dựa vào tên. Nếu đảo vị trí `fromAccount` và `toAccount` thì compiler vẫn có thể chấp nhận vì hai component đều là `String`, nhưng ý nghĩa nghiệp vụ sẽ bị đảo. Do đó:

- Giữ thứ tự đúng theo khai báo `record`.
- Dùng tên ngắn khi biểu thức đơn giản (`x`, `y`, `id`), tên mô tả vai trò khi có nhiều giá trị cùng kiểu (`fromAccount`, `toAccount`).
- Khi tên thành phần đã rõ và không có ngữ cảnh mới, nên dùng tên gần với component (`sender`, `receiver`, `amount`) để dễ tra cứu.
- Tránh đặt tên gây hiểu sai đơn vị (`cents` chỉ nên dùng nếu `amount` thực sự được lưu theo cent; nếu không biết đơn vị, hãy dùng `amount` hoặc `amountValue`).

Một pattern cho record có ba component phải có đúng ba component pattern; **không thể chỉ viết hai biến để bỏ qua component thứ ba**.

## 4. Đặt tên khi record pattern lồng nhau

Xét hai record:

```java
record Point(int x, int y) {}
record Shipment(String trackingCode, Point destination, int boxes) {}
```

Có thể phân rã cả `Shipment` và `Point` trong một biểu thức:

```java
// Trích đoạn; 'input' có kiểu Object.
if (input instanceof Shipment(var tracking, Point(var destX, var destY),
                              var boxCount)) {
    System.out.println(tracking + ": " + destX + ", " + destY
            + "; boxes=" + boxCount);
}
```

Các tên biến và nguồn giá trị:

| Pattern variable | Nguồn dữ liệu | Kiểu được suy luận |
| --- | --- | --- |
| `tracking` | `Shipment.trackingCode` | `String` |
| `destX` | `Shipment.destination.x` | `int` |
| `destY` | `Shipment.destination.y` | `int` |
| `boxCount` | `Shipment.boxes` | `int` |

Chú ý `destination` là một component của `Shipment`, nhưng trong mẫu này nó được phân rã tiếp bằng `Point(var destX, var destY)`, nên **không tự động tạo một biến tên `destination`**. Nếu cần tham chiếu cả đối tượng `Point`, dùng một pattern variable riêng tại vị trí thứ hai:

```java
// Trích đoạn thay thế: lấy đối tượng destination, chưa phân rã x/y.
if (input instanceof Shipment(var tracking, var destination, var boxCount)) {
    if (destination != null) {
        System.out.println(destination.x() + ", " + destination.y());
    }
}
```

Cả hai cách đều có ích. Lựa chọn tên biến nào phụ thuộc việc các bước sau cần **toàn bộ đối tượng record** hay chỉ **một số component bên trong**.

## 5. Phạm vi của component pattern variable

Pattern variable được giới hạn bởi **luồng điều khiển chứng minh pattern đã khớp** (flow scoping).

### Trong `if` và toán tử `&&`

```java
record Point(int x, int y) {}

// Trích đoạn; 'input' là Object.
if (input instanceof Point(var px, var py) && px >= 0 && py >= 0) {
    System.out.println("First quadrant or axes: " + px + ", " + py);
}
```

Khi kiểm tra điều kiện bên phải của `&&`, pattern đã khớp, nên `px` và `py` được phép sử dụng. Nếu thay `&&` bằng `||` và tham chiếu `px` trong vế bên phải, compiler không thể bảo đảm pattern đã khớp; đó là lỗi phạm vi.

Bên trong nhánh `if`, có thể dùng những biến đã ràng buộc. Sau khối `if` thông thường, đừng giả định chúng vẫn còn trong phạm vi: khi kiểm tra không khớp, chúng chưa được tạo.

### Trong `switch` và `when`

```java
// Trích đoạn; 'input' là Object.
String result = switch (input) {
    case Point(var px, var py) when px == py -> "Diagonal: " + px;
    case Point(var px, var py) -> "Point: " + px + ", " + py;
    case null -> "No point";
    default -> "Other";
};
```

- `px` và `py` tồn tại trong **nhánh case đang khớp** và có thể dùng trong điều kiện `when`.
- Hai nhánh `case` riêng biệt có thể dùng cùng tên `px` và `py` vì mỗi nhánh có phạm vi riêng.
- Nhánh đầu khớp `Point` thỏa `px == py`; nhánh sau xử lý những `Point` còn lại.
- `case null` xử lý selector `null`; bản thân record pattern `Point(...)` không khớp đối tượng `null`.

Một tên pattern variable trong nhánh này không trở thành biến được chia sẻ cho tất cả nhánh khác.

## 6. Ví dụ Java 21+ hoàn chỉnh: tên biến trong deconstruction

Tạo tệp **`ComponentVariableNamesDemo.java`**:

```java
public class ComponentVariableNamesDemo {
    record Point(int x, int y) {}
    record Shipment(String trackingCode, Point destination, int boxes) {}
    record Message(Object content) {}

    static String describe(Object input) {
        return switch (input) {
            case Shipment(var code, Point(var destX, var destY), var count)
                    when count >= 2 ->
                    code + ": " + destX + "," + destY + " (" + count + " boxes)";

            case Shipment(var code, Point(var x, var y), var count) ->
                    code + ": " + x + "," + y + " (" + count + " box)";

            case Shipment(var code, var destination, var count) ->
                    code + ": destination missing";

            case Message(String text) ->
                    "message: " + text.toUpperCase();

            case Message(var value) ->
                    "message content: " + value;

            case null -> "null input";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
                new Shipment("S-10", new Point(12, 34), 3)));
        System.out.println(describe(
                new Shipment("S-11", new Point(5, 8), 1)));
        System.out.println(describe(
                new Shipment("S-12", null, 2)));
        System.out.println(describe(new Message("fragile")));
        System.out.println(describe(new Message(404)));
        System.out.println(describe(new Message(null)));
        System.out.println(describe(null));
        System.out.println(describe(42));
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac ComponentVariableNamesDemo.java
java ComponentVariableNamesDemo
```

Kết quả:

```text
S-10: 12,34 (3 boxes)
S-11: 5,8 (1 box)
S-12: destination missing
message: FRAGILE
message content: 404
message content: null
null input
other
```

Giải thích luồng khớp:

1. Đối tượng `Shipment("S-10", Point(12, 34), 3)` khớp nhánh đầu; `destX = 12`, `destY = 34`, `count = 3` và điều kiện `count >= 2` đúng.
2. Đối tượng `Shipment("S-11", Point(5, 8), 1)` không qua guard đầu nhưng khớp nhánh thứ hai; tên `x`, `y` của nhánh này là các biến **khác** với `destX`, `destY` ở nhánh đầu.
3. Đối tượng `Shipment("S-12", null, 2)` không khớp hai record pattern lồng nhau, bởi `Point(...)` không khớp component `destination == null`. Nhánh thứ ba dùng `var destination` và nhận được `null`.
4. Với `Message("fragile")`, `Message(String text)` kiểm tra component có kiểu `String` và tạo biến `text`; với số `404` hoặc `null`, nhánh `Message(var value)` nhận giá trị mà không đòi hỏi kiểu `String`.
5. `case null` xử lý đối tượng đầu vào bằng `null`; `default` xử lý số nguyên `42` vì đây không phải `Shipment` hoặc `Message`.

Ví dụ cho thấy **tên biến được lựa chọn cục bộ để giải thích vai trò**: `code`, `destX`, `destY`, `count` hay `text`. Không tên nào thay đổi cách Java lưu các record components.

## 7. Quy tắc đặt tên và các trường hợp dễ nhầm

### Mỗi biến cần một tên hợp lệ, không trùng trong cùng pattern

Trong một record pattern, không thể khai báo hai pattern variable **cùng tên**:

```java
record Point(int x, int y) {}

// SAI: trùng tên x trong cùng record pattern.
if (input instanceof Point(var x, var x)) {
    System.out.println(x);
}
```

Hãy dùng `Point(var x, var y)` hoặc các tên phân biệt như `Point(var left, var right)`. Một pattern variable cũng không thể khai báo lại tên của một local variable đã tồn tại trong phạm vi chồng lấn.

Tên phải tuân thủ quy tắc identifier của Java; tránh keyword, tên gây nhầm lẫn và các từ quá chung như `a`, `b` trong tình huống phức tạp.

### Component có thể là `null`

`var` lấy giá trị và kiểu tĩnh được suy luận; nó **không tự bảo đảm khác `null`** cho component kiểu tham chiếu:

```java
record User(String displayName) {}

// Trích đoạn; 'input' có kiểu Object.
if (input instanceof User(var name)) {
    String shown = name == null ? "(unnamed)" : name;
    System.out.println(shown);
}
```

Nếu component là kiểu nguyên thủy `int`, `var quantity` có kiểu `int` nên không có trường hợp `quantity == null`. Nếu component là `String`, biến có kiểu `String` nhưng vẫn có thể chứa `null`, tùy dữ liệu thực tế.

### Pattern variable khác `record component`

Đặt tên `userName` cho biến trích ra từ `User.displayName` **không đổi** accessor thành `userName()`. Sau khi tạo `User user`, accessor vẫn là `user.displayName()`. Pattern variable chỉ là một tên cục bộ được ràng buộc khi khớp; tên đó không trở thành field, accessor, hay thành viên mới của record.

### Không cần component thì sao?

Nếu cần **bỏ qua** một component, cú pháp phù hợp phụ thuộc phiên bản Java:

```java
record Point(int x, int y) {}

// Java 21: dùng tên mô tả rằng giá trị không được sử dụng.
if (input instanceof Point(var x, var ignoredY)) {
    System.out.println(x);
}

// Java 22+: unnamed pattern '_' là tính năng chính thức.
if (input instanceof Point(var x, _)) {
    System.out.println(x);
}
```

Hai đoạn là **minh họa độc lập cho các phiên bản Java khác nhau**, không phải nội dung có thể cùng biên dịch bằng Java 21. Java 21 chỉ hỗ trợ `_` ở chế độ preview theo JEP 443; từ Java 22, `_` là tính năng chính thức theo JEP 456. Khác với `var ignoredY`, `_` **không khai báo biến có tên để truy cập**.

Khi còn cần sử dụng component, hãy đặt tên rõ nghĩa. Không nên dùng `_` rồi cố tham chiếu đến giá trị bị bỏ qua.

## 8. Những lỗi thường gặp

| Tình huống | Vì sao sai hoặc dễ gây hiểu nhầm | Cách sửa |
| --- | --- | --- |
| `Point(var y, var x)` nhưng dùng `x` làm tọa độ thứ nhất | Binding dựa vào vị trí; đặt tên đảo tạo nhầm lẫn | `Point(var x, var y)` nếu muốn giữ ý nghĩa component gốc |
| `Point(var x)` cho `record Point(int x, int y)` | Thiếu một component pattern | `Point(var x, var y)` hoặc `Point(var x, _)` trên Java 22+ |
| `Point(var x, var x)` | Trùng tên trong cùng pattern | Dùng hai tên khác nhau |
| Tham chiếu `x` sau `if (obj instanceof Point(var x, var y))` không bảo đảm đã khớp | Flow scoping không bảo đảm `x` tồn tại ở vị trí đó | Dùng `x` trong nhánh khớp, hoặc tổ chức lại điều kiện |
| Gọi `text.toUpperCase()` từ `Message(var text)` khi component khai báo là `Object` | `text` có kiểu `Object`, thiếu phương thức đó | Dùng `Message(String text)` hoặc kiểm tra kiểu rõ ràng |
| Tin rằng `var name` làm giá trị tham chiếu khác `null` | `var` chỉ ràng buộc giá trị, không tự kiểm tra khác `null` | Kiểm tra `name != null` trước khi gọi phương thức |
| Dùng `_` trong code Java 21 không bật preview | Unnamed patterns chỉ chính thức từ Java 22 | Dùng tên `ignoredY` trên Java 21 hoặc JDK 22+ |
| Đổi tên pattern variable rồi gọi accessor bằng tên mới | Tên component của record không đổi | Gọi accessor theo khai báo record |

## 9. Bài tập luyện tập

Cho ba record:

```java
record Dimensions(int width, int height) {}
record Product(String sku, Dimensions size, long priceInCents) {}
record Reply(Object payload) {}
```

**Bài 1.** Với `Object input`, viết pattern lấy `width`, `height` của `Dimensions` nhưng đặt tên là `w` và `h`. Cả hai có kiểu gì?

**Đáp án:**

```java
if (input instanceof Dimensions(var w, var h)) {
    System.out.println(w * h);
}
```

`w` và `h` đều có kiểu `int`.

**Bài 2.** Viết pattern lồng nhau cho `Product` để trích `sku` thành `productCode`, `size.width` thành `w`, `size.height` thành `h`, `priceInCents` thành `price`.

**Đáp án:**

```java
if (input instanceof Product(var productCode,
                             Dimensions(var w, var h), var price)) {
    System.out.println(productCode + ": " + w + "x" + h + " @ " + price);
}
```

`productCode` có kiểu `String`, `w` và `h` có kiểu `int`, `price` có kiểu `long`. Pattern lồng nhau không khớp nếu `Product.size` là `null`.

**Bài 3.** Với `Reply(Object payload)`, cách nào giúp khớp khi payload thực sự là `String` và tạo biến `text` có kiểu `String`?

**Đáp án:** `if (input instanceof Reply(String text)) { ... }`. `Reply(var text)` chỉ suy luận `text` là `Object`.

**Bài 4.** Có nên đặt tên biến thứ hai là `height` trong `Dimensions(var width, var height)` nếu code phía sau chỉ sử dụng `width`?

**Đáp án:** Đặt tên `height` vẫn hợp lệ và dễ hiểu trên Java 21. Nếu chạy Java 22+ và thật sự không dùng giá trị thứ hai, có thể viết `Dimensions(var width, _)` để không tạo biến dư. Cần giữ đủ hai vị trí component.

## 10. Ghi nhớ

- `Point(var left, var right)` tạo các **component pattern variables** `left` và `right`. Tên biến là tên cục bộ của pattern, không cần trùng tên component gốc.
- **Thứ tự** record component quyết định giá trị được ràng buộc; đặt tên rõ nghĩa để tránh đảo lẫn các component cùng kiểu.
- `var` cho compiler suy luận kiểu từ khai báo record; kiểu tường minh như `Message(String text)` còn có thể kiểm tra runtime type của component.
- Pattern variable chỉ được dùng khi luồng điều khiển bảo đảm pattern khớp. Trong `switch`, mỗi nhánh có phạm vi biến riêng; trong `if`, biến có thể dùng ở vế phải của `&&` và nhánh khớp.
- Với record lồng nhau, đặt tên ở đúng cấp phân rã; component `null` có thể khiến pattern lồng nhau không khớp.
- Record patterns ổn định từ **Java 21**; unnamed pattern `_` là tính năng chính thức từ **Java 22**.

Tài liệu chính thức: [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle — Record Patterns (Java 21)](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 456 — Unnamed Variables and Patterns](https://openjdk.org/jeps/456).
