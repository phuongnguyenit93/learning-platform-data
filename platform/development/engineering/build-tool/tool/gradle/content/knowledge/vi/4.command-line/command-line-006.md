# Điều chỉnh log, stacktrace, chế độ cảnh báo và console trong Gradle

## 1. Mục tiêu và mô hình tổng quan

Lệnh Gradle có thể chạy đúng nhưng in quá ít thông tin để hiểu chuyện gì xảy ra, hoặc in hàng nghìn dòng khiến không tìm được nguyên nhân. Để đọc và điều chỉnh output hiệu quả, cần phân biệt **bốn nhóm tuỳ chọn độc lập**:

| Nhóm | Câu hỏi giải quyết | Tuỳ chọn tiêu biểu |
| --- | --- | --- |
| **Log level** | Gradle in **bao nhiêu** thông tin về hoạt động build? | `--quiet`, `--warn`, `--info`, `--debug` |
| **Stacktrace** | **Đường gọi ngoại lệ** khi build lỗi là gì? | `--stacktrace`, `--full-stacktrace` |
| **Warning mode** | Gradle **hiển thị và xử lý cảnh báo** của build ra sao? | `--warning-mode=all`, `summary`, `none`, `fail` |
| **Console mode** | Log có **màu, progress và cách trình bày** thế nào? | `--console=plain`, `auto`, `colored`, `rich`, `verbose` |

Các nhóm này bổ sung cho nhau: `--info` không tự làm stacktrace đầy đủ; `--warning-mode=all` không có nghĩa tất cả log sẽ thành WARN; `--console=plain` không giảm số lượng sự kiện log. Chọn đúng nhóm tiết kiệm thời gian khi debug và giúp log CI ổn định.

Trong bài học, chạy lệnh tại thư mục gốc dự án có Gradle Wrapper:

```bash
./gradlew help --console=plain          # Linux/macOS
```

```powershell
.\gradlew.bat help --console=plain     # Windows PowerShell
```

Gradle Wrapper giúp sử dụng đúng phiên bản Gradle của dự án. `help` là task thường có sẵn; `build`, `test` và các task khác phụ thuộc plugin/dự án. Tuỳ chọn toàn cục có thể viết trước hoặc sau task: `./gradlew --info help` tương đương `./gradlew help --info`. Dùng `./gradlew --help` để xem những tuỳ chọn thực tế của phiên bản đang chạy.

## 2. Log level: điều chỉnh mức chi tiết

Gradle có hệ thống log nhiều cấp. Từ ít đến nhiều nội dung:

1. **ERROR**: lỗi nghiêm trọng.
2. **QUIET**: thông điệp quan trọng được thiết kế để vẫn hiện khi dùng `--quiet`.
3. **WARN/WARNING**: các thông điệp cảnh báo thông thường.
4. **LIFECYCLE**: mốc thực thi và trạng thái build. Đây là **mức mặc định**.
5. **INFO**: nhiều chi tiết hơn về cấu hình, task và xử lý nội bộ.
6. **DEBUG**: log chẩn đoán chi tiết nhất; có thể rất dài.

Bảng lựa chọn:

| Lệnh | Ngưỡng log | Thích hợp khi |
| --- | --- | --- |
| `-q`, `--quiet` | QUIET trở lên | Muốn giảm bớt thông báo tiến trình. |
| `-w`, `--warn` | WARN trở lên | Chỉ quan tâm log cảnh báo và thông điệp quan trọng. |
| Không thêm cờ | LIFECYCLE trở lên | Chạy thông thường, mặc định. |
| `-i`, `--info` | INFO trở lên | Điều tra vì sao task chạy/bị skip, cấu hình và phụ thuộc. |
| `-d`, `--debug` | DEBUG trở lên | Truy vết kỹ thuật chuyên sâu sau khi INFO chưa đủ. |

