# Dùng help:effective-settings và tránh làm lộ bí mật trong Maven

Maven có thể đọc cấu hình từ **`settings.xml` toàn cục**, **`settings.xml` của người dùng**, tham số dòng lệnh và môi trường chạy. Vì vậy, khi một máy tải dependency được nhưng máy khác không thể kết nối repository, chỉ mở một tệp `settings.xml` thường chưa đủ: Maven có thể đang sử dụng **cấu hình có hiệu lực** khác với cấu hình bạn nghĩ.

Maven Help Plugin cung cấp goal **`help:effective-settings`** để hiển thị các settings đã được Maven tính toán sau khi kết hợp nguồn cấu hình phù hợp. Đây là công cụ quan trọng để chẩn đoán `localRepository`, `mirrors`, `servers`, `proxies`, `profiles` và `activeProfiles`.

Tuy nhiên, `settings.xml` cũng có thể chứa **tên người dùng, thông tin xác thực repository, cấu hình proxy, đường dẫn private key hoặc dữ liệu nội bộ**. Việc in toàn bộ effective settings vào console, lưu ra file, đính kèm log CI hoặc gửi ảnh chụp màn hình có thể làm rò rỉ dữ liệu.

**Nguyên tắc cốt lõi:**

- Dùng `help:effective-settings` để **hiểu Maven thực sự đang dùng cấu hình nào**.
- Theo tài liệu Maven Help Plugin, tham số **`showPasswords` mặc định là `false`**, vì vậy các trường mật khẩu mà plugin nhận diện được che theo mặc định.
- **Không được suy ra rằng toàn bộ output đã an toàn để công khai**: URL nội bộ, username, path, thông tin profile hoặc secret được đặt trong trường không được che vẫn có thể xuất hiện.
- Không bật `-DshowPasswords=true` trong môi trường có thông tin thật, không đưa raw output vào issue, pull request, chat, log CI hay tài liệu công khai.
- Khi cần trao đổi sự cố, chỉ chia sẻ **bản tóm tắt đã kiểm duyệt thủ công**: ví dụ ID của mirror có được chọn hay không, profile nào đang bật và repository bị ảnh hưởng, không chia sẻ thông tin xác thực.

Bài học sử dụng cách gọi phù hợp với Maven 3.x và Maven Help Plugin; ở phần bảo mật có phân biệt Maven 3 và Maven 4 khi cần thiết.

## 1. `settings.xml` là gì và khác `pom.xml` thế nào?

**`pom.xml`** là mô hình dự án: tọa độ, dependencies, plugins, build lifecycle, modules và cấu hình gắn với dự án. Tệp này thường được quản lý trong Git.

**`settings.xml`** chứa cấu hình liên quan tới **máy chạy Maven hoặc tài khoản đang chạy Maven**: proxy, mirror, local repository, repository credentials, profile theo môi trường và một số tùy chọn khác.

| Nội dung | Thường nằm ở đâu? | Lý do |
| --- | --- | --- |
| `groupId`, `artifactId`, `version` | `pom.xml` | Định danh dự án và artifact. |
| Dependencies và phiên bản plugin | `pom.xml`, parent POM | Mô tả cách dự án build và những thư viện sử dụng. |
| URL repository để triển khai artifact | `pom.xml`, trong `distributionManagement` | Định nghĩa đích triển khai của dự án. |
| Username/password hoặc cơ chế xác thực của server | `settings.xml` hoặc secret integration phù hợp | Tránh đưa bí mật vào POM được chia sẻ. |
| Mirror thay thế Maven Central | `settings.xml` | Quyết định cách truy cập repository trong một môi trường. |
| Proxy mạng doanh nghiệp | `settings.xml` | Phụ thuộc mạng của từng máy hoặc CI runner. |
| Local repository tùy chỉnh | `settings.xml` hoặc tùy chọn phù hợp | Điều khiển nơi cache artifact trên máy. |

Cấu trúc của settings không giống POM. Hai tệp có thể cùng chứa `<profiles>` nhưng các phần tử được hỗ trợ trong **settings profile** hạn chế hơn POM profile: thông thường liên quan properties, repositories và pluginRepositories, không phải nơi thay toàn bộ cấu hình build plugin của dự án.

**Không ghi password, access token hoặc private key vào `pom.xml`.** POM có thể được commit và phát hành cùng artifact; cấu hình bảo mật nên được cấp từ môi trường được quản lý.

## 2. Hai nguồn settings chính: global và user

Với Maven 3, các vị trí thông dụng là:

```text
MAVEN_HOME/
└── conf/
    └── settings.xml              <- global settings

USER_HOME/
└── .m2/
    ├── settings.xml              <- user settings
    ├── settings-security.xml     <- thông tin hỗ trợ giải mã Maven 3, nếu dùng
    └── repository/               <- local repository mặc định
```

Trên Linux/macOS, user home thường là `~`; trên Windows, ví dụ có thể là `C:\Users\alice`. Đừng nhầm user home với project root. `.m2` cũng **không phải** thư mục nguồn `src` của một dự án Maven.

Một số điểm quan trọng:

1. **Global settings** nằm dưới thư mục cài Maven, thường là `${maven.home}/conf/settings.xml`.
2. **User settings** mặc định nằm ở `${user.home}/.m2/settings.xml`, và có thể không tồn tại nếu người dùng chưa cần cấu hình.
3. Maven tổng hợp settings từ cả hai nguồn; khi có cấu hình xung đột và quy tắc hợp nhất áp dụng, **user settings thường được ưu tiên**. Với danh sách có ID như `mirrors`, `servers`, `profiles`, việc hợp nhất theo ID quan trọng hơn cách nghĩ “chỉ nối hai tệp”.
4. `settings.xml` không phải nơi ghi thay đổi theo dự án nếu thay đổi đó phải được dùng nhất quán bởi mọi người. Phân biệt cấu hình dự án với cấu hình môi trường để tránh lỗi “máy tôi chạy được”.
5. Nếu muốn dùng tệp khác, Maven có các lựa chọn CLI `-s` / `--settings` và `-gs` / `--global-settings`.

Ví dụ về việc **chọn** tệp settings, không in nội dung của chúng:

```bash
mvn -s /path/to/user-settings.xml verify
mvn -gs /path/to/global-settings.xml verify
mvn -s /path/to/user-settings.xml -gs /path/to/global-settings.xml verify
```

Các đường dẫn trên là ví dụ minh họa. `-s` chỉ định **user settings thay thế**, không có nghĩa cộng thêm tệp đó vào user settings mặc định. `-gs` chỉ định **global settings thay thế**. Maven vẫn xử lý việc kết hợp hai lớp theo quy tắc của phiên đang chạy.

**Lưu ý bảo mật:** bản thân đường dẫn tới settings không phải password, nhưng tên thư mục, username hoặc cấu trúc máy nội bộ có thể là thông tin nhạy cảm trong một số môi trường.

## 3. `help:effective-settings` thực sự hiển thị gì?

Goal này thuộc **Apache Maven Help Plugin**, không phải một lệnh shell đọc XML thuần túy. Maven tải cấu hình và kết hợp settings, rồi Help Plugin hiển thị mô hình settings có hiệu lực.

Lệnh cơ bản:

```bash
mvn help:effective-settings
```

Trong môi trường CI hoặc terminal muốn giảm tương tác và tiến độ tải:

```bash
mvn -B -ntp help:effective-settings
```

`-B` bật batch mode. `-ntp` (no transfer progress) giúp giảm log tiến độ tải trên các phiên Maven hỗ trợ. Nếu Help Plugin chưa có trong local repository, Maven có thể phải tải plugin từ remote repository; lỗi mạng/xác thực có thể xảy ra trước khi nó tạo output.

Với Maven Help Plugin 3.5.2, tài liệu mô tả:

- Goal: `help:effective-settings`.
- Tham số `output`: ghi kết quả vào một tệp thay vì chỉ hiển thị trên console.
- Tham số `showPasswords`: cho phép yêu cầu hiện mật khẩu, **mặc định `false`** vì lý do bảo mật.
- Cấu hình settings hiển thị là kết quả của việc tính toán settings và hợp nhất global/user settings trong phạm vi hỗ trợ của goal.

Ví dụ minh họa **chỉ những trường không nhạy cảm** mà effective settings có thể giúp kiểm tra:

```xml
<settings>
    <localRepository>/home/example/.m2/repository</localRepository>
    <mirrors>
        <mirror>
            <id>training-mirror</id>
            <mirrorOf>central</mirrorOf>
            <url>https://repo.example.invalid/maven</url>
        </mirror>
    </mirrors>
    <activeProfiles>
        <activeProfile>training</activeProfile>
    </activeProfiles>
</settings>
```

Đây là **đoạn XML mô phỏng đã lược bỏ thông tin**, không phải output nguyên văn hay đầy đủ của plugin. Địa chỉ `repo.example.invalid` là miền minh họa không sử dụng làm endpoint mạng thực tế. Trong một output thật còn có các phần tử khác, namespace/schema và giá trị tùy môi trường.

**Phải nhớ:** effective settings trả lời “Maven đã tính ra cấu hình settings nào”, **không bảo đảm một repository sẽ truy cập được, tài khoản còn hiệu lực hoặc dependency đã tải thành công**. Muốn biết build thật, vẫn cần chạy goal thích hợp và đọc trạng thái lỗi/log của nó.

## 4. Cấu trúc settings cần biết khi xem output

| Phần tử | Ý nghĩa | Điều nên xác minh | Rủi ro khi chia sẻ |
| --- | --- | --- | --- |
| `<localRepository>` | Đường dẫn tới cache artifact cục bộ. | Có đúng vị trí mong muốn không? | Tiết lộ đường dẫn máy và tên tài khoản. |
| `<mirrors>` | Ánh xạ các repository sang mirror. | `mirrorOf` có đúng đối tượng? URL có đúng endpoint? | Tiết lộ host nội bộ hoặc kiến trúc repository. |
| `<servers>` | Cấu hình xác thực/tùy chọn cho server theo ID. | ID có khớp repo/mirror/deploy target? | Có thể chứa username, password, key/passphrase. |
| `<proxies>` | Proxy truy cập mạng. | Proxy có active không, host/port có đúng? | Có thể tiết lộ proxy nội bộ và credentials. |
| `<profiles>` | Các settings profile có repository và properties. | Có profile mong muốn không? | Có thể chứa URL nội bộ hoặc token trong properties. |
| `<activeProfiles>` | Những profile được khai báo để kích hoạt. | ID profile có chính xác? | Tiết lộ tên môi trường. |
| `<pluginGroups>` | Nhóm plugin được dùng khi tìm plugin theo prefix. | Có nhóm plugin đúng không? | Thường rủi ro thấp hơn nhưng vẫn là metadata nội bộ. |
| `<offline>` | Cấu hình chạy không truy cập mạng. | Đang bật ngoài ý muốn không? | Rủi ro thấp; hữu ích khi chẩn đoán. |

