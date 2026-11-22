# Đánh giá tính dễ đọc của pattern composition trong Java (Java 21+)

## 1. Tại sao cần đánh giá tính dễ đọc?

**Pattern composition** là cách kết hợp nhiều pattern để nhận diện kiểu và cấu trúc dữ liệu, tách thành phần của `record`, sau đó chọn cách xử lý. Trong Java 21+, composition thường xuất hiện dưới dạng **nested record patterns**, **type patterns**, **`instanceof` kết hợp điều kiện**, và **pattern matching cho `switch` với `when`**.

Ví dụ, cùng một đối tượng `Shipment` có thể được kiểm tra qua nhiều tầng:

```java
case Shipment(
        var id,
        Customer(var name, var vip),
        Address(var city, Point(var x, var y)),
        var parcels) when vip && parcels > 0 && x >= 0 && y >= 0 ->
    ...
```

Cú pháp này súc tích vì diễn tả một lần cả **hình dạng** dữ liệu và các giá trị cần dùng. Tuy nhiên, càng lồng sâu, càng nhiều biến và điều kiện, người đọc càng khó nhận biết **nhánh nào khớp**, **vì sao khớp**, **null ở tầng nào làm thất bại**, và **sửa một quy tắc cần thay đổi ở đâu**.

Bài học tập trung vào **đánh giá khả năng đọc, hiểu và bảo trì** của pattern composition. Mục tiêu không phải cố làm mã ngắn nhất; mục tiêu là để người khác dễ trả lời ba câu hỏi:

1. **Đang nhận dạng dữ liệu gì?** Kiểu ngoài cùng, các record con và các thành phần cần thiết.
2. **Nhánh xử lý có điều kiện gì?** Quy tắc cấu trúc, `null`, guard và độ ưu tiên.
3. **Nếu thêm một biến thể hoặc sửa quy tắc, cần thay đổi chỗ nào?** Khả năng bảo trì và kiểm thử.

**Phiên bản:** `record` là tính năng chính thức từ Java 16. **Record Patterns (JEP 440)** và **Pattern Matching for `switch` (JEP 441)** trở thành tính năng chính thức ở **Java 21**. Các ví dụ đầy đủ trong bài dùng **JDK 21+**, không cần `--enable-preview`.

## 2. Nhận diện các dạng composition trước khi đánh giá

### 2.1. Type pattern: chỉ quan tâm kiểu

```java
case Shipment s -> "Lô hàng " + s.id()
```

Mẫu này nhận một đối tượng `Shipment` không-null, giữ nguyên đối tượng trong biến `s`. Nó thường dễ đọc khi xử lý nhiều thuộc tính trong phương thức khác hoặc khi chỉ cần một accessor.

### 2.2. Record pattern: tách component trực tiếp

```java
case Point(var x, var y) -> "Điểm (" + x + ", " + y + ")"
```

Với `record Point(int x, int y) {}`, mẫu này vừa nhận `Point`, vừa tách hai thành phần theo thứ tự khai báo. `x` và `y` được suy luận là `int`. Dạng này tốt khi thật sự cần hai giá trị trong nhánh.

### 2.3. Nested record pattern: kiểm tra nhiều tầng

```java
case Address(var city, Point(var x, var y)) ->
    city + ": " + x + ", " + y
```

Với `record Address(String city, Point location) {}`, mẫu kiểm tra `Address` ở ngoài và `Point` trong component `location`. **Mỗi dấu `Type(` bắt đầu một tầng kiểm tra mới**; các `var` là điểm dừng tách, gán nguyên component vào biến.

### 2.4. Guard: bổ sung quy tắc giá trị

```java
case Point(var x, var y) when x >= 0 && y >= 0 ->
    "Hai tọa độ không âm"
```

`when` chỉ được xét sau khi pattern của `case` đã khớp; khi guard sai, `switch` xét nhánh tiếp theo. Guard phù hợp với điều kiện ngắn có ý nghĩa rõ ràng. Điều kiện nghiệp vụ dài có thể khiến người đọc phải rời mắt qua nhiều cặp ngoặc và phép toán.

