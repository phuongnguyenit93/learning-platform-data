# Duyệt Iterator và thời điểm provider được nạp, khởi tạo theo nhu cầu

## 1. Vấn đề cần hiểu

Trong hệ thống Java hỗ trợ plugin, \`ServiceLoader<S>\` là công cụ khám phá provider của một service type \`S\` mà không yêu cầu ứng dụng liệt kê các implementation khi biên dịch. Điểm quan trọng là **tạo \`ServiceLoader\` không đồng nghĩa với tạo tất cả provider**. \`ServiceLoader\` thực hiện khám phá và tạo provider theo nhu cầu khi chương trình duyệt iterator hoặc stream của nó.

Cần phân biệt bốn sự kiện:

1. **Tạo loader:** gọi \`ServiceLoader.load(S.class)\` hoặc overload nhận classloader.
2. **Khám phá metadata:** đọc thông tin provider từ \`META-INF/services/<service-binary-name>\` trên classpath hoặc từ module descriptors thích hợp trên module path.
3. **Nạp và liên kết class:** JVM cần truy cập/kiểm tra class provider khi tiến hành khám phá hoặc khởi tạo; chính xác thời điểm JVM load/link/initialize từng class không nên suy luận từ việc chỉ tạo loader.
4. **Tạo đối tượng provider:** constructor hoặc provider factory được gọi khi iterator phải cung cấp một instance mới. Đối với stream, đọc \`Provider.type()\` và gọi \`Provider.get()\` là hai thao tác khác nhau.

Nhầm lẫn giữa các bước này dễ dẫn đến việc cho rằng mọi plugin đã sẵn sàng chỉ vì có một \`ServiceLoader\`, hoặc cho rằng một lần \`hasNext()\` luôn tạo instance. Hành vi phải được xét theo API cụ thể.

## 2. Ví dụ chạy được với Java 17+: quan sát \`Iterator\`

Ví dụ gồm một interface, hai provider, tệp đăng ký SPI và một class chạy. Hai provider in thông báo trong static initializer và constructor để quan sát thời điểm tương ứng.

Cấu trúc:

\`\`\`text
example/
├── src/
│   ├── demo/spi/Greeter.java
│   ├── demo/plugins/EnglishGreeter.java
│   ├── demo/plugins/VietnameseGreeter.java
│   └── demo/Main.java
└── resources/
    └── META-INF/services/demo.spi.Greeter
\`\`\`

\`src/demo/spi/Greeter.java\`:

\`\`\`java
package demo.spi;

public interface Greeter {
    String greet();
}
\`\`\`

\`src/demo/plugins/EnglishGreeter.java\`:

\`\`\`java
package demo.plugins;

import demo.spi.Greeter;

public final class EnglishGreeter implements Greeter {
    static {
        System.out.println("English: static initializer");
    }

    public EnglishGreeter() {
        System.out.println("English: constructor");
    }

    @Override
    public String greet() {
        return "Hello";
    }
}
\`\`\`

\`src/demo/plugins/VietnameseGreeter.java\`:

\`\`\`java
package demo.plugins;

import demo.spi.Greeter;

public final class VietnameseGreeter implements Greeter {
    static {
        System.out.println("Vietnamese: static initializer");
    }

    public VietnameseGreeter() {
        System.out.println("Vietnamese: constructor");
    }

    @Override
    public String greet() {
        return "Xin chào";
    }
}
\`\`\`

\`resources/META-INF/services/demo.spi.Greeter\`:

\`\`\`text
demo.plugins.EnglishGreeter
demo.plugins.VietnameseGreeter
\`\`\`

\`src/demo/Main.java\`:

\`\`\`java
package demo;

import demo.spi.Greeter;
import java.util.Iterator;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        System.out.println("1. Before load");
        ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);
        System.out.println("2. Loader created");

        Iterator<Greeter> iterator = loader.iterator();
        System.out.println("3. Iterator created");

        System.out.println("4. hasNext=" + iterator.hasNext());
        System.out.println("5. Calling next");
        Greeter first = iterator.next();
        System.out.println("6. First result=" + first.greet());

        System.out.println("7. hasNext=" + iterator.hasNext());
        System.out.println("8. Calling next");
        Greeter second = iterator.next();
        System.out.println("9. Second result=" + second.greet());
    }
}
\`\`\`

Tại thư mục \`example\`, chạy trên shell có lệnh \`cp\` và \`find\` (ví dụ bash):

\`\`\`bash
mkdir -p out
javac -d out src/demo/spi/Greeter.java src/demo/plugins/EnglishGreeter.java src/demo/plugins/VietnameseGreeter.java src/demo/Main.java
cp -R resources/. out/
java -cp out demo.Main
\`\`\`

Một output điển hình với chính hai provider và thứ tự khai báo ở ví dụ:

\`\`\`text
1. Before load
2. Loader created
3. Iterator created
4. hasNext=true
5. Calling next
English: static initializer
English: constructor
6. First result=Hello
7. hasNext=true
8. Calling next
Vietnamese: static initializer
Vietnamese: constructor
9. Second result=Xin chào
\`\`\`

Quan sát:

- Không có constructor nào được gọi tại \`ServiceLoader.load(...)\` hoặc \`loader.iterator()\`.
- \`hasNext()\` trả lời liệu còn provider có thể được lấy ra; với ví dụ classpath đơn giản này, nó không gọi constructor.
- Mỗi lần \`next()\` cần một provider mới, provider tương ứng được tạo và đưa vào cache.
- Static initializer xuất hiện trước constructor khi class được khởi tạo bởi JVM. Đó là hệ quả của việc tạo instance; không phải cam kết mọi thao tác \`hasNext()\` sẽ không bao giờ có hoạt động load/link class.

**Giới hạn của phép quan sát:** ví dụ chạy trên classpath, service configuration hợp lệ, không dùng provider factory của named module, không có provider nào đã bị tạo trước đó. Trên JPMS, stream và kiểm tra metadata có thể tạo ra thứ tự hoạt động khác, nhưng vẫn phải tuân theo hợp đồng công khai của \`ServiceLoader\`.

## 3. \`hasNext()\`, \`next()\` và sự khác nhau giữa khám phá với khởi tạo

\`ServiceLoader.iterator()\` trả iterator dùng cơ chế khám phá và cache nội bộ. Các thao tác có vai trò khác nhau:

| Thao tác | Ý nghĩa | Có bảo đảm tạo provider mới? |
| --- | --- | --- |
| \`ServiceLoader.load(S.class)\` | Tạo loader phục vụ khám phá | Không |
| \`loader.iterator()\` | Lấy iterator duyệt provider | Không |
| \`iterator.hasNext()\` | Kiểm tra có phần tử kế tiếp; có thể cần đọc/kiểm tra metadata | Không |
| \`iterator.next()\` | Lấy instance provider kế tiếp | Có thể: tạo mới nếu chưa được cache; không nếu trả instance đã cache |
| \`loader.reload()\` | Xóa cache provider của loader để khám phá lại | Không tự tạo provider |
| \`loader.stream()\` | Tạo stream các đối tượng \`Provider<S>\` | Không trực tiếp tạo mọi provider |
| \`Provider.type()\` | Cho biết class/type của provider theo API stream | Không yêu cầu một instance provider |
| \`Provider.get()\` | Yêu cầu một provider instance | Có thể tạo instance; mỗi lần gọi có thể tạo instance mới |

**Không đồng nhất \`hasNext()\` với \`next()\`.** Việc biết metadata của một provider chưa chứng minh provider đó khởi tạo thành công. Chẳng hạn, file đăng ký tham chiếu tên không tồn tại hoặc provider có constructor ném exception: lỗi có thể chỉ lộ ra trong quá trình khám phá hoặc khi yêu cầu instance. Không nên dựa vào một loại exception/điểm phát sinh cố định; tùy lỗi, \`ServiceConfigurationError\` có thể xuất hiện ở các bước duyệt khác nhau.

Nếu mục đích là kiểm tra mọi provider có dùng được hay không, phải **duyệt và sử dụng thực sự** từng instance thay vì chỉ tạo loader hay nhìn thấy tệp đăng ký.

## 4. Cache của \`ServiceLoader\` ảnh hưởng đến tính lazy như thế nào?

Một \`ServiceLoader\` lưu cache các provider instance đã được tạo qua iterator. Các lần duyệt sau có thể lấy lại instance từ cache trước khi tìm/khởi tạo provider còn lại.

Ví dụ sau tiếp tục dùng \`loader\` đã tạo ở phần trước:

\`\`\`java
for (Greeter greeter : loader) {
    System.out.println(greeter.greet());
}
\`\`\`

Vì hai provider đã được tạo trong lần duyệt trước, lần duyệt lại có thể sử dụng hai instance đã cache mà **không gọi constructor thêm lần nữa**.

Có hai hệ quả:

- Lazy initialization là đặc tính của **mỗi loader và trạng thái cache**. Câu “\`next()\` luôn gọi constructor” sai nếu phần tử đó đã ở trong cache.
- Cache của \`ServiceLoader\` không đồng nghĩa với singleton toàn ứng dụng. Tạo \`ServiceLoader\` khác hoặc gọi \`Provider.get()\` qua stream có thể dẫn tới instance khác, tùy provider và kiểu triển khai.

Mô hình suy nghĩ phù hợp:

\`\`\`text
ServiceLoader được tạo
      |
iterator() / stream()
      |
phát hiện thông tin provider khi cần
      |
yêu cầu provider instance
      |
đã cache? ---- Có ----> trả instance trong cache (iterator)
      |
     Không
      |
xác minh/khởi tạo provider
      |
lưu cache (iterator)
      |
trả instance
\`\`\`

Sơ đồ là mô hình khái niệm cho iterator. Không dùng nó để suy diễn rằng \`stream().map(Provider::get)\` nhất thiết có cùng chính sách cache instance như \`iterator()\`.

## 5. Iterator duyệt dở và tác dụng của \`reload()\`

Giả sử một plugin directory được thay đổi sau khi tạo loader, hoặc code gọi:

\`\`\`java
loader.reload();
\`\`\`

\`reload()\` xóa cache hiện có. Iterator hoặc stream đã lấy ra trước lần \`reload()\` có thể trở nên không hợp lệ; với API này, việc sử dụng iterator cũ sau reload có thể gây \`ConcurrentModificationException\`. Hãy lấy iterator/stream mới từ loader sau reload.

Ví dụ độc lập trong method:

\`\`\`java
ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);
Iterator<Greeter> oldIterator = loader.iterator();
loader.reload();

Iterator<Greeter> freshIterator = loader.iterator();
while (freshIterator.hasNext()) {
    Greeter greeter = freshIterator.next();
    System.out.println(greeter.greet());
}
\`\`\`

**Quan trọng:** \`reload()\` không tự thêm JAR vào classpath/classloader, không chữa descriptor sai và không tự dỡ class đã nạp khỏi JVM. Nó chỉ làm loader bỏ cache để việc khám phá lại được tiến hành khi duyệt tiếp. Nếu classloader không nhìn thấy JAR mới, reload vẫn không giúp tìm được plugin đó. Với hệ thống hỗ trợ hot deployment, cần phối hợp quản lý loader, file JAR và vòng đời instance của plugin.

## 6. \`stream()\` cung cấp mức lazy khác với \`iterator()\`

Từ Java 9, \`ServiceLoader.stream()\` trả một stream các \`ServiceLoader.Provider<S>\`. Mỗi \`Provider\` cung cấp:

- \`type()\`: thông tin type của provider để lọc theo annotation hoặc metadata trên class.
- \`get()\`: lấy provider instance; việc gọi \`get()\` có thể dẫn tới tạo mới và chạy initialization.

Ví dụ lọc theo tên class trước khi tạo instance:

\`\`\`java
ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);
loader.stream()
    .filter(provider -> provider.type().getSimpleName().equals("EnglishGreeter"))
    .map(ServiceLoader.Provider::get)
    .forEach(greeter -> System.out.println(greeter.greet()));
\`\`\`

Kết quả với các provider của ví dụ và một loader mới:

\`\`\`text
English: static initializer
English: constructor
Hello
\`\`\`

Ví dụ trên là **đoạn code trong method có import \`Greeter\`, \`ServiceLoader\`**. Đặt trong ứng dụng mẫu và chạy cùng classpath trước đó để xem kết quả. Provider không vượt qua filter không bị gọi \`get()\`; tuy nhiên thao tác \`type()\` có thể khiến JVM load/link class hoặc thực hiện xác minh metadata. Vì thế \`type()\` không có nghĩa là “không động đến class” mà là “không yêu cầu tạo instance provider”.

Trong named module, provider có thể được khai báo bằng \`provides ... with ...\` và có provider method. Khi đó type do \`Provider.type()\` cung cấp có thể là return type của provider method, không nhất thiết là class factory được ghi trong module descriptor. Không giả định tương đồng tuyệt đối với provider class trên classpath.

**Khi chọn API nào?**

- Dùng \`iterator()\` hoặc enhanced \`for\` nếu muốn lấy instance tuần tự và sử dụng ngay.
- Dùng \`stream()\` nếu muốn sàng lọc qua metadata/type trước khi gọi \`Provider.get()\`, hoặc tổ chức pipeline khám phá provider có điều kiện.
- Không dùng \`ServiceLoader\` như một công cụ sandbox, policy enforcement hoặc bảo đảm performance; plugin code có thể thực thi khi provider được khởi tạo.

## 7. Lỗi và quan sát runtime

### Lỗi cấu hình khác lỗi khởi tạo

Một số lỗi có thể được bọc trong \`ServiceConfigurationError\`, ví dụ:

- Descriptor \`META-INF/services/\` sai định dạng hoặc trỏ đến class không có.
- Provider không tương thích với service type.
- Provider không đáp ứng yêu cầu tạo instance, hoặc constructor/provider method gây lỗi.
- Không thể truy cập provider do vấn đề module accessibility hoặc classloader.

Không nên bắt rộng rồi bỏ qua mọi lỗi:

\`\`\`java
try {
    for (Greeter greeter : ServiceLoader.load(Greeter.class)) {
        System.out.println(greeter.greet());
    }
} catch (java.util.ServiceConfigurationError error) {
    throw new IllegalStateException("Invalid plugin deployment", error);
}
\`\`\`

Đây là đoạn dùng trong method. Nó giữ nguyên nguyên nhân để vận hành tìm được provider lỗi. Với hệ thống có cơ chế cô lập plugin cụ thể, có thể quyết định tiếp tục sau khi ghi log lỗi, nhưng cần xử lý rõ ràng theo yêu cầu sản phẩm; không nên nuốt lỗi mặc định.

### Instrumentation nên đo đúng điều gì?

Khi benchmark hay debug lazy loading:

1. Đặt điểm đo ngay trước/sau \`ServiceLoader.load\`, \`iterator()\`, \`hasNext()\`, \`next()\`, \`Provider.type()\` và \`Provider.get()\`.
2. Ghi nhận thời điểm gọi constructor, static initialization, đọc tài nguyên, kết nối ngoài hoặc đọc file config.
3. Chạy lần đầu và lần lặp lại để so sánh trạng thái cache/JIT/warmup; không cộng gộp hai kết quả.
4. Nếu muốn kiểm tra tính lazy, dùng provider có hiệu ứng quan sát được ở constructor, đồng thời xác nhận phương thức nạp chưa được gọi trước lúc đo.
5. Chạy bằng artifact và classloader phân phối thật; classpath của IDE có thể che giấu thiếu metadata.

Không suy ra tốc độ từ khái niệm “lazy”: khởi tạo trễ giúp tránh trả chi phí trước khi cần, nhưng có thể đưa độ trễ vào request đầu tiên. Cần đo trong tải thực tế.

## 8. Một vài tình huống thiết kế

### Trì hoãn plugin đắt đỏ

Nếu plugin khởi tạo client kết nối hoặc đọc cấu hình lớn trong constructor, iterator cho phép chỉ tạo provider khi thực sự duyệt đến nó. Tuy nhiên **gọi \`for (Greeter g : loader)\` đến hết danh sách sẽ tạo toàn bộ provider**, nên không đạt mục tiêu chỉ dùng một plugin. Có thể dùng stream để lọc qua type trước khi gọi \`get()\`, hoặc thiết kế registry metadata riêng nếu lựa chọn dựa trên ID chỉ có thể biết qua instance.

### Provider không thread-safe

\`ServiceLoader\` **không an toàn để dùng đồng thời bởi nhiều thread**. Không chia sẻ một instance loader rồi gọi các thao tác duyệt/reload từ nhiều thread mà không có chiến lược đồng bộ phù hợp. Cache provider cũng không tự bảo đảm implementation thread-safe: phải quản lý vòng đời và truy cập provider theo hợp đồng riêng.

### Plugin cập nhật khi ứng dụng chạy

Nếu plugin archive thay đổi trên đĩa, classloader cũ có thể vẫn giữ class đã nạp; \`reload()\` không bảo đảm đọc bytecode mới. Để thay phiên bản, thường cần tạo classloader/module layer mới phù hợp, chuyển reference và dọn vòng đời loader cũ. Cần kiểm soát shutdown resource của provider để tránh rò rỉ thread, file handle hoặc classloader.

## 9. Checklist để sử dụng \`ServiceLoader\` đúng

- [ ] Xác minh tên service type, descriptor \`META-INF/services\` hoặc \`module-info.java\`.
- [ ] Duyệt bằng iterator khi cần instance; dùng stream khi cần lọc thông tin provider trước \`get()\`.
- [ ] Phân biệt đọc metadata, load/link class, class initialization và tạo provider instance.
- [ ] Hiểu \`hasNext()\` không chứng minh provider khởi tạo thành công; \`next()\` có thể dùng cache.
- [ ] Không giả định gọi \`load(...)\` tạo sẵn tất cả plugin.
- [ ] Nếu gọi \`reload()\`, tạo iterator/stream mới và quản lý việc thay classloader riêng.
- [ ] Test thời điểm khởi tạo bằng output/side effects có kiểm soát, không dựa vào suy đoán.
- [ ] Kiểm tra plugin thực trên artifact phát hành và đúng runtime classloader.
- [ ] Xử lý \`ServiceConfigurationError\` có logging/cause và chính sách lỗi rõ ràng.

**Điểm cốt lõi:** \`ServiceLoader\` cho phép phát hiện và khởi tạo provider theo nhu cầu; iterator là nơi một provider có thể được yêu cầu tạo instance, còn cache có thể làm lần duyệt sau trả lại instance đã tạo. Muốn chỉ tạo plugin được chọn, hãy phân biệt duyệt metadata bằng \`stream()\` và gọi \`Provider.get()\`, đồng thời kiểm chứng thời điểm khởi tạo trong môi trường chạy thật.
