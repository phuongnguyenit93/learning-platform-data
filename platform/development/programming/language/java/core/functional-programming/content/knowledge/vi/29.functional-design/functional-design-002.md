# Chia nghiệp vụ thành các hàm nhỏ có đầu vào và đầu ra rõ ràng trong Java

## 1. Vấn đề: một phương thức vừa làm tất cả thường khó hiểu và khó kiểm thử

Khi triển khai một quy trình nghiệp vụ, chúng ta thường cần nhiều việc khác nhau: chuẩn hóa dữ liệu, kiểm tra điều kiện, tính toán, quyết định chính sách, ghi dữ liệu và trả kết quả. Nếu nhét tất cả vào một phương thức dài, người đọc khó biết **dữ liệu nào đi vào, quy tắc nào được áp dụng, kết quả nào đi ra và bước nào có tác dụng phụ**.

Ví dụ một phương thức `checkout()` có thể vừa đọc database, vừa tính giảm giá, vừa tạo hóa đơn, vừa ghi log, vừa gửi thông báo. Những thao tác này có loại phụ thuộc và cách kiểm thử khác nhau. Thiết kế theo hàm hướng tới việc chia chúng thành **những phép biến đổi có hợp đồng rõ ràng**, rồi kết hợp thành luồng nghiệp vụ tổng thể.

Mục tiêu của bài:

1. Nhận diện các **bước nghiệp vụ có ý nghĩa riêng**, không cắt phương thức một cách máy móc theo số dòng.
2. Xác định **input**, **output**, điều kiện trước/sau và lỗi có thể phát sinh của mỗi hàm.
3. Ưu tiên **hàm thuần khiết** (*pure functions*) cho phần tính toán và quyết định có thể tách khỏi I/O.
4. Tránh mutation và các phụ thuộc ẩn khiến việc gọi hàm có kết quả bất ngờ.
5. Kết hợp những hàm nhỏ thành pipeline hoặc orchestrator **dễ đọc, dễ test, dễ thay đổi**.
6. Đặt việc ghi database, gửi thông báo và gọi dịch vụ ngoài ở **ranh giới tác dụng phụ** rõ ràng.

**Không phải cứ nhiều hàm là thiết kế tốt.** Một hàm nhỏ tốt phải có **một trách nhiệm có tên**, nhận dữ liệu đủ để làm nhiệm vụ của nó và trả một giá trị/hiệu ứng có ý nghĩa.

## 2. Hàm có đầu vào và đầu ra rõ ràng nghĩa là gì?

Một hàm thường được mô tả bằng ánh xạ:

~~~text
input (dữ liệu/điều kiện) ──► function ──► output (giá trị/kết quả)
~~~

Ví dụ:

~~~java
static int lineTotal(int unitPrice, int quantity) {
    return Math.multiplyExact(unitPrice, quantity);
}
~~~

Đây là **phương thức minh họa** có hai input `int` và một output `int`. Với `unitPrice=12`, `quantity=3`, nó trả `36`. `Math.multiplyExact` còn biểu diễn rõ quy tắc **ném `ArithmeticException` nếu phép nhân tràn phạm vi `int`**, thay vì âm thầm tạo giá trị tràn.

Một hợp đồng hàm nên trả lời được:

| Câu hỏi | Điều cần rõ |
|---|---|
| Hàm nhận gì? | Kiểu tham số, ý nghĩa và đơn vị dữ liệu |
| Hàm trả gì? | Kiểu kết quả, ý nghĩa nghiệp vụ, có thể rỗng/null không |
| Điều kiện trước? | Input hợp lệ, dữ liệu bắt buộc, miền giá trị |
| Điều kiện sau? | Kết quả phản ánh quy tắc nào, bất biến nào được giữ |
| Có thay đổi trạng thái không? | Có mutate tham số/field, ghi DB, I/O hay không |
| Có thể lỗi thế nào? | Exception, result kiểu lỗi hoặc nhánh vắng dữ liệu |
| Có phụ thuộc ngoài không? | Đồng hồ, random, cấu hình toàn cục, service, network |
| Có an toàn để chạy lại không? | Cùng input có cùng output, có tạo tác dụng phụ lặp không |

Không phải mọi hàm đều bắt buộc chỉ dùng primitive. Ngược lại, **một kiểu dữ liệu đầu vào được đặt tên rõ** thường tốt hơn phương thức nhận quá nhiều tham số rời rạc như `apply(int a, int b, boolean x, int y, String z)`.

## 3. Đầu vào/đầu ra kiểu dữ liệu có ý nghĩa nghiệp vụ

### 3.1. Tránh “primitive obsession”

Nếu một nghiệp vụ sử dụng tiền, số lượng và tỷ lệ giảm giá, tất cả cùng là `int` nhưng **không mang cùng ý nghĩa**. Phương thức sau dễ truyền nhầm thứ tự:

~~~java
static int calculate(int a, int b, int c, int d) {
    return a * b - c + d;
}
~~~

Người gọi khó biết `a` là đơn giá hay số lượng, `c` là giảm giá hay phí vận chuyển.

Cải thiện bằng tên hàm, tên tham số và các kiểu dữ liệu:

~~~java
record Line(String sku, int unitPrice, int quantity) {}

static int subtotal(Line line) {
    return Math.multiplyExact(line.unitPrice(), line.quantity());
}
~~~

Ở đây `Line` biểu đạt một mặt hàng, còn `subtotal` có mục đích rõ. Cần chú ý rằng record không tự động validate `quantity > 0` hay `unitPrice >= 0`; ràng buộc đó nên được mã hóa ở constructor hoặc nơi kiểm tra dữ liệu.

### 3.2. Record giúp đầu ra trở nên minh bạch

Một phép tính báo giá có thể trả nhiều đại lượng:

~~~java
record Quote(int subtotal, int discount, int shipping, int total) {}
~~~

Thay vì trả một mảng `int[]` khiến caller phải nhớ vị trí `0,1,2,3`, record cho những accessor có tên `subtotal()`, `discount()`, `shipping()`, `total()`.

Tuy nhiên, **record không tự làm mọi object bất biến sâu**. Record chỉ giữ các component trong trường `final`; nếu component là `List<MutableItem>`, caller vẫn có thể thay đổi phần tử. Muốn model bất biến, cần kiểm tra **toàn bộ object graph và defensive copying** khi cần.

## 4. Một ví dụ nghiệp vụ: tính báo giá có nhiều bước độc lập

Giả sử yêu cầu:

- Mỗi dòng hàng có đơn giá và số lượng.
- `subtotal` là tổng `unitPrice × quantity`.
- Khách thành viên được giảm **10% subtotal**, làm tròn xuống theo phép chia nguyên cho các giá trị không âm.
- Phí giao hàng là **15** nếu giá sau giảm **nhỏ hơn 100**; ngược lại là **0**.
- Tổng thanh toán bằng `subtotal - discount + shipping`.
- Dữ liệu đầu vào phải hợp lệ; quy trình tính báo giá **không ghi database hoặc sửa dòng hàng**.

Có thể tách thành các bước:

~~~text
Order ──► subtotal ──► discount ──► afterDiscount ──► shipping
             │            │                              │
             └────────────┴───────────► Quote ◄──────────┘
~~~

Thay vì trộn tất cả vào một lambda lớn, mỗi quy tắc có tên và hợp đồng:

| Hàm | Input | Output | Trách nhiệm |
|---|---|---|---|
| `lineCost(Line)` | Một dòng hàng hợp lệ | `int` | Tính tiền một dòng |
| `subtotal(Order)` | Danh sách dòng hàng | `int` | Cộng tiền các dòng |
| `discount(int, boolean)` | Subtotal, trạng thái thành viên | `int` | Quy tắc ưu đãi |
| `shipping(int)` | Tổng sau giảm | `int` | Quy tắc phí vận chuyển |
| `quote(Order, boolean)` | Order và trạng thái thành viên | `Quote` | Phối hợp những phép tính thành kết quả |

Sơ đồ thể hiện **sự phụ thuộc dữ liệu**, không bắt buộc chương trình phải dùng một API Stream cho tất cả bước. Một orchestrator rõ thứ tự gọi hàm thường dễ hiểu hơn một chuỗi `map` lồng nhau.

## 5. Chương trình Java 17 hoàn chỉnh: hàm nhỏ, hợp đồng rõ và kết quả bất biến

Lưu file **`FunctionalOrderPricingDemo.java`**:

~~~java
import java.util.List;
import java.util.Objects;

