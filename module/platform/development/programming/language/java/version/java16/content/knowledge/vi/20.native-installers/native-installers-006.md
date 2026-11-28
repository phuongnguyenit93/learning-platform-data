# Windows launcher console, shortcut và menu bằng tùy chọn jpackage

Khi đóng gói ứng dụng Java cho Windows bằng **jpackage**, có thể cấu hình cách launcher tương tác với console và cách installer tạo lối tắt cho người dùng. Các tùy chọn chính gồm **--win-console**, **--win-shortcut**, **--win-shortcut-prompt**, **--win-menu** và **--win-menu-group**.

Những tùy chọn này phục vụ hai phần khác nhau của trải nghiệm cài đặt. **--win-console** quyết định loại launcher được tạo để ứng dụng có thể tương tác với cửa sổ console. Các tùy chọn shortcut và menu điều khiển lối tắt được tạo trong quá trình cài đặt. Chọn đúng tùy chọn giúp ứng dụng CLI có console để nhập/xuất, ứng dụng GUI không mở cửa sổ console thừa và người dùng tìm thấy ứng dụng từ Desktop hoặc Start Menu.

Trong module Java 16, **jpackage** là công cụ đóng gói đã được hoàn thiện và các tùy chọn Windows này vẫn hữu ích trong quy trình phát hành Java hiện đại. Bài này tập trung vào loại launcher, shortcut Desktop, Start Menu, nhóm menu, phạm vi cài đặt và cách kiểm thử MSI/EXE sau khi cài. Không dùng các kỹ thuật đóng gói thử nghiệm hoặc đã lỗi thời.

## 1. Phân biệt launcher và shortcut

Launcher là chương trình native khởi chạy ứng dụng Java từ application image. Shortcut là lối tắt trỏ đến launcher đã cài đặt.

| Thành phần | Vai trò | Tùy chọn liên quan |
|---|---|---|
| Windows launcher | Khởi chạy JVM và lớp main của ứng dụng | **--win-console** |
| Desktop shortcut | Tạo lối tắt trên Desktop | **--win-shortcut** |
| Shortcut trong Start Menu | Thêm ứng dụng vào Start Menu | **--win-menu** |
| Nhóm trong Start Menu | Chọn thư mục nhóm chứa shortcut | **--win-menu-group** |
| Hộp thoại chọn shortcut | Cho người dùng quyết định có tạo shortcut hay không trong installer | **--win-shortcut-prompt** |

Tạo shortcut không thay đổi loại launcher. Ví dụ, **--win-shortcut** không làm ứng dụng có console; nó chỉ tạo lối tắt đến launcher. Tương tự, **--win-console** không tự tạo Desktop shortcut hoặc Start Menu entry.

## 2. Chọn launcher có console hay không

### Ứng dụng CLI cần console

Với ứng dụng dòng lệnh có đọc dữ liệu từ bàn phím, ghi kết quả ra console hoặc cần tương tác qua terminal, dùng **--win-console**:

~~~powershell
jpackage --type msi --name InventoryCLI --app-version 1.4.0 --input build\libs --main-jar inventory-cli.jar --main-class com.example.inventory.Main --win-console --dest dist
~~~

Tùy chọn này yêu cầu jpackage tạo console launcher cho ứng dụng. Khi người dùng khởi chạy từ shortcut hoặc File Explorer, launcher có thể mở cửa sổ console để hiển thị output và nhận input.

Ứng dụng phù hợp với console launcher thường có các đặc điểm:

- Dùng System.in để nhận lệnh hoặc dữ liệu.
- Dùng System.out/System.err để hiển thị kết quả và thông báo lỗi.
- Chạy tác vụ CLI cần hiển thị tiến trình hoặc trạng thái cho người dùng.
- Có quy trình tương tác yêu cầu người dùng nhập thông tin trong cửa sổ console.

### Ứng dụng GUI không cần console

Với ứng dụng Swing, JavaFX hoặc ứng dụng desktop có giao diện riêng, thông thường không thêm **--win-console**:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.ui.Main --dest dist
~~~

Launcher GUI không mở cửa sổ console phụ khi người dùng khởi chạy ứng dụng. Nếu ứng dụng cần ghi log để chẩn đoán, nên dùng logging framework và lưu log vào vùng dữ liệu phù hợp của người dùng hoặc hệ thống. Không phụ thuộc vào việc người dùng nhìn thấy System.out hoặc System.err từ ứng dụng GUI.

### Vì sao chọn sai launcher gây bất tiện?

