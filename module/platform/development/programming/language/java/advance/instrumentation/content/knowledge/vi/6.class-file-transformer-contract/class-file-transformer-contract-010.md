# Loại trừ lớp của agent, helper và công cụ ghi log để tránh tự chèn mã

## 1. Vì sao transformer cần loại trừ chính hệ thống instrumentation?

Khi Java agent đăng ký `ClassFileTransformer`, JVM có thể gọi `transform(...)` vào thời điểm định nghĩa một class mới, khi redefine, và với transformer có capability tương ứng thì cả khi retransform. Callback nằm trên đường **nạp hoặc biến đổi class** của ứng dụng: code chạy trong callback phải đủ nhẹ, có thể chạy nhiều lần và đặc biệt phải tránh tự kích hoạt chuỗi nạp class phụ thuộc mà nó lại cố instrument.

Nếu agent biến đổi luôn các class của **agent**, **helper**, **logger**, **metrics exporter** hoặc thư viện bytecode mà chính nó dùng, điểm đo có thể làm thay đổi bộ máy tạo điểm đo. Một vòng lặp có thể xuất hiện:

~~~text
JVM đang nạp example/app/InventoryService
    -> gọi SafeTransformer.transform(...)
        -> transformer gọi Logger.debug(...)
            -> logger chưa được nạp, JVM nạp logger
                -> gọi SafeTransformer.transform(logger)
                    -> transformer lại gọi Logger.debug(...)
                        -> lặp, lỗi linkage, treo hoặc tràn stack
~~~

Không phải hệ thống nào cũng tái hiện vòng lặp y hệt sơ đồ. JVM có một số cơ chế bảo vệ class phụ thuộc trực tiếp vào transformer, nhưng **không nên dựa vào đó để suy rằng mọi helper/logger tự động được an toàn**. Callback có thể gọi code chưa khởi tạo, kích hoạt class loading/reentrancy hoặc tranh chấp khóa. Hậu quả có thể là `StackOverflowError`, `ClassCircularityError`, `NoClassDefFoundError`, `LinkageError`, deadlock hoặc overhead cực lớn; loại lỗi thực tế phụ thuộc JVM và chuỗi phụ thuộc.

**Nguyên tắc:** xác định lớp thuộc phạm vi instrument bằng một **bộ lọc cực sớm**, trước khi tạo parser ASM, khởi tạo Byte Buddy, gọi reflection, truy cập logger hay tạo span. Nếu lớp không thuộc phạm vi, trả về `null` ngay. Lớp dùng để **thực hiện instrumentation** phải nằm ngoài phạm vi mà instrumentation áp dụng.

Bài học chỉ tập trung vào **hợp đồng lọc trong transformer**: chọn/loại trừ class và tránh tự instrument. Việc viết bytecode cụ thể có thể thực hiện bằng ASM, Byte Buddy hoặc công cụ khác sau khi vượt qua bước lọc.

## 2. Đầu vào của `ClassFileTransformer.transform` và điểm lọc đúng

Java 17 có overload nhận `Module`:

~~~java
byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

Đây là **chữ ký minh họa**, không phải một chương trình độc lập. Với phiên bản overload năm tham số (không có `Module`), Java 17 mặc định chuyển từ overload sáu tham số sang phương thức cũ nếu bạn override nó. Vì vậy ví dụ chạy độc lập ở phần sau dùng overload năm tham số cho gọn.

| Tham số | Ý nghĩa để ra quyết định |
| --- | --- |
| `module` | Module của class đang biến đổi; hữu ích khi cần giới hạn theo module ở overload Java 9+ |
| `loader` | Class loader **định nghĩa** class; có thể `null` cho bootstrap class loader |
| `className` | Tên nội bộ theo JVM, ví dụ `java/lang/String`, `example/agent/SafeAgent$SafeTransformer`; có thể `null` trong một số trường hợp |
| `classBeingRedefined` | `null` khi load lần đầu; là đối tượng `Class<?>` trong redefine/retransform |
| `protectionDomain` | Miền bảo vệ của class, có thể giúp nhận diện nguồn khi chính sách yêu cầu |
| `classfileBuffer` | Bytecode đầu vào; **không được sửa trực tiếp mảng này** |

