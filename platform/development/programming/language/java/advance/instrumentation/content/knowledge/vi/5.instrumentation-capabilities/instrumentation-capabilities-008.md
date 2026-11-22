# Chọn chức năng thay thế hoặc bỏ qua có báo cáo khi khả năng Instrumentation không được hỗ trợ

Một Java agent có thể chạy tốt trên JVM này nhưng không thực hiện được cùng thao tác trên JVM khác. Ví dụ, việc đăng ký `ClassFileTransformer` để xử lý **lớp nạp trong tương lai** không đồng nghĩa JVM cho phép `retransformClasses` đối với **lớp đã nạp**. Tương tự, có quyền retransform không đồng nghĩa mọi class đều sửa được, và có quyền redefine không đồng nghĩa có bytecode thay thế hợp lệ.

Thiết kế agent tốt phải trả lời rõ bốn câu hỏi trước khi đụng đến một chức năng tùy chọn:

1. **Người dùng cần kết quả gì?** Chẳng hạn “theo dõi phương thức đã nạp” khác “theo dõi lớp được nạp từ bây giờ”.
2. **JVM/agent/lớp mục tiêu hỗ trợ gì?** Kiểm tra năng lực toàn JVM và điều kiện riêng của mục tiêu.
3. **Có chức năng thay thế nào thực sự đáp ứng yêu cầu không?** Chỉ chọn fallback khi đã xác định phạm vi và khác biệt về ngữ nghĩa.
4. **Nếu không làm được, báo gì?** Trả trạng thái, lý do và mức ảnh hưởng; tránh tiếp tục như thể instrumentation đã thành công.

Bài này trình bày cách **kiểm tra capability → chọn phương án → thực hiện → xác nhận kết quả → báo cáo**, áp dụng cho Java 17+ và API `java.lang.instrument.Instrumentation`.

## 1. Phân biệt “có API” với “được JVM hiện tại hỗ trợ”

Tồn tại phương thức trong Java API chỉ có nghĩa chương trình **biên dịch được**. Một số tính năng Instrumentation là **optional capabilities**: JVM có thể không hỗ trợ, hoặc agent chưa yêu cầu khả năng đó trong manifest.

Các phép kiểm tra quan trọng:

| Điều cần làm | Phép kiểm tra | Điều kiện liên quan | Nếu không đáp ứng |
|---|---|---|---|
| Biến đổi lớp **đã nạp** bằng cách chạy lại chuỗi transformer | `isRetransformClassesSupported()` **và** `isModifiableClass(target)` | `Can-Retransform-Classes: true` và JVM hỗ trợ | Cân nhắc redefine có đủ dữ liệu, load-time cho lớp mới, hoặc bỏ qua có lý do |
| Thay bytecode lớp **đã nạp** bằng bản class bytes đã chuẩn bị | `isRedefineClassesSupported()` **và** `isModifiableClass(target)` | `Can-Redefine-Classes: true`, bytes hợp lệ và sửa đổi được phép | Chỉ fallback khi có một phương án đáp ứng cùng yêu cầu; nếu không, bỏ qua |
| Đặt tiền tố cho native method wrapper | `isNativeMethodPrefixSupported()` | `Can-Set-Native-Method-Prefix: true` và JVM hỗ trợ | Không gọi `setNativeMethodPrefix`; xem có cần loại bỏ tính năng/đổi thiết kế |
| Điều chỉnh đọc module, exports hoặc opens | `isModifiableModule(module)` | `redefineModule` phải phù hợp module và tham số | Giữ module nguyên; cân nhắc cấu hình lúc khởi động ở lần chạy sau |
| Quan sát lần định nghĩa lớp **trong tương lai** | Đăng ký `addTransformer(transformer)` | Có `Instrumentation` và transformer hợp lệ | Đây là phương án cơ bản, **không** giải quyết lớp đã nạp |
| Chỉ sửa một lớp cụ thể | `isModifiableClass(type)` | Lớp được JVM coi là modifiable | Không thử `retransformClasses(type)`/`redefineClasses(type)` với lớp đó |

### 1.1. Kiểm tra capability toàn JVM và capability của mục tiêu là hai việc độc lập

`isRetransformClassesSupported() == true` chưa đủ để kết luận `SomeClass.class` có thể retransform. Phải kiểm tra tiếp:

```java
boolean canRetransform = inst.isRetransformClassesSupported();
boolean canModifyTarget = inst.isModifiableClass(SomeClass.class);

if (canRetransform && canModifyTarget) {
    // Có thể thử retransform; kết quả cuối vẫn phải được kiểm tra.
}
```

Đây là **đoạn mã minh họa**: `inst` là `Instrumentation` agent đã nhận qua `premain` hoặc `agentmain`, `SomeClass` là lớp mục tiêu có thật.

Ngược lại, `isModifiableClass(SomeClass.class) == true` cũng **không chứng minh** retransform/redefine được bật. Theo hợp đồng API, kết quả `isModifiableClass` độc lập với hai cờ năng lực toàn JVM. Lớp nguyên thủy như `int.class` và lớp mảng như `String[].class` không modifiable.

Đối với module, `isModifiableModule(module)` kiểm tra được phép thay đổi quan hệ module bằng `redefineModule`, **không phải** kiểm tra có thể retransform các class trong module. Với unnamed module, `isModifiableModule` có thể trả true nhưng `redefineModule` trên unnamed module là no-op. Cần phân biệt trước khi báo thành công.

### 1.2. Manifest có thể khiến capability bị tắt ngay từ đầu

Ví dụ manifest agent có yêu cầu các khả năng tùy chọn:

```text
Manifest-Version: 1.0
Premain-Class: CapabilityAgent
Agent-Class: CapabilityAgent
Can-Retransform-Classes: true
Can-Redefine-Classes: true
Can-Set-Native-Method-Prefix: true

```

Đây chỉ là **mẫu minh họa manifest**; muốn chạy cả hai entry point phải cài cả `premain` và `agentmain`. Các dòng `Can-*` chỉ **yêu cầu** capability. JVM vẫn có thể trả false nếu không hỗ trợ. Khi thuộc tính vắng mặt hoặc không phải `true`, khả năng tương ứng không được yêu cầu; không thể chỉ nhìn phiên bản Java rồi kết luận tất cả bật.

Vì vậy, không hard-code kiểu:

```java
inst.addTransformer(transformer, true); // có thể ném UnsupportedOperationException
inst.retransformClasses(target);        // có thể ném UnsupportedOperationException
```

mà không xét capability. Tuy nhiên **precheck không thay thế xử lý lỗi**: tác vụ vẫn có thể thất bại do class unmodifiable, thay đổi bytecode không hợp lệ, điều kiện triển khai hay lỗi vào thời điểm thực thi.

## 2. Trước khi chọn fallback, định nghĩa “chức năng” ở mức hành vi

Một sai lầm phổ biến là đặt mục tiêu bằng tên API: “ưu tiên `retransformClasses`, nếu không có thì dùng `redefineClasses`”. Hai API **khác hợp đồng đầu vào và ngữ nghĩa**:

- `retransformClasses(Class<?>...)` yêu cầu JVM xây lại định nghĩa lớp từ bytecode nền và chuỗi transformer. Transformer đăng ký với `addTransformer(transformer, true)` mới được gọi lại trong lần retransform; transformer không hỗ trợ retransform được áp lại kết quả biến đổi trước đó theo quy tắc JVM.
- `redefineClasses(ClassDefinition...)` nhận **bytecode thay thế do người gọi cung cấp**. Nó không tự gọi một công cụ để tạo class bytes tương đương mục tiêu của retransform, và không tự sửa những thay đổi cấu trúc mà JVM không cho phép.
- `addTransformer(transformer)` (tương đương `addTransformer(transformer, false)`) cho phép xử lý các **class definition mới**; không làm một class đã nạp chạy lại callback ngay lập tức.

Định nghĩa nhu cầu nên là một trong các mức sau:

| Mục tiêu tính năng | Phương án chính | Fallback có thể chấp nhận | Khi nào bắt buộc SKIP |
|---|---|---|---|
| Thu thập thông tin tại thời điểm **lớp mới nạp** | Load-time transformer | Ghi log/event trực tiếp từ ứng dụng hoặc các điểm hook hiện có, nếu đủ dữ liệu | Không có cách hợp lệ để quan sát sự kiện cần thiết |
| Áp probe lên **lớp đã nạp** | Retransformation | Redefinition nếu có bytecode thay thế đã xác minh và mục tiêu cho phép; hoặc chuyển sang quan sát **các lần nạp trong tương lai** với thông báo giảm phạm vi | Yêu cầu phải instrument ngay lớp hiện tại mà cả hai cơ chế không khả dụng |
| Đổi một method body đã nạp bằng bản build mới | Redefinition với bytecode phù hợp | Retransformation chỉ khi transformer có thể tạo đúng thay đổi tương đương | Không có replacement bytes hợp lệ, class không sửa được hoặc thay đổi schema bị cấm |
| Bao một native method qua native prefix | `setNativeMethodPrefix` | Wrapper ở tầng ứng dụng/thiết kế lại khi triển khai sau, nếu được chấp nhận | Không có phương án tương đương runtime |
| Mở module cho probe truy cập một gói | `redefineModule` khi module modifiable | Khởi động lại với thiết lập module phù hợp, ví dụ `--add-opens` khi có quyền và phạm vi được xét duyệt | Không được phép thay đổi quan hệ module lúc chạy |
| Đổi superclass/thêm trường vào class đã nạp | Không nên coi HotSwap chuẩn là giải pháp | Biến đổi trước khi tải lớp, build/redeploy, thiết kế class loader phù hợp | Không thể bảo đảm hợp đồng của instance đang tồn tại |

**Điểm mấu chốt:** “Có một API khác” chưa phải fallback. Phải xét nó có giữ được **phạm vi quan sát, thời điểm có hiệu lực, dữ liệu, an toàn và kỳ vọng người dùng** hay không.

### Ví dụ: fallback từ retransform sang load-time

Agent được attach vào một ứng dụng đã chạy 3 giờ. Cần thêm probe vào `OrderService` đang phục vụ request.

- Nếu JVM không hỗ trợ retransform, việc đăng ký `addTransformer(t)` **không** làm `OrderService` đã nạp có probe.
- Transformer đó vẫn có thể phục vụ những class **được định nghĩa trong tương lai**, nhưng đây là **giảm phạm vi**, không hoàn thành yêu cầu cho `OrderService` hiện tại.
- Báo cáo đúng phải là “`OrderService`: SKIPPED, reason=RETRANSFORM_UNSUPPORTED; future-load observation: ACTIVE (nếu đã đăng ký thành công)”.
- Nếu yêu cầu phục vụ an toàn nghiệp vụ đòi probe có mặt ngay, không được coi tương lai là thay thế chấp nhận được; phải báo lỗi hoặc yêu cầu restart/redeploy theo chính sách.

### Ví dụ: redefine là fallback có điều kiện

Giả sử capability trả `retransform=false` và `redefine=true`, class mục tiêu modifiable. Điều đó **chưa đủ** để gọi:

```java
inst.redefineClasses(
    new ClassDefinition(target, replacementBytes)
);
```

