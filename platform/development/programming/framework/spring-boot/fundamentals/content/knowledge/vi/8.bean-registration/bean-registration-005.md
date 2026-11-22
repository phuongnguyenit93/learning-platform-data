# @ComponentScan với include filter, exclude filter và phạm vi quét

Trong một ứng dụng Spring Boot, có những lớp được đánh dấu `@Service`, `@Repository`, `@RestController` hoặc `@Component`, nhưng Spring chỉ tạo bean cho chúng khi **có cơ chế đăng ký bean phù hợp**. Một trong các cơ chế phổ biến là **component scanning**: Spring tìm các lớp ứng viên trong những package được chỉ định rồi đăng ký bean definition cho các lớp đáp ứng quy tắc.

Annotation `@ComponentScan` cho phép kiểm soát việc tìm kiếm đó ở ba khía cạnh liên quan chặt chẽ:

- **Phạm vi quét**: Spring đi tìm thành phần trong package nào?
- **Include filter**: ngoài các ứng viên mặc định, Spring còn nên nhận những lớp có đặc điểm gì?
- **Exclude filter**: những lớp nào cần bị loại khỏi lần quét đó?

Đây là một bài toán quan trọng khi ứng dụng lớn lên: một package chứa nhiều implementation, chỉ một vài adapter được phép chạy trong một môi trường, hoặc lớp khởi động được đặt sai package khiến bean không được phát hiện. Tuy nhiên, filter **chỉ điều khiển một hoạt động component scan**; nó không tự xóa bean được đăng ký từ những nguồn khác, cũng không thay thế Spring profile, auto-configuration hay cơ chế quản lý dependency.

## 1. Component scanning nằm ở đâu trong quá trình đăng ký bean?

Xét một ứng dụng có những thành phần sau:

~~~text
HTTP request
     |
     v
OrderController
     |
     v
OrderService
     |
     v
OrderRepository
~~~

`OrderController` và `OrderService` cần trở thành Spring bean để container có thể tạo chúng và tiêm dependency qua constructor. Một lựa chọn là tự khai báo mọi bean bằng phương thức `@Bean`, nhưng với các lớp do dự án sở hữu, Spring còn hỗ trợ component scanning.

Ví dụ:

~~~java
package com.example.store.orders;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    public String status() {
        return "READY";
    }
}
~~~

Nếu một component scan bao phủ `com.example.store.orders` và không có điều kiện loại trừ, Spring có thể nhận `OrderService` là ứng viên, đăng ký bean definition và khởi tạo nó theo vòng đời container.

Luồng được đơn giản hóa:

~~~text
Cấu hình @ComponentScan
          |
          v
Xác định các package gốc cần quét
          |
          v
Đọc metadata các class có thể tìm thấy
          |
          v
Áp dụng quy tắc ứng viên mặc định,
include filter và exclude filter
          |
          v
Đăng ký bean definitions
          |
          v
Spring container giải quyết dependency
và tạo bean theo scope, điều kiện, vòng đời
~~~

Điểm phân biệt: **quét và đăng ký bean definition** khác với **khởi tạo instance**. Spring thường đăng ký định nghĩa trước, sau đó mới tạo instance theo scope và thời điểm thích hợp. Một lớp phù hợp với filter vẫn có thể không khởi tạo được nếu thiếu dependency hoặc constructor gặp lỗi.

### Những annotation nào thường được phát hiện mặc định?

Spring component scanning mặc định nhận các lớp có `@Component` hoặc annotation dựa trên `@Component`, trong đó có các stereotype thường gặp:

| Annotation | Ý nghĩa thường dùng |
|---|---|
| `@Component` | Thành phần tổng quát do Spring quản lý |
| `@Service` | Thành phần xử lý logic ứng dụng hoặc nghiệp vụ |
| `@Repository` | Thành phần truy cập dữ liệu |
| `@Controller` | Controller của Spring MVC |
| `@RestController` | REST controller, kết hợp chức năng controller với ghi response body |
| `@Configuration` | Lớp cấu hình chứa bean definition hoặc cấu hình Spring |

Ví dụ `@RestController` là một dạng chuyên biệt của `@Controller`; `@Controller` lại là component stereotype. Do đó, controller thường được phát hiện dù lớp không viết `@Component` trực tiếp.

Cơ chế phát hiện dựa trên metadata của lớp và annotation tương ứng. Tuy nhiên, **chỉ có annotation chưa đủ**: lớp phải nằm trong vùng quét, không bị filter loại, không bị điều kiện đăng ký khác ngăn lại và có thể được container xử lý hợp lệ.

## 2. Spring Boot quét ở đâu nếu không khai báo @ComponentScan?

Một ứng dụng Spring Boot điển hình:

~~~java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
~~~

`@SpringBootApplication` là annotation tổng hợp, bao gồm cơ chế component scan theo quy ước và kích hoạt auto-configuration. Với cách đặt lớp trên, component scan mặc định bắt đầu từ package `com.example.store`, sau đó quét những package con như:

~~~text
com.example.store
├── StoreApplication.java
├── catalog/
│   ├── BookController.java
│   └── BookService.java
├── orders/
│   ├── OrderController.java
│   └── OrderService.java
└── payments/
    └── PaymentService.java
~~~

Nếu các lớp ở package con được đánh dấu stereotype thích hợp, chúng có thể được phát hiện mà không cần viết thêm `@ComponentScan`.

Nhưng xét cấu trúc khác:

~~~text
com.example.store
├── bootstrap/
│   └── StoreApplication.java
├── catalog/
│   └── BookService.java
└── orders/
    └── OrderService.java
~~~

Lúc này lớp `StoreApplication` thuộc `com.example.store.bootstrap`. Theo quy ước mặc định, scan khởi đầu từ package `bootstrap` và các package con của nó, **không tự đi lên package cha rồi quét các package anh em**. Vì vậy `BookService` và `OrderService` có thể không trở thành bean.

Có hai hướng thông thường:

1. Đặt lớp `StoreApplication` trong package gốc `com.example.store`.
2. Chỉ định rõ phạm vi component scan bằng cấu hình.

Nếu không có lý do kiến trúc đặc biệt, đặt lớp khởi động ở package gốc chung thường đơn giản hơn.

