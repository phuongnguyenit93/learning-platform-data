# Mô hình hóa variant bằng subtype trong domain model (Java 21+)

## 1. Variant là gì và vì sao cần subtype?

Trong thiết kế domain model, một thực thể hoặc khái niệm thường có **nhiều biến thể hợp lệ** (*variants*) với dữ liệu và quy tắc riêng. Ví dụ, một đơn hàng có thể được giao theo ba cách:

- **Nhận tại cửa hàng**: cần `storeId`.
- **Giao tới nhà**: cần địa chỉ và lựa chọn giao nhanh.
- **Nhận ở tủ hàng**: cần `lockerId`.

Một thiết kế dễ gặp là gộp mọi trường vào một record:

~~~java
enum DeliveryKind { PICKUP, HOME, LOCKER }

record DeliveryData(
        DeliveryKind kind,
        String storeId,
        String lockerId,
        String city,
        String street,
        boolean express) {}
~~~

Đây là **đoạn minh họa**, không phải mô hình được đề xuất. Nó cho phép các tổ hợp vô nghĩa:

- `kind == PICKUP` nhưng không có `storeId`.
- `kind == HOME` nhưng `city == null`, hoặc đồng thời có `lockerId`.
- `kind == LOCKER` nhưng lại bật `express`, một cờ chỉ có ý nghĩa đối với giao tại nhà.

Ứng dụng phải dùng các chuỗi `if` để xác nhận mọi kết hợp trường hợp lệ. Nếu một nhánh thiếu kiểm tra, đối tượng vẫn được tạo ở trạng thái không hợp lệ. Đây là dấu hiệu **mô hình dữ liệu chưa thể hiện đúng các variant**.

Phương án tốt hơn là **mỗi variant có một subtype riêng**: chỉ mang những trường nó cần và chịu trách nhiệm kiểm tra các ràng buộc của chính mình.

> Nguyên tắc: Khi các biến thể có **cấu trúc dữ liệu khác nhau**, hãy cân nhắc mô hình kiểu tổng (sum type) bằng một tập subtype; khi chúng chỉ khác tên trạng thái, một `enum` có thể đơn giản hơn.

## 2. Chọn “tập variant đóng” bằng `sealed interface`

Với Java 17+, một `sealed interface` xác định trực tiếp các kiểu được phép triển khai nó:

~~~java
sealed interface DeliveryOption
        permits StorePickup, HomeDelivery, ParcelLocker {}

record StorePickup(String storeId) implements DeliveryOption {}
record HomeDelivery(Address destination, boolean express)
        implements DeliveryOption {}
record ParcelLocker(String lockerId) implements DeliveryOption {}

record Address(String city, String street) {}
~~~

Đây là **các khai báo minh họa**; bên dưới chúng ta sẽ bổ sung validation vào constructor và đưa tất cả vào một chương trình đầy đủ.

Ý nghĩa mô hình:

| Subtype | Dữ liệu đặc thù | Ý nghĩa nghiệp vụ |
| --- | --- | --- |
| `StorePickup` | `storeId` | Khách đến nhận tại cửa hàng |
| `HomeDelivery` | `Address destination`, `express` | Giao tới địa chỉ khách chỉ định |
| `ParcelLocker` | `lockerId` | Giao tới một tủ nhận hàng |
| `DeliveryOption` | Không khai báo một tổ hợp trường thừa | Abstraction chung cho các variant |

`DeliveryOption` đại diện cho khái niệm “cách nhận hàng”, **không** phải một đối tượng cần được tạo trực tiếp. Ba subtype mang ba hình dạng dữ liệu khác nhau.

**Vì sao dùng `sealed`?** Với tập variant nghiệp vụ được kiểm soát trong codebase, `permits` giới hạn **các subtype trực tiếp**. Các `record` là kiểu `final` theo mặc định nên không thể có subclass tùy ý của `StorePickup`, `HomeDelivery` hoặc `ParcelLocker`.

