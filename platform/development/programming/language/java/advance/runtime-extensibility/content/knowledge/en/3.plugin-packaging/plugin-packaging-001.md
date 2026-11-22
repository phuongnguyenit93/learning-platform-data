# Tách JAR hợp đồng, JAR ứng dụng chủ và JAR phần triển khai

## Mục tiêu và vai trò của từng JAR

Một hệ thống plugin cần ranh giới rõ ràng giữa **hợp đồng mở rộng**, **ứng dụng chủ** và **phần triển khai có thể thay thế**. Thay vì biên dịch ứng dụng chủ cùng mọi plugin, đóng gói ba thành phần riêng:

| Thành phần | Chứa gì | Phụ thuộc lúc biên dịch | Được phân phối cho ai |
|---|---|---|---|
| **Contract/API JAR** | Interface, các kiểu dữ liệu ổn định mà hai bên dùng chung | Tối thiểu, tốt nhất không có dependency ngoài | Cả host và tác giả plugin |
| **Host JAR** | Điểm khởi chạy, vòng đời, khám phá và gọi plugin | Contract JAR | Người chạy ứng dụng |
| **Plugin implementation JAR** | Lớp triển khai interface, provider descriptor và tài nguyên riêng | Contract JAR | Người cài plugin, có thể phát hành độc lập |

Hướng phụ thuộc lúc biên dịch:

\`\`\`text
       host.jar ───────────┐
                           ▼
                      contract.jar
                           ▲
       plugin.jar ─────────┘

Host không import trực tiếp lớp triển khai trong plugin.
Plugin không phụ thuộc host.jar.
\`\`\`

Đây là ranh giới **compile-time dependency**. Trong lúc chạy, host vẫn cần truy cập contract JAR và có cách khám phá plugin JAR. Ví dụ dưới dùng Java SPI (\`ServiceLoader\`) trên classpath để minh họa sự tách biệt. Cơ chế nạp động phức tạp hơn, cách ly ClassLoader, bảo mật và phiên bản API là các quyết định bổ sung; việc tách file JAR tự nó chưa giải quyết những vấn đề ấy.

## Ví dụ hoàn chỉnh trên Java 17+

Ta xây dựng ứng dụng xử lý thông điệp bằng plugin. Contract quy định thao tác xử lý; host chọn provider qua \`ServiceLoader\`; plugin cung cấp một implementation. Cấu trúc dự án:

\`\`\`text
plugin-demo/
├── contract-src/
│   └── demo/api/MessagePlugin.java
├── host-src/
│   └── demo/host/Main.java
├── plugin-src/
│   ├── demo/plugin/UppercasePlugin.java
│   └── META-INF/services/demo.api.MessagePlugin
└── build/                              # sinh ra khi chạy lệnh
\`\`\`

### 1. Contract JAR: định nghĩa API chung

Tệp \`contract-src/demo/api/MessagePlugin.java\`:

\`\`\`java
package demo.api;

public interface MessagePlugin {
    String id();
    String transform(String input);
}
\`\`\`

\`id()\` là định danh để host nhận biết plugin; \`transform()\` là hành vi mà các provider phải triển khai. Interface thuộc package \`demo.api\`, không nằm trong package của host hay plugin. Chữ ký dùng \`String\` của JDK, tránh làm API phụ thuộc kiểu riêng của host.

Biên dịch và đóng gói từ thư mục \`plugin-demo\`:

\`\`\`bash
mkdir -p build/contract-classes
javac -d build/contract-classes contract-src/demo/api/MessagePlugin.java
jar --create --file build/contract.jar -C build/contract-classes .
\`\`\`

\`contract.jar\` hiện chứa \`demo/api/MessagePlugin.class\`. Nó phải có mặt đúng một bản trong phạm vi nạp lớp dùng chung của host và plugin.

### 2. Plugin JAR: triển khai và đăng ký provider

Tệp \`plugin-src/demo/plugin/UppercasePlugin.java\`:

\`\`\`java
package demo.plugin;

import demo.api.MessagePlugin;
import java.util.Locale;

public final class UppercasePlugin implements MessagePlugin {
    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
\`\`\`

Tệp văn bản \`plugin-src/META-INF/services/demo.api.MessagePlugin\` chứa chính xác tên lớp provider:

\`\`\`text
demo.plugin.UppercasePlugin
\`\`\`

Với kiểu provider thông thường dùng classpath, lớp triển khai phải được khai báo là provider trong file cấu hình \`META-INF/services/<tên-interface-đầy-đủ>\`. Lớp ở đây là \`public\`, có constructor không tham số public ngầm định, triển khai interface và được JVM khởi tạo khi \`ServiceLoader\` duyệt provider. Việc thiếu hoặc gõ sai descriptor khiến provider không được phát hiện; khai báo provider không hợp lệ có thể gây \`ServiceConfigurationError\`.

Biên dịch plugin chỉ với **contract JAR** trên compile classpath, rồi đóng gói cả \`class\` và descriptor:

\`\`\`bash
mkdir -p build/plugin-classes
javac -cp build/contract.jar -d build/plugin-classes plugin-src/demo/plugin/UppercasePlugin.java
jar --create --file build/plugin.jar \
  -C build/plugin-classes . \
  -C plugin-src META-INF/services
\`\`\`

Lệnh \`jar\` không tự sao chép descriptor chỉ vì ta đã biên dịch class: phải đưa tài nguyên này vào JAR. Plugin JAR không chứa lại \`MessagePlugin.class\` từ contract.

### 3. Host JAR: chỉ biết interface

Tệp \`host-src/demo/host/Main.java\`:

\`\`\`java
package demo.host;

import demo.api.MessagePlugin;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<MessagePlugin> plugins = ServiceLoader.load(MessagePlugin.class);
        boolean found = false;
        for (MessagePlugin plugin : plugins) {
            found = true;
            System.out.println(plugin.id() + ": " + plugin.transform("Xin chào Java"));
        }
        if (!found) {
            System.out.println("Không tìm thấy plugin");
        }
    }
}
\`\`\`

Host không import \`demo.plugin.UppercasePlugin\`: việc gắn kết implementation được thực hiện khi chạy qua service descriptor.

\`\`\`bash
mkdir -p build/host-classes
javac -cp build/contract.jar -d build/host-classes host-src/demo/host/Main.java
jar --create --file build/host.jar --main-class demo.host.Main -C build/host-classes .
\`\`\`

Ở cách đóng gói này, \`host.jar\` chỉ chứa mã host và manifest \`Main-Class\`. Nó **không** phải fat JAR; contract và plugin là các file riêng phải được đưa vào runtime classpath.

### 4. Chạy và kiểm chứng khả năng thay thế

Trên Linux/macOS, dấu phân cách classpath là \`:\`:

\`\`\`bash
java -cp "build/host.jar:build/contract.jar:build/plugin.jar" demo.host.Main
\`\`\`

Trên Windows, dùng dấu \`;\`:

\`\`\`powershell
java -cp "build/host.jar;build/contract.jar;build/plugin.jar" demo.host.Main
\`\`\`

Kết quả chính xác của cả hai:

\`\`\`text
uppercase: XIN CHÀO JAVA
\`\`\`

Thử bỏ plugin JAR khỏi runtime classpath:

\`\`\`bash
java -cp "build/host.jar:build/contract.jar" demo.host.Main
\`\`\`

Kết quả:

\`\`\`text
Không tìm thấy plugin
\`\`\`

Như vậy cùng \`host.jar\` và \`contract.jar\` vẫn chạy khi không có plugin, và phát hiện plugin khi JAR cung cấp provider có mặt. Nếu đổi provider hoặc thêm provider tương thích, không phải biên dịch lại host.

Có thể kiểm tra trực tiếp nội dung bằng:

\`\`\`bash
jar --list --file build/contract.jar
jar --list --file build/plugin.jar
jar --list --file build/host.jar
\`\`\`

Hãy xác nhận \`contract.jar\` chứa \`demo/api/MessagePlugin.class\`, \`plugin.jar\` chứa \`demo/plugin/UppercasePlugin.class\` cùng \`META-INF/services/demo.api.MessagePlugin\`, còn \`host.jar\` chứa \`demo/host/Main.class\`. Danh sách đầy đủ còn có manifest và entry thư mục tùy lệnh đóng gói.

## Quy tắc dependency khi dùng Maven hoặc Gradle

Trong dự án đa module, thể hiện hướng phụ thuộc như sau:

\`\`\`text
:plugin-api          (định nghĩa contract; xuất bản artifact riêng)
:host                -> :plugin-api
:uppercase-plugin    -> :plugin-api
\`\`\`

Với Gradle Java Library plugin, ví dụ phần dependencies:

\`\`\`groovy
// host/build.gradle
plugins { id 'application' }
dependencies { implementation project(':plugin-api') }
application { mainClass = 'demo.host.Main' }
\`\`\`

\`\`\`groovy
// uppercase-plugin/build.gradle
plugins { id 'java-library' }
dependencies { compileOnly project(':plugin-api') }
\`\`\`

\`compileOnly\` phù hợp khi runtime của host đã cung cấp API JAR và ta không muốn package lại contract vào plugin. Nó cũng có nghĩa plugin phải được chạy trong môi trường có contract; nếu cần test plugin độc lập, bổ sung \`testImplementation project(':plugin-api')\` theo nhu cầu. Với các hệ thống xuất bản plugin cho bên thứ ba, contract nên có tọa độ artifact và version rõ ràng, ví dụ \`com.example:plugin-api:1.0.0\`. Người viết plugin biên dịch chống lại API đã phát hành, không phụ thuộc mã host nội bộ.

Nếu plugin cần một thư viện riêng, package hoặc phân phối runtime dependency đó một cách có chủ đích. JAR thường không tự chứa các JAR phụ thuộc. Một fat JAR có thể phù hợp trong một số mô hình, nhưng tuyệt đối tránh nhúng một bản \`contract.jar\` riêng vào không gian ClassLoader của provider khi host kỳ vọng cùng một lớp contract.

## Classpath, ClassLoader và danh tính kiểu

Trên classpath đơn giản của ví dụ, cả ba JAR được application ClassLoader nạp. Khi chuyển sang kiến trúc host tải plugin lúc chạy bằng \`URLClassLoader\`, cần duy trì **một định nghĩa được chia sẻ** của \`demo.api.MessagePlugin\` qua parent ClassLoader. Trong JVM, tên đầy đủ của lớp **chưa đủ** để đảm bảo cùng kiểu: danh tính lớp còn phụ thuộc ClassLoader định nghĩa nó. Nếu host và plugin nạp hai bản contract trong hai ClassLoader khác nhau, hai interface cùng tên có thể không tương thích và ép kiểu thất bại (\`ClassCastException\`).

Thiết kế phổ biến là parent loader cung cấp contract và các kiểu chung; child loader của plugin nạp implementation và dependency riêng, thường với cơ chế parent-first tiêu chuẩn. Cần chủ động giải quyết trùng dependency, tên package, native library, resource, thread, khả năng unload, và cách quản lý lifecycle khi chuyển tới plugin isolation. \`ServiceLoader.load(MessagePlugin.class)\` mặc định sử dụng thread context ClassLoader; nếu triển khai loader riêng, truyền loader rõ ràng bằng \`ServiceLoader.load(MessagePlugin.class, pluginClassLoader)\`.

## Tương thích phiên bản, phát hành và kiểm thử

- **Giữ hợp đồng nhỏ và ổn định:** tránh đưa các kiểu implementation, dependency cụ thể của host hoặc trạng thái nội bộ vào API. Ghi rõ quy tắc nullability, exception, thread safety và lifecycle nếu ảnh hưởng provider.
- **Quản lý thay đổi API:** bổ sung abstract method vào interface có thể làm provider cũ không còn tương thích khi phương thức được gọi; thay đổi chữ ký hoặc xóa phương thức có thể gây lỗi liên kết. Dùng kiểm tra binary compatibility và thử plugin biên dịch với bản API cũ trên host mới. Default method đôi khi hỗ trợ mở rộng, nhưng cũng cần đánh giá xung đột và hành vi.
- **Tách ba bước build:** build/publish \`plugin-api\` trước; host và plugin compile phụ thuộc artifact API; phát hành plugin mà không rebuild host. Kiểm tra metadata, nội dung JAR và service descriptor sau packaging.
- **Thử cả hai trạng thái runtime:** thiếu plugin phải có fallback hoặc thông báo rõ; có plugin phải được phát hiện và thực thi đúng. Với nhiều provider, đừng mặc định thứ tự \`ServiceLoader\` là thứ tự ưu tiên nghiệp vụ; sắp xếp hoặc lựa chọn có chủ đích nếu cần.
- **Bảo vệ host:** validate plugin ID, input/output, lỗi provider và compatibility trước khi kích hoạt; \`ServiceLoader\` có thể ném \`ServiceConfigurationError\`, còn implementation có thể ném exception. Plugin bên thứ ba chạy cùng process có khả năng truy cập nhiều tài nguyên của process; một JAR riêng không phải sandbox bảo mật.

## Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Host import \`UppercasePlugin\` | Host bị gắn chặt với một implementation; phải rebuild khi thay plugin | Host chỉ import interface và khám phá implementation |
| Plugin phụ thuộc \`host.jar\` | Lộ chi tiết host, dễ tạo vòng dependency | Chuyển các kiểu thực sự cần chung về API độc lập |
| Đóng gói contract lặp trong loader riêng | Các kiểu trùng tên có thể không ép kiểu được | Dùng một contract do parent loader cung cấp |
| Thiếu \`META-INF/services\` | \`ServiceLoader\` không tìm thấy provider trên classpath | Đặt descriptor đúng tên và đóng gói trong plugin JAR |
| Chỉ đưa \`plugin.jar\` lên runtime classpath | Host hoặc provider có thể không tìm thấy API | Cung cấp \`contract.jar\` và dependency runtime cần thiết |
| Cho rằng mọi plugin tương thích mọi API | Có thể xảy ra \`NoSuchMethodError\`, lỗi khởi tạo hoặc thay đổi hành vi | Version hóa API và kiểm thử tương thích |

## Checklist trước khi phân phối

1. Contract JAR chỉ chứa API công khai và các kiểu dùng chung được thiết kế ổn định.
2. Host JAR compile với contract, không compile phụ thuộc implementation.
3. Plugin JAR compile với contract và chứa provider descriptor/tài nguyên đầy đủ.
4. Bộ JAR runtime có đúng một phiên bản contract dùng chung trong loader tương thích.
5. Chạy kiểm chứng có plugin, không plugin, plugin lỗi, và thử tương thích các phiên bản được hỗ trợ.
6. Tài liệu phát hành chỉ rõ phiên bản Java, phiên bản contract, dependency runtime, cách cài/gỡ plugin và cơ chế chọn provider.

**Kết luận:** Tách contract, host và implementation thành ba artifact cho phép phát hành plugin độc lập và giữ host ổn định. Hiệu quả thực tế phụ thuộc vào hướng dependency, cách nạp lớp, metadata provider và quy tắc tương thích được kiểm chứng khi chạy.
