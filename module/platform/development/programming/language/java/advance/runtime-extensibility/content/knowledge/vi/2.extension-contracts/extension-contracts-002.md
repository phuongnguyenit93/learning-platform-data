# Tách kiểu dữ liệu và API dùng chung khỏi cách triển khai của plugin

Khi một ứng dụng cho phép thêm plugin, câu hỏi thiết kế quan trọng là: **host và plugin cần cùng biết điều gì, và điều gì phải nằm riêng trong mỗi plugin?** Nếu host gọi trực tiếp lớp triển khai như UppercaseTransformer, hoặc API dùng chung trả về một lớp chỉ có trong plugin cụ thể, việc bổ sung/thay thế plugin sẽ kéo theo sửa và biên dịch lại host. Giải pháp là định nghĩa một **hợp đồng mở rộng (extension contract)** nhỏ, ổn định, rồi để host và từng plugin phụ thuộc vào hợp đồng đó.

## 1. Ba phần và hướng phụ thuộc

Giả sử host nhận văn bản và cần gọi một trong nhiều bộ biến đổi do plugin cung cấp:

~~~text
             phụ thuộc lúc biên dịch
host-app --------------------------> plugin-api
                                           ^
                                           |
plugin-uppercase --------------------------+
      |
      +-- đăng ký implementation để host phát hiện lúc chạy

host-app -- khám phá ở runtime --> plugin-uppercase
~~~

| Thành phần | Chứa gì | Được phụ thuộc vào |
| --- | --- | --- |
| **plugin-api** | Interface SPI, kiểu dữ liệu đầu vào/đầu ra, quy tắc lỗi hoặc khả năng cần công bố | JDK và những thư viện chung thực sự cần thiết |
| **host-app** | Điều phối, cấu hình, chọn plugin, kiểm soát vòng đời, xử lý lỗi | plugin-api; có thể mang plugin ở runtime |
| **plugin-uppercase** | Lớp thực thi, thuật toán, dependency nội bộ, metadata đăng ký dịch vụ | plugin-api và dependency riêng của nó |

SPI (*Service Provider Interface*) là mặt hợp đồng mà plugin phải thực hiện để host gọi được. API chung định nghĩa **lời hứa có thể quan sát**, không định nghĩa **cách một plugin thực hiện lời hứa**.

Một sơ đồ phụ thuộc tốt có hai mũi tên biên dịch cùng đi về plugin-api. Trong ví dụ dưới đây, host không import hay khởi tạo trực tiếp UppercaseTransformer; nó chỉ biết interface Transformer. Plugin có thể đổi thuật toán mà không cần sửa host, miễn là vẫn đáp ứng hợp đồng.

Phân biệt hai việc: **tách phụ thuộc biên dịch** giúp host không biết lớp triển khai; **nạp/khám phá plugin khi chạy** là cơ chế khác (ServiceLoader, DI container, class loader riêng...). Bài này minh họa cả ranh giới và một cách khám phá đơn giản bằng Java SE.

## 2. Đặt kiểu dữ liệu và API nào vào hợp đồng chung?

Một API tốt nên chứa những khái niệm mà tất cả plugin và host thực sự cùng hiểu:

- **Đầu vào/đầu ra chung:** DTO có ý nghĩa độc lập với plugin, ví dụ TransformRequest và TransformResult. Java record phù hợp với dữ liệu nhỏ, bất biến về tham chiếu thành phần; lưu ý record không tự làm bất biến những object mutable chứa bên trong.
- **Hành vi mở rộng:** interface Transformer với id() và transform(...). Chữ ký chỉ dùng kiểu từ JDK hoặc plugin-api.
- **Ngữ nghĩa hợp đồng:** id phải ổn định/duy nhất trong một tập plugin; transform trả kết quả cho đầu vào hợp lệ; quy định rõ lỗi, null, tài nguyên và tính an toàn luồng khi hệ thống cần.
- **Version hoặc capability khi cần:** host có thể kiểm tra khả năng/phiên bản trước khi gọi các tính năng mới, thay vì ép mọi plugin phải hiểu ngay một API thay đổi.