- CLI không có console: người dùng không có cửa sổ phù hợp để nhập lệnh hoặc xem output tương tác; System.console() có thể trả về null khi không có console gắn với tiến trình.
- GUI có console không cần thiết: mỗi lần mở ứng dụng có thể xuất hiện thêm cửa sổ console, gây rối trải nghiệm.
- Chỉ tạo shortcut: shortcut vẫn mở launcher hiện có; nó không thay đổi cách launcher xử lý console.

Hãy chọn loại launcher theo cách ứng dụng được thiết kế để tương tác với người dùng.

## 3. Tạo Desktop shortcut bằng --win-shortcut

Tùy chọn **--win-shortcut** yêu cầu installer tạo Desktop shortcut cho ứng dụng:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.ui.Main --win-shortcut --dest dist
~~~

Sau khi cài đặt, người dùng có thể mở ứng dụng từ Desktop mà không cần tìm thư mục cài đặt. Shortcut trỏ đến launcher được tạo trong application image và được cài cùng ứng dụng.

Lưu ý:

- **--win-shortcut** là yêu cầu tạo shortcut khi cài đặt package; không phải tùy chọn đổi vị trí cài ứng dụng.
- Shortcut không chứa bản sao riêng của JAR hoặc runtime; nó trỏ đến launcher của ứng dụng đã cài.
- Nếu cài đặt per-user, shortcut thường thuộc phạm vi người dùng đó; nếu cài đặt per-machine, phạm vi shortcut phụ thuộc cơ chế installer và cấu hình package.
- Sau khi thay tên ứng dụng hoặc launcher, kiểm tra lại tên và đích shortcut trong bản cài mới.

## 4. Cho phép người dùng chọn shortcut với --win-shortcut-prompt

Nếu muốn installer hỏi người dùng có tạo shortcut hay không, kết hợp **--win-shortcut-prompt** với **--win-shortcut**:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.ui.Main --win-shortcut --win-shortcut-prompt --dest dist
~~~

**--win-shortcut-prompt** thêm hộp thoại để người dùng chọn có tạo shortcut do installer cung cấp hay không. Đây là lựa chọn phù hợp khi muốn hỗ trợ shortcut nhưng vẫn để người dùng quyết định Desktop của họ có thêm biểu tượng hay không.

Nếu không cần hỏi, chỉ dùng **--win-shortcut**. Nếu không muốn installer yêu cầu tạo shortcut Desktop, bỏ cả hai tùy chọn. Hãy kiểm tra giao diện installer thực tế vì trải nghiệm có thể phụ thuộc loại package và phiên bản JDK.

## 5. Thêm ứng dụng vào Start Menu bằng --win-menu

Tùy chọn **--win-menu** yêu cầu tạo Start Menu shortcut:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.ui.Main --win-menu --dest dist
~~~

Sau khi cài, người dùng có thể tìm ứng dụng trong Start Menu. Đây là lối mở ứng dụng quen thuộc trên Windows, đặc biệt với ứng dụng desktop được cài thường xuyên.

**--win-menu** chỉ yêu cầu tạo Start Menu shortcut. Nó không tạo Desktop shortcut; muốn có cả hai, dùng thêm **--win-shortcut**.

## 6. Sắp xếp Start Menu bằng --win-menu-group

Khi có nhiều ứng dụng cùng nhà phát hành, có thể đặt shortcut vào một nhóm Start Menu:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.ui.Main --win-menu --win-menu-group "Example Tools" --dest dist
~~~

**--win-menu-group** đặt tên nhóm Start Menu mà shortcut của ứng dụng được đưa vào. Ví dụ, nhóm Example Tools có thể chứa InventoryDesk, ReportViewer và các ứng dụng khác của cùng bộ sản phẩm.

Nên giữ tên nhóm ổn định giữa các bản phát hành để tránh tạo nhiều thư mục gần giống nhau trong Start Menu. Tùy chọn này có ý nghĩa khi tạo Start Menu entry; kết hợp nó với **--win-menu** để yêu cầu tạo entry.

## 7. Kết hợp menu và shortcut trong một installer

Một ứng dụng desktop thông thường có thể cung cấp cả Start Menu và Desktop shortcut:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.ui.Main --win-menu --win-menu-group "Example Tools" --win-shortcut --win-shortcut-prompt --dest dist
~~~

Ý nghĩa của các tùy chọn:

- **--win-menu**: yêu cầu tạo shortcut trong Start Menu.
- **--win-menu-group**: đặt shortcut vào nhóm Example Tools.
- **--win-shortcut**: yêu cầu tạo Desktop shortcut.
- **--win-shortcut-prompt**: cho phép người dùng chọn có tạo Desktop shortcut hay không trong installer.

