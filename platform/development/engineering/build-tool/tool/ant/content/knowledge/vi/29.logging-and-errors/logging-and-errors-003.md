# Chọn logger và listener bằng tùy chọn dòng lệnh trong Apache Ant

Khi chạy Apache Ant, cùng một bản dựng có thể cần nhiều kiểu nhật ký: lập trình viên muốn xem lỗi trên terminal, người kiểm thử cần báo cáo XML, còn hệ thống CI cần lưu lại thông tin để tra cứu khi build thất bại. Ant cho phép cấu hình các cách quan sát này ngay trên dòng lệnh, không cần sửa `build.xml`.

Hai tùy chọn quan trọng nhất là `-logger` (chọn bộ ghi nhật ký chính) và `-listener` (đăng ký đối tượng theo dõi sự kiện bổ sung). Chúng đều nhận **tên lớp Java đầy đủ**, nhưng đảm nhiệm những vai trò khác nhau.

## 1. Hiểu cơ chế ghi nhật ký của Ant

Trong quá trình thực thi, Ant phát các sự kiện như:

- `buildStarted` / `buildFinished`: bắt đầu hoặc kết thúc toàn bộ bản dựng.
- `targetStarted` / `targetFinished`: bắt đầu hoặc kết thúc một `target`.
- `taskStarted` / `taskFinished`: bắt đầu hoặc kết thúc một tác vụ như `<javac>`, `<copy>` hay `<echo>`.
- `messageLogged`: một task hoặc thành phần Ant ghi thông điệp với mức ưu tiên cụ thể.

Một đối tượng triển khai `org.apache.tools.ant.BuildListener` có thể nhận các sự kiện đó. `org.apache.tools.ant.BuildLogger` mở rộng `BuildListener`, đồng thời có khả năng nhận luồng xuất/luồng lỗi, mức ghi log và chế độ hiển thị do Ant cấu hình.

```text
                       Apache Ant
                 (build, target, task)
                          |
                     BuildEvent
                          |
          +---------------+------------------+
          |                                  |
    Logger chính                       Listener bổ sung
    (mặc định hoặc -logger)             (-listener, có thể nhiều)
          |                                  |
  Console / -logfile                Theo dõi, thu thập,
  theo mức -verbose...              tạo tệp hoặc tích hợp khác
```

**Điểm cần phân biệt:**

- **Logger** quyết định cách trình bày nhật ký chính. Nếu không dùng `-logger`, Ant sử dụng `org.apache.tools.ant.DefaultLogger`.
- **Listener** quan sát sự kiện và thực hiện hành động do lớp đó định nghĩa. Thêm `-listener` **không tự động thay thế** logger chính.
- Một lớp có thể vừa là logger vừa là listener, ví dụ `org.apache.tools.ant.XmlLogger`. Hành vi cụ thể có thể khác nhau tùy nó được nạp qua `-logger` hay `-listener`.
- Logger và listener xử lý sự kiện đồng bộ trong quá trình build. Thành phần ghi log quá chậm có thể làm thời gian build tăng lên.

## 2. Các tùy chọn dòng lệnh liên quan

Cú pháp tổng quát:

```bash
ant [options] [target [target2 ...]]
```

| Tùy chọn | Mục đích | Ghi chú |
|---|---|---|
| `-logger <classname>` | Chọn **một** logger chính | Lớp phải triển khai `BuildLogger`; thay thế logger mặc định. |
| `-listener <classname>` | Thêm một listener | Có thể khai báo `-listener` nhiều lần để đăng ký nhiều lớp. |
| `-logfile <file>` hoặc `-l <file>` | Ghi luồng nhật ký chính vào tệp | Không đồng nghĩa việc mọi listener đều ghi vào tệp này. |
| `-quiet` hoặc `-q` | Giảm thông điệp được hiển thị | Phù hợp khi chỉ cần thông tin quan trọng. |
| `-silent` hoặc `-S` | Chỉ hiện đầu ra task và lỗi build | Ít thông tin hơn chế độ thông thường. |
| `-verbose` hoặc `-v` | Hiện thông điệp chi tiết | Hữu ích để tìm task và cấu hình gây lỗi. |
| `-debug` hoặc `-d` | Hiện mức thông tin gỡ lỗi | Rất nhiều đầu ra; nên dùng có mục đích. |
| `-emacs` hoặc `-e` | Bỏ một số thành phần trang trí của log | Hữu ích khi cần đọc hoặc xử lý đầu ra dạng văn bản. |
| `-lib <path>` | Bổ sung JAR hoặc lớp Java vào classpath của Ant | Cần khi sử dụng logger/listener tự viết hoặc từ thư viện ngoài. |
| `-Dname=value` | Truyền property cho bản dựng | Một số logger/listener đọc property để chọn tệp đầu ra. |
| `-f <file>` hoặc `-buildfile <file>` | Chọn tệp build | Dùng trong ví dụ để chỉ rõ `build.xml`. |

