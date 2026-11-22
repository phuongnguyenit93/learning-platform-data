# Compression trong jlink

**jlink** là công cụ của JDK dùng để liên kết các module cùng dependency của chúng thành một custom runtime image. Plugin **compress** điều khiển cách nén resource trong image đầu ra, giúp giảm dung lượng phân phối hoặc lưu trữ runtime. Tùy chọn này có thể tác động đến kích thước image và chi phí CPU khi resource được sử dụng, vì vậy nên đo trên workload thực tế.

Compression của jlink áp dụng cho resource trong **runtime image** do jlink tạo. Nó không phải là tùy chọn nén một JAR ứng dụng bất kỳ, không thay thế ZIP/JAR compression, và không tự loại bỏ module khỏi image. Muốn giảm module phải chọn root module phù hợp và xem xét dependency graph; muốn giảm dữ liệu locale, debug hoặc tài liệu phải dùng các tùy chọn tương ứng.

## 1. Compression trong quy trình tạo runtime image

Một ứng dụng modular thường có source hoặc module JAR/JMOD làm đầu vào. jlink phân giải các module được chọn, thêm dependency cần thiết, rồi tạo runtime image chứa launcher, thư viện runtime và các module cần thiết.

Quy trình tổng quát:

~~~text
Module path
   |
   +-- application module
   +-- dependency modules
   +-- JDK modules
          |
          v
     jlink resolution
          |
          v
     runtime image
       - java launcher
       - linked modules
       - runtime resources
       - compression / other plugins
~~~

Tùy chọn **--compress** điều khiển plugin compress trong giai đoạn tạo image. Nó có thể giảm dung lượng resource được lưu trong image. Khi chạy, runtime vẫn sử dụng nội dung resource theo định dạng mà JVM và image hỗ trợ; ứng dụng không cần tự giải nén thư mục image trước khi khởi động.

Compression là một trong nhiều cách tối ưu image. Kết quả còn phụ thuộc vào số module, resource được đóng gói, locale data, debug metadata, service binding và các plugin khác.

## 2. Cú pháp compression trên JDK hiện đại

Theo tài liệu JDK 26, cú pháp hiện tại là:

~~~bash
jlink --compress=zip-N
~~~

Trong đó N là mức từ 0 đến 9:

| Tùy chọn | Ý nghĩa |
|---|---|
| --compress=zip-0 | Không nén resource |
| --compress=zip-1 | ZIP compression ở mức 1 |
| --compress=zip-6 | ZIP compression ở mức 6; mặc định hiện tại |
| --compress=zip-9 | Mức nén cao nhất trong dải được hỗ trợ |

Các giá trị zip-1 đến zip-9 là mức ZIP compression. Mức càng cao hướng tới tỷ lệ nén tốt hơn, nhưng có thể tăng thời gian tạo image hoặc chi phí CPU liên quan. Mức 0 không nén. Mặc định của JDK 26 là zip-6. Hãy kiểm tra tài liệu đúng phiên bản JDK đang dùng thay vì giả định mọi bản jlink có cùng cú pháp.

Có thể xem phiên bản công cụ và các plugin khả dụng:

~~~bash
jlink --version
jlink --list-plugins
jlink --help
~~~

Tùy chọn **--list-plugins** đặc biệt hữu ích khi script build cần chạy trên nhiều JDK release, bởi plugin và cú pháp của chúng có thể thay đổi theo phiên bản.

## 3. Khác biệt cú pháp giữa JDK cũ và JDK mới

Các bản JDK cũ, ví dụ JDK 21, dùng cú pháp số:

~~~bash
jlink --compress=0
jlink --compress=1
jlink --compress=2
~~~

Ý nghĩa legacy:

| Cú pháp cũ | Ý nghĩa cũ |
|---|---|
| --compress=0 | Không nén |
| --compress=1 | Constant string sharing |
| --compress=2 | ZIP compression |

Tài liệu JDK 26 đánh dấu các giá trị số này là deprecated và đưa ra cú pháp mới:

| Giá trị legacy | Cách dùng mới được tài liệu gợi ý |
|---|---|
| --compress=0 | --compress=zip-0 |
| --compress=1 | Constant string sharing legacy; không được đồng nhất với zip-1 |
| --compress=2 | --compress=zip-6 |

**Điểm dễ nhầm:** trên JDK 26, **--compress=1** legacy có nghĩa constant string sharing, còn **--compress=zip-1** là ZIP compression mức 1. Hai tùy chọn không tương đương. Tương tự, **--compress=2** legacy là ZIP compression, trong khi **--compress=zip-2** chỉ là mức ZIP 2.

Khi duy trì build script cho nhiều thế hệ JDK:

1. Xác định JDK thực tế dùng để chạy jlink.
2. Kiểm tra **jlink --help** và **jlink --list-plugins**.
3. Chọn cú pháp phù hợp với phiên bản được pin trong build.
4. Không thay số bằng chuỗi zip-N theo phép thay thế tự động.
5. Tạo image và chạy smoke test sau khi thay đổi tùy chọn.

Tài liệu Oracle JDK 21 mô tả các giá trị 0/1/2 cũ; tài liệu Oracle JDK 26 mô tả zip-0 đến zip-9 và trạng thái deprecated của giá trị số.

## 4. Chọn mức nén theo mục tiêu

Mức nén phù hợp phụ thuộc vào cách phân phối image và môi trường chạy:

| Mục tiêu | Lựa chọn để thử | Lý do |
|---|---|---|
| Ưu tiên tạo image đơn giản, không nén resource | zip-0 | Không thực hiện ZIP compression |
| Cân bằng kích thước và chi phí | zip-6 | Mức mặc định của JDK 26 |
| Ưu tiên giảm dung lượng image | zip-9 | Mức nén cao nhất được tài liệu hỗ trợ |
| Muốn so sánh hiệu năng và dung lượng | Tạo nhiều image với zip-0, zip-6 và zip-9 | Đo trên cùng module graph và workload |

Không có một mức tối ưu cho mọi ứng dụng. Resource dạng text thường có thể nén tốt; resource đã nén sẵn như ảnh JPEG, font hoặc archive khác có thể giảm ít hơn. Image có nhiều class và resource cũng có đặc tính khác với image nhỏ chỉ chứa một vài module.

Không nên kết luận chỉ dựa vào kích thước image. Hãy so sánh ít nhất:

- Dung lượng image trên đĩa.
- Thời gian jlink tạo image.
- Thời gian khởi động ứng dụng.
- CPU và thời gian truy cập resource trong workload đại diện.
- Dung lượng khi đóng gói image thành installer hoặc archive để phân phối.

## 5. Tạo runtime image với compression

Giả sử module ứng dụng đã được biên dịch vào thư mục mods và có tên com.acme.app. Module path cần chứa cả các module ứng dụng và các JDK modules cần thiết.

Trên Linux/macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --launcher app=com.acme.app/com.acme.app.Main --compress=zip-6 --output runtime
~~~

Trên Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.app --launcher app=com.acme.app/com.acme.app.Main --compress=zip-6 --output runtime
~~~

Giải thích:

- **--module-path** chỉ định nơi jlink tìm các module. JDK thường cung cấp module hệ thống trong thư mục jmods.
- **--add-modules** chọn root module; jlink tự thêm các dependency cần thiết theo module graph.
- **--launcher** tạo launcher có tên app trỏ tới module và main class.
- **--compress=zip-6** bật ZIP compression mức 6.
- **--output runtime** đặt runtime image được tạo trong thư mục runtime.

Thư mục output phải phù hợp với yêu cầu của jlink; nếu đã tồn tại, hãy dùng một thư mục mới hoặc làm sạch output theo quy trình build trước khi tạo lại. Không trỏ output vào thư mục JDK đang cài hoặc thư mục chứa dữ liệu không liên quan.

Kiểm tra image:

~~~bash
runtime/bin/java --version
runtime/bin/java --list-modules
runtime/bin/app
~~~

Trên Windows, executable/launcher nằm trong runtime\bin. Tên và phần mở rộng launcher phụ thuộc nền tảng. Nếu không tạo launcher riêng, có thể chạy module bằng runtime Java executable:

~~~bash
runtime/bin/java --module com.acme.app/com.acme.app.Main
~~~

Runtime image được tạo cho nền tảng và kiến trúc mà jlink đang chạy. Thông thường, cần tạo image riêng cho từng hệ điều hành/kiến trúc đích bằng JDK phù hợp.

## 6. Compression filter

Plugin compress cho phép thêm filter để chỉ định pattern của resource được nén:

~~~bash
jlink --compress=zip-6:filter=pattern-list
~~~

Filter là danh sách pattern phân tách bằng dấu phẩy. Tài liệu jlink hỗ trợ các dạng:

- Glob pattern.
- **glob:** theo sau là glob pattern.
- **regex:** theo sau là regular expression.
- **@filename** để đọc các pattern từ file, mỗi dòng một pattern.

Ví dụ minh họa chọn resource theo phần mở rộng:

~~~bash
jlink --compress=zip-6:filter=glob:**.properties,glob:**.xml
~~~

Pattern cụ thể phải được kiểm tra với đường dẫn resource trong image. Filter là điều kiện chọn resource áp dụng compression; nó không có nghĩa là xóa các file không khớp khỏi runtime image. Các resource không được chọn vẫn thuộc image theo cách xử lý mặc định của plugin.

Có thể kiểm tra plugin trên JDK hiện tại:

~~~bash
jlink --list-plugins
~~~

Và xem toàn bộ tùy chọn bằng:

~~~bash
jlink --help
~~~

Dùng filter khi có lý do rõ ràng, chẳng hạn muốn nén nhóm resource text nhưng giữ nhóm file khác ở dạng không nén. Trước khi áp dụng cho production, hãy kiểm tra image và chạy ứng dụng để xác nhận resource được tìm thấy bình thường.

## 7. Compression không thay thế việc giảm module

Compression làm giảm dung lượng resource được lưu trong image. Nó không loại bỏ module không cần thiết. Để giảm footprint, cần xác định module ứng dụng thực sự sử dụng.

Ví dụ:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --compress=zip-6 --output runtime
~~~

jlink sẽ liên kết com.acme.app và các dependency cần thiết. Nếu ứng dụng kéo theo module không mong muốn qua service binding hoặc dependency, cần xem lại module graph và cách chọn module.

Các tùy chọn liên quan:

| Tùy chọn | Vai trò |
|---|---|
| --add-modules | Chọn root modules được đưa vào image |
| --limit-modules | Giới hạn tập module có thể quan sát trong quá trình resolution |
| --bind-services | Liên kết service provider modules và dependency của chúng |
| --include-locales | Giới hạn locale data được đưa vào image |
| --no-header-files | Loại header files |
| --no-man-pages | Loại man pages |
| --strip-debug | Loại debug information khỏi output image |
| --compress | Nén resource trong output image |

Mỗi tùy chọn tác động đến thành phần khác nhau. Nếu mục tiêu là image nhỏ hơn, nên kiểm tra module graph trước, sau đó mới so sánh compression và các plugin loại bỏ thành phần không cần thiết.

## 8. Kết hợp compression với các plugin khác

jlink cung cấp một số plugin có thể dùng cùng compression. Ví dụ:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --strip-debug --no-header-files --no-man-pages --compress=zip-6 --output runtime
~~~

Ý nghĩa:

- **--strip-debug** loại debug information khỏi runtime image.
- **--no-header-files** không đưa header files vào image.
- **--no-man-pages** không đưa man pages vào image.
- **--compress=zip-6** nén resource còn lại theo mức ZIP 6.

Không nên bật tất cả tùy chọn tối ưu theo thói quen. Nếu môi trường cần header files, man pages hoặc debug information cho mục đích vận hành, hãy giữ lại chúng. Hãy đo tác động của từng thay đổi để biết plugin nào thực sự giúp giảm dung lượng.

