# Giữ tài nguyên và dữ liệu locale mà ứng dụng cần trong custom runtime

Khi đóng gói ứng dụng Java thành runtime riêng bằng jlink, mục tiêu không chỉ là giảm dung lượng JDK. Runtime phải giữ đủ module, resource và dữ liệu locale để các chức năng mà ứng dụng sử dụng tiếp tục hoạt động.

Có hai nhóm dữ liệu cần phân biệt:

- **Resource của ứng dụng:** file cấu hình, ResourceBundle, template, schema, ảnh hoặc metadata được đóng gói trong module/JAR của ứng dụng.
- **Locale data của JDK:** dữ liệu dùng bởi NumberFormat, DateFormat, Collator, Calendar và các API quốc tế hóa khác. Phần dữ liệu locale mở rộng được cung cấp bởi module jdk.localedata.

jlink liên kết các module được chỉ định cùng dependency của chúng. Resource nằm trong module được liên kết thường được giữ lại, trừ khi cấu hình plugin loại bỏ resource. Riêng locale data có thể được giới hạn bằng plugin --include-locales. Để dùng plugin này, phải đưa jdk.localedata vào tập module được liên kết bằng --add-modules.

## 1. Hiểu hai loại dữ liệu cần giữ

| Loại dữ liệu | Ví dụ | Cách bảo đảm có trong runtime |
|---|---|---|
| Resource ứng dụng | Messages_fr.properties, app.properties, template.html | Đóng gói resource vào module/JAR được link; tránh plugin loại bỏ file đó |
| Locale data của JDK | Quy tắc định dạng số/ngày, collation và calendar theo locale | Link jdk.localedata và chọn locale bằng --include-locales |
| Module chứa code sử dụng resource | com.example.localeapp | Thêm module ứng dụng vào --add-modules hoặc làm dependency của root module |
| Service provider | Provider được khai báo qua uses/provides | Đưa provider cần thiết vào image; cân nhắc --bind-services |

Không nên coi --include-locales là tùy chọn để đóng gói file dịch của ứng dụng. Nó lọc locale data của JDK trong jdk.localedata. Các file Messages_fr.properties do ứng dụng sở hữu vẫn phải được build và đóng gói cùng module ứng dụng.

## 2. Resource của ứng dụng được giữ như thế nào?

Resource không phải mã Java, nhưng có thể là thành phần bắt buộc để ứng dụng hoạt động. Ví dụ:

- ResourceBundle chứa nội dung giao diện theo ngôn ngữ.
- File properties chứa cấu hình mặc định.
- Template HTML hoặc email.
- Schema XML/JSON và dữ liệu mapping.
- File metadata hoặc service configuration.

Nếu resource nằm trong module được jlink đưa vào image, resource đó được giữ lại theo mặc định. Tuy nhiên, javac chỉ biên dịch mã nguồn Java; nó không tự sao chép file properties, template hay ảnh từ thư mục nguồn sang thư mục output. Build process phải chép các file này vào đúng vị trí trong module output hoặc đóng gói chúng vào modular JAR.

Ví dụ module có cấu trúc:

~~~text
src/
└── com.example.localeapp/
    ├── module-info.java
    └── com/example/localeapp/
        ├── Main.java
        ├── Messages.properties
        └── Messages_fr.properties
~~~

Hai file properties là resource của package com.example.localeapp. Khi build module, cần giữ chúng trong cùng vị trí tương ứng của module output:

~~~text
mods/
└── com.example.localeapp/
    ├── module-info.class
    └── com/example/localeapp/
        ├── Main.class
        ├── Messages.properties
        └── Messages_fr.properties
~~~

Với Maven, Gradle hoặc công cụ build khác, hãy kiểm tra cấu hình resource source set và nội dung artifact sau khi build. Với ví dụ dùng javac trực tiếp, phải copy resource thủ công.

### 2.1. ResourceBundle trong named module

ResourceBundle có thể tìm các file properties theo base name và locale. Ví dụ:

~~~java
ResourceBundle messages =
        ResourceBundle.getBundle(
                "com.example.localeapp.Messages",
                Locale.FRANCE
        );

System.out.println(messages.getString("greeting"));
~~~

