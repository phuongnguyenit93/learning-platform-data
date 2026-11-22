# Giải nén, kiểm tra nội dung và bảo vệ vị trí đích khi giải nén

Trong Apache Ant, task `<unzip>` giải nén các mục trong một tệp ZIP vào một thư mục trên hệ thống tệp. Đây là bước thường gặp khi chuẩn bị thư viện, giải nén artifact, đưa tài nguyên vào thư mục staging hoặc tạo dữ liệu cho bước build tiếp theo.

Giải nén có vẻ đơn giản: chỉ cần chỉ định tệp ZIP và thư mục đích. Tuy nhiên, một archive có thể chứa hàng trăm mục, tên đường dẫn lồng nhau, tệp trùng tên, đường dẫn tuyệt đối hoặc đường dẫn được tạo có chủ đích để ghi ra ngoài thư mục đích. Vì vậy, một buildfile an toàn cần kiểm soát nguồn archive, tập mục được lấy ra, chính sách ghi đè, thư mục staging và kết quả sau giải nén.

## 1. Task unzip và expand

Ant cung cấp task `<unzip>` để giải nén ZIP. `<expand>` là tên task tương đương cho thao tác mở rộng archive; trong buildfile, `<unzip>` thường dễ đọc hơn khi nguồn là tệp ZIP.

Cú pháp cơ bản:

```xml
<target name="extract-library">
    <mkdir dir="build/dependencies" />

    <unzip
        src="downloads/library.zip"
        dest="build/dependencies" />
</target>
```

Hai thuộc tính chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `src` | Tệp ZIP cần giải nén |
| `dest` | Thư mục gốc nhận các mục được giải nén |

Nếu archive chứa `lib/core.jar`, Ant ghi mục đó thành `build/dependencies/lib/core.jar`. Đường dẫn bên trong archive được giữ tương đối với `dest`.

Task giải nén không tự quyết định thư viện có an toàn hoặc phù hợp với dự án hay không. Buildfile phải xác định archive nào được phép dùng, mục nào được trích xuất và những gì cần có sau thao tác.

## 2. Hiểu đường dẫn bên trong archive

Một ZIP lưu các mục với tên đường dẫn tương đối, thường dùng dấu `/` để phân cấp thư mục. Ví dụ:

```text
library.zip
├── README.txt
├── lib/
│   ├── core.jar
│   └── logging.jar
└── config/
    └── defaults.properties
```

Khi giải nén vào `build/dependencies`, cây kết quả tương ứng là:

```text
build/dependencies/
├── README.txt
├── lib/
│   ├── core.jar
│   └── logging.jar
└── config/
    └── defaults.properties
```

Thư mục `dest` là gốc đích. Các đường dẫn trong archive được nối vào gốc này theo cấu trúc tương đối. Vì vậy, cần kiểm tra xem archive có chứa thêm một cấp thư mục ngoài dự kiến hay không. Chẳng hạn, archive có thể chứa `library-2.0/lib/core.jar`; khi đó kết quả sẽ nằm dưới `dest/library-2.0/` thay vì trực tiếp dưới `dest/lib/`.

Đừng suy đoán cấu trúc archive chỉ từ tên tệp ZIP. Một archive tên `library.zip` không đảm bảo bên trong có thư mục `lib`; hãy xác định các đường dẫn mà buildfile mong đợi và kiểm tra chúng sau khi giải nén.

## 3. Chỉ giải nén những mục cần thiết

Task `<unzip>` hỗ trợ các mẫu chọn tệp thông qua `patternset`. Điều này giúp chỉ lấy những phần cần thiết của archive, ví dụ chỉ JAR và tệp cấu hình:

```xml
<unzip src="downloads/application.zip" dest="build/application">
    <patternset>
        <include name="lib/**/*.jar" />
        <include name="config/**/*.properties" />
        <exclude name="**/samples/**" />
        <exclude name="**/private/**" />
    </patternset>
</unzip>
```

Các mẫu được so khớp với tên mục bên trong archive:

- `lib/**/*.jar` chọn các JAR nằm dưới nhánh `lib`.
- `config/**/*.properties` chọn các tệp properties trong nhánh cấu hình.
- `**/samples/**` và `**/private/**` loại các nhánh không cần lấy.

