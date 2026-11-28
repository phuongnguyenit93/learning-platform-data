# Cập nhật runtime đi kèm khi JDK có bản vá và phát hành lại ứng dụng

Ứng dụng được đóng gói cùng Java runtime có thể chạy trên máy người dùng mà không cần cài một JDK riêng. Đổi lại, nhóm phát triển chịu trách nhiệm cập nhật runtime đó khi nhà cung cấp phát hành bản vá bảo mật hoặc sửa lỗi. Cập nhật JDK trên máy build không làm thay đổi runtime đã nằm trong các gói ứng dụng đã phát hành.

Quy trình đúng là tạo runtime image mới từ JDK đã được cập nhật, đóng gói lại ứng dụng, kiểm thử image mới trên từng nền tảng, ký và phát hành phiên bản package mới. Bài học tập trung vào jpackage, jlink và cách quản lý vòng đời runtime image trên các JDK hiện đại.

## 1. Runtime đi kèm là một phần của sản phẩm

Một application image do jpackage tạo thường có launcher, nội dung ứng dụng và thư mục runtime:

~~~text
ReportTool/
├── bin/
│   └── ReportTool
├── app/
│   ├── ReportTool.cfg
│   └── report-tool.jar
└── runtime/
    ├── bin/
    │   └── java
    ├── lib/
    └── release
~~~

Thư mục runtime là Java runtime được đóng gói để launcher sử dụng. Khi người dùng mở ứng dụng, launcher chạy runtime này thay vì tự động chọn JDK đang cài toàn hệ thống.

Điều đó có hai hệ quả:

- Cập nhật JDK trên máy lập trình hoặc CI không sửa các application image đã tạo trước đó.
- Người dùng chỉ nhận được bản vá runtime khi cài một package/application image mới có chứa runtime đã cập nhật, hoặc khi ứng dụng được thiết kế rõ ràng để dùng runtime do tổ chức quản lý riêng.

Với mô hình self-contained, runtime đi kèm là thành phần cần được quản lý, kiểm kê, kiểm thử và phát hành như các thư viện phụ thuộc khác của ứng dụng.

## 2. jpackage tạo runtime mới hay sao chép runtime có sẵn?

jpackage có hai cách nhận Java runtime:

| Cách đóng gói | Hành vi |
|---|---|
| Không chỉ định --runtime-image | jpackage gọi jlink để tạo runtime image từ JDK dùng cho quá trình đóng gói |
| Có chỉ định --runtime-image | jpackage sao chép runtime image đã được tạo trước vào application image |

Đây là điểm quyết định trong quy trình vá runtime. Nếu build pipeline truyền một runtime image cũ qua --runtime-image, việc nâng JDK cài trên máy build không làm runtime cũ được cập nhật. Pipeline phải dựng lại runtime image rồi truyền đúng đường dẫn image mới.

### Cách 1: để jpackage tạo runtime

Ví dụ với ứng dụng classpath:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --main-class com.example.ReportTool \
    --dest build/packages
~~~

Khi chạy lệnh bằng jpackage thuộc JDK đã được cập nhật, công cụ dùng jlink của bộ JDK đó để tạo runtime image mới. Đây là cách đơn giản nếu runtime mặc định do jpackage tạo đã chứa đủ module cho ứng dụng.

### Cách 2: tự tạo runtime bằng jlink

Khi cần kiểm soát module hoặc tùy chọn runtime, hãy gọi jlink riêng:

~~~text
jlink \
    --module-path "$JDK_HOME/jmods" \
    --add-modules java.base,java.logging,java.sql \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --output build/runtime
~~~

Sau đó đưa runtime image vừa tạo vào jpackage:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --main-class com.example.ReportTool \
    --runtime-image build/runtime \
    --dest build/packages
~~~

Trong pipeline cập nhật, JDK_HOME phải trỏ tới JDK distribution đã nhận bản vá. Không dùng lại thư mục runtime cũ chỉ vì tên đường dẫn không đổi.

Danh sách module trong ví dụ chỉ minh họa. Ứng dụng thực tế phải thêm mọi module cần cho thư viện, tính năng, provider và tích hợp mà nó sử dụng.

