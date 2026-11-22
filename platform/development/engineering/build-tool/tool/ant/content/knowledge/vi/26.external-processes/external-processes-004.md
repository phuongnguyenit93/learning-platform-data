# Thu thập output, error, resultproperty và chuyển hướng bằng redirector

Khi Apache Ant gọi một chương trình bên ngoài bằng task `<exec>`, chương trình đó có thể tạo ra ba loại kết quả khác nhau: dữ liệu ghi vào **standard output (stdout)**, thông báo ghi vào **standard error (stderr)** và **mã thoát (exit code)** cho biết tiến trình kết thúc như thế nào. Ba loại kết quả này phục vụ các mục đích khác nhau, vì vậy cần thu thập và xử lý chúng đúng cách.

Ant cung cấp các thuộc tính như `output`, `error`, `outputproperty`, `errorproperty` và `resultproperty` để lưu kết quả. Khi cần cấu hình chuyển hướng phức tạp hơn, có thể dùng phần tử lồng `<redirector>`. Hiểu rõ sự khác nhau giữa output, error và resultproperty giúp buildfile vừa lưu được log để chẩn đoán, vừa quyết định chính xác khi nào một target phải thất bại.

## 1. Ba kênh kết quả của một tiến trình ngoài

Một chương trình command line thường giao tiếp với tiến trình gọi qua ba kênh:

| Kênh | Tên | Vai trò | Ví dụ |
|---|---|---|---|
| Luồng đầu ra chuẩn | stdout | Dữ liệu hoặc kết quả chính mà chương trình tạo ra | Danh sách file, JSON, phiên bản công cụ |
| Luồng lỗi chuẩn | stderr | Cảnh báo, chẩn đoán hoặc thông báo lỗi | Cảnh báo cấu hình, stack trace, lỗi kết nối |
| Mã thoát | exit code | Giá trị số chương trình trả về khi kết thúc | `0` thường biểu thị thành công; khác `0` thường biểu thị lỗi |

Ví dụ chạy một lệnh kiểm tra:

```bash
tool --version
```

Chương trình có thể in phiên bản ra stdout và trả mã thoát `0`. Một lệnh khác có thể in thông báo lỗi ra stderr và trả mã thoát `2`. Cũng có trường hợp chương trình in một cảnh báo ra stderr nhưng vẫn trả `0`; việc có dữ liệu trên stderr không tự động có nghĩa tiến trình thất bại.

Vì vậy, không nên đồng nhất ba khái niệm:

- `output`/`outputproperty` thu thập stdout.
- `error`/`errorproperty` thu thập stderr.
- `resultproperty` thu thập mã thoát của tiến trình.

## 2. Gọi chương trình ngoài bằng task exec

Task `<exec>` khởi chạy một chương trình bên ngoài Ant. Ví dụ:

```xml
<exec executable="java" failonerror="true">
    <arg value="-version"/>
</exec>
```

`executable` chỉ tên chương trình cần chạy. Các đối số được truyền bằng phần tử `<arg>`. Cách tách chương trình và đối số giúp Ant truyền từng đối số riêng, tránh nhiều lỗi trích dẫn khi có khoảng trắng trong đường dẫn.

Một số thuộc tính thường dùng của `<exec>`:

| Thuộc tính | Mục đích |
|---|---|
| `executable` | Chương trình cần khởi chạy |
| `dir` | Thư mục làm việc của tiến trình |
| `output` | File nhận stdout |
| `error` | File nhận stderr |
| `outputproperty` | Property nhận nội dung stdout |
| `errorproperty` | Property nhận nội dung stderr |
| `resultproperty` | Property nhận mã thoát |
| `failonerror` | Làm task/build thất bại khi tiến trình trả mã thoát khác `0` |
| `failifexecutionfails` | Làm task thất bại nếu Ant không thể khởi chạy tiến trình |
| `append` | Ghi nối vào file output/error thay vì ghi đè |
| `logError` | Quyết định có đưa stderr đã chuyển hướng vào log Ant hay không |
| `timeout` | Giới hạn thời gian chờ tiến trình, tính bằng mili giây |
| `input` | File được dùng làm stdin của tiến trình |
| `inputstring` | Chuỗi được dùng làm stdin của tiến trình |
| `spawn` | Khởi chạy tiến trình tách khỏi Ant, không chờ kết quả theo cách thông thường |

Task `<exec>` không tự động chạy lệnh thông qua shell trên mọi hệ điều hành. Nếu cần pipe, wildcard do shell mở rộng hoặc cú pháp shell đặc biệt, phải gọi shell tương ứng một cách tường minh; cách đó thường làm buildfile phụ thuộc nền tảng. Với lệnh đơn giản, nên dùng `executable` cùng các phần tử `<arg>`.

