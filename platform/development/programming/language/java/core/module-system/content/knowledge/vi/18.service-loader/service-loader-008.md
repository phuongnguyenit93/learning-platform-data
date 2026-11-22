# Context class loader với service discovery

## 1. Context class loader là gì?

Mỗi lớp Java được định nghĩa bởi một class loader. Có thể xem loader đã định nghĩa một lớp bằng **Class.getClassLoader()**. Tuy nhiên, một thread còn có một loader ngữ cảnh riêng, gọi là **context class loader (TCCL)**, lấy bằng **Thread.currentThread().getContextClassLoader()**.

    ClassLoader definingLoader = Codec.class.getClassLoader();
    ClassLoader contextLoader =
            Thread.currentThread().getContextClassLoader();

Hai loader này có thể giống hoặc khác nhau:

- **Defining class loader** là loader đã nạp và định nghĩa lớp cụ thể. Danh tính lớp trong JVM phụ thuộc vào tên nhị phân và loader định nghĩa nó.
- **Context class loader** là loader được gắn với thread để mã đang chạy trên thread có thể dùng khi tìm lớp hoặc tài nguyên. Nó là một ngữ cảnh được truyền cho thư viện và framework.

TCCL giải quyết một tình huống phổ biến: một thư viện được nạp bởi loader của framework cần tìm implementation do ứng dụng hoặc plugin cung cấp. Nếu thư viện chỉ dùng loader định nghĩa chính nó, loader đó có thể không nhìn thấy các lớp nằm trong vùng nạp của ứng dụng. TCCL cho phép thread mang theo loader phù hợp với ứng dụng đang thực hiện công việc.

TCCL được đọc và thay đổi qua:

    Thread thread = Thread.currentThread();
    ClassLoader loader = thread.getContextClassLoader();

    thread.setContextClassLoader(loader);

Khi một thread mới được tạo, context class loader ban đầu thường được kế thừa từ thread cha tại thời điểm tạo thread. Vì vậy, giá trị này có thể khác nhau giữa các thread. Với thread pool, thread worker có thể được tạo từ lâu và tiếp tục giữ context loader cũ nếu ứng dụng không quản lý nó rõ ràng.

## 2. Vì sao ServiceLoader dùng context class loader?

**ServiceLoader** là cơ chế chuẩn của Java để tìm và tạo các implementation của một service mà không buộc ứng dụng phụ thuộc trực tiếp vào lớp implementation.

Một service thường là interface hoặc abstract class. Ví dụ:

    package com.example.codec;

    public interface Codec {
        String name();
        byte[] encode(String input);
    }

Thư viện chỉ cần biết kiểu **Codec**. Các module hoặc JAR khác có thể cung cấp implementation như **JsonCodec** hay **XmlCodec**. Ứng dụng yêu cầu các provider thông qua ServiceLoader:

    ServiceLoader<Codec> codecs =
            ServiceLoader.load(Codec.class);

    for (Codec codec : codecs) {
        System.out.println(codec.name());
    }

Overload **ServiceLoader.load(Class)** sử dụng context class loader của thread hiện tại. Về mặt API, lời gọi:

    ServiceLoader.load(Codec.class);

tương đương:

    ServiceLoader.load(
            Codec.class,
            Thread.currentThread().getContextClassLoader());

Đây là lý do TCCL thường xuất hiện trong service discovery. Một thư viện có thể gọi ServiceLoader mà không cần biết loader riêng của từng ứng dụng. Thread đã mang context loader do môi trường chạy hoặc ứng dụng thiết lập; ServiceLoader dùng loader đó làm điểm bắt đầu để tìm provider.

TCCL chỉ ảnh hưởng đến những API thực sự sử dụng nó. Việc đổi TCCL không làm thay đổi loader đã định nghĩa các lớp hiện có và cũng không tự động thay đổi mọi thao tác nạp lớp trong JVM.

## 3. Service discovery trên classpath

Khi provider được đóng gói dưới dạng JAR trên classpath, ServiceLoader nhận diện provider thông qua file cấu hình trong thư mục **META-INF/services**.

Tên file là tên nhị phân đầy đủ của service. Với service **com.example.codec.Codec**, JAR provider có file:

    META-INF/services/com.example.codec.Codec

Nội dung file liệt kê tên nhị phân đầy đủ của các provider, mỗi provider trên một dòng:

    com.example.codec.json.JsonCodec
    com.example.codec.xml.XmlCodec

File được mã hóa UTF-8. Dòng trống và khoảng trắng quanh tên provider được bỏ qua; ký tự **#** mở đầu phần chú thích trên dòng. Một provider trùng lặp được bỏ qua.

