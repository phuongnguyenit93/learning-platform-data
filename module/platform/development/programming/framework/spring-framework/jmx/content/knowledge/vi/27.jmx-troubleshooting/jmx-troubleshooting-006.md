# Không gọi được JMX operation do sai chữ ký hoặc kiểu tham số trong Spring Framework

## 1. Bối cảnh và mục tiêu

Một MBean đã được đăng ký thành công, JConsole hiển thị operation, nhưng Java client gọi `MBeanServerConnection.invoke(...)` lại gặp `ReflectionException`, `IllegalArgumentException`, lỗi chuyển đổi kiểu hoặc thông báo “operation not found”. Đây là lỗi thường gặp khi Spring Framework export managed beans qua JMX và client truyền **sai tên operation, sai chữ ký kiểu tham số, hoặc giá trị không tương thích**.

Ví dụ tưởng như hợp lý nhưng sai:

```java
connection.invoke(
    objectName,
    "setLimit",
    new Object[]{10},
    new String[]{"java.lang.Integer"});
```

Nếu operation thực tế có tham số Java nguyên thủy `int`, JMX metadata có thể ghi signature là `"int"`, không phải `"java.lang.Integer"`. Hai kiểu này liên quan autoboxing trong Java source, nhưng **không phải cùng tên kiểu trong signature JMX**.

Bài này giúp bạn:

1. Hiểu cấu trúc `invoke(ObjectName, String, Object[], String[])`.
2. Phân biệt tên operation với attribute getter/setter.
3. Đọc `MBeanInfo`, `MBeanOperationInfo` và `MBeanParameterInfo` để lấy signature thật.
4. Nhận diện sai khác primitive, wrapper, array, enum, overload và `null`.
5. Hiểu ảnh hưởng của Spring annotations, exporter và proxy.
6. Phân biệt lỗi dispatch trước method với exception ném từ business method.
7. Viết client helper, integration tests và quy trình chẩn đoán an toàn.

## 2. JMX định danh một operation như thế nào?

Với API:

```java
Object result = connection.invoke(
    objectName,
    operationName,
    params,
    signature);
```

các thành phần có nghĩa:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| `objectName` | `training.spring:type=Queue,name=Orders` | Chọn MBean đã đăng ký |
| `operationName` | `"resetForQueue"` | Chọn tên operation |
| `params` | `new Object[]{"orders"}` | Giá trị argument thực tế |
| `signature` | `new String[]{"java.lang.String"}` | Tên Java types của từng argument |
| Return value | `Object` | Kết quả operation hoặc JMX/Open Type conversion |

Quan hệ bắt buộc:

```text
params.length == signature.length
```

Mỗi vị trí `signature[i]` mô tả kiểu của `params[i]` theo method được công bố. Đừng để tên kiểu trong signature phản ánh kiểu runtime của argument một cách máy móc: method nhận `long` có thể nhận giá trị Java boxed `Long`, nhưng signature vẫn cần `"long"`.

### 2.1. Quá trình dispatch

```text
JMX client
   |
   v
invoke(objectName, operationName, params, signature)
   |
   +-- MBean có tồn tại?
   |
   +-- Operation có trong MBeanInfo?
   |
   +-- Tên và signature có khớp?
   |
   +-- Kiểu argument có hợp lệ?
   |
   v
MBean implementation / Spring adapter
   |
   v
Business method
```

Nếu sai tên hoặc signature, lời gọi thường thất bại **trước khi method chạy**. Điều này khác với business method đã được gọi và chủ động ném exception.

## 3. Bài toán primitive và wrapper

Một trong các lỗi phổ biến nhất là nhầm `int` với `Integer`, `boolean` với `Boolean`.

| Method declaration | Signature JMX thường gặp |
|---|---|
| `reset(int count)` | `"int"` |
| `reset(Integer count)` | `"java.lang.Integer"` |
| `setEnabled(boolean value)` nếu expose là operation | `"boolean"` |
| `setEnabled(Boolean value)` nếu expose là operation | `"java.lang.Boolean"` |
| `sample(long duration)` | `"long"` |
| `sample(Long duration)` | `"java.lang.Long"` |
| `notify(String text)` | `"java.lang.String"` |
| `configure(double ratio)` | `"double"` |

Ví dụ đúng với method `reset(int)`:

```java
connection.invoke(
    name,
    "reset",
    new Object[]{Integer.valueOf(10)},
    new String[]{"int"});
```

Phần `params` chứa boxed value vì `Object[]` không chứa trực tiếp primitive; còn `signature` mô tả declaration của method.

Ví dụ sai nếu method khai `reset(int)`:

```java
connection.invoke(
    name,
    "reset",
    new Object[]{10},
    new String[]{Integer.class.getName()});
```

`Integer.class.getName()` trả về `"java.lang.Integer"`, không khớp declaration `int` khi JMX dispatcher yêu cầu exact signature.

### 3.1. Vì sao autoboxing không cứu được?

Khi gọi Java method trong source code, compiler có thể tự boxing/unboxing và chọn overload phù hợp. Nhưng `MBeanServerConnection.invoke` không phải một lời gọi Java source-level qua compiler. JMX nhận **mảng tên kiểu** và dùng metadata/dispatch tương ứng. Đừng suy luận “Java vẫn tự convert được nên JMX phải chạy”.

## 4. Lấy signature đúng bằng MBeanInfo

Đây là phương pháp chẩn đoán quan trọng nhất: **đọc hợp đồng runtime trước khi sửa code client**.

```java
import javax.management.*;
import java.util.Arrays;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo op : info.getOperations()) {
    System.out.print(op.getName() + "(");

    String argsText = Arrays.stream(op.getSignature())
        .map(p -> p.getType() + " " + p.getName())
        .reduce((a, b) -> a + ", " + b)
        .orElse("");

    System.out.print(argsText);
    System.out.println(") -> " + op.getReturnType());
}
```

Ví dụ output minh họa:

```text
reset(int p1) -> void
rename(java.lang.String p1) -> void
updateThreshold(long p1, boolean p2) -> void
rebuildIndex() -> java.lang.String
```

Điều đáng tin là `MBeanOperationInfo.getSignature()[i].getType()`. Tên tham số `p1` chỉ mang tính metadata, có thể thay đổi theo assembler và không bắt buộc trùng parameter name trong Java source.

### 4.1. Helper tạo signature

```java
static String[] signature(MBeanOperationInfo op) {
    return Arrays.stream(op.getSignature())
        .map(MBeanParameterInfo::getType)
        .toArray(String[]::new);
}
```

Với một operation đã chọn đúng, helper này giúp tránh tự đoán primitive hay wrapper.

Tuy nhiên, client vẫn phải chọn **đúng overload** trước khi dùng signature đó; chỉ so tên operation là chưa đủ khi có nhiều methods cùng tên.

## 5. Operation overload: cùng tên, nhiều signature

Một Java class có thể khai báo:

```java
public void reset(int count) { ... }
public void reset(String category) { ... }
```

Nếu cả hai được expose qua JMX, metadata có thể có:

```text
reset(int)
reset(java.lang.String)
```

Client phải truyền signature đúng overload:

```java
connection.invoke(
    name,
    "reset",
    new Object[]{10},
    new String[]{"int"});

connection.invoke(
    name,
    "reset",
    new Object[]{"orders"},
    new String[]{"java.lang.String"});
```

Nếu dùng `new String[0]` cho một operation nhận tham số, JMX không tự đoán từ `params`.

### 5.1. Overload và Spring annotations

Một Spring bean có thể annotate hai methods:

```java
@ManagedOperation
public void refresh(String cacheName) { ... }

@ManagedOperation
public void refresh(String cacheName, boolean force) { ... }
```

Dù cùng tên, chúng có signatures khác nhau. Khi dùng Spring `MBeanExporter` với annotation assembler, cần xác minh cả hai xuất hiện trong `MBeanInfo`, tránh assumption dựa vào source code.

### 5.2. Tránh overload quá phức tạp trong API quản trị

Nếu operation có nhiều overload gần giống nhau, tooling và operator dễ chọn nhầm. Một API quản trị rõ ràng có thể dùng tên khác:

```java
refreshCache(String cacheName)
refreshCacheForcefully(String cacheName)
```

Điều này giảm phụ thuộc vào metadata overload, đặc biệt với client scripts hoặc dashboard.

## 6. Attribute setter không đồng nghĩa operation

