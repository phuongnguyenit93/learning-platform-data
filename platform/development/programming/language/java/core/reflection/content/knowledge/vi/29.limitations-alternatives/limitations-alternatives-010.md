# Đối chiếu hành vi Reflection trên JVM tiêu chuẩn, runtime bị hạn chế và môi trường AOT

## 1. Mục tiêu và phạm vi

Java Reflection cho phép tìm lớp theo tên, đọc annotation, tìm constructor/method/field và gọi chúng ở **thời điểm chạy**. Trên JVM thông thường, thao tác này thường dựa vào các class file có sẵn trên classpath hoặc module path. Nhưng cùng một chương trình có thể hoạt động khác khi:

- chạy trong **named module** của JPMS, chịu quy tắc `exports`, `opens` và quyền truy cập thành viên;
- chạy trong **GraalVM Native Image**, nơi phần lớn cấu trúc ứng dụng được phân tích và đưa vào binary trước khi chạy;
- dùng **Spring AOT** hoặc framework tối ưu trước các quyết định vốn được suy ra bằng quét classpath/Reflection;
- chạy trong một sandbox, runtime tùy biến hoặc nền tảng có quy tắc riêng với nạp lớp, tạo bytecode và quyền Reflection.

Bài học giúp đối chiếu **nguyên nhân, triệu chứng, cách kiểm tra và lựa chọn thay thế**. Một nguyên tắc quan trọng: **“biên dịch trước” không tự động có nghĩa “không hỗ trợ Reflection”**. Phải xác định chính xác công nghệ, phiên bản, chính sách module và loại thao tác động đang dùng.

## 2. Hai câu hỏi độc lập cần hỏi trước khi gọi Reflection

Mọi lời gọi Reflection phụ thuộc ít nhất vào hai yếu tố:

1. **Có gì hiện diện ở runtime?** Class, constructor, method, field, annotation metadata, resource hay proxy class có tồn tại/được giữ lại trong môi trường chạy không? Đây là vấn đề *reachability* hoặc *availability*.
2. **Ai được phép truy cập?** Lookup/caller có quyền đọc module, dùng thành viên public, hay thực hiện *deep reflection* vào thành viên private không? Đây là vấn đề *accessibility*.

Trên HotSpot JVM, có thể có `Class.forName("demo.Plugin")` thành công nhưng `getDeclaredConstructor().newInstance()` thất bại vì constructor không accessible. Trên Native Image, chính `Class.forName(...)` hoặc truy vấn constructor có thể thiếu metadata cần thiết **ngay cả khi source Java và JAR build đều chứa class ấy**.

**Đăng ký reachability metadata không phải cơ chế vượt rào `private` của JPMS.** Ngược lại, mở package bằng `--add-opens` không tự làm Native Image giữ mọi thành viên được gọi động. Hai nhóm điều kiện phải được xét riêng.

## 3. Bảng đối chiếu các môi trường phổ biến

| Môi trường/cấu hình | Khám phá lớp/thành viên ở runtime | Ràng buộc chính | Hướng xử lý |
| --- | --- | --- | --- |
| JVM thông thường, classpath | Có thể nạp class còn sẵn trong đường dẫn và tra cứu bằng Reflection | Classpath, class loader, Java language access | Kiểm tra classloader, tên binary, visibility |
| JVM với JPMS named modules | Có Reflection nhưng phụ thuộc module graph | `reads`, `exports`/`opens` và quyền member | API public, `opens` có chọn lọc, `MethodHandles.Lookup` hợp lệ |
| JVM với `jlink` custom runtime | Reflection vẫn hoạt động cho các lớp được đưa vào | Không có module cần thiết trong runtime image; vẫn có JPMS | Bao gồm module cần thiết lúc tạo runtime |
| JVM với CDS/AppCDS | Reflection vẫn theo quy tắc JVM/JPMS | Archive chủ yếu tối ưu tải và chia sẻ metadata | Không tự suy ra bị hạn chế Reflection |
| GraalVM Native Image | Hỗ trợ Reflection trên các thành phần được phân tích/đăng ký | Phân tích *closed world*, reachability metadata, ranh giới runtime native | Đăng ký đúng class/member hoặc tái cấu trúc static |
| Spring AOT / native | Tạo cấu hình và mã cần thiết ở build time | Quyết định bean/profile/scan thường đã cố định trước khi chạy | `RuntimeHints`, AOT processor, static bean registration |
| Runtime sandbox/tùy biến | Tùy nền tảng/chính sách cụ thể | Có thể hạn chế nạp bytecode, dynamic proxies, quyền truy cập | Đọc contract nền tảng, viết integration test đúng đích |

