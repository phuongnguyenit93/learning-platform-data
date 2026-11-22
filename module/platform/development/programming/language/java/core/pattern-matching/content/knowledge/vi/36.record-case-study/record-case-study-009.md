# Đánh giá độ sâu nested pattern: case study record trong Java 21+

## 1. Đặt vấn đề

**Nested record pattern** cho phép kiểm tra và tách dữ liệu từ một record chứa record khác, thay vì viết nhiều phép `instanceof`, cast và lời gọi accessor thủ công. Ví dụ, dữ liệu đơn mua hàng được tổ chức như sau:

```text
Purchase
├── reference: String
├── customer: Customer
│   ├── id: String
│   └── address: Address
│       ├── city: City
│       │   └── name: String
│       └── street: String
└── cents: long
```

Để lấy `City.name`, Java 21 có thể viết:

```java
// Đoạn minh họa trong một phương thức có Object value.
if (value instanceof Purchase(
        var ref,
        Customer(var id, Address(City(var name), var street)),
        var cents)) {
    System.out.println(ref + ":" + id + ":" + name);
}
```

Cú pháp này gọn hơn nhiều phép truy cập từng tầng, nhưng **gọn về số dòng không tự động đồng nghĩa dễ bảo trì**. Khi model sâu hơn, một biểu thức phải gánh đồng thời nhiều trách nhiệm:

- Xác nhận có record đúng loại ở từng tầng.
- Ràng buộc các component vào biến.
- Xử lý `null` ở record gốc, record con và giá trị component.
- Đánh giá các guard nghiệp vụ.
- Phụ thuộc vào số lượng/thứ tự/kiểu component của nhiều record.
- Giúp người đọc tìm ra tầng gây ra `non-match` khi debug.

**Mục tiêu:** học cách **đánh giá độ sâu nested pattern bằng tiêu chí đo được**, thí nghiệm với cùng dữ liệu ở độ sâu 1, 2, 3, 4; so sánh với cách truy cập từng bước và xác định lúc nào nên tách một pattern sâu.

Bài dùng **record patterns final từ Java 21** (JEP 440) và type patterns/flow scoping của `instanceof` (JEP 394). `record` declaration đã final từ Java 16 (JEP 395). Mã chính chạy với **JDK 21+**, không cần `--enable-preview`.

## 2. Quy ước đo độ sâu: tính rõ trước khi so sánh

Không có một thước đo “độ sâu tốt nhất” chung được Java Language Specification ấn định cho chất lượng source code. Vì vậy cần **định nghĩa nhất quán quy ước riêng cho buổi đánh giá**.

Trong bài:

- **D — Max record nesting depth:** số record patterns trên đường lồng sâu nhất; record ngoài cùng tính là **1**. Type pattern `City c` không tính là record pattern `City(...)`.
- **R — Record-pattern nodes:** tổng số lần xuất hiện các cấu trúc `RecordType(...)` trong biểu thức.
- **V — Bound variables:** số biến được ràng buộc qua `var name` hoặc type pattern, dù biến đó có được dùng tiếp hay không.
- **N — Required nested-record links:** số kết nối record-con phải tồn tại và match để đi hết đường lồng sâu nhất. Với một chuỗi record tuyến tính như ví dụ, `N = D - 1`.
- **G — Guard predicates:** số điều kiện Boolean độc lập mà ta cố ý viết bên ngoài record pattern để kiểm tra giá trị nghiệp vụ.
- **S — Schema coupling points:** những vị trí mà source phụ thuộc trực tiếp vào component của record và cần review nếu record thay đổi; trong bài này xác định qua từng record-pattern node và biến được tách, không tự suy ra số file sẽ sửa.

**Ví dụ:**

```java
Purchase(var ref,
    Customer(var id,
        Address(
            City(var name),
            var street)),
    var cents)
```

Cách đếm trên:

- `D = 4` vì có chuỗi `Purchase → Customer → Address → City`.
- `R = 4` record-pattern nodes.
- `V = 5` biến: `ref`, `id`, `name`, `street`, `cents`.
- `N = 3` liên kết bắt buộc: `Purchase.customer`, `Customer.address` và `Address.city`.
- `G = 0` nếu chỉ xét record pattern; **`G = 3`** nếu ghép guard `name != null && !name.isBlank() && cents > 0`.

`String name` là **component thường**, không phải record pattern bổ sung, vì `City(var name)` đã là record node cuối; không tính thêm một tầng cho `var name`.

**Quan trọng:** với cây pattern có nhiều nhánh lồng nhau, `R` có thể lớn hơn `D`. Đừng mặc định hai chỉ số bằng nhau; ở case study này chỉ có một đường lồng sâu nên trùng nhau.

## 3. Bốn độ sâu trên cùng một record model

Khai báo các kiểu dữ liệu:

```java
record City(String name) {}
record Address(City city, String street) {}
record Customer(String id, Address address) {}
record Purchase(String reference, Customer customer, long cents) {}
```

