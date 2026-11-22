# Phân biệt nạp, liên kết và khởi tạo lớp trong luồng kích hoạt plugin

## 1. Ba giai đoạn của JVM và bước kích hoạt của ứng dụng

Khi một ứng dụng Java nhận thêm plugin, các hành động “tìm thấy tệp JAR”, “nạp lớp”, “liên kết lớp”, “khởi tạo lớp”, “tạo đối tượng” và “bật plugin” **không đồng nghĩa**. Nếu gộp chúng thành một bước, rất khó giải thích vì sao plugin đã được phát hiện nhưng chưa chạy, vì sao lỗi thiếu thư viện chỉ xuất hiện khi gọi phương thức, hoặc vì sao một đoạn mã `static` lại chạy sớm hơn dự định.

Có thể nhìn quy trình ở hai tầng:

- **Tầng JVM:** nạp (loading), liên kết (linking) và khởi tạo (initialization) **lớp/giao diện** theo quy tắc của máy ảo Java.
- **Tầng ứng dụng:** phát hiện plugin, kiểm tra hợp đồng/siêu dữ liệu, tạo instance, gọi phương thức kích hoạt như `start()`, rồi quản lý hoạt động và dừng plugin. Những bước này do host hoặc plugin manager thiết kế.

```text
Host đọc cấu hình/JAR hoặc thông tin đăng ký plugin
                     |
                     v
            Tìm tên kiểu provider
                     |
                     v
       JVM nạp lớp (LOADING)
       tìm bytecode, tạo Class
                     |
                     v
       JVM liên kết (LINKING)
       kiểm tra -> chuẩn bị -> phân giải (*)
                     |
                     v
       JVM khởi tạo (INITIALIZATION)
       chạy logic khởi tạo tĩnh khi có kích hoạt
                     |
                     v
       Tạo đối tượng plugin (nếu mô hình cần)
                     |
                     v
       Host gọi start()/activate() của plugin
                     |
                     v
       Plugin được phép phục vụ yêu cầu

(*) JVM có thể phân giải tham chiếu ký hiệu sớm hoặc trì hoãn
    cho tới khi dùng; sơ đồ là trình tự khái niệm, không phải
    bảo đảm mọi tiểu bước đều xảy ra thành từng khối cố định.
```

**Khởi tạo lớp** là công việc của JVM; **kích hoạt plugin** là quyết định của host. Một lớp có thể đã được khởi tạo trong JVM nhưng plugin vẫn chưa nhận lời gọi `start()`. Ngược lại, một plugin manager không thể an toàn gọi instance method của plugin khi chưa có đối tượng phù hợp.

## 2. Nạp lớp (loading): tìm và định nghĩa kiểu

Nạp lớp là quá trình JVM, thông qua một bộ nạp lớp (class loader), tìm biểu diễn nhị phân của lớp/giao diện và tạo đối tượng `java.lang.Class` tương ứng. Với plugin, bytecode có thể đến từ JAR trên classpath hoặc cơ chế nạp do host quản lý.

Ví dụ, host biết tên nhị phân của provider:

```text
demo.plugin.GreetingPlugin
```

Một lời gọi tiêu biểu là:

```java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
Class<?> type = Class.forName("demo.plugin.GreetingPlugin", false, loader);
```

Đây là **đoạn mã minh họa**, không phải chương trình độc lập. Tham số `false` yêu cầu **không khởi tạo lớp** trong lời gọi này. Theo API Java, overload `Class.forName(name, initialize, loader)` cố tìm, nạp và liên kết lớp; điều đó **không đồng nghĩa** với thực thi khối `static`. Một số công việc phân giải liên kết có thể vẫn phát sinh sau đó.

Phân biệt hai đối tượng thường bị nhầm:

- `Class<?>` là đối tượng mô tả **kiểu** mà JVM biết đến; sở hữu đối tượng này chưa có nghĩa đã tạo instance của plugin.
- `GreetingPlugin` là kiểu lớp; một **instance** chỉ xuất hiện khi host tạo đối tượng bằng `new`, constructor phản chiếu hoặc cơ chế tạo provider khác.

