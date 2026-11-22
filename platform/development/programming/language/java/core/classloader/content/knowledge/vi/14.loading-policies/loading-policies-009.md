# Đánh đổi giữa cô lập, tương thích và khả năng chẩn đoán trong chính sách nạp lớp Java

Khi triển khai một hệ thống plugin, application server, test runner, bộ script động hoặc ứng dụng cho phép nhiều phiên bản thư viện, ta phải chọn **chính sách class loading**. Lựa chọn quan trọng không đơn thuần là viết `new ClassLoader(...)`, mà là quyết định **class nào do loader nào định nghĩa, lớp nào được chia sẻ và hoạt động nạp được quan sát bằng cách nào**.

Ba mục tiêu thường kéo nhau theo các hướng khác nhau:

- **Cô lập (isolation):** hạn chế các phiên bản/cấu phần nhìn thấy hoặc can thiệp vào nhau; cho phép cùng tên binary của class được định nghĩa trong những loader khác nhau.
- **Tương thích (compatibility/interoperability):** bảo đảm host và plugin cùng dùng **một runtime type** cho API giao tiếp, đồng thời không phá vỡ resolution, visibility, method linkage và hợp đồng của framework.
- **Khả năng chẩn đoán (diagnosability/observability):** khi xảy ra `ClassCastException`, `NoSuchMethodError`, `ClassNotFoundException` hoặc resource lookup sai, có thể xác định chính xác **ai yêu cầu nạp, ai định nghĩa, nguồn bytecode là gì, chính sách ủy quyền ra sao**.

Không có một chính sách duy nhất tối ưu cả ba. **Parent-first** thường ưu tiên chia sẻ và tương thích; **child-first có chọn lọc** tăng cô lập dependency riêng; **ghi nhận loader identity và quá trình resolution** giúp chẩn đoán nhưng thêm độ phức tạp/vận hành.

## 1. Mô hình nền tảng: runtime type không chỉ có tên lớp

Java coi một runtime class/interface được xác định bởi hai yếu tố:

~~~text
Runtime type identity = (binary name, defining class loader)
~~~

Ví dụ:

~~~text
plugin.impl.Greeting do loader A định nghĩa
plugin.impl.Greeting do loader B định nghĩa
~~~

Hai kiểu này có cùng tên `plugin.impl.Greeting` nhưng là **hai kiểu runtime khác nhau** nếu A và B là hai defining loader khác nhau.

Ngược lại, hai loader con A/B có thể gọi `loadClass("api.Plugin")` rồi cùng được parent trả về **chính một** `Class<?>` do parent định nghĩa. Trong trường hợp đó, API `api.Plugin` được chia sẻ.

Sơ đồ thường dùng:

~~~text
                     Bootstrap / platform
                             |
                         App loader
                       defines api.Plugin
                        /            \
                       /              \
            Plugin loader A       Plugin loader B
            defines ImplA         defines ImplB
                       \              /
                        \            /
                  Host sử dụng api.Plugin
~~~

Nếu plugin loader định nghĩa lại `api.Plugin` thay vì delegate cho app loader, thì một class `implements api.Plugin` trong plugin có thể implement **một interface runtime khác** so với `api.Plugin` của host, dù package và class name hoàn toàn giống nhau.

### Defining loader và initiating loader

**Defining loader** là loader thực sự tạo định nghĩa class (thường qua `defineClass`). `Class.getClassLoader()` cho biết defining loader.

**Initiating loader** có thể là loader bắt đầu yêu cầu `loadClass` và sau đó delegate cho parent; nó không nhất thiết là defining loader.

~~~java
Class<?> target = pluginLoader.loadClass("api.Plugin");
ClassLoader defining = target.getClassLoader();

System.out.println(defining == pluginLoader);
~~~

Đây là **mảnh minh họa**, giả định `pluginLoader` đã tạo và API có thể tìm. Kết quả `false` hoàn toàn bình thường nếu API được parent định nghĩa.

**Không** suy ra defining loader từ tên JAR, tên loader, classpath hay việc một method `loadClass` có log nhận yêu cầu.

