# Không dùng class loader để nạp lại chính lớp đang được biến đổi

Trong Java Instrumentation, khi JVM gọi `ClassFileTransformer.transform(...)` để xử lý một lớp, lớp đó **có thể đang ở giữa quá trình được định nghĩa**. Lúc này, transformer đã có **tên nội bộ của lớp** (`className`), **class loader đang định nghĩa nó** (`loader`) và **bytecode đầu vào** (`classfileBuffer`). Transformer **không cần** và **không nên** gọi lại `loader.loadClass(...)` hay `Class.forName(...)` để “nạp lại” chính lớp đang được transform.

Nguyên tắc này thuộc chủ đề **Class loader và helper**: tránh kéo lớp đích quay lại quy trình class loading khi quy trình đó chưa hoàn tất; tách code helper của agent khỏi lớp nghiệp vụ; xử lý bytecode từ dữ liệu JVM đã truyền vào thay vì truy tìm một `Class<?>` mới bằng loader.

Sau bài này, bạn sẽ phân biệt được: **loader được nhận làm thông tin ngữ cảnh** và **loader bị gọi để tải lớp** là hai việc khác nhau; vì sao việc “load lại” có thể dẫn tới reentrancy, vòng phụ thuộc hoặc treo; khi nào `classBeingRedefined` có thể được sử dụng; tại sao một helper nhìn thấy được từ agent chưa chắc nhìn thấy được từ lớp ứng dụng đã instrument; và cách viết một Java agent JDK 17+ có thể chạy thử an toàn.

## 1. Luồng class loading và vị trí của transform callback

Xét ứng dụng cần nạp `lab.app.TargetService`. Một luồng đơn giản hóa:

~~~text
Ứng dụng yêu cầu sử dụng lab.app.TargetService
        |
        v
Class loader tìm bytes định nghĩa lớp
        |
        v
ClassLoader.defineClass(...) hoặc cơ chế tương đương
        |
        v
JVM chạy chuỗi ClassFileTransformer.transform(...)
        |       Tham số đã có:
        |       - className = "lab/app/TargetService"
        |       - loader = class loader của định nghĩa
        |       - classfileBuffer = bytes để xử lý
        |
        v
JVM kiểm tra và định nghĩa lớp từ kết quả cuối
        |
        v
Lớp có thể được liên kết và khởi tạo khi cần
        |
        v
Ứng dụng thực thi code của lớp
~~~

Đây là sơ đồ **khái niệm**, không phải lời hứa rằng mọi JVM thực hiện mọi bước theo đúng trình tự vi mô ở mọi tình huống. Điều **được API bảo đảm** là transformer được gọi trong quá trình định nghĩa/redefine/retransform và **trước khi bytes cuối được xác minh hoặc áp dụng**.

Một lệnh sai trong callback:

~~~java
Class<?> target = loader.loadClass("lab.app.TargetService"); // KHÔNG LÀM
~~~

có thể yêu cầu chính loader đó xử lý lại cái tên mà nó **đang định nghĩa**. Lớp chưa nhất thiết xuất hiện như một `Class<?>` đã được loader ghi nhận. Kết quả phụ thuộc loader/JVM/trạng thái: có thể xuất hiện reentrant loading, một chuỗi phụ thuộc lớp khó kiểm soát, lỗi liên kết hoặc deadlock. **Không khẳng định mọi lần gọi chắc chắn ném cùng một exception**; bản thân yêu cầu load trong thời điểm này mới là vấn đề thiết kế.

### Quy tắc cốt lõi

**Dùng `className` để quyết định có biến đổi lớp hay không; dùng `classfileBuffer` để đọc và sửa bytecode. Không truy ngược lại class loader để lấy chính `Class<?>` đang được định nghĩa.**

Nếu transformer không cần sửa gì, trả `null`. Nếu cần sửa, tạo **mảng byte mới** từ dữ liệu đã nhận, không ghi đè trực tiếp `classfileBuffer`.

## 2. loadClass không phải API “reload class”

Tên `ClassLoader.loadClass(String)` đôi khi khiến người học hiểu rằng mỗi lần gọi sẽ đọc lại file `.class` và tạo ra bản định nghĩa mới. Đó **không phải** hợp đồng của API.

Trong cách triển khai mặc định, `ClassLoader.loadClass(name, resolve)` thường thực hiện:

1. Dùng `findLoadedClass(name)` để tìm một lớp **đã được loader ghi nhận** với tên đó.
2. Nếu chưa có, thử **ủy quyền cho parent loader** theo delegation.
3. Nếu parent không tìm được, thử `findClass(name)` tại loader hiện tại.
4. Có thể liên kết (*resolve*) lớp theo tham số và trả về một `Class<?>`.

Các subclass `ClassLoader` có thể có chiến lược khác (child-first, plugin isolation, module layer, dynamic bytecode), nhưng **không** có cơ chế Java tiêu chuẩn “đưa lớp cũ quay lại trạng thái chưa từng load” chỉ bằng `loadClass`.

### Trước, trong và sau lúc định nghĩa khác nhau

| Thời điểm | Gọi `loader.loadClass(targetName)` có ý nghĩa gì? | Nên làm trong transformer? |
| --- | --- | --- |
| **Trước** khi lớp được yêu cầu load | Có thể bắt đầu tải/định nghĩa lớp | Không dùng như bước chuẩn bị từ callback |
| **Đang** trong callback định nghĩa lớp | Có thể tái yêu cầu chính lớp chưa hoàn tất định nghĩa, tạo phụ thuộc/reentrancy | **Không** |
| **Sau** khi lớp định nghĩa xong | Thường trả lại `Class<?>` đã có hoặc delegate; không “reload” definition | Không cần thiết cho transform vừa kết thúc |
| **Trong redefine/retransform** class đã load | Lớp đã tồn tại và callback có thể được truyền `classBeingRedefined` | **Không cần** gọi loader để tìm lại |

Vì vậy, ngay cả khi gọi `loadClass` cho lớp đã nạp có thể trả về bình thường, điều đó không chứng minh nó an toàn hoặc hữu ích **khi đang transform chính lớp ấy**. Việc đọc class bytes đã được cung cấp làm đầu vào vừa rõ ràng vừa tránh lệ thuộc vào trạng thái loader.

### Tên lớp phải dùng đúng định dạng

`className` từ `ClassFileTransformer` có dạng **internal name**:

~~~text
lab/app/TargetService
java/util/ArrayList
~~~

Trong khi `ClassLoader.loadClass(String)` dùng **binary name**:

~~~text
lab.app.TargetService
java.util.ArrayList
~~~

Nếu transformer chỉ cần lọc mục tiêu, đừng chuyển đổi sang binary name rồi gọi loader. Chỉ so sánh internal name:

~~~java
if (!"lab/app/TargetService".equals(className)) {
    return null;
}
~~~

Cách viết literal ở bên trái cũng an toàn khi `className == null`. Trong các tình huống class đặc biệt, nhất là một số định nghĩa do runtime tạo, không được giả định mọi callback đều có tên lớp thông thường.

## 3. Vì sao load lại target trong callback là rủi ro?

### 3.1. Reentrant class loading

Trong quá trình định nghĩa A, JVM gọi transformer cho A. Nếu transformer lại yêu cầu nạp A thông qua loader, ta có chuỗi phụ thuộc logic:

~~~text
Loader đang định nghĩa A
       |
       v
transform(A)
       |
       v
loader.loadClass(A)
       |
       +----> Có thể trở về cùng quy trình đang dang dở
                    |
                    +----> phụ thuộc lặp / recursion / lỗi loading
~~~

Không phải mọi loader và mọi tình huống đều phát sinh recursion giống nhau; mặc định loader có cơ chế kiểm tra lớp đã load và đồng bộ theo khóa. Tuy nhiên **lớp đang được định nghĩa** không nhất thiết đã được công bố như một lớp đã hoàn tất và sẵn sàng trả về cho yêu cầu khác. Đừng dựa vào một hành vi phụ thuộc implementation để tránh lặp.

### 3.2. Khóa class loading và deadlock

`ClassLoader.loadClass` mặc định đồng bộ bằng lock do `getClassLoadingLock(name)` trả về. Một số custom loader không đăng ký *parallel capable* sẽ khóa ở mức loader; những loader khác có thể dùng khóa theo tên. Nếu callback yêu cầu thêm lớp trong khi đang giữ khóa, nó có thể tạo thêm quan hệ chờ lock, nhất là khi nhiều loaders phụ thuộc nhau hoặc hai threads cùng đang tải các lớp có vòng phụ thuộc.

Ví dụ về nguy cơ, **không phải kịch bản JVM nào cũng sẽ treo**:

~~~text
Thread-1 giữ lock loader-X khi define A
       |
       +-- transform(A) muốn load B bằng loader-Y

Thread-2 giữ lock loader-Y khi define B
       |
       +-- transform(B) muốn load A bằng loader-X

=> Có nguy cơ chờ vòng; JVM/custom loader có thể báo lỗi hoặc treo.
~~~

Không có bảo đảm rằng việc thêm `synchronized` hay `ThreadLocal<Boolean> inTransform` vào agent giải được mọi nguy cơ: một guard theo thread không kiểm soát vòng chờ **giữa các thread** hoặc **giữa các loader**.

### 3.3. Lỗi liên kết và danh tính class

Một class trong JVM được xác định về mặt runtime bởi **binary name cộng với defining class loader**. Một loader khác có thể định nghĩa class có **cùng tên** nhưng là **một runtime class khác**. Nếu transformer cố định nghĩa lại bằng `defineClass` trong cùng loader hoặc dùng loader khác để tìm “bản sao” target, các hệ quả có thể gồm:

- Lỗi kiểu `LinkageError` khi cố định nghĩa trùng trong hoàn cảnh JVM không cho phép.
- Class cast hoặc linkage failure do hai loader định nghĩa các kiểu trùng tên nhưng khác danh tính.
- Resource/class bytes được tìm từ nơi khác so với bytes mà JVM đang transform.
- Khó đoán về đồng bộ class loading trong ứng dụng plugin, application server hoặc OSGi-like environments.

**Lưu ý về `ClassCircularityError`:** ngoại lệ này được JVM dùng khi phát hiện chu trình trong cấu trúc superclass lúc load; **không phải mọi lần gọi `loadClass` trong transformer đều ném `ClassCircularityError`**. Khi ghi tài liệu lỗi, nên dùng “có thể dẫn tới class-loading/linkage problems” thay vì hứa một exception cố định.

### 3.4. Vô tình khởi tạo lớp ứng dụng

`Class.forName(binaryName)` là lời gọi có thể tải **và khởi tạo** class theo ngữ cảnh caller. Trong khi đó overload `Class.forName(name, false, loader)` không yêu cầu khởi tạo, nhưng **vẫn có thể phải tải/liên kết lớp**. Vì thế:

~~~java
Class.forName("lab.app.TargetService", true, loader);  // SAI trong transform(A)
Class.forName("lab.app.TargetService", false, loader); // Cũng không nên trong transform(A)
~~~

Đặt `false` **không giải quyết vấn đề đang định nghĩa A**; nó chỉ điều khiển yêu cầu khởi tạo. Static initializer `<clinit>`, class-loading phụ trợ và module linkage đều là các lĩnh vực khác với việc phân tích bytes hiện có.

## 4. Đọc đúng các tham số của ClassFileTransformer

Chữ ký Java 17+ thường dùng:

~~~java
@Override
public byte[] transform(
        Module module,
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain protectionDomain,
        byte[] classfileBuffer) {
    // Không cần loader.loadClass(className).
    return null;
}
~~~

Đây là **mảnh code phải đặt trong một class triển khai `ClassFileTransformer`**, không phải chương trình chạy độc lập.

| Tham số | Có thể dùng để làm gì? | Không nên hiểu sai thành |
| --- | --- | --- |
| `module` | Xác định module gắn với class cần transform; lọc theo phạm vi khi cần | Quyền truy cập tự động tới mọi package/private API |
| `loader` | Biết **defining loader**; phân biệt bootstrap (`null`), app hoặc plugin loader | Lời mời gọi `loader.loadClass(target)` trong callback |
| `className` | Lọc theo internal name, ví dụ `"lab/app/TargetService"` | Binary name để truyền nguyên văn cho `loadClass` |
| `classBeingRedefined` | Khi redefine/retransform, cho biết chính `Class<?>` đã tồn tại; khi load mới là `null` | Class object bắt buộc phải khác `null` ở mọi callback |
| `protectionDomain` | Metadata về protection domain của class được định nghĩa/redefine | Cơ chế để agent bypass mọi bảo vệ JVM/module |
| `classfileBuffer` | **Đầu vào chính xác tại bước transform này** để parse và phát bytes mới | Mảng được phép sửa trực tiếp hoặc luôn giống bản `.class` trên đĩa |