`javac` dịch `.java` thành `.class` **không làm Reflection biến mất**. `jlink` dựng một runtime gồm các module được chọn; CDS lưu trữ một phần trạng thái lớp để khởi động nhanh hơn. Cả hai khác với *closed-world native compilation*.

## 4. Vì sao Native Image cần biết Reflection từ trước?

GraalVM Native Image phân tích ứng dụng tại **thời điểm build** để xác định thành phần có thể được sử dụng và đưa thành phần cần thiết vào executable. Một lệnh trực tiếp như:

~~~java
new java.util.ArrayList<String>();
~~~

cho phép công cụ nhìn thấy loại cần dùng. Một lệnh động lại khó dự đoán hơn:

~~~java
String className = args[0];
Class<?> type = Class.forName(className);
Object value = type.getDeclaredConstructor().newInstance();
~~~

Khi build, `args[0]` có thể chưa được biết. Công cụ không thể mặc nhiên giữ **mọi class và constructor** của ứng dụng cùng mọi dependency; làm vậy vừa tốn tài nguyên vừa trái mục tiêu tối ưu kích thước.

Đối với các lời gọi Reflection có đối số **hằng hoặc có thể suy luận**, Native Image có thể tính được phần tử cần thiết lúc build. Những phần không suy ra được cần **reachability metadata**. GraalVM hiện đại có thể cho phép cung cấp metadata qua file `reachability-metadata.json`, qua phân tích mã, cấu hình thư viện, tracing agent hoặc API hỗ trợ.

**Không nên khẳng định “hễ dùng `Class.forName` thì Native Image sẽ lỗi”.** Với tên hằng, hoặc khi framework đã cung cấp metadata, lời gọi có thể chạy tốt. Ngược lại, không nên dựa vào kết quả thành công của **một input** để kết luận các tên lớp động khác cũng được đóng gói đầy đủ.

## 5. Ví dụ Java 17 chạy trên JVM: chọn implementation bằng tên lớp

Tạo file `ReflectionModesDemo.java`:

~~~java
public class ReflectionModesDemo {
    public interface Task {
        String run();
    }

    public static class Alpha implements Task {
        public Alpha() {}

        @Override
        public String run() {
            return "alpha";
        }
    }

    public static class Beta implements Task {
        public Beta() {}

        @Override
        public String run() {
            return "beta";
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Pass binary class name");
        }

        Class<? extends Task> type =
                Class.forName(args[0]).asSubclass(Task.class);
        Task task = type.getDeclaredConstructor().newInstance();

        System.out.println("type=" + type.getName());
        System.out.println("result=" + task.run());
    }
}
~~~

Đây là chương trình **độc lập**, gồm `Task` và hai implementation là member class bên trong `ReflectionModesDemo`. Tên nhị phân của member class dùng dấu `$`, không dùng tên canonical dấu chấm.

Trên hệ thống có JDK 17+, chạy trong thư mục chứa source:

~~~bash
javac --release 17 ReflectionModesDemo.java
java ReflectionModesDemo 'ReflectionModesDemo$Alpha'
java ReflectionModesDemo 'ReflectionModesDemo$Beta'
~~~

Với **PowerShell**, dùng dấu nháy đơn cho đối số có `$` như ví dụ để tránh việc shell mở rộng tên biến.

Kết quả lệnh gọi Alpha:

~~~text
type=ReflectionModesDemo$Alpha
result=alpha
~~~

Kết quả lệnh gọi Beta:

~~~text
type=ReflectionModesDemo$Beta
result=beta
~~~