**Đặc biệt:** `className` dùng dấu gạch chéo `/` thay vì dấu chấm `.` như tên Java source. Bộ lọc `"example.agent."` sẽ không khớp với `"example/agent/SafeAgent"`. Nested class cũng dùng ký hiệu `$` như `SafeAgent$SafeTransformer` nên một prefix package `"example/agent/"` sẽ loại trừ cả nested class.

Transformer tuân theo hợp đồng:

- **Trả về `null`:** transformer hiện tại **không thay đổi** bytecode của class này. Điều đó **không ngăn** JVM nạp class và **không cấm** các transformer khác tác động lên nó.
- **Trả về `byte[]` mới:** đây là nội dung class file đã biến đổi; phải hợp lệ và tuân thủ ràng buộc redefine/retransform. Không sửa `classfileBuffer` đầu vào tại chỗ.
- **Có exception:** JVM vẫn tiếp tục thử những transformer khác theo hợp đồng. Không trông đợi exception trong transformer sẽ giúp “hủy an toàn” việc load class; thiết kế filter và code weaving phải chủ động kiểm soát lỗi.

Đối với mục tiêu bảo vệ agent, kiểm tra `className`/`loader` phải diễn ra **trước** mọi phân tích bytecode hay ghi log chi tiết. Chỉ một lệnh `Class.forName(...)` hoặc lời gọi tiện ích chưa được warm-up cũng có thể kéo theo nạp lớp trong chính callback.

Tham khảo: [ClassFileTransformer — Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).

## 3. Thiết kế chính sách loại trừ nhiều lớp

Một bộ lọc thực dụng có hai tầng:

1. **Denylist/bỏ qua bắt buộc:** class của agent, helper, logger/metrics, hệ thống JDK và thành phần nhạy cảm của cơ chế nạp lớp. Mục tiêu là không đụng vào chính đường thực thi instrumentation.
2. **Allowlist/giới hạn phạm vi:** chỉ instrument các package/class nghiệp vụ mà bài toán thực sự yêu cầu. Ví dụ chỉ `example/app/`, không mở rộng sang toàn bộ class của bên thứ ba.

Ví dụ các nhóm cần cân nhắc:

| Nhóm | Prefix nội bộ minh họa | Vì sao bỏ qua? |
| --- | --- | --- |
| Agent và transformer | `example/agent/` | Tránh điểm đo tự áp dụng vào mã cài điểm đo |
| Helper riêng | `example/helper/` | Helper thường được gọi bên trong `transform`, recorder hoặc advice |
| Logging/telemetry riêng | `example/logging/`, `example/telemetry/` | Tránh log/span tự sinh tiếp log/span hoặc trigger class loading |
| Logging framework | `org/slf4j/`, `ch/qos/logback/`, `org/apache/logging/log4j/` | Các lớp logging có thể nằm trên đường xử lý của chính agent |
| Lớp nền của JDK | `java/`, `javax/`, `jdk/`, `sun/`, `com/sun/` | Bộ lọc an toàn mặc định cho bài học, giảm nguy cơ can thiệp class hạ tầng |
| Mã nghiệp vụ cần đo | `example/app/` | Chỉ các lớp có tên thuộc phạm vi này được xét tiếp |

Đây là **chính sách minh họa**, không phải danh sách đầy đủ cho mọi dự án. Nếu agent dùng ASM, Byte Buddy, Micrometer hoặc exporter riêng, cần loại trừ **đúng package thực tế**, kể cả phiên bản đã được **relocate/shade** vào namespace khác. Một agent bên trong `company/observability/` cần bảo vệ toàn bộ namespace đó, thay vì chỉ loại `example/agent/`. Đừng thêm những prefix vô căn cứ khiến bỏ sót lớp nghiệp vụ quan trọng.

