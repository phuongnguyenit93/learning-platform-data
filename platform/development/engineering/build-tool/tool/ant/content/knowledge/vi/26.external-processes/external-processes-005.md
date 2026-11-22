# Kiểm soát timeout, `failonerror` và `failifexecutionfails`

Apache Ant có thể gọi chương trình bên ngoài bằng task `<exec>`, chẳng hạn compiler native, công cụ đóng gói, script triển khai hoặc một chương trình kiểm tra dữ liệu. Khi gọi một tiến trình ngoài, build cần kiểm soát ba tình huống khác nhau: chương trình chạy quá lâu, chương trình đã chạy nhưng trả về mã lỗi, và Ant không thể khởi chạy chương trình ngay từ đầu.

Ba thuộc tính quan trọng của `<exec>` xử lý các tình huống đó:

- `timeout`: giới hạn thời gian tiến trình được phép chạy.
- `failonerror`: quyết định build có dừng khi chương trình kết thúc với mã lỗi hay không.
- `failifexecutionfails`: quyết định build có dừng khi Ant không thể khởi chạy executable hay không.

Hiểu rõ sự khác nhau giữa lỗi khởi chạy và lỗi trả về từ chương trình giúp build file phản ứng đúng: một công cụ bắt buộc không có mặt phải làm build thất bại, còn một công cụ tùy chọn có thể được bỏ qua theo chính sách của dự án.

## 1. Gọi chương trình bên ngoài bằng `<exec>`

Một lời gọi cơ bản chỉ định chương trình qua `executable` và truyền từng đối số bằng phần tử `<arg>`:

```xml
<target name="generate-report">
    <exec executable="report-generator"
          dir="${basedir}"
          failonerror="true">
        <arg value="--input"/>
        <arg value="data/input.csv"/>
        <arg value="--output"/>
        <arg value="build/report.html"/>
    </exec>
</target>
```

`executable` chỉ chứa tên hoặc đường dẫn chương trình. Các đối số được khai báo riêng, theo đúng thứ tự mà chương trình yêu cầu. `dir` đặt working directory của tiến trình con; nếu không chỉ định, thư mục chạy phụ thuộc cơ chế launcher và project. Nên chỉ định rõ `dir` khi chương trình sử dụng đường dẫn tương đối.

Không gộp toàn bộ lệnh và các đối số vào một chuỗi có dấu cách. Task `<exec>` không mặc định chạy command qua shell, vì vậy các ký tự như `*`, `>`, `|`, `&&` hoặc biến môi trường không tự được shell diễn giải. Nếu cần chức năng shell, hãy gọi shell một cách tường minh và truyền script/đối số theo quy tắc của hệ điều hành.

Ví dụ chạy file batch trên Windows:

```xml
<exec executable="cmd" dir="${basedir}" failonerror="true">
    <arg value="/c"/>
    <arg value="scripts\build-native.bat"/>
    <arg value="release"/>
</exec>
```

Trên Windows, file `.bat` hoặc `.cmd` thường cần được gọi thông qua `cmd /c`. Nếu executable không được tìm thấy, hãy kiểm tra `PATH` hoặc truyền đường dẫn tuyệt đối tới chương trình.

## 2. Phân biệt hai loại lỗi

Một tiến trình ngoài có thể thất bại ở hai giai đoạn khác nhau:

| Tình huống | Ví dụ | Thuộc tính kiểm soát |
|---|---|---|
| Không khởi chạy được chương trình | Không tìm thấy executable, thiếu quyền chạy, đường dẫn sai hoặc hệ điều hành từ chối tạo tiến trình | `failifexecutionfails` |
| Chương trình đã chạy nhưng báo lỗi | Chương trình trả về mã thoát khác 0 theo quy ước của nó | `failonerror` |

`failifexecutionfails` mặc định là `true`. Khi Ant không thể tạo tiến trình, build dừng với `BuildException`. Đặt `false` nếu chương trình thực sự là tùy chọn và việc không thể khởi chạy nó không nên làm build thất bại.

`failonerror` mặc định là `false`. Khi chương trình đã chạy và trả về mã lỗi, Ant mặc định không dừng build chỉ vì mã trả về đó. Đặt `true` để biến mã lỗi của chương trình thành lỗi của target hiện tại.

