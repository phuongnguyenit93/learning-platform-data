# Đồng bộ tác vụ chờ bằng `waitfor` và quản lý giới hạn thời gian

Khi một build Ant cần sử dụng một tiến trình bên ngoài, đôi khi lệnh khởi chạy tiến trình đã kết thúc nhưng dịch vụ mà tiến trình đó cung cấp vẫn chưa sẵn sàng. Ví dụ, một target khởi động máy chủ thử nghiệm, sau đó cần chờ cổng TCP mở trước khi chạy integration test. Nếu chạy test ngay lập tức, kết quả có thể thất bại do máy chủ chưa hoàn tất khởi tạo.

Task `<waitfor>` của Ant giải quyết tình huống này bằng cách kiểm tra một condition theo chu kỳ cho đến khi condition đúng hoặc hết thời gian chờ. Nó có thể chờ một tệp xuất hiện, một cổng mạng sẵn sàng hoặc một điều kiện kết hợp. Thuộc tính timeout giúp build phản hồi rõ ràng khi điều kiện không đạt được trong khoảng thời gian cho phép.

`waitfor` chỉ quan sát trạng thái và chờ; nó không tự khởi động dịch vụ, không quản lý vòng đời tiến trình và không tự dừng tiến trình khi hết hạn. Build cần kết hợp nó với task khởi chạy, kiểm tra lỗi và bước cleanup phù hợp.

## 1. Vì sao cần đồng bộ tác vụ ngoài?

Một lệnh khởi động dịch vụ có thể trả về trước khi dịch vụ thực sự sẵn sàng. Quá trình startup có thể cần thời gian để:

- Đọc cấu hình và nạp thư viện.
- Mở socket hoặc bind cổng mạng.
- Tạo thư mục dữ liệu và tệp trạng thái.
- Kết nối database hoặc message broker.
- Chạy migration hoặc kiểm tra health.
- Nạp cache và khởi tạo thành phần nội bộ.

Nếu target tiếp theo chạy quá sớm, build gặp lỗi phụ thuộc vào thời điểm, thường được gọi là race condition. Trên máy nhanh lỗi có thể không xuất hiện; trên CI hoặc máy tải cao lỗi lại xảy ra thường xuyên.

Ví dụ luồng cần đồng bộ:

```text
Khởi chạy test server
        |
        v
Tiến trình server bắt đầu
        |
        v
Chờ server sẵn sàng
        |
        +---- condition đúng ----> Chạy integration test
        |
        +---- hết thời gian -----> Báo lỗi startup timeout
```

Chờ một khoảng cố định bằng `<sleep>` không bảo đảm dịch vụ đã sẵn sàng. Nếu chờ quá ngắn, test vẫn chạy sớm; nếu chờ quá dài, build lãng phí thời gian. `waitfor` kiểm tra điều kiện thực tế và tiếp tục ngay khi điều kiện đạt được.

## 2. Cú pháp cơ bản của `<waitfor>`

`<waitfor>` nhận một hoặc nhiều condition lồng bên trong. Task đánh giá condition, chờ theo chu kỳ nếu kết quả chưa đúng và kết thúc khi condition đúng hoặc hết thời gian tối đa.

Cú pháp:

```xml
<waitfor maxwait="60"
         maxwaitunit="second"
         checkevery="500"
         checkeveryunit="millisecond"
         timeoutproperty="service.startup.timeout">
    <available file="build/service.ready" type="file"/>
</waitfor>
```

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `maxwait` | Thời gian chờ tối đa |
| `maxwaitunit` | Đơn vị của `maxwait`, ví dụ `millisecond`, `second`, `minute`, `hour` hoặc `day` |
| `checkevery` | Khoảng thời gian giữa hai lần đánh giá condition |
| `checkeveryunit` | Đơn vị của `checkevery` |
| `timeoutproperty` | Tên property được đặt khi hết thời gian chờ mà condition vẫn chưa đúng |

