# Tách build, publish và deploy thành các thao tác tường minh

Trong một dự án Java, việc biên dịch và đóng gói ứng dụng chỉ là một phần của quá trình đưa phần mềm đến người dùng. Sau khi tạo được JAR hoặc WAR, nhóm còn phải lưu artifact vào nơi phân phối chung và triển khai đúng phiên bản đến môi trường chạy như development, staging hoặc production.

Ba hoạt động này có mục tiêu và tác động khác nhau:

- **Build:** biên dịch, kiểm thử và tạo artifact từ mã nguồn.
- **Publish:** đưa artifact đã tạo lên repository hoặc kho lưu trữ dùng chung để các hệ thống khác có thể lấy về.
- **Deploy:** lấy một phiên bản artifact đã được chọn và đưa nó vào môi trường chạy, chẳng hạn cài đặt lên máy chủ hoặc cập nhật dịch vụ.

Apache Ant cho phép biểu diễn từng hoạt động bằng target riêng. Khi tách chúng rõ ràng, lập trình viên có thể build nhiều lần mà không vô tình phát hành hoặc thay đổi môi trường đang chạy. Hệ thống CI cũng có thể kiểm soát quyền, điều kiện và lịch sử của từng bước.

Sau bài học, bạn có thể:

- Phân biệt build, publish và deploy.
- Tạo target Ant riêng cho từng thao tác.
- Tổ chức artifact và phiên bản phát hành nhất quán.
- Publish JAR lên repository bằng Apache Ivy hoặc cơ chế phân phối phù hợp.
- Deploy một phiên bản đã publish bằng công cụ triển khai của môi trường.
- Kiểm tra đầu vào, môi trường và phiên bản trước khi thực hiện thao tác có tác động.
- Thiết kế target tổng hợp tùy chọn mà vẫn giữ từng thao tác có thể gọi riêng.
- Tích hợp các bước vào pipeline CI/CD và hỗ trợ rollback.

## 1. Phân biệt build, publish và deploy

Ba từ này thường được dùng trong cùng một quy trình nhưng không nên xem chúng là một thao tác duy nhất.

| Hoạt động | Câu hỏi cần trả lời | Đầu ra hoặc tác động |
|---|---|---|
| Build | Mã nguồn có biên dịch, kiểm thử và đóng gói được không? | Artifact cục bộ, ví dụ `sample-app-1.4.0.jar`. |
| Publish | Artifact nào được đưa vào repository để người khác sử dụng? | Một phiên bản artifact được lưu trong kho phân phối. |
| Deploy | Phiên bản nào được cài đặt hoặc kích hoạt ở môi trường nào? | Ứng dụng được cập nhật trên môi trường chạy. |

Có thể hình dung luồng dữ liệu như sau:

```text
Mã nguồn
   |
   v
 BUILD
   |  compile + test + package
   v
Artifact cục bộ
   |
   v
 PUBLISH
   |  upload/copy vào repository
   v
Artifact đã phát hành
   |
   v
 DEPLOY
   |  lấy đúng version và cài vào môi trường
   v
Ứng dụng đang chạy
```

Build thường là hoạt động lặp lại trong quá trình phát triển. Publish và deploy thường có phạm vi tác động rộng hơn: publish thay đổi nội dung repository; deploy có thể thay đổi dịch vụ mà người dùng đang truy cập.

### 1.1. Build tạo artifact

Build là quá trình chuyển mã nguồn và tài nguyên thành sản phẩm có thể phân phối. Một target `build` thường gọi các bước:

1. Chuẩn bị thư mục đầu ra.
2. Biên dịch mã nguồn Java.
3. Biên dịch và chạy kiểm thử.
4. Kiểm tra chất lượng mã nếu dự án yêu cầu.
5. Sao chép tài nguyên.
6. Đóng gói JAR, WAR hoặc ZIP.
7. Tạo metadata hoặc checksum nếu cần.

Artifact thường nằm trong thư mục như `build/dist` hoặc `dist`. Build không cần ghi lên repository dùng chung và không cần kết nối đến máy chủ triển khai.

### 1.2. Publish đưa artifact vào repository

Publish là bước lưu artifact đã tạo vào một nơi có thể truy cập chung. Tùy loại dự án, repository có thể là:

- Ivy repository.
- Maven repository hoặc repository manager nội bộ.
- Kho artifact của hệ thống CI.
- Registry dành cho container image.
- Kho file phát hành của tổ chức.

Khi publish một thư viện Java, repository thường lưu cả artifact và metadata để dự án khác có thể khai báo dependency theo tọa độ module và phiên bản.

Publish không có nghĩa ứng dụng đã được cài lên server. Một JAR có thể đã được publish nhưng chưa được deploy ở bất kỳ môi trường nào.

### 1.3. Deploy đưa một phiên bản vào môi trường chạy

Deploy sử dụng artifact đã được chọn để cập nhật môi trường đích. Công việc cụ thể phụ thuộc cách ứng dụng được vận hành:

- Chép JAR lên máy chủ và khởi động lại service.
- Cập nhật WAR trong application server.
- Cập nhật image tag của một workload container.
- Gọi API của nền tảng cloud hoặc hệ thống orchestration.
- Cài đặt gói phát hành qua công cụ triển khai nội bộ.

Deploy cần biết ít nhất artifact/version và môi trường đích. Nó cũng thường cần cấu hình, thông tin xác thực và quyền truy cập phù hợp. Những thông tin này nên đến từ môi trường CI hoặc secret store, không nên viết cố định vào buildfile.