## 2. Parent-first: tương thích trước, phiên bản phụ thuộc vào parent
`ClassLoader.loadClass` mặc định hỏi parent trước rồi mới đến `findClass` của child nếu chưa có định nghĩa. Điều này giúp các plugin dùng chung API và thư viện do host quản lý. Đổi lại, `lib.Parser` ở parent có thể **che** một phiên bản trong plugin; class nạp được nhưng phương thức mà plugin đã biên dịch để gọi có thể thiếu, dẫn đến `NoSuchMethodError`.

Lợi ích vận hành là ít loader-specific overrides, nhưng chỉ có ý nghĩa khi owner của dependency và **binary compatibility** được kiểm soát. Parent-first không bảo đảm mọi plugin tương thích với mọi thư viện ở parent.

## 3. Child-first: cô lập có chọn lọc, phải bảo vệ boundary
Với những dependency private bị host shadow, child-first có thể chọn bytecode thuộc plugin trước. Điều này cho phép hai plugins dùng cùng binary name với hai versions khác nhau, nhưng chỉ hiệu quả nếu chúng không trao đổi trực tiếp những implementation types ấy qua API host.

Cần giữ `java.*`/platform classes và shared interface, DTO, annotation, exception types ở loader chung. Child-first không tự thay `getResource`/ServiceLoader hay bypass JPMS, không phải sandbox bảo mật, và tăng chi phí chẩn đoán/metadata nếu tạo nhiều class definitions. Câu hỏi là **namespace nào thật sự phải độc lập**, chứ không phải đổi toàn bộ ứng dụng sang child-first.

## 4. So sánh các chính sách

| Tiêu chí | Parent-first | Child-first toàn phần | Child-first chọn lọc |
|---|---|---|---|
| Chia sẻ API host/plugin | Thuận lợi | Dễ vô tình nhân bản kiểu | Thuận lợi nếu giữ API ở parent |
| Tách phiên bản library trùng tên | Hạn chế | Cao hơn | Cao cho namespace được chọn |
| Tính dự đoán mặc định | Dễ hơn | Phụ thuộc override | Phụ thuộc danh sách prefix/quy tắc |
| Rủi ro `ClassCastException` do duplicate API | Thấp hơn | Cao | Thấp nếu boundary thiết kế đúng |
| Rủi ro method/linkage incompatibility | Có nếu parent version sai | Có ở ranh giới chia sẻ | Có, cần kiểm thử |
| Resource lookup tương ứng class | Dễ hiểu hơn khi default delegation | **Không tự động đồng bộ** | Phải thiết kế riêng |
| Gỡ lỗi loader identity | Thường đơn giản hơn | Phức tạp hơn | Cần log chính sách cụ thể |
| Chi phí quản trị cấu hình | Thấp hơn | Cao hơn | Trung bình–cao |
| Phù hợp plugin nhiều version | Khi API/dependencies đồng nhất | Chỉ trong thiết kế được kiểm soát | Thường là điểm cân bằng |

Không có cột nào “bảo mật hơn” theo nghĩa có thể chạy mã không tin cậy một cách an toàn. Cả ba phương án vẫn chạy bên trong cùng JVM/process trừ khi bạn thiết kế thêm ranh giới cách ly thực sự.

## 5. Thiết kế ranh giới chia sẻ trước khi chọn policy

Một cách tổ chức hợp lý cho plugin runtime:

~~~text
Application classloader
  api.Plugin
  api.PluginContext
  shared DTO / public contracts
          |
          +-- Child loader A
          |    plugin.impl.Greeting
          |    plugin.internal.*
          |    private dependencies v1
          |
          +-- Child loader B
               plugin.impl.Greeting
               plugin.internal.*
               private dependencies v2
~~~

Các nguyên tắc:

1. **API chung phải có một defining loader thống nhất**. Đặt `api.Plugin`, các interface callback và DTO thực sự được chia sẻ ở parent.
2. **Implementation của mỗi plugin có thể là child-first** nếu host không cần liên kết trực tiếp đến class triển khai theo tên.
3. **Hạn chế kiểu implementation riêng vượt ranh giới**. Giao tiếp qua `api.Plugin` hoặc DTO chung do parent định nghĩa.
4. **Kiểm tra transitive dependencies**, không chỉ plugin top-level class. Một dependency của plugin có thể tham chiếu class mà parent đã cung cấp phiên bản không tương thích.
5. **Có chiến lược resources/services**. Child-first cho class **không tự đổi** `getResource` thành child-first; resource cùng tên có thể đến từ parent.
6. **Thiết kế lifecycle**. Loader không tự unload class khi plugin bị “disable”; phải giải phóng references và tài nguyên được giữ.
7. **Chấp nhận ranh giới JPMS** nếu dùng named modules. Module readability/exports/opens khác với policy của custom URLClassLoader.

