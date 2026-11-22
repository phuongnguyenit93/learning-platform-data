# Gợi ý descriptor qua --generate-module-info

## 1. Mục tiêu

Khi chuyển một thư viện JAR truyền thống sang Java Platform Module System (JPMS), việc viết module-info.java thủ công có thể mất thời gian vì cần xác định dependency và package API. Công cụ jdeps trong JDK có tùy chọn --generate-module-info để phân tích JAR và tạo một module descriptor gợi ý.

Lệnh này hữu ích trong giai đoạn khảo sát và chuyển đổi thư viện:

- Phân tích bytecode để tìm phụ thuộc tới package và module khác.
- Xác định các module JDK mà thư viện cần.
- Đề xuất các chỉ thị requires và exports trong module-info.java.
- Tạo file descriptor trong thư mục đầu ra để lập trình viên kiểm tra, chỉnh sửa và biên dịch.

Kết quả là một bản nháp module-info.java. jdeps không tự biến JAR đầu vào thành modular JAR và không thể suy ra đầy đủ mọi yêu cầu runtime của thư viện. Descriptor được sinh ra phải được review, kiểm thử và điều chỉnh trước khi phát hành.

## 2. jdeps và vai trò trong quá trình modular hóa

jdeps là công cụ phân tích dependency đi kèm JDK. Nó đọc class file, thư mục class và JAR để xác định quan hệ phụ thuộc ở mức package, class hoặc module.

Một số tùy chọn thường dùng:

| Tùy chọn | Công dụng |
|---|---|
| -s hoặc -summary | In dependency summary theo archive |
| --list-deps | Liệt kê các module phụ thuộc |
| --list-reduced-deps | Liệt kê dependency graph đã rút gọn |
| --print-module-deps | In danh sách module phân tách bằng dấu phẩy, hữu ích với jlink |
| --generate-module-info DIR | Sinh module-info.java cho các JAR đầu vào |
| --generate-open-module DIR | Sinh descriptor dạng open module |
| --check MODULE | Kiểm tra descriptor và dependency của module |
| --jdk-internals | Tìm tham chiếu tới API nội bộ của JDK |
| --missing-deps | Tìm dependency không resolve được |

Không nên bắt đầu bằng cách chạy --generate-module-info rồi đưa ngay kết quả vào production. Trước tiên hãy hiểu dependency của thư viện, kiểm tra JDK nội bộ, xác định package nào thực sự là API công khai và kiểm tra những dependency không thể phát hiện chỉ từ bytecode.

## 3. Cú pháp --generate-module-info

Cú pháp cơ bản:

~~~bash
jdeps --generate-module-info <output-directory> <jar-file>
~~~

Ví dụ:

~~~bash
jdeps --generate-module-info generated dist/legacy-lib.jar
~~~

jdeps phân tích JAR và tạo file module-info.java trong thư mục con có tên module được suy ra cho JAR:

~~~text
generated/
└── legacy.lib/
    └── module-info.java
~~~

Tên module được xác định từ metadata của JAR nếu có Automatic-Module-Name trong manifest; nếu không, tên được suy ra từ tên file theo quy tắc đặt tên automatic module. Ví dụ legacy-lib.jar được suy ra thành legacy.lib.

Tùy chọn này tạo source file ở thư mục đầu ra. JAR đầu vào không bị thay đổi. Bạn cần xem lại descriptor, biên dịch module-info.java và đóng gói module-info.class vào JAR nếu muốn tạo explicit modular JAR.

Một số giới hạn của lệnh:

- --generate-module-info không dùng cùng --class-path hoặc --dot-output.
- Nếu thư viện phụ thuộc vào JAR khác, đặt dependency phù hợp trên module path để jdeps có thể resolve.
- Với multi-release JAR, chọn phiên bản cần phân tích bằng --multi-release.
- Nếu muốn tạo descriptor mở toàn bộ package cho reflection, jdeps có --generate-open-module. Đây là lựa chọn rộng quyền; chỉ dùng khi thiết kế thư viện thật sự cần open module.

## 4. Ví dụ thư viện JAR chưa có module descriptor

Giả sử có một thư viện cũ với hai package:

~~~text
legacy-lib/
└── src/
    └── com/
        └── acme/
            └── legacy/
                ├── api/
                │   └── LegacyApi.java
                └── impl/
                    └── InternalHelper.java