**Đã kiểm chứng:** chương trình trên được biên dịch bằng `javac --release 17` và chạy hai trường hợp trên OpenJDK 21, kết quả khớp chính xác. `Class.forName` tìm lớp, `asSubclass(Task.class)` kiểm tra contract, `getDeclaredConstructor().newInstance()` tạo đối tượng, và lời gọi cuối cùng là **dispatch interface thông thường**. Kiểm tra bằng `asSubclass` không thể thay thế quyền truy cập constructor hoặc cơ chế đăng ký member của Native Image.

## 6. Xây dựng Native Image: cần metadata gì?

Chương trình ví dụ nhận tên class từ tham số runtime, nên khi biên dịch native cần bảo đảm hai kiểu `Alpha` và `Beta` cùng các constructor mà Reflection gọi được ghi nhận.

Với **định dạng metadata hiện đại** của GraalVM, tạo file:

`out/META-INF/native-image/demo/reflection/reachability-metadata.json`

~~~json
{
  "reflection": [
    {
      "type": "ReflectionModesDemo$Alpha",
      "allDeclaredConstructors": true
    },
    {
      "type": "ReflectionModesDemo$Beta",
      "allDeclaredConstructors": true
    }
  ]
}
~~~

`allDeclaredConstructors` cấp khả năng tìm và gọi các constructor được khai báo của class tương ứng trong native binary. Nó **không nâng quyền Java** cho constructor private. Trong chương trình, cả hai constructor đều public và không cần `setAccessible(true)`. Gói metadata này không cần khai báo reflective invocation cho `run()` vì lời gọi `task.run()` đi qua interface được compiler biết trước.

Metadata trên khá rộng đối với constructor; nếu dự án lớn, nên chọn chính xác member thực sự cần dùng theo schema và công cụ của phiên bản GraalVM đang chạy. Tên class trong JSON phải là **binary name đầy đủ**: member class dùng `$`; class có package thì thêm tiền tố package.

Để build demo, cần một **GraalVM có công cụ `native-image`**, toolchain native phù hợp hệ điều hành và Java version tương thích. Trong thư mục chứa source, có thể làm:

~~~bash
mkdir -p out/META-INF/native-image/demo/reflection
javac --release 17 -d out ReflectionModesDemo.java
# Ghi JSON bên trên vào:
# out/META-INF/native-image/demo/reflection/reachability-metadata.json
native-image -cp out ReflectionModesDemo reflection-modes-demo
./reflection-modes-demo 'ReflectionModesDemo$Alpha'
./reflection-modes-demo 'ReflectionModesDemo$Beta'
~~~

Lệnh `mkdir -p` dùng shell Unix. Trên PowerShell, tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force out\META-INF\native-image\demo\reflection | Out-Null
~~~

Sau khi ghi JSON và biên dịch Java theo cùng các tham số, lệnh build native có thể dùng:

~~~powershell
native-image -cp out ReflectionModesDemo reflection-modes-demo
.\reflection-modes-demo.exe 'ReflectionModesDemo$Alpha'
.\reflection-modes-demo.exe 'ReflectionModesDemo$Beta'
~~~

**Kết quả mong muốn** của hai native run là giống JVM `type=...` và `result=...` ở mục 5. Đây là **kịch bản kiểm chứng đề xuất, chưa thực thi native build trong bài này**. Bản GraalVM hoặc cách đóng gói hiện hữu có thể dùng schema metadata khác: bản cũ thường dùng `reflect-config.json` với cấu trúc một mảng có trường `name`; **không thay lẫn hai định dạng một cách tùy ý**. Luôn xác minh tài liệu đúng phiên bản công cụ và metadata thực sự được đưa vào classpath tại thời điểm build.

## 7. Khi thiếu metadata thì lỗi có thể biểu hiện ra sao?

Nếu không có thông tin cần thiết và Native Image cũng không thể suy ra access từ mã:

- `Class.forName(runtimeName)` có thể thất bại do lớp không được giữ lại hoặc không được đăng ký cho dạng truy cập ấy.
- `getDeclaredConstructor`, `getDeclaredMethod`, `getDeclaredField` hoặc `newInstance` có thể thất bại vì member không được cho phép truy vấn/gọi qua Reflection.
- Tùy phiên bản và chế độ kiểm tra, có thể thấy `ClassNotFoundException`, `NoSuchMethodException`, `MissingReflectionRegistrationError` hoặc chẩn đoán khác. **Không có một loại exception duy nhất được bảo đảm cho mọi thiếu sót metadata.**
- Mã có `catch (Exception)` có thể che mất một phần triệu chứng. Một số lỗi về thiếu đăng ký là `Error` chứ không phải `Exception`; đừng bắt `Throwable` đại trà rồi im lặng tiếp tục.

Cũng cần kiểm tra **nguyên nhân không liên quan metadata**: sai binary name, thiếu dependency khi build native, API private không accessible, lệch version thư viện, hoặc class khởi tạo static không thành công.

Trên các bản GraalVM hỗ trợ, `--exact-reachability-metadata` bật chế độ báo thiếu registration rõ hơn. Khi chạy native binary, `-XX:MissingRegistrationReportingMode=Warn` hoặc `Exit` có thể giúp tìm truy cập chưa được đăng ký. Các flag này **phụ thuộc phiên bản**; kiểm tra tài liệu của runtime thực tế trước khi đưa vào CI.

## 8. Tracing agent: thu thập Reflection thực sự phát sinh

Trong hệ sinh thái GraalVM, tracing agent có thể theo dõi một lần chạy **trên JVM** và ghi metadata cho Reflection, resources, proxy, JNI và các tính năng động liên quan. Một dạng lệnh điển hình (cần GraalVM/JDK có agent tương thích):

~~~bash
java -agentlib:native-image-agent=config-output-dir=generated-config \
  ReflectionModesDemo 'ReflectionModesDemo$Alpha'
~~~

Agent ghi cấu hình cho các thao tác nó **quan sát được**. Nhưng nếu chỉ chạy Alpha, không có gì bảo đảm metadata cho Beta cũng được thu thập. Hãy thiết kế **test matrix bao phủ tất cả đường đi động**, gồm các plugin tùy cấu hình, kiểu dữ liệu, nhánh lỗi và biến thể môi trường.

Quy trình tốt hơn là:

1. Thu thập metadata qua các ca chạy đại diện.
2. Review file đã sinh; loại bỏ đăng ký thừa và bổ sung nhánh chưa chạy.
3. Gộp metadata thành đầu vào build có kiểm soát phiên bản.
4. Build native và chạy test với chính binary đó.
5. Tái chạy mỗi khi cập nhật framework, thư viện hoặc phiên bản GraalVM.

Agent là **công cụ khám phá**, không tự chứng minh đã bao phủ mọi cấu hình runtime mà hệ thống có thể gặp.

## 9. Reflection không phải loại dynamic feature duy nhất

Một hệ thống có thể qua được bước đọc annotation nhưng vẫn lỗi khi làm việc với thứ khác. Đối chiếu nhu cầu:

| Tính năng động | JVM bình thường | Native Image / AOT cần xem xét |
| --- | --- | --- |
| `Class.forName` theo input | Tìm class còn trên classpath và được loader thấy | Class có được giữ lại/đăng ký không? |
| `Method.invoke`/constructor Reflection | Tra cứu và kiểm tra Java access | Member có metadata cho query/invoke không? |
| `getDeclaredAnnotations` và đọc giá trị | Metadata annotation nếu `RetentionPolicy.RUNTIME` | Annotation metadata/kiểu liên quan còn được giữ không? |
| `Proxy.newProxyInstance` | Sinh JDK proxy theo interface runtime | Interface/proxy combination có được hỗ trợ/đăng ký không? |
| Sinh bytecode mới bằng thư viện | JVM có thể nạp class mới khi công cụ và quyền cho phép | Native Image không tương đương classloading JVM mở; cần phương án sinh sẵn hoặc hỗ trợ riêng |
| Tải resource theo tên | Đọc resource có mặt trong classpath | Resource có được đóng gói/đăng ký không? |
| Serialization dựa trên Reflection | Thường truy cập nhiều constructor/field ẩn | Metadata serialization và reflection tương ứng |
| JNI hoặc truy cập native | Nhiều class/member được tra cứu từ native code | Metadata JNI và khả năng liên kết native code |

