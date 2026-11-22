# Thiết kế annotation bật tính năng theo mẫu `@Enable` trong Spring Framework

## 1. Từ nhiều cấu hình rời rạc đến một annotation công khai

Trong Spring, một tính năng thường không chỉ có một object. Ví dụ audit cần một `AuditSink`, một service sử dụng sink, có thể thêm validator, advisor hoặc bean infrastructure. Nếu yêu cầu người dùng tự nhập từng cấu hình:

```java
@Configuration
@Import({
    AuditSinkConfig.class,
    AuditServiceConfig.class,
    AuditInfrastructureConfig.class
})
class AppConfig {
}
```

thì nơi khởi động phải biết quá nhiều chi tiết triển khai. Khi tính năng mở rộng, danh sách class có thể thay đổi và ứng dụng sử dụng thư viện phải sửa code chỉ để bổ sung một config nội bộ.

Một API gọn hơn:

```java
@Configuration
@EnableAudit(level = AuditLevel.DETAILED)
class AppConfig {
}
```

Trong thiết kế này, **`@EnableAudit` là annotation tự định nghĩa**, không có sẵn trong Spring Framework. Bên trong nó sử dụng `@Import` để dẫn Spring đến một class cấu hình, `ImportSelector` hoặc `ImportBeanDefinitionRegistrar`. Ứng dụng chỉ công bố **ý định bật tính năng**, còn thư viện giữ quyền tổ chức các beans và implementation.

Đó là mẫu thiết kế `@Enable...`: một **annotation ở type level** trở thành entry point khai báo cho một capability của ứng dụng.

Nhiều annotation thực tế của Spring đi theo hướng này: `@EnableCaching`, `@EnableAsync`, `@EnableScheduling`, `@EnableTransactionManagement`. Chúng không đồng nhất về implementation, nhưng cùng tư tưởng: kích hoạt cơ chế cấu hình hạ tầng qua annotation trên class cấu hình.

Mục tiêu bài học:

1. Thiết kế metadata của custom `@Enable...`: `@Target`, `@Retention`, `@Documented`, `@Import` và attributes.
2. Chọn đúng extension point: import class cố định, `ImportSelector`, `DeferredImportSelector` hay `ImportBeanDefinitionRegistrar`.
3. Bảo đảm tính năng được bật/tắt **đồng bộ cả producer và consumer beans**.
4. Hiểu lúc nào selector đọc annotation attributes, môi trường hoặc điều kiện.
5. Phân biệt bật khả năng framework với việc tạo mọi dependency hạ tầng cần thiết.
6. Thiết kế public API ổn định, tương thích refactor và không quét quá rộng.
7. Chạy demo Java 17+ với Spring 6.2 cho `@EnableAudit` ở các chế độ BASIC, DETAILED, OFF, đối chiếu đầu ra thực tế dự kiến.
8. Kiểm thử và chẩn đoán lỗi thiếu bean, trùng bean, proxy và lifecycle.

## 2. Một annotation `@Enable...` hoạt động như thế nào?

Về mặt Java, annotation chỉ là **metadata**; tự gắn `@EnableAudit` lên class không có nghĩa JVM gọi code tạo bean. Spring phải nhìn thấy configuration class đó, xử lý metadata và có một cơ chế chuyển metadata thành bean definitions.

Ví dụ mô hình phổ biến:

```text
AppConfig được đăng ký vào ApplicationContext
                    |
                    v
         @EnableAudit(level=DETAILED)
                    |
                    v
     Annotation được meta-annotated @Import
                    |
                    v
           AuditConfigurationSelector
                    |
          Đọc metadata/attributes
                    |
                    v
  Chọn DetailedAuditConfig + AuditServiceConfig
                    |
                    v
    Spring xử lý imported configuration classes
                    |
                    v
  Đăng ký bean definitions AuditSink, AuditService
                    |
                    v
      BeanFactory resolve dependency & lifecycle
                    |
                    v
        Các managed beans sẵn sàng sử dụng
```

**Điểm cốt lõi:** annotation công khai **khai báo yêu cầu**, extension point nội bộ **chọn/đăng ký definitions**, BeanFactory **tạo và quản lý objects**. Không gộp ba giai đoạn vào một method tự gọi `new` rồi cho rằng container đã quản lý object.

### 2.1. Điều kiện đầu tiên: class dùng `@Enable...` phải được xử lý

```java
@EnableAudit
class AppConfig {
}
```

Nếu `AppConfig` không được đưa vào Spring context bằng đăng ký trực tiếp, component scan, một `@Import` khác hay cơ chế hợp lệ tương ứng, annotation sẽ **không được xử lý**. Trong demo chạy được, chúng ta sử dụng:

```java
new AnnotationConfigApplicationContext(BasicAppConfig.class)
```

Đây là snippet minh họa từ ví dụ ở mục 8. Bean definitions được tạo trong context đó, không phải trên toàn JVM.

### 2.2. Bật tính năng khác với bật component scanning

`@EnableAudit` không bắt buộc phải có `@ComponentScan`. Khi một annotation khai báo `@Import(AuditSelector.class)`, Spring chỉ nhập các class mà selector chỉ ra, và những registrations phát sinh từ các class đó.

Nếu imported configuration tự chứa `@ComponentScan`, nó có thể quét một package và đăng ký thêm nhiều bean; nhưng đó là do **cấu hình đã nhập**, không phải vì mọi annotation `@Enable...` tự nhiên quét package của thư viện.

### 2.3. Một khả năng có thể gồm nhiều beans

“Bật audit” thường cần cả **writer** và **service sử dụng writer**. Nếu chỉ đăng ký service mà không cung cấp writer khi dependency bắt buộc, context có thể thất bại. Nếu tắt writer nhưng vẫn để service được tạo eager và đòi writer, tắt tính năng cũng có thể khiến context lỗi.

Do đó, hãy nghĩ theo **module bean graph** chứ không chỉ theo một class: selector phải chọn một tập configuration classes nhất quán. Khi disabled, hoặc không đăng ký consumer, hoặc consumer dùng optional dependency/fallback có chủ đích.

## 3. Cấu tạo tối thiểu của custom `@Enable` annotation

Một annotation thường có dạng:

```java
package com.acme.audit;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.context.annotation.Import;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(AuditModuleConfig.class)
public @interface EnableAudit {
}
```

Đây là **file minh họa `EnableAudit.java`**, cần thêm class `AuditModuleConfig` hợp lệ để biên dịch. Trong phiên bản tối giản này, `@Import` đưa vào một configuration class cố định; không cần viết selector hoặc registrar.

Ý nghĩa từng metadata:

| Annotation | Vai trò |
| --- | --- |
| `@Target(ElementType.TYPE)` | Chỉ cho phép gắn annotation vào class/interface/annotation type theo khả năng Java |
| `@Retention(RetentionPolicy.RUNTIME)` | Giữ annotation ở runtime để framework có thể truy xuất metadata |
| `@Documented` | Cho phép Javadoc của type sử dụng annotation trình bày annotation ấy |
| `@Import(AuditModuleConfig.class)` | Chỉ Spring đến class cấu hình hoặc extension point cần xử lý |
| `public @interface EnableAudit` | Định nghĩa một Java annotation được application có thể dùng |

