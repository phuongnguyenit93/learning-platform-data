# Lọc tập lớp để lập kế hoạch biến đổi và ghi nhận lớp bỏ qua

Trong Java Instrumentation, việc biết **lớp nào đang được JVM nạp** mới chỉ là bước đầu. Một agent an toàn cần trả lời ba câu hỏi riêng biệt: **Lớp nào thuộc phạm vi cần instrument? Lớp nào thực sự đủ điều kiện để biến đổi? Những lớp không được chọn hoặc không thể biến đổi bị bỏ qua vì lý do gì?**

Đây là mục tiêu của bài **“Lọc tập lớp để lập kế hoạch biến đổi và ghi nhận lớp bỏ qua”** trong chủ đề **Khảo sát khi chạy**. Thay vì lấy toàn bộ kết quả `Instrumentation.getAllLoadedClasses()` rồi gọi `retransformClasses(...)` trên tất cả, ta tạo **một bản kế hoạch có giải thích được** (*explainable transformation plan*): đối với từng ứng viên, ghi `READY` hoặc một **skip reason** cụ thể, chỉ đưa những lớp qua kiểm tra vào danh sách thực thi.

Một quy trình chuẩn có bốn pha:

~~~text
KHẢO SÁT
  Instrumentation.getAllLoadedClasses()
       |
       v
LỌC PHẠM VI
  tên lớp, loader/module, package, denylist/allowlist
       |
       v
ĐÁNH GIÁ KỸ THUẬT
  array/primitive, policy, capability, isModifiableClass
       |
       v
KẾ HOẠCH CÓ KIỂM TOÁN
  READY: Class<?> mục tiêu
  SKIP: Class<?> + lý do rõ ràng
       |
       +--> DRY_RUN: chỉ báo cáo
       |
       +--> APPLY: kiểm tra lại, đăng ký transformer,
                   retransform đúng tập READY
~~~

**Nguyên tắc chính:** *“Đang được load” không đồng nghĩa “nên biến đổi”; “modifiable” không đồng nghĩa “mọi bytecode đều hợp lệ”; “bỏ qua” phải có lý do có thể giải thích và đo lường.* Bài học tập trung vào cách tạo kế hoạch có kiểm toán. Một ví dụ Java 17+ đầy đủ có cả `DRY_RUN` và lệnh `--apply` minh họa thực thi có chủ đích.

## 1. Vì sao không instrument toàn bộ các class đã load?

Một JVM thường chứa class của nhiều nguồn khác nhau: JDK, framework, ứng dụng, agent, test runner, proxy động, class sinh ra tại runtime và những class đến từ custom class loader. Chỉ vì một class xuất hiện trong tập khảo sát không có nghĩa instrumentation của bạn dành cho nó.

Nếu truyền thẳng toàn bộ mảng vào `retransformClasses`, có thể gặp:

- **Array class và primitive class**: API quy định chúng **không bao giờ modifiable**.
- **Class của JDK hoặc agent**: có nguy cơ can thiệp vào class loading, runtime, logging hoặc helper của chính agent.
- **Các class ngoài phạm vi nghiệp vụ**: tăng overhead mà không thu được dữ liệu hữu ích.
- **Class được định nghĩa bởi loader khác**: hai class có thể cùng binary name nhưng khác runtime identity.
- **Class implementation-specific**: JVM có thể báo không modifiable.
- **Class chứa bytecode mà transformer chưa xử lý được**: việc `isModifiableClass(...) == true` không bảo đảm output sẽ hợp lệ.
- **Khối lượng quá lớn**: quét hoặc sửa hàng nghìn class có thể gây áp lực CPU, bộ nhớ, safepoint và độ trễ.
- **Lỗi khó truy nguyên**: khi không ghi `SKIP_*`, ta khó biết một method không được đo vì chính sách, vì capability hay vì chưa được nạp.

Giải pháp là tách ba tầng quyết định:

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Phát hiện** (*discovery*) | Class đã xuất hiện trong JVM chưa? | `getAllLoadedClasses()` |
| **Chính sách** (*policy*) | Nó có thuộc phạm vi cần đo không? | `demo.app.WorkService` được cho phép; `java.lang.String` nằm ngoài phạm vi |
| **Khả năng kỹ thuật** (*eligibility*) | JVM/agent có thể retransform nó không? | `isRetransformClassesSupported()` và `isModifiableClass(type)` |

Kết quả nên là **một danh sách ứng viên có trạng thái**, không phải chỉ một danh sách tên class đã được in log.

## 2. Khảo sát bằng Instrumentation.getAllLoadedClasses()

API trọng tâm:

~~~java
Class<?>[] snapshot = instrumentation.getAllLoadedClasses();
~~~

Đây là **đoạn mã minh họa**, yêu cầu một `Instrumentation instrumentation` đã nhận từ `premain` hoặc `agentmain`.

Theo Javadoc của Java SE 21, `getAllLoadedClasses()` trả về mảng chứa các class/interface hiện đang được JVM nạp, **bao gồm hidden classes/interfaces và array classes**. Đây là kết quả **tại thời điểm lấy snapshot**, không phải danh sách được cập nhật liên tục.

### 2.1. Snapshot là ảnh chụp, không phải khóa toàn JVM

Một class có thể được nạp **sau khi** bạn lấy mảng; một class loader có thể bị thu gom khi không còn được tham chiếu. Giữ các `Class<?>` trong kế hoạch quá lâu còn có thể **ngăn class loader được unload** vì các tham chiếu mạnh trong agent.

Hệ quả vận hành:

1. **Thu thập** snapshot.
2. **Lọc** nhanh, tạo các bản ghi quyết định.
3. **Giải phóng** những tham chiếu không cần thiết; chỉ giữ `Class<?>` cho thao tác sắp thực hiện.
4. Nếu thời gian chờ giữa khảo sát và thực thi kéo dài, **khảo sát/kiểm tra lại**.
5. Muốn theo dõi các lớp được load *sau đó*, dùng một `ClassFileTransformer` cho load-time events; một snapshot đơn lẻ không thay thế theo dõi liên tục.

**Không** suy luận rằng `snapshot.length` là số class “có thể instrument”. Nó bao gồm cả những class mà chính sách hoặc JVM sẽ loại.

### 2.2. Phân biệt getAllLoadedClasses và getInitiatedClasses

Hai API liên quan nhưng có ý nghĩa khác nhau:

| API | Trả về |
| --- | --- |
| `getAllLoadedClasses()` | Tập class/interface hiện đang nạp trên toàn JVM, bao gồm cả array/hidden classes |
| `getInitiatedClasses(loader)` | Những class mà `loader` được ghi nhận là **initiating loader**, tức loader có thể tìm được bằng tên theo contract |

**Initiating loader không đồng nghĩa defining loader.** Một parent có thể thực sự định nghĩa class nhưng child loader vẫn được ghi nhận là initiating loader cho lần tham chiếu tới class đó. Do đó, không dùng `getInitiatedClasses(loader)` như bằng chứng duy nhất về **nơi class được định nghĩa**.

