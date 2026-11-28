# Parent và nested module trong graph

> **Chương:** Module graph  
> **Module học tập:** `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`  
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.

## 1. Parent và nested module giải quyết vấn đề gì?

Một ứng dụng Spring Boot phát triển lâu dài thường có những phần nghiệp vụ quá lớn để biểu diễn bằng một application module duy nhất. Ví dụ, module `sales` có các quy trình riêng như `checkout`, `billing` và quản lý chính sách bán hàng. Nếu chỉ vẽ một ô `sales`, đội phát triển khó xác định phần nào phụ thuộc phần nào. Ngược lại, nếu xem mọi package như các module ngang hàng, sơ đồ đánh mất cấu trúc phân cấp nghiệp vụ.

Spring Modulith cho phép mô hình hóa **application module nằm trong application module khác**. Trong quan hệ này:

- **Parent module** (module cha): module chứa các nested module trong mô hình phân cấp. Ví dụ `sales` là parent của `sales.checkout` và `sales.billing`.
- **Nested module** (module lồng): application module được khai báo bên dưới package của parent; nó vẫn có ranh giới và API module để các quy tắc kiến trúc có thể kiểm tra.
- **Root application module**: module ở cấp cao nhất dưới package gốc ứng dụng, ví dụ `sales`, `catalog` hoặc `notification`.

Đặc điểm quan trọng nhất: **quan hệ parent–nested là quan hệ phân cấp/bao chứa (containment), không phải bằng chứng có lời gọi hoặc phụ thuộc mã giữa hai module**.

### Kết quả cần đạt

Sau bài này, người học có thể:

1. Phân biệt root, parent và nested application module với Java package thông thường.
2. Đọc module graph mà không nhầm đường phân cấp với các cạnh dependency.
3. Khai báo một nested module bằng `package-info.java` và `@ApplicationModule` trong dự án hỗ trợ tính năng này.
4. Đọc đúng ý nghĩa của đồ thị khi các nested module được hiển thị riêng hoặc được gom vào parent.
5. Kết hợp `ApplicationModules.verify()`, `Documenter` và Actuator để kiểm tra cấu trúc; dùng metrics/tracing khi cần bằng chứng tương tác thực tế.

## 2. Cấu trúc ví dụ: sales chứa checkout và billing

Giả sử hệ thống bán hàng có cấu trúc package:

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
│   ├── CatalogApi.java
│   └── internal
│       └── CatalogRepositoryAdapter.java
├── sales
│   ├── SalesFacade.java                     # API ở cấp parent sales
│   ├── internal
│   │   └── SalesPolicy.java
│   ├── checkout
│   │   ├── package-info.java                # Khai báo nested module
│   │   ├── CheckoutOperations.java          # API của sales.checkout
│   │   ├── CheckoutCompleted.java           # Event API của sales.checkout
│   │   └── internal
│   │       └── CheckoutService.java
│   └── billing
│       ├── package-info.java                # Khai báo nested module
│       ├── BillingOperations.java           # API của sales.billing
│       └── internal
│           └── CheckoutCompletedListener.java
└── notification
    ├── NotificationApi.java
    └── internal
        └── EmailSender.java
~~~

Đặt `ShopApplication` ở package gốc `com.acme.shop` giúp Spring Modulith nhận diện các package con trực tiếp như `catalog`, `sales` và `notification` thành **root application modules** theo chiến lược phát hiện module mặc định phù hợp. Riêng `sales.checkout` và `sales.billing` được khai báo là **nested application modules**, không đơn thuần là package con phụ trợ.

Mô hình phân cấp mong đợi ở mức khái niệm:

~~~mermaid
flowchart TB
    App["Ứng dụng Shop"]
    App --- Sales["sales (root, parent)"]
    App --- Catalog["catalog (root)"]
    App --- Notification["notification (root)"]
    Sales --- Checkout["sales.checkout (nested)"]
    Sales --- Billing["sales.billing (nested)"]
    linkStyle default stroke-dasharray: 5 5
~~~