`@Retention(RUNTIME)` là lựa chọn chuẩn cho annotation cấu hình dễ đọc qua reflection. Spring cũng có metadata readers dựa trên class files, nhưng không nên vì vậy dùng một retention mơ hồ cho public configuration annotation.

### 3.1. Phiên bản không có tham số

Nếu luôn chỉ có một cách triển khai audit, sử dụng cấu hình tĩnh:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(AuditModuleConfig.class)
public @interface EnableAudit {
}
```

Và application:

```java
@Configuration(proxyBeanMethods = false)
@EnableAudit
class ShopConfiguration {
}
```

Đây là hai trích đoạn minh họa riêng. Ưu điểm: ít mã, dễ debug, imported config định nghĩa rõ các beans. Nếu logic phụ thuộc profiles/properties nhưng vẫn chỉ là điều kiện có/không, có thể đặt `@Conditional` trên configuration hoặc bean factory methods mà không cần một selector.

### 3.2. Phiên bản có thuộc tính

Khi muốn cung cấp lựa chọn BASIC/DETAILED hoặc cho phép disable:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(AuditSelector.class)
public @interface EnableAudit {
    boolean enabled() default true;
    AuditLevel level() default AuditLevel.BASIC;
}
```

Đây là **trích đoạn minh họa** cần `AuditSelector` và enum `AuditLevel`. Những thuộc tính trên trở thành **public API của annotation**; người dùng có thể viết:

```java
@EnableAudit(enabled = true, level = AuditLevel.DETAILED)
```

Hoặc:

```java
@EnableAudit(enabled = false)
```

Đừng chọn mặc định tùy tiện: nếu bật audit mặc định có chi phí hoặc nghĩa vụ tuân thủ, phải thống nhất ý nghĩa của `enabled=true`, môi trường hỗ trợ, các dependency cần cấu hình và hành vi khi thiếu provider.

### 3.3. Có cần `@AliasFor` không?

**Không phải annotation `@Enable...` nào cũng cần `@AliasFor`.** Với `enabled()` và `level()` là attributes riêng do selector đọc, không cần alias.

`@AliasFor` hữu ích khi custom annotation **tái xuất** hoặc đồng bộ attributes của một meta-annotation tương ứng. Ví dụ khi tạo composed annotation trực tiếp trên `@ComponentScan`, việc alias sang `basePackages` phải được khai báo đúng semantics, có kiểm thử và tài liệu rõ ràng.

Không sử dụng `@AliasFor` để nói rằng “`enabled` tự động truyền đến mọi imported configuration”. `@Import` không có thuộc tính `enabled` để alias; selector hoặc condition mới là nơi quyết định cách xử lý.

## 4. Ba cách triển khai annotation bật tính năng

### 4.1. Cách A — `@Import` class cấu hình cố định

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(AuditModuleConfig.class)
public @interface EnableAudit {
}
```

Phù hợp khi:

- một module luôn có cùng tập bean definitions;
- không cần chọn implementation dựa trên annotation attributes;
- muốn cấu trúc tối giản, dễ tìm từ annotation đến configuration.

`AuditModuleConfig` có thể khai báo nhiều `@Bean` methods, hoặc import thêm các config khác. Khi được xử lý, bean definitions phát sinh vẫn chịu mọi quy tắc về scope, dependency, conditions và names.

### 4.2. Cách B — `@Import(ImportSelector.class)`

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(AuditSelector.class)
public @interface EnableAudit {
    AuditLevel level() default AuditLevel.BASIC;
}
```

`AuditSelector` implement `org.springframework.context.annotation.ImportSelector`:

```java
@Override
public String[] selectImports(AnnotationMetadata metadata) {
    Map<String, Object> attrs =
            metadata.getAnnotationAttributes(EnableAudit.class.getName());
    if (attrs == null) {
        throw new IllegalStateException("Missing @EnableAudit");
    }
    AuditLevel level = (AuditLevel) attrs.get("level");
    return level == AuditLevel.DETAILED
            ? new String[] { DetailedAuditConfig.class.getName() }
            : new String[] { BasicAuditConfig.class.getName() };
}
```

Các snippet ở trên là **minh họa**, cần đủ imports, enum, classes. `ImportSelector` trả **tên class đầy đủ**, không trả bean name và không trực tiếp trả object bean.

Phù hợp khi:

- attributes của `@Enable...` quyết định class nào cần import;
- có nhiều implementation configurations;
- muốn ẩn chi tiết packages/classes nội bộ sau annotation;
- lựa chọn xảy ra lúc xây context và có thể kiểm thử rõ ràng.

`ImportSelector` có thể đọc `Environment` qua `EnvironmentAware` hoặc constructor injection các loại hạ tầng được hỗ trợ theo Javadoc Spring. Nhưng không nên lookup eager business beans chỉ để chọn import: selection diễn ra trong giai đoạn configuration parsing, thường trước khi bean ứng dụng sẵn sàng.

### 4.3. Cách C — `@Import(ImportBeanDefinitionRegistrar.class)`

Một registrar có thể sử dụng `AnnotationMetadata` và `BeanDefinitionRegistry` để chủ động tạo bean definitions:

```java
public final class AuditRegistrar
        implements ImportBeanDefinitionRegistrar {

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata metadata,
            BeanDefinitionRegistry registry) {
        RootBeanDefinition definition =
                new RootBeanDefinition(AuditRuntime.class);
        registry.registerBeanDefinition("auditRuntime", definition);
    }
}
```

Đây là **đoạn minh họa**, cần imports từ `org.springframework.context.annotation.ImportBeanDefinitionRegistrar`, `org.springframework.core.type.AnnotationMetadata`, `org.springframework.beans.factory.support.BeanDefinitionRegistry`/`RootBeanDefinition` và một class `AuditRuntime` có constructor phù hợp.

Phù hợp khi:

- số lượng/type/names của beans phụ thuộc metadata động;
- framework cần đăng ký definitions ở cấp thấp hơn `@Bean`;
- bạn thực sự cần kiểm soát `BeanDefinitionRegistry`.

Không nên dùng registrar khi chỉ cần hai factory methods cố định. Nó phức tạp hơn selector/configuration, dễ gây xung đột tên và có giới hạn vòng đời của các infrastructure post-processors. Đặc biệt, Javadoc Spring cảnh báo về cách đăng ký `BeanDefinitionRegistryPostProcessor` qua registrar; hãy tuân theo extension point phù hợp.

### 4.4. So sánh lựa chọn

| Yêu cầu | Khuyến nghị đầu tiên |
| --- | --- |
| Bật một tập cấu hình cố định | `@Import(MyFeatureConfig.class)` |
| Có hai config, chọn bằng attribute `mode` | `ImportSelector` |
| Chỉ cần bật/tắt một config theo property | `@Conditional` trên config có thể đủ |
| Môi trường dev/prod | `@Profile` nếu phù hợp |
| Thêm nhiều bean definitions động theo metadata | `ImportBeanDefinitionRegistrar` |
| Auto-configuration có ordering/aggregation phức tạp | Xem `DeferredImportSelector` và cơ chế auto-config tương ứng |
| Phát hiện tất cả application components dưới một package | `@ComponentScan`, không lạm dụng `@Import` |

