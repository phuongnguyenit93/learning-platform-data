# Phân biệt giá trị tích lũy, tốc độ thay đổi và giá trị tức thời

Một hệ thống xử lý báo cáo đang hiển thị ba con số: đã hoàn tất 50 công việc, tốc độ gần nhất là 0 công việc/giây và còn 3 công việc trong hàng đợi. Ba số này không mâu thuẫn. Chúng trả lời ba câu hỏi khác nhau về thời gian.

Để đọc đúng metrics, cần phân biệt **lượng đã tích lũy**, **lượng thay đổi trên một đơn vị thời gian** và **trạng thái được quan sát tại một thời điểm**. Nếu nhầm lẫn, bạn có thể coi một tổng rất lớn là tải hiện tại, coi dữ liệu bị thiếu là tốc độ bằng không hoặc dùng số lượng hàng đợi làm số công việc đã hoàn tất.

Bài này dùng một dòng thời gian và ví dụ Micrometer 1.13.0 để giải thích ba cách nhìn đó. Mã dùng Java 17, chạy được trên JDK 21 và không cần máy chủ giám sát để kiểm chứng các phép đo cơ bản.

## 1. Ba câu hỏi trước cùng một hệ thống

Giả sử một nhóm worker xử lý công việc từ hàng đợi `reports`:

| Câu hỏi | Đại lượng cần xem | Ví dụ | Đơn vị |
| --- | --- | --- | --- |
| Đã ghi nhận bao nhiêu công việc hoàn tất kể từ mốc bắt đầu của bộ đếm? | Giá trị tích lũy | 50 | Công việc |
| Trong khoảng đang xét, trung bình mỗi giây hoàn tất bao nhiêu? | Tốc độ thay đổi | 2 | Công việc/giây |
| Tại lúc quan sát, có bao nhiêu công việc đang chờ? | Giá trị tức thời của trạng thái | 3 | Công việc |

Giá trị tích lũy và giá trị hàng đợi có thể cùng đơn vị “công việc” nhưng khác ý nghĩa. Tốc độ lại có thêm thành phần “trên thời gian”. Vì vậy, không thể chỉ nhìn kiểu số hoặc nhãn đơn vị để biết một biểu đồ đang nói gì.

Đối với mỗi điểm đo, hãy xác định:

1. Sự kiện hoặc trạng thái nào làm số thay đổi?
2. Số được tính từ mốc nào hoặc trong khoảng nào?
3. Thời điểm quan sát có ý nghĩa gì?
4. Có khởi động lại, thay instance hoặc mất mẫu trong khoảng đang xét không?

## 2. Giá trị tích lũy: lượng đã được cộng dồn

Trong ví dụ, `Counter` ghi mỗi lần hoàn tất công việc. Nếu lần lượt có 30 rồi 20 công việc hoàn tất, bộ đếm tăng từ 0 lên 30 rồi 50.

```text
Lần ghi nhận thứ nhất: +30
Lần ghi nhận thứ hai:  +20
Tổng hiện tại:          50
```

Với counter tích lũy trong một vòng đời liên tục, đọc giá trị không làm số về 0. Không có công việc mới thì tổng giữ nguyên, chứ không tự giảm theo thời gian.

Micrometer cung cấp `Counter` cho các lượng tăng; khi quan sát hoạt động theo thời gian, tốc độ tăng thường giúp đánh giá tình hình hiện tại rõ hơn riêng tổng tuyệt đối. [Counter trong Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/counters.html).

### 2.1. Tổng lớn chưa nói hiện tại đang bận

Hai instance có thể cùng xử lý 2 công việc/giây, nhưng một instance đã chạy nhiều ngày còn instance kia vừa khởi động. Tổng từ lúc bộ đếm bắt đầu của chúng sẽ rất khác nhau.

Ngược lại, một instance đã ghi nhận hàng triệu công việc có thể đang không xử lý thêm công việc nào. Giá trị tổng không giảm nên một biểu đồ chỉ vẽ tổng vẫn nằm rất cao.

