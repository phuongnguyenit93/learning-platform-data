# Theo dõi dung lượng và phần đĩa còn trống

Một ứng dụng có thể vẫn nhận yêu cầu bình thường nhưng sắp không còn chỗ để ghi log, tạo tệp tạm hoặc xuất báo cáo. Theo dõi dung lượng đĩa giúp biết nơi lưu dữ liệu còn khả năng chứa thêm bao nhiêu, thay vì chỉ chờ một thao tác ghi thất bại.

Trong Spring Boot Actuator, các số đo `disk.total` và `disk.free` cho biết dung lượng liên quan tới hệ thống tệp (filesystem) chứa đường dẫn được theo dõi. Điểm quyết định là **đường dẫn nào đang được đo và số “còn trống” được hiểu theo API nào**. Đây không phải phép cộng dung lượng mọi ổ vật lý trên máy, cũng không phải phép đo kích thước một thư mục.

Bài này dùng hành vi của Spring Boot 3.3.0 và Micrometer 1.13.0 để giải thích cấu hình, truy vấn và cách đọc đúng số liệu. Ví dụ Java dùng mức ngôn ngữ Java 17, chạy được trên JDK 21 và có cả chế độ dữ liệu mẫu lẫn đọc filesystem thật.

## 1. Đường dẫn là điểm bắt đầu của phép đo

Giả sử ứng dụng ghi báo cáo vào `/data/reports`. Thư mục này nằm trên một filesystem có tổng dung lượng 100 GiB và còn 20 GiB khả dụng cho JVM.

Các con số đó nói về filesystem chứa đường dẫn. Chúng không nói rằng:

- Thư mục báo cáo đang chứa đúng 80 GiB tệp.
- Mỗi thư mục con có riêng 100 GiB dung lượng.
- Toàn bộ máy chủ chỉ có một ổ 100 GiB.
- Ứng dụng chắc chắn ghi thêm được đúng 20 GiB trong mọi điều kiện.

Đường dẫn của ứng dụng có thể nằm trên filesystem gốc, một vùng lưu trữ (volume) được gắn thêm, ổ mạng hoặc một vùng lưu trữ khác theo cấu hình môi trường. Vì vậy, cần bắt đầu từ nơi ứng dụng thực sự ghi dữ liệu.

