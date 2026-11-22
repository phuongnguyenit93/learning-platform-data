# Đo hiệu năng Java Collections bằng JMH: dữ liệu, warmup và so sánh công bằng

## 1. Mục tiêu và câu hỏi đo lường

`Java Microbenchmark Harness` (JMH) là công cụ của OpenJDK để đo những thao tác Java đủ nhỏ mà tác động của JIT, tối ưu hóa mã, GC, khởi động JVM và nhiễu hệ thống có thể làm phép đo thủ công sai lệch. Trong module `Java core - collection`, ta dùng JMH để trả lời một câu hỏi cụ thể: **với tập dữ liệu và kiểu truy vấn xác định, thời gian kiểm tra phần tử bằng `ArrayList.contains` và `HashSet.contains` khác nhau thế nào?**

Bài học cần phân biệt ba điều:

- **Đúng chức năng:** hai cấu trúc phải trả về cùng kết quả cho cùng khóa; mọi khóa thử đều tồn tại (hit) hoặc đều không tồn tại (miss) theo kịch bản.
- **Đúng phạm vi đo:** benchmark bên dưới chỉ đo `contains` cùng chi phí lấy khóa truy vấn; khâu tạo collection, nạp dữ liệu và tạo khóa được làm ở `@Setup`, ngoài phần đo.
- **Đúng quyết định kỹ thuật:** kết quả một phép tra cứu chưa đủ quyết định giữa `List` và `Set`. Còn phải xét thứ tự, phần tử trùng, chi phí xây dựng/cập nhật, bộ nhớ, tính địa phương của cache và tỷ lệ đọc/ghi trong ứng dụng.

Về kỳ vọng thuật toán, một lần `ArrayList.contains` quét tuần tự và có độ phức tạp O(n) trong trường hợp xấu nhất; `HashSet.contains` thường có chi phí trung bình gần O(1) với hàm băm và phân bố khóa phù hợp, nhưng không được cam kết luôn O(1) cho mọi trường hợp. JMH kiểm tra hiệu năng **trong điều kiện đo**, không chứng minh mọi đầu vào hay mọi máy đều có cùng tỷ lệ nhanh/chậm.

## 2. Thiết kế phép so sánh trước khi chạy

Đặt giả thuyết: khi kích thước collection tăng, tra cứu bằng hash có thể có lợi hơn quét tuyến tính; với collection nhỏ, chi phí cố định của hashing và bộ nhớ có thể ảnh hưởng đến chênh lệch. Giữ những biến số sau minh bạch:

| Biến số | Thiết kế ví dụ | Vì sao cần kiểm soát |
| --- | --- | --- |
| Số phần tử (`size`) | 128, 8.192, 65.536 | Thấy cách hiệu năng đổi theo kích thước, tránh kết luận từ một kích thước. |
| Trường hợp tìm kiếm (`scenario`) | `hit` và `miss` | `ArrayList` có thể dừng sớm khi tìm thấy; tìm trượt thường phải quét hết. |
| Dữ liệu lưu trữ | Các `Integer` duy nhất từ 0 đến `size - 1` ở cả hai collection | Bảo đảm cùng nội dung logic và không có khác biệt do dữ liệu đầu vào. |
| Khóa thử | 1.024 khóa sinh bằng `Random` có seed cố định; hit nằm trong collection, miss nằm ngoài | Có nhiều khóa thay đổi qua các lời gọi, đồng thời có khả năng lặp lại thí nghiệm. |
| Môi trường | Cùng JDK, JVM options, CPU, số luồng, forks và điều kiện tải máy | Hạn chế nhiễu từ các yếu tố bên ngoài. |
| Công việc mỗi lần gọi | Một lần lấy khóa và một lần `contains` | So sánh cùng nhiệm vụ, không lẫn chi phí tạo dữ liệu. |

Không so trực tiếp `ArrayList.get(index)` với `HashSet.contains(value)`: đó là hai nghiệp vụ khác nhau. Tương tự, không so `new HashSet<>(list).contains(x)` với `list.contains(x)` rồi gọi kết quả là tốc độ **tra cứu**; phương án đầu đã cộng chi phí xây dựng cấu trúc băm. Nếu nghiệp vụ thật sự tạo set để tra cứu một lần, hãy đo **toàn bộ luồng xử lý đó** ở một benchmark riêng.