### 2.1. Dùng arg để truyền đối số

Ví dụ gọi Git với một thư mục làm việc cụ thể:

```xml
<exec executable="git" dir="${basedir}" failonerror="true">
    <arg value="status"/>
    <arg value="--short"/>
</exec>
```

Mỗi `<arg value="..."/>` tương ứng một đối số. Nếu một đối số chứa khoảng trắng, `value` giữ nó thành một đối số duy nhất:

```xml
<arg value="--message"/>
<arg value="Release candidate 1"/>
```

Không cần tự thêm dấu nháy quanh `Release candidate 1` trong giá trị `arg`; Ant truyền chuỗi đó như một đối số. Việc tự nhúng dấu nháy có thể khiến dấu nháy trở thành ký tự thật trong đối số.

## 3. Chuyển stdout vào file bằng output

Thuộc tính `output` chỉ định file nhận nội dung stdout của tiến trình.

Ví dụ:

```xml
<mkdir dir="build/logs"/>

<exec executable="git"
      output="build/logs/git-version.out"
      failonerror="true">
    <arg value="--version"/>
</exec>
```

Ant ghi stdout vào `build/logs/git-version.out`. Ví dụ dùng `git --version`, lệnh thường ghi chuỗi phiên bản ra stdout. File đích phù hợp khi:

- Output dài hoặc có nhiều dòng.
- Muốn lưu log làm artifact của CI.
- Cần mở và tìm kiếm nội dung sau khi build kết thúc.
- Không muốn giữ toàn bộ nội dung lớn trong property của Ant.

Nếu chương trình không ghi gì vào stdout, file output có thể rỗng hoặc việc tạo file phụ thuộc cấu hình redirector. Nếu quy trình cần luôn có file rỗng để biểu thị lần chạy, có thể xem thuộc tính `createemptyfiles` của redirector.

## 4. Chuyển stderr vào file bằng error

Thuộc tính `error` chỉ định file nhận stderr.

```xml
<exec executable="tool"
      output="build/logs/tool.out"
      error="build/logs/tool.err"
      failonerror="false">
    <arg value="validate"/>
</exec>
```

Trong ví dụ:

- stdout được ghi vào `tool.out`.
- stderr được ghi vào `tool.err`.
- Task không tự thất bại chỉ vì tiến trình trả mã thoát khác `0`, do `failonerror="false"`.

Lưu riêng hai luồng giúp chẩn đoán dễ hơn. Một số chương trình ghi cả tiến trình thông thường vào stderr, vì vậy hãy xem mã thoát để xác định thành công hay thất bại, không chỉ nhìn xem file `.err` có nội dung hay không.

### 4.1. Khi muốn gộp stderr vào log Ant

Thuộc tính `logError` điều khiển việc đưa stderr vào log của Ant trong trường hợp đã chuyển hướng output/error. Ví dụ:

```xml
<exec executable="tool"
      error="build/logs/tool.err"
      logError="true">
    <arg value="check"/>
</exec>
```

Khi bật, stderr vẫn được chuyển đến đích đã cấu hình và được ghi vào log Ant theo cơ chế của task. Điều này hữu ích khi muốn lưu file lỗi riêng nhưng vẫn nhìn thấy cảnh báo trong console CI.

Không nên bật log chi tiết cho chương trình có thể in secret, token truy cập hoặc dữ liệu nhạy cảm ra stderr.

## 5. Ghi nối bằng append

Mặc định, khi redirector ghi vào file, nội dung cũ có thể bị thay thế. Thuộc tính `append="true"` yêu cầu ghi nối vào cuối file hiện có.

Ví dụ:

```xml
<exec executable="tool"
      output="build/logs/validation.log"
      error="build/logs/validation-error.log"
      append="true">
    <arg value="validate"/>
</exec>
```

Ghi nối phù hợp khi nhiều lần gọi cần đóng góp vào cùng một log trong một lượt build. Tuy nhiên, cần cân nhắc:

- Nếu không xóa log cũ, file có thể chứa dữ liệu từ nhiều lần build.
- Log lớn dần có thể làm CI lưu artifact quá nặng.
- Khi nhiều tiến trình cùng ghi một file, thứ tự dòng có thể khó dự đoán.
- Nên tạo log mới cho mỗi build hoặc xóa file trước khi bắt đầu nếu muốn kết quả độc lập.

Ví dụ xóa log trước khi chạy:

```xml
<target name="prepare-tool-logs">
    <mkdir dir="build/logs"/>
    <delete file="build/logs/validation.log" quiet="true"/>
    <delete file="build/logs/validation-error.log" quiet="true"/>
</target>
```

Sau đó target gọi `<exec>` phụ thuộc vào `prepare-tool-logs`.