### 2.5. Kết hợp `instanceof` với `&&`

```java
if (value instanceof Point(var x, var y)
        && x >= 0
        && y >= 0) {
    System.out.println("Điểm hợp lệ");
}
```

Đây là một tổ hợp dễ đọc khi chỉ có một câu hỏi Boolean. `&&` đánh giá ngắn mạch: các biến `x`, `y` chỉ được dùng ở vế phải khi pattern đã khớp. Không thay bằng `||` rồi kỳ vọng các biến vẫn có mặt: phía phải `||` có thể được xét khi pattern không khớp.

## 3. Bộ tiêu chí để đánh giá một pattern có dễ đọc không

Không có một chỉ số duy nhất cho mọi codebase. Khi review, kiểm tra các tiêu chí sau và giải thích bằng tình huống cụ thể:

| Tiêu chí | Dấu hiệu dễ đọc | Dấu hiệu cần xem lại |
| --- | --- | --- |
| **Ý định** | Người đọc nhìn thấy ngay dữ liệu cần nhận và hành động tương ứng | Phải đọc toàn bộ cây record mới đoán được tên quy tắc nghiệp vụ |
| **Độ sâu** | Chỉ tách đến tầng thật sự cần | Tách qua nhiều record con chỉ để dùng một giá trị hoặc kiểm tra một cờ |
| **Số biến** | Biến được đặt tên theo ý nghĩa và đa số có tác dụng trong nhánh | Nhiều `var a, var b, var c`; nhiều biến được khai báo nhưng không sử dụng |
| **Guard** | Một vài điều kiện rõ ràng, null-safe, dễ kiểm tra | Chuỗi `&&`/`||` dài, nhiều phủ định, điều kiện phụ thuộc thứ tự khó thấy |
| **Null và lỗi dữ liệu** | Biết tầng nào có thể null và nhánh dự phòng nào nhận nó | Nhầm `Record(...)` với `var component`; guard có thể gọi phương thức trên null |
| **Thứ tự `case`** | Nhánh cụ thể/guard đặt trước nhánh tổng quát | Nhánh tổng quát che nhánh sau hoặc người đọc khó biết ưu tiên |
| **Phạm vi và tên biến** | Dễ tìm chỗ biến được tách, dùng trong `when`/thân nhánh | Dùng lại tên mơ hồ, phải lần theo nhiều dấu ngoặc |
| **Khả năng thay đổi** | Đổi một quy tắc có một vị trí rõ ràng để sửa và test | Cùng điều kiện xuất hiện ở nhiều `case`, dễ sửa thiếu |
| **Kiểm thử** | Liệt kê được input, case phù hợp, guard và output | Không thể giải thích nhánh dự phòng hoặc các trường hợp biên |

Có thể dùng **câu hỏi chẩn đoán**: “Một người mới nhìn đoạn code có phân biệt được **pattern không khớp** và **pattern khớp nhưng guard sai** trong khoảng một lượt đọc không?” Nếu khó, hãy giảm độ sâu, tách điều kiện, hoặc đặt tên cho quy tắc.

Các mốc như “hơn hai tầng lồng” hay “hơn ba nhóm điều kiện” chỉ là **tín hiệu nên cân nhắc refactor**, không phải luật ngôn ngữ hay ngưỡng đo chất lượng chính thức. Một nested pattern ba tầng rất quen thuộc đôi khi vẫn dễ đọc hơn hàng loạt accessor.

## 4. Ví dụ pattern composition rõ ràng, dù có lồng nhau

Giả sử:

```java
record Point(int x, int y) {}
record Rectangle(Point topLeft, Point bottomRight) {}
```

Khi nhiệm vụ là kiểm tra thứ tự tọa độ hai góc, một pattern hai tầng có thể rất tự nhiên:

```java
case Rectangle(
        Point(var x1, var y1),
        Point(var x2, var y2))
        when x1 <= x2 && y1 <= y2 ->
    "Hai góc theo thứ tự hợp lệ"
```