Nguyên tắc: **chọn mức trừu tượng tối thiểu đáp ứng đúng yêu cầu**.

## 5. Phân biệt `@Enable...` với các annotation thực tế của Spring

Spring Framework có một số annotation tiêu biểu. Hãy xem cách sử dụng và cơ chế kích hoạt của chúng để thiết kế annotation riêng có trách nhiệm rõ ràng.

| Annotation | Bật tính năng gì? | Điều cần có thêm |
| --- | --- | --- |
| `@EnableCaching` | Hạ tầng xử lý các annotation cache như `@Cacheable` | `CacheManager`/cache resolver thích hợp và caching configuration |
| `@EnableAsync` | Hạ tầng xử lý các method `@Async` | Các managed beans phù hợp và executor/configuration thích hợp |
| `@EnableScheduling` | Hạ tầng phát hiện/đăng ký `@Scheduled` methods | Managed beans với scheduled methods và scheduler phù hợp |
| `@EnableTransactionManagement` | Hạ tầng xử lý `@Transactional` | Transaction manager phù hợp với tài nguyên và application |
| Custom `@EnableAudit` | Module audit do chính ứng dụng/thư viện định nghĩa | Config/beans được selector hoặc registrar đăng ký đúng |

### 5.1. Ví dụ thật: `@EnableCaching`

Trong Spring Framework 6.2, `@EnableCaching` được meta-annotated bằng `@Import(CachingConfigurationSelector.class)`. Selector này lựa chọn hạ tầng phù hợp với `AdviceMode`/cấu hình. Đây là ví dụ điển hình cho thiết kế “annotation công khai → selector → infrastructure configurations”.

Nhưng chỉ viết `@EnableCaching` **không bảo đảm mọi method được cache**. Cần có các cache annotations trên managed beans, manager/resolver phù hợp và cơ chế proxy/AspectJ theo config. Với proxy mode, self-invocation thông thường có thể bypass proxy; bài toán này thuộc AOP, không phải cơ chế `@Enable` tự giải quyết.

### 5.2. Ví dụ thật: `@EnableAsync`

`@EnableAsync` sử dụng `AsyncConfigurationSelector` để nhập cấu hình cho asynchronous method execution. Nó không biến mọi method Java thành bất đồng bộ. Cần method được đánh dấu `@Async` trên Spring-managed bean và lời gọi đi qua đúng infrastructure/proxy theo mode.

Không suy ra rằng một custom `@EnableAudit` phải làm AOP để trở thành “@Enable đúng chuẩn”. Nếu audit chỉ cần producer/service beans, `@Import` hoặc selector đơn giản là hoàn toàn hợp lệ.

### 5.3. Ví dụ thật: `@EnableScheduling`

`@EnableScheduling` đăng ký những infrastructure beans thích hợp để phát hiện `@Scheduled` trên managed beans. Nó không đồng nghĩa tự tạo jobs nếu ứng dụng không có method phù hợp. Việc scheduler, thread pool, lỗi thực thi và lifecycle chạy job cần được cân nhắc riêng.

### 5.4. Ví dụ thật: `@EnableTransactionManagement`

Annotation này bật hạ tầng hỗ trợ `@Transactional` nhưng **không tự tạo database**, `DataSource` hay transaction manager cho mọi ứng dụng. Một custom `@Enable...` cũng vậy: bạn cần công bố rõ những beans/tài nguyên phải được người dùng cung cấp và lúc nào tính năng thực sự sẵn sàng.

## 6. Public API: thiết kế attributes có ý nghĩa

Annotation bật tính năng nên có surface area nhỏ, rõ và ổn định.

### 6.1. `enabled`, `mode`, `level` và giá trị mặc định

Một thiết kế tốt:

```java
public @interface EnableAudit {
    boolean enabled() default true;
    AuditLevel level() default AuditLevel.BASIC;
}
```

Đây là đoạn minh họa thuộc tính, chưa bao gồm `@Target`/`@Retention`/`@Import`.

- `enabled` thể hiện **bật/tắt toàn bộ module**.
- `level` chọn implementation/behavior khi module được bật.
- `default` đảm bảo cách gọi `@EnableAudit` không tham số có semantics xác định.
- Khi `enabled=false`, các thuộc tính khác có thể bị bỏ qua hoặc phải được validate theo policy được tài liệu hóa.

Nếu use case là chọn một trong hai protocols, tên attribute `protocol` có thể rõ hơn một `mode` chung chung. Không thêm hàng loạt switches cho từng internal bean chỉ vì annotation cho phép khai báo nhiều attributes.

### 6.2. Vì sao dùng enum thay vì String?

`AuditLevel.BASIC` và `AuditLevel.DETAILED` được Java compiler kiểm tra; typo như `DETAILD` là compile error. Ngược lại, `String level()` dễ đưa typo đến runtime.

Enum phù hợp với tập lựa chọn nhỏ, ổn định. Khi cần mở rộng provider bởi plugin bên thứ ba, có thể cần model khác: class token, provider type hoặc configuration properties. Đừng cố liệt kê mọi extension tương lai trong một enum public nếu ecosystem dự kiến mở.

### 6.3. Không đặt secrets vào annotation attributes

Java annotation attributes về bản chất là metadata tĩnh của class. Không dùng annotation để chứa mật khẩu, API key hoặc secrets. Những giá trị có thể thay đổi theo môi trường nên đi qua cấu hình runtime/secret management phù hợp, không compile vào source.

### 6.4. Cẩn trọng với rename/refactor

Class selector và config nên dùng `SomeConfig.class.getName()` thay vì chuỗi tên class literal để giảm rủi ro sai package, nhất là với nested classes. Đổi tên public annotation hoặc enum constants là thay đổi API ảnh hưởng mọi caller.

Bean names mà consumer tham chiếu bằng string cũng có thể là hợp đồng, nhưng chúng không cần được lộ như attributes nếu người dùng chỉ cần interface/type injection.

### 6.5. Những gì `@Enable...` không nên cam kết

Đừng quảng cáo rằng annotation “bật audit cho **tất cả** objects” khi thực tế module chỉ cấu hình một `AuditService`. Những object tạo bằng `new` ngoài Spring không tự được quản lý. Nếu feature dùng AOP, caller cần đi qua proxy phù hợp; nếu dùng bean factory, chỉ các consumers được inject service mới tận dụng capability.

Hãy mô tả chính xác:
- Bean definitions nào được đăng ký?
- Cần những dependencies nào?
- Tính năng bị disable nghĩa là gì?
- Có tác động đến những bean cũ khi context đã refresh hay không?
- Có bean scope/lifecycle, side effects hoặc startup cost đáng kể nào không?

## 7. Vòng đời và thời điểm bật tính năng

Một số mốc quan trọng:

```text
Class được đăng ký vào context
           |
           v
Configuration metadata được đọc
           |
           v
@Import / selector / registrar xử lý
           |
           v
Bean definitions được đăng ký
           |
           v
Các bean post-processors và factory phases vận hành
           |
           v
Beans được tạo khi cần theo scope/lazy/dependencies
           |
           v
Ứng dụng bắt đầu sử dụng capability
```

