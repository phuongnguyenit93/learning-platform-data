# Đánh giá tối ưu bằng thời gian chạy và tính đúng của sản phẩm trong Apache Ant

## 1. Mục tiêu: build nhanh hơn nhưng sản phẩm vẫn đúng

Trong một dự án sử dụng **Apache Ant**, tối ưu hiệu năng thường liên quan đến việc giảm thời gian biên dịch, kiểm thử, sao chép tài nguyên, đóng gói, sinh tài liệu hoặc triển khai. Tuy nhiên, một thay đổi làm lệnh `ant` kết thúc nhanh hơn **chưa đủ** để kết luận build được tối ưu thành công.

Ví dụ, trước khi tối ưu:

```text
ant clean verify
BUILD SUCCESSFUL
Total time: 2 minutes 15 seconds
```

Sau khi tối ưu:

```text
ant clean verify
BUILD SUCCESSFUL
Total time: 50 seconds
```

Kết quả thứ hai trông tốt hơn, nhưng cần trả lời thêm: các lớp Java có được biên dịch đủ không? Bộ kiểm thử có thực sự chạy không? JAR được tạo có đúng nội dung và entry point không? Các file mới hoặc file đã thay đổi có được đưa vào artifact không? Một task có bị bỏ qua chỉ vì điều kiện `uptodate` hoặc timestamp tính sai không?

Đánh giá tối ưu đúng nghĩa luôn có **hai tiêu chí song hành**:

1. **Hiệu năng:** cùng một khối lượng công việc, quá trình build sử dụng ít thời gian hoặc tài nguyên hơn với mức cải thiện lặp lại được.
2. **Tính đúng của sản phẩm:** đầu ra và hành vi của ứng dụng vẫn đáp ứng các yêu cầu đã định, kể cả khi build từ trạng thái sạch, build tăng dần và chạy trong môi trường cần hỗ trợ.

Một tối ưu chỉ được chấp nhận khi đạt tiêu chí hiệu năng **và** không phá vỡ tiêu chí đúng đắn. Tính đúng cần được định nghĩa bằng phép kiểm tra cụ thể, thay vì chỉ nhìn vào dòng `BUILD SUCCESSFUL`.

## 2. Phân biệt điều cần đo và điều cần chứng minh

### 2.1. Chỉ số hiệu năng

| Chỉ số | Câu hỏi cần trả lời | Cách đo thực tế |
| --- | --- | --- |
| **Wall-clock time** (thời gian thực) | Từ khi bắt đầu đến khi Ant kết thúc mất bao lâu? | Đồng hồ bên ngoài quá trình: `time`, `Measure-Command`, `time.perf_counter()` |
| Thời gian từng task/target | `javac`, `junit`, `copy` hay `jar` chiếm bao nhiêu thời gian? | Log theo task/target, profiler của Ant hoặc công cụ đo riêng |
| CPU time | Build dùng CPU bao nhiêu, có chờ I/O hoặc mạng không? | `/usr/bin/time`, trình theo dõi tiến trình, profiler |
| Bộ nhớ cao nhất | Thay đổi có gây tràn heap hoặc tăng peak RSS không? | OS process monitor, profiler, giám sát CI |
| I/O và cache | Build có đọc/ghi nhiều dữ liệu hoặc tải lại dependency không? | Log task, số lượng file xử lý, công cụ giám sát đĩa/mạng |
| Độ ổn định | Tối ưu có nhanh nhất quán hay chỉ nhanh trong một lần đo? | Nhiều lần chạy, median và mức phân tán |

**Wall-clock time** thường là chỉ số đầu tiên nên đo vì phản ánh thời gian người phát triển hoặc CI thực sự chờ. Nhưng cùng một thời gian tổng không cho biết chỗ nào cần tối ưu. Nếu `<javac>` chiếm 80% thời gian, tối ưu bước `<zip>` chiếm 3% chỉ có thể đem lại lợi ích giới hạn.

### 2.2. Các mức kiểm tra tính đúng

| Mức kiểm tra | Ví dụ trong dự án Ant | Lỗi có thể phát hiện |
| --- | --- | --- |
| Task hoàn tất | Ant trả exit code 0; không có lỗi biên dịch/đóng gói | Lỗi được task chủ động báo |
| Kiểm thử tự động | Unit test, integration test, kiểm tra hợp đồng API | Sai logic, sai tương tác giữa module |
| Kiểm tra cấu trúc artifact | Kiểm tra các entry trong JAR/WAR/ZIP, file manifest, cấu hình, dependency | Thiếu class, thiếu tài nguyên, sai đường dẫn |
| Kiểm thử chạy artifact | `java -jar`, smoke test, khởi tạo ứng dụng trong môi trường thử | Artifact không thực thi được dù biên dịch thành công |
| Kiểm tra cập nhật | Sửa một file nguồn rồi build không `clean`; xem class và artifact có đổi phù hợp | Cache sai, bỏ sót dependency, sản phẩm cũ |
| So sánh byte/checksum | So sánh SHA-256 khi hợp đồng yêu cầu artifact tái lập được | Thay đổi byte không mong muốn, metadata động |
| Kiểm tra triển khai | Chạy trong JDK/OS/container đích | Khác biệt môi trường, đường dẫn hoặc quyền truy cập |