Hợp đồng `ClassFileTransformer` yêu cầu: nếu không cần thay đổi, trả `null`; nếu cần thay, tạo **mảng byte mới** và trả về bytes class file hợp lệ. Mảng `classfileBuffer` được truyền vào **không được chỉnh sửa tại chỗ**.

Khi có nhiều transformer, bytes đầu vào của một transformer có thể đã được transformer trước thay đổi. Việc tự đọc `getResourceAsStream("...class")` hoặc file từ đĩa rồi coi đó là “bản gốc” dễ làm mất những biến đổi hợp lệ đã thực hiện trước bước của bạn.

### Khi classBeingRedefined khác null thì sao?

Ở lần **load mới**, JVM đang xây dựng class nên `classBeingRedefined == null` theo API. Trong **redefinition** hoặc **retransformation**, đây là tham chiếu `Class<?>` đang được sửa.

Khi đó, nếu cần biết danh tính runtime của target, đã có object đó:

~~~java
if (classBeingRedefined != null) {
    ClassLoader definingLoader = classBeingRedefined.getClassLoader();
    // Chỉ lấy metadata; không gọi definingLoader.loadClass(targetName).
}
~~~

Đây là **mảnh minh họa**, không phải lời khuyên gọi reflective methods hoặc logic ứng dụng trong callback. Và `classBeingRedefined != null` **không đủ** để phân biệt redefine với retransform: cả hai sự kiện đều có thể truyền tham chiếu này.

## 5. Mã sai điển hình: tự tìm target bằng loader

**Không chạy đoạn dưới như Java agent**. Nó là mẫu phản diện để nhận diện anti-pattern:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader,
        String className, Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain, byte[] classfileBuffer) {
    if (!"lab/app/TargetService".equals(className)) {
        return null;
    }

    try {
        // SAI: callback đang xử lý chính class TargetService.
        Class<?> target = loader.loadClass("lab.app.TargetService");
        System.out.println(target.getDeclaredMethods().length);
    } catch (ClassNotFoundException e) {
        throw new IllegalStateException(e);
    }
    return null;
}
~~~

Các vấn đề:

1. Callback cho `TargetService` được gọi khi class có thể **chưa hoàn tất việc định nghĩa**. Một yêu cầu `loadClass(TargetService)` lồng vào có thể tái nhập loading flow.
2. `getDeclaredMethods()` còn kích hoạt nhu cầu đọc/resolve thêm metadata về các kiểu method được khai báo; không phải cách duy nhất để phân tích bytecode.
3. Nếu `loader == null` (bootstrap), code ném `NullPointerException` trước cả bước load.
4. Nếu loader tùy biến/child-first, nguy cơ phụ thuộc chéo, deadlock hoặc nạp sai kiểu càng khó kiểm soát.
5. Nếu callback của agent ném exception, JVM vẫn có thể tiếp tục chuỗi transformer theo hợp đồng. “Throw exception để dừng pipeline và rollback hết” không phải chiến lược đáng tin.

**Không chữa bằng cách đổi thành `Class.forName("lab.app.TargetService", false, loader)`.** Vẫn yêu cầu class loading. Cũng không chữa bằng cách đổi sang system class loader: nó có thể không phải loader thực sự định nghĩa target, dẫn tới **class identity khác hoặc không tìm thấy lớp**.

## 6. Mã đúng: lọc tên và đọc bytes có sẵn

Transformer tối thiểu:

~~~java
@Override
public byte[] transform(Module module, ClassLoader loader,
        String className, Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain, byte[] classfileBuffer) {

    if (!"lab/app/TargetService".equals(className)) {
        return null;
    }

    boolean hasClassMagic = classfileBuffer.length >= 4
            && (classfileBuffer[0] & 0xFF) == 0xCA
            && (classfileBuffer[1] & 0xFF) == 0xFE
            && (classfileBuffer[2] & 0xFF) == 0xBA
            && (classfileBuffer[3] & 0xFF) == 0xBE;

    // Nếu chỉ quan sát hoặc lọc, không cần tạo mảng bytes mới.
    return null;
}
~~~

Đây là **mảnh code** minh họa nguyên tắc, không phải nguyên một class. Kiểm tra `CAFEBABE` bằng bốn byte đầu là phép kiểm tra **magic header**, **không chứng minh toàn bộ class file hợp lệ**. Việc kiểm tra cấu trúc thật nên giao cho công cụ parse class file đúng chuẩn.

Đối với phép biến đổi bytecode thật:

~~~text
Được làm:
    classfileBuffer -> parser/class model -> transform -> bytes mới -> return

Không nên làm:
    className -> loader.loadClass(className) -> reflection trên target
              -> cố tạo lại bytes hoặc định nghĩa target lần nữa
~~~

Trong Java 17, có thể dùng ASM hoặc thư viện bytecode khác để parse bytes đã nhận; với JDK 24+, `java.lang.classfile.ClassFile.of().parse(classfileBuffer)` là một lựa chọn chuẩn. API JDK 24 **không có ở JDK 17/21 dưới dạng API ổn định**, nên nếu dự án cần hỗ trợ Java 17, hãy chọn thư viện tương thích hoặc tách implementation theo phiên bản.

## 7. Ví dụ Java 17+ chạy được: agent không load lại lớp đích

Ví dụ đầy đủ dùng **hai khu vực mã riêng**:

- **Agent** chứa `lab.agent.SafeLoadingAgent`, đăng ký transformer.
- **Ứng dụng** chứa `lab.app.TargetService` và `lab.app.RunDemo`. Chỉ ứng dụng chủ động yêu cầu load target.

Để chứng minh **callback có sẵn đủ thông tin**, transformer log tên lớp theo điều kiện lọc, loader có phải bootstrap không, trạng thái `classBeingRedefined` và magic bytes. Nó **không** gọi `Class.forName`, `ClassLoader.loadClass` hoặc class literal `TargetService.class` trong callback. Agent trả `null`, nên đây là **demo kiểm tra/quan sát an toàn**, chưa thay bytecode.

### 7.1. Cấu trúc thư mục

~~~text
safe-loader-demo/
├── agent-src/
│   └── lab/agent/SafeLoadingAgent.java
├── app-src/
│   └── lab/app/TargetService.java
│   └── lab/app/RunDemo.java
└── agent.mf
~~~

Các thư mục `agent-bin` và `app-bin` được tạo ở bước biên dịch. Tách agent JAR khỏi classpath app để kiểm tra rõ **lớp target không được agent trực tiếp tham chiếu như một kiểu Java**.

