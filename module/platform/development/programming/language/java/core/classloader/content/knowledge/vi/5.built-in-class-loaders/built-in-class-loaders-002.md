# Platform class loader trong JDK hiện đại

**Platform class loader** là một trong các class loader tích hợp của Java runtime từ **Java 9 trở đi**. Nó giúp mã Java và các class loader tùy biến truy cập các lớp thuộc **nền tảng Java** mà không cần giả định rằng tất cả lớp của Java SE/JDK đều do **bootstrap class loader** định nghĩa. Trên Java 17+, API để lấy loader này là `ClassLoader.getPlatformClassLoader()`.

Đây là điểm khác biệt quan trọng sau khi Java chuyển sang **Java Platform Module System (JPMS)**: một phần lớp nền tảng được định nghĩa bởi bootstrap loader, một phần bởi platform loader. Vì vậy, **một lớp nhìn thấy được từ platform loader chưa chắc do chính platform loader định nghĩa**. Bài học giải thích vị trí của loader tích hợp này, cơ chế ủy quyền, mối quan hệ với module, cách quan sát trên JDK 17+ và các lỗi thiết kế thường gặp.

## 1. Vì sao Java cần platform class loader?

Trước Java 9, người học thường nhìn thấy mô hình:

```text
Bootstrap ClassLoader
       ↑
Extension ClassLoader
       ↑
Application/System ClassLoader
       ↑
Custom ClassLoader
```

Trong các JDK hiện đại, cách trình bày cơ bản trở thành:

```text
Bootstrap loader (được JVM cung cấp; Java thường biểu diễn là null)
             ↑
Platform loader (ClassLoader.getPlatformClassLoader())
             ↑
Application/System loader (ClassLoader.getSystemClassLoader())
             ↑
Custom loader có parent là system loader, nếu chọn như vậy
```

Mũi tên `↑` biểu diễn **quan hệ parent/delegation điển hình**; không phải quan hệ `extends` của class Java và cũng không chứng minh mọi lookup thực tế đi đúng một đường thẳng. Loader tùy biến có thể chọn parent khác; các loader tích hợp có xử lý đặc biệt để hỗ trợ module.

Những thay đổi chính từ Java 9:

1. **Extension mechanism cũ bị loại bỏ.** Không còn dùng `jre/lib/ext` hoặc `java.ext.dirs` làm cơ chế cài extension tự động như JDK 8.
2. **Extension class loader được thay thế về vai trò/tên bằng platform class loader.** Đừng hiểu tên mới chỉ là đổi nhãn trong khi cơ chế extension directory vẫn còn hoạt động.
3. **Nhiều lớp Java SE/JDK nằm trong các module**, không nằm trong một `rt.jar` duy nhất. Các module nền tảng có thể được định nghĩa cho bootstrap hoặc platform loader.
4. **Application loader trong các JDK phổ biến từ Java 9 không còn được bảo đảm là `URLClassLoader`.** Không ép kiểu `(URLClassLoader) ClassLoader.getSystemClassLoader()` để thêm JAR.
5. **API công khai `ClassLoader.getPlatformClassLoader()` được bổ sung từ Java 9** để ứng dụng chọn một parent phù hợp khi muốn thấy các lớp nền tảng nhưng không mặc nhiên lấy application classpath làm namespace cha.

Platform loader là một thành phần nội bộ của **hệ thống nạp lớp ở runtime**. Nó không phải một JAR, không phải một JVM mới, không phải một class loader được ứng dụng tạo riêng cho từng package và không phải tên khác của thread context class loader.

## 2. Ba loader tích hợp và vai trò khác nhau

| Thành phần | API nhận diện | Vai trò chủ yếu | Lưu ý |
| --- | --- | --- | --- |
| **Bootstrap loader** | `SomeClass.class.getClassLoader() == null` thường biểu diễn bootstrap | Nạp/định nghĩa nhiều lớp nền tảng cốt lõi, trong đó có `java.lang.String` | Bootstrap không có object `ClassLoader` thông thường được expose cho Java; `null` ở đây có ý nghĩa đặc biệt. |
| **Platform loader** | `ClassLoader.getPlatformClassLoader()` | Cho phép truy cập toàn bộ các lớp nền tảng; định nghĩa một số lớp trong các module nền tảng, đồng thời thấy lớp do bootstrap định nghĩa | Từ Java 9; có tên triển khai built-in là `platform` trong JDK thông dụng. |
| **Application/System loader** | `ClassLoader.getSystemClassLoader()` | Thường định nghĩa các class trên application classpath/module path, cùng một số công cụ JDK | Loader hệ thống có thể tùy biến qua `java.system.class.loader`; đừng luôn đồng nhất với tên lớp triển khai cụ thể. |

