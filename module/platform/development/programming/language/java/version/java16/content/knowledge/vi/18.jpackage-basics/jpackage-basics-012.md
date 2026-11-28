# Tách `--arguments` của ứng dụng khỏi `--java-options` của JVM

Khi đóng gói ứng dụng Java bằng `jpackage`, có hai nhóm giá trị được cấu hình cho thời điểm launcher chạy: **tham số ứng dụng** và **tùy chọn khởi động JVM**. Hai nhóm này đi vào hai nơi khác nhau. `--arguments` thiết lập các tham số mặc định được truyền tới phương thức `main(String[] args)`, còn `--java-options` thiết lập tùy chọn cho Java runtime trước khi ứng dụng bắt đầu chạy.

Phân biệt đúng hai nhóm giúp tránh những lỗi khó phát hiện: đặt `-Xmx` vào `args` khiến ứng dụng chỉ nhận một chuỗi thông thường thay vì tăng heap; đặt `--config` vào `--java-options` khiến JVM hiểu nhầm đó là tùy chọn của runtime. Bài học tập trung vào cách cấu hình launcher ổn định trên Java 16 trở lên và các JDK hiện đại.

## 1. Hai lớp tham số trong một ứng dụng được đóng gói

Khi người dùng mở launcher do `jpackage` tạo, trình khởi chạy sẽ khởi động runtime đi kèm, áp dụng các JVM options đã cấu hình, sau đó gọi entry point của ứng dụng với mảng tham số.

| Mục đích | Tùy chọn `jpackage` | Nơi nhận giá trị | Ví dụ |
|---|---|---|---|
| Truyền cấu hình nghiệp vụ, file đầu vào, chế độ chạy | `--arguments` | `String[] args` trong `main()` | `--config settings.properties` |
| Chọn heap, system property, module access hoặc JVM behavior | `--java-options` | JVM khi khởi động | `-Xmx1g`, `-Dapp.profile=prod` |

Hãy xem `jpackage` như công cụ tạo launcher. Các tùy chọn `--arguments` và `--java-options` được ghi vào cấu hình của launcher trong application image; chúng không phải là tham số để ứng dụng đọc trực tiếp ngay lúc chạy lệnh đóng gói.

Ví dụ:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --main-class com.example.ReportTool \
    --arguments "--mode=desktop --config conf/default.properties" \
    --java-options "-Xms256m -Xmx1g -Dapp.profile=desktop"
~~~

Trong ví dụ:

- `--mode=desktop` và `--config ...` là tham số ứng dụng.
- `-Xms256m` và `-Xmx1g` là tùy chọn bộ nhớ của JVM.
- `-Dapp.profile=desktop` tạo system property để code có thể đọc bằng `System.getProperty()`.
- `--type app-image` tạo application image để kiểm thử launcher trước khi tạo installer của hệ điều hành.

## 2. `--arguments` thiết lập tham số mặc định cho main class

`--arguments` xác định các tham số mặc định được truyền tới main class khi người dùng chạy launcher mà không cung cấp tham số dòng lệnh. Mảng tham số này xuất hiện trong `String[] args`.

Ví dụ:

~~~java
package com.example;

public class ReportTool {
    public static void main(String[] args) {
        System.out.println("Application arguments:");
        for (int i = 0; i < args.length; i++) {
            System.out.printf("args[%d] = %s%n", i, args[i]);
        }
    }
}
~~~

Đóng gói với giá trị mặc định:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --main-class com.example.ReportTool \
    --arguments "--mode=desktop --config conf/default.properties"
~~~

Khi người dùng mở launcher mà không thêm tham số, ứng dụng nhận ba phần tử:

~~~text
args[0] = --mode=desktop
args[1] = --config
args[2] = conf/default.properties
~~~

Nếu ứng dụng muốn `--config=conf/default.properties` là một phần tử duy nhất, hãy cấu hình theo đúng cú pháp parser mà ứng dụng sử dụng:

~~~text
--arguments "--mode=desktop --config=conf/default.properties"
~~~

Điều quan trọng là `jpackage` không tự hiểu ý nghĩa nghiệp vụ của các tham số. Ứng dụng chịu trách nhiệm phân tích `args` theo quy ước của chính nó.

### Tham số người dùng nhập thay thế giá trị mặc định