Có thể dùng nhiều phần tử `include` và `exclude`. Nhiều mẫu include tạo tập ứng viên; các mẫu exclude loại những mục khớp khỏi kết quả. Mẫu `*` khớp trong một thành phần đường dẫn, còn `**` có thể đi qua nhiều cấp.

Nếu chỉ cần một vài tệp đã biết, hãy chọn đúng đường dẫn cụ thể. Lọc theo mẫu giúp giảm lượng dữ liệu được ghi ra và hạn chế nguy cơ đưa các tài liệu không cần thiết vào thư mục đích. Tuy nhiên, patternset chỉ là bộ lọc nội dung; nó không thay thế các biện pháp bảo vệ đường dẫn đích khi xử lý archive không đáng tin cậy.

## 4. Kiểm soát ghi đè bằng overwrite

Khi giải nén vào một thư mục đã có dữ liệu, một mục trong archive có thể trùng đường dẫn với tệp hiện có. Thuộc tính `overwrite` điều khiển việc ghi lại tệp đích đã tồn tại.

Ví dụ cho phép thay thế tệp đích:

```xml
<unzip
    src="downloads/application.zip"
    dest="build/application"
    overwrite="true" />
```

Ví dụ không yêu cầu ghi đè vô điều kiện:

```xml
<unzip
    src="downloads/application.zip"
    dest="build/application"
    overwrite="false" />
```

Khi cần hành vi có thể dự đoán giữa các môi trường, hãy đặt `overwrite` tường minh thay vì dựa vào giá trị mặc định của phiên bản Ant. `overwrite="true"` cho phép thay thế tệp trùng tên ở đích. Khi không bật overwrite, Ant áp dụng quy tắc cập nhật của task và timestamp để quyết định có ghi lại tệp hiện có hay không.

Không dùng `overwrite="true"` để giải quyết mọi xung đột một cách máy móc. Nếu thư mục đích có dữ liệu do người dùng tạo hoặc artifact từ một lần phát hành trước, ghi đè có thể làm mất nội dung. Một thư mục staging mới cho mỗi lần build thường dễ kiểm soát hơn việc giải nén trực tiếp vào thư mục đang được sử dụng.

## 5. Bảo toàn thời gian sửa đổi

Thuộc tính `preservelastmodified` điều khiển việc giữ thời gian sửa đổi của mục archive khi ghi ra hệ thống tệp:

```xml
<unzip
    src="downloads/source-bundle.zip"
    dest="build/source-bundle"
    preservelastmodified="true" />
```

Giữ timestamp có thể hữu ích nếu các bước sau dựa trên thời gian sửa đổi để quyết định có xử lý lại tệp hay không. Nếu không có yêu cầu cụ thể, hãy dùng chính sách mặc định của task hoặc cấu hình rõ theo quy trình build.

Timestamp không chứng minh nội dung đã đúng hoặc đáng tin cậy. Khi cần xác nhận archive là bản phát hành được mong đợi, hãy kiểm tra checksum hoặc chữ ký số từ nguồn phân phối đáng tin cậy trước khi giải nén.

## 6. Kiểm tra nội dung sau khi giải nén

Sau khi giải nén, nên xác nhận các tệp hoặc thư mục mà bước build tiếp theo cần dùng đã xuất hiện. Ant có task `available` để kiểm tra file hoặc thư mục và thiết lập property nếu mục đó tồn tại.

```xml
<target name="extract-and-check">
    <mkdir dir="build/staging/library" />

    <unzip
        src="downloads/library.zip"
        dest="build/staging/library"
        overwrite="true" />

    <available
        file="build/staging/library/lib/core.jar"
        type="file"
        property="library.core.present" />

    <available
        file="build/staging/library/config/defaults.properties"
        type="file"
        property="library.config.present" />

    <fail
        unless="library.core.present"
        message="Archive is missing lib/core.jar" />

    <fail
        unless="library.config.present"
        message="Archive is missing config/defaults.properties" />
</target>
```