Nếu không khai báo, Ant dùng thời gian chờ tối đa và chu kỳ kiểm tra mặc định của task. Để build dễ đọc và không phụ thuộc vào mặc định, nên chỉ định rõ cả `maxwait` lẫn `checkevery` trong những bước quan trọng.

Trong ví dụ, Ant kiểm tra sự tồn tại của `build/service.ready` tối đa 60 giây, mỗi 500 mili giây. Nếu tệp xuất hiện, task kết thúc thành công. Nếu tệp không xuất hiện trước hạn, Ant đặt property `service.startup.timeout`.

### 2.1. Condition đúng và timeout là hai kết quả khác nhau

Khi condition trở thành đúng, `<waitfor>` kết thúc mà không đặt timeout property. Khi hết hạn, property được chỉ định bởi `timeoutproperty` được đặt để target tiếp theo có thể quyết định phải làm gì.

Task không tự làm build thất bại chỉ vì đã timeout. Nếu timeout là lỗi bắt buộc, hãy kiểm tra property bằng `<fail>`:

```xml
<waitfor maxwait="60"
         maxwaitunit="second"
         checkevery="500"
         checkeveryunit="millisecond"
         timeoutproperty="service.startup.timeout">
    <available file="build/service.ready" type="file"/>
</waitfor>

<fail if="service.startup.timeout"
      message="Service did not create its ready marker within 60 seconds."/>
```

`if` ở đây kiểm tra property có được thiết lập hay không. Vì timeout property chỉ được đặt khi hết hạn, điều kiện này phù hợp để dừng build.

Không kiểm tra timeout bằng `unless="service.startup.timeout"`, vì `unless` sẽ kiểm tra sự tồn tại của property chứ không đánh giá nội dung chuỗi. Nếu một property được đặt thành giá trị `false`, nó vẫn được xem là đã tồn tại.

### 2.2. Chọn thời gian kiểm tra hợp lý

Chu kỳ kiểm tra quá ngắn làm tăng số lần đánh giá condition, trong khi chu kỳ quá dài khiến build tiếp tục chờ sau khi dịch vụ đã sẵn sàng.

Một số mức tham khảo:

| Tình huống | `maxwait` gợi ý | `checkevery` gợi ý |
|---|---:|---:|
| Tệp marker được tạo bởi một bước cục bộ | 10–30 giây | 200–500 ms |
| Server khởi động trong môi trường test | 60–120 giây | 500 ms–1 giây |
| Dịch vụ tích hợp cần kết nối nhiều thành phần | 2–5 phút | 1–2 giây |
| Tài nguyên từ môi trường từ xa | Theo SLA của môi trường | 1–5 giây |

Đây chỉ là giá trị khởi đầu. Hãy dựa trên thời gian startup thực tế, tải CI và giới hạn của hệ thống. Timeout nên đủ dài để tránh false failure nhưng vẫn đủ ngắn để phát hiện sự cố trong thời gian hợp lý.

## 3. Chờ một tệp hoặc resource xuất hiện

Một cách đơn giản để đồng bộ là chờ một tệp marker do tiến trình ngoài tạo ra khi đã sẵn sàng.

Ví dụ:

```xml
<property name="service.ready.file" location="${basedir}/build/service.ready"/>

<target name="wait-service-ready">
    <waitfor maxwait="45"
             maxwaitunit="second"
             checkevery="250"
             checkeveryunit="millisecond"
             timeoutproperty="service.ready.timeout">
        <available file="${service.ready.file}" type="file"/>
    </waitfor>

    <fail if="service.ready.timeout"
          message="Service did not create ${service.ready.file} before timeout."/>
</target>
```

Condition `<available>` đúng khi tệp tồn tại. Thuộc tính `type="file"` yêu cầu resource là tệp, tránh việc một thư mục cùng tên vô tình thỏa điều kiện.

### 3.1. Tệp marker cần phản ánh readiness thật

