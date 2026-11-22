# Điểm mở rộng extension-point và extensionOf

Trong một dự án Apache Ant, nhiều phần của quy trình build có thể được tách thành các build file hoặc target riêng. Một build file chính thường cần xác định những mốc công việc chung, trong khi các phần mở rộng cần có cách bổ sung bước xử lý vào đúng mốc đó mà không phải sửa danh sách dependency của build file chính mỗi lần có thành phần mới.

Ant cung cấp hai cơ chế dành cho mục đích này:

- `<extension-point>` khai báo một điểm mà các target khác có thể mở rộng.
- Thuộc tính `extensionOf` trên một `<target>` đăng ký target đó vào điểm mở rộng đã khai báo.

Cơ chế này hữu ích khi chia build thành nhiều phần, ví dụ một build file phụ bổ sung bước đóng gói tài liệu, sao chép cấu hình, tạo báo cáo hoặc chuẩn bị artifact. Build file chính định nghĩa quy trình tổng thể; phần mở rộng chỉ cần khai báo target và điểm mà target muốn tham gia.

`extension-point` và `extensionOf` được hỗ trợ từ Apache Ant 1.8.0. Nếu dự án cần chạy trên Ant cũ hơn, phải nâng phiên bản Ant hoặc thiết kế dependency theo cách khác.

## 1. Extension point là gì?

Một extension point là một mốc trong đồ thị thực thi target. Nó có thể có các dependency như một target thông thường, nhưng bản thân nó không chứa các task xử lý. Các target khác có thể đăng ký để trở thành dependency bổ sung của extension point đó.

Cú pháp:

```xml
<extension-point name="prepare-distribution" depends="compile" />
```

Trong ví dụ này:

- `prepare-distribution` là tên extension point.
- `depends="compile"` yêu cầu target `compile` chạy trước khi extension point hoàn tất.
- Các target khác có thể mở rộng `prepare-distribution` bằng thuộc tính `extensionOf`.

Có thể xem extension point như một vị trí được chừa sẵn trong quy trình build. Nó xác định **khi nào** các phần mở rộng cần được thực thi, còn từng target mở rộng xác định **làm gì** tại vị trí đó.

Một extension point có thể được gọi như một target:

```text
ant prepare-distribution
```

Khi gọi nó, Ant thực hiện các dependency của extension point, bao gồm dependency được khai báo trực tiếp trong `depends` và những target đã đăng ký mở rộng điểm đó.

## 2. extensionOf là gì?

`extensionOf` là thuộc tính của phần tử `<target>`. Khi một target khai báo thuộc tính này, Ant thêm target đó vào danh sách dependency của extension point được chỉ định.

Ví dụ:

```xml
<extension-point name="prepare-distribution" depends="compile" />

<target name="copy-application-files"
        extensionOf="prepare-distribution">
    <copy todir="${dist.stage}">
        <fileset dir="${build.classes}" />
    </copy>
</target>
```

Target `copy-application-files` vẫn là một target bình thường: nó có tên, có thể có dependency riêng và chứa các task. Điểm khác biệt là target này tự đăng ký vào `prepare-distribution`. Khi một target khác phụ thuộc vào extension point, Ant cũng chạy target mở rộng đó.

Thuộc tính `extensionOf` không sao chép nội dung của extension point vào target và cũng không tạo một loại plugin độc lập. Nó chỉ bổ sung quan hệ dependency giữa các target trong build.

Một target có thể vừa khai báo dependency riêng, vừa mở rộng extension point:

```xml
<target name="generate-api-docs"
        depends="compile"
        extensionOf="prepare-distribution">
    <!-- Tạo tài liệu API vào thư mục staging -->
</target>
```

Trong trường hợp này, target `generate-api-docs` cần `compile` hoàn thành trước khi thực hiện công việc của nó, đồng thời được thêm vào điểm `prepare-distribution`.

## 3. Ví dụ đơn giản trong cùng một build file

Trước khi tách nhiều build file, hãy xem cách nhiều target cùng mở rộng một điểm:

```xml
<project name="sample" default="verify">

    <target name="compile">
        <echo message="Compile application" />
    </target>

    <extension-point name="verification" depends="compile" />

    <target name="check-format" extensionOf="verification">
        <echo message="Check source formatting" />
    </target>

    <target name="run-tests" extensionOf="verification">
        <echo message="Run automated tests" />
    </target>

    <target name="verify" depends="verification">
        <echo message="Verification completed" />
    </target>

</project>
```

