# Ảnh hưởng của khởi động JVM, JIT và tải nền đến phép đo

## 1. Đo cùng mã chưa chắc đang đo cùng trạng thái

Một đoạn Java có thể chạy khác nhau ở lần đầu và sau khi ứng dụng đã hoạt động một thời gian. Sự khác biệt không chỉ nằm ở thuật toán: JVM đang khởi động, lớp đang được nạp, mã đang được tối ưu và máy còn chạy các công việc khác.

Trước khi bấm đồng hồ, phải xác định câu hỏi:

| Mục tiêu | Phần cần đưa vào phép đo |
| --- | --- |
| Một công cụ dòng lệnh chạy một lần mất bao lâu? | Tạo tiến trình, khởi động JVM, nạp ứng dụng, xử lý và kết thúc theo ranh giới đã chọn |
| Dịch vụ bao lâu mới nhận được yêu cầu đầu tiên? | Khởi động tới điều kiện sẵn sàng thực sự |
| Yêu cầu đầu tiên chậm bao nhiêu? | Đường xử lý chưa được dùng trước đó, kể cả khởi tạo lười có liên quan |
| Một thao tác khi hệ thống đã ổn định nhanh bao nhiêu? | Giai đoạn vận hành sau điều kiện khởi động/làm nóng đã định nghĩa |
| Độ trễ khi hệ thống đang chịu tải là bao nhiêu? | Cả tranh chấp, hàng đợi, GC và tác động tài nguyên trong môi trường mục tiêu |

Không có một cách “bỏ vài lần đầu” đúng cho mọi mục tiêu. Nếu cần biết chi phí khởi động, bỏ giai đoạn đó sẽ bỏ luôn điều cần đo. Nếu muốn so sánh hiệu năng khi đã hoạt động ổn định, trộn nó với khởi động có thể che mất câu trả lời.

## 2. Khởi động JVM khác lần đầu đi qua một đường mã

### Khởi động tiến trình

Lệnh `java` khởi động JVM, nạp lớp được chỉ định rồi gọi `main()`. Các bước trước khi vào `main()` không nằm trong bộ đếm bắt đầu bằng `System.nanoTime()` ở dòng đầu của `main()`. Xem [The java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).

Muốn đo thời gian toàn tiến trình, cần bộ điều phối bên ngoài ghi thời gian trước khi tạo tiến trình và sau mốc kết thúc phù hợp. Muốn đo thời gian sẵn sàng của dịch vụ, cần một tín hiệu sẵn sàng có ý nghĩa, không chỉ dựa vào việc tiến trình đã tồn tại.

Cũng phải phân biệt hai chế độ chạy:

- `java MyProgram`: chạy lớp đã được biên dịch.
- `java MyProgram.java`: chế độ chạy tệp nguồn có thêm việc biên dịch nguồn trước khi gọi chương trình.

Nếu mục tiêu là đo ứng dụng đóng gói, không đưa chi phí biên dịch nguồn vào một phương án rồi đem so với phương án chạy class/JAR đã biên dịch.

### Lần đầu dùng chức năng

Ứng dụng đã khởi động vẫn có thể còn đường mã chưa được dùng. Lần đầu truy cập một chức năng có thể gặp:

- Nạp, liên kết và khởi tạo lớp liên quan.
- Khởi tạo bảng tra, dữ liệu tĩnh hoặc đối tượng dùng chung.
- Tạo serializer, bộ phân tích, pool hay bộ đệm theo nhu cầu.
- Mở kết nối tới dịch vụ bên ngoài hoặc làm đầy bộ nhớ đệm.

Các chi phí đó thuộc đường gọi đầu tiên nếu người dùng thực sự phải chờ chúng. Khởi động xong không đồng nghĩa mọi chức năng đã được làm nóng.

Khởi động một JVM mới cũng không bảo đảm máy đang ở trạng thái “lạnh hoàn toàn”: bộ nhớ đệm tệp của hệ điều hành hoặc dịch vụ ngoài có thể vẫn còn trạng thái từ lần chạy trước. Hãy đặt tên đúng cho điều kiện đã kiểm soát.

## 3. JIT có thể thay đổi cách mã được thực thi

Trên một JVM có biên dịch đúng lúc (Just-In-Time compilation, JIT), mã có thể bắt đầu bằng cách thực thi ít tối ưu hơn, sau đó được biên dịch/tối ưu dựa trên thông tin quan sát khi chạy.