Marker chỉ có ý nghĩa nếu tiến trình tạo nó sau khi hoàn tất những bước khởi tạo cần thiết. Nếu tiến trình tạo marker ngay khi vừa bắt đầu, build có thể tiếp tục trước khi dịch vụ thực sự nhận request được.

Nên tạo marker sau khi:

- Server đã bind cổng cần sử dụng.
- Kết nối phụ thuộc bắt buộc đã sẵn sàng.
- Cấu hình và dữ liệu khởi tạo đã được nạp.
- Health check nội bộ đã thành công.

Nếu ứng dụng không hỗ trợ tạo marker, có thể chờ một cổng TCP hoặc một endpoint health check. Không nên tạo marker từ chính build ngay sau lệnh khởi chạy vì thao tác đó chỉ chứng minh task đã chạy, không chứng minh tiến trình ngoài đã sẵn sàng.

### 3.2. Dọn marker cũ trước khi khởi động

Marker còn sót từ lần chạy trước có thể khiến `<waitfor>` kết thúc ngay lập tức dù tiến trình mới chưa sẵn sàng. Hãy xóa marker trước khi khởi động tiến trình:

```xml
<target name="prepare-service-startup">
    <delete file="${service.ready.file}" quiet="true"/>
</target>
```

Sau đó target khởi động service phụ thuộc vào `prepare-service-startup`, rồi target chờ marker. Tệp marker nên nằm trong thư mục build riêng để target clean có thể dọn an toàn.

## 4. Chờ cổng TCP bằng condition `<socket>`

Nếu dịch vụ mở cổng TCP, có thể dùng condition `<socket>` để chờ cổng đó nhận kết nối:

```xml
<target name="wait-http-port">
    <waitfor maxwait="90"
             maxwaitunit="second"
             checkevery="500"
             checkeveryunit="millisecond"
             timeoutproperty="http.port.timeout">
        <socket server="127.0.0.1" port="8080"/>
    </waitfor>

    <fail if="http.port.timeout"
          message="The test server did not open TCP port 8080 within 90 seconds."/>
</target>
```

Condition `<socket>` thử kết nối đến host và port được chỉ định. Khi kết nối thành công, condition đúng và build tiếp tục.

### 4.1. Cổng mở chưa chắc dịch vụ đã sẵn sàng

Một cổng TCP mở chỉ chứng minh có tiến trình chấp nhận kết nối tại endpoint đó. Nó không chứng minh ứng dụng đã hoàn thành migration, nạp dữ liệu hoặc phục vụ đúng API.

Ví dụ server có thể mở cổng HTTP sớm nhưng trả về `503 Service Unavailable` trong lúc khởi tạo. Nếu integration test cần API thực sự hoạt động, hãy chờ một health endpoint hoặc marker được tạo sau khi readiness check thành công.

Chọn condition phù hợp với mục tiêu:

| Condition | Điều được xác nhận | Giới hạn |
|---|---|---|
| `<available file="..."/>` | Tệp tồn tại | Không xác nhận nội dung hoặc tính sẵn sàng của dịch vụ |
| `<socket server="..." port="..."/>` | Kết nối TCP đến host/port thành công | Không xác nhận API hoặc nghiệp vụ hoạt động |
| Condition HTTP phù hợp với phiên bản Ant | Endpoint phản hồi theo điều kiện của condition | Cần kiểm tra cách condition đánh giá status và response |
| Marker do ứng dụng tạo | Ứng dụng đã đạt mốc readiness do nó định nghĩa | Chỉ đáng tin nếu marker được tạo đúng thời điểm và được dọn trước lần chạy |

### 4.2. Chờ dịch vụ trên host khác

`server` có thể là hostname hoặc địa chỉ IP của máy cung cấp dịch vụ. Ví dụ:

```xml
<socket server="test-db.internal.example" port="5432"/>
```