## 6. Thu thập stdout vào property bằng outputproperty

Thuộc tính `outputproperty` lưu stdout vào một property của Ant thay vì ghi ra file.

```xml
<exec executable="git"
      outputproperty="git.version.output"
      failonerror="true">
    <arg value="--version"/>
</exec>

<echo message="Captured output: ${git.version.output}"/>
```

Property phù hợp khi output ngắn và cần dùng ngay trong các bước tiếp theo của build, ví dụ:

- Đọc một giá trị phiên bản.
- Thu thập một chuỗi nhận diện môi trường.
- Lưu kết quả của một lệnh truy vấn ngắn.
- Hiển thị thông tin trong log Ant.

Không nên dùng property để giữ log rất lớn. Property nằm trong bộ nhớ và không phải kho lưu trữ có thể cập nhật tùy ý.

### 6.1. Property của Ant là bất biến

Ant property thông thường chỉ được gán lần đầu. Nếu `git.version.output` đã có giá trị, một lần gọi sau không thể ghi đè nó bằng `outputproperty` cùng tên.

Ví dụ, nếu target được gọi nhiều lần trong cùng project và cùng dùng `outputproperty="tool.output"`, property có thể vẫn giữ kết quả của lần đầu tiên được gán. Đừng giả định outputproperty hoạt động như một biến có thể cập nhật sau mỗi lần thực thi.

Nếu cần lưu nhiều kết quả, hãy dùng file riêng cho mỗi lần gọi, tên property khác nhau, hoặc một cơ chế lưu dữ liệu phù hợp khác. Có thể dùng property động theo một định danh đã biết khi cấu trúc build cho phép.

## 7. Thu thập stderr vào property bằng errorproperty

`errorproperty` lưu nội dung stderr vào property:

```xml
<exec executable="tool"
      outputproperty="tool.stdout"
      errorproperty="tool.stderr"
      failonerror="false">
    <arg value="inspect"/>
</exec>
```

Sau khi tiến trình kết thúc, có thể sử dụng các property trong log hoặc điều kiện build:

```xml
<echo message="Tool stdout: ${tool.stdout}"/>
<echo message="Tool stderr: ${tool.stderr}"/>
```

`outputproperty` và `errorproperty` không phải nơi lưu mã thoát. Chúng giữ nội dung văn bản của hai luồng. Mã thoát phải được thu thập bằng `resultproperty`.

Không nên in toàn bộ stderr vào console nếu có khả năng chứa dữ liệu nhạy cảm. Trong CI, có thể lưu file log hạn chế quyền truy cập thay vì đưa nội dung vào property rồi echo ra màn hình.

## 8. Thu thập mã thoát bằng resultproperty

`resultproperty` lưu mã thoát mà tiến trình trả về khi kết thúc.

```xml
<exec executable="tool"
      resultproperty="tool.exit.code"
      failonerror="false">
    <arg value="validate"/>
</exec>

<echo message="Tool exit code: ${tool.exit.code}"/>
```

Quy ước thường gặp:

- `0`: lệnh hoàn thành thành công.
- Khác `0`: lệnh báo một trạng thái khác, thường là lỗi hoặc điều kiện đặc biệt.

Mã thoát cụ thể phụ thuộc chương trình. Một số công cụ dùng nhiều mã khác nhau để biểu thị lỗi cú pháp, lỗi đầu vào, cảnh báo bị nâng thành lỗi hoặc trạng thái “có phát hiện”. Cần xem tài liệu của chương trình để hiểu ý nghĩa từng mã.

### 8.1. resultproperty khác outputproperty như thế nào?

| Thuộc tính | Giá trị được lưu | Ví dụ |
|---|---|---|
| `outputproperty` | Nội dung stdout | `"Found 12 files"` |
| `errorproperty` | Nội dung stderr | `"Warning: deprecated option"` |
| `resultproperty` | Mã thoát dạng số/chuỗi biểu diễn số | `0`, `1`, `2` |

Không dùng `resultproperty` để lưu thông báo lỗi. Ngược lại, không nên suy luận mã thoát chỉ từ việc outputproperty có rỗng hay không.

## 9. Phân biệt failonerror và failifexecutionfails

Hai thuộc tính này điều khiển hai tình huống khác nhau.

### 9.1. failonerror

`failonerror` quyết định task có thất bại khi tiến trình đã chạy xong nhưng trả mã thoát khác `0` hay không.

```xml
<exec executable="tool" failonerror="true">
    <arg value="validate"/>
</exec>
```

Khi tiến trình trả mã khác `0`, Ant ném lỗi build và target thất bại. Đây là lựa chọn phù hợp khi mọi mã thoát khác `0` đều phải chặn build.