**Trong sơ đồ trên, tất cả nét nối đứt biểu thị quan hệ phân cấp**, không biểu thị Java dependency, event publication hay call graph. Đây là **sơ đồ tư duy để giải thích containment**, không phải cam kết về hình thức sơ đồ do một phiên bản `Documenter` nhất định sinh ra.

### Ba câu hỏi khác nhau

| Câu hỏi | Câu trả lời trong ví dụ | Loại thông tin |
|---|---|---|
| `checkout` nằm trong phạm vi nghiệp vụ nào? | `sales` | Parent/nested hierarchy |
| `billing` có dùng API của `checkout` không? | Phải phân tích dependency thực tế trong mã | Static dependency |
| Khi checkout thành công, listener billing có chạy không? | Phải xem trace/event publication/runtime logs | Runtime execution |

Một package như `sales.internal` chỉ là package con thuộc phần triển khai nội bộ của `sales` nếu không được khai báo/nhận diện như nested module. **Không phải mọi dấu chấm trong tên package đều tương ứng một cạnh parent–nested của application module graph.**

## 3. Cách khai báo nested module

### 3.1. Parent module ở cấp gốc

Với chiến lược phát hiện module mặc định, `sales` đã là root application module vì nó là package con trực tiếp của root package ứng dụng. Thông thường không cần tự thêm annotation vào package `sales` chỉ để biến nó thành root module.

Ví dụ class khởi động:

~~~java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Phạm vi root package này ảnh hưởng đến module detection. Nếu chuyển `ShopApplication` sang package khác, sử dụng kiểu phát hiện module tùy chỉnh hoặc cấu hình vùng scan khác, kết quả graph có thể thay đổi.

### 3.2. Đánh dấu package của nested module

Trong các phiên bản Spring Modulith hỗ trợ nested application modules, có thể dùng `@ApplicationModule` trên `package-info.java` tại package muốn tách thành module:

~~~java
// src/main/java/com/acme/shop/sales/checkout/package-info.java

@org.springframework.modulith.ApplicationModule
package com.acme.shop.sales.checkout;
~~~

~~~java
// src/main/java/com/acme/shop/sales/billing/package-info.java

@org.springframework.modulith.ApplicationModule
package com.acme.shop.sales.billing;
~~~

Hai khai báo trên thể hiện ý định đưa `checkout` và `billing` thành application module riêng nằm trong `sales`. Đường dẫn `package-info.java` và mệnh đề `package` phải khớp chính xác; annotation đặt vào file ngẫu nhiên hoặc package khác không đạt mục đích đó.

**Lưu ý phiên bản:** Cơ chế phát hiện, cấu hình nested module và khả năng hiển thị phân cấp phụ thuộc phiên bản Spring Modulith. Kiểm tra API `@ApplicationModule` và kết quả `ApplicationModules` của version mà dự án đang sử dụng. Ví dụ trong bài giả định phiên bản đã hỗ trợ khai báo module lồng theo cách này.

### 3.3. Ranh giới API của nested module

Trong ví dụ:

- `com.acme.shop.sales.checkout.CheckoutOperations` là một kiểu đặt ở base package của nested module `sales.checkout`, có thể được thiết kế làm API.
- `com.acme.shop.sales.checkout.internal.CheckoutService` nằm dưới package nội bộ của nested module; việc đánh dấu lớp là Java `public` **không mặc nhiên khiến nó trở thành API được phép dùng từ các module khác**.
- `com.acme.shop.sales.billing.CheckoutCompletedListener` là lớp triển khai thuộc nested module `sales.billing`; nó có thể tham chiếu kiểu sự kiện đã công bố trong API `sales.checkout`.

Dù cùng nằm bên dưới `com.acme.shop.sales`, `checkout` và `billing` không nên được xem là một khối mã hoàn toàn không có ranh giới. Chính việc phân chia thành nested modules cho phép kiểm tra phụ thuộc và che giấu implementation rõ hơn.

**Không suy diễn quyền truy cập chỉ từ cây package.** Mọi ngoại lệ, named interface, allowed dependencies hoặc quy tắc áp dụng cho parent và nested phải được kiểm tra theo cấu hình module thực tế và `verify()`. Quan hệ cha–con tự nó không phải cơ chế phân quyền, Spring Bean scope hay transaction scope.