Có thể xem các tùy chọn mà phiên bản Ant trên máy hỗ trợ bằng `ant -help`. Với `-quiet`, `-verbose` và `-debug`, thông thường hãy chọn mức phù hợp cho một lần chạy, tránh kết hợp các mức mâu thuẫn.

## 3. Tạo ví dụ để quan sát sự khác biệt

Tạo tệp `build.xml` trong một thư mục thử nghiệm:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="cli-log-demo" default="build">
    <target name="prepare">
        <echo level="info" message="Chuẩn bị dự án"/>
        <echo level="verbose" message="Chi tiết chuẩn bị"/>
        <echo level="debug" message="Thông tin để gỡ lỗi"/>
    </target>

    <target name="build" depends="prepare">
        <echo message="Đang thực hiện bản dựng"/>
        <fail if="simulate.failure"
              message="Lỗi giả lập khi build"/>
    </target>
</project>
```

Trong ví dụ này, `build` phụ thuộc vào `prepare`, còn property `simulate.failure` cho phép chủ động tạo lỗi. Lệnh có `-Dsimulate.failure=true` sẽ kích hoạt task `<fail>`; không có property đó thì build kết thúc bình thường.

Chạy ba chế độ đầu ra cơ bản:

```bash
ant -f build.xml build
ant -f build.xml -verbose build
ant -f build.xml -debug build
```

Ở chế độ thường, Ant hiển thị các thông điệp mức `info` trở lên theo chính sách của logger. `-verbose` bổ sung thông điệp `verbose`; `-debug` cho phép xem thêm thông điệp `debug` cùng nhiều chi tiết nội bộ. Đầu ra thực tế có thể nhiều hơn các dòng `<echo>` vì Ant và các task khác cũng ghi log.

## 4. Chọn một logger bằng `-logger`

Cú pháp:

```bash
ant -f build.xml -logger ten.package.LoggerClass build
```

### 4.1. Dùng logger mặc định

```bash
ant -f build.xml -logger org.apache.tools.ant.DefaultLogger build
```

`DefaultLogger` là lựa chọn ngầm định khi không chỉ định `-logger`. Nó trình bày target, các dòng thông báo và kết quả `BUILD SUCCESSFUL` hoặc `BUILD FAILED` theo phong cách quen thuộc của Ant. Khai báo tường minh thường chỉ cần thiết khi muốn làm rõ cấu hình hoặc so sánh các logger.

### 4.2. Giảm các dòng tiêu đề không cần thiết với NoBannerLogger

```bash
ant -f build.xml -logger org.apache.tools.ant.NoBannerLogger build
```

`NoBannerLogger` tránh in tiêu đề của target không có đầu ra hữu ích. Nó phù hợp với build gồm nhiều target phụ nhưng chỉ muốn tập trung vào hoạt động thực sự tạo thông điệp.

### 4.3. Gắn thời điểm kết thúc bằng TimestampedLogger

```bash
ant -f build.xml -logger org.apache.tools.ant.listener.TimestampedLogger build
```

`TimestampedLogger` gần giống logger mặc định nhưng bổ sung dấu thời gian ở thông báo kết thúc build. Có thể dùng khi cần đối chiếu nhiều lượt chạy trong lịch sử CI hoặc nhật ký vận hành.

### 4.4. Theo dõi thời gian thực thi bằng ProfileLogger

```bash
ant -f build.xml -logger org.apache.tools.ant.listener.ProfileLogger build
```

`ProfileLogger` bổ sung thời điểm và thời lượng thực thi của build, target và task. Chọn nó khi cần tìm phần nào của quy trình build tốn thời gian. Đây là thông tin đo thời lượng do logger cung cấp, không thay thế một công cụ profiling JVM chuyên sâu.

### 4.5. Hiển thị màu với AnsiColorLogger

```bash
ant -f build.xml -logger org.apache.tools.ant.listener.AnsiColorLogger build
```

`AnsiColorLogger` sử dụng mã điều khiển màu ANSI để phân biệt mức thông báo. Hiệu quả phụ thuộc terminal có hỗ trợ ANSI hay không. Nếu kết hợp với `-logfile`, các mã ANSI có thể được ghi nguyên vào tệp và làm log khó xử lý bằng công cụ văn bản thuần.

### 4.6. Chọn logger cho dự án nhiều module con

Với build sử dụng `<ant>` hoặc `<subant>` để chạy các dự án con, có thể dùng:

```bash
ant -logger org.apache.tools.ant.listener.BigProjectLogger -f build.xml build
```

`BigProjectLogger` giúp nhận biết tên dự án đang chạy, ranh giới dự án con và target tương ứng. `SimpleBigProjectLogger` có thông tin về dự án con nhưng trình bày gọn hơn. Với ví dụ một project đơn giản ở trên, lợi ích của hai logger này chưa rõ bằng khi chạy build nhiều project.

## 5. Thêm listener bằng `-listener`

Cú pháp:

```bash
ant -f build.xml -listener ten.package.ListenerClass build
```

Listener **được cộng thêm** vào danh sách đối tượng quan sát sự kiện. Đây là cách thích hợp để tạo đầu ra thứ hai, lưu dấu vết build hoặc kết nối một cơ chế theo dõi riêng, đồng thời vẫn giữ nhật ký chính trên terminal.

### 5.1. Vừa xem log thường, vừa tạo báo cáo XML

```bash
ant -f build.xml \
    -listener org.apache.tools.ant.XmlLogger \
    -DXmlLogger.file=build-events.xml \
    build