## 2. Vì sao cần tách ba thao tác?

Nếu target mặc định vừa build, vừa publish, vừa deploy, một lệnh Ant đơn giản có thể tạo ra thay đổi ngoài dự kiến. Ví dụ, lập trình viên chỉ muốn kiểm tra mã nguồn nhưng lại vô tình đưa JAR lên repository hoặc cập nhật môi trường staging.

Tách target giúp:

- **Giảm tác động ngoài ý muốn:** `ant build` chỉ tạo artifact cục bộ.
- **Kiểm soát quyền:** tài khoản build có thể chỉ cần quyền đọc dependency; tài khoản publish mới cần quyền ghi repository; tài khoản deploy cần quyền cập nhật môi trường.
- **Dễ điều tra:** có thể xác định lỗi xảy ra trong biên dịch, upload artifact hay triển khai.
- **Dễ chạy lại:** khi publish gặp lỗi mạng, có thể chạy lại publish với artifact đã build mà không nhất thiết biên dịch lại.
- **Hỗ trợ promotion:** cùng một artifact có thể được triển khai lần lượt lên staging và production.
- **Hỗ trợ rollback:** có thể chọn lại phiên bản artifact đã phát hành trước đó.
- **Tích hợp CI rõ ràng:** mỗi giai đoạn có điều kiện và bước phê duyệt riêng.

Một nguyên tắc hữu ích là build một lần cho một phiên bản phát hành, sau đó publish và promote chính artifact đó qua các môi trường. Không nên build lại mã nguồn riêng cho từng môi trường nếu điều đó làm thay đổi nội dung artifact; cấu hình môi trường nên được cung cấp ở thời điểm deploy khi kiến trúc ứng dụng cho phép.

## 3. Tổ chức thư mục và định danh artifact

Một cấu trúc đơn giản:

```text
sample-app/
├── build.xml
├── ivy.xml
├── ivysettings.xml
├── src/
│   └── main/java/
├── config/
│   └── deploy/
└── build/
    ├── classes/
    ├── test-classes/
    └── dist/
        ├── sample-app-1.4.0.jar
        └── sample-app-1.4.0.jar.sha256
```

Thư mục `build` chứa đầu ra tạm có thể tạo lại. Repository phát hành nên nằm ngoài thư mục build để target `clean` không xóa các artifact đã publish.

### 3.1. Dùng property cho tên và phiên bản

Khai báo các giá trị dùng chung ở đầu buildfile:

```xml
<property name="module.name" value="sample-app" />
<property name="release.version" value="1.4.0" />
<property name="build.dir" location="build" />
<property name="dist.dir" location="${build.dir}/dist" />
<property name="artifact.file"
          location="${dist.dir}/${module.name}-${release.version}.jar" />
```

Khi muốn build phiên bản khác, truyền property từ dòng lệnh:

```bash
ant -Drelease.version=1.4.1 build
```

Property Ant là bất biến sau khi được đặt. Giá trị truyền bằng `-D` có sẵn trước khi buildfile đặt giá trị mặc định cùng tên, nên nó được giữ lại.

### 3.2. Phiên bản phát hành nên ổn định

Artifact cần có định danh rõ ràng, thường gồm tên module và version. Ví dụ:

```text
sample-app-1.4.0.jar
sample-app-1.4.1.jar
sample-app-1.5.0.jar
```

Với release chính thức, nên coi một version là bất biến sau khi publish. Nếu cần sửa lỗi, tạo version mới thay vì âm thầm ghi đè JAR đã phát hành. Điều này giúp checksum, dependency resolution và lịch sử deploy có ý nghĩa.

Trong quá trình phát triển, có thể dùng version snapshot hoặc build number theo quy ước repository. Cần thống nhất quy tắc để không nhầm artifact thử nghiệm với release chính thức.

## 4. Thiết kế target `build` trong Ant

Target `build` nên tạo artifact cục bộ và trả về trạng thái thành công/thất bại của các bước bắt buộc. Nó không nên tự động publish hoặc deploy.

Ví dụ tối giản:

```xml
<project name="sample-app" default="build" basedir=".">
    <property name="module.name" value="sample-app" />
    <property name="release.version" value="1.4.0" />
    <property name="src.dir" location="src/main/java" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="dist.dir" location="${build.dir}/dist" />
    <property name="artifact.file"
              location="${dist.dir}/${module.name}-${release.version}.jar" />

    <target name="init">
        <mkdir dir="${classes.dir}" />
        <mkdir dir="${dist.dir}" />
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false" />
    </target>

    <target name="package" depends="compile">
        <jar destfile="${artifact.file}"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Implementation-Title" value="${module.name}" />
                <attribute name="Implementation-Version" value="${release.version}" />
            </manifest>
        </jar>
    </target>

    <target name="build" depends="package">
        <checksum file="${artifact.file}"
                  algorithm="SHA-256"
                  fileext=".sha256" />
        <echo message="Built ${artifact.file}" />
    </target>
</project>
```

Trong ví dụ:

- `init` tạo thư mục đầu ra.
- `compile` biên dịch mã nguồn.
- `package` tạo JAR có manifest chứa tên và phiên bản.
- `build` tạo checksum SHA-256 sau khi JAR được tạo.
- `default="build"` khiến lệnh `ant` chỉ thực hiện build cục bộ.