Mặc định `failonerror` là `false`, do đó nếu không bật, một tiến trình có thể trả mã khác `0` mà target vẫn tiếp tục. Nếu muốn tự quyết định dựa trên mã cụ thể, hãy để `failonerror="false"` và dùng `resultproperty`.

### 9.2. failifexecutionfails

`failifexecutionfails` điều khiển việc Ant có thất bại nếu không thể khởi chạy tiến trình hay không. Ví dụ:

- Không tìm thấy executable.
- Không có quyền thực thi.
- Không thể tạo tiến trình do lỗi môi trường.

Mặc định thuộc tính này là `true`. Nó độc lập với `failonerror`: chương trình phải khởi chạy được thì mới có mã thoát để kiểm tra.

Ví dụ:

```xml
<exec executable="tool"
      failifexecutionfails="true"
      failonerror="false"
      resultproperty="tool.exit.code">
    <arg value="inspect"/>
</exec>
```

Trong ví dụ, Ant sẽ báo lỗi nếu không thể khởi chạy `tool`; nhưng nếu `tool` chạy được và trả mã khác `0`, task không tự thất bại vì `failonerror` đang là `false`. Buildfile có thể đọc `tool.exit.code` để quyết định bước tiếp theo.

## 10. Kiểm tra resultproperty bằng condition và fail

Khi cần xử lý mã thoát theo quy tắc riêng, có thể dùng `condition` và `fail`.

Ví dụ: chỉ chấp nhận mã `0`, còn mọi mã khác đều làm build thất bại với thông báo có đường dẫn log:

```xml
<target name="validate-external-tool">
    <exec executable="tool"
          dir="${basedir}"
          failonerror="false"
          resultproperty="validation.exit.code"
          output="build/logs/validation.out"
          error="build/logs/validation.err">
        <arg value="validate"/>
    </exec>

    <condition property="validation.failed">
        <not>
            <equals arg1="${validation.exit.code}" arg2="0"/>
        </not>
    </condition>

    <fail if="validation.failed"
          message="External validation failed. See build/logs/validation.out and validation.err."/>
</target>
```

Target này thực hiện theo trình tự:

1. Chạy công cụ với `failonerror="false"` để Ant không dừng ngay khi nhận mã khác `0`.
2. Ghi stdout và stderr vào hai file riêng.
3. Lưu mã thoát vào `validation.exit.code`.
4. Dùng `condition` để đặt property `validation.failed` nếu mã khác `0`.
5. Dùng `fail` để dừng build với thông báo chỉ rõ vị trí log.

Trong ví dụ này, nếu không thể khởi chạy executable, `failifexecutionfails` mặc định vẫn khiến task thất bại ngay. Phần kiểm tra condition xử lý trường hợp chương trình đã chạy và trả mã thoát.

### 10.1. Chấp nhận một số mã thoát đặc biệt

Giả sử công cụ dùng:

- `0`: không có phát hiện.
- `1`: có phát hiện cần xem xét nhưng không phải lỗi chạy.
- `2`: lỗi đầu vào hoặc lỗi thực thi.

Buildfile có thể chấp nhận `0` và `1`, chỉ thất bại với `2` hoặc mã khác. Ví dụ:

```xml
<exec executable="scanner"
      failonerror="false"
      resultproperty="scanner.exit.code"
      output="build/logs/scanner.out"
      error="build/logs/scanner.err">
    <arg value="scan"/>
</exec>

<condition property="scanner.fatal">
    <not>
        <or>
            <equals arg1="${scanner.exit.code}" arg2="0"/>
            <equals arg1="${scanner.exit.code}" arg2="1"/>
        </or>
    </not>
</condition>

<fail if="scanner.fatal"
      message="Scanner could not complete. See build/logs/scanner.err."/>
```

Chỉ áp dụng quy tắc này khi tài liệu của scanner xác nhận mã `1` là trạng thái có thể chấp nhận. Không tự suy đoán ý nghĩa mã thoát của chương trình.

## 11. Chuyển hướng bằng nested redirector

Các thuộc tính `output`, `error`, `input`, `outputproperty`, `errorproperty` và encoding là các cách cấu hình chuyển hướng phổ biến. Khi cần nhóm các thiết lập này thành một cấu hình rõ ràng hoặc sử dụng các khả năng bổ sung, task hỗ trợ redirector có thể nhận phần tử lồng `<redirector>`.

Ví dụ:

```xml
<exec executable="tool" failonerror="false">
    <arg value="validate"/>

    <redirector output="build/logs/tool.out"
                error="build/logs/tool.err"
                append="false"
                logError="true"
                outputEncoding="UTF-8"
                errorEncoding="UTF-8"/>
</exec>
```