`ClassLoader.loadClass("demo.plugin.GreetingPlugin")` cũng thường được dùng để yêu cầu nạp lớp; bản thân thao tác nạp thông thường **không yêu cầu chạy khởi tạo tĩnh**. Tuy nhiên, host không nên dựa vào tên phương thức “load” để đoán mọi phụ thuộc đã tương thích: việc phân giải một số tham chiếu có thể được trì hoãn.

### Vai trò của classloader trong plugin

Một lớp Java được phân biệt không chỉ bằng tên nhị phân mà còn bằng **bộ nạp đã định nghĩa lớp**. Hai classloader khác nhau có thể tạo hai kiểu riêng biệt cùng tên `demo.spi.Plugin`; plugin thực thi một bản interface có thể không ép kiểu được sang bản do host giữ.

Để dùng chung hợp đồng, hệ thống plugin thường để cả host và plugin nhìn thấy **cùng kiểu API/SPI** qua cấu trúc classloader phù hợp. Classloader riêng giúp tổ chức phụ thuộc và có thể hỗ trợ tháo gỡ phiên bản plugin khi mọi tham chiếu đã được giải phóng; nó **không tự là ranh giới bảo mật** và việc nạp động không bảo đảm hot-swap an toàn.

## 3. Liên kết (linking): kiểm tra, chuẩn bị và phân giải

Liên kết là công việc biến lớp đã nạp thành kiểu có thể sử dụng theo quy tắc JVM. Ba phần cần hiểu:

| Phần của linking | JVM thực hiện điều gì? | Điều cần nhớ với plugin |
|---|---|---|
| **Verification** – kiểm tra | Kiểm tra tính hợp lệ của biểu diễn lớp/bytecode, các ràng buộc kiểu và an toàn kiểm chứng | Plugin bị lỗi bytecode có thể gây `VerifyError` trước khi phương thức nghiệp vụ chạy |
| **Preparation** – chuẩn bị | Tạo bộ nhớ cho các trường `static` của lớp và đặt giá trị khởi đầu theo quy tắc JVM | Không phải bước chạy toàn bộ mã `static` do lập trình viên viết |
| **Resolution** – phân giải | Biến tham chiếu ký hiệu trong constant pool thành tham chiếu trực tiếp đến lớp, trường, phương thức... | Thiếu lớp phụ thuộc, sai chữ ký, vi phạm quyền truy cập có thể lộ ra khi tham chiếu được phân giải |

### 3.1. Preparation không phải initialization

Xét một lớp minh họa:

```java
final class State {
    static int counter = 7;
    static String text = build();

    private static String build() {
        System.out.println("build()");
        return "ready";
    }
}
```

Đây là **đoạn lớp minh họa**, không phải chương trình hoàn chỉnh. Ở bước chuẩn bị, các trường `static` thông thường nhận giá trị mặc định phù hợp (`0` hoặc `null`). Những phép gán như `counter = 7` và lời gọi `build()` thuộc công việc **khởi tạo**, không đơn giản được thực thi ở bước chuẩn bị. Vì thế không được kỳ vọng thấy `build()` in ra chỉ vì class đã được nạp hoặc chuẩn bị.

Ngoại lệ kỹ thuật cần biết: trường `static final` có thuộc tính class file `ConstantValue` được JVM gán giá trị hằng theo quy tắc của bước chuẩn bị. Điều này **không làm thay đổi** kết luận rằng khối `static { ... }` và các biểu thức khởi tạo tĩnh thông thường không chạy trong preparation.

### 3.2. Resolution có thể đến muộn

Bytecode có thể lưu các tên ký hiệu như `demo.spi.Plugin`, tên phương thức và kiểu tham số trong constant pool. JVM có quyền phân giải nhiều tham chiếu khi liên kết hoặc trì hoãn đến lúc lệnh cần dùng chúng. Do đó:

- Không thể khẳng định mọi lớp phụ thuộc và mọi phương thức đã được phân giải xong chỉ vì `Class.forName(..., false, ...)` trả về `Class`.
- Một plugin có thể nạp/khởi tạo được nhưng thất bại khi đi vào **nhánh mã chưa từng chạy** vì thiếu phương thức hoặc lớp phụ thuộc.
- Các lỗi `NoClassDefFoundError`, `NoSuchMethodError`, `IllegalAccessError` hoặc dạng `LinkageError` khác cần được xem xét cùng bộ nạp, phiên bản bytecode và thư viện thực sự hiện diện.

