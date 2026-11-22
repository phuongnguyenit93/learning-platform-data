# Vai trò của @AutoConfigurationPackage và AutoConfigurationPackages

## 1. Vấn đề: auto-configuration cần biết package gốc nào?

Khi khởi động một ứng dụng Spring Boot, một số tính năng được tự cấu hình cần một **điểm bắt đầu để tìm các kiểu ứng dụng**. Ví dụ, cấu hình JPA thường cần biết package mặc định để tìm các lớp `@Entity`; cấu hình Spring Data có thể dùng package mặc định để xác định vị trí repository. Những package này được gọi là **auto-configuration packages**.

Hai API trong package `org.springframework.boot.autoconfigure` đảm nhiệm việc ghi nhớ và cung cấp thông tin đó:

- **`@AutoConfigurationPackage`:** annotation yêu cầu Spring Boot **đăng ký một hoặc nhiều tên package làm package cơ sở cho các tính năng tự cấu hình**.
- **`AutoConfigurationPackages`:** lớp tiện ích/hạ tầng dùng để **lưu, tra cứu hoặc đăng ký thêm danh sách package** trong `BeanFactory`/`BeanDefinitionRegistry` của ứng dụng.

Quan trọng: đăng ký một package **không đồng nghĩa với quét ngay tất cả class trong package, tạo bean, bật mọi starter hay bổ sung auto-configuration class vào danh sách ứng viên**. Nó cung cấp thông tin vị trí để *những tính năng có nhu cầu* tra cứu và sử dụng theo quy tắc riêng.

~~~text
@SpringBootApplication
   |
   +-- @EnableAutoConfiguration
          |
          +-- @AutoConfigurationPackage
          |      |
          |      +-- @Import(AutoConfigurationPackages.Registrar)
          |             |
          |             +-- Lưu package mặc định trong BeanFactory
          |                   (thường là package của lớp ứng dụng)
          |
          +-- @Import(AutoConfigurationImportSelector)
                 |
                 +-- Chọn các lớp auto-configuration ứng viên
                     từ AutoConfiguration.imports
                 +-- Áp dụng exclusions và điều kiện liên quan

Một tính năng tự cấu hình cần package gốc
   -> AutoConfigurationPackages.get(beanFactory)
   -> tên package -> tìm entity/repository/... tùy tính năng
~~~

Trong sơ đồ, **hai nhánh dưới `@EnableAutoConfiguration` có chức năng khác nhau**: một nhánh đăng ký thông tin package; nhánh kia chọn cấu hình tự động. Sự tách biệt này giúp giải thích vì sao chỉnh package mặc định không tương đương chỉnh danh sách auto-configuration.

## 2. Vì sao `@SpringBootApplication` tự có package mặc định?

Trong Spring Boot 3.3, các annotation có quan hệ:

~~~java
@SpringBootApplication
// tương đương nhóm ý nghĩa chính:
// @SpringBootConfiguration
// @EnableAutoConfiguration
// @ComponentScan
~~~

Bản thân `@EnableAutoConfiguration` được chú thích bằng `@AutoConfigurationPackage` và `@Import(AutoConfigurationImportSelector.class)`. Vì vậy, khi class chính được Spring xử lý, Boot có thể đăng ký package chứa class kích hoạt tự cấu hình, đồng thời tiến hành cơ chế chọn cấu hình tự động.

Ví dụ:

~~~text
com.example.shop
├── ShopApplication.java   <- @SpringBootApplication
├── domain
│   └── Product.java       <- @Entity
├── repository
│   └── ProductRepository.java
└── service
    └── ProductService.java
~~~

Với `ShopApplication` trong package `com.example.shop`, package tự cấu hình mặc định thường là `com.example.shop`. Một tính năng tìm entity/repository dựa trên quy ước mặc định có thể xem đây là điểm gốc để tìm các kiểu thích hợp ở những package con.

**Dấu hiệu cần nhớ:** package của class kích hoạt `@EnableAutoConfiguration` (thường là class `@SpringBootApplication`) có ý nghĩa đặc biệt. Đây là lý do tài liệu Spring Boot khuyến nghị đặt class khởi động trong package gốc phía trên các package ứng dụng.