## 3. Tạo dự án JMH có cấu hình build đúng

Yêu cầu: JDK 17 trở lên, Maven và khả năng tải dependency từ Maven Central. Dùng Maven archetype chính thức của JMH để có annotation processor và JAR chạy độc lập; ví dụ cố định phiên bản JMH 1.37 để dễ tái lập.

~~~bash
mvn archetype:generate -B -DarchetypeGroupId=org.openjdk.jmh -DarchetypeArtifactId=jmh-java-benchmark-archetype -DarchetypeVersion=1.37 -DgroupId=org.sample -DartifactId=collection-jmh -Dversion=1.0-SNAPSHOT
cd collection-jmh
~~~

Tạo tệp `src/main/java/org/sample/CollectionLookupBenchmark.java` với nội dung đầy đủ bên dưới. Lớp mẫu do archetype sinh ra có thể giữ nguyên: khi chạy ta sẽ lọc đúng benchmark này.

## 4. Benchmark Java hoàn chỉnh

~~~java
package org.sample;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;
import java.util.concurrent.TimeUnit;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Measurement(iterations = 5, time = 1, timeUnit = TimeUnit.SECONDS)
@Fork(2)
public class CollectionLookupBenchmark {

    @State(Scope.Thread)
    public static class LookupData {
        @Param({"128", "8192", "65536"})
        public int size;

        @Param({"hit", "miss"})
        public String scenario;

        List<Integer> list;
        Set<Integer> set;
        Integer[] probes;
        int position;

        @Setup(Level.Trial)
        public void prepare() {
            list = new ArrayList<>(size);
            set = new HashSet<>();

            for (int i = 0; i < size; i++) {
                Integer value = Integer.valueOf(i);
                list.add(value);
                set.add(value);
            }

            Random random = new Random(2026L + size);
            probes = new Integer[1024];

            for (int i = 0; i < probes.length; i++) {
                int selected = random.nextInt(size);
                int key = scenario.equals("hit") ? selected : size + selected;
                probes[i] = Integer.valueOf(key);
            }
        }

        Integer nextProbe() {
            return probes[position++ & (probes.length - 1)];
        }
    }

    @Benchmark
    public boolean arrayListContains(LookupData data) {
        return data.list.contains(data.nextProbe());
    }

    @Benchmark
    public boolean hashSetContains(LookupData data) {
        return data.set.contains(data.nextProbe());
    }

    @Benchmark
    public Integer probeOnly(LookupData data) {
        return data.nextProbe();
    }
}
~~~

**Tại sao viết như vậy?**

1. `@State(Scope.Thread)` yêu cầu JMH cấp state riêng cho mỗi luồng benchmark. Collection chỉ được đọc, còn `position` thay đổi trong cùng luồng; không phát sinh tranh chấp ghi giữa các luồng. Các bộ sưu tập được chuẩn bị lại cho từng trial.
2. `@Param` tạo ma trận **3 kích thước × 2 kịch bản** cho mỗi benchmark. Ta xem từng cặp có cùng tham số trước khi so sánh hai cấu trúc.
3. `@Setup(Level.Trial)` nạp dữ liệu **trước khi đo**. Vì vậy kết quả không phải thời gian tạo `HashSet` hoặc `ArrayList`. Nếu câu hỏi là chi phí xây dựng, cần benchmark xây dựng riêng.
4. Seed cố định làm dữ liệu đầu vào ổn định giữa các lần chạy và giữa hai phương án. `probes` đã được tạo dưới dạng `Integer[]`, nên việc boxing và sinh số ngẫu nhiên không nằm trong thời gian `contains`; cả hai phương án truy vấn cùng loại khóa.
5. Mỗi `nextProbe()` đi qua 1.024 vị trí bằng phép AND vì 1.024 là lũy thừa của hai. Khóa thay đổi theo lời gọi, tránh chỉ đo một hằng số duy nhất. Benchmark vẫn bao gồm phần lấy khóa và tăng `position`; đây là chi phí nền chung, đặc biệt đáng chú ý khi thao tác tra cứu rất nhanh.
6. `hit` dùng khóa trong đoạn từ 0 đến `size - 1`; `miss` dùng từ `size` đến `2 × size - 1`. Vì vậy mọi lần gọi trong mỗi kịch bản trả về kết quả logic đã định: `true` hoặc `false`, giống nhau cho cả `List` lẫn `Set`.
7. Mỗi phương thức `@Benchmark` **trả về kết quả** để JMH tiêu thụ, làm giảm nguy cơ JIT xóa phép tính vì kết quả không được dùng (*dead-code elimination*). Nếu cần dùng nhiều kết quả trong cùng một lượt đo, có thể tiêm `Blackhole` và gọi `consume`.
8. `probeOnly` là phép đo tham khảo cho công việc chọn khóa. Không được lấy số đo của nó trừ thẳng khỏi số đo `contains` và xem hiệu số là độ trễ chính xác: JIT, tối ưu hóa và chi phí lời gọi của các benchmark có thể khác nhau.