Không phải dự án nào cũng yêu cầu artifact có byte giống hệt trước và sau tối ưu. Nếu một thay đổi chủ đích làm JAR nhỏ hơn bằng cách bỏ file thừa, checksum đương nhiên khác. Lúc đó phải kiểm tra **nội dung và hành vi theo đặc tả**. Ngược lại, nếu yêu cầu là build tái lập, khác checksum của cùng đầu vào cần được giải thích, kể cả khi chương trình vẫn chạy đúng.

## 3. Xác định kịch bản đo trước khi thay đổi `build.xml`

Ant điều phối các **target** và quan hệ phụ thuộc `depends`. Việc tối ưu một target có thể tác động khác nhau tùy loại build. Vì thế phải đo đúng loại công việc đang muốn cải thiện.

| Kịch bản | Lệnh minh họa | Ý nghĩa |
| --- | --- | --- |
| **Clean build** | `ant clean verify` | Biên dịch, kiểm thử, đóng gói từ đầu; thường đại diện cho CI hoặc bản phát hành |
| **Build không đổi nguồn** | `ant dist` lần thứ hai | Đo overhead và khả năng bỏ qua công việc không cần thiết |
| **Incremental build** | Sửa một file rồi chạy `ant verify` | Đo tốc độ cập nhật và phát hiện phụ thuộc bị bỏ sót |
| **Thay đổi ảnh hưởng nhiều module** | Sửa API dùng chung rồi chạy `ant verify` | Kiểm tra đường đi phụ thuộc và biên dịch lại cần thiết |
| **Build có kiểm thử** | `ant test` hoặc `ant verify` | Đánh giá thời gian phản hồi khi cần phát hiện lỗi |
| **Build đóng gói riêng** | `ant dist` | Đánh giá phần đóng gói và xử lý resource |

Các tên `clean`, `test`, `dist` và `verify` chỉ là **quy ước thường dùng**, không phải những target mặc định mà mọi `build.xml` đều có. Hãy dùng target thực tế của dự án và giữ nguyên tập công việc khi so sánh.

Không so sánh thời gian của `ant clean verify` trước tối ưu với `ant dist` sau tối ưu: hai lệnh thực hiện khối lượng công việc khác nhau. Tương tự, kết quả build sau tối ưu chỉ có ích nếu cùng chạy kiểm thử như trước, trừ khi mục tiêu đã được xác định rõ là đo riêng công đoạn đóng gói.

### 3.1. Phân biệt clean và incremental về tính đúng

Tối ưu incremental build mang lại lợi ích lớn trong phát triển, nhưng dễ tạo lỗi **artifact cũ**:

- Thay đổi `App.java` mà `App.class` không được biên dịch lại.
- Sửa file cấu hình nhưng `<copy>` không đưa file mới vào thư mục đóng gói.
- Sửa API trong module A nhưng module B phụ thuộc A không được biên dịch lại.
- Đổi tham số compiler mà target vẫn được xem là “đã cập nhật” vì chỉ so sánh thời gian file.
- Xóa file nguồn nhưng file `.class` cũ vẫn tồn tại trong thư mục đầu ra và bị đưa vào JAR.

Vì vậy, một cải thiện thời gian incremental phải được thử trên **file mới, file sửa, file xóa và thay đổi phụ thuộc** nếu những trường hợp đó thuộc workflow thực tế. Clean build thành công không chứng minh incremental build luôn đúng.

## 4. Thiết lập baseline đáng tin cậy

**Baseline** là số liệu và sản phẩm từ phiên bản chưa tối ưu, dùng làm mốc đối chiếu. Lưu lại baseline trước khi sửa cấu hình; nếu không, rất khó chứng minh phần thời gian giảm đến từ thay đổi nào.

### 4.1. Cố định điều kiện thí nghiệm

Ghi lại ít nhất:

- Revision mã nguồn (commit), dữ liệu đầu vào và phiên bản dependency.
- Phiên bản Ant (`ant -version`), JDK/JVM (`java -version`), hệ điều hành và kiến trúc CPU.
- Các biến cấu hình liên quan như `JAVA_HOME`, `ANT_OPTS`, `JAVA_TOOL_OPTIONS` và tham số build.
- Số lõi CPU, giới hạn CPU/bộ nhớ trong container, tình trạng chạy song song trên máy.
- Loại đĩa, trạng thái cache, truy cập mạng, repository Maven/Ivy hoặc thư mục dependency nội bộ.
- Target chính xác, ví dụ `clean verify`, và liệu đầu vào có được tạo mới trước mỗi lượt hay không.

Nên đo ở máy ít chịu nhiễu từ các tác vụ nặng khác. Với CI chia sẻ runner, thời gian có thể dao động do hàng đợi, máy chủ, mạng và tải của các job khác; vì vậy cần nhiều lần đo và báo mức phân tán.

### 4.2. Phân biệt warm-up và lượt đo

