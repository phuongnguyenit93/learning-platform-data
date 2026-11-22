# Connector kết nối được nhưng proxy gọi thất bại trong Spring JMX

## 1. Hiện tượng: kết nối JMX thành công không chứng minh MBean proxy hoạt động

Trong Spring Framework JMX, một client có thể tạo được `JMXConnector`, lấy `MBeanServerConnection` và thậm chí liệt kê được các MBean từ JVM đích, nhưng lời gọi trên một `MBeanProxyFactoryBean` vẫn thất bại.

Ví dụ:

```java
JMXConnector connector = JMXConnectorFactory.connect(serviceUrl, env);
MBeanServerConnection connection = connector.getMBeanServerConnection();

System.out.println(connection.getDefaultDomain()); // Thành công

WorkerManagement proxy = context.getBean(
    "workerManagementProxy", WorkerManagement.class
);

proxy.getActiveWorkers(); // Thất bại
```

Trường hợp này dễ gây nhầm lẫn vì cùng một ứng dụng đích và cùng đường mạng đã chấp nhận kết nối. Tuy nhiên, **connector readiness** và **MBean invocation readiness** là hai mức kiểm tra khác nhau:

```text
JMX connector established
         |
         v
MBeanServerConnection available
         |
         +--> queryNames(...) thành công
         |
         v
ObjectName được tìm thấy?
         |
         v
MBeanInfo có attribute / operation đúng?
         |
         v
Proxy interface ánh xạ đúng metadata?
         |
         v
Authorization, input và runtime state hợp lệ?
         |
         v
MBean target thực thi thành công
```

Một lỗi ở bất kỳ tầng nào sau bước connect đều có thể làm proxy gọi thất bại mà connector vẫn tồn tại. Vì vậy, không sửa network hoặc thay credential mù khi đã xác nhận connector hoạt động; hãy tìm **bước cụ thể đầu tiên bị lỗi**.

## 2. Phân biệt các lớp kết nối, đăng ký và thực thi

| Lớp | Phép kiểm tra | Xác nhận điều gì | Chưa xác nhận điều gì |
|---|---|---|---|
| Remote transport | `JMXConnectorFactory.connect(...)` | Có thể tạo connector | Target MBean tồn tại |
| JMX session | `getMBeanServerConnection()` | Có connection API | Quyền gọi từng operation |
| Server metadata | `getDefaultDomain()` / `queryNames()` | Server trả lời JMX request | Proxy interface tương thích |
| Registration | `isRegistered(objectName)` | ObjectName tồn tại ở thời điểm kiểm tra | MBean đáp ứng method mong đợi |
| Contract | `getMBeanInfo(objectName)` | Attribute/operation được công bố | Logic nghiệp vụ chắc chắn thành công |
| Invocation | `getAttribute`, `setAttribute`, `invoke` | Raw JMX call thực sự chạy | Proxy Spring luôn tương thích |
| Spring proxy | Gọi method của interface | End-to-end adapter + JMX | Không bảo đảm remote sẽ ổn định về sau |

**Lỗi proxy không đồng nghĩa lỗi kết nối.** Một MBeanServer có thể phục vụ `queryNames` cho caller nhưng không cho gọi một operation nhạy cảm; một MBean có thể trả đúng metadata nhưng getter lại ném exception khi dependency chưa sẵn sàng.

## 3. Các thành phần cần xác định trước khi debug

Một ứng dụng Spring dùng remote JMX proxy thường có:

- **`JMXServiceURL`**: địa chỉ của connector đích, ví dụ RMI/JMX.
- **`JMXConnector`**: session client tới server.
- **`MBeanServerConnection`**: giao diện client cho JMX operations.
- **`ObjectName`**: địa chỉ chính xác của MBean trong registry.
- **`MBeanInfo`**: metadata attribute/operation/notification đang có hiệu lực.
- **`MBeanProxyFactoryBean`**: Spring `FactoryBean` tạo typed proxy.
- **`MBeanClientInterceptor`**: lớp chuyển method của proxy thành JMX requests.
- **Management interface**: hợp đồng Java mà proxy triển khai.
- **`MBeanExporter`** phía server, nếu MBean được Spring export.

Sơ đồ:

```text
Spring client context
   |
   +-- MBeanProxyFactoryBean
          |
          +-- proxyInterface = WorkerManagement
          +-- objectName     = company.workers:type=Pool,name=primary
          +-- server         = MBeanServerConnection
          |
          v
      MBeanClientInterceptor
          |
          v
      JMXConnector / transport
          |
Remote MBeanServer
          |
          +-- ObjectName
          +-- MBeanInfo
          +-- target MBean
```

