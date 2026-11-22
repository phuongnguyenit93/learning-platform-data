# Giữ bí mật ngoài buildfile, tệp phân phối và nhật ký trong Apache Ant

Apache Ant thường được dùng để biên dịch, đóng gói và phát hành ứng dụng Java. Trong các bước này, bản dựng có thể cần mật khẩu kho lưu trữ, token của dịch vụ phát hành, khóa ký hoặc thông tin truy cập hệ thống nội bộ. Nếu đưa những giá trị đó trực tiếp vào `build.xml`, lưu chúng chung với tệp phát hành hoặc in ra nhật ký, một bản dựng thành công vẫn có thể gây lộ thông tin quan trọng.

Nguyên tắc cốt lõi là **đưa bí mật đến đúng công cụ cần sử dụng tại đúng thời điểm, trong phạm vi ngắn nhất**, đồng thời bảo đảm nội dung được phát hành và nhật ký chỉ chứa dữ liệu được phép tiết lộ. Ant hỗ trợ tự động hóa quá trình này, nhưng **Ant property không phải một kho lưu trữ bí mật hay cơ chế che log tự động**.

Bài học hướng dẫn cách tổ chức bản dựng Ant an toàn ở ba ranh giới: **nguồn cấu hình build**, **đầu ra phân phối**, và **nhật ký/chẩn đoán**. Các ví dụ minh họa cách tách đóng gói khỏi phát hành, giới hạn danh sách tệp được đưa vào ZIP và chuyển quyền sử dụng thông tin xác thực cho một công cụ ngoài biết đọc secret từ môi trường được cấp riêng.

## 1. Xác định những gì phải giữ bí mật

Một secret là giá trị mà người không được cấp quyền không nên biết hoặc sao chép. Các loại thường gặp trong quy trình Ant:

| Loại dữ liệu | Ví dụ | Nơi nên quản lý |
|---|---|---|
| Mật khẩu và token phát hành | Token upload lên kho artifact, token CI/CD | Secret manager hoặc cơ chế lưu secret của CI |
| Khóa ký | Private key dùng để ký JAR hay gói cài đặt | Kho khóa/credential store có kiểm soát quyền |
| Thông tin tài khoản dịch vụ | API key, client secret, access token | Secret manager hoặc credential file nằm ngoài vùng build |
| Dữ liệu cấu hình nhạy cảm | Mật khẩu cơ sở dữ liệu, URL kết nối chứa credential | Cấu hình runtime riêng, được cấp khi triển khai |
| Thông tin dùng tạm | OTP, token ngắn hạn, session credential | Cấp ngay trước khi dùng và hủy hoặc cho hết hạn sau đó |

Không phải tất cả cấu hình đều là secret. Tên ứng dụng, phiên bản release, cổng mạng công khai, tên môi trường như `staging` hay `production` thường có thể xuất hiện trong manifest hoặc gói phân phối. Điều cần tránh là **giá trị xác thực** hoặc thông tin nội bộ chưa được phê duyệt công bố.

Đặc biệt, **một secret có thể bị tiết lộ gián tiếp**: token nằm trong URL truy cập repository, password nằm trong thông báo lỗi HTTP, private key bị copy vào thư mục staging, hoặc Java source chứa hằng số nhạy cảm rồi được biên dịch vào `.class`. Việc không thấy một tệp tên `secrets.properties` trong ZIP chưa đủ chứng minh ZIP sạch.

## 2. Sơ đồ luồng dữ liệu an toàn

Một cấu trúc phát hành nên có hai luồng tách biệt:

```text
   Nguồn công khai đã chọn lọc
              |
              v
       Ant target package
              |
              v
     dist/release.zip   ---------------------+
       (không có secret)                    |
                                           v
  Secret manager / CI secrets ------> Bước publish riêng
             |                             |
    Cấp token chỉ cho bước cần             v
             +--------------------> Công cụ upload
                                     (đọc token từ
                                      môi trường hoặc
                                      credential store)
                                           |
                                           v
                                    Artifact repository

  Buildfile, source control, dist và log
      không chứa giá trị bí mật.
```

Trong thiết kế này, `build.xml` biết **cần chạy tác vụ nào**, nhưng không biết **giá trị token là gì**. Công cụ phát hành chỉ nhận token khi chạy ở môi trường đã được cấp quyền; không có lý do để thêm token vào ZIP, manifest, Java class hoặc tham số dòng lệnh.

Ba ranh giới cần xem xét:

1. **Nguồn build:** file XML, properties, script, biến cấu hình và lịch sử Git.
2. **Đầu ra build:** JAR/WAR/EAR/ZIP, thư mục `dist`, test report, source map, manifest, cache và tệp tạm.
3. **Kênh quan sát:** terminal, log của Ant, log CI, exception/stack trace, báo cáo và log của các tiến trình con.

Bí mật đi qua một ranh giới mới chỉ khi thật sự cần. Càng ít bước xử lý giá trị secret, càng ít nơi phải kiểm tra rò rỉ.

## 3. Vì sao không nên đặt secret trong `build.xml`?

