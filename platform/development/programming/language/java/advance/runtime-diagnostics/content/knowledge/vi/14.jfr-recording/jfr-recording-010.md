# 14.10 Khôi phục các chunk hoàn chỉnh khi cần phân tích sau sự cố

> **Bối cảnh:** Java Flight Recorder (JFR) trên HotSpot/JDK 17+ ghi một recording theo các **chunk**. Khi JVM dừng đột ngột trước lúc xuất được file `.jfr` cuối cùng, đôi khi vẫn còn các chunk hoàn chỉnh trong **disk repository**. Công cụ `jfr assemble` có thể ghép chúng lại để phục vụ điều tra. Đây là **khôi phục phần dữ liệu đã ghi hoàn chỉnh**, không phải phục hồi toàn bộ những gì JVM từng thấy trước khi chết.

## 1. Kết quả học tập và tình huống cần xử lý

Sau bài này, bạn có thể:

1. Giải thích mối quan hệ giữa **JFR memory buffers**, **disk repository**, **chunk hoàn chỉnh (`.jfr`)**, **chunk đang ghi (`.part`)** và file recording xuất ra sau cùng.
2. Xác định khi nào có thể khôi phục bằng `jfr assemble`, khi nào phải dùng `jcmd JFR.dump`, khi nào không còn dữ liệu để khôi phục.
3. Thu thập **bản sao** repository sau sự cố mà không làm thay đổi chứng cứ gốc, chọn đúng thư mục chứa chunk của **một JVM**.
4. Ghép chunk, xác minh recording bằng `jfr summary`, `jfr metadata`, `jfr print`, và giải thích những khoảng dữ liệu bị thiếu.
5. Chủ động cấu hình lưu trữ để tăng khả năng giữ lại dữ liệu khi JVM crash/container bị kill, nhưng không đánh đồng cấu hình này với bảo đảm không mất sự kiện.

**Tình huống ví dụ:** service Java đang ghi JFR để điều tra những lần treo ngắn. Container đột ngột bị `OOMKilled`/JVM gặp lỗi fatal nên không tạo được `incident.jfr` hoàn chỉnh. Disk repository còn một số file chunk. Người vận hành cần tập hợp **những chunk đã hoàn tất**, đọc stack trace và event trước thời điểm lỗi, rồi đối chiếu với log, metrics và `hs_err_pid` nếu có.

Không nên bắt đầu bằng cách sửa đuôi `.part` thành `.jfr`, nối byte thủ công, hoặc chạy lại service để “thử” khi chưa bảo quản được repository cũ: đó là các thao tác dễ đánh mất hoặc làm rối chứng cứ.

## 2. JFR thực sự lưu dữ liệu ở đâu?

### 2.1. Luồng ghi event

Một sơ đồ giản lược:

```text
Java/JVM events
     |
     v
JFR thread-local / global memory buffers
     |
     | ghi/flush vào disk repository khi recording dùng disk=true
     v
Disk repository của JVM
     +-- chunk hoàn chỉnh: ... .jfr
     +-- chunk đang ghi:  ... .part
     |
     | dump/stop/exit bình thường hoặc khôi phục offline
     v
File recording hoàn chỉnh: incident.jfr
     |
     +-- jfr summary / jfr print / jfr metadata
     +-- JDK Mission Control (JMC)
```

Một **JFR chunk** chứa dữ liệu và metadata cần thiết để bộ đọc phân tích chunk đó; đây là đơn vị có thể ghép lại. Trong disk repository, file chunk **đã hoàn chỉnh** mang phần mở rộng `.jfr`; file đang viết thường có phần mở rộng `.part`. Theo mô tả của công cụ JDK, `jfr assemble` **xếp các chunk hoàn chỉnh theo thời gian** và **bỏ qua các `.part` chưa hoàn tất**.

Điều đó tạo ra một ranh giới quan trọng:

- **Có thể khôi phục:** chunk hoàn chỉnh còn tồn tại, còn đọc được, thuộc đúng recording/repository cần điều tra.
- **Không được hứa sẽ khôi phục:** các event còn trong JFR memory buffers chưa flush, chunk `.part` chưa hoàn tất, chunk đã bị retention xóa, dữ liệu trong repository đã bị xóa hoặc mất cùng container/volume.
- **File `.jfr` cuối chưa có không đồng nghĩa toàn bộ dữ liệu đã mất:** repository có thể vẫn còn các chunk dùng được.

