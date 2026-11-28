# Tạo AOT cache, đo khởi động và so sánh với ứng dụng chạy không có cache

> **Chương:** Thực hành tổng hợp
>
> **Mục tiêu:** Dùng AOT cache của JDK 25 để giảm công việc class loading/linking và cải thiện warm-up nhờ method profiles. Bài thực hành tạo cache từ workload đại diện, xác minh cache được nạp, đo cùng một ứng dụng khi có và không có cache, rồi quyết định có nên đưa cache vào artifact triển khai hay không.

## 1. Kết quả cần đạt

Sau bài thực hành, bạn có thể:

1. Giải thích AOT cache lưu những thông tin nào và khác gì với native executable.
2. Build một artifact cố định bằng JDK 25.
3. Chạy training workload và tạo file .aot.
4. Dùng lại cache với đúng ứng dụng, JDK, hệ điều hành và kiến trúc CPU.
5. Xác minh JVM thực sự nạp cache.
6. Đo startup và warm-up theo cùng một workload, cả khi có và không có cache.
7. Đọc kết quả bằng median và phân tích độ biến thiên.
8. Quyết định có nên tạo lại cache trong CI cho mỗi bản phát hành.

**Lưu ý phiên bản:** JDK 25 bổ sung cách tạo cache một bước qua JEP 514 và đưa method-execution profiles vào cache qua JEP 515. Đây là quy trình được dùng trong bài. JDK 25.0.5.1+4 là bản cập nhật Oracle được phát hành ngày 17/11/2026 (BPR cập nhật ngày 24/11/2026); khi thực hiện, hãy dùng bản cập nhật mới nhất được vendor của bạn hỗ trợ và ghi lại chính xác build đã kiểm thử.

## 2. AOT cache là gì?

AOT là viết tắt của Ahead-of-Time. JVM thực hiện trước một phần công việc thường phải làm khi ứng dụng bắt đầu chạy, rồi lưu kết quả vào một cache để dùng ở lần chạy sau.

Trong JDK 25, AOT cache có thể chứa:

- Thông tin lớp đã được đọc, phân tích, nạp và liên kết.
- Một số heap object đã được khởi tạo trước.
- Method-execution profiles thu thập trong training run theo JEP 515.

Khi khởi động với cache, JVM có thể tái sử dụng các lớp và object đã chuẩn bị. Method profiles cũng giúp JIT compiler có thông tin về những phương thức nóng sớm hơn, nhờ đó bắt đầu tối ưu mã nhanh hơn.

AOT cache **không phải native executable**. Ứng dụng vẫn chạy trên JVM; JIT vẫn hoạt động và tiếp tục thu thập thông tin ở runtime. Cache giúp JVM giảm một phần công việc khởi động và warm-up.

### AOT cache và các tính năng liên quan

| Thành phần | Vai trò |
| --- | --- |
| AOT cache | Lưu artifact tối ưu hóa để JVM tái sử dụng khi chạy ứng dụng |
| CDS (Class Data Sharing) | Cơ chế chia sẻ dữ liệu lớp; là nền tảng liên quan đến việc chuẩn bị lớp trước khi chạy |
| JIT compiler | Biên dịch bytecode thành native code trong khi ứng dụng chạy |
| Native Image | Biên dịch ứng dụng thành executable riêng, có mô hình build và runtime khác JVM thông thường |

Với ứng dụng chạy trên JDK 25, hãy bắt đầu bằng AOT cache. Không cần tự tạo CDS archive thủ công bằng các cờ cũ nếu mục tiêu là dùng quy trình AOT cache hiện hành.

## 3. Những thay đổi quan trọng của AOT cache trong Java 25

| JEP | Phiên bản | Ý nghĩa |
| --- | --- | --- |
| JEP 483 — Ahead-of-Time Class Loading & Linking | JDK 24 | Giới thiệu AOT cache và mô hình training, assembly, production |
| JEP 514 — Ahead-of-Time Command-Line Ergonomics | JDK 25 | Cho phép tạo cache bằng một lần chạy với -XX:AOTCacheOutput |
| JEP 515 — Ahead-of-Time Method Profiling | JDK 25 | Đưa method profiles từ training run vào AOT cache để hỗ trợ warm-up |
| JEP 516 — Ahead-of-Time Object Caching with Any GC | JDK 26 | Mở rộng AOT object caching để dùng được với mọi garbage collector, bao gồm ZGC |

