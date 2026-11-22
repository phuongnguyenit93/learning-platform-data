# Refactor accessor chain dài bằng record patterns trong Java 21

Trong Java, một domain model có nhiều tầng dữ liệu thường tạo ra những biểu thức như:

```java
String city = purchase.customer().profile().address().city();
```

Biểu thức chỉ có một dòng nhưng chứa **nhiều giả định ngầm**: `purchase`, `customer`, `profile`, `address` và `city` đều phải tồn tại. Chỉ cần một thành phần tham chiếu bằng `null`, việc truy cập tiếp có thể ném `NullPointerException` (NPE). Khi phải bảo vệ mọi cấp, mã `if` và các biến trung gian lại dài ra.

**Record patterns** – tính năng chính thức của **Java 21** – cho phép *deconstruct* (tách cấu trúc) một record và các record lồng nhau ngay trong `instanceof` hoặc `switch`. Thay vì viết nhiều chuỗi accessor/cast, ta có thể mô tả **hình dạng dữ liệu cần khớp**, rồi xử lý những giá trị được ràng buộc.

Bài thuộc nhóm **Case study record**, với mục tiêu thực tế: chuyển một accessor chain dài thành mã dễ đọc, an toàn với `null` ở từng cấp, nhưng **không thay đổi hành vi nghiệp vụ**. Phần thực hành dùng Java 21+ với `record`, nested record patterns, `&&`, guard `when` và `switch expression`; không cần `--enable-preview`.

## 1. Mô hình dữ liệu tạo ra accessor chain

Giả sử ứng dụng xử lý đơn hàng và cần lấy thành phố giao hàng. Một đơn mua hàng có khách hàng, khách hàng có hồ sơ, hồ sơ có địa chỉ, địa chỉ có thành phố:

```text
Purchase
 ├─ orderId : String
 ├─ customer : Customer
 │   ├─ id : String
 │   └─ profile : Profile
 │       ├─ address : Address
 │       │   ├─ city : String
 │       │   └─ street : String
 │       └─ email : String
 └─ quantity : int
```

Khai báo model tối giản:

```java
record Address(String city, String street) {}
record Profile(Address address, String email) {}
record Customer(String id, Profile profile) {}
record Purchase(String orderId, Customer customer, int quantity) {}
```

Các khai báo trên là **đoạn thành phần** được đặt trong cùng lớp ở chương trình hoàn chỉnh phần 9.

Với dữ liệu đầy đủ, ta có thể gọi:

```java
Purchase purchase = new Purchase(
        "O-7",
        new Customer(
                "C-1",
                new Profile(
                        new Address("  Ha Noi  ", "Main St"),
                        "user@example.com")),
        2);
String city = purchase.customer().profile().address().city();
System.out.println(city.strip()); // Ha Noi
```

### Record có tự đảm bảo thành phần khác null không?

**Không.** `record` chủ yếu mô tả cấu trúc dữ liệu và tự cung cấp constructor, accessor, `equals/hashCode/toString`. Nếu không thêm validation vào constructor, những giá trị sau vẫn có thể được tạo:

```java
new Purchase("O-1", null, 1);
new Customer("C-1", null);
new Profile(null, "mail");
new Address(null, "street");
```

Điều đó tạo ra ít nhất **năm điểm cần quan sát** khi debug: chính `Purchase` là `null`, `customer` là `null`, `profile` là `null`, `address` là `null` và `city` là `null`. Chuỗi rỗng hoặc chỉ chứa khoảng trắng lại là trường hợp khác `null`.

**Lưu ý về tính bất biến:** các component record là field `final`, nhưng record chỉ bất biến nông (*shallowly immutable*). Với component kiểu tham chiếu trỏ tới object có thể sửa, trạng thái sâu vẫn có thể thay đổi. Trong ví dụ này, các record lồng nhau và `String` không có setter nên trạng thái đơn giản hơn.

## 2. Vấn đề của accessor chain một dòng

Hàm ngắn nhất nhưng không an toàn:

```java
static String unsafeCity(Purchase purchase) {
    return purchase.customer().profile().address().city().strip();
}
```

Các đường gây NPE:

| Giá trị bất thường | Phép truy cập dễ gây NPE |
| --- | --- |
| `purchase == null` | `purchase.customer()` |
| `purchase.customer() == null` | gọi `.profile()` trên customer null |
| `customer.profile() == null` | gọi `.address()` trên profile null |
| `profile.address() == null` | gọi `.city()` trên address null |
| `address.city() == null` | gọi `.strip()` trên city null |

Đây không phải lỗi riêng của record; bất kỳ chuỗi gọi phương thức nào cũng có nguy cơ tương tự khi trung gian có thể `null`.

### Không nên chỉ bọc toàn bộ chain bằng catch NPE

```java
// Không khuyến nghị:
try {
    return purchase.customer().profile().address().city().strip();
} catch (NullPointerException ex) {
    return "UNKNOWN";
}
```

Mã trên không giải thích được **cấp nào** bị thiếu và có thể che lỗi lập trình bên trong accessor do người dùng tự định nghĩa. Nên xử lý điều kiện đã biết bằng guard hoặc invariant thay vì dùng `catch` rộng để che mọi NPE.

## 3. Bước refactor an toàn đầu tiên: tách biến và kiểm tra từng tầng