Khi debug, ghi lại URL, ObjectName, tên Java interface, phiên bản ứng dụng client/server và phiên bản Spring. Tránh ghi credential, token, raw request hoặc exception payload nhạy cảm vào log.

## 4. Bước đầu tiên: giữ connection, thử raw JMX API

Trước khi sửa `MBeanProxyFactoryBean`, lấy cùng `MBeanServerConnection` mà proxy đang sử dụng và thực hiện các phép kiểm tra nhỏ.

```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

ObjectName name = new ObjectName(
    "company.workers:type=Pool,name=primary"
);

System.out.println("Registered: " + connection.isRegistered(name));
System.out.println("Domain: " + connection.getDefaultDomain());
```

Nếu `isRegistered(name)` trả `false`, kết nối đã thành công nhưng **không có MBean tại ObjectName đó**. Chuyển sang bước 5. Nếu `true`, tiếp tục xem `MBeanInfo` ở bước 6.

Một cách liệt kê có giới hạn:

```java
for (ObjectName candidate : connection.queryNames(
        new ObjectName("company.workers:*"), null)) {
    System.out.println(candidate.getCanonicalName());
}
```

Không in toàn bộ MBean và tất cả giá trị attribute trong production. Chỉ truy vấn domain của ứng dụng để tránh làm lộ thông tin vận hành ngoài phạm vi cần thiết.

### Vì sao phải dùng **cùng** connection?

Nếu test raw API bằng `ManagementFactory.getPlatformMBeanServer()` ở **client JVM**, bạn đang truy vấn server local của client, không phải remote server. Kết quả đó không chứng minh điều gì về endpoint mà proxy đang gọi.

Tương tự, nếu client có nhiều connection beans, một connection có thể trỏ đến JVM A còn proxy sử dụng JVM B. Hãy xác nhận identity và cấu hình kết nối thực tế.

## 5. Trường hợp 1: ObjectName không tồn tại hoặc không chính xác

Đây là một nguyên nhân phổ biến:

```text
Proxy objectName:
  company.workers:type=Pool,name=primary

Server registration:
  company.worker:type=Pool,name=primary
```

Hai tên chỉ khác một chữ nhưng là hai ObjectName khác nhau. `JMXConnector` vẫn hoạt động; `getAttribute` trên tên sai có thể ném `InstanceNotFoundException` hoặc Spring wrapper tương ứng.

### 5.1. Chẩn đoán

```java
Set<ObjectName> names = connection.queryNames(
    new ObjectName("company.*:*"), null
);

names.forEach(System.out::println);
```

Trong code này cần import `java.util.Set`. Với miền sản xuất lớn, dùng query pattern hẹp hơn để tránh output quá dài.

Kiểm tra:

1. Domain chính xác?
2. Các key property `type`, `name`, `instance` có đúng?
3. ObjectName bị thay do naming strategy hoặc Spring Boot auto-configuration?
4. Server đã thực sự đăng ký target hay chỉ có bean trong `ApplicationContext`?
5. Target bị unregister/re-register sau khi proxy khởi tạo?

ObjectName là **địa chỉ registry**, không phải Spring bean name. Một bean tên `workerManagement` trong context không có nghĩa JMX ObjectName là `workerManagement`.

### 5.2. ObjectName pattern không thay thế tên thực của target

Một pattern:

```text
company.workers:type=Pool,*
```

hữu ích cho `queryNames`, nhưng một typed proxy thường cần ObjectName định vị **một MBean cụ thể**. Không dùng pattern rồi mong proxy tự chọn instance bất kỳ. Nếu có nhiều MBean matching, chọn đúng target theo tiêu chí rõ ràng.

### 5.3. ObjectName đúng vẫn có thể thay đổi trong thời gian chạy

`isRegistered(name)` là kiểm tra tại một thời điểm. Giữa bước kiểm tra và lúc proxy gọi, MBean có thể bị unregister hoặc thay thế. Do đó cần xử lý `InstanceNotFoundException` ở call path thay vì coi một lần kiểm tra `true` là bảo đảm vĩnh viễn.

## 6. Trường hợp 2: MBeanInfo không khớp interface của proxy

Đây là nguyên nhân nền tảng khác. Spring proxy chuyển method Java thành JMX call dựa trên management interface. Nhưng server chỉ hỗ trợ những attribute và operation có trong metadata.

Giả sử client dùng:

```java
public interface WorkerManagement {
    int getActiveWorkers();
    void pause();
    void setConcurrency(int value);
}
```

Server lại export:

```text
Attributes:
  ActiveWorkerCount (int, read-only)
  ConcurrencyLimit (int, read-write)

Operations:
  pauseProcessing()
```

