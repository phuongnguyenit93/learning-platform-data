# Truyền thông tin xác thực cho tác vụ phát hành qua môi trường

## Mục tiêu

Một quy trình phát hành thường phải đăng nhập vào máy chủ để tải artifact lên, chạy lệnh triển khai từ xa hoặc ký JAR bằng keystore. Các thông tin như tên tài khoản, mật khẩu, token, đường dẫn khóa riêng và passphrase là dữ liệu nhạy cảm. Nếu ghi trực tiếp chúng vào build.xml hoặc tệp properties được commit, bí mật có thể bị lộ qua lịch sử Git, log CI, bản sao lưu hoặc quyền đọc repository.

Apache Ant cho phép nhận giá trị từ môi trường của tiến trình rồi truyền chúng vào thuộc tính của task. Nhờ đó, buildfile có thể giữ cấu hình phát hành trong mã nguồn nhưng nhận thông tin xác thực từ môi trường chạy.

Quy trình nên được tổ chức như sau:

1. Hệ thống CI hoặc người vận hành cung cấp biến môi trường cho tiến trình Ant.
2. Ant nạp các biến môi trường thành property bằng task property.
3. Target kiểm tra những thông tin bắt buộc đã được cung cấp.
4. Task phát hành nhận giá trị qua các thuộc tính username, password, keyfile, passphrase, storepass hoặc token tương ứng.
5. Build thực hiện ký và chuyển artifact, đồng thời không in giá trị bí mật ra log.
6. Hệ thống CI thu hồi hoặc hết hạn thông tin xác thực sau công việc phát hành.

Điểm cần nhớ là biến môi trường giúp tách bí mật khỏi buildfile, nhưng bản thân biến môi trường không phải kho lưu trữ bí mật. Hãy kết hợp chúng với secret store của CI, quyền truy cập tối thiểu và thời hạn sử dụng ngắn.

## 1. Phân biệt cấu hình phát hành và thông tin xác thực

Không phải mọi giá trị trong buildfile đều là bí mật. Hãy tách cấu hình thông thường khỏi thông tin xác thực.

| Loại dữ liệu | Ví dụ | Nơi phù hợp |
|---|---|---|
| Cấu hình không nhạy cảm | Tên môi trường, phiên bản phát hành, tên artifact, thư mục đích | build.xml hoặc release.properties |
| Thông tin định tuyến | Tên máy chủ, cổng SSH, URL repository | build.xml hoặc cấu hình môi trường |
| Tên tài khoản | Tài khoản upload, alias ký | Biến môi trường hoặc cấu hình được quản lý |
| Mật khẩu và token | SSH password, FTP password, API token | Secret store của CI, sau đó inject vào môi trường |
| Khóa riêng | SSH private key, keystore | Secret file hoặc secret manager, với quyền truy cập hạn chế |
| Passphrase | Mật khẩu bảo vệ khóa riêng hoặc keystore | Secret store, inject khi job chạy |

Ví dụ, file release.properties có thể chứa các giá trị không nhạy cảm:

~~~properties
release.name=sample-app
release.version=2.4.0
release.host=release.example.org
release.directory=/srv/releases/sample-app
~~~

Không đưa RELEASE_PASSWORD, DEPLOY_TOKEN, SIGNING_STOREPASS hoặc private key vào file này nếu file nằm trong repository. Các giá trị nhạy cảm nên được cung cấp riêng bởi môi trường CI hoặc cơ chế quản lý bí mật của hệ thống.

## 2. Nạp biến môi trường thành Ant property

### 2.1. Cú pháp property environment

Task property có thuộc tính environment. Giá trị của thuộc tính này là tiền tố Ant dùng để đặt tên property được tạo từ các biến môi trường:

~~~xml
<property environment="env"/>
~~~

Sau khi thực hiện, Ant có thể tham chiếu biến môi trường RELEASE_USER bằng property:

~~~text
${env.RELEASE_USER}
~~~

Tương tự:

| Biến môi trường | Ant property |
|---|---|
| RELEASE_USER | env.RELEASE_USER |
| RELEASE_PASSWORD | env.RELEASE_PASSWORD |
| DEPLOY_HOST | env.DEPLOY_HOST |
| DEPLOY_TOKEN | env.DEPLOY_TOKEN |
| SIGNING_STOREPASS | env.SIGNING_STOREPASS |
| SSH_KNOWN_HOSTS | env.SSH_KNOWN_HOSTS |

Tiền tố env là quy ước do buildfile chọn. Có thể dùng tên khác, chẳng hạn secrets hoặc releaseEnv, nhưng nên chọn một tên thống nhất trong toàn bộ dự án.

### 2.2. Sử dụng property trong task

Sau khi nạp môi trường, giá trị có thể được truyền trực tiếp vào thuộc tính task:

~~~xml
<property environment="env"/>