Đoạn trên **chỉ là mã minh họa**, không phải chương trình độc lập. Cần chứng minh `replacementBytes` thực sự chứa bytecode đúng class/binary name/loader, class-file version được hỗ trợ, cấu trúc không vượt giới hạn redefine, dependency hợp lệ và các probe khác không bị phá hỏng. Không đưa một byte array tùy ý từ file nguồn trên đĩa vào runtime đang chạy. Nếu không có replacement bytes đáng tin cậy, quyết định đúng là **SKIPPED** dù `redefine=true`.

## 3. Xây dựng ma trận quyết định rõ ràng

Thiết kế thực tế có thể đi theo thứ tự:

```text
Nhận yêu cầu feature và phạm vi mục tiêu
                  |
                  v
Kiểm tra Instrumentation đã sẵn sàng chưa?
        | không                  | có
        v                        v
SKIPPED/FAILED            Chụp capability + target facts
AGENT_UNAVAILABLE                |
                                 v
                      Phân biệt feature bắt buộc/tùy chọn
                                 |
                                 v
                    Phương án chính có được hỗ trợ?
                   /                         \
                 Có                          Không
                  |                            |
        Kiểm tra class/module       Fallback được định nghĩa,
        và điều kiện bytecode       đủ dữ liệu và đúng ngữ nghĩa?
                  |                    /             \
                  v                  Có              Không
              Thử thực hiện           |                |
                  |                Chọn fallback       |
                  v                   |             SKIPPED
          Xác minh hậu điều kiện <----/             + reason
                  |
                  v
      Báo cáo APPLIED/DEGRADED/FAILED
      kèm phạm vi thật và bằng chứng
```

### Đề xuất thứ tự ưu tiên cho lớp đã nạp

1. **Xác định loại thay đổi**: chỉ quan sát callback, chèn method-body probe, thay method body bằng bytecode chuẩn bị sẵn, hay cần sửa cấu trúc lớp.
2. **Kiểm tra `isModifiableClass(target)`** và đúng defining class loader. Nếu false, không thử retransform/redefine với lớp ấy.
3. **Ưu tiên API thực sự khớp hợp đồng**: retransform nếu cần chạy lại transformer; redefine nếu đã có một định nghĩa thay thế hợp lệ.
4. **Chỉ dùng API còn lại** khi đã chứng minh có thể tạo **kết quả tương đương**, không dựa mỗi vào capability boolean.
5. **Nếu cả hai không phù hợp**, xét load-time-only cho class tương lai hoặc chiến lược restart/redeploy, và phản ánh chính xác những class đã nạp còn thiếu probe.
6. **Mọi nhánh đều có báo cáo**; không có nhánh `return;` âm thầm đối với feature được người dùng kỳ vọng.

Bảng ví dụ cho yêu cầu *áp probe ngay lên một class đã nạp*:

| Retransform | Redefine | Class modifiable | Có replacement bytes hợp lệ, đáp ứng cùng mục tiêu? | Quyết định |
|---|---|---|---|---|
| true | bất kỳ | true | Không cần | Dùng retransform, rồi xác minh |
| false | true | true | Có | Có thể dùng redefine theo chính sách |
| false | true | true | Không | **SKIPPED** trên class cũ; cân nhắc load-time cho class mới |
| false | false | true | Bất kỳ | **SKIPPED**: thiếu cả hai capability |
| true/false | true/false | false | Bất kỳ | **SKIPPED**: class unmodifiable |
| true | bất kỳ | true | Không cần, nhưng bytecode được biến đổi là bất hợp lệ | **FAILED** khi thực thi; không giả vờ đã áp dụng |

Cần đọc bảng theo yêu cầu thực tế: nếu cần **retransform callback** chứ không chỉ “có bytecode tương đương”, redefine không nhất thiết là fallback. Nếu mục tiêu là thay đổi cấu trúc lớp, cả hai nhánh đều có thể không hợp lệ theo JVM implementation.

## 4. Trạng thái báo cáo: tách quyết định khỏi kết quả thực thi

Một báo cáo năng lực dễ sử dụng nên có trạng thái nhất quán. Có thể thiết kế bốn trạng thái chính:

- **APPLIED**: đường đi được chọn thực thi thành công và hậu điều kiện của **feature đã định nghĩa** được chứng minh.
- **DEGRADED**: có chức năng thay thế đang hoạt động, nhưng thiếu một phần phạm vi hoặc độ chính xác; phải công bố phần bị mất.
- **SKIPPED**: không thực hiện feature trên mục tiêu này do không có điều kiện hoặc không có fallback được chấp thuận; đây có thể là kết quả dự kiến cho tính năng optional.
- **FAILED**: đã thử thao tác hoặc bước kiểm chứng nhưng gặp lỗi, hoặc feature bắt buộc không đạt điều kiện. Cần mô tả lỗi và quyết định vận hành sau đó.

Một lớp đã nạp có thể mang trạng thái **SKIPPED**, trong khi cùng một agent đã kích hoạt load-time transformer thành công cho các class khác. Không gộp hai kết quả đó thành một dòng “instrumentation enabled”.

### Một bản ghi quyết định có cấu trúc

```json
{
  "feature": "loaded-class-method-probe",
  "targetClass": "com.example.OrderService",
  "classLoader": "app-loader",
  "requestedMode": "RETRANSFORM",
  "capabilities": {
    "retransform": false,
    "redefine": true,
    "classModifiable": true
  },
  "chosenMode": "SKIP_EXISTING_CLASS",
  "fallback": "LOAD_TIME_ONLY_FOR_FUTURE_CLASSES",
  "status": "DEGRADED",
  "existingClassStatus": "SKIPPED",
  "reason": "NO_APPROVED_REPLACEMENT_BYTES",
  "scope": "future_class_definitions_only",
  "effectVerified": false
}
```