Hai thuộc tính này không thay thế nhau. Nếu executable không tồn tại, `failonerror` không giải quyết được vấn đề vì chương trình chưa chạy để trả mã thoát. Ngược lại, nếu chương trình chạy thành công về mặt khởi chạy nhưng trả mã `1`, `failifexecutionfails` không quyết định kết quả đó.

## 3. Dừng build khi chương trình trả về mã lỗi: `failonerror`

Khi một lệnh là bước bắt buộc của build, đặt `failonerror="true"`:

```xml
<target name="compile-native">
    <exec executable="native-compiler"
          dir="${basedir}"
          failonerror="true">
        <arg value="-O2"/>
        <arg value="-o"/>
        <arg value="build/native/app"/>
        <arg value="src/native/main.c"/>
    </exec>
</target>
```

Nếu compiler kết thúc với mã lỗi, task ném `BuildException` và target không tiếp tục các task sau nó. Đây là lựa chọn phù hợp khi artifact phía sau phụ thuộc vào kết quả của chương trình.

Nếu để `failonerror="false"` (mặc định), Ant bỏ qua mã trả về lỗi và tiếp tục. Điều đó hữu ích khi build muốn thu thập kết quả trước rồi tự quyết định, nhưng rất nguy hiểm nếu không có bước kiểm tra sau đó: build có thể báo thành công dù công cụ đã thất bại.

## 4. Lấy mã thoát bằng `resultproperty`

Khi cần xử lý mã thoát theo logic riêng, dùng `resultproperty`. Thuộc tính này ghi mã trả về của tiến trình vào một Ant property. Nó hữu ích khi `failonerror="false"`, bởi nếu `failonerror="true"`, mọi mã lỗi đều khiến task dừng trước khi build có thể xử lý tiếp.

```xml
<target name="run-check">
    <exec executable="quality-checker"
          dir="${basedir}"
          failonerror="false"
          failifexecutionfails="true"
          resultproperty="quality.exit">
        <arg value="--strict"/>
        <arg value="src"/>
    </exec>

    <condition property="quality.succeeded">
        <equals arg1="${quality.exit}" arg2="0"/>
    </condition>

    <fail unless="quality.succeeded"
          message="Quality checker failed with exit code ${quality.exit}"/>
</target>
```

Luồng xử lý:

1. Ant khởi chạy `quality-checker`.
2. Task không dừng ngay khi chương trình trả mã lỗi vì `failonerror="false"`.
3. Ant lưu mã trả về vào `quality.exit`.
4. Condition đặt `quality.succeeded` nếu mã trả về bằng `0`.
5. Task `<fail>` dừng target nếu property thành công không được đặt.

Cách này cho phép thực hiện thêm bước ghi log, lưu báo cáo hoặc phân loại mã lỗi trước khi quyết định build có thất bại hay không. Hãy nhớ Ant property là bất biến: không nên đặt trước `quality.exit` hoặc `quality.succeeded` nếu muốn task/condition gán giá trị trong lần chạy này.

Nếu tiến trình bị timeout, Ant đặt kết quả thực thi là `-1`. Với `failonerror="false"`, mã này có thể được lưu vào `resultproperty`; condition kiểm tra bằng `0` sẽ không thành công và target vẫn bị fail ở bước `<fail>`.

## 5. Giới hạn thời gian bằng `timeout`

Thuộc tính `timeout` chỉ định thời gian tối đa tiến trình được phép chạy, tính bằng mili giây. Khi hết thời gian mà chương trình chưa kết thúc, Ant dừng tiến trình con và ghi thông báo vào log.

```xml
<target name="run-integration-checks">
    <exec executable="integration-checker"
          dir="${basedir}"
          timeout="120000"
          failonerror="true"
          failifexecutionfails="true">
        <arg value="--suite"/>
        <arg value="integration"/>
    </exec>
</target>
```

`timeout="120000"` tương đương hai phút. Nếu tiến trình không kết thúc trong thời gian đó, Ant dừng nó và nhận mã kết quả `-1`. Với `failonerror="true"`, build thất bại. Nếu `failonerror="false"`, mã lỗi có thể bị bỏ qua trừ khi được ghi bằng `resultproperty` và kiểm tra sau đó.