`proxy.getActiveWorkers()`, `proxy.pause()` và `proxy.setConcurrency(4)` có thể thất bại vì **tên method/attribute khác nhau**, dù cả hai bên vẫn nói về worker pool.

### 6.1. Đọc metadata thực tế

```java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanAttributeInfo attr : info.getAttributes()) {
    System.out.printf(
        "ATTR %s type=%s readable=%s writable=%s%n",
        attr.getName(),
        attr.getType(),
        attr.isReadable(),
        attr.isWritable()
    );
}

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.println("OP " + op.getName());
    for (var parameter : op.getSignature()) {
        System.out.println(
            "  PARAM " + parameter.getType()
        );
    }
}
```

`MBeanInfo` là nguồn chính xác về hợp đồng đang được server cung cấp, thay vì suy đoán từ một interface trong source client hoặc từ bản README của phiên bản cũ.

### 6.2. Getter JavaBean và JMX attribute

Thông thường:

```java
int getActiveWorkers();
```

ánh xạ tới JMX attribute `ActiveWorkers`. Nếu server chỉ có attribute `ActiveWorkerCount`, proxy sẽ không tự dịch tên.

Tương tự:

```java
void setWarningThreshold(int value);
```

thường ánh xạ tới writable attribute `WarningThreshold`. Nếu server chỉ cung cấp read-only attribute, setter call sẽ bị từ chối.

Không dùng `getSomething()` như operation tùy ý trong khi server đã export nó thành attribute. JMX phân biệt `getAttribute` với `invoke`; Spring adapter dựa trên metadata để chọn thao tác.

## 7. Trường hợp 3: chữ ký operation hoặc kiểu tham số lệch

JMX operation được nhận diện bằng tên và chữ ký kiểu tham số.

Server:

```java
public void resizePool(int newSize);
```

Client proxy:

```java
void resizePool(long newSize);
```

Mặc dù tên giống, `int` khác `long`. Nếu call được chuyển thành `invoke` với signature `long`, server có thể không tìm thấy operation tương ứng.

Ví dụ raw call:

```java
connection.invoke(
    name,
    "resizePool",
    new Object[]{8},
    new String[]{"int"}
);
```

Trong JMX, primitive signature thường dùng tên như `"int"`, còn object type thường dùng tên fully qualified, ví dụ `"java.lang.String"`. Cần lấy chữ ký từ `MBeanOperationInfo.getSignature()` và giữ client/server tương thích.

Không giả định server tự ép `String` thành `int`, hoặc `Integer` thành `Long` cho mọi ModelMBean. Cả contract lẫn value conversion phải phù hợp.

### 7.1. Overload và interface drift

Nếu management interface có:

```java
void reset(String scope);
void reset(int scopeId);
```

proxy phải chọn đúng signature. Khi team thay đổi overload trong server mà client còn bản interface cũ, code compile được nhưng runtime JMX có thể báo operation không tồn tại.

Cách phòng ngừa là phát hành management interface dùng chung giữa client/server hoặc kiểm tra compatibility bằng metadata trong integration test.

## 8. Trường hợp 4: MBean đọc được nhưng operation bị từ chối quyền

Không phải mọi connection có quyền như nhau. Một client có thể:

- Kết nối thành công.
- Liệt kê tên MBean.
- Đọc metadata.
- Đọc một số attribute.
- Nhưng bị từ chối khi gọi operation hoặc ghi attribute.

Ví dụ tài khoản monitoring được cấu hình read-only, trong khi proxy có phương thức:

```java
void pause();
```

Lời gọi `pause()` có thể thất bại do authorization hoặc security policy. Điều đó có thể là **hành vi bảo mật đúng**, không phải lỗi của proxy.

Phân biệt:

| Kiểm tra | Nếu thành công | Nếu thất bại |
|---|---|---|
| `queryNames` | Client có thể truy vấn tên theo policy | Có thể thiếu quyền metadata |
| `getMBeanInfo` | Metadata có thể đọc | Có thể bị hạn chế |
| `getAttribute` | Được phép đọc attribute cụ thể | Có thể do quyền hoặc attribute |
| `setAttribute` | Được phép ghi và input hợp lệ | Có thể do quyền hoặc validation |
| `invoke` | Operation được cho phép và target chạy | Có thể do quyền, contract hoặc runtime |

Không nên khắc phục bằng cách cấp quyền rộng cho mọi JMX client. Nếu một operation cần đặc quyền cao hơn, tạo identity quản trị phù hợp hoặc tách ra một giao diện quản trị khác có kiểm soát.

## 9. Trường hợp 5: proxy target là Standard MBean, MXBean hay Spring ModelMBean?