Trong JDK 25, lệnh -XX:AOTCacheOutput=... tự thực hiện training và assembly. JVM ghi nhận workload, sau đó khởi chạy một JVM phụ để tạo cache khi tiến trình training kết thúc. Đây là đường đi ngắn gọn nên dùng cho bài thực hành.

JDK 25 chưa hỗ trợ đầy đủ AOT object caching với ZGC. Nếu ứng dụng bắt buộc dùng ZGC, cần cân nhắc giới hạn phiên bản này; JEP 516 đã giải quyết giới hạn đó từ JDK 26. Không áp dụng giới hạn của JDK 25 cho các JDK mới hơn mà không kiểm tra tài liệu tương ứng.

## 4. Mô hình ba giai đoạn

Dù JDK 25 có thể gộp hai bước đầu vào một lệnh, hãy hiểu ba giai đoạn logic:

~~~text
TRAINING
Chạy ứng dụng với workload đại diện
        |
        v
Ghi nhận lớp, object và method profiles
        |
        v
ASSEMBLY
Tạo file AOT cache (.aot)
        |
        v
PRODUCTION
Khởi chạy cùng ứng dụng với -XX:AOTCache
        |
        v
Đo startup và warm-up
~~~

Training trả lời câu hỏi: ứng dụng thực sự nạp lớp nào, khởi tạo object nào và gọi những phương thức nào thường xuyên? Cache có giá trị khi câu trả lời này gần với workload production.

Nếu training chỉ chạy startup rồi thoát, cache có thể ghi nhận tốt phần khởi tạo nhưng thiếu method profiles cho các request chính. Nếu training chạy một bộ test khổng lồ không giống production, cache có thể chứa nhiều lớp không cần thiết và profile sai đường chạy quan trọng.

## 5. Chuẩn bị môi trường và artifact

Bài thực hành dùng ứng dụng Java command-line nhỏ để có thể tái lập toàn bộ vòng đời. Có thể thay bằng ứng dụng thực tế sau khi đã nắm quy trình.

### 5.1. Kiểm tra JDK

Dùng cùng JDK 25 cho compile, training và production run:

~~~bash
java --version
javac --version
~~~

Ghi lại vendor và full version string của JDK, hệ điều hành, kiến trúc CPU, garbage collector và các JVM options quan trọng.

Không chỉ ghi Java 25; cache được tạo cho một ứng dụng, một JDK release và một cặp OS/CPU architecture cụ thể. Khi đổi một trong các yếu tố này, hãy tạo lại cache.

### 5.2. Tạo source code demo

Tạo file src/main/java/com/example/AotDemo.java:

~~~java
package com.example;

import java.util.Locale;

public final class AotDemo {

    private static final int OPERATIONS = 120_000;

    private AotDemo() {
    }

    public static void main(String[] args) {
        long started = System.nanoTime();
        long checksum = 0;

        for (int i = 0; i < OPERATIONS; i++) {
            boolean premium = (i % 3) == 0;
            checksum += calculateOrderTotal(i, premium);
        }

        double applicationWorkMs =
                (System.nanoTime() - started) / 1_000_000.0;

        System.out.printf(
                Locale.ROOT,
                "operations=%d appWorkMs=%.3f checksum=%d%n",
                OPERATIONS,
                applicationWorkMs,
                checksum);
    }

    private static long calculateOrderTotal(int orderId, boolean premium) {
        long subtotal = 1_000L + (orderId % 997) * 17L;

        if (premium) {
            subtotal = subtotal * 95 / 100;
        }

        return applyTax(subtotal);
    }

    private static long applyTax(long amount) {
        return amount + amount * 8 / 100;
    }
}
~~~

Chương trình gọi lặp lại calculateOrderTotal() và applyTax(), tạo một workload hữu hạn để training kết thúc bình thường. Đây chỉ là workload minh họa. Với ứng dụng thật, hãy dùng các thao tác nghiệp vụ, endpoint và dữ liệu đại diện cho production.

Trường appWorkMs chỉ đo phần thân workload sau khi main() bắt đầu. Nó **không đo toàn bộ thời gian JVM khởi động**. Phần benchmark bên dưới dùng đồng hồ bên ngoài để đo cả tiến trình.

### 5.3. Compile và đóng gói một lần

Trên Linux hoặc macOS:

~~~bash
mkdir -p build/classes
javac --release 25 -d build/classes src/main/java/com/example/AotDemo.java
jar --create --file build/aot-demo.jar --main-class com.example.AotDemo -C build/classes .
~~~

Trên PowerShell, có thể tạo thư mục bằng New-Item -ItemType Directory -Force build/classes, sau đó chạy hai lệnh javac và jar tương tự.

