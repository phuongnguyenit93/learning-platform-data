# Thay phụ thuộc vào chi tiết nội bộ bằng hợp đồng được hỗ trợ

Khi một mô-đun gọi trực tiếp class, package hoặc cấu trúc dữ liệu nội bộ của mô-đun khác, hai mô-đun bị gắn chặt với cách triển khai hiện tại. Một thay đổi tưởng như riêng tư — đổi tên class, thay ORM, chuyển package hoặc thay cách lưu dữ liệu — có thể làm mã tiêu thụ không biên dịch hoặc không chạy. Trong JPMS, ranh giới truy cập giúp ngăn kiểu phụ thuộc này; hợp đồng được hỗ trợ cung cấp điểm tích hợp ổn định để các mô-đun vẫn phối hợp với nhau.

## 1. Phân biệt hợp đồng với chi tiết triển khai

Hợp đồng được hỗ trợ là phần API mà mô-đun chủ động công khai và cam kết duy trì. Trong một mô-đun Java, hợp đồng này thường nằm trong package được khai báo bằng `exports` ở `module-info.java`. Nó có thể gồm interface, class, enum, exception và kiểu dữ liệu mà người dùng thực sự cần.

Chi tiết triển khai là phần có thể thay đổi mà không làm thay đổi cách người dùng gọi chức năng: repository cụ thể, adapter, cache, entity của ORM, client HTTP, lớp truy cập database, thuật toán nội bộ hoặc helper class. Những package như `internal`, `impl`, `persistence` thường chứa các chi tiết này và không nên export nếu chúng không phải API.

Ví dụ một ứng dụng phụ thuộc trực tiếp vào `com.example.invoice.internal.JdbcTaxRepository` sẽ phải biết implementation đang dùng JDBC. Nếu mô-đun thay JDBC bằng dịch vụ từ xa, ứng dụng có thể phải sửa theo. Ứng dụng chỉ cần biết hợp đồng `TaxPolicy` và gọi hành vi đã cam kết.

```text
Thiết kế gắn chặt:
  Application ───────> JdbcTaxRepository
                         chi tiết nội bộ

Thiết kế theo hợp đồng:
  Application ───────> TaxPolicy (API/SPI)
                           ▲
                           │ implements
                  StandardTaxPolicy
                    package internal
```

## 2. Tạo một ranh giới API nhỏ và ổn định

Đặt interface hoặc kiểu hợp đồng trong package API riêng. Chỉ export package đó. Chữ ký của hợp đồng nên mô tả nghiệp vụ mà bên gọi cần, không làm lộ cách bên cung cấp thực hiện công việc.

Một hợp đồng tốt thường có các đặc điểm:

- Tên và phương thức thể hiện hành vi nghiệp vụ, chẳng hạn `TaxPolicy`, `PaymentGateway` hoặc `DocumentStore`, thay vì tên implementation như `JdbcTaxPolicy`.
- Chỉ dùng các kiểu dữ liệu ổn định trong chữ ký. Ưu tiên kiểu Java SE hoặc DTO thuộc chính API; tránh trả về entity ORM, connection, request nội bộ hoặc class từ thư viện triển khai.
- Giữ bề mặt API nhỏ. Chỉ công khai phương thức mà consumer cần; không export package chỉ vì một class tiện cho việc triển khai.
- Xác định rõ nullability, đơn vị, quy tắc lỗi, thread-safety và ý nghĩa dữ liệu nếu các yếu tố đó ảnh hưởng tới người gọi.
- Có chính sách tương thích. Khi cần mở rộng, ưu tiên thay đổi tương thích ngược và kiểm tra consumer thực tế trước khi loại bỏ thành phần cũ.

Không phải mọi class `public` đều là hợp đồng được hỗ trợ. Với named module, consumer chỉ truy cập package được export và còn phải có quan hệ readability tới mô-đun đó. Một class public nằm trong package không export vẫn có thể là chi tiết triển khai.