Có nhiều cơ chế export trong JMX:

- **Standard MBean**: class thực hiện interface theo convention `SomethingMBean` hoặc sử dụng wrapper thích hợp.
- **MXBean**: interface `SomethingMXBean`, `@MXBean` hoặc wrapper, có quy tắc OpenType mapping.
- **Dynamic MBean**: tự mô tả metadata và xử lý access/invoke.
- **Spring ModelMBean**: Spring exporter + assembler tạo metadata từ annotation/interface/method names.

Một proxy dùng interface Standard MBean không mặc nhiên phù hợp với MXBean DTO. MXBean có thể trả dữ liệu dạng `CompositeData` hoặc `TabularData` ở raw API, trong khi typed MXBean proxy thực hiện ánh xạ sang kiểu Java phù hợp.

Ví dụ JDK:

```java
MyStatusMXBean proxy = JMX.newMXBeanProxy(
    connection,
    name,
    MyStatusMXBean.class
);
```

`MyStatusMXBean` ở đây cần là interface MXBean thực và target phải được đăng ký theo semantics MXBean. Nếu dùng `JMX.newMBeanProxy` cho MXBean có DTO phức tạp, type conversion có thể không đúng như mong đợi.

Với `MBeanProxyFactoryBean` của Spring, cần đối chiếu hỗ trợ của phiên bản Spring cụ thể cho cách proxy MXBean/ModelMBean và chọn interface tương ứng. Không lấy việc proxy tạo thành công làm bằng chứng rằng mọi kiểu trả về đều có thể chuyển đổi.

## 10. Trường hợp 6: đối tượng server chưa READY

Một MBean có thể được đăng ký khi Spring `ApplicationContext` mới refresh nhưng các công việc nền chưa hoàn tất. Ví dụ:

```text
JMX connector: READY
MBean registered: YES
Worker service: STARTING
Dependency database: NOT READY
```

`getActiveWorkers()` có thể chạy được nếu chỉ đọc một counter local. Nhưng `reloadConfiguration()` có thể thất bại vì database/config server chưa sẵn sàng.

Đây là **runtime failure của target**, không phải network failure. Hãy kiểm tra stack trace/cause phía server, trạng thái lifecycle và getter/operation đang gọi dependency nào.

Thiết kế MBean tốt nên:

- Export trạng thái như `STARTING`, `READY`, `DEGRADED`.
- Cho getter đơn giản hoạt động ngay cả khi service chưa READY.
- Guard operation thay đổi trạng thái khi dependency chưa sẵn sàng.
- Tránh gọi network nặng trong getter.
- Trả error code/exception rõ nhưng không làm lộ secret.

Không coi JMX registration thành công là bằng chứng service đã healthy.

## 11. Trường hợp 7: lỗi logic bên trong MBean

Proxy call có thể đến đúng MBean và đúng method, nhưng method ném exception:

```java
@ManagedOperation
public void refreshCache() {
    if (!cacheBackend.isAvailable()) {
        throw new IllegalStateException("Cache backend unavailable");
    }
    cacheBackend.refresh();
}
```

JMX có thể bọc exception trong `MBeanException`, `RuntimeMBeanException` hoặc wrapper của Spring JMX access. Vì vậy stack trace của client có thể bắt đầu từ proxy/interceptor, nhưng nguyên nhân gốc nằm trong target.

Khi chẩn đoán:

1. Tìm exception root cause trong `getCause()` và log server tương ứng.
2. Xác định operation đã bắt đầu chạy hay chưa.
3. Kiểm tra giá trị đầu vào và trạng thái dependency.
4. Tránh log raw payload hoặc credential trong exception message.
5. Không retry operation có side effect chỉ vì client nhận exception mơ hồ.

Một exception sau khi operation thực hiện một phần vẫn có thể để lại state đã thay đổi.

## 12. Trường hợp 8: connector vẫn có nhưng session/network không còn ổn định

Một connector từng connect thành công không bảo đảm mọi lời gọi sau vẫn chạy. Remote RMI endpoint có thể bị restart, firewall có thể ngắt kết nối idle, hoặc mạng có thể gián đoạn.

Các tình huống:

```text
T0: connect() thành công
T1: getMBeanInfo() thành công
T2: remote JVM restart
T3: proxy.getActiveWorkers() -> lỗi I/O
```

Trong trường hợp này, cần kiểm tra network/session và chiến lược reconnect. Nó khác với **MBean target trả exception** khi server vẫn hoạt động.

Nếu một call read-only thất bại do connection, có thể reconnect và thử lại theo policy có giới hạn. Với operation có tác dụng phụ, **timeout không chứng minh operation chưa chạy**. Server có thể đã thực hiện nhưng response bị mất, nên retry mù có thể gây tác dụng phụ lặp.

