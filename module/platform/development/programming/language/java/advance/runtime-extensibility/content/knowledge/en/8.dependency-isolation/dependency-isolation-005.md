# Chẩn đoán ClassCastException dù hai lớp có cùng tên

## 1. Triệu chứng: tên giống nhau nhưng JVM vẫn từ chối ép kiểu

Trong một ứng dụng Java có plugin, hai lớp có thể cùng tên đầy đủ, cùng mã nguồn và thậm chí cùng bytecode, nhưng JVM vẫn xem là **hai kiểu khác nhau**. Nguyên nhân thường là chúng được **định nghĩa bởi hai class loader khác nhau**.

Một ngoại lệ điển hình:

\`\`\`text
java.lang.ClassCastException:
  class com.example.api.Message cannot be cast to class com.example.api.Message
  (com.example.api.Message is in unnamed module of loader 'plugin-loader' @...;
   com.example.api.Message is in unnamed module of loader 'app'...)
\`\`\`

Thoạt nhìn, \`Message\` đang được ép thành chính \`Message\`. Nhưng trong JVM, **class identity** được xác định bởi cặp:

\`\`\`text
(tên nhị phân của lớp, class loader định nghĩa lớp)
\`\`\`

Do đó:

\`\`\`text
(com.example.api.Message, HostClassLoader)
    !=
(com.example.api.Message, PluginClassLoader)
\`\`\`

Tên lớp giống nhau không đủ để ép kiểu thành công. Đây là vấn đề phổ biến khi host và plugin đóng gói bản sao của cùng thư viện API, hoặc khi hệ thống tạo class loader riêng theo plugin, module, deployment hoặc lần hot reload.

## 2. Loading class và defining class khác nhau thế nào?

Một class loader có thể **nhận yêu cầu nạp lớp** thông qua \`loadClass(name)\`, rồi ủy quyền cho class loader cha. Loader được gọi không nhất thiết là loader **định nghĩa** lớp.

- **Initiating loader:** loader mà qua đó quá trình nạp lớp được yêu cầu hoặc khởi tạo.
- **Defining loader:** loader thực sự gọi cơ chế định nghĩa class từ bytecode. \`Class.getClassLoader()\` cho biết defining loader của lớp đó (với bootstrap class loader thường trả \`null\`).
- **Parent delegation:** \`ClassLoader.loadClass\` mặc định ưu tiên lớp đã nạp, sau đó hỏi parent trước khi tự \`findClass\`. Đây là cơ chế giúp host và plugin chia sẻ API nếu triển khai đúng.

Giả sử host có \`com.example.api.Plugin\` trong classpath chính, plugin cũng đóng gói bản sao \`com.example.api.Plugin\` trong JAR riêng. Nếu loader plugin theo quy tắc child-first cho package API, nó có thể định nghĩa một \`Plugin\` khác. Khi host ép instance plugin sang \`com.example.api.Plugin\` mà host biết, phép ép kiểu thất bại, dù tên interface trong hai phía hoàn toàn giống nhau.

**Lưu ý:** tên cùng package không tạo ra quan hệ kiểu. JVM vẫn kiểm tra identity của class/interface, cấu trúc kế thừa và các quy tắc liên kết.

## 3. Mô hình nguyên nhân trong hệ plugin

\`\`\`text
                     Host application
                           |
                    AppClassLoader
                           |
             com.example.api.Plugin (A)
                           |
                         cast
                           |
                 Plugin implementation
                           |
                 PluginClassLoader
                           |
             com.example.api.Plugin (B)
\`\`\`

Nếu \`PluginClassLoader\` tự định nghĩa \`Plugin (B)\`, instance triển khai B không nhất thiết là instance của A. Chúng cùng chuỗi tên \`com.example.api.Plugin\`, nhưng không phải cùng đối tượng \`Class<?>\`.

Các nguyên nhân thường gặp:

1. **API JAR bị đóng gói hai lần:** cùng interface tồn tại trong host và trong JAR plugin, và mỗi bên được nạp bởi loader riêng.
2. **Child-first không chọn lọc:** plugin loader ưu tiên nạp mọi package từ plugin, kể cả package hợp đồng chung.
3. **Hai phiên bản dependency:** hai loader nạp thư viện cùng tên lớp nhưng khác phiên bản; ngoài \`ClassCastException\` còn có thể phát sinh \`NoSuchMethodError\`, \`AbstractMethodError\` hoặc \`LinkageError\` tùy tình huống.
4. **Hot reload:** loader mới định nghĩa lại cùng tên lớp; object còn sống từ loader cũ không tương thích với kiểu của loader mới.
5. **Container hoặc framework:** application server, OSGi, test runner hoặc môi trường module có ranh giới loader riêng.
6. **Serialization/caching:** object được lưu trong cache hoặc session từ deployment/loader cũ rồi chuyển qua API của loader mới.

Không phải mọi lỗi \`ClassCastException\` đều do class loader; cũng có trường hợp cast sai hoàn toàn giữa hai kiểu vốn không liên quan. Phải kiểm tra cả tên lớp **và defining loader**.

## 4. Chẩn đoán có hệ thống

### Bước 1: Đọc chính xác hai phía của lỗi

Từ stack trace, xác định:

- Kiểu thực tế của object tại runtime.
- Kiểu đích mà đoạn code muốn ép.
- Vị trí dòng code thực hiện cast hoặc vị trí bridge/proxy/framework gây cast.
- Thông tin module và loader nếu JVM cung cấp.

Ví dụ:

\`\`\`java
Plugin plugin = (Plugin) instance;
\`\`\`

Nếu lỗi xuất hiện tại đây, hai class \`Plugin\` có thể khác identity dù cùng tên. Ngược lại, nếu lỗi là \`Foo cannot be cast to Bar\`, hãy kiểm tra quan hệ \`extends\`/\`implements\` trước khi kết luận do duplicate class.

### Bước 2: Ghi class identity và defining loader

Đoạn chẩn đoán sau dùng được trong chương trình có \`Object instance\` và \`Class<?> apiType\`:

\`\`\`java
// Đoạn tích hợp, không phải chương trình độc lập.
Class<?> actual = instance.getClass();

System.out.println("actual = " + actual.getName());
System.out.println("actual loader = " + actual.getClassLoader());
System.out.println("expected = " + apiType.getName());
System.out.println("expected loader = " + apiType.getClassLoader());
System.out.println("same Class object = " + (actual == apiType));
System.out.println("assignable = " + apiType.isAssignableFrom(actual));
System.out.println("instanceof expected = " + apiType.isInstance(instance));
\`\`\`

Hai điểm quan trọng:

- \`actual == apiType\` chỉ kiểm tra có đúng **cùng một lớp** hay không. Đối với implementation và interface khác tên, phép so sánh này đương nhiên là \`false\`; khi đó hãy dùng \`isAssignableFrom\` hoặc \`isInstance\`.
- \`ClassLoader.toString()\` có thể được tùy chỉnh và không phải định danh bảo mật duy nhất. Khi cần điều tra sâu, ghi cả \`System.identityHashCode(loader)\` và quan hệ parent, nhưng hash cũng không phải ID toàn cục không trùng.

### Bước 3: Kiểm tra nguồn bytecode

Với class đã nạp, có thể lấy nơi cung cấp code khi metadata cho phép:

\`\`\`java
// Đoạn tích hợp, không phải chương trình độc lập.
java.security.ProtectionDomain domain = actual.getProtectionDomain();
java.security.CodeSource source = domain == null ? null : domain.getCodeSource();
System.out.println(source == null ? "<unknown>" : source.getLocation());
\`\`\`

\`CodeSource\` có thể là \`null\`; URL được trả về không luôn là đường dẫn JAR nguyên gốc. Với \`ClassLoader\` tự định nghĩa, thông tin có thể không đầy đủ. Ngoài ra, \`Class.getResource\` và các resource lookup khác chịu ảnh hưởng của chính sách loader.

### Bước 4: Xác minh dependency và package trùng

Xem cách plugin được đóng gói:

\`\`\`bash
jar --list --file plugin.jar
\`\`\`

Tìm dấu hiệu như \`com/example/api/Plugin.class\` xuất hiện trong cả host API JAR và plugin JAR. Kiểm tra build configuration (Gradle/Maven) có vô tình đưa API chung vào fat JAR hoặc shaded artifact hay không. Nếu plugin cần API do host cung cấp, thường phải khai báo dependency này ở chế độ compile-only/provided phù hợp quy trình đóng gói.

Lưu ý: chỉ có bản sao class trong hai JAR **chưa đủ** kết luận lỗi sẽ xảy ra; nếu plugin loader delegate về parent cho package API, cả hai phía vẫn có thể dùng cùng \`Class\`.

### Bước 5: Kiểm tra đường tải lớp

Có thể dùng JVM logging hỗ trợ phân tích nguồn load:

\`\`\`bash
java -Xlog:class+load=info -jar host.jar
\`\`\`

Tùy môi trường và phiên bản JVM, log có thể cho biết tên lớp, nguồn class và loader liên quan. Tăng mức log có chọn lọc khi cần, tránh ghi dữ liệu quá lớn trong production. Kết hợp với log định danh class loader mà ứng dụng tự xuất ra để tìm chỗ split identity.

## 5. Ví dụ Java 17+ tái hiện lỗi có cùng tên lớp

Ví dụ tạo cùng một tên lớp \`example.Shared\` bằng bytecode giống nhau, rồi định nghĩa hai lần trong hai loader khác nhau. Nó không yêu cầu tải JAR bên ngoài và minh họa trực tiếp bản chất class identity.

Tạo file **\`ClassLoaderIdentityDemo.java\`**:

\`\`\`java
import java.io.IOException;
import java.io.InputStream;

public class ClassLoaderIdentityDemo {
    public static class Shared {
        public String value() {
            return "hello";
        }
    }

    static final class IsolatedLoader extends ClassLoader {
        private final String target;

        IsolatedLoader(String target) {
            super(ClassLoaderIdentityDemo.class.getClassLoader());
            this.target = target;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            synchronized (getClassLoadingLock(name)) {
                Class<?> loaded = findLoadedClass(name);
                if (loaded == null) {
                    if (name.equals(target)) {
                        loaded = findClass(name);
                    } else {
                        loaded = super.loadClass(name, false);
                    }
                }
                if (resolve) {
                    resolveClass(loaded);
                }
                return loaded;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!name.equals(target)) {
                throw new ClassNotFoundException(name);
            }

            String resource = name.replace('.', '/') + ".class";
            try (InputStream in =
                    ClassLoaderIdentityDemo.class.getClassLoader()
                        .getResourceAsStream(resource)) {
                if (in == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = in.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException e) {
                throw new ClassNotFoundException(name, e);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        String name = Shared.class.getName();
        ClassLoader isolated = new IsolatedLoader(name);

        Class<?> another = isolated.loadClass(name);
        Object pluginValue = another.getDeclaredConstructor().newInstance();

        System.out.println("same name: " +
            Shared.class.getName().equals(another.getName()));
        System.out.println("same class: " + (Shared.class == another));
        System.out.println("assignable: " +
            Shared.class.isAssignableFrom(another));
        System.out.println("host loader == plugin loader: " +
            (Shared.class.getClassLoader() == another.getClassLoader()));

        try {
            Shared value = (Shared) pluginValue;
            System.out.println(value.value());
        } catch (ClassCastException e) {
            System.out.println("cast failed: ClassCastException");
        }
    }
}
\`\`\`

Biên dịch và chạy:

\`\`\`bash
javac ClassLoaderIdentityDemo.java
java ClassLoaderIdentityDemo
\`\`\`

Kết quả:

\`\`\`text
same name: true
same class: false
assignable: false
host loader == plugin loader: false
cast failed: ClassCastException
\`\`\`

Tại sao lỗi xảy ra?

1. \`Shared.class\` của host được định nghĩa bởi application class loader.
2. \`IsolatedLoader\` chỉ xử lý đặc biệt tên lớp lồng \`ClassLoaderIdentityDemo$Shared\`; khi có yêu cầu nạp đúng tên đó, nó đọc resource \`.class\` và tự gọi \`defineClass\`.
3. JVM thấy hai định nghĩa có cùng tên nhị phân nhưng defining loader khác nhau, do đó tạo hai đối tượng \`Class\` khác identity.
4. \`pluginValue\` là instance của lớp do \`IsolatedLoader\` định nghĩa, nên không thể ép sang \`Shared\` do host loader định nghĩa.

Đây là ví dụ chủ động **child-first cho đúng một lớp** để tái hiện lỗi. Nó không phải kiến trúc class loader khuyến nghị cho môi trường production.

## 6. Cách sửa: chia sẻ API, cô lập implementation

Nguyên tắc thường dùng trong plugin system:

**API chung do loader ổn định của host định nghĩa; implementation và dependency riêng do loader plugin định nghĩa.**

\`\`\`text
              Bootstrap / Platform
                       |
                Host API loader
                 |           |
          PluginLoader A  PluginLoader B
          impl + lib A    impl + lib B
\`\`\`

Cả hai loader plugin **delegate về parent** đối với package API chung như \`com.example.plugin.api.*\`. Nhờ vậy, \`Plugin\`, \`Context\`, các DTO và exception trong hợp đồng được định nghĩa một lần; host có thể cast implementation sang interface của host.

Các giải pháp thực tế:

- **Loại bỏ API duplicate** khỏi JAR plugin nếu build system đã cung cấp API từ host.
- **Thiết lập delegation theo package:** parent-first với \`java.*\`, API dùng chung và thư viện cần chia sẻ; chỉ cô lập implementation/dependency đã xác định.
- **Version hóa API rõ ràng:** không trộn plugin biên dịch theo API v1 với host API v2 khi không tương thích nhị phân.
- **Không đưa object nội bộ của plugin qua ranh giới API** trừ khi kiểu đó thuộc shared contract hoặc được chuyển sang DTO thuần đã thống nhất.
- **Hot reload:** chuyển request mới sang loader mới; tránh dùng trực tiếp object/proxy còn sống từ loader cũ; đóng tài nguyên khi không còn tham chiếu.
- **Công cụ packaging:** kiểm tra nội dung artifact để ngăn việc nhúng nhầm \`com.example.plugin.api\` từ fat JAR/shading.

Ví dụ Gradle (chỉ minh họa cấu hình cho một module plugin):

\`\`\`groovy
dependencies {
    compileOnly project(':plugin-api')
    // Các thư viện thật sự cần đóng gói riêng phải được xem xét theo runtime.
}
\`\`\`

\`compileOnly\` cho phép biên dịch nhưng không tự đưa dependency vào runtime classpath của module plugin. Host/loader triển khai phải cung cấp API chung đúng phiên bản khi chạy. Cấu hình này không tự giải quyết mọi xung đột dependency.

**Không áp dụng child-first cho toàn bộ classpath một cách mù quáng.** Nếu cả API chung bị định nghĩa lại, lớp plugin có thể không còn implement interface mà host đang kiểm tra.

## 7. Khi hai loader dùng cùng thư viện nhưng cần cách ly phiên bản

Đôi khi cô lập dependency là mục tiêu đúng: plugin A dùng \`lib-x\` v1, plugin B dùng \`lib-x\` v2. Có thể nạp các phiên bản vào loader khác nhau, miễn là API trao đổi giữa plugin và host **không làm lộ kiểu của lib-x**.

Ví dụ hợp đồng tốt:

\`\`\`java
// Shared API - ý tưởng minh họa, không phải chương trình độc lập.
public interface TextExtractor {
    String extract(byte[] documentBytes);
}
\`\`\`

Host và plugin chỉ trao đổi \`String\` và \`byte[]\` (các kiểu JDK được bootstrap/platform/host chia sẻ trong cách nạp thông thường). Plugin có thể dùng parser version khác trong implementation.

Hợp đồng dễ gây xung đột:

\`\`\`java
// Không nên dùng nếu Document thuộc thư viện riêng trong loader plugin.
public interface TextExtractor {
    third.party.Document extract(byte[] documentBytes);
}
\`\`\`

Khi \`third.party.Document\` được định nghĩa riêng ở nhiều loader, chữ ký phương thức, linker và cast có thể gặp vấn đề. Tách ranh giới bằng DTO chung, dữ liệu primitive/JDK, JSON/protobuf được xử lý theo hợp đồng, hoặc thậm chí ranh giới tiến trình nếu cần.

## 8. Những lỗi liên quan cần phân biệt

| Hiện tượng | Hướng chẩn đoán |
|---|---|
| \`ClassCastException\` với hai tên giống nhau | Kiểm tra defining loader của cả hai lớp |
| \`ClassNotFoundException\` | Loader không tìm thấy tên được yêu cầu |
| \`NoClassDefFoundError\` | JVM không thể định nghĩa/liên kết lớp phụ thuộc hoặc lớp đã lỗi khởi tạo |
| \`NoSuchMethodError\` | Mã gọi phương thức không hiện diện trong class được liên kết ở runtime |
| \`AbstractMethodError\` | Triển khai runtime không cung cấp phương thức được yêu cầu theo giao diện nhị phân |
| \`LinkageError: loader constraint violation\` | Các loader vi phạm ràng buộc identity của kiểu trong quá trình liên kết |
| \`IllegalAccessError\` hoặc \`InaccessibleObjectException\` | Kiểm tra phạm vi truy cập, JPMS modules và reflective access |

Một \`ClassCastException\` không tự chứng minh rằng Java “nạp sai JAR”; lỗi có thể xuất phát từ thiết kế loader, đóng gói API, phiên bản không tương thích, cache hoặc logic lựa chọn provider. Thu thập bằng chứng về defining loader và class source trước khi sửa cấu hình.

## 9. Checklist thực hành khi gặp lỗi

1. Ghi nguyên stack trace và dòng code cast; xác định actual type và expected type.
2. Log \`getName()\`, \`getClassLoader()\`, \`isAssignableFrom()\` và \`isInstance()\`.
3. Xác định classloader graph: parent, child-first exceptions, loader nào định nghĩa API và implementation.
4. Kiểm tra JAR thực tế và class resource; tìm lớp trùng package API hoặc thư viện version khác.
5. Kiểm tra việc hot reload, cache, static singleton, thread context class loader hoặc proxy lưu giữ object cũ.
6. Đảm bảo shared API dùng một định nghĩa \`Class\` từ parent/host; giới hạn package được cô lập.
7. Test đường đi thực sự: nạp plugin, cast sang interface của host, gọi phương thức, giải phóng và thay plugin.
8. Bổ sung kiểm tra packaging và compatibility ở bước pre-activation để lỗi được phát hiện trước khi phục vụ request.

**Ghi nhớ:** trong JVM, *tên lớp không phải toàn bộ danh tính của kiểu*. Khi hai lớp “cùng tên” không ép kiểu được, hãy so sánh **defining class loader**. Kiến trúc plugin bền vững cần **chia sẻ contract** tại ranh giới host và **cô lập dependency implementation** một cách có chủ đích.