Ant cho phép khai báo property như sau:

```xml
<!-- Ví dụ KHÔNG an toàn: không làm theo -->
<property name="deploy.password" value="my-production-password"/>
<property name="deploy.token" value="token-value-here"/>

<target name="publish">
    <exec executable="release-uploader">
        <arg value="--token"/>
        <arg value="${deploy.token}"/>
    </exec>
</target>
```

Cách viết này tạo ít nhất ba nơi có thể lộ secret: giá trị nằm trong file được lưu hoặc commit; property có thể bị task và logger quan sát; tham số `--token` có thể xuất hiện trong danh sách tiến trình, thông báo lỗi hoặc log của công cụ upload.

Cùng vấn đề xuất hiện khi đặt secret vào:

- `build.xml` và mọi file XML được `<import>` hoặc `<include>`.
- `build.properties`, `local.properties` hoặc các file `.properties` được đưa lên Git.
- Script `.bat`, `.cmd`, `.sh` dùng để gọi Ant.
- Metadata được sinh ra từ template có chứa password, token hoặc private key.
- Lời gọi `ant -Ddeploy.token=...` viết trực tiếp trong script hay cấu hình CI.

**Ant property không có cơ chế “secret” đặc biệt.** Giá trị của `<property>` thường là chuỗi thông thường trong bộ nhớ, có thể được nội suy bằng `${...}` và truyền sang task khác. Việc đặt tên như `secret.password` không tự động ẩn giá trị khỏi nhật ký.

### 3.1. Tại sao `-Dtoken=...` không phải cách cấp bí mật an toàn?

Lệnh sau trông tiện lợi nhưng không nên dùng cho credential:

```bash
ant -f build.xml -Ddeploy.token=YOUR_REAL_TOKEN publish
```

Token có thể được lưu trong lịch sử shell, trong cấu hình job, trong log dòng lệnh đã chạy hoặc bị quan sát qua thông tin tiến trình tùy hệ điều hành và quyền truy cập. Lệnh `-D` phù hợp cho **tham số không nhạy cảm** như phiên bản, môi trường hoặc đường dẫn công khai.

Đẩy token sang `ANT_OPTS` hoặc tham số JVM `-D...` cũng không biến nó thành bí mật: giá trị vẫn có thể xuất hiện trong môi trường, đối số JVM hoặc dữ liệu chẩn đoán của tiến trình.

### 3.2. `-propertyfile` và `<property file="...">` có an toàn không?

Tệp properties giúp tách cấu hình khỏi XML, nhưng bản thân tệp **không được mã hóa**. Nếu chứa secret, nó phải nằm ngoài vùng được commit/đóng gói, có quyền truy cập hạn chế, vòng đời rõ ràng và được cấp bởi hệ thống quản lý secret khi cần.

Ví dụ:

```xml
<!-- Cần thận trọng nếu file chứa credential -->
<property file="private/local-credentials.properties"/>
```

Cách đọc trên đưa giá trị vào hệ thống property của Ant. Sau đó mọi task có khả năng tham chiếu property đều có thể nhận được giá trị. Nếu logger, task hoặc debug dump ghi lại property, secret cũng có thể bị ghi ra. Khi chỉ một công cụ phát hành cần credential, nên để **chính công cụ đó** đọc từ credential store hoặc tệp được cấp quyền, thay vì nhập toàn bộ secret vào Ant.

## 4. Nguồn cấp secret: ưu tiên secret manager và phạm vi ngắn

Cách triển khai thường gặp là lưu credential trong secret manager của tổ chức hoặc vùng secret của nền tảng CI. Job được phân quyền sẽ cấp secret cho **bước sử dụng**; phần build/compile/package trước đó không cần biết giá trị.

Có hai cách truyền phổ biến:

- **Biến môi trường được cấp cho tiến trình:** phù hợp khi công cụ đích có hỗ trợ đọc credential từ biến như `DEPLOY_TOKEN`.
- **Tệp credential riêng bên ngoài workspace:** phù hợp khi công cụ cần một tệp cấu hình, keystore hoặc private key. Tệp phải do môi trường được kiểm soát cấp và chỉ có quyền đọc tối thiểu.

Cả hai đều yêu cầu bảo vệ môi trường chạy. Biến môi trường không được mã hóa mặc định; người hoặc tiến trình có quyền phù hợp trên cùng máy có thể xem chúng. Một tệp credential cũng có thể bị đọc nếu phân quyền sai hoặc bị chép vào artifact. Chúng là **cách hạn chế lộ secret trong nguồn và tham số**, không phải giải pháp bảo mật độc lập cho máy build.

### 4.1. Ví dụ CI chỉ cấp secret ở bước publish

Ví dụ cú pháp GitHub Actions (minh họa môi trường CI; Ant không phụ thuộc GitHub Actions):

```yaml
steps:
  - name: Package public files
    run: ant -f build.xml package

  - name: Publish
    env:
      DEPLOY_TOKEN: ${{ secrets.DEPLOY_TOKEN }}
    run: ant -f build.xml publish
```

