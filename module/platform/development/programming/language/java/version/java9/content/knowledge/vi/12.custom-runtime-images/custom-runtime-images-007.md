# Chọn plugin tối ưu theo JDK đang dùng

## 1. Hiểu đúng plugin trong quá trình tạo runtime riêng

Trong ngữ cảnh tạo runtime riêng bằng JPMS, plugin được nhắc đến ở đây là **plugin của công cụ jlink**. jlink ghép các module cần thiết thành một runtime image có thể triển khai cùng ứng dụng. Các plugin tham gia xử lý nội dung image, chẳng hạn loại bỏ debug information, nén tài nguyên, bỏ header hoặc man page và tối ưu thứ tự tài nguyên.

Plugin của jlink được cung cấp theo JDK đang chạy công cụ. Danh sách và tùy chọn có thể khác giữa các phiên bản JDK hoặc các bản phân phối JDK. Vì vậy, không nên sao chép một danh sách plugin từ tài liệu của JDK khác rồi mặc định rằng mọi tùy chọn đều có mặt.

Cần phân biệt ba nhóm:

- **jlink options** điều khiển quá trình tạo image, ví dụ **--module-path**, **--add-modules**, **--bind-services** và **--output**.
- **jlink plugins** xử lý hoặc biến đổi nội dung image, ví dụ **--strip-debug**, **--compress** hoặc **--include-locales** nếu JDK hiện tại cung cấp.
- **Maven/Gradle plugins** là phần mở rộng của build tool. Chúng có thể gọi jlink hoặc chuẩn bị artifact, nhưng không phải plugin tích hợp của jlink.

Bài này tập trung vào plugin của jlink vì mục tiêu là lựa chọn cấu hình phù hợp khi tạo runtime riêng. Nguyên tắc quan trọng là chọn theo danh sách mà đúng JDK mục tiêu cung cấp, mục đích triển khai và kết quả đo kiểm.

## 2. Kiểm tra JDK và plugin có sẵn

Trước khi chọn plugin, hãy xác định chính xác JDK mà build đang sử dụng:

~~~bash
java --version
jlink --version
jlink --list-plugins
~~~

- **java --version** hiển thị phiên bản Java của lệnh java đang được tìm thấy qua PATH.
- **jlink --version** hiển thị phiên bản công cụ jlink.
- **jlink --list-plugins** liệt kê plugin cùng cú pháp và mô tả mà công cụ jlink hiện tại hỗ trợ.

Khi hai lệnh java và jlink trỏ tới hai JDK khác nhau, kết quả kiểm tra có thể gây nhầm lẫn. Trong CI hoặc script phát hành, nên gọi công cụ bằng đường dẫn tuyệt đối từ cùng một thư mục JDK, chẳng hạn:

~~~bash
"$JAVA_HOME/bin/java" --version
"$JAVA_HOME/bin/jlink" --version
"$JAVA_HOME/bin/jlink" --list-plugins
~~~

Trên Windows PowerShell:

~~~powershell
& "$env:JAVA_HOME\bin\java.exe" --version
& "$env:JAVA_HOME\bin\jlink.exe" --version
& "$env:JAVA_HOME\bin\jlink.exe" --list-plugins
~~~

Đầu ra của **--list-plugins** là nguồn kiểm tra trực tiếp cho JDK đang dùng. Hãy đọc cả cú pháp, giá trị hợp lệ và mô tả của từng plugin. Nếu plugin cần dùng không xuất hiện trong danh sách, hãy kiểm tra lại JDK, nhà cung cấp và phiên bản trước khi thiết kế cấu hình thay thế.

## 3. Chọn plugin theo mục tiêu triển khai

Không có một bộ plugin tối ưu cho mọi ứng dụng. Hãy bắt đầu từ yêu cầu của runtime image:

| Mục tiêu | Plugin hoặc tùy chọn cần xem xét | Đánh đổi cần đánh giá |
|---|---|---|
| Giảm kích thước image | **--compress** | Giảm dung lượng lưu trữ; cần đo thời gian khởi động và tải tài nguyên. |
| Loại bỏ thông tin debug | **--strip-debug** | Image gọn hơn; việc debug và phân tích stack trace có thể ít thông tin hơn. |
| Không cần header C/C++ | **--no-header-files** | Phù hợp runtime triển khai; không phù hợp image dùng làm SDK để biên dịch native code. |
| Không cần tài liệu man | **--no-man-pages** | Giảm nội dung image; không phù hợp môi trường cần tài liệu man tại chỗ. |
| Chỉ cần một số locale | **--include-locales** | Giảm dữ liệu locale; phải giữ đủ locale mà ứng dụng thực sự hỗ trợ. |
| Sắp xếp resource | **--order-resources** | Có thể cải thiện locality trong một số trường hợp; cần đo trên ứng dụng thực tế. |
| Tạo CDS archive | **--generate-cds-archive**, nếu có trong danh sách | Có thể cải thiện thời gian khởi động; cần kiểm tra điều kiện sử dụng và chi phí tạo archive. |
| Giữ provider cho ServiceLoader | **--bind-services** | Đây là tùy chọn tạo image, không phải plugin xử lý nén; có thể làm image chứa thêm module provider. |

Hãy ưu tiên yêu cầu chức năng và kích thước thực tế. Không bật tất cả plugin chỉ vì chúng có trong danh sách. Một runtime image nhỏ hơn nhưng thiếu locale, provider hoặc tài nguyên mà ứng dụng cần sẽ không phải là kết quả tối ưu.

## 4. Các plugin jlink thường gặp

Danh sách thực tế phải lấy từ **jlink --list-plugins** của JDK mục tiêu. Những plugin dưới đây là các lựa chọn phổ biến trên nhiều bản JDK hiện đại; cú pháp và khả năng cụ thể vẫn cần đối chiếu với đầu ra của công cụ đang dùng.

### 4.1. Nén tài nguyên bằng --compress

Plugin **--compress** điều khiển cách nén nội dung trong runtime image. Các mức thường gặp:

- **0**: không nén.
- **1**: chia sẻ chuỗi hằng theo cơ chế hỗ trợ của jlink.
- **2**: nén tài nguyên theo ZIP.

Ví dụ:

~~~bash
jlink --compress=2 --module-path mods --add-modules com.acme.hello --output runtime
~~~

Mức nén cao hơn có thể làm image nhỏ hơn nhưng có chi phí CPU khi runtime đọc hoặc giải nén dữ liệu. Hãy đo cả kích thước image, thời gian khởi động và hành vi tải resource của ứng dụng. Không chọn mức nén chỉ dựa trên kích thước file đầu ra.

### 4.2. Loại bỏ debug information bằng --strip-debug

Plugin **--strip-debug** loại bỏ thông tin debug khỏi các class được đưa vào runtime image:

~~~bash
jlink --strip-debug --module-path mods --add-modules com.acme.hello --output runtime
~~~

Tùy chọn này phù hợp với runtime triển khai khi không cần giữ đầy đủ metadata phục vụ debug. Nếu hệ thống cần phân tích lỗi production với thông tin dòng nguồn hoặc debug metadata, hãy đánh giá tác động trước khi bật.

Có thể duy trì một image phục vụ chẩn đoán và một image tối ưu cho triển khai nếu quy trình vận hành yêu cầu hai mục tiêu khác nhau.

### 4.3. Bỏ header và man page

Hai plugin thường được dùng khi tạo runtime image chỉ để chạy ứng dụng:

~~~bash
jlink --no-header-files --no-man-pages --module-path mods --add-modules com.acme.hello --output runtime
~~~

- **--no-header-files** bỏ các header native.
- **--no-man-pages** bỏ tài liệu man.

Các tùy chọn này thường hợp lý cho image triển khai ứng dụng Java. Không bật chúng nếu image còn được dùng làm môi trường phát triển native hoặc cần tài liệu man cục bộ.

### 4.4. Giới hạn locale bằng --include-locales

Một số ứng dụng chỉ cần một tập locale xác định. Plugin **--include-locales** cho phép giới hạn dữ liệu locale được đưa vào image. Plugin này liên quan tới module **jdk.localedata**; hãy xác nhận module và plugin đều có trong JDK đang dùng.

Ví dụ minh họa:

~~~bash
jlink --add-modules com.acme.hello,jdk.localedata --include-locales=en,vi --module-path mods --output runtime
~~~

Chỉ giữ các locale đã được kiểm thử với yêu cầu sản phẩm. Nếu người dùng có thể chọn locale khác, image rút gọn có thể khiến định dạng ngày tháng, số, tiền tệ hoặc thông điệp bản địa hóa không đáp ứng mong đợi.

### 4.5. Sắp xếp tài nguyên bằng --order-resources