Không khai báo `timeout` nghĩa là task không đặt giới hạn thời gian. Với lệnh có thể treo do kết nối mạng, chờ phản hồi hoặc deadlock, nên đặt timeout phù hợp để build không bị giữ vô thời hạn.

### Chọn timeout phù hợp

Timeout quá ngắn có thể dừng một bước hợp lệ khi CI đang tải dependency hoặc máy build bị tải cao. Timeout quá dài lại làm một lỗi treo chiếm worker trong thời gian không cần thiết. Có thể chọn giá trị dựa trên thời gian chạy bình thường và biên độ dao động:

| Loại lệnh | Ví dụ giới hạn ban đầu |
|---|---:|
| Kiểm tra nhanh hoặc định dạng file | 10–30 giây |
| Biên dịch native nhỏ | 1–3 phút |
| Kiểm thử tích hợp | 2–10 phút |
| Tải hoặc xử lý dữ liệu lớn | Theo SLA và kích thước dữ liệu |

Các con số trên chỉ là điểm khởi đầu. Hãy đo thời gian thực tế của dự án và điều chỉnh theo môi trường CI. Nếu tiến trình cần thời gian biến thiên lớn, có thể tách thành nhiều bước nhỏ để giới hạn timeout chính xác hơn.

## 6. Kiểm soát việc không khởi chạy được: `failifexecutionfails`

Mặc định `failifexecutionfails="true"`. Nếu Ant không thể tạo tiến trình, ví dụ executable không tồn tại hoặc hệ điều hành từ chối chạy, build thất bại ngay:

```xml
<exec executable="required-tool"
      failifexecutionfails="true"
      failonerror="true">
    <arg value="--version"/>
</exec>
```

Đây là cấu hình phù hợp cho công cụ bắt buộc. Nếu thiếu tool, build không thể hoàn thành đúng mục tiêu nên cần dừng sớm.

Với công cụ tùy chọn, có thể đặt `failifexecutionfails="false"`:

```xml
<exec executable="optional-linter"
      failifexecutionfails="false"
      failonerror="false">
    <arg value="src"/>
</exec>
```

Nếu `optional-linter` không thể khởi chạy, Ant ghi cảnh báo và tiếp tục. Nếu chương trình chạy được nhưng trả mã lỗi, `failonerror="false"` cũng cho phép build tiếp tục. Cần phân biệt rõ đây là chính sách bỏ qua công cụ tùy chọn; không dùng cấu hình này cho compiler, test runner hoặc công cụ tạo artifact bắt buộc.

Khi cần biết tool có sẵn trước khi gọi, có thể kiểm tra đường dẫn executable bằng condition hoặc cấu hình môi trường trước đó. `failifexecutionfails="false"` chỉ cho phép tiếp tục khi không thể chạy chương trình; nó không tự tạo một property mô tả chính xác vì sao executable vắng mặt.

## 7. Kết hợp ba thuộc tính trong một lệnh

Một lệnh bắt buộc thường cần cả timeout lẫn hai chính sách fail rõ ràng:

```xml
<target name="generate-artifact">
    <exec executable="artifact-generator"
          dir="${basedir}"
          timeout="90000"
          failonerror="true"
          failifexecutionfails="true">
        <arg value="--source"/>
        <arg value="src"/>
        <arg value="--destination"/>
        <arg value="build/generated"/>
    </exec>

    <echo message="Artifact generation completed"/>
</target>
```

Kết quả của cấu hình:

| Sự kiện | Kết quả |
|---|---|
| Không tìm thấy `artifact-generator` hoặc không tạo được tiến trình | `failifexecutionfails=true` làm build thất bại |
| Chương trình chạy quá 90 giây | Ant dừng tiến trình; kết quả là `-1`; `failonerror=true` làm build thất bại |
| Chương trình kết thúc với mã lỗi | `failonerror=true` làm build thất bại |
| Chương trình kết thúc thành công | Task hoàn tất và `<echo>` được thực thi |

Đặt cả hai thuộc tính `failonerror` và `failifexecutionfails` thành `true` thường là lựa chọn an toàn cho lệnh bắt buộc. Timeout bổ sung giới hạn thời gian cho trường hợp chương trình không bao giờ kết thúc.

