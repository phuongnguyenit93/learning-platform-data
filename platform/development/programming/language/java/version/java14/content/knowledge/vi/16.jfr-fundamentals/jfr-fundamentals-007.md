# Chi phí thu thập và dữ liệu có thể chứa thông tin nhạy cảm trong Java Flight Recorder (JFR)

## 1. Mục tiêu: quan sát ứng dụng mà không tạo thêm rủi ro không cần thiết

**Java Flight Recorder (JFR)** là cơ chế ghi nhận sự kiện chẩn đoán của JVM/JDK và ứng dụng Java: hoạt động GC, CPU, thread, allocation, I/O, độ trễ, stack traces và các sự kiện do chính ứng dụng định nghĩa. Bản ghi thường được kết xuất thành tệp **`.jfr`** để phân tích bằng `jfr`, Java Mission Control (JMC), hoặc API `jdk.jfr.consumer`.

JFR được thiết kế để **có thể quan sát hệ thống với chi phí tương đối thấp**, đặc biệt khi dùng cấu hình `default`. Tuy nhiên, JFR **không hoàn toàn miễn phí** và **không mặc nhiên an toàn để chia sẻ**. Có hai câu hỏi độc lập cần trả lời trước khi bật hoặc xuất một recording:

1. **Chi phí vận hành:** việc ghi thêm sự kiện tiêu thụ bao nhiêu CPU, bộ nhớ đệm, băng thông đĩa, dung lượng lưu trữ, thời gian xử lý và có thể tác động tới độ trễ/tạm dừng của ứng dụng ra sao?
2. **An toàn thông tin:** sự kiện nào được thu thập, trong chúng có tên class/method, đường dẫn tệp, địa chỉ mạng, arguments, system properties, tên thread, hoặc dữ liệu nhạy cảm do custom events ghi vào không? Ai có quyền đọc, trích xuất, tải lên, chuyển tiếp và giữ những bản ghi đó?

**Không nên mặc định “low overhead” = không cần đo, hoặc “file hỗ trợ debug” = không chứa dữ liệu nội bộ.** Đúng hơn, hãy chọn sự kiện tối thiểu, giới hạn thời gian/dung lượng, kiểm tra quyền truy cập và đo trên workload thực.

JFR và API `jdk.jfr` đã được tích hợp trong JDK hiện đại; bài sử dụng các khả năng **Java 17+** vẫn áp dụng trên Java 21/25 và các bản hiện hành, không dựa trên yêu cầu giấy phép hay cú pháp JFR cũ của những JDK đời trước.

## 2. “Chi phí thu thập” của JFR gồm những gì?

Cơ chế JFR ghi **event**: dữ liệu có thời điểm, loại sự kiện và các trường tương ứng. Khi một event được bật, JVM hoặc code ứng dụng có thể phải thực hiện thêm thao tác để tạo/ghi nó. Các nguồn chi phí thường gặp:

| Loại chi phí | Tại sao phát sinh | Dấu hiệu nên theo dõi |
| --- | --- | --- |
| **CPU** | Kiểm tra event enabled/threshold, lấy timestamp, ghi dữ liệu, xử lý sampling hoặc stack trace | CPU process, throughput, p95/p99 latency |
| **Bộ nhớ đệm** | Buffer theo thread và buffer tổng phục vụ ghi sự kiện | Mức sử dụng bộ nhớ và áp lực tài nguyên tổng |
| **I/O đĩa** | Flush chunk và tạo/dump recording | Lưu lượng ghi đĩa, mức chiếm dụng ổ |
| **Dung lượng** | Event volume tăng khi nhiều sự kiện hoặc recording chạy lâu | Kích thước `.jfr`, bytes/phút, số sự kiện |
| **Độ trễ/tạm dừng** | Một số hoạt động đo chuyên sâu có thể yêu cầu thêm công việc trên JVM; thu thập đường tới GC roots có thể gây pause | Tail latency, GC pause, thời gian dump |
| **Chi phí xử lý sau thu thập** | Parse, export JSON, chuyển file, tạo báo cáo, lưu nhiều bản sao | CPU của công cụ phân tích, storage, network |

**Tổng chi phí phụ thuộc workload và cấu hình**: loại event, tần suất, threshold, có stack trace hay không, số thread, số recording đồng thời, thời lượng, lưu ra disk hay memory, tốc độ I/O và cả giới hạn của hệ điều hành/container.

Không nên khẳng định bất kỳ ứng dụng nào dùng JFR cũng chỉ mất “đúng 1% CPU” hay “không ảnh hưởng p99”. Các con số tỷ lệ chỉ có ý nghĩa nếu được đo với **cấu hình, workload và môi trường cụ thể**.

### Chi phí thấp không đồng nghĩa mọi event thấp

Một event rất hiếm, chẳng hạn thông tin về một lần GC, có thể rẻ hơn nhiều so với custom event do ứng dụng commit **trên mỗi request** với hàng loạt trường chuỗi. Việc yêu cầu stack trace cho từng event tần suất cao, tăng độ sâu stack, lấy nhiều thống kê heap hoặc kích hoạt đường tới GC roots có thể làm thay đổi tác động.

JFR còn có chi phí **ngay trong code tạo dữ liệu**: nếu lập trình viên tính toán payload nặng hoặc nối chuỗi có nội dung nhạy cảm trước khi biết event có được ghi hay không, bản thân công việc đó vẫn tiêu tốn CPU và cấp phát bộ nhớ. Không phải tất cả chi phí đều nằm trong thư viện JFR.