Plugin **--order-resources** cho phép chỉ định thứ tự tài nguyên trong image. Nó có thể hữu ích khi muốn ưu tiên những tài nguyên được truy cập sớm.

~~~bash
jlink --order-resources='**/module-info.class' --module-path mods --add-modules com.acme.hello --output runtime
~~~

Mẫu trên chỉ minh họa cách truyền một pattern; thứ tự hữu ích phụ thuộc cách ứng dụng tải class và resource. Không nên xem việc sắp xếp resource là cải thiện hiệu năng chắc chắn. Hãy đo bằng workload đại diện trước và sau khi bật plugin.

### 4.6. Tạo CDS archive nếu JDK hỗ trợ

Một số bản JDK cung cấp plugin **--generate-cds-archive** để tạo Class Data Sharing archive trong quá trình tạo runtime image.

CDS có thể giảm công việc khởi tạo class ở các lần chạy sau trong môi trường phù hợp. Tuy nhiên, plugin và điều kiện sử dụng phụ thuộc JDK. Chỉ dùng khi **--list-plugins** xác nhận plugin có sẵn, sau đó kiểm tra image thực tế và đo thời gian khởi động trên môi trường triển khai.

## 5. Phân biệt plugin với các tùy chọn tạo runtime

Một số tùy chọn quan trọng của jlink không phải plugin. Chúng quyết định module nào được đưa vào image và cách runtime được đóng gói.

| Tùy chọn | Vai trò |
|---|---|
| **--module-path** | Chỉ định nơi jlink tìm module ứng dụng và module JDK. |
| **--add-modules** | Chọn các module gốc cần đưa vào image; jlink giải quyết dependency của chúng. |
| **--bind-services** | Bổ sung các module provider phù hợp với service binding trong đồ thị module. |
| **--launcher** | Tạo launcher tùy chỉnh cho ứng dụng. |
| **--output** | Chỉ định thư mục runtime image đầu ra. |
| **--plugin-module-path** | Chỉ định module path chứa plugin mở rộng nếu môi trường có plugin bổ sung. |
| **--list-plugins** | Liệt kê plugin mà jlink hiện tại cung cấp. |

Ví dụ, nếu ứng dụng sử dụng ServiceLoader, chỉ thêm module ứng dụng vào image có thể chưa đủ để đưa provider mong muốn vào. Khi đó cần hiểu khai báo **uses**, **provides** và cân nhắc **--bind-services**.

Không dùng **--bind-services** như một plugin nén hoặc tối ưu kích thước. Nó thay đổi tập module provider được đưa vào image, nên có thể làm image lớn hơn để bảo đảm chức năng dịch vụ.

## 6. Quy trình chọn plugin theo JDK

Một quy trình lựa chọn có thể áp dụng trong dự án:

1. **Chốt JDK mục tiêu.** Ghi rõ nhà cung cấp, phiên bản phát hành, kiến trúc và hệ điều hành của runtime sẽ triển khai.
2. **Dùng jlink từ chính JDK đó.** Kiểm tra java --version và jlink --version để tránh dùng nhầm công cụ trong PATH.
3. **Liệt kê plugin.** Chạy jlink --list-plugins và lưu đầu ra trong log build để có thể truy lại cấu hình.
4. **Xác định module cần thiết.** Phân tích dependency của ứng dụng, khai báo service và các module mà runtime cần có.
5. **Chọn plugin theo mục tiêu.** Chọn nén, strip debug, locale, resource ordering hoặc CDS khi có yêu cầu rõ ràng và JDK hỗ trợ.
6. **Tạo image thử nghiệm.** Dùng đúng module path, plugin và tùy chọn sẽ dùng trong pipeline phát hành.
7. **Kiểm thử chức năng.** Chạy luồng nghiệp vụ, nạp resource, định dạng locale, tải provider và các tác vụ khởi động quan trọng.
8. **Đo hiệu năng và dung lượng.** So sánh kích thước image, thời gian khởi động, mức dùng bộ nhớ và thời gian tải tài nguyên.
9. **Cố định cấu hình.** Ghi nhận JDK, plugin và tham số đã chọn trong script build hoặc pipeline để kết quả có thể tái lập.

Khi nâng JDK, hãy chạy lại bước liệt kê plugin và kiểm thử. Không mặc định plugin cũ vẫn có cùng tên, cùng tham số hoặc cùng hành vi ở phiên bản mới.