Khả năng phân giải muộn giải thích vì sao preflight tại thời điểm khám phá plugin là cần thiết nhưng chưa chắc phát hiện mọi lỗi chạy về sau.

## 4. Khởi tạo lớp (initialization): JVM chạy mã tĩnh

Khởi tạo là giai đoạn JVM thực thi logic khởi tạo tĩnh của lớp, thường được trình biên dịch gom thành phương thức đặc biệt `<clinit>`. Nó bao gồm các khối `static { ... }` và các biểu thức khởi tạo trường `static` theo thứ tự hợp lệ. Lập trình viên **không tự gọi** `<clinit>` như phương thức Java bình thường.

Khi JVM khởi tạo một lớp, nó phải xử lý thứ tự khởi tạo các lớp cha liên quan theo đặc tả; điều này không có nghĩa mọi lớp phụ thuộc được nạp đều tự động khởi tạo ngay.

Các trường hợp **sử dụng chủ động (active use)** có thể kích hoạt khởi tạo lớp nếu lớp chưa được khởi tạo:

- Tạo đối tượng bằng `new` (khởi tạo lớp trước khi chạy constructor của instance).
- Gọi phương thức `static` do lớp khai báo.
- Đọc hoặc ghi trường `static` không thuộc ngoại lệ hằng compile-time.
- Một số thao tác phản chiếu hoặc lời gọi method handle theo quy tắc Java/JVM; ví dụ `Class.forName(name, true, loader)` yêu cầu khởi tạo.

Ngược lại, lấy class literal `GreetingPlugin.class`, gọi `getName()` trên đối tượng `Class` hoặc dùng `Class.forName(name, false, loader)` **không tự là yêu cầu khởi tạo lớp đó**. Nếu lớp đã được mã khác khởi tạo trước, lời gọi `false` cũng không “hoàn tác” việc này.

**Bẫy hằng số:** tham chiếu trực tiếp đến một biến hằng `static final` nguyên thủy/`String` mà giá trị được xác định lúc biên dịch có thể bị inline vào mã gọi và **không kích hoạt khởi tạo** của lớp khai báo. Đừng dùng việc đọc một hằng như thế làm phép thử xem khối `static` đã chạy chưa.

Khởi tạo thành công thông thường xảy ra **một lần cho mỗi lớp được định nghĩa** trong JVM, kể cả khi nhiều thread cùng sử dụng. JVM đồng bộ hóa quy trình; các thread khác có thể phải đợi. Classloader khác định nghĩa một lớp cùng tên là một **định danh kiểu khác**, chứ không phải “khởi tạo lại” chính đối tượng `Class` đã có.

### 4.1. Điều gì xảy ra nếu <clinit> thất bại?

Một khối khởi tạo tĩnh có thể ném ngoại lệ, ví dụ vì phụ thuộc ngoài chưa sẵn sàng. Nếu mã khởi tạo ném ngoại lệ không phải `Error`, JVM thường báo `ExceptionInInitializerError` cho lần thất bại; những nỗ lực sử dụng tiếp theo đối với cùng lớp trong cùng loader có thể gặp `NoClassDefFoundError` vì lớp đã ở trạng thái khởi tạo lỗi. Không nên giả định có thể đơn giản “thử lại `Class.forName(..., true, ...)`” để làm cho lớp lỗi chạy lại `static`.

Một ví dụ nguy hiểm là kết nối mạng, mở file, tạo thread hoặc tự đăng ký vào registry ngay trong `static`. Các tác dụng phụ ấy có thể xuất hiện **trước khi host chính thức bật plugin**, khiến kiểm soát lỗi, rollback hoặc tắt plugin khó khăn. Nên để công việc nghiệp vụ và tài nguyên vào vòng đời tường minh khi có thể.

## 5. Khởi tạo lớp, tạo instance và kích hoạt plugin là ba hành động riêng

Xét một lớp có cả khối `static`, constructor và phương thức `start()`:

| Hành động | Ai điều phối? | Chạy phần mã nào? |
|---|---|---|
| JVM **khởi tạo lớp** | JVM khi gặp tình huống cần khởi tạo | `static` / `<clinit>`, thông thường một lần |
| **Tạo instance** | Host/factory/ServiceLoader hoặc mã khác | Constructor và các bộ khởi tạo instance, mỗi đối tượng mới |
| **Kích hoạt plugin** | Host hoặc plugin manager theo hợp đồng | `start()`/`activate()` do hệ thống tự định nghĩa |