Ở đây bước `package` không được cấp `DEPLOY_TOKEN`. Bước `publish` nhận token trong môi trường của tiến trình và tiến trình con, nếu công cụ phát hành cần nó. Cần cấu hình quyền của runner, quyền truy cập secret và xác thực job/branch theo chính sách của hệ thống CI.

**Không giả định cơ chế che secret của CI có thể chặn mọi rò rỉ.** Log có thể bị biến đổi bằng encode, chia nhỏ, viết sang file hoặc chuyển sang artifact trước khi bộ lọc che hoạt động. Phòng ngừa bằng cách không in secret là chính.

### 4.2. Cấp biến môi trường tạm thời khi chạy ở máy cá nhân

Nếu công cụ phát hành chấp nhận `DEPLOY_TOKEN`, Bash có thể đọc token từ người dùng mà không đưa giá trị vào câu lệnh shell:

```bash
(
    read -r -s -p "Deploy token: " DEPLOY_TOKEN
    printf '\n'
    export DEPLOY_TOKEN
    ant -f build.xml publish
)
```

Đây là ví dụ cho **Bash**. Dấu `-s` khiến nội dung đang nhập không hiện trên terminal; dùng subshell `(...)` để biến môi trường được giải phóng khỏi shell gọi khi khối lệnh kết thúc. Tránh bật `set -x` (shell tracing) trong lúc chuẩn bị/đọc credential; tránh lưu token vào lịch sử, log hoặc tệp tạm.

Nếu tổ chức có công cụ lấy secret từ vault, nên sử dụng quy trình xác thực và cơ chế cấp credential của công cụ đó. Không nên tự tạo một script mật khẩu riêng khi nền tảng đã có secret manager.

### 4.3. Khi công cụ chỉ chấp nhận tệp credential

Đặt tệp bên ngoài source tree và thư mục phân phối, ví dụ đường dẫn riêng do CI cấp:

```text
workspace/
  project/
    build.xml
    public-release/
    build/
    dist/

/secure-runtime/credentials/deploy.json  <-- chỉ tồn tại khi publish
```

Công cụ được phép đọc tệp trực tiếp. Ant chỉ cần biết nên chạy công cụ nào; không nhất thiết phải mở hay copy tệp đó. Trên Linux/macOS, giới hạn quyền đọc ở user của job; trên Windows, quản lý ACL tương ứng.

Không đặt credential file trong `src/main/resources`, `WEB-INF`, `META-INF`, thư mục Docker build context hoặc bất kỳ thư mục nào task `<copy>`/`<zip>`/`<jar>` có thể quét tự động.

## 5. Thiết kế Ant buildfile chỉ đóng gói dữ liệu công khai

Ta xây ví dụ nhỏ mà người đọc có thể dùng làm mẫu. Source tree chứa đúng các tài nguyên dự kiến xuất bản:

```text
safe-ant-release/
├── build.xml
├── public-release/
│   ├── README.txt
│   ├── config/
│   │   └── app.properties       # chỉ chứa giá trị công khai
│   └── assets/
│       └── description.txt
└── dist/                        # Ant tạo khi chạy
```

Ví dụ `public-release/config/app.properties`:

```properties
app.name=sample-service
app.environment=production
app.port=8080
```

File này **không** có `db.password`, `api.key` hoặc khóa truy cập. Mật khẩu kết nối và token dành cho ứng dụng runtime sẽ được cấp khi triển khai theo cơ chế riêng của hệ thống chạy.

Nội dung `build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="safe-ant-release" default="package" basedir=".">
    <property name="public.dir" location="public-release"/>
    <property name="dist.dir" location="dist"/>

    <target name="package">
        <mkdir dir="${dist.dir}"/>

        <!-- Chỉ đưa những đường dẫn được cho phép vào ZIP -->
        <zip destfile="${dist.dir}/release.zip" whenempty="fail">
            <fileset dir="${public.dir}">
                <include name="README.txt"/>
                <include name="config/app.properties"/>
                <include name="assets/**"/>
            </fileset>
        </zip>
    </target>

    <target name="publish">
        <available file="${dist.dir}/release.zip"
                   property="release.exists"/>
        <fail unless="release.exists"
              message="Chưa có release.zip; hãy chạy target package"/>

        <!-- Công cụ giả định tự đọc DEPLOY_TOKEN từ môi trường -->
        <exec executable="release-uploader" failonerror="true">
            <arg value="--artifact"/>
            <arg file="${dist.dir}/release.zip"/>
        </exec>
    </target>
</project>
```

Ở đây, `release-uploader` là **tên công cụ minh họa**, không phải lệnh có sẵn của Ant. Khi áp dụng thực tế, thay bằng ứng dụng phát hành đã cài đặt và xác nhận nó hỗ trợ lấy credential từ môi trường/secret store, không bắt buộc truyền bằng `--token=...`.

Chạy lần lượt:

```bash
ant -f build.xml package
ant -f build.xml publish
```

Lệnh thứ hai chỉ hoạt động nếu `release.zip` đã tồn tại, `release-uploader` có sẵn và môi trường đã cấp credential cho nó. Không có token nào được khai báo trong XML hoặc đưa vào command argument của `<exec>`.

