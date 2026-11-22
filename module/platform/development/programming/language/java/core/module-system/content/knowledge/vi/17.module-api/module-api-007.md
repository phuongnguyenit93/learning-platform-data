# Module.getClassLoader() và giới hạn của ClassLoader

## 1. Vai trò của Module.getClassLoader()

Từ Java 9, Java Platform Module System (JPMS) bổ sung lớp **java.lang.Module** để biểu diễn một module đang được JVM nạp. Mỗi module được định nghĩa bởi một class loader. Phương thức **Module.getClassLoader()** trả về class loader đã định nghĩa module đó.

    Module module = Main.class.getModule();
    ClassLoader loader = module.getClassLoader();

Cách lấy này hữu ích khi cần tìm hiểu một lớp thuộc module nào và module đó được nạp bởi loader nào. Thông thường, hãy bắt đầu từ một lớp mà ứng dụng đã biết, gọi **Class.getModule()**, rồi lấy loader từ đối tượng Module tương ứng.

Cần phân biệt hai khái niệm:

- **Module** mô tả ranh giới module: tên module, các module mà nó đọc được, package được export hoặc open và những quan hệ liên quan.
- **ClassLoader** chịu trách nhiệm tìm và định nghĩa các lớp. Loader tham gia quyết định một tên lớp được ánh xạ thành đối tượng Class nào trong JVM.

Một class loader có thể định nghĩa nhiều named module và cả unnamed module của chính nó. Vì vậy, quan hệ giữa module và class loader không nhất thiết là một-một. Không thể suy ra rằng mỗi module luôn có một loader riêng, hoặc mọi module do cùng loader định nghĩa đều là cùng một module.

Trong JVM, danh tính của một lớp gắn với **tên nhị phân của lớp và class loader đã định nghĩa lớp đó**. Hai lớp có cùng tên đầy đủ nhưng được định nghĩa bởi hai loader khác nhau vẫn là hai kiểu khác nhau. Điều này giải thích nhiều lỗi ép kiểu hoặc liên kết lớp trong ứng dụng plugin, container và môi trường có nhiều loader.

## 2. Vì sao getClassLoader() có thể trả về null?

Nếu module được định nghĩa bởi **bootstrap class loader**, phương thức trả về **null**. Đây là giá trị hợp lệ, không có nghĩa module bị thiếu hoặc thao tác lấy loader thất bại.

Ví dụ điển hình là module **java.base**, nơi có lớp String:

    Module baseModule = String.class.getModule();

    System.out.println(baseModule.getName());        // java.base
    System.out.println(baseModule.getClassLoader()); // null

Bootstrap loader là loader nền tảng do JVM quản lý; ứng dụng không nhận được một đối tượng ClassLoader thông thường đại diện cho nó. Vì thế, không được gọi trực tiếp **loader.loadClass(...)** khi chưa xử lý trường hợp loader bằng null.

Một cách kiểm tra an toàn:

    Module module = Main.class.getModule();
    ClassLoader loader = module.getClassLoader();

    if (loader == null) {
        System.out.println("Module được nạp bởi bootstrap loader: "
                + module.getName());
    } else {
        System.out.println("Class loader: " + loader);
    }

Không nên thay thế kết quả null bằng **ClassLoader.getSystemClassLoader()** một cách máy móc. System class loader là một loader cụ thể của môi trường chạy; nó không phải đại diện chung cho mọi module và không nhất thiết là loader đã định nghĩa module đang xét.

## 3. Lấy loader không đồng nghĩa với quyền truy cập module

Đây là giới hạn quan trọng nhất khi làm việc với JPMS: **Module.getClassLoader() chỉ cho biết loader gắn với module; nó không cấp thêm quyền đọc module, truy cập package hoặc phản chiếu sâu.**

Quyền truy cập giữa các module vẫn tuân theo cấu hình module:

- **requires** khai báo quan hệ đọc giữa các module. Một module thường phải đọc module chứa kiểu mà nó sử dụng.
- **exports** công khai một package cho các module khác theo quy tắc truy cập của Java. Export không biến mọi thành phần private hoặc package-private thành API công khai.
- **opens** cho phép truy cập phản chiếu sâu vào package trong những điều kiện JPMS quy định. Đây là cơ chế thường cần khi framework dùng reflection để truy cập thành viên không public.

Ví dụ, nếu module A lấy được loader của module B, điều đó không tự động khiến A được phép sử dụng mọi lớp trong B. Cần kiểm tra đồng thời quan hệ đọc, package được export/open và các quy tắc truy cập Java thông thường.

