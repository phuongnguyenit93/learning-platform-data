# Viết custom ApplicationModuleDetectionStrategy

## Mục tiêu thực hành

Trong bài này, bạn sẽ tạo một chiến lược phát hiện application module theo quy ước package của một ứng dụng Spring Boot. Sau khi hoàn thành, bạn có thể:

- Giải thích khi nào quy tắc mặc định của Spring Modulith chưa phù hợp.
- Viết lớp triển khai ApplicationModuleDetectionStrategy.
- Chọn đúng package con của package gốc làm module.
- Đăng ký chiến lược qua spring.modulith.detection-strategy.
- Kiểm tra danh sách module được phát hiện và chạy ApplicationModules.verify().
- Phân biệt cấu hình chỉ phục vụ test/tài liệu với cấu hình cần có trong production runtime.

Bài thực hành sử dụng một ứng dụng quản lý hoàn tất đơn hàng có các package nghiệp vụ orders, stock và delivery, cùng các package kỹ thuật configuration, bootstrap và observability.

## Tình huống và cấu trúc ban đầu

Giả sử lớp Spring Boot application nằm tại com.acme.fulfillment. Cấu trúc package hiện tại:

~~~text
com.acme.fulfillment
├── FulfillmentApplication.java
├── orders
│   ├── OrderManagement.java
│   └── internal
├── stock
│   ├── StockManagement.java
│   └── internal
├── delivery
│   ├── DeliveryManagement.java
│   └── internal
├── configuration
│   └── PersistenceConfiguration.java
├── bootstrap
│   └── StartupDataLoader.java
└── observability
    └── FulfillmentMetrics.java
~~~

Theo mặc định, Spring Modulith xem các package con trực tiếp của package gốc là application module. Với cấu trúc này, configuration, bootstrap và observability cũng có thể được phát hiện như module, dù nhóm chỉ muốn quản lý ranh giới nghiệp vụ của orders, stock và delivery.

Ta cần một quy tắc cụ thể:

- Chỉ orders, stock và delivery là module nghiệp vụ.
- Các package kỹ thuật không trở thành module độc lập.
- Package con như orders.internal vẫn thuộc module orders, không được phát hiện thành module cấp cao riêng.

Custom ApplicationModuleDetectionStrategy cho phép triển khai quy tắc này.

## Bước 1: Xác định package gốc và quy ước phát hiện

Package gốc là package chứa lớp được đánh dấu @SpringBootApplication. Trong ví dụ, đó là com.acme.fulfillment.

Chiến lược sẽ nhận một JavaPackage đại diện cho package gốc, duyệt các package con trực tiếp và chỉ giữ lại những package có tên cục bộ nằm trong danh sách module nghiệp vụ.

| Package con trực tiếp | Local name | Kết quả |
|---|---|---|
| com.acme.fulfillment.orders | orders | Phát hiện module |
| com.acme.fulfillment.stock | stock | Phát hiện module |
| com.acme.fulfillment.delivery | delivery | Phát hiện module |
| com.acme.fulfillment.configuration | configuration | Bỏ qua |
| com.acme.fulfillment.bootstrap | bootstrap | Bỏ qua |
| com.acme.fulfillment.observability | observability | Bỏ qua |

Dùng local name giúp chiến lược không phải ghép hoặc so sánh toàn bộ tên package ở nhiều vị trí. Tuy nhiên, quy tắc này giả định các module nghiệp vụ đều là package con trực tiếp của package gốc.

Nếu dự án đặt module ở nhiều root package khác nhau hoặc có nested module, hãy xác định rõ quy ước trước khi viết strategy. Một chiến lược chọn package con trực tiếp không tự động phát hiện mọi module nằm sâu trong cây package.

## Bước 2: Tạo lớp chiến lược tùy chỉnh

Tạo file BusinessModuleDetectionStrategy.java. Nếu chiến lược chỉ phục vụ kiểm chứng kiến trúc và tạo tài liệu trong test, đặt file tại src/test/java. Ví dụ:

~~~text
src/test/java
└── com/acme/fulfillment/architecture
    └── BusinessModuleDetectionStrategy.java