Nếu cần phân biệt identity, lấy `Class<?>` thực tế và xem `type.getClassLoader()`, `type.getModule()`. `loader == null` thường là bootstrap loader; đó là thông tin ngữ cảnh, không phải lỗi.

### 2.3. Không gọi Class.forName để “khảo sát thêm”

Một agent đang đọc `getAllLoadedClasses()` **không cần** dùng `Class.forName(name)` cho từng class tên tìm được. Làm như vậy có thể kích hoạt class loading hoặc initialization không chủ đích, lệch class loader identity và thay chính tập lớp mà ta đang cố quan sát.

Nếu đã có `Class<?> type` từ snapshot, hãy **xem metadata** của đối tượng đó; không nạp lại nó. Khi code `ClassFileTransformer.transform(...)` đang được gọi cho một class, nguyên tắc càng quan trọng: phân tích `className` và `classfileBuffer` đã được JVM cấp, không yêu cầu loader nạp lại chính target đang được định nghĩa.

## 3. Thiết kế kết quả của một phép lọc

Một bản ghi quyết định hữu ích nên trả lời:

- **Class nào?** Tên, identity của class loader, module (khi cần).
- **Kết quả?** `READY` hay `SKIP`.
- **Nếu SKIP, vì sao?** Mã lý do ổn định và có mô tả.
- **Chính sách nào?** Allowlist/denylist, version của policy.
- **Đã kiểm tra capability nào?** Retransform, redefine hoặc chỉ load-time.
- **Khi nào?** Thời điểm snapshot/lượt kế hoạch; không nhầm với thời điểm thực sự apply.
- **Thực thi hay mới xem trước?** `DRY_RUN` khác `APPLY`; không ghi nhãn “đã biến đổi” chỉ vì lớp nằm trong kế hoạch.

Ví dụ ở dạng bảng:

| Class | Quyết định | Giải thích |
| --- | --- | --- |
| `demo.app.WorkService` | `READY` | Trong allowlist, đã load, modifiable và có capability |
| `demo.app.ReportService` | `READY` | Thỏa các điều kiện giống trên |
| `demo.app.internal.InternalHelper` | `SKIP_EXCLUDED_PACKAGE` | Policy bảo vệ lớp hạ tầng |
| `java.lang.String` | `SKIP_OUTSIDE_SCOPE` | Không thuộc mục tiêu nghiệp vụ |
| `int[]` | `SKIP_ARRAY` | Array classes không modifiable |
| `int` | `SKIP_PRIMITIVE` | Primitive classes không modifiable |

Hai dòng cuối là **ứng viên minh họa chính sách**. Một chương trình có thể đưa chúng vào tập kiểm tra riêng để chứng minh lý do skip, bất kể chúng có xuất hiện trong snapshot cụ thể hay không.

## 4. Thứ tự lọc để chi phí thấp và lý do ổn định

Một chính sách hợp lý nên áp dụng điều kiện **từ rẻ và dứt khoát tới đắt/phụ thuộc JVM**:

~~~text
Class<?> type
  |
  +-- null? -----------------------> SKIP_INVALID_CANDIDATE
  +-- primitive? ------------------> SKIP_PRIMITIVE
  +-- array? ---------------------> SKIP_ARRAY
  +-- hidden theo policy? --------> SKIP_HIDDEN_POLICY
  +-- không thuộc snapshot? ------> SKIP_NOT_IN_SNAPSHOT
  +-- package agent/helper? ------> SKIP_EXCLUDED_PACKAGE
  +-- không khớp allowlist? ------> SKIP_OUTSIDE_SCOPE
  +-- capability thiếu? ----------> SKIP_NO_RETRANSFORM_CAPABILITY
  +-- không modifiable? ----------> SKIP_NOT_MODIFIABLE
  |
  +-------------------------------> READY
~~~

Đây là **một thứ tự do agent chọn**, không phải thứ tự bắt buộc trong JVM. Ý nghĩa của nó: mỗi class được ghi **một lý do chính** có thể tái lập. Có thể ghi thêm **nhiều lý do phụ** nếu audit yêu cầu, nhưng cần phân biệt *primary reason* với *all applicable reasons*.

Ví dụ `java.lang.String` là class của JDK, có thể thuộc nhóm JVM cho phép sửa trong môi trường cụ thể. Ta vẫn chọn `SKIP_OUTSIDE_SCOPE` nếu policy không instrument JDK. Không nên cố kiểm tra xem nó modifiable để rồi ghi `SKIP_NOT_MODIFIABLE` và vô tình làm mờ **lý do thực sự: agent không muốn đụng vào class này**.

### 4.1. Vì sao kiểm tra primitive và array trước?

Javadoc bảo đảm `isModifiableClass(primitiveType)` và `isModifiableClass(arrayType)` trả `false`; bạn có thể trực tiếp phân loại bằng `type.isPrimitive()` và `type.isArray()`, tiết kiệm một số lời gọi instrumentation và làm rõ lý do kỹ thuật.

Đừng suy luận từ `type.isFinal()` (không có API đó) hay từ `java.lang.reflect.Modifier.isFinal(type.getModifiers())` rằng class `final` không thể retransform. **Final class không đồng nghĩa unmodifiable class**.

### 4.2. Hidden, proxy và generated classes

`Class.isHidden()` có từ Java 15. Một chính sách an toàn có thể loại hidden class để tránh instrument các class do runtime sinh ra, nhưng phải ghi đúng `SKIP_HIDDEN_POLICY`: **đó là lựa chọn policy**. Không dùng mã lý do như thể mọi hidden/proxy/record/enum/interface đều bị JVM cấm trong mọi điều kiện.

Tương tự, loại các class tên có `$$Lambda`, `$Proxy`, `CGLIB` hoặc các tên generated cụ thể chỉ là một **heuristic**, có thể sai ở framework/version khác. Khi đưa vào production, nên có allowlist và kiểm thử thật thay vì lọc mù quáng chỉ theo mẫu tên.

### 4.3. Class loader và module

Hai `Class<?>` có thể cùng tên `com.example.Service` nhưng được **hai defining loaders khác nhau** định nghĩa; chúng là hai runtime classes khác nhau. Nếu policy muốn instrument chỉ một application loader, phải dùng **identity của loader**, không chỉ `type.getName()`.

Module cũng quan trọng trong JPMS: bạn có thể muốn chỉ chọn `type.getModule().getName()` nhất định. Tuy nhiên `module == null` hoặc module name `null` có thể xuất hiện ở tình huống phù hợp; xử lý null-safe. Việc class modifiable không tự làm cho helper của agent được module target đọc hoặc truy cập.

## 5. Capability và modifiability: hai điều kiện độc lập

Nếu kế hoạch dự định dùng **retransformation**, kiểm tra:

~~~java
boolean capable = instrumentation.isRetransformClassesSupported();
boolean modifiable = instrumentation.isModifiableClass(target);
~~~

