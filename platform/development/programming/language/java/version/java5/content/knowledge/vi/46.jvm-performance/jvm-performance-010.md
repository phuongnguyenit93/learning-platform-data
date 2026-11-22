# Đánh giá tối ưu bằng dữ liệu thay cho dùng cấu hình mặc định từ JDK cũ

## 1. Tối ưu là cải thiện một mục tiêu đã xác định

Một cấu hình JVM từng tốt ở phiên bản JDK khác không tự trở thành lựa chọn tốt cho ứng dụng hiện tại. Phần mềm, bộ thu gom rác, JIT, phần cứng, giới hạn container và kiểu tải có thể đã thay đổi. Cách đánh giá đáng tin bắt đầu từ yêu cầu của ứng dụng, đường cơ sở có thể tái lập và dữ liệu quan sát được.

Ví dụ một dịch vụ cần đồng thời:

- Giữ độ trễ đuôi trong giới hạn đã thỏa thuận.
- Xử lý đủ lượng yêu cầu thành công mỗi giây.
- Không vượt ngân sách CPU và bộ nhớ của môi trường triển khai.
- Giữ tính đúng đắn, tỷ lệ lỗi và độ ổn định.

Một thay đổi tăng số yêu cầu xử lý nhưng làm nhiều yêu cầu lỗi hơn chưa chắc là tối ưu. Một thay đổi giảm thời gian GC nhưng tăng thời gian chờ cơ sở dữ liệu cũng chưa giải quyết được vấn đề người dùng gặp.

Tên module Java 5 không phải chỉ dẫn dùng hành vi mặc định của JVM thời Java 5. Hãy khảo sát đúng JDK đang triển khai và chỉ dùng những công cụ/cấu hình còn được hỗ trợ ở phiên bản ấy.

## 2. Vì sao không nên sao chép nguyên bộ cờ cũ?