Nếu sản phẩm chỉ muốn xuất hiện trong Start Menu, bỏ **--win-shortcut** và **--win-shortcut-prompt**. Nếu chỉ muốn Desktop shortcut, bỏ **--win-menu** và **--win-menu-group**.

## 8. Cấu hình launcher ở giai đoạn tạo application image

**--win-console** là tùy chọn tạo launcher. Khi dùng quy trình hai giai đoạn, cần đặt tùy chọn này lúc tạo application image:

~~~powershell
jpackage --type app-image --name InventoryCLI --input build\libs --main-jar inventory-cli.jar --main-class com.example.inventory.Main --win-console --dest build\app-image
~~~

Sau khi kiểm thử launcher trong image, tạo MSI từ image đó:

~~~powershell
jpackage --type msi --name InventoryCLI --app-version 1.4.0 --app-image build\app-image\InventoryCLI --win-menu --win-menu-group "Example Tools" --win-shortcut --dest dist
~~~

Ở giai đoạn thứ hai, **--app-image** đã chứa launcher được tạo ở giai đoạn đầu. Các tùy chọn menu và shortcut được áp dụng khi tạo installer. Không thể trông chờ thêm **--win-console** ở giai đoạn installer để thay đổi launcher đã có; nếu cần đổi kiểu console, hãy tạo lại application image với cấu hình launcher mong muốn rồi đóng gói lại.

## 9. Tạo launcher GUI và CLI riêng cho cùng ứng dụng

Một sản phẩm có thể cung cấp giao diện desktop và một công cụ CLI. Khi đó, có thể tạo launcher chính và launcher bổ sung bằng **--add-launcher**. File properties của launcher bổ sung cho phép đặt main class và thuộc tính Windows riêng, trong đó có **win-console**.

Ví dụ file properties cho launcher CLI, lưu tại cli-launcher.properties:

~~~properties
main-class=com.example.inventory.cli.Main
win-console=true
~~~

Tạo application image với launcher chính GUI và launcher bổ sung CLI:

~~~powershell
jpackage --type app-image --name InventorySuite --input build\libs --main-jar inventory-suite.jar --main-class com.example.inventory.ui.Main --add-launcher InventoryCLI=cli-launcher.properties --dest build\app-image
~~~

Launcher chính InventorySuite không dùng **--win-console**, nên phù hợp với GUI. Launcher InventoryCLI có **win-console=true** trong file properties, nên được tạo theo kiểu console launcher.

Sau khi kiểm thử cả hai launcher, có thể tạo installer:

~~~powershell
jpackage --type msi --name InventorySuite --app-version 1.4.0 --app-image build\app-image\InventorySuite --win-menu --win-menu-group "Example Tools" --win-shortcut --dest dist
~~~

Tùy chọn và properties được hỗ trợ có thể khác giữa các major JDK. Kiểm tra danh sách khóa của **--add-launcher** trong **jpackage --help** của đúng JDK. Với launcher bổ sung, cần kiểm thử riêng cách tạo shortcut/menu và đích launcher trong installer cuối.

## 10. Kết hợp phạm vi cài đặt per-user

Tùy chọn **--win-per-user-install** yêu cầu installer cài ứng dụng cho người dùng hiện tại:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.ui.Main --win-per-user-install --win-menu --win-menu-group "Example Tools" --win-shortcut --dest dist
~~~

Phạm vi cài đặt ảnh hưởng đến vị trí cài chương trình và phạm vi shortcut được tạo. Dùng per-user khi ứng dụng dành cho tài khoản đang cài và không cần triển khai dùng chung toàn máy. Dùng cài đặt per-machine khi IT cần cài ứng dụng cho nhiều tài khoản và có quyền quản trị phù hợp.

Không nhầm **--win-per-user-install** với việc lưu dữ liệu cá nhân. Dữ liệu cấu hình và file người dùng vẫn cần đặt trong AppData hoặc vùng dữ liệu phù hợp của từng tài khoản, bất kể ứng dụng được cài theo user hay toàn máy.

## 11. Chọn EXE hay MSI

Các tùy chọn launcher, menu và shortcut là cấu hình Windows của jpackage; loại package có thể là EXE hoặc MSI nếu JDK và toolchain hỗ trợ.

| Nhu cầu | Định dạng nên cân nhắc |
|---|---|
| Phân phối cho người dùng tự tải và chạy trình cài đặt | EXE |
| Triển khai bằng Windows Installer hoặc công cụ quản trị doanh nghiệp | MSI |
| Tạo application image để chạy thử trước | app-image |

