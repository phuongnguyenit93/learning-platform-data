# File association bằng --file-associations và tệp properties

Ứng dụng Java có thể xử lý một số loại tài liệu riêng, chẳng hạn file dự án, bản ghi dữ liệu hoặc tài liệu cấu hình. Khi người dùng mở file từ File Explorer, Finder hoặc trình quản lý file Linux, hệ điều hành có thể khởi chạy ứng dụng đã đăng ký để xử lý file đó. **jpackage** hỗ trợ khai báo liên kết này bằng tùy chọn **--file-associations** và một tệp properties cho mỗi loại file.

Một association mô tả phần mở rộng, MIME type, mô tả ngắn và icon của loại file. jpackage đưa thông tin đó vào package để hệ điều hành đăng ký handler khi cài đặt. Ứng dụng vẫn phải tự đọc đường dẫn file được chuyển đến launcher và kiểm tra nội dung trước khi xử lý.

Trong module Java 16, jpackage là công cụ đóng gói ổn định và **--file-associations** vẫn hữu ích trong quy trình phát hành Java hiện đại. Bài này tập trung vào cú pháp properties, nhiều loại file, cách truyền tùy chọn cho jpackage, xử lý tham số trong Java và kiểm thử trên Windows, macOS, Linux. Việc đăng ký handler không đồng nghĩa ứng dụng được tự động chọn làm ứng dụng mặc định trong mọi hệ điều hành.

## 1. File association là gì?

File association là quan hệ giữa một loại file và ứng dụng có thể mở hoặc xử lý loại file đó. Hệ điều hành sử dụng thông tin như phần mở rộng và MIME type để tìm ứng dụng phù hợp khi người dùng mở file.

Ví dụ một ứng dụng quản lý kho có thể xử lý:

| Loại file | Extension | MIME type ví dụ | Mục đích |
|---|---|---|---|
| Inventory document | inv | application/vnd.example.inventory | Dữ liệu kho chính. |
| Inventory exchange | invx | application/vnd.example.inventory-exchange | File trao đổi dữ liệu. |
| Inventory template | invtpl | application/vnd.example.inventory-template | Mẫu dữ liệu. |

Khi cài ứng dụng, jpackage có thể đăng ký các loại file này để hệ điều hành biết ứng dụng có thể mở chúng. Khi người dùng mở file, hệ điều hành gọi launcher của ứng dụng và truyền file cần mở theo cơ chế của nền tảng.

File association có thể được người dùng thay đổi sau đó. Nếu nhiều ứng dụng cùng hỗ trợ một loại file, hệ điều hành hoặc desktop environment quyết định ứng dụng nào là handler mặc định dựa trên thiết lập của người dùng.

## 2. Vai trò của --file-associations

Tùy chọn **--file-associations** nhận đường dẫn tới một tệp properties mô tả một association:

~~~bash
jpackage \
  --name InventoryDesk \
  --input build/input \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --file-associations packaging/inventory.properties \
  --dest dist
~~~

Các điểm cần nhớ:

- Mỗi tệp properties mô tả một association.
- Mỗi association cần một lần truyền **--file-associations** riêng.
- Tùy chọn có thể được dùng nhiều lần trong cùng lệnh.
- Association được tạo khi đóng gói installer và đăng ký trong quá trình cài đặt.
- Tệp properties có thể dùng đường dẫn tuyệt đối hoặc tương đối với thư mục hiện tại của lệnh build.

**--file-associations** là tùy chọn tạo application package. Nó không phải tùy chọn tạo application image độc lập. Nếu quy trình có hai giai đoạn, hãy truyền các file association khi tạo installer từ application image.

## 3. Cấu trúc tệp properties

Oracle định nghĩa bốn khóa cho file association:

| Khóa | Bắt buộc? | Ý nghĩa |
|---|---|---|
| mime-type | Không bắt buộc nếu đã có extension | MIME type của loại file mà ứng dụng xử lý. |
| extension | Không bắt buộc nếu đã có mime-type | Phần mở rộng file, không cần dấu chấm ở đầu. |
| icon | Không | Icon dùng cho loại file. |
| description | Không | Mô tả ngắn của association. |

Mỗi association phải có ít nhất một trong hai khóa **mime-type** hoặc **extension**. Trong ứng dụng thực tế, nên khai báo cả hai khi biết chính xác MIME type và extension để hệ điều hành có đủ thông tin nhận diện.