Không đặt vào plugin-api các lớp như UppercaseTransformer, cấu hình cơ sở dữ liệu riêng, HTTP client riêng, repository, entity nội bộ, hay kiểu trả về từ thư viện mà chỉ một plugin sử dụng. Một chữ ký như phương thức trả về com.vendor.plugin.InternalResult sẽ làm host phải hiểu và tải loại dữ liệu đặc thù đó, phá vỡ ranh giới chung.

API cũng không nên trở thành một túi mọi tính năng có thể có. Nếu hai nhóm plugin có hợp đồng thực sự khác nhau, hãy cân nhắc hai SPI hẹp hoặc một capability được công bố rõ, thay vì một interface lớn buộc mọi plugin cung cấp các phương thức không liên quan.

## 3. Ví dụ Java 17+ chạy được: API JAR, plugin JAR và host JAR

Ví dụ dùng **classpath** thông thường, chưa sử dụng Java Platform Module System (JPMS). Tạo các tệp theo cấu trúc:

~~~text
src/
  api/
    com/example/spi/
      TransformRequest.java
      TransformResult.java
      Transformer.java
  plugin/
    com/example/plugin/
      UppercaseTransformer.java
    META-INF/services/
      com.example.spi.Transformer
  host/
    com/example/host/
      Main.java
~~~

### Bước 1: Viết DTO và SPI trong plugin-api

**src/api/com/example/spi/TransformRequest.java**

~~~java
package com.example.spi;

import java.util.Objects;

public record TransformRequest(String text) {
    public TransformRequest {
        Objects.requireNonNull(text, "text");
    }
}
~~~

**src/api/com/example/spi/TransformResult.java**

~~~java
package com.example.spi;

import java.util.Objects;

public record TransformResult(String text) {
    public TransformResult {
        Objects.requireNonNull(text, "text");
    }
}
~~~

**src/api/com/example/spi/Transformer.java**

~~~java
package com.example.spi;

public interface Transformer {
    String id();
    TransformResult transform(TransformRequest request);
}
~~~

Host và plugin sẽ biên dịch dựa trên ba kiểu này. Hợp đồng không đề cập đến chữ "uppercase", lớp triển khai hay cách xử lý văn bản. Kiểm tra null tại biên của DTO giúp lỗi dữ liệu được phát hiện sớm; một dự án thực tế có thể bổ sung các quy tắc khác như giới hạn kích thước đầu vào.

### Bước 2: Viết plugin thực thi riêng

**src/plugin/com/example/plugin/UppercaseTransformer.java**

~~~java
package com.example.plugin;

import com.example.spi.TransformRequest;
import com.example.spi.TransformResult;
import com.example.spi.Transformer;
import java.util.Locale;

public final class UppercaseTransformer implements Transformer {
    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public TransformResult transform(TransformRequest request) {
        return new TransformResult(request.text().toUpperCase(Locale.ROOT));
    }
}
~~~

Ở đây Locale.ROOT giúp cách đổi chữ hoa độc lập với locale mặc định của máy. Quan trọng hơn, plugin chỉ dùng DTO và interface từ plugin-api để trao đổi với host. Các lớp hỗ trợ riêng, nếu có, vẫn có thể nằm trong package của plugin.

Để Java ServiceLoader tìm được provider trên classpath, tạo **tệp văn bản** với tên chính xác:

**src/plugin/META-INF/services/com.example.spi.Transformer**

~~~text
com.example.plugin.UppercaseTransformer
~~~

Tên tệp là tên nhị phân đầy đủ của SPI; nội dung là tên lớp provider triển khai SPI, mỗi dòng một lớp. Ví dụ này dùng lớp public có constructor không tham số mặc định và không cần thư viện phụ trợ.

### Bước 3: Host chỉ gọi qua interface chung

**src/host/com/example/host/Main.java**

~~~java
package com.example.host;

import com.example.spi.TransformRequest;
import com.example.spi.Transformer;
import java.util.Map;
import java.util.ServiceLoader;
import java.util.TreeMap;

