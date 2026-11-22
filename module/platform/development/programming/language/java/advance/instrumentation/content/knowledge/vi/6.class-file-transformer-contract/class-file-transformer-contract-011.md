# Quản lý dữ liệu chẩn đoán mà không làm callback phụ thuộc vào lớp đang được nạp

Khi xây dựng Java instrumentation agent, phương thức `ClassFileTransformer.transform(...)` chạy đúng lúc JVM đang xử lý việc **định nghĩa, định nghĩa lại hoặc biến đổi lại một lớp**. Đây là vị trí có độ nhạy cao: chỉ một lệnh ghi log, tạo serializer, gọi reflection hoặc tham chiếu nhầm tới lớp ứng dụng cũng có thể kéo theo việc nạp lớp khác trước khi lớp hiện tại hoàn tất quá trình định nghĩa. Hậu quả có thể là vòng gọi transformer, lỗi liên kết lớp, khóa chéo khi class loading, độ trễ khởi động tăng mạnh hoặc mất tín hiệu chẩn đoán ngay lúc cần nhất.

Mục tiêu của bài là thiết kế **đường ghi nhận dữ liệu chẩn đoán an toàn trong transformer callback**, tránh biến việc quan sát thành một phụ thuộc vào **chính lớp đang được nạp**, tách thu thập ra khỏi phân tích/xuất dữ liệu, và biết giới hạn của từng kiểu bộ đệm. Ví dụ Java 17+ bên dưới là một startup agent chạy được, chỉ đếm callback và giữ một mẫu tên lớp trong bộ nhớ có giới hạn; nó không thay đổi bytecode.

Bạn sẽ giải thích được: tại sao `Class.forName`, logger, formatter, service discovery, class loader và serializer là rủi ro ở trong callback; dữ liệu nào có sẵn trong tham số `transform`; cách đặt bộ đếm và buffer an toàn; vì sao ghi log ngoài callback vẫn phải để ý backpressure, vòng lặp và thời điểm agent được khởi tạo.

## 1. Bối cảnh: transformer chạy trong quá trình nạp lớp

Agent đăng ký callback qua `Instrumentation.addTransformer(...)`. Với một lớp mới, JVM gọi transformer trước khi bytes của lớp được dùng để định nghĩa hoàn chỉnh; nếu có nhiều transformer, kết quả của transformer trước có thể được truyền cho transformer tiếp theo.

~~~text
JVM chuẩn bị định nghĩa lớp demo/app/Target
       |
       v
đọc class bytes -> transformer A -> transformer B -> verify/link/define
                       |
                       +-- [NGUY HIỂM] muốn ghi log
                              -> logger backend cần load một lớp
                              -> class loader / transformer lại hoạt động
                              -> có thể kéo theo reentrancy / khóa / lỗi
                       |
                       +-- [AN TOÀN HƠN] kiểm tra tên, tăng counter,
                              ghi nhận metadata rất nhỏ vào bộ đệm hữu hạn,
                              trả null hoặc byte[] hợp lệ ngay
       |
       v
phần khác của agent đọc dữ liệu sau, ghi log/export ngoài callback
~~~

"Transformer chạy trong lúc lớp được load" **không có nghĩa** mọi lời gọi `transform` chỉ đến từ load mới: nó còn có thể đến từ `redefineClasses` và, với transformer được đăng ký có khả năng retransformation, từ `retransformClasses`. Vì vậy, dữ liệu ghi nhận phải nói rõ mình đếm **lần callback**, **định nghĩa lớp**, hay **lần retransform**. Không suy ra một callback = một lớp mới đã khởi tạo thành công.

Đường nóng có các ràng buộc đặc biệt:

- Callback có thể được gọi rất nhiều lần, trong lúc ứng dụng khởi động hoặc tự động load lớp theo yêu cầu.
- Nhiều luồng có thể đồng thời đi qua callback cho những lớp khác nhau; không giả định callback toàn cục chỉ chạy trên một luồng.
- JVM có thể đang giữ hoặc phải tương tác với các khóa liên quan class loading. Bổ sung lock từ logger/cache trong callback có thể tạo vòng chờ.
- Mã agent có thể tự cần nạp lớp hỗ trợ khi chạy. Nếu các dependency ấy chưa sẵn sàng, callback lại tạo ra class-loading activity mà chính nó đang quan sát.
- Lỗi và stack trace của callback không nhất thiết tới được log bên ứng dụng theo cách quen thuộc; Javadoc cho biết exception không được xử lý của transformer có hiệu ứng giống trả `null` đối với phép biến đổi và các transformer sau vẫn có thể được gọi.

Vì thế, nguyên tắc thiết kế ở đây là: **làm ít việc trong `transform`, đẩy công việc có thể gây nạp lớp, khóa, I/O hoặc cấp phát lớn ra nơi khác.**

## 2. Những tham số có thể sử dụng mà không nạp lại lớp mục tiêu

Java 17 hỗ trợ hai overload `transform`. Ví dụ chữ ký nhận thông tin module (xuất hiện từ Java 9):

~~~java
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer);
~~~

Đây là **chữ ký minh họa**, không phải một Java source file độc lập. Có thể override phiên bản năm tham số (không có `Module`); default method sáu tham số sẽ chuyển tiếp tới phiên bản năm tham số nếu phiên bản sáu tham số không được override.

| Tham số | Có ích để biết | Rủi ro cần tránh |
| --- | --- | --- |
| `className` | Tên nhị phân **dạng internal** như `demo/app/Target`, có thể dùng để lọc | Không tự gọi `Class.forName` để "xác nhận" tên; kiểm tra `null` trước |
| `loader` | Class loader định nghĩa, có thể là `null` với bootstrap loader | Không gọi `loadClass`, `getResource`, `toString` hoặc giữ strong reference vô hạn |
| `classBeingRedefined` | `null` khi định nghĩa lớp mới; có giá trị khi redefine/retransform | Không dựa vào nó để có `Class<?>` ở lần load đầu hoặc kích hoạt reflection |
| `module` | Module mang lớp đang transform (với overload sáu tham số) | Không chạy logic reflection/module scanning phức tạp trong hook |
| `protectionDomain` | Miền bảo vệ liên quan lớp đang được định nghĩa | Không lập tức mở code source URL/JAR, truy cập chính sách/quyền hoặc giữ object dài hạn |
| `classfileBuffer` | Bytecode đầu vào tại điểm transformer đang được gọi | Không chỉnh sửa trực tiếp buffer; không giữ tham chiếu lâu; có thể chứa dữ liệu nhạy cảm |