Khi muốn biết hoạt động gần đây, cần xét lượng tăng trong khoảng phù hợp. Khi cần kiểm tra tổng đã ghi nhận trong vòng đời đang xét, giá trị tích lũy vẫn hữu ích. Hai mục đích cần được tách rõ.

### 2.2. Mốc tích lũy không nhất thiết là toàn bộ lịch sử nghiệp vụ

Counter bộ nhớ có thể bắt đầu lại khi tiến trình khởi động lại, registry được tạo lại hoặc bộ đo được thay mới. Nó không mặc nhiên là sổ cái bền vững của toàn hệ thống.

Nếu một công việc được thử lại và mỗi lần thử đều được tăng counter, tổng đó là tổng các lần đã ghi theo quy tắc ấy. Muốn đếm công việc duy nhất hay lần thử, phải định nghĩa ngay ở điểm đo. Từ một con số tích lũy không thể tự suy ra quy tắc nghiệp vụ chưa được khai báo.

## 3. Tốc độ thay đổi: lượng tăng chia cho thời gian

Gọi `C(t)` là giá trị counter tích lũy tại thời điểm `t`. Khi hai mẫu thuộc cùng chuỗi, không có reset và thời gian tăng đúng, tốc độ trung bình trên khoảng được tính như sau:

```text
delta = C(t2) - C(t1)
elapsed = t2 - t1
average rate = delta / elapsed
```

Nếu thời gian tính bằng giây và counter tính bằng công việc, đơn vị kết quả là công việc/giây.

Ví dụ từ giây 10 đến giây 20:

```text
C(10) = 30
C(20) = 50
Lượng tăng = 50 - 30 = 20 công việc
Thời gian = 20 - 10 = 10 giây
Tốc độ trung bình = 20 / 10 = 2 công việc/giây
```

Đây không phải khẳng định cứ đúng mỗi giây có hai công việc hoàn tất. Hai mươi công việc có thể hoàn tất đều, dồn vào đầu khoảng hoặc thành một đợt ngắn ở cuối khoảng. Các mẫu biên không lưu được toàn bộ cách phân bố sự kiện bên trong.

### 3.1. Phân biệt lượng tăng và tốc độ

| Đại lượng | Giá trị trong ví dụ | Ý nghĩa |
| --- | --- | --- |
| Tổng tại giây 20 | 50 công việc | Lượng đã ghi từ mốc của bộ đếm |
| Lượng tăng từ giây 10 đến 20 | 20 công việc | Số tăng trong khoảng 10 giây |
| Tốc độ trung bình trong khoảng | 2 công việc/giây | Lượng tăng đã chuẩn hóa theo thời gian |

Một biểu đồ ghi “20 công việc trong 10 giây” không tương đương “20 công việc/giây”. Thiếu phép chia thời gian làm diễn giải lệch mười lần trong ví dụ này.

### 3.2. Cửa sổ đo quyết định câu hỏi

Tốc độ luôn cần một khoảng quan sát. Trong cùng dòng thời gian, tốc độ ở 10 giây gần nhất có thể bằng 0, trong khi tốc độ trung bình của 30 giây vẫn lớn hơn 0.

Cửa sổ ngắn phản ánh thay đổi gần đây rõ hơn nhưng thường dao động mạnh hơn. Cửa sổ dài tổng hợp nhiều thời gian hơn, làm các đợt ngắn bớt nổi bật. Chọn cửa sổ dựa trên câu hỏi vận hành và mật độ dữ liệu, không chỉ để đường biểu đồ trông mượt.

Nếu các khoảng có độ dài khác nhau, không lấy trung bình cộng các tốc độ rồi coi đó là tốc độ toàn khoảng. Ví dụ:

```text
10 giây đầu: 30 công việc -> 3 công việc/giây
20 giây tiếp: 20 công việc -> 1 công việc/giây
Toàn 30 giây: 50 / 30 -> khoảng 1,667 công việc/giây
```

