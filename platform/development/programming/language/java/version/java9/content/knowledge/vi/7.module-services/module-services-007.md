# Chọn nhà cung cấp khi có nhiều phần triển khai bằng JPMS

Trong một ứng dụng mô-đun, một service thường có nhiều phần triển khai. Ví dụ, ứng dụng thanh toán có thể hỗ trợ nhà cung cấp thẻ, chuyển khoản ngân hàng hoặc một cổng thanh toán bên ngoài. Mã nghiệp vụ nên phụ thuộc vào **service interface** và chọn một implementation theo chính sách của ứng dụng, thay vì gắn cứng với một class cụ thể.

Java cung cấp `ServiceLoader` để khám phá các nhà cung cấp service. Trong JPMS, mô-đun tiêu thụ khai báo `uses`, còn từng mô-đun cung cấp khai báo `provides ... with ...`. Khi có nhiều provider, ứng dụng có thể đọc metadata của chúng và áp dụng quy tắc lựa chọn như mức ưu tiên, khả năng hỗ trợ, khu vực, cấu hình hoặc lựa chọn của người dùng.

Điểm quan trọng: `ServiceLoader` chịu trách nhiệm tìm provider; **chính ứng dụng định nghĩa provider nào được chọn**. Không nên xem thứ tự khám phá provider là chính sách nghiệp vụ.

## 1. Tách service interface khỏi các implementation

Giả sử ứng dụng cần một service `PaymentProvider`:

```java
package com.acme.payment.api;

public interface PaymentProvider {
    String id();
    String charge(String invoiceId);
}
```

Mô-đun chứa interface là hợp đồng chung. Các implementation có thể nằm trong những mô-đun độc lập và được triển khai, thay thế hoặc bổ sung mà không cần sửa mã gọi service.

Ví dụ:

- `com.acme.payment.card` cung cấp xử lý thanh toán bằng thẻ.
- `com.acme.payment.bank` cung cấp xử lý thanh toán qua ngân hàng.
- `com.acme.payment.app` là ứng dụng tiêu thụ service.

Cấu trúc này tránh việc ứng dụng phải viết các nhánh phụ thuộc trực tiếp như `new CardProvider()` hoặc `new BankProvider()`. Ứng dụng chỉ biết interface `PaymentProvider`.

## 2. Khai báo service trong module descriptor

Mô-đun API export package chứa interface để các mô-đun khác có thể đọc và sử dụng:

**`src/com.acme.payment.api/module-info.java`:**

```java
module com.acme.payment.api {
    exports com.acme.payment.api;
}
```

Mô-đun triển khai thẻ khai báo phụ thuộc vào API và đăng ký provider:

**`src/com.acme.payment.card/module-info.java`:**

```java
module com.acme.payment.card {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProvider
        with com.acme.payment.card.CardProvider;
}
```

Mô-đun triển khai ngân hàng đăng ký một provider khác:

**`src/com.acme.payment.bank/module-info.java`:**

```java
module com.acme.payment.bank {
    requires com.acme.payment.api;

    provides com.acme.payment.api.PaymentProvider
        with com.acme.payment.bank.BankProvider;
}
```

Mô-đun ứng dụng khai báo rằng nó sử dụng service:

**`src/com.acme.payment.app/module-info.java`:**

```java
module com.acme.payment.app {
    requires com.acme.payment.api;

    uses com.acme.payment.api.PaymentProvider;
}
```

Hai chỉ thị có vai trò riêng:

- `provides S with P;` đăng ký class `P` làm provider của service `S`.
- `uses S;` khai báo rằng mô-đun hiện tại sẽ tìm và sử dụng service `S`.

Mô-đun ứng dụng không cần khai báo `requires com.acme.payment.card` hoặc `requires com.acme.payment.bank` chỉ để gọi service qua `ServiceLoader`. Các provider module có thể được liên kết vào đồ thị mô-đun nhờ service binding khi mô-đun đã phân giải khai báo `uses` service đó và provider có mặt trên module path.

## 3. Viết các provider độc lập

Mỗi provider triển khai cùng một interface. Ví dụ, provider thẻ:

**`src/com.acme.payment.card/com/acme/payment/card/CardProvider.java`:**