Khi chờ tài nguyên từ xa, timeout cần tính đến DNS, mạng, firewall và tải của dịch vụ. Không dùng địa chỉ loopback `127.0.0.1` nếu dịch vụ nằm trên máy khác.

## 5. Kết hợp nhiều điều kiện

Ant cung cấp condition logic như `<and>`, `<or>` và `<not>`. Có thể dùng chúng bên trong `<waitfor>` để mô tả trạng thái cần đạt.

### 5.1. Chờ tất cả điều kiện cùng đúng

Ví dụ chờ cả marker file lẫn cổng TCP:

```xml
<waitfor maxwait="90"
         maxwaitunit="second"
         checkevery="500"
         checkeveryunit="millisecond"
         timeoutproperty="service.ready.timeout">
    <and>
        <available file="${service.ready.file}" type="file"/>
        <socket server="127.0.0.1" port="8080"/>
    </and>
</waitfor>
```

`<and>` chỉ đúng khi cả hai condition đúng. Điều này hữu ích nếu marker xác nhận ứng dụng hoàn tất startup và socket xác nhận endpoint thực sự nhận kết nối.

### 5.2. Chờ một trong nhiều điều kiện

Nếu dịch vụ có nhiều endpoint thay thế, có thể dùng `<or>`:

```xml
<waitfor maxwait="30"
         maxwaitunit="second"
         timeoutproperty="endpoint.timeout">
    <or>
        <socket server="127.0.0.1" port="8080"/>
        <socket server="127.0.0.1" port="8081"/>
    </or>
</waitfor>
```

Condition đúng khi ít nhất một cổng nhận kết nối. Chỉ dùng cấu trúc này khi hai endpoint thật sự thay thế được cho nhau. Nếu ứng dụng cần cả hai cổng, dùng `<and>`.

### 5.3. Phủ định condition bằng `<not>`

`<not>` đảo kết quả condition bên trong. Ví dụ chờ một tệp khóa biến mất:

```xml
<waitfor maxwait="120"
         maxwaitunit="second"
         checkevery="1"
         checkeveryunit="second"
         timeoutproperty="lock.timeout">
    <not>
        <available file="build/deploy.lock" type="file"/>
    </not>
</waitfor>
```

Build tiếp tục khi `deploy.lock` không còn tồn tại. Nếu tệp khóa vẫn còn sau hai phút, timeout property được đặt. Không xóa lock file chỉ để làm condition đúng nếu chưa xác định tiến trình nào đang sở hữu nó.

## 6. Dùng `waitfor` sau khi khởi chạy tiến trình ngoài

Một quy trình thường có ba phần: chuẩn bị trạng thái, khởi động tiến trình và chờ readiness. Task `<exec>` có thể chạy chương trình ngoài; `waitfor` sau đó kiểm tra condition.

Ví dụ minh họa:

```xml
<property name="service.work.dir" location="${basedir}/build/test-service"/>
<property name="service.ready.file" location="${service.work.dir}/ready.flag"/>

<target name="prepare-service">
    <delete dir="${service.work.dir}" quiet="true"/>
    <mkdir dir="${service.work.dir}"/>
</target>

<target name="start-service" depends="prepare-service">
    <exec executable="${basedir}/tools/test-server"
          dir="${service.work.dir}"
          spawn="true"
          failonerror="false">
        <arg value="--ready-file"/>
        <arg file="${service.ready.file}"/>
    </exec>
</target>

<target name="wait-service" depends="start-service">
    <waitfor maxwait="90"
             maxwaitunit="second"
             checkevery="500"
             checkeveryunit="millisecond"
             timeoutproperty="service.startup.timeout">
        <available file="${service.ready.file}" type="file"/>
    </waitfor>
    <fail if="service.startup.timeout"
          message="Test server did not become ready within 90 seconds."/>
</target>

<target name="integration-test" depends="wait-service">
    <!-- Chạy test sau khi service đã sẵn sàng. -->
</target>
```