Với HotSpot hiện đại, biên dịch theo tầng (tiered compilation) là một cơ chế điển hình: mã được thực thi, thu thập thông tin và có thể chuyển sang phiên bản tối ưu hơn. Đây là hành vi của triển khai JVM, không phải quy tắc rằng mọi phương thức Java đều được biên dịch sau cùng một số lần gọi. Xem [HotSpot: Tiered Compilation](https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html).

Những hệ quả cho phép đo:

- Lần gọi đầu và lần gọi sau có thể chạy các phiên bản mã khác nhau.
- Công việc biên dịch nền sử dụng tài nguyên, có thể ảnh hưởng phép đo đang diễn ra.
- Dữ liệu và kiểu đối tượng được gặp có thể tác động quyết định tối ưu.
- Một nhánh hiếm hoặc kiểu mới xuất hiện có thể làm các giả định tối ưu thay đổi.
- Thời gian có thể giảm, dao động hoặc thay đổi theo nhiều giai đoạn; không bảo đảm giảm đều.

Không quy mọi lần giảm thời gian cho JIT. Bộ nhớ đệm dữ liệu, nạp lớp, trạng thái CPU và tải nền cũng có thể thay đổi. Cần bằng chứng quan sát phù hợp để phân biệt nguyên nhân.

### Làm nóng phải đại diện cho công việc thật

Làm nóng (warmup) là cho hệ thống đi qua công việc trước giai đoạn đo chính, nhằm quan sát trạng thái phù hợp với câu hỏi về vận hành ổn định.

Nếu lúc làm nóng chỉ dùng một loại đầu vào nhỏ hoặc một kiểu triển khai, rồi lúc đo dùng dữ liệu lớn và nhiều kiểu khác, trạng thái được tạo ra có thể không đại diện.

Không có con số cố định “gọi 10.000 lần là JVM đã nóng”. Có ứng dụng vẫn tiếp tục nạp lớp, tối ưu hoặc thay đổi hành vi bộ nhớ sau mốc đó. Cần quan sát chuỗi kết quả theo thời gian và định nghĩa điều kiện đo của chính thí nghiệm.

## 4. Tải nền làm thay đổi cả cơ hội chạy và tài nguyên có thể dùng

Một phép đo thời gian đã trôi qua có thể bao gồm lúc luồng bị ngừng chạy hoặc đang chờ tài nguyên. Vì vậy, một đợt chậm chưa chắc phương thức vừa cần nhiều lệnh CPU hơn.

| Nguồn tác động | Điều có thể quan sát |
| --- | --- |
| Tiến trình khác tranh CPU | Luồng đo được cấp CPU chậm hơn |
| Công việc tranh bộ nhớ/băng thông | Truy cập dữ liệu chậm hơn dù thuật toán không đổi |
| I/O, mạng, dịch vụ phụ thuộc | Thời gian chờ tăng |
| GC và điểm dừng của JVM | Một số khoảng trễ tăng hoặc throughput thay đổi |
| Giới hạn CPU trong container/VM | Bị hạn chế thời gian chạy dù máy chủ còn tài nguyên |
| Chế độ nguồn, nhiệt độ, trạng thái CPU | Hiệu năng có thể khác giữa các lượt chạy |
| IDE, debugger, profiler hoặc log nhiều | Môi trường và chi phí đo bị thay đổi |

Tải nền có thể là nhiễu cần kiểm soát trong một microbenchmark, hoặc chính là điều kiện bắt buộc của bài thử chịu tải. Phải quyết định từ mục tiêu.

Ví dụ, chạy một máy hoàn toàn rảnh để so sánh chi phí một hàm là hợp lý. Nhưng lấy số đó cam kết độ trễ p99 khi dịch vụ cùng chạy nhiều tác vụ tranh CPU là suy rộng quá mức.

GC cũng không luôn là thứ phải loại bỏ. Nếu công việc thật tạo rác, chi phí thu hồi là một phần của vận hành. Có thể làm phép đo riêng để hiểu chi phí cấp phát/GC, nhưng cần ghi rõ ranh giới thay vì xóa các mẫu chậm khỏi báo cáo tổng thể.

## 5. Ví dụ chạy được: quan sát các đợt trong một JVM

Chương trình sau chạy tám đợt biến đổi một mảng. Các giá trị trong mảng thay đổi sau mỗi lượt, kết quả được giữ và in sau khi đo để không bỏ toàn bộ công việc như một kết quả không dùng.