<sshexec host="${env.DEPLOY_HOST}"
         username="${env.DEPLOY_USER}"
         password="${env.DEPLOY_PASSWORD}"
         command="mkdir -p /srv/releases"
         trust="false"
         knownhosts="${env.SSH_KNOWN_HOSTS}"/>
~~~

Buildfile không chứa mật khẩu thật. Khi Ant chạy, các biểu thức property được thay bằng giá trị trong môi trường tiến trình.

Không viết task echo để in giá trị của env.DEPLOY_PASSWORD hoặc env.DEPLOY_TOKEN. Nếu cần chẩn đoán, chỉ in trạng thái có/không hoặc tên biến đang thiếu.

### 2.3. Ant nạp toàn bộ biến môi trường

Task property với environment="env" tạo property cho mọi biến môi trường mà Ant có thể đọc được, không chỉ các biến RELEASE_* đã chọn. Vì vậy:

- Không dùng echoproperties để in toàn bộ property trong job phát hành.
- Không bật debug hoặc verbose nếu chưa hiểu dữ liệu task có thể ghi ra log.
- Không in trực tiếp các property có tiền tố env.
- Chỉ tham chiếu đúng những biến cần thiết trong target phát hành.

Nếu chỉ cần truyền một biến cho chương trình bên ngoài thông qua task exec, có thể dùng phần tử env lồng trong exec để truyền biến đó cho tiến trình con. Cách này không yêu cầu tạo property toàn cục cho mọi biến môi trường.

### 2.4. Phân biệt tên biến môi trường và tên Ant property

Tên property của Ant phân biệt chữ hoa và chữ thường. Trên một số hệ điều hành, tên biến môi trường không phân biệt chữ hoa và chữ thường, nhưng Ant vẫn có thể tạo property với cách viết đúng như tên được hệ thống trả về.

Ví dụ, trên Windows, biến hệ thống Path có thể xuất hiện dưới tên env.Path thay vì env.PATH. Với biến do dự án tự đặt, hãy dùng tên chữ hoa nhất quán như RELEASE_USER và tham chiếu đúng env.RELEASE_USER.

Khả năng đọc biến môi trường cũng phụ thuộc nền tảng và phiên bản Java/Ant. Nếu build phải chạy trên nhiều hệ điều hành, hãy kiểm tra cơ chế môi trường trong các runner thực tế.

## 3. Cung cấp biến môi trường cho tiến trình Ant

### 3.1. Trong CI

Cách phù hợp nhất cho pipeline là tạo secret trong hệ thống CI rồi ánh xạ secret đó thành biến môi trường chỉ trong job phát hành.

Ví dụ về ánh xạ khái niệm:

| Secret trong CI | Biến môi trường đưa vào Ant |
|---|---|
| Secret chứa tài khoản deploy | RELEASE_USER |
| Secret chứa mật khẩu deploy | RELEASE_PASSWORD |
| Secret chứa token repository | REPOSITORY_TOKEN |
| Secret chứa passphrase khóa ký | SIGNING_KEYPASS |
| Secret file chứa SSH private key | DEPLOY_KEY_FILE |

Tên và cú pháp khai báo secret khác nhau giữa các nền tảng CI. Dù dùng nền tảng nào, hãy bảo đảm:

- Secret chỉ được cấp cho job hoặc environment cần phát hành.
- Pull request từ nhánh không tin cậy không được nhận secret phát hành.
- Log được cấu hình che giá trị secret, nhưng không dựa hoàn toàn vào chức năng masking.
- Tài khoản deploy chỉ có quyền ghi vào thư mục hoặc repository cần thiết.
- Token có thời hạn ngắn và có thể thu hồi.
- Job phát hành được bảo vệ bằng điều kiện branch, approval hoặc environment protection phù hợp.

### 3.2. Chạy Ant từ shell

Nếu môi trường đã có các biến RELEASE_USER và RELEASE_PASSWORD, Ant có thể đọc chúng trực tiếp:

~~~text
ant publish
~~~

Có thể đặt biến trong phạm vi một tiến trình trên Unix-like shell:

~~~text
RELEASE_USER="$CI_RELEASE_USER" RELEASE_PASSWORD="$CI_RELEASE_PASSWORD" ant publish
~~~

Lệnh trên lấy giá trị từ các biến đã được môi trường CI cấp. Lịch sử shell chỉ chứa tên biến tham chiếu, không chứa giá trị bí mật nếu người vận hành không thay chúng bằng chuỗi thật.

Trong PowerShell, có thể ánh xạ biến CI đã được inject vào biến dùng cho Ant:

~~~powershell
$env:RELEASE_USER = $env:CI_RELEASE_USER
$env:RELEASE_PASSWORD = $env:CI_RELEASE_PASSWORD
ant publish
~~~

Không gõ mật khẩu thật trực tiếp vào lệnh được lưu trong shell history hoặc tài liệu. Với máy cá nhân, nên dùng secret manager hoặc cơ chế cấp biến tạm thời của hệ điều hành thay vì lưu lâu dài trong profile.

### 3.3. Truyền qua -D có phù hợp không?