Với ứng dụng nhiều dependency, đóng gói theo quy trình build hiện tại của dự án, sau đó dùng đúng danh sách JAR trên classpath khi training và production.

**Không build lại JAR giữa training và benchmark.** Cache gắn với ứng dụng và classpath đã dùng khi tạo. Nếu thay bytecode, dependency hoặc nội dung JAR, phải tạo cache mới.

## 6. Tạo AOT cache bằng một lệnh trong JDK 25

Chạy workload training và yêu cầu JVM ghi cache:

~~~bash
java -XX:AOTCacheOutput=build/aot-demo.aot -cp build/aot-demo.jar com.example.AotDemo
~~~

JDK 25 thực hiện:

1. Chạy ứng dụng ở chế độ training.
2. Ghi nhận các lớp, object và method profiles được quan sát.
3. Khi ứng dụng kết thúc, khởi chạy JVM phụ để assembly.
4. Ghi cache vào build/aot-demo.aot.

Ứng dụng demo tự kết thúc nên đây là một training run hữu hạn. Với server chạy liên tục, cần có cách kết thúc recording có kiểm soát; không dừng tiến trình bằng cách kill cưỡng bức trước khi cache được ghi xong.

Sau khi lệnh hoàn tất, kiểm tra file:

~~~bash
ls -lh build/aot-demo.aot
~~~

Trên PowerShell:

~~~powershell
Get-Item build/aot-demo.aot | Select-Object Name, Length, LastWriteTime
~~~

Nếu file chưa xuất hiện, kiểm tra exit code và log của cả training lẫn tiến trình assembly. Cache được ghi khi JVM kết thúc; một lần training bị dừng cưỡng bức có thể không tạo được cache hợp lệ.

### 6.1. Vì sao workload training phải giống production?

Method profiles trong JDK 25 giúp JIT có thông tin về những phương thức thường được gọi. Nếu training chỉ thực hiện startup, các phương thức xử lý request chưa chắc được nhận diện là hot.

Với ứng dụng web hoặc service:

- Chạy các route chính, không chỉ health check.
- Dùng payload và kích thước dữ liệu gần với production.
- Bao gồm các luồng xác thực, serialization, truy cập dữ liệu và nghiệp vụ thường gặp.
- Để workload chạy đủ lâu và đủ số lần để các đường code nóng xuất hiện.
- Tránh chạy các test framework hoặc test suite không đại diện nếu chúng chỉ làm nạp thêm nhiều lớp phụ.

Training có thể dựa trên integration test hoặc một lượt traffic production-like. Chọn cách nào thì giữ nguyên artifact và classpath giữa training với production.

## 7. Xác minh cache có thể được nạp

Trước khi benchmark, chạy một lần kiểm tra nghiêm ngặt trên JDK 25:

~~~bash
java -XX:AOTMode=on -XX:AOTCache=build/aot-demo.aot -Xlog:aot -cp build/aot-demo.jar com.example.AotDemo
~~~

Trong JDK 25, AOTMode=on yêu cầu JVM nạp cache; nếu cache không tồn tại hoặc không tương thích, JVM báo lỗi và dừng. Đây là chế độ kiểm tra, không phải lựa chọn mặc định cho production.

Lưu ý khi nâng JDK: tài liệu JDK 27 xem on là alias của required và khuyến nghị không dùng on trong cấu hình mới. Nếu chuyển bài thực hành sang JDK 27, dùng -XX:AOTMode=required cho kiểm tra fail-fast; chế độ auto vẫn phù hợp cho production. Lệnh -XX:AOTMode=on ở ví dụ trên dành cho runtime JDK 25.

Nếu muốn kiểm tra lớp nào được nạp từ cache, có thể bật thêm log class loading:

~~~bash
java -XX:AOTMode=on -XX:AOTCache=build/aot-demo.aot -Xlog:aot,class+load=info -cp build/aot-demo.jar com.example.AotDemo
~~~

Log class+load giúp xem nguồn nạp của lớp. Dùng log trong lần xác minh riêng; không bật log chi tiết khi đo hiệu năng chính thức vì việc ghi log có thể làm thay đổi kết quả.

### Chế độ production

Trong production, dùng chế độ auto:

~~~bash
java -XX:AOTMode=auto -XX:AOTCache=build/aot-demo.aot -cp build/aot-demo.jar com.example.AotDemo
~~~

auto là mặc định của JDK 25. Khi cache tương thích, JVM sử dụng cache. Nếu không thể nạp cache, JVM tiếp tục chạy ứng dụng mà không có cache. Cách này phù hợp với môi trường production vì lỗi tối ưu hóa không làm ứng dụng ngừng khởi động.