Đây là **mẫu log minh họa**, không phải kết quả từ JVM cụ thể. Một hệ thống thực có thể thêm agent version, JDK/VM vendor, feature ID, request ID, timestamp, class-loader identity đáng tin cậy và đếm số lớp đạt/chưa đạt. Tránh log dữ liệu nhạy cảm từ method arguments hoặc thổi phồng cardinality metrics bằng tên từng instance/class loader.

Mã lý do nên ổn định và dễ tìm kiếm:

| Reason | Ý nghĩa |
|---|---|
| `AGENT_NOT_INITIALIZED` | Chưa có đối tượng `Instrumentation` để thao tác |
| `RETRANSFORM_UNSUPPORTED` | JVM/agent config không hỗ trợ retransform |
| `REDEFINE_UNSUPPORTED` | JVM/agent config không hỗ trợ redefine |
| `NATIVE_PREFIX_UNSUPPORTED` | Không được đặt native method prefix |
| `CLASS_UNMODIFIABLE` | Lớp mục tiêu không thể redefine/retransform |
| `MODULE_UNMODIFIABLE` | Module không cho thay đổi theo `redefineModule` |
| `REPLACEMENT_BYTES_MISSING` | Không có định nghĩa thay thế đủ điều kiện cho redefine |
| `FALLBACK_SCOPE_REDUCED` | Fallback chỉ tác dụng cho lớp mới hoặc phạm vi hẹp hơn |
| `BYTECODE_REJECTED` | JVM không chấp nhận class bytes sau biến đổi |
| `POSTCONDITION_NOT_VERIFIED` | Thao tác đã chạy nhưng chưa đủ bằng chứng feature đạt mục tiêu |
| `POLICY_BLOCKED` | Chính sách vận hành không cho phép thay đổi |
| `TRANSFORMER_NOT_REGISTERED` | Không đăng ký được transformer đúng capability |

### Đừng đánh đồng “lệnh API trả về” với “probe hoạt động”

`inst.retransformClasses(target)` trả về không ném exception cho thấy yêu cầu retransform đã được xử lý thành công theo API. Nhưng nếu transformer trả `null` hoặc không biến đổi đúng class, bạn **chưa chứng minh** probe mong muốn đã xuất hiện. Có thể báo `operation=RETRANSFORM status=COMPLETED effect=NO_CHANGE/UNVERIFIED`, sau đó chỉ báo `feature=APPLIED` khi đã kiểm chứng hành vi/bytecode.

Ngược lại, một transformer ném exception có thể bị JVM xử lý như không biến đổi; các transformer sau vẫn chạy. Vì vậy đừng thiết kế cơ chế báo lỗi chỉ bằng cách ném exception trong `ClassFileTransformer.transform` rồi mong toàn bộ class load tự thất bại. Hãy ghi nhận lỗi biến đổi bằng một kênh có kiểm soát và xác minh các mục tiêu ở tầng điều phối.

## 5. Ví dụ Java 17+ chạy được: tự chọn retransform hoặc SKIP và vẫn quan sát lớp mới

Ví dụ sau chỉ **quan sát callback** của JVM. `transform` luôn trả `null`, nghĩa là **không thay đổi bytecode**; nhờ vậy thí nghiệm tập trung vào việc chọn capability và báo cáo thay vì phụ thuộc thư viện bytecode bên thứ ba.

Ta tạo 4 file trong cùng thư mục: `CapabilityAgent.java`, `ObserveTransformer.java`, `Demo.java` và `agent.mf`.

### 5.1. `ObserveTransformer.java`

```java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

public final class ObserveTransformer implements ClassFileTransformer {
    @Override
    public byte[] transform(
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        if ("ExistingClass".equals(className)
                || "FutureClass".equals(className)) {
            String phase = classBeingRedefined == null
                    ? "LOAD"
                    : "RETRANSFORM_OR_REDEFINE";
            System.out.println(
                    "EVENT class=" + className + " phase=" + phase);
        }
        return null; // Quan sát thôi, không thay class bytes.
    }
}
```

`className` dùng dạng JVM internal name; với hai class ở **default package** trong ví dụ, nó là `ExistingClass` và `FutureClass`. Nếu chuyển sang package `demo`, filter phải dùng `demo/ExistingClass`, không phải `demo.ExistingClass`. Giá trị `classBeingRedefined != null` phân biệt callback khi JVM đang redefine hoặc retransform; chỉ dựa vào trường đó không biết **API nào đã gây ra callback**.

### 5.2. `CapabilityAgent.java`

