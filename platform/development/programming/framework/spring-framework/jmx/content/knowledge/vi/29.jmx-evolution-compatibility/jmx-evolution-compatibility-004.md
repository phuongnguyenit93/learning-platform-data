# Xóa operation đang được gọi từ công cụ quản trị trong Spring Framework JMX

## Mục tiêu

JMX là một API quản trị runtime. Khi Spring Framework export bean bằng \`MBeanExporter\`, \`@ManagedResource\`, \`@ManagedOperation\` hoặc Standard MBean/MXBean interface, các JMX client có thể gọi operation qua \`MBeanServerConnection.invoke()\`. Client có thể là JConsole, VisualVM, một tập lệnh vận hành, automation, monitoring agent, một control plane hoặc công cụ của đối tác nội bộ. Vì vậy, việc **xóa operation** không chỉ là refactor method Java: đó có thể là **breaking change của hợp đồng quản trị**.

Đặc biệt nguy hiểm khi operation đã được gọi tự động từ công cụ quản trị. Một thay đổi tưởng nhỏ có thể khiến runbook khẩn cấp thất bại, batch automation báo lỗi, hoặc operator thử đi thử lại một lệnh không còn tồn tại. Với operation có tác dụng phụ, việc retry hoặc fallback sai còn có thể làm trạng thái hệ thống không nhất quán.

Sau bài này, bạn có thể:

- Giải thích vì sao xóa một JMX operation có thể phá tương thích ngay cả khi ứng dụng vẫn khởi động.
- Phân biệt xóa method Java, bỏ \`@ManagedOperation\`, thay management interface và thay \`ObjectName\`.
- Nhận diện client phụ thuộc dựa trên operation name, parameter signature, return type và ObjectName.
- Lập kế hoạch inventory, deprecation, migration và removal theo phiên bản.
- Thiết kế wrapper hoặc compatibility operation để chuyển tiếp mà không giữ mã cũ mãi mãi.
- Kiểm tra tác động lên scripts, JConsole, remote clients và automation.
- Sử dụng \`MBeanInfo\` và integration tests để khóa hợp đồng quản trị.
- Thiết lập rollback, audit và thông báo thay đổi cho nhóm vận hành.

## 1. Một operation JMX là một hợp đồng công khai

Ví dụ Spring bean:

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Cache,name=Catalog",
    description = "Catalog cache administration")
public class CatalogCacheAdministration {

    @ManagedOperation(description = "Evict the entire catalog cache")
    public void clearAll() {
        // Gọi dịch vụ quản lý cache của ứng dụng.
    }
}
\`\`\`

Một JMX client có thể gọi:

\`\`\`java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;

ObjectName objectName = new ObjectName(
    "com.example.ops:type=Cache,name=Catalog");

connection.invoke(
    objectName,
    "clearAll",
    new Object[0],
    new String[0]);
\`\`\`

Lời gọi phụ thuộc vào nhiều thành phần:

| Thành phần của contract | Giá trị minh họa | Điều có thể phá client |
|---|---|---|
| MBeanServer/endpoint | JMX connector của JVM A | Di chuyển connector/server mà client không được cập nhật |
| ObjectName | \`com.example.ops:type=Cache,name=Catalog\` | Đổi domain/key properties |
| Operation name | \`clearAll\` | Xóa hoặc đổi tên |
| Parameter signature | \`[]\` | Thêm, bớt hoặc đổi kiểu tham số |
| Return value | \`void\` | Client phụ thuộc kiểu/ý nghĩa kết quả |
| Authorization | Người gọi có quyền invoke | Thay đổi policy mà không thông báo |
| Behavior | Xóa cache toàn vùng | Đổi phạm vi/tác dụng mà không cập nhật runbook |

Vì vậy, xóa \`clearAll()\` khỏi Java class chỉ là một kiểu thay đổi. Bỏ annotation \`@ManagedOperation\`, loại method khỏi management interface hoặc thay assembler cũng có thể khiến operation biến mất khỏi \`MBeanInfo\` dù method Java vẫn còn.

## 2. Phân biệt “xóa method” và “ngừng export”

Có ít nhất bốn trường hợp:

1. **Xóa method Java hoàn toàn.** Code ứng dụng hoặc các caller Java trực tiếp cũng có thể hỏng khi compile/chạy.
2. **Giữ method Java nhưng bỏ khỏi JMX metadata.** Ứng dụng nội bộ vẫn dùng được nhưng JMX client không thể invoke qua contract ấy.
3. **Giữ method nhưng đổi operation name/signature.** Client cũ không tìm thấy đúng operation.
4. **Giữ operation nhưng đổi ObjectName hoặc server đích.** JMX client cũ thấy như operation bị xóa, dù implementation vẫn tồn tại ở nơi khác.

Ví dụ:

\`\`\`java
public class CacheAdministration {

    // Không còn @ManagedOperation.
    public void clearAll() {
        // Vẫn có thể được Java code gọi.
    }
}
\`\`\`

Nếu Spring exporter dùng annotation-driven metadata, \`clearAll\` không được export theo annotation này. Nhưng nếu cùng bean được export qua assembler khác, method có thể vẫn xuất hiện. Do đó không nên dựa vào việc “đã xóa annotation” như bằng chứng cuối cùng; phải đọc \`MBeanInfo\` trên server chạy thực tế.

Đối với Standard MBean:

\`\`\`java
public interface CatalogCacheMBean {
    long getHitCount();
    void clearAll();
}
\`\`\`

Nếu loại \`clearAll()\` khỏi interface, method implementation có thể vẫn public nhưng không thuộc Standard MBean contract. Đây cũng là thay đổi breaking đối với JMX client từng gọi operation.

## 3. Vì sao công cụ quản trị thường phụ thuộc âm thầm?

Các JMX client không nhất thiết xuất hiện trong code repository ứng dụng. Chúng có thể là:
- Script Bash/PowerShell gọi JMX client.
- Job automation của nhóm SRE.
- Plugin JConsole hoặc VisualVM.
- Một chương trình Java dùng \`JMXConnectorFactory\`.
- Một trang dashboard có nút điều khiển.
- Hệ thống orchestration gọi operation khi triển khai.
- Runbook hướng dẫn operator bấm một operation cụ thể.
- Tác vụ scheduled maintenance.
- Một thư viện monitoring hoặc control plane chạy ở JVM khác.

Điều này khiến việc grep code ứng dụng chưa đủ. Một operation có thể không được gọi trong source Java nội bộ nhưng vẫn được dùng hằng tuần bởi external operator.

### 3.1 Không suy luận “ít dùng” từ metric nghiệp vụ

Nếu không có audit invocation, rất khó biết operation nào đã được gọi. Một MBean có thể được dùng chỉ khi sự cố nghiêm trọng xảy ra, nên nhiều tháng không có invocation không đồng nghĩa nó có thể xóa an toàn.

Cần inventory hệ thống quản trị, hỏi owner của runbook và có cơ chế theo dõi thực tế trước khi gỡ.

## 4. Client nhìn thấy gì khi operation bị xóa?

Sau khi thay đổi, JMX metadata không còn operation. Một lời gọi cũ:

\`\`\`java
connection.invoke(
    name,
    "clearAll",
    new Object[0],
    new String[0]);
\`\`\`

có thể thất bại bằng \`ReflectionException\` hoặc exception dispatch phù hợp với implementation/connector. Nếu chính MBean không còn tồn tại, có thể nhận \`InstanceNotFoundException\`. Với remote connection, các lỗi này có thể được bọc hoặc kèm \`IOException\` nếu transport hỏng.

Không nên khẳng định mọi JMX client đều hiển thị một thông báo giống nhau. JConsole có thể bỏ operation khỏi giao diện sau khi đọc lại metadata; script có thể vẫn cố invoke và gặp lỗi; một client cache \`MBeanInfo\` có thể hiển thị nút cũ đến khi refresh.

Phân biệt:

| Triệu chứng | Nguyên nhân khả dĩ |
|---|---|
| \`isRegistered(name)=false\` | MBean bị unregister, ObjectName đổi hoặc sai server |
| MBean có nhưng operation không nằm trong \`MBeanInfo\` | Contract đã bỏ operation |
| Operation có mặt nhưng invoke lỗi | Sai signature, quyền, implementation exception |
| Client báo timeout | Có thể kết nối/operation chậm, không chứng minh operation bị xóa |
| Script compile nhưng runtime fail | JMX invocation thường dùng tên string, không được compiler kiểm tra |
| JConsole thiếu nút sau deploy | Metadata runtime đã đổi hoặc client nhìn server khác |

Cần kiểm tra đúng server, ObjectName và \`MBeanInfo\` trước khi kết luận lỗi do xóa operation.

## 5. Bước 1: inventory operation trước khi xóa

Lập bảng ít nhất:

| Trường | Ví dụ |
|---|---|
| ObjectName | \`com.example.ops:type=Cache,name=Catalog\` |
| Operation name | \`clearAll\` |
| Signature | Không tham số |
| Return type | \`void\` |
| Current behavior | Evict toàn bộ cache trong một JVM |
| Rủi ro tác dụng phụ | Cache miss tăng, downstream quá tải |
| Chủ sở hữu | Nhóm vận hành cache |
| Clients đang dùng | Runbook R-12, script deployment, dashboard |
| Lần gọi gần nhất | Dựa trên audit nếu có |
| Replacement | \`requestEviction(String region, String requestId)\` |
| Phiên bản dự kiến bỏ | Theo kế hoạch release |
| Kế hoạch rollback | Giữ compatibility adapter trong giai đoạn chuyển tiếp |

Chỉ lập danh sách trên tài liệu mà không xác minh runtime là chưa đủ. Một exporter có thể tự phát hiện thêm operation, hoặc proxy/assembler có thể thay metadata.

### 5.1 Trích xuất contract từ MBeanInfo

\`\`\`java
import javax.management.MBeanInfo;
import javax.management.MBeanOperationInfo;
import javax.management.MBeanParameterInfo;

MBeanInfo info = connection.getMBeanInfo(name);

for (MBeanOperationInfo operation : info.getOperations()) {
    System.out.println("operation=" + operation.getName());
    for (MBeanParameterInfo parameter : operation.getSignature()) {
        System.out.println("  parameterType=" + parameter.getType());
    }
    System.out.println("returnType=" + operation.getReturnType());
}
\`\`\`

Với overloaded operations, chỉ kiểm tra tên là chưa đủ. Một method \`reset(String)\` và \`reset(long)\` có cùng operation name nhưng contract khác.

Nếu đổi \`int\` thành \`Integer\`, client truyền signature \`"int"\` cũ có thể không còn khớp. Đây là thay đổi tương thích JMX ngay cả khi tên operation giữ nguyên.

## 6. Bước 2: tìm dependency từ phía công cụ quản trị

Nguồn cần khảo sát:
1. Source của CLI, script vận hành, control plane và plugin JMX.
2. Job scheduler, pipeline, runbook, dashboard có operation buttons.
3. Danh sách người có quyền JMX và nhóm sở hữu.
4. Logs/audit của JMX invocation nếu hệ thống có.
5. Cấu hình endpoint và ObjectName được hard-code.
6. Môi trường staging, production và các phiên bản ứng dụng đang chạy song song.
7. Hệ thống disaster recovery nơi operation chỉ được dùng hiếm khi.

Tránh ghi raw secrets, JMX credentials hoặc payload nhạy cảm vào quá trình inventory. Việc tìm client phải bao gồm cả các công cụ ngoài repository ứng dụng.

### 6.1 Nếu chưa có audit invocation

Không nên tuyên bố “không ai sử dụng” chỉ vì tìm không thấy string trong code. Có thể bổ sung logging/audit ở management adapter hoặc control plane được bảo vệ. Khi JMX MBeanServer hoặc connector không cung cấp identity đáng tin cậy ở method level, không được tin một tham số \`actor\` do client tự truyền là danh tính đã xác thực.

Bật metric số lần gọi operation và trạng thái thành công/thất bại có thể giúp đánh giá usage, nhưng phải tránh làm lộ parameter có secret. Đối với operation hiếm nhưng quan trọng, có thể cần xác nhận trực tiếp với nhóm vận hành dù metric không có hit.

## 7. Bước 3: công bố deprecation trước khi removal

Một cách an toàn hơn là giữ operation cũ trong giai đoạn chuyển tiếp, ghi rõ replacement và hướng di chuyển.

Ví dụ:

\`\`\`java
@ManagedOperation(
    description = "DEPRECATED: use requestEviction(region, requestId)")
public void clearAll() {
    // Ủy quyền sang service hoặc adapter mới nếu tương đương.
    cacheEvictionService.requestLegacyClearAll();
}
\`\`\`

Trong Java có thể dùng:

\`\`\`java
@Deprecated(since = "2.4", forRemoval = true)
\`\`\`

Nhưng \`@Deprecated\` không tự khiến một remote JMX client hiện cảnh báo hoặc không cho gọi. JMX clients có thể chỉ biết metadata được exporter công bố. Thông tin deprecation cần tồn tại ở description, tài liệu runbook, release notes và communication tới owners.

Nếu operation cũ có tác dụng quá rộng, đừng tiếp tục duy trì hành vi nguy hiểm mà không có kiểm soát chỉ để giữ tương thích. Có thể cần giới hạn quyền, kiểm tra điều kiện và thiết kế một đường di chuyển khẩn cấp có phê duyệt.

## 8. Bước 4: thiết kế replacement có hợp đồng rõ

Giả sử operation cũ:

\`\`\`java
void clearAll();
\`\`\`

Replacement:

\`\`\`java
String requestEviction(String region, String requestId);
String getOperationStatus(String requestId);
\`\`\`

Lợi ích:
- Có phạm vi \`region\` thay vì xóa tất cả.
- Có request ID để nhận biết trùng request.
- Có trạng thái tác vụ nếu thực thi bất đồng bộ.
- Có khả năng validate và audit.

Nhưng đây không phải thay thế tương đương tuyệt đối. \`clearAll()\` có thể đồng bộ, còn \`requestEviction()\` trả \`ACCEPTED\` trước khi hoàn tất. Runbook và client phải hiểu sự khác biệt. Không giữ cùng tên operation nhưng âm thầm thay semantics vì “trông vẫn chạy được”.

### 8.1 Nếu replacement chỉ là rename

Một cách ít rủi ro:

\`\`\`java
@ManagedOperation
public void refreshMetrics() {
    metricsService.refresh();
}

@Deprecated
@ManagedOperation(description = "DEPRECATED: use refreshMetrics")
public void reloadMetrics() {
    refreshMetrics();
}
\`\`\`

Điều này phù hợp khi hai operation có cùng semantics và khả năng lặp lại. Tuy nhiên khi dùng AOP proxy, self-invocation \`refreshMetrics()\` trong cùng bean có thể không đi qua advice; nếu cần transaction/security advice, nên gọi một service được inject qua proxy phù hợp.

## 9. Compatibility adapter thay vì giữ logic cũ

Một adapter có thể tách JMX contract khỏi implementation:

\`\`\`java
public final class CacheAdministration {

    private final CacheMaintenanceService service;

    public CacheAdministration(CacheMaintenanceService service) {
        this.service = service;
    }

    @ManagedOperation(description = "DEPRECATED: use requestEviction")
    public void clearAll() {
        service.evictAllWithGuardrails();
    }

    @ManagedOperation(description = "Request bounded eviction")
    public String requestEviction(String region, String requestId) {
        return service.requestEviction(region, requestId);
    }
}
\`\`\`

Trong dự án thực tế, class cần được export qua annotation metadata hoặc interface phù hợp; service phải triển khai validation, authorization và audit theo thiết kế. Compatibility adapter tránh copy hai bộ business logic. Khi hết giai đoạn hỗ trợ, chỉ xóa entry point cũ khỏi management contract thay vì xóa service chung.

Tuy nhiên, \`evictAllWithGuardrails()\` cần có hợp đồng rõ. Nếu không thể bảo đảm an toàn của operation cũ, phải cân nhắc rút quyền hoặc disable có thông báo; tương thích không phải lý do để tiếp tục một thao tác không thể kiểm soát.

## 10. Phân biệt deprecation, disable và removal

| Giai đoạn | Operation có trong MBeanInfo? | Invoke có thành công? | Mục đích |
|---|---|---|---|
| Active | Có | Theo hành vi cũ | Sử dụng bình thường |
| Deprecated | Có | Thường vẫn hỗ trợ | Cảnh báo và chuyển client |
| Restricted | Có | Chỉ caller có quyền/điều kiện | Giảm rủi ro khi chuyển tiếp |
| Disabled | Có thể có | Trả lỗi có chủ đích | Chặn sử dụng nhưng giữ dấu hiệu contract |
| Removed | Không | Client cũ không gọi được | Kết thúc hợp đồng cũ |

Một operation vẫn xuất hiện nhưng trả lỗi “DISABLED” không tương đương đã xóa. Nó giúp script nhận lỗi rõ hơn nhưng cũng là breaking behavior. Cần thống nhất chính sách với nhóm vận hành.

Không tự thêm tham số \`confirmed=true\` rồi xem là bảo mật. Caller có thể tự truyền \`true\`; quyền và xác nhận phải gắn với identity, scope và precondition đáng tin cậy.

## 11. Versioning management API

Có nhiều chiến lược:

### 11.1 Giữ ObjectName và thêm operation mới

\`\`\`text
com.example.ops:type=Cache,name=Catalog
  ├── clearAll()               [deprecated]
  └── requestEviction(region) [new]
\`\`\`

Phù hợp khi vẫn muốn một MBean duy nhất. Client mới có thể dùng method mới, client cũ tiếp tục hoạt động trong thời gian chuyển tiếp.

### 11.2 MBean mới theo version

\`\`\`text
com.example.ops:type=Cache,name=Catalog,api=v1
com.example.ops:type=Cache,name=Catalog,api=v2
\`\`\`

Phù hợp khi hai contract khác nhau đáng kể và cần chạy song song. Điều này tăng số registration và yêu cầu ownership/lifecycle rõ. Client cần chọn đúng ObjectName; không tự động chuyển khi MBean v1 bị xóa.

### 11.3 API chỉ quan sát trên JMX, control qua nền tảng khác

Nếu operation cũ có tác dụng phụ lớn, một lộ trình có thể:
- Giữ JMX attributes read-only cho health/status.
- Chuyển lệnh điều khiển sang control plane có authentication, approval và audit.
- Công bố migration runbook và thời điểm ngừng operation cũ.

Đây thường là lựa chọn tốt khi operation cần quản lý identity theo tenant, two-person approval hoặc workflow phức tạp hơn quyền JMX connector có thể cung cấp.

## 12. Trường hợp client hard-code ObjectName và signature

Một client Java:

\`\`\`java
ObjectName name = new ObjectName(
    "com.example.ops:type=Cache,name=Catalog");

connection.invoke(
    name,
    "clearAll",
    new Object[0],
    new String[0]);
\`\`\`

Có thể hỏng khi:
- ObjectName đổi.
- Operation bị xóa.
- Signature đổi thành có tham số.
- Quyền invoke bị thu hẹp.
- MBean chuyển sang server khác mà connector không phục vụ.
- MBean chỉ được đăng ký sau một thời điểm startup khác.
- Client dùng metadata cache cũ.

Để dễ migration, client nên có bước discovery/validation:

\`\`\`java
if (!connection.isRegistered(name)) {
    throw new IllegalStateException("Expected MBean not registered");
}

MBeanInfo info = connection.getMBeanInfo(name);
// Kiểm tra operation + signature, không chỉ tên.
\`\`\`

Không nên tự động fallback sang operation có semantics gần giống nếu nó có side effect. Ví dụ \`clearRegion("all")\` không nhất thiết tương đương \`clearAll()\` cũ. Chỉ gọi replacement khi contract được mô tả và owner chấp thuận.

## 13. Compatibility test trước khi deploy

Một integration test có thể chốt contract đang được hỗ trợ:

\`\`\`java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Arrays;
import javax.management.*;

class CacheJmxCompatibilityAssertions {

    static boolean hasOperation(
            MBeanInfo info, String operationName,
            String... parameterTypes) {

        return Arrays.stream(info.getOperations())
            .filter(op -> op.getName().equals(operationName))
            .anyMatch(op -> {
                MBeanParameterInfo[] signature = op.getSignature();
                if (signature.length != parameterTypes.length) {
                    return false;
                }
                for (int i = 0; i < signature.length; i++) {
                    if (!signature[i].getType()
                            .equals(parameterTypes[i])) {
                        return false;
                    }
                }
                return true;
            });
    }
}
\`\`\`

Test khi giai đoạn migration:

\`\`\`java
MBeanInfo info = server.getMBeanInfo(name);

assertTrue(hasOperation(info, "clearAll"));
assertTrue(hasOperation(
    info,
    "requestEviction",
    "java.lang.String",
    "java.lang.String"));
\`\`\`

Sau thời điểm removal đã được phê duyệt, test đổi thành:

\`\`\`java
assertFalse(hasOperation(info, "clearAll"));
assertTrue(hasOperation(
    info,
    "requestEviction",
    "java.lang.String",
    "java.lang.String"));
\`\`\`

Đây là **contract test**, không chỉ test implementation method. Nó xác minh exporter/assembler thực sự công bố đúng operation. Nếu có overload, so sánh đầy đủ signature thay vì kiểm tra tên.

### 13.1 Test client thực tế

Một integration test còn nên tạo JMX client qua \`MBeanServerConnection\` và gọi replacement trên fixture an toàn:

\`\`\`java
Object result = connection.invoke(
    name,
    "requestEviction",
    new Object[]{"test-region", "request-001"},
    new String[]{
        "java.lang.String",
        "java.lang.String"
    });
\`\`\`

Dùng test service không gây xóa dữ liệu production. Nếu operation bất đồng bộ, kiểm tra status hoàn tất thay vì coi response đầu tiên là thành công cuối cùng.

## 14. Negative test: old operation phải biến mất đúng thời điểm

Sau khi removal:

1. MBean vẫn được đăng ký dưới ObjectName dự kiến.
2. Operation cũ không còn trong \`MBeanInfo\`.
3. Replacement vẫn có mặt với signature đúng.
4. Attribute quan sát không bị mất.
5. Một script dùng contract mới hoạt động.
6. Một script cố gọi contract cũ thất bại theo cách dự kiến.
7. Context shutdown unregister đúng registration, không gây lỗi khi redeploy.

Không nên test operation nguy hiểm cũ trên production chỉ để chứng minh nó không còn. Kiểm tra \`MBeanInfo\` là cách an toàn hơn để xác minh vắng mặt. Trong môi trường test cô lập, có thể thêm negative invocation test nếu cần.

## 15. Kiểm soát deploy rolling và version skew

Một cluster có nhiều JVM có thể chạy song song các phiên bản khác nhau:

\`\`\`text
node-01: v2.4 — clearAll + requestEviction
node-02: v2.5 — clearAll + requestEviction
node-03: v2.6 — requestEviction only
\`\`\`

Nếu script điều khiển đồng thời nhiều node, nó cần biết contract của từng node. Đổi tất cả client sang \`requestEviction\` trước khi tất cả node có method mới có thể làm lỗi trên các node cũ. Xóa method cũ trước khi toàn bộ client chuyển đổi cũng gây lỗi.

Lộ trình tương thích:

\`\`\`text
Release A: thêm replacement, giữ legacy operation
      |
      v
Nâng cấp tất cả server nodes để hỗ trợ cả hai
      |
      v
Chuyển các client sang replacement
      |
      v
Xác minh không còn phụ thuộc legacy
      |
      v
Release B: deprecate/restrict legacy, theo dõi
      |
      v
Release C: remove legacy theo kế hoạch
\`\`\`

Trình tự phải xét rollout pattern của hệ thống. Nếu client mới chỉ hỗ trợ contract mới, nó không thể được triển khai khi còn node chưa hỗ trợ. Có thể cần dual-path client nhưng mọi fallback phải có semantics an toàn, nhất là với operation có side effect.

## 16. Tác dụng phụ và idempotency khi migration

Xóa một operation có side effect có thể khiến operator tìm workaround hoặc retry. Cần hướng dẫn rõ replacement và cách xác minh kết quả.

Giả sử \`clearAll()\` được gọi qua JMX và connection timeout. Không thể kết luận lệnh chưa chạy. Nếu client chuyển sang \`requestEviction\` ngay và gọi lại, hệ thống có thể bị clear hai lần hoặc tạo cache stampede.

Các biện pháp:
- Operation ID hoặc request ID.
- Status query để biết yêu cầu đã được chấp nhận/thực thi.
- Precondition về trạng thái và phạm vi.
- Bounded impact, rate limit và audit.
- Không retry mù sau \`IOException\` hoặc timeout.
- Runbook phục hồi khi trạng thái thực thi không xác định.

Idempotent về trạng thái cuối không đồng nghĩa không có side effect do repeated invocation. \`clearCache()\` có thể để lại cache rỗng ở cả hai lần nhưng vẫn gây hai đợt downstream load khác nhau.

## 17. Audit quá trình migration

Có thể theo dõi:
- Số lần legacy operation được gọi.
- Caller identity nếu connector/control plane cung cấp đáng tin cậy.
- Target instance/ObjectName.
- Operation signature.
- Tham số sau redaction.
- Kết quả accepted/rejected/completed.
- Nguồn gọi: script, UI, automation hoặc manual operation nếu nhận diện được.
- Lần gọi gần nhất theo từng environment.
- Thời gian còn lại trước removal.

Không log raw credential, secret hoặc dữ liệu cá nhân. Một annotation \`@ManagedOperation(description=...)\` không tự cung cấp invocation audit. Nếu cần identity theo từng lệnh và JMX connector không chuyển được caller identity tin cậy, nên dùng management gateway hoặc control plane có xác thực riêng.

## 18. Khi nào nên giữ operation legacy lâu hơn?

Một số operation chỉ được dùng trong tình huống hiếm:

- Khôi phục kết nối sau sự cố lớn.
- Làm sạch checkpoint khi dữ liệu hỏng.
- Đổi chế độ debug để điều tra incident.
- Quản lý hệ thống disaster recovery.
- Repair queue bị stuck.
- Chạy maintenance sau nhiều tháng.

Nếu không có usage telemetry, không nên mặc định operation “không ai gọi” chỉ vì không có hit trong một tuần. Có thể cần chu kỳ thông báo dài hơn hoặc diễn tập khôi phục trên staging trước khi xóa.

Tuy nhiên nếu operation cũ không an toàn, việc kéo dài thời gian hỗ trợ phải đi kèm hạn chế quyền, giám sát và kế hoạch sunset rõ ràng. Không giữ legacy mãi vì ngại phối hợp.

## 19. Một ví dụ deprecation adapter hoàn chỉnh

\`\`\`java
import org.springframework.jmx.export.annotation.ManagedOperation;
import org.springframework.jmx.export.annotation.ManagedOperationParameter;
import org.springframework.jmx.export.annotation.ManagedOperationParameters;
import org.springframework.jmx.export.annotation.ManagedResource;
import org.springframework.stereotype.Component;

@Component
@ManagedResource(
    objectName = "com.example.ops:type=Cache,name=Catalog",
    description = "Catalog cache management API")
public class CatalogCacheMBeanAdapter {

    private final CacheMaintenanceService service;

    public CatalogCacheMBeanAdapter(CacheMaintenanceService service) {
        this.service = service;
    }

    @Deprecated(since = "2.4", forRemoval = true)
    @ManagedOperation(
        description = "DEPRECATED: use requestEviction(region, requestId)")
    public void clearAll() {
        service.legacyClearAllWithGuardrails();
    }

    @ManagedOperation(
        description = "Request a bounded cache eviction")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "region",
            description = "Validated cache region"),
        @ManagedOperationParameter(
            name = "requestId",
            description = "Unique idempotency key")
    })
    public String requestEviction(String region, String requestId) {
        return service.requestEviction(region, requestId);
    }

    @ManagedOperation(
        description = "Read the current status of a request")
    @ManagedOperationParameters({
        @ManagedOperationParameter(
            name = "requestId",
            description = "Existing request identifier")
    })
    public String getOperationStatus(String requestId) {
        return service.getOperationStatus(requestId);
    }
}
\`\`\`

\`CacheMaintenanceService\` ở đây là service ứng dụng minh họa. Trong production phải triển khai validation, authorization, idempotency, audit và bounds thực tế. Việc đặt tên \`getOperationStatus\` với một tham số khiến nó được export như operation chứ không phải attribute getter không tham số trong mô hình metadata phù hợp.

Với Spring AOP, adapter gọi service được inject qua proxy để những advice cần thiết vẫn áp dụng. Không nên gọi trực tiếp target và vô tình bypass transaction/security.

## 20. Runbook xóa operation đang được gọi

### Trước khi công bố thay đổi

1. Xác định ObjectName, operation, full signature và behavior.
2. Chụp \`MBeanInfo\` để lưu contract hiện tại.
3. Kiểm kê scripts, dashboard, runbooks, automation và external clients.
4. Gán owner cho operation và các consumer.
5. Phân loại tác dụng phụ và khả năng rollback.
6. Thiết kế replacement cùng kế hoạch hỗ trợ rolling upgrade.
7. Thống nhất release/deprecation/removal dates.

### Trong giai đoạn deprecation

1. Thêm replacement và giữ legacy nếu an toàn.
2. Công bố description, release notes và runbook mới.
3. Thêm usage metric/audit theo khả năng tin cậy của hệ thống.
4. Cập nhật lần lượt clients và deployment automation.
5. Đo các lời gọi legacy còn lại, kể cả environment hiếm.
6. Kiểm thử compatibility trên nhiều phiên bản đang cùng chạy.

### Trước ngày removal

1. Xác nhận nhóm vận hành đã chuyển runbook.
2. Xác nhận không còn caller được biết đang phụ thuộc old operation.
3. Kiểm tra edge-case như disaster recovery.
4. Đảm bảo mọi node hỗ trợ new operation.
5. Có rollback plan và cửa sổ release phù hợp.
6. Chốt contract tests của phiên bản mới.

### Sau removal

1. Kiểm tra MBeanInfo không còn operation cũ.
2. Kiểm tra replacement hoạt động trên test fixture.
3. Theo dõi \`ReflectionException\`, failed invoke và error logs.
4. Cập nhật dashboard, CLI help, docs, troubleshooting notes.
5. Không khôi phục legacy operation một cách tự động nếu nguyên nhân xóa là rủi ro bảo mật nghiêm trọng.

## 21. Những nhầm lẫn thường gặp

**“Xóa method Java chỉ ảnh hưởng code compile.”** Sai: JMX client có thể gọi bằng string và chỉ lỗi tại runtime.

**“Không có references trong source nghĩa là không ai dùng.”** Sai: automation và runbook có thể ở repository/hệ thống khác.

**“Đổi tên operation giữ nguyên behavior nên không breaking.”** Sai: client gọi theo tên và signature.

**“@Deprecated sẽ tự cảnh báo JConsole.”** Không nên giả định. Cần công bố deprecation qua JMX metadata, tài liệu và communication.

**“Thêm replacement rồi xóa ngay operation cũ.”** Nguy hiểm khi clients hoặc nodes nâng cấp theo rolling rollout.

**“Client không thấy operation nghĩa là bean đã bị xóa.”** Chưa chắc; MBean vẫn có nhưng operation không còn trong MBeanInfo.

**“Giữ ObjectName thì mọi client tương thích.”** Không đủ: operation signature và behavior vẫn có thể đổi.

**“Timeout sau invoke nghĩa là operation chưa thực thi.”** Không chắc; không retry mù thao tác có side effect.

**“Tách version bằng domain tự tạo quyền truy cập riêng.”** Không. ObjectName namespace không thay thế connector authorization.

## 22. Bài tập vận dụng

**Bài 1 — Tác động của removal.** Một script gọi \`clearAll()\` bằng \`MBeanServerConnection.invoke()\`. Sau deploy, MBean còn nhưng operation biến mất. Hãy mô tả cách xác minh qua \`MBeanInfo\` và loại lỗi runtime phù hợp.

**Bài 2 — Signature migration.** Operation \`reset(int)\` đổi thành \`reset(long)\`. Vì sao đây là breaking change dù tên vẫn là reset? Viết test so sánh signature.

**Bài 3 — Rolling cluster.** Ba JVM chạy phiên bản khác nhau. Hãy xếp thứ tự deploy replacement, nâng cấp server nodes, nâng cấp clients và xóa legacy operation.

**Bài 4 — Legacy runbook.** Một operation không có usage log 6 tháng, nhưng được ghi trong runbook disaster recovery. Có thể xóa ngay không? Đề xuất quy trình phê duyệt và diễn tập.

**Bài 5 — Compatibility adapter.** Viết một method legacy gọi service mới và trả result tương thích, nhưng bảo đảm không bypass AOP advice.

**Bài 6 — Side effect.** Client gặp timeout khi gọi operation cũ, rồi thử operation mới để “chắc ăn”. Hãy phân tích nguy cơ double execution và đề xuất request ID/status check.

## Tổng kết

Xóa một operation đang được gọi từ công cụ quản trị là thay đổi **hợp đồng JMX runtime**, không chỉ là sửa source Java. Client phụ thuộc vào ObjectName, operation name, signature, return type, quyền và semantics. Cách an toàn là inventory dependency, quan sát usage, công bố deprecation, thêm replacement có hợp đồng rõ, chuyển clients theo lộ trình, hỗ trợ rolling version skew và chỉ remove sau khi đã kiểm chứng. \`MBeanInfo\` và integration tests giúp khóa contract, còn audit/runbook/rollback bảo vệ vận hành. Đối với operation có side effect, quản lý idempotency và tránh retry mù đặc biệt quan trọng. Khi mỗi bước được gắn với owner và tiêu chí xác nhận rõ, hệ thống có thể tiến hóa management API mà không phá vỡ các công cụ quản trị đang phục vụ production.