**Phải kiểm tra ranh giới package.** Dùng `"example/agent/"`, không dùng `"example/agent"`: tiền tố thiếu dấu `/` có thể vô tình loại `example/agentTools/Service`. Cũng không chỉ so sánh bằng `equals("example/agent/SafeAgent")` vì sẽ bỏ lọt nested class và helper khác.

**Chỉ lọc bằng tên cũng chưa đủ ở hệ thống plugin:** hai class loader có thể định nghĩa hai class cùng tên. Với môi trường đa tenant, OSGi, application server hoặc plugin loader, nên xác định class loader/module/`ProtectionDomain` đúng phạm vi; trong callback tránh thao tác phức tạp để suy đoán danh tính loader.

### 3.1. Vấn đề bootstrap class loader

`loader == null` thường nghĩa class được định nghĩa bởi **bootstrap class loader**. Mẫu an toàn của bài này loại trừ chúng, kể cả khi tên có vẻ phù hợp. Đây là **lựa chọn chính sách**, không phải quy tắc của API. Agent chuyên instrument thư viện JDK có thể cần xử lý bootstrap một cách có chủ đích, với mô hình class loader, module, trợ giúp bootstrap và kiểm tra tương thích rất chặt. Không nới lỏng bộ lọc chỉ vì một probe chưa xuất hiện.

### 3.2. `className == null`

Callback không nên giả định mọi tình huống đều có tên. Điều kiện `className == null` phải được xử lý ngay trước khi gọi `startsWith` để tránh `NullPointerException`. Với trường hợp không biết tên, chính sách “không instrument” là mặc định an toàn của ví dụ.

## 4. Ví dụ Java 17+ chạy được: bộ lọc an toàn và agent quan sát

Ta xây dựng một agent thật sự đăng ký `ClassFileTransformer` nhưng **cố tình không sửa bytecode**. Nó xác nhận callback thấy class nghiệp vụ, trong khi các class nằm trong denylist không được xử lý tiếp. Điều này giúp thử chính xác ranh giới lọc trước khi gắn thư viện bytecode vào agent.

Cấu trúc ví dụ:

~~~text
demo/
├── MANIFEST.MF
├── example/
│   ├── agent/
│   │   ├── ClassNamePolicy.java
│   │   └── SafeAgent.java
│   └── app/
│       ├── InventoryService.java
│       └── DemoMain.java
└── out/                         (thư mục .class do javac tạo)
~~~

### 4.1. Chính sách lọc, khởi tạo trước khi đăng ký transformer

**Tệp: `example/agent/ClassNamePolicy.java`**

~~~java
package example.agent;

public final class ClassNamePolicy {
    private static final String[] EXCLUDED_PREFIXES = {
        "example/agent/",
        "example/helper/",
        "example/logging/",
        "example/telemetry/",
        "org/slf4j/",
        "ch/qos/logback/",
        "org/apache/logging/log4j/",
        "java/",
        "javax/",
        "jdk/",
        "sun/",
        "com/sun/"
    };

    private ClassNamePolicy() {}

    public static void prepare() {
        // Nạp/khởi tạo chính sách trước khi đăng ký transformer.
        shouldInspect(
                ClassNamePolicy.class.getClassLoader(),
                "example/agent/ClassNamePolicy");
    }

    public static boolean shouldInspect(
            ClassLoader loader, String internalName) {
        if (loader == null || internalName == null) {
            return false;
        }

        for (String prefix : EXCLUDED_PREFIXES) {
            if (internalName.startsWith(prefix)) {
                return false;
            }
        }

        // Chỉ quan sát namespace ứng dụng được cho phép.
        return internalName.startsWith("example/app/");
    }
}
~~~

`prepare()` chủ động khởi tạo `ClassNamePolicy` và mảng các prefix **trước khi** JVM bắt đầu gọi transformer đã đăng ký. Nếu không chuẩn bị và callback đầu tiên làm JVM nạp một helper chưa sẵn sàng, agent có thể tự tạo chuỗi class loading không mong muốn. Bộ lọc chỉ thao tác trên `String`/mảng đã khởi tạo; nó không dùng logger, reflection hoặc classpath scan.

### 4.2. Java agent đặt bộ lọc ở đầu callback