Khi chạy:

```text
ant verify
```

Ant thực hiện các công việc theo quan hệ dependency:

1. Chạy `compile`.
2. Chạy các target đã mở rộng extension point `verification`, gồm `check-format` và `run-tests`.
3. Thực hiện phần task bên trong target `verify`.

Hai target `check-format` và `run-tests` đều được đăng ký vào cùng một extension point. Build file không cần ghi tên từng target đó trong thuộc tính `depends` của `verify`.

Không nên dựa vào thứ tự tình cờ giữa nhiều target cùng mở rộng một extension point nếu thứ tự đó ảnh hưởng đến kết quả. Nếu một bước bắt buộc phải chạy sau bước khác, hãy thể hiện quan hệ đó bằng `depends` hoặc thiết kế các extension point theo từng giai đoạn.

## 4. Dùng extension-point để chia build thành nhiều file

Đây là trường hợp sử dụng phổ biến: build file chính định nghĩa extension point, còn build file phụ bổ sung target vào điểm đó.

Giả sử dự án có cấu trúc:

```text
my-ant-project/
├── build.xml
├── distribution-extra.xml
├── src/
│   └── main/
│       └── java/
├── docs/
│   └── README.md
└── config/
    └── application.properties
```

Build file chính `build.xml`:

```xml
<project name="my-ant-project" default="dist" basedir=".">

    <property name="build.classes"
              location="${basedir}/build/classes" />
    <property name="dist.stage"
              location="${basedir}/build/distribution" />
    <property name="dist.dir"
              location="${basedir}/dist" />
    <property name="dist.file"
              location="${dist.dir}/my-ant-project.zip" />

    <target name="compile">
        <mkdir dir="${build.classes}" />
        <javac srcdir="${basedir}/src/main/java"
               destdir="${build.classes}"
               includeantruntime="false"
               encoding="UTF-8" />
    </target>

    <!-- Khai báo điểm mở rộng trước khi nạp build file bổ sung. -->
    <extension-point name="prepare-distribution"
                     depends="compile" />

    <import file="distribution-extra.xml" />

    <target name="dist" depends="prepare-distribution">
        <mkdir dir="${dist.dir}" />
        <zip destfile="${dist.file}"
             basedir="${dist.stage}" />
    </target>

</project>
```

Build file phụ `distribution-extra.xml`:

```xml
<project name="distribution-extra">

    <target name="copy-application"
            extensionOf="prepare-distribution">
        <copy todir="${dist.stage}">
            <fileset dir="${build.classes}" />
        </copy>
    </target>

    <target name="copy-documentation"
            extensionOf="prepare-distribution">
        <copy todir="${dist.stage}">
            <fileset dir="${basedir}/docs" />
        </copy>
    </target>

    <target name="copy-configuration"
            extensionOf="prepare-distribution">
        <copy todir="${dist.stage}/config">
            <fileset dir="${basedir}/config" />
        </copy>
    </target>

</project>
```

Khi chạy:

```text
ant dist
```

quy trình diễn ra như sau:

1. Target `dist` phụ thuộc vào `prepare-distribution`.
2. Extension point `prepare-distribution` phụ thuộc vào `compile`, nên mã Java được biên dịch trước.
3. Ba target `copy-application`, `copy-documentation` và `copy-configuration` đã mở rộng điểm này sẽ được đưa vào danh sách dependency của nó.
4. Sau khi extension point hoàn tất, Ant chạy các task trong target `dist` để nén thư mục staging thành ZIP.

Nhờ vậy, build file phụ có thể bổ sung nội dung phân phối mà không phải sửa target `dist` trong build file chính. Khi thêm một phần đóng gói mới, chỉ cần định nghĩa target mở rộng đúng extension point.

Trong ví dụ, các thư mục `src/main/java`, `docs` và `config` cần tồn tại, đồng thời dự án phải có JDK để chạy task `javac`. Có thể điều chỉnh các đường dẫn theo cấu trúc thật của dự án.

## 5. Vai trò của import và thứ tự khai báo