Các API như **Module.canRead(...)**, **Module.isExported(...)** và **Module.isOpen(...)** giúp kiểm tra những khía cạnh này. Chúng trả lời các câu hỏi khác với **getClassLoader()**:

    Module source = Main.class.getModule();
    Module target = Service.class.getModule();

    boolean canRead = source.canRead(target);
    boolean exported = target.isExported("com.example.service",
                                         source);
    boolean opened = target.isOpen("com.example.service",
                                   source);

Kết quả cần được hiểu theo đúng loại quyền đang kiểm tra. Một package được export không đồng nghĩa package đó được open cho deep reflection.

## 4. Dùng loader để nạp lớp: cần hiểu phạm vi tìm kiếm

Khi loader khác null, có thể gọi **ClassLoader.loadClass(String)**:

    ClassLoader loader = Main.class.getModule().getClassLoader();
    Class<?> serviceType =
            loader.loadClass("com.example.service.Service");

Lệnh này yêu cầu loader tìm lớp theo tên nhị phân. Nó có thể ném **ClassNotFoundException** nếu không tìm thấy lớp. Kết quả phụ thuộc vào cách loader triển khai việc tìm lớp, quan hệ parent-child và các module mà loader định nghĩa.

Tuy nhiên, **loadClass(String) không phải API khẳng định rằng lớp trả về thuộc chính xác module mà bạn đang kiểm tra**. Một loader có thể định nghĩa nhiều module. Vì vậy, nếu yêu cầu là tìm một lớp trong một module cụ thể, hãy cân nhắc overload **Class.forName(Module, String)**:

    Module module = Main.class.getModule();
    Class<?> serviceType =
            Class.forName(module, "com.example.service.Service");

    if (serviceType == null) {
        System.out.println("Không tìm thấy lớp trong module đã chỉ định");
    }

API này có từ Java 9. Nó tìm lớp theo module được chỉ định và trả về **null** nếu lớp không được tìm thấy trong module đó. Phương thức này không khởi tạo lớp. Đây thường là lựa chọn rõ nghĩa hơn khi cần ràng buộc việc tra cứu vào một module cụ thể.

Không nhầm API trên với **Class.forName(String)**. Overload chỉ nhận tên lớp sử dụng cơ chế nạp lớp mặc định của nó, nên có thể tra cứu qua loader khác với loader của module mà bạn đang quan tâm.

## 5. Những giới hạn và khác biệt thường gặp của ClassLoader

### Cơ chế delegation

Nhiều class loader dùng mô hình parent delegation: trước tiên kiểm tra lớp đã được nạp, sau đó hỏi parent loader, rồi mới tự tìm lớp nếu cần. Đây là cách triển khai phổ biến, không phải cam kết rằng mọi loader tùy biến đều phải có cùng hành vi. Loader có thể ghi đè logic tìm lớp để phục vụ plugin, ứng dụng server hoặc môi trường chạy đặc thù.

Do đó, biết đối tượng loader không có nghĩa là biết đầy đủ thứ tự tìm lớp. Khi điều tra lỗi nạp lớp, cần xem cả loader cụ thể và cấu trúc parent của nó.

### Cùng tên lớp nhưng khác loader

Giả sử hai plugin cùng mang một lớp tên **com.example.api.Message**, nhưng mỗi plugin được nạp bởi một loader riêng. JVM có thể xem chúng là hai kiểu khác nhau. Khi truyền đối tượng giữa hai phía, ứng dụng có thể gặp **ClassCastException**, dù thông báo hiển thị cùng tên lớp.

Một số lỗi liên kết khác cũng có thể xuất hiện nếu các thành phần trong một kiểu dữ liệu được nạp từ những loader không tương thích. Cách xử lý thường là thống nhất nơi định nghĩa các API dùng chung, xác định ranh giới loader và tránh đóng gói nhiều bản sao của cùng API vào các vùng nạp lớp độc lập.

### Module layer có thể dùng chiến lược loader khác nhau

JPMS cho phép tạo module layer với các chiến lược loader khác nhau. Ví dụ, **ModuleLayer.defineModulesWithOneLoader(...)** có thể định nghĩa các module trong layer bằng một loader dùng chung; **ModuleLayer.defineModulesWithManyLoaders(...)** có thể dùng loader riêng cho từng module. Ứng dụng cũng có thể dùng loader tùy biến khi xây dựng layer.

Vì vậy, không nên dựa vào giả định rằng mỗi module có một loader riêng. Hãy xem cách layer được tạo và cách loader được cấu hình trong ứng dụng thực tế.