public final class Main {
    public static void main(String[] args) {
        Map<String, Transformer> plugins = new TreeMap<>();
        for (Transformer plugin : ServiceLoader.load(Transformer.class)) {
            if (plugins.putIfAbsent(plugin.id(), plugin) != null) {
                throw new IllegalStateException("Duplicate plugin id: " + plugin.id());
            }
        }

        System.out.println("Plugins: " + plugins.keySet());
        Transformer selected = plugins.get("uppercase");
        if (selected == null) {
            throw new IllegalStateException("Missing plugin: uppercase");
        }
        System.out.println(selected.transform(new TransformRequest("hello Java")).text());
    }
}
~~~

Host chỉ import các kiểu thuộc com.example.spi. ServiceLoader đọc metadata dịch vụ từ những JAR nhìn thấy được bởi class loader liên quan, rồi tạo provider. TreeMap khiến thứ tự danh sách id ổn định cho ví dụ; putIfAbsent phát hiện id trùng. Trong hệ thống thật, host còn nên kiểm tra id null/rỗng, khả năng tương thích và chính sách khi một provider lỗi.

### Bước 4: Biên dịch thành ba JAR và chạy

Chạy ở thư mục chứa src, với **JDK 17 hoặc mới hơn**. Các lệnh sau dùng **PowerShell trên Windows**; cờ --release 17 khiến mã ví dụ được biên dịch cho Java 17:

~~~powershell
New-Item -ItemType Directory -Force -Path 'out/api','out/plugin','out/host','dist' | Out-Null

javac --release 17 -encoding UTF-8 -d out/api src/api/com/example/spi/TransformRequest.java src/api/com/example/spi/TransformResult.java src/api/com/example/spi/Transformer.java
jar --create --file dist/plugin-api.jar -C out/api .

javac --release 17 -encoding UTF-8 -cp dist/plugin-api.jar -d out/plugin src/plugin/com/example/plugin/UppercaseTransformer.java
jar --create --file dist/uppercase-plugin.jar -C out/plugin . -C src/plugin META-INF/services

javac --release 17 -encoding UTF-8 -cp dist/plugin-api.jar -d out/host src/host/com/example/host/Main.java
jar --create --file dist/host.jar -C out/host .

java -cp "dist/plugin-api.jar;dist/host.jar;dist/uppercase-plugin.jar" com.example.host.Main
~~~

Trên Linux/macOS, thay dòng tạo thư mục bằng lệnh sau và đổi dấu phân cách trong classpath cuối từ dấu chấm phẩy thành dấu hai chấm; những lệnh javac và jar còn lại giữ nguyên:

~~~bash
mkdir -p out/api out/plugin out/host dist
java -cp "dist/plugin-api.jar:dist/host.jar:dist/uppercase-plugin.jar" com.example.host.Main
~~~

**Stdout khi chạy với plugin JAR:**

~~~text
Plugins: [uppercase]
HELLO JAVA
~~~

Điểm cần kiểm tra trong từng lệnh: bước biên dịch host chỉ có **dist/plugin-api.jar** trên compile classpath; **không có uppercase-plugin.jar**. Plugin cũng biên dịch chỉ với API. Chỉ khi chạy, ta mới đưa ba JAR vào runtime classpath để ServiceLoader phát hiện implementation.

Có thể dùng lệnh sau để kiểm tra provider descriptor thực sự được đóng trong plugin JAR:

~~~powershell
jar tf dist/uppercase-plugin.jar
~~~

Danh sách phải có cả lớp com/example/plugin/UppercaseTransformer.class và META-INF/services/com.example.spi.Transformer. Nếu thiếu tệp đăng ký hoặc bỏ plugin JAR khỏi runtime classpath, ServiceLoader không tìm thấy provider này và host sẽ báo thiếu plugin.

## 4. Đưa ranh giới trên vào một dự án Gradle

Trong dự án nhiều module, có thể dùng ba module **plugin-api**, **plugin-uppercase** và **host-app**. Ví dụ dependencies viết theo Gradle Groovy DSL, mỗi khối thuộc build.gradle của module tương ứng:

**plugin-uppercase/build.gradle**

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    compileOnly project(':plugin-api')
}
~~~

**host-app/build.gradle**

~~~groovy
plugins {
    id 'application'
}