Ví dụ file inventory.properties:

~~~properties
mime-type=application/vnd.example.inventory
extension=inv
description=Inventory Document
~~~

Một số quy tắc:

- Giá trị extension là inv, không phải .inv.
- MIME type nên dùng dạng type/subtype theo quy ước MIME.
- Description nên ngắn, dễ hiểu và nhất quán với tên loại tài liệu.
- Icon phải có trong thư mục input của ứng dụng tại thời điểm đóng gói.
- Nếu bỏ icon, jpackage dùng icon mặc định theo hành vi của nền tảng.

Không đưa dấu chấm vào extension nếu không có yêu cầu đặc biệt từ toolchain. Dùng tên MIME type thuộc namespace của tổ chức nếu đó là định dạng file riêng.

## 4. Tạo một association cho file riêng của ứng dụng

Giả sử ứng dụng InventoryDesk mở file có phần mở rộng inv. Tạo file packaging/inventory.properties:

~~~properties
mime-type=application/vnd.example.inventory
extension=inv
description=Inventory Document
icon=inventory-document.ico
~~~

Thư mục đầu vào của ứng dụng cần chứa JAR, dependency và icon:

~~~text
build/
  input/
    inventory-app.jar
    inventory-document.ico
    lib/
      dependency-a.jar
      dependency-b.jar
packaging/
  inventory.properties
~~~

Sau đó đóng gói trực tiếp từ input directory:

~~~bash
jpackage \
  --type msi \
  --name InventoryDesk \
  --app-version 1.4.0 \
  --input build/input \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --file-associations packaging/inventory.properties \
  --dest dist
~~~

Trong ví dụ này, jpackage tìm icon association trong build/input theo yêu cầu tài liệu. Lệnh MSI chỉ chạy trên Windows. Trên macOS hoặc Linux, chọn loại package tương ứng và build trên chính nền tảng đích.

## 5. Khai báo nhiều loại file

Nếu ứng dụng hỗ trợ nhiều loại file, tạo một properties file cho từng association. Ví dụ:

inventory.properties:

~~~properties
mime-type=application/vnd.example.inventory
extension=inv
description=Inventory Document
icon=inventory-document.ico
~~~

inventory-exchange.properties:

~~~properties
mime-type=application/vnd.example.inventory-exchange
extension=invx
description=Inventory Exchange File
icon=inventory-exchange.ico
~~~

inventory-template.properties:

~~~properties
mime-type=application/vnd.example.inventory-template
extension=invtpl
description=Inventory Template
icon=inventory-template.ico
~~~

Truyền từng association bằng một lần gọi tùy chọn:

~~~bash
jpackage \
  --type msi \
  --name InventoryDesk \
  --app-version 1.4.0 \
  --input build/input \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --file-associations packaging/inventory.properties \
  --file-associations packaging/inventory-exchange.properties \
  --file-associations packaging/inventory-template.properties \
  --dest dist
~~~

Không gộp nhiều extension vào một giá trị extension bằng dấu phẩy. Theo hướng dẫn jpackage, mỗi association có một properties file và một lần dùng **--file-associations**. Cách tách riêng giúp mô tả, MIME type và icon của từng loại file rõ ràng.

## 6. Khi nào chỉ khai báo extension, khi nào khai báo MIME type?

Extension là cách nhận diện quen thuộc với người dùng và file manager. MIME type mô tả loại nội dung theo hệ thống định danh nội dung.

| Tình huống | Cấu hình phù hợp |
|---|---|
| Định dạng nội bộ chỉ có extension riêng | Có thể chỉ khai báo extension. |
| Định dạng có MIME type được xác định rõ | Nên khai báo MIME type. |
| Định dạng riêng có cả extension và MIME type | Khai báo cả hai. |
| File không có extension nhưng hệ thống nhận diện bằng MIME type | Có thể chỉ khai báo MIME type. |
| Nhiều extension là các loại tài liệu khác nhau | Tạo properties file riêng cho từng association. |

Không tự tạo MIME type trùng với định dạng phổ biến khác. Nếu định dạng do tổ chức phát triển, dùng vendor tree hoặc namespace riêng theo quy ước MIME và quản lý tài liệu định dạng đó.