### 7.1. `@Enable` thường là cấu hình bootstrap, không phải runtime toggle

Nếu `@EnableAudit(enabled=true)` dẫn selector đến `AuditServiceConfig`, lựa chọn được áp dụng trong quá trình xây context. Sau `refresh()`, việc sửa một property ngẫu nhiên **không tự chạy lại** `ImportSelector` để xóa hoặc thêm bean definitions.

Muốn bật/tắt audit trong khi ứng dụng đang chạy, thường cần một facade luôn tồn tại, chẳng hạn `AuditService` kiểm tra một feature flag tại mỗi invocation, hoặc một mechanism refresh/rebuild context được thiết kế đúng. Đó là yêu cầu khác với mẫu `@Enable...` tĩnh.

### 7.2. Scope/lazy vẫn thuộc BeanFactory

`@Enable...` tự nó không thay đổi singleton thành prototype, không bảo đảm các beans được lazy và không quyết định thứ tự khởi tạo. Mọi bean được import vẫn dùng `@Scope`, `@Lazy`, `@DependsOn`, dependency graph và BeanPostProcessors như những beans khác.

### 7.3. “Enable” không có nghĩa “bỏ qua mọi điều kiện khác”

Imported `@Configuration` có thể được gắn `@Profile`/`@Conditional`. Nếu điều kiện không thỏa, bean definitions có thể bị bỏ qua dù selector đã trả class name. Consumer yêu cầu dependency bắt buộc vẫn có thể làm context fail. Phải thiết kế đồng bộ cả consumer config và producer config.

### 7.4. Điều kiện classpath

Nếu selector trả `com.vendor.AuditIntegrationConfig` nhưng module chứa class này không có trên runtime classpath, import processing có thể thất bại. Đừng trả tên của class tùy chọn khi chưa kiểm tra điều kiện tương ứng; với Spring Boot libraries, các conditional auto-config mechanisms thường phù hợp hơn để tích hợp classpath-conditional modules.

## 8. Ví dụ chạy được Java 17+: thiết kế `@EnableAudit` đầy đủ

Chúng ta tạo một Java application Spring Context thuần với ba configuration classes:

- `BasicApp`: `@EnableAudit` mặc định, chọn BASIC.
- `DetailedApp`: `@EnableAudit(level=DETAILED)`, chọn DETAILED.
- `OffApp`: `@EnableAudit(enabled=false)`, không đăng ký các beans của module audit.

Mỗi context độc lập. `AuditImportSelector` chọn **hai cấu hình** khi enabled: một cung cấp `AuditSink`, một cung cấp `AuditService` phụ thuộc vào sink. Khi disabled, nó trả một mảng rỗng, nhờ đó không để lại consumer thiếu dependency.

Không cần Spring Boot, HTTP, database, XML hoặc external services.

### 8.1. Cấu trúc file

```text
enable-audit-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/
    └── EnableAuditDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'enable-audit-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'EnableAuditDemo'
}
```

Chạy bằng JDK 17+ và bản Gradle tương thích JDK. `spring-context` kéo theo các module Spring Beans/Core cần cho `@Configuration`, `@Import`, `AnnotationMetadata` và `AnnotationConfigApplicationContext`.

### 8.2. Mã nguồn hoàn chỉnh