JFR được thiết kế có overhead thấp và không bảo đảm mọi event đều được giữ khi hệ thống quá tải, ghi đĩa lỗi hoặc JVM bị kill. Vì thế, “assemble thành công” chỉ xác nhận **file có thể đọc được**, không chứng minh recording chứa mọi thời điểm của sự cố.

### 2.2. `disk=true` khác `disk=false`

Một recording với `disk=true` liên tục chuyển dữ liệu từ buffer tới **disk repository** theo chính sách JFR; đây là điều kiện quan trọng cho khôi phục chunk sau sự cố.

Với `disk=false`, dữ liệu còn chủ yếu trong **memory buffers** của JVM; nếu tiến trình chết trước khi dump thì `jfr assemble` **không có các chunk disk cần thiết để phục hồi**. `dumponexit=true` không thay thế được dữ liệu đã mất do `SIGKILL`, container kill, mất nguồn hoặc JVM crash quá nặng.

| Tình huống | Hướng xử lý phù hợp |
| --- | --- |
| JVM **còn chạy**, cần lấy bản ghi ngay | `jcmd <PID> JFR.dump ...` để xuất snapshot mà không dừng recording (nếu attach được). |
| JVM đã dừng **bình thường**, file `.jfr` hoàn chỉnh tồn tại | Dùng chính file đó; chạy `jfr summary` kiểm tra. Không cần `assemble`. |
| JVM chết đột ngột, còn repository chứa `.jfr` chunks | Sao chép repository và chạy `jfr assemble` **offline** trên bản sao. |
| Chỉ còn `.part`, không có chunk `.jfr` hoàn chỉnh | `assemble` không lấy được chunk chưa hoàn tất; không tự đổi tên hoặc giả định recoverable. |
| Recording chạy `disk=false`, JVM chết, không có dump | Không thể dùng `assemble` để dựng dữ liệu chỉ còn trong RAM đã mất. |
| Repository bị xóa, nằm trên ephemeral volume đã mất, hoặc chunk cũ đã bị loại | Phục hồi phải dựa vào snapshot/backup khác; `jfr assemble` không tạo lại dữ liệu không còn. |

## 3. Chuẩn bị từ trước để tăng cơ hội khôi phục

Đây là các lựa chọn **trước khi có sự cố**. Trong ứng dụng thực tế, chọn đường dẫn nằm trên storage có dung lượng và thời gian lưu phù hợp, đồng thời xem xét quyền truy cập vì JFR có thể chứa stack trace, class/method names, đường dẫn và thông tin runtime nhạy cảm.

### 3.1. Đặt repository ở nơi biết rõ

Ví dụ lệnh khởi động Linux (các thư mục phải tồn tại và tài khoản chạy JVM phải có quyền ghi):

```bash
java \
  -XX:FlightRecorderOptions=repository=/var/lib/myapp/jfr-repository \
  -XX:StartFlightRecording=name=incident,disk=true,settings=default,maxage=30m,maxsize=256m,dumponexit=true,filename=/var/log/myapp/incident.jfr \
  -jar app.jar
```

Giải thích:

- `-XX:FlightRecorderOptions=repository=...` chỉ định **thư mục gốc chứa các chunk tạm của JFR**; JFR có thể tạo các thư mục con cho từng tiến trình hoặc phiên.
- `-XX:StartFlightRecording=...` bắt đầu recording từ lúc JVM khởi động.
- `disk=true` giúp recording dùng disk repository; mặc định thường đã là `true`, nhưng ghi rõ giúp đọc cấu hình và kiểm tra nguyên nhân.
- `settings=default` dùng profile JFR mặc định; có thể thay bằng `.jfc` đã được xác minh nếu cần event chuyên biệt.
- `maxage=30m`/`maxsize=256m` giới hạn dữ liệu được giữ trong repository; chunk quá cũ có thể bị loại. Các con số ở đây **chỉ là ví dụ thiết kế**, phải chọn theo tần suất event, dung lượng đĩa, thời gian điều tra và kích thước chunk.
- `dumponexit=true` yêu cầu dump khi JVM **shutdown theo luồng có xử lý exit**; không thể coi là bảo đảm cho crash/`SIGKILL`.
- `filename=/var/log/myapp/incident.jfr` là đường dẫn **file recording xuất ra**, không phải đường dẫn **repository**. Đây là hai vị trí có nhiệm vụ khác nhau.