~~~

Nội dung lớp:

~~~java
package com.acme.fulfillment.architecture;

import java.util.Set;
import java.util.stream.Stream;

import org.springframework.modulith.core.ApplicationModuleDetectionStrategy;
import org.springframework.modulith.core.JavaPackage;

public class BusinessModuleDetectionStrategy
        implements ApplicationModuleDetectionStrategy {

    private static final Set<String> MODULE_NAMES =
        Set.of("orders", "stock", "delivery");

    @Override
    public Stream<JavaPackage> getModuleBasePackages(
            JavaPackage rootPackage) {

        return rootPackage.getDirectSubPackages().stream()
            .filter(candidate ->
                MODULE_NAMES.contains(candidate.getLocalName())
            );
    }
}
~~~

Có ba phần quan trọng:

1. MODULE_NAMES là danh sách các package được phép trở thành module.
2. getDirectSubPackages() lấy các package con trực tiếp của package gốc.
3. getLocalName() trả về tên đoạn cuối của package, ví dụ orders hoặc stock.

Phương thức trả về Stream<JavaPackage>, đúng với hợp đồng của ApplicationModuleDetectionStrategy. Spring Modulith dùng các package được trả về làm module base package.

Không trả về package gốc, package kỹ thuật hoặc package con nội bộ như orders.internal. Nếu trả về cả orders và orders.internal, bạn có thể vô tình tạo cấu trúc module lồng nhau ngoài chủ đích.

## Bước 3: Đăng ký strategy bằng application.properties

Tạo hoặc cập nhật file src/test/resources/application.properties:

~~~properties
spring.modulith.detection-strategy=com.acme.fulfillment.architecture.BusinessModuleDetectionStrategy
~~~

Giá trị phải là tên đầy đủ của lớp, gồm package và tên class. Lớp strategy phải có trên test classpath khi bài kiểm chứng chạy.

Spring Modulith nhận diện các giá trị strategy dựng sẵn như direct-subpackages và explicitly-annotated. Nếu giá trị cấu hình không phải tên của strategy dựng sẵn, Spring Modulith diễn giải nó như tên lớp triển khai tùy chỉnh.

Không khai báo tên class ngắn như BusinessModuleDetectionStrategy nếu class nằm trong package architecture. Tên đầy đủ giúp Spring Modulith tìm đúng lớp khi khởi tạo.

## Bước 4: Viết test kiểm tra kết quả phát hiện

Tạo bài test trong package gốc để mô hình được tạo từ đúng lớp ứng dụng:

~~~text
src/test/java
└── com/acme/fulfillment
    └── ModularityDetectionTests.java
~~~

Nội dung test:

~~~java
package com.acme.fulfillment;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityDetectionTests {

    @Test
    void detectsOnlyBusinessModules() {
        var modules = ApplicationModules.of(FulfillmentApplication.class);

        assertThat(modules.getModuleByName("orders")).isPresent();
        assertThat(modules.getModuleByName("stock")).isPresent();
        assertThat(modules.getModuleByName("delivery")).isPresent();

        assertThat(modules.getModuleByName("configuration")).isEmpty();
        assertThat(modules.getModuleByName("bootstrap")).isEmpty();
        assertThat(modules.getModuleByName("observability")).isEmpty();

        modules.verify();
    }
}
~~~

Các assertion kiểm tra cả hai phía:

- Module nghiệp vụ phải được phát hiện.
- Package kỹ thuật phải không xuất hiện như application module.

Cuối cùng, verify() kiểm tra các quy tắc kiến trúc trên mô hình đã tạo. Nếu strategy chọn sai package, test sẽ giúp phát hiện ngay tại bước xác nhận danh sách module.

Có thể in mô hình ra console để quan sát thêm:

~~~java
var modules = ApplicationModules.of(FulfillmentApplication.class);
modules.forEach(System.out::println);
~~~

Kết quả cần có các module orders, stock và delivery. Không nên chỉ dựa vào số lượng module; hãy kiểm tra tên và base package để phát hiện trường hợp package sai bị chọn thay cho package mong muốn.