`MBeanClientInterceptor` hoặc connection factory ở một số phiên bản Spring có tùy chọn refresh connection on failure, nhưng không mặc định bảo đảm exactly-once hoặc phục hồi mọi loại lỗi. Cần xem chính sách theo dependency Spring đang dùng.

## 13. Trường hợp 9: trỏ nhầm JVM hoặc MBeanServer

Một ứng dụng có thể có nhiều JVM:

```text
worker-a.example.internal
worker-b.example.internal
worker-c.example.internal
```

Cũng có thể một JVM có nhiều MBeanServer. Connector connect được nhưng service URL đang trỏ tới một node khác, nơi ObjectName tồn tại với contract/version khác.

Dấu hiệu:

- Cùng ObjectName nhưng metadata khác.
- Attribute `Version` hoặc `InstanceId` (nếu có, không nhạy cảm) không khớp môi trường.
- Phản hồi thay đổi sau failover/load balancing.
- JConsole local trên server A thấy MBean, nhưng client remote kết nối server B.
- Client dùng `ManagementFactory.getPlatformMBeanServer()` local để kiểm tra trong khi proxy sử dụng remote connection.

Giải pháp là xác định endpoint thực tế từ cấu hình hiệu lực, kiểm tra identity không nhạy cảm của target và đọc `MBeanInfo` trên **chính connection mà proxy đang dùng**.

Không sửa `ObjectName` ngẫu nhiên cho tới khi call thành công, vì có thể bạn vô tình gọi operation trên MBean cùng tên thuộc instance khác.

## 14. Trường hợp 10: Spring proxy được tạo trước khi target xuất hiện

`MBeanProxyFactoryBean` là một `FactoryBean` tạo typed proxy cho MBean đích. Tạo proxy không đăng ký MBean.

Có những cách lỗi xuất hiện:

- Proxy khởi tạo và cố lấy metadata khi MBean chưa đăng ký.
- Proxy được tạo thành công nhưng lời gọi đầu tiên xảy ra trước khi exporter đăng ký target.
- Target bị unregister trong lúc context đang STOPPING.
- Server đã restart và registration được tạo lại muộn hơn connector.
- Cấu hình ObjectName hoặc `MBeanServerConnection` khác thực tế.

Nếu proxy và target cùng Spring context, có thể tổ chức dependency/lifecycle để tránh gọi sớm. Nếu target ở JVM khác, dùng trạng thái readiness và xử lý kết nối phù hợp; không dùng `@DependsOn` ở client rồi cho rằng nó sắp thứ tự khởi động của remote server.

## 15. Debug raw API trước khi debug Spring proxy

Một trình tự có thể lặp lại trong lab:

### Bước 1 — Kiểm tra registration

```java
if (!connection.isRegistered(name)) {
    throw new IllegalStateException(
        "MBean not registered: " + name
    );
}
```

### Bước 2 — Kiểm tra metadata

```java
MBeanInfo info = connection.getMBeanInfo(name);
System.out.println("Class: " + info.getClassName());
```

Không coi `getClassName()` là luôn chính xác Java business class vì Spring ModelMBean có thể báo wrapper/adapter.

### Bước 3 — Đọc attribute an toàn

```java
Object active = connection.getAttribute(name, "ActiveWorkers");
System.out.println("ActiveWorkers=" + active);
```

Chỉ chọn attribute không chứa dữ liệu nhạy cảm và không thực hiện truy vấn nặng.

### Bước 4 — Gọi operation thử trong môi trường test

```java
connection.invoke(
    name,
    "ping",
    new Object[0],
    new String[0]
);
```

Chỉ gọi nếu `ping` **thực sự được export và an toàn**. Không dùng operation như `reset`, `delete`, `restart` hoặc `rotateSecret` chỉ để kiểm tra connectivity.

### Bước 5 — Gọi proxy cùng contract

Nếu raw access thành công mà proxy thất bại, khả năng cao nằm ở cách proxy diễn giải interface, loại MBean, mapping getter/setter, signature hoặc config khác giữa raw connection và proxy.

Nếu raw access cũng thất bại, tập trung vào ObjectName, quyền, metadata và target runtime trước.

## 16. Ví dụ end-to-end: Standard MBean và JMX proxy

### 16.1. Management interface dùng chung

```java
// WorkerManagementMBean.java
public interface WorkerManagementMBean {
    int getActiveWorkers();
    int getConcurrencyLimit();
    void setConcurrencyLimit(int limit);
    void pause();
}
```

### 16.2. Implementation phía server