Có thể giữ -Xlog:aot trong giai đoạn rollout để quan sát cache được sử dụng hay bị bỏ qua. Sau khi xác nhận ổn định, điều chỉnh log theo chính sách vận hành.

## 8. Chạy baseline không có cache

Để có nhóm đối chứng rõ ràng, tắt AOT cache:

~~~bash
java -XX:AOTMode=off -cp build/aot-demo.jar com.example.AotDemo
~~~

AOTMode=off bảo đảm lần chạy này không dùng AOT cache. Dùng cùng JDK vendor/build, JAR và classpath, JVM options khác, input, workload, máy và container limits.

Hai lệnh benchmark tương ứng:

~~~bash
# Baseline
java -XX:AOTMode=off -cp build/aot-demo.jar com.example.AotDemo

# Có cache
java -XX:AOTMode=auto -XX:AOTCache=build/aot-demo.aot -cp build/aot-demo.jar com.example.AotDemo
~~~

Không tính thời gian tạo cache vào thời gian startup production. Training và assembly là chi phí chuẩn bị trước, còn benchmark chỉ đo các lần chạy sử dụng artifact đã sẵn sàng.

## 9. Đo thời gian khởi động và warm-up

Một phép đo tốt cần tách hai câu hỏi:

**Startup:** từ lúc tiến trình JVM được tạo đến khi ứng dụng sẵn sàng nhận công việc đầu tiên mất bao lâu?

**Warm-up:** sau khi đã sẵn sàng, ứng dụng cần bao lâu để đạt throughput/latency ổn định?

Với chương trình CLI hữu hạn, có thể đo thời gian từ lúc khởi chạy java đến khi tiến trình kết thúc. Con số đó bao gồm JVM startup cộng workload của chương trình. Trường appWorkMs trong output giúp quan sát riêng thời gian thân chương trình, nhưng không thay thế phép đo từ bên ngoài.

Với server:

- Đo từ thời điểm tạo process/container đến khi readiness endpoint thành công.
- Sau readiness, gửi cùng một lượng request và ghi latency/throughput theo từng khoảng thời gian.
- Không dùng thời điểm log Started làm readiness nếu ứng dụng vẫn chưa nhận được request nghiệp vụ.

### 9.1. Quy trình benchmark đề xuất

1. Tạo cache một lần từ artifact cố định.
2. Xác minh cache có thể nạp bằng chế độ kiểm tra.
3. Chạy mỗi biến thể bằng một JVM process mới.
4. Thực hiện tối thiểu 20–30 lần cho mỗi biến thể.
5. Luân phiên thứ tự chạy có cache và không cache để giảm ảnh hưởng của nhiệt độ CPU hoặc tải nền.
6. Ghi lại thời gian từng lần chạy, không chỉ ghi giá trị tốt nhất.
7. So sánh median và phân bố kết quả; nếu cần, báo thêm p90/p95 với đủ số mẫu.
8. Lặp lại trên đúng runtime image và cấu hình tài nguyên dự kiến deploy.

Không kết luận từ một lần chạy. Các yếu tố như JIT warm-up, filesystem page cache, CPU frequency scaling, antivirus, background process và container CPU quota có thể làm kết quả thay đổi đáng kể.

### 9.2. Script đo bằng PowerShell

Đo 30 lần cho mỗi biến thể, luân phiên thứ tự và ghi kết quả ra CSV:

~~~powershell
$rows = [System.Collections.Generic.List[object]]::new()

for ($i = 0; $i -lt 30; $i++) {
    if (($i % 2) -eq 0) {
        $variants = @("no-cache", "aot")
    }
    else {
        $variants = @("aot", "no-cache")
    }

    foreach ($variant in $variants) {
        if ($variant -eq "no-cache") {
            $jvmArgs = @(
                "-XX:AOTMode=off",
                "-cp", "build/aot-demo.jar",
                "com.example.AotDemo"
            )
        }
        else {
            $jvmArgs = @(
                "-XX:AOTMode=auto",
                "-XX:AOTCache=build/aot-demo.aot",
                "-cp", "build/aot-demo.jar",
                "com.example.AotDemo"
            )
        }

        $watch = [System.Diagnostics.Stopwatch]::StartNew()
        & java @jvmArgs | Out-Null
        $exitCode = $LASTEXITCODE
        $watch.Stop()

        if ($exitCode -ne 0) {
            throw "Java process failed: variant=$variant exitCode=$exitCode"
        }

        $rows.Add([pscustomobject]@{
            Variant = $variant
            Run = $i + 1
            ElapsedMs = $watch.Elapsed.TotalMilliseconds
        })
    }
}