Đây là **các record minh họa**, chương trình runnable đầy đủ nằm ở mục 7. Để so sánh null và non-match, bản mẫu **không cài validation trong constructor**; do đó cố ý cho phép tạo component null hoặc chuỗi blank. Với domain model production, cần áp invariant tại constructor/factory phù hợp.

Định nghĩa một đối tượng hợp lệ:

```java
Object ok = new Purchase("P-1",
        new Customer("C-1", new Address(new City("Hue"), "Main")),
        2500);
```

### 3.1. Độ sâu 1: chỉ tách Purchase

```java
if (value instanceof Purchase(var ref, var customer, var cents)) {
    // D = 1, R = 1; customer có thể null.
}
```

Ở đây ta kiểm tra record gốc `Purchase` và lấy **nguyên component `customer`**, không yêu cầu nó khác null. Nếu `new Purchase("P-2", null, 2500)`, pattern **vẫn khớp** vì `var customer` có thể ràng buộc null.

Phù hợp khi code chỉ cần `reference` hoặc `cents`, không cần hiểu cấu trúc khách hàng. Lồng thêm record chỉ vì có thể làm được sẽ tăng coupling không cần thiết.

### 3.2. Độ sâu 2: Purchase → Customer

```java
if (value instanceof Purchase(
        var ref, Customer(var id, var address), var cents)) {
    // D = 2; Customer(...) bắt buộc phải khớp.
}
```

Khác biệt chủ yếu: `customer == null` bây giờ làm toàn bộ record pattern **không khớp**, vì `Customer(...)` là pattern con yêu cầu một đối tượng Customer thực sự.

`address` có thể null vì được lấy bằng `var address`, chưa phải `Address(...)`. Nếu chỉ cần customer ID, đây là độ sâu đủ dùng.

### 3.3. Độ sâu 3: Purchase → Customer → Address

```java
if (value instanceof Purchase(
        var ref,
        Customer(var id, Address(var city, var street)),
        var cents)) {
    // D = 3; Address(...) phải tồn tại.
}
```

`Customer.address == null` khiến pattern không khớp. Nhưng **`Address.city == null` vẫn có thể khớp** vì đang dùng `var city`, chưa phải `City(...)`.

Ở đây logic đang phụ thuộc vào thứ tự component của ba record. Nếu cần một giá trị `City` như một value object có hành vi riêng, có thể giữ nguyên `var city` thay vì lồng tiếp.

### 3.4. Độ sâu 4: Purchase → Customer → Address → City

```java
if (value instanceof Purchase(
        var ref,
        Customer(var id, Address(City(var name), var street)),
        var cents)
        && name != null && !name.isBlank() && cents > 0) {
    // D = 4, R = 4, V = 5, N = 3, G = 3.
}
```

Trường hợp này đòi hỏi **cả ba record con tồn tại**, rồi kiểm tra thêm hai yêu cầu nghiệp vụ: `City.name` phải không blank và số tiền `cents` phải dương.

`City(var name)` **vẫn có thể match `new City(null)`**, bởi `var name` nhận null; nhưng điều kiện `name != null` sẽ từ chối sau khi deconstruction đã khớp. Đừng kết luận mọi giá trị `false` ở biểu thức `instanceof ... && guard` đều có nghĩa pattern sai cấu trúc.

Các toán tử `&&` đánh giá ngắn mạch: `!name.isBlank()` chỉ được gọi khi `name != null`, tránh `NullPointerException`.

### 3.5. Bảng chỉ số của bốn phiên bản

| Cấp | Đường pattern | D | R | V | N | G |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | `Purchase(...)` | 1 | 1 | 3 | 0 | 0 |
| 2 | `Purchase(...Customer(...))` | 2 | 2 | 4 | 1 | 0 |
| 3 | `Purchase(...Customer(...Address(...)))` | 3 | 3 | 5 | 2 | 0 |
| 4 | `Purchase(...Customer(...Address(City(...))))` kèm guard | 4 | 4 | 5 | 3 | 3 |

Bảng này dùng **đúng một mẫu code cho mỗi cấp**, không phải điểm chấm chất lượng Java. Trong một domain khác, hai pattern cùng `D=4` vẫn có thể khác nhau rất lớn về số nhánh, độ rõ tên kiểu, độ dài guard, chi phí truy cập dữ liệu và mức cần thay đổi khi model tiến hóa.

## 4. Vì sao tăng độ sâu thay đổi hành vi với null?

Trong record patterns, phải phân biệt **null ở selector**, **null ở vị trí có record pattern con** và **null ở component bị ràng buộc bởi `var`**.

Ví dụ dữ liệu:

```java
Object noCustomer = new Purchase("P-2", null, 2500);
Object noCity = new Purchase("P-4",
        new Customer("C-4", new Address(null, "Main")), 2500);
```

Kết quả theo cấp:

| Input | Pattern cấp 1 | Cấp 2 | Cấp 3 | Cấp 4 |
| --- | --- | --- | --- | --- |
| `Purchase` đầy đủ | Khớp | Khớp | Khớp | Khớp nếu guard đạt |
| `Purchase.customer == null` | **Khớp**, `var customer = null` | Không khớp | Không khớp | Không khớp |
| `Customer.address == null` | Khớp | **Khớp**, `var address = null` | Không khớp | Không khớp |
| `Address.city == null` | Khớp | Khớp | **Khớp**, `var city = null` | Không khớp |
| `City.name == null` | Khớp | Khớp | Khớp | **Pattern khớp**, guard thất bại |
| `City.name == " "` | Khớp | Khớp | Khớp | Pattern khớp, guard `isBlank` thất bại |
| `cents == 0` | Khớp | Khớp | Khớp | Pattern khớp, guard `cents > 0` thất bại |
| Root `value == null` | Không khớp | Không khớp | Không khớp | Không khớp |

**Bài học:** mỗi lần thay `var component` bằng `RecordType(...)`, bạn đã bổ sung một **điều kiện cấu trúc**. Việc tăng chiều sâu không đơn giản là thêm cú pháp để lấy field; nó có thể thay đổi những input được nhận và những input bị từ chối.

Trong một ứng dụng thật, hãy quyết định rõ **đối tượng nào được phép thiếu**. Nếu thiếu địa chỉ là dữ liệu hợp lệ, không nên dùng pattern sâu tới `Address(...)` ở nhánh xử lý mà vẫn muốn nhận trường hợp thiếu địa chỉ. Có thể tách branch hoặc dùng model đại diện cho trạng thái thiếu dữ liệu theo chủ đích.

## 5. Độ sâu cao có lợi trong trường hợp nào?

Một nested record pattern đáng dùng khi nó **khớp chính xác cấu trúc mà nhánh nghiệp vụ cần**:

- Tập record được thiết kế rõ ràng, tương đối ổn định.
- Nhánh cần các component ở tầng sâu và xử lý ngay trong phạm vi ngắn.
- Một non-match ở bất cứ tầng nào **đều mang cùng một ý nghĩa**, chẳng hạn “không phải đơn hàng đủ địa chỉ để giao”.
- Có ít guard, ít biến ràng buộc và tên kiểu/component mang ý nghĩa domain.
- Dữ liệu đã được chuẩn hóa ở boundary, không cần báo từng lỗi chi tiết ngay tại nơi match.

Ví dụ, một hàm chuyển đổi dữ liệu nhỏ có thể dùng trực tiếp cấp 4 để lấy `City.name` nếu thiếu bất kỳ tầng nào cũng dẫn tới kết quả chung `"NO_MATCH"`.

Ngược lại, nếu nghiệp vụ cần **thông báo khác nhau** cho “thiếu khách hàng”, “thiếu địa chỉ”, “thiếu thành phố” và “tên thành phố rỗng”, một biểu thức cấp 4 trả Boolean là **quá ít thông tin** cho mục đích debug/validation. Hãy chia bước hoặc dùng kiểu kết quả validation có lý do.

## 6. Tiêu chí đánh giá ngoài số D

### 6.1. Cấu trúc: D, R, V, N, G

Dùng bảng ở mục 3 làm baseline. Khi `D` tăng nhưng `V` không tăng, độ khó đọc vẫn có thể tăng vì có thêm dấu ngoặc và vị trí thất bại tiềm năng. Khi `G` tăng, cần xem logic còn đang “match cấu trúc” hay đã trộn nhiều **business rules** vào biểu thức.

Trong ví dụ cấp 4, `R=4` và `N=3`: có ba record con bắt buộc phải tồn tại. `G=3` theo cách đếm điều kiện nguyên tử (không đếm dấu ngoặc, cũng không tự tính mỗi lần sử dụng `&&` là một tầng).

### 6.2. Readability: người đọc mất bao lâu để giải thích?

Đưa cho reviewer biểu thức cấp 4 và hỏi:

1. `customer == null` thì biểu thức trả gì?
2. `city == null` (đối tượng City) khác gì `city.name() == null`?
3. `street == null` có làm biểu thức không khớp không?
4. `cents <= 0` là lỗi cấu trúc hay lỗi guard?
5. Biến `name` có thể được dùng ở đâu theo flow scoping?
6. Đổi thứ tự component nào có thể khiến biến nhận sai ý nghĩa?

Nếu trả lời không nhất quán, nên tách pattern, đổi tên biến hoặc chuyển một phần validation sang factory/constructor.

### 6.3. Schema coupling: khi record đổi hình dạng

Record patterns được viết theo **số lượng, thứ tự và kiểu của components**, không dựa vào tên accessor. Nếu thay:

```java
record Address(City city, String street) {}
```

thành:

```java
record Address(City city, String street, String postalCode) {}
```

thì pattern cũ `Address(City(var name), var street)` **không còn đủ component**. Compiler có thể báo lỗi và buộc cập nhật. Đây là lợi ích phát hiện thay đổi, đồng thời là **chi phí bảo trì** của việc deconstruct trực tiếp nhiều tầng.

