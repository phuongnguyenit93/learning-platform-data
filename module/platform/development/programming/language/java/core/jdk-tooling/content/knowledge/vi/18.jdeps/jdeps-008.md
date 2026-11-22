# Phát hiện và xử lý JDK internal API bằng jdeps

## 1. JDK internal API là gì?

**JDK internal API** là các class, interface hoặc package phục vụ việc triển khai bên trong JDK. Chúng không thuộc hợp đồng API Java SE công khai mà ứng dụng có thể dựa vào lâu dài.

Một số tên thường gặp:

- sun.misc.Unsafe
- jdk.internal.misc.Unsafe
- jdk.internal.reflect.*
- com.sun.org.apache.xerces.internal.*
- com.sun.image.codec.jpeg.*

Các API này có thể thay đổi, bị đóng gói chặt hơn hoặc bị loại bỏ giữa các phiên bản JDK. Code phụ thuộc vào chúng có thể chạy được trên một JDK nhưng thất bại khi nâng cấp sang JDK khác.

Không nên kết luận mọi package bắt đầu bằng sun hoặc com.sun đều là internal chỉ dựa vào tên. Ví dụ, com.sun.net.httpserver là API được cung cấp công khai trong module jdk.httpserver. Hãy dùng kết quả phân tích của jdeps và tài liệu API của JDK để xác định chính xác.

## 2. Vì sao cần phát hiện internal API trước khi nâng cấp JDK?

Một dependency nội bộ có thể gây ra nhiều rủi ro:

- **Tương thích phiên bản:** class hoặc method có thể biến mất, đổi chữ ký hoặc đổi hành vi.
- **Encapsulation:** module system có thể chặn truy cập vào package nội bộ.
- **Biên dịch:** compiler có thể cảnh báo API proprietary hoặc từ chối truy cập package không được export.
- **Runtime:** JVM có thể ném IllegalAccessError hoặc InaccessibleObjectException.
- **Bảo trì:** ứng dụng phụ thuộc vào chi tiết triển khai của một vendor hoặc một bản JDK cụ thể.
- **Di chuyển nền tảng:** code có thể không chạy trên JDK distribution khác dù cùng Java release.

Từ Java 9, JPMS đưa ra ranh giới module và cơ chế exports/opens. JDK 16 và 17 tiếp tục tăng cường strong encapsulation đối với nhiều API nội bộ. Một số API quan trọng vẫn được giữ lại để tương thích, nhưng điều đó không biến chúng thành API Java SE ổn định.

Vì vậy, kiểm tra internal API là một phần quan trọng của quy trình nâng cấp JDK, nâng cấp thư viện và chuẩn bị ứng dụng modular.

## 3. jdeps giúp phát hiện internal API như thế nào?

**jdeps** là công cụ phân tích dependency của class file, thư mục class hoặc JAR. Tùy chọn quan trọng cho bài này là:

~~~bash
jdeps --jdk-internals app.jar
~~~

Có thể dùng alias cũ:

~~~bash
jdeps -jdkinternals app.jar
~~~

Tùy chọn **--jdk-internals** yêu cầu jdeps tìm dependency ở cấp class tới JDK internal API. Kết quả thường cho biết:

- Artifact hoặc module đang phân tích.
- Class trong ứng dụng tạo ra dependency.
- Class hoặc package nội bộ mà ứng dụng tham chiếu.
- Module JDK chứa API đó.
- Gợi ý hoặc đường dẫn tham khảo về hướng thay thế, nếu có.

Ví dụ một dòng kết quả:

~~~text
app.jar -> jdk.unsupported
   demo.InternalApiSample -> sun.misc.Unsafe JDK internal API (jdk.unsupported)
~~~

Dòng này cho biết class demo.InternalApiSample có dependency tới sun.misc.Unsafe và dependency đó nằm trong module jdk.unsupported.

jdeps phân tích bytecode đã biên dịch, không đọc trực tiếp source Java. Vì vậy, hãy build đúng artifact trước khi chạy công cụ.

