# Đa hình và nhiều cách thực hiện cùng một thao tác trong Java

Trong lập trình hướng đối tượng (OOP), **đa hình (polymorphism)** cho phép một đoạn mã gửi **cùng một lời gọi phương thức** tới các đối tượng khác nhau, nhưng mỗi đối tượng thực hiện công việc theo cách phù hợp với loại của nó.

Ví dụ, một hệ thống bán hàng phải tính phí giao hàng. Đối với cùng một kiện hàng, giao tiêu chuẩn, giao hỏa tốc và giao tiết kiệm sẽ có công thức giá và thời gian giao dự kiến khác nhau. Thay vì để màn hình thanh toán tự kiểm tra `if (loaiGiaoHang == ...)` rồi tính từng công thức, ta định nghĩa một hợp đồng `ShippingPolicy.quote(parcel)` và để **mỗi implementation tự chịu trách nhiệm** cho cách tính của mình.

Điểm cần nắm:

- **Thao tác chung**: `quote(Parcel)` — yêu cầu một báo giá giao hàng.
- **Các cách thực hiện khác nhau**: `StandardShipping`, `ExpressShipping`, `EconomyShipping`.
- **Mã sử dụng chung**: chỉ biết `ShippingPolicy`, không cần biết chi tiết công thức.
- **Khi chạy**: Java gọi implementation thích hợp với **kiểu thực tế của đối tượng** mà tham chiếu đang trỏ tới.

## 1. Một hành động, nhiều hành vi

Hợp đồng có thể biểu diễn bằng interface:

~~~java
interface ShippingPolicy {
    ShippingQuote quote(Parcel parcel);
}
~~~

Ba kiểu giao hàng hiện thực hóa cùng một phương thức:

~~~java
class StandardShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        // Tính phí tiêu chuẩn.
        // ...
        return null; // Chỉ là đoạn khung minh họa, không phải code hoàn chỉnh.
    }
}

class ExpressShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        // Tính phí hỏa tốc.
        // ...
        return null; // Đoạn khung.
    }
}
~~~

Phần mã dùng chung:

~~~java
ShippingPolicy policy = /* một đối tượng triển khai ShippingPolicy */;
ShippingQuote result = policy.quote(parcel);
~~~

Câu lệnh gọi **không đổi** khi thay `policy` từ một đối tượng `StandardShipping` thành `ExpressShipping`. Điều khác nhau nằm ở **implementation** của phương thức được chọn.

Đa hình dựa trên phương thức instance được override/implement thường được gọi là **đa hình động** (*runtime polymorphism*). Không phải Java nhìn tên biến `policy` để lựa chọn; nó căn cứ vào **đối tượng thực tế** đang được tham chiếu.

## 2. Ví dụ Java hoàn chỉnh: nhiều chiến lược tính phí giao hàng

Giả sử hệ thống hỗ trợ ba gói dịch vụ:

| Gói | Phí cơ bản ở nội thành | Phí cơ bản ở ngoại thành | Phụ phí theo khối lượng | Thời gian dự kiến |
| --- | ---: | ---: | --- | --- |
| Tiết kiệm | 18.000đ | 28.000đ | 2.000đ cho mỗi kg bắt đầu **sau kg đầu tiên** | 4–6 ngày |
| Tiêu chuẩn | 20.000đ | 35.000đ | 5.000đ cho mỗi kg bắt đầu **sau kg đầu tiên** | 2–4 ngày |
| Hỏa tốc | 50.000đ | 70.000đ | 15.000đ cho mỗi 500 g bắt đầu, **kể cả 500 g đầu** | 1 ngày |

Đây là các **con số giả định** để luyện Java, không phải biểu phí của hãng vận chuyển. Mỗi chính sách hỗ trợ cả hai khu vực để các implementation có thể được sử dụng thay thế nhau theo hợp đồng chung.