Điểm mạnh:

- Cấu trúc `Rectangle(Point, Point)` thể hiện trực tiếp điều kiện cần hai điểm.
- Các biến `x1, y1, x2, y2` được dùng ngay trong guard; không có biến thừa.
- Guard chỉ kiểm tra **một ý tưởng**: góc đầu không nằm bên phải hoặc dưới góc cuối theo hệ tọa độ đang giả định.
- Người đọc có thể dự đoán điều gì xảy ra khi một `Point` là null: record pattern tại vị trí đó không khớp, nên nhánh này không chạy.

Đoạn trên là **nhãn `case` minh họa**, cần đặt bên trong `switch` phù hợp. Nó không quy định hệ tọa độ cho toàn ứng dụng; nếu trục `y` tăng theo hướng khác, quy tắc nghiệp vụ cần điều chỉnh.

Việc dùng nested pattern ở đây **không xấu chỉ vì có hai cặp record**. Cần xem xét độ sâu có phản ánh đúng thông tin nhánh sử dụng hay không.

## 5. Ví dụ khó đọc: trộn cấu trúc sâu với nhiều chính sách

Giả sử một lô hàng có:

```java
record Point(int x, int y) {}
record Address(String city, Point location) {}
record Customer(String name, boolean vip) {}
record Shipment(String id, Customer customer, Address address, int parcels) {}
```

Yêu cầu xử lý: ưu tiên khi lô hàng có mã không trống, khách hàng VIP có tên hợp lệ, thành phố không trống, tọa độ không âm và số kiện dương. Tất cả các lô hàng còn lại được xử lý ở nhánh thông thường.

Ta *có thể* viết mọi thứ trong một `case`:

```java
case Shipment(
        var id,
        Customer(var name, var vip),
        Address(var city, Point(var x, var y)),
        var parcels)
        when id != null && !id.isBlank()
            && name != null && !name.isBlank()
            && vip
            && city != null && !city.isBlank()
            && x >= 0 && y >= 0
            && parcels > 0 ->
    "Ưu tiên: " + id + " / " + name + " @ " + city;
```

Mã trên **hợp lệ** trong `switch` Java 21 và mô tả đúng điều kiện. Vấn đề về *tính dễ đọc* bắt đầu khi một reviewer phải giữ nhiều thông tin trong đầu cùng lúc:

1. Nhìn cây `Shipment → Customer/Address → Point` để biết khi nào pattern khớp.
2. Nhớ rằng `Customer(...)`, `Address(...)` và `Point(...)` đều cần component record tương ứng **không-null**.
3. Theo dõi các biến `id, name, vip, city, x, y, parcels` và kiểu của chúng.
4. Đọc guard dài gồm nhiều quy tắc: mã, tên, VIP, thành phố, tọa độ, số kiện.
5. Dự đoán nhánh tiếp theo nếu record thiếu, nếu chuỗi rỗng, hoặc nếu một điều kiện Boolean false.

Những quy tắc đó đều có ý nghĩa nghiệp vụ riêng. Khi thêm yêu cầu mới như “khách hàng VIP chỉ được ưu tiên ở một khu vực”, đoạn `case` dễ bị kéo dài thêm. Đây là thời điểm nên cân nhắc **đặt tên cho điều kiện** và giữ phần `switch` ở mức điều phối.

## 6. Hai cách viết cùng hành vi: ví dụ Java 21 chạy độc lập

Tạo tệp **`PatternReadabilityDemo.java`**:

```java
public class PatternReadabilityDemo {
    record Point(int x, int y) {}
    record Address(String city, Point location) {}
    record Customer(String name, boolean vip) {}
    record Shipment(String id, Customer customer,
                    Address address, int parcels) {}

    // Cách 1: trộn nested deconstruction và mọi guard vào một case.
    static String classifyDense(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case Shipment(
                    var id,
                    Customer(var name, var vip),
                    Address(var city, Point(var x, var y)),
                    var parcels)
                    when id != null && !id.isBlank()
                        && name != null && !name.isBlank()
                        && vip
                        && city != null && !city.isBlank()
                        && x >= 0 && y >= 0
                        && parcels > 0 ->
                "Ưu tiên: " + id + " / " + name + " @ " + city;

            case Shipment(var id, var customer,
                          var address, var parcels) ->
                "Thông thường: " + id;

            default -> "Không phải lô hàng";
        };
    }

    // Cách 2: mỗi helper thể hiện một quy tắc rõ ràng.
    static boolean isVipCustomer(Object value) {
        return value instanceof Customer(var name, var vip)
            && name != null
            && !name.isBlank()
            && vip;
    }

    static boolean isValidAddress(Object value) {
        return value instanceof Address(
                var city, Point(var x, var y))
            && city != null
            && !city.isBlank()
            && x >= 0 && y >= 0;
    }

    static boolean isPriority(Shipment shipment) {
        return shipment.id() != null
            && !shipment.id().isBlank()
            && shipment.parcels() > 0
            && isVipCustomer(shipment.customer())
            && isValidAddress(shipment.address());
    }

    static String classifyReadable(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case Shipment shipment when isPriority(shipment) ->
                "Ưu tiên: " + shipment.id()
                    + " / " + shipment.customer().name()
                    + " @ " + shipment.address().city();

            case Shipment shipment ->
                "Thông thường: " + shipment.id();

            default -> "Không phải lô hàng";
        };
    }

    // Đảm bảo hai cách phân loại cho cùng kết quả ở từng input.
    static void compare(Object value) {
        String dense = classifyDense(value);
        String readable = classifyReadable(value);

        if (!dense.equals(readable)) {
            throw new AssertionError(
                "Hai cách phân loại khác nhau: "
                    + dense + " <> " + readable);
        }
        System.out.println(readable);
    }

    public static void main(String[] args) {
        compare(new Shipment(
            "S-01",
            new Customer("An", true),
            new Address("Huế", new Point(1, 2)),
            3));

        compare(new Shipment(
            "S-02",
            new Customer("Bình", false),
            new Address("Huế", new Point(1, 2)),
            3));

        compare(new Shipment(
            "S-03",
            new Customer("Chi", true),
            new Address("Huế", null),
            1));

        compare(new Shipment(
            "S-04",
            null,
            new Address("Huế", new Point(1, 2)),
            1));

        compare(new Shipment(
            "S-05",
            new Customer("Dũng", true),
            new Address("", new Point(1, 2)),
            1));

        compare("abc");
        compare(null);
    }
}
```

Biên dịch bằng JDK 21 hoặc mới hơn tại thư mục chứa tệp:

```bash
javac --release 21 -encoding UTF-8 PatternReadabilityDemo.java
java PatternReadabilityDemo
```

Đầu ra:

```text
Ưu tiên: S-01 / An @ Huế
Thông thường: S-02
Thông thường: S-03
Thông thường: S-04
Thông thường: S-05
Không phải lô hàng
Không có dữ liệu
```

**Cả hai cách đều hợp lệ**, và trong ví dụ này cho cùng đầu ra trên từng input. Hàm `compare` kiểm tra sự tương đương thực tế trước khi in. Nó **không phải chứng minh hình thức cho mọi giá trị đầu vào**, nhưng là bước kiểm tra tốt khi refactor.

### Vì sao bản tách hàm có thể dễ đọc hơn?

Ở `classifyReadable`, phần `switch` chỉ trả lời “lô hàng ưu tiên, lô hàng thông thường hay dữ liệu không phù hợp?”. Điều kiện được đặt tên `isPriority`. Helper `isVipCustomer` làm rõ điều kiện về khách hàng, còn `isValidAddress` xử lý cấu trúc địa chỉ và vị trí. Reviewer có thể mở từng helper để xem chi tiết khi cần, đồng thời kiểm tra chúng độc lập.