## 3. Quy trình cập nhật runtime khi có bản vá JDK

Một quy trình có thể lặp lại nên gồm các bước:

1. **Nhận diện runtime đang phát hành:** ghi lại nhà cung cấp, phiên bản đầy đủ, build number, kiến trúc và module của runtime hiện tại.
2. **Đánh giá bản cập nhật:** đọc thông báo bảo mật và release notes của nhà cung cấp JDK; xác định mức độ ảnh hưởng, thời hạn cần phát hành và thay đổi tương thích.
3. **Chọn JDK đã vá:** tải đúng bản phân phối và build được tổ chức chấp nhận, xác minh nguồn tải và checksum/signature theo chính sách.
4. **Dựng runtime mới:** chạy jpackage để nó gọi jlink, hoặc chạy jlink riêng rồi truyền image mới qua --runtime-image.
5. **Kiểm tra runtime:** xác minh phiên bản, module, kiến trúc và các file runtime được tạo.
6. **Kiểm thử ứng dụng:** chạy test, smoke test, tích hợp, native integration và các tác vụ quan trọng trên image mới.
7. **Đóng gói lại:** tạo application image và installer mới cho từng nền tảng được hỗ trợ.
8. **Ký và phát hành:** ký lại artifact đã thay đổi, tạo checksum, cập nhật metadata phiên bản và phân phối package mới.
9. **Theo dõi triển khai:** xác nhận người dùng hoặc hệ thống triển khai đã cài bản mới; duy trì quy trình rollback theo chính sách sản phẩm.

Không nên xem việc thay một vài file trong thư mục runtime của package đã cài là một bản cập nhật hoàn chỉnh. Runtime image gồm nhiều thành phần liên quan với nhau; hãy tạo lại image từ bộ JDK nhất quán để kết quả có thể tái lập.

## 4. Ghi lại nguồn gốc của runtime image

Khi cần phát hành bản vá, trước tiên phải biết runtime đang có nguồn gốc từ đâu. Nên lưu các thông tin sau trong build metadata hoặc hồ sơ phát hành:

| Thông tin | Ví dụ |
|---|---|
| Nhà cung cấp JDK | Nhà cung cấp đã được tổ chức phê duyệt |
| Phiên bản đầy đủ | Kết quả java --version |
| Build number | Build number trong version string hoặc release metadata |
| Hệ điều hành và kiến trúc | Windows x64, Linux AArch64, macOS AArch64 |
| Module được liên kết | Kết quả java --list-modules |
| Tùy chọn jlink | Danh sách module và plugin đã dùng |
| Phiên bản ứng dụng | Version của artifact và installer |
| Nguồn đầu vào | JDK archive/image, checksum và build pipeline |

Runtime image có file release chứa metadata của runtime. Có thể kiểm tra nhanh bằng:

~~~text
cat build/runtime/release
~~~

Trên Windows PowerShell:

~~~powershell
Get-Content build/runtime/release
~~~

Kiểm tra phiên bản Java trong runtime image:

~~~text
build/runtime/bin/java --version
~~~

Kiểm tra module đã được liên kết:

~~~text
build/runtime/bin/java --list-modules
~~~

Trên Windows, thay bin/java bằng bin/java.exe. Khi kiểm tra application image hoàn chỉnh, chạy các lệnh trên đối với thư mục runtime nằm trong image cuối cùng, không chỉ thư mục runtime trung gian.

## 5. Chọn đúng JDK distribution và nền tảng build

Runtime image chứa bytecode, thư viện native và thành phần phụ thuộc nền tảng. Cần dựng và kiểm thử image cho từng hệ điều hành/kiến trúc mà ứng dụng hỗ trợ.

Một quy tắc build an toàn là dùng cùng nhà cung cấp và cùng phiên bản JDK cho công cụ jlink và các module JDK đầu vào. Điều này đặc biệt quan trọng với JDK 26: kiểm tra phiên bản khi cross-link đã chặt hơn; tập module JDK đầu vào phải khớp cả phiên bản lẫn nhà cung cấp với JDK chạy jlink.