JVM, hệ điều hành và cache đĩa có thể khiến lần chạy đầu khác các lần sau. Có thể chạy một đến hai lượt **warm-up** rồi đo năm đến mười lượt riêng biệt. Mỗi lượt clean build phải thực sự xóa thư mục output cần dọn; mỗi lượt incremental phải bắt đầu từ cùng trạng thái artifact và áp dụng cùng kiểu thay đổi.

Warm-up không phải lệnh luôn bắt buộc, nhưng phải thực hiện tương đương giữa baseline và phương án mới. Nếu thí nghiệm có mục tiêu đo **cold build** sau khi clone mới hoặc trong container hoàn toàn sạch, không được vô tình thay bằng kết quả cache nóng rồi tuyên bố đã tối ưu cold build.

### 4.3. Tránh so sánh tuần tự gây thiên lệch

Chạy toàn bộ baseline vào buổi sáng và toàn bộ phiên bản tối ưu vào lúc máy ít tải hơn có thể tạo kết luận sai. Khi khả thi, chuẩn bị hai checkout độc lập của cùng revision và đổi qua lại các lượt đo theo mẫu **A–B–B–A**, hoặc luân phiên A/B. Không được cho hai build dùng chung cùng thư mục `build/` hoặc cùng đầu ra khiến cache/công việc của lượt này thay đổi điều kiện của lượt kia.

Trong thực tế, thông số môi trường và đầu vào quan trọng hơn việc chọn đúng một mẫu sắp lượt. Cần ghi nhận chênh lệch có thể đến từ biến động môi trường.

## 5. Đo thời gian tổng và phát hiện phần tốn thời gian

### 5.1. Đo bằng hệ điều hành

**Linux/macOS — shell built-in `time`:**

```bash
time ant -noinput clean verify
```

Kết quả thường hiển thị `real` (wall-clock), `user` và `sys`. Cú pháp hiển thị phụ thuộc shell. Dùng `real` khi so sánh thời gian người dùng chờ. Đồng thời theo dõi exit code của `ant`, vì một build thất bại sớm có thể “nhanh” bất thường.

**Windows PowerShell:**

```powershell
$elapsed = Measure-Command {
    & ant -noinput clean verify
    if ($LASTEXITCODE -ne 0) {
        throw "Ant failed with exit code $LASTEXITCODE"
    }
}
Write-Host ("Wall-clock: {0:N2} s" -f $elapsed.TotalSeconds)
```

`Measure-Command` đo khoảng thời gian thực của toàn bộ khối lệnh. Nếu cần giữ log, hãy chuyển hướng đầu ra của Ant vào file ở ngoài thư mục bị `clean` xóa, rồi vẫn kiểm tra mã thoát.

### 5.2. Dùng profiler/log của Ant để định vị điểm nghẽn

Ant có thể dùng logger dạng profile để xem thời gian thực thi task:

```bash
ant -noinput -logger org.apache.tools.ant.listener.ProfileLogger clean verify
```

Trong các bản Ant có `ProfileLogger`, log giúp nhận ra task nào tốn thời gian và cần xem xét trước, ví dụ `javac`, `junit`, `copy`, `jar` hoặc `exec`. Kiểm tra phiên bản Ant và logger hiện có nếu class logger không được tìm thấy. Số liệu từ profiler nên dùng để **xác định vị trí nghi vấn**, còn so sánh trước/sau vẫn nên dựa trên phép đo wall-clock nhất quán bên ngoài.

Một câu hỏi hữu ích: nếu `<javac>` chiếm 90 giây trong tổng 120 giây thì việc tối ưu một `<zip>` mất 4 giây khó giúp cải thiện lớn. Để ưu tiên công việc, trước hết hãy lập bảng thời gian các bước hoặc ít nhất các target chậm.

### 5.3. Áp dụng giới hạn của Amdahl

Nếu một phần công việc chiếm tỷ lệ `p` của tổng thời gian và có thể tăng tốc phần đó `s` lần, giới hạn tăng tốc lý thuyết toàn build (giả sử phần còn lại không đổi) là:

\[
S=\frac{1}{(1-p)+\frac{p}{s}}
\]

Ví dụ, đóng gói chiếm 10% thời gian và có thể tăng tốc gấp đôi (`p=0,1`, `s=2`), tổng build chỉ nhanh khoảng:

\[
S=\frac{1}{0,9+0,05}\approx1,053
\]

Tức tổng thời gian giảm khoảng **5%**, không phải 50%. Đây là lý do ưu tiên task đang chiếm nhiều thời gian thực thay vì tối ưu theo cảm giác.

## 6. Ví dụ Ant tự chứa: xây baseline có kiểm thử và artifact

Ta tạo một dự án Java nhỏ để minh họa cách đo thời gian mà vẫn có bằng chứng về đầu ra. Cấu trúc:

```text
ant-perf-demo/
├── build.xml
├── src/
│   └── demo/
│       └── App.java
└── test/
    └── demo/
        └── AppTest.java
```

**`src/demo/App.java`**

```java
package demo;

public final class App {
    private App() {}

    public static String message() {
        return "ANT-READY";
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

**`test/demo/AppTest.java`**

```java
package demo;