Tuy vậy, **tách hàm không phải lúc nào cũng tốt hơn**. Nếu chỉ có một guard đơn giản như `x >= 0`, việc nhảy qua nhiều helper có thể làm mất tính trực tiếp. Ngược lại, nếu cùng tiêu chí VIP/địa chỉ được dùng ở nhiều nơi, đặt tên cho các quy tắc giúp tránh lặp và giảm nguy cơ sửa một chỗ, quên chỗ khác.

Hai hàm giả định các `record` có accessor mặc định đơn giản và không có tác dụng phụ. Nếu accessor tùy biến làm điều khác nhau giữa các lần gọi, việc thay đổi thứ tự/lần đọc accessor trong một đợt refactor có thể ảnh hưởng hành vi. Khi đó phải kiểm tra hợp đồng của kiểu dữ liệu trước khi khẳng định tương đương.

## 7. Đọc kết quả như một bài đánh giá pattern composition

Bảng dưới đây phân tích các input trong chương trình:

| Input | Vì sao không/được ưu tiên? | Kết quả |
| --- | --- | --- |
| `S-01`: khách VIP, tên/thành phố hợp lệ, điểm (1,2), 3 kiện | Nested record khớp; toàn bộ điều kiện guard đúng | `Ưu tiên: S-01 / An @ Huế` |
| `S-02`: `vip == false` | Cấu trúc khớp nhưng guard false | `Thông thường: S-02` |
| `S-03`: `Address.location() == null` | Nested `Point(...)` không khớp | `Thông thường: S-03` |
| `S-04`: `customer == null` | Nested `Customer(...)` không khớp | `Thông thường: S-04` |
| `S-05`: thành phố là chuỗi rỗng | Pattern khớp; `!city.isBlank()` false | `Thông thường: S-05` |
| `"abc"` | Không phải `Shipment` | `Không phải lô hàng` |
| `null` | Selector null, do `case null` xử lý | `Không có dữ liệu` |

Đây là cách review **theo hành vi**, không chỉ theo hình thức mã nguồn. Một bản rút gọn chỉ đáng chấp nhận nếu vẫn xử lý đầy đủ nhánh null, trường hợp component record thiếu, guard sai và kiểu đầu vào khác.

Ở bản `classifyReadable`, `isVipCustomer` nhận `Object` và kiểm tra bằng `instanceof Customer(...)`; khi đối số null, pattern không khớp và hàm trả false. `isValidAddress` cũng nhận `Object`; nếu `location` null, nested `Point(...)` không khớp. Nhờ đó `isPriority` không cần gọi accessor trên component thiếu.

Điểm cần học: **giảm độ sâu ở nơi điều phối, giữ chi tiết cấu trúc trong helper có tên tốt**. Mã trở nên dễ đánh giá hơn nếu tên helper mô tả chính xác bất biến mà nó kiểm tra.

## 8. Kiểm tra null: điểm dễ khiến pattern composition bị hiểu sai

Khi review pattern lồng, hãy phân biệt:

- **Bản thân record pattern** `Customer(...)` hoặc `Point(...)` yêu cầu đối tượng tại tầng đó không-null.
- **`var customer` hoặc `var location` nằm trong record pattern** nhận nguyên component theo kiểu đã suy luận, và có thể giữ giá trị null.
- **Selector `switch` null** là trường hợp riêng: nên thêm `case null` nếu muốn xử lý, vì `default` không phải lựa chọn thay thế chung cho null trong pattern matching `switch`.

Ví dụ:

```java
case Shipment(var id, Customer(var name, var vip),
              var address, var parcels) ->
    ...
```

Nhánh trên đòi `customer` là `Customer` không-null nhưng **không đòi `address` không-null**, vì thành phần thứ ba chỉ dùng `var address`. Nếu cần ràng buộc sâu hơn, viết `Address(var city, Point(...))` ở vị trí đó.

Một guard null-safe:

```java
case Shipment(var id, var customer, var address, var parcels)
        when customer == null || address == null ->
    "Thiếu thông tin";
```

