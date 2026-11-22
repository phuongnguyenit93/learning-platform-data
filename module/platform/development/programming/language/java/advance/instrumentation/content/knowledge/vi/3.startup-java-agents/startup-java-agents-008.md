# Launcher-Agent-Class trong executable JAR và vai trò `agentmain`

## 1. Mục tiêu và bối cảnh

Java Instrumentation API (`java.lang.instrument`) cho phép một **Java agent** quan sát, biến đổi bytecode khi class được nạp, hoặc làm việc với một số class đã được nạp thông qua các khả năng `Instrumentation` được JVM hỗ trợ. Cách agent được **khởi chạy** quyết định tên phương thức vào (`premain` hay `agentmain`), thời điểm phương thức đó chạy và cách đóng gói JAR.

Trong một **executable JAR** chạy bằng `java -jar application.jar`, manifest có thể khai báo:

```text
Main-Class: com.example.Main
Launcher-Agent-Class: com.example.StartupAgent
```

`Main-Class` cho Java launcher biết entry point của **ứng dụng**. `Launcher-Agent-Class` chỉ định **lớp agent được đóng gói trong chính executable JAR**; JVM sẽ gọi phương thức **`agentmain` của lớp agent trước khi gọi `main` của ứng dụng**.

Điều cần nhớ: dù agent này chạy **ngay khi khởi động**, entry point của nó là **`agentmain`**, không phải `premain`. Tên `agentmain` cũng được dùng cho agent attach vào JVM đang chạy, nhưng đây là **hai con đường khởi chạy khác nhau**.

Tính năng này đã được mô tả từ Java 9; bài thực hành bên dưới dùng Java 17+.

## 2. Cơ chế JVM đọc `Launcher-Agent-Class`

Khi dùng cơ chế executable JAR chuẩn, dòng chảy có thể hình dung như sau:

```text
java -jar application.jar [application arguments]
         |
         v
Java launcher đọc META-INF/MANIFEST.MF
         |
         +-- Main-Class: tên lớp chạy ứng dụng
         |
         +-- Launcher-Agent-Class: tên lớp agent đi cùng JAR
                   |
                   v
             JVM nạp lớp agent
                   |
                   v
             agentmain("", Instrumentation)
                   |
             thiết lập transformer / state / hook cần thiết
                   |
             agentmain trả về
                   |
                   v
             Main.main(String[] args)
```

Đây là sơ đồ luồng logic, không phải khẳng định mọi lớp hệ thống đều chỉ được JVM nạp sau `agentmain`. Một số lớp JVM và thư viện có thể đã được tải trong quá trình khởi động. Bảo đảm quan trọng là **`agentmain` được gọi trước lúc gọi phương thức `main` của ứng dụng**.

Điều kiện cơ bản:

1. Chạy **JAR executable bằng cơ chế `java -jar`**; JAR chứa main manifest với `Main-Class` hợp lệ.
2. Trong cùng **main section** của `META-INF/MANIFEST.MF` có `Launcher-Agent-Class` trỏ tới **tên nhị phân đầy đủ** của lớp agent, ví dụ `com.example.StartupAgent`; không ghi đuôi `.class`, không ghi đường dẫn kiểu `com/example/StartupAgent.class`.
3. Lớp agent và những phụ thuộc cần dùng lúc khởi động phải được class loader phù hợp tìm thấy. Với ví dụ JAR chuẩn, đặt lớp tại đúng đường dẫn tương ứng trong JAR.
4. Lớp agent cung cấp phương thức `public static void agentmain(...)` hợp lệ.
5. `agentmain` khởi tạo các thành phần cần thiết rồi **trả về** để JVM tiếp tục chạy ứng dụng.

Nếu manifest không có `Launcher-Agent-Class` thì JVM không tự khởi chạy loại agent này. Nếu manifest chỉ có `Launcher-Agent-Class` mà thiếu `Main-Class`, JAR không đủ điều kiện khởi chạy như executable JAR chuẩn.

## 3. Hợp đồng của `agentmain` ở chế độ launcher

JVM ưu tiên tìm chữ ký:

```java
public static void agentmain(String agentArgs,
                             java.lang.instrument.Instrumentation inst)
```

Nếu lớp agent **không định nghĩa chữ ký hai tham số**, JVM thử phương thức thay thế:

```java
public static void agentmain(String agentArgs)
```