Đây là **mảnh code**: `instrumentation` do JVM cung cấp và `target` là một `Class<?>` khác `null`.

- `isRetransformClassesSupported()` phản ánh capability của JVM/agent configuration. Để hỗ trợ, JAR agent phải có manifest `Can-Retransform-Classes: true` và JVM cũng phải cho phép.
- `isModifiableClass(target)` kiểm tra class cụ thể. Kết quả **không phụ thuộc** vào việc retransform capability có bật hay không.
- Cả hai đều phải thỏa để một class có thể được retransform, nhưng **chưa đủ để bảo đảm bytecode cuối hợp lệ**.

Trong một kế hoạch dùng `redefineClasses(...)`, điều kiện capability tương ứng là `isRedefineClassesSupported()` và manifest `Can-Redefine-Classes: true`. Đừng thay nhầm hai capability.

### Vẫn có thể thất bại sau READY

`READY` nghĩa là class **đủ điều kiện sơ bộ** tại thời điểm lập kế hoạch, không phải “chắc chắn transform thành công”. JVM có thể từ chối vì:

- Bytecode do transformer trả về sai định dạng hoặc verifier phát hiện lỗi.
- Thay đổi cấu trúc class không được hỗ trợ (thêm/xóa field, đổi signature, quan hệ kế thừa...).
- Lớp hoặc môi trường đã đổi giữa snapshot và apply.
- Một transformer khác trong chain tạo output không hợp lệ.
- Agent gặp lỗi linkage/class loader/module trong quá trình thực thi.

Vì vậy phân biệt các trạng thái **PLANNED_READY**, **APPLY_ATTEMPTED**, **APPLIED**, **APPLY_FAILED** thay vì coi `READY` là đã sửa xong.

## 6. Phân loại lý do bỏ qua theo nhóm

Một hệ thống thực tế có thể đặt mã lý do theo **taxonomy** để dashboard và audit dễ hiểu:

| Nhóm | Mã ví dụ | Ý nghĩa |
| --- | --- | --- |
| Phạm vi | `SKIP_OUTSIDE_SCOPE` | Không thuộc allowlist class/module/loader |
| Phạm vi | `SKIP_EXCLUDED_PACKAGE` | Là agent/helper/logger hoặc namespace bị bảo vệ |
| Phạm vi | `SKIP_HIDDEN_POLICY` | Chính sách không đụng hidden classes |
| Loại class | `SKIP_PRIMITIVE` | Class biểu diễn primitive; không modifiable |
| Loại class | `SKIP_ARRAY` | Array class; không modifiable |
| Snapshot | `SKIP_NOT_IN_SNAPSHOT` | Ứng viên không xuất hiện trong ảnh chụp đang xét |
| Capability | `SKIP_NO_RETRANSFORM_CAPABILITY` | Agent/JVM chưa bật khả năng retransformation |
| Khả năng | `SKIP_NOT_MODIFIABLE` | `isModifiableClass(type) == false` |
| Tính sẵn sàng | `SKIP_NOT_YET_LOADED` | Class mục tiêu chưa được load, nếu có danh sách kỳ vọng từ cấu hình |
| Tính tương thích | `SKIP_UNSUPPORTED_TARGET_VERSION` | Quy tắc xử lý bytes chưa hỗ trợ class-file version đó, xác định bằng parser |
| Trạng thái | `SKIP_ALREADY_INSTRUMENTED` | Policy tránh chèn lặp; cần marker/metadata có thể kiểm chứng |
| Vận hành | `SKIP_BUDGET_LIMIT` | Đã hết budget/limit số class hoặc thời gian xử lý |

Những mã trên là **thiết kế ứng dụng**, không phải các constant do Java Instrumentation định nghĩa sẵn. Code demo bên dưới sử dụng một tập con. Nếu class có nhiều lý do, nên định nghĩa thứ tự ưu tiên ổn định và/hoặc lưu danh sách đầy đủ để báo cáo không gây hiểu nhầm.

**Không ghi lỗi apply thành skip** nếu thực tế đã gọi `retransformClasses(...)` rồi thao tác thất bại. `SKIP` là quyết định **trước apply**; sau khi thử apply cần có `APPLY_FAILED + error category` rõ ràng.

## 7. Chế độ dry-run và thực thi có chủ đích

**Dry-run** rất hữu ích trong instrumentation production: có thể trả lời “agent *sẽ* sửa những class nào?” mà không đưa bytes nào vào JVM. Quy trình:

1. Lấy snapshot.
2. Áp dụng filter và policy.
3. Tạo danh sách `READY` và `SKIP(code)`.
4. In/ghi số lượng theo reason.
5. **Không** gọi `retransformClasses` hay `redefineClasses`.
6. Cho phép người vận hành xem kế hoạch, sau đó mới thực thi nếu có yêu cầu rõ ràng.

Khi **apply**, nên:

1. Kiểm tra capability và modifiability sát thời điểm thao tác.
2. Đảm bảo transformer được đăng ký với capability phù hợp.
3. Tạo array đúng các `Class<?>` đã qua kiểm tra, không chuyển thành tên rồi `Class.forName` lại.
4. Gọi `retransformClasses(readyArray)`.
5. Ghi **kết quả thực thi** tách khỏi kết quả plan.
6. Tháo transformer khi phù hợp, giải phóng references/buffers.
7. Nếu thao tác thất bại, ghi lỗi và không tuyên bố thành công.

Chú ý rằng dù một transformer **trả `null`** (không đổi bytes ở bước của nó), việc gọi `retransformClasses` vẫn là **một thao tác retransformation thực sự**; các transformers khác có thể được gọi lại. Do đó “apply với observer-only transformer” **không tương đương dry-run tuyệt đối** trong JVM có các agent khác.

## 8. Java agent JDK 17+ hoàn chỉnh: tạo kế hoạch và ghi skip reasons

Demo này chạy trên JDK 17+ và gồm hai mode:

- **Mặc định**: chỉ khảo sát/ghi quyết định, in `mode=DRY_RUN`, **không** gọi retransform.
- **`--apply`**: dùng tập `READY` để gọi `retransformClasses`, đăng ký một observer transformer trả `null` nhằm ghi nhận callback. Không cố tình thay method body.

Để stdout có thể tái lập, ví dụ tạo **một danh sách sáu ứng viên cố định**, đồng thời dùng **snapshot thật từ `getAllLoadedClasses()` để xác nhận các class ứng dụng đã load**. Đây là ví dụ về **bộ lọc trên tập ứng viên được chọn**, không giả vờ in toàn bộ hàng nghìn class của JVM. Khi vận hành thật, có thể mở rộng sang duyệt mọi `Class<?>` trong snapshot trước khi áp policy.

### 8.1. Tổ chức thư mục

~~~text
survey-plan-demo/
├── agent-src/
│   └── demo/agent/SurveyAgent.java
├── app-src/
│   └── demo/app/
│       ├── WorkService.java
│       ├── ReportService.java
│       ├── RunSurvey.java
│       └── internal/InternalHelper.java
└── agent.mf
~~~

