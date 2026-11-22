# Đăng ký với MBeanServer và đặt ObjectName

## 1. Bài toán: làm thế nào để JMX nhìn thấy MXBean của ứng dụng?

**MXBean** là một dạng *Managed Bean* trong **Java Management Extensions (JMX)**. Nó cho phép ứng dụng công bố những **thuộc tính quản trị** (attributes), **thao tác quản lý** (operations) và, nếu thiết kế, **notifications** thông qua một giao diện rõ ràng. JMX tools/monitoring components giao tiếp với MBean qua **MBeanServer** và định danh mỗi MBean bằng một **ObjectName**.

`javax.management.MXBean`, `JMX.newMXBeanProxy`, `StandardMBean` với chế độ MXBean và các khả năng liên quan đã có từ **Java 6**; những API này **vẫn được Java SE 26 duy trì**. Phần thực hành dùng Java 17+ nhưng giải thích **chỉ các cơ chế JMX còn áp dụng hiện nay**, không lấy Java 6 làm cớ khuyến nghị kỹ thuật quản lý/remote networking lỗi thời.

Điểm quan trọng: **tạo một object Java implement MXBean interface chưa khiến object xuất hiện trong JMX**. Cần gọi:

~~~java
MBeanServer mbs = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
        "com.example.app:type=Worker,name=payments");
mbs.registerMBean(new Worker(), name);
~~~

Đây là **đoạn trích**, chỉ biên dịch khi đã định nghĩa lớp `Worker` compliant và import các classes tương ứng. Sau khi đăng ký thành công, mỗi object có thể được truy vấn qua `MBeanServer` hoặc JMX tool hỗ trợ. Nếu không có connector hợp lệ/được cấp quyền, việc đăng ký **không tự động mở một HTTP endpoint hay public network port**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **MXBean interface, implementation object, MBeanServer và ObjectName**.
2. Chọn `ManagementFactory.getPlatformMBeanServer()` cho tiến trình thực, và `MBeanServerFactory.newMBeanServer(...)` khi cần server độc lập trong test.
3. Biết interface `SomethingMXBean` hoặc `@MXBean`, vì sao public interface và signatures compliant quan trọng.
4. Thiết kế ObjectName gồm **domain** và **key properties** theo namespace/identity rõ ràng.
5. Sử dụng `ObjectName.quote(String)` cho **giá trị động**, tránh ký tự `,`, `=`, `:`, `*`, `?` tạo sai tên hoặc pattern ngoài ý muốn.
6. Phân biệt **exact ObjectName dùng đăng ký** với **ObjectName pattern dùng query**.
7. Gọi `registerMBean`, lấy `ObjectInstance`, kiểm tra `isRegistered`/`getAttribute`/`invoke`/`getMBeanInfo`.
8. Truy cập MXBean qua `JMX.newMXBeanProxy` và hiểu `open type` conversion, ví dụ `Map<String,String>` thành `TabularData`.
9. Xử lý `InstanceAlreadyExistsException`, `NotCompliantMBeanException` và cleanup bằng `unregisterMBean` đúng quyền sở hữu.
10. Hiểu security: **ObjectName không phải authorization boundary**; các thao tác qua JMX connector được bật có thể nhạy cảm.
11. Kiểm thử hai chương trình Java 17+ đã biên dịch và chạy thành công với stdout xác nhận được.

~~~text
      Ứng dụng Java
            |
            +--> public MXBean interface  (management contract)
            |       getState(), getCount(), reset()...
            |
            +--> implementation object  (trạng thái thật)
            |       Worker implements WorkerMetrics
            |
            +--> MBeanServer
                    |
                    +-- ObjectName exact:
                    |     com.example.app:type=Worker,name=payments
                    |
                    +-- registerMBean(object, objectName)
                    |
                    +-- isRegistered / getAttribute / invoke
                    |
                    +-- JMX.newMXBeanProxy(...)
                    |
                    +-- queryNames(pattern, null)
                    |
                    +-- unregisterMBean(objectName)
                                  |
                         Optional authorized JMX tools
~~~

## 2. Bốn thành phần không được nhầm với nhau

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **MXBean interface** | Xác định phần trạng thái và hành vi được quản lý | `WorkerMetrics` gắn `@MXBean` |
| **Implementation** | Đối tượng Java cung cấp giá trị thật, logic thread-safe | `new Worker()` |
| **MBeanServer** | Registry + management gateway trong JVM | `ManagementFactory.getPlatformMBeanServer()` |
| **ObjectName** | Tên định danh một MBean trong một MBeanServer | `com.example.app:type=Worker,name=payments` |
| **MXBean proxy** | Giao diện Java phía management client | `JMX.newMXBeanProxy(server, name, WorkerMetrics.class)` |
| **Open types** | Định dạng chuyển đổi dữ liệu tương thích JMX clients | `CompositeData`, `TabularData` |
| **MBeanServerConnection** | Giao diện chung cho access local hoặc remote | `MBeanServer` extends `MBeanServerConnection` |

Một `MBeanServer` có thể có nhiều MXBeans cùng interface nhưng khác `ObjectName`. Ngược lại, một `ObjectName` cụ thể chỉ định danh **một registered MBean tại một thời điểm trong cùng server**. Không được suy rằng cùng ObjectName ở hai JVMs hoặc hai MBeanServers khác nhau là cùng object; namespace của nó là **per MBeanServer**.

### 2.1. Registration khác publication qua network

`registerMBean(...)` đưa MBean vào registry trong JVM. Nó **không tự** cấu hình public JMX remote connector, TLS hoặc authentication. Nếu một connector/adaptor đã được gắn vào MBeanServer, các attributes/operations được công bố có thể truy cập từ các clients được connector cho phép. Vì vậy kiểm soát access **phải được thiết kế từ lúc tạo management interface**, không đợi đến khi mở remote port.

### 2.2. MXBean khác Standard MBean như thế nào?

Một **Standard MBean** thường tuân naming `SomethingMBean` và exposure các Java types theo MBean rules. **MXBean** tập trung vào khả năng chuyển Java types được chấp nhận sang **JMX open types**, giúp clients ở JVM/version khác nhau đọc dữ liệu mà không nhất thiết tải class riêng của model.

Ví dụ `Map<String,String>` được MXBean chuyển thành một dạng **`TabularData`** khi đọc qua `MBeanServer.getAttribute`; khi đi qua typed `JMX.newMXBeanProxy`, Java client có thể nhận lại `Map<String,String>` theo contract tương ứng. Bài test thứ hai xác nhận chính xác hiện tượng này.

### 2.3. API module Java hiện đại

JMX APIs nằm ở **module `java.management`**:

~~~java
module com.example.monitoring {
    requires java.management;
}
~~~

Đây là **đoạn khai báo module-info.java minh họa**, không phải chương trình runnable. Khi dùng classpath và JDK 17+, module `java.management` thông thường có thể được resolved mặc định; hai chương trình độc lập ở bài này biên dịch bằng `javac --release 17` và không cần thêm thư viện bên thứ ba.

## 3. Nhận diện MXBean interface: convention và @MXBean

JMX nhận diện một interface như MXBean khi:

- Đó là **public interface** có tên kết thúc bằng `MXBean`, ví dụ `QueueMetricsMXBean`, và không gắn `@MXBean(false)`; **hoặc**
- Interface được đánh dấu **`@MXBean` / `@MXBean(true)`** cho phép tên khác quy ước, ví dụ `WorkerMetrics`.

~~~java
import javax.management.MXBean;

@MXBean
public interface WorkerMetrics {
    String getState();
    long getProcessedCount();
    void recordProcessed(long count);
}
~~~

Đây là **đoạn trích** của management interface, không phải file độc lập cùng main. `@MXBean` đặt ở **interface**, không đơn thuần đánh dấu implementation class rồi mong mọi public method trở thành management operation.

### 3.1. Naming convention

~~~java
public interface QueueStatsMXBean {
    long getWaitingJobs();
    void clearCompletedJobs();
}
~~~

Interface public và hậu tố `MXBean` được JMX nhận diện mà không cần annotation, nếu signatures tuân rules. Nhưng nếu muốn tên interface thông thường hoặc một class implement nhiều interfaces, dùng `@MXBean` và/hoặc `StandardMBean(..., true)` để quản lý sự rõ ràng.

### 3.2. Attribute và operation mapping