Với **dynamic proxy**, không chỉ quan tâm class của handler: **danh sách interface và thứ tự** cũng mang ý nghĩa. Với resource, Reflection metadata **không tự thay thế** resource metadata. Với `ServiceLoader`, cần kiểm tra provider được phát hiện và đóng gói đúng trên native target. Mỗi cơ chế có vùng đăng ký riêng; đừng cấu hình `allDeclaredMethods` cho toàn bộ ứng dụng như một cách giải quyết chung.

## 10. Một giới hạn khác: JPMS và deep reflection

Ngay cả khi chạy trên **HotSpot JVM đầy đủ**, named module vẫn có ranh giới đóng gói.

Giả sử:

~~~java
// module-info.java của thư viện
module data.core {
    exports demo.api;
}
~~~

`exports demo.api;` cho phép code ở module đọc được `data.core` sử dụng **API public** ở package đó. Nó **không cấp quyền** cho một module khác gọi private field/method bằng `setAccessible(true)`.

Nếu một framework ở module `data.client` cần deep reflection vào `demo.api`, module sở hữu có thể mở có chọn lọc:

~~~java
module data.core {
    exports demo.api;
    opens demo.api to data.client;
}
~~~

Hoặc khi chạy JVM, nếu có cơ sở bảo mật và vận hành phù hợp:

~~~bash
java --add-opens data.core/demo.api=data.client \
  --module-path mods -m data.client/demo.client.Main
~~~

Trong PowerShell, viết cùng lệnh một dòng:

~~~powershell
java --add-opens data.core/demo.api=data.client --module-path mods -m data.client/demo.client.Main
~~~

Lưu ý:

- `exports` cho dùng public API; `opens` cho phép deep reflection vào package được mở.
- Việc module gọi **đọc được module đích** vẫn quan trọng để làm việc với kiểu/API tương ứng.
- `--add-opens` là flag mở package, không phải cơ chế đăng ký reachability cho Native Image.
- `trySetAccessible()` cho biết việc bật quyền có thành công hay không; `setAccessible(true)` có thể ném `InaccessibleObjectException`.
- `MethodHandles.privateLookupIn(...)` có yêu cầu lookup mode và quyền module riêng, không phải cách bỏ qua hoàn toàn `opens`.

**Chẩn đoán dựa vào lỗi:** `InaccessibleObjectException` thường gợi ý bị giới hạn truy cập JPMS; lỗi thiếu metadata trên native binary thường gợi ý cấu hình reachability; `ClassNotFoundException` còn có thể do đường dẫn lớp/sai tên và cần truy nguyên.

## 11. Spring AOT: cấu hình được quyết định trước thời điểm chạy

Spring có khả năng **Ahead-of-Time processing** để phân tích `ApplicationContext`, tạo mã khởi tạo bean và sinh `RuntimeHints` cho những thao tác động cần thiết. Một số thứ trước đây do classpath scanning hoặc runtime introspection quyết định nay cần **biết đủ thông tin khi build**.

Chẳng hạn, trong Spring AOT:

- classpath và tập bean được phân tích từ build-time environment; thêm JAR mới vào runtime không nhất thiết làm AOT context khám phá ra bean mới;
- các điều kiện như `@Profile` và `@Conditional` có thể được xác định trong AOT processing; đổi cấu hình runtime không luôn thay đổi tập bean như cách chạy JVM thông thường;
- mã AOT có thể dùng lời gọi constructor/factory trực tiếp thay cho Reflection;
- nếu thư viện tùy biến vẫn phải truy cập member bằng Reflection, hãy đóng góp **`RuntimeHints`** cho đúng type/member.

Một ví dụ lớp registrar trong dự án Spring Framework hỗ trợ AOT:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class TaskHints implements RuntimeHintsRegistrar {
    public static class PluginTask {
        public PluginTask() {}
    }

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
                PluginTask.class,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS);
    }
}
~~~

