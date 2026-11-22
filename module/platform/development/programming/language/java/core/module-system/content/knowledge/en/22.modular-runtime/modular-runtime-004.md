# java --show-module-resolution

Khi chạy ứng dụng modular, JVM phải resolve một tập module trước khi khởi chạy main class. Quá trình này xác định module gốc (root), các dependency được khai báo bằng `requires`, vị trí tìm thấy từng module và những module provider được bổ sung qua service binding.

Tùy chọn `java --show-module-resolution` yêu cầu Java launcher in thông tin của quá trình resolve trong lúc khởi động. Đây là công cụ hữu ích khi ứng dụng chạy được trên máy này nhưng thất bại trên máy khác, khi module path chứa nhiều phiên bản thư viện, hoặc khi một service provider bất ngờ xuất hiện hay biến mất khỏi runtime graph.

Bài này dùng JDK 21 và một ứng dụng có module `com.acme.app`. Các đường dẫn và tên module trong output minh họa có thể khác theo hệ điều hành, JDK và cách đóng gói.

## 1. Cú pháp cơ bản

Cú pháp tổng quát:

~~~bash
java --show-module-resolution --module-path <module-path> --module <module-name>/<main-class>
~~~

Các tùy chọn:

- `--show-module-resolution`: in thông tin module resolution khi ứng dụng khởi chạy.
- `--module-path` hoặc `-p`: chỉ định thư mục hoặc file JAR chứa named module.
- `--module` hoặc `-m`: chỉ định module chứa ứng dụng; có thể kèm main class sau dấu gạch chéo.
- `--add-modules`: bổ sung root module ngoài root được launcher chọn từ cách khởi chạy.
- `--limit-modules`: giới hạn tập module có thể quan sát khi resolve, hữu ích cho một số cấu hình runtime nhưng có thể làm dependency không còn tìm thấy.

Ví dụ:

~~~bash
java --show-module-resolution   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Cách viết ngắn:

~~~bash
java --show-module-resolution -p mods -m com.acme.app/com.acme.app.Main
~~~

Trong ví dụ này, `com.acme.app` là root module được khởi chạy. Java launcher tìm module trong `mods`, resolve các dependency của nó, tạo configuration và sau đó khởi chạy `com.acme.app.Main`.

Nếu module descriptor khai báo main class, bạn có thể khởi chạy module mà không cần ghi class sau dấu gạch chéo. Tuy nhiên, ghi rõ `module/main-class` giúp lệnh dễ đọc và tránh nhầm lẫn khi học hoặc debug.

## 2. Đọc output: root và requires

Giả sử ứng dụng có các module:

~~~text
mods/
├── com.acme.api/
│   └── module-info.class
└── com.acme.app/
    └── module-info.class
~~~

Descriptor của ứng dụng:

~~~java
module com.acme.app {
    requires com.acme.api;
}
~~~

Descriptor của API:

~~~java
module com.acme.api {
    exports com.acme.api;
}
~~~

Một output rút gọn có thể có dạng:

~~~text
root com.acme.app file:///project/mods/com.acme.app/
com.acme.app requires com.acme.api file:///project/mods/com.acme.api/
com.acme.app requires java.base jrt:/java.base
com.acme.api requires java.base jrt:/java.base
~~~

Cách đọc:

- `root` cho biết module nào được chọn làm điểm bắt đầu của configuration.
- `requires` cho biết module nào cần module khác theo descriptor.
- Đường dẫn sau tên module cho biết vị trí module được tìm thấy.
- `jrt:/...` là URI dùng để chỉ module nằm trong runtime image của JDK.
- `file:/...` hoặc URI file tương tự thường chỉ module được tìm từ module path.

Trong graph này, `com.acme.app` là root. Nó yêu cầu `com.acme.api`; cả hai module đều phụ thuộc ngầm định vào `java.base`. Vì vậy, dù ứng dụng chỉ khai báo một dependency trực tiếp, graph còn có các dependency nền tảng được resolve theo descriptor.