Một direct subclass của kiểu `sealed` về nguyên tắc phải chọn một trong các dạng `final`, `sealed` hoặc `non-sealed`; trong ví dụ này, `record` đã đáp ứng bằng tính `final`. Nếu sử dụng `non-sealed` ở một nhánh, tập subtype sâu hơn có thể mở rộng; tính “đóng” của toàn bộ cây sẽ khác. Đừng nhầm `sealed` với việc tự động cấm mọi trạng thái dữ liệu sai: **constructor validation vẫn cần thiết**.

## 3. Bảo vệ invariant ngay tại nơi tạo variant

*Invariant* là điều kiện phải đúng đối với mọi đối tượng hợp lệ trong domain. Ví dụ:

- `StorePickup.storeId` phải khác `null` và không trắng.
- `ParcelLocker.lockerId` phải khác `null` và không trắng.
- `HomeDelivery.destination` phải khác `null`.
- `Address.city` và `Address.street` phải khác `null` và không trắng.

Với `record`, ta có thể dùng **compact constructor** để xác thực:

~~~java
static String requireText(String text, String field) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException(field);
    }
    return text;
}

record Address(String city, String street) {
    Address {
        requireText(city, "city");
        requireText(street, "street");
    }
}

record StorePickup(String storeId) implements DeliveryOption {
    StorePickup {
        requireText(storeId, "storeId");
    }
}

record HomeDelivery(Address destination, boolean express)
        implements DeliveryOption {
    HomeDelivery {
        if (destination == null) {
            throw new IllegalArgumentException("destination");
        }
    }
}

record ParcelLocker(String lockerId) implements DeliveryOption {
    ParcelLocker {
        requireText(lockerId, "lockerId");
    }
}
~~~

Đây là **đoạn minh họa các thành phần** dùng trong cùng một lớp; phương thức `requireText` và interface `DeliveryOption` cần có ở phạm vi bao ngoài. Chương trình nguyên vẹn ở mục 7 sắp xếp chúng đầy đủ.

Với compact constructor, Java tự thực hiện việc gán các tham số cho record component sau phần thân constructor. Nếu điều kiện sai, ném `IllegalArgumentException` ngay lúc tạo đối tượng; không cần để hàng loạt hàm nghiệp vụ kiểm tra lại những đối tượng bị tạo sai.

Ví dụ:

~~~java
new StorePickup("S1");                     // Hợp lệ
new HomeDelivery(new Address("Ha Noi", "12 Pho Hue"), true); // Hợp lệ

new StorePickup(" ");                      // IllegalArgumentException
new HomeDelivery(null, true);              // IllegalArgumentException
~~~

**Lưu ý về tính bất biến:** record tạo các component `private final` và accessor, nhưng chỉ bảo đảm *shallow immutability*. Nếu component giữ `List` hoặc object có thể thay đổi, cần tạo bản sao phòng vệ hoặc dùng value object bất biến khi domain yêu cầu. Trong ví dụ này các component là `String`, `boolean` và một `Address` record hợp lệ, nên không có collection mutable cần xử lý.

## 4. Pattern matching biến tập subtype thành những nhánh rõ ràng

Khi mô hình đã có subtype cụ thể, ta có thể viết một `switch expression` trên `DeliveryOption`:

~~~java
static int fee(DeliveryOption option) {
    java.util.Objects.requireNonNull(option, "option");

    return switch (option) {
        case StorePickup(var storeId) -> 0;
        case ParcelLocker(var lockerId) -> 15;
        case HomeDelivery(var destination, var express)
                when express -> 50;
        case HomeDelivery(var destination, var express) -> 25;
    };
}
~~~

Các con số `0`, `15`, `50` và `25` chỉ là **quy tắc phí minh họa**, không phải biểu phí thực tế.

Điểm đáng chú ý:

1. `StorePickup(...)` và `ParcelLocker(...)` là **record pattern**, phân rã các component tương ứng của mỗi subtype.
2. `HomeDelivery(var destination, var express) when express` là pattern có **guard**: chỉ dùng phí giao nhanh nếu component `express` bằng `true`.
3. Nhánh `HomeDelivery(...)` tiếp theo xử lý những trường hợp giao tại nhà không thỏa guard. Đặt nhánh cụ thể có `when` **trước** nhánh HomeDelivery tổng quát.
4. `switch` bao phủ cả ba subtype được phép của `sealed interface`. Vì vậy, **không cần `default`** trong ví dụ này.
5. Lệnh `Objects.requireNonNull` nói rõ hợp đồng đầu vào: `null` không được chấp nhận. Nếu truyền `null`, chương trình ném `NullPointerException` tại kiểm tra này, thay vì coi `null` là một variant giao hàng.

**Lợi ích khi thêm variant:** Giả sử sau này có `DroneDelivery` được thêm vào danh sách `permits`. Khi biên dịch lại code, một `switch expression` không có `default` và chưa xử lý subtype mới có thể bị compiler báo **không exhaustive**. Đây là tác dụng quan trọng của việc mô hình tập variant đóng.

Điều này **không** có nghĩa mọi logic trong hệ thống tự động được sửa đúng; các nơi có `default` rộng, logic dùng `if` hoặc hệ thống chạy với các class biên dịch ở thời điểm khác vẫn cần được kiểm tra. Lợi ích là có thêm bảo đảm và điểm báo lỗi **tại compile time**.

## 5. Nested record pattern: lấy dữ liệu đặc thù, không cần ép kiểu

Đối với giao hàng tại nhà, địa chỉ được mô hình bằng record `Address`. Java 21 cho phép phân rã qua hai tầng:

~~~java
static String route(DeliveryOption option) {
    java.util.Objects.requireNonNull(option, "option");

    return switch (option) {
        case StorePickup(var storeId) -> "store:" + storeId;
        case ParcelLocker(var lockerId) -> "locker:" + lockerId;
        case HomeDelivery(Address(var city, var street), var express) ->
                "home:" + city + "/" + street
                        + (express ? ":express" : ":standard");
    };
}
~~~

Đây là một phương thức minh họa dùng các subtype đã định nghĩa; toàn bộ mã được trình bày ở mục 7.

- `HomeDelivery(...)` xác nhận variant giao tại nhà.
- `Address(var city, var street)` phân rã record nằm trong component `destination`.
- `city` và `street` là biến mẫu ở tầng trong; `express` là biến mẫu của `HomeDelivery` ở tầng ngoài.
- Không phải gọi liên tiếp `((HomeDelivery) option).destination().city()` hoặc ép kiểu bằng tay.
- Các biến chỉ có phạm vi trong nhánh `case` mà pattern đã khớp.

Một mẫu lồng `Address(...)` yêu cầu component `destination` có hình dạng phù hợp. Vì constructor `HomeDelivery` cấm `destination == null`, chúng ta không kỳ vọng đối tượng hợp lệ có địa chỉ `null`. Dù vậy, đây là bảo đảm từ **domain invariant**, không phải do compiler tự suy ra mọi dữ liệu luôn đúng nghiệp vụ.

**Cẩn thận với `null` trong record component:** các component pattern dạng `var` có thể lấy giá trị `null`. Một record pattern lồng cũng không thay thế việc kiểm tra giá trị đầu vào theo domain. Ở đây `Address` chủ động cấm `city` và `street` trống hoặc null, nên phương thức tạo route dựa được vào invariant đó.

### So sánh với kiểm tra kiểu thủ công

~~~java
static String routeOldStyle(DeliveryOption option) {
    if (option instanceof StorePickup pickup) {
        return "store:" + pickup.storeId();
    }
    if (option instanceof ParcelLocker locker) {
        return "locker:" + locker.lockerId();
    }
    if (option instanceof HomeDelivery home) {
        Address address = home.destination();
        return "home:" + address.city() + "/" + address.street()
                + (home.express() ? ":express" : ":standard");
    }
    throw new IllegalStateException("Unsupported delivery option");
}
~~~