Bảng trên không có nghĩa mọi trường đều luôn xuất hiện. Tệp settings của một máy có thể rất nhỏ; các giá trị còn lại đến từ mặc định của Maven. Không nên coi việc thiếu một thẻ trong bản output rút gọn là lỗi.

Đặc biệt, **`<server><id>` phải khớp mục tiêu xác thực tương ứng**. Với deployment, ID có thể khớp với `distributionManagement.repository.id` trong POM. Với download qua mirror, hãy kiểm tra cách Maven chọn mirror và ID server được dùng cho kết nối thực tế; đừng chỉ so hostname một cách cảm tính.

## 5. Thực hành an toàn: kiểm tra settings bằng dữ liệu giả

Để hiểu cấu trúc và `help:effective-settings` mà không đụng tới bí mật thật, hãy tạo một tệp học tập có **toàn bộ giá trị minh họa không nhạy cảm**.

Tệp `training-settings.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
                              https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <localRepository>${user.home}/.m2/repository</localRepository>

    <profiles>
        <profile>
            <id>training</id>
            <properties>
                <training.mode>safe-demo</training.mode>
            </properties>
        </profile>
    </profiles>

    <activeProfiles>
        <activeProfile>training</activeProfile>
    </activeProfiles>
</settings>
```

Giải thích:

- `settings` là phần tử gốc khác với `project` trong POM.
- `localRepository` dùng biểu thức `${user.home}` được Maven hỗ trợ trong quá trình xử lý settings.
- Profile có ID `training`, thêm property không chứa secret.
- `activeProfiles` chọn profile này trong settings.
- Không có `<servers>`, mật khẩu, proxy hay repository URL nội bộ.

**Trước khi chạy:** tệp cần ở một thư mục mà bạn kiểm soát. Các dòng XML là ví dụ cho settings Maven 3.x; môi trường dùng Maven 4 cần đối chiếu schema và hành vi cụ thể của phiên bản mình đang chạy. Không đặt URL/proxy minh họa vào kết nối thực của tổ chức.

Chạy Help Plugin với tệp user settings thay thế:

```bash
mvn -B -ntp -s training-settings.xml help:effective-settings
```

Nếu Help Plugin đã có trong local cache hoặc Maven kết nối được tới repository phù hợp, output sẽ cho phép đối chiếu `localRepository`, profile `training` và property `training.mode`. **Không đưa dự đoán về toàn bộ stdout**, bởi plugin có thể in thêm cấu hình mặc định và log tùy môi trường.

Một chi tiết đáng lưu ý: `-s training-settings.xml` chỉ thay thế tệp user settings đang chọn; Maven vẫn có thể lấy **global settings** của bản Maven đang chạy. Vì vậy, nếu bạn đang ở máy dùng global settings doanh nghiệp, output còn có thể chứa cấu hình nội bộ dù tệp `training-settings.xml` không có secret. Để học an toàn, dùng môi trường thử nghiệm sạch và **không chia sẻ toàn bộ output** nếu chưa xem kỹ.

Có thể kiểm tra giá trị của một property dùng trong mô hình POM bằng Help Plugin ở ngữ cảnh thích hợp:

```bash
mvn -B -ntp -s training-settings.xml help:active-profiles
```

`help:active-profiles` giúp xác nhận những profile đang hoạt động. Goal này không đồng nghĩa hiệu lực của mọi property đều đã được áp dụng vào một POM bất kỳ; phải dùng lệnh cùng dự án và cùng profile nếu muốn kiểm tra build thực.

## 6. Tình huống thực tế: global settings và user settings ghi đè

Giả sử một tổ chức cài Maven với global settings khai báo mirror:

```xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>central</mirrorOf>
        <url>https://repo.example.invalid/company</url>
    </mirror>
</mirrors>
```

Một người dùng có user settings khai báo một mirror cùng ID nhưng URL khác:

```xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>central</mirrorOf>
        <url>https://repo.example.invalid/team</url>
    </mirror>
</mirrors>
```

Đây là hai **đoạn cấu hình minh họa đặt bên trong `<settings>`**. Với ID trùng, Maven phải hợp nhất theo quy tắc settings; user settings được ưu tiên trong những trường hợp xung đột phù hợp. Tuy nhiên đừng chỉ suy đoán từ hai đoạn trích, nhất là khi có nhiều mirror, alias hoặc mirrorOf pattern.

Lúc này, `help:effective-settings` hữu ích để trả lời:
- Mirror ID nào thực sự có trong settings?
- URL nào nằm trong cấu hình sau hợp nhất?
- `mirrorOf` có bao phủ repository dự kiến không?
- Có user settings hoặc CLI `-s` trỏ sang một tệp khác không?

Sau đó mới dùng log của **lệnh tải dependency thật** để xác nhận Maven có chọn mirror đúng hay không. Một mirror xuất hiện trong effective settings không có nghĩa mọi repository đều dùng mirror đó: lựa chọn còn phụ thuộc `mirrorOf`, ID repository và quy tắc Maven Resolver.

**Phân biệt cấu hình và kết nối:** nếu output ghi URL nội bộ đúng nhưng build bị `401 Unauthorized`, vấn đề có thể nằm ở credentials hoặc policy server; nếu `407 Proxy Authentication Required`, có thể nằm ở proxy. Không gửi nguyên tệp settings để nhờ chẩn đoán lỗi.