### Các annotation ảnh hưởng đến phép đo

- `@BenchmarkMode(Mode.AverageTime)`: báo **thời gian trung bình cho một operation**, càng nhỏ càng tốt nếu ngữ nghĩa tương đương. Với throughput, dùng `Mode.Throughput` và đọc đơn vị operations/giây, khi đó càng cao càng tốt.
- `@OutputTimeUnit(TimeUnit.NANOSECONDS)`: trình bày kết quả dưới dạng `ns/op`, không bảo đảm phần cứng đo chính xác tuyệt đối đến từng nano giây.
- `@Warmup(iterations = 5, time = 1)`: 5 vòng làm nóng, mỗi vòng 1 giây; dữ liệu warmup không tính vào điểm số. JVM có thời gian tải lớp, JIT biên dịch và tối ưu đường chạy nóng.
- `@Measurement(iterations = 5, time = 1)`: tiếp theo là 5 vòng đo, mỗi vòng 1 giây cho một tập tham số và fork.
- `@Fork(2)`: chạy ở 2 tiến trình JVM con riêng biệt, giúp giảm phụ thuộc vào trạng thái một JVM. Dùng nhiều forks/iterations hơn khi cần độ tin cậy cao, chấp nhận thời gian chạy dài hơn.

Warmup **không tương đương** với chạy thử một lần bằng `System.nanoTime()`. JIT có thể biên dịch lại khi hồ sơ thực thi thay đổi; cấp phát và GC cũng có thể ảnh hưởng. JMH kiểm soát vòng warmup, measurement, fork và cách lấy mẫu, nhưng người thiết kế vẫn phải chọn workload hợp lý.

## 5. Build và chạy phép đo

Tại thư mục `collection-jmh`:

~~~bash
mvn clean verify
java -jar target/benchmarks.jar "CollectionLookupBenchmark.*" -t 1 -wi 5 -i 5 -w 1s -r 1s -f 2 -rf json -rff target/jmh-results.json
~~~

Ý nghĩa một số tham số CLI:

- `"CollectionLookupBenchmark.*"` chỉ chọn ba benchmark của lớp này; không chạy benchmark mẫu có sẵn của archetype.
- `-t 1` dùng một luồng benchmark; giảm nhiễu do tranh chấp CPU. Muốn đánh giá truy cập đồng thời, phải thiết kế benchmark riêng với state và mức cạnh tranh phù hợp.
- `-wi 5 -w 1s` là 5 vòng warmup, mỗi vòng 1 giây; `-i 5 -r 1s` là 5 vòng đo, mỗi vòng 1 giây. Tham số CLI ghi đè mặc định ở annotation.
- `-f 2` sử dụng 2 JVM forks; `-rf json -rff ...` ghi kết quả máy đọc được ra `target/jmh-results.json`.
- Để thử riêng một tình huống, có thể bổ sung `-p size=8192 -p scenario=hit` vào lệnh trên. Dùng tùy chọn `-h` của JAR để xem các cờ theo phiên bản JMH đang chạy.