Hai thư mục output `agent-bin/` và `app-bin/` được sinh ở bước biên dịch; `survey-agent.jar` là JAR agent. Tách agent với app giúp minh họa rằng `Instrumentation` được cấp cho **agent**, không phải do app tự tạo.

### 8.2. agent-src/demo/agent/SurveyAgent.java

~~~java
package demo.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Set;

public final class SurveyAgent {
    private static volatile Instrumentation instrumentation;

    public static void premain(String args, Instrumentation inst) {
        instrumentation = inst;
        System.out.println("agentReady=true");
    }

    public static void plan(boolean apply, Class<?>... samples) throws Exception {
        Instrumentation inst = instrumentation;
        if (inst == null) {
            throw new IllegalStateException("Use -javaagent:survey-agent.jar");
        }
        Set<Class<?>> loaded = Collections.newSetFromMap(new IdentityHashMap<>());
        for (Class<?> loadedType : inst.getAllLoadedClasses()) {
            loaded.add(loadedType);
        }
        boolean capable = inst.isRetransformClassesSupported();
        System.out.println("retransformSupported=" + capable);

        List<Class<?>> ready = new ArrayList<>();
        int skipped = 0;
        for (Class<?> type : samples) {
            String reason = classify(inst, loaded, capable, type);
            System.out.println(reason + " " + type.getTypeName());
            if ("READY".equals(reason)) {
                ready.add(type);
            } else {
                skipped++;
            }
        }
        System.out.println("ready=" + ready.size() + " skipped=" + skipped);
        if (!apply) {
            System.out.println("mode=DRY_RUN");
            return;
        }
        System.out.println("mode=APPLY");
        ClassFileTransformer observer = new ClassFileTransformer() {
            @Override
            public byte[] transform(Module module, ClassLoader loader,
                    String className, Class<?> classBeingRedefined,
                    ProtectionDomain domain, byte[] bytes) {
                if ("demo/app/WorkService".equals(className)
                        || "demo/app/ReportService".equals(className)) {
                    System.out.println("transformed=" + className);
                }
                return null;
            }
        };
        inst.addTransformer(observer, true);
        try {
            inst.retransformClasses(ready.toArray(new Class<?>[0]));
            System.out.println("applyCount=" + ready.size());
        } finally {
            inst.removeTransformer(observer);
        }
    }

    private static String classify(Instrumentation inst, Set<Class<?>> loaded,
            boolean capable, Class<?> type) {
        if (type.isPrimitive()) return "SKIP_PRIMITIVE";
        if (type.isArray()) return "SKIP_ARRAY";
        if (type.isHidden()) return "SKIP_HIDDEN_POLICY";
        if (!loaded.contains(type)) return "SKIP_NOT_IN_SNAPSHOT";
        if (type.getName().startsWith("demo.app.internal."))
            return "SKIP_EXCLUDED_PACKAGE";
        if (!type.getName().equals("demo.app.WorkService")
                && !type.getName().equals("demo.app.ReportService"))
            return "SKIP_OUTSIDE_SCOPE";
        if (!capable) return "SKIP_NO_RETRANSFORM_CAPABILITY";
        if (!inst.isModifiableClass(type)) return "SKIP_NOT_MODIFIABLE";
        return "READY";
    }
}
~~~

#### Đọc code ở bốn tầng

**Tầng 1 — Snapshot:** `getAllLoadedClasses()` cấp tập class đã load. `IdentityHashMap` cho tập bằng reference identity của `Class<?>`, không nhầm hai class cùng tên do hai class loaders khác nhau định nghĩa.

**Tầng 2 — Plan:** `classify(...)` trả về **một mã trạng thái**. Kiểm tra primitive/array xảy ra trước snapshot membership, nên các loại đó vẫn được ghi đúng `SKIP_PRIMITIVE`/`SKIP_ARRAY` ngay cả khi không xuất hiện trong một snapshot cụ thể.

**Tầng 3 — Preview:** Nếu `apply == false`, phương thức chỉ in tổng số và `mode=DRY_RUN`, rồi trả về. Không có `addTransformer` hoặc `retransformClasses` trong nhánh này.

**Tầng 4 — Apply:** Agent chỉ gọi `retransformClasses(...)` với danh sách `ready` và đăng ký observer `canRetransform=true`. Trong callback, `className` dùng internal name có dấu `/`; `return null` thể hiện observer không chủ ý thay class bytes. Cuối thao tác, transformer được remove trong `finally`. Do class loading có concurrency, `removeTransformer` không bảo đảm tuyệt đối rằng không còn callback đang chạy tại chính thời điểm remove.

**Giới hạn của bản demo:** `plan(...)` nhận danh sách ứng viên do app gửi để có stdout cố định; nó **không** phải một công cụ discovery tổng quát có policy đọc từ file. Các tên cho phép đã được cố định trong `classify`; cần thay bằng cấu hình có kiểm thử nếu áp dụng production. Nó cũng không bắt/mã hóa mọi lỗi apply thành status record; production code phải thêm tầng thực thi có trạng thái và logging phù hợp.

### 8.3. app-src/demo/app/WorkService.java

~~~java
package demo.app;

public final class WorkService {
    public int execute() {
        return 7;
    }
}
~~~

Đây là một class ứng dụng **được phép** theo allowlist của demo. Không cần có annotation đặc biệt để `Instrumentation.isModifiableClass(...)` hoạt động.

### 8.4. app-src/demo/app/ReportService.java

~~~java
package demo.app;

public final class ReportService {
    public String report() {
        return "ok";
    }
}
~~~

Lớp này cũng thuộc allowlist, được dự kiến `READY` nếu JVM/agent hỗ trợ retransformation và class modifiable. Đây là **kết quả trên môi trường ví dụ**, không phải lời hứa mọi JVM đều cho phép sửa tất cả ứng dụng classes.

### 8.5. app-src/demo/app/internal/InternalHelper.java

~~~java
package demo.app.internal;

public final class InternalHelper {
    public void help() {
    }
}
~~~

Lớp này được cố tình đặt trong package `demo.app.internal` để chứng minh **policy exclusion**. Nó có thể modifiable về mặt JVM nhưng không nên nằm trong kế hoạch instrumentation của ứng dụng.

### 8.6. app-src/demo/app/RunSurvey.java

~~~java
package demo.app;

import demo.agent.SurveyAgent;
import demo.app.internal.InternalHelper;

public final class RunSurvey {
    public static void main(String[] args) throws Exception {
        new WorkService().execute();
        new ReportService().report();
        new InternalHelper().help();
        SurveyAgent.plan(args.length > 0 && "--apply".equals(args[0]),
                WorkService.class,
                ReportService.class,
                InternalHelper.class,
                String.class,
                int[].class,
                int.class);
    }
}
~~~

Các `new ...` đầu tiên bảo đảm ba lớp ứng dụng đã được dùng trước lúc agent lấy snapshot. Lời gọi `SurveyAgent.plan(...)` đưa đúng sáu ứng viên:

- Hai class ứng dụng trong allowlist.
- Một helper bị loại bởi policy.
- Một class JDK ngoài phạm vi.
- Một array class và một primitive class để minh họa trường hợp không modifiable.

Lệnh `new ...` ở đây là một phần **driver thử nghiệm**. Trong agent production, không nên tự khởi tạo hàng loạt classes của ứng dụng chỉ để khảo sát, vì nó có thể thay đổi ứng dụng và kích hoạt `<clinit>` không chủ đích. Khi làm real discovery, lấy từ `getAllLoadedClasses()` thay vì cố ép class vào snapshot.

### 8.7. Tệp agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: demo.agent.SurveyAgent
Can-Retransform-Classes: true
~~~

**Manifest phải có dòng trống cuối.** Mục `Can-Retransform-Classes: true` cho phép agent **yêu cầu** retransformation nếu JVM hỗ trợ. Vì demo có mode `--apply`, thuộc tính này là cần thiết. Khi chỉ chạy `DRY_RUN`, tác vụ không thực thi retransform, nhưng vẫn có thể đọc capability.

### 8.8. Biên dịch, đóng JAR và chạy

Các lệnh sau dùng JDK **17+**, chạy từ thư mục gốc `survey-plan-demo/`.

Bash:

~~~bash
mkdir -p agent-bin app-bin

javac --release 17 -d agent-bin agent-src/demo/agent/SurveyAgent.java

javac --release 17 -cp agent-bin -d app-bin \
  app-src/demo/app/WorkService.java \
  app-src/demo/app/ReportService.java \
  app-src/demo/app/internal/InternalHelper.java \
  app-src/demo/app/RunSurvey.java

jar --create --file survey-agent.jar --manifest agent.mf -C agent-bin .

java -javaagent:survey-agent.jar -cp app-bin demo.app.RunSurvey
java -javaagent:survey-agent.jar -cp app-bin demo.app.RunSurvey --apply
~~~