### 5.1. Tại sao dùng allowlist thay vì quét cả thư mục dự án?

Khác biệt đáng chú ý:

```xml
<!-- Dễ đưa nhầm tệp nhạy cảm vào gói -->
<zip destfile="dist/release.zip" basedir="."/>
```

Cấu hình đó có thể đưa vào archive cả `.git`, file local, script nội bộ, log hoặc chính tệp ZIP đang được tạo tùy cấu trúc build. Chỉ khai báo `excludes="**/*secret*"` là chưa đủ: không thể dự đoán mọi tên tệp nhạy cảm.

Cấu hình an toàn hơn là chọn **cụ thể đường dẫn được phép** bằng `<fileset>` như ví dụ. Hãy coi thư mục `public-release` là nơi chỉ chứa nội dung có thể phát hành và xem lại từng pattern khi thêm file.

Một allowlist có thể vẫn vô tình đưa secret vào file được cho phép: nếu `config/app.properties` chứa `db.password`, đường dẫn được phép vẫn có nội dung không hợp lệ. Vì vậy cần kiểm soát **tên tệp lẫn nội dung tệp**.

### 5.2. Không đặt secret trong JAR, WAR, ZIP hay manifest

Những vị trí đặc biệt dễ bị bỏ sót:

| Đầu ra | Cách secret lọt vào |
|---|---|
| `.jar` / `.war` / `.ear` | Tài nguyên trong `src/main/resources`, `WEB-INF`, file cấu hình hoặc lớp Java chứa hằng số. |
| `.zip` / `.tar` | `<fileset>` quá rộng, thư mục staging lẫn credential và artifact. |
| `MANIFEST.MF` | `<manifest>` ghi property đã nội suy, URL chứa thông tin đăng nhập hoặc metadata nội bộ. |
| Template đã thay thế biến | `<copy filtering="true">`, `<filterset>` hoặc `<replace>` đưa password/token vào file phát hành. |
| Source map và báo cáo | Dữ liệu runtime, URL nội bộ, chuỗi cấu hình hoặc log đã được đóng gói. |
| Container/image | Credential nằm trong Docker build context, layer hoặc biến môi trường được lưu ở cấu hình image. |

Ví dụ dễ gây rò rỉ nếu property chứa secret:

```xml
<!-- KHÔNG làm theo: secret thành một phần manifest -->
<jar destfile="dist/app.jar" basedir="build/classes">
    <manifest>
        <attribute name="Deploy-Token" value="${deploy.token}"/>
    </manifest>
</jar>
```

Manifest có thể xem bằng các công cụ thông thường; ký hoặc nén JAR không làm nội dung đó trở thành bí mật. Tương tự, base64 encoding và obfuscation không thay cho việc giữ credential ngoài tệp phân phối.

Đối với ứng dụng cần thông tin bí mật khi chạy, hãy cấu hình **runtime** lấy credential từ môi trường triển khai hoặc secret store, thay vì biên dịch trực tiếp vào code hay đính kèm trong archive.

## 6. Nguy cơ rò rỉ khi lọc token và nội suy property

Ant hỗ trợ nhiều cách xử lý tệp văn bản:

- `<copy filtering="true">` và `<filterset>` để thay token trong file.
- `<replace>` để thay chuỗi.
- `<expandproperties>` và các filter/chain khác để nội suy giá trị.
- `<echo file="...">` để ghi nội dung ra file.
- `<propertyfile>` để tạo hoặc sửa file properties.

Những task này hữu ích để tạo cấu hình, nhưng nếu đầu vào có secret, kết quả có thể trở thành artifact được lưu hoặc phát hành.

Ví dụ không an toàn:

```xml
<!-- KHÔNG làm theo: phát hành file có token đã nội suy -->
<copy file="templates/app.properties"
      tofile="dist/config/app.properties"
      filtering="true">
    <filterset>
        <filter token="API_KEY" value="${api.key}"/>
    </filterset>
</copy>
```

Nếu template chứa `@API_KEY@`, tệp output có thể mang giá trị bí mật. Sau khi file xuất hiện trong `dist`, một bước khác có thể tải nó lên artifact repository mà không hiểu nội dung.

Mẫu tốt hơn là sử dụng placeholder công khai:

```properties
# File đóng gói vào bản phát hành
external.api.key.source=runtime-secret-store
```

Đây là **cấu hình chỉ dẫn**, không phải giá trị API key. Ứng dụng hoặc nền tảng triển khai cần có cơ chế runtime tương ứng để đọc khóa thật.

Nếu vì tương thích hệ thống mà cần sinh tệp chứa credential, chỉ tạo nó ở pha triển khai trên môi trường được kiểm soát, lưu ngoài workspace phát hành, đặt quyền truy cập tối thiểu, không lưu cache và dọn theo chính sách vận hành. Tránh dùng Ant làm nơi trung chuyển secret khi không cần thiết.

## 7. Ngăn secret lọt vào log của Ant