## 7. Icon và description của loại file

Khóa **icon** chỉ định icon đại diện cho loại file, còn **description** là mô tả ngắn mà hệ điều hành hoặc file manager có thể hiển thị.

Ví dụ:

~~~properties
mime-type=application/vnd.example.inventory
extension=inv
description=Inventory Document
icon=inventory-document.png
~~~

Ví dụ trên dùng PNG cho build Linux. Với build Windows, dùng icon phù hợp như ICO; với macOS, dùng ICNS. Icon phải nằm trong thư mục input của ứng dụng khi đóng gói. Không dùng đường dẫn tuyệt đối trỏ đến máy phát triển, vì máy build khác hoặc máy người dùng không có đường dẫn đó.

Nên dùng icon riêng cho loại file khi ứng dụng xử lý nhiều định dạng và người dùng cần phân biệt nhanh. Nếu tất cả loại file dùng cùng icon ứng dụng, có thể bỏ khóa icon và để hệ điều hành sử dụng icon mặc định.

Định dạng icon và cách hiển thị có thể khác giữa Windows, macOS và Linux. Kiểm tra icon trong installer trên nền tảng thực tế, bao gồm kích thước, nền trong suốt và đường dẫn sau cài đặt.

## 8. Ứng dụng Java nhận đường dẫn file như thế nào?

Khi hệ điều hành mở file thông qua association, launcher khởi chạy ứng dụng và chuyển file cần mở tới tiến trình. Với cách khởi chạy truyền command-line arguments, ứng dụng nhận các đường dẫn trong mảng **args** của phương thức main.

Ví dụ Java:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class InventoryApplication {
    private InventoryApplication() {
    }

    public static void main(String[] args) {
        if (args.length == 0) {
            startWithoutDocument();
            return;
        }

        for (String argument : args) {
            Path file = Path.of(argument);
            openDocument(file);
        }
    }

    private static void startWithoutDocument() {
        System.out.println("InventoryDesk is ready.");
    }

    private static void openDocument(Path file) {
        if (!Files.isRegularFile(file)) {
            System.err.println("File does not exist: " + file);
            return;
        }

        try {
            byte[] content = Files.readAllBytes(file);
            System.out.println("Opened " + file + ", bytes=" + content.length);
        } catch (IOException exception) {
            System.err.println("Cannot read file: " + file);
            exception.printStackTrace();
        }
    }
}
~~~

Đây là ví dụ minh họa luồng nhận file. Ứng dụng thực tế cần parse định dạng, kiểm tra kích thước, xác thực nội dung, xử lý encoding và báo lỗi thân thiện. Không tin tưởng file chỉ vì extension hoặc MIME type khớp với association.

Đường dẫn có thể chứa dấu cách hoặc ký tự Unicode. Hệ điều hành/launcher truyền đối số theo cơ chế riêng của nền tảng; không tự tách chuỗi đường dẫn bằng dấu cách. Dùng từng phần tử của args như một argument hoàn chỉnh.

## 9. Xử lý khi ứng dụng đã chạy

Nếu người dùng mở một file khi ứng dụng chưa chạy, hệ điều hành thường khởi chạy ứng dụng mới với thông tin file. Nếu ứng dụng đã chạy, hành vi phụ thuộc nền tảng, launcher và kiến trúc single-instance của ứng dụng.

Một số ứng dụng sẽ mở tiến trình thứ hai; ứng dụng khác chuyển yêu cầu mở file tới cửa sổ đang chạy thông qua cơ chế riêng. Không giả định mọi hệ điều hành đều gửi file mới vào mảng args của tiến trình cũ.

Nếu sản phẩm cần một cửa sổ duy nhất, hãy thiết kế cơ chế chuyển yêu cầu file giữa các tiến trình, ví dụ local socket hoặc named pipe, rồi kiểm thử riêng trên từng OS. Với macOS, cần kiểm tra hành vi Launch Services và sự kiện mở tài liệu theo cách ứng dụng được đóng gói; không chỉ thử trường hợp app chưa chạy.

## 10. Hành vi theo từng hệ điều hành