**Tính nhìn thấy được (visibility)** và **định nghĩa lớp (defining loader)** là hai khái niệm khác nhau. Khi gọi `platform.loadClass("java.lang.String")`, platform loader có thể ủy quyền về bootstrap. Kết quả `Class<?>` là lớp `String` đã được bootstrap định nghĩa; không phải platform vừa định nghĩa một bản `String` mới.

Tương tự, application loader nhận `loadClass("java.lang.String")` có thể ủy quyền qua platform đến bootstrap. `ClassLoader.loadClass` được gọi trên loader nào không đủ để kết luận **defining loader** của kết quả là loader đó.

### Initiating loader và defining loader

Giả sử application loader yêu cầu nạp `java.lang.String`:

```text
Yêu cầu đến application loader
            │
            ▼
Application loader  ──ủy quyền──> Platform loader
                                    │
                                    └──ủy quyền──> Bootstrap loader
                                                       │
                                                       ▼
                                                 java.lang.String
                                                 được định nghĩa
```

- **Initiating loader:** loader mà JVM hoặc mã ứng dụng dùng để yêu cầu nạp một class; nó có thể được ghi nhận là đã khởi xướng nạp class ấy.
- **Defining loader:** loader thực sự định nghĩa class từ dữ liệu nhị phân hoặc cơ chế built-in. Runtime type identity phụ thuộc **tên nhị phân + defining loader**.
- **Kết quả `loadClass`:** object `Class<?>` của định nghĩa thực tế đã tìm được; việc gọi method trên một loader không tạo bản sao class ở loader đó.

Sơ đồ mô tả parent-first thông thường. `ClassLoader` cho phép các mô hình tùy biến; loader built-in biết về module nên còn có thể thực hiện delegation theo quan hệ module, không chỉ theo đường parent tuyến tính.

## 3. Chính xác platform class loader bảo đảm điều gì?

Javadoc Java 17 của `ClassLoader.getPlatformClassLoader()` quy định: **tất cả các platform classes đều nhìn thấy được từ platform loader**. Nhóm này gồm API nền tảng Java SE, lớp triển khai của chúng và các lớp runtime JDK thích hợp, được định nghĩa bởi platform loader **hoặc một ancestor của nó**.

Từ khẳng định này có thể suy ra:

- `platform.loadClass("java.lang.String")` tìm được `String` trên một JDK bình thường, nhưng `String.class.getClassLoader()` thường là `null` (bootstrap).
- Các lớp nền tảng khác có thể do platform loader định nghĩa. Phân công **từng module/từng class** là chi tiết có thể thay đổi giữa JDK releases hoặc implementation; không nên mã hóa bảng tên class cố định trong logic nghiệp vụ.
- `ClassLoader.getPlatformClassLoader()` trả về **loader**, không trả về tập các module hay toàn bộ tên class được định nghĩa bởi loader.
- Không có bảo đảm rằng mọi class nằm trên **application classpath** đều nhìn thấy được từ platform loader.
- Khả năng loader tìm được một `Class<?>` không thay thế các quy tắc **module readability**, `exports` và kiểm soát truy cập runtime của JPMS.

Một hiểu nhầm hay gặp: "**platform class loader là loader trực tiếp định nghĩa tất cả lớp của gói `java.*`**". Điều này sai. Chẳng hạn `java.lang.String` thuộc `java.base` và thường do bootstrap định nghĩa. Ngược lại, tên package bắt đầu bằng `java.` cũng không cung cấp API chính thức để xác định mọi defining loader; hãy quan sát đối tượng `Class` cụ thể.

### Quan hệ parent có phải là quy tắc tuyệt đối?

Với cấu hình JDK 17 phổ biến, platform loader là parent của application loader; parent của platform loader được biểu diễn như bootstrap (`null`). Tuy nhiên:

- `ClassLoader.getSystemClassLoader()` có thể được thay bằng loader do cấu hình hệ thống cung cấp qua `-Djava.system.class.loader=...`; không giả định mọi trường hợp `getSystemClassLoader().getParent() == getPlatformClassLoader()`.
- **Platform loader có thể phải delegate đến loader khác, kể cả application loader**, khi xử lý các module đã được nâng cấp/ghi đè và phụ thuộc module. Đây là ngoại lệ đã được ghi trong Javadoc `ClassLoader`.
- Trên hệ module, quan hệ **loader parent** và quan hệ **module reads** là hai đồ thị khác nhau. `Module X reads Module Y` không đồng nghĩa `class loader của X là con của class loader của Y`.
- Dù một loader có thể thấy class, quyền **link trực tiếp hoặc reflection** vẫn chịu ràng buộc của ngôn ngữ và JPMS.

## 4. Thực hành A — quan sát platform, system và bootstrap bằng Java 17+