$rows | Export-Csv build/aot-results.csv -NoTypeInformation

$rows | Group-Object Variant | ForEach-Object {
    $values = @($_.Group.ElapsedMs | Sort-Object)
    $middle = [int][Math]::Floor($values.Count / 2)

    if (($values.Count % 2) -eq 0) {
        $median = ($values[$middle - 1] + $values[$middle]) / 2
    }
    else {
        $median = $values[$middle]
    }

    [pscustomobject]@{
        Variant = $_.Name
        Runs = $values.Count
        MedianMs = [Math]::Round($median, 2)
        MinMs = [Math]::Round($values[0], 2)
        MaxMs = [Math]::Round($values[-1], 2)
    }
} | Format-Table -AutoSize
~~~

Script này đo toàn bộ thời gian process, bao gồm khởi tạo JVM và workload CLI. Với server, thay tiêu chí kết thúc process bằng thời điểm readiness và dùng load generator để đo warm-up.

### 9.3. Bảng kết quả cần lưu

| Biến thể | Số lần chạy | Median startup/process | p95 | Ghi chú |
| --- | ---: | ---: | ---: | --- |
| Không cache | 30 | Điền kết quả | Điền kết quả | AOTMode=off |
| Có cache | 30 | Điền kết quả | Điền kết quả | AOTMode=auto, cache được xác nhận |

Tính mức thay đổi theo median:

\[
\text{Improvement (\%)} =
\frac{T_{\text{no-cache}} - T_{\text{AOT}}}
{T_{\text{no-cache}}} \times 100
\]

Giá trị dương nghĩa là biến thể có cache nhanh hơn theo phép đo đó. Nếu kết quả gần 0 hoặc thay đổi theo từng lần chạy, lợi ích có thể nhỏ hơn nhiễu đo.

Không dùng một tỷ lệ tăng tốc được công bố trong bài viết hoặc JEP làm cam kết cho ứng dụng của bạn. Kết quả phụ thuộc số lớp, cách khởi tạo, workload, phần cứng và cách đo.

## 10. Đo warm-up riêng

JEP 515 bổ sung method profiles vào AOT cache để JIT có thể bắt đầu tối ưu sớm hơn. Do đó, ngoài startup, cần đo tốc độ đạt trạng thái ổn định.

Với server, có thể chia traffic sau readiness thành các cửa sổ:

| Cửa sổ | Điều cần quan sát |
| --- | --- |
| Request đầu tiên | Latency ngay sau readiness |
| 1–10 giây đầu | JIT bắt đầu tối ưu các đường chạy nóng |
| 10–60 giây | Throughput và latency có tiến gần trạng thái ổn định không |
| Sau khi ổn định | So sánh throughput/latency dài hạn giữa hai biến thể |

Nếu AOT cache giúp readiness nhanh hơn nhưng throughput dài hạn không đổi, đó vẫn có thể là lợi ích đáng giá với workload scale-to-zero hoặc autoscaling. Nếu startup nhanh hơn nhưng latency sau đó xấu đi, cần phân tích profile training và hành vi JIT trước khi phát hành.

Không chỉ đo lần chạy đầu tiên rồi kết luận. AOT cache là một tối ưu hóa; phải kiểm tra cả startup, warm-up và steady-state.

## 11. Yêu cầu tương thích của cache

AOT cache không phải file dùng chung cho mọi ứng dụng. Các điều kiện chính:

| Thành phần | Yêu cầu |
| --- | --- |
| Ứng dụng | Cùng artifact và cấu trúc classpath/module path đã dùng khi training |
| JDK | Cùng JDK release; nên pin cùng vendor/build cho training và production |
| Hệ điều hành | Cùng OS |
| CPU | Cùng architecture |
| JAR | Giữ nguyên nội dung và timestamp của JAR giữa training và production |
| Classpath | Dùng danh sách JAR rõ ràng; tránh directory, wildcard và nested JAR trong classpath training |

Classpath production phải chứa classpath training theo cùng thứ tự; có thể thêm JAR hoặc directory ở cuối theo điều kiện của cache. Các phần thêm vào cuối không được xem là đã cache.

Hãy tạo lại cache khi:

- Build lại ứng dụng hoặc thay đổi bytecode.
- Thêm, xóa hoặc cập nhật dependency.
- Thay đổi classpath/module path.
- Nâng JDK release.
- Thay đổi OS hoặc CPU architecture.
- Thay đổi cấu hình JVM theo cách làm cache không còn tương thích.