## 3. Dùng SPI khi consumer cần một implementation có thể thay thế

Service Provider Interface (SPI) là một dạng hợp đồng: mô-đun API định nghĩa interface; mô-đun cung cấp dịch vụ triển khai interface; mô-đun tiêu thụ chỉ biết interface. `ServiceLoader` tìm implementation đã đăng ký mà không buộc consumer khai báo phụ thuộc trực tiếp tới module provider.

Trong JPMS, ba chỉ thị có vai trò khác nhau:

| Chỉ thị | Đặt ở đâu | Ý nghĩa |
| --- | --- | --- |
| `exports` | Module API | Công khai package chứa hợp đồng cho mô-đun đọc nó. |
| `uses` | Module tiêu thụ | Khai báo mô-đun sẽ tìm implementation của service interface. |
| `provides ... with ...` | Module cung cấp | Đăng ký class triển khai cho service interface. |

Module provider thường `requires` module API. Package chứa class implementation không cần export cho consumer. Với provider class dùng constructor, class provider phải public và có public constructor không tham số; package vẫn có thể được giữ kín. `ServiceLoader` được JPMS cho phép khởi tạo provider theo khai báo `provides`.

## 4. Ví dụ chạy được: ứng dụng chỉ phụ thuộc vào hợp đồng

Ví dụ có ba mô-đun:

- `com.example.invoice.api` định nghĩa SPI `TaxPolicy` và export package API.
- `com.example.invoice.standard` triển khai SPI trong package `internal`; module descriptor đăng ký provider nhưng không export package implementation.
- `com.example.invoice.app` chỉ requires API và khai báo `uses`. Ứng dụng tìm implementation bằng `ServiceLoader`.

Cấu trúc thư mục:

```text
src/
├── com.example.invoice.api/
│   ├── module-info.java
│   └── com/example/invoice/api/TaxPolicy.java
├── com.example.invoice.standard/
│   ├── module-info.java
│   └── com/example/invoice/standard/internal/StandardTaxPolicy.java
└── com.example.invoice.app/
    ├── module-info.java
    └── com/example/invoice/app/Main.java
```

**`src/com.example.invoice.api/module-info.java`**

```java
module com.example.invoice.api {
    exports com.example.invoice.api;
}
```

**`src/com.example.invoice.api/com/example/invoice/api/TaxPolicy.java`**

```java
package com.example.invoice.api;

import java.math.BigDecimal;

public interface TaxPolicy {
    BigDecimal taxFor(String region, BigDecimal netAmount);
}
```

Đây là hợp đồng mà consumer và provider cùng hiểu. Chữ ký không để lộ database, framework hay class nội bộ nào.

**`src/com.example.invoice.standard/module-info.java`**

```java
module com.example.invoice.standard {
    requires com.example.invoice.api;

    provides com.example.invoice.api.TaxPolicy
            with com.example.invoice.standard.internal.StandardTaxPolicy;
}
```

Provider phụ thuộc vào hợp đồng API. Descriptor đăng ký class triển khai cho service; không có dòng `exports com.example.invoice.standard.internal`.

**`src/com.example.invoice.standard/com/example/invoice/standard/internal/StandardTaxPolicy.java`**

```java
package com.example.invoice.standard.internal;

import com.example.invoice.api.TaxPolicy;
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class StandardTaxPolicy implements TaxPolicy {
    public StandardTaxPolicy() {
    }

    @Override
    public BigDecimal taxFor(String region, BigDecimal netAmount) {
        if ("VN".equals(region)) {
            return netAmount.multiply(new BigDecimal("0.10"))
                    .setScale(2, RoundingMode.HALF_UP);
        }
        return BigDecimal.ZERO.setScale(2);
    }
}
```

Tỷ lệ 10% ở đây chỉ dùng để minh họa cơ chế gọi SPI, không đại diện cho quy định thuế thực tế. Có thể thay toàn bộ class này bằng implementation khác mà không cần thay chữ ký `TaxPolicy`.