## 6. Case study: chọn policy cho hai plugin mà host đã có dependency cũ
Giả sử host chứa `lib.Parser` v1 và public SPI `api.Plugin`; plugin A dùng Parser v1, plugin B được biên dịch với Parser v2 có thêm `parse(byte[])`. Cả hai plugin phải implements **chính runtime `api.Plugin`** của host.

| Phương án | Hành vi đối với plugin B | Hợp đồng API và vận hành |
| --- | --- | --- |
| Giữ parent-first với v1 trên parent | B có thể nhận Parser v1 rồi phát sinh `NoSuchMethodError` khi gọi method chỉ có ở v2 | Dễ quản lý loader nhưng không đạt yêu cầu chức năng |
| Loại Parser khỏi parent, đặt bản tương ứng ở mỗi plugin URL | Cả A/B tự định nghĩa Parser phiên bản riêng ngay với parent-first thông thường | Ưu tiên khi dependency này thực sự private; API vẫn do parent định nghĩa |
| Parent còn Parser v1, dùng selective child-first cho `lib.*` private | B ưu tiên Parser v2 nếu JAR child chứa đủ phụ thuộc | Cần audit transitive dependencies, fallback, resource, sealed packages |
| Shading/relocation Parser v2 | Đổi binary name tránh trùng với host | Build phải cập nhật reflection, resource và service descriptors khi cần |
| Plugin B ở process/JVM riêng | Không có class identity trực tiếp với host | Cần protocol/schema IPC, chi phí deploy/vận hành lớn hơn |

### 6.1. Kết quả chẩn đoán theo từng trường hợp

```text
B gọi lib.Parser.parse(byte[])
  ├─ Parser được parent định nghĩa, không có signature   → NoSuchMethodError
  ├─ Parser v2 được child định nghĩa, signature tồn tại  → lời gọi có thể thành công
  ├─ child định nghĩa lại api.Plugin                    → host có thể không cast được
  └─ class v2 + config từ parent v1                     → có thể chạy sai dù không lỗi linkage
```

Trước khi quyết định, ghi lại class đang lỗi, `getClassLoader()`, `CodeSource` khi có, JAR class thật, tên/descriptor method bằng `javap -s`, URL resource và loader được `ServiceLoader` dùng. Một class tìm được không chứng minh runtime đã dùng đúng version.

### 6.2. Ma trận kiểm chứng sau thay đổi

1. **Host API:** `api.Plugin` từ loader plugin phải là chính `api.Plugin.class` của host; thử cast một instance implementation.
2. **Dependency ownership:** Parser A và B phải được định nghĩa bởi loader dự kiến; so hai `Class<?>` cùng tên bằng `==` và gọi method v2 thật.
3. **Missing local class:** thử tên chỉ có ở parent. Chọn fallback nếu đã phê duyệt, hoặc fail closed cho private namespace phải cô lập tuyệt đối.
4. **Resource/SPI:** đặt tên resource trùng giữa parent và child, kiểm tra cả `getResource` lẫn `getResources`; với service descriptor, giữ đủ provider hợp lệ.
5. **Lifecycle:** reload B bằng loader mới, dừng threads/callbacks, dọn TCCL và cache; `close()` không bảo đảm unload tức thì.
6. **Quan sát:** cung cấp loader ID ổn định, class/package rule được chọn và nguồn thực tế; không log nội dung bí mật.

Case study này không đòi một custom classloader duy nhất. Nó buộc chọn **tập dependencies thuộc parent**, **đường giao tiếp dùng chung**, và **cách chứng minh version thật khi chạy** trước khi triển khai.

## 7. Tại sao child-first toàn phần dễ phá tương thích?

Giả sử host compile dựa vào:

~~~java
package api;
public interface Plugin {
    String message();
}
~~~

