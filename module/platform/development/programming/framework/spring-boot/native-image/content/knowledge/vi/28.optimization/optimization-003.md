# Giới hạn reflection, resource và proxy metadata theo nhu cầu đã kiểm chứng

## 1. Vì sao cần giới hạn metadata?

GraalVM Native Image phân tích ứng dụng ở build time và chỉ đóng gói những thành phần mà nó xác định là cần thiết. Khi ứng dụng dùng reflection, đọc resource theo tên hoặc tạo JDK dynamic proxy, static analysis có thể không suy ra đầy đủ hành vi. Khi đó, reachability metadata cho compiler biết chính xác class, member, resource hoặc tổ hợp interface nào cần được giữ lại.

Metadata là một phần của tính đúng đắn, không chỉ là cấu hình để làm build thành công. Nếu đăng ký thiếu, ứng dụng có thể chạy tốt trên JVM nhưng thất bại khi gọi một đường code trong native executable. Nếu đăng ký quá rộng, compiler có thể phải giữ thêm method, constructor, field, resource hoặc proxy không thực sự cần thiết. Điều đó làm tăng tập reachable, kích thước executable, thời gian phân tích/build và có thể cả bộ nhớ runtime.

Vì vậy, mục tiêu là **đăng ký đúng quyền truy cập mà code thực sự sử dụng, sau đó chứng minh bằng test và native execution**. Không nên thu nhỏ metadata theo cảm tính hoặc xóa một entry chỉ vì chưa thấy lỗi trong một lần chạy.

Sau bài học, bạn có thể:

- Chọn `MemberCategory` phù hợp với thao tác reflection thực tế.
- Thay wildcard resource rộng bằng pattern giới hạn theo thư mục, loại file hoặc feature.
- Đăng ký đúng từng tổ hợp JDK proxy và giữ thứ tự interface.
- Dùng hints có điều kiện cho dependency hoặc tính năng tùy chọn.
- Kiểm thử registrar bằng `RuntimeHintsPredicates` và xác minh trên native executable.
- Đánh giá tác động của metadata bằng build report, resource inventory và số đo trước/sau.

## 2. Hiểu đúng phạm vi của từng loại metadata

Spring `RuntimeHints` mô tả nhu cầu truy cập động của ứng dụng. Spring AOT có thể thu thập một số nhu cầu từ bean definitions, controller signatures, serialization/binding và các integration đã biết. Chỉ bổ sung thủ công phần AOT không thể suy ra.

| Loại metadata | Dùng khi | Ví dụ |
|---|---|---|
| Reflection | Code tra cứu class/member hoặc gọi constructor/method/field bằng reflection | `Class.getMethod`, `getDeclaredConstructor`, `Method.invoke` |
| Resource | Code tải file từ classpath bằng tên hoặc pattern động | Template, schema, file cấu hình, chứng thư, bundle |
| JDK proxy | Code tạo `Proxy.newProxyInstance` với danh sách interface xác định | Proxy triển khai `OrderOperations` và `Auditable` |

Ba loại này không thay thế lẫn nhau. Reflection hint không đưa file JSON vào image; resource hint không cho phép gọi method bằng reflection; proxy hint không đăng ký metadata cho mọi member của implementation class.

Native Image có thể nhận metadata qua Spring `RuntimeHints` được chuyển thành cấu hình native, qua `reachability-metadata.json` trong dependency hoặc qua metadata thu thập từ Tracing Agent. Khi một thư viện đã cung cấp metadata chính xác, tránh thêm bản sao ở ứng dụng nếu không có lý do.

## 3. Giới hạn reflection theo thao tác thực tế

### 3.1. Phân biệt introspection và invocation

Spring `MemberCategory` cho phép chọn quyền cần thiết. Hai nhóm thường gặp là:

- `INTROSPECT_*`: cho phép lấy thông tin constructor/method bằng reflection nhưng không đăng ký quyền gọi chúng.
- `INVOKE_*`: cho phép gọi constructor/method bằng reflection.

Một số category phổ biến:

| Category | Phạm vi |
|---|---|
| `INTROSPECT_PUBLIC_METHODS` | Tra cứu public methods, bao gồm method kế thừa |
| `INTROSPECT_DECLARED_METHODS` | Tra cứu methods được khai báo trên class, không gồm method kế thừa |
| `INVOKE_PUBLIC_METHODS` | Gọi public methods, bao gồm method kế thừa |
| `INVOKE_DECLARED_METHODS` | Gọi methods được khai báo trên class |
| `INTROSPECT_PUBLIC_CONSTRUCTORS` | Tra cứu public constructors |
| `INVOKE_PUBLIC_CONSTRUCTORS` | Gọi public constructors |
| `INVOKE_DECLARED_CONSTRUCTORS` | Gọi constructors được khai báo, kể cả non-public khi phù hợp |
| `PUBLIC_FIELDS` (Spring 6.x) / `ACCESS_PUBLIC_FIELDS` (Spring 7.x) | Truy cập public fields bằng reflection |
| `DECLARED_FIELDS` (Spring 6.x) / `ACCESS_DECLARED_FIELDS` (Spring 7.x) | Truy cập fields được khai báo trên class |

Chỉ chọn category tương ứng với API mà thư viện gọi. Nếu code chỉ gọi `getMethod()` để kiểm tra method có tồn tại, quyền introspection có thể đủ. Nếu code tiếp tục gọi `Method.invoke()`, cần invocation metadata.

**Khác biệt giữa Spring Framework 6.x và 7.x:** các category `INTROSPECT_*` và một số category introspection như `PUBLIC_CLASSES`/`DECLARED_CLASSES` đã deprecated for removal trong Spring 7.0 vì introspection được bao gồm mặc định khi thêm reflection hint cho type. `PUBLIC_FIELDS` và `DECLARED_FIELDS` được thay bằng `ACCESS_PUBLIC_FIELDS` và `ACCESS_DECLARED_FIELDS`. Khi hỗ trợ cả hai major version, ưu tiên đăng ký member cụ thể qua `TypeHint.Builder.withMethod(...)`/`withConstructor(...)` hoặc dùng category đúng với Spring version đang compile.

### 3.2. Ví dụ: đăng ký một method thay vì toàn bộ class

Giả sử một adapter legacy gọi method `code()` bằng reflection:

```java
package com.example.orders.plugin;

public class OrderPlugin {

    public String code() {
        return "orders";
    }
}
```

Đường code sử dụng reflection:

```java
package com.example.orders.plugin;

import java.lang.reflect.Method;

public class OrderPluginInvoker {

    public String invokeCode(OrderPlugin plugin) throws ReflectiveOperationException {
        Method method = OrderPlugin.class.getMethod("code");
        return (String) method.invoke(plugin);
    }
}
```

Registrar có thể khai báo đúng method cần gọi:

```java
package com.example.orders.plugin;

import java.util.List;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OrderPluginRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(OrderPlugin.class, typeHint ->
                typeHint.withMethod("code", List.of(), ExecutableMode.INVOKE));
    }
}
```

Ở đây chỉ method `code()` được đăng ký để invocation. Không cần bật toàn bộ constructors, fields và methods của `OrderPlugin` nếu ứng dụng không dùng chúng qua reflection.

Nếu thư viện thật sự cần tạo instance qua public no-argument constructor, bổ sung đúng constructor đó:

```java
hints.reflection().registerType(OrderPlugin.class, typeHint -> typeHint
        .withConstructor(List.of(), ExecutableMode.INVOKE)
        .withMethod("code", List.of(), ExecutableMode.INVOKE));
```

`ExecutableMode.INTROSPECT` phù hợp khi chỉ tra cứu executable; `ExecutableMode.INVOKE` phù hợp khi thực thi nó. Ví dụ này dùng API Spring Framework 6.x/7.x; luôn đối chiếu Javadoc với version Spring Framework mà dự án quản lý.

### 3.3. Khi nào mới dùng `MemberCategory` rộng?

Nếu thư viện thực sự gọi nhiều public methods của một kiểu, có thể đăng ký category:

```java
hints.reflection().registerType(
        OrderPlugin.class,
        MemberCategory.INVOKE_PUBLIC_METHODS);
```

Đây là một quyền rộng hơn đăng ký riêng `code()`. Chỉ dùng khi code path có thể gọi nhiều method public và danh sách method không thể mô tả hợp lý bằng hint từng member.