Nếu có cả hai overload, JVM ưu tiên bản **hai tham số**. Phương thức phải là `public static`, trả về `void`; đừng thay bằng `main`, `premain`, phương thức instance, hoặc sai tên/thứ tự kiểu tham số.

### Giá trị `agentArgs`

**Đối với `Launcher-Agent-Class`, `agentArgs` luôn là chuỗi rỗng `""`.** Đây là quy tắc của cơ chế launcher, không phải giá trị lấy từ các đối số phía sau tên JAR.

Ví dụ:

```bash
java -jar application.jar user-1 debug
```

- `main(String[] args)` của ứng dụng nhận hai phần tử `"user-1"` và `"debug"`.
- `agentmain(String agentArgs, ...)` của launcher agent nhận `""`, **không nhận** `"user-1 debug"`.
- Không có cú pháp chính thức kiểu `Launcher-Agent-Class=trace` để truyền tùy chọn qua đối số `-jar`. Nếu cần cấu hình agent nhúng, có thể dùng system property, environment variable hoặc cấu hình riêng do ứng dụng/agent định nghĩa; hãy xác định cách đọc và thứ tự khởi tạo rõ ràng.

### Vai trò của `Instrumentation`

Đối tượng `Instrumentation` là API do JVM cấp, thường dùng để:

- Đăng ký hoặc hủy đăng ký `ClassFileTransformer` bằng `addTransformer`/`removeTransformer`, để xử lý các class được nạp sau khi transformer hoạt động.
- Kiểm tra khả năng `isRetransformClassesSupported()`, `isRedefineClassesSupported()`; nếu được hỗ trợ và đáp ứng điều kiện, gọi `retransformClasses`/`redefineClasses`.
- Đọc thông tin lớp đã nạp (`getAllLoadedClasses`), kiểm tra khả năng sửa lớp (`isModifiableClass`), hỗ trợ module/class-loader search theo API tương ứng.

Không phải mọi VM đều hỗ trợ mọi khả năng. Những manifest capability như `Can-Retransform-Classes: true` và `Can-Redefine-Classes: true` có thể cần thiết, nhưng **không bảo đảm** tính năng thực sự được VM hỗ trợ; luôn kiểm tra API trước khi dùng.

Với chữ ký **một tham số** (`agentmain(String)`), agent không trực tiếp nhận đối tượng `Instrumentation`; cách đó phù hợp khi chỉ làm bước khởi tạo khác, không cần các API instrumentation.

### Lỗi khởi tạo có thể làm ứng dụng dừng hẳn

Nếu lớp agent không được nạp, thiếu phương thức `agentmain` hợp lệ, hoặc `agentmain` ném ngoại lệ/lỗi không bắt, **JVM abort trước khi gọi `main`**. Vì vậy code trong `agentmain` nên làm khởi tạo thiết yếu, xử lý lỗi có chủ đích và không phụ thuộc vào trạng thái chỉ được thiết lập trong `main`.

## 4. Ví dụ chạy được trên Java 17+: agent nhúng tự chạy trước `main`

Ví dụ này chỉ sử dụng Java SE, không cần Maven/Gradle hay thư viện ngoài. Tạo **ba tệp** trong cùng một thư mục:

```text
demo/
├── LauncherAgent.java
├── DemoApp.java
└── manifest.mf
```

Các class ở default package để tập trung vào manifest; dự án thực tế nên dùng package rõ ràng.

### Tệp 1: `LauncherAgent.java`

```java
import java.lang.instrument.Instrumentation;

public final class LauncherAgent {
    private LauncherAgent() {
    }

    public static void agentmain(String agentArgs, Instrumentation inst) {
        System.out.println("[agent] argsEmpty=" + agentArgs.isEmpty());
        System.out.println("[agent] hasInstrumentation=" + (inst != null));

        // Chứng minh phần khởi tạo agent đã chạy trước DemoApp.main.
        System.setProperty("demo.launcher.agent", "ready");
    }
}
```

Giải thích:

- Hàm `agentmain` đúng chữ ký `public static void ... (String, Instrumentation)`.
- `agentArgs.isEmpty()` sẽ là `true` trong cơ chế `Launcher-Agent-Class`.
- `inst` là đối tượng JVM cấp; ví dụ chưa sửa bytecode, chỉ xác minh sự hiện diện của nó.
- System property là cách **minh họa thứ tự chạy**. Không xem đây là một giao thức truyền trạng thái bắt buộc của agent.