Giá trị `(3 + 1) / 2 = 2` không phải tốc độ của toàn 30 giây. Cần lấy tổng lượng tăng chia tổng thời gian, hoặc tính trung bình có trọng số thời gian.

## 4. Giá trị tức thời: trạng thái tại lúc được quan sát

Độ dài hàng đợi là một trạng thái. Nó có thể tăng khi có công việc vào, giảm khi worker lấy công việc ra và giữ nguyên khi không thay đổi.

`Gauge` quan sát giá trị hiện tại của một đối tượng hoặc hàm. Trong ví dụ, một `AtomicInteger` giữ số công việc đang chờ, và gauge đọc số đó khi được hỏi. [Gauge trong Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/gauges.html).

### 4.1. Giá trị hiện tại không phải lượng tích lũy

Giả sử lần lượt quan sát hàng đợi dài 5, 8 rồi 3 công việc. Không được cộng `5 + 8 + 3` để kết luận đã có 16 công việc đi qua hàng đợi. Một công việc chờ lâu có thể xuất hiện trong nhiều lần quan sát.

Cũng không thể kết luận số công việc hoàn tất là `8 - 3 = 5`. Công việc có thể vừa được thêm vào và lấy ra trong khoảng; khi rời hàng đợi nó có thể mới bắt đầu xử lý, chưa hoàn tất.

Trong một mô hình hàng đợi đơn giản, thay đổi ròng của độ dài liên hệ với lượng vào và lượng rời hàng đợi:

```text
thay đổi độ dài = số vào hàng đợi - số rời hàng đợi
```

Muốn biết từng lượng vào và ra, cần đo chúng theo đúng sự kiện. Chỉ hai giá trị trạng thái ở đầu và cuối khoảng không đủ phân tách hai lượng đó.

### 4.2. Một đỉnh ngắn có thể không xuất hiện trong mẫu

Nếu trạng thái thay đổi từ 5 lên 100 rồi về 8 giữa hai lần thu thập, các mẫu chỉ có 5 và 8 sẽ không chứng minh được đỉnh 100 đã tồn tại.

Gauge không tự lưu toàn bộ lịch sử các lần gán. Tính lớn nhất của những mẫu đã thu thập cũng không bảo đảm bằng đỉnh thực tế nếu đỉnh xảy ra giữa các lần lấy mẫu.

Nếu cần ghi nhận các sự kiện ngắn hoặc giá trị đỉnh theo một chính sách cụ thể, phải chọn cơ chế thu thập phù hợp. Tăng tần suất lấy mẫu có thể giảm khả năng bỏ sót nhưng không biến một gauge thành nhật ký đầy đủ của mọi thay đổi.

### 4.3. “Tức thời” là ý nghĩa của mẫu, không phải bảo đảm không có độ trễ

Mẫu được đọc tại một thời điểm, sau đó còn có thể trải qua bước truyền, lưu và hiển thị. Giá trị đang thấy trên màn hình có thể là mẫu mới nhất đã nhận, không phải trạng thái chính xác ở thời điểm mắt bạn nhìn.

Một gauge cũng có thể quan sát một giá trị đã được thành phần khác tính toán, chẳng hạn một tốc độ trung bình có sẵn. Vì thế, loại công cụ và ý nghĩa đại lượng cần được xem cùng nhau. Trong bài này, gauge trực tiếp đọc **độ dài hàng đợi**, nên nó biểu diễn trạng thái chờ.

## 5. Đọc ba đại lượng trên cùng một dòng thời gian

Các mẫu dùng trong chương trình:

| Thời điểm | Tổng hoàn tất C(t) | Lượng tăng từ mẫu trước | Tốc độ trung bình từ mẫu trước | Hàng đợi Q(t) |
| --- | --- | --- | --- | --- |
| 0 giây | 0 | Chưa có khoảng trước | Chưa tính được | 5 |
| 10 giây | 30 | 30 | 3 công việc/giây | 8 |
| 20 giây | 50 | 20 | 2 công việc/giây | 3 |
| 30 giây | 50 | 0 | 0 công việc/giây | 3 |

Tại giây 30:

- `C(30)=50` cho biết tổng đã ghi nhận trong vòng đời của counter.
- Tốc độ trên khoảng 20–30 giây bằng 0 vì counter không tăng.
- `Q(30)=3` cho biết còn ba công việc đang chờ ở thời điểm lấy mẫu.

Không có mâu thuẫn giữa tổng hoàn tất cao, tốc độ gần nhất bằng 0 và hàng đợi chưa rỗng. Để biết nguyên nhân hàng đợi không giảm, cần thêm ngữ cảnh về worker, công việc mới, trạng thái xử lý hoặc lỗi. Ba số đo này hỗ trợ đặt câu hỏi, chưa tự chứng minh nguyên nhân.

## 6. Ví dụ Java có thể chạy

Chương trình tạo `Counter` tích lũy và `Gauge` trong `SimpleMeterRegistry`. Nó đọc các mẫu, rồi tính tốc độ từ các cặp mẫu bằng công thức đơn giản.

Các mốc 0, 10, 20 và 30 là **thời gian của kịch bản giả lập**, được truyền rõ vào bản ghi mẫu. Chương trình không đợi 30 giây thực và không đo tốc độ của máy đang chạy. Các lần hoàn tất và trạng thái hàng đợi là đầu vào để minh họa cách đọc số liệu, không phải mô phỏng đầy đủ bộ máy xử lý hàng đợi.

### 6.1. Phụ thuộc

Tạo thư mục thử nghiệm riêng:

```text
metric-time-semantics-demo/
├── pom.xml
└── MetricTimeSemanticsDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>metric-time-semantics-demo</artifactId>
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

Ví dụ cố định Micrometer 1.13.0 để kết quả có thể tái lập. Với dự án Spring Boot dùng tập phụ thuộc của Boot, giữ cơ chế quản lý phiên bản chung của dự án.

### 6.2. Mã đầy đủ

`MetricTimeSemanticsDemo.java`:

```java
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class MetricTimeSemanticsDemo {
    record Snapshot(long seconds, double completed, double queued) {
    }

    static final class WorkMetrics {
        private final AtomicInteger queueDepth = new AtomicInteger();
        private final Counter completed;
        private final Gauge queued;

        WorkMetrics(SimpleMeterRegistry registry) {
            completed = Counter.builder("worker.jobs.completed")
                    .tag("queue", "reports")
                    .register(registry);
            queued = Gauge.builder(
                            "worker.queue.depth", queueDepth, AtomicInteger::get)
                    .tag("queue", "reports")
                    .register(registry);
        }

        void complete(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            completed.increment(amount);
        }

        void setQueueDepth(int amount) {
            if (amount < 0) {
                throw new IllegalArgumentException("queue depth must be nonnegative");
            }
            queueDepth.set(amount);
        }

        Snapshot snapshot(long seconds) {
            return new Snapshot(seconds, completed.count(), queued.value());
        }
    }

    public static void main(String[] args) {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            WorkMetrics metrics = new WorkMetrics(registry);

            metrics.setQueueDepth(5);
            Snapshot s0 = metrics.snapshot(0);

            metrics.complete(30);
            metrics.setQueueDepth(100);
            metrics.setQueueDepth(8);
            Snapshot s10 = metrics.snapshot(10);

            metrics.complete(20);
            metrics.setQueueDepth(3);
            Snapshot s20 = metrics.snapshot(20);

            Snapshot s30 = metrics.snapshot(30);

            printSnapshot(s0);
            printSnapshot(s10);
            printSnapshot(s20);
            printSnapshot(s30);
            printRate(s0, s10);
            printRate(s10, s20);
            printRate(s20, s30);
            printRate(s0, s30);
        } finally {
            registry.close();
        }
    }

    static double averageRate(Snapshot from, Snapshot to) {
        long elapsed = to.seconds() - from.seconds();
        double delta = to.completed() - from.completed();
        if (elapsed <= 0 || delta < 0) {
            throw new IllegalArgumentException(
                    "Need increasing time and no counter reset");
        }
        return delta / elapsed;
    }

    private static void printSnapshot(Snapshot sample) {
        System.out.printf(Locale.ROOT,
                "t=%ds completed=%.0f queued=%.0f%n",
                sample.seconds(), sample.completed(), sample.queued());
    }

    private static void printRate(Snapshot from, Snapshot to) {
        System.out.printf(Locale.ROOT,
                "rate[%d,%d]=%.3f jobs/s%n",
                from.seconds(), to.seconds(), averageRate(from, to));
    }
}
```

Cách mã phản ánh các khái niệm:

1. `complete(amount)` tăng counter theo lượng công việc hoàn tất. Trong registry của ví dụ, các lần đọc không xóa tổng.
2. `setQueueDepth(amount)` cập nhật đối tượng trạng thái. `queued.value()` đọc giá trị mới nhất của đối tượng ấy.
3. Trước mẫu ở giây 10, mã gán hàng đợi bằng 100 rồi 8. Mẫu chỉ chứa 8; không có danh sách lịch sử 100 trong gauge.
4. `Snapshot` chứa thời điểm giả lập và các giá trị đã đọc. Chính tập mẫu này cho phép tính chênh lệch theo thời gian.
5. `averageRate(...)` chia lượng tăng cho số giây thực sự của khoảng. Nó từ chối khoảng thời gian không dương và chênh lệch counter âm.
6. `queueDepth` được giữ trong một trường của `WorkMetrics`. Đối tượng trạng thái cần sống cùng phép đo; gauge thường không giữ tham chiếu mạnh thay ứng dụng.

Trong ví dụ một luồng, các giá trị được điều khiển trước khi đọc. Trong hệ thống có nhiều luồng, hai phép đọc counter và gauge không mặc nhiên tạo một ảnh chụp nguyên tử của toàn bộ nghiệp vụ. Cần cân nhắc độ nhất quán phù hợp với mục đích quan sát.

Hàm `averageRate(...)` chỉ minh họa hai mẫu của cùng bộ đếm tích lũy liên tục. Nó không lưu lịch sử, không phát hiện mọi dạng reset và không thay thế thuật toán truy vấn của một hệ thống giám sát.

### 6.3. Biên dịch và chạy

Cần Maven và JDK 17 trở lên. Ví dụ cũng chạy với JDK 21. Tải các thư viện vào `lib`:

```shell
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
```

PowerShell/Windows:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MetricTimeSemanticsDemo.java
java -cp "out;lib/*" MetricTimeSemanticsDemo
```