public final class AppTest {
    public static void main(String[] args) {
        String actual = App.message();
        if (!"ANT-READY".equals(actual)) {
            throw new AssertionError("Unexpected message: " + actual);
        }
        System.out.println("AppTest passed");
    }
}
```

Kiểm thử minh họa dùng một chương trình Java thoát khác 0 khi sai, nên không cần cài thêm JUnit. Trong dự án thực tế, có thể thay bằng `<junit>` hoặc framework test hiện hành, miễn là lỗi test làm build thất bại.

**`build.xml`** (yêu cầu Ant 1.10.2 trở lên cho thuộc tính `modificationtime` của `<jar>`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-perf-demo" default="verify" basedir=".">
    <property name="src.dir" location="src"/>
    <property name="test.src.dir" location="test"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir" location="${build.dir}/test-classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"
               debug="true"/>
    </target>

    <target name="compile-tests" depends="compile">
        <mkdir dir="${test.classes.dir}"/>
        <javac srcdir="${test.src.dir}"
               destdir="${test.classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"
               debug="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
            </classpath>
        </javac>
    </target>

    <target name="test" depends="compile-tests">
        <java classname="demo.AppTest"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
                <pathelement location="${test.classes.dir}"/>
            </classpath>
        </java>
    </target>

    <target name="dist" depends="compile">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${dist.dir}/app.jar"
             basedir="${classes.dir}"
             modificationtime="2024-01-01T00:00:00Z"
             roundup="false"
             duplicate="fail"
             update="false">
            <manifest>
                <attribute name="Main-Class" value="demo.App"/>
                <attribute name="Implementation-Version" value="1.0.0"/>
            </manifest>
        </jar>
    </target>

    <target name="verify" depends="test,dist">
        <checksum file="${dist.dir}/app.jar"
                  algorithm="SHA-256"
                  property="artifact.sha256"/>
        <echo message="Artifact SHA-256: ${artifact.sha256}"/>
    </target>
</project>
```

Trong ví dụ:

- `clean` xóa đầu ra để đo full build.
- `compile` và `compile-tests` biên dịch nguồn sản phẩm và mã kiểm thử trong hai thư mục riêng.
- `test` dùng `failonerror="true"` để biến lỗi chức năng thành build thất bại.
- `dist` tạo JAR với `Main-Class` cố định. Timestamp entry cố định giúp giảm sai khác metadata giữa các lần clean build trong cùng môi trường.
- `verify` chạy cả kiểm thử lẫn đóng gói; tính SHA-256 như một bằng chứng cho artifact tạo ra.

Chạy:

```bash
ant -noinput clean verify
java -jar build/dist/app.jar
jar tf build/dist/app.jar
```

Ứng dụng phải in `ANT-READY`. Danh sách entry JAR phải có `demo/App.class` và `META-INF/MANIFEST.MF`. Với cùng đầu vào và cùng toolchain, checksum sau các clean build có thể dùng để quan sát tính ổn định byte; nếu khác, cần kiểm tra manifest và metadata của archive trước khi suy ra nội dung chương trình thay đổi.

**Để đánh giá một tối ưu**, hãy giữ phiên bản trên làm baseline rồi tạo một thay đổi cụ thể trong `build.xml`, chẳng hạn giảm số resource không cần thiết được đưa vào JAR hoặc cải thiện điều kiện để `<copy>` chỉ cập nhật tệp thực sự thay đổi. Đo lại cùng `ant clean verify` và `ant verify`; kiểm tra test, danh sách entry và kết quả chạy JAR như baseline.

## 7. Thu thập nhiều lượt đo tự động và lưu log

Thời gian từ một lần build đơn lẻ dễ bị nhiễu. Có thể dùng script Python dưới đây làm bộ đo chéo nền tảng, gọi đúng một lệnh Ant đã chọn nhiều lần và giữ log của từng lượt.

Lưu thành **`benchmark_ant.py`** bên cạnh `build.xml`:

```python
from pathlib import Path
import statistics
import subprocess
import sys
import time

RUNS = 7
COMMAND = ["ant", "-noinput", "-f", "build.xml", "clean", "verify"]
LOG_DIR = Path("benchmark-logs")


def run_once(label: str) -> float:
    start = time.perf_counter()
    process = subprocess.run(
        COMMAND,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    elapsed = time.perf_counter() - start

    LOG_DIR.mkdir(exist_ok=True)
    (LOG_DIR / f"{label}.log").write_text(
        process.stdout, encoding="utf-8"
    )

    if process.returncode != 0:
        print(f"{label} FAILED (exit={process.returncode})")
        print(f"See {LOG_DIR / f'{label}.log'}")
        sys.exit(process.returncode)

    print(f"{label}: {elapsed:.3f} s")
    return elapsed


print("Warm-up:")
run_once("warmup")

times = [run_once(f"run-{i:02d}") for i in range(1, RUNS + 1)]
print(f"Median: {statistics.median(times):.3f} s")
print(f"Min:    {min(times):.3f} s")
print(f"Max:    {max(times):.3f} s")
print("Logs:   benchmark-logs/")
```

Chạy:

```bash
python benchmark_ant.py
```

