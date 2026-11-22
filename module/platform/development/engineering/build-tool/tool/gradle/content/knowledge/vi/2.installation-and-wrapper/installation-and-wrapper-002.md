# Cài đặt Gradle thủ công, bằng trình quản lý phiên bản và qua IDE

## Mục tiêu bài học

Sau bài này, bạn có thể: (1) chọn cách cài Gradle phù hợp với hệ điều hành và mục đích sử dụng; (2) tự cài bản phân phối Gradle và cấu hình môi trường; (3) cài hoặc chuyển phiên bản bằng trình quản lý gói/SDK; (4) cấu hình IntelliJ IDEA, Eclipse hoặc VS Code để làm việc với dự án Gradle; (5) kiểm tra và xử lý lỗi thường gặp.

**Phân biệt ngay từ đầu:** Gradle là công cụ build; **Gradle Wrapper** là các script nằm trong từng dự án, tự dùng đúng phiên bản Gradle dự án chỉ định. Nếu mở một dự án đã có **gradlew**, **gradlew.bat** và **gradle/wrapper/gradle-wrapper.properties**, thông thường **không cần cài Gradle toàn cục**. Cài Gradle riêng hữu ích khi khởi tạo dự án mới bằng dòng lệnh, thử nghiệm một bản Gradle hoặc quản trị máy phát triển. Sau khi tạo dự án, nên chuyển sang Wrapper để cả nhóm và CI chạy cùng phiên bản.

## 1. Chuẩn bị trước khi cài

### 1.1. Kiểm tra Java và Gradle hiện có

