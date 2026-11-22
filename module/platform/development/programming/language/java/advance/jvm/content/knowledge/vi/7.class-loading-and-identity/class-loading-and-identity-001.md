# Nạp lớp là gì và vì sao JVM không nạp toàn bộ chương trình ngay từ đầu?

## 1. Câu trả lời ngắn: JVM xây dựng chương trình đang chạy từ các kiểu cần thiết

Một chương trình Java có thể chứa hàng nghìn tệp `.class` trên classpath/module path, cùng rất nhiều lớp trong thư viện JDK. **Không có quy tắc “khởi động là nạp và khởi tạo toàn bộ các lớp đó”.** JVM khởi động từ lớp ban đầu (thông thường là lớp chứa `main`), rồi tải, liên kết và khởi tạo các lớp/interface khác theo nhu cầu thực thi và những yêu cầu liên quan.

Đối với **lớp hoặc interface không phải mảng**, *class loading* là quá trình tìm **biểu diễn nhị phân** của một kiểu theo tên (thường là các byte của `.class` trong thư mục, JAR, module hoặc nguồn do class loader cung cấp), rồi tạo **biểu diễn kiểu tại runtime** để JVM có thể quản lý kiểu đó. Đây là một công việc khác với việc **chạy khối `static {}`** hoặc tạo **instance** bằng `new`.

Ví dụ: JAR của một ứng dụng có lớp `ReportExporter` nhưng người dùng không bao giờ bấm nút Export. Không có nghĩa vụ phải **khởi tạo** `ReportExporter` ngay ở startup. Tuy nhiên, không được biến nhận xét này thành khẳng định cứng rằng `ReportExporter` chắc chắn chưa từng được **load**: JVM có thể sớm resolve, verify hoặc các framework có thể chủ động tìm/nạp kiểu ấy.

Một cách nói chính xác hơn:

> JVM hỗ trợ **dynamic loading** và có thể trì hoãn nhiều công việc tới khi cần; thời điểm loading/linking cụ thể có một phần do JVM implementation quyết định, còn các sự kiện kích hoạt **initialization** phải tuân thủ quy tắc ngôn ngữ/JVM.

### Những câu hỏi cần phân biệt

- **Class có trong JAR?** Điều đó chỉ nói mã nhị phân có sẵn trên đường tìm kiếm; chưa nói class đã được JVM load.
- **Class đã loaded?** JVM có representation của kiểu đó; chưa chắc class đã initialized.
- **Class đã linked?** Việc verification/preparation đã hoàn tất và symbolic references được resolve theo mức cần thiết; chưa chắc `<clinit>` đã chạy.
- **Class đã initialized?** Các static initializer/khởi tạo static field không phải constant variable đã được thực thi theo quy tắc class initialization.
- **Đã có object?** Một instance đã được tạo; một class có thể initialized mà chưa có instance nào.
- **Đã có method chạy?** Có thể là static method không cần instance, instance method gọi qua object, hoặc một method khác dẫn đến yêu cầu tải kiểu.

## 2. Ba giai đoạn loading, linking, initialization

Trong kiến trúc JVM, ba pha lớn có quan hệ thứ tự ở mức ngữ nghĩa:

~~~text
Lớp được yêu cầu/đề cập bởi hoạt động phù hợp
             |
             v
        LOADING
  tìm bytes / define Class
             |
             v
        LINKING
  verification -> preparation -> resolution (*)
             |
             v
      INITIALIZATION
  chạy logic khởi tạo class/interface
             |
             v
       Sử dụng kiểu theo ngữ nghĩa Java

(*) Resolution có thể diễn ra sớm hoặc trì hoãn; không phải mọi
    symbolic reference bắt buộc resolve cùng một thời điểm.
~~~

### 2.1. Loading — tìm/định nghĩa kiểu

Với một kiểu thông thường, class loader có thể:

1. Nhận yêu cầu về **binary name** như `com.example.service.ReportExporter`.
2. Tìm một định nghĩa thích hợp từ nguồn của loader (JAR, thư mục, module, bytes sinh động, ...).
3. Cung cấp class bytes cho JVM để **define** kiểu; JVM xây cấu trúc nội bộ cho class/interface và một đối tượng `java.lang.Class` biểu diễn kiểu ấy.
4. Ghi nhận quan hệ **defining class loader**, vì class identity ở runtime không chỉ dựa vào tên.

`ClassLoader.loadClass(...)` là một API cấp Java thường được dùng để đề nghị tải lớp, nhưng các chi tiết loader ủy quyền và nguồn bytes phụ thuộc triển khai.

**Không nhầm:** tìm thấy file `.class` ở ổ đĩa chưa đồng nghĩa phương thức static initializer của kiểu đó đã chạy. Ngược lại, một kiểu runtime không phải lúc nào cũng đến từ một file `.class` riêng đọc trực tiếp từ ổ đĩa: runtime có thể sinh bytecode hoặc định nghĩa lớp từ nguồn khác.

### 2.2. Linking — chuẩn bị lớp để dùng đúng và an toàn

*Linking* có ba nhóm hoạt động chính:

| Công đoạn | Mục đích |
| --- | --- |
| **Verification** | Kiểm tra ràng buộc của class file/bytecode, độ hợp lệ của stack type, control flow, quyền truy cập và những quy tắc kiểm chứng liên quan |
| **Preparation** | Cấp/chuẩn bị bộ nhớ và cấu trúc cho static fields; đặt giá trị ban đầu mặc định theo quy tắc, xử lý những hằng được khai báo qua `ConstantValue` |
| **Resolution** | Biến symbolic references tới class, field, method... thành tham chiếu runtime phù hợp, kiểm tra khả năng liên kết và truy cập |

**Preparation không đồng nghĩa initialization.** Ví dụ `static int count = 5;` nhận giá trị mặc định `0` ở giai đoạn chuẩn bị, rồi logic khởi tạo static field gán `5` trong initialization. Với `static final int LIMIT = 10;` là compile-time constant variable, class file có thể có `ConstantValue`; các quy tắc gán hằng trong preparation khác với thực thi một biểu thức runtime.

Một implementation có thể **resolve sớm** nhiều symbolic reference, hoặc trì hoãn cho đến khi thực tế sử dụng. Đặc tả yêu cầu bảo toàn các điều kiện như class được load trước khi link, được verify/prepare trước khi initialize và lỗi liên kết được phát sinh ở thời điểm chương trình có hành động có thể yêu cầu quá trình liên kết tương ứng. Vì thế **lazy loading không có nghĩa “mỗi lớp luôn được load đúng tại dòng Java đầu tiên đề cập tên nó”**.

### 2.3. Initialization — thực thi `<clinit>` nếu cần

Initialization xử lý static field initializers và `static {}` theo đúng thứ tự nguồn của các thành phần liên quan, thông thường được compiler gom thành class/interface initialization method tên JVM **`<clinit>`** khi cần.

~~~java
class Settings {
    static int port = loadPort();
    static {
        System.out.println("SETTINGS_INITIALIZED");
    }
    static int loadPort() {
        return 8080;
    }
}
~~~

Đây là **mảnh mã minh họa**, chưa phải chương trình tự chạy vì không có `main`. Khi `Settings` được initialized, `loadPort()` được gọi và static block in thông báo; nhưng chỉ có việc `Settings.class` xuất hiện trong một expression **không tự động kích hoạt** static block.

Initialization thường xảy ra **một lần cho mỗi runtime class được định nghĩa bởi loader tương ứng**, với cơ chế đồng bộ giữa các thread. Nếu một thread đang initialize class và thread khác cần class ấy, JVM áp dụng quy tắc phối hợp initialization; không chạy `<clinit>` tùy tiện đồng thời nhiều lần cho cùng class.

Class có thể không cần `<clinit>` riêng nếu không có logic khởi tạo động; vẫn có trạng thái “đã initialized” của kiểu. Cũng đừng dùng cụm “`new` mới là load”: một class có thể đã loaded và initialized từ một static call, không hề có instance nào.

## 3. Vì sao không nạp hết mọi lớp lúc startup?

### 3.1. Tránh công việc có thể không bao giờ cần

Giả sử hệ thống hỗ trợ bốn tính năng:

~~~text
app.jar
├── Main.class                 khởi động ứng dụng
├── core/RequestHandler.class thường dùng
├── export/PdfExporter.class  chỉ khi export PDF
├── billing/InvoiceJob.class  chỉ khi có lịch tính phí
└── admin/MigrationTool.class chỉ khi chạy migration
~~~

Nếu request hiện tại chỉ dùng `RequestHandler`, việc bắt buộc load và link mọi class của export, billing, admin ngay lập tức có thể làm phát sinh I/O, kiểm chứng, phân bổ metadata và phụ thuộc không cần thiết. Mô hình dynamic loading cho phép JVM **không làm tất cả những việc ấy từ đầu**.

Ví dụ cây trên là hình dung về **artifact chứa class**, không phải bản ghi cho biết lớp nào chính xác đã được loaded trong JVM cụ thể. Các class loader, framework và JVM có thể chủ động tải thêm lớp do quét annotation, discovery, proxy, verification, resolution hoặc warm-up.

### 3.2. Cân bằng khởi động, bộ nhớ và độ trễ lần dùng đầu

Lợi ích và chi phí thường gặp:

| Lựa chọn | Có thể cải thiện | Cái giá cần cân nhắc |
| --- | --- | --- |
| Load/link theo nhu cầu | Startup ít việc hơn, tránh xử lý nhiều class không được dùng, có thể giảm metadata resident | Lần đầu dùng tính năng có thể xuất hiện độ trễ load, verify, resolve và initialization |
| Eager initialization/preloading được kiểm soát | Dời công việc khỏi request đầu tiên, phát hiện lỗi sớm hơn, warm up | Startup lâu hơn, giữ thêm metadata/object và có thể khởi tạo phần không cần |
| Quét classpath/module path bằng framework | Tự đăng ký component, dependency injection, plugin discovery | Nhiều hoạt động class-loading hoặc reflective access trước khi request thật xuất hiện |

