# Giảm module thừa khi không dùng service

## 1. Mục tiêu

Java Platform Module System (JPMS) hỗ trợ Service Loader để một module sử dụng một service mà không phải phụ thuộc trực tiếp vào từng module cung cấp implementation. Cơ chế này rất linh hoạt, nhưng khi đóng gói ứng dụng thành custom runtime image bằng **jlink**, việc tự động liên kết service provider có thể làm image chứa nhiều module hơn mức ứng dụng cần.

Bài này tập trung vào cách giữ runtime image gọn khi ứng dụng không cần service provider, hoặc chỉ cần một số provider đã chọn.

Các ý chính:

- **jlink mặc định không thực hiện service binding** khi tạo image.
- Tùy chọn **--bind-services** bật service binding, đưa các module cung cấp service được module đã resolve sử dụng vào image cùng dependencies của chúng.
- **--add-modules** xác định root modules. jlink vẫn thêm các module được yêu cầu bằng requires và dependencies bắc cầu của chúng.
- Nếu chỉ cần một provider cụ thể, có thể thêm chính module provider đó vào root modules thay vì liên kết tất cả provider tìm được.
- Phải kiểm tra hành vi ServiceLoader sau khi tạo image: một provider bị loại khỏi image sẽ không thể được phát hiện từ image đó.

Không nên nhầm việc bỏ service binding với việc loại bỏ mọi module không dùng trực tiếp. Các module được yêu cầu qua requires vẫn phải có mặt để ứng dụng chạy.

## 2. Service binding tạo thêm module như thế nào?

Một ứng dụng modular có thể khai báo service usage trong module-info.java:

~~~java
module com.acme.application {
    requires com.acme.codec.api;
    uses com.acme.codec.Codec;
}
~~~

Module API định nghĩa service type:

~~~java
module com.acme.codec.api {
    exports com.acme.codec;
}
~~~

Một module khác cung cấp implementation:

~~~java
module com.acme.codec.json {
    requires com.acme.codec.api;

    provides com.acme.codec.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

Một provider khác có thể cung cấp cùng service:

~~~java
module com.acme.codec.xml {
    requires com.acme.codec.api;

    provides com.acme.codec.Codec
        with com.acme.codec.xml.XmlCodec;
}
~~~

Ứng dụng có thể tìm provider bằng ServiceLoader:

~~~java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);

for (Codec codec : codecs) {
    System.out.println(codec.name());
}
~~~

Module ứng dụng khai báo **uses** để nói rằng nó sử dụng service type. Module provider khai báo **provides ... with ...** để đăng ký implementation. Đây là quan hệ service-use riêng của module system; nó không tạo ra một chỉ thị requires trực tiếp từ application tới từng provider.

Nếu module ứng dụng chỉ khai báo requires com.acme.codec.api, dependency thông thường này không tự kéo tất cả module provider vào graph. Provider được thêm thông qua một trong các cách sau:

1. Được thêm rõ ràng vào root modules, ví dụ qua --add-modules.
2. Được thêm do một module khác yêu cầu bằng requires.
3. Được tìm thấy và thêm trong quá trình service binding.

### resolve và resolveAndBind

API Java biểu diễn hai kiểu giải quyết module graph:

- **Configuration.resolve(...)** giải quyết root modules cùng các dependency module thông thường.
- **Configuration.resolveAndBind(...)** thực hiện resolve và bổ sung các module provider phát sinh từ service-use dependence.

Với resolveAndBind, module system kiểm tra các module đã resolve có service dependence và các module trong parent configurations. Module nào cung cấp implementation cho service type được sử dụng có thể được thêm vào graph. Các module provider mới cũng được resolve; nếu chúng sử dụng service khác, quá trình tiếp tục cho đến khi không còn provider mới cần thêm.

Đây là lý do service binding có thể làm graph lớn lên theo nhiều tầng: một module provider được thêm vào có thể sử dụng service khác, từ đó kéo thêm provider và dependencies của provider đó.

## 3. Hành vi mặc định của jlink

**jlink mặc định không service-bind** khi tạo custom runtime image. Nó liên kết root modules và dependencies thông thường của chúng. Các module provider chỉ được đưa vào nếu chúng được thêm rõ ràng, được yêu cầu qua requires, hoặc được bao gồm bởi một lựa chọn root rộng hơn.

Ví dụ:

~~~text
jlink
  --module-path <module-path>
  --add-modules com.acme.application
  --output image-minimal
~~~

Image này chứa:

- com.acme.application và các module được khai báo requires trực tiếp hoặc bắc cầu;
- các module provider đã được thêm bằng cách khác;
- các module nền tảng cần thiết cho graph.

Image không tự động thêm com.acme.codec.json và com.acme.codec.xml chỉ vì application có chỉ thị uses com.acme.codec.Codec.