public class FunctionalOrderPricingDemo {
    record Line(String sku, int unitPrice, int quantity) {
        Line {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank()) {
                throw new IllegalArgumentException("sku is blank");
            }
            if (unitPrice < 0 || quantity <= 0) {
                throw new IllegalArgumentException("invalid price or quantity");
            }
        }
    }

    record Order(List<Line> lines) {
        Order {
            lines = List.copyOf(lines);
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("order is empty");
            }
        }
    }

    record Quote(int subtotal, int discount, int shipping, int total) {}

    static int lineCost(Line line) {
        return Math.multiplyExact(line.unitPrice(), line.quantity());
    }

    static int subtotal(Order order) {
        return order.lines().stream()
                .mapToInt(FunctionalOrderPricingDemo::lineCost)
                .reduce(0, Math::addExact);
    }

    static int discount(int subtotal, boolean member) {
        return member ? subtotal / 10 : 0;
    }

    static int shipping(int afterDiscount) {
        return afterDiscount < 100 ? 15 : 0;
    }

    static Quote quote(Order order, boolean member) {
        int sub = subtotal(order);
        int off = discount(sub, member);
        int afterDiscount = Math.subtractExact(sub, off);
        int delivery = shipping(afterDiscount);
        int total = Math.addExact(afterDiscount, delivery);
        return new Quote(sub, off, delivery, total);
    }

    public static void main(String[] args) {
        Order order = new Order(List.of(
                new Line("pen", 12, 3),
                new Line("book", 25, 2)
        ));

        Quote regular = quote(order, false);
        Quote member = quote(order, true);

        System.out.println("regular=" + regular);
        System.out.println("member=" + member);
        System.out.println("lines=" + order.lines());
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac FunctionalOrderPricingDemo.java
java FunctionalOrderPricingDemo
~~~

Stdout:

~~~text
regular=Quote[subtotal=86, discount=0, shipping=15, total=101]
member=Quote[subtotal=86, discount=8, shipping=15, total=93]
lines=[Line[sku=pen, unitPrice=12, quantity=3], Line[sku=book, unitPrice=25, quantity=2]]
~~~

**Diễn giải các bước:**

1. `lineCost(pen) = 12 × 3 = 36`; `lineCost(book) = 25 × 2 = 50`.
2. `subtotal(order)` cộng hai dòng, được `86`.
3. Với khách thường, `discount(86, false) = 0`. Với thành viên, `discount(86, true) = 86 / 10 = 8` do chia nguyên.
4. Cả `86` và `78` sau giảm đều nhỏ hơn ngưỡng `100`, nên phí vận chuyển là `15`.
5. Tổng thường bằng `86 - 0 + 15 = 101`; tổng thành viên bằng `86 - 8 + 15 = 93`.
6. `quote()` chỉ phối hợp các phép tính và trả một `Quote` mới. Nó không ghi file, không gọi database, không sửa `Order`.
7. Constructor của `Order` dùng `List.copyOf` để tạo danh sách unmodifiable và ngăn thay đổi cấu trúc đầu vào từ bên ngoài. Vì `Line` chứa `String` và primitive fields, các phần tử trong ví dụ có trạng thái value ổn định.
8. `Math.multiplyExact`, `Math.addExact` và `Math.subtractExact` giúp phát hiện overflow của các phép số nguyên quan trọng. Quy tắc giảm giá cũng cần kiểm soát miền giá trị; trong ví dụ input được validate và giá trị nhỏ nên không phát sinh lỗi tràn.

**Thiết kế có thể cải thiện tiếp:** trong ứng dụng tiền tệ thực tế, hãy xác định rõ **đơn vị tiền nhỏ nhất**, tỷ lệ, chính sách làm tròn, thuế, chiết khấu đồng thời và giới hạn miền giá trị. Có thể dùng `long` hoặc `BigDecimal` theo nghiệp vụ. Các quyết định đó thuộc **hợp đồng** của hàm, không nên để suy luận từ một biểu thức toán học ngắn.

## 6. Vì sao hàm nhỏ làm việc kiểm thử hiệu quả hơn?

Khi mỗi bước có input/output tường minh, có thể kiểm thử độc lập:

| Quy tắc | Input kiểm thử | Kỳ vọng |
|---|---|---|
| `lineCost` | Đơn giá `12`, số lượng `3` | `36` |
| `subtotal` | Hai dòng tiền `36` và `50` | `86` |
| `discount` | `86`, thành viên | `8` |
| `discount` | `86`, không thành viên | `0` |
| `shipping` | `78` | `15` |
| `shipping` | `100` | `0` |
| `quote` | Đơn hàng mẫu, thành viên | `Quote(86,8,15,93)` |
| Validation | Số lượng `0` | Ném `IllegalArgumentException` |
| Overflow | Phép nhân vượt `int` | Ném `ArithmeticException` |

Ở thiết kế “một phương thức làm tất cả”, muốn kiểm thử một quy tắc phí vận chuyển có thể phải mock repository, tạo giả database hoặc đi qua nhiều nhánh không liên quan. Với `shipping(int)`, kiểm thử ngay ở giá trị biên `99` và `100` là đủ để chứng minh riêng chính sách ngưỡng.

**Đơn vị kiểm thử lý tưởng là hành vi có ý nghĩa**, không phải chỉ là “mỗi dòng một hàm”. Nếu tách `return x + 1;` thành ba helper vô danh và buộc người đọc nhảy qua nhiều file, thiết kế có thể tệ hơn.

### 6.1. Kiểm thử quy tắc ở giá trị biên

Ví dụ quy tắc phí giao hàng:

~~~java
static int shipping(int afterDiscount) {
    return afterDiscount < 100 ? 15 : 0;
}
~~~

Các ca `99`, `100` và `101` phân biệt rõ nhánh “nhỏ hơn” với “nhỏ hơn hoặc bằng”. Nếu viết quy tắc chung chung “miễn phí vận chuyển khi gần 100” mà không có điều kiện chính xác, các nhóm triển khai/test rất dễ hiểu khác nhau.

**Với một hàm cụ thể**, ngoài input/output cần định nghĩa **biên**, dữ liệu không hợp lệ, cách làm tròn và lỗi: ví dụ có cho phép `afterDiscount < 0` không, có cần throw exception không, hay sẽ được bảo đảm bởi caller?

## 7. Tách chuẩn hóa, kiểm tra và quyết định thành ba loại hàm

Ở bài toán nhận đăng ký, ta có thể phân tách:

1. **Normalize:** chuyển input thô thành dữ liệu có dạng chuẩn.
2. **Validate:** trả những lỗi hợp lệ/không hợp lệ, không ghi log hoặc ném ngoại lệ cho mọi lỗi nghiệp vụ thông thường.
3. **Decide:** dựa trên kết quả đã kiểm tra để tạo quyết định.

Ví dụ dữ liệu đi qua:

~~~text
Registration raw
    │
    ▼ normalize(raw) ──────────► Registration normalized
                                   │
                                   ▼ validate(normalized)
                               List<String> errors
                                   │
                                   ▼ decide(normalized, errors)
                                  Decision
~~~

Lợi ích: quy tắc trim/lowercase không bị trộn với quy tắc giới hạn tuổi hoặc hiệu ứng ghi database. Khi chính sách thay đổi, có thể sửa/test một bước riêng.

### 7.1. Phân biệt lỗi lập trình và lỗi nghiệp vụ

Một dữ liệu có email sai định dạng hoặc tuổi không đủ có thể được biểu diễn bằng **kết quả validation** chứa lỗi. Điều đó khác với lỗi lập trình như đưa vào một đối tượng `null` không được hợp đồng cho phép, có thể cần `Objects.requireNonNull` hoặc ngoại lệ.

Không có một quy định toàn cục rằng mọi lỗi nghiệp vụ phải trả `List<String>`. Có thể dùng enum, record `ValidationError`, kiểu result tùy dự án, hoặc exception khi phù hợp. Điều quan trọng là **hợp đồng của hàm nhất quán**, không buộc caller suy đoán một giá trị `null` mang nghĩa gì.

## 8. Chương trình Java 17 hoàn chỉnh: chuẩn hóa và kiểm tra không cần I/O

Lưu file **`FunctionalRegistrationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class FunctionalRegistrationDemo {
    record Registration(String username, String email, int age) {}

    record Decision(Registration normalized, List<String> errors) {
        Decision {
            errors = List.copyOf(errors);
        }

        boolean accepted() {
            return errors.isEmpty();
        }
    }

    static Registration normalize(Registration input) {
        Objects.requireNonNull(input, "input");
        Objects.requireNonNull(input.username(), "username");
        Objects.requireNonNull(input.email(), "email");

        return new Registration(
                input.username().strip(),
                input.email().strip().toLowerCase(Locale.ROOT),
                input.age()
        );
    }

    static List<String> validate(Registration value) {
        List<String> errors = new ArrayList<>();

        if (value.username().isBlank()) {
            errors.add("username.required");
        }
        if (!value.email().contains("@")) {
            errors.add("email.invalid");
        }
        if (value.age() < 18) {
            errors.add("age.under18");
        }
        return List.copyOf(errors);
    }

    static Decision decide(Registration input) {
        Registration normalized = normalize(input);
        List<String> errors = validate(normalized);
        return new Decision(normalized, errors);
    }

    public static void main(String[] args) {
        Decision valid = decide(
                new Registration("  Mai  ", " Mai@Example.COM ", 20));
        Decision invalid = decide(
                new Registration("   ", "invalid", 16));

        System.out.println("valid=" + valid);
        System.out.println("accepted=" + valid.accepted());
        System.out.println("invalid=" + invalid);
        System.out.println("accepted=" + invalid.accepted());
    }
}
~~~

Chạy:

~~~bash
javac FunctionalRegistrationDemo.java
java FunctionalRegistrationDemo
~~~

Stdout:

~~~text
valid=Decision[normalized=Registration[username=Mai, email=mai@example.com, age=20], errors=[]]
accepted=true
invalid=Decision[normalized=Registration[username=, email=invalid, age=16], errors=[username.required, email.invalid, age.under18]]
accepted=false
~~~

**Vì sao cách chia hợp lý?**

- `normalize` chỉ chuẩn hóa cách biểu diễn. Nó **không kiểm tra đầy đủ** email hoặc tuổi.
- `validate` xử lý những quy tắc nghiệp vụ có thể phát biểu trên một `Registration` đã chuẩn, rồi trả danh sách lỗi unmodifiable. Nó dùng một `ArrayList` **nội bộ** để xây kết quả — việc dùng local mutable state không tự động làm hàm có tác dụng phụ ra ngoài nếu state đó không bị lộ và kết quả quan sát được xác định.
- `decide` là orchestrator nối kết hai phép biến đổi và đóng gói kết quả trong `Decision`, giúp caller nhìn rõ dữ liệu đã chuẩn hóa, lỗi và trạng thái chấp nhận.
- `Decision` có `accepted()` tính từ danh sách lỗi; không cần lưu một cờ mutable mà ai đó phải đồng bộ lại sau khi thay đổi errors.
- Thêm một luật kiểm tra tuổi tối đa hoặc định dạng username có thể thực hiện trong `validate`, không cần sửa normalization hay caller.
- Muốn dùng kiểm tra email thật trong sản phẩm, phải định nghĩa hợp đồng cụ thể và dùng validator phù hợp; điều kiện `contains("@")` **chỉ là minh họa một luật đơn giản**, không phải chuẩn xác thực email đầy đủ.

**Trường hợp lỗi:** `normalize` từ chối `input` hoặc trường chuỗi bằng `null`. Các input như email thiếu `@` hoặc tuổi `16` được báo bằng result lỗi nghiệp vụ. Đây là cách phân biệt rõ **precondition failure** với **validation failure**.

## 9. Mô hình core thuần khiết và shell có tác dụng phụ

Một cách tổ chức hữu ích là **functional core, imperative shell**:

- **Functional core** gồm những hàm tính toán, chuẩn hóa, quyết định, biến đổi dữ liệu theo input và trả output. Phần lớn có thể kiểm thử chỉ bằng input/output.
- **Imperative shell** nhận request, đọc cấu hình/dữ liệu bên ngoài, gọi core, lưu DB, gửi event hoặc trả HTTP response. Đây là nơi **tác dụng phụ được thể hiện rõ**.

~~~text
HTTP/CLI/Service request
        │
        ▼
Shell: đọc dữ liệu, xác định ngữ cảnh
        │
        ▼
Core: validate → calculate → decide
        │
        ▼
Shell: lưu kết quả / phát sự kiện / trả response
~~~

Không nhất thiết cần tổ chức thành đúng hai package trong một codebase. Đây là **nguyên tắc phân chia trách nhiệm**; phương thức có hiệu ứng thật nên có tên/hợp đồng thể hiện việc nó thực hiện I/O hoặc cập nhật trạng thái.

### 9.1. Vì sao không nên ghi DB trong map?

~~~java
// Cảnh báo: side effect ẩn trong biến đổi.
List<Receipt> receipts = requests.stream()
        .map(request -> {
            Receipt receipt = calculate(request);
            repository.save(receipt);  // Ghi DB bên trong mapper.
            return receipt;
        })
        .toList();
~~~

Đoạn trên là minh họa với các lớp và phương thức giả định đã có. Nó trộn hai trách nhiệm: **tính toán** và **lưu trữ**. Sau này muốn dùng lại `calculate` để preview mà không lưu, hoặc muốn xử lý retry/transaction riêng, code trở nên khó điều khiển. Thêm parallelism, short-circuit hoặc một terminal operation khác còn khiến việc dựa vào số lần callback như một cam kết nghiệp vụ trở nên nguy hiểm.

Thay bằng việc **tách rõ hiệu ứng**:

~~~java
List<Receipt> receipts = requests.stream()
        .map(this::calculate)
        .toList();

repository.saveAll(receipts);
~~~

Hai dòng thể hiện rõ ranh giới: lần đầu chỉ tạo các value, sau đó mới thực hiện bước persistence. Tất nhiên, một ứng dụng thực tế vẫn phải thiết kế transaction/idempotency, lỗi giữa chừng và quyền ghi; việc tách dòng code không tự giải quyết tất cả vấn đề đó.

## 10. Chương trình Java 17: tính toán trước, hiệu ứng được gọi sau

Lưu file **`FunctionalCoreShellDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class FunctionalCoreShellDemo {
    record Request(String id, List<Integer> prices) {
        Request {
            prices = List.copyOf(prices);
        }
    }

    record Receipt(String id, int total) {}

    static Receipt calculate(Request request) {
        int total = request.prices().stream()
                .mapToInt(Integer::intValue)
                .sum();
        return new Receipt(request.id(), total);
    }

    static class InMemoryStore {
        private final List<Receipt> saved = new ArrayList<>();

        void save(Receipt receipt) {
            saved.add(receipt);
            System.out.println("saved:" + receipt.id() + ":" + receipt.total());
        }

        int size() {
            return saved.size();
        }
    }

    public static void main(String[] args) {
        List<Request> requests = List.of(
                new Request("A", List.of(10, 20)),
                new Request("B", List.of(7, 8))
        );

        List<Receipt> receipts = requests.stream()
                .map(FunctionalCoreShellDemo::calculate)
                .toList();

        System.out.println("computed=" + receipts);

        InMemoryStore store = new InMemoryStore();
        receipts.forEach(store::save);
        System.out.println("stored=" + store.size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FunctionalCoreShellDemo.java
java FunctionalCoreShellDemo
~~~

Stdout:

~~~text
computed=[Receipt[id=A, total=30], Receipt[id=B, total=15]]
saved:A:30
saved:B:15
stored=2
~~~

**Phân tích:**

1. `Request` giữ một snapshot cấu trúc của danh sách giá bằng `List.copyOf`. Với phần tử `Integer` immutable và dữ liệu mẫu không null, request không bị thay đổi cấu trúc từ ngoài.
2. `calculate(Request)` có hợp đồng **một request → một receipt**. Nó chỉ tính tổng và tạo record mới, không ghi vào `store`.
3. `map(FunctionalCoreShellDemo::calculate).toList()` tạo danh sách receipt; `computed` được in **trước** khi có dòng `saved` nào.
4. `store.save` là bước có side effect, được gọi riêng sau khi toàn bộ giá trị đã tính xong. `InMemoryStore` chỉ là giả lập để nhìn rõ ranh giới, không phải cơ chế database/transaction thật.
5. `forEach` ở đây gọi trên `List<Receipt>`, với thứ tự rõ trong ví dụ tuần tự; nếu cần transaction/retry trong sản phẩm, nên dùng service/repository có hợp đồng tương ứng, thay vì phụ thuộc `forEach` để tự động bảo đảm atomicity.
6. Các phép tổng trong ví dụ dùng `int` và dữ liệu nhỏ. Với tiền tệ hoặc dữ liệu lớn, cần chính sách overflow và kiểu dữ liệu phù hợp.

Bài học không phải mọi side effect đều “xấu”: nó nên được **làm rõ trong tên/hợp đồng và đặt ở nơi dễ kiểm soát**.

## 11. Java functional interfaces hỗ trợ thiết kế như thế nào?

Không nhất thiết phải tạo một class cho mỗi phép biến đổi. Java hỗ trợ những interface chuẩn:

| Kiểu | Hình dạng | Khi phù hợp |
|---|---|---|
| `Function<T,R>` | `T → R` | Chuyển một value sang value khác |
| `UnaryOperator<T>` | `T → T` | Biến đổi cùng kiểu dữ liệu |
| `Predicate<T>` | `T → boolean` | Kiểm tra một điều kiện |
| `BiFunction<T,U,R>` | `(T,U) → R` | Hàm nhận hai tham số |
| `Supplier<T>` | `() → T` | Cung cấp giá trị khi được gọi |
| `Consumer<T>` | `T → void` | Thực hiện hành động có side effect |
| `IntFunction<R>`, `IntUnaryOperator` | Biến thể primitive | Tránh boxing khi hợp lý |

**Giao diện hàm biểu diễn chữ ký kỹ thuật, không thay thế ngữ nghĩa nghiệp vụ.** Ví dụ một `Function<Order,Quote>` không tự chứng minh rằng mọi `Order` hợp lệ, không có I/O hoặc luôn tính đúng tiền. Những bảo đảm đó đến từ **hợp đồng, implementation và test**.

### 11.1. Compose và andThen: nối các phép biến đổi cùng hợp đồng

~~~java
Function<String, String> trim = String::strip;
Function<String, String> upper =
        s -> s.toUpperCase(Locale.ROOT);

Function<String, String> normalized = trim.andThen(upper);

System.out.println(normalized.apply("  hello  ")); // HELLO
~~~

Đây là mã minh họa, cần `import java.util.function.Function;` và `import java.util.Locale;`.

- `trim.andThen(upper)` áp dụng `trim` **trước**, rồi `upper`.
- `upper.compose(trim)` cũng cho thứ tự biến đổi tương ứng.
- `compose` và `andThen` chỉ nối những hàm có kiểu tương thích; chúng **không tự giải quyết** kiểm tra null, exceptions, side effects hoặc những điều kiện nghiệp vụ chưa được định nghĩa.

### 11.2. Lựa chọn giữa method và lambda

Một quy tắc nghiệp vụ có tên như `calculateShipping` thường dễ đọc và dễ tái sử dụng hơn lambda dài:

~~~java
// Nếu calculateShipping(int) có sẵn.
IntUnaryOperator shippingPolicy = MyPolicy::calculateShipping;
~~~

Nhưng không cần biến **mọi** phương thức thành `Function`/`Supplier` hay truyền callback qua nhiều lớp. Nếu một hàm chỉ được dùng trực tiếp tại một vị trí, gọi phương thức bình thường thường rõ ràng hơn. Functional interface hữu ích nhất khi **cần truyền hành vi** (chẳng hạn chính sách giảm giá có thể thay thế).

## 12. Tách trách nhiệm mà không bị phân mảnh quá mức

Một câu hỏi quan trọng: **khi nào nên tách thành hàm mới?**

Nên cân nhắc tách nếu:

- Bước có một **tên nghiệp vụ cụ thể** như `validateAddress`, `discountForMember`, `calculateTax`.
- Bước có thể **kiểm thử độc lập** với nhiều trường hợp biên.
- Quy tắc có khả năng **thay đổi riêng**.
- Bước có **đầu vào/đầu ra đủ ổn định** để tái sử dụng.
- Việc tách giúp **làm rõ tác dụng phụ hoặc hợp đồng lỗi**.
- Bước cần cùng một quy tắc ở nhiều nơi mà không muốn copy-paste.

**Không nên tách máy móc** nếu:

- Helper chỉ đổi tên một biểu thức rất đơn giản nhưng khiến người đọc phải nhảy qua nhiều file mới hiểu luồng nghiệp vụ.
- Hàm mới nhận hàng loạt biến nội bộ của hàm cũ mà không có khái niệm miền dữ liệu rõ ràng.
- Một giá trị trung gian chỉ phục vụ một biểu thức ngay cạnh nó và tên biến đã đủ rõ.
- Việc tách khiến phụ thuộc bị che bằng state toàn cục/field mutable thay vì truyền input rõ ràng.
- Tạo abstract class/strategy/factory nhiều tầng chỉ để xử lý một quy tắc cố định không có yêu cầu mở rộng.

**Tính kết dính (*cohesion*) quan trọng hơn độ ngắn tuyệt đối của phương thức.** Một hàm 20 dòng thực hiện một quyết định có tên và một kết quả rõ ràng có thể tốt hơn 10 hàm một dòng khó theo dấu.

## 13. Thiết kế hợp đồng lỗi rõ ràng

Khi chia nghiệp vụ, caller cần biết **hàm sẽ làm gì nếu dữ liệu không hợp lệ**.

Các lựa chọn phổ biến:

1. **Ném exception cho vi phạm tiền điều kiện**: ví dụ `Objects.requireNonNull(input)`, `IllegalArgumentException` nếu số lượng âm là sai cách dùng API.
2. **Trả kết quả validation có cấu trúc**: phù hợp khi người dùng có thể gửi nhiều trường chưa hợp lệ, cần hiển thị mọi lỗi.
3. **Dùng `Optional<T>`**: phù hợp khi kết quả có thể **vắng mặt một cách bình thường**, không yêu cầu mô tả lỗi chi tiết.
4. **Dùng kiểu kết quả riêng** như một sealed interface hoặc record chứa status/error: hữu ích khi có nhiều nhánh nghiệp vụ cần phân biệt.
5. **Phân tách lỗi I/O** với lỗi tính toán: ghi DB có thể lỗi mạng, nhưng hàm tính giảm giá thuần khiết không nên buộc caller xử lý network exception.

Đừng để `null` mang nhiều nghĩa (“không tìm thấy”, “lỗi”, “chưa tính”, “trống hợp lệ”). Những sự mơ hồ này khiến đầu ra của hàm không thực sự rõ.

### 13.1. Validation nên độc lập với quyết định và I/O

Với bài đăng ký, `validate` trả danh sách lỗi, `decide` đóng gói trạng thái và dữ liệu đã chuẩn hóa. Khi cần lưu đăng ký được chấp nhận, **shell** đọc `decision.accepted()` rồi gọi repository. Nhờ vậy test validation không cần DB, test repository không cần thực thi lại mọi quy tắc normalization.

Trong hệ thống thật, kết quả validation có thể bị lệch nếu dữ liệu thay đổi giữa kiểm tra và ghi. Với yêu cầu nhất quán, shell/repository vẫn cần transaction hoặc cơ chế chống race phù hợp. Việc có hàm nhỏ giúp xác định chỗ đặt bảo đảm đó, không thay thế nó.

## 14. Tính bất biến và tránh tham số đầu vào bị thay đổi

Một hàm nhỏ có thể trả kết quả rõ nhưng vẫn gặp vấn đề nếu **đầu vào bị sửa ở nơi khác**.

~~~java
record Report(List<StringBuilder> names) {}
~~~

Record trên chỉ giữ tham chiếu đến list và các `StringBuilder` mutable. Dùng `List.copyOf(names)` trong constructor sẽ bảo vệ **cấu trúc list**, nhưng không sao chép sâu từng `StringBuilder`. Nếu muốn snapshot kết quả, chuyển phần tử thành `String` trước khi copy.

Ví dụ:

~~~java
List<String> names = mutableNames.stream()
        .map(StringBuilder::toString)
        .toList();
~~~

Đoạn minh họa giả định `mutableNames` kiểu `List<StringBuilder>`. Các chuỗi output có trạng thái immutable tại thời điểm conversion. Khi input có thể bị thread khác thay đổi **trong lúc snapshot**, cần đồng bộ hóa phù hợp để đạt nhất quán; `toList()` không phải transaction snapshot.

**Hàm có input/output rõ** không đồng nghĩa dữ liệu luôn immutable, nhưng nên có một chính sách rõ: hàm có được mutate input không? Output có chia sẻ reference với input không? Caller có được mutate output không?

## 15. Hàm nhỏ và concurrent execution

Một lợi ích thường được nhắc tới của hàm thuần khiết là dễ chạy song song. Nhưng chỉ “tách nhiều hàm nhỏ” không tự biến code thành thread-safe.

Đối với Stream song song:

- Mapper/predicate nên **stateless, non-interfering**, không chỉnh sửa collection nguồn.
- Nếu hàm đọc một cache hoặc cấu hình mutable, nó còn phụ thuộc vào trạng thái ngoài.
- Ghi vào `ArrayList` hoặc tăng biến đếm `int` dùng chung trong nhiều callback có thể gây race.
- Các phép giảm `reduce` cần accumulator associative, identity và combiner phù hợp.
- Tính toán tiền/tổng còn cần xem overflow, floating-point precision và thứ tự làm tròn.

Ví dụ không nên làm:

~~~java
// CẢNH BÁO: tích lũy vào list ngoài trong parallel stream.
List<String> output = new ArrayList<>();
input.parallelStream().map(x -> {
    output.add(transform(x));
    return x;
}).count();
~~~

Ngoài rủi ro race, một terminal operation như `count()` trên nguồn có kích thước xác định có thể **không gọi mapper** khi implementation chứng minh kết quả mà không cần duyệt. Vì vậy không dùng side effect của intermediate operation làm logic bắt buộc.

Hướng phù hợp khi thật sự cần tạo danh sách:

~~~java
List<String> output = input.parallelStream()
        .map(MyService::transform)
        .toList();
~~~

Đoạn minh họa cần `MyService.transform` là hàm tương thích kiểu, stateless và phù hợp thread safety. Bộ thu kết quả của Stream xử lý việc tạo list theo hợp đồng, không cần một `ArrayList` ngoài pipeline để các worker cùng cập nhật.

## 16. Refactor từ phương thức dài sang các hàm nhỏ theo quy trình

Một cách chuyển đổi an toàn:

**Bước 1 — Ghi lại hành vi hiện có.** Xác định input, output, luật nghiệp vụ, I/O, exception và test hiện hữu. Không vội đổi thuật toán.

**Bước 2 — Nhận diện các phép tính có tên.** Ví dụ `subtotal`, `discount`, `shipping`. Kiểm tra luật nào cần dùng giá trị của luật khác.

**Bước 3 — Thiết kế kiểu dữ liệu.** Dùng `Order`, `Line`, `Quote` hoặc DTO đúng miền nghiệp vụ thay vì truyền những danh sách tham số rời rạc.

**Bước 4 — Tách hàm thuần khiết trước.** Dời phép tính và validation không I/O ra những phương thức nhận input rõ ràng, trả output xác định. Viết test cho giá trị biên.

**Bước 5 — Tạo orchestrator.** Một phương thức `quote()` hoặc `decide()` gọi các hàm con theo thứ tự logic và trả kết quả cuối. Không cần dùng `Function.andThen` ở mọi nơi; gọi method trực tiếp có thể dễ đọc hơn.

**Bước 6 — Cô lập hiệu ứng.** Chuyển việc ghi DB/log/bắn event ra bước service/shell có hợp đồng về transaction và lỗi. Nếu hiện đang có side effect trong mapper, xác nhận yêu cầu nghiệp vụ trước khi di chuyển, tránh vô tình đổi thứ tự tác động.

**Bước 7 — Kiểm thử regression.** So sánh output với cách triển khai cũ trên tập trường hợp bình thường, biên, không hợp lệ, rỗng, tràn số. Với phần I/O, kiểm thử tương tác và kịch bản thất bại riêng.

**Bước 8 — Xem lại độ phức tạp.** Nếu việc tách tạo quá nhiều helper một dòng, dependency injection thừa hoặc biến trạng thái ẩn, gộp lại theo ranh giới trách nhiệm.

Quy trình này có thể áp dụng dần mà không cần viết lại toàn bộ ứng dụng. Mỗi bước refactor nên giữ hành vi nghiệp vụ hoặc chỉ thay đổi những hành vi đã được yêu cầu và kiểm thử.

## 17. Lỗi thường gặp khi “chia nhỏ” nghiệp vụ

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Hàm nhận quá nhiều primitive | Dễ truyền nhầm thứ tự và ý nghĩa | Dùng record/value object đúng miền dữ liệu |
| Hàm tên `process` hoặc `handle` nhưng không rõ output | Người đọc phải mở implementation để biết mục đích | Đặt tên `normalizeEmail`, `calculateShipping`, `validateOrder` |
| Bỏ qua trường hợp null/rỗng | Caller phải đoán hàm trả gì | Định nghĩa precondition, Optional hoặc result lỗi |
| Vừa tính vừa ghi DB trong mapper | Khó test, retry và preview | Tách core tính toán và shell có I/O |
| Mọi helper đều đọc static config mutable | Phụ thuộc ẩn, test khó ổn định | Truyền config/snapshot qua input rõ ràng |
| Một hàm trả object mutable dùng chung | Caller tác động lẫn nhau | Defensive copy hoặc immutable output |
| Một hàm có quá nhiều boolean flags | Nhiều nhánh khó hiểu | Enum/strategy/kiểu yêu cầu có tên |
| Tách quá nhỏ không theo trách nhiệm | Code nhảy qua nhiều nơi, khó đọc | Gộp các bước thuộc cùng một khái niệm |
| Dùng Stream cho mọi phép toán | Flow phức tạp, dễ giấu side effect | Dùng loop/orchestrator nếu rõ hơn |
| Quên rule identity/associativity của reduce | Kết quả song song không đáng tin | Kiểm tra hợp đồng reduce hoặc dùng collector |
| Lạm dụng unchecked exception cho mọi lỗi người dùng | Khó trả thông báo validation có cấu trúc | Chọn kiểu result lỗi rõ ràng |
| Xem thuần khiết là điều tự có vì dùng lambda | Side effect và state vẫn tồn tại | Xem implementation và dependency |
| Không kiểm thử giới hạn/ràng buộc | Sai ở ngưỡng, rỗng, overflow | Test nhánh và giá trị biên |
| Tách ra nhưng vẫn mutate input | Side effect không biến mất | Tạo value mới hoặc làm rõ lệnh cập nhật |

## 18. Checklist review thiết kế theo hàm

1. Có thể mô tả mỗi bước bằng **một câu nghiệp vụ cụ thể** không?
2. Tên hàm có nói rõ **hành động hoặc phép tính** không?
3. Các input có đủ và đúng kiểu, đơn vị, ý nghĩa không?
4. Hàm trả một output có nghĩa, hay phải sửa biến ngoài để “trả kết quả”?
5. Có yêu cầu validation, null, rỗng, overflow, rounding, exception không?
6. Callback có mutate input, state ngoài hoặc nguồn Stream không?
7. Kết quả có chia sẻ mutable reference với input/caller không?
8. Có thể unit test hàm bằng input/output mà không khởi chạy database/web server không?
9. Luật nào thay đổi riêng và có ca kiểm thử biên?
10. Hàm có đọc thời gian, random, cấu hình, môi trường không? Nếu có, dependency đã rõ chưa?
11. Có tách thao tác có side effect khỏi phép biến đổi?
12. Có một orchestrator thể hiện thứ tự dữ liệu đi qua các bước không?
13. Những hàm quá nhỏ có đang khiến luồng xử lý khó hiểu hơn không?
14. Có cần dùng Stream, hay một vòng lặp/lệnh trực tiếp dễ hiểu hơn?
15. Nếu chạy parallel, các callback có stateless/non-interfering và giảm kết quả đúng hợp đồng không?

Đạt checklist không có nghĩa hệ thống không bao giờ lỗi. Nó giúp các giả định quan trọng **hiển thị ngay trong cấu trúc API**, nhờ đó test, code review và thay đổi quy tắc ít tạo tác dụng ngoài ý muốn.

## 19. Bài tập tự kiểm tra

**Câu 1.** Phương thức nhận `(int a, int b, int c, int d)` để tính tiền có vấn đề gì nếu không có kiểu dữ liệu/naming rõ?

**Câu 2.** Vì sao `map(p -> { p.setPrice(...); return p; })` không mang ý nghĩa “biến đổi không tác dụng phụ”?

**Câu 3.** Trong ví dụ tính báo giá, vì sao `shipping(int afterDiscount)` dễ kiểm thử hơn khi nằm riêng trong `checkout()` dài?

**Câu 4.** Một hàm không sửa input nhưng ghi log và đọc đồng hồ có chắc pure không?

**Câu 5.** `normalize` và `validate` nên chịu trách nhiệm khác nhau thế nào?

**Câu 6.** Vì sao `List.copyOf` có thể chưa đủ để bảo đảm bất biến sâu nếu phần tử là mutable entity?

**Câu 7.** `Function.andThen` được dùng khi nào? Có bắt buộc dùng nó để gọi hai hàm liên tiếp không?

**Câu 8.** Vì sao không nên dùng `peek`/`map` để bảo đảm mỗi phần tử đều được ghi audit trong Stream?

**Câu 9.** Trong ví dụ `FunctionalCoreShellDemo`, đâu là functional core và đâu là imperative shell?

**Câu 10.** Khi nào nên **không** tách một biểu thức ngắn thành hàm mới?

**Đáp án ngắn:**

1. Các tham số thiếu ngữ nghĩa và dễ bị truyền sai vị trí; dùng tên/record/value object.
2. Vì nó sửa chính object input và có thể ảnh hưởng những reference khác.
3. Hàm có một input và một kết quả với ngưỡng rõ; dễ test `99`, `100` mà không chuẩn bị các phụ thuộc I/O.
4. Không; side effect và dependency ngoài vẫn có.
5. `normalize` chuyển biểu diễn; `validate` đánh giá điều kiện và trả thông tin lỗi.
6. Vì copy cấu trúc list không clone từng object con.
7. Khi muốn nối những `Function` tương thích kiểu; gọi phương thức bình thường vẫn hoàn toàn hợp lệ.
8. Short-circuit và tối ưu hóa có thể bỏ callback; side effect không được cam kết chạy cho mọi phần tử.
9. `calculate(Request)` là core; `store.save(...)` và vòng đời lưu trữ thuộc shell.
10. Khi nó không tạo khái niệm nghiệp vụ riêng, làm người đọc phải nhảy qua nhiều nơi hoặc che giấu dependency.

## 20. Tài liệu chính thức để đối chiếu

- [Java SE 17 — java.util.function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html): các functional interface chuẩn và mục đích sử dụng.
- [Java SE 17 — Function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html): `apply`, `compose` và `andThen`.
- [Java SE 17 — Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): `map`, `reduce`, `toList`, đặc tính pipeline và yêu cầu callback.
- [Java SE 17 — java.util.stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): tính non-interference, statelessness và lưu ý side effects.
- [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): tạo danh sách unmodifiable snapshot cấu trúc.
- [Java SE 17 — Records](https://docs.oracle.com/en/java/javase/17/language/records.html): cú pháp record và dữ liệu có component rõ ràng.

**Ghi nhớ:** Thiết kế theo hàm tốt không nằm ở số lượng lambda hoặc số lượng helper, mà ở **những bước nghiệp vụ có tên, có input/output rõ ràng, có điều kiện và lỗi được định nghĩa**. Hãy dùng các hàm nhỏ để tách **chuẩn hóa – kiểm tra – tính toán – quyết định**; phối hợp chúng trong orchestrator dễ đọc; và đưa **lưu trữ/I/O/tác dụng phụ** ra ranh giới phù hợp. Thiết kế như vậy giúp code dễ kiểm thử, dễ mở rộng và an toàn hơn trước thay đổi trạng thái.