Khi không cần đổi bytecode, **`return null` là câu trả lời đúng**, nghĩa là transformer này không thực hiện biến đổi. Không trả nguyên `classfileBuffer` chỉ để báo "không đổi"; không chỉnh sửa trực tiếp byte[] đầu vào. Khi cần thay đổi thật, trả **một byte[] mới hợp lệ** và bảo đảm contract redefine/retransform nếu dùng các chức năng đó.

`className` dùng dấu `/`, không phải dấu `.`. Trong những trường hợp định nghĩa đặc biệt, tên có thể là `null`, nên filter phải luôn chịu được `null`. `loader == null` không có nghĩa "không xác định", mà thường chỉ bootstrap loader; cũng không nên suy ra quyền truy cập của agent tới mọi module chỉ từ thông tin tên.

## 3. Cách tạo ra phụ thuộc vòng ngay trong callback

### 3.1. Dùng reflection để tìm "lớp đang được load"

Đoạn dưới mô tả **điều không nên làm** khi JVM đang định nghĩa một lớp mới:

~~~java
// Ví dụ nguy hiểm: không đưa đoạn này vào transformer thực tế.
String binaryName = className.replace('/', '.');
Class<?> target = Class.forName(binaryName, true, loader);
target.getDeclaredMethods();
~~~

Khi lớp đang được định nghĩa, gọi `Class.forName` có thể yêu cầu class loader tham gia định nghĩa/chạy khởi tạo lớp cùng tên hoặc nạp các lớp mà phần reflection cần. Trong các tình huống cụ thể nó có thể gây load đệ quy, ClassCircularityError, LinkageError, deadlock hoặc hành vi phụ thuộc trạng thái thời điểm load. Đổi `true` thành `false` chỉ tránh yêu cầu initialization; **vẫn có thể kích hoạt loading và linking**. Không dùng cách đó để lấy metadata lớp đang ở trong quá trình định nghĩa.

Nếu cần phân tích cấu trúc lớp để quyết định transform, hãy đọc **bytes đã được JVM chuyển cho callback** bằng công cụ bytecode đã chuẩn bị trước, và chỉ làm việc cần thiết. Đọc bytes không cần định nghĩa lớp thành `Class<?>`; nhưng **parser** cũng có dependency, cấp phát và có thể tự gây class loading. Vì vậy phải đóng gói, preinitialize và kiểm soát parser.

### 3.2. Tham chiếu thẳng tới lớp ứng dụng từ mã agent

Ví dụ không nên đặt trong `transform`:

~~~java
// Minh họa nguy hiểm, không phải chương trình độc lập.
if (demo.app.Target.class.getName().equals(className)) {
    DiagnosticRegistry.record(demo.app.Target.class);
}
~~~

Trong Java source trên, một class literal có thể thúc đẩy resolution hoặc khiến mã callback phải liên kết tới loại do application loader quản lý. Một khi agent có phụ thuộc tĩnh vào mã ứng dụng, thứ tự class loading và visibility của loader trở thành một phần của tính đúng đắn. Mã agent ở class loader khác còn có thể gặp `NoClassDefFoundError` dù ứng dụng tự nạp được lớp ấy.

Thay vì phụ thuộc vào một object `Class` của target, so sánh **literal tên internal**:

~~~java
if ("demo/app/Target".equals(className)) {
    // Chỉ thu dữ liệu primitive/String nhỏ đã có sẵn.
}
~~~

Phép so sánh chuỗi không đòi JVM định nghĩa `demo.app.Target`. Đó chính là lý do callback thường lọc sớm trên `className` trước khi làm thao tác đắt.

### 3.3. Ghi log bằng framework trong hook

Một câu lệnh tưởng như vô hại:

~~~java
// Chỉ minh họa failure mode.
logger.debug("Transforming {}", className);
~~~

có thể kéo theo load backend logging, message formatter, provider, MDC, stack walker, service loader, cấu hình, appender và I/O. Khi log engine chưa được khởi tạo, những lớp hỗ trợ của nó có thể lại đi qua callback. Nếu logger dùng lock còn callback chạy dưới trạng thái class loading nhạy cảm, vòng lock càng khó đoán. Nhiều thư viện logging còn tạo dữ liệu đối tượng/phản chiếu hoặc lưu thông tin context không phù hợp để giữ trên đường này.

Không nhất thiết logger nào cũng lỗi; vấn đề là **phụ thuộc khó kiểm soát**, thời điểm khởi tạo và overhead. Với một callback bắt mọi lớp, một lệnh log cho từng lớp có thể làm log bùng nổ ngay lúc startup.

### 3.4. Lấy dữ liệu "cho đầy đủ" từ loader, domain hoặc bytes

- `loader.getClass().getName()`, `loader.toString()`, `loader.getResource(...)` hoặc `loader.loadClass(...)` có thể làm thêm việc class loading, synchronization hay I/O.
- `protectionDomain.getCodeSource()` và các bước lấy URL/JAR có thể tạo dependency mới; một `toString` của object tùy ý có thể gọi code không kiểm soát.
- Dùng JSON serializer để serialize `ClassLoader`, `Module` hoặc `ProtectionDomain` có thể kéo theo reflection, cycle, object graph rất lớn và rò thông tin.
- Giữ `classfileBuffer` ở queue dài hạn sẽ ghim nhiều mảng byte lớn, tăng heap, GC và nguy cơ lộ class bytes.
- Cache `Class<?>` hoặc `ClassLoader` trong một `static Map` của agent có thể giữ class loader sống sau khi ứng dụng undeploy/hot reload.

