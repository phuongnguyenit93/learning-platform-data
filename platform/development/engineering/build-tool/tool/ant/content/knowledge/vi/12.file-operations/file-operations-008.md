# Kiểm tra checksum của tệp và gói phân phối

Khi build một ứng dụng Java, kết quả thường được đóng gói thành JAR, WAR, ZIP hoặc một thư mục phân phối. Trước khi chuyển artifact cho người dùng, máy chủ hoặc một bước CI/CD khác, cần có cách xác nhận file nhận được vẫn giống file đã được tạo ra.

Checksum là giá trị được tính từ nội dung của file bằng một thuật toán băm. Chỉ cần nội dung thay đổi, checksum thường sẽ thay đổi theo. Apache Ant cung cấp task `<checksum>` để tính checksum, ghi giá trị ra file riêng hoặc property, và kiểm tra file có khớp với checksum đã lưu hay không.

## 1. Checksum dùng để làm gì?

Checksum giúp phát hiện file bị hỏng hoặc thay đổi trong quá trình lưu trữ, sao chép, tải xuống và phân phối. Ví dụ, sau khi tạo `app.zip`, build có thể tạo thêm file `app.zip.sha256` chứa checksum SHA-256. Người nhận tải cả hai file rồi dùng Ant để kiểm tra lại.

```text
Build source
    |
    v
Package app.zip
    |
    v
Calculate SHA-256
    |
    +----> app.zip
    |
    +----> app.zip.sha256
                |
                v
       Transfer / publish
                |
                v
       Verify received file
                |
          +-----+-----+
          |           |
        Match       Mismatch
          |           |
       Continue      Fail
```

Checksum không mã hóa file và không che giấu nội dung. Nó cũng không tự chứng minh ai đã tạo artifact. Nếu người khác có thể thay cả artifact lẫn file checksum, họ có thể tính checksum mới cho file đã bị thay. Muốn xác thực nguồn phát hành, cần kết hợp chữ ký số hoặc một kênh phân phối metadata đáng tin cậy.

## 2. Chọn thuật toán băm

Task `<checksum>` hỗ trợ các thuật toán digest mà Java runtime cung cấp thông qua `MessageDigest`. Với gói phân phối mới, nên chỉ định rõ `SHA-256` thay vì dựa vào mặc định của task.

| Thuật toán | Đặc điểm | Khuyến nghị |
|---|---|---|
| MD5 | Nhanh, phổ biến trong hệ thống cũ nhưng không còn an toàn trước tấn công collision | Chỉ dùng khi cần tương thích hệ thống cũ, không dùng làm bảo đảm an toàn |
| SHA-1 | Đã có các tấn công collision thực tế | Tránh dùng cho artifact mới |
| SHA-256 | Thuộc họ SHA-2, được hỗ trợ rộng rãi | Lựa chọn mặc định phù hợp cho checksum phân phối |
| SHA-512 | Thuộc họ SHA-2, digest dài hơn SHA-256 | Có thể dùng khi chính sách hệ thống yêu cầu |

Trong Ant, tên thuật toán truyền vào thuộc tính `algorithm`, ví dụ `algorithm="SHA-256"`. Thuật toán phải được hỗ trợ bởi JDK và provider đang chạy Ant.

## 3. Tính checksum cho một file bằng property

Nếu chỉ cần lấy checksum để ghi log, so sánh hoặc truyền cho một task khác, dùng thuộc tính `property`:

```xml
<target name="calculate-checksum">
    <checksum file="dist/app.zip"
              algorithm="SHA-256"
              property="artifact.sha256"/>
    <echo message="SHA-256: ${artifact.sha256}"/>
</target>
```

`file` chỉ định file cần tính. `algorithm` chọn thuật toán băm. `property` là tên property mà Ant đặt kết quả checksum sau khi tính xong.

Khi dùng `property`, task đưa kết quả vào property thay vì tạo file checksum bên cạnh artifact. Cách này phù hợp nếu giá trị chỉ được dùng trong cùng build, chẳng hạn ghi log, tạo metadata hoặc truyền sang một task khác.

Property của Ant có tính bất biến. Nếu cùng property đã được đặt trước đó, lần tính sau không ghi đè giá trị cũ. Khi cần tính nhiều checksum trong cùng một build, hãy dùng tên property riêng cho từng artifact hoặc tạo một luồng build mới.