### Giới hạn locale data

Nếu ứng dụng chỉ cần một tập locale nhất định, có thể giảm locale data bằng plugin include-locales. Ví dụ:

~~~bash
jlink --add-modules com.acme.app,jdk.localedata --include-locales=en,vi --compress=zip-6 --output runtime
~~~

Khi dùng **--include-locales**, cần thêm module jdk.localedata. Danh sách locale phải phản ánh nhu cầu thực tế của ứng dụng; thiếu locale có thể làm định dạng ngày, số hoặc thông điệp theo locale không hoạt động như mong đợi.

## 9. Đo và so sánh dung lượng runtime image

Để đánh giá compression, tạo nhiều image từ cùng module path và cùng root modules. Chỉ thay đổi mức nén giữa các lần build.

Ví dụ trên Linux/macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --compress=zip-0 --output runtime-zip0
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --compress=zip-6 --output runtime-zip6
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.app --compress=zip-9 --output runtime-zip9

du -sh runtime-zip0 runtime-zip6 runtime-zip9
~~~

Trên Windows PowerShell, có thể tính tổng kích thước file:

~~~powershell
Get-ChildItem runtime-zip0 -Recurse -File | Measure-Object -Property Length -Sum
Get-ChildItem runtime-zip6 -Recurse -File | Measure-Object -Property Length -Sum
Get-ChildItem runtime-zip9 -Recurse -File | Measure-Object -Property Length -Sum
~~~

Ghi lại kết quả vào bảng:

| Image | Compression | Dung lượng | Thời gian tạo | Startup / workload |
|---|---|---:|---:|---|
| runtime-zip0 | zip-0 | Đo thực tế | Đo thực tế | Đo thực tế |
| runtime-zip6 | zip-6 | Đo thực tế | Đo thực tế | Đo thực tế |
| runtime-zip9 | zip-9 | Đo thực tế | Đo thực tế | Đo thực tế |

Không điền số liệu ước lượng thay cho kết quả đo. Dùng cùng máy build, cùng JDK, cùng input modules và cùng cấu hình để phép so sánh có ý nghĩa.

Khi đo startup, hãy chạy mỗi image nhiều lần trong điều kiện tương đương. Tách biệt lần chạy đầu có thể chịu ảnh hưởng của cache hệ điều hành với các lần chạy tiếp theo. Nếu ứng dụng đọc resource nhiều, hãy đưa thao tác đó vào workload benchmark.

## 10. Kiểm tra tính đúng đắn sau khi nén

Sau khi tạo image, kiểm tra các khía cạnh sau:

1. **Image tồn tại**: xác nhận thư mục output chứa launcher và cấu trúc runtime.
2. **Runtime version**: chạy executable java bên trong image để xác nhận đúng runtime.
3. **Module list**: dùng --list-modules để kiểm tra module đã liên kết.
4. **Launcher**: chạy launcher hoặc module entry point.
5. **Resource**: kiểm tra ứng dụng đọc được properties, XML, template, locale và resource khác.
6. **Service loading**: kiểm tra các service provider cần thiết được resolve và hoạt động.
7. **Native library**: xác nhận thư viện native phù hợp nền tảng và kiến trúc.
8. **Workload**: chạy smoke test và integration test đại diện.

Compression không nên làm thay đổi logic của ứng dụng. Nếu ứng dụng thất bại sau khi tạo image, hãy kiểm tra module graph, resource filtering, service binding và khác biệt giữa runtime image với JDK đầy đủ trước khi kết luận do compression.

## 11. Các lỗi và hiểu nhầm thường gặp