Trong Kubernetes/container, `repository` mặc định thường ở vùng tạm của JVM/OS. Nếu pod hoặc filesystem bị xóa khi restart, các chunk có thể mất ngay. Muốn điều tra hậu sự cố, phải lên kế hoạch volume và quy trình trích xuất phù hợp; đừng mặc định `/tmp` tồn tại sau pod recreation.

### 3.2. Kiểm tra trước khi sự cố xảy ra

Khi JVM còn sống, có thể dùng:

```bash
jcmd -l
jcmd 12345 JFR.check name=incident verbose=true
jcmd 12345 JFR.configure
```

`12345` là **PID minh họa**: thay bằng PID thật lấy từ `jcmd -l` hoặc công cụ OS. Các lệnh `jcmd` cần attach được vào JVM cùng máy/container với quyền thích hợp; môi trường bảo mật hoặc namespace khác có thể chặn attach.

Ở JDK có hỗ trợ, lệnh:

```bash
jcmd 12345 JFR.configure preserve-repository=true
```

yêu cầu JFR giữ lại các file trong disk repository khi JVM kết thúc **bình thường** thay vì dọn chúng theo mặc định. **Phải cấu hình trong lúc process còn sống**; không thể gọi `JFR.configure` sau khi process đã chết. Cơ chế preserve không bù lại việc storage bị xóa/ghi đè hoặc chunk chưa hoàn chỉnh, và không biến `.part` thành chunk hợp lệ.

Lưu ý hai tên setting dễ nhầm:

- `repository=` trong `-XX:FlightRecorderOptions` là **cờ JVM lúc khởi động**.
- `repositorypath=` trong `jcmd ... JFR.configure` là **tham số diagnostic command khi JVM còn sống**. Dùng `jcmd ... JFR.configure` để kiểm tra khả năng hỗ trợ và trạng thái thực trên JDK đang chạy.

Thư mục repository phục vụ làm việc của recorder; **không nên biến nó thành kho backup dài hạn**. Chính sách bảo quản sự cố nên sao chép bản gốc vào nơi riêng, kiểm soát quyền và vòng đời file.

## 4. Quy trình khôi phục hậu sự cố: từ repository tới `.jfr`

Đây là runbook chính. Các lệnh dưới đây giả định Linux/macOS với shell tương thích Bash. Đường dẫn chỉ minh họa; phải thay theo cấu hình triển khai và đúng **thư mục trực tiếp chứa chunk** của JVM gặp sự cố.

### Bước 1 — Giữ trạng thái chứng cứ và xác nhận JVM đã dừng

Thu thập PID trước khi chết, thời điểm sự cố (có múi giờ), version của JDK, logs, container ID/pod ID, vị trí mount và lựa chọn `disk`/`repository`. Nếu process thực sự **còn chạy**, ưu tiên:

```bash
jcmd 12345 JFR.dump name=incident filename=/var/log/myapp/live-snapshot.jfr
```

Đây là lựa chọn an toàn hơn việc chụp thư mục mà recorder đang thay đổi. `JFR.dump` xuất file từ recording đang chạy và không dừng recording. Nếu process đã chết, không thể dùng `jcmd` để lấy sự kiện từ nó.

### Bước 2 — Xác định đúng repository của một JVM

Ví dụ repo gốc được cấu hình ở `/var/lib/myapp/jfr-repository`:

```bash
find /var/lib/myapp/jfr-repository -type f \
  \( -name '*.jfr' -o -name '*.part' \) -print
```

Chọn **thư mục con chứa các chunk của tiến trình/phiên ghi cần khôi phục**. Một service có nhiều process, nhiều đợt restart hoặc nhiều phiên recording có thể để lại các nhóm file khác nhau; **không trộn chunk từ các process khác nhau** chỉ vì chúng có cùng phần mở rộng.

Nếu trên hiện trường file `.jfr` chunk nằm trực tiếp trong thư mục repo gốc thì có thể dùng chính thư mục đó. Nếu chúng nằm trong một thư mục con, phải dùng **đúng thư mục con** làm input cho `assemble`. Khi chỉ nhìn thấy `.part`, hãy ghi nhận rõ không có `.jfr` hoàn chỉnh, tránh suy diễn.