Một lớp đã khởi tạo **không tự tạo đối tượng**; một đối tượng được tạo **không tự được coi là plugin đã kích hoạt** nếu hợp đồng yêu cầu gọi `start()`. Trong mô hình dùng phương thức `static` làm điểm vào, có thể không cần instance, nhưng host vẫn phải định nghĩa rõ bước kích hoạt ứng dụng.

### 5.1. Trình tự kiến trúc nên hướng tới

1. **Phát hiện ứng viên:** đọc descriptor, service provider file hoặc cấu hình để biết plugin nào có thể được nạp.
2. **Kiểm tra trước:** phiên bản, hợp đồng, chữ ký/nguồn tin cậy, quyền và điều kiện cấu hình. Những kiểm tra có thể làm từ metadata nên thực hiện trước khi chạy mã plugin.
3. **Nạp/kiểm tra kiểu:** chọn classloader, lấy `Class` khi cần, so sánh khả năng triển khai SPI. Bước này có thể khiến JVM kiểm tra/giải quyết một số phụ thuộc.
4. **Khởi tạo/tạo instance:** theo cơ chế JVM hoặc provider factory; chấp nhận rằng mã tĩnh và constructor có thể phát sinh tác dụng phụ/lỗi.
5. **Kích hoạt:** gọi `start()` sau khi host đã quyết định chấp nhận plugin; quản lý kết quả và trạng thái hoạt động.
6. **Ngừng hoạt động:** gọi `stop()`/`close()` nếu hợp đồng có quy định; giải phóng tài nguyên và tham chiếu.

Thứ tự này là **chính sách ứng dụng để hạn chế tác dụng phụ**; JVM có quyền phân giải từng tham chiếu vào các thời điểm khác nhau và một số bước có thể đã diễn ra do thao tác khác từ trước. Host không thể bảo đảm mọi mã độc hại được kiểm tra an toàn chỉ bằng việc tải `Class` mà không khởi tạo.

## 6. Ví dụ Java 17+: nhìn thấy thời điểm mỗi loại mã chạy

Ví dụ này dùng reflection để chủ động yêu cầu nạp **không khởi tạo**, sau đó yêu cầu khởi tạo, tạo đối tượng và gọi phương thức kích hoạt. Plugin nằm trong JAR riêng trên classpath; không cần thư viện bên ngoài.

### 6.1. Cấu trúc tệp

```text
loading-demo/
├── api/
│   └── src/demo/spi/Plugin.java
├── plugin/
│   └── src/demo/plugin/GreetingPlugin.java
└── host/
    └── src/demo/host/Main.java
```

### 6.2. Hợp đồng — api/src/demo/spi/Plugin.java

```java
package demo.spi;

public interface Plugin {
    void start();
}
```

Giao diện này là hợp đồng chung. Host và plugin đều biên dịch dựa trên một bản `Plugin` mà chương trình chạy sẽ dùng chung.

### 6.3. Triển khai — plugin/src/demo/plugin/GreetingPlugin.java

```java
package demo.plugin;

import demo.spi.Plugin;

public final class GreetingPlugin implements Plugin {
    static {
        System.out.println("    <clinit> GreetingPlugin");
    }

    public GreetingPlugin() {
        System.out.println("    <init> GreetingPlugin");
    }

    @Override
    public void start() {
        System.out.println("    start() GreetingPlugin");
    }
}
```

Thông báo `<clinit>` mô phỏng tên phương thức khởi tạo tĩnh trong JVM; Java sẽ sinh phần tương ứng khi biên dịch. Dòng `<init>` là **chuỗi được in trong constructor**, biểu thị thao tác tạo instance. Còn `start()` là phương thức nghiệp vụ do host gọi, không phải hook khởi tạo tự động của JVM.

### 6.4. Host — host/src/demo/host/Main.java