Đây là ví dụ khung: executable `tools/test-server` cần hỗ trợ tùy chọn `--ready-file` và chỉ tạo marker khi thật sự sẵn sàng. Trên Windows, cần thay executable bằng chương trình phù hợp, chẳng hạn `.exe` hoặc script được gọi qua shell.

### 6.1. Hiểu `spawn="true"`

Với `<exec spawn="true">`, Ant khởi chạy tiến trình và không chờ tiến trình đó kết thúc như một lệnh thông thường. Điều này phù hợp khi tiến trình là server cần tiếp tục chạy trong lúc test.

Đổi lại, build không nhận được mã thoát cuối cùng của tiến trình được spawn theo cách thông thường. Nếu server khởi động rồi thoát ngay, target `start-service` vẫn có thể kết thúc trước khi `waitfor` phát hiện marker. Vì vậy, cần kiểm tra readiness và log để phát hiện trường hợp startup thất bại.

Nếu lệnh ngoài chỉ thực hiện một công việc ngắn rồi kết thúc, không dùng `spawn="true"`. Hãy để `<exec>` chờ lệnh hoàn thành và kiểm tra mã thoát bằng `failonerror="true"`.

### 6.2. `waitfor` không quản lý vòng đời server

Khi `waitfor` timeout, nó không tự gửi tín hiệu dừng hoặc kill tiến trình đã được spawn. Build cần một cơ chế shutdown riêng, ví dụ:

- Gọi endpoint hoặc lệnh điều khiển shutdown của test server.
- Dùng script wrapper có PID file và lệnh dừng tương ứng.
- Để CI chạy service trong container hoặc job có lifecycle được quản lý.
- Dùng task cleanup sau khi test hoàn thành và bảo đảm cleanup cũng chạy khi test lỗi.

Không nên xóa PID file hoặc marker mà không kiểm tra tiến trình tương ứng, vì có thể để lại server chạy nền hoặc tác động đến tiến trình khác.

## 7. Quản lý timeout trong target

Timeout là một quyết định của build: chờ bao lâu trước khi xem trạng thái là lỗi hoặc bỏ qua. Hãy phân biệt timeout của `<waitfor>` với timeout của task chạy tiến trình.

| Cơ chế | Giới hạn điều gì? | Ví dụ |
|---|---|---|
| `<waitfor maxwait="...">` | Thời gian chờ một condition đạt được | Chờ port 8080 mở tối đa 90 giây |
| `<exec timeout="...">` | Thời gian chờ lệnh ngoài kết thúc | Lệnh migration chạy tối đa 5 phút |
| `<java timeout="...">` | Thời gian chạy JVM con do task `<java>` khởi chạy | Test launcher tối đa 10 phút |
| Timeout của CI/job/container | Thời gian tối đa cho toàn bộ bước hoặc job | Pipeline dừng sau 20 phút |

Không thay thế timeout của tiến trình bằng timeout của `waitfor`. Một tiến trình có thể treo khi đang chạy lệnh; lúc đó condition không phải vấn đề duy nhất. Dùng timeout đúng task quản lý tiến trình.

### 7.1. Dùng timeout property để chọn nhánh xử lý

Có thể xử lý timeout bằng target điều kiện:

```xml
<target name="wait-for-database">
    <waitfor maxwait="45"
             maxwaitunit="second"
             timeoutproperty="database.timeout">
        <socket server="127.0.0.1" port="5432"/>
    </waitfor>
</target>

<target name="database-ready"
        depends="wait-for-database"
        unless="database.timeout">
    <echo message="Database is accepting TCP connections."/>
</target>

<target name="database-not-ready"
        depends="wait-for-database"
        if="database.timeout">
    <fail message="Database startup timed out after 45 seconds."/>
</target>
```

`unless` và `if` kiểm tra sự tồn tại của timeout property. Khi condition thành công, property không được đặt nên target `database-ready` chạy. Khi timeout, property tồn tại nên target `database-not-ready` chạy.

