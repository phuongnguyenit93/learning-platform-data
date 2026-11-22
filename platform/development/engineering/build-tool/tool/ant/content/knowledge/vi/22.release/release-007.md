# Tải hoặc chuyển sản phẩm bằng HTTP, SCP và task ngoài khi phù hợp

Sau khi build hoàn tất, dự án thường cần lấy dependency từ một máy chủ artifact hoặc chuyển sản phẩm đã đóng gói tới máy chủ kiểm thử, máy staging hay hệ thống lưu trữ. Apache Ant có task `<get>` để tải tài nguyên qua URL. Với việc chuyển tệp qua SSH, có thể dùng task SCP tùy chọn của Ant hoặc gọi chương trình `scp` có sẵn trên hệ điều hành bằng task `<exec>`. Những công cụ ngoài như `curl`, `wget` hoặc `rsync` cũng có thể được tích hợp khi giao thức và yêu cầu triển khai phù hợp.

Điều quan trọng là chọn đúng công cụ cho giao thức, quản lý thông tin xác thực an toàn, kiểm tra tệp sau khi truyền và để build báo lỗi khi thao tác không thành công. Tải hoặc chuyển tệp thành công về mặt kết nối chưa đủ để chứng minh artifact nhận được là đúng phiên bản hoặc không bị hỏng.

## 1. Chọn phương thức truyền phù hợp

| Phương thức | Hướng truyền thường gặp | Công cụ Ant hoặc hệ điều hành | Trường hợp phù hợp |
|---|---|---|---|
| HTTP/HTTPS | Tải từ repository hoặc server về máy build | Ant `<get>` | Tải artifact công khai hoặc endpoint HTTP đơn giản |
| HTTP/HTTPS với API hoặc upload | Gửi artifact lên server hoặc làm việc với API | `curl`/`wget` qua Ant `<exec>` | Upload bằng PUT/POST, token, header hoặc API riêng |
| SCP qua SSH | Gửi tệp từ máy build tới máy chủ hoặc lấy tệp về | Ant optional `<scp>` hoặc chương trình `scp` qua `<exec>` | Chuyển artifact qua kết nối SSH được xác thực bằng key |
| Công cụ truyền tệp khác | Tùy giao thức và hệ thống | `rsync`, `sftp`, CLI của artifact repository qua `<exec>` | Đồng bộ thư mục, truyền nhiều tệp hoặc tích hợp với hệ thống cụ thể |

Hãy ưu tiên giao thức được hệ thống đích hỗ trợ và có cơ chế xác thực, kiểm tra tính toàn vẹn phù hợp. Không cần gọi một công cụ ngoài nếu task Ant tích hợp đã đáp ứng được yêu cầu; ngược lại, không nên ép `<get>` xử lý một quy trình upload hoặc API phức tạp mà nó không được thiết kế để thực hiện.

## 2. Tải artifact qua HTTP/HTTPS bằng `<get>`

Task `<get>` tải nội dung từ URL về tệp hoặc thư mục trên máy build. Ví dụ tải một JAR từ repository:

```xml
<project name="http-download-demo" default="download" basedir=".">

    <property name="download.dir" location="build/downloads"/>
    <property name="artifact.url"
              value="https://repo.example.com/releases/com/example/tool/1.2.0/tool-1.2.0.jar"/>
    <property name="artifact.file" location="${download.dir}/tool-1.2.0.jar"/>

    <target name="download">
        <mkdir dir="${download.dir}"/>
        <get src="${artifact.url}"
             dest="${artifact.file}"
             verbose="true"/>
    </target>

</project>
```

Các thuộc tính thường dùng:

- `src`: URL nguồn cần tải, thường là `https://` hoặc `http://`.
- `dest`: tệp đích hoặc thư mục nhận nội dung.
- `verbose`: yêu cầu Ant hiển thị thông tin tải chi tiết hơn.
- `usetimestamp`: nếu được bật và máy chủ cung cấp thông tin sửa đổi phù hợp, Ant có thể tránh tải lại nội dung chưa thay đổi.