## 7. `showPasswords=false` mặc định: bảo vệ có giới hạn

Đây là phần quan trọng nhất về bảo mật.

Theo tài liệu chính thức của Maven Help Plugin, `help:effective-settings` có tham số **`showPasswords`**, mặc định là **`false`**. Plugin được thiết kế để **ẩn các mật khẩu mà nó biết cách nhận diện** khi in settings.

Nhưng việc che password **không có nghĩa toàn bộ output an toàn**:

- `<username>` có thể chứa tên đăng nhập thật.
- `<id>`, `<url>`, `<host>`, `<port>` và `<nonProxyHosts>` có thể tiết lộ cấu trúc mạng doanh nghiệp.
- `<localRepository>` và `<privateKey>` có thể chứa đường dẫn và danh tính máy/tài khoản.
- `<profiles><profile><properties>` hoặc trường cấu hình tùy chỉnh có thể vô tình chứa API token, webhook URL, credential trong URL hoặc chuỗi bí mật mà plugin **không nhận diện là password**.
- Biến môi trường được nội suy vào settings cũng có thể trở thành văn bản nhạy cảm ở một vị trí không được che.
- Log của plugin khác, chế độ debug hoặc lỗi kết nối có thể in thông tin bổ sung không nằm trong lớp che password của Help Plugin.

**Kết luận:** “Mặc định che mật khẩu” là cơ chế giảm rủi ro, **không phải bảo đảm output đã được ẩn danh hoặc kiểm toán bảo mật**.

### 7.1. Không bật `showPasswords` khi có dữ liệu thật

Một lựa chọn không nên dùng trong troubleshooting thông thường là:

```text
-DshowPasswords=true
```

Đây là **tên tham số nguy hiểm cần nhận diện**, không phải lời khuyên thực thi. Khi bật, plugin được yêu cầu hiển thị cả giá trị mật khẩu. Điều đó có thể làm lộ thông tin qua terminal, CI logs, file output hoặc bản ghi lệnh.

Ngay cả với tệp chứa password đã mã hóa theo cơ chế Maven, giá trị hiển thị vẫn là dữ liệu nhạy cảm: có thể bị tái sử dụng hoặc giải mã trong môi trường có đủ thành phần. Không chép hay chia sẻ các chuỗi trông giống ciphertext.

Thực hành thông thường là **giữ mặc định `showPasswords=false`** và tập trung vào ID, mirrorOf, activeProfiles, sự tồn tại của cấu hình thay vì hiển thị secret.

### 7.2. “Masked” không có nghĩa “không có bí mật”

Giả sử ai đó đặt token vào một property tên `team.apiToken`:

```xml
<profiles>
    <profile>
        <id>internal</id>
        <properties>
            <team.apiToken>EXAMPLE_NOT_A_REAL_TOKEN</team.apiToken>
        </properties>
    </profile>
</profiles>
```

Đoạn XML này dùng một **chuỗi giả**, không phải secret thật. Nhưng nó minh họa anti-pattern: dù `<server><password>` được che, một giá trị tùy ý trong `<properties>` có thể vẫn được in khi xem effective settings. Điều tương tự xảy ra khi token bị nhúng vào URL, username hoặc tham số plugin khác.

Vì vậy **không đưa secret vào settings properties hoặc URL một cách tùy tiện**, và không tin rằng mọi khóa có tên như `token` hay `secret` đều sẽ được công cụ tự động ẩn.

## 8. Xuất effective settings ra file: thuận tiện nhưng dễ rò rỉ

Help Plugin có tham số `output` để ghi effective settings ra tệp UTF-8 thay vì chỉ in trên console. Ví dụ cú pháp:

```bash
mvn help:effective-settings -Doutput=effective-settings.xml
```

Mẫu trên chỉ nên dùng trong **môi trường thử nghiệm không chứa secret** hoặc khi bạn có biện pháp xử lý tài liệu nhạy cảm. Tệp tạo ra có thể tồn tại lâu hơn phiên terminal và dễ bị commit, đính kèm hoặc upload nhầm.

**Không đặt `effective-settings.xml` có dữ liệu thật vào thư mục Git chung, thư mục artifact CI hoặc nơi đồng bộ cloud mặc định**. Ngay cả khi plugin che password, output có thể vẫn chứa các thông tin nhạy cảm khác.

Nếu buộc phải lưu bản nội bộ phục vụ chẩn đoán:
1. Dùng thư mục hạn chế truy cập, nằm ngoài repository được chia sẻ.
2. Đặt quyền file phù hợp: trên Unix có thể dùng `umask 077` trước khi tạo file; trên Windows dùng quyền ACL phù hợp với tài khoản chạy.
3. Giữ mặc định không hiển thị mật khẩu, không bật debug logging nếu không cần.
4. Đánh dấu file là dữ liệu nhạy cảm; không đưa vào CI artifact hoặc hệ thống issue.
5. Sau khi dùng, xóa theo quy trình bảo mật của môi trường. **Xóa một file không bảo đảm đã xóa bản sao khỏi backup, shell transcript hoặc hệ thống thu thập log**.
6. Khi cần chia sẻ bằng chứng, tạo **bản tóm tắt thủ công** với các trường an toàn và xem lại trước khi gửi.

Lệnh kiểm tra settings trong môi trường có dữ liệu thật tốt nhất thường được chạy **cục bộ và tương tác**, không tự động lưu toàn bộ XML. Nếu đang trong CI, ưu tiên kiểm tra lệnh cấu hình và trạng thái bước thay vì chủ động in settings.