## 4. Tạo ví dụ có dependency tới internal API

Tạo source tại src/demo/InternalApiSample.java:

~~~java
package demo;

import sun.misc.Unsafe;

public class InternalApiSample {
    public static void main(String[] args) {
        System.out.println("Internal type: " + Unsafe.class.getName());
    }
}
~~~

Đây là ví dụ cố ý tham chiếu tới sun.misc.Unsafe để minh họa cách phát hiện. Ứng dụng thực tế không nên dùng class này chỉ để lấy tên kiểu.

Biên dịch bằng JDK 17 trở lên:

~~~bash
mkdir -p out

javac --release 17 -encoding UTF-8 \
    -d out \
    src/demo/InternalApiSample.java
~~~

Compiler có thể phát cảnh báo rằng Unsafe là internal proprietary API và có thể bị loại bỏ trong tương lai. Việc biên dịch thành công không chứng minh API được hỗ trợ lâu dài.

Chạy ví dụ:

~~~bash
java -cp out demo.InternalApiSample
~~~

Stdout:

~~~text
Internal type: sun.misc.Unsafe
~~~

Tạo JAR để phân tích:

~~~bash
jar --create \
    --file app.jar \
    -C out .
~~~

Chạy jdeps trên JAR:

~~~bash
jdeps --jdk-internals app.jar
~~~

Với JDK 24.0.2, ví dụ này được phát hiện là dependency tới sun.misc.Unsafe trong module jdk.unsupported. jdeps trả về thông tin class gọi, internal API và cảnh báo về rủi ro tương thích.

Kết quả có thể khác về đường dẫn, cách trình bày hoặc gợi ý thay thế theo phiên bản JDK; hãy tập trung vào tên class gọi và API nội bộ được báo.

## 5. Đọc và diễn giải kết quả jdeps

Ví dụ output:

~~~text
app.jar -> jdk.unsupported
   demo.InternalApiSample -> sun.misc.Unsafe JDK internal API (jdk.unsupported)

Warning: JDK internal APIs are unsupported and private to JDK implementation
that are subject to be removed or changed incompatibly and could break your application.
~~~

Cách đọc:

1. **app.jar:** artifact được phân tích.
2. **jdk.unsupported:** module JDK cung cấp class nội bộ được tham chiếu.
3. **demo.InternalApiSample:** class phía ứng dụng tạo dependency.
4. **sun.misc.Unsafe:** class nội bộ mà ứng dụng sử dụng.
5. **JDK internal API:** jdeps nhận diện đây là API nội bộ.

Thông tin này giúp truy ngược từ dependency tới class source cần sửa. Nếu JAR chứa nhiều package, không nên chỉ xem tên module; hãy đọc từng dòng class-level dependency.

Nếu nhiều class cùng sử dụng một internal API, hãy nhóm kết quả theo API để xác định phạm vi thay đổi. Một thư viện bên thứ ba có thể tạo dependency dù source ứng dụng không trực tiếp import API đó.

jdeps có thể hiển thị gợi ý thay thế hoặc liên kết tới tài liệu migration. Gợi ý không phải lúc nào cũng là một thay thế 1:1; hãy đánh giá mục đích thực tế của code đang sử dụng API.

## 6. Phân tích cả ứng dụng và dependency JAR

Một ứng dụng thường phụ thuộc vào nhiều JAR. Chỉ phân tích JAR chính có thể bỏ sót internal API nằm trong thư viện phụ thuộc.

Ví dụ cấu trúc:

~~~text
project/
├── target/
│   └── app.jar
└── lib/
    ├── legacy-util.jar
    └── vendor-client.jar
~~~

Phân tích ứng dụng cùng classpath dependency:

~~~bash
jdeps --jdk-internals \
    --class-path "lib/*" \
    target/app.jar
~~~

Tùy hệ điều hành, dấu phân tách classpath khi có nhiều đường dẫn khác nhau:

- Windows dùng dấu chấm phẩy.
- Linux và macOS dùng dấu hai chấm.

Trên Windows PowerShell, có thể viết:

~~~powershell
jdeps --jdk-internals --class-path "lib\*" target\app.jar
~~~

jdeps có thể phân tích các class trong input và classpath theo quy tắc của công cụ. Với dự án lớn, hãy đảm bảo tất cả dependency cần kiểm tra thực sự nằm trong phạm vi phân tích.

Đối với thư viện được resolve qua module path, truyền module path phù hợp:

~~~bash
jdeps --jdk-internals \
    --module-path mods \
    --module com.example.app
~~~

Nếu phân tích một thư viện riêng, truyền trực tiếp đường dẫn JAR hoặc thư mục class của thư viện đó.

## 7. Phân tích dependency trực tiếp và mở rộng

Một số tùy chọn jdeps hữu ích:

| Tùy chọn | Công dụng |
|---|---|
| --jdk-internals | Tìm dependency tới JDK internal API. |
| --class-path | Chỉ định classpath để phân giải class dependency. |
| --module-path | Chỉ định module path. |
| --module | Chọn module gốc để phân tích. |
| -R hoặc --recursive | Phân tích đệ quy dependency runtime. |
| --no-recursive | Không duyệt dependency theo kiểu đệ quy. |
| -include regex | Giới hạn các class được phân tích theo regex. |
| --multi-release | Chọn phiên bản entry trong multi-release JAR. |
| --api-only | Chỉ phân tích dependency xuất hiện trong API public/protected. |

Ví dụ phân tích đệ quy:

~~~bash
jdeps --jdk-internals -R \
    --class-path "lib/*" \
    target/app.jar
~~~

Phân tích đệ quy giúp mở rộng việc duyệt dependency runtime theo khả năng của jdeps. Dù vậy, vẫn cần đưa các artifact cần thiết vào classpath hoặc module path để công cụ phân giải đúng.

Nếu muốn kiểm tra một phần class:

~~~bash
jdeps --jdk-internals \
    -include "com.example.*" \
    target/app.jar
~~~

Tùy chọn --jdk-internals không dùng cùng các bộ lọc -p, -e và -s theo giới hạn của jdeps. Nếu cần lọc, hãy dùng -include để giới hạn class được phân tích.

## 8. Multi-release JAR và phiên bản bytecode

Một multi-release JAR có thể chứa các phiên bản class khác nhau trong thư mục META-INF/versions. Class được chọn có thể phụ thuộc phiên bản Java đang chạy.

Khi phân tích JAR dạng này, chỉ rõ release cần kiểm tra:

~~~bash
jdeps --jdk-internals \
    --multi-release 17 \
    app.jar
~~~

Giá trị --multi-release có thể là số nguyên từ 9 trở lên hoặc base để chọn nội dung gốc của JAR.

Nếu ứng dụng hỗ trợ nhiều JDK release, nên phân tích các release mà dự án thực sự phân phối. Một phiên bản class có thể dùng API nội bộ trong khi phiên bản khác đã được thay thế bằng API công khai.

Không nên chỉ kiểm tra base entry rồi kết luận toàn bộ multi-release JAR an toàn.

## 9. API nội bộ trong public signature

Một class có thể không gọi API nội bộ trong phần thân method nhưng vẫn để lộ kiểu nội bộ trong public/protected signature.

Ví dụ một thư viện public method nhận hoặc trả về kiểu không thuộc API công khai của JDK. Khi đó, consumer cũng có thể bị buộc phụ thuộc vào kiểu nội bộ.

Tùy chọn **--api-only** giúp tập trung vào dependency xuất hiện trong signature của public/protected member:

~~~bash
jdeps --api-only --verbose:class app.jar
~~~

Đây là góc nhìn bổ sung khi kiểm tra tính ổn định của API thư viện. Nó không thay thế lần quét đầy đủ bằng --jdk-internals, vì internal API còn có thể được dùng bên trong method body hoặc class private.