`extensionOf` thường được dùng cùng `<import>` để các build file có thể mở rộng lẫn nhau. Build file được import tham gia vào cùng project Ant, nên các target trong đó có thể dùng property và target được định nghĩa trong build file chính.

Một quy tắc bố trí dễ hiểu là:

1. Khai báo property và target nền tảng mà build file phụ cần sử dụng.
2. Khai báo extension point mà phần mở rộng sẽ đăng ký.
3. Import build file chứa các target mở rộng.
4. Khai báo target tổng hợp phụ thuộc vào extension point.

Đặc biệt, trong cấu trúc ví dụ trên, extension point được khai báo trước khi import file mở rộng. Cách bố trí này giúp điểm mà file phụ tham chiếu đã hiện diện khi Ant xử lý phần mở rộng.

Không nên tạo một target mở rộng tham chiếu nhầm tên extension point. Tên trong `extensionOf` phải khớp với tên đã khai báo. Nếu đổi tên extension point, cần cập nhật tất cả target đang mở rộng nó.

Có thể chia theo trách nhiệm, chẳng hạn:

```text
build.xml
  ├── compile
  ├── extension-point: prepare-distribution
  └── import distribution-extra.xml

distribution-extra.xml
  ├── copy-application
  ├── copy-documentation
  └── copy-configuration

dist
  └── depends on prepare-distribution
```

Không cần tách mọi target thành một file riêng. Chỉ nên tách khi các phần có ranh giới trách nhiệm rõ ràng hoặc được nhiều nhóm/thành phần quản lý độc lập.

## 6. So sánh depends và extensionOf

Hai cơ chế đều tạo quan hệ dependency nhưng diễn đạt ý định từ hai phía khác nhau.

| Tiêu chí | `depends` | `extensionOf` |
|---|---|---|
| Khai báo ở đâu? | Target cần sử dụng dependency | Target muốn tham gia một extension point |
| Ý nghĩa | Target này cần các target kia chạy trước | Thêm target hiện tại vào dependency của extension point |
| Ai cần biết tên target? | Target gọi phải liệt kê dependency | Extension point không cần liệt kê trước tên target mở rộng |
| Trường hợp phù hợp | Quan hệ phụ thuộc cố định, trực tiếp | Các bước mở rộng được bổ sung từ module/build file khác |
| Có thể dùng cùng nhau? | Có | Có |

Ví dụ với `depends`:

```xml
<target name="dist" depends="compile,copy-docs,copy-config">
    <zip destfile="dist/app.zip" basedir="build/stage" />
</target>
```

Mỗi lần thêm bước mới, target `dist` phải được sửa để thêm tên dependency.

Cùng ý tưởng đó với extension point:

```xml
<extension-point name="prepare-dist" depends="compile" />

<target name="copy-docs" extensionOf="prepare-dist">
    <copy file="docs/README.md" todir="build/stage" />
</target>

<target name="copy-config" extensionOf="prepare-dist">
    <copy file="config/app.properties" todir="build/stage" />
</target>

<target name="dist" depends="prepare-dist">
    <zip destfile="dist/app.zip" basedir="build/stage" />
</target>
```

Target `dist` chỉ phụ thuộc vào điểm `prepare-dist`. Các target mở rộng tự đăng ký vào điểm đó. Đây là cách giảm sự liên kết trực tiếp giữa quy trình chính và các bước bổ sung.

## 7. Mở rộng một target vào nhiều extension point

Một target có thể mở rộng nhiều extension point bằng cách liệt kê các tên, phân tách bằng dấu phẩy. Điều này hữu ích khi một công việc cần tham gia vào nhiều giai đoạn đã được định nghĩa trong build.

Ví dụ:

```xml
<extension-point name="before-package" />
<extension-point name="after-package" />

<target name="generate-metadata"
        extensionOf="before-package,after-package">
    <echo message="Generate metadata" />
</target>
```

Trong ví dụ này, `generate-metadata` được đăng ký vào cả hai extension point. Cần cân nhắc kỹ khi dùng cách này: target sẽ được đưa vào dependency của cả hai điểm. Trong một lần chạy Ant, một target chỉ được thực thi một lần; target sẽ chạy khi Ant đi tới nó qua dependency của một trong các điểm được gọi. Việc gắn cùng một target vào nhiều giai đoạn có thể làm ý nghĩa của quy trình khó hiểu.