Trước khi chuyển sang record pattern, nên làm rõ ngữ nghĩa của mã legacy. Ví dụ này chủ động trả `"UNKNOWN"` nếu **bất kỳ cấp dữ liệu cần thiết nào bị thiếu**, hoặc thành phố trống/blank:

```java
static String legacyCity(Purchase purchase) {
    if (purchase == null) return "UNKNOWN";

    Customer customer = purchase.customer();
    if (customer == null) return "UNKNOWN";

    Profile profile = customer.profile();
    if (profile == null) return "UNKNOWN";

    Address address = profile.address();
    if (address == null) return "UNKNOWN";

    String city = address.city();
    if (city == null || city.isBlank()) return "UNKNOWN";

    return city.strip();
}
```

Đây là bản refactor **từng bước có biến trung gian** (*snapshot variables*). Nó dài hơn một dòng, nhưng có nhiều lợi thế:

1. Mỗi phép truy cập có vị trí cụ thể, dễ đặt breakpoint.
2. Mọi cấp `null` đều được xử lý có chủ đích.
3. Trong mỗi lần thực thi bình thường của đường thành công, mã chỉ gọi mỗi accessor trong chain một lần.
4. Quy tắc nghiệp vụ về `city == null` và `city.isBlank()` được thể hiện tường minh.
5. Nếu sau này cần trả thông báo riêng cho thiếu customer/profile/address, ta biết cần bổ sung nhánh ở đâu.

**Quan trọng:** trước khi so sánh với bản dùng record pattern, phải chốt hợp đồng: thiếu thành phố trả `UNKNOWN`, thành phố có nội dung trả `city.strip()`. Không được vô tình biến thiếu khách hàng thành exception, hoặc xem chuỗi `"   "` như thành phố hợp lệ.

## 4. Thay các bước deconstruct bằng nested record pattern

Record pattern có thể tách cả cấu trúc nhiều tầng:

```java
static String patternCity(Purchase purchase) {
    if (purchase instanceof Purchase(
            var orderId,
            Customer(var customerId,
                    Profile(Address(var city, var street), var email)),
            var quantity)
            && city != null && !city.isBlank()) {
        return city.strip();
    }
    return "UNKNOWN";
}
```

Cách đọc từ ngoài vào trong:

- `purchase instanceof Purchase(...)`: selector phải là một đối tượng `Purchase` khác `null`.
- Component `customer` phải khớp `Customer(...)`; nếu nó bằng `null`, nested record pattern không khớp.
- Component `profile` phải khớp `Profile(...)`; nếu nó bằng `null`, pattern không khớp.
- Component `address` phải khớp `Address(...)`; nếu nó bằng `null`, pattern không khớp.
- Khi đến `Address(var city, var street)`, `city` và `street` được ràng buộc từ component. **`var city` có thể nhận `null`**, nên vẫn cần `city != null` trước khi gọi `isBlank()`.
- `&&` dùng short-circuit: `!city.isBlank()` chỉ chạy nếu toàn bộ nested pattern khớp và `city != null`.
- Nếu mọi điều kiện đều đúng, trả thành phố đã bỏ khoảng trắng ở hai đầu. Mọi trường hợp khác trả `UNKNOWN`.

Ví dụ:

```java
patternCity(new Purchase("O", null, 1)); // UNKNOWN
patternCity(new Purchase("O",
        new Customer("C", new Profile(new Address(null, "Main"), "m")),
        1));                             // UNKNOWN
patternCity(new Purchase("O",
        new Customer("C", new Profile(new Address("  Hue  ", "Main"), "m")),
        1));                             // Hue
```

Mẫu trên không yêu cầu cast kiểu `(Customer)` hoặc `(Profile)`. Trình biên dịch kiểm tra record patterns, các kiểu component và phạm vi của pattern variables.

### var ở component không có nghĩa dynamic typing

Trong `Address(var city, var street)`, compiler suy ra `city` và `street` có kiểu `String` từ khai báo record. Trong `Purchase(..., var quantity)`, `quantity` có kiểu `int`.

Điều này không đồng nghĩa biến `city` chắc chắn khác null. **Kiểu tĩnh và nullability là hai điều khác nhau** đối với tham chiếu Java.

### Tại sao bản trên dài về cú pháp nhưng vẫn hữu ích?

Một accessor chain vốn có **bốn cấp record**, vì vậy một nested pattern tương ứng cũng sâu. Lợi ích không nhất thiết là ít ký tự hơn, mà là **cấu trúc dữ liệu cần khớp được mô tả tại một chỗ**, thay vì nhiều biểu thức truy cập lặp. Khi cấu trúc rất sâu hoặc chỉ cần đúng một field, đôi khi bản biến trung gian ở mục 3 **dễ đọc hơn**; không cần ép mọi chain thành một pattern lớn.

## 5. Null selector, null record con và null component: ba quy tắc khác nhau

| Input/pattern | Khớp không? | Giải thích |
| --- | --- | --- |
| `null instanceof Purchase(...)` | Không | Record pattern ngoài không khớp null |
| `Purchase("O", null, 1)` với nested `Customer(...)` | Không | Record con customer null |
| `Customer("C", null)` với nested `Profile(...)` | Không | Record con profile null |
| `Profile(null, "m")` với nested `Address(...)` | Không | Record con address null |
| `Address(null, "Main")` với `Address(var city, var street)` | Có | `var city` là component pattern, có thể ràng buộc null |
| `Address("  ", "Main")` với `Address(var city, var street)` | Có | Blank là một `String` hợp lệ về kiểu |
| `switch (purchase)` thiếu `case null` khi selector null | Ném NPE | Pattern switch mặc định không tự chuyển null vào `default` |