dependencies {
    implementation project(':plugin-api')
    runtimeOnly project(':plugin-uppercase')
}

application {
    mainClass = 'com.example.host.Main'
}
~~~

Với cấu hình này, host compile với API và runtime có thể nhận plugin. Module plugin vẫn cần tệp đăng ký tại **src/main/resources/META-INF/services/com.example.spi.Transformer** để Gradle đưa vào JAR. Không đóng gói bản sao các lớp của plugin-api bên trong plugin-uppercase; để host cung cấp hợp đồng chung ở runtime.

Các dependency này phù hợp với tập plugin đã biết lúc build/deploy. Nếu cho phép người dùng thả JAR plugin mới sau khi ứng dụng đã khởi động, cần thêm cơ chế quản lý đường dẫn JAR, class loader, discovery lại, đóng tài nguyên và quy tắc vòng đời. Chỉ thêm một JAR vào thư mục khi JVM đang chạy sẽ **không tự động** làm ServiceLoader.load trên classpath hiện tại nhìn thấy nó.

## 5. Ranh giới class loader: cùng tên lớp chưa chắc là cùng kiểu

Trong JVM, danh tính một class được xác định bằng **tên nhị phân + class loader định nghĩa nó**. Nếu host tải com.example.spi.Transformer bằng loader A, còn plugin bằng một loader riêng kiểu child-first lại tự định nghĩa một bản sao Transformer bằng loader B, hai kiểu đó không giống nhau. Kết quả có thể là không cast được, lỗi cấu hình provider hoặc một lỗi liên kết lớp khó hiểu dù tên package/class trông giống hệt.

Quy tắc áp dụng khi dùng class loader riêng:

1. Nạp **plugin-api** bằng một loader chung mà cả host và plugin cùng nhìn thấy, thường là parent loader.
2. Cho plugin loader ủy quyền các package hợp đồng sang parent; chỉ nạp implementation và dependency riêng từ plugin.
3. Tránh bundle/shade các kiểu hợp đồng chung vào plugin JAR. Shade thư viện nội bộ có thể hợp lệ, nhưng không đổi danh tính các kiểu đi qua biên API.
4. Kiểm tra provider có thể ép về đúng Transformer.class mà host sử dụng, đặc biệt khi tạo lại loader hoặc nạp nhiều phiên bản plugin.

Ví dụ này chạy ba JAR trong cùng application classpath nên không đòi hỏi tạo class loader tùy chỉnh. Với môi trường có JPMS, provider có thể được công bố bằng provides và người dùng bằng uses trong module-info.java; đó là cơ chế đóng gói/khám phá khác nhưng ranh giới hợp đồng vẫn giữ nguyên.

## 6. Thiết kế hợp đồng cho thay đổi và tương thích

Tách API khỏi triển khai không có nghĩa mọi sửa đổi API đều an toàn. Plugin thường được biên dịch ở thời điểm khác host, vì vậy cần phân biệt tương thích nguồn, nhị phân và hành vi:

| Thay đổi | Ảnh hưởng có thể xảy ra | Hướng xử lý |
| --- | --- | --- |
| Sửa thuật toán bên trong UppercaseTransformer, giữ nguyên SPI | Thường không cần biên dịch lại host | Test hành vi, đóng gói lại plugin |
| Thêm phương thức abstract vào Transformer | Provider cũ có thể thiếu implementation; khi gọi có thể gặp AbstractMethodError | Xem xét default method phù hợp hoặc nâng phiên bản hợp đồng |
| Đổi package, tên hoặc chữ ký của SPI | Provider đã build có thể không liên kết được; service descriptor cũ không còn khớp | Thay đổi có kế hoạch, build/test lại plugin, version API |
| Đổi thành phần của một record DTO | Constructor/accessor có thể đổi chữ ký nhị phân; client cũ có thể lỗi khi liên kết | Thêm kiểu mới, adapter hoặc version contract |
| Thay đổi ý nghĩa id, null, lỗi hay dữ liệu trả về | Có thể vẫn biên dịch nhưng sai hành vi | Viết contract test và ghi rõ quy tắc |