Nếu công việc thực sự cần chạy ở hai thời điểm khác nhau, nên tách thành hai target có tên riêng hoặc thiết kế lại các extension point. Chỉ mở rộng nhiều điểm khi việc dùng chung cùng một target là chủ đích rõ ràng.

## 8. Xử lý extension point không tồn tại

Mặc định, nếu target khai báo `extensionOf` nhưng extension point được tham chiếu không tồn tại, Ant báo lỗi. Điều này giúp phát hiện lỗi chính tả hoặc việc thiếu build file nền tảng.

Thuộc tính `onMissingExtensionPoint` cho phép chọn cách xử lý khi điểm mở rộng không có mặt:

| Giá trị | Hành vi |
|---|---|
| `fail` | Dừng với lỗi; đây là mặc định |
| `warn` | Ghi cảnh báo và tiếp tục |
| `ignore` | Bỏ qua việc không tìm thấy extension point |

Ví dụ:

```xml
<target name="publish-optional-report"
        extensionOf="after-verification"
        onMissingExtensionPoint="warn">
    <echo message="Publish optional report" />
</target>
```

Cách xử lý này phù hợp khi một build file mở rộng có thể được dùng trong nhiều dự án, trong đó không phải dự án nào cũng khai báo extension point `after-verification`.

Không nên đặt `warn` hoặc `ignore` chỉ để che lỗi cấu hình. Nếu extension point là bắt buộc để build tạo ra sản phẩm đúng, hãy giữ mặc định `fail` để lỗi được phát hiện ngay.

## 9. Điều khiển thứ tự thực thi

Extension point bổ sung dependency vào đồ thị target của Ant. Vì vậy, cần thiết kế quan hệ phụ thuộc có chủ đích.

Giả sử cần thực hiện:

```text
compile
   |
   v
prepare-distribution
   |
   +--> copy-application
   |
   +--> copy-documentation
   |
   v
dist
```

Trong đó, hai bước sao chép có thể độc lập. Nếu một bước cần kết quả của bước kia, hãy khai báo dependency trực tiếp:

```xml
<target name="copy-application"
        extensionOf="prepare-distribution">
    <echo message="Copy application files" />
</target>

<target name="generate-checksum"
        depends="copy-application"
        extensionOf="prepare-distribution">
    <echo message="Generate checksum after application files are copied" />
</target>
```

Target `generate-checksum` phụ thuộc vào `copy-application`, do đó Ant phải hoàn tất việc sao chép ứng dụng trước khi tạo checksum. Đây là quan hệ thứ tự được khai báo rõ ràng.

Cần tránh dependency vòng. Ví dụ, nếu `compile` phụ thuộc vào `prepare-distribution`, trong khi `prepare-distribution` lại phụ thuộc vào `compile`, Ant không thể tạo thứ tự thực thi hợp lệ và sẽ báo lỗi circular dependency.

Không dùng extension point để thay thế mọi quan hệ `depends`. Với các bước có quan hệ cố định, `depends` vẫn là cách thể hiện trực tiếp và dễ đọc nhất.

## 10. Quy ước đặt tên và tổ chức module mở rộng

Khi nhiều build file cùng tham gia một dự án, nên thống nhất cách đặt tên:

- Tên extension point mô tả giai đoạn hoặc thời điểm, ví dụ `before-compile`, `prepare-distribution`, `after-test`.
- Tên target mở rộng mô tả hành động, ví dụ `copy-documentation`, `generate-report`, `publish-metadata`.
- Tránh tên chung chung như `extra`, `step1` hoặc `custom` khi dự án có nhiều module.
- Đặt target và extension point ở build file sở hữu trách nhiệm tương ứng.
- Ghi chú rõ dependency bắt buộc và các property mà target mở rộng cần.
- Không để nhiều module cùng ghi vào một tệp staging theo cách gây ghi đè ngoài ý muốn.

Ví dụ tổ chức:

```text
build/
├── build.xml
├── compile.xml
├── tests.xml
├── distribution.xml
└── reports.xml
```

Build file chính có thể định nghĩa các extension point như `after-compile`, `before-dist` hoặc `after-test`; từng file được import sẽ cung cấp target mở rộng phù hợp. Hãy giữ số lượng extension point vừa đủ để quy trình dễ theo dõi. Một extension point cho mỗi task nhỏ sẽ khiến đồ thị build trở nên phức tạp và khó đọc.