Với mục đích chẩn đoán thông thường, **tên lớp + loại sự kiện + vài counter** thường đủ để khoanh vùng. Chỉ giữ các object sống của class loader nếu có một cơ chế lifecycle/weak reference được thiết kế và kiểm chứng rõ ràng.

## 4. Kiến trúc thu thập: đường nóng nhỏ, chẩn đoán xử lý ở nơi khác

Một kiến trúc thực dụng:

~~~text
                  Agent bootstrap (premain/agentmain)
                    | tạo DiagnosticState
                    | nạp trước các helper cần thiết
                    | cấu hình bộ lọc / giới hạn / writer
                    v
       đăng ký ClassFileTransformer (một lần)
                    |
              mỗi callback transform
                    |
              name == null? -> return null
                    |
              không đúng prefix? -> return null
                    |
              ghi primitive/counter/metadata nhỏ
                    |
              buffer hữu hạn / overwrite hoặc drop
                    |
                 return null
                    |
       +------------+------------------------------+
       |                                           |
JVM tiếp tục define lớp                     Reporter của agent
                                            đọc snapshot
                                            redaction / format
                                            ghi log / JFR / export
                                            bên ngoài callback
~~~

Tách thành ba trách nhiệm:

1. **Bootstrap:** chuẩn bị helper, khởi tạo counter/buffer và reporter **trước khi** đăng ký transformer. Tránh việc callback lần đầu tự động init cả graph thư viện.
2. **Collector trong callback:** lọc sớm, ghi vào cấu trúc đã cấp phát, chịu được concurrency, có độ trễ và memory bound, không block chờ reporter.
3. **Reporter ngoài callback:** định kỳ lấy snapshot hoặc drain queue, tổng hợp, định dạng, ghi log/xuất mạng, quản lý timeout/batch, retention và sức khỏe pipeline.

Đường này không loại bỏ 100% class-loading side effects (JVM, compiler/JIT, thư viện và lịch trình có thể thay đổi), nhưng giảm đáng kể sự phụ thuộc không kiểm soát. Không chạy reporter bên trong `transform` chỉ vì "muốn log ngay".

### 4.1. Những việc nên làm trước khi đăng ký transformer

- Khởi tạo **lớp transformer**, các lớp helper, counter, filter và cấu trúc dữ liệu dùng trên hot path.
- Nếu có parser bytecode, chuẩn bị và thử parser trên dữ liệu an toàn trước khi hook bắt đầu; cân nhắc preload/relocate helper packages.
- Thiết lập **self-exclusion** cho package của agent, logger, exporter, serializer hoặc package nội bộ không cần theo dõi.
- Xác định kích thước bộ đệm, giới hạn payload, số event/giây và hành vi khi đầy.
- Chọn reporter thread/lifecycle bên ngoài callback. Dùng daemon worker nếu phù hợp, và ngắt/flush theo ngân sách khi shutdown.
- Không gọi `Instrumentation.addTransformer` nhiều lần ngoài ý muốn; đăng ký trùng có thể gây gọi callback lặp và khó xác định nguồn.

"Đã preload" không phải chứng chỉ rằng mọi dependency chắc chắn không còn class loading sau đó (ví dụ lazy provider, lambda, charset, locale, logging backend). Cần kiểm thử được trên JVM phiên bản thực tế và vẫn giữ đường callback đơn giản.

### 4.2. Mức dữ liệu nên lưu

| Dữ liệu | Khuyến nghị | Lý do |
| --- | --- | --- |
| Tổng số callback theo filter | Atomic counter | Đếm nhanh, không ghim target class |
| `className` dạng internal | Tối đa một số slot có giới hạn hoặc sample | Có thể định hướng điều tra mà không nạp class |
| `loader == null` | Boolean/flag khi có ích | Không giữ reference tới loader |
| Load mới vs redefine/retransform | `classBeingRedefined == null` hoặc metadata đã xác định | Không buộc gọi reflection vào `Class<?>` |
| `Module`, `ClassLoader`, `ProtectionDomain` | Tránh giữ trực tiếp trong buffer dài hạn | Có thể giữ sống graph lớp/JVM |
| `classfileBuffer` | Chỉ dùng trong callback khi transform thật sự cần | Mảng byte có thể lớn và chứa bí mật |
| Stack trace đầy đủ | Chỉ thu có chọn lọc ở phần xử lý bên ngoài callback | Có phí cao và mở rộng dependency |
| Token/cấu hình/URL nhạy cảm | Redact hoặc không lưu | Telemetry không được trở thành đường rò dữ liệu |

Không phải mọi dữ liệu có thể tạo được **sau** callback: nếu muốn ghi tên lớp, loại sự kiện hoặc nhãn quan sát được ngay tại thời điểm transform, hãy lưu **snapshot tối giản của thông tin có sẵn**; reporter không cần gọi ngược lại class loader để dựng metadata.

## 5. Ví dụ Java 17+: bộ đệm chẩn đoán hữu hạn, callback không nạp `Target`

Ví dụ tạo một startup agent và ứng dụng đơn giản. Agent chỉ ghi nhận callback cho `demo/app/Target` bằng một `AtomicLong` và `AtomicReferenceArray<String>` có tám slot. Callback **không gọi `Class.forName`**, không log, không serialize và không tham chiếu tới `demo.app.Target.class`. Reporter in số liệu lúc JVM kết thúc bình thường qua shutdown hook, tức là ở ngoài `transform`.

Bốn file cần có là `SafeDiagnosticAgent.java`, `Main.java`, `MANIFEST.MF` và JAR được tạo từ chúng. Hai file Java có thể được đặt cùng một thư mục nguồn; `javac -d` tạo cây thư mục class tương ứng với package.

### 5.1. File `SafeDiagnosticAgent.java`

~~~java
import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReferenceArray;