## 4. Phân biệt cạnh phân cấp với cạnh dependency

Giả sử `sales.checkout` dùng API của `catalog` để đọc giá sản phẩm; `sales.billing` dùng kiểu `CheckoutCompleted` do `sales.checkout` công bố.

Có hai tập quan hệ tách biệt:

**Quan hệ containment:**

~~~text
sales
├── sales.checkout
└── sales.billing
~~~

**Quan hệ dependency tĩnh:**

~~~text
sales.checkout ──uses component/API──> catalog
sales.billing  ──uses event type─────> sales.checkout
~~~

Khi trình bày chung:

~~~mermaid
flowchart LR
    subgraph Sales["sales — parent / ranh giới phân cấp"]
        direction TB
        Checkout["sales.checkout"]
        Billing["sales.billing"]
    end
    Catalog["catalog"]
    Checkout -->|"USES_COMPONENT / phụ thuộc API"| Catalog
    Billing -->|"EVENT_LISTENER / tham chiếu event"| Checkout
~~~

Khung `Sales` có nghĩa hai nested module **thuộc parent `sales`**. Mũi tên liền từ `sales.checkout` đến `catalog` là **dependency giữa hai module**. Mũi tên từ `sales.billing` đến `sales.checkout` là **dependency của listener vào kiểu event/API**; không được tự diễn giải nó thành chiều sự kiện chạy.

### Phân loại chính xác các quan hệ

| Quan hệ | Ví dụ | Nguồn thông tin | Ý nghĩa |
|---|---|---|---|
| Parent–nested | `sales` chứa `sales.checkout` | Cấu trúc module đã được nhận diện | Phân cấp module |
| Dependency dùng component | `sales.checkout → catalog` | Phân tích tham chiếu Java/Spring của module | Code checkout phụ thuộc API của catalog |
| Dependency kiểu event listener | `sales.billing → sales.checkout` | Phân tích listener/kiểu event | Code billing tham chiếu event của checkout |
| Runtime event flow | `checkout → billing` | Trace, event publication, logs | Một event đi từ publisher đến consumer trong lần chạy được ghi nhận |
| Runtime method invocation | `checkout → catalog` | Span/trace đã instrument | Lời gọi thực sự xảy ra trong một execution cụ thể |

**Hai cạnh đối hướng có thể cùng đúng:** nếu listener trong billing tham chiếu `CheckoutCompleted` từ checkout, dependency tĩnh có thể là `billing → checkout`; nhưng sự kiện runtime được phát từ checkout sang billing. Graph tĩnh và luồng runtime đang biểu diễn hai khái niệm khác nhau.

## 5. Đọc graph khi có nhiều cấp module

### 5.1. Biểu diễn phân cấp và biểu diễn phẳng

Cùng một kiến trúc có thể được trình bày dưới dạng cây hoặc graph phẳng.

**Dạng cây** giúp trả lời module nào thuộc parent nào:

~~~text
Shop
├── catalog
├── sales
│   ├── checkout
│   └── billing
└── notification
~~~

**Dạng graph phẳng** giúp tập trung vào các cạnh dependency của những module được hiển thị:

~~~mermaid
flowchart LR
    Checkout["sales.checkout"] --> Catalog["catalog"]
    Billing["sales.billing"] --> Checkout
    Notification["notification"]
~~~

Trong graph phẳng, định danh dạng `sales.checkout` giúp nhận biết module thuộc parent nào nếu công cụ xuất đủ định danh. Tuy nhiên, định dạng tên hiển thị có thể khác theo cấu hình/phiên bản; không nên viết parser giả định mọi tên module đều luôn là `parent.child`.

Graph phẳng không nhất thiết hiển thị riêng parent nếu chế độ xuất sơ đồ chỉ chọn những module/phụ thuộc cần thiết. **Module không xuất hiện trong một hình vẽ không mặc nhiên có nghĩa nó vắng mặt trong mô hình**: hãy kiểm tra chế độ lọc, phạm vi tài liệu và metadata do công cụ thực sự trả về.