Nếu target cần dừng ngay sau timeout, cách dùng `<fail if="database.timeout">` trong cùng target thường ngắn gọn hơn. Tách target hữu ích khi muốn có nhánh xử lý hoặc log riêng.

### 7.2. Chọn chính sách khi timeout

Không phải mọi timeout đều cần làm build thất bại. Có thể chọn một trong các chính sách:

- **Fail fast**: dừng build khi dịch vụ bắt buộc không sẵn sàng.
- **Retry hoặc fallback**: chuyển sang endpoint dự phòng hoặc thử một quy trình phục hồi khác.
- **Skip optional step**: bỏ qua một bước tùy chọn nếu môi trường không cung cấp dịch vụ.
- **Collect diagnostics**: lấy log, trạng thái tiến trình hoặc thông tin cổng trước khi dừng.

Với compile, package hoặc release, dependency bắt buộc không sẵn sàng thường phải làm build thất bại. Với một bước kiểm tra tùy chọn, có thể bỏ qua nhưng cần ghi thông báo rõ ràng để người đọc log biết bước đó chưa chạy.

## 8. Thu thập log khi timeout

Khi dịch vụ không sẵn sàng, chỉ báo `timeout` thường chưa đủ để tìm nguyên nhân. Hãy lưu stdout/stderr của tiến trình và in vị trí log trong thông báo lỗi.

Ví dụ gọi server wrapper và lưu log:

```xml
<exec executable="${basedir}/tools/start-test-server"
      dir="${service.work.dir}"
      spawn="true"
      output="${service.work.dir}/server.out.log"
      error="${service.work.dir}/server.err.log">
    <arg value="--port"/>
    <arg value="8080"/>
</exec>
```

Sau khi wait timeout, có thể in đường dẫn log:

```xml
<fail if="service.startup.timeout"
      message="Server did not become ready. Inspect ${service.work.dir}/server.out.log and server.err.log."/>
```

Với tiến trình spawn, việc thu thập output phụ thuộc cách `<exec>` chuyển hướng stdout/stderr và hệ điều hành. Nếu cần quản lý process, log rotation và shutdown đáng tin cậy, một script wrapper hoặc container thường phù hợp hơn việc dồn toàn bộ logic vào build file.

## 9. Chờ một health endpoint

Một cổng TCP mở không đồng nghĩa dịch vụ đã phục vụ request thành công. Với ứng dụng HTTP, health endpoint thường là tín hiệu readiness tốt hơn.

Một số phiên bản Ant có condition HTTP trong thư viện condition của Ant. Cú pháp và cách condition đánh giá response phụ thuộc phiên bản, vì vậy hãy kiểm tra tài liệu của bản Ant đang dùng trước khi đưa vào build. Nếu không có condition phù hợp, có thể gọi một script hoặc chương trình nhỏ thực hiện HTTP health check và trả mã thoát 0 khi dịch vụ sẵn sàng.

Ví dụ dùng một chương trình kiểm tra endpoint trong vòng lặp bên ngoài:

```xml
<exec executable="${basedir}/tools/check-health"
      dir="${basedir}"
      failonerror="true"
      timeout="10000">
    <arg value="http://127.0.0.1:8080/health/ready"/>
</exec>
```

Đoạn này chỉ thực hiện một lần kiểm tra. Nếu cần polling, hãy đặt nó trong một wrapper có thời hạn tổng thể hoặc dùng một condition phù hợp trực tiếp với `<waitfor>`. Không dùng một lần gọi HTTP thành công như bằng chứng readiness nếu endpoint chỉ kiểm tra process còn sống mà không kiểm tra dependency bắt buộc.

## 10. Tránh race condition và timeout không ổn định

Một số thực hành giúp build ít phụ thuộc vào tốc độ máy:

1. Chờ condition có ý nghĩa với bước kế tiếp, không chỉ chờ thời gian cố định.
2. Xóa marker cũ trước khi khởi động tiến trình mới.
3. Dùng thư mục làm việc riêng cho mỗi lần build hoặc mỗi test run.
4. Đặt timeout dựa trên dữ liệu thời gian startup thực tế và giới hạn CI.
5. Dùng chu kỳ polling đủ hợp lý để không tạo quá nhiều kết nối hoặc truy vấn.
6. Thu thập log khi timeout để phân biệt server chưa khởi động, server crash và dependency chưa sẵn sàng.
7. Dọn tiến trình và tài nguyên sau test, kể cả khi test thất bại.

Nếu nhiều build chạy song song, tránh dùng chung cổng cố định hoặc marker file cố định. Mỗi run nên có cổng, thư mục và tên marker riêng để không đọc nhầm trạng thái của run khác.

## 11. Ví dụ hoàn chỉnh: khởi động service, chờ readiness và chạy test

Ví dụ sau mô tả một server test được khởi động bằng script, tạo marker khi readiness đạt, sau đó Ant chờ tối đa 90 giây trước khi gọi test launcher.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="waitfor-integration" default="integration-test" basedir=".">

    <property name="build.dir" location="${basedir}/build"/>
    <property name="service.dir" location="${build.dir}/test-service"/>
    <property name="ready.file" location="${service.dir}/ready.flag"/>
    <property name="service.port" value="8080"/>

    <target name="prepare-service">
        <delete dir="${service.dir}" quiet="true"/>
        <mkdir dir="${service.dir}"/>
    </target>

    <target name="start-service" depends="prepare-service">
        <exec executable="${basedir}/tools/start-test-server"
              dir="${service.dir}"
              spawn="true"
              output="${service.dir}/server.out.log"
              error="${service.dir}/server.err.log">
            <arg value="--port"/>
            <arg value="${service.port}"/>
            <arg value="--ready-file"/>
            <arg file="${ready.file}"/>
        </exec>
    </target>

    <target name="wait-service" depends="start-service">
        <waitfor maxwait="90"
                 maxwaitunit="second"
                 checkevery="500"
                 checkeveryunit="millisecond"
                 timeoutproperty="service.startup.timeout">
            <and>
                <available file="${ready.file}" type="file"/>
                <socket server="127.0.0.1" port="${service.port}"/>
            </and>
        </waitfor>

        <fail if="service.startup.timeout"
              message="Test service did not become ready. Inspect ${service.dir}/server.out.log and server.err.log."/>
    </target>

    <target name="integration-test" depends="wait-service">
        <java classname="com.example.tests.IntegrationTestLauncher"
              fork="true"
              dir="${service.dir}"
              timeout="300000"
              failonerror="true">
            <classpath>
                <pathelement location="${build.dir}/test-classes"/>
                <pathelement location="${build.dir}/classes"/>
                <fileset dir="lib/test">
                    <include name="*.jar"/>
                </fileset>
            </classpath>
            <sysproperty key="test.base.url"
                         value="http://127.0.0.1:${service.port}"/>
            <arg value="--suite"/>
            <arg value="integration"/>
        </java>
    </target>

    <target name="clean">
        <delete dir="${build.dir}" quiet="true"/>
    </target>

