# Định danh chỉ số bằng tên, tag và đơn vị đo

Khi đọc một con số trên biểu đồ, trước hết cần biết đó là số gì, thuộc nhóm nào và dùng đơn vị nào. Giá trị `1000` có thể là một nghìn công việc đã hoàn tất, một nghìn byte hoặc một nghìn mili giây. Chỉ có giá trị số thì chưa đủ để diễn giải.

Trong Micrometer, ba thông tin cần thiết để hiểu phép đo là **tên đại lượng, các chiều phân loại bằng tag và đơn vị đo**. Tuy nhiên, cần phân biệt chúng với khóa mà registry dùng để nhận diện meter: **trong cùng một registry, định danh dựa trên tên và tập tag; đơn vị đo là metadata, không phải một thành phần khóa độc lập**.

Bài này giúp bạn thiết kế tên và tag nhất quán, khai báo và đọc đúng đơn vị, đồng thời nhận ra khi nào hai lời gọi đăng ký đang cùng dùng một meter. Các hành vi trong ví dụ được minh họa bằng Micrometer 1.13.0, phù hợp để học cùng Spring Boot 3.3.x; mã dùng Java 17 và chạy được trên JDK 21.

## 1. Phân biệt meter, số đo và định danh

`Meter` là công cụ thu thập các số đo. Ví dụ, một `Counter` cho biết lượng đã được tăng; một `Timer` cung cấp ít nhất số lần ghi nhận và tổng thời gian. Một meter có thể tạo ra nhiều đại lượng được xuất ra hệ thống giám sát.

`MeterRegistry` quản lý các meter. Khi bạn đăng ký một meter, registry cần quyết định trả về meter đã có hay tạo một meter mới.

Ví dụ một bộ đếm công việc:

```text
Tên logic: batch.jobs.completed
Tag:       queue=export, outcome=success
Đơn vị:    jobs
Loại:      Counter
Giá trị:   3
```

Cách đọc: đã ghi nhận ba công việc hoàn tất thuộc hàng đợi xuất dữ liệu, với kết quả thành công.

Đây là các vai trò khác nhau:

| Thông tin | Câu hỏi được trả lời | Ví dụ | Có làm thành phần khóa tên–tag không? |
| --- | --- | --- | --- |
| Tên logic | Đang đo đại lượng nào? | `batch.jobs.completed` | Có |
| Tag | Đại lượng thuộc nhóm nào? | `queue=export`, `outcome=success` | Có |
| Đơn vị cơ sở (`baseUnit`) | Giá trị được hiểu theo đơn vị gì? | `jobs`, `bytes` | Không |
| Loại meter | Ghi nhận theo cơ chế nào? | `Counter`, `Timer` | Không tạo một khóa tên–tag khác; phải tương thích với meter đã đăng ký |
| Mô tả (`description`) | Đại lượng có ý nghĩa cụ thể ra sao? | Số công việc đã kết thúc | Không |
| Giá trị hiện tại hoặc thống kê | Đã đo được bao nhiêu? | `3`, tổng thời gian `1` giây | Không |

