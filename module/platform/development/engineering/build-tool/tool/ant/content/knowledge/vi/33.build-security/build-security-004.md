# Kiểm tra tham số đầu vào trước thao tác xóa, ghi và phát hành trong Apache Ant

Apache Ant giúp tự động hóa các bước biên dịch, sao chép, xóa file, tạo gói và phát hành. Những bước này thường nhận cấu hình qua thuộc tính (property), tham số dòng lệnh hoặc biến môi trường. Nếu một tham số sai được chuyển thẳng vào thao tác có tác động đến dữ liệu, hậu quả có thể lớn hơn một lần build thất bại: xóa nhầm thư mục, ghi đè đầu ra, đưa sai artifact lên nơi phát hành hoặc công bố một phiên bản chưa được kiểm tra.

Trong chủ đề **an toàn build**, kiểm tra tham số đầu vào là việc biến các giả định thành điều kiện rõ ràng **trước khi** chạy target nguy hiểm. Một buildfile tốt cần xác định: tham số nào bắt buộc, giá trị nào được phép, đường dẫn nào có thể ghi/xóa, sản phẩm nào được phát hành, và khi không thỏa điều kiện thì build phải dừng ở đâu.

Bài học này sử dụng các task có sẵn của Apache Ant như `<property>`, `<condition>`, `<fail>`, `<available>` và `<echo>` để xây dựng các bước kiểm tra thực tế. Các ví dụ ưu tiên cấu hình theo lựa chọn được cho phép (allowlist) và đường dẫn đích cố định, vì đây là cách hạn chế sai sót đơn giản hơn việc chấp nhận mọi đường dẫn tự do.

## 1. Các đầu vào dễ gây rủi ro

Một target có thể nhận tham số từ nhiều nguồn:

| Nguồn đầu vào | Ví dụ | Nguy cơ nếu dùng ngay |
| --- | --- | --- |
| Tham số dòng lệnh `-D` | `-Doutput.dir=...` | Ghi hoặc xóa vào thư mục ngoài dự kiến |
| Property trong `build.xml` | `<property name="release.channel" value="prod"/>` | Giá trị mặc định vô tình dùng cho môi trường quan trọng |
| File property bên ngoài | `<property file="local.properties"/>` | Giá trị cũ hoặc giá trị của máy khác |
| Biến môi trường | `env.DEPLOY_HOST`, `env.PUBLISH_DIR` | Nhầm máy chủ, đường dẫn hoặc tài khoản |
| Kết quả từ task trước | Tên artifact, version, thư mục staging | Truyền tiếp dữ liệu chưa được xác nhận |
| Lệnh hoặc file script | `<exec>` nhận executable và đối số | Chạy nhầm công cụ hoặc truyền đối số nguy hiểm |

Đặc biệt, các task như `<delete>`, `<copy>`, `<move>`, `<replace>`, `<echo file="...">`, `<zip>`, `<jar>` và công cụ phát hành bên ngoài có thể gây thay đổi dữ liệu. Cách kiểm tra nên phụ thuộc vào **tác động của thao tác**, không chỉ vào việc property có được khai báo hay không.

Ví dụ dễ gây nhầm lẫn:

```xml
<project name="unsafe" default="clean">
    <property name="cleanup.dir" value="build"/>
    <target name="clean">
        <delete dir="${cleanup.dir}"/>
    </target>
</project>
```

Người dùng có thể truyền `-Dcleanup.dir=...` khi chạy. Trong Ant, property thường không bị ghi đè sau khi đã có giá trị, và user property từ `-D` có mức ưu tiên cao; vì vậy giá trị truyền vào có thể quyết định thư mục được xóa. Tham số chưa qua kiểm tra sẽ ảnh hưởng trực tiếp đến `<delete>`.

Thay vì để người gọi chỉ định một đường dẫn xóa bất kỳ, nên định nghĩa rõ **loại dọn dẹp được hỗ trợ**, sau đó map lựa chọn đó tới một thư mục cố định bên trong project.

## 2. Hiểu cơ chế property trước khi đặt điều kiện

Trong Ant, property thường có tính chất **được đặt một lần**: sau khi có giá trị, lệnh đặt property tiếp theo thường không ghi đè được giá trị đã có. Tham số `-Dname=value` trên dòng lệnh tạo user property có độ ưu tiên cao.

Ví dụ:

```xml
<project name="property-demo" default="show">
    <property name="build.mode" value="development"/>

    <target name="show">
        <echo message="Mode: ${build.mode}"/>
    </target>
</project>
```

Chạy bình thường:

```bash
ant -f build.xml show
```

Giá trị là `development`. Nhưng khi gọi:

```bash
ant -f build.xml -Dbuild.mode=production show
```

Giá trị `production` được sử dụng thay cho mặc định trong file. Vì vậy, **không xem một `<property name="..." value="..."/>` là hàng rào chống người gọi đưa giá trị khác vào**.

Một điểm khác: nếu tham chiếu `${some.name}` mà property chưa được xác định, Ant thường giữ lại chuỗi tham chiếu chưa được thay thế. Điều này không tương đương với một giá trị rỗng được kiểm tra an toàn. Không nên dựa vào việc đường dẫn chưa resolve sẽ luôn gây lỗi đúng lúc.

Đối với tham số bắt buộc, nên:

1. Không cấp mặc định cho đầu vào được yêu cầu người vận hành truyền một cách có chủ đích.
2. Kiểm tra sự hiện diện bằng `<fail unless="...">`.
3. Kiểm tra miền giá trị bằng `<condition>` hoặc condition lồng trong `<fail>`.
4. Chỉ sau khi các kiểm tra qua hết mới thực thi task thay đổi dữ liệu.

Ví dụ:

```xml
<target name="validate-mode">
    <fail unless="build.mode"
          message="Required: -Dbuild.mode=dev or -Dbuild.mode=ci"/>

    <condition property="build.mode.valid">
        <or>
            <equals arg1="${build.mode}" arg2="dev"/>
            <equals arg1="${build.mode}" arg2="ci"/>
        </or>
    </condition>

    <fail unless="build.mode.valid"
          message="Invalid build.mode: expected dev or ci"/>
</target>
```

Điều kiện `<equals>` có chủ đích chọn chính xác hai giá trị được phép. Một property chỉ có mặt không có nghĩa nó hợp lệ: `-Dbuild.mode=unexpected` phải dừng build.

## 3. Kiểm tra có mặt, giá trị rỗng và giá trị được phép

Có ba câu hỏi khác nhau:

- **Có tham số không?** Dùng `<fail unless="param">` hoặc `<isset property="param"/>`.
- **Tham số có đúng miền giá trị không?** Dùng `<equals>`, `<matches>` và tổ hợp `<and>`/`<or>`/`<not>`.
- **Tham số có hợp với thao tác sắp chạy không?** Dùng quy tắc riêng cho xóa, ghi hoặc phát hành.

Ví dụ nhận một kênh phát hành chỉ cho phép `staging` và `production`:

```xml
<target name="validate-channel">
    <fail unless="release.channel"
          message="Missing -Drelease.channel=staging|production"/>

    <condition property="release.channel.allowed">
        <or>
            <equals arg1="${release.channel}"
                    arg2="staging"
                    casesensitive="true"
                    trim="false"/>
            <equals arg1="${release.channel}"
                    arg2="production"
                    casesensitive="true"
                    trim="false"/>
        </or>
    </condition>

    <fail unless="release.channel.allowed"
          message="release.channel must be staging or production"/>
</target>
```

`-Drelease.channel=` tạo property có thể đã được định nghĩa nhưng có giá trị rỗng. Kiểm tra `unless` đơn thuần chỉ kiểm tra property đã được đặt; điều kiện `equals` sẽ từ chối giá trị rỗng và mọi lựa chọn khác.

Trong target validation, mỗi property kết quả như `release.channel.allowed` nên có tên riêng theo mục đích. Không nên dùng một property condition chung cho nhiều phép kiểm tra khác nhau, bởi property đã được đặt sẽ không tự chuyển về trạng thái false khi điều kiện tiếp theo không thỏa.

### Kiểm tra phiên bản theo mẫu

Nếu chuẩn phát hành yêu cầu phiên bản dạng `MAJOR.MINOR.PATCH`, có thể kiểm tra bằng condition `matches`:

```xml
<target name="validate-version">
    <fail unless="release.version"
          message="Missing -Drelease.version=MAJOR.MINOR.PATCH"/>

    <condition property="release.version.valid">
        <matches string="${release.version}"
                 pattern="^[0-9]+\.[0-9]+\.[0-9]+$"/>
    </condition>

    <fail unless="release.version.valid"
          message="release.version must look like 1.2.3"/>
</target>
```

Mẫu trên chấp nhận `1.2.3`, từ chối `latest`, `1.2` và các chuỗi có ký tự phụ thêm. Đây là **kiểm tra hình thức**, chưa xác nhận phiên bản có thực sự cao hơn phiên bản trước, chưa tồn tại trong kho phát hành hoặc tuân thủ toàn bộ quy tắc Semantic Versioning. Những yêu cầu nghiệp vụ như vậy cần kiểm tra riêng.

Không nên ghép chuỗi version chưa kiểm tra vào tên file hoặc argument của công cụ phát hành. Chẳng hạn, một version chứa dấu phân cách đường dẫn có thể làm file đích khác xa dự kiến nếu cấu hình cho phép.

## 4. Đặt bước kiểm tra làm phụ thuộc của target có tác động

Khả năng kiểm tra tốt phụ thuộc nhiều vào **thứ tự thực thi**. Trong Ant, `depends` xác định target nào phải hoàn thành trước target hiện tại.

```xml
<project name="guard-demo" default="help">
    <target name="help">
        <echo message="Use -Dclean.scope=generated clean-generated"/>
    </target>

    <target name="validate-clean">
        <fail unless="clean.scope"
              message="Specify -Dclean.scope=generated"/>

        <fail message="Only clean.scope=generated is allowed">
            <condition>
                <not>
                    <equals arg1="${clean.scope}"
                            arg2="generated"/>
                </not>
            </condition>
        </fail>
    </target>

    <target name="clean-generated" depends="validate-clean">
        <delete dir="build/generated"/>
    </target>
</project>
```

Ở ví dụ này:

- Chạy `ant -f build.xml` chỉ hiển thị hướng dẫn vì target mặc định là `help`.
- Chạy `ant -f build.xml clean-generated` sẽ dừng khi thiếu `clean.scope`.
- Chạy `ant -f build.xml -Dclean.scope=all clean-generated` cũng dừng.
- Chỉ khi gọi `ant -f build.xml -Dclean.scope=generated clean-generated`, Ant mới có thể thực thi `<delete>` tại thư mục **cố định** `build/generated`.

Đây là kiểu thiết kế có chủ đích: người vận hành xác nhận một **phạm vi được định nghĩa trước**, không nhập một đường dẫn bất kỳ.

### Tại sao chỉ dùng thuộc tính `if` của target là chưa đủ?

Giả sử:

```xml
<target name="release" depends="package"
        if="release.confirmed">
    <!-- publish -->
</target>
```

Trong Ant, điều kiện `if`/`unless` ở target quyết định có chạy **phần thân** target đó hay không; các target phụ thuộc vẫn được giải quyết theo `depends`. Nếu `package` đã xóa hay ghi lại file, những thao tác đó có thể xảy ra trước khi điều kiện của `release` được xét.

Thêm vào đó, `if="release.confirmed"` chỉ kiểm tra property **có tồn tại**, không kiểm tra `release.confirmed=true`. Giá trị `false` cũng có thể khiến target được coi là thỏa điều kiện vì property đã được đặt.

Đối với bước quan trọng, hãy tạo target `validate-release` rõ ràng và đưa nó đứng trước mọi target thay đổi dữ liệu liên quan trong chuỗi phụ thuộc:

```xml
<target name="release" depends="validate-release,package">
    <!-- publish sau khi validate-release và package thành công -->
</target>
```

Các bước nằm trong `package` cũng cần có điều kiện bảo vệ riêng nếu có thể được gọi trực tiếp và tự thực hiện thao tác nguy hiểm.

## 5. Thao tác xóa: giới hạn phạm vi thay vì nhận đường dẫn tự do

`<delete>` là task cần kiểm soát kỹ vì xóa cây thư mục có thể làm mất dữ liệu thật. Cấu hình trực tiếp bằng tham số đầu vào tự do là một dấu hiệu cần xem xét:

```xml
<!-- Không nên dùng cho lệnh dọn dẹp do người vận hành gọi -->
<target name="clean-anything">
    <delete dir="${delete.path}"/>
</target>
```

Nếu người gọi đặt nhầm `delete.path` về thư mục cha hoặc một vị trí không được phép, task có thể xóa dữ liệu ngoài phạm vi mong muốn. Việc chỉ kiểm tra property tồn tại không giải quyết được rủi ro.

Một cách an toàn hơn là tạo target có đường dẫn đích cố định hoặc có **allowlist lựa chọn**:

```xml
<project name="safe-clean" default="help" basedir=".">
    <target name="help">
        <echo message="Available cleanup: generated, test-results"/>
    </target>

    <target name="validate-clean">
        <fail unless="clean.scope"
              message="Required: -Dclean.scope=generated|test-results"/>

        <condition property="clean.generated.allowed">
            <equals arg1="${clean.scope}" arg2="generated"/>
        </condition>
        <condition property="clean.tests.allowed">
            <equals arg1="${clean.scope}" arg2="test-results"/>
        </condition>
        <condition property="clean.scope.valid">
            <or>
                <isset property="clean.generated.allowed"/>
                <isset property="clean.tests.allowed"/>
            </or>
        </condition>

        <fail unless="clean.scope.valid"
              message="Unknown clean.scope"/>
    </target>

    <target name="clean-generated" depends="validate-clean"
            if="clean.generated.allowed">
        <delete dir="build/generated"/>
    </target>

    <target name="clean-test-results" depends="validate-clean"
            if="clean.tests.allowed">
        <delete dir="build/test-results"/>
    </target>

    <target name="clean"
            depends="clean-generated,clean-test-results"/>
</project>
```

Ví dụ này dùng các mục tiêu xóa cố định và validation trước. Tuy nhiên, để giảm nhầm lẫn khi người khác gọi trực tiếp `clean-generated` hay `clean-test-results` với scope khác, nên tổ chức API build rõ hơn: chỉ công khai một target `clean`, đặt các target xử lý nội bộ theo quy ước đặt tên và tài liệu hóa việc chỉ gọi qua `clean`. Nếu cần bảo vệ cả các target con khi được gọi trực tiếp, hãy thêm kiểm tra scope ngay trong từng target trước `<delete>`, thay vì chỉ dựa vào `if` có thể dẫn đến bỏ qua tác vụ.

### Không thể chỉ kiểm tra chuỗi để đảm bảo một đường dẫn bất kỳ an toàn