| Hệ điều hành | Nơi đăng ký handler | Điều người dùng cần kiểm tra |
|---|---|---|
| Windows | Thông tin file association/ProgID do installer đăng ký trong hệ thống | Open with, Default apps, icon và lệnh mở file. Windows có thể yêu cầu người dùng chọn ứng dụng mặc định. |
| macOS | Metadata document type trong app bundle và Launch Services | Finder nhận diện loại file, Open With, Change All và mở file khi app đang chạy. |
| Linux | Desktop entry và MIME database của desktop environment | Menu, MIME type, xdg-mime, default application và mở file từ file manager. |

jpackage tạo metadata association cho package; hệ điều hành quản lý lựa chọn ứng dụng mặc định. Installer không nên âm thầm ghi đè lựa chọn mặc định của người dùng. Nếu người dùng đã chọn một ứng dụng khác, hệ điều hành có thể tiếp tục ưu tiên lựa chọn đó.

## 11. Windows: đăng ký extension và chọn ứng dụng mặc định

Trên Windows, installer có thể đăng ký khả năng xử lý extension và thông tin ứng dụng tương ứng. Tuy nhiên, Windows hiện đại kiểm soát việc thay đổi ứng dụng mặc định theo lựa chọn của người dùng.

Sau khi cài:

1. Mở Settings > Apps > Default apps.
2. Tìm extension cần kiểm tra, ví dụ .inv.
3. Xem ứng dụng nào đang là mặc định.
4. Nếu cần, người dùng chọn InventoryDesk làm ứng dụng mặc định.
5. Thử mở file bằng double-click và bằng Open with.

Không thiết kế installer dựa trên giả định có thể tự động chiếm quyền mặc định cho mọi extension. Tôn trọng lựa chọn người dùng và kiểm tra luồng Open with.

## 12. macOS: document type và Launch Services

Trên macOS, association được biểu diễn qua metadata của app bundle và được Launch Services sử dụng để tìm ứng dụng có thể mở tài liệu. Sau khi cài app, Finder có thể hiển thị ứng dụng trong Open With cho loại file đã khai báo.

Kiểm tra trên macOS:

1. Cài ứng dụng vào vị trí phân phối dự kiến.
2. Mở Finder và chọn một file có extension đã đăng ký.
3. Mở Get Info để xem loại file và ứng dụng mặc định.
4. Dùng Open With để chọn InventoryDesk nếu muốn.
5. Dùng Change All nếu muốn đặt làm mặc định cho loại file đó.
6. Mở file khi ứng dụng chưa chạy và khi ứng dụng đã chạy.

Không sửa Info.plist sau khi đã ký app bundle. Nếu cần thay đổi association, cập nhật properties file và tạo lại package trước khi ký/notarize.

## 13. Linux: MIME type và desktop entry

Trên Linux, desktop entry có thể khai báo MIME type mà launcher xử lý. jpackage kết hợp file association với metadata desktop của ứng dụng để môi trường desktop tìm được launcher.

Sau khi cài, có thể kiểm tra bằng các lệnh:

~~~bash
xdg-mime query filetype sample.inv
xdg-mime query default application/vnd.example.inventory
~~~

Lệnh đầu kiểm tra MIME type được nhận diện cho file mẫu. Lệnh thứ hai xem desktop entry mặc định cho MIME type nếu desktop environment hỗ trợ xdg-mime.

Nếu muốn đặt mặc định trong môi trường thử nghiệm của một người dùng, có thể dùng:

~~~bash
xdg-mime default inventorydesk.desktop application/vnd.example.inventory
~~~

Tên desktop entry ở ví dụ phải là file .desktop thực tế được cài bởi package. Lệnh này thay đổi lựa chọn mặc định trong môi trường người dùng; không đưa thao tác đó thành bước bắt buộc chạy dưới quyền root trong installer.

Kiểm tra trên GNOME, KDE Plasma hoặc desktop environment được công bố hỗ trợ. Cách hiển thị Open With, menu và default handler có thể khác nhau.

## 14. File association với quy trình app-image hai giai đoạn

Nếu quy trình build tách thành hai giai đoạn:

1. Tạo application image từ JAR và runtime.
2. Tạo installer từ application image.

Hãy truyền **--file-associations** ở giai đoạn tạo installer:

Ví dụ file packaging/inventory-no-icon.properties:

~~~properties
mime-type=application/vnd.example.inventory
extension=inv
description=Inventory Document
~~~