Lưu đoạn dưới đây thành **`ShippingPolymorphismDemo.java`**. Mã chạy độc lập với **Java 11+**, chỉ cần JDK.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

public class ShippingPolymorphismDemo {

    enum Zone {
        INNER_CITY, OUTER_CITY
    }

    // Dữ liệu kiện hàng: không sửa được sau khi tạo.
    static final class Parcel {
        private final String trackingCode;
        private final int weightGrams;
        private final Zone zone;

        Parcel(String trackingCode, int weightGrams, Zone zone) {
            String code = Objects.requireNonNull(
                    trackingCode, "trackingCode").trim();
            if (code.isEmpty()) {
                throw new IllegalArgumentException("Mã kiện hàng bị rỗng");
            }
            if (weightGrams <= 0) {
                throw new IllegalArgumentException(
                        "Khối lượng phải lớn hơn 0");
            }
            this.trackingCode = code;
            this.weightGrams = weightGrams;
            this.zone = Objects.requireNonNull(zone, "zone");
        }

        int getWeightGrams() {
            return weightGrams;
        }

        Zone getZone() {
            return zone;
        }
    }

    // Kết quả dùng chung, bất kể cách tính phí.
    static final class ShippingQuote {
        private final String serviceName;
        private final BigDecimal feeVnd;
        private final int estimatedDays;

        ShippingQuote(String serviceName, BigDecimal feeVnd,
                      int estimatedDays) {
            this.serviceName = Objects.requireNonNull(
                    serviceName, "serviceName");
            this.feeVnd = Objects.requireNonNull(feeVnd, "feeVnd");
            if (feeVnd.signum() < 0 || estimatedDays <= 0) {
                throw new IllegalArgumentException(
                        "Báo giá hoặc thời gian không hợp lệ");
            }
            this.estimatedDays = estimatedDays;
        }

        String getServiceName() {
            return serviceName;
        }

        BigDecimal getFeeVnd() {
            return feeVnd;
        }

        int getEstimatedDays() {
            return estimatedDays;
        }
    }

    // Hợp đồng chung cho MỌI chính sách giao hàng.
    interface ShippingPolicy {
        ShippingQuote quote(Parcel parcel);
    }

    static final class EconomyShipping implements ShippingPolicy {
        @Override
        public ShippingQuote quote(Parcel parcel) {
            Objects.requireNonNull(parcel, "parcel");

            long extraKg = (parcel.getWeightGrams() - 1L) / 1000L;
            long base = parcel.getZone() == Zone.INNER_CITY
                    ? 18_000L : 28_000L;
            long fee = base + extraKg * 2_000L;
            int days = parcel.getZone() == Zone.INNER_CITY ? 4 : 6;

            return new ShippingQuote(
                    "Tiết kiệm", BigDecimal.valueOf(fee), days);
        }
    }

    static final class StandardShipping implements ShippingPolicy {
        @Override
        public ShippingQuote quote(Parcel parcel) {
            Objects.requireNonNull(parcel, "parcel");

            long extraKg = (parcel.getWeightGrams() - 1L) / 1000L;
            long base = parcel.getZone() == Zone.INNER_CITY
                    ? 20_000L : 35_000L;
            long fee = base + extraKg * 5_000L;
            int days = parcel.getZone() == Zone.INNER_CITY ? 2 : 4;

            return new ShippingQuote(
                    "Tiêu chuẩn", BigDecimal.valueOf(fee), days);
        }
    }

    static final class ExpressShipping implements ShippingPolicy {
        @Override
        public ShippingQuote quote(Parcel parcel) {
            Objects.requireNonNull(parcel, "parcel");

            long unitsOf500g =
                    (parcel.getWeightGrams() + 499L) / 500L;
            long base = parcel.getZone() == Zone.INNER_CITY
                    ? 50_000L : 70_000L;
            long fee = base + unitsOf500g * 15_000L;

            return new ShippingQuote(
                    "Hỏa tốc", BigDecimal.valueOf(fee), 1);
        }
    }

