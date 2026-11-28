# Windows cài theo người dùng và quản lý --win-upgrade-uuid

Khi phát hành ứng dụng Java trên Windows bằng **jpackage**, cần quyết định ứng dụng được cài cho một tài khoản hay cho toàn bộ máy, đồng thời thiết lập mã nhận diện nâng cấp ổn định giữa các phiên bản. Hai tùy chọn quan trọng là **--win-per-user-install** và **--win-upgrade-uuid**.

**--win-per-user-install** chọn installation context của Windows Installer. **--win-upgrade-uuid** cung cấp GUID để Windows Installer nhận diện các phiên bản thuộc cùng một sản phẩm khi thực hiện major upgrade. Hai tùy chọn giải quyết hai vấn đề khác nhau: một tùy chọn quyết định phạm vi cài đặt, tùy chọn còn lại xác định quan hệ giữa các phiên bản.

Trong module Java 16, jpackage đã là công cụ đóng gói ổn định. Bài này tập trung vào MSI/EXE trên Windows, cài đặt per-user/per-machine, cách giữ UpgradeCode qua các bản phát hành và kiểm thử nâng cấp. Các hướng dẫn chỉ sử dụng Windows Installer và tùy chọn jpackage còn áp dụng; không dùng công cụ đóng gói Java cũ đã legacy.

## 1. Phân biệt cài đặt per-user và per-machine

Windows Installer hỗ trợ hai installation context:

- **Per-user:** ứng dụng được cài cho tài khoản Windows đang thực hiện cài đặt. Shortcut và thông tin đăng ký ứng dụng thuộc profile của tài khoản đó.
- **Per-machine:** ứng dụng được cài dùng chung trên máy. Shortcut và thông tin đăng ký được tạo trong phạm vi toàn hệ thống; thao tác cài đặt thường cần quyền quản trị.

Với jpackage, **--win-per-user-install** yêu cầu cài đặt theo người dùng. Nếu không chỉ định tùy chọn này, MSI do jpackage tạo mặc định cài theo phạm vi toàn máy.

| Tiêu chí | Per-user | Per-machine |
|---|---|---|
| Người dùng sử dụng | Tài khoản cài đặt | Các tài khoản trên máy |
| Phạm vi shortcut | Profile người dùng cài | Profile chung của máy |
| Registry | Chủ yếu theo nhánh người dùng | Chủ yếu theo nhánh hệ thống |
| Quyền cài đặt | Thường không cần quyền quản trị | Thường cần quyền quản trị |
| Vị trí chương trình | Vùng cài đặt user-level | Vùng cài đặt toàn máy |
| Phù hợp với | Ứng dụng desktop cá nhân, người dùng tự cài | Máy doanh nghiệp, triển khai tập trung, ứng dụng dùng chung |

Chọn context ngay từ thiết kế phát hành. Nếu ứng dụng cần dùng chung cho nhiều tài khoản hoặc được triển khai qua công cụ quản trị thiết bị, per-machine thường phù hợp. Nếu người dùng tự cài mà không có quyền quản trị, per-user thường thuận tiện hơn.

## 2. Dùng --win-per-user-install

Ví dụ tạo MSI cài theo tài khoản hiện tại:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.Main --win-per-user-install --win-menu --win-shortcut --dest dist
~~~

Trong lệnh này:

- **--type msi** tạo gói Windows Installer.
- **--win-per-user-install** yêu cầu cài ứng dụng cho người dùng hiện tại.
- **--win-menu** yêu cầu tạo shortcut Start Menu trong phạm vi người dùng.
- **--win-shortcut** yêu cầu tạo Desktop shortcut trong phạm vi người dùng.
- **--app-version** đặt phiên bản ứng dụng/package.

Nếu muốn cài cho toàn máy, bỏ **--win-per-user-install**:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.Main --win-menu --win-shortcut --dest dist
~~~

Với cài đặt per-machine, cần kiểm thử bằng tài khoản có quyền cài đặt phù hợp. Với per-user, kiểm tra ứng dụng chỉ xuất hiện trong danh sách ứng dụng và shortcut của tài khoản đã cài.

## 3. UpgradeCode và ProductCode trong Windows Installer

MSI sử dụng hai GUID quan trọng để quản lý sản phẩm và nâng cấp:

| Mã | Ý nghĩa | Quy tắc qua các phiên bản |
|---|---|---|
| **UpgradeCode** | Nhận diện một họ sản phẩm gồm các phiên bản liên quan | Giữ nguyên cho các phiên bản của cùng một sản phẩm. |
| **ProductCode** | Nhận diện một sản phẩm/release cụ thể trong Windows Installer | Thay đổi khi tạo major upgrade. |

Ví dụ, InventoryDesk 1.4.0 và InventoryDesk 1.5.0 là hai phiên bản của cùng sản phẩm. Hai MSI cần cùng UpgradeCode để Windows Installer nhận diện quan hệ giữa chúng; ProductCode của bản phát hành mới phải khác ProductCode của bản cũ.

Không dùng một UpgradeCode chung cho những ứng dụng độc lập chỉ vì chúng cùng nhà phát hành. Nếu Windows Installer coi hai ứng dụng không liên quan là cùng một họ sản phẩm, quá trình tìm và gỡ phiên bản cũ có thể tác động nhầm sản phẩm.

## 4. --win-upgrade-uuid làm gì?

Tùy chọn **--win-upgrade-uuid** truyền GUID dùng làm UpgradeCode cho package Windows:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.Main --win-upgrade-uuid 7F3A9E20-6D41-4B8C-9A2E-5F6C1D0B8A74 --dest dist
~~~

Giá trị ví dụ có dạng GUID chuẩn: 8 ký tự, 4 ký tự, 4 ký tự, 4 ký tự và 12 ký tự, ngăn cách bằng dấu gạch nối. Hãy tạo GUID riêng cho sản phẩm của bạn và lưu nó trong cấu hình build.

Khi phát hành phiên bản tiếp theo của InventoryDesk, dùng lại đúng GUID đó:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.5.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.Main --win-upgrade-uuid 7F3A9E20-6D41-4B8C-9A2E-5F6C1D0B8A74 --dest dist
~~~

Điều quan trọng là GUID không đổi giữa các lần build của cùng sản phẩm. Không tạo GUID mới trong mỗi pipeline hoặc mỗi bản phát hành, vì khi đó MSI mới có thể không nhận ra MSI cũ là phiên bản liên quan.

Nếu không chỉ định **--win-upgrade-uuid**, jpackage tự chọn giá trị mặc định khi tạo package. Không dựa vào giá trị mặc định đó như định danh nâng cấp được quản lý lâu dài; hãy cung cấp GUID tường minh nếu muốn kiểm soát quan hệ giữa các phiên bản.

## 5. Giữ UpgradeCode ổn định qua các bản phát hành

Nên lưu GUID trong cấu hình phát hành có kiểm soát, chẳng hạn biến cấu hình của pipeline hoặc file cấu hình build được quản lý trong repository. GUID không phải secret, vì vậy không cần lưu như mật khẩu; điều cần bảo vệ là tính nhất quán của giá trị.

Quy tắc thực hành:

1. Tạo một GUID cho sản phẩm khi chuẩn bị MSI đầu tiên.
2. Dùng GUID đó trong mọi bản phát hành tiếp theo của cùng sản phẩm.
3. Không sinh GUID mới khi nâng version, đổi JDK, đổi máy build hoặc chạy lại CI.
4. Dùng GUID khác cho sản phẩm độc lập.
5. Chỉ thay UpgradeCode khi thực sự tạo một dòng sản phẩm mới hoặc thay đổi chiến lược nhận diện sản phẩm; khi đó cần có kế hoạch chuyển đổi từ bản cũ.
6. Lưu GUID cùng cấu hình build để mọi nhánh release và runner đều sử dụng cùng giá trị.

Ví dụ PowerShell lấy GUID từ biến môi trường để tránh chép tay ở nhiều lệnh:

~~~powershell
$upgradeCode = "7F3A9E20-6D41-4B8C-9A2E-5F6C1D0B8A74"
jpackage --type msi --name InventoryDesk --app-version 1.5.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.Main --win-upgrade-uuid $upgradeCode --dest dist
~~~

Trong CI thực tế, có thể đưa giá trị này vào biến cấu hình dùng chung cho mọi job phát hành. Không tạo GUID bằng lệnh ngẫu nhiên trong từng lần build.

## 6. ProductCode khác UpgradeCode như thế nào?

