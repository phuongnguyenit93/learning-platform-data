# Sử dụng `echo`, mức log và thông báo theo ngữ cảnh `target` trong Apache Ant

## 1. Vì sao cần thiết kế log cho bản build?

Khi chạy Apache Ant, một dự án thường thực hiện nhiều `target` liên tiếp: chuẩn bị thư mục, biên dịch, kiểm thử, đóng gói và phát hành. Nếu mọi bước đều in những câu như “Đang chạy…” hoặc “Thành công” mà không nêu rõ bước nào, người đọc log khó xác định nơi xảy ra sự cố. Ngược lại, in quá nhiều chi tiết trong mỗi lần build khiến cảnh báo và lỗi thật bị chìm.

Ant cung cấp tác vụ `<echo>` để xuất thông báo. Mỗi thông báo có thể được gán **mức log**; nội dung cũng có thể mang **ngữ cảnh của target**, môi trường và đầu ra đang xử lý. Kết hợp ba yếu tố này giúp đọc log tại máy cá nhân, trong terminal của CI và trong tệp lưu trữ nhất quán hơn.

Sau bài học, bạn có thể:

- Dùng `<echo>` để ghi thông báo một dòng hoặc nhiều dòng và chèn giá trị property.
- Chọn mức `error`, `warning`, `info`, `verbose` hoặc `debug` đúng mục đích.
- Dự đoán thông báo nào xuất hiện khi chạy Ant với `-quiet`, mặc định, `-verbose` hay `-debug`.
- Đặt thông điệp theo tên `target` để nhận diện bước đang chạy và kết quả của bước đó.
- Phân biệt **ghi một thông báo lỗi** với **thực sự dừng build vì lỗi**.
- Chọn cách lưu log phù hợp mà không để lộ dữ liệu nhạy cảm.

## 2. `echo` hoạt động thế nào?

Cú pháp đơn giản nhất:

```xml
<target name="hello">
    <echo message="Chào từ Apache Ant!"/>
</target>
```

Có thể đặt thông điệp bên trong phần thân của tác vụ:

```xml
<target name="hello">
    <echo>Đây là thông báo trong phần thân echo.</echo>
</target>
```

Với thông báo nhiều dòng, dùng phần thân để dễ đọc:

```xml
<target name="show-plan">
    <echo>Quy trình dự kiến:
1. Chuẩn bị đầu vào
2. Biên dịch mã nguồn
3. Đóng gói sản phẩm</echo>
</target>
```

Các đặc điểm cần nhớ:

1. `message` thích hợp cho câu ngắn, nhất là khi muốn tránh xuống dòng hoặc khoảng trắng vô tình xuất hiện vì thụt lề XML. Phần thân `<echo>...</echo>` thích hợp cho nội dung dài hoặc nhiều dòng.
2. Khi không chỉ định `file`, thông báo được gửi vào hệ thống logging của Ant. Logger/listener đang sử dụng quyết định cách hiển thị; tiền tố quen thuộc `[echo]` thường đến từ logger mặc định.
3. `echo` là tác vụ trong `target`. Nó chỉ thực thi khi luồng build thật sự đi qua vị trí ấy; đặt một `echo` trong `target` không được gọi sẽ không sinh log.
4. Ant thay thế những biểu thức property đã được xác định, chẳng hạn `${build.dir}`, trước khi hiển thị thông điệp. Property chưa tồn tại có thể còn nguyên biểu thức `${...}` trong log, nên cần kiểm tra nơi khai báo và giá trị truyền vào.

Ví dụ gắn thông điệp với property:

```xml
<project name="build-example" default="show-config">
    <property name="build.dir" location="build/classes"/>
    <property name="profile" value="local"/>

    <target name="show-config">
        <echo level="info"
              message="[show-config][${profile}] Thư mục build: ${build.dir}"/>
    </target>
</project>
```

Khi gọi `ant -Dprofile=ci show-config`, thuộc tính dòng lệnh đặt `profile` thành `ci`. Các property trong Ant về cơ bản có tính **bất biến sau khi được đặt**; vì vậy không nên thiết kế mỗi `target` cùng ghi đè một property `target.name` rồi mong giá trị được cập nhật. Cách an toàn là ghi rõ tên `target` trong thông báo hoặc truyền tên đó như tham số của một macro.