Theo quy tắc JMX:

| Java interface method | JMX exposure |
| --- | --- |
| `long getProcessedCount()` | Readable attribute `ProcessedCount` |
| `String getState()` | Readable attribute `State` |
| `boolean isHealthy()` | Boolean attribute `Healthy` |
| `void setLimit(int value)` | Writable attribute `Limit` nếu có getter tương ứng hoặc theo accessor rules |
| `void reset()` | Operation `reset` |
| `void recordProcessed(long n)` | Operation `recordProcessed` với argument `long` |

Ví dụ:

~~~java
Object state = server.getAttribute(name, "State");
Object count = server.getAttribute(name, "ProcessedCount");
server.invoke(name, "recordProcessed", new Object[] {2L},
        new String[] {"long"});
~~~

**Đoạn trích**, tên attribute từ getter **không bao gồm tiền tố `get`**. `invoke` yêu cầu chữ ký Java type chính xác; `"long"` cho primitive, không phải `"java.lang.Long"`. Dùng `JMX.newMXBeanProxy` sẽ dễ bảo trì hơn so với tự viết strings cho mọi attributes/operations nếu client có management interface.

### 3.3. Method return/parameter types phải MXBean-compliant

Các kiểu Java được MXBean chuyển sang JMX open types theo rules chính thức: primitives/boxed types, String, một số collections/maps, enums và bean-like composite classes khi thỏa điều kiện mapping/reconstruction. Không trả một arbitrary object graph/cyclic model, JDBC Connection, Thread hay private business domain type không chuyển đổi được rồi mong nó tự serializable.

**Không nên lộ secrets** như access tokens, password, keystore contents, heap dump raw hoặc PII qua attributes, dù getter trả String hợp lệ. JMX là bề mặt quản lý có thể có remote access khi được bật.

### 3.4. Kiểm tra interface nhận diện bằng API

~~~java
boolean isMXBean = JMX.isMXBeanInterface(WorkerMetrics.class);
~~~

Đoạn trích. `true` xác nhận interface được xem như MXBean interface theo naming/annotation, **chưa** đảm bảo implementation class hợp lệ, mọi types có mapping hay object đã được đăng ký. Dùng `registerMBean`/`getMBeanInfo` và integration tests để kiểm tra toàn bộ hợp đồng.

## 4. Chọn MBeanServer: platform dùng chung hay server độc lập?

### 4.1. Platform MBeanServer cho service đang chạy

~~~java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
~~~

Đây là lựa chọn thông thường cho ứng dụng muốn bổ sung application metrics/management vào cùng server chứa các JVM/platform MXBeans. Lần đầu gọi, `ManagementFactory.getPlatformMBeanServer()` tạo server và đăng ký các platform management MBeans; các lần gọi tiếp theo trong **cùng JVM** nhận reference của **platform MBeanServer** đã chia sẻ.

Ưu điểm:
- Các công cụ JMX có quyền truy cập vào platform MBeanServer có thể nhìn thấy JVM metrics và application MXBeans trong một nơi.
- Một management connection có thể truy vấn application và JVM measurements.
- Không cần tự tạo server riêng cho từng component.

Lưu ý:
- **Namespace chung trong một JVM**: các libraries/components có thể dùng cùng ObjectName.
- Không ghi đè MBeans thuộc `java.lang` hoặc domain của framework khác.
- Module/redeploy/restart trong cùng process cần cleanup tránh collisions.
- Đăng ký không tự mở remote connector, nhưng khi connector có sẵn, các MBeans mới cũng nằm trong bề mặt quản lý của nó.

### 4.2. MBeanServerFactory.newMBeanServer cho test cô lập

~~~java
MBeanServer isolated = MBeanServerFactory.newMBeanServer("training");
~~~

Đây là đoạn trích dùng **server riêng**, không đăng ký vào danh sách global servers do factory quản lý như `createMBeanServer`. `"training"` ở đây là **default domain** của MBeanServer, **không hạn chế** các domain mà MBeans bên trong có thể dùng. Bài test thứ hai dùng server cô lập để có kết quả query count xác định, không phụ thuộc platform MBeans của process.

### 4.3. createMBeanServer so với newMBeanServer

| Factory | Ý nghĩa |
| --- | --- |
| `MBeanServerFactory.createMBeanServer(domain)` | Tạo server và giữ reference trong danh sách do factory quản lý |
| `MBeanServerFactory.newMBeanServer(domain)` | Tạo server mà factory **không giữ reference** như server created |
| `ManagementFactory.getPlatformMBeanServer()` | Platform singleton quản lý JVM MXBeans, dùng chung process |

Không đồng nhất một server riêng với platform server. MBeans đăng ký ở isolated server **không tự xuất hiện** khi bạn query platform server.

### 4.4. Default domain không phải security domain

Nếu ObjectName có domain rỗng trong vài trường hợp, MBeanServer có thể áp default domain. Nhưng ứng dụng thực tế nên dùng **domain tường minh** để tránh registry names khó dự đoán. Domain như `com.example.inventory` là **namespace**, không phải firewall, credential scope hay đơn vị cách ly đa tenant.

## 5. ObjectName: cú pháp và danh tính của MBean

Một ObjectName có dạng:

~~~text
domain:key1=value1,key2=value2,...
~~~

Ví dụ:

~~~text
com.example.monitoring:type=Worker,name=payments,instance=primary
com.example.monitoring:type=Queue,name=invoices,region=apac
com.example.monitoring:type=DatabasePool,name=orders,instance=west-1
~~~

- **Domain**: namespace, thường dùng reverse-DNS-style để giảm collision.
- **Key properties**: cặp key=value cho biết `type`, `name`, `instance`, `region`, `tenant` đã được thiết kế.
- Domain và keys/values có ràng buộc cú pháp; không ghép input tự do vào bất kỳ vị trí nào.
- Trật tự các key properties về **định danh** không quan trọng: canonical representation sẽ sắp xếp chúng.

### 5.1. Reverse-DNS namespace là convention hữu ích

Oracle khuyến nghị bắt đầu domain bằng reverse DNS của tổ chức, ví dụ `com.example.monitoring`, để tránh collisions. Trong bài dùng `com.example.lesson` và `com.example.training`, chỉ là các domain minh họa. Khi triển khai thật, chọn domain của tổ chức/project và quy ước key cố định; đừng lạm dụng `java.lang` để đặt MBean ứng dụng.

### 5.2. ObjectName exact và pattern khác nhau

`ObjectName` có thể biểu diễn:
- **Exact name** dùng `registerMBean(object, name)`.
- **Pattern** dùng `queryNames(pattern, null)` hoặc query MBeans.

Các ký tự wildcard:
- `*`: khớp một chuỗi (có thể rỗng);
- `?`: khớp một ký tự;
- dấu `,*` trong key-property list: pattern cho phép **thêm properties** khác.

Ví dụ:

~~~text
com.example.monitoring:type=Worker,name=payments
com.example.monitoring:type=Worker,*
com.example.monitoring:type=Worker,name=*,*
com.example.monitoring:*
*:* 
~~~

Dòng thứ nhất là exact name. Ba dòng tiếp là pattern từ hẹp đến rộng theo cú pháp; `*:*` là wildcard mọi domains/properties. **Không bao giờ dùng một query pattern làm registration identity**.

### 5.3. isPattern() nên là assertion trước đăng ký

~~~java
ObjectName exact = new ObjectName(
        "com.example.monitoring:type=Worker,name=payments");
if (exact.isPattern()) {
    throw new IllegalArgumentException("Registration requires exact ObjectName");
}
~~~

**Đoạn trích**. Nó bảo vệ một số lỗi xây tên động, nhưng cần thêm validation cho domain/key values và ownership. MBeanServer cũng kiểm tra validity/compliance khi đăng ký.

### 5.4. QueryNames cho tập MBeans

~~~java
Set<ObjectName> found = server.queryNames(
        new ObjectName("com.example.monitoring:type=Worker,*"),
        null);
~~~

**Đoạn trích**, cần import `java.util.Set`. Pattern `type=Worker,*` match các names có key `type=Worker` và có thể có thêm key properties như `name` hoặc `instance`. **Nếu bỏ `,*`**, một pattern chỉ có `type=Worker` có thể bị giới hạn theo danh sách properties, nên không suy rằng nó luôn match mọi Worker đã có nhiều properties.