Tạo một chương trình chạy độc lập duy nhất trong cây:

```text
platform-loader-lab/
└── src/
    └── demo/
        └── PlatformOverview.java
```

Nội dung **`src/demo/PlatformOverview.java`**:

```java
package demo;

public class PlatformOverview {
    public static void main(String[] args) throws ClassNotFoundException {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        Class<?> stringFromPlatform =
                platform.loadClass("java.lang.String");

        System.out.println("platform exists: " + (platform != null));
        System.out.println("platform != system: " + (platform != system));
        System.out.println("String reachable: " +
                (stringFromPlatform == String.class));
        System.out.println("String bootstrap: " +
                (String.class.getClassLoader() == null));
        System.out.println("app loaded by system: " +
                (PlatformOverview.class.getClassLoader() == system));
    }
}
```

Trong thư mục `platform-loader-lab`, với **JDK 17+ thông dụng, launcher mặc định**:

```sh
javac --release 17 -d out src/demo/PlatformOverview.java
java -cp out demo.PlatformOverview
```

**Stdout trong cấu hình mặc định của OpenJDK/HotSpot 17+**:

```text
platform exists: true
platform != system: true
String reachable: true
String bootstrap: true
app loaded by system: true
```

Giải thích theo từng dòng:

1. `ClassLoader.getPlatformClassLoader()` luôn trả về một platform loader hợp lệ cho JDK hỗ trợ API.
2. Platform và system là **hai loader phân biệt**. Không dùng tên class thực thi nội bộ để kiểm tra điều này.
3. `platform.loadClass("java.lang.String")` có thể nhìn thấy lớp do bootstrap định nghĩa; kết quả cùng identity với `String.class`.
4. `String.class.getClassLoader() == null` là cách Java thường biểu diễn việc `String` được định nghĩa bởi bootstrap trên JDK tương ứng.
5. `PlatformOverview` nằm trong `out`, được `-cp out` đưa vào application classpath; với launcher/default built-in system loader, defining loader của chương trình bằng system loader.

Nếu ứng dụng sử dụng custom system loader, agent, module layer khác hoặc một JVM implementation đặc biệt, một số chi tiết quan sát về defining loader có thể khác; đọc code và phạm vi stdout là **JDK OpenJDK/HotSpot 17+ mặc định**, không phải lời hứa độc lập mọi JVM.

### Đừng nhầm tên hiển thị với hợp đồng API

Trên nhiều bản OpenJDK hiện đại:

```java
System.out.println(ClassLoader.getPlatformClassLoader().getName());
System.out.println(ClassLoader.getSystemClassLoader().getName());
```

thường hiện:

```text
platform
app
```

Đây là đoạn **minh họa chèn vào `main` nếu muốn quan sát**, không phải chương trình độc lập. Tên `platform` và `app` là implementation notes trong Javadoc built-in loaders; phân tích ứng dụng nên dựa vào API và object identity, không vào `loader.getClass().getName()` hoặc chuỗi tên hiển thị.

## 5. Vì sao Java 9 thay đổi cách các lớp nền tảng được nạp?

Trước Java 9, cơ chế extension cho phép đặt JAR trong một thư mục của JRE để class loader mở rộng nhìn thấy mà ứng dụng không khai báo trong `-cp`. Điều này dẫn tới thói quen coi bootstrap + extension là một vùng classes ngoài application classpath.

Từ Java 9:

- JDK dùng **module image** runtime thay vì mô hình phân phối dựa trên `rt.jar` truyền thống. Trong JDK cài đặt thông dụng, nhiều class nền tảng được cung cấp qua hệ thống module và có thể quan sát qua URL `jrt:/...`; không nên cố tìm mọi class bằng cách mở `rt.jar`.
- **Platform class loader** được cung cấp qua API ổn định, phục vụ khả năng truy cập các lớp nền tảng một cách phù hợp mô hình module.
- Cơ chế `lib/ext`/`java.ext.dirs` để triển khai extension đã bị loại bỏ. Thư viện bên thứ ba phải được cấu hình thông qua **classpath**, **module path** hoặc cơ chế load/module layer được thiết kế rõ ràng.
- Legacy code giả định `getSystemClassLoader() instanceof URLClassLoader` hoặc `new URLClassLoader(urls, null)` nhìn thấy mọi Java SE classes cần được xem lại.

Không nên mô tả platform loader là "thư mục chứa extension JAR mới". Từ "platform" ở đây chỉ **vai trò của loader trong nền tảng Java**, không chỉ một đường dẫn tìm file.

## 6. Platform loader và JPMS: ba tầng cần tách

Có ba câu hỏi khác nhau khi ứng dụng chạy với modules:

1. **Module có được resolve vào boot layer hoặc layer phù hợp hay không?** Một module trong image/path không có nghĩa mọi module đều được chọn vào graph.
2. **Module được định nghĩa cho class loader nào?** Bootstrap/platform/application có thể tham gia; mapping phụ thuộc runtime.
3. **Một class/module khác được phép dùng API hay không?** Điều này liên quan `requires`/readability, `exports` và `opens`, không chỉ loader có tìm thấy bytes.

Ví dụ một module `app.module` khai báo:

```java
module app.module {
    requires java.sql;
}
```

Đây là **tệp `module-info.java` minh họa**, không độc lập để chạy. `requires java.sql` tạo quan hệ readability để mã trong module `app.module` sử dụng API exported của `java.sql`. Không có nghĩa class trong `java.sql` bắt buộc phải được application loader định nghĩa, cũng không có nghĩa platform loader sẽ tải mọi database driver do bên thứ ba phát hành.

Mở rộng góc nhìn:

| Thuật ngữ | Câu hỏi trả lời | Cần tránh suy luận |
| --- | --- | --- |
| Module resolution | Module nào tham gia cấu hình runtime? | "Có trên module path" = "đã resolved". |
| Readability | Module caller có đọc module đích? | Loader load được = compiler/runtime chắc chắn cho đọc. |
| Exports | Package có cho phép module ngoài truy cập public types? | Public class = luôn dùng được ở mọi module. |
| Opens | Package có mở cho deep reflection phù hợp? | Load class thành công = `setAccessible` luôn thành công. |
| Defining loader | Loader nào tạo runtime class identity? | Module name hoặc package name tự quyết định loader. |
| Parent delegation | Khi loader không xử lý, có ủy quyền cho loader khác? | Đây là đồ thị giống hệt `requires`. |

### Platform loader có phải chỉ nhìn thấy các module do chính nó định nghĩa?

Không. Javadoc quy định platform loader **nhìn thấy platform classes**, kể cả các lớp do ancestor (bootstrap) định nghĩa. Hơn nữa, trong một số tình huống **upgraded modules** cần tham chiếu module được định nghĩa bởi loader khác, platform loader có thể delegate ngoài parent chain (thậm chí tới application loader). Do đó sơ đồ bootstrap ← platform ← app vẫn rất hữu ích để học nhưng không phải mô hình tra cứu module tuyệt đối.

## 7. Thực hành B — dùng platform loader làm parent của loader tùy biến

Một lý do cụ thể để lấy platform loader là **làm parent của class loader do ứng dụng tự tạo**. Khi plugin chỉ cần các lớp nền tảng và muốn tránh vô tình nhìn thấy mọi class của application classpath qua parent, có thể chọn platform loader.

Tạo file:

```text
platform-parent-lab/
└── src/
    └── demo/
        ├── AppOnly.java
        └── ParentVisibility.java
```

**`src/demo/AppOnly.java`**:

```java
package demo;

public class AppOnly {
    public static String value() {
        return "in app classpath";
    }
}
```

**`src/demo/ParentVisibility.java`**:

```java
package demo;

public class ParentVisibility {
    public static void main(String[] args) throws Exception {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        ClassLoader plugin = new ClassLoader(platform) { };

        Class<?> core = plugin.loadClass("java.lang.String");
        System.out.println("platform API visible: " +
                (core == String.class));

        try {
            plugin.loadClass("demo.AppOnly");
            System.out.println("app class visible: true");
        } catch (ClassNotFoundException e) {
            System.out.println("app class visible: false");
        }

        Class<?> app = ClassLoader.getSystemClassLoader()
                .loadClass("demo.AppOnly");
        System.out.println("system sees app: " +
                (app == AppOnly.class));
    }
}
```

Biên dịch và chạy bằng JDK 17+ từ thư mục `platform-parent-lab`:

```sh
javac --release 17 -d out src/demo/AppOnly.java src/demo/ParentVisibility.java
java -cp out demo.ParentVisibility
```

**Stdout trên JDK OpenJDK/HotSpot mặc định với classpath như trên:**

```text
platform API visible: true
app class visible: false
system sees app: true
```

**Vì sao?**

- `new ClassLoader(platform) { }` tạo một subclass ẩn danh dùng **default parent-first** của `ClassLoader`, không ghi đè `findClass` và không có logic đọc file/JAR riêng.
- Đối với `java.lang.String`, loader mới ủy quyền lên platform/bootstrap và tìm thấy class.
- Đối với `demo.AppOnly` trên **unnamed application classpath**, platform loader không dùng application classpath làm nguồn tra cứu theo cơ chế mặc định; loader mới cũng không tự đọc file. Kết quả là `ClassNotFoundException`.
- System loader có thể tìm `demo.AppOnly` từ `-cp out`, do đó trả về cùng `Class` với `AppOnly.class`.