Khi migration, cần kiểm tra cả hai câu hỏi:

- Có internal API nào xuất hiện trong public/protected contract không?
- Có internal API nào được dùng bên trong implementation không?

Nếu internal type bị lộ ra API công khai, ưu tiên thay đổi contract trước khi phát hành phiên bản tương thích tiếp theo.

## 10. jdeps và module dependency analysis

jdeps có nhiều chế độ phân tích module. Một số lệnh thường dùng:

~~~bash
jdeps --list-deps app.jar
~~~

In các module dependency mà artifact cần. Output có thể chứa module internal như jdk.unsupported nếu class tham chiếu tới sun.misc.Unsafe.

~~~bash
jdeps --print-module-deps app.jar
~~~

In danh sách module dependency phân tách bằng dấu phẩy. Kết quả có thể dùng làm đầu vào cho jlink --add-modules khi tạo runtime image.

~~~bash
jdeps --check com.example.app
~~~

Kiểm tra module descriptor và module dependency graph của module đã chỉ định.

Cần phân biệt mục tiêu:

- **--jdk-internals:** tìm class-level dependency tới API nội bộ.
- **--list-deps:** xem module dependency.
- **--print-module-deps:** lấy danh sách module để tạo runtime image.
- **--check:** kiểm tra module descriptor và quan hệ dependency.

Việc thấy jdk.unsupported trong danh sách module chưa đủ để biết class nào đang dùng API nội bộ. Hãy chạy --jdk-internals để tìm class-level reference.

## 11. Vì sao jdeps có thể không phát hiện mọi cách dùng internal API?

jdeps phân tích dependency được thể hiện trong class file. Một số cách truy cập động có thể không tạo reference class-level mà công cụ nhận diện được.

Ví dụ:

~~~java
String name = "jdk.internal.misc.Unsafe";
Class<?> type = Class.forName(name);
System.out.println(type.getName());
~~~

Tên class được giữ dưới dạng chuỗi. jdeps có thể không coi chuỗi đó là một class dependency thông thường.

Các trường hợp khác cần kiểm tra bổ sung:

- Class.forName với tên class tạo từ cấu hình.
- Reflection dựa trên chuỗi tên package/class.
- MethodHandles.Lookup và privateLookupIn.
- Native code gọi JNI hoặc truy cập symbol nội bộ.
- Framework/plugin tự nạp class theo cấu hình.
- Dependency được tải ở runtime từ vị trí không có trong classpath/module path khi phân tích.

Vì vậy, kết quả không có dòng internal API là tín hiệu tốt nhưng không phải bằng chứng tuyệt đối. Kết hợp jdeps với tìm kiếm source, kiểm tra cấu hình, phân tích dependency và integration test.

Có thể tìm các tên package đáng nghi trong source:

~~~bash
rg -n "sun\.|com\.sun\.|jdk\.internal\." src
~~~

Đây chỉ là bước sàng lọc. Hãy kiểm tra từng kết quả vì một số API có prefix com.sun vẫn là API công khai được hỗ trợ.

## 12. Lựa chọn API thay thế

Thay thế internal API cần dựa trên mục đích mà code đang sử dụng, không chỉ dựa trên tên class.

| Internal API hoặc mục đích | Hướng thay thế công khai |
|---|---|
| sun.misc.BASE64Encoder / BASE64Decoder | java.util.Base64. |
| Truy cập field và thao tác atomic/ordering qua Unsafe | VarHandle, java.lang.invoke và các API concurrency phù hợp. |
| Truy cập bộ nhớ native/off-heap qua Unsafe | Foreign Function & Memory API trong JDK hiện đại; kiểm tra baseline JDK của ứng dụng. |
| Internal XML parser/transformer | JAXP, javax.xml.parsers, javax.xml.transform, org.w3c.dom và org.xml.sax. |
| Internal JPEG codec | javax.imageio.ImageIO. |
| Tạo instance bỏ qua constructor bằng ReflectionFactory hoặc Unsafe | Thiết kế constructor/factory rõ ràng hoặc dùng API serialization được hỗ trợ nếu đúng trường hợp. |