Nếu launcher đã có default arguments, người dùng có thể truyền danh sách tham số riêng khi khởi chạy. Khi đó, danh sách do người dùng cung cấp được dùng thay cho default arguments. Các giá trị mặc định không được tự động nối thêm vào danh sách mới.

Giả sử launcher có default arguments:

~~~text
--arguments "--mode=desktop --config conf/default.properties"
~~~

Khi người dùng mở launcher không có tham số, ứng dụng nhận các giá trị mặc định. Khi người dùng chạy:

~~~text
ReportTool --mode=batch --input data.csv
~~~

ứng dụng nhận `--mode=batch` và `--input data.csv`; danh sách mặc định `--mode=desktop --config ...` không được tự động thêm vào.

Đây là lý do nên đặt các giá trị có thể thay đổi theo lần chạy ở `--arguments`, rồi để ứng dụng tự chọn fallback khi cần. Ví dụ, nếu không có `--config`, ứng dụng có thể tự tìm file cấu hình ở vị trí mặc định của nó.

## 3. `--java-options` cấu hình JVM trước khi main chạy

`--java-options` truyền các tùy chọn cho Java runtime trong launcher. Các giá trị này được xử lý khi JVM khởi động, trước khi gọi `main()`.

Một số ví dụ thường gặp:

| JVM option | Tác dụng |
|---|---|
| `-Xms256m` | Heap ban đầu |
| `-Xmx1g` | Giới hạn heap tối đa |
| `-Dapp.profile=production` | Tạo system property `app.profile` |
| `-Dapp.home=$APPDIR` | Truyền đường dẫn application image qua system property |
| `--add-opens=java.base/java.lang=ALL-UNNAMED` | Mở một package cho reflective access nếu ứng dụng thực sự cần |

Ví dụ:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --java-options "-Xms256m -Xmx1g -Dapp.profile=production"
~~~

Ứng dụng có thể đọc system property:

~~~java
String profile = System.getProperty("app.profile", "local");
System.out.println("Profile: " + profile);
~~~

Giá trị `production` được lấy từ JVM option `-Dapp.profile=production`, không xuất hiện trong `String[] args`.

### Phân biệt JVM option với application argument

Ví dụ sau đặt nhầm `-Xmx1g` vào `--arguments`:

~~~text
--arguments "-Xmx1g"
~~~

Trong trường hợp này, `main()` nhận một phần tử chuỗi `-Xmx1g`. Heap của JVM không được thay đổi bởi chuỗi đó.

Ngược lại, nếu đặt tham số nghiệp vụ vào `--java-options`:

~~~text
--java-options "--config conf/app.properties"
~~~

JVM sẽ cố diễn giải các chuỗi đó như tùy chọn runtime. `--config` không phải JVM option chuẩn nên launcher có thể không khởi động được.

## 4. Một ví dụ đầy đủ: ứng dụng đọc tham số và system property

Ví dụ dưới đây cho thấy hai nguồn cấu hình đến hai API khác nhau:

~~~java
package com.example;

import java.lang.management.ManagementFactory;
import java.util.Arrays;

public class RuntimeConfiguration {
    public static void main(String[] args) {
        String profile = System.getProperty("app.profile", "local");
        String configPath = findOptionValue(args, "--config");

        System.out.println("Profile: " + profile);
        System.out.println("Config: " + configPath);
        System.out.println("Application args: "
                + Arrays.toString(args));
        System.out.println("JVM input arguments: "
                + ManagementFactory.getRuntimeMXBean().getInputArguments());
        System.out.println("Maximum heap: "
                + Runtime.getRuntime().maxMemory());
    }

    private static String findOptionValue(
            String[] args, String option) {
        for (int i = 0; i < args.length - 1; i++) {
            if (option.equals(args[i])) {
                return args[i + 1];
            }
        }
        return null;
    }
}
~~~

Đóng gói:

~~~text
jpackage --type app-image \
    --name RuntimeConfiguration \
    --input build/input \
    --main-jar runtime-configuration.jar \
    --main-class com.example.RuntimeConfiguration \
    --arguments "--config conf/app.properties" \
    --java-options "-Xms256m -Xmx768m -Dapp.profile=production"
~~~

Khi mở launcher không truyền tham số:

- `args` chứa `--config` và `conf/app.properties`.
- `System.getProperty("app.profile")` trả về `production`.
- `Runtime.getRuntime().maxMemory()` phản ánh giới hạn heap của JVM đã khởi động.
- `RuntimeMXBean.getInputArguments()` giúp quan sát các JVM input arguments trong môi trường chạy.

Không dùng `RuntimeMXBean.getInputArguments()` để thay thế cấu hình ứng dụng. Đây là API chẩn đoán hữu ích; logic nghiệp vụ nên đọc `args` và các system property có tên rõ ràng.

## 5. Nhiều giá trị và nhiều lần xuất hiện của tùy chọn

`--arguments` có thể xuất hiện nhiều lần. Có thể truyền một chuỗi gồm nhiều argument được phân tách bằng dấu cách, hoặc lặp tùy chọn để khai báo các giá trị riêng:

~~~text
--arguments "arg1 arg2 arg3"
~~~

Tương đương về mục đích:

~~~text
--arguments arg1 --arguments arg2 --arguments arg3
~~~

`--java-options` cũng có thể xuất hiện nhiều lần:

~~~text
--java-options "-Xms256m" \
--java-options "-Xmx1g" \
--java-options "-Dapp.profile=production"
~~~

Hoặc gộp thành một giá trị:

~~~text
--java-options "-Xms256m -Xmx1g -Dapp.profile=production"
~~~

Chọn một kiểu thống nhất trong build script để người review dễ kiểm tra các giá trị được đóng gói.

## 6. Xử lý argument có dấu cách

Có hai lớp phân tích chuỗi:

1. Shell của hệ điều hành xử lý câu lệnh `jpackage`.
2. Launcher xử lý chuỗi default arguments để tạo các phần tử truyền tới main class.

Vì vậy, chỉ đặt toàn bộ giá trị trong một cặp dấu nháy của shell chưa chắc đã giữ một đường dẫn có dấu cách thành một argument duy nhất ở thời điểm chạy ứng dụng.

Ví dụ đường dẫn cấu hình có dấu cách:

~~~text
--arguments "\"--config\" \"conf/production settings.properties\""
~~~

Các dấu nháy được escape giúp launcher nhận ra `--config` và đường dẫn có dấu cách là hai argument riêng. Có thể lặp `--arguments` cho từng phần tử nếu phù hợp với build script.

Tài liệu `jpackage` có các ví dụ về nested quoting cho argument có dấu cách. Cú pháp escape cụ thể phụ thuộc shell đang dùng. Hãy kiểm tra bằng cách chạy application image và in từng `args[i]` trước khi tạo installer.

### JVM option có dấu cách

Một JVM option chứa giá trị có dấu cách cũng cần quoting ở lớp launcher:

~~~text
--java-options "\"-Dapp.description=Report service for finance team\""
~~~

Đừng dùng một cách escape duy nhất cho mọi shell mà không kiểm thử. Build chạy trong Bash, PowerShell và CI runner có thể xử lý dấu nháy khác nhau. Nếu build script phức tạp, dùng file cấu hình launcher hoặc argument file được `jpackage` hỗ trợ để giảm độ rối của câu lệnh.

## 7. Dùng `$APPDIR`, `$BINDIR`, `$ROOTDIR` và biến môi trường

Giá trị của `--arguments` và `--java-options` có thể chứa các chuỗi được launcher mở rộng khi chạy:

- `$APPDIR`: thư mục application image chứa payload ứng dụng.
- `$BINDIR`: thư mục chứa launcher.
- `$ROOTDIR`: thư mục gốc của application image.
- Tên biến môi trường: được thay bằng giá trị biến môi trường tương ứng nếu biến tồn tại.

Ví dụ:

~~~text
--java-options "-Dapp.home=\$APPDIR"
~~~

Khi launcher chạy, `$APPDIR` được thay bằng đường dẫn thực tế của application image. Dấu `$` cần được bảo vệ khỏi shell khi câu lệnh đóng gói được chạy trong shell có variable expansion.

Có thể dùng macro trong default argument:

~~~text
--arguments "--config \$APPDIR/conf/app.properties"
~~~

Hoặc đặt trong launcher properties file:

~~~properties
arguments=--config "$APPDIR/conf/app.properties"
java-options=-Dapp.home=$APPDIR
~~~