Nếu chỉ cần `City.name`, cân nhắc phương thức domain có tên ý nghĩa như `customer.cityName()` hoặc một truy cập staged, thay vì buộc mọi caller biết chính xác các component của Address.

**Lưu ý:** Khi hai component cùng kiểu `String` bị đảo thứ tự, code đôi khi **vẫn biên dịch** mà logic sai. Compiler không thay thế unit tests và review schema migration.

### 6.4. Debuggability: phân biệt nguyên nhân non-match

Một `instanceof` cấp 4 chỉ trả một Boolean cho toàn bộ cấu trúc. Nó không cho bạn biết record con nào null hoặc guard nào không đạt.

Tách thành những bước có tên rõ, ghi reason, hoặc dùng một `switch` với case cụ thể và fallback:

```java
// Minh họa bên trong class có record Purchase, Customer, Address, City.
static String classify(Object value) {
    return switch (value) {
        case Purchase(var ref,
                Customer(var id, Address(City(var name), var street)),
                var cents)
                when name != null && !name.isBlank() && cents > 0 ->
                "complete:" + ref;
        case Purchase p -> "incomplete-purchase";
        case null -> "missing-root";
        default -> "wrong-type";
    };
}
```

Thứ tự case có chủ đích: case cụ thể với `when` trước `case Purchase p` tổng quát. Nếu đảo thứ tự, case cụ thể có thể bị **dominated**.

Phương thức này vẫn chỉ cho lý do tổng quát `incomplete-purchase`. Muốn chẩn đoán đúng tầng, xem `diagnose` ở chương trình hoàn chỉnh.

### 6.5. Testability: cùng input, hai cách triển khai

Đừng chỉ đo độ dài dòng code. Một thí nghiệm tốt viết:

- **Nested implementation:** dùng depth 4 trực tiếp.
- **Staged implementation:** kiểm tra `Purchase`, `Customer`, `Address`, `City` theo từng bước, rồi mới xử lý `name` và `cents`.

Chạy cùng bộ input và so sánh **kết quả ngữ nghĩa**. Nếu hai cách trả kết quả khác nhau, trước khi kết luận cách nào dễ đọc hơn phải sửa các khác biệt về guard, null policy hoặc thứ tự xử lý.

## 7. Chương trình Java 21 hoàn chỉnh: depth 1–4 và so sánh staged

Tạo file **`NestedPatternDepthDemo.java`**:

```java
public class NestedPatternDepthDemo {
    record City(String name) {}
    record Address(City city, String street) {}
    record Customer(String id, Address address) {}
    record Purchase(String reference, Customer customer, long cents) {}

    static String depth1(Object value) {
        if (value instanceof Purchase(var ref, var customer, var cents)) {
            return "d1:" + ref + ":"
                    + (customer == null ? "missing" : "present");
        }
        return "d1:no-match";
    }

    static String depth2(Object value) {
        if (value instanceof Purchase(
                var ref, Customer(var id, var address), var cents)) {
            return "d2:" + ref + ":" + id;
        }
        return "d2:no-match";
    }

    static String depth3(Object value) {
        if (value instanceof Purchase(var ref,
                Customer(var id, Address(var city, var street)), var cents)) {
            return "d3:" + ref + ":" + id + ":"
                    + (city == null ? "missing" : "present");
        }
        return "d3:no-match";
    }

    static String depth4(Object value) {
        if (value instanceof Purchase(var ref,
                Customer(var id, Address(City(var name), var street)), var cents)
                && name != null && !name.isBlank() && cents > 0) {
            return "d4:" + ref + ":" + id + ":" + name + ":" + cents;
        }
        return "d4:no-match";
    }

    static String staged(Object value) {
        if (!(value instanceof Purchase p)) return "step:no-match";

        Customer customer = p.customer();
        if (customer == null) return "step:no-match";

        Address address = customer.address();
        if (address == null) return "step:no-match";

        City city = address.city();
        if (city == null) return "step:no-match";

        String name = city.name();
        if (name == null || name.isBlank() || p.cents() <= 0)
            return "step:no-match";

        return "step:" + p.reference() + ":" + customer.id()
                + ":" + name + ":" + p.cents();
    }

    static String diagnose(Object value) {
        if (value == null) return "root-null";
        if (!(value instanceof Purchase p)) return "wrong-root";
        if (p.customer() == null) return "customer-null";
        if (p.customer().address() == null) return "address-null";
        if (p.customer().address().city() == null) return "city-null";

        String name = p.customer().address().city().name();
        if (name == null) return "city-name-null";
        if (name.isBlank()) return "city-name-blank";
        if (p.cents() <= 0) return "cents-nonpositive";
        return "ok";
    }

    static void check(String label, Object value,
                      String expected, String reason) {
        String nested = depth4(value);
        String step = staged(value);
        String diagnosis = diagnose(value);
        String normalized = nested.replace("d4:", "step:");

        if (!nested.equals(expected) || !step.equals(normalized)
                || !reason.equals(diagnosis)) {
            throw new AssertionError(label + " nested=" + nested
                    + ", step=" + step + ", diagnose=" + diagnosis);
        }
        System.out.println(label + " -> " + nested + " [" + diagnosis + "]");
    }

    public static void main(String[] args) {
        Object ok = new Purchase("P-1",
                new Customer("C-1",
                        new Address(new City("Hue"), "Main")), 2500);

        System.out.println(depth1(ok));
        System.out.println(depth2(ok));
        System.out.println(depth3(ok));
        System.out.println(depth4(ok));

        Object noCustomer = new Purchase("P-2", null, 2500);
        System.out.println(depth1(noCustomer));
        System.out.println(depth2(noCustomer));

        Object noCity = new Purchase("P-4",
                new Customer("C-4", new Address(null, "Main")), 2500);
        System.out.println(depth3(noCity));
        System.out.println(depth4(noCity));

        check("valid", ok, "d4:P-1:C-1:Hue:2500", "ok");
        check("street-null", new Purchase("P-5",
                new Customer("C-5",
                        new Address(new City("Da Nang"), null)), 10),
                "d4:P-5:C-5:Da Nang:10", "ok");
        check("customer-null", noCustomer,
                "d4:no-match", "customer-null");
        check("address-null", new Purchase("P-3",
                new Customer("C-3", null), 2500),
                "d4:no-match", "address-null");
        check("city-null", noCity, "d4:no-match", "city-null");
        check("name-null", new Purchase("P-6",
                new Customer("C-6",
                        new Address(new City(null), "Main")), 2500),
                "d4:no-match", "city-name-null");
        check("name-blank", new Purchase("P-7",
                new Customer("C-7",
                        new Address(new City(" "), "Main")), 2500),
                "d4:no-match", "city-name-blank");
        check("cents-zero", new Purchase("P-8",
                new Customer("C-8",
                        new Address(new City("Hue"), "Main")), 0),
                "d4:no-match", "cents-nonpositive");
        check("wrong-root", "not-purchase",
                "d4:no-match", "wrong-root");
        check("root-null", null, "d4:no-match", "root-null");

        System.out.println("10/10 comparisons passed");
    }
}
```

