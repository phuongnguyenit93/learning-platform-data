# java --add-modules: thêm root module

## 1. Mục đích của --add-modules

Java Platform Module System (JPMS) không tự động đưa mọi module có thể quan sát được vào cấu hình chạy. JVM bắt đầu quá trình phân giải từ một tập **root modules**. Từ các root này, hệ thống module tìm các dependency được khai báo bằng requires và xây dựng quan hệ đọc giữa các module.

Tùy chọn **--add-modules** của Java launcher cho phép thêm module vào tập root cần phân giải, bên cạnh module khởi đầu của ứng dụng:

    java --add-modules java.sql -cp app.jar com.example.Main

Trong ví dụ, java.sql được yêu cầu làm root module bổ sung. JVM phải tìm module này trong tập module có thể quan sát, phân giải nó cùng các dependency cần thiết rồi mới khởi chạy ứng dụng.

Tùy chọn này hữu ích khi:

- Ứng dụng chạy từ classpath nhưng cần dùng API nằm trong một named module chưa thuộc tập root mặc định.
- Ứng dụng hoặc thư viện cần một module JDK cụ thể mà module đó chưa được đưa vào cấu hình chạy.
- Một module provider cần được đưa vào cấu hình để ứng dụng có thể sử dụng chức năng tương ứng.
- Ứng dụng muốn chỉ định rõ các module bổ sung khi khởi chạy một named module.
- Cần thử nghiệm một module hoặc cấu hình module path mà không thay đổi module-info.java của ứng dụng.

**--add-modules chỉ bổ sung root cho quá trình phân giải.** Nó không thêm JAR vào module path, không tự tạo dependency requires, không export package và không mở package cho reflection.

## 2. Cú pháp và vị trí trên command line

Cú pháp cơ bản:

    java --add-modules module[,module...] <main-class>

Có thể dùng dấu bằng:

    java --add-modules=java.sql,java.xml -cp app.jar com.example.Main

Có thể chỉ định nhiều module trong cùng một danh sách, phân cách bằng dấu phẩy. Tên được dùng là tên module, không phải tên JAR, package hay tên lớp.

Ví dụ với một named module làm chương trình chính:

    java --module-path mods \
         --add-modules com.example.metrics \
         --module com.example.application/com.example.application.Main

Trong lệnh trên:

- **--module-path mods** xác định nơi JVM tìm các application module.
- **--module com.example.application/...** chọn module chính và lớp main.
- **--add-modules com.example.metrics** bổ sung com.example.metrics làm root module.
- Các dependency được khai báo bằng requires sẽ được phân giải theo quy tắc module resolution.

Các option của launcher phải đứng trước tên lớp chính, tên JAR sau -jar hoặc đối số module sau -m/--module. Những đối số xuất hiện sau điểm bắt đầu chương trình được chuyển cho main method, không còn được hiểu là option của launcher.

Trên Windows, dấu phân cách các phần tử module path là dấu chấm phẩy. Trên Linux và macOS, dấu phân cách là dấu hai chấm.

## 3. Root module và quá trình phân giải

Root module là điểm bắt đầu của quá trình module resolution. Có thể hình dung quá trình này theo các bước:

1. JVM xác định module chính của ứng dụng và các root bổ sung được yêu cầu bằng --add-modules.
2. JVM tìm module descriptor tương ứng trong tập observable modules.
3. Các directive requires được duyệt đệ quy để xác định dependency cần thiết.
4. JVM xây dựng readability graph, thể hiện module nào đọc được module nào.
5. Nếu cấu hình có service binding, các provider phù hợp cũng có thể được đưa vào cấu hình theo quy tắc service binding của JPMS.

Ví dụ, giả sử:

    module com.example.application {
        requires com.example.api;
    }

    module com.example.api {
        requires com.example.logging;
    }

Nếu com.example.application là root, module resolution sẽ phân giải các dependency được khai báo theo quan hệ requires. Không cần thêm từng dependency bằng --add-modules nếu chúng đã được yêu cầu và có thể quan sát được.

Ngược lại, nếu ứng dụng chạy trên classpath và không có named module chính, ứng dụng có thể cần bổ sung một named module bằng --add-modules để module đó được resolve vào boot layer.

Tập root mặc định khi chạy named module thường là module ứng dụng được chỉ định cho launcher. Khi chạy lớp chính từ classpath hoặc biên dịch mã trong unnamed module, tập root mặc định phụ thuộc implementation. Trong JDK, tập mặc định bao gồm các module quan sát được trên upgrade module path hoặc trong system modules và export ít nhất một package không có giới hạn module đích.