Việc mở rộng biến môi trường phân biệt chữ hoa/chữ thường trên Unix và không phân biệt trên Windows. Các tên `APPDIR`, `BINDIR`, `ROOTDIR` được dành cho launcher; không nên đặt biến môi trường ứng dụng trùng các tên này để kỳ vọng launcher dùng giá trị do người dùng đặt.

## 8. Tách cấu hình theo launcher bằng `--add-launcher`

Một application image có thể cung cấp nhiều launcher cho cùng một ứng dụng. Ví dụ:

- Launcher `ReportTool` mở giao diện desktop với profile mặc định.
- Launcher `ReportBatch` chạy chế độ batch với heap lớn hơn.
- Launcher `ReportAdmin` mở chế độ bảo trì với file cấu hình riêng.

`--add-launcher` nhận tên launcher và một properties file:

~~~text
--add-launcher ReportBatch=report-batch.properties
~~~

Ví dụ file `report-batch.properties`:

~~~properties
arguments=--mode=batch --config "$APPDIR/conf/batch.properties"
java-options=-Xms512m -Xmx2g -Dapp.profile=batch
~~~

Tạo launcher chính và launcher phụ:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --main-class com.example.ReportTool \
    --arguments "--mode=desktop --config conf/desktop.properties" \
    --java-options "-Xms256m -Xmx1g -Dapp.profile=desktop" \
    --add-launcher ReportBatch=report-batch.properties
~~~

Launcher phụ dùng cấu hình riêng trong properties file. Các thuộc tính `arguments` và `java-options` ở launcher phụ có thể bổ sung hoặc ghi đè cấu hình tương ứng được cung cấp khi tạo launcher chính. Cần kiểm tra từng launcher sau khi đóng gói vì mỗi launcher có thể có default arguments và JVM options khác nhau.

Một launcher properties file có thể định nghĩa `module`, `main-jar`, `main-class`, `description`, `arguments`, `java-options`, `icon` và một số tùy chọn nền tảng. Với launcher thay thế, ít nhất một thuộc tính phải được đặt. Nếu launcher dùng cùng entry point và chỉ cần giá trị mặc định khác nhau, chỉ cần đặt `arguments` và/hoặc `java-options`.

## 9. Kiểm tra cấu hình đã được ghi vào application image

Sau khi `jpackage` tạo application image, trong thư mục `app` của image có file cấu hình tên theo ứng dụng, ví dụ `ReportTool.cfg`. Vị trí đầy đủ thay đổi theo cấu trúc application image của từng nền tảng.

File này có các vùng cấu hình như:

- `[ArgOptions]`: các default arguments được launcher truyền tới ứng dụng.
- `[JavaOptions]`: các JVM options được áp dụng khi khởi động.

Có thể đọc file này để xác minh các giá trị đã được ghi đúng sau khi đóng gói. Đây là bước kiểm tra hữu ích khi build script có nhiều dấu nháy hoặc nhiều launcher.

Không nên sửa file `.cfg` sinh ra bằng tay như một quy trình cấu hình chính. Hãy cập nhật lệnh `jpackage`, properties file hoặc build script rồi tạo lại application image để kết quả có thể tái lập.

## 10. Kiểm thử launcher trước khi tạo installer

Nên tạo `app-image` trước để kiểm tra hành vi thực tế:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --main-class com.example.ReportTool \
    --arguments "--mode=desktop --config conf/default.properties" \
    --java-options "-Xms256m -Xmx1g -Dapp.profile=desktop" \
    --dest build/packages
~~~

Chạy launcher không truyền tham số:

~~~text
build/packages/ReportTool/bin/ReportTool
~~~

Sau đó chạy với tham số do người dùng cung cấp:

~~~text
build/packages/ReportTool/bin/ReportTool --mode=batch --input data.csv
~~~

Trên Windows, launcher thường có đuôi `.exe`; trên macOS, launcher nằm trong application bundle; trên Linux, launcher nằm trong thư mục `bin` của application image. Đường dẫn trên chỉ minh họa cấu trúc Linux/macOS dạng app-image.

Kiểm tra các điểm:

1. Không truyền argument: ứng dụng nhận default arguments đã cấu hình.
2. Có truyền argument: ứng dụng nhận danh sách do người dùng cung cấp thay cho default list.
3. System property đọc được đúng giá trị đặt trong `--java-options`.
4. Heap và JVM input arguments phản ánh cấu hình dự kiến.
5. Từng launcher phụ có đúng arguments và java options riêng.
6. Đường dẫn có dấu cách và macro `$APPDIR` được mở rộng đúng.

Sau khi application image hoạt động đúng, mới tạo định dạng package phù hợp với nền tảng đích. `jpackage` tạo package theo nền tảng đang chạy; cần thực hiện quy trình đóng gói riêng cho Windows, macOS và Linux.

## 11. Ứng dụng modular và non-modular

Khác biệt giữa ứng dụng modular và non-modular nằm ở cách chỉ định entry point và module path. Nguyên tắc phân chia application arguments và JVM options vẫn giống nhau.

Non-modular application:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --input build/input \
    --main-jar report-tool.jar \
    --main-class com.example.ReportTool \
    --arguments "--mode=desktop" \
    --java-options "-Xmx1g -Dapp.profile=desktop"
~~~

Modular application:

~~~text
jpackage --type app-image \
    --name ReportTool \
    --module-path build/modules \
    --module com.example.report/com.example.report.Main \
    --arguments "--mode=desktop" \
    --java-options "-Xmx1g -Dapp.profile=desktop"
~~~

Một lệnh `jpackage` chỉ chọn một trong hai cách chỉ định entry point: `--main-jar` hoặc `--module`. Không truyền đồng thời cả hai. Các tùy chọn `--arguments` và `--java-options` vẫn có cùng vai trò với cả hai kiểu ứng dụng.

## 12. Các lỗi cấu hình thường gặp

| Cách cấu hình sai | Hậu quả | Cách sửa |
|---|---|---|
| Đặt `-Xmx1g` trong `--arguments` | `main()` nhận chuỗi `-Xmx1g`, heap không đổi | Đặt trong `--java-options` |
| Đặt `--config` trong `--java-options` | JVM có thể từ chối tùy chọn không hợp lệ | Đặt trong `--arguments` |
| Nghĩ default arguments luôn được nối với tham số người dùng | Ứng dụng thiếu cấu hình mặc định khi người dùng truyền tham số riêng | Hiểu rằng tham số người dùng thay thế default list |
| Đặt `-Dapp.profile=prod` trong `--arguments` | System property không được tạo | Dùng `--java-options` |
| Không escape dấu `$` khi đóng gói trong shell | Shell có thể mở rộng biến trước khi jpackage nhận giá trị | Dùng quoting/escape phù hợp shell |
| Không quote argument có dấu cách ở lớp launcher | Một đường dẫn bị tách thành nhiều phần tử | Dùng nested quoting hoặc properties file |
| Ghi cấu hình của launcher phụ vào lệnh chính nhưng quên file `--add-launcher` | Launcher phụ không có cấu hình mong muốn | Đặt `arguments`/`java-options` trong properties file tương ứng |
| Ghi đè classpath bằng `-cp` mà không thêm các JAR của image | Không tìm thấy class khi chạy | Tránh override classpath hoặc thêm đầy đủ các JAR cần thiết |
| Chỉnh file `.cfg` sinh ra nhưng không sửa build script | Lần build tiếp theo mất thay đổi | Đặt cấu hình trong đầu vào của jpackage |
| Đưa mật khẩu hoặc token vào default arguments/JVM options | Giá trị nhạy cảm bị đóng cứng trong package hoặc log build | Đọc secret từ cơ chế quản lý secret ở runtime |

## 13. Chọn đúng nơi cho từng loại cấu hình

Một quy tắc thực tế là đặt cấu hình theo thời điểm và chủ sở hữu của nó:

| Giá trị | Nơi phù hợp | Lý do |
|---|---|---|
| `--input`, `--output`, `--mode` của ứng dụng | `--arguments` | Ứng dụng cần đọc và xử lý |
| Đường dẫn file cấu hình | `--arguments` | Ứng dụng quyết định cách đọc file |
| Heap ban đầu/tối đa | `--java-options` | JVM cần biết trước khi chạy main |
| System property điều khiển runtime | `--java-options` | JVM tạo property trước khi code chạy |
| Mở package cho reflection | `--java-options` | Đây là tùy chọn module/runtime |
| Chế độ batch với heap lớn | Launcher phụ có `arguments` và `java-options` riêng | Mỗi launcher có profile vận hành riêng |
| Password, API token, secret | Secret store/environment/runtime config | Không đóng gói bí mật vào launcher |