```

> Lệnh nhiều dòng ở trên dùng dấu `\` để nối dòng trong shell kiểu Unix. Trên Windows hoặc khi muốn dùng ở mọi terminal, nhập thành một dòng như bên dưới.

```text
ant -f build.xml -listener org.apache.tools.ant.XmlLogger -DXmlLogger.file=build-events.xml build
```

`XmlLogger` đăng ký làm listener sẽ thu thập sự kiện và ghi báo cáo XML vào `build-events.xml`. Nếu không đặt `XmlLogger.file`, tên tệp mặc định là `log.xml`. Logger mặc định vẫn xuất thông tin ra terminal.

Báo cáo XML được dựng từ các sự kiện của build, bao gồm thông tin target, task và thời lượng. `XmlLogger` gom dữ liệu để hoàn thiện nội dung khi build kết thúc, vì vậy **không nên kỳ vọng XML xuất hiện đầy đủ trong lúc build đang chạy**.

### 5.2. Dùng XmlLogger làm logger chính

```bash
ant -f build.xml \
    -logger org.apache.tools.ant.XmlLogger \
    -logfile build-report.xml \
    build
```

Khi chọn `XmlLogger` qua `-logger`, nó trở thành bộ ghi nhật ký chính và đưa nội dung XML vào luồng đầu ra của logger. `-logfile build-report.xml` chuyển luồng đó đến tệp tương ứng.

Sự khác biệt chính:

| Cách dùng | Nhật ký trên terminal | Tệp XML |
|---|---|---|
| `-listener org.apache.tools.ant.XmlLogger` | Logger mặc định vẫn hoạt động | `log.xml` hoặc `XmlLogger.file` |
| `-logger org.apache.tools.ant.XmlLogger -logfile build-report.xml` | Nhật ký chính được chuyển sang tệp | `build-report.xml` |

Vì thế, nếu muốn **có cả log văn bản dễ đọc và báo cáo XML**, thông thường nên dùng `XmlLogger` ở vai trò listener.

### 5.3. Đăng ký nhiều listener

```bash
ant -f build.xml \
    -listener org.apache.tools.ant.XmlLogger \
    -listener com.example.ant.AuditListener \
    -DXmlLogger.file=events.xml \
    -lib tools/ant-audit.jar \
    build
```

Ví dụ giả định `tools/ant-audit.jar` chứa lớp `com.example.ant.AuditListener` đã được biên dịch và mọi thư viện phụ thuộc cần thiết. Ant sẽ đăng ký cả hai listener. Mỗi listener xử lý các sự kiện theo logic của chính nó; không được mặc định rằng chúng tạo cùng một định dạng log hay cùng một tệp.

**Lưu ý:** `-logger` chỉ chọn một logger chính; lặp lại `-logger` để chỉ định hai lớp là cách dùng sai. Muốn thêm cơ chế ghi nhận song song, hãy xem xét `-listener`.

## 6. Kết hợp logger, listener và tệp nhật ký

Có thể kết hợp các tùy chọn để đáp ứng nhiều nhu cầu trong cùng một lượt chạy:

```bash
ant -f build.xml \
    -logger org.apache.tools.ant.NoBannerLogger \
    -listener org.apache.tools.ant.XmlLogger \
    -DXmlLogger.file=events.xml \
    -logfile console.log \
    -verbose \
    build