Đừng copy cache từ máy x64 sang AArch64, từ Linux sang Windows hoặc từ JDK 25 sang JDK release khác.

## 12. Tích hợp cache vào pipeline và container

Một pipeline phát hành có thể gồm:

~~~text
1. Build artifact bằng JDK đã pin
2. Lưu checksum và metadata artifact
3. Chạy training trên artifact đó với workload đại diện
4. Tạo file AOT cache
5. Xác minh cache có thể nạp bằng AOTMode=on
6. Đo baseline và cache trên cùng runtime image
7. Đóng gói artifact + cache vào image theo OS/CPU mục tiêu
8. Chạy smoke test trong image cuối
9. Promote đúng image đã được kiểm thử
~~~

Đặt cache gần artifact, ví dụ:

~~~text
release/
  app.jar
  app.aot
  build-info.txt
~~~

Trong container, cache phải được copy vào đúng đường dẫn mà entrypoint sử dụng:

~~~dockerfile
FROM eclipse-temurin:25-jre
WORKDIR /app
COPY release/app.jar /app/app.jar
COPY release/app.aot /app/app.aot
ENTRYPOINT ["java", "-XX:AOTMode=auto", "-XX:AOTCache=/app/app.aot", "-jar", "/app/app.jar"]
~~~

Đây là ví dụ minh họa. Image release thực tế phải pin tag patch và digest, cùng vendor/build đã dùng trong training và kiểm thử. Không dùng cache được tạo trên build host khác OS/architecture với container production.

Không tạo cache một lần rồi dùng vô thời hạn. Cache thuộc về trạng thái cụ thể của artifact và runtime; mỗi release mới cần tạo và kiểm tra cache tương ứng.

## 13. Trường hợp ứng dụng Spring Boot

Với executable JAR của Spring Boot, hãy dùng chế độ extract để có classpath phù hợp với AOT cache:

~~~bash
java -Djarmode=tools -jar my-app.jar extract --destination application
~~~

Chuyển vào thư mục được extract và tạo cache theo hướng dẫn của phiên bản Spring Boot đang dùng. Khi dùng Java 25+, training nên chạy một phần workload production-like để thu thập method profiles, thay vì chỉ khởi tạo ApplicationContext rồi thoát ngay.

Quy trình khái niệm:

1. Extract executable JAR.
2. Khởi chạy ứng dụng đã extract với -XX:AOTCacheOutput=app.aot.
3. Gửi traffic đại diện vào ứng dụng.
4. Dừng ứng dụng một cách graceful để hoàn tất ghi cache.
5. Khởi chạy lại với -XX:AOTCache=app.aot.
6. Chạy cùng readiness probe và benchmark request.

-Dspring.context.exit=onRefresh vẫn hữu ích nếu mục tiêu chỉ là cache phần startup/context initialization. Nhưng với Java 25, cách này không đại diện cho các method profiles của request production; không dùng nó làm training duy nhất nếu muốn tối ưu cả warm-up.

Cache phải được dùng với cùng extracted application/classpath. Nếu chuyển lại sang chạy JAR lồng nhau theo một classpath khác, cache có thể không có tác dụng.

## 14. Quy trình riêng cho ứng dụng chạy lâu dài

Với ứng dụng server không tự kết thúc, training run cần được dừng có kiểm soát sau khi đã chạy workload đại diện. JDK bắt đầu ghi AOT artifacts theo JVM options và kết thúc recording khi JVM thoát hoặc khi recording được kết thúc qua management interface.

JDK 25 cung cấp HotSpotAOTCacheMXBean.endRecording() để kết thúc recording đang chạy và chờ artifacts được ghi hoàn tất. API này phù hợp cho một tác vụ điều phối bên ngoài khi không muốn chèn logic training vào code nghiệp vụ.

Không dùng kill cưỡng bức để kết thúc training. Hãy bảo đảm recording kết thúc và file cache được ghi hoàn chỉnh trước khi đóng gói.

## 15. Tách training và assembly khi thiếu bộ nhớ

Lệnh một bước -XX:AOTCacheOutput=... thuận tiện, nhưng JVM phụ dùng cho assembly cần heap riêng. Trong môi trường giới hạn bộ nhớ, mức sử dụng đỉnh có thể tăng đáng kể so với heap của training process.