jpackage tạo native installer theo nền tảng đích và không hỗ trợ cross-platform packaging. Vì vậy, pipeline nên có build job riêng cho mỗi hệ điều hành/kiến trúc, dùng JDK đã vá phù hợp và kiểm thử artifact ngay trên nền tảng đó.

Ví dụ ma trận:

| Build job | JDK đầu vào | Artifact cần kiểm thử |
|---|---|---|
| Windows x64 | JDK patch đã duyệt cho Windows x64 | Application image và installer Windows x64 |
| Linux x64 | JDK patch đã duyệt cho Linux x64 | Application image và DEB/RPM tương ứng |
| macOS AArch64 | JDK patch đã duyệt cho macOS AArch64 | Application image và PKG/DMG tương ứng |

Không lấy runtime image của Windows để đóng gói cho Linux hoặc ngược lại. Nếu dùng cross-link trong một quy trình chuyên biệt, phải tuân thủ yêu cầu version/vendor của jlink và kiểm thử đầy đủ trên target platform.

## 6. Tạo runtime image mới bằng jlink

Với ứng dụng modular, jlink liên kết main module cùng các module phụ thuộc bắc cầu. Với ứng dụng classpath, cần xác định các module JDK mà ứng dụng và thư viện sử dụng.

Có thể dùng jdeps làm điểm bắt đầu để phân tích dependency:

~~~text
jdeps --multi-release 26 \
    --print-module-deps \
    --class-path "build/input/lib/*" \
    build/input/report-tool.jar
~~~

Thay số 26 bằng phiên bản Java mục tiêu của runtime đang tạo; chỉ dùng tùy chọn này khi cần phân tích phiên bản tương ứng của multi-release JAR. Kết quả jdeps là gợi ý tĩnh, không phải danh sách đảm bảo đầy đủ trong mọi ứng dụng. Reflection, cấu hình provider, JDBC driver, service loading và module được nạp theo tên ở runtime có thể cần bổ sung thủ công.

Sau khi xác định module, tạo runtime:

~~~text
jlink \
    --module-path "$JDK_HOME/jmods" \
    --add-modules java.base,java.logging,java.sql,java.naming \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --output build/runtime
~~~

Để tái lập bản build, lưu lại chính xác:

- Phiên bản đầy đủ và nhà cung cấp của JDK.
- Module path và danh sách --add-modules.
- Các plugin/tùy chọn jlink.
- Hệ điều hành và kiến trúc của runner.
- Phiên bản ứng dụng cùng dependency đầu vào.

Khi nhận bản vá JDK tiếp theo, chạy lại cùng quy trình bằng JDK mới, rồi kiểm tra sự thay đổi của module list và kết quả test.

## 7. Dùng jpackage để tạo runtime mới tự động

Nếu không cần runtime tùy chỉnh riêng, có thể để jpackage chạy jlink:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --main-class com.example.ReportTool \
    --dest build/packages
~~~

Trong CI, cần gọi đúng executable jpackage thuộc JDK đã vá. Trước khi chạy, ghi lại:

~~~text
jpackage --version
jlink --version
java --version
~~~

Các executable nên đến từ cùng JDK distribution. Tránh để PATH trỏ đến JDK khác với biến môi trường mà build script đang dùng.

Nếu cần thêm module:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --main-class com.example.ReportTool \
    --add-modules java.sql,java.naming \
    --dest build/packages
~~~

Đối với ứng dụng modular, jpackage có thể xác định module chính và dependency bắc cầu từ module graph; --add-modules dùng để bổ sung module còn thiếu theo nhu cầu thực tế.

## 8. Lưu ý ServiceLoader khi tạo runtime trên JDK 25 trở lên

Từ JDK 25, runtime image do jpackage tạo không còn tự động bao gồm service bindings như các JDK trước. Nếu ứng dụng phụ thuộc provider module được tìm qua service binding, cần kiểm tra hành vi và thêm tùy chọn --bind-services cho jlink.

Ví dụ khi để jpackage gọi jlink:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --main-class com.example.ReportTool \
    --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services" \
    --dest build/packages
~~~

Nếu tự gọi jlink, truyền --bind-services trực tiếp:

~~~text
jlink \
    --module-path "$JDK_HOME/jmods:build/modules" \
    --add-modules com.example.report \
    --bind-services \
    --output build/runtime