Điểm cần nhớ: **observable không đồng nghĩa với resolved**. Một module có thể tồn tại trên module path hoặc trong runtime image nhưng chưa nằm trong cấu hình module đã resolve. --add-modules yêu cầu launcher đưa module đó vào tập root để phân giải.

## 4. Ba selector đặc biệt

Ngoài tên module cụ thể, Java launcher hỗ trợ ba giá trị đặc biệt:

| Giá trị | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| **ALL-DEFAULT** | Tập module root mặc định của launcher | Muốn chỉ rõ tập root mặc định, thường hữu ích trong source-file mode hoặc cấu hình launcher cần nêu rõ |
| **ALL-SYSTEM** | Tất cả system modules có thể quan sát được trong runtime image | Cần resolve toàn bộ system modules của JDK để thử nghiệm hoặc cấu hình đặc biệt |
| **ALL-MODULE-PATH** | Tất cả module có thể quan sát trên application module path | Muốn resolve mọi module được cung cấp qua module path |

Ví dụ:

    java --add-modules ALL-DEFAULT -cp app.jar com.example.Main

    java --add-modules ALL-SYSTEM -cp app.jar com.example.Main

    java --module-path mods \
         --add-modules ALL-MODULE-PATH \
         --module com.example.application/com.example.application.Main

Các selector này có phạm vi rộng khác nhau. ALL-SYSTEM có thể đưa vào nhiều module JDK mà ứng dụng không cần. ALL-MODULE-PATH có thể resolve cả những module ứng dụng không sử dụng trực tiếp. Điều đó có thể làm tăng số module trong cấu hình, bộc lộ xung đột package/module và khiến việc phân tích dependency khó hơn.

Trong ứng dụng thông thường, ưu tiên chỉ định tên module cụ thể. Dùng selector toàn bộ khi có lý do rõ ràng, chẳng hạn môi trường thử nghiệm, công cụ cần khảo sát module hoặc cấu hình runtime được thiết kế để đưa tất cả module vào.

## 5. Observable modules: module phải được tìm thấy trước

--add-modules không phải tùy chọn để thêm file JAR hoặc thư mục vào nơi tìm module. Module phải nằm trong tập observable modules của runtime.

Các nguồn thường gặp:

- **System modules:** các module có sẵn trong runtime image của JDK.
- **Upgrade module path:** nơi đặt module thay thế cho một số module có thể nâng cấp trong runtime image.
- **Application module path:** nơi đặt modular JAR hoặc exploded module của ứng dụng và thư viện.

Ví dụ:

    java --module-path mods \
         --add-modules com.example.reporting \
         --module com.example.application/com.example.application.Main

Nếu com.example.reporting không có trong các nguồn module mà JVM quan sát được, launcher sẽ báo lỗi không tìm thấy module. Cần kiểm tra module path và tên module thực tế trước khi thay đổi danh sách root.

Có thể xem module có thể quan sát bằng:

    java --list-modules

Lệnh này liệt kê các module mà runtime nhìn thấy. Nó không có nghĩa tất cả module trong danh sách đã được resolve vào boot layer.

Có thể xem thông tin một module:

    java --module-path mods --describe-module com.example.reporting

Để xem quá trình module resolution lúc khởi động:

    java --show-module-resolution \
         --module-path mods \
         --add-modules com.example.reporting \
         --module com.example.application/com.example.application.Main

Option **--show-module-resolution** giúp quan sát module nào được resolve và các quan hệ dependency trong lúc khởi động.

## 6. Ví dụ: ứng dụng classpath cần API từ named module

Giả sử ứng dụng cũ chạy trên classpath:

    java -cp app.jar com.example.Main

Mã trong app.jar sử dụng một API thuộc module com.example.metrics. JAR modular của module này nằm trong thư mục mods.

Có thể khởi chạy như sau:

    java --module-path mods \
         --add-modules com.example.metrics \
         -cp app.jar \
         com.example.Main

Module com.example.metrics được thêm làm root và resolve cùng các dependency của nó. Lớp ứng dụng vẫn chạy trong unnamed module vì main class được tải từ classpath.