## 3. Cấu hình `default` và `profile`: khác biệt về mức thu thập

JDK cung cấp hai cấu hình sự kiện phổ biến tại `JAVA_HOME/lib/jfr`:

| Cấu hình | Mục đích | Chi phí và lựa chọn |
| --- | --- | --- |
| `default.jfc` (`settings=default`) | Thu thập các sự kiện chẩn đoán cơ bản với overhead thấp | Điểm xuất phát hợp lý cho recording kéo dài/quan sát production |
| `profile.jfc` (`settings=profile`) | Thu thập thêm dữ liệu phục vụ profiling trong thời gian xác định | Có thể tạo nhiều event và overhead lớn hơn; dùng ngắn hạn khi cần |
| `custom.jfc` | Chỉ định loại event, threshold, stack trace, period phù hợp câu hỏi đang điều tra | Tốt khi hiểu nhu cầu và đã kiểm thử cấu hình; không mặc nhiên rẻ hơn `default` |

Các cấu hình là **bộ event settings**, không phải cam kết “chi phí = một con số cố định”. File `.jfc` có thể điều chỉnh:

- **`enabled`**: một event type có được thu thập không.
- **`threshold`**: với duration event, chỉ ghi các lần đủ dài theo ngưỡng.
- **`period`**: khoảng cách phát sinh periodic event (nếu event hỗ trợ).
- **`stackTrace`**: có ghi stack trace cho event đó không.
- **`cutoff`, `throttle` và các setting riêng**: chỉ khả dụng ở loại event/JDK hỗ trợ; cần kiểm tra metadata thực tế.

Không nên giả định **tất cả event** đều hỗ trợ cùng một danh sách settings hoặc hiệu ứng giống nhau. Dùng `jfr metadata`, tài liệu của event và cấu hình thực tế để quyết định.

**Quy tắc thực hành:** điều tra latency/GC tổng quát có thể bắt đầu từ `default`; chỉ chuyển sang `profile` hoặc bật event nặng khi dữ liệu hiện có chưa đủ để trả lời câu hỏi. Tránh để một cấu hình có độ chi tiết cao chạy vô hạn chỉ vì đang debug.

## 4. Giảm overhead ngay từ cách chọn sự kiện

### 4.1. Bật ít sự kiện hơn

Mỗi event type tạo một góc nhìn khác nhau. Nếu chỉ cần biết GC pause và CPU tổng, không có lý do mặc định bật custom events ghi từng giao dịch, tham số truy vấn hoặc request body.

Hãy liệt kê **câu hỏi chẩn đoán cụ thể** rồi chọn các nhóm sự kiện cần thiết, thay vì bật mọi thứ và lọc sau. Lọc **lúc phân tích** chỉ giảm dữ liệu hiển thị, không hoàn tác chi phí đã ghi và không xóa dữ liệu khỏi file gốc.

### 4.2. Dùng threshold cho sự kiện theo thời lượng

Ví dụ muốn quan sát các thao tác I/O chậm, threshold hợp lý có thể giảm lượng sự kiện so với ghi mọi thao tác ngắn. Nhưng threshold cao hơn cũng có nghĩa **bỏ qua thao tác dưới ngưỡng**; cần cân bằng giữa độ bao phủ và chi phí.

Nếu sự kiện xảy ra hàng triệu lần/giây, việc tăng threshold cho duration events hoặc chỉ đo sự kiện thực sự quan trọng giúp giảm dung lượng và noise. Đừng áp threshold cho instant/periodic event mà không xác minh event hỗ trợ.

### 4.3. Sampling và period

Một số event lấy mẫu hoặc chạy theo chu kỳ. Tần suất cao cung cấp tín hiệu chi tiết hơn nhưng có thể tăng overhead và kích thước recording. Tần suất thấp giảm chi phí nhưng có thể bỏ sót spike ngắn.

Không hiểu sampling như cách ghi **chính xác mọi lần gọi hàm**: nó là dữ liệu lấy mẫu; phân tích phải diễn giải theo xác suất/tần suất lấy mẫu.

### 4.4. Stack traces

Stack trace cung cấp ngữ cảnh class/method và đường gọi, rất hữu ích để tìm điểm nghẽn, nhưng có thể làm tăng chi phí và bộc lộ cấu trúc nội bộ.

Với custom event chỉ cần đếm số request theo nhóm, thường **không cần stack trace**. Có thể vô hiệu hóa ở event settings hoặc dùng `@StackTrace(false)` làm default ở khai báo event. Không nên ghi stack trace chỉ để “có thêm dữ liệu” nếu nó không phục vụ câu hỏi chẩn đoán.

### 4.5. Chặn chi phí dựng payload

Custom events nên tránh thu thập dữ liệu nặng trước khi kiểm tra có cần commit. Một mẫu thực hành:

~~~java
MyEvent event = new MyEvent();

if (event.shouldCommit()) {
    event.count = count;
    event.commit();
}
~~~

Đoạn trên là **mảnh minh họa**, giả định `MyEvent extends jdk.jfr.Event` và có field `count`. Nó chỉ có lợi khi dữ liệu đắt được tính **bên trong** nhánh `shouldCommit()`; tính chuỗi nhạy cảm hoặc cấp phát lớn **trước** nhánh vẫn tốn công và có nguy cơ làm lộ dữ liệu.

