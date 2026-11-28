# Chạy application image trên máy không cài JDK riêng

**Application image** do **jpackage** tạo là một thư mục ứng dụng có launcher native và Java runtime được đóng gói cùng. Người dùng có thể chạy launcher trên máy đích mà không cần cài riêng JDK hoặc JRE, miễn là image được tạo cho đúng hệ điều hành và kiến trúc, đồng thời các phụ thuộc native của ứng dụng có mặt.

Nếu không truyền runtime image có sẵn, jpackage dùng **jlink** để tạo runtime phù hợp rồi đặt runtime đó trong application image. Đây là điểm giúp ứng dụng Java có thể được phân phối như một ứng dụng độc lập. Bài học này hướng dẫn cách tạo image, kiểm tra nội dung, chuyển image sang máy khác và khởi chạy trên Windows, Linux hoặc macOS.

## 1. Application image là gì?

Application image là cấu trúc thư mục chứa những thành phần cần thiết để khởi chạy một ứng dụng Java:

- Launcher native do jpackage tạo.
- File cấu hình launcher.
- JAR hoặc module của ứng dụng và các file đầu vào.
- Java runtime image được đóng gói cùng ứng dụng.

Khác với việc gửi một file JAR rồi yêu cầu người dùng chạy **java -jar**, application image có launcher riêng. Launcher biết vị trí runtime đi kèm và cấu hình khởi chạy do jpackage tạo.

Khi người dùng chạy launcher, ứng dụng sử dụng runtime nằm trong application image. Máy đích không cần tìm một Java installation bên ngoài thông qua PATH hoặc JAVA_HOME.

Application image có thể được dùng để:

- Kiểm thử ứng dụng trước khi tạo installer.
- Phân phối ứng dụng dưới dạng thư mục có thể chạy.
- Làm đầu vào cho bước tạo gói cài đặt native.
- Đóng gói ứng dụng cùng runtime đã chọn.

## 2. Application image chứa những gì?

Cấu trúc cụ thể phụ thuộc hệ điều hành. Với một ứng dụng đơn giản tên **OrderDesk**, cấu trúc tiêu biểu như sau.

### Windows

~~~text
OrderDesk/
  OrderDesk.exe
  app/
    OrderDesk.cfg
    orderdesk.jar
  runtime/
    bin/
    conf/
    lib/
~~~

Chạy file **OrderDesk.exe** để khởi động ứng dụng.

### Linux

~~~text
OrderDesk/
  bin/
    OrderDesk
  lib/
    app/
      OrderDesk.cfg
      orderdesk.jar
    runtime/
      bin/
      conf/
      lib/
~~~

Chạy launcher **bin/OrderDesk**.

### macOS

~~~text
OrderDesk.app/
  Contents/
    Info.plist
    MacOS/
      OrderDesk
    Resources/
    app/
      OrderDesk.cfg
      orderdesk.jar
    runtime/
      bin/
      conf/
      lib/
~~~

Người dùng thường mở file bundle **OrderDesk.app** từ Finder hoặc dùng lệnh **open**.