## 3. Hiểu năm mức log của `echo`

`<echo>` hỗ trợ năm giá trị cho thuộc tính `level`. Thứ tự từ nghiêm trọng đến chi tiết là:

| Mức | Khi nào dùng | Ví dụ thông điệp |
| --- | --- | --- |
| `error` | Nêu lỗi nghiêm trọng; thường đi kèm một cơ chế thực sự kết thúc build | `[verify] Không thể tạo artifact` |
| `warning` | Phát hiện bất thường nhưng build vẫn có thể tiếp tục | `[docs] Thiếu tài liệu tùy chọn` |
| `info` | Mốc thực thi và kết quả chính cần thấy trong lần chạy thông thường | `[compile] Bắt đầu biên dịch` |
| `verbose` | Thông tin phụ trợ chỉ cần khi điều tra vấn đề | `[compile] Đầu ra: build/classes` |
| `debug` | Dữ liệu chẩn đoán chi tiết dành cho phiên gỡ lỗi | `[resolve] Sử dụng đường dẫn cấu hình X` |

**Điểm dễ bỏ sót:** nếu không ghi `level`, `echo` mặc định dùng **`warning`**. Do đó:

```xml
<echo message="Bắt đầu biên dịch"/>
```

không tương đương về mức log với:

```xml
<echo level="info" message="Bắt đầu biên dịch"/>
```

Với thông điệp tiến độ thông thường, hãy khai báo `level="info"` rõ ràng. Nếu để mặc định `warning` cho mọi câu thông báo, chế độ chạy yên lặng vẫn có thể bị lấp đầy bởi các câu không phải cảnh báo.

### 3.1. Các chế độ hiển thị từ dòng lệnh

Giả sử chỉ sử dụng logger mặc định của Ant, bảng sau cho thấy mức độ chi tiết thông thường:

| Chạy lệnh | Mức được hiển thị | Mục đích |
| --- | --- | --- |
| `ant -quiet` hoặc `ant -q` | `error`, `warning` | Giữ lại vấn đề đáng chú ý |
| `ant` | `error`, `warning`, `info` | Theo dõi build hằng ngày |
| `ant -verbose` hoặc `ant -v` | Thêm `verbose` | Tìm hiểu các bước và thông số |
| `ant -debug` hoặc `ant -d` | Thêm `debug` | Điều tra sâu hoạt động của Ant |

Tên `target`, tên tác vụ, thông báo do tác vụ khác tạo và định dạng dòng có thể thay đổi theo logger, listener hoặc môi trường CI. Bảng trên tập trung vào **ngưỡng lọc thông báo** của hệ thống logging, không cam kết một bản ghi stdout giống hệt trên mọi máy.

Ví dụ:

```xml
<target name="inspect-log-levels">
    <echo level="error" message="[inspect] error"/>
    <echo level="warning" message="[inspect] warning"/>
    <echo level="info" message="[inspect] info"/>
    <echo level="verbose" message="[inspect] verbose"/>
    <echo level="debug" message="[inspect] debug"/>
</target>
```

Chạy lần lượt:

```bash
ant -q inspect-log-levels
ant inspect-log-levels
ant -v inspect-log-levels
ant -d inspect-log-levels
```

Ở chế độ mặc định, ba thông điệp `error`, `warning` và `info` có thể được hiển thị; hai thông điệp cuối sẽ xuất hiện khi nâng ngưỡng chi tiết phù hợp. Tác vụ `echo` vẫn được **thực thi** ngay cả khi logger không hiển thị thông điệp của nó.

### 3.2. `level="error"` không làm build thất bại

Đây là khác biệt quan trọng giữa **ghi log** và **điều khiển luồng thực thi**:

```xml
<target name="wrong-error-handling">
    <echo level="error" message="[check] Thiếu tệp cấu hình"/>
    <echo level="info" message="[check] Ant vẫn có thể chạy đến đây"/>
</target>
```

Thông báo có mức `error` nhưng riêng `echo` không ném lỗi và không trả trạng thái thất bại cho build. Nếu thiếu đầu vào bắt buộc, dùng `<fail>`:

```xml
<target name="check-input">
    <available file="config/app.properties"
               type="file"
               property="app.config.exists"/>

    <fail unless="app.config.exists"
          message="[check-input] Thiếu config/app.properties; hãy bổ sung trước khi build."/>

    <echo level="info"
          message="[check-input] Đã kiểm tra tệp cấu hình bắt buộc"/>
</target>
```

`<fail>` dừng luồng build bằng lỗi và cung cấp thông điệp cho logger. Nếu `config/app.properties` không tồn tại, lệnh phía sau `<fail>` sẽ không chạy. Thông thường không cần thêm một `echo level="error"` ngay trước `<fail>` với đúng cùng nội dung vì nó tạo log trùng.

## 4. Tổ chức thông điệp theo ngữ cảnh `target`

Ant hiển thị tên `target` tại một số vị trí trong log mặc định, nhưng **không tự động chèn tên target đang chạy vào chuỗi message của từng `echo`**. Điều này càng quan trọng khi log bị gom từ nhiều job, sao chép một đoạn ngắn hoặc xuất qua logger khác.

Một mẫu dễ tra cứu là:

```text
[target][môi-trường] Sự kiện + đối tượng + kết quả/đề xuất xử lý
```

Ví dụ:

- `[prepare][ci] Tạo thư mục build/classes` — đã biết bước và môi trường.
- `[compile][ci] Bắt đầu biên dịch từ src` — có hành động và nguồn.
- `[package][ci] Đã tạo dist/demo.jar` — có kết quả cụ thể.
- `[verify][ci] Thiếu config/app.properties; hãy bổ sung tệp` — có lỗi và hướng xử lý.

Không nhất thiết phải đưa mọi thông tin vào mọi dòng. Chẳng hạn, thông điệp `verbose` mô tả đường dẫn có thể ngắn hơn, miễn là vẫn xác định được `target` tạo ra nó.

### 4.1. Ví dụ `build.xml` đầy đủ

Ví dụ sau giả định một dự án Java nhỏ có mã nguồn trong `src/` và được chạy với JDK. Tệp `build.xml` có thể đặt ở thư mục gốc của dự án:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-log-demo" default="package" basedir=".">

    <!-- Giá trị -Dbuild.profile=ci trên dòng lệnh có quyền ưu tiên. -->
    <property name="build.profile" value="local"/>
    <property name="src.dir" location="src"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="dist"/>
    <property name="artifact.name" value="demo"/>

    <target name="prepare">
        <echo level="info"
              message="[prepare][${build.profile}] Chuẩn bị ${classes.dir}"/>
        <mkdir dir="${classes.dir}"/>
        <echo level="verbose"
              message="[prepare] Thư mục output: ${classes.dir}"/>
    </target>

    <target name="compile" depends="prepare">
        <available file="${src.dir}"
                   type="dir"
                   property="src.dir.exists"/>

        <fail unless="src.dir.exists"
              message="[compile] Thiếu ${src.dir}; hãy tạo thư mục mã nguồn."/>

        <echo level="info"
              message="[compile][${build.profile}] Bắt đầu biên dịch"/>

        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"/>

        <echo level="info"
              message="[compile] Biên dịch hoàn tất"/>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="${dist.dir}"/>

        <echo level="info"
              message="[package][${build.profile}] Tạo JAR"/>

        <jar destfile="${dist.dir}/${artifact.name}.jar"
             basedir="${classes.dir}"/>

        <echo level="info"
              message="[package] Đã tạo ${dist.dir}/${artifact.name}.jar"/>
        <echo level="debug"
              message="[package] Nguồn dữ liệu JAR: ${classes.dir}"/>
    </target>