### 5.5. Canonical order và equals

~~~java
ObjectName a = new ObjectName(
        "com.example.app:type=Worker,name=payments");
ObjectName b = new ObjectName(
        "com.example.app:name=payments,type=Worker");
boolean same = a.equals(b); // true.
String canonical = a.getCanonicalName();
~~~

Đây là đoạn trích. `ObjectName.equals` dựa trên **canonical form**; thứ tự properties không phân biệt identity. Không dùng raw `ObjectName.toString()` rồi tự so sánh chuỗi để quyết định một tên có giống tên khác hay không. `getCanonicalName()` sắp xếp properties theo thứ tự lexical để ổn định; có thể dùng cho logging/registry keys.

## 6. ObjectName.quote: biến dữ liệu thành tên an toàn

Đây là phần dễ phát sinh bug nhất nếu **instance ID, queue name hoặc tenant ID** có ký tự đặc biệt. Ví dụ tên logic:

~~~text
billing,primary
daily,*?
blue=green
north:prod
worker\name
~~~

Nếu nối trực tiếp vào:

~~~java
// SAI: dấu phẩy và wildcard có thể đổi ý nghĩa ObjectName.
ObjectName wrong = new ObjectName(
        "com.example.app:type=Worker,name=" + userSuppliedName);
~~~

Đoạn phản ví dụ. `userSuppliedName` chứa dấu phẩy có thể làm parser nghĩ một key property mới, hoặc ký tự `*`/`?` tạo **pattern**. Đối với **giá trị** key-property, dùng:

~~~java
String logicalName = "billing,primary";
ObjectName name = new ObjectName(
        "com.example.app:type=Worker,name="
        + ObjectName.quote(logicalName));
~~~

`ObjectName.quote` tự bọc value trong dấu nháy kép và escape các ký tự đặc biệt (`"`, backslash, `*`, `?`, newline) để chúng trở thành **literal data**. Sau đó kiểm tra `name.isPattern()==false`. **Chỉ dùng quote cho value**, không cho domain hoặc property key; những phần đó do code cố định/validate.

### 6.1. Đọc lại giá trị quoted

~~~java
String stored = name.getKeyProperty("name");
String logical = ObjectName.unquote(stored);
boolean same = "billing,primary".equals(logical);
~~~

**Đoạn trích.** Nếu key property chứa quoted representation, `getKeyProperty(...)` có thể trả chuỗi còn dấu quote/escape, và `ObjectName.unquote` giúp lấy lại original value khi bạn biết nó được tạo bằng `quote`. Không gọi `unquote` mù quáng lên một unquoted property value, vì method có thể ném `IllegalArgumentException`.

### 6.2. Wildcard trong quoted value

Một tên logic `daily,*?` phải được hiểu **literal** khi đăng ký, không phải “mọi task tên daily...”. Bài test thứ hai tạo:

~~~java
String original = "daily,*?";
ObjectName name = new ObjectName(
        "com.example.training:type=Task,name="
        + ObjectName.quote(original));
if (name.isPattern()) {
    throw new IllegalStateException("Unexpected query pattern");
}
~~~

`ObjectName.quote` escape `*` và `?` bên trong quote, nên `isPattern()==false`. Lưu ý **chỉ bọc value bằng dấu nháy không đủ** nếu bạn tự nối chuỗi vì `*`/`?` chưa được escape có thể vẫn được hiểu là wildcard theo grammar. Hãy dùng **API `ObjectName.quote`**, không tự viết escaping.

### 6.3. Tránh nhồi sensitive data vào ObjectName

ObjectName dễ được liệt kê bằng `queryNames` và management tools. Vì vậy:
- Không dùng password, session ID, bearer token hoặc customer email làm ObjectName.
- Với tenant IDs nhạy cảm, dùng stable surrogate ID không tiết lộ PII.
- Không tạo hàng triệu ObjectNames theo từng request; mỗi registered MBean là quản trị object, có lifecycle và metadata.
- Hạn chế việc cho client input trực tiếp tạo key/value ngay cả khi đã quote: quoted data vẫn có thể gây memory/cardinality explosion.

### 6.4. Domain và key names nên cố định

Một helper nhận data có thể làm:

~~~java
static ObjectName workerName(String logicalId)
        throws MalformedObjectNameException {
    if (logicalId == null || logicalId.isBlank()
            || logicalId.length() > 128) {
        throw new IllegalArgumentException("Invalid logicalId");
    }
    return new ObjectName(
            "com.example.myservice:type=Worker,name="
            + ObjectName.quote(logicalId));
}
~~~

Đây là **đoạn trích**, cần import `javax.management.*`. Nó là ví dụ giới hạn kích thước/empty name; trong production còn có thể cần whitelist/normalization business IDs, stable namespace versioning và không đưa PII vào name. Đừng cho một input thay đổi `domain`, `type` hay property keys nếu không thực sự có một quản lý registry policy rõ ràng.

## 7. Luồng đăng ký và hủy đăng ký chính xác

Các bước điển hình:

1. Định nghĩa **public MXBean interface** compliant.
2. Tạo implementation với state an toàn khi nhiều threads gọi.
3. Xác định đúng MBeanServer (platform hoặc isolated theo mục đích).
4. Xây **exact ObjectName** với domain/key convention đã kiểm tra.
5. Có thể gọi `isRegistered` để đưa ra lỗi thân thiện, nhưng **không coi đó là khóa concurrency**.
6. Gọi `registerMBean(instance, name)` và nhận `ObjectInstance`.
7. Truy cập bằng `getAttribute`, `invoke`, `getMBeanInfo` hoặc `JMX.newMXBeanProxy`.
8. Khi component dừng, **unregister đúng MBean mà component đã register**.
9. Đóng các resources riêng của implementation (executors, files, connections) theo lifecycle riêng.

~~~text
Create implementation
         |
         v
Build exact ObjectName
         |
         v
MBeanServer.registerMBean
         |
         +---- InstanceAlreadyExistsException --> không ghi đè ownership khác
         |
         +---- NotCompliantMBeanException -----> sửa MXBean contract
         |
         v
ObjectInstance (registered)
         |
         +--> getAttribute / invoke
         +--> JMX.newMXBeanProxy
         +--> queryNames exact/pattern
         |
         v
Application/component shutdown
         |
         v
unregisterMBean / release resources
~~~

### 7.1. registerMBean() nhận pre-existing object

~~~java
ObjectInstance result = server.registerMBean(
        new Worker(), name);
ObjectName actual = result.getObjectName();
~~~

**Đoạn trích.** `registerMBean` không tạo instance từ class name; instance đã được ứng dụng tạo. Nếu muốn factory tạo từ class name có `createMBean`, đó là một API khác có thêm requirements về classloading/constructors; với dependency-injected applications, `registerMBean` thường đơn giản và minh bạch hơn.

### 7.2. Phải bảo vệ duplicate identity

Nếu hai components cùng đăng ký:

~~~java
server.registerMBean(first, sameName);
server.registerMBean(second, sameName);
~~~

Lần thứ hai phải chịu **`InstanceAlreadyExistsException`** nếu tên đã có. Không tự gọi `unregisterMBean(sameName)` để “giải phóng” nếu không biết chắc đó là MBean do component của mình sở hữu: có thể xóa management bean của module khác.

### 7.3. isRegistered() là preflight, không atomic reservation

~~~java
if (!server.isRegistered(name)) {
    server.registerMBean(instance, name);
}
~~~

Đây là đoạn minh họa **có race**: giữa lúc `isRegistered` trả false và `registerMBean`, worker khác có thể đăng ký tên đó. Vì vậy `registerMBean`/`InstanceAlreadyExistsException` mới là điểm phân xử cuối cùng. Nếu cần idempotent startup, thiết kế owner registry, lifecycle coordination và kiểm tra identity rõ thay vì “catch mọi exception rồi coi như thành công”.

### 7.4. Registration callbacks và exception bất ngờ

MBean có thể implement `MBeanRegistration` với các lifecycle hooks:
- `preRegister`, `postRegister`;
- `preDeregister`, `postDeregister`.

Theo Javadoc `MBeanServer.registerMBean`, nếu `postRegister` ném runtime exception thì **có trường hợp registration đã thành công mặc dù method ném exception**. Điều này làm chiến lược retry một cách mù quáng trở nên nguy hiểm: sau lỗi không rõ, kiểm tra trạng thái và owner trước khi retry/cleanup. Các ví dụ bài này **không implement registration hooks**, nên không có trường hợp đó trong fixture.