**Phạm vi của ví dụ:** Đó là một loader không có cách tự nạp plugin, dùng để minh họa **ranh giới parent visibility**. Nó **chưa phải plugin loader hoàn chỉnh**. Plugin loader thực tế phải có nguồn bytecode, định nghĩa package/module hợp lệ, quản lý dependency và cơ chế chia sẻ API thích hợp.

### Vì sao không luôn chọn parent là `null`?

Constructor `ClassLoader(null)` dùng bootstrap làm parent theo cơ chế `ClassLoader` thông thường. Nhưng từ Java 9, **không bảo đảm tất cả platform classes đều nhìn thấy được qua bootstrap**. Plugin cần dùng Java SE API thuộc module do platform loader định nghĩa có thể thất bại khi parent chỉ là bootstrap.

Chọn `ClassLoader.getPlatformClassLoader()` làm parent giúp loader con có quyền **nhìn thấy đầy đủ platform classes** theo Javadoc. Nếu plugin cần đồng thời dùng các application classes như `com.myapp.spi.Plugin` được định nghĩa bởi application loader, parent là platform có thể không phù hợp: cần thiết kế rõ class loader dùng chung cho SPI hoặc cơ chế module layer/delegation phù hợp. Đừng thay parent tùy tiện với kỳ vọng chỉ thay hiệu năng.

### Khi nào lại chọn system loader làm parent?

Nếu plugin cần truy cập nhiều API của chính ứng dụng đang chạy, system loader (hoặc một loader chứa shared API) có thể phù hợp hơn. Đổi lại, nếu plugin có dependency cùng tên với ứng dụng, parent-first có thể khiến class của ứng dụng được ưu tiên; từ đó gây version conflict.

Không có một parent duy nhất phù hợp cho mọi framework. Tiêu chí chọn là **những lớp nào cần chia sẻ identity** giữa core và plugin, những lớp nào cần cách ly, và module nào cần được nhìn thấy.

## 8. Thực hành C — quan sát module và defining loader mà không dựa vào tên nội bộ

Tạo một file độc lập `src/demo/ModuleView.java`:

```java
package demo;

public class ModuleView {
    public static void main(String[] args) {
        Class<?> platformClass = java.sql.Driver.class;

        System.out.println("module: " +
                platformClass.getModule().getName());

        ClassLoader loader = platformClass.getClassLoader();
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        ClassLoader system = ClassLoader.getSystemClassLoader();

        String owner = loader == null ? "bootstrap"
                : loader == platform ? "platform"
                : loader == system ? "system" : "other";

        System.out.println("owner: " + owner);
        System.out.println("visible from platform: " +
                canLoad(platform, platformClass.getName(), platformClass));
    }

    private static boolean canLoad(ClassLoader loader,
                                   String name,
                                   Class<?> expected) {
        try {
            return loader.loadClass(name) == expected;
        } catch (ClassNotFoundException e) {
            return false;
        }
    }
}
```

Biên dịch và chạy từ thư mục bài thực hành bằng JDK 17+ đầy đủ, hỗ trợ module `java.sql`:

```sh
javac --release 17 -d out src/demo/ModuleView.java
java -cp out demo.ModuleView
```

Output được thiết kế để **phân biệt thông tin ổn định và thông tin tùy JVM**:

```text
module: java.sql
owner: <bootstrap hoặc platform, tùy phân công của JDK>
visible from platform: true
```

Dòng `owner` trên đây là **sơ đồ kết quả minh họa**, ký hiệu trong dấu `<...>` không phải stdout nguyên văn. Hãy chạy chương trình để xem loader thực tế; trên các bản OpenJDK phổ biến, `java.sql` thường do platform loader định nghĩa, nhưng bài học không gắn một module cụ thể với defining loader như hợp đồng ổn định. Dòng module `java.sql` và khả năng nhìn thấy qua platform là đặc tính được quan sát/đảm bảo khi chạy trên JDK đầy đủ như mô tả. Với runtime image tạo qua `jlink` hoặc cấu hình giới hạn module, thiếu module `java.sql` có thể khiến chương trình biên dịch/chạy không phù hợp; cần đảm bảo module đó hiện diện.

Giá trị của chương trình: nó hỏi **chính đối tượng `Class<?>`** xem module và loader, sau đó dùng `platform.loadClass` để thử visibility. Đừng so sánh tên JVM internal loader class, vì không có bảo đảm tương thích nhị phân khi nhà cung cấp JDK đổi implementation.

## 9. Phân biệt platform loader với Thread Context Class Loader (TCCL)

Platform loader là **một loader built-in** xác định qua API static `ClassLoader.getPlatformClassLoader()`. Trong khi đó, **Thread Context Class Loader** là thuộc tính thay đổi được của từng thread:

```java
ClassLoader context = Thread.currentThread().getContextClassLoader();
```

Đây là đoạn code **minh họa** có thể đặt trong `main`. Trên JVM launcher thông dụng, context loader ban đầu của main thread thường là system loader. Nhưng framework có thể thay nó để thực hiện discovery/nạp plugin.

Không nên suy luận:

```text
Thread.currentThread().getContextClassLoader()
    == ClassLoader.getPlatformClassLoader()
```

là điều mặc định, hay mọi lệnh `Class.forName` tự động dùng context loader. Có sự khác biệt quan trọng:

- `Class.forName(String)` dùng loading context của lớp gọi theo API Java, đồng thời **yêu cầu initialization**.
- `Class.forName(String, boolean, ClassLoader)` dùng loader được truyền trực tiếp, có thể chọn không initialization.
- `ServiceLoader.load(Class<S>)` thường dùng **context class loader của thread hiện tại** để tìm provider; `ServiceLoader.load(Class<S>, ClassLoader)` cho phép truyền loader.
- `ClassLoader.getPlatformClassLoader()` chỉ cung cấp **object loader nền tảng**; không tự thay đổi TCCL của thread.

Ví dụ JDBC: `java.sql.Driver` là **API thuộc nền tảng**; driver do nhà cung cấp ứng dụng đưa vào classpath/module path là **mã bên thứ ba**. Tìm thấy `java.sql.Driver` qua platform loader không đảm bảo platform loader thấy tất cả các class triển khai driver. Nếu framework tìm driver/provider theo TCCL hoặc ServiceLoader, loader dùng để discovery có thể là system/plugin loader. Chỉ cần thay TCCL cũng có thể đổi tập provider tìm thấy, dù platform loader không đổi.

## 10. Những khác biệt quan trọng khi chọn parent của custom loader

Có thể minh họa quyết định qua bảng sau:

| Mục tiêu | Parent đáng cân nhắc | Rủi ro phải kiểm soát |
| --- | --- | --- |
| Plugin cần Java platform API, muốn tách khỏi ứng dụng | `ClassLoader.getPlatformClassLoader()` | Không thấy application SPI/SDK nếu không tạo kênh chia sẻ rõ ràng. |
| Plugin cần interface/core libraries của ứng dụng | System loader hoặc loader chứa các shared API | Parent-first có thể khiến plugin dùng phiên bản dependency ở core. |
| Cô lập tập class tùy biến ở mức thấp | Loader riêng với kế hoạch delegation cụ thể | Type identity, package sealing, module access, resource lookup, TCCL. |
| Legacy loader từng dùng parent `null` cho mọi class Java | Chuyển sang platform parent nếu thực sự cần toàn bộ Java SE/JDK API | Giữ nguyên `null` có thể thiếu platform-defined classes sau Java 9. |

**Không thể chỉ thay platform/system parent để tạo sandbox bảo mật.** Class loader chủ yếu giải quyết định nghĩa và không gian tên của lớp. Ranh giới bảo mật, quyền truy cập file/network và thực thi mã không đáng tin cần cơ chế độc lập; class loader cách ly tên không tự làm code trở nên an toàn.

**Không dùng platform loader như kho lưu thư viện ứng dụng.** `ClassLoader.getPlatformClassLoader()` không cung cấp API để thêm tùy ý JAR vào platform path. Nếu ứng dụng muốn hot-load JAR, hãy thiết kế loader riêng hoặc module layer và vòng đời phù hợp.

### Class identity là điểm phải kiểm tra

JVM định danh runtime class/interface bằng **(binary name, defining loader)**. Nếu `com.example.spi.Plugin` xuất hiện trong hai JAR và bị hai loaders định nghĩa riêng, hai class có thể cùng `getName()` nhưng **không assignable cho nhau**. Điều này gây `ClassCastException` hoặc `LinkageError` tùy ngữ cảnh.

Một plugin dùng platform parent nhưng tự nạp bản sao interface SPI của ứng dụng có thể không cast được sang interface SPI mà app loader định nghĩa. Hãy đặt **shared SPI** dưới một loader chung trong cấu trúc mà cả hai phía thật sự dùng, hoặc có lớp chuyển dữ liệu qua ranh giới. Đừng lấy `getName()` giống nhau làm bằng chứng identity giống nhau.

## 11. Quan sát ứng dụng thực tế bằng công cụ JDK

### 11.1. Xem class đến từ module/JAR nào

Với ví dụ A:

```sh
java -Xlog:class+load=info -cp out demo.PlatformOverview
```