Target này xác nhận hai tệp bắt buộc có mặt. Nếu một trong hai thiếu, task `fail` làm build dừng với thông báo cụ thể, tránh để bước biên dịch hoặc chạy ứng dụng thất bại muộn hơn với lỗi khó hiểu.

Có thể kiểm tra thư mục bằng `type="dir"`, hoặc kiểm tra một tệp marker mà archive phải cung cấp. Nếu chỉ cần biết một đường dẫn có tồn tại, `available` là cách đơn giản và dễ đọc.

### Kiểm tra số lượng mục

Nếu cần bảo đảm một tập tệp không rỗng, có thể dùng resource collection và task `resourcecount` sau khi giải nén:

```xml
<resourcecount property="extracted.jar.count">
    <fileset dir="build/staging/library">
        <include name="lib/**/*.jar" />
    </fileset>
</resourcecount>
```

`resourcecount` tạo property chứa số lượng tài nguyên phù hợp. Vì `unless` chỉ kiểm tra property có tồn tại, không thể dùng trực tiếp `unless="extracted.jar.count"` để chứng minh số lượng lớn hơn 0. Nếu cần kiểm tra giá trị số, hãy dùng điều kiện `condition` với phép so sánh:

```xml
<condition property="has.library.jars">
    <not>
        <equals arg1="${extracted.jar.count}" arg2="0" />
    </not>
</condition>

<fail
    unless="has.library.jars"
    message="Archive did not provide any library JARs." />
```

Ở đây `condition` thiết lập `has.library.jars` chỉ khi số lượng khác 0. Đây là ví dụ về khác biệt giữa kiểm tra property tồn tại và kiểm tra giá trị property trong Ant.

## 7. Dùng thư mục staging để bảo vệ vị trí đích

Không nên giải nén trực tiếp một archive mới tải về vào thư mục source, thư mục phát hành đang hoạt động hoặc thư mục dùng chung của nhiều tiến trình. Một archive lỗi hoặc không đúng cấu trúc có thể để lại các tệp một phần, ghi đè nội dung hiện có hoặc khiến các bước sau đọc dữ liệu chưa được xác minh.

Một quy trình an toàn hơn là:

1. Tạo một thư mục staging riêng nằm bên dưới thư mục build do dự án kiểm soát.
2. Giải nén archive vào staging.
3. Kiểm tra các đường dẫn và nội dung bắt buộc.
4. Chỉ sau khi kiểm tra thành công mới đưa các tệp đã chọn sang vị trí đích cuối.

Ví dụ:

```xml
<property name="archive.file" value="downloads/sdk.zip" />
<property name="stage.dir" value="build/staging/sdk" />
<property name="install.dir" value="build/tools/sdk" />

<target name="prepare-sdk-stage">
    <delete dir="${stage.dir}" />
    <mkdir dir="${stage.dir}" />

    <unzip
        src="${archive.file}"
        dest="${stage.dir}"
        overwrite="true" />

    <available
        file="${stage.dir}/bin/compiler.jar"
        type="file"
        property="sdk.compiler.present" />

    <fail
        unless="sdk.compiler.present"
        message="SDK archive is incomplete: bin/compiler.jar is missing." />
</target>

<target name="install-sdk" depends="prepare-sdk-stage">
    <mkdir dir="${install.dir}" />
    <copy todir="${install.dir}">
        <fileset dir="${stage.dir}" />
    </copy>
</target>
```

`stage.dir` là thư mục tạm do build quản lý; `install.dir` chỉ nhận dữ liệu sau khi kiểm tra thành công. Trong ví dụ, `delete` chỉ nhắm tới staging path được cấu hình riêng. Không đặt `stage.dir` trùng với thư mục source hoặc thư mục đích chứa dữ liệu cần giữ.

Nếu cần thay thế toàn bộ một bản cài đặt đang hoạt động, hãy thiết kế bước chuyển đổi riêng: chuẩn bị và kiểm tra đầy đủ bản mới, lưu hoặc giữ khả năng khôi phục bản cũ, rồi mới chuyển vị trí sử dụng. Một chuỗi `delete` rồi `move` không tự tạo ra giao dịch nguyên tử; nếu bước move thất bại sau khi xóa, bản cũ có thể đã mất.

## 8. Bảo vệ đường dẫn đích trước Zip Slip