Không suy ra rằng chỉ cần có tên package này thì JPA hoạt động: vẫn cần dependency, cấu hình dữ liệu, bean cần thiết và các điều kiện của cấu hình JPA. `@AutoConfigurationPackage` chỉ góp phần xác định *nơi có thể tìm*, chứ không quyết định *tính năng nào chắc chắn hoạt động*.

## 3. `@AutoConfigurationPackage` làm gì ở mức kỹ thuật?

Annotation có cấu trúc khái niệm tương đương:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@Import(AutoConfigurationPackages.Registrar.class)
public @interface AutoConfigurationPackage {
    String[] basePackages() default {};
    Class<?>[] basePackageClasses() default {};
}
~~~

Đây là **trích dẫn cấu trúc rút gọn phục vụ giải thích**, không phải một lớp bạn cần tự định nghĩa. `@Import` đưa một registrar nội bộ của Boot vào quy trình xử lý cấu hình. Registrar nhận metadata annotation và đăng ký danh sách tên package vào hạ tầng `AutoConfigurationPackages`.

Quy tắc chọn tên package:

1. Nếu không khai báo `basePackages` và `basePackageClasses`, package của **class được chú thích** được lấy làm tên package.
2. Nếu muốn chỉ rõ package, dùng `basePackages = "com.example.domain"`.
3. Nếu muốn an toàn hơn khi đổi tên package lúc refactor, dùng `basePackageClasses = DomainMarker.class`. Boot lấy **package chứa class được chỉ định**, không lấy class đó làm bean.

Ví dụ minh họa:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurationPackage;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@AutoConfigurationPackage(basePackages = "com.example.inventory.domain")
public class InventoryPackageConfiguration {
}
~~~

Đây là một **đoạn cấu hình** cần được scan/import/đăng ký để có hiệu lực; chỉ tạo file class mà Spring không xử lý thì annotation không chạy. Nó đăng ký tên package `com.example.inventory.domain` vào tập package tự cấu hình của context.

### `basePackages` và `basePackageClasses`

| Thuộc tính | Cách dùng | Đặc điểm |
| --- | --- | --- |
| `basePackages` | `@AutoConfigurationPackage(basePackages = "com.example.domain")` | Dùng chuỗi; cần cập nhật khi đổi tên package |
| `basePackageClasses` | `@AutoConfigurationPackage(basePackageClasses = DomainMarker.class)` | Dùng class/interface để xác định package theo kiểu, thân thiện với refactor |
| Không truyền thuộc tính | `@AutoConfigurationPackage` | Dùng package của class được chú thích |

Marker có thể là một interface rỗng:

~~~java
package com.example.domain;

// Chỉ dùng để tham chiếu package, không cần tạo bean.
public interface DomainMarker {
}
~~~

Đừng hiểu `basePackageClasses = DomainMarker.class` như lệnh đăng ký `DomainMarker` thành một bean hoặc chỉ quét duy nhất class này. API dùng vị trí package của marker làm dữ liệu.

## 4. `AutoConfigurationPackages`: nơi tra cứu danh sách package

`AutoConfigurationPackages` là một lớp tiện ích Spring Boot cung cấp các phương thức tĩnh quan trọng:

~~~java
public static boolean has(BeanFactory beanFactory);
public static List<String> get(BeanFactory beanFactory);
public static void register(
    BeanDefinitionRegistry registry, String... packageNames
);
~~~

*Đoạn trên là các chữ ký API để học, không phải một lớp Java tự biên dịch độc lập.*

- `has(beanFactory)`: kiểm tra trong bean factory có các auto-configuration base packages khả dụng hay không.
- `get(beanFactory)`: lấy danh sách tên package mà Boot đã đăng ký. **Có thể ném `IllegalStateException`** nếu cơ chế package chưa được thiết lập; gọi `has` trước trong mã không chắc ngữ cảnh là hợp lý.
- `register(registry, packageNames...)`: đăng ký các package bằng mã. Các lần đăng ký tiếp theo có thể bổ sung tên package. API này hữu ích cho những cơ chế hạ tầng, nhưng với code ứng dụng nên ưu tiên annotation và quy ước thay vì tự thao tác registry.