**Tệp: `example/agent/SafeAgent.java`**

~~~java
package example.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class SafeAgent {
    private static volatile boolean serviceObserved;

    private SafeAgent() {}

    public static void premain(
            String options, Instrumentation instrumentation) {
        ClassNamePolicy.prepare();
        ClassFileTransformer transformer = new SafeTransformer();

        instrumentation.addTransformer(transformer, false);
        System.out.println("agent-installed");
    }

    public static boolean wasServiceObserved() {
        return serviceObserved;
    }

    private static final class SafeTransformer
            implements ClassFileTransformer {

        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {

            // Lọc ngay lập tức; không gọi logger hoặc bytecode parser.
            if (!ClassNamePolicy.shouldInspect(loader, className)) {
                return null;
            }

            // Chỉ lưu một dấu hiệu để chứng minh class đi qua callback.
            if ("example/app/InventoryService".equals(className)) {
                serviceObserved = true;
            }

            // Demo không chèn bytecode; null = giữ nguyên class.
            return null;
        }
    }
}
~~~

`new SafeTransformer()` và `ClassNamePolicy.prepare()` chạy **trước** `addTransformer(...)`, giúp chuẩn bị những lớp cốt lõi mà transformer phụ thuộc vào. Lúc JVM nạp `example/app/InventoryService`, tên của class vượt qua filter và biến `serviceObserved` được đặt thành true. Mọi class khác bị bỏ qua hoặc không có thay đổi; **không có phép instrument bytecode thật**. Dòng `System.out.println(...)` chỉ chạy một lần từ `premain`, **không nằm trong `transform`**.

Tham số thứ hai `false` của `addTransformer(transformer, false)` nghĩa transformer được đăng ký **không hỗ trợ retransformation**. Nó vẫn nhận callback cho các class được định nghĩa mới sau khi đăng ký. Nếu mục tiêu là retransform class đã load, cần capability riêng và cách đăng ký khác; không liên quan đến quy tắc loại trừ cơ bản.

### 4.3. Mã ứng dụng

**Tệp: `example/app/InventoryService.java`**

~~~java
package example.app;

public final class InventoryService {
    public int available() {
        return 42;
    }
}
~~~

**Tệp: `example/app/DemoMain.java`**

~~~java
package example.app;

import example.agent.ClassNamePolicy;
import example.agent.SafeAgent;

public final class DemoMain {
    public static void main(String[] args) {
        ClassLoader loader = DemoMain.class.getClassLoader();

        System.out.println("agentExcluded="
                + !ClassNamePolicy.shouldInspect(
                        loader, "example/agent/SafeAgent"));
        System.out.println("helperExcluded="
                + !ClassNamePolicy.shouldInspect(
                        loader, "example/helper/Helper"));
        System.out.println("loggerExcluded="
                + !ClassNamePolicy.shouldInspect(
                        loader, "example/logging/LogSink"));
        System.out.println("jdkExcluded="
                + !ClassNamePolicy.shouldInspect(
                        loader, "java/lang/String"));
        System.out.println("bootstrapExcluded="
                + !ClassNamePolicy.shouldInspect(
                        null, "example/app/InventoryService"));
        System.out.println("nullNameExcluded="
                + !ClassNamePolicy.shouldInspect(loader, null));
        System.out.println("appIncluded="
                + ClassNamePolicy.shouldInspect(
                        loader, "example/app/InventoryService"));

        System.out.println("service="
                + new InventoryService().available());
        System.out.println("serviceObserved="
                + SafeAgent.wasServiceObserved());
    }
}
~~~

Chương trình demo cố ý tham chiếu `ClassNamePolicy` và `SafeAgent` trong `DemoMain` để có thể kiểm chứng nội bộ. **Ứng dụng production không nên phụ thuộc trực tiếp vào agent để đọc trạng thái như vậy**: collector/metrics có thể xuất kết quả qua kênh quan sát riêng. Các tên `example/helper/Helper` và `example/logging/LogSink` ở đây là **chuỗi tên mô phỏng để kiểm thử chính sách**, không phải class cần viết thêm.