## 7. Ví dụ hoàn chỉnh: tạo runtime riêng cho ứng dụng modular

Ví dụ sau tạo một ứng dụng Java nhỏ và dùng jlink để tạo runtime image. Cấu hình chọn một số plugin phổ biến; trước khi chạy, xác nhận JDK đang dùng liệt kê các tùy chọn đó.

Cấu trúc dự án:

~~~text
project/
└── src/
    └── com.acme.hello/
        ├── module-info.java
        └── com/acme/hello/Main.java
~~~

File **src/com.acme.hello/module-info.java**:

~~~java
module com.acme.hello {
}
~~~

File **src/com.acme.hello/com/acme/hello/Main.java**:

~~~java
package com.acme.hello;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from custom runtime");
    }
}
~~~

### 7.1. Kiểm tra công cụ và plugin

~~~bash
java --version
jlink --version
jlink --list-plugins
~~~

Xác nhận JDK đang dùng hỗ trợ **--strip-debug**, **--no-header-files**, **--no-man-pages** và **--compress** trước khi dùng các tham số này.

### 7.2. Biên dịch module ứng dụng

Tại thư mục project:

~~~bash
javac --module-source-path src -d mods -m com.acme.hello
~~~

Lệnh này biên dịch module vào thư mục **mods**. Module ứng dụng chỉ sử dụng **java.base** ngầm định nên không cần khai báo requires riêng cho module nền tảng đó.

### 7.3. Tạo runtime image

Trên Linux hoặc macOS:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.acme.hello --strip-debug --no-header-files --no-man-pages --compress=2 --output runtime
~~~

Trên Windows PowerShell:

~~~powershell
& "$env:JAVA_HOME\bin\jlink.exe" --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.acme.hello --strip-debug --no-header-files --no-man-pages --compress=2 --output runtime
~~~

Thư mục **jmods** cung cấp các module của JDK; **mods** cung cấp module ứng dụng. jlink phân giải dependency của module gốc và tạo image trong thư mục **runtime**.

### 7.4. Chạy bằng runtime image vừa tạo

Trên Linux hoặc macOS:

~~~bash
runtime/bin/java -m com.acme.hello/com.acme.hello.Main
~~~

Trên Windows:

~~~powershell
.\runtime\bin\java.exe -m com.acme.hello/com.acme.hello.Main
~~~

Kết quả:

~~~text
Hello from custom runtime
~~~

Ứng dụng chạy bằng Java runtime được tạo trong thư mục **runtime**. Không cần dùng JDK đầy đủ để khởi chạy image này.

## 8. Cách đánh giá plugin đã chọn

Sau khi tạo image, hãy so sánh với image cơ sở không bật các plugin tối ưu. Một bảng đo đơn giản:

| Chỉ số | Image cơ sở | Image tối ưu |
|---|---|---|
| Kích thước thư mục image | Đo thực tế | Đo thực tế |
| Thời gian khởi động | Đo nhiều lần | Đo nhiều lần |
| Thời gian tải resource | Đo theo workload | Đo theo workload |
| Hành vi locale | Kiểm thử các locale yêu cầu | Kiểm thử lại |
| Service provider | Kiểm thử danh sách provider | Kiểm thử lại |
| Chức năng nghiệp vụ | Bộ kiểm thử chuẩn | Chạy lại toàn bộ |

Để phép đo có ý nghĩa:

- Dùng cùng ứng dụng, dữ liệu, máy và điều kiện chạy.
- Thực hiện nhiều lần và so sánh median hoặc phân vị phù hợp.
- Phân biệt thời gian khởi động nguội và khởi động khi cache đã nóng.
- Đo kích thước image sau khi tạo hoàn chỉnh, không chỉ kích thước thư mục module trung gian.
- Kiểm tra ứng dụng trên đúng hệ điều hành và kiến trúc mục tiêu.

Plugin chỉ nên được giữ trong cấu hình phát hành khi kết quả đo hoặc yêu cầu chức năng chứng minh giá trị của nó.

## 9. Plugin mở rộng và tính tương thích

Ngoài plugin được tích hợp trong JDK, jlink có thể nhận plugin mở rộng qua **--plugin-module-path** nếu JDK và plugin cung cấp cơ chế tương thích.

Khi dùng plugin bên ngoài:

- Kiểm tra tài liệu và phiên bản plugin có hỗ trợ đúng phiên bản JDK mục tiêu hay không.
- Chỉ dùng plugin từ nguồn đáng tin cậy và quản lý phiên bản như một dependency build.
- Kiểm tra module plugin có thể được jlink nạp và đăng ký đúng cách.
- Chạy lại jlink --list-plugins với đúng cấu hình plugin module path nếu công cụ hỗ trợ liệt kê chúng trong môi trường đó.
- Kiểm thử runtime image được tạo ra; không chỉ dựa vào việc lệnh jlink kết thúc thành công.

Không đưa plugin được build cho một JDK khác vào pipeline phát hành khi chưa xác nhận tương thích. Plugin có thể phụ thuộc API nội bộ hoặc SPI của phiên bản JDK cụ thể.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| jlink báo unrecognized option hoặc unknown plugin | Plugin không có trong JDK đang dùng, hoặc cú pháp tham số không đúng. Chạy --list-plugins để đối chiếu. |
| java và jlink báo phiên bản khác nhau | PATH đang trỏ tới các JDK khác nhau. Dùng đường dẫn từ cùng JAVA_HOME. |
| Không tìm thấy module khi tạo image | Module path thiếu JMOD hoặc module ứng dụng; kiểm tra --module-path và --add-modules. |
| Runtime thiếu provider | Ứng dụng dùng service nhưng provider chưa được đưa vào image. Kiểm tra uses/provides và --bind-services. |
| Image nhỏ nhưng ứng dụng lỗi khi hiển thị ngôn ngữ | Plugin locale đã loại bỏ dữ liệu mà ứng dụng cần. Kiểm tra jdk.localedata và --include-locales. |
| Không thể biên dịch native code trên image | Header files đã bị loại bỏ bằng --no-header-files. Dùng JDK hoặc môi trường SDK phù hợp cho tác vụ biên dịch. |
| Khởi động hoặc tải tài nguyên chậm hơn sau nén | Chi phí giải nén có thể ảnh hưởng workload. Đo các mức nén và chọn theo kết quả thực tế. |
| Plugin hoạt động trên máy phát triển nhưng thất bại trong CI | JDK hoặc nhà cung cấp trong CI khác môi trường phát triển. Cố định JDK và lưu kết quả --list-plugins. |
| Image chạy trên máy build nhưng không chạy ở máy đích | Runtime image gắn với nền tảng hệ điều hành và kiến trúc. Tạo và kiểm thử image cho đúng nền tảng triển khai. |

## 11. Checklist trước khi phát hành runtime riêng

- [ ] Đã cố định nhà cung cấp, phiên bản JDK, hệ điều hành và kiến trúc mục tiêu.
- [ ] java và jlink được gọi từ cùng một JDK.
- [ ] Đã lưu đầu ra của jlink --list-plugins.
- [ ] Mỗi plugin được chọn có mục đích rõ ràng và được JDK hiện tại hỗ trợ.
- [ ] Đã xác định đủ module ứng dụng và dependency.
- [ ] Đã kiểm tra service provider nếu ứng dụng dùng ServiceLoader.
- [ ] Locale và resource cần thiết vẫn có trong image.
- [ ] Image được kiểm thử bằng chính runtime java nằm trong image.
- [ ] Đã đo kích thước và hiệu năng với workload đại diện.
- [ ] Pipeline build cố định các tham số để có thể tái lập kết quả.
- [ ] Đã chạy lại toàn bộ kiểm thử khi nâng JDK.

## 12. Kết luận

Cách chọn plugin jlink đáng tin cậy nhất là kiểm tra danh sách từ đúng JDK sẽ tạo runtime image, sau đó chọn plugin theo mục tiêu cụ thể của ứng dụng. **--list-plugins** giúp xác nhận tên, cú pháp và khả năng hiện có; các plugin như **--compress**, **--strip-debug**, **--no-header-files**, **--no-man-pages** và **--include-locales** giải quyết những nhu cầu khác nhau và có các đánh đổi riêng.

Kết quả tối ưu phải giữ đủ module, provider, locale và resource mà ứng dụng cần, đồng thời đáp ứng mục tiêu dung lượng, thời gian khởi động và khả năng vận hành. Khi đổi phiên bản hoặc nhà cung cấp JDK, hãy kiểm tra lại plugin và tạo image thử nghiệm. Đừng chọn plugin chỉ vì nó có sẵn; hãy giữ lại plugin đã được kiểm chứng trên runtime và môi trường triển khai thực tế.