**`src/com.example.invoice.app/module-info.java`**

```java
module com.example.invoice.app {
    requires com.example.invoice.api;
    uses com.example.invoice.api.TaxPolicy;
}
```

Consumer chỉ phụ thuộc API. Không khai báo `requires com.example.invoice.standard`; quan hệ với implementation được thiết lập qua service binding.

**`src/com.example.invoice.app/com/example/invoice/app/Main.java`**

```java
package com.example.invoice.app;

import com.example.invoice.api.TaxPolicy;
import java.math.BigDecimal;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        TaxPolicy policy = ServiceLoader.load(TaxPolicy.class)
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("No TaxPolicy provider found"));

        BigDecimal tax = policy.taxFor("VN", new BigDecimal("100.00"));
        System.out.println("Tax: " + tax);
    }
}
```

Biên dịch từ thư mục chứa `src`:

```powershell
javac --release 17 --module-source-path src -d out -m com.example.invoice.api,com.example.invoice.standard,com.example.invoice.app
```

Chạy ứng dụng:

```powershell
java --module-path out -m com.example.invoice.app/com.example.invoice.app.Main
```

STDOUT:

```text
Tax: 10.00
```

Khi chạy trên module path, launcher resolve mô-đun ứng dụng và các dependency của nó; service binding có thể đưa provider phù hợp vào layer. `uses` trong consumer và `provides` trong provider cho phép `ServiceLoader` tìm implementation mà consumer không phải tham chiếu class `StandardTaxPolicy`.

## 5. Xác minh implementation package không phải API công khai

Có thể đóng gói provider thành modular JAR và đọc descriptor:

```powershell
New-Item -ItemType Directory -Force build | Out-Null
jar --create --file build/com.example.invoice.standard.jar -C out/com.example.invoice.standard .
jar --describe-module --file build/com.example.invoice.standard.jar
```

Phần liên quan của kết quả:

```text
com.example.invoice.standard
requires com.example.invoice.api
requires java.base mandated
provides com.example.invoice.api.TaxPolicy with com.example.invoice.standard.internal.StandardTaxPolicy
contains com.example.invoice.standard.internal
```

`contains` cho biết package có trong mô-đun; nó không có nghĩa package được export. Descriptor không có dòng `exports com.example.invoice.standard.internal`, nên một consumer không thể import trực tiếp class implementation qua ranh giới mô-đun.

Thử import `StandardTaxPolicy` từ một mô-đun consumer khác sẽ bị compiler từ chối vì package không được export. Consumer cần dùng `TaxPolicy` và cơ chế provider đã công bố.

## 6. Khi nào dùng dependency injection thay cho ServiceLoader?

Không phải mọi interface đều cần `ServiceLoader`. Nếu ứng dụng có một implementation cố định và composition root được phép chọn implementation, có thể truyền interface qua constructor:

```java
public final class InvoiceService {
    private final TaxPolicy taxPolicy;

    public InvoiceService(TaxPolicy taxPolicy) {
        this.taxPolicy = taxPolicy;
    }
}
```

Đây là dependency injection: `InvoiceService` chỉ biết hợp đồng `TaxPolicy`; phần khởi tạo bên ngoài cung cấp đối tượng cụ thể. Cách này phù hợp khi ứng dụng chủ động lắp ghép dependency và không cần khám phá provider tại runtime.

Dùng `ServiceLoader` khi muốn phát hiện provider theo module path, hỗ trợ plugin hoặc cho phép thêm implementation mà không sửa consumer. Dù dùng cách nào, dependency của consumer vẫn nên trỏ tới hợp đồng được hỗ trợ. Không tạo interface chỉ để bọc một class nội bộ nếu không có ranh giới thay đổi hoặc nhu cầu thay thế thực sự.

## 7. Giữ hợp đồng ổn định khi implementation thay đổi