Một bản dựng có thể không chứa password trong XML nhưng vẫn rò rỉ khi mở chế độ debug hoặc khi task cố gắng in giá trị.

Các lệnh thường gặp:

```bash
ant -f build.xml package
ant -f build.xml -verbose package
ant -f build.xml -debug package
ant -f build.xml -logfile build.log package
ant -diagnostics
```

`-verbose` và `-debug` hữu ích để chẩn đoán target, dependency và property, nhưng mức chi tiết cao có thể khiến các giá trị hoặc đường dẫn nhạy cảm xuất hiện trong log tùy task/logger. `ant -diagnostics` đưa ra nhiều dữ liệu môi trường; cần rà soát trước khi chia sẻ.

**`-logfile` không che dữ liệu bí mật.** Nó chỉ chuyển log sang tệp. `-quiet`/`-silent` cũng không phải biện pháp bảo mật đáng tin cậy; một task, listener hoặc ứng dụng con vẫn có thể viết secret vào file, stdout hoặc stderr.

### 7.1. Các pattern cần tránh

```xml
<!-- KHÔNG làm theo khi giá trị là bí mật -->
<echo message="Deploy token: ${deploy.token}"/>
<echo file="dist/deploy-log.txt" message="${deploy.token}"/>
<echoproperties/>
<fail message="Authentication failed for ${deploy.token}"/>
```

`<echoproperties>` có thể ghi hàng loạt property của Ant, trong đó có những giá trị được lấy từ môi trường hoặc properties file. Nếu dùng `<property environment="env"/>` để nhập toàn bộ biến môi trường vào Ant, chính phạm vi dữ liệu có thể bị log cũng tăng lên.

Khi cần thông báo lỗi, chỉ ghi trạng thái:

```xml
<fail message="Publish failed: check uploader exit code and permissions"/>
```

Đừng đưa token hoặc URL mang credential vào thông báo để “dễ debug”. Nếu cần biết secret đang tồn tại hay không, kiểm tra điều kiện mà **không in giá trị**.

### 7.2. Chú ý tới tiến trình con và listener

Một target có thể gọi công cụ khác:

```xml
<exec executable="release-uploader" failonerror="true">
    <arg value="--artifact"/>
    <arg file="dist/release.zip"/>
</exec>
```

Dù Ant không tự in token, công cụ `release-uploader` vẫn có thể in request header, URL xác thực hoặc dump môi trường khi lỗi. Vì vậy phải kiểm tra hành vi log của **cả công cụ được gọi**.

Tương tự, `-logger` và `-listener` cho phép thay cách ghi nhật ký và thêm bộ thu thập sự kiện. Một listener ghi tất cả message vào tệp khác có thể tạo bản sao của thông tin nhạy cảm. Việc cấu hình logger mới không đảm bảo redaction, trừ khi implementation có cơ chế lọc đã được xác minh.

Các task nhận đầu ra chương trình, như `<exec output="...">`, `<exec outputproperty="...">` hoặc redirector, có thể ghi lại nội dung stdout/stderr hoặc biến đầu ra thành property. Không dùng chúng để gom log chứa credential vào file phân phối hoặc bản ghi chẩn đoán.

### 7.3. Shell tracing và log CI

Một số rò rỉ xảy ra trước khi Ant chạy:

```bash
# Rủi ro nếu script bật tracing rồi tạo lệnh chứa secret
set -x
ant -Ddeploy.token="$DEPLOY_TOKEN" publish
```

Khi shell tracing bật, dòng lệnh sau khi thay biến có thể được ghi vào log. Bất kể có bật tracing hay không, truyền secret qua `-D...` vẫn đưa nó vào đối số tiến trình Ant.

Trong CI, tránh in mọi biến môi trường bằng các lệnh chẩn đoán kiểu `env`, `printenv` hoặc dump toàn bộ cấu hình khi secret đã được cấp. Cơ chế log của CI phải có chính sách truy cập và thời gian giữ phù hợp, nhưng kiểm soát truy cập log không bù được việc đưa token vào log.

## 8. Kiểm tra gói phân phối trước khi phát hành

Bước đóng gói kết thúc thành công chỉ chứng minh Ant tạo được artifact. Nó không chứng minh artifact không mang credential.

Có thể xem danh sách tệp trong ZIP/JAR bằng lệnh Java JDK:

```bash
jar tf dist/release.zip
```

Với ví dụ ở mục 5, danh sách dự kiến chỉ gồm những đường dẫn đã cho phép như `README.txt`, `config/app.properties` và `assets/description.txt` (có thể kèm entry thư mục). Nếu xuất hiện `.env`, `credentials.json`, private key hoặc log, hãy dừng phát hành và xem lại các `fileset`/task sinh artifact.

Cần kiểm tra thêm **nội dung** của các tệp đã được đóng gói, vì một secret có thể ẩn dưới tên file hoàn toàn bình thường. Có thể áp dụng công cụ quét secret được tổ chức phê duyệt ở bước kiểm tra artifact, chạy trên nội dung ZIP/JAR đã giải nén trong vùng tạm được bảo vệ. Nên cấu hình kết quả quét chỉ báo **có/không, vị trí và loại vấn đề**, tránh in giá trị secret thật vào log kiểm tra.