Ant hỗ trợ truyền property bằng tham số -D:

~~~text
ant -Drelease.environment=staging publish
~~~

Cách này phù hợp với giá trị không nhạy cảm như tên môi trường, phiên bản hoặc tùy chọn build. Không nên truyền password hoặc token bằng tham số như:

~~~text
ant -Dpassword=secret-value publish
~~~

Đối số dòng lệnh có thể xuất hiện trong danh sách tiến trình, log runner hoặc thông tin chẩn đoán. Tài liệu task SSH của Ant cũng cảnh báo mật khẩu trên command line có thể bị người dùng khác trên hệ thống Unix nhìn thấy qua công cụ như ps.

Hãy dùng -D cho giá trị điều khiển không nhạy cảm và dùng biến môi trường được cấp từ secret store cho thông tin xác thực.

## 4. Kiểm tra biến bắt buộc trước khi phát hành

Không nên để task phát hành bắt đầu rồi mới phát hiện thiếu username, password hoặc token. Hãy tạo target kiểm tra trước.

### 4.1. Kiểm tra property tồn tại và không rỗng

Ví dụ target validate:

~~~xml
<project name="release-project" default="publish" basedir=".">
    <property environment="env"/>

    <condition property="release.credentials.ready">
        <and>
            <isset property="env.RELEASE_USER"/>
            <isset property="env.RELEASE_PASSWORD"/>
            <not>
                <equals arg1="${env.RELEASE_USER}" arg2=""/>
            </not>
            <not>
                <equals arg1="${env.RELEASE_PASSWORD}" arg2=""/>
            </not>
        </and>
    </condition>

    <target name="validate-release-env">
        <fail unless="release.credentials.ready"
              message="Missing RELEASE_USER or RELEASE_PASSWORD environment variables."/>
    </target>
</project>
~~~

Condition chỉ tạo property release.credentials.ready khi cả hai giá trị đều tồn tại và không rỗng. Task fail kiểm tra sự tồn tại của property cờ, không in nội dung mật khẩu.

Nếu biến môi trường chưa được định nghĩa, biểu thức property tương ứng có thể chưa được thay thế. Điều kiện isset giúp phát hiện trường hợp đó. Điều kiện equals giúp phát hiện biến có tồn tại nhưng giá trị rỗng.

### 4.2. Kiểm tra nhiều nhóm thông tin

Một job có thể cần host, user, password và thư mục đích:

~~~xml
<condition property="upload.settings.ready">
    <and>
        <isset property="env.RELEASE_HOST"/>
        <isset property="env.RELEASE_USER"/>
        <isset property="env.RELEASE_PASSWORD"/>
        <isset property="env.RELEASE_DIRECTORY"/>
        <not>
            <equals arg1="${env.RELEASE_HOST}" arg2=""/>
        </not>
        <not>
            <equals arg1="${env.RELEASE_USER}" arg2=""/>
        </not>
        <not>
            <equals arg1="${env.RELEASE_PASSWORD}" arg2=""/>
        </not>
        <not>
            <equals arg1="${env.RELEASE_DIRECTORY}" arg2=""/>
        </not>
    </and>
</condition>

<target name="validate-upload">
    <fail unless="upload.settings.ready"
          message="Release connection settings are incomplete."/>
</target>
~~~

Thông báo lỗi nên nêu tên biến hoặc nhóm cấu hình bị thiếu, nhưng không nối giá trị thực tế vào message.

### 4.3. Tách validate khỏi publish

Một target phát hành nên phụ thuộc vào target kiểm tra:

~~~xml
<target name="publish" depends="validate-release-env">
    <!-- Các task ký và upload artifact -->
</target>
~~~

Nếu validation thất bại, Ant dừng trước khi thực hiện tác vụ phát hành. Có thể tạo các target validate riêng cho SSH, signing hoặc repository để chỉ kiểm tra đúng nhóm thông tin cần thiết.

## 5. Truyền thông tin xác thực cho SSH và SCP

### 5.1. Dùng SSH key thay cho password

Đối với máy chủ hỗ trợ SSH, xác thực bằng key thường thuận tiện hơn việc dùng mật khẩu tài khoản. Ant có task scp để chuyển tệp và sshexec để chạy lệnh trên máy chủ từ xa.

Ví dụ biến môi trường cần có:

~~~text
DEPLOY_HOST
DEPLOY_USER
DEPLOY_KEY_FILE
DEPLOY_KEY_PASSPHRASE
SSH_KNOWN_HOSTS
~~~

DEPLOY_KEY_FILE là đường dẫn đến tệp private key đã được CI tạo hoặc mount vào runner. DEPLOY_KEY_PASSPHRASE là passphrase bảo vệ private key; nếu key không có passphrase, có thể cấp một biến rỗng theo quy ước của job.

### 5.2. Upload artifact bằng scp

~~~xml
<property environment="env"/>

