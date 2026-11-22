# So sánh deconstruction với mapping thủ công trong Java

## 1. Phân biệt hai khái niệm trước khi so sánh

Trong Java, **deconstruction bằng record pattern** là thao tác kiểm tra một giá trị có khớp một `record` hay không, rồi **tách các record components thành biến cục bộ**. Ví dụ: `Order(var id, Money(var cents, var currency))` kiểm tra cả `Order` và `Money` lồng nhau, đồng thời lấy `id`, `cents` và `currency`.

**Mapping thủ công** là việc lập trình viên tự truy cập dữ liệu nguồn, kiểm tra điều kiện và **chuyển thành biểu diễn đích**, chẳng hạn `OrderRow` dùng để xuất báo cáo hoặc trả về API. Khi nguồn là record, cách thủ công thường gọi các accessor như `order.total()`, `total.currency()`; nếu cần DTO, lập trình viên còn tự gọi constructor hoặc builder của đối tượng đích.

Hai thao tác không hoàn toàn thay thế nhau:

- Deconstruction **tách dữ liệu** từ record; nó **không tự tạo** DTO mới, không tự đổi tên hay chuyển đổi định dạng các trường.
- Mapping **tạo biểu diễn đích**; việc lấy dữ liệu nguồn có thể thực hiện **bằng accessor thủ công hoặc bằng deconstruction**.
- Vì vậy, cách so sánh sát thực tế là **“tự truy cập các thành phần rồi mapping”** với **“dùng record pattern để lấy các thành phần rồi mapping”**.

Record patterns được chuẩn hóa trong **Java 21** (JEP 440). Ví dụ bên dưới yêu cầu **JDK 21+**, không dùng `--enable-preview`. Java 17 có `record` nhưng chưa hỗ trợ cú pháp record pattern.

## 2. Cùng một yêu cầu nghiệp vụ

Giả sử dữ liệu nguồn gồm đơn hàng và số tiền, còn dữ liệu đích là một hàng báo cáo phẳng:

```java
record Money(long cents, String currency) {}
record Order(String id, Money total) {}
record OrderRow(String id, String currency, long cents) {}
```

Cần đổi một giá trị đầu vào kiểu `Object` thành `OrderRow` khi:

1. Đầu vào thực sự là `Order`.
2. `Order.total` không phải `null`.
3. `Money.currency` không phải `null`.

Nếu một trong ba điều kiện không đạt, phép mapping trả về `null` theo **quy ước của ví dụ**. Trong ứng dụng thật có thể chọn `Optional<OrderRow>`, đối tượng lỗi hoặc ngoại lệ tùy hợp đồng API.

Đầu ra hợp lệ, ví dụ với `new Order("O-17", new Money(1299, "USD"))`, là:

```text
OrderRow[id=O-17, currency=USD, cents=1299]
```

Ở đây `cents` là đơn vị nhỏ nhất của USD: `1299` tương đương 12,99 USD. Bài này giữ nguyên số nguyên để tập trung vào cách lấy dữ liệu và mapping.

## 3. Cách A — mapping thủ công bằng accessor

Sau khi kiểm tra kiểu `Order`, ta lần lượt lấy từng thành phần và tự kiểm tra `null`:

```java
static OrderRow manual(Object source) {
    if (!(source instanceof Order order)) return null;

    Money total = order.total();
    if (total == null) return null;

    String currency = total.currency();
    if (currency == null) return null;

    return new OrderRow(order.id(), currency, total.cents());
}
```

**Diễn giải:**

- `source instanceof Order order` là **type pattern**, giúp kiểm tra và lấy **toàn bộ đối tượng** `Order`. Đây chưa phải record deconstruction.
- `order.total()` lấy component `total`; phải kiểm tra `null` trước khi gọi `total.currency()` hoặc `total.cents()`.
- `new OrderRow(...)` mới là bước **mapping sang đối tượng đích**; trong ví dụ, trường `currency` được đưa lên cùng cấp với `id` và `cents`.
- Mỗi nhánh kiểm tra đều tường minh, nên có thể dễ dàng thêm thông báo lỗi riêng cho “thiếu total” hoặc “thiếu currency”.

Đây là cách dễ kiểm soát các bước xử lý trung gian, nhưng khi cấu trúc dữ liệu lồng nhiều tầng, code có thể dài vì phải gọi nhiều accessor và kiểm tra `null` lặp lại.

## 4. Cách B — deconstruction trước, mapping sau

Record pattern tách hai tầng dữ liệu ngay trong `instanceof`:

```java
static OrderRow deconstructAndMap(Object source) {
    if (source instanceof Order(var id, Money(var cents, var currency))
            && currency != null) {
        return new OrderRow(id, currency, cents);
    }
    return null;
}
```