Script đo một lượt warm-up, sau đó bảy lượt `ant clean verify` và in median/min/max. Mỗi lượt thất bại sẽ dừng việc đo để tránh tính một **thời gian lỗi** như một tối ưu thành công. Thư mục `benchmark-logs/` nằm ngoài `build/` nên không bị target `clean` trong ví dụ xóa.

**Lưu ý:** script được thiết kế cho *clean build*. Không thay `clean verify` bằng `verify` rồi cho rằng đã đo đúng incremental build: lượt đầu, thứ hai và thứ bảy khi đó có thể làm khối lượng khác nhau. Muốn benchmark incremental, mỗi lượt phải khôi phục một trạng thái artifact ban đầu tương đương, áp dụng cùng một thay đổi nguồn, sau đó mới bắt đầu đồng hồ.

Nếu PowerShell hoặc shell là công cụ mặc định trong CI, có thể dùng chúng để lặp lệnh thay vì Python. Bất kể công cụ nào, cần ghi **lệnh đo, số lần chạy, phiên bản môi trường, dữ liệu đầu vào và kết quả thực tế**, không chỉ ghi một con số thời gian cuối cùng.

## 8. Tính mức cải thiện và đọc kết quả

Giả sử cùng lệnh `ant clean verify` trên cùng môi trường cho các thời gian sau (số liệu minh họa):

| Lượt | Baseline (giây) | Sau tối ưu (giây) |
| ---: | ---: | ---: |
| 1 | 123 | 96 |
| 2 | 121 | 94 |
| 3 | 122 | 95 |
| 4 | 121 | 95 |
| 5 | 124 | 93 |
| **Median** | **122** | **95** |

Tính:

\[
\text{Tiết kiệm thời gian (\%)} =
\frac{T_{\text{trước}}-T_{\text{sau}}}{T_{\text{trước}}}\times 100
\]

\[
\text{Speedup}=\frac{T_{\text{trước}}}{T_{\text{sau}}}
\]

Với median ở bảng:

\[
\frac{122-95}{122}\times100\approx22{,}1\%
\qquad
\text{Speedup}=\frac{122}{95}\approx1{,}28
\]

Có thể báo cáo: *Trong cùng kịch bản clean build, thời gian median giảm từ 122 giây xuống 95 giây, tương ứng giảm khoảng 22,1% và tăng tốc khoảng 1,28 lần.*

Đây là ví dụ về cách trình bày số liệu, **không phải kết quả đã chạy trên một dự án cụ thể**.

Không nên khẳng định cải thiện đáng tin cậy khi mức chênh lệch nhỏ hơn dao động bình thường của môi trường. Xem xét thêm độ trải của số đo (min/max, khoảng tứ phân vị hoặc độ lệch chuẩn) và số lượt đo. Trong CI nhiều nhiễu, hãy ưu tiên báo xu hướng và chạy thêm các lượt xác nhận trước khi đặt ngưỡng hiệu năng bắt buộc.

## 9. Kiểm chứng sản phẩm trước và sau tối ưu

### 9.1. Kiểm thử tự động phải giữ cùng phạm vi

Trước khi tối ưu, ghi lại danh sách test chạy, kết quả, report và target tạo report. Sau tối ưu, dùng đúng phạm vi đó, có cùng dữ liệu test và mã thoát phản ánh thất bại.

Nếu dùng task `<junit>`, hãy cấu hình để test lỗi làm build thất bại bằng cơ chế phù hợp (ví dụ kết hợp thuộc tính lưu kết quả lỗi và `<fail>`). Chỉ tạo report XML nhưng cho build kết thúc 0 khi có test hỏng không đủ để coi là kiểm chứng đạt.

Một thay đổi “tối ưu” bằng cách bỏ test chậm có thể rút ngắn thời gian, nhưng chỉ là thay đổi **mức độ kiểm chứng**. Nếu dự án chủ đích tách unit test và integration test thành hai pipeline, hãy báo riêng thời gian từng pipeline và giữ quy tắc chấp nhận của từng loại.

### 9.2. Kiểm tra artifact về nội dung và khả năng chạy

Với JAR:

```bash
jar tf build/dist/app.jar
java -jar build/dist/app.jar
```

Kiểm tra ít nhất:

- Các class và resource cần thiết có mặt, đặt đúng đường dẫn.
- Manifest có `Main-Class`, version và các thuộc tính thực sự cần cho runtime.
- Tệp không mong muốn (log, tệp tạm, test fixture nhạy cảm) không bị đưa vào artifact.
- Ứng dụng có thể khởi động và thực hiện một thao tác mẫu.
- Kích thước artifact thay đổi có lý do, không phải vì mất tệp cần thiết.

Đối với WAR/EAR, có thể bổ sung kiểm tra cấu trúc `WEB-INF/`, `META-INF/`, thư viện đi kèm, cấu hình servlet/server và smoke test trên máy chủ mục tiêu. Với ZIP phân phối, kiểm tra script, đường dẫn và quyền thực thi.

### 9.3. So sánh checksum: khi nào áp dụng?

**Linux:**

```bash
sha256sum build/dist/app.jar
```

**PowerShell:**

