# Tách các annotation khi cần kiểm soát rõ từng cơ chế

Trong Spring Boot, lớp khởi động thường chỉ cần một annotation `@SpringBootApplication`. Annotation này rất tiện lợi vì kết hợp ba cơ chế quan trọng: xác định lớp cấu hình của ứng dụng, bật auto-configuration và tìm các Spring component. Tuy nhiên, khi ứng dụng cần kiểm soát phạm vi quét, lựa chọn cấu hình tự động hoặc tổ chức cấu hình thành những phần độc lập, ta có thể **tách ba cơ chế ra thành các annotation riêng**.

Điều cần hiểu trước khi tách là: những annotation này **không làm cùng một việc**. Nếu tách không đúng, ứng dụng có thể vẫn biên dịch nhưng không tạo được controller/service, thiếu repository, mất hạ tầng web hoặc thay đổi kết quả của các bài kiểm thử Spring Boot.

## 1. Bản chất của `@SpringBootApplication`

Một ứng dụng điển hình:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`@SpringBootApplication` là **composed annotation**: nó kết hợp những annotation khác để giảm mã cấu hình thường lặp lại.

| Annotation được kết hợp | Trách nhiệm chính | Hiện tượng nếu thiếu |
|---|---|---|
| `@SpringBootConfiguration` | Xác định lớp là nguồn cấu hình của một ứng dụng Boot; dựa trên `@Configuration` | Boot test có thể không tự tìm được cấu hình ứng dụng; lớp không còn mang marker cấu hình Boot tương đương |
| `@EnableAutoConfiguration` | Chọn các auto-configuration dựa trên dependency, bean, property và loại ứng dụng | Hạ tầng web, dữ liệu, security hoặc tích hợp khác sẽ không còn được Boot tự tạo theo cơ chế này |
| `@ComponentScan` | Tìm các class mang stereotype như `@Component`, `@Service`, `@Controller`, `@Configuration` trong các package phù hợp | Các component do lập trình viên tạo có thể không được đăng ký thành bean |

Có thể hình dung:

~~~text
                   @SpringBootApplication
                            │
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
@SpringBootConfiguration  @EnableAutoConfiguration  @ComponentScan
          │                 │                 │
  Nguồn cấu hình      Chọn cấu hình        Tìm bean ứng dụng
  cho ứng dụng        tự động theo         theo Java package
  Spring Boot         các điều kiện
          └─────────────────┼─────────────────┘
                            ▼
                      ApplicationContext
                       (các bean được tạo)
~~~

Ba annotation ở trên thường phối hợp, nhưng **mỗi cái giải quyết một câu hỏi khác nhau**: cấu hình ứng dụng bắt đầu từ đâu, Boot cần tự cung cấp hạ tầng gì, và lớp nào trong mã nguồn ứng dụng cần được đăng ký.

### Cấu hình Boot không đồng nghĩa với phương thức Java `main`

Phương thức `main(String[] args)` chỉ là điểm vào của chương trình Java. Chính class được truyền cho `SpringApplication.run(...)`, cùng những annotation cấu hình của class đó, quyết định nguồn cấu hình Spring. Nếu đặt phương thức `main` trong một launcher khác nhưng vẫn truyền `CatalogApplication.class`, phạm vi quét mặc định gắn với class cấu hình được sử dụng chứ không phải tên của launcher.

## 2. Cách tách gần tương đương mà vẫn giữ hành vi mặc định

Có thể chuyển lớp trên sang cách viết tường minh dưới đây, với package và dependency giữ nguyên:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurationExcludeFilter;
import org.springframework.boot.context.TypeExcludeFilter;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan(
    basePackageClasses = CatalogApplication.class,
    excludeFilters = {
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = TypeExcludeFilter.class
        ),
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = AutoConfigurationExcludeFilter.class
        )
    }
)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Ở đây:

1. `@SpringBootConfiguration` giữ vai trò lớp cấu hình của ứng dụng Boot.
2. `@EnableAutoConfiguration` giữ cơ chế tự động cấu hình.
3. `@ComponentScan(basePackageClasses = CatalogApplication.class)` quét `com.example.catalog` và các package con, tương ứng với phạm vi mặc định khi lớp `@SpringBootApplication` nằm tại `com.example.catalog`.
4. Hai `excludeFilters` giữ lại các filter mà `@SpringBootApplication` áp dụng cho component scan. Chúng có ý nghĩa với các cơ chế loại trừ của Boot, đặc biệt ở một số **test slice**, và tránh nhận auto-configuration class như component thường.

Trong ứng dụng đơn giản, nhiều ví dụ trực tuyến chỉ viết:

~~~java
@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
public class CatalogApplication {
}
~~~

Cách viết rút gọn này thể hiện đúng **ba chức năng chính**, nhưng **không sao chép đầy đủ cấu hình component scan ngầm của `@SpringBootApplication`**: nó thiếu hai filter nêu trên. Khi cần thay thế thực tế mà vẫn giữ các hành vi mặc định của Boot, hãy chủ động xử lý sự khác biệt đó. Các thuộc tính tùy chỉnh khác của `@SpringBootApplication`, nếu đã được ứng dụng sử dụng, cũng cần được chuyển sang annotation tương ứng.

Đây là lý do việc tách annotation nên xuất phát từ **một yêu cầu cấu hình cụ thể**, thay vì tách chỉ để có nhiều dòng code hơn.

## 3. Hiểu riêng `@SpringBootConfiguration`: nguồn cấu hình ứng dụng

`@SpringBootConfiguration` kế thừa ý nghĩa từ `@Configuration`: nó đánh dấu một class có thể khai báo các bean qua `@Bean` và chứa thông tin cấu hình Spring. Đồng thời, nó là dấu hiệu giúp một số công cụ của Spring Boot nhận biết **cấu hình gốc**.

Ví dụ:

~~~java
package com.example.catalog;

import java.time.Clock;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.context.annotation.Bean;

@SpringBootConfiguration
public class CatalogConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
~~~

Nếu class này được cung cấp cho `SpringApplication.run(...)`, bean `Clock` có thể được đăng ký. Nhưng **chỉ có `@SpringBootConfiguration` không tự bật component scan hoặc auto-configuration**. Nó không tự tạo HTTP server, `DispatcherServlet` hay quét `@Service` ở mọi package.

Trong tình huống bình thường, dùng `@SpringBootConfiguration` cho lớp cấu hình gốc của ứng dụng, còn các lớp cấu hình bổ sung dùng `@Configuration`. Nếu có nhiều lớp gốc `@SpringBootConfiguration` không cần thiết trong những package mà test tự dò tìm, cơ chế bootstrap kiểm thử có thể trở nên khó đoán.

### `@SpringBootConfiguration` và `@Configuration` có giống hệt nhau?

Chúng có cùng nền tảng cấu hình Spring, nhưng Boot có thể tìm kiếm marker `@SpringBootConfiguration` khi khởi tạo kiểm thử. Thay thế bằng `@Configuration` thuần túy không phải lúc nào cũng giữ nguyên hành vi **tự phát hiện lớp cấu hình gốc** của `@SpringBootTest` hoặc các test slice.

Vì vậy, nếu mục tiêu chỉ là tách `@SpringBootApplication` ra thành ba annotation, dùng `@SpringBootConfiguration` trên lớp ứng dụng là cách rõ ràng nhất.

## 4. Hiểu riêng `@EnableAutoConfiguration`: chọn hạ tầng có điều kiện

`@EnableAutoConfiguration` giúp Spring Boot nhập các **auto-configuration candidate** do Boot và thư viện tích hợp cung cấp. Trong Spring Boot 3.x, các class auto-configuration của thư viện được liệt kê trong tài nguyên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Boot đánh giá các điều kiện trước khi đăng ký cấu hình hoặc bean tương ứng. Một số annotation điều kiện thường gặp:

| Điều kiện | Câu hỏi được kiểm tra |
|---|---|
| `@ConditionalOnClass` | Có class/thư viện cần thiết trên classpath không? |
| `@ConditionalOnMissingClass` | Có thiếu class nhất định không? |
| `@ConditionalOnBean` | Context đã có bean cần thiết chưa? |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp để Boot tạo mặc định? |
| `@ConditionalOnProperty` | Property có thỏa giá trị yêu cầu không? |
| `@ConditionalOnWebApplication` | Ứng dụng có đang chạy web stack phù hợp không? |

Ví dụ, khi classpath có các thư viện Spring MVC và Servlet phù hợp, Boot có thể cấu hình hạ tầng web MVC; khi thêm Spring Data JPA và có điều kiện kết nối dữ liệu, Boot có thể tạo `DataSource` cùng hạ tầng JPA. Nếu ứng dụng đã cung cấp bean mà auto-configuration khai báo `@ConditionalOnMissingBean`, cấu hình mặc định thường sẽ **nhường chỗ**.

Sự có mặt của `@EnableAutoConfiguration` không đảm bảo tất cả những bean đó đều xuất hiện. **Classpath mở ra khả năng; điều kiện thực tế quyết định kết quả.**

### Loại trừ một auto-configuration cụ thể

Khi muốn giữ phần lớn auto-configuration nhưng ngăn Boot tự cấu hình một thành phần, có thể dùng thuộc tính `exclude`:

~~~java
package com.example.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.context.annotation.ComponentScan;

@SpringBootConfiguration
@EnableAutoConfiguration(
    exclude = DataSourceAutoConfiguration.class
)
@ComponentScan(basePackageClasses = BatchApplication.class)
public class BatchApplication {
    public static void main(String[] args) {
        SpringApplication.run(BatchApplication.class, args);
    }
}
~~~

Đây là đoạn minh họa cho **ý định loại trừ**: không yêu cầu Boot tạo `DataSource` theo `DataSourceAutoConfiguration`. Nếu dùng trong ứng dụng thật, cần áp dụng hai filter component scan như ví dụ đầy đủ ở mục 2, và bảo đảm những bean khác không còn phụ thuộc vào `DataSource` bị loại trừ.

Tương đương về ý tưởng, khi còn dùng annotation gộp, có thể viết:

~~~java
@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class BatchApplication {
}
~~~

Điều này cho thấy **không nhất thiết phải tách annotation chỉ để exclude**: `@SpringBootApplication` đã cung cấp thuộc tính `exclude` và `excludeName`. Ta chỉ nên tách khi cần kiểm soát riêng từng cơ chế hoặc tổ chức cấu hình rõ hơn.

### Tắt một auto-configuration khác với tắt toàn bộ auto-configuration

Thiếu `@EnableAutoConfiguration` làm mất cơ chế Boot tự chọn hạ tầng trên diện rộng; loại trừ một cấu hình cụ thể chỉ tác động tới phần được chỉ định, dù các phụ thuộc liên quan có thể tạo ảnh hưởng dây chuyền. Một ứng dụng có thể vẫn khởi động nhưng thiếu server, JSON converter, transaction manager hoặc các bean mặc định, tùy cấu hình còn lại.

Không nên dùng cách bỏ hẳn `@EnableAutoConfiguration` chỉ để né lỗi cấu hình database. Hãy xác định auto-configuration nào đang được chọn và vì sao nó thất bại.

## 5. Hiểu riêng `@ComponentScan`: phạm vi tìm bean ứng dụng

Giả sử ứng dụng có cấu trúc:

~~~text
src/main/java/
└── com/example/catalog/
    ├── CatalogApplication.java
    ├── api/
    │   └── ProductController.java
    ├── service/
    │   └── ProductService.java
    ├── config/
    │   └── CatalogConfig.java
    └── persistence/
        ├── ProductEntity.java
        └── ProductRepository.java
~~~