Nếu child-first định nghĩa lại `api.Plugin` từ bản copy trong plugin JAR, thì class trong plugin implement **một `api.Plugin` khác**. Phía host không tự cast object được về interface của nó.

~~~text
Host:  (api.Plugin, AppLoader)
Plugin:(api.Plugin, ChildLoader)

Tên giống nhau, runtime type khác nhau.
~~~

Trường hợp này thường dẫn đến `ClassCastException` khi host cast object trực tiếp. Ngoài ra, JVM có thể gặp loading constraints hoặc lỗi liên kết khác nếu hai định nghĩa kiểu bị kết hợp trong signature. Không phải mọi lỗi đều có cùng exception; phải đọc stack trace và xác định **thời điểm load/resolve/initialize/cast**.

**Phương án cân bằng:**

- Parent-first: `java.*`, `javax.*` khi thích hợp, public API host/plugin, DTO/exceptions chung, logging facade hoặc những contract dùng qua boundary.
- Child-first chọn lọc: `plugin.impl.*` và những namespace implementation riêng thật sự cần cách ly.
- Với library bị shade/relocate, kiểm tra binary names đã thay đổi và tránh để plugin export những class library riêng trực tiếp qua API chung.
- Các namespace chia sẻ nên được quy hoạch thành một danh sách có chủ sở hữu rõ ràng; đừng thêm “ngoại lệ” không kiểm soát.

## 8. Tương thích bao gồm API, ABI, module và vòng đời

### 8.1. Binary compatibility

Chia sẻ một class từ parent không bảo đảm plugin compile trên v2 sẽ chạy với v1. Ví dụ method `foo(int)` chỉ có ở bản mới: plugin có thể nạp được class `lib.Util` cũ nhưng khi resolve lời gọi `foo(int)` JVM báo `NoSuchMethodError`.

Do đó cần kiểm thử:

- Signature các method/field và inheritance mà plugin sử dụng.
- Phiên bản bytecode `--release` và runtime JDK.
- Transitive dependencies và version được JVM thực sự nạp.
- Những lời gọi reflection, method handles và service provider discovery.

### 8.2. Package-private và runtime package

JVM xác định runtime package từ **package name + defining loader**. Hai class cùng `package p;` nhưng ở loader khác nhau **không đương nhiên có quyền package-private** lẫn nhau. Có thể gặp `IllegalAccessError` dù javac cho phép cùng package khi compile.

Không phân chia các class cần dùng package-private thành các defining loaders khác nhau trừ khi đã chủ động thiết kế lại boundary sang public API thích hợp.

### 8.3. JPMS không thay thế chính sách classloader

Named module có `requires`, `exports`, `opens`, readability và encapsulation. Loader hierarchy không tự vượt qua những ranh giới đó.

Tạo `new URLClassLoader(urls, parent)` không tự resolve JAR thành named module chỉ vì JAR có `module-info.class`. Đối với chương trình modular, xét `ModuleLayer`, module configuration và module loader đúng cơ chế.

### 8.4. Serialization và giao tiếp qua loader boundary

Nếu host/plugin cùng dùng một DTO hoặc exception, nên đặt loại đó ở loader chung. Java serialization với class do loader riêng định nghĩa có thể gặp vấn đề giải quyết kiểu tại bên nhận. Không dựa vào việc tên class trùng nhau để coi chúng là interchangeable.

Đối với boundary dài hạn, nên dùng API versioned rõ ràng hoặc schema/format ổn định (JSON, protocol messages, v.v.) khi cần tách deployment hay tách process.

### 8.5. Unloading và leaks

Đóng `URLClassLoader` giúp đóng file handles, nhưng class không được unload ngay. Reference tới `Class<?>`, instance plugin, thread context loader, static cache, `ThreadLocal`, thread đang chạy hoặc callback có thể giữ loader sống lâu.

Nếu ưu tiên hot redeploy, cần thiết kế **plugin lifecycle** từ đầu: dừng threads, đóng resources, hủy callback, dọn caches, reset TCCL và loại bỏ references. Isolation hỗ trợ việc tái triển khai nhưng không tự làm thay các bước đó.

## 9. Khả năng chẩn đoán: cần log gì và không nên log gì?