Với Locale.FRANCE, quá trình tìm kiếm có thể sử dụng Messages_fr_FR.properties, sau đó Messages_fr.properties và bundle gốc Messages.properties theo quy tắc fallback của ResourceBundle.

Nên đặt bundle trong module sở hữu nó và kiểm tra việc truy cập từ đúng module. Quy tắc đóng gói của named module vẫn áp dụng; nếu một module khác cần truy cập resource nằm trong package của module cung cấp, hãy thiết kế API/resource access và mức mở package phù hợp.

### 2.2. Không để plugin loại bỏ resource cần thiết

jlink có plugin --exclude-resources để loại resource theo pattern. Ví dụ:

~~~bash
jlink --exclude-resources '**.jcov'
~~~

Nếu dùng pattern quá rộng, file properties hoặc resource của ứng dụng có thể bị loại khỏi runtime. Trước khi bật plugin loại bỏ resource, hãy kiểm tra pattern với nội dung module thực tế và chạy thử các chức năng đọc resource.

Các tùy chọn như --compress chỉ nén resource; --strip-debug loại thông tin debug. Chúng không thay thế việc xác định resource nào cần được giữ. Cần đặc biệt chú ý --exclude-resources vì tùy chọn này có thể làm mất dữ liệu ứng dụng.

## 3. Locale data của JDK và module jdk.localedata

JDK có dữ liệu locale phục vụ API quốc tế hóa. Một phần dữ liệu nền tảng nằm trong các module cơ bản; dữ liệu locale mở rộng được cung cấp qua module jdk.localedata.

Ứng dụng có thể dùng các API như:

- NumberFormat để định dạng số và tiền tệ.
- DateFormat hoặc DateTimeFormatter để trình bày ngày giờ.
- Collator để so sánh và sắp xếp chuỗi theo quy tắc ngôn ngữ.
- Calendar để xử lý lịch theo locale.
- ResourceBundle để lấy nội dung dịch của ứng dụng; phần bundle này là resource ứng dụng, không phải locale data của JDK.

Nếu ứng dụng cần các locale mở rộng, hãy đưa jdk.localedata vào runtime. jlink có plugin --include-locales để giới hạn các locale cần giữ, thay vì đưa toàn bộ dữ liệu locale mở rộng vào image.

### 3.1. Cú pháp --include-locales

Cú pháp:

~~~bash
jlink --module-path <module-path> \
      --add-modules <root-modules> \
      --include-locales=<language-tags> \
      --output <runtime-image>
~~~

Ví dụ:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.example.localeapp,jdk.localedata \
      --include-locales=en,fr \
      --output runtime
~~~

Trong đó:

- --module-path chỉ định các module của JDK và module ứng dụng.
- --add-modules xác định root module cần đưa vào image. jlink sẽ phân giải các dependency cần thiết.
- jdk.localedata phải có mặt trong danh sách module được thêm để plugin lọc locale data hoạt động.
- --include-locales nhận danh sách BCP 47 language tag, phân tách bằng dấu phẩy.
- --output là thư mục runtime image được tạo.

Các tag được so khớp theo quy tắc locale matching của RFC 4647. Ví dụ có thể dùng en, ja hoặc mẫu *-IN tùy các locale ứng dụng cần hỗ trợ. Hãy chọn các tag phù hợp với yêu cầu sản phẩm và kiểm tra locale cụ thể trong runtime cuối cùng.

**Nếu dùng --include-locales mà không thêm jdk.localedata, jlink sẽ báo lỗi.** Trên JDK 24, thông báo kiểm thử là:

~~~text
Error: jdk.localedata module was not specified with --add-modules option
~~~

Đây là lỗi cấu hình module root, không phải lỗi của ResourceBundle hay mã ứng dụng.

### 3.2. Xem các plugin jlink trên JDK đang dùng

Danh sách plugin có thể thay đổi theo phiên bản JDK. Kiểm tra trực tiếp:

~~~bash
jlink --list-plugins
~~~

Tìm --include-locales và các plugin liên quan đến resource. Cũng có thể xem cú pháp chung:

~~~bash
jlink --help
~~~