“Ngưỡng” nghĩa là cấp chi tiết hơn sẽ **bao gồm** các cấp phía trên; `--info` vẫn hiển thị ERROR, QUIET, WARN và LIFECYCLE. `--quiet` không làm mọi dòng biến mất: `logger.quiet(...)` và thông điệp ERROR vẫn có thể xuất hiện. Theo tài liệu, Gradle mặc định chuyển nội dung `println(...)` trong build script sang log mức QUIET; vì vậy dùng `println` để debug có thể tạo output bất ngờ ngay cả khi chọn quiet.

Thử chạy và so sánh cùng một task:

```bash
./gradlew help --quiet --console=plain
./gradlew help --warn --console=plain
./gradlew help --console=plain
./gradlew help --info --console=plain
./gradlew help --debug --console=plain
```

Lượng output thực tế phụ thuộc Gradle, plugin và dự án; những lệnh này **không bảo đảm** cho ra số dòng cố định. INFO thường là bước điều tra đầu tiên. DEBUG có thể ghi ra biến môi trường, thông tin tài khoản/kho artifact hoặc giá trị cấu hình nhạy cảm; tránh bật mặc định trên CI công khai và kiểm tra kỹ trước khi chia sẻ log.

### 2.1. Ví dụ runnable với Kotlin DSL

Thêm task sau vào `build.gradle.kts` trong dự án Kotlin DSL:

```kotlin
tasks.register("demoLogLevels") {
    doLast {
        logger.error("E: error")
        logger.quiet("Q: quiet")
        logger.warn("W: warning")
        logger.lifecycle("L: lifecycle")
        logger.info("I: info")
        logger.debug("D: debug")
    }
}
```

Chạy lần lượt:

```bash
./gradlew demoLogLevels --quiet --console=plain
./gradlew demoLogLevels --console=plain
./gradlew demoLogLevels --info --console=plain
./gradlew demoLogLevels --debug --console=plain
```

Khi **chỉ xét các dòng E/Q/W/L/I/D do task tự tạo**, kỳ vọng:

| Chế độ | Dòng từ task được in |
| --- | --- |
| quiet | `E`, `Q` |
| lifecycle (mặc định) | `E`, `Q`, `W`, `L` |
| info | `E`, `Q`, `W`, `L`, `I` |
| debug | `E`, `Q`, `W`, `L`, `I`, `D` |

Các dòng task name, build summary, lỗi khác hoặc log nội bộ Gradle có thể xuất hiện thêm; không xem bảng này là **toàn bộ stdout chính xác**. Khi viết plugin/task thật, dùng đúng `logger.lifecycle/info/debug/warn/error` để kiểm soát thông tin thay cho `println` tràn lan.

## 3. Stacktrace: tìm đường gọi khi lỗi

Một build thất bại thường in `FAILURE: Build failed with an exception.` và các phần `What went wrong`, `Try`. Đây là mô tả nguyên nhân ban đầu. Stacktrace giúp biết chuỗi lời gọi nào dẫn tới ngoại lệ, đặc biệt khi một Gradle plugin hoặc task custom phát lỗi.

| Cờ | Hành vi | Khi sử dụng |
| --- | --- | --- |
| Không thêm cờ | Chủ yếu in báo cáo lỗi tóm tắt; một số ngoại lệ nội bộ vẫn có trace. | Chạy bình thường. |
| `-s`, `--stacktrace` | In stacktrace thông thường, có thể lược bớt những frame ít hữu ích. | **Lựa chọn đầu tiên** khi gặp lỗi khó hiểu. |
| `-S`, `--full-stacktrace` | In stacktrace đầy đủ, thường dài hơn nhiều, đặc biệt trong Groovy. | Khi trace ngắn chưa đủ để tìm nguyên nhân. |

Ví dụ:

```bash
./gradlew test --stacktrace --console=plain
./gradlew test --info --stacktrace --console=plain
./gradlew test --full-stacktrace --console=plain
```

`--info` kể thêm diễn biến trước lỗi; `--stacktrace` cho biết ngoại lệ đi qua những frame nào. Dùng chung hai cờ khi cần. Không dựa vào `--debug` như lựa chọn thay thế: tài liệu Logging của Gradle khuyến nghị bật `--stacktrace` một cách tường minh khi cần trace lỗi build, kể cả đang dùng DEBUG.