### 7.5. unregisterMBean() không đồng nghĩa close toàn bộ service

`server.unregisterMBean(name)` xóa mapping trong MBeanServer. Nó **không** thay việc dừng thread pool, scheduler, DB client hoặc đóng files thuộc implementation, trừ khi MBean/component tự lập lifecycle phù hợp. Tách ownership:
- **Registry ownership**: ai đăng ký thì người đó gỡ.
- **Resource ownership**: ai tạo resource thì người đó đóng.
- **Connector ownership**: ai khởi động JMXConnectorServer thì người đó dừng đúng thời điểm.

## 8. Java 17+ runnable: MXBean register, proxy, query và cleanup

Chương trình `MxBeanRegistrationDemo.java` dùng `ManagementFactory.getPlatformMBeanServer()` ngay trong process, không mở network connector:
- Interface `WorkerMetrics` public, có `@MXBean`.
- `Worker` dùng `AtomicLong` để đếm processed items an toàn trước concurrent calls.
- `ObjectName.quote("billing,primary")` để name có dấu phẩy vẫn là literal.
- Gọi `registerMBean`, kiểm tra `ObjectInstance.getObjectName()` và `isRegistered`.
- Getter `getState()` được JMX expose thành attribute `State`.
- Dùng typed `JMX.newMXBeanProxy` gọi `recordProcessed(3)`.
- Dùng `MBeanServer.invoke` gọi `recordProcessed(2)`, signature primitive `long`.
- `getAttribute("ProcessedCount")` trả Long 5.
- `queryNames("com.example.lesson:type=Worker,*")` tìm thấy name.
- Đăng ký lại cùng name ném `InstanceAlreadyExistsException`.
- Finally hủy đăng ký **chỉ khi chương trình đã đăng ký thành công** và kiểm tra sạch.

### 8.1. File MxBeanRegistrationDemo.java

~~~java
import java.lang.management.ManagementFactory;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;
import javax.management.*;

public final class MxBeanRegistrationDemo {
    @MXBean
    public interface WorkerMetrics {
        String getState();
        long getProcessedCount();
        void recordProcessed(long count);
    }

    public static final class Worker implements WorkerMetrics {
        private final AtomicLong processed = new AtomicLong();

        @Override public String getState() {
            return "running";
        }

        @Override public long getProcessedCount() {
            return processed.get();
        }

        @Override public void recordProcessed(long count) {
            if (count < 0) throw new IllegalArgumentException("count must be >= 0");
            processed.addAndGet(count);
        }
    }

    static void check(boolean okay, String description) {
        if (!okay) throw new AssertionError(description);
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = ManagementFactory.getPlatformMBeanServer();
        String instanceId = "billing,primary";
        ObjectName name = new ObjectName(
                "com.example.lesson:type=Worker,name=" + ObjectName.quote(instanceId));
        check(!name.isPattern(), "registration name must be exact");
        check(instanceId.equals(ObjectName.unquote(name.getKeyProperty("name"))),
                "ObjectName quoting round trip");
        check(JMX.isMXBeanInterface(WorkerMetrics.class), "MXBean interface detection");

        if (server.isRegistered(name)) {
            throw new IllegalStateException("ObjectName already owned: " + name);
        }
        boolean owned = false;
        try {
            ObjectInstance registration = server.registerMBean(new Worker(), name);
            owned = true;
            check(name.equals(registration.getObjectName()), "returned name");
            check(server.isRegistered(name), "registered");
            check("running".equals(server.getAttribute(name, "State")), "State attribute");

            WorkerMetrics proxy = JMX.newMXBeanProxy(server, name, WorkerMetrics.class);
            proxy.recordProcessed(3);
            server.invoke(name, "recordProcessed",
                    new Object[] { 2L }, new String[] { "long" });

            long value = (Long) server.getAttribute(name, "ProcessedCount");
            check(value == 5L && proxy.getProcessedCount() == 5L, "metrics access");
            Set<ObjectName> matches = server.queryNames(
                    new ObjectName("com.example.lesson:type=Worker,*"), null);
            check(matches.contains(name), "query result");

            boolean duplicateRejected = false;
            try {
                server.registerMBean(new Worker(), name);
            } catch (InstanceAlreadyExistsException expected) {
                duplicateRejected = true;
            }
            check(duplicateRejected, "duplicate should fail");

            System.out.println("mxbean-interface=true");
            System.out.println("object-name-exact=true");
            System.out.println("object-name-quoted-roundtrip=true");
            System.out.println("registered=true");
            System.out.println("state=running");
            System.out.println("processed-count=" + value);
            System.out.println("query-matched=true");
            System.out.println("duplicate-rejected=" + duplicateRejected);
        } finally {
            if (owned && server.isRegistered(name)) {
                server.unregisterMBean(name);
            }
        }
        check(!server.isRegistered(name), "cleanup");
        System.out.println("registered-after-cleanup=false");
        System.out.println("tests=PASS");
    }
}
~~~

### 8.2. Biên dịch và chạy

Lưu file đúng tên `MxBeanRegistrationDemo.java`, dùng JDK 17+:

~~~bash
javac -encoding UTF-8 --release 17 MxBeanRegistrationDemo.java
java MxBeanRegistrationDemo
~~~

**Stdout chính xác đã kiểm chứng trên OpenJDK 24**, target Java 17:

~~~text
mxbean-interface=true
object-name-exact=true
object-name-quoted-roundtrip=true
registered=true
state=running
processed-count=5
query-matched=true
duplicate-rejected=true
registered-after-cleanup=false
tests=PASS
~~~

### 8.3. Đọc đúng kết quả

- `mxbean-interface=true`: `JMX.isMXBeanInterface(WorkerMetrics.class)` công nhận annotation.
- `object-name-exact=true`: `ObjectName.isPattern()` là false; tên dùng được như identity.
- `object-name-quoted-roundtrip=true`: dấu phẩy trong `billing,primary` là data, không tạo một property mới.
- `registered=true`: MBeanServer đã đăng ký MBean với tên đó.
- `state=running`: `getState()` ánh xạ thành attribute `State`.
- `processed-count=5`: proxy operation + invoke đều cập nhật cùng đối tượng thật (3+2).
- `query-matched=true`: ObjectName pattern tìm được MBean.
- `duplicate-rejected=true`: server ngăn đăng ký trùng; **không** đè object cũ.
- `registered-after-cleanup=false`: finally đã gỡ mapping.
- `tests=PASS`: tất cả assertions đạt; không có remote connector được bật trong demo.

### 8.4. Vì sao dùng AtomicLong?

Một MXBean có thể bị gọi đồng thời bởi nhiều management threads và chính application. `AtomicLong.addAndGet` bảo đảm tăng counter atomic, không làm lost updates như `long count; count += delta`. Đối với metrics lớn, cân nhắc `LongAdder`, nhưng khi cần atomic read/write/operation semantics cụ thể, dùng primitive concurrency phù hợp. Các getter nên nhanh và không giữ lock lâu.

### 8.5. Không để registration name va chạm với application đang chạy

Demo dùng `com.example.lesson:type=Worker,name="billing,primary"`. Trước khi chạy trong một **shared JVM** đã có component cùng namespace, xác định ownership. Ví dụ có precheck `isRegistered`, nhưng vẫn bắt `InstanceAlreadyExistsException` để đối phó registration đồng thời.

## 9. StandardMBean wrapper và MXBean annotation

JMX nhận diện implementation class theo một số đường:

- Implement **public interface tên kết thúc `MXBean`**;
- Implement **public interface được gắn `@MXBean`**;
- Bọc implementation trong `new StandardMBean(impl, interface, true)` để chọn rõ **MXBean mode**, ngay cả khi tên implementation không theo naming convention;
- Các advanced implementations có thể dùng `DynamicMBean`, nhưng đó là tầng khác và không cần cho ví dụ cơ bản.

### 9.1. Tại sao dùng StandardMBean(..., true)?

Ví dụ:

~~~java
StandardMBean wrapped =
        new StandardMBean(new TaskStats("daily"), TaskView.class, true);
server.registerMBean(wrapped, objectName);
~~~