Các đường dẫn `../`, dấu phân cách `/` và `\`, ổ đĩa, UNC path, đường dẫn tuyệt đối, chữ hoa/thường và symlink có thể khiến những chuỗi khác nhau cùng trỏ tới một vị trí thật. Một phép kiểm tra kiểu “chuỗi bắt đầu bằng `build/`” chưa đủ để bảo đảm đường dẫn nằm bên trong `build` sau khi chuẩn hóa.

Nếu yêu cầu nghiệp vụ **bắt buộc** cho phép đường dẫn tùy ý, bước kiểm tra cần xử lý đường dẫn tuyệt đối, chuẩn hóa/canonical path, gốc được cho phép và khả năng symlink dẫn ra ngoài phạm vi; đồng thời cần xem xét thay đổi filesystem giữa lúc kiểm tra và lúc thao tác. Những kiểm tra đó thường cần task tùy chỉnh hoặc chương trình được kiểm soát chặt thay vì một phép `<equals>` đơn giản trong XML.

Đối với những target xóa chuẩn của project, một thư mục cố định như `build/classes` hoặc `build/generated` thường là lựa chọn rõ ràng và ít rủi ro hơn.

## 6. Thao tác ghi: xác định rõ đầu ra và tránh ghi đè ngoài ý muốn

Không chỉ `<delete>`, các task ghi file cũng cần preflight. Ví dụ:

```xml
<copy file="config/app.properties"
      tofile="${output.path}"/>
```

Nếu `output.path` chưa được kiểm tra, task có thể ghi vào thư mục source, một cấu hình đang dùng hoặc một nơi bất ngờ. Tương tự, `<echo file="...">`, `<move>` và `<zip destfile="...">` cũng nên có đích được thiết kế trước.

### Ưu tiên đường dẫn đích được tính từ gốc do build quản lý

```xml
<project name="safe-write" default="stage" basedir=".">
    <property name="stage.dir" location="build/staging"/>

    <target name="validate-input">
        <available file="src/main/resources/config/app.properties"
                   type="file"
                   property="config.source.exists"/>
        <fail unless="config.source.exists"
              message="Missing config/app.properties"/>
    </target>

    <target name="stage" depends="validate-input">
        <mkdir dir="${stage.dir}"/>
        <copy file="src/main/resources/config/app.properties"
              tofile="${stage.dir}/app.properties"
              overwrite="false"/>
    </target>
</project>
```

Thư mục staging thuộc `build` và không nhận đường dẫn tùy ý từ CLI. `<available>` kiểm tra file nguồn có tồn tại trước khi tạo thư mục và ghi. `overwrite="false"` không phải cơ chế chống mọi trường hợp ghi đè: `copy` có logic cập nhật dựa trên thời gian và trạng thái file, và vẫn có thể ghi khi cần. Nếu yêu cầu thực sự là **không được ghi lên artifact đã có**, cần kiểm tra sự hiện diện của đích và dừng rõ ràng.

### Chặn tên artifact đã tồn tại

```xml
<target name="validate-new-output">
    <available file="dist/app.jar"
               type="file"
               property="dist.app.exists"/>
    <fail if="dist.app.exists"
          message="dist/app.jar already exists; use a new version"/>
</target>

<target name="write-new-output" depends="validate-new-output">
    <mkdir dir="dist"/>
    <jar destfile="dist/app.jar" basedir="build/classes"/>
</target>
```

Phép kiểm tra này có ý nghĩa đối với một lần chạy Ant đơn lẻ trong môi trường được kiểm soát. Nó không phải một khóa độc quyền giữa nhiều tiến trình: nếu hai build cùng kiểm tra một file chưa tồn tại rồi cùng ghi, vẫn có khả năng tranh chấp. Với kho artifact phát hành dùng chung, nên có thêm cơ chế khóa, phiên bản bất biến hoặc thao tác xuất bản có kiểm tra từ phía nơi lưu trữ.

## 7. Phát hành: xác nhận chủ đích, kênh và phiên bản

Phát hành thường có tác động lớn hơn build nội bộ: artifact được đưa tới kho dùng chung, hệ thống triển khai hoặc người dùng cuối. Cần tối thiểu những điều kiện như:

- Một xác nhận rõ ràng, ví dụ `-Drelease.confirm=RELEASE`.
- Kênh/đích phát hành thuộc danh sách được cho phép.
- Phiên bản đúng định dạng và chưa bị sử dụng theo quy tắc của hệ thống phát hành.
- Artifact tồn tại và được tạo từ build/test phù hợp.
- Thông tin xác thực và quyền ghi được cấp cho đúng môi trường; không ghi token trực tiếp trong buildfile.

**Không dùng sự tồn tại của một property làm xác nhận.** Ví dụ:

```xml
<target name="publish" if="release.confirm">
    <!-- publishing action -->
</target>
```

Lệnh `-Drelease.confirm=false` vẫn định nghĩa property, nên không đáp ứng mục đích “chỉ phát hành khi bằng true”. Dùng so khớp giá trị chính xác:

```xml
<target name="validate-release">
    <fail unless="release.confirm"
          message="Missing -Drelease.confirm=RELEASE"/>
    <fail unless="release.channel"
          message="Missing -Drelease.channel=staging|production"/>
    <fail unless="release.version"
          message="Missing -Drelease.version=MAJOR.MINOR.PATCH"/>

    <condition property="release.confirm.valid">
        <equals arg1="${release.confirm}"
                arg2="RELEASE"
                casesensitive="true"/>
    </condition>
    <fail unless="release.confirm.valid"
          message="Pass -Drelease.confirm=RELEASE to publish"/>

    <condition property="release.channel.valid">
        <or>
            <equals arg1="${release.channel}" arg2="staging"/>
            <equals arg1="${release.channel}" arg2="production"/>
        </or>
    </condition>
    <fail unless="release.channel.valid"
          message="Invalid release.channel"/>

    <condition property="release.version.valid">
        <matches string="${release.version}"
                 pattern="^[0-9]+\.[0-9]+\.[0-9]+$"/>
    </condition>
    <fail unless="release.version.valid"
          message="Invalid release.version"/>