### 9.1. Minimum diagnostic context

Khi nhìn thấy một lỗi classloading, log các thông tin sau:

| Trường | Ví dụ / ý nghĩa |
|---|---|
| Binary name | `plugin.impl.Greeting` |
| Defining loader class | `PolicyLoader` hay built-in app loader |
| Loader name | `"child-first"`, chỉ là nhãn |
| Loader object identity | So bằng `==`; `identityHashCode` chỉ giúp log trong process và **không tuyệt đối duy nhất** |
| Parent chain | Loader nào là parent ở mỗi bước |
| CodeSource / source URL | Nguồn JAR/file nếu JVM có metadata này |
| Resource URL | Resource cụ thể được chọn |
| TCCL | `Thread.currentThread().getContextClassLoader()` |
| Runtime module | `type.getModule()` |
| Error chain | Class/linkage exception và nested causes |

Không log bí mật, API keys hoặc nội dung đầy đủ của file cấu hình nhạy cảm chỉ để chẩn đoán. Với policy động, nên log **prefix rule nào đã được áp dụng** và loader nào thực sự định nghĩa class.

### 9.2. Mảnh code chẩn đoán class

~~~java
static void explain(Class<?> type) {
    ClassLoader loader = type.getClassLoader();

    System.out.println("name=" + type.getName());
    System.out.println("module=" + type.getModule().getName());
    System.out.println("loader-name="
            + (loader == null ? "<bootstrap>" : loader.getName()));
    System.out.println("loader-class="
            + (loader == null ? "<bootstrap>"
                : loader.getClass().getName()));
    System.out.println("loader-id="
            + (loader == null ? 0
                : System.identityHashCode(loader)));
}
~~~

Đây là **method minh họa**, không có `main`. `Module.getName()` có thể trả `null` cho unnamed module. `identityHashCode` có thể trùng giữa hai object trong một JVM, nên chỉ sử dụng làm manh mối log, **không làm khóa nhận dạng bất biến duy nhất**; nếu có thể, ghi ID logic tự cấp cho mỗi loader từ registry của ứng dụng.

Nếu muốn truy nguồn class:

~~~java
Class<?> type = obj.getClass(); // obj phải khác null

var domain = type.getProtectionDomain();
var codeSource = domain == null ? null : domain.getCodeSource();

System.out.println(codeSource == null
        ? "source unavailable"
        : codeSource.getLocation());
~~~

Đây là **mảnh minh họa**, không phải mọi class đều có CodeSource hữu ích; giá trị có thể `null`. Không suy đoán URL nguồn từ chuỗi `type.getName()`.

### 9.3. Logging của HotSpot

Trên HotSpot/JDK 17+ có thể bật Unified Logging:

~~~bash
java -Xlog:class+load=info,class+unload=info -jar app.jar
~~~

Log phụ thuộc JDK và có thể gồm thông tin rất nhiều class; đây là **lệnh chẩn đoán**, không thuộc stdout dự kiến của demo. Để điều tra lỗi ở production, có thể bật log tập trung trên khoảng thời gian ngắn, lọc theo class/plugin và giữ đủ context của defining loader.

Các công cụ như `jcmd`, Java Flight Recorder (JFR) hoặc profiler có thể bổ sung số lượng classloader, classloading/unloading events và allocations khi runtime hỗ trợ. Không mặc định một event chứa đủ mọi thông tin về mọi cuộc delegation.

### 9.4. Khi resource cùng tên nhưng sai phiên bản

Luôn kiểm tra URL thật sự được trả:

~~~java
URL found = loader.getResource("plugin/config.txt");
System.out.println(found);
~~~

Đây là mảnh minh họa, có thể trả `null`. Với `URLClassLoader`, có thể so `getResource` (bao gồm parent delegation) và `findResource` (tìm trong nguồn của chính loader) để xác định xung đột.

## 10. Quy trình xử lý lỗi theo từng hiện tượng

### `ClassCastException: X cannot be cast to X`

1. Xác định `Class<?>` nguồn và `Class<?>` đích; không chỉ đọc `getName()`.
2. In `getClassLoader()` của cả hai và so bằng `==`.
3. Kiểm tra interface/DTO nào đã bị child định nghĩa trùng với parent.
4. Chuyển shared API về parent hoặc thay đổi boundary thành contract rõ ràng.
5. Nếu cần chạy hai phiên bản độc lập, không ép kiểu trực tiếp qua class implementation riêng.