### 7.2. File agent-src/lab/agent/SafeLoadingAgent.java

~~~java
package lab.agent;

import java.lang.instrument.ClassFileTransformer;
import java.lang.instrument.Instrumentation;
import java.security.ProtectionDomain;

public final class SafeLoadingAgent {
    public static void premain(String args, Instrumentation instrumentation) {
        instrumentation.addTransformer(new ClassFileTransformer() {
            @Override
            public byte[] transform(
                    Module module,
                    ClassLoader loader,
                    String className,
                    Class<?> classBeingRedefined,
                    ProtectionDomain protectionDomain,
                    byte[] classfileBuffer) {

                if (!"lab/app/TargetService".equals(className)) {
                    return null;
                }

                // No Class.forName, no loader.loadClass, no target class literal!
                boolean magicOK = classfileBuffer.length >= 4
                        && (classfileBuffer[0] & 0xFF) == 0xCA
                        && (classfileBuffer[1] & 0xFF) == 0xFE
                        && (classfileBuffer[2] & 0xFF) == 0xBA
                        && (classfileBuffer[3] & 0xFF) == 0xBE;

                System.out.println("transformTarget=true");
                System.out.println("loaderIsBootstrap=" + (loader == null));
                System.out.println("classBeingRedefinedIsNull="
                        + (classBeingRedefined == null));
                System.out.println("magicOK=" + magicOK);
                return null; // Chỉ quan sát, không thay đổi bytes.
            }
        });

        System.out.println("agentRegistered=true");
    }
}
~~~

**Điểm quan trọng:**

1. `premain` được JVM gọi khi khởi động với `-javaagent:safe-agent.jar`. Callback transformer được đăng ký **trước** khi `RunDemo.main()` yêu cầu load `TargetService`.
2. Nhánh lọc `"lab/app/TargetService".equals(className)` diễn ra **đầu tiên**; những lớp không liên quan đi qua bằng `return null`, giảm overhead và nguy cơ tải helper không cần thiết.
3. Chương trình không gọi bất kỳ phương thức nào của `loader`; chỉ kiểm tra `loader == null` để xác định bootstrap loader.
4. `classfileBuffer` được xem là **read-only**. Các phép kiểm tra byte sử dụng `& 0xFF` vì `byte` của Java là signed; không cần nhân bản bytes nếu không sửa.
5. Trong demo, `System.out.println` giúp người học quan sát callback. Trong production, logging ngay trong transformer phải giới hạn/sampling và tránh làm nạp thêm hệ thống logging phức tạp.
6. Agent tự đặt tên trong package `lab.agent`; nó không import hay tham chiếu `lab.app.TargetService` bằng class literal. Đây là cách giảm phụ thuộc giữa helper của agent và target.

### 7.3. File app-src/lab/app/TargetService.java

~~~java
package lab.app;

public final class TargetService {
    static {
        System.out.println("targetClinit=true");
    }

    public static String message() {
        return "hello";
    }
}
~~~

Thông điệp `targetClinit=true` được in khi class **khởi tạo**. Sự kiện này cần phân biệt với **load/define** của class; JVM có thể định nghĩa class trước khi khởi tạo nó.

### 7.4. File app-src/lab/app/RunDemo.java

~~~java
package lab.app;

public final class RunDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("appBeforeLoad=true");

        ClassLoader appLoader = RunDemo.class.getClassLoader();
        Class<?> target = Class.forName(
                "lab.app.TargetService", false, appLoader);

        System.out.println("loadedWithoutInitializing=true");
        System.out.println("sameLoader="
                + (target.getClassLoader() == appLoader));

        Class.forName("lab.app.TargetService", true, appLoader);
        System.out.println("message="
                + target.getMethod("message").invoke(null));
    }
}
~~~

**Vì sao đây không vi phạm nguyên tắc bài học?** `Class.forName(...)` ở trên được gọi từ **mã ứng dụng `main`**, **ngoài callback `transform`** và chính là yêu cầu load ban đầu mà transformer cần quan sát. Nó không phải là transformer đang định nghĩa target rồi bất ngờ yêu cầu nạp lại target. `Class.forName(name, false, loader)` chỉ yêu cầu load/link phù hợp mà **không khởi tạo**. Lời gọi với `true` sau đó yêu cầu khởi tạo bình thường.

Điểm cần nhớ: *không cấm ứng dụng tải lớp*; **cấm anti-pattern “transformer tự gọi loader để tải lại chính lớp đang được transform”**.

### 7.5. File agent.mf

~~~text
Manifest-Version: 1.0
Premain-Class: lab.agent.SafeLoadingAgent
~~~

Manifest cần có **dòng trống ở cuối**. Demo dùng load-time transformer với cách đăng ký `addTransformer(transformer)`, tương đương `canRetransform=false`; không cần capability retransform/redefine vì không có thao tác nào thuộc hai nhóm đó.

### 7.6. Biên dịch bằng JDK 17+ và chạy

Lệnh Bash (Linux/macOS hoặc Git Bash). Các thư mục mã nguồn phải được tạo như mục 7.1:

~~~bash
mkdir -p agent-bin app-bin
javac --release 17 -d agent-bin agent-src/lab/agent/SafeLoadingAgent.java
javac --release 17 -d app-bin app-src/lab/app/TargetService.java app-src/lab/app/RunDemo.java
jar --create --file safe-agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:safe-agent.jar -cp app-bin lab.app.RunDemo
~~~

Lệnh tương ứng với Windows PowerShell để tạo hai thư mục output:

~~~powershell
New-Item -ItemType Directory -Force -Path agent-bin, app-bin | Out-Null
javac --release 17 -d agent-bin agent-src/lab/agent/SafeLoadingAgent.java
javac --release 17 -d app-bin app-src/lab/app/TargetService.java app-src/lab/app/RunDemo.java
jar --create --file safe-agent.jar --manifest agent.mf -C agent-bin .
java -javaagent:safe-agent.jar -cp app-bin lab.app.RunDemo
~~~

`javac --release 17` biên dịch theo API/class-file target của Java 17. JAR chứa toàn bộ package `lab.agent`, bao gồm class ẩn danh do compiler tạo cho transformer (ví dụ `SafeLoadingAgent$1.class`). Đừng chỉ đóng đúng `SafeLoadingAgent.class` rồi quên class triển khai transformer.

**Stdout đã biên dịch/chạy kiểm chứng trên Zulu OpenJDK 24, với `--release 17`:**