public final class SafeDiagnosticAgent {
    private static final int CAPACITY = 8;
    private static final AtomicLong SEEN = new AtomicLong();
    private static final AtomicReferenceArray<String> RECENT =
            new AtomicReferenceArray<>(CAPACITY);

    public static void premain(String agentArgs, Instrumentation inst) {
        // Khởi tạo helper/các thao tác thiết yếu trước đăng ký.
        Observer observer = new Observer();
        SEEN.getAndIncrement();
        SEEN.set(0);
        RECENT.set(0, null);

        Runtime.getRuntime().addShutdownHook(
                new Thread(SafeDiagnosticAgent::report, "agent-report"));

        inst.addTransformer(observer, false);
        System.out.println("AGENT_READY");
    }

    private static void report() {
        System.out.println("TARGET_CALLBACKS=" + SEEN.get());
        System.out.println("RECENT_TARGET=" + RECENT.get(0));
    }

    private static final class Observer implements ClassFileTransformer {
        @Override
        public byte[] transform(
                ClassLoader loader,
                String className,
                Class<?> classBeingRedefined,
                ProtectionDomain protectionDomain,
                byte[] classfileBuffer) {

            // So sánh tên internal; không resolve/load target class.
            if (!"demo/app/Target".equals(className)) {
                return null;
            }

            long sequence = SEEN.getAndIncrement();
            int slot = (int) (sequence & (CAPACITY - 1));
            RECENT.set(slot, className);
            return null;
        }
    }
}
~~~

**Phân tích từng quyết định:**

- `Observer` được tạo trước khi `inst.addTransformer(...)`. Các object/cấu trúc dùng trong callback đã có sẵn; phần "warm up" counter và slot chỉ giúp sẵn sàng hơn, không bảo đảm mọi đường JDK đã được nạp trước.
- Method năm tham số được override. Trên Java 17, default overload có `Module` sẽ gọi lại bản này nếu ta không override overload sáu tham số.
- Filter so sánh `"demo/app/Target".equals(className)` tránh `NullPointerException` khi tên là null và **không** bắt buộc nạp class Target để so sánh.
- `SEEN.getAndIncrement()` cấp một số thứ tự cho event, dùng `AtomicLong` chịu được concurrent callbacks. Đây là **số lần callback khớp filter**, không phải số lần JVM đã định nghĩa lớp thành công.
- `AtomicReferenceArray` có đúng tám ô: công thức `sequence & 7` đưa mỗi event vào một slot. Với nhiều sự kiện, slot cũ sẽ bị ghi đè; bộ nhớ giữ số tên lớp có giới hạn. Chuỗi tên class được cung cấp qua tham số callback; không giữ `Class<?>`, `ClassLoader` hay `byte[]`.
- `return null` nghĩa là **không đổi bytecode**. Chức năng đếm và hiển thị metadata chỉ là quan sát.
- `report()` chạy trong shutdown hook, không nằm trong callback. Vì vậy `System.out`, định dạng chuỗi và I/O chỉ nằm ở bước xuất kết quả. Shutdown hook là cách demo thuận tiện, **không phải giao thức telemetry đáng tin cho production**.
- Không có dependency bên thứ ba. `SafeDiagnosticAgent` ở default package chỉ để giảm thao tác biên dịch, không phải cấu trúc được khuyến nghị cho agent lớn.

**Giới hạn concurrency của ring:** counter atomic ghi nhận số lần callback, nhưng việc hai luồng `SEEN.getAndIncrement()` rồi `RECENT.set(...)` có thể bị lập lịch xen kẽ. Mảng chỉ cho snapshot gần đây theo best-effort; nó không bảo đảm "tám sự kiện mới nhất" theo thứ tự thời gian hay một hàng đợi tiêu thụ đúng một lần. Nếu cần bảo toàn thứ tự/lossless, phải chọn cấu trúc và cơ chế backpressure khác, chấp nhận chi phí và giả định rõ ràng.

### 5.2. File `Main.java`

~~~java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("APP_RESULT=" + Target.answer());
    }
}

final class Target {
    static int answer() {
        return 42;
    }
}
~~~

`Main` và `Target` được biên dịch thành hai class files trong package `demo.app`. Khi ứng dụng thực hiện lời gọi `Target.answer()`, JVM phải có định nghĩa `demo/app/Target`; agent đã được đăng ký từ `premain` trước khi `main` chạy.

### 5.3. File `MANIFEST.MF`

~~~text
Manifest-Version: 1.0
Premain-Class: SafeDiagnosticAgent

~~~

Manifest ở đây dành cho **startup agent**: `Premain-Class` trỏ tới lớp `SafeDiagnosticAgent` chứa `public static void premain(...)`. Bảo đảm có newline kết thúc và dòng trống cuối main section. Không cần `Agent-Class` vì bài thực hành không nạp động bằng Attach API.

### 5.4. Biên dịch, đóng gói và chạy

Trong thư mục chứa ba file nguồn vừa tạo, dùng JDK 17 trở lên:

~~~bash
javac --release 17 -d agent-out SafeDiagnosticAgent.java
javac --release 17 -d app-out Main.java
jar --create --file safe-agent.jar --manifest MANIFEST.MF -C agent-out .
java -javaagent:safe-agent.jar -cp app-out demo.app.Main
~~~

Hai lệnh `javac -d` tạo output directories và các subdirectories cần thiết trên JDK 17+. `jar --create` đóng gói agent class cùng nested class `SafeDiagnosticAgent$Observer.class` vào `safe-agent.jar`; ứng dụng được chạy độc lập qua `-cp app-out`. Hãy dùng một lần chạy mới, không đồng thời gắn agent khác hoặc chủ động redefine/retransform `Target` để so sánh expected output.

**Standard output do ví dụ tạo trên JVM thông thường:**

~~~text
AGENT_READY
APP_RESULT=42
TARGET_CALLBACKS=1
RECENT_TARGET=demo/app/Target
~~~