## 8. Ghi output và error để chẩn đoán

Khi tiến trình thất bại, log stdout và stderr thường giúp xác định nguyên nhân. `<exec>` có thể ghi hai luồng ra file riêng:

```xml
<target name="run-compiler">
    <mkdir dir="build/logs"/>

    <exec executable="native-compiler"
          dir="${basedir}"
          timeout="60000"
          failonerror="true"
          failifexecutionfails="true"
          output="build/logs/compiler.stdout.log"
          error="build/logs/compiler.stderr.log">
        <arg value="--version"/>
    </exec>
</target>
```

`output` chỉ định file nhận stdout; `error` chỉ định file nhận stderr. Có thể dùng `append="true"` nếu muốn nối thêm output vào file hiện có thay vì ghi đè. Nếu dùng `outputproperty` hoặc `errorproperty`, Ant lưu nội dung luồng vào property; các property này cũng bất biến nên không phù hợp để tích lũy output qua nhiều lần gọi.

Nếu chỉ đặt `outputproperty` mà không chuyển stderr riêng, stderr có thể được gộp vào nội dung output property. Khi cần phân tích lỗi rõ ràng, hãy tách hai luồng bằng `error` hoặc `errorproperty`.

## 9. `spawn` và các giới hạn của nó

Thuộc tính `spawn="true"` yêu cầu Ant khởi chạy chương trình rồi trả quyền điều khiển ngay, không đợi tiến trình kết thúc. Cách này phù hợp với một chương trình nền mà build không cần chờ kết quả, ví dụ mở một dịch vụ cục bộ phục vụ thao tác thủ công sau đó.

```xml
<exec executable="local-preview-server" spawn="true">
    <arg value="--directory"/>
    <arg value="build/site"/>
</exec>
```

Khi dùng `spawn`, Ant không ghi output của tiến trình vào log và các cấu hình `input`, `output`, `error`, `resultproperty` không hoạt động. Vì Ant không chờ tiến trình kết thúc, task cũng không thể dựa vào mã thoát cuối cùng để quyết định thành công hay thất bại. `spawn` không phù hợp khi cần kiểm soát `timeout`, `failonerror` hoặc kết quả thực thi.

Nếu build phải xác nhận server đã sẵn sàng, hãy dùng một cơ chế start/health-check riêng và chờ kiểm tra thành công trước khi tiếp tục. Không xem việc task `spawn` trả về là bằng chứng tiến trình nền đã khởi động đúng.

## 10. Ví dụ xử lý một công cụ tùy chọn

Giả sử dự án có một công cụ tối ưu ảnh tùy chọn. Khi tool không được cài, build vẫn tạo package; khi tool có mặt và chạy, build lưu mã thoát để có thể cảnh báo hoặc thất bại theo chính sách:

```xml
<target name="optimize-images">
    <exec executable="image-optimizer"
          dir="${basedir}"
          timeout="45000"
          failifexecutionfails="false"
          failonerror="false"
          resultproperty="image.optimizer.exit"
          output="build/logs/image-optimizer.log">
        <arg value="--input"/>
        <arg value="src/images"/>
        <arg value="--output"/>
        <arg value="build/site/images"/>
    </exec>

    <condition property="image.optimizer.succeeded">
        <equals arg1="${image.optimizer.exit}" arg2="0"/>
    </condition>

    <echo message="Image optimizer exit code: ${image.optimizer.exit}"/>
</target>
```

Ví dụ này minh họa việc không làm build thất bại khi không thể khởi chạy công cụ hoặc khi công cụ trả mã lỗi. Nếu `resultproperty` không được gán do executable không thể khởi chạy, giá trị property có thể không tồn tại; không nên giả định rằng mọi lần gọi đều có mã thoát. Trong pipeline thực tế, nếu cần phân biệt rõ “không cài đặt” và “đã chạy nhưng thất bại”, hãy kiểm tra sự hiện diện của executable trước, hoặc tách target theo điều kiện có tool.

Nếu tối ưu ảnh là bắt buộc cho release, hãy đổi `failifexecutionfails` và `failonerror` thành `true` để không phát hành package khi bước tối ưu không hoàn tất.