~~~text
agentRegistered=true
appBeforeLoad=true
transformTarget=true
loaderIsBootstrap=false
classBeingRedefinedIsNull=true
magicOK=true
loadedWithoutInitializing=true
sameLoader=true
targetClinit=true
message=hello
~~~

**Đọc kết quả:**

- `agentRegistered=true`: transformer được đăng ký trước khi app yêu cầu load target.
- `appBeforeLoad=true`: ứng dụng bắt đầu thao tác class loading.
- `transformTarget=true`: callback được gọi cho đúng class; không phải do agent tự nạp target.
- `loaderIsBootstrap=false`: trong ví dụ app class loader này, `loader` không phải `null`. **Không suy rộng** thành mọi target đều có non-null loader.
- `classBeingRedefinedIsNull=true`: đây là **định nghĩa class lần đầu**, không phải redefine/retransform.
- `magicOK=true`: có đủ bytes header `CAFEBABE` ở input mà **JVM đã đưa tới transformer**.
- `loadedWithoutInitializing=true` rồi `targetClinit=true`: cho thấy giai đoạn class đã được load nhưng chưa chạy initializer, sau đó application chủ động yêu cầu khởi tạo.
- `sameLoader=true`: class được nạp qua loader ứng dụng như kịch bản thiết lập.
- `message=hello`: không có transformer nào thay bytecode, ứng dụng vẫn hoạt động bình thường.

Bài demo không chứng minh rằng logging trong callback luôn miễn nhiễm mọi class-loading side effect. Nó chứng minh **đường xử lý target** không gọi loader để tải chính target và chạy được trên một môi trường kiểm thử cụ thể.

## 8. Nếu cần biến đổi bytecode thật thì phải làm gì?

Để biến đổi một method trong target, hãy dùng bytes mà JVM đưa vào thay vì reflection vào target trong lúc nó đang được định nghĩa.

### 8.1. Dùng thư viện parse bytecode hỗ trợ Java version

Với ASM (cần dependency ASM tương thích), một bước tạo mô hình có thể là:

~~~java
org.objectweb.asm.ClassReader reader =
        new org.objectweb.asm.ClassReader(classfileBuffer);
~~~

Đây là **mảnh code**, không phải Java độc lập để copy-chạy bằng JDK thuần. `ClassReader` parse **mảng class bytes**, không cần có `Class<?>` của target. Để sửa class, tạo transformer/visitor và `ClassWriter` thích hợp rồi trả `byte[]` mới từ `ClassWriter.toByteArray()`.

Trong JDK 24+, Class-File API chính thức cũng có:

~~~java
java.lang.classfile.ClassModel model =
        java.lang.classfile.ClassFile.of().parse(classfileBuffer);
~~~

Đây là **mảnh code yêu cầu JDK 24+**, không hợp lệ trên Java 17/21 như API ổn định. Nó cũng không cần `loader.loadClass(target)` chỉ để parse class bytes.

### 8.2. Cẩn trọng khi công cụ cần tính hierarchy hoặc frames

Dù parser trực tiếp không cần tải target, một số tiện ích tính hierarchy hoặc common superclass có thể **tự tìm/resolve các class khác**. Chẳng hạn một chế độ ASM tính toán frames có thể cần thông tin quan hệ kế thừa, tùy cách cấu hình writer. Nếu framework sử dụng class loading để lấy metadata, bạn vẫn cần chiến lược:

- Dùng metadata/class bytes của các dependencies đã có hoặc resource lookup có kiểm soát.
- Tránh yêu cầu load **chính target đang transform**.
- Không giả định system loader thấy đúng các kiểu của plugin class loader.
- Với hierarchy phức tạp, dùng type pool/metadata cache phù hợp và test với nhiều loader/module.
- Không sử dụng class loader mục tiêu một cách mù quáng để gọi reflection chỉ vì tiện kiểm tra superclass.

**Tách khái niệm:** “Không load target bằng loader” **không có nghĩa** không bao giờ được biết loader nào đang định nghĩa nó. `loader` vẫn có giá trị để định danh phạm vi và giải quyết các metadata cần thiết một cách an toàn.

### 8.3. Return null và mảng mới

| Kết quả callback | JVM xử lý |
| --- | --- |
| `return null` | Không thay đổi bytes ở bước này; transformer sau nhận bytes hiện có |
| `return newClassBytes` | JVM chuyển bytes mới tới transformer kế tiếp; cuối pipeline kiểm tra/áp dụng |
| Sửa trực tiếp `classfileBuffer` | **Sai hợp đồng API**; phải tạo mảng bytes mới |
| Trả bytes sai cấu trúc | Có thể bị JVM từ chối sau pipeline |
| Ném exception từ transformer | Không tự cắt toàn bộ pipeline; theo contract các transformer sau vẫn có thể được gọi |

Nếu chỉ muốn thu thập metrics về số lần nạp class, bạn **không cần** trả lại bản sao của input. Còn nếu muốn thay nội dung, cần bảo đảm output hợp lệ; việc tránh `loader.loadClass` giải quyết một nguy cơ, không thay thế quy trình xác minh bytecode.

## 9. Agent helper: tránh phụ thuộc vào target đang load

Một lý do phổ biến khiến transformer cố load target là **helper có reference ngược tới class ứng dụng**. Ví dụ:

~~~java
public final class AgentHelper {
    public static void record() {
        // Sai thiết kế nếu helper bị gọi ngay khi TargetService đang load:
        // TargetService.someStaticMethod();
    }
}
~~~

Đây là **mảnh minh họa**, không phải class runnable độc lập vì `TargetService` không được khai báo ở đây. Vấn đề là helper gọi code của target hoặc nạp target để lấy annotation/metadata khi target **chưa hoàn tất định nghĩa**.

Thiết kế tốt hơn:

- Helper nhận **dữ liệu trung tính** như chuỗi internal name, descriptor, timestamp, số liệu thô.
- Transformer xử lý `classfileBuffer` trong callback, không cần khởi tạo target object.
- Hạn chế static initializer của helper làm nạp package ứng dụng.
- Tải/khởi tạo những thư viện agent thiết yếu **trước khi đăng ký transformer**, nếu có thể, nhưng tránh preload chính target hoặc các lớp nghiệp vụ cần quan sát.
- Exclude packages của agent/logger/bytecode tooling khỏi phạm vi transformation nếu không cần theo dõi chúng.
- Khi helper cần gọi trong **method đã instrument**, đảm bảo helper có thể được **loader của method đó** truy cập sau khi class đã định nghĩa.