Unnamed module có khả năng đọc các named module trong cấu hình phù hợp, nhưng khả năng truy cập package vẫn phụ thuộc exports. Nếu package chỉ được export có điều kiện cho một module cụ thể, việc thêm root module không tự cấp quyền cho unnamed module.

Ví dụ, module library có:

    module com.example.metrics {
        exports com.example.metrics.api;
        exports com.example.metrics.internal
            to com.example.metrics.tests;
    }

Ứng dụng classpath có thể sử dụng API trong package được export không điều kiện. Việc thêm module không làm package internal trở thành public cho unnamed module.

## 7. Ví dụ: module chính cần một module bổ sung

Với ứng dụng modular, module chính được chọn bằng -m hoặc --module:

    java --module-path mods \
         --module com.example.application/com.example.application.Main

Nếu module chính không khai báo requires tới một module khác nhưng runtime vẫn cần resolve module đó như một root độc lập, có thể bổ sung:

    java --module-path mods \
         --add-modules com.example.diagnostics \
         --module com.example.application/com.example.application.Main

Trường hợp này thường xuất hiện với module được tìm bằng cơ chế động hoặc module cung cấp chức năng được ứng dụng kích hoạt theo cấu hình. Nếu quan hệ dependency là bắt buộc về mặt thiết kế và có thể khai báo tĩnh, nên thể hiện trong module-info.java bằng requires thay vì dựa lâu dài vào option triển khai.

Nếu module được sử dụng qua ServiceLoader, cần phân biệt hai việc:

- Module consumer khai báo **uses** để đăng ký nhu cầu service.
- Module provider khai báo **provides ... with ...** để đăng ký implementation.

--add-modules có thể đưa provider module vào tập root, nhưng không thay thế uses/provides và không làm cho một provider sai kiểu trở thành hợp lệ.

## 8. Phân biệt với các option module khác

Các option sau thường bị nhầm với --add-modules:

| Option | Tác dụng | Điều nó không làm |
|---|---|---|
| **--module-path** | Xác định nơi tìm application modules | Không tự yêu cầu mọi module trên đường dẫn được resolve |
| **--add-modules** | Thêm root modules vào tập cần resolve | Không thêm đường dẫn hoặc export package |
| **--limit-modules** | Giới hạn tập observable modules | Không thêm module mới vào tập observable |
| **--add-reads** | Thêm quan hệ readability giữa hai module | Không tự resolve module không quan sát được |
| **--add-exports** | Cho phép một package được export thêm tới module đích | Không thêm root module |
| **--add-opens** | Mở package cho deep reflection tới module đích | Không thay thế requires hoặc module resolution |

Ví dụ:

    java --module-path mods \
         --add-modules com.example.library \
         --add-exports com.example.library/com.example.internal=ALL-UNNAMED \
         -cp app.jar com.example.Main

Trong lệnh này, --add-modules đưa com.example.library vào tập root; --add-exports điều chỉnh quyền truy cập package internal cho unnamed modules. Hai option giải quyết hai vấn đề khác nhau.

Nếu module không nằm trong module path hoặc runtime image, thêm --add-reads hay --add-exports không thể làm cho JVM tìm thấy module đó. Trước hết cần bảo đảm module có thể quan sát được.

## 9. Kết hợp với --limit-modules

**--limit-modules** giới hạn tập observable modules của runtime. Tùy chọn này thường dùng khi muốn kiểm tra ứng dụng có thể chạy với một tập module nhỏ hơn hoặc tạo runtime có phạm vi giới hạn.

Ví dụ:

    java --limit-modules java.base,java.logging \
         --add-modules java.sql \
         -cp app.jar com.example.Main

Nếu java.sql không nằm trong tập observable sau khi áp dụng giới hạn, launcher không thể resolve nó chỉ vì có tên trong --add-modules. Module cần được phép quan sát và tìm thấy theo cấu hình đã giới hạn.

Khi kết hợp hai option, hãy xem xét tập observable trước, sau đó mới xác định root module. --add-modules chọn module từ tập có thể quan sát; --limit-modules xác định giới hạn của chính tập đó.

Không nên thêm một danh sách root rất rộng rồi đồng thời giới hạn module mà không hiểu dependency closure. Một module được thêm làm root có thể kéo theo các module khác thông qua requires; nếu dependency bị loại khỏi tập observable, quá trình resolve sẽ thất bại.

## 10. Kiểm tra và chẩn đoán

Khi launcher báo lỗi module không tìm thấy hoặc ứng dụng không truy cập được API, có thể kiểm tra theo thứ tự:

1. Xác định tên module thực tế bằng jar --describe-module hoặc java --list-modules.
2. Xác nhận module nằm trong system modules, upgrade module path hay application module path.
3. Xác nhận option --module-path trỏ đúng thư mục hoặc JAR.
4. Kiểm tra tên module được truyền vào --add-modules có khớp module descriptor không.
5. Xem dependency closure của module qua các directive requires.
6. Dùng --show-module-resolution để quan sát module nào được resolve.
7. Nếu lỗi là IllegalAccessError hoặc InaccessibleObjectException, kiểm tra exports, opens và readability; thêm root module không tự sửa quyền truy cập.
8. Nếu lỗi là package không tìm thấy hoặc lớp không nạp được, xác định module chứa package và loader đang dùng.

Một số lệnh hữu ích:

    java --list-modules

    jar --describe-module --file mods/com.example.metrics.jar

    java --module-path mods \
         --add-modules com.example.metrics \
         --show-module-resolution \
         --module com.example.application/com.example.application.Main

    java --module-path mods --validate-modules

**--validate-modules** kiểm tra tính hợp lệ của module configuration trên module path rồi kết thúc. Nó không chạy main method và không thay thế kiểm thử chức năng của ứng dụng.

## 11. Những lỗi thường gặp

### Module không tìm thấy

Nguyên nhân thường là module chưa nằm trên module path, tên module sai hoặc module bị loại khỏi tập observable bởi --limit-modules. Kiểm tra JAR bằng jar --describe-module, rồi kiểm tra lại đường dẫn.

### Module đã resolve nhưng package vẫn không truy cập được

--add-modules không thay đổi exports hoặc opens. Nếu ứng dụng không được phép truy cập package, hãy sửa module descriptor theo đúng thiết kế hoặc dùng option bổ sung phù hợp cho mục đích chạy/kiểm thử đã xác định.

### Thêm module nhưng dependency vẫn lỗi

Khi module được thêm làm root, JVM tiếp tục phân giải dependency của nó. Nếu module khai báo requires tới một module không observable hoặc có xung đột package, toàn bộ resolution có thể thất bại. Kiểm tra dependency closure thay vì chỉ kiểm tra module root.

### Dùng ALL-MODULE-PATH gây xung đột

Đưa toàn bộ module trên module path thành root có thể làm lộ xung đột package hoặc module name mà cấu hình tối thiểu không gặp. Chỉ dùng ALL-MODULE-PATH khi thực sự cần resolve toàn bộ tập module trên đường dẫn.

### Nhầm --add-modules với --add-reads

Một module có thể đã được resolve nhưng module khác chưa đọc được nó. Trong trường hợp đó, vấn đề là readability chứ không phải root set. --add-reads điều chỉnh quan hệ đọc; --add-modules đưa module vào quá trình resolve. Chọn option dựa trên loại lỗi thực tế.

## 12. Ghi nhớ

- **--add-modules** thêm root module vào tập module cần resolve, bên cạnh module khởi đầu.
- Root module kéo theo dependency qua các directive requires trong quá trình resolution.
- Module phải nằm trong tập observable; --add-modules không thay thế --module-path.
- Có thể chỉ định tên module cụ thể hoặc dùng ALL-DEFAULT, ALL-SYSTEM và ALL-MODULE-PATH.
- ALL-DEFAULT đại diện tập root mặc định; ALL-SYSTEM chọn toàn bộ system modules; ALL-MODULE-PATH chọn toàn bộ module trên application module path.
- --add-modules không tự thêm requires, exports, opens hoặc readability.
- --limit-modules giới hạn tập module có thể quan sát; module bị loại khỏi tập này không thể được thêm làm root.
- Dùng --show-module-resolution để xem cấu hình module thực tế lúc khởi động.
- Ưu tiên thêm module cụ thể thay vì resolve tất cả nếu ứng dụng chỉ cần một vài module.

**--add-modules là công cụ điều khiển điểm bắt đầu của module resolution.** Khi phân biệt rõ root module, dependency, observable module và quyền truy cập package, bạn có thể dùng option này để bổ sung đúng module cho ứng dụng mà không nhầm nó với các cơ chế khác của JPMS.

## Tài liệu tham khảo

- Java SE 21 Tool Specifications — java launcher: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Java SE 21 API — java.lang.module package summary: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/package-summary.html
- Java SE 21 Tool Specifications — javac: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html