Khi `CatalogApplication` đặt ở `com.example.catalog` và `@ComponentScan` không chỉ định base package khác, Spring thường quét từ package này xuống các package con.

Các class như sau có thể được phát hiện:

~~~java
package com.example.catalog.service;

import org.springframework.stereotype.Service;

@Service
public class ProductService {
    public String label(long id) {
        return "product-" + id;
    }
}
~~~

~~~java
package com.example.catalog.api;

import com.example.catalog.service.ProductService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProductController {
    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping("/products/{id}/label")
    public String getLabel(@PathVariable long id) {
        return service.label(id);
    }
}
~~~

Controller và service cần được đăng ký thành bean; việc định tuyến HTTP còn cần hạ tầng web phù hợp. Trong ứng dụng dùng `spring-boot-starter-web`, **component scan** giúp tìm `ProductController` và **auto-configuration** giúp thiết lập Spring MVC/`DispatcherServlet` để endpoint có thể được gọi.

### Package cha, package anh em và phạm vi quét

~~~text
com.example
├── catalog
│   ├── CatalogApplication   ← @ComponentScan mặc định từ đây
│   ├── api                  ← trong phạm vi
│   └── service              ← trong phạm vi
├── shared                  ← ngoài phạm vi
└── accounting              ← ngoài phạm vi
~~~

Nếu `ProductService` được chuyển tới `com.example.shared`, nó sẽ không còn tự động nằm trong phạm vi scan của `com.example.catalog`. Khi controller yêu cầu service đó, việc tạo bean có thể thất bại:

~~~text
Parameter 0 of constructor in ProductController
required a bean of type ProductService that could not be found.
~~~

Để sửa, có thể mở rộng phạm vi scan **có chủ đích**, chuyển lớp về package gốc của ứng dụng, hoặc nhập cấu hình cụ thể.

## 6. Tách annotation để quét nhiều package có chủ đích

Đây là một trường hợp thực tế khi việc tách ba cơ chế giúp mục đích trở nên dễ đọc.

Giả sử:

~~~text
com.example.catalog
├── CatalogApplication
└── api
    └── ProductController

com.example.shared.audit
├── AuditPackageMarker
└── AuditService        ← @Service
~~~

Vì `com.example.shared.audit` không phải package con của `com.example.catalog`, ta muốn component scan bao trùm **hai package xác định** mà không quét toàn bộ `com.example`.

~~~java
// File: com/example/shared/audit/AuditPackageMarker.java
package com.example.shared.audit;

public interface AuditPackageMarker {
}
~~~

~~~java
// File: com/example/catalog/CatalogApplication.java
package com.example.catalog;

import com.example.shared.audit.AuditPackageMarker;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurationExcludeFilter;
import org.springframework.boot.context.TypeExcludeFilter;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;

@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan(
    basePackageClasses = {
        CatalogApplication.class,
        AuditPackageMarker.class
    },
    excludeFilters = {
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = TypeExcludeFilter.class
        ),
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = AutoConfigurationExcludeFilter.class
        )
    }
)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

`basePackageClasses` lấy **package chứa mỗi class** làm gốc quét. Marker interface không cần mang annotation `@Component`; vai trò của nó là đại diện một package, giúp mã cấu hình an toàn hơn khi refactor so với chuỗi package tự viết.

Cũng có thể khai báo chuỗi:

~~~java
@ComponentScan(basePackages = {
    "com.example.catalog",
    "com.example.shared.audit"
})
~~~

Nhưng nếu thay toàn bộ `@ComponentScan` theo cách trên, cần giữ các filter mặc định của Boot khi cần tính tương đương với `@SpringBootApplication`. Khi ứng dụng chỉ cần đổi phạm vi quét, cách viết **ngắn hơn** vẫn có sẵn:

~~~java
@SpringBootApplication(
    scanBasePackageClasses = {
        CatalogApplication.class,
        AuditPackageMarker.class
    }
)
public class CatalogApplication {
}
~~~