### Hai vấn đề khác nhau về helper

**Vấn đề A — helper chạy trong callback của agent:** nó cần sẵn sàng khi JVM đang define class. Nếu helper tự tham chiếu target, có thể tạo vòng phụ thuộc trong load.

**Vấn đề B — helper được gọi bởi bytecode chèn vào ứng dụng:** khi method ứng dụng thực thi, JVM sẽ resolve tham chiếu helper theo quan hệ loader/module/visibility. Việc agent tự load được helper **không bảo đảm** mọi class đích đều resolve được helper đó.

Ví dụ một class `java.base` được bootstrap loader định nghĩa không thể mặc nhiên truy cập một helper chỉ tồn tại trong application class loader. Với nhiều plugin loaders cách ly, các class cùng tên cũng có thể resolve helper theo những paths khác nhau.

## 10. Làm cho helper khả kiến mà không tự nạp target

Các cách tổ chức thực tiễn:

| Cách bố trí helper | Khi phù hợp | Điểm cần lưu ý |
| --- | --- | --- |
| Helper nằm trong agent JAR, system/application loader có thể thấy | Instrument các class ứng dụng đơn giản | Custom loaders có thể không delegate tới hệ thống helper |
| Helper nằm trong JAR riêng và được thêm vào bootstrap search | Cần target từ bootstrap hoặc nhiều loader cùng truy cập helper | Chỉ đưa lớp tối thiểu vào bootstrap, tránh split package/conflict |
| Thêm helper vào system loader search | Cần mở rộng lớp mà system loader tìm được | Không bảo đảm mọi child-first/custom loader dùng nó |
| Không chèn lệnh gọi helper vào target, chỉ phân tích bytecode | Probe thuần metadata và transform tự chứa | Không cần giải quyết helper lúc runtime |
| Dùng một cơ chế bridge có hợp đồng module/loader rõ ràng | Ứng dụng nhiều module/plugin | Phải kiểm thử module reads/exports/opens, identity và lifecycle |

API có sẵn:

~~~java
instrumentation.appendToBootstrapClassLoaderSearch(jarFile);
instrumentation.appendToSystemClassLoaderSearch(jarFile);
~~~

Đây là **đoạn minh họa**: `instrumentation` phải do JVM cấp, `jarFile` là `java.util.jar.JarFile` hợp lệ; cần chuẩn bị JAR riêng và xử lý lỗi. Không dùng chỉ để né vấn đề đang transform target; hai phương thức **bổ sung nơi tìm helper**, không phải lệnh “reload target”.

Oracle Javadoc cảnh báo rằng JAR thêm vào bootstrap **chỉ nên chứa đúng các lớp/tài nguyên dự kiến được bootstrap loader định nghĩa**. Đưa cả agent/app JAR vào đó có thể làm thay đổi cách resolve class, gây xung đột package hoặc liên kết khó chẩn đoán.

Ngoài loader visibility, module system (JPMS) có các quan hệ **readability**, **exports** và **opens**. Trong một số tình huống agent phải sắp xếp quan hệ module bằng `Instrumentation.redefineModule(...)`. Đó là một bài toán **truy cập helper**, không cho phép transformer nạp lại chính target đang định nghĩa.

### Không lạm dụng Thread Context ClassLoader

`Thread.currentThread().getContextClassLoader()` (TCCL) có thể khác **defining loader** của target. Dùng TCCL để “tìm lại” class đang transform dễ trả về class trùng tên nhưng từ môi trường khác, hoặc chẳng tìm được class. Nếu cần biết loader nào nhận bytecode, **tham số `loader` đã cung cấp thông tin trực tiếp**. Nếu chỉ cần lọc tên, hãy dùng `className`.

## 11. Khi nào Class.forName hoặc loader.loadClass là đúng?

Không phải mọi việc tải lớp bằng Java đều sai. Quy tắc bài học có **phạm vi rất cụ thể**: **trong lúc transformer đang xử lý một class, không tự tải lại chính class ấy**.

Một số tình huống hợp lệ khác:

- Application code chủ động sử dụng hoặc tải một class **ngoài callback**, như ví dụ `RunDemo.main()`.
- Framework plugin thực sự muốn nạp một class sau khi loader đã sẵn sàng và không trong chuỗi define của chính class đó.
- Agent chủ động tìm một class **đã load xong** để yêu cầu `Instrumentation.retransformClasses(existingClass)` hoặc `redefineClasses(...)` ngoài callback, sau khi kiểm tra capability và modifiability.
- Agent cần chuẩn bị **các helper độc lập** trước khi đăng ký transformer, không kéo target bị quan sát vào quá trình preload.

Ngay cả với các tình huống này, cần phân biệt class loader identity, class initialization và thay đổi hệ thống do việc tải lớp gây ra. Khác biệt căn bản là **không tái nhập vào chính tiến trình định nghĩa target đang dang dở**.

### Nếu class đã tồn tại trong callback retransform thì sao?

Ở redefine/retransform, `classBeingRedefined` đã cho `Class<?>` của target. Bạn có thể dùng nó để nhận diện class được sửa trong các giới hạn hợp lý. Nhưng việc gọi `Class.forName(...)` hay `loader.loadClass(...)` cho chính target vẫn **thừa**, không giúp bạn có “phiên bản bytecode mới nhất” và có thể kích hoạt logic loading/linkage phụ.

Nếu muốn **đọc bytes** đang được transform, chỉ lấy từ `classfileBuffer`. Nếu muốn **thay đổi** lớp đã nạp, thực hiện bằng `retransformClasses`/`redefineClasses` ở một **thời điểm điều phối thích hợp ngoài callback**, không gọi lồng hai thao tác này cho chính target khi JVM còn đang xử lý transform của nó.

## 12. Lỗi phổ biến và nguyên nhân thực tế