</project>
```

Chạy:

```bash
ant package
ant -Dbuild.profile=ci package
ant -q package
ant -v package
```

Luồng phụ thuộc là `package → compile → prepare`: Ant thực thi `prepare` trước, kế đến `compile` rồi `package`. Trong build bình thường, các `echo level="info"` cho biết bước đang chạy; `-v` bổ sung thông điệp `verbose`. Nếu thư mục `src/` thiếu, `<fail>` trong `compile` nêu rõ nguyên nhân và `package` không được thực thi.

Chú ý rằng thông điệp “Đã tạo JAR” nằm **sau** tác vụ `<jar>`. Cách đặt này giúp tránh công bố thành công trước khi thao tác thực sự kết thúc. Cũng nên dùng đường dẫn của artifact ngay trong câu thông báo để người xử lý CI biết phải kiểm tra tệp nào.

### 4.2. Chọn thời điểm phát thông báo

| Vị trí trong target | Nội dung nên ghi | Lý do |
| --- | --- | --- |
| Trước một tác vụ quan trọng | `Bắt đầu biên dịch từ src` | Dễ xác định bước cuối cùng trước khi gặp lỗi |
| Sau khi tác vụ hoàn thành | `Đã tạo dist/demo.jar` | Không thông báo thành công quá sớm |
| Khi có tình huống bất thường nhưng được chấp nhận | `Không tìm thấy tài liệu tùy chọn; bỏ qua` | Giúp giải thích vì sao kết quả thiếu một phần |
| Khi điều tra chi tiết | `Lấy class từ build/classes` | Có thể lọc khỏi log thông thường |
| Khi điều kiện bắt buộc không đạt | `<fail message="..."/>` | Dừng build và truyền nguyên nhân rõ ràng |

Với `target` có `depends`, log có thể xen với thông báo do tác vụ Ant khác sinh ra. Tiền tố ngữ cảnh trong `message` giúp tìm lại sự kiện dù người đọc chỉ có một trích đoạn.

## 5. Tránh lặp tiền tố bằng `macrodef`

Trong build lớn, nhiều `target` dùng chung định dạng log. Có thể định nghĩa macro một lần ở mức `project`, rồi truyền tên `target` và thông điệp tại từng nơi gọi:

```xml
<!-- Đặt ở trong <project>, bên ngoài các <target>. -->
<macrodef name="log-step">
    <attribute name="area"/>
    <attribute name="message"/>
    <attribute name="level" default="info"/>
    <sequential>
        <echo level="@{level}"
              message="[@{area}][${build.profile}] @{message}"/>
    </sequential>
</macrodef>

<target name="verify-artifact" depends="package">
    <log-step area="verify-artifact"
              message="Kiểm tra tệp JAR đầu ra"/>

    <available file="${dist.dir}/${artifact.name}.jar"
               property="artifact.exists"/>

    <fail unless="artifact.exists"
          message="[verify-artifact] Không tìm thấy tệp JAR đầu ra"/>

    <log-step area="verify-artifact"
              level="verbose"
              message="Tệp JAR hiện diện tại ${dist.dir}"/>
</target>
```

Đoạn này được dùng cùng `<project>` và các property của ví dụ trước; hãy thêm macro trước các `target`, sau đó thêm `target verify-artifact` vào trong dự án. Gọi `ant verify-artifact` sẽ tự chạy phần phụ thuộc `package` rồi kiểm tra tệp JAR.

Trong `macrodef`, cú pháp `@{area}` biểu thị **tham số macro**, còn `${build.profile}` biểu thị **property của Ant**. Hai cơ chế thay thế giá trị khác nhau. Việc đưa `area` thành tham số cũng giải quyết vấn đề Ant không cung cấp một property chung tự thay đổi thành tên của target đang chạy ở mọi vị trí.

Chỉ cần dùng macro khi nhiều target thực sự chia sẻ một quy ước. Với build nhỏ, một `<echo level="info" message="[compile] ..."/>` thường dễ hiểu hơn.

## 6. Kết hợp log với điều kiện và đường đi thực thi

Có ba tình huống cần phân biệt:

**Target không chạy.** Nếu `target` không nằm trong chuỗi phụ thuộc của lệnh được gọi, các `echo` trong nó cũng không chạy.

**Target bị bỏ qua bởi `if` / `unless`.** Các thuộc tính này xét **sự tồn tại của property** trong cú pháp target truyền thống, không đơn thuần xét chuỗi giá trị có bằng `true` hay không. Vì vậy `-Dskip=false` vẫn tạo ra property `skip`, có thể làm một `target unless="skip"` bị bỏ qua. Đừng chỉ dựa vào việc không thấy thông điệp để kết luận rằng tác vụ đã chạy.

**Tác vụ thất bại trước thông điệp cuối.** Với chuỗi:

```xml
<echo level="info" message="[compile] Bắt đầu"/>
<javac srcdir="src" destdir="build/classes"
       includeantruntime="false"/>
