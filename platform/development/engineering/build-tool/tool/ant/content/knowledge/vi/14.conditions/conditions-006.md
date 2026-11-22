# Dừng build có chủ đích bằng fail và thông báo có ngữ cảnh

Trong Apache Ant, một build script không chỉ thực hiện các bước biên dịch, kiểm thử và đóng gói. Nó còn cần xác định khi nào đầu vào không hợp lệ, cấu hình bị thiếu hoặc một điều kiện quan trọng không được đáp ứng. Nếu vẫn tiếp tục trong những trường hợp đó, build có thể tạo ra artifact sai hoặc khiến lỗi chỉ xuất hiện ở một bước xa hơn.

Task `<fail>` cho phép chủ động dừng build và đưa ra thông báo giải thích nguyên nhân. Khi dùng đúng cách, nó biến các giả định của build thành những điều kiện được kiểm tra rõ ràng: thiếu file cấu hình thì dừng, môi trường không được hỗ trợ thì dừng, test hoặc kiểm tra phát hành không đạt thì không tiếp tục đóng gói.

## 1. Task fail làm gì?

`<fail>` là task của Ant dùng để báo lỗi và làm lần chạy build thất bại. Khi task này được thực thi, Ant phát sinh lỗi build, in thông tin `BUILD FAILED` và kết thúc lần chạy hiện tại với trạng thái thất bại. Các task tiếp theo trong target và những target phụ thuộc vào target đang lỗi sẽ không được thực hiện.

Ví dụ đơn giản:

```xml
<target name="validate-release">
    <fail message="Release stopped: required configuration is missing."/>
</target>
```

Khi chạy:

```bash
ant validate-release
```

Ant dừng ngay tại task `<fail>`. Đây là một lỗi được tạo ra có chủ đích để ngăn quy trình đi tiếp khi điều kiện cần thiết chưa được đáp ứng.

Không nên dùng `<echo>` thay cho `<fail>` khi cần báo build thất bại. `echo` chỉ in thông báo; nếu không có task nào khác làm build lỗi, Ant vẫn có thể kết thúc với trạng thái thành công. `<fail>` thể hiện rõ rằng điều kiện hiện tại không cho phép tiếp tục.

## 2. Dùng message để giải thích nguyên nhân dừng

Thuộc tính `message` chứa nội dung Ant hiển thị khi task fail được kích hoạt:

```xml
<target name="check-input">
    <fail message="Input validation failed: config/app.properties was not found."/>
</target>
```

Một thông báo tốt nên giúp người đọc trả lời được ba câu hỏi:

1. Bước nào hoặc điều kiện nào không đạt?
2. Đối tượng nào gây ra vấn đề, chẳng hạn file, property, môi trường hoặc artifact?
3. Người vận hành nên kiểm tra điều gì tiếp theo?

Ví dụ, thông báo `Build failed` quá chung chung. Thông báo `Cannot package release: ${config.file} does not exist. Check the release configuration path.` cung cấp ngữ cảnh và hướng kiểm tra cụ thể hơn.

Có thể đưa property vào message:

```xml
<property name="environment" value="dev"/>
<property name="config.file" value="config/${environment}.properties"/>

<target name="validate-config">
    <fail message="Cannot continue: configuration '${config.file}' is missing for environment '${environment}'."/>
</target>
```

Ant thay các tham chiếu property khi đọc build file. Nếu property chưa được đặt, biểu thức có thể không được thay bằng giá trị mong đợi; vì vậy nên khai báo giá trị mặc định hoặc kiểm tra property đầu vào trước khi sử dụng nó.

Không đưa password, access token, private key hoặc dữ liệu nhạy cảm vào thông báo lỗi. Log build thường được lưu trên CI và có thể được nhiều người truy cập.

## 3. Kiểm tra file bắt buộc trước khi chạy task