Windows PowerShell (tránh các dấu `\` dùng để nối dòng trong ví dụ Bash):

~~~powershell
New-Item -ItemType Directory -Force -Path agent-bin, app-bin | Out-Null
javac --release 17 -d agent-bin agent-src/demo/agent/SurveyAgent.java
javac --release 17 -cp agent-bin -d app-bin app-src/demo/app/WorkService.java app-src/demo/app/ReportService.java app-src/demo/app/internal/InternalHelper.java app-src/demo/app/RunSurvey.java
jar --create --file survey-agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:survey-agent.jar -cp app-bin demo.app.RunSurvey
java -javaagent:survey-agent.jar -cp app-bin demo.app.RunSurvey --apply
~~~

Tại bước `javac app`, `-cp agent-bin` để compiler tìm thấy kiểu `SurveyAgent`. Khi chạy, agent JAR được JVM nạp qua `-javaagent`; trong môi trường thử nghiệm này, lớp agent được system class loader tìm thấy để ứng dụng gọi `SurveyAgent.plan(...)`. Với class loaders cách ly hoặc module systems riêng, cần thiết kế cầu giao tiếp agent/application rõ ràng.

### 8.9. Kết quả dry-run đã xác minh

**Stdout khi chạy trên Zulu OpenJDK 24, biên dịch bằng `--release 17`:**

~~~text
agentReady=true
retransformSupported=true
READY demo.app.WorkService
READY demo.app.ReportService
SKIP_EXCLUDED_PACKAGE demo.app.internal.InternalHelper
SKIP_OUTSIDE_SCOPE java.lang.String
SKIP_ARRAY int[]
SKIP_PRIMITIVE int
ready=2 skipped=4
mode=DRY_RUN
~~~

Ở mode này, agent không gọi `retransformClasses`. Chỉ có **kế hoạch**: hai ứng viên được đánh dấu `READY` và bốn ứng viên có lý do bỏ qua cụ thể.

Điểm đáng chú ý:

- `SKIP_EXCLUDED_PACKAGE` là **quyết định chính sách**, không nhất thiết là một lỗi khả năng sửa của JVM.
- `SKIP_OUTSIDE_SCOPE` cho `java.lang.String` không có nghĩa `String.class` chắc chắn unmodifiable; agent chỉ **không chọn** nó.
- `SKIP_ARRAY`/`SKIP_PRIMITIVE` phản ánh loại class mà API quy định không thể sửa.
- `retransformSupported=true` là **phụ thuộc môi trường chạy thử**; không được hardcode như một điều đúng cho mọi JVM/manifest.

### 8.10. Kết quả có --apply đã xác minh

Lệnh thứ hai chạy **một JVM mới**, không phải một lượt tiếp nối trong cùng JVM dry-run trước đó.

**Stdout:**

~~~text
agentReady=true
retransformSupported=true
READY demo.app.WorkService
READY demo.app.ReportService
SKIP_EXCLUDED_PACKAGE demo.app.internal.InternalHelper
SKIP_OUTSIDE_SCOPE java.lang.String
SKIP_ARRAY int[]
SKIP_PRIMITIVE int
ready=2 skipped=4
mode=APPLY
transformed=demo/app/WorkService
transformed=demo/app/ReportService
applyCount=2
~~~

Kết quả cho thấy observer transformer thực sự nhận callbacks cho hai class được chọn khi gọi `retransformClasses(...)`. Các class bị bỏ qua không được **đưa vào array retransform** của demo.

**Cẩn trọng về tên log:** `transformed=...` trong callback chỉ chứng minh **callback đã chạy**. Observer trả `null`, nên nó **không sửa bytes**. Đây không phải bằng chứng đã chèn instrumentation vào method. Muốn giám sát production chính xác, đặt tên `transformCallback=...` hoặc `retransformObserved=...` sẽ rõ hơn và không nhầm với thành công thay bytecode.

Ngoài ra, không nên suy luận rằng **thứ tự xử lý giữa hai class trong cùng một batch** luôn được bảo đảm giống stdout thử nghiệm. Bảo đảm về thứ tự các transformers **trong một chuỗi cho từng class** là vấn đề riêng, được quy định bởi `ClassFileTransformer`.

## 9. Mở rộng từ sáu ứng viên sang khảo sát toàn JVM

Demo đưa một danh sách mẫu để thuận tiện kiểm thử, nhưng agent thực tế thường muốn phát hiện **tất cả class đã load** đáp ứng policy. Một cách mở rộng:

~~~java
Class<?>[] all = instrumentation.getAllLoadedClasses();

for (Class<?> type : all) {
    if (type == null || type.isPrimitive() || type.isArray()) {
        continue;
    }

    String name = type.getName();
    if (!name.startsWith("com.acme.service.")) {
        continue;
    }

    // Tiếp tục kiểm tra loader/module, exclusions, capability,
    // isModifiableClass(type) rồi ghi READY hoặc SKIP với reason.
}
~~~

Đây là **mảnh code minh họa**, không phải chương trình độc lập; `com.acme.service.` là ví dụ về phạm vi package của một ứng dụng giả định. Không có class nào được gọi `Class.forName` trong vòng lặp; chỉ dùng những `Class<?>` đã có từ snapshot.

**Lưu ý về báo cáo đầy đủ:** Nếu bạn dùng `continue` ngay khi không khớp package, những lớp bị bỏ qua sớm **sẽ không xuất hiện trong audit**. Nếu yêu cầu nghiệp vụ là “ghi nhận lớp bỏ qua”, hãy quyết định rõ:

- **Audit toàn snapshot**: ghi `SKIP_OUTSIDE_SCOPE` cho mọi phần tử bị loại, có thể rất nhiều bản ghi.
- **Audit trong phạm vi quan tâm**: chỉ ghi skip reasons sau một filter sơ bộ trên package/loader và báo rõ tổng số bị loại ở prefilter.
- **Audit theo danh sách mục tiêu**: dùng một allowlist ứng viên có số lượng vừa phải, như demo, để mỗi ứng viên có một kết quả chi tiết.

Cả ba có thể đúng nếu **phạm vi báo cáo và mẫu số thống kê** được mô tả minh bạch.

### Không lưu lâu mảng allLoadedClasses

Trong hệ thống ứng dụng động như plugin architecture, một snapshot lưu ở singleton agent có thể giữ mạnh nhiều `Class<?>`, từ đó kéo theo class loader. Điều này có thể cản trở class unloading và gây leak. Phương án thường tốt hơn là **xử lý rồi giải phóng snapshot**, ghi kết quả audit dưới dạng metadata không giữ live references, và chỉ giữ `Class<?>` của những lớp cần áp dụng trong khoảng thời gian ngắn.

## 10. Ghi nhận skip reason sao cho hữu dụng trong vận hành

Một log “skipped” không đủ. Nên có **record có cấu trúc** hoặc ít nhất một dòng gồm reason code và định danh lớp.

Ví dụ JSON Lines mang tính minh họa:

~~~json
{"runId":"survey-001","className":"demo.app.internal.InternalHelper","outcome":"SKIP","reason":"SKIP_EXCLUDED_PACKAGE","phase":"PLAN"}
{"runId":"survey-001","className":"demo.app.WorkService","outcome":"READY","reason":null,"phase":"PLAN"}
{"runId":"survey-001","className":"demo.app.ReportService","outcome":"APPLIED","reason":null,"phase":"APPLY"}
~~~

Đây là **dữ liệu ví dụ**, không phải output thực tế của chương trình Java bên trên. Trong production, thêm định danh loader/module đủ để phân biệt class trùng tên. Nếu ghi thời gian, dùng timestamp có timezone; nếu ghi metrics, dùng số liệu được thu thập thực tế chứ không bịa phần trăm.

Một thiết kế có thể có hai bảng riêng:

| Bảng kế hoạch | Bảng thực thi |
| --- | --- |
| `planRunId`, `classKey`, `decision`, `skipReason`, `policyVersion` | `executionRunId`, `planRunId`, `classKey`, `attemptedAt`, `result`, `errorType` |
| Tạo **trước apply** | Tạo **sau khi thực sự thử apply** |
| `READY` không có nghĩa đã sửa | `APPLIED` chỉ khi thao tác thành công theo tiêu chí đã xác định |

Nếu không cần lưu toàn bộ hàng triệu class ngoài phạm vi, có thể **đếm theo reason** và lấy mẫu một số bản ghi. Nhưng phải nói rõ dashboard biểu diễn **tất cả classes được khảo sát** hay chỉ **ứng viên sau prefilter**.

### Đếm lý do và đảm bảo tính nhất quán

Với một chính sách **mỗi ứng viên có đúng một kết quả**, bảo đảm bất biến:

~~~text
evaluated = ready + skipped
skipped   = sum(count by primary skip reason)
attempted <= ready
applied + failed = attempted     (nếu mỗi attempt có một outcome cuối)
~~~

Ở demo: `evaluated=6`, `ready=2`, `skipped=4`. Vì mode dry-run không apply, `attempted=0`. Với mode apply thành công trong môi trường kiểm thử, `attempted=2`, `applied=2` theo **thao tác retransform**, chứ không phải 2 phép thay method body.

Nếu một class bị xuất hiện nhiều lần trong danh sách ứng viên, bạn phải chọn rõ: ghi hai lượt evaluation riêng hay **deduplicate theo `Class<?>` identity** trước khi đếm. Đừng deduplicate chỉ bằng tên khi có nhiều class loaders.

## 11. Chọn phạm vi bằng class loader, module và class name

Chọn package đơn giản có ích, nhưng đối với ứng dụng lớn, nên ghép nhiều điều kiện:

~~~text
selectionPolicy(type):
    targetPrefix = com.acme.order.
    definingLoader ∈ approvedApplicationLoaders
    module ∈ allowedModules (nếu chạy JPMS)
    className không nằm trong excludedAgentOrFrameworkPrefixes
    class không nằm trong denylist do sự cố
    parser hỗ trợ class-file version
~~~

Đây là **mô hình chính sách**, không phải cú pháp API trực tiếp. Một class có thể mang tên có prefix ứng dụng nhưng đến từ **custom loader của plugin không thuộc phạm vi**. Nếu chỉ dùng prefix, agent có thể instrument nhầm class đang vận hành bởi một tenant hoặc plugin khác.

Một ví dụ về điều kiện loader khi bạn đã nắm được class loader dự kiến:

~~~java
if (type.getClassLoader() != approvedLoader) {
    return "SKIP_UNAPPROVED_LOADER";
}
~~~

Đây là **mảnh code**, cần hai biến và được đặt trong classifier trả về chuỗi reason. Đừng viết `type.getClassLoader().equals(approvedLoader)` vì bootstrap loader có thể là `null`. So sánh `==` thể hiện đúng identity.

Đối với module:

~~~java
Module module = type.getModule();
String moduleName = module == null ? null : module.getName();
~~~

Module name có thể `null` với unnamed module. Không ghi “module null = invalid class”. Trong môi trường JPMS, class loader visibility và module readability/exports/opens là hai tầng khác nhau; một helper được agent load thành công vẫn có thể không được target module truy cập.

## 12. Nếu cần log lớp bị bỏ qua khi load-time transformation

Khảo sát `getAllLoadedClasses()` chỉ xét những class hiện đã load. Một transformer đăng ký đúng thời điểm có thể theo dõi **các định nghĩa class trong tương lai**:

~~~java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    if (className == null || !className.startsWith("com/acme/order/")) {
        return null;
    }

    // Filter có kiểm soát trong callback:
    // chỉ xử lý bytes, không yêu cầu loader nạp lại chính target.
    return null;
}
~~~

Đây là **mảnh code minh họa** bên trong lớp triển khai `ClassFileTransformer`. Ở load-time, `classBeingRedefined` thường là `null`: bạn **chưa có** đối tượng `Class<?>` mục tiêu để gọi `isModifiableClass(target)` theo cách dùng trong kế hoạch cho classes đã load. Do đó:

- **Loaded-class survey:** dùng `Class<?>` từ snapshot và đánh giá modifiability cho kế hoạch retransform.
- **Load-time transformer:** dùng `className` (internal name), `loader`, `module` và `classfileBuffer`; có thể ghi skip reasons theo policy ở chính callback.
- Không áp dụng máy móc một classifier đòi `Class<?>` vào callback load-time rồi gọi `Class.forName(target)` để tạo đối tượng thiếu.

Một agent kết hợp cả hai có thể thống nhất **tên mã reason**, nhưng phải phân biệt các giai đoạn và dữ liệu đầu vào.

## 13. Tái kiểm tra kế hoạch trước khi apply

Đừng biến một plan được lưu từ một giờ trước thành lệnh retransform vô điều kiện. Trước khi apply:

1. Xác nhận **đúng JVM/process** và đúng namespace class loader.
2. Xác nhận policy/version chưa đổi; nếu đổi, lập lại kế hoạch.
3. Đối với từng `Class<?>` còn giữ, xác nhận capability và `isModifiableClass`.
4. Chỉ đưa những class hiện còn hợp lệ vào batch.
5. Nếu có thể, chạy với nhóm nhỏ trước, rồi mở rộng dần.
6. Lưu kết quả **trong khi thực thi** và phân biệt lỗi từng batch.
7. Không tự động áp dụng lại một batch thất bại vô hạn.
8. Nếu transformer tạo bytecode, verify/test trên JDK và môi trường tương ứng.

### Một batch hay nhiều batch?

`retransformClasses(Class<?>... classes)` cho phép đưa nhiều classes trong một lời gọi, giúp áp dụng những thay đổi liên quan. Nếu bytes cuối không hợp lệ hoặc thao tác thất bại, contract quy định **không class nào trong lời gọi đó được retransform thành công**. Điều đó khác với gọi riêng từng class, nơi một lời gọi thành công trước có thể đã có hiệu lực khi lời gọi sau thất bại.

Chọn **batch cùng nhau** khi thay đổi liên quan về logic hoặc cần một đơn vị nhất quán; chọn **batch nhỏ** khi cần kiểm soát tác động và khả năng khoanh vùng lỗi. Đừng giả định việc chia nhỏ luôn tốt hơn, cũng đừng gửi toàn bộ JVM classes trong một batch khổng lồ.

### Lưu ý trạng thái khi transformer khác tồn tại

Khi retransformation xảy ra, các `ClassFileTransformer` có `canRetransform=true` được gọi lại; kết quả trước của transformers không có khả năng đó được tái áp dụng theo thứ tự quy định. Do đó, ngay cả observer của demo trả `null` vẫn có thể khiến **transformers khác** chạy lại. Nếu muốn một bước hoàn toàn không gây side effects, giữ ở **dry-run** và không gọi retransform.

## 14. Hiệu năng và an toàn khi khảo sát

### 14.1. Giảm chi phí

- Lấy `getAllLoadedClasses()` theo **sự kiện quản trị hoặc một chu kỳ hợp lý**, không gọi trên mỗi request HTTP.
- Lọc tên/loader/module sớm để tránh parse bytecode hoặc gọi nhiều API tốn chi phí.
- Tránh `Class.forName`, reflection sâu, class initialization hoặc gọi method nghiệp vụ trong vòng survey.
- Không ghi từng class của JDK vào logger đồng bộ nếu mục tiêu chỉ là một package ứng dụng.
- Giới hạn số lượng audit events, dùng bounded buffers, sampling, hoặc aggregate counts khi cần.
- Không xây một map giữ reference tới mọi class/loader vô thời hạn.

### 14.2. Tránh rủi ro trong vòng đời ứng dụng

- **Startup:** callback của class loader có thể nhạy cảm với việc nạp thêm logging/helper. Giữ code agent nhẹ.
- **Multi-thread:** nhiều threads có thể load/unload classes; snapshot là dữ liệu tại thời điểm gọi, không phải khung cảnh bất biến tuyệt đối.
- **Multi-loader:** trùng tên class không đồng nghĩa trùng `Class<?>`.
- **JPMS:** module access có thể ảnh hưởng helper được chèn vào code sau này.
- **Hidden classes:** có trong `getAllLoadedClasses()`, nhưng chính sách và hỗ trợ sửa có thể khác; đừng ép sửa chỉ vì thấy chúng trong danh sách.
- **Long-running agents:** memory retention của `Class<?>`/ClassLoader và code caches cần kiểm soát.

## 15. Những lỗi thường gặp khi tạo kế hoạch

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Lấy tất cả class từ snapshot rồi retransform ngay | Đụng JDK, array, helper, class không modifiable | Tạo plan, lọc và dry-run trước |
| Không ghi skip reason | Khó phân biệt policy và lỗi JVM | Dùng mã lý do có nghĩa ổn định |
| Ghi `SKIP_NOT_MODIFIABLE` cho mọi thứ ngoài scope | Báo cáo sai nguyên nhân | Phân loại theo policy trước khi kiểm tra kỹ thuật |
| Nhầm `getInitiatedClasses` với defining loader | Chọn sai class khi có parent delegation | Dùng `Class<?>` thật và `getClassLoader()` |
| Dedupe bằng `getName()` | Gộp nhầm class của nhiều loaders | Dedupe theo `Class<?>` identity |
| Cho rằng class `final` không thể retransform | Bỏ qua class có thể modifiable | Dùng `isModifiableClass`, không dựa vào `final` |
| Cho rằng `isModifiableClass=true` bảo đảm thành công | Lỗi verifier/schema khi apply | Verify output và xử lý ngoại lệ |
| Quên manifest capability | `isRetransformClassesSupported=false` | Dùng `Can-Retransform-Classes: true` và kiểm tra JVM |
| Gọi `Class.forName` khi survey | Nạp/khởi tạo lớp mới ngoài ý muốn | Làm việc với snapshot `Class<?>` |
| Dùng same-name để tái tìm target trong transform callback | Reentrant loading hoặc sai class identity | Dùng `className` + `classfileBuffer` |
| Giữ `Class<?>[]` mãi trong agent | Có thể chặn class unload | Lưu metadata và giải phóng references |
| Nhầm plan READY với actual APPLIED | Báo cáo giả thành công | Tách PLAN và APPLY outcomes |
| Dùng sampling nhưng công bố đó là “toàn JVM” | Sai denominator/metrics | Ghi rõ phạm vi và mẫu số |
| Re-run vô hạn batch lỗi | Tăng độ trễ, biến đổi lặp hoặc lặp lỗi | Backoff/circuit breaker, lỗi phân loại |
| Dùng code callback để tải library nặng | Deadlock/reentrancy hoặc startup regression | Chuẩn bị helper, lọc nhanh, giảm phụ thuộc |

## 16. Checklist trước khi triển khai

1. **Mục tiêu rõ ràng:** đo package/method nào; vì sao cần retransform class đã load thay vì chỉ load-time.
2. **Nguồn lớp đúng:** snapshot `getAllLoadedClasses()` hoặc danh sách ứng viên có chủ đích.
3. **Bộ lọc xác định:** allowlist, exclude agent/JDK/bootstrap hoặc package khác, loader/module policy.
4. **Loại class đặc biệt:** primitive/array luôn không modifiable; hidden/proxy theo policy phù hợp.
5. **Capability:** `isRetransformClassesSupported()` và manifest; nếu dùng redefine, kiểm tra capability tương ứng.
6. **Modifiability:** `isModifiableClass(type)` với class ứng viên thực tế.
7. **Mỗi quyết định có lý do:** `READY` hoặc một `SKIP_*` rõ ràng.
8. **Dry-run:** xem danh sách trước khi thực thi.
9. **Plan và execution được tách:** trạng thái apply thành công/thất bại không trộn với lý do skip.
10. **Giữ class identity:** không tái tạo class object bằng tên trong loader khác.
11. **Không làm load/unload ngoài ý muốn:** không giữ toàn bộ snapshot lâu dài hoặc ép class init để khảo sát.
12. **Lỗi apply được xử lý:** không suy luận thành công chỉ vì transformer callback được gọi.
13. **Giới hạn volume:** budget số class, logging, timeouts và concurrency.
14. **QA:** test trên JVM mục tiêu và nhiều loaders/modules nếu ứng dụng thực sự dùng chúng.

## 17. Bài tập tự kiểm tra

**Câu 1.** `getAllLoadedClasses()` trả một mảng chứa nhiều nghìn class, trong đó có `java.lang.String`. Điều đó có nghĩa agent cần instrument `String` không?

**Câu 2.** Trong plan, `java.lang.String` được loại vì package không thuộc allowlist. Nên ghi `SKIP_OUTSIDE_SCOPE` hay `SKIP_NOT_MODIFIABLE`?

**Câu 3.** `int[].class` có thể đi vào array của `retransformClasses` chỉ vì xuất hiện trong snapshot không?

**Câu 4.** Một class được load bởi plugin loader A và một class khác cùng binary name bởi plugin loader B. Có được coi là cùng ứng viên nếu lập plan theo tên không?

**Câu 5.** `isModifiableClass(type)` trả true nhưng `isRetransformClassesSupported()` trả false. Có được đánh dấu `READY` cho retransform không?

**Câu 6.** Một class `final` trong package hợp lệ, JVM nói modifiable. Có nên tự gán `SKIP_FINAL_CLASS` vì nó `final` không?

**Câu 7.** Một plan được sinh hôm qua, hôm nay mới apply trên ứng dụng plugin đã hot reload class loader. Có nên dùng y nguyên reference/tên cũ không?

**Câu 8.** Dry-run của demo trả `READY=2`, `SKIP=4`. Có thể tuyên bố “đã instrument hai class” ngay sau dry-run không?

**Câu 9.** Observer transformer trong mode apply trả `null` và in `transformed=...`. Điều này có chứng minh bytecode đã được sửa không?

**Câu 10.** Một class được `SKIP_HIDDEN_POLICY`. Đây là lý do không modifiable của JVM hay policy của agent?

**Câu 11.** Vì sao không nên giữ `Class<?>[] snapshot` trong static field của agent suốt đời JVM nếu ứng dụng dùng dynamic plugin loaders?

**Câu 12.** Một vòng quét dùng `continue` ngay khi class không nằm trong package mục tiêu. Nếu dashboard tuyên bố đã ghi skip reason cho **mọi class đã khảo sát**, báo cáo đó đúng hay sai?

**Câu 13.** Trong `ClassFileTransformer.transform(...)` của một class mới, `classBeingRedefined` thường bằng null. Có nên gọi `Class.forName(className)` để áp dụng lại classifier trên `Class<?>` không?

**Câu 14.** `getInitiatedClasses(loader)` có nhất thiết chỉ chứa những class được **chính loader đó define** không?

### Đáp án

1. **Không.** Đang load chỉ là fact discovery; cần policy và điều kiện kỹ thuật riêng.
2. **SKIP_OUTSIDE_SCOPE** theo chính sách đã nêu; không quy kết khả năng sửa khi chưa kiểm tra.
3. **Không.** Array classes không modifiable theo API.
4. **Không.** Runtime identity khác nhau; dùng `Class<?>` cùng defining loader/module context.
5. **Không.** Capability và modifiability là hai điều kiện độc lập, cả hai cần thỏa.
6. **Không.** `final` không phải tiêu chí unmodifiable; dùng kết quả API/policy thực tế.
7. **Không.** Cần khảo sát lại và bảo đảm đúng class identity, loader, capability.
8. **Không.** Mới có kế hoạch, không có lời gọi retransform.
9. **Không.** Observer chỉ nhận callback rồi trả `null`; chưa đổi class bytes.
10. Là **policy** trong ví dụ; không suy luận hidden class bị cấm ở mọi JVM/mọi kiểu thao tác.
11. Tham chiếu mạnh tới Class object có thể kéo theo ClassLoader, ngăn unloading.
12. **Sai** nếu không nói rõ prefilter. Những class bị `continue` chưa có record skip chi tiết.
13. **Không.** Callback đang xử lý class có thể chưa hoàn tất định nghĩa; dùng `className` và `classfileBuffer`.
14. **Không.** Initiating loader có thể khác defining loader vì cơ chế delegation.

## 18. Kết luận

Muốn instrument lớp đã load một cách có kiểm soát, cần **khảo sát bằng `getAllLoadedClasses()`, lọc theo phạm vi, kiểm tra capability/modifiability và ghi lại lý do bỏ qua**. Danh sách `READY` là kế hoạch đủ điều kiện sơ bộ, không phải bằng chứng lớp đã được thay bytecode. Dry-run giúp đánh giá tác động trước khi thực hiện retransform, trong khi kết quả apply phải được theo dõi riêng.

**Một kế hoạch tốt có thể giải thích được cả “vì sao chọn lớp này” lẫn “vì sao không chọn lớp kia”**, giữ đúng class loader identity, tránh các lớp đặc biệt, giảm nguy cơ can thiệp vào JVM và cho phép audit đáng tin cậy.

## 19. Tài liệu tham khảo chính thức

- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `getAllLoadedClasses`, `getInitiatedClasses`, `isModifiableClass`, `isRetransformClassesSupported`, `retransformClasses` và quy tắc atomicity của thao tác.
- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): filter trong callback, thứ tự transformer, nghĩa của `className`, `return null` và trách nhiệm không sửa mảng input.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getName`, `getTypeName`, `getClassLoader`, `isPrimitive`, `isArray`, `isHidden`.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining/initiating loader, delegation và class-loading locks.
- [Java SE 21 — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): `premain`, `agentmain`, manifest `Can-Retransform-Classes` và cơ chế Java agent.