<target name="upload" depends="validate-release">
    <scp localFile="dist/sample-app.zip"
         remoteTodir="${env.DEPLOY_USER}@${env.DEPLOY_HOST}:/srv/releases/sample-app"
         keyfile="${env.DEPLOY_KEY_FILE}"
         passphrase="${env.DEPLOY_KEY_PASSPHRASE}"
         knownhosts="${env.SSH_KNOWN_HOSTS}"
         trust="false"
         sftp="true"
         failonerror="true"/>
</target>
~~~

Các thuộc tính có ý nghĩa:

- localFile chỉ rõ tệp cục bộ cần gửi.
- remoteTodir chỉ rõ tài khoản, máy chủ và thư mục đích từ xa.
- keyfile trỏ đến private key.
- passphrase cung cấp mật khẩu bảo vệ key nếu có.
- knownhosts xác minh danh tính máy chủ SSH.
- trust="false" yêu cầu máy chủ đã có trong known_hosts.
- sftp="true" dùng giao thức SFTP trên SSH2 thay vì SCP1.

Task scp cần thư viện SSH bổ sung theo tài liệu Ant; các thư viện này không được đóng gói đầy đủ trong bản Ant chuẩn. Hãy cài đúng dependency và phiên bản tương thích.

Không đặt trust="true" trong pipeline phát hành chỉ để bỏ qua lỗi host key. Cách đó chấp nhận máy chủ chưa xác minh và làm suy yếu khả năng phát hiện kết nối đến nhầm máy chủ.

### 5.3. Chạy lệnh từ xa bằng sshexec

Nếu cần chạy lệnh triển khai sau khi upload:

~~~xml
<sshexec host="${env.DEPLOY_HOST}"
         username="${env.DEPLOY_USER}"
         keyfile="${env.DEPLOY_KEY_FILE}"
         passphrase="${env.DEPLOY_KEY_PASSPHRASE}"
         knownhosts="${env.SSH_KNOWN_HOSTS}"
         trust="false"
         command="sh /srv/releases/sample-app/deploy.sh"
         failonerror="true"
         timeout="120000"/>
~~~

Task sshexec chạy lệnh trên máy chủ SSH. Timeout được tính bằng mili giây. failonerror mặc định là true, nhưng khai báo rõ giúp người đọc hiểu rằng deploy thất bại sẽ làm build thất bại.

Nếu lệnh từ xa nhận tham số do người dùng hoặc môi trường cung cấp, cần xử lý quoting và kiểm tra dữ liệu đầu vào. Không ghép trực tiếp chuỗi không tin cậy vào command vì nó có thể bị diễn giải thành cú pháp shell.

### 5.4. Khi buộc phải dùng password SSH

Task scp và sshexec có thuộc tính password. Có thể lấy giá trị từ môi trường:

~~~xml
<sshexec host="${env.DEPLOY_HOST}"
         username="${env.DEPLOY_USER}"
         password="${env.DEPLOY_PASSWORD}"
         knownhosts="${env.SSH_KNOWN_HOSTS}"
         trust="false"
         command="sh /srv/releases/deploy.sh"
         failonerror="true"/>
~~~

Không ghi mật khẩu trong URL remote, thuộc tính password cố định hoặc file được commit. Nếu máy chủ hỗ trợ key authentication, ưu tiên key với quyền hạn và thời hạn phù hợp.

Task SSH phụ thuộc thư viện bên ngoài và cấu hình host key. Kiểm tra known_hosts trước khi chạy, không tắt xác minh máy chủ để làm pipeline qua lỗi.

## 6. Truyền thông tin xác thực cho task signjar

### 6.1. Các giá trị cần thiết khi ký JAR

Task signjar gọi công cụ jarsigner để ký JAR. Các thông tin thường cần gồm:

- Đường dẫn keystore.
- Alias của chứng thư hoặc khóa cần ký.
- storepass để mở hoặc kiểm tra tính toàn vẹn keystore.
- keypass nếu khóa riêng có mật khẩu khác với storepass.

Không commit keystore phát hành và mật khẩu của nó vào repository. CI có thể mount keystore dưới dạng secret file và cấp mật khẩu qua biến môi trường.

### 6.2. Ví dụ dùng environment properties

~~~xml
<property environment="env"/>

<target name="sign">
    <signjar jar="dist/sample-app.jar"
             signedjar="dist/signed/sample-app.jar"
             keystore="${env.SIGNING_KEYSTORE}"
             alias="${env.SIGNING_ALIAS}"
             storepass="${env.SIGNING_STOREPASS}"
             keypass="${env.SIGNING_KEYPASS}"
             sigalg="SHA256withRSA"
             digestalg="SHA-256"
             strict="true"/>
</target>
~~~

Trong ví dụ:

- SIGNING_KEYSTORE là đường dẫn đến keystore đã được cung cấp cho job.
- SIGNING_ALIAS xác định khóa dùng để ký.
- SIGNING_STOREPASS và SIGNING_KEYPASS là bí mật do CI inject.
- signedjar tạo bản đã ký riêng, giúp giữ artifact chưa ký để so sánh hoặc lưu trữ nếu cần.