Đây là **thí nghiệm quan sát theo giai đoạn**, không phải một microbenchmark đã kiểm soát đầy đủ. Nó không tự đo riêng chi phí JIT hay khởi động JVM.

Lưu thành `PhaseObservationDemo.java`:

```java
import java.util.Locale;

public class PhaseObservationDemo {
    static long transform(int[] values) {
        long checksum = 0;
        for (int i = 0; i < values.length; i++) {
            int x = values[i];
            x ^= x << 13;
            x ^= x >>> 17;
            x ^= x << 5;
            values[i] = x;
            checksum += x;
        }
        return checksum;
    }

    public static void main(String[] args) {
        int seed = args.length == 0 ? 1 : Integer.parseInt(args[0]);
        int[] data = new int[1024];
        for (int i = 0; i < data.length; i++) {
            data[i] = seed + i;
        }

        int phases = 8;
        int passes = 2000;
        long[] elapsed = new long[phases];
        long[] checksums = new long[phases];

        for (int phase = 0; phase < phases; phase++) {
            long checksum = 0;
            long start = System.nanoTime();
            for (int pass = 0; pass < passes; pass++) {
                checksum ^= transform(data);
            }
            elapsed[phase] = System.nanoTime() - start;
            checksums[phase] = checksum;
        }

        for (int phase = 0; phase < phases; phase++) {
            System.out.printf(Locale.ROOT,
                    "phase=%d elapsedMs=%.3f checksum=%d%n",
                    phase, elapsed[phase] / 1_000_000.0, checksums[phase]);
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -encoding UTF-8 PhaseObservationDemo.java
java PhaseObservationDemo
```

Một lần chạy class đã biên dịch trên Windows, JDK 24 cho kết quả:

```text
phase=0 elapsedMs=4.124 checksum=-581372681531
phase=1 elapsedMs=2.137 checksum=-1666931978837
phase=2 elapsedMs=0.290 checksum=25521915540
phase=3 elapsedMs=0.291 checksum=-1917613196273
phase=4 elapsedMs=0.291 checksum=-969671597540
phase=5 elapsedMs=0.290 checksum=-491296145065
phase=6 elapsedMs=0.296 checksum=714222013332
phase=7 elapsedMs=0.290 checksum=-1397782334942
```

Thời gian là số đo thực của một lượt, không phải output cố định. Với cùng seed mặc định và cùng phép tính, checksum là dữ kiện có thể dùng kiểm tra kết quả; thời gian có thể khác mỗi lần.

Cách đọc đúng:

- Mỗi `elapsedMs` là thời gian **cả đợt 2.000 lượt biến đổi**, không phải thời gian một phần tử hay một lần gọi.
- Dữ liệu được tạo trước các đợt, nên thời gian cấp phát/khởi tạo mảng ban đầu không được tính vào từng đợt.
- Console không nằm trong các khoảng đo; tất cả kết quả được in sau.
- Mã vẫn có vòng lặp, cập nhật dữ liệu và tác động tối ưu của chính harness; không thể coi đây là chi phí cô lập của một biểu thức.
- Những đợt đầu chậm hơn gợi ý có tác động giai đoạn đầu. Chỉ bảng thời gian này chưa chứng minh phần chênh hoàn toàn do JIT.
- Các đợt sau gần nhau trong một lượt không chứng minh mọi tải thật sẽ ổn định như vậy.
- Tám đợt tổng hợp không đủ để suy ra phân vị p99 của từng thao tác.

Có thể chạy lại bằng một tiến trình JVM mới để so sánh chuỗi. Không chỉ chạy tiếp trong cùng tiến trình rồi gọi đó là một mẫu khởi động mới.

## 6. Vì sao chạy A rồi B trong cùng JVM có thể làm lệch so sánh?

Nếu chạy A trước, A có thể chịu nạp lớp và giai đoạn đầu; B hưởng phần khởi tạo đã xong. Nhưng tác động không chỉ là “B luôn có lợi”.

Thông tin kiểu và nhánh mà A tạo ra có thể ảnh hưởng cách mã dùng chung được tối ưu khi đo B. Hai phương án còn có thể để lại trạng thái bộ nhớ, pool hoặc bộ nhớ đệm khác nhau.

Một cách giảm trộn hồ sơ tối ưu là chạy các benchmark trong JVM riêng (fork). Ví dụ chính thức của JMH minh họa ảnh hưởng việc trộn hồ sơ kiểu trong cùng tiến trình và cách fork giúp cô lập. Xem [JMH: Forking](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_12_Forking.java).