Không mặc định dùng các nhóm như `allDeclaredMethods`, `allDeclaredFields` hoặc toàn bộ constructors cho mọi DTO. Với JSON binding, Spring AOT và các annotation binding có thể đã tạo hints phù hợp; hãy kiểm tra output và native test trước khi thêm metadata trùng.

### 3.4. Chỉ đăng ký reflection khi class hiện diện

Một starter có thể hỗ trợ một thư viện tùy chọn. Dùng `registerTypeIfPresent` để không buộc dependency đó phải có mặt trong mọi ứng dụng:

```java
package com.example.orders.autoconfigure;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OptionalMapperRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerTypeIfPresent(
                classLoader,
                "com.vendor.optional.OrderMapper",
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS);
    }
}
```

`registerTypeIfPresent` kiểm tra class bằng class loader được truyền vào và chỉ đăng ký khi kiểu tồn tại. Nếu chỉ cần một constructor hoặc method, dùng overload nhận builder để thu hẹp member tương tự ví dụ trước.

## 4. Giới hạn resource patterns

### 4.1. Bắt đầu từ resource thực sự được tải

Giả sử ứng dụng chỉ tải template hóa đơn:

```text
src/main/resources/
  templates/
    orders/
      invoice.html
      receipt.html
    admin/
      dashboard.html
  i18n/
    orders/
      messages.properties
      messages_vi.properties
```

Nếu ứng dụng chỉ đọc `invoice.html`, đăng ký file đó:

```java
hints.resources().registerPattern("templates/orders/invoice.html");
```

Nếu một renderer thực sự tải cả bộ template đơn hàng, pattern có thể rộng hơn nhưng vẫn giới hạn theo thư mục:

```java
hints.resources().registerPattern("templates/orders/*.html");
```

Tránh đăng ký `**/*`, `templates/**` hoặc toàn bộ classpath chỉ để sửa một `MissingResourceException`. Resource metadata làm các file khớp pattern được đưa vào native executable, kể cả khi một phần nội dung không được dùng trong luồng chính.

### 4.2. Phân biệt wildcard của Spring và glob của GraalVM JSON

Spring `ResourcePatternHints` sử dụng include/exclude patterns; GraalVM `reachability-metadata.json` dùng trường `glob`. Quy tắc wildcard có khác biệt theo cơ chế và version. Trong JSON metadata hiện hành của GraalVM:

- `*` khớp các ký tự ở một cấp đường dẫn.
- `**` khớp qua nhiều cấp đường dẫn.
- Glob không được rỗng, không có slash cuối, không có chuỗi wildcard liên tiếp tùy ý.

Khi dùng Spring API, đọc Javadoc `ResourcePatternHint` của version đang chạy và viết pattern đủ hẹp. Không sao chép một pattern JSON sang Spring API mà chưa kiểm tra ý nghĩa.

### 4.3. Dùng `registerPatternIfPresent` cho resource tùy chọn

Nếu một module chỉ có ở một số ứng dụng, có thể kiểm tra một resource marker trước khi thêm pattern:

```java
hints.resources().registerPatternIfPresent(
        classLoader,
        "i18n/orders/messages.properties",
        resourceHint -> resourceHint.includes("i18n/orders/messages*.properties"));
```

Method này dùng `ClassLoader.getResource(location)` để kiểm tra location. Location kiểm tra không tự được đưa vào hint; pattern trong builder mới là tập resource được đăng ký. Chọn một marker file chắc chắn tồn tại trong module tùy chọn.

### 4.4. Resource bundle là một nhu cầu riêng

Nếu code dùng `ResourceBundle.getBundle("i18n.orders.messages")`, hãy đăng ký bundle base name:

```java
hints.resources().registerResourceBundle("i18n.orders.messages");
```

Không thay resource bundle hint bằng một wildcard rộng trên toàn bộ `*.properties`. Bundle có thể có nhiều locale; chỉ cấu hình các locale cần thiết nếu ứng dụng có chiến lược giới hạn locale ở build time.

### 4.5. Không phải mọi resource đều cần hint thủ công