### 4.4. Manifest của agent

**Tệp: `MANIFEST.MF`**

~~~text
Manifest-Version: 1.0
Premain-Class: example.agent.SafeAgent

~~~

Trong file manifest thực tế, cần một dòng trống kết thúc phần main attributes. Ví dụ chỉ cần `Premain-Class` vì dùng `-javaagent` lúc khởi động. Không cần `Agent-Class`/`agentmain` hay capability retransformation cho bài tập này.

### 4.5. Biên dịch, đóng gói và chạy

Từ thư mục `demo/` chứa source và manifest:

~~~bash
javac --release 17 -d out example/agent/ClassNamePolicy.java example/agent/SafeAgent.java example/app/InventoryService.java example/app/DemoMain.java
jar --create --file safe-agent.jar --manifest MANIFEST.MF -C out example/agent
java -javaagent:safe-agent.jar -cp out example.app.DemoMain
~~~

Các lệnh trên chạy được với JDK 17+ trên Windows PowerShell hoặc shell Unix khi `javac`, `jar`, `java` nằm trong `PATH`. Tạo thư mục `out` bằng `mkdir out` trước khi biên dịch nếu cần; `javac -d out` cần thư mục output tồn tại.

**Stdout kỳ vọng của chương trình có agent trên HotSpot/JDK thông thường:**

~~~text
agent-installed
agentExcluded=true
helperExcluded=true
loggerExcluded=true
jdkExcluded=true
bootstrapExcluded=true
nullNameExcluded=true
appIncluded=true
service=42
serviceObserved=true
~~~

Dòng cuối xác nhận `InventoryService` được JVM đưa qua callback, nhưng không có bytecode nào bị sửa. Giá trị `agentExcluded=true` kiểm tra policy bằng tên; đối với mã thật, policy trả `false` ngay nếu JVM gọi transformer cho `example/agent/SafeAgent` hoặc các helper cùng package.

**Chạy lại không dùng agent:**

~~~bash
java -cp out example.app.DemoMain
~~~

Khi không có `-javaagent`, `premain` không chạy và không có transformer được đăng ký, nên stdout giống ở trên ngoại trừ **không có dòng `agent-installed`** và dòng cuối là **`serviceObserved=false`**. Các kết quả kiểm tra policy vẫn giống nhau vì chúng là hàm thuần trên tên và class loader.

## 5. Tại sao ví dụ tránh được tự chèn mã?

**Thứ nhất, tách namespace.** Toàn bộ công cụ agent và chính sách filter ở `example/agent/`, trong khi mã ứng dụng ở `example/app/`. Prefix rõ ràng cho phép bỏ qua agent và nested class như `example/agent/SafeAgent$SafeTransformer`. Nếu công cụ parser/recorder nằm ở `example/helper/` hoặc `example/telemetry/`, chúng cũng thuộc denylist.

**Thứ hai, chuẩn bị phụ thuộc trước.** `ClassNamePolicy.prepare()` và việc tạo `SafeTransformer` xảy ra trước `addTransformer`. Trong agent có weaving bằng ASM/Byte Buddy, cần chuẩn bị các class tối thiểu mà filter/weaver phụ thuộc vào theo thiết kế riêng, đồng thời không tải hàng loạt thư viện vào lúc callback bắt đầu. Khởi tạo sớm không đủ nếu helper bên trong lại có phụ thuộc trễ mới, vì thế việc loại trừ namespace vẫn bắt buộc.

**Thứ ba, lọc dựa trên dữ liệu callback.** `shouldInspect(loader, className)` không gọi `Class.forName(className)`, không làm classpath scan và không truy cập `ClassLoader.loadClass`. Trong callback ban đầu, `classBeingRedefined` thường là null; để xác định lớp sắp định nghĩa, dùng tên/loader/metadata có sẵn là đủ.