### 8.1. Danh sách cho phép và danh sách cấm

Hai biện pháp có vai trò khác nhau:

- **Allowlist:** chỉ đưa vào archive các tệp hoặc nhóm tệp được phép; đây là lựa chọn nền tảng.
- **Denylist/gate:** chặn thêm một số mẫu sai phạm đã biết như `.env`, `*secret*` hoặc `credentials*`; hữu ích làm lớp bảo vệ bổ sung, nhưng không bao quát mọi trường hợp.

Ví dụ một điều kiện Ant chặn tệp có tên đáng ngờ trong **thư mục staging đã xác định**:

```xml
<fail message="Có tệp nhạy cảm trong thư mục staging">
    <condition>
        <resourcecount when="greater" count="0">
            <fileset dir="build/staging">
                <include name="**/*.env"/>
                <include name="**/*secret*"/>
                <include name="**/*credential*"/>
            </fileset>
        </resourcecount>
    </condition>
</fail>
```

Mẫu này phù hợp nếu target của bạn thực sự tạo `build/staging` và muốn bổ sung một cổng kiểm tra; thư mục phải tồn tại khi thực hiện. Một tệp có tên khác vẫn có thể chứa secret, nên ví dụ **không thay thế** việc hạn chế đầu vào và quét nội dung.

### 8.2. Kiểm tra các artifact phụ

Ngoài file ZIP/JAR cuối cùng, xem cả:

- Thư mục build tạm và thư mục staging.
- Test result XML/HTML, báo cáo coverage và log thử nghiệm.
- Cache CI, artifact được upload tự động ngay cả khi job thất bại.
- Docker build context và các layer/image được tạo nếu Ant gọi container tool.
- Tệp nguồn đã sinh, manifest, tài nguyên đóng gói và file metadata.
- Bản log sinh từ `-logfile`, `<record>` hoặc công cụ phát hành.

Nếu quy trình dùng chung thư mục cho build, staging và dist, những tệp cũ từ lượt trước có thể lọt vào đầu ra. Tổ chức thư mục rõ ràng và lựa chọn tệp theo allowlist giúp giảm nguy cơ này.

## 9. Tách target build, package và publish

Một build an toàn thường có cấu trúc:

```text
compile  -->  package  -->  kiểm tra artifact
                             |
                             v
                      publish (có credential)
```

Đối với ví dụ mục 5, `package` và `publish` là hai target độc lập. Bước publish kiểm tra có artifact trước khi gọi công cụ upload. Tại CI, có thể chạy `package` khi chưa cấp secret, kiểm tra ZIP, sau đó cấp secret cho một bước `publish` riêng.

Lợi ích:

1. **Thời gian tồn tại secret ngắn:** các bước compile/test/package thường không cần truy cập credential phát hành.
2. **Giảm phạm vi bị lộ:** script và task đóng gói không nhìn thấy secret mà chúng không cần.
3. **Dễ kiểm tra:** artifact có thể được xác minh trước khi upload.
4. **Dễ cấp quyền:** chỉ job hoặc bước được phê duyệt mới có quyền phát hành.

Tuy nhiên, tách target chỉ có ý nghĩa khi cơ chế CI thực sự giới hạn secret theo từng bước và workspace/runner được bảo vệ. Nếu đặt token vào biến môi trường của toàn bộ job từ đầu, mục tiêu giảm phạm vi truy cập sẽ không đạt.

Nếu cần ký JAR trước khi publish, thêm một bước ký riêng nhận private key từ hệ thống được bảo vệ. Private key không được đóng gói cùng JAR ký; quá trình ký chỉ nên tạo chữ ký và metadata công khai cần thiết.

## 10. Không dùng `.gitignore` làm cơ chế bảo vệ duy nhất

Một số dự án thêm các mục sau:

```gitignore
.env
*.secret
local-credentials.properties
dist/
build/
```

Những pattern này giúp giảm nguy cơ **vô tình** đưa tệp mới vào Git. Nhưng `.gitignore` không ngăn:

- Tệp đã được Git theo dõi từ trước tiếp tục xuất hiện trong commit.
- Tệp bị copy hoặc nén vào ZIP bằng task Ant.
- Token bị in trên terminal/log hoặc xuất hiện trong lệnh gọi CI.
- Artifact/caches được upload ngoài cơ chế Git.
- Secret từng được commit còn nằm trong lịch sử repository.

Nếu cần lưu một file config mẫu, hãy tạo template **không chứa secret**, chẳng hạn `credentials.example.properties` chỉ mô tả tên trường hoặc placeholder. File thật phải được cấp ở môi trường an toàn và nằm ngoài tập tin được phát hành.

Việc tách secret khỏi Git phải được thực hiện ngay từ thiết kế, thay vì chỉ bổ sung `.gitignore` sau khi đã commit dữ liệu nhạy cảm.

## 11. Phân biệt giá trị secret với metadata có thể ghi log