Ở đây cả `customer` và `address` đã được ràng buộc bởi pattern; guard `||` dùng chúng hợp lệ. Đừng nhầm với:

```java
// SAI: biến x ở bên phải || chưa chắc được ràng buộc.
if (value instanceof Point(var x, var y) || x >= 0) {
    // ...
}
```

Khi `instanceof` false, vế phải của `||` vẫn có thể được đánh giá, nên `x` không nằm trong phạm vi được bảo đảm. Ngược lại, dùng `&&` phù hợp khi các điều kiện bên phải chỉ được xét sau khi pattern khớp.

Một vấn đề khác: `var name` có thể nhận chuỗi null; trước khi gọi `name.isBlank()`, guard cần `name != null`. Tách helper có tên rõ nghĩa không được làm mất thứ tự kiểm tra null này.

## 9. Thứ tự nhánh và dominance ảnh hưởng tính dễ đọc

Trong pattern matching `switch`, các nhánh được xét theo thứ tự; một nhánh tổng quát đặt quá sớm có thể che nhánh cụ thể.

Ví dụ **cố ý sai, không biên dịch**:

```java
return switch (value) {
    case Shipment shipment -> "Mọi lô hàng";
    case Shipment(var id, Customer(var name, var vip),
                  var address, var parcels) when vip ->
        "VIP"; // Nhánh bị che bởi case Shipment ở trên.
    default -> "Khác";
};
```

`case Shipment shipment` nhận mọi `Shipment` không-null. Nhánh lồng phía sau do đó bị **dominated**. Một thứ tự có thể kiểm tra dễ dàng hơn:

```java
return switch (value) {
    case Shipment(
            var id, Customer(var name, var vip),
            var address, var parcels) when vip ->
        "VIP";
    case Shipment shipment -> "Mọi lô hàng khác";
    default -> "Khác";
};
```

Hai đoạn trên là **minh họa đặt trong phương thức** có `value` và các record liên quan, không phải chương trình độc lập. Nếu `value` có thể null, cần quyết định xử lý null riêng.

Về **exhaustiveness**, một `switch` expression cần các nhánh bao phủ những giá trị có thể đến. Với selector `Object`, các pattern chỉ nhận `Shipment` không đủ bao phủ, nên thường cần `default`. Với một `sealed interface` có đầy đủ biến thể, compiler có thể hỗ trợ kiểm tra bao phủ khi dùng `switch`; tuy nhiên **guard tùy ý không được coi là đã xử lý mọi giá trị của kiểu đó**. Một nhánh tổng quát cho biến thể sau các guard vẫn có giá trị.

Khi review, hãy hỏi: “Nếu thêm một loại message vào hệ `sealed`, tôi có biết nhánh nào phải xử lý không?” và “Nếu guard VIP false, nhánh tiếp theo có nhận lô hàng không?” Hai câu hỏi này thường bộc lộ vấn đề rõ hơn việc chỉ đếm số dòng.

## 10. Khi nào giữ pattern inline, khi nào tách?

| Tình huống | Lựa chọn thường dễ đọc hơn | Lý do |
| --- | --- | --- |
| Chỉ cần hai component và một phép so sánh | Giữ record pattern và guard tại chỗ | Toàn bộ ý định nằm trong một màn hình đọc |
| Cấu trúc record lồng nhau khớp đúng mô hình nghiệp vụ, dùng nhiều giá trị lá | Giữ nested record pattern có thụt lề rõ | Thể hiện quan hệ cấu trúc trực tiếp |
| Guard gồm nhiều chính sách khác nhau (tuổi, trạng thái, khu vực, số tiền...) | Trích helper tên theo quy tắc | Tách logic nghiệp vụ khỏi điều phối nhánh |
| Cùng điều kiện xuất hiện ở nhiều `case` | Dùng một hàm kiểm tra dùng chung, thuần và có test | Giảm lặp và tránh sửa thiếu |
| Một nhánh dùng chỉ một component của record sâu | Tách ở tầng nông hơn hoặc gọi accessor | Tránh ràng buộc nhiều biến thừa |
| Cần thông báo lỗi khác nhau theo từng trường thiếu | Tách nhiều nhánh hoặc validation riêng | Người đọc thấy rõ nhánh xử lý từng lỗi |
| Có nhiều biến thể `sealed` | Dùng `switch` rõ ràng trên từng biến thể, guard nhỏ | Tận dụng kiểm tra bao phủ khi biên dịch |