    // Mã sử dụng chỉ phụ thuộc vào hợp đồng ShippingPolicy.
    static final class CheckoutService {
        private final ShippingPolicy policy;

        CheckoutService(ShippingPolicy policy) {
            this.policy = Objects.requireNonNull(policy, "policy");
        }

        ShippingQuote estimate(Parcel parcel) {
            return policy.quote(parcel);
        }
    }

    public static void main(String[] args) {
        Parcel parcel = new Parcel(
                "PK-001", 1500, Zone.INNER_CITY);

        List<ShippingPolicy> policies = List.of(
                new EconomyShipping(),
                new StandardShipping(),
                new ExpressShipping());

        for (ShippingPolicy policy : policies) {
            CheckoutService checkout = new CheckoutService(policy);
            ShippingQuote quote = checkout.estimate(parcel);

            System.out.println(
                    quote.getServiceName() + ": "
                    + quote.getFeeVnd().toPlainString() + " VND"
                    + ", dự kiến " + quote.getEstimatedDays() + " ngày");
        }
    }
}
~~~

Chạy:

~~~bash
javac ShippingPolymorphismDemo.java
java ShippingPolymorphismDemo
~~~

Kết quả:

~~~text
Tiết kiệm: 20000 VND, dự kiến 4 ngày
Tiêu chuẩn: 25000 VND, dự kiến 2 ngày
Hỏa tốc: 95000 VND, dự kiến 1 ngày
~~~

### Kiểm tra phép tính

Kiện hàng có khối lượng **1.500 g**, khu vực **nội thành**:

- **Tiết kiệm**: 18.000 + 1 × 2.000 = **20.000 VND**, vì có 1 kg bắt đầu sau kg đầu.
- **Tiêu chuẩn**: 20.000 + 1 × 5.000 = **25.000 VND**.
- **Hỏa tốc**: 50.000 + 3 × 15.000 = **95.000 VND**, vì 1.500 g có ba đơn vị 500 g.

Các phương thức cùng trả `ShippingQuote`, nên phần mã thanh toán có thể nhận và hiển thị báo giá mà **không phải đổi cấu trúc dữ liệu** theo từng gói.

### Tại sao đây là đa hình chứ không chỉ là ba hàm khác nhau?

Điểm chung không đơn thuần là cả ba lớp có tên phương thức `quote`. Cả ba **cùng `implements ShippingPolicy`**, tạo ra một hợp đồng kiểu rõ ràng.

Trong vòng lặp:

~~~java
for (ShippingPolicy policy : policies) {
    ShippingQuote quote = policy.quote(parcel);
}
~~~

Tại mỗi lần lặp:

| Lần | Kiểu khai báo của `policy` | Đối tượng thực tế | Implementation của `quote` được chạy |
| --- | --- | --- | --- |
| 1 | `ShippingPolicy` | `EconomyShipping` | `EconomyShipping.quote` |
| 2 | `ShippingPolicy` | `StandardShipping` | `StandardShipping.quote` |
| 3 | `ShippingPolicy` | `ExpressShipping` | `ExpressShipping.quote` |

**Một lời gọi ở phía sử dụng, nhiều hành vi ở phía triển khai**: đó là biểu hiện rất điển hình của đa hình động.

## 3. Quan hệ kiểu và cách Java lựa chọn hành vi

~~~mermaid
classDiagram
    class ShippingPolicy {
        <<interface>>
        +quote(Parcel) ShippingQuote
    }
    class EconomyShipping {
        +quote(Parcel) ShippingQuote
    }
    class StandardShipping {
        +quote(Parcel) ShippingQuote
    }
    class ExpressShipping {
        +quote(Parcel) ShippingQuote
    }
    class CheckoutService {
        -policy ShippingPolicy
        +estimate(Parcel) ShippingQuote
    }
    ShippingPolicy <|.. EconomyShipping
    ShippingPolicy <|.. StandardShipping
    ShippingPolicy <|.. ExpressShipping
    CheckoutService --> ShippingPolicy : depends on
