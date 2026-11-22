# Spring Framework JMX — Tránh overload gây khó chọn chữ ký từ công cụ

## 1. Vấn đề: overload Java thuận tiện nhưng JMX client cần chữ ký chính xác

Trong Java, overload cho phép nhiều phương thức cùng tên nhưng khác danh sách kiểu tham số:

\`\`\`java
public void resize(int newSize) { /* ... */ }
public void resize(long newSize) { /* ... */ }
public void resize(String profile) { /* ... */ }
\`\`\`

Compiler Java có thể dựa trên kiểu biểu thức tại nơi gọi để chọn overload. Nhưng khi phương thức được export thành JMX operation, một công cụ quản trị như JConsole, VisualVM, Jolokia gateway hoặc chương trình gọi \`MBeanServerConnection.invoke\` phải xác định **operation name + parameter signature**. Không phải công cụ nào cũng hiển thị, nhập và chọn overload dễ dàng; một số giao diện còn hiển thị nhiều operation gần giống khiến người vận hành khó biết cần gọi cái nào.

Bài học này tập trung vào \`@ManagedOperation\` của Spring Framework và cách thiết kế giao diện quản trị JMX rõ ràng, ít nhầm lẫn, đặc biệt khi một Java class có overloaded methods.

Mục tiêu:
- Hiểu vì sao JMX dùng tên operation, mảng tham số và **mảng chữ ký kiểu**.
- Phân biệt tên method với chữ ký \`int\`, \`long\`, \`java.lang.Integer\` và \`java.lang.String\`.
- Nhận biết nguy cơ của overload khi dùng công cụ quản trị thủ công hoặc script.
- Thiết kế operation có tên theo ý nghĩa nghiệp vụ thay vì chỉ dựa vào overload.
- Biết cách dùng metadata \`MBeanInfo\` để truy xuất chữ ký thực tế trước khi \`invoke\`.

## 2. Mô hình tư duy: JMX operation khác lời gọi Java thông thường

Một Java caller có thể viết:

\`\`\`java
service.resize(12);
service.resize(12L);
service.resize("large");
\`\`\`

Compiler biết kiểu của từng biểu thức, thực hiện quy tắc overload resolution của Java và tạo lời gọi phù hợp.

JMX caller lại làm việc qua API:

\`\`\`java
Object result = connection.invoke(
    objectName,
    operationName,
    params,
    signature
);
\`\`\`

Trong đó:

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| \`objectName\` | Xác định MBean đã đăng ký | \`com.example:type=WorkerPool,name=main\` |
| \`operationName\` | Tên operation | \`"resize"\` |
| \`params\` | Giá trị Java gửi đến operation | \`new Object[]{12}\` |
| \`signature\` | Danh sách **tên kiểu khai báo** của tham số | \`new String[]{"int"}\` |

Công cụ không nên đoán overload chỉ dựa vào giá trị \`12\` được truyền qua mảng \`Object[]\`: phần tử đó đã là một đối tượng \`Integer\` do boxing, trong khi method JMX có thể khai báo primitive \`int\`.

Sơ đồ:

\`\`\`text
Java source
  resize(int)
  resize(long)
  resize(String)
       |
       | Spring JMX metadata assembler
       v
MBeanInfo.operations[]
  resize(signature = ["int"])
  resize(signature = ["long"])
  resize(signature = ["java.lang.String"])
       |
       | JMX client must select exact signature
       v
MBeanServerConnection.invoke(name, "resize", params, signature)
\`\`\`

**Ý chính:** \`@ManagedOperation\` công bố operation; nó không khiến mọi JMX tool có bộ giải overload giống Java compiler.

## 3. Ví dụ dễ gây khó khăn với @ManagedOperation

Giả sử có một bean điều khiển worker pool:

\`\`\`java
package com.example.jmx;

import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=WorkerPool,name=main",
    description = "Runtime worker pool controls"
)
public class WorkerPoolControl {

    @ManagedOperation(description = "Resize worker count")
    public void resize(int threads) {
        applyWorkerCount(threads);
    }

    @ManagedOperation(description = "Resize using long count")
    public void resize(long threads) {
        if (threads > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("Too many threads");
        }
        applyWorkerCount((int) threads);
    }

    @ManagedOperation(description = "Resize using named profile")
    public void resize(String profile) {
        switch (profile) {
            case "small" -> applyWorkerCount(4);
            case "medium" -> applyWorkerCount(8);
            case "large" -> applyWorkerCount(16);
            default -> throw new IllegalArgumentException(
                "Unknown profile: " + profile
            );
        }
    }

    private void applyWorkerCount(int count) {
        if (count < 1 || count > 64) {
            throw new IllegalArgumentException("count must be 1..64");
        }
        // Thực tế: gọi cơ chế cấu hình executor đang chạy.
    }
}
\`\`\`

Nếu được export bởi Spring JMX annotation infrastructure, MBean có thể công bố ba entries tên \`resize\` với signatures khác nhau.

Điều đó **không sai về mặt Java**, nhưng tạo gánh nặng cho người dùng giao diện quản trị:

- Trên một công cụ hiển thị danh sách operations, người dùng có thể nhìn thấy ba dòng \`resize\`.
- Khi gọi từ script, caller phải tự chọn \`"int"\`, \`"long"\` hoặc \`"java.lang.String"\`.
- Khi một JMX bridge nhận tham số từ JSON hoặc chuỗi văn bản, kiểu runtime có thể không đủ để chọn overload tự động.
- Khi một overload mới được thêm, công cụ hoặc script dùng cách suy đoán chữ ký có thể đổi hành vi hoặc thất bại.
- Khi log chỉ ghi \`operation=resize\`, không đủ để biết chính xác overload đã gọi.

Những rắc rối này càng rõ khi nhiều overload cùng trả về giá trị tương tự hoặc cùng có tác dụng phụ lên trạng thái production.

## 4. Vì sao signature primitive và wrapper khác nhau?

Hai khai báo Java dưới đây không có cùng JMX signature:

\`\`\`java
public void setLimit(int value);
public void setLimit(Integer value);
\`\`\`

JMX operation metadata dùng **tên kiểu khai báo**, không dùng nhãn hiển thị tự tạo:

| Khai báo Java | Chuỗi signature JMX |
|---|---|
| \`int\` | \`"int"\` |
| \`long\` | \`"long"\` |
| \`boolean\` | \`"boolean"\` |
| \`double\` | \`"double"\` |
| \`java.lang.Integer\` | \`"java.lang.Integer"\` |
| \`java.lang.Long\` | \`"java.lang.Long"\` |
| \`java.lang.String\` | \`"java.lang.String"\` |
| \`java.time.Duration\` | \`"java.time.Duration"\` |

Với Java primitive \`int\`, giá trị gửi trong \`Object[]\` vẫn là \`Integer\`:

\`\`\`java
connection.invoke(
    objectName,
    "resize",
    new Object[] { Integer.valueOf(12) },
    new String[] { "int" }
);
\`\`\`

Không thay \`"int"\` bằng \`"java.lang.Integer"\` chỉ vì phần tử trong mảng \`params\` là \`Integer\`.

Tương tự, nếu method khai báo \`long\`, dùng \`"long"\` và giá trị \`Long\` phù hợp:

\`\`\`java
connection.invoke(
    objectName,
    "resize",
    new Object[] { Long.valueOf(12L) },
    new String[] { "long" }
);
\`\`\`

**Không giả định JMX tự áp dụng numeric widening như Java compiler.** Một bridge hoặc MBean implementation có thể xử lý chuyển đổi riêng, nhưng thiết kế client đúng nên dựa vào metadata cụ thể và truyền đúng kiểu.

## 5. Lỗi phổ biến khi gọi overloaded operation

### 5.1. Sai signature dù giá trị có vẻ đúng

\`\`\`java
// Operation thực là resize(int), nhưng signature chọn Integer:
connection.invoke(
    objectName,
    "resize",
    new Object[] { 12 },
    new String[] { "java.lang.Integer" }
);
\`\`\`

Nếu MBean chỉ có \`resize(int)\`, JMX không tìm được operation với chữ ký \`java.lang.Integer\`. Tùy loại MBean và adapter, lỗi có thể đi qua \`ReflectionException\` kèm nguyên nhân như \`NoSuchMethodException\`, hoặc một dạng dispatch exception khác.

### 5.2. Không truyền signature hoặc truyền sai số tham số

\`\`\`java
connection.invoke(
    objectName,
    "resize",
    new Object[] { 12 },
    new String[0] // Không phù hợp với một tham số
);
\`\`\`

Với \`resize(int)\`, cần một entry \`"int"\`. Chữ ký số lượng không khớp khiến việc định vị operation thất bại hoặc bị implementation từ chối.

### 5.3. Gọi tên giống nhau nhưng chọn overload sai ý nghĩa

Giả sử:
- \`resize(int)\` có nghĩa số worker tuyệt đối;
- \`resize(String)\` có nghĩa profile vận hành;
- \`resize(long)\` chấp nhận số lớn nhưng có validation riêng.

Một script đọc input dạng chuỗi \`"12"\` và chọn \`resize(String)\` vì dữ liệu đầu vào là text, dù người vận hành muốn số worker tuyệt đối. Nếu Java method \`resize(String)\` chỉ hỗ trợ profile, lỗi sẽ xảy ra trong business method, không phải ở bước JMX dispatch.

Đây là ví dụ về **API không rõ ý nghĩa**, không chỉ là lỗi truyền kiểu.

### 5.4. Ghi log thiếu signature

\`\`\`text
event=jmx.invoke.failed
operation=resize
exception=ReflectionException
\`\`\`

Log này khó điều tra vì thiếu:
- ObjectName và endpoint,
- kiểu tham số được gửi,
- chữ ký mà client yêu cầu,
- chữ ký được MBean metadata công bố,
- cause/target exception.

Nên ghi:

\`\`\`text
event=jmx.invoke.failed
objectName=com.example.app:type=WorkerPool,name=main
operation=resize
signature=[java.lang.Integer]
expectedSignatures=[[int],[long],[java.lang.String]]
exception=javax.management.ReflectionException
\`\`\`

Tránh ghi giá trị tham số nhạy cảm vào log.

## 6. Cách tránh overload: đặt tên theo hành vi

Thiết kế dễ vận hành nhất thường là **mỗi JMX operation có một tên phân biệt về ý nghĩa**. Thay vì:

\`\`\`java
@ManagedOperation
public void resize(int threads) { /* ... */ }

@ManagedOperation
public void resize(String profile) { /* ... */ }
\`\`\`

hãy dùng:

\`\`\`java
@ManagedOperation(description = "Set absolute worker count")
public void setWorkerCount(int threads) {
    applyWorkerCount(threads);
}

@ManagedOperation(description = "Apply a predefined worker profile")
public void applyWorkerProfile(String profile) {
    // validate profile và cấu hình worker pool
}
\`\`\`

Và nếu cần một thao tác điều chỉnh tương đối:

\`\`\`java
@ManagedOperation(description = "Increase workers by delta")
public void increaseWorkerCount(int delta) {
    // ...
}
\`\`\`

Khi đó MBeanInfo rõ ràng:

\`\`\`text
setWorkerCount(int)
applyWorkerProfile(java.lang.String)
increaseWorkerCount(int)
\`\`\`

Ưu điểm:
1. Người vận hành đọc tên đã hiểu hành động.
2. Client ít phải phân biệt overload phức tạp.
3. Log dễ tra cứu hơn.
4. Cấu hình authorization theo operation rõ ràng hơn nếu hệ thống hỗ trợ policy chi tiết.
5. Việc thêm operation mới ít tác động đến script cũ hơn.
6. Dễ mô tả tác dụng phụ và miền giá trị của từng hành động.

**Nguyên tắc đặt tên:** dùng động từ mô tả tác dụng thực tế; tên càng đặc thù càng tốt với operation có thể thay đổi state, khởi động job hoặc xóa dữ liệu.

## 7. Khi nào nên dùng @ManagedAttribute thay vì operation?

Một số overload bắt nguồn từ việc mô hình hóa sai hành động. Ví dụ:

\`\`\`java
public void configure(int maxThreads);
public void configure(int maxThreads, int queueSize);
\`\`\`

Nếu người vận hành chỉ cần chỉnh một cấu hình độc lập, có thể expose thuộc tính:

\`\`\`java
@ManagedAttribute
public int getMaxThreads() {
    return maxThreads;
}

@ManagedAttribute
public void setMaxThreads(int value) {
    if (value < 1 || value > 64) {
        throw new IllegalArgumentException("Expected 1..64");
    }
    maxThreads = value;
}
\`\`\`

Khi cần áp dụng **nhiều cấu hình nguyên tử**, một operation có tên rõ ràng như \`reconfigurePool(int, int)\` có thể thích hợp hơn nhiều overload \`configure(...)\`.

Phân biệt:
- **Attribute:** trạng thái hoặc một giá trị cấu hình có getter/setter.
- **Operation:** hành động hoặc thao tác có nhiều bước/tác dụng phụ.
- **Không cần export:** những helper methods thuần nội bộ.

Không biến một operation nguy hiểm như \`clearCache()\` thành setter \`setClearCache(true)\` chỉ để tránh overload. Điều quan trọng là hợp đồng quản trị rõ nghĩa.

## 8. Tách API Java nội bộ và giao diện JMX

Ứng dụng có thể cần overload Java vì tiện lợi cho business code, nhưng không nhất thiết expose toàn bộ qua JMX.

Ví dụ:

\`\`\`java
public class WorkerPoolControl {
    public void resize(int threads) {
        // API nội bộ dùng nhiều nơi
    }

    public void resize(String profile) {
        // API nội bộ khác
    }

    @ManagedOperation(description = "Set worker pool size")
    public void setWorkerCount(int threads) {
        resize(threads);
    }

    @ManagedOperation(description = "Apply worker pool profile")
    public void applyWorkerProfile(String profile) {
        resize(profile);
    }
}
\`\`\`

Nếu Spring metadata assembler chỉ công bố annotated methods, \`resize\` không trở thành JMX operation, còn hai phương thức có tên rõ nghĩa được công bố.

Lợi ích của facade quản trị:
- Giữ backward compatibility của Java API nội bộ.
- Tách lifecycle và authorization cho thao tác quản trị.
- Có thể bổ sung validation chuyên biệt cho remote management.
- Có chỗ log audit và metrics riêng.
- Thay đổi implementation nội bộ mà không đổi contract JMX.

Với hệ thống lớn, có thể tạo một bean \`WorkerPoolManagementFacade\` riêng thay vì thêm mọi annotation vào lớp nghiệp vụ.

## 9. Spring Framework: tạo operation metadata với annotation

\`@ManagedOperation\` nằm trong:

\`\`\`java
org.springframework.jmx.export.annotation.ManagedOperation
\`\`\`

Bean thường dùng:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;

@ManagedResource(
    objectName = "com.example.app:type=WorkerPool,name=main"
)
public class WorkerPoolManagementFacade {
    @ManagedOperation(description = "Set exact number of workers")
    public void setWorkerCount(int count) {
        // ...
    }

    @ManagedOperation(description = "Pause new work")
    public void pauseIntake() {
        // ...
    }

    @ManagedOperation(description = "Resume new work")
    public void resumeIntake() {
        // ...
    }
}
\`\`\`

Để annotation được export, cần hạ tầng Spring JMX, ví dụ:

\`\`\`java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableMBeanExport;

@Configuration
@EnableMBeanExport
public class JmxConfig {}
\`\`\`

Hoặc có thể cấu hình \`MBeanExporter\` và \`MetadataMBeanInfoAssembler\` tường minh. Điều cần tránh là hai exporter cùng đăng ký một bean và ObjectName.

**Lưu ý:** việc thêm \`@ManagedOperation\` không tự giải quyết overload; nếu annotate nhiều phương thức trùng tên, metadata vẫn có thể chứa nhiều operation entries cùng tên và khác signature.

## 10. Thêm @ManagedOperationParameter để công cụ dễ hiểu

Spring có annotation \`@ManagedOperationParameter\` để mô tả tham số, thường dùng cùng \`@ManagedOperationParameters\`.

Ví dụ:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;

@ManagedOperation(description = "Set exact worker count")
@ManagedOperationParameters({
    @ManagedOperationParameter(
        name = "threads",
        description = "Number of workers, from 1 to 64"
    )
})
public void setWorkerCount(int threads) {
    // ...
}
\`\`\`

Metadata này giúp JMX tool hiển thị tên/mô tả tham số rõ hơn. Tuy nhiên:
- Mô tả **không thay đổi chữ ký kiểu** dùng trong \`invoke\`.
- Nó **không sửa** vấn đề ba overload cùng tên.
- Không biến String \`"12"\` thành primitive \`int\`.
- Không thay thế validation trong Java code.

Thay vì chỉ dựa vào metadata để giảm nhầm lẫn, hãy ưu tiên đặt tên operation phân biệt và chọn kiểu đầu vào đơn giản.

## 11. Kiểm tra chữ ký thực tế bằng MBeanInfo

Không nên dự đoán chữ ký từ source code rồi hardcode script mà không kiểm tra MBean đã export thực tế. Cùng bean có thể được Spring bọc trong ModelMBean, và assembler quyết định những operation nào được công bố.

Dùng Java JMX API:

\`\`\`java
import java.lang.management.ManagementFactory;
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;
import javax.management.MBeanServer;
import javax.management.ObjectName;

public class InspectJmxOperations {
    public static void main(String[] args) throws Exception {
        MBeanServer server =
            ManagementFactory.getPlatformMBeanServer();

        ObjectName name = new ObjectName(
            "com.example.app:type=WorkerPool,name=main"
        );

        MBeanInfo info = server.getMBeanInfo(name);

        for (MBeanOperationInfo operation : info.getOperations()) {
            System.out.print(operation.getName() + "(");

            MBeanParameterInfo[] params = operation.getSignature();
            for (int i = 0; i < params.length; i++) {
                if (i > 0) System.out.print(", ");
                System.out.print(params[i].getType());
            }

            System.out.println(")");
        }
    }
}
\`\`\`

Nếu output có:

\`\`\`text
setWorkerCount(int)
applyWorkerProfile(java.lang.String)
pauseIntake()
resumeIntake()
\`\`\`

thì client có đủ thông tin để gọi. Nếu output vẫn chứa nhiều \`resize\`, hãy xác định chúng có thật sự cần public qua JMX hay không.

Trong ứng dụng dùng nhiều MBeanServer, client cần dùng đúng server mà \`MBeanExporter\` đăng ký; \`getPlatformMBeanServer()\` chỉ là trường hợp phổ biến, không bảo đảm đúng mọi cấu hình.

## 12. Gọi invoke theo chữ ký rõ ràng

Giả sử metadata công bố:

\`\`\`text
setWorkerCount(int)
applyWorkerProfile(java.lang.String)
pauseIntake()
\`\`\`

Client gọi:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.app:type=WorkerPool,name=main"
);

server.invoke(
    name,
    "setWorkerCount",
    new Object[] { Integer.valueOf(12) },
    new String[] { "int" }
);

server.invoke(
    name,
    "applyWorkerProfile",
    new Object[] { "large" },
    new String[] { "java.lang.String" }
);

server.invoke(
    name,
    "pauseIntake",
    new Object[0],
    new String[0]
);
\`\`\`

Mỗi operation có tên riêng. Script không phải suy đoán giữa \`resize(int)\` và \`resize(String)\`.

### Đừng sử dụng kiểu parameter quá phức tạp nếu không cần

Ví dụ:

\`\`\`java
@ManagedOperation
public void configure(java.time.Duration timeout) { /* ... */ }
\`\`\`

Một Java client có cùng classpath có thể gửi \`Duration\`, nhưng công cụ JMX chung, remote client và các bridge dựa trên JSON có thể gặp khó với kiểu phức tạp.

Thay bằng hợp đồng dễ gọi:

\`\`\`java
@ManagedOperation(description = "Set timeout in milliseconds")
public void setTimeoutMillis(long timeoutMillis) {
    if (timeoutMillis < 0 || timeoutMillis > 600_000) {
        throw new IllegalArgumentException("Invalid timeoutMillis");
    }
    // Chuyển sang Duration trong implementation.
}
\`\`\`

Tương tự, dùng \`String\` cho enum/profile có whitelist rõ ràng, hoặc expose một số nguyên với đơn vị và miền giá trị được mô tả. Sự đơn giản ở ranh giới JMX giảm lỗi vận hành.

## 13. Nếu bắt buộc giữ overload

Đôi khi có client cũ phụ thuộc vào overload hoặc interface JMX đã được triển khai. Khi chưa thể đổi hợp đồng, cần tối thiểu:

1. Công bố **mọi signature** và ví dụ gọi cụ thể.
2. Chỉ dùng overload khi semantics thực sự cùng một hành động, không thay đổi nghĩa theo kiểu.
3. Tránh các cặp gần nhau như \`int\`/\`Integer\`, \`int\`/\`long\` nếu chúng không mang giá trị vận hành riêng.
4. Không cho JMX client suy đoán signature từ chuỗi input.
5. Kiểm tra \`MBeanInfo\` tại runtime để xây danh sách operation.
6. Dùng wrapper/client helper được kiểm soát để tạo \`params\` và \`signature\` đúng.
7. Khi thêm overload mới, xem đó là thay đổi giao diện quản trị cần kiểm tra tương thích.
8. Với operation có tác dụng phụ, xác nhận đã chọn đúng overload trước khi gọi trong production.

Ví dụ helper rõ chữ ký:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

public final class WorkerJmxClient {
    private final MBeanServerConnection connection;
    private final ObjectName name;

    public WorkerJmxClient(
            MBeanServerConnection connection,
            ObjectName name) {
        this.connection = connection;
        this.name = name;
    }

    public void resizeByCount(int count) throws Exception {
        connection.invoke(
            name,
            "resize",
            new Object[] { count },
            new String[] { "int" }
        );
    }

    public void resizeByProfile(String profile) throws Exception {
        connection.invoke(
            name,
            "resize",
            new Object[] { profile },
            new String[] { "java.lang.String" }
        );
    }
}
\`\`\`

Mặc dù JMX contract vẫn có tên \`resize\` bị overload, API client \`resizeByCount\` và \`resizeByProfile\` giúp người gọi Java không cần lặp chữ ký mỗi lần.

## 14. Dùng operation alias khi cần chuyển đổi API

Một phương án migration là duy trì overload cũ trong thời gian chuyển đổi nhưng thêm operation có tên rõ nghĩa:

\`\`\`java
@ManagedOperation(description = "Legacy resize(int)")
public void resize(int threads) {
    setWorkerCount(threads);
}

@ManagedOperation(description = "Preferred: set worker count")
public void setWorkerCount(int threads) {
    // ...
}
\`\`\`

Cần:
- Công bố tên mới trong tài liệu vận hành.
- Cập nhật dashboards/scripts từng bước.
- Theo dõi sử dụng operation cũ nếu có logging.
- Không xóa operation cũ trước khi xác nhận client đã chuyển.
- Khi remove, coi đây là thay đổi có thể phá vỡ tương thích JMX.

Nếu cần giữ Java overload nhưng không cần export qua JMX, chỉ annotate những alias quản trị. Không nhất thiết export cả bản cũ trong JMX.

## 15. Khi operation là hành động nguy hiểm

Đối với operation như:

\`\`\`java
reloadConfiguration(...)
clearCache(...)
restartWorker(...)
rotateKeys(...)
\`\`\`

overload có thể gây hậu quả lớn hơn việc chọn sai một giá trị đọc. Nên:
- Chọn tên biểu đạt scope rõ, ví dụ \`clearLocalCache\` khác \`clearDistributedCache\`.
- Dùng signature đơn giản và validate đầu vào.
- Có authorization thích hợp với remote JMX.
- Ghi audit ObjectName, operation, signature và trạng thái kết quả.
- Không ghi secret/credential vào log.
- Nếu operation có thể chạy một phần rồi thất bại, xác minh hậu trạng thái trước khi retry.
- Khi cần xác nhận thao tác nguy hiểm, bổ sung quy trình ở client/tool thay vì trông chờ Java overload giúp người dùng hiểu rủi ro.

Ví dụ hai operation cùng \`clearCache\` với \`boolean distributed\` và \`String cacheName\` rất khó hiểu khi được hiển thị trong JMX console. Tên \`clearLocalCache\`, \`clearNamedCache\` hoặc \`clearAllCaches\` phản ánh phạm vi rõ hơn.

## 16. Bảng lỗi và hướng điều tra

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| \`ReflectionException\` khi invoke | Sai operation name hoặc signature | In \`MBeanInfo.getOperations()\` |
| \`NoSuchMethodException\` trong cause | Không khớp method theo signature | So từng tên kiểu: \`int\` vs \`java.lang.Integer\` |
| Gọi thành công nhưng áp dụng sai kiểu cấu hình | Chọn overload khác ý định | Đổi tên operation theo semantics |
| JConsole hiển thị nhiều dòng trùng tên | Export nhiều overload | Hạn chế annotated methods hoặc dùng alias |
| Bridge gửi mọi tham số thành String | Mất kiểu primitive trong client | Chuyển đổi rõ theo metadata hoặc đổi API JMX |
| \`InvalidAttributeValueException\` | Thao tác này liên quan attribute, không phải operation | Phân biệt \`setAttribute\` và \`invoke\` |
| \`MBeanException\`/\`RuntimeMBeanException\` | Business logic của operation ném lỗi | Xem target exception, validation, state |
| \`InstanceNotFoundException\` | Sai ObjectName/MBean chưa đăng ký | Kiểm tra registration trước khi điều tra overload |

Không nên coi mọi \`ReflectionException\` là lỗi overload; có thể là method không tồn tại hoặc adapter không gọi được method. Kiểm tra full exception chain và metadata.

## 17. Bài thực hành

### Bài 1 — Dự đoán signature

Cho các method:

\`\`\`java
@ManagedOperation
public void schedule(int delaySeconds) { }

@ManagedOperation
public void schedule(long epochMillis) { }

@ManagedOperation
public void schedule(String cron) { }
\`\`\`

Hỏi: Các signature JMX là gì?

Đáp án:
- \`schedule(int)\` → \`["int"]\`.
- \`schedule(long)\` → \`["long"]\`.
- \`schedule(java.lang.String)\` → \`["java.lang.String"]\`.

### Bài 2 — Phát hiện lời gọi sai

\`\`\`java
connection.invoke(
    name,
    "schedule",
    new Object[] { Integer.valueOf(30) },
    new String[] { "java.lang.Integer" }
);
\`\`\`

Hỏi: Nếu chỉ có \`schedule(int)\`, phải sửa gì?

Đáp án: chữ ký phải là \`"int"\`, vì kiểu method khai báo là primitive \`int\`.

### Bài 3 — Refactor tên theo ý nghĩa

Ban đầu:

\`\`\`java
void reset();
void reset(boolean includeHistory);
void reset(String module);
\`\`\`

Thiết kế tên đề xuất:

\`\`\`java
resetCurrentCounters();
resetCountersIncludingHistory();
resetModuleCounters(String module);
\`\`\`

Tên rõ phạm vi hơn. Cũng cần cân nhắc reset history có phải operation nhạy cảm cần quyền riêng hay không.

### Bài 4 — Chọn attribute hay operation

Có hai method:
- \`setMaxThreads(int)\` thay đổi cấu hình worker;
- \`clearQueue()\` xóa công việc đang chờ.

Gợi ý:
- \`MaxThreads\` có thể là read/write \`@ManagedAttribute\` nếu là property thực sự.
- \`clearQueue()\` nên là \`@ManagedOperation\` riêng, với quyền và cảnh báo rõ.

### Bài 5 — Khi nào nên giữ overload?

Có client cũ đã dùng \`resize(int)\` nhiều năm; muốn thêm lựa chọn profile. Gợi ý:
- Giữ \`resize(int)\` cho client cũ nếu cần tương thích.
- Thêm \`applyWorkerProfile(String)\`, tránh tạo thêm \`resize(String)\`.
- Cập nhật tài liệu và theo dõi migration.

## 18. Checklist thiết kế @ManagedOperation

Trước khi công bố một operation ra JMX, hãy hỏi:

1. Tên method đã thể hiện rõ **hành động** và phạm vi chưa?
2. Có overload cùng tên trong giao diện JMX không? Nếu có, thật sự cần không?
3. \`signature\` có đơn giản và phổ biến với client không?
4. Kiểu primitive/wrapper có được sử dụng nhất quán không?
5. Các tham số có mô tả tên, đơn vị và phạm vi hợp lệ không?
6. Operation có gây thay đổi state hoặc tác dụng phụ không?
7. MBean metadata khi export có đúng ý đồ không?
8. Script có dùng signature đúng từ \`MBeanInfo\` không?
9. Có xử lý lỗi, xác minh hậu trạng thái và retry an toàn không?
10. Tên mới hoặc thay đổi overload có gây phá vỡ client hiện có không?

## 19. Tổng kết

Overload không phải anti-pattern trong Java nói chung, nhưng thường khiến **JMX management API khó vận hành hơn**. API JMX chọn operation bằng tên và danh sách kiểu tham số; signature \`"int"\`, \`"long"\` và \`"java.lang.Integer"\` là khác nhau. Khi một tool không có cách chọn overload thân thiện, người vận hành và script dễ chọn sai kiểu hoặc hiểu sai hành động.

Đối với Spring \`@ManagedOperation\`, hãy ưu tiên **tên operation duy nhất, mô tả theo nghiệp vụ**, dùng kiểu tham số dễ nhập, cung cấp metadata hữu ích và chỉ expose những phương thức cần quản trị. Nếu Java nội bộ cần overload, có thể giữ chúng ở implementation và export một facade JMX không overload. Kiểm tra \`MBeanInfo\` sau khi exporter đăng ký để xem chính xác contract mà client thực sự nhận được.