**Thứ tư, không log trong `transform`.** Agent có thể log **một lần** sau khi đăng ký ở `premain`, nhưng callback không gọi logging framework, network exporter hoặc recorder có thể làm nạp class. Nếu cần theo dõi tổng số lần lọc, hãy thiết kế counter nhẹ đã khởi tạo và đọc/xuất ở kênh ngoài callback; tránh tạo metric label khác nhau cho mọi tên class.

**Thứ năm, không sửa bytecode khi chưa cần.** `return null` giữ nguyên input để JVM tiếp tục nạp class. Khi cần weaving thật, chỉ tạo `byte[]` mới **sau** filter và trả bytes hợp lệ. Không bao giờ sửa tại chỗ `classfileBuffer` được JVM giao cho transformer.

### 5.1. Chèn mã thực ở vị trí nào?

Trong một agent đã tích hợp thư viện biến đổi bytecode, cấu trúc logic nên là:

~~~text
transform(loader, className, ..., bytes)
    if loader hoặc className không hợp lệ: return null
    if agent/helper/logger/JDK:             return null
    if ngoài package nghiệp vụ:             return null
    kiểm tra điều kiện instrument cụ thể
    gọi bytecode weaver đã được chuẩn bị từ trước
    nếu không thay đổi:                     return null
    trả về byte[] MỚI hợp lệ
~~~

Đây là **mô hình luồng xử lý**, không phải lệnh Java chạy độc lập. Mẫu thực nghiệm ở mục 4 chủ ý dừng trước bước weaver để minh họa ranh giới một cách có thể chạy và kiểm tra.

Nếu dùng **Byte Buddy**, hãy cấu hình `ignore(...)` hoặc matcher loại trừ tương đương **trước** các rule `type(...)` mà agent gắn advice, bảo đảm cả helper/advice/plugin/logger đã được exclude. Nếu dùng **ASM trực tiếp** trong `ClassFileTransformer`, gọi bộ lọc tên/loader trước khi dựng `ClassReader` hoặc `ClassWriter`. Các API và matcher cụ thể phụ thuộc phiên bản thư viện; nguyên tắc lớp loại trừ vẫn giống nhau.

## 6. Các bẫy thường gặp khi mở rộng sang production

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đặt `log.debug(...)` ngay đầu `transform` | Logger còn chưa nạp có thể tạo vòng class-loading hoặc callback reentrant | Lọc trước, bỏ log khỏi đường callback quan trọng; phát thông tin ngoài callback |
| Chỉ exclude class `SafeAgent` | Nested transformer, helper và thư viện khác vẫn bị đụng | Exclude toàn bộ package có dấu `/` kết thúc và các namespace phụ thuộc |
| Dùng `example.agent.` để so `className` | Không khớp với tên kiểu JVM `example/agent/SafeAgent` | Dùng internal name, dấu `/` |
| Quên xử lý `className == null` | `NullPointerException` trong lúc nạp class | Bỏ qua sớm bằng `return null` |
| Chỉ exclude `java/` rồi instrument mọi thứ còn lại | Dễ đụng logger, instrumentation library hoặc classloader của framework | Denylist hệ thống + allowlist nghiệp vụ |
| Prefix quá rộng như `example/` | Bỏ sót tất cả class ứng dụng cần instrument | Giới hạn namespace exclusions cụ thể |
| Prefix thiếu ranh giới như `example/log` | Có thể loại nhầm `example/login/...` | Dùng `example/logging/` |
| Nghĩ `loader == null` là tên không hợp lệ | Nhầm dấu hiệu bootstrap loader | Bỏ qua bootstrap là lựa chọn an toàn của ví dụ, không phải yêu cầu API |
| Dùng `Class.forName` để suy class theo tên trong callback | Tự gây nạp thêm class và tái nhập transformer | Dựa vào `className`, `loader`, `module` sẵn có |
| Trả `classfileBuffer` sau khi sửa nội dung tại chỗ | Vi phạm hợp đồng không sửa input | Trả `null` nếu không đổi; khi đổi, tạo mảng bytes mới |
| Coi `return null` là chặn mọi agent | Transformer khác vẫn có thể xử lý class | Chính sách chỉ bảo vệ transformer đang xét; cần kiểm tra agent khác |
| Tưởng `removeTransformer` tức thời dừng mọi callback | Callback đang chạy vẫn có thể xảy ra khi remove | Xử lý concurrency, cleanup và vòng đời an toàn |
| Instrument cả collector/tracer | Có thể tự sinh span/metric/log vô hạn hoặc overhead cao | Exclude logger, tracer SDK và exporter theo package thực tế |