## 11. Các lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể xảy ra | Cách xử lý |
|---|---|---|
| Ant báo không tìm thấy extension point | Sai tên trong `extensionOf`, thiếu build file khai báo điểm đó hoặc import chưa đúng | Đối chiếu tên và thứ tự khai báo/import |
| Target mở rộng không được chạy | Target không được đăng ký vào extension point mà target tổng hợp đang phụ thuộc | Kiểm tra `extensionOf` và dependency của target gọi |
| Target mở rộng chạy nhưng thiếu dữ liệu đầu vào | Extension target chưa khai báo dependency cần thiết | Thêm `depends` phù hợp hoặc dùng extension point có dependency nền |
| Build báo circular dependency | Các target tạo thành vòng phụ thuộc | Vẽ lại đồ thị target và loại bỏ dependency vòng |
| Thứ tự các target mở rộng không như mong đợi | Đang dựa vào thứ tự giữa các extension target độc lập | Khai báo dependency tường minh giữa các target |
| Một extension point bị tham chiếu sai sau khi đổi tên | Một hoặc nhiều file phụ vẫn dùng tên cũ | Tìm tất cả `extensionOf` và cập nhật đồng bộ |
| Target bị bỏ qua khi extension point không có | Cấu hình `onMissingExtensionPoint` là `warn` hoặc `ignore` | Dùng `fail` nếu điểm mở rộng là bắt buộc |
| Hai target ghi đè cùng một tệp | Các module mở rộng dùng chung đường dẫn output | Tách tên tệp hoặc thư mục staging theo module |

Khi điều tra, hãy xem tên target, dependency và build file nơi target được khai báo. Có thể chạy Ant ở mức thông tin chi tiết hơn để quan sát target và task đang được thực thi:

```text
ant -verbose dist
```

Thông tin chi tiết giúp xác định dependency nào được chạy trước và target mở rộng có được đưa vào quy trình hay không.

## 12. Khi nào nên dùng extension-point?

Nên dùng extension point khi build có một quy trình chung và nhiều phần độc lập cần bổ sung bước vào các giai đoạn đã định nghĩa. Một số ví dụ:

- Build chính biên dịch ứng dụng; module tài liệu bổ sung bước tạo tài liệu trước khi đóng gói.
- Build chính chuẩn bị artifact; module cấu hình bổ sung các tệp cấu hình vào staging.
- Quy trình kiểm thử có các target kiểm tra định dạng, chạy test và tạo báo cáo được đăng ký vào một điểm xác minh chung.
- Các module triển khai khác nhau bổ sung bước chuẩn bị vào điểm trước khi phát hành.

Không cần dùng extension point khi chỉ có một vài target phụ thuộc cố định và danh sách đó hiếm khi thay đổi. Khi đó, `depends` trực tiếp thường dễ đọc và dễ bảo trì hơn.

Khi thiết kế một extension point, hãy trả lời rõ ba câu hỏi: điểm này xảy ra ở giai đoạn nào, target mở rộng cần những đầu vào gì, và target tổng hợp nào sẽ phụ thuộc vào điểm đó. Nếu các câu trả lời rõ ràng, cơ chế mở rộng sẽ giúp build linh hoạt mà vẫn giữ được thứ tự thực thi có thể dự đoán.

## 13. Tóm tắt quan hệ giữa các thành phần

```text
Build file chính
  |
  +-- target compile
  |
  +-- extension-point prepare-distribution
  |       |
  |       +-- depends: compile
  |       +-- target copy-application (extensionOf)
  |       +-- target copy-documentation (extensionOf)
  |       +-- target copy-configuration (extensionOf)
  |
  +-- target dist
          |
          +-- depends: prepare-distribution
          +-- tạo gói phát hành
```

`<extension-point>` xác định điểm trong quy trình mà các phần khác có thể tham gia. `extensionOf` cho phép một target tự đăng ký vào điểm đó. Khi target tổng hợp phụ thuộc vào extension point, Ant thực thi cả các dependency nền và các target mở rộng đã đăng ký. Kết hợp đúng với `depends`, cơ chế này giúp chia build thành các phần có trách nhiệm riêng, dễ bổ sung và dễ duy trì.