### Bước 3 — Sao chép để bảo toàn bản gốc

Ví dụ sau giả định `/var/lib/myapp/jfr-repository/recording-001` là **thư mục vừa xác minh có các chunk `.jfr`**, và `/srv/incidents/incident-001` là nơi lưu kết quả **nằm ngoài repository nguồn**:

```bash
SOURCE_DIR=/var/lib/myapp/jfr-repository/recording-001
CASE_DIR=/srv/incidents/incident-001

mkdir -p "$CASE_DIR"
cp -a "$SOURCE_DIR" "$CASE_DIR/repository-copy"

find "$CASE_DIR/repository-copy" -maxdepth 1 -type f \
  \( -name '*.jfr' -o -name '*.part' \) -print
```

`cp -a` giữ bản sao file cùng nhiều metadata hệ thống trên Linux; quyền và filesystem đích có thể ảnh hưởng mức độ bảo toàn metadata. Hãy ghi nhận thời điểm sao chép, nguồn, PID, JDK version và chính sách lưu trữ để người khác tái dựng cuộc điều tra.

Nên lưu checksum riêng cho **bản sao**, ví dụ:

```bash
find "$CASE_DIR/repository-copy" -maxdepth 1 -type f -name '*.jfr' \
  -exec sha256sum {} \;
```

Hash giúp chứng minh các bản sao được giữ nguyên giữa các lần phân tích. Không cần sửa file chunk, loại `.part` hay đổi tên thủ công trong bản gốc. Nơi chứa output phải **khác** thư mục input để tránh vô tình đưa kết quả assemble vào cùng nguồn.

### Bước 4 — Ghép các chunk hoàn chỉnh

Dùng đúng cú pháp command của JDK:

```bash
jfr assemble "$CASE_DIR/repository-copy" "$CASE_DIR/recovered.jfr"
```

Hai đối số lần lượt là **thư mục chứa chunk** và **đường dẫn file recording mới**. `jfr assemble` chọn các chunk hoàn chỉnh, xếp theo thứ tự thời gian và ghi ra file `.jfr`. Theo đặc tả của công cụ JDK, các file `.part` đang dở sẽ bị **loại**.

**Không** thực hiện các thao tác sau để “cứu” dữ liệu:

- Đổi đuôi `.part` thành `.jfr` và coi nó là chunk hoàn chỉnh.
- Nối file theo thứ tự tên bằng `cat`/`copy /b` khi chưa xác nhận đó là các JFR chunks thuộc cùng repository.
- Dùng `jfr assemble` trên thư mục gốc vô tình chứa nhiều repository từ nhiều process/restart.
- Chạy lại ghi JFR vào đúng repo chưa sao chép, khiến housekeeping hoặc retention có thể xóa chunk cần thiết.
- Xóa file chunk vì tưởng là “file tạm” trước khi lưu bản sao.

Nếu công cụ báo không có chunk, không truy cập được đường dẫn, hoặc một chunk bị hỏng, **giữ nguyên bản sao chứng cứ** và kiểm tra điều kiện đầu vào. Không tự tuyên bố đã recover khi câu lệnh thất bại.

### Bước 5 — Xác minh file khôi phục

```bash
jfr summary "$CASE_DIR/recovered.jfr"
jfr metadata "$CASE_DIR/recovered.jfr"
jfr print --events jdk.GarbageCollection,jdk.ExecutionSample \
  "$CASE_DIR/recovered.jfr"
```

- `jfr summary`: cần đọc được file, cho biết **version/chunk count/khoảng thời gian recording** cùng số sự kiện theo event type. Những con số này giúp nhận ra file rỗng, sai process hoặc khác cửa sổ sự cố.
- `jfr metadata`: xác nhận cấu trúc event schema có thể đọc được, nhất là khi JVM thu thập và công cụ phân tích khác phiên bản.
- `jfr print --events`: lọc event theo chủ đề đang điều tra. Các loại `jdk.GarbageCollection`, `jdk.ExecutionSample` có thể không xuất hiện nếu chúng không được bật/thu trong cửa sổ tương ứng; output trống **không có nghĩa lệnh assemble thất bại**.
- Có thể mở `recovered.jfr` trong **JDK Mission Control (JMC)** để quan sát timeline, stack traces, các sự kiện GC, locks, CPU, threads và biểu đồ tương quan.