Gradle chạy trên JVM nên cần JDK phù hợp. **Gradle 9.x yêu cầu JDK 17 trở lên để chạy Gradle**; với dự án dùng phiên bản Gradle cũ hoặc mới khác, hãy đối chiếu [bảng tương thích Java–Gradle](https://docs.gradle.org/current/userguide/compatibility.html). Phiên bản JDK *chạy Gradle* có thể khác phiên bản Java mà ứng dụng được biên dịch bằng Java Toolchains; đừng nhầm hai khái niệm.

Trên Linux/macOS (Terminal) hoặc Windows (PowerShell/Command Prompt), kiểm tra:

~~~text
java -version
javac -version
gradle --version
~~~

- **java -version** xác nhận runtime Java; **javac -version** giúp xác nhận đang có JDK.
- Nếu **gradle --version** chạy được, hãy xem phiên bản và JVM hiển thị trước khi cài thêm.
- Nếu **gradle** không được nhận diện, chưa thể kết luận máy chưa có Gradle: có thể đã giải nén nhưng chưa thêm thư mục **bin** vào **PATH**.
- Kiểm tra **JAVA_HOME** khi cần chọn JDK cụ thể. Giá trị phải trỏ đến **thư mục gốc của JDK**, không trỏ vào **bin** hay thư mục JRE.

Ví dụ cách xem biến môi trường:

~~~bash
# Linux/macOS
echo "$JAVA_HOME"
command -v java
command -v gradle
~~~

~~~powershell
# Windows PowerShell
$env:JAVA_HOME
Get-Command java
Get-Command gradle
~~~

**GRADLE_HOME** (tùy chọn) là nơi giải nén bộ cài Gradle. **GRADLE_USER_HOME** là thư mục lưu cache, cấu hình người dùng và các bản phân phối Wrapper (mặc định thường là thư mục **.gradle** trong home). Đó là hai chức năng khác nhau. Với Gradle cài toàn cục, thư mục **bin** của bản phân phối phải nằm trên **PATH**; chỉ đặt **GRADLE_HOME** mà không sửa **PATH** thì chưa đủ để gọi lệnh **gradle** từ mọi nơi.

### 1.2. Chọn phương án

| Phương án | Phù hợp khi | Điểm cần lưu ý |
| --- | --- | --- |
| **Cài thủ công từ ZIP** | Cần kiểm soát chính xác bản phân phối, không dùng trình quản lý gói, hoặc thiết lập môi trường đặc biệt | Tự giải nén, quản lý PATH, cập nhật và dọn bản cũ |
| **SDKMAN!** | Linux/macOS/WSL, muốn cài và chuyển qua lại nhiều bản Gradle | Có bản mặc định của người dùng và bản dùng tạm trong phiên shell |
| **Homebrew / Scoop / Chocolatey / winget** | Muốn cài, cập nhật nhanh bằng công cụ quản lý gói đã có | Phiên bản trên kho có thể khác bản stable mới nhất của Gradle |
| **IDE + Gradle Wrapper** | Làm việc với dự án thực tế trong IntelliJ IDEA, Eclipse, VS Code hoặc Android Studio | IDE có thể tải Gradle cho dự án mà lệnh **gradle** toàn cục vẫn chưa tồn tại |

**Ví dụ phiên bản trong bài:** **9.9.0** (bản stable được liệt kê ngày 09/11/2026). Khi thực hành sau thời điểm này, thay bằng bản stable tương thích với dự án lấy từ [Gradle Releases](https://gradle.org/releases/); không tự ý nâng Wrapper của một dự án đang hoạt động.

## 2. Cài đặt thủ công từ bản phân phối ZIP

### 2.1. Tải đúng bản Gradle

1. Mở [https://gradle.org/releases/](https://gradle.org/releases/), chọn phiên bản ổn định mong muốn và tải **Binary-only (bin)**. Bản **all** có thêm tài liệu và mã nguồn; không bắt buộc để chạy build.
2. Tải tệp kiểm tra **SHA-256** tương ứng nếu muốn kiểm tra tính toàn vẹn. So sánh hash của file ZIP vừa tải với giá trị Gradle công bố; không chỉ nhìn tên file.
3. Chỉ lấy bản phân phối từ nguồn chính thức hoặc kho nội bộ đáng tin cậy. Hãy nhớ rằng ZIP chứa thư mục **gradle-9.9.0**, còn lệnh thực thi nằm trong **gradle-9.9.0/bin**.

Ví dụ kiểm tra SHA-256 trong thư mục chứa tệp ZIP:

~~~bash
# Linux
sha256sum gradle-9.9.0-bin.zip

# macOS
shasum -a 256 gradle-9.9.0-bin.zip
~~~

~~~powershell
# Windows PowerShell
Get-FileHash -Algorithm SHA256 .\gradle-9.9.0-bin.zip
~~~

### 2.2. Linux và macOS: giải nén rồi đặt PATH

Giả sử ZIP được tải vào thư mục **Downloads**, bạn có thể cài trong thư mục home mà không cần quyền quản trị:

~~~bash
mkdir -p "$HOME/tools/gradle"
unzip "$HOME/Downloads/gradle-9.9.0-bin.zip" -d "$HOME/tools/gradle"

export GRADLE_HOME="$HOME/tools/gradle/gradle-9.9.0"
export PATH="$GRADLE_HOME/bin:$PATH"

gradle --version
~~~

Những lệnh **export** chỉ có hiệu lực trong terminal hiện tại. Để dùng lâu dài, thêm hai dòng **export** vào tệp cấu hình của shell bạn thực sự sử dụng, thường là **~/.zshrc** (zsh) hoặc **~/.bashrc** (bash), rồi mở terminal mới hoặc nạp lại cấu hình. Nếu cài nhiều phiên bản, hãy giữ từng thư mục riêng và đổi **GRADLE_HOME** tới phiên bản mong muốn. Việc thay đổi **PATH** ở đầu danh sách giúp bản bạn chọn được ưu tiên hơn bản cũ.

Bạn cũng có thể cài ở **/opt/gradle** hoặc **/usr/local/gradle** theo chính sách máy, nhưng thao tác tạo thư mục có thể cần quyền quản trị. Không có yêu cầu kỹ thuật bắt buộc phải cài ở vị trí hệ thống.

### 2.3. Windows: giải nén rồi đặt PATH

Cách bằng giao diện: giải nén **gradle-9.9.0-bin.zip** để có **C:\Gradle\gradle-9.9.0**; vào **System Properties → Advanced → Environment Variables**. Tạo **GRADLE_HOME = C:\Gradle\gradle-9.9.0** (tùy chọn), rồi thêm **%GRADLE_HOME%\bin** hoặc đường dẫn **C:\Gradle\gradle-9.9.0\bin** vào biến **Path**. Mở PowerShell/Command Prompt **mới** rồi chạy **gradle --version**.

Có thể thử nhanh trong PowerShell trước khi thay đổi biến môi trường lâu dài:

~~~powershell
# Giả sử ZIP nằm trong Downloads của tài khoản hiện tại.
$zip = Join-Path $HOME 'Downloads\gradle-9.9.0-bin.zip'
New-Item -ItemType Directory -Force -Path 'C:\Gradle' | Out-Null
Expand-Archive -LiteralPath $zip -DestinationPath 'C:\Gradle'

$env:GRADLE_HOME = 'C:\Gradle\gradle-9.9.0'
$env:Path = "$env:GRADLE_HOME\bin;$env:Path"

gradle --version
~~~

Các lệnh gán **$env:** phía trên chỉ đổi môi trường của **phiên PowerShell hiện tại**. Để lưu lâu dài, dùng giao diện **Environment Variables** hoặc cơ chế cấu hình môi trường được tổ chức cho phép. Không trỏ PATH đến file **gradle.bat**; trỏ đến **thư mục bin** chứa file đó. Nếu ổ **C:** bị hạn chế quyền, giải nén ở thư mục người dùng và cập nhật đường dẫn tương ứng.

### 2.4. Xác nhận cài thủ công thành công

~~~text
gradle --version
~~~

Đầu ra đúng sẽ có tiêu đề **Gradle 9.9.0** (hoặc phiên bản bạn đã chọn) cùng thông tin **Launcher JVM / Daemon JVM / OS**. Đây là ví dụ về **những trường cần thấy**, không phải bản sao đầu ra cố định: ngày build, bản Java và hệ điều hành sẽ khác trên từng máy.

Với Windows, dùng **where.exe gradle**; trên Linux/macOS dùng **command -v gradle** (hoặc **type -a gradle**) để tìm lệnh đang được ưu tiên. Nếu kết quả chỉ đến bản cũ, kiểm tra thứ tự các mục trong **PATH**.

## 3. Cài bằng trình quản lý phiên bản hoặc trình quản lý gói

Cần phân biệt hai nhóm: **version manager** hỗ trợ chuyển giữa các phiên bản SDK (ví dụ SDKMAN!), còn **package manager** cài/cập nhật gói theo kho (Homebrew, Scoop, Chocolatey, winget). Không nên cài đồng thời bằng nhiều công cụ nếu không có nhu cầu, vì nhiều đường dẫn **gradle** trên PATH dễ gây nhầm phiên bản.

### 3.1. SDKMAN! (Linux, macOS, WSL)

Cài SDKMAN! theo [hướng dẫn chính thức](https://sdkman.io/install/) và mở shell có lệnh **sdk**. Sau đó:

~~~bash
sdk version
sdk list gradle
sdk install gradle 9.9.0
sdk current gradle
gradle --version
~~~

Chuyển phiên bản đã cài cho **terminal hiện tại**:

~~~bash
sdk use gradle 9.9.0
gradle --version
~~~

Đặt bản dùng **mặc định cho các shell mới**:

~~~bash
sdk default gradle 9.9.0
~~~

Nếu không cần cố định phiên bản, **sdk install gradle** sẽ cài bản stable mà SDKMAN! cung cấp tại thời điểm chạy. Có thể dùng file **.sdkmanrc** và **sdk env** để chọn bộ SDK theo dự án nếu nhóm thống nhất cách quản lý; tuy nhiên điều này không thay thế Gradle Wrapper được commit trong repository. Trên Windows, SDKMAN! thường dùng **bên trong WSL**; PATH và Gradle trong WSL thuộc môi trường Linux, không tự trở thành lệnh Windows gốc.

### 3.2. Homebrew (macOS, một số bản Linux)

Nếu Homebrew đã cài:

~~~bash
brew install gradle
gradle --version
~~~

Cập nhật Gradle do Homebrew quản lý:

~~~bash
brew upgrade gradle
~~~

Homebrew quản lý công thức và vị trí liên kết lệnh; thông thường không cần tự đặt **GRADLE_HOME**. Nếu cần khóa chặt phiên bản cho dự án, ưu tiên **Wrapper**, vì công thức Homebrew có thể được cập nhật theo kho.

### 3.3. Windows: chọn một trong winget, Scoop, Chocolatey

Những lệnh sau là **ba lựa chọn thay thế**, không phải ba bước chạy liên tiếp. Chỉ sử dụng công cụ đã được cài và được phép dùng trên máy:

~~~powershell
# Windows Package Manager (winget)
winget install --id Gradle.Gradle --exact
~~~

~~~powershell
# Scoop
scoop install gradle
~~~

~~~powershell
# Chocolatey
choco install gradle -y
~~~

Sau khi cài, mở terminal mới và chạy **gradle --version**. Để nâng cấp, dùng cơ chế tương ứng như **winget upgrade --id Gradle.Gradle --exact**, **scoop update gradle** hoặc **choco upgrade gradle -y**. Một số môi trường yêu cầu PowerShell có quyền quản trị cho Chocolatey hoặc chính sách cài gói riêng. Phiên bản phát hành trên các kho của bên thứ ba có thể chậm hơn nguồn Gradle chính thức.

### 3.4. Ưu và nhược điểm khi chọn công cụ

| Tiêu chí | ZIP thủ công | SDKMAN! | Package manager |
| --- | --- | --- | --- |
| Cài không cần công cụ quản lý ngoài | Có | Không | Không |
| Chuyển nhiều phiên bản trên cùng máy | Tự đổi đường dẫn | Có lệnh chuyển phiên bản | Tùy công cụ/gói; không mặc nhiên thuận tiện |
| Cập nhật | Tự tải, giải nén và đổi PATH | Qua lệnh sdk | Qua lệnh cập nhật gói |
| Kiểm soát chính xác bản Gradle | Chọn đúng ZIP | Chọn phiên bản khả dụng | Phụ thuộc phiên bản kho |
| Phù hợp cho dự án nhóm | Dùng khi tạo/kiểm thử môi trường | Hữu ích cho nhà phát triển | Tiện cho máy cá nhân; vẫn nên chạy dự án qua Wrapper |

## 4. Làm việc với Gradle thông qua IDE

**IDE tích hợp Gradle không đồng nghĩa với việc lệnh gradle đã được cài cho toàn hệ thống.** IDE có thể tải/sử dụng một bản Gradle theo Wrapper hoặc cấu hình riêng, trong khi terminal ngoài IDE vẫn báo không tìm thấy **gradle**. Thường nên **mở dự án ở thư mục gốc chứa settings.gradle hoặc settings.gradle.kts**, rồi để IDE import mô hình Gradle.

### 4.1. IntelliJ IDEA

1. Cài JDK phù hợp, mở **File → Open** và chọn thư mục dự án Gradle hoặc file build Gradle; với dự án mới, có thể chọn loại dự án **Gradle** trong trình tạo project.
2. Đợi IntelliJ import/sync. Mở **Settings/Preferences → Build, Execution, Deployment → Build Tools → Gradle** (tên mục có thể thay đổi chút ít giữa các bản).
3. Ở phần **Distribution / Use Gradle from**, ưu tiên **Gradle Wrapper** dựa trên file **gradle-wrapper.properties**. Khi cần kiểm thử bản Gradle đã cài thủ công, chọn **Local installation / Specified location** và trỏ tới thư mục gốc **gradle-9.9.0**, không phải thư mục **bin**.
4. Ở **Gradle JVM**, chọn JDK tương thích với bản Gradle đang chạy; lưu ý **Project SDK**, **Gradle JVM** và Java Toolchain có thể là ba lựa chọn riêng.
5. Trong cửa sổ **Gradle**, thực hiện **Reload/Sync** rồi chạy task **help** hoặc **tasks**. Nếu chạy build/test bằng Gradle trong IDE, kết quả sẽ phù hợp hơn với lệnh Wrapper ngoài terminal khi cùng cấu hình.

**Khi nào chọn Local installation?** Chỉ khi bạn chủ động muốn sử dụng bản Gradle hệ thống để thử nghiệm hoặc dự án chưa có Wrapper. Đối với dự án nhóm đã có Wrapper, để IDE dùng Wrapper giảm rủi ro lệch phiên bản plugin/build logic.

### 4.2. Eclipse IDE với Buildship

1. Đảm bảo Eclipse có tích hợp **Buildship Gradle Integration** (có sẵn trong một số bộ cài, hoặc cài qua Eclipse Marketplace).
2. Chọn **File → Import → Gradle → Existing Gradle Project** và trỏ tới thư mục gốc của dự án.
3. Trong tùy chọn Gradle distribution khi import hoặc trong cấu hình Buildship, chọn dùng **Gradle Wrapper** nếu dự án cung cấp; chỉ định **Local Gradle installation** nếu cần dùng bản cài thủ công.
4. Kiểm tra JDK mà Eclipse/Buildship dùng để chạy Gradle, hoàn tất import và thử chạy một task Gradle từ giao diện.

Nhớ rằng **Eclipse Buildship** là tích hợp để nhập/chạy dự án Gradle. Nó không phải bằng chứng Gradle CLI toàn cục đã xuất hiện trên **PATH**. Nếu import thất bại, hãy chạy Wrapper trong terminal để phân biệt lỗi dự án với lỗi cấu hình IDE.

### 4.3. Visual Studio Code

1. Cài JDK và các extension Java cần thiết; cài thêm **Gradle for Java** từ Visual Studio Code Marketplace.
2. Mở **toàn bộ thư mục dự án** Gradle (không chỉ một file Java). Extension sẽ nhận diện cấu hình Gradle, nhập mô hình build và hiển thị **Gradle Tasks**/công cụ liên quan.
3. Chờ import/sync rồi chạy task **help**, **test** hoặc **build** trong Gradle Tasks. Có thể mở terminal tích hợp để chạy script Wrapper của dự án và so sánh kết quả.
4. Nếu extension không nhập dự án, kiểm tra Java runtime cấu hình trong VS Code, file build, Wrapper và trạng thái tải dependency. Tính năng Gradle for Java tập trung vào dự án Java, không thay thế công cụ Android chuyên biệt.

Việc cài extension **không tự đảm bảo lệnh gradle toàn cục có trên PATH**. Với dự án có Wrapper, terminal tích hợp vẫn có thể chạy **./gradlew** hoặc **.\gradlew.bat** dù **gradle** không được nhận diện.

### 4.4. Android Studio

Android Studio tích hợp quy trình Gradle cho dự án Android và thường dùng **Gradle Wrapper** cùng **Android Gradle Plugin** theo cấu hình dự án. Không tự thay Wrapper lên bản Gradle mới chỉ vì vừa cài bản toàn cục: phiên bản **Android Gradle Plugin**, Gradle và JDK cần tương thích với nhau theo hướng dẫn Android. Khi sync lỗi, kiểm tra các phiên bản do **dự án** quy định trước.

## 5. Kiểm chứng thực tế và mối quan hệ với Wrapper

### 5.1. Trên máy đã cài Gradle

Ở một thư mục trống dành cho thực hành, chạy:

~~~bash
mkdir gradle-install-demo
cd gradle-install-demo
gradle init --type basic --dsl kotlin --project-name gradle-install-demo
gradle help
~~~

Lệnh **gradle init** khởi tạo dự án đơn giản và tạo các file cấu hình/Wrapper (trình khởi tạo có thể hỏi thêm tùy phiên bản). **gradle help** là task nhẹ để xác nhận Gradle có thể đọc dự án; nếu thành công, phần kết thúc thường có **BUILD SUCCESSFUL**. Việc tải dependency có thể cần mạng trong lần đầu.

Sau khi dự án có Wrapper, **từ thư mục gốc dự án**:

~~~bash
# Linux/macOS
./gradlew --version
./gradlew help
~~~

~~~powershell
# Windows PowerShell
.\gradlew.bat --version
.\gradlew.bat help
~~~

- **gradle help**: dùng bản Gradle cài toàn cục đang được PATH chọn.
- **./gradlew help** hoặc **.\gradlew.bat help**: dùng phiên bản do dự án khai báo trong **gradle/wrapper/gradle-wrapper.properties**. Lần đầu Wrapper có thể tải bản phân phối về cache.
- Nếu hai lệnh báo **hai phiên bản khác nhau**, đó là hành vi có thể hoàn toàn bình thường; **phiên bản Wrapper** mới là bản nên dùng cho build của dự án nhóm.
- Khi muốn tạo hoặc thay đổi Wrapper cho **dự án của chính bạn**, có thể chạy **gradle wrapper --gradle-version 9.9.0 --distribution-type bin** (hoặc lệnh Wrapper hiện có) và kiểm tra thay đổi. Với dự án đã có Wrapper, chỉ nâng phiên bản khi đã kiểm chứng khả năng tương thích và được nhóm thống nhất.
- Khi đưa dự án vào Git, thường commit **gradlew**, **gradlew.bat**, **gradle/wrapper/gradle-wrapper.jar** và **gradle/wrapper/gradle-wrapper.properties**; chúng bảo đảm người khác/CI có thể khởi chạy đúng bản Gradle. Tránh sửa trực tiếp JAR Wrapper hoặc giả định chỉ cần một file script.

### 5.2. Checklist sau cài đặt

1. **java -version** và **javac -version** cho kết quả JDK phù hợp; **JAVA_HOME** (nếu đặt) trỏ đúng thư mục JDK.
2. **gradle --version** chạy được nếu bạn đã cài Gradle toàn cục, hiển thị đúng phiên bản mong muốn.
3. Mở terminal mới vẫn nhận diện được **gradle** (kiểm tra PATH đã được lưu bền vững).
4. Nếu dự án có Wrapper, chạy được **./gradlew help** hoặc **.\gradlew.bat help**.
5. IDE sync/import thành công; **Gradle JVM** trong IDE tương thích và **Gradle distribution** được chọn đúng mục tiêu (Wrapper hoặc local).
6. Nếu làm việc nhóm, build bằng Wrapper trước khi kết luận cài Gradle hệ thống đã “giải quyết” vấn đề của dự án.

## 6. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra/sửa |
| --- | --- | --- |
| **gradle: command not found** hoặc **'gradle' is not recognized** | Chưa cài, PATH chưa có thư mục bin, hoặc terminal chưa nạp biến mới | Kiểm tra thư mục **gradle-*/bin**, thêm vào PATH, mở terminal mới; dùng **command -v gradle** / **where.exe gradle** |
| **JAVA_HOME is set to an invalid directory** hoặc không tìm được Java | JAVA_HOME trỏ vào **bin**, JRE hoặc JDK đã bị di chuyển | Trỏ JAVA_HOME tới thư mục gốc JDK; chạy lại **java -version** / **javac -version** |
| **Unsupported Java / Gradle requires Java ...** | Bản JDK chạy Gradle không tương thích | Kiểm tra bản Gradle và [compatibility matrix](https://docs.gradle.org/current/userguide/compatibility.html); với Gradle 9.x dùng JDK 17+; kiểm tra cả **Gradle JVM** trong IDE |
| Máy báo **Gradle 8.x** dù vừa cài 9.x | PATH ưu tiên đường dẫn cũ hoặc đang dùng trình quản lý gói khác | Xem **where.exe gradle** / **type -a gradle**, sửa thứ tự PATH hoặc đổi bản đang active trong version manager |
| Terminal build được nhưng IDE sync lỗi | IDE dùng JDK/Gradle distribution khác hoặc gặp lỗi plugin/repository | Kiểm tra **Gradle JVM**, chọn Wrapper, xem thông báo sync và thử chạy Wrapper trong terminal |
| Wrapper tải Gradle thất bại | Proxy, DNS, TLS, mạng, quyền ghi cache hoặc URL distribution sai | Kiểm tra kết nối và **distributionUrl** trong **gradle-wrapper.properties**, cấu hình proxy theo môi trường, kiểm tra cache/quyền; không tải JAR từ nguồn không rõ |
| Build khác nhau giữa hai máy | Dùng Gradle toàn cục/IDE local khác version dự án; JDK hoặc dependency khác | Dùng cùng Wrapper; so sánh JDK và cấu hình plugin/toolchain; giữ Wrapper trong Git |
| **Permission denied** khi chạy **./gradlew** trên Unix | Script chưa có quyền thực thi | Với dự án tin cậy, chạy **chmod +x gradlew** và commit executable bit khi cần |
| Lệnh **gradle** chạy được nhưng **.\gradlew.bat** không có | Đang ở sai thư mục hoặc dự án không cung cấp Wrapper | Chuyển đến root dự án, kiểm tra các file Wrapper; không tự sửa cấu trúc dự án đang làm việc khi chưa rõ quy ước |

**Lưu ý bảo mật:** kiểm tra checksum bản ZIP tải thủ công; ưu tiên nguồn chính thức, giữ Wrapper JAR từ repository tin cậy và tránh chạy script của dự án lạ khi chưa xem xét. Lần chạy đầu có thể tải bản Gradle và dependencies, nên “chạy offline” chỉ khả thi khi những thành phần cần thiết đã có sẵn trong cache.

## 7. Tình huống chọn cách cài

- **Bạn clone một repo công ty có gradlew:** cài đúng JDK, chạy **./gradlew build** (Windows: **.\gradlew.bat build**), chọn Wrapper trong IDE; chưa cần cài Gradle toàn cục.
- **Bạn muốn học Gradle CLI từ đầu trên macOS:** dùng Homebrew để bắt đầu nhanh, hoặc SDKMAN! nếu muốn thử nhiều bản; sau **gradle init**, sử dụng Wrapper trong dự án thực hành.
- **Bạn đang ở Windows không được cài công cụ quản lý gói:** tải ZIP chính thức, giải nén vào thư mục được phép, cấu hình PATH rồi xác nhận **gradle --version**.
- **Bạn dùng IntelliJ IDEA mà gradle ngoài terminal không tồn tại:** có thể vẫn import và build qua Wrapper thành công. Chỉ cài Gradle global nếu cần sử dụng riêng lệnh **gradle** ngoài dự án.
- **Bạn đổi giữa nhiều dự án khác phiên bản Gradle:** mỗi dự án nên chạy Wrapper của chính nó. Version manager hữu ích cho thao tác CLI độc lập, nhưng không nên thay phiên bản dự án bằng PATH máy cá nhân.

## 8. Nguồn tham khảo chính thức

- [Gradle — Installing Gradle](https://docs.gradle.org/current/userguide/installation.html): điều kiện Java, ZIP, cài qua trình quản lý gói và xác minh.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): vai trò Wrapper, nội dung file, cách chạy và nâng phiên bản.
- [Gradle — Releases](https://gradle.org/releases/): bản phát hành, bộ cài và checksum.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): tương thích Java/JVM và Gradle.
- [SDKMAN! — Usage](https://sdkman.io/usage/): cài, dùng tạm và đặt mặc định phiên bản SDK.
- [JetBrains — Gradle settings](https://www.jetbrains.com/help/idea/gradle-settings.html): chọn Wrapper/local distribution và Gradle JVM.
- [Eclipse Buildship](https://github.com/eclipse-buildship/buildship): tích hợp Gradle cho Eclipse.
- [Visual Studio Code — Java build tools](https://code.visualstudio.com/docs/java/java-build): extension Gradle for Java và cơ chế import/build.

**Kết luận thực hành:** cài thủ công hoặc qua trình quản lý gói giúp bạn có lệnh **gradle** trên máy; IDE giúp import/chạy build thuận tiện; còn **Wrapper** là cách chủ đạo để dự án thực tế dùng đúng phiên bản Gradle một cách nhất quán.