Trước khi đổi implementation, kiểm tra xem thay đổi có làm thay đổi chữ ký hoặc ý nghĩa của hợp đồng hay không. Thay JDBC bằng HTTP, thay cache, đổi thuật toán hoặc di chuyển class trong package internal thường không cần thay consumer nếu API vẫn giữ nguyên.

Nếu cần mở rộng hợp đồng, hãy cân nhắc:

1. Thêm phương thức hoặc kiểu mới theo cách tương thích với consumer hiện tại; với interface, cân nhắc default method khi có hành vi mặc định đúng và an toàn.
2. Giữ kiểu trả về và tham số thuộc API ổn định; không đưa class implementation mới vào chữ ký public.
3. Xác định rõ cách xử lý lỗi và giá trị thiếu để consumer không phụ thuộc vào exception hoặc trạng thái nội bộ.
4. Viết contract test để kiểm tra mọi provider tuân thủ cùng quy tắc đầu vào, đầu ra và lỗi.
5. Kiểm tra cả consumer lẫn provider khi nâng phiên bản module API; kiểm tra module path thực tế trong build và runtime.

Thay đổi package internal có thể phá plugin nếu provider khác đang truy cập trái phép qua reflection hoặc `--add-exports`. Những truy cập đó không phải hợp đồng ổn định. Nếu framework cần reflection sâu, chỉ mở đúng package và đúng module đích khi có lý do rõ ràng; không mở toàn bộ module để né ranh giới thiết kế.

## 8. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `package ... is not visible` | Consumer import package không được export. | Dùng API đã export hoặc bổ sung hợp đồng có chủ đích. |
| `No provider found` hoặc không tìm thấy service | Consumer thiếu `uses`, provider thiếu `provides`, provider không được resolve hoặc không nằm trên module path. | Kiểm tra hai descriptor, module path và module layer đang dùng. |
| `NoClassDefFoundError` khi gọi service | Provider hoặc dependency của provider không có trong runtime graph. | Kiểm tra service binding và các dependency bắt buộc của provider. |
| Thay implementation làm consumer phải sửa | Consumer phụ thuộc class cụ thể hoặc kiểu nội bộ xuất hiện trong API. | Chuyển điểm phụ thuộc sang interface/DTO được hỗ trợ. |
| API thay đổi liên tục | Hợp đồng chứa quá nhiều chi tiết triển khai hoặc không có chính sách tương thích. | Thu nhỏ bề mặt public, ổn định ngữ nghĩa và thêm contract test. |

Không giải quyết vấn đề bằng cách export mọi package hoặc dùng `--add-exports` lâu dài cho ứng dụng. Các cờ đó có thể hữu ích khi chẩn đoán hoặc chuyển đổi tạm thời, nhưng chúng không thay thế một hợp đồng module được thiết kế và hỗ trợ rõ ràng.

## 9. Nguyên tắc áp dụng

- Consumer phụ thuộc vào interface hoặc API công khai mô tả hành vi cần dùng.
- Provider triển khai hợp đồng trong package nội bộ và đăng ký qua `provides` khi cần khám phá dịch vụ.
- Consumer khai báo `uses` và tìm provider bằng `ServiceLoader`; với ứng dụng lắp ghép trực tiếp, dùng constructor injection.
- Không đưa entity, repository, adapter hoặc class framework nội bộ vào chữ ký của hợp đồng.
- Chỉ export package có chủ đích; giữ implementation package không export và kiểm tra descriptor bằng `jar --describe-module`.
- Duy trì contract test và kiểm tra tương thích khi phát hành phiên bản API mới.

Thay phụ thuộc vào chi tiết nội bộ bằng hợp đồng được hỗ trợ giúp mỗi mô-đun có thể thay đổi cách triển khai trong phạm vi của mình. API hoặc SPI trở thành điểm giao tiếp có chủ đích; JPMS kiểm soát package được công khai, còn `uses`/`provides` và `ServiceLoader` cho phép tìm implementation mà không buộc consumer biết class nội bộ.