```java
import java.lang.instrument.Instrumentation;
import java.lang.instrument.UnmodifiableClassException;

public final class CapabilityAgent {
    private static volatile Instrumentation instrumentation;
    private static volatile boolean canRetransform;

    public static void premain(
            String agentArgs, Instrumentation inst) {

        instrumentation = inst;
        canRetransform = inst.isRetransformClassesSupported();

        System.out.println("CAP retransform=" + canRetransform);

        // Luôn quan sát được lớp nạp sau khi transformer được đăng ký.
        // Nếu không hỗ trợ retransform, đăng ký với false là hợp lệ.
        inst.addTransformer(new ObserveTransformer(), canRetransform);

        System.out.println(
                "REPORT status=ACTIVE feature=LOAD_TIME_FUTURE");
    }

    public static void inspectAlreadyLoaded(Class<?> target) {
        if (instrumentation == null) {
            System.out.println(
                    "REPORT status=SKIPPED feature=RETRANSFORM"
                    + " reason=AGENT_NOT_INITIALIZED");
            return;
        }

        if (!instrumentation.isModifiableClass(target)) {
            System.out.println(
                    "REPORT status=SKIPPED feature=RETRANSFORM"
                    + " reason=CLASS_UNMODIFIABLE");
            return;
        }

        if (!canRetransform) {
            System.out.println(
                    "REPORT status=SKIPPED feature=RETRANSFORM"
                    + " reason=RETRANSFORM_UNSUPPORTED");
            return;
        }

        try {
            instrumentation.retransformClasses(target);
            System.out.println(
                    "REPORT status=COMPLETED feature=RETRANSFORM"
                    + " effect=NO_BYTECODE_CHANGE");
        } catch (UnmodifiableClassException
                 | UnsupportedOperationException e) {
            System.out.println(
                    "REPORT status=FAILED feature=RETRANSFORM"
                    + " cause=" + e.getClass().getSimpleName());
        }
    }
}
```

Vì `canRetransform` lấy từ `isRetransformClassesSupported()`, lời gọi `addTransformer(transformer, canRetransform)` chỉ đặt `true` khi JVM/manifest hỗ trợ. Nếu `false`, transformer vẫn xử lý class **nạp về sau** nhưng sẽ không nhận callback cho retransform. Phần `inspectAlreadyLoaded` phân biệt rõ lớp không sửa được với tính năng retransform chưa hỗ trợ.

Để ví dụ ngắn, `catch` chỉ minh họa hai loại lỗi dự kiến ở tầng capability. Với agent thực, lỗi class file, verifier, module, linkage hay bug của transformer phải được ghi nhận và xử lý theo chính sách riêng; không nên giấu chúng bằng một `catch(Throwable)` rồi báo SKIPPED.

### 5.3. `Demo.java`

```java
public final class Demo {
    public static void main(String[] args) throws Exception {
        System.out.println("APP_START");

        Class<?> existing = Class.forName("ExistingClass");
        CapabilityAgent.inspectAlreadyLoaded(existing);

        Class.forName("FutureClass");
        System.out.println("APP_DONE");
    }
}

final class ExistingClass {
}

final class FutureClass {
}
```

Hai class không có `public` nằm cùng file `Demo.java` là hợp lệ. `Class.forName("ExistingClass")` làm lớp `ExistingClass` được nạp sau khi agent đã đăng ký transformer. Sau đó `inspectAlreadyLoaded` thử retransform **chính đối tượng `Class<?>` đã nạp**. Cuối cùng, `FutureClass` được nạp sau quyết định và phải vẫn đi qua transformer.

### 5.4. `agent.mf`

```text
Manifest-Version: 1.0
Premain-Class: CapabilityAgent
Can-Retransform-Classes: true

```

Đây là startup agent nên chỉ cần `Premain-Class`. Thuộc tính `Can-Retransform-Classes: true` cho phép agent yêu cầu capability; **không ép** mọi JVM hỗ trợ. Ví dụ không dùng `Can-Redefine-Classes` vì không gọi redefine, và không cần `Can-Set-Native-Method-Prefix`.

### 5.5. Biên dịch, đóng gói và chạy

Trên JDK 17+ có `javac`, `jar`, `java`:

```shell
javac CapabilityAgent.java ObserveTransformer.java Demo.java
jar cfm capability-agent.jar agent.mf CapabilityAgent.class ObserveTransformer.class
java -javaagent:capability-agent.jar -cp . Demo
```

Tất cả file được biên dịch trong cùng thư mục. File `ExistingClass.class` và `FutureClass.class` do `javac Demo.java` sinh ra vẫn nằm ở classpath `.`. Agent JAR chứa đủ hai class mà agent sử dụng. Lệnh `jar cfm` lấy manifest ngoài để đưa vào `META-INF/MANIFEST.MF`.

**Kết quả điển hình với HotSpot JDK 17/21 hỗ trợ retransformation:**

```text
CAP retransform=true
REPORT status=ACTIVE feature=LOAD_TIME_FUTURE
APP_START
EVENT class=ExistingClass phase=LOAD
EVENT class=ExistingClass phase=RETRANSFORM_OR_REDEFINE
REPORT status=COMPLETED feature=RETRANSFORM effect=NO_BYTECODE_CHANGE
EVENT class=FutureClass phase=LOAD
APP_DONE
```

**Nếu JVM/agent không hỗ trợ retransformation** nhưng cho phép transformer cho lớp mới, nhánh tương ứng in:

```text
CAP retransform=false
REPORT status=ACTIVE feature=LOAD_TIME_FUTURE
APP_START
EVENT class=ExistingClass phase=LOAD
REPORT status=SKIPPED feature=RETRANSFORM reason=RETRANSFORM_UNSUPPORTED
EVENT class=FutureClass phase=LOAD
APP_DONE
```

Đây là **hai kết quả phụ thuộc capability**, không phải hai output phải xuất hiện trong một lần chạy. Một JVM khác cũng có thể đánh dấu lớp là unmodifiable, lúc đó xuất hiện nhánh `CLASS_UNMODIFIABLE`.

### 5.6. Đọc output cho đúng