**Phân biệt quan trọng:** Nested record pattern `Customer(...)` yêu cầu **một instance Customer tồn tại**. Ngược lại, component pattern `var city` đọc một thành phần `String` bên trong `Address` đã khớp, nên vẫn có thể nhận giá trị `null`. Đừng suy luận rằng cả record pattern và mọi thành phần lồng trong nó đều khác null.

Một record pattern có component type pattern không điều kiện đối với kiểu khai báo cũng có thể ràng buộc null trong điều kiện cụ thể theo JLS Java 21. Tuy nhiên, trong case study, dùng `var` và guard `city != null` để biểu thị chủ đích rõ nhất.

### Null check đặt ở đâu?

Với mục tiêu **chỉ cần thành phố có nội dung**, một `instanceof` nested record pattern kết hợp `&& city != null` là đủ.

Với mục tiêu **biết vì sao thiếu dữ liệu**, phải phân biệt từng cấp, chẳng hạn trả `MISSING_CUSTOMER`, `MISSING_PROFILE` hoặc `MISSING_ADDRESS` bằng những case chuyên biệt như phần tiếp theo.

## 6. Dùng pattern switch để chẩn đoán và phân loại dữ liệu lồng sâu

Một ứng dụng có thể cần **error code cụ thể** thay vì `UNKNOWN` cho mọi dữ liệu thiếu. `switch expression` với record patterns và `when` giúp diễn đạt thứ tự kiểm tra rõ ràng:

```java
static String routingDecision(Purchase purchase) {
    return switch (purchase) {
        case null -> "MISSING_PURCHASE";

        case Purchase(var id, var customer, var qty)
                when id == null || id.isBlank() -> "INVALID_ORDER_ID";

        case Purchase(var id, var customer, var qty)
                when customer == null -> "MISSING_CUSTOMER";

        case Purchase(var id, Customer(var cid, var profile), var qty)
                when profile == null -> "MISSING_PROFILE";

        case Purchase(var id,
                      Customer(var cid, Profile(var address, var email)),
                      var qty)
                when address == null -> "MISSING_ADDRESS";

        case Purchase(var id,
                      Customer(var cid,
                               Profile(Address(var city, var street), var email)),
                      var qty)
                when city == null -> "MISSING_CITY";

        case Purchase(var id,
                      Customer(var cid,
                               Profile(Address(var city, var street), var email)),
                      var qty)
                when city.isBlank() -> "BLANK_CITY";

        case Purchase(var id,
                      Customer(var cid,
                               Profile(Address(var city, var street), var email)),
                      var qty)
                when qty <= 0 -> "INVALID_QUANTITY";

        case Purchase(var id,
                      Customer(var cid,
                               Profile(Address(var city, var street), var email)),
                      var qty) ->
                "ROUTE " + id + " -> " + city.strip() + " qty=" + qty;

        case Purchase(var id, var customer, var qty) ->
                "UNSUPPORTED_STRUCTURE";
    };
}
```

Đây là phương thức thành phần trong cùng lớp chứa các record của bài; chương trình đầy đủ có ở mục 9.

### Giải thích thứ tự

1. `case null` xử lý **selector Purchase** null. Nó không xử lý component bên trong một Purchase có thật.
2. `INVALID_ORDER_ID` kiểm tra `id == null || id.isBlank()`; nhờ short-circuit, `isBlank()` không chạy nếu ID null.
3. `MISSING_CUSTOMER` lấy component bằng `var customer` để có thể phát hiện customer null.
4. `MISSING_PROFILE` yêu cầu Customer tồn tại, rồi kiểm tra component profile null.
5. `MISSING_ADDRESS` yêu cầu Customer và Profile tồn tại, rồi kiểm tra address null.
6. `MISSING_CITY` yêu cầu ba record lồng tồn tại, rồi kiểm tra component city null.
7. `BLANK_CITY` dùng `city.isBlank()`. Mã an toàn trong thứ tự này vì các trường hợp `city == null` đã được case trước xử lý. Nếu đảo hai case này, đầu vào có city null có thể ném NPE tại guard.
8. `INVALID_QUANTITY` chỉ xét sau khi cả địa chỉ và city đã qua các bước trước. Đây là **thứ tự ưu tiên báo lỗi** mà ví dụ lựa chọn.
9. Case `ROUTE` khớp dữ liệu đầy đủ, không guard và tạo chuỗi kết quả.
10. Case `UNSUPPORTED_STRUCTURE` là nhánh dự phòng theo cấu trúc ở cuối. Những tình huống được đặc tả đã có các case chuyên biệt; nhánh này bảo vệ nếu cấu trúc bị thay đổi ngoài giả định. Nó **không** được dùng để bỏ qua test những cấp null cần xử lý.

**Không biến mọi case thành một cấu trúc lồng quá dài trong production:** ví dụ cố ý cho thấy độ sâu để dạy cơ chế. Khi nghiệp vụ lớn, cân nhắc hàm kiểm tra từng cấp rồi dùng `switch` trên một **kiểu kết quả đã chuẩn hóa**.