Một mẹo khi review: thử **đọc câu lệnh thành tiếng**. Nếu có thể nói “Với lô hàng đủ dữ liệu, nếu khách VIP và địa chỉ hợp lệ thì ưu tiên; còn lại xử lý thông thường” mà không phải nhắc đến bảy tên biến cùng lúc, mã đang truyền tải ý định tốt.

## 11. Quy trình review và refactor mà không đổi hành vi

1. **Ghi rõ đầu vào và đầu ra.** Nhánh nào cho `null`, kiểu khác, component null, guard false và dữ liệu hợp lệ?
2. **Gạch ranh giới cấu trúc và quy tắc.** Phần `Record(...)` trả lời “hình dạng là gì?”; `when` trả lời “giá trị đạt điều kiện gì?”.
3. **Đọc theo thứ tự ngoài → trong.** Xác định từng component theo khai báo record; không suy diễn theo tên biến trong pattern.
4. **Thống kê biến thực sự dùng.** Nếu tách nhiều component chỉ để kiểm tra một cờ, thử dùng pattern nông hơn hoặc helper.
5. **Thử đặt tên cho điều kiện.** Tên như `isPriority` chỉ hữu ích khi có hợp đồng rõ ràng; nếu tên chung chung như `check` hoặc `valid`, cân nhắc cụ thể hóa.
6. **Kiểm tra thứ tự case.** Nhánh có guard/cụ thể phải được xét trước nhánh bao phủ rộng; đừng tạo dominance.
7. **Lập bảng các trường hợp biên.** Ít nhất: khớp đầy đủ, guard false, null tại mỗi record lồng, chuỗi null/rỗng, selector null, kiểu khác.
8. **So sánh kết quả trước và sau.** Chạy cùng bộ input và xác nhận output/exception mong đợi, đặc biệt khi có accessor tùy biến hay các quy tắc kiểm tra theo thứ tự.

Tách hàm cũng có chi phí: nhiều bước điều hướng hơn và một số trường hợp cần đọc cùng dữ liệu hai lần. Vì vậy mục tiêu là **cân bằng** giữa cấu trúc hiện rõ trong `case` và tên quy tắc nghiệp vụ ở helper. Không có định dạng nào luôn thắng.

Khi refactor logic có tác dụng phụ, phải thận trọng: guard có thể được xét theo thứ tự và accessor tùy biến có thể ném ngoại lệ hoặc có side effect. Ví dụ minh họa trong bài dùng các record có accessor mặc định, giúp so sánh hành vi rõ ràng. Nếu accessor ném ngoại lệ trong quá trình deconstruction, Java có thể báo `MatchException` chứa nguyên nhân gốc; đừng che đi sự khác biệt lỗi bằng một helper bắt exception tùy tiện.

## 12. Các lỗi nhận xét khi code review