## 4. Tạo file checksum bên cạnh artifact

Để phân phối checksum cùng gói, dùng thuộc tính `fileext`:

```xml
<target name="write-checksum">
    <checksum file="dist/app.zip"
              algorithm="SHA-256"
              fileext=".sha256"/>
</target>
```

Với file `dist/app.zip`, Ant tạo file checksum tương ứng `dist/app.zip.sha256`. Thuộc tính `fileext` xác định phần mở rộng của file checksum. Nên dùng tên dễ nhận biết và thống nhất trong dự án, ví dụ `.sha256` cho SHA-256.

Checksum sidecar phải được lưu và phát hành cùng artifact. Nếu chỉ giữ artifact mà bỏ file checksum, người nhận sẽ không có giá trị tham chiếu để kiểm tra tính toàn vẹn sau khi tải xuống.

Không chỉnh sửa thủ công file checksum sau khi tạo. Nếu artifact được đóng gói lại, thay đổi metadata bên trong ZIP hoặc ghi thêm file vào JAR, cần tính lại checksum từ artifact cuối cùng.

## 5. Tính checksum cho nhiều file trong gói phân phối

Khi thư mục `dist` có nhiều artifact, có thể dùng `fileset` để chọn tập file và thuộc tính `todir` để ghi checksum vào một thư mục đích:

```xml
<target name="checksum-all">
    <checksum todir="dist/checksums"
              algorithm="SHA-256"
              fileext=".sha256">
        <fileset dir="dist">
            <include name="*.jar"/>
            <include name="*.zip"/>
            <include name="*.war"/>
        </fileset>
    </checksum>
</target>
```

Ở đây, `fileset` chọn các artifact có phần mở rộng được chỉ định. `checksum` tính digest cho từng file. `todir` chỉ định nơi ghi các file checksum, còn `fileext` quy định phần mở rộng. Ant giữ quan hệ đường dẫn tương đối phù hợp với các file nguồn khi tạo output trong thư mục checksum.

Nếu không cần tách checksum ra thư mục riêng, có thể dùng `fileext` mà không chỉ định `todir` để tạo sidecar cạnh từng artifact. Hãy chọn một quy ước duy nhất để người nhận biết checksum nằm ở đâu.

Không đưa các file `.sha256` đã tạo vào chính fileset đầu vào nếu mục tiêu là chỉ tính checksum cho artifact. Ví dụ trên chỉ include JAR, ZIP và WAR nên không chọn lại các sidecar.

## 6. Kiểm tra file bằng verifyproperty

Task `<checksum>` có thể xác minh file hiện tại với checksum đã lưu. Dùng `verifyproperty` để nhận kết quả kiểm tra vào một property:

```xml
<target name="verify-artifact">
    <checksum file="dist/app.zip"
              algorithm="SHA-256"
              fileext=".sha256"
              verifyproperty="artifact.checksum.matches"/>

    <condition property="artifact.checksum.valid">
        <equals arg1="${artifact.checksum.matches}" arg2="true"/>
    </condition>

    <fail unless="artifact.checksum.valid"
          message="SHA-256 verification failed for dist/app.zip"/>

    <echo message="Artifact checksum verified."/>
</target>
```

Luồng xử lý:

1. Ant đọc `dist/app.zip` và file checksum tương ứng `dist/app.zip.sha256`.
2. Task tính lại checksum bằng SHA-256.
3. Kết quả so sánh được đặt vào property `artifact.checksum.matches` dưới dạng `true` hoặc `false`.
4. Task `<condition>` chỉ đặt `artifact.checksum.valid` khi giá trị kết quả đúng bằng chuỗi `true`.
5. Task `<fail>` làm build thất bại nếu property hợp lệ chưa được đặt.

Điểm quan trọng: `if` và `unless` cổ điển của Ant kiểm tra property có tồn tại hay không, không kiểm tra chuỗi giá trị boolean. Vì vậy, không nên viết `<fail unless="artifact.checksum.matches"/>`: property vẫn tồn tại khi giá trị là `false`, khiến điều kiện đó không phát hiện được checksum sai. Hãy chuyển kết quả boolean thành property chỉ tồn tại khi điều kiện đúng như ví dụ trên.