Một archive không đáng tin cậy có thể chứa tên mục như:

```text
../../outside.txt
```

Nếu một công cụ nối tên này vào thư mục đích mà không kiểm tra đường dẫn chuẩn hóa, mục giải nén có thể thoát khỏi `dest`. Lỗ hổng kiểu này thường được gọi là *Zip Slip* hoặc path traversal trong archive.

Khi giải nén archive không đáng tin cậy:

- Dùng phiên bản Apache Ant còn được hỗ trợ và có biện pháp bảo vệ đường dẫn giải nén. Các bản Ant hiện đại có kiểm tra để ngăn mục archive thoát khỏi thư mục đích; hành vi và thuộc tính liên quan phụ thuộc phiên bản.
- Nếu phiên bản Ant cung cấp thuộc tính `allowFilesToEscapeDest`, giữ giá trị an toàn mặc định là `false`; không bật nó cho archive bên ngoài.
- Không giải nén archive không rõ nguồn gốc bằng một phiên bản Ant cũ chưa có bản vá bảo mật.
- Giải nén vào staging riêng, không đặt `dest` ở gốc repository, thư mục home hoặc thư mục triển khai đang hoạt động.
- Không coi `patternset` là biện pháp bảo vệ duy nhất. Bộ lọc tên tệp không thay thế kiểm tra canonical path.
- Sau khi giải nén, chỉ chuyển các tệp đã xác minh vào vị trí cuối cùng.

Một số archive cũ có thể lưu đường dẫn tuyệt đối hoặc ký hiệu ổ đĩa. Ant có các tùy chọn tương thích như `stripAbsolutePathSpec` trong những phiên bản hỗ trợ, nhưng việc loại bỏ phần đường dẫn tuyệt đối không thay thế kiểm tra traversal như `../`. Hãy đọc tài liệu đúng phiên bản Ant trước khi thay đổi các tùy chọn xử lý đường dẫn; không bật tùy chọn cho phép ghi ra ngoài thư mục đích để khắc phục lỗi archive.

Nếu ứng dụng tự viết logic giải nén bằng Java thay vì dùng task Ant, phải tự chuẩn hóa từng entry path, resolve nó dưới thư mục đích và xác nhận đường dẫn kết quả vẫn nằm bên trong thư mục đích trước khi ghi. Kiểm tra chuỗi đầu vào bằng cách tìm `..` là chưa đủ vì còn có dấu phân cách, đường dẫn tuyệt đối, encoding và khác biệt hệ điều hành.

## 9. Kiểm tra nguồn archive trước khi giải nén

An toàn của thao tác giải nén bắt đầu từ nguồn archive. Với artifact tải từ mạng hoặc nhận từ bên ngoài, nên xác minh nguồn và tính toàn vẹn trước khi gọi `<unzip>`.

Một cách phổ biến là so sánh SHA-256 với giá trị checksum lấy từ kênh phân phối đáng tin cậy:

```xml
<checksum
    file="downloads/sdk.zip"
    algorithm="SHA-256"
    property="sdk.archive.sha256" />

<echo message="SDK archive SHA-256: ${sdk.archive.sha256}" />
```

Task `checksum` tính digest của tệp. Để xác minh, cần so sánh digest đó với giá trị kỳ vọng được cung cấp qua kênh đáng tin cậy; chỉ tính checksum rồi in ra không chứng minh archive hợp lệ.

Ví dụ nếu giá trị kỳ vọng được truyền từ command line hoặc cấu hình CI:

```xml
<condition property="sdk.archive.valid">
    <equals
        arg1="${sdk.archive.sha256}"
        arg2="${sdk.expected.sha256}"
        casesensitive="false" />
</condition>

<fail
    unless="sdk.archive.valid"
    message="SDK archive checksum does not match the expected value." />
```

Đặt bước xác minh này trước target giải nén. Với artifact có chữ ký số, xác minh chữ ký và danh tính nhà phát hành còn cung cấp bằng chứng về nguồn phát hành, trong khi checksum đơn lẻ chỉ xác nhận nội dung khớp với digest kỳ vọng.

## 10. Giữ cấu trúc đích và tránh giải nén lồng nhiều cấp