**Diễn giải từng phần:**

- `Order(...)` yêu cầu giá trị nguồn khớp record `Order` và truy xuất hai component theo **thứ tự khai báo**: `id` rồi `total`.
- `var id` nhận component `id`; `Money(var cents, var currency)` yêu cầu component `total` khớp record `Money` và tách tiếp `cents`, `currency`.
- `var` suy luận từ kiểu tĩnh của component: `id` và `currency` là `String`, `cents` là `long`. Đây không phải biến kiểu động.
- Nếu `source` là `null`, không phải `Order`, hoặc `total` là `null`, biểu thức record pattern không khớp và `instanceof` trả về `false`.
- Một component kiểu tham chiếu được bắt bằng `var` **có thể là `null`**. Vì vậy, điều kiện `&& currency != null` vẫn cần thiết; deconstruction **không tự xác thực** tất cả giá trị.
- Các biến `id`, `cents` và `currency` chỉ tồn tại tại những vị trí trình biên dịch xác định pattern đã khớp; chúng hợp lệ ở vế phải `&&` và trong nhánh `if` tương ứng.
- `new OrderRow(id, currency, cents)` **vẫn là bước mapping thủ công**. Record pattern không tự tạo hàng báo cáo.

Như vậy, hai phương thức trên có cùng **hợp đồng kết quả** trong các trường hợp bình thường của mô hình này. Chúng có cú pháp, chiến lược kiểm tra và khả năng gắn thông báo lỗi khác nhau.

## 5. Chương trình hoàn chỉnh chạy được

Tạo file **`DeconstructionVsMappingDemo.java`** với toàn bộ nội dung:

```java
public class DeconstructionVsMappingDemo {
    record Money(long cents, String currency) {}
    record Order(String id, Money total) {}
    record OrderRow(String id, String currency, long cents) {}

    static OrderRow manual(Object source) {
        if (!(source instanceof Order order)) return null;

        Money total = order.total();
        if (total == null) return null;

        String currency = total.currency();
        if (currency == null) return null;

        return new OrderRow(order.id(), currency, total.cents());
    }

    static OrderRow deconstructAndMap(Object source) {
        if (source instanceof Order(var id, Money(var cents, var currency))
                && currency != null) {
            return new OrderRow(id, currency, cents);
        }
        return null;
    }

    static void verify(String label, Object source) {
        OrderRow first = manual(source);
        OrderRow second = deconstructAndMap(source);

        if (!java.util.Objects.equals(first, second)) {
            throw new AssertionError(label + ": " + first + " != " + second);
        }
        System.out.println(label + " -> " + second);
    }

    public static void main(String[] args) {
        verify("valid", new Order("O-17", new Money(1299, "USD")));
        verify("missing-total", new Order("O-18", null));
        verify("missing-currency", new Order("O-19", new Money(2000, null)));
        verify("wrong-type", "not an order");
        verify("null-input", null);
        System.out.println("5 cases passed");
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac --release 21 DeconstructionVsMappingDemo.java
java DeconstructionVsMappingDemo
```

**Stdout chính xác:**

```text
valid -> OrderRow[id=O-17, currency=USD, cents=1299]
missing-total -> null
missing-currency -> null
wrong-type -> null
null-input -> null
5 cases passed
```

Hàm `verify` so sánh kết quả bằng `Objects.equals`. Vì `OrderRow` là record, hai giá trị record được so sánh theo các component qua `equals` tự sinh. Nếu hai cách tạo ra kết quả khác nhau, chương trình ném `AssertionError`. Kết quả nêu trên đã được kiểm tra với JDK 24, dùng cú pháp của Java 21.

**Điều các ca kiểm thử chứng minh:**

| Dữ liệu đầu vào | Mapping accessor | Deconstruction + mapping | Lý do |
| --- | --- | --- | --- |
| `Order` và `Money` hợp lệ, có currency | Tạo `OrderRow` | Tạo `OrderRow` bằng các biến tách ra | Đủ điều kiện |
| `Order.total == null` | Dừng ở kiểm tra `total` | `Money(...)` không khớp | Cả hai trả `null` |
| `Money.currency == null` | Dừng ở kiểm tra `currency` | Pattern vẫn có thể tách `currency` nhưng điều kiện `&&` thất bại | Cả hai trả `null` |
| Không phải `Order` | Type pattern không khớp | Record pattern ngoài không khớp | Cả hai trả `null` |
| Nguồn bằng `null` | Type pattern không khớp | Record pattern không khớp | Cả hai trả `null` |

## 6. So sánh theo tiêu chí thiết kế