### `NoSuchMethodError` / `NoSuchFieldError`

1. Xác định tên binary của class chứa method/field đang fail.
2. Kiểm tra defining loader và CodeSource của class thực sự được nạp.
3. So signature thực với phiên bản plugin đã compile.
4. Nếu parent-first che bản dependency mới, cân nhắc child-first **cho thư viện implementation phù hợp**, không thay toàn bộ policy.
5. Chạy integration tests với classpath/deployment giống production.

### `ClassNotFoundException`

1. Kiểm tra binary name đúng với package.
2. Kiểm tra URL roots/JAR entries và quyền truy cập file.
3. Xác định loader nào nhận yêu cầu: host, plugin loader, TCCL hay framework loader.
4. Kiểm tra policy prefix và fallback parent.
5. Không chữa bằng thêm mọi JAR vào global classpath nếu điều đó phá isolation.

### `NoClassDefFoundError`

Đây không phải lúc nào cũng là “file `.class` mất”. Nó còn có thể phát sinh do dependencies thiếu, lỗi liên kết hoặc một kiểu đã initialization thất bại. Phải đọc phần `Caused by` và thời điểm lỗi, thay vì ngay lập tức tạo loader mới.

### `IllegalAccessError`

Kiểm tra runtime package identity và quyền truy cập module/class. Cùng chuỗi package không đủ nếu defining loaders khác nhau. Nếu dùng JPMS, `exports`/`opens` có tác dụng khác nhau; không sửa tùy tiện bằng “mở tất cả package”.

### `ServiceLoader` không thấy provider

`ServiceLoader.load(PluginService.class)` thường sử dụng **thread context class loader (TCCL)** theo API overload tương ứng. Nếu TCCL không phải loader có provider, lookup có thể thất bại dù `pluginLoader.loadClass` thấy lớp.

Trong workflow cho plugin, có thể tạm thiết lập TCCL trong phạm vi có kiểm soát và **phải khôi phục trong `finally`**:

~~~java
Thread thread = Thread.currentThread();
ClassLoader original = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi framework / ServiceLoader khi contract cho phép.
} finally {
    thread.setContextClassLoader(original);
}
~~~

Đây là **mảnh minh họa**, cần biến `pluginLoader` hợp lệ. Không thay TCCL của thread pool rồi quên khôi phục; điều đó có thể giữ plugin loader cũ sống lâu và gây cross-plugin visibility sai.

## 11. Tác động hiệu năng và vận hành

| Yếu tố | Cô lập mạnh (nhiều loaders) | Chia sẻ mạnh (ít loaders) |
|---|---|---|
| Số runtime `Class<?>` của thư viện trùng | Có thể tăng | Ít bản trùng hơn |
| Metaspace và metadata overhead | Có thể tăng do duplicate definitions | Thường giảm |
| Khả năng chạy dependency version riêng | Cao hơn | Hạn chế hơn |
| CPU cho class loading và resource lookup | Có thể tăng theo số loader/URL/delegation | Có thể đơn giản hơn |
| Thay plugin mà không thay host | Thuận lợi khi lifecycle đúng | Khó nếu class ở loader sống suốt đời |
| Chẩn đoán lỗi duplicate class | Phức tạp hơn | Ít trường hợp hơn, nhưng version conflicts vẫn có |
| Tác động thay đổi API chung | Cần contract versioned | Có thể ảnh hưởng toàn hệ thống |

Không coi “nhiều loaders” chắc chắn chậm hơn với một con số cố định: hiệu năng phụ thuộc số class, kích thước JAR, caching, I/O, JPMS/framework, pattern tải class và tần suất tạo/hủy loader. Đo trong workload thực tế bằng JFR, JVM metrics và các phép benchmark có kiểm soát.

Tránh tạo một URLClassLoader mới cho **mỗi request**. Một plugin có vòng đời rõ ràng thường cần một loader tồn tại tương ứng lifecycle đó, được đóng sau khi tất cả công việc của plugin kết thúc.

## 12. Một chiến lược chọn policy có kiểm chứng