Với duration event, thứ tự thông thường là `begin()` → công việc → `end()` → `shouldCommit()` → `commit()`. Nếu cần thời gian thực thi thật, không thay bằng một instant event có `count` rồi suy đoán đó là duration.

## 5. Giới hạn thời lượng, bộ nhớ đệm và dung lượng đĩa

JFR có các tùy chọn điều khiển **vòng đời recording**. Chúng giúp giảm rủi ro tài nguyên và thu hẹp phạm vi dữ liệu bị lưu quá lâu.

### 5.1. Bắt đầu recording ngắn với `jcmd`

Trên HotSpot JDK có công cụ `jcmd`, sau khi xác định đúng PID của ứng dụng, ví dụ:

~~~bash
jcmd -l
jcmd 12345 JFR.start name=triage settings=default duration=60s filename=/secure/jfr/triage.jfr
~~~

Trong đó `12345` là **PID minh họa**, phải thay bằng PID thật. Đường dẫn `/secure/jfr/triage.jfr` là ví dụ về vị trí đã có quyền hạn chế trên máy Unix; trên Windows dùng đường dẫn thích hợp. Các lệnh này **không được tự chạy vào production** nếu chưa có chính sách vận hành/quyền truy cập tương ứng.

- `settings=default` chọn template ít chi phí hơn.
- `duration=60s` giới hạn thời gian chạy.
- `filename=...` chỉ định đích kết xuất; người chạy phải có quyền ghi và cần bảo vệ file sau khi tạo.
- Lệnh `JFR.start` có thể được thực hiện với JVM đang chạy mà không cần restart, nếu diagnostic command/attach được hỗ trợ và có quyền.

Khi cần profiling sâu, dùng `settings=profile` trong **khoảng thời gian được xác định và giám sát**:

~~~bash
jcmd 12345 JFR.start name=profile-brief settings=profile duration=60s filename=/secure/jfr/profile-brief.jfr
~~~

Không nên vừa đổi sang profile vừa bật hàng loạt events không liên quan rồi kết luận overhead của JFR là do một setting duy nhất.

### 5.2. Continuous recording có giới hạn

Một recording kiểu rolling, ví dụ:

~~~bash
jcmd 12345 JFR.start name=rolling settings=default disk=true maxage=10m maxsize=64m
~~~

Khi cần lấy dữ liệu đã thu:

~~~bash
jcmd 12345 JFR.dump name=rolling filename=/secure/jfr/incident.jfr
~~~

Dừng khi không cần:

~~~bash
jcmd 12345 JFR.stop name=rolling
~~~

**Cần hiểu chính xác các giới hạn:**

- `maxage` giới hạn tuổi dữ liệu được **giữ trong disk repository** của recording; `maxsize` giới hạn dung lượng dữ liệu được **giữ trong repository** đó. Cả hai chỉ phù hợp khi `disk=true`.
- Các giới hạn hoạt động theo **chunk** và điều kiện của JVM; không phải cam kết từng byte không bao giờ vượt ranh giới trong mọi thời điểm.
- `maxsize` phải phù hợp với kích thước chunk tối thiểu và cấu hình JFR của JVM. Trong ví dụ, 64 MiB là con số minh họa cần kiểm tra với môi trường thật.
- Giá trị bằng 0 hoặc không cấu hình có thể mang nghĩa **không giới hạn** theo từng option. Nếu không giới hạn cả tuổi và dung lượng, dữ liệu có thể tăng không mong muốn.
- `JFR.dump` tạo một **bản tệp được xuất ra**; giới hạn của recording repository **không tự xóa** các file dump, bản upload, bản sao trong kho lưu trữ, log hoặc backup.
- `disk=false` giữ dữ liệu trong các buffer bộ nhớ và thay đổi khả năng ghi/đọc history; nó **không phải cài đặt “ẩn danh hóa”** và không loại bỏ nhu cầu kiểm soát dữ liệu.

Theo dõi cả **filesystem repository tạm thời** của JFR lẫn các file `.jfr` xuất ra. Không nên để repository đầy đĩa hoặc khiến dữ liệu phải bị thu hồi đột ngột chỉ vì cấu hình không có giới hạn.

## 6. Dữ liệu trong recording có thể nhạy cảm đến mức nào?

Một tệp `.jfr` không nhất thiết chứa payload của mọi request. Nhưng tùy **event types đang bật, JVM/JDK, custom events và ứng dụng**, nó có thể bộc lộ thông tin quan trọng:

| Nhóm thông tin | Ví dụ có thể xuất hiện | Vì sao cần thận trọng |
| --- | --- | --- |
| Tên class, method, package và stack traces | Các đường gọi trong ứng dụng hoặc thư viện | Tiết lộ cấu trúc code, mô-đun nội bộ, hành vi xử lý |
| Thread metadata | Tên/ID thread, thread liên quan sự kiện | Tên thread đôi khi bị ứng dụng đặt chứa tenant ID hoặc dữ liệu request |
| JVM/OS/process context | Thông tin phiên bản, lệnh chạy, arguments hoặc cấu hình JVM/systems nếu event liên quan bật | Có thể chứa endpoint nội bộ, cấu hình nhạy cảm hoặc thông tin môi trường |
| I/O metadata | Đường dẫn tệp, host/address/port và thời lượng/trạng thái I/O nếu event bật | Bộc lộ hệ thống nội bộ, đường dẫn người dùng, topology |
| Tên/giá trị trong custom event | `customerId`, `requestUri`, `sql`, `errorText`, `authorizationHeader` nếu lập trình viên tự ghi | Có thể chứa PII, dữ liệu cá nhân, token, bí mật truy cập |
| Dữ liệu cấp phát/profiling | Class được cấp phát, call sites, tần suất | Có thể làm lộ logic nghiệp vụ và tần suất hoạt động |
| Metadata của recording | Thời điểm, JVM/runtime, tên ứng dụng hoặc settings | Có thể cho biết lịch trình vận hành và đặc điểm hệ thống |