Nếu `dest` là tên tệp, buildfile kiểm soát rõ tên artifact được lưu. Nếu `dest` là thư mục, task sử dụng tên tài nguyên dựa trên URL. Với build phát hành, chỉ định tệp đích cụ thể thường giúp các bước checksum, đóng gói và lưu trữ dễ dự đoán hơn.

HTTPS mã hóa kết nối tới máy chủ. Tuy nhiên, chỉ dùng HTTPS không thay thế việc kiểm tra checksum hoặc chữ ký của artifact khi nguồn cung cấp các giá trị xác minh đó.

## 3. Chỉ tải lại khi artifact thay đổi

Nếu server cung cấp header `Last-Modified`, thuộc tính `usetimestamp="true"` cho phép Ant so sánh thời điểm sửa đổi từ xa với tệp cục bộ và tránh tải lại khi bản cục bộ vẫn còn mới:

```xml
<get src="https://downloads.example.com/tool/tool-1.2.0.zip"
     dest="build/downloads/tool-1.2.0.zip"
     usetimestamp="true"
     verbose="true"/>
```

Tính năng này phù hợp để giảm lượng dữ liệu tải khi server hỗ trợ cơ chế timestamp. Nó không phải cơ chế khóa phiên bản và cũng không chứng minh nội dung từ xa không bị thay đổi ngoài ý muốn. Với artifact phát hành cần tái lập, nên dùng URL chứa phiên bản cố định và xác minh checksum.

Nếu URL trỏ tới một tên như `latest.zip`, nội dung có thể thay đổi theo thời gian dù tên không đổi. Khi đó, chỉ dựa vào tên tệp hoặc timestamp có thể không đủ để biết chính xác binary nào đã được sử dụng. Nên lưu version hoặc build identifier trong metadata của dự án.

## 4. Tải về vùng tạm rồi xác minh trước khi sử dụng

Không nên để bước biên dịch hoặc đóng gói sử dụng ngay một tệp đang được tải dở. Một quy trình rõ ràng là tải vào tệp tạm, kiểm tra sự tồn tại và checksum, rồi mới chuyển tệp sang tên chính thức.

Ví dụ dùng Ant `<get>` và `<checksum>`:

```xml
<project name="verified-download" default="download-verified" basedir=".">

    <property name="download.dir" location="build/downloads"/>
    <property name="artifact.url"
              value="https://downloads.example.com/tool/tool-1.2.0.jar"/>
    <property name="temp.file" location="${download.dir}/tool-1.2.0.jar.part"/>
    <property name="final.file" location="${download.dir}/tool-1.2.0.jar"/>
    <property name="expected.sha256" value="replace-with-published-sha256"/>

    <target name="download-verified">
        <mkdir dir="${download.dir}"/>
        <delete file="${temp.file}" quiet="true"/>

        <get src="${artifact.url}"
             dest="${temp.file}"
             verbose="true"/>

        <available file="${temp.file}" property="download.exists"/>
        <fail unless="download.exists"
              message="Downloaded artifact was not created"/>

        <checksum file="${temp.file}"
                  algorithm="SHA-256"
                  property="actual.sha256"/>

        <condition property="checksum.matches">
            <equals arg1="${actual.sha256}" arg2="${expected.sha256}"/>
        </condition>
        <fail unless="checksum.matches"
              message="SHA-256 mismatch for downloaded artifact"/>

        <move file="${temp.file}" tofile="${final.file}" overwrite="true"/>
    </target>

</project>
```

Thay `expected.sha256` bằng checksum được công bố qua kênh tin cậy cho đúng phiên bản artifact. Không tự tạo giá trị kỳ vọng từ chính tệp vừa tải rồi coi đó là xác minh độc lập.

Tệp `.part` giúp phân biệt bản đang tải với bản đã được xác minh. Task `<move>` đặt bản đã kiểm tra vào vị trí chính thức. Nếu tệp tạm và tệp đích cùng filesystem, thao tác di chuyển thường đơn giản hơn; tuy vậy, không nên coi mọi triển khai `move` trên mọi filesystem là bảo đảm atomic tuyệt đối.

## 5. Tải nhiều artifact