Nếu keypass giống storepass, có thể bỏ thuộc tính keypass theo yêu cầu của keystore. Nếu task được dùng với HSM hoặc provider đặc biệt, cấu hình có thể cần thêm provider hoặc cơ chế xác thực tương ứng.

Tài liệu Ant nêu rằng signjar không truyền storepass bằng tùy chọn -storepass trên command line; task gửi mật khẩu cho jarsigner khi được hỏi. Dù vậy, vẫn phải bảo vệ property và log vì giá trị có thể bị lộ qua cách chẩn đoán hoặc cấu hình build khác.

### 6.3. Kiểm tra kết quả ký

Sau khi ký, có thể dùng jarsigner để xác minh chữ ký:

~~~text
jarsigner -verify -verbose -certs dist/signed/sample-app.jar
~~~

Có thể đưa bước xác minh vào target exec hoặc công cụ phù hợp. Không in storepass/keypass trong lệnh kiểm tra. Khi phát hành chính thức, cần kiểm tra chứng thư, chuỗi tin cậy, timestamp và chính sách chữ ký theo yêu cầu của nền tảng phân phối.

## 7. Truyền thông tin xác thực cho FTP/FTPS

### 7.1. Thuộc tính userid và password

Task ftp của Ant nhận userid và password:

~~~xml
<property environment="env"/>

<ftp server="${env.RELEASE_FTP_HOST}"
     userid="${env.RELEASE_FTP_USER}"
     password="${env.RELEASE_FTP_PASSWORD}"
     remotedir="${env.RELEASE_FTP_DIRECTORY}"
     action="put"
     passive="true"
     binary="true"
     failonerror="true">
    <fileset dir="dist">
        <include name="sample-app.zip"/>
    </fileset>
</ftp>
~~~

Ví dụ này minh họa cách truyền thông tin đăng nhập từ môi trường vào task. Task ftp cần thư viện bổ sung, thường là Apache Commons Net, theo hướng dẫn dependency của Ant.

### 7.2. Không dùng FTP thuần cho thông tin xác thực nhạy cảm

FTP thông thường không mã hóa username, password và nội dung truyền tải. Không dùng FTP thuần qua mạng không tin cậy để phát hành artifact nhạy cảm.

Nếu phải dùng FTP, xem xét FTPS khi phiên bản Ant và máy chủ hỗ trợ. Ant bổ sung thuộc tính useFtps từ phiên bản 1.10.13 và useSecureDataChannel từ 1.10.15:

~~~xml
<ftp server="${env.RELEASE_FTP_HOST}"
     userid="${env.RELEASE_FTP_USER}"
     password="${env.RELEASE_FTP_PASSWORD}"
     remotedir="${env.RELEASE_FTP_DIRECTORY}"
     action="put"
     useFtps="true"
     useSecureDataChannel="true"
     passive="true"
     binary="true"
     failonerror="true">
    <fileset dir="dist">
        <include name="sample-app.zip"/>
    </fileset>
</ftp>
~~~

Hãy xác nhận phiên bản Ant và cấu hình TLS của máy chủ. FTPS là FTP được bảo vệ bằng TLS; nó khác với SFTP, vốn chạy trên SSH. Nếu hệ thống cung cấp SSH/SFTP, task scp với sftp="true" thường là lựa chọn rõ ràng hơn.

## 8. Truyền token cho chương trình triển khai bên ngoài

Nhiều nhóm phát hành bằng CLI riêng của nền tảng hoặc nhà cung cấp. Nếu công cụ nhận token từ biến môi trường, task exec có nested env:

~~~xml
<property environment="env"/>

<target name="publish-cli">
    <exec executable="release-cli" failonerror="true">
        <arg value="publish"/>
        <arg value="dist/sample-app.zip"/>
        <env key="RELEASE_TOKEN" value="${env.RELEASE_TOKEN}"/>
    </exec>
</target>
~~~

Nested env đặt biến RELEASE_TOKEN cho tiến trình con. Cách này hữu ích khi CLI yêu cầu biến môi trường thay vì đối số command line.

Nếu không cần Ant đọc token như một property, có thể để CI inject trực tiếp biến môi trường vào tiến trình Ant và truyền tiếp cho CLI. Tránh dùng đối số như --token actual-secret vì command line có thể được ghi lại.

Mặc định exec kế thừa môi trường của tiến trình Ant. Nếu đặt newenvironment="true", tiến trình con không nhận các biến môi trường cũ; khi đó cần truyền lại mọi biến bắt buộc như PATH, JAVA_HOME hoặc các biến cấu hình khác. Không bật newenvironment chỉ để cố che một biến bí mật.

Luôn đặt failonerror="true" hoặc kiểm tra mã trả về nếu lỗi của CLI phải làm pipeline thất bại.

## 9. Tổ chức target phát hành hoàn chỉnh

Một buildfile có thể tách validation, signing và upload:

~~~xml
<project name="release-build" default="publish" basedir=".">
    <property environment="env"/>

    <property name="release.file" location="dist/sample-app.zip"/>
    <property name="release.remote.dir" value="/srv/releases/sample-app"/>

    <condition property="ssh.credentials.ready">
        <and>
            <isset property="env.DEPLOY_HOST"/>
            <isset property="env.DEPLOY_USER"/>
            <isset property="env.DEPLOY_KEY_FILE"/>
            <isset property="env.DEPLOY_KEY_PASSPHRASE"/>
            <isset property="env.SSH_KNOWN_HOSTS"/>
            <not>
                <equals arg1="${env.DEPLOY_HOST}" arg2=""/>
            </not>
            <not>
                <equals arg1="${env.DEPLOY_USER}" arg2=""/>
            </not>
            <not>
                <equals arg1="${env.DEPLOY_KEY_FILE}" arg2=""/>
            </not>
            <not>
                <equals arg1="${env.SSH_KNOWN_HOSTS}" arg2=""/>
            </not>
        </and>
    </condition>

    <target name="validate-release">
        <fail unless="ssh.credentials.ready"
              message="SSH release environment is incomplete."/>
        <available file="${release.file}" property="release.file.exists"/>
        <fail unless="release.file.exists"
              message="Release artifact does not exist."/>
    </target>

    <target name="upload" depends="validate-release">
        <scp localFile="${release.file}"
             remoteTodir="${env.DEPLOY_USER}@${env.DEPLOY_HOST}:${release.remote.dir}"
             keyfile="${env.DEPLOY_KEY_FILE}"
             passphrase="${env.DEPLOY_KEY_PASSPHRASE}"
             knownhosts="${env.SSH_KNOWN_HOSTS}"
             trust="false"
             sftp="true"
             failonerror="true"/>
    </target>

    <target name="publish" depends="upload">
        <echo message="Release upload completed."/>
    </target>
</project>
~~~

Ví dụ này tập trung vào SSH key authentication. Job cần cung cấp các biến:

~~~text
DEPLOY_HOST
DEPLOY_USER
DEPLOY_KEY_FILE
DEPLOY_KEY_PASSPHRASE
SSH_KNOWN_HOSTS
~~~

DEPLOY_KEY_PASSPHRASE có thể là chuỗi rỗng nếu private key không được bảo vệ bằng passphrase; hãy bảo đảm biến vẫn được cung cấp nếu buildfile tham chiếu nó.

Target validate-release kiểm tra thông tin xác thực và sự tồn tại của artifact trước khi upload. Target publish chỉ ghi một thông báo không nhạy cảm sau khi upload thành công.

Trong dự án thực tế, có thể tách signing thành target riêng và đặt nó trước upload. Nếu chữ ký là điều kiện bắt buộc, không cho phép target upload chạy khi signing thất bại.

## 10. Quản lý biến môi trường và tính bất biến của Ant property

Ant property không phải biến có thể thay đổi tùy ý. Khi một property được thiết lập lần đầu, giá trị đó được giữ trong phần còn lại của build.

Điều này có một số hệ quả:

- Task property environment="env" nạp snapshot các biến môi trường tại thời điểm task chạy.
- Nếu property env.RELEASE_USER đã được thiết lập trước đó, việc nạp môi trường sau có thể không ghi đè nó.
- Nạp hai tệp properties có cùng key trong một project không tạo ra cơ chế thay đổi giá trị theo target.
- Không thể đổi giá trị property giữa hai target rồi mong task sau tự nhận giá trị mới.

Hãy nạp môi trường sớm, trước khi dùng các property này. Nếu mỗi môi trường phát hành cần bộ credential khác nhau, nên chạy Ant thành tiến trình riêng cho từng môi trường hoặc dùng build invocation riêng. Không cố nạp nhiều credential có cùng tên tuần tự trong một project.

Property được truyền bằng -D từ dòng lệnh có ưu tiên cao hơn property được khai báo trong buildfile hoặc tệp properties. Điều này hữu ích với cấu hình thông thường, nhưng không phải lý do để truyền bí mật bằng -D.

## 11. Bảo vệ secret trong log, repository và artifact

### 11.1. Không in giá trị bí mật

Tránh các lệnh:

~~~xml
<echo message="Password: ${env.RELEASE_PASSWORD}"/>
<echo message="Token: ${env.RELEASE_TOKEN}"/>
<echoproperties/>
~~~

Không dùng debug/verbose trong job phát hành nếu chưa kiểm tra task có thể ghi dữ liệu nào. Một số task hoặc công cụ bên ngoài có thể hiển thị command, URL, header hoặc tham số khi chạy verbose.

Thay vào đó, in thông báo không chứa giá trị:

~~~xml
<echo message="Release credentials have been supplied."/>
~~~

Nếu cần kiểm tra một biến có được cung cấp không, dùng isset hoặc condition rồi chỉ in trạng thái.

### 11.2. Không commit bí mật