Điều đó không có nghĩa fork giải quyết mọi vấn đề:

- Các tiến trình vẫn dùng chung máy và có thể chịu tải nền khác nhau.
- Khởi động mới không xóa mọi bộ nhớ đệm ở hệ điều hành/dịch vụ ngoài.
- Dữ liệu đầu vào vẫn phải tương đương.
- Số lượt chạy độc lập vẫn cần đủ để thấy dao động.

Khi so sánh, có thể xen kẽ hoặc thay đổi thứ tự các lượt độc lập để giảm ảnh hưởng xu hướng thời gian, đồng thời ghi rõ cách thực hiện. Không chạy hai phương án đồng thời trên cùng tài nguyên tranh chấp rồi gọi đó là điều kiện cô lập.

## 7. Không để tối ưu làm phép đo mất đối tượng cần đo

Ví dụ sai ở mức ý tưởng:

```java
long start = System.nanoTime();
compute(input); // Ket qua khong duoc dung.
long elapsed = System.nanoTime() - start;
```

Nếu compiler nhận ra công việc không ảnh hưởng kết quả quan sát được, nó có thể loại bỏ hoặc rút gọn công việc. Số đo rất nhỏ khi đó không chứng minh thuật toán thực sự hoàn thành nhanh như vậy trong tình huống ứng dụng.

JMH có cơ chế tiêu thụ giá trị trả về hoặc sử dụng `Blackhole` để hỗ trợ tránh loại bỏ mã không dùng, nhưng benchmark vẫn cần thiết kế đầu vào đúng. Xem [JMH: Dead Code](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java).

Các lỗi khác:

- Đầu vào hằng làm phép tính được tính trước hoặc rút gọn.
- Chèn một lần ghi `volatile` vào từng thao tác nhỏ làm đo cả chi phí đồng bộ đó.
- Tự lặp rất nhiều thao tác rồi chia tổng có thể làm JIT tối ưu vòng lặp khác cách sử dụng thật.
- Dùng cùng một đối tượng biến đổi giữa các lượt mà không nhận ra trạng thái đã khác.
- Đọc đồng hồ và in log cho từng thao tác ngắn làm phần đo lấn át công việc.