### Tệp 2: `DemoApp.java`

```java
public final class DemoApp {
    private DemoApp() {
    }

    public static void main(String[] args) {
        String agentState =
                System.getProperty("demo.launcher.agent", "missing");
        System.out.println("[main] agentState=" + agentState);
        System.out.println("[main] args=" + String.join(",", args));
    }
}
```

Ứng dụng đọc property mà agent thiết lập rồi in đối số do người dùng truyền sau `-jar`.

### Tệp 3: `manifest.mf`

```text
Manifest-Version: 1.0
Main-Class: DemoApp
Launcher-Agent-Class: LauncherAgent

```

Manifest nằm trong **main section** của JAR; ví dụ dùng các tên class không có package. Nếu class có package, giá trị phải là tên đầy đủ kiểu `example.agent.LauncherAgent`.

**Lưu ý định dạng manifest:** mỗi thuộc tính một dòng `Name: value`, có dấu cách sau dấu hai chấm; tệp nên có **dòng trống kết thúc**. Không thêm cú pháp `.class` hoặc dấu ngoặc cho giá trị `Launcher-Agent-Class`. Lệnh `jar --manifest` sẽ đưa nội dung vào `META-INF/MANIFEST.MF`.

### Biên dịch, đóng gói và chạy

Mở terminal ở thư mục chứa ba tệp. Dùng JDK 17 trở lên có hỗ trợ `--release 17`:

```bash
javac --release 17 LauncherAgent.java DemoApp.java
jar --create --file launcher-demo.jar --manifest manifest.mf LauncherAgent.class DemoApp.class
java -jar launcher-demo.jar alpha beta
```

**Stdout chính xác** từ `java -jar launcher-demo.jar alpha beta` khi chạy ví dụ trên JVM hỗ trợ cơ chế launcher agent:

```text
[agent] argsEmpty=true
[agent] hasInstrumentation=true
[main] agentState=ready
[main] args=alpha,beta
```

Hai dòng `[agent]` xuất hiện **trước** hai dòng `[main]`. Người dùng truyền `alpha beta` cho ứng dụng, nhưng `agentArgs` của agent vẫn rỗng. `javac` và `jar` thông thường không in gì ra stdout nếu thành công.

Để nhìn các entry trong JAR:

```bash
jar --list --file launcher-demo.jar
```

Bạn phải thấy các entry tương ứng `META-INF/MANIFEST.MF`, `LauncherAgent.class` và `DemoApp.class` (ngoài các entry `META-INF/` có thể có).

### Thử đối chứng: khởi chạy như class bình thường

Chạy trong **một tiến trình Java mới**:

```bash
java -cp launcher-demo.jar DemoApp alpha beta
```

Stdout:

```text
[main] agentState=missing
[main] args=alpha,beta
```

Ở đây Java launcher dùng `-cp` và chỉ định trực tiếp `DemoApp`, không dùng cơ chế executable JAR `-jar`. Vì vậy chỉ có metadata `Launcher-Agent-Class` trong JAR **không tự kích hoạt agent**. Một JVM mới cũng không kế thừa system property Java vừa được đặt trong JVM chạy trước đó.

## 5. Từ khởi tạo đơn giản sang instrumentation thực sự

Trong ví dụ trước, `agentmain` chỉ đặt property. Trong hệ thống thực, `agentmain` thường là nơi tạo/truy cập cấu hình, đăng ký transformer và chỉ sau đó cho ứng dụng tiếp tục. Ví dụ đoạn mã **minh họa đặt bên trong phương thức `agentmain(String, Instrumentation)`**, không phải một chương trình Java độc lập:

```java
inst.addTransformer((loader, className, classBeingRedefined,
                     protectionDomain, classfileBuffer) -> {
    if ("com/example/BusinessService".equals(className)) {
        System.out.println("[agent] loading " + className);
    }

    return null; // Quan sát, không thay thế bytecode.
});
```

Ý nghĩa:

- `ClassFileTransformer` nhận tên lớp theo dạng nội bộ có dấu `/`, ví dụ `com/example/BusinessService`; tham số `className` có thể là `null` trong một số tình huống nên dùng so sánh bằng constant như trên.
- `return null` nghĩa là transformer **không thay đổi** bytecode. Muốn biến đổi thật phải trả byte array hợp lệ, bảo toàn các ràng buộc JVM; thường cần thư viện như ASM hoặc Byte Buddy.
- Transformer nhận sự kiện của các class được định nghĩa **sau khi đăng ký**. Đừng suy ra toàn bộ class đã được tải từ trước sẽ đi qua transformer.
- Với lớp đã được tải, `retransformClasses`/`redefineClasses` có điều kiện và ràng buộc khác; phải kiểm tra VM hỗ trợ, quyền và khả năng sửa lớp trước khi gọi.

Sơ đồ thành phần:

```text
LauncherAgent.agentmain("", inst)
            |
            +--> chuẩn bị cấu hình/quan sát
            |
            +--> inst.addTransformer(transformer)
                            |
                            v
                  JVM định nghĩa class mới
                            |
                            v
                  transformer nhận bytes
                            |
                  +---------+---------+
                  |                   |
             trả về null       trả về byte[] mới
             giữ bytecode      dùng bytecode đã sửa
```

**Không nên** thực hiện công việc đồng bộ quá nặng trong `agentmain`. Nếu startup phải có transformer trước khi ứng dụng hoạt động, thực hiện phần đăng ký thiết yếu rồi trả về. Công việc nền cần quản lý vòng đời, thread, lỗi và tài nguyên rõ ràng; nên ưu tiên quan sát/biến đổi tối thiểu để giảm rủi ro ảnh hưởng startup.

## 6. So sánh ba cơ chế khởi chạy Java agent

| Cơ chế | Kích hoạt | Manifest dùng để chỉ định agent | Phương thức được gọi | Thời điểm |
| --- | --- | --- | --- | --- |
| Agent đi cùng executable JAR | `java -jar app.jar` | `Launcher-Agent-Class` trong executable JAR | **`agentmain`** | Trước `Main-Class.main` |
| Agent JAR riêng trên command line | `java -javaagent:agent.jar[=options] ...` | `Premain-Class` trong agent JAR | **`premain`** | Trước application `main` |
| Agent được nạp khi JVM đã chạy | Cơ chế attach/loadAgent do VM cho phép | `Agent-Class` trong agent JAR | **`agentmain`** | Khi agent được nạp động, thường sau `main` |

### Tại sao cùng tên `agentmain` nhưng hành vi lỗi khác?

**Launcher agent:** `agentmain` được gọi **trong giai đoạn JVM khởi động executable JAR**. Nếu không khởi tạo được, JVM **abort**, không đi đến ứng dụng `main`.

**Dynamically attached agent:** `agentmain` cũng được gọi, nhưng JVM **đã chạy**. Theo hợp đồng `java.lang.instrument`, lỗi khởi tạo/ngoại lệ không bắt của agent attach **không làm JVM ứng dụng abort theo cùng cơ chế launcher** (có thể được ghi log); việc tải agent còn chịu chính sách attach và hỗ trợ của từng JVM.

**Command-line agent:** `-javaagent` đòi manifest `Premain-Class`, gọi `premain`, và cũng làm JVM dừng khởi động nếu agent bắt buộc không thể chạy. Chỉ có `Launcher-Agent-Class` **không thay thế** được `Premain-Class` khi dùng `-javaagent`.

**Quan hệ các thuộc tính:**

- `Main-Class`: entry point ứng dụng. Không đồng nghĩa một agent.
- `Launcher-Agent-Class`: agent được nhúng trong JAR mà launcher đang chạy, gọi `agentmain` trước `main`.
- `Premain-Class`: agent được đưa vào bằng `-javaagent`, gọi `premain`.
- `Agent-Class`: agent JAR được nạp vào JVM đã khởi chạy, gọi `agentmain`.
- `Can-Redefine-Classes`, `Can-Retransform-Classes` và `Can-Set-Native-Method-Prefix`: yêu cầu khả năng bổ sung; chúng **không** tự khởi chạy agent.

Nếu một JAR đồng thời khai báo nhiều entry point và ứng dụng sử dụng nhiều con đường khởi chạy, có thể xảy ra **khởi tạo agent nhiều lần**. Tránh giả định init chỉ chạy một lần trong mọi tình huống: cần idempotency hoặc kiểm soát trạng thái rõ ràng.

## 7. Khi nào nên dùng `Launcher-Agent-Class`?

Phù hợp khi:

1. Bạn **kiểm soát executable JAR** và muốn phân phối ứng dụng cùng agent trong một artifact.
2. Muốn agent thiết lập tracing/metric hook/instrumentation trước `main` mà người triển khai không phải thêm flag `-javaagent`.
3. Không cần truyền tùy chọn agent thông qua cú pháp `-javaagent:...=...`; có thể dùng một cơ chế cấu hình khác.
4. Chấp nhận rằng **lỗi agent nhúng có thể chặn ứng dụng khởi động**.

Không phải mọi tệp có đuôi `.jar` đều là executable JAR. Nếu người dùng thực tế chạy một lớp bằng `java -cp ... SomeMain`, launcher sẽ không tự gọi `Launcher-Agent-Class`. Nếu muốn gắn một agent độc lập vào nhiều ứng dụng mà không sửa artifact của chúng, `-javaagent` thường thích hợp hơn.

### Cẩn thận với JAR có nested dependencies / custom launcher

Một JAR **chuẩn** đặt `com/example/StartupAgent.class` ở đường dẫn tương ứng trong archive. Nhưng một số công cụ đóng gói, ví dụ **Spring Boot executable JAR**, đặt class ứng dụng ở `BOOT-INF/classes/` và thư viện ở `BOOT-INF/lib/`; `Main-Class` có thể là `org.springframework.boot.loader.launch.JarLauncher`, còn class ứng dụng nằm trong `Start-Class`.

Khi launcher agent chạy **trước** `main`, không được mặc nhiên cho rằng class chỉ có trong `BOOT-INF/classes/` hoặc JAR lồng bên trong sẽ được **system class loader** tìm thấy. Cơ chế nạp nested JAR của Spring Boot được thiết lập bởi launcher của Spring Boot ở một thời điểm khác. Muốn dùng agent nhúng trong kiểu đóng gói này, phải **kiểm chứng đường dẫn class, class loader và dependencies thực tế**; có thể cần bố trí class agent để được JVM nhìn thấy ngay từ đầu hoặc phân phối agent JAR độc lập bằng `-javaagent`.

Sử dụng tên lớp, đường dẫn, manifest của **artifact sau đóng gói** để kiểm tra, không chỉ nhìn `build.gradle` hoặc mã nguồn.

## 8. Lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra / khắc phục |
| --- | --- | --- |
| `no main manifest attribute` khi `java -jar` | JAR không có `Main-Class` hợp lệ | Kiểm tra main manifest; đóng gói executable JAR đúng |
| `main` chạy nhưng không thấy agent | Thiếu `Launcher-Agent-Class`, hoặc đang chạy bằng `java -cp` | Kiểm tra manifest của đúng artifact và lệnh chạy thực tế |
| JVM dừng trước `main` do không tải được agent | Giá trị `Launcher-Agent-Class` sai tên, class/dependency không ở nơi loader nhìn thấy | Dùng tên nhị phân đầy đủ; kiểm tra class path và bố trí JAR |
| JVM dừng do thiếu phương thức phù hợp | `agentmain` là instance/private, sai tham số, sai kiểu trả về | Định nghĩa `public static void agentmain(String, Instrumentation)` hoặc bản một tham số |
| JVM dừng vì lỗi trong agent | Exception/error thoát khỏi `agentmain` | Log và xử lý lỗi khởi tạo đúng chính sách, tránh phụ thuộc vào `main` |
| Dùng `-javaagent:launcher-demo.jar` nhưng không chạy | Chỉ khai báo `Launcher-Agent-Class`, thiếu `Premain-Class` | Cung cấp agent JAR/manifest có `Premain-Class` và phương thức `premain` nếu dùng `-javaagent` |
| Transformer không tác động lên một class | Class đã được tải trước lúc đăng ký; tên class không khớp; transform trả `null` | Xác minh thời điểm định nghĩa class, tên dạng `com/example/Foo` và transformer được đăng ký |
| `retransformClasses` bị từ chối | VM/agent không có khả năng hoặc class không thể sửa | Kiểm tra `isRetransformClassesSupported()`, `isModifiableClass()` và manifest capability |
| Chạy Spring Boot nested JAR không tìm thấy agent | Lớp agent nằm ở khu vực mà JVM startup loader chưa thấy | Kiểm tra nội dung artifact, loader/manifest, thử đóng gói agent ở vị trí nhìn thấy hoặc dùng `-javaagent` |