```java
// WorkerManagement.java
public class WorkerManagement implements WorkerManagementMBean {
    private volatile int activeWorkers = 4;
    private volatile int concurrencyLimit = 8;
    private volatile boolean paused;

    @Override
    public int getActiveWorkers() {
        return activeWorkers;
    }

    @Override
    public int getConcurrencyLimit() {
        return concurrencyLimit;
    }

    @Override
    public void setConcurrencyLimit(int limit) {
        if (limit < 1 || limit > 64) {
            throw new IllegalArgumentException("limit must be 1..64");
        }
        concurrencyLimit = limit;
    }

    @Override
    public void pause() {
        paused = true;
    }
}
```

Vì tên class `WorkerManagement` và interface `WorkerManagementMBean` khớp convention, instance có thể được đăng ký như Standard MBean.

Đăng ký local trên server:

```java
MBeanServer server = ManagementFactory.getPlatformMBeanServer();
ObjectName name = new ObjectName(
    "company.workers:type=WorkerManagement,name=primary"
);
server.registerMBean(new WorkerManagement(), name);
```

Lệnh trên **không tự mở remote connector**. Nếu client nằm ở JVM khác, server phải cấu hình `JMXConnectorServer` và security phù hợp.

### 16.3. Cấu hình client Spring

```java
import javax.management.MBeanServerConnection;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jmx.access.MBeanProxyFactoryBean;

@Configuration
public class WorkerProxyConfiguration {

    @Bean
    public MBeanProxyFactoryBean workerProxy(
            MBeanServerConnection connection) {

        MBeanProxyFactoryBean factory =
            new MBeanProxyFactoryBean();

        factory.setServer(connection);
        factory.setObjectName(
            "company.workers:type=WorkerManagement,name=primary"
        );
        factory.setProxyInterface(WorkerManagementMBean.class);
        return factory;
    }
}
```

`MBeanServerConnection` được cấp từ một connection factory khác hoặc bean cấu hình kết nối, không phải `MBeanServer` local của client. Đảm bảo client nhận đúng connection remote.

Một caller:

```java
public class WorkerDashboard {
    private final WorkerManagementMBean management;

    public WorkerDashboard(WorkerManagementMBean management) {
        this.management = management;
    }

    public int readActiveWorkers() {
        return management.getActiveWorkers();
    }
}
```

Nếu `readActiveWorkers()` lỗi, chạy các bước raw API bằng **cùng connection** để phân biệt lỗi server/contract với lỗi proxy.

## 17. Spring MBeanProxyFactoryBean và interceptor

`MBeanProxyFactoryBean` tạo proxy cho interface được chỉ định. Bên dưới, `MBeanClientInterceptor` xử lý method invocation và quyết định thực hiện JMX attribute access hoặc operation.

Ví dụ:

```text
proxy.getActiveWorkers()
  -> getAttribute(ObjectName, "ActiveWorkers")

proxy.setConcurrencyLimit(16)
  -> setAttribute(ObjectName, Attribute("ConcurrencyLimit", 16))

proxy.pause()
  -> invoke(ObjectName, "pause", [], [])
```

Đây là mô hình khái quát. Cơ chế cụ thể có thể chịu ảnh hưởng metadata, loại MBean và Spring version. Một getter JavaBeans theo tên không bảo đảm target đã export attribute đó; phải kiểm tra `MBeanInfo`.

### 17.1. Khi nào cần chọn MBeanClientInterceptor trực tiếp?

Nếu muốn custom `ProxyFactory`, thêm advice hoặc tự kiểm soát xử lý lỗi, có thể cấu hình interceptor ở mức thấp. Nhưng khi mục tiêu là typed access thông thường, `MBeanProxyFactoryBean` đơn giản hơn.

Không nên viết lớp adapter tự tạo để nuốt mọi exception rồi trả số 0 cho metrics: số 0 là giá trị nghiệp vụ có nghĩa, khác với trạng thái `UNKNOWN` do lỗi kết nối. Client monitoring nên biểu diễn dữ liệu stale hoặc unavailable rõ ràng.

## 18. Bảng phân loại exception để tìm nguyên nhân

| Exception/biểu hiện | Nguyên nhân thường gặp | Bước tiếp theo |
|---|---|---|
| `InstanceNotFoundException` | Sai ObjectName hoặc target chưa đăng ký | `queryNames`, lifecycle |
| `AttributeNotFoundException` | Attribute không tồn tại/không readable | `MBeanInfo.getAttributes()` |
| `InvalidAttributeValueException` | Setter nhận giá trị không hợp lệ | Kiểu input, validation |
| `ReflectionException` | Không tìm được method JMX tương ứng | Tên, signature, overload |
| `MBeanException` | Target operation phát exception được JMX bọc | Root cause trong server log |
| `RuntimeMBeanException` | Runtime exception từ MBean | Validation, trạng thái target |
| `SecurityException` | Thiếu quyền hoặc policy từ chối | Authentication/authorization |
| `IOException` / timeout | Session, network, connector hỏng | Server status, reconnect |
| `ClassCastException` / conversion error | Return type không đúng với client | Standard/MXBean mapping |
| Spring JMX access exception | Adapter/interceptor chuyển/bọc lỗi JMX | Xem cause chain và metadata |