Trong workflow một bước của JDK 25, JVM phụ assembly dùng heap riêng có cùng kích thước với heap của training run. Vì vậy, nếu training chạy với -Xmx2g, môi trường có thể cần xấp xỉ 4 GB heap capacity cho hai JVM trong giai đoạn chuyển tiếp, chưa tính native memory và các tiến trình khác. Nếu container/CI runner không đủ RAM, hãy tách record và create thành hai job hoặc giảm heap phù hợp.

Nếu cần tách hai giai đoạn, JDK 25 vẫn hỗ trợ quy trình explicit configuration:

~~~bash
# Training: ghi cấu hình
java -XX:AOTMode=record -XX:AOTConfiguration=build/app.aotconfig -cp build/aot-demo.jar com.example.AotDemo

# Assembly: tạo cache từ cấu hình
java -XX:AOTMode=create -XX:AOTConfiguration=build/app.aotconfig -XX:AOTCache=build/aot-demo.aot -cp build/aot-demo.jar
~~~

Ở quy trình này, training và assembly có thể chạy ở hai bước CI riêng, miễn là JDK release, OS/CPU và ứng dụng phù hợp. Đây là lựa chọn khi cần tách tài nguyên; với ứng dụng thông thường, ưu tiên lệnh một bước của JDK 25.

## 16. Giới hạn và nguyên tắc vận hành

- AOT cache chỉ là tối ưu hóa. Ứng dụng phải chạy đúng ngay cả khi không có cache.
- Không phải mọi JVM option hoặc JVMTI agent đều tương thích với cache.
- Training workload thiếu đại diện có thể tạo cache ít hữu ích hoặc làm warm-up không đúng như production.
- Tạo cache có chi phí CPU và bộ nhớ; đưa chi phí đó vào pipeline, không tính vào startup production.
- Cache có thể lớn; đo dung lượng và thời gian tạo để đánh giá chi phí lưu trữ/phân phối.
- Không dùng cache thay cho việc tối ưu dependency, classpath hoặc startup logic không cần thiết.
- Với JDK 25, AOT object caching chưa hỗ trợ ZGC; JDK 26 đã mở rộng hỗ trợ qua JEP 516.
- Khi nâng JDK, build lại cache bằng JDK mục tiêu và chạy lại benchmark.

## 17. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tạo được file .aot | Training chưa kết thúc bình thường hoặc assembly thất bại | Kiểm tra exit code và log JVM phụ; chạy lại training |
| Cache không nạp được | Sai JDK, OS/CPU, artifact hoặc JVM options | Dùng cùng môi trường; xác minh bằng AOTMode=on |
| Ứng dụng vẫn chạy nhưng không nhanh hơn | auto bỏ qua cache do không tương thích hoặc training không đại diện | Dùng -Xlog:aot, kiểm tra classpath và workload |
| Cache không chứa đường xử lý chính | Training chỉ chạy startup hoặc health check | Gửi request production-like trong training |
| Chạy được local nhưng không chạy trong container | OS/architecture/JDK khác hoặc cache không được copy | Tạo cache trong cùng image/runtime target và kiểm tra đường dẫn |
| Cache vô hiệu sau lần build mới | Artifact/dependency thay đổi | Tạo cache mới cho mỗi release |
| Cache không dùng được với ZGC trên JDK 25 | Giới hạn AOT object caching của JDK 25 | Dùng GC được hỗ trợ trên JDK 25 hoặc nâng JDK lên bản có JEP 516 |
| Training một bước hết bộ nhớ | JVM phụ assembly cần heap riêng | Giảm heap phù hợp hoặc tách record/create thành hai job |
| Startup nhanh hơn nhưng warm-up không cải thiện | Training không ghi nhận method profiles đại diện | Bổ sung workload request thật và đo lại |
| Kết quả benchmark không ổn định | Số lần chạy ít, tải nền hoặc điều kiện CPU thay đổi | Tăng số mẫu, luân phiên biến thể và báo median/phân bố |

## 18. Bài tập thực hành

### Bài A — Tạo cache

Build AotDemo bằng JDK 25, tạo JAR và chạy training với -XX:AOTCacheOutput.

**Điều kiện đạt:** file .aot được tạo sau khi JVM training và assembly kết thúc.

### Bài B — Xác minh cache

Chạy ứng dụng với -XX:AOTMode=on, -XX:AOTCache và -Xlog:aot.

**Điều kiện đạt:** JVM nạp cache thành công và ứng dụng hoàn tất workload.

### Bài C — So sánh có và không có cache

Chạy baseline với AOTMode=off, sau đó chạy với AOTMode=auto và cache. Dùng script PowerShell ở phần 9 để thu thập 30 mẫu mỗi biến thể.