## Bước 5: Mở rộng quy tắc khi thêm module mới

Giả sử nhóm thêm module returns. Nếu vẫn dùng danh sách tường minh, cần cập nhật strategy:

~~~java
private static final Set<String> MODULE_NAMES =
    Set.of("orders", "stock", "delivery", "returns");
~~~

Sau đó cập nhật test để xác nhận returns được phát hiện.

Cách dùng danh sách tường minh phù hợp khi số module ít và nhóm muốn kiểm soát chính xác module nào được đưa vào mô hình. Đổi lại, mỗi lần thêm module phải cập nhật strategy và test tương ứng.

Nếu tổ chức có quy ước package ổn định, có thể dùng quy tắc đặt tên. Ví dụ, tất cả module nghiệp vụ nằm trong package con trực tiếp có tên bắt đầu bằng business:

~~~java
return rootPackage.getDirectSubPackages().stream()
    .filter(candidate ->
        candidate.getLocalName().startsWith("business")
    );
~~~

Với cách này, nhóm có thể đặt package như businessOrders hoặc businessInventory. Tuy nhiên, tên package cần được thống nhất trong toàn bộ dự án. Một quy tắc quá rộng có thể đưa nhầm package kỹ thuật vào mô hình.

Không dùng naming convention chỉ để giảm vài dòng cấu hình nếu danh sách module có thể thay đổi không kiểm soát. Hãy chọn quy tắc dễ giải thích, có test xác nhận và phù hợp với cách tổ chức mã nguồn.

## Bước 6: So sánh với strategy dựng sẵn

Trước khi duy trì custom strategy, hãy xác nhận các strategy có sẵn không đáp ứng được yêu cầu.

| Strategy | Cách chọn module | Trường hợp sử dụng |
|---|---|---|
| direct-subpackages | Chọn tất cả package con trực tiếp | Package gốc chỉ chứa các module |
| explicitly-annotated | Chỉ chọn package được đánh dấu @ApplicationModule hoặc jMolecules @Module | Nhóm muốn khai báo module ngay tại package |
| Custom strategy | Chọn package bằng naming convention hoặc logic riêng | Cấu trúc dự án cần quy tắc đặc thù |

Nếu package gốc chỉ có orders, stock và delivery, strategy mặc định thường đã đủ. Nếu nhóm muốn chọn module theo annotation, explicitly-annotated có thể phù hợp hơn. Chỉ duy trì custom strategy khi có quy tắc riêng mà hai lựa chọn dựng sẵn không biểu đạt được.

Custom strategy cũng có thể override detectNamedInterfaces() để tùy chỉnh việc phát hiện named interface bên trong từng module. Đó là một trách nhiệm khác với việc chọn module base package. Trong bài thực hành này, ta chỉ triển khai getModuleBasePackages() để giữ phạm vi rõ ràng.

## Bước 7: Chuyển strategy sang production khi runtime cần

Nếu custom strategy chỉ phục vụ ApplicationModules.verify() và Documenter trong test, đặt lớp và cấu hình trong test sources là đủ.

Nếu ứng dụng dùng Spring Modulith runtime components, ví dụ ApplicationModuleInitializer, actuator hoặc observability, runtime cũng cần nạp cùng strategy. Khi đó:

- Chuyển BusinessModuleDetectionStrategy.java sang src/main/java.
- Chuyển thuộc tính spring.modulith.detection-strategy sang src/main/resources/application.properties.
- Đảm bảo spring-modulith-core có trên compile classpath.
- Nếu sử dụng runtime auto-configuration, khai báo spring-modulith-runtime theo cấu hình runtime phù hợp.

Cấu trúc sau khi chuyển:

~~~text
src
├── main
│   ├── java
│   │   └── com/acme/fulfillment
│   │       ├── FulfillmentApplication.java
│   │       └── architecture
│   │           └── BusinessModuleDetectionStrategy.java
│   └── resources
│       └── application.properties
└── test
    └── java
        └── com/acme/fulfillment
            └── ModularityDetectionTests.java
~~~

