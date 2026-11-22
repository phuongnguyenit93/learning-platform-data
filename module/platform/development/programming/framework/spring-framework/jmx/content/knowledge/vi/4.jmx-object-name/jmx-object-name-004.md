# Tránh xung đột tên giữa nhiều bean hoặc nhiều ứng dụng trong JMX

## 1. Bài toán: vì sao ObjectName bị trùng?

Trong Java Management Extensions (**JMX**), mỗi MBean được đăng ký vào một `MBeanServer` dưới một **`ObjectName`**. `ObjectName` đóng vai trò định danh duy nhất của MBean trong phạm vi MBeanServer đó.

Một ứng dụng có thể có nhiều Spring bean cùng loại, nhiều application context trong một JVM, hoặc nhiều module cùng xuất MBean. Nếu tất cả đều đăng ký bằng tên chung:

```text
com.example:type=CacheManager
```

thì bean đầu tiên đăng ký thành công, còn bean tiếp theo với cùng `ObjectName` có thể gặp:

```text
javax.management.InstanceAlreadyExistsException:
com.example:type=CacheManager
```

Trùng tên không có nghĩa Java object hay Spring bean name trùng nhau. **Spring bean name** được quản lý trong Spring `ApplicationContext`; còn **JMX ObjectName** được quản lý trong `MBeanServer`. Hai không gian tên này độc lập và có quy tắc riêng.

### Phạm vi duy nhất

- Trong **cùng MBeanServer**, hai MBean không thể cùng tồn tại với một `ObjectName` chính xác giống nhau.
- Trong **các MBeanServer khác nhau**, một `ObjectName` có thể xuất hiện ở cả hai server mà không tự gây `InstanceAlreadyExistsException`.
- Trong **hai tiến trình JVM riêng**, việc dùng cùng `ObjectName` thường không xung đột trực tiếp nếu chúng có MBeanServer riêng. Tuy nhiên, hệ thống giám sát tập trung vẫn cần nhận diện rõ tiến trình/instance để không gộp sai nguồn dữ liệu.
- Nhiều Spring `ApplicationContext` trong cùng JVM có thể cùng dùng **platform MBeanServer**, vì vậy vẫn có nguy cơ trùng tên dù context khác nhau.

Mục tiêu là thiết kế tên **ổn định, dễ truy vấn, đủ phân biệt các thực thể cần quản trị**, đồng thời có chính sách rõ ràng cho đăng ký trùng.

## 2. Cấu trúc ObjectName cần nắm vững

`ObjectName` có cú pháp khái quát:

```text
domain:key1=value1,key2=value2,...
```

Ví dụ:

```text
com.example.orders:type=Queue,name=payment
com.example.orders:type=Queue,name=shipping
com.example.cache:type=CacheManager,name=primary
```

**Domain** thường thể hiện namespace của ứng dụng hoặc tổ chức. **Key properties** mô tả loại tài nguyên và định danh cụ thể.

Một số quy tắc:

1. `domain` và bộ key properties cấu thành danh tính của ObjectName; không chỉ riêng `name` quyết định trùng hay không.
2. Thứ tự key trong chuỗi đầu vào không làm thay đổi định danh. Ví dụ `domain:type=Cache,name=main` và `domain:name=main,type=Cache` biểu diễn cùng ObjectName.
3. Hai key property có cùng tên trong một ObjectName là không hợp lệ.
4. Những ký tự đặc biệt trong value, ví dụ dấu phẩy, dấu hai chấm, dấu bằng, dấu ngoặc kép, dấu sao và dấu hỏi, cần xử lý theo cú pháp ObjectName. Với giá trị tùy ý, dùng `ObjectName.quote(value)` để escape đúng khi xây dựng giá trị có quote.
5. `*` và `?` có thể mang ý nghĩa pattern trong ObjectName. Đừng vô ý tạo pattern khi mục đích là đăng ký một MBean có tên cụ thể.
6. MBean phải được đăng ký với ObjectName không có tính chất pattern; pattern hữu ích cho thao tác `queryNames`.

### Cách xây tên bằng Java

```java
import javax.management.ObjectName;
import java.util.Hashtable;

public final class JmxNames {
    private JmxNames() {}

    public static ObjectName cache(
            String application,
            String cacheName
    ) throws Exception {
        Hashtable<String, String> properties = new Hashtable<>();
        properties.put("type", "Cache");
        properties.put("application", application);
        properties.put("name", cacheName);
        return new ObjectName("com.example.management", properties);
    }
}
```