Ví dụ dùng trong một context Spring Boot đã khởi động:

~~~java
import java.util.List;
import org.springframework.boot.autoconfigure.AutoConfigurationPackages;
import org.springframework.context.ConfigurableApplicationContext;

// context là ConfigurableApplicationContext đã được khởi động.
boolean available = AutoConfigurationPackages.has(context.getBeanFactory());
if (available) {
    List<String> roots =
        AutoConfigurationPackages.get(context.getBeanFactory());
    System.out.println(roots);
}
~~~

Đây là **đoạn mã cần biến `context`**, không phải một file Java chạy riêng. `getBeanFactory()` trả về `ConfigurableListableBeanFactory`, phù hợp với tham số `BeanFactory` của hai method trên.

### Cái gì được lưu?

Boot đăng ký thông tin package trong container, và các auto-configuration quan tâm có thể tra cứu ở giai đoạn phù hợp. Đây là **danh sách tên package**, không phải danh sách class đã tìm được, cũng không phải danh sách `BeanDefinition` tương ứng với mọi class nằm trong package.

Cũng vì vậy, việc `get(...)` trả về `com.example.shop` **không chứng minh** có bao nhiêu entity, repository hay service ở package đó. Phải kiểm tra từng scanner/registry tương ứng để biết kết quả thực tế.

## 5. Phân biệt ba phạm vi thường bị nhầm

Spring Boot có nhiều cơ chế liên quan package nhưng mục đích khác nhau.

| Cơ chế | Câu hỏi được trả lời | Ai sử dụng | Có tự tạo bean từ mọi class không? |
| --- | --- | --- | --- |
| `@ComponentScan` / `scanBasePackages` | Quét package nào để tìm các component phù hợp? | Spring component scanner | Chỉ với class phù hợp điều kiện quét, không phải mọi class |
| `@AutoConfigurationPackage` / `AutoConfigurationPackages` | Package gốc mặc định cho những tính năng auto-config cần tra cứu là gì? | Tính năng Boot như một số scanner entity/repository | Không |
| `AutoConfiguration.imports` | Những class auto-configuration nào có thể được xem xét? | Cơ chế chọn auto-configuration của Boot | Không; các điều kiện vẫn quyết định cấu hình/bean |

**Ví dụ dễ nhầm:**

~~~java
@SpringBootApplication(scanBasePackages = "com.example.controllers")
public class ShopApplication {
}
~~~

Giả sử `ShopApplication` nằm trong `com.example.boot`. `scanBasePackages` ở trên **chỉ thay phạm vi `@ComponentScan`**, không tự chuyển package mặc định của `AutoConfigurationPackages` sang `com.example.controllers`. Các scanner cho entity/repository không được điều khiển bởi tham số này theo cùng cách.

Ngược lại, nếu đăng ký thêm `com.example.entities` qua `@AutoConfigurationPackage`, Spring **không tự mở rộng `@ComponentScan`** để tìm các `@Service` hay `@Controller` trong `com.example.entities`.

### `@EntityScan` và `@EnableJpaRepositories` khác ở đâu?

- `@EntityScan` định nghĩa phạm vi quét các kiểu persistence như JPA entities cho những cơ chế được hỗ trợ. Khi đã khai báo phạm vi tường minh, nó có thể thay quy ước mặc định về package tìm entity.
- `@EnableJpaRepositories` có thể khai báo package quét repository một cách tường minh, theo cơ chế Spring Data JPA.
- `@ComponentScan` quét component Spring như `@Component`/`@Service`/`@Controller`, không phải thay thế trực tiếp cho hai cơ chế trên.
- `@AutoConfigurationPackage` đăng ký dữ liệu package **mặc định** để một số tính năng tự cấu hình sử dụng; nó không bảo đảm ghi đè các lựa chọn tường minh và không phải “lệnh quét chung cho mọi thứ”.