Vì vậy, lợi ích của cách tách ở đây là thể hiện rõ ba phần cấu hình độc lập, không phải có thêm một khả năng scan mà annotation gộp không thể làm được.

### Nếu chỉ cần một lớp cấu hình từ package khác

Thay vì quét cả package lớn, có thể dùng `@Import` để đăng ký một cấu hình cụ thể:

~~~java
package com.example.catalog;

import com.example.shared.config.AuditConfiguration;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(AuditConfiguration.class)
public class CatalogApplication {
}
~~~

`@Import` là một lựa chọn khác khi tích hợp module dùng chung. Nếu `AuditConfiguration` chứa các phương thức `@Bean`, những bean đó có thể được đăng ký mà không cần quét toàn bộ package chia sẻ. Không phải lúc nào cũng cần tách annotation để tổ chức cấu hình.

## 7. Tách annotation để phân biệt rõ component scanning và entity/repository scanning

Một điểm dễ nhầm là cho rằng mở rộng `@ComponentScan` sẽ tự động giải quyết **mọi** loại class. Trong thực tế:

| Loại thành phần | Cơ chế phát hiện/đăng ký điển hình |
|---|---|
| `@Service`, `@RestController`, `@Component`, `@Configuration` | Spring component scanning |
| `@Bean` từ lớp cấu hình | Xử lý nguồn `@Configuration` được đăng ký/nhập |
| JPA `@Entity` | Entity scanning/JPA persistence unit |
| Interface kế thừa `JpaRepository` | Spring Data repository scanning |
| Class đánh dấu `@ConfigurationProperties` | Configuration properties registration/scanning |
| Auto-configuration class của thư viện | Cơ chế chọn auto-configuration của Boot |

`@EnableAutoConfiguration` thường thiết lập **auto-configuration packages** theo package của lớp được gắn annotation. Những package này được nhiều auto-configuration, trong đó có JPA và Spring Data, dùng làm gốc mặc định. Chúng **không tự đổi theo** thuộc tính `basePackages` của `@ComponentScan`.

Xét cấu trúc:

~~~text
com.example.catalog
└── CatalogApplication

com.example.persistence
├── entity
│   └── ProductEntity             ← @Entity
└── repository
    └── ProductJpaRepository      ← extends JpaRepository
~~~

Nếu chỉ quét thêm `com.example.persistence` bằng `@ComponentScan`, JPA entity và repository interface chưa chắc đã được phát hiện theo mong đợi. Khi cần tách phạm vi dữ liệu một cách tường minh, có thể viết:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.domain.EntityScan;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.context.annotation.ComponentScan;

@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan(basePackageClasses = CatalogApplication.class)
@EntityScan(basePackages = "com.example.persistence.entity")
@EnableJpaRepositories(
    basePackages = "com.example.persistence.repository"
)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

Đây là bản rút gọn nhằm làm nổi bật **ba phạm vi khác nhau**. Nếu dùng làm cấu hình chính thay thế `@SpringBootApplication` trong dự án thật, thêm hai `excludeFilters` của component scan như mục 2 để giữ hành vi của Boot.

Với cấu hình trên:

- `@ComponentScan` phụ trách component của ứng dụng ở `com.example.catalog`.
- `@EntityScan` phụ trách entity ở `com.example.persistence.entity`.
- `@EnableJpaRepositories` phụ trách interface repository ở `com.example.persistence.repository`.
- `@EnableAutoConfiguration` tiếp tục cung cấp các auto-configuration tương ứng **nếu classpath và điều kiện phù hợp**.

Với Spring Data MongoDB, R2DBC hoặc module lưu trữ khác, dùng cơ chế repository tương ứng; `@EnableJpaRepositories` chỉ dành cho **Spring Data JPA**. Cấu hình trên cũng giả định ứng dụng đã có starter JPA, driver và thiết lập database phù hợp.