**Tránh đặt lớp khởi động ở default package** (không có dòng `package`). Điều này có thể khiến phạm vi quét quá rộng và tạo ra hành vi khó kiểm soát.

## 3. Chỉ định phạm vi quét bằng @ComponentScan

Annotation `@ComponentScan` có nhiều thuộc tính. Hai nhóm quan trọng nhất khi thiết kế phạm vi là:

- `basePackages` hoặc `value`: tên package dưới dạng chuỗi.
- `basePackageClasses`: các lớp hoặc interface dùng để xác định package gốc theo kiểu an toàn hơn khi refactor.

### 3.1. Quét bằng tên package

Ví dụ, cần quét các thành phần trong hai nhánh:

~~~java
package com.example.store;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;

@SpringBootApplication
@ComponentScan(basePackages = {
        "com.example.store.catalog",
        "com.example.store.orders"
})
public class StoreApplication {
    // Phương thức main như ví dụ phía trên
}
~~~

Lần component scan này bắt đầu từ hai package được khai báo và đi xuống các package con của chúng.

Nếu có `com.example.store.payments.PaymentService` nhưng không nằm dưới các gốc trên, lớp đó sẽ không được lần scan này phát hiện. Tuy nhiên, một bean cùng loại **vẫn có thể đến từ nơi khác**, chẳng hạn `@Bean`, `@Import` hoặc một cấu hình scan khác.

Cách dùng tên package dưới dạng chuỗi dễ đọc, nhưng khi đổi tên hoặc di chuyển package, IDE có thể không tự cập nhật mọi chuỗi literal. Vì vậy, cần chú ý khi refactor.

### 3.2. Quét bằng marker class hoặc marker interface

Có thể đặt một interface trống trong package cần quét:

~~~java
// com/example/store/catalog/CatalogPackage.java
package com.example.store.catalog;

public interface CatalogPackage {}
~~~

Sau đó tham chiếu bằng class literal:

~~~java
package com.example.store;

import com.example.store.catalog.CatalogPackage;
import com.example.store.orders.OrdersPackage;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;

@SpringBootApplication
@ComponentScan(basePackageClasses = {
        CatalogPackage.class,
        OrdersPackage.class
})
public class StoreApplication {
    // Phương thức main
}
~~~

`OrdersPackage` cũng là marker được định nghĩa trong package `com.example.store.orders`. Interface marker không cần trở thành bean; nó chỉ đại diện cho **vị trí package** để Spring xác định nơi cần quét.

Phương pháp này có hai lợi ích: compiler kiểm tra được kiểu tham chiếu, và công cụ refactor Java thường cập nhật import/class reference tốt hơn các chuỗi package. Vì vậy, `basePackageClasses` là lựa chọn đáng cân nhắc khi dự án có nhiều package nghiệp vụ hoặc nhiều module.

### 3.3. Thuộc tính của @SpringBootApplication

Để chỉ đổi phạm vi quét trong ứng dụng Spring Boot, có thể dùng các thuộc tính tiện lợi:

~~~java
package com.example.store.bootstrap;

import com.example.store.catalog.CatalogPackage;
import com.example.store.orders.OrdersPackage;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
        scanBasePackageClasses = {
                CatalogPackage.class,
                OrdersPackage.class
        }
)
public class StoreApplication {
    // ...
}
~~~

Hoặc:

~~~java
@SpringBootApplication(
        scanBasePackages = {
                "com.example.store.catalog",
                "com.example.store.orders"
        }
)
public class StoreApplication {
    // ...
}
~~~

`scanBasePackages` và `scanBasePackageClasses` là các thuộc tính tiện lợi cho **component scan**. Chúng không tự thay đổi mọi loại scanning khác trong Spring Boot.

Đặc biệt với JPA và Spring Data, **entity scanning** và **repository scanning** có cơ chế xác định package riêng. Nếu ứng dụng chuyển các entity hoặc repository ra ngoài package gốc mà auto-configuration thường sử dụng, có thể cần `@EntityScan` hoặc `@EnableJpaRepositories` phù hợp. Không nên giả định rằng chỉ khai báo `scanBasePackages` đã bao phủ toàn bộ cơ chế quét của JPA.

### 3.4. Bản chất phạm vi quét

| Lựa chọn | Ý nghĩa | Khi nào hữu ích? |
|---|---|---|
| Không khai báo, dùng mặc định của `@SpringBootApplication` | Quét package chứa ứng dụng và package con | Dự án có package root hợp lý |
| `@ComponentScan("...")` hoặc `basePackages` | Quét package theo tên | Định nghĩa rõ nhiều vùng cần quét |
| `basePackageClasses` | Quét package chứa những kiểu được chỉ định | Muốn tránh chuỗi hardcode |
| `scanBasePackages` trong `@SpringBootApplication` | Cấu hình component scan từ annotation khởi động | Chỉ cần thay đổi phạm vi quét của Boot |
| `@Import` hoặc `@Bean` | Đăng ký cấu hình/bean cụ thể | Muốn đăng ký tường minh thay vì quét cả package |

Khi không có `basePackages` hoặc `basePackageClasses`, Spring thường lấy package của lớp khai báo `@ComponentScan` làm cơ sở.

**Chú ý:** `@ComponentScan` đặt trực tiếp trên lớp cũng mang `@SpringBootApplication` có thể được ưu tiên hơn cấu hình component scan đến từ meta-annotation. Vì vậy, khi thêm `@ComponentScan` trực tiếp, hãy mô tả đầy đủ phạm vi và filter mong muốn. Ngoài ra, một cấu hình khác có thể tiến hành **lần scan riêng**; điều này có nghĩa cấu hình lọc ở một lần scan không nhất thiết loại được bean do lần scan kia đăng ký.

## 4. Include filter và exclude filter là gì?

Một component scan phải quyết định lớp nào là **ứng viên**. Mặc định, nó đã có những filter nhận diện stereotype như `@Component` và các annotation dựa trên `@Component`.

Hai thuộc tính cho phép tùy chỉnh:

- `includeFilters`: thêm hoặc xác định những loại lớp được coi là ứng viên.
- `excludeFilters`: loại những lớp phù hợp khỏi kết quả lần scan tương ứng.