~~~

Mũi tên tam giác nét đứt biểu diễn quan hệ **implements**. `CheckoutService` giữ một tham chiếu kiểu `ShippingPolicy`; nó không cần giữ riêng ba field cho ba gói.

Khi chạy một lần tính phí:

~~~mermaid
sequenceDiagram
    actor App as Main
    participant Checkout as CheckoutService
    participant Policy as ShippingPolicy
    participant Express as ExpressShipping

    App->>Checkout: estimate(parcel)
    Checkout->>Policy: quote(parcel)
    Note over Policy,Express: Tham chiếu có kiểu ShippingPolicy<br/>nhưng object thực là ExpressShipping
    Policy->>Express: Dispatch tới ExpressShipping.quote()
    Express-->>Policy: ShippingQuote(95000, 1)
    Policy-->>Checkout: ShippingQuote
    Checkout-->>App: ShippingQuote
~~~

Sơ đồ dùng `ShippingPolicy` như một **vai trò hợp đồng**, không ngụ ý rằng Java tạo thêm một instance của interface. Trong lần chạy thực tế, lời gọi được thực hiện trên chính instance `ExpressShipping` mà `CheckoutService.policy` trỏ đến.

### Phân biệt kiểu tĩnh và kiểu runtime

~~~java
ShippingPolicy policy = new ExpressShipping();
~~~

- Kiểu **tĩnh** của biến `policy` là `ShippingPolicy`: compiler cho phép gọi những phương thức được giao diện khai báo, ví dụ `quote`.
- Kiểu **thực tế** của object là `ExpressShipping`: khi gọi `policy.quote(...)`, phần triển khai của `ExpressShipping` được sử dụng.

Nếu lớp cụ thể có phương thức riêng không thuộc interface:

~~~java
class DebugShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        return new ShippingQuote("Debug", BigDecimal.ZERO, 1);
    }

    public void resetDebugCounters() {
        System.out.println("Đã reset");
    }
}
~~~

~~~java
ShippingPolicy policy = new DebugShipping();
policy.quote(parcel); // Hợp lệ.

// policy.resetDebugCounters(); // Lỗi biên dịch: interface không khai báo.
~~~

Compiler dựa vào **kiểu tham chiếu** để xác định thao tác có thể gọi; khi đã gọi một phương thức instance được implement/override, **kiểu runtime** quyết định cách thực hiện.

## 4. Thay câu hỏi “đây là loại gì?” bằng “hãy thực hiện thao tác”

Nếu phần thanh toán liên tục kiểm tra `"ECONOMY"`, `"STANDARD"`, `"EXPRESS"` để lặp lại cách tính, mỗi chính sách mới làm nhiều nơi phải sửa. Thay vào đó, người sử dụng chỉ yêu cầu:

~~~java
ShippingQuote quote = policy.quote(parcel);
~~~

Còn nơi lựa chọn gói giao hàng **vẫn có thể dùng** `switch`, `Map<String,ShippingPolicy>` hoặc cấu hình:

~~~java
Map<String, ShippingPolicy> options = Map.of(
    "economy", new EconomyShipping(),
    "express", new ExpressShipping()
);
ShippingPolicy selected = options.get("express");
if (selected == null) throw new IllegalArgumentException("Gói không hợp lệ");
ShippingQuote quote = selected.quote(parcel);
~~~

Đoạn mã minh họa này cần `import java.util.Map;` và đặt trong phương thức Java phù hợp. **Nhánh chọn chiến lược ở ranh giới** không đồng nghĩa với việc phải dạy lại công thức trong mọi service. Bài *Đa hình thay cho điều kiện kiểm tra từng loại* phân tích từng bước refactor, test hồi quy và các trường hợp một `if/switch` vẫn là lựa chọn tốt.