Native Image có thể suy ra một số truy cập khi receiver và tên resource là hằng số, ví dụ `OrderTemplate.class.getResourceAsStream("invoice.html")`. Spring AOT cũng có thể nhận biết một số resource từ framework contract. Trước khi thêm hint, kiểm tra:

- Đường code dùng `Class.getResourceAsStream` với class và tên file cố định hay không.
- Resource có được thư viện hoặc Spring AOT đăng ký sẵn không.
- Resource được tải bằng tên tạo từ dữ liệu runtime hay không.
- File nằm trong classpath hay trên filesystem lúc chạy.

File trên filesystem như `/etc/orders/runtime.yml` không cần classpath resource hint; thay vào đó cần mount/copy file và cấu hình đường dẫn, quyền đọc phù hợp.

## 5. Giới hạn JDK proxy metadata

### 5.1. Mỗi tổ hợp interface là một proxy riêng

JDK dynamic proxy được định nghĩa bởi danh sách interface mà proxy triển khai. Đăng ký đúng tổ hợp mà code thực sự truyền cho `Proxy.newProxyInstance`:

```java
hints.proxies().registerJdkProxy(
        OrderOperations.class,
        Auditable.class);
```

Không đăng ký một proxy giả định chứa mọi interface của hệ thống. Nếu ứng dụng có hai tổ hợp:

```java
new Class<?>[] { OrderOperations.class, Auditable.class }
new Class<?>[] { PaymentOperations.class, Auditable.class }
```

hãy đăng ký hai tổ hợp riêng:

```java
hints.proxies().registerJdkProxy(
        OrderOperations.class,
        Auditable.class);

hints.proxies().registerJdkProxy(
        PaymentOperations.class,
        Auditable.class);
```

Đưa các lệnh này vào registrar của module proxy:

```java
package com.example.orders.proxy;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class OrderProxyRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.proxies().registerJdkProxy(
                OrderOperations.class,
                Auditable.class);
        hints.proxies().registerJdkProxy(
                PaymentOperations.class,
                Auditable.class);
    }
}
```

### 5.2. Giữ đúng thứ tự interface

Thứ tự interface là một phần của proxy definition. `[OrderOperations, Auditable]` khác `[Auditable, OrderOperations]`. Nếu code có thể tạo cả hai thứ tự, đăng ký cả hai; nếu chỉ dùng một, giữ nguyên thứ tự trong factory và registrar.

Không thêm một interface chỉ vì nó có mặt trong class hierarchy của target. Hãy ghi lại chính xác array truyền vào `Proxy.newProxyInstance`, bao gồm các interface marker như `Serializable` nếu runtime thật sự dùng chúng.

### 5.3. Phân biệt JDK proxy với class-based proxy

`registerJdkProxy(...)` dành cho JDK interface proxy. Nó không đăng ký tùy ý mọi subclass do CGLIB/Byte Buddy tạo. Proxy do Spring AOP quản lý có thể được Spring AOT phân tích và chuẩn bị. Trước khi thêm hints thủ công, kiểm tra proxy thực tế được tạo bởi Spring AOP, JDK `Proxy` hay thư viện class-generation riêng.

Nếu proxy tùy chỉnh tạo động từ interface list runtime, hãy giới hạn tập tổ hợp có thể xuất hiện tại build time. Nếu danh sách interface hoàn toàn tùy ý sau khi triển khai, vấn đề đó vượt quá việc thêm một proxy hint rộng.

## 6. Tổ chức hints theo feature và dependency sở hữu

### 6.1. Gắn registrar gần component cần hints

```java
package com.example.orders.plugin;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(OrderPluginRuntimeHints.class)
public class OrderPluginConfiguration {
}
```

Đặt `@ImportRuntimeHints` gần component sử dụng metadata. Spring Framework khuyến nghị cách này để nếu component không được đóng góp vào `BeanFactory`, hints của component đó cũng không được đóng góp. Điều này giúp hints đi cùng lifecycle của feature thay vì tồn tại toàn cục dù feature đã bị loại.

### 6.2. Tách registrar theo feature

Ví dụ một module đơn hàng có thể chia:

```text
orders/
  plugin/
    OrderPluginRuntimeHints.java
  templates/
    OrderTemplateRuntimeHints.java
  proxy/
    OrderProxyRuntimeHints.java
```