Khi cần tải nhiều file từ các URL khác nhau, có thể khai báo nhiều task `<get>` trong một target:

```xml
<target name="download-tools">
    <mkdir dir="build/downloads"/>

    <get src="https://downloads.example.com/tool-a-1.0.jar"
         dest="build/downloads/tool-a-1.0.jar"/>
    <get src="https://downloads.example.com/tool-b-2.3.jar"
         dest="build/downloads/tool-b-2.3.jar"/>
    <get src="https://downloads.example.com/tool-c-4.1.zip"
         dest="build/downloads/tool-c-4.1.zip"/>
</target>
```

Nếu mỗi artifact có checksum riêng, nên xác minh từng file trước khi target tiếp theo sử dụng. Có thể tạo property hoặc target dùng chung để tránh lặp logic xác minh, nhưng mỗi artifact vẫn cần giá trị checksum kỳ vọng riêng.

Đối với số lượng dependency lớn, Ivy hoặc một dependency manager phù hợp thường thuận tiện hơn việc viết một task `<get>` cho từng JAR. `<get>` thích hợp với tải một số artifact trực tiếp hoặc một tài nguyên cố định, còn dependency manager có thể giải quyết metadata và dependency bắc cầu.

## 6. Khi nào dùng công cụ ngoài như `curl`?

Task `<get>` tập trung vào tải tài nguyên từ URL. Một số quy trình cần thêm khả năng như:

- Upload file bằng HTTP PUT hoặc POST.
- Gửi header tùy chỉnh hoặc token xác thực.
- Gọi API của artifact repository.
- Chọn phương thức HTTP, content type hoặc metadata upload.
- Điều khiển retry, timeout và mã phản hồi theo chính sách của hệ thống.

Trong trường hợp đó, có thể gọi `curl` qua Ant `<exec>`. Ví dụ upload một artifact bằng HTTP PUT:

```xml
<target name="upload-artifact">
    <exec executable="curl" failonerror="true">
        <arg value="--fail"/>
        <arg value="--show-error"/>
        <arg value="--silent"/>
        <arg value="--upload-file"/>
        <arg file="dist/inventory-app.jar"/>
        <arg value="https://artifacts.example.com/releases/inventory-app/1.0.0/inventory-app.jar"/>
    </exec>
</target>
```

Ví dụ dùng `--upload-file` gửi nội dung tệp bằng PUT. Endpoint server phải hỗ trợ phương thức này và quyền của tài khoản phải cho phép ghi. `--fail` khiến curl trả mã lỗi cho các phản hồi HTTP lỗi phù hợp, còn `failonerror="true"` yêu cầu Ant đánh dấu target thất bại khi tiến trình curl trả mã thoát khác 0.

Các phần tử `<arg>` truyền đối số riêng cho chương trình. Cách này tránh phải ghép một chuỗi shell dài và giảm rủi ro lỗi do dấu cách hoặc ký tự đặc biệt trong đường dẫn tệp.

## 7. Truyền token hoặc thông tin xác thực HTTP

Không đặt token, mật khẩu hoặc API key trực tiếp trong `build.xml`, URL, log hoặc tham số dòng lệnh được commit vào repository. Những giá trị này có thể bị lưu trong lịch sử Git, log CI hoặc danh sách tiến trình.

Với curl, nên sử dụng secret store hoặc cơ chế xác thực do CI cung cấp. Ví dụ, nếu môi trường đã cấp một tệp cấu hình curl được bảo vệ quyền truy cập, có thể dùng:

```xml
<property environment="env"/>

<exec executable="curl" failonerror="true">
    <arg value="--fail"/>
    <arg value="--show-error"/>
    <arg value="--config"/>
    <arg value="${env.CURL_CONFIG_FILE}"/>
    <arg value="--upload-file"/>
    <arg file="dist/inventory-app.jar"/>
    <arg value="https://artifacts.example.com/releases/inventory-app/1.0.0/inventory-app.jar"/>
</exec>
```

Tệp cấu hình curl cần được tạo và quản lý bên ngoài repository với quyền truy cập phù hợp. Cú pháp `${env.NAME}` phụ thuộc cách Ant truy cập environment properties; nếu môi trường build không tự expose chúng, hãy khai báo property tương ứng theo cách được tổ chức cho phép. Không in nội dung tệp cấu hình hoặc token ra log.