Không nên giả định một tùy chọn plugin có sẵn trên mọi bản JDK chỉ vì nó xuất hiện trong script của dự án khác. Build runtime phải được kiểm tra trên JDK dùng để tạo image.

## 4. Ví dụ hoàn chỉnh: giữ resource bundle và locale Pháp

Ví dụ tạo một module ứng dụng có resource bundle tiếng Pháp. Custom runtime chỉ giữ locale en và fr, nhưng vẫn phải giữ file Messages_fr.properties của ứng dụng.

### 4.1. Cấu trúc nguồn

~~~text
project/
├── src/
│   └── com.example.localeapp/
│       ├── module-info.java
│       └── com/example/localeapp/
│           ├── Main.java
│           ├── Messages.properties
│           └── Messages_fr.properties
└── mods/
~~~

File src/com.example.localeapp/module-info.java:

~~~java
module com.example.localeapp {
}
~~~

File src/com.example.localeapp/com/example/localeapp/Main.java:

~~~java
package com.example.localeapp;

import java.text.NumberFormat;
import java.util.Arrays;
import java.util.Locale;
import java.util.ResourceBundle;

public class Main {
    public static void main(String[] args) {
        Locale locale = Locale.FRANCE;

        ResourceBundle messages = ResourceBundle.getBundle(
                "com.example.localeapp.Messages",
                locale
        );

        NumberFormat number =
                NumberFormat.getNumberInstance(locale);

        System.out.println(messages.getString("greeting"));
        System.out.println(number.format(12345.67));
        System.out.println(
                "fr_FR available: " +
                Arrays.asList(Locale.getAvailableLocales()).contains(locale)
        );
    }
}
~~~

File src/com.example.localeapp/com/example/localeapp/Messages.properties:

~~~properties
greeting=Hello
~~~

File src/com.example.localeapp/com/example/localeapp/Messages_fr.properties:

~~~properties
greeting=Bonjour
~~~

ResourceBundle chọn bundle tiếng Pháp nếu resource tương ứng có mặt. NumberFormat dùng locale Pháp để định dạng số theo dữ liệu locale của JDK.

### 4.2. Biên dịch module và copy resource

Từ thư mục project, tạo module output:

~~~bash
mkdir -p mods
javac -d mods --module-source-path src -m com.example.localeapp
~~~

Copy các resource vào module output:

~~~bash
cp src/com.example.localeapp/com/example/localeapp/Messages*.properties \
   mods/com.example.localeapp/com/example/localeapp/
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force mods | Out-Null
javac -d mods --module-source-path src -m com.example.localeapp
Copy-Item -Path src/com.example.localeapp/com/example/localeapp/Messages*.properties -Destination mods/com.example.localeapp/com/example/localeapp/
~~~

Sau bước này, kiểm tra hai file properties thực sự nằm trong thư mục module output. Nếu chúng không có trong module, jlink không thể tự tạo hoặc khôi phục nội dung dịch của ứng dụng.

### 4.3. Tạo custom runtime

Trên Linux hoặc macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" \
      --add-modules com.example.localeapp,jdk.localedata \
      --include-locales=en,fr \
      --output runtime
~~~

Trên Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.localeapp,jdk.localedata --include-locales=en,fr --output runtime
~~~

Thư mục output runtime phải chưa tồn tại khi chạy jlink. Nếu thư mục runtime đã được tạo trước đó, hãy chọn một đường dẫn output mới hoặc xử lý thư mục cũ theo quy trình build của dự án.

### 4.4. Chạy bằng Java trong custom runtime

Trên Linux hoặc macOS:

~~~bash
runtime/bin/java --module com.example.localeapp/com.example.localeapp.Main
~~~

Trên Windows PowerShell:

~~~powershell
.\runtime\bin\java.exe --module com.example.localeapp/com.example.localeapp.Main
~~~

Kết quả stdout trên OpenJDK 24.0.2:

~~~text
Bonjour
12 345,67
fr_FR available: true
~~~

Dòng đầu chứng minh resource bundle Messages_fr.properties của ứng dụng được giữ và nạp. Dòng thứ hai chứng minh locale data Pháp trong runtime hỗ trợ NumberFormat. Dòng thứ ba xác nhận Locale.FRANCE có trong danh sách locale của runtime đã tạo.