**Không khẳng định mọi JFR luôn ghi passwords, môi trường hay câu SQL.** Có hay không phụ thuộc event được bật và nội dung ứng dụng ghi. Chính vì khó biết một file chứa gì nếu chưa kiểm tra, **hãy đối xử với file JFR chưa được rà soát như dữ liệu chẩn đoán nội bộ có thể nhạy cảm**.

Một số kiểu event có thể chỉ chứa metadata (ví dụ địa chỉ/port hoặc tên class), không chứa nội dung gói mạng. Nhưng metadata đó vẫn có thể nhạy cảm trong bối cảnh kiến trúc nội bộ hoặc yêu cầu bảo vệ dữ liệu của doanh nghiệp.

### Nguy cơ đặc biệt từ tên thread, SQL và URL

Một đội ngũ có thể vô tình đặt:

~~~java
Thread.currentThread().setName("tenant-" + tenantId);
~~~

Hoặc định nghĩa JFR custom event có field:

~~~java
String requestUri;
String queryText;
~~~

Hai mảnh mã chỉ là ví dụ về **nguồn dữ liệu cần rà soát**, không phải hướng dẫn thu thập. Nếu tên thread, URI hay query chứa email, token, ID người dùng hoặc tham số nhạy cảm, việc recording các trường đó có thể đưa chúng vào file.

Không nên “lọc dữ liệu nhạy cảm sau khi upload” như hàng rào đầu tiên. Hãy giảm hoặc bỏ chúng **ngay tại nơi tạo event**.

## 7. Ví dụ một custom event an toàn hơn

Thay vì log thông tin riêng của từng request, một event mô tả **số lượng đã xử lý theo nhóm** có thể đủ để tìm vấn đề throughput:

~~~java
@jdk.jfr.Name("demo.SafeBatch")
@jdk.jfr.StackTrace(false)
static class SafeBatch extends jdk.jfr.Event {
    String stage;
    int itemCount;
}
~~~

Đây là **mảnh khai báo class lồng** (không phải chương trình độc lập). Nó không mang email, request body, JWT, session ID, raw URL hay SQL text. Điều đó **giảm bề mặt dữ liệu nhạy cảm** từ custom event, dù recording vẫn có thể chứa các event JVM/JDK khác.

Lưu ý:

- Dùng tên nhóm cố định/được cho phép như `"aggregate"` thay vì giá trị chứa dữ liệu người dùng.
- Ghi **số liệu đã tổng hợp** nếu có thể, thay vì từng sự kiện cá nhân.
- Cân nhắc `withoutStackTrace()` cho event khi không cần đường gọi.
- Nếu giá trị chỉ phục vụ debug, cân nhắc threshold/sampling thay vì commit mọi lần.
- Không dùng `@Label` hoặc một annotation để suy ra dữ liệu đã được mã hóa, redacted hay bảo vệ; annotation chủ yếu mô tả metadata.
- **Vô hiệu hóa event** sẽ giảm thu thập mới; nó **không làm sạch** các bản recording đã xuất trước đó.

## 8. Chương trình Java 17+ chạy độc lập và có kết quả kiểm chứng

Ví dụ sau được **biên dịch và chạy thử trên OpenJDK 21** với API đã có trong Java 17. Nó cho thấy cách:

1. Mở một recording theo cấu hình `default`.
2. Giới hạn tuổi/dung lượng dữ liệu trên disk repository.
3. Chỉ bật custom event chứa thông tin **không định danh cá nhân**.
4. Không ghi stack trace cho custom event.
5. Dump recording vào một tệp tạm, đọc lại các event theo đúng type name.
6. Chỉ in số liệu tổng hợp và xóa tệp tạm khi kết thúc.