~~~bash
jpackage \
  --type app-image \
  --name InventoryDesk \
  --input build/input \
  --main-jar inventory-app.jar \
  --main-class com.example.inventory.Main \
  --dest build/app-image

jpackage \
  --type deb \
  --name InventoryDesk \
  --app-version 1.4.0 \
  --app-image build/app-image/InventoryDesk \
  --file-associations packaging/inventory-no-icon.properties \
  --dest dist
~~~

Trong ví dụ hai giai đoạn, file properties không khai báo icon để tránh phụ thuộc vào đường dẫn icon trong input directory khi chỉ truyền application image. Application image tự nó không đăng ký association vào hệ điều hành. Việc đăng ký xảy ra khi installer được cài. Nếu cần icon riêng cho association trong quy trình này, hãy kiểm tra cách JDK đang dùng tìm icon, bảo đảm icon có trong input directory mà jpackage yêu cầu và xác minh nội dung package trước khi phát hành.

## 15. Nâng cấp, gỡ cài đặt và xung đột association

File association là metadata của package. Khi phát hành phiên bản mới, giữ các MIME type và extension ổn định nếu định dạng file không thay đổi. Nếu định dạng thay đổi không tương thích, cân nhắc dùng extension hoặc MIME type phiên bản mới để tránh mở nhầm file.

Một số nguyên tắc:

- Không đăng ký extension mà ứng dụng không thực sự hỗ trợ.
- Không dùng MIME type phổ biến của ứng dụng khác chỉ để ứng dụng xuất hiện trong Open With.
- Giữ tên và mô tả association ổn định qua các bản phát hành.
- Kiểm tra installer nâng cấp có giữ handler hay không.
- Kiểm tra gỡ cài đặt có loại bỏ metadata do package đăng ký hay không.
- Không xóa hoặc thay đổi lựa chọn mặc định của ứng dụng khác.
- Sau khi đổi icon hoặc description, cài nâng cấp và kiểm tra cache icon/MIME của hệ điều hành.

Nếu hai ứng dụng cùng đăng ký một extension, hệ điều hành có thể liệt kê cả hai trong Open With. Ứng dụng mặc định vẫn phụ thuộc vào chính sách và lựa chọn của người dùng.

## 16. Bảo vệ ứng dụng khi mở file ngoài

Extension và MIME type chỉ là gợi ý nhận diện, không phải bằng chứng nội dung an toàn. Một file có đuôi .inv vẫn có thể chứa dữ liệu hỏng, dữ liệu giả mạo hoặc nội dung độc hại.

Khi mở file:

1. Chuẩn hóa và kiểm tra đường dẫn.
2. Kiểm tra file tồn tại và là file thường nếu nghiệp vụ yêu cầu.
3. Giới hạn kích thước đầu vào trước khi đọc toàn bộ.
4. Parse theo grammar của định dạng; từ chối cấu trúc không hợp lệ.
5. Không thực thi nội dung hoặc script nhúng chỉ vì file được association.
6. Không ghi đè file gốc khi chưa có hành động rõ ràng của người dùng.
7. Báo lỗi bằng thông tin hữu ích nhưng tránh đưa dữ liệu nhạy cảm vào log.

Với file lớn, dùng streaming API thay vì Files.readAllBytes. Với file nén hoặc định dạng có cấu trúc phức tạp, đặt giới hạn tài nguyên để tránh decompression bomb hoặc tiêu thụ bộ nhớ quá mức.

## 17. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jpackage không tạo association | Properties thiếu cả mime-type và extension | Bổ sung ít nhất một trong hai khóa. |
| Không thấy icon loại file | Icon không nằm trong input directory hoặc tên file sai | Đưa icon vào đúng thư mục input và kiểm tra package. |
| Chỉ extension hoạt động trên một OS | MIME type chưa được khai báo hoặc database desktop chưa cập nhật | Khai báo MIME type phù hợp và kiểm tra trên OS đích. |
| Nhiều loại file cùng mở bằng một cấu hình sai | Gộp nhiều extension vào một properties file không đúng cách | Tạo một file properties cho từng association và lặp --file-associations. |
| Ứng dụng mở nhưng không thấy tài liệu | Main class bỏ qua args | Parse từng argument như đường dẫn file và xử lý. |
| Đường dẫn file có dấu cách bị tách | Ứng dụng tự split chuỗi command line | Dùng từng phần tử trong args; không tách theo dấu cách. |
| Double-click vẫn mở ứng dụng khác | Người dùng đã chọn default handler khác | Kiểm tra Default apps/Open With và cho người dùng chọn ứng dụng. |
| Mở file lần hai không hiện ở cửa sổ đang chạy | Ứng dụng chưa có cơ chế single-instance/open-file forwarding | Thiết kế IPC hoặc xử lý sự kiện nền tảng và kiểm thử riêng. |
| Association mất sau nâng cấp/gỡ cài đặt | Metadata package hoặc installer lifecycle chưa đúng | Kiểm tra association trong package mới và trạng thái sau cài/gỡ. |