**Kiểm tra dữ liệu theo thời gian:** ghi lại start/end time của recording khôi phục, khoảng thời gian sự cố từ logs, số chunk, các khoảng trống đáng ngờ và event cần điều tra. Nếu mất chunk cuối hoặc event vẫn ở buffer, những giây sát crash có thể **không còn**. Một file khôi phục hoàn chỉnh về mặt format vẫn có thể **không bao phủ nguyên nhân cuối cùng** của sự cố.

## 5. Vì sao không thể “khôi phục tất cả”?

### 5.1. Ba mức độ mất dữ liệu

1. **Chưa flush khỏi buffers:** dữ liệu vẫn trong RAM khi JVM chết; JFR offline không có nguyên liệu để khôi phục.
2. **Đang ghi chunk `.part`:** file chưa hoàn tất nên `jfr assemble` bỏ qua. Không dựa vào việc đổi extension hoặc sửa vài bytes để tuyên bố đã recover một chunk hợp lệ.
3. **Chunk đã hoàn tất nhưng không còn trên disk:** có thể bị xóa do `maxage`/`maxsize`, shutdown cleanup, filesystem tạm, disk failure hoặc thao tác vận hành. `jfr assemble` không khôi phục được file vật lý đã mất.

Ngoài ra, event có thể **không được bật**, chịu threshold/sample rate hoặc bị drop dưới áp lực cao ngay từ đầu. Không thể lấy lại một event **chưa bao giờ được lưu** dù có đầy đủ mọi chunk.

### 5.2. Hiểu đúng `maxage`, `maxsize` và chunk rollover

`maxage`/`maxsize` là chính sách **retention của recording trên disk**. Khi đạt ngưỡng, JVM có thể xóa các chunk cũ để dành chỗ; vì vậy repo còn lại chỉ có thể phản ánh **cửa sổ gần nhất**, không phải toàn bộ uptime.

`-XX:FlightRecorderOptions=maxchunksize=...` điều chỉnh kích thước tối đa/định hướng chunk theo HotSpot, **không** có nghĩa một chunk bắt buộc đúng số bytes đó, hay mỗi `maxage` phút sẽ sinh một chunk. `maxsize` của recording phải tương thích với giới hạn chunk; chọn ngưỡng đủ lớn để giữ lại chu kỳ quan sát có ý nghĩa.

Nếu cần recovery gần thời điểm sự cố, hãy cân nhắc **disk persistence** và chính sách retention từ trước. Cấu hình này chỉ làm tăng cơ hội, vẫn có thể mất phần dữ liệu cuối.

## 6. Lab Java 17+: dựng lại recording từ các chunk hoàn chỉnh

Lab dùng **recording hợp lệ**, chủ động tách thành nhiều chunk bằng `jfr disassemble`, rồi ghép lại bằng `jfr assemble`. Đây là phép kiểm tra cú pháp, định dạng và quy trình ghép; nó **không mô phỏng đầy đủ** sự cố `SIGKILL` hoặc việc mất `.part`.

### 6.1. Chương trình tạo nhiều JFR events

Tạo file `JfrChunkLab.java`:

```java
import jdk.jfr.Enabled;
import jdk.jfr.Event;
import jdk.jfr.Name;

public class JfrChunkLab {
    @Name("lab.Checkpoint")
    @Enabled(true)
    public static class Checkpoint extends Event {
        int sequence;
        String phase;
    }

    public static void main(String[] args) {
        int markers = 350_000;

        for (int i = 0; i < markers; i++) {
            Checkpoint event = new Checkpoint();
            event.sequence = i;
            event.phase = "diagnostic";
            event.commit();
        }

        System.out.println("markers=" + markers);
    }
}
```

Đây là Java 17+ hoàn chỉnh, không dùng API nội bộ. `Checkpoint` là custom JFR event; `@Name("lab.Checkpoint")` tạo event type dễ nhận trong `jfr summary`. `@Enabled(true)` bật event type mặc định cho recording; JFR phải đang chạy trước khi vòng lặp phát event. Không áp dụng số lượng sự kiện này trong production vì 350.000 events có thể gây overhead đáng kể; đây chỉ là lab ngắn.

### 6.2. Biên dịch và thu file `.jfr`

