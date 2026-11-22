# Vì sao thay JAR trên đĩa không làm lớp đã nạp tự đổi mã

Trong ứng dụng Java cho phép cài hoặc nâng cấp plugin lúc chạy, một thao tác có vẻ đơn giản là **chép JAR phiên bản mới đè lên JAR cũ**. Nhưng sau khi chép, lời gọi vào đối tượng plugin đang chạy vẫn thực hiện logic cũ. Đây là hành vi đúng theo mô hình **class loading và class identity** của JVM, không phải lỗi đồng bộ dữ liệu hay do hệ điều hành chưa cập nhật file.

**Nguyên tắc quan trọng nhất:** *JAR là nguồn chứa bytecode để class loader nạp; còn `Class` đã được JVM định nghĩa là thực thể runtime có danh tính và vòng đời riêng. Thay nội dung JAR trên đĩa không tự định nghĩa lại `Class`, không cập nhật instance cũ, và không khiến JVM tạo lại class loader.*

Khi muốn cập nhật một plugin, cần phân biệt ba việc:

1. **Thay artifact**: có một JAR mới trên ổ đĩa.
2. **Nạp phiên bản mới**: tạo class loader/layer phù hợp để định nghĩa các class từ JAR mới.
3. **Chuyển hoạt động sang phiên bản mới**: đổi registry, route các lời gọi mới, hoàn tất hoặc hủy có kiểm soát các lời gọi cũ và giải phóng tài nguyên.

Chỉ hoàn thành việc (1) **không** tự động hoàn thành (2) và (3).

## 1. Khi Java nạp class từ JAR thì điều gì xảy ra?

Xét file `plugins/report.jar` chứa class `com.example.report.ReportPlugin`. Khi ứng dụng cần class đó, một class loader có thể tìm bytecode trong JAR, chuyển byte thành định nghĩa class và JVM tạo đối tượng metadata kiểu `java.lang.Class`. Sau đó class có thể được liên kết, khởi tạo và thực thi theo vòng đời JVM.

```text
Trên đĩa: plugins/report.jar (bytecode v1)
                   |
                   v
       ClassLoader tìm class theo tên
                   |
                   v
          JVM define/load Class
                   |
                   v
  Class<ReportPlugin> đã được định nghĩa
                   |
                   +--> tạo ReportPlugin instance A
                   +--> tạo ReportPlugin instance B
                   +--> JIT có thể tối ưu đường thực thi
                   
Sau đó: report.jar được thay bằng bytecode v2
                   |
                   X (không có cơ chế tự động)
                   |
     Class v1, instance A và B không tự biến thành v2
```

JVM có những giai đoạn khác nhau: **loading, linking, initialization**. Từ bytecode trong artifact, JVM xác lập một class với metadata và quan hệ loader. Khi đã được định nghĩa, class đó **không được tải lại một cách thông thường dưới cùng danh tính chỉ vì file bên ngoài đổi**.

Một số hệ quả:

- `new ReportPlugin()` dùng class đã được loader giải quyết có thể tiếp tục tạo instance **v1**, ngay cả khi file JAR ở đường dẫn cũ chứa byte mới.
- Instance hiện có giữ class của chính nó; sửa file JAR không thay mã phương thức của instance đó.
- JIT compiler tối ưu mã **của class runtime**; quá trình JIT/GC không có nghĩa JVM sẽ tự thăm dò file JAR để cập nhật bytecode.
- Nếu class vẫn chưa từng được nạp, một lời tìm kiếm sau khi file đổi có thể bị ảnh hưởng bởi cache, loader và trạng thái JAR. Vì thế có nguy cơ **trộn phiên bản** giữa các class cũ và các class được nạp sau; không nên dùng ghi đè JAR làm chiến lược cập nhật.

Nên coi một bản JAR được đưa vào vận hành như một **artifact bất biến**. Mỗi lần phát hành dùng đường dẫn hoặc tên có phiên bản, rồi để một loader/layer mới đọc bản đó.

## 2. Danh tính class gồm tên và class loader định nghĩa

Một điểm rất quan trọng của Java là **hai class có cùng binary name vẫn có thể là hai kiểu runtime khác nhau**, nếu chúng được định nghĩa bởi hai class loader khác nhau.

Có thể hình dung:

```text
DefiningLoader#1 + "com.example.Plugin" => Class A (v1)
DefiningLoader#2 + "com.example.Plugin" => Class B (v2)

Class A.getName().equals(Class B.getName())  == true
Class A == Class B                           == false
```