Đây là **Unified Logging** trên các JVM hỗ trợ, tiêu biểu là HotSpot. Log có nhiều dòng và thứ tự phụ thuộc runtime, nên không có stdout cố định cho lệnh này. Các dòng load thường kèm tên class và nguồn như `jrt:/java.base` hoặc đường dẫn classpath. **Nguồn class bytes không tự cho biết toàn bộ quan hệ parent**; kết hợp với `getClassLoader()` để nhận diện defining loader.

### 11.2. Kiểm tra các module có trong JDK

```sh
java --list-modules
java --describe-module java.sql
```

Dùng `java --list-modules` để biết module nào có trong runtime image hiện tại; `java --describe-module` cho thông tin module. Danh sách xuất ra là dữ liệu cấu hình, **không trực tiếp nói loader nào định nghĩa từng class**. Nếu đang dùng `jlink` để tạo custom image, hãy kiểm tra module có hiện diện trước khi chạy ví dụ C.

### 11.3. In quan hệ parent trong môi trường đang chạy

Có thể thêm vào `main` của ví dụ A:

```java
System.out.println(
        ClassLoader.getSystemClassLoader().getParent()
                == ClassLoader.getPlatformClassLoader());
System.out.println(
        ClassLoader.getPlatformClassLoader().getParent() == null);
```

Trong OpenJDK/HotSpot mặc định, thường in hai dòng `true`. Đây là đoạn **chèn bổ sung**, không phải file Java độc lập. Với custom system loader hoặc cấu hình đặc biệt, không dựa vào giả định quan hệ parent luôn giống ví dụ.

## 12. Tình huống lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Kiểm tra/khắc phục |
| --- | --- | --- |
| `ClassNotFoundException` khi dùng loader với parent `null` | Lớp Java SE mong muốn được platform, không phải bootstrap, định nghĩa; hoặc phụ thuộc khác không thấy được | Kiểm tra `getPlatformClassLoader()`; đối chiếu module hiện diện trong runtime; cân nhắc platform parent. |
| `ClassNotFoundException` với app class khi dùng platform parent | Platform loader không tìm class tùy ý trong unnamed application classpath | Thiết kế parent phù hợp hoặc thêm nguồn class riêng cho child loader; không "nhét" app JAR vào platform. |
| `ClassCastException` dù binary name giống | Hai defining loaders độc lập định nghĩa cùng API | Quan sát `getClassLoader()` của hai `Class`; tổ chức lại shared SPI và delegation. |
| `LinkageError` với loading constraint | Descriptor qua các loader yêu cầu cùng identity nhưng nhận class không tương thích | Kiểm tra full stacktrace, defining loaders, phiên bản API và module graph. |
| `IllegalAccessError` / `InaccessibleObjectException` | Ràng buộc runtime access/module exports/opens | Kiểm tra `requires`, `exports`, `opens` và cách sử dụng reflection. |
| Legacy `java.ext.dirs` không còn hoạt động | Extension mechanism của JDK 8 đã bị loại bỏ | Di chuyển dependency sang `-cp`, `--module-path`, hoặc loader riêng. |
| `ClassCastException` khi ép system loader thành `URLClassLoader` | Ứng dụng phụ thuộc implementation JDK 8 | Bỏ ép kiểu; dùng API loader thích hợp hoặc thiết kế nạp riêng. |
| ServiceLoader không tìm driver/provider | TCCL, module `provides/uses`, classpath hoặc layer khác dự tính | Kiểm tra discovery loader, module graph và cấu hình provider. |
| Có module trên path nhưng class vẫn không truy cập | Module chưa resolved hoặc thiếu quyền readability/exports | Kiểm tra `--add-modules`/root modules và descriptor; không chỉ xem class loader. |

**Cách debug có trình tự:**

1. Xác định **tên class được yêu cầu**, loader nào khởi tạo yêu cầu nạp và API phát sinh lỗi.
2. In **defining loader** của `Class` (nếu đã lấy được), dùng `getClassLoader()`; `null` biểu diễn bootstrap trong ngữ cảnh này.
3. Kiểm tra **classpath/module path thực sự lúc chạy**, kể cả custom runtime image và module graph.
4. Đối chiếu **parent của custom loader**: `null`, platform, system hay loader cung cấp shared API?
5. Nếu class tìm thấy mà vẫn lỗi, kiểm tra **resolution**, binary API, access rules, module exports/opens và TCCL.
6. Thực hiện lại từ quy trình chạy tối giản xác định JDK, tránh phán đoán chỉ dựa vào tên file JAR.

