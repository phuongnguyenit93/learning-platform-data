# Deconstruct record phẳng trong Java 21

**Deconstruction** (tách thành phần) của một record phẳng là cách khớp một đối tượng record và lấy trực tiếp các thành phần của nó vào những biến riêng. Trong Java 21+, ta làm điều này bằng **record pattern**, ví dụ `Item(String sku, int quantity, double unitPrice)` hoặc `Item(var sku, var quantity, var unitPrice)`.

Bài này tập trung vào **record phẳng**: các thành phần của record là giá trị thông thường như `String`, `int`, `double`; ta tách đúng **một cấp** và chưa cần record pattern lồng nhau. Record patterns trở thành tính năng chính thức từ **Java 21** (JEP 440). Có thể kết hợp chúng với `instanceof` và `switch`; không cần tùy chọn `--enable-preview` khi biên dịch với Java 21.

## 1. Từ record thông thường đến deconstruction

Định nghĩa record lưu một dòng hàng hóa:

```java
record Item(String sku, int quantity, double unitPrice) {}
```

Record này có **ba thành phần theo đúng thứ tự khai báo**:

| Vị trí | Thành phần | Kiểu | Ý nghĩa |
| --- | --- | --- | --- |
| 1 | `sku` | `String` | Mã mặt hàng |
| 2 | `quantity` | `int` | Số lượng |
| 3 | `unitPrice` | `double` | Đơn giá |

Tạo dữ liệu bằng constructor:

```java
Item item = new Item("PEN", 2, 12.5);
```

Khi cần đọc, cách thông thường là gọi accessor:

```java
String sku = item.sku();
int quantity = item.quantity();
double price = item.unitPrice();
```

Với **record pattern**, trong một ngữ cảnh khớp phù hợp, ta có thể kiểm tra và trích xuất ngay:

```java
Object candidate = item;

if (candidate instanceof Item(String sku, int quantity, double price)) {
    System.out.println(sku);      // PEN
    System.out.println(quantity); // 2
    System.out.println(price);    // 12.5
}
```

Trong biểu thức `candidate instanceof Item(String sku, int quantity, double price)`:

1. `candidate` là đối tượng được kiểm tra.
2. `Item` là **kiểu record** cần khớp.
3. `(String sku, int quantity, double price)` là các **component patterns** theo thứ tự thành phần của `Item`.
4. Nếu khớp, `sku`, `quantity`, `price` được khai báo và nhận giá trị tương ứng. Ta sử dụng chúng trong nhánh `if` mà compiler biết phép khớp đã thành công.

Cú pháp `Item(String sku, int quantity, double price)` là **pattern**, không phải lời gọi constructor hay cú pháp tạo record. `new Item("PEN", 2, 12.5)` mới là biểu thức tạo đối tượng.

## 2. Cú pháp record pattern phẳng

Dạng tổng quát khi khớp một record không có cấp lồng:

```text
RecordType(ComponentPattern1, ComponentPattern2, ...)
```

Các `ComponentPattern` ở bài cơ bản thường là **type pattern** với kiểu tường minh hoặc `var`:

```java
// Khai báo tường minh kiểu của từng thành phần.
if (candidate instanceof Item(String s, int q, double p)) {
    System.out.println(s + ": " + q * p);
}

// Để trình biên dịch suy ra kiểu của từng thành phần.
if (candidate instanceof Item(var s, var q, var p)) {
    System.out.println(s + ": " + q * p);
}
```

Hai cách trên tách cùng ba thành phần. Ở phiên bản `var`, trình biên dịch suy ra **`s` có kiểu `String`, `q` có kiểu `int`, `p` có kiểu `double`** từ khai báo `record Item(String sku, int quantity, double unitPrice)`. `var` không tạo biến kiểu động.

Tên biến trong pattern **không bắt buộc giống** tên thành phần record. Chẳng hạn `p` vẫn nhận `unitPrice` vì nó đứng ở **vị trí thứ ba**. Tuy nhiên, hãy chọn tên dễ hiểu khi dùng trong mã thực tế.

### Số lượng và kiểu component patterns phải phù hợp

Record `Item` có ba thành phần nên cần ba component patterns. Những cách viết sau không hợp lệ:

```java
// Sai: thiếu thành phần thứ ba.
// candidate instanceof Item(String sku, int quantity)

// Sai: thứ tự kiểu không tương thích với khai báo record.
// candidate instanceof Item(int quantity, String sku, double price)

// Sai: chưa khai báo biến bằng một kiểu hoặc var.
// candidate instanceof Item(sku, quantity, unitPrice)
```

