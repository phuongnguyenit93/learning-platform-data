# Count sample trong jstat

Trong `jstat`, tham số **count** xác định số lần công cụ lấy và in mẫu thống kê từ một JVM đang chạy. Mỗi sample là một lần chụp các bộ đếm hoặc chỉ số JVM tại một thời điểm. Ví dụ, `jstat -gcutil <pid> 250ms 5` yêu cầu lấy 5 mẫu, cách nhau khoảng 250 mili giây.

Count là số dòng dữ liệu mẫu mà `jstat` in ra; nó không phải số lần garbage collection, số object hoặc số sự kiện của ứng dụng. Các cột như `YGC` và `FGC` trong báo cáo GC là bộ đếm sự kiện GC tích lũy riêng.

## 1. Cú pháp và vị trí của count

Cú pháp tổng quát:

~~~sh
jstat <statOption> [-t] [-h lines] <vmid> [interval [count]]
~~~

Các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| `<statOption>` | Loại thống kê cần xem, ví dụ `-gcutil`, `-gc` hoặc `-class` |
| `-t` | Thêm cột thời gian đã trôi qua kể từ lúc JVM đích khởi động |
| `-h lines` | Lặp lại dòng tiêu đề sau mỗi `lines` mẫu |
| `<vmid>` | Định danh JVM đích; với JVM cục bộ thường là PID |
| `interval` | Khoảng thời gian giữa các lần lấy mẫu |
| `count` | Số mẫu cần lấy trước khi kết thúc |

`count` nằm sau `interval` trong cú pháp. Vì vậy, để yêu cầu 5 mẫu cách nhau 250 ms, phải truyền cả hai tham số:

~~~sh
jstat -gcutil 18360 250ms 5
~~~

Lệnh trên yêu cầu 5 lần lấy mẫu từ JVM có VMID `18360`. Không thể bỏ `interval` rồi đặt `count` ở vị trí kế tiếp; tham số vị trí đó sẽ được hiểu là interval.

## 2. Count và interval hoạt động như thế nào?

`interval` xác định nhịp lấy mẫu; `count` xác định số mẫu. Hai tham số có quy tắc:

- Interval phải là số nguyên dương.
- Đơn vị mặc định là mili giây (`ms`).
- Có thể ghi rõ hậu tố `ms` hoặc `s`.
- Count phải là số nguyên dương.
- Khi đã truyền interval nhưng bỏ count, mặc định count là vô hạn: `jstat` tiếp tục in mẫu cho tới khi JVM đích kết thúc hoặc người dùng dừng lệnh.
- Trong thử nghiệm với JDK 24.0.2, nếu chỉ truyền stat option và VMID mà không có interval, `jstat` in một snapshot rồi kết thúc.

Ví dụ interval tương đương:

~~~sh
jstat -gcutil 18360 250 5
jstat -gcutil 18360 250ms 5
jstat -gcutil 18360 1s 5
jstat -gcutil 18360 1000ms 5
~~~

Hai lệnh đầu lấy 5 mẫu cách nhau 250 ms. Hai lệnh sau lấy 5 mẫu cách nhau 1 giây.

Không nên coi interval là lịch thời gian thực tuyệt đối. Thời điểm thực tế có thể lệch do thời gian đọc counter, tải hệ thống, lập lịch thread và độ trễ của JVM. Khoảng cách giữa các dòng thường gần interval yêu cầu, nhưng có thể dài hơn khi máy bận.

## 3. Ví dụ count hữu hạn

Lấy 3 mẫu GC utilization, cách nhau 200 ms:

~~~sh
jstat -gcutil 18360 200ms 3
~~~

Kết quả có một dòng header và đúng 3 dòng dữ liệu. Đây là output minh họa từ JDK 24.0.2; giá trị thay đổi theo tiến trình:

~~~text
  S0     S1      E      O      M     CCS    YGC    YGCT    FGC    FGCT    CGC    CGCT     GCT
   -      -    4.26   0.00      -      -      0   0.000      0   0.000      0   0.000   0.000
   -      -    6.38   0.00      -      -      0   0.000      0   0.000      0   0.000   0.000
   -      -    8.51   0.00      -      -      0   0.000      0   0.000      0   0.000   0.000
~~~

Điều cần kiểm tra ở bài này là có đúng 3 dòng sample sau header, không phải các con số giống hệt ví dụ.

Một số lệnh hữu ích:

~~~sh
jstat -gcutil <pid> 1s 10
jstat -gc <pid> 500ms 6
jstat -class <pid> 2s 4
~~~

- Lệnh thứ nhất lấy 10 mẫu GC utilization, mỗi mẫu cách nhau khoảng 1 giây.
- Lệnh thứ hai lấy 6 mẫu thống kê heap/GC theo đơn vị KB, mỗi mẫu cách nhau khoảng 500 ms.
- Lệnh thứ ba lấy 4 mẫu thống kê class loading, mỗi mẫu cách nhau khoảng 2 giây.

## 4. Count mặc định vô hạn và cách dừng

Nếu truyền interval nhưng bỏ count, `jstat` tiếp tục lấy mẫu vô hạn:

~~~sh
jstat -gcutil 18360 1s
~~~

Lệnh tiếp tục in một dòng dữ liệu mỗi khoảng một giây. Nó kết thúc khi JVM đích thoát hoặc khi người dùng dừng tiến trình `jstat` bằng `Ctrl+C`.

Chế độ vô hạn hữu ích khi quan sát một giai đoạn tải hoặc chờ sự kiện GC. Tuy nhiên, nếu chỉ cần một báo cáo ngắn, hãy chỉ định count hữu hạn để tránh quên tiến trình giám sát đang chạy và tạo output không cần thiết.

Có thể chọn số mẫu theo mục tiêu quan sát:

| Mục tiêu | Ví dụ | Số mẫu |
|---|---|---:|
| Kiểm tra nhanh | `jstat -gcutil <pid> 250ms 3` | 3 |
| Quan sát ngắn | `jstat -gcutil <pid> 1s 10` | 10 |
| Theo dõi tới khi dừng thủ công | `jstat -gcutil <pid> 1s` | Vô hạn |

Nếu JVM đích kết thúc trước khi đủ count, việc lấy mẫu cũng kết thúc theo tiến trình đích; số dòng thực tế có thể ít hơn count yêu cầu.

## 5. Count khác với số lần GC

Đây là điểm dễ nhầm nhất. `count` đếm số lần `jstat` lấy mẫu. Trong khi đó, các cột GC phản ánh số sự kiện GC đã xảy ra trong JVM.

Với tùy chọn `-gcutil`:

| Cột | Ý nghĩa |
|---|---|
| `YGC` | Số lần young-generation GC tích lũy |
| `FGC` | Số lần full GC tích lũy |
| `YGCT` | Tổng thời gian young GC |
| `FGCT` | Tổng thời gian full GC |
| `GCT` | Tổng thời gian GC |

Ví dụ, lệnh:

~~~sh
jstat -gcutil 18360 250ms 5
~~~

lấy 5 mẫu. Nếu trong 5 khoảng quan sát không có GC mới, giá trị `YGC` và `FGC` có thể giống nhau ở cả 5 dòng. Nếu có GC giữa hai lần lấy mẫu, các bộ đếm này tăng lên. Số lần GC không nhất thiết bằng 5.

Có thể hiểu đơn giản:

- `count=5`: công cụ đọc trạng thái 5 lần.
- `YGC=8`: JVM đã ghi nhận 8 sự kiện young GC tính từ khi bộ đếm bắt đầu.
- Một sample không đồng nghĩa một GC event.

## 6. Kết hợp count với -h và -t

Tùy chọn `-h` điều khiển tần suất lặp lại header. Ví dụ:

~~~sh
jstat -gcutil -h2 18360 250ms 5
~~~