Tên và thứ tự các dòng output không nên được xem là giao diện ổn định để máy khác phân tích. Hãy đọc chúng như thông tin chẩn đoán dành cho con người; nếu cần xử lý tự động, dùng Java Module API thay vì parse văn bản console.

## 3. Root module được chọn như thế nào?

Root module là điểm bắt đầu của quá trình resolve. Root set ảnh hưởng trực tiếp đến graph cuối cùng.

Khi chạy:

~~~bash
java --show-module-resolution -p mods -m com.acme.app/com.acme.app.Main
~~~

module `com.acme.app` được chọn làm root.

Có thể bổ sung một root khác:

~~~bash
java --show-module-resolution   --module-path mods   --add-modules com.acme.tools   --module com.acme.app/com.acme.app.Main
~~~

Lúc này `com.acme.tools` cũng được đưa vào tập root. Nếu module đó có dependency riêng, các dependency ấy có thể xuất hiện trong output dù `com.acme.app` không yêu cầu trực tiếp `com.acme.tools`.

Một số giá trị đặc biệt của `--add-modules`:

- `ALL-MODULE-PATH`: chọn tất cả module quan sát được trên module path làm root.
- `ALL-SYSTEM`: chọn tất cả module hệ thống có thể quan sát trong runtime image.
- Tên module cụ thể: thêm module đó vào root set.

Không nên dùng `ALL-MODULE-PATH` chỉ để “sửa” lỗi thiếu dependency mà không tìm nguyên nhân. Nó có thể làm graph lớn hơn đáng kể, che khuất dependency thực sự của ứng dụng và làm runtime chứa những module không cần thiết.

## 4. Đọc vị trí module trong output

Vị trí module giúp xác định launcher đang dùng module nào khi có nhiều nguồn cung cấp:

| Dạng vị trí | Ý nghĩa thường gặp |
|---|---|
| `jrt:/java.base` | Module nằm trong runtime image của JDK |
| `file:/.../mods/com.acme.api/` | Exploded module được tìm thấy trên module path |
| `file:/.../lib/com.acme.api.jar` | Modular JAR hoặc JAR được nhận diện thành module |
| `jrt:/java.sql` | Module hệ thống `java.sql` của runtime image |

Nếu bạn có hai bản JAR cùng tên ở hai thư mục khác nhau, output giúp xác định bản nào đã được chọn. Hãy đối chiếu đường dẫn đó với cấu hình module path và artifact mà build tool tạo ra.

Đừng nhầm module location với vị trí source code. Java launcher resolve module đã đóng gói hoặc đã biên dịch; nó không dùng đường dẫn source `.java` để chạy ứng dụng.

## 5. Service binding và các dòng binds

Ngoài dependency `requires`, module graph có thể được mở rộng qua service binding.

Consumer khai báo service:

~~~java
module com.acme.app {
    requires com.acme.api;
    uses com.acme.api.Codec;
}
~~~

Provider khai báo implementation:

~~~java
module com.acme.codec.json {
    requires com.acme.api;

    provides com.acme.api.Codec
        with com.acme.codec.json.JsonCodec;
}
~~~

Khi configuration thực hiện service binding, provider phù hợp có thể được bổ sung nếu module provider nằm trong tập module quan sát được. Output resolution có thể thể hiện quan hệ này bằng dòng `binds`, ví dụ minh họa:

~~~text
root com.acme.app file:///project/mods/com.acme.app/
com.acme.app requires com.acme.api file:///project/mods/com.acme.api/
com.acme.app binds com.acme.codec.json file:///project/mods/com.acme.codec.json/
com.acme.codec.json requires com.acme.api file:///project/mods/com.acme.api/
~~~

Dòng `binds` giúp nhận ra provider được thêm vào do service binding. Module provider có thể kéo theo dependency của chính nó; nếu provider dùng một service khác, quá trình binding có thể tiếp tục mở rộng graph.

Một số điểm quan trọng:

- Consumer phải nằm trong graph và khai báo `uses` cho service cần tìm.
- Provider phải khai báo `provides ... with ...` cho đúng service type.
- Provider phải có thể được quan sát qua module finder/module path và không bị giới hạn khỏi tập module resolve.
- Nếu provider được chọn làm root hoặc được yêu cầu qua `requires`, nó vẫn xuất hiện dù không cần service binding.
- Nhiều provider có thể cùng được thêm cho một service. Service binding không phải cơ chế chọn duy nhất một implementation.

Output cụ thể phụ thuộc phiên bản JDK và graph. Nếu không có dòng `binds`, đừng kết luận ngay rằng descriptor provider sai; hãy kiểm tra root set, service type, module path và các giới hạn resolve.

## 6. So sánh root set và module graph

Để hiểu một module xuất hiện vì lý do nào, hãy chạy cùng ứng dụng với các root set khác nhau.

Chỉ root ứng dụng:

~~~bash
java --show-module-resolution -p mods -m com.acme.app/com.acme.app.Main
~~~

Bổ sung một module làm root:

~~~bash
java --show-module-resolution   -p mods   --add-modules com.acme.tools   -m com.acme.app/com.acme.app.Main
~~~

Đưa tất cả module trên module path vào root set:

~~~bash
java --show-module-resolution   -p mods   --add-modules ALL-MODULE-PATH   -m com.acme.app/com.acme.app.Main
~~~

So sánh các output:

1. Ghi lại các dòng `root`.
2. Tìm các dòng `requires` để xác định dependency thông thường.
3. Tìm các dòng `binds` nếu service binding bổ sung provider.
4. So sánh module location để xem module đến từ runtime image hay module path.
5. Với mỗi module chỉ xuất hiện ở lần chạy thứ hai, xác định nó được thêm bởi root mới, dependency của root đó hay service binding.

Cách làm này hữu ích khi một module “tự nhiên” xuất hiện trong ứng dụng. Đừng chỉ so sánh tổng số module; hãy tìm đường đi cụ thể khiến module được resolve.

## 7. Kết hợp với các công cụ chẩn đoán khác

`--show-module-resolution` tập trung vào graph module. Có thể kết hợp với những lệnh sau để kiểm tra các khía cạnh khác.

### Liệt kê module có thể quan sát

~~~bash
java --module-path mods --list-modules
~~~

Lệnh này liệt kê module mà runtime có thể quan sát trong runtime image và module path. Danh sách đó không đồng nghĩa tất cả module đều đã được resolve vào graph của ứng dụng.

### Mô tả descriptor một module

~~~bash
java --module-path mods --describe-module com.acme.app
~~~

Dùng lệnh này để xem `requires`, `exports`, `opens`, `uses` và `provides` của một module. Nó trả lời module khai báo gì, trong khi `--show-module-resolution` giúp thấy module nào thực sự được resolve khi chạy ứng dụng.

### Xem class loading

~~~bash
java -Xlog:class+load=info   --module-path mods   --module com.acme.app/com.acme.app.Main
~~~

Nếu lỗi nằm ở class loading, classpath hoặc class được nạp từ đâu, log class loading phù hợp hơn. Module resolution không phải log từng class được nạp.

### Kiểm tra dependency tĩnh bằng jdeps

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

`jdeps` hỗ trợ kiểm tra dependency của module và một số vấn đề liên quan đến module descriptor. Nó bổ sung thông tin phân tích tĩnh; không thay thế quan sát graph lúc launcher chạy.

## 8. Phân biệt java launcher với jlink

Hai công cụ đều làm việc với module graph nhưng phục vụ hai thời điểm khác nhau:

| Công cụ | Thời điểm | Mục đích |
|---|---|---|
| `java --show-module-resolution` | Lúc khởi chạy | Quan sát module được resolve cho lần chạy ứng dụng |
| `jlink` | Lúc tạo runtime image | Liên kết tập module thành runtime có thể triển khai |
| `jlink --bind-services` | Lúc tạo runtime image | Bổ sung provider module cho service trong graph liên kết |

Ví dụ:

~~~bash
jlink   --module-path "$JAVA_HOME/jmods:mods"   --add-modules com.acme.app   --bind-services   --output runtime-app
~~~

