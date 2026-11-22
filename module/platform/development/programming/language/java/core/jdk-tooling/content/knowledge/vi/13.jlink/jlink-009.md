# Tối ưu kích thước runtime image với jlink

`jlink` tạo custom runtime image từ các Java module đã được phân giải. Kích thước image phụ thuộc vào những module được đưa vào, dữ liệu đi kèm, thư viện native và các plugin xử lý đầu ra. Muốn giảm dung lượng một cách an toàn, trước tiên cần xác định ứng dụng thực sự cần những module và tài nguyên nào, sau đó áp dụng nén hoặc loại bỏ metadata không cần cho runtime rồi đo lại.

Không có một tùy chọn duy nhất luôn tạo ra image nhỏ nhất cho mọi ứng dụng. Nén mạnh hơn có thể làm tăng chi phí giải nén hoặc đọc tài nguyên; loại debug data có thể gây khó khăn khi điều tra lỗi; bỏ native command có thể khiến image không còn lệnh `java` để khởi chạy thông thường. Vì vậy, mỗi thay đổi cần được đánh giá bằng kích thước và kiểm thử trên image cuối.

## 1. Những thành phần quyết định kích thước image

Một runtime image thường có cấu trúc tương tự:

```text
app-image/
├── bin/
│   ├── java
│   └── app
├── conf/
├── include/
├── legal/
├── lib/
│   ├── modules
│   ├── security/
│   └── server/
└── release
```

Cấu trúc chính xác tùy JDK, hệ điều hành và các tùy chọn link. Những thành phần có thể ảnh hưởng đáng kể đến kích thước:

- **Module Java:** mỗi module được chọn có class file, resource và metadata tương ứng. Các module như `java.sql`, `java.xml`, `java.desktop` hoặc `jdk.localedata` có thể bổ sung nhiều nội dung tùy ứng dụng.
- **Native libraries:** JVM, security provider và thư viện native được đóng gói cho nền tảng mục tiêu.
- **Native commands:** các command trong image, ví dụ `java`, launcher ứng dụng hoặc command được cung cấp bởi module.
- **Locale data:** dữ liệu ngôn ngữ, định dạng số/ngày, collation và các locale khác.
- **Debug information:** thông tin dòng nguồn, biến cục bộ và metadata hỗ trợ gỡ lỗi.
- **Man pages và header files:** tài liệu và header dành cho phát triển native, thường không cần trong runtime image thông thường.
- **Resource:** tệp cấu hình, dữ liệu và tài nguyên của các module.

Trong nhiều image, file `lib/modules` chứa phần lớn nội dung module đã được liên kết. Tuy nhiên, không nên chỉ nhìn kích thước một file; hãy đo toàn bộ thư mục image vì binary, cấu hình, legal notice và các file phụ trợ cũng chiếm dung lượng.

## 2. Bắt đầu bằng image cơ sở và đo kích thước

Giả sử đã có module ứng dụng `com.example.app` trong thư mục `mods`, còn JDK được cài tại `JAVA_HOME`.

Tạo image cơ sở trên Linux/macOS:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output app-image
```

Trên Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output app-image
```

Image output cần có thư mục đích chưa tồn tại hoặc đang rỗng. Khi đo nhiều cấu hình, hãy dùng tên thư mục riêng hoặc dọn đúng thư mục build trước khi chạy lại.

Đo dung lượng trên Linux/macOS:

```sh
du -sh app-image
du -ah app-image | sort -h | tail -20
```

Lệnh đầu cho biết tổng dung lượng thư mục theo cách hiển thị của hệ thống. Lệnh sau giúp tìm các tệp/thư mục lớn nhất để biết phần nào chiếm nhiều dung lượng.

Đo bằng PowerShell:

```powershell
$bytes = (Get-ChildItem .\app-image -Recurse -File |
    Measure-Object -Property Length -Sum).Sum
"{0:N2} MB" -f ($bytes / 1MB)
```

Có thể kiểm tra riêng các tệp lớn:

```powershell
Get-ChildItem .\app-image -Recurse -File |
    Sort-Object Length -Descending |
    Select-Object -First 20 FullName, Length
```

Nên ghi lại kích thước cơ sở trước khi tối ưu. Khi so sánh, dùng cùng JDK vendor/version, hệ điều hành, kiến trúc CPU, đầu vào module và cách đo. Nếu thay nhiều yếu tố cùng lúc, sẽ khó xác định thay đổi nào tạo ra mức chênh lệch.

## 3. Chọn đúng module gốc

Tác động lớn nhất thường đến từ việc chọn đúng module cần thiết. Tùy chọn `--add-modules` xác định các root module; `jlink` tự phân giải các module bắt buộc mà chúng yêu cầu.

Ví dụ:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --output app-image
```

Nếu ứng dụng cần JDBC API, XML hoặc AWT/Swing, dependency module tương ứng sẽ được đưa vào khi có quan hệ module phù hợp. Không thêm hàng loạt module chỉ để tránh một lỗi chưa được xác định.

Có thể dùng:

```text
--add-modules ALL-MODULE-PATH
```

để chọn tất cả module quan sát được trên module path. Cách này tiện khi thử nghiệm nhưng thường tạo image lớn hơn cần thiết. Khi mục tiêu là tối ưu dung lượng, hãy chọn root module thực sự cần.

### 3.1. Phân tích dependency bằng jdeps

Với JAR hoặc ứng dụng Java, `jdeps` giúp phân tích các tham chiếu module tĩnh:

```sh
jdeps --print-module-deps --class-path "lib/*" app.jar
```

Kết quả là danh sách module Java mà công cụ xác định ứng dụng cần. Có thể dùng danh sách đó làm đầu vào cho `--add-modules`, sau đó tạo image và chạy kiểm thử.

Ví dụ:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules java.base,java.logging,java.sql,com.example.app \
  --output app-image
```

Danh sách module ở trên chỉ là ví dụ minh họa; hãy thay bằng kết quả phân tích và dependency thực tế của ứng dụng.

**Giới hạn của phân tích tĩnh:** `jdeps` có thể không phát hiện đầy đủ module được nạp bằng reflection, tên lớp lưu trong cấu hình, plugin, ServiceLoader, JNI hoặc cơ chế tải động riêng. Những module đó có thể cần được thêm tường minh. Sau khi giảm module, phải chạy test chức năng và kiểm tra các luồng khởi tạo, plugin, logging, database, TLS và xử lý tài nguyên.

### 3.2. Cẩn trọng với --limit-modules

`--limit-modules` giới hạn tập module mà linker có thể quan sát khi phân giải module graph. Nó có thể giúp kiểm soát phạm vi resolution, nhưng không phải công tắc nén đơn giản.

Nếu module bắt buộc hoặc provider cần thiết bị loại khỏi tập có thể quan sát, quá trình link sẽ báo lỗi hoặc image thiếu chức năng. Chỉ sử dụng sau khi hiểu dependency graph và đã kiểm thử đầy đủ.

## 4. Nén resource bằng --compress

Tùy chọn `--compress` điều khiển việc nén resource trong runtime image:

| Giá trị | Hành vi |
|---:|---|
| `0` | Không nén |
| `1` | Chia sẻ chuỗi hằng số (constant string sharing) |
| `2` | Nén resource bằng ZIP |

Ví dụ dùng mức ZIP:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --compress=2 \
  --output app-image-compressed