### 5.2. “Thu gọn” parent sẽ làm mất chi tiết nào?

Giả sử cả hai nested module của `sales` đều phụ thuộc `catalog`:

~~~text
sales.checkout → catalog
sales.billing  → catalog
~~~

Một sơ đồ tổng quan **được thu gọn theo parent** có thể chỉ vẽ:

~~~text
sales → catalog
~~~

Cạnh `sales → catalog` trong bản thu gọn là **tóm tắt các phụ thuộc bên trong phạm vi `sales`**, không đủ bằng chứng rằng code thuộc base package trực tiếp của parent `sales` phụ thuộc `catalog`.

Ngược lại, nếu bản tổng quan không hiển thị `sales.billing`, không được kết luận `billing` hoàn toàn không có dependency. Muốn đánh giá chi tiết, hãy mở rộng nested module, xem graph của từng module và danh sách dependency đầy đủ.

### 5.3. Nested sâu hơn một cấp

Về mặt khái niệm, một mô hình có thể chứa nhiều tầng:

~~~text
sales
└── checkout
    └── payment
~~~

Tuy vậy, việc khai báo và phát hiện **nhiều tầng nested module** còn phụ thuộc phiên bản cùng chiến lược module detection. Không suy ra rằng cứ thêm package `sales.checkout.payment` thì công cụ sẽ tự tạo module ở tầng thứ ba. Cần xác minh bằng `ApplicationModules` trước khi đưa mô hình đó vào tài liệu chính thức.

## 6. Nhận diện API và dependency trong từng ranh giới

Xét kiểu event công khai của checkout:

~~~java
// src/main/java/com/acme/shop/sales/checkout/CheckoutCompleted.java

package com.acme.shop.sales.checkout;

import java.util.UUID;

public record CheckoutCompleted(UUID checkoutId) {}
~~~

Và listener thuộc billing:

~~~java
// src/main/java/com/acme/shop/sales/billing/internal/CheckoutCompletedListener.java

package com.acme.shop.sales.billing.internal;

import com.acme.shop.sales.checkout.CheckoutCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class CheckoutCompletedListener {

    @ApplicationModuleListener
    void on(CheckoutCompleted event) {
        // Gửi yêu cầu nghiệp vụ đến BillingOperations hoặc service trong billing.
        // Phần hiện thực xử lý thanh toán được lược bỏ.
    }
}
~~~

Vì mã của billing **tham chiếu kiểu `CheckoutCompleted`**, công cụ có căn cứ nhận diện phụ thuộc tĩnh từ `sales.billing` đến `sales.checkout`. Listener này là ví dụ về **tương tác giữa hai nested modules cùng parent**, nhưng vẫn là tương tác qua ranh giới module.

Ngược lại, cách viết dưới đây là **tình huống cần tránh**:

~~~java
// Ví dụ phản diện: code thuộc billing cố tham chiếu triển khai internal.
import com.acme.shop.sales.checkout.internal.CheckoutService;
~~~

Ngay cả nếu `CheckoutService` được khai báo Java `public`, nó thuộc package triển khai nội bộ của `sales.checkout`. Spring Modulith có thể đánh dấu việc truy cập này là vi phạm ranh giới module khi chạy kiểm tra cấu trúc theo quy tắc tương ứng.

Điều cần quan sát là **module phát sinh dependency, module đích và vị trí API/internal của kiểu được tham chiếu**; không chỉ xem hai lớp nằm bên dưới cùng chuỗi `sales`.

## 7. Xây module graph và kiểm tra phân cấp

### 7.1. Tạo mô hình trong test

Sử dụng `ApplicationModules` để nhận diện module từ root Spring Boot application:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTests {

    @Test
    void verifyModuleStructure() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        modules.verify();
    }
}
~~~

`verify()` kiểm tra các bất biến kiến trúc được Spring Modulith hỗ trợ, ví dụ những vòng phụ thuộc giữa module, truy cập implementation nội bộ từ module khác và khai báo dependency được phép nếu có.