## 9. Không làm lộ bí mật qua CI, log và ảnh chụp

Trong CI/CD, output của một bước `run` có thể được lưu, tìm kiếm, xuất và xem bởi người có quyền truy cập job. Việc in effective settings vào console có thể làm lộ:

- Host, đường dẫn mirror, tên môi trường hoặc cấu trúc repository nội bộ.
- Tên tài khoản dùng cho deploy.
- Token được đưa nhầm vào URL hoặc property tùy chỉnh.
- Đường dẫn tới tệp private key hay thư mục cấu hình của runner.
- Các tham số dòng lệnh vô tình chứa secret.

### 9.1. Tránh đưa secret trực tiếp vào command line

Ví dụ **không nên áp dụng cho dữ liệu thật**:

```text
mvn -DrepoPassword=MY_SECRET deploy
```

Giá trị có thể bị lưu trong lịch sử shell, process command line, log runner hoặc báo cáo chẩn đoán tùy môi trường. Thay vì dán mật khẩu vào lệnh, sử dụng CI secret store hoặc cơ chế cấp thông tin xác thực được nền tảng/hệ thống quản lý.

Trong môi trường dùng settings có tham chiếu biến môi trường, Maven hỗ trợ nội suy một số biến bằng cú pháp `${env.VAR_NAME}`. Tuy nhiên biến môi trường **không tự động vô hình**: nếu plugin hoặc script in biến/giá trị đã nội suy, secret vẫn có thể lộ. Cần cấu hình phạm vi secret, masking và log phù hợp với hệ thống CI cụ thể.

### 9.2. Đừng tự log toàn bộ settings khi job thất bại

Một đoạn CI như sau là **anti-pattern**:

```yaml
- name: Dump Maven settings for debugging
  run: mvn help:effective-settings
```

Vì CI lưu log của bước, đoạn này có nguy cơ công bố thông tin nội bộ. Thay vào đó, hãy kiểm tra ít thông tin nhất để giải quyết lỗi: đúng tệp `-s` hay chưa, mirror ID mong đợi có được khai báo không, profile có được chọn không, bước download trả mã lỗi nào.

**Không nên dùng `grep`, `sed` hoặc regex đơn giản để tự khẳng định bản output đã hoàn toàn sạch secret.** Dữ liệu nhạy cảm có thể nằm trong nhiều vị trí XML, được encode hoặc có định dạng bất ngờ. Chỉ chia sẻ sau khi xem, lược bỏ hoặc thay thế thủ công tất cả trường có khả năng nhạy cảm theo chính sách tổ chức.

### 9.3. Không bật verbose/debug khi chưa kiểm soát nơi ghi log

Tùy chọn `-X` có thể giúp Maven đưa ra thông tin debug trong một số tình huống, nhưng nó có thể mở rộng đáng kể dữ liệu được ghi. Trước khi bật trên CI, cần biết ai đọc được log, dữ liệu nào được mask và log được lưu bao lâu.

Ngay cả khi không chạy `help:effective-settings`, script tự in các biến môi trường hoặc nội dung `settings.xml` cũng có thể làm lộ secret. Việc bảo vệ cần xét **toàn bộ pipeline**, không chỉ riêng goal Help Plugin.

## 10. Ví dụ về thông tin được phép chia sẻ khi báo lỗi

Thay vì đính kèm toàn bộ output effective settings, một báo cáo chẩn đoán an toàn hơn có thể viết:

```text
Maven: 3.x (phiên bản cụ thể đã xác minh bằng mvn -version)
Settings được chọn: user settings từ đường dẫn do CI cấu hình
Mirror: có một mirror áp dụng cho repository central
Server ID: khớp với ID mục tiêu (không hiển thị username/password)
Active profile: repo-internal
Lỗi: HTTP 401 khi truy cập repository nội bộ
Đã ẩn: hostname nội bộ, URL đầy đủ, username, token,
        private key path và toàn bộ phần servers/proxies
```

Đây là **mẫu báo cáo giả định**, không phải dữ liệu lấy từ máy thật. Cách báo cáo này cho phép người hỗ trợ hiểu loại vấn đề và phạm vi mà không cần nhận bản raw XML.

**Nguyên tắc “least disclosure”:** chỉ tiết lộ phần cần thiết để người nhận đưa ra quyết định. Nếu cần hỗ trợ sâu hơn, dùng kênh nội bộ được phép, chia sẻ cho người có quyền và tránh sao chép credential vào lịch sử trao đổi.

## 11. Những hiểu lầm về mã hóa password Maven

Maven có cơ chế hỗ trợ lưu các mật khẩu server dưới dạng mã hóa, nhưng **mức bảo vệ phụ thuộc phiên bản**.

### Maven 3

Maven 3 hỗ trợ `settings-security.xml` và lệnh mã hóa master password/server password. Dù vậy, tài liệu Apache Maven cảnh báo cơ chế mã hóa của Maven 3 mang tính **che giấu/obfuscation**, không phải sự thay thế cho quản lý secret an toàn. Người có đủ dữ liệu có thể giải mã; do đó:

- Bảo vệ quyền truy cập `settings.xml` và `settings-security.xml`.
- Tránh dùng chung tệp secret trên máy nhiều người không có phân quyền phù hợp.
- Không commit tệp security hoặc tệp chứa credential đã mã hóa vào Git công khai.
- Với CI, ưu tiên secret manager/vault và cơ chế cấp quyền được kiểm soát.
- Không đưa password vào đối số dòng lệnh chỉ để mã hóa; các phiên Maven 3 hiện đại hỗ trợ hỏi qua prompt, tránh lưu password trong shell history.