Vì vậy, khi gặp trường hợp repository được phát hiện nhưng entity không được quản lý, hãy kiểm tra riêng **phạm vi quét repository** và **phạm vi entity**, thay vì chỉ điều chỉnh `scanBasePackages`.

## 6. Ví dụ hoàn chỉnh: bổ sung package mà không mở rộng component scan

Thí nghiệm dùng **Java 17+**, **Spring Boot 3.3.13**, **Maven 3.9+**. Không cần cơ sở dữ liệu. Mục tiêu là nhìn trực tiếp danh sách package trong `AutoConfigurationPackages` và chứng minh nó độc lập với component scanning.

### Sơ đồ project

~~~text
package-demo/
├── pom.xml
└── src/main/java/
    └── com/example/
        ├── launch/
        │   └── DemoApplication.java
        ├── config/
        │   └── ExtraPackageConfiguration.java
        ├── domain/
        │   ├── DomainMarker.java
        │   └── HiddenProbe.java
        └── component/
            └── ScannedProbe.java
~~~

Class khởi động nằm trong `com.example.launch`. Ta cố tình đặt hai `@Component` trong các package khác nhau: một cái thuộc vùng component scan, một cái chỉ nằm trong package được bổ sung vào danh sách auto-configuration.

### 6.1. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>package-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter` đủ để xây dựng `ApplicationContext` và quan sát bean đơn giản. Demo không dùng JPA; việc thêm package ở đây chỉ minh họa metadata, không bắt buộc thêm entity.

### 6.2. `src/main/java/com/example/domain/DomainMarker.java`

~~~java
package com.example.domain;

public interface DomainMarker {
}
~~~

Marker này xác định package `com.example.domain` bằng kiểu Java, giúp IDE hỗ trợ refactor.

### 6.3. `src/main/java/com/example/domain/HiddenProbe.java`

~~~java
package com.example.domain;

import org.springframework.stereotype.Component;

@Component
public class HiddenProbe {
}
~~~

`HiddenProbe` được đánh dấu `@Component` nhưng sẽ không được component scan từ `com.example.component` phát hiện. Nó không phải bean chỉ vì package `com.example.domain` được đưa vào `AutoConfigurationPackages`.

### 6.4. `src/main/java/com/example/component/ScannedProbe.java`

~~~java
package com.example.component;

import org.springframework.stereotype.Component;

@Component
public class ScannedProbe {
}
~~~

Đây là component trong vùng được chọn để quét bằng `scanBasePackages`. Nếu scanner hoạt động, tên bean mặc định sẽ là `scannedProbe`.

### 6.5. `src/main/java/com/example/config/ExtraPackageConfiguration.java`

~~~java
package com.example.config;

import com.example.domain.DomainMarker;
import org.springframework.boot.autoconfigure.AutoConfigurationPackage;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@AutoConfigurationPackage(basePackageClasses = DomainMarker.class)
public class ExtraPackageConfiguration {
}
~~~

Spring chỉ xử lý cấu hình này khi nó được đưa vào context. Nó đăng ký thêm tên package `com.example.domain` thông qua registrar của `@AutoConfigurationPackage`. **Nó không khai báo `@ComponentScan`** và cũng không đăng ký `HiddenProbe` thành bean.

### 6.6. `src/main/java/com/example/launch/DemoApplication.java`

~~~java
package com.example.launch;

import com.example.config.ExtraPackageConfiguration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.AutoConfigurationPackages;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Import;

@SpringBootApplication(scanBasePackages = "com.example.component")
@Import(ExtraPackageConfiguration.class)
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {

            boolean hasRoots =
                AutoConfigurationPackages.has(context.getBeanFactory());

            List<String> roots = new ArrayList<>(
                AutoConfigurationPackages.get(context.getBeanFactory())
            );
            Collections.sort(roots);

            System.out.println("hasAutoPackages=" + hasRoots);
            System.out.println("autoPackages=" + roots);
            System.out.println("scannedProbe=" +
                context.containsBean("scannedProbe"));
            System.out.println("hiddenProbe=" +
                context.containsBean("hiddenProbe"));
        }
    }
}
~~~

