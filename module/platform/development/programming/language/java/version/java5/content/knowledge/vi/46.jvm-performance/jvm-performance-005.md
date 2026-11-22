# Quan hệ giữa thông lượng, độ trễ và dung lượng heap

## 1. Ba đại lượng cùng ảnh hưởng đến chất lượng hệ thống

Một dịch vụ Java có thể xử lý rất nhiều yêu cầu mỗi giây nhưng vẫn có một phần người dùng phải chờ lâu. Một cấu hình heap nhỏ có thể tiết kiệm bộ nhớ nhưng khiến JVM phải thu gom thường xuyên. Tăng heap có thể giảm áp lực thu gom, nhưng không tự làm mọi yêu cầu nhanh hơn.

Ba đại lượng cần hiểu cùng nhau:

| Đại lượng | Câu hỏi |
| --- | --- |
| Thông lượng (throughput) | Hệ thống hoàn tất được bao nhiêu công việc trong một khoảng thời gian? |
| Độ trễ (latency) | Một công việc cụ thể mất bao lâu từ điểm bắt đầu đến điểm kết thúc đã xác định? |
| Dung lượng heap | JVM có bao nhiêu không gian cho đối tượng Java và việc quản lý chúng? |

Đánh đổi không có nghĩa luôn phải hy sinh đúng một đại lượng để cải thiện hai đại lượng kia. Xóa một rò rỉ bộ nhớ hoặc giảm việc cấp phát vô ích có thể cải thiện cả ba. Nhưng khi chương trình và tài nguyên giữ nguyên, tối ưu một mục tiêu thường thay đổi cách JVM sử dụng CPU, bộ nhớ và thời gian tạm dừng.

Bài học dùng các khái niệm và công cụ HotSpot hiện hành, với ví dụ chạy trên JDK 17+. Không áp dụng máy móc cách chỉnh JVM của thời Java 5 cho bộ thu gom hiện đại.

## 2. Định nghĩa phép đo trước khi thay heap

### Thông lượng: đếm đúng công việc thành công

Ví dụ định nghĩa:

```text
Thông lượng = số yêu cầu hoàn tất thành công / thời gian đo
```

Cần ghi rõ đơn vị: yêu cầu/giây, giao dịch/giây hoặc số bản ghi/giây. Không coi số yêu cầu được gửi vào hệ thống là số yêu cầu đã xử lý thành công.

Nếu cấu hình mới trả lỗi nhanh hơn hoặc loại bỏ nhiều yêu cầu hơn, chỉ số “phản hồi mỗi giây” có thể tăng mà chất lượng dịch vụ lại giảm. Cần nhìn cùng tỷ lệ lỗi, timeout và số công việc còn tồn đọng.

### Độ trễ: trung bình không kể hết trải nghiệm

Độ trễ cần được đo ở điểm có ý nghĩa với người dùng, chẳng hạn từ lúc máy khách gửi yêu cầu đến lúc nhận đủ phản hồi.

- `p50`: mức mà khoảng một nửa quan sát không vượt quá.
- `p95` và `p99`: cho thấy phần đuôi chậm hơn của phân bố.
- Thời gian chờ hàng đợi, mạng, cơ sở dữ liệu và CPU đều có thể góp phần vào độ trễ cuối cùng.

Không lấy trung bình của các p99 theo từng phút rồi gọi đó là p99 của cả giờ. Phân vị cần được tính từ phân bố hoặc dữ liệu có thể tổng hợp đúng cách.

### GC pause khác độ trễ yêu cầu

Một lần JVM dừng các luồng ứng dụng có thể trì hoãn nhiều yêu cầu, rồi tạo thêm hàng đợi ngay sau khi chạy lại. Vì thế, giảm pause có thể giúp độ trễ đuôi nhưng không bảo đảm p99 yêu cầu bằng p99 pause.

Ngược lại, p99 tăng mà GC pause ổn định có thể do khóa, I/O, thiếu CPU hoặc tải vượt năng lực. Cần đối chiếu theo cùng dòng thời gian thay vì gán mọi lần chậm cho GC.

## 3. Xmx, heap đang dùng và bộ nhớ tiến trình