~~~

Ví dụ module-path dùng dấu phân cách của Unix; trên Windows, dùng dấu phân cách path phù hợp nền tảng. Chỉ thêm service binding khi ứng dụng cần provider discovery theo module service configuration. Sau khi đổi JDK build, hãy chạy test cho JDBC, logging provider, serialization provider và các SPI mà ứng dụng thật sự sử dụng.

## 9. Khi jpackage nhận runtime image đã tạo trước

Nếu quy trình sử dụng --runtime-image, trách nhiệm cập nhật nằm ở bước tạo image đó:

~~~text
jlink \
    --module-path "$JDK_HOME/jmods" \
    --add-modules java.base,java.logging,java.sql \
    --output build/runtime-patched

jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --main-class com.example.ReportTool \
    --runtime-image build/runtime-patched \
    --dest build/packages
~~~

Hãy kiểm tra rõ đường dẫn build/runtime-patched được tạo trong cùng pipeline từ JDK đã vá. Một lỗi phổ biến là cập nhật biến JDK_HOME nhưng vẫn truyền đường dẫn runtime image được cache từ lần build cũ.

Nếu cache runtime image để tiết kiệm thời gian, cache key phải chứa tối thiểu:

- Nhà cung cấp JDK.
- Phiên bản đầy đủ/build number của JDK.
- Hệ điều hành và kiến trúc.
- Danh sách module và tùy chọn jlink.
- Các dependency hoặc module đầu vào ảnh hưởng runtime.

Khi bất kỳ thành phần nào thay đổi, phải tạo cache key mới. Không dùng một runtime image cache cũ chỉ dựa vào tên nhánh hoặc phiên bản ứng dụng.

## 10. Kiểm thử runtime mới trước khi phát hành

Không dừng ở việc kiểm tra lệnh đóng gói trả exit code 0. Hãy chạy ứng dụng bằng chính launcher trong application image vừa tạo.

### Kiểm tra phiên bản và module

~~~text
build/packages/ReportTool/runtime/bin/java --version
build/packages/ReportTool/runtime/bin/java --list-modules
~~~

Đối chiếu version string, build, vendor và module list với metadata dự kiến. Trên Windows, executable là java.exe.

### Smoke test launcher

~~~text
build/packages/ReportTool/bin/ReportTool --health-check
~~~

Đây là tham số minh họa; ứng dụng cần có chế độ health check hoặc một lệnh test phù hợp. Bảo đảm launcher sử dụng runtime nằm trong image vừa build, không vô tình gọi java từ PATH.

### Các nhóm kiểm thử nên chạy

| Nhóm | Điều cần xác nhận |
|---|---|
| Startup | Launcher khởi động bằng runtime mới |
| Runtime version | Đúng vendor, version và build đã duyệt |
| Module resolution | Không thiếu module khi chạy |
| Service loading | Provider cần thiết được tìm thấy |
| Native integration | JNI/JNA và thư viện native hoạt động trên target OS/arch |
| TLS và security | Kết nối TLS, chứng thư và thuật toán cần thiết vẫn hoạt động |
| File/config | Đường dẫn, encoding và quyền truy cập vẫn đúng |
| Performance | Startup, memory và workload chính không có hồi quy đáng kể |
| Shutdown | Ứng dụng đóng sạch, không để lại process hoặc lock |

Đối với bản vá bảo mật khẩn cấp, rút ngắn thời gian phát hành nhưng vẫn giữ các test tối thiểu cho startup, giao tiếp mạng, persistence và chức năng cốt lõi.

## 11. Đóng gói lại, ký và phát hành

Runtime image thay đổi làm application image thay đổi. Vì vậy, package mới cần được tạo lại và ký lại theo quy trình phát hành của nền tảng.

Một pipeline điển hình:

~~~text
1. Build application artifacts
2. Resolve approved patched JDK
3. Create runtime image with jlink or jpackage
4. Create application image
5. Run tests against packaged launcher
6. Create native installer
7. Sign/notarize package where required
8. Generate checksums and release metadata
9. Publish the new package
~~~

