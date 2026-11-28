# Chọn thư mục xuất bằng --dest và xử lý đường dẫn chứa khoảng trắng

**jpackage** là công cụ đóng gói ứng dụng Java thành application image hoặc gói cài đặt native. Khi build, tùy chọn **--dest** (viết tắt **-d**) chỉ định thư mục nhận kết quả. Nếu không truyền tùy chọn này, jpackage ghi kết quả vào working directory hiện tại của tiến trình.

Đường dẫn đầu ra có thể là tuyệt đối hoặc tương đối. Nếu đường dẫn chứa khoảng trắng, cần đặt toàn bộ giá trị thành một đối số của shell. Quy tắc này áp dụng cho cả **--dest** và các tùy chọn nhận đường dẫn khác như **--input**, **--icon**, **--runtime-image**, **--resource-dir** và **--temp**.

Bài học này trình bày cách chọn thư mục xuất rõ ràng, xử lý đường dẫn có khoảng trắng trên PowerShell, Command Prompt và Bash, phân biệt các thư mục mà jpackage sử dụng, và kiểm tra artifact sau khi đóng gói.

## 1. Vai trò của --dest

Cú pháp:

~~~text
jpackage --dest <output-path> [các tùy chọn khác]
~~~

Hoặc dùng dạng viết tắt:

~~~text
jpackage -d <output-path> [các tùy chọn khác]
~~~

**--dest** xác định nơi jpackage đặt kết quả được tạo ra. Giá trị này là đường dẫn thư mục, không phải tên file cài đặt.

Ví dụ:

~~~bash
jpackage --type app-image --name OrderDesk --dest build-output
~~~

Trong ví dụ, **build-output** là thư mục nhận application image. jpackage tạo image của ứng dụng bên trong thư mục đích.

Nếu tạo gói cài đặt native, file package được đặt trong thư mục đích. Loại file phụ thuộc vào **--type** và nền tảng build, ví dụ EXE hoặc MSI trên Windows, DEB hoặc RPM trên Linux, PKG hoặc DMG trên macOS.

### Khi không chỉ định --dest

Nếu bỏ qua **--dest**, jpackage sử dụng working directory hiện tại:

~~~bash
jpackage --type app-image --name OrderDesk --input input --main-jar OrderDesk.jar
~~~

Kết quả được đặt trong thư mục mà tiến trình đang chạy tại thời điểm gọi lệnh. Thư mục này có thể khác với thư mục chứa file JAR, file script hoặc project.

Điều này thường gây nhầm lẫn trong IDE, CI pipeline hoặc script build được gọi từ thư mục khác. Vì vậy, với build lặp lại, nên chỉ định **--dest** rõ ràng.

## 2. Đường dẫn tuyệt đối và tương đối

Tài liệu jpackage quy định đường dẫn của **--dest** có thể là:

- Đường dẫn tuyệt đối.
- Đường dẫn tương đối với working directory hiện tại.

Ví dụ đường dẫn tương đối:

~~~bash
jpackage --type app-image --name OrderDesk --dest "release output"
~~~

Nếu lệnh được chạy từ thư mục project:

~~~text
D:\projects\order-service
~~~

thì thư mục đầu ra được hiểu là:

~~~text
D:\projects\order-service\release output
~~~

Ví dụ đường dẫn tuyệt đối trên Windows:

~~~text
D:\build artifacts\order-service
~~~

Ví dụ đường dẫn tuyệt đối trên Linux:

~~~text
/opt/build artifacts/order-service
~~~

Đường dẫn tuyệt đối giúp lệnh không phụ thuộc vào vị trí gọi script. Nếu dùng đường dẫn tương đối, cần bảo đảm working directory được thiết lập đúng trước khi gọi jpackage.

### Kiểm soát working directory trong script

Trên PowerShell:

~~~powershell
Set-Location "D:\projects\order-service"
~~~

Trên Bash:

~~~bash
cd "/opt/projects/order-service"
~~~

Nếu script có thể được gọi từ nhiều vị trí, cách ổn định hơn là tính đường dẫn tuyệt đối từ thư mục gốc project rồi truyền vào **--dest**.