Trong dự án thực tế, target `build` thường còn phụ thuộc vào target kiểm thử và các kiểm tra bắt buộc. Có thể mở rộng thành `build depends="test,package"` hoặc để `package` phụ thuộc `test`, tùy cách tổ chức dependency của dự án.

### 4.1. Kiểm tra artifact sau build

Sau khi build, cần biết chính xác tệp nào sẽ được publish. Có thể kiểm tra sự tồn tại trước khi chạy bước tiếp theo:

```xml
<available file="${artifact.file}" property="artifact.exists" />
<fail unless="artifact.exists"
      message="Artifact was not created: ${artifact.file}" />
```

Task `<available>` đặt property nếu tệp tồn tại; `<fail>` dừng build nếu điều kiện không đạt. Cách này hữu ích ở target publish để tránh upload một đường dẫn rỗng hoặc artifact cũ không đúng version.

### 4.2. Vì sao build nên độc lập với môi trường deploy?

Build không nên cần địa chỉ server production hoặc mật khẩu triển khai. Nó nên có thể chạy trên máy phát triển và CI với quyền tối thiểu để lấy dependency và ghi đầu ra cục bộ.

Nếu artifact phải thay đổi theo môi trường, hãy xem xét chuyển cấu hình sang biến môi trường, tệp cấu hình được cung cấp khi deploy hoặc hệ thống quản lý cấu hình. Điều này giúp cùng một JAR có thể được kiểm thử ở staging rồi promote lên production.

## 5. Thiết kế target `publish`

Target `publish` đưa artifact đã build vào repository. Nó cần biết:

- Artifact nào sẽ publish.
- Module và version nào được gắn cho artifact.
- Repository đích và resolver nào được dùng.
- Chính sách ghi đè hoặc từ chối version đã tồn tại.
- Thông tin xác thực được cung cấp an toàn như thế nào.

Với Ant, Apache Ivy có thể publish module và artifact lên một repository Ivy. Nếu dự án dùng Maven repository manager hoặc hệ thống artifact khác, hãy dùng cơ chế publish được repository đó hỗ trợ, chẳng hạn Maven Deploy Plugin, CLI hoặc API của repository manager.

### 5.1. Mô tả artifact trong `ivy.xml`

Ví dụ `ivy.xml` tối giản:

```xml
<ivy-module version="2.0">
    <info organisation="com.example"
          module="sample-app" />

    <configurations>
        <conf name="default" visibility="public" />
    </configurations>

    <publications>
        <artifact name="sample-app"
                  type="jar"
                  ext="jar"
                  conf="default" />
    </publications>
</ivy-module>
```

`organisation` và `module` định danh module. Phần `<publications>` mô tả artifact JAR mà module cung cấp. Revision phát hành có thể được cung cấp bởi target Ivy publish thông qua `pubrevision`.

### 5.2. Cấu hình repository Ivy

Để thực hành cục bộ, có thể dùng filesystem resolver. Ví dụ `ivysettings.xml`:

```xml
<ivysettings>
    <settings defaultResolver="company-release" />

    <resolvers>
        <filesystem name="company-release">
            <ivy pattern="${user.home}/.ivy2/company-release/[organisation]/[module]/[revision]/ivy.xml" />
            <artifact pattern="${user.home}/.ivy2/company-release/[organisation]/[module]/[revision]/[artifact]-[revision].[ext]" />
        </filesystem>
    </resolvers>
</ivysettings>
```

Resolver này ghi artifact vào một repository trên hệ thống tệp của người dùng, phù hợp để học cách publish. Với môi trường dùng chung, hãy thay bằng repository/resolver nội bộ có chính sách ghi, xác thực và lưu trữ phù hợp. Không coi thư mục cache cá nhân là repository phát hành chính thức.

### 5.3. Target publish bằng Ivy

Trong `build.xml`, khai báo namespace Ivy và target publish:

```xml
<project name="sample-app" default="build"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="module.name" value="sample-app" />
    <property name="release.version" value="1.4.0" />
    <property name="dist.dir" location="build/dist" />
    <property name="artifact.file"
              location="${dist.dir}/${module.name}-${release.version}.jar" />

    <target name="publish">
        <available file="${artifact.file}" property="artifact.exists" />
        <fail unless="artifact.exists"
              message="Build the artifact before publishing: ${artifact.file}" />

        <ivy:settings file="ivysettings.xml" />
        <ivy:publish resolver="company-release"
                     pubrevision="${release.version}"
                     status="release"
                     overwrite="false">
            <artifacts pattern="${dist.dir}/[artifact]-[revision].[ext]" />
        </ivy:publish>
    </target>
</project>
```

Target `publish` không phụ thuộc `build`. Vì vậy, khi gọi `ant publish`, Ant yêu cầu artifact của version đó phải tồn tại từ trước. Nếu chưa build, target dừng với thông báo rõ ràng.

Việc tách này cho phép quy trình thực hiện hai lệnh riêng:

```bash
ant -Drelease.version=1.4.0 build
ant -Drelease.version=1.4.0 publish
```

Trong cùng một lần chạy Ant, property chỉ được đặt một lần. Khi chạy thành hai tiến trình riêng, hãy truyền cùng version ở cả hai lệnh để target publish chọn đúng artifact đã build.

### 5.4. Publish không nên ghi đè release đã tồn tại

Với release chính thức, `overwrite="false"` thể hiện chính sách không ghi đè artifact cùng version nếu repository đã có. Nếu cần sửa nội dung, hãy tạo revision mới theo quy ước phát hành.