### 3.1. Tự tạo lỗi để so sánh

Trong `build.gradle.kts`, thêm:

```kotlin
tasks.register("failForStacktrace") {
    doLast {
        throw GradleException("Demo failure for stacktrace")
    }
}
```

Chạy:

```bash
./gradlew failForStacktrace --console=plain
./gradlew failForStacktrace --stacktrace --console=plain
```

**Cả hai lần đều cố ý thất bại (exit code khác 0)**. Phần thông điệp nguyên nhân thường chứa:

```text
Execution failed for task ':failForStacktrace'.
> Demo failure for stacktrace
```

Khi có `--stacktrace`, kết quả còn chứa phần trace ngoại lệ và các frame liên quan. Tên file, số dòng và thứ tự frame khác nhau theo phiên bản/môi trường, nên không giả định một output hoàn chỉnh cố định. Đọc từ thông điệp `What went wrong`, tiếp tục tìm `Caused by` và những frame trỏ tới mã bạn kiểm soát. Với tiến trình Java/test được fork ra ngoài Gradle, cần xem thêm stdout/stderr hoặc test report của chính tiến trình đó; Gradle stacktrace không luôn chứa mọi chi tiết của tiến trình con.

## 4. Warning mode: kiểm soát cảnh báo Gradle

Gradle thu thập những cảnh báo liên quan đến build, đặc biệt khi plugin hoặc script dùng API đã lỗi thời (*deprecation*), có nguy cơ không tương thích bản Gradle tương lai. Mặc định Gradle thường **gom cảnh báo thành phần summary** cuối build, thay vì in chi tiết từng chỗ.

Cú pháp: `--warning-mode=all`, `--warning-mode=summary`, `--warning-mode=none`, `--warning-mode=fail`.

| Giá trị | Hiển thị | Có thể làm build thất bại chỉ do cảnh báo? |
| --- | --- | --- |
| `summary` — **mặc định** | Thông báo tóm tắt cuối build khi có cảnh báo. | Không. |
| `all` | Hiển thị từng cảnh báo để truy tới vị trí/nguyên nhân. | Không. |
| `none` | Ẩn cảnh báo mà warning mode quản lý, kể cả summary. | Không. |
| `fail` | Hiển thị đầy đủ và làm build thất bại nếu xuất hiện cảnh báo thuộc cơ chế này. | **Có.** |

Khi nâng cấp Gradle/plugin, chạy:

```bash
./gradlew help --warning-mode=all --console=plain
```

Với dự án đã xử lý cảnh báo và muốn dùng cảnh báo làm tiêu chí chất lượng CI:

```bash
./gradlew build --warning-mode=fail --console=plain
```

Lệnh `fail` có thể khiến một build trước đây thành công chuyển thành thất bại; cần chủ động duy trì plugin/script tương thích và xem cảnh báo cụ thể. Nếu bài test không tạo deprecation/problem nào, `summary` và `all` có thể cho output giống nhau: điều đó bình thường.

**Cảnh báo Gradle và log ở mức WARN là hai khái niệm khác nhau:**

- `--warn` thay đổi **log level** và có thể ẩn thông điệp lifecycle/info.
- `--warning-mode=all` thay đổi **cách trình bày cảnh báo được Gradle quản lý** (nhất là deprecation), không tăng mọi loại log lên DEBUG/INFO.
- `--warning-mode=fail` **không** có nghĩa mọi lời gọi `logger.warn("...")` trong một task sẽ tự gây lỗi build.
- `--warning-mode=none` không vô hiệu hoá báo lỗi build, cũng không bảo đảm ẩn mọi dòng WARN do plugin/application tự ghi.

Trước khi bật `fail` trên CI, dùng `all` để tìm nguồn cảnh báo, sau đó nâng cấp Gradle plugin hoặc sửa DSL theo hướng dẫn chính thức. Dùng `none` để tạm giảm nhiễu có thể che dấu thông tin quan trọng cho đợt nâng cấp tiếp theo.