<echo level="info" message="[compile] Hoàn thành"/>
```

nếu `<javac>` thất bại, thông báo “Hoàn thành” không xuất hiện. Đây là hành vi mong muốn. Để dễ đọc, đừng in `Hoàn thành` trước tác vụ mà nó đang mô tả.

Một cảnh báo có điều kiện cũng nên chỉ xuất hiện khi bất thường thật sự xảy ra. Ví dụ độc lập dưới đây dùng `available` để xác định sự tồn tại của tài liệu tùy chọn:

```xml
<project name="optional-docs" default="check-docs">
    <available file="docs/README.md" property="docs.exists"/>

    <target name="warn-missing-docs" unless="docs.exists">
        <echo level="warning"
              message="[warn-missing-docs] Không có docs/README.md; bỏ qua bước đóng gói tài liệu"/>
    </target>

    <target name="check-docs" depends="warn-missing-docs">
        <echo level="info"
              message="[check-docs] Đã kết thúc kiểm tra tài liệu tùy chọn"/>
    </target>
</project>
```

`warning` ở đây hợp lý vì tài liệu là **tùy chọn**. Nếu tài liệu là đầu vào bắt buộc, chuyển sang `<fail>` với lý do rõ ràng.

## 7. Ghi thông báo ra tệp và thu thập log của toàn build

### 7.1. Dùng `echo file="..."` khi cần tạo tệp văn bản

`echo` cũng có thể viết trực tiếp vào tệp:

```xml
<target name="write-status">
    <mkdir dir="build/logs"/>
    <echo file="build/logs/status.txt"
          append="true"
          encoding="UTF-8"
          message="[write-status] Bước xử lý đã hoàn thành"/>