Đây là **một file Java dùng Spring Framework**, không thuộc ví dụ JDK thuần ở mục 5; cần dependency Spring AOT trên classpath. Để engine biết registrar, có thể gắn `@ImportRuntimeHints(TaskHints.class)` lên một bean/cấu hình phù hợp hoặc đăng ký theo cơ chế `META-INF/spring/aot.factories` được tài liệu Spring hỗ trợ. Mục đích là nói rõ constructor nào sẽ được gọi động.

Spring thường tự sinh nhiều hints cho các thành phần framework mà engine phân tích được; **không đăng ký thủ công trùng lặp mọi bean**. Tập trung vào plugin, conversion, library reflection hoặc loại dữ liệu không được engine suy ra từ bean graph. `RuntimeHintsPredicates` và các công cụ test Runtime Hints của Spring giúp kiểm tra phần đăng ký.

## 12. Kịch bản so sánh hành vi cần chạy trong CI

Hãy giữ **cùng một contract đầu vào/đầu ra** rồi kiểm tra trên từng môi trường; không chỉ đo xem ứng dụng có khởi động thành công.

| Ca kiểm thử | JVM classpath | JVM JPMS hạn chế | Native Image có metadata |
| --- | --- | --- | --- |
| Chọn `Alpha` bằng tên nhị phân | Mong đợi `alpha` | Mong đợi nếu class/module accessible | Mong đợi `alpha` nếu đã đăng ký |
| Chọn `Beta` (nhánh khác) | Mong đợi `beta` | Phụ thuộc module | Phải có metadata cho Beta |
| Tìm public constructor | Thường thành công nếu class tồn tại và accessible | Cần đúng module access | Cần member được giữ/đăng ký |
| Truy cập private field từ module khác | Có thể bị từ chối | Dễ bị `InaccessibleObjectException` khi không `opens` | Vừa cần đăng ký metadata, vừa cần quyền phù hợp |
| Tải class/JAR mới sau khi tiến trình chạy | Có thể qua class loader | Có thêm giới hạn module/loader | Không giả định có thể nạp bytecode hoàn toàn mới |
| Đọc resource động | Nếu resource có mặt | Nếu resource có mặt và cho phép | Phải được đóng gói/đăng ký |
| Dynamic proxy theo cấu hình | JVM có thể tạo lớp proxy | Có thể cần xét quyền module của interface | Cần cấu hình/hỗ trợ proxy phù hợp |

**Bộ kiểm thử tối thiểu:**

1. Chạy trên JVM classpath thông thường với toàn bộ tên lớp có thể chọn.
2. Nếu dự án có JPMS, chạy trên module path và thử quyền `opens`, cả tình huống thành công và bị từ chối.
3. Build Native Image **từ đúng commit, dependency và metadata** sẽ phát hành; chạy binary với ít nhất hai nhánh dynamic input độc lập.
4. Nếu dùng Spring AOT, kiểm tra build-time profile/condition, những bean động và custom Runtime Hints.
5. So sánh loại lỗi, cause, stdout/return value và side effect; lưu log có tên binary, classloader/module và version native-image.

Điểm cốt lõi: **JVM test pass chưa chứng minh Native Image tương thích**. Trái lại, lỗi trên native không mặc nhiên là bug của Java Reflection: có thể do thiếu metadata hoặc giả định sai về những quyết định được đưa lên build time.

## 13. Khi nên thay Reflection bằng thiết kế tĩnh?

Reflection đem lại khả năng mở rộng, nhưng hệ thống AOT càng dễ phân tích khi loại thực thi/metadata được chỉ định rõ ràng.

Các lựa chọn nên cân nhắc:

- **Interface + factory tường minh:** chọn các implementation đã biết, khởi tạo bằng code; compiler/AOT dễ theo dõi call graph.
- **Constructor injection:** cung cấp dependency qua constructor thay vì quét và sửa private field.
- **ServiceLoader với providers xác định trước:** phù hợp khi quy tắc provider của target runtime và build plugin được kiểm chứng; không xem nó là bảo đảm tự động cho JAR nạp sau build.
- **Generated registry tại build time:** annotation processor hoặc AOT step sinh map tên → factory thay cho runtime classpath scan.
- **MethodHandle/VarHandle:** hữu ích để tối ưu đường gọi khi đã có quyền và handle; nhưng **không bảo đảm vượt rào Native Image metadata hoặc JPMS**.
- **Reflection + hints** khi sự linh hoạt thực sự cần: đăng ký đúng lớp/member và kiểm tra native binary trong CI.

Ví dụ thay tìm lớp động bằng factory rõ ràng:

~~~java
import java.util.Map;
import java.util.function.Supplier;

public class StaticTaskFactoryDemo {
    interface Task { String run(); }
    static class Alpha implements Task {
        public String run() { return "alpha"; }
    }
    static class Beta implements Task {
        public String run() { return "beta"; }
    }

    public static void main(String[] args) {
        Map<String, Supplier<Task>> factories = Map.of(
                "alpha", Alpha::new,
                "beta", Beta::new);
        String key = args.length == 0 ? "alpha" : args[0];
        Supplier<Task> factory = factories.get(key);
        if (factory == null) {
            throw new IllegalArgumentException("Unknown task: " + key);
        }
        System.out.println(factory.get().run());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 StaticTaskFactoryDemo.java
java StaticTaskFactoryDemo alpha
java StaticTaskFactoryDemo beta
~~~

Kết quả mỗi lần gọi lần lượt là:

~~~text
alpha
~~~

~~~text
beta
~~~

Ở đây compiler thấy trực tiếp `Alpha::new`, `Beta::new` và không cần `Class.forName` hay reflective constructor invocation. Đánh đổi là không thể tự thêm implementation hoàn toàn mới chỉ bằng thay đổi chuỗi cấu hình; muốn hỗ trợ loại mới, cần sinh lại registry hoặc build lại binary.

## 14. Lỗi chẩn đoán thường gặp

| Dấu hiệu | Điều cần phân biệt | Cách xử lý thực tế |
| --- | --- | --- |
| `ClassNotFoundException` | Sai tên, thiếu classpath/module, hoặc class không có trong Native Image | Xác minh tên binary, classpath khi build, metadata |
| `NoSuchMethodException` | Sai signature, member bị lược bỏ trong native, hoặc API đổi version | Kiểm tra descriptor, method/constructor registration |
| `InaccessibleObjectException` | JPMS đóng package với deep reflection | API public hoặc `opens` đúng package/module |
| `IllegalAccessException` | Access check không qua | Kiểm tra visibility/module/lookup context |
| `MissingReflectionRegistrationError` | Native Image thiếu phần tử được yêu cầu | Thêm hints/metadata phù hợp và chạy native test |
| Proxy phát sinh lỗi | Interface combination hoặc AOT proxy metadata chưa được suy ra | Đối chiếu interface list/order và đăng ký proxy |
| Resource có trên JVM, mất trong native | Resource chưa vào image | Resource metadata hoặc build plugin phù hợp |
| Bean có trên JVM, vắng trên Spring AOT | Build-time graph/conditions khác runtime assumption | Kiểm tra AOT logs, profile/conditions, explicit bean definition |
| Biên dịch native thành công nhưng runtime lỗi | Build pass không bao phủ mọi đường đi động | Test đủ input/configuration và exact registration diagnostics |

Bắt ngoại lệ đúng phạm vi, log nguyên nhân gốc. Không xử lý bằng cách mở toàn bộ JDK package, giữ mọi class/method, hay nuốt mọi exception; các cách đó có thể che lỗi và làm tăng kích thước/tấn công bề mặt của ứng dụng.

## 15. Lưu ý về hiệu năng và an toàn

Native Image thường hướng tới **thời gian khởi động nhanh và footprint nhỏ hơn**, đổi lại có giới hạn nhất định về tính linh hoạt của những thành phần được phép xuất hiện lúc chạy. Tuy nhiên, tốc độ gọi `Method.invoke` không tự động nhanh hơn chỉ vì đã build native; muốn so sánh phải đo cả warmup, throughput, peak RSS, startup và workload thực tế.

- Đăng ký Reflection càng rộng (ví dụ `allDeclaredMethods` cho số lượng class lớn) càng có thể tăng kích thước binary và giữ metadata thừa.
- Đừng coi metadata như một permission check. Nếu một đoạn code được phép truy cập private bằng Java access và metadata đã cho phép, nó có thể trở thành kênh thao tác nhạy cảm.
- Khi dùng tên class nhận từ input không tin cậy, giới hạn danh sách implementation được phép. Cả JVM lẫn Native Image không làm `Class.forName(userInput)` tự trở thành an toàn.
- Một ứng dụng cấu hình plugin động cần đánh giá **khả năng thêm logic mới sau build**. Native binary có *closed-world assumption* khác JVM đầy đủ.
- Nếu quyền truy cập không cần dynamic dispatch, ưu tiên code tường minh giúp dễ audit và dễ tối ưu.

## 16. Câu hỏi tự kiểm tra

1. `javac` biên dịch `.java` trước khi chạy có khiến `Class.forName` không hoạt động? **Không.** JVM còn classpath/module path và cơ chế nạp lớp khi chạy.
2. Vì sao Native Image thường cần reachability metadata? Vì phân tích build-time không thể biết đầy đủ những class/member sẽ được chọn từ input runtime tùy ý.
3. `Class.forName("java.lang.String")` luôn đòi JSON metadata riêng? **Không.** Nhiều lời gọi với input hằng có thể được Native Image suy ra.
4. Có `--add-opens` thì không cần khai báo reflection metadata nữa? **Sai.** `opens` xử lý quyền module, metadata xử lý tính hiện diện/khả năng reflection trong image.
5. Nếu tracing agent chỉ chạy Alpha, nó có tự chứng minh Beta đã được bao phủ? **Không.** Cần chạy mọi nhánh hoặc khai báo bổ sung.
6. `new Alpha()` khác `Class.forName(name).getDeclaredConstructor().newInstance()` ở điểm nào với AOT? Lựa chọn class/constructor ở biểu thức đầu là **tĩnh**; biểu thức thứ hai có thể phụ thuộc dữ liệu runtime.
7. Khi Spring AOT không suy ra việc truy cập Reflection từ custom code, dùng gì? **`RuntimeHintsRegistrar` và `RuntimeHints`** (hoặc tích hợp hints/AOT processor phù hợp).
8. Nếu JVM test pass nhưng native binary báo thiếu member, bước tiếp theo? Xác nhận class/member/đường đi thực tế, metadata đúng phiên bản, rồi build và thử lại chính binary.
9. Named module có `exports` public API nhưng không `opens`, dùng `setAccessible(true)` với private field từ module khác được không? **Không được bảo đảm**; thông thường phải mở package cho module caller.
10. Cách nào phù hợp hơn nếu chỉ có hai task Alpha/Beta và không có yêu cầu thêm plugin tùy ý? **Interface + static factory/registry** có thể đơn giản, an toàn và dễ AOT hơn.

## 17. Tài liệu chính thức để đối chiếu phiên bản

- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/) (cấu trúc `reachability-metadata.json`, reflection và tùy chọn chẩn đoán).
- [GraalVM Native Image — Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/metadata/AutomaticMetadataCollection/) (thu thập metadata theo ca chạy; đối chiếu đường dẫn tài liệu với bản phát hành thực tế).
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html) (hạn chế build-time graph, `RuntimeHints`, `@ImportRuntimeHints`, test).
- [Java SE 17 — Class.forName và Reflection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html).
- [OpenJDK JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403).

**Ghi nhớ:** Để so sánh Reflection trên các môi trường, kiểm tra riêng **class/member có trong runtime hay không**, **quyền truy cập có đủ hay không**, và **hành vi có bị cố định ở build time hay không**. Trên Native Image, bổ sung metadata chính xác và test chính binary; trên JPMS, làm rõ `reads`/`exports`/`opens`; còn khi có thể, dùng registry/factory tĩnh để tránh những nhu cầu reflection không cần thiết.