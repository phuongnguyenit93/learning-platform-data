# Bỏ qua component không cần dùng trong record patterns

Khi dùng **record patterns** để phân rã (deconstruct) một `record`, chương trình thường chỉ cần một vài component. Ví dụ, `record Point(int x, int y)` có hai component `x` và `y`, nhưng một phép xử lý có thể chỉ cần `x`. Từ **Java 22**, ta có thể đặt **unnamed pattern** `_` (dấu gạch dưới) tại vị trí component không cần dùng. Mẫu vẫn nhận diện cấu trúc record, nhưng không tạo biến để truy cập giá trị bị bỏ qua.

## 1. Vì sao cần bỏ qua component?

Giả sử có record:

```java
record OrderLine(String productCode, int quantity, String warehouse) {}
```

Khi muốn lấy số lượng mà không dùng mã sản phẩm và kho, cách viết thông thường trong Java 21 là:

```java
// Trích đoạn minh họa; 'value' là một biến Object đã được khai báo.
if (value instanceof OrderLine(var unusedCode, var quantity, var unusedWarehouse)) {
    System.out.println(quantity);
}
```

Hai tên `unusedCode` và `unusedWarehouse` vẫn được tạo ra dù không được dùng. Với Java 22 trở lên, ta biểu đạt ý định trực tiếp hơn:

```java
// Trích đoạn minh họa; yêu cầu Java 22+.
if (value instanceof OrderLine(_, var quantity, _)) {
    System.out.println(quantity);
}
```

Đọc mẫu `OrderLine(_, var quantity, _)` từ trái sang phải:

| Vị trí | Component của record | Component pattern | Ý nghĩa |
| --- | --- | --- | --- |
| 1 | `productCode` (`String`) | `_` | Chấp nhận giá trị ở vị trí này, không tạo biến |
| 2 | `quantity` (`int`) | `var quantity` | Trích giá trị vào biến `quantity` |
| 3 | `warehouse` (`String`) | `_` | Chấp nhận giá trị ở vị trí này, không tạo biến |

Điểm mấu chốt: **bỏ qua giá trị không có nghĩa là bỏ vị trí component trong cú pháp**. Record có ba component thì record pattern phải có đúng ba component pattern, kể cả khi cả ba đều là `_`.

## 2. Phiên bản Java và cú pháp

| Phiên bản | Record patterns | `_` để bỏ qua component |
| --- | --- | --- |
| Java 17 | Chưa có record patterns theo cú pháp hoàn thiện | Không dùng được |
| Java 21 | Tính năng chính thức, không cần preview | Có dưới dạng preview của JEP 443; cần bật preview khi biên dịch và chạy |
| Java 22 trở lên | Tính năng chính thức | Tính năng chính thức theo JEP 456; không cần bật preview |

Các ví dụ hoàn chỉnh trong bài dùng **JDK 22+**. Với đúng **JDK 21**, nếu muốn dùng `_` trong record pattern thì cần biên dịch bằng `javac --enable-preview --release 21` và chạy bằng `java --enable-preview`. Nếu dự án dùng Java 21 mà không bật preview, hãy dùng các biến có tên như `var unusedY`. Không thể dùng `_` như một tên biến thông thường để thay thế trên Java 17/21.

## 3. Quy tắc của unnamed pattern `_`

- `_` trong danh sách component của record pattern **khớp với mọi giá trị** ở vị trí đó, kể cả `null`, và **không khai báo biến**. Có thể dùng nhiều dấu `_` trong cùng một pattern.
- Phải giữ đủ số vị trí và đúng thứ tự của các component trong khai báo `record`. Ví dụ `Point(var x, _)` hợp lệ với `record Point(int x, int y)`, còn `Point(var x)` không hợp lệ.
- Có thể phối hợp `_` với `var name`, kiểu tường minh như `int x` hoặc record pattern lồng nhau, chẳng hạn `Point(var x, _)` bên trong một record khác.
- `_` chỉ là **một component pattern** trong trường hợp này. Không được thay cả top-level pattern bằng `if (obj instanceof _)`. Nếu muốn kiểm tra kiểu của giá trị ngoài cùng, vẫn cần record/type pattern thích hợp.
- Không thể đọc lại giá trị đã bỏ qua: `System.out.println(_)` không hợp lệ. Khi cần sử dụng hoặc kiểm tra giá trị đó về sau, hãy đặt tên cho biến ngay từ pattern.

Ví dụ vị trí lồng nhau:

```java
record Point(int x, int y) {}
record TaggedPoint(String label, Point point, String tag) {}

// Trích đoạn minh họa: bỏ qua label, y và tag; chỉ giữ x.
if (obj instanceof TaggedPoint(_, Point(var x, _), _)) {
    System.out.println(x);
}
```

`TaggedPoint` có ba component, còn `Point` có hai. Mẫu bên ngoài sử dụng đúng ba vị trí; mẫu `Point(var x, _)` bên trong sử dụng đúng hai. Không có phép “bỏ phần đuôi” ngầm định như ở một số ngôn ngữ khác.

## 4. Ví dụ hoàn chỉnh: đọc một component, bỏ qua các component còn lại

Lưu đoạn sau vào tệp **`IgnoreRecordComponentsDemo.java`**:

```java
public class IgnoreRecordComponentsDemo {
    record Point(int x, int y) {}
    record NamedPoint(String name, Point point, String tag) {}

    static String describe(Object input) {
        return switch (input) {
            case NamedPoint(_, Point(var x, _), _) -> "x = " + x;
            case NamedPoint(_, _, _) -> "point = null";
            case null -> "input = null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
            new NamedPoint("A", new Point(3, 9), "red")));
        System.out.println(describe(
            new NamedPoint("B", null, null)));
        System.out.println(describe(null));
        System.out.println(describe("abc"));
    }
}
```

Dùng **JDK 22 trở lên**:

```bash
javac IgnoreRecordComponentsDemo.java
java IgnoreRecordComponentsDemo
```

Kết quả chuẩn:

```text
x = 3
point = null
input = null
other
```

Giải thích từng nhánh:

1. `case NamedPoint(_, Point(var x, _), _)` chỉ khớp khi `input` là một `NamedPoint` và component `point` chứa một `Point` khác `null`. Nó bỏ qua `name`, `tag` và `y`, nhưng lấy `x = 3`.
2. `case NamedPoint(_, _, _)` nhận một `NamedPoint` chưa khớp nhánh trước. Trong ví dụ này, `point` có kiểu khai báo `Point` nên trường hợp còn lại là `point == null`. Hai dấu `_` khác vẫn chấp nhận giá trị `null`.
3. `case null` xử lý chính đối tượng `input` bằng `null`. `_` ở component không có tác dụng làm cho một record pattern bên ngoài khớp với đối tượng `null`.
4. `default` xử lý giá trị không thuộc kiểu `NamedPoint`, ví dụ chuỗi `"abc"`.

Với dữ liệu thực tế, thông điệp `"point = null"` ở nhánh thứ hai chỉ phù hợp khi ta biết rằng kiểu khai báo của component là `Point` và nhánh thứ nhất đã bao phủ mọi `Point` khác `null`.

## 5. Phân biệt “bỏ qua” và “kiểm tra điều kiện”

Giả sử `record Parcel(String id, Object payload) {}`. Hai pattern sau **không có cùng ý nghĩa**:

```java
// Đoạn minh họa dùng trong 'instanceof' hoặc nhánh 'case'.
Parcel(var id, _)          // payload bất kỳ, kể cả null
Parcel(var id, String _)   // payload phải khớp type pattern String
```

Mẫu thứ nhất bỏ qua hoàn toàn giá trị của `payload`. Mẫu thứ hai không đặt tên cho `payload` nhưng vẫn yêu cầu đối tượng này khớp kiểu `String`; với component khai báo là `Object`, một `Integer` hoặc `null` sẽ không khớp nhánh thứ hai.

Tương tự, nếu nghiệp vụ cần xác nhận `quantity > 0` thì **không** thể thay `var quantity` bằng `_` rồi dùng `quantity` trong điều kiện. Hãy trích đúng biến cần kiểm tra:

```java
// Trích đoạn minh họa; 'value' đã được khai báo.
if (value instanceof OrderLine(_, var quantity, _) && quantity > 0) {
    System.out.println("Valid quantity: " + quantity);
}
```

Trong `switch`, có thể kiểm tra biến đã trích qua `when`, chẳng hạn `case Point(var x, _) when x >= 0 -> ...`. Ngược lại, một component chỉ dùng `_` không cung cấp tên để tham chiếu trong guard hoặc thân nhánh.

## 6. `null`, kiểm tra kiểu và việc thực thi accessor

Cần phân biệt hai cấp độ khớp:

- **Đối tượng bên ngoài:** `null instanceof Point(var x, _)` là `false`, vì bản thân giá trị đầu vào không phải đối tượng `Point`. Với `switch` xử lý `null`, dùng `case null` khi phù hợp.
- **Component bên trong:** nếu đầu vào là một record không `null`, `_` chấp nhận cả component chứa `null`. Tuy nhiên, record pattern lồng nhau như `Point(var x, _)` vẫn cần component đó thực sự là một đối tượng `Point` để tiếp tục phân rã.