## 5. `@Override` xác nhận mối nối giữa hợp đồng và implementation

Mỗi `ShippingPolicy` cụ thể phải cung cấp `public ShippingQuote quote(Parcel)`. Annotation `@Override` cho phép trình biên dịch bắt lỗi gõ nhầm hoặc sai danh sách tham số:

~~~java
class ExampleShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        return new ShippingQuote("Mẫu", BigDecimal.ZERO, 1);
    }
}
~~~

Ví dụ này đặt lớp `ExampleShipping` **bên trong** `ShippingPolymorphismDemo` để dùng trực tiếp các kiểu lồng từ chương trình chính (và `BigDecimal` đã import); nếu tách ra lớp top-level, cần định danh đúng các kiểu lồng. Nếu đổi `quote(Parcel)` thành `quote(String)`, nó không còn thực hiện chữ ký bắt buộc. Compiler kiểm tra kiểu, phạm vi truy cập, kiểu trả về và checked exception tương thích; **không chứng minh** được quy tắc phí không âm, thời gian hợp lệ, tác dụng phụ hoặc kết quả nghiệp vụ. Bài *Ghi đè và lựa chọn phương thức khi chạy* đi sâu vào điều kiện override, `final` và lời gọi `super`.

## 6. Ghi đè không phải là nạp chồng

~~~java
class Animal {
    String sound() { return "Âm thanh"; }
}
class Dog extends Animal {
    @Override String sound() { return "Gâu"; }
}
Animal a = new Dog();
System.out.println(a.sound()); // Gâu
~~~

Đây là **override**: cùng chữ ký `sound()`, implementation được chọn theo đối tượng `Dog` lúc chạy. Ngược lại, `print(Object)` và `print(String)` là **overload**, tức hai chữ ký khác tham số; compiler quyết định chọn cái nào bằng kiểu tĩnh ở chỗ gọi. Vì vậy `Object text = "Java"; print(text)` sẽ chọn overload `Object` khi cả hai tồn tại, dù object thực là `String`.

Một lời gọi Java có thể cần **hai bước**: chọn overload khi biên dịch, sau đó dispatch tới override của chữ ký đã chọn lúc chạy. Bài *Phân giải phương thức tĩnh và phân giải động* trình bày cơ chế hai bước; bài *Phân biệt ghi đè với nạp chồng* cung cấp các phép thử cụ thể.

## 7. Hợp đồng chung có thể là interface hoặc lớp cha

`ShippingPolicy` biểu thị một khả năng nên phù hợp với `interface` trong ví dụ chính. Nếu nhiều kiểu vận chuyển thật sự chia sẻ constructor, trạng thái và một phần công thức chung, có thể thêm abstract class `implements ShippingPolicy` để chia sẻ thuật toán nền. Khi đó class cụ thể có thể chỉ override một hook được chỉ định.

Không cần tạo abstract superclass chỉ để hai phương thức tình cờ có vài dòng giống nhau: kế thừa kéo theo những cam kết giữa cha và con. Với các chiến lược có thể thay thế độc lập, interface kết hợp composition thường dễ bảo trì hơn. Dù cách nào, các lớp vẫn phải giữ cùng hợp đồng `quote(Parcel)`.

## 8. Chọn implementation ở nơi lắp ghép ứng dụng

~~~java
CheckoutService standard =
    new CheckoutService(new StandardShipping());
CheckoutService express =
    new CheckoutService(new ExpressShipping());
~~~

Hai đối tượng `CheckoutService` khác nhau cùng sử dụng kiểu dependency `ShippingPolicy`. Mỗi lần gọi `estimate(parcel)` chuyển tới phương thức `quote` của policy đã được cung cấp, nên checkout không phải biết công thức hoặc class cụ thể.