Một test thành công có nghĩa là **không phát hiện vi phạm theo các quy tắc và mô hình đang kiểm tra**. Nó không chứng minh checkout/billing đã hoạt động đúng về mặt nghiệp vụ, đã truyền sự kiện thành công hoặc có thể quan sát qua tracing.

### 7.2. Sinh tài liệu module graph

Dùng `Documenter` của Spring Modulith:

~~~java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleGraphDocumentationTests {

    @Test
    void generateGraphAndCanvas() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        modules.verify();

        new Documenter(modules)
                .writeModulesAsPlantUml()
                .writeIndividualModulesAsPlantUml()
                .writeModuleCanvases();
    }
}
~~~

Ví dụ giả định dự án đã có dependency test cho `spring-modulith-docs`, chẳng hạn qua `spring-modulith-starter-test`. Tùy phiên bản và tùy chọn, `Documenter` có thể cung cấp các kiểu biểu diễn và khả năng lọc module/dependency khác nhau.

**Cách đọc tài liệu sinh ra:**

1. Tìm root module `sales` và xác định các nested modules `checkout`/`billing` có được nhận diện riêng hay không.
2. Kiểm tra sơ đồ hoặc canvas ở mức chi tiết để hiểu dependency của từng nested module.
3. Nếu hình vẽ chỉ hiển thị parent hoặc bỏ qua nested module, kiểm tra cấu hình/filter của `Documenter` và model discovery trước khi kết luận.
4. Ghi lại version Spring Modulith, commit/build ID và lựa chọn render để đối chiếu các bản tài liệu về sau.

Không nên coi một kiểu render PlantUML/C4 là chuẩn JSON cố định cho mọi phiên bản. **Mô hình module được phát hiện là nguồn cần kiểm tra; hình vẽ là một cách trình bày mô hình ấy.**

### 7.3. Đọc kết quả từ Actuator của bản triển khai

Với Spring Boot Actuator và Spring Modulith Actuator có trên runtime classpath (ví dụ thông qua Insight starter), expose endpoint `modulith` ở môi trường thử nghiệm:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,modulith,metrics"
~~~

Nếu ứng dụng web chạy cổng `8080`, base path Actuator mặc định và quyền truy cập cho phép:

~~~bash
curl -i http://localhost:8080/actuator/modulith
~~~

Endpoint trả **metadata application module của bản đang chạy**. Hãy tìm trong dữ liệu module, tên/định danh, base package, quan hệ phụ thuộc và **thông tin phân cấp parent/nested nếu định dạng ở phiên bản đang dùng cung cấp**. Tên trường cụ thể, cấu trúc nested và cách thể hiện dependency có thể thay đổi theo phiên bản; không nên viết công cụ phân tích dựa vào JSON giả định chưa đối chiếu với payload thực tế.

Đặc biệt, `/actuator/modulith` **không phải đồ thị các method call xảy ra trong production**. Nó giúp đối chiếu kiến trúc của artifact triển khai, kể cả khi ứng dụng chưa hề phục vụ một request nghiệp vụ nào.

### 7.4. Đối chiếu CI với bản triển khai

Để tránh hai sơ đồ nhìn khác nhau vì deploy sai phiên bản:

| Bước | Chứng cứ | Câu hỏi |
|---|---|---|
| Build/CI | `ApplicationModules` + `Documenter` | Graph trong commit hiện tại nhận diện nested modules nào? |
| Build/CI | `modules.verify()` | Có vi phạm ranh giới hoặc dependency ngoài ý muốn không? |
| Deploy | Build ID/commit/version | Ứng dụng đang chạy là artifact nào? |
| Deploy | `GET /actuator/modulith` | Mô hình module ở runtime có khớp với artifact cần kiểm tra không? |
| Thực thi kịch bản | Metrics/tracing/event registry/logs | Một tương tác cụ thể giữa nested modules có thực sự xảy ra và hoàn thành không? |

Chỉ so sánh sơ đồ khi chắc chắn **đúng artifact**, cùng chiến lược module detection và cùng cách lọc/hiển thị.

## 8. Case study: đọc sai graph khiến điều tra lỗi lệch hướng