Cùng với hai thuộc tính này, cần đặc biệt hiểu `useDefaultFilters`:

~~~java
@ComponentScan(
        basePackages = "com.example.store",
        useDefaultFilters = true
)
~~~

Giá trị `true` là mặc định. Khi đó, những component stereotype thông thường vẫn được nhận diện. Nếu thêm include filter mà giữ `useDefaultFilters = true`, kết quả có thể rộng hơn dự kiến: **các lớp `@Component`, `@Service`, `@Repository` và `@Controller` vẫn được quét** dù không khớp include filter bổ sung.

Ngược lại:

~~~java
@ComponentScan(
        basePackages = "com.example.store.extensions",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = Extension.class
        )
)
~~~

Lần scan này không sử dụng bộ lọc nhận diện component mặc định; nó chỉ nhận lớp phù hợp với include filter được chỉ định (và không bị exclude filter loại). `Extension` trong ví dụ là một annotation do dự án định nghĩa.

Cần import `org.springframework.context.annotation.FilterType` khi sử dụng các giá trị `FilterType.ANNOTATION`, `FilterType.ASSIGNABLE_TYPE`, v.v.

### Quy tắc đọc một lần component scan

Có thể hình dung cách xét ứng viên:

~~~text
Tập các class trong package được quét
                  |
                  v
  Ứng viên theo filter mặc định?
        hoặc theo include filter?
                  |
             Có   |   Không
                  |      └── Bỏ qua
                  v
       Khớp exclude filter?
             |        |
            Có       Không
             |        |
           Bỏ qua     v
                Có thể đăng ký bean definition
                (còn xét điều kiện và các bước khác)
~~~

Đây là mô hình tư duy giúp đọc cấu hình, không phải mã giả chính xác của mọi bước nội bộ scanner. Nhưng hai ý thực hành rất quan trọng:

1. **Include filter không nhất thiết là danh sách được phép duy nhất**, trừ khi bạn điều chỉnh `useDefaultFilters` thích hợp.
2. **Exclude filter có thể loại một lớp khỏi scan dù lớp đó phù hợp include filter**.

## 5. Các loại FilterType thường dùng

`@ComponentScan.Filter` có thuộc tính `type` để chỉ định cách kiểm tra ứng viên.

| `FilterType` | Cách so khớp | Trường hợp sử dụng |
|---|---|---|
| `ANNOTATION` | Lớp có annotation được chỉ định theo cơ chế so khớp annotation của Spring | Chỉ tìm lớp mang annotation tùy chỉnh hoặc loại lớp theo annotation |
| `ASSIGNABLE_TYPE` | Lớp thuộc kiểu được chỉ định hoặc có quan hệ kế thừa/triển khai phù hợp | Tìm các implementation của một interface |
| `REGEX` | Tên lớp đầy đủ khớp biểu thức chính quy | Loại một họ tên lớp hoặc nhóm class có quy ước đặt tên |
| `ASPECTJ` | Tên/kiểu khớp pattern theo cú pháp AspectJ | Quy tắc lựa chọn phức tạp, cần thư viện hỗ trợ phù hợp |
| `CUSTOM` | Gọi `TypeFilter` do ứng dụng cung cấp | Cần đọc metadata và áp dụng logic tùy chỉnh |

Trong annotation:

- Với `ANNOTATION` và `ASSIGNABLE_TYPE`, thường dùng thuộc tính `classes`.
- Với `REGEX` hoặc `ASPECTJ`, dùng thuộc tính `pattern`.
- Với `CUSTOM`, `classes` trỏ tới implementation của `TypeFilter`.

Có thể cung cấp nhiều filter trong `includeFilters` hoặc `excludeFilters`. Chúng giúp diễn đạt nhiều đường nhận diện khác nhau, nhưng **mỗi filter không tạo ranh giới package riêng**: scanner vẫn chỉ khảo sát các package gốc đã chỉ định.

## 6. Ví dụ include filter: chỉ lấy thành phần có annotation riêng

Giả sử ứng dụng hỗ trợ các extension để xuất báo cáo. Không muốn đưa tất cả lớp trong package `extensions` thành bean; chỉ những lớp đánh dấu `@ReportExtension` mới được nhận.

Cấu trúc ví dụ:

~~~text
com.example.report
├── ReportApplication.java
└── extensions
    ├── ReportExtension.java
    ├── CsvExporter.java
    ├── PdfExporter.java
    └── ExperimentHelper.java
~~~

### 6.1. Định nghĩa annotation đánh dấu

File `ReportExtension.java`:

~~~java
package com.example.report.extensions;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface ReportExtension {}
~~~

Annotation `@ReportExtension` **không cần gắn `@Component`** ở ví dụ này. Nó là marker để include filter nhận diện. Chỉ khi có cấu hình scan với filter tương ứng, các lớp mang annotation mới được chọn theo ví dụ.

### 6.2. Viết các lớp extension

~~~java
package com.example.report.extensions;

@ReportExtension
public class CsvExporter {
    public String format() {
        return "csv";
    }
}
~~~

~~~java
package com.example.report.extensions;

@ReportExtension
public class PdfExporter {
    public String format() {
        return "pdf";
    }
}
~~~

~~~java
package com.example.report.extensions;

public class ExperimentHelper {
    // Chưa được đánh dấu là extension.
}
~~~

### 6.3. Cấu hình scan chỉ nhận @ReportExtension

Ví dụ đặt `@ComponentScan` trực tiếp trên lớp khởi động để thể hiện rõ lựa chọn scanning của ứng dụng:

~~~java
package com.example.report;

import com.example.report.extensions.ReportExtension;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootApplication
@ComponentScan(
        basePackages = "com.example.report.extensions",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = ReportExtension.class
        )
)
public class ReportApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportApplication.class, args);
    }
}
~~~

Trong vùng được quét theo cấu hình này, `CsvExporter` và `PdfExporter` phù hợp marker nên là ứng viên bean; `ExperimentHelper` không phù hợp nên không được đăng ký từ lần scan này.