Nếu file checksum không tồn tại hoặc không đọc được, task có thể báo lỗi trong lúc xác minh. Build cần được xem là thất bại trong trường hợp không thể xác minh artifact.

## 7. Tạo và xác minh checksum trong cùng quy trình build

Một build phân phối thường có ba giai đoạn: chuẩn bị output, đóng gói artifact, sau đó tính checksum. Có thể tổ chức bằng các target riêng:

```xml
<project name="distribution" default="release" basedir=".">
    <property name="staging.dir" location="${basedir}/build/staging"/>
    <property name="dist.dir" location="${basedir}/dist"/>
    <property name="artifact.file" location="${dist.dir}/app.zip"/>

    <target name="init">
        <mkdir dir="${staging.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="stage" depends="init">
        <copy todir="${staging.dir}">
            <fileset dir="src/distribution">
                <include name="**/*"/>
            </fileset>
        </copy>
    </target>

    <target name="package" depends="stage">
        <zip destfile="${artifact.file}" basedir="${staging.dir}"/>
    </target>

    <target name="checksum" depends="package">
        <checksum file="${artifact.file}"
                  algorithm="SHA-256"
                  fileext=".sha256"/>
    </target>

    <target name="verify" depends="checksum">
        <checksum file="${artifact.file}"
                  algorithm="SHA-256"
                  fileext=".sha256"
                  verifyproperty="artifact.checksum.matches"/>
        <condition property="artifact.checksum.valid">
            <equals arg1="${artifact.checksum.matches}" arg2="true"/>
        </condition>
        <fail unless="artifact.checksum.valid"
              message="Distribution checksum verification failed"/>
    </target>

    <target name="release" depends="verify">
        <echo message="Distribution is packaged and verified: ${artifact.file}"/>
    </target>

    <target name="clean">
        <delete dir="${staging.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>
</project>
```

Đồ thị target của ví dụ:

```text
release
  └── verify
        └── checksum
              └── package
                    └── stage
                          └── init

clean
```

Khi chạy `ant release`, Ant tạo staging directory, copy nội dung phân phối, tạo ZIP, sinh checksum và xác minh lại file. Nếu xác minh không thành công, target `release` không hoàn tất thành công.

Trong quy trình phát hành thực tế, bước checksum phải chạy sau khi artifact đã hoàn tất mọi thao tác ghi. Nếu một task tiếp tục thay đổi ZIP sau khi checksum được tạo, sidecar sẽ không còn khớp.

## 8. Xác minh artifact sau khi tải xuống

Người nhận cần có cả file artifact và file checksum được phát hành cùng nó. Có thể tạo một target chỉ thực hiện xác minh, không đóng gói lại artifact:

```xml
<target name="verify-downloaded-artifact">
    <checksum file="download/app.zip"
              algorithm="SHA-256"
              fileext=".sha256"
              verifyproperty="download.checksum.matches"/>
    <condition property="download.checksum.valid">
        <equals arg1="${download.checksum.matches}" arg2="true"/>
    </condition>
    <fail unless="download.checksum.valid"
          message="Downloaded artifact is corrupted or does not match its checksum"/>
    <echo message="Downloaded artifact is intact."/>
</target>
```

Target này giả định hai file nằm tại `download/app.zip` và `download/app.zip.sha256`. Nếu tải artifact vào thư mục khác, hãy điều chỉnh đường dẫn file và quy tắc `fileext` tương ứng.

Không nên tạo lại checksum từ file vừa tải xuống rồi dùng checksum mới đó để xác minh chính file ấy. Cách làm đúng là lấy checksum tham chiếu từ nguồn phát hành đáng tin cậy, sau đó so sánh với file nhận được.

## 9. Checksum cho nhiều artifact và manifest phát hành

Với một bản phát hành có nhiều JAR hoặc ZIP, có thể tạo một checksum sidecar cho từng artifact. Cách này cho phép tải và xác minh từng file độc lập.

Ví dụ:

```text
dist/
├── app.jar
├── app.jar.sha256
├── sources.zip
├── sources.zip.sha256
├── docs.zip
└── docs.zip.sha256
```