```java
package com.acme.payment.card;

import com.acme.payment.api.PaymentProvider;
import com.acme.payment.api.Priority;

@Priority(100)
public final class CardProvider implements PaymentProvider {
    public CardProvider() {}

    @Override
    public String id() {
        return "card";
    }

    @Override
    public String charge(String invoiceId) {
        return "card charged " + invoiceId;
    }
}
```

Provider ngân hàng:

**`src/com.acme.payment.bank/com/acme/payment/bank/BankProvider.java`:**

```java
package com.acme.payment.bank;

import com.acme.payment.api.PaymentProvider;
import com.acme.payment.api.Priority;

@Priority(50)
public final class BankProvider implements PaymentProvider {
    public BankProvider() {}

    @Override
    public String id() {
        return "bank";
    }

    @Override
    public String charge(String invoiceId) {
        return "bank charged " + invoiceId;
    }
}
```

Trong ví dụ này, `@Priority` là annotation do ứng dụng định nghĩa để mô tả thứ tự ưu tiên. Giá trị càng lớn thì provider càng được ưu tiên. Annotation không phải quy tắc ưu tiên được `ServiceLoader` tự hiểu; nó là metadata mà ứng dụng sẽ đọc và sử dụng trong comparator.

Định nghĩa annotation trong mô-đun API:

**`src/com.acme.payment.api/com/acme/payment/api/Priority.java`:**

```java
package com.acme.payment.api;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
public @interface Priority {
    int value();
}
```

`RetentionPolicy.RUNTIME` cho phép đọc annotation bằng reflection khi ứng dụng đang chạy. Package chứa annotation được export bởi mô-đun API, nên mô-đun ứng dụng có thể tham chiếu kiểu `Priority`.

Provider implementation có thể nằm trong package không export. Consumer chỉ cần biết interface và metadata công khai; không cần import class triển khai trực tiếp. Provider class trong ví dụ có constructor không tham số public để `ServiceLoader` có thể khởi tạo nó theo cơ chế provider constructor.

## 4. Khám phá và chọn provider bằng `ServiceLoader`

Từ Java 9, `ServiceLoader` có phương thức `stream()`, trả về các `ServiceLoader.Provider<S>`. Mỗi đối tượng provider cho phép:

- `type()`: lấy class của provider để kiểm tra metadata mà chưa tạo instance.
- `get()`: khởi tạo và trả về instance của service.

Đây là điểm hữu ích khi có nhiều implementation. Ứng dụng có thể đọc annotation hoặc metadata của từng provider, xếp hạng chúng rồi chỉ gọi `get()` cho provider được chọn.

**`src/com.acme.payment.app/com/acme/payment/app/Main.java`:**

```java
package com.acme.payment.app;

import com.acme.payment.api.PaymentProvider;
import com.acme.payment.api.Priority;
import java.util.Comparator;
import java.util.ServiceLoader;

public final class Main {
    private static int priorityOf(
            ServiceLoader.Provider<PaymentProvider> provider) {
        Priority priority =
            provider.type().getAnnotation(Priority.class);

        return priority == null ? 0 : priority.value();
    }

    public static void main(String[] args) {
        PaymentProvider selected = ServiceLoader
            .load(PaymentProvider.class)
            .stream()
            .min(Comparator.comparingInt(Main::priorityOf)
                .reversed()
                .thenComparing(provider -> provider.type().getName()))
            .orElseThrow(() -> new IllegalStateException(
                "No PaymentProvider is available"))
            .get();

        System.out.println("Selected: " + selected.id());
        System.out.println(selected.charge("INV-85"));
    }
}
```

Quy tắc lựa chọn trong ví dụ:

1. `ServiceLoader.load(PaymentProvider.class)` tạo loader cho service.
2. `stream()` lấy luồng các provider descriptor.
3. `provider.type()` cho phép đọc annotation `@Priority` trên class triển khai mà chưa khởi tạo provider.
4. `Comparator.comparingInt(...).reversed()` xếp điểm ưu tiên cao trước.
5. `thenComparing(provider -> provider.type().getName())` dùng tên class đầy đủ làm tiêu chí phụ nếu hai provider có cùng điểm.
6. `min(...)` lấy phần tử đứng đầu theo comparator đã đảo chiều.
7. `get()` chỉ khởi tạo provider đã chọn.

Vì `CardProvider` có priority 100 và `BankProvider` có priority 50, ứng dụng chọn provider thẻ. Tiêu chí phụ theo tên class giúp kết quả vẫn xác định được nếu các provider có cùng priority.