Nhóm phát triển có `sales` gồm `checkout` và `billing`. Sau khi thanh toán, một số giao dịch không phát hành hóa đơn.

Tài liệu tổng quan cho thấy:

~~~text
sales → catalog
~~~

Một kỹ sư kết luận: “`billing` không có đường nối tới `checkout`, nên chức năng phát hành hóa đơn chưa được tích hợp.” Kết luận này thiếu cơ sở vì sơ đồ tổng quan có thể **đang thu gọn parent** hoặc chỉ hiện một tập dependency.

Quy trình đúng:

1. **Xác định phạm vi của graph:** hình vẽ này hiển thị root modules hay có mở rộng nested modules?
2. **Kiểm tra mô hình module:** `sales.checkout` và `sales.billing` có thực sự được nhận diện là nested modules không? Có bị khai báo thiếu `package-info.java`?
3. **Mở graph chi tiết:** có cạnh dependency tĩnh `sales.billing → sales.checkout` do listener dùng kiểu `CheckoutCompleted` không?
4. **Kiểm tra quy tắc:** `verify()` có phát hiện access vào package `checkout.internal` hoặc cycle bất hợp lệ không?
5. **Nếu nghi ngờ luồng chạy:** xem publication state, trace/span, event metrics và log của giao dịch đó, rồi kiểm tra kết quả phát hành hóa đơn.

Ở bước 3, phát hiện cạnh dependency chứng minh **có liên hệ mã ở cấp kiến trúc**, vẫn chưa chứng minh listener đã nhận hay xử lý event. Nếu metric phát event tăng mà listener thất bại, vấn đề nằm ở **runtime behavior**, không nhất thiết ở cấu trúc parent–nested.

### Cạnh dependency và chiều giao sự kiện khác nhau

~~~mermaid
flowchart TB
    subgraph S["sales (parent)"]
        Checkout["sales.checkout"]
        Billing["sales.billing"]
    end
    Billing -->|"dependency: kiểu CheckoutCompleted"| Checkout
    Checkout -.->|"runtime: event được phát/nhận nếu thực thi"| Billing
~~~

Sơ đồ có hai mũi tên trái chiều nhưng không mâu thuẫn: mỗi mũi tên có **ngữ nghĩa riêng**. Cạnh chứa hai module trong cùng parent là một chuyện thứ ba.

## 9. Khi nào nên tách nested module?

Nested module hữu ích khi một root module đã quá rộng nhưng các phần con vẫn thuộc chung miền nghiệp vụ lớn.

**Dấu hiệu nên cân nhắc:**

- `sales` có các nhóm chức năng tương đối độc lập: đặt hàng, thanh toán, xuất hóa đơn.
- Các nhóm cần có API rõ ràng và giới hạn truy cập implementation của nhau.
- Đồ thị parent ở cấp root đang che mất những phụ thuộc nội bộ quan trọng.
- Cần review/verify kiến trúc chi tiết mà vẫn giữ cây nghiệp vụ ở cấp cao dễ đọc.

**Dấu hiệu chưa cần tách:**

- Package con chỉ là nhóm kỹ thuật rất nhỏ như `config`, `internal`, `repository` mà không có hợp đồng nghiệp vụ riêng.
- Việc chia nested module làm API phình to, tăng số cạnh dependency hoặc tạo chu trình khó giải quyết.
- Nhóm muốn dùng nested module để thay cho service riêng, transaction boundary hoặc cơ chế cách ly dữ liệu dù yêu cầu đó chưa được thiết kế.

Một nested module vẫn chạy **trong cùng ứng dụng Spring Boot** và có thể cùng JVM, dependency injection container, database hoặc transaction infrastructure. Cách tổ chức module **không tự sinh ra tiến trình độc lập**. Trước khi tách, hãy xác định hợp đồng API, nơi phát event, owner của dữ liệu và cách kiểm chứng dependency.

### Đặt tên và phân cấp ổn định