Một trường hợp phổ biến là yêu cầu file cấu hình phải tồn tại trước khi compile, test hoặc package. Task `<available>` có thể đặt property khi file tồn tại; `<fail>` dừng build nếu property đó chưa được đặt.

```xml
<project name="release-app" default="package" basedir=".">
    <property name="environment" value="production"/>
    <property name="config.file"
              location="${basedir}/config/${environment}.properties"/>

    <target name="validate-config">
        <available file="${config.file}"
                   type="file"
                   property="config.exists"/>
        <fail unless="config.exists"
              message="Cannot package '${environment}': configuration file '${config.file}' does not exist."/>
    </target>

    <target name="package" depends="validate-config">
        <echo message="Configuration found. Packaging release."/>
    </target>
</project>
```

Khi chạy `ant package`, Ant thực hiện `validate-config` trước. Nếu file tồn tại, `<available>` đặt `config.exists` và `<fail unless="config.exists">` không kích hoạt. Nếu file không tồn tại, property không được đặt, task `<fail>` dừng build và target `package` không chạy.

Thuộc tính `type="file"` yêu cầu đường dẫn là file. Nếu muốn chấp nhận cả file lẫn thư mục, có thể bỏ thuộc tính này hoặc dùng điều kiện phù hợp với yêu cầu. Cần kiểm tra đúng loại tài nguyên mà bước sau thực sự cần.

## 4. Phân biệt if/unless của fail với giá trị boolean

Task `<fail>` hỗ trợ `if` và `unless` để quyết định có kích hoạt lỗi hay không. Giống điều kiện cổ điển trên target, các thuộc tính này kiểm tra **property có tồn tại hay không**, không kiểm tra nội dung property có phải chuỗi `true` hay không.

```xml
<property name="release.enabled" value="false"/>

<target name="check-release">
    <fail if="release.enabled"
          message="Release is blocked because release.enabled is set."/>
</target>
```

Trong ví dụ, property `release.enabled` đã tồn tại nên `<fail if="release.enabled">` được kích hoạt, dù giá trị property là `false`.

Tương tự:

- `if="some.property"`: fail khi property đã được đặt.
- `unless="some.property"`: fail khi property chưa được đặt.

Nếu cần kiểm tra một giá trị boolean hoặc so sánh nội dung property, hãy dùng `<condition>` để tạo property kết quả chỉ khi biểu thức đúng. Sau đó dùng `unless` với property kết quả.

Ví dụ kiểm tra môi trường hợp lệ:

```xml
<project name="environment-check" default="validate" basedir=".">
    <property name="environment" value="dev"/>

    <target name="validate">
        <condition property="environment.valid">
            <or>
                <equals arg1="${environment}" arg2="dev"/>
                <equals arg1="${environment}" arg2="test"/>
                <equals arg1="${environment}" arg2="production"/>
            </or>
        </condition>

        <fail unless="environment.valid"
              message="Unsupported environment '${environment}'. Allowed values: dev, test, production."/>
    </target>
</project>
```

Chạy với giá trị mặc định:

```bash
ant validate
```

Hoặc truyền môi trường khác:

```bash
ant -Denvironment=production validate
ant -Denvironment=staging validate
```

`production` được chấp nhận. `staging` không khớp bất kỳ nhánh `equals` nào, vì vậy `environment.valid` không được tạo và `<fail>` dừng build với thông báo liệt kê các giá trị hợp lệ.

Ant property có tính bất biến: một khi đã được đặt, khai báo property sau đó không ghi đè giá trị cũ. Đây là lý do nên dùng property đầu vào như `environment`, rồi tạo property kết quả riêng như `environment.valid`.

## 5. Dùng nested condition trực tiếp trong fail

Ngoài `if` và `unless`, task `<fail>` có thể chứa phần tử `<condition>` để mô tả điều kiện kích hoạt lỗi. Cách này hữu ích khi không cần tái sử dụng property kết quả ở nơi khác.