Danh tính kiểu runtime của một class được quyết định bởi **binary name và defining class loader**. Không thể dùng riêng tên class hay tên file JAR để kết luận hai class có cùng kiểu.

Vì vậy:

- `Class<?> oldClass` và `Class<?> newClass` có thể có cùng `getName()` nhưng `oldClass != newClass`.
- Đối tượng được tạo từ class thuộc loader cũ không tự trở thành instance của class thuộc loader mới.
- Cố ép kiểu một object định nghĩa bởi loader A sang kiểu **cùng tên** do loader B định nghĩa có thể gặp `ClassCastException`.
- Các kiểu trong chữ ký plugin phải được quản lý cẩn thận: nếu plugin tự đóng gói một bản interface API của host và loader định nghĩa lại interface ấy, ngay cả các phương thức nhìn giống nhau cũng có thể không tương thích kiểu.
- Parent delegation có thể làm class loader mới lấy class từ parent thay vì từ JAR mới, khiến việc tưởng rằng đã chuyển phiên bản thực chất vẫn gọi mã cũ.

### 2.1. Cùng một loader không thể cứ định nghĩa lại cùng tên

Với cơ chế nạp class thông thường, một `ClassLoader` ghi nhớ các class nó đã nạp/định nghĩa. Khi yêu cầu cùng binary name lần nữa, `loadClass` thường trả class đã được nạp theo quy tắc delegation; nó **không tự mở lại JAR để thay bytecode cũ**.

Một class loader cũng không được định nghĩa lần thứ hai một class trùng binary name trong cùng namespace loader theo `defineClass` như cách nạp thông thường; nỗ lực định nghĩa trùng có thể gây `LinkageError`. Vì thế “xóa cache ứng dụng rồi gọi `loadClass` lại” **không** tương đương với reload class đã tồn tại.

Không phải mọi thứ có tên “reload” đều tái định nghĩa Java class. Phải đọc hợp đồng cụ thể của framework/loader để biết nó reload cấu hình, service list, resource hay **thực sự tạo runtime class mới**.

## 3. Ví dụ Java 17 chạy được: cùng tên class, hai JAR, hai phiên bản

Ví dụ dùng **hai JAR có đường dẫn khác nhau** để tránh lỗi ghi đè file đang được mở trên Windows/Linux và để kết quả ổn định. Nó cho thấy trong **cùng một JVM**, bản v1 vẫn thực thi được sau khi bản v2 đã được nạp bởi loader khác.

### 3.1. Chuẩn bị hai phiên bản mã nguồn

Cấu trúc dự án:

```text
project/
  v1/
    src/demo/plugin/Greeting.java
  v2/
    src/demo/plugin/Greeting.java
  PluginSwapDemo.java
```

Nội dung `v1/src/demo/plugin/Greeting.java`:

```java
package demo.plugin;

public final class Greeting {
    public String say() {
        return "v1";
    }
}
```

Nội dung `v2/src/demo/plugin/Greeting.java`:

```java
package demo.plugin;

public final class Greeting {
    public String say() {
        return "v2";
    }
}
```

Hai class có **cùng package, tên và public API**. Chỉ thân phương thức khác nhau.

### 3.2. Chương trình host dùng hai URLClassLoader

Tệp `PluginSwapDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class PluginSwapDemo {

    static String message(Class<?> type) throws Exception {
        Object instance = type.getConstructor().newInstance();
        return (String) type.getMethod("say").invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        URL oldJar = Path.of(args[0])
                .toAbsolutePath().toUri().toURL();
        URL nextJar = Path.of(args[1])
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader oldLoader = new URLClassLoader(
                    new URL[] {oldJar},
                    ClassLoader.getPlatformClassLoader());
             URLClassLoader newLoader = new URLClassLoader(
                    new URL[] {nextJar},
                    ClassLoader.getPlatformClassLoader())) {

            Class<?> oldClass = Class.forName(
                    "demo.plugin.Greeting", true, oldLoader);
            Class<?> newClass = Class.forName(
                    "demo.plugin.Greeting", true, newLoader);

            System.out.println("old=" + message(oldClass));
            System.out.println("new=" + message(newClass));
            System.out.println("sameName="
                    + oldClass.getName().equals(newClass.getName()));
            System.out.println("sameClass=" + (oldClass == newClass));
            System.out.println("sameLoader="
                    + (oldClass.getClassLoader()
                       == newClass.getClassLoader()));
            System.out.println("oldStill=" + message(oldClass));
        }
    }
}
```