</target>
```

Lệnh ví dụ:

```bash
ant -f build.xml -Drelease.confirm=RELEASE -Drelease.channel=staging -Drelease.version=1.2.3 publish
```

Với shell khác nhau, cách đặt dấu nháy cho giá trị có khoảng trắng có thể khác; các giá trị trong ví dụ đều không có khoảng trắng.

**Lưu ý về kiểm tra kênh:** kiểm tra tham số `production` là giá trị cho phép không tự kiểm chứng người chạy đã được cấp quyền phát hành production. Quyền sử dụng tài khoản, approval và chính sách của kho lưu trữ vẫn phải được thực thi bên ngoài/ở nơi nhận.

### Định tuyến tới đích cố định theo kênh

Nếu phải phân biệt thư mục staging và production trong local build, có thể khai báo target có điều kiện sau khi validation:

```xml
<target name="validate-release">
    <!-- Các kiểm tra bắt buộc từ ví dụ bên trên -->
</target>

<target name="select-channel" depends="validate-release">
    <condition property="release.out.dir"
               value="dist/staging"
               else="dist/production">
        <equals arg1="${release.channel}" arg2="staging"/>
    </condition>
</target>

<target name="publish" depends="select-channel">
    <mkdir dir="${release.out.dir}"/>
    <copy file="dist/app.jar"
          tofile="${release.out.dir}/app-${release.version}.jar"/>
</target>
```

Đoạn này minh họa cách chọn đường dẫn dựa trên kênh **đã được kiểm tra hợp lệ**. Không nên dùng riêng đoạn code trên khi chưa bổ sung phần validation đầy đủ và kiểm tra artifact; nếu không, `else="dist/production"` có thể định tuyến các giá trị sai sang production. Thực tế thường cần phát hành qua API/repository quản lý, thay vì chỉ copy file vào thư mục.

## 8. Buildfile mẫu: bảo vệ xóa, ghi và phát hành cùng một chỗ

Ví dụ tự chứa sau sử dụng source Java ở `src/main/java`, biên dịch vào `build/classes` và đóng gói `dist/app.jar`. Target `clean-generated` chỉ xóa một thư mục build cố định khi scope đúng. Target `publish-local` minh họa **tạo bản sao có version trong thư mục phát hành cục bộ**, chưa thực hiện upload ra hệ thống bên ngoài.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="safe-ant-build" default="help" basedir=".">
    <property name="classes.dir" location="build/classes"/>
    <property name="jar.file" location="dist/app.jar"/>
    <property name="published.dir" location="dist/published"/>

    <target name="help">
        <echo message="Build: ant -f build.xml package"/>
        <echo message="Clean: ant -f build.xml -Dclean.scope=classes clean-generated"/>
        <echo message="Publish local: ant -f build.xml -Drelease.confirm=RELEASE -Drelease.version=1.2.3 publish-local"/>
    </target>

    <target name="validate-clean">
        <fail unless="clean.scope"
              message="Missing -Dclean.scope=classes"/>
        <condition property="clean.scope.valid">
            <equals arg1="${clean.scope}" arg2="classes"/>
        </condition>
        <fail unless="clean.scope.valid"
              message="Only clean.scope=classes is supported"/>
    </target>

    <target name="clean-generated" depends="validate-clean">
        <delete dir="${classes.dir}"/>
    </target>

    <target name="validate-build-input">
        <available file="src/main/java"
                   type="dir"
                   property="java.source.exists"/>
        <fail unless="java.source.exists"
              message="Missing src/main/java"/>
    </target>

    <target name="compile" depends="validate-build-input">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="src/main/java"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="dist"/>
        <jar destfile="${jar.file}"
             basedir="${classes.dir}"/>
    </target>

    <target name="validate-release">
        <fail unless="release.confirm"
              message="Missing -Drelease.confirm=RELEASE"/>
        <fail unless="release.version"
              message="Missing -Drelease.version=MAJOR.MINOR.PATCH"/>

        <condition property="release.confirm.valid">
            <equals arg1="${release.confirm}"
                    arg2="RELEASE"/>
        </condition>
        <fail unless="release.confirm.valid"
              message="Explicit confirmation required"/>

        <condition property="release.version.valid">
            <matches string="${release.version}"
                     pattern="^[0-9]+\.[0-9]+\.[0-9]+$"/>
        </condition>
        <fail unless="release.version.valid"
              message="Version must match MAJOR.MINOR.PATCH"/>
    </target>

    <target name="publish-local"
            depends="validate-release,package">
        <available file="${published.dir}/app-${release.version}.jar"
                   type="file"
                   property="release.destination.exists"/>
        <fail if="release.destination.exists"
              message="Version already exists in local published directory"/>
        <mkdir dir="${published.dir}"/>
        <copy file="${jar.file}"
              tofile="${published.dir}/app-${release.version}.jar"
              overwrite="false"/>
        <echo message="Published locally: version ${release.version}"/>
    </target>
</project>
```

Gọi build bình thường:

```bash
ant -f build.xml package
```

Yêu cầu xóa thư mục classes với xác nhận scope:

```bash
ant -f build.xml -Dclean.scope=classes clean-generated
```