```powershell
Get-FileHash -Algorithm SHA256 build/dist/app.jar
```

Nếu hợp đồng sản phẩm yêu cầu output byte-identical, lưu checksum baseline rồi so sánh sau tối ưu với **cùng mã nguồn, dependency, toolchain và timestamp**. Khi checksum khác, hãy điều tra manifest, thứ tự entry, timestamp, quyền, cấu hình nén và nội dung class/resource.

Nếu tối ưu chủ đích tạo byte khác (ví dụ thay mức nén ZIP, loại tệp thừa), hash khác không tự động là lỗi; lúc đó dùng test chức năng, so sánh nội dung cần giữ, API và khả năng triển khai để đánh giá. Nên mô tả rõ ngoại lệ này trong báo cáo thay đổi.

### 9.4. Kiểm tra incremental bằng thay đổi có kiểm soát

Tạo một chuỗi thao tác có thể lặp lại:

1. Chạy `ant clean verify` để có trạng thái artifact nền hợp lệ.
2. Sửa một tệp nguồn cụ thể; ví dụ đổi nội dung thông báo hoặc một hành vi có test đi kèm.
3. Chạy `ant verify` **không dùng `clean`**; xác nhận bytecode cần thiết được cập nhật và test phản ánh thay đổi.
4. Thêm một resource mới và đảm bảo nó được đưa vào archive nếu bộ lọc của build có trách nhiệm làm việc đó.
5. Xóa hoặc đổi tên resource/class; kiểm tra artifact cuối không còn tệp cũ.
6. Thực hiện clean build cùng revision cuối và so sánh **hành vi/nội dung mong đợi** của sản phẩm incremental với sản phẩm từ clean build.

Đối với `<javac>`, Ant kiểm tra file nguồn và class theo thời gian sửa đổi để lựa chọn biên dịch tăng dần; cơ chế này không thay thế một hệ thống theo dõi đầy đủ mọi quan hệ phụ thuộc Java. Khi thay đổi public API, sinh mã hoặc loại bỏ class, cần chú ý khả năng class đã biên dịch cũ còn sót. Đó là lý do bài đo incremental luôn phải có bước kiểm tra output, không chỉ đo số giây.

### 9.5. Kiểm tra lỗi có được phát hiện

Một phép thử hữu ích là **cố ý gây lỗi trong nhánh thử nghiệm**:

- Sửa giá trị trả về của `App.message()` thành chuỗi khác nhưng giữ điều kiện của `AppTest`.
- Chạy `ant test` hoặc `ant verify`; build phải **thất bại**.
- Khôi phục nguồn đúng rồi chạy lại; build phải thành công.

Điều này giúp xác nhận test thực sự được thực thi và lỗi không bị cấu hình như `failonerror="false"` âm thầm bỏ qua. Chỉ dùng thay đổi cố ý trong một workspace/thử nghiệm có thể khôi phục; không đưa lỗi có chủ đích vào mã nguồn phát hành.

## 10. Những hướng tối ưu Ant và rủi ro cần đo cùng

| Ý tưởng tối ưu | Lợi ích có thể có | Tính đúng cần kiểm chứng |
| --- | --- | --- |
| Hạn chế `<javac>` vào đúng `srcdir`, pattern, module cần thiết | Ít file biên dịch hơn | Không bỏ thiếu class; thay API được cập nhật |
| Sử dụng build incremental và `<uptodate>` hợp lý | Bỏ qua công việc nếu đầu vào không đổi | Điều kiện phải bao quát **mọi** dependency thật, kể cả file cấu hình và đầu ra bị xóa |
| Giảm lượng tệp `<copy>`/`<zip>` phải quét | Ít I/O và nén hơn | Không thiếu resource và không lưu tệp cũ |
| Cache dependency với Ivy hoặc repository nội bộ | Giảm tải mạng và thời gian phân giải | Phiên bản và checksum dependency không thay đổi ngoài chủ đích |
| Tách target có thể chạy độc lập | Giảm đường găng khi chạy song song | Không có ghi đồng thời vào cùng output, thứ tự tạo artifact vẫn hợp lệ |
| Dùng `<parallel>` cho công việc thật sự độc lập | Tận dụng CPU/I/O | Tránh race condition, ghi file đồng thời, phụ thuộc ẩn |
| Tinh chỉnh `ANT_OPTS`/JVM memory | Giảm GC, tránh thiếu heap | Không phát sinh khác biệt do compiler/runtime, không vượt giới hạn CI |
| Thay đổi mức nén JAR/ZIP | Giảm CPU hoặc dung lượng | Artifact giải nén đúng; kiểm tra yêu cầu byte-identical nếu có |
| Giảm số lần chạy test tốn kém có chọn lọc | Phản hồi nhanh hơn cho developer | Tách rõ pipeline nhanh và đầy đủ, giữ cổng kiểm thử cần thiết |

Đối với `<parallel>`, Ant không tự biến một target graph thành lịch trình song song an toàn. Người viết `build.xml` phải thiết kế các nhánh độc lập. Nếu hai nhánh cùng ghi `build/classes`, cùng xóa thư mục tạm hoặc cùng tạo một JAR, thời gian có thể giảm ở lượt thử nhưng artifact trở nên không xác định.