Hai lựa chọn quan trọng trên class này:

1. `@SpringBootApplication(scanBasePackages = "com.example.component")` chỉ rõ package cho **component scan**. Điều này không đổi package mặc định của cơ chế auto-configuration, vốn gắn với `com.example.launch`.
2. `@Import(ExtraPackageConfiguration.class)` đưa thêm cấu hình có `@AutoConfigurationPackage(basePackageClasses = DomainMarker.class)` vào quá trình xử lý. Do đó danh sách package tự cấu hình có thêm `com.example.domain`.

Dùng `Collections.sort(roots)` để kết quả hiển thị ổn định, vì thứ tự đăng ký package không phải điểm đang cần kiểm tra.

### 6.7. Chạy và đối chiếu output

Từ thư mục `package-demo`:

~~~bash
java -version
mvn -version
mvn -q spring-boot:run
~~~

Bốn dòng do `System.out.println` của ví dụ in ra:

~~~text
hasAutoPackages=true
autoPackages=[com.example.domain, com.example.launch]
scannedProbe=true
hiddenProbe=false
~~~

Spring Boot có thể in thêm banner và log. Bốn dòng trên thể hiện:

- `com.example.launch` là package mặc định, xác định qua lớp `DemoApplication` kích hoạt `@EnableAutoConfiguration`.
- `com.example.domain` được bổ sung bởi `ExtraPackageConfiguration`.
- Bean `scannedProbe` có mặt vì `com.example.component` được component scan.
- Bean `hiddenProbe` **không có** vì chỉ đăng ký package auto-configuration không khiến component scanner quét package đó.

**Quan sát này kiểm tra trực tiếp API và bean trong context**, không cần đoán dựa trên tên annotation.

## 7. Ba thay đổi nhỏ để tự kiểm nghiệm cơ chế

### Thử 1: bỏ `@Import(ExtraPackageConfiguration.class)`

Trong `DemoApplication`, bỏ annotation `@Import(ExtraPackageConfiguration.class)`, giữ nguyên các file khác. Vì `com.example.config` không nằm trong vùng component scan, cấu hình bổ sung không được nạp. Kết quả dự kiến:

~~~text
hasAutoPackages=true
autoPackages=[com.example.launch]
scannedProbe=true
hiddenProbe=false
~~~

Giải thích: `@EnableAutoConfiguration` vẫn hiện diện qua `@SpringBootApplication` nên vẫn có package mặc định. Phần thêm `com.example.domain` biến mất vì registrar tương ứng không được chạy.

### Thử 2: chuyển component scan sang package domain

Khôi phục `@Import` rồi đổi trên `DemoApplication`:

~~~java
@SpringBootApplication(scanBasePackages = "com.example.domain")
@Import(ExtraPackageConfiguration.class)
public class DemoApplication {
    // Giữ nguyên phương thức main ở mục 6.6.
}
~~~

Đây là **đoạn thay thế cho khai báo class**, không phải một chương trình riêng. Khi chạy lại, dự kiến:

~~~text
hasAutoPackages=true
autoPackages=[com.example.domain, com.example.launch]
scannedProbe=false
hiddenProbe=true
~~~

Danh sách auto-configuration packages **giữ nguyên**; chỉ vùng quét component đổi. Trường hợp này chứng minh hai cơ chế độc lập ở mức cấu hình mặc định.

### Thử 3: bỏ annotation `@AutoConfigurationPackage` ở cấu hình bổ sung

Khôi phục component scan như ban đầu; giữ `@Import(ExtraPackageConfiguration.class)`, nhưng bỏ `@AutoConfigurationPackage(basePackageClasses = DomainMarker.class)` khỏi lớp cấu hình bổ sung. Lớp cấu hình vẫn được import; chỉ mất tác dụng đăng ký package mới. Kết quả trở lại:

~~~text
hasAutoPackages=true
autoPackages=[com.example.launch]
scannedProbe=true
hiddenProbe=false
~~~

Có thể tiếp tục bổ sung một bean bằng `@Bean` trong `ExtraPackageConfiguration`: bean đó vẫn được đăng ký dù không còn `@AutoConfigurationPackage`. Điều này tách biệt rõ **đưa một cấu hình vào context** với **đăng ký package cho các scanner có nhu cầu**.

## 8. Khi JPA hoặc Spring Data thực sự dùng các package này

Trong thí nghiệm trên, `AutoConfigurationPackages.get(...)` trả về hai chuỗi package nhưng chưa có dependency persistence, nên chưa có chuyện tìm entity/repository. Trong ứng dụng có JPA/Spring Data, một số auto-configuration dùng những tên package làm nguồn mặc định cho việc tìm các kiểu nhất định.

Giả sử tổ chức dự án:

~~~text
com.acme.launch
  └── MainApplication.java
com.acme.catalog.domain
  └── Product.java          (@Entity)
com.acme.catalog.repo
  └── ProductRepository.java (Spring Data repository interface)
~~~

Nếu class chính nằm ở `com.acme.launch`, các package `com.acme.catalog.domain` và `com.acme.catalog.repo` nằm **ngoài** đường package mặc định. Có vài lựa chọn tùy mục tiêu:

**Cách A: đặt class khởi động ở package cha chung.** Ví dụ chuyển ứng dụng vào `com.acme`, nếu cấu trúc và phạm vi quét phù hợp. Đây là cách theo quy ước mà Spring Boot khuyến khích.

**Cách B: đăng ký thêm package tự cấu hình.** Dùng một cấu hình được import có `@AutoConfigurationPackage(basePackageClasses = CatalogMarker.class)`, trong đó marker nằm ở package gốc `com.acme.catalog`. Tính năng dựa trên `AutoConfigurationPackages` có thể thấy thêm đường dẫn mặc định ấy.

**Cách C: cấu hình rõ từng scanner.** Với JPA, sử dụng `@EntityScan(basePackageClasses = Product.class)`; với Spring Data JPA, khi cần điều khiển phạm vi repository, sử dụng `@EnableJpaRepositories(basePackageClasses = ProductRepository.class)`. Hai annotation này nhắm vào hai cơ chế khác nhau. Khi đã khai báo các phạm vi cụ thể, hãy kiểm tra các quy tắc của từng scanner thay vì giả định mọi thứ đều kế thừa `AutoConfigurationPackages`.

Lưu ý: `@AutoConfigurationPackage` không được thiết kế để thay toàn bộ các annotation scanning tường minh. Với hệ thống nhiều module có topology phức tạp, lựa chọn nào phù hợp còn phụ thuộc cơ chế persistence được dùng và mức độ chủ động bạn muốn kiểm soát.

### Vì sao repository và entity có thể khác nhau?

Spring Data repository scanner tìm **các interface repository phù hợp**; JPA entity scanner tìm **kiểu entity được quản lý**. Việc cả hai có thể bắt đầu từ package gốc tương tự không có nghĩa chúng là một scanner duy nhất. Nếu repository bean tồn tại nhưng xuất hiện lỗi “Not a managed type”, cần kiểm tra riêng tập entity được quản lý. Nếu entity tồn tại nhưng không thấy repository bean, kiểm tra cơ chế bật/repository scanning và điều kiện auto-configuration.

Không khẳng định entity nào được quản lý chỉ bằng `AutoConfigurationPackages.get(...)`. Kết quả phải xác nhận qua JPA metamodel/`EntityManagerFactory` nếu đang dùng JPA.

## 9. Những điều annotation này KHÔNG làm