Điều này quan trọng vì hệ thống khác có thể đã tải artifact cũ, checksum cũ hoặc đã triển khai version đó. Ghi đè âm thầm khiến cùng một tọa độ module/version có thể đại diện cho nội dung khác nhau ở các máy.

### 5.5. Publish lên Maven repository hoặc kho nội bộ

Không phải repository nào cũng hỗ trợ giao thức publish của Ivy. Một Maven repository manager có thể yêu cầu Maven Deploy Plugin, một CLI riêng hoặc API upload. Khi đó, target `publish` vẫn giữ nguyên vai trò nhưng gọi công cụ phù hợp:

```xml
<target name="publish-maven" >
    <available file="${artifact.file}" property="artifact.exists" />
    <fail unless="artifact.exists"
          message="Artifact does not exist: ${artifact.file}" />

    <exec executable="repository-cli" failonerror="true">
        <arg value="upload" />
        <arg value="--repository" />
        <arg value="${release.repository}" />
        <arg value="--file" />
        <arg value="${artifact.file}" />
        <arg value="--version" />
        <arg value="${release.version}" />
    </exec>
</target>
```

`repository-cli` ở đây là tên minh họa cho công cụ của repository manager. Hãy thay bằng lệnh thật của hệ thống đang dùng và cấu hình xác thực bằng cơ chế an toàn của môi trường build.

## 6. Thiết kế target `deploy`

Deploy sử dụng một artifact đã được publish và đưa nó đến môi trường chạy. Target cần nhận version cụ thể và môi trường đích rõ ràng.

Ví dụ cách gọi:

```bash
ant -Drelease.version=1.4.0 -Ddeploy.environment=staging deploy
```

Lệnh này yêu cầu triển khai version `1.4.0` lên `staging`. Target deploy không nên tự build hoặc publish một phiên bản mới, vì điều đó làm khó xác định chính xác artifact đang được cài đặt.

### 6.1. Kiểm tra tham số trước khi deploy

Có thể dùng `<fail>` và `<condition>` để xác nhận môi trường được phép:

```xml
<target name="deploy">
    <fail unless="release.version"
          message="Set -Drelease.version to the version to deploy." />
    <fail unless="deploy.environment"
          message="Set -Ddeploy.environment to staging or production." />

    <condition property="deploy.environment.valid">
        <or>
            <equals arg1="${deploy.environment}" arg2="staging" />
            <equals arg1="${deploy.environment}" arg2="production" />
        </or>
    </condition>

    <fail unless="deploy.environment.valid"
          message="Unsupported deployment environment: ${deploy.environment}" />

    <!-- Gọi công cụ triển khai ở bước tiếp theo. -->
</target>
```

`unless` kiểm tra sự tồn tại của property, không kiểm tra nội dung có phải chuỗi `true` hay không. Vì vậy, ví dụ dùng `<condition>` để xác nhận giá trị môi trường nằm trong danh sách cho phép.

### 6.2. Gọi công cụ triển khai từ Ant

Ant không có một task deploy chung cho mọi nền tảng. Cách triển khai phụ thuộc ứng dụng chạy trên máy chủ Java, container platform, cloud service hay hệ thống nội bộ.

Có thể gọi CLI của nền tảng bằng task `<exec>`:

```xml
<target name="deploy">
    <fail unless="release.version"
          message="Set -Drelease.version before deployment." />
    <fail unless="deploy.environment"
          message="Set -Ddeploy.environment before deployment." />

    <exec executable="deploy-cli" failonerror="true">
        <arg value="deploy" />
        <arg value="--module" />
        <arg value="${module.name}" />
        <arg value="--version" />
        <arg value="${release.version}" />
        <arg value="--environment" />
        <arg value="${deploy.environment}" />
    </exec>
</target>
```

`deploy-cli` là placeholder. Công cụ thật cần có khả năng lấy đúng module/version từ repository và triển khai nó đến môi trường được chỉ định. Tách từng đối số thành phần tử `<arg>` giúp Ant truyền tham số riêng biệt, giảm rủi ro do khoảng trắng trong đường dẫn.

Một công cụ triển khai có thể thực hiện các bước như:

1. Tải artifact đúng version từ repository.
2. Kiểm tra checksum hoặc chữ ký nếu quy trình yêu cầu.
3. Đưa artifact vào vị trí triển khai.
4. Cập nhật cấu hình runtime từ nguồn cấu hình của môi trường.
5. Khởi động hoặc cập nhật service.
6. Chờ health check và trả mã thoát phù hợp.

Ant nhận mã thoát từ công cụ. Với `failonerror="true"`, lệnh triển khai trả mã lỗi sẽ làm target thất bại.

### 6.3. Deploy không nên tự động publish

Trong ví dụ, target `deploy` không phụ thuộc `publish`. Nó nhận version đã được publish và yêu cầu công cụ triển khai lấy version đó từ repository.

Điều này tạo ra ranh giới rõ ràng:

- `ant build`: tạo artifact cục bộ.
- `ant publish`: đưa artifact đã tạo vào repository.
- `ant deploy`: triển khai một version đã có trong repository.

Nếu `deploy` tự gọi `publish`, người vận hành có thể vô tình phát hành một artifact mới trong lúc chỉ định cập nhật môi trường. Việc tách target cho phép CI áp dụng quyền và bước phê duyệt riêng cho publish và deploy.

## 7. Target mặc định và target tổng hợp