```

Mức 2 thường giảm dung lượng tốt hơn với resource có thể nén, nhưng hiệu quả tùy nội dung. Một số dữ liệu đã được nén hoặc có entropy cao sẽ giảm ít. Nén cũng có thể làm tăng chi phí đọc/giải nén tài nguyên lúc chạy.

Mức 1 dùng constant string sharing và có đặc tính khác ZIP compression. Hãy đo cả hai cấu hình trên ứng dụng thực tế nếu dung lượng và thời gian khởi động đều quan trọng.

Không nên khẳng định `--compress=2` luôn nhanh hơn hoặc luôn tốt hơn. Cần so sánh:

- Tổng dung lượng image.
- Thời gian khởi động.
- Thời gian tải resource mà ứng dụng sử dụng thường xuyên.
- Mức sử dụng CPU và bộ nhớ trong các luồng quan trọng.

## 5. Loại bỏ thông tin debug với --strip-debug

Thông tin debug có thể bao gồm số dòng nguồn, tên và phạm vi biến cục bộ cùng dữ liệu phục vụ debugger. Nếu image production không cần những thông tin này, có thể dùng:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --strip-debug \
  --output app-image-no-debug
```

Tùy chọn `--strip-debug` loại thông tin debug khỏi các module được link. Nó không loại bỏ bytecode thực thi của ứng dụng.

Tác động cần cân nhắc:

- Debugger có thể không hiển thị tên biến cục bộ hoặc ánh xạ dòng nguồn đầy đủ.
- Stack trace vẫn có thể cho biết lớp và phương thức, nhưng số dòng có thể không có nếu line number metadata bị loại.
- Việc phân tích sự cố production có thể khó hơn.

Nếu đội vận hành cần line number hoặc khả năng debug sâu, hãy cân nhắc giữ thông tin cần thiết. Đừng loại debug metadata chỉ để giảm một ít dung lượng mà làm mất dữ liệu cần cho điều tra lỗi.

## 6. Loại header và man page

Các header file native và man page thường hữu ích cho phát triển, tích hợp native hoặc tra cứu tài liệu. Runtime image dùng để chạy ứng dụng thường không cần chúng.

Có thể loại bằng:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --no-header-files \
  --no-man-pages \
  --output app-image-runtime
```

- `--no-header-files`: không đưa header file native vào image.
- `--no-man-pages`: không đưa trang hướng dẫn vào image.

Hai tùy chọn này thường phù hợp với image chỉ dùng để chạy ứng dụng. Nếu image còn được dùng để biên dịch native code hoặc cung cấp tài liệu cho người phát triển, cần đánh giá trước khi loại bỏ.

Không xóa thủ công các tệp trong thư mục `legal` để giảm dung lượng. Legal notice và license có thể là một phần nghĩa vụ phân phối của JDK hoặc thư viện. Hãy giữ các thành phần pháp lý mà quy trình phát hành yêu cầu.

## 7. Giới hạn locale data

Module `jdk.localedata` cung cấp dữ liệu locale bổ sung. Nếu ứng dụng chỉ hỗ trợ một số ngôn ngữ/khu vực, plugin `--include-locales` có thể giảm dữ liệu locale không cần thiết.

Ví dụ image cần tiếng Anh và tiếng Việt:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,jdk.localedata \
  --include-locales=en,vi \
  --output app-image-locales
```

Cần đưa `jdk.localedata` vào tập module để plugin có dữ liệu xử lý. Các locale tag phải phù hợp với danh sách được JDK hỗ trợ; có thể dùng tag ngôn ngữ và vùng theo quy tắc locale của Java.

Ứng dụng có thể vẫn chạy nhưng hiển thị định dạng ngày, số, tiền tệ, collation hoặc thông báo khác khi thiếu locale data. Hãy kiểm thử:

- `Locale.getAvailableLocales()`.
- `NumberFormat` và `DateTimeFormatter` cho các locale sản phẩm hỗ trợ.
- Sắp xếp và so sánh văn bản nếu dùng locale-sensitive collation.
- Các màn hình hoặc báo cáo có nội dung đa ngôn ngữ.

Chỉ giới hạn locale khi biết rõ sản phẩm cần hỗ trợ những locale nào. Nếu ứng dụng cho phép người dùng chọn locale bất kỳ, image có thể cần dữ liệu rộng hơn.

## 8. Service binding có thể làm image lớn hơn

`--bind-services` yêu cầu linker tìm service provider cho các service được module đã chọn sử dụng và liên kết provider cùng dependency cần thiết.

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --bind-services \
  --output app-image-services