### 7.1. Biên dịch và chạy

Với JDK 21 trở lên:

```bash
javac --release 21 NestedPatternDepthDemo.java
java NestedPatternDepthDemo
```

**Stdout đã kiểm chứng:**

```text
d1:P-1:present
d2:P-1:C-1
d3:P-1:C-1:present
d4:P-1:C-1:Hue:2500
d1:P-2:missing
d2:no-match
d3:P-4:C-4:missing
d4:no-match
valid -> d4:P-1:C-1:Hue:2500 [ok]
street-null -> d4:P-5:C-5:Da Nang:10 [ok]
customer-null -> d4:no-match [customer-null]
address-null -> d4:no-match [address-null]
city-null -> d4:no-match [city-null]
name-null -> d4:no-match [city-name-null]
name-blank -> d4:no-match [city-name-blank]
cents-zero -> d4:no-match [cents-nonpositive]
wrong-root -> d4:no-match [wrong-root]
root-null -> d4:no-match [root-null]
10/10 comparisons passed
```

Chương trình đã được chạy trên **JDK 24/JShell** và xác nhận đúng 19 dòng trên, sử dụng các cú pháp final từ Java 21. `check` đối chiếu **cả ba kết quả**: output nested, output staged sau khi chuẩn hóa tiền tố và reason. Nếu một kết quả không đúng expected, chương trình ném `AssertionError` thay vì chỉ in thành công.

**Mục đích của `diagnose`:** Nêu **lý do đầu tiên** theo thứ tự được kiểm tra. Hàm này không phải validator tổng hợp mọi lỗi; nếu một Purchase có cả customer null và cents không dương, nó trả `customer-null` trước. Với record accessors mặc định, việc lặp lại getter trong ví dụ ổn định; ở code thật, nên lưu reference trung gian vào biến để giảm lặp và dễ đặt breakpoint, nhất là khi accessor được custom hóa.

## 8. Phân tích bộ 10 phép so sánh

| Test | Kết quả cấp 4 | Reason từ chẩn đoán | Ý nghĩa |
| --- | --- | --- | --- |
| `valid` | `d4:P-1:C-1:Hue:2500` | `ok` | Đường đi bình thường, cả bốn tầng tồn tại và guard đúng |
| `street-null` | `d4:P-5:C-5:Da Nang:10` | `ok` | `var street` có thể nhận null, và domain mẫu cho phép |
| `customer-null` | `d4:no-match` | `customer-null` | `Customer(...)` bắt buộc khác null |
| `address-null` | `d4:no-match` | `address-null` | `Address(...)` bắt buộc khác null |
| `city-null` | `d4:no-match` | `city-null` | `City(...)` bắt buộc khác null |
| `name-null` | `d4:no-match` | `city-name-null` | Record khớp, nhưng guard `name != null` thất bại |
| `name-blank` | `d4:no-match` | `city-name-blank` | Record khớp, nhưng guard `!name.isBlank()` thất bại |
| `cents-zero` | `d4:no-match` | `cents-nonpositive` | Record khớp, nhưng guard `cents > 0` thất bại |
| `wrong-root` | `d4:no-match` | `wrong-root` | Selector khác kiểu `Purchase` |
| `root-null` | `d4:no-match` | `root-null` | `instanceof` trên null trả false |