**Vì sao parent là platform class loader?** Ví dụ `Greeting` chỉ dùng API JDK, nên có thể chọn `ClassLoader.getPlatformClassLoader()` để tránh vô tình lấy một `demo.plugin.Greeting` cùng tên từ application classpath. **Đây chỉ là cách tổ chức demo**. Trong kiến trúc plugin thực tế, parent thường cần chia sẻ **interface API ổn định của host** và các dependency dùng chung; chọn parent sai sẽ làm plugin không nạp được lớp API hoặc tạo type identity khác.

### 3.3. Biên dịch, đóng JAR và chạy

Từ thư mục `project`, với JDK 17+:

```bash
javac -d v1/classes v1/src/demo/plugin/Greeting.java
javac -d v2/classes v2/src/demo/plugin/Greeting.java

jar --create --file v1.jar -C v1/classes .
jar --create --file v2.jar -C v2/classes .

javac PluginSwapDemo.java
java PluginSwapDemo v1.jar v2.jar
```

Các lệnh `javac` và `jar` có cú pháp giống nhau trên PowerShell/CMD và bash khi chạy từ thư mục dự án có cấu trúc trên. Lệnh dùng đường dẫn không có ký tự phân tách classpath dành riêng cho hệ điều hành.

Stdout đã kiểm tra khi chạy chương trình:

```text
old=v1
new=v2
sameName=true
sameClass=false
sameLoader=false
oldStill=v1
```

**Giải thích từng kết quả:**

- `old=v1`: class do `oldLoader` định nghĩa đọc bytecode từ `v1.jar`.
- `new=v2`: class do `newLoader` định nghĩa đọc bytecode từ `v2.jar`.
- `sameName=true`: hai class đều tên `demo.plugin.Greeting`.
- `sameClass=false` và `sameLoader=false`: JVM coi chúng là hai kiểu khác nhau vì defining loader khác nhau.
- `oldStill=v1`: sau khi lớp v2 xuất hiện trong JVM, **lớp cũ không bị viết lại**; lời gọi qua `oldClass` vẫn thực thi v1.

Ví dụ này minh họa **nạp hai phiên bản** theo cách an toàn và quyết định được kết quả, không thực hiện xóa/ghi đè JAR đang được sử dụng. Nó cũng không tự chuyển request thật của ứng dụng từ v1 sang v2: việc chuyển route phải được lập trình riêng.

## 4. Vì sao ghi đè cùng một đường dẫn JAR có thể tạo kết quả khó lường?

Giả sử ứng dụng đang dùng:

```text
plugins/analytics.jar   -> đã được nạp từ v1
```

Sau đó triển khai bằng cách ghi đè:

```text
plugins/analytics.jar   -> nội dung file v2
```

Sẽ có các yếu tố độc lập:

| Thành phần | Sau khi ghi đè file | Kết luận |
|---|---|---|
| `Class` đã định nghĩa của v1 | Vẫn là đối tượng kiểu runtime v1 | Không tự đổi thành v2 |
| Instance v1 đang được giữ trong registry | Vẫn tham chiếu class/loader cũ | Các lời gọi tiếp theo vẫn có thể chạy v1 |
| Method đã được JIT tối ưu | Dựa trên class runtime đã định nghĩa | Không phải cơ chế thăm dò JAR trên đĩa |
| Class chưa được nạp bởi loader cũ | Có thể bị ảnh hưởng bởi cache, handle JAR, nội dung file mới hoặc lỗi I/O | Không thể dùng làm bảo đảm hot reload |
| `URLClassLoader` đang giữ JAR | Có thể giữ handle/cache đến JAR cũ tùy môi trường | Ghi đè có thể bị chặn hoặc gây trạng thái không nhất quán |
| `getResource(...)` / resource stream | Cách mở URL/cache/resource có thể khác đường nạp class | Không chứng minh bytecode của class cũ đã thay |
| Class loader mới chỉ vào JAR mới | Có thể định nghĩa các class mới từ v2 khi cấu hình đúng | Vẫn cần route chuyển phiên bản |

### 4.1. Đường dẫn ổn định không có nghĩa bytecode được cập nhật

`ClassLoader` và `URLClassLoader` không phải file watcher. Chúng **không tự đăng ký** theo dõi thời điểm file sửa, tự xóa `Class`, hay tự gọi lại `defineClass` cho kiểu đã nạp. Một đường dẫn như `plugins/current.jar` có thể đổi target của symlink hoặc thay bytes, nhưng `Class` đã load vẫn là class đã được định nghĩa trước đó.