Cách `if/else` dùng type pattern như trên vẫn hợp lệ và đôi khi dễ hiểu hơn. Tuy nhiên, với một tập `sealed` đóng và một phép chuyển đổi thành **một giá trị kết quả**, `switch expression` thường thể hiện rõ hơn việc xử lý toàn bộ variant và giúp compiler kiểm tra tính bao phủ.

## 6. Variant khác với trạng thái và “cờ tùy chọn”

Không phải cứ có một giá trị `enum` là cần tạo subtype mới. Nên xác định **bản chất khác biệt**:

- **Subtype variant:** dữ liệu và/hoặc quy tắc cấu trúc khác nhau. Ví dụ `StorePickup(storeId)` khác `HomeDelivery(address, express)`.
- **Trạng thái trong cùng một variant:** một đơn hàng có `status = CREATED/PAID/CANCELLED` nhưng mọi trạng thái vẫn dùng chung dữ liệu. Có thể dùng `enum` nếu không cần biểu diễn tập dữ liệu khác nhau giữa các trạng thái.
- **Tùy chọn nội bộ variant:** `express` chỉ có ý nghĩa trong `HomeDelivery`, nên đặt bên trong subtype đó, không đặt trên interface chung cho mọi cách nhận hàng.

Hai câu hỏi giúp lựa chọn:

1. **Có tổ hợp field nào không thể hợp lệ không?** Nếu có, subtype thường giúp loại bỏ những trường không liên quan khỏi mỗi variant.
2. **Các variant có trường bắt buộc khác nhau không?** Nếu khác nhau rõ rệt, subtype giúp constructor bảo đảm đúng dữ liệu bắt buộc.

Nếu mọi biến thể chỉ là một nhãn trong một cột, không có dữ liệu đặc thù hoặc thay đổi về cấu trúc, một `enum` có thể đủ. Nếu variant có hành vi phong phú, cũng cân nhắc đặt **hành vi** gần subtype tương ứng thay vì tạo một `switch` khổng lồ ở khắp mọi tầng của ứng dụng.

## 7. Chương trình Java 21 hoàn chỉnh

Lưu mã sau thành tệp **`DeliveryVariantsDemo.java`**. Ví dụ xác thực constructor, tính phí, tạo route, phân rã record lồng và chạy các ca kiểm thử, không cần thư viện ngoài JDK.

~~~java
public class DeliveryVariantsDemo {
    sealed interface DeliveryOption
            permits StorePickup, HomeDelivery, ParcelLocker {}

    record Address(String city, String street) {
        Address {
            requireText(city, "city");
            requireText(street, "street");
        }
    }

    record StorePickup(String storeId) implements DeliveryOption {
        StorePickup {
            requireText(storeId, "storeId");
        }
    }

    record HomeDelivery(Address destination, boolean express)
            implements DeliveryOption {
        HomeDelivery {
            if (destination == null) {
                throw new IllegalArgumentException("destination");
            }
        }
    }

    record ParcelLocker(String lockerId) implements DeliveryOption {
        ParcelLocker {
            requireText(lockerId, "lockerId");
        }
    }