Nên chọn parent theo miền nghiệp vụ (`sales`), nested theo năng lực nghiệp vụ (`checkout`, `billing`). Hạn chế tạo các tầng lồng quá sâu chỉ để phản ánh cơ cấu nhóm hoặc thư mục kỹ thuật; nhiều tầng khiến đồ thị khó đọc và dễ bị hiểu sai khi collapse.

Khi thay đổi tên/nơi đặt package, cần cập nhật code import, package-info, tài liệu và kiểm thử module. **Một refactor package có thể làm thay đổi module detection ngay cả khi luồng nghiệp vụ không đổi.**

## 10. Các nhầm lẫn thường gặp

| Ngộ nhận | Cách hiểu chính xác |
|---|---|
| “Bất kỳ package con nào cũng là nested module.” | Package con có thể chỉ là implementation; nested application module phải được công cụ nhận diện theo quy tắc/cấu hình phiên bản. |
| “Parent chứa nested nên chắc chắn parent gọi nested.” | Parent–nested là quan hệ phân cấp, không phải một dependency hay runtime call. |
| “Hai nested module cùng parent thì tự do gọi mọi lớp của nhau.” | Cần tôn trọng API/named interface và quy tắc ranh giới module; dùng `verify()` để xác nhận. |
| “Từ `sales → catalog` suy ra chính `SalesFacade` sử dụng catalog.” | Graph thu gọn có thể tổng hợp dependency từ nested module; phải xem chi tiết. |
| “Graph phẳng không có `sales`, tức không tồn tại parent.” | Phụ thuộc chế độ hiển thị; cần đối chiếu mô hình module và metadata. |
| “`billing → checkout` nghĩa checkout đã gọi billing thành công.” | Đây có thể là static dependency của event listener vào kiểu event; runtime event flow có chiều khác. |
| “`verify()` pass nghĩa listener billing đã xuất hóa đơn thành công.” | Verify kiểm tra kiến trúc; thành công nghiệp vụ cần test và dữ liệu runtime. |
| “Actuator công bố module graph giống trace request.” | `/actuator/modulith` công bố metadata cấu trúc của deploy; trace ghi nhận execution được instrument. |
| “Chỉ thêm nested module là tự có distributed tracing.” | Cần cấu hình hạ tầng observability, tracer/exporter, sampling và context propagation khi cần. |

## 11. Bài thực hành kiểm chứng parent–nested

Chuẩn bị ứng dụng mẫu cùng bố cục `sales.checkout`, `sales.billing` và `catalog` ở trên. Thực hiện trong môi trường phát triển:

1. Chạy test dựng `ApplicationModules.of(ShopApplication.class)` và gọi `verify()`.
2. Sinh PlantUML/module canvases bằng `Documenter`. Xác định root `sales` và hai nested modules trong mô hình được hỗ trợ bởi phiên bản dự án.
3. Cho `CheckoutOperations` gọi một API công khai của `CatalogApi`; quan sát dependency `sales.checkout → catalog` ở graph chi tiết.
4. Cho `CheckoutCompletedListener` tham chiếu event API của `sales.checkout`; quan sát dependency tĩnh `sales.billing → sales.checkout`.
5. Thử tham chiếu một kiểu Java `public` ở `sales.checkout.internal` từ billing. Chạy `verify()` và ghi nhận quy tắc ranh giới nào phát hiện vi phạm (nếu mô hình/cấu hình áp dụng ràng buộc đó).
6. Mở graph ở mức parent (nếu công cụ có tùy chọn phù hợp) và ở mức nested để chỉ ra thông tin bị thu gọn.
7. Nếu có Actuator, kiểm tra mô hình trên `/actuator/modulith` của đúng build.
8. Nếu có observability, thực thi checkout thành công và đối chiếu metric/trace/event registry với graph tĩnh. Ghi nhận rõ khoảng thời gian, ID sự kiện và sampling để tránh kết luận từ trace thiếu.

### Bảng ghi kết quả gợi ý