- `EVENT class=ExistingClass phase=LOAD`: callback xuất hiện ở lần đầu JVM định nghĩa class.
- `EVENT ... phase=RETRANSFORM_OR_REDEFINE`: trong thí nghiệm này đến từ lệnh `retransformClasses`, vì code không gọi `redefineClasses`. Chuỗi “OR_REDEFINE” chỉ phản ánh thông tin có sẵn trong callback.
- `status=COMPLETED ... effect=NO_BYTECODE_CHANGE`: thao tác retransform hoàn tất, **không** chứng minh đã cài probe; transformer trả `null`.
- `status=SKIPPED feature=RETRANSFORM` khi capability không hỗ trợ: request retransform không thực hiện; không giấu lỗi hoặc gọi bừa API.
- `status=ACTIVE feature=LOAD_TIME_FUTURE` và `EVENT class=FutureClass phase=LOAD`: vẫn có đường quan sát lớp mới, ngay cả khi không retransform được class cũ.

Nếu muốn thí nghiệm chế độ thiếu capability trên JVM thông thường, có thể biên dịch lại manifest với `Can-Retransform-Classes: false` rồi đóng gói lại JAR; đây là **đổi cấu hình capability của agent**, không phải giả mạo kết quả. Khi đó `isRetransformClassesSupported()` sẽ trả false theo hợp đồng của Java agent. Đừng thay manifest của JAR đang được JVM chạy rồi mong agent đang nạp tự đổi capability; cần khởi động JVM mới cho lượt thử.

## 6. Từ ví dụ quan sát đến agent thực: kiểm tra hậu điều kiện

Trong sản phẩm thực, transformer có thể tạo bytecode chứa probe đo thời gian hoặc ghi trace. Khi đó, thứ tự kiểm tra nên là:

1. **Trước thao tác:** ghi feature ID, class binary name, defining class loader, module, capability, chính sách fallback và trạng thái hiện tại.
2. **Trong thao tác:** đảm bảo transformer nhắm đúng class; bắt và lưu lỗi riêng của logic biến đổi. Không sửa trực tiếp `classfileBuffer`; trả `null` nếu không thay đổi, hoặc trả một mảng byte mới hợp lệ.
3. **Sau thao tác:** xác minh callback/bytecode kết quả/hành vi probe tùy mục tiêu (ví dụ probe xuất hiện trên request mới với một event được kiểm chứng). Một callback được gọi chưa đủ chứng minh đã có instrumentation.
4. **Báo cáo:** class nào `APPLIED`, class nào `SKIPPED` và vì sao, có `DEGRADED` do chỉ hỗ trợ load-time không, có `FAILED` do bytecode bị từ chối hay không.

Một bất biến có ích là:

```text
reported APPLIED
    => capability và điều kiện mục tiêu đã thỏa
    => API đã trả về thành công
    => điều kiện hậu kiểm của feature được chứng minh

reported SKIPPED
    => không tuyên bố feature đã có hiệu lực trên mục tiêu đó
    => có reason cụ thể
    => không lặng lẽ gọi phương án không được phép

reported DEGRADED
    => fallback có hiệu lực trong phạm vi đã nêu
    => phần phạm vi bị mất được báo riêng
```

Nếu việc xác minh hậu điều kiện tốn kém, hệ thống có thể chọn trạng thái trung gian như `OPERATION_COMPLETED_EFFECT_UNVERIFIED`. Không “nâng cấp” trạng thái đó thành `APPLIED` chỉ để log đẹp.

## 7. Bỏ qua có báo cáo không đồng nghĩa bỏ qua trách nhiệm

Cần phân biệt **tính năng tùy chọn** với **tính năng bắt buộc**:

- **Tùy chọn:** agent phục vụ số liệu bổ sung. Nếu JVM thiếu retransform, ứng dụng có thể tiếp tục chạy; agent báo `SKIPPED/DEGRADED`, hiển thị tỷ lệ coverage thực tế và cung cấp đường thu thập khác nếu đã xác minh.
- **Bắt buộc:** một chức năng chính yêu cầu probe hoặc kiểm soát ở tất cả lớp mục tiêu. Khi không có capability, không được coi fallback chỉ theo dõi lớp mới là đủ. Hãy dừng kích hoạt tính năng hoặc từ chối trạng thái “sẵn sàng” theo chính sách có sẵn và nêu lý do, thay vì giả vờ bảo đảm đã được thực thi.
- **Có tác động lớn:** `redefineClasses` hoặc mở module có thể thay đổi hành vi/quan hệ truy cập. Fallback không được tự động mở rộng quyền hoặc đổi class bytes chỉ để tránh báo SKIPPED.

Một báo cáo vận hành điển hình:

```text
feature=latency-probe
requested=loaded-class-and-future-class
class=com.example.OrderService
canRetransform=false
canRedefine=true
isModifiableClass=true
replacementBytesVerified=false
existingClass=SKIPPED reason=REPLACEMENT_BYTES_MISSING
futureClasses=ACTIVE mode=LOAD_TIME_ONLY
overall=DEGRADED
action=RESTART_WITH_STARTUP_AGENT_IF_FULL_COVERAGE_REQUIRED
```

Đây là bản ghi minh họa, không phải kết quả thực thi API. Nó cho biết rõ **tính năng nào còn dùng được, tính năng nào thiếu và phải làm gì nếu cần đủ coverage**.

### Có thể gộp kết quả cho nhiều class như thế nào?

Một JVM có thể có hàng nghìn class và nhiều class loader. Không nên dùng một boolean `agentEnabled=true` để thể hiện thành công trên tất cả mục tiêu. Nên đếm:

```text
requestedTargets = 30
appliedTargets   = 24
skippedTargets   = 4
failedTargets    = 2

reportedCoverage = 24 / 30 = 80%
```

Các số trên chỉ là ví dụ. Công thức coverage cần định nghĩa rõ mẫu số: **các mục tiêu được yêu cầu**, chứ không phải toàn bộ class JVM. Nếu một class có nhiều bản theo defining loader, cần thống kê theo định nghĩa mục tiêu đã chọn. Với hệ thống metric, dùng counter theo `feature/status/reason`; tên class chi tiết nên đưa vào structured logs hoặc bản báo cáo có giới hạn cardinality.