Đây là lựa chọn phù hợp khi:

- Ứng dụng không gọi ServiceLoader cho service đó.
- Service chỉ là extension point tùy chọn và không có provider nào cần triển khai trong image.
- Provider được nạp từ một nguồn khác trong kiến trúc triển khai, thay vì từ các module được liên kết vào image.
- Bạn muốn kiểm soát từng provider để giảm dung lượng runtime image.

### --bind-services thay đổi điều gì?

Khi bật tùy chọn:

~~~text
jlink
  --module-path <module-path>
  --add-modules com.acme.application
  --output image-with-services
  --bind-services
~~~

jlink liên kết các module provider tìm được cho service mà các module đã resolve sử dụng, cùng dependencies của các provider đó.

Trong ví dụ Codec, nếu cả hai provider đều observable trên module path và cung cấp com.acme.codec.Codec, service binding có thể đưa cả com.acme.codec.json và com.acme.codec.xml vào image.

Điều này thuận tiện khi ứng dụng cần toàn bộ provider có sẵn. Tuy nhiên, nếu chỉ cần một implementation hoặc không dùng service, tùy chọn này có thể làm image lớn hơn cần thiết.

**--bind-services là lựa chọn tường minh.** Không thêm tùy chọn này khi mục tiêu là chỉ liên kết root modules và dependencies thông thường.

## 4. Chọn một provider thay vì liên kết tất cả

Giả sử ứng dụng chỉ cần JsonCodec. Có thể thêm provider đó trực tiếp vào root modules:

~~~text
jlink
  --module-path <module-path>
  --add-modules com.acme.application,com.acme.codec.json
  --output image-json
~~~

Kết quả:

- com.acme.application và dependencies của nó được liên kết.
- com.acme.codec.json được liên kết cùng dependencies.
- com.acme.codec.xml không được thêm chỉ vì nó cũng cung cấp Codec.
- Không có bước tự động liên kết mọi provider của các service được sử dụng.

Cách này phù hợp khi deployment chọn một implementation cụ thể theo môi trường, ví dụ JSON ở production nhưng XML chỉ dùng trong một công cụ khác.

Nếu ứng dụng thực sự cần nhiều provider, liệt kê các module provider cần thiết:

~~~text
--add-modules com.acme.application,com.acme.codec.json,com.acme.codec.xml
~~~

Không cần bật --bind-services nếu danh sách provider đã được xác định đầy đủ. Nếu dependencies của provider sử dụng service khác và ứng dụng cũng cần các provider cho service đó, hãy thêm các provider tương ứng hoặc cân nhắc bật service binding sau khi đánh giá số module được thêm.

## 5. Tránh mở rộng root modules quá mức

Ngay cả khi không bật --bind-services, bạn vẫn có thể vô tình đưa nhiều module vào image bằng cách chọn root modules quá rộng.

Ví dụ:

~~~text
--add-modules ALL-MODULE-PATH
~~~

ALL-MODULE-PATH yêu cầu thêm mọi module quan sát được trên module path làm root. Nếu module path chứa nhiều provider, chúng có thể được liên kết do đã là root modules, dù service binding đang tắt.

Để tạo image nhỏ, hãy:

1. Chọn module ứng dụng làm root chính.
2. Để requires mô tả dependency module thực sự cần thiết.
3. Chỉ thêm provider cần dùng.
4. Không thêm toàn bộ module path chỉ để tránh thiếu một provider.
5. Kiểm tra kết quả bằng danh sách module của image.

Tùy chọn **--limit-modules** có thể giới hạn tập module observable cho quá trình resolve. Tập này gồm closure của các module được chỉ định, module chính nếu có, và các module được chỉ định qua --add-modules. Đây là công cụ kiểm soát nâng cao; nếu giới hạn quá chặt, jlink có thể không resolve được dependency hoặc provider mà ứng dụng cần. Chỉ dùng sau khi đã hiểu module graph và kiểm tra image sau khi build.

## 6. Tìm provider trước khi quyết định đưa vào image

jlink có tùy chọn **--suggest-providers** để liệt kê các module cung cấp implementation cho service type được chỉ định.

Ví dụ:

~~~text
jlink
  --module-path <module-path>
  --suggest-providers com.acme.codec.Codec
~~~

Kết quả có thể cho biết:

~~~text
Suggested providers:
  com.acme.codec.json provides com.acme.codec.Codec
  com.acme.codec.xml provides com.acme.codec.Codec
~~~

Từ danh sách này, bạn có thể chọn module cần thiết để thêm vào --add-modules.

Đây là bước hữu ích khi module path chứa nhiều provider hoặc khi service được cung cấp bởi module của JDK. Không nên đoán tên provider hoặc thêm tất cả provider trước khi biết ứng dụng thực sự cần implementation nào.