Với các giá trị đã được kiểm soát theo chuẩn đặt tên (chữ, số, dấu gạch nối, dấu gạch dưới), cách tạo bằng key properties thuận tiện. Nếu dữ liệu tùy ý có ký tự đặc biệt, cần xây dựng giá trị được quote đúng hoặc giới hạn về mã định danh hợp lệ trước khi tạo ObjectName; không ghép trực tiếp chuỗi dữ liệu không tin cậy.

Ví dụ pattern để tìm các cache:

```java
import javax.management.MBeanServer;
import javax.management.ObjectName;
import java.lang.management.ManagementFactory;
import java.util.Set;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

Set<ObjectName> caches = server.queryNames(
    new ObjectName("com.example.management:type=Cache,*"),
    null
);

for (ObjectName name : caches) {
    System.out.println(name.getCanonicalName());
}
```

`getCanonicalName()` hữu ích để ghi log và so sánh tên theo thứ tự key chuẩn hóa.

## 3. Xung đột phổ biến khi có nhiều bean trong một ứng dụng

Giả sử có hai bean cùng loại:

```java
@Bean
CacheService productCache() {
    return new CacheService("product");
}

@Bean
CacheService customerCache() {
    return new CacheService("customer");
}
```

Nếu cả hai đều xuất dưới:

```text
com.example:type=CacheService
```

thì MBeanServer không thể phân biệt bean nào đang được quản lý.

Tên phù hợp hơn là:

```text
com.example.cache:type=CacheService,name=product
com.example.cache:type=CacheService,name=customer
```

Với hệ thống có nhiều application context cùng dùng một server, có thể cần thêm `context` hoặc `application`:

```text
com.example.cache:type=CacheService,application=storefront,name=product
com.example.cache:type=CacheService,application=backoffice,name=product
```

Chỉ thêm các chiều thực sự cần để phân biệt. Nếu tạo một MBean mới cho từng request hoặc từng user, registry sẽ có cardinality rất lớn, gây tốn bộ nhớ và khó quản trị. MBean nên đại diện cho tài nguyên có lifecycle tương đối ổn định.

## 4. Xung đột giữa nhiều ứng dụng cùng JVM

Trong một JVM có nhiều module hoặc nhiều `ApplicationContext`, dùng domain quá tổng quát như `app`, `spring` hoặc `monitoring` dễ dẫn tới va chạm.

Một chiến lược thiết kế:

```text
<namespace>:type=<ResourceType>,application=<AppId>,name=<ResourceId>
```

Ví dụ:

```text
com.acme.platform:type=ThreadPool,application=checkout,name=async
com.acme.platform:type=ThreadPool,application=inventory,name=async
com.acme.platform:type=DataSource,application=checkout,name=primary
```

Nên quy định rõ:

| Thành phần tên | Mục đích | Ví dụ |
| --- | --- | --- |
| Domain | Namespace của tổ chức hoặc sản phẩm | `com.acme.platform` |
| `type` | Nhóm tài nguyên | `Cache`, `ThreadPool`, `DataSource` |
| `application` | Dịch vụ hoặc ứng dụng sở hữu | `checkout`, `inventory` |
| `context` | Phân biệt Spring context nếu thật sự cần | `root`, `admin` |
| `name` | Định danh tài nguyên ổn định | `primary`, `scheduler` |
| `instance` | Phân biệt replica khi chúng thực sự chung một MBeanServer | `worker-1` |

Không nên bắt buộc `instance` là UUID ngẫu nhiên trong mọi môi trường. UUID thay đổi mỗi lần khởi động làm mất tính ổn định của các query và dashboard. Nếu mỗi replica chạy trong JVM riêng, thông thường chỉ cần hệ thống monitoring gắn nhãn instance ở tầng thu thập; không nhất thiết đưa replica ID vào `ObjectName`.

### Nguyên tắc quan trọng

**Giữ tên MBean ổn định trong một instance, còn phân biệt các instance khác nhau ở tầng giám sát khi phù hợp.** Cách này giúp truy vấn JMX đơn giản và tránh sinh quá nhiều tên biến động.

## 5. Các chính sách xử lý tên trùng