Giải thích: `AGENT_READY` xuất hiện trong `premain`. Ứng dụng sau đó in `42`; callback cho lớp Target được tính một lần; khi JVM shutdown bình thường, reporter in thống kê đã ghi. Với môi trường có agent khác, custom class loaders, nhiều redefinition hoặc JVM thêm diagnostics, output có thể thêm dòng hoặc số lượt callback khác. Không coi số `1` là chuẩn bất biến cho mọi workload.

**Chức năng thật sự được chứng minh:** lớp Target hoạt động như cũ trong demo, filter tên lớp hoạt động, dữ liệu nhỏ được lưu mà callback không gọi vào class Target, và việc in báo cáo được tách khỏi callback. Nó **không** chứng minh bytecode modification, retransformation, logging backend hay agent hoàn toàn không thể gặp class loading nội bộ.

## 6. Khi cần thu nhiều sự kiện: chọn storage và chính sách mất dữ liệu

Bộ đệm thích hợp phải có **capacity** và **failure policy** rõ ràng. Một số lựa chọn:

| Cơ chế | Ưu điểm | Rủi ro và điều kiện |
| --- | --- | --- |
| `AtomicLong`/`LongAdder` counters | Ít dữ liệu, cạnh tranh tương đối thấp; phù hợp tổng số | Không giữ tên/chuỗi sự kiện; cách đếm không đồng nghĩa class load thành công |
| `AtomicReferenceArray` ring overwrite | Cấp phát hữu hạn, ghi nhanh, không giữ loader | Bị ghi đè; snapshot có thể không đúng thứ tự khi đa luồng |
| Queue bounded + `offer` | Có chỗ tách producer và consumer, báo được khi đầy | Một số implementation dùng lock; `offer` không chờ có dung lượng nhưng **có thể tranh lock** |
| Concurrent queue không giới hạn | API đơn giản, không block trên capacity | Nếu consumer chậm, dữ liệu/phân bổ bộ nhớ tăng không giới hạn |
| Bộ đệm thread-local | Giảm tranh chấp giữa producers | Phải quản lý vòng đời thread và tổng bộ nhớ; thread pool kéo dài tuổi thọ dữ liệu |
| Export trực tiếp trong callback | Dữ liệu đi ngay | Nên tránh: I/O, serialization, retry và lock làm chậm/đảo luồng load |

**Overwriting ring** là chính sách **best-effort snapshot**: giữ gần đây, chấp nhận mất lịch sử. **Drop-on-full** của queue là chính sách khác: từ chối event mới khi đầy, có `droppedCounter` để biết đã mất gì. Cả hai cần một metric riêng về số sự kiện bị ghi đè/drop và một tuyên bố rõ ràng rằng dữ liệu không hoàn chỉnh.

Nếu yêu cầu "không mất sự kiện", bạn phải cân nhắc độ tin cậy của dữ liệu với an toàn của JVM. Block vô hạn trong transformer để "chờ chỗ trống" thường là lựa chọn nguy hiểm, vì callback đang nằm trong vòng đời class loading. Với nghiệp vụ cần ghi nhận chính xác, hãy dùng một kênh audit nghiệp vụ bền vững riêng; diagnostics best-effort không thể thay audit transaction.

### 6.1. Giới hạn số lượng và kích thước

Một số phép tính giúp tránh thiết kế ngẫu nhiên:

- 100.000 callback mà mỗi event giữ một array class bytes trung bình 20 KiB sẽ giữ khoảng **2 GiB** dữ liệu thô, chưa kể overhead. Không lưu byte[] vì "sẽ phân tích sau" mà không có hard limit.
- Một ring có 256 slots giữ tối đa 256 object references ở một thời điểm; chuỗi/record được tham chiếu vẫn tiêu thụ memory nên cần giới hạn kích thước record.
- Nếu log từng lớp trong một hệ thống có hàng chục nghìn class definitions, log volume ngay lúc startup có thể vượt tốc độ exporter; cần lọc trước khi tạo event.
- Nếu quá tải, có thể tăng filter specificity, giảm sampling rate, chỉ thu counter tổng hợp hoặc bỏ event. Luôn phản ánh việc mất mẫu trong báo cáo.

Các số trong phép tính là minh họa. Dung lượng thực tế phải đo theo class sizes, tốc độ nạp lớp, GC và cấu hình agent. Đếm số callback của transformer không tương đương số class đang sống trong heap.

### 6.2. Độc lập class loader và quản lý tham chiếu

Trong ứng dụng có plugin, app server hay hot reload, class loader có thể được tạo và bỏ nhiều lần. Một `Map<ClassLoader, Diagnostics>` đặt trong agent global sẽ giữ strong reference đến loader; nó có thể làm toàn bộ class graph/metadata không được thu hồi. Ngay cả cache `Class<?>` cũng có thể kéo theo giữ loader.

Giải pháp tùy mục đích:

- Không giữ loader nếu chỉ cần số lượt callback theo package.
- Nếu cần danh tính loader, tạo một identifier riêng có vòng đời quản lý; không lấy `toString` của loader tùy ý trong callback.
- Dùng weak references/weak-key maps **nếu thật sự cần theo dõi loader**, nhưng phải hiểu equality, cleanup, đồng thời và việc một giá trị vô tình giữ lại key.
- Hủy hoặc thu nhỏ dữ liệu khi agent/module không còn cần quan sát. `removeTransformer` ngăn callback tương lai nhưng Javadoc cho biết một số callback đã chạy có thể tiếp tục sau khi remove; code cần chịu được trạng thái đó.

## 7. Preload và class loader isolation: cần nhưng chưa đủ

Một cách phòng ngừa là đóng gói helper dùng riêng cho agent, và cố gắng khởi tạo trước lúc đăng ký transformer. Có thể đưa các helper vào agent JAR hoặc dùng shaded/relocated dependencies để tránh xung đột tên với ứng dụng, tùy cách agent triển khai. Không nên để helper được resolve bằng class loader của chính lớp mục tiêu trong callback.

Tuy nhiên có vài bẫy:

1. **Lazy loading:** thư viện đã instantiate nhưng lần đầu gọi method mới nạp formatter, codec, lambda hoặc provider.
2. **Bootstrap/library instrumentation:** nếu transformer áp dụng lên `java/*` hay `jdk/*`, ngay helper JDK dùng để ghi dữ liệu cũng có thể làm phát sinh callback. Filter sớm, chỉ instrument nhóm thật sự cần.
3. **Không có lớp `Class<?>` ở load mới:** `classBeingRedefined == null` là contract bình thường; không chạy `Class.forName` để bù.
4. **Cross-loader visibility:** agent được load bởi một loader chưa chắc có quyền truy cập lớp của ứng dụng. Một package name đúng không có nghĩa `loader.loadClass` sẽ an toàn.
5. **Instrumentation of helpers:** nếu tự instrument agent/helper/exporter, có thể tạo recursion trong đường đo. Xác định phạm vi exclude trước khi bật.
6. **Module boundary:** `Module` từ API không phải giấy phép tự động đọc/mở toàn bộ module hoặc gọi reflection vào mọi package. Cần xử lý module access hợp lệ ở phần setup nếu thật sự cần.

Javadoc `Instrumentation.addTransformer` nói các lớp mà transformer phụ thuộc có thể được loại khỏi luồng callback. Điều đó **không** phải bảo đảm tổng quát rằng "dependency nào cũng tự động an toàn". Đừng dựa vào một cơ chế loại trừ nội bộ của JVM để bỏ qua thiết kế tránh reentrancy và class-loader dependency.

## 8. Guard chống reentrancy: tác dụng và giới hạn

Một số agent dùng `ThreadLocal` làm reentrancy guard. Mục tiêu là ngăn **cùng một luồng** xử lý nested diagnostic event do chính đường đo của nó tạo ra. Mã ý tưởng:

~~~java
// Pseudocode: minh họa guard, không phải class chạy độc lập.
if (Boolean.TRUE.equals(IN_DIAGNOSTICS.get())) {
    return null;
}
IN_DIAGNOSTICS.set(Boolean.TRUE);
try {
    captureMinimalMetadata(className);
    return null;
} finally {
    IN_DIAGNOSTICS.remove();
}
~~~

`IN_DIAGNOSTICS` phải được khai báo/khởi tạo trong agent trước khi transformer đăng ký; `captureMinimalMetadata` phải là đường xử lý an toàn đã chuẩn bị. Đây không phải cách "thêm ThreadLocal là mọi callback trở nên an toàn":

- Guard chỉ tránh reentrancy **trong cùng thread**; nó không giải quyết deadlock giữa hai thread hoặc dependency class loading của thread khác.
- `ThreadLocal` có thể làm tăng overhead hoặc cấp phát trạng thái mới ở thread khác; dùng `remove` tránh sót context trong thread pool.
- Nếu guard nằm *sau* lệnh gọi logger/parser có khả năng kích hoạt loading, nó đến quá muộn.
- Giữ guard qua tác vụ bất đồng bộ không tự truyền qua thread khác.
- Khi callback ném lỗi, `finally` phải khôi phục trạng thái; một guard bị kẹt có thể âm thầm làm mất mọi diagnostics tiếp theo trên thread đó.

**Ưu tiên không tạo ra dependency ngay từ đầu.** Guard là lớp phòng thủ bổ sung khi không tránh hoàn toàn được logic lồng nhau, cần test trên JDK, loader, class loading và concurrency của ứng dụng thật.

## 9. Lỗi trong callback và cách giữ tín hiệu chẩn đoán

Contract của `ClassFileTransformer` có một chi tiết dễ gây hiểu lầm: **nếu một transformer ném exception không được xử lý, JVM vẫn thử các transformer tiếp theo và vẫn thử quá trình load/redefine/retransform**; đối với phép biến đổi của transformer lỗi, hiệu ứng giống trả `null`. Vì vậy, bạn có thể không thấy một exception bình thường nảy ra ở nơi ứng dụng gọi class, nhưng đã mất phép biến đổi hoặc mất diagnostics.

Cách tổ chức:

- Với lỗi dự kiến của diagnostic storage, có một **failure counter tối giản**, và `return null` khi không có biến đổi bytecode.
- Không cố tạo exception message lớn, stack trace đầy đủ hoặc gọi logger phức tạp bên trong callback; điều đó có thể tạo vòng lỗi mới.
- Nếu thực sự cần báo lỗi, thu mã lỗi/số lượng nhỏ ở callback, chuyển sang reporter để định dạng, quyết định retry hoặc cảnh báo.
- Với lỗi classfile hợp lệ của logic biến đổi, API cho phép `IllegalClassFormatException` khi dữ liệu không phải class file đúng định dạng. Đó không phải lệnh "buộc JVM phải dừng": loại lỗi này cũng có hiệu ứng như trả `null` trong chuỗi transformer. Cần có kiểm thử riêng để xác nhận transformer không tạo bytes lỗi.
- Javadoc nhắc có thể `catch Throwable` để phòng tác động từ unchecked exceptions. Khi thiết kế production, không âm thầm nuốt mọi lỗi nghiêm trọng của JVM như `OutOfMemoryError` rồi giả vờ ổn định. Chọn chính sách lỗi, đo lường và hậu quả rõ ràng.

Ví dụ minh họa **một phương thức helper, không phải source độc lập**:

~~~java
private byte[] safeObserve(String className) {
    try {
        if (className != null && className.startsWith("demo/app/")) {
            observed.incrementAndGet();
        }
    } catch (RuntimeException diagnosticFailure) {
        failures.incrementAndGet();
    }
    return null;
}
~~~

Ở đây, `observed` và `failures` là **các bộ đếm đã được tạo sẵn**. Đây chỉ là mẫu xử lý lỗi dự kiến; nếu bản thân `failures.incrementAndGet()` hay lớp helper chưa được chuẩn bị khiến phát sinh lỗi mới, callback vẫn cần thiết kế bảo vệ tốt hơn. Đừng làm lỗi diagnostic thay đổi bytecode trả về hoặc contract của lớp nghiệp vụ.