```

Nếu ứng dụng dùng ServiceLoader, provider module có thể được tìm thấy thông qua service binding. Tuy nhiên, việc thêm provider cũng có thể làm tăng số module và dung lượng image.

Hãy chỉ bật service binding khi ứng dụng cần cơ chế đó. Nếu provider được chọn tường minh hoặc ứng dụng có cấu hình service riêng, kiểm tra xem module nào thực sự cần thiết. Sau khi link, chạy test để xác nhận provider vẫn được tìm thấy và không có provider không mong muốn.

## 9. Native command và native library

Native component có thể chiếm dung lượng đáng kể, đặc biệt với ứng dụng dùng thư viện xử lý ảnh, âm thanh, database hoặc tính toán native.

Các plugin và tùy chọn liên quan:

- `--strip-native-commands`: loại native command khỏi image.
- `--no-header-files`: loại header file.
- `--no-man-pages`: loại man page.

Cần đặc biệt cẩn thận với `--strip-native-commands`. Plugin này có thể loại các command native như `java`/`javaw` khỏi image. Nếu người dùng cần chạy ứng dụng bằng `app-image/bin/java`, không bật plugin này. Chỉ dùng khi mô hình triển khai có cách khởi chạy phù hợp khác và đã được kiểm thử.

Không phải mọi native library đều có thể loại bỏ. JVM và một số module cần thư viện native để hoạt động. Nếu xóa nhầm thư viện hoặc command, image có thể link thành công nhưng không khởi chạy hoặc thiếu chức năng khi chạy.

## 10. Cấu hình tối ưu thường dùng

Một cấu hình production phổ biến có thể loại debug metadata, header và man page, đồng thời nén resource:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --compress=2 \
  --output app-image-prod
```

Đây là cấu hình bắt đầu để đo, không phải cấu hình mặc định phù hợp cho mọi ứng dụng. Nếu ứng dụng cần locale data, service provider hoặc native command, hãy thêm cấu hình tương ứng và chạy test.

Ví dụ thêm locale:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app,jdk.localedata \
  --include-locales=en,vi \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --compress=2 \
  --output app-image-prod