**ProductCode** nhận diện một sản phẩm cụ thể trong Windows Installer. Với jpackage, ProductCode được tạo trong quá trình đóng gói MSI; người dùng không truyền ProductCode qua **--win-upgrade-uuid**.

Khi phát hành major upgrade:

- Phiên bản ứng dụng thay đổi, ví dụ từ 1.4.0 lên 1.5.0.
- ProductCode của MSI mới phải khác ProductCode của MSI cũ.
- UpgradeCode vẫn giữ nguyên để Windows Installer tìm phiên bản liên quan.
- Windows Installer dùng thông tin phiên bản và Upgrade Table để xác định sản phẩm cũ cần nâng cấp.

Không cố dùng cùng một GUID cho cả ProductCode và UpgradeCode. Chúng có vai trò khác nhau trong mô hình Windows Installer.

## 7. Kết hợp per-user với UpgradeCode

Ví dụ phát hành ứng dụng cài theo người dùng và hỗ trợ nhận diện nâng cấp:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.4.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.Main --win-per-user-install --win-upgrade-uuid 7F3A9E20-6D41-4B8C-9A2E-5F6C1D0B8A74 --win-menu --win-shortcut --dest dist
~~~

Ở bản 1.5.0, giữ nguyên cả hai tùy chọn:

~~~powershell
jpackage --type msi --name InventoryDesk --app-version 1.5.0 --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.Main --win-per-user-install --win-upgrade-uuid 7F3A9E20-6D41-4B8C-9A2E-5F6C1D0B8A74 --win-menu --win-shortcut --dest dist
~~~

Hai phần cần giữ ổn định:

- **Installation context:** tiếp tục dùng **--win-per-user-install** nếu bản cũ đã cài per-user.
- **Upgrade identity:** tiếp tục dùng cùng **--win-upgrade-uuid** để nhận diện cùng dòng sản phẩm.

Nếu sản phẩm cài per-machine, bỏ **--win-per-user-install** trong mọi phiên bản theo cùng chiến lược đó. Không đổi context tùy tiện giữa các lần nâng cấp.

## 8. Không thể major upgrade xuyên qua installation context

Windows Installer không thực hiện major upgrade giữa hai installation context khác nhau:

- Bản cũ cài per-user thì bản nâng cấp cũng phải chạy per-user.
- Bản cũ cài per-machine thì bản nâng cấp cũng phải chạy per-machine.

Ví dụ, nếu MSI 1.4.0 được tạo với **--win-per-user-install**, còn MSI 1.5.0 bỏ tùy chọn này và cài per-machine, việc giữ nguyên **--win-upgrade-uuid** không làm Windows Installer chuyển bản cài cũ sang context mới.

Nếu sản phẩm bắt buộc chuyển từ per-user sang per-machine, hãy thiết kế một quy trình migration riêng:

1. Xác định dữ liệu người dùng cần giữ và vị trí lưu dữ liệu.
2. Sao lưu hoặc di chuyển dữ liệu theo chính sách đã công bố.
3. Gỡ bản cài trong context cũ theo đúng tài khoản/context.
4. Cài MSI mới trong context đích.
5. Khôi phục hoặc chuyển dữ liệu và kiểm tra quyền truy cập.
6. Xác minh shortcut, registry, file association và entry trong danh sách ứng dụng.

Không coi việc đổi hoặc giữ UpgradeCode là công cụ chuyển context. Đây là hai phần cấu hình độc lập.

## 9. Phiên bản MSI và điều kiện nhận diện nâng cấp

**--app-version** đặt phiên bản ứng dụng/package mà jpackage đưa vào metadata installer. Windows Installer sử dụng ProductVersion khi tìm các phiên bản liên quan trong quá trình major upgrade.

Đối với MSI, Windows Installer chỉ xét ba trường đầu của ProductVersion. Nếu đặt phiên bản bốn trường như 1.5.0.12, trường thứ tư không được dùng để phân biệt thứ tự phiên bản trong tìm kiếm major upgrade.

Nên dùng phiên bản số có tối đa ba thành phần cho MSI, ví dụ:

| Phiên bản phát hành | ProductVersion dùng cho MSI | Ghi chú |
|---|---|---|
| 1.4.0 | 1.4.0 | Bản đầu tiên trong ví dụ. |
| 1.5.0 | 1.5.0 | Bản mới hơn, có thể nâng cấp 1.4.0. |
| 1.5.1 | 1.5.1 | Bản sửa lỗi tiếp theo. |
| 2.0.0 | 2.0.0 | Major release tiếp theo. |