Sau đó quan sát runtime image:

~~~bash
runtime-app/bin/java   --show-module-resolution   --module com.acme.app/com.acme.app.Main
~~~

Ở bước đầu, `jlink --bind-services` ảnh hưởng thành phần module được đóng vào image. Ở bước sau, `java --show-module-resolution` cho biết graph được launcher resolve khi ứng dụng khởi chạy trên runtime đó. Hai output thuộc hai giai đoạn khác nhau, vì vậy không nên xem chúng là cùng một báo cáo.

## 9. Giới hạn của --show-module-resolution

Tùy chọn này rất hữu ích nhưng không trả lời mọi câu hỏi về ứng dụng:

- Nó cho biết module graph, không cho biết mọi class đã được nạp.
- Nó không chứng minh một provider đã được khởi tạo hoặc method của provider đã được gọi.
- Nó không cho biết thứ tự xử lý nghiệp vụ của các provider trong ứng dụng.
- Nó không hiển thị đầy đủ mọi quy tắc truy cập package, reflection hoặc lỗi runtime xảy ra sau khi main bắt đầu.
- Output là văn bản chẩn đoán; không nên phụ thuộc vào thứ tự dòng hoặc parse nó như một định dạng máy ổn định.

Nếu ứng dụng không khởi chạy được, hãy kết hợp thông tin resolution với exception đầy đủ, descriptor của module liên quan, module path và log class loading. Nếu ứng dụng khởi chạy nhưng không tìm thấy service, kiểm tra `uses`, `provides`, provider visibility và cách configuration được tạo.

## 10. Quy trình debug thực tế

Khi một module hoặc provider không xuất hiện như mong đợi, có thể đi theo thứ tự:

1. Xác định main module và root set thực tế từ lệnh `java`.
2. Chạy lại với `--show-module-resolution` để ghi nhận root và các cạnh `requires`.
3. Dùng `--describe-module` cho consumer để xác nhận `requires` và `uses`.
4. Dùng `--describe-module` cho provider để xác nhận `provides` và dependency của nó.
5. Dùng `--list-modules` hoặc kiểm tra module path để xác nhận provider có thể được quan sát.
6. Kiểm tra có `--limit-modules` hoặc cấu hình module path nào loại provider khỏi tập resolve không.
7. Nếu dùng runtime image, kiểm tra cách tạo image và việc có bật `jlink --bind-services` hay không.
8. So sánh output sau mỗi thay đổi nhỏ để tìm chính xác root, dependency hoặc service binding làm graph thay đổi.

Không thêm tất cả module vào root set chỉ để làm lỗi biến mất. Cách đó có thể che mất nguyên nhân và tạo runtime graph lớn hơn cần thiết.

## 11. Thực hành

1. Tạo module `com.acme.api`, `com.acme.app` và `com.acme.codec.json` với các descriptor `requires`, `uses`, `provides` như ví dụ.
2. Đặt các module đã compile vào thư mục `mods`.
3. Chạy `java --show-module-resolution -p mods -m com.acme.app/com.acme.app.Main` và ghi lại root, requires, binds cùng module location.
4. Chạy lại với `--add-modules com.acme.codec.json`. Xác định provider xuất hiện do root hay service binding.
5. Chạy với `--add-modules ALL-MODULE-PATH`. So sánh số root và graph với hai lần trước.
6. Dùng `java --describe-module` để đọc descriptor consumer/provider, sau đó đối chiếu với output resolution.
7. Tạo runtime image bằng `jlink --bind-services`, chạy ứng dụng trên image đó với `--show-module-resolution` và so sánh graph lúc link với graph lúc launch.

Khi đọc `java --show-module-resolution`, hãy phân biệt module được chọn làm root, dependency qua `requires`, provider được thêm qua service binding và vị trí thực tế của từng module. Từ những thông tin đó, bạn có thể giải thích vì sao graph có thành phần hiện tại, phát hiện module path sai và kiểm soát runtime modular một cách có căn cứ.