## 3. Khoảng trắng trong đường dẫn có ý nghĩa gì?

Shell thường dùng khoảng trắng để phân tách các đối số trên command line. Nếu không đặt path trong dấu nháy, một giá trị như:

~~~text
D:\Build Output\Order App
~~~

có thể bị tách thành nhiều phần:

~~~text
D:\Build
Output\Order
App
~~~

jpackage sẽ nhận sai số lượng đối số hoặc hiểu nhầm các từ phía sau là tùy chọn khác.

Cách đúng là đặt toàn bộ giá trị path trong dấu nháy phù hợp với shell:

~~~powershell
--dest "D:\Build Output\Order App"
~~~

hoặc:

~~~bash
--dest "/opt/Build Output/Order App"
~~~

Shell loại bỏ dấu nháy cú pháp và truyền giá trị đường dẫn thành một argument duy nhất cho chương trình Java.

Cần phân biệt:

- Dấu nháy bao quanh giá trị là cú pháp của shell.
- Khoảng trắng bên trong dấu nháy là một phần của đường dẫn.
- Không thêm dấu nháy vào tên thư mục thực tế.
- Mỗi tùy chọn và giá trị của nó vẫn là các đối số riêng biệt.

Ví dụ:

~~~bash
jpackage --dest "release output"
~~~

Ở đây jpackage nhận hai đối số liên quan: tùy chọn **--dest** và một giá trị duy nhất là **release output**.

## 4. Dùng dấu nháy trên PowerShell

PowerShell hỗ trợ dấu nháy đơn và dấu nháy kép. Với đường dẫn cố định, dấu nháy đơn thường dễ đọc vì không nội suy biến:

~~~powershell
jpackage --dest 'D:\Build Output\Order App'
~~~

Dấu nháy kép hữu ích khi cần nội suy biến:

~~~powershell
$destination = "D:\Build Output\Order App"
jpackage --dest $destination
~~~

Có thể tạo đường dẫn bằng **Join-Path** để tránh tự nối dấu phân cách:

~~~powershell
$projectRoot = "D:\projects\order-service"
$destination = Join-Path $projectRoot "release output"

jpackage --dest $destination
~~~

Khi gọi trực tiếp file thực thi jpackage trong JDK có đường dẫn chứa khoảng trắng, dùng call operator **&** và đặt đường dẫn executable trong dấu nháy:

~~~powershell
& "C:\Program Files\Java\jdk-16\bin\jpackage.exe" --dest "D:\Build Output\Order App"
~~~

Call operator yêu cầu PowerShell chạy file thực thi được chỉ định. Nếu bỏ dấu nháy quanh đường dẫn executable có khoảng trắng, PowerShell có thể không tìm thấy chương trình.

### Ví dụ đầy đủ trên PowerShell

Giả sử cấu trúc đầu vào:

~~~text
order-service/
  build/
    input files/
      Order Desk.jar
~~~

Tạo application image vào thư mục có khoảng trắng:

~~~powershell
$javaHome = $env:JAVA_HOME
$jpackage = Join-Path $javaHome "bin\jpackage.exe"
$inputDir = Join-Path (Get-Location) "build\input files"
$destination = Join-Path (Get-Location) "release packages"

New-Item -ItemType Directory -Force -Path $destination | Out-Null

& $jpackage --type app-image --name "Order Desk" --input $inputDir --main-jar "Order Desk.jar" --dest $destination --verbose

if ($LASTEXITCODE -ne 0) {
    throw "jpackage failed with exit code $LASTEXITCODE"
}
~~~

Các biến **$inputDir** và **$destination** được truyền thành từng argument riêng. Không cần tự chèn dấu nháy vào nội dung biến.

**--main-jar** ở ví dụ là tên JAR tương đối với thư mục **--input**. Vì tên JAR có khoảng trắng, nó cũng phải được giữ thành một argument duy nhất.

## 5. Dùng dấu nháy trong Command Prompt (cmd.exe)

Trong Command Prompt, dùng dấu nháy kép để giữ đường dẫn thành một argument:

~~~bat
"%JAVA_HOME%\bin\jpackage.exe" --dest "D:\Build Output\Order App"
~~~

Khi viết lệnh nhiều dòng, dùng dấu mũ **^** ở cuối dòng:

~~~bat
if not exist "D:\Build Output\Order App" mkdir "D:\Build Output\Order App"

"%JAVA_HOME%\bin\jpackage.exe" ^
  --type app-image ^
  --name "Order Desk" ^
  --input "D:\projects\order-service\build\input files" ^
  --main-jar "Order Desk.jar" ^
  --dest "D:\Build Output\Order App" ^
  --verbose

if errorlevel 1 exit /b %ERRORLEVEL%
~~~

Trong Command Prompt:

- Dấu nháy kép bao quanh đường dẫn có khoảng trắng.
- Biến môi trường được mở rộng bằng cú pháp **%JAVA_HOME%**.
- Dấu mũ **^** nối các dòng lệnh.
- Không dùng cú pháp nội suy biến của PowerShell như **$env:JAVA_HOME**.

Nếu đường dẫn tới jpackage nằm trong **JAVA_HOME** có khoảng trắng, vẫn phải đặt toàn bộ executable path trong dấu nháy kép.

## 6. Dùng dấu nháy trong Bash

Trên Linux và macOS, dùng dấu nháy kép hoặc đơn quanh đường dẫn có khoảng trắng:

~~~bash
"$JAVA_HOME/bin/jpackage" --dest "/opt/Build Output/Order App"
~~~

Ví dụ đầy đủ:

~~~bash
project_root="/opt/projects/order-service"
input_dir="$project_root/build/input files"
destination="$project_root/release packages"

mkdir -p "$destination"

"$JAVA_HOME/bin/jpackage" \
  --type app-image \
  --name "Order Desk" \
  --input "$input_dir" \
  --main-jar "Order Desk.jar" \
  --dest "$destination" \
  --verbose
~~~

Trong Bash:

- Dấu nháy kép cho phép mở rộng biến như **$JAVA_HOME** và **$destination**.
- Dấu nháy đơn giữ nguyên nội dung, không mở rộng biến.
- Dấu gạch chéo ngược ở cuối dòng nối lệnh sang dòng tiếp theo.
- Luôn đặt biến chứa path trong dấu nháy khi truyền vào chương trình.

Không viết:

~~~bash
jpackage --dest $destination
~~~

nếu biến có thể chứa khoảng trắng. Shell có thể tách giá trị biến thành nhiều đối số. Hãy viết:

~~~bash
jpackage --dest "$destination"
~~~

## 7. Không nhầm --dest với --input, --temp và --install-dir

jpackage có nhiều tùy chọn nhận đường dẫn. Mỗi tùy chọn có mục đích khác nhau.

| Tùy chọn | Vai trò | Ví dụ |
| --- | --- | --- |
| **--input** | Thư mục chứa file ứng dụng đầu vào để đóng gói | **build/input files** |
| **--dest** | Thư mục nhận application image hoặc package đầu ra | **release packages** |
| **--temp** | Thư mục mới hoặc rỗng dùng cho file tạm trong quá trình đóng gói | **build/temp work** |
| **--runtime-image** | Runtime image đã tạo trước và được đưa vào application image/package | **runtime image** |
| **--resource-dir** | Thư mục chứa resource tùy chỉnh thay thế resource mặc định | **package resources** |
| **--icon** | Đường dẫn tới file icon | **assets/Order Desk.ico** |
| **--install-dir** | Vị trí cài ứng dụng trên máy đích, theo quy tắc từng nền tảng | **Program Files/Order Desk** |

**--dest** là vị trí lưu kết quả build. **--install-dir** là vị trí mà trình cài đặt sẽ sử dụng trên máy người dùng. Thay đổi một tùy chọn không tự thay đổi ý nghĩa của tùy chọn còn lại.