Một chiến lược phổ biến là công bố phiên bản plugin-api, tài liệu phạm vi tương thích và một bộ **contract tests** dùng chung để mọi provider phải chạy qua. Nếu hệ thống cần nhiều thế hệ API đồng thời, host phải chủ động thiết kế adapter/version negotiation; không thể chỉ hy vọng tên class giữ nguyên là đủ.

Nên làm rõ lỗi nào là lỗi dữ liệu đầu vào, lỗi provider, lỗi tải provider và lỗi của host. Không để host phải catch loại exception riêng chỉ có trong JAR một plugin. Khi xử lý lỗi plugin, host có thể dùng một exception đã quy định trong API hoặc cơ chế bao lỗi nhất quán và ghi lại nguyên nhân gốc để chẩn đoán.

## 7. Những lỗi thiết kế thường gặp

**Host tạo trực tiếp implementation.** Viết new UppercaseTransformer() hay import package plugin trong mã điều phối làm host phụ thuộc triển khai. Thay bằng registry/discovery trả về Transformer, và để host quyết định chọn theo id hoặc capability.

**Dùng DTO của plugin làm chữ ký SPI.** Một interface chung trả về VendorSpecificResponse khiến mọi plugin/host lệ thuộc một vendor. Đưa dữ liệu thật sự chung vào plugin-api; chi tiết nội bộ chỉ được chuyển đổi ở phía plugin. Không biến một DTO chung thành tập hợp field dành riêng cho từng provider.

**Đóng nhiều bản plugin-api ở các plugin loader.** Những bản sao có thể tạo lỗi định danh kiểu. Bảo đảm một nguồn cung cấp lớp API qua parent/common loader và kiểm tra sơ đồ class loader khi triển khai.

**Có class triển khai nhưng thiếu đăng ký ServiceLoader.** Java không tự quét mọi class chỉ vì chúng implements interface. Với classpath ServiceLoader, cần đường dẫn META-INF/services đúng và provider hợp lệ; nếu dùng một framework discovery khác thì phải theo quy tắc của framework đó.

**Mặc định mọi plugin đều đáng tin hoặc thread-safe.** Plugin chạy cùng tiến trình có thể giữ thread, mở file/network, ném exception hoặc làm treo luồng host. Tài liệu API phải nói rõ vòng đời, đồng thời host cần timeout/isolation theo kiến trúc phù hợp. Class loader riêng giúp tổ chức dependency nhưng **không phải sandbox bảo mật**. Không bảo đảm hot unload nếu vẫn còn object, thread hay static reference giữ loader.

**Thay API mà không thử với plugin build cũ.** Build thành công cả workspace chưa chứng minh một plugin đã phát hành trước đó tương thích nhị phân. Kiểm thử bằng đúng JAR cũ với API/host mới khi chính sách hỗ trợ tương thích yêu cầu.

## 8. Cách tự kiểm tra ranh giới trên một hệ plugin thực tế

- Tạm bỏ JAR triển khai khỏi **compile classpath** của host. Host vẫn phải biên dịch được nếu API đã tách đúng.
- Mở JAR plugin và xác minh có provider descriptor, class implementation, nhưng không có bản sao các class com.example.spi.
- Chạy host cùng plugin JAR để thấy plugin được discover và gọi qua Transformer; thử bỏ plugin JAR để chắc chắn host báo thiếu provider một cách có chủ đích.
- Thử hai provider có cùng id để kiểm tra chính sách trùng; thử provider lỗi và xem host ghi nhận/cách ly theo đúng contract.
- Với loader động, thử lấy Transformer.class từ host và ép provider về interface đó; test tải lại/giải phóng tài nguyên, và kiểm tra plugin được build bằng các phiên bản API còn được hỗ trợ.

**Nguyên tắc cốt lõi:** kiểu dữ liệu trao đổi và API mà host cùng mọi plugin thực sự dùng chung thuộc một artifact hợp đồng ổn định. Thuật toán, dependency, cấu hình và lớp triển khai thuộc từng plugin. Host quản lý việc tìm, chọn và gọi plugin thông qua hợp đồng đó; cơ chế nạp có thể thay đổi mà không làm đảo ngược hướng phụ thuộc.