Một lỗi phổ biến là archive đã có thư mục gốc nhưng buildfile lại tạo thêm một thư mục cùng tên ở đích:

```text
archive.zip
└── sdk-4.0/
    ├── bin/
    └── lib/
```

Nếu giải nén vào `build/sdk-4.0`, kết quả sẽ là:

```text
build/sdk-4.0/sdk-4.0/bin/
build/sdk-4.0/sdk-4.0/lib/
```

Điều này có thể khiến target sau tìm `build/sdk-4.0/bin` nhưng không thấy. Hãy xác định trước archive chứa thư mục gốc hay các mục trực tiếp. Chọn `dest` phù hợp với cấu trúc đó, hoặc dùng pattern/mapper được task hỗ trợ để lấy đúng nhánh.

Không nên sửa cấu trúc archive bằng cách di chuyển thủ công toàn bộ thư mục con nếu chưa xác nhận nó là thư mục gốc duy nhất. Archive có thể chứa nhiều nhánh hợp lệ khác nhau; một thao tác move quá rộng có thể làm mất cấu trúc mong muốn.

## 11. Ví dụ buildfile hoàn chỉnh

Ví dụ sau mô phỏng việc cài một gói công cụ từ ZIP. Buildfile tính checksum, xác minh digest, giải nén vào staging, kiểm tra hai tệp bắt buộc rồi mới sao chép sang thư mục cài đặt của build.

```xml
<project name="safe-unpack" default="install-package">

    <property name="archive.file" value="downloads/toolkit.zip" />
    <property name="stage.dir" value="build/staging/toolkit" />
    <property name="install.dir" value="build/tools/toolkit" />

    <!-- Giá trị này cần được cung cấp từ nguồn phân phối đáng tin cậy. -->
    <property name="expected.sha256" value="replace-with-published-digest" />

    <target name="verify-archive">
        <checksum
            file="${archive.file}"
            algorithm="SHA-256"
            property="archive.sha256" />

        <condition property="archive.checksum.valid">
            <equals
                arg1="${archive.sha256}"
                arg2="${expected.sha256}"
                casesensitive="false" />
        </condition>

        <fail
            unless="archive.checksum.valid"
            message="Toolkit archive checksum is invalid." />
    </target>

    <target name="stage-package" depends="verify-archive">
        <delete dir="${stage.dir}" />
        <mkdir dir="${stage.dir}" />

        <unzip
            src="${archive.file}"
            dest="${stage.dir}"
            overwrite="true"
            preservelastmodified="true">
            <patternset>
                <include name="bin/**" />
                <include name="lib/**/*.jar" />
                <include name="config/*.properties" />
                <exclude name="**/samples/**" />
            </patternset>
        </unzip>

        <available
            file="${stage.dir}/bin/tool-launcher.jar"
            type="file"
            property="tool.launcher.present" />

        <available
            file="${stage.dir}/lib/core.jar"
            type="file"
            property="tool.core.present" />

        <fail
            unless="tool.launcher.present"
            message="Toolkit archive is missing bin/tool-launcher.jar." />

        <fail
            unless="tool.core.present"
            message="Toolkit archive is missing lib/core.jar." />
    </target>

    <target name="install-package" depends="stage-package">
        <mkdir dir="${install.dir}" />
        <copy todir="${install.dir}" overwrite="true">
            <fileset dir="${stage.dir}" />
        </copy>
    </target>

</project>
```

Giá trị `expected.sha256` trong ví dụ chỉ là chỗ giữ chỗ; phải được thay bằng digest thực tế do nhà phát hành cung cấp qua kênh đáng tin cậy. Buildfile không được coi chuỗi giữ chỗ đó là một checksum hợp lệ.

Các target được thực hiện theo thứ tự:

1. `verify-archive` tính SHA-256 và dừng build nếu digest không khớp.
2. `stage-package` tạo staging directory mới rồi giải nén các nhánh được chọn.
3. `available` xác nhận các JAR bắt buộc có mặt.
4. `fail` dừng build nếu archive thiếu thành phần cần thiết.
5. `install-package` chỉ sao chép dữ liệu sau khi staging hoàn tất và kiểm tra thành công.