Ký tự phân tách hàng nghìn trong output là narrow no-break space. Kết quả định dạng cụ thể có thể thay đổi theo phiên bản JDK và dữ liệu locale; hãy kiểm thử trên đúng JDK dùng để phát hành runtime.

## 5. Kiểm tra module và resource sau khi link

Sau khi tạo image, nên kiểm tra cả module và hành vi ứng dụng.

### 5.1. Kiểm tra danh sách module

Chạy:

~~~bash
runtime/bin/java --list-modules
~~~

Xác nhận có:

~~~text
com.example.localeapp
jdk.localedata
~~~

Phiên bản hiển thị sau ký hiệu @ phụ thuộc JDK được dùng để tạo runtime.

Nếu jdk.localedata vắng mặt, hãy kiểm tra lại --add-modules. Nếu module ứng dụng vắng mặt, kiểm tra tên module và module path đầu vào của jlink.

### 5.2. Kiểm tra resource bundle

Chạy ứng dụng và xác nhận chuỗi Bonjour được in ra. Nếu resource bị thiếu, ResourceBundle có thể ném MissingResourceException hoặc dùng bundle fallback không đúng ngôn ngữ mong muốn.

Khi gặp lỗi, kiểm tra theo thứ tự:

1. File Messages_fr.properties có trong source resource không?
2. Build có copy file vào module output không?
3. Module output/JAR có chứa file ở đúng package path không?
4. Module sở hữu resource có được đưa vào jlink image không?
5. Có plugin --exclude-resources nào loại file đó không?
6. Base name và locale truyền vào ResourceBundle có đúng không?

### 5.3. Kiểm tra locale data

Không chỉ kiểm tra rằng jdk.localedata có trong image. Hãy gọi các API locale mà ứng dụng thực sự dùng, với các locale đại diện cho yêu cầu sản phẩm.

Ví dụ:

~~~java
NumberFormat number = NumberFormat.getNumberInstance(Locale.FRANCE);
System.out.println(number.format(12345.67));
~~~

Nếu ứng dụng cần ngày tháng, tiền tệ, collation hoặc calendar, hãy bổ sung kiểm thử cho các API đó. Một locale có trong Locale.getAvailableLocales() không tự chứng minh mọi chức năng nghiệp vụ đã được kiểm tra.

## 6. Các tùy chọn jlink liên quan đến resource

| Tùy chọn | Tác dụng | Lưu ý |
|---|---|---|
| --add-modules | Chọn root module để link | Thêm module chứa code hoặc locale data mà ứng dụng cần |
| --include-locales | Giới hạn locale data được giữ | Cần jdk.localedata trong --add-modules |
| --exclude-resources | Loại resource theo pattern | Có thể làm mất properties, template hoặc metadata cần thiết |
| --compress | Nén resource trong image | Nén không đồng nghĩa với loại bỏ resource |
| --strip-debug | Loại thông tin debug | Không thay thế việc chọn module/resource |
| --no-header-files | Không đưa header files vào image | Dùng khi runtime không cần native development headers |
| --no-man-pages | Không đưa man pages vào image | Không ảnh hưởng resource bundle của ứng dụng |
| --bind-services | Link provider module và dependency của service | Hữu ích khi ứng dụng cần provider được khai báo qua uses/provides |

Không bật --exclude-resources theo pattern tổng quát nếu chưa kiểm tra. Ví dụ loại toàn bộ file properties có thể khiến ứng dụng mất cấu hình và bản dịch ngay cả khi jdk.localedata vẫn có đủ locale data.

Nếu ứng dụng dùng ServiceLoader, hãy xác định provider nào cần có trong runtime. --bind-services có thể đưa các provider module phù hợp và dependency của chúng vào image khi phân giải service binding. Vẫn phải kiểm tra kết quả bằng ứng dụng thực tế.

## 7. Phân biệt lỗi resource và lỗi locale data