Không có một “mẹo chống tối ưu” thay thế toàn bộ phương pháp benchmark. Với microbenchmark, nên dùng [JMH](https://github.com/openjdk/jmh) và kiểm tra xem phép thử có trả lời đúng câu hỏi hay không.

## 8. Quy trình đo phù hợp cho từng mục tiêu

### Đo khởi động hoặc đường gọi lạnh

1. Xác định mốc bắt đầu và mốc kết thúc: tạo tiến trình tới sẵn sàng, tới hoàn tất một tác vụ hay tới phản hồi đầu tiên.
2. Biên dịch/đóng gói trước nếu sản phẩm thật chạy class/JAR.
3. Tạo JVM mới cho mỗi lượt khi mục tiêu đòi hỏi trạng thái JVM mới.
4. Ghi rõ trạng thái dữ liệu, tệp, mạng và dịch vụ ngoài.
5. Lặp nhiều lượt độc lập, giữ cả các lượt chậm và điều tra nguyên nhân.
6. Báo cáo phân bố phù hợp, không chỉ một lần nhanh nhất.

Nếu đo yêu cầu đầu tiên, phải định nghĩa “đầu tiên” sau mốc nào và yêu cầu đó đi qua những lớp/khởi tạo nào. Không làm nóng đúng đường đó rồi vẫn gọi số đo sau là cold path.

### Đo vận hành ổn định

1. Làm nóng bằng đầu vào, kiểu dữ liệu và mức đồng thời đại diện.
2. Quan sát chuỗi kết quả; không dựa vào một số lần gọi cố định như định luật.
3. Tách giai đoạn làm nóng khỏi giai đoạn đo nhưng lưu thông tin cả hai.
4. Dùng các lượt JVM độc lập nếu cần kiểm tra khả năng lặp lại/cô lập hồ sơ.
5. Giữ cấu hình JVM, phần cứng và dữ liệu nhất quán giữa phương án.
6. Đánh giá độ phân tán và tính đúng đắn của kết quả.

Nếu hệ thống không đạt trạng thái ổn định trong khoảng quan sát, báo đúng hiện tượng; không chọn một vài đợt đẹp nhất rồi trình bày như toàn bộ hành vi.

### Đo dưới tải

Cần mô tả số kết nối/luồng, kiểu yêu cầu, kích thước dữ liệu, tốc độ đến và giới hạn tài nguyên. Máy tạo tải cũng phải đủ khả năng tạo tải mục tiêu; nếu nó bị nghẽn, thời gian/throughput quan sát có thể đang phản ánh bộ phát tải.

Một phép đo với tải nền cố định và một phép đo trên máy rảnh là hai thí nghiệm khác nhau. Báo cáo riêng giúp người đọc hiểu mỗi kết quả áp dụng trong điều kiện nào.

## 9. Thu bằng chứng trước khi quy kết nguyên nhân

Nếu một đợt chậm bất thường, có thể cần xem:

- Sự kiện nạp/khởi tạo lớp.
- Hoạt động biên dịch và thay đổi mã được tối ưu.
- GC, safepoint, cấp phát.
- Trạng thái luồng, khóa và chờ I/O.
- Mức sử dụng CPU, bộ nhớ và giới hạn tài nguyên của môi trường.

Trên JDK hiện đại, Flight Recorder (JFR) giúp thu sự kiện để điều tra. Cần tính đến chi phí công cụ và chọn cấu hình phù hợp; đừng tự coi profiler luôn có overhead bằng 0. Xem [Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html).

Ví dụ lệnh chẩn đoán trên JVM hỗ trợ JFR:

```shell
java -XX:StartFlightRecording=filename=phase-observation.jfr,settings=profile,dumponexit=true PhaseObservationDemo
```

Lệnh này chạy phiên có ghi sự kiện; thời gian của nó không nên được trộn vào tập kết quả không bật ghi mà không nêu rõ khác biệt. Chương trình mẫu rất ngắn, nên bản ghi có thể không có đủ mẫu để kết luận về mọi hiện tượng. Với ứng dụng thật, chọn thời gian ghi và sự kiện theo câu hỏi.

Sự trùng thời điểm giữa một sự kiện và một đợt chậm là đầu mối điều tra. Không chỉ thấy một bản ghi biên dịch hoặc GC rồi quy toàn bộ độ trễ cho nó mà không xem thời lượng và các thành phần khác.

## 10. Những lỗi diễn giải thường gặp

| Nhận định | Điểm cần sửa |
| --- | --- |
| Lần thứ hai nhanh hơn nên thuật toán đã tốt hơn | Có thể khác trạng thái JVM, dữ liệu hoặc môi trường |
| Bỏ 5 lần đầu là loại hết chi phí khởi động | Chưa có bảo đảm làm nóng đủ hoặc đúng mục tiêu |
| Restart JVM nghĩa là mọi bộ nhớ đệm đều lạnh | Trạng thái ngoài JVM có thể vẫn còn |
| Tắt JIT sẽ làm phép so sánh công bằng hơn | Đó là môi trường thực thi khác; phải phù hợp câu hỏi |
| Gọi System.gc trước mỗi lượt sẽ đưa mọi thứ về chuẩn | Không bảo đảm trạng thái giống nhau và có thể đổi tải/đường chạy |
| Xóa các lần chậm sẽ cho tốc độ thật | Có thể xóa luôn hành vi mà người dùng gặp |
| Không có cấp phát trong đoạn đo thì không thể gặp GC | Hoạt động toàn tiến trình vẫn có thể ảnh hưởng luồng |
| Một giá trị trung bình đủ để cam kết độ trễ | Cần xem phân bố, tải và định nghĩa đại lượng |

Bài tập:

1. Với một CLI chạy 200 ms rồi thoát, vì sao loại toàn bộ giai đoạn đầu có thể làm kết quả mất ý nghĩa?
2. Hai phương án cùng kết quả nhưng A chạy trước B trong cùng JVM. Hãy thiết kế lại lượt thử để kiểm tra ảnh hưởng thứ tự.
3. Trong chương trình mẫu, hãy thay seed đầu vào và quan sát cả checksum lẫn thời gian. Dữ liệu nào kiểm tra tính đúng, dữ liệu nào mô tả hiệu năng?
4. Một đợt chậm trùng lúc GC xuất hiện. Cần thêm bằng chứng nào trước khi kết luận GC giải thích toàn bộ mức tăng?

Một báo cáo có ích phải nói rõ đang đo giai đoạn nào, điều kiện nào đã kiểm soát và điều gì còn có thể gây dao động. Cấu hình đo phù hợp mục tiêu quan trọng hơn việc chỉ có một con số thời gian nhỏ.