**--temp** cũng không phải thư mục xuất. Nếu chỉ định, thư mục này phải mới hoặc rỗng; jpackage không tự xóa nó sau khi hoàn tất, vì vậy người build cần tự quản lý. Nếu bỏ qua, jpackage tạo và xóa thư mục tạm của nó theo vòng đời tác vụ.

## 8. Khoảng trắng trong các tùy chọn đường dẫn khác

Cùng nguyên tắc quote áp dụng cho mọi giá trị path có khoảng trắng.

Ví dụ:

~~~powershell
jpackage --input "D:\Build Input\Order Service" --dest "D:\Release Packages" --icon "D:\Brand Assets\Order Desk.ico" --runtime-image "D:\Runtime Images\order runtime"
~~~

Ví dụ Bash:

~~~bash
jpackage \
  --input "/opt/build input/order service" \
  --dest "/opt/release packages" \
  --icon "/opt/brand assets/order desk.png" \
  --runtime-image "/opt/runtime images/order runtime"
~~~

Mỗi giá trị được quote độc lập. Không đặt cả chuỗi tùy chọn thành một argument:

~~~bash
# Sai: shell truyền cả chuỗi thành một argument
jpackage "--dest release packages --type app-image"
~~~

Cũng không nên quote từng từ riêng lẻ:

~~~bash
# Sai: giá trị --dest bị tách thành nhiều argument
jpackage --dest "release" "packages"
~~~

Dùng đúng:

~~~bash
jpackage --type app-image --dest "release packages"
~~~

### Module path có nhiều thành phần

Nếu **--module-path** chứa nhiều thư mục, dấu phân cách phụ thuộc hệ điều hành:

- Windows dùng dấu chấm phẩy (**;**).
- Linux và macOS dùng dấu hai chấm (**:**).

Khi toàn bộ module path có khoảng trắng, quote toàn bộ giá trị:

~~~powershell
jpackage --module-path "D:\Java Modules;D:\Third Party Modules"
~~~

~~~bash
jpackage --module-path "/opt/java modules:/opt/third party modules"
~~~

Không thay dấu phân cách của module path bằng dấu phân cách của hệ điều hành khác.

## 9. Dùng đường dẫn tuyệt đối trong CI và build script

CI agent, IDE và service build có thể đặt working directory khác nhau. Một lệnh dùng **--dest "release output"** có thể ghi kết quả vào vị trí khác nếu được gọi từ thư mục khác.

Để build ổn định:

1. Xác định project root.
2. Tạo đường dẫn tuyệt đối tới input và destination.
3. Tạo destination directory trước khi đóng gói.
4. Truyền mỗi path thành một argument.
5. Ghi lại working directory và lệnh build trong log.
6. Kiểm tra exit code của jpackage.
7. Xác minh artifact nằm trong destination dự kiến.

Ví dụ Bash:

~~~bash
project_root="$(pwd)"
destination="$project_root/dist packages"
input_dir="$project_root/build/input"

mkdir -p "$destination"

"$JAVA_HOME/bin/jpackage" \
  --type app-image \
  --name "Order Desk" \
  --input "$input_dir" \
  --main-jar "order-desk.jar" \
  --dest "$destination"

status=$?
if [ "$status" -ne 0 ]; then
  echo "jpackage failed: $status" >&2
  exit "$status"
fi

find "$destination" -maxdepth 2 -print
~~~

Ví dụ PowerShell:

~~~powershell
$projectRoot = (Get-Location).Path
$destination = Join-Path $projectRoot "dist packages"
$inputDir = Join-Path $projectRoot "build\input"

New-Item -ItemType Directory -Force -Path $destination | Out-Null

& "$env:JAVA_HOME\bin\jpackage.exe" --type app-image --name "Order Desk" --input $inputDir --main-jar "order-desk.jar" --dest $destination

if ($LASTEXITCODE -ne 0) {
    throw "Packaging failed: $LASTEXITCODE"
}

Get-ChildItem -LiteralPath $destination -Force
~~~

Các ví dụ kiểm tra artifact sau lệnh đóng gói để xác nhận kết quả đã xuất hiện ở đúng thư mục.

## 10. Chọn thư mục xuất dễ quản lý