Một quy ước khác là tạo manifest chứa tên artifact và checksum. Manifest giúp người nhận có danh sách đầy đủ những file thuộc cùng một lần phát hành. Nếu tự tạo manifest bằng task `<checksum property="...">`, hãy đặt property riêng cho từng artifact rồi ghi các giá trị đó vào file manifest. Đảm bảo manifest được tạo sau khi tất cả artifact đã hoàn tất.

Khi xác minh manifest, cần kiểm tra từng artifact với giá trị checksum tham chiếu tương ứng. Không chỉ kiểm tra rằng file sidecar tồn tại; sự hiện diện của sidecar không chứng minh nội dung artifact còn nguyên vẹn.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tạo được checksum | File nguồn không tồn tại hoặc đường dẫn sai | Kiểm tra `file`, `todir` và dependency tạo artifact |
| Thuật toán không được hỗ trợ | JDK/provider không cung cấp thuật toán đã chọn | Dùng thuật toán được JDK hỗ trợ, ưu tiên SHA-256 |
| Verify thất bại | Artifact đã thay đổi hoặc sidecar thuộc phiên bản khác | Phát hành lại checksum từ artifact cuối cùng hoặc tải lại đúng cặp file |
| Sidecar không nằm cạnh artifact | Đã cấu hình `todir` sang thư mục khác | Kiểm tra đường dẫn đích và quy ước phân phối |
| Checksum luôn được xem là hợp lệ | Dùng `unless` trực tiếp với property có giá trị `false` | So sánh giá trị bằng `<condition>` rồi mới gọi `<fail>` |
| Checksum đúng ngay sau build nhưng sai sau publish | Một bước sau checksum đã sửa artifact | Đưa bước checksum xuống cuối chuỗi tạo artifact |
| Người nhận tạo checksum mới nhưng không phát hiện file bị thay | Không dùng checksum tham chiếu đáng tin cậy | Lấy checksum hoặc chữ ký từ nguồn phát hành độc lập, đáng tin cậy |

## 11. Thực hành với SHA-256

Tạo một thư mục `dist` và đặt một file ZIP mẫu vào đó. Sau đó thực hiện:

1. Viết target tính SHA-256 cho một file bằng thuộc tính `property` và in giá trị ra log.
2. Viết target tạo sidecar `.sha256` cạnh file ZIP.
3. Viết target dùng `verifyproperty` để xác minh file với sidecar.
4. Dùng `<condition>` để chỉ đặt property `checksum.valid` khi kết quả verify bằng `true`.
5. Dùng `<fail>` để làm build thất bại khi checksum không khớp.
6. Chạy xác minh lần đầu khi artifact còn nguyên và ghi nhận kết quả.
7. Thay đổi một byte trong file ZIP rồi chạy lại target verify; build phải thất bại.
8. Khôi phục artifact đúng hoặc tạo lại artifact và checksum, sau đó xác minh thành công.
9. Mở rộng sang fileset để tạo checksum cho tất cả JAR và ZIP trong thư mục phân phối.

Khi hoàn thành, người học cần giải thích được checksum được tính từ đâu, sidecar được đặt ở đâu, `verifyproperty` trả kết quả như thế nào và vì sao phải dùng `<condition>` để kiểm tra giá trị boolean thay vì chỉ kiểm tra property có tồn tại.

## 12. Nguyên tắc đưa checksum vào quy trình phát hành

Hãy tính checksum sau khi artifact đã hoàn tất, dùng thuật toán mạnh như SHA-256, phát hành checksum cùng artifact và xác minh ở phía nhận trước khi sử dụng file. Giữ quy ước đặt tên sidecar nhất quán để các bước CI/CD có thể tìm thấy và kiểm tra tự động.

Checksum giúp phát hiện lỗi toàn vẹn trong quá trình phân phối. Với yêu cầu xác thực nhà phát hành, hãy ký artifact hoặc manifest bằng chữ ký số và phân phối khóa công khai qua kênh tin cậy. Hai cơ chế giải quyết hai câu hỏi khác nhau: checksum trả lời nội dung có khớp giá trị tham chiếu hay không; chữ ký số giúp xác minh dữ liệu được ký bởi chủ thể nắm giữ khóa riêng tương ứng.