## 11. Lỗi thường gặp và cách xử lý

1. **Build không dừng dù chương trình trả mã lỗi.** `failonerror` mặc định là `false`. Đặt `failonerror="true"` hoặc dùng `resultproperty` rồi kiểm tra mã thoát.
2. **Build dừng vì không tìm thấy executable.** Kiểm tra `PATH`, quyền thực thi, đường dẫn và working directory. Với công cụ bắt buộc, giữ `failifexecutionfails="true"`; với công cụ tùy chọn, cân nhắc `false`.
3. **Tiến trình chạy mãi không kết thúc.** Đặt `timeout` theo mili giây. Kiểm tra log và nguyên nhân chương trình bị treo trước khi tăng timeout.
4. **Timeout xảy ra nhưng build vẫn tiếp tục.** Khi timeout, tiến trình bị dừng và kết quả là `-1`. Nếu `failonerror="false"`, task không tự fail; hãy bật `failonerror` hoặc kiểm tra `resultproperty`.
5. **Dùng `resultproperty` nhưng không thấy property.** Thuộc tính chỉ có ích khi tiến trình thực sự chạy và có kết quả; nếu Ant không thể khởi chạy chương trình và `failifexecutionfails="false"`, không có mã thoát thông thường để lưu.
6. **Đối số chứa khoảng trắng bị tách sai.** Dùng từng `<arg value="..."/>` hoặc `<arg file="..."/>` thay vì nối mọi đối số trong một chuỗi command.
7. **Dùng dấu `|`, `>` hoặc `&&` nhưng không hoạt động.** `<exec>` không mặc định chạy qua shell. Gọi `cmd /c` trên Windows hoặc shell phù hợp trên Unix khi thực sự cần cú pháp shell.
8. **Không đọc được output khi `spawn=true`.** Ant không ghi log output của tiến trình được spawn và không kích hoạt các cấu hình input/output/error/result. Bỏ `spawn` nếu cần quan sát kết quả.
9. **Log bị ghi đè ở mỗi lần chạy.** Mặc định output file được ghi mới. Dùng `append="true"` nếu muốn nối log, hoặc tạo tên log riêng cho từng lần build.
10. **Dùng `<exec>` để chạy Java class.** Nếu mục đích là chạy Java class hoặc JAR, cân nhắc task `<java>` vì nó hiểu classpath, JVM argument và các tùy chọn Java chuyên biệt.

## 12. Quy trình chọn chính sách thực thi

Khi thêm một lệnh ngoài vào build file, hãy quyết định theo thứ tự:

1. Xác định executable có bắt buộc cho build hay chỉ là tiện ích tùy chọn.
2. Nếu bắt buộc, giữ `failifexecutionfails="true"`; chỉ đặt `false` khi việc thiếu executable được chấp nhận.
3. Xác định mã thoát khác 0 có đồng nghĩa bước build thất bại hay không. Nếu có, đặt `failonerror="true"`.
4. Nếu cần xử lý mã thoát theo logic riêng, dùng `failonerror="false"` cùng `resultproperty` và kiểm tra property bằng condition.
5. Đặt `timeout` cho lệnh có nguy cơ treo; nhớ đơn vị là mili giây.
6. Ghi stdout và stderr vào log khi cần chẩn đoán lỗi.
7. Chỉ dùng `spawn="true"` khi build không cần chờ kết quả, không cần output hoặc mã thoát.
8. Kiểm tra lệnh trên đúng hệ điều hành, đúng working directory và đúng môi trường CI mà build sẽ chạy.

## Tài liệu tham khảo

- [Apache Ant Manual — Exec Task](https://ant.apache.org/manual/Tasks/exec.html): `timeout`, `failonerror`, `failifexecutionfails`, `resultproperty`, `spawn`, đối số và chuyển hướng output.
- [Apache Ant API — ExecTask](https://ant.apache.org/manual/api/org/apache/tools/ant/taskdefs/ExecTask.html): mô tả các setter và cách task kiểm soát tiến trình.
- [Apache Ant Manual — Java Task](https://ant.apache.org/manual/Tasks/java.html): lựa chọn phù hợp khi cần chạy Java class hoặc JAR thay vì executable tổng quát.