Nếu dùng `<uptodate>` hoặc thuộc tính điều kiện như `if`/`unless` để bỏ một bước, hãy so sánh cả **kịch bản thay đổi có liên quan**; không được chỉ đo trường hợp không có gì thay đổi. Một bước bị bỏ nhầm vẫn có thể khiến Ant báo thành công, dù sản phẩm là bản cũ.

## 11. Thiết kế tiêu chí chấp nhận tối ưu

Đặt tiêu chí trước khi đo, không chọn ngưỡng sau khi đã thấy số liệu. Một bộ tiêu chí thực tế có thể gồm:

| Nhóm | Ví dụ tiêu chí | Kết quả cần lưu |
| --- | --- | --- |
| Hiệu năng clean build | Median giảm ít nhất 15% so với baseline trong cùng điều kiện | Các thời gian từng lượt, median và phiên bản môi trường |
| Hiệu năng incremental | Thời gian của thay đổi một tệp giảm, không phát sinh rebuild thừa | Dấu vết file được biên dịch lại và thời gian |
| Unit/integration tests | Tất cả test bắt buộc thành công, không giảm số lượng test ngoài chủ đích | Report kiểm thử và exit code |
| Artifact | Đủ class/resource, manifest hợp lệ, ứng dụng khởi chạy được | Danh sách entry, smoke test |
| Tính cập nhật | Sửa/thêm/xóa nguồn được phản ánh đúng sau build incremental | Kết quả tình huống thử |
| Tính tái lập | Cùng đầu vào cho cùng checksum nếu đây là yêu cầu | SHA-256 baseline và tối ưu |
| Tài nguyên | Peak memory không vượt giới hạn runner | Log hoặc thông số giám sát |

Ngưỡng **15%** ở bảng chỉ là ví dụ minh họa, không phải chuẩn chung. Một dự án có build mất 30 phút có thể đánh giá mức giảm 8% là rất đáng kể; với build 2 giây, chênh lệch 0,1 giây có thể nằm trong nhiễu đo. Tiêu chí nên phản ánh thời gian thực tiết kiệm, mức biến động và chi phí duy trì cấu hình tối ưu.

### Cổng chất lượng trong CI

Một pipeline hợp lý có thể triển khai theo luồng:

```text
Checkout cùng revision
          |
          v
      ant clean
          |
          v
      ant verify --------> Unit / integration tests
          |                      |
          v                      v
   Artifact validation      Test reports
          |
          v
     Smoke test
          |
          v
  Ghi thời gian, checksum,
  phiên bản JDK / Ant
          |
          v
  So sánh baseline / ngưỡng
          |
          v
     Chấp nhận hoặc điều tra
```

Với CI chạy trên máy dùng chung, không nên biến một ngưỡng thời gian quá sát thành điều kiện fail tuyệt đối sau **một** lượt đo. Có thể lưu xu hướng nhiều build trên runner tương đương và chỉ cảnh báo khi hồi quy lặp lại. Các kiểm tra đúng đắn như test thất bại, thiếu artifact hoặc checksum sai trong quy trình yêu cầu byte-identical vẫn phải chặn phát hành theo chính sách dự án.

## 12. Mẫu báo cáo kết quả tối ưu

Một bản báo cáo ngắn nhưng đủ cơ sở review nên có:

**Mục tiêu và thay đổi:** giảm thời gian thực hiện một target cụ thể; nêu khác biệt trong `build.xml`, tài nguyên đầu vào hoặc cách xử lý phụ thuộc.

**Điều kiện đo:** revision, Ant/JDK, hệ điều hành, cấu hình máy/runner, lệnh, loại build (clean/incremental), số lần chạy, cách warm-up và trạng thái cache.

**Số liệu:** từng thời gian trước/sau, median, mức dao động, tiết kiệm tuyệt đối bằng giây, phần trăm giảm và speedup.

**Chứng cứ tính đúng:** test report, mã thoát, smoke test, danh sách artifact; checksum nếu cần; kiểm tra thay đổi source/resource và kết quả clean so với incremental.

**Giới hạn:** những môi trường chưa đo, thay đổi chủ đích về byte đầu ra, phụ thuộc vào cache, mức nhiễu CI hoặc khối lượng dữ liệu chưa đại diện.

Ví dụ cách viết kết luận kỹ thuật:

> Với cùng revision và cùng lệnh `ant clean verify` trên runner cố định, median của năm lượt đo giảm từ 122 giây xuống 95 giây (giảm khoảng 22,1%). Tất cả kiểm thử bắt buộc đều thành công; JAR chứa đầy đủ class/resource và vượt qua smoke test. Kịch bản sửa một file nguồn, thêm và xóa resource cũng tạo đầu ra đúng trong incremental build. Phép đo này áp dụng cho môi trường JDK và Ant đã ghi trong báo cáo; chưa suy rộng sang runner khác.

Con số trong ví dụ là giả định. Trong một dự án thật, **không được tuyên bố test hoặc phép đo đã chạy nếu chưa có log/kết quả tương ứng**.