```

Trong cấu hình này:

1. `NoBannerLogger` tạo nhật ký văn bản của bản dựng theo mức `verbose`.
2. `-logfile console.log` chuyển nhật ký chính vào `console.log`.
3. `XmlLogger` nhận các sự kiện và tạo báo cáo `events.xml` độc lập.
4. Build vẫn trả về mã thoát thành công hoặc thất bại theo kết quả thực thi; việc đổi logger không biến một build lỗi thành build thành công.

Nếu muốn thử trường hợp lỗi:

```bash
ant -f build.xml \
    -listener org.apache.tools.ant.XmlLogger \
    -DXmlLogger.file=failed-build.xml \
    -Dsimulate.failure=true \
    build
```

Lúc đó target `build` chạy đến `<fail>` và kết thúc với `BUILD FAILED`. Listener vẫn có cơ hội ghi nhận sự kiện hoàn tất build cùng thông tin lỗi. Điều này hữu ích khi kiểm tra hệ thống báo cáo thất bại của CI.

## 7. Nạp logger hoặc listener tự viết với `-lib`

Các logger và listener có sẵn của Ant không cần JAR bổ sung. Với lớp do nhóm phát triển tự viết, classpath của Ant phải nhìn thấy lớp trước khi quá trình build bắt đầu.

Ví dụ, giả sử đã đóng gói:

```text
tools/
└── audit-listener.jar
    └── com/example/ant/AuditListener.class
```

Chạy:

```bash
ant -lib tools/audit-listener.jar \
    -listener com.example.ant.AuditListener \
    -f build.xml build