Ví dụ dừng nếu file cấu hình không tồn tại:

```xml
<target name="validate-config">
    <fail message="Required configuration config/app.properties is missing.">
        <condition>
            <not>
                <available file="config/app.properties" type="file"/>
            </not>
        </condition>
    </fail>
</target>
```

Ant đánh giá điều kiện lồng bên trong `<fail>`. Nếu `<available>` trả về false, `<not>` đảo kết quả thành true và task fail được kích hoạt.

Có thể kết hợp nhiều điều kiện:

```xml
<fail message="Release requires a production config and a built JAR.">
    <condition>
        <or>
            <not>
                <equals arg1="${environment}" arg2="production"/>
            </not>
            <not>
                <available file="dist/app.jar" type="file"/>
            </not>
        </or>
    </condition>
</fail>
```

Task fail được kích hoạt nếu môi trường không phải `production` hoặc file JAR không tồn tại. Với điều kiện phức tạp, hãy đặt tên target rõ ràng và viết message phản ánh đúng điều kiện thất bại để log dễ đọc.

## 6. Kiểm tra nhiều điều kiện trước khi đóng gói

Một target validate có thể gom các kiểm tra đầu vào trước khi các target package hoặc deploy chạy. Ví dụ:

```xml
<project name="app-release" default="release" basedir=".">
    <property name="environment" value="production"/>
    <property name="main.class" value="com.example.App"/>
    <property name="config.file"
              location="${basedir}/config/${environment}.properties"/>

    <target name="validate">
        <available file="${config.file}"
                   type="file"
                   property="config.exists"/>

        <fail unless="config.exists"
              message="Release validation failed: missing config file '${config.file}'."/>

        <condition property="environment.valid">
            <or>
                <equals arg1="${environment}" arg2="test"/>
                <equals arg1="${environment}" arg2="production"/>
            </or>
        </condition>

        <fail unless="environment.valid"
              message="Release validation failed: environment '${environment}' is not allowed."/>

        <condition property="main.class.valid">
            <isset property="main.class"/>
        </condition>

        <fail unless="main.class.valid"
              message="Release validation failed: main.class property is missing."/>
    </target>

    <target name="compile" depends="validate">
        <mkdir dir="build/classes"/>
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false"/>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="dist"/>
        <jar destfile="dist/app.jar" basedir="build/classes">
            <manifest>
                <attribute name="Main-Class" value="${main.class}"/>
            </manifest>
        </jar>
    </target>

    <target name="release" depends="package">
        <echo message="Release artifact created for '${environment}'."/>
    </target>
</project>
```

Các target phía sau chỉ chạy nếu `validate` hoàn tất. Nếu một task fail trong `validate`, Ant dừng và không thực hiện `compile`, `package` hoặc `release`.

Trong ví dụ này, `main.class` được khai báo mặc định nên kiểm tra `isset` chỉ minh họa cách kiểm tra property. Với dự án thật, cần xác định chính xác giá trị bắt buộc, chẳng hạn không cho phép chuỗi rỗng, và dùng điều kiện phù hợp để xác nhận.

## 7. Dừng build khi một artifact hoặc kết quả kiểm tra không đạt

Task `<fail>` thường được dùng sau các bước kiểm tra. Ví dụ, sau khi chạy một chương trình kiểm tra hoặc xác minh checksum, build có thể dừng nếu kết quả không đạt.

```xml
<target name="verify-artifact">
    <checksum file="dist/app.zip"
              algorithm="SHA-256"
              fileext=".sha256"
              verifyproperty="checksum.matches"/>

    <condition property="checksum.valid">
        <equals arg1="${checksum.matches}" arg2="true"/>
    </condition>

    <fail unless="checksum.valid"
          message="Artifact verification failed: SHA-256 does not match dist/app.zip.sha256."/>
</target>
```