Không đưa password, token, private key, keystore phát hành hoặc passphrase vào:

- build.xml.
- release.properties được commit.
- Tệp manifest hoặc JAR.
- Script shell/batch nằm trong repository.
- File report, log hoặc thông báo lỗi.
- URL remote có chứa user:password.

Nếu lỡ commit secret, xóa dòng khỏi file không đủ để thu hồi rủi ro vì secret vẫn có thể nằm trong Git history. Hãy thu hồi hoặc xoay vòng credential trước, sau đó xử lý lịch sử repository theo quy trình của tổ chức.

### 11.3. Không coi environment là vault

Biến môi trường giúp tách bí mật khỏi mã nguồn, nhưng tiến trình Ant và tiến trình con có thể truy cập môi trường được cấp. Người có quyền đủ cao trên runner cũng có thể quan sát hoặc thu thập dữ liệu của tiến trình.

Vì vậy:

- Chỉ cấp secret cho job phát hành cần dùng.
- Không chạy mã không tin cậy trong cùng job có secret.
- Dùng runner riêng hoặc môi trường cô lập khi cần.
- Giới hạn quyền đọc file private key và keystore.
- Xóa file secret tạm sau job nếu runner không tự hủy.
- Ưu tiên token ngắn hạn, phạm vi quyền nhỏ và có thể thu hồi.
- Không để secret xuất hiện trong artifact hoặc cache của CI.

### 11.4. Masking của CI không phải lớp bảo vệ duy nhất

Nền tảng CI thường có chức năng che secret trong log. Tuy nhiên, masking có thể không nhận diện được giá trị đã mã hóa, cắt nhỏ, biến đổi hoặc nối với chuỗi khác.

Không cố tình in secret với hy vọng CI sẽ che nó. Hãy thiết kế buildfile để không ghi giá trị bí mật ra output ngay từ đầu.

## 12. Lựa chọn cơ chế xác thực theo tác vụ

| Tác vụ phát hành | Cách nhận thông tin xác thực | Gợi ý |
|---|---|---|
| SCP/SFTP | keyfile, passphrase hoặc password | Ưu tiên SSH key; kiểm tra known_hosts |
| Chạy lệnh SSH | username, keyfile/passphrase hoặc password | Giữ trust=false và failonerror=true |
| Ký JAR | keystore, alias, storepass, keypass | Keystore từ secret file; mật khẩu từ secret env |
| FTP/FTPS | userid, password | Tránh FTP thuần; dùng FTPS hoặc SFTP |
| CLI bên ngoài | Nested env hoặc môi trường tiến trình | Truyền token qua env, không qua command arguments |
| Repository publish | Token/API credential theo task hoặc CLI | Dùng token ngắn hạn và quyền publish tối thiểu |

Task không tự động biến mọi loại thông tin xác thực thành bí mật. Việc bảo vệ nguồn cấp, phạm vi quyền, log và file đầu ra vẫn thuộc quy trình phát hành.

## 13. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Property env.RELEASE_USER không tồn tại | Biến môi trường chưa được cấp hoặc sai tên | Kiểm tra cấu hình CI và cách viết tên biến |
| Property có giá trị rỗng | Secret được cấu hình nhưng giá trị chưa được gán | Kiểm tra secret mapping và validation không rỗng |
| Task dùng giá trị cũ | Property đã được thiết lập trước đó và không ghi đè | Nạp env sớm hoặc chạy Ant invocation riêng |
| Chạy trên Windows được nhưng Linux thất bại | Sai chữ hoa/chữ thường hoặc khác cách đặt env | Chuẩn hóa tên biến và tham chiếu đúng property |
| SSH từ chối kết nối | Sai user/key/passphrase hoặc host key chưa được tin cậy | Kiểm tra credential, known_hosts và quyền file |
| SCP báo thiếu thư viện | Chưa cài dependency SSH tùy chọn của Ant | Cài đúng thư viện theo tài liệu Ant |
| Ký JAR báo lỗi keystore | Sai đường dẫn keystore, alias hoặc password | Kiểm tra secret file và alias, không in password |
| FTP đăng nhập được nhưng upload lỗi | Quyền thư mục, chế độ passive hoặc cấu hình TLS | Kiểm tra quyền remote và cấu hình FTPS |
| CLI báo thiếu token | Token chưa được truyền vào môi trường tiến trình con | Dùng nested env hoặc inject trực tiếp từ CI |
| Secret xuất hiện trong log | Echo property, debug/verbose hoặc công cụ con in tham số | Xóa output nhạy cảm và xoay vòng secret đã lộ |
| Job test cũng nhận được secret release | Secret được cấp ở phạm vi pipeline quá rộng | Chỉ inject secret trong job/environment phát hành |
| Task bỏ qua lỗi upload | Cấu hình ignore hoặc không kiểm tra exit code | Đặt failonerror=true hoặc kiểm tra result property |

### 13.1. Chẩn đoán mà không lộ giá trị