Trong một JVM, **địa chỉ file của artifact và danh tính class không giống nhau**. Cơ chế file cache của hệ điều hành hoặc URL/JAR caching có thể làm việc đọc một resource mới xảy ra khác kỳ vọng; nó không làm thay đổi định luật class identity.

### 4.2. Nguy cơ “nửa cũ, nửa mới”

Đừng chủ động thay bytes JAR tại chỗ khi JVM đang hoạt động:

- Class A đã được nạp trước thay đổi và tiếp tục chạy theo v1.
- Class B chưa từng được nạp; một lượt tải sau khi thay đổi có thể mở bản đã thay, dùng cache cũ hoặc gặp lỗi.
- Nếu A và B có ABI/constant khác nhau, có thể xuất hiện `NoSuchMethodError`, `NoSuchFieldError`, `LinkageError`, `ClassNotFoundException` hoặc hành vi không nhất quán khác.
- Một resource cấu hình mới có thể không tương thích code v1, dẫn đến lỗi mà người vận hành tưởng rằng “plugin vừa nâng cấp”.
- Trên Windows, file đang được mở có thể không ghi đè/xóa được; trên các hệ thống khác, cách rename/replace và open handles cũng có semantics riêng.

**Giải pháp:** tạo file theo phiên bản/content hash riêng (`plugin-1.4.0.jar`, `plugin-1.5.0.jar`), kiểm tra tính toàn vẹn rồi chỉ định **loader mới** tới đường dẫn artifact mới. Giữ artifact cũ cho đến khi không còn request hoặc loader cũ cần nó.

## 5. Tại sao chỉ gọi reload hoặc restart một phần chưa đủ?

Có một số API có tên gần giống reload nhưng phạm vi khác nhau.

### 5.1. `ServiceLoader.reload()`

`java.util.ServiceLoader` tìm các provider mà JAR/module công bố theo cơ chế dịch vụ Java. `ServiceLoader.reload()` **xóa cache provider** của chính đối tượng `ServiceLoader` đó để lượt duyệt sau có thể tìm/khởi tạo lại provider theo lookup hiện tại.

Nó **không** tự:

- Thêm URL JAR mới vào `URLClassLoader` đang có.
- Định nghĩa lại class đã được loader cũ nạp.
- Thay object provider v1 mà ứng dụng đã lưu ở registry/field trước đó.
- Đảm bảo các lớp thuộc JAR vừa ghi đè sẽ được load từ v2.
- Quản lý lifecycle, hoàn tất request cũ hoặc giải phóng resource cho bạn.

Một provider mới được lấy qua một `ServiceLoader` vẫn có thể thuộc **cùng `Class` cũ** nếu loader đang dùng đã nạp kiểu ấy.

### 5.2. Đóng `URLClassLoader`

`URLClassLoader` triển khai `Closeable`; nên đóng loader khi không còn cần nạp tài nguyên từ JAR. Nhưng:

```java
try (URLClassLoader loader =
        new URLClassLoader(jarUrls, parentLoader)) {
    // load class, tạo provider, sử dụng trong vòng đời được kiểm soát
}
```

Đoạn trên là **mã minh họa trong một phương thức**; `jarUrls` và `parentLoader` phải được khởi tạo, đồng thời import `java.net.URLClassLoader`.

`close()` đóng các tài nguyên mở bởi loader theo hợp đồng `URLClassLoader` và hạn chế việc tiếp tục nạp class/resource mới từ loader. Nó **không xóa `Class` đã định nghĩa khỏi JVM**, không phá hủy các instance, không đóng thread do plugin khởi tạo, và không bảo đảm GC sẽ unload class ngay. Các class đã nạp vẫn có thể được gọi trong thời gian còn tham chiếu.

Trong ví dụ mục 3, cả hai loader được đóng khi thoát khỏi `try`; trước đó class v1 và v2 tồn tại song song. **Đóng loader không phải thao tác “nâng cấp class”.**

### 5.3. JPMS và `ModuleLayer`

Với plugin triển khai bằng named modules, `ModuleLayer` biểu diễn nhóm module đã được định nghĩa. Thay JAR được finder nhìn thấy trên đĩa **không đổi các module đã định nghĩa vào layer hiện hữu**. Thông thường, cần tạo **`ModuleFinder` và `Configuration` mới**, phân giải từ roots phù hợp, rồi định nghĩa một **layer mới** để nạp module phiên bản mới.

Tương tự class loader, module layer không phải “danh sách file sống” được tự cập nhật. Khi thay module plugin, phải cân nhắc API module dùng chung ở parent layer, dependency graph, module readability và references giữ layer cũ.

### 5.4. `Class.forName(...)` hoặc “clear cache”