Ba dòng trên **chỉ minh họa mã sai**, được đặt trong comment, không phải ví dụ cần chạy. Pattern thông thường tách dựa trên thứ tự và kiểu thành phần record; nó không ánh xạ biến theo tên.

## 3. Dùng record pattern với instanceof

`instanceof` phù hợp khi giá trị ban đầu có kiểu rộng hơn, chẳng hạn `Object`, và ta chỉ muốn thao tác khi dữ liệu đúng là `Item`:

```java
static double calculateTotal(Object candidate) {
    if (candidate instanceof Item(var sku, var quantity, var price)) {
        return quantity * price;
    }
    return 0.0;
}
```

Ở đây `sku` được tách nhưng chưa dùng; đó là biến hợp lệ, tuy vậy nên chỉ khai báo các biến cần thiết trong những thiết kế phức tạp hơn. Với record phẳng, record pattern yêu cầu cung cấp component pattern cho mọi thành phần (Java 21 chưa có cú pháp bỏ qua thành phần `_` chính thức như một mẫu thông thường). Nếu chỉ cần một accessor duy nhất, cách viết `candidate instanceof Item item` rồi gọi `item.quantity()` có thể đọc dễ hơn.

Có thể kết hợp với điều kiện `&&` để kiểm tra thêm:

```java
if (candidate instanceof Item(var sku, var quantity, var price)
        && quantity > 0) {
    System.out.println(sku + " total=" + (quantity * price));
}
```

Vế phải của `&&` chỉ được đánh giá sau khi record pattern khớp, vì thế `quantity` nằm trong phạm vi sử dụng hợp lệ. Ngược lại, các biến của record pattern không tự động có phạm vi khắp phương thức.

### Khi không khớp

- Nếu `candidate` là một `Item`, record pattern được kiểm tra và các thành phần phù hợp được tách.
- Nếu `candidate` là kiểu khác, ví dụ `String`, phép `instanceof` trả về `false`.
- Nếu `candidate == null`, phép `instanceof` với record pattern cũng trả về `false`. Nó không tự gọi accessor trên đối tượng `null`.

**Deconstruction không sửa record**, không tạo bản sao mới và không chuyển đổi đối tượng sang một kiểu khác. Nó kiểm tra, đọc các thành phần bằng cơ chế accessor của record và đưa kết quả vào những biến mới của pattern.

## 4. Dùng record pattern trong switch

Record pattern cũng có thể xuất hiện trong nhánh `case` của `switch` từ Java 21:

```java
static String stockLabel(Object candidate) {
    return switch (candidate) {
        case null -> "null input";
        case Item(var sku, var quantity, var price) when quantity == 0 ->
                "Empty: " + sku;
        case Item(var sku, var quantity, var price) ->
                "Available: " + sku + " x" + quantity;
        default -> "Other type";
    };
}
```

Diễn giải:

- `case Item(var sku, var quantity, var price)` vừa nhận diện `Item` vừa tách ba thành phần; các biến được dùng trong biểu thức sau `->`.
- `when quantity == 0` là **guard**: chỉ chọn nhánh đầu khi record khớp **và** số lượng bằng 0.
- Nhánh `Item(...)` không có guard nhận các `Item` còn lại.
- `case null` xử lý chính giá trị đầu vào của `switch` bằng `null`. `default` không phải cách thay thế mặc định cho `case null`.
- `default` nhận các kiểu giá trị khác.

Trong cùng một `switch`, đặt một pattern rộng không điều kiện **trước** pattern cụ thể có thể làm case sau không thể tới được (lỗi *dominance*). Ở ví dụ này, nhánh có guard đứng trước nhánh `Item(...)` tổng quát.

Khi logic ngắn, `instanceof` thường đủ; khi muốn phân loại nhiều trường hợp dựa trên giá trị thành phần, `switch` giúp tổ chức nhánh rõ hơn.

## 5. Lưu ý đặc biệt về null trong record phẳng

**Record phẳng vẫn có thể chứa thành phần tham chiếu `null`.** Nếu không có quy tắc kiểm tra trong constructor, ta được phép tạo:

```java
Item item = new Item(null, 1, 3.0);
```

`Item` ở đây là đối tượng khác `null`; chỉ có `sku` (kiểu `String`) bằng `null`. Với:

```java
Object candidate = item;

if (candidate instanceof Item(var sku, var quantity, var price)) {
    System.out.println(sku == null); // true
}
```

Record pattern **khớp thành công** và `sku` nhận `null`. Điều đó không mâu thuẫn với quy tắc record pattern không khớp **đối tượng record** bằng `null`. Các component patterns như `var` là những pattern riêng bên trong record pattern.