## 7. Ví dụ thực tế với charset provider của JDK

Một ví dụ trong JDK là service **java.nio.charset.spi.CharsetProvider**. Module java.base sử dụng service này; module jdk.charsets cung cấp một số charset bổ sung.

Khi chạy trên một JDK đầy đủ, module resolution thông thường có thể thực hiện service binding và tìm provider jdk.charsets. Vì vậy, nhiều charset có thể sẵn sàng trong môi trường JDK đầy đủ.

Khi tạo custom runtime image bằng jlink:

~~~text
jlink
  --add-modules java.base
  --output image-base-only
~~~

jlink không tự động thêm mọi provider chỉ vì java.base khai báo sử dụng service. Nếu ứng dụng cần các charset bổ sung trong jdk.charsets, hãy thêm module đó rõ ràng:

~~~text
jlink
  --add-modules java.base,jdk.charsets
  --output image-with-charsets
~~~

Hoặc bật --bind-services nếu muốn jlink tự động thêm các provider phù hợp cho service được các module đã resolve sử dụng:

~~~text
jlink
  --add-modules java.base
  --output image-bound
  --bind-services
~~~

Ví dụ này cho thấy sự khác biệt giữa một JDK đầy đủ và custom runtime image. Khi tạo image, bạn chịu trách nhiệm chọn module và provider mà ứng dụng cần.

## 8. Điều gì xảy ra nếu provider không có trong image?

Nếu ứng dụng gọi:

~~~java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);
~~~

nhưng không có provider phù hợp trong runtime image hoặc module layer mà ServiceLoader quan sát được, quá trình tìm kiếm không tự tải provider bị thiếu từ module path lúc build. ServiceLoader có thể trả về một kết quả rỗng.

Ví dụ:

~~~java
Optional<Codec> selected = ServiceLoader.load(Codec.class)
        .findFirst();

if (selected.isEmpty()) {
    throw new IllegalStateException(
            "No Codec provider is available in this runtime image");
}
~~~

Nếu service là bắt buộc, ứng dụng nên xử lý rõ trường hợp không tìm thấy provider. Nếu service chỉ là tính năng tùy chọn, có thể dùng implementation mặc định hoặc tắt chức năng liên quan theo thiết kế.

Đối với named module, module gọi ServiceLoader cần khai báo uses cho service type. Module provider cần khai báo provides trong module descriptor. Kiểm tra cả hai phía khi provider không được tìm thấy.

Không nên bỏ provider khỏi image chỉ dựa trên việc ứng dụng không tham chiếu trực tiếp tới class provider. ServiceLoader được thiết kế để tìm implementation thông qua service type, nên tên class provider có thể không xuất hiện trong code ứng dụng.

## 9. Phân biệt các lý do module xuất hiện trong image

Khi một module xuất hiện trong custom runtime image, hãy xác định nó được đưa vào bằng đường nào:

| Nguồn đưa module vào | Ví dụ | Cách kiểm soát |
|---|---|---|
| Root module | --add-modules com.acme.application | Chỉ chọn root thực sự cần |
| Dependency thông thường | application requires com.acme.api | Xem lại requires và dependency graph |
| Provider được chọn tường minh | --add-modules com.acme.codec.json | Chỉ thêm provider cần thiết |
| Service binding | --bind-services | Bỏ tùy chọn nếu không cần tự động liên kết provider |
| Root quá rộng | --add-modules ALL-MODULE-PATH | Thu hẹp danh sách root |

Việc tắt service binding chỉ ngăn đường bổ sung module do service-use dependence. Nó không loại bỏ module đã được thêm bằng requires, root module hoặc một dependency khác.

Một module provider có thể vẫn xuất hiện khi ứng dụng không dùng service nếu module đó được yêu cầu trực tiếp hoặc bắc cầu bằng requires, hoặc được chỉ định trong --add-modules. Muốn giảm thêm, phải xem lại dependency thực tế và kiến trúc module; không thể xóa an toàn một dependency chỉ bằng cách tắt service binding.

## 10. Quy trình tạo image gọn và có thể kiểm tra

### Bước 1 — Xác định root module

Chọn module khởi chạy của ứng dụng. Với jlink, --add-modules là nơi chỉ định root modules.

~~~text
--add-modules com.acme.application
~~~

### Bước 2 — Kiểm tra service usage

Tìm các chỉ thị uses trong module-info.java và các đoạn code gọi ServiceLoader. Kiểm tra cả dependencies, vì module thư viện cũng có thể khai báo uses.

Nếu ứng dụng không dùng service, loại bỏ chỉ thị uses không còn cần thiết và code ServiceLoader dư thừa. Nếu service là extension point tùy chọn, ghi rõ provider nào cần có trong từng môi trường triển khai.

### Bước 3 — Quyết định chiến lược provider