## 5. Console mode: định dạng và tiến độ

Console mode quyết định cách Gradle sử dụng màu sắc, ký tự điều khiển và progress/status. Nó không phải log level. Cú pháp `--console=<mode>`, với các giá trị được hỗ trợ trong tài liệu hiện hành:

| Mode | Cách hiển thị | Gợi ý |
| --- | --- | --- |
| `auto` — mặc định | Khi có terminal tương tác thường dùng màu/progress; khi không có terminal thường dùng plain. | Mặc định cho developer. |
| `plain` | Chỉ văn bản thuần, bỏ màu/progress động. | CI, file log, copy/search/diff log. |
| `colored` | Có màu nhưng bỏ status/progress phong phú. | Muốn màu mà không muốn thanh tiến độ động. |
| `rich` | Bật màu và rich progress ngay cả khi terminal không tương tác; có thể phát mã ANSI. | Terminal hỗ trợ rich UI. |
| `verbose` | Như rich, đồng thời in tên task và outcome ở log level LIFECYCLE. | Theo dõi task nào chạy, skipped, up-to-date. |

Thử:

```bash
./gradlew help --console=auto
./gradlew help --console=plain
./gradlew help --console=colored
./gradlew help --console=rich
./gradlew help --console=verbose
```

Nếu môi trường thu thập log không hiểu rich console, `rich`/`verbose` có thể để lại ký tự ANSI hoặc progress bị in lặp; `--console=plain` giúp file log ổn định. Khi biến môi trường `NO_COLOR` không rỗng, Gradle tắt màu bất kể console mode, nhưng các tính năng rich khác như progress vẫn có thể tồn tại.

**`--console=verbose` khác `--info`:** verbose làm hiện rõ tên/outcome task ở mức lifecycle; info mở thêm log kỹ thuật từ Gradle/plugin. Khi cần phân tích dependency resolution, cấu hình hoặc task execution, `--info` mới là công cụ chính.

## 6. Kết hợp lệnh cho tình huống thực tế

Các lệnh dùng cú pháp Linux/macOS; trên Windows đổi `./gradlew` thành `.\gradlew.bat`.

| Tình huống | Lệnh đề xuất | Giải thích |
| --- | --- | --- |
| Chạy thông thường | `./gradlew build` | Dùng mặc định lifecycle, warning summary, console auto. |
| CI cần văn bản rõ | `./gradlew build --console=plain` | Tránh ký tự điều khiển và log tiến độ động. |
| Lỗi task khó hiểu | `./gradlew test --stacktrace --console=plain` | Bổ sung stacktrace. |
| Cần xem hoạt động trước lỗi | `./gradlew test --info --stacktrace --console=plain` | Kết hợp log ngữ cảnh và trace. |
| Chuẩn bị nâng cấp | `./gradlew help --warning-mode=all --console=plain` | Liệt kê cảnh báo Gradle để sửa. |
| CI muốn chặn cảnh báo | `./gradlew build --warning-mode=fail --console=plain` | Thất bại khi có cảnh báo thuộc warning mode. |
| Muốn hiện task outcomes | `./gradlew build --console=verbose` | Console rich + chi tiết task ở lifecycle. |
| Debug chuyên sâu tại máy tin cậy | `./gradlew build --debug --stacktrace --console=plain` | Log nhiều; kiểm soát nơi lưu/chia sẻ. |

Đọc lỗi theo thứ tự: xem phần `What went wrong` và task thất bại; thêm `--stacktrace` để thấy trace; thêm `--info` khi cần ngữ cảnh; chỉ dùng `--debug` hoặc `--full-stacktrace` nếu hai bước trước chưa đủ. Riêng cảnh báo nâng cấp, dùng `--warning-mode=all` thay vì chỉ tăng log level.

### 6.1. Ghi log vào file và giữ lỗi trên CI

Trong Bash, redirect stdout/stderr:

```bash
./gradlew test --info --stacktrace --console=plain > gradle-test.log 2>&1
```

File `gradle-test.log` chứa cả stdout/stderr của lệnh, và mã thoát của Gradle vẫn là mã thoát shell command (kiểm tra ngay bằng `echo $? `). Cẩn thận dữ liệu nhạy cảm, nhất là ở mức INFO/DEBUG; tránh commit log ra repository.

Nếu cần vừa xem vừa lưu bằng `tee` trên Bash CI:

```bash
set -o pipefail
./gradlew test --stacktrace --console=plain 2>&1 | tee gradle-test.log
```

`pipefail` giúp pipeline báo lỗi khi Gradle thất bại. Nếu bỏ, shell thường dùng exit code của `tee` nên có thể báo thành công sai. Trên Windows PowerShell dùng cú pháp chuyển hướng phù hợp bản PowerShell đang chạy và kiểm tra exit code của `gradlew.bat`.

## 7. Cấu hình mặc định bằng gradle.properties

Thay vì gõ lặp lại, Gradle hỗ trợ đặt các thuộc tính trong `gradle.properties` của dự án hoặc cấu hình người dùng ở `GRADLE_USER_HOME`. Mẫu **minh hoạ** cho một nhóm muốn log văn bản và xem chi tiết deprecation:

```properties
org.gradle.logging.level=lifecycle
org.gradle.warning.mode=all
org.gradle.console=plain
org.gradle.logging.stacktrace=all
```

Ý nghĩa:

- `org.gradle.logging.level` nhận `quiet`, `warn`, `lifecycle`, `info` hoặc `debug`.
- `org.gradle.warning.mode` nhận `all`, `summary`, `none`, `fail`.
- `org.gradle.console` nhận `auto`, `plain`, `colored`, `rich`, `verbose`.
- `org.gradle.logging.stacktrace=all` yêu cầu stacktrace thông thường; giá trị `full` yêu cầu full stacktrace. **Chữ `all` ở đây khác `--warning-mode=all`**.

Có thể chọn riêng cho một lần chạy bằng CLI:

```bash
./gradlew test -Dorg.gradle.logging.level=info -Dorg.gradle.warning.mode=all --console=plain
```

Cờ CLI giúp điều chỉnh hành vi tại lần chạy đang điều tra. Đừng commit `debug` hoặc `full` stacktrace mặc định cho cả nhóm chỉ vì một lỗi phát sinh; mức log quá nhiều khiến build chậm đọc và làm tăng nguy cơ lộ dữ liệu. Cân nhắc giữ mặc định `lifecycle`/`summary`/`auto` và chỉ bật chi tiết khi cần.

## 8. Lỗi sử dụng thường gặp

| Hiện tượng | Giải thích | Cách sửa |
| --- | --- | --- |
| Dùng `--quiet` nhưng vẫn có một số dòng | QUIET và ERROR vẫn được in; `println` cũng thường được thu ở QUIET | Kiểm tra nguồn log và dùng `logger` ở cấp phù hợp. |
| Dùng `--info` vẫn không có trace mong muốn | Log level và stacktrace độc lập | Thêm `--stacktrace`. |
| Dùng `--debug` nhưng khó tìm lỗi hơn | Nhiều log nội bộ lấn át thông điệp chính | Bắt đầu ở `--stacktrace` + `--info`, chỉ lên DEBUG nếu cần. |
| `--warning-mode=none` vẫn có WARN | Đây không phải bộ lọc mọi logger.warn | Phân biệt Gradle-managed warning và log level WARN. |
| `--warning-mode=fail` không fail khi logger.warn | Log WARN bình thường không nhất thiết là cảnh báo được Gradle warning mode theo dõi | Kiểm tra chính loại cảnh báo đang phát ra. |
| `--console=verbose` không hiện chi tiết download/dependency | Verbose định dạng task output, không tăng INFO | Dùng thêm `--info`. |
| Log CI chứa chuỗi escape ANSI, progress bị lặp | Đã bật rich/verbose trong môi trường thu thập log | Chuyển `--console=plain`. |
| Build bắt đầu fail sau khi bật warning-mode=fail | Gradle tìm thấy deprecation/problem mà trước đó chỉ báo | Dùng `--warning-mode=all`, sửa nguồn cảnh báo thay vì tắt kiểm tra. |
| Đã đặt các thuộc tính trong gradle.properties nhưng output khác kỳ vọng | Có tham số CLI hoặc cấu hình người dùng/môi trường khác tác động | Xem lệnh gọi thực tế, `gradle.properties` và cấu hình CI. |