Nên dùng một thư mục build output riêng, có tên thể hiện mục đích:

~~~text
order-service/
  build/
    input/
    temp/
  release packages/
~~~

Ví dụ:

- **build/input** chứa JAR và các file runtime resource cần đóng gói.
- **build/temp** là nơi chứa file tạm nếu chủ động cấu hình **--temp**.
- **release packages** chứa application image hoặc installer do jpackage tạo.

Không nên dùng chung thư mục input và destination. Tách riêng giúp dễ xác định file nào là đầu vào, file nào là sản phẩm build.

Với build tự động, có thể dùng thư mục theo phiên bản hoặc build number:

~~~text
release/
  1.4.0/
  1.4.1/
~~~

Việc tách thư mục giúp tránh nhầm artifact giữa các lần build và thuận tiện lưu trữ, kiểm tra hoặc phát hành.

## 11. Xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| jpackage báo thừa đối số hoặc không nhận ra tùy chọn | Path chứa khoảng trắng bị shell tách thành nhiều argument | Quote toàn bộ giá trị path |
| Không tìm thấy jpackage | Đường dẫn tới executable có khoảng trắng nhưng chưa được quote | Quote executable path; dùng call operator trong PowerShell |
| Kết quả xuất hiện ở thư mục không mong muốn | Bỏ --dest hoặc dùng path tương đối với working directory khác dự kiến | Dùng --dest tuyệt đối và ghi rõ project root |
| Không tìm thấy file JAR | --main-jar không trỏ đúng file bên trong --input | Kiểm tra input directory và đường dẫn tương đối của main JAR |
| Không tìm thấy icon hoặc runtime image | Path của --icon hoặc --runtime-image bị tách hoặc sai | Quote path và kiểm tra file tồn tại |
| Build lỗi do thư mục tạm | --temp trỏ tới thư mục không mới hoặc không rỗng | Chọn thư mục tạm riêng, mới hoặc rỗng |
| Không thể tạo artifact | Destination hoặc thư mục cha không có quyền ghi, hoặc artifact đầu ra đã tồn tại theo trạng thái không được phép | Kiểm tra quyền, nội dung thư mục và log verbose; chọn destination phù hợp |
| Lệnh chạy được trong terminal nhưng lỗi trong CI | Working directory, biến môi trường hoặc quyền của CI khác môi trường local | Dùng path tuyệt đối và kiểm tra environment của job |

Khi cần thêm chi tiết, bật **--verbose** để xem tiến trình đóng gói. Kiểm tra cả exit code và nội dung thư mục đích; chỉ nhìn thấy thông báo khởi chạy lệnh chưa đủ để xác nhận package đã được tạo.

## 12. --dest không quyết định nền tảng package

**--dest** chỉ chọn nơi lưu kết quả. Nó không quyết định định dạng package và không biến jpackage thành công cụ cross-platform.

Dùng **--type** để chọn định dạng đầu ra phù hợp:

| Loại | Ý nghĩa |
| --- | --- |
| **app-image** | Application image có launcher và runtime cần thiết |
| **exe**, **msi** | Gói cài đặt Windows |
| **deb**, **rpm** | Gói cài đặt Linux |
| **pkg**, **dmg** | Gói cài đặt hoặc phân phối macOS |

Các định dạng native phải được tạo trên nền tảng tương ứng. Ví dụ, muốn tạo MSI cho Windows thì chạy jpackage trên Windows với các công cụ đóng gói cần thiết; đặt **--dest** thành một đường dẫn Windows khi đang chạy Linux không tạo được MSI.

Để tránh phụ thuộc mặc định theo nền tảng, nên chỉ định **--type** rõ ràng trong script build.

## 13. Quy trình thực hành hoàn chỉnh

Giả sử ứng dụng không modular có cấu trúc:

~~~text
order-service/
  build/
    input files/
      Order Desk.jar
  release packages/
~~~

Trên Windows PowerShell:

~~~powershell
$projectRoot = (Get-Location).Path
$inputDir = Join-Path $projectRoot "build\input files"
$destination = Join-Path $projectRoot "release packages"