Quan trọng: cấu hình này đã cố ý **tắt filter mặc định**. Nếu thêm một `@RestController` thông thường trong package `extensions` mà không đánh dấu `@ReportExtension`, controller đó cũng sẽ không được nhận bởi lần scan này. Nếu các controller và service chính nằm ngoài `extensions`, ứng dụng phải có cách đăng ký khác cho chúng. Ví dụ này nhằm minh họa một **vùng quét được chọn lọc**, không phải cấu hình chung nên áp dụng cho mọi dự án.

Để mở rộng một ứng dụng đã có scan mặc định mà chỉ muốn scan chọn lọc một package plugin riêng, có thể đặt package plugin **ngoài vùng scan mặc định**, rồi import một lớp `@Configuration` chứa `@ComponentScan` riêng. Nếu plugin nằm dưới vùng mặc định của một scan khác, lần quét đó có thể đã đăng ký những bean mà bạn không định chọn. Cần thiết kế vị trí package và các lần scan phối hợp rõ ràng.

### Điều gì xảy ra nếu quên useDefaultFilters = false?

Giả sử `ExperimentHelper` được đánh dấu `@Component`, và cấu hình vẫn đặt:

~~~java
@ComponentScan(
        basePackages = "com.example.report.extensions",
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = ReportExtension.class
        )
)
~~~

Vì `useDefaultFilters` mặc định là `true`, lớp `ExperimentHelper` mang `@Component` vẫn là ứng viên, mặc dù nó không có `@ReportExtension`.

Do đó, **include filter thêm ứng viên** trong cấu hình mặc định; nếu yêu cầu là “chỉ đăng ký những lớp có marker”, phải thiết kế tương ứng với `useDefaultFilters = false`.

## 7. Include filter theo interface với ASSIGNABLE_TYPE

Trong một hệ thống có nhiều plugin cùng một hợp đồng, có thể tìm các implementation của interface.

~~~java
package com.example.report.spi;

public interface ReportExporter {
    String format();
}
~~~

Các lớp triển khai:

~~~java
package com.example.report.plugins;

import com.example.report.spi.ReportExporter;

public class CsvReportExporter implements ReportExporter {
    @Override
    public String format() {
        return "csv";
    }
}
~~~

~~~java
package com.example.report.plugins;

import com.example.report.spi.ReportExporter;

public class PdfReportExporter implements ReportExporter {
    @Override
    public String format() {
        return "pdf";
    }
}
~~~

Cấu hình:

~~~java
package com.example.report;

import com.example.report.spi.ReportExporter;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.FilterType;

@Configuration
@ComponentScan(
        basePackages = "com.example.report.plugins",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = ReportExporter.class
        )
)
public class ExporterScanConfiguration {}
~~~

Nếu `ExporterScanConfiguration` được ứng dụng import hoặc đăng ký qua một cách phù hợp, lần scan này có thể nhận các lớp triển khai `ReportExporter` trong package `plugins`. `@Component` trên mỗi exporter không còn là điều kiện bắt buộc của filter ví dụ này.

Cần hiểu một giới hạn: filter theo kiểu có thể thu thập **nhiều implementation**. Nếu một service inject một `ReportExporter` duy nhất và có hai bean, Spring có thể báo không biết chọn bean nào. Khi thiết kế nhiều plugin, nên dùng `List<ReportExporter>`, `Map<String, ReportExporter>`, `@Qualifier` hoặc một cơ chế lựa chọn thích hợp.

Ngoài ra, interface hoặc abstract class có thể khớp quan hệ kiểu nhưng không nhất thiết là bean có thể khởi tạo. Scanner còn áp dụng quy tắc ứng viên hợp lệ; filter không biến một interface thành instance tự chạy.

## 8. Ví dụ exclude filter: loại một lớp theo annotation

Một tình huống khác: muốn quét gần như toàn bộ module nhưng không đăng ký các thành phần mang marker `@LegacyComponent`.

Định nghĩa marker:

~~~java
package com.example.store.shared;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface LegacyComponent {}
~~~

Sử dụng:

~~~java
package com.example.store.pricing;

import com.example.store.shared.LegacyComponent;
import org.springframework.stereotype.Service;

@LegacyComponent
@Service
public class OldDiscountCalculator {
    // Thuật toán cũ không muốn kích hoạt qua component scan.
}
~~~

Cấu hình scan:

~~~java
package com.example.store;

import com.example.store.shared.LegacyComponent;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootApplication
@ComponentScan(
        basePackages = "com.example.store",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = LegacyComponent.class
        )
)
public class StoreApplication {
    // ...
}
~~~

Trong lần scan này, `OldDiscountCalculator` nằm trong vùng quét và có stereotype `@Service`, nhưng nó khớp exclude filter nên không được đăng ký bằng component scanning đó.

Điều này có thể hữu ích khi chuyển đổi implementation cũ sang mới. Tuy nhiên, nếu service khác vẫn inject trực tiếp `OldDiscountCalculator` hoặc interface mà chỉ lớp này triển khai, việc loại nó có thể khiến ứng dụng không khởi động do thiếu bean. Filter thay đổi **đồ thị bean**, nên phải cân nhắc những dependency đang sử dụng.

### Exclude filter theo kiểu cụ thể

Nếu chỉ muốn loại một lớp:

~~~java
@ComponentScan(
        basePackages = "com.example.store",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = OldDiscountCalculator.class
        )
)
~~~

Kiểu `ASSIGNABLE_TYPE` cũng có thể phù hợp với các kiểu con/implementation có quan hệ assignable, nên không nhất thiết chỉ là so khớp tên đúng một class theo nghĩa hẹp. Nếu chỉ cần điều kiện rất cụ thể, nên đánh giá loại filter thích hợp và đường kế thừa thực tế.

### Exclude theo package bằng REGEX

Vì `@ComponentScan` không có một thuộc tính mang nghĩa “loại toàn bộ package con này” bằng tên package độc lập, có thể dùng regex trên **tên lớp đầy đủ**:

~~~java
@ComponentScan(
        basePackages = "com.example.store",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.REGEX,
                pattern = "com[.]example[.]store[.]legacy[.].*"
        )
)
~~~

Pattern trên nhắm tới class có tên đầy đủ bắt đầu bằng `com.example.store.legacy.`, ví dụ `com.example.store.legacy.LegacyPricingService`.