Đó là constructor injection đơn giản, có thể thực hiện bằng Java thuần. Nó tạo lợi ích thay thế và kiểm thử khi hợp đồng thực sự rõ ràng; việc thêm một policy mới vẫn có thể đòi hỏi đăng ký ở nơi lựa chọn, cập nhật giao diện và viết test cho công thức mới.

## 9. Những hiểu nhầm cần nhận diện trước khi đi sâu

| Nhận định | Điều đúng trong Java |
|---|---|
| Hai class cùng có `quote(Parcel)` tự dùng được như `ShippingPolicy` | Cần quan hệ `implements`/`extends` hợp lệ hoặc adapter; Java nominal typing |
| Thêm overload `quote(String)` ở class con làm `quote(Parcel)` đổi hành vi | Không; override phải đúng chữ ký |
| Static method hay public field cùng tên cũng đa hình động | Không; static/field có quy tắc hiding và compile-time lookup |
| Dùng `instanceof` khắp nơi mới chọn được class cụ thể | Nếu đã có `ShippingPolicy.quote`, gọi trực tiếp phương thức đó |
| Mọi implementation đều biên dịch thì chắc chắn thay thế an toàn | Còn cần giữ precondition, kết quả, lỗi và tác dụng phụ của hợp đồng |

Bài về *Phân biệt che khuất thành viên với ghi đè* và *Phạm vi đa hình của phương thức và thuộc tính* minh họa riêng các trường hợp field, static, private và getter. Bài này chỉ cần nhớ quy tắc nền: **đa hình động xảy ra với lời gọi instance method thuộc hợp đồng và có implementation thích hợp theo object runtime**.

## 10. Kiểm thử hợp đồng qua nhiều implementation

Khi nhiều lớp cùng thực hiện `ShippingPolicy`, thay vì chỉ kiểm thử riêng từng công thức, hãy kiểm tra **hợp đồng chung**. Ví dụ dưới đây dùng **JUnit 5**, cần dependency JUnit Jupiter và test runner phù hợp.

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class ShippingPolicyContractTest {

    @Test
    void everyPolicyReturnsAValidQuote() {
        ShippingPolymorphismDemo.Parcel parcel =
                new ShippingPolymorphismDemo.Parcel(
                        "PK-TEST", 1500,
                        ShippingPolymorphismDemo.Zone.INNER_CITY);

        List<ShippingPolymorphismDemo.ShippingPolicy> policies =
                List.of(
                        new ShippingPolymorphismDemo.EconomyShipping(),
                        new ShippingPolymorphismDemo.StandardShipping(),
                        new ShippingPolymorphismDemo.ExpressShipping());

        for (ShippingPolymorphismDemo.ShippingPolicy policy : policies) {
            ShippingPolymorphismDemo.ShippingQuote quote =
                    policy.quote(parcel);

            assertNotNull(quote);
            assertTrue(quote.getFeeVnd().signum() >= 0);
            assertTrue(quote.getEstimatedDays() > 0);
        }
    }
}
~~~

Một test bổ sung nên kiểm tra các **trường hợp biên**: 1 g, 500 g, 501 g, 1.000 g, 1.001 g; nội thành/ngoại thành; `null`; và các con số lớn. Ví dụ đã dùng phép toán `long` trong tính phí để giảm nguy cơ overflow khi cộng đơn vị trọng lượng với số cố định.

Để kiểm thử `CheckoutService` độc lập với công thức giá, tạo một implementation giả của `ShippingPolicy` trả một `ShippingQuote` biết trước. Nếu `CheckoutService.estimate` trả đúng giá trị và gọi chính sách đúng cách, phần điều phối đang hoạt động theo hợp đồng, không phụ thuộc vào lớp `ExpressShipping` cụ thể.

## 11. Câu hỏi tự luyện có lời giải

**1.** Nếu `ShippingPolicy p = new ExpressShipping();`, câu lệnh `p.quote(parcel)` sử dụng công thức của lớp nào?