Redirector gom cấu hình chuyển hướng luồng vào một phần tử riêng. Nó có thể cấu hình nơi nhận stdout/stderr, nguồn stdin, chế độ ghi nối và encoding. Các thuộc tính cụ thể được hỗ trợ phụ thuộc task và phiên bản Ant; hãy kiểm tra tài liệu của task đang sử dụng.

### 11.1. Khi nào dùng thuộc tính trực tiếp, khi nào dùng redirector?

| Cách cấu hình | Phù hợp khi |
|---|---|
| Thuộc tính trực tiếp của `<exec>` | Chỉ cần một hoặc hai đường dẫn output/error hoặc property đơn giản |
| Nested `<redirector>` | Cần nhóm nhiều tùy chọn chuyển hướng, cấu hình encoding hoặc input/output phức tạp |
| `outputproperty`/`errorproperty` | Output ngắn cần được dùng trong logic build |
| `output`/`error` | Output dài cần được lưu thành file log |

Không cần dùng redirector cho mọi lệnh. Với một task đơn giản, thuộc tính trực tiếp dễ đọc hơn. Khi cấu hình chuyển hướng dài, phần tử lồng làm rõ ranh giới giữa tham số của tiến trình và cách thu thập dữ liệu.

### 11.2. Encoding của output và error

Nếu chương trình tạo văn bản UTF-8, có thể cấu hình encoding tương ứng để Ant giải mã và ghi đúng nội dung:

```xml
<exec executable="tool" failonerror="false">
    <arg value="report"/>
    <redirector output="build/logs/report.out"
                error="build/logs/report.err"
                outputEncoding="UTF-8"
                errorEncoding="UTF-8"/>
</exec>
```

Encoding cần khớp với encoding mà chương trình thực sự phát ra. Nếu công cụ dùng encoding khác, đặt UTF-8 một cách tùy tiện có thể làm hỏng dấu tiếng Việt hoặc ký tự ngoài ASCII.

## 12. Chuyển stdin vào tiến trình bằng input và inputstring

Redirector không chỉ xử lý output. Có thể cấp dữ liệu đầu vào cho tiến trình qua:

- `input`: đọc stdin từ một file.
- `inputstring`: gửi một chuỗi làm stdin.

Ví dụ dùng file input:

```xml
<exec executable="processor" failonerror="true">
    <arg value="--stdin"/>
    <redirector input="config/input.txt"
                output="build/logs/processor.out"
                error="build/logs/processor.err"/>
</exec>
```

Ví dụ dùng chuỗi input:

```xml
<exec executable="processor" failonerror="true">
    <arg value="--stdin"/>
    <redirector inputstring="name=inventory&#10;mode=release&#10;"
                output="build/logs/processor.out"
                error="build/logs/processor.err"/>
</exec>
```

`inputstring` hữu ích với dữ liệu nhỏ. Với dữ liệu nhiều dòng hoặc lớn, nên dùng file input để tránh nhúng nội dung dài vào buildfile.

Không nên truyền mật khẩu hoặc secret trực tiếp qua `inputstring` nếu buildfile, log hoặc tiến trình có thể làm lộ dữ liệu đó. Hãy dùng cơ chế secret phù hợp và hạn chế log.

### 12.1. Chỉ chọn một nguồn stdin

`input` và `inputstring` cùng mô tả nguồn dữ liệu chuẩn đầu vào. Hãy chọn một cách cho mỗi lần thực thi để cấu hình rõ ràng. Nếu chương trình không cần stdin, không cần khai báo nguồn input.

## 13. Lưu stdout và stderr vào property để kiểm tra nội dung

Một số công cụ trả một giá trị nhỏ qua stdout, ví dụ chuỗi phiên bản. Có thể lấy nội dung đó rồi kiểm tra:

```xml
<exec executable="tool"
      outputproperty="tool.version"
      errorproperty="tool.version.error"
      resultproperty="tool.version.exit"
      failonerror="false">
    <arg value="--version"/>
</exec>

<echo message="Tool version: ${tool.version}"/>
```

Sau đó có thể kiểm tra mã thoát hoặc dùng điều kiện với nội dung property nếu mục đích là xác minh phiên bản. Lưu ý rằng Ant property là bất biến; hãy dùng tên property riêng cho từng lần chạy nếu cần thu thập nhiều kết quả trong cùng một project.

Đối với stdout/stderr có nhiều dòng, dữ liệu lớn hoặc cần lưu lại lâu dài, dùng file thường phù hợp hơn property.

## 14. Redirector và output của nhiều lần gọi

Khi một target gọi cùng chương trình nhiều lần, cần quyết định log được ghi riêng hay ghi nối.

### 14.1. File log riêng cho mỗi lần gọi

Ví dụ:

```xml
<exec executable="tool" output="build/logs/compile-step.out">
    <arg value="compile"/>
</exec>

<exec executable="tool" output="build/logs/package-step.out">
    <arg value="package"/>
</exec>
```

Mỗi bước có file log riêng, dễ xác định bước nào tạo thông báo.

### 14.2. Ghi nối vào cùng một log

```xml
<exec executable="tool" output="build/logs/tool.log" append="true">
    <arg value="compile"/>
</exec>

<exec executable="tool" output="build/logs/tool.log" append="true">
    <arg value="package"/>
</exec>
```

File log có nội dung từ cả hai lần gọi. Nếu cần biết phần nào thuộc bước nào, hãy thêm thông tin ngữ cảnh bằng log riêng hoặc một bước ghi tiêu đề vào file.

### 14.3. Property không phải bộ đệm có thể cộng dồn

Không dùng cùng một `outputproperty` như thể nó tự nối stdout từ nhiều lần gọi. Property của Ant chỉ được thiết lập lần đầu; lần sau không thể cập nhật giá trị đã tồn tại theo cơ chế property thông thường.

Nếu cần nối kết quả, ghi ra file với `append="true"`, hoặc dùng một cơ chế xử lý dữ liệu phù hợp khác.

## 15. Timeout và tiến trình không kết thúc

Thuộc tính `timeout` đặt giới hạn thời gian chờ tiến trình, tính bằng mili giây.

Ví dụ giới hạn 60 giây:

```xml
<exec executable="integration-test"
      timeout="60000"
      failonerror="true"
      output="build/logs/integration-test.out"
      error="build/logs/integration-test.err">
    <arg value="--batch"/>
</exec>
```

Nếu tiến trình chạy quá thời gian cho phép, Ant chấm dứt việc chờ theo cơ chế timeout của task và đánh dấu thao tác không hoàn thành bình thường. Cần xem log và tài liệu task để hiểu trạng thái cụ thể trên hệ điều hành đang dùng.

Timeout hữu ích khi:

- Gọi công cụ có thể chờ mạng hoặc dịch vụ bên ngoài.
- Chạy test tích hợp có nguy cơ treo.
- Thực hiện thao tác có giới hạn thời gian rõ ràng.
- Bảo vệ CI khỏi job chạy vô hạn.

Không nên đặt timeout quá ngắn khiến tác vụ hợp lệ bị chấm dứt trên máy CI chậm. Hãy chọn giá trị theo thời gian chạy bình thường và yêu cầu của pipeline.

## 16. Spawn và giới hạn khi cần thu thập kết quả

Thuộc tính `spawn="true"` khởi chạy tiến trình tách khỏi Ant thay vì chờ tiến trình kết thúc theo cách thông thường. Cách này phù hợp với một số tiến trình nền cần tiếp tục chạy sau khi target hoàn thành.

Tuy nhiên, khi dùng spawn, Ant không thể thu thập kết quả theo mô hình đồng bộ thông thường. Vì vậy, không nên dùng `spawn` nếu cần:

- Đọc exit code sau khi tiến trình kết thúc.
- Chờ stdout/stderr hoàn chỉnh.
- Quyết định target tiếp tục hay thất bại dựa trên `resultproperty`.
- Dùng timeout như một lệnh chạy đồng bộ.

Nếu mục tiêu là kiểm tra một lệnh, thu thập log và xử lý mã thoát, hãy để `spawn` ở mặc định `false`.

## 17. Ví dụ tổng hợp: chạy validator và lưu cả ba kết quả

Giả sử dự án có chương trình `validator` cần chạy trên thư mục `src/main`. Ta muốn:

- Lưu stdout vào file `validator.out`.
- Lưu stderr vào file `validator.err`.
- Lưu mã thoát vào property.
- Nếu mã thoát khác `0`, làm build thất bại với thông báo chỉ đến log.

Buildfile:

```xml
<property name="quality.log.dir" location="build/logs/quality"/>

<target name="prepare-validator-logs">
    <mkdir dir="${quality.log.dir}"/>
    <delete file="${quality.log.dir}/validator.out" quiet="true"/>
    <delete file="${quality.log.dir}/validator.err" quiet="true"/>
</target>

<target name="validate" depends="prepare-validator-logs">
    <exec executable="validator"
          dir="${basedir}"
          output="${quality.log.dir}/validator.out"
          error="${quality.log.dir}/validator.err"
          resultproperty="validator.exit.code"
          failifexecutionfails="true"
          failonerror="false">
        <arg value="--source"/>
        <arg value="src/main"/>
        <arg value="--format"/>
        <arg value="text"/>
    </exec>

    <condition property="validator.failed">
        <not>
            <equals arg1="${validator.exit.code}" arg2="0"/>
        </not>
    </condition>

    <fail if="validator.failed"
          message="Validation failed. See ${quality.log.dir}/validator.out and validator.err."/>
</target>
```