Giữ ổn định định danh ứng dụng và quy tắc nâng cấp của package để installer mới được nhận diện là bản cập nhật của ứng dụng đã cài. Cách cấu hình cụ thể phụ thuộc định dạng package và hệ điều hành.

Trên macOS, thay đổi runtime hoặc binary trong application bundle cần được ký lại và thực hiện quy trình notarization phù hợp. Trên Windows, ký lại installer/executable theo chính sách phân phối. Trên Linux, tạo lại DEB/RPM và ký repository/package theo cơ chế phát hành của tổ chức nếu có.

Tạo checksum cho artifact cuối cùng và lưu cùng metadata JDK nguồn. Không dùng checksum của application image trước khi ký để đại diện cho package cuối cùng sau khi ký.

## 12. Quản lý phiên bản và khả năng rollback

Một bản phát hành có thể giữ nguyên phiên bản nghiệp vụ nhưng cần phân biệt được runtime patch đã đóng gói. Có thể quản lý:

- Phiên bản ứng dụng.
- Phiên bản JDK đầy đủ.
- Build number và nhà cung cấp.
- Phiên bản package/installer.
- Mã build pipeline hoặc commit nguồn.
- Checksum artifact cuối cùng.

Ví dụ metadata phát hành:

~~~yaml
applicationVersion: 4.8.2
runtime:
  vendor: ApprovedVendor
  version: "26.0.1+8"
  platform: linux-x64
  modules:
    - java.base
    - java.logging
    - java.sql
package:
  type: deb
  buildId: "release-4.8.2-runtime-26.0.1"
~~~

Đây là ví dụ metadata nội bộ, không phải định dạng bắt buộc của jpackage.

Giữ lại package trước đó trong thời gian rollback được cho phép. Nếu bản vá mới có hồi quy, có thể khôi phục package đã duyệt trước đó theo quy trình incident. Tuy nhiên, không nên rollback vô thời hạn về runtime có lỗ hổng đã được công bố; cần cân nhắc mức độ rủi ro và phát hành bản sửa tiếp theo.

## 13. Các lỗi thường gặp khi cập nhật runtime

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ cập nhật JDK trên máy build | Runtime trong package cũ không thay đổi | Tạo lại runtime image và package |
| Dùng lại --runtime-image cũ | Package mới vẫn chứa runtime cũ | Tạo runtime mới rồi truyền đúng đường dẫn |
| Dùng JDK vendor/version không khớp với module đầu vào cho jlink | Link thất bại hoặc không tạo được image đáng tin cậy | Dùng module và toolchain cùng vendor/version |
| Dùng runtime image của hệ điều hành khác | Thiếu hoặc sai native binaries | Build runtime cho từng target OS/arch |
| Chỉ kiểm tra java --version trên máy build | Không chứng minh launcher dùng runtime đã vá | Chạy runtime/bin/java --version trong app image |
| Không kiểm tra module/service binding | Ứng dụng thiếu provider hoặc module khi chạy | Kiểm tra module list và test ServiceLoader |
| Cache runtime không có JDK build trong key | CI có thể tái sử dụng image lỗi thời | Đưa vendor/version/build/OS/arch/module options vào cache key |
| Thay runtime nhưng không ký lại package | Chữ ký không còn hợp lệ hoặc không bao phủ artifact mới | Tạo lại và ký artifact cuối cùng |
| Không chạy integration test trên image đóng gói | Lỗi chỉ xuất hiện trong runtime rút gọn | Test bằng launcher và runtime thật |
| Giữ JDK 16 chỉ vì ứng dụng bắt đầu từ Java 16 | Dùng runtime không còn nằm trong dòng hỗ trợ phù hợp | Chọn JDK đang được nhà cung cấp hỗ trợ và kiểm thử tương thích |

## 14. Java 16 là mốc giới thiệu, không phải phiên bản runtime bắt buộc

jpackage trở thành công cụ đóng gói chuẩn trong JDK 16. Ý tưởng self-contained application và quy trình tạo runtime image vẫn còn áp dụng trên các JDK mới.