```bash
javac JfrChunkLab.java
java \
  -XX:FlightRecorderOptions=maxchunksize=1m \
  -XX:StartFlightRecording=filename=lab.jfr,dumponexit=true,settings=default \
  JfrChunkLab
```

**Stdout từ chương trình Java**:

```text
markers=350000
```

Ngoài dòng trên, JVM có thể in thêm thông báo `[jfr,startup]` về recording. `maxchunksize=1m` được đặt nhỏ cho lab nhằm dễ tạo nhiều chunk; JFR vẫn có quyền ghi kích thước chunk thực lớn hơn mốc cấu hình tùy hoàn cảnh runtime. Số chunk không cố định giữa các bản JDK hoặc máy.

### 6.3. Tách rồi ghép lại

Trên Linux/macOS:

```bash
mkdir -p chunks
jfr summary lab.jfr
jfr disassemble --max-chunks 1 --output chunks lab.jfr
jfr assemble chunks recovered-lab.jfr
jfr summary recovered-lab.jfr
```

Trên Windows PowerShell, thay lệnh `mkdir` bằng:

```powershell
New-Item -ItemType Directory -Path .\chunks -Force
jfr disassemble --max-chunks 1 --output .\chunks .\lab.jfr
jfr assemble .\chunks .\recovered-lab.jfr
jfr summary .\recovered-lab.jfr
```

`jfr disassemble` tạo các file nhỏ hơn có thứ tự; với `--max-chunks 1`, mỗi file output chứa tối đa một chunk. Nếu recording **chỉ có một chunk**, công cụ có thể báo **không cần disassemble**; hãy tạo recording lớn hơn hoặc nhiều events hơn rồi thử lại. Không dùng cảnh báo đó để kết luận file bị hỏng.

**Kết quả thực nghiệm đã kiểm tra trên OpenJDK 24:** với 350.000 custom events và cấu hình trên, recording tạo ra **3 chunks**; `jfr disassemble` tạo 3 file, `jfr assemble` tạo file có **350.000 `lab.Checkpoint`**, và SHA-256 của recording ghép trùng file trước khi tách. Đó là một kết quả tham khảo của lần chạy này, **không phải cam kết** số chunk cố định trên JDK 17/21 hoặc các môi trường khác.

Dùng:

```bash
jfr summary recovered-lab.jfr
```

để tìm event type `lab.Checkpoint`, xem số events và chunk count. Nếu event count khác kỳ vọng, trước hết kiểm tra recording có khởi động trước khi vòng lặp chạy, event có được bật, sampling/retention và thông báo JFR. **Một event được `commit()` trong code cũng không đồng nghĩa mọi event chắc chắn vào file khi hệ thống có áp lực hoặc mất dữ liệu**.

### 6.4. Lab liên quan gì đến cứu dữ liệu sau crash?

Trong lab, `jfr disassemble` cố ý tạo những file `.jfr` hoàn chỉnh từ một recording hợp lệ. Sau crash thật, các chunk `.jfr` còn sót lại trong disk repository đóng vai trò **đầu vào** cho cùng công cụ `jfr assemble`; không cần trước đó đã chạy `disassemble`.

Đừng đảo ngược quy trình thành “phải có file recording nguyên vẹn rồi mới recover”: `disassemble` chỉ dùng để học/kiểm tra hoặc tách **một recording đã đọc được**. Sau crash, nếu file đích chưa từng được dump, nguồn khôi phục có thể chính là **repository còn các chunk hoàn chỉnh**.

## 7. Khi file `.jfr` đã tồn tại nhưng có dấu hiệu hỏng

Trước tiên **sao chép file lỗi** và giữ bản gốc. Sau đó chạy:

```bash
jfr summary suspicious.jfr
jfr metadata suspicious.jfr
```

Nếu hai lệnh đọc thành công, file có thể vẫn chứa các chunk hợp lệ; hãy tiếp tục điều tra theo thời gian và event types. Nếu file lớn và **đọc được**, `jfr disassemble --max-chunks 1` có thể tách từng chunk để định vị phần dữ liệu phục vụ phân tích. Nếu chỉ một đoạn chunk hỏng, có thể thử ghép **các chunk được xác nhận hợp lệ** trong một thư mục mới; luôn ghi rõ phạm vi thời gian đã bỏ mất.