Linux/macOS:

```shell
mkdir -p out
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out MetricTimeSemanticsDemo.java
java -cp "out:lib/*" MetricTimeSemanticsDemo
```

Dấu phân cách classpath là `;` trên Windows và `:` trên Linux/macOS. Lần tải phụ thuộc đầu tiên cần truy cập kho Maven nếu máy chưa có thư viện.

Stdout:

```text
t=0s completed=0 queued=5
t=10s completed=30 queued=8
t=20s completed=50 queued=3
t=30s completed=50 queued=3
rate[0,10]=3.000 jobs/s
rate[10,20]=2.000 jobs/s
rate[20,30]=0.000 jobs/s
rate[0,30]=1.667 jobs/s
```

`Locale.ROOT` giúp định dạng số ổn định. Dòng cuối làm tròn `50/30` đến ba chữ số sau dấu thập phân; nó không khẳng định tốc độ trong mọi giây đều bằng `1.667`.

## 7. Reset, thiếu mẫu và cách ghép nhiều instance

### 7.1. Counter giảm không tự có nghĩa là tốc độ âm

Xét chuỗi có khởi động lại:

| Thời điểm | Counter | Sự kiện đã biết trong thí nghiệm |
| --- | --- | --- |
| 30 giây | 50 | Trước khởi động lại |
| 34 giây | 54 | Mẫu cuối trước reset |
| 35 giây | 0 | Counter mới bắt đầu |
| 40 giây | 8 | Sau khởi động lại |