Bảng cho thấy **depth 4 rút ngắn cú pháp đường đi hợp lệ**, nhưng tất cả lỗi đều quy về `d4:no-match` nếu chỉ nhìn kết quả trực tiếp. Chỉ khi bổ sung một cách kiểm tra reason riêng mới phân biệt được lỗi ở từng tầng.

**Thay đổi mức độ sâu có thể thay đổi chính sách chấp nhận dữ liệu**: cấp 1 nhận `Purchase` có customer null; cấp 2 loại bỏ; cấp 3 nhận address có city null; cấp 4 loại bỏ. Vì vậy, khi refactor biểu thức đang dùng `var city` thành `City(var name)`, hãy viết test cho `city == null` ngay cả khi các case hợp lệ vẫn chạy đúng.

## 9. Tại sao không có một “độ sâu tối đa” chung?

Java cho phép nested record patterns với độ sâu được giới hạn bởi cú pháp, cấu trúc thực tế và các giới hạn tài nguyên/compiler; không có quy tắc kiểu **“Java chỉ nên lồng tối đa hai record”** trong JLS. Một ngưỡng đánh giá code review là **quy ước nhóm**, không phải yêu cầu ngôn ngữ.

Một heuristic có ích để thảo luận:

| Độ sâu | Nhận định khởi đầu | Khi nào nên xem xét thay đổi? |
| --- | --- | --- |
| D=1 | Thường dễ đọc | Khi record có rất nhiều component/guard hoặc không cần deconstruction |
| D=2 | Tương đối rõ nếu model tốt | Khi null policy/điều kiện nghiệp vụ phức tạp |
| D=3 | Nên review số biến và độ phụ thuộc schema | Khi có nhiều nhánh, độ sâu vượt quá phần logic thực sự dùng |
| D≥4 | Cân nhắc staged extraction hoặc helper domain | Khi debug thất bại khó, component thay đổi thường xuyên, guard dài, hoặc người review khó giải thích |

**Đây là heuristic, không phải giới hạn bắt buộc.** Một pattern cấp 4 ngắn, có kiểu rõ và được test tốt có thể **dễ hiểu hơn** một hàm đầy if/cast phức tạp. Ngược lại, một pattern cấp 2 với 15 binding variables có thể gây khó đọc hơn một pattern cấp 4 nhỏ.

Đánh giá tốt nên dùng **nhiều tiêu chí đồng thời** và bám sát mục đích của nhánh, không gán điểm tốt/xấu chỉ từ D.

## 10. So sánh nested pattern và staged extraction

| Tiêu chí | Nested record pattern cấp 4 | Truy cập từng bước (`staged`) |
| --- | --- | --- |
| Mục tiêu tốt nhất | Kiểm tra toàn bộ một cấu trúc cụ thể rồi dùng dữ liệu ngay | Chẩn đoán từng tầng, áp dụng quy tắc khác nhau cho từng loại lỗi |
| Số record-pattern nodes | 4 | 0 record patterns lồng; dùng một type pattern và accessor |
| Số nhánh kiểm tra null viết rõ | Ít, vì record patterns tự không khớp với record con null | Nhiều, được đặt tên rõ trong code |
| Bảng lý do thất bại | Không có sẵn nếu chỉ dùng `instanceof` Boolean | Dễ mở rộng để trả từng mã lỗi |
| Coupling với component order | Cao trên các record-pattern nodes được tách | Phụ thuộc vào accessor/tên property tương ứng |
| Số dòng | Có thể ngắn hơn | Thường dài hơn |
| Hành vi trên component null | Phân biệt `var` và record pattern con | Kiểm soát bằng kiểm tra null từng bước |
| Kiểm thử | Cần nhiều ca biên để hiểu đường đi | Có thể test từng nhánh/chẩn đoán cụ thể |
| Hiệu năng | Không có bảo đảm luôn nhanh hơn | Không có bảo đảm luôn chậm hơn |

**Không suy luận tốc độ từ bảng này.** JIT có thể tối ưu cả hai dạng; nếu performance là mục tiêu thật, dùng công cụ benchmark phù hợp (ví dụ JMH), warmup, kết quả thống kê và dữ liệu đại diện. `System.nanoTime()` chạy vài lần trên một ví dụ nhỏ không đủ để khẳng định nested pattern sâu hơn chậm hơn.

Sự đánh đổi chính ở đây là **khả năng biểu đạt toàn bộ một cấu trúc trong một nhánh** so với **khả năng quản lý các bước và lý do thất bại tách biệt**.

## 11. Lỗi biên dịch phổ biến khi lồng nhiều record

Các đoạn sau **cố tình sai**; không được chèn vào file chạy ở mục 7.

### 11.1. Sai số component ở record sâu nhất