Cụ thể, khi component type pattern **không điều kiện (unconditional)** đối với kiểu được khai báo của thành phần, nó có thể khớp thành phần `null`. Với `Item`, cả `String sku` (trên thành phần được khai báo `String`) và `var sku` đều là trường hợp có thể tách thành phần đó khi `null`. Sau khi tách, cần kiểm tra `sku == null` trước khi gọi `sku.length()` hoặc các phương thức khác.

Ngược lại, trường hợp:

```java
Object candidate = null;
boolean matched = candidate instanceof Item(var sku, var q, var p);
// matched == false
```

vẫn trả về `false` vì **đối tượng ngoài** không khớp `Item(...)`.

Các thành phần `quantity` và `unitPrice` có kiểu nguyên thủy `int`, `double` nên **không thể chứa `null`**. Nếu nghiệp vụ không cho phép `sku == null`, hãy đặt ràng buộc trong constructor của record, thay vì trông chờ deconstruction tự từ chối nó:

```java
record StrictItem(String sku, int quantity, double unitPrice) {
    StrictItem {
        java.util.Objects.requireNonNull(sku, "sku");
    }
}
```

Đoạn trên là một ví dụ độc lập về **khai báo record**, không thuộc lớp chạy ở mục 7. `new StrictItem(null, 1, 3.0)` sẽ ném `NullPointerException` khi tạo đối tượng. Quy tắc constructor đảm bảo dữ liệu; record pattern chỉ kiểm tra và tách dữ liệu đã có.

## 6. So sánh ba cách truy cập dữ liệu

Giả sử có `Object candidate` được dự đoán là một `Item`:

| Cách | Ví dụ | Phù hợp khi |
| --- | --- | --- |
| Type pattern | `candidate instanceof Item item`, sau đó `item.sku()` | Muốn giữ đối tượng, chỉ đọc một vài thành phần, hoặc gọi nhiều phương thức của record |
| Record pattern kiểu tường minh | `candidate instanceof Item(String sku, int quantity, double price)` | Muốn nhìn thấy kiểu của mọi thành phần ngay tại nơi tách |
| Record pattern dùng `var` | `candidate instanceof Item(var sku, var quantity, var price)` | Muốn giảm lặp kiểu nhưng vẫn có các biến thành phần được suy luận kiểu tĩnh |

Không có cú pháp Java 21 dạng `var (sku, quantity, price) = item;` hay `(sku, quantity, price) = item;` để deconstruct như một lệnh gán độc lập. **Record pattern xuất hiện trong một ngữ cảnh pattern matching** như `instanceof` hoặc `case` của `switch`.

Các biến `sku`, `quantity`, `price` là biến cục bộ được ràng buộc bởi phép khớp. Thay đổi biến cục bộ (khi được phép gán lại) **không thay đổi thành phần của record**; các thành phần record có tính bất biến ở cấp tham chiếu/thành phần, còn giá trị tham chiếu tới một đối tượng có thể thay đổi bên trong nếu đối tượng đó mutable.

## 7. Ví dụ Java 21 hoàn chỉnh có thể biên dịch và chạy

Lưu nguyên đoạn này vào **`FlatRecordDeconstruction.java`**:

```java
public class FlatRecordDeconstruction {
    record Item(String sku, int quantity, double unitPrice) {}

    static String describe(Object candidate) {
        if (candidate instanceof Item(String sku, int quantity, double unitPrice)) {
            return "Item " + sku + ": qty=" + quantity + ", price=" + unitPrice;
        }
        return "Not an Item";
    }

    static double total(Object candidate) {
        if (candidate instanceof Item(var sku, var quantity, var unitPrice)
                && quantity > 0) {
            return quantity * unitPrice;
        }
        return 0.0;
    }

    static String stockLabel(Object candidate) {
        return switch (candidate) {
            case null -> "null input";
            case Item(var sku, var quantity, var unitPrice) when quantity == 0 ->
                    "Empty: " + sku;
            case Item(var sku, var quantity, var unitPrice) ->
                    "Available: " + sku + " x" + quantity;
            default -> "Other type";
        };
    }

    public static void main(String[] args) {
        Item item = new Item("PEN", 2, 12.5);
        System.out.println(describe(item));
        System.out.println("Total: " + total(item));
        System.out.println(stockLabel(item));
        System.out.println(stockLabel(new Item("NOTE", 0, 7.0)));
        System.out.println(describe("hello"));
        System.out.println(stockLabel(null));
        Object missingSku = new Item(null, 1, 3.0);
        if (missingSku instanceof Item(var sku, var quantity, var unitPrice)) {
            System.out.println("sku null: " + (sku == null));
        }
        System.out.println("Accessor: " + item.sku());
    }
}
```

Biên dịch và chạy bằng **JDK 21+**:

```bash
javac --release 21 -encoding UTF-8 FlatRecordDeconstruction.java
java FlatRecordDeconstruction
```

**Kết quả chuẩn:**

```text
Item PEN: qty=2, price=12.5
Total: 25.0
Available: PEN x2
Empty: NOTE
Not an Item
null input
sku null: true
Accessor: PEN
```

Giải thích kết quả:

1. `describe(item)` dùng record pattern kiểu tường minh để lấy `sku="PEN"`, `quantity=2`, `unitPrice=12.5`.
2. `total(item)` dùng `var` để lấy các thành phần rồi tính `2 * 12.5 = 25.0`. Điều kiện `quantity > 0` trong cùng phép `if` chứng minh nhánh phù hợp.
3. `stockLabel(item)` chọn nhánh `Item(...)` tổng quát, còn `Item("NOTE", 0, 7.0)` chọn nhánh có guard vì `quantity == 0`.
4. `describe("hello")` không khớp kiểu `Item` và trả `Not an Item`.
5. `stockLabel(null)` đi vào `case null`.
6. Record cuối có `sku == null` nhưng deconstruction bằng `var sku` vẫn thành công; accessor `item.sku()` của record đầu tiên trả `PEN`.

Ví dụ chỉ dùng những tính năng chuẩn Java 21 và đã kiểm chứng được bằng `javac --release 21`.

## 8. Các lỗi phổ biến

1. **Viết thiếu hoặc thừa component patterns.** Với ba thành phần, phải khớp đúng ba vị trí trong `Item(...)`. Nếu record được thay đổi cấu trúc, hãy cập nhật pattern tương ứng.
2. **Nhầm tên biến với cơ chế ánh xạ.** `Item(var price, var amount, var code)` vẫn gắn biến thứ nhất với `sku`, thứ hai với `quantity`, thứ ba với `unitPrice`. Việc đặt tên sai gây hiểu nhầm dù code có thể biên dịch.
3. **Đọc biến pattern khi chưa chắc chắn khớp.** Không dùng `sku` ngoài nơi compiler bảo đảm record pattern thành công. Trong `if`, dùng trong nhánh đúng; trong `switch`, dùng trong phần case phù hợp.
4. **Nhầm record pattern với lời gọi constructor.** Pattern mô tả cấu trúc cần tách; constructor tạo một đối tượng mới. Không viết `new Item(var sku, var quantity, var price)`.
5. **Cho rằng mọi thành phần tham chiếu đều khác null.** `Item(var sku, ...)` vẫn có thể tách `sku == null`, nên kiểm tra trước khi gọi phương thức trên `sku`.
6. **Dùng cú pháp record pattern với class thường.** `RecordType(...)` chỉ phù hợp với kiểu record được khai báo bằng `record`; với class thường, dùng type pattern hoặc accessor thích hợp.
7. **Sử dụng phiên bản Java chưa hỗ trợ ổn định.** Bài dùng `record patterns` và `switch` pattern matching chuẩn Java 21. Với JDK 17, chương trình ở trên không biên dịch được bằng cú pháp này.
8. **Cho rằng `switch default` tự bắt null.** Với selector `null` trong `switch` dạng này, cần xử lý `case null`; nếu không, có thể phát sinh `NullPointerException`.

## 9. Bài tập tự kiểm tra

**Bài 1.** Với `Object c = new Item("BOOK", 4, 6.0);`, nếu tách bằng `Item(var code, var q, var p)`, giá trị `q * p` là bao nhiêu?

*Đáp án:* `24.0`. `q` là `4` và `p` là `6.0`; kiểu suy ra lần lượt là `int` và `double`.

**Bài 2.** Pattern `Item(var price, var qty, var sku)` có trích xuất đúng theo ý nghĩa tên biến không?

*Đáp án:* Không. Java trích xuất theo **vị trí**, nên `price` nhận mã hàng (kiểu `String`), `qty` nhận số lượng (kiểu `int`), còn `sku` nhận đơn giá (kiểu `double`). Hãy đặt tên khớp ý nghĩa thực tế.

**Bài 3.** `new Item(null, 1, 3.0)` có thể khớp `Item(var sku, var quantity, var unitPrice)` không?

*Đáp án:* Có. Đối tượng `Item` ngoài khác `null` và `var sku` có thể nhận thành phần `sku == null`. Tuy nhiên thao tác `sku.length()` khi đó vẫn gây `NullPointerException`.

**Bài 4.** Nếu chỉ cần `item.sku()`, luôn phải dùng record pattern không?

*Đáp án:* Không. Sử dụng accessor thông thường, hoặc type pattern `Item item` khi đang kiểm tra một `Object`, có thể đơn giản và rõ ràng hơn.

**Tài liệu tham khảo:** [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441).