## 8. Xử lý lỗi sau precheck: capability true vẫn có thể thất bại

Ngay cả khi `isRetransformClassesSupported() == true` và `isModifiableClass(target) == true`, `retransformClasses` vẫn có thể thất bại:

- `UnmodifiableClassException`: lớp không cho thay đổi.
- `UnsupportedOperationException`: cấu hình không hỗ trợ thao tác hoặc phép biến đổi vi phạm giới hạn cho lớp đã nạp (ví dụ thay đổi cấu trúc không được hỗ trợ).
- `ClassFormatError`, `UnsupportedClassVersionError`, `NoClassDefFoundError`, `ClassCircularityError` hoặc `LinkageError`: bytecode mới không hợp lệ/không tương thích theo các ràng buộc JVM tương ứng.
- Một `transform` có thể ném exception nhưng JVM vẫn tiếp tục chuỗi transformer; nếu transformation không được áp, phải dựa vào hậu kiểm để tránh báo thành công giả.

Với `redefineClasses` có thể có các lỗi tương tự, và thao tác còn cần `ClassDefinition` chứa bytes tương ứng. Với `setNativeMethodPrefix`, ngoài `UnsupportedOperationException` nếu thiếu capability, `IllegalArgumentException` có thể xuất hiện nếu transformer chưa đăng ký. Với `redefineModule`, `UnmodifiableModuleException` liên quan module không sửa được.

**Chính sách lỗi nên phân nhóm:**

| Phân nhóm | Ví dụ | Hướng xử lý |
|---|---|---|
| Unsupported trước khi thực thi | `isRetransformClassesSupported=false` | Không gọi API; chọn fallback hợp lệ hoặc `SKIPPED` |
| Mục tiêu không thích hợp | `isModifiableClass=false` | `SKIPPED target`; ghi class và lý do |
| Không đủ dữ liệu fallback | Thiếu class bytes hợp lệ cho redefine | `SKIPPED` hoặc yêu cầu triển khai khác; không tự tạo bytes sai |
| API từ chối ở runtime | `UnsupportedOperationException`, `UnmodifiableClassException` | `FAILED` với nguyên nhân; chỉ thử fallback nếu tương thích và có chính sách rõ |
| Bytecode/transformer bị lỗi | `ClassFormatError`, `VerifyError`, lỗi bên trong transformer | `FAILED`, giữ bằng chứng/phiên bản; không khai báo đã cài probe |
| Hậu kiểm không khớp | API hoàn tất nhưng không có event/hành vi cần thiết | `UNVERIFIED/FAILED` theo yêu cầu; không công bố `APPLIED` |
| Feature bắt buộc | Mọi fallback thiếu hiệu lực trên lớp hiện tại | Đánh dấu không sẵn sàng, yêu cầu restart/redeploy/sửa cấu hình |

Đừng catch mọi exception và in “instrumentation disabled” một cách chung chung; thông tin về **không hỗ trợ**, **không phù hợp**, **lỗi thực thi** và **thiếu hậu kiểm** ảnh hưởng cách khắc phục khác nhau. Đồng thời không nuốt `VirtualMachineError` hay lỗi nghiêm trọng khác để bắt ứng dụng tiếp tục như bình thường nếu không có chính sách đủ mạnh.

## 9. Ba tình huống thực tế nên quyết định như thế nào?

### Tình huống A — agent gắn vào JVM đang chạy, cần tracing cho lớp đã nạp

Đề bài: “Ghi dấu tất cả lời gọi mới của `PaymentService` ngay lập tức”.

- Nếu `retransform=true`, class modifiable và transformer tạo bytecode hợp lệ, dùng retransform, sau đó xác minh probe thật sự ghi trace.
- Nếu `retransform=false` nhưng `redefine=true`, chỉ dùng redefine khi có **bytecode thay thế tương đương đã kiểm chứng** và chấp thuận tác động.
- Nếu cả hai không khả dụng, việc kích hoạt load-time transformer cho lớp nạp sau chỉ là **giảm phạm vi**. Báo `PaymentService=SKIPPED`; không gọi là “đã bật tracing”.
- Nếu yêu cầu bắt buộc, đề xuất chạy startup agent ở lần triển khai tiếp theo hoặc thay đổi thiết kế quan sát của ứng dụng.

### Tình huống B — profiler muốn hỗ trợ native method prefix trên nhiều JVM

Đề bài: “Bọc các phương thức native để quan sát call chain qua cơ chế prefix của Instrumentation”.

- Kiểm tra `isNativeMethodPrefixSupported()` và manifest `Can-Set-Native-Method-Prefix`.
- Khi được hỗ trợ, đăng ký transformer trước khi gọi `setNativeMethodPrefix` và kiểm tra kết quả instrumentation.
- Khi không hỗ trợ, không thử gọi rồi bỏ qua exception. Có thể ghi số liệu ở wrapper tầng Java nếu nó đáp ứng được nhu cầu, nhưng phải báo phạm vi khác JNI-level wrapping. Nếu không đủ, `SKIPPED reason=NATIVE_PREFIX_UNSUPPORTED`.

### Tình huống C — agent cần mở package trong module để gọi helper

Đề bài: “Agent cần deep reflection vào package của một named module”.