Không phải thông tin nào liên quan đến bước phát hành cũng phải ẩn. Nhật ký vẫn cần đủ dữ liệu để chẩn đoán.

| Nên ghi | Không nên ghi |
|---|---|
| Target đang chạy, tên công cụ, mã thoát | Password, API token, private key |
| Phiên bản ứng dụng, mã commit công khai theo chính sách | URL có embedded credential hoặc query token |
| Tên kho artifact được phép công bố | Header `Authorization` hoặc cookie xác thực |
| Số lượng tệp đã đóng gói, kích thước artifact | Toàn bộ biến môi trường hay mọi Ant property |
| Thông báo `credentials unavailable` hoặc `authentication failed` | Giá trị credential được dùng hoặc chuỗi mã hóa từ credential |
| ID job và thời điểm chạy phù hợp | Nội dung tệp credential và đường dẫn cá nhân không cần thiết |

Thay vì:

```text
Upload failed with token eyJ... to https://user:password@example.invalid
```

hãy ghi:

```text
Publish failed: uploader exited with code 1.
Target: publish
Artifact: dist/release.zip
Credential source: CI environment
Check repository permissions and uploader diagnostics.
```

Việc log nguồn cấp theo **loại** (“CI environment”, “credential file”, “vault”) thường đủ để người vận hành hiểu luồng dữ liệu. Không cần ghi tên secret thực tế, đường dẫn nội bộ nhạy cảm hay giá trị của biến.

## 12. Đối phó khi nghi đã lộ secret

Nếu phát hiện token trong `build.xml`, log, ZIP hoặc lịch sử Git, không nên chỉ xóa dòng trong file hiện tại rồi tiếp tục dùng token cũ.

Quy trình xử lý phù hợp:

1. **Ngừng sử dụng và thu hồi hoặc xoay vòng credential** qua hệ thống cấp phát chính thức. Nếu token đã tới kho công khai, coi nó là đã bị lộ.
2. **Xác định phạm vi:** secret đã xuất hiện ở commit nào, artifact nào, log của job nào, cache nào và ai có thể truy cập.
3. **Xử lý bản sao đã phát tán:** gỡ artifact/log/cache theo quy trình tổ chức và rà soát lịch sử repository khi cần. Việc viết đè tệp local không xóa bản đã tải xuống.
4. **Xác định con đường rò rỉ:** property trong buildfile, `-D`, echo/debug, filtering, fileset quá rộng hay công cụ ngoài in credential.
5. **Thay đổi luồng build:** chuyển secret sang bước được cấp quyền, giới hạn packaging bằng allowlist và bổ sung kiểm tra artifact/log.
6. **Ghi nhận sự cố không kèm giá trị secret:** báo cáo tên hệ thống, ảnh hưởng, thời điểm, biện pháp đã thực hiện và trạng thái token mới.

Nếu secret đã từng được commit, xóa dòng ở commit mới **không xóa lịch sử Git**. Việc viết lại lịch sử là một thay đổi phối hợp có ảnh hưởng đến đồng nghiệp và hệ thống CI; cần thực hiện theo quy trình tổ chức. Ưu tiên thu hồi credential ngay vì không thể bảo đảm mọi bản sao trong lịch sử đã biến mất.

## 13. Những sai lầm thường gặp trong Ant

| Hiện tượng | Vì sao nguy hiểm | Cách xử lý |
|---|---|---|
| Đặt `password=value` trong `build.xml` | Secret thành mã nguồn và có thể vào lịch sử Git | Dùng secret manager, không đưa giá trị vào Ant XML |
| Truyền `-Dtoken=...` | Giá trị có thể nằm trong đối số tiến trình, shell history và log | Công cụ đích đọc credential từ môi trường/credential store |
| Dùng `<property environment="env"/>` rồi `<echoproperties>` | Nhiều biến môi trường có thể bị in ra | Không dump property; chỉ xử lý tối thiểu dữ liệu cần thiết |
| Chạy `-debug` trên job có credential rồi công khai log | Debug/task có thể ghi thông tin nhạy cảm | Không in secret từ nguồn; giới hạn log và quyền truy cập |
| Đóng gói bằng `<fileset dir=".">` hoặc ZIP cả project | Tệp local, secret và log có thể vào archive | Dùng thư mục public và allowlist file |
| `<copy filtering="true">` thay secret vào config | Credential tồn tại trong đầu ra phân phối | Chỉ tạo cấu hình công khai, cấp secret ở runtime |
| Dùng `-logfile` và cho rằng đã an toàn | Tệp log vẫn chứa nguyên dữ liệu đã ghi | Thiết kế log không chứa secret và kiểm soát tệp log |
| Đưa secret vào biến môi trường của toàn bộ pipeline | Mọi bước cùng runner có thể đọc credential | Cấp theo bước, vai trò và thời gian cần thiết |
| Chỉ dựa vào `.gitignore` | Không bảo vệ file đã track, artifact hoặc log | Kiểm tra cả Git, staging, dist, cache, log |
| Chỉ kiểm tra tên file trong JAR/ZIP | Token có thể nằm trong file có tên vô hại | Quét nội dung artifact bằng công cụ tin cậy |