| Nhận xét chưa đủ cụ thể | Cách nhận xét hữu ích hơn |
| --- | --- |
| “Pattern này quá dài.” | “Nhánh tách qua `Shipment → Address → Point`, nhưng chỉ cần biết tọa độ hợp lệ; hãy thử đặt `isValidAddress` và kiểm tra riêng null ở `Point`.” |
| “Thêm `default` đi.” | “Selector là `Object`; ngoài `Shipment` còn có các kiểu khác. Bổ sung nhánh cho kiểu khác và kiểm tra chính sách selector null.” |
| “Dùng pattern ở mọi chỗ cho hiện đại.” | “Nhánh chỉ cần `shipment.id()`; type pattern `Shipment s` có thể dễ hiểu hơn record pattern bốn component.” |
| “Chỉ cần đảo nhánh là được.” | “`case Shipment s` đang che nhánh `Shipment(...) when vip`. Đưa nhánh VIP lên trước và có test cho VIP/non-VIP.” |
| “Null chắc không bao giờ xảy ra.” | “`Customer(...)` không khớp khi `customer == null`; hãy xác định nhánh dự phòng hoặc chặn null ở constructor.” |
| “Tách ra hàm nào cũng được.” | “Điều kiện gồm ba quy tắc độc lập; tách `isVipCustomer` và `isValidAddress` để có tên và test rõ ràng.” |

Review tốt chỉ ra **vị trí**, **rủi ro cụ thể**, **đề xuất có lý do**, và **cách kiểm chứng**. Việc làm đẹp indentation mà không kiểm tra null, guard và dominance không đảm bảo mã dễ hiểu hơn về hành vi.

## 13. Bài tập thực hành

**Bài 1 — Đánh giá hai cách viết.** Với `record Pair(Point first, Point second) {}`, muốn kiểm tra hai tọa độ x cùng dương, hãy so sánh:

```java
// Phương án A: tách trực tiếp.
case Pair(Point(var x1, var y1), Point(var x2, var y2))
        when x1 > 0 && x2 > 0 ->
    "Hai x dương";

// Phương án B: giữ nguyên hai Point.
case Pair(var first, var second)
        when first != null && second != null
            && first.x() > 0 && second.x() > 0 ->
    "Hai x dương";
```

Đây là hai **đoạn nhãn `case` minh họa cho hai cách triển khai**, không đặt cạnh nhau như hai nhánh trùng nhau trong một `switch`. Cả hai cùng mục tiêu với `Point` có accessor mặc định; cách A rõ cấu trúc lồng, cách B có nhiều điều kiện null hơn nhưng không tách `y1` và `y2` không dùng. Bạn sẽ chọn cách nào cho người mới trong nhóm? Giải thích dựa trên mục đích của nhánh.

**Bài 2 — Tìm lỗi dominance.** Vì sao `case Shipment s -> ...` ở trước `case Shipment(...) when ... -> ...` làm nhánh sau không thể tới? Hãy viết lại thứ tự và chỉ ra trường hợp guard false.

**Bài 3 — Thiết kế bộ kiểm thử.** Với `PatternReadabilityDemo`, thêm ba tình huống: `id == null`, `Customer.name() == null`, và `parcels == 0`. Dự đoán kết quả cả hai hàm phân loại và chạy để đối chiếu.

**Bài 4 — Cân nhắc refactor.** Nếu `isPriority` thêm yêu cầu thành phố thuộc danh sách được phục vụ và điểm nằm trong một vùng nhất định, bạn sẽ giữ mọi điều kiện inline hay tách `isServiceableDestination`? Hãy nêu lý do dựa vào độ dễ đọc, test và khả năng sửa sau này.

**Bài 5 — Dùng bảng review.** Đọc một pattern composition trong dự án của bạn (nếu có) và trả lời: mục đích, độ sâu, biến thừa, thứ tự `case`, khả năng xảy ra null, guard, nhánh fallback, và test quan trọng nhất. Không sửa mã trước khi biết hành vi thực tế.

## 14. Ghi nhớ

**Pattern composition dễ đọc khi cấu trúc được thể hiện vừa đủ, điều kiện mang tên rõ ràng, đường đi qua các nhánh có thể dự đoán, và hành vi giữ nguyên sau refactor.** Với nested record patterns, kiểm tra kiểu/record diễn ra theo các tầng; `var` nhận component, `when`/`&&` lọc thêm giá trị. Đừng chỉ tìm biểu thức ngắn nhất: hãy tìm biểu thức giúp người khác hiểu **vì sao nhánh được chọn** và **điều gì xảy ra nếu dữ liệu thay đổi**.

Tài liệu tham khảo:
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