Khi gọi **ServiceLoader.load(Codec.class)**, TCCL được dùng để tìm các tài nguyên cấu hình service và nạp các lớp provider được liệt kê. Provider phải nhìn thấy được từ loader được dùng để tìm kiếm. Vì thế, một file META-INF/services tồn tại trong JAR chưa đủ để bảo đảm provider được phát hiện: JAR đó và provider class phải nằm trong phạm vi mà loader có thể truy cập.

Có thể truyền loader tường minh khi ứng dụng đã biết loader cần dùng:

    ClassLoader pluginLoader = getPluginClassLoader();

    ServiceLoader<Codec> codecs =
            ServiceLoader.load(Codec.class, pluginLoader);

Cách này làm rõ phạm vi discovery và không phụ thuộc giá trị TCCL ngầm định của thread.

## 4. Service discovery trên module path với JPMS

Khi provider được đóng gói trong named module, metadata service nằm trong **module-info.java** thay vì dựa vào file META-INF/services.

Module chứa service công khai kiểu service:

    module com.example.codec.api {
        exports com.example.codec;
    }

Module ứng dụng khai báo rằng nó sử dụng service:

    module com.example.application {
        requires com.example.codec.api;
        uses com.example.codec.Codec;
    }

Module cung cấp implementation khai báo provider:

    module com.example.codec.json {
        requires com.example.codec.api;

        provides com.example.codec.Codec
            with com.example.codec.json.JsonCodec;
    }

Directive **uses** cho biết module ứng dụng có nhu cầu tìm provider của service. Nếu caller nằm trong explicit named module mà module descriptor không khai báo uses cho service, các phương thức load tương ứng có thể ném **ServiceConfigurationError**.

Directive **provides ... with ...** đăng ký provider với JPMS. Package chứa implementation thường không cần export cho ứng dụng tiêu thụ service; ứng dụng làm việc thông qua kiểu service công khai. Điều này giúp module provider giữ kín chi tiết triển khai.

ServiceLoader hỗ trợ cả provider trên classpath lẫn provider trong named module. Với overload nhận class loader, quá trình tìm kiếm xét provider trong các named module liên quan đến loader và các loader cha, sau đó xét provider trong unnamed module thông qua các file cấu hình service mà loader tìm được. Nếu một loader thuộc module layer, việc tìm provider named module có thể bao gồm các module trong layer đó, kể cả module được định nghĩa bởi loader khác trong cùng layer.

Khi ứng dụng muốn chỉ rõ module layer cần tra cứu, dùng:

    ModuleLayer pluginLayer = ...;

    ServiceLoader<Codec> codecs =
            ServiceLoader.load(pluginLayer, Codec.class);

Overload này tìm provider trong module layer được chỉ định và các layer cha của nó. Nó không tìm provider trong unnamed module. Đây là lựa chọn rõ ràng cho hệ thống plugin tạo module layer động và cần giới hạn discovery theo layer.

## 5. Chọn overload ServiceLoader phù hợp

| API | Phạm vi discovery | Khi nên dùng |
|---|---|---|
| **ServiceLoader.load(service)** | Dùng TCCL hiện tại làm loader bắt đầu tìm provider | Thư viện hoặc framework muốn tôn trọng loader ngữ cảnh của ứng dụng |
| **ServiceLoader.load(service, loader)** | Dùng loader được truyền vào để tìm provider trong named và unnamed modules mà loader có thể truy cập | Ứng dụng biết rõ plugin loader cần sử dụng |
| **ServiceLoader.load(layer, service)** | Tìm provider trong named modules thuộc layer và các layer cha; không tìm unnamed modules | Ứng dụng quản lý module layer riêng |
| **ServiceLoader.loadInstalled(service)** | Dùng platform class loader | Chỉ muốn provider được cài đặt ở phạm vi platform |

Không nên chọn overload chỉ theo thói quen. Hãy xác định provider được triển khai trên classpath, module path hay module layer động, rồi chọn loader hoặc layer thể hiện đúng phạm vi mong muốn.

**loadInstalled** không phải lựa chọn thay thế chung cho **load**. Nó dùng platform class loader, nên provider chỉ có trên application classpath hoặc application module path sẽ không được tìm thấy qua overload này.

## 6. Thiết lập TCCL có kiểm soát