~~~

File src/com/acme/legacy/api/LegacyApi.java:

~~~java
package com.acme.legacy.api;

import java.sql.Connection;

public final class LegacyApi {
    private LegacyApi() {
    }

    public static String driverName(Connection connection) throws Exception {
        return connection.getMetaData().getDriverName();
    }
}
~~~

Public API nhận java.sql.Connection làm tham số. Vì vậy, module descriptor cần thể hiện dependency tới module java.sql; dependency này còn xuất hiện trong public signature.

File src/com/acme/legacy/impl/InternalHelper.java:

~~~java
package com.acme.legacy.impl;

public final class InternalHelper {
    private InternalHelper() {
    }

    public static String version() {
        return "1";
    }
}
~~~

Biên dịch và đóng gói thư viện thông thường:

~~~bash
mkdir -p classes dist generated

javac --release 17 -d classes \
  src/com/acme/legacy/api/LegacyApi.java \
  src/com/acme/legacy/impl/InternalHelper.java

jar --create --file dist/legacy-lib.jar -C classes .
~~~

JAR này chưa có module-info.class. Khi đặt trên module path, JVM có thể coi nó là automatic module; tên tự suy ra trong ví dụ là legacy.lib.

## 5. Phân tích dependency trước khi sinh descriptor

Chạy summary:

~~~bash
jdeps -s dist/legacy-lib.jar
~~~

Kết quả trên OpenJDK 24.0.2:

~~~text
legacy-lib.jar -> java.base
legacy-lib.jar -> java.sql
~~~

Có thể lấy danh sách module cần thiết:

~~~bash
jdeps --print-module-deps dist/legacy-lib.jar
~~~

Output:

~~~text
java.base,java.sql
~~~

java.base là module nền tảng được mọi module Java thông thường đọc ngầm định. java.sql xuất hiện vì thư viện sử dụng Connection trong public API.

--print-module-deps trả danh sách module JDK cần thiết, có thể dùng làm đầu vào cho jlink --add-modules. Kết quả này không thay thế việc kiểm tra dependency của ứng dụng đầy đủ, đặc biệt khi ứng dụng còn có thư viện ngoài JDK hoặc dependency được nạp qua reflection.

Nếu thư viện có dependency chưa resolve được, hãy xử lý module path và chạy lại phân tích. Không dùng --ignore-missing-deps để che lỗi rồi coi kết quả là đầy đủ.

## 6. Sinh module-info.java

Chạy:

~~~bash
jdeps --generate-module-info generated dist/legacy-lib.jar
~~~

jdeps thông báo:

~~~text
writing to generated\legacy.lib\module-info.java
~~~

Nội dung descriptor được sinh trong ví dụ:

~~~java
module legacy.lib {
    requires transitive java.sql;

    exports com.acme.legacy.api;
    exports com.acme.legacy.impl;
}
~~~

Giải thích:

- module legacy.lib là tên module được suy ra từ tên JAR.
- requires transitive java.sql thể hiện dependency tới java.sql được truyền tiếp cho module đọc legacy.lib. Trong ví dụ, public API dùng Connection, nên kiểu của module java.sql xuất hiện trong chữ ký API.
- exports com.acme.legacy.api công khai package API.
- exports com.acme.legacy.impl công khai cả package implementation vì jdeps phát hiện package trong JAR. Đây là gợi ý cần review, không nhất thiết là quyết định thiết kế đúng.

Điểm quan trọng: jdeps có thể export tất cả package mà nó phát hiện trong JAR. Package nội bộ thường không nên trở thành API công khai. Trước khi sử dụng descriptor, hãy xóa các exports không cần thiết và kiểm tra các dependency transitive có thực sự cần được truyền tới module consumer hay không.

## 7. Vì sao descriptor sinh ra cần được review?

Phân tích dependency dựa trên bytecode có thể xác định nhiều quan hệ tĩnh, nhưng không hiểu đầy đủ ý định thiết kế hoặc mọi hành vi runtime.

Những điều cần kiểm tra thủ công:

1. **Exports:** chỉ công khai package API mà người dùng thư viện cần truy cập. Package implementation có thể giữ kín.
2. **Requires transitive:** chỉ dùng khi kiểu từ dependency xuất hiện trong API được export và consumer cần đọc dependency đó thông qua module này.
3. **Requires static:** xem dependency có chỉ cần lúc biên dịch hay không; không tự chuyển requires thành requires static nếu chưa hiểu runtime.
4. **Opens:** jdeps không thể suy ra đầy đủ package cần mở cho reflection của ORM, serializer hoặc dependency injection. Khai báo opens có giới hạn khi framework thực sự cần.
5. **Uses/provides:** kiểm tra SPI và service provider. Đăng ký provider trong META-INF/services hoặc module-info.java có thể cần được bổ sung riêng.
6. **Reflection và tên class:** dependency được nạp bằng Class.forName, reflection, cấu hình XML/JSON hoặc resource có thể không xuất hiện như dependency bytecode thông thường.
7. **Native code và resource:** kiểm tra JNI, file cấu hình, service file, resource và dữ liệu được tải theo tên.
8. **JDK internal API:** dùng jdeps --jdk-internals để tìm tham chiếu tới package nội bộ. Không nên phát hành module phụ thuộc vào API nội bộ của JDK.
9. **Split package:** bảo đảm cùng một package không bị chia giữa nhiều named module.
10. **Tên module:** xác nhận Automatic-Module-Name hoặc tên được suy ra ổn định, phù hợp quy ước phân phối.

Không nên coi descriptor sinh ra là bằng chứng thư viện đã modular hóa hoàn chỉnh. Nó là cơ sở để bắt đầu thiết kế module boundary.

## 8. Biên dịch descriptor và cập nhật modular JAR

Sau khi review file generated/legacy.lib/module-info.java, hãy chỉnh descriptor và loại bỏ package implementation khỏi exports:

~~~java
module legacy.lib {
    requires transitive java.sql;

    exports com.acme.legacy.api;
}
~~~

Sau đó biên dịch descriptor với JAR hiện tại được đưa vào patch-module:

~~~bash
mkdir -p descriptor-classes

javac --patch-module legacy.lib=dist/legacy-lib.jar \
  -d descriptor-classes \
  generated/legacy.lib/module-info.java
~~~

--patch-module cho compiler biết các class hiện có thuộc module legacy.lib trong lúc biên dịch descriptor. Lệnh này tạo module-info.class trong descriptor-classes.

Thêm descriptor đã biên dịch vào bản JAR đầu ra:

~~~bash
jar --update --file dist/legacy-lib.jar \
  -C descriptor-classes module-info.class
~~~

Kiểm tra JAR sau khi cập nhật:

~~~bash
jar --describe-module --file dist/legacy-lib.jar
~~~

Descriptor đã review phải chỉ công khai package API:

~~~text
legacy.lib
exports com.acme.legacy.api
requires java.base mandated
requires java.sql transitive
~~~

Việc thêm module-info.class biến JAR thành explicit modular JAR. Hãy thực hiện trên bản build hoặc bản sao phát hành, giữ lại artifact gốc và chạy test trên module path trước khi phân phối.

## 9. Kiểm tra module sau khi chuyển đổi

Dùng jdeps --check để kiểm tra dependency graph và descriptor:

~~~bash
jdeps --check legacy.lib --module-path dist/legacy-lib.jar
~~~

Lệnh này hiển thị descriptor hiện tại, dependency sau phân tích và module graph rút gọn. Nó giúp phát hiện dependency khai báo thừa hoặc quan hệ module cần xem lại.

Có thể kiểm tra module descriptor:

~~~bash
jar --describe-module --file dist/legacy-lib.jar
~~~

Kiểm tra JDK internal API:

~~~bash
jdeps --jdk-internals dist/legacy-lib.jar
~~~

Nếu kết quả chỉ ra package nội bộ của JDK, hãy thay bằng API công khai được hỗ trợ. Việc một thư viện biên dịch được trên một JDK cụ thể không bảo đảm internal API sẽ tiếp tục tồn tại ở các bản JDK khác.

Kiểm tra dependency bị thiếu:

~~~bash
jdeps --missing-deps dist/legacy-lib.jar
~~~

Nếu JAR là multi-release, chọn đúng phiên bản runtime cần phân tích:

~~~bash
jdeps --multi-release 17 --generate-module-info generated dist/legacy-lib.jar
~~~