Đây là một lỗi rất dễ bị bỏ qua: Java method có tên `setEnabled(boolean)` thường được JMX hiểu là **setter của attribute `Enabled`**, không phải operation `setEnabled`.

Với Standard MBean:

```java
public interface ServiceControlMBean {
    boolean isEnabled();
    void setEnabled(boolean enabled);
}
```

Metadata thường có:

```text
Attribute: Enabled
  readable=true
  writable=true
  type=boolean
```

Nhưng không nhất thiết có `setEnabled` trong `MBeanInfo.getOperations()`.

Cách đúng:

```java
connection.setAttribute(
    name,
    new Attribute("Enabled", Boolean.TRUE));
```

Thay vì:

```java
connection.invoke(
    name,
    "setEnabled",
    new Object[]{true},
    new String[]{"boolean"});
```

Một Spring annotation-based MBean có thể expose setter như operation nếu metadata được cấu hình chủ đích, nhưng phải xác nhận từ `MBeanInfo`, không giả định theo tên Java method.

### 6.1. Getter cũng tương tự

`getCount()` có thể được expose thành attribute `Count`. Client nên dùng:

```java
Object count = connection.getAttribute(name, "Count");
```

không tự động coi `getCount` là operation để `invoke`.

## 7. Sai số lượng hoặc thứ tự tham số

Giả sử operation khai báo:

```java
@ManagedOperation
public void updateThreshold(long millis, boolean enabled) { ... }
```

Đúng:

```java
connection.invoke(
    name,
    "updateThreshold",
    new Object[]{1500L, true},
    new String[]{"long", "boolean"});
```

Sai số lượng:

```java
new Object[]{1500L};
new String[]{"long", "boolean"};
```

Sai thứ tự:

```java
new Object[]{true, 1500L};
new String[]{"boolean", "long"};
```

Sai kiểu:

```java
new Object[]{"1500", true};
new String[]{"java.lang.String", "boolean"};
```

JMX không mặc định parse chuỗi `"1500"` thành số `long`. Một UI như JConsole có thể hỗ trợ nhập chuỗi rồi chuyển đổi dựa trên metadata, nhưng Java API `invoke` không nên dựa vào khả năng chuyển đổi đó.

## 8. Arrays, varargs và tên class

Mảng trong Java reflection có tên không giống biểu diễn cú pháp source code.

```java
public void replaceTags(String[] tags) { ... }
```

Signature phù hợp theo tên Java reflection:

```java
String[] signature = {
    String[].class.getName()
};
```

`String[].class.getName()` trả về `"[Ljava.lang.String;"`.

Với primitive array:

```java
int[].class.getName(); // "[I"
```

Client:

```java
connection.invoke(
    name,
    "replaceTags",
    new Object[]{new String[]{"urgent", "review"}},
    new String[]{String[].class.getName()});
```

Không viết `"java.lang.String[]"` theo thói quen nếu MBeanInfo khai tên JVM reflection descriptor khác. **Luôn đọc type thực tế từ metadata**.

### 8.1. Varargs

Method:

```java
public void addTags(String... tags) { ... }
```

trong bytecode nhận một `String[]`, nên signature về bản chất là kiểu array. JMX không tự động nhận nhiều values rời như Java varargs syntax; phải truyền một phần tử trong `Object[]` là chính `String[]`.

## 9. Null argument và overload

`null` tạo vấn đề vì không có runtime class để suy ra type:

```java
connection.invoke(
    name,
    "rename",
    new Object[]{null},
    new String[]{String.class.getName()});
```

Nếu method chấp nhận nullable `String`, signature vẫn được khai báo là `java.lang.String`. Nhưng nếu nhiều overload `rename(String)` và `rename(CharSequence)`, chỉ giá trị `null` không đủ để chọn đúng method; client phải chỉ định signature.

Không truyền `null` cho primitive `int`, `long` hoặc `boolean` nếu method không có cơ chế chấp nhận nó. Dispatch/adapter có thể báo lỗi reflection hoặc argument type tùy implementation.

## 10. Enum và kiểu dữ liệu phức tạp

Method:

```java
public void changeMode(Mode mode) { ... }
```

với enum:

```java
enum Mode { NORMAL, MAINTENANCE }
```

Client local có thể truyền enum instance đúng class nếu Standard MBean interface cho phép kiểu đó:

```java
connection.invoke(
    name,
    "changeMode",
    new Object[]{Mode.MAINTENANCE},
    new String[]{Mode.class.getName()});
```

Nhưng với remote JMX, custom types cần khả năng serialization và tương thích classpath. MXBeans có cơ chế chuyển đổi types sang Open Types; ví dụ enum có thể được biểu diễn dạng `String` ở lớp Open Data, nhưng cách mapping qua MXBean proxy và metadata phải được kiểm chứng. Không suy luận mọi custom type đều an toàn hoặc portable qua JMX/RMI.

### 10.1. DTO và MXBean

Khi operation nhận cấu trúc phức tạp, có thể cần `CompositeData`, `TabularData` hoặc MXBean mapping. Nếu metadata công bố Open Type, client truyền raw Java DTO vào `invoke` có thể không khớp.

Giải pháp:

1. Xem `MBeanInfo` và Open MBean metadata nếu có.
2. Kiểm tra đó là Standard MBean, MXBean hay DynamicMBean.
3. Sử dụng client proxy MXBean và mapping phù hợp khi có thể.
4. Tránh gửi Java domain objects tùy ý qua remote JMX nếu không có hợp đồng serialization rõ.

## 11. Spring MBeanExporter và metadata có thể khác Java source

Spring có thể export bean qua:

- Standard MBean interface.
- `@ManagedResource`, `@ManagedOperation`, `@ManagedAttribute`.
- `MBeanExporter` với `MBeanInfoAssembler` tùy chỉnh.
- DynamicMBean hoặc adapter do framework sử dụng.

Ví dụ annotation:

```java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "training.spring:type=Queue,name=Orders")
public class QueueMaintenance {

    @ManagedOperation
    public void rebalance(String queue, int batchSize) {
        // Controlled maintenance operation.
    }
}
```

MBean cần được export qua `@EnableMBeanExport` hoặc `MBeanExporter` cấu hình annotation metadata phù hợp. JMX metadata thường thể hiện:

```text
rebalance(java.lang.String, int)
```

Client:

```java
connection.invoke(
    name,
    "rebalance",
    new Object[]{"orders", 100},
    new String[]{"java.lang.String", "int"});
```

Nếu exporter không expose method hoặc proxy AOP làm thay đổi method visibility, lỗi không phải do giá trị `batchSize` mà do **operation không tồn tại trong MBeanInfo**. Luôn kiểm tra registration và metadata trước.

## 12. AOP proxy và methods không nằm trên interface

Spring AOP với JDK dynamic proxy có thể chỉ công khai methods của interfaces. Một method có `@ManagedOperation` trên implementation class nhưng không có trong interface mà exporter dùng có thể bị bỏ khỏi JMX metadata, tùy cách exporter/assembler xử lý target class và proxy.

Chẩn đoán:

```java
Object bean = context.getBean("queueMaintenance");

System.out.println(
    org.springframework.aop.support.AopUtils.isAopProxy(bean));

System.out.println(
    org.springframework.aop.support.AopUtils
        .getTargetClass(bean).getName());
```

Sau đó đọc `MBeanInfo`. Nếu method thiếu hoàn toàn, đổi signature trong JMX client không giúp gì. Cần sửa exposure/management interface hoặc dùng facade quản trị riêng.

Không tắt transaction hoặc security advice chỉ để phương thức hiện lên; cần giữ contract vận hành và business semantics.

## 13. Phân biệt ReflectionException với MBeanException

| Exception | Bối cảnh thường gặp | Chẩn đoán |
|---|---|---|
| `InstanceNotFoundException` | ObjectName không được đăng ký trong server | Query MBeans/server/lifecycle |
| `ReflectionException` | Operation/signature không tìm được hoặc lỗi reflection | Xem `MBeanInfo.getOperations()` |
| `MBeanException` | Checked exception phát sinh trong managed method/adapter | Xem `getTargetException()` |
| `RuntimeMBeanException` | Runtime exception trong MBean path | Xem `getTargetException()` |
| `InvalidAttributeValueException` | Ghi attribute với giá trị không hợp lệ | Kiểm tra setter/type/range |
| `AttributeNotFoundException` | Attribute không tồn tại hoặc không writable/readable | Xem `MBeanAttributeInfo` |
| `IOException` | Remote transport/connector failure | Kiểm tra network, trạng thái operation |
| `SecurityException` | Không đủ quyền | Kiểm tra policy, không bypass |