Đây là dấu hiệu định hướng chứ không phải ánh xạ một-một. Cùng một lỗi root cause có thể được bọc bởi nhiều exception khác nhau ở các phiên bản Spring/JMX.

## 19. Kiểm tra cấu hình hiệu lực của Spring client

Một cấu hình trên file chưa chắc đã là cấu hình đang chạy. Trong `ApplicationContext`, cần xác định:

- Bean proxy nào được tạo bởi `MBeanProxyFactoryBean`.
- ObjectName được cấu hình có đúng với server deployment không.
- Connection bean đến từ `MBeanServerConnectionFactoryBean` hay nguồn khác.
- Service URL/credentials đang dùng có bị override bởi profile/environment không.
- Có nhiều bean cùng implement management interface làm injection chọn nhầm proxy không.
- Proxy có phải object do FactoryBean tạo ra hay caller đang inject target local.

Với `FactoryBean`, `context.getBean("workerProxy")` thường trả **product proxy**, còn `context.getBean("&workerProxy")` trả chính FactoryBean. Sự khác biệt này rất hữu ích khi debug wiring.

Nếu nhiều bean cùng management interface, dùng `@Qualifier` để chỉ rõ bean proxy:

```java
public WorkerDashboard(
    @Qualifier("workerProxy") WorkerManagementMBean management) {
    this.management = management;
}
```

Không log password/truststore contents hoặc credential environment khi điều tra.

## 20. Quy trình troubleshooting theo nhánh

```text
Connector connect được?
    |
    +-- Không -> network, URL, RMI, TLS, auth
    |
    +-- Có
         |
         v
    isRegistered(ObjectName)?
         |
         +-- Không -> naming, registration, đúng JVM?
         |
         +-- Có
              |
              v
        getMBeanInfo được?
              |
              +-- Không -> quyền/registry/target
              |
              +-- Có
                   |
                   v
         Metadata khớp proxy interface?
                   |
                   +-- Không -> sửa interface/mapping/version
                   |
                   +-- Có
                        |
                        v
              Raw JMX read/invoke được?
                        |
                        +-- Không -> quyền, validation, runtime
                        |
                        +-- Có
                             |
                             v
                    Proxy call thất bại?
                             |
                             +-- Có -> Spring wiring,
                             |          interceptor, type mapping
                             |
                             +-- Không -> theo dõi ổn định,
                                        lifecycle, reconnect
```

Thực hiện một test nhỏ cho mỗi nhánh để tránh thay đổi đồng thời URL, ObjectName, interface và security rồi không biết sửa nào tạo ra khác biệt.

## 21. Quy trình điều tra bằng log và metadata an toàn

Khi lỗi xuất hiện, ghi nhận thông tin có ích:

```text
timestamp
client application/module/version
target logical environment
service URL host/port (không chứa credential)
ObjectName
proxy interface name
method đang gọi
exception class và root cause
MBeanInfo attribute/operation signature liên quan
server lifecycle state nếu có
```

Tránh:

- In toàn bộ `Environment`, system properties hoặc credentials.
- Dump mọi JMX attribute, vì có thể chứa secret.
- Log raw request body hoặc payload người dùng.
- Tự gọi các operation nguy hiểm để xác nhận kết nối.
- Thay permission thành toàn quyền mà không phân tích nguyên nhân.

Nếu cần log server để so sánh, dùng correlation ID không nhạy cảm hoặc timestamp của operation. Phải biết đồng hồ hai máy có thể lệch khi đối chiếu thời gian.

## 22. Phòng ngừa lỗi từ trước khi triển khai

### 22.1. Management interface dùng chung

Đóng gói interface trong artifact versioned được dùng bởi client/server khi hợp lý. Điều này giảm nguy cơ lệch chữ ký và kiểu dữ liệu; vẫn cần kiểm tra metadata runtime vì server có thể dùng assembler khác.

### 22.2. Kiểm thử hợp đồng JMX

Trong integration test, đăng ký MBean vào server test rồi assert:

- ObjectName chính xác.
- `MBeanInfo` có đúng attribute, operation, signature.
- Getter an toàn có thể đọc.
- Writable attribute có validation.
- Operation không mong đợi không xuất hiện.
- Proxy cùng interface gọi được.