Trước thí nghiệm chính, chạy smoke test ngắn với ít iterations để phát hiện lỗi cấu hình; không lấy điểm số smoke test làm kết luận. Khi đo chính thức, chạy máy ở điều kiện tương đối ổn định, tránh build nặng/chạy tác vụ nền, ghi rõ cấu hình phần cứng và môi trường Java. Kiểm tra nhiệt độ CPU, chế độ tiết kiệm điện, tần số, tài nguyên RAM và việc xuất hiện GC nếu dữ liệu đủ lớn.

Có thể chạy lại với profiler GC tích hợp của JMH:

~~~bash
java -jar target/benchmarks.jar "CollectionLookupBenchmark.*" -t 1 -f 2 -prof gc
~~~

Thông tin `gc.alloc.rate.norm` giúp xem byte được cấp phát trên mỗi operation trong điều kiện đo. Nó không đo trực tiếp tổng bộ nhớ mà collection đã chiếm khi dựng ở `@Setup`; muốn đánh giá footprint thực tế, dùng thêm đo bộ nhớ riêng có phương pháp kiểm soát.

## 6. Đọc kết quả và suy luận đúng

JMH xuất bảng với các cột như `Benchmark`, tham số `size`/`scenario`, `Mode`, `Cnt`, `Score`, `Error`, `Units`. Với `avgt` và `ns/op`, so `arrayListContains` với `hashSetContains` **trong đúng cùng kích thước, hit/miss, JDK, cấu hình và điều kiện chạy**. Hai nhóm số đo khác điều kiện không tạo thành so sánh kiểm soát.

Có thể tính tỷ lệ `Score(list) / Score(set)` khi cả hai đo cùng operation, score dương, đủ ổn định; tỷ lệ lớn hơn 1 biểu thị `HashSet` nhanh hơn về average time **trong trường hợp đo đó**. Báo cả điểm số, độ biến động/ước lượng sai số và số lần đo; không chỉ báo “nhanh hơn X lần”. Nếu chênh lệch cùng cỡ nhiễu, cần tăng phép lặp, xem phân tán giữa forks và chạy lại trong môi trường sạch hơn trước khi kết luận. `Error` không nên hiểu là bảo chứng rằng kết quả sẽ lặp lại y hệt trên máy khác.

Khi diễn giải, hãy trả lời lần lượt:

1. **`size` có ảnh hưởng gì?** Với tuyến tính, miss thường tốn nhiều lần so sánh hơn khi n tăng. Hash lookup có thể ổn định hơn nhưng phụ thuộc hash, cache, collision và tải bộ nhớ.
2. **`hit` khác `miss` ra sao?** List tìm thấy có thể kết thúc ở vị trí bất kỳ; list miss thường quét hết. Set hit và miss có đặc tính khác nhau về hash, so sánh khóa và nhánh rẽ.
3. **`probeOnly` đáng kể không?** Nếu thời gian chọn khóa chiếm tỷ trọng lớn so với lookup, phép đo nhỏ khó phân biệt. Có thể thiết kế benchmark nhiều thao tác trên một invocation và chuẩn hóa `@OperationsPerInvocation` khi cần, đồng thời phải cẩn thận để không kích hoạt loop optimizations làm sai kết quả.
4. **Cấu trúc nào phù hợp ứng dụng?** Nếu chỉ kiểm tra thành viên nhiều lần trên tập ổn định và chấp nhận bộ nhớ bổ sung, `HashSet` là ứng viên đáng thử. Nếu cần giữ thứ tự, cho phép trùng hoặc tập rất nhỏ, `ArrayList` có thể phù hợp hơn. Không đánh đồng performance của `contains` với performance mọi thao tác của collection.

**Phân biệt microbenchmark và end-to-end:** JMH chỉ trả lời tác vụ được định nghĩa. Quyết định triển khai còn cần dữ liệu sản xuất đại diện, độ trễ toàn luồng, throughput thực tế, bộ nhớ, GC, hiệu năng khi thêm/xóa, tính đúng đắn và hành vi khi chạy đồng thời.