Lỗi thực tế có thể được Spring adapter/proxy bọc theo cách khác. `ReflectionException` thường là dấu hiệu metadata/dispatch, nhưng không nên khẳng định tuyệt đối business method chưa chạy nếu chưa thấy cause và stack trace trong implementation cụ thể.

### 13.1. Đọc cause

```java
try {
    connection.invoke(
        name, "rebalance",
        new Object[]{"orders", 100},
        new String[]{"java.lang.String", "int"});

} catch (ReflectionException ex) {
    System.err.println(
        "Dispatch/reflection failed: " +
        ex.getTargetException());

} catch (MBeanException ex) {
    System.err.println(
        "MBean operation failed: " +
        ex.getTargetException());

} catch (RuntimeMBeanException ex) {
    System.err.println(
        "Runtime failure: " +
        ex.getTargetException());
}
```

Đây là ví dụ phân loại lỗi; production code không nên chỉ ghi `System.err` rồi tiếp tục như thể operation thành công. Cần trả trạng thái lỗi rõ ràng, log an toàn và không lộ dữ liệu nhạy cảm.

## 14. JConsole và công cụ GUI có thể che việc chuyển kiểu

Trong JConsole, tab **MBeans → Operations** hiển thị tên và tham số của operation. Khi người dùng nhập chữ số `100`, công cụ có thể chuyển input text thành `Integer` phù hợp với signature `int`.

Do đó:

- JConsole gọi thành công không chứng minh Java client gửi signature đúng.
- Java client có thể sai vì tự dùng `args[i].getClass().getName()`.
- GUI có thể giới hạn loại tham số được hỗ trợ.
- Messages của GUI khác nhau giữa JDK/tool versions.
- Metadata runtime đáng tin hơn việc suy đoán từ UI labels.

Nếu cùng operation chạy trong JConsole nhưng không chạy trong Java client, hãy log **tên operation, signature thực gửi và signature từ MBeanInfo** (không log secrets trong values).

## 15. Client helper: chọn operation theo signature mong đợi

Một helper đơn giản kiểm tra operation có tồn tại:

```java
import javax.management.*;
import java.util.Arrays;

public final class OperationContract {

    public static boolean hasOperation(
            MBeanServerConnection connection,
            ObjectName name,
            String operation,
            String... signature) throws Exception {

        MBeanInfo info = connection.getMBeanInfo(name);

        return Arrays.stream(info.getOperations())
            .anyMatch(op ->
                op.getName().equals(operation) &&
                Arrays.equals(
                    Arrays.stream(op.getSignature())
                        .map(MBeanParameterInfo::getType)
                        .toArray(String[]::new),
                    signature));
    }
}
```

Sử dụng:

```java
if (!OperationContract.hasOperation(
        connection, name, "rebalance",
        "java.lang.String", "int")) {
    throw new IllegalStateException(
        "Expected JMX operation signature is missing");
}

connection.invoke(
    name, "rebalance",
    new Object[]{"orders", 100},
    new String[]{"java.lang.String", "int"});
```

Helper này không thực hiện type conversion và không giải quyết vấn đề permission, MBean unregistration giữa lookup và invocation (TOCTOU), remote transport hoặc business exceptions. Nó giúp phát hiện mismatch sớm và đưa ra thông báo có ý nghĩa.

### 15.1. Không tự động invoke overload đầu tiên

Một anti-pattern:

```java
MBeanOperationInfo operation =
    Arrays.stream(info.getOperations())
        .filter(op -> op.getName().equals("refresh"))
        .findFirst()
        .orElseThrow();
```

Nếu có nhiều overload, phần tử đầu không nhất thiết là overload mong muốn. Hãy chỉ định signature đầy đủ hoặc dùng API quản trị tránh overload mơ hồ.

## 16. Kiểm thử integration bằng MBeanServer cô lập

Một ví dụ dùng Standard MBean để minh họa lỗi signature mà không phụ thuộc annotation scanning.

### 16.1. Management interface

```java
public interface QueueControlMBean {
    int getCapacity();
    void rebalance(String queue, int batchSize);
}
```