Khi `MBeanServer.registerMBean(mbean, objectName)` gặp tên đã tồn tại, thao tác thường phát sinh `InstanceAlreadyExistsException`. Với Spring Framework, `MBeanExporter` hỗ trợ chính sách xử lý va chạm tên, tùy phiên bản Spring đang sử dụng.

Ba lựa chọn khái niệm thường gặp:

| Chính sách | Ý nghĩa | Trường hợp |
| --- | --- | --- |
| Fail/error | Từ chối đăng ký tên trùng; phát hiện cấu hình sai | Hệ thống cần hợp đồng định danh chặt chẽ |
| Ignore | Giữ MBean hiện có, bỏ qua lần đăng ký trùng | Có nhiều context vô tình export cùng một MBean hệ thống và đã xác định rõ chủ sở hữu |
| Replace | Gỡ MBean hiện có và đăng ký MBean mới | Chỉ khi lifecycle và ownership được xác định chắc chắn |

**Không nên chọn replace như cách chữa lỗi đặt tên mặc định.** Một module có thể xóa MBean thuộc module khác, khiến client giữ tham chiếu hoặc subscription sai, hoặc làm biến mất trạng thái quản trị trong lúc ứng dụng chạy.

### 5.1. Mặc định ưu tiên phát hiện sớm

Đối với MBean do ứng dụng tự quản lý, fail khi trùng thường giúp phát hiện sai cấu hình và tránh bị che khuất.

### 5.2. Ignore cần có lý do rõ ràng

Ignore có thể giúp một thành phần không đăng ký lại MBean chung nếu đã có chủ thể khác đăng ký. Nhưng nếu hai bean có nghiệp vụ khác nhau, ignore khiến một bean bị mất khả năng quản trị mà không tạo tên riêng.

### 5.3. Replace đòi hỏi ownership

Nếu một context gỡ MBean do context khác đăng ký, khi context cũ dừng có thể xảy ra xung đột lifecycle. Chỉ replace khi chính sách quản lý ownership bảo đảm thao tác đó là chủ ý.

## 6. Spring Framework: đặt ObjectName tường minh

Spring Framework cung cấp `MBeanExporter` để xuất bean sang JMX.

Ví dụ cấu hình Java:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.export.MBeanExporter;
import org.springframework.jmx.support.RegistrationPolicy;

import java.util.LinkedHashMap;
import java.util.Map;

@Configuration
public class JmxExportConfiguration {

    @Bean
    public MBeanExporter applicationMBeanExporter(
            ProductCacheAdmin productCacheAdmin,
            CustomerCacheAdmin customerCacheAdmin
    ) {
        MBeanExporter exporter = new MBeanExporter();

        Map<String, Object> beans = new LinkedHashMap<>();
        beans.put(
            "com.acme.shop:type=Cache,application=storefront,name=product",
            productCacheAdmin
        );
        beans.put(
            "com.acme.shop:type=Cache,application=storefront,name=customer",
            customerCacheAdmin
        );

        exporter.setBeans(beans);
        exporter.setRegistrationPolicy(
            RegistrationPolicy.FAIL_ON_EXISTING
        );
        return exporter;
    }
}
```

Đây là ví dụ về chính sách naming và export. `ProductCacheAdmin` và `CustomerCacheAdmin` là các lớp minh họa chưa được định nghĩa trong snippet; trong ứng dụng thực cần là các MBean phù hợp hoặc được kết hợp với assembler phù hợp để tạo interface JMX.

Các giá trị `RegistrationPolicy` thường gồm:

- `FAIL_ON_EXISTING`: phát sinh lỗi nếu MBean đã tồn tại.
- `IGNORE_EXISTING`: bỏ qua đăng ký khi tên đã tồn tại.
- `REPLACE_EXISTING`: thay MBean đã có bằng MBean mới.

Chọn `FAIL_ON_EXISTING` cho các MBean thuộc application nếu chưa có lý do chính thức để share một ObjectName.

## 7. Spring @ManagedResource và nguy cơ trùng tên

Spring hỗ trợ export MBean dựa trên annotation như `@ManagedResource`, `@ManagedAttribute`, `@ManagedOperation`.

```java
import org.springframework.jmx.export.annotation.ManagedAttribute;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.acme.shop:type=Cache,name=product",
    description = "Product cache management"
)
public class ProductCacheAdmin {

    private volatile int entryCount;