```java
package demo.host;

import demo.spi.Plugin;

public final class Main {
    public static void main(String[] args) throws Exception {
        String name = "demo.plugin.GreetingPlugin";
        ClassLoader loader = Thread.currentThread().getContextClassLoader();

        System.out.println("1. Nap lop, chua yeu cau khoi tao");
        Class<?> candidate = Class.forName(name, false, loader);
        System.out.println("2. Class: " + candidate.getName());

        boolean compatible = Plugin.class.isAssignableFrom(candidate);
        System.out.println("3. Dung hop dong: " + compatible);
        if (!compatible) {
            throw new IllegalArgumentException("Not a Plugin: " + name);
        }

        System.out.println("4. Yeu cau JVM khoi tao lop");
        Class.forName(name, true, loader);

        System.out.println("5. Tao doi tuong");
        Plugin plugin = (Plugin) candidate.getDeclaredConstructor().newInstance();

        System.out.println("6. Kich hoat plugin");
        plugin.start();
    }
}
```

Lưu ý tên lớp provider nằm trong chuỗi cấu hình của host. Việc dùng `Class.forName` ở đây là ví dụ dạy học để nhìn thấy **ranh giới các giai đoạn**; một ứng dụng thực tế có thể lấy tên từ descriptor hoặc dùng `ServiceLoader`/registry.

### 6.5. Biên dịch và chạy bằng JDK 17+ trên PowerShell

Từ thư mục `loading-demo`, chạy:

```powershell
New-Item -ItemType Directory -Force -Path out\api,out\plugin,out\host | Out-Null

javac -d out\api api\src\demo\spi\Plugin.java
javac -cp out\api -d out\plugin plugin\src\demo\plugin\GreetingPlugin.java
javac -cp out\api -d out\host host\src\demo\host\Main.java

jar --create --file out\greeting-plugin.jar -C out\plugin .
java -cp "out\api;out\host;out\greeting-plugin.jar" demo.host.Main
```

Đầu ra tiêu chuẩn với các tệp trên:

```text
1. Nap lop, chua yeu cau khoi tao
2. Class: demo.plugin.GreetingPlugin
3. Dung hop dong: true
4. Yeu cau JVM khoi tao lop
    <clinit> GreetingPlugin
5. Tao doi tuong
    <init> GreetingPlugin
6. Kich hoat plugin
    start() GreetingPlugin
```

Mã in thông báo host không dấu tiếng Việt để dễ đối chiếu chính xác đầu ra trên mọi console. Trên macOS/Linux, dùng đường dẫn/lệnh shell tương đương và thay dấu phân cách classpath `;` bằng `:`.

### 6.6. Vì sao thứ tự này quan trọng?

- Sau dòng **1**, JVM tìm và liên kết lớp theo yêu cầu `Class.forName(name, false, loader)`; không có dòng `<clinit>` từ plugin.
- Dòng **2** chỉ lấy tên của đối tượng `Class`; không tạo instance.
- Dòng **3** kiểm tra kiểu có triển khai giao diện `Plugin`; chưa gọi mã nghiệp vụ của plugin.
- Sau dòng **4**, yêu cầu khởi tạo làm JVM thực thi khối `static` và in `<clinit>`.
- Sau dòng **5**, constructor được gọi để tạo instance và in `<init>`. Lớp đã khởi tạo, nên `<clinit>` không chạy lần thứ hai.
- Sau dòng **6**, host mới gọi `start()`; lúc này plugin thực hiện thao tác được định nghĩa trong hợp đồng.

Nếu **bỏ lời gọi `Class.forName(name, true, loader)`** nhưng vẫn giữ việc tạo instance, JVM sẽ phải khởi tạo `GreetingPlugin` trước khi constructor của nó chạy. Vì thế dòng `<clinit>` sẽ xuất hiện ở bước tạo đối tượng. Đây là lý do không thể dùng “đã gọi constructor” để suy ra lớp chỉ bắt đầu khởi tạo vào đúng lúc đó.

Nếu bỏ `greeting-plugin.jar` khỏi classpath, lời gọi `Class.forName(name, false, loader)` sẽ thất bại với `ClassNotFoundException`. Đây là lỗi **chưa nạp được lớp**, không phải lỗi do `start()`.

## 7. ServiceLoader và việc khởi tạo provider

Trong SPI trên classpath, `ServiceLoader` là cơ chế giúp host khám phá provider được công bố qua `META-INF/services/<tên-nhị-phân-service>`. Nó liên quan tới nạp lớp nhưng **không đồng nghĩa với toàn bộ vòng đời kích hoạt plugin**.