Implementation:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class QueueControl implements QueueControlMBean {
    private final AtomicInteger calls = new AtomicInteger();

    @Override
    public int getCapacity() {
        return 500;
    }

    @Override
    public void rebalance(String queue, int batchSize) {
        calls.incrementAndGet();
    }

    public int internalCallCount() {
        return calls.get();
    }
}
```

### 16.2. Test sai và đúng signature

```java
import org.junit.jupiter.api.Test;
import javax.management.*;
import static org.junit.jupiter.api.Assertions.*;

class OperationSignatureTest {

    @Test
    void wrongSignatureFailsBeforeMethodInvocation()
            throws Exception {

        MBeanServer server =
            MBeanServerFactory.newMBeanServer("test");

        QueueControl target = new QueueControl();

        ObjectName name = new ObjectName(
            "training.test:type=QueueControl,name=Orders");

        server.registerMBean(target, name);

        assertThrows(
            ReflectionException.class,
            () -> server.invoke(
                name, "rebalance",
                new Object[]{"orders", 10},
                new String[]{
                    "java.lang.String",
                    "java.lang.Integer"}));

        assertEquals(0, target.internalCallCount());

        server.invoke(
            name, "rebalance",
            new Object[]{"orders", 10},
            new String[]{"java.lang.String", "int"});

        assertEquals(1, target.internalCallCount());
    }
}
```

Trong một JVM/JMX implementation cụ thể, sai signature thường sinh `ReflectionException`. Nếu framework adapter báo exception khác, kiểm tra cause và MBeanInfo, rồi chốt test theo contract của implementation đang chạy.

### 16.3. Test operation metadata

```java
MBeanInfo info = server.getMBeanInfo(name);

MBeanOperationInfo rebalance =
    java.util.Arrays.stream(info.getOperations())
        .filter(op -> op.getName().equals("rebalance"))
        .findFirst()
        .orElseThrow();

String[] actual = java.util.Arrays.stream(
        rebalance.getSignature())
    .map(MBeanParameterInfo::getType)
    .toArray(String[]::new);

assertArrayEquals(
    new String[]{"java.lang.String", "int"},
    actual);