Phép trừ thẳng hai biên 30 và 40 giây cho `(8 - 50) / 10 = -4,2` công việc/giây. Điều đó không mô tả một lượng công việc hoàn tất âm; hai mẫu nằm qua mốc reset.

Nếu đã biết đầy đủ các mốc như bảng, với 54 là giá trị cuối trước reset và 0 là giá trị đầu sau reset, tổng lượng tăng trong khoảng là `(54 - 50) + (8 - 0) = 12`. Nếu chỉ biết hai mẫu 50 và 8, không thể tự phục hồi chính xác mọi sự kiện đã xảy ra trước lúc tiến trình dừng.

Không sửa vấn đề bằng cách ép mọi chênh lệch âm thành 0. Cách đó có thể che mất hoạt động thật. Cũng không suy ra rằng chênh lệch không âm chứng minh chưa reset: counter có thể reset rồi tăng vượt giá trị mẫu cũ trước lần quan sát tiếp theo.

### 7.2. Tốc độ bằng 0 khác với không đủ dữ liệu

Để tính chênh lệch đơn giản, cần ít nhất hai mẫu hợp lệ với khoảng thời gian dương. Một giá trị duy nhất bằng 50 không cho biết tốc độ của 10 giây trước.

- Hai mẫu hợp lệ bằng nhau trong một khoảng dương, không reset: lượng tăng quan sát được bằng 0.
- Thiếu mẫu, mất liên lạc hoặc chưa có đủ lịch sử: chưa có cơ sở để khẳng định tốc độ bằng 0.
- Mẫu rất cũ: có thể không còn mô tả hoạt động gần đây dù vẫn còn một giá trị để hiển thị.

Khoảng cách lấy mẫu lớn có thể giữ được tổng lượng tăng của một counter liên tục nhưng làm mất chi tiết các đợt hoạt động bên trong. Với gauge, một đỉnh đã xuất hiện rồi biến mất giữa hai mẫu có thể bị bỏ sót hoàn toàn.

### 7.3. Tính tốc độ cho từng chuỗi trước khi gộp

Mỗi instance có thể có vòng đời và reset riêng. Vì vậy, cần giữ đủ chiều nhận diện để công cụ truy vấn xử lý từng chuỗi đúng trước khi tổng hợp.

Ví dụ trong 10 giây, instance A hoàn tất thêm 30 công việc và B thêm 20 công việc. Nếu hai nhóm không ghi trùng cùng một sự kiện và cùng định nghĩa đại lượng, tốc độ tổng là `3 + 2 = 5` công việc/giây.

Nhưng cộng các counter thô qua nhiều instance rồi mới suy chênh lệch có thể che một reset: một instance giảm trong khi instance khác tăng, khiến tổng trông vẫn tăng bình thường. Mốc khởi đầu và vòng đời riêng đã bị mất trước khi có cơ hội xử lý.

Với gauge, cách gộp phụ thuộc ý nghĩa. Có thể cộng số công việc ở các hàng đợi rời nhau để xem tổng. Không cộng hai bản sao cùng quan sát một hàng đợi chia sẻ rồi coi đó là hai hàng đợi độc lập.

## 8. Phân biệt chu kỳ lấy mẫu, cửa sổ truy vấn và kiểu xuất

Ba khoảng thời gian sau có thể khác nhau:

| Khoảng thời gian | Vai trò | Ví dụ minh họa |
| --- | --- | --- |
| Chu kỳ thu thập | Khi nào hệ thống lấy một mẫu mới | Mỗi 15 giây |
| Cửa sổ tính tốc độ | Xét lượng thay đổi trong đoạn lịch sử nào | Năm phút gần nhất |
| Bước hiển thị hoặc đánh giá | Khi nào tính một điểm kết quả mới | Mỗi 30 giây |

Cửa sổ năm phút không có nghĩa là chỉ lấy dữ liệu mỗi năm phút. Một điểm trên biểu đồ cũng có thể là kết quả tổng hợp từ nhiều mẫu, không phải một sự kiện vừa xảy ra tại đúng điểm đó.