`Class.forName(name, true, oldLoader)` không mang ý nghĩa “lấy phiên bản mới nhất trên đĩa”. Nó yêu cầu loader xác định class có tên đó, và loader có thể trả về class đã nạp. `Class.forName` cũng **không đồng nghĩa tạo instance mới**. Tương tự, xóa một map cache do ứng dụng tự tạo không buộc JVM quên metadata class.

Muốn có class mới ở cơ chế nạp thông thường, cần một **defining loader khác** hoặc đường can thiệp bytecode chuyên biệt được nêu ở phần sau.

## 6. Cách nâng cấp plugin an toàn bằng loader mới

Một quy trình cập nhật có kiểm soát không chỉ “copy JAR, gọi reload”. Nó quản lý version, quyền, reference và request đang chạy.

```text
             plugin v1 đang hoạt động
                     |
           [1] Nạp artifact v2 mới
                     |
           [2] Xác minh hash/chữ ký,
              API và dependency
                     |
           [3] Tạo loader/layer v2
                     |
           [4] Khởi tạo + self-test,
              health check + warm-up
                     |
           [5] Công bố snapshot v2
                bằng thao tác atomic
                 /                 \
          request mới           request cũ
           -> v2                -> v1 đến khi xong
                 \                 /
                  [6] Drain v1
                       |
             [7] Deregister/stop
                 thread, listener,
                 callback và tài nguyên
                       |
             [8] Đóng loader v1,
                 bỏ tham chiếu
                       |
             [9] GC có thể unload
                 khi đủ điều kiện
```

### 6.1. Các bước vận hành chi tiết

1. **Stage artifact bất biến.** Lưu `plugin-2.0.0.jar` (hoặc đường dẫn chứa hash) riêng với `plugin-1.0.0.jar`; không ghi vào bản đang phục vụ request. Kiểm tra chữ ký/hashing từ nguồn triển khai được tin cậy.
2. **Xác minh metadata.** Kiểm tra plugin ID, version, min/max host API version, dependency, quyền plugin yêu cầu và danh sách package/module; từ chối bản không hợp lệ.
3. **Tạo loader/layer mới.** Dùng JAR mới và parent loader chứa **SPI/API chung ổn định**, không để plugin tái định nghĩa interface API của host.
4. **Khởi tạo thử.** Tạo instance mới, chạy kiểm tra readiness và dependency. Nếu thất bại, bỏ bản candidate và để v1 phục vụ bình thường.
5. **Quản lý state.** Quy định state nào có thể chuyển, schema/config có cần migrate, transaction nào đang dở và khả năng tương thích ngược. Không ép object v1 sang class v2.
6. **Chuyển route nguyên tử.** Đổi tham chiếu registry/holder dùng cho **request mới** từ v1 sang v2 bằng cơ chế đồng bộ/atomic phù hợp; đừng ghi lại bytecode trong class cũ.
7. **Drain các request đang dùng v1.** Có chính sách timeout/cancel an toàn, đặc biệt với thao tác có side effect; request đang chạy có thể hoàn tất trên snapshot v1.
8. **Tháo đăng ký v1.** Dừng scheduler/thread, deregister listener, MBean, callback, service, close stream/socket, clear cache/ThreadLocal, đóng loader theo vòng đời.
9. **Rollback khi cần.** Có thể chuyển lại registry sang instance v1 còn sống nếu chưa drain/dừng và data migration tương thích; nếu đã thay schema, rollback phải được lập kế hoạch riêng.
10. **Thu gom artifact cũ khi an toàn.** Chỉ xóa file v1 sau khi không còn loader/request cần nó và việc vận hành không cần giữ để rollback.

### 6.2. Ranh giới host API và plugin implementation

Một kiến trúc phổ biến:

```text
Application / parent class loader
  com.example.plugin.api.Plugin    <-- contract dùng chung
                  |
           PluginRegistry
            /          \
       PluginV1       PluginV2
       loader v1      loader v2
       impl JAR v1    impl JAR v2
```

`Plugin` là interface do host hoặc một API artifact ổn định quản lý, được nạp một lần từ **parent loader**. Các plugin implementation khác version được định nghĩa bởi **child loaders**; implementation có thể thực thi cùng một interface chung.

Với `URLClassLoader` mặc định, delegation thường là parent-first. Do đó cần:

- Không để implementation class name trùng với class đã được parent nạp.
- Không đóng gói trùng API/SPI trong plugin JAR theo cách dẫn tới nhiều phiên bản API bị loader khác nhau định nghĩa.
- Cố định host API compatibility (method signature, data DTO, exception contract); versioning chỉ tên file JAR không giải quyết được lỗi binary compatibility.
- Kiểm tra dependencies mà plugin cung cấp và dependencies dùng chung. Hai plugin có thể dùng thư viện version khác nhau nếu loader isolation hợp lệ; không phải lúc nào cũng tách được thư viện native hoặc global state.
- Dùng interface/DTO làm ranh giới, không trả thẳng implementation classes của plugin lên host lâu dài nếu muốn unload phiên bản cũ.

### 6.3. Atomic switch không đồng nghĩa unload ngay

Registry có thể lưu một đối tượng `PluginHandle` gồm version, provider instance, loader, lifecycle status và số request đang giữ snapshot. Khi thay bản, host atomically công bố handle v2, nhưng vẫn giữ handle v1 đến khi in-flight calls kết thúc.

Sơ đồ code minh họa (không phải chương trình độc lập):

```java
AtomicReference<PluginHandle> active =
        new AtomicReference<>(handleV1);

// Sau khi handleV2 đã được validate và khởi tạo thành công:
PluginHandle previous = active.getAndSet(handleV2);

// Request đã giữ handleV1 vẫn có thể cần hoàn thành.
// previous chỉ được close sau khi đã drain an toàn.
```

Để dùng thực tế, cần các kiểu `PluginHandle`, `handleV1`, `handleV2` và import `java.util.concurrent.atomic.AtomicReference`; `AtomicReference` **chỉ bảo đảm thay tham chiếu nguyên tử**, không tự giải quyết drain, transaction, quota, lifecycle hay rollback.

Nếu request đọc `active.get()` rồi gọi plugin mà hệ thống lập tức đóng loader cũ, vẫn có race. Cần hợp đồng lease/reference counting, read/write coordination hoặc cơ chế snapshot ổn định phù hợp. Việc ngắt một thao tác đang tạo side effect không được giải quyết bằng thay tham chiếu đơn thuần.

## 7. Khi nào class cũ mới có thể được unload?

JVM có cơ chế **class unloading** khi những class và defining class loader phù hợp trở nên không còn cần thiết và GC quyết định thu gom; thời điểm không được bảo đảm. Gọi `System.gc()` không phải hợp đồng đảm bảo unload.

Các tham chiếu thường giữ plugin cũ sống lâu ngoài ý muốn:

| Nguồn giữ tham chiếu | Hậu quả |
|---|---|
| Registry/singleton còn giữ provider v1 | Giữ instance, class và loader của v1 |
| Một `Class<?>` / `Method` / `Constructor` được cache | Giữ metadata liên quan đến class cũ |
| Thread của plugin chưa dừng hoặc thread context class loader trỏ v1 | Loader có thể tiếp tục được giữ sống |
| `ThreadLocal` ở thread pool còn giá trị của plugin | Giữ object plugin và loader cũ qua nhiều request |
| Listener/event bus/scheduler/MBean còn đăng ký | Callback và target instance v1 vẫn tồn tại |
| `ServiceLoader`, cache reflection hoặc framework container | Có thể giữ provider/class/loader cũ |
| Task đang chạy, stream/socket hoặc resource chưa đóng | Giữ vòng đời và file handles liên quan |
| Static field bên trong class v1 | Có thể giữ thêm object/thread; nếu class vẫn reachable thì làm phức tạp giải phóng |

Một plugin manager tốt cung cấp `start`/`stop`/`close`, đăng ký tất cả resource theo vòng đời và có metric theo version. Khi dừng, chủ động clear references của host, deregister callback, dọn TCCL/ThreadLocal khi thích hợp, dừng executor. **Đóng `URLClassLoader` giúp giải phóng resource, nhưng không bảo đảm class unloading.**

Nếu thao tác thay plugin liên tục khiến metaspace hoặc thread count tăng dần, hãy kiểm tra leak từ registry, thread, event listener và class loader reachability, không chỉ kích thước JAR.

## 8. Trường hợp ngoại lệ: Instrumentation có thể định nghĩa lại bytecode

Java còn có cơ chế chuyên biệt `java.lang.instrument.Instrumentation`, thông thường được cung cấp qua **Java agent**, cho phép `redefineClasses(...)` hoặc `retransformClasses(...)` trong những JVM hỗ trợ tính năng tương ứng.

Điều này tạo khác biệt quan trọng:

- **Ghi đè JAR không gọi các API instrumentation.** JVM không tự thay định nghĩa class chỉ vì byte trong file thay.
- Với API instrumentation hỗ trợ, agent có thể đưa **bytecode mới của một class đã tồn tại** vào runtime, nhưng phải thỏa những giới hạn và năng lực của JVM/agent.
- `redefineClasses` có các ràng buộc về việc thay cấu trúc class (ví dụ không thể tùy ý thêm/bớt field hoặc method, đổi hierarchy/signatures trong cơ chế chuẩn). Đây không phải thay plugin JAR bất kỳ theo kiểu hot swap hoàn chỉnh.
- Những method invocation **đang thực thi** có thể tiếp tục bằng bytecode cũ trên stack, trong khi lời gọi sau dùng định nghĩa được cập nhật theo cơ chế JVM. Không nên giả định có một thời điểm dừng toàn bộ logic một cách tự động.
- State, static fields, object instances, resources và cấu trúc dependency không tự được migrate. Method body mới có thể không tương thích trạng thái cũ.
- Không phải mọi JVM đều hỗ trợ mọi dạng redefine/retransform; cần kiểm tra các capability như `isRedefineClassesSupported()` và `isRetransformClassesSupported()`.

**Khi nào dùng?** Agent/hot code replace có thể hữu ích cho debugger, profiler, instrumentation hoặc thay đổi method body được kiểm soát. Với **plugin upgrade có thay API, field, dependency hoặc vòng đời**, cách tạo **class loader/layer mới rồi switch** thường thích hợp và rõ ràng hơn. Không hứa rằng “bật HotSwap” là đủ để áp mọi JAR mới trong production.

## 9. Kiểm thử tình huống thay plugin

Các bài test nên phân biệt bytecode trên đĩa, class đã định nghĩa, loader, instance và registry:

| Tình huống | Kỳ vọng |
|---|---|
| Host đang giữ `Greeting` v1; file JAR bị thay | `Class`/instance v1 không tự biến thành v2 |
| Gọi `Class.forName(..., oldLoader)` sau thay file | Không yêu cầu tạo class v2; thường nhận class v1 đã được loader nạp |
| Tạo loader mới chỉ tới `v2.jar` | Có thể tạo `Class` v2 nếu delegation không chọn class cũ |
| Tên class v1/v2 giống nhau, loader khác nhau | `getName()` bằng nhau, `Class<?>` khác nhau |
| Ép object của implementation v1 sang implementation v2 cùng tên | Có thể `ClassCastException` nếu dùng type v2 |
| Host/chid cùng có bản SPI khác defining loader | Cast API có thể thất bại dù tên interface giống |
| `ServiceLoader.reload()` với old loader | Không bảo đảm bytecode provider đã load thay đổi |
| `URLClassLoader.close()` | Không xóa class đã nạp hoặc kết thúc mọi thread |
| Plugin mới không qua health check | Không switch active registry, v1 vẫn phục vụ |
| In-flight request dùng v1 khi chuyển route | Tiếp tục theo snapshot v1, không tự nhảy sang v2 |
| Plugin v1 còn đăng ký listener/thread | Có nguy cơ leak hoặc callback v1 tiếp tục chạy |
| Loader/layer v1 không còn tham chiếu | GC **có thể** unload, không có deadline cứng |
| Trên Windows ghi đè JAR đang mở | Có thể bị khóa, vì vậy dùng artifact versioned |
| Resource đọc ra v2 nhưng code vẫn v1 | Đây không chứng minh class reload; cần chẩn đoán riêng |
| Plugin JAR chưa được load trước khi file đổi | Không giả định an toàn/nhất quán; phụ thuộc loader/cache |
| JVM agent redefine đúng cách | Chỉ hành vi trong phạm vi instrumentation hỗ trợ; không tự migrate state |

### 9.1. Log tối thiểu cần ghi khi chẩn đoán

Khi người dùng báo “đã thay JAR mà chạy mã cũ”, log nên có:

```text
plugin.id=report
plugin.version=2.0.0
artifact.sha256=<calculated-hash>
artifact.path=<approved-immutable-path>
class.name=com.example.report.ReportPlugin
class.loader.id=plugin-loader-v2
active.handle.version=2.0.0
inflight.v1=3
```

Đây là **ví dụ tên trường**, không phải stdout của chương trình. `artifact.sha256` phải được tính thật từ artifact; đừng tin riêng nhãn version hoặc một đường dẫn `current.jar`. Định danh loader có thể do registry cấp để debug, không nên dùng `toString()` của loader như một cơ chế phân quyền.