Không suy ra rằng **loading chiếm toàn bộ chi phí startup**. Một ứng dụng Java còn có JVM startup, GC/JIT runtime setup, khởi tạo framework, I/O, network connection, config, database migration... Và class loading không có quan hệ tuyến tính đơn giản “càng ít class thì chương trình luôn nhanh hơn” trong mọi workload.

### 3.3. Hỗ trợ plugin và định nghĩa lớp động

Khi hệ thống chỉ biết plugin sau khi khởi động, ví dụ plugin được lắp vào thư mục/module layer hoặc được tải từ một nguồn tùy biến, cơ chế class loader cho phép nạp định nghĩa mới khi có yêu cầu. Tuy nhiên, không phải cứ bỏ thêm JAR vào thư mục khi JVM đang chạy là ứng dụng **tự** nhận plugin; hệ thống cần logic discovery, loader/module layer, versioning và quản lý vòng đời.

Nhiều bytecode generation framework tạo proxy hoặc helper class ở runtime. Những kiểu này có thể không tồn tại dưới dạng file nguồn Java tương ứng trong source tree.

### 3.4. Không phải cơ chế “không tải dependency lỗi”

Dynamic loading có thể khiến một tính năng ít dùng chỉ bộc lộ lỗi missing class/method khi đường code đó được thực thi. Đây là **rủi ro trì hoãn lỗi**, không phải sự bảo đảm rằng JVM “sẽ bỏ qua vĩnh viễn” mọi dependency sai.

Một JVM có quyền link/resolve sớm trong phạm vi đặc tả; thư viện/framework cũng có thể load/initialize sớm. Nên triển khai smoke tests cho những đường plugin/feature quan trọng, thay vì coi “main đã chạy được” là bằng chứng mọi classpath dependency đều tốt.

## 4. JVM biết tới lớp khác bằng những con đường nào?

Một class file thường chứa **constant pool** với nhiều **symbolic references**, ví dụ tên kiểu `java/lang/String`, `com/example/Feature`, hoặc method descriptor chứa kiểu đối số. Những tên ấy giúp JVM tìm lớp khi cần resolve/liên kết.

~~~text
Main.class
  constant_pool:
    class Main
    class com/example/Feature
    Methodref com/example/Feature.run:()V
    class java/lang/String
    ...
~~~

Đây là sơ đồ mang tính khái niệm, không phải `javap -v` chính xác cho file thực tế.

**Có tên trong constant pool KHÔNG đồng nghĩa:** JVM đã đọc toàn bộ class bytes của tất cả class được nhắc đến, đã khởi tạo mọi superclass/interface liên quan hoặc đã thực thi static initializer của bất kỳ lớp nào. Một số kiểu có thể được load/resolve vì verification hoặc linking; việc lựa chọn thời điểm có giới hạn linh hoạt theo đặc tả.

Những hoạt động thường dẫn tới việc cần biết một lớp ở runtime gồm:

- `new SomeClass()` khi tạo object.
- Truy cập static field không phải compile-time constant hoặc gọi static method.
- Gọi instance method, kiểm tra cast/`instanceof`, truy cập field trên object (với class/reference cần thiết).
- Phản chiếu `Class.forName`, truy vấn method/field, `ClassLoader.loadClass` hoặc framework scanning.
- Method handles, `invokedynamic`, generated proxies, serialization, service loading khi tính năng sử dụng chúng.
- Việc link/verify/resolve lớp khác mà JVM quyết định cần xử lý.

**Không phải mọi hoạt động trên đều lập tức làm chạy static initializer của mọi kiểu liên quan.** Cần phân biệt *class được tải/resolve để hiểu kiểu* với *class phải initialization do hành vi sử dụng chủ động*.

## 5. Những trường hợp thường kích hoạt initialization

Theo JLS/JVMS (trong bối cảnh Java 17), những trường hợp đáng nhớ gồm:

1. **Tạo một instance** của class bằng `new` (trước khi constructor thực thi, class cần được initialized đúng quy tắc).
2. **Gọi static method** được class/interface tương ứng khai báo, ví dụ `Feature.run()`.
3. **Đọc static field không phải constant variable**, ví dụ `Settings.port`.
4. **Gán static field**, ví dụ `Settings.port = 9090`.
5. Một số yêu cầu từ **reflection** và API runtime tương ứng, như `Class.forName(String)`, cũng có thể trực tiếp yêu cầu initialization.
6. **Khởi động JVM:** lớp khởi đầu cần được load/link/initialize trước khi chạy `main`.
7. Khi initialized class, các **superclass** của nó được initialized trước, cùng những **superinterface khai báo default methods** theo quy tắc hiện đại nếu chưa được initialized.

Những quy tắc nói về class/interface **thực sự khai báo field hoặc method được resolve**, không chỉ tên tĩnh ở bề ngoài của một expression.

### 5.1. Class literal không tự khiến `<clinit>` chạy

~~~java
Class<?> type = Feature.class;
~~~