| Hiện tượng | Nguyên nhân có thể | Điều chỉnh |
| --- | --- | --- |
| JVM chậm hoặc treo khi startup với agent | Callback tải lớp khác/target trong class-loading lock; logger/helper tải lớp lồng nhau | Lọc class đầu callback; bỏ `loadClass(target)`; giới hạn helper |
| `StackOverflowError` khi nạp class | Reentrant transformation hoặc recursive helper | Loại chu trình; không gọi lại target trong callback |
| `ClassNotFoundException` | Dùng system loader sai, nhầm binary name/internal name hoặc class chưa được định nghĩa | So sánh `className`, dùng đúng loader khi thật sự cần ngoài callback |
| `NoClassDefFoundError` | Helper không có ở classpath/loader mà bytecode instrumented sử dụng; initialization lỗi | Bố trí/helper bootstrap/module đúng |
| `LinkageError` khi define | Định nghĩa trùng class hoặc vi phạm loader constraint | Không tự `defineClass` lại target; xác định đúng runtime identity |
| `ClassCastException` giữa hai kiểu cùng tên | Class thực tế được định nghĩa bởi hai loader khác nhau | Dùng cùng `Class<?>`/loader dự kiến, không tạo bản duplicate |
| Không thấy callback target | Transformer đăng ký sau khi target đã load, filter sai, class thuộc loader khác | Đăng ký sớm hoặc retransform có kiểm soát |
| `classBeingRedefined == null` | Đang load một định nghĩa mới | Dùng `className` và bytes; không cố tìm `Class<?>` |
| `loader == null` | Lớp bootstrap-defined | Không dereference loader; helper placement đúng |
| `className == null` | Tình huống class đặc biệt do JVM/runtime định nghĩa | Viết filter null-safe, dùng metadata khác nếu có |
| Reading .class resource cho kết quả khác | Class tạo động, multi-release JAR, resource khác hoặc transformer khác đã thay bytes | Tin `classfileBuffer` cho lượt transform hiện tại |
| Agent log ra lỗi verifier sau khi trả bytes | Output bytecode không hợp lệ, stack maps/frames sai | Dùng bytecode parser/verifier và test trên JDK mục tiêu |
| Module error sau khi chèn helper call | Loader thấy helper nhưng JPMS read/export/open không phù hợp | Thiết kế module linkage rõ ràng, không nạp lại target |

**Không thể chẩn đoán mọi `ClassCircularityError` là do agent**: theo định nghĩa JVM, nó liên quan phát hiện chu trình superclass. Khi xuất hiện lỗi loading/linkage, xem stack trace, các callbacks đang chạy và phụ thuộc loader cụ thể; tránh gán nguyên nhân chung cho mọi lỗi.

## 13. Thiết kế filter an toàn và tránh reentrancy

Một transformer production thường có cấu trúc:

~~~text
Bắt đầu transform
    |
    +-- className null? --------------------> return null
    |
    +-- không đúng phạm vi package? -------> return null
    |
    +-- là package agent/helper? -----------> return null
    |
    +-- cần metadata nào? -----------------> đọc classfileBuffer
    |
    +-- parse/transform bytes bằng tool
    |
    +-- output hợp lệ? --------------------> return byte[] mới
    |
    +-- không đổi? ------------------------> return null
~~~

Các ý thiết kế:

1. **Filter rất sớm** bằng `className`, tùy scope bằng `loader`/`module` mà không buộc loader tải target.
2. **Đừng gọi application code** như `TargetService.someMethod()` trong transformer của TargetService.
3. **Tránh khởi tạo logger/serializer phức tạp** bên trong callback, nhất là ở giai đoạn startup JVM.
4. **Tách parser và helper khỏi package đang instrument**; chuẩn bị dependency trước khi đăng ký nếu được.
5. **Dùng guard reentrancy** cho callback trong những hệ thống cần thiết, nhưng không coi guard là thay thế việc loại trừ class-loading dependency và deadlock giữa threads.
6. **Không giữ strong references tới class loaders lâu hơn cần thiết** trong cache agent; có thể ngăn class unloading ở ứng dụng plugin. Nếu cache theo loader, cân nhắc weak keys và đồng bộ.
7. **Không giả định mọi loader là parent-first**; kiểm thử child-first, isolated plugin loader và bootstrap.
8. **Đo đúng điều cần đo**; nếu chỉ cần số lần load, không parse toàn bộ class hoặc load class qua reflection chỉ để ghi một metric.

### Vì sao chỉ dùng ThreadLocal guard vẫn chưa đủ?

Một mẫu phổ biến:

~~~java
if (Boolean.TRUE.equals(inTransform.get())) {
    return null;
}
inTransform.set(true);
try {
    return doTransform(classfileBuffer);
} finally {
    inTransform.remove();
}
~~~

Đây là **mảnh mã minh họa**, yêu cầu `ThreadLocal<Boolean> inTransform` và `doTransform(byte[])` được định nghĩa. Guard có thể ngăn một số recursion **trên cùng thread**, nhưng **không** ngăn việc Thread A giữ loader X rồi chờ loader Y trong khi Thread B giữ loader Y rồi chờ loader X. Nếu `doTransform` gọi `loader.loadClass(target)`, thiết kế vẫn sai ngay cả khi thêm guard.

Điểm quan trọng hơn guard là **xóa phụ thuộc vòng** ngay trong luồng class loading.

## 14. Kiểm thử an toàn loader cho Java agent

Không chỉ kiểm tra ứng dụng chạy được sau khi attach agent. Nên có một ma trận kiểm thử tập trung:

| Kiểm thử | Cách làm | Kết quả mong muốn |
| --- | --- | --- |
| Target load lần đầu | Chạy agent từ `premain`, sau đó ứng dụng mới load target | Một callback đúng class, không lỗi loading |
| Target không khởi tạo sớm | App dùng `Class.forName(name, false, loader)` rồi mới init | Callback chạy trước `<clinit>` trong kịch bản mẫu |
| Nhiều class không liên quan | Load thêm các class khác | Filter trả `null` nhanh, không log/transform bừa |
| Custom child-first loader | Định nghĩa target bằng plugin loader | Không yêu cầu system loader nạp lại cùng tên |
| Bootstrap class | Instrument một lớp bootstrap trong môi trường test cô lập | `loader==null` được xử lý, không NPE |
| Hai class cùng binary name ở hai loaders | Load trong hai plugin contexts | Cache/filter phân biệt loader identity |
| Reentrant dependencies | Helper tham chiếu class khác cũng bị instrument | Không recursion vô hạn, không deadlock |
| Nhiều threads load đồng thời | Stress class loading trên nhiều loaders | Không treo, không lock cycle, metrics an toàn |
| Redefine/retransform | Callback có `classBeingRedefined != null` | Không cần loader.loadClass để tìm target |
| Class được tạo động | Bytecode từ generator/in-memory | Parser dùng bytes đầu vào, không lệ thuộc classfile resource |
| Missing helper | Chèn lời gọi helper rồi thử custom loader | Báo rõ linkage/visibility; có giải pháp đóng gói |
| Verify output | Trả bytes từ parser bytecode | JVM chấp nhận class, test runtime qua được |