Ngược lại, nếu `jfr disassemble` cũng báo lỗi parse, **không có bảo đảm** công cụ JDK sẽ tự cứu một file nhị phân bị cắt byte ở giữa hoặc bị corrupt. Có thể cần snapshot/backup khác hoặc công cụ forensics chuyên sâu, nhưng không nên hứa có thể biến mọi `.part`/file hỏng thành recording đầy đủ.

## 8. Chẩn đoán lỗi trong quá trình khôi phục

| Hiện tượng | Cách hiểu | Hành động |
| --- | --- | --- |
| `jfr assemble` không tìm thấy chunk | Sai directory, repo đã bị dọn, chỉ còn `.part`, hoặc không có disk recording | Xác nhận `disk=true` trước sự cố, kiểm tra cây thư mục/volume/backup, chọn đúng leaf directory. |
| Có nhiều thư mục PID/recording | Nhiều JVM hoặc phiên ghi chia sẻ cùng repo gốc | Xác định PID, thời điểm, nhóm file; xử lý **riêng từng repository**. |
| Có nhiều `.part` nhưng không có `.jfr` | Không còn chunk hoàn chỉnh để ghép | Bảo quản file hiện có; đừng đổi đuôi hoặc công bố “khôi phục thành công”. |
| `jfr summary recovered.jfr` không đọc được | Output thiếu/hỏng, input không đúng loại, hoặc vấn đề tương thích công cụ | Đọc lỗi thực, kiểm tra danh sách input, thử JDK tool version phù hợp với JVM tạo recording. |
| File đọc được nhưng không thấy event cần tìm | Event không được bật, threshold/sample, khoảng recording không khớp, chunk đã mất | So sánh `.jfc`, logs, `jfr summary`, timestamps; không quy mọi thiếu hụt cho `assemble`. |
| Không có dữ liệu ngay trước crash | Buffers chưa flush, `.part` bị bỏ qua, retention/gap | Ghi rõ khoảng dữ liệu chưa bao phủ; đối chiếu `hs_err_pid`, GC logs, application logs và OS metrics. |
| `jcmd JFR.dump` báo attach denied | Quyền, process namespace hoặc chính sách môi trường | Dùng quyền/context thích hợp **khi JVM còn sống**; không dùng `jcmd` sau khi PID chết. |
| Pod restart khiến `/tmp` cũ biến mất | Storage ephemeral/lifecycle cleanup | Tìm volume/snapshot/backup; thiết kế đường lưu bền và trích xuất chứng cứ cho lần sau. |
| Tên file có thứ tự khác timestamp | Rename, copy, đồng hồ, hoặc tên do công cụ tạo | Để `jfr assemble` sắp chunk theo metadata; không tự nối theo tên file nếu chưa kiểm chứng. |
| File recovered có duration ít hơn uptime | Recording chỉ chạy trong một cửa sổ, `maxage`/`maxsize` loại cũ hoặc thiếu chunks | Báo đúng cửa sổ có bằng chứng thay vì gọi đó là toàn bộ lịch sử JVM. |

### Không nhầm các công cụ

| Lệnh | Đầu vào/đầu ra | Dùng khi |
| --- | --- | --- |
| `jcmd PID JFR.dump ...` | JVM **đang sống** → `.jfr` snapshot | Lấy dữ liệu trước khi stop/restart, không phải công cụ offline. |
| `jcmd PID JFR.stop ...` | JVM **đang sống** → dừng recording và có thể ghi `.jfr` | Kết thúc một recording còn đang chạy. |
| `jfr assemble REPO OUT.jfr` | Directory chứa **complete chunks** → recording `.jfr` | Khôi phục offline khi chỉ còn chunk sau sự cố. |
| `jfr disassemble FILE.jfr` | Recording **đọc được** → các file chunk/segment | Lab, chia file lớn, xác định các phần hợp lệ. |
| `jfr summary FILE.jfr` | Recording `.jfr` → số chunk, event counts, metadata tổng quan | Xác thực và đánh giá kết quả. |
| `jfr print --events ... FILE.jfr` | Recording `.jfr` → event detail dạng text | Tra stack/timestamp/field sau khi xác thực file. |
| JMC | Recording `.jfr` → timeline, chart, tương quan | Điều tra sự cố dựa trên những event còn lại. |

## 9. Quy tắc bảo toàn, tính đầy đủ và tính riêng tư