Bốn khái niệm thường bị trộn:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Heap tối đa | Giới hạn JVM được phép sử dụng cho heap, thường do `-Xmx` quy định |
| Heap đã cam kết | Phần heap JVM đã cam kết sử dụng theo cơ chế hệ điều hành/JVM |
| Heap đang dùng | Phần đang chứa đối tượng, có thể gồm cả đối tượng đã không còn cần nhưng chưa được thu gom |
| Tập đối tượng sống (live set) | Những đối tượng còn được chương trình giữ và chưa thể thu hồi |

Dung lượng heap tối đa không đồng nhất với bộ nhớ vật lý tiến trình đang chiếm. Bộ nhớ tiến trình còn có metadata lớp, bộ nhớ mã biên dịch, stack của luồng, bộ đệm trực tiếp, cấu trúc GC và tài nguyên native.

Vì vậy, đặt `-Xmx` bằng toàn bộ giới hạn bộ nhớ container không chừa chỗ cho các thành phần khác. Tiến trình có thể bị môi trường kết thúc vì vượt giới hạn ngay cả khi không thấy `OutOfMemoryError: Java heap space`.

`-Xms` và `-Xmx` cũng không đồng nghĩa “đối tượng sống tối thiểu/tối đa”. Chúng điều khiển kích thước heap theo hợp đồng JVM, còn việc giữ tham chiếu phụ thuộc chương trình. Quan hệ giữa không gian dự trữ và cam kết được giải thích trong [tài liệu dung lượng heap](https://docs.oracle.com/en/java/javase/25/gctuning/factors-affecting-garbage-collection-performance.html); chi tiết điều chỉnh phụ thuộc bộ thu gom.

## 4. Vì sao heap nhỏ có thể giảm thông lượng?

Hãy xét một ứng dụng cấp phát nhanh nhưng chỉ giữ một phần nhỏ đối tượng lâu dài.

Nếu không gian trống nhanh hết, GC cần hoạt động thường xuyên hơn để JVM tiếp tục cấp phát. Công việc thu gom và các điểm dừng có thể lấy thời gian CPU hoặc thời gian chạy khỏi ứng dụng, làm giảm số công việc hoàn tất mỗi giây.

Nếu heap gần sát tập đối tượng sống, JVM còn ít không gian để vừa cấp phát vừa thực hiện thu gom. Với các bộ thu gom cần di chuyển đối tượng hoặc làm việc đồng thời, phần dư này có vai trò riêng; không thể chỉ lấy live set rồi cộng một tỷ lệ cố định cho mọi hệ thống.

Một mô hình trực giác:

```text
Khoảng trống sử dụng được / tốc độ cấp phát
          ≈ thời gian lấp đầy lý tưởng
```

Nếu có 400 MiB khoảng trống và cấp phát 200 MiB/giây, phép chia cho 2 giây chỉ giúp hình dung áp lực. Nó **không** dự đoán chính xác chu kỳ GC: bộ thu gom có thể hoạt động trước khi đầy, đối tượng có vòng đời khác nhau và việc thu hồi diễn ra theo thuật toán riêng.

Đừng nhầm tốc độ cấp phát với tăng trưởng dữ liệu sống. Một ứng dụng có thể cấp phát hàng GiB mỗi giây mà live set tương đối ổn định, hoặc cấp phát chậm nhưng giữ mọi đối tượng khiến live set tăng liên tục.

## 5. Vì sao tăng heap đôi khi có ích, đôi khi làm xấu tình hình?

### Trường hợp có thể cải thiện

Heap lớn hơn có thể tạo thêm khoảng trống cho cấp phát, giảm tần suất một số lần thu gom hoặc cho phần thu gom đồng thời thêm thời gian hoàn tất. Nếu cấu hình cũ thiếu không gian nhưng tải và CPU phù hợp, thông lượng hoặc độ trễ có thể tốt hơn.

### Trường hợp không giải quyết nguyên nhân

- Nếu cơ sở dữ liệu là nút thắt, tăng heap có thể không cải thiện thời gian phản hồi.
- Nếu cache không giới hạn hoặc giữ tham chiếu ngoài dự kiến, heap lớn hơn có thể chỉ trì hoãn lúc hết bộ nhớ.
- Nếu hệ thống gần giới hạn RAM, tăng heap có thể gây áp lực bộ nhớ, lỗi trang, hoán đổi hoặc bị container kết thúc.
- Nếu hàng đợi không giới hạn, tăng heap có thể cho phép giữ nhiều yêu cầu đang chờ hơn; thông lượng không tăng tương ứng nhưng độ trễ tăng.

Heap lớn hơn cũng có thể làm một số công việc thu gom xử lý nhiều dữ liệu hơn, tùy đối tượng sống và bộ thu gom. Nhưng câu “heap gấp đôi thì pause gấp đôi” không phải quy luật.

Lựa chọn bộ thu gom và cách nó chia công việc là một phần của bài toán. [Tài liệu giới thiệu GC](https://docs.oracle.com/en/java/javase/25/gctuning/introduction-garbage-collection-tuning.html) mô tả các bộ thu gom phục vụ mục tiêu khác nhau và chi phí runtime đi kèm.

## 6. Thông lượng và độ trễ có thể kéo theo hai hướng

Một bộ thu gom có thể gom nhiều việc vào ít lần dừng hơn để đạt hiệu quả tổng thể. Một thiết kế khác có thể chia nhỏ hoặc chuyển thêm công việc sang xử lý đồng thời nhằm giảm thời gian dừng, đổi lại chi phí CPU, bộ nhớ hoặc thao tác trên đường thực thi.

Với G1, mục tiêu thời gian pause là **mục tiêu thích nghi**, không phải cam kết mọi lần dừng luôn dưới một ngưỡng. Đặt mục tiêu cực thấp không tự tạo hệ thống thời gian thực; nó có thể làm thay đổi kích thước công việc thu gom và thông lượng.

[Tài liệu tuning G1](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html) khuyến nghị bắt đầu với cấu hình mặc định, tập trung trước vào heap và mục tiêu pause khi cần. Không cố định kích thước vùng trẻ chỉ vì một bài hướng dẫn cũ có làm như vậy: khả năng điều chỉnh vùng trẻ là một công cụ quan trọng của G1.

Cũng cần phân biệt:

- Tỷ lệ thời gian dừng trong cửa sổ đo.
- CPU mà các luồng GC sử dụng, bao gồm công việc đồng thời.
- Thời gian đáp ứng yêu cầu ở máy khách.

Không lấy riêng “tổng pause / tổng thời gian” làm toàn bộ chi phí GC cho bộ thu gom đồng thời.

## 7. Hàng đợi có thể khuếch đại áp lực bộ nhớ

Một vòng phản hồi cần chú ý:

```text
Xử lý chậm hơn
      |
Yêu cầu chờ nhiều hơn
      |
Giữ thêm đối tượng và bộ đệm
      |
Heap chịu áp lực hơn
      |
GC/CPU chịu tải hơn
      |
Xử lý tiếp tục chậm
```

Đây là một mô hình nguyên nhân có thể xảy ra, không phải chẩn đoán cho mọi hệ thống.

Giới hạn hàng đợi, giới hạn số công việc đồng thời, thời hạn hợp lý và điều tiết tải có thể giúp phá vòng này. Tăng heap chỉ thay không gian lưu yêu cầu đang chờ; nó không tạo thêm năng lực cho nút thắt ở phía sau.

Khi so sánh cấu hình, phải giữ cùng mức tải đầu vào và theo dõi số yêu cầu đang chờ. Một bộ phát tải luôn đợi phản hồi rồi mới gửi yêu cầu kế tiếp có thể vô tình giảm tải khi máy chủ chậm, làm kết quả trông tốt hơn thực tế.

## 8. Thí nghiệm Java 17+: tách tổng cấp phát khỏi dữ liệu được giữ

Chương trình sau liên tục tạo mảng và giữ lại tối đa một số lượng hữu hạn trong vòng đệm. Nó giúp quan sát áp lực cấp phát với cùng khối lượng dữ liệu logic ở hai kích thước heap.

Đây là thí nghiệm tạo tải bộ nhớ nhỏ, **không phải benchmark dịch vụ**. Nó không tạo yêu cầu mạng và không đo p99.

Lưu thành `HeapPressureDemo.java`:

```java
public class HeapPressureDemo {
    public static void main(String[] args) {
        if (args.length != 0 && args.length != 3) {
            throw new IllegalArgumentException(
                    "Use: HeapPressureDemo [iterations payloadBytes slots]");
        }
        int iterations = args.length == 0 ? 200_000 : positive(args[0]);
        int payloadBytes = args.length == 0 ? 1_024 : positive(args[1]);
        int slots = args.length == 0 ? 1_024 : positive(args[2]);

        byte[][] retained = new byte[slots][];
        long checksum = 0;
        for (int i = 0; i < iterations; i++) {
            byte[] block = new byte[payloadBytes];
            block[0] = (byte) i;
            checksum += Byte.toUnsignedInt(block[0]);
            retained[i % slots] = block;
        }

        long retainedPayloadBytes = 0;
        long retainedChecksum = 0;
        for (byte[] block : retained) {
            if (block != null) {
                retainedPayloadBytes += block.length;
                retainedChecksum += Byte.toUnsignedInt(block[0]);
            }
        }

        System.out.println("allocations=" + iterations);
        System.out.println("requestedPayloadBytes="
                + (long) iterations * payloadBytes);
        System.out.println("retainedPayloadBytes=" + retainedPayloadBytes);
        System.out.println("checksum=" + checksum);
        System.out.println("retainedChecksum=" + retainedChecksum);
    }

    private static int positive(String value) {
        int parsed = Integer.parseInt(value);
        if (parsed <= 0) {
            throw new IllegalArgumentException("Values must be positive");
        }
        return parsed;
    }
}
```

Biên dịch:

```shell
javac HeapPressureDemo.java
```

Chạy hai cấu hình HotSpot G1 trên JDK 17+ trong cùng thư mục:

```shell
java -Xms64m -Xmx64m -XX:+UseG1GC "-Xlog:gc*:file=gc-64m.log:time,uptime,level,tags" HeapPressureDemo
java -Xms256m -Xmx256m -XX:+UseG1GC "-Xlog:gc*:file=gc-256m.log:time,uptime,level,tags" HeapPressureDemo
```

Stdout của cả hai lần với tham số mặc định:

```text
allocations=200000
requestedPayloadBytes=204800000
retainedPayloadBytes=1048576
checksum=25493856
retainedChecksum=130560
```

Cách đọc kết quả:

- Mã nguồn yêu cầu tạo tổng 204.800.000 byte payload qua các lượt cấp phát.
- Khi quan sát cuối vòng lặp, các mảng được giữ có tổng 1.048.576 byte payload.
- Đây là payload của mảng, không gồm header đối tượng, mảng tham chiếu hoặc dữ liệu JVM khác.
- Dữ liệu cũ bị thay thế trong vòng đệm có thể trở thành rác; “không còn được giữ” khác với “đã được GC thu hồi ngay”.
- Checksum giống nhau giúp xác nhận hai lần thực hiện cùng tính toán logic, không chứng minh hiệu năng giống nhau.

JIT có thể tối ưu mã; lượng cấp phát thực tế phải đo bằng công cụ, không lấy số đếm logic làm số byte tuyệt đối JVM đã cấp phát. Không dựa vào một vòng chạy ngắn này để xếp hạng bộ thu gom.

Các GC log chứa thời điểm, loại thu gom, mức dùng heap và pause thay đổi theo máy/JDK. Bài không đưa một số mili giây cố định làm kết quả chuẩn.

Có thể tăng số ô giữ bằng tham số thứ ba để thay đổi lượng dữ liệu sống:

```shell
java -Xms64m -Xmx64m -XX:+UseG1GC HeapPressureDemo 200000 1024 16384
```

Lần này cấu trúc giữ tối đa 16 MiB payload thay vì 1 MiB. Nó thay đổi một thuộc tính của tải là thời gian giữ đối tượng, nên không trộn kết quả với thí nghiệm chỉ thay heap rồi kết luận nguyên nhân là heap.

## 9. Quy trình so sánh cấu hình có thể tin được

1. **Xác định mục tiêu.** Ví dụ cần đạt thông lượng tối thiểu, p99 tối đa, tỷ lệ lỗi cho phép và ngân sách bộ nhớ tiến trình.
2. **Ghi môi trường.** JDK và nhà cung cấp, bộ thu gom, số CPU/quota, RAM/container, tham số JVM và dữ liệu đầu vào.
3. **Đo đường cơ sở.** Ghi thông lượng thành công, phân bố độ trễ, timeout, hàng đợi, CPU, heap sau GC, bộ nhớ tiến trình và hoạt động GC.
4. **Thay một yếu tố có chủ đích.** Chẳng hạn chỉ đổi heap, giữ nguyên collector và tải. Không đồng thời thêm nhiều cờ rồi đoán cờ nào có tác dụng.
5. **Cho JVM và tải ổn định.** Tách khởi động/JIT khỏi giai đoạn tải dài hạn nếu mục tiêu là hiệu năng ổn định; nếu mục tiêu là khởi động thì đo nó riêng.
6. **Lặp lại và thử tải biến động.** Xem kết quả có ổn định qua các lần và khi tải tăng đột biến hay không.
7. **Chọn cấu hình đạt ràng buộc.** Không chọn heap lớn nhất chỉ vì một chỉ số đẹp hơn.

Trong thí nghiệm, đặt `Xms=Xmx` giúp bớt một yếu tố biến động là mở rộng heap. Đó không phải quy tắc bắt buộc cho mọi container hoặc dịch vụ.

Cú pháp `-Xms`, `-Xmx` và unified logging được mô tả trong [lệnh java](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html). Các cờ `-XX` phụ thuộc JVM và phiên bản; kiểm tra hỗ trợ trước khi áp dụng.

JFR giúp đối chiếu hoạt động GC với mẫu CPU, khóa và các sự kiện runtime. Native Memory Tracking có thể hỗ trợ phân tích phần bộ nhớ ngoài heap; số liệu của nó vẫn cần đọc cùng số liệu tiến trình/hệ điều hành. Xem [công cụ chẩn đoán JDK](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html).

## 10. Đọc triệu chứng trước khi ra quyết định

| Quan sát | Giả thuyết cần kiểm tra |
| --- | --- |
| Thu gom thường xuyên, tập sống ổn định, nhiều cấp phát ngắn hạn | Áp lực cấp phát; cân nhắc giảm cấp phát hoặc thêm khoảng trống phù hợp |
| Tập sống sau GC tăng mãi dưới tải tương đương | Giữ tham chiếu, cache không giới hạn hoặc tăng trưởng dữ liệu cần thiết |
| p99 tăng nhưng GC không đổi | Hàng đợi, khóa, I/O, thiếu CPU hoặc nút thắt ngoài JVM |
| Heap còn chỗ nhưng container bị kết thúc | Bộ nhớ native, stack, bộ đệm trực tiếp hoặc ngân sách toàn tiến trình |
| Tăng heap nhưng thông lượng gần như không đổi | Nút thắt có thể không phải quản lý heap |
| Pause ngắn hơn nhưng CPU GC cao và thông lượng giảm | Đánh đổi collector/mục tiêu cần được đánh giá theo SLO |

Bảng là danh sách giả thuyết, không thay thế bằng chứng. Quyết định tăng heap cần đi kèm quan sát về phần bộ nhớ còn dư và mục tiêu độ trễ, không chỉ ảnh chụp “heap used” tại một thời điểm.

## 11. Tự kiểm tra

1. Tăng Xmx có bảo đảm tăng thông lượng không? **Không; còn phụ thuộc nút thắt và tải.**
2. Heap đang dùng có bằng dữ liệu sống không? **Không; có thể chứa rác chưa thu gom.**
3. Tổng payload đã cấp phát có bằng heap cần giữ không? **Không; nhiều đối tượng chỉ tồn tại trong thời gian ngắn.**
4. p99 yêu cầu có bằng p99 GC pause không? **Không; còn hàng đợi và nhiều thành phần khác.**
5. Vì sao không đặt Xmx bằng toàn bộ giới hạn container? **Tiến trình còn nhiều vùng bộ nhớ ngoài heap.**
6. Vì sao không chỉ so hai lần chạy ngắn? **Khởi động, JIT, nhiễu và biến động tải có thể chi phối kết quả.**
7. Khi nào tăng heap chỉ trì hoãn sự cố? **Khi dữ liệu được giữ tăng không giới hạn hoặc có rò rỉ mà nguyên nhân chưa được sửa.**