Ví dụ ở mức ý tưởng:

```java
ServiceLoader<Plugin> services = ServiceLoader.load(Plugin.class);

for (Plugin plugin : services) {
    plugin.start();
}
```

Đây là **đoạn bổ sung minh họa**, giả định `Plugin` được import và có provider đăng ký hợp lệ. `ServiceLoader.load(...)` chủ yếu tạo đối tượng loader; việc tìm và tạo provider thường diễn ra **lười** khi duyệt danh sách. Trong ví dụ classpath thông thường, lúc ServiceLoader thực sự tạo instance provider thì JVM phải đảm bảo lớp được khởi tạo trước constructor. Còn `plugin.start()` là quyết định riêng của host.

Hệ quả quan trọng: nếu host duyệt `ServiceLoader` để “kiểm tra xem có plugin nào” thì quá trình duyệt có thể đã **tạo đối tượng provider và chạy mã tĩnh/constructor**. Nếu muốn xem metadata trước khi chạy mã plugin, hãy thiết kế descriptor hoặc bước kiểm tra riêng, hoặc dùng API provider thích hợp và hiểu rõ giới hạn nạp/khởi tạo của nó. `ServiceLoader` không tự thực thi kiểm tra độ tin cậy, quyền truy cập, thứ tự ưu tiên hay quản lý `stop()`.

Với provider trên **named module** trong JPMS, quy tắc `provides ... with ...` còn cho phép dạng provider factory theo đặc tả. Chi tiết tạo provider tùy cách công bố; bài học cốt lõi vẫn là tách **việc tìm/định nghĩa kiểu** khỏi **mã được thực thi khi khởi tạo và bật plugin**.

## 8. Phân loại lỗi theo giai đoạn

| Lỗi hoặc dấu hiệu | Thường liên quan đến | Cách điều tra |
|---|---|---|
| `ClassNotFoundException` khi `Class.forName` | Không tìm được lớp cần nạp bằng loader được chọn | Kiểm tra tên nhị phân, classpath/JAR, bộ nạp hiện hành |
| `UnsupportedClassVersionError` | Bytecode không tương thích phiên bản JVM | So phiên bản JDK dùng biên dịch và chạy |
| `VerifyError` | Bytecode/kiểu không hợp lệ theo kiểm chứng | Kiểm tra bytecode, công cụ tạo bytecode và phụ thuộc |
| `NoClassDefFoundError` | Không thể tìm/định nghĩa lớp phụ thuộc hoặc lớp từng khởi tạo thất bại | Đọc thông điệp và nguyên nhân, phân biệt thiếu class với trạng thái khởi tạo lỗi |
| `NoSuchMethodError`, `IllegalAccessError` | Phân giải/lệnh dùng thành viên không tương thích thư viện lúc chạy | Kiểm tra phiên bản API/SPI và phương thức/chế độ truy cập |
| `ExceptionInInitializerError` | Lỗi khi thực thi mã khởi tạo tĩnh | Kiểm tra `cause` và khối `static`; tránh retry mù |
| `InvocationTargetException` từ reflection | Constructor/phương thức được gọi qua reflection ném lỗi | Kiểm tra ngoại lệ nguyên nhân; phân biệt với lỗi nạp/liên kết |
| `ClassCastException` khi ép kiểu provider | Không đúng hợp đồng hoặc hai classloader định nghĩa hai bản khác nhau của kiểu cùng tên | Kiểm tra định danh kiểu và loader của cả hai bên |
| `ServiceConfigurationError` khi duyệt SPI | Khai báo provider sai hoặc không tạo được provider theo ServiceLoader | Kiểm tra `META-INF/services`, constructor/factory, phụ thuộc và nguyên nhân |

**Không gán một loại lỗi vào duy nhất một thời điểm tuyệt đối.** Vì JVM có thể phân giải tham chiếu lười, lỗi liên kết có thể xuất hiện ở lần dùng sau, kể cả khi `Class.forName` và constructor trước đó đã thành công. Ghi lại stack trace, classloader và thời điểm host gọi API sẽ giúp định vị đúng nguồn lỗi.

## 9. Quy tắc thực hành khi thiết kế kích hoạt plugin