Mỗi registrar chỉ quản lý phần metadata của component sở hữu. Cách chia này giúp reviewer biết vì sao một class, resource hoặc proxy được giữ lại và dễ xóa hints khi feature không còn.

### 6.3. Đăng ký resource có điều kiện theo feature

Spring resource pattern builder cho phép gắn `reachableType` vào pattern:

```java
import org.springframework.aot.hint.TypeReference;

hints.resources().registerPattern(resourceHint ->
        resourceHint.includes(
                TypeReference.of(OrderExportFeature.class),
                "templates/orders/export/*.html"));
```

Pattern chỉ áp dụng khi type đại diện cho feature được reach. Đây là cách giới hạn tài nguyên tùy chọn theo feature khi dùng Spring RuntimeHints API.

Trong Spring API, `reachableType` là điều kiện reachability được xét ở build time bởi static analysis. Nó không đồng nghĩa với `condition.typeReached` trong GraalVM JSON, vốn quyết định thời điểm metadata có hiệu lực trong runtime.

## 7. Conditional reachability metadata trong GraalVM

### 7.1. Khi nào dùng `typeReached`?

Reachability metadata JSON hỗ trợ `condition.typeReached`. Entry chỉ có hiệu lực khi type được chỉ định được reach trong runtime. Điều này hữu ích khi metadata thuộc một integration tùy chọn hoặc một feature chỉ được bật khi type tương ứng được kích hoạt.

Ví dụ file `META-INF/native-image/com.example/orders/reachability-metadata.json`:

```json
{
  "reflection": [
    {
      "condition": {
        "typeReached": "com.example.orders.export.OrderExportFeature"
      },
      "type": "com.example.orders.export.LegacyOrderFormatter",
      "methods": [
        {
          "name": "format",
          "parameterTypes": ["com.example.orders.Order"]
        }
      ]
    }
  ],
  "resources": [
    {
      "condition": {
        "typeReached": "com.example.orders.export.OrderExportFeature"
      },
      "glob": "templates/orders/export/*.html"
    }
  ]
}
```

Đặt metadata trong thư mục `META-INF/native-image/<groupId>/<artifactId>/` trên classpath. Ví dụ dùng schema reachability metadata hiện hành của GraalVM; với version cũ, schema và tên condition có thể khác.

### 7.2. Điều kiện không phải một cờ cấu hình tùy ý

`typeReached` không có nghĩa là property `orders.export.enabled=true`. GraalVM xét type được reach trong quá trình runtime/class initialization. Class literal đơn thuần không nhất thiết làm type được đánh dấu reached; class initialization hoặc subtype reach có ý nghĩa theo quy tắc GraalVM.

Entry có điều kiện vẫn có thể ảnh hưởng kích thước image nếu condition type được reach tại build time. Khi type được reach lúc chạy, metadata mới trở nên khả dụng. Vì vậy, conditional metadata giúp giới hạn phạm vi kích hoạt và tránh cấp quyền động trước khi feature xuất hiện; nó không bảo đảm mọi entry đều miễn phí về kích thước.

### 7.3. Chọn Spring RuntimeHints hay JSON metadata

| Trường hợp | Cách phù hợp |
|---|---|
| Metadata thuộc Spring bean/feature của ứng dụng | `RuntimeHintsRegistrar` và `@ImportRuntimeHints` |
| Thư viện độc lập cung cấp metadata cho mọi ứng dụng dùng nó | `reachability-metadata.json` trong artifact của thư viện |
| Cần metadata có điều kiện theo type reach | Conditional entry `typeReached` trong JSON hoặc Spring hint builder có điều kiện phù hợp |
| Một resource/class tùy chọn có thể vắng mặt trên classpath | `registerPatternIfPresent` hoặc `registerTypeIfPresent` |
| Metadata do framework đã tự suy ra | Không thêm bản sao nếu test xác nhận đã đủ |

## 8. Kiểm thử từng nhóm metadata

### 8.1. Test reflection hint

`RuntimeHintsPredicates` cho phép xác minh registrar đã đăng ký quyền gọi method cụ thể:

```java
package com.example.orders.plugin;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class OrderPluginRuntimeHintsTests {

    @Test
    void registersOnlyTheRequiredPluginMethod() {
        RuntimeHints hints = new RuntimeHints();
        new OrderPluginRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.reflection()
                .onMethod(OrderPlugin.class, "code")
                .invoke())
                .accepts(hints);
    }
}
```

Predicate xác nhận hint đã được đăng ký. Nó không chứng minh code path gọi method đúng hoặc tất cả reflection khác trong ứng dụng đều được khai báo.

### 8.2. Test resource pattern

```java
package com.example.orders.templates;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class OrderTemplateRuntimeHintsTests {

    @Test
    void registersTheInvoiceTemplate() {
        RuntimeHints hints = new RuntimeHints();
        new OrderTemplateRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.resource()
                .forResource("templates/orders/invoice.html"))
                .accepts(hints);
    }
}
```

Nên kiểm tra một resource thực tế mà ứng dụng tải, không chỉ kiểm tra pattern string. Nếu pattern bao phủ quá nhiều file, hãy review số lượng resource thực tế được embed trong image.

### 8.3. Test proxy interface list

```java
package com.example.orders.proxy;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class OrderProxyRuntimeHintsTests {

    @Test
    void registersTheExpectedOrderedProxyInterfaces() {
        RuntimeHints hints = new RuntimeHints();
        new OrderProxyRuntimeHints().registerHints(
                hints, getClass().getClassLoader());

        assertThat(RuntimeHintsPredicates.proxies()
                .forInterfaces(OrderOperations.class, Auditable.class))
                .accepts(hints);
    }
}
```

Predicate proxy kiểm tra cả thứ tự interface. Nếu factory tạo `[Auditable, OrderOperations]`, test trên phải fail cho đến khi registrar và factory được đồng bộ.

### 8.4. Kiểm thử native với missing-registration reporting

Unit test predicate kiểm tra metadata Spring đã khai báo. Native executable mới xác nhận các thao tác động thật sự hoạt động. Với GraalVM JDK 23 trở lên, bật exact reachability metadata khi build:

```bash
native-image --exact-reachability-metadata -jar target/order-service.jar order-service
```

Chạy executable ở chế độ cảnh báo để tìm các vị trí thiếu registration:

```bash
./order-service -XX:MissingRegistrationReportingMode=Warn
```

Trong integration test, dùng `Exit` để phát hiện cả lỗi metadata bị code bắt và bỏ qua:

```bash
./order-service -XX:MissingRegistrationReportingMode=Exit
```

Nếu chỉ muốn bật kiểm tra cho một package, có thể dùng `--exact-reachability-metadata=com.example.orders`. Với GraalVM trước JDK 23, tên build option và missing-registration reporting có thể khác; kiểm tra tài liệu version đang dùng.

## 9. Dùng Tracing Agent nhưng không giữ nguyên mọi thứ nó ghi nhận

GraalVM Native Image Tracing Agent quan sát reflection, resource, proxy và các thao tác động trong lần chạy JVM. Metadata sinh ra là bằng chứng về những gì đã xảy ra trong các kịch bản đó, không phải bản cấu hình tối thiểu tự động.

Quy trình review:

1. Chạy agent với các kịch bản nghiệp vụ đã chọn.
2. Gộp output từ nhiều profile hoặc integration.
3. Nhóm entry theo thư viện/feature sở hữu.
4. So sánh với hints Spring AOT đã tạo và metadata do dependency cung cấp.
5. Loại entry chỉ thuộc test harness, tooling hoặc code path không có trong production.
6. Thu hẹp reflection xuống member cần thiết, resource xuống path cần đọc và proxy xuống tổ hợp interface thực tế.
7. Chạy exact reachability metadata và native integration test sau khi thu hẹp.

Không xóa entry chỉ vì một lần tracing không ghi nhận nó. Nếu tính năng tùy chọn chưa được chạy, agent không thể biết metadata của tính năng đó. Trước khi loại một entry, cần có test chứng minh feature không dùng nó hoặc một native test bao phủ feature sau khi thay đổi.

## 10. Đo ảnh hưởng của metadata

### 10.1. Đo trên cùng một điều kiện build

Tạo baseline và bản đã tối ưu với cùng:

- GraalVM distribution và JDK version.
- Spring Boot/Spring Framework/dependency versions.
- OS, kiến trúc CPU và native build flags.
- Source code nghiệp vụ và cấu hình build khác biệt duy nhất là metadata được thử nghiệm.

Ghi lại ít nhất:

| Chỉ số | Ý nghĩa |
|---|---|
| Native executable size | Tổng kích thước file được tạo |
| Native build duration | Chi phí phân tích và biên dịch |
| Startup time | Thời gian từ lúc chạy process đến khi readiness `UP` |
| RSS sau warm-up | Bộ nhớ resident trong workload đại diện |
| Embedded resource count/size | Tập file được đưa vào executable |
| Reflection/proxy errors | Độ đúng sau khi thu hẹp metadata |

### 10.2. Kiểm tra embedded resources

GraalVM có thể xuất build report:

```bash
native-image --emit build-report -jar target/order-service.jar order-service
```

Trong build report, xem mục Resources để kiểm tra các file đã được đưa vào image. Có thể tạo danh sách JSON tài nguyên nhúng bằng:

```bash
native-image -H:+GenerateEmbeddedResourcesFile -jar target/order-service.jar order-service
```

File `embedded-resources.json` giúp đối chiếu các resource theo tên, nguồn gốc và kích thước. Dùng báo cáo này để xác nhận một pattern hẹp thực sự loại được file không cần thiết.

### 10.3. Đừng kết luận từ một số đo đơn lẻ

Một thay đổi metadata có thể làm executable nhỏ hơn nhưng build time thay đổi ít; hoặc giảm số resource nhưng không ảnh hưởng đáng kể RSS. Hãy đo nhiều lần, dùng cùng workload và so sánh theo baseline. Quan trọng nhất là giữ toàn bộ test chức năng pass sau khi thu hẹp.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Native báo thiếu method dù class đã có reflection hint | Hint chỉ cho introspection, code thực hiện invocation | Đổi sang `INVOKE_*` hoặc `ExecutableMode.INVOKE` cho đúng member |
| Thêm `INVOKE_PUBLIC_METHODS` nhưng vẫn lỗi constructor | Constructor chưa được đăng ký | Thêm đúng constructor cần gọi; không bật toàn bộ constructors nếu không cần |
| Đăng ký `allDeclaredMethods` làm image lớn hơn | Nhiều method không cần thiết trở thành reachable | Thay bằng member cụ thể hoặc category hẹp hơn |
| Template không tìm thấy trên native | Resource pattern sai hoặc resource chưa được giữ | Kiểm tra classpath path, pattern, build report và `embedded-resources.json` |
| Đăng ký `**/*` để sửa một file thiếu | Pattern quá rộng | Đăng ký exact path hoặc thư mục/extension nhỏ nhất đủ dùng |
| Optional dependency không có trên classpath làm AOT thất bại | Registrar tham chiếu class tùy chọn trực tiếp | Dùng `registerTypeIfPresent` và `registerPatternIfPresent` |
| Proxy chạy JVM nhưng native báo thiếu proxy | Chưa đăng ký đúng JDK interface combination hoặc thứ tự | Ghi lại array runtime và đăng ký cùng thứ tự bằng `registerJdkProxy` |
| Đã đăng ký JDK proxy nhưng CGLIB vẫn lỗi | Hint không đúng loại proxy | Kiểm tra proxy factory và để Spring AOT xử lý class-based proxy khi có thể |
| Tracing Agent tạo nhiều entry hơn cần thiết | Chạy nhiều framework/test path hoặc thiếu filter | Review theo owner, loại test-only entry và thu hẹp trước khi commit |
| Xóa hint làm test JVM vẫn pass nhưng native fail | JVM không cần metadata native; test chưa chạy code path động | Dùng exact reachability metadata và native integration test |
| Conditional entry không được áp dụng | Condition type chưa reached theo quy tắc GraalVM | Kiểm tra typeReached, class initialization và luồng kích hoạt feature |

## 12. Bài thực hành: thu hẹp metadata cho order-service

**Bối cảnh:** `order-service` dùng reflection để gọi `OrderPlugin.code()`, tải template `templates/orders/invoice.html` và tạo proxy gồm `OrderOperations` cùng `Auditable`. Tracing Agent đã ghi thêm một số method, resource và proxy không cần thiết.