## 18. Quy trình kiểm thử file association

Trước khi phát hành, thực hiện các bước sau trên từng hệ điều hành:

1. Tạo một properties file cho mỗi loại file được hỗ trợ.
2. Xác nhận mỗi association có extension hoặc MIME type.
3. Xác nhận icon có trong input directory.
4. Tạo installer bằng đúng JDK và nền tảng đích.
5. Cài ứng dụng trên máy sạch.
6. Xác nhận hệ điều hành nhận diện extension/MIME type và liệt kê ứng dụng.
7. Mở file bằng double-click, Open With và từ launcher.
8. Kiểm tra đường dẫn nhận được trong args và nội dung mở đúng.
9. Thử đường dẫn có dấu cách, Unicode, file không tồn tại và file sai định dạng.
10. Mở thêm file khi ứng dụng đã chạy để kiểm tra hành vi single-instance.
11. Nâng cấp từ bản trước và xác nhận association vẫn hoạt động.
12. Gỡ cài đặt và kiểm tra handler/metadata được xử lý đúng.

Không chỉ kiểm thử trên máy build. Default app và MIME database có thể đã bị thay đổi bởi ứng dụng khác hoặc cấu hình người dùng; nên dùng máy ảo sạch hoặc tài khoản thử nghiệm mới.

## 19. Cách áp dụng trong quy trình Java hiện đại

- Dùng **--file-associations** để khai báo loại file mà ứng dụng thật sự hỗ trợ.
- Tạo một properties file riêng cho mỗi association và truyền tùy chọn nhiều lần.
- Khai báo ít nhất mime-type hoặc extension; nên khai báo cả hai nếu có thông tin chính xác.
- Đưa icon vào input directory và dùng đường dẫn resource không phụ thuộc máy build.
- Parse file path từ args và hỗ trợ dấu cách, Unicode, nhiều file.
- Kiểm tra file theo nội dung thực tế; không tin extension hoặc MIME type như cơ chế bảo mật.
- Phân biệt đăng ký handler với việc chọn ứng dụng mặc định.
- Kiểm thử hành vi trên Windows, macOS và Linux, cả khi app chưa chạy và đã chạy.
- Kiểm tra association sau nâng cấp và gỡ cài đặt.

**--file-associations** giúp package khai báo các loại tài liệu mà ứng dụng có thể xử lý. Tệp properties giữ thông tin extension, MIME type, description và icon; hệ điều hành dùng metadata đó để tìm launcher phù hợp. Ứng dụng cần nhận và xác thực đường dẫn file, còn lựa chọn handler mặc định vẫn do hệ điều hành và người dùng kiểm soát.

## Tài liệu tham khảo

- [Oracle JDK 16 — Support Application Requirements: Set File Associations](https://docs.oracle.com/en/java/javase/16/jpackage/support-application-features.html)
- [Oracle JDK 16 — The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Oracle JDK 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [freedesktop.org — Shared MIME-info Database Specification](https://specifications.freedesktop.org/shared-mime-info/latest/)
- [freedesktop.org — Desktop Entry Specification](https://specifications.freedesktop.org/desktop-entry/latest/)
- [freedesktop.org — MIME Applications Specification](https://specifications.freedesktop.org/mime-apps/latest/)
- [Microsoft Support — Change Default Apps in Windows](https://support.microsoft.com/en-us/windows/apps/change-default-apps-in-windows)
- [Apple — CFBundleDocumentTypes](https://developer.apple.com/documentation/bundleresources/information-property-list/cfbundledocumenttypes)