## 10. Reporter ngoài callback: định dạng, xuất dữ liệu và shutdown

Đưa I/O ra một worker hoặc điểm lifecycle khác giúp callback không bị network/formatter cản trở; nhưng reporter vẫn chạy **trong cùng JVM** nên dùng chung CPU, heap, GC và có khả năng tạo class loading. Vì vậy:

- Khởi tạo reporter trên luồng/đường khởi động agent trước hoặc độc lập với callback; chuẩn bị dependency và có bộ lọc bỏ qua package của exporter.
- Chỉ tiêu thụ dữ liệu đã snapshot; không gọi ngược vào `Class.forName` của class đang load để bổ sung thông tin thiếu.
- Với queue có giới hạn, dùng flush/batch theo ngân sách, timeout, drop metrics; tránh retry vô tận khi collector lỗi.
- Không gửi event có chứa secret, class bytes, toàn bộ class loader object hoặc đường dẫn có thông tin nhạy cảm.
- Nếu reporter lỗi, callback không nên chờ reporter sửa xong; giữ fail-open cho diagnostics nếu contract ứng dụng yêu cầu, và cảnh báo mất tín hiệu.
- Đặt shutdown hook với giới hạn công việc; `Runtime.halt`, kill -9, JVM crash hoặc môi trường tắt đột ngột có thể khiến shutdown hook không chạy. Vì vậy ví dụ in lúc shutdown không phải đảm bảo lưu trữ bền vững.
- Tránh worker non-daemon sống vô hạn khiến ứng dụng không thoát; đóng tài nguyên và dừng worker theo vòng đời phù hợp.

Tại nơi cần giữ dữ liệu qua crash, hãy cân nhắc cơ chế ghi nhận khác có độ bền thích hợp, nhưng không biến `transform` thành nơi ghi file đồng bộ cho mọi lớp chỉ để bảo đảm mất mát bằng 0.

## 11. Chất lượng dữ liệu: callback không đồng nghĩa class loading thành công

Một counter như `TARGET_CALLBACKS=1` chứng minh transformer đã được JVM gọi một lần cho tên khớp filter trong demo. Nó **không** chứng minh:

- Lớp đã đi qua bước verify/link/initialize thành công sau khi callback trả về.
- Tên lớp là duy nhất trong toàn JVM: cùng tên có thể xuất hiện qua nhiều defining class loaders.
- Mọi class definition đã đi qua agent: agent đăng ký muộn không tự thấy lớp đã load trước; một số dependency class definitions được loại trừ theo contract.
- Một callback ứng với đúng một event nghiệp vụ hoặc một phương thức thực thi.
- Dữ liệu đã được gửi thành công tới backend khi chỉ vừa nằm trong ring.
- Thứ tự ghi ring phản ánh tuyệt đối thứ tự thời gian ở nhiều thread.

Nếu cần tính số **lớp đang được nạp thành công** hoặc bản đồ chính xác của loaded classes, cần định nghĩa lại tín hiệu, bổ sung những nguồn chẩn đoán độc lập và xử lý các điều kiện JVM hỗ trợ. Phép đo số lần callback nên được đặt tên đúng và đi kèm mất mẫu/giới hạn coverage.

Để chẩn đoán thiếu dữ liệu, phân biệt:

| Quan sát | Diễn giải khả dĩ | Kiểm tra tiếp |
| --- | --- | --- |
| Counter tăng, ring không còn tên cũ | Slot đã bị overwrite | Tổng event và capacity, xem retention/snapshot |
| Counter không tăng cho lớp đang kỳ vọng | Filter sai, lớp đã load trước registration, khác loader/đường load, callback chưa chạy | Kiểm tra tên internal, thời điểm đăng ký, JDK/agent setup |
| App load class lỗi nhưng counter đã tăng | Callback chạy trước verify/define hoàn tất | Xem ClassFormatError/LinkageError và log JVM |
| Exporter thiếu sự kiện dù counter tăng | Queue drop/flush thất bại, backend bị lỗi/lag | Theo dõi drop/failure/ingest delay |
| Agent khởi động chậm | Hook hoặc helper init nặng, logger/encoder được load lúc đầu | Tách thời gian premain và callback, giảm package được instrument |
| Tăng heap khi hot redeploy | Agent giữ strong reference tới loader/class hoặc bytes | Kiểm tra cache, weak refs và retention |

## 12. QA trước khi triển khai vào dịch vụ thật

Đừng chỉ kiểm thử "agent đã in đúng". Dùng một matrix gọn nhưng đánh đúng failure modes:

| Nhóm test | Cách kích hoạt | Điều kiện chấp nhận |
| --- | --- | --- |
| Load mới | Main gọi lớp mới sau `premain` | Callback nhận tên internal đúng; app trả kết quả như baseline |
| Tên null / bootstrap | Callback gặp tên null hoặc loader null | Không NPE; không ép load class để biết tên |
| Tranh chấp nhiều luồng | Nhiều thread load các lớp khác nhau | Không deadlock, data race, queue vượt giới hạn |
| Reentrancy | Logger/parser/helper được lazy load ở thời điểm thử | Không recursive hook vô hạn; filter/guard có hiệu lực |
| Reporter down | Thử collector mất mạng, queue đầy | Class loading không treo; drop/overwrite có tín hiệu |
| Redeploy / custom loader | Load rồi thả class loader plugin | Agent không giữ strong references ngoài ý muốn |
| Lỗi bytecode | Cố tình cung cấp dữ liệu biến đổi lỗi trong test cách ly | Fail path rõ ràng, không làm hỏng class ngoài phạm vi |
| Retransform / redefine | Nếu agent có hỗ trợ, thử trên lớp modifiable | Callback semantics/đếm đúng; không thay đổi schema trái giới hạn JVM |
| Shutdown / abrupt stop | Tắt bình thường và kill cưỡng bức ở môi trường thử | Hiểu tín hiệu nào có thể mất; không dựa hoàn toàn vào shutdown hook |