Các tùy chọn **--win-console**, **--win-menu**, **--win-menu-group**, **--win-shortcut** và **--win-shortcut-prompt** không thay thế việc chọn loại package. Hãy kiểm tra loại đầu ra được JDK hiện tại hỗ trợ bằng **jpackage --help**.

## 12. Kiểm thử sau khi cài đặt

Sau khi tạo EXE hoặc MSI, cài trên máy Windows sạch hoặc máy ảo tương ứng với phạm vi cài đặt dự kiến. Kiểm tra:

1. Launcher chạy đúng ứng dụng và đúng main class.
2. CLI mở cửa sổ console và có thể nhận input/hiển thị output khi cần.
3. GUI mở cửa sổ giao diện mà không xuất hiện console thừa.
4. Start Menu có shortcut khi dùng **--win-menu**.
5. Shortcut nằm trong nhóm mong muốn khi dùng **--win-menu-group**.
6. Desktop shortcut được tạo khi chọn tạo shortcut; nếu dùng **--win-shortcut-prompt**, xác nhận cả hai lựa chọn của người dùng.
7. Shortcut trỏ đúng launcher sau khi cài hoặc nâng cấp.
8. Phạm vi per-user/per-machine và quyền cài đặt đúng với thiết kế.
9. Nâng cấp từ phiên bản trước không tạo shortcut trùng hoặc để lại nhóm menu cũ ngoài ý muốn.
10. Gỡ cài đặt loại bỏ shortcut và entry do package tạo theo đúng chính sách.

Kiểm thử cả trường hợp người dùng chọn không tạo shortcut. Không kết luận tùy chọn hoạt động chỉ vì lệnh jpackage trả về thành công; cần xác nhận lối tắt trong Windows Start Menu và Desktop sau khi installer chạy.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ứng dụng CLI không có console tương tác | Application image được tạo không có **--win-console** | Tạo lại launcher/application image với **--win-console**. |
| Ứng dụng GUI mở thêm cửa sổ console | Đã bật **--win-console** cho launcher GUI | Tạo lại launcher GUI và bỏ tùy chọn đó. |
| Không có Desktop shortcut | Thiếu **--win-shortcut** hoặc người dùng chọn không tạo trong prompt | Kiểm tra tùy chọn và lựa chọn trong installer. |
| Không thấy ứng dụng trong Start Menu | Thiếu **--win-menu** | Thêm **--win-menu** khi tạo installer. |
| Shortcut nằm sai nhóm | Tên **--win-menu-group** không đúng hoặc menu group không được yêu cầu | Kiểm tra tên nhóm và kết hợp với **--win-menu**. |
| Thêm **--win-console** khi đóng gói từ image nhưng launcher không đổi | Launcher đã được tạo trước đó trong app-image | Tạo lại app-image với cấu hình launcher đúng. |
| Có nhiều shortcut hoặc tên launcher khó phân biệt | Cấu hình nhiều launcher nhưng không kiểm tra riêng từng launcher | Đặt tên launcher rõ ràng và kiểm thử shortcut của từng launcher. |

## 14. Cách áp dụng trong quy trình phát hành Java hiện đại

- Chọn **--win-console** cho launcher cần tương tác console; bỏ tùy chọn với GUI không cần console.
- Dùng **--win-shortcut** khi muốn cung cấp Desktop shortcut.
- Kết hợp **--win-shortcut-prompt** khi muốn người dùng chọn có tạo shortcut hay không.
- Dùng **--win-menu** để tạo Start Menu entry và **--win-menu-group** để sắp xếp nhóm.
- Khi dùng **--app-image**, tạo launcher đúng kiểu ở giai đoạn application image; áp dụng menu/shortcut ở giai đoạn installer.
- Dùng **--win-per-user-install** khi cần cài theo tài khoản hiện tại; tách dữ liệu người dùng khỏi thư mục chương trình.
- Kiểm thử launcher, shortcut, Start Menu, nâng cấp và gỡ cài đặt trên Windows sạch.
- Xác nhận tùy chọn với **jpackage --help** của đúng JDK và lưu cấu hình đóng gói trong quy trình build có kiểm soát.

Các tùy chọn Windows của jpackage giúp định hình cách người dùng mở ứng dụng sau cài đặt. **--win-console** phù hợp với chương trình CLI cần tương tác, còn **--win-shortcut**, **--win-menu** và **--win-menu-group** tổ chức lối truy cập từ Desktop và Start Menu. Tách đúng cấu hình launcher khỏi cấu hình installer và kiểm thử trên máy Windows sạch giúp bộ cài có trải nghiệm nhất quán qua các lần phát hành.