### Khi nhiều điều kiện cùng sai, lỗi nào được ưu tiên?

Với `new Purchase(null, null, 0)`, dispatcher trả `INVALID_ORDER_ID` vì case này đứng trước. Nếu sản phẩm muốn trả `MISSING_CUSTOMER` hoặc tổng hợp nhiều lỗi, phải thiết kế lại logic validation. Java không tự chọn “lỗi nghiêm trọng nhất”.

Mặt khác, `legacyCity` và `patternCity` **chỉ trích xuất city**, không kiểm tra `orderId` hay `quantity`. Vì vậy khi `orderId == null` nhưng địa chỉ đầy đủ, hai hàm trích xuất vẫn có thể trả thành phố, trong khi `routingDecision` trả `INVALID_ORDER_ID`. Đây là **hai trách nhiệm khác nhau**, không phải mâu thuẫn kết quả.

## 7. Dominance và flow scoping khi dùng nested patterns

### Case tổng quát có thể che case sâu hơn

Mẫu cố ý sai:

```java
// Không biên dịch: case Purchase(var customer) ở trước là quá rộng.
return switch (purchase) {
    case null -> "null";
    case Purchase(var id, var customer, var qty) -> "general";
    case Purchase(var id, Customer(var cid, var profile), var qty)
            when profile == null -> "missing profile";
};
```

Case `Purchase(var id, var customer, var qty)` không guard khớp mọi Purchase khác null, bao gồm các giá trị mà case chuyên biệt phía sau có thể xử lý. Compiler Java 21 báo lỗi:

```text
error: this case label is dominated by a preceding case label
```

**Sửa:** đặt case có guard/cấu trúc cụ thể trước, rồi mới đến case rộng không có guard, như `routingDecision`.

Các guard `when` không bảo đảm toàn bộ điều kiện được compiler chứng minh về mặt nghiệp vụ. Khi đổi thứ tự case, phải chạy regression tests với null và blank ở từng cấp; một switch biên dịch được vẫn có thể có NPE trong guard nếu thứ tự kiểm tra null sai.

### Flow scoping cho phép dùng biến pattern ở vế phải &&

```java
static boolean deliverable(Purchase purchase) {
    return purchase instanceof Purchase(
            var orderId,
            Customer(var customerId,
                    Profile(Address(var city, var street), var email)),
            var quantity)
            && city != null && !city.isBlank() && quantity > 0;
}
```

- Chỉ khi phần `instanceof` khớp thì vế phải `&&` mới được đánh giá.
- `city` và `quantity` được ràng buộc trong phạm vi compiler cho phép.
- `city != null` bảo vệ `city.isBlank()`.
- `quantity` là `int`; giá trị có thể bằng 0 hoặc âm nếu constructor không kiểm tra.

Biến pattern **không tự xuất hiện ở mọi nhánh** của chương trình. Viết `input instanceof ... || city.isBlank()` theo kiểu sử dụng biến ngay khi phép khớp sai là một lỗi về phạm vi/definite matching. Luôn suy luận theo hướng đánh giá ngắn mạch của `&&`/`||`.

## 8. Khi nào không nên thay accessor chain bằng record pattern?

Nested record patterns có giá trị lớn khi:

- Domain thực sự được biểu diễn bằng các record lồng nhau.
- Bạn cần kiểm tra **cấu trúc nhiều tầng** để quyết định một nhánh.
- Bạn muốn **nhận nhiều component** trong cùng một lần khớp.
- Mã dùng Java 21+, không cần tương thích mức source thấp hơn.
- Những accessor là đơn giản hoặc đã hiểu rõ hành vi.

Tuy nhiên, không nên refactor máy móc nếu gặp những tình huống sau.

### 8.1. Độ sâu làm mất khả năng đọc

`Purchase(Customer(Profile(Address(...))))` dễ bị dày dấu ngoặc khi nhiều tầng và nhiều component. Với mục tiêu chỉ lấy một city, bản snapshot variables ở mục 3 có thể **rõ ràng hơn**, nhất là khi cần breakpoint hay thông báo lỗi riêng. Có thể tạo một hàm projection như `shippingCity(Purchase purchase)` và tái sử dụng thay vì chép lại pattern sâu trong nhiều service.

### 8.2. Các lớp không phải record

Record patterns là cú pháp deconstruction cho **record classes** phù hợp; Java 21 không tự cung cấp record deconstruction cho mọi POJO/bean bất kỳ. Nếu mô hình đang dùng các lớp truyền thống với `getCustomer()`, bạn có thể refactor thành biến trung gian và null checks hoặc chuyển model sang record khi thay đổi đó có lý do. Không nên đổi toàn bộ entity ORM sang record chỉ để rút ngắn một accessor chain.

### 8.3. Accessor có tác dụng phụ hoặc có thể ném exception

Record cho phép **khai báo accessor tường minh**. Khi record pattern tách component, các accessor liên quan được gọi để lấy dữ liệu; accessor có thể thực hiện logic riêng. Do đó refactor có thể thay đổi **số lần hoặc thứ tự gọi**, nhất là khi một `switch` thử nhiều case với cấu trúc tương tự.

Một ví dụ độc lập đã chạy trên Java 21:

```java
public class RecordAccessorEffectsDemo {
    record Box(String value) {
        static int accesses;

        @Override
        public String value() {
            accesses++;
            return value;
        }
    }

    record Wrapper(Box box) {}

    public static void main(String[] args) {
        Object input = new Wrapper(new Box("ready"));
        if (input instanceof Wrapper(Box(var value))) {
            System.out.println("matched=" + value);
        }
        System.out.println("accesses=" + Box.accesses);
    }
}
```

Chạy bằng:

```bash
javac --release 21 -Xlint:all -Werror RecordAccessorEffectsDemo.java
java RecordAccessorEffectsDemo
```

**Stdout đã kiểm chứng:**

```text
matched=ready
accesses=1
```

Ví dụ chứng minh deconstruction đã gọi **accessor `Box.value()` có logic tùy chỉnh**. Không nên từ một lần chạy này suy ra mọi nested pattern với nhiều case luôn gọi mỗi accessor đúng một lần. Nếu accessor có side effect hoặc phụ thuộc trạng thái bên ngoài, phải kiểm tra hành vi trước và sau refactor bằng test có chủ đích.

### 8.4. API cần phân biệt thiếu dữ liệu và dữ liệu không hợp lệ

`patternCity` trả `UNKNOWN` khi thiếu bất kỳ cấp nào. Nếu API cần phân biệt thiếu customer với city blank, nên trả một **kiểu kết quả có cấu trúc** (ví dụ sealed result với từng loại lỗi) hoặc dùng `routingDecision`, thay vì gộp mọi lỗi vào cùng một chuỗi.

### 8.5. Tính tương thích Java

Khai báo `record` đã final từ Java 16, nhưng **record patterns** final từ Java 21 (JEP 440). Mã của bài không chạy ở mức `--release 17`. Nếu phải hỗ trợ Java 17, vẫn có thể giữ record và dùng accessor snapshot cùng type pattern `instanceof`; không cần dùng preview syntax của các bản trung gian.

## 9. Chương trình Java 21 đầy đủ: so sánh refactor trước và sau

Lưu nguyên tệp **`RecordAccessorRefactorDemo.java`**. Chương trình kiểm thử 14 trường hợp, gồm null ở từng cấp, city rỗng/blank, ID không hợp lệ, quantity biên và dữ liệu hợp lệ. Ba hàm được kiểm chứng: `legacyCity` (đọc từng cấp), `patternCity` (nested record pattern) và `routingDecision` (pattern switch kèm guard).