Ngoài ra, agent có thể thêm chi phí startup, ảnh hưởng hiệu năng hoặc thay đổi hành vi ứng dụng. Chỉ chạy agent và executable JAR có nguồn gốc đáng tin cậy; bản thân agent có khả năng can thiệp sâu vào bytecode và quá trình nạp class.

## 9. Checklist trước khi phát hành executable JAR có agent nhúng

1. **Manifest:** có `Manifest-Version`, `Main-Class` và `Launcher-Agent-Class` chính xác trong **main section**; tên class dùng cú pháp binary name, không có `.class`.
2. **Đóng gói:** class agent và dependency load-time của nó thực sự được system class loader thấy; test đúng file JAR sau build/shading/repackage.
3. **Entry point:** agent có `public static void agentmain(String, Instrumentation)`; biết rõ launcher luôn truyền `agentArgs = ""` và method phải return.
4. **Cấu hình:** chọn system property/environment/config rõ ràng nếu agent cần tham số; không đọc nhầm `main(args)` thành `agentArgs`.
5. **Khả năng instrumentation:** đăng ký transformer đúng thời điểm, kiểm tra `isRetransformClassesSupported()` hoặc `isRedefineClassesSupported()` trước các thao tác yêu cầu khả năng bổ sung.
6. **Kiểm thử thực tế:** chạy `java -jar packaged-app.jar` trên JVM triển khai, xác nhận agent khởi chạy trước `main`, kiểm tra hành vi khi agent lỗi và mức overhead.
7. **Đường chạy khác:** kiểm tra `java -cp`, script vận hành, container entrypoint và framework launcher; flag hay manifest chỉ có tác dụng nếu **đúng cơ chế khởi chạy**.

## 10. Tự kiểm tra hiểu bài

**Tình huống A:** Manifest có `Main-Class: DemoApp` và `Launcher-Agent-Class: LauncherAgent`. Lệnh `java -jar demo.jar one two` gọi hàm nào trước? `agentArgs` là gì?

**Đáp án:** JVM gọi `LauncherAgent.agentmain("", inst)` trước `DemoApp.main(new String[]{"one", "two"})`, theo hợp đồng launcher. Agent nhận chuỗi rỗng; ứng dụng nhận hai đối số.

**Tình huống B:** Chạy `java -javaagent:demo.jar -jar demo.jar` với JAR chỉ có `Launcher-Agent-Class` mà không có `Premain-Class`. Có dùng được launcher entry point thay cho premain không?

**Đáp án:** Không. `-javaagent` yêu cầu `Premain-Class` cho agent JAR; `Launcher-Agent-Class` chỉ áp dụng cho cơ chế executable JAR, không đáp ứng yêu cầu đó.

**Tình huống C:** Agent chạy qua `Launcher-Agent-Class` ghi log ở `agentmain` rồi ném `IllegalStateException` không bắt. Ứng dụng có vào `main` không?

**Đáp án:** Không. Theo hợp đồng của launcher agent, JVM abort khi `agentmain` không khởi tạo thành công.

**Tình huống D:** Nếu chỉ thay `java -jar demo.jar` bằng `java -cp demo.jar DemoApp`, có còn tự chạy agent nhúng không?

**Đáp án:** Không. Cú pháp `java -cp` không kích hoạt `Launcher-Agent-Class` từ manifest như cơ chế `-jar`.

## 11. Tài liệu chuẩn

- [Oracle Java SE 21 — `java.lang.instrument` package specification](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): ba cơ chế khởi động, chữ ký và lỗi `agentmain`/`premain`, manifest capabilities.
- [Oracle Java SE 21 — JAR File Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html): manifest `Main-Class` và `Launcher-Agent-Class`.
- [Oracle — `jar` command reference](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html): cú pháp `--create`, `--manifest`, `--file`.
- [Spring Boot — Launching Executable JARs](https://docs.spring.io/spring-boot/specification/executable-jar/launching.html): cấu trúc launcher/nested JAR để phân biệt với JAR chuẩn.

**Ghi nhớ:** `Launcher-Agent-Class` nằm trong **executable JAR**, dùng **`agentmain` trước `main`**, truyền **agentArgs rỗng** và có thể làm JVM dừng khởi động nếu agent lỗi; `-javaagent` dùng **`Premain-Class + premain`**, còn dynamic attach dùng **`Agent-Class + agentmain`**.