## 9. Bài tập và tự kiểm tra

**Bài 1 — Mức log.** Thêm `demoLogLevels` ở mục 2.1, chạy ở bốn mức quiet, lifecycle, info, debug. Đối chiếu từng ký hiệu E/Q/W/L/I/D. Vì sao `logger.quiet` vẫn xuất hiện ở chế độ quiet?

**Bài 2 — Stacktrace.** Chạy `failForStacktrace` hai lần, với và không với `--stacktrace`. Cả hai phải thất bại với thông điệp `Demo failure for stacktrace`; lần có stacktrace cho biết điều gì mà báo cáo ngắn thiếu?

**Bài 3 — Warning mode.** Chạy:

```bash
./gradlew help --warning-mode=summary --console=plain
./gradlew help --warning-mode=all --console=plain
```

Nếu không có cảnh báo được Gradle ghi nhận thì hai kết quả có thể tương tự. Khi có deprecation thật, chuyển `all` để tìm đúng file/đoạn cấu hình và tra tài liệu nâng cấp. Không “tạo” cảnh báo giả chỉ để ép hai chế độ khác nhau.

**Bài 4 — Console.** So sánh `auto`, `rich` và `plain` trên terminal. Sau đó ghi output plain vào file. Tại sao rich console thường không phù hợp với log CI và pipeline grep?

**Bài 5 — Kịch bản.** Một CI job thất bại không rõ nguyên nhân và log chứa ký tự điều khiển màu. Lệnh hợp lý trước tiên là `./gradlew test --info --stacktrace --console=plain`. Nếu thấy cảnh báo về deprecation trong quá trình nâng cấp, thêm `--warning-mode=all`. Tránh `--debug` trên môi trường công khai nếu chưa đánh giá rủi ro lộ log.

Tự trả lời nhanh:

1. **`--info` có thay `--stacktrace` không?** Không: một cái đổi log level, một cái in chuỗi ngoại lệ.
2. **`--warn` có giống `--warning-mode=all` không?** Không: một cái lọc cấp log, một cái điều khiển cách Gradle báo cảnh báo.
3. **`--warning-mode=fail` có chặn mọi dòng WARN do ứng dụng in không?** Không; chỉ áp dụng cho cảnh báo mà cơ chế Gradle warning mode xử lý.
4. **`--console=plain` có làm task chạy nhanh hơn hoặc đổi kết quả build không?** Không có bảo đảm như vậy; nó chủ yếu thay đổi hình thức hiển thị.
5. **Khi nào dùng `--full-stacktrace`?** Khi stacktrace mặc định chưa đủ và bạn chấp nhận trace rất dài.

## 10. Tài liệu chính thức

- Gradle Command-Line Interface (logging flags, warning mode, console): https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle Logging and Output (log levels, stacktrace properties, nguy cơ DEBUG): https://docs.gradle.org/current/userguide/logging.html
- Troubleshooting Builds (đọc lỗi, chẩn đoán bằng stacktrace/info): https://docs.gradle.org/current/userguide/troubleshooting.html
- Configuring Build Environment (`gradle.properties`): https://docs.gradle.org/current/userguide/build_environment.html

**Ghi nhớ:** Chọn `--info` để thấy thêm quá trình, `--stacktrace` để thấy đường gọi ngoại lệ, `--warning-mode=all` để tìm cảnh báo tương thích, `--console=plain` để tạo log dễ đọc trong CI.