Biểu thức này tạo hoặc lấy một đối tượng `Class` biểu thị kiểu `Feature` cho chương trình, và JVM có thể load/link đủ thông tin cần thiết. Nhưng **không kích hoạt initialization của Feature chỉ vì class literal**. Đây là một ví dụ điển hình tại sao quan sát “chưa in static block” **không chứng minh class chưa loaded**.

### 5.2. Compile-time constant có thể được inline

~~~java
class Constants {
    static {
        System.out.println("INIT_CONSTANTS");
    }
    static final int LIMIT = 10;
    static int computed = Integer.parseInt("10");
}
~~~

Nếu caller tham chiếu `Constants.LIMIT`, Java compiler có thể nhúng literal `10` vào bytecode của caller; chỉ đọc compile-time constant variable này không kích hoạt initialization của `Constants`. Trái lại, truy cập `Constants.computed` thường dẫn đến `getstatic` và initialization nếu chưa xảy ra.

Điều này cũng có hậu quả ABI: đổi giá trị compile-time constant rồi chỉ thay JAR có thể không làm những caller đã biên dịch cũ nhận giá trị mới; cần rebuild caller khi phù hợp.

### 5.3. Tạo mảng không tự khởi tạo lớp phần tử

~~~java
Feature[] slots = new Feature[3];
~~~

Thao tác tạo object mảng có thể khiến runtime cần kiểu mảng/thành phần, nhưng **không tự gọi `Feature.<clinit>`** chỉ vì các phần tử có kiểu `Feature`. Các phần tử reference mặc định là `null`. Nếu sau đó thực sự viết `new Feature()`, class sẽ cần được initialized.

Các kiểu mảng do JVM tạo theo quy tắc riêng, **không có một file `[LFeature;.class` thông thường** cho mỗi kiểu mảng. Với `int[]`, các lớp thành phần primitive và việc JVM cung cấp `Class` object cho primitive cũng khác cơ chế đọc bytes của user-defined class.

### 5.4. `Class.forName` có chế độ initialization

| API / biểu thức | Thường cần load/resolve? | Có yêu cầu initialization không? |
| --- | --- | --- |
| `SomeType.class` | Có thể khiến runtime cần thông tin biểu diễn kiểu | **Không chỉ vì class literal** |
| `Class.forName("pkg.SomeType")` | Tìm/resolve kiểu theo API | **Có**, với overload một tham số cho class thông thường |
| `Class.forName(name, false, loader)` | Load/link theo hợp đồng API | **Không yêu cầu initialization** |
| `loader.loadClass(name)` | Yêu cầu loader tìm lớp | **Thông thường không** initialize, nhưng lớp khác có thể có side effect riêng từ custom loader |
| `new SomeType()` | Phải có class để tạo instance | **Có**, trước khi constructor chạy |
| `SomeType.nonConstantStatic` | Phải resolve field phù hợp | **Có**, nếu truy cập static field không phải constant variable |
| `SomeType.COMPILE_TIME_CONSTANT` | Caller có thể dùng literal đã inline | **Không chỉ do đọc constant variable** |

Đặc biệt, `Class.forName(name, false, loader)` vẫn có thể load và link, gây lỗi class loading/linking dù không initialize; **`initialize=false` không đồng nghĩa “đừng nạp class”**.

Không dùng bảng này làm lời hứa cứng về log class-loading: JVM có thể nạp kiểu sớm do linking/verification, và custom loader có thể có hành vi phụ.

## 6. Chương trình Java 17 hoàn chỉnh: minh họa “có Class nhưng chưa initialized”

Tạo đúng một file **`LazyLoadingDemo.java`**:

~~~java
public final class LazyLoadingDemo {
    static final class OnlyMentioned {
        static {
            System.out.println("INIT_ONLY_MENTIONED");
        }
    }

    static final class Feature {
        static {
            System.out.println("INIT_FEATURE");
        }

        static String run() {
            return "READY";
        }
    }

    static final class Config {
        static {
            System.out.println("INIT_CONFIG");
        }

        static final int LIMIT = 10;
        static int dynamic = compute();

        static int compute() {
            return 99;
        }
    }