Một số internal API không có thay thế tương đương hoàn toàn. Ví dụ, Unsafe cung cấp nhiều khả năng thấp cấp; VarHandle và Foreign Function & Memory API chỉ thay thế những nhóm use case tương ứng.

Với truy cập bộ nhớ native trong JDK mới, Foreign Function & Memory API nằm trong package java.lang.foreign và được hoàn thiện trong JDK 22. Nếu ứng dụng còn hỗ trợ JDK cũ hơn, cần chọn giải pháp tương thích với baseline hoặc điều chỉnh kế hoạch nâng cấp.

Không nên thay một internal API bằng một internal API khác chỉ vì API mới có vẻ thuận tiện hơn. Mục tiêu là chuyển về contract công khai, được tài liệu hóa và có chính sách tương thích rõ ràng.

## 13. Xử lý tạm thời bằng --add-exports và --add-opens

Trong giai đoạn migration, đôi khi cần giữ ứng dụng chạy trong khi chưa thể thay ngay dependency.

Tùy chọn **--add-exports** cho phép module export thêm một package tới module khác:

~~~bash
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED \
    -cp app.jar \
    com.example.Main
~~~

Ví dụ trên mở quyền truy cập các public type trong package jdk.internal.misc của module java.base cho code trên classpath (unnamed module).

Tùy chọn **--add-opens** phục vụ deep reflection ở runtime:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
    -cp app.jar \
    com.example.Main
~~~

Hai tùy chọn có mục đích khác nhau:

- --add-exports cho phép truy cập type/member public trong package được export bổ sung.
- --add-opens cho phép reflection sâu vào member không public của package tại runtime.

Với named module, thay ALL-UNNAMED bằng tên module đích phù hợp.

Đây là giải pháp tương thích tạm thời, không biến internal API thành API được hỗ trợ. Hãy ghi lại package/module được mở, lý do, thành phần phụ thuộc và thời hạn loại bỏ option.

Tùy chọn --illegal-access không còn là cách tổng quát để khôi phục truy cập rộng vào internal API trên JDK hiện đại. Không nên dùng nó làm kế hoạch migration.

## 14. Quy trình migration dependency nội bộ

Một quy trình thực tế có thể thực hiện theo các bước:

1. Build toàn bộ ứng dụng và thư viện đúng phiên bản dự định phát hành.
2. Chạy jdeps --jdk-internals trên JAR chính và các dependency quan trọng.
3. Ghi lại class gọi, API nội bộ, module JDK và dependency artifact liên quan.
4. Xác định dependency đến từ source của ứng dụng hay từ thư viện bên thứ ba.
5. Kiểm tra use case thực tế để chọn API Java SE hoặc JDK API công khai phù hợp.
6. Thay implementation và cập nhật dependency nếu thư viện bên ngoài đã có bản sửa.
7. Loại bỏ --add-exports hoặc --add-opens không còn cần thiết.
8. Biên dịch và chạy test trên JDK baseline thấp nhất mà dự án hỗ trợ.
9. Chạy lại jdeps để xác nhận dependency nội bộ đã biến mất hoặc có ngoại lệ được ghi nhận.
10. Đưa kiểm tra vào CI để phát hiện dependency mới trước khi merge/release.

Nếu dependency đến từ thư viện bên thứ ba, có thể cần nâng cấp thư viện, thay thư viện hoặc yêu cầu nhà cung cấp sửa. Không nên patch JDK để giữ ứng dụng chạy với internal API.

## 15. Tích hợp kiểm tra internal API vào CI

Có thể thêm một bước phân tích sau khi build JAR:

~~~bash
jdeps --jdk-internals \
    --class-path "target/lib/*" \
    target/application.jar
~~~

Đọc output và lưu log làm artifact của build. Nếu tổ chức muốn chặn dependency mới, có thể viết script CI kiểm tra kết quả jdeps và thất bại khi phát hiện dòng JDK internal API.