**Quy trình đo overhead:** chạy baseline không agent, agent bật nhưng filter bỏ qua mọi lớp, agent với filter thật và reporter bật. Giữ tải, JDK flags và workload tương đương; so sánh startup time, CPU, heap, allocation, GC, thread contention, class-loading rate, latency p95/p99, số event ghi/ghi đè và drop. Đừng gán một overhead cố định cho mọi agent.

### Checklist thiết kế ngắn

1. Lọc bằng `className` và giá trị nguyên thủy; tránh giải quyết `Class<?>` cho lớp đang được nạp.
2. Tiền khởi tạo helper, parser cần thiết và bộ nhớ đệm trước `addTransformer`.
3. Không log/serialize/đọc tài nguyên/đợi I/O bên trong `transform`.
4. Không giữ `classfileBuffer`, loader, `Class<?>` hay domain trong global collection vô hạn.
5. Có capacity, overwrite/drop policy và thống kê mất dữ liệu.
6. Xuất dữ liệu bên ngoài callback, có timeout và self-exclusion cho agent/exporter.
7. QA trên nhiều thread, custom loaders, class loading và khi reporter lỗi.
8. Nêu rõ event được đếm là **callback** chứ không phải class thành công hoặc nghiệp vụ hoàn tất.

## 13. Các sai lầm thường gặp

- **"Chỉ gọi `Class.forName(name, false, loader)` nên không thể gây load."** Sai: `false` không khởi tạo lớp nhưng vẫn có thể load/link.
- **"Log chỉ đọc dữ liệu nên không gây tác động."** Sai: backend, formatter, lock, I/O và lớp hỗ trợ có thể chạy ngay lúc lớp đang được định nghĩa.
- **"Có `Class<?>` trong mọi transform callback."** Sai: `classBeingRedefined` thường là null khi load mới.
- **"Trả `classfileBuffer` là cách biểu thị không đổi."** Contract dành `return null` cho no-op; không sửa trực tiếp input bytes.
- **"Gọi `getResource` trên loader để biết nguồn lớp là an toàn."** Không đảm bảo; loader có thể thực hiện I/O, khóa và thêm class loading.
- **"Queue có `offer` thì không bao giờ chặn thread."** Không đảm bảo với implementation dùng lock; `offer` chỉ có nghĩa khác `put` về chờ capacity.
- **"ThreadLocal guard giải quyết mọi vòng phụ thuộc."** Nó chỉ giới hạn reentrancy cùng thread; không xử lý deadlock giữa thread.
- **"Buffer ring chứa tám event mới nhất chính xác theo thời gian."** Không đảm bảo khi callbacks chạy đồng thời và slot bị overwrite.
- **"`removeTransformer` ngừng ngay mọi callback."** In-flight callbacks có thể tiếp tục.
- **"Callback chạy chứng minh class definition thành công."** Callback được gọi trước khi class bytes được verify/áp dụng.
- **"Đã preload agent thì exporter không còn loading lớp."** Lazy initialization vẫn có thể xảy ra; phải kiểm chứng.

## 14. Câu hỏi tự kiểm tra

1. Vì sao một lời gọi `Class.forName(className.replace('/', '.'), false, loader)` vẫn có thể là sai trong `transform`?
2. `classBeingRedefined` khác nhau thế nào giữa định nghĩa mới và redefine/retransform?
3. `return null` trong `ClassFileTransformer` có nghĩa gì? Có cần trả input byte[] khi không đổi không?
4. Vì sao callback chỉ nên giữ `loader == null` thay vì lưu loader object vào static map?
5. Điều gì khiến logger hoặc JSON encoder có thể tạo recursion hoặc deadlock dù chỉ "ghi chẩn đoán"?
6. Phân biệt counter callback, ring overwrite và queue drop; chúng cho phép kết luận gì về chất lượng dữ liệu?
7. Trong ví dụ, vì sao `SafeDiagnosticAgent` phải gọi `new Observer()` và chuẩn bị bộ đệm trước `addTransformer`?
8. Nếu class Target nạp thành công nhưng reporter bị kill, bạn còn biết chắc điều gì từ count nội bộ, và mất điều gì khi xuất dữ liệu?
9. Khi đa luồng ghi ring có tám slot, liệu snapshot luôn là tám sự kiện mới nhất theo timestamp không?
10. Nếu dùng Byte Buddy/ASM thực sự biến đổi bytes, bạn sẽ chuẩn bị helper và tách log lỗi thế nào để không phụ thuộc vào lớp target đang được định nghĩa?

## 15. Kết luận và nguồn đọc thêm

Hãy xem `transform` như một **đoạn mã nằm trong giao dịch định nghĩa lớp**. Không giải quyết `Class<?>` của lớp đang load, không gọi vào class loader hoặc thư viện có graph phụ thuộc khó kiểm soát, không xuất dữ liệu đồng bộ trên đường này. Giữ callback chỉ lọc metadata sẵn có và cập nhật cấu trúc nhỏ, hữu hạn; chuyển phần xử lý tốn kém ra ngoài; mô tả rõ coverage, overwrite/drop, concurrency và tính không đầy đủ của dữ liệu.

Khi transformer thực sự biến đổi bytecode, phần sửa bytes **phải xảy ra và trả kết quả đồng bộ trong callback** để JVM dùng class definition mới. Việc chuyển ra ngoài chỉ áp dụng cho **format, ghi nhận, tổng hợp và export diagnostics**; không thể lùi một phép biến đổi bytecode bắt buộc ra sau khi lớp đã được định nghĩa rồi coi như cùng một cơ chế.

**Tham khảo chính thức:**

- [Oracle JDK 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): thời điểm callback, các tham số, `null` khi no-op, chaining, exception và redefine/retransform.
- [Oracle JDK 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, quan hệ giữa các transformers, `removeTransformer` và các giới hạn retransformation.
- [Oracle JDK 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): vòng đời startup/dynamic agent, manifest và `Instrumentation`.
- [Oracle JDK 21 — javac](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): `--release` và `-d`, cách đặt package classes vào output directory.