    static final class Untouched {
        static {
            System.out.println("INIT_UNTOUCHED");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("MAIN");

        Class<?> description = OnlyMentioned.class;
        System.out.println("CLASS=" + description.getSimpleName());

        Class.forName(Feature.class.getName(), false,
                LazyLoadingDemo.class.getClassLoader());
        System.out.println("FOUND_FEATURE");

        System.out.println("CONST=" + Config.LIMIT);
        System.out.println("BEFORE_RUN");
        System.out.println("RESULT=" + Feature.run());

        System.out.println("BEFORE_CONFIG");
        System.out.println("DYNAMIC=" + Config.dynamic);

        Class.forName(OnlyMentioned.class.getName());
        System.out.println("FOR_NAME_DONE");
        System.out.println("END");
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file:

~~~bash
javac --release 17 LazyLoadingDemo.java
java LazyLoadingDemo
~~~

**Stdout dự kiến và có thể kiểm chứng bằng chương trình:**

~~~text
MAIN
CLASS=OnlyMentioned
FOUND_FEATURE
CONST=10
BEFORE_RUN
INIT_FEATURE
RESULT=READY
BEFORE_CONFIG
INIT_CONFIG
DYNAMIC=99
INIT_ONLY_MENTIONED
FOR_NAME_DONE
END
~~~

### Đọc kết quả từng mốc

1. `MAIN`: lớp `LazyLoadingDemo` đã sẵn sàng để thực thi method `main`.
2. `OnlyMentioned.class` cho một đối tượng `Class`. `getSimpleName()` được gọi nhưng **chưa thấy `INIT_ONLY_MENTIONED`**; điều này minh họa **class literal không yêu cầu initialization**, **không** chứng minh class chưa loaded.
3. `Class.forName(..., false, ...)` yêu cầu biết lớp `Feature` mà **chưa initialize** nó; `FOUND_FEATURE` xuất hiện trước `INIT_FEATURE`.
4. `Config.LIMIT` là compile-time constant `10`; dòng `CONST=10` không làm in `INIT_CONFIG`. Đây không phải dấu hiệu rằng file `Config.class` chưa từng được load.
5. Lần đầu gọi `Feature.run()`, JVM bảo đảm `Feature` được initialized trước khi thực thi method: `INIT_FEATURE` xuất hiện trước `RESULT=READY`.
6. Lần đọc `Config.dynamic` kích hoạt initialization của `Config`: `INIT_CONFIG` xuất hiện trước `DYNAMIC=99`.
7. Lời gọi `Class.forName(OnlyMentioned.class.getName())` ở overload một tham số yêu cầu initialization: `INIT_ONLY_MENTIONED` xuất hiện trước `FOR_NAME_DONE`.
8. `Untouched` không bao giờ được chủ động sử dụng trong chương trình. Không thấy `INIT_UNTOUCHED` nghĩa là **không thấy class initialization**, nhưng **không đủ chứng minh runtime chưa load/verify class đó**.

Điểm quan trọng nhất của ví dụ không phải đoán số lượng class đã load từ stdout, mà là **dùng static initializer để quan sát riêng sự kiện initialization**. Muốn quan sát loading, sử dụng log công cụ ở mục 7.

### Nếu thay `false` thành `true`?

Đoạn:

~~~java
Class.forName(Feature.class.getName(), true,
        LazyLoadingDemo.class.getClassLoader());
~~~

là **biến thể để thử riêng, không phải code nguyên bản của bài thực hành**. Khi `initialize=true`, `INIT_FEATURE` sẽ xuất hiện ngay ở lần `Class.forName` đó, trước `FOUND_FEATURE`. Đến lần gọi `Feature.run()` sau này, static initializer sẽ **không chạy lại** với cùng runtime class. Tương tự, chỉ khởi tạo một class khác có cùng binary name nhưng thuộc defining loader khác mới là một identity class khác cần xét riêng.

## 7. Quan sát class thực sự được load bằng công cụ JDK

### 7.1. `-Xlog:class+load=info` trên HotSpot / JDK 17

Với OpenJDK/HotSpot hỗ trợ Unified Logging:

~~~bash
java -Xlog:class+load=info LazyLoadingDemo
~~~

Bạn sẽ thấy nhiều log event dạng class loading, ngoài stdout của ví dụ. Số dòng log, tên module/JAR/loader và thứ tự có thể thay đổi theo JDK, classpath, cấu hình hoặc cách implementation thực hiện resolution; vì vậy **không đưa “stdout chính xác” cho chế độ bật logging**.

Ghi class-load log riêng vào file:

~~~bash
java -Xlog:class+load=info:file=class-load.log:uptime,level,tags LazyLoadingDemo
~~~

Sau đó lọc các dòng chứa tên app:

~~~bash
# Bash trên Linux/macOS
grep 'LazyLoadingDemo' class-load.log

# PowerShell trên Windows
Select-String -Path class-load.log -Pattern 'LazyLoadingDemo'
~~~

Lưu ý: các class trong JDK như `java.lang.Object`, `java.lang.String`, class loader, I/O và nhiều thành phần runtime có thể được tải trước khi `main` in dòng đầu tiên. Một JVM startup chỉ tải mỗi class `Main` theo nghĩa đen là mô tả **không chính xác**.

Dạng cũ `-verbose:class` cũng có thể dùng với nhiều Java launcher để xem thông tin class loading. Đối với hệ thống đang chạy production, bật class-load log mức cao có thể tăng lượng log và chi phí I/O; hãy thử trong môi trường kiểm thử.

### 7.2. `javap` không phải class-load log

~~~bash
javap -v LazyLoadingDemo
javap -c -p LazyLoadingDemo
~~~

`javap -v` cho biết **cấu trúc class file** và constant-pool references, còn `javap -c` hiển thị bytecode. Đây là phân tích **tĩnh của class file**, không tự nói thứ tự runtime đã load các lớp khác.

Ví dụ `javap` có thể cho thấy tham chiếu tới `Feature.run()` và `Config.dynamic`. Nhưng **việc comment `// Method ...` xuất hiện trong disassembly không chứng minh method hay `<clinit>` đã thực thi**.

### 7.3. JAR chứa class không có nghĩa JVM đã load tất cả

~~~bash
jar tf app.jar
~~~

Lệnh trên (nếu có `app.jar`) chỉ liệt kê file bên trong archive. Nó không khởi chạy ứng dụng và không phải thống kê lớp đã được JVM load. Đây là khác biệt giữa **có trên classpath**, **đã load**, **đã link**, và **đã initialize**.

## 8. ClassLoader: lớp do ai định nghĩa cũng quan trọng

Một lớp Java được định danh tại runtime bằng **binary name kết hợp với defining class loader** (đối với các kiểu không ẩn và mô hình thông thường). Hai loader khác nhau có thể định nghĩa hai kiểu có **cùng binary name** nhưng JVM vẫn coi chúng là **hai runtime class khác nhau**.

Ví dụ tư duy:

~~~text
Loader A định nghĩa com.acme.Plugin  ---> Class A
Loader B định nghĩa com.acme.Plugin  ---> Class B

Tên binary giống nhau; defining loader khác nhau;
vì thế Class A != Class B tại runtime.
~~~

Hậu quả:

- Cast giữa hai kiểu không tương thích có thể gây `ClassCastException`, dù cả hai được gọi là `com.acme.Plugin` ở log.
- Các `static` field và quá trình initialization thuộc về **mỗi runtime class** riêng, không gom chung chỉ dựa vào tên.
- Trong môi trường app server, plugin và test runner, lỗi `ClassCastException: Foo cannot be cast to Foo` có thể liên quan nhiều class loader, không nhất thiết source class sai.

### 8.1. Bootstrap, platform, application loader

Trong JDK hiện đại thường thấy:

- **Bootstrap class loader:** cơ chế nền của VM, tải nhiều class nền tảng như `java.lang.Object`; trong API `Class.getClassLoader()`, lớp bootstrap thường trả **`null`** theo hợp đồng.
- **Platform class loader:** tải nhiều module/platform classes theo cơ chế triển khai JDK.
- **Application/system class loader:** thường tải ứng dụng từ classpath/module path do launcher định nghĩa.

Mối quan hệ loader thực tế có thể phức tạp, nhất là module layers, application servers, plugin frameworks. **Parent-first delegation** là mô hình mặc định phổ biến của `ClassLoader.loadClass`: hỏi loader cha trước rồi mới tìm class của mình; **không phải định luật cấm mọi loader tùy biến làm child-first** trong phạm vi được phép.

Phân biệt:

- **Initiating loader:** loader nhận/khởi đầu yêu cầu nạp class.
- **Defining loader:** loader thực sự định nghĩa class đó. Hai khái niệm này có thể khác nhau do delegation.
- **Runtime package** cũng chịu ảnh hưởng của defining loader; hai class có package name cùng chuỗi nhưng loader khác không tự động ở cùng runtime package đối với access checks.

### 8.2. ClassLoader context và module system

Nhiều framework đọc **thread context class loader** khi discovery plugin/resource để không bị giới hạn vào loader của code thư viện. Với Java Platform Module System (JPMS), module graph và readability/export rules còn tác động khả năng resolve/access.

Tuy nhiên, class loader **không tự xử lý** hoàn chỉnh dependency injection, discovery hoặc quản lý module lifecycle. Nó là tầng nạp/định danh lớp; nhiều công việc cấp ứng dụng được thực hiện bởi framework.

## 9. Loading, initialization và `new` không đồng nghĩa nhau

| Tình huống | Điều thực sự diễn ra |
| --- | --- |
| `obj = new Service()` | Cần class `Service` được initialized; tạo instance, gọi constructor theo quy tắc |
| `Service.runStatic()` | Có thể initialize `Service` nhưng **không tạo instance Service** |
| `Service.class` | Có thể tạo/nhận `Class<Service>`; không yêu cầu chạy static initializer |
| `new Service[5]` | Tạo **mảng reference Service** với phần tử null; không tạo 5 Service instance |
| `Class.forName("Service", false, loader)` | Có thể load/link Service nhưng không yêu cầu initialize |
| `Object o = new Object()` | Không chứng minh JVM đã load mọi class kế thừa Object ở toàn bộ classpath |
| `main()` bắt đầu | Lớp chạy main đã được initialize, cùng các dependency bắt buộc; **không phải tất cả class toàn chương trình** |

Đây còn là lý do cụm “JVM đọc file Java khi chạy” không đúng với cơ chế chuẩn: launcher làm việc với class/module artifacts; class loader đưa binary representation phù hợp cho JVM. Source `.java` không phải đầu vào mặc định của mọi bytecode load, dù Java launcher có hỗ trợ chế độ thực thi source-file ở mức công cụ phát triển.

## 10. Những lỗi bộc lộ khác thời điểm vì nạp/liên kết động

### 10.1. `ClassNotFoundException` khác `NoClassDefFoundError`

| Triệu chứng | Ngữ cảnh điển hình | Hướng kiểm tra |
| --- | --- | --- |
| `ClassNotFoundException` | API phản chiếu/loader được yêu cầu tìm class theo tên nhưng không tìm được, chẳng hạn `Class.forName("missing.Plugin")` | Tên binary, module/classpath, JAR, case-sensitive path, loader được truyền |
| `NoClassDefFoundError` | JVM cần một class tại runtime nhưng định nghĩa không có/không dùng được, hoặc một class trước đó đã lỗi initialization | Nguyên nhân gốc (thường trong `Caused by`), classpath/version, class initialization trước đó |
| `ExceptionInInitializerError` | Exception thoát bất thường khỏi code initialization của class (theo những quy tắc bao bọc Throwable) | Static fields/blocks, cấu hình, I/O, recursive initialization |
| `UnsupportedClassVersionError` | Class file được biên dịch cho phiên bản JVM cao hơn phiên bản runtime hỗ trợ | Bytecode major version, JDK chạy thực tế và `--release` |
| `ClassFormatError` / `VerifyError` | Binary class file hoặc quy tắc bytecode/verification không hợp lệ | Class file build/transform/obfuscation, dependency và version |
| `NoSuchMethodError` / `NoSuchFieldError` | Caller tham chiếu member với tên/descriptor không còn khớp binary ở runtime | Jar hell, API/ABI thay đổi, transitive dependency |

**Quan trọng:** `NoClassDefFoundError` không phải lúc nào cũng có nghĩa **tệp `.class` không tồn tại**. Ví dụ `<clinit>` của class lỗi ở lần khởi tạo đầu; lần sử dụng sau có thể nhận `NoClassDefFoundError: Could not initialize class ...`. JVM không tự “chạy lại static initializer” một cách tùy ý để sửa trạng thái lỗi của cùng class.

### 10.2. Lỗi có thể xuất hiện muộn

Ví dụ một class `PdfExporter` phụ thuộc thư viện chỉ dùng lúc export. Nếu startup không cần resolve hoặc initialize đường export, ứng dụng có thể chạy được bình thường cho tới khi người dùng bấm Export. Khi đó JVM hoặc framework mới cần class liên quan và lỗi dependency xuất hiện.

Nhưng đừng cam kết “lỗi chắc chắn chỉ xảy ra lúc bấm Export”: JVM được phép thực hiện một số linking sớm; framework cũng có thể preload/scan. **Thời điểm lỗi chính xác** cần căn cứ stack trace và cấu hình runtime.

### 10.3. Quy trình chẩn đoán thực tế

1. Xác định **class nào** lỗi và **operation nào** kích hoạt: load bằng tên, call method, access field, create instance, reflection hoặc plugin discovery.
2. Kiểm tra artifact chứa class, classpath/module path và version JDK: `java -version`, build target, JAR thực có trong runtime.
3. Tìm **caused by đầu tiên** trong stack trace; đừng chỉ đọc thông báo `NoClassDefFoundError` ở cuối.
4. Bật class-load logging có chọn lọc trong môi trường thử nghiệm, rồi đối chiếu **class được load từ nguồn nào**.
5. Kiểm tra loader identity khi app server/plugin có nhiều loader. Dùng `someObject.getClass().getClassLoader()` để quan sát loader của object khi phù hợp (bootstrap có thể null).
6. Nếu lỗi ở static initialization, kiểm tra thứ tự init, side effects, recursive dependency và cấu hình cần thiết **trước lần active use đầu tiên**.
7. Kiểm tra đường feature ít dùng bằng smoke test thay vì chỉ thử startup.

## 11. Class unloading: không phải class nào đã nạp cũng tồn tại vĩnh viễn

JVM có cơ chế **class unloading** dưới những điều kiện phù hợp. Với class do user-defined loader định nghĩa, khả năng giải phóng class metadata thường liên quan tới việc **defining loader** và các cấu trúc liên quan không còn reachable, cùng quy tắc GC/implementation.

Không có lời hứa rằng `System.gc()` lập tức unload một class. Một class được load nhiều lần bởi **cùng loader** theo cách bình thường không có nghĩa mỗi lần tạo một định nghĩa class mới; loader phải tuân thủ các ràng buộc về định danh/định nghĩa, và JVM quản lý trạng thái loaded/linked/initialized của runtime class.

**Class loader leak** có thể khiến class metadata và object liên quan không được giải phóng: ví dụ giữ reference tới plugin loader trong static cache, thread hoặc thread context class loader sau khi plugin đã tắt. Khi thiết kế hot-reload, phải quản lý resources, threads, caches và các static references, không chỉ xóa file JAR.

Trong HotSpot thường có vùng **Metaspace** để lưu nhiều loại class metadata, nhưng tên vùng, chính sách cấp phát và GC là chi tiết triển khai, không phải yêu cầu rằng mọi JVM bắt buộc dùng layout giống hệt.

## 12. Các ngộ nhận quan trọng cần bỏ

1. **“Ứng dụng có 10.000 class thì JVM nạp cả 10.000 trước main.”** Không có quy tắc như vậy.
2. **“Có tên trong constant pool là class đã nạp.”** Không; symbolic reference có thể còn chờ resolution.
3. **“Lazy load nghĩa là class được load đúng ở câu lệnh đầu tiên dùng nó.”** Không; verification/resolution có thể làm load sớm, loader/framework cũng có thể preload.
4. **“Class được loaded tức là static block đã chạy.”** Sai; initialization là pha riêng.
5. **“`Class.forName(..., false, ...)` không load class.”** Sai; `false` điều khiển initialization, không tắt loading.
6. **“`SomeType.class` chắc chắn chạy `<clinit>`.”** Sai; class literal không tự initialize.
7. **“Đọc `static final int` luôn initialize class.”** Sai nếu đây là compile-time constant variable được dùng theo quy tắc Java.
8. **“`new Widget[10]` tạo 10 object Widget.”** Sai; đó là một object mảng chứa các phần tử reference null.
9. **“`ClassNotFoundException` và `NoClassDefFoundError` là một.”** Sai; API/ngữ cảnh và nguyên nhân khác nhau.
10. **“Nếu app chạy tới main, mọi dependency đều không lỗi.”** Sai; đường code chưa dùng có thể lỗi sau.
11. **“Hai class cùng full name luôn là cùng class.”** Sai; defining class loader thuộc identity.
12. **“Class loading càng lazy thì luôn càng nhanh.”** Sai; có trade-off startup so với first-use latency và chi phí động.
13. **“Mỗi class chỉ initialize một lần trong cả hệ điều hành.”** Sai; trạng thái thuộc từng runtime class/loader trong tiến trình JVM tương ứng.
14. **“Khi class initialized thất bại, lần truy cập sau tự chạy lại initializer.”** Không có cơ chế retry tùy ý như vậy cho cùng class đã vào trạng thái lỗi.
15. **“`javap` chứng minh một class đã loaded trong process.”** Sai; `javap` đọc class file tĩnh, còn class-load log quan sát runtime.

## 13. Câu hỏi tự kiểm tra

1. Class loading gồm điều gì? **Tìm binary representation phù hợp và tạo kiểu runtime**, không phải tự động chạy `static {}`.
2. Linking có các phần nào? **Verification, preparation và resolution**, với thời điểm resolution có thể linh hoạt trong giới hạn đặc tả.
3. Điều kiện cần trước khi initialization? **Class đã hoàn tất loading, verification và preparation**, và các quy tắc phụ thuộc khởi tạo được tôn trọng.
4. Tại sao không được dùng “không thấy INIT” để chứng minh “chưa loaded”? Vì **static initializer chỉ phản ánh initialization**, class có thể đã load/link trước.
5. Đọc `Config.LIMIT` là compile-time constant có làm `INIT_CONFIG` chạy không? **Không chỉ vì lần đọc này**.
6. `Class.forName(name)` và `Class.forName(name,false,loader)` khác nhau điểm chính nào? **Overload một tham số yêu cầu initialization; overload với `false` không yêu cầu initialization**.
7. `new Feature[3]` có gọi constructor của ba Feature không? **Không**.
8. Tại sao một class trong JAR có thể chưa được load? Vì JAR là **nguồn bytes sẵn có**, không đồng nghĩa mọi lớp được dùng/liên kết ở startup.
9. Hai loader định nghĩa cùng binary name có tạo cùng runtime class không? **Không**.
10. Vì sao lỗi dependency có thể chỉ xảy ra ở request thứ 100? Vì đường code đó có thể chỉ bắt đầu **load/link/initialize** dependency khi request ấy dùng feature; dù cũng có thể được phát hiện sớm.
11. `-Xlog:class+load=info` quan sát gì? **Những sự kiện class loading do JVM có cơ chế logging ấy ghi lại**; không phải danh sách static initializer đã chạy.
12. Có nên preload toàn bộ class để tránh mọi lỗi không? **Không mặc định**; chọn chiến lược startup/warmup/smoke test dựa trên latency, memory và độ tin cậy.
13. Class unloading có bảo đảm ngay khi gán reference bằng null không? **Không**; GC, class loader reachability và implementation quyết định.
14. `NoClassDefFoundError` có thể đến từ lỗi initialization trước đó không? **Có**, không chỉ do thiếu class file.

## 14. Tài liệu chuẩn và định hướng đào sâu

- JVM Specification Java SE 17, chương **Loading, Linking, and Initializing**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- JVM Specification, mục **Creation and Loading**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- JVM Specification, mục **Linking**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- JVM Specification, mục **Initialization**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- Java Language Specification Java SE 17, chương **Execution**, các mục 12.2–12.4: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- `java.lang.Class` Java 17 API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- `java.lang.ClassLoader` Java 17 API: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html

**Kết luận:** class loading là quá trình JVM nhận và định nghĩa **kiểu runtime**, không phải đọc mọi tệp của chương trình vào RAM ngay lập tức và cũng không phải chạy `static {}`. JVM hỗ trợ nạp và liên kết động để giảm công việc không cần thiết và phục vụ các hệ thống plugin/runtime linh hoạt, nhưng được phép thực hiện một số resolution sớm. Phân biệt thật rõ **loading → linking → initialization**, **lớp có trong JAR → lớp được load → lớp được initialized**, cùng **class identity = binary name + defining loader** là nền tảng để hiểu startup, first-use latency và lỗi classpath trong ứng dụng Java.