### Những assertion nên có

- Trong callback, mọi nhánh xử lý target **không có** `Class.forName(targetName)`, `loader.loadClass(targetName)` hoặc tự `defineClass(targetName, ...)`.
- Với input không thuộc phạm vi, transformer trả `null` mà không khởi tạo dependency không cần thiết.
- Nếu output `byte[]` mới được trả, input `classfileBuffer` không bị sửa tại chỗ.
- Không có class initialization không chủ đích trước điểm ứng dụng chủ động sử dụng class.
- Agent không làm hỏng class loader identity ở các plugin/classloader boundaries.
- Không có deadlock hoặc recursion dưới tải đồng thời.
- Nếu có helper call chèn vào method, helper có thể được resolve **bởi runtime của method**, không chỉ từ agent.
- Khi retransform/redefine target đã load, không làm phát sinh class definition thứ hai.

**Không dùng việc “chạy lần đầu thành công” làm bằng chứng cho mọi class loader**. Plugin loader, module layer, bootstrap và container environment có thể có quy tắc khác. Test cần phản ánh môi trường triển khai.

## 15. Bài tập tự kiểm tra

**Câu 1.** Transformer nhận `className="com/example/Service"` cùng `classfileBuffer`. Nó muốn kiểm tra xem method `run()` có trong class hay không. Có cần `loader.loadClass("com.example.Service")` không?

**Câu 2.** Khi JVM load class mới, `classBeingRedefined == null`. Điều này có nghĩa callback phải gọi `Class.forName(...)` để lấy một `Class<?>`?

**Câu 3.** Vì sao `Class.forName(name, false, loader)` **trong callback của chính target** vẫn là anti-pattern dù `initialize=false`?

**Câu 4.** `loader == null` trong `transform(...)` có phải error hay không? Đây thường là loader nào?

**Câu 5.** Hai plugin loaders định nghĩa hai class cùng tên `com.example.PluginService`. Cần phân biệt chúng bằng thông tin nào?

**Câu 6.** Vì sao gọi `ClassLoader.getSystemClassLoader().loadClass(binaryName)` không phải là cách sửa lỗi an toàn khi transformer cho một target của custom loader?

**Câu 7.** Agent dùng `ClassFileTransformer` trả `null` cho target. Điều đó có nghĩa lớp không được JVM định nghĩa nữa không?

**Câu 8.** Agent đã gọi `Class.forName(name, false, loader)` trong callback và may mắn không treo trên máy A. Có nên coi đây là giải pháp portable cho mọi JVM không?

**Câu 9.** Agent helper dùng từ code chèn vào một bootstrap class nằm trong agent JAR ở system loader. Liệu bootstrap class có mặc nhiên truy cập được helper không?

**Câu 10.** Mã trong `RunDemo.main` gọi `Class.forName("lab.app.TargetService", false, appLoader)`. Vì sao điều đó khác với transformer tự gọi lệnh tương tự?

**Câu 11.** Một framework muốn tính stack map frames và tự load mọi superclass bằng class loader của target. Điều gì cần kiểm tra trước khi dùng nó trong transformer?

**Câu 12.** Đang retransform class đã load, `classBeingRedefined` là non-null. Có cần gọi lại loader để có class identity không?

### Đáp án

1. **Không.** Đọc `classfileBuffer` bằng parser như ASM hoặc JDK 24 Class-File API; không cần `Class<?>` để biết danh sách method.
2. **Không.** `null` là trạng thái bình thường khi load class mới; dùng `className` và bytes hiện có.
3. `initialize=false` chỉ tránh yêu cầu khởi tạo, **không tránh yêu cầu load/link** chính class đang định nghĩa.
4. **Không**. Thường biểu thị bootstrap loader; không dereference `loader` nếu `null`.
5. Cặp **binary/internal name và defining loader identity**, có thể kèm module khi cần.
6. System loader có thể không nhìn thấy class của custom loader, hoặc nhìn thấy **một class khác cùng tên**; không sửa vấn đề reentrancy.
7. **Không**. `return null` nghĩa là transformer này **không thay bytes**; JVM tiếp tục chuỗi biến đổi/định nghĩa class.
8. **Không**. Hành vi phụ thuộc JVM, lock/delegation và trạng thái; không biến sự may mắn thành contract.
9. **Không**. Bootstrap loader không mặc nhiên nhìn thấy mọi class trong system loader; phải bố trí helper/module access phù hợp.
10. Nó là **yêu cầu load ban đầu từ ứng dụng**, ngoài callback. Anti-pattern là **yêu cầu nạp lại chính lớp đích trong khi callback đang xử lý lớp đó**.
11. Kiểm tra framework có thể tái tải target hoặc class đang load khác hay không, loader isolation, hierarchy cache và nguy cơ reentrancy/lock.
12. **Không.** `classBeingRedefined` đã chứa `Class<?>` của target; `classfileBuffer` đã chứa bytes cần transform.

## 16. Kết luận

**Trong callback transform, lớp đích chưa nhất thiết là một `Class<?>` đã hoàn tất việc định nghĩa. Đừng yêu cầu class loader nạp lại chính lớp ấy.** Sử dụng dữ liệu trực tiếp từ JVM: `className` để lọc, `loader`/`module` để hiểu ngữ cảnh, `classfileBuffer` để parse và phát bytes đã biến đổi. Nếu callback chỉ quan sát thì trả `null`.

Giữ helper của agent độc lập với target, kiểm tra khả năng nhìn thấy helper ở runtime của class được instrument, tránh recursion/deadlock trong class loading và phân biệt rõ **lần load gốc** với việc **redefine/retransform một class đã tồn tại**.

## 17. Tài liệu kỹ thuật chính thức

- [Java SE 21 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): thời điểm callback được gọi, tham số `className`/`loader`/`classBeingRedefined`/`classfileBuffer`, quy tắc return bytes/`null` và không sửa mảng input.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): cơ chế `loadClass`, parent delegation, `findLoadedClass`, synchronization/class-loading locks và class loader identity.
- [Java SE 21 — Instrumentation](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `appendToBootstrapClassLoaderSearch`, `appendToSystemClassLoaderSearch` và `redefineModule`.
- [Java SE 21 — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `Class.forName`, class identity, defining loader và hidden classes.
- [Java SE 21 — java.lang.instrument package](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent manifest, `Premain-Class` và class loading của agent helper.
- [JVM Specification 21 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): mô hình loading, class loader và tương tác với liên kết/khởi tạo.