**Điều kiện đạt:** có CSV kết quả, median của mỗi biến thể và phần trăm thay đổi.

### Bài D — Kiểm tra warm-up

Chuyển workload demo thành một service có readiness endpoint hoặc dùng ứng dụng mẫu có request handler. Training với traffic đại diện và đo các cửa sổ request sau readiness.

**Điều kiện đạt:** có số đo startup riêng, latency/throughput trong warm-up và steady-state.

### Bài E — So sánh sau khi đổi artifact

Tạo cache, sau đó build lại ứng dụng hoặc thay đổi một dependency rồi thử dùng cache cũ.

**Điều kiện đạt:** giải thích vì sao cache gắn với trạng thái ứng dụng và đưa ra quy trình tái tạo cache trong release pipeline.

## 19. Checklist trước khi phát hành

- [ ] Dùng JDK 25 update đã được tổ chức phê duyệt và ghi lại full version string.
- [ ] Build artifact một lần và giữ nguyên giữa training, benchmark và production.
- [ ] Training workload đại diện cho các luồng nghiệp vụ thực tế.
- [ ] File .aot được ghi hoàn tất sau training/assembly.
- [ ] Cache được xác minh bằng chế độ kiểm tra nghiêm ngặt.
- [ ] Production dùng AOTMode=auto để fallback an toàn khi cache không nạp được.
- [ ] JDK, OS, CPU architecture, classpath và JVM options tương thích.
- [ ] JAR timestamps và thứ tự classpath được giữ nguyên.
- [ ] Đo startup và warm-up riêng; mỗi biến thể có đủ số lần chạy.
- [ ] Báo median và phân bố, không chỉ báo lần chạy nhanh nhất.
- [ ] Benchmark được thực hiện trong runtime image gần với production.
- [ ] Tạo lại cache sau mỗi lần thay đổi artifact hoặc dependency.
- [ ] Đã đánh giá dung lượng cache và chi phí training/assembly.
- [ ] Đã kiểm tra giới hạn garbage collector của đúng JDK mục tiêu.

## 20. Tài liệu tham khảo

1. [JEP 483 — Ahead-of-Time Class Loading & Linking](https://openjdk.org/jeps/483): thiết kế AOT cache và các điều kiện tương thích.
2. [JEP 514 — Ahead-of-Time Command-Line Ergonomics](https://openjdk.org/jeps/514): quy trình tạo AOT cache một bước trong JDK 25.
3. [JEP 515 — Ahead-of-Time Method Profiling](https://openjdk.org/jeps/515): method profiles được lưu trong cache để hỗ trợ warm-up.
4. [Oracle Java 25 — java command, Ahead-of-Time Cache](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): AOTCacheOutput, AOTCache, AOTConfiguration, AOTMode và logging.
5. [Java SE 25 — HotSpotAOTCacheMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/jdk/management/HotSpotAOTCacheMXBean.html): kết thúc AOT recording qua endRecording().
6. [Inside.java — Run Into the New Year with Java’s Ahead-of-Time Cache Optimizations](https://inside.java/2026/01/09/run-aot-cache/): training workload, một bước tạo cache, điều kiện tương thích và xác minh.
7. [JEP 516 — Ahead-of-Time Object Caching with Any GC](https://openjdk.org/jeps/516): thay đổi hỗ trợ ZGC từ JDK 26.
8. [Oracle JDK 25 Release Notes](https://www.oracle.com/java/technologies/javase/25all-relnotes.html): các bản cập nhật JDK 25 và thông tin phiên bản.
9. [Spring Framework — JVM AOT Cache](https://docs.spring.io/spring-framework/reference/integration/aot-cache.html): cách tạo và dùng cache cho ứng dụng Spring, gồm lưu ý method profiles trên Java 25+.
10. [Spring Boot — AOT Cache](https://docs.spring.io/spring-boot/reference/packaging/aot-cache.html): quy trình extract executable JAR và sử dụng AOT cache.
11. [Oracle Java 27 — java command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): thay đổi cách đặt tên strict AOT mode, trong đó on là alias của required và không còn được khuyến nghị.

**Ghi nhớ:** Với Java 25, hãy tạo cache bằng -XX:AOTCacheOutput, chạy workload gần production để thu thập cả method profiles, xác minh cache trước khi benchmark và dùng AOTMode=auto trong production. Chỉ so sánh khi artifact, JDK, classpath, OS/CPU và workload giống nhau; đo cả startup lẫn warm-up trước khi quyết định phát hành cache.