### Maven 4

Maven 4 có cơ chế mã hóa bảo mật được thiết kế lại và công cụ `mvnenc`, với các nguồn master key/secret khác nhau tùy cấu hình. **Không giả định file và lệnh quản lý secret của Maven 3 hoạt động giống hệt Maven 4**; cần xem hướng dẫn phiên bản Maven đang sử dụng.

Trong cả hai trường hợp, **một chuỗi mã hóa vẫn là dữ liệu nhạy cảm**. Không bật `showPasswords=true` chỉ để “kiểm tra có mã hóa hay chưa”, và không đăng công khai nội dung `settings-security.xml`.

## 12. Phân biệt `effective-settings`, `effective-pom` và các lệnh liên quan

Những goal Maven Help Plugin thường bị nhầm:

| Goal | Câu hỏi trả lời | Khi nên dùng |
| --- | --- | --- |
| `help:effective-settings` | Maven đang dùng settings đã tổng hợp nào? | Kiểm tra mirror, proxy, servers, localRepository và settings profiles. |
| `help:effective-pom` | Maven hiểu mô hình dự án cuối cùng thế nào? | Kiểm tra inheritance, dependencies, plugin config, build directories. |
| `help:active-profiles` | Profile nào đang hoạt động với phiên build? | Tìm khác biệt giữa local và CI. |
| `help:evaluate` | Một expression cụ thể đang có giá trị gì? | Xem project.groupId, project.version, properties… khi phù hợp. |

Ví dụ:

```bash
mvn help:effective-settings
mvn help:effective-pom
mvn help:active-profiles
mvn help:evaluate -Dexpression=project.version -q -DforceStdout
```

Những lệnh này có mục đích khác nhau. `effective-settings` **không giải thích toàn bộ dependency graph**; `effective-pom` **không tự tiết lộ tất cả settings hiệu lực**; `active-profiles` **không chứng minh thông tin đăng nhập repository đúng**.

Khi chỉ cần kiểm tra một tọa độ POM cụ thể, `help:evaluate` thường ít thông tin hơn in toàn bộ effective POM. Nhưng tránh dùng biểu thức có thể trả về secret; nguyên tắc **không ghi log dữ liệu nhạy cảm** vẫn áp dụng.

## 13. Quy trình chẩn đoán an toàn cho các lỗi thường gặp

### Tình huống A: Maven dùng sai local repository

Triệu chứng: dependency dường như bị tải lại, cache không giống giữa các máy hoặc dung lượng lưu trữ tăng bất ngờ.

Cách xử lý:

1. Kiểm tra dòng lệnh có `-Dmaven.repo.local=...` không.
2. Xác định user/global settings đã được chọn, bao gồm `-s` và `-gs`.
3. Xem `localRepository` trong effective settings **cục bộ**, không chia sẻ nguyên path nếu chứa thông tin nhạy cảm.
4. Kiểm tra quyền truy cập và dung lượng thư mục cache thực tế.

Đừng nhầm `${user.home}/.m2/repository` với thư mục `target` của dự án; hai vị trí có nhiệm vụ khác nhau.

### Tình huống B: Mirror không được sử dụng

Triệu chứng: Maven vẫn cố tải từ repository gốc dù cấu hình mirror trong user settings.

Cách xử lý:

1. Kiểm tra mirror có xuất hiện trong effective settings không.
2. So `<mirrorOf>` với ID repository Maven đang truy cập.
3. Xác định có global/user settings nào định nghĩa mirror cùng ID khác không.
4. Kiểm tra log resolution có xác nhận mirror được chọn hay không.
5. Nếu mirror yêu cầu authentication, kiểm tra ID server tương ứng, nhưng **không in password**.

**Cảnh báo:** mirror selection phụ thuộc `mirrorOf`, không phải cứ tồn tại `<mirror>` thì mọi repository đều tự chuyển hướng qua nó.

### Tình huống C: `401 Unauthorized` khi tải hoặc deploy

Triệu chứng: URL repository có vẻ đúng nhưng server trả HTTP 401.

Cách xử lý:

1. Xác định ID repository/mirror/deployment target mà Maven thực sự dùng.
2. Kiểm tra `server.id` có trùng ID cần xác thực không.
3. Kiểm tra credential có được cung cấp qua settings/CI đúng phạm vi không, nhưng không hiển thị giá trị.
4. Xác nhận tài khoản còn quyền, token chưa hết hạn bằng quy trình quản trị được phép.
5. Kiểm tra proxy hoặc repository manager có đang đổi endpoint/ID không.

**Không gửi `settings.xml` nguyên bản** lên diễn đàn, issue tracker hay chat; bản đó có thể chứa credential hoặc URL không được công bố.

### Tình huống D: `407 Proxy Authentication Required`

Triệu chứng: yêu cầu qua proxy bị từ chối.

Cách xử lý:

1. Xem proxy nào đang có `active=true`.
2. Đối chiếu `protocol`, `host`, `port`, `nonProxyHosts` với quy tắc mạng.
3. Xác minh proxy credentials qua kênh được phép.
4. Không đăng log hoặc ảnh có hostname nội bộ hay mật khẩu proxy.

Đặc biệt, proxy authentication không giống repository authentication; sửa `<server>` chưa chắc chữa được lỗi `407`.

### Tình huống E: Profile khác giữa máy cá nhân và CI