Có thể kiểm tra trạng thái của property bằng condition:

~~~xml
<condition property="deploy.user.present">
    <isset property="env.DEPLOY_USER"/>
</condition>

<fail unless="deploy.user.present"
      message="DEPLOY_USER is not available in the Ant environment."/>
~~~

Không dùng echo để in giá trị thực. Nếu cần biết biến có rỗng không, dùng equals trong condition như ví dụ validation trước đó.

### 13.2. Kiểm tra quyền của secret file

Nếu CI tạo private key hoặc keystore dưới dạng file, kiểm tra:

- Đường dẫn tồn tại.
- Tiến trình Ant có quyền đọc.
- File chỉ cho tài khoản runner hoặc nhóm cần thiết truy cập.
- File được tạo trong thư mục tạm của job.
- File không bị upload vào artifact hoặc cache.
- File được xóa khi job kết thúc nếu runner được tái sử dụng.

Trên Unix-like, private key thường cần quyền đọc hạn chế, chẳng hạn chỉ chủ sở hữu đọc được. Trên Windows, dùng ACL để giới hạn tài khoản có thể truy cập.

## 14. Thực hành tốt

- Giữ cấu hình không nhạy cảm trong build.xml hoặc release.properties.
- Cấp password, token và passphrase từ secret store của CI.
- Dùng property environment để đọc biến môi trường khi task Ant cần giá trị trực tiếp.
- Dùng nested env trong exec khi chỉ cần chuyển một biến cho tiến trình con.
- Nạp môi trường trước khi target phát hành sử dụng property.
- Kiểm tra biến bắt buộc tồn tại và không rỗng trước khi ký hoặc upload.
- Không truyền password/token qua tham số -D hoặc command line.
- Không echo secret, không in toàn bộ property và hạn chế debug/verbose.
- Ưu tiên SSH key hoặc token ngắn hạn thay cho password dùng lâu dài.
- Kiểm tra SSH host key bằng known_hosts; không bật trust chỉ để bỏ qua xác minh.
- Dùng FTPS hoặc SFTP thay FTP thuần khi truyền dữ liệu xác thực.
- Bảo vệ private key và keystore bằng secret file, quyền đọc hạn chế và thời gian tồn tại ngắn.
- Chỉ cấp credential cho job phát hành cần dùng.
- Không để credential đi vào manifest, artifact, report hoặc cache.
- Dùng tài khoản deploy với quyền tối thiểu và thư mục đích giới hạn.
- Xoay vòng credential ngay khi có dấu hiệu bị lộ.
- Chạy Ant invocation riêng nếu các môi trường cần bộ credential khác nhau.

## 15. Tự kiểm tra trước khi chạy target publish

Trước khi phát hành, hãy tự trả lời:

1. Credential được cấp từ secret store hoặc nguồn được kiểm soát nào?
2. Biến môi trường có được inject vào đúng job và đúng phạm vi không?
3. Buildfile đã nạp environment trước khi dùng các property chưa?
4. Tên biến và cách viết property có thống nhất giữa Windows và Linux không?
5. Các giá trị bắt buộc đã được kiểm tra tồn tại và không rỗng chưa?
6. Task đang dùng password, SSH key, keystore hay token?
7. Nếu dùng SSH, known_hosts có xác minh đúng máy chủ không?
8. Nếu ký JAR, keystore và alias có đúng artifact phát hành không?
9. Nếu dùng FTP, dữ liệu đăng nhập có được bảo vệ bằng TLS không?
10. Có secret nào bị in vào log, truyền qua command line hoặc ghi vào artifact không?
11. Secret có bị cấp cho test job hoặc pull request không đáng tin cậy không?
12. Credential có quyền tối thiểu, thời hạn phù hợp và khả năng thu hồi không?
13. Nếu một task phát hành thất bại, build có dừng với mã lỗi phù hợp không?
14. File private key/keystore tạm có được bảo vệ và dọn dẹp sau job không?

Truyền thông tin xác thực qua môi trường giúp buildfile không phải chứa password hoặc token cố định. Khi kết hợp secret store của CI, validation sớm, SSH host verification, quyền tối thiểu và kiểm soát log, các task phát hành của Ant có thể dùng credential theo cách dễ quản lý và ít rủi ro hơn.

## Tài liệu tham khảo

- [Apache Ant — Property Task](https://ant.apache.org/manual/Tasks/property.html)
- [Apache Ant — Running Ant and environment variables](https://ant.apache.org/manual/running.html)
- [Apache Ant — SCP Task](https://ant.apache.org/manual/Tasks/scp.html)
- [Apache Ant — SSHEXEC Task](https://ant.apache.org/manual/Tasks/sshexec.html)
- [Apache Ant — SignJar Task](https://ant.apache.org/manual/Tasks/signjar.html)
- [Apache Ant — FTP Task](https://ant.apache.org/manual/Tasks/ftp.html)
- [Apache Ant — Exec Task](https://ant.apache.org/manual/Tasks/exec.html)