HotSpot có cơ chế tự chọn cấu hình theo môi trường và điều chỉnh một số hành vi khi chạy, thường gọi là ergonomics. Tài liệu GC hiện hành khuyên bắt đầu với các lựa chọn mặc định phù hợp trước khi dùng các điều khiển chi tiết. Mặc định và tác dụng của tùy chọn phải được kiểm tra theo phiên bản JVM. [JDK Garbage Collection Tuning Guide: Ergonomics](https://docs.oracle.com/en/java/javase/25/gctuning/ergonomics.html).

Một bộ tham số cũ có thể gặp các vấn đề:

| Vấn đề | Hệ quả khi đánh giá |
| --- | --- |
| Tùy chọn đã đổi tác dụng, bị loại bỏ hoặc không áp dụng với collector hiện tại | Cấu hình không chạy hoặc không còn đạt điều từng kỳ vọng |
| Cố định thông số trước đây JVM tự điều chỉnh | Bỏ mất khả năng thích nghi hữu ích của runtime hiện tại |
| Giả định tài nguyên vật lý khác giới hạn triển khai | Chọn heap, luồng hoặc mức đồng thời không phù hợp |
| Chỉ tối ưu một chỉ số | Chuyển chi phí sang độ trễ, CPU, bộ nhớ hoặc thời gian khởi động |
| Không có lý do và dữ liệu cho từng cờ | Không thể biết cờ nào cần giữ, bỏ hoặc kiểm thử lại |

Điều này không có nghĩa mọi cấu hình tường minh đều sai. Giới hạn bộ nhớ, collector cụ thể hoặc một điều chỉnh có bằng chứng vẫn có thể cần thiết. Hãy giữ một lý do hiện hành cho từng thay đổi thay vì coi cấu hình được truyền lại là một gói tối ưu bất biến.

Không xóa toàn bộ tham số khỏi môi trường sản xuất để thử mặc định. Xây dựng các cấu hình đối chứng trong môi trường thử phù hợp và có khả năng quay lại.

## 3. Đường cơ sở phải phản ánh đúng môi trường chạy

Trước khi sửa cờ, ghi nhận cấu hình thực tế:

| Nhóm thông tin | Nội dung cần giữ cùng kết quả |
| --- | --- |
| Ứng dụng | Phiên bản mã, bản dựng, dependency, dữ liệu/cấu hình nghiệp vụ |
| JVM | Nhà cung cấp, phiên bản đầy đủ, kiến trúc, collector, tham số thực tế |
| Tài nguyên | CPU/quota, giới hạn bộ nhớ, hệ điều hành, kiến trúc máy, môi trường container |
| Tải | Mẫu yêu cầu, kích thước dữ liệu, mức đồng thời, tốc độ đưa tải, thời gian chạy |
| Phụ thuộc | Cơ sở dữ liệu, mạng, cache, dịch vụ ngoài, giới hạn pool |
| Quan sát | Cách thu thập metric/profile, khoảng lấy mẫu, mức ghi nhật ký |

`java -version` trên terminal chưa chắc là Java đang chạy dịch vụ. Wrapper khởi động, đường dẫn executable, image hoặc công cụ triển khai có thể chọn bản khác. Các tùy chọn từ biến môi trường/launcher cũng có thể bổ sung tham số; phải kiểm tra tiến trình thật. [Tài liệu lệnh java](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).

Với một tiến trình HotSpot thích hợp có PID đã xác định, có thể khảo sát bằng:

```shell
jcmd 12345 VM.version
jcmd 12345 VM.command_line
jcmd 12345 VM.flags -all
```

Đây là ví dụ cú pháp: `12345` là PID minh họa và phải thay bằng đúng tiến trình cần khảo sát. Chạy với quyền/ngữ cảnh truy cập phù hợp. `jcmd` có lệnh `help` cho từng JVM; không giả định mọi JVM/vendor đều có cùng tập lệnh. Không dùng PID `0` để vô tình gửi lệnh tới mọi tiến trình Java. [Tài liệu jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html).

## 4. Chọn chỉ số và điều kiện chấp nhận trước khi chạy

Phân biệt mục tiêu chính với các giới hạn không được vi phạm:

| Vai trò | Ví dụ |
| --- | --- |
| Mục tiêu chính | Tăng throughput thành công khi vẫn đáp ứng độ trễ yêu cầu |
| Giới hạn độ trễ | p95/p99 của loại yêu cầu quan trọng không vượt mức chấp nhận |
| Giới hạn chất lượng | Tỷ lệ lỗi, timeout và kết quả nghiệp vụ không xấu đi |
| Giới hạn tài nguyên | RSS, CPU, số kết nối và kích thước hàng đợi trong ngân sách |
| Giới hạn vận hành | Không tăng quá mức thời gian khởi động hoặc thời gian phục hồi |

Không chỉ đọc độ trễ trung bình. Một số yêu cầu chậm có thể rất quan trọng dù trung bình trông tốt. p99 là một phân vị của phân bố quan sát; muốn hiểu nó phải biết loại yêu cầu, cửa sổ đo và số mẫu. Không lấy trung bình các p99 từ nhiều tiến trình rồi coi đó là p99 chung của toàn bộ yêu cầu; cần cách tổng hợp phân bố phù hợp.

Ghi rõ throughput là yêu cầu được đưa vào, hoàn tất hay thành công. Máy phát tải bị nghẽn có thể làm ứng dụng trông ít tải hơn. Nếu chỉ đo các yêu cầu thành công và bỏ timeout, báo cáo độ trễ có thể che mất sự suy giảm nghiêm trọng.

Ngưỡng “tăng bao nhiêu thì đáng chấp nhận” là quyết định của bài toán và mức nhiễu thực nghiệm. Không áp một tỷ lệ tăng cố định cho mọi hệ thống.

## 5. Thu thập dữ liệu để tìm nút thắt trước khi chỉnh

Dữ liệu quan sát giúp nối triệu chứng với giả thuyết:

| Quan sát | Hướng điều tra có thể phù hợp |
| --- | --- |
| CPU cao, đường chạy tập trung trong một hàm | Profile CPU, thuật toán, chi phí xử lý dữ liệu |
| Cấp phát nhiều và GC thường xuyên | Nguồn cấp phát, vòng đời đối tượng, heap/collector theo dữ liệu |
| Độ trễ cao nhưng CPU không bão hòa | Khóa, I/O, hàng đợi, pool, phụ thuộc ngoài |
| RSS tăng trong khi heap không tương ứng | Bộ nhớ ngoài heap, direct buffer, luồng, thư viện native |
| Tải tăng kéo theo thời gian chờ dài | Khả năng tiếp nhận tải, giới hạn đồng thời và điểm bão hòa |

Các cặp trên là giả thuyết điều tra, không phải kết luận chỉ từ một biểu đồ. CPU thấp không chứng minh thiếu luồng; GC xuất hiện không chứng minh GC là nguyên nhân chính.

Java Flight Recorder (JFR) và unified logging có thể cung cấp dữ liệu về hoạt động JVM. Ví dụ thu một khoảng ghi nhận trên tiến trình hỗ trợ:

```shell
jcmd 12345 JFR.start name=baseline settings=profile duration=60s filename=baseline.jfr
```

Ví dụ bật log GC/safepoint khi chạy một JAR minh họa:

```shell
java "-Xlog:gc*,safepoint:file=baseline-gc.log:time,uptime,level,tags" -jar app.jar
```

`app.jar` là ứng dụng cần đo, không phải tệp kèm theo bài học. Chọn nơi ghi có dung lượng và quyền phù hợp; dùng tên tệp khác cho từng lần chạy. Các lệnh là công cụ thu bằng chứng, không tự tối ưu ứng dụng. Kiểm tra cú pháp và tùy chọn của đúng JDK đích. [jcmd và JFR.start](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html), [java và unified logging](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html).

Cách ghi nhận cũng có chi phí. Giữ cách quan sát tương đương giữa các cấu hình cần so sánh hoặc đo riêng tác động của nó; đừng so một bên đang profile nặng với một bên không profile rồi gán mọi khác biệt cho cờ JVM.

## 6. Thiết kế thí nghiệm tách được nguyên nhân

Một quy trình thực nghiệm có thể đi theo chuỗi:

```text
Xác định triệu chứng và mục tiêu
  -> ghi đường cơ sở có thể tái lập
  -> dùng dữ liệu lập một giả thuyết
  -> đổi một yếu tố hoặc một nhóm thay đổi có lý do rõ ràng
  -> chạy lại với tải và môi trường tương đương
  -> lặp, kiểm tra nhiễu và giới hạn bảo vệ
  -> chấp nhận, bác bỏ hoặc cần thêm bằng chứng
```

Ví dụ giả thuyết: “Ở tải mục tiêu, việc cấp phát đối tượng tạm làm tăng chi phí GC; giảm cấp phát ở đường xử lý đã được profile sẽ giảm p99 mà không tăng lỗi.” Đây là giả thuyết có thể kiểm tra, khác với “thêm một danh sách cờ để máy chạy nhanh hơn”.

Nếu vừa đổi phiên bản JDK, collector, heap, pool kết nối và mã ứng dụng trong một lần, rất khó biết yếu tố nào tạo khác biệt. Có thể chia so sánh thành các hồ sơ:

| Hồ sơ | Điều được kiểm tra |
| --- | --- |
| A | Bản đang triển khai, ghi đầy đủ cấu hình để làm mốc |
| B | JDK đích với cấu hình tối thiểu cần thiết cho ràng buộc ứng dụng |
| C | Giống B, thêm một điều chỉnh đã có giả thuyết |

Khi A và B khác JDK, kết quả giữa chúng là tác động của toàn bộ thay đổi đã ghi nhận, không được gán riêng cho một cờ. B và C giúp đánh giá điều chỉnh trên cùng JDK đích.

## 7. Tải thử phải đại diện cho hành vi cần tối ưu

Giữ tương đương các điều kiện quan trọng: tỷ lệ đọc/ghi, dữ liệu nhỏ/lớn, cache trúng/trượt, kích thước tập dữ liệu, độ trễ phụ thuộc và mức đồng thời. Một thử nghiệm chỉ có dữ liệu nằm hết trong cache không đại diện cho hệ thống thường xuyên đọc dữ liệu mới.

Tách các giai đoạn có mục tiêu khác nhau:

- Khởi động: thời gian sẵn sàng, nạp lớp, khởi tạo và những yêu cầu đầu.
- Làm nóng: JVM và ứng dụng thay đổi trạng thái trước khi vào vùng đo ổn định mong muốn.
- Trạng thái vận hành ổn định: đo mục tiêu throughput/độ trễ với dữ liệu đủ dài.
- Tải biến động hoặc đột biến: đánh giá hàng đợi, phục hồi và giới hạn tài nguyên.

Không luôn loại giai đoạn khởi động khỏi báo cáo: nếu ứng dụng ngắn hạn hoặc thường xuyên mở rộng số phiên bản chạy, khởi động là một mục tiêu thực sự. Ngược lại, đo một dịch vụ lâu dài chỉ bằng vài yêu cầu đầu cũng không phản ánh trạng thái vận hành chính.

Thử nhiều mức tải quanh điểm mục tiêu và điểm bão hòa. Một cấu hình có thể tốt ở tải nhẹ nhưng suy giảm sớm hơn khi tăng tải. Khi thay giới hạn CPU/bộ nhớ, đó là một biến thực nghiệm cần ghi lại, không còn cùng điều kiện đối chứng.

## 8. Hiểu các đánh đổi trước khi chấp nhận kết quả

Một số quan hệ thường cần đánh giá:

| Thay đổi | Lợi ích có thể có | Chi phí có thể xuất hiện |
| --- | --- | --- |
| Heap lớn hơn | Giảm tần suất thu gom trong một số tải | RSS cao hơn, giảm vùng dự phòng, hành vi thu gom khác |
| Mục tiêu pause nghiêm hơn với collector hỗ trợ | Hướng tới pause ngắn hơn | Tăng công việc GC hoặc giảm throughput |
| Cache lớn hơn | Giảm tính toán/I/O lặp | Giữ nhiều dữ liệu, tăng bộ nhớ và chi phí vô hiệu hóa |
| Mức đồng thời cao hơn | Tận dụng thời gian chờ khi còn tài nguyên | Tranh chấp, hàng đợi và áp lực phụ thuộc ngoài |

Mục tiêu pause của GC là mục tiêu/hint mà collector cố đạt, không phải cam kết cứng rằng mọi yêu cầu ứng dụng đều có độ trễ dưới con số đó. [GC Ergonomics](https://docs.oracle.com/en/java/javase/25/gctuning/ergonomics.html).

`-Xmx` là giới hạn heap, không phải giới hạn toàn bộ bộ nhớ tiến trình. Trong môi trường có giới hạn bộ nhớ, còn phải tính các phần như bộ nhớ native, metaspace, code cache, ngăn xếp luồng và buffer ngoài heap. Một cấu hình heap vừa sát toàn bộ ngân sách tiến trình có thể không còn vùng dự phòng cần thiết.

Không gắn nhãn một collector, một mức heap hoặc số luồng là “nhanh nhất” mà thiếu điều kiện tải và mục tiêu. Quyết định đúng phải nói rõ thắng ở chỉ số nào và đổi lấy chi phí gì.

## 9. Ví dụ Java 17+: throughput tăng vẫn có thể không đạt

Chương trình sau kiểm tra một điều kiện chấp nhận **minh họa** trên dữ liệu giả. Nó không benchmark JVM, không đọc metric thật và không xác định cấu hình JVM nào tốt hơn.

Hồ sơ ví dụ yêu cầu throughput thành công tăng ít nhất 5%, p99 không quá 50 ms, RSS không quá 400 MiB và tỷ lệ lỗi không quá 1%. Những ngưỡng này chỉ phục vụ bài học; không phải khuyến nghị chung.

Lưu thành `PerformanceGateDemo.java`:

```java
public class PerformanceGateDemo {
    record Result(String name, int requestsPerSecond,
                  int p99Millis, int rssMiB, double errorRate) {}

    static boolean passesExampleGate(Result baseline, Result candidate) {
        boolean meaningfulGain = candidate.requestsPerSecond()
                >= baseline.requestsPerSecond() * 1.05;
        boolean guardrails = candidate.p99Millis() <= 50
                && candidate.rssMiB() <= 400
                && candidate.errorRate() <= 0.01;
        return meaningfulGain && guardrails;
    }

    public static void main(String[] args) {
        // Số liệu giả cho bài học, không phải phép đo JVM.
        Result baseline = new Result("baseline", 1000, 40, 320, 0.005);
        Result candidateA = new Result("candidateA", 1300, 90, 480, 0.020);
        Result candidateB = new Result("candidateB", 1100, 38, 330, 0.005);
        System.out.println("candidateA=" + passesExampleGate(baseline, candidateA));
        System.out.println("candidateB=" + passesExampleGate(baseline, candidateB));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 PerformanceGateDemo.java
java PerformanceGateDemo
```

Stdout:

```text
candidateA=false
candidateB=true
```

Phương án A tăng throughput giả lập từ 1.000 lên 1.300 yêu cầu thành công/giây nhưng vi phạm độ trễ, bộ nhớ và tỷ lệ lỗi. Phương án B tăng lên 1.100 và thỏa các ngưỡng minh họa. `candidateB=true` chỉ nghĩa là dữ liệu được đưa vào hàm vượt qua điều kiện đã lập; chưa chứng minh mẫu đủ lớn, kết quả ổn định hay có quan hệ nhân quả.

Trong báo cáo thực, lưu đơn vị cho từng chỉ số; chẳng hạn MiB khác MB và `0.01` ở ví dụ là tỷ lệ 1%, không phải 0,01%. Đừng chuyển một bộ điều kiện đơn giản thành chứng nhận hiệu năng nếu dữ liệu đầu vào không đạt chất lượng.

## 10. Lặp lại, đọc độ biến động và tránh kết luận quá sớm

Chạy lại các cấu hình với nhiều lượt độc lập phù hợp; có thể đổi thứ tự A/B hoặc A/B/A để nhận diện ảnh hưởng từ máy nóng lên, tải nền, cache hoặc phụ thuộc ngoài. Giữ dữ liệu thô và mô tả rõ cửa sổ đo.

Không chỉ lấy lần tốt nhất. Cần xem phân bố, khoảng biến động và độ ổn định ở cùng mức tải. Nếu mức cải thiện nhỏ hơn nhiễu giữa các lượt, kết luận phù hợp là chưa đủ bằng chứng, không phải chọn kết quả đẹp nhất.

Với microbenchmark mã Java, dùng JMH và thiết kế đúng để kiểm soát các ảnh hưởng như JIT, việc loại bỏ mã và vòng lặp bị tối ưu khác điều định đo. Một ví dụ chính thức của JMH cho thấy tự gộp nhiều phép toán trong vòng lặp có thể làm sai chi phí suy ra trên mỗi phép toán. [JMH sample về vòng lặp](https://raw.githubusercontent.com/openjdk/jmh/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_11_Loops.java).

Microbenchmark chỉ hỗ trợ một phần lập luận. Một hàm nhanh hơn không bảo đảm API nhanh hơn nếu chi phí chủ yếu nằm ở I/O hoặc hàng đợi. Sau thay đổi cục bộ vẫn cần kiểm thử tích hợp/toàn hệ thống theo mục tiêu.

## 11. Đưa thay đổi vào vận hành với tiêu chí quay lại

Trước khi áp dụng rộng, giữ một bản mô tả có thể đánh giá:

```text
Vấn đề: chỉ số nào không đạt, ở tải và giới hạn tài nguyên nào
Giả thuyết: nguyên nhân được dữ liệu hỗ trợ
Thay đổi: đúng phiên bản mã/JDK/cấu hình đã sửa
Bằng chứng: dữ liệu đường cơ sở, các lượt đối chứng và profile liên quan
Đánh đổi: độ trễ, throughput, CPU, bộ nhớ, lỗi, khởi động
Quyết định: chấp nhận/bác bỏ/chưa đủ dữ liệu
Theo dõi: ngưỡng quan sát và điều kiện quay lại sau triển khai
```

Triển khai có phạm vi phù hợp, quan sát tải thật và giữ cách quay lại cấu hình trước. Một phương án tốt trong thử nghiệm có thể không còn tốt khi phân bố dữ liệu hoặc phụ thuộc ngoài khác đi.

Không cập nhật JDK chỉ để “có mặc định mới” mà bỏ qua kiểm thử tương thích và hiệu năng. Cũng không giữ mãi tham số từ bản JDK cũ vì sợ mất một cải thiện chưa từng được đo lại. Mỗi lần thay môi trường quan trọng là dịp kiểm chứng các giả định đang dùng.

## 12. Tự nhận diện các kết luận không có đủ bằng chứng

| Kết luận vội | Bằng chứng còn thiếu |
| --- | --- |
| Thêm nhiều cờ nên cấu hình đã được tối ưu | Lý do hiện hành và đo đối chứng cho thay đổi |
| GC ít hơn nên ứng dụng nhanh hơn | Độ trễ, throughput thành công, CPU và các nút thắt khác |
| Trung bình tốt nên người dùng đều tốt hơn | Phân bố độ trễ, timeout và tỷ lệ lỗi |
| JDK đích chậm vì một lần chạy đầu lâu | Phân biệt khởi động, làm nóng và giai đoạn cần đánh giá |
| p99 giảm ở tải nhẹ nên chịu tải tốt hơn | Kết quả tại tải mục tiêu, gần bão hòa và tải biến động |
| Một phép đo cục bộ đủ cho quyết định sản xuất | Tính tái lập, quy mô dữ liệu, kiểm thử tích hợp và theo dõi vận hành |

Bài tập: một thay đổi giảm thời gian GC nhưng RSS tiến sát giới hạn bộ nhớ, trong khi p99 không cải thiện. Chưa có cơ sở chấp nhận chỉ từ log GC. Cần quay lại mục tiêu, xác định chi phí đang chuyển sang đâu và kiểm tra liệu giả thuyết ban đầu có đúng với nút thắt thực tế không.