Tăng một trong ba trường theo chính sách phát hành. Không chỉ thay số build ở trường thứ tư rồi kỳ vọng Windows Installer nhận ra đó là phiên bản mới hơn.

UpgradeCode là điều kiện để nhận diện họ sản phẩm, nhưng quá trình major upgrade còn phụ thuộc ProductVersion, ngôn ngữ và cấu hình Upgrade Table của MSI. Hãy kiểm thử installer thực tế thay vì chỉ xác nhận lệnh jpackage tạo file thành công.

## 10. --win-upgrade-uuid không phải cơ chế tự cập nhật

**--win-upgrade-uuid** không tải phiên bản mới từ Internet, không kiểm tra máy chủ cập nhật và không tự chạy installer mới. Nó thiết lập mã nhận diện liên quan giữa các MSI để Windows Installer có thể phát hiện phiên bản cũ khi người dùng chạy gói nâng cấp.

Ứng dụng vẫn cần kênh phân phối phiên bản mới, chẳng hạn website, hệ thống quản trị phần mềm hoặc cơ chế cập nhật riêng. Khi MSI mới được chạy, Windows Installer dùng metadata trong package để xác định cách xử lý sản phẩm cũ.

Nếu cần tự động kiểm tra bản mới và tải installer, hãy thiết kế updater hoặc tích hợp hệ thống phân phối riêng. Không nhầm UpgradeCode với URL cập nhật hay logic tự cập nhật trong ứng dụng.

## 11. Kiểm thử nâng cấp trên Windows

Nên kiểm thử trong máy ảo hoặc máy Windows sạch để tránh trạng thái cài đặt cũ từ các thử nghiệm trước:

1. Cài MSI 1.4.0 với installation context dự kiến.
2. Xác nhận ứng dụng xuất hiện trong đúng phạm vi người dùng hoặc toàn máy.
3. Tạo dữ liệu người dùng và cấu hình để kiểm tra việc bảo toàn.
4. Chạy MSI 1.5.0 với cùng UpgradeCode và cùng installation context.
5. Xác nhận phiên bản cũ được xử lý theo major upgrade và bản mới được cài.
6. Kiểm tra shortcut, Start Menu, file association và vị trí cài đặt.
7. Xác nhận dữ liệu người dùng còn nguyên hoặc đã được migration đúng.
8. Kiểm tra gỡ cài đặt bản mới và chính sách giữ/xóa dữ liệu.
9. Thử chạy installer trong context khác để xác nhận quy trình phát hành không vô tình thay đổi per-user/per-machine.
10. Kiểm tra log Windows Installer nếu upgrade không phát hiện bản cũ.

Không kiểm thử nâng cấp bằng cách chỉ chạy MSI mới trên máy chưa từng cài bản cũ. Cần có trạng thái phiên bản cũ đúng với context phát hành thực tế.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| MSI mới cài song song với bản cũ | UpgradeCode thay đổi giữa hai lần build hoặc Upgrade Table không nhận diện version cũ | Dùng lại GUID ổn định, kiểm tra ProductVersion và test major upgrade. |
| UpgradeCode giống nhau nhưng bản cũ không được nâng cấp | Context per-user/per-machine khác nhau hoặc version không được nhận diện là mới hơn | Giữ cùng context và tăng một trong ba trường ProductVersion. |
| Mỗi lần CI build tạo ra một dòng sản phẩm mới | GUID được tạo ngẫu nhiên trong pipeline hoặc không truyền tùy chọn ổn định | Lưu GUID cố định trong cấu hình release và truyền bằng --win-upgrade-uuid. |
| Hai ứng dụng độc lập ảnh hưởng lẫn nhau khi nâng cấp | Dùng chung UpgradeCode cho sản phẩm không liên quan | Tạo UpgradeCode riêng cho mỗi sản phẩm độc lập. |
| Bản mới không được nhận diện là mới hơn | Chỉ thay trường version thứ tư | Dùng tối đa ba trường ProductVersion và tăng đúng trường. |
| Chuyển per-user sang per-machine không nâng cấp được | Windows Installer không major upgrade xuyên context | Thiết kế migration/uninstall/install riêng và bảo toàn dữ liệu. |
| Gỡ bản cũ làm mất dữ liệu cá nhân | Dữ liệu nằm trong thư mục cài đặt hoặc uninstall xóa vùng dữ liệu | Lưu dữ liệu ngoài install directory và kiểm thử chính sách retention. |