Lệnh lấy 5 mẫu và in lại header sau mỗi 2 sample. Output có dạng:

~~~text
S0  S1  E  O  M  CCS  YGC  YGCT  FGC  FGCT  CGC  CGCT  GCT
-   -   4  0  -  -    0    0.0   0    0.0   0    0.0   0.0
-   -   6  0  -  -    0    0.0   0    0.0   0    0.0   0.0
S0  S1  E  O  M  CCS  YGC  YGCT  FGC  FGCT  CGC  CGCT  GCT
-   -   8  0  -  -    0    0.0   0    0.0   0    0.0   0.0
-   -  10  0  -  -    0    0.0   0    0.0   0    0.0   0.0
S0  S1  E  O  M  CCS  YGC  YGCT  FGC  FGCT  CGC  CGCT  GCT
-   -  12  0  -  -    0    0.0   0    0.0   0    0.0   0.0
~~~

Header được in lại không làm tăng count. Với 5 sample và `-h2`, có 5 dòng dữ liệu và 3 lần xuất hiện header: đầu output, sau sample 2 và sau sample 4.

Tùy chọn `-t` thêm cột `Timestamp` ở đầu mỗi sample:

~~~sh
jstat -gcutil -t 18360 250ms 5
~~~

Timestamp là số giây đã trôi qua kể từ khi JVM đích khởi động, không phải giờ trên đồng hồ. Nó giúp đối chiếu các mẫu với tuổi tiến trình và sự kiện xảy ra trong runtime. Trên hệ thống bận, timestamp có thể không cách đều chính xác theo interval vì độ trễ lập lịch.

Có thể kết hợp cả hai:

~~~sh
jstat -gcutil -t -h2 18360 250ms 5
~~~

## 7. Chọn loại thống kê trước khi chọn count

Count áp dụng cho output option mà bạn chọn. Dùng `jstat -options` để xem các loại thống kê có sẵn trên JDK hiện tại.

Một số lựa chọn thường dùng:

| Option | Nội dung |
|---|---|
| `-gcutil` | Tỷ lệ sử dụng các vùng heap và bộ đếm GC |
| `-gc` | Dung lượng và mức sử dụng các vùng heap theo KB cùng bộ đếm GC |
| `-class` | Thống kê class loading/unloading |
| `-compiler` | Hoạt động của JIT compiler |
| `-gccause` | Thống kê GC và nguyên nhân của lần GC gần nhất/đang diễn ra |

Ví dụ lấy 8 mẫu class loading:

~~~sh
jstat -class 18360 1s 8
~~~

Ví dụ lấy 6 mẫu GC utilization:

~~~sh
jstat -gcutil 18360 500ms 6
~~~

Count chỉ quyết định số lần lấy dữ liệu. Nó không làm cho `-gcutil` trở thành `-gc` hoặc thay đổi ý nghĩa các cột. Chọn đúng stat option theo câu hỏi cần điều tra, sau đó mới quyết định interval và count.

## 8. Ví dụ Java 17+ có thể chạy để thực hành

Chương trình sau liên tục cấp phát các mảng byte và giữ lại một vòng 200 mảng gần nhất. Nó tạo hoạt động heap để quan sát bằng `jstat`. Chương trình chạy cho tới khi bạn nhấn Ctrl+C.

Tạo file `StatProbe.java`:

~~~java
public class StatProbe {
    public static void main(String[] args) throws InterruptedException {
        byte[][] retained = new byte[200][];
        int next = 0;

        System.out.println("stat-probe-ready");

        while (true) {
            retained[next] = new byte[64 * 1024];
            next = (next + 1) % retained.length;
            Thread.sleep(20);
        }
    }
}
~~~

Biên dịch bằng Java 17 trở lên:

~~~sh
mkdir -p out
javac --release 17 -d out StatProbe.java
~~~

Chạy ứng dụng:

~~~sh
java -Xms128m -Xmx128m -cp out StatProbe
~~~

Stdout chính xác khi chương trình khởi động:

~~~text
stat-probe-ready
~~~

Giữ terminal này mở. Mở terminal thứ hai và tìm PID:

~~~sh
jcmd -l
~~~

Giả sử PID là `18360`. Lấy 3 mẫu:

~~~sh
jstat -gcutil 18360 200ms 3
~~~

Output có một header và đúng 3 dòng dữ liệu. Lấy tiếp 5 mẫu có timestamp và lặp header sau mỗi 2 sample:

~~~sh
jstat -gcutil -t -h2 18360 200ms 5
~~~

Trong thử nghiệm với JDK 24.0.2, lệnh đầu in đúng 3 sample; lệnh thứ hai in đúng 5 sample và 3 header. Giá trị heap, GC counter và timestamp phụ thuộc tốc độ máy cũng như thời điểm chạy.

Khi hoàn tất, quay lại terminal chạy `StatProbe` và nhấn `Ctrl+C` để kết thúc JVM.

## 9. Cách chọn interval và count cho mục tiêu giám sát

Không có một cặp interval/count phù hợp với mọi tình huống. Chọn dựa trên tốc độ thay đổi của chỉ số và khoảng thời gian cần quan sát:

- Khi cần kiểm tra nhanh trước/sau một thao tác, dùng vài mẫu với interval ngắn.
- Khi quan sát GC hoặc heap utilization trong một workload kéo dài, dùng interval khoảng một giây và count vừa đủ bao phủ giai đoạn đó.
- Khi cần quan sát tới một sự kiện chưa biết thời điểm xảy ra, có thể bỏ count và dừng thủ công khi đã thu thập đủ.
- Khi output được lưu vào file, dùng count hữu hạn để giới hạn kích thước và thời lượng ghi.

Interval quá ngắn làm tăng số lần đọc dữ liệu và tạo nhiều output, nhưng không đảm bảo phát hiện mọi sự kiện rất ngắn. Interval quá dài có thể bỏ qua thay đổi ngắn giữa hai sample. Hãy chọn tần suất đủ để trả lời câu hỏi điều tra, không chỉ chọn giá trị nhỏ nhất.

Mẫu lấy ở các thời điểm rời rạc. Nếu một GC xảy ra rồi kết thúc giữa hai sample, bạn có thể thấy bộ đếm GC tăng nhưng không thấy trực tiếp trạng thái trong lúc GC diễn ra. Dùng log GC, Java Flight Recorder hoặc công cụ quan sát phù hợp nếu cần timeline chi tiết hơn.

## 10. Lưu output và các lưu ý khi tự động hóa

Có thể chuyển output sang file để xem lại:

~~~sh
jstat -gcutil 18360 1s 60 > gc-samples.txt
~~~

Lệnh ghi tối đa 60 mẫu, mỗi mẫu cách nhau khoảng một giây. Trên PowerShell:

~~~powershell
jstat -gcutil 18360 1s 60 | Out-File -Encoding utf8 gc-samples.txt
~~~

Không nên phụ thuộc lâu dài vào việc parse output `jstat` bằng script cố định. Tài liệu Oracle cảnh báo định dạng output có thể thay đổi giữa các bản phát hành. Nếu cần telemetry cho production, hãy cân nhắc JMX, Java Flight Recorder hoặc hệ thống metrics có schema ổn định hơn.