    static String requireText(String text, String field) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(field);
        }
        return text;
    }

    static int fee(DeliveryOption option) {
        java.util.Objects.requireNonNull(option, "option");
        return switch (option) {
            case StorePickup(var storeId) -> 0;
            case ParcelLocker(var lockerId) -> 15;
            case HomeDelivery(var destination, var express)
                    when express -> 50;
            case HomeDelivery(var destination, var express) -> 25;
        };
    }

    static String route(DeliveryOption option) {
        java.util.Objects.requireNonNull(option, "option");
        return switch (option) {
            case StorePickup(var storeId) -> "store:" + storeId;
            case ParcelLocker(var lockerId) -> "locker:" + lockerId;
            case HomeDelivery(Address(var city, var street), var express) ->
                "home:" + city + "/" + street
                    + (express ? ":express" : ":standard");
        };
    }

    private static int passed = 0;

    static void check(boolean ok, String name) {
        if (!ok) {
            throw new AssertionError(name);
        }
        passed++;
        System.out.println("PASS " + name);
    }

    static void expectInvalid(Runnable action, String name) {
        try {
            action.run();
            throw new AssertionError(
                    "Expected IllegalArgumentException: " + name);
        } catch (IllegalArgumentException expected) {
            check(true, name);
        }
    }

    public static void main(String[] args) {
        DeliveryOption pickup = new StorePickup("S1");
        Address address = new Address("Ha Noi", "12 Pho Hue");
        DeliveryOption standard = new HomeDelivery(address, false);
        DeliveryOption express = new HomeDelivery(address, true);
        DeliveryOption locker = new ParcelLocker("L9");

        check(fee(pickup) == 0, "pickup fee");
        check(route(pickup).equals("store:S1"), "pickup route");
        check(fee(standard) == 25, "standard fee");
        check(fee(express) == 50, "express fee");
        check(route(express).equals("home:Ha Noi/12 Pho Hue:express"),
                "express route");
        check(fee(locker) == 15, "locker fee");
        check(route(locker).equals("locker:L9"), "locker route");

        Object unknown = express;
        check(unknown instanceof HomeDelivery(
                Address(var city, var street), var fast)
                && city.equals("Ha Noi") && fast,
                "nested pattern");

        check(pickup.equals(new StorePickup("S1")),
                "record value equality");

        expectInvalid(() -> new StorePickup(" "), "blank store id");
        expectInvalid(() -> new Address("", "12 Pho Hue"), "blank city");
        expectInvalid(() -> new HomeDelivery(null, true),
                "null destination");
        expectInvalid(() -> new ParcelLocker(""), "blank locker id");

        try {
            fee(null);
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            check(true, "null selector");
        }

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Biên dịch và chạy với JDK 21 trở lên:

~~~bash
javac --release 21 DeliveryVariantsDemo.java
java DeliveryVariantsDemo
~~~

**Kết quả chuẩn:**

~~~text
PASS pickup fee
PASS pickup route
PASS standard fee
PASS express fee
PASS express route
PASS locker fee
PASS locker route
PASS nested pattern
PASS record value equality
PASS blank store id
PASS blank city
PASS null destination
PASS blank locker id
PASS null selector
ALL PASSED: 14
~~~

### Đọc kết quả kiểm thử

- Các ca `pickup`, `standard`, `express` và `locker` xác minh **mỗi subtype** có phí và route theo quy tắc ví dụ.
- `nested pattern` xác minh mẫu `HomeDelivery(Address(var city, var street), var fast)` phân rã đúng subtype và record con từ một biến đầu vào kiểu tĩnh `Object`.
- `record value equality` xác minh hai record `StorePickup("S1")` có giá trị thành phần bằng nhau thì `equals` trả `true`. Đây là ngữ nghĩa so sánh giá trị được record sinh ra.
- Bốn ca `expectInvalid` xác minh không thể tạo object hợp lệ với thông tin store/locker trống, city trống hoặc địa chỉ null.
- `null selector` xác minh hàm `fee` không chấp nhận một “variant null”. Đây là lựa chọn API cụ thể: ném `NullPointerException` do `Objects.requireNonNull`.
- Mỗi phép kiểm tra dùng `AssertionError` để dừng nếu sai, không phụ thuộc cờ `-ea` của `java`. Vì vậy kết quả `ALL PASSED: 14` chỉ được in khi toàn bộ các kiểm thử đạt.

## 8. Thêm một variant mới mà không bỏ sót xử lý

Giả sử domain bổ sung cách giao hàng bằng drone và có một dữ liệu riêng là `landingZone`. Về mặt thiết kế, ta sẽ:

1. Tạo subtype `DroneDelivery(String landingZone)` với constructor validation tương ứng.
2. Đưa subtype đó vào `permits` của `DeliveryOption`.
3. Biên dịch lại và rà soát các `switch expression` không có `default`: những chỗ chưa xử lý `DroneDelivery` sẽ cần thêm nhánh mới.
4. Bổ sung kiểm thử phí, route, dữ liệu không hợp lệ và tích hợp liên quan.

Ví dụ subtype mới (minh họa, **không** đưa vào chương trình mục 7):

~~~java
record DroneDelivery(String landingZone) implements DeliveryOption {
    DroneDelivery {
        requireText(landingZone, "landingZone");
    }
}
~~~

Đây không phải “mở rộng miễn phí”. Nếu số variant thay đổi thường xuyên do plugin bên ngoài định nghĩa, việc đóng danh sách bằng `sealed` có thể là một giới hạn không phù hợp. Khi đó, cân nhắc interface mở cùng hợp đồng hành vi riêng hoặc một cơ chế đăng ký handler theo nhu cầu.

**Đừng thêm `default -> ...` vào mọi `switch` chỉ để tránh lỗi khi thêm subtype.** Một nhánh mặc định quá rộng có thể che đi việc quên cập nhật xử lý một variant quan trọng. Với tập variant đóng, tận dụng kiểm tra exhaustive thường hữu ích hơn.

## 9. Khi nào nên dùng subtype, enum hay đa hình?

| Lựa chọn | Điểm mạnh | Giới hạn/cân nhắc |
| --- | --- | --- |
| `enum` | Đơn giản, phù hợp các nhãn trạng thái hoặc lựa chọn không có dữ liệu đặc thù | Không tự biểu diễn cấu trúc field khác nhau của từng biến thể |
| `sealed interface` + `record` | Tập variant đóng, mỗi subtype có payload riêng, hỗ trợ pattern matching và kiểm tra exhaustive | Thêm subtype cần cập nhật phần xử lý; record phù hợp nhất với dữ liệu kiểu giá trị |
| `sealed abstract class` + class con | Có thể chia sẻ trạng thái/cơ chế chung hoặc quản lý cấu trúc phức tạp | Cần kiểm soát kế thừa, constructor và khả năng thay đổi trạng thái |
| Interface thường + các implementation | Phù hợp hệ thống muốn cho phép plugin/mô-đun ngoài mở rộng | Compiler không có danh sách subtype đóng để bảo đảm exhaustive tương tự |
| Đa hình bằng method trên subtype | Đặt hành vi gần dữ liệu, giúp tránh nhiều switch rải rác | Cần cân nhắc nếu có rất nhiều phép chuyển đổi độc lập và thay đổi thường xuyên |

Với một **domain entity có identity**, lifecycle và trạng thái mutable, không nên vội dùng `record` chỉ vì cú pháp ngắn. Record phù hợp với các **value-like variants** bất biến và dữ liệu truyền qua các tầng. Nếu subtype phải bảo vệ hành vi biến đổi trạng thái có kiểm soát, class với constructor, method và encapsulation rõ ràng có thể là lựa chọn tốt hơn.

## 10. Lỗi mô hình hóa phổ biến

**Lỗi 1 — sử dụng một object “có tất cả field” rồi để phần lớn field bằng null.** Điều này đưa nhiều trạng thái không hợp lệ vào mô hình. Hãy tạo subtype cho những biến thể có dữ liệu bắt buộc khác nhau.

**Lỗi 2 — nghĩ `sealed` thay thế validation.** `sealed` chỉ giới hạn kiểu con trực tiếp; nó không chứng minh rằng `storeId` hợp lệ hay `Address` đầy đủ. Bảo vệ invariant khi khởi tạo.

**Lỗi 3 — đặt cờ của một variant vào interface chung.** Cờ `express` chỉ thuộc giao tại nhà. Nếu mọi kiểu giao hàng đều có nó, những tổ hợp vô nghĩa sẽ xuất hiện.

**Lỗi 4 — dùng `default` che lỗi quên xử lý variant.** Một `switch expression` exhaustive trên tập subtype đóng mang lại giá trị kiểm tra từ compiler. Đừng bỏ lợi ích đó một cách vô thức.

**Lỗi 5 — bỏ qua selector `null`.** `null` không tự trở thành subtype của interface. Quyết định rõ hợp đồng: từ chối sớm bằng `requireNonNull`, xử lý bằng `case null` nếu nghiệp vụ cho phép, hoặc xác nhận dữ liệu đầu vào ở biên hệ thống.

**Lỗi 6 — hiểu nhầm record là deep immutable.** Record tạo field final nhưng component có thể tham chiếu đến object mutable. Nếu domain đòi bất biến sâu hơn, cần chủ động thiết kế.

**Lỗi 7 — lạm dụng một `switch` khổng lồ cho tất cả nghiệp vụ.** Nếu các hành vi thực sự thuộc về từng subtype, cân nhắc đa hình. Dùng pattern matching khi cần **phân loại, biến đổi, tích hợp hoặc trình bày** các variant với một kết quả rõ ràng.

**Lỗi 8 — xem mọi giá trị cùng cấp là một subtype.** Ví dụ một trạng thái có 3 mức ưu tiên nhưng không có dữ liệu khác biệt; tạo ba class chỉ để thay một enum có thể khiến mô hình cồng kềnh vô ích.

## 11. Checklist áp dụng trong dự án thực tế

Trước khi triển khai variant bằng subtype, tự trả lời:

1. Đã liệt kê đầy đủ **các variant hợp lệ** trong phạm vi domain hiện tại chưa?
2. Mỗi variant có đúng **các field bắt buộc** của chính nó, không mang field chỉ dùng ở variant khác?
3. Constructor/factory đã kiểm tra các invariant như null, trắng, giới hạn giá trị, quan hệ giữa các field?
4. Có cần một tập variant **đóng** không? Nếu cần, `sealed` có phù hợp với nhu cầu mở rộng và đóng gói module?
5. Mỗi `switch` xử lý variant có exhaustive không? Có nhánh `default` đang vô tình che một subtype mới?
6. Đã định nghĩa rõ xử lý `null` ở ranh giới hệ thống chưa?
7. Có test cho **từng subtype**, dữ liệu hợp lệ, không hợp lệ và các trường hợp biên?
8. Payload có chứa object mutable không? Có cần phòng vệ để giữ invariant qua thời gian?
9. Các quy tắc nghiệp vụ nên được đặt trên subtype hay xử lý tập trung bằng pattern matching?
10. Khi thêm variant mới, quy trình review và kiểm thử có đảm bảo các điểm liên quan được cập nhật không?

### Bài tập mở rộng

- Thêm subtype `CurbsidePickup(String storeId, String parkingSpot)`: cả hai chuỗi phải không trắng. Cập nhật `permits`, `fee`, `route` và kiểm thử.
- Đổi `HomeDelivery` thành một kiểu chứa thêm `deliveryWindow`, đồng thời thêm validation không cho phép cửa sổ giao hàng trống. Kiểm tra xem những chỗ dùng record pattern cần cập nhật cấu trúc như thế nào.
- Thử xóa nhánh `ParcelLocker` khỏi `switch expression` không có `default` và quan sát lỗi compiler về tính exhaustive.
- Viết một handler kiểu `DeliveryOption -> String` trả về thông điệp hiển thị, rồi quyết định liệu logic ấy nên ở một `switch` tập trung hay trong method đa hình.

**Ghi nhớ:** Mô hình hóa variant bằng subtype là cách đưa **sự khác biệt về cấu trúc và invariant** vào hệ thống kiểu Java. `sealed interface` giúp xác định tập variant được kiểm soát; `record` chứa payload bất biến dạng giá trị; constructor bảo vệ trạng thái hợp lệ; và pattern matching trong `switch`/record pattern xử lý từng loại một cách rõ ràng, có hỗ trợ kiểm tra exhaustive khi phù hợp.