Đối với `@ConfigurationProperties`, cân nhắc `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. Mở rộng component scan **không tự thay thế** các quy tắc đăng ký configuration properties.

## 8. Có thể tách từng nhóm cấu hình thành class riêng không?

Có. Thay vì đặt mọi annotation trên lớp ứng dụng, ta có thể **nhập một lớp cấu hình chuyên trách**. Cần lưu ý package mặc định của `@ComponentScan` là package của class **được gắn `@ComponentScan`**, không tự động chuyển về package của lớp có phương thức `main`.

Ví dụ:

~~~java
// File: com/example/catalog/CatalogApplication.java
package com.example.catalog;

import com.example.catalog.bootstrap.CatalogComponents;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Import;

@SpringBootConfiguration
@EnableAutoConfiguration
@Import(CatalogComponents.class)
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

~~~java
// File: com/example/catalog/bootstrap/CatalogComponents.java
package com.example.catalog.bootstrap;

import com.example.catalog.CatalogApplication;
import org.springframework.boot.autoconfigure.AutoConfigurationExcludeFilter;
import org.springframework.boot.context.TypeExcludeFilter;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.FilterType;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ComponentScan(
    basePackageClasses = CatalogApplication.class,
    excludeFilters = {
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = TypeExcludeFilter.class
        ),
        @ComponentScan.Filter(
            type = FilterType.CUSTOM,
            classes = AutoConfigurationExcludeFilter.class
        )
    }
)
public class CatalogComponents {
}
~~~

`CatalogComponents` được `@Import` trực tiếp, và `@ComponentScan` trong class này đã được chỉ rõ `basePackageClasses` để bao trùm `com.example.catalog`. Nếu bỏ đối số đó, scan mặc định sẽ bắt đầu tại **`com.example.catalog.bootstrap`**, khiến nhiều component trong `api` hoặc `service` không được tìm thấy.

Ở ví dụ này, `@SpringBootConfiguration` vẫn nằm trên lớp cấu hình gốc mà Boot dùng để khởi động/test; `@EnableAutoConfiguration` vẫn được bật. Cách chia này phù hợp khi một nhóm cấu hình có phạm vi đủ phức tạp để cần tên riêng, hoặc khi cần chia ownership giữa module bootstrap và module tính năng.

Đối với ứng dụng nhỏ, một lớp `@SpringBootApplication` thông thường vẫn dễ đọc và dễ bảo trì hơn.

## 9. Những tác dụng phụ quan trọng khi tách annotation

### 9.1. Quên `@ComponentScan`

~~~java
@SpringBootConfiguration
@EnableAutoConfiguration
public class CatalogApplication {
}
~~~

Ứng dụng có thể vẫn nhận auto-configuration và khởi động được, nhưng những class như `ProductService` hay `ProductController` **không được tìm theo component scan thông thường**. Nếu chúng không được đăng ký qua `@Import`, `@Bean` hoặc cơ chế khác, injection có thể thất bại hoặc endpoint không tồn tại.

### 9.2. Quên `@EnableAutoConfiguration`

~~~java
@SpringBootConfiguration
@ComponentScan
public class CatalogApplication {
}
~~~

Các component của ứng dụng vẫn có thể được phát hiện, nhưng những cấu hình mà Boot thường tự tạo sẽ không xuất hiện từ annotation này: chẳng hạn embedded HTTP server, MVC infrastructure hoặc datasource/transaction infrastructure, tùy thư viện và các cấu hình còn lại. Bản thân `@ComponentScan` không thay thế được auto-configuration.

### 9.3. Thay `@SpringBootConfiguration` bằng `@Configuration` mà quên tác động tới test

Ứng dụng có thể chạy nếu truyền đúng class cấu hình cho `SpringApplication.run(...)`, nhưng một số test Spring Boot dùng cơ chế tìm cấu hình gốc theo package có thể không tìm được `@SpringBootConfiguration` mong muốn. Có thể chỉ rõ:

~~~java
@SpringBootTest(classes = CatalogApplication.class)
class CatalogContextTest {
}
~~~

Tuy nhiên, với lớp ứng dụng Boot, giữ marker `@SpringBootConfiguration` sẽ giúp phản ánh đúng vai trò bootstrap và thuận tiện cho test.

### 9.4. Không giữ hai filter của `@ComponentScan`

Trong `@SpringBootApplication`, component scan có sẵn hai filter:

~~~java
@ComponentScan.Filter(
    type = FilterType.CUSTOM,
    classes = TypeExcludeFilter.class
)
@ComponentScan.Filter(
    type = FilterType.CUSTOM,
    classes = AutoConfigurationExcludeFilter.class
)
~~~

`TypeExcludeFilter` đóng vai trò trong việc loại trừ những class không thuộc phạm vi của một số kiểu test slice, còn `AutoConfigurationExcludeFilter` tránh để auto-configuration bị nhận nhầm qua quá trình quét component. Nếu tự tạo `@ComponentScan` mà quên filter, kết quả scan hoặc context test có thể khác kỳ vọng, đặc biệt với `@WebMvcTest`, `@DataJpaTest` hoặc các slice có bộ lọc riêng.

### 9.5. Nhầm `@ComponentScan` với `@EnableAutoConfiguration`

Thêm một package vào component scan không đồng nghĩa mọi bean dữ liệu/security/web mặc định sẽ xuất hiện. Ngược lại, thêm starter vào classpath có thể làm Boot bật auto-configuration mới mà không cần mở rộng component scan. Hai cơ chế có **nguồn cấu hình và điều kiện khác nhau**.

### 9.6. Dùng `@EnableWebMvc` như một thay thế cho `@EnableAutoConfiguration`

Trong ứng dụng Spring Boot MVC, thêm `@EnableWebMvc` thường có ý nghĩa **tự quản lý cấu hình Spring MVC**, khiến auto-configuration MVC của Boot nhường chỗ ở những phần tương ứng. Đây là quyết định khác hẳn việc tách `@SpringBootApplication` thành các annotation nền tảng. Nếu chỉ cần chỉnh formatter, interceptor hoặc resource handling, nên cân nhắc `WebMvcConfigurer` trước khi quyết định kiểm soát toàn bộ MVC.

## 10. Khi nào nên giữ annotation gộp, khi nào nên tách?

| Nhu cầu | Hướng xử lý thường hợp lý |
|---|---|
| Ứng dụng Boot thông thường, các component nằm dưới một package gốc | Giữ `@SpringBootApplication` |
| Chỉ cần thêm package quét component | Dùng `scanBasePackages` hoặc `scanBasePackageClasses` của `@SpringBootApplication` |
| Chỉ cần loại trừ một auto-configuration | Dùng `exclude`/`excludeName` của `@SpringBootApplication` hoặc `spring.autoconfigure.exclude` |
| Muốn cấu hình riêng rõ ràng giữa nguồn cấu hình, auto-configuration và scan | Tách thành `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@ComponentScan` |
| Cần tập hợp nhiều package scan, filter riêng hoặc chia cấu hình theo module | Tách hợp lý, chỉ định base package và giữ các filter của Boot nếu cần tương đương |
| Có JPA entity/repository nằm ngoài package gốc | Dùng `@EntityScan`/`@EnableJpaRepositories` đúng mục đích |
| Chỉ cần dùng một cấu hình có sẵn ở package khác | Cân nhắc `@Import` |
| Cần thay đổi vài chi tiết Spring MVC | Ưu tiên cấu hình MVC chuyên biệt, tránh tự động tắt auto-configuration không liên quan |

Điểm cần lưu ý: **tách không đồng nghĩa với tùy chỉnh thành công**. Điều quan trọng là hiểu mỗi annotation đang bật hoặc giới hạn điều gì, và giữ nguyên những cơ chế mặc định mà ứng dụng vẫn cần.

## 11. Cách quan sát kết quả sau khi thay đổi cách khai báo

Khi tách annotation trong một dự án, có thể dựa vào một số dấu hiệu chạy thực tế để hiểu các cơ chế:

| Hiện tượng | Mối liên hệ cần xem |
|---|---|
| Khởi động lỗi vì thiếu `@Service` hoặc `@Controller` | Package quét của `@ComponentScan`, annotation stereotype, `@Import`/`@Bean` |
| Endpoint trả HTTP 404 dù controller đã viết | Controller có được scan, web framework có cấu hình handler mapping, mapping URL có đúng? |
| Không có embedded web server | `@EnableAutoConfiguration` còn hoạt động không, starter web có tồn tại và ứng dụng đang chọn web type nào? |
| Báo thiếu `DataSource` hoặc JPA infrastructure | Dependency JDBC/JPA, properties, auto-configuration condition và các exclude |
| JPA báo `Not a managed type` | Phạm vi `@EntityScan`/persistence unit, annotation entity |
| Spring Data repository không được đăng ký | Phạm vi repository scan, starter Spring Data phù hợp |
| `@WebMvcTest` nạp những bean lạ hoặc context khác dự kiến | Kiểm tra component-scan filters khi thay `@SpringBootApplication` |
| `@SpringBootTest` không tìm thấy cấu hình gốc | Marker `@SpringBootConfiguration` và vị trí package của test |

Để điều tra **auto-configuration**, Spring Boot có Conditions Evaluation Report khi chạy với tùy chọn:

~~~text
--debug
~~~

hoặc:

~~~properties
debug=true
~~~

Báo cáo có thể cho biết auto-configuration nào **matched**, **did not match** hoặc đã được **excluded**. Chúng giúp giải thích điều kiện kích hoạt, nhưng không nên coi báo cáo là danh sách đầy đủ những class mà component scan đã khảo sát.

Để xem bean đã được đăng ký thực sự, có thể quan sát `ApplicationContext` hoặc dùng Actuator endpoint `beans` khi đã bật và bảo vệ endpoint phù hợp. Với controller, hãy kiểm tra endpoint mapping của ứng dụng; với repository/entity, kiểm tra cấu hình dữ liệu tương ứng. Việc nhìn đúng cơ chế tiết kiệm thời gian hơn việc liên tục mở rộng `basePackages`.

## 12. Một ví dụ kết hợp: tổ chức ứng dụng theo chức năng

Giả sử một hệ thống quản lý đơn hàng có hai nhóm chức năng:

~~~text
com.example.orders
├── OrdersApplication
├── sales
│   ├── SalesController
│   └── SalesService
└── shipping
    ├── ShippingController
    └── ShippingService
~~~

Nếu đây là toàn bộ phạm vi ứng dụng, cách khai báo tốt nhất thường chỉ là:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Giả sử sau này ứng dụng tích hợp thêm một module công ty có package `com.example.shared.events`, đồng thời muốn nhập một bean cấu hình chuyên dụng. Khi đó có thể **chỉ mở rộng phần liên quan**:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "com.example.orders",
        "com.example.shared.events"
    }
)
@Import(EventPublisherConfiguration.class)
public class OrdersApplication {
}
~~~

Nếu nhóm phát triển cần quản lý từng cơ chế ở các vị trí tách biệt, có thể chuyển sang bộ ba `@SpringBootConfiguration`, `@EnableAutoConfiguration`, `@ComponentScan` như ví dụ đầy đủ ở mục 2 hoặc 6, giữ nguyên chức năng Boot cần thiết và chỉ định rõ phạm vi scan.

**Nguyên tắc cốt lõi:** `@SpringBootApplication` cung cấp một cấu hình gộp có chủ đích. Tách nó ra là cách làm lộ rõ những quyết định về **nguồn cấu hình**, **auto-configuration** và **component scanning**. Khi cần kiểm soát sâu, hãy điều chỉnh đúng annotation phụ trách vấn đề đang gặp, duy trì các filter/điều kiện cần thiết và phân biệt component với entity, repository hoặc configuration properties. Nhờ vậy, mã khởi động vừa rõ ý nghĩa vừa tránh những thay đổi ngầm trong Spring application context.