Yêu cầu tạo bản phát hành cục bộ:

```bash
ant -f build.xml -Drelease.confirm=RELEASE -Drelease.version=1.2.3 publish-local
```

Trong ví dụ này, target mặc định `help` không đụng đến dữ liệu. Target dọn dẹp dùng đường dẫn cố định `build/classes`; target `publish-local` kiểm tra xác nhận và version **trước** khi chạy `package`, rồi từ chối đích trùng tên đã tồn tại. Việc copy vào `dist/published` chỉ nhằm minh họa cơ chế bảo vệ thao tác ghi; quy trình phát hành thật cần thêm kiểm thử, kiểm tra artifact, xác thực và cấp quyền cho kho đích.

Một điểm cần lưu ý: `classes.dir`, `jar.file` và `published.dir` trong ví dụ đều khai báo bằng property và thông thường có thể bị ghi đè bởi `-D` từ người gọi. Trong build nghiêm ngặt, nếu các đường dẫn đích bắt buộc cố định, nên tránh để chúng trở thành tham số bên ngoài có thể thay đổi, hoặc đặt một bước validation so sánh chính xác với đường dẫn được cho phép trước thao tác. Một property mặc định **không tạo ra ranh giới bảo mật**.

## 9. Khóa đường dẫn đầu ra khi cần cho phép tùy biến

Đôi khi CI phải truyền một thư mục làm việc riêng, ví dụ build chạy trong workspace tạm. Khi đó, có thể giới hạn lựa chọn tới một **nhóm tên/đích đã định nghĩa**, hoặc dùng property dẫn xuất từ workspace do runner quản lý, thay vì nhận thư mục tùy ý.

Ví dụ logic chọn thư mục theo profile hợp lệ:

```xml
<target name="validate-profile">
    <fail unless="build.profile"
          message="Pass -Dbuild.profile=dev|ci"/>
    <condition property="profile.valid">
        <or>
            <equals arg1="${build.profile}" arg2="dev"/>
            <equals arg1="${build.profile}" arg2="ci"/>
        </or>
    </condition>
    <fail unless="profile.valid"
          message="build.profile must be dev or ci"/>
</target>

<target name="select-output" depends="validate-profile">
    <condition property="selected.output"
               value="build/ci-output"
               else="build/dev-output">
        <equals arg1="${build.profile}" arg2="ci"/>
    </condition>
</target>

<target name="prepare-output" depends="select-output">
    <mkdir dir="${selected.output}"/>
</target>
```

Trong Ant, property có thể được đặt từ bên ngoài trước khi buildfile thiết lập giá trị, nên với những tham số ảnh hưởng đến xóa/ghi thực sự, cần **kiểm tra giá trị cuối cùng được sử dụng**. Nếu đòi hỏi một đường dẫn nội bộ không thể bị caller thay đổi, kiểm soát bằng quy tắc và quyền của runner, hoặc dùng task chuyên dụng có allowlist, thay vì chỉ dựa vào thứ tự các lệnh `<property>`.

Đừng cho phép các giá trị như `.`, `..`, `/`, ký tự ổ đĩa hoặc đường dẫn network đi vào `<delete>`/`<copy>` chỉ vì chúng đi qua một property Ant. Việc chặn các chuỗi đơn giản có thể hữu ích, nhưng giới hạn đường dẫn bằng **danh sách đích hợp lệ đã biết** dễ xác minh hơn việc cố đoán mọi biểu diễn đường dẫn nguy hiểm.

## 10. Tách validation khỏi thực thi và tránh tác dụng phụ sớm

Một số buildfile có phần việc ghi file tại cấp project hoặc được kích hoạt trong target phụ thuộc trước khi đến bước xác nhận. Nếu những thao tác ấy đã chạy, validation đặt quá muộn không còn hữu ích.

Ví dụ thứ tự chưa phù hợp:

```xml
<target name="publish" depends="package,validate-release">
    <!-- upload -->
</target>
```

`package` được xử lý trước `validate-release` theo danh sách phụ thuộc trong một lần gọi. Nếu `package` có thao tác ghi đè hoặc xóa, người chạy có thể đã gây thay đổi trước khi bị từ chối phát hành.

Nên đặt bước xác nhận lên trước:

```xml
<target name="publish" depends="validate-release,package">
    <!-- upload chỉ sau khi các bước bắt buộc thành công -->
</target>
```

Với target package cũng có thể được gọi độc lập, cần thiết kế mức kiểm tra phù hợp cho chính target đó. Có thể có các điều kiện khác nhau: người dùng được phép build bất kỳ lúc nào, nhưng phát hành phải có xác nhận và credential; xóa artifact phát hành phải chịu chính sách chặt hơn xóa class biên dịch.

Target validation nên được viết sao cho chỉ xác minh trạng thái và không tự gây tác dụng phụ: dùng `fail`, `condition`, `available`, `echo` có kiểm soát. Các bước cài đặt công cụ, tạo thư mục hoặc tải dependency nên được phân biệt rõ với những phép kiểm tra đầu vào này.

## 11. Tham số đưa vào `exec` và công cụ phát hành ngoài

Khi cần dùng CLI phát hành thay vì task Ant, hạn chế đưa chuỗi người dùng vào lệnh shell ghép thủ công.