## 13. Những sai lầm khiến số liệu tối ưu mất ý nghĩa

### Chỉ so thời gian báo bởi Ant, không xác minh mã thoát

Một task thất bại sớm làm tổng thời gian ngắn đi. Hãy coi build thất bại là **lượt đo không hợp lệ** và giữ log để điều tra.

### So sánh clean build với build có cache

Một bên xóa `build/`, bên kia dùng class cũ thì không cùng khối lượng. Đánh giá clean và incremental như hai kịch bản riêng.

### Chỉ kiểm tra JAR tồn tại

Một `app.jar` vẫn có thể thiếu dependency, thiếu resource hoặc chứa class cũ. Cần test, kiểm tra danh sách entry và thực thi artifact.

### Coi checksum khác là luôn sai hoặc luôn không quan trọng

Checksum khác có thể do timestamp ZIP, manifest, thứ tự entry, compression hoặc nội dung thật sự. Ý nghĩa của sai khác tùy hợp đồng sản phẩm; cần nêu rõ yêu cầu byte-identical hay tương đương chức năng.

### Bỏ qua biến động máy và số lần chạy

Một lần nhanh hơn vài phần trăm không chứng minh tối ưu. Lặp phép đo, dùng median và giữ số liệu phân tán để phân biệt cải thiện với nhiễu.

### Tối ưu task nhanh trong khi bỏ qua đường găng

Nếu thời gian chủ yếu ở biên dịch hoặc integration test, giảm vài mili giây của target đóng gói ít ảnh hưởng đến thời gian phát hành. Dùng số liệu profiler và tỷ trọng các bước để chọn ưu tiên.

### Sửa điều kiện cập nhật nhưng không thử thêm/xóa file

Một biểu thức `<uptodate>` thiếu dependency có thể trông rất nhanh vì build không làm điều cần làm. Test thay đổi đầu vào và so với sản phẩm từ clean build.

## 14. Bài thực hành gợi ý

1. Tạo dự án ví dụ ở mục 6. Chạy `ant -noinput clean verify`, `java -jar build/dist/app.jar` và `jar tf build/dist/app.jar`; ghi nhận kết quả.
2. Dùng script mục 7 đo bảy lần clean build và lưu median, min/max cùng log. Ghi phiên bản Ant/JDK và môi trường.
3. Xác định một thay đổi trong xử lý resource hoặc bước đóng gói mà bạn dự kiến giúp giảm thời gian trên một tập dữ liệu lớn hơn. Ghi giả thuyết trước khi thay đổi.
4. Đo lại bằng cùng lệnh, dữ liệu và cách chạy; tính tỷ lệ cải thiện. Nếu số đo dao động quá nhiều, báo giới hạn thay vì cố gắng kết luận.
5. Chạy kiểm thử, smoke test, liệt kê class/resource; thử sửa/thêm/xóa file và kiểm tra sản phẩm incremental.
6. Giới thiệu một lỗi có chủ đích trong lớp `App` để xác nhận target `test` thật sự phát hiện lỗi. Khôi phục mã và xác nhận build thành công.
7. Viết một báo cáo ngắn chỉ rõ thay đổi, kết quả đo, bằng chứng tính đúng và phạm vi áp dụng.

## 15. Ghi nhớ

Với Apache Ant, đánh giá hiệu năng cần bắt đầu từ **một kịch bản build xác định**, đo thời gian **lặp lại được** và xác định task đang chiếm thời gian. Mọi thay đổi tối ưu phải vượt qua những phép kiểm tra **sản phẩm đúng** phù hợp: test, cấu trúc artifact, chạy thực tế, cập nhật incremental và checksum nếu cần.

Một build nhanh hơn chỉ có giá trị khi nó vẫn tạo ra **đúng sản phẩm cần phát hành**. Thời gian đo cung cấp bằng chứng về tốc độ; kiểm thử và xác minh artifact cung cấp bằng chứng về tính đúng. Hai loại bằng chứng cần được báo cáo cùng nhau.

## Tài liệu tham khảo

- [Apache Ant Manual — Running Apache Ant](https://ant.apache.org/manual/running.html): lệnh chạy, logger và các tham số Ant.
- [Apache Ant Manual — Buildfile](https://ant.apache.org/manual/using.html): project, target và quan hệ phụ thuộc.
- [Apache Ant Manual — Javac](https://ant.apache.org/manual/Tasks/javac.html): biên dịch và giới hạn của cơ chế kiểm tra cập nhật.
- [Apache Ant Manual — JUnit](https://ant.apache.org/manual/Tasks/junit.html): chạy test và xử lý lỗi.
- [Apache Ant Manual — Jar](https://ant.apache.org/manual/Tasks/jar.html): tạo artifact và manifest.
- [Apache Ant Manual — UpToDate](https://ant.apache.org/manual/Tasks/uptodate.html): điều kiện xem đầu ra đã cập nhật.
- [Apache Ant Manual — Parallel](https://ant.apache.org/manual/Tasks/parallel.html): thực thi tác vụ song song.
- [Apache Ant Manual — Checksum](https://ant.apache.org/manual/Tasks/checksum.html): tạo và xác minh checksum artifact.