Với HTTP Basic hoặc bearer token, hãy tuân theo cơ chế xác thực mà server yêu cầu và hướng dẫn của công cụ. Ưu tiên token có phạm vi tối thiểu, thời hạn ngắn và được cấp riêng cho CI. Không tắt kiểm tra chứng chỉ TLS để vượt qua lỗi kết nối; hãy sửa trust store hoặc chứng chỉ của môi trường.

## 8. Tải bằng `wget` hoặc công cụ CLI khác

Nếu môi trường đã có `wget`, Ant có thể gọi nó bằng `<exec>`:

```xml
<target name="download-with-wget">
    <mkdir dir="build/downloads"/>
    <exec executable="wget" failonerror="true">
        <arg value="--https-only"/>
        <arg value="--output-document=build/downloads/tool-1.2.0.zip"/>
        <arg value="https://downloads.example.com/tool-1.2.0.zip"/>
    </exec>
</target>
```

Tùy phiên bản `wget` và hệ điều hành, tùy chọn có thể khác nhau. Hãy kiểm tra `wget --help` trên môi trường build và pin phiên bản công cụ nếu build phụ thuộc vào hành vi cụ thể.

Không nên giả định mọi máy chạy Ant đều có `curl`, `wget` hoặc cùng một đường dẫn executable. Nếu dùng công cụ ngoài, hãy ghi rõ yêu cầu cài đặt trong tài liệu môi trường build hoặc kiểm tra sự hiện diện của chương trình trước khi chạy target.

## 9. Chuyển file bằng SCP qua Ant optional task

Ant có task `<scp>` trong bộ task tùy chọn dùng thư viện SSH của JSch. Đây không phải task lõi có sẵn trong mọi cấu hình Ant. Cần có các thư viện Ant/JSch tương thích trên classpath của Ant và dùng đúng phiên bản theo tài liệu của bản Ant đang cài.

Ví dụ cấu hình gửi một JAR lên máy chủ bằng khóa SSH:

```xml
<target name="publish-scp">
    <scp file="dist/inventory-app.jar"
         todir="deploy@staging.example.com:/srv/releases/inventory-app/1.0.0/"
         keyfile="${user.home}/.ssh/id_ed25519"
         knownhosts="${user.home}/.ssh/known_hosts"
         trust="false"
         verbose="true"/>
</target>
```

Các thuộc tính thường gặp của task tùy chọn gồm:

- `file`: tệp cục bộ cần gửi.
- `todir`: thư mục đích trên máy chủ theo dạng `user@host:/path`.
- `keyfile`: đường dẫn tới private key được dùng để xác thực.
- `knownhosts`: tệp chứa host key đã tin cậy.
- `trust`: điều khiển việc có tin cậy host key chưa xác minh hay không; không nên bật chế độ trust mù trong build phát hành.
- `verbose`: hiển thị thông tin truyền chi tiết hơn.

Tên thuộc tính và khả năng hỗ trợ có thể phụ thuộc phiên bản task `scp`/Ant-JSch. Hãy xem tài liệu optional task của đúng phiên bản đang dùng trước khi triển khai. Nếu task không được nhận diện, cần kiểm tra các JAR optional task và thư viện SSH đã có trong classpath của Ant chưa.

Không ghi private key hoặc passphrase trực tiếp vào buildfile. Private key nên được cung cấp bởi agent/secret store của CI hoặc tài khoản build với quyền đọc hạn chế. Host key của máy chủ cần được xác minh qua kênh đáng tin cậy và lưu trong `known_hosts`.

## 10. Dùng chương trình `scp` của hệ điều hành qua `<exec>`

Nếu máy build đã cài OpenSSH client, có thể gọi `scp` trực tiếp. Cách này không yêu cầu Ant optional SSH task:

```xml
<target name="publish-scp-cli">
    <exec executable="scp" failonerror="true">
        <arg value="-i"/>
        <arg file="${user.home}/.ssh/id_ed25519"/>
        <arg value="-o"/>
        <arg value="BatchMode=yes"/>
        <arg value="-o"/>
        <arg value="StrictHostKeyChecking=yes"/>
        <arg value="-o"/>
        <arg value="UserKnownHostsFile=${user.home}/.ssh/known_hosts"/>
        <arg file="dist/inventory-app.jar"/>
        <arg value="deploy@staging.example.com:/srv/releases/inventory-app/1.0.0/inventory-app.jar"/>
    </exec>
</target>
```

Ant truyền từng đối số trực tiếp cho executable. `BatchMode=yes` ngăn SSH hỏi tương tác trong CI; `StrictHostKeyChecking=yes` yêu cầu host key phải được xác minh; `UserKnownHostsFile` chỉ định tệp host key được tin cậy. Tùy phiên bản OpenSSH, có thể cần điều chỉnh cách truyền tùy chọn hoặc đường dẫn.

Trên Windows, executable có thể là `scp.exe`; trên Linux/macOS thường là `scp`. Nếu Ant không tìm thấy chương trình qua `PATH`, hãy cấu hình `executable` bằng đường dẫn đã cài đặt trên máy build.

Không dùng `StrictHostKeyChecking=no` như cách sửa nhanh lỗi host key trong môi trường phát hành. Hãy xác minh fingerprint máy chủ và cập nhật `known_hosts` theo quy trình an toàn.

## 11. Gửi thư mục hoặc nhiều tệp qua SCP

Với chương trình `scp` của OpenSSH, có thể dùng tùy chọn đệ quy `-r` để gửi thư mục:

```xml
<exec executable="scp" failonerror="true">
    <arg value="-r"/>
    <arg value="-i"/>
    <arg file="${user.home}/.ssh/id_ed25519"/>
    <arg file="dist/release-bundle"/>
    <arg value="deploy@staging.example.com:/srv/releases/"/>
</exec>
```

Nếu chỉ cần gửi một số artifact, có thể khai báo từng file trong các lần gọi hoặc dùng một công cụ hỗ trợ danh sách nguồn. Với thư mục lớn hoặc cần đồng bộ chỉ phần thay đổi, `rsync` qua SSH có thể hiệu quả hơn SCP nếu cả hai đầu đều có công cụ này.

Đường dẫn đích nên được tạo hoặc kiểm tra trước trên máy chủ. SCP không tự thiết kế cấu trúc phát hành hay xác nhận ứng dụng có thể chạy; nó chỉ chuyển dữ liệu theo đường dẫn đã chỉ định.

## 12. Dùng `rsync` khi cần đồng bộ

`rsync` phù hợp khi cần đồng bộ thư mục phát hành, chỉ truyền phần thay đổi hoặc giữ cấu trúc thư mục. Ví dụ:

```xml
<target name="sync-release">
    <exec executable="rsync" failonerror="true">
        <arg value="-az"/>
        <arg value="--delete-delay"/>
        <arg value="-e"/>
        <arg value="ssh -i ${user.home}/.ssh/id_ed25519 -o BatchMode=yes -o StrictHostKeyChecking=yes"/>
        <arg file="dist/"/>
        <arg value="deploy@staging.example.com:/srv/releases/inventory-app/"/>
    </exec>
</target>
```

`-a` giữ nhiều thuộc tính tệp và đồng bộ đệ quy; `-z` nén dữ liệu truyền; `--delete-delay` xóa ở đích những tệp không còn ở nguồn sau giai đoạn truyền. Cần hiểu kỹ tác động của `--delete-delay`: dùng sai thư mục nguồn hoặc đích có thể xóa dữ liệu không mong muốn trên máy chủ.

Đối số `-e` ở ví dụ là một chuỗi lệnh SSH do rsync diễn giải. Khác với các đối số đơn của `scp`, phần này có cú pháp riêng của rsync. Nếu đường dẫn private key chứa khoảng trắng hoặc có ký tự đặc biệt, cần kiểm tra cách quoting của phiên bản rsync/SSH đang dùng. Chỉ dùng tùy chọn xóa khi đích là thư mục phát hành được dành riêng cho đồng bộ.