- Kiểm tra `isModifiableModule(targetModule)` và hợp lệ của package/module đích.
- Nếu được phép, `redefineModule` có thể **bổ sung** opens/exports/reads phù hợp; nó không xóa các quan hệ cũ.
- Nếu không được phép, không tự mở module khác hoặc áp `--add-opens` vào JVM đang chạy như thể là cùng thao tác; có thể cần thay cấu hình khởi động cho lần chạy sau.
- Dù module modifiable, vẫn cần chứng minh quyền truy cập thực tế của helper và không vượt chính sách bảo mật ứng dụng.

## 10. Các lỗi thiết kế cần tránh

1. **Chỉ dựa vào version JDK:** cùng Java 21 có thể có agent manifest và capability/configuration khác nhau; phải hỏi `Instrumentation` hiện tại.
2. **Chỉ kiểm tra capability toàn JVM:** một class riêng có thể unmodifiable; phải kiểm tra thêm `isModifiableClass`.
3. **Gọi `addTransformer(t, true)` khi không có retransform:** gây `UnsupportedOperationException`; hãy chọn `true/false` từ capability.
4. **Tự chuyển sang `redefineClasses` mà không có bytes chuẩn:** đây là thao tác thay định nghĩa lớp, không phải phiên bản thay tên của retransform.
5. **Coi load-time transformer là cập nhật lớp cũ:** đã đăng ký transformer không có nghĩa các class đã nạp sẽ được instrument.
6. **Không phân biệt trạng thái:** optional `SKIPPED` khác `FAILED` lúc thực thi; `DEGRADED` phải nêu rõ phần chức năng bị mất.
7. **Ghi log chung “agent started”:** không thể suy ra phần trăm class đã instrument từ trạng thái process agent.
8. **Bỏ qua hậu kiểm:** callback chạy/`retransformClasses` trả về nhưng transformer có thể trả `null`.
9. **Catch và che lỗi không phục hồi:** nuốt lỗi verifier/linkage có thể khiến công cụ tiếp tục với giả định sai.
10. **Tự mở rộng phạm vi fallback:** đừng đổi sang sửa module/native method hoặc thay class loader chỉ vì đường đi ban đầu thiếu capability.
11. **Quên class loader:** hai class cùng binary name do hai defining class loader định nghĩa là hai mục tiêu khác nhau; thống kê và thay đổi phải gắn đúng `Class<?>`.
12. **Lặp lại thao tác mù quáng:** khi năng lực không được hỗ trợ, retry liên tục không tạo thêm capability; trạng thái hỗ trợ retransformation/redefinition ổn định trong một JVM instance theo API.
13. **Không có tiêu chí thành công:** APPLIED nên đi kèm bằng chứng cụ thể, ví dụ probe event, class hash/bytecode version phù hợp hoặc kiểm chứng đường đo.

## 11. Câu hỏi tự kiểm tra

1. **`isModifiableClass(target)=true` nhưng `isRetransformClassesSupported=false`. Có gọi retransform được không?** Không. Hai điều kiện độc lập; muốn retransform cần cả hai.
2. **Agent không hỗ trợ retransform có thể dùng `addTransformer(t)` không?** Có, cho các lần định nghĩa lớp mới (và callback ở những tình huống khác theo hợp đồng); không tự thay lớp đã nạp.
3. **`isRedefineClassesSupported=true` có đủ để thay thế retransform không?** Không. Cần bytecode thay thế tương thích và chứng minh kết quả đáp ứng mục tiêu.
4. **Transformer trả `null` sau callback, có thể báo probe đã được cài không?** Không. `null` là không thay class bytes ở callback đó; phải có bằng chứng khác nếu muốn báo feature đã áp.
5. **Một class đã nạp không modifiable nhưng các class khác modifiable. Có dừng toàn bộ agent không?** Phụ thuộc chính sách feature; có thể `SKIP` class đó và tiếp tục mục tiêu khác, đồng thời ghi rõ coverage thiếu.
6. **`isModifiableModule=true` có nghĩa class trong module redefine được không?** Không. Đây là điều kiện của `redefineModule`, không phải `redefineClasses`.
7. **Fallback chỉ hoạt động với lớp sẽ nạp sau có thể báo “100% coverage” cho các lớp đã nạp không?** Không. Phải ghi phạm vi thật và số mục tiêu bị bỏ qua.
8. **Capability true nhưng JVM từ chối bytecode sau retransform thì trạng thái gì?** `FAILED` cho thao tác đó; không ép `APPLIED`. Ghi exception và nguyên nhân để xử lý.
9. **Tại sao cần mã reason ổn định?** Để so sánh giữa JDK, JVM vendor, phiên bản agent, phát hiện lỗi lặp và quyết định cần sửa manifest hay mã biến đổi.
10. **Với feature bảo vệ bắt buộc, có được dùng một fallback không tương đương để cho ứng dụng báo ready không?** Không. Phải giữ điều kiện sẵn sàng theo hợp đồng của feature.

## 12. Tài liệu tham khảo chính thức

- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `isRetransformClassesSupported`, `isRedefineClassesSupported`, `isNativeMethodPrefixSupported`, `isModifiableClass`, `isModifiableModule`, ngoại lệ và giới hạn API.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback cho class load/redefine/retransform, tham số `canRetransform` và ngữ nghĩa trả `null`.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): entry point `premain`/`agentmain` và các manifest attributes `Can-*`.
- [Java SE 21 — ClassDefinition](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassDefinition.html): bytecode thay thế dùng với `redefineClasses`.

**Ghi nhớ:** Phát hiện capability trước, kiểm tra mục tiêu và ngữ nghĩa trước khi chọn fallback, rồi **báo chính xác phạm vi đã làm được**. Khi không có phương án tương đương, `SKIPPED` kèm lý do là kết quả hợp lệ cho tính năng tùy chọn; báo “đã thành công” khi chưa instrument được mục tiêu mới là lỗi.