</project>
```

Script `start-test-server` và ứng dụng server cần được triển khai theo môi trường thực tế. Script phải tạo `ready.flag` sau khi endpoint đạt trạng thái sẵn sàng và ghi log vào những tệp được chỉ định. Nếu script chỉ tạo marker ngay sau khi fork một tiến trình khác, marker không còn phản ánh readiness thực tế.

Target `wait-service` chờ đồng thời marker và socket. Nếu hết 90 giây, Ant dừng với thông báo chỉ rõ log cần xem. Khi service sẵn sàng, target `integration-test` chạy trong JVM con với timeout riêng năm phút.

Ví dụ chưa trình bày lệnh shutdown server. Trong build thực tế, hãy bổ sung một target cleanup hoặc để CI quản lý service lifecycle, bảo đảm server không tiếp tục chạy sau khi test kết thúc.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `<waitfor>` kết thúc ngay dù server mới khởi động | Marker file từ lần chạy trước vẫn còn | Xóa marker trước khi khởi chạy server mới |
| Waitfor timeout dù server đang chạy | Condition kiểm tra sai host, port hoặc đường dẫn | Kiểm tra đúng endpoint, basedir, quyền truy cập và log server |
| Port mở nhưng test vẫn nhận lỗi 503 | Socket chỉ xác nhận TCP, chưa xác nhận ứng dụng sẵn sàng | Chờ health endpoint hoặc marker được tạo sau health check |
| Build tiếp tục sau timeout | Chỉ khai báo `timeoutproperty` mà không kiểm tra nó | Dùng `<fail if="...">` hoặc nhánh xử lý riêng |
| Server còn chạy sau khi build thất bại | `waitfor` không dừng tiến trình spawn | Bổ sung shutdown/cleanup hoặc dùng container/process supervisor |
| Timeout xảy ra ngẫu nhiên trên CI | Thời gian startup thay đổi theo tải hoặc dependency | Đo thời gian thực tế, tăng maxwait hợp lý và kiểm tra readiness đúng |
| Nhiều build đọc nhầm marker hoặc cổng | Các run dùng chung tài nguyên | Dùng thư mục và cổng riêng theo build ID hoặc worker |
| Tệp marker xuất hiện nhưng nội dung chưa hoàn chỉnh | Ứng dụng tạo file trước khi ghi xong | Ghi file tạm rồi đổi tên nguyên tử khi hoàn tất, hoặc kiểm tra nội dung/health riêng |
| Waitfor kiểm tra quá thường xuyên | `checkevery` quá nhỏ | Tăng chu kỳ polling để giảm tải |
| Lệnh ngoài bị treo nhưng waitfor không liên quan | Lệnh chưa kết thúc hoặc process quản lý không đúng | Dùng timeout của `<exec>`/`<java>` hoặc quản lý tiến trình bằng wrapper |

## 13. Checklist dùng `waitfor`

- [ ] Đã xác định condition phản ánh trạng thái cần chờ.
- [ ] Condition không thể thỏa mãn nhầm từ dữ liệu của lần chạy trước.
- [ ] Đã chọn `maxwait` và `maxwaitunit` phù hợp.
- [ ] Đã chọn `checkevery` và `checkeveryunit` để cân bằng độ phản hồi với chi phí polling.
- [ ] Đã khai báo `timeoutproperty` cho bước quan trọng.
- [ ] Đã xử lý timeout bằng `<fail>` hoặc nhánh fallback có chủ đích.
- [ ] Đã phân biệt cổng TCP mở với ứng dụng thực sự sẵn sàng.
- [ ] Tiến trình ngoài tạo marker sau khi readiness đạt, nếu dùng marker file.
- [ ] Đã lưu log stdout/stderr để điều tra khi timeout.
- [ ] Đã dùng timeout riêng cho lệnh hoặc JVM con nếu chúng có thể treo.
- [ ] Đã có kế hoạch dừng tiến trình và dọn tài nguyên sau test.
- [ ] Build song song dùng marker, working directory và port riêng.

`waitfor` giúp các target Ant đồng bộ với trạng thái thực tế của tiến trình ngoài bằng cách polling condition có giới hạn thời gian. Khi kết hợp condition phù hợp, timeout property, log chẩn đoán và cleanup rõ ràng, build tránh được nhiều lỗi do race condition và không phải chờ cố định lâu hơn mức cần thiết.

Tài liệu tham khảo: [Apache Ant Manual — Waitfor Task](https://ant.apache.org/manual/Tasks/waitfor.html) và [Apache Ant Manual — Conditions](https://ant.apache.org/manual/Tasks/conditions.html).