Ví dụ này không thay thế việc dùng phiên bản Ant có bản vá bảo mật khi giải nén archive không đáng tin cậy. Nó bổ sung kiểm tra nguồn, giới hạn nội dung và xác nhận cấu trúc đầu ra để tránh đưa một gói thiếu hoặc sai phiên bản vào bước tiếp theo.

## 12. Lỗi thường gặp khi giải nén

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy tệp sau khi giải nén | Archive có thêm một thư mục gốc hoặc cấu trúc khác dự kiến | Kiểm tra tên entry và điều chỉnh đường dẫn kiểm tra/`dest` |
| Tệp cũ vẫn còn ở đích | Chính sách overwrite hoặc timestamp khiến mục hiện có không được thay thế | Đặt `overwrite` rõ ràng hoặc dùng staging directory mới |
| Tệp ngoài phạm vi mong muốn xuất hiện | Patternset quá rộng hoặc archive chứa thêm nhánh | Thu hẹp include/exclude và kiểm tra cấu trúc archive |
| Build tiếp tục dù archive thiếu tệp cần thiết | Chưa có bước kiểm tra đầu ra bắt buộc | Dùng `available` kết hợp `fail` trước target tiếp theo |
| Kết quả cài đặt có dữ liệu từ lần trước | Giải nén nhiều lần vào cùng thư mục mà không làm sạch staging | Dùng staging riêng và tạo lại staging trước mỗi lần giải nén |
| Có nguy cơ ghi ra ngoài thư mục đích | Archive chứa đường dẫn traversal hoặc Ant quá cũ | Cập nhật Ant, giữ bảo vệ escape mặc định và giải nén trong staging |
| Build mất dữ liệu đích khi cập nhật thất bại | Xóa bản cũ trước khi xác minh bản mới | Chuẩn bị và kiểm tra bản mới trước; giữ bản cũ cho tới khi chuyển đổi thành công |
| Không xác minh được archive | Chỉ tính checksum nhưng không so sánh với giá trị đáng tin cậy | So sánh digest với giá trị công bố độc lập hoặc xác minh chữ ký |
| Tệp đích có timestamp không như nguồn | Không bật bảo toàn timestamp hoặc filesystem làm tròn thời gian | Dùng `preservelastmodified` nếu cần và không dựa timestamp làm bằng chứng nội dung |

Khi điều tra lỗi, hãy xác định archive nguồn, đường dẫn entry, thư mục đích thực tế, chính sách overwrite và các bước xác minh sau giải nén. Nếu nghi ngờ path traversal, không tiếp tục thử trên thư mục chứa dữ liệu quan trọng; dùng staging cô lập và phiên bản Ant đã được cập nhật.

## 13. Quy trình giải nén có kiểm soát trong Ant

Khi thêm bước giải nén vào buildfile, có thể thực hiện theo trình tự sau:

1. Xác định nguồn ZIP và xác minh nguồn phân phối.
2. Kiểm tra checksum hoặc chữ ký nếu archive đến từ bên ngoài.
3. Dùng phiên bản Ant được duy trì và có bảo vệ chống mục archive thoát khỏi `dest`.
4. Chọn thư mục staging riêng nằm trong vùng build do dự án kiểm soát.
5. Dùng `patternset` để chỉ lấy những nhánh và phần mở rộng cần thiết.
6. Đặt `overwrite` và `preservelastmodified` theo chính sách rõ ràng.
7. Kiểm tra các tệp, thư mục hoặc số lượng tài nguyên bắt buộc sau khi giải nén.
8. Chỉ chuyển hoặc sao chép nội dung đã xác minh sang vị trí cuối cùng.
9. Giữ khả năng khôi phục bản cũ nếu bước cài đặt thay thế một thư mục đang được sử dụng.

`<unzip>` thực hiện việc giải nén; `patternset` giới hạn mục được lấy; `overwrite` và `preservelastmodified` điều khiển cách ghi kết quả. Việc dùng staging, xác minh archive và kiểm tra đầu ra giúp bảo vệ thư mục đích khỏi dữ liệu thiếu, xung đột tên và các đường dẫn độc hại trong archive.