**Bước 1 — Vẽ boundary type.** Liệt kê API, DTO, exception, callback, service interfaces dùng qua host/plugin. Chúng cần được định nghĩa ở đâu?

**Bước 2 — Phân loại package.** Xác định những namespace là API chung và những namespace chỉ chứa implementation/dependency riêng.

**Bước 3 — Chọn mặc định parent-first.** Giữ delegation chuẩn cho Java core, platform và shared API.

**Bước 4 — Chỉ mở child-first cho nhu cầu có chứng cứ.** Nếu plugin thật sự cần dependency khác version với host, chọn prefix/namespace càng nhỏ càng tốt; cân nhắc shading/relocation nếu phù hợp.

**Bước 5 — Đồng bộ chính sách resource.** Kiểm tra `getResource`, `getResources`, ServiceLoader, TCCL và config source; không mặc định class policy tự kéo resource policy theo.

**Bước 6 — Kiểm thử cả đường thành công lẫn lỗi.** Có ít nhất các test parent has class / parent misses / duplicate API / duplicate resource / missing dependency / wrong bytecode version / plugin redeploy.

**Bước 7 — Thiết kế chẩn đoán.** Log class name, defining loader, parent chain, CodeSource, module, policy branch và resource URL (không log secrets).

**Bước 8 — Thiết kế vòng đời.** Đóng stream/JAR handles, dừng plugin tasks, reset TCCL, loại bỏ references để JVM có thể unload khi thích hợp.

## 13. Checklist kiểm thử

- [ ] API chung được một defining loader sở hữu và cả host/plugin nhìn đúng runtime type.
- [ ] Child-first chỉ áp dụng những namespace có chủ đích, không áp dụng mù quáng cho `java.*`.
- [ ] Plugin có dependency riêng version khác vẫn dùng đúng bytecode cần thiết.
- [ ] Có test trùng tên class giữa parent/child để bảo đảm thứ tự nạp mong muốn.
- [ ] Có test trùng resource giữa parent/child để kiểm tra thứ tự và resource URL thực tế.
- [ ] `Class.getClassLoader()` được dùng để xác nhận defining loader, không chỉ dựa vào loader name.
- [ ] Có test casting qua public interface chung và khi interface bị copy trùng.
- [ ] Có test `ServiceLoader` / TCCL nếu framework sử dụng.
- [ ] Có test `ClassNotFoundException`, `NoClassDefFoundError`, `NoSuchMethodError` theo những tình huống có ý nghĩa.
- [ ] Plugin không còn giữ thread, callback, static cache hay file handles sau khi dừng.
- [ ] Classloader diagnostics không ghi nội dung secrets hoặc gây logging overload.
- [ ] Nếu dùng JPMS, module layer/readability/exports/opens được đánh giá riêng.

## 14. Những ngộ nhận cần tránh

1. **“Child-first luôn tốt hơn vì cô lập mạnh hơn.”** Sai: cô lập trùng API làm cast/linkage hỏng và có chi phí vận hành.
2. **“Parent-first luôn bảo đảm tương thích.”** Sai: parent có thể trả dependency version không đủ binary API mà plugin cần.
3. **“Cùng tên class tức cùng type.”** Sai: cần cùng defining loader.
4. **“Một loader gọi `loadClass` thì nó phải là defining loader.”** Sai: delegation có thể trả class của parent.
5. **“Child-first cho class tự làm resource child-first.”** Sai: override `loadClass` không tự thay `getResource`.
6. **“Đặt cùng tên loader làm hai loader giống nhau.”** Sai: tên là nhãn, không phải runtime identity.
7. **“Nhiều classloaders tạo sandbox bảo mật.”** Sai: JVM process vẫn có quyền truy cập chung nếu không có cách ly riêng.
8. **“Chỉ cần đóng URLClassLoader là class unload ngay.”** Sai: còn references và GC.
9. **“Một JAR có `module-info.class` sẽ tự thành named module trong URLClassLoader.”** Sai: module resolution là cơ chế khác.
10. **“`ClassCastException` chỉ có thể do hai tên class khác nhau.”** Sai: duplicate defining loaders có thể gây thông báo cast X sang X.
11. **“`NoClassDefFoundError` luôn đồng nghĩa không tìm thấy file.”** Sai: còn class initialization thất bại và những nguyên nhân linkage khác.
12. **“TCCL luôn giống system class loader.”** Sai: TCCL thay đổi theo thread/framework.
13. **“`identityHashCode` là ID loader duy nhất toàn hệ thống.”** Sai: có thể trùng và không ổn định giữa tiến trình.
14. **“Cứ tắt logging sẽ cải thiện chẩn đoán.”** Sai: cần giữ khả năng truy vết ở mức phù hợp với overhead và bảo mật.
15. **“Shading chỉ đổi tên file JAR là đủ.”** Sai: relocation thực sự thay đổi package/binary names; phải kiểm tra service/resource metadata đi kèm.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Plugin A muốn dùng bản `lib.Parser` mới, host đã có `lib.Parser` cũ. Parent-first sẽ chọn bản nào nếu parent tìm được?