```

Các module gốc phải phản ánh đúng dependency thực tế. Không sao chép nguyên lệnh ví dụ vào production nếu chưa xác nhận module và locale của ứng dụng.

## 11. Đo trước và sau theo cách có thể so sánh

Một phép so sánh đáng tin cần giữ các điều kiện như nhau:

1. Cùng phiên bản JDK và vendor.
2. Cùng hệ điều hành và kiến trúc CPU.
3. Cùng module đầu vào và ứng dụng.
4. Cùng cách đo dung lượng.
5. Chỉ thay đổi một nhóm tùy chọn mỗi lần.
6. Chạy cùng một bộ kiểm thử và workload.

Ví dụ bảng ghi kết quả:

| Cấu hình | Modules | Plugins | Image size | Startup | Kết quả test |
|---|---|---|---|---|---|
| Baseline | Theo dependency | Không | Đo thực tế | Đo thực tế | PASS/FAIL |
| Strip metadata | Như baseline | `--strip-debug`, no headers/man pages | Đo thực tế | Đo thực tế | PASS/FAIL |
| Compressed | Như baseline | `--compress=2` | Đo thực tế | Đo thực tế | PASS/FAIL |
| Minimal modules | Root modules đã xác minh | Plugin phù hợp | Đo thực tế | Đo thực tế | PASS/FAIL |
| Locale limited | Theo yêu cầu locale | `--include-locales` | Đo thực tế | Đo thực tế | PASS/FAIL |

Không điền số liệu ước lượng vào bảng. Hãy đo trên artifact được tạo bởi chính pipeline phát hành. Nếu muốn tính phần trăm giảm, dùng:

[
\text{Giảm dung lượng (\%)} =
\frac{\text{Kích thước ban đầu} - \text{Kích thước mới}}
{\text{Kích thước ban đầu}} \times 100
]

Ví dụ, nếu baseline là 120 MB và image mới là 90 MB, mức giảm là 25%. Đây chỉ là ví dụ tính toán; mức giảm thực tế phụ thuộc module và resource.

## 12. Kiểm tra nội dung image sau khi tối ưu

Không đánh giá image chỉ bằng số MB. Hãy xác nhận module và command cần thiết vẫn tồn tại.

Liệt kê module:

```sh
./app-image-prod/bin/java --list-modules
```

Kiểm tra phiên bản runtime:

```sh
./app-image-prod/bin/java -version
```

Kiểm tra các entry trong runtime image bằng `jimage`:

```sh
jimage list app-image-prod/lib/modules
```

Danh sách này giúp xem nội dung module image. Có thể dùng công cụ hệ điều hành để kiểm tra các file trong `bin`, `lib` và các thư mục khác.

Chạy ứng dụng bằng runtime image:

```sh
./app-image-prod/bin/java -m com.example.app/com.example.app.Main
```

Nếu đã tạo launcher:

```sh
./app-image-prod/bin/app
```

Sau đó kiểm thử các chức năng có nguy cơ bị ảnh hưởng:

- Khởi động, shutdown và xử lý exception.
- Logging, JDBC/database và các driver.
- TLS, security provider và chứng chỉ.
- Locale, ngày giờ, tiền tệ và định dạng số.
- Reflection, ServiceLoader, plugin và tải lớp động.
- Native library, JNI và native command.
- Resource, cấu hình và file bên ngoài.
- Các tác vụ vận hành cần công cụ dòng lệnh.

Một image nhỏ hơn nhưng thiếu provider hoặc tài nguyên cần thiết không phải kết quả tối ưu hợp lệ.

## 13. Các plugin bổ sung và lưu ý

Liệt kê plugin của JDK hiện tại:

```sh
jlink --list-plugins
```

Danh sách plugin có thể khác giữa các phiên bản JDK. Một số plugin hữu ích khác:

- `--order-resources`: điều chỉnh thứ tự resource trong image theo pattern, có thể hỗ trợ truy cập resource thường dùng.
- `--generate-cds-archive`: tạo CDS archive nếu JDK hỗ trợ; có thể cải thiện thời gian khởi động ở một số trường hợp nhưng cũng làm thay đổi dung lượng.
- `--exclude-files` và `--exclude-resources`: loại các file/resource theo pattern được plugin hỗ trợ.

Không dùng exclude pattern để loại file chỉ vì tên có vẻ không cần thiết. Một resource tưởng như phụ có thể được module hoặc ứng dụng nạp lúc chạy. Kiểm tra plugin theo tài liệu của JDK đang dùng và test image sau mỗi thay đổi.

## 14. Lỗi thường gặp khi tối ưu kích thước

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Image gần bằng JDK đầy đủ | Chọn quá nhiều module hoặc dùng `ALL-MODULE-PATH` | Phân tích dependency và chọn root module tối thiểu |
| Ứng dụng thiếu lớp khi chạy | Module được nạp động không được link | Xác định module qua cấu hình/reflection/service và thêm tường minh |
| ServiceLoader không tìm thấy provider | Thiếu provider module hoặc chưa bật service binding | Kiểm tra `uses`/`provides`, module path và `--bind-services` |
| Định dạng ngày/số sai ở một locale | Đã giới hạn locale nhưng thiếu dữ liệu cần thiết | Thêm locale cần hỗ trợ và kiểm thử `jdk.localedata` |
| Image giảm dung lượng nhưng debug khó | Đã strip debug metadata | Giữ thông tin debug cần thiết hoặc tạo image chẩn đoán riêng |
| Không chạy được lệnh java trong image | Đã bật `--strip-native-commands` | Bỏ plugin nếu cần launcher Java thông thường |
| Compression giảm ít hoặc khởi động chậm hơn | Resource khó nén hoặc chi phí giải nén cao | Đo mức 0/1/2 trên workload thật |
| Image không link được sau khi dùng limit modules | Module bắt buộc nằm ngoài tập quan sát | Điều chỉnh `--limit-modules` và kiểm tra dependency |
| Image nhỏ nhưng thiếu native library | Dependency native bị bỏ hoặc không được đóng gói | Kiểm tra native dependency trên target và thêm thành phần cần thiết |
| Không so sánh được kích thước giữa hai lần build | Khác JDK, OS, kiến trúc hoặc cách đo | Chuẩn hóa môi trường và đo lại cùng điều kiện |

Nếu quá trình link báo thiếu module, hãy xử lý module graph trước. Nếu link thành công nhưng ứng dụng lỗi, hãy kiểm tra dependency động, service provider, locale và native component. Đừng tiếp tục loại module chỉ để đạt một con số dung lượng.

## 15. Quy trình tối ưu khuyến nghị

1. Tạo baseline bằng root module tối thiểu đã biết và đo toàn image.
2. Dùng `jdeps` cùng module descriptor để xác định dependency tĩnh.
3. Kiểm tra các module được tải động, service provider, JNI và cấu hình runtime.
4. Tạo image với `--strip-debug`, `--no-header-files`, `--no-man-pages`.
5. So sánh `--compress=1` và `--compress=2` nếu dung lượng resource đáng kể.
6. Giới hạn locale bằng `--include-locales` khi sản phẩm có danh sách locale rõ ràng.
7. Xem xét service binding và native command để tránh thêm thành phần không cần.
8. Đo dung lượng, thời gian khởi động và workload sau từng thay đổi.
9. Chạy toàn bộ test trên runtime image cuối và đúng nền tảng triển khai.
10. Lưu lại lệnh jlink, phiên bản JDK, danh sách module và kết quả đo để build có thể tái lập.

Có thể lưu các tùy chọn link bằng `--save-opts` để ghi lại cấu hình dùng lại:

```sh
jlink \
  --module-path "$JAVA_HOME/jmods:mods" \
  --add-modules com.example.app \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --compress=2 \
  --save-opts jlink-options.txt \
  --output app-image