Một framework đôi khi cần đặt TCCL thành loader của ứng dụng hoặc plugin trong lúc chạy một đoạn mã. Hãy lưu giá trị cũ và khôi phục trong khối **finally**:

    Thread thread = Thread.currentThread();
    ClassLoader previous = thread.getContextClassLoader();

    try {
        thread.setContextClassLoader(pluginLoader);

        ServiceLoader<Codec> codecs =
                ServiceLoader.load(Codec.class);

        for (Codec codec : codecs) {
            System.out.println(codec.name());
        }
    } finally {
        thread.setContextClassLoader(previous);
    }

Việc khôi phục đặc biệt quan trọng khi dùng thread pool. Worker thread được tái sử dụng cho nhiều tác vụ; nếu một tác vụ để lại TCCL của plugin, tác vụ tiếp theo có thể phát hiện nhầm provider hoặc giữ tham chiếu tới loader cũ. Tham chiếu đó cũng có thể giữ lại class loader và các lớp của plugin, khiến việc unload plugin hoặc thu hồi bộ nhớ khó khăn.

Nếu chỉ cần một lần service discovery, truyền loader tường minh thường đơn giản hơn việc thay đổi TCCL:

    ServiceLoader<Codec> codecs =
            ServiceLoader.load(Codec.class, pluginLoader);

Chỉ thay đổi TCCL khi mã được gọi hoặc framework cần đọc context loader từ thread. Không đặt TCCL thành plugin loader rồi quên khôi phục.

TCCL ban đầu của thread con thường được kế thừa tại thời điểm thread được tạo. Điều này có nghĩa thread được tạo trước khi ứng dụng đổi TCCL có thể không mang loader mới. Với executor hoặc thread pool, cần xác định ai chịu trách nhiệm đặt và khôi phục loader cho từng tác vụ.

## 7. Discovery là lazy và provider được cache

Việc tạo **ServiceLoader** chưa có nghĩa tất cả provider đã được nạp và khởi tạo. Provider được tìm, nạp và tạo instance theo nhu cầu khi ứng dụng duyệt **iterator()** hoặc xử lý **stream()**.

    ServiceLoader<Codec> codecs =
            ServiceLoader.load(Codec.class);

    for (Codec codec : codecs) {
        // Provider được khởi tạo khi iterator duyệt đến provider đó.
        System.out.println(codec.name());
    }

Nếu chỉ muốn xem thông tin kiểu provider trước khi tạo instance, có thể dùng **stream()** và **ServiceLoader.Provider**:

    ServiceLoader.load(Codec.class)
            .stream()
            .map(provider -> provider.type().getName())
            .forEach(System.out::println);

Gọi **Provider.type()** cho phép xem lớp provider mà chưa cần lấy instance. Gọi **Provider.get()** mới lấy instance từ provider.

Một ServiceLoader lưu cache các provider đã được nạp. Các lần duyệt tiếp theo sử dụng các provider đã cache trước, rồi mới tiếp tục tìm provider còn lại. Gọi **reload()** để xóa cache và cho phép nạp lại provider:

    codecs.reload();

ServiceLoader được tạo với loader tại thời điểm gọi **load**. Thay đổi TCCL sau đó không tự chuyển ServiceLoader hiện có sang loader mới. Nếu cần discovery theo loader mới, hãy tạo ServiceLoader mới bằng overload phù hợp.

## 8. Lỗi thường gặp khi service discovery

### Không tìm thấy provider

Kiểm tra các điểm sau:

- TCCL của thread có phải loader mà ứng dụng mong muốn không?
- JAR provider có nằm trong phạm vi tìm kiếm của loader không?
- File **META-INF/services** có đúng tên service và đúng vị trí không?
- Tên provider trong file có phải tên nhị phân đầy đủ và lớp có thể được loader nhìn thấy không?
- Với named module, provider module có khai báo **provides** đúng service không?
- Module layer chứa provider có nằm trong phạm vi discovery không?
- Caller trong explicit named module đã khai báo **uses** chưa?

Có thể in thông tin loader để chẩn đoán:

    Thread thread = Thread.currentThread();

    System.out.println("Thread: " + thread.getName());
    System.out.println("Context loader: "
            + thread.getContextClassLoader());
    System.out.println("Service loader: "
            + Codec.class.getClassLoader());
    System.out.println("Service module: "
            + Codec.class.getModule());

### Provider không tương thích kiểu service

Service type và provider phải tương thích về danh tính kiểu tại runtime. Nếu ứng dụng và plugin cùng nạp hai bản sao của interface **Codec** bằng hai loader độc lập, JVM có thể xem chúng là hai kiểu khác nhau dù tên package và tên lớp giống hệt nhau.