Sử dụng `[.]` thay cho dấu chấm không escape giúp thể hiện rõ ký tự dấu chấm trong regex. Nếu dùng `\\.` bên trong Java string, cần phân biệt quy tắc escape của regex và quy tắc escape của chuỗi Java.

Lưu ý ba điểm:

- Regex áp dụng cho **tên kiểu Java** mà scanner kiểm tra, không phải URL, đường dẫn file hoặc chuỗi package tuỳ ý.
- Tên package con như `legacy.extra` cũng có thể khớp pattern.
- Nếu có một `@Configuration` được import trực tiếp từ package bị exclude hoặc bean tạo bởi `@Bean` trong cấu hình đã được đăng ký, filter trên component scan không bảo đảm chúng sẽ biến mất khỏi context.

### Khi nào nên dùng @Profile thay vì exclude filter?

Nếu mục tiêu là “chỉ kích hoạt bean này khi chạy môi trường dev”, Spring profile thường diễn đạt ý định rõ hơn:

~~~java
@Service
@Profile("dev")
public class DebugOnlyService {
    // ...
}
~~~

Còn exclude filter thích hợp hơn khi muốn **quy tắc quét** loại một nhóm class theo type, annotation hoặc quy ước gói. Cả hai cơ chế có thể cùng xuất hiện, nhưng chúng giải quyết hai vấn đề khác nhau:

- `@Profile`: điều kiện đăng ký theo môi trường.
- `@ComponentScan.excludeFilters`: loại ứng viên khỏi một lần quét.

## 9. Custom TypeFilter khi quy tắc vượt quá annotation hoặc regex

Spring cho phép tự định nghĩa filter bằng cách triển khai `org.springframework.core.type.filter.TypeFilter`. Cách này hữu ích khi quyết định dựa trên metadata class mà các filter có sẵn khó diễn đạt.

Ví dụ minh họa: loại mọi lớp có tên kết thúc bằng `InternalAdapter` trong một package đang quét.

~~~java
package com.example.store.scanning;

import java.io.IOException;
import org.springframework.core.type.classreading.MetadataReader;
import org.springframework.core.type.classreading.MetadataReaderFactory;
import org.springframework.core.type.filter.TypeFilter;

public class InternalAdapterFilter implements TypeFilter {

    @Override
    public boolean match(
            MetadataReader metadataReader,
            MetadataReaderFactory metadataReaderFactory
    ) throws IOException {
        String className =
                metadataReader.getClassMetadata().getClassName();
        return className.endsWith("InternalAdapter");
    }
}
~~~

Dùng filter:

~~~java
package com.example.store;

import com.example.store.scanning.InternalAdapterFilter;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootApplication
@ComponentScan(
        basePackages = "com.example.store",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.CUSTOM,
                classes = InternalAdapterFilter.class
        )
)
public class StoreApplication {
    // ...
}
~~~

`TypeFilter` nhận metadata từ `MetadataReader`, nên có thể ra quyết định mà không nhất thiết phải tạo instance của class ứng viên. Điều này quan trọng vì component scanning là quá trình phân tích và đăng ký, chưa phải thời điểm mọi bean đều đã được khởi tạo.

Custom filter có sức mạnh lớn nhưng cũng dễ khó đọc, khó bảo trì và tạo chi phí quét. Nếu một marker annotation hoặc một ranh giới package rõ ràng đã giải quyết được yêu cầu thì nên ưu tiên cơ chế đơn giản hơn.

## 10. Kết hợp include, exclude và phạm vi quét

Giả sử dự án có module export tài liệu:

~~~text
com.example.docs
├── DocsApplication.java
├── exports
│   ├── CsvExporter.java       @ExportPlugin
│   ├── PdfExporter.java       @ExportPlugin
│   ├── OldXmlExporter.java    @ExportPlugin @Deprecated
│   └── ExportMetrics.java     @Component
└── orders
    └── OrderService.java      @Service
~~~

Bạn chỉ muốn một lần scan tìm exporter mang `@ExportPlugin` trong `exports`, không tìm component khác, và loại exporter cũ có `@Deprecated`.

Có thể cấu hình theo ý tưởng:

~~~java
@ComponentScan(
        basePackages = "com.example.docs.exports",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = ExportPlugin.class
        ),
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = Deprecated.class
        )
)
~~~

Giả sử `@ExportPlugin` là marker annotation hợp lệ và các class là ứng viên có thể tạo bean, kết quả kỳ vọng của **lần scan này**:

| Class | Trong package quét? | Khớp include? | Khớp exclude? | Kết quả |
|---|---|---|---|---|
| `CsvExporter` | Có | Có | Không | Được chọn |
| `PdfExporter` | Có | Có | Không | Được chọn |
| `OldXmlExporter` | Có | Có | Có | Bị loại |
| `ExportMetrics` | Có | Không | Không | Bị loại vì tắt filter mặc định |
| `OrderService` | Không | Không xét | Không xét | Nằm ngoài vùng quét |

Bảng này chỉ diễn tả **một lần component scan**. Nếu `DocsApplication` đồng thời dùng một scan mặc định phủ toàn `com.example.docs` từ một cấu hình khác, những lớp bị loại khỏi lần scan chọn lọc có thể vẫn được đăng ký bởi scan khác. Vì vậy, điều quan trọng là kiểm soát cả **ranh giới package** và **tất cả nguồn đăng ký bean** khi thiết kế một chính sách quét nghiêm ngặt.

### Tại sao việc phối hợp nhiều lần quét có thể gây bất ngờ?

Hãy phân biệt:

~~~text
Scan A: com.example.docs (default filters)
Scan B: com.example.docs.exports
        (include @ExportPlugin, exclude @Deprecated)
~~~

`OldXmlExporter` có thể bị loại bởi Scan B nhưng vẫn được tìm thấy bởi Scan A nếu nó mang `@Component` hoặc một stereotype phù hợp. Không nên suy luận rằng exclude filter của Scan B là “lệnh cấm” toàn ApplicationContext.

Ngược lại, nếu không có scan nào khác và Scan B là nguồn đăng ký duy nhất cho `exports`, filter có thể quyết định rõ bộ ứng viên trong vùng đó.