`City` chỉ có một component `name`. Viết:

```java
// CỐ TÌNH SAI: City chỉ có một component.
static boolean badDepth(Object value) {
    return value instanceof Purchase(
            var ref,
            Customer(var id,
                    Address(City(var name, var extra), var street)),
            var cents);
}
```

Compiler JDK 24 từ chối với lỗi **`incorrect number of nested patterns`**. Đây là dấu hiệu nested pattern phụ thuộc vào **arity** của record. Sửa thành `City(var name)` hoặc thay đổi mô hình phù hợp; đừng thêm biến vô nghĩa để dự đoán số component.

### 11.2. Biến pattern ngoài flow scope

```java
// CỐ TÌNH SAI: name không tồn tại sau if nếu pattern thất bại.
static void badScope(Object value) {
    if (value instanceof Purchase(
            var ref,
            Customer(var id,
                    Address(City(var name), var street)),
            var cents)) {
        System.out.println(name);
    }
    System.out.println(name); // Lỗi biên dịch.
}
```

Java áp dụng **flow scoping**: biến pattern được dùng ở những vị trí compiler biết pattern đã khớp. Nó có thể dùng trong nhánh `if` đúng hoặc vế phải của `&&` nếu biểu thức pattern là vế trái, nhưng không thể dùng tự do sau `if` trong ví dụ này. Ca này đã được thử bằng JShell và bị từ chối khi không thể bảo đảm biến `name` hợp lệ.

### 11.3. Kiểu suy luận của biến không phù hợp thao tác

`Purchase.cents` là primitive `long`. Đoạn này sai:

```java
// CỐ TÌNH SAI: cents là long, không có toUpperCase().
static String wrongType(Purchase purchase) {
    return switch (purchase) {
        case Purchase(var ref,
                Customer(var id,
                        Address(City(var name), var street)),
                var cents) -> cents.toUpperCase();
    };
}
```

Compiler JDK 24 từ chối với lỗi **`long cannot be dereferenced`**. `var` trong pattern không có nghĩa giá trị dynamic hay luôn là `Object`. Nó được suy luận từ kiểu component. Khi deconstruct sâu nhiều tầng, reviewer càng cần kiểm tra mỗi biến đang mang kiểu/ý nghĩa gì.

## 12. Lỗi hành vi không được compiler phát hiện

Không phải lỗi nào cũng xuất hiện ở compile time.

**Nhầm thứ tự component cùng kiểu:**

```java
record Address(City city, String street) {}
record City(String name) {}
```

Nếu có một record như `record Person(String firstName, String lastName) {}`, pattern `Person(var lastName, var firstName)` vẫn có thể biên dịch nhưng **gán sai ý nghĩa** do tên biến do lập trình viên tự đặt. Khi có nhiều record lồng, lỗi đặt sai tên hoặc đổi thứ tự component cùng kiểu có thể khó nhận ra hơn.

**Giả định component non-null:** `City(var name)` có thể khớp khi `name == null`. Code gọi `name.isBlank()` không kiểm tra null có thể ném `NullPointerException`.

**Dùng pattern quá sâu cho một phép phân loại đơn giản:** Nếu chỉ cần biết `value instanceof Purchase` thì không cần `Purchase(...Customer(...Address(...)))`. Pattern sâu có thể khiến một Purchase hợp lệ nhưng thiếu địa chỉ bị bỏ qua ở nhánh không mong muốn.

**Nhiều lời gọi accessor custom:** Với record, accessor có thể được tự định nghĩa. Nếu accessor ném lỗi trong deconstruction, hành vi có thể là `MatchException` thay vì một non-match bình thường. Phương thức `diagnose` dùng accessor mặc định trong chương trình này. Với accessor được custom và có side effect, hãy kiểm soát số lần gọi, giữ dữ liệu ổn định và kiểm tra stack trace khi debug.

**Trộn validation với matching:** Có trường hợp cần tách validation tại boundary, tạo value objects đã kiểm tra invariant, rồi dùng pattern ngắn trên model đã chuẩn hóa. Điều này tốt hơn so với lặp các guard như `name != null && !name.isBlank()` ở nhiều nơi mà không có một contract chung.

## 13. Quy trình đánh giá nested pattern trong codebase

Dùng quy trình này cho một biểu thức thực tế, tránh đánh giá cảm tính:

1. **Chọn case cần đo:** xác định một biểu thức pattern và mục tiêu nghiệp vụ, ví dụ “đọc tên thành phố của đơn hàng”.
2. **Vẽ cây dữ liệu:** liệt kê từng record, component, kiểu tĩnh và chính sách null.
3. **Đếm D/R/V/N/G:** dùng chung quy ước như mục 2; ghi rõ cách tính, nhất là với nhiều nhánh record lồng.
4. **Kiểm tra mục đích của từng tầng:** tầng này được match vì logic thực sự cần, hay chỉ vì muốn ít accessor?
5. **Liệt kê đường thất bại:** root null, sai kiểu, từng record con null, component null/blank, guard thất bại.
6. **Đo coupling khi schema thay đổi:** thử một thay đổi component trong nhánh thử nghiệm; ghi những pattern nào bị compiler từ chối và logic nào cần test lại.
7. **Viết bản staged tương đương:** cùng input và chính sách nghiệp vụ, chỉ khác cấu trúc code.
8. **Chạy unit tests đối chiếu:** đặc biệt các ca null theo từng tầng và các điều kiện guard.
9. **Review readability/debuggability:** người khác có thể giải thích biến, thứ tự và reason hay không? IDE breakpoint giúp khoanh vùng lỗi đến đâu?
10. **Chọn dạng rõ nhất:** giữ nested khi ngắn, đúng mục tiêu và ít rủi ro; chia nhỏ khi nhiều trách nhiệm/validation, hoặc chuyển logic sang phương thức domain có tên.
11. **Đo benchmark riêng nếu cần:** không coi số tầng hay số dòng là số liệu hiệu năng.

Bản ghi đánh giá có thể ở dạng:

| Metric | Nested hiện tại | Staged thay thế | Nhận xét |
| --- | --- | --- | --- |
| D | 4 | Không có nested record pattern | Định nghĩa theo cú pháp của bài |
| R | 4 | 0 | Staged chỉ dùng type pattern root |
| V | 5 | Một số biến cục bộ có tên | Không so sánh trực tiếp số `var` khi code tổ chức khác |
| N | 3 | Ba kiểm tra record con khác null rõ ràng | Tương đương chính sách nhận dữ liệu |
| G | 3 | Ba điều kiện ở `if` trên `name`/`cents` | Tương đương kiểm tra nghiệp vụ |
| Readability | Đọc một biểu thức dài | Đọc nhiều bước ngắn | Đánh giá bằng review, không tự suy ra từ D |
| Failure reason | `d4:no-match` | Có thể trả lý do cụ thể | `diagnose` bổ sung lý do trong demo |
| Regression tests | 10 case đã xác nhận | Cùng 10 case | Kiểm tra tương đương trên cùng bộ input |

## 14. Bài tập thực hành

### Bài tập 1 — đo độ sâu một cấu trúc khác

Cho:

```java
record Coordinates(double lat, double lon) {}
record Location(String label, Coordinates coordinates) {}
record Delivery(String code, Location destination) {}
```

Viết record pattern để lấy `lat`, `lon` từ `Object input`. Theo quy ước mục 2, nếu dùng `Delivery(...Location(...Coordinates(...)))` thì **`D=3` và `R=3`**. Đếm `V` cho chính pattern bạn đã viết, sau đó thêm guard kiểm tra:

- Vĩ độ từ `-90` đến `90`.
- Kinh độ từ `-180` đến `180`.
- Cả hai số hữu hạn: `Double.isFinite`.

### Bài tập 2 — phân biệt record con null với component null

Với cấu trúc ở bài 1, tạo các input: `Delivery(null)` (giả định constructor cho phép), `Location.coordinates == null`, `Coordinates.lat` không hợp lệ, root null. Xem tầng nào làm record pattern không khớp; tầng nào chỉ bị guard từ chối. Lưu ý `Coordinates` chứa primitive `double` nên `lat` không thể null; thay vì ca null, thử `NaN` hoặc vô cực.

### Bài tập 3 — đổi schema

Thêm `String postalCode` vào `Location`. Kiểm tra các record patterns đang tách `Location(...)`; cập nhật đúng thứ tự và số lượng components. So sánh với bản staged dùng `location.coordinates()` để xem mức coupling của hai cách.

### Bài tập 4 — đánh giá hai phương án

Viết hai cách lấy `delivery.destination.coordinates.lat`: một biểu thức nested và một hàm staged. Đặt test cho tất cả ca null/sai kiểu và giá trị biên. Chọn phương án dễ giải thích nhất trong một code review giả định; báo cáo D/R/V/N/G và lý do quyết định, không chỉ nói “nested nhiều nên xấu”.

## 15. Kết luận và tài liệu

**Đánh giá độ sâu nested pattern là đánh giá mức độ cấu trúc được mã hóa trong một biểu thức, cùng ảnh hưởng đến null semantics, readability, schema coupling, debug và test.** Trong ví dụ:

- `D=1` chỉ tách `Purchase` và có thể chấp nhận customer null.
- `D=2` yêu cầu `Customer` tồn tại.
- `D=3` yêu cầu `Address` tồn tại nhưng vẫn có thể lấy `city == null` bằng `var`.
- `D=4` yêu cầu `City` tồn tại, rồi guard mới kiểm tra tên thành phố và số tiền.
- Cùng 10 input, nested depth 4 và staged đã cho kết quả tương đương; method chẩn đoán giải thích lý do.
- **Không có giới hạn độ sâu “đẹp” do Java quy định**; dùng D/R/V/N/G và yêu cầu domain để quyết định. Độ sâu nhiều không đồng nghĩa tự động chậm, an toàn hay khó bảo trì hơn trong mọi trường hợp.

Tài liệu chính thức:

- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