Thuộc tính `default` của phần tử `<project>` quyết định target chạy khi gọi `ant` mà không ghi tên. Nên đặt target mặc định là một thao tác an toàn, thường là `build`.

```xml
<project name="sample-app" default="build">
    <!-- Các target được khai báo ở đây. -->
</project>
```

Khi đó:

| Lệnh | Hoạt động |
|---|---|
| `ant` | Chạy target mặc định `build`. |
| `ant build` | Chỉ build artifact và các phụ thuộc cần thiết. |
| `ant publish` | Publish artifact đã được build trước đó. |
| `ant deploy -Drelease.version=1.4.0 -Ddeploy.environment=staging` | Deploy version đã publish lên staging. |

Nếu muốn có một lệnh chạy cả chuỗi, hãy tạo target tổng hợp có tên rõ ràng:

```xml
<target name="release" depends="build,publish,deploy" />
```

Target `release` là thao tác opt-in. Khi gọi `ant release`, Ant chạy các dependency theo thứ tự khai báo: `build`, rồi `publish`, rồi `deploy`. Khi gọi `ant` hoặc `ant build`, hai thao tác có tác động ra bên ngoài không tự chạy.

Target tổng hợp phù hợp với pipeline đã được cấu hình đầy đủ. Với production, có thể tách `deploy-staging` và `deploy-production`, hoặc để hệ thống CI yêu cầu bước phê duyệt trước target deploy production.

## 8. Ví dụ buildfile hoàn chỉnh

Ví dụ dưới đây minh họa ba target độc lập và một target tổng hợp tùy chọn. Repository Ivy trong ví dụ là filesystem repository phục vụ học tập; thay bằng repository thật của tổ chức khi triển khai.

```xml
<project name="sample-app" default="build"
         xmlns:ivy="antlib:org.apache.ivy.ant"
         basedir=".">

    <property name="module.name" value="sample-app" />
    <property name="release.version" value="1.4.0" />
    <property name="src.dir" location="src/main/java" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="dist.dir" location="${build.dir}/dist" />
    <property name="artifact.file"
              location="${dist.dir}/${module.name}-${release.version}.jar" />

    <target name="init">
        <mkdir dir="${classes.dir}" />
        <mkdir dir="${dist.dir}" />
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false" />
    </target>

    <target name="package" depends="compile">
        <jar destfile="${artifact.file}"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Implementation-Title" value="${module.name}" />
                <attribute name="Implementation-Version" value="${release.version}" />
            </manifest>
        </jar>
    </target>

    <!-- Build chỉ tạo artifact cục bộ. -->
    <target name="build" depends="package">
        <checksum file="${artifact.file}"
                  algorithm="SHA-256"
                  fileext=".sha256" />
        <echo message="Built ${artifact.file}" />
    </target>

    <!-- Publish yêu cầu artifact đã tồn tại; không tự gọi build. -->
    <target name="publish">
        <available file="${artifact.file}" property="artifact.exists" />
        <fail unless="artifact.exists"
              message="Run build before publish: ${artifact.file}" />

        <ivy:settings file="ivysettings.xml" />
        <ivy:publish resolver="company-release"
                     pubrevision="${release.version}"
                     status="release"
                     overwrite="false">
            <artifacts pattern="${dist.dir}/[artifact]-[revision].[ext]" />
        </ivy:publish>
    </target>

    <!-- Deploy lấy version đã publish; không build hoặc publish ngầm. -->
    <target name="deploy">
        <fail unless="release.version"
              message="Set -Drelease.version to the published version." />
        <fail unless="deploy.environment"
              message="Set -Ddeploy.environment to staging or production." />

        <condition property="deploy.environment.valid">
            <or>
                <equals arg1="${deploy.environment}" arg2="staging" />
                <equals arg1="${deploy.environment}" arg2="production" />
            </or>
        </condition>
        <fail unless="deploy.environment.valid"
              message="Unsupported environment: ${deploy.environment}" />

        <exec executable="deploy-cli" failonerror="true">
            <arg value="deploy" />
            <arg value="--module" />
            <arg value="${module.name}" />
            <arg value="--version" />
            <arg value="${release.version}" />
            <arg value="--environment" />
            <arg value="${deploy.environment}" />
        </exec>
    </target>

    <!-- Chỉ chạy khi người gọi chủ động yêu cầu cả chuỗi. -->
    <target name="release" depends="build,publish,deploy" />

    <target name="clean">
        <delete dir="${build.dir}" />
    </target>
</project>
```

Tệp `ivy.xml`:

```xml
<ivy-module version="2.0">
    <info organisation="com.example"
          module="sample-app" />

    <configurations>
        <conf name="default" visibility="public" />
    </configurations>

    <publications>
        <artifact name="sample-app"
                  type="jar"
                  ext="jar"
                  conf="default" />
    </publications>
</ivy-module>
```

Tệp `ivysettings.xml` dùng filesystem repository cho bài thực hành:

```xml
<ivysettings>
    <settings defaultResolver="company-release" />
    <resolvers>
        <filesystem name="company-release">
            <ivy pattern="${user.home}/.ivy2/company-release/[organisation]/[module]/[revision]/ivy.xml" />
            <artifact pattern="${user.home}/.ivy2/company-release/[organisation]/[module]/[revision]/[artifact]-[revision].[ext]" />
        </filesystem>
    </resolvers>
</ivysettings>
```

Các target có thể gọi riêng:

```bash
# Tạo JAR và checksum ở máy build
ant -Drelease.version=1.4.0 build

# Đưa version 1.4.0 vào repository Ivy
ant -Drelease.version=1.4.0 publish

# Triển khai version đã publish lên staging
ant -Drelease.version=1.4.0 -Ddeploy.environment=staging deploy
```

`deploy-cli` là lệnh minh họa và cần được thay bằng công cụ triển khai thực tế. Ví dụ cũng giả định Ivy đã được cài và Ant có thể nạp task Ivy. Nếu repository là Maven repository manager hoặc dịch vụ artifact khác, thay target publish bằng cơ chế upload phù hợp.

## 9. Giữ artifact nhất quán giữa các môi trường

Một cách làm quan trọng trong phát hành là build một lần, sau đó promote cùng artifact qua các môi trường.

Ví dụ:

```text
Build version 1.4.0
        |
        v
Publish sample-app:1.4.0
        |
        v
Deploy sample-app:1.4.0 -> staging
        |
        +-- kiểm thử chấp nhận
        |
        v
Deploy sample-app:1.4.0 -> production
```

Staging và production nhận cùng tọa độ module/version. Điều thay đổi giữa các môi trường thường là cấu hình runtime, secret, endpoint, số replica hoặc thông số vận hành.

Nếu build riêng một JAR cho staging và một JAR khác cho production, rất khó chứng minh sản phẩm đã được kiểm thử ở staging chính là sản phẩm đang chạy production. Giữ artifact bất biến giúp quá trình promotion đáng tin cậy hơn.

### 9.1. Ghi nhận checksum

Checksum giúp xác nhận artifact lấy từ repository hoặc chuyển qua mạng có cùng nội dung với artifact đã build.

Ant có task `<checksum>`:

```xml
<checksum file="${artifact.file}"
          algorithm="SHA-256"
          fileext=".sha256" />
```

Tùy repository và công cụ deploy, checksum có thể được lưu cạnh artifact hoặc được cung cấp dưới dạng metadata. Công cụ nhận artifact nên xác minh checksum theo quy trình của tổ chức trước khi cài đặt.

Checksum phát hiện sự khác biệt nội dung; nó không tự chứng minh nguồn gốc hoặc tính xác thực của artifact. Nếu cần xác minh nguồn phát hành, có thể bổ sung chữ ký số và kiểm tra chữ ký bằng công cụ phù hợp.

### 9.2. Gắn metadata phát hành

Ngoài tên tệp, có thể ghi version vào manifest của JAR:

```xml
<jar destfile="${artifact.file}" basedir="${classes.dir}">
    <manifest>
        <attribute name="Implementation-Title" value="${module.name}" />
        <attribute name="Implementation-Version" value="${release.version}" />
        <attribute name="Build-Jdk" value="${java.version}" />
    </manifest>
</jar>
```

Metadata giúp điều tra artifact đang chạy. Hãy chỉ ghi thông tin cần thiết và tránh đưa secret hoặc dữ liệu nội bộ nhạy cảm vào manifest.

## 10. Cấu hình môi trường và thông tin xác thực

Deploy thường cần cấu hình khác nhau giữa các môi trường. Ví dụ:

| Thuộc tính | Development | Staging | Production |
|---|---|---|---|
| `deploy.environment` | `dev` | `staging` | `production` |
| API endpoint | Máy hoặc dịch vụ phát triển | Endpoint kiểm thử tích hợp | Endpoint production |
| Database | Cơ sở dữ liệu dev | Cơ sở dữ liệu staging | Cơ sở dữ liệu production |
| Quyền triển khai | Nhóm phát triển | CI hoặc nhóm release | Tài khoản có kiểm soát và phê duyệt |

Không nên nhúng endpoint, mật khẩu hoặc token vào artifact nếu có thể cung cấp chúng khi deploy. Artifact nên chứa ứng dụng; cấu hình môi trường được lấy từ nguồn cấu hình phù hợp với môi trường đích.

### 10.1. Đọc cấu hình môi trường

Ant có thể đọc biến môi trường bằng task `<property environment="env" />`:

```xml
<property environment="env" />

<target name="deploy">
    <fail unless="env.DEPLOY_ENV"
          message="Environment variable DEPLOY_ENV is required." />
    <echo message="Deploying to ${env.DEPLOY_ENV}" />
</target>
```

Ví dụ này chỉ minh họa cách đọc biến môi trường. Công cụ triển khai thực tế có thể đọc trực tiếp credential từ environment hoặc secret provider. Tránh truyền secret qua đối số dòng lệnh nếu công cụ có cách đọc an toàn hơn, vì đối số có thể xuất hiện trong process list hoặc log.

### 10.2. Tách quyền build, publish và deploy

Trong CI, có thể dùng các credential hoặc service account riêng:

- Job build chỉ cần quyền đọc dependency và ghi artifact của job.
- Job publish có quyền ghi vào repository phát hành.
- Job deploy staging có quyền cập nhật staging.
- Job deploy production có quyền production và có thể yêu cầu phê duyệt riêng.

Việc tách quyền giảm tác động nếu một bước bị cấu hình sai hoặc một tài khoản bị lộ. Buildfile nên nhận thông tin cần thiết từ môi trường CI thay vì chứa credential cố định.

## 11. Thiết kế pipeline CI/CD tương ứng

Các target Ant là đơn vị công việc. CI/CD có thể gọi chúng trong các stage riêng:

```text
                 +----------------+
                 |   Checkout     |
                 +--------+-------+
                          |
                          v
                 +----------------+
                 |     BUILD      |
                 | compile/test   |
                 | package/check  |
                 +--------+-------+
                          |
                          v
                 +----------------+
                 |    PUBLISH     |
                 | upload version |
                 +--------+-------+
                          |
                          v
                 +----------------+
                 | DEPLOY STAGING |
                 +--------+-------+
                          |
                          v
                 +----------------+
                 | Acceptance test|
                 +--------+-------+
                          |
                          v
                 +----------------+
                 | Approval gate  |
                 +--------+-------+
                          |
                          v
                 +----------------+
                 | DEPLOY PROD    |
                 +----------------+
```

Ví dụ cách CI gọi Ant:

```bash
ant -Drelease.version=1.4.0 build
ant -Drelease.version=1.4.0 publish
ant -Drelease.version=1.4.0 -Ddeploy.environment=staging deploy
```

Sau khi staging đạt kiểm thử chấp nhận và bước phê duyệt hoàn tất:

```bash
ant -Drelease.version=1.4.0 -Ddeploy.environment=production deploy
```

CI cần lưu artifact và metadata của lần build. Khi publish hoặc deploy thất bại, có thể chạy lại đúng stage bằng cùng version thay vì tạo một artifact mới không cần thiết.

### 11.1. Điều kiện để promotion an toàn

Trước khi deploy production, pipeline thường cần xác nhận:

- Artifact version đã được publish.
- Checksum hoặc chữ ký hợp lệ theo chính sách.
- Test và quality gate bắt buộc đã thành công.
- Phiên bản đó đã được triển khai và kiểm tra ở staging.
- Có cấu hình đúng cho production.
- Người hoặc hệ thống có thẩm quyền đã cho phép thao tác.

Ant có thể kiểm tra một số điều kiện kỹ thuật bằng `<available>`, `<condition>` và `<fail>`. Việc phê duyệt và quản lý quyền thường do CI/CD hoặc hệ thống phát hành đảm nhiệm.

## 12. Rollback và khả năng khôi phục

Nếu phiên bản mới gây lỗi sau deploy, rollback thường là triển khai lại một phiên bản đã phát hành trước đó.

Ví dụ:

```bash
ant -Drelease.version=1.3.2 -Ddeploy.environment=production deploy
```

Đây là lý do artifact release nên bất biến và repository phải giữ lại các version cũ theo chính sách lưu trữ. Nếu version `1.3.2` vẫn tồn tại, hệ thống triển khai có thể lấy đúng artifact đó mà không cần build lại mã nguồn cũ.

Rollback không phải lúc nào cũng chỉ là đổi JAR. Nếu phiên bản mới đã thay đổi schema database hoặc dữ liệu trạng thái, cần có kế hoạch tương thích và khôi phục dữ liệu riêng. Buildfile có thể gọi migration/rollback tool, nhưng không nên giả định mọi thay đổi đều có thể đảo ngược tự động.

## 13. Các lỗi thường gặp khi tách build, publish và deploy

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `ant` vô tình publish hoặc deploy | Target mặc định gọi chuỗi release. | Đặt `default="build"`; chỉ gọi target có tác động khi chủ động yêu cầu. |
| Publish không tìm thấy artifact | Chưa chạy build, sai version hoặc sai đường dẫn. | Kiểm tra `artifact.file`, property version và target build. |
| Publish lấy nhầm JAR cũ | Tên tệp không gắn version hoặc thư mục đầu ra còn artifact cũ. | Đặt tên theo module/version và kiểm tra tệp trước khi publish. |
| Repository từ chối publish | Version đã tồn tại, credential sai hoặc không có quyền ghi. | Kiểm tra revision, chính sách overwrite và quyền repository. |
| Artifact đã publish nhưng deploy không tìm thấy | Deploy CLI dùng sai repository, module hoặc version. | Truyền cùng tọa độ release và kiểm tra cấu hình repository của deploy tool. |
| Deploy chạy nhầm môi trường | Property môi trường mặc định hoặc giá trị truyền vào sai. | Yêu cầu chỉ định môi trường, kiểm tra bằng `<condition>` và dùng CI environment protection. |
| Deploy vô tình build lại artifact | Target deploy phụ thuộc build hoặc publish. | Để deploy nhận version đã publish và không tạo artifact mới. |
| Staging và production chạy artifact khác nhau | Build lại riêng cho từng môi trường. | Build một lần, publish một version rồi promote cùng artifact. |
| Deploy báo thành công nhưng service không hoạt động | CLI chỉ upload mà không kiểm tra health hoặc restart. | Bổ sung health check và xác nhận trạng thái ứng dụng sau triển khai. |
| Không thể rollback | Artifact cũ bị ghi đè hoặc đã bị xóa. | Dùng version bất biến và chính sách lưu trữ artifact phù hợp. |
| Secret xuất hiện trong log | Credential được truyền trực tiếp qua đối số hoặc echo. | Dùng secret provider/credential helper và tránh in giá trị nhạy cảm. |
| Publish hoặc deploy thất bại nhưng build lại làm thay đổi artifact | Artifact không được lưu hoặc quy trình không giữ đúng đầu ra của lần build. | Lưu artifact như CI artifact, ghi checksum và chạy lại stage trên cùng version. |

## 14. Các lệnh Ant thường dùng trong quy trình phát hành