New-Item -ItemType Directory -Force -Path $destination | Out-Null

& "$env:JAVA_HOME\bin\jpackage.exe" --type app-image --name "Order Desk" --input $inputDir --main-jar "Order Desk.jar" --dest $destination --verbose

if ($LASTEXITCODE -ne 0) {
    throw "jpackage failed with exit code $LASTEXITCODE"
}

Get-ChildItem -LiteralPath $destination -Force
~~~

Trên Linux Bash:

~~~bash
project_root="$(pwd)"
input_dir="$project_root/build/input files"
destination="$project_root/release packages"

mkdir -p "$destination"

"$JAVA_HOME/bin/jpackage" \
  --type app-image \
  --name "Order Desk" \
  --input "$input_dir" \
  --main-jar "Order Desk.jar" \
  --dest "$destination" \
  --verbose

find "$destination" -maxdepth 2 -print
~~~

Kết quả là application image nằm dưới destination đã chọn. Nếu thay **--type app-image** bằng định dạng native phù hợp với hệ điều hành build, jpackage sẽ đặt package tương ứng trong cùng destination.

## 14. Checklist trước khi chạy jpackage

| Kiểm tra | Mục đích |
| --- | --- |
| Đã xác định working directory chưa? | Hiểu đúng cách phân giải path tương đối |
| Đã chọn --dest rõ ràng chưa? | Kiểm soát nơi lưu artifact |
| Đường dẫn có khoảng trắng đã được quote chưa? | Đảm bảo mỗi path là một argument |
| Executable jpackage có path chứa khoảng trắng không? | Quote đúng đường dẫn chương trình |
| --input và --main-jar có khớp nhau không? | Đảm bảo tìm được JAR đầu vào |
| --temp có bị nhầm với --dest không? | Tách thư mục tạm khỏi artifact |
| --install-dir có bị nhầm với --dest không? | Tách nơi build khỏi nơi cài đặt |
| Đã chọn --type chưa? | Tránh phụ thuộc định dạng mặc định của nền tảng |
| Destination có quyền ghi và phù hợp cho lần build này không? | Tránh lỗi tạo artifact |
| Đã kiểm tra exit code và output chưa? | Xác nhận đóng gói thành công |

## 15. Kết luận

**--dest** hoặc **-d** chỉ định thư mục nơi jpackage đặt application image hoặc gói cài đặt. Nếu không chỉ định, kết quả được đặt trong working directory hiện tại. Đường dẫn có thể tuyệt đối hoặc tương đối, vì vậy build script nên dùng đường dẫn tuyệt đối khi cần kết quả ổn định giữa IDE, terminal và CI.

Khi đường dẫn chứa khoảng trắng, hãy quote toàn bộ giá trị theo cú pháp của shell đang sử dụng: dấu nháy đơn hoặc kép trong PowerShell, dấu nháy kép trong Command Prompt và dấu nháy trong Bash. Quy tắc tương tự áp dụng cho **--input**, **--icon**, **--runtime-image**, **--resource-dir** và các tùy chọn đường dẫn khác.

Cần phân biệt **--dest** với **--temp** và **--install-dir**: một tùy chọn lưu sản phẩm build, một tùy chọn chọn thư mục tạm, còn tùy chọn kia quy định nơi cài ứng dụng trên máy đích. Chỉ định rõ **--type**, kiểm tra exit code và xác minh artifact trong destination sẽ giúp quy trình đóng gói dễ lặp lại và ít lỗi do đường dẫn.

## Tài liệu tham khảo

- [The jpackage Command — Java SE 16](https://docs.oracle.com/en/java/javase/16/docs/specs/man/jpackage.html)
- [Packaging Tool User's Guide — Java SE 16](https://docs.oracle.com/javase/jp/16/jpackage/packaging-tool-user-guide.pdf)
- [Support Application Features — Java SE 16](https://docs.oracle.com/en/java/javase/16/jpackage/support-application-features.html)
- [The jpackage Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [Packaging Tool User's Guide — Java SE 26](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-tool-user-guide.pdf)