Nếu active handle vẫn trỏ v1 dù artifact path đã cập nhật v2, lỗi nằm ở **không chuyển registry/snapshot**, không phải JVM không đọc được file mới. Nếu đã chuyển v2 mà log vẫn gọi class v1, kiểm tra **parent delegation**, cache instance/callback, class identity và resource path.

## 10. Những hiểu nhầm cần tránh

1. **“JVM luôn đọc file JAR từ đĩa mỗi khi gọi phương thức.”** Sai: method call thực thi mã của class đã được định nghĩa; JAR là nguồn load, không phải file script tự đọc lại mỗi lần.
2. **“Chép đè JAR xong phải có hiệu lực ngay.”** Sai: không có watcher/hot reload mặc định.
3. **“Nếu class name giống nhau thì hai object có thể cast qua lại.”** Sai: class identity bao gồm defining loader.
4. **“Đặt JAR mới trong cùng thư mục rồi gọi `Class.forName` sẽ nạp lại.”** Không nếu class cũ đã được loader giải quyết; class loader mới và route mới mới là bước chính.
5. **“`ServiceLoader.reload()` giải quyết mọi việc.”** Sai: nó chỉ reset cache provider của chính `ServiceLoader`, không update class hay registry của ứng dụng.
6. **“Gọi `close()` trên `URLClassLoader` sẽ hủy mọi object plugin.”** Sai: object/class cũ còn sống theo references và GC.
7. **“Gọi GC chắc chắn giải phóng class loader.”** Sai: không có bảo đảm thời điểm, nhất là khi còn tham chiếu ở thread/listener/singleton.
8. **“Dùng một loader cho mọi phiên bản là tiết kiệm nhất.”** Dễ gây xung đột tên và khiến không thay được class; phải có ranh giới loader hợp lý.
9. **“Hai loader luôn cô lập hoàn toàn plugin.”** Sai: cùng JVM còn chia sẻ process, native state, OS permissions và những global services; class loader không phải sandbox.
10. **“Đã nạp v2 thì mọi request lập tức dùng v2.”** Sai: route/registry, active objects và in-flight request có vòng đời độc lập.
11. **“Instrumentation có thể thay bất kỳ cấu trúc class nào.”** Sai: redefine có giới hạn, state không tự thay và support phụ thuộc JVM.
12. **“Thay JAR tại chỗ chỉ có lỗi Windows khóa file.”** Sai: còn nguy cơ trộn class/resource, cache, race, thiếu rollback trên nhiều nền tảng.
13. **“Xóa tên JAR cũ ngay sau switch là đủ dọn rác.”** Sai: còn request cũ, class loader/resource handles và khả năng rollback.
14. **“Đổi đường dẫn resource nghĩa là code đã nâng cấp.”** Sai: resource lookup và class definition là hai cơ chế khác nhau.

## 11. Checklist cho plugin manager có thể nâng cấp

Trước khi đổi phiên bản, hãy xác nhận:

- Có **artifact v2 bất biến** đã kiểm tra nguồn, checksum/chữ ký và API version.
- Có **class loader/module layer mới** với parent API và dependency policy đúng.
- Có bài kiểm tra rằng `v2` thật sự chạy từ loader/layer v2, không bị parent lấy nhầm class v1.
- Có cách khởi tạo candidate, health check và từ chối bản lỗi mà không ảnh hưởng active v1.
- Có holder/snapshot để **switch atomically** và quản lý in-flight calls an toàn.
- Có phương án **state migration**, idempotency, database/schema compatibility và rollback.
- Có lifecycle stop/close cho executor, listener, cache, ThreadLocal, stream, socket và class loader.
- Có log/metric theo plugin ID, version, artifact hash, defining loader, active handle và inflight.
- Có kiểm thử cả môi trường Windows lẫn hệ triển khai thực, JAR/module path và classloader delegation.
- Có giới hạn an ninh: plugin không tin cậy **không** được coi là an toàn chỉ vì chạy trong class loader riêng.

### API tham khảo (Java SE 17)

- [ClassLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [URLClassLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [ServiceLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
- [Instrumentation — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html)
- [ModuleLayer — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html)

**Kết luận:** thay JAR **chỉ thay artifact**, không tự thay `Class` đã được JVM định nghĩa hay instance còn sống. Để nâng cấp plugin ở runtime theo cơ chế Java thông thường, hãy **tạo artifact phiên bản mới, nạp bằng loader/layer mới, chuyển registry sang instance mới, drain và giải phóng phiên bản cũ**. Quy trình ấy tách rõ việc thay file, thay kiểu runtime và thay hoạt động phục vụ request, giúp ứng dụng có thể kiểm thử, rollback và tránh trộn các phiên bản.