Không đưa mọi thứ vào một chuỗi cấu hình duy nhất. Tách application arguments khỏi JVM options giúp người vận hành biết giá trị nào thuộc giao thức ứng dụng và giá trị nào điều khiển runtime.

## 14. Quy trình thực hiện

1. Xác định main class hoặc main module và tạo application image.
2. Liệt kê các tham số ứng dụng cần có giá trị mặc định.
3. Đưa các tham số đó vào `--arguments`.
4. Xác định heap, system property và các tùy chọn runtime thật sự cần thiết.
5. Đưa các giá trị runtime vào `--java-options`.
6. Nếu cần nhiều chế độ khởi chạy, tạo properties file riêng và khai báo `--add-launcher`.
7. Kiểm tra quoting, dấu cách và macro đường dẫn.
8. Tạo `app-image`, chạy từng launcher với và không có argument.
9. Đọc file `.cfg` để kiểm tra `[ArgOptions]` và `[JavaOptions]`.
10. Khi hành vi đúng, tạo installer cho nền tảng đích.

## 15. Checklist review

- [ ] `--arguments` chỉ chứa tham số dành cho main class.
- [ ] `--java-options` chỉ chứa tùy chọn JVM.
- [ ] Code đọc application arguments từ `String[] args`.
- [ ] Code đọc system property bằng `System.getProperty()`.
- [ ] Heap options được đặt trong `--java-options`.
- [ ] Đã xác định đúng hành vi khi người dùng truyền argument riêng.
- [ ] Argument có dấu cách được quote ở cả lớp shell và launcher.
- [ ] Macro `$APPDIR` không bị shell mở rộng sớm.
- [ ] Mỗi launcher phụ có properties file và cấu hình đúng mục đích.
- [ ] Đã kiểm tra `[ArgOptions]` và `[JavaOptions]` trong application image.
- [ ] Đã chạy thử launcher trên application image trước khi tạo installer.
- [ ] Không đóng gói password, token hoặc secret trong arguments/JVM options.
- [ ] Không ghi đè classpath/module path nếu chưa chủ động cung cấp đầy đủ giá trị.

## 16. Ghi nhớ

- `--arguments` đặt default arguments cho main class khi launcher được chạy mà không có tham số người dùng.
- Khi người dùng truyền tham số lúc chạy launcher, danh sách đó thay thế default arguments.
- `--java-options` truyền JVM options trước khi `main()` chạy.
- `-Xmx`, `-Xms`, `-D...` và `--add-opens` thuộc nhóm JVM options.
- `--config`, `--mode`, đường dẫn dữ liệu và tùy chọn nghiệp vụ thuộc nhóm application arguments.
- `--arguments` và `--java-options` đều có thể xuất hiện nhiều lần.
- Dùng `--add-launcher` và properties file để tạo launcher có cấu hình riêng.
- `$APPDIR`, `$BINDIR`, `$ROOTDIR` và biến môi trường có thể được launcher mở rộng khi chạy.
- Kiểm tra application image và file `.cfg` để xác nhận giá trị đã được đóng gói.
- Không đóng gói secret vào arguments hoặc JVM options.

Tách đúng `--arguments` và `--java-options` giúp launcher khởi động ứng dụng với cấu hình rõ ràng, có thể kiểm thử và tái lập. Đây là cách cấu hình vẫn áp dụng trên các JDK hiện đại khi đóng gói ứng dụng bằng `jpackage`.

## Tài liệu tham khảo

- [The jpackage Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html) — cú pháp `--arguments`, `--java-options` và `--add-launcher`.
- [Packaging Tool User's Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-tool-user-guide.pdf) — default arguments, JVM options, quoting, macro `$APPDIR` và launcher properties.
- [Packaging Overview — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-overview.html) — application image, runtime image và các định dạng package.
- [JEP 392: Packaging Tool](https://openjdk.org/jeps/392) — jpackage trở thành công cụ đóng gói chuẩn trong JDK 16.