### Bước 1 — Lập bảng nhu cầu thực tế

Ghi lại chính xác:

- Reflection: class nào, constructor nào, method nào được tra cứu và method nào được gọi.
- Resource: file nào được tải, có resource bundle không, path nào được tạo từ dữ liệu runtime.
- Proxy: array interface được truyền vào `Proxy.newProxyInstance`, theo đúng thứ tự.

### Bước 2 — Viết registrar hẹp

Tạo ba registrar hoặc một registrar theo feature, chỉ đăng ký method `code`, file invoice và proxy `[OrderOperations, Auditable]`. Nếu module export là tùy chọn, dùng conditional hints.

### Bước 3 — Viết predicate tests

Viết `RuntimeHintsPredicates` cho method reflection, resource invoice và proxy interface list. Bảo đảm test fail nếu registrar bị mở rộng hoặc factory đổi thứ tự proxy.

### Bước 4 — Chạy Tracing Agent và review

Chạy các luồng tạo đơn và xuất hóa đơn. So sánh output agent với registrar đã viết. Giữ metadata của feature tùy chọn nếu feature đó được yêu cầu trong production, dù một lần chạy agent không đi qua nó.

### Bước 5 — Build native với exact metadata

Build executable với `--exact-reachability-metadata`, chạy `Warn` để phát hiện thiếu registration và chạy native integration test cho cả ba hành vi. Sau khi không còn lỗi, chạy `Exit` trong CI.

### Bước 6 — So sánh kết quả

Ghi executable size, build time, startup-to-readiness, RSS và resource inventory trước/sau. Nếu số đo không thay đổi đáng kể, vẫn giữ metadata hẹp hơn khi nó phản ánh đúng hợp đồng runtime và test chứng minh tính đúng đắn.

### Phiếu kết quả

| Hạng mục | Baseline | Sau tối ưu |
|---|---|---|
| Reflection entries/members | _(ghi)_ | _(ghi)_ |
| Resource patterns/files | _(ghi)_ | _(ghi)_ |
| JDK proxy combinations | _(ghi)_ | _(ghi)_ |
| Executable size | _(ghi)_ | _(ghi)_ |
| Build duration | _(ghi)_ | _(ghi)_ |
| Startup-to-readiness | _(ghi)_ | _(ghi)_ |
| RSS sau warm-up | _(ghi)_ | _(ghi)_ |
| Exact metadata/native tests | PASS/FAIL | PASS/FAIL |

## 13. Ghi nhớ

Reflection metadata nên mô tả đúng member được tra cứu hoặc gọi; resource metadata nên giới hạn theo file, thư mục và bundle thực sự được dùng; proxy metadata nên mô tả đúng từng tổ hợp interface theo đúng thứ tự. Dùng `registerTypeIfPresent` và `registerPatternIfPresent` cho dependency tùy chọn, gắn registrar gần component sở hữu và sử dụng `typeReached` khi metadata JSON chỉ cần có hiệu lực cùng một feature.

`RuntimeHintsPredicates` giúp test hợp đồng metadata của Spring; GraalVM exact reachability metadata cùng `MissingRegistrationReportingMode` giúp tìm lỗi trên executable native. Tracing Agent hỗ trợ khám phá nhưng output cần được review. Chỉ coi việc thu hẹp metadata là hoàn tất khi các đường code thực tế vẫn chạy trên native và số đo trước/sau được thực hiện trong cùng điều kiện.

### Tài liệu tham khảo chính thức

- [Spring Framework — Ahead-of-Time Optimizations and Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Framework 6.2 — `ReflectionHints` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/ReflectionHints.html)
- [Spring Framework 6.2 — `MemberCategory` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/MemberCategory.html)
- [Spring Framework 6.2 — `ResourceHints` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/ResourceHints.html)
- [Spring Framework 6.2 — `ProxyHints` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/ProxyHints.html)
- [Spring Framework 6.2 — `RuntimeHintsPredicates` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/predicate/RuntimeHintsPredicates.html)
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM — Troubleshoot Native Image Run-Time Errors](https://www.graalvm.org/latest/reference-manual/native-image/guides/troubleshoot-run-time-errors/)