## 13. Quy trình phát hành đề xuất

Với một sản phẩm Windows dùng MSI:

1. Chọn per-user hoặc per-machine và ghi rõ trong chính sách phát hành.
2. Tạo một GUID cố định cho UpgradeCode của sản phẩm.
3. Lưu GUID trong cấu hình release để mọi job CI sử dụng cùng giá trị.
4. Tăng ProductVersion theo quy tắc ba trường của Windows Installer.
5. Tạo MSI bằng jpackage với **--win-upgrade-uuid** và context tương ứng.
6. Ký số MSI theo quy trình phát hành của tổ chức.
7. Cài thử bản cũ, nâng cấp lên bản mới và xác minh dữ liệu/shortcut.
8. Lưu artifact, checksum, phiên bản JDK và cấu hình installer để có thể tái tạo.

Ví dụ cấu hình phát hành per-machine:

~~~powershell
$upgradeCode = "7F3A9E20-6D41-4B8C-9A2E-5F6C1D0B8A74"
$appVersion = "1.5.0"
jpackage --type msi --name InventoryDesk --app-version $appVersion --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.Main --win-upgrade-uuid $upgradeCode --dest dist
~~~

Ví dụ cấu hình phát hành per-user:

~~~powershell
$upgradeCode = "7F3A9E20-6D41-4B8C-9A2E-5F6C1D0B8A74"
$appVersion = "1.5.0"
jpackage --type msi --name InventoryDesk --app-version $appVersion --input build\libs --main-jar inventory-desk.jar --main-class com.example.inventory.Main --win-per-user-install --win-upgrade-uuid $upgradeCode --dest dist
~~~

Giữ GUID giống nhau cho mọi phiên bản của InventoryDesk. Nếu đổi sang một sản phẩm khác, tạo GUID khác. Nếu đổi installation context, xử lý như một dự án migration riêng.

## 14. Cách áp dụng trong quy trình Java hiện đại

- Chọn per-user khi ứng dụng dành cho tài khoản cài đặt; chọn per-machine khi cần dùng chung và quản trị toàn máy.
- Dùng **--win-per-user-install** nhất quán qua các phiên bản nếu sản phẩm được cài theo người dùng.
- Dùng **--win-upgrade-uuid** với GUID cố định cho từng sản phẩm.
- Giữ UpgradeCode qua các bản phát hành cùng sản phẩm; không tạo GUID mới ở mỗi lần build.
- Để jpackage tạo ProductCode cho từng MSI; không nhầm ProductCode với UpgradeCode.
- Tăng ProductVersion trong ba trường đầu để Windows Installer nhận diện phiên bản mới.
- Giữ installation context giống bản đang cài khi thực hiện major upgrade.
- Kiểm thử nâng cấp từ MSI cũ, bảo toàn dữ liệu và gỡ cài đặt trên máy Windows sạch.

**--win-per-user-install** quyết định ứng dụng thuộc tài khoản hay toàn máy. **--win-upgrade-uuid** xác định các MSI thuộc cùng dòng sản phẩm để Windows Installer tìm phiên bản liên quan. Giữ đúng hai cấu hình này, tăng ProductVersion hợp lệ và kiểm thử nâng cấp thực tế giúp ứng dụng Java được cập nhật ổn định trên Windows.

## Tài liệu tham khảo

- [Oracle JDK 16 — The jpackage Command](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Microsoft Learn — UpgradeCode property](https://learn.microsoft.com/en-us/windows/win32/msi/upgradecode)
- [Microsoft Learn — Using an UpgradeCode](https://learn.microsoft.com/en-us/windows/win32/msi/using-an-upgradecode)
- [Microsoft Learn — Major Upgrades](https://learn.microsoft.com/en-us/windows/win32/msi/major-upgrades)
- [Microsoft Learn — Installation Context](https://learn.microsoft.com/en-us/windows/win32/msi/installation-context)
- [Microsoft Learn — ProductCode property](https://learn.microsoft.com/en-us/windows/win32/msi/productcode)