| Mục kiểm tra | Kỳ vọng | Bằng chứng tự thu thập |
|---|---|---|
| Nhận diện root | `sales`, `catalog`... | Danh sách module hoặc tài liệu sinh ra |
| Nhận diện nested | `sales.checkout`, `sales.billing` | Thông tin phân cấp/module ID phù hợp version |
| Cạnh API | `sales.checkout → catalog` | Graph chi tiết |
| Cạnh event type | `sales.billing → sales.checkout` | Graph chi tiết/canvas |
| Quy tắc internal | Không được sử dụng tùy tiện `checkout.internal` | Kết quả `verify()` |
| Runtime event | Có/không có xử lý event trong lần thử | Trace, logs, registry và trạng thái nghiệp vụ |

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Trong code có package `com.acme.shop.sales.internal`. Package này có mặc nhiên là nested application module của `sales` không?

**Đáp án:** Không. Package con là chi tiết tổ chức Java; cần được nhận diện thành application module theo chiến lược phát hiện và cấu hình thực tế mới trở thành nested module.

**Câu 2.** Sơ đồ có khung `sales` bao quanh `checkout` và `billing`. Có thể kết luận `billing` phụ thuộc `checkout` không?

**Đáp án:** Chưa thể. Khung bao chỉ mô tả hierarchy. Cần xem cạnh dependency tĩnh thực sự được phát hiện giữa các module.

**Câu 3.** Vì sao graph tổng quan `sales → catalog` có thể không đủ để truy lỗi thanh toán?

**Đáp án:** Graph có thể đang gom các phụ thuộc của nested modules vào parent. Phải xem graph chi tiết mới biết `checkout` hay `billing` phụ thuộc `catalog`.

**Câu 4.** Listener ở `billing` sử dụng kiểu `CheckoutCompleted` trong API `checkout`. Vì sao graph có thể hiển thị `billing → checkout` dù event chạy từ checkout sang billing?

**Đáp án:** Mũi tên tĩnh chỉ chiều phụ thuộc mã. Event flow trong runtime có chiều publisher → consumer; hai biểu diễn khác ngữ nghĩa.

**Câu 5.** Sau khi tách `sales.billing` thành nested module, bài test `verify()` thành công. Có thể kết luận mọi hóa đơn được phát hành đúng không?

**Đáp án:** Không. Kiểm tra cấu trúc không thay thế kiểm thử nghiệp vụ, giao dịch, xử lý lại event và bằng chứng runtime.

**Câu 6.** Khi tài liệu CI không thấy `sales.checkout` nhưng Actuator của deploy hiển thị nó, cần kiểm tra điều gì trước?

**Đáp án:** Xác nhận commit/build/version và cấu hình module detection, sau đó kiểm tra bộ lọc/chế độ hiển thị của tài liệu CI; không vội kết luận một nguồn sai.

## 13. Tổng kết

- **Parent–nested** mô tả **quan hệ phân cấp** của application modules: `sales` chứa `sales.checkout` và `sales.billing`.
- **Dependency edges** mô tả những phụ thuộc được phân tích từ mã, ví dụ `billing → checkout` hoặc `checkout → catalog`; chúng **không phát sinh chỉ vì quan hệ parent–nested**.
- **Graph tổng quan** có thể thu gọn nested module; muốn tìm nguyên nhân của một phụ thuộc, cần đọc graph chi tiết và API module tương ứng.
- Dùng `@ApplicationModule`, `ApplicationModules.verify()` và `Documenter` theo phiên bản Spring Modulith dự án để **định nghĩa, xác minh và trình bày** ranh giới.
- Dùng `/actuator/modulith` để **đối chiếu metadata cấu trúc của bản triển khai**. Dùng metrics, tracing, event registry và kiểm chứng dữ liệu khi cần trả lời **điều gì đã xảy ra trong runtime**.

## Tài liệu tham khảo

1. [Spring Modulith Reference – Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html) — Quy ước phát hiện application modules, API và nested modules.
2. [Spring Modulith Reference – Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html) — `Documenter`, module graph và module canvas.
3. [Spring Modulith Reference – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html) — Các ràng buộc và quy tắc kiểm tra dependency.
4. [Spring Modulith Reference – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — Actuator, observability, module invocations và event metrics.
5. [Spring Modulith Reference – Application Events](https://docs.spring.io/spring-modulith/reference/events.html) — Event publication và listener.