`jstat` được tài liệu JDK đánh dấu là công cụ experimental và unsupported; option và chức năng có thể thay đổi hoặc bị loại bỏ trong bản JDK tương lai. Hãy kiểm tra `jstat -help` và `jstat -options` trên đúng JDK đang dùng.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Chỉ có một sample rồi kết thúc | Không truyền interval; trong JDK 24.0.2 đã kiểm thử, lệnh in một snapshot | Thêm interval và count nếu cần chuỗi mẫu |
| Lệnh chạy mãi không dừng | Có interval nhưng bỏ count; mặc định count là vô hạn | Truyền count hữu hạn hoặc nhấn Ctrl+C |
| Số dòng dữ liệu ít hơn count | JVM đích kết thúc trước khi đủ mẫu hoặc việc attach bị gián đoạn | Kiểm tra trạng thái JVM và output lỗi |
| Báo interval không hợp lệ | Interval không phải số nguyên dương hoặc định dạng đơn vị sai | Dùng dạng `250ms` hoặc `1s` |
| Báo count không hợp lệ | Count không phải số nguyên dương | Dùng số nguyên dương, ví dụ 5 hoặc 10 |
| Header xuất hiện nhiều lần | Có sử dụng `-hN` | Header lặp theo số sample; header không được tính vào count |
| Tưởng YGC/FGC là sample count | Nhầm bộ đếm GC tích lũy với số lần lấy mẫu | Count là số dòng dữ liệu; YGC/FGC là số sự kiện GC |
| Không tìm thấy JVM | PID sai, JVM đã dừng hoặc đang ở container/PID namespace khác | Dùng `jcmd -l` hoặc `jps -l` trong đúng môi trường |
| Số liệu thay đổi không đều | Workload và lịch lập lịch hệ điều hành thay đổi | Đọc timestamp, tăng interval nếu cần và xem log/recording bổ sung |
| Script parse output bị lỗi sau nâng cấp JDK | Định dạng jstat có thể thay đổi | Tránh phụ thuộc parser theo cột; dùng telemetry có schema ổn định |

## 12. Quy trình sử dụng count sample

1. Xác định JVM cần quan sát bằng `jcmd -l` hoặc `jps -l`.
2. Chọn stat option phù hợp với mục tiêu, ví dụ `-gcutil` cho tỷ lệ heap/GC.
3. Chọn interval dương, có đơn vị rõ ràng như `250ms` hoặc `1s`.
4. Chọn count dương theo số mẫu cần thu thập.
5. Thêm `-t` nếu cần đối chiếu thời gian từ lúc JVM khởi động.
6. Thêm `-hN` nếu output dài và cần lặp header dễ đọc.
7. Chạy lệnh và đếm các dòng dữ liệu, không tính header.
8. So sánh các mẫu theo thời gian; phân biệt count với các bộ đếm GC tích lũy.
9. Nếu cần theo dõi liên tục, quyết định rõ cách dừng hoặc dùng count hữu hạn.
10. Lưu ý giới hạn experimental/unsupported và không phụ thuộc vào định dạng output cho script dài hạn.

### Checklist

- [ ] Đã chọn đúng VMID/PID.
- [ ] Đã chọn đúng stat option.
- [ ] Interval là số nguyên dương và đơn vị được hiểu đúng.
- [ ] Count là số nguyên dương nếu muốn số mẫu hữu hạn.
- [ ] Đã hiểu bỏ count khi có interval sẽ chạy vô hạn.
- [ ] Đã hiểu count là số sample, không phải số GC event.
- [ ] Đã phân biệt header lặp bởi `-h` với dòng dữ liệu.
- [ ] Đã dùng `-t` nếu cần thời gian kể từ khi JVM khởi động.
- [ ] Đã kiểm tra số sample thực tế và trạng thái JVM đích.
- [ ] Đã cân nhắc output format có thể thay đổi trong JDK tương lai.

Tham số `count` giúp giới hạn số lần `jstat` lấy mẫu, còn `interval` quyết định nhịp lấy dữ liệu. Khi hiểu rõ hai tham số này, phân biệt sample với bộ đếm GC và kết hợp đúng `-h`/`-t`, bạn có thể thu thập một chuỗi số liệu vừa đủ để phân tích JVM mà không để lệnh giám sát chạy ngoài ý muốn.

## Tài liệu tham khảo

- [Oracle JDK 24 — The jstat Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jstat.html)
- [Oracle JDK 24 — Diagnostic Tools, jstat Utility](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- [Oracle JDK 24 — JDK Tool Specifications](https://docs.oracle.com/en/java/javase/24/docs/specs/man/index.html)