Bỏ qua bằng `_` nghĩa là **không tạo ràng buộc tên** cho component, chứ không làm component biến mất khỏi record hay thay đổi kết cấu của nó. Quá trình record-pattern matching vẫn tuân theo ngữ nghĩa truy cập các component và kiểm tra khớp; không nên dựa vào `_` để bảo đảm rằng accessor của component sẽ không được gọi hoặc để tối ưu hiệu năng.

## 7. Lỗi thường gặp

| Cách viết | Vấn đề | Cách sửa |
| --- | --- | --- |
| `Point(var x)` với `record Point(int x, int y)` | Thiếu một vị trí component | `Point(var x, _)` |
| `if (obj instanceof _)` | `_` không hợp lệ ở top-level pattern | Dùng `obj instanceof Point(_, _)` hoặc một type pattern thích hợp |
| `Point(var x, _)` rồi truy cập `_` trong thân `if` | Không có biến tên `_` để tham chiếu | Dùng `Point(var x, var y)` nếu cần `y` |
| Biên dịch mã dùng `_` bằng Java 21 không bật preview | Java 21 chỉ hỗ trợ tính năng này ở chế độ preview | Bật preview trên đúng JDK 21 hoặc dùng JDK 22+ |
| Dùng `_` để bỏ qua cả một cấp record lồng nhau dù cần kiểm tra kiểu/giá trị bên trong | Không thực hiện kiểm tra bên trong cấp đó | Viết pattern lồng nhau, ví dụ `Point(_, var y)` |
| Cho rằng `_` chỉ khớp khi component khác `null` | Hiểu sai tính chất null-matching | Nếu cần kiểm tra kiểu/khác `null`, dùng pattern và điều kiện phù hợp |

Đừng tự thêm những tên `ignored1`, `ignored2` chỉ để né số lượng component khi dự án hỗ trợ Java 22+: các dấu `_` khiến người đọc thấy rõ component nào không tham gia tính toán. Tuy nhiên, đặt tên cho biến vẫn đúng khi giá trị đó thực sự được dùng để tạo kết quả hoặc xác thực dữ liệu.

## 8. Tự luyện tập

Cho hai record sau:

```java
record Payment(String id, long amount, String currency, boolean refunded) {}
record Wrapper(String label, Payment payment) {}
```

**Bài 1.** Viết record pattern lấy `amount` từ `Payment`, bỏ qua `id`, `currency` và `refunded`.

**Đáp án:** `Payment(_, var amount, _, _)`.

**Bài 2.** Viết record pattern cho `Wrapper`, bỏ qua `label` và toàn bộ các component của `Payment` trừ `amount`.

**Đáp án:** `Wrapper(_, Payment(_, var amount, _, _))`. Mẫu chỉ khớp khi `payment` khác `null` và có kiểu `Payment`.

**Bài 3.** Có thể thay `Payment(_, var amount, _, _)` bằng `Payment(_, var amount)` để rút ngắn hay không?

**Đáp án:** Không. `Payment` có bốn component nên record pattern cũng phải cung cấp đúng bốn component pattern.

## 9. Ghi nhớ và tài liệu tra cứu

- Muốn bỏ qua một component trong record pattern trên **Java 22+**, viết `_` tại **đúng vị trí** component đó.
- Muốn sử dụng component, đặt tên bằng `var name` hoặc một type pattern phù hợp.
- `_` khớp cả `null` ở cấp component và không khai báo biến; nó không làm thay đổi số lượng component, không thay cho top-level pattern, không phải kỹ thuật bỏ qua việc truy cập accessor.
- Java 21 đã hỗ trợ record patterns ổn định nhưng `_` chỉ là preview; hãy chọn cú pháp theo phiên bản JDK và cấu hình biên dịch của dự án.

Tài liệu chuẩn:
- [Oracle — Record Patterns (Java 21)](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle — Unnamed Patterns and Variables (Java 21, preview)](https://docs.oracle.com/en/java/javase/21/language/unnamed-variables-and-patterns.html).
- [Oracle — Java SE 22 Language Changes](https://docs.oracle.com/en/java/javase/22/language/java-language-changes.html).
- [Java Language Specification — Unnamed Variables and Patterns (Java 22)](https://docs.oracle.com/en/java/javase/22/docs/specs/unnamed-jls.html).