Khi đó provider có thể không được xem là implementation của service mà ứng dụng đang dùng, hoặc phát sinh lỗi liên quan đến kiểu khi nạp và sử dụng provider. Nên đặt API service dùng chung ở một loader/module được chia sẻ giữa host và plugin; tránh đóng gói bản sao độc lập của API đó vào từng plugin.

### ServiceConfigurationError

**ServiceConfigurationError** có thể xuất hiện khi ServiceLoader không đọc được cấu hình, không nạp được provider, provider không tương thích với service, thiếu constructor/provider method hợp lệ hoặc quá trình tạo provider thất bại. Với explicit named module, thiếu directive **uses** cũng là nguyên nhân cần kiểm tra.

Lỗi có thể xuất hiện khi duyệt iterator, kể cả ở **hasNext()** hoặc **next()**, hoặc khi thực hiện thao tác trên stream khiến provider được tìm hay nạp. Vì quá trình là lazy, không nên chỉ kiểm tra việc tạo ServiceLoader rồi kết luận discovery đã thành công.

### Dùng chung ServiceLoader giữa nhiều thread

Các instance **ServiceLoader** không an toàn khi nhiều thread cùng sử dụng đồng thời. Không nên chia sẻ một instance mutable cho nhiều thread mà không có đồng bộ. Thông thường, tạo loader riêng theo phạm vi tác vụ hoặc đồng bộ hóa rõ ràng nếu cần chia sẻ.

### Cache ServiceLoader trên toàn JVM

Không nên cache một ServiceLoader tạo bằng **ServiceLoader.load(service)** ở phạm vi toàn JVM khi môi trường có nhiều ứng dụng hoặc plugin. Mỗi thread có thể có TCCL khác nhau; provider tìm thấy trong ngữ cảnh của một ứng dụng có thể không phù hợp với ứng dụng khác. Cache như vậy còn có thể giữ tham chiếu tới plugin class loader và gây rò rỉ bộ nhớ.

## 9. Quy trình chẩn đoán nhanh

Khi service discovery không tìm thấy provider hoặc tìm nhầm provider, có thể lần lượt kiểm tra:

1. Xác định kiểu service đang dùng: gọi **Codec.class.getModule()** và **Codec.class.getClassLoader()**.
2. Xác định TCCL tại đúng thread thực hiện lời gọi: **Thread.currentThread().getContextClassLoader()**.
3. Xác định overload ServiceLoader: mặc định dùng TCCL, truyền loader tường minh hay chỉ định module layer.
4. Kiểm tra nơi triển khai provider: file META-INF/services trên classpath hay directive provides trong module descriptor.
5. Với named module, kiểm tra **uses**, **provides**, module path và module layer.
6. Kiểm tra service interface có bị nạp thành nhiều bản sao bởi các loader khác nhau không.
7. Duyệt iterator hoặc stream và ghi nhận **ServiceConfigurationError** thực tế; discovery diễn ra lazy nên lỗi có thể chỉ xuất hiện khi duyệt.

## 10. Ghi nhớ

- TCCL là loader ngữ cảnh của thread; defining loader là loader đã định nghĩa một lớp. Hai giá trị có thể khác nhau.
- **ServiceLoader.load(service)** sử dụng TCCL của thread hiện tại.
- **ServiceLoader.load(service, loader)** dùng loader được chỉ định, phù hợp khi muốn kiểm soát rõ phạm vi tìm provider.
- **ServiceLoader.load(layer, service)** tìm provider trong module layer và các layer cha, không tìm provider trong unnamed modules.
- Provider trên classpath được khai báo bằng **META-INF/services/**; provider trong named module được khai báo bằng **provides** và consumer module khai báo **uses**.
- TCCL không cấp quyền JPMS và không sửa đổi danh tính của lớp đã được nạp.
- Khôi phục TCCL trong **finally**, nhất là khi dùng thread pool hoặc plugin.
- ServiceLoader nạp provider lazy, cache các provider đã nạp và không an toàn cho nhiều thread dùng chung.
- Khi provider không được tìm thấy, kiểm tra loader, module layer, cấu hình service và danh tính lớp service trước khi thay đổi cấu hình runtime.

**Context class loader là cầu nối để thư viện tìm thấy implementation do ứng dụng hoặc plugin cung cấp.** Khi kết hợp với ServiceLoader, cần chọn đúng loader hoặc module layer và quản lý vòng đời của nó theo từng thread/tác vụ.

## Tài liệu tham khảo

- Java SE 21 API — ServiceLoader: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 21 API — Thread: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html