```java
public class RecordAccessorRefactorDemo {
    record Address(String city, String street) {}
    record Profile(Address address, String email) {}
    record Customer(String id, Profile profile) {}
    record Purchase(String orderId, Customer customer, int quantity) {}
    record Sample(String label, Purchase input, String city, String route) {}

    private static int checks;

    static Purchase sample(String orderId, String city, int quantity) {
        return new Purchase(orderId,
                new Customer("C-1",
                        new Profile(new Address(city, "Main St"), "user@example.com")),
                quantity);
    }

    static String legacyCity(Purchase purchase) {
        if (purchase == null) return "UNKNOWN";
        Customer customer = purchase.customer();
        if (customer == null) return "UNKNOWN";
        Profile profile = customer.profile();
        if (profile == null) return "UNKNOWN";
        Address address = profile.address();
        if (address == null) return "UNKNOWN";
        String city = address.city();
        if (city == null || city.isBlank()) return "UNKNOWN";
        return city.strip();
    }

    static String patternCity(Purchase purchase) {
        if (purchase instanceof Purchase(
                var orderId,
                Customer(var customerId,
                        Profile(Address(var city, var street), var email)),
                var quantity)
                && city != null && !city.isBlank()) {
            return city.strip();
        }
        return "UNKNOWN";
    }

    static String routingDecision(Purchase purchase) {
        return switch (purchase) {
            case null -> "MISSING_PURCHASE";
            case Purchase(var id, var customer, var qty)
                    when id == null || id.isBlank() -> "INVALID_ORDER_ID";
            case Purchase(var id, var customer, var qty)
                    when customer == null -> "MISSING_CUSTOMER";
            case Purchase(var id, Customer(var cid, var profile), var qty)
                    when profile == null -> "MISSING_PROFILE";
            case Purchase(var id,
                          Customer(var cid, Profile(var address, var email)),
                          var qty)
                    when address == null -> "MISSING_ADDRESS";
            case Purchase(var id,
                          Customer(var cid,
                                   Profile(Address(var city, var street), var email)),
                          var qty)
                    when city == null -> "MISSING_CITY";
            case Purchase(var id,
                          Customer(var cid,
                                   Profile(Address(var city, var street), var email)),
                          var qty)
                    when city.isBlank() -> "BLANK_CITY";
            case Purchase(var id,
                          Customer(var cid,
                                   Profile(Address(var city, var street), var email)),
                          var qty)
                    when qty <= 0 -> "INVALID_QUANTITY";
            case Purchase(var id,
                          Customer(var cid,
                                   Profile(Address(var city, var street), var email)),
                          var qty) ->
                    "ROUTE " + id + " -> " + city.strip() + " qty=" + qty;
            case Purchase(var id, var customer, var qty) -> "UNSUPPORTED_STRUCTURE";
        };
    }

    static String unsafeCity(Purchase purchase) {
        return purchase.customer().profile().address().city().strip();
    }

    private static void expect(String label, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        checks++;
    }

    public static void main(String[] args) {
        Sample[] cases = {
            new Sample("null-selector", null, "UNKNOWN", "MISSING_PURCHASE"),
            new Sample("null-id", sample(null, "Hue", 1), "Hue", "INVALID_ORDER_ID"),
            new Sample("blank-id", sample("  ", "Hue", 1), "Hue", "INVALID_ORDER_ID"),
            new Sample("null-customer", new Purchase("O-1", null, 1),
                    "UNKNOWN", "MISSING_CUSTOMER"),
            new Sample("null-profile", new Purchase("O-2", new Customer("C", null), 1),
                    "UNKNOWN", "MISSING_PROFILE"),
            new Sample("null-address", new Purchase("O-3",
                    new Customer("C", new Profile(null, "mail")), 1),
                    "UNKNOWN", "MISSING_ADDRESS"),
            new Sample("null-city", sample("O-4", null, 1),
                    "UNKNOWN", "MISSING_CITY"),
            new Sample("empty-city", sample("O-5", "", 1),
                    "UNKNOWN", "BLANK_CITY"),
            new Sample("blank-city", sample("O-6", " \t ", 1),
                    "UNKNOWN", "BLANK_CITY"),
            new Sample("valid-city", sample("O-7", "  Ha Noi  ", 2),
                    "Ha Noi", "ROUTE O-7 -> Ha Noi qty=2"),
            new Sample("valid-other-city", sample("O-8", "Da Nang", 1),
                    "Da Nang", "ROUTE O-8 -> Da Nang qty=1"),
            new Sample("qty-zero", sample("O-9", "Hue", 0),
                    "Hue", "INVALID_QUANTITY"),
            new Sample("qty-negative", sample("O-10", "Hue", -1),
                    "Hue", "INVALID_QUANTITY"),
            new Sample("qty-one", sample("O-11", "Hue", 1),
                    "Hue", "ROUTE O-11 -> Hue qty=1")
        };

        for (Sample test : cases) {
            expect("legacy-" + test.label(), test.city(), legacyCity(test.input()));
            expect("pattern-" + test.label(), test.city(), patternCity(test.input()));
            expect("route-" + test.label(), test.route(), routingDecision(test.input()));
        }

        System.out.println("PASS cases=" + cases.length);
        System.out.println("PASS assertions=" + checks);
        System.out.println("city=" + patternCity(sample("O-7", "  Ha Noi  ", 2)));
        System.out.println("route=" + routingDecision(sample("O-7", "  Ha Noi  ", 2)));
        System.out.println("nested-null=" + routingDecision(new Purchase(
                "O-2", new Customer("C", null), 1)));
        System.out.println("selector-null=" + routingDecision(null));

        try {
            unsafeCity(new Purchase("NPE", null, 1));
            throw new AssertionError("Expected NPE on null customer");
        } catch (NullPointerException expected) {
            System.out.println("unsafe-chain=NPE");
        }
        try {
            unsafeCity(sample("NPE", null, 1));
            throw new AssertionError("Expected NPE on null leaf city");
        } catch (NullPointerException expected) {
            System.out.println("unsafe-leaf=NPE");
        }
    }
}
```

Biên dịch và chạy trên JDK 21 hoặc compiler mới hơn có hỗ trợ `--release 21`:

```bash
javac --release 21 -Xlint:all -Werror -encoding UTF-8 RecordAccessorRefactorDemo.java
java RecordAccessorRefactorDemo
```

**Stdout chính xác đã kiểm chứng:**

```text
PASS cases=14
PASS assertions=42
city=Ha Noi
route=ROUTE O-7 -> Ha Noi qty=2
nested-null=MISSING_PROFILE
selector-null=MISSING_PURCHASE
unsafe-chain=NPE
unsafe-leaf=NPE
```

### Tại sao in PASS?

Mỗi `Sample` có ba kết quả kỳ vọng được định nghĩa độc lập:

1. `legacyCity(test.input())` phải bằng `test.city()`.
2. `patternCity(test.input())` cũng phải bằng `test.city()`.
3. `routingDecision(test.input())` phải bằng `test.route()`.

Hàm `expect` ném `AssertionError` nếu bất kỳ kết quả thực tế nào khác oracle. Có **14 Sample × 3 assert = 42 assert**. Các dòng PASS chỉ xuất hiện sau khi tất cả đều chạy thành công.

Mã cũng chủ động gọi `unsafeCity` trong hai trường hợp lỗi khác nhau: thiếu record customer và thiếu thành phần city. Hai NPE được bắt để minh họa nguyên nhân, **không khuyến nghị bắt NPE rộng trong code sản phẩm**.

### Một số ca quan trọng

| Ca | Kỳ vọng từ hai hàm lấy city | Kỳ vọng từ routingDecision |
| --- | --- | --- |
| `purchase == null` | `UNKNOWN` | `MISSING_PURCHASE` |
| `orderId == null`, địa chỉ tốt | Tên thành phố | `INVALID_ORDER_ID` |
| `customer == null` | `UNKNOWN` | `MISSING_CUSTOMER` |
| `profile == null` | `UNKNOWN` | `MISSING_PROFILE` |
| `address == null` | `UNKNOWN` | `MISSING_ADDRESS` |
| `city == null` | `UNKNOWN` | `MISSING_CITY` |
| `city == ""` hoặc blank | `UNKNOWN` | `BLANK_CITY` |
| `city == "  Ha Noi  "` | `Ha Noi` | `ROUTE O-7 -> Ha Noi qty=2` |
| `quantity == 0`, thành phố tốt | Tên thành phố | `INVALID_QUANTITY` |