**Đáp án:** `ExpressShipping`, do object runtime là `ExpressShipping`. Kiểu biến `ShippingPolicy` chỉ xác định API có thể gọi.

**2.** Thêm `SameDayShipping implements ShippingPolicy` có buộc sửa `CheckoutService.estimate` không?

**Đáp án:** Thường không nếu implementation mới thực hiện đúng hợp đồng. Cần đăng ký/lựa chọn chiến lược mới ở nơi cấu hình thích hợp; code chỉ gọi `policy.quote(parcel)` vẫn giữ nguyên.

**3.** Một lớp `class LegacyShipping` có `quote(Parcel)` cùng chữ ký, nhưng không `implements ShippingPolicy`. Truyền nó vào constructor `CheckoutService(ShippingPolicy)` được không?

**Đáp án:** Không theo hệ kiểu Java thông thường. Cần cho lớp implements hợp đồng nếu sửa được mã, hoặc dùng adapter phù hợp nếu không sửa được.

**4.** Vì sao đoạn `Printer.print(Object)` và `Printer.print(String)` minh họa overload chứ không phải chọn theo runtime?

**Đáp án:** Compiler chọn chữ ký dựa vào **kiểu tĩnh của đối số** ở nơi gọi. Nó không tự chọn `String` overload chỉ vì biến `Object` đang tham chiếu tới một chuỗi.

**5.** Tại sao việc có cùng tên phương thức `quote` chưa chắc đủ để thay thế nhiều implementation trong hệ thống bán hàng?

**Đáp án:** Phải có quan hệ kiểu hợp lệ và tuân thủ cùng hợp đồng ngữ nghĩa: dữ liệu đầu vào, đơn vị tiền, kết quả, quy tắc lỗi và tác động phụ. Nếu một implementation bất ngờ sửa `Parcel` hay trả giá âm, khả năng thay thế thực tế bị hỏng.

**6.** Với kiện 1.500 g nội thành, tại sao ví dụ cho ra 20.000đ tiết kiệm, 25.000đ tiêu chuẩn, 95.000đ hỏa tốc?

**Đáp án:** Mỗi chính sách dùng biểu phí và đơn vị trọng lượng khác nhau, dù cùng nhận một `Parcel` và cùng trả một `ShippingQuote`.

**7.** Nếu một phương thức của subclass được đánh dấu `static` trùng tên với static method lớp cha, có phải runtime đa hình không?

**Đáp án:** Không. Đây là method hiding; cách gọi tĩnh gắn với tên class/kiểu biểu thức, không phải dynamic dispatch cho method instance.

**8.** Khi muốn chọn chính sách theo lựa chọn trên UI, có được dùng `Map` hoặc `switch` để tạo đúng implementation không?

**Đáp án:** Được. Đó là **bước lựa chọn đối tượng**. Điều nên tránh là lặp lại toàn bộ công thức tính phí cho từng loại ở mọi nơi dùng thay vì ủy quyền cho `quote`.

## Kết luận

Đa hình không làm các đối tượng trở nên giống nhau; nó cho phép **sử dụng chúng thông qua cùng một hợp đồng** trong khi mỗi đối tượng giữ cách thực thi phù hợp với mình.

Với Java, hãy ghi nhớ công thức tư duy:

**Interface hoặc lớp cha định nghĩa “có thể yêu cầu làm gì” → các lớp cụ thể định nghĩa “làm như thế nào” → mã sử dụng chỉ gọi phương thức chung → runtime chọn phần triển khai dựa trên object thực tế.**

Khi đọc code OOP, tìm một tham chiếu kiểu cha/interface, một lời gọi instance method và nhiều lớp override/implement phương thức đó. Đó thường là nơi đa hình đang loại bỏ những nhánh kiểm tra loại và giúp hệ thống mở rộng linh hoạt hơn.