Nếu yêu cầu chỉ là gửi một JAR đơn lẻ, SCP thường đơn giản hơn. Nếu yêu cầu là đồng bộ một cây thư mục lớn qua nhiều lần phát hành, rsync có thể tiết kiệm băng thông.

## 13. Gọi lệnh ngoài an toàn và có thể chẩn đoán

Khi tích hợp `curl`, `scp`, `rsync` hoặc `wget`, nên tuân thủ các nguyên tắc:

- Dùng `<arg>` riêng cho từng đối số thay vì ghép cả lệnh vào một chuỗi shell.
- Bật `failonerror="true"` khi thao tác truyền là điều kiện bắt buộc của target.
- Dùng đường dẫn tuyệt đối hoặc property Ant được xây dựng từ `${basedir}` cho tệp quan trọng.
- Kiểm tra executable có sẵn trong môi trường build.
- Dùng timeout nếu công cụ và task hỗ trợ, tránh tiến trình treo vô thời hạn.
- Ghi log đủ để chẩn đoán nhưng không in token, mật khẩu hoặc nội dung private key.
- Tránh dùng `spawn="true"` cho thao tác phát hành cần chờ kết quả và xác nhận mã thoát.

Ví dụ kiểm tra executable trước khi chạy có thể dùng task `<available>` với đường dẫn chương trình nếu biết vị trí cố định, hoặc để `<exec>` báo lỗi rõ ràng nếu chương trình không có trong `PATH`. Trên môi trường CI, nên cài và pin phiên bản công cụ ngoài trong image build.

## 14. Chuyển artifact theo quy trình staging

Không nên ghi đè trực tiếp bản phát hành đang được sử dụng nếu máy chủ đích có thể phục vụ ứng dụng trong lúc truyền. Một quy trình staging có thể gồm:

1. Tạo thư mục phát hành mới theo version hoặc build ID.
2. Chuyển JAR, dependency và metadata vào thư mục staging.
3. Xác minh kích thước hoặc checksum ở máy đích.
4. Chỉ sau khi xác minh mới cập nhật đường dẫn `current`, symlink hoặc cấu hình triển khai.
5. Giữ bản trước để có thể rollback theo chính sách vận hành.

Ví dụ tên thư mục:

```text
/srv/releases/inventory-app/
├── 1.0.0/
│   ├── inventory-app.jar
│   ├── SHA256SUMS
│   └── lib/
└── 1.0.1/
    ├── inventory-app.jar
    ├── SHA256SUMS
    └── lib/
```

Với SCP, có thể gửi file vào thư mục version mới. Một bước riêng trên máy chủ sẽ xác minh checksum rồi mới đổi liên kết hoặc cấu hình phục vụ. Không nên để bước truyền file đồng thời xóa hoặc thay thế thư mục đang chạy nếu chưa có cơ chế triển khai an toàn.

## 15. Kiểm tra checksum sau khi truyền

Checksum giúp xác nhận tệp nhận được có cùng nội dung với artifact đã tạo. Trước khi upload, tạo checksum tại máy build:

```sh
sha256sum dist/inventory-app.jar
```

Trên Windows PowerShell:

```powershell
Get-FileHash .\dist\inventory-app.jar -Algorithm SHA256
```

Có thể lưu kết quả thành file metadata trong gói phát hành. Sau khi chuyển, tính checksum trên máy đích và so sánh. Nếu checksum khác, không đưa artifact vào sử dụng; hãy kiểm tra quá trình truyền, nguồn file và thao tác ghi ở đích.

Đối với tải HTTP, nên so sánh với checksum do nguồn phát hành tin cậy công bố. Đối với SCP, checksum trước/sau giúp phát hiện lỗi hoặc nhầm tệp, nhưng xác thực SSH vẫn cần thiết để bảo vệ kết nối và máy chủ đích.