**Đoạn trích**, `TaskStats` implements `TaskView`. Boolean `true` nói interface được đăng ký theo **MXBean semantics**, chứ không phải Standard MBean convention. Nếu đặt `false`, bạn có thể thay đổi loại MBean/kiểu dữ liệu được exposed. Bài test thứ hai xác minh descriptor MXBean và open-data mapping.

### 9.2. Annotation khác tên interface hậu tố MXBean

Interface trong bài test thứ hai được đặt tên **`TaskView`**, không kết thúc bằng `MXBean`, nhưng có `@MXBean`. Vì vậy direct registration của `new TaskStats("direct")` vẫn được JMX chấp nhận. Điều đó chứng minh:
- Hậu tố `MXBean` là **convention**, không phải điều kiện duy nhất.
- Annotation `@MXBean` trên interface là một cách công khai/đọc được.
- Wrapper `StandardMBean(..., true)` là cách explicit chọn management interface khi cần.

### 9.3. MBeanInfo/Descriptor xác minh điều gì?

`MBeanServer.getMBeanInfo(name)` cung cấp metadata như attributes, operations, class name và descriptor. Trong SunJSSE/JMX implementation được kiểm thử, trường descriptor `mxbean` có giá trị **String `"true"`**, không phải `Boolean.TRUE`. Đừng ép kiểu boolean mù quáng:

~~~java
Object flag = server.getMBeanInfo(name)
        .getDescriptor().getFieldValue("mxbean");
boolean mxbean = "true".equalsIgnoreCase(String.valueOf(flag));
~~~

**Đoạn trích**. Tên field là `mxbean`; với descriptor tiêu chuẩn, bạn nên kiểm tra **giá trị theo contract**, không chỉ dựa vào `instanceof Boolean`. Một JMX client cần phân biệt metadata thực tế với suy đoán dựa trên tên class.

## 10. Open type conversion của MXBean

### 10.1. Vì sao open types quan trọng?

Một MXBean có thể trả về một Java value như `Map<String,String>`, nhưng remote client không nhất thiết có class implementation/model giống server. JMX MXBean mapping chuyển những Java types được hỗ trợ sang `javax.management.openmbean` open data.

| Java MXBean interface type | Open data representation phổ biến |
| --- | --- |
| `String` | `String` |
| `long` / `Long` | `Long` |
| `long[]` | `long[]` hoặc mapped array type tương ứng |
| `Map<String,String>` | `TabularData` |
| Bean-like composite values hợp chuẩn | `CompositeData` |
| Enum hợp lệ | `String` theo enum naming |
| Collections/arrays hợp lệ | Open array/mapped data tương ứng |

Không suy rằng mọi Java class đều tự động remote-friendly; MXBean specification có các quy tắc mapping và reconstructibility nghiêm ngặt.

### 10.2. getAttribute() nhận open type, proxy nhận lại interface type

Giả sử interface có:

~~~java
@MXBean
public interface TaskView {
    Map<String, String> getLabels();
}
~~~

**Đoạn trích**, cần imports. Khi đã đăng ký:
- `server.getAttribute(name, "Labels")` có thể trả **`TabularData`**;
- `JMX.newMXBeanProxy(server, name, TaskView.class).getLabels()` sẽ chuyển open data thành **`Map<String,String>`** theo interface contract.

Đó là mục đích của typed proxy: giúp caller không phải tự đọc hàng/cột của TabularData. Bài test thứ hai kiểm tra cả hai đường.

### 10.3. Không biến MXBean thành bulk-data endpoint

JMX phù hợp với **management data**: counters, limited configuration, health snapshots, kích thước queue, trạng thái component. Không nên trả hàng chục MB hoặc millions of rows qua `getAttribute` mỗi lần:
- JMX read có thể gây CPU/heap churn;
- remote clients có thể gây áp lực nếu quá nhiều requests;
- getter chậm kéo dài diagnostic tooling;
- dữ liệu có thể chứa secrets/PII.

Thiết kế attributes nhẹ, bounded, thread-safe; dùng metrics APIs hoặc dữ liệu lưu trữ chuyên dụng khi cần telemetry tốc độ cao/high cardinality.

## 11. Java 17+ runnable: ObjectName quoting, wrapper, OpenType và lỗi đăng ký

Chương trình thứ hai `MxBeanNamesAndOpenTypesDemo.java` mở một **MBeanServer riêng** bằng `MBeanServerFactory.newMBeanServer("training")` để không làm thay đổi platform registry của JVM.

Nội dung kiểm thử:
1. Tên logic `daily,*?` được `ObjectName.quote` biến thành literal value; `isPattern()==false`.
2. Hai ObjectNames với thứ tự key properties đảo ngược vẫn `equals()==true`.
3. `ObjectName.unquote(getKeyProperty(...))` khôi phục giá trị ban đầu.
4. `queryNames(new ObjectName("com.example.training:type=Task,*"), null)` là một pattern hợp lệ.
5. Đăng ký `TaskStats` bằng **`StandardMBean(..., true)`** dưới tên wrapped.
6. Đăng ký trực tiếp một `TaskStats` khác thông qua interface `TaskView` có `@MXBean`.
7. `server.getAttribute(wrapped,"Labels")` là **`TabularData`**; typed proxy chuyển về Map.
8. Lấy `MBeanInfo.Descriptor` và xác nhận field `mxbean`.
9. Query tìm đúng **hai MBeans**.
10. Đăng ký `new Object()` bị từ chối bằng **`NotCompliantMBeanException`**.
11. Finally gỡ cả hai và xác minh registry sạch.

### 11.1. File MxBeanNamesAndOpenTypesDemo.java

~~~java
import java.util.Map;
import java.util.Set;
import javax.management.*;
import javax.management.openmbean.TabularData;

public final class MxBeanNamesAndOpenTypesDemo {
    @MXBean
    public interface TaskView {
        String getName();
        Map<String, String> getLabels();
        long[] getBuckets();
        void reset();
    }

    public static final class TaskStats implements TaskView {
        private final String name;
        public TaskStats(String name) { this.name = name; }
        @Override public String getName() { return name; }
        @Override public Map<String, String> getLabels() {
            return Map.of("region", "apac", "tier", "test");
        }
        @Override public long[] getBuckets() { return new long[] { 2L, 4L }; }
        @Override public void reset() { }
    }

    static void check(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        MBeanServer server = MBeanServerFactory.newMBeanServer("training");
        String logical = "daily,*?";
        String quoted = ObjectName.quote(logical);
        ObjectName wrapped = new ObjectName(
                "com.example.training:type=Task,name=" + quoted);
        ObjectName reversed = new ObjectName(
                "com.example.training:name=" + quoted + ",type=Task");
        ObjectName direct = new ObjectName(
                "com.example.training:type=Task,name=" + ObjectName.quote("direct"));
        ObjectName query = new ObjectName("com.example.training:type=Task,*");

        check(!wrapped.isPattern(), "literal characters must not create pattern");
        check(wrapped.equals(reversed), "canonical properties are unordered");
        check(ObjectName.unquote(wrapped.getKeyProperty("name")).equals(logical),
                "quoted name roundtrip");
        check(query.isPattern(), "query must be pattern");

        StandardMBean model = new StandardMBean(
                new TaskStats(logical), TaskView.class, true);
        boolean registeredWrapped = false;
        boolean registeredDirect = false;
        try {
            server.registerMBean(model, wrapped);
            registeredWrapped = true;
            server.registerMBean(new TaskStats("direct"), direct);
            registeredDirect = true;

            check("daily,*?".equals(server.getAttribute(wrapped, "Name")), "name");
            Object labels = server.getAttribute(wrapped, "Labels");
            check(labels instanceof TabularData, "Map must be mapped to TabularData");
            TaskView proxy = JMX.newMXBeanProxy(server, wrapped, TaskView.class);
            check("apac".equals(proxy.getLabels().get("region")), "mapped back");
            check(proxy.getBuckets().length == 2 && proxy.getBuckets()[1] == 4L,
                    "long array");
            Object descriptor = server.getMBeanInfo(wrapped)
                    .getDescriptor().getFieldValue("mxbean");
            check("true".equalsIgnoreCase(String.valueOf(descriptor)),
                    "MXBean descriptor");
            Set<ObjectName> names = server.queryNames(query, null);
            check(names.contains(wrapped) && names.contains(direct),
                    "query matches two registered MBeans");

            boolean notCompliantRejected = false;
            try {
                server.registerMBean(new Object(),
                        new ObjectName("com.example.training:type=Bad,name=plain"));
            } catch (NotCompliantMBeanException expected) {
                notCompliantRejected = true;
            }
            check(notCompliantRejected, "non-MBean should fail");

            System.out.println("quoted-name-not-pattern=true");
            System.out.println("canonical-property-order-ignored=true");
            System.out.println("query-pattern=true");
            System.out.println("wrapped-registered=true");
            System.out.println("annotation-direct-registered=true");
            System.out.println("labels-open-type=" + (labels instanceof TabularData));
            System.out.println("proxy-map-converted=true");
            System.out.println("mxbean-descriptor=true");
            System.out.println("query-count=" + names.size());
            System.out.println("non-compliant-rejected=" + notCompliantRejected);
        } finally {
            if (registeredWrapped && server.isRegistered(wrapped))
                server.unregisterMBean(wrapped);
            if (registeredDirect && server.isRegistered(direct))
                server.unregisterMBean(direct);
        }
        check(!server.isRegistered(wrapped) && !server.isRegistered(direct),
                "cleanup");
        System.out.println("registered-after-cleanup=false");
        System.out.println("tests=PASS");
    }
}
~~~