Lưu thành **`JfrCostPrivacyDemo.java`** (UTF-8):

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrCostPrivacyDemo {
    @Name("demo.SafeBatch")
    @Label("Safe Batch")
    @Category({"Demo", "Aggregates"})
    @StackTrace(false)
    static class SafeBatch extends Event {
        @Label("Stage") String stage;
        @Label("Item Count") int itemCount;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("jfr-safe-demo-", ".jfr");
        try {
            try (Recording recording =
                    new Recording(Configuration.getConfiguration("default"))) {
                recording.setName("safe-demo");
                recording.setToDisk(true);
                recording.setMaxAge(Duration.ofMinutes(3));
                recording.setMaxSize(32L * 1024 * 1024);
                recording.enable(SafeBatch.class)
                         .withoutThreshold()
                         .withoutStackTrace();
                recording.start();

                for (int count : new int[] {10, 20, 30}) {
                    SafeBatch event = new SafeBatch();
                    event.stage = "aggregate";
                    event.itemCount = count;
                    if (event.shouldCommit()) {
                        event.commit();
                    }
                }

                recording.stop();
                recording.dump(file);
            }

            int eventCount = 0;
            int total = 0;
            boolean onlyAggregate = true;
            try (RecordingFile recordingFile = new RecordingFile(file)) {
                while (recordingFile.hasMoreEvents()) {
                    RecordedEvent event = recordingFile.readEvent();
                    if ("demo.SafeBatch".equals(event.getEventType().getName())) {
                        eventCount++;
                        total += event.getInt("itemCount");
                        onlyAggregate &=
                            "aggregate".equals(event.getString("stage"));
                    }
                }
            }
            System.out.println("safe-events=" + eventCount);
            System.out.println("total-items=" + total);
            System.out.println("only-aggregate-stage=" + onlyAggregate);
            System.out.println("jfr-written=" + (Files.size(file) > 0));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 JfrCostPrivacyDemo.java
java JfrCostPrivacyDemo
~~~

**Kết quả đã thử trên OpenJDK 21:**

~~~text
safe-events=3
total-items=60
only-aggregate-stage=true
jfr-written=true
~~~

**Vì sao kết quả như vậy?**

- Ba lần tạo `SafeBatch` với `itemCount` lần lượt `10`, `20`, `30`; tổng là `60`.
- Event name `demo.SafeBatch` được cố định bằng `@Name`, nên bộ đọc chỉ đếm event của ví dụ, không đếm các event JVM khác mà cấu hình default có thể phát sinh.
- `event.shouldCommit()` tránh commit nếu event không được ghi theo cấu hình; khi đã bật event và bỏ threshold, ba event ở ví dụ đều được ghi.
- `withoutStackTrace()` vô hiệu hóa stack trace cho **event custom này**, không tắt stack trace của các event khác.
- `setMaxAge(Duration.ofMinutes(3))` và `setMaxSize(...)` giới hạn giữ dữ liệu ở repository, **không giới hạn kích thước mọi bản dump** được tạo ngoài repository và không bảo đảm file không chứa metadata khác.
- Recording được `stop()` rồi `dump(file)` khi dữ liệu vẫn còn trong recording; sau đó `Recording.close()` giải phóng tài nguyên.
- Tệp `.jfr` tạm được xóa trong `finally`; đây là ví dụ chạy cục bộ, **không phải** chính sách xóa bản ghi production hay bản sao backup.

### Kiểm thử dữ liệu nhạy cảm vẫn phải kiểm tra toàn bộ recording

Ví dụ chỉ chứng minh **custom event do ta định nghĩa** không chứa field PII. Nó **không chứng minh toàn bộ tệp `.jfr` được ẩn danh**, bởi cấu hình default vẫn có thể thu thập các event JVM/JDK và metadata môi trường. Nếu file thật cần chia sẻ ra ngoài, bắt buộc thực hiện quy trình phân loại dữ liệu và kiểm duyệt nội dung ở cấp recording.

## 9. Kiểm tra file recording bằng `jfr` và hiểu giới hạn của các lệnh

Với JDK đã cài công cụ `jfr`, có thể xem:

~~~bash
jfr summary incident.jfr
jfr metadata incident.jfr
jfr print --events jdk.CPULoad incident.jfr
~~~

- `jfr summary` giúp xem kích thước, loại event, số lượng và các thống kê tổng hợp.
- `jfr metadata` cho biết tên event và schema fields trong recording.
- `jfr print` có thể in các **giá trị cụ thể** của event; cần hạn chế xuất ra console, log chia sẻ hoặc hệ thống CI nếu có dữ liệu nhạy cảm.

**Quan trọng:** chỉ chạy các lệnh này ở môi trường được phép và với file đã phân loại phù hợp. Dữ liệu xuất ra dạng text/JSON cũng có thể chứa thông tin nhạy cảm, thậm chí dễ copy/paste hơn file nhị phân ban đầu.

### Lọc lúc hiển thị khác lọc nội dung file

~~~bash
jfr print --events jdk.CPULoad incident.jfr
~~~

Lệnh trên chọn **event được in ra**, không sửa tệp gốc và **không xóa** các event khác khỏi `incident.jfr`.

Các JDK hiện đại cũng có thể cung cấp `jfr scrub` để lọc loại sự kiện/nhóm/thread khỏi một bản recording:

~~~bash
jfr scrub --exclude-events demo.RawPayload incident.jfr reviewed.jfr
~~~

Lệnh trên là **minh họa** cho việc lọc một event type tên `demo.RawPayload` nếu nó tồn tại. Cần kiểm tra `jfr help scrub` trên **JDK đang dùng**, vì lệnh/phương án tùy bản công cụ.

**`scrub` không phải cam kết bảo mật tự động**: nó có thể lọc theo event/thread/category, không nhất thiết thay thế hoặc xóa một field nhạy cảm bên trong **những event còn được giữ lại**. Sau scrub, phải rà soát file đầu ra theo chính sách chia sẻ; file gốc cũng cần được bảo vệ và xử lý riêng.

## 10. Chính sách bảo vệ file `.jfr`

Một recording file có thể tiết lộ chi tiết hệ thống và thông tin do ứng dụng ghi vào. Vì vậy hãy áp dụng quản trị dữ liệu tương tự những artifact chẩn đoán nội bộ khác:

### 10.1. Trước khi thu thập

1. **Xác định mục đích:** ví dụ “tìm p99 latency khi đọc đĩa”, không phải “thu mọi thứ để phòng sau này cần”.
2. **Kiểm kê event types:** built-in và custom events. Với custom events, duyệt tên/trường và đường truyền dữ liệu từ business objects.
3. **Giảm dữ liệu cá nhân:** không ghi nguyên request/response body, credentials, cookies, access tokens, personal identifiers hoặc query parameters chứa dữ liệu riêng nếu không thật sự cần.
4. **Xác định thời gian và dung lượng:** chọn `default`, giới hạn duration/maxage/maxsize phù hợp, dùng `profile` ngắn hạn khi có lý do.
5. **Chuẩn bị nơi ghi bảo mật:** directory với quyền tối thiểu, dung lượng và chính sách retention. Không coi `/tmp` hoặc volume chia sẻ là nơi mặc nhiên an toàn.
6. **Xác định chủ thể được phép attach/dump:** diagnostic tool có thể trích dữ liệu nhạy cảm; chỉ cấp cho nhân sự/quy trình cần thiết.

### 10.2. Khi đang thu thập

- Giám sát **CPU, p95/p99 latency, throughput, GC pause, disk I/O và dung lượng repository**.
- Xem số event và tốc độ tăng kích thước; giảm scope nếu event quá dày.
- Không nhập request payload hoặc bí mật vào custom event chỉ để hỗ trợ việc phân tích ngắn hạn.
- Giữ `jcmd` và khả năng truy cập JVM trong ranh giới quyền hạn thích hợp; công cụ attach có khả năng quan sát sâu nên cần được kiểm soát.
- Chỉ ghi/chuyển file tới kho an toàn, tránh thư mục public hoặc link tải không xác thực.

### 10.3. Khi xuất và chuyển tệp

- Coi bản dump là **artifact nhạy cảm cho tới khi được phân loại**; kiểm tra event types, trường và metadata.
- Nếu phải chia sẻ: ưu tiên báo cáo tổng hợp ít nhạy cảm thay vì nguyên file. Chỉ chia sẻ recording đã được review đến người được phép.
- Dùng kênh chuyển có mã hóa khi truyền và cơ chế lưu trữ có kiểm soát quyền truy cập, mã hóa phù hợp khi lưu.
- Ghi nhận người nhận, lý do, phạm vi và thời gian giữ theo quy định của tổ chức.
- Không đính kèm nguyên `.jfr` lên issue tracker, chat nhóm công khai, kho mã nguồn hoặc email bên ngoài theo thói quen.
- **Giảm dữ liệu tại nguồn** luôn tốt hơn thu tất cả rồi hy vọng “ẩn được” bằng công cụ export.

### 10.4. Sau khi phân tích

- Dừng recording tạm khi đã đủ thông tin.
- Xóa/sắp xếp vòng đời file gốc, bản scrub, file kết xuất JSON/text, bản copy, upload và backup theo chính sách retention.
- Không xem `maxage/maxsize` của JFR là chính sách xóa tất cả các bản sao bên ngoài.
- Tránh ghi tên file JFR và thông tin vận hành nhạy cảm vào log công khai.
- Với sự cố cần lưu chứng cứ, bảo toàn bằng quy trình được phép; không xóa dữ liệu có nghĩa vụ giữ lại chỉ vì nội dung nhạy cảm.

## 11. Đo overhead thực tế của JFR trên workload

Bài toán performance không thể trả lời bằng một tỷ lệ overhead chung. Một thử nghiệm đáng tin cần:

**Điều kiện đối chứng:** giữ nguyên JDK/vendor, heap/GC settings, cấu hình container/CPU/memory, mức tải, dữ liệu thử nghiệm và điểm xuất báo cáo. Không đồng thời đổi phiên bản ứng dụng, DB và event settings khi đo.

Đo theo ít nhất ba trạng thái:

1. **Baseline:** workload khi không có recording cần đo.
2. **Default:** workload tương đương với `settings=default`.
3. **Profile/custom:** workload tương đương với `settings=profile` hoặc cấu hình custom dự định dùng.

Theo dõi trong mỗi trạng thái:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Throughput (requests/second hoặc items/second) | Năng lực xử lý có thay đổi không? |
| Latency p50/p95/p99 | Có tác động tới người dùng, nhất là tail latency, không? |
| CPU process và tổng CPU host/container | JVM thu thập dữ liệu có tiêu thụ thêm CPU không? |
| Heap/GC pauses, allocation | Có ảnh hưởng tới cấp phát, rác và pause không? |
| Disk write bytes/second và file size | Tốc độ ghi recording có phù hợp hạn mức không? |
| JFR event count/size theo `jfr summary` | Loại sự kiện nào tạo nhiều dữ liệu? |
| Ổn định theo thời gian và các lần lặp | Kết quả có lặp lại hay là nhiễu tải? |

Lặp lại đủ lần để giảm nhiễu, warm-up ứng dụng trước khi so sánh và dùng dữ liệu phù hợp để tránh đột biến tùy thời điểm. Nếu đo profiling event nặng, nên giới hạn thời gian và có điều kiện dừng nếu latency/disk vượt ngưỡng an toàn của hệ thống.

### Công thức tham khảo

Với một đại lượng mà **cao hơn nghĩa là tốn hơn** (ví dụ CPU hoặc latency), độ thay đổi tương đối là:

~~~text
deltaPercent = (measuredWithJfr - baseline) / baseline * 100
~~~

Nếu baseline bằng 0, không dùng trực tiếp phép chia đó. Với throughput (cao hơn thường tốt hơn), cần diễn giải hướng thay đổi ngược lại. Đừng báo “JFR overhead = 2%” khi chưa nói rõ **2% của chỉ số nào**, tải bao nhiêu và đo bằng cách nào.

**Không lấy size của file .jfr làm thước đo trực tiếp cho CPU overhead.** Dung lượng lớn có thể liên quan số lượng event và băng thông I/O, nhưng không tự suy ra mức chậm của ứng dụng.

## 12. Trường hợp có nguy cơ cao: custom events trên đường nóng

Giả sử code backend xử lý một request và muốn ghi event:

~~~java
// Không nên đưa dữ liệu bí mật vào event.
event.requestBody = rawBody;
event.authorizationHeader = authHeader;
event.sqlWithParameters = queryText;
event.commit();
~~~

Đây là **mảnh mã minh họa điều cần tránh**, không phải đoạn khai báo event đầy đủ. Các hậu quả có thể xảy ra đồng thời:

- **Privacy:** request body, header hoặc SQL chứa PII/token nằm trong recording.
- **CPU/heap:** phải tạo/bảo toàn chuỗi hoặc bản sao dữ liệu có thể lớn.
- **Dung lượng:** event count tăng theo lưu lượng request.
- **Thời gian sống:** dữ liệu có thể tồn tại trong repository, bản dump và bản sao xuất ra.
- **Rủi ro vận hành:** người phân tích tưởng file chỉ chứa số liệu kỹ thuật trong khi thực tế chứa dữ liệu nhạy cảm.

Cách tiếp cận tốt hơn:

~~~java
if (event.shouldCommit()) {
    event.routeGroup = "catalog-read";
    event.itemCount = itemsProcessed;
    event.commit();
}
~~~

Các field `routeGroup` và `itemCount` chỉ có ý nghĩa khi bạn **đã định nghĩa custom event tương ứng**. Không ghi raw URL có query string hay user ID vào `routeGroup`; dùng danh mục route tĩnh được phép. Nếu cần điều tra một giao dịch cụ thể, dùng cơ chế tracing/logging có kiểm soát dữ liệu và quyền truy cập phù hợp, không tiện tay đưa mọi tham số vào JFR.

**Cảnh báo:** ngay cả aggregate events vẫn có thể tiết lộ dữ liệu thống kê nhạy cảm khi nhóm quá nhỏ hoặc dùng label có khả năng tái định danh. Đánh giá theo nghiệp vụ.

## 13. Những hiểu nhầm phổ biến

| Hiểu nhầm | Thực tế |
| --- | --- |
| “JFR có overhead bằng 0.” | JFR được tối ưu để overhead thấp nhưng vẫn phải đo theo event settings và workload. |
| “`settings=profile` lúc nào cũng an toàn để bật liên tục.” | Profile thu thập nhiều dữ liệu hơn và có thể tốn tài nguyên; thường dùng ngắn hạn. |
| “Cứ có `maxsize` là không thể đầy đĩa.” | Giới hạn repository theo chunk, không bao quát mọi file dump và bản sao. |
| “`disk=false` nghĩa là recording không chứa dữ liệu nhạy cảm.” | Dữ liệu có thể vẫn nằm trong buffer và có thể được xử lý/thu thập; không phải cơ chế ẩn danh. |
| “`jfr print --events ...` làm sạch file gốc.” | Chỉ lọc nội dung in ra, file gốc không bị sửa. |
| “`jfr scrub` tự loại mọi token/PII.” | Bộ lọc event/thread không bảo đảm redaction từng field trong các event còn lại. |
| “Mọi recording luôn chứa request body/password.” | Chỉ có nếu event/metadata/cấu hình phù hợp thu thập chúng; không nên suy đoán ngược lại rằng file an toàn. |
| “Custom event chỉ là logging miễn phí.” | Commit tần suất cao và dựng payload nặng cũng có chi phí CPU/heap/disk. |
| “Disable event sẽ xóa dữ liệu cũ.” | Nó chỉ thay đổi thu thập trong tương lai; các tệp đã xuất vẫn phải quản lý. |
| “Stack trace chỉ chứa số dòng.” | Còn có tên class/method, cấu trúc call path, có thể nhạy cảm. |
| “File .jfr là binary nên không đọc được thông tin.” | `jfr print`, API/JMC có thể trích xuất nội dung rất chi tiết. |
| “Có thể đo overhead từ kích thước file một cách trực tiếp.” | Cần so CPU/latency/throughput/GC/disk với baseline, không chỉ file size. |
| “Mọi JDK đều có cùng subcommands và settings.” | Cần kiểm tra phiên bản, implementation và `jfr help`/`jcmd PID help` thực tế. |
| “Có quyền đọc file hệ thống là nên upload JFR ra ngoài.” | Quyền vận hành không thay thế chính sách phân loại và chia sẻ dữ liệu. |

## 14. Checklist trước khi bật JFR trên production

1. **Mục tiêu:** câu hỏi chẩn đoán nào cần trả lời?
2. **Tải:** ứng dụng có đang ở mức tải mà thêm CPU/disk có thể gây sự cố không?
3. **Cấu hình:** bắt đầu bằng `default` hay cần `profile`? Có event nặng/GC roots nào được bật không?
4. **Chi phí sự kiện:** threshold, period, stack trace, custom events có được tối ưu và hạn chế không?
5. **Giới hạn:** có `duration`, `maxage`, `maxsize` hoặc quy trình dừng thủ công rõ ràng?
6. **Nơi lưu:** repository và output file có quyền hạn chế, dung lượng và quản trị retention phù hợp?
7. **Dữ liệu:** sự kiện có thể chứa thread names, class paths, host, process arguments, custom fields hoặc PII không?
8. **Quyền:** ai được dùng `jcmd`, xem `.jfr`, export/chia sẻ và xóa các bản ghi?
9. **Đo:** đã có baseline CPU, p99 latency, throughput, GC và disk để so sánh?
10. **Giám sát và dừng:** có điều kiện dừng nếu chi phí vượt ngưỡng hoặc không còn mục đích chẩn đoán?
11. **Hậu kiểm:** có bước xem metadata/event types, phân loại và review trước khi chia sẻ file không?
12. **Vòng đời:** có chính sách quản lý các bản dump, file scrub, bản export và backup ngoài repository không?

## 15. Bài tập tự luyện

### Bài 1 — Chọn cấu hình hợp lý

**Tình huống:** dịch vụ production có p99 latency cao bất thường 2 lần/ngày; đội muốn thu thập JFR liên tục và xem 10 phút gần nhất khi xảy ra lỗi.

**Gợi ý:** bắt đầu từ `settings=default` với rolling recording `disk=true maxage=10m maxsize=...` theo dung lượng đo được, rồi dump khi cần. Giám sát overhead và quản lý nơi lưu. Chỉ bật `profile` ngắn hạn nếu thông tin chưa đủ.

### Bài 2 — Xác định dữ liệu nhạy cảm

Một custom event có các fields `routeGroup`, `durationMs`, `userEmail` và `rawAuthorizationHeader`. Hãy chọn trường nào nên giữ nếu mục tiêu chỉ đo độ trễ theo nhóm route.

**Đáp án gợi ý:** giữ `routeGroup` theo danh mục tĩnh và `durationMs`; bỏ `userEmail` và `rawAuthorizationHeader` vì không cần cho mục tiêu và có nguy cơ lộ dữ liệu/tokens.

### Bài 3 — Lọc hiển thị và xóa dữ liệu

Bạn chạy `jfr print --events jdk.CPULoad incident.jfr`, sau đó gửi nguyên `incident.jfr` qua email. Người nhận có thể đọc các event khác trong file không?

**Đáp án:** có. Lệnh print chỉ lọc những gì hiển thị trên terminal, **không thay đổi file gốc**. Cần review và xử lý artifact trước khi chia sẻ, ưu tiên báo cáo tổng hợp.

### Bài 4 — Đo overhead

Baseline p99 là 120 ms; khi dùng JFR profile p99 đo được 132 ms trong workload giống nhau. Hãy tính độ tăng tương đối:

~~~text
(132 - 120) / 120 * 100 = 10%
~~~

**Đáp án:** p99 tăng **10%** trong phép đo minh họa. Chưa thể suy ra đây là overhead cố định của JFR; phải lặp đo, xét nhiễu tải, GC, các yếu tố môi trường và tính đại diện của workload.

### Bài 5 — Giới hạn repository

Recording có `maxage=10m`, `maxsize=64m` nhưng mỗi ngày một người dump 3 file vào folder chung, không ai xóa chúng. Tại sao vẫn đầy đĩa?

**Đáp án:** `maxage/maxsize` điều khiển dữ liệu giữ trong repository của recording, không tự dọn các **bản dump độc lập**. Cần quản trị vòng đời tệp xuất ra.

### Bài 6 — Thực hành Java

Dùng chương trình `JfrCostPrivacyDemo` ở mục 8:

1. Chạy nguyên mẫu và xác nhận `safe-events=3`, `total-items=60`.
2. Thử đổi ba số đếm thành `5`, `10`, `15` và dự đoán tổng `30`.
3. Bật `@StackTrace(true)` hoặc event settings tương ứng trong môi trường thử nghiệm, quan sát metadata/size thay đổi nhưng không cam kết con số cố định.
4. Không bổ sung field chứa thông tin cá nhân. Viết một đoạn giải thích tại sao việc ghi `requestBody` sẽ thay đổi rủi ro bảo mật và chi phí thu thập.

## 16. Tài liệu chính thức, còn phù hợp

- [Oracle JDK 25 — Diagnostic Tools / Flight Recorder](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): nhóm sự kiện, cấu hình `default`/`profile` và nguyên tắc overhead.
- [Oracle JDK 25 — jcmd Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`, `maxage`, `maxsize`, `path-to-gc-roots`.
- [Oracle JDK 25 — jfr Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jfr.html): `summary`, `metadata`, `print`, `scrub` và giới hạn lọc.
- [OpenJDK Dev.java — Configuring JDK Flight Recorder](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/): cách cấu hình recording, event settings, threshold, stack trace và tùy chọn JFR.
- [Oracle JDK 17 — Recording API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): `Recording(Configuration)`, `setMaxSize`, `setMaxAge`, `enable`, `stop`, `dump`.
- [Oracle JDK 17 — jdk.jfr Package](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/package-summary.html): event settings và API custom events.