Với `@ComponentScan` khai báo trực tiếp trên lớp mang `@SpringBootApplication`, cấu hình local thường có ưu tiên so với component scan do meta-annotation của `@SpringBootApplication` cung cấp. Tuy nhiên, `@Import` hoặc các lớp `@Configuration` khác vẫn có thể tham gia đăng ký bean. Vì thế cần hiểu **toàn bộ cấu hình context** thay vì xem riêng một annotation.

## 11. Phân biệt excludeFilters của @ComponentScan với exclude của Spring Boot

Hai cú pháp có vẻ giống nhau nhưng phục vụ hai việc khác nhau.

**Loại một component khỏi lần quét:**

~~~java
@SpringBootApplication
@ComponentScan(
        basePackages = "com.example.store",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.ASSIGNABLE_TYPE,
                classes = OldOrderService.class
        )
)
public class StoreApplication {}
~~~

**Loại một auto-configuration class khỏi Spring Boot auto-configuration:**

~~~java
@SpringBootApplication(
        exclude = {
                SomeAutoConfiguration.class
        }
)
public class StoreApplication {}
~~~

`SomeAutoConfiguration` ở ví dụ thứ hai chỉ là tên minh họa cho một auto-configuration class thực tế có thể bị loại theo cơ chế Spring Boot, không phải lớp ứng dụng bất kỳ.

| Cơ chế | Tác động chính |
|---|---|
| `@ComponentScan.excludeFilters` | Loại ứng viên từ những package đang component scan |
| `@SpringBootApplication(exclude = ...)` | Loại một auto-configuration thuộc cơ chế Boot |
| `@Profile`, `@Conditional...` | Điều kiện để một bean/configuration được áp dụng |
| `@Import` | Đăng ký cấu hình hoặc thành phần theo cách tường minh |
| `@Bean` | Đăng ký bean qua factory method |

Ví dụ, nếu một `DataSource` được Boot đăng ký qua auto-configuration, exclude filter nhắm vào tên package của một repository không có nghĩa DataSource sẽ bị loại. Và nếu một class không có `@Component` nhưng được đăng ký qua `@Bean`, exclude filter cũng không đơn giản “xóa” bean đó.

## 12. Component scan và phạm vi bean là hai nghĩa khác nhau của “scope”

Trong bài này, **phạm vi quét** là package tree mà scanner tìm lớp. Nhưng Spring còn có **bean scope**, ví dụ `singleton`, `prototype` và `request`.

Hai thứ không đồng nghĩa:

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Phạm vi component scan | Những package nào được xem xét để đăng ký bean? | `com.example.store.orders` |
| Bean scope | Bean instance được tạo và tái sử dụng theo phạm vi vòng đời nào? | `singleton` hoặc `prototype` |

Ví dụ:

~~~java
package com.example.store.orders;

import org.springframework.context.annotation.Scope;
import org.springframework.stereotype.Component;

@Component
@Scope("prototype")
public class OrderDraftBuilder {
    // ...
}
~~~

Nếu `OrderDraftBuilder` nằm ngoài vùng component scan hoặc bị exclude filter loại, `@Scope("prototype")` **không khiến nó tự xuất hiện**. Ngược lại, nếu bean được đăng ký, scope sẽ ảnh hưởng đến cách container tạo và cung cấp instance, chứ không thay đổi vùng package mà Spring đi quét.

Trong một số tình huống đặc biệt, `@ComponentScan` còn có `scopeResolver` và `scopedProxy` liên quan đến cách xác định scope/proxy cho bean quét được. Đó là nhóm cấu hình khác với `basePackages`, `includeFilters` và `excludeFilters` đang được học.

## 13. Component scan khi tổ chức dự án thành nhiều module

Với Spring Boot application dạng nhiều module Maven/Gradle, component scan chỉ nhìn thấy các class **có mặt trên classpath**. Vì vậy, khai báo một package để quét chưa đủ nếu module chứa package đó không được thêm vào runtime dependencies của ứng dụng.

Giả sử:

~~~text
store-parent/
├── store-app/
│   └── src/main/java/com/example/store/StoreApplication.java
├── store-catalog/
│   └── src/main/java/com/example/catalog/CatalogService.java
└── store-orders/
    └── src/main/java/com/example/orders/OrderService.java
~~~

Nếu `store-app` phụ thuộc vào `store-catalog` và `store-orders` ở runtime, có thể chỉ định:

~~~java
@SpringBootApplication(
        scanBasePackages = {
                "com.example.store",
                "com.example.catalog",
                "com.example.orders"
        }
)
public class StoreApplication {
    // ...
}
~~~

Hoặc tham chiếu marker class trong từng module:

~~~java
@SpringBootApplication(
        scanBasePackageClasses = {
                StoreApplication.class,
                CatalogPackage.class,
                OrdersPackage.class
        }
)
public class StoreApplication {
    // ...
}
~~~

Lựa chọn dùng marker class giảm sự phụ thuộc vào chuỗi tên package và làm rõ module nào được kết nối ở composition root.

Cần lưu ý:

- Component scan không tự tải một module chưa có trên runtime classpath.
- Spring Data repository và JPA entity có thể cần vùng quét riêng, tùy vị trí package và cấu hình.
- Nếu module chỉ muốn công bố một số bean, có thể cân nhắc `@Configuration` + `@Import`, cấu hình có điều kiện, hoặc một mô hình đăng ký rõ ràng thay vì quét toàn bộ.
- Quét nhiều package chung một lần có thể tạo ra hai implementation cùng kiểu hoặc những bean không dự kiến, dẫn tới lỗi injection hay cấu hình.

Khi mở rộng thành hệ thống plugin, quét classpath đơn giản chưa chắc đủ. Plugin có thể được nạp động bằng classloader riêng hoặc có lifecycle phức tạp; các cơ chế đó cần thiết kế riêng ngoài phạm vi `@ComponentScan` cơ bản.

## 14. Vấn đề phổ biến: bean không được phát hiện

Ví dụ:

~~~text
com.acme.app
├── boot
│   └── Application.java
└── payment
    └── PaymentService.java  @Service
~~~

Nếu `Application` đặt ở `com.acme.app.boot` mà không khai báo thêm vùng quét, `PaymentService` có thể không được đăng ký. Lỗi khi inject thường có dạng:

~~~text
No qualifying bean of type 'com.acme.app.payment.PaymentService'
available
~~~

Đây là lỗi **không có bean phù hợp**, nhưng nó có nhiều nguyên nhân tiềm năng:

1. Lớp chưa được đánh dấu stereotype hoặc chưa đăng ký bằng `@Bean`.
2. Lớp nằm ngoài vùng component scan thực tế.
3. `useDefaultFilters = false` làm annotation thông thường không còn được chọn.
4. Một include/exclude filter khiến lớp không là ứng viên.
5. `@Profile`, `@Conditional` hoặc cấu hình khác ngăn đăng ký.
6. Lớp hoặc module không có mặt trên runtime classpath.
7. Bean có thể đã được tạo nhưng loại được yêu cầu khi inject không tương thích; hoặc context đang dùng trong test khác với context ứng dụng đầy đủ.

Đừng sửa bằng cách mở rộng scan thành package quá rộng ngay lập tức. Hãy xác định class cần được đăng ký, nguồn đăng ký dự kiến và phạm vi thật sự đang được dùng.

### Một ví dụ khác: Bean bị đăng ký nhiều lần

Giả sử:

~~~java
@Service
public class RemoteCustomerService implements CustomerService {
    // ...
}
~~~

Đồng thời có một cấu hình:

~~~java
@Configuration
public class CustomerConfiguration {

    @Bean
    public CustomerService customerService() {
        return new RemoteCustomerService();
    }
}
~~~

Component scan có thể tìm `RemoteCustomerService`; phương thức `@Bean` cũng đăng ký một bean `CustomerService` riêng. Khi inject interface `CustomerService` mà không có quy tắc chọn rõ ràng, container có thể gặp nhiều ứng viên.

Đây không phải chỉ là lỗi do include filter: nó là hậu quả của **nhiều nguồn đăng ký bean**. Cần chọn một cơ chế đăng ký phù hợp, hoặc dùng `@Qualifier`/`@Primary` khi thật sự muốn có nhiều implementation.

## 15. Gỡ lỗi phạm vi quét và filter

Khi thấy `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException` hoặc một bean “không mong muốn” xuất hiện, có thể chẩn đoán theo trình tự sau.

### Bước 1: xác định lớp khởi động và package gốc

Tìm `@SpringBootApplication`, vị trí package và các thuộc tính `scanBasePackages`/`scanBasePackageClasses`. Xem dự án có khai báo `@ComponentScan` trực tiếp hay thông qua cấu hình được import không.

Câu hỏi đầu tiên: **Spring có được yêu cầu tìm trong package chứa bean đang cần không?**

### Bước 2: xác định tất cả các lần quét có thể liên quan

Tìm `@ComponentScan` trong những lớp `@Configuration` được đăng ký và chú ý đến cấu hình do thư viện cung cấp. Một bean có thể xuất hiện nhờ scan khác, nên filter của một lần scan không đủ để khẳng định bean sẽ vắng mặt.

### Bước 3: đọc useDefaultFilters

Đây là nguồn gây nhầm lẫn thường gặp:

~~~java
@ComponentScan(
        basePackages = "com.example.extensions",
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = Extension.class
        )
)
~~~

Với `useDefaultFilters` mặc định là `true`, lớp mang `@Service` trong package này vẫn có thể được quét dù không có `@Extension`.

Nếu ý định là chỉ chọn extension, xem xét:

~~~java
@ComponentScan(
        basePackages = "com.example.extensions",
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
                type = FilterType.ANNOTATION,
                classes = Extension.class
        )
)
~~~

Việc tắt filter mặc định sẽ thay đổi toàn bộ tập ứng viên và có thể khiến một số cấu hình thường được quét biến mất; vì thế cần thiết kế rõ vùng quét và các bean phụ thuộc.

### Bước 4: xác minh exclude filter và các điều kiện

Kiểm tra filter theo annotation, assignable type, regex và custom type filter. Sau đó xem profile và điều kiện tạo bean. Trong Spring Boot, báo cáo điều kiện auto-configuration có thể giúp giải thích vì sao một số cấu hình được áp dụng hoặc bị bỏ qua, nhưng báo cáo này **không thay thế việc xác định component scan** cho mọi lớp ứng dụng.

### Bước 5: xác định bean thực tế trong ApplicationContext

Có thể xem bean theo kiểu hoặc theo tên, ví dụ trong một đoạn mã chẩn đoán:

~~~java
String[] names =
        applicationContext.getBeanNamesForType(PaymentService.class);

for (String name : names) {
    System.out.println(name);
}
~~~

`applicationContext` là biến tham chiếu đến Spring `ApplicationContext` mà mã chẩn đoán có thể nhận qua constructor injection hoặc một nguồn phù hợp. Đây là đoạn minh họa để hiểu cách truy vấn bean; trong ứng dụng thật, nên chọn cách log/quan sát thích hợp.

Nếu đã tích hợp Actuator và mở các endpoint quản trị theo chính sách an toàn của hệ thống, thông tin về bean có thể hỗ trợ chẩn đoán. Không nên bật công khai thông tin cấu hình hoặc bean nội bộ chỉ để gỡ lỗi trên môi trường production.

### Bước 6: kiểm tra dependency và tính hợp lệ của bean

Một lớp được scanner phát hiện vẫn có thể lỗi khi container cố tạo instance. Khi đó thông báo có thể chuyển từ “không tìm thấy bean” sang lỗi constructor, missing dependency, classpath, factory method hoặc database.

Cần phân biệt:

- **Không có bean definition**: lớp không được đăng ký (hoặc điều kiện không áp dụng).
- **Có bean definition nhưng khởi tạo thất bại**: container biết bean, nhưng không thể dựng object graph.
- **Có nhiều bean ứng viên**: injection point mơ hồ và cần quy tắc chọn.
- **Có bean, nhưng hành vi sai**: lỗi có thể nằm ở business logic hoặc lựa chọn implementation, không chỉ ở scan.

## 16. Dùng filter có hợp lý không?

Không phải mọi yêu cầu chỉ dùng một phần mã nguồn đều cần include/exclude filter. Lựa chọn nên phản ánh đúng nguyên nhân.