### Context class loader là một khái niệm khác

**Thread.currentThread().getContextClassLoader()** trả về context class loader của thread. Framework hoặc thư viện có thể dùng loader này để tìm lớp hoặc provider thay mặt cho mã đang chạy.

Context class loader có thể khác loader trả về từ **Module.getClassLoader()**. Chúng phục vụ các mục đích khác nhau: một bên gắn với module chứa lớp, bên kia là ngữ cảnh nạp lớp do thread mang theo. Không nên thay thế lẫn nhau nếu chưa hiểu thư viện đang sử dụng cơ chế nào.

## 6. Ví dụ tổng hợp

Ví dụ sau kiểm tra module và loader của một lớp ứng dụng:

    public class LoaderInfo {
        public static void printInfo(Class<?> anchor) {
            Module module = anchor.getModule();
            ClassLoader loader = module.getClassLoader();

            System.out.println("Module name: " + module.getName());

            if (loader == null) {
                System.out.println("Loader: bootstrap");
            } else {
                System.out.println("Loader: " + loader);
                System.out.println("Parent: " + loader.getParent());
            }
        }
    }

Có thể gọi phương thức với một lớp thuộc ứng dụng:

    LoaderInfo.printInfo(Main.class);

Nếu chạy trên classpath, lớp ứng dụng thường thuộc unnamed module. Nếu chạy trên module path, lớp có thể thuộc named module được khai báo trong **module-info.java**. Trong cả hai trường hợp, loader cụ thể phụ thuộc cấu hình runtime.

Để tra cứu một lớp thuộc đúng module, có thể dùng:

    Module module = Main.class.getModule();
    Class<?> result =
            Class.forName(module, "com.example.app.internal.Helper");

    if (result != null) {
        System.out.println("Found in module: " + result.getModule().getName());
    }

Ví dụ dùng tên nhị phân đầy đủ của lớp, bao gồm package. Nếu lớp không thuộc module được chỉ định, kết quả là null; việc lấy được loader của module không làm thay đổi điều kiện này.

## 7. Cách chọn API phù hợp

| Nhu cầu | API nên xem xét | Lưu ý |
|---|---|---|
| Xác định module của một lớp | **Class.getModule()** | Trả về Module chứa lớp đó |
| Lấy loader gắn với module | **Module.getClassLoader()** | Có thể trả về null với bootstrap loader |
| Nạp lớp qua một loader đã biết | **ClassLoader.loadClass(String)** | Tìm theo logic của loader; không ràng buộc duy nhất vào một module |
| Tra cứu lớp trong module xác định | **Class.forName(Module, String)** | Trả về null nếu lớp không nằm trong module đó; không khởi tạo lớp |
| Kiểm tra module có đọc module khác | **Module.canRead(Module)** | Không thay thế kiểm tra truy cập package |
| Kiểm tra package được công khai | **Module.isExported(...)** | Phục vụ quyền truy cập theo exports |
| Kiểm tra package mở cho reflection | **Module.isOpen(...)** | Liên quan đến deep reflection |
| Lấy loader theo ngữ cảnh thread | **Thread.getContextClassLoader()** | Có thể khác loader gắn với module |

## 8. Ghi nhớ

- Lấy module từ một lớp bằng **Class.getModule()**, sau đó mới gọi **Module.getClassLoader()**.
- Luôn xử lý trường hợp kết quả loader là null; đây là trường hợp hợp lệ của bootstrap loader.
- Một loader có thể định nghĩa nhiều module, nên loader không đại diện duy nhất cho module.
- **ClassLoader.loadClass(...)** tìm lớp theo logic của loader; nó không tự cấp quyền truy cập module và không bảo đảm lớp thuộc module đang xét.
- Dùng **Class.forName(Module, String)** khi cần tra cứu lớp trong đúng module đã chỉ định.
- Khi gặp lỗi truy cập, kiểm tra **requires**, **exports**, **opens** và quy tắc truy cập Java; đổi hoặc lấy loader không tự giải quyết các giới hạn này.
- Khi gặp lỗi ép kiểu hoặc liên kết, kiểm tra xem các lớp có bị nạp từ những loader khác nhau hay không.
- Phân biệt loader của module với context class loader của thread.

**Module.getClassLoader() là API để nhận diện loader gắn với một module.** Muốn nạp lớp đúng phạm vi và truy cập được lớp đó, vẫn phải xét cách loader tìm lớp cùng với các quy tắc của Java Module System.