Lưu toàn bộ vào `src/main/java/EnableAuditDemo.java`:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Map;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class EnableAuditDemo {

    public enum AuditLevel {
        BASIC, DETAILED
    }

    public interface AuditSink {
        String format(String action);
    }

    public record BasicAuditSink() implements AuditSink {
        @Override
        public String format(String action) {
            return "basic:" + action;
        }
    }

    public record DetailedAuditSink() implements AuditSink {
        @Override
        public String format(String action) {
            return "detailed:" + action + "|trace";
        }
    }

    public record AuditService(AuditSink sink) {
        public String report(String action) {
            return sink.format(action);
        }
    }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @Import(AuditImportSelector.class)
    public @interface EnableAudit {
        boolean enabled() default true;
        AuditLevel level() default AuditLevel.BASIC;
    }

    public static class AuditImportSelector implements ImportSelector {
        @Override
        public String[] selectImports(
                AnnotationMetadata importingClassMetadata) {

            Map<String, Object> attributes =
                    importingClassMetadata.getAnnotationAttributes(
                            EnableAudit.class.getName());

            if (attributes == null) {
                throw new IllegalStateException(
                        "Missing @EnableAudit metadata");
            }

            boolean enabled = (Boolean) attributes.get("enabled");
            if (!enabled) {
                return new String[0];
            }

            AuditLevel level =
                    (AuditLevel) attributes.get("level");

            Class<?> sinkConfig = level == AuditLevel.DETAILED
                    ? DetailedAuditConfig.class
                    : BasicAuditConfig.class;

            return new String[] {
                    sinkConfig.getName(),
                    AuditServiceConfig.class.getName()
            };
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class BasicAuditConfig {
        @Bean
        AuditSink auditSink() {
            return new BasicAuditSink();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DetailedAuditConfig {
        @Bean
        AuditSink auditSink() {
            return new DetailedAuditSink();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AuditServiceConfig {
        @Bean
        AuditService auditService(AuditSink sink) {
            return new AuditService(sink);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAudit
    public static class BasicApp {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAudit(level = AuditLevel.DETAILED)
    public static class DetailedApp {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAudit(enabled = false)
    public static class OffApp {
    }

    private static void show(
            String label, Class<?> applicationConfig) {

        try (var context =
                     new AnnotationConfigApplicationContext(
                             applicationConfig)) {

            int sinkCount =
                    context.getBeanNamesForType(AuditSink.class).length;
            int serviceCount =
                    context.getBeanNamesForType(AuditService.class).length;

            System.out.println(label + ": sinks=" + sinkCount +
                    ", services=" + serviceCount);

            if (serviceCount > 0) {
                AuditService service =
                        context.getBean(AuditService.class);
                System.out.println(label + ": " +
                        service.report("checkout"));
            }
        }
    }

    public static void main(String[] args) {
        show("BASIC", BasicApp.class);
        show("DETAILED", DetailedApp.class);
        show("OFF", OffApp.class);
    }
}
```

### 8.3. Cách chạy và stdout

Tại thư mục `enable-audit-demo`:

```bash
gradle run --quiet
```

Nếu dự án có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS, hoặc `.\gradlew.bat run --quiet` trên Windows PowerShell.

Stdout **do chính chương trình in ra**:

```text
BASIC: sinks=1, services=1
BASIC: basic:checkout
DETAILED: sinks=1, services=1
DETAILED: detailed:checkout|trace
OFF: sinks=0, services=0
```

Đây là các dòng `System.out.println` từ demo. Một build tool hoặc logging backend có thể tạo thêm dòng riêng; không coi chúng là output nghiệp vụ của ứng dụng.

### 8.4. Phân tích từng case

**BASIC:** `@EnableAudit` trên `BasicApp` sử dụng defaults `enabled=true` và `level=BASIC`. Selector nhận metadata, chọn `BasicAuditConfig` và `AuditServiceConfig`, tạo bean `AuditSink` trả về `BasicAuditSink` và bean `AuditService` tiêu thụ sink đó. Có đúng một bean mỗi kiểu. `report("checkout")` trả chuỗi `basic:checkout`.

**DETAILED:** `DetailedApp` khai báo `level=DETAILED` nên selector chọn `DetailedAuditConfig`. Bean `AuditService` được tạo từ cùng `AuditServiceConfig`, nhận `DetailedAuditSink` theo interface `AuditSink`. Dòng audit chứa hậu tố `|trace`.

**OFF:** `OffApp` vẫn được Spring xử lý như một configuration class hợp lệ, nhưng selector đọc `enabled=false` và trả mảng rỗng. **Cả `AuditSink` lẫn `AuditService` đều không được đăng ký**, vì cả hai nguồn config nằm phía sau selector. Context refresh thành công; chương trình không gọi `getBean(AuditService.class)` ở nhánh không có service.

Cách thiết kế này làm cho “disable feature” có semantics rõ: không có audit capability beans trong context ấy. Nếu muốn service audit vẫn tồn tại nhưng là no-op, đó là một policy khác: hãy cho selector chọn `NoOpAuditConfig` đồng thời cung cấp đủ consumer dependencies.

### 8.5. Vì sao hai configs dùng chung bean name `auditSink` nhưng không xung đột?

`BasicAuditConfig` và `DetailedAuditConfig` đều có factory method `@Bean auditSink()`. Tuy nhiên, selector **chỉ chọn một trong hai configs tại một thời điểm**, còn mỗi case tạo **ApplicationContext riêng**. Vì vậy registry không nhận đồng thời hai bean definitions `auditSink`.

Nếu code khác lại import cả hai configs, tên `auditSink` có thể xung đột/được override tùy registry policy; sau khi đổi tên, cả hai vẫn có thể gây ambiguity khi inject `AuditSink` đơn. Selector không thể ngăn registrations độc lập do những module khác thực hiện.

### 8.6. Vì sao `AuditServiceConfig` dùng method parameter?

`AuditServiceConfig.auditService(AuditSink sink)` nhận dependency do Spring resolve. Nó không tự gọi `BasicAuditConfig.auditSink()` hoặc `DetailedAuditConfig.auditSink()` và không cần biết implementation đang hoạt động.

Điều này giữ cấu hình tách lớp: selector chọn provider config, BeanFactory inject đúng provider vào consumer. Khi thay thế implementation, consumer config không đổi.

### 8.7. Vì sao không dùng `@ComponentScan` trong ví dụ?

Để minh họa rõ “chỉ những classes được import mới tham gia”, demo không quét package. Nếu bật scanner trên package chứa các configs nhưng gắn thêm stereotype lên tất cả chúng, rất dễ vô tình đăng ký cả BASIC và DETAILED trước khi selector kịp tạo lựa chọn, làm sai mục tiêu demo.

Một thư viện có thể dùng component scanning nội bộ, nhưng khi thiết kế `@Enable...` có trách nhiệm chọn một implementation, hãy cân nhắc **package và registration boundaries**. Đừng scan toàn bộ thư viện chỉ để sử dụng đúng một bean.

## 9. Các biến thể thiết kế thường gặp

### 9.1. Bật tính năng nhưng cho phép không có provider: no-op

Nếu audit là optional và application luôn inject `AuditService`, tắt bằng cách **không đăng ký service** sẽ gây lỗi nếu consumer vẫn bắt buộc cần nó. Một chiến lược khác là luôn đăng ký interface service và đưa vào một `NoOpAuditSink` khi disabled.

Ví dụ minh họa:

```java
public record NoOpAuditSink() implements AuditSink {
    @Override
    public String format(String action) {
        return "ignored";
    }
}
```

Đoạn này cần interface `AuditSink` ở demo mục 8. Một selector có thể chọn `NoOpAuditConfig` + `AuditServiceConfig` khi `enabled=false`. Hợp đồng public khi đó đổi thành “audit service luôn có mặt nhưng có thể không ghi”. Chọn thiết kế dựa trên nhu cầu của consumers và yêu cầu an toàn/tuân thủ; không âm thầm bỏ audit có ý nghĩa bắt buộc trong hệ thống thật.

### 9.2. Tách `enabled` khỏi `level`

`enabled=false` thường ưu tiên hơn `level` vì không có gì để lựa chọn khi module tắt. Tuy nhiên, nếu muốn báo lỗi khi người dùng đặt `enabled=false, level=DETAILED`, selector có thể validate tổ hợp đó. Quy tắc phải được mô tả rõ trong API; ví dụ mục 8 chủ động bỏ qua `level` khi disabled.

### 9.3. Chọn theo `Environment`

Có thể cho selector implement `EnvironmentAware` và đọc một property như `audit.level` để override annotation attribute. Đây là một biến thể phù hợp khi cấu hình triển khai phải được điều chỉnh mà không sửa code. Cần công bố thứ tự ưu tiên: attribute thắng hay property thắng, xử lý giá trị lỗi thế nào, và property cần được thiết lập **trước configuration processing**.

Dùng `@ConditionalOnProperty` trong Spring Boot hoặc `@Conditional` trong Spring Framework cho yêu cầu conditional đơn giản có thể ít code hơn một selector custom. Đừng tự viết một hệ thống condition/flags quá rộng khi framework đã có extension point đáp ứng.

### 9.4. Annotation trỏ tới class được chọn

Đối với hệ sinh thái nhiều provider mà enum không đủ linh hoạt, một thiết kế `Class<? extends AuditSink> implementation()` có thể cho phép caller chọn class. Nhưng điều đó lộ implementation type vào public API và vẫn cần cách đăng ký/DI phù hợp. Các object do người dùng chọn phải được Spring tạo chứ không tự `new` trong selector để tránh mất injection/lifecycle.

### 9.5. Annotation kích hoạt advisor/proxy

Một số `@Enable...` bật infrastructure `BeanPostProcessor`, `Advisor` hoặc proxy để áp dụng behavior lên các managed beans. Khi thiết kế kiểu này, hãy phân biệt:

- **Import/registration** tạo infrastructure definitions.
- **Post-processing/AOP** áp dụng behavior cho beans/calls phù hợp.
- **Method invocation** có đi qua proxy không (self-invocation)?
- **Số lượng proxy/post-processors** có bị nhân đôi khi import nhiều config không?

Không phải mọi annotation `@Enable...` đều phải proxy. Hãy chọn infrastructure theo khả năng cần hỗ trợ, không vì muốn bắt chước toàn bộ mã nguồn của `@EnableCaching`.

## 10. ImportSelector, DeferredImportSelector và ImportBeanDefinitionRegistrar

### 10.1. ImportSelector thường

`ImportSelector.selectImports(AnnotationMetadata)` chạy trong giai đoạn Spring phân tích cấu hình. Trả về `String[]` tên class cần import. Có thể chọn theo annotation attributes, `Environment` hoặc những metadata bootstrap khác; thích hợp với tình huống trong ví dụ.

**Không trả bean names** như `"auditService"`. Hãy trả class names bằng `AuditServiceConfig.class.getName()`. Với nested classes, JVM binary name chứa `$`; dùng `Class.getName()` để tránh ghép sai.

### 10.2. DeferredImportSelector

`DeferredImportSelector` là biến thể cho phép trì hoãn selection đến giai đoạn processing sau khi các configuration classes thông thường được xét. Đây là cơ chế bootstrap, **không phải runtime reload** hay asynchronous task. `DeferredImportSelector.Group` có thể phối hợp nhiều deferred selectors, hữu ích trong auto-configuration frameworks phức tạp.

Đối với một tính năng audit với BASIC/DETAILED, selector thường là đủ. Chỉ chọn deferred nếu cần ordering/aggregation đặc thù có lý do rõ.

### 10.3. ImportBeanDefinitionRegistrar

Registrar làm việc trực tiếp với bean definition registry. Nó cho phép tạo tên/kiểu/metadata bean không phụ thuộc cố định vào một `@Bean` method, nhưng phức tạp hơn và cần hiểu bean factory lifecycle.

Một `@Enable...` trong thư viện có thể dùng registrar khi cần đăng ký adapter/proxy factories theo tên interface được khai báo trên annotation. Đừng sử dụng registrar để né việc viết một configuration class rõ ràng.

### 10.4. Có dùng đồng thời các cơ chế không?

Có, một custom annotation có thể import một configuration class mà cấu hình đó lại import selector hoặc registrar; một selector cũng có thể chọn một configuration chứa các `@Bean` methods và conditions. Điều này tạo đồ thị import mạnh nhưng có thể rất khó debug.

Khuyến nghị giữ **một điểm vào, một nguyên tắc lựa chọn, một nguồn chịu trách nhiệm đăng ký mỗi bean**. Ghi lại import graph trong tài liệu và kiểm thử số bean definitions cuối cùng.

## 11. Tích hợp vào dự án nhiều module

Một thư viện nên phân biệt **public configuration API** và **implementation detail**:

```text
audit-api/
  AuditSink.java
  AuditService.java
  EnableAudit.java               <-- annotation public
  AuditLevel.java                <-- lựa chọn public

audit-spring/
  AuditImportSelector.java       <-- internal implementation
  BasicAuditConfig.java
  DetailedAuditConfig.java
  AuditServiceConfig.java

shop-app/
  ShopApplication.java           <-- dùng @EnableAudit
```

Đây là mô hình kiến trúc minh họa; cấu trúc build thực tế phải bảo đảm annotation và selector/config classes có mặt trong runtime dependency. Nếu chia làm nhiều JAR, hãy kiểm tra cycle dependencies: annotation trong module API không thể tham chiếu `AuditImportSelector.class` ở module implementation nếu implementation lại phụ thuộc ngược vào API trong cách chia module đơn giản. Có thể đặt annotation cùng module Spring integration hoặc tách contracts/entrypoint sao cho hướng dependency không tạo vòng.

Với module thật, một cấu trúc thường dễ triển khai hơn:

```text
audit-contracts/
  AuditSink.java
  AuditService.java

audit-spring/
  EnableAudit.java
  AuditLevel.java
  AuditImportSelector.java
  configurations...

shop-app/
  ShopApplication.java
```

`audit-spring` phụ thuộc `audit-contracts`, còn `shop-app` phụ thuộc cả hai hoặc có dependencies bắc cầu phù hợp. `@EnableAudit` công khai trong module `audit-spring`; consumer không cần biết từng class cấu hình nội bộ.

### 11.1. Giữ cấu hình hạ tầng khỏi component scan quá rộng

Nếu các imported configuration classes mang `@Configuration` và nằm ngay dưới một root package được Spring Boot component-scanned, chúng có thể được phát hiện **độc lập với selector**. Ví dụ cả `BasicAuditConfig` và `DetailedAuditConfig` là `@Configuration` nằm dưới package root Boot, rồi `@EnableAudit` lại chỉ chọn một; scanner có thể đã đăng ký cả hai, gây duplicate bean names/types hoặc khiến disabled vẫn có beans.

Giải pháp thiết kế:

- đặt các internal module configurations ngoài application scan root;
- không để chúng được component-scanned trừ khi cố ý;
- sử dụng explicit module import/auto-config có điều kiện;
- bổ sung integration tests từ Spring Boot application context thật để bảo đảm không đăng ký nhầm.

Đừng nhầm “class được selector chọn” với “class chưa bao giờ được đăng ký từ nguồn khác”.

### 11.2. Không lạm dụng cùng một `@Enable` trên nhiều configurations

Nếu một context nhập nhiều configurations cùng mang `@EnableAudit` nhưng yêu cầu **khác level**, selector có thể gặp hai requests không tương thích. Đây là câu hỏi thiết kế API: cần fail fast, quy tắc precedence hay hỗ trợ nhiều audit providers?

Đừng dựa vào thứ tự scan/import để đoán config nào thắng. Với capability chỉ cho phép một provider, đặt một policy rõ, tránh lặp `@Enable...` ở những nơi khác nhau trong cùng composition root.

### 11.3. Spring Boot starter và auto-configuration

Một reusable Spring Boot starter thường khai báo **auto-configuration** theo các convention/metadata của phiên bản Boot đang dùng và dùng điều kiện như classpath, properties và missing beans. Không nhất thiết yêu cầu mọi người tiêu dùng gắn custom `@Enable...`.

Custom `@Enable...` hợp lý khi người dùng muốn **opt-in tường minh**, có attributes thể hiện lựa chọn, hoặc một integration cần kích hoạt chỉ tại một cấu hình. Auto-configuration hợp lý khi muốn behavior plug-and-play nhưng có conditional semantics chặt chẽ. Có thể kết hợp, song phải tránh đăng ký chồng cùng capability.

## 12. Những lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Annotation `@EnableAudit` không có tác dụng | Class dùng annotation chưa được Spring register/import/scan | Kiểm tra configuration entry point thực tế |
| `selectImports` không chạy | Meta-annotation `@Import` thiếu hoặc selector class không hợp lệ | Kiểm tra `@Target`, `@Retention`, imports, classpath |
| Selector trả `"auditService"` | Trả bean name thay vì class name | Trả `AuditServiceConfig.class.getName()` |
| Đọc metadata trả `null` | Sai annotation type hoặc selector không được gọi từ annotation dự kiến | Kiểm tra `EnableAudit.class.getName()` và class importing |
| Cast `level` lỗi | Kiểu enum/attribute không khớp | Dùng đúng `AuditLevel` và metadata accessor |
| Tắt `enabled=false` nhưng context lỗi dependency | Consumer vẫn được đăng ký, producer bị loại | Tắt cả module graph hoặc dùng no-op/optional consumer |
| BASIC và DETAILED cùng thành bean | Configuration khác scan/import cả hai | Rà soát component scan roots và import graph |
| Trùng bean name `auditSink` | Cả hai provider configs được đăng ký | Chỉ đăng ký provider đã chọn, hoặc định danh rõ |
| `NoUniqueBeanDefinitionException` | Có nhiều `AuditSink` implementations cùng type | `@Qualifier`, `@Primary` hoặc module selection rõ |
| Context thiếu bean dù `@EnableAudit` được xử lý | Imported config bị `@Profile`/`@Conditional` loại | Kiểm tra profile, conditions, classpath |
| Property thay đổi sau `refresh` mà tính năng không đổi | Selection là bootstrap decision | Thiết kế runtime flag/facade riêng nếu cần |
| Test gọi `new AppConfig()` rồi mong có bean | Không có Spring container xử lý metadata | Tạo `AnnotationConfigApplicationContext` |
| Dùng `@ImportResource` thay `@Import` trong custom annotation | Nhầm XML resource với Java class imports | Dùng `@Import` cho Java classes/selectors/registrars |
| Annotation dùng String secret | Secrets bị compile vào class metadata | Sử dụng secret provider/environment có kiểm soát |
| Registrar đụng bean name có sẵn | Registry keys trùng hoặc registration chạy nhiều lần | Kiểm tra tồn tại, naming policy và module ownership |
| Custom `@Enable` khiến startup chậm | Selector làm I/O hoặc quét package quá rộng | Giữ selector nhẹ, import có mục tiêu, đo startup |
| Proxy feature không áp dụng khi self-call | Spring AOP self-invocation bypass proxy thông thường | Thiết kế service boundaries phù hợp, không nhầm với import |
| Hai contexts cho kết quả khác nhau | Mỗi context có registry/profile/conditions riêng | Kiểm tra từng context, không giả định singleton toàn JVM |

### 12.1. Quy trình debug theo bằng chứng

1. **Xem entry point:** context được tạo từ class nào? Class đó có `@Enable...` trực tiếp/meta-annotated không?
2. **Theo dõi import graph:** annotation dẫn đến config, selector hay registrar nào? Chúng chọn/đăng ký chính xác những gì?
3. **Kiểm tra metadata:** type của `enabled`, `level` và source annotations có như dự kiến không?
4. **Xem bean candidates:** sau khi context refresh thành công, gọi `getBeanNamesForType(AuditSink.class)` và `getBeanNamesForType(AuditService.class)`.
5. **Đối chiếu disabled mode:** trong thiết kế mục 8, cả hai counts cần bằng zero.
6. **Xem config bổ sung:** component scan, Boot auto-config, profile và conditional declarations có đăng ký provider khác không?
7. **Đọc exception root cause:** thiếu bean, trùng tên hay nhiều ứng viên cùng type là những lỗi khác nhau; không chữa tất cả bằng `@Primary`.
8. **Kiểm thử context nhỏ và context ứng dụng thật:** tránh chỉ unit test selector rồi bỏ qua cách packaging/component scanning vận hành ở production.

## 13. Kiểm thử annotation `@Enable...` ở các tầng

### 13.1. Kiểm thử hợp đồng của selector

Một unit test có thể tạo metadata cho configuration class ở mức test, rồi kiểm tra mảng class names được chọn. Các trường hợp tối thiểu:

| Annotation trên class | Kỳ vọng |
| --- | --- |
| `@EnableAudit` | BASIC config + service config |
| `@EnableAudit(level=DETAILED)` | DETAILED config + service config |
| `@EnableAudit(enabled=false)` | Mảng import rỗng |
| Annotation không có mặt nhưng selector vẫn được gọi trực tiếp | Báo lỗi metadata rõ ràng |

Nếu tách logic quyết định thành một hàm thuần như `selectConfigs(boolean enabled, AuditLevel level)`, unit test có thể kiểm tra nhanh mà không phải dựng container. Nhưng bài test ấy chưa xác thực cơ chế `@Import` thật.

### 13.2. Integration test cần xác nhận registry và DI

Ví dụ một test khi dùng types của mục 8:

```java
try (var context =
        new AnnotationConfigApplicationContext(
                EnableAuditDemo.DetailedApp.class)) {

    var sinkNames = context.getBeanNamesForType(
            EnableAuditDemo.AuditSink.class);
    var service = context.getBean(
            EnableAuditDemo.AuditService.class);

    if (sinkNames.length != 1) {
        throw new AssertionError("Expected one AuditSink");
    }
    if (!"detailed:checkout|trace".equals(
            service.report("checkout"))) {
        throw new AssertionError("Wrong audit implementation");
    }
}
```

Đây là một **trích đoạn test** dùng các public nested types từ demo, không phải source file độc lập. Test như thế xác minh **annotation → import → bean definition → dependency injection → behavior**, hơn là chỉ kiểm tra selector trả tên class đúng.

### 13.3. Tại sao cần test disabled?

Một chức năng chỉ chạy đúng khi enabled chưa đủ an toàn. Tắt tính năng có thể để lại bean consumers chưa được thỏa dependency hoặc các components bị scan tự động. Với `OFF`, hãy kiểm tra:

- Context có thể refresh thành công.
- Không có `AuditSink`.
- Không có `AuditService` theo contract đã công bố.
- Không còn scheduled task/side effect thuộc capability nếu implementation ngoài ví dụ có thêm infrastructure.
- Không có một auto-configuration khác bật audit lại ngoài ý muốn.

### 13.4. Test nhiều context có một ý nghĩa riêng

Các tests tạo contexts BASIC, DETAILED và OFF tách biệt giúp tránh dùng lẫn registry và giữ output ổn định. Singleton Spring không phải singleton toàn JVM; hai contexts có thể có hai instances/tập beans khác nhau mà không mâu thuẫn.

## 14. Bài tập thực hành và đáp án

### Bài 1 — Khi nào cần selector?

Một module chỉ có duy nhất `MetricsConfig`, không có attributes và không đổi theo environment. Có nên viết `ImportSelector` không?

**Đáp án:** Không bắt buộc. Dùng `@Import(MetricsConfig.class)` trực tiếp trong custom `@EnableMetrics` là cách đơn giản, rõ nghĩa hơn.

### Bài 2 — Điều gì khiến annotation thật sự có tác dụng?

Một class `AppConfig` mang `@EnableAudit` nhưng chưa bao giờ được register/scan/import vào bất kỳ `ApplicationContext` nào. Có bean audit không?

**Đáp án:** Không do annotation ấy. Metadata không tự kích hoạt ngoài container; Spring phải xử lý configuration class.

### Bài 3 — Hai class được import khi bật

Selector trả `BasicAuditConfig.class.getName()` nhưng quên `AuditServiceConfig.class.getName()`. `AuditService` có được tự đăng ký không?

**Đáp án:** Không qua selector đó. Basic config chỉ tạo `AuditSink`, còn service cần một nguồn registration riêng. Thiết kế module graph phải đủ.

### Bài 4 — OFF mode tạo lỗi

Selector trả mảng rỗng khi disabled, nhưng `AppConfig` còn khai báo `@Bean CheckoutService checkoutService(AuditService service)` không optional. Điều gì xảy ra?

**Đáp án:** Context có thể fail do thiếu bean `AuditService`. Cần disable cả consumer, dùng optional dependency hoặc cung cấp no-op implementation theo hợp đồng.

### Bài 5 — Chọn dựa trên enum

`@EnableAudit(level=DETAILED)` ở demo có bao nhiêu `AuditSink`?

**Đáp án:** Một, nếu không có registrations bổ sung. Selector chỉ chọn `DetailedAuditConfig` và `AuditServiceConfig`.

### Bài 6 — Trùng bean name

Cả `BasicAuditConfig` và `DetailedAuditConfig` cùng tồn tại trong một context do một scanner khác, đều khai báo `@Bean auditSink()`. Có nguy cơ gì?

**Đáp án:** Xung đột/ghi đè bean name hoặc nhầm provider. Hãy sửa phạm vi đăng ký, tránh scan các internal configs ngoài selector.

### Bài 7 — `@AliasFor` có bắt buộc cho `level`?

Custom `@EnableAudit` có riêng `AuditLevel level()`, selector đọc metadata. Có phải alias `level` sang `@Import.value` không?

**Đáp án:** Không. `@Import.value` nhận class array, không nhận AuditLevel. Attribute `level` là input riêng cho selector.

### Bài 8 — Thay property khi ứng dụng đã chạy

Thay `audit.level=BASIC` thành `DETAILED` sau `ApplicationContext.refresh()` có tự thay imported config không?

**Đáp án:** Không. Import decisions thuộc giai đoạn bootstrap; runtime switching cần mechanism khác.

### Bài 9 — Dùng `@EnableCaching` thiếu CacheManager

Một ứng dụng khai báo `@EnableCaching` và `@Cacheable` trên managed bean, nhưng chưa cấu hình cache provider/manager phù hợp. Có nên giả định caching hoàn toàn hoạt động?

**Đáp án:** Không. Annotation bật infrastructure, nhưng các phụ thuộc của infrastructure vẫn phải được thỏa mãn. Cần kiểm tra cache configuration và calls thực tế.

### Bài 10 — Sự khác biệt selector và registrar

Library muốn chọn một trong hai `@Configuration` classes. Library khác muốn đăng ký nhiều bean definitions theo metadata annotation. Chọn công cụ nào?

**Đáp án:** `ImportSelector` cho lựa chọn class configurations; `ImportBeanDefinitionRegistrar` cho đăng ký definitions cấp thấp có tính động.

### Bài 11 — Quan hệ phụ thuộc giữa các factory methods

`AuditServiceConfig` muốn dùng `AuditSink` được config khác tạo. Có nên new một `BasicAuditSink` trực tiếp trong service method?

**Đáp án:** Không nếu muốn module selector quyết định implementation. Viết `@Bean AuditService auditService(AuditSink sink)`; BeanFactory cung cấp managed dependency.

### Bài 12 — Scope của enable annotation

Hai `AnnotationConfigApplicationContext` độc lập đều dùng `@EnableAudit`. Có bắt buộc cùng dùng một singleton `AuditSink` toàn JVM không?

**Đáp án:** Không. Spring singleton scope là trong một container/BeanFactory; các contexts độc lập có bean registries riêng.

### Bài 13 — Bật transaction bằng custom @Enable?

Một người muốn tạo `@EnablePayments`, bên trong chỉ import `PaymentServiceConfig` và mong mọi method tự động có transaction. Điều đó đúng không?

**Đáp án:** Không. `@EnablePayments` trong thiết kế ấy chỉ nhập bean definitions do config công bố. Transaction management cần hạ tầng riêng, transaction manager và interception/cơ chế phù hợp; không xuất hiện chỉ từ việc đặt tên annotation là Enable.

### Bài 14 — API công khai của module

Thư viện có các lớp `DetailedAuditConfig` và `AuditImportSelector` được đổi package giữa các phiên bản, nhưng vẫn giữ `EnableAudit` và `AuditLevel` ổn định. Ứng dụng có cần biết package mới của hai lớp nội bộ không?

**Đáp án:** Thường không nếu entry point và contract public giữ nguyên, và jar/module thư viện cung cấp đúng classes. Đây là một lợi ích chính của annotation façade cho cấu hình.

## 15. Checklist trước khi phát hành custom `@Enable...`

- Tính năng có cần annotation bật tường minh, hay `@Import`/`@Conditional` đã đủ?
- Annotation có `@Target(TYPE)`, `@Retention(RUNTIME)`, `@Documented` và đúng `@Import` chưa?
- Attributes có ý nghĩa nghiệp vụ, tên rõ, defaults hợp lý và types compiler-checkable chưa?
- Selector/registrar chỉ làm công việc bootstrap, không tự tạo business objects bên ngoài BeanFactory chứ?
- Khi **enabled**, mọi producer/consumer/configuration cần thiết có được đăng ký nhất quán không?
- Khi **disabled**, các consumer bắt buộc có bị bỏ lại với dependency thiếu không?
- Có khả năng config bị scan hoặc auto-config đăng ký thêm từ đường khác không?
- Selector có trả **fully qualified class names** và xử lý classpath/profiles/conditions không?
- Có bean name conflicts hoặc nhiều candidates cùng interface không?
- Các tham số `@Bean`/constructors đã thể hiện dependency rõ thay vì gọi trực tiếp config methods chưa?
- Có hiểu đúng runtime toggle khác bootstrap-time enable không?
- Public API có tránh lộ secrets hoặc internal class names không?
- Đã test annotation ở cả BASIC, DETAILED, OFF và kiểm chứng số lượng bean cùng behavior trong Spring context thật chưa?

## 16. Tổng kết

Mẫu **`@Enable...`** biến một tập cấu hình và extension points thành API khai báo gọn: người dùng chỉ gắn một annotation trên configuration class, còn thư viện dùng **`@Import`** để đăng ký cấu hình cố định, chọn bằng **`ImportSelector`**, hoặc đăng ký bean definitions qua **`ImportBeanDefinitionRegistrar`** khi cần.

Thiết kế tốt không chỉ là làm cho annotation “có tác dụng” khi bật; nó phải làm cho **enabled/disabled semantics, dependency graph, bean ownership và classpath boundaries** nhất quán. Với use case đơn giản, nhập configuration cố định; với choices theo attributes, dùng selector; với registration hạ tầng rất động, cân nhắc registrar. Tránh tạo infrastructure phức tạp chỉ để trông giống một annotation có sẵn của Spring.

**Nguyên tắc cuối:** `@Enable...` là quyết định ở lúc **configuration processing**, không mặc nhiên là công tắc runtime. Tất cả object được chọn vẫn cần bean definitions hợp lệ, đúng scope/qualifier và được BeanFactory quản lý.

### Tài liệu Spring chính thức

- [Spring Framework 6.2 — `@Import` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Import.html).
- [Spring Framework 6.2 — `ImportSelector` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/ImportSelector.html).
- [Spring Framework 6.2 — `ImportBeanDefinitionRegistrar` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/ImportBeanDefinitionRegistrar.html).
- [Spring Framework — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
- [Spring Framework 6.2 — `@EnableCaching` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/cache/annotation/EnableCaching.html).
- [Spring Framework 6.2 — `@EnableAsync` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html).
- [Spring Framework 6.2 — `@EnableScheduling` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableScheduling.html).
- [Spring Framework 6.2 — `@EnableTransactionManagement` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html).