Bảng cho thấy vì sao cần phân biệt **trích xuất dữ liệu** và **validate toàn bộ yêu cầu** khi refactor. Hai phương thức có thể dùng cùng các record patterns nhưng phục vụ hai hợp đồng khác nhau.

## 10. Khi nào nên đưa kiểm tra null vào constructor record?

Nếu nghiệp vụ **không bao giờ cho phép** một `Purchase` thiếu khách hàng, hồ sơ hoặc địa chỉ, có thể đặt invariant khi tạo dữ liệu:

```java
record StrictCustomer(String id, Profile profile) {
    StrictCustomer {
        java.util.Objects.requireNonNull(profile, "profile");
    }
}

record StrictPurchase(String orderId, StrictCustomer customer, int quantity) {
    StrictPurchase {
        java.util.Objects.requireNonNull(customer, "customer");
    }
}
```

Đây là ví dụ **cấu trúc cần đặt trong lớp có sẵn định nghĩa `Profile`**, không phải tệp Java độc lập. Với model cho phép null như dữ liệu “chưa điền”, thêm `requireNonNull` có thể **thay đổi contract**, nên không được áp dụng trước khi hiểu nguồn dữ liệu.

Có hai lựa chọn hợp lệ:

- **Nullable domain:** null là trạng thái có nghĩa; giữ record cho phép null và xử lý trong parser/dispatcher/service.
- **Validated domain:** thiếu thành phần là lỗi đầu vào; từ chối ngay tại constructor/factory, khiến các tầng xử lý sau có bất biến mạnh hơn.

Không nên vừa cho rằng null hợp lệ trong dữ liệu lưu trữ, vừa mặc định mọi nested pattern sẽ khớp và mọi accessor luôn an toàn.

## 11. Quy trình refactor thực tế

Khi gặp accessor chain dài trong code đang vận hành, có thể làm theo trình tự sau:

1. **Xác định kết quả nghiệp vụ.** Chuỗi dùng để hiển thị, routing, logging hay validation? Thành phố null có trả default, ném lỗi hay được bỏ qua?
2. **Vẽ sơ đồ từng cấp.** Ghi kiểu tĩnh `Purchase → Customer → Profile → Address → String` và cấp nào có thể null.
3. **Tách biểu thức bằng biến trung gian** như `legacyCity` ở mục 3. Việc này giúp nhìn rõ thứ tự dereference và tạo một baseline dễ test.
4. **Viết test oracle trước.** Ít nhất thử selector null, từng record con null, component lá null, chuỗi blank và dữ liệu hợp lệ.
5. **Kiểm tra phiên bản Java.** Nested record patterns final từ Java 21; với source 17, dừng ở biến trung gian hoặc accessor helper.
6. **Thay bằng record pattern nếu thật sự cải thiện khả năng đọc.** Tách cấu trúc record ở vị trí phù hợp, không cố deconstruct những thành phần không cần thiết chỉ để dùng cú pháp mới.
7. **Bổ sung guard cho nullable components.** `var city` không tự bảo đảm non-null; dùng `city != null && !city.isBlank()` đúng thứ tự.
8. **Giữ riêng các quy tắc validation ngoài accessor chain.** ID trống, quantity không dương và quyền giao hàng không nên vô tình bị gộp vào một null guard nếu chúng có mã lỗi khác nhau.
9. **Kiểm tra accessor behavior.** Nếu accessor bị override, có side effect, throw hoặc phụ thuộc trạng thái, so sánh số lần và thứ tự gọi trước/sau.
10. **Chạy compiler và regression tests.** Kiểm tra `when` dominance, null selector, null component, kết quả trích xuất và kết quả routing. Trong dự án lớn, dùng thêm JUnit và coverage tool.
11. **Review mức độ dễ đọc.** Nếu nested pattern lớn hơn rất nhiều so với code cũ, có thể giữ accessor snapshot hoặc tạo domain projection method thay vì cố rút ngắn bằng mọi giá.

Một refactor tốt phải **giảm nguy cơ lỗi và làm ý định rõ hơn**. Việc đổi từ accessor chain sang pattern không phải mục đích tự thân.

## 12. Lỗi thường gặp khi refactor accessor chain