    @ManagedAttribute
    public int getEntryCount() {
        return entryCount;
    }
}
```

Nếu một lớp được dùng làm nhiều bean và tất cả cùng lấy `objectName` cố định từ annotation, việc xuất nhiều instance có thể gây trùng.

Các hướng giải quyết:

1. **Một instance duy nhất:** đảm bảo chỉ một bean được export dưới tên annotation cố định.
2. **Nhiều instance cần quản trị riêng:** cấu hình tên riêng cho từng instance qua exporter/naming strategy phù hợp.
3. **Nhiều application context:** quy định context nào sở hữu MBean hoặc thêm định danh context nếu mỗi context phải export.
4. **Component dùng chung:** tránh đưa định danh service cố định vào thư viện được tái sử dụng; cho ứng dụng cung cấp namespace riêng.

Annotation không tự bảo đảm tên duy nhất cho mỗi instance. Cần kiểm tra cách `AnnotationMBeanExporter` và naming strategy hoạt động trong cấu hình thực tế.

## 8. ObjectNamingStrategy và KeyNamingStrategy

Spring `ObjectNamingStrategy` cung cấp điểm mở rộng để xác định `ObjectName` cho một bean. Đây là vị trí phù hợp để thực hiện chính sách naming đồng nhất.

Một số chiến lược phổ biến:

- **MetadataNamingStrategy:** dựa vào metadata JMX (ví dụ annotation) và chiến lược fallback phù hợp.
- **KeyNamingStrategy:** dùng ánh xạ từ bean key sang ObjectName hoặc sử dụng định dạng tên theo quy tắc cấu hình.
- **Chiến lược tùy chỉnh:** implements `ObjectNamingStrategy` và xây `ObjectName` dựa trên namespace, resource type và bean key.

Ví dụ implementation tùy chỉnh:

```java
import org.springframework.jmx.export.naming.ObjectNamingStrategy;
import javax.management.MalformedObjectNameException;
import javax.management.ObjectName;

public final class ApplicationObjectNamingStrategy
        implements ObjectNamingStrategy {

    private final String application;

    public ApplicationObjectNamingStrategy(String application) {
        this.application = application;
    }

    @Override
    public ObjectName getObjectName(Object managedBean, String beanKey)
            throws MalformedObjectNameException {
        String type = managedBean.getClass().getSimpleName();

        return new ObjectName(
            "com.acme.management:type=" + ObjectName.quote(type)
                + ",application=" + ObjectName.quote(application)
                + ",name=" + ObjectName.quote(beanKey)
        );
    }
}
```

Chiến lược trên minh họa cách đưa `application` và `beanKey` vào tên. Trong hệ thống thật, cần kiểm soát tính ổn định của bean key, proxy class và cú pháp ObjectName. Khi Spring AOP tạo proxy, `managedBean.getClass().getSimpleName()` có thể mang tên lớp proxy thay vì lớp nghiệp vụ. Nếu phải ổn định qua thay đổi proxy, lấy **resource type từ metadata hoặc cấu hình ổn định** thay cho tên lớp runtime.

`ObjectName.quote` giúp escape giá trị trong cú pháp ObjectName; tránh ghép giá trị người dùng trực tiếp nếu không được xử lý.

## 9. Tránh tên biến động do proxy, profile và runtime

### 9.1. Proxy của Spring

Bean có thể được bao bởi proxy khi dùng AOP, transaction hoặc scoped proxy. Nếu thuật toán đặt tên dùng trực tiếp tên class runtime, tên MBean có thể thay đổi sau khi thêm advice. Tốt hơn nên dùng:

```text
domain=namespace cố định
type=tên tài nguyên nghiệp vụ
application=ID dịch vụ ổn định
name=ID bean/resource ổn định
```

### 9.2. Profile và môi trường

Trong môi trường tách JVM, cùng ObjectName giữa dev, staging và production không nhất thiết gây va chạm tại MBeanServer. Tầng monitoring nên gắn nhãn environment/cluster. Chỉ đưa môi trường vào ObjectName nếu nhiều môi trường thực sự chia sẻ server/namespace và cần tách riêng tại đó.

### 9.3. Nhiều Spring context

Một ứng dụng web có parent context và child context hoặc nhiều deployment trong cùng container. Các context có thể dùng cùng platform MBeanServer. Cần:

- Một exporter có ownership rõ ràng.
- Namespace theo context khi mỗi context cần MBean độc lập.
- Chính sách đăng ký/hủy đăng ký tương ứng với lifecycle từng context.

Không nên đặt `REPLACE_EXISTING` ở mọi context vì có thể khiến context khởi động sau thay MBean của context trước.

## 10. Vòng đời đăng ký và hủy đăng ký MBean

Định danh nhất quán mới giải quyết một nửa vấn đề. Một MBean có thể bị bỏ lại nếu quá trình shutdown hoặc hot reload không hủy đăng ký đúng, làm lần triển khai tiếp theo gặp xung đột.

Các thao tác cơ bản:

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class JmxLifecycle {
    public static void unregisterIfOwned(ObjectName name)
            throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();

        if (server.isRegistered(name)) {
            // Only do this when this component owns the registration.
            server.unregisterMBean(name);
        }
    }
}
```