### Phân biệt những lệnh gọi hay bị nhầm

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
Class<?> clazz = platform.loadClass("java.lang.String");
Class<?> loaded = Class.forName("java.lang.String", false, platform);
```

Đây là đoạn minh họa có thể đặt trong method có `throws ClassNotFoundException`. Cả hai API đều cho phép nhận lớp theo tên nhị phân và loader; `Class.forName` có tham số `initialize=false` để không yêu cầu initialization. `loadClass(String)` thường cũng không yêu cầu initialization. Truy xuất đối tượng `Class<?>` **không đồng nghĩa đã tạo instance**.

## 13. Lỗi hiểu nhầm cần tránh

- **"Platform class loader chính là bootstrap loader."** Không: platform là object loader riêng, còn bootstrap thường được biểu diễn bằng `null`.
- **"Mọi lớp `java.*` do platform định nghĩa."** Không: có lớp do bootstrap định nghĩa và vẫn nhìn thấy từ platform.
- **"Platform loader tải mọi thư viện ứng dụng."** Không: classpath ứng dụng thông thường do application/system loader xử lý.
- **"Platform loader là Extension loader y nguyên với thư mục `lib/ext`."** Không: cơ chế extension directory cũ đã bị loại bỏ ở Java 9.
- **"Loader parent hierarchy luôn trùng module dependency graph."** Không: JPMS readability, định nghĩa module và class loader là các quan hệ khác nhau.
- **"Platform chỉ có thể hỏi bootstrap, không bao giờ delegate ngược."** Không: Javadoc có trường hợp module upgrade cần nhìn class ở application loader.
- **"`getPlatformClassLoader()` thay thế TCCL."** Không: TCCL là thuộc tính thread có thể thay đổi, dùng bởi một số discovery APIs.
- **"Có thể dùng platform parent để cách ly bảo mật hoàn toàn plugin."** Không: class loader chủ yếu phân chia namespace/visibility; security cần cơ chế khác.
- **"Class cùng tên là cùng kiểu."** Không: identity còn phụ thuộc defining loader.
- **"Platform loader nào cũng là `URLClassLoader` nên thêm URL được."** Không: không phụ thuộc implementation nội bộ.

## 14. Câu hỏi tự kiểm tra

**1. Platform loader được giới thiệu từ Java nào?** Từ Java 9, qua `ClassLoader.getPlatformClassLoader()`.

**2. Vì sao platform loader nhìn thấy `java.lang.String` dù defining loader của `String` là bootstrap?** Vì platform có thể ủy quyền lên bootstrap; visibility khác defining identity.

**3. Tại sao parent `null` có thể gây lỗi sau khi nâng cấp từ Java 8 lên Java 17?** Vì Java 9+ không bảo đảm mọi lớp nền tảng đều được bootstrap định nghĩa; một số nằm ở platform loader.

**4. Chọn platform làm parent của custom plugin loader có tự nạp class trên application classpath không?** Không. Loader con phải có nguồn tự tìm class, hoặc quan hệ delegation được thiết kế để thấy application classes.

**5. Hai class cùng tên nạp từ hai custom loaders khác nhau có luôn tương đương không?** Không. Defining loader là một phần của runtime type identity.

**6. Mã chạy trong module `app.module` thấy API `java.sql` thì có phải app loader định nghĩa tất cả class `java.sql`?** Không. Module readability và loader mapping là hai vấn đề riêng.

**7. Vì sao không ép kiểu system loader về `URLClassLoader`?** Vì implementation của system loader không được đặc tả phải là `URLClassLoader`, và các JDK từ Java 9 đã thay đổi.

**8. Khi nào dùng TCCL thay vì platform loader?** Khi API/framework cần khám phá provider hoặc tài nguyên trong context của thread/plugin; điều này có mục đích khác với lấy platform loader làm parent.

## 15. Tài liệu chuẩn và hướng mở rộng

- [Java SE 17 `ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): mục **Run-time Built-in Class Loaders**, `getPlatformClassLoader()`, `getSystemClassLoader()`, `getParent()` và delegation.
- [Java SE 17 `Class` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader()`, `getModule()` và runtime class metadata.
- [Java SE 17 `Module` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html): module identity, readability và quan hệ module.
- [JDK Migration Guide — New Class Loader Implementations](https://docs.oracle.com/en/java/javase/15/migrate/): migration từ extension mechanism sang platform class loader và cảnh báo về parent `null`.
- [JEP 261 — Module System](https://openjdk.org/jeps/261): bối cảnh module path, runtime image và built-in loader từ Java 9.

**Ghi nhớ:** platform class loader là **điểm truy cập ổn định đến các lớp nền tảng** và là một lựa chọn parent hữu ích cho loader tùy biến trên JDK hiện đại. Khi phân tích một class, hãy tách bạch **nó thuộc module nào**, **loader nào định nghĩa nó**, **loader nào nhìn thấy nó**, và **caller có quyền truy cập nó hay không**. Bốn câu hỏi này giúp tránh phần lớn nhầm lẫn khi di chuyển ứng dụng Java 8 lên 17+ hoặc thiết kế hệ thống plugin.