Đây là cấu trúc minh họa theo tài liệu đóng gói của JDK. Một số file và thư mục bên trong là chi tiết triển khai, có thể thay đổi giữa các phiên bản JDK. Khi chạy ứng dụng, hãy sử dụng launcher được tạo ra thay vì viết script phụ thuộc vào đường dẫn nội bộ của runtime. Xem [Generated Application Image trong tài liệu JDK 16](https://docs.oracle.com/en/java/javase/16/jpackage/packaging-overview.html).

## 3. Vì sao máy đích không cần cài JDK?

Khi tạo application image, jpackage cần một JDK trên máy build. Nếu không truyền runtime image riêng, jpackage gọi **jlink** để tạo runtime image rồi đưa nó vào application image.

Runtime đi kèm thường có các thành phần:

- JVM và các thư viện runtime cần thiết.
- Các module JDK cần cho ứng dụng.
- Cấu hình runtime cần thiết để launcher khởi động ứng dụng.

Runtime image do jpackage tạo không phải một JDK đầy đủ. Nó không bao gồm các công cụ phát triển thông thường như javac, javadoc, jdeps, jpackage, trang man hoặc source archive. Mục tiêu là chạy ứng dụng, không phải phát triển hay biên dịch mã Java trên máy người dùng.

Vì vậy cần phân biệt:

| Máy build | Máy chạy ứng dụng |
| --- | --- |
| Cần JDK có jpackage và jlink | Không cần cài JDK/JRE riêng |
| Có source, JAR, module và tài nguyên đầu vào | Nhận application image hoàn chỉnh |
| Tạo launcher và runtime image | Chạy launcher được đóng gói |
| Có thể cần công cụ native để tạo installer | Chỉ cần hệ điều hành tương thích và các phụ thuộc runtime bên ngoài |

Nếu người dùng chạy file JAR trực tiếp bằng lệnh **java -jar**, họ vẫn cần một Java runtime được cài riêng. Để tận dụng runtime đi kèm, hãy chạy launcher trong application image.

## 4. Tạo application image cho ứng dụng không modular

Giả sử ứng dụng đã được build thành JAR và có manifest khai báo Main-Class:

~~~text
order-app/
  input/
    orderdesk.jar
    lib/
      database-driver.jar
      utility.jar
~~~

Tạo image trên Windows:

~~~powershell
jpackage --type app-image --name OrderDesk --input "input" --main-jar "orderdesk.jar" --dest "dist"
~~~

Trên Linux hoặc macOS:

~~~bash
jpackage --type app-image \
  --name OrderDesk \
  --input input \
  --main-jar orderdesk.jar \
  --dest dist
~~~

Nếu JAR không khai báo Main-Class trong manifest, chỉ định lớp main:

~~~bash
jpackage --type app-image \
  --name OrderDesk \
  --input input \
  --main-jar orderdesk.jar \
  --main-class com.example.order.Main \
  --dest dist
~~~

Thư mục **input** chứa JAR chính cùng các file ứng dụng cần đóng gói. Hãy đưa các thư viện phụ thuộc, resource và file cấu hình cần thiết vào đầu vào theo cách ứng dụng sử dụng chúng. Việc tạo image thành công không chứng minh mọi dependency được tải động đã được đưa vào; cần kiểm tra các plugin, driver và tên lớp được đọc từ cấu hình.

Khi không truyền **--runtime-image**, jpackage tạo runtime bằng jlink. Với ứng dụng không modular, runtime được tạo theo tập module JDK dành cho ứng dụng chạy trên class path; có thể bổ sung module nếu ứng dụng cần.

## 5. Tạo application image cho ứng dụng modular

Với ứng dụng modular, cung cấp module path và main module:

~~~bash
jpackage --type app-image \
  --name OrderDesk \
  --module-path mods \
  --module com.example.order/com.example.order.Main \
  --dest dist
~~~

Trong ví dụ:

- **mods** chứa modular JAR hoặc module đã biên dịch.
- **com.example.order** là tên module chính.
- **com.example.order.Main** là lớp main.
- jpackage gọi jlink để tạo runtime image gồm module chính và các dependency module bắc cầu của nó.

Ứng dụng modular giúp mô tả dependency rõ ràng trong module-info.java. Tuy nhiên, dependency được tải bằng reflection, plugin hoặc cấu hình chuỗi vẫn cần được kiểm tra riêng.

Nếu cần bổ sung module JDK mà phân tích tự động chưa xác định được, dùng **--add-modules**:

~~~bash
jpackage --type app-image \
  --name OrderDesk \
  --module-path mods \
  --module com.example.order/com.example.order.Main \
  --add-modules java.sql,java.naming \
  --dest dist
~~~

Chỉ thêm module mà ứng dụng thực sự cần. Runtime nhỏ hơn có thể giảm dung lượng phân phối, nhưng thiếu module sẽ khiến ứng dụng lỗi khi đi vào đường code cần module đó.

## 6. Dùng runtime image tự tạo khi cần kiểm soát nhiều hơn

Runtime mặc định của jpackage phù hợp với nhiều ứng dụng. Nếu cần chọn module cụ thể, thêm thành phần runtime hoặc tái sử dụng một runtime đã kiểm thử, có thể tạo runtime image bằng **jlink** trước.

Ví dụ với ứng dụng modular:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.order,java.sql,java.naming \
  --output runtime-image
~~~

Trên Windows, module path dùng dấu phân cách của hệ điều hành:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.order,java.sql,java.naming --output runtime-image
~~~

Sau đó truyền runtime image cho jpackage:

~~~bash
jpackage --type app-image \
  --name OrderDesk \
  --module-path mods \
  --module com.example.order/com.example.order.Main \
  --runtime-image runtime-image \
  --dest dist
~~~

**--runtime-image** phải trỏ tới runtime image tương thích được tạo bằng jlink, không phải thư mục cài JDK đầy đủ. Runtime này phải phù hợp với hệ điều hành và kiến trúc mà application image hướng tới.

Nếu ứng dụng sử dụng service provider qua **ServiceLoader**, hãy xác định provider module nào cần có trong runtime. Có thể dùng tùy chọn jlink **--bind-services** thông qua **--jlink-options**, hoặc thêm module provider một cách tường minh. Hành vi mặc định về service binding có thể khác giữa các bản JDK, vì vậy hãy kiểm tra tài liệu của JDK đang dùng và chạy integration test với runtime image thực tế.

## 7. Chạy application image trên Windows

Sau khi build thành công, giả sử output là:

~~~text
dist/
  OrderDesk/
    OrderDesk.exe
    app/
    runtime/
~~~

Có thể chuyển toàn bộ thư mục **OrderDesk** sang máy Windows đích. Người dùng chạy:

~~~powershell
.\dist\OrderDesk\OrderDesk.exe
~~~

Hoặc mở file **OrderDesk.exe** bằng File Explorer.

Không cần cài JDK riêng và không cần cấu hình JAVA_HOME trên máy đích. Launcher dùng runtime đi kèm trong image.

Nếu ứng dụng cần cửa sổ console để nhận input hoặc hiển thị output, hãy cấu hình launcher với tùy chọn phù hợp, chẳng hạn **--win-console**. Ứng dụng desktop GUI thường không cần console launcher.

Khi sao chép image, giữ nguyên toàn bộ thư mục và các file bên trong. Không chỉ sao chép file EXE vì launcher cần file cấu hình, ứng dụng và runtime đi kèm.

## 8. Chạy application image trên Linux

Với cấu trúc:

~~~text
dist/
  OrderDesk/
    bin/
      OrderDesk
    lib/
      app/
      runtime/
~~~

Chuyển toàn bộ thư mục **OrderDesk** sang máy Linux có môi trường tương thích. Chạy:

~~~bash
./dist/OrderDesk/bin/OrderDesk
~~~

Nếu chuyển image bằng công cụ lưu trữ hoặc copy làm mất executable permission, cần khôi phục quyền chạy cho launcher:

~~~bash
chmod +x dist/OrderDesk/bin/OrderDesk
~~~

Thông thường công cụ đóng gói và giải nén phù hợp sẽ giữ quyền file. Hãy kiểm tra quyền thực tế trước khi sửa.

Máy Linux đích vẫn cần những thư viện hệ thống mà JVM hoặc ứng dụng native phụ thuộc vào. Runtime đi kèm không đóng gói kernel, libc, driver đồ họa hoặc mọi thư viện native của hệ điều hành.

## 9. Chạy application image trên macOS

Trên macOS, jpackage tạo application bundle có đuôi **.app**:

~~~text
dist/
  OrderDesk.app/
    Contents/
      Info.plist
      MacOS/
      Resources/
      app/
      runtime/
~~~

Người dùng có thể mở bundle bằng Finder hoặc Terminal:

~~~bash
open dist/OrderDesk.app
~~~

Nếu phân phối cho người dùng khác, cần tính tới chính sách bảo mật macOS. Ứng dụng phân phối rộng rãi thường cần quy trình code signing và notarization phù hợp để Gatekeeper xác minh. Việc bundle chứa runtime Java không tự động ký hoặc notarize toàn bộ ứng dụng.

Không chỉnh sửa tùy tiện các file nội bộ sau khi ký, vì thay đổi nội dung bundle có thể làm chữ ký không còn hợp lệ.

## 10. Application image không phải installer

**--type app-image** chỉ tạo application image. Nó không tự cài ứng dụng vào thư mục hệ thống, tạo shortcut, thêm Start Menu entry hoặc quản lý uninstall như một installer native.

| Kiểu đầu ra | Kết quả |
| --- | --- |
| **app-image** | Thư mục ứng dụng có launcher và runtime |
| **msi**, **exe** | Gói cài đặt Windows |
| **deb**, **rpm** | Gói cài đặt Linux |
| **pkg**, **dmg** | Gói phân phối macOS |

Nếu chỉ cần chạy thử hoặc phân phối ứng dụng dưới dạng thư mục, application image là đủ. Nếu cần quy trình cài đặt và gỡ cài đặt quen thuộc với người dùng, có thể dùng application image làm cơ sở tạo installer native trên nền tảng tương ứng.

Application image vẫn có thể chạy mà không qua installer. Người dùng chỉ cần giải nén hoặc đặt thư mục ở vị trí phù hợp rồi chạy launcher.

## 11. Không thể dùng một image cho mọi hệ điều hành

Launcher native và runtime image phụ thuộc nền tảng. Application image tạo trên Windows không phải image chạy trực tiếp trên Linux hoặc macOS.

Cần build riêng cho từng nền tảng đích:

| Nền tảng đích | Cách build |
| --- | --- |
| Windows | Chạy jpackage trên Windows với JDK và kiến trúc phù hợp |
| Linux | Chạy jpackage trên Linux tương ứng |
| macOS | Chạy jpackage trên macOS tương ứng |

Ngoài hệ điều hành, cần quan tâm kiến trúc CPU như x64 hoặc ARM64 và mức tương thích của hệ thống. Một image Linux được tạo trên distro mới có thể phụ thuộc thư viện hệ thống mới hơn so với máy Linux cũ.

Nếu phát hành cho nhiều hệ điều hành hoặc kiến trúc, hãy tạo artifact riêng và kiểm thử trên máy sạch đại diện cho từng nhóm mục tiêu. Tài liệu jpackage xác nhận không có cross-platform packaging: mỗi định dạng phải được build trên nền tảng mà nó chạy.

## 12. Runtime đi kèm không bao gồm mọi dependency bên ngoài

Application image đóng gói Java runtime và nội dung ứng dụng mà jpackage nhận được. Nó không tự động cài mọi phần mềm mà ứng dụng cần ở cấp hệ điều hành.

Ví dụ các dependency cần kiểm tra riêng:

- Native library được gọi qua JNI hoặc FFM.
- DLL, shared object hoặc dynamic library của bên thứ ba.
- Driver đồ họa hoặc thư viện hệ thống.
- Database server hoặc dịch vụ mạng bên ngoài.
- File cấu hình, chứng thư, dữ liệu và resource không nằm trong input.
- Quyền truy cập thư mục, registry, thiết bị hoặc socket của hệ điều hành.

Nếu ứng dụng dùng JavaFX hoặc thư viện native khác, hãy đóng gói đúng module, native library và resource cho nền tảng đích. Không thể lấy một thư viện native Windows đặt vào image Linux rồi mong nó hoạt động.

Đặc biệt, hãy kiểm tra dependency được nạp động qua reflection, ServiceLoader hoặc cấu hình. Runtime image có thể thiếu module hoặc provider nếu dependency đó không được thể hiện trong phân tích tĩnh.

## 13. Kiểm tra image trước khi phân phối

Sau khi tạo application image, thực hiện kiểm tra theo thứ tự:

1. Xác nhận thư mục đích chứa launcher và runtime.
2. Chạy launcher trên máy build để kiểm tra image cơ bản.
3. Chép toàn bộ image sang máy sạch không có JDK/JRE.
4. Chạy launcher bằng user thường, không dùng quyền administrator/root nếu ứng dụng không yêu cầu.
5. Kiểm tra log, cấu hình, resource và dữ liệu mà ứng dụng cần.
6. Kích hoạt các tính năng dùng reflection, plugin, ServiceLoader và native library.
7. Kiểm tra kết nối database, file system, network và các dịch vụ ngoài.
8. Thử cập nhật hoặc thay thế image theo quy trình phát hành.
9. Kiểm thử riêng từng OS và kiến trúc được hỗ trợ.

Có thể dùng lệnh kiểm tra version runtime đi kèm để chẩn đoán khi cần, nhưng đường dẫn nội bộ runtime là chi tiết triển khai. Không nên yêu cầu người dùng cài hoặc chạy một JDK ngoài chỉ để khởi động application image.

## 14. Lỗi thường gặp khi chạy trên máy không có JDK

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy lệnh java | Người dùng đang chạy JAR trực tiếp thay vì launcher của image | Chạy launcher được jpackage tạo |
| Launcher không khởi động | Thiếu file trong application image hoặc chỉ copy riêng launcher | Phân phối toàn bộ thư mục image |
| Lỗi thiếu module | Runtime image chưa có module mà ứng dụng cần | Bổ sung bằng --add-modules hoặc tạo runtime image phù hợp |
| Không tìm thấy plugin/provider | Plugin không được đóng gói hoặc service provider module chưa được liên kết | Kiểm tra cấu hình, module path và service binding |
| Lỗi UnsatisfiedLinkError | Thiếu native library hoặc sai kiến trúc | Đóng gói đúng thư viện native cho OS/CPU đích |
| Linux báo Permission denied | Launcher mất executable permission hoặc thư mục không cho phép chạy | Kiểm tra mount và quyền execute |
| macOS chặn ứng dụng | Chữ ký hoặc notarization chưa đáp ứng chính sách phân phối | Hoàn thiện quy trình signing/notarization |
| Chạy được trên máy build nhưng lỗi trên máy sạch | Máy build có dependency ngoài mà image chưa đóng gói | Kiểm thử trên máy sạch và kiểm kê dependency |
| Ứng dụng lỗi trên OS cũ | Runtime hoặc native dependency cần phiên bản hệ điều hành mới hơn | Xác định baseline hỗ trợ và build/test trên baseline đó |

Không nên xử lý lỗi bằng cách yêu cầu người dùng cài một JDK bất kỳ ngay lập tức. Trước hết hãy xác định launcher đang sử dụng runtime đi kèm hay không, sau đó kiểm tra module, resource và native dependency bị thiếu.

## 15. Checklist phát hành application image

- [ ] Đã chọn đúng OS và kiến trúc đích.
- [ ] Đã tạo image bằng **--type app-image**.
- [ ] Image có launcher và thư mục runtime.
- [ ] Đã đóng gói đủ JAR, module, resource và cấu hình.
- [ ] Đã xác định các module cần thiết cho ứng dụng.
- [ ] Đã kiểm tra ServiceLoader và plugin provider nếu có.
- [ ] Đã đóng gói native library đúng nền tảng.
- [ ] Đã thử chạy bằng launcher trên máy không có JDK/JRE riêng.
- [ ] Đã kiểm thử với user thường và quyền filesystem thực tế.
- [ ] Đã xác minh yêu cầu signing/notarization nếu phân phối trên macOS.
- [ ] Đã lưu artifact riêng theo OS, kiến trúc và phiên bản ứng dụng.

## 16. Kết luận

Application image của jpackage là một thư mục ứng dụng có launcher native, file cấu hình, nội dung ứng dụng và Java runtime được đóng gói cùng. Nếu không truyền runtime image riêng, jpackage dùng jlink để tạo runtime phù hợp. Người dùng chỉ cần chạy launcher trong image, không cần cài riêng JDK hoặc JRE và không cần cấu hình JAVA_HOME để khởi động ứng dụng.

Máy đích vẫn phải tương thích với hệ điều hành và kiến trúc của image, đồng thời có các thư viện native hoặc dịch vụ bên ngoài mà ứng dụng cần. Application image không phải installer và không phải artifact đa nền tảng. Hãy build riêng cho từng nền tảng, chuyển nguyên thư mục image, kiểm thử trên máy sạch và xác nhận các dependency tĩnh lẫn dependency được tải động trước khi phát hành.

## Tài liệu tham khảo

- [Packaging Overview — Java SE 16](https://docs.oracle.com/en/java/javase/16/jpackage/packaging-overview.html)
- [The jpackage Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Packaging Overview — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html)
- [The jpackage Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Image and Runtime Modifications — Java SE 25](https://docs.oracle.com/en/java/javase/25/jpackage/image-and-runtime-modifications.html)
- [The jlink Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)