### 6.1. Có nên chỉ lọc theo class loader?

Không. Một class loader thường chứa cả class ứng dụng lẫn thư viện agent hoặc framework. `loader != null` chỉ là bước đầu để bỏ qua bootstrap; **không có nghĩa tất cả class còn lại đều an toàn**. Kết hợp filter theo **tên package** với class loader/module được phép. Nếu cùng tên class tồn tại ở nhiều loader, phải áp dụng policy đúng cho **mỗi cặp (loader, name)**.

Một agent được nạp vào class loader của hệ thống có thể đi cùng class ứng dụng. Vì vậy việc kiểm tra `loader == SafeAgent.class.getClassLoader()` cũng có thể loại nhầm **toàn bộ ứng dụng** nếu dùng như denylist. Chọn lọc theo loader phải dựa trên kiến trúc thực tế, không áp dụng tùy tiện.

### 6.2. Khi retransform/redefine class đã nạp

Bộ lọc package vẫn cần áp dụng khi retransform/redefine. Tuy nhiên:

- `classBeingRedefined` có thể không null, giúp xác định đúng `Class<?>` đang được sửa.
- Khả năng `Instrumentation.isRetransformClassesSupported()` và `isModifiableClass(type)` phải được kiểm tra riêng nếu chủ động gọi `retransformClasses`.
- Transformer đăng ký `canRetransform=false` **không được gọi lại** trong một đợt retransform; JVM có thể tái dùng kết quả transform trước đó theo hợp đồng.
- Rule mới được thêm vào hệ thống instrument không tự động loại bỏ bytecode của class đã biến đổi trước đó. Cần kế hoạch deployment, retransform/redefine và tính tương thích khi thay đổi phạm vi instrument.

Trong ví dụ ở mục 4, `addTransformer(..., false)` cố tình chỉ theo dõi **class definitions mới**. Không nên suy ra agent đã quan sát tất cả class từng được tải trước khi nó đăng ký.

### 6.3. Nếu filter/weaver ném exception thì sao?

Theo hợp đồng `ClassFileTransformer`, việc transformer ném exception không nhất thiết làm JVM hủy toàn bộ class loading; các transformer khác vẫn có thể được gọi. Đừng dùng exception làm cơ chế “skip class”. Với tên/loader ngoài phạm vi, **trả `null` trước mọi thao tác có rủi ro**.

Nếu có lỗi xử lý bytecode sau khi qua filter, nên ghi nhận qua kênh chẩn đoán đã được chuẩn bị an toàn, giới hạn số log và không để recorder phụ gây thêm lỗi. Có thể cần `catch` ở biên transformation để giữ lỗi có thể phân tích; nhưng không tự ý nuốt lỗi nghiêm trọng rồi báo “instrumentation đã thành công”. Trường hợp bytecode đầu vào không hợp lệ có `IllegalClassFormatException` theo API. Việc quyết định dừng ứng dụng hay tiếp tục phải được thực hiện bằng chính sách triển khai rõ ràng, không trông chờ một exception trong callback.

## 7. Checklist triển khai và kiểm thử phạm vi lọc

Trước khi phát hành agent thực tế, kiểm tra theo ba lớp:

**A. Kiểm thử bộ lọc thuần:**

- `example/agent/SafeAgent`, nested `example/agent/SafeAgent$SafeTransformer` → **exclude**.
- `example/helper/SomeHelper`, `example/logging/LogSink`, `org/slf4j/Logger` → **exclude**.
- `java/lang/String`, `jdk/internal/...`, loader null, name null → **exclude** trong chính sách này.
- `example/app/InventoryService` với loader ứng dụng → **include**.
- `example/app2/Other` → **exclude**, vì allowlist chỉ cấp quyền cho `example/app/`.
- Xác minh prefix có ranh giới; các package mới/shaded được khai báo lại.