## 5. Biên dịch và chạy ví dụ nhiều mô-đun

Cấu trúc mã nguồn:

```text
src/
├── com.acme.payment.api/
│   ├── module-info.java
│   └── com/acme/payment/api/
│       ├── PaymentProvider.java
│       └── Priority.java
├── com.acme.payment.card/
│   ├── module-info.java
│   └── com/acme/payment/card/CardProvider.java
├── com.acme.payment.bank/
│   ├── module-info.java
│   └── com/acme/payment/bank/BankProvider.java
└── com.acme.payment.app/
    ├── module-info.java
    └── com/acme/payment/app/Main.java
```

Từ thư mục gốc chứa `src/`, tạo thư mục đầu ra và biên dịch các mô-đun:

**PowerShell:**

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --module-source-path src -d out -m com.acme.payment.api,com.acme.payment.card,com.acme.payment.bank,com.acme.payment.app
```

**Bash:**

```bash
mkdir -p out
javac --module-source-path src -d out -m com.acme.payment.api,com.acme.payment.card,com.acme.payment.bank,com.acme.payment.app
```

Chạy ứng dụng:

```bash
java --module-path out -m com.acme.payment.app/com.acme.payment.app.Main
```

Kết quả:

```text
Selected: card
card charged INV-85
```

Có thể thêm `--show-module-resolution` để xem quá trình phân giải. Trong ví dụ này, output có các dòng cho biết `com.acme.payment.app` bind cả `com.acme.payment.card` và `com.acme.payment.bank`. Nhờ vậy, hai provider module có mặt trong module path và được tìm thấy qua service binding.

## 6. Chọn provider theo chính sách thực tế

Priority chỉ là một ví dụ. Trong ứng dụng thực tế, chính sách lựa chọn cần phản ánh yêu cầu nghiệp vụ:

- **Ưu tiên cấu hình:** chọn provider được bật trong cấu hình triển khai.
- **Khả năng hỗ trợ:** chỉ chọn provider hỗ trợ loại giao dịch, tiền tệ hoặc khu vực hiện tại.
- **Sức khỏe dịch vụ:** loại provider đang ngừng hoạt động hoặc không vượt qua kiểm tra sẵn sàng.
- **Ưu tiên người dùng:** dùng provider mà người dùng đã chọn nếu nó vẫn đáp ứng yêu cầu.
- **Fallback:** thử provider dự phòng khi provider ưu tiên không khả dụng.

Nếu lựa chọn dựa trên nhiều thuộc tính, hãy tách policy thành một hàm có thể kiểm thử, ví dụ:

```text
candidate providers
        |
        v
filter by capability and availability
        |
        v
rank by business priority
        |
        v
apply deterministic tie-break
        |
        v
instantiate the selected provider
        |
        v
invoke the service
```

Một số ứng dụng cần thử nhiều provider theo thứ tự thay vì chọn đúng một provider ngay từ đầu. Khi đó, tạo danh sách ứng viên đã sắp xếp, khởi tạo lần lượt và áp dụng chính sách retry/fallback phù hợp. Cần phân biệt lỗi khởi tạo provider với lỗi nghiệp vụ khi gọi `charge()`; hai trường hợp có cách xử lý khác nhau.

Không nên mặc định rằng provider đầu tiên mà `ServiceLoader` khám phá là provider tốt nhất. Thứ tự khám phá không thể hiện priority, mức sẵn sàng hay lựa chọn của người dùng. Nếu kết quả cần ổn định, luôn áp dụng tiêu chí xếp hạng và tie-break do ứng dụng định nghĩa.

## 7. Phạm vi tìm kiếm và vòng đời của ServiceLoader

Cách gọi thông dụng:

```java
ServiceLoader<PaymentProvider> loader =
    ServiceLoader.load(PaymentProvider.class);
```

Cách này sử dụng thread context class loader của thread hiện tại để tìm provider. Với ứng dụng sử dụng nhiều module layer hoặc muốn giới hạn việc tìm kiếm vào một layer cụ thể, có thể dùng overload:

```java
ServiceLoader<PaymentProvider> loader =
    ServiceLoader.load(layer, PaymentProvider.class);