1. **Không bổ sung ứng viên vào `AutoConfiguration.imports`.** Danh sách auto-configuration class của Boot 3.x đến từ tài nguyên `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; package base không phải cơ chế liệt kê những class này.
2. **Không bật/tắt từng auto-configuration.** Việc chọn cấu hình phụ thuộc exclusions, classpath và điều kiện như `@ConditionalOnClass`, `@ConditionalOnProperty` hoặc `@ConditionalOnMissingBean`. Thay danh sách package tự cấu hình không trực tiếp thay các điều kiện đó.
3. **Không thực hiện component scan.** Một class `@Service` trong package được đăng ký vẫn có thể không thành bean nếu không nằm trong vùng scan/import/đăng ký tương ứng.
4. **Không tự động tạo `@Entity` thành bean Spring bình thường.** Entity do JPA quản lý theo cơ chế persistence; không đồng nhất entity với bean `@Component`.
5. **Không thay đổi toàn bộ search path của mọi thư viện.** Một thư viện tự quyết định cách tìm class của nó; chỉ những cơ chế được thiết kế đọc `AutoConfigurationPackages` mới dùng giá trị này.
6. **Không tự bảo đảm các dependency runtime.** Đăng ký tên package không tạo database, datasource, driver hay transaction manager.

### Hai nhầm lẫn trong tên gọi

- `@AutoConfigurationPackage` có chữ “AutoConfiguration” nhưng nó làm việc với **base package của ứng dụng** được những tính năng tự cấu hình sử dụng. Nó không dùng để khai báo một lớp `@AutoConfiguration` mới.
- `AutoConfigurationPackages` có chữ “Packages” nhưng nó không phải danh sách các package chứa JAR auto-configuration của Spring Boot. Tên package trong danh sách là các gốc tìm kiếm của **ứng dụng**, do cấu hình ứng dụng đăng ký.

## 10. Chẩn đoán khi “không tìm thấy entity/repository/service”

Một cách kiểm tra có hệ thống:

| Bước | Câu hỏi | Bằng chứng cần thu thập |
| --- | --- | --- |
| 1 | Lớp khởi động và `@EnableAutoConfiguration` nằm trong package nào? | Đường package thực tế của class chính |
| 2 | Danh sách auto-config base packages hiện tại là gì? | `AutoConfigurationPackages.has/get` trên bean factory |
| 3 | Có ai đăng ký thêm package bằng `@AutoConfigurationPackage` không? | Class cấu hình được scan/import và marker được tham chiếu |
| 4 | Cơ chế đang gặp lỗi là component scan, JPA entity scan hay repository scan? | Loại annotation và thông báo lỗi |
| 5 | Có `@EntityScan`/`@EnableJpaRepositories` hoặc cấu hình tường minh tương tự không? | Annotation và cấu hình thực tế của từng scanner |
| 6 | Auto-configuration liên quan có chạy và thỏa điều kiện không? | Condition Evaluation Report bằng `--debug` hoặc Actuator conditions |
| 7 | Đối tượng/định nghĩa cần tìm có thực sự tồn tại? | `ApplicationContext`, repository registry hoặc JPA metamodel |

Ví dụ xác minh phần package an toàn:

~~~java
var factory = context.getBeanFactory();
if (AutoConfigurationPackages.has(factory)) {
    System.out.println(
        AutoConfigurationPackages.get(factory)
    );
} else {
    System.out.println("Chưa có auto-configuration packages");
}
~~~

*Đoạn trên cần có biến `context` và import tương ứng.* Kiểm tra trước bằng `has` giúp tránh gọi `get` trong một context chưa đăng ký package.

### Đừng sửa sai phạm vi

Nếu thiếu một `@Service`, bước đầu là kiểm tra `@ComponentScan`, `@Import`, `@Bean` và điều kiện bean. Thêm `@AutoConfigurationPackage` có thể không giải quyết gì.

Nếu thiếu `@Entity`, kiểm tra JPA đang được bật, dependency persistence, package entity mặc định, `@EntityScan` và thông báo từ metamodel. Mở rộng `scanBasePackages` chỉ giải quyết quét component, không phải thay thế cho `@EntityScan`.

Nếu thiếu repository, kiểm tra dependency Spring Data, cơ chế repository scanning và package chứa interface. Tránh kết luận chỉ từ việc class interface tồn tại trên classpath.

## 11. Góc nhìn thiết kế: khi nào nên khai báo thêm package?

**Ưu tiên quy ước khi cấu trúc đơn giản.** Đặt class `@SpringBootApplication` tại package cha chung giúp cả component scan và các auto-configuration mặc định có phạm vi hợp lý. Không nên dùng `@AutoConfigurationPackage` để che một cấu trúc package bất hợp lý khi có thể sửa kiến trúc gói rõ ràng hơn.

**Ưu tiên marker class thay vì chuỗi khi cần cấu hình mở rộng.** Một `CatalogMarker` đặt trong package gốc giúp refactor an toàn; không cần tạo instance hay bean cho marker.

**Dùng thêm package khi thực sự có consumer.** Nếu ứng dụng không dùng một tính năng đọc `AutoConfigurationPackages`, việc thêm package chỉ thay đổi metadata. Khi dùng nhiều thư viện persistence, hãy kiểm tra tài liệu từng thư viện vì không phải mọi scanner đều sử dụng chung danh sách mặc định.

**Giữ phạm vi hẹp theo nhu cầu.** Không đăng ký package quá rộng như `com` hoặc package mặc định (không khai báo package). Những phạm vi quá rộng có thể làm các scanner đi qua nhiều class không liên quan, tăng chi phí khởi động hoặc gây phát hiện ngoài ý muốn tùy scanner.

**Đừng gọi `AutoConfigurationPackages.register(...)` trong mã nghiệp vụ.** API này phục vụ đăng ký hạ tầng; cách phổ biến cho ứng dụng là annotation hoặc tổ chức package hợp lý. Nếu cần can thiệp chương trình, phải hiểu rõ thời điểm đăng ký `BeanDefinition` trước khi consumer đọc danh sách.

## 12. Tự kiểm tra kiến thức

1. Trong sơ đồ `@EnableAutoConfiguration`, registrar của `@AutoConfigurationPackage` và `AutoConfigurationImportSelector` khác nhau ở kết quả nào?
2. `@SpringBootApplication(scanBasePackages = "com.example.feature")` đặt trên class ở `com.example.launch`: nếu không có cấu hình bổ sung, `AutoConfigurationPackages.get(...)` thường trả package nào? Vì sao?
3. Nếu đăng ký thêm `com.example.domain` qua `@AutoConfigurationPackage`, tại sao một `@Component` trong package đó vẫn có thể vắng mặt trong context?
4. `basePackageClasses = CatalogMarker.class` ghi nhận package hay instance của marker? Khi đổi tên package, cách này có ưu điểm gì?
5. Khi `AutoConfigurationPackages.has(beanFactory)` trả về `false`, có nên gọi `get(beanFactory)` không? API ghi nhận hành vi nào nếu chưa được thiết lập?
6. Repository được phát hiện nhưng entity không được quản lý: bạn cần kiểm tra những scanner và dependency nào trước?
7. Trong ví dụ ở mục 6, dự đoán output khi (a) bỏ `@Import`; (b) đổi `scanBasePackages`; (c) bỏ `@AutoConfigurationPackage`. Giải thích mỗi kết quả bằng một cơ chế cụ thể.

**Tiêu chí hoàn thành:** bạn phân biệt được metadata package với component scan và import candidates; đọc được package gốc từ `AutoConfigurationPackages`; biết khi nào nên dùng `@AutoConfigurationPackage` và khi nào cần `@EntityScan`/repository scanning; giải thích được kết quả thí nghiệm bằng quan hệ giữa annotation, registrar và context.

## 13. Tài liệu đối chiếu

- [Spring Boot 3.3.13 — `@EnableAutoConfiguration` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html)
- [Spring Boot 3.3.13 — `@AutoConfigurationPackage` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationPackage.html)
- [Spring Boot 3.3.13 — `AutoConfigurationPackages` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationPackages.html)
- [Spring Boot 3.3.13 — `@SpringBootApplication` Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/SpringBootApplication.html)
- [Spring Boot — Auto-configuration packages](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html#using.auto-configuration.auto-configuration-packages)