## 16. Xử lý lỗi HTTP, SCP và công cụ ngoài

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `<get>` không tải được URL | URL sai, DNS/network lỗi, TLS certificate không tin cậy hoặc server từ chối | Kiểm tra URL, kết nối, chứng chỉ và log Ant |
| HTTP trả 401 hoặc 403 | Thiếu quyền hoặc xác thực không hợp lệ | Kiểm tra credential được cấp, scope token và quyền repository |
| Tải xong nhưng JAR không dùng được | File tải về không đúng artifact, bị cắt hoặc nội dung lỗi | Kiểm tra kích thước, checksum và thử liệt kê nội dung JAR |
| Ant báo không tìm thấy `curl`, `scp` hoặc `rsync` | Công cụ chưa cài hoặc không có trong `PATH` | Cài công cụ trên agent build hoặc cấu hình đường dẫn executable |
| SCP báo host key verification failed | Host key chưa có hoặc khác với giá trị đã lưu | Xác minh fingerprint máy chủ và cập nhật `known_hosts` qua kênh tin cậy |
| SCP báo permission denied | Sai user, key, quyền thư mục hoặc chính sách máy chủ | Kiểm tra tài khoản, key được cấp và quyền ghi đích |
| Task `<scp>` không được nhận diện | Thiếu Ant optional SSH task hoặc JSch dependency | Kiểm tra Ant-JSch/JSch và phiên bản tương thích |
| `curl` trả lỗi nhưng Ant vẫn tiếp tục | Thiếu `--fail` hoặc Ant không được cấu hình fail khi exit code khác 0 | Dùng `--fail` và `failonerror="true"` |
| Upload thành công nhưng server không thấy file | Upload vào endpoint/path khác hoặc server xử lý lưu trữ riêng | Xác nhận API endpoint, đích và phản hồi server |
| Tệp đích bị ghi dở khi build bị ngắt | Ghi trực tiếp vào tên phát hành cuối cùng | Upload vào tên tạm hoặc thư mục version mới, xác minh rồi mới công bố |
| Artifact có checksum khác | Nhầm file, nội dung bị thay đổi hoặc nguồn checksum không đúng | So sánh với checksum lấy từ nguồn tin cậy và tải/truyền lại |

## 17. Checklist trước khi tải hoặc chuyển sản phẩm

- [ ] Đã chọn đúng giao thức: HTTP/HTTPS, SCP, SFTP, rsync hoặc API phù hợp.
- [ ] URL, tên artifact, version và đường dẫn đích được khai báo rõ.
- [ ] Tệp được tải vào vị trí tạm trước khi xác minh nếu cần tránh dùng file dở.
- [ ] Checksum hoặc chữ ký được xác minh theo nguồn tin cậy.
- [ ] Thông tin xác thực được cấp từ secret store hoặc môi trường build, không ghi trong repository.
- [ ] SSH host key được xác minh và lưu trong `known_hosts`.
- [ ] Công cụ ngoài được cài đặt và phiên bản phù hợp trên máy build.
- [ ] Các đối số của `<exec>` được truyền riêng bằng `<arg>`.
- [ ] Lỗi truyền được trả về Ant bằng `failonerror` hoặc cơ chế kiểm tra mã thoát tương ứng.
- [ ] Artifact được chuyển vào thư mục staging/version riêng trước khi công bố.
- [ ] Đã xác minh tệp ở đích trước khi triển khai hoặc cho phép người dùng tải.
- [ ] Log không chứa mật khẩu, token hoặc private key.

## 18. Kết luận

Ant `<get>` phù hợp để tải artifact qua HTTP/HTTPS trong các quy trình đơn giản. Khi cần upload qua HTTP, gọi API hoặc điều khiển header và xác thực, có thể dùng `curl` qua `<exec>`. Với SSH, dùng optional task `<scp>` nếu đã cấu hình đúng thư viện, hoặc gọi OpenSSH `scp` từ môi trường build. `rsync` phù hợp khi cần đồng bộ cây thư mục và chỉ truyền phần thay đổi.

Dù chọn công cụ nào, hãy pin version artifact, giữ thông tin xác thực ngoài buildfile, xác minh host và checksum, chuyển vào vùng staging trước khi công bố, đồng thời để Ant nhận biết mã lỗi của tiến trình. Như vậy, bước tải và chuyển sản phẩm trở thành một phần có thể tái lập và chẩn đoán được của quy trình phát hành.