Khi chạy `ant validate`, Ant tạo thư mục log, xóa log cũ, khởi chạy validator, chuyển hướng hai luồng và ghi mã thoát. Sau đó buildfile kiểm tra mã thoát và dừng build nếu khác `0`.

Nếu executable không thể khởi chạy, `failifexecutionfails="true"` làm task thất bại ngay. Nếu chương trình chạy được nhưng trả mã khác `0`, `failonerror="false"` cho phép target kiểm tra `resultproperty` rồi tự phát thông báo có đường dẫn log.

## 18. Ví dụ tổng hợp: dùng redirector để cấu hình input/output

Ví dụ dưới đây dùng nested redirector để đọc input từ file, lưu stdout/stderr riêng và quy định encoding:

```xml
<property name="processor.input" location="config/processor-input.txt"/>
<property name="processor.output" location="build/logs/processor.out"/>
<property name="processor.error" location="build/logs/processor.err"/>

<target name="run-processor">
    <mkdir dir="build/logs"/>

    <exec executable="processor"
          dir="${basedir}"
          resultproperty="processor.exit.code"
          failonerror="false">
        <arg value="--stdin"/>

        <redirector input="${processor.input}"
                    output="${processor.output}"
                    error="${processor.error}"
                    append="false"
                    inputEncoding="UTF-8"
                    outputEncoding="UTF-8"
                    errorEncoding="UTF-8"
                    logError="true"/>
    </exec>

    <echo message="Processor exit code: ${processor.exit.code}"/>
</target>
```

Trong ví dụ, redirector quản lý stdin và hai luồng output; `resultproperty` vẫn là thuộc tính của task exec vì mã thoát là trạng thái thực thi tiến trình, không phải nội dung luồng văn bản.

## 19. Các lỗi thường gặp khi chuyển hướng output

| Hiện tượng | Nguyên nhân có thể có | Cách xử lý |
|---|---|---|
| File output rỗng | Chương trình không ghi stdout hoặc ghi kết quả vào stderr | Kiểm tra cả hai luồng và tài liệu công cụ |
| File error có nội dung nhưng task vẫn thành công | stderr không quyết định mã thoát | Kiểm tra `resultproperty` hoặc bật `failonerror` |
| Chương trình trả mã khác `0` nhưng build vẫn xanh | `failonerror` mặc định là `false` và không kiểm tra resultproperty | Bật `failonerror="true"` hoặc kiểm tra `resultproperty` bằng condition/fail |
| Build lỗi ngay dù failonerror=false | Không thể khởi chạy executable; `failifexecutionfails` vẫn là true | Kiểm tra executable, PATH, quyền và working directory |
| Không thấy property output | Chương trình không tạo stdout, property đã được đặt trước hoặc tiến trình không chạy theo cách đồng bộ | Kiểm tra log, tên property và cách gọi task |
| Property giữ giá trị lần chạy cũ | Ant property thông thường bất biến | Dùng tên property mới hoặc ghi output vào file riêng |
| Log bị ghi đè | `append` không bật | Dùng `append="true"` khi thật sự cần nối log |
| Log chứa dữ liệu từ build cũ | File chưa được xóa trước khi chạy | Xóa file log hoặc tạo tên file theo build/lần chạy |
| Ký tự tiếng Việt bị lỗi | Encoding output/error không khớp với chương trình | Đặt encoding theo charset thực tế của tiến trình |
| Không có exit code để kiểm tra | Tiến trình không khởi chạy, bị tách bằng spawn hoặc task dừng trước khi hoàn thành | Dùng exec đồng bộ và kiểm tra lỗi khởi chạy/timeout |
| Pipeline hoặc lệnh shell hoạt động khác hệ điều hành | Ant đang gọi executable trực tiếp, không có shell mở rộng cú pháp | Dùng task portable hoặc gọi shell nền tảng một cách có chủ đích |
| Log Ant không hiển thị stderr đã chuyển hướng | Chưa bật `logError` hoặc cấu hình redirector chỉ ghi file | Bật logError khi cần, hoặc xem file error riêng |

### 19.1. Không dùng stderr để quyết định build thất bại

Một chương trình có thể ghi cảnh báo ra stderr trong khi vẫn hoàn thành thành công. Ví dụ:

```text
Warning: using a deprecated option
```

Nếu tiến trình trả mã `0`, nó có thể vẫn được xem là thành công theo hợp đồng của chương trình. Ngược lại, chương trình có thể trả mã `1` nhưng không in gì ra stderr. Vì vậy, dùng exit code để quyết định thành công/thất bại; dùng stdout/stderr để xem nội dung và chẩn đoán.