```

Tệp tùy chọn giúp lưu lại cấu hình linker, nhưng pipeline vẫn cần quản lý phiên bản JDK, đầu vào module và nền tảng build.

## 16. Checklist trước khi phát hành

- [ ] Đã đo baseline của toàn runtime image.
- [ ] Đã xác định root modules theo dependency của ứng dụng.
- [ ] Đã kiểm tra các module nạp động và service provider.
- [ ] Đã loại header/man page chỉ khi không cần.
- [ ] Đã quyết định giữ hay strip debug metadata theo nhu cầu vận hành.
- [ ] Đã so sánh compression level bằng kích thước và thời gian chạy.
- [ ] Đã giới hạn locale data theo yêu cầu sản phẩm.
- [ ] Không loại native command nếu image cần `bin/java`.
- [ ] Đã giữ native libraries và dependency hệ thống cần thiết.
- [ ] Đã kiểm tra module image bằng `java --list-modules` và `jimage list`.
- [ ] Đã chạy ứng dụng và test trên image cuối.
- [ ] Đã tạo image riêng cho đúng OS/CPU mục tiêu.
- [ ] Đã lưu lệnh build và số liệu đo để có thể tái lập.

## 17. Tài liệu tham khảo

- Oracle JDK Tool Reference — The `jlink` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html
- Oracle JDK Tool Reference — The `jdeps` Command: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html
- Java Platform Module System: https://docs.oracle.com/javase/specs/

Tối ưu kích thước image là quá trình cân bằng giữa dung lượng, khả năng tương thích, thời gian khởi động và khả năng vận hành. Chọn đúng module thường đem lại lợi ích lớn nhất; các plugin nén và loại metadata giúp tinh chỉnh thêm. Image chỉ được xem là đạt yêu cầu khi vừa đáp ứng mục tiêu dung lượng vừa chạy đầy đủ trên môi trường triển khai thực tế.