- Không dùng service: giữ mặc định, không bật --bind-services.
- Chỉ dùng một vài provider: thêm đúng module provider vào --add-modules.
- Cần mọi provider phù hợp trên module path: cân nhắc --bind-services.

### Bước 4 — Build image

~~~text
jlink
  --module-path <module-path>
  --add-modules com.acme.application
  --output image
~~~

Thêm provider module hoặc --bind-services tùy quyết định ở bước trước.

### Bước 5 — Kiểm tra module thực tế

Chạy Java trong image vừa tạo:

~~~text
image/bin/java --list-modules
~~~

Trên Windows:

~~~text
image\bin\java.exe --list-modules
~~~

Đối chiếu danh sách với root modules, requires dependencies và provider modules dự kiến. Không chỉ dựa vào kích thước thư mục để kết luận image đã tối ưu.

### Bước 6 — Kiểm tra chức năng service

Chạy integration test hoặc smoke test trên chính runtime image:

- ServiceLoader tìm thấy provider bắt buộc.
- Provider được chọn đúng với cấu hình deployment.
- Các chức năng tùy chọn xử lý trường hợp không có provider.
- Không phụ thuộc vào JDK đầy đủ của máy phát triển.

Kiểm tra trên JDK đầy đủ có thể che giấu lỗi thiếu provider trong custom image. Hãy chạy test bằng executable trong image đầu ra.

## 11. Các hiểu nhầm thường gặp

### Nghĩ uses tự động kéo provider vào jlink image

Chỉ thị uses mô tả service dependence. jlink mặc định không thực hiện service binding, vì vậy provider chỉ xuất hiện nếu được thêm qua root, dependency hoặc lựa chọn khác.

### Nghĩ bỏ --bind-services sẽ loại mọi provider

Không đúng. Provider được thêm bằng --add-modules hoặc requires vẫn được liên kết. Tắt service binding chỉ ngăn bước tự động thêm provider theo service-use dependence.

### Nghĩ --bind-services chỉ thêm provider mà ứng dụng chính gọi

Không nhất thiết. Các module đã resolve, bao gồm dependencies, có thể khai báo service usage. Provider cho các service đó cũng có thể được thêm; provider mới lại có thể tạo service dependence tiếp theo.

### Nghĩ provider không có trong image vẫn tự tìm được từ module path lúc chạy

Module path dùng khi chạy phải thực sự chứa provider và provider phải observable trong configuration phù hợp. Module path chỉ có ở máy build không tự trở thành module path của runtime image.

### Nghĩ ALL-MODULE-PATH tương đương với bind-services

Hai cơ chế khác nhau. ALL-MODULE-PATH thêm mọi module quan sát được trên module path làm root; --bind-services bổ sung provider theo service-use dependence của các module đã resolve. Cả hai đều có thể làm image lớn hơn, nhưng nguyên nhân khác nhau.

### Nghĩ module không được ứng dụng import trực tiếp là module thừa

Một module có thể được cần đến qua requires bắc cầu, reflection, service provider hoặc chức năng runtime khác. Phải kiểm tra cách module được sử dụng trước khi loại bỏ.

## 12. Checklist quyết định có bật service binding không

- Ứng dụng có gọi ServiceLoader hoặc dùng extension point dựa trên service không?
- Những module dependency nào khai báo uses?
- Service nào là bắt buộc, service nào chỉ là tùy chọn?
- Provider nào thực sự cần có trong image?
- Provider có được thêm do requires hoặc --add-modules trước khi xét service binding không?
- Có đang dùng ALL-MODULE-PATH khiến mọi module trên module path trở thành root không?
- Nếu không dùng --bind-services, các provider cần thiết đã được thêm tường minh chưa?
- Image sau khi build đã được kiểm tra bằng --list-modules chưa?
- Integration test có chạy bằng runtime image đầu ra không?
- Khi thiếu provider, ứng dụng có thông báo lỗi rõ ràng hoặc xử lý fallback phù hợp không?

**Ghi nhớ:** Muốn image nhỏ khi không cần service provider, hãy để jlink ở chế độ mặc định, chọn root modules chính xác và chỉ thêm provider cần thiết. Bật --bind-services khi bạn thực sự muốn module system tự động tìm và liên kết provider cho các service được dùng. Luôn xác minh danh sách module và chạy thử trên chính image được tạo.

## Tài liệu tham khảo

- Oracle Java SE 21 — jlink Command, các tùy chọn --add-modules, --bind-services, --limit-modules và --suggest-providers: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html
- Oracle Java SE 21 API — Configuration.resolve và Configuration.resolveAndBind: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/Configuration.html
- Dev.java — Creating Runtime and Application Images with JLink, mục Including Services: https://dev.java/learn/jlink/
- Oracle Java SE 21 API — ServiceLoader: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html