`verifyproperty` nhận kết quả kiểm tra. `<condition>` tạo `checksum.valid` chỉ khi kết quả bằng `true`. Nếu checksum không khớp, property không tồn tại và task `<fail>` dừng build.

Đây là mẫu tổng quát cho các kết quả dạng boolean: chuyển giá trị kiểm tra thành property chỉ tồn tại khi đạt, sau đó dùng `fail unless` để bắt trường hợp không đạt. Không dùng `fail if="checksum.matches"` nếu `checksum.matches` tồn tại cả khi giá trị là `false`.

## 8. Dùng status để trả mã lỗi phù hợp

Task `<fail>` có thuộc tính `status` để chỉ định mã trạng thái thoát khi build thất bại. Nếu không chỉ định, Ant dùng mã lỗi mặc định của mình.

```xml
<target name="validate-release">
    <fail status="2"
          message="Release validation failed. Check required configuration and artifact inputs."/>
</target>
```

Mã trạng thái có thể được hệ thống CI hoặc script bên ngoài sử dụng để phân loại lỗi. Hãy thống nhất quy ước mã lỗi nếu pipeline cần phân biệt các nhóm thất bại. Không nên dùng mã trạng thái như một cách thay thế cho thông báo giải thích; log vẫn cần message đủ ngữ cảnh để người vận hành biết nguyên nhân.

Khi task fail được gọi, Ant kết thúc lần build hiện tại. Việc một hệ thống bên ngoài hiển thị mã lỗi ra sao còn phụ thuộc cách nó gọi Ant và cách wrapper xử lý exit code.

## 9. Phân biệt fail với điều kiện if/unless trên target

`if` và `unless` trên target quyết định các task trong target có được thực hiện sau khi dependency hoàn tất hay không. Chúng có thể bỏ qua target mà không làm build thất bại.

`<fail>` là một task thực thi trong target. Khi điều kiện của task fail được kích hoạt, build bị đánh dấu thất bại.

| Cơ chế | Kết quả khi điều kiện không đạt |
|---|---|
| Target có `if` không thỏa | Bỏ qua task trong target; dependency đã chạy trước đó vẫn có thể đã thực hiện |
| Target có `unless` không thỏa | Bỏ qua task trong target |
| Task `<fail>` được kích hoạt | Dừng build với trạng thái thất bại |
| Task `<echo>` in cảnh báo | Chỉ ghi thông báo; build vẫn có thể thành công |

Ví dụ, nếu muốn bỏ qua bước publish khi `skip.publish` được đặt, dùng `unless` trên target. Nếu muốn dừng hoàn toàn vì file cấu hình bắt buộc bị thiếu, dùng `<fail>`. Chọn đúng cơ chế theo ý nghĩa nghiệp vụ: bỏ qua một nhánh tùy chọn khác với việc dữ liệu đầu vào không hợp lệ.

## 10. Thiết kế thông báo lỗi có ngữ cảnh

Thông báo lỗi là một phần của giao diện vận hành build. Người đọc có thể không phải người viết `build.xml`, vì vậy message nên đủ rõ để xử lý mà không cần mở toàn bộ source.

Một số mẫu thông báo:

| Tình huống | Message gợi ý |
|---|---|
| Thiếu file cấu hình | `Missing configuration '${config.file}' for environment '${environment}'.` |
| Giá trị môi trường không hợp lệ | `Unsupported environment '${environment}'. Allowed values: dev, test, production.` |
| Thiếu artifact đầu vào | `Cannot deploy: artifact '${artifact.file}' does not exist.` |
| Kiểm tra checksum thất bại | `Artifact '${artifact.file}' failed SHA-256 verification.` |
| Thiếu thư viện bắt buộc | `Required library '${library.file}' is missing from the dependency directory.` |
| Thiếu tham số build | `Property 'release.version' is required. Pass -Drelease.version=<version>.` |

Nên đưa vào message:

- Tên target hoặc bước nghiệp vụ đang dừng.
- Giá trị thực tế gây lỗi nếu giá trị đó không nhạy cảm.
- Đường dẫn file hoặc tên artifact liên quan.
- Giá trị hợp lệ hoặc cách truyền tham số nếu người chạy có thể tự sửa.

Tránh message chỉ có `Invalid input`, `Something went wrong` hoặc `Build failed`. Những câu này không giúp thu hẹp nguyên nhân.

## 11. Những lỗi thường gặp khi dùng fail

| Lỗi cấu hình | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng `echo` thay cho `fail` | Log có cảnh báo nhưng build vẫn có thể thành công | Dùng `<fail>` khi điều kiện bắt buộc không đạt |
| Dùng `if` với property có giá trị `false` | Fail vẫn kích hoạt vì property tồn tại | Dùng `<condition>` để tạo property kết quả chỉ khi đúng |
| Dùng `unless` với property luôn được khai báo | Fail không kích hoạt vì property đã tồn tại | Tạo property cờ chỉ khi điều kiện đạt |
| Kiểm tra file sau khi task cần file đã chạy | Build có thể lỗi ở bước sau với message khó hiểu | Tạo target validate và đặt làm dependency trước bước sử dụng file |
| Message quá chung chung | Khó tìm nguyên nhân từ log CI | Thêm tên file, property, môi trường và hành động đang dừng |
| Đưa secret vào message | Dữ liệu nhạy cảm có thể bị ghi vào log | Chỉ hiển thị tên cấu hình hoặc vị trí, không in giá trị bí mật |
| Gọi fail quá sớm trước khi chuẩn bị dữ liệu cần kiểm tra | Điều kiện không phản ánh trạng thái cuối cùng | Đặt bước kiểm tra sau dependency tạo hoặc xác định dữ liệu |

## 12. Bài tập thực hành

Tạo một `build.xml` cho ứng dụng có target `validate`, `compile`, `test`, `package` và `release`.

1. Khai báo property `environment` với giá trị mặc định `dev`.
2. Dùng `<condition>` để chỉ chấp nhận `dev`, `test` hoặc `production`.
3. Dùng `<available>` kiểm tra file cấu hình của môi trường hiện tại.
4. Dùng `<fail>` với message nêu rõ tên môi trường và đường dẫn file nếu cấu hình thiếu.
5. Đặt `compile` phụ thuộc `validate`, để lỗi đầu vào ngăn các bước sau chạy.
6. Tạo một property kết quả kiểm tra checksum và dùng `<fail>` khi checksum không khớp.
7. Thử `ant -Denvironment=staging release` và quan sát message cùng trạng thái build.
8. Thử bỏ file cấu hình rồi chạy lại để xác nhận build dừng tại validate.
9. Cải thiện từng message để người khác có thể biết cần sửa file hoặc property nào.

Khi hoàn thành, người học cần phân biệt được trường hợp nên bỏ qua target với trường hợp phải dừng build, biết cách kiểm tra property đúng nghĩa boolean và viết được message đủ ngữ cảnh để CI hoặc người vận hành xử lý.

## 13. Nguyên tắc sử dụng fail trong build thực tế

Đặt các kiểm tra bắt buộc ở đầu luồng build, trước target đầu tiên sử dụng dữ liệu đó. Dùng `<condition>` hoặc các task kiểm tra như `<available>` để xác định trạng thái, sau đó dùng `<fail>` để dừng khi điều kiện không đạt. Giữ message ngắn gọn nhưng có tên đối tượng và hướng xử lý; không đưa bí mật vào log.

Khi build thất bại, mục tiêu là để người vận hành hiểu chính xác bước nào không thể tiếp tục và vì sao. Một build dừng sớm với nguyên nhân rõ ràng dễ xử lý hơn một build tạo artifact thiếu hoặc sai rồi chỉ bộc lộ vấn đề ở giai đoạn phát hành.