Spring Boot tự cấu hình các system metrics trong đó có nhóm tên `disk.`. Micrometer cung cấp bộ đăng ký phép đo (binder) `DiskSpaceMetrics` để đăng ký các phép đo dung lượng cho một đường dẫn. [System metrics trong Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html), [Disk Space Metrics của Micrometer](https://docs.micrometer.io/micrometer/reference/reference/system.html).

## 2. Hai meter cần đọc

| Meter | Cơ sở đọc trong Micrometer 1.13.0 | Đơn vị | Ý nghĩa |
| --- | --- | --- | --- |
| `disk.total` | `File.getTotalSpace()` | Byte | Tổng dung lượng của phân vùng/filesystem được đường dẫn xác định theo cách JVM và hệ điều hành nhìn thấy |
| `disk.free` | `File.getUsableSpace()` | Byte | Lượng dung lượng khả dụng cho JVM theo kết quả API |

Hai meter là `Gauge`: chúng đọc trạng thái tại thời điểm quan sát. Dung lượng khả dụng có thể tăng khi dữ liệu được giải phóng, giảm khi có ghi mới và thay đổi do hoạt động của cả ứng dụng lẫn tiến trình khác.

Không dùng các số này như counter tích lũy. Đĩa còn 20 GiB rồi còn 18 GiB không có nghĩa cần tính một “counter reset”; đó là thay đổi của trạng thái lưu trữ.

### 2.1. disk.free dùng usable space

Tên có chữ `free`, nhưng trong phần hiện thực đang xét, nguồn dữ liệu là `getUsableSpace()`, không phải `getFreeSpace()`.

Java phân biệt dung lượng chưa được cấp phát với lượng được báo là khả dụng cho JVM. Khi có thể, `getUsableSpace()` xét thêm các giới hạn như quyền ghi và hạn chế của hệ điều hành. Kết quả vẫn là thông tin tại thời điểm đọc, không bảo đảm mọi thao tác ghi sau đó sẽ thành công. [API File của JDK 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/File.html).

Do đó, hai công cụ cùng nói về “đĩa còn trống” có thể đưa ra số khác nhau nếu chúng dùng khái niệm hoặc phạm vi khác nhau. Trước khi cho rằng số liệu sai, kiểm tra filesystem, quyền của tiến trình, đơn vị hiển thị và định nghĩa “available” của từng công cụ.

### 2.2. Không suy ra kích thước thư mục

`disk.total` không cộng kích thước từng tệp dưới đường dẫn. Một thư mục rất nhỏ và một thư mục rất lớn trên cùng filesystem có thể cho cùng dung lượng tổng và khả dụng.

Muốn biết thư mục nào đang chiếm dung lượng, cần một phép khảo sát khác. Không dùng cặp metrics này để khẳng định riêng thư mục log, báo cáo hoặc tệp tạm đã sử dụng bao nhiêu.

## 3. Bật tích hợp và chọn nơi cần theo dõi

Trong một dự án Spring Boot đã có cơ chế quản lý phụ thuộc của Boot, đưa starter Actuator vào cấu hình build. Ví dụ trích từ Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Đây là khai báo cho dự án Spring Boot hiện có, không phải toàn bộ một tệp build độc lập. Khi tự cấu hình metrics và registry phù hợp hoạt động, các binder hệ thống được đăng ký.

### 3.1. Giá trị mặc định của đường dẫn

Trong Spring Boot 3.3.0, `management.metrics.system.diskspace.paths` mặc định là danh sách chứa `.`. Đó là đường dẫn tương đối theo thư mục làm việc của tiến trình, không mặc nhiên là nơi chứa mọi dữ liệu nghiệp vụ.

Thay đổi cách chạy JAR, thư mục làm việc của service hoặc cấu hình container có thể khiến `.` trỏ tới một nơi khác. Không suy ra đường dẫn mặc định từ vị trí tệp mã nguồn trong repository.

### 3.2. Cấu hình rõ đường dẫn

Ví dụ cho ứng dụng web trên môi trường có thư mục `/data/reports` tồn tại:

```yaml
management:
  metrics:
    system:
      diskspace:
        paths:
          - /data/reports
  endpoints:
    web:
      exposure:
        include: health,metrics
```

`management.metrics.system.diskspace.paths` là danh sách các đường dẫn cần báo số đo. Cấu hình không tạo thư mục, không gắn volume và không cấp thêm dung lượng. [Danh mục thuộc tính Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html).

Trên Windows, có thể dùng một đường dẫn tuyệt đối của môi trường đó, chẳng hạn `"D:/data/reports"`. Tên trong ví dụ chỉ minh họa cú pháp; cần thay bằng đường dẫn thực sự có trên máy chạy ứng dụng.

Nếu cần nhiều nơi:

```yaml
management:
  metrics:
    system:
      diskspace:
        paths:
          - /data/reports
          - /var/log/report-service
```

Đây là một lựa chọn cấu hình khác cho cùng thuộc tính. Hai đường dẫn không tự có nghĩa là hai filesystem độc lập. Kiểm tra quan hệ lưu trữ của chúng trước khi cộng số liệu.

Giữ danh sách đường dẫn ổn định theo nơi lưu trữ cần quản lý. Không tạo một binder mới cho từng tệp tải lên hoặc từng yêu cầu chỉ để đo cùng filesystem.

## 4. Đọc tên, đơn vị và tag path

Trong ứng dụng web có Actuator được cho phép truy cập, kiểm tra các tên:

```http
GET /actuator/metrics/disk.total
GET /actuator/metrics/disk.free
```

Phản hồi cho biết các số đo và `availableTags`. Trong binder đang xét, tag `path` chứa chuỗi đường dẫn tuyệt đối của đối tượng `File` được dùng để đăng ký.

Với nhiều đường dẫn, truy vấn chỉ theo tên có thể gộp các gauge. Muốn xem một nơi cụ thể, dùng chính giá trị `path` mà ứng dụng báo.

Ví dụ nếu tag hiện có đúng bằng `/data/reports`:

```shell
curl --get "http://localhost:8080/actuator/metrics/disk.free" --data-urlencode "tag=path:/data/reports"
curl --get "http://localhost:8080/actuator/metrics/disk.total" --data-urlencode "tag=path:/data/reports"
```

Lấy cùng một tập tag cho cả tử số và mẫu số khi tính tỷ lệ. Không lấy `disk.free` của nơi này chia cho `disk.total` của nơi khác.

Các đường dẫn tương đương ở mức filesystem có thể có chuỗi biểu diễn khác nhau. Giá trị mặc định `.` hoặc đường dẫn đi qua liên kết cũng có thể làm nhãn không giống cách bạn tự viết. Hãy đọc `availableTags`, không đoán nhãn hoặc tự rút gọn chuỗi trước khi lọc.

Trên Windows, dùng mã hóa URL như ví dụ giúp giữ nguyên dấu hai chấm của ký tự ổ đĩa và các ký tự trong đường dẫn. Nếu shell dùng một alias khác cho `curl`, gọi `curl.exe` với các đối số tương ứng.

## 5. Tính GiB và tỷ lệ còn khả dụng

Với hai mẫu hợp lệ của cùng filesystem:

```text
free GiB = disk.free / 1.073.741.824
free % = 100 × disk.free / disk.total
```

1 GiB bằng `1024 × 1024 × 1024` byte. 1 GB theo hệ thập phân bằng một tỷ byte. Hai cách hiển thị không cho cùng giá trị số; hãy ghi rõ đơn vị khi so sánh.

Ví dụ có tổng 100 GiB, còn khả dụng 20 GiB:

| Đại lượng | Kết quả | Cách hiểu |
| --- | --- | --- |
| `disk.total` | 107.374.182.400 byte | Tổng của filesystem đang đo |
| `disk.free` | 21.474.836.480 byte | Khả dụng theo API cho JVM |
| Còn khả dụng | 20 GiB | Cùng lượng ở đơn vị dễ đọc |
| Tỷ lệ còn khả dụng | 20% | 20/100 |
| Tổng trừ phần khả dụng | 80 GiB | Phần không được phản ánh là khả dụng cho JVM |

### 5.1. total - usable không luôn là kích thước tệp đã dùng

Nếu tổng là 100 GiB, lượng chưa cấp phát là 30 GiB nhưng lượng khả dụng cho JVM chỉ là 20 GiB, thì `total - usable` là 80 GiB. Con số đó không đồng nghĩa có đúng 80 GiB nội dung tệp của ứng dụng.

Phần chênh có thể liên quan dữ liệu đã cấp phát và những phần không khả dụng theo giới hạn của hệ thống. Vì vậy, khi dùng `100 - free %`, nên diễn giải đúng theo định nghĩa usable, thay vì gọi đó là phần trăm dung lượng riêng ứng dụng đã chiếm.

### 5.2. Xử lý mẫu không hợp lệ

Chỉ tính tỷ lệ khi tổng lớn hơn 0, các giá trị hữu hạn và khoảng số hợp lý. `total=0`, `NaN` hoặc không có meter không nên bị biến thành “đĩa còn 0%” hoặc “đĩa còn 100%”.

Java có thể trả về 0 khi không xác định được thông tin về phân vùng. Khi `free=0`, cần xem thêm đường dẫn, quyền và trạng thái filesystem để phân biệt hết chỗ với việc thông tin không đọc được.

Hai phép đọc total và usable không phải một giao dịch đọc nguyên tử của toàn bộ hệ thống lưu trữ. Nếu có thay đổi mount hoặc trạng thái bất thường giữa các lần đọc, cần kiểm tra tính hợp lệ của mẫu trước khi diễn giải.

## 6. Ví dụ Java: số liệu cố định và đọc filesystem thật

Chương trình dùng chính `DiskSpaceMetrics` của Micrometer. Nó có hai chế độ:

- `--sample`: cung cấp một đối tượng `File` giả lập để đầu ra cố định, có thể đối chiếu phép tính và phương thức mà binder đọc.
- Một đường dẫn thực hoặc không truyền đối số: đọc thông tin filesystem của đường dẫn; mặc định là thư mục làm việc hiện tại.

Chế độ mẫu không tạo tệp, không cấp phát một volume 100 GiB và không mô tả máy đang chạy. Chế độ thật cũng chỉ đọc thông tin dung lượng, không ghi dữ liệu thử để làm đầy đĩa.

### 6.1. Chuẩn bị

Tạo một thư mục thử nghiệm riêng:

```text
disk-space-metrics-demo/
├── pom.xml
└── DiskSpaceMetricsDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>disk-space-metrics-demo</artifactId>
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

Ví dụ độc lập cố định Micrometer 1.13.0. Trong dự án Spring Boot, tiếp tục dùng cơ chế quản lý phiên bản chung của Boot.

### 6.2. Mã nguồn

`DiskSpaceMetricsDemo.java`:

```java
import java.io.File;
import java.util.Locale;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.binder.system.DiskSpaceMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

public class DiskSpaceMetricsDemo {
    static final long GIB = 1024L * 1024 * 1024;

    static final class SampleFile extends File {
        SampleFile() {
            super("sample-volume");
        }

        @Override
        public long getTotalSpace() {
            return 100 * GIB;
        }

        @Override
        public long getUsableSpace() {
            return 20 * GIB;
        }

        @Override
        public long getFreeSpace() {
            return 30 * GIB;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 1) {
            throw new IllegalArgumentException("Use --sample or one existing path");
        }
        boolean sample = args.length == 1 && args[0].equals("--sample");
        File path = sample ? new SampleFile()
                : new File(args.length == 0 ? "." : args[0]).getCanonicalFile();
        if (!sample && !path.exists()) {
            throw new IllegalArgumentException("Path must exist: " + path);
        }

        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        try {
            new DiskSpaceMetrics(path).bindTo(registry);
            String pathTag = path.getAbsolutePath();
            Gauge totalGauge = registry.get("disk.total")
                    .tag("path", pathTag).gauge();
            Gauge freeGauge = registry.get("disk.free")
                    .tag("path", pathTag).gauge();

            double total = totalGauge.value();
            double usable = freeGauge.value();
            double percent = usablePercent(total, usable);

            System.out.println("mode=" + (sample ? "sample" : "real"));
            if (!sample) {
                System.out.println("path=" + pathTag);
            }
            System.out.printf(Locale.ROOT, "disk.total=%.0f bytes%n", total);
            System.out.printf(Locale.ROOT, "disk.free=%.0f bytes%n", usable);
            System.out.printf(Locale.ROOT,
                    "freeGiB=%.3f freePercent=%.3f%n",
                    usable / GIB, percent);
            System.out.printf(Locale.ROOT,
                    "totalMinusUsableGiB=%.3f%n", (total - usable) / GIB);
            System.out.printf(Locale.ROOT,
                    "type=%s unit=%s pathTagMatches=%s%n",
                    freeGauge.getId().getType(),
                    freeGauge.getId().getBaseUnit(),
                    pathTag.equals(freeGauge.getId().getTag("path")));
        } finally {
            registry.close();
        }
    }

    static double usablePercent(double total, double usable) {
        if (!Double.isFinite(total) || !Double.isFinite(usable)
                || total <= 0 || usable < 0 || usable > total) {
            throw new IllegalArgumentException("Invalid disk-space sample");
        }
        return 100.0 * usable / total;
    }
}
```

Các chi tiết cần theo dõi:

1. `DiskSpaceMetrics` đăng ký hai gauge. Mã tra cứu chúng bằng cả tên và tag `path`, tránh lấy lẫn nhóm.
2. `SampleFile` khai báo total là 100 GiB, usable là 20 GiB và free theo `getFreeSpace()` là 30 GiB. Đầu ra `disk.free` vẫn là 20 GiB vì binder dùng usable.
3. `usablePercent(...)` không chia khi total không dương hoặc mẫu không hợp lệ. Nó không che trường hợp thiếu dữ liệu bằng một tỷ lệ có vẻ hợp lệ.
4. Tên `totalMinusUsableGiB` giữ rõ ý nghĩa phép trừ, không gọi đó là kích thước chính xác của các tệp đã sử dụng.
5. Nhánh đọc thật dùng `getCanonicalFile()` để chuẩn hóa đường dẫn của chương trình. Với binder tự cấu hình của một ứng dụng khác, vẫn đọc tag thực tế thay vì giả định chuỗi nhãn phải giống cách chuẩn hóa này.
6. `Locale.ROOT` giữ cách định dạng số ổn định. Registry do chương trình tạo được đóng trong `finally`.

### 6.3. Biên dịch và chạy chế độ mẫu

Cần Maven và JDK 17 trở lên. Với JDK 21 vẫn biên dịch ở mức Java 17 bằng `--release 17`.

Tải phụ thuộc vào `lib`:

```shell
mvn -q dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=lib
```

PowerShell/Windows:

```powershell
New-Item -ItemType Directory -Path out -Force | Out-Null
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out DiskSpaceMetricsDemo.java
java -cp "out;lib/*" DiskSpaceMetricsDemo --sample
```

Linux/macOS:

```shell
mkdir -p out
javac -encoding UTF-8 --release 17 -cp "lib/*" -d out DiskSpaceMetricsDemo.java
java -cp "out:lib/*" DiskSpaceMetricsDemo --sample
```

Classpath dùng dấu `;` trên Windows và `:` trên Linux/macOS. Lần tải đầu cần mạng nếu máy chưa có các thư viện.

Stdout cố định của chế độ mẫu:

```text
mode=sample
disk.total=107374182400 bytes
disk.free=21474836480 bytes
freeGiB=20.000 freePercent=20.000
totalMinusUsableGiB=80.000
type=GAUGE unit=bytes pathTagMatches=true
```

Đầu ra xác nhận tên, kiểu gauge, đơn vị byte và phép lọc theo path. Nó cũng minh họa vì sao không dùng giá trị 30 GiB của `getFreeSpace()` làm kết quả dự đoán cho `disk.free`.

### 6.4. Chạy chế độ thật

Với một đường dẫn thực trên Windows:

```powershell
java -cp "out;lib/*" DiskSpaceMetricsDemo "D:/data/reports"
```

Với một đường dẫn thực trên Linux/macOS:

```shell
java -cp "out:lib/*" DiskSpaceMetricsDemo /data/reports
```

Hoặc truyền `.` để đọc filesystem của thư mục làm việc. Đường dẫn trong lệnh phải tồn tại; ví dụ không tự tạo nó.

Đầu ra thật có thêm dòng `path=...`. Dung lượng phụ thuộc hệ thống và có thể thay đổi giữa các lần chạy, nên không có một bộ số cố định đúng cho mọi máy. So sánh tên, đơn vị, đường dẫn và điều kiện hợp lệ trước khi so sánh giá trị.

Chương trình độc lập không chạy HTTP server. Muốn truy vấn qua `/actuator/metrics/...`, dùng một ứng dụng web có Actuator như phần cấu hình ở trên.

## 7. Tránh cộng nhầm nhiều đường dẫn

### 7.1. Hai đường dẫn có thể cùng một filesystem

Giả sử `/data/reports` và `/data/archive` cùng nằm trên filesystem tổng 100 GiB, còn khả dụng 20 GiB. Đăng ký cả hai đường dẫn có thể tạo hai nhóm tag:

| path | disk.total | disk.free |
| --- | --- | --- |
| `/data/reports` | 100 GiB | 20 GiB |
| `/data/archive` | 100 GiB | 20 GiB |

Truy vấn gộp các gauge theo tên có thể cho tổng 200 GiB và khả dụng 40 GiB. Điều đó không làm xuất hiện một filesystem mới; dung lượng của cùng nơi lưu trữ đã được quan sát qua hai đường dẫn.

Trong Spring Boot 3.3.0, binder nhiều đường dẫn đăng ký phép đo cho từng phần tử cấu hình. Không dựa vào danh sách paths để mặc định đã có bước nhận diện và loại các filesystem trùng.

Chọn tag cụ thể khi kiểm tra. Nếu cần tổng hợp dung lượng thực tế, xác định các vùng lưu trữ độc lập và cách tránh đếm lặp trước khi cộng.

### 7.2. Tổng tỷ lệ có thể che một nơi sắp hết chỗ

Ngay cả khi hai filesystem độc lập, một tỷ lệ gộp có thể che vấn đề cục bộ:

| Filesystem | Tổng | Còn khả dụng | Tỷ lệ còn khả dụng |
| --- | --- | --- | --- |
| A | 100 GiB | 1 GiB | 1% |
| B | 900 GiB | 450 GiB | 50% |
| Gộp | 1000 GiB | 451 GiB | 45,1% |

Tỷ lệ chung 45,1% không làm A có thêm chỗ ghi. Các thao tác ghi vào A vẫn phụ thuộc phần khả dụng của A.

Vì vậy, khi theo dõi nguy cơ hết chỗ, giữ đủ chiều để biết nơi nào đang thiếu. Tổng toàn bộ hệ thống có thể phục vụ một câu hỏi khác, nhưng không thay thế việc xem từng filesystem cần cho nghiệp vụ.

## 8. Metrics và DiskSpaceHealthIndicator là hai vai trò

| Thành phần | Cung cấp điều gì? |
| --- | --- |
| `disk.total`, `disk.free` | Các giá trị số để quan sát, lưu lịch sử và tính toán |
| `DiskSpaceHealthIndicator` | Đánh giá trạng thái sức khỏe theo đường dẫn và ngưỡng cấu hình |

Health không phải một tên meter khác của `disk.free`. Một trạng thái `UP` cũng không tự nói dung lượng đang giảm nhanh hay còn đủ chỗ cho mọi nhu cầu sắp tới.

Ví dụ cấu hình health cho cùng nơi ghi báo cáo, với ngưỡng minh họa chính xác một GiB:

```yaml
management:
  health:
    diskspace:
      path: /data/reports
      threshold: 1073741824B
```

Đây là phần cấu hình bổ sung cho ứng dụng Spring Boot; khi ghép vào tệp đang có, đặt các mục dưới cùng khóa `management`, không tạo hai khóa gốc `management` song song.

`management.health.diskspace.path` và `management.metrics.system.diskspace.paths` là hai cấu hình riêng. Đổi danh sách paths của metrics không tự đồng bộ nơi health kiểm tra. Muốn so sánh hai kết quả, xác nhận chúng đang xét cùng nơi. [Disk space health trong Spring Boot](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

Trong mã của phiên bản 3.3.0, health so dung lượng usable với ngưỡng để chọn trạng thái; ngưỡng minh họa không phải quy tắc phù hợp cho mọi hệ thống. Việc thay ngưỡng health cũng không tạo thêm dung lượng đĩa và không thay đổi hai phép đo.

## 9. Container, quyền và phạm vi quan sát

### 9.1. Quan sát từ môi trường mà JVM đang chạy

Khi ứng dụng ở trong container, đường dẫn được giải theo môi trường filesystem của container. Nơi làm việc mặc định có thể nằm trên lớp lưu trữ khác với volume dữ liệu đã gắn.

Chọn đường dẫn volume nơi dữ liệu thật được ghi. Không nhìn số đo của filesystem gốc trong container rồi suy rằng volume cơ sở dữ liệu hoặc báo cáo chắc chắn còn chỗ.

Nhiều instance có thể cùng nhìn một volume chia sẻ. Cộng dung lượng do từng instance báo lại có thể đếm cùng nơi lưu trữ nhiều lần.

### 9.2. Còn byte không bảo đảm thao tác ghi thành công

Dung lượng là một điều kiện quan trọng, nhưng việc ghi còn có thể thất bại vì quyền, filesystem chỉ đọc, giới hạn lưu trữ, lỗi thiết bị hoặc các điều kiện khác. Trên các filesystem có khái niệm inode, hết inode cũng có thể là vấn đề riêng.

Một mẫu dung lượng không thay thế việc theo dõi lỗi ghi thực tế hoặc kiểm tra trạng thái môi trường. Không diễn giải một số dương thành bảo đảm rằng mọi lần tạo tệp sau đó đều thành công.

### 9.3. Dung lượng không phải tốc độ I/O

`disk.free` và `disk.total` không đo số thao tác đọc/ghi mỗi giây, độ trễ ghi, thông lượng hay kích thước dữ liệu đã ghi bởi riêng tiến trình.

Nếu dung lượng khả dụng giảm từ 20 xuống 18 GiB, đó là thay đổi trạng thái giữa hai thời điểm. Muốn xem xu hướng cần có lịch sử, và phải tính tới cả ghi mới, xóa, giải phóng trễ cùng hoạt động của các tiến trình khác.

Một mẫu duy nhất không đủ để dự đoán chính xác còn bao lâu sẽ hết chỗ. Việc theo dõi nên kết hợp dung lượng tuyệt đối, tỷ lệ và diễn biến theo thời gian của đúng nơi lưu trữ cần quản lý.

## 10. Kiểm tra chéo khi số liệu khó hiểu

Trước hết, xác nhận cùng đường dẫn và filesystem, sau đó mới so giá trị:

1. Đọc tag `path` thực tế của meter.
2. Kiểm tra đường dẫn có tồn tại trong môi trường của JVM và trỏ tới nơi ứng dụng ghi hay không.
3. Xác định các đường dẫn cấu hình có cùng filesystem hoặc cùng volume chia sẻ không.
4. So sánh đơn vị byte, GB và GiB.
5. Xác định công cụ đối chiếu đang báo unallocated, usable, dung lượng đã dùng hay kích thước thư mục.
6. Kiểm tra thời điểm của các mẫu và quyền của tiến trình thực hiện phép đọc.

Trên Linux, các lệnh chỉ đọc sau có thể hỗ trợ kiểm tra một đường dẫn đang tồn tại:

```shell
df -B1 /data/reports
df -i /data/reports
```

Lệnh đầu giúp xem dung lượng ở đơn vị byte theo công cụ hệ thống; lệnh sau giúp xem inode khi filesystem hỗ trợ. Không mặc định mọi trường của công cụ này phải giống một API Java mà chưa đối chiếu định nghĩa và môi trường.

Trên Windows với một ổ ký tự đơn giản, có thể xem:

```powershell
Get-Volume -DriveLetter D | Select-Object DriveLetter, Size, SizeRemaining
```

Đây là ví dụ cho ổ D, không phải phép xác minh tự động mọi đường dẫn UNC hoặc mount lồng. Cần đối chiếu đúng nơi lưu trữ mà path của ứng dụng sử dụng.

| Hiện tượng | Điều cần kiểm tra |
| --- | --- |
| Không thấy hai tên disk | Actuator, registry, tự cấu hình, filter và danh sách paths |
| Giá trị bằng 0 hoặc không hợp lệ | Đường dẫn, quyền và khả năng lấy thông tin filesystem |
| Tổng lớn gần gấp đôi dự kiến | Có đang gộp nhiều path trên cùng filesystem hoặc nhiều instance cùng volume? |
| Health tốt nhưng metrics nơi ghi dữ liệu gần hết | Hai cấu hình có đang xét hai đường dẫn khác nhau? |
| Công cụ hệ thống và metric lệch nhau | Đơn vị, định nghĩa khả dụng, thời điểm, quyền và phạm vi filesystem |
| Đã xóa dữ liệu nhưng dung lượng chưa tăng như dự đoán | Cơ chế lưu trữ, tệp còn mở, thời điểm cập nhật và hoạt động ghi khác |

## 11. Thực hành

Thử từng thay đổi trên chương trình mẫu và giải thích kết quả:

1. Đổi usable trong `SampleFile` từ 20 GiB thành 5 GiB. Tỷ lệ còn khả dụng thành 5%, còn `totalMinusUsableGiB` thành 95 GiB.
2. Chỉ đổi `getFreeSpace()` từ 30 GiB thành 40 GiB, giữ usable là 20 GiB. `disk.free` của binder đang dùng không thay đổi.
3. Cho tổng bằng 0 trong chế độ mẫu. Chương trình từ chối tính tỷ lệ thay vì tạo một phần trăm giả.
4. Chạy chế độ thật với hai thư mục đã tồn tại trên cùng filesystem. Đối chiếu dung lượng tổng và giải thích vì sao chúng không phải hai ổ riêng; các mẫu usable có thể chênh theo thời điểm đọc.
5. Cấu hình nhiều paths trong ứng dụng Boot, xem `availableTags` rồi lọc từng path. Không lấy giá trị gộp theo tên làm tổng dung lượng vật lý nếu chưa loại đếm lặp.
6. Đối chiếu đường dẫn health và metrics trong một cấu hình có sẵn. Giải thích việc hai kết quả khác nhau trước khi thay ngưỡng hoặc thay cách tính.

Khi ghi lại một số đo dung lượng, nêu cùng đường dẫn, phạm vi filesystem, đơn vị và thời điểm quan sát. Cách đó giúp phân biệt “còn 20 GiB ở nơi JVM đang ghi báo cáo” với một con số dung lượng chung chưa xác định nơi áp dụng.