**Cảnh báo về ownership:** `server.isRegistered(name)` chỉ cho biết tên đã đăng ký; nó không chứng minh MBean hiện tại thuộc về component của bạn. Đoạn mã trên chỉ phù hợp khi trước đó ứng dụng đã bảo đảm ownership bằng lifecycle, không dùng để xóa MBean của ứng dụng khác.

Khi dùng Spring `MBeanExporter`, hãy ưu tiên để exporter quản lý đăng ký/hủy đăng ký trong lifecycle ứng dụng. Với đăng ký thủ công, nên theo dõi chính xác ObjectName mà thành phần đã đăng ký thành công, hủy chính những tên đó khi đóng, và xử lý các lỗi race condition có thể xảy ra.

### Race condition trong thao tác kiểm tra rồi đăng ký

Mã như sau không bảo đảm an toàn tuyệt đối khi nhiều thread/context cùng đăng ký:

```java
if (!server.isRegistered(name)) {
    server.registerMBean(bean, name);
}
```

Giữa hai lệnh, một thành phần khác có thể đăng ký cùng tên. Hãy xử lý `InstanceAlreadyExistsException` theo chính sách ownership hoặc serialize quá trình đăng ký nếu hệ thống thực sự dùng chung server.

## 11. Gợi ý kiến trúc naming cho ứng dụng có nhiều module

Một hợp đồng tên có thể được thống nhất ở thư viện quản trị chung:

```text
domain = com.acme.<product>
key properties:
  type        = nhóm tài nguyên
  application = tên service/module
  name        = tên logical resource
  context     = optional, nếu context cần phân biệt
```

Ví dụ:

```text
com.acme.retail:type=Cache,application=catalog,name=products
com.acme.retail:type=Cache,application=pricing,name=rules
com.acme.retail:type=ThreadPool,application=catalog,name=background
com.acme.retail:type=DataSource,application=orders,name=primary
```

Lợi ích:

- Dễ tìm MBean theo `type` hoặc `application`.
- Tránh xung đột giữa hai bean cùng loại.
- Giảm sự phụ thuộc vào tên lớp Java hoặc proxy.
- Giữ ObjectName ổn định khi thay đổi implementation.
- Có khả năng xây dashboard/alert query theo pattern.

Mọi application cùng chia sẻ namespace cần dùng cùng quy ước; một module tự phát đưa tên vào key khác có thể làm query của hệ thống monitoring trở nên rời rạc.

## 12. Quan sát và chẩn đoán xung đột

### Liệt kê MBean hiện có

```java
import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

MBeanServer server = ManagementFactory.getPlatformMBeanServer();

for (ObjectName name : server.queryNames(
        new ObjectName("com.acme.*:*"), null)) {
    System.out.println(name.getCanonicalName());
}
```

Pattern trên chỉ minh họa: domain pattern và key pattern phải được thiết kế phù hợp domain thật. Có thể dùng JConsole hoặc VisualVM để duyệt cây MBean và đối chiếu ObjectName thực tế.

### Quy trình kiểm tra khi gặp InstanceAlreadyExistsException

1. Đọc ObjectName đầy đủ trong exception.
2. Xác định MBeanServer đang được dùng (platform server hay server tùy chỉnh).
3. Tra cứu xem ObjectName đó đã được đăng ký bởi component/context nào.
4. Kiểm tra các exporter hoặc annotation đang tạo ra cùng tên.
5. Kiểm tra bean key, cấu hình naming strategy và thay đổi do proxy.
6. Chọn cách sửa nguyên nhân: đổi schema tên, tách ownership hoặc ngăn export trùng.
7. Chỉ dùng ignore/replace khi đã hiểu rõ lifecycle và chủ sở hữu.