### 11.2. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 17 MxBeanNamesAndOpenTypesDemo.java
java MxBeanNamesAndOpenTypesDemo
~~~

**Stdout chính xác**, đã chạy thành công trên OpenJDK 24, target Java 17:

~~~text
quoted-name-not-pattern=true
canonical-property-order-ignored=true
query-pattern=true
wrapped-registered=true
annotation-direct-registered=true
labels-open-type=true
proxy-map-converted=true
mxbean-descriptor=true
query-count=2
non-compliant-rejected=true
registered-after-cleanup=false
tests=PASS
~~~

### 11.3. Phân tích kết quả

`quoted-name-not-pattern=true` chứng minh `*` và `?` trong tên thực tế đã được escape như literal. `canonical-property-order-ignored=true` cho biết hai ObjectNames có các key-value giống nhau nhưng khác thứ tự là cùng định danh. `query-pattern=true` cho biết chỉ tên query mới dùng wildcard.

Hai registrations cho thấy có thể dùng **wrapper explicit** hoặc **direct annotated interface**. `labels-open-type=true` là `TabularData` ở đường MBeanServer; `proxy-map-converted=true` là typed proxy khôi phục Map. `mxbean-descriptor=true` là metadata đã được server cung cấp. `non-compliant-rejected=true` chứng minh không phải bất kỳ Java Object nào cũng được register. Cleanup xóa đúng hai MBeans do demo đã tạo.

### 11.4. Vì sao query-count=2 là kết quả đáng tin?

Ví dụ dùng **`MBeanServerFactory.newMBeanServer` riêng**, nên pattern `com.example.training:type=Task,*` chỉ tìm hai MBeans do test đăng ký trong server đó. Nếu dùng platform server chung cho nhiều components, **không nên assert query count toàn domain** bằng số cố định trừ khi test kiểm soát hoàn toàn registry.

## 12. Một naming convention có thể dùng ở ứng dụng thực

Ví dụ đặt tên với các key có nghĩa:

~~~text
com.mycompany.orders:type=Queue,name=payment-events,instance=primary
com.mycompany.orders:type=WorkerPool,name=dispatch,region=apac,instance=west-1
com.mycompany.orders:type=Cache,name=product-catalog,instance=local
~~~

### 12.1. Domain để tránh collision

Chọn domain dựa trên tổ chức + service. Tránh tên quá ngắn như `default` hoặc `app` nếu cùng process chạy nhiều libraries/agents. Không dùng `java.lang` vì đó là namespace JVM/platform MXBeans.

### 12.2. Key type, name, instance

- `type`: phân loại resource (Queue/WorkerPool/Cache/ConnectionPool).
- `name`: logical resource name, ổn định giữa những lần quét JMX.
- `instance`: disambiguate nhiều instances (ví dụ deployment identity); đừng dùng timestamp cho mỗi request.
- `region` hoặc `shard`: chỉ thêm khi nó giúp quản lý, không làm tăng cardinality không cần thiết.

### 12.3. Cùng instance ID nhưng khác type có được không?

Có: `domain:type=Queue,name=main` và `domain:type=WorkerPool,name=main` khác nhau vì key property `type`. Tuy nhiên, một physical resource không nên bị đăng ký dưới quá nhiều names không có giải thích, vì gây nhầm metrics/ownership và duplicate management actions.

### 12.4. Stable names xuyên redeploy

Trong cùng JVM, nếu module/component reload, phải unregister old MBean trước khi new component đăng ký lại tên ổn định. Với nhiều pods/JVMs, mỗi process có một MBeanServer riêng nên **cùng logical ObjectName ở các JVMs khác nhau là bình thường**; management connector location/process identity dùng để phân biệt. Đừng cố nhồi hostname/port vào ObjectName như một authorization mechanism.

### 12.5. Quản lý ObjectName trong factory

Thay vì string building rải rác:

~~~java
public final class MonitoringNames {
    private MonitoringNames() {}

    public static ObjectName worker(String logicalName)
            throws MalformedObjectNameException {
        if (logicalName == null || logicalName.isBlank()) {
            throw new IllegalArgumentException("Logical worker name required");
        }
        if (logicalName.length() > 128) {
            throw new IllegalArgumentException("Logical worker name too long");
        }
        return new ObjectName(
            "com.mycompany.orders:type=Worker,name="
            + ObjectName.quote(logicalName));
    }
}
~~~

Đây là **snippet** không phải file độc lập; cần `javax.management.*`. ObjectName factory cố định domain/type, quote value, kiểm soát kích thước. Không tạo MBean cho từng user/request; dùng aggregates.

## 13. Các exceptions thường gặp khi đăng ký/truy cập

| Exception | Khi nào xảy ra | Hướng xử lý |
| --- | --- | --- |
| `MalformedObjectNameException` | Cú pháp ObjectName sai, ký tự bất hợp lệ | Dùng factory và `ObjectName.quote` cho dynamic values |
| `InstanceAlreadyExistsException` | Có MBean khác đã đăng ký cùng ObjectName | Kiểm tra ownership, sửa namespace/lifecycle; không đè |
| `NotCompliantMBeanException` | Object/interface không tuân JMX/MXBean rules | Kiểm tra public interface, naming/annotation, open type conversion |
| `MBeanRegistrationException` | Lifecycle hook đăng ký/hủy đăng ký ném checked exception | Xem root cause, xác minh registry state |
| `InstanceNotFoundException` | Query/invoke/unregister với name không còn tồn tại | Refresh registry state, xử lý component shutdown |
| `AttributeNotFoundException` | `getAttribute` tên sai hoặc không được expose | Kiểm tra `getMBeanInfo`, getter mapping |
| `ReflectionException` | Operation/constructor reflection không phù hợp | Kiểm tra method name/signature và classloading |
| `MBeanException` | Implementation operation ném checked exception | Kiểm tra cause, không bỏ qua nghiệp vụ lỗi |
| `RuntimeMBeanException` | Runtime exception từ managed code/lifecycle hook | Có thể có side effects; không retry mù |
| `SecurityException` / connector auth errors | Access/security policy ngăn thao tác | Xem quyền, không tắt authentication |

Các lỗi trong bảng có thể được wrap/biểu diễn khác ở proxy hoặc remote transport. Một typed proxy không có nghĩa network partition hay connection refusal tự biến mất.

### 13.1. Kiểm tra JMX names để phân loại lỗi

~~~java
if (!server.isRegistered(name)) {
    // Có thể component chưa register hoặc đã unregister.
}
MBeanInfo info = server.getMBeanInfo(name);
for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.println(attr.getName());
}
~~~

**Đoạn trích**, không phải runnable main. `getMBeanInfo` cung cấp names/types/metadata được expose. Không log sensitive attribute **values** một cách mặc định, chỉ in metadata trong môi trường test cần thiết.

### 13.2. MBeanRegistration callback đặc biệt cần cẩn trọng