**B. Kiểm thử agent trong JVM tách biệt:**

Chạy một lần **không agent** và một lần với `-javaagent`. Quan sát thứ tự `premain` chạy trước `main`, callback thấy class thuộc allowlist được định nghĩa sau đăng ký, và output nghiệp vụ không đổi. Đối với agent có weaver thật, kiểm tra class agent/helper/logger không bị thay đổi bytecode, đồng thời kiểm tra lớp nghiệp vụ đã được biến đổi chính xác.

**C. Kiểm thử áp lực và failure:**

Chạy nhiều thread, lazy initialization của thư viện logging, classloader/plugin mới, startup chậm, tiến trình tắt; đo overhead, số class được xem xét và số bytecode thực sự biến đổi. Thử cả khi transformer trả `null`, khi weaver gặp class file không được hỗ trợ và khi agent phải cleanup. Có giới hạn log/telemetry để không biến công cụ quan sát thành nguồn sự cố.

### 7.1. Kịch bản phát hiện lỗi “agent tự chèn mã”

Giả sử sau khi bật agent, startup trở nên chậm rồi xuất hiện `ClassCircularityError` gần các lớp logger. Kiểm tra theo thứ tự:

1. Xem bộ lọc có chạy **trước** logger/Byte Buddy/ASM hay không.
2. Liệt kê toàn bộ package agent, helper, advice, shaded dependencies và logging/telemetry exporter mà callback sử dụng.
3. Kiểm tra `className` sử dụng internal name và có xử lý `null` không.
4. Xác minh rule deny/allow không bị matcher sau đó ghi đè khi framework xây dựng pipeline.
5. Thử agent tối giản chỉ `return null` như ví dụ để tách lỗi do callback/filter khỏi lỗi do weaving.
6. Bật lại từng phần instrument với phạm vi hẹp, thu bằng chứng về class được chọn và biến động tài nguyên **ngoài đường callback**.

Đây là quy trình phân tích, không phải khẳng định mọi `ClassCircularityError` đều do logger. Cần xem stack trace, cấu trúc class loader và thời điểm lỗi thực tế.

## 8. Câu hỏi tự kiểm tra

1. Nếu callback gọi `Logger.debug(...)` trước khi kiểm tra `className`, logger chưa được load có thể dẫn đến tình huống gì?
2. Tại sao `example/agent/` bảo vệ cả `SafeAgent` và `SafeAgent$SafeTransformer`?
3. `className` có định dạng `example.app.InventoryService` hay `example/app/InventoryService`?
4. Vì sao `return null` là cách bỏ qua an toàn đối với class không thuộc phạm vi, nhưng **không** cấm agent khác?
5. Tại sao dùng chỉ `loader != null` hoặc chỉ `loader == agentLoader` có thể sai?
6. Vì sao phải chuẩn bị filter/helper trước `addTransformer` mà vẫn cần denylist?
7. Mẫu ở mục 4 có sửa bytecode `InventoryService` không? Dòng stdout nào chứng minh callback đã được gọi?
8. Nếu dùng ASM/Byte Buddy, bước filter cần nằm trước hay sau lúc khởi tạo parser/weaving?

**Kết luận:** Trong Java instrumentation, **bộ lọc tên class và class loader phải là bước đầu tiên của transformer**. Loại trừ agent, helper, logger, telemetry và thư viện phụ thuộc; đồng thời allowlist đúng mã nghiệp vụ cần quan sát. Khởi tạo dependency trước đăng ký transformer, không ghi log hoặc chủ động nạp class trong callback, và dùng `return null` khi không có biến đổi. Những biện pháp này giảm rủi ro tự instrument, reentrancy và recursion khi JVM đang nạp lớp.

### Tài liệu tham khảo

- [Java 17 — ClassFileTransformer, hợp đồng transform và return null](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [Java 17 — Instrumentation, addTransformer và removeTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [Java 17 — java.lang.instrument agent specification](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html)