Ví dụ dễ gây nhầm lẫn:

```xml
<exec executable="sh" failonerror="true">
    <arg value="-c"/>
    <arg value="publish --version ${release.version}"/>
</exec>
```

Chuỗi truyền vào `sh -c` được shell phân tích, nên ký tự đặc biệt trong `release.version` có thể thay đổi ý nghĩa câu lệnh. Đây là lý do cần kiểm tra đầu vào và tránh chạy thông qua shell khi không cần.

Ưu tiên executable cố định với từng đối số tách biệt:

```xml
<exec executable="publish-tool"
      failonerror="true">
    <arg value="--version"/>
    <arg value="${release.version}"/>
    <arg value="--artifact"/>
    <arg file="dist/app.jar"/>
</exec>
```

Trong ví dụ, `publish-tool` là tên công cụ giả định: cần thay bằng công cụ thật của dự án và bảo đảm nó được cài trên runner. `<arg value="..."/>` truyền một đối số riêng; `<arg file="..."/>` diễn đạt đối số là đường dẫn file theo cơ chế Ant. Cách này giảm việc để shell diễn giải lại chuỗi tham số, nhưng **không loại bỏ yêu cầu kiểm tra tham số và quyền thực thi**: công cụ nhận đối số vẫn có thể có cú pháp, option hoặc behavior riêng cần kiểm soát.

Không nhận tên executable, tên host hoặc URL công bố tùy ý qua `-D` nếu pipeline chỉ được phép phát hành vào một số nơi. Thay vào đó, map một mã môi trường đã được kiểm tra (ví dụ `staging`) sang endpoint cố định được cấu hình trong môi trường CI.

Credential và token không nên được ghi thẳng vào `build.xml` hoặc in qua `<echo>`. Khi xuất log chế độ `-verbose`/`-debug`, kiểm tra nguy cơ lộ property, tham số hoặc thông tin xác thực trước khi lưu/chia sẻ.

## 12. Preflight nên kiểm tra thêm điều gì?

Ngoài giá trị tham số, có thể kiểm tra những điều kiện cần thiết khác trước khi thay đổi dữ liệu:

**Nguồn đầu vào tồn tại.**

```xml
<available file="src/main/java"
           type="dir"
           property="source.present"/>
<fail unless="source.present"
      message="Missing src/main/java"/>
```

**Artifact đã được tạo.**

```xml
<available file="dist/app.jar"
           type="file"
           property="artifact.present"/>
<fail unless="artifact.present"
      message="Run package before publishing"/>
```

**Không trùng tên đích.**

```xml
<available file="dist/published/app-1.2.3.jar"
           type="file"
           property="published.exists"/>
<fail if="published.exists"
      message="Artifact version already exists"/>
```

**Công cụ ngoài đã có.** Có thể chạy một target `check-tool` để gọi `--version` của executable cố định, dùng `failonerror="true"`; hoặc dùng cơ chế kiểm tra phù hợp với môi trường. Nếu không có công cụ thì dừng trước thao tác phát hành thật.

**Kiểm thử đã thành công.** Thường nên để target release phụ thuộc vào target kiểm thử (ví dụ `verify`) đã được định nghĩa đầy đủ, chứ không chỉ kiểm tra có file `.jar`. Artifact tồn tại có thể là kết quả còn sót của một build trước đó.

**Kênh production có quyền riêng.** Việc property vượt qua validation không thay thế cho phân quyền của CI, secret store, môi trường triển khai hoặc kho artifact. Với production, approval và policy của hệ thống phát hành cần được duy trì độc lập.

## 13. Thử các trường hợp đầu vào sai mà không gây tác động

Một build an toàn cần có thông báo lỗi dễ hiểu khi người dùng:

| Tình huống | Giá trị ví dụ | Kết quả mong muốn |
| --- | --- | --- |
| Thiếu scope xóa | Không truyền `-Dclean.scope` | Dừng trước `delete` |
| Scope xóa không hợp lệ | `-Dclean.scope=all` | Dừng, không xóa |
| Xác nhận phát hành sai | `-Drelease.confirm=false` | Dừng trước package/publish |
| Thiếu version | Không truyền `-Drelease.version` | Dừng với hướng dẫn cú pháp |
| Version chứa ký tự đường dẫn | `-Drelease.version=../temp` | Dừng trước khi ghép tên artifact |
| Kênh ngoài danh sách | `-Drelease.channel=other` | Dừng trước khi chọn endpoint |
| Artifact thiếu | Chưa chạy `package` | Dừng trước tác vụ upload |
| Đích đã tồn tại | Phiên bản đã được phát hành | Dừng, tránh ghi đè |

Các lệnh giúp người dùng nhìn thấy kết quả validation ở ví dụ:

```bash
ant -f build.xml clean-generated
ant -f build.xml -Dclean.scope=all clean-generated
ant -f build.xml -Drelease.confirm=false -Drelease.version=1.2.3 publish-local
ant -f build.xml -Drelease.confirm=RELEASE -Drelease.version=../tmp publish-local
```

Những lệnh này minh họa đầu vào cần bị từ chối bởi buildfile có target validation tương ứng. Không chạy thử hành vi nguy hiểm với một buildfile chưa có bảo vệ. Khi phát triển buildfile, có thể dùng bản project tạm hoặc target `validate-*` thuần kiểm tra để quan sát thông báo trước khi cho phép thao tác thật.