| Triệu chứng | Nhóm nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| ResourceBundle ném MissingResourceException | Bundle không được copy, sai base name hoặc module chứa resource không có trong image | Kiểm tra resource path và artifact module |
| Ứng dụng hiển thị nội dung mặc định thay vì bản dịch | Bundle theo locale không có hoặc fallback được kích hoạt | Kiểm tra Messages_fr.properties và locale truyền vào |
| NumberFormat/DateFormat không cho kết quả mong đợi | Locale data cần thiết chưa được link hoặc locale chưa được include | Thêm jdk.localedata và --include-locales phù hợp |
| jlink báo jdk.localedata module was not specified | Dùng --include-locales nhưng không thêm jdk.localedata vào --add-modules | Bổ sung jdk.localedata |
| File properties có trong source nhưng mất trong image | Build không copy resource hoặc plugin exclude-resources loại file | Kiểm tra module output và plugin list |
| Chạy bằng JDK đầy đủ được nhưng custom runtime lỗi | Image thiếu module/resource hoặc locale cần thiết | Kiểm tra module graph, resource và locale API trong image |
| Một số locale chạy được, locale khác không | Danh sách locale include chưa bao phủ nhu cầu | Điều chỉnh BCP 47 tag và kiểm thử các locale bắt buộc |

Lỗi resource bundle và lỗi locale data có thể xuất hiện cùng lúc nhưng cần được xử lý riêng. Thêm jdk.localedata không khôi phục file dịch của ứng dụng; copy file dịch cũng không bổ sung locale data cho NumberFormat hoặc DateFormat.

## 8. Quy trình tạo runtime có đủ dữ liệu cần thiết

1. Liệt kê module ứng dụng và dependency runtime.
2. Liệt kê resource mà ứng dụng cần: properties, ResourceBundle, template, schema và file cấu hình.
3. Xác nhận build copy resource vào đúng module/JAR.
4. Xác định locale cần hỗ trợ từ yêu cầu sản phẩm, không chỉ từ locale mặc định của máy build.
5. Thêm jdk.localedata nếu cần locale data mở rộng.
6. Dùng --include-locales với BCP 47 tags phù hợp.
7. Kiểm tra các plugin loại resource trước khi dùng chúng.
8. Tạo image vào thư mục output mới.
9. Kiểm tra java --list-modules và resource bundle trong runtime.
10. Chạy kiểm thử định dạng số, ngày giờ, collation và nội dung dịch trên chính runtime image sẽ phát hành.

Nếu ứng dụng thay đổi locale hoặc thêm resource mới trong tương lai, cần cập nhật cấu hình build/link và kiểm thử lại runtime. Custom runtime là artifact được tạo từ tập module và resource cụ thể; nó không tự cập nhật khi source hoặc resource thay đổi.

## 9. Checklist trước khi phát hành custom runtime

- [ ] Module ứng dụng và các dependency bắt buộc có trong image.
- [ ] Module sở hữu từng resource cần thiết đã được link.
- [ ] File properties, ResourceBundle và template đã được copy vào module output/JAR.
- [ ] Không có --exclude-resources pattern loại nhầm resource.
- [ ] jdk.localedata được thêm nếu cần dữ liệu locale mở rộng.
- [ ] --include-locales chứa các locale mà ứng dụng phải hỗ trợ.
- [ ] Các BCP 47 tags đã được kiểm thử trong runtime image.
- [ ] ResourceBundle trả về bản dịch mong muốn.
- [ ] NumberFormat, DateFormat, Collator hoặc Calendar được kiểm thử theo nghiệp vụ.
- [ ] java --list-modules cho thấy các module cần thiết.
- [ ] Ứng dụng chạy thành công bằng runtime image, không dựa vào JDK cài trên máy build.

## 10. Tài liệu tham khảo

- [Java SE 26 — jlink command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html): tạo runtime image, root modules và các tùy chọn link.
- [Java SE 26 API — ResourceBundle](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html): tra cứu bundle, locale và cơ chế fallback.
- [Java SE 26 API — Locale](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Locale.html): locale identifiers và BCP 47 language tags.
- [Java SE 26 API — NumberFormat](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html): định dạng số theo locale.
- [Java SE 26 — jdk.localedata module](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.localedata/module-summary.html): module cung cấp dữ liệu locale mở rộng.
