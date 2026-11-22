# MBeanServer: Phân biệt lỗi tên, lỗi kiểu và lỗi thực thi operation

## 1. Vì sao cần phân biệt ba nhóm lỗi?

Trong JMX, ứng dụng quản trị gọi MBean qua \`MBeanServer\` hoặc \`MBeanServerConnection\`. Một câu lệnh có thể thất bại vì **chọn sai đối tượng hoặc thành viên**, **truyền sai kiểu/chữ ký**, hoặc **mã bên trong operation thực sự ném lỗi**. Các tình huống này có hướng xử lý khác nhau.

Hãy hình dung một lời gọi JMX đi qua ba cửa:

\`\`\`text
JMX client
    |
    v
[1] Định danh đích
    ObjectName có MBean?
    Attribute/operation có tên đúng?
    |
    v
[2] Khớp hợp đồng
    Attribute có thể đọc/ghi?
    Giá trị truyền đúng kiểu?
    Operation có đúng signature?
    |
    v
[3] Thực thi
    Getter / setter / operation được gọi
    Business logic có ném exception?
    |
    v
Trả kết quả hoặc exception cho client
\`\`\`

Điểm mấu chốt: **cùng một thông điệp "JMX call failed" không đủ để biết lỗi nằm ở đâu**. Cần xem loại exception, nguyên nhân gốc (\`cause\`/\`targetException\`), tên ObjectName, tên attribute/operation, chữ ký tham số và metadata của MBean.

Ví dụ MBean minh họa có định danh:

\`\`\`text
com.example.app:type=WorkerControl,name=main
\`\`\`

và công bố:

| Thành viên JMX | Loại | Hợp đồng |
|---|---|---|
| \`MaxThreads\` | Attribute | \`int\`, readable và writable, giá trị từ 1 đến 64 |
| \`Active\` | Attribute | \`boolean\`, chỉ đọc |
| \`ProcessedCount\` | Attribute | \`long\`, chỉ đọc |
| \`pause()\` | Operation | Không tham số, \`void\` |
| \`resize(int)\` | Operation | Một tham số primitive \`int\`, \`void\` |
| \`resetCounters()\` | Operation | Không tham số, \`void\` |

Đây là hợp đồng ví dụ; khi xử lý hệ thống thực phải đọc metadata của MBean đang được đăng ký thay vì tự suy luận từ tên class Java.

## 2. Cơ sở Java để tái hiện lỗi

Một MBean chuẩn có interface kết thúc bằng \`MBean\`. Ví dụ ngắn sau có getter, setter và operations để minh họa các đường lỗi:

\`\`\`java
package com.example.jmx;

public interface WorkerControlMBean {
    int getMaxThreads();

    void setMaxThreads(int value);

    boolean isActive();

    long getProcessedCount();

    void pause();

    void resize(int threads);

    void resetCounters();
}
\`\`\`

\`\`\`java
package com.example.jmx;

public class WorkerControl implements WorkerControlMBean {
    private int maxThreads = 8;
    private boolean active = true;
    private long processedCount = 0;

    @Override
    public synchronized int getMaxThreads() {
        return maxThreads;
    }

    @Override
    public synchronized void setMaxThreads(int value) {
        if (value < 1 || value > 64) {
            throw new IllegalArgumentException(
                "maxThreads phải nằm trong khoảng 1..64"
            );
        }
        maxThreads = value;
    }

    @Override
    public synchronized boolean isActive() {
        return active;
    }

    @Override
    public synchronized long getProcessedCount() {
        return processedCount;
    }

    @Override
    public synchronized void pause() {
        active = false;
    }

    @Override
    public synchronized void resize(int threads) {
        setMaxThreads(threads);
    }

    @Override
    public synchronized void resetCounters() {
        processedCount = 0;
    }
}
\`\`\`

Đăng ký vào MBeanServer của JVM trong một chương trình ví dụ:

\`\`\`java
package com.example.jmx;

import java.lang.management.ManagementFactory;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class RegisterWorkerMBean {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.app:type=WorkerControl,name=main"
        );

        if (!server.isRegistered(name)) {
            server.registerMBean(new WorkerControl(), name);
        }

        System.out.println(
            server.getAttribute(name, "MaxThreads")
        );
    }
}
\`\`\`

Trong ứng dụng Spring Framework, \`MBeanExporter\` có thể đăng ký bean như Standard MBean, hoặc export dạng ModelMBean dựa trên \`@ManagedResource\`, \`@ManagedAttribute\` và \`@ManagedOperation\`. Cơ chế adapter có thể làm thay đổi chi tiết exception được trả về; vẫn nên phân tích theo **bước lỗi** trước, rồi dựa vào ngoại lệ cụ thể và metadata.

Các ví dụ bên dưới sử dụng \`javax.management.*\` (gói JMX trong Java SE), dùng được cho JMX API kể cả khi MBean được quản lý qua Spring.

## 3. Nhóm 1: Lỗi tên và định danh

Lỗi tên phát sinh khi client chọn sai **ObjectName** hoặc chọn sai tên attribute/operation.

### 3.1. ObjectName hợp lệ nhưng không có MBean tương ứng

\`\`\`java
ObjectName wrongTarget = new ObjectName(
    "com.example.app:type=WorkerControl,name=secondary"
);

// Giả sử chỉ MBean name=main được đăng ký:
server.getAttribute(wrongTarget, "MaxThreads");
\`\`\`

Với \`MBeanServer\` tiêu chuẩn, lời gọi đến MBean chưa đăng ký thường ném:

\`\`\`text
javax.management.InstanceNotFoundException
\`\`\`

Kiểm tra:

\`\`\`java
boolean exists = server.isRegistered(wrongTarget);
System.out.println("registered=" + exists);

for (ObjectName candidate :
        server.queryNames(
            new ObjectName("com.example.app:type=WorkerControl,*"),
            null
        )) {
    System.out.println(candidate);
}
\`\`\`

Cần phân biệt:

- \`MalformedObjectNameException\`: cú pháp \`ObjectName\` không hợp lệ, có thể phát sinh ngay khi xây dựng \`new ObjectName(...)\`.
- \`InstanceNotFoundException\`: ObjectName đã parse được, nhưng không định vị được MBean đăng ký tại thời điểm gọi.
- \`InstanceAlreadyExistsException\`: khi **đăng ký** trùng ObjectName, không phải khi đọc attribute.

Nếu ứng dụng tự động tạo tên qua Spring exporter, hãy lấy ObjectName thực tế từ MBeanServer hoặc cấu hình export, đặc biệt khi có nhiều bean cùng loại.

### 3.2. MBean tồn tại nhưng tên attribute sai

\`\`\`java
server.getAttribute(name, "MaxThread"); // Thiếu chữ 's'
\`\`\`

Lỗi điển hình:

\`\`\`text
javax.management.AttributeNotFoundException
\`\`\`

JMX attribute name có tính phân biệt chữ hoa/chữ thường. \`MaxThreads\`, \`maxThreads\` và \`MaxThread\` không mặc nhiên là cùng một thuộc tính.

Để xem tên đúng:

\`\`\`java
import javax.management.MBeanAttributeInfo;
import javax.management.MBeanInfo;

MBeanInfo info = server.getMBeanInfo(name);

for (MBeanAttributeInfo attribute : info.getAttributes()) {
    System.out.printf(
        "%s | type=%s | read=%s | write=%s%n",
        attribute.getName(),
        attribute.getType(),
        attribute.isReadable(),
        attribute.isWritable()
    );
}
\`\`\`

Một thuộc tính tồn tại nhưng không readable hoặc không writable cũng có thể dẫn tới \`AttributeNotFoundException\` ở tương tác tương ứng. Vì vậy **thấy AttributeNotFoundException chưa đủ để kết luận chỉ sai chính tả**; cần đối chiếu quyền đọc/ghi trong metadata.

### 3.3. Tên operation sai

\`\`\`java
server.invoke(
    name,
    "paus",                 // Sai tên: pause
    new Object[0],
    new String[0]
);
\`\`\`

Tùy implementation MBean, lỗi không tìm thấy operation có thể đi ra dưới dạng \`ReflectionException\` (thường chứa nguyên nhân kiểu \`NoSuchMethodException\`) hoặc exception liên quan dispatch. Khác với attribute, không nên giả định operation sai tên sẽ phát sinh \`AttributeNotFoundException\`.

Khám phá operations:

\`\`\`java
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.print(operation.getName() + "(");
    MBeanParameterInfo[] signature = operation.getSignature();

    for (int i = 0; i < signature.length; i++) {
        if (i > 0) System.out.print(", ");
        System.out.print(signature[i].getType());
    }
    System.out.println(")");
}
\`\`\`

### 3.4. Chẩn đoán nhanh lỗi tên

1. \`ObjectName\` parse được chưa? Nếu chưa, sửa cú pháp.
2. \`server.isRegistered(name)\` có trả \`true\` tại thời điểm kiểm tra không?
3. \`getMBeanInfo(name)\` có trả metadata cho MBean cần gọi không?
4. Attribute/operation có tên **đúng từng ký tự** không?
5. Với attribute, cờ readable/writable có cho phép thao tác không?
6. Với operation, tiếp tục kiểm tra signature ở nhóm lỗi kiểu bên dưới.

Lưu ý: MBean có thể bị unregister giữa kiểm tra \`isRegistered\` và lời gọi kế tiếp; kiểm tra trước không loại bỏ hoàn toàn lỗi runtime.

## 4. Nhóm 2: Lỗi kiểu giá trị hoặc chữ ký operation

Có hai hình thức thường gặp: **attribute nhận sai kiểu dữ liệu** và **operation được invoke với danh sách kiểu tham số không khớp**.

### 4.1. Ghi attribute bằng kiểu sai

Giả sử \`MaxThreads\` có kiểu \`int\` được JMX biểu diễn khi set bằng giá trị Java tương ứng:

\`\`\`java
import javax.management.Attribute;

server.setAttribute(
    name,
    new Attribute("MaxThreads", "16") // String, không phải Integer
);
\`\`\`

Một Standard MBean có thể ném \`InvalidAttributeValueException\` do giá trị không tương thích với kiểu attribute. \`"16"\` không tự động được chuyển thành số nguyên chỉ vì nội dung chuỗi trông như một số.

Dùng đúng kiểu:

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxThreads", Integer.valueOf(16))
);
\`\`\`

Vì Java primitive \`int\` được boxing thành \`Integer\`, đối tượng mang giá trị cho setter dạng \`int\` thường là \`Integer\`; điều này khác với việc gửi \`String\`.

### 4.2. Tên đúng, signature operation sai

Giả sử operation đã đăng ký là:

\`\`\`java
void resize(int threads);
\`\`\`

Một lời gọi sai chữ ký:

\`\`\`java
server.invoke(
    name,
    "resize",
    new Object[] { Integer.valueOf(12) },
    new String[] { "java.lang.Integer" } // Sai chữ ký khai báo
);
\`\`\`

Mảng \`params\` mang giá trị runtime; mảng \`signature\` mô tả **kiểu tham số khai báo** mà MBeanServer dùng để chọn operation. Với \`resize(int)\`, kiểu cần gửi trong chữ ký là \`"int"\`:

\`\`\`java
server.invoke(
    name,
    "resize",
    new Object[] { Integer.valueOf(12) },
    new String[] { "int" }
);
\`\`\`

Tương tự:

| Khai báo Java | Chuỗi JMX signature |
|---|---|
| \`int\` | \`"int"\` |
| \`long\` | \`"long"\` |
| \`boolean\` | \`"boolean"\` |
| \`Integer\` | \`"java.lang.Integer"\` |
| \`String\` | \`"java.lang.String"\` |

Đừng thay \`"int"\` bằng \`"Integer"\`: đó không phải tên kiểu fully-qualified và cũng không phải primitive.

### 4.3. Số lượng tham số và overload

Các lỗi dưới đây không khớp \`resize(int)\`:

\`\`\`java
// Thiếu tham số
server.invoke(name, "resize", new Object[0], new String[0]);

// Chữ ký báo 2 tham số trong khi operation khai báo 1
server.invoke(
    name,
    "resize",
    new Object[] { 12, 13 },
    new String[] { "int", "int" }
);
\`\`\`

Tùy implementation, các lỗi dispatch có thể tạo \`ReflectionException\` hoặc một wrapper khác. Metadata của \`MBeanOperationInfo.getSignature()\` là nguồn xác thực đáng tin cậy nhất.

Nếu có overload \`resize(int)\` và \`resize(long)\`, \`invoke\` phải chỉ ra đúng chữ ký. Không được dựa vào ép kiểu ngầm như khi compiler Java tự lựa chọn overload tại thời điểm biên dịch.

### 4.4. Một giá trị hợp kiểu nhưng không hợp lệ về nghiệp vụ

\`\`\`java
server.setAttribute(
    name,
    new Attribute("MaxThreads", Integer.valueOf(1000))
);
\`\`\`

\`1000\` là \`Integer\`, vì vậy **không nhất thiết là lỗi kiểu JMX**. Ở ví dụ, setter mới kiểm tra giới hạn 1..64 và ném \`IllegalArgumentException\`.

Đường lỗi có thể được JMX bọc thành \`RuntimeMBeanException\` nếu runtime exception thoát khỏi MBean, hoặc thành dạng exception khác khi đi qua Spring ModelMBean/adapter. Phải xem cause để phân biệt **hợp đồng kiểu đã khớp nhưng validation nghiệp vụ thất bại** với kiểu không khớp ở lớp JMX.

Đây là ranh giới quan trọng: \`InvalidAttributeValueException\` thường gợi ý đầu vào không phù hợp với attribute; nhưng implementation có thể xử lý và map lỗi theo cách riêng. Không thể phân loại chính xác mọi trường hợp chỉ dựa vào một tên exception mà bỏ qua cause.

## 5. Nhóm 3: Lỗi khi thực thi operation

Khi ObjectName tồn tại, operation được tìm thấy và tham số khớp, logic business vẫn có thể lỗi: truy cập tài nguyên thất bại, trạng thái không cho phép, dữ liệu không hợp lệ, hoặc bug trong code.

Ví dụ một operation ném checked exception:

\`\`\`java
package com.example.jmx;

public interface MaintenanceMBean {
    void refresh() throws Exception;
}
\`\`\`

\`\`\`java
package com.example.jmx;

public class Maintenance implements MaintenanceMBean {
    @Override
    public void refresh() throws Exception {
        throw new Exception("Không đọc được nguồn cấu hình");
    }
}
\`\`\`

Khi gọi \`invoke\`, \`MBeanServer\` tiêu chuẩn thường bọc checked exception do operation ném thành \`MBeanException\`:

\`\`\`java
import javax.management.MBeanException;
import javax.management.ObjectName;

try {
    server.invoke(
        new ObjectName("com.example.app:type=Maintenance"),
        "refresh",
        new Object[0],
        new String[0]
    );
} catch (MBeanException ex) {
    Throwable businessFailure = ex.getTargetException();
    System.err.println(
        "Operation đã được gọi nhưng thất bại: "
            + businessFailure
    );
}
\`\`\`

Nếu operation ném unchecked exception như \`IllegalStateException\`, JMX thường dùng \`RuntimeMBeanException\`:

\`\`\`java
import javax.management.RuntimeMBeanException;

try {
    server.invoke(name, "resize",
        new Object[] { Integer.valueOf(-2) },
        new String[] { "int" });
} catch (RuntimeMBeanException ex) {
    RuntimeException cause = ex.getTargetException();
    System.err.println("Lỗi runtime bên trong MBean: " + cause);
}
\`\`\`

Một implementation hoặc exporter có thể map lỗi khác đi; khi bắt lỗi không nên dựa vào một wrapper duy nhất mà bỏ qua chuỗi cause.

### 5.1. Ba nhóm lỗi nhìn từ cùng một operation

Dùng \`resize(int)\` để phân biệt:

| Tình huống | Ví dụ | Bước thất bại |
|---|---|---|
| Sai tên | Gọi \`"reszie"\` | Tìm operation |
| Sai kiểu/chữ ký | Gọi \`"resize"\` với signature \`"java.lang.String"\` | Khớp contract operation |
| Logic không chấp nhận giá trị | Gọi \`resize(1000)\` đúng chữ ký \`"int"\` | Chạy setter/validation |
| Lỗi tài nguyên khi xử lý | Gọi \`refresh()\` đúng contract nhưng backend không truy cập được | Thực thi nghiệp vụ |

Đối với nhóm thứ ba, sửa tên và signature không giải quyết lỗi; cần kiểm tra log, điều kiện tiền đề, trạng thái hệ thống và nguyên nhân gốc mà MBean báo ra.

### 5.2. Operation có thể đã tạo tác dụng phụ trước khi lỗi

Một lỗi thực thi xảy ra **sau khi đã bắt đầu chạy code**, nên không được mặc định hệ thống chưa thay đổi gì. Ví dụ operation thực hiện:

\`\`\`text
1. Xóa cache cũ
2. Nạp cấu hình mới từ dịch vụ bên ngoài
3. Dịch vụ bên ngoài timeout
4. Operation ném exception
\`\`\`

Khi client nhận lỗi, cache đã bị xóa ở bước 1. Gọi lại vô điều kiện có thể tăng tải hoặc làm trạng thái khó phục hồi. Cần tài liệu hóa tính idempotent, điều kiện retry, cách quan sát trạng thái cuối và cơ chế rollback hoặc compensation nếu có.

Đặc biệt với remote JMX, lỗi kết nối hoặc timeout không cho biết chắc lời gọi đã được server nhận và thực hiện hay chưa. Phải kiểm tra trạng thái thực tế trước khi gửi lại operation có tác dụng phụ.

## 6. Phân biệt lỗi bằng API metadata và exception

Trước khi gọi, có thể sử dụng \`MBeanInfo\` để loại trừ nhiều lỗi tên/chữ ký:

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo metadata = server.getMBeanInfo(name);

for (MBeanOperationInfo operation : metadata.getOperations()) {
    System.out.print(operation.getName() + " signature=[");
    for (MBeanParameterInfo param : operation.getSignature()) {
        System.out.print(param.getType() + " ");
    }
    System.out.println("]");
}
\`\`\`

Ví dụ gọi operation với phân luồng exception cụ thể:

\`\`\`java
import javax.management.InstanceNotFoundException;
import javax.management.MBeanException;
import javax.management.ReflectionException;
import javax.management.RuntimeMBeanException;

try {
    server.invoke(
        name,
        "resize",
        new Object[] { Integer.valueOf(12) },
        new String[] { "int" }
    );
    System.out.println("Invoke thành công");
} catch (InstanceNotFoundException ex) {
    System.err.println("Sai hoặc mất ObjectName: " + name);
} catch (ReflectionException ex) {
    System.err.println(
        "Không resolve/invoke được method: " + ex.getCause()
    );
} catch (MBeanException ex) {
    System.err.println(
        "Checked exception trong MBean: " + ex.getTargetException()
    );
} catch (RuntimeMBeanException ex) {
    System.err.println(
        "Runtime exception trong MBean: " + ex.getTargetException()
    );
}
\`\`\`

Đoạn trên minh họa các exception thường gặp với Java JMX. Trong code thật cần xử lý các trường hợp khác theo contract API và kiểu \`MBeanServerConnection\` cụ thể, ví dụ \`IOException\` khi kết nối remote; kiểm tra exception declaration của method đang dùng.

Một cách chẩn đoán không phụ thuộc quá nhiều vào wrapper:

\`\`\`java
static void printCauseChain(Throwable error) {
    int depth = 0;
    for (Throwable current = error;
         current != null && depth < 12;
         current = current.getCause(), depth++) {
        System.err.println(
            depth + ": " + current.getClass().getName()
                + ": " + current.getMessage()
        );
    }
}
\`\`\`

Với các lớp wrapper JMX có \`getTargetException()\`, nên quan sát target exception rõ ràng; tùy phiên bản và implementation nó có thể cũng xuất hiện trong cause chain.

### Quy trình ra quyết định

\`\`\`text
Lời gọi thất bại
  |
  +-- ObjectName parse không được?
  |      -> Sửa cú pháp ObjectName
  |
  +-- InstanceNotFoundException?
  |      -> Xác minh registration và ObjectName
  |
  +-- AttributeNotFoundException?
  |      -> Kiểm tra tên + quyền read/write của attribute
  |
  +-- InvalidAttributeValueException?
  |      -> Kiểm tra kiểu và giá trị truyền khi set
  |
  +-- ReflectionException / không tìm thấy operation?
  |      -> Kiểm tra tên, số tham số, signature và implementation
  |
  +-- MBeanException / RuntimeMBeanException?
  |      -> Kiểm tra target exception, business log, hậu trạng thái
  |
  +-- IOException / remote timeout?
  |      -> Kiểm tra transport; không suy đoán operation chưa chạy
  |
  +-- Lỗi khác?
         -> Xem full stack trace, cause chain, metadata, adapter
\`\`\`

Sơ đồ là gợi ý ưu tiên điều tra; có trường hợp wrapper bao bọc một lỗi khác, và thứ tự kiểm tra phải dựa trên stack trace thực tế.

## 7. Lập bảng lỗi theo thao tác MBeanServer

| API | Ví dụ lỗi tên | Ví dụ lỗi kiểu/contract | Ví dụ lỗi thực thi |
|---|---|---|---|
| \`getAttribute\` | Không có MBean; sai tên attribute; attribute không readable | Thường không có tham số giá trị; client cast kết quả sai kiểu có thể gây \`ClassCastException\` phía client | Getter ném exception |
| \`setAttribute\` | Không có MBean; sai tên attribute; attribute không writable | Giá trị truyền sai kiểu hoặc bị từ chối | Setter ném exception khi xử lý |
| \`invoke\` | Không có MBean; sai operation name | Sai số lượng tham số, signature, hoặc giá trị param không hợp lệ | Operation ném checked/unchecked exception hoặc tác vụ backend thất bại |

Điều cần chú ý với **đọc thuộc tính**: \`getAttribute\` trả \`Object\`; client có thể tự tạo lỗi \`ClassCastException\` nếu giả định kết quả là \`Integer\` nhưng thực tế là \`Long\`. Đây là **lỗi giải mã/ép kiểu phía client**, không nhất thiết là MBeanServer báo \`InvalidAttributeValueException\`.

\`\`\`java
Object value = server.getAttribute(name, "ProcessedCount");

// Sai: attribute này có kiểu long -> thường trả Long
// Integer processed = (Integer) value;

// Đúng theo hợp đồng minh họa:
Long processed = (Long) value;
\`\`\`

Với operation trả kết quả, client cũng phải dùng kiểu trả về khai báo trong \`MBeanOperationInfo.getReturnType()\` để chuyển đổi an toàn.

## 8. Trường hợp đặc thù khi dùng Spring Framework JMX

Spring có thể export bean bằng \`MBeanExporter\` và các annotation:

\`\`\`java
@ManagedResource(
    objectName = "com.example.app:type=WorkerControl,name=main"
)
public class WorkerControlFacade {
    @ManagedAttribute
    public int getMaxThreads() { /* ... */ return 8; }

    @ManagedAttribute
    public void setMaxThreads(int value) { /* ... */ }

    @ManagedOperation
    public void resize(int value) { /* ... */ }
}
\`\`\`

Mã trên là phác thảo cách công bố metadata, chưa phải lớp triển khai hoàn chỉnh.

Khi xử lý lỗi JMX trong Spring, cần xác định nơi lỗi xuất hiện:

1. **Khởi động/export:** trùng ObjectName, MBean không tuân thủ chuẩn, không tìm được server, exporter cấu hình sai. Lỗi xảy ra trước khi client gọi.
2. **Client tìm nhầm tên:** tên do naming strategy hoặc annotation export khác tên client giả định. Kiểm tra MBean đã đăng ký và metadata.
3. **Khác biệt giữa phương thức Java và interface JMX:** không phải mọi public method của Spring bean đều được export; chỉ các member mà MBean contract/assembler công bố mới có thể gọi qua JMX.
4. **Adapter wrapper:** lỗi business có thể đi qua ModelMBean hoặc Spring exporter; kiểm tra target/cause và log Spring thay vì ép mọi exception vào một loại duy nhất.
5. **Proxy:** nếu bean được AOP proxy hoặc cấu hình exporter khác nhau, metadata và cách truy cập method có thể khác kỳ vọng. Đọc metadata của MBean thực tế được export.

Không nên sửa một operation thất bại bằng cách tùy tiện đổi exception mapping. Mục tiêu là giữ nguyên nguyên nhân, cung cấp thông báo dễ chẩn đoán và xử lý đúng nơi gây lỗi.

## 9. Quan sát, logging và xử lý khi production

Một thông báo lỗi có ích nên ghi:

- **Thời điểm và correlation/request ID** nếu môi trường có hỗ trợ.
- **MBean ObjectName** và MBeanServer/endpoint đang dùng.
- **Thao tác**: \`READ_ATTRIBUTE\`, \`WRITE_ATTRIBUTE\` hoặc \`INVOKE_OPERATION\`.
- **Tên attribute/operation**, signature khai báo và kiểu giá trị truyền vào.
- **Loại exception**, thông điệp, cause chain; với wrapper JMX, cả target exception.
- **Trạng thái sau lỗi** nếu an toàn để đọc, để tránh retry tạo tác dụng phụ.

Không ghi token, mật khẩu, thông tin đăng nhập JMX hoặc dữ liệu nhạy cảm vào log. Với giá trị cấu hình nhạy cảm, ghi loại và tên field thay cho raw value.

Một cấu trúc log minh họa:

\`\`\`text
event=jmx.invoke.failed
objectName=com.example.app:type=WorkerControl,name=main
operation=resize
signature=[int]
exception=javax.management.RuntimeMBeanException
rootCause=java.lang.IllegalArgumentException
message="maxThreads phải nằm trong khoảng 1..64"
\`\`\`

Với kết nối remote, phải phân biệt **lỗi dispatch JMX** với **lỗi transport/xác thực**:

- Sai credentials hoặc thiếu quyền có thể ngăn kết nối hoặc thao tác tùy cấu hình.
- RMI/network timeout có thể khiến client không nhận được kết quả dù operation đã bắt đầu.
- Remote client cần cơ chế kiểm tra hậu trạng thái qua attribute/metric hoặc trạng thái operation trước khi retry.
- Không xuất JMX remote công khai mà thiếu authentication, authorization và bảo vệ kênh truyền phù hợp.

## 10. Bài thực hành chẩn đoán

Cho MBean ví dụ với \`MaxThreads\`, \`ProcessedCount\`, \`resize(int)\` và \`pause()\`. Hãy nhận diện bước lỗi và cách khắc phục.

**Bài 1 — ObjectName không tồn tại**

\`\`\`java
server.invoke(
    new ObjectName("com.example.app:type=WorkerControl,name=backup"),
    "pause",
    new Object[0],
    new String[0]
);
\`\`\`

*Phân tích:* ObjectName hợp lệ nhưng nếu không đăng ký MBean \`name=backup\`, lỗi thuộc nhóm định danh, thường là \`InstanceNotFoundException\`. Dùng \`queryNames\` hoặc \`isRegistered\` để lấy tên đúng; không sửa operation \`pause\`.

**Bài 2 — Attribute sai tên**

\`\`\`java
server.getAttribute(name, "MaxThread");
\`\`\`

*Phân tích:* \`MaxThread\` khác \`MaxThreads\`; kỳ vọng \`AttributeNotFoundException\`. Lấy danh sách attribute từ \`getMBeanInfo\`.

**Bài 3 — Ghi attribute sai kiểu**

\`\`\`java
server.setAttribute(name, new Attribute("MaxThreads", "12"));
\`\`\`

*Phân tích:* \`String\` không khớp kiểu \`int\`; kiểm tra \`MBeanAttributeInfo.getType()\` và truyền \`Integer.valueOf(12)\`.

**Bài 4 — Operation sai chữ ký**

\`\`\`java
server.invoke(
    name, "resize",
    new Object[] { 12 },
    new String[] { "java.lang.Integer" }
);
\`\`\`

*Phân tích:* \`resize(int)\` yêu cầu signature \`"int"\`, không phải \`"java.lang.Integer"\`. Đây là lỗi dispatch/contract, không chứng minh business method đã được chạy.

**Bài 5 — Tham số đúng kiểu nhưng giá trị ngoài giới hạn**

\`\`\`java
server.invoke(
    name, "resize",
    new Object[] { 200 },
    new String[] { "int" }
);
\`\`\`

*Phân tích:* Tên và chữ ký hợp lệ; \`WorkerControl.resize\` đi vào validation và ném \`IllegalArgumentException\`. Kiểm tra \`RuntimeMBeanException.getTargetException()\` khi được bọc theo Standard MBean.

**Bài 6 — Client ép kiểu sai sau khi đọc**

\`\`\`java
Integer count =
    (Integer) server.getAttribute(name, "ProcessedCount");
\`\`\`

*Phân tích:* \`ProcessedCount\` kiểu \`long\`, thông thường kết quả là \`Long\`. Đây là \`ClassCastException\` phía Java client sau khi JMX đọc thành công.

**Bài 7 — Operation đã bắt đầu nhưng kết nối timeout**

Client gọi \`refreshCache()\`, sau đó mất kết nối trước khi có response.

*Phân tích:* Không thể kết luận operation chưa chạy. Cần đọc hậu trạng thái hoặc metric/job status bằng một kết nối mới và xác định operation có thể retry an toàn không.

## 11. Checklist chẩn đoán trước khi sửa code

1. Ghi lại câu gọi cụ thể: \`ObjectName\`, method (\`getAttribute\`, \`setAttribute\` hoặc \`invoke\`), tên member, tham số và signature.
2. Xác nhận ObjectName được parse đúng và MBean đã đăng ký.
3. Đọc \`MBeanInfo\` để đối chiếu tên, read/write flag, kiểu và chữ ký.
4. Nếu contract khớp, kiểm tra full exception cùng target/cause và log business.
5. Với lỗi bên trong operation, kiểm tra hệ thống có đổi trạng thái trước khi exception xuất hiện không.
6. Với remote timeout, xác minh trạng thái trước khi retry.
7. Khi sửa nguyên nhân, dùng lại lời gọi JMX với dữ liệu hợp lệ và quan sát kết quả thực; không chỉ kiểm tra hết exception.

## 12. Tóm tắt mô hình tư duy

**Lỗi tên**: không định vị được MBean hoặc thành viên được công bố. Xác minh \`ObjectName\`, registration và tên trong \`MBeanInfo\`.

**Lỗi kiểu/hợp đồng**: thành viên tồn tại nhưng giá trị, số tham số, chữ ký hoặc quyền truy cập không khớp. So sánh kiểu chính xác, \`isReadable/isWritable\` và \`MBeanOperationInfo.getSignature()\`.

**Lỗi thực thi**: đã tới code của MBean, nhưng setter/getter/operation không hoàn thành vì validation, trạng thái hoặc tài nguyên. Quan sát target exception, business log và hậu trạng thái; cân nhắc tác dụng phụ trước khi gọi lại.

Chẩn đoán đúng là xác định **lời gọi thất bại ở bước nào**. Exception là tín hiệu để khoanh vùng; metadata cùng cause chain và trạng thái runtime mới hoàn thiện kết luận.