1. **Cho rằng có `instanceof` là mọi cấp đã non-null.** Chỉ record object cần khớp khác null ở cấp đó; component `var city` vẫn có thể null.
2. **Nhầm null ở selector với null ở component.** `null instanceof Purchase(...)` false, còn `Purchase(..., Address(null,...),...)` có thể khớp pattern và ràng buộc city null.
3. **Xóa null check ở lá.** `city.strip()` sẽ ném NPE nếu city là null, bất kể các record cha đều tồn tại.
4. **Đặt guard `city.isBlank()` trước guard `city == null`.** Trong `switch`, một guard có thể ném NPE trước khi Java xét case tiếp theo.
5. **Dùng `||` sai hướng với biến pattern.** `input instanceof Purchase(...) || city.isBlank()` không đảm bảo city đã được ràng buộc khi vế phải chạy; cần đọc quy tắc flow scoping.
6. **Đặt case rộng trước case sâu có `when`.** Case rộng không guard có thể che case đặc biệt, dẫn đến compiler error dominated case.
7. **Giữ cú pháp pattern quá sâu khó đọc.** Các tầng ngoặc lồng làm bảo trì khó khăn nếu chỉ cần một field. Có thể dùng snapshot variables/hàm projection.
8. **Dùng record pattern với POJO không phải record.** Java 21 không tự deconstruct mọi lớp tùy ý; phải dùng accessor hoặc model phù hợp.
9. **Mặc định record accessor luôn thuần.** Có thể override accessor và thêm code; thay đổi cấu trúc match có thể đổi hành vi khi accessor có side effect.
10. **Thay đổi chính sách báo lỗi khi refactor.** Trả `UNKNOWN` cho mọi thiếu dữ liệu khác với `MISSING_PROFILE`/`MISSING_ADDRESS` riêng.
11. **Cho rằng record constructor mặc định cấm null.** Record có thể chứa component tham chiếu null nếu không có invariant.
12. **Dùng `catch NullPointerException` để che mọi chain lỗi.** Dễ nuốt lỗi lập trình không thuộc dữ liệu thiếu.
13. **Lạm dụng `Optional` chỉ để né null mà không rõ contract.** `Optional.ofNullable` có thể giúp biểu diễn vắng mặt, nhưng chuỗi `map` dài không tự giải quyết việc phải phân biệt nhiều nguyên nhân thiếu.
14. **Chạy record patterns Java 21 dưới `--release 17`.** `record` có thể dùng ở Java 17, nhưng record patterns yêu cầu Java 21 để dùng như tính năng final.

## 13. Bài tập tự luyện

**Bài 1.** Với `new Purchase("O", null, 1)`, tại sao pattern `Purchase(var id, Customer(...), var quantity)` không khớp?

*Đáp án:* Component customer bằng null, còn nested record pattern `Customer(...)` yêu cầu có một instance Customer khác null để deconstruct. Mẫu `Purchase(var id, var customer, var quantity)` vẫn có thể khớp và ràng buộc `customer == null`.

**Bài 2.** Với `new Address(null, "Main")`, liệu `Address(var city, var street)` có thể khớp không?

*Đáp án:* Có. `var city` là component pattern nhận giá trị theo kiểu component đã khai báo và có thể ràng buộc null. Nếu sau đó gọi `city.isBlank()` phải kiểm tra null trước.

**Bài 3.** Tại sao `patternCity` dùng `&& city != null && !city.isBlank()` mà không gọi `city.isBlank()` ngay sau record pattern?

*Đáp án:* Vì pattern có thể thành công khi thành phần city null; `&&` bảo đảm `isBlank()` chỉ chạy sau khi `city != null` đúng.

**Bài 4.** Nếu đồng thời `orderId == null` và `customer == null`, `routingDecision` trả gì?

*Đáp án:* `INVALID_ORDER_ID` vì case kiểm tra ID đứng trước case kiểm tra customer. Đây là quy tắc ưu tiên báo lỗi do tác giả chọn; nếu API muốn ưu tiên khác, phải sắp lại case và test.

**Bài 5.** Có nên dùng `Purchase(Customer(Profile(Address(var city,...))))` trong mọi hàm lấy city không?

*Đáp án:* Không. Nếu pattern quá sâu hoặc mã chỉ cần một giá trị, dùng snapshot variables hoặc domain projection helper thường dễ bảo trì hơn. Pattern phù hợp khi muốn thể hiện cấu trúc và điều kiện match một cách rõ ràng.

**Bài 6.** Vì sao một refactor có thể thay đổi hành vi nếu record accessor được override?

*Đáp án:* Deconstruction gọi các accessor để lấy component. Nếu accessor có side effect, truy cập I/O hoặc trả giá trị phụ thuộc trạng thái, số lần/thứ tự gọi ở một pattern switch có thể khác so với chuỗi accessor cũ. Phải có test và review những chỗ đó.

**Bài 7.** Khi dự án build với `--release 17`, hướng chuyển accessor chain nào là khả thi mà không bật preview?

*Đáp án:* Giữ `record` và dùng accessor với biến trung gian/null check; hoặc tạo helper/accessor tổng hợp theo contract. Record patterns final ở Java 21 nên không dùng trực tiếp trong source level 17.

**Bài 8.** Nếu cần trả cả thành phố và mã khách hàng, record pattern có lợi thế gì?

*Đáp án:* Có thể ràng buộc `customerId` và `city` trong cùng pattern sau khi các record lồng khớp, không cần gọi lại nhiều accessor; vẫn phải kiểm tra nullable components và business rule. Khi nhiều field/nhánh phức tạp, nên xét record kết quả riêng thay vì một pattern quá dài.

## 14. Tài liệu chính thức

- [JEP 395 – Records (Java 16)](https://openjdk.org/jeps/395)
- [JEP 394 – Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 440 – Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 – Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 – Patterns `14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java Language Specification 21 – Records `8.10](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10)
- [Java Language Specification 21 – Scope of pattern variables `6.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