Triệu chứng: local build dùng repository A, CI dùng repository B, hoặc property được chọn khác.

Cách xử lý:

1. Kiểm tra `activeProfiles` và profile definitions trong effective settings.
2. Chạy `help:active-profiles` với cùng POM và tham số `-P`/`-s` như build.
3. Xem user/global settings của mỗi môi trường có cùng ID profile và giá trị phù hợp không.
4. Kiểm tra JDK, OS, biến hệ thống/môi trường nếu profile có điều kiện kích hoạt.
5. Không đưa credentials vào output để chứng minh profile nào đang bật; chỉ cần ID đã được kiểm duyệt.

### Tình huống F: Help Plugin không chạy được

Triệu chứng: chính `help:effective-settings` không chạy do lỗi plugin resolution hoặc Maven startup.

Cách xử lý:

1. Kiểm tra `mvn -version` để xác nhận Maven/JDK.
2. Kiểm tra Maven có kết nối tới repository mà Help Plugin cần không.
3. Nếu Maven chạy offline hoặc mirror lỗi, goal có thể không tải được plugin lần đầu.
4. Kiểm tra cú pháp `-s`/`-gs` và tệp settings có là XML hợp lệ không.
5. Không cố “chữa” bằng cách gửi nguyên settings chứa secret cho người khác.

Trong một số sự cố khởi động Maven, Help Plugin không thể chạy vì chính vấn đề settings ngăn Maven giải quyết plugin. Khi đó cần đối chiếu **cấu hình tại nguồn trên máy được phép**, không coi thiếu output effective-settings là bằng chứng rằng Maven không có settings.

## 14. Những lỗi phổ biến và cách tránh

**Lỗi 1 — Xem `help:effective-settings` như bản XML đã được ẩn danh hoàn toàn.** Plugin che password theo mặc định, nhưng không chắc che URL nội bộ, username hoặc token ở property tùy chỉnh. **Cách tránh:** kiểm duyệt toàn bộ output trước khi chia sẻ.

**Lỗi 2 — Bật `-DshowPasswords=true` để kiểm tra đăng nhập.** Điều này có thể phơi lộ password. **Cách tránh:** kiểm tra sự tồn tại, ID và quyền truy cập thông qua quy trình bảo mật, không in secret.

**Lỗi 3 — Đính kèm `effective-settings.xml` vào Git issue hoặc pull request.** Tệp có thể chứa nhiều thông tin nội bộ. **Cách tránh:** chỉ gửi bản tóm tắt đã lược bỏ bí mật, sử dụng kênh được phép nếu phải gửi sâu hơn.

**Lỗi 4 — Cho rằng `-s` thêm settings vào tệp user mặc định.** `-s` thực chất chọn một tệp user settings thay thế. **Cách tránh:** xác định chính xác nguồn settings đang được Maven dùng.

**Lỗi 5 — Nhầm `settings.xml` với `pom.xml`.** Cấu hình username/password không nên đặt trong POM phát hành. **Cách tránh:** tách dự án và môi trường.

**Lỗi 6 — Coi mirror ID và repository ID luôn giống nhau.** Khi Maven chọn mirror, ID server dùng để lấy credentials có thể liên quan đến mirror được chọn. **Cách tránh:** kiểm tra cả mirror selection và cấu hình server theo ID thực sự.

**Lỗi 7 — Ghi API token trong `<properties>` của settings rồi tin rằng plugin sẽ che.** Thuộc tính tùy ý không nhất thiết được mask. **Cách tránh:** dùng cơ chế secret đúng loại và tránh in tất cả properties.

**Lỗi 8 — Cho rằng password Maven 3 đã mã hóa là an toàn để commit.** Cơ chế Maven 3 không thay thế secret vault. **Cách tránh:** giữ file bảo mật ngoài nguồn và dùng quyền truy cập phù hợp.

**Lỗi 9 — Bật `-X` trên CI công khai mà không kiểm soát log.** Debug có thể làm lộ nhiều thông tin hơn cần thiết. **Cách tránh:** thu thập tối thiểu, trong kênh kín và có retention phù hợp.

**Lỗi 10 — Chia sẻ ảnh chụp console có nội dung đã che một phần.** Những trường không được che có thể vẫn tiết lộ cấu trúc mạng. **Cách tránh:** tạo một bản tóm tắt an toàn thay cho screenshot.

**Lỗi 11 — Giữ tệp output trong thư mục tự động upload artifact.** Tệp được xuất có thể tồn tại lâu và được tải bởi nhiều người. **Cách tránh:** không xuất effective settings trong CI nếu không bắt buộc; dùng thư mục hạn chế và xóa theo quy trình.

**Lỗi 12 — Tin rằng `help:effective-settings` xác nhận đã đăng nhập thành công.** Nó cho thấy cấu hình, không kiểm tra quyền server hoặc khả năng kết nối. **Cách tránh:** kiểm tra mã thoát và log kết nối của lệnh Maven thực tế, nhưng không in credential.

## 15. Checklist kiểm tra trước khi chia sẻ kết quả

Trước khi gửi thông tin debug Maven cho người khác, tự hỏi:

- [ ] Mình có đang chia sẻ **output hoàn chỉnh** của `help:effective-settings` không? Nếu có, có thể thay bằng bản tóm tắt không?
- [ ] Có bật `showPasswords`, ghi log toàn bộ env hoặc bật debug không?
- [ ] Có token trong URL, property hoặc các trường không được plugin mask không?
- [ ] Có tên tài khoản, hostname, proxy, private key path hoặc đường dẫn nội bộ cần lược bỏ không?
- [ ] Bản ghi có bị lưu vào CI artifact, cloud sync hoặc issue công khai không?
- [ ] Mình đã đối chiếu ID mirror/server/profile mà **không cần lộ secret** chưa?
- [ ] Người nhận có quyền xem thông tin nội bộ này và kênh chia sẻ có phù hợp không?
- [ ] Nếu tệp đã được lưu tạm, mình đã xử lý quyền truy cập và vòng đời lưu giữ chưa?

Nếu chưa chắc, **đừng gửi raw settings**. Chỉ đưa ra những kết luận có thể xác minh: “profile X đang hoạt động”, “mirrorOf áp dụng cho central”, “server ID chưa khớp”, “Maven trả HTTP 401”, sau khi kiểm duyệt tên/URL nội bộ cần thiết.

## 16. Bài tập tự kiểm tra

**Câu 1.** Global settings khai báo mirror A, user settings khai báo mirror khác cùng ID. Tại sao chỉ xem global settings có thể dẫn tới kết luận sai?

**Đáp án:** Maven kết hợp global và user settings, user settings thường ưu tiên ở cấu hình xung đột phù hợp. `help:effective-settings` giúp xem kết quả có hiệu lực thay vì suy đoán từ một nguồn.

**Câu 2.** `help:effective-settings` mặc định có hiển thị toàn bộ password không? Có thể đăng output công khai không?

**Đáp án:** Theo tài liệu Help Plugin, `showPasswords=false` mặc định, nên các password mà plugin nhận diện được che. **Vẫn không thể mặc nhiên công khai** vì username, URL nội bộ, private key path hoặc token ở trường tùy chỉnh có thể xuất hiện.

**Câu 3.** Muốn Maven chạy với tệp user settings `ci-settings.xml` thay thế, dùng tùy chọn nào?

**Đáp án:** `-s ci-settings.xml` hoặc `--settings ci-settings.xml`. Nó chọn tệp user settings đó cho phiên chạy, không tự cộng thêm file vào user settings mặc định.

**Câu 4.** Mirror được khai báo nhưng Maven vẫn tải từ repository gốc. Có phải mật khẩu chắc chắn sai?

**Đáp án:** Chưa thể kết luận. Cần kiểm tra mirror có hiệu lực không, `mirrorOf` có khớp repository không, và Maven thực sự đã chọn mirror nào. Authentication là bước khác.

**Câu 5.** Một người đặt token trong `<profiles><profile><properties>`. Việc mặc định che password có đủ bảo vệ token đó không?

**Đáp án:** Không. Token ở property tùy ý có thể không nằm trong các trường password mà Help Plugin che. Không dùng vị trí này để lưu token rồi công khai output.

**Câu 6.** Khi gặp HTTP 401 từ repository, vì sao có thể cần so `server.id` với ID mục tiêu?

**Đáp án:** Maven liên kết thông tin xác thực với một server ID được sử dụng cho kết nối; nếu ID không khớp, credentials phù hợp có thể không được dùng, dù URL đúng. Không cần in password để kiểm tra ID.

**Câu 7.** `help:effective-settings` khác `help:effective-pom` thế nào?

**Đáp án:** Goal đầu xem cấu hình môi trường đã kết hợp từ settings; goal sau xem mô hình POM dự án sau inheritance, profiles và nội suy liên quan.

**Câu 8.** Có nên tin rằng password đã mã hóa trong `settings.xml` của Maven 3 an toàn để đăng Git không?

**Đáp án:** Không. Maven 3 có cơ chế bảo vệ tương đối yếu so với secret manager; cần giữ quyền truy cập chặt, không commit file chứa secret và không chia sẻ giá trị mã hóa.

**Câu 9.** Sau khi chạy `help:effective-settings` ra file nội bộ, người dùng muốn đăng file đó vào issue. Cách xử lý đúng?

**Đáp án:** Không đăng nguyên file. Tạo bản tóm tắt hoặc trích phần đã được kiểm duyệt thủ công, loại password, token, hostname/path và metadata nội bộ không cần thiết; dùng kênh được phép.

## Tài liệu Apache Maven tham khảo

- [Apache Maven Help Plugin – effective-settings](https://maven.apache.org/plugins/maven-help-plugin/effective-settings-mojo.html): mô tả goal, `output` và `showPasswords` (mặc định `false`).
- [Apache Maven Help Plugin – Usage](https://maven.apache.org/plugins/maven-help-plugin/usage.html): cách dùng `help:effective-settings`, `help:effective-pom`.
- [Apache Maven – Settings Reference](https://maven.apache.org/settings.html): định nghĩa `settings.xml`, global/user settings, servers, mirrors, proxies, profiles và localRepository.
- [Apache Maven – Configuring Maven](https://maven.apache.org/guides/mini/guide-configuring-maven.html): mô hình phân chia cấu hình dự án và cấu hình môi trường.
- [Apache Maven – Password Encryption (Maven 3)](https://maven.apache.org/guides/mini/guide-encryption.html): cơ chế mã hóa và giới hạn bảo mật.
- [Apache Maven – Password Encryption (Maven 4)](https://maven.apache.org/guides/mini/guide-encryption-4.html): công cụ `mvnenc` và mô hình bảo vệ mới.
- [Apache Maven Help Plugin – active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html): xác định profile đang được kích hoạt.
- [Apache Maven Help Plugin – effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html): phân biệt mô hình dự án với settings.