Khi nhận lỗi, người dùng cần biết **tên property**, **các giá trị hợp lệ**, và **một lệnh mẫu**. Ví dụ:

```text
BUILD FAILED
Invalid release.version: expected MAJOR.MINOR.PATCH

Example:
  ant -f build.xml -Drelease.confirm=RELEASE -Drelease.version=1.2.3 publish-local
```

Thông báo rõ ràng giúp giảm thói quen sửa đại giá trị hoặc vô hiệu hóa validation chỉ để build chạy tiếp.

## 14. Giới hạn của validation trong một buildfile Ant

Các điều kiện XML giúp ngăn lỗi cấu hình thông thường, nhưng không nên xem chúng là cơ chế bảo mật hoàn chỉnh:

- **Property có thể được truyền từ bên ngoài.** Giá trị mặc định trong `build.xml` không phải một hằng bất biến. Cần kiểm tra chính những giá trị được dùng để xóa/ghi.
- **Tính đúng của đường dẫn phụ thuộc filesystem.** Symlink, đường dẫn tương đối, canonical path, case sensitivity và quyền truy cập có thể khiến một chuỗi có vẻ hợp lệ dẫn đến vị trí ngoài dự kiến.
- **Có thể có tranh chấp giữa kiểm tra và ghi.** Hai tiến trình song song hoặc một tác nhân khác có thể thay đổi file sau khi `<available>` chạy.
- **Xác nhận bằng property không thay thế authorization.** Người có khả năng chạy lệnh với `-Drelease.confirm=RELEASE` có thể cung cấp giá trị đó; CI, kho artifact và môi trường triển khai phải thực thi quyền riêng.
- **Thông báo thành công không bảo đảm phát hành đúng nội dung.** Cần kiểm tra phiên bản, checksum/chữ ký nếu quy trình yêu cầu, test report và thông tin nguồn tạo artifact.
- **Buildfile có thể bị sửa.** Nếu người dùng hoặc tác nhân không tin cậy có quyền sửa buildfile/script và chạy chúng với credential nhạy cảm, một vài điều kiện trong chính buildfile không phải rào chắn đủ mạnh. Cần bảo vệ nhánh, pipeline và secret của môi trường phát hành.

Vì vậy, validation nên được hiểu là **lớp phòng ngừa lỗi và diễn đạt hợp đồng đầu vào**. Nó bổ sung cho kiểm soát truy cập, review thay đổi, môi trường CI cách ly và chính sách của nơi nhận artifact.

## 15. Cách tổ chức target để an toàn và dễ bảo trì

Một cấu trúc dễ đọc thường có ba lớp:

```text
                    [Tham số dòng lệnh/CI]
                              |
                      validate-input
                              |
                +-------------+-------------+
                |             |             |
          validate-clean  validate-write  validate-release
                |             |             |
            delete task    write task      package + publish
                |             |             |
             build/*       build/*       dist/ / repository
```

Ý nghĩa của sơ đồ: **mỗi thao tác gây tác động đều đi qua điều kiện liên quan trước khi thực hiện**. Target xóa không cần phụ thuộc vào xác nhận phát hành, còn target phát hành phải thỏa điều kiện nghiêm ngặt hơn target build thông thường.

Một số quy ước hữu ích:

1. Đặt target mặc định là `help` hoặc một target build ít rủi ro, tránh mặc định xóa hoặc deploy.
2. Đặt tên validation cụ thể: `validate-clean`, `validate-output`, `validate-release`.
3. Đặt `depends` để validation đi trước target làm thay đổi dữ liệu; lưu ý target có thể được gọi trực tiếp.
4. Đưa lựa chọn môi trường và phạm vi xóa về một allowlist; tránh nhận đường dẫn tuyệt đối tự do.
5. Tách dữ liệu nguồn, build tạm, artifact và khu vực phát hành thành các cây thư mục rõ ràng.
6. Tránh xuất secret qua log; để credential được quản lý bởi runner hoặc hệ thống phát hành.
7. Dừng build bằng `<fail>` ngay khi điều kiện không thỏa, kèm thông báo chỉ cách sửa tham số.

## 16. Kết luận

Trong Apache Ant, **kiểm tra tham số đầu vào phải xảy ra trước thao tác xóa, ghi và phát hành**. Chỉ xác nhận rằng property đã tồn tại là chưa đủ: cần kiểm tra giá trị, phạm vi cho phép, trạng thái file, artifact và các tiền điều kiện của từng mục tiêu. Cách thiết kế đơn giản và đáng tin cậy là chọn tên phạm vi hoặc kênh từ danh sách cho phép, ánh xạ chúng tới đích cố định, dùng target `validate-*` với `<condition>` và `<fail>`, rồi mới thực hiện task có tác dụng phụ.

Với thao tác phát hành, xác nhận `-D` chỉ là một phần của quy trình. Quyền của runner, approval, kiểm thử và chính sách kho artifact tiếp tục quyết định liệu thao tác có được phép và có an toàn hay không. Một buildfile diễn đạt rõ các điều kiện này giúp người dùng biết phải cung cấp gì, giúp CI dừng sớm khi dữ liệu sai, và giảm nguy cơ gây thay đổi không mong muốn.