```

Đây là regression test hữu ích nếu một thay đổi method declaration hoặc Spring metadata assembler làm client scripts hỏng.

## 17. Negative tests nên có

| Trường hợp | Kỳ vọng |
|---|---|
| Sai ObjectName | `InstanceNotFoundException` |
| Sai operation name | Lỗi dispatch/reflection |
| Sai số lượng tham số | Lỗi invocation trước method |
| `int` vs `Integer` | Mismatch signature |
| Đảo thứ tự arguments | Mismatch hoặc argument type failure |
| `null` với primitive | Lỗi kiểu tại invocation |
| Array signature sai | Không tìm đúng operation |
| Setter được expose là attribute | Dùng `setAttribute` thay vì `invoke` |
| Business method ném exception | JMX wrapper/target cause phù hợp |
| MBean unregister giữa lookup/call | Lỗi lookup/lifecycle |

Không cần test bằng action phá hủy dữ liệu thật. Dùng test MBean có counter hoặc state trong memory.

## 18. Quy trình chẩn đoán production

Khi Java client báo “operation not found”:

**Bước 1 — Xác nhận đúng MBeanServer.** Remote connection có thể tới JVM khác hoặc exporter đăng ký vào custom server.

**Bước 2 — Kiểm tra ObjectName.**

```java
boolean exists = connection.isRegistered(name);
```

**Bước 3 — In danh sách operation metadata.** Dùng `getMBeanInfo` và `getOperations`.

**Bước 4 — So tên và signature đúng từng vị trí.** Đặc biệt primitive/wrapper, array, overload, thứ tự.

**Bước 5 — Phân biệt attribute với operation.** `setXxx` hoặc `getXxx` có thể thuộc attributes.

**Bước 6 — Kiểm tra values.** Số lượng, null, boxed values, enum/complex type.

**Bước 7 — Kiểm tra Spring exporter/assembler/AOP.** Nếu operation không nằm trong metadata, vấn đề có thể không ở client.

**Bước 8 — Đọc exception chain và server logs.** Phân biệt dispatch failure với business exception.

**Bước 9 — Kiểm thử bằng MBeanServer fixture.** Chốt regression test theo hợp đồng runtime.

**Bước 10 — Cân nhắc thay đổi API quản trị.** Nếu có overload khó dùng, thiết kế tên operation rõ ràng hơn thay vì tiếp tục dựa vào conversion ngầm.

## 19. Những anti-patterns cần tránh

1. Tạo signature bằng `args[i].getClass().getName()` cho mọi argument.
2. Dùng `"Integer"` hoặc `"String"` thay vì fully qualified type names.
3. Truyền `String` cho số rồi mong server tự parse.
4. Dùng `invoke` cho mọi `getXxx`/`setXxx`.
5. Chọn overload theo phần tử đầu tiên từ `getOperations`.
6. Bỏ qua `MBeanInfo` và chỉ sửa arguments theo phỏng đoán.
7. Bật remote JMX không bảo vệ để thử nghiệm.
8. Tự retry operation có side effect khi client gặp network timeout.
9. Log toàn bộ values nếu có thể chứa secrets.
10. Thay đổi business method signature mà không kiểm tra client JMX contract.

## 20. Bài tập thực hành

### Bài tập A — Primitive và wrapper

Tạo method `limit(int)` và gọi qua JMX bằng signature `"java.lang.Integer"`, sau đó sửa thành `"int"`. Ghi exception và xác minh method chỉ được gọi khi đúng signature.

### Bài tập B — Setter hay operation?

Tạo Standard MBean với `setEnabled(boolean)`, đọc `MBeanInfo` và xác định `Enabled` có nằm trong attributes không. Thử `invoke("setEnabled")` rồi chuyển sang `setAttribute`.

### Bài tập C — Overload

Tạo `refresh(String)` và `refresh(String, boolean)`, expose cả hai. Viết client đọc metadata và chọn đúng overload theo signature đầy đủ.

### Bài tập D — Array

Tạo `replaceTags(String[])`, in `String[].class.getName()`, gọi bằng mảng trong `Object[]`, rồi thử sai signature `"java.lang.String[]"` để quan sát sự khác biệt.

### Bài tập E — Annotation và proxy

Tạo Spring bean với `@ManagedOperation rebalance(String, int)`. Bật AOP proxy, kiểm tra `MBeanInfo` còn operation không. Viết test bảo vệ signature khi refactor.

### Bài tập F — Remote client

Trong lab đã bảo vệ connector, gọi operation từ JVM khác. So sánh lỗi signature với lỗi transport bằng cách thử tên operation sai và ngắt connection. Không làm trên production.

## 21. Câu hỏi tự kiểm tra

1. `params` và `signature` khác nhau thế nào?
2. Vì sao `int` không đồng nghĩa `java.lang.Integer` trong JMX signature?
3. Đọc signature thực tế bằng class nào của JMX API?
4. Một getter Java có luôn là JMX operation không?
5. Nếu có overload, chỉ biết tên operation đã đủ chưa?
6. `String[].class.getName()` trả về gì?
7. Vì sao `null` không giúp suy ra overload?
8. Làm thế nào phân biệt dispatch failure với business method exception?
9. Nếu `MBeanInfo` không có operation, đổi params có giúp không?
10. AOP proxy có thể ảnh hưởng metadata được export ra sao?
11. Vì sao JConsole gọi được không đảm bảo Java client có signature đúng?
12. Test nào chứng minh method không chạy khi signature sai?

## 22. Tài liệu tham khảo

- Spring Framework Reference — JMX: https://docs.spring.io/spring-framework/reference/integration/jmx.html
- Spring Framework API — `@ManagedOperation`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jmx/export/annotation/ManagedOperation.html
- Java SE 21 — `MBeanServerConnection`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanServerConnection.html
- Java SE 21 — `MBeanOperationInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanOperationInfo.html
- Java SE 21 — `MBeanParameterInfo`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/MBeanParameterInfo.html
- Java SE 21 — `ReflectionException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ReflectionException.html
- Java SE 21 — `ObjectName`: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/javax/management/ObjectName.html

**Ghi nhớ:** khi `invoke` không gọi được operation, hãy lấy `MBeanInfo` của MBean đang chạy rồi so sánh **tên operation, số lượng tham số, thứ tự và type names**. Không suy đoán signature từ runtime class của arguments. Phân biệt attribute setter/getter với operation và tách lỗi dispatch khỏi lỗi nghiệp vụ.