Tuy nhiên, không nên hiểu rằng ứng dụng từng được build bằng Java 16 phải tiếp tục đóng gói runtime Java 16. Java 16 là một bản phát hành không phải LTS và đã cũ. Với sản phẩm đang vận hành, hãy chọn một JDK line còn được nhà cung cấp hỗ trợ, nhận bản vá và đáp ứng yêu cầu tương thích của ứng dụng.

Khi nâng runtime lên một JDK mới hơn:

- Giữ baseline bytecode/API phù hợp với yêu cầu tương thích nếu cần hỗ trợ runtime cũ hơn.
- Chạy test trên đúng runtime mới được đóng gói.
- Kiểm tra thay đổi mặc định của JVM, module, service loading và bảo mật.
- Không giả định chỉ thay số phiên bản JDK là đủ cho mọi ứng dụng.

## 15. Checklist phát hành bản vá runtime

- [ ] Đã xác định vendor, version, build và nền tảng của runtime đang phát hành.
- [ ] Đã đọc advisory/release notes của bản JDK cập nhật.
- [ ] Đã chọn JDK distribution đã được phê duyệt và xác minh nguồn tải.
- [ ] jlink và module đầu vào cùng vendor/version theo yêu cầu toolchain.
- [ ] Runtime image mới được tạo trong pipeline hiện tại.
- [ ] Không tái sử dụng runtime cache cũ khi JDK build thay đổi.
- [ ] Đã kiểm tra runtime/bin/java --version.
- [ ] Đã kiểm tra runtime/bin/java --list-modules.
- [ ] Đã kiểm tra service binding nếu ứng dụng dùng ServiceLoader/provider module.
- [ ] Đã chạy smoke test bằng launcher trong application image.
- [ ] Đã chạy test tích hợp trên từng OS/architecture được hỗ trợ.
- [ ] Đã tạo lại application image và native installer.
- [ ] Đã ký/notarize lại artifact theo yêu cầu nền tảng.
- [ ] Đã tạo checksum và lưu metadata nguồn gốc runtime.
- [ ] Đã chuẩn bị kế hoạch rollout và rollback.

## 16. Ghi nhớ

- Runtime được đóng gói cùng ứng dụng không tự cập nhật khi máy build hoặc máy người dùng cài JDK mới.
- jpackage tự gọi jlink nếu không truyền --runtime-image.
- Khi truyền --runtime-image, jpackage chỉ đưa runtime image được chỉ định vào application image.
- Bản vá JDK cần đi qua quy trình dựng runtime mới, đóng gói, kiểm thử, ký và phát hành lại.
- Dùng JDK và module đầu vào nhất quán về vendor/version; JDK 26 kiểm tra cross-link nghiêm ngặt hơn.
- Tạo runtime cho từng OS/architecture; native package cần build trên target platform.
- Kiểm tra phiên bản và module từ chính runtime nằm trong application image.
- JDK 25 trở lên không tự liên kết service bindings trong runtime do jpackage tạo; thêm --bind-services khi ứng dụng cần.
- Giữ metadata nguồn gốc và checksum để có thể kiểm toán, tái lập và rollback.
- Java 16 là mốc jpackage trở thành công cụ chuẩn; sản phẩm hiện tại nên dùng một JDK line còn được hỗ trợ.

Quản lý runtime đi kèm là trách nhiệm phát hành liên tục của ứng dụng. Mỗi khi JDK có bản vá phù hợp, hãy tạo runtime image mới từ toolchain đã duyệt, xác minh nội dung image, kiểm thử bằng launcher thực tế và phát hành lại package đã ký cho từng nền tảng.

## Tài liệu tham khảo

- [The jpackage Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html) — cách jpackage tạo hoặc nhận runtime image.
- [Packaging Overview — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html) — cấu trúc application image, runtime requirements và thay đổi service binding trong JDK 25+.
- [The jlink Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html) — tạo custom runtime image và trách nhiệm cập nhật runtime.
- [JDK 26 Release Notes](https://www.oracle.com/java/technologies/javase/26-relnote-issues.html) — kiểm tra phiên bản nghiêm ngặt hơn khi cross-link bằng jlink.
- [JEP 392: Packaging Tool](https://openjdk.org/jeps/392) — jpackage trở thành công cụ đóng gói chuẩn trong JDK 16.