Lưu ý một tình huống theo Javadoc: nếu `postRegister` ném RuntimeException, `registerMBean` có thể ném exception **mặc dù MBean đã được thêm**. Vì vậy không nên dùng công thức “exception nghĩa là chắc chắn chưa register”. Chỉ khi bạn hiểu trạng thái thực tế và ownership mới quyết định rollback; tránh unregister MBean của module khác vì bạn không giữ bằng chứng ownership.

### 13.3. Không catch Exception rồi tiếp tục

Nếu một management MBean bắt buộc cho observability/SLA, lỗi register cần được surfaced và xử lý trong startup. Nếu chỉ là optional, app có thể degrade theo policy, nhưng phải log rõ nguyên nhân, không che xung đột namespace rồi báo system healthy giả.

## 14. Access control và remote JMX security

### 14.1. ObjectName không xác thực/ủy quyền

Một namespace như `com.mycompany.private:*` **không tạo access control**. MBeanServer + connector exposure mới xác định ai có thể đọc attributes hoặc gọi operations. Nếu bật remote JMX mà không thiết kế authentication/TLS/authorization và network isolation, các operations có thể bị lạm dụng.

### 14.2. Cẩn trọng với management operations

Không expose những phương thức nguy hiểm qua MXBean không được bảo vệ, ví dụ:

- đọc raw secrets hoặc access tokens;
- thay đổi truststore/credentials không có auth;
- xóa database/bảng dữ liệu/queue;
- chạy shell commands hoặc arbitrary scripts;
- thay đổi permission/roles;
- start/stop các production subsystems không có audit.

Một operation `reset()` trong fixture không làm gì, nên an toàn. Với production, ngay cả `resetCounters()` cũng có thể ảnh hưởng monitoring/SLOs, nên phân loại read-only và write/manage operations, phân quyền và audit riêng.

### 14.3. MBeanServer local không phải remote endpoint

Các ví dụ **không** tạo `JMXConnectorServer`, RMI registry, user/password file hay remote port. Vì vậy stdout tests chỉ chứng minh local JMX APIs. Nếu muốn remote observability, xem tài liệu quản trị JMX tương ứng JDK/framework và chỉ cấu hình trên trusted networks qua authentication/TLS, role-based access và phù hợp threat model. Không “đơn giản hóa” bằng cách mở unauthenticated public JMX/RMI port.

### 14.4. JMX được tools sử dụng nhưng không bắt buộc expose tất cả

Một service có thể xuất metrics qua Prometheus/OpenTelemetry mà không cho remote invoke JMX operations. Hãy cân nhắc:
- JMX thích hợp với **management MBeans** đã có của JVM/framework;
- Metrics exporters đọc giới hạn và chuyển thành time series;
- API health/readiness riêng có thể phục vụ load balancer;
- high cardinality hoặc dữ liệu nhạy cảm cần chính sách exposure khác.

Không thay thế cả authorization và transport security của một management endpoint chỉ bằng ObjectName đẹp.

## 15. Lifecycle, concurrency và hiệu năng

### 15.1. MXBean implementation là state thực, không phải DTO tạm

Nếu service đồng thời có worker threads cập nhật metrics, getter của MXBean có thể chạy trong management thread. Dùng `AtomicLong`, `LongAdder`, immutable snapshots hoặc synchronized blocks đúng phạm vi. Tránh:
- `counter++` không atomic;
- trả mutable collection tham chiếu nội bộ;
- getter mất vài giây chờ network/database;
- deadlock khi getter giữ lock trong khi management operation cần lock đó;
- spam notifications theo mỗi request.

### 15.2. QueryNames nhiều MBeans

`queryNames(ObjectName pattern, QueryExp query)` là công cụ tìm MBeans. Không query `*:*` liên tục mỗi vài milliseconds trong production để monitor toàn hệ thống nếu số MBeans lớn; dùng patterns có scope, caching hợp lý hoặc một metrics pipeline. Với nhiều MBeans, kết quả trả về `Set<ObjectName>` **không được hứa có thứ tự**, nên nếu cần output ổn định hãy sort theo `getCanonicalName()`.

### 15.3. Khi nào đăng ký và gỡ?

- Startup: dependency/metrics implementation sẵn sàng → register MBean.
- During runtime: chỉ thay data/operations từ cùng instance, không re-register mỗi request.
- Shutdown: stop nhận công việc, unregister MBean thuộc component, đóng resources.
- Application redeploy: tránh classloader leaks, unregister listeners và MBeans do module cũ tạo.
- Nếu registration fails, không tranh giành ObjectName của module khác.

### 15.4. Notification support là tùy chọn

MBeans có thể hỗ trợ `NotificationBroadcaster`/`NotificationEmitter` để thông báo các thay đổi, nhưng không phải MXBean nào cũng cần notifications. `NotificationBroadcasterSupport` là API còn sử dụng được, không nên phát một event cho từng metrics increment nếu có throughput lớn. Nếu có, cần sequence numbers, listener lifecycle, error handling và hiểu remote delivery khác local.

### 15.5. Register/unregister đúng ownership

Bài demo dùng boolean `owned` để chỉ unregister nếu lời gọi register đã thành công. Trong production có thể quản lý registration handle (ObjectName + server + owner identity) với lifecycle/AutoCloseable. Tuy nhiên cần cẩn trọng `MBeanRegistration.postRegister` exception như đã nêu; một handle chỉ được coi là owned sau khi đã xác nhận phù hợp registry state.

## 16. Checklist QA khi triển khai MXBean mới

| Bài kiểm tra | Kỳ vọng |
| --- | --- |
| Public interface tên MXBean hoặc gắn @MXBean | JMX nhận diện đúng |
| `JMX.isMXBeanInterface(...)` | True cho management interface |
| Return/argument types | MXBean open type mapping hợp lệ |
| Internal/PII/secrets trong methods | Không expose |
| ObjectName domain | Reverse DNS unique theo organization |
| Key names | `type,name,instance` theo convention |
| Dynamic value có dấu phẩy | Được quote và roundtrip |
| Dynamic value có `*`/`?` | Không biến exact name thành pattern |
| Name exact dùng register | `isPattern()==false` |
| Query pattern | `isPattern()==true` và match có kiểm soát |
| Two ObjectNames key order khác nhau | Canonical equality đúng |
| First register | `isRegistered==true` |
| Duplicate register | `InstanceAlreadyExistsException` |
| Random `new Object()` | `NotCompliantMBeanException` |
| Getter attribute | Correct JMX attribute name/type |
| Operation invoke | Signature/parameter types đúng |
| JMX.newMXBeanProxy | Typed access hoạt động |
| Map attribute | Server trả `TabularData` |
| Proxy map conversion | Client trả Map đúng contract |
| getMBeanInfo descriptor | `mxbean` field phù hợp |
| Two instances | Có ObjectNames riêng |
| Isolated MBeanServer | Không trộn platform registry |
| Server notifications | Nếu dùng, lifecycle và listener cleanup đúng |
| Concurrent getter/update | Không race/lost updates |
| Management getter latency | Không block quá lâu |
| Registration failure | Không nuốt lỗi hay retry ghi đè |
| Component shutdown | Unregister đúng owner |
| After cleanup | `isRegistered==false` |
| JVM redeploy/classloader | Không giữ strong references cũ |
| Remote JMX security | TLS/auth/authorization/network isolation nếu enabled |
| Java 17/21/26 | API và open type behavior regression tests |

### 16.1. Đừng test toàn bộ platform MBean count

Platform server thường có JVM MXBeans và components của libraries. Đừng assert `server.queryNames(null,null).size()==N` cho một N cố định. Chỉ assert **ObjectName bạn sở hữu** có mặt/biến mất, hoặc dùng isolated MBeanServer để kiểm soát toàn bộ registry như chương trình thứ hai.

### 16.2. Đừng dùng management test để vô tình kích hoạt production command

Các bài test nên dùng read-only getters hoặc operations có side effects nhỏ/được kiểm soát. Không dùng JMX operations nguy hiểm chỉ để đo JMX có kết nối hay chưa; nếu cần kiểm tra connection, lấy `MBeanInfo` hoặc đọc attribute không nhạy cảm.

## 17. Câu hỏi tự đánh giá

**1.** MXBean object có tự hiện trong JMX chỉ vì implement interface không?

**Đáp án:** Không. Cần đăng ký với MBeanServer bằng ObjectName (hoặc cơ chế container/framework tương đương có đăng ký thật).

**2.** `ManagementFactory.getPlatformMBeanServer()` dùng khi nào?