Không nên giải quyết bằng tên ngẫu nhiên mỗi lần chạy, vì nó khiến các công cụ quản trị khó tìm lại MBean và có thể che giấu việc registry bị rò rỉ.

## 13. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách làm tốt hơn |
| --- | --- | --- |
| Mọi bean có tên `type=Service` | Nhiều bean trùng ObjectName | Thêm key `name` theo resource |
| Lấy trực tiếp tên proxy class | Tên thay đổi sau khi thêm AOP | Dùng logical type ổn định |
| Dùng UUID ngẫu nhiên cho từng MBean | Dashboard khó truy vấn, nhiều tên khó theo dõi | Dùng resource ID ổn định |
| `IGNORE_EXISTING` trên mọi exporter | Bean mới có thể không được quản trị | Phát hiện lỗi sớm và sửa naming |
| `REPLACE_EXISTING` cho mọi context | Context này có thể thay MBean context khác | Xác định ownership rõ ràng |
| Không unregister khi shutdown | MBean cũ chiếm tên | Quản lý lifecycle và ownership |
| Bỏ qua ký tự đặc biệt trong value | `MalformedObjectNameException` hoặc pattern ngoài ý muốn | Quote/validate value đúng cú pháp |
| Nghĩ khác Spring context là khác MBeanServer | Vẫn trùng nếu dùng cùng platform server | Kiểm tra MBeanServer được dùng |
| Nhầm tên Spring bean với ObjectName | Sửa sai lớp định danh | Kiểm tra exporter/naming strategy |
| Đưa request/user ID vào ObjectName | Cardinality cao, tốn tài nguyên | Xuất số liệu tổng hợp ổn định |

## 14. Câu hỏi tự kiểm tra

**1. Hai MBean ở hai JVM khác nhau có thể cùng ObjectName không?**

Có. Tính duy nhất do từng MBeanServer quản lý. Khi quan sát tập trung vẫn cần định danh nguồn (host, process, instance) ở tầng giám sát.

**2. Vì sao `type=Cache` chưa đủ?**

Vì ứng dụng có thể có nhiều cache khác nhau. Thêm `name=products`, `name=prices` hoặc định danh resource khác để phân biệt.

**3. `ObjectName.quote` có tác dụng gì?**

Escape giá trị theo cú pháp ObjectName, giúp xử lý các ký tự đặc biệt trong key property value.

**4. Spring bean name có bắt buộc bằng key `name` trong ObjectName không?**

Không. Naming strategy hoặc cấu hình exporter xác định ObjectName; có thể dùng bean key làm một phần định danh, nhưng đây là lựa chọn thiết kế.

**5. Tại sao không dùng `REPLACE_EXISTING` mặc định?**

Vì một component có thể ghi đè hoặc hủy đối tượng quản trị thuộc component khác, đặc biệt khi có nhiều application context.

**6. Khi nào thêm `context` vào ObjectName?**

Khi nhiều context thực sự chia sẻ một MBeanServer và mỗi context cần xuất MBean riêng cùng loại/tên.

**7. Kiểm tra `isRegistered` trước `registerMBean` đã đủ tránh race chưa?**

Chưa. Đây là hai thao tác riêng; một thread khác có thể đăng ký tên giữa hai lệnh.

## 15. Kết luận

Tránh xung đột tên JMX cần một chiến lược `ObjectName` thống nhất, dựa trên **namespace + loại tài nguyên + ứng dụng + logical resource**, đồng thời hiểu rõ **phạm vi duy nhất của MBeanServer**. Trong Spring Framework, kết hợp `MBeanExporter`, `ObjectNamingStrategy`, `@ManagedResource` và `RegistrationPolicy` để kiểm soát tên và hành vi khi trùng.

Quy tắc thực tế: **Đặt tên ổn định và phân biệt đủ rõ ngay từ đầu; xử lý xung đột bằng thiết kế namespace và ownership thay vì mặc định bỏ qua hoặc thay thế MBean.**

### Tài liệu tham khảo

- Java SE API — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html
- Java SE API — `MBeanServer`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServer.html
- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `RegistrationPolicy`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/support/RegistrationPolicy.html