`Meter.Id` mang nhiều thông tin mô tả meter, nhưng không nên suy ra rằng mọi trường trong đối tượng đó đều tham gia so sánh định danh. Trong Micrometer 1.13.0, phép so sánh định danh dùng tên và tập tag. Tài liệu Micrometer cũng mô tả meter là duy nhất theo tên và các chiều phân loại. [Mô hình Meter](https://docs.micrometer.io/micrometer/reference/concepts/meters.html).

## 2. Đặt tên để người đọc biết đang đo gì

### 2.1. Tên là hợp đồng về đại lượng

Một tên tốt diễn tả đại lượng tương đối ổn định, không gắn với từng đối tượng cụ thể:

| Nhu cầu | Tên logic có ý nghĩa | Thông tin nên đặt trong tag hoặc nguồn khác |
| --- | --- | --- |
| Đếm công việc đã kết thúc | `batch.jobs.completed` | Hàng đợi, kết quả |
| Đo thời gian xử lý công việc | `batch.job.duration` | Hàng đợi, loại công việc được giới hạn |
| Đo kích thước dữ liệu đầu ra | `batch.output.size` | Định dạng hoặc nhóm hàng đợi |
| Đọc số công việc đang chờ | `batch.queue.size` | Hàng đợi |

Người xem chỉ chọn tên `batch.jobs.completed` vẫn phải hiểu đó là nhóm số liệu về công việc đã kết thúc. Sau đó tag mới giúp phân tích chi tiết thành công, thất bại hoặc từng hàng đợi.

Tên quá chung như `value` hoặc `count` buộc người đọc tìm thêm ngữ cảnh. Tên chứa từng mã công việc như `batch.job.872391.completed` lại biến mỗi công việc thành một tên mới và làm việc truy vấn, tổng hợp khó quản lý.

### 2.2. Giữ tên logic tách khỏi quy ước của nơi nhận

Micrometer khuyến nghị tên viết thường, phân tách từ bằng dấu chấm. Registry cho từng hệ thống có thể chuyển tên sang quy ước phù hợp với hệ thống đó. [Quy ước tên của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html).

Ví dụ, `batch.jobs.completed` là tên được dùng trong mã. Sau khi xuất, tên vật lý có thể thay đổi cách phân tách hoặc bổ sung thông tin theo loại phép đo và đơn vị. Không mặc định tên trên hệ thống giám sát phải giống nguyên văn chuỗi trong Java.

Phân biệt ba mức:

```text
Tên logic được đăng ký trong Java
    -> quy tắc chuyển tên và biểu diễn của registry
    -> tên và chuỗi thời gian ở hệ thống giám sát
```

Không tạo hai tên logic chỉ khác nhau ở những ký tự mà nơi nhận sẽ chuẩn hóa giống nhau. Chẳng hạn, `normalization.test` và `normalization_test` là hai tên khác nhau trong registry bộ nhớ nhưng cùng thành `normalization_test` khi áp dụng quy ước snake case. Việc chúng cùng tồn tại cục bộ không bảo đảm xuất ra ngoài sẽ không xung đột.

### 2.3. Mô tả giúp làm rõ ranh giới

`description` có thể giải thích một công việc được tính là hoàn tất ở thời điểm nào, có tính lần thử lại hay không hoặc kích thước đang đo trước hay sau nén. Những chi tiết này giúp người vận hành dùng đúng số liệu.

Đổi mô tả không tạo một meter mới và không phải cơ chế cập nhật lại ý nghĩa của dữ liệu đã được ghi. Nếu đổi định nghĩa nghiệp vụ của đại lượng, cần xử lý thay đổi hợp đồng đo lường rõ ràng.

## 3. Tag tạo các chiều phân loại

Tag gồm khóa và giá trị. Các tổ hợp sau là ba định danh khác nhau trong cùng một registry:

```text
batch.jobs.completed {queue=export, outcome=success}
batch.jobs.completed {queue=export, outcome=failure}
batch.jobs.completed {queue=import, outcome=success}
```

Đổi `outcome` hoặc `queue` làm số liệu đi vào nhóm khác. Vì vậy, một tên logic có thể có nhiều meter tương ứng với các tổ hợp tag đã xuất hiện.

### 3.1. Thứ tự tag không tạo nhóm mới

Hai cách viết sau biểu diễn cùng tập tag:

```java
registry.counter("batch.jobs.completed",
        "queue", "export", "outcome", "success");
registry.counter("batch.jobs.completed",
        "outcome", "success", "queue", "export");
```

Đây là đoạn trích trong ngữ cảnh đã có biến `registry`. Việc đảo thứ tự cặp tag không phải cách tạo một bộ đếm độc lập.

Nếu hai thành phần trong ứng dụng cùng tăng meter có cùng tên và tag trong cùng registry, số liệu sẽ cộng vào cùng bộ đếm. Điều đó có thể là chủ ý để tổng hợp từ nhiều điểm ghi, nhưng cũng có thể là lỗi ghi nhận hai lần cho một sự kiện.

### 3.2. Quy ước giá trị cần nhất quán

`outcome=success` và `outcome=SUCCESS` không phải cùng giá trị logic trong registry. Nếu hai nhóm phát triển dùng hai cách viết, người vận hành có thể vô tình bỏ sót một nhóm khi lọc.

Với cùng họ số liệu, nên thống nhất:

- Ý nghĩa của từng khóa tag.
- Tập giá trị cho từng khóa và cách viết của chúng.
- Các khóa nào luôn có mặt.
- Cách biểu diễn trường hợp chưa xác định hoặc không áp dụng, nếu nghiệp vụ cần.

Không truyền giá trị `null` cho tag. Cũng không lặp cùng một khóa với nhiều giá trị trong một lần đăng ký rồi kỳ vọng tạo ra nhiều chiều độc lập; hãy xây dựng tập tag rõ ràng, mỗi khóa có một ý nghĩa.

### 3.3. Một tên không đồng nghĩa với một chuỗi thời gian

Nếu có hai hàng đợi, ba kết quả và bốn vùng chạy, số tổ hợp có thể là `2 × 3 × 4 = 24` trước khi xét thêm chiều khác. Đây là giới hạn tổ hợp của ví dụ, không phải khẳng định mọi tổ hợp đều xuất hiện.

Một timer còn có nhiều thống kê, nên số chuỗi thời gian ở nơi nhận có thể lớn hơn số định danh meter. Các cấu hình histogram cũng có thể làm số chuỗi tăng thêm.

Số lượng tổ hợp giá trị thường được gọi là cardinality. Tag theo từng mã công việc, mã yêu cầu hoặc người dùng có thể tăng cùng lượng dữ liệu phát sinh. Chọn các chiều phân loại có tập giá trị được kiểm soát; các định danh chi tiết từng lần xử lý thường phù hợp hơn với log hoặc trace.

## 4. Đơn vị đo là hợp đồng về ý nghĩa số

### 4.1. baseUnit không tạo một meter độc lập

Xét hai lời gọi đăng ký cùng tên và tag nhưng khai báo `baseUnit` khác nhau:

```text
Đăng ký lần đầu:  batch.jobs.completed + queue=export + outcome=success + jobs
Đăng ký lần sau:  batch.jobs.completed + queue=export + outcome=success + tasks
```

Với `SimpleMeterRegistry` và Micrometer 1.13.0, lần sau trả về counter đã được đăng ký; đơn vị trên meter đó vẫn là `jobs`. Đây là một tình huống cố ý tạo khai báo mâu thuẫn để quan sát, không phải mẫu thiết kế nên dùng.

Do đó, hai thành phần không thể phân biệt hai đại lượng chỉ bằng cách dùng cùng tên, cùng tag rồi đổi đơn vị. Đơn vị khác nhau không mở thêm một ô lưu số liệu.

Nếu một thành phần ghi byte còn thành phần khác ghi kilobyte vào cùng meter, registry không tự phát hiện ý nghĩa sai của từng số rồi chuyển đổi giúp. Kết quả có thể trông hợp lệ về kiểu Java nhưng không còn nghĩa đo lường thống nhất.

### 4.2. Đơn vị cơ sở không tự chuyển đổi số đầu vào

`DistributionSummary` thích hợp để ghi các giá trị không phải thời gian, chẳng hạn kích thước đầu ra. Có thể khai báo đơn vị bằng `baseUnit("bytes")`. [DistributionSummary và đơn vị cơ sở](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html).

Đoạn trích:

```java
DistributionSummary bytes = DistributionSummary.builder("batch.output.size")
        .baseUnit("bytes")
        .register(registry);
bytes.record(2);
```

Cần import `io.micrometer.core.instrument.DistributionSummary`. Mã trên ghi giá trị số `2`. Theo hợp đồng đã chọn, ứng dụng đang khai báo đó là 2 byte; thư viện không biết con số đầu vào vốn được tính theo byte hay KiB.

Nếu nguồn đầu vào là 2 KiB và hợp đồng của meter là byte, ứng dụng phải chuẩn hóa trước khi ghi:

```java
double sizeInKiB = 2.0;
bytes.record(sizeInKiB * 1024);
```

Phân biệt KiB và kB khi thiết kế hợp đồng: 1 KiB là 1024 byte, còn 1 kB là 1000 byte. Chọn một ý nghĩa và giữ nhất quán; đừng dùng một nhãn mơ hồ để che sự khác nhau.

Tương tự, giá trị tỷ lệ `0.25` và phần trăm `25` không thể trộn vào cùng meter mà không chuyển đổi về cùng thang đo. Metadata đơn vị không thay thế việc chuẩn hóa dữ liệu.

### 4.3. Timer có API đơn vị thời gian rõ ràng

Với thời gian, dùng `Timer` và truyền `Duration` hoặc cặp giá trị–`TimeUnit`:

```java
duration.record(Duration.ofMillis(250));
duration.record(750, TimeUnit.MILLISECONDS);
```

Tổng là 1000 ms, cũng là 1 giây. Khi đọc bằng `totalTime(TimeUnit.MILLISECONDS)` hay `totalTime(TimeUnit.SECONDS)`, bạn chỉ định rõ đơn vị kết quả.

Timer biết chuyển đổi thời gian theo API và theo đơn vị cơ sở phù hợp với registry. Điều này khác với việc chỉ gắn chuỗi `baseUnit` vào một summary. Không giả định tất cả nơi nhận đều dùng cùng đơn vị thời gian hoặc tự ghi hậu tố của đơn vị xuất vào tên logic. [Timer và chuyển đổi đơn vị](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html).

### 4.4. Loại meter phải phù hợp với đại lượng

Đơn vị chưa đủ để mô tả cơ chế đo. Một counter đơn vị `jobs` đếm lượng công việc; một gauge cũng có thể đơn vị `jobs` nhưng đọc số công việc đang chờ tại thời điểm quan sát.

Cùng đơn vị không có nghĩa là có thể cộng tùy ý hai đại lượng. “Tổng công việc đã hoàn tất” và “công việc đang chờ” vẫn là hai câu hỏi khác nhau, nên cần tên và loại công cụ phù hợp.

Ngược lại, đăng ký một `Counter` rồi đăng ký `Timer` với cùng tên và tag là xung đột loại. Trong phiên bản của ví dụ, registry báo `IllegalArgumentException`; trường `type` không biến chúng thành hai meter độc lập dưới cùng khóa tên–tag.

## 5. Ví dụ đầy đủ: quan sát định danh và đơn vị

Ví dụ dùng hai registry bộ nhớ để kiểm chứng:

- Cùng tên, cùng tag và đảo thứ tự tag vẫn dùng cùng counter.
- Chỉ đổi đơn vị không tạo counter mới.
- Đổi giá trị tag tạo nhóm riêng.
- Timer chuyển đổi đơn vị thời gian khi đọc.
- Summary giữ giá trị đầu vào theo hợp đồng đơn vị đã khai báo.
- Registry khác có trạng thái riêng, dù tên và tag giống nhau.

### 5.1. Chuẩn bị dự án thử nghiệm

Tạo hai tệp trong một thư mục riêng:

```text
meter-identity-demo/
├── pom.xml
└── MeterIdentityDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>meter-identity-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.13.0</version>
        </dependency>
    </dependencies>
</project>
```

Ví dụ cố định Micrometer 1.13.0 để kết quả có thể tái lập. Trong dự án Spring Boot, dùng tập phiên bản do Boot quản lý thay vì tự sao chép số phiên bản của bài thử nghiệm vào ứng dụng.

### 5.2. Mã Java

`MeterIdentityDemo.java`:

```java
import java.time.Duration;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MeterIdentityDemo {
    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        SimpleMeterRegistry otherRegistry = new SimpleMeterRegistry();
        try {
            Counter success = Counter.builder("batch.jobs.completed")
                    .tag("queue", "export")
                    .tag("outcome", "success")
                    .baseUnit("jobs")
                    .description("Completed batch jobs")
                    .register(registry);

            Counter reordered = Counter.builder("batch.jobs.completed")
                    .tag("outcome", "success")
                    .tag("queue", "export")
                    .baseUnit("jobs")
                    .register(registry);

            Counter differentUnit = Counter.builder("batch.jobs.completed")
                    .tag("queue", "export")
                    .tag("outcome", "success")
                    .baseUnit("tasks")
                    .register(registry);

            Counter failure = Counter.builder("batch.jobs.completed")
                    .tag("queue", "export")
                    .tag("outcome", "failure")
                    .baseUnit("jobs")
                    .register(registry);

            success.increment();
            reordered.increment(2);
            failure.increment();

            System.out.println("sameAfterTagReorder=" + (success == reordered));
            System.out.println("sameAfterUnitChange=" + (success == differentUnit));
            System.out.println("keptBaseUnit=" + success.getId().getBaseUnit());
            System.out.printf(Locale.ROOT,
                    "successCount=%.0f failureCount=%.0f%n",
                    success.count(), failure.count());

            Timer duration = Timer.builder("batch.job.duration")
                    .tag("queue", "export")
                    .register(registry);
            duration.record(Duration.ofMillis(250));
            duration.record(750, TimeUnit.MILLISECONDS);
            System.out.printf(Locale.ROOT,
                    "timerCount=%d totalMs=%.0f totalSeconds=%.3f%n",
                    duration.count(),
                    duration.totalTime(TimeUnit.MILLISECONDS),
                    duration.totalTime(TimeUnit.SECONDS));

            DistributionSummary outputSize =
                    DistributionSummary.builder("batch.output.size")
                            .tag("queue", "export")
                            .baseUnit("bytes")
                            .register(registry);
            outputSize.record(2048);
            outputSize.record(512);
            System.out.printf(Locale.ROOT,
                    "sizeUnit=%s sizeCount=%d totalSize=%.0f%n",
                    outputSize.getId().getBaseUnit(),
                    outputSize.count(), outputSize.totalAmount());

            boolean typeConflict = false;
            try {
                registry.timer("batch.jobs.completed",
                        "queue", "export", "outcome", "success");
            } catch (IllegalArgumentException expected) {
                typeConflict = true;
            }
            System.out.println("typeConflict=" + typeConflict);

            Counter other = Counter.builder("batch.jobs.completed")
                    .tag("queue", "export")
                    .tag("outcome", "success")
                    .baseUnit("jobs")
                    .register(otherRegistry);
            System.out.printf(Locale.ROOT,
                    "sameAcrossRegistries=%s otherCount=%.0f%n",
                    success == other, other.count());
        } finally {
            registry.close();
            otherRegistry.close();
        }
    }
}
```

Hai điểm cần chú ý trước khi chạy:

1. `differentUnit` là phép thử cố ý khai báo đơn vị khác để kiểm tra hành vi đăng ký lại. Trong mã ứng dụng thật, các nơi cùng ghi một đại lượng phải thống nhất đơn vị ngay từ đầu.
2. Phần bắt `IllegalArgumentException` chỉ bao quanh phép thử xung đột loại đã được chủ động tạo ra. Không dùng mẫu này để bỏ qua mọi lỗi đăng ký meter trong ứng dụng.

Chương trình gọi `close()` trong `finally` cho các registry do nó tự tạo. Đây là chương trình độc lập, không sử dụng vòng đời bean của Spring.

### 5.3. Biên dịch và chạy

Cần Maven và JDK 17 trở lên. Các lệnh sau cũng chạy với JDK 21, trong đó `--release 17` đặt mức ngôn ngữ và API Java của mã được biên dịch.

Tải các thư viện chạy vào `lib`:

```shell
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
```

PowerShell/Windows:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MeterIdentityDemo.java
java -cp "out;lib/*" MeterIdentityDemo
```

Linux/macOS:

```shell
mkdir -p out
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MeterIdentityDemo.java
java -cp "out:lib/*" MeterIdentityDemo
```

Classpath dùng dấu `;` trên Windows và `:` trên Linux/macOS. Maven cần tải phụ thuộc trong lần đầu nếu máy chưa có các thư viện.

Stdout:

```text
sameAfterTagReorder=true
sameAfterUnitChange=true
keptBaseUnit=jobs
successCount=3 failureCount=1
timerCount=2 totalMs=1000 totalSeconds=1.000
sizeUnit=bytes sizeCount=2 totalSize=2560
typeConflict=true
sameAcrossRegistries=false otherCount=0
```

`Locale.ROOT` giữ cách định dạng số ổn định, bao gồm dấu chấm trong `1.000`.

### 5.4. Đọc bằng chứng từ đầu ra

| Kết quả | Điều được kiểm chứng |
| --- | --- |
| `sameAfterTagReorder=true` | Thứ tự các cặp tag không tạo định danh khác |
| `sameAfterUnitChange=true` | Đổi metadata đơn vị chưa tạo counter mới |
| `keptBaseUnit=jobs` | Đơn vị của counter đã đăng ký trước được giữ trong thí nghiệm |
| `successCount=3 failureCount=1` | Hai lời gọi qua cùng counter cộng chung; tag `failure` có số liệu riêng |
| `timerCount=2 totalMs=1000 totalSeconds=1.000` | Cùng tổng thời gian có thể đọc ở các đơn vị rõ ràng |
| `sizeUnit=bytes sizeCount=2 totalSize=2560` | Hai kích thước 2048 và 512 được ghi theo hợp đồng byte |
| `typeConflict=true` | Không thể dùng cùng tên–tag để tạo thêm timer bên cạnh counter |
| `sameAcrossRegistries=false otherCount=0` | Registry thứ hai có đối tượng và trạng thái riêng |

Không diễn giải `sameAcrossRegistries=false` thành “tên và tag không còn quan trọng”. Quy tắc định danh cần được hiểu trong phạm vi registry đang xét. Hai registry độc lập không tự chia sẻ bộ đếm chỉ vì đăng ký cùng tên.

## 6. Truy vấn đúng nhóm số liệu

### 6.1. Tra cứu trong Java

Muốn lấy counter cho nhóm thành công, chỉ định các chiều cần lọc:

```java
Counter success = registry.get("batch.jobs.completed")
        .tags("queue", "export", "outcome", "success")
        .counter();
```

Đây là đoạn trích cho registry đã có dữ liệu. `get(...)` là cách tra cứu yêu cầu có kết quả; dùng nó khi thiếu meter là điều cần phát hiện trong kiểm chứng.

Một lời gọi như `registry.get("batch.jobs.completed").counter()` không tự tính tổng mọi counter có tên đó. Khi cần tổng hợp trong Java, hãy chọn các meter khớp rồi thực hiện phép tính có ý nghĩa.

Ví dụ cho đúng các counter trong thí nghiệm:

```java
double total = registry.find("batch.jobs.completed")
        .tag("queue", "export")
        .counters()
        .stream()
        .mapToDouble(Counter::count)
        .sum();
```

Kết quả trong registry chính của ví dụ là `4.0`, gồm ba công việc thành công và một công việc thất bại. Phép cộng này hợp lý vì các nhóm đang dùng chung định nghĩa “công việc đã kết thúc” và cùng đơn vị `jobs`.

Không cộng một số lượng theo byte với một số theo KiB chỉ vì hai meter có tên gần giống nhau. Cũng không cộng mọi thống kê của timer vào một con số: số lần và tổng thời gian là các đại lượng khác đơn vị.

### 6.2. Kiểm tra bằng Actuator trong ứng dụng web

Phần này áp dụng cho một ứng dụng Spring Boot web đang chạy, đã đưa cùng hợp đồng meter vào registry do Spring quản lý. Chương trình dòng lệnh ở phần 5 kết thúc sau khi in kết quả và không mở cổng HTTP.

Để dùng endpoint kiểm tra trong môi trường học, cấu hình exposure phù hợp, chẳng hạn:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
```

Cấu hình nằm trong `application.yml` của ứng dụng web có Actuator; nó không tự tạo các meter nghiệp vụ. Quyền đọc endpoint vẫn cần phù hợp với cấu hình truy cập của ứng dụng.

Chọn tên logic trong mã rồi lọc bằng các tham số `tag=KEY:VALUE`:

```shell
curl "http://localhost:8080/actuator/metrics/batch.jobs.completed"
curl "http://localhost:8080/actuator/metrics/batch.jobs.completed?tag=queue:export&tag=outcome:success"
```

Endpoint `metrics` dùng tên logic trước khi tên được chuẩn hóa cho hệ thống giám sát. Nó tổng hợp các thống kê của meter khớp tên và các tag đã lọc. Với đúng hai nhóm counter và số liệu của thí nghiệm, truy vấn theo tên có `COUNT=4`; truy vấn thêm `outcome=success` có `COUNT=3`. Đây là hành vi của endpoint, không phải quy tắc rằng mọi API tra cứu Java đều tự cộng. [Metrics endpoint trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Trong ứng dụng thật, các lần ghi mới có thể làm số tăng giữa hai truy vấn. Khi kiểm chứng số chính xác, cần kiểm soát các lần ghi và chọn đúng registry, instance cùng khoảng thời gian.

## 7. Các quy tắc chung có thể thay đổi định danh hiệu lực

### 7.1. Tag dùng chung

Ứng dụng có thể thêm tag ở cấp registry để phân biệt ứng dụng hoặc vùng chạy. Ví dụ dưới đây dành cho một registry tự quản lý và phải thực hiện trước khi đăng ký meter:

```java
registry.config().commonTags(
        "application", "batch-service",
        "region", "vn-south");
```

Khi xem định danh cuối cùng, cần tính cả tag chung bên cạnh tag khai báo tại điểm đo. Một người chỉ nhìn hai dòng `.tag(...)` ở service có thể chưa thấy hết các chiều mà meter thực sự mang.

Trong Spring Boot có thể cấu hình tag chung qua `management.metrics.tags` hoặc callback cấu hình registry thích hợp. Hãy thiết lập chúng trước khi các meter được đăng ký; không kỳ vọng thêm một tag về sau sẽ tự tái thiết kế đồng bộ mọi meter cũ.

### 7.2. Filter có thể làm hai định danh gặp nhau

`MeterFilter` có thể sửa tên, thêm hoặc bỏ tag trước khi meter được quản lý theo cấu hình hiệu lực. Vì vậy cần xét cả các quy tắc đó khi giải thích một xung đột hoặc việc số liệu bị gộp. [MeterFilter](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Ví dụ một filter bỏ tag `outcome`:

```java
registry.config().meterFilter(MeterFilter.ignoreTags("outcome"));
```

Đoạn trích cần import `io.micrometer.core.instrument.config.MeterFilter` và được cấu hình trước khi đăng ký meter. Khi đó hai nhóm sau có thể cùng về một counter:

```text
batch.jobs.completed {queue=export, outcome=success}
batch.jobs.completed {queue=export, outcome=failure}
                         |
                         v
batch.jobs.completed {queue=export}
```

Kết quả trong một registry bộ nhớ mới là lượng tăng của hai nhóm cộng vào cùng counter. Điều đó có thể phục vụ chủ ý bỏ một chiều phân tích, nhưng cũng làm mất khả năng phân biệt thành công và thất bại ở đường số liệu đó.

Nếu bỏ tag để giảm cardinality, cần đánh giá ý nghĩa của phép gộp. Các nhóm phải còn tương thích về đại lượng và đơn vị; giảm số chuỗi bằng cách làm mất nghĩa không phải là kết quả đo lường tốt.

## 8. Duy trì hợp đồng tên–tag–đơn vị khi phát triển

Một hợp đồng đo lường nên ghi rõ:

| Thành phần | Ví dụ hợp đồng |
| --- | --- |
| Tên | `batch.output.size` |
| Ý nghĩa | Kích thước dữ liệu đầu ra sau nén của một công việc đã hoàn tất |
| Loại | `DistributionSummary` |
| Đơn vị đầu vào | Byte |
| Khóa tag | `queue`, `format` |
| Giá trị được phép | Các hàng đợi và định dạng đã chuẩn hóa |
| Thời điểm ghi | Sau khi đã biết kích thước đầu ra thực tế |

Điều này giải quyết những thay đổi có thể không bị trình biên dịch phát hiện:

- Một phiên bản chuyển sang ghi kích thước trước nén nhưng giữ nguyên tên và mô tả.
- Một thư viện nhận giá trị theo KiB rồi ghi thẳng vào meter khai báo byte.
- Một nhóm dùng `outcome=ok`, nhóm khác dùng `outcome=success` cho cùng một ý nghĩa.
- Một điểm đo bỏ tag `format`, trong khi các điểm khác vẫn gắn tag đó cho cùng họ số liệu.

Giữ tập khóa tag và ý nghĩa của chúng nhất quán cho cùng họ meter giúp xuất dữ liệu và truy vấn đáng tin cậy. Một số hệ thống giám sát còn có ràng buộc riêng đối với schema nhãn; việc registry bộ nhớ chấp nhận một đăng ký chưa chứng minh mọi exporter đều chấp nhận cùng cấu trúc.

Nếu cần thay đơn vị đầu vào, ưu tiên chuẩn hóa về hợp đồng đang có khi ý nghĩa đại lượng không đổi. Nếu thay đổi thực sự không tương thích, thiết kế một tên hoặc hợp đồng mới rõ ràng và cập nhật các nơi dùng số liệu. Chỉ sửa `baseUnit` trong một lần gọi builder không chuyển dữ liệu đã ghi và không di chuyển lịch sử ở hệ thống giám sát.

## 9. Những lỗi dễ nhận ra từ hành vi đăng ký

| Dấu hiệu | Khả năng cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Hai biến counter có số tăng chung | Cùng tên và tag trong cùng registry | Xác nhận đó là tổng hợp có chủ ý hay ghi nhận hai lần |
| Đổi `baseUnit` nhưng không thấy meter mới | Đơn vị không tham gia khóa tên–tag | Thống nhất đơn vị hoặc thiết kế thay đổi hợp đồng rõ ràng |
| Giá trị lệch 1000 hoặc 1024 lần | Đơn vị đầu vào và hợp đồng không khớp | Chuyển đổi tại nơi nhận dữ liệu trước khi ghi |
| Có hai nhóm `SUCCESS` và `success` | Quy ước tag không thống nhất | Chuẩn hóa giá trị theo hợp đồng |
| Registry báo xung đột loại | Dùng cùng định danh cho counter và timer | Chọn tên hoặc các đại lượng đúng nghĩa; không dựa vào loại để tách khóa |
| Đầu ra ở hệ thống giám sát bị trùng hoặc bị từ chối | Các tên khác nhau cùng bị chuẩn hóa hoặc schema nhãn không phù hợp | Kiểm tra tên xuất, tag hiệu lực và yêu cầu của nơi nhận |
| Chỉ xem theo tên thấy số lớn hơn dự kiến | Kết quả gồm nhiều nhóm tag, nhất là ở endpoint tổng hợp | Lọc các chiều cần xem và kiểm tra ý nghĩa của phép cộng |
| Sau cấu hình filter không còn phân biệt kết quả | Một tag phân loại đã bị bỏ | Kiểm tra chủ ý của filter và thông tin cần giữ |

Để chẩn đoán, kiểm tra theo thứ tự: registry đang dùng, tên logic, tag tại điểm ghi, tag chung, filter, loại và đơn vị, rồi mới tới cách đổi tên khi xuất. Cách này giúp tránh sửa nhầm tên hoặc đơn vị trong khi nguyên nhân thực sự nằm ở một chiều phân loại đã bị thay đổi.

## 10. Thực hành

Thực hiện từng thay đổi trên một lần chạy mới của ví dụ và dự đoán kết quả trước khi chạy:

1. Đổi thứ tự `.tag(...)` trong lời gọi tạo `reordered`. `sameAfterTagReorder` vẫn là `true`, số thành công vẫn là 3.
2. Chỉ đổi `baseUnit("tasks")` thành `baseUnit("bytes")` trong phép thử `differentUnit`. Với cùng tên và tag, kết quả vẫn là cùng counter và đơn vị đã đăng ký trước vẫn là `jobs`. Hãy giải thích vì sao điều đó không cho phép trộn dữ liệu byte vào bộ đếm công việc.
3. Đổi tag của `reordered` sang `queue=import`. Nó trở thành một nhóm riêng: counter `success` ban đầu chỉ nhận một lần tăng, còn nhóm import nhận lượng tăng bằng 2.
4. Thay hai lần ghi thời gian bằng `record(1, TimeUnit.SECONDS)` và `record(500, TimeUnit.MILLISECONDS)`. Tổng mới là 1500 ms hoặc 1,5 giây; số lần là 2.
5. Truy vấn tất cả counter `batch.jobs.completed` của registry chính rồi cộng `count()`. Với chương trình nguyên bản, tổng là 4; không cộng thêm counter của `otherRegistry` nếu mục đích chỉ quan sát registry chính.
6. Trong một registry mới, cấu hình filter bỏ tag `outcome` trước khi tạo hai nhóm success và failure. Quan sát việc gộp counter, rồi xác định thông tin phân tích nào đã bị mất.

Khi tự kiểm chứng một điểm đo, hãy ghi lại cả tên, tập tag hiệu lực, loại công cụ, đơn vị đầu vào và registry chứa nó. Một giá trị số khớp dự đoán chỉ có ý nghĩa khi các thông tin đó cũng khớp hợp đồng.