| Lệnh | Mục đích |
|---|---|
| `ant` | Chạy target mặc định, nên là build cục bộ. |
| `ant clean` | Xóa đầu ra build cục bộ. |
| `ant build` | Biên dịch, kiểm thử và tạo artifact theo cấu hình dự án. |
| `ant publish` | Đưa artifact đã build vào repository. |
| `ant deploy -Drelease.version=1.4.0 -Ddeploy.environment=staging` | Deploy version cụ thể lên staging. |
| `ant release -Drelease.version=1.4.0 -Ddeploy.environment=staging` | Chạy target tổng hợp build, publish và deploy nếu dự án chủ động khai báo. |

Tên target là quy ước của dự án. Điều quan trọng là mô tả rõ tác động của từng target trong `description` và tài liệu build để người vận hành biết lệnh nào chỉ tạo đầu ra cục bộ, lệnh nào ghi repository và lệnh nào thay đổi môi trường chạy.

## 15. Bài thực hành

Tạo dự án có cấu trúc:

```text
release-lab/
├── build.xml
├── ivy.xml
├── ivysettings.xml
└── src/main/java/com/example/Hello.java
```

Tệp `Hello.java`:

```java
package com.example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from release pipeline");
    }
}
```

Thực hiện các yêu cầu:

1. Khai báo `module.name`, `release.version`, `build.dir`, `dist.dir` và `artifact.file`.
2. Tạo target `init`, `compile`, `package` và `build`.
3. Đặt `default="build"` và xác nhận `ant` không publish hoặc deploy.
4. Tạo `ivy.xml` mô tả module và artifact JAR.
5. Cấu hình filesystem repository trong `ivysettings.xml` để thực hành.
6. Tạo target `publish` kiểm tra artifact tồn tại rồi gọi `ivy:publish`.
7. Tạo target `deploy` yêu cầu version và environment, sau đó gọi một script triển khai giả lập hoặc CLI có sẵn trong môi trường học tập.
8. Bảo đảm `deploy` không phụ thuộc `build` hoặc `publish`.
9. Tạo target `release` tùy chọn phụ thuộc `build,publish,deploy`.
10. Tạo checksum và ghi version vào manifest của JAR.

Chạy lần lượt:

```bash
ant -Drelease.version=1.0.0 build
ant -Drelease.version=1.0.0 publish
ant -Drelease.version=1.0.0 -Ddeploy.environment=staging deploy
```

Sau đó thử:

- Gọi `ant publish` trước khi build và quan sát thông báo thiếu artifact.
- Gọi `ant deploy` mà không truyền môi trường và xác nhận target dừng trước khi gọi CLI.
- Publish lại cùng version để xem repository xử lý chính sách version đã tồn tại.
- Build version `1.0.1`, publish và deploy version mới.
- Deploy lại version `1.0.0` để mô phỏng rollback.
- Kiểm tra checksum của artifact được lưu ở mỗi version.

### Câu hỏi tự kiểm tra

1. Build khác publish ở đầu ra và tác động như thế nào?
2. Publish một JAR có đồng nghĩa ứng dụng đã được deploy không?
3. Vì sao target mặc định thường nên là `build`?
4. Tại sao target `deploy` nên nhận một version cụ thể?
5. Vì sao không nên để deploy tự động publish một artifact mới?
6. Làm thế nào để cùng một artifact được promote từ staging lên production?
7. Vì sao release version nên bất biến sau khi publish?
8. Checksum giúp ích gì trong quá trình phát hành?
9. Khi nào nên dùng target tổng hợp `release`?
10. Vì sao credential không nên được ghi trực tiếp trong buildfile?

### Đáp án gợi ý

- Build tạo artifact cục bộ; publish đưa artifact vào repository dùng chung.
- Không. Publish chỉ lưu artifact để có thể lấy về; deploy mới đưa artifact vào môi trường chạy.
- Để lệnh `ant` thông thường chỉ tạo đầu ra cục bộ và không gây tác động bên ngoài.
- Để xác định chính xác artifact cần cài đặt và hỗ trợ promotion/rollback.
- Vì người vận hành có thể chỉ muốn triển khai một version đã phát hành; publish ngầm làm ranh giới quyền và tác động không rõ ràng.
- Publish một version bất biến rồi deploy cùng tọa độ/version đến từng môi trường.
- Để cùng một module/version luôn đại diện cho cùng nội dung artifact.
- Checksum giúp xác nhận artifact nhận được có cùng nội dung với artifact đã tạo hoặc đã lưu.
- Khi người gọi chủ động muốn thực hiện toàn bộ chuỗi build, publish và deploy theo quy trình đã kiểm soát.
- Vì buildfile có thể được commit, chia sẻ hoặc ghi log; secret nên được cung cấp từ môi trường bảo mật.

## Kết luận

Trong Apache Ant, hãy biểu diễn build, publish và deploy bằng các target riêng. `build` tạo artifact cục bộ; `publish` đưa artifact có version cụ thể vào repository; `deploy` lấy một version đã publish và cập nhật môi trường chạy. Đặt target mặc định là build, kiểm tra đầu vào trước khi publish hoặc deploy, giữ artifact release bất biến và dùng cùng một artifact khi promotion giữa các môi trường. Nếu cần chạy cả chuỗi, tạo target tổng hợp rõ ràng để người vận hành chủ động yêu cầu. Cách tổ chức này giúp build dễ tái lập, phát hành có thể kiểm soát và triển khai có lịch sử rõ ràng.