```

Nếu đường dẫn có khoảng trắng, đặt đường dẫn trong dấu ngoặc kép:

```text
ant -lib "C:/build tools/audit-listener.jar" -listener com.example.ant.AuditListener -f build.xml build
```

Lớp được chọn phải tương thích với giao diện tương ứng: `BuildLogger` cho `-logger`, `BuildListener` cho `-listener`, có thể tạo đối tượng theo cách Ant yêu cầu và không thiếu các JAR phụ thuộc. Thông thường các lớp này cần constructor công khai không tham số.

Đối với listener tự viết, cần tránh ghi trực tiếp `System.out` hoặc `System.err` trong callback `messageLogged`. Ant có thể chuyển đầu ra chuẩn thành sự kiện log; việc ghi vào đó từ callback có nguy cơ tạo vòng lặp log vô hạn. Logger tự viết nên sử dụng các luồng Ant cấp qua cơ chế `BuildLogger`.

## 8. Mức thông báo và cách chọn tổ hợp phù hợp

Các mức thông điệp phổ biến trong Ant có thứ tự từ ít đến nhiều chi tiết: `error`, `warning`, `info`, `verbose`, `debug`. Mức đầu ra được chọn quyết định **thông điệp nào được logger trình bày**, trong khi sự kiện mà listener nhận được và cách nó xử lý còn phụ thuộc vào từng implementation.

| Mục tiêu | Lệnh gợi ý | Lý do |
|---|---|---|
| Chạy build hằng ngày | `ant -f build.xml build` | Logger mặc định thường đủ dễ đọc. |
| Chỉ theo dõi thông tin quan trọng | `ant -q -f build.xml build` | Giảm lượng thông điệp. |
| Điều tra lỗi cấu hình hoặc task | `ant -v -f build.xml build` | Hiển thị thêm thông tin hoạt động. |
| Cần phân tích sâu | `ant -d -f build.xml build` | Đưa thêm thông tin debug ra đầu ra. |
| Tìm target/task chậm | `ant -logger org.apache.tools.ant.listener.ProfileLogger -f build.xml build` | Có thông tin thời lượng từng phần. |
| Lưu báo cáo máy có thể đọc | `ant -listener org.apache.tools.ant.XmlLogger -f build.xml build` | Vừa có log thường vừa có XML. |
| Tách log chính sang tệp | `ant -logfile build.log -f build.xml build` | Phù hợp khi cần lưu lịch sử lượt chạy. |

Khi đưa log lên CI, cân nhắc rằng `-debug` có thể làm lộ đường dẫn, property hoặc thông tin môi trường do các task in ra. Chỉ bật mức phù hợp, quản lý quyền truy cập log và tránh đưa mật khẩu hoặc token vào thông điệp task.

## 9. Những lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ant không tìm thấy logger/listener | Sai tên lớp đầy đủ, thiếu JAR hoặc thiếu dependency | Kiểm tra FQCN; bổ sung classpath qua `-lib`. |
| Build báo lỗi vì khai báo nhiều `-logger` | Ant chỉ cho chọn một logger chính | Giữ một `-logger` và dùng `-listener` cho thành phần bổ sung. |
| Dùng `-listener` nhưng cách trình bày terminal không thay đổi | Listener nhận sự kiện mà không thay thế logger chính | Dùng `-logger` nếu mục tiêu là đổi định dạng nhật ký chính. |
| Không thấy `events.xml` đúng chỗ | Chưa đặt `XmlLogger.file`, đang xem sai thư mục làm việc hoặc build chưa hoàn tất | Đặt đường dẫn tệp rõ ràng; đợi Ant kết thúc rồi kiểm tra. |
| Dùng `-logfile` nhưng listener tạo tệp khác | `-logfile` áp dụng cho luồng của logger chính | Cấu hình đích xuất riêng của listener, chẳng hạn `XmlLogger.file`. |
| Tệp log màu có ký tự điều khiển lạ | `AnsiColorLogger` ghi mã ANSI vào tệp | Dùng logger văn bản thông thường khi cần lưu/parse log. |
| Không thấy thông điệp `verbose` hoặc `debug` | Mức ghi log đang thấp hơn mức thông điệp | Dùng `-verbose` hoặc `-debug` khi cần. |
| Log bị lặp hoặc build chậm rõ rệt | Nạp nhiều listener cùng ghi nội dung hoặc listener xử lý I/O nặng | Xem lại số listener và chi phí ghi sự kiện. |

Khi gặp lỗi khởi tạo listener/logger, hãy xem thông báo exception sớm nhất trong quá trình chạy, đặc biệt là `ClassNotFoundException` và `NoClassDefFoundError`. `ant -version`, `ant -help` và `ant -diagnostics` cũng hữu ích để xác nhận phiên bản và môi trường Ant đang sử dụng.

**Không nên dùng `org.apache.tools.ant.listener.Log4jListener` dựa trên Log4j 1.x cho cấu hình mới:** phiên bản Log4j đó đã ngừng phát triển và có rủi ro bảo mật đã được ghi nhận. Nếu hệ thống hiện tại cần tích hợp thư viện logging, hãy đánh giá phương án tương thích, được duy trì và các phụ thuộc của nó.

## 10. Thực hành chọn cấu hình theo yêu cầu

**Tình huống A — Dự án nhỏ:** Chỉ cần biết build thành công hay lỗi và xem thông điệp task. Chạy `ant -f build.xml build`. Chưa cần chọn logger đặc biệt.

**Tình huống B — Build nhiều dự án con:** Nhật ký lẫn giữa các subproject. Chọn `BigProjectLogger` để phân biệt ngữ cảnh và xác định nhanh project phát sinh lỗi.

**Tình huống C — CI cần hai loại bằng chứng:** Con người đọc `console.log`, công cụ xử lý `events.xml`. Kết hợp `-logger` hoặc logger mặc định với `-logfile`, đồng thời đăng ký `XmlLogger` bằng `-listener`.

**Tình huống D — Build chạy lâu:** Dùng `ProfileLogger` để tìm target và task tiêu tốn thời gian, sau đó mới quyết định có cần đo sâu bằng công cụ khác hay không.

Có thể tự thử với `build.xml` ở mục 3: lần lượt bật `-verbose`, `-debug`, dùng `XmlLogger` theo hai vai trò rồi thêm `-Dsimulate.failure=true`. Quan sát sự khác nhau giữa nhật ký trên terminal, tệp đầu ra và mã kết thúc của Ant.

## 11. Tài liệu tham khảo

- [Apache Ant Manual — Running Apache Ant](https://ant.apache.org/manual/running.html): cú pháp dòng lệnh, `-logger`, `-listener`, `-logfile`, `-lib` và các mức chi tiết.
- [Apache Ant Manual — Listeners & Loggers](https://ant.apache.org/manual/listeners.html): cơ chế sự kiện, các logger tích hợp và cách cấu hình `XmlLogger`.
- [Apache Ant API — BuildListener](https://ant.apache.org/manual/api/org/apache/tools/ant/BuildListener.html) và [BuildLogger](https://ant.apache.org/manual/api/org/apache/tools/ant/BuildLogger.html): giao diện dành cho lớp mở rộng.

Khi chọn công cụ, hãy bắt đầu từ câu hỏi **ai sẽ đọc log và đọc ở đâu**: terminal cần dạng văn bản, CI có thể cần tệp lưu trữ, còn hệ thống xử lý tự động cần định dạng có cấu trúc. Chọn `-logger` cho nhật ký chính và thêm `-listener` khi cần quan sát hoặc xuất dữ liệu bổ sung là cách cấu hình dễ kiểm soát nhất.