</target>
```

Ở đây:

- `file` là tệp đích thay vì nơi hiển thị thông thường của hệ thống logger.
- `append="true"` thêm nội dung vào cuối tệp; nếu không dùng `append`, hành vi mặc định là ghi đè nội dung của tệp đích.
- `encoding="UTF-8"` chủ động chọn bộ mã cho nội dung ghi tệp trên các phiên bản Ant hỗ trợ thuộc tính này.

Đây là cách tạo một tệp trạng thái hoặc một vài dòng thông báo theo định dạng mong muốn. Nó **không tự động thu thập** mọi thông báo của `<javac>`, `<copy>`, `<jar>` và các task khác. Ngoài ra, thông điệp đã chuyển vào `file` không nên được coi như một bản ghi đồng thời trên console.

### 7.2. Thu thập log toàn bộ phiên chạy

Nếu muốn lưu cả quá trình build để đọc sau, dùng tùy chọn dòng lệnh:

```bash
ant -Dbuild.profile=ci -logfile build.log package
```

Tùy chọn `-logfile` (viết ngắn là `-l`) đưa log của Ant vào tệp được chỉ định. Trong môi trường CI, có thể lưu `build.log` như một artifact chẩn đoán, theo chính sách lưu trữ của dự án.

Ant cũng có tác vụ `<record>` để bắt đầu hoặc dừng ghi log trong một phần quy trình build. Chọn `echo file="..."` khi cần một **tệp nội dung do mình kiểm soát**, còn chọn logger, `-logfile` hoặc `record` khi cần **thu thập dòng sự kiện của build**. Đừng nhầm hai mục đích này.

## 8. Quy ước log cho pipeline và bảo mật

Để một dự án có log dễ đọc trong nhiều môi trường, có thể áp dụng quy tắc sau:

| Sự kiện | Mức đề xuất | Lưu ý |
| --- | --- | --- |
| Bắt đầu / kết thúc target quan trọng | `info` | Ghi tên target và artifact nếu có |
| Đường dẫn build, lựa chọn cấu hình không nhạy cảm | `verbose` | Chỉ mở khi điều tra |
| Thông số sâu phục vụ chẩn đoán | `debug` | Có thể rất nhiều dòng |
| Bỏ qua bước tùy chọn vì thiếu đầu vào | `warning` | Nêu việc bỏ qua và hậu quả |
| Thiếu điều kiện bắt buộc | `fail` và thông báo lỗi | Không chỉ `echo level="error"` |
| Điều kiện bình thường, không hữu ích để theo dõi | Có thể không cần log | Tránh in quá mức |

Giữ nội dung log ngắn nhưng đủ trả lời ba câu hỏi: **target nào? chuyện gì? cần làm gì tiếp?** Chẳng hạn, `[verify] Thiếu output` kém hữu ích hơn `[verify] Không tìm thấy dist/demo.jar; hãy kiểm tra bước package`.

Không in mật khẩu, token, khóa API, biến môi trường có bí mật hoặc toàn bộ dòng lệnh chứa thông tin xác thực. `echo` không phải cơ chế che giấu bí mật; mức `debug` hay việc ghi log vào tệp cũng không làm dữ liệu đó an toàn. Khi chia sẻ `build.log`, cần xem xét những thông tin do **các task khác** đã ghi ra, không chỉ những dòng `echo` do mình viết.

## 9. Chẩn đoán khi thiếu hoặc thừa thông báo

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không thấy thông báo `info` | Chạy với `-quiet` hoặc logger khác lọc `info` | Thử `ant` mặc định; kiểm tra cấu hình logger |
| Không thấy thông báo `verbose` / `debug` | Ngưỡng log chưa đủ chi tiết | Dùng `-v` hoặc `-d` khi cần |
| Không thấy bất kỳ thông báo nào của target | Target không nằm trong chuỗi chạy, bị điều kiện bỏ qua hoặc build thất bại sớm | Kiểm tra `default`, `depends`, `if`, `unless` và lỗi trước đó |
| Thông báo bình thường vẫn xuất hiện dưới `-q` | `echo` đang dùng mặc định `warning` | Chỉ định `level="info"` |
| Console in nguyên `${some.property}` | Property chưa được khai báo đúng tên hoặc chưa có tại thời điểm sử dụng | Kiểm tra tên, thứ tự khai báo và giá trị `-D` |
| Build vẫn báo thành công sau câu có mức `error` | `echo` chỉ ghi log | Dùng `<fail>` hoặc để tác vụ thực sự ném lỗi |
| Nhiều target đều in “Xong” | Thông điệp không có ngữ cảnh | Thêm tiền tố target và tên artifact |
| Tệp log thiếu thông báo của task khác | Đang dùng `echo file="..."` cho một thông điệp đơn lẻ | Dùng `-logfile` hoặc recorder phù hợp |
| Log trên CI quá dài | Lạm dụng `info`/`warning` cho chi tiết lặp lại | Chuyển chi tiết sang `verbose`/`debug`, giảm log trong vòng lặp |

Nếu vừa không thấy `echo` vừa không thấy thông báo của tác vụ khác, hãy kiểm tra lệnh Ant thực tế và logger/listener mà môi trường đang sử dụng trước khi sửa nội dung các `target`.

## 10. Bài thực hành ngắn

**Bài 1 — Quan sát mức log.** Tạo `build.xml` với target `inspect-log-levels` ở mục 3. Chạy với `-q`, mặc định, `-v` và `-d`. Ghi nhận những mức log hiển thị. Sau đó bỏ `level` của một `echo` và quan sát vì sao nó vẫn xuất hiện trong chế độ `-q`.

**Bài 2 — Gắn ngữ cảnh target.** Dùng ví dụ `ant-log-demo` ở mục 4:

1. Chạy `ant -Dbuild.profile=local package` và xác định thông điệp từ từng `target`.
2. Chạy `ant -Dbuild.profile=ci -v package`; tìm dòng nói rõ thư mục output.
3. Tạm đổi tên hoặc bỏ thư mục `src/`, chạy lại để quan sát thông điệp của `<fail>` và kiểm tra rằng câu “Đã tạo JAR” không được in.
4. Thêm `macrodef log-step` vào project, dùng nó cho một `target` khác và so sánh định dạng các dòng log.

Khi thiết kế build thực tế, hãy dùng `info` cho các cột mốc cần thấy mỗi ngày, `verbose`/`debug` cho dữ liệu điều tra, `warning` cho tình huống bất thường có thể tiếp tục, và `<fail>` khi cần báo lỗi để chặn build. Mỗi thông báo nên gắn với `target` và sự kiện cụ thể để người đọc hiểu tiến trình ngay cả khi chỉ có một phần log.