**Đáp án:** Bản do parent định nghĩa, có nguy cơ thiếu method mà plugin cần. Có thể xem xét child-first có chọn lọc cho `lib.Parser`, shading/relocation hoặc đồng bộ dependency version.

**Câu 2.** Vì sao child-first toàn phần có thể gây `ClassCastException` khi ép plugin về interface `api.Plugin` của host?

**Đáp án:** Vì child có thể tự định nghĩa thêm một `api.Plugin` với defining loader khác; runtime interface đó không giống interface do host dùng.

**Câu 3.** Hai child loaders có tên cùng `"plugin"` và cùng bytecode. Chúng có một runtime class chung không?

**Đáp án:** Không nếu từng loader tự định nghĩa kiểu; tên loader và bytecode giống không làm runtime identity trùng nhau.

**Câu 4.** Class policy đã child-first cho `plugin.impl.`. Tại sao `loader.getResource("plugin/config.txt")` vẫn có thể trả resource từ parent?

**Đáp án:** Vì `getResource` của ClassLoader có delegation policy riêng, mặc định tìm parent trước. Override `loadClass` không thay đổi nó.

**Câu 5.** Khi điều tra `NoSuchMethodError`, vì sao phải xem defining loader và CodeSource?

**Đáp án:** Để biết class thực tế được nạp từ version/JAR nào, không chỉ dựa vào dependency tree lúc build hoặc vị trí URL dự kiến.

**Câu 6.** `URLClassLoader.close()` đủ để unload một plugin không?

**Đáp án:** Không. Phải dừng plugin tasks, giải phóng references, reset TCCL, đóng handles; JVM chỉ unload khi điều kiện cho phép.

**Câu 7.** Nếu cần kiểm thử hai phiên bản implementation khác nhau nhưng vẫn cast object về chung `Plugin`, đặt `Plugin` ở đâu?

**Đáp án:** Trong loader cha dùng chung, và cấu hình child loaders delegate việc nạp `api.Plugin` về parent.

## 16. Khung ghi nhớ

~~~text
                    Chọn chính sách class loading
                                |
                    Shared API, DTO, callbacks?
                         /               \
                       Có                 Không
                        |                   |
                Định nghĩa ở parent   Có cần dependency
                        |              khác version?
                 Parent-first cho API     /       \
                                        Không       Có
                                         |          |
                                   Parent-first   Child-first
                                   thường đủ      chọn lọc
                                                      |
                                            kiểm tra type identity
                                                      |
                                            kiểm tra resource policy
                                                      |
                                            log defining loader / URL
                                                      |
                                            quản lý lifecycle / TCCL
~~~

**Kết luận:** Hãy **chia sẻ những kiểu thật sự là hợp đồng giao tiếp**, **cô lập những chi tiết triển khai thật sự cần khác version**, và **lưu đủ dấu vết để chứng minh JVM đã định nghĩa class nào từ đâu**. Đó là điểm cân bằng có thể bảo trì giữa isolation, compatibility và diagnosability trong Java class loading.

### Tài liệu chính thức

- [Java SE 17 — ClassLoader: loadClass, getResource, getResources](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — URLClassLoader: findClass, findResource, close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html)
- [JVMS §5.3 — Creation and Loading; defining/initiating loaders](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
- [JLS §13 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html)
- [Java SE 17 — ServiceLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html)