| Tiêu chí | Accessor + mapping thủ công | Deconstruction + mapping |
| --- | --- | --- |
| Kiểm tra kiểu nguồn | Dùng `instanceof Order order` hoặc kiểm tra/ép kiểu rõ ràng | Dùng `instanceof Order(...)` |
| Lấy component | Gọi từng accessor như `order.id()`, `order.total()` | Khai báo pattern con theo cấu trúc `record` |
| Dữ liệu lồng | Tự lấy từng object ở mỗi tầng | Tách nhiều tầng bằng `Order(..., Money(...))` |
| Kiểm tra `null` | Viết các điều kiện ở từng tầng | Record pattern lồng không khớp `null`; component bắt bằng `var` vẫn cần guard nếu phải khác `null` |
| Tạo DTO/record đích | Viết `new`, builder hoặc phương thức mapping | **Vẫn phải viết** `new`, builder hoặc mapping; deconstruction chỉ thay phần lấy dữ liệu |
| Chuyển kiểu/format/tính toán | Viết logic chuyển đổi | Viết logic chuyển đổi sau khi tách biến |
| Phạm vi biến | Biến tạm thông thường hoặc biến type pattern | Pattern variable tuân theo **flow scoping** |
| Phản hồi lỗi cụ thể | Các bước `if` riêng có thể chỉ ra nguyên nhân | Pattern lồng thường chỉ cho biết “khớp/không khớp”; cần kiểm tra thêm để phân loại lỗi |
| Điều kiện về kiểu nguồn | Có thể đọc từ record, class thường, JavaBean, `Map`, API khác | Record pattern `R(...)` chỉ deconstruct **record** tương ứng |
| Tính dễ đọc | Tốt với logic chuyển đổi dài, nhiều nhánh | Gọn với record lồng và logic điều kiện ngắn |
| Hiệu năng | Phụ thuộc mã gọi accessor, kiểm tra, cấp phát đích | Vẫn truy xuất component và cấp phát DTO nếu có `new`; cần đo thực tế, không mặc định nhanh hơn |

**Không nên chọn chỉ dựa vào số dòng code.** Khi mapping chỉ chuyển vài component record và xử lý trường hợp không khớp đơn giản, record pattern thường dễ đọc. Khi quy trình cần nhiều phép biến đổi, kiểm tra từng lỗi, giữ giá trị trung gian hoặc lấy dữ liệu từ class không phải record, accessor thủ công hoặc mapper chuyên dụng có thể rõ ràng hơn.

## 7. Những khác biệt dễ gây lỗi

### 7.1. Deconstruction không tự tạo đối tượng mới

Biểu thức sau chỉ lấy dữ liệu và sử dụng trực tiếp:

```java
if (source instanceof Order(var id, Money(var cents, var currency))) {
    System.out.println(id + " " + cents + " " + currency);
}
```

Nó **không tạo** `OrderRow`. Ngược lại, đoạn `return new OrderRow(id, currency, cents);` là thao tác mapping và có thể xuất hiện trong cả hai cách tiếp cận.

### 7.2. `var` và `null` không phải “null validation” tự động

`Order(var id, Money(var cents, var currency))` yêu cầu component `total` phải là một `Money` khác `null`, nhưng `currency` được lấy bằng `var` nên có thể là `null`. Nếu thay toàn bộ pattern con bằng:

```java
if (source instanceof Order(var id, var total)) {
    // total có thể là null vì pattern này không đòi hỏi Money(...).
}
```

thì một `Order` có `total == null` vẫn có thể khớp. Vì vậy, cần đặt chính xác yêu cầu dữ liệu ở từng tầng. Mapping thủ công cũng phải xác định các quy tắc `null` chứ không thể dựa vào bản thân accessor để xác thực.

### 7.3. Record pattern phụ thuộc khai báo component, không phải getter tùy ý

Record pattern tuân theo **số lượng, thứ tự và kiểu component** của `record`. Chẳng hạn `Money(var cents, var currency)` lấy `cents` trước `currency` theo khai báo. Nếu đảo tên biến mà kiểu vẫn tương thích, code có thể biên dịch nhưng gán sai ý nghĩa nghiệp vụ ở các record có nhiều component cùng kiểu. Khi thay đổi thứ tự component, phải kiểm tra lại các pattern liên quan.

Với một class thông thường có `getTotal()`, không thể tự viết `OrderLike(var id, var total)` nếu `OrderLike` không phải record. Mapping qua accessor vẫn hoạt động với class thông thường và các nguồn dữ liệu không có cấu trúc record.

### 7.4. Scope của biến pattern khác biến cục bộ thông thường

Code đúng:

```java
if (source instanceof Order(var id, Money(var cents, var currency))
        && currency != null) {
    System.out.println(id + ": " + cents);
}
```

Code không hợp lệ:

```java
// Sai: vế phải || có thể chạy khi record pattern chưa khớp.
if (source instanceof Order(var id, Money(var cents, var currency))
        || cents > 0) {
    System.out.println("checking");
}
```

Không thể dùng `cents` trên đường đi mà pattern có thể thất bại. Khi dùng accessor thủ công, cũng cần tôn trọng scope của biến được khai báo trong từng nhánh.

### 7.5. Deconstruction không làm sâu bản sao dữ liệu

Record là biểu diễn dữ liệu với component final, nhưng component có thể chứa tham chiếu đến đối tượng mutable, chẳng hạn `List`. Cả lấy component bằng accessor lẫn deconstruction đều không tự động tạo **deep copy**. Nếu DTO đích phải tách biệt khỏi dữ liệu nguồn, bước mapping phải chủ động sao chép các cấu trúc mutable cần thiết.

### 7.6. Accessor tự định nghĩa có thể ảnh hưởng hành vi

Record pattern lấy giá trị component thông qua accessor của record. Khi accessor do lập trình viên tự định nghĩa có thể ném ngoại lệ, việc khớp record pattern có thể ném `MatchException` với nguyên nhân từ accessor. Khi gọi accessor trực tiếp trong mapping thủ công, cách ngoại lệ được truyền ra có thể khác. Do đó không nên khẳng định hai đoạn code **luôn tương đương tuyệt đối** khi record có accessor bất thường hoặc có side effects. Ví dụ chạy ở mục 5 dùng accessor mặc định, không có các hành vi này.

## 8. Khi nào kết hợp cả hai?

Trong code thực tế, một lựa chọn cân bằng là dùng deconstruction để lấy dữ liệu và giữ mapping trong một hàm chuyên trách:

```java
static OrderRow toRow(Object source) {
    if (!(source instanceof Order(var id, Money(var cents, var currency)))) {
        return null;
    }
    if (currency == null) {
        return null;
    }
    return new OrderRow(id, currency, cents);
}
```

Đoạn này là một **phương thức minh họa** dùng cùng ba record đã khai báo ở mục 2, không phải file Java độc lập. Nhánh `if` thất bại trả về ngay, vì thế các biến `id`, `cents`, `currency` vẫn có thể dùng sau `if` theo quy tắc flow scoping của Java.

Nếu bước mapping phát triển thêm yêu cầu chuyển đổi tiền tệ, thay đổi tên trường, quy tắc xác thực, tạo thông báo lỗi cụ thể hoặc lấy dữ liệu từ nhiều nguồn, hãy tách trách nhiệm thành các phương thức chuyển đổi nhỏ để dễ kiểm thử. Record pattern vẫn hữu ích ở phần bóc tách cấu trúc, nhưng **mapping nghiệp vụ** cần được mô tả và kiểm thử riêng.

## 9. Bài tập tự luyện và tiêu chí đánh giá

Cho:

```java
record Address(String city, String street) {}
record Customer(String name, Address address) {}
record CustomerRow(String name, String city) {}
```

Yêu cầu: từ `Object input`, tạo `CustomerRow` nếu `input` là `Customer`, `address` khác `null` và `city` không rỗng; các trường hợp khác trả `null`.

Hãy viết hai phương thức: (a) dùng accessor thủ công; (b) dùng `Customer(var name, Address(var city, var street))`, sau đó gọi constructor đích. Đảm bảo cùng xử lý các ca: địa chỉ hợp lệ; địa chỉ `null`; thành phố `null`; thành phố chuỗi rỗng; đầu vào sai kiểu.

**Gợi ý điều kiện đúng:** `city != null && !city.isEmpty()`. Nếu ứng dụng yêu cầu loại bỏ khoảng trắng thì cân nhắc `city.isBlank()` (Java 11+) theo hợp đồng dữ liệu; đây là quy tắc nghiệp vụ **bổ sung**, không do record pattern tự áp dụng.

## 10. Ghi nhớ

**Record pattern deconstruction** giúp nhận diện và tách thành phần record, nhất là record lồng; **mapping** quyết định mô hình đích và cách chuyển đổi dữ liệu. Khi cần cả hai, dùng deconstruction để giảm thao tác accessor và tiếp tục tự tạo DTO theo quy tắc nghiệp vụ. Đánh giá sự tương đương bằng các test có dữ liệu đúng, `null`, sai kiểu và tình huống biên, thay vì chỉ nhìn cách viết gọn hơn.

**Tài liệu chính thức:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440); [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html); [Java `Record` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html).