Chỉ dùng --multi-release với phiên bản từ 9 trở lên hoặc base. Chọn đúng release tương ứng với artifact và runtime mà dự án hỗ trợ.

## 10. Khi nào dùng --generate-open-module?

jdeps có tùy chọn:

~~~bash
jdeps --generate-open-module generated-open dist/legacy-lib.jar
~~~

Nó tạo descriptor dạng open module, nghĩa là tất cả package của module được mở cho deep reflection ở runtime. Điều này có thể giúp chuyển đổi nhanh thư viện cũ phụ thuộc reflection rộng.

Tuy nhiên, open module làm giảm mức encapsulation. Khi có thể, nên dùng module thông thường và khai báo opens cho đúng package, đúng framework cần truy cập. Không dùng open module chỉ để tránh tìm hiểu package nào thực sự cần reflection.

open module vẫn cần requires và dependency phù hợp. Tùy chọn này không tự giải quyết class loader, resource, service registration hoặc dependency được nạp động.

## 11. Quy trình chuyển đổi thư viện thực tế

Một quy trình an toàn thường gồm:

1. Chọn bản JAR đầu vào và ghi nhận checksum/version.
2. Dùng jdeps -s, --list-deps và --jdk-internals để hiểu dependency.
3. Resolve dependency bên ngoài trên module path khi phân tích.
4. Chạy --generate-module-info để lấy descriptor ban đầu.
5. Review module name, requires, requires transitive, exports, opens, uses và provides.
6. Biên dịch module-info.java với --patch-module.
7. Thêm module-info.class vào bản JAR đầu ra.
8. Kiểm tra bằng jar --describe-module và jdeps --check.
9. Chạy unit test, integration test và kiểm tra service/reflection trên module path.
10. Kiểm thử với các JDK runtime mà thư viện cam kết hỗ trợ.
11. Phát hành artifact mới cùng module name ổn định và tài liệu migration.

Nếu thư viện có nhiều phiên bản JDK hoặc multi-release JAR, hãy kiểm tra từng biến thể class. Descriptor cần phù hợp với toàn bộ API và dependency mà artifact thực sự cung cấp.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| jdeps không resolve được dependency | Thiếu JAR hoặc module trên module path | Bổ sung dependency đúng phiên bản và chạy lại |
| Module name không như mong đợi | Tên JAR được suy ra khác hoặc manifest có Automatic-Module-Name | Kiểm tra manifest và jar --describe-module |
| Descriptor export package nội bộ | jdeps tạo exports dựa trên package trong archive | Review và xóa exports không cần thiết |
| Consumer không truy cập được kiểu trong dependency | Thiếu requires transitive hoặc API boundary chưa đúng | Kiểm tra public signature và module graph |
| Reflection lỗi sau khi modular hóa | Package chưa được mở cho framework | Thêm opens có giới hạn hoặc cấu hình framework |
| ServiceLoader không tìm thấy provider | Thiếu uses/provides hoặc META-INF/services | Kiểm tra service registration và module layer |
| JAR vẫn là automatic module | module-info.class chưa được thêm vào artifact | Kiểm tra jar --list và jar --describe-module |
| Lỗi với JDK khác | Dùng API nội bộ hoặc descriptor không tương thích | Kiểm tra --release, jdeps --jdk-internals và CI matrix |

## 13. Checklist nghiệm thu

- [ ] Đã xác định JDK release và dependency dùng để phân tích.
- [ ] Đã xem dependency summary và danh sách module phụ thuộc.
- [ ] Đã sinh module-info.java từ đúng JAR đầu vào.
- [ ] Module name ổn định và không bị trùng.
- [ ] Requires và requires transitive phản ánh đúng API.
- [ ] Chỉ export package API cần công khai.
- [ ] Opens, uses và provides được review theo hành vi runtime.
- [ ] Không còn dependency ngoài ý muốn tới JDK internal API.
- [ ] Descriptor được biên dịch và module-info.class có trong JAR đầu ra.
- [ ] jar --describe-module và jdeps --check cho kết quả hợp lệ.
- [ ] Test chạy thành công trên module path và các JDK được hỗ trợ.
- [ ] Artifact gốc được giữ nguyên; artifact modular mới được kiểm tra trước khi phát hành.

## Tài liệu tham khảo

- [jdeps Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html)
- [jar Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [javac Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javac.html)
- [Module System — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/)
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261)