| Hiện tượng / hiểu nhầm | Nguyên nhân hoặc cách hiểu đúng |
|---|---|
| jlink báo invalid compression value | Cú pháp thay đổi theo JDK; kiểm tra jlink --help và --list-plugins |
| Dùng --compress=1 trên JDK mới nhưng mong ZIP level 1 | Giá trị legacy 1 là constant string sharing; ZIP level 1 dùng zip-1 |
| Image không nhỏ hơn nhiều | Resource đã nén sẵn hoặc phần dung lượng chính nằm ở module/class/native library |
| Nghĩ --compress loại bỏ module | Compression chỉ nén resource; chọn module bằng --add-modules và --limit-modules |
| Runtime không tìm thấy resource sau build | Filter hoặc cấu hình đóng gói cần được kiểm tra; xác minh entry/resource thực tế |
| Image chạy được trên máy build nhưng không chạy trên máy đích | Khác OS, CPU architecture, native library hoặc cấu hình runtime |
| Chỉ kiểm tra kích thước thư mục | Cần kiểm tra startup, workload, resource và service behavior |
| Dùng --strip-debug làm thay đổi compression | Đây là plugin khác, loại debug metadata; hãy đo riêng từng tác động |
| Image cũ không nhận security update tự động | Developer phải tạo và phân phối lại custom runtime image từ JDK đã cập nhật |

## 12. Quy trình lựa chọn compression cho dự án

1. Xác định JDK release được pin trong pipeline tạo runtime image.
2. Chạy jlink --list-plugins để xác nhận cú pháp compress.
3. Xác định module root và dependency cần thiết cho ứng dụng.
4. Tạo image baseline không nén hoặc dùng mức nén mặc định.
5. Tạo các image thử nghiệm với zip-0, zip-6 và zip-9 nếu JDK hỗ trợ cú pháp mới.
6. So sánh dung lượng, thời gian tạo, startup và workload.
7. Chỉ dùng filter khi có pattern resource cụ thể và đã kiểm thử.
8. Kết hợp các plugin khác như strip-debug, include-locales hoặc no-man-pages khi phù hợp.
9. Chạy smoke test và integration test trên chính runtime image sẽ phát hành.
10. Lưu lại JDK version, lệnh jlink và kết quả đo để có thể tái tạo image.

## 13. Bảo trì custom runtime image

Custom runtime image không tự cập nhật như một JDK được cài đặt và cập nhật độc lập. Khi JDK có bản cập nhật bảo mật hoặc sửa lỗi, đội phát triển cần tạo lại image bằng JDK đã cập nhật, chạy test và phát hành image mới.

Nên lưu cùng artifact:

- Phiên bản JDK dùng để tạo image.
- Danh sách module được liên kết.
- Các tùy chọn jlink và plugin.
- Compression level và filter.
- Phiên bản ứng dụng và dependency.
- Hệ điều hành/kiến trúc mục tiêu.
- Kết quả smoke test và benchmark dung lượng.

Compression không mã hóa resource và không phải cơ chế bảo mật. Nếu image chứa secret hoặc dữ liệu nhạy cảm, cần quản lý chúng bằng cơ chế cấu hình và secret management riêng, không nhúng vào runtime image.

## 14. Ghi nhớ

- jlink tạo custom runtime image từ module graph; plugin compress điều khiển nén resource trong image đó.
- JDK 26 dùng --compress=zip-0 đến --compress=zip-9; mặc định là zip-6.
- zip-0 không nén; zip-9 là mức nén cao nhất trong dải hiện tại.
- Cú pháp cũ 0/1/2 được deprecated trong tài liệu JDK 26; giá trị legacy 1 là constant string sharing, không phải ZIP level 1.
- Filter chọn pattern resource được nén; nó không xóa các resource không khớp khỏi image.
- Compression không thay thế việc giảm module, giới hạn locale hoặc strip debug.
- Đo dung lượng, startup và workload trước khi chọn mức nén production.
- Kiểm tra runtime image bằng launcher, --list-modules và test resource/service.
- Developer phải cập nhật và phát hành lại custom runtime image khi JDK nền cần cập nhật.

## Tài liệu tham khảo chính thức

- [jlink Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [jlink Command — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [Module jdk.jlink — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jlink/module-summary.html)