```

Overload nhận `ModuleLayer` giúp ứng dụng chỉ định phạm vi mô-đun cần tìm service. Điều này hữu ích khi ứng dụng tạo layer riêng để nạp plugin hoặc các nhóm mô-đun độc lập.

Các điểm cần nhớ về vòng đời:

- Provider được khám phá và khởi tạo theo nhu cầu; tạo loader không đồng nghĩa với việc mọi provider đã được khởi tạo.
- `stream()` cho phép xem provider descriptor và metadata trước khi gọi `get()`.
- `get()` tạo instance của provider được yêu cầu; tránh gọi `get()` cho tất cả provider nếu chỉ cần chọn một.
- `reload()` xóa cache provider của loader để việc duyệt tiếp theo khám phá lại provider theo loader/layer hiện tại. Nó không tự thêm mô-đun mới vào một module layer đã tồn tại.
- Khi ứng dụng tạo module layer mới, dùng loader gắn với layer đó để khám phá provider trong phạm vi mong muốn.

Trong named module, mô-đun gọi `ServiceLoader` cần khai báo `uses` cho service. Nếu thiếu khai báo này, việc sử dụng service có thể thất bại ở runtime với `ServiceConfigurationError`.

## 8. Lỗi thường gặp và cách xử lý

**Có implementation nhưng không tìm thấy provider**

Kiểm tra module descriptor của provider có `provides Service with Implementation;` hay chưa. Kiểm tra provider module có nằm trên module path và có được phân giải trong runtime configuration hay không.

**Mô-đun tiêu thụ quên `uses`**

Mô-đun gọi `ServiceLoader` phải khai báo `uses` cho đúng service interface. Chỉ có `requires` mô-đun API là chưa đủ.

**Provider không thể khởi tạo**

Kiểm tra provider class có đáp ứng dạng provider được khai báo, ví dụ class public với public no-argument constructor trong ví dụ này. Nếu constructor hoặc quá trình khởi tạo ném exception, việc lấy provider có thể phát sinh `ServiceConfigurationError`.

**Chọn sai provider khi có nhiều implementation**

Không dùng `findFirst()` như một chính sách ưu tiên. Đọc metadata, lọc theo điều kiện nghiệp vụ, xếp hạng và đặt tie-break rõ ràng.

**Khởi tạo tất cả provider quá sớm**

Nếu gọi `.map(ServiceLoader.Provider::get)` trước khi lọc hoặc sắp xếp, ứng dụng sẽ tạo instance của nhiều provider. Dùng `Provider.type()` để đọc metadata trước và chỉ gọi `get()` sau khi đã chọn được ứng viên.

**Provider không có metadata ưu tiên**

Quy định rõ giá trị mặc định, như priority bằng 0, hoặc từ chối provider thiếu metadata nếu chính sách yêu cầu bắt buộc. Ví dụ trên dùng 0 và tie-break bằng tên class.

**Nhầm `uses` với `requires`**

`requires` thiết lập khả năng đọc một mô-đun cụ thể. `uses` khai báo nhu cầu sử dụng một service. Consumer thường cần `requires` mô-đun API để tham chiếu interface và `uses` interface đó để khám phá implementation.

## 9. Checklist thiết kế lựa chọn provider

Trước khi đưa service vào ứng dụng, hãy kiểm tra:

1. Service interface nằm trong mô-đun API có package được export.
2. Mô-đun tiêu thụ khai báo `uses` cho service.
3. Mỗi mô-đun provider khai báo `provides ... with ...` và phụ thuộc vào mô-đun API.
4. Provider class hoặc provider method đáp ứng quy tắc của `ServiceLoader`.
5. Các provider cần dùng có mặt trong module path và được phân giải vào layer phù hợp.
6. Chính sách chọn provider có tiêu chí rõ ràng: capability, availability, priority và fallback.
7. Có tie-break ổn định khi các provider có cùng mức ưu tiên.
8. Metadata được đọc qua `Provider.type()`; chỉ khởi tạo provider cần dùng bằng `Provider.get()`.
9. Đã kiểm tra tình huống không có provider, provider lỗi khi khởi tạo và provider lỗi khi thực hiện nghiệp vụ.

`ServiceLoader` giúp mô-đun tiêu thụ không phụ thuộc trực tiếp vào các class triển khai. Khi có nhiều provider, hãy coi việc khám phá và việc lựa chọn là hai bước riêng: JPMS cùng `ServiceLoader` tìm các ứng viên, còn policy của ứng dụng quyết định ứng viên nào phù hợp với yêu cầu tại thời điểm chạy.