## 7. Sai lầm thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách làm phù hợp |
| --- | --- | --- |
| Một lần chạy `System.nanoTime()` rồi kết luận | Chịu nhiễu khởi động, JIT, GC và scheduler | Dùng JMH với warmup, measurements và forks có kiểm soát. |
| Dùng một giá trị hằng, bỏ qua kết quả | JIT có thể gấp hằng hoặc bỏ phép tính | Dùng nhiều khóa đã chuẩn bị và trả về kết quả hoặc `Blackhole`. |
| Sinh `Random`, nạp dữ liệu, log, in console trong `@Benchmark` | Đo cả phần việc khác, I/O lấn át thao tác | Đưa fixture vào `@Setup(Level.Trial)` nếu chỉ đo lookup. |
| Mỗi bên nhận tập dữ liệu khác hoặc tỷ lệ hit khác | Khác workload nên không so sánh được | Dùng cùng quy tắc sinh, seed, kích thước và kịch bản. |
| Đo một `size` rất nhỏ rồi khái quát mọi quy mô | Bỏ qua chuyển dịch chi phí theo n và cache | Thử nhiều kích thước phù hợp dữ liệu thật. |
| So `List.get` với `Set.contains` hoặc bỏ qua chi phí xây set | So nghiệp vụ khác nhau, kết luận sai | Giữ cùng operation; thêm benchmark end-to-end nếu cần. |
| Cấp lại state bằng `@Setup(Level.Invocation)` một cách máy móc | Chi phí setup mỗi lời gọi và tương tác đo có thể đáng kể | Chọn đúng lifecycle; đọc rõ JMH xử lý phần setup và đo thao tác rất ngắn. |
| Chạy cùng lúc IDE, tải CPU cao hoặc đổi JDK giữa phép thử | Nhiễu hệ thống và JIT khác | Đo từ executable JAR, ghi cấu hình, kiểm soát môi trường. |
| Chỉ đọc điểm trung bình, bỏ qua forks/sai số | Dễ chọn phương án từ một kết quả không ổn định | Xem độ phân tán, chạy lặp lại và tái kiểm tra khi khác biệt nhỏ. |
| Cho rằng nhanh nhất theo `ns/op` là tối ưu toàn hệ thống | Không xét RAM, thiết lập, ghi, concurrency và GC | Ghép JMH với profiling và benchmark theo luồng nghiệp vụ thật. |

## 8. Quy trình áp dụng cho phép so sánh collection khác

Khi đổi sang `HashMap`/`TreeMap`, `ArrayList`/`LinkedList` hay `HashSet`/`TreeSet`, hãy bắt đầu bằng **một hành vi chung có cùng ý nghĩa** (ví dụ lookup cùng khóa hoặc duyệt toàn bộ cùng tập dữ liệu), rồi xác định rõ tập dữ liệu, kích thước, phân bố hit/miss, cách khởi tạo, số lượng thao tác, thứ tự chạy, số luồng và mục tiêu đầu ra. Tạo các dữ liệu thử đại diện ngoài thời gian đo; viết kiểm thử chức năng riêng để xác nhận kết quả trước khi benchmark; cho JMH warmup/measurement/fork đúng mức; cuối cùng diễn giải điểm số gắn với workload và trade-off.

Cần đánh giá nhiều chi phí thì tạo **nhiều benchmark có phạm vi tường minh**: một benchmark lookup trên cấu trúc đã dựng, một benchmark xây dựng cấu trúc, một benchmark cập nhật, và một phép đo workload kết hợp với tỷ lệ thao tác sát ứng dụng. Đừng gộp chúng thành một con số rồi gọi là “collection nhanh nhất”.

### Tài liệu đối chiếu

- Dự án JMH chính thức: https://github.com/openjdk/jmh
- Ví dụ về `@Param`: https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_27_Params.java
- Ví dụ về dead-code elimination: https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java
- Ví dụ về `Blackhole`: https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_09_Blackholes.java

**Kết quả mong đợi của bài thực hành:** tự chạy JMH trên JDK 17+, đọc đúng `ns/op` và tham số hit/miss, giải thích được vì sao cần warmup và forks, biết lựa chọn dữ liệu đại diện và phân biệt sự cải thiện của một thao tác lookup với lợi ích của cả ứng dụng.