| Mục tiêu | Công cụ thường phù hợp |
|---|---|
| Mọi component trong package nghiệp vụ đều được quét | Mặc định của `@SpringBootApplication` hoặc `scanBasePackageClasses` |
| Chỉ nhận class có marker trong package extension | `includeFilters` với `useDefaultFilters = false` |
| Bỏ qua một nhóm component trong cùng lần quét | `excludeFilters` |
| Chọn implementation dev/prod | `@Profile` hoặc điều kiện tạo bean phù hợp |
| Chỉ tạo bean khi property bật | `@ConditionalOnProperty` trên cấu hình/bean |
| Cung cấp đối tượng thư viện ngoài | `@Bean` trong `@Configuration` |
| Chỉ định rõ module hoặc cấu hình cần bật | `@Import` hoặc cấu hình theo module |
| Tránh một auto-configuration của Spring Boot | Cơ chế exclude auto-configuration, không phải component scan filter |
| Bean có nhiều implementation, cần chọn một | `@Qualifier`, `@Primary` hoặc thiết kế injection phù hợp |

Các cơ chế có thể phối hợp, nhưng mỗi cơ chế điều khiển một tầng khác nhau: **tìm ứng viên**, **đăng ký có điều kiện**, **chọn ứng viên khi tiêm**, hoặc **cấu hình framework tự động**.

Với ứng dụng nhỏ, nếu chỉ có một implementation và package root hợp lý, để mặc định Spring Boot component scanning thường là đơn giản nhất. Filter phát huy giá trị khi thực sự có yêu cầu chọn một nhóm class cụ thể hoặc loại một nhóm khỏi cơ chế quét.

## 17. Bài tập tự áp dụng: quét adapter theo nhu cầu

Giả sử ứng dụng xử lý đơn hàng có cấu trúc:

~~~text
com.example.orders
├── OrdersApplication.java
├── api/
│   └── OrderController.java           @RestController
├── service/
│   └── OrderService.java              @Service
└── adapters/
    ├── EmailNotifier.java            @NotificationAdapter
    ├── SmsNotifier.java              @NotificationAdapter
    ├── OldFaxNotifier.java           @NotificationAdapter @Deprecated
    └── DebugHelper.java               @Component
~~~

Yêu cầu:

1. Controller và service của ứng dụng vẫn phải được đăng ký bình thường.
2. Trong nhóm `adapters`, chỉ các lớp đánh dấu `@NotificationAdapter` mới được quét.
3. `OldFaxNotifier` không được chọn từ lần scan adapter.
4. Không tạo hai bean cùng interface rồi inject đơn lẻ mà không có quy tắc chọn.

Một cách thiết kế có thể là:

- Đặt các adapter cần chọn lọc ở một package **không bị scan mặc định khác bao phủ**.
- Dùng một cấu hình `@ComponentScan` riêng cho package adapter với `useDefaultFilters = false`, include `@NotificationAdapter` và exclude `@Deprecated`.
- Đăng ký cấu hình scan adapter một cách tường minh, ví dụ qua `@Import`.
- Giữ component scan mặc định cho các package ứng dụng thông thường.
- Nếu cần nhiều notifier đồng thời, inject danh sách; nếu chỉ cần một, tạo lựa chọn rõ ràng theo cấu hình hoặc qualifier.

Bài tập này cho thấy vì sao phải thiết kế **phạm vi** trước khi viết filter: nếu `adapters` đã nằm trong một scan mặc định phủ toàn `com.example.orders`, cấu hình lọc riêng không tự loại `DebugHelper` hoặc `OldFaxNotifier` được tìm thấy từ lần scan trước.

## 18. Những nguyên tắc nên ghi nhớ

1. **`@ComponentScan` tìm ứng viên trong package, rồi áp dụng quy tắc lọc.** Package ngoài vùng quét không trở thành ứng viên chỉ vì có `@Component`.
2. **Mặc định vẫn quét stereotype.** Include filter thông thường mở rộng tập ứng viên; để chỉ nhận các class khớp include filter, cần hiểu và cấu hình `useDefaultFilters = false`.
3. **Exclude filter chỉ tác động đến hoạt động component scan tương ứng.** Bean vẫn có thể được đăng ký bởi `@Bean`, `@Import`, auto-configuration hoặc một scan khác.
4. **`basePackageClasses` giúp tránh chuỗi package dễ sai khi refactor.** Marker interface là một lựa chọn nhẹ để đặt ranh giới quét.
5. **`@SpringBootApplication` có cơ chế component scan mặc định theo package.** Vị trí đặt lớp khởi động ảnh hưởng trực tiếp đến những thành phần được phát hiện.
6. **Component scan khác với JPA entity/repository scanning và bean scope.** Mỗi cơ chế có mục đích và cấu hình riêng.
7. **Filter có thể thay đổi đồ thị dependency.** Loại một service hoặc repository có thể khiến bean khác không thể khởi tạo; thêm ứng viên có thể gây `NoUniqueBeanDefinitionException`.
8. **Ưu tiên cấu hình đơn giản thể hiện đúng ý định.** Khi điều kiện thực chất là dev/prod hoặc bật/tắt tính năng, profile/conditional có thể sáng rõ hơn regex hoặc custom filter.

## Kết luận

`@ComponentScan` quyết định **Spring được tìm ở đâu và những lớp nào được xem là ứng viên bean**. Phạm vi được xác định bằng package gốc; `includeFilters` mở rộng hoặc, khi tắt filter mặc định, giới hạn các loại ứng viên được nhận; `excludeFilters` loại các lớp phù hợp khỏi lần quét. Các filter này làm việc cùng các cơ chế đăng ký và cấu hình bean khác của Spring Boot, vì vậy luôn cần hiểu nguồn đăng ký của từng bean.

Khi một bean không xuất hiện hoặc xuất hiện ngoài dự kiến, hãy bắt đầu từ package của lớp khởi động, package gốc được cấu hình, `useDefaultFilters`, filter đang áp dụng và những nguồn đăng ký bean khác. Hiểu rõ những yếu tố này giúp tổ chức mã Spring Boot thành các module có ranh giới rõ, tránh đăng ký nhầm component và giải thích chính xác những thay đổi trong ApplicationContext.