Không duy trì hai bản strategy riêng cho test và production. Nếu hai môi trường chọn module theo hai quy tắc khác nhau, test có thể xác minh một kiến trúc trong khi ứng dụng chạy với kiến trúc khác.

## Bước 8: Xử lý các lỗi thường gặp

**Không tìm thấy class strategy.** Kiểm tra tên đầy đủ trong spring.modulith.detection-strategy, package khai báo trong file Java và source set chứa lớp. Nếu cấu hình nằm trong test resources, class phải nằm trong test source set.

**Không có module nào được phát hiện.** Kiểm tra package gốc của FulfillmentApplication, tên local của package và danh sách MODULE_NAMES. Đảm bảo lớp ứng dụng nằm ở package cha của orders, stock và delivery.

**Package kỹ thuật bị phát hiện thành module.** Kiểm tra điều kiện filter. Nếu strategy trả về tất cả direct sub-packages hoặc dùng prefix quá rộng, configuration và bootstrap có thể lọt vào danh sách.

**Module mới không xuất hiện.** Với allowlist tên tường minh, thêm tên module vào MODULE_NAMES và cập nhật assertion. Với naming convention, xác nhận package mới thực sự tuân thủ quy ước.

**Module con bị tạo thành module riêng.** Chỉ trả về package con trực tiếp từ rootPackage. Không duyệt đệ quy toàn bộ cây nếu không có chủ đích tạo nested application modules.

**Test qua nhưng runtime dùng danh sách khác.** Kiểm tra vị trí lớp strategy và file application.properties. Nếu runtime components cần strategy, cả hai phải nằm trong production sources.

**Verification báo lỗi dependency sau khi module được phát hiện.** Đây có thể là lỗi kiến trúc thật, không phải lỗi detection. Đọc module nguồn, module đích và package được tham chiếu; sửa dependency hoặc công bố API đúng cách.

## Bài thực hành hoàn chỉnh

Hãy thực hiện lần lượt trên một ứng dụng Spring Boot thử nghiệm:

1. Tạo package gốc com.acme.fulfillment và lớp FulfillmentApplication.
2. Tạo ba package nghiệp vụ orders, stock và delivery.
3. Tạo thêm các package kỹ thuật configuration, bootstrap và observability.
4. Viết BusinessModuleDetectionStrategy chọn đúng ba package nghiệp vụ.
5. Đăng ký strategy bằng spring.modulith.detection-strategy trong test resources.
6. Viết ModularityDetectionTests để xác nhận ba module được phát hiện và ba package kỹ thuật bị bỏ qua.
7. Gọi ApplicationModules.verify() để kiểm tra cấu trúc.
8. Thêm module returns và cập nhật strategy cùng assertion.
9. Nếu ứng dụng dùng runtime components, chuyển strategy và cấu hình sang production sources.
10. In danh sách module để kiểm tra kết quả cuối cùng.

Kết quả mong đợi:

| Tên module | Base package |
|---|---|
| orders | com.acme.fulfillment.orders |
| stock | com.acme.fulfillment.stock |
| delivery | com.acme.fulfillment.delivery |
| returns | com.acme.fulfillment.returns |

Các package configuration, bootstrap và observability không xuất hiện trong danh sách module. Các package con như orders.internal vẫn thuộc orders.

## Tiêu chí hoàn tất

Bài thực hành hoàn tất khi bạn có thể:

- Triển khai ApplicationModuleDetectionStrategy với phương thức getModuleBasePackages().
- Dùng JavaPackage để duyệt package con và chọn module theo quy tắc rõ ràng.
- Đăng ký strategy bằng spring.modulith.detection-strategy.
- Viết test xác nhận module được chọn và package bị loại.
- Chạy ApplicationModules.verify() trên mô hình kết quả.
- Giải thích khi nào strategy cần nằm trong test sources và khi nào phải chuyển sang production sources.

Tài liệu tham khảo:

- [Spring Modulith — Customizing Module Detection](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [ApplicationModuleDetectionStrategy API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleDetectionStrategy.html)
- [JavaPackage API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/JavaPackage.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