**Đáp án:** Khi muốn đăng ký/tra cứu JVM và application MXBeans trong platform server của process.

**3.** `MBeanServerFactory.newMBeanServer` có phải platform server không?

**Đáp án:** Không, nó tạo một MBeanServer riêng, phù hợp cho isolated tests hoặc các use cases quản trị chuyên biệt.

**4.** ObjectName gồm những phần nào?

**Đáp án:** Domain và danh sách key properties, ví dụ `com.example.app:type=Worker,name=payments`.

**5.** `ObjectName.quote` nên dùng ở đâu?

**Đáp án:** Cho giá trị động của key property, tránh special chars/wildcards tạo sai cấu trúc hoặc pattern.

**6.** Có thể đưa ObjectName pattern vào registerMBean không?

**Đáp án:** Không nên/không hợp lệ cho identity đăng ký. Dùng exact ObjectName để register, pattern cho query.

**7.** `ObjectName.equals` có phụ thuộc thứ tự key properties không?

**Đáp án:** Không, canonical ordering của key properties quyết định identity.

**8.** Lợi ích của `JMX.newMXBeanProxy`?

**Đáp án:** Truy cập attributes/operations kiểu mạnh qua Java interface, với MXBean open type conversion.

**9.** Getter `getProcessedCount` expose attribute tên gì?

**Đáp án:** `ProcessedCount`.

**10.** Dùng `invoke("recordProcessed",...,{"long"})` khác `{"java.lang.Long"}` không?

**Đáp án:** Có, signature chính xác phải theo method parameter type; ví dụ primitive `long`.

**11.** Vì sao `getAttribute("Labels")` có thể trả TabularData, còn proxy trả Map?

**Đáp án:** MXBean mapping dùng open types tại MBeanServer boundary, typed proxy chuyển về interface Java types khi có thể.

**12.** Precheck `isRegistered==false` có đảm bảo register sẽ thành công không?

**Đáp án:** Không, có race với registration của thread/component khác; phải xử lý `InstanceAlreadyExistsException`.

**13.** Có nên unregister tên đã tồn tại để giải phóng cho mình không?

**Đáp án:** Không nếu không có bằng chứng ownership; có thể xóa MBean của component khác.

**14.** `new StandardMBean(impl, interface, true)` có nghĩa gì?

**Đáp án:** Wrap implementation theo interface với MXBean semantics.

**15.** `@MXBean` đặt ở class hay interface?

**Đáp án:** Ở management interface; implementation implements interface đó.

**16.** Unregister có tự dừng thread pool/resource của implementation không?

**Đáp án:** Không. Phải quản lý resource lifecycle riêng.

**17.** Đăng ký MBean có tự mở JMX remote port không?

**Đáp án:** Không; connector configuration là việc riêng, và cần authentication/TLS/authorization khi exposed.

**18.** Nếu `postRegister` ném RuntimeException, registration chắc chắn fail hoàn toàn?

**Đáp án:** Không. Javadoc nêu có trường hợp MBean đã được đăng ký dù method báo exception; phải xác minh trạng thái trước khi retry/rollback.

### Bài tập thực hành

1. Chạy `MxBeanRegistrationDemo` trên JDK 17/21/26; so sánh output.
2. Thay `recordProcessed(3)` thành 7 và update asserted total thành 9; giải thích getter/proxy.
3. Thử `ObjectName.quote("a,b=c")`, xác minh `unquote` roundtrip.
4. Thử `ObjectName.quote("daily,*?")` và chứng minh exact name không phải pattern.
5. Đảo thứ tự key properties và so sánh `equals`/`getCanonicalName`.
6. Thêm property `instance=secondary` vào ObjectName; query với `type=Worker,*`.
7. Đăng ký hai Worker instances khác name cùng một MBeanServer, chứng minh query có hai names.
8. Thử duplicate registration song song; chỉ một operation đăng ký thành công, operation kia phải bị reject.
9. Chạy `MxBeanNamesAndOpenTypesDemo`, kiểm tra Map thành `TabularData`.
10. Đổi interface `TaskView` thành tên `TaskStatsMXBean` (vẫn public) và thử naming convention không cần annotation.
11. Bỏ `@MXBean` ở interface không kết thúc bằng `MXBean`; quan sát `NotCompliantMBeanException` khi direct register.
12. Dùng `StandardMBean(..., true)` để wrap implementation với management interface rõ.
13. Thêm boolean `isHealthy()` và xác minh JMX attribute `Healthy`.
14. Thử khai báo unsupported return type trong MXBean interface, ghi nhận lỗi compliance.
15. Thử đọc `MBeanInfo`/descriptor, không đọc dữ liệu nhạy cảm.
16. Đăng ký trên isolated server rồi query platform server; giải thích vì sao chúng khác registries.
17. Thêm lifecycle component sở hữu registration + cleanup, kiểm tra không còn MBean sau close.
18. Viết test khi getter/update được gọi đồng thời, xác minh AtomicLong không lost updates.
19. Thiết kế ObjectName factory có length validation và key names cố định.
20. Soát security review cho management interface: remove operations có destructive side effects, giới hạn JMX remote connector.
21. Test redeploy trong cùng JVM với cùng ObjectName, xác nhận cleanup tránh collision.
22. Tạo MXBean aggregate cho queue lengths (bounded), không đăng ký một MBean mới cho từng request.

## 18. Tài liệu chính thức còn áp dụng

- [Oracle Java SE 26 — MXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MXBean.html): naming/annotation detection, open types, compliant MXBean interfaces.
- [Oracle Java SE 26 — MBeanServer](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServer.html): register/unregister/isRegistered và lifecycle/exception contracts.
- [Oracle Java SE 26 — MBeanServerConnection](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServerConnection.html): attributes, operations, queries, local/remote connection interface.
- [Oracle Java SE 26 — ObjectName](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/ObjectName.html): domain/key properties, quote/unquote, patterns, canonical names.
- [Oracle Java SE 26 — StandardMBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/StandardMBean.html): explicit MXBean wrapping bằng isMXBean=true.
- [Oracle Java SE 26 — JMX](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/JMX.html): MXBean interface detection và newMXBeanProxy.
- [Oracle Java SE 26 — MBeanServerFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanServerFactory.html): create/new server semantics.
- [Oracle Java SE 26 — ObjectInstance](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/ObjectInstance.html): registered object metadata.
- [Oracle Java SE 26 — MBeanInfo](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanInfo.html): attribute/operation metadata và descriptors.
- [Oracle Java SE 26 — MBeanRegistration](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/MBeanRegistration.html): preRegister/postRegister và deregistration hooks.
- [Oracle Java SE 26 — InstanceAlreadyExistsException](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/InstanceAlreadyExistsException.html): duplicate identity.
- [Oracle Java SE 26 — NotCompliantMBeanException](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/NotCompliantMBeanException.html): compliance failures.
- [Oracle Java SE 26 — TabularData](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/openmbean/TabularData.html): open-data Map representation.
- [Oracle Java SE 26 — ManagementFactory](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/ManagementFactory.html): platform MBeanServer.
- [Oracle Java SE 26 — java.lang.management](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/package-summary.html): platform MXBeans và JMX interoperability.
- [Oracle Java SE 26 — NotificationBroadcasterSupport](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/NotificationBroadcasterSupport.html): notifications khi cần.
- [Oracle Java SE 26 — JMXConnectorServer](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/javax/management/remote/JMXConnectorServer.html): remote connector lifecycle/security implications.
- [Oracle Java SE 17 — MXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/MXBean.html): Java 17 target API availability.
- [Oracle Java SE 17 — ObjectName](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/javax/management/ObjectName.html): ObjectName grammar và quoting ở JDK17.

**Ghi nhớ:** đăng ký MXBean cần **public MXBean interface + compliant implementation + MBeanServer + exact ObjectName**. Dùng platform server cho JVM/application management, isolated server cho kiểm thử, **ObjectName.quote** cho dynamic **values**, phân biệt query **pattern** với registration **identity**, kiểm tra duplicate/ownership và unregister khi component dừng. Đối với MXBean, các Java types được chuyển qua **JMX open types** và `JMX.newMXBeanProxy` cung cấp typed access. Đặc biệt: **ObjectName không cấp quyền bảo mật**, và remote JMX connector phải được cấu hình/kiểm soát riêng trước khi expose management operations.