### 22.3. Theo dõi deployment và lifecycle

Một MBean được export trong startup có thể chưa ready. Export trạng thái `STARTING`/`READY` và yêu cầu caller kiểm tra trước operation nhạy cảm.

### 22.4. Giảm surface area

Chỉ export MBean cần thiết. Không công bố token, password hoặc raw config; tách monitoring read-only khỏi operation điều khiển khi cần.

### 22.5. Reconnect có giới hạn

Thiết kế timeout và reconnect phù hợp. Retry read-only operation có thể hợp lý; side-effect operation cần idempotency hoặc xác minh state.

### 22.6. Xác định đúng server

Trong nhiều JVM/namespace, tạo naming convention rõ ràng, ví dụ ObjectName chứa module hoặc instance id không nhạy cảm. Không dùng load-balanced endpoint theo cách làm proxy ngẫu nhiên gọi các MBean có contract khác nhau.

## 23. Bài tập thực hành

**Bài 1 — Sai ObjectName.** Đăng ký MBean tại `company.workers:type=WorkerManagement,name=primary`, cấu hình proxy dùng `name=secondary`. Xác nhận connector/raw metadata server hoạt động nhưng proxy lỗi, sau đó dùng `queryNames` tìm tên đúng.

**Bài 2 — Sai tên attribute.** Server export `ActiveWorkers`, client interface chỉ có `getActiveWorkerCount()`. Dùng `MBeanInfo` xác định sự khác biệt và sửa hợp đồng.

**Bài 3 — Lệch signature.** Server có `resizePool(int)`, client khai báo `resizePool(long)`. So sánh `MBeanOperationInfo.getSignature()` và lỗi từ raw `invoke`.

**Bài 4 — Read-only credential.** Tạo identity monitoring chỉ có quyền đọc, thử gọi operation thay đổi state. Giải thích vì sao kết nối thành công và đọc metadata được vẫn không cho phép operation.

**Bài 5 — Runtime exception.** Tạo một `@ManagedOperation` ném `IllegalStateException` khi service chưa READY. Quan sát exception chain phía proxy và server.

**Bài 6 — MXBean mapping.** Tạo MXBean trả DTO có OpenType mapping. So sánh raw `CompositeData` với typed `JMX.newMXBeanProxy` và giải thích vì sao một Standard proxy có thể sai kiểu.

**Bài 7 — Server restart.** Dùng JVM test riêng, kết nối rồi restart target. Phân biệt lỗi session và lỗi ObjectName chưa đăng ký sau restart; thiết kế reconnect/readiness.

**Bài 8 — Kiểm thử quyền và audit.** Cấu hình endpoint JMX test có authentication/TLS, dùng identity với quyền khác nhau để gọi attribute và operation; ghi lại khác biệt không tiết lộ credential.

## 24. Câu hỏi tự kiểm tra

1. `JMXConnectorFactory.connect(...)` thành công xác nhận những gì?
2. Vì sao `getDefaultDomain()` thành công không chứng minh proxy sẽ gọi được?
3. `ObjectName` và Spring bean name khác nhau như thế nào?
4. `MBeanInfo` giúp chẩn đoán lệch interface ra sao?
5. Vì sao `getActiveWorkers()` có thể không khớp attribute `ActiveWorkerCount`?
6. JMX operation signature yêu cầu những kiểu gì?
7. Một client read-only có thể kết nối nhưng không được `invoke` không?
8. Vì sao `MBeanException` có thể chỉ là wrapper của lỗi bên trong target?
9. Timeout có bảo đảm operation chưa chạy không?
10. Tại sao raw API cần dùng cùng `MBeanServerConnection` với proxy?
11. `FactoryBean` và product proxy khác nhau như thế nào khi `getBean`?
12. Vì sao không nên gọi operation có tác dụng phụ để kiểm tra connectivity?

## 25. Ghi nhớ

**Kết nối JMX thành công chỉ xác nhận rằng connector có thể giao tiếp với MBeanServer, không chứng minh một MBean cụ thể có thể được proxy gọi thành công.** Hãy đi theo thứ tự: **đúng connection → đúng ObjectName → MBeanInfo tương thích → raw JMX call → Spring proxy**.

Nếu raw API cũng lỗi, kiểm tra registration, quyền, kiểu dữ liệu và runtime của target. Nếu raw API chạy nhưng proxy lỗi, kiểm tra management interface, mapping, Spring wiring, MXBean conversion và interceptor. Với lỗi mạng, phân biệt session failure với operation failure và không retry mù các thao tác có tác dụng phụ.