### Về tính năng “ẩn secret” của logger hoặc CI

Một số nền tảng CI hỗ trợ masking, nhưng không nên xem masking là ranh giới bảo mật duy nhất. Nó có thể không nhận diện biến thể đã mã hóa, secret bị chia thành nhiều đoạn hoặc dữ liệu bị ghi vào file thay vì stdout. Với Ant, không có bảo đảm chung rằng mọi `BuildLogger`, `BuildListener` và task tùy biến đều biết cách che credential.

Hãy kiểm soát dữ liệu ngay tại nơi task nhận vào và sinh ra, sau đó dùng cơ chế masking của CI như một lớp phòng vệ bổ sung.

## 14. Tình huống thực hành: phát hành ZIP mà không đưa token vào build

Giả sử dự án cần xuất bản `release.zip` lên repository yêu cầu xác thực.

**Tình huống chưa an toàn:**

```xml
<project name="unsafe">
    <property name="token" value="ABC-SECRET"/>
    <target name="publish">
        <zip destfile="dist/release.zip" basedir="."/>
        <exec executable="release-uploader">
            <arg value="--token"/>
            <arg value="${token}"/>
            <arg value="dist/release.zip"/>
        </exec>
    </target>
</project>
```

Vấn đề: token nằm trong XML, được truyền dưới dạng đối số và ZIP có thể lấy cả file XML hoặc tệp nhạy cảm khác.

**Thiết kế đề xuất:** sử dụng `build.xml` ở mục 5 và tổ chức CI như mục 4.1.

- `ant package` chỉ lấy `public-release/README.txt`, `public-release/config/app.properties` và `public-release/assets/**`.
- Kiểm tra nội dung `dist/release.zip` và xác nhận không có credential, log hoặc tệp nội bộ.
- Chỉ ở bước `ant publish`, CI cấp `DEPLOY_TOKEN` cho `release-uploader`.
- Công cụ upload đọc credential từ môi trường và không ghi token vào stdout, stderr hay log khác.
- Thất bại publish được biểu diễn bằng mã thoát khác 0; Ant `failonerror="true"` biến thất bại đó thành lỗi build, không cần in token.

Trong tình huống này, một người có quyền xem source và ZIP nhưng không được cấp credential publish vẫn có thể kiểm tra nội dung bản phát hành mà không nhìn thấy token.

### Thực hành tự kiểm tra

Tạo cây `safe-ant-release` như mục 5, đặt `build.xml` và ba tệp public có nội dung giả, rồi chạy:

```bash
ant -f build.xml package
jar tf dist/release.zip
```

Quan sát danh sách tệp đã cho phép. Sau đó thử đặt một tệp `private.env` cạnh `build.xml` nhưng **không đưa giá trị secret thật vào tệp**; chạy lại `package` và quan sát rằng tệp đó không được chọn vào ZIP bởi allowlist.

Với bước `publish`, chỉ chạy khi đã có công cụ phát hành thực tế hỗ trợ biến môi trường và bạn được quyền sử dụng kho artifact đích. Tên `release-uploader` trong ví dụ chỉ có ý nghĩa minh họa.

## 15. Tài liệu tham khảo

- [Apache Ant Manual — Properties](https://ant.apache.org/manual/properties.html): đặc điểm property và nội suy giá trị.
- [Apache Ant Manual — Property Task](https://ant.apache.org/manual/Tasks/property.html): nạp property từ file hoặc môi trường.
- [Apache Ant Manual — Exec Task](https://ant.apache.org/manual/Tasks/exec.html): chạy công cụ ngoài, truyền đối số và môi trường.
- [Apache Ant Manual — Copy Task](https://ant.apache.org/manual/Tasks/copy.html): copy, filtering và các điều kiện ảnh hưởng nội dung đầu ra.
- [Apache Ant Manual — Zip Task](https://ant.apache.org/manual/Tasks/zip.html): lựa chọn tệp được đưa vào artifact.
- [Apache Ant Manual — EchoProperties Task](https://ant.apache.org/manual/Tasks/echoproperties.html): lý do cần thận trọng khi xuất toàn bộ property.
- [Apache Ant Manual — Running Ant](https://ant.apache.org/manual/running.html): `-D`, `-verbose`, `-debug`, `-logfile` và `-diagnostics`.
- [OWASP — Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): các nguyên tắc quản lý secret, cấp quyền, luân chuyển và vòng đời.
- [GitHub Actions — Using secrets in GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions): ví dụ về secret được cấp qua môi trường bước CI.

Một quy trình Ant an toàn không cần dạy buildfile cách “giữ kín” giá trị mật khẩu. **Buildfile chỉ mô tả công việc; môi trường được cấp quyền mới cung cấp secret cho bước thật sự cần dùng.** Kết hợp điều đó với allowlist khi đóng gói và quy tắc không in credential trong log sẽ ngăn ba đường rò rỉ phổ biến nhất: nguồn build, tệp phân phối và nhật ký.