**Bảo toàn chứng cứ:** đánh dấu đường dẫn gốc, PID/host/container ID, thời điểm lấy dữ liệu và JDK build; tạo bản sao riêng trước khi thao tác. Với nhiều file, checksum từng file `.jfr` giúp kiểm tra chúng có thay đổi giữa các bước. Giữ cả `.part` trong bản lưu gốc dù `assemble` không dùng được, vì đây vẫn là chứng cứ về trạng thái ghi dở lúc sự cố.

**Không đánh đồng “file parse được” với “sự cố đã được ghi đủ”:** `jfr summary` xác nhận cấu trúc và loại event; điều tra vẫn cần khoảng thời gian, event setting, buffer/retention behavior và dữ liệu bên ngoài JVM. Ví dụ nếu GC logs/OS report OOM lúc 10:00:05 nhưng recording cuối lúc 10:00:01, kết luận đúng là **JFR khôi phục tới 10:00:01**, không được nói không có GC/OOM sau đó.

**Đọc timestamps đúng múi giờ:** JFR tool có thể hiển thị UTC hoặc thời gian local tùy command/version. Khi đối chiếu ứng dụng, container, tracing, log OS, hãy chuyển về một chuẩn thời gian và ghi rõ đơn vị (ms/ns) để tránh suy luận sai quan hệ nhân quả.

**Kiểm soát truy cập:** JFR có thể chứa tên thread, class, method, frame, đường dẫn, thông tin system/environment và payload của custom events; không upload lên dịch vụ công khai hoặc đưa vào ticket không có kiểm soát nếu chưa kiểm tra chính sách dữ liệu. File recovered cần được bảo vệ như một artifact chẩn đoán hệ thống.

**Tính đúng môi trường:** chạy `jfr` từ JDK tương thích với phiên bản đã ghi; dùng `jfr metadata` để xác nhận schema thật. Nếu tool quá cũ không đọc được recording mới, hãy thử bản JDK phù hợp thay vì sửa bytes.

## 10. Checklist thao tác thực tế

- [ ] Xác định **JVM đã chết hay còn chạy**; nếu còn sống, ưu tiên `jcmd JFR.dump` với quyền thích hợp.
- [ ] Tìm đúng **disk repository** và nhóm chunk của **một JVM/phiên**; xác nhận có ít nhất một chunk `.jfr` hoàn chỉnh.
- [ ] Bảo quản bản gốc, sao chép toàn bộ thư mục relevant gồm cả `.part`, ghi nhận metadata và checksum.
- [ ] Đặt **output ngoài repository input**, chạy `jfr assemble` trên bản sao.
- [ ] Chạy `jfr summary` và `jfr metadata` để xác nhận file parse được, xem số chunk, start/end time, event counts.
- [ ] Mở trong JMC hoặc dùng `jfr print` để phân tích; so timeline với logs, GC, container/OS metrics và các bằng chứng crash.
- [ ] Báo rõ **dữ liệu còn, dữ liệu thiếu và điều gì không thể suy ra** (buffers, `.part`, retention, event settings).
- [ ] Với lần sau, kiểm tra `disk=true`, repository path, khả năng lưu bền của volume, quyền, retention và quy trình snapshot trước restart.

**Kết luận:** sau sự cố, `jfr assemble` là công cụ dành cho **những JFR chunks đã hoàn tất và còn trên đĩa**. Nó có thể cứu phần lịch sử hữu ích dù file recording cuối cùng chưa được dump, nhưng không thể tái tạo event đã mất trong RAM, chunk `.part` chưa hoàn tất, hoặc chunk đã bị xóa. Khôi phục thành công phải đi cùng **xác minh nội dung và công bố giới hạn thời gian**.

## Tài liệu tham khảo

- [Oracle JDK 21 — `jfr` command: `assemble`, `disassemble`, `summary`, `metadata`, `print`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 21 — `jcmd`: JFR.configure, JFR.start, JFR.check, JFR.dump](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 21 — Java launcher: `-XX:StartFlightRecording`, `-XX:FlightRecorderOptions`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Dev.java — Configuring the JDK Flight Recorder, disk/repository/chunks](https://dev.java/learn/jvm/jfr/configure/)
- [Dev.java — The JFR command-line tool](https://dev.java/learn/jvm/jfr/tools/)
- [JDK 24 API — `jdk.jfr.Recording`, `setToDisk`, `dump`, `setMaxAge`, `setMaxSize`](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/Recording.html)