### 19.2. Không dùng outputproperty cho log rất lớn

Nếu một công cụ in hàng trăm nghìn dòng, đưa toàn bộ vào property làm build giữ lượng dữ liệu lớn trong bộ nhớ và khó quan sát. Hãy dùng `output`/`error` để ghi file, sau đó dùng công cụ xử lý log riêng nếu cần trích xuất một giá trị nhỏ.

## 20. Quy trình chọn cơ chế thu thập

Có thể lựa chọn theo mục tiêu:

| Nhu cầu | Cơ chế nên dùng |
|---|---|
| Lưu stdout dài | `output="file"` |
| Lưu stderr riêng | `error="file"` |
| Dùng stdout ngắn trong buildfile | `outputproperty="name"` |
| Dùng stderr ngắn để chẩn đoán | `errorproperty="name"` |
| Kiểm tra chương trình thành công hay thất bại | `resultproperty="name"` hoặc `failonerror="true"` |
| Tự chấp nhận một số exit code | `resultproperty` + `condition` + `fail` |
| Ghi nối log nhiều lần chạy | `append="true"` |
| Cấp stdin từ file | `input="file"` |
| Cấp stdin từ chuỗi nhỏ | `inputstring="..."` |
| Cấu hình chuyển hướng nhiều tùy chọn | Nested `<redirector>` |
| Chạy tiến trình đồng bộ có giới hạn | `timeout` và không dùng `spawn` |

Trước khi viết buildfile, hãy xác định câu trả lời cho ba câu hỏi:

1. Chương trình tạo dữ liệu nào trên stdout và stderr?
2. Mã thoát nào được coi là thành công?
3. Kết quả cần lưu trong file để người vận hành xem, hay trong property để buildfile xử lý tiếp?

Khi trả lời được ba câu hỏi đó, lựa chọn thuộc tính của Ant sẽ rõ ràng hơn.

## 21. Nguyên tắc sử dụng exec và redirector dễ bảo trì

- Tách `executable` và từng đối số bằng `<arg>`; tránh ghép toàn bộ lệnh thành một chuỗi phụ thuộc shell.
- Đặt `dir` rõ ràng nếu chương trình cần chạy trong một thư mục cụ thể.
- Phân biệt stdout, stderr và exit code.
- Dùng `output`/`error` cho log dài và `outputproperty`/`errorproperty` cho nội dung ngắn.
- Dùng `resultproperty` khi cần tự quyết định dựa trên mã thoát.
- Bật `failonerror="true"` khi mọi mã khác `0` đều phải chặn build.
- Giữ `failifexecutionfails="true"` nếu không thể tiếp tục khi executable không khởi chạy.
- Không dùng stderr có nội dung làm tiêu chí duy nhất để kết luận tiến trình thất bại.
- Dùng `append` có chủ đích và xóa log cũ nếu cần kết quả sạch.
- Đặt encoding theo charset thật của tiến trình.
- Dùng redirector khi cần cấu hình input/output có cấu trúc hoặc nhiều tùy chọn.
- Tránh `spawn` khi cần chờ output và mã thoát.
- Không lưu secret trong property rồi echo ra log.
- Dùng timeout hợp lý cho tiến trình có thể treo.

## 22. Kết luận

Khi Ant chạy chương trình bên ngoài, cần phân biệt ba kết quả: stdout là dữ liệu đầu ra chuẩn, stderr là luồng thông báo lỗi/chẩn đoán, còn exit code là trạng thái kết thúc của tiến trình. Ant cung cấp `output` và `error` để ghi hai luồng ra file; `outputproperty` và `errorproperty` để lưu nội dung vào property; `resultproperty` để lưu mã thoát.

`failonerror` quyết định cách xử lý mã thoát khác `0`, còn `failifexecutionfails` xử lý trường hợp không thể khởi chạy chương trình. Khi cần điều khiển nhiều tùy chọn input/output, nested `<redirector>` cho phép cấu hình file, property, append và encoding trong một phần tử riêng. Chọn đúng cơ chế theo kích thước dữ liệu và mục tiêu của build giúp log dễ đọc, lỗi được phát hiện đúng và quy trình CI không bỏ sót trạng thái thất bại.

## Tài liệu tham khảo

- [Apache Ant — Exec Task](https://ant.apache.org/manual/Tasks/exec.html)
- [Apache Ant — Redirector](https://ant.apache.org/manual/Types/redirector.html)
- [Apache Ant — Conditions](https://ant.apache.org/manual/Tasks/conditions.html)
- [Apache Ant — Fail Task](https://ant.apache.org/manual/Tasks/fail.html)