**Giữ khối static đơn giản.** Chỉ dùng cho trạng thái bất biến, khởi tạo thuần túy nếu thực sự cần. Tránh tự mở kết nối, khởi tạo thread nền, ghi file hoặc phát lệnh nghiệp vụ từ `static` vì host chưa chắc quyết định bật plugin.

**Kiểm tra hợp đồng trước khi tạo instance.** Ví dụ `Plugin.class.isAssignableFrom(candidate)` có thể phát hiện không tương thích kiểu đã nạp trước khi yêu cầu constructor. Tuy vậy, bước kiểm tra này không thay thế việc xác thực nguồn plugin, kiểm tra phiên bản/phụ thuộc hoặc xử lý lỗi runtime.

**Phân biệt “đã nạp” với “sẵn sàng phục vụ”.** Một trạng thái plugin manager hữu ích có thể là `DISCOVERED` → `VALIDATED` → `LOADED` → `CREATED` → `ACTIVE` → `STOPPED`, nhưng đó là **trạng thái nghiệp vụ do host đặt**, không phải bản sao của ba giai đoạn JVMS. Có thể một provider được nạp trước rồi mới được kích hoạt sau.

**Không coi `close()` là “hủy khởi tạo lớp”.** Lời gọi `stop()`/`close()` chỉ giải phóng tài nguyên mà plugin quản lý theo hợp đồng. JVM không có thao tác chuẩn “uninitialize class”; khả năng thu hồi lớp/bộ nạp phụ thuộc việc mọi đối tượng/tham chiếu liên quan đã có thể được thu gom. Muốn thay đổi phiên bản plugin trong cùng tiến trình cần chiến lược classloader và tài nguyên kỹ lưỡng, hoặc tách tiến trình.

**Giữ quyền kiểm soát ở host.** Host quyết định khi nào chấp nhận plugin, phương thức kích hoạt nào được gọi, khi nào ngắt, log lỗi, timeout hoặc rollback. Việc một lớp đã khởi tạo thành công chỉ cho biết một điều về JVM; không chứng minh plugin đúng hợp đồng nghiệp vụ hoặc an toàn.

## 10. Câu hỏi tự kiểm tra

1. **Có đối tượng `Class` có nghĩa đã chạy `static` chưa?** Không. Có thể yêu cầu nạp/liên kết mà chưa khởi tạo, ví dụ `Class.forName(name, false, loader)`.
2. **Preparation có chạy phép gán `static int counter = compute()` không?** Không. Biểu thức gọi `compute()` thuộc khởi tạo lớp; preparation thông thường tạo trường với giá trị mặc định theo quy tắc JVM.
3. **Vì sao lỗi `NoSuchMethodError` có thể xuất hiện lúc gọi plugin thay vì lúc nạp?** Vì một số tham chiếu có thể được phân giải lười khi cần dùng.
4. **Khối `static`, constructor và `start()` giống nhau ở chỗ nào?** Cả ba đều có thể chạy mã plugin, nhưng chúng diễn ra tại **ba cơ chế khác nhau**: khởi tạo lớp, tạo instance và kích hoạt nghiệp vụ.
5. **ServiceLoader tìm thấy provider có đồng nghĩa host đã bật plugin không?** Không; việc tìm/tạo provider và lời gọi `start()` là các quyết định khác nhau.
6. **Đóng plugin có chạy lại `<clinit>` khi mở lần sau không?** Không theo cách gọi `stop()/start()` trên cùng lớp đã khởi tạo. Muốn lớp mới mang cùng tên trong một loader khác là bài toán nạp lớp và vòng đời riêng.

**Bài tập:** Chạy ví dụ mục 6, sau đó (a) bỏ lệnh `Class.forName(name, true, loader)` và quan sát thời điểm `<clinit>`; (b) gọi `plugin.start()` hai lần và so số dòng `<clinit>`, `<init>` và `start()`; (c) bỏ plugin JAR khỏi classpath, ghi lại lỗi xảy ra trước bước nào. Giải thích mỗi kết quả bằng các giai đoạn JVM và vòng đời ứng dụng.

## Tài liệu tham khảo

- Java Virtual Machine Specification 17, Chương 5 – Loading, Linking, and Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- Java Language Specification 17, Chương 12 – Execution, Initialization: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- Java SE 17, `Class.forName(String, boolean, ClassLoader)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17, `java.util.ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