Một quy trình CI có thể gồm:

- Build JAR/module.
- Thu thập dependency đúng với runtime packaging.
- Chạy jdeps --jdk-internals.
- Kiểm tra các dependency đã được phê duyệt hoặc có migration ticket.
- Chạy unit test và integration test trên JDK mục tiêu.
- Lưu báo cáo dependency cùng artifact phát hành.

Không nên dùng --quiet để che warning khi đang kiểm tra internal API. Cần giữ diagnostic để biết class nào và API nào tạo dependency.

Nếu cho phép ngoại lệ tạm thời, ghi rõ owner, lý do, phiên bản thư viện liên quan và ngày dự kiến loại bỏ. Định kỳ chạy lại jdeps sau khi nâng cấp JDK hoặc dependency.

## 16. Lỗi thường gặp khi phân tích internal API

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jdeps không thấy internal API dù source có import | Đang phân tích nhầm hoặc chưa build lại artifact. | Build lại và chạy trên đúng class/JAR. |
| Chỉ thấy module jdk.unsupported | Mới xem module dependency, chưa có class-level report. | Dùng --jdk-internals. |
| Không phân giải được dependency class | Thiếu classpath hoặc module path. | Truyền đúng --class-path hoặc --module-path. |
| JAR multi-release cho kết quả khác nhau | Chưa chọn entry version-specific. | Dùng --multi-release với release cần kiểm tra. |
| jdeps không thấy Class.forName | Dependency được tạo động từ chuỗi. | Tìm kiếm source/config và chạy integration test. |
| Internal API vẫn chạy được trên máy hiện tại | Một số API còn được giữ để tương thích. | Vẫn coi là rủi ro và lập kế hoạch thay thế. |
| --add-exports không giải quyết lỗi reflection | Cần mở package cho deep reflection. | Xác định đúng use case và cân nhắc --add-opens tạm thời. |
| Một số com.sun package bị đánh dấu đáng nghi | Dùng prefix làm tiêu chí duy nhất. | Kiểm tra kết quả jdeps và tài liệu API của package cụ thể. |
| Thư viện bên thứ ba tạo dependency | Internal API nằm trong dependency JAR. | Nâng cấp, thay thư viện hoặc yêu cầu bản sửa. |
| Không có replacement trực tiếp | Internal API cung cấp hành vi thấp cấp đặc thù. | Phân tích use case và thiết kế lại bằng API công khai phù hợp. |

## 17. Checklist trước khi phát hành

- [ ] Đã chạy jdeps --jdk-internals trên JAR hoặc module đã build.
- [ ] Đã phân tích cả dependency quan trọng trên classpath/module path.
- [ ] Đã ghi nhận class gọi, internal API và module chứa API.
- [ ] Đã kiểm tra multi-release JAR nếu dự án sử dụng.
- [ ] Đã phân biệt dependency trực tiếp, dependency thư viện và truy cập động.
- [ ] Đã kiểm tra source/config cho reflection hoặc tên class dạng chuỗi.
- [ ] Đã chọn API công khai thay thế theo use case thực tế.
- [ ] Đã loại bỏ các --add-exports/--add-opens không còn cần thiết.
- [ ] Đã test trên các JDK release mà dự án hỗ trợ.
- [ ] Đã đưa jdeps vào CI hoặc quy trình nâng cấp dependency.
- [ ] Đã ghi nhận owner và thời hạn cho mọi ngoại lệ còn tồn tại.
- [ ] Đã chạy lại phân tích sau khi thay đổi JDK hoặc dependency.

jdeps giúp phát hiện dependency tĩnh tới JDK internal API và chỉ ra class tạo ra liên kết đó. Khi kết hợp báo cáo này với kiểm tra source, lựa chọn API công khai thay thế và test trên JDK mục tiêu, nhóm có thể giảm rủi ro khi nâng cấp runtime và duy trì tương thích lâu dài.