### 8.1. Counter tích lũy và counter theo kỳ

Micrometer hỗ trợ các hệ thống tính tốc độ ở phía máy chủ lẫn các hệ thống cần tổng hợp trước ở phía ứng dụng. Một số implementation dùng giá trị tích lũy; một số dùng kỳ tổng hợp (step). [Cách Micrometer tổng hợp tốc độ](https://docs.micrometer.io/micrometer/reference/concepts/rate-aggregation.html).

Trong cơ chế step, lượng tăng được tích lũy cho kỳ hiện tại; khi sang kỳ tiếp theo, phía đọc có thể nhận lượng của kỳ vừa hoàn tất. Ví dụ, 30 lần tăng trong một kỳ 10 giây tương ứng 3 lần/giây. Kỳ kế không có lần tăng thì lượng của kỳ đó bằng 0.

Chuỗi `30, 0` theo các kỳ hoàn tất không phải là counter tích lũy đã bị reset và cũng không phải vì vậy mà thành gauge về hàng đợi. Nó vẫn mô tả sự kiện đếm, nhưng cơ sở thời gian của số liệu là từng kỳ.

Kiểm tra implementation và định dạng xuất để biết giá trị đang nhận là tổng từ mốc bắt đầu, lượng trong kỳ hay tốc độ đã chuẩn hóa. Nếu dữ liệu đã là công việc/giây, không tiếp tục tính tốc độ của nó rồi gọi kết quả là công việc/giây. Nếu dữ liệu là lượng trong kỳ, cần hiểu độ dài kỳ và cách nơi nhận tổng hợp.

### 8.2. Đọc snapshot của Actuator

Endpoint `metrics` của Actuator giúp kiểm tra số đo đang có theo tên và tag, khi đã cấu hình cho phép truy cập. [Metrics trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

Trong ứng dụng dùng counter tích lũy như ví dụ, một lần đọc có `COUNT=50` chưa phải kết quả “50 công việc/giây”. Cần lịch sử và mốc thời gian để tính tốc độ.

Một lần gọi endpoint kiểm tra cũng không tự tạo kho lưu lịch sử. Muốn theo dõi các cửa sổ thời gian qua nhiều lần thu thập, cần thành phần lưu và truy vấn phù hợp. Chương trình dòng lệnh trong bài không mở HTTP server.

## 9. Minh họa cách hỏi trong Prometheus

Giả sử hệ thống đã xuất counter thành `worker_jobs_completed_total` và gauge thành `worker_queue_depth`. Đây là tên đầu ra dùng để minh họa truy vấn; cần kiểm tra tên thực tế của registry đang dùng.

```promql
sum by (queue) (rate(worker_jobs_completed_total[5m]))
```

Truy vấn tốc độ trung bình theo giây; tính từng chuỗi trước khi gộp để xử lý reset.

```promql
increase(worker_jobs_completed_total[5m])
```

Truy vấn lượng tăng trong cửa sổ. Prometheus có ngoại suy, nên kết quả có thể không nguyên dù counter tăng theo số nguyên.

```promql
worker_queue_depth
```

Đọc mẫu gauge mới nhất theo quy tắc truy vấn. `irate(...)` dùng hai mẫu cuối để ước lượng tốc độ; tên gọi “instant” không biến nó thành gauge trạng thái hoặc phép đo tại một thời điểm vô hạn nhỏ. [Các hàm truy vấn Prometheus](https://prometheus.io/docs/prometheus/latest/querying/functions/).

Không dùng `rate(...)` của counter để diễn giải độ dài hàng đợi giảm. Muốn đo xu hướng gauge, phải dùng phép tính phù hợp với gauge và hiểu đó là thay đổi ròng của trạng thái, không phải số công việc đã hoàn tất.

## 10. Những cách đọc sai thường gặp

| Cách đọc sai | Vì sao sai | Cách kiểm tra phù hợp |
| --- | --- | --- |
| Tổng counter cao nghĩa là hiện tại rất bận | Tổng phụ thuộc cả lịch sử đã tích lũy | Xem lượng tăng và tốc độ trong cửa sổ phù hợp |
| Counter không tăng thì giá trị phải về 0 | Bộ đếm tích lũy giữ tổng khi không có lần ghi mới | Phân biệt tổng và tốc độ |
| Hàng đợi giảm 5 nghĩa là hoàn tất 5 công việc | Đó là thay đổi ròng, còn có lượng vào và thời điểm rời hàng đợi | Đo các sự kiện theo từng giai đoạn cần biết |
| Cộng các mẫu gauge cho ra tổng số sự kiện | Một đối tượng có thể xuất hiện ở nhiều mẫu | Dùng phép đếm sự kiện khi cần tổng lượng |
| Không có kết quả tốc độ nghĩa là hoạt động bằng 0 | Có thể chưa đủ hoặc mất mẫu | Kiểm tra dữ liệu, độ mới và khả năng truy cập |
| Mọi counter đều trả tổng từ khi khởi động | Có implementation và nơi xuất theo kỳ | Kiểm tra cơ sở thời gian của giá trị |
| Mọi giá trị giảm đều là gauge | Counter có thể reset hoặc số liệu đang theo kỳ | Xét ngữ nghĩa và vòng đời thay vì chỉ hình dạng đường |
| Đường gauge không có đỉnh nghĩa là chưa từng có đỉnh | Đỉnh có thể xảy ra giữa các lần lấy mẫu | Đánh giá độ phân giải và cơ chế ghi nhận |
| Tốc độ ngắn hạn và dài hạn phải giống nhau | Chúng tổng hợp các khoảng khác nhau | Ghi rõ cửa sổ và câu hỏi của từng biểu đồ |

Để so sánh hai biểu đồ, cần cùng đại lượng, đơn vị, nhóm tag, khoảng thời gian và cách tổng hợp. Hai biểu đồ đều mang chữ “count” chưa đủ để kết luận chúng phải trùng nhau.

## 11. Thực hành kiểm chứng

Thay đổi từng điều trong ví dụ, chạy lại và đối chiếu với dự đoán:

1. Đổi lượng hoàn tất ở khoảng 10–20 giây từ 20 thành 40. Tổng ở giây 20 và 30 thành 70; tốc độ khoảng 10–20 thành 4 công việc/giây, còn khoảng 20–30 vẫn bằng 0.
2. Giữ nguyên lượng tăng nhưng đổi mốc `s20` thành 25 và `s30` thành 35. Khoảng 10–25 dài 15 giây nên tốc độ là `20/15`, không còn 2 công việc/giây. Dữ liệu đầu vào phải phản ánh đúng kịch bản thời gian mới.
3. Đổi lần gán đỉnh hàng đợi từ 100 thành 1000 nhưng vẫn gán lại 8 trước mẫu `s10`. Stdout về hàng đợi không thay đổi; hãy chỉ ra dữ liệu nào đã không được lưu thành mẫu.
4. Cho hai mẫu có cùng thời điểm vào `averageRate(...)`. Hàm báo lỗi thay vì chia cho 0; một khoảng dương là điều kiện của phép tính đang dùng.
5. Tạo một registry mới rồi tăng counter từ 0 lên 4. So sánh với mẫu 50 của registry cũ; không lấy chênh lệch hai vòng đời làm tốc độ hoàn tất thông thường.
6. So sánh hàng đợi không đổi bằng 3 với counter không đổi bằng 50. Trường hợp đầu nói về trạng thái chờ; trường hợp sau cho lượng tăng bằng 0 trong một khoảng hợp lệ. Chúng không cung cấp cùng thông tin.

Khi trình bày một kết quả, ghi đủ dạng đại lượng và cơ sở thời gian: “tổng 50 công việc trong vòng đời bộ đếm này”, “trung bình 2 công việc/giây trong khoảng 10–20 giây”, hoặc “3 công việc đang chờ tại mẫu giây 30”. Cách diễn đạt cụ thể giúp người đọc không phải tự đoán ý nghĩa của một con số.
