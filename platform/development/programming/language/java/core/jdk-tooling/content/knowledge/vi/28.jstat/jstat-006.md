# Interval sampling với jstat

@@jstat@@ là công cụ dòng lệnh để theo dõi performance counter của một Java HotSpot VM đang chạy. Công cụ lấy mẫu thống kê GC, dung lượng và mức sử dụng heap, class loading, JIT compilation theo một khoảng thời gian xác định.

Điểm cốt lõi của *interval sampling* là đọc cùng một nhóm counter nhiều lần, cách nhau một khoảng thời gian. Một dòng dữ liệu cho biết trạng thái tại một thời điểm; so sánh các dòng liên tiếp mới cho thấy tốc độ tăng của GC counter, thay đổi mức sử dụng Eden/Old/Metaspace và xu hướng hoạt động của JVM.

Oracle đánh dấu @@jstat@@ là *experimental and unsupported*: option và định dạng output có thể thay đổi hoặc bị loại bỏ ở bản JDK tương lai. Dùng nó tốt cho kiểm tra trực tiếp và runbook đã được kiểm chứng, nhưng không nên xây automation mới phụ thuộc vào việc parse output dạng bảng.

## 1. Interval sampling là gì?

Một lần lấy mẫu (*sample*) là một lần @@jstat@@ đọc các counter của JVM đích và in ra một hàng dữ liệu. *Sampling interval* là thời gian chờ giữa hai lần lấy mẫu liên tiếp. *Count* là số hàng dữ liệu cần in trước khi kết thúc.

Ví dụ:

~~~bash
jstat -gcutil 12345 1000 5
~~~

Lệnh trên đọc thống kê GC của JVM có VM identifier @@12345@@, cách nhau 1.000 ms (1 giây), và in 5 sample. Sau sample thứ năm, @@jstat@@ kết thúc.

Nếu bỏ @@count@@:

~~~bash
jstat -gcutil 12345 1000
~~~

Công cụ tiếp tục lấy mẫu mỗi giây cho tới khi JVM đích kết thúc hoặc người vận hành dừng lệnh bằng @@Ctrl+C@@. Theo tài liệu, count mặc định là vô hạn. Để giới hạn thời gian và tái lập kết quả, hãy chỉ định rõ cả interval và count.

Interval sampling hữu ích vì các counter như số lần GC và tổng thời gian GC thường là giá trị tích lũy từ khi JVM khởi chạy. Chỉ nhìn một dòng không cho biết tốc độ hiện tại. So sánh hai dòng ở hai thời điểm sẽ cho biết trong khoảng đó đã có bao nhiêu GC và tổng thời gian GC tăng thêm bao nhiêu.

## 2. Cú pháp và ý nghĩa của interval/count

Cú pháp tổng quát theo Java SE 21:

~~~text
jstat <statOption> [-t] [-h n] <vmid> [interval [count]]
~~~

| Thành phần | Ý nghĩa |
|---|---|
| @@statOption@@ | Nhóm thống kê cần in, ví dụ @@-gcutil@@, @@-gc@@, @@-class@@ |
| @@-t@@ | Thêm cột Timestamp: số giây đã trôi qua từ lúc JVM đích khởi chạy |
| @@-h n@@ | In lại dòng tiêu đề sau mỗi @@n@@ sample |
| @@vmid@@ | Virtual Machine Identifier của JVM cần theo dõi |
| @@interval@@ | Khoảng cách giữa các sample; số nguyên kèm @@ms@@ hoặc @@s@@, mặc định là millisecond |
| @@count@@ | Tổng số sample; số nguyên dương, mặc định là vô hạn |

Một số cách viết:

~~~bash
# Mỗi 250 ms, lấy 10 sample
jstat -gcutil 12345 250 10

# Mỗi 1 giây, lấy 60 sample
jstat -gcutil 12345 1s 60

# Mỗi 2 giây, tiếp tục cho tới khi dừng
jstat -gcutil 12345 2s

# Có timestamp và lặp header mỗi 5 sample
jstat -gcutil -t -h 5 12345 1s 30
~~~

@@interval@@ phải là số nguyên dương. Có thể ghi rõ đơn vị bằng @@ms@@ hoặc @@s@@; nếu chỉ ghi số, đơn vị mặc định là millisecond. @@count@@ cũng phải là số nguyên dương.

### 2.1. Chọn interval theo mục đích

| Mục tiêu | Khoảng lấy mẫu gợi ý | Cách sử dụng |
|---|---|---|
| Kiểm tra sức khỏe GC ban đầu | 1–5 giây | Quan sát xu hướng trong vài phút |
| Theo dõi một đợt tăng tải ngắn | 250 ms–1 giây | Chỉ lấy trong khoảng ngắn khi cần thấy biến động nhanh |
| Theo dõi dài hạn trong lúc test tải | 1–5 giây | Chọn count đủ lớn để bao phủ toàn bộ bài test |
| Kiểm tra một lần | Không lặp hoặc count nhỏ | Chỉ xem snapshot hiện tại |

Đây là khoảng tham khảo, không phải giới hạn của công cụ. Chọn interval dựa trên tốc độ biến động cần quan sát và chi phí thu thập. Interval quá dài có thể bỏ lỡ GC ngắn hoặc một đợt spike; interval quá ngắn tạo nhiều output, tăng hoạt động giám sát và khiến việc đọc xu hướng khó hơn.

Một sample không phải event log. Nếu GC xảy ra rồi kết thúc giữa hai lần lấy mẫu, counter có thể chỉ cho biết tổng số event đã tăng; bạn không biết chính xác thời điểm bắt đầu/kết thúc của event từ một dòng @@jstat@@.

### 2.2. Timestamp và header lặp

@@-t@@ thêm cột @@Timestamp@@ ở đầu output. Giá trị này là thời gian tính bằng giây kể từ khi JVM đích khởi chạy, không phải ngày giờ trên đồng hồ:

~~~bash
jstat -gcutil -t 12345 500ms 8
~~~

Timestamp giúp tính khoảng cách thực tế giữa hai sample và so sánh dữ liệu trong cùng một phiên JVM. Độ phân giải có thể thay đổi do tải hệ thống và lịch chạy thread; đừng giả định mọi sample luôn cách nhau chính xác tuyệt đối 500 ms.

@@-h n@@ in lại header sau mỗi @@n@@ dòng dữ liệu. Điều này hữu ích khi theo dõi lâu, lưu output vào file hoặc đọc log bị cuộn:

~~~bash
jstat -gcnew -h 10 12345 1s 100
~~~

Header xuất hiện ở đầu và được lặp sau mỗi 10 sample. Nó giúp người đọc không phải kéo lên đầu file để nhớ ý nghĩa từng cột.

## 3. Xác định VMID trước khi lấy mẫu

@@jstat@@ nhận @@vmid@@ (Virtual Machine Identifier). Với JVM cục bộ, VMID thường là local VM identifier (lvmid), thường trùng với OS process ID nhưng không được đảm bảo luôn như vậy.

Liệt kê các Java process:

~~~bash
jps -l
~~~

Ví dụ:

~~~text
5485 jdk.jcmd/sun.tools.jcmd.JCmd
2125 com.example.orders.OrderApplication
7810 org.example.worker.BatchWorker
~~~

Trong ví dụ, @@2125@@ là lvmid của ứng dụng cần theo dõi:

~~~bash
jstat -gcutil 2125 1s 10
~~~

Có thể xác định process bằng công cụ hệ điều hành như @@ps@@ trên Linux/macOS hoặc Task Manager/PowerShell trên Windows:

~~~powershell
Get-Process java
~~~

@@jps@@ và @@jstat@@ có thể không nhìn thấy JVM chạy trong Docker process/PID namespace riêng khi gọi từ host. Khi đó, xác định VMID trong đúng container hoặc namespace.

### 3.1. Remote VMID và jstatd

@@jstat@@ có hỗ trợ remote monitoring qua giao thức RMI nếu máy đích chạy @@jstatd@@. VMID remote có dạng:

~~~text
<lvmid>@<hostname>
~~~

Ví dụ:

~~~bash
jstat -gcutil 40496@remote.example.test 1s 60
~~~

Máy đích phải được cấu hình @@jstatd@@ và registry theo đúng hướng dẫn JDK. Đây là cơ chế quản trị từ xa legacy; cần giới hạn mạng, quyền truy cập và chính sách bảo mật. Không mở @@jstatd@@ công khai trên Internet. Với hệ thống mới, cân nhắc JMX được bảo vệ, JFR hoặc nền tảng monitoring có xác thực và mã hóa.

## 4. Chọn nhóm thống kê phù hợp

Liệt kê những stat option có trên JDK đang sử dụng:

~~~bash
jstat -options
~~~

Xem trợ giúp:

~~~bash
jstat -help
~~~

Các option phổ biến trong Java SE 21:

| Option | Thông tin |
|---|---|
| @@-gc@@ | Mức sử dụng và dung lượng các vùng heap, metaspace, cùng counter GC |
| @@-gcutil@@ | Tóm tắt mức sử dụng các vùng dưới dạng phần trăm |
| @@-gccause@@ | Tóm tắt như @@-gcutil@@ và thêm nguyên nhân GC gần nhất/đang diễn ra |
| @@-gccapacity@@ | Dung lượng tối thiểu, tối đa và hiện tại của các generation/space |
| @@-gcnew@@ | Thống kê New Generation, Eden và Survivor |
| @@-gcnewcapacity@@ | Dung lượng các vùng của New Generation |
| @@-gcold@@ | Thống kê Old Generation và Metaspace |
| @@-gcoldcapacity@@ | Dung lượng Old Generation |
| @@-gcmetacapacity@@ | Dung lượng Metaspace và Compressed Class Space |
| @@-class@@ | Số class đã load/unload và thời gian hoạt động class loader |
| @@-compiler@@ | Thống kê JIT compiler |
| @@-printcompilation@@ | Method vừa được biên dịch và thông tin compilation |

Tập option và các cột thực tế phụ thuộc JDK, JVM vendor và collector. @@jstat -options@@ trên chính máy đang vận hành là nguồn kiểm tra trực tiếp.

### 4.1. -gcutil: xem phần trăm sử dụng

@@-gcutil@@ thường là lựa chọn đầu tiên khi cần nhìn nhanh xu hướng GC:

~~~bash
jstat -gcutil -t 12345 1s 20
~~~

Các cột thường gặp trên HotSpot:

| Cột | Ý nghĩa |
|---|---|
| @@S0@@ | Phần trăm sử dụng Survivor Space 0 |
| @@S1@@ | Phần trăm sử dụng Survivor Space 1 |
| @@E@@ | Phần trăm sử dụng Eden |
| @@O@@ | Phần trăm sử dụng Old Space |
| @@M@@ | Phần trăm sử dụng Metaspace |
| @@CCS@@ | Phần trăm sử dụng Compressed Class Space |
| @@YGC@@ | Tổng số Young GC kể từ khi JVM khởi chạy |
| @@YGCT@@ | Tổng thời gian Young GC, tính bằng giây |
| @@FGC@@ | Tổng số Full GC kể từ khi JVM khởi chạy |
| @@FGCT@@ | Tổng thời gian Full GC, tính bằng giây |
| @@GCT@@ | Tổng thời gian GC được JVM báo cáo, tính bằng giây |

Một số bản JDK/collector mới có thể thêm cột như @@CGC@@ hoặc @@CGCT@@ cho concurrent GC. Cột có thể vắng mặt, có giá trị @@-@@ hoặc mang ý nghĩa khác tùy collector; hãy đọc header thực tế và tài liệu của JDK đang chạy.

### 4.2. -gc: xem dung lượng và mức sử dụng theo KB

@@-gc@@ hiển thị dung lượng và lượng đã sử dụng thay vì chỉ phần trăm:

~~~bash
jstat -gc -t 12345 1s 10
~~~

Các cột thường gặp:

| Cột | Ý nghĩa |
|---|---|
| @@S0C@@ / @@S1C@@ | Dung lượng hiện tại của Survivor 0/1 (KB) |
| @@S0U@@ / @@S1U@@ | Lượng đang sử dụng trong Survivor 0/1 (KB) |
| @@EC@@ / @@EU@@ | Dung lượng và lượng sử dụng của Eden (KB) |
| @@OC@@ / @@OU@@ | Dung lượng và lượng sử dụng của Old Space (KB) |
| @@MC@@ / @@MU@@ | Metaspace committed và used (KB) |
| @@CCSC@@ / @@CCSU@@ | Compressed Class Space committed và used (KB) |
| @@YGC@@ / @@YGCT@@ | Số Young GC và tổng thời gian Young GC |
| @@FGC@@ / @@FGCT@@ | Số Full GC và tổng thời gian Full GC |
| @@GCT@@ | Tổng thời gian GC |

Để tính mức sử dụng phần trăm của một vùng trong một sample:

\[
\text{Usage \%} = \frac{\text{Used}}{\text{Capacity}} \times 100
\]

Ví dụ nếu @@OU@@ là 12.288 KB và @@OC@@ là 16.384 KB thì Old Space đang sử dụng khoảng 75% capacity hiện tại. Capacity có thể thay đổi khi heap mở rộng/thu hẹp; do đó nên quan sát cả used lẫn capacity.

### 4.3. -gccause: xem nguyên nhân GC

~~~bash
jstat -gccause -t 12345 1s 20
~~~

Option này bổ sung:

- @@LGCC@@: nguyên nhân của lần GC gần nhất.
- @@GCC@@: nguyên nhân của GC hiện tại nếu có.

Ví dụ nguyên nhân có thể gặp là @@Allocation Failure@@ hoặc @@No GC@@. Đây là thông tin chẩn đoán hữu ích, nhưng không thay thế GC log khi cần phân tích chi tiết từng event, pause phase hoặc nguyên nhân ở mức sâu.

### 4.4. Các option khác

- @@-gcnew@@: xem Eden/Survivor, tenuring threshold và Young GC. Các cột thường gặp gồm @@TT@@, @@MTT@@, @@DSS@@, @@EC@@, @@EU@@, @@YGC@@, @@YGCT@@.
- @@-gcold@@: xem Old Space, Metaspace và các counter GC.
- @@-gccapacity@@, @@-gcnewcapacity@@, @@-gcoldcapacity@@: xem giới hạn và capacity hiện tại.
- @@-gcmetacapacity@@: xem capacity Metaspace/Compressed Class Space.
- @@-class@@: xem class loader đã load/unload bao nhiêu class, lượng byte và thời gian.
- @@-compiler@@: xem số compilation task thành công/thất bại và thời gian JIT.
- @@-printcompilation@@: xem method vừa được biên dịch trong các sample.

Ví dụ theo dõi class loading và JIT:

~~~bash
jstat -class -t 12345 2s 15
jstat -compiler -t 12345 2s 15
jstat -printcompilation 12345 1s 20
~~~

## 5. Đọc xu hướng qua các sample

Điều quan trọng nhất khi interval sampling là phân biệt **giá trị tức thời** với **counter tích lũy**.

### 5.1. Giá trị tức thời

Các cột như @@E@@, @@O@@, @@S0@@, @@S1@@, @@M@@ là phần trăm sử dụng ở thời điểm sample. Chúng có thể tăng hoặc giảm giữa các dòng:

- @@E@@ tăng khi ứng dụng cấp phát object vào Eden.
- Sau Young GC, @@E@@ thường giảm mạnh vì object còn sống được chuyển/promote và Eden được tái sử dụng.
- @@S0@@ và @@S1@@ luân phiên vai trò trong các collector generational kiểu truyền thống.
- @@O@@ tăng khi object được promote hoặc giữ lại lâu hơn; giảm khi có collection thu hồi được object.
- @@M@@ phản ánh sử dụng Metaspace, liên quan metadata của class.

Eden chạm gần 100% trước Young GC có thể là hành vi bình thường. Không kết luận GC bất thường chỉ vì một sample có @@E=100@@. Hãy quan sát việc Eden có được giải phóng sau collection và tần suất collection có phù hợp với tải hay không.

Old Space tăng liên tục qua nhiều chu kỳ GC có thể cho thấy object sống lâu, promotion cao hoặc heap đang chịu áp lực. Tuy nhiên, một giá trị @@O@@ cao không tự chứng minh memory leak; cần xem xu hướng sau collection, heap dump, GC log hoặc JFR.

### 5.2. Counter tích lũy

@@YGC@@, @@YGCT@@, @@FGC@@, @@FGCT@@ và @@GCT@@ là số liệu tích lũy kể từ khi JVM khởi chạy. Chúng thường không giảm sau mỗi sample. Muốn hiểu hoạt động trong một khoảng, lấy hiệu giữa hai dòng:

\[
\Delta YGC = YGC_2 - YGC_1
\]

\[
\Delta GCT = GCT_2 - GCT_1
\]

Ví dụ minh họa:

| Counter | Sample 1 | Sample 2 | Chênh lệch |
|---|---:|---:|---:|
| Timestamp | 10.0 s | 20.0 s | 10.0 s |
| YGC | 120 | 150 | 30 |
| YGCT | 2.40 s | 3.00 s | 0.60 s |
| FGC | 3 | 4 | 1 |
| FGCT | 0.50 s | 0.80 s | 0.30 s |
| GCT | 2.90 s | 3.80 s | 0.90 s |

Trong khoảng 10 giây:

- Có 30 Young GC, tương đương khoảng 3 Young GC/giây.
- Tổng thời gian Young GC tăng 0,60 giây; thời gian trung bình theo counter là 0,60/30 = 0,02 giây (20 ms) mỗi event.
- Có thêm 1 Full GC, với FGCT tăng 0,30 giây.
- GCT tăng 0,90 giây trong khoảng 10 giây.

Có thể tính một tỷ lệ tham chiếu:

\[
\text{GC time ratio} \approx
\frac{\Delta GCT}{\Delta t} \times 100\%
\]

Trong ví dụ: @@0,90 / 10 × 100 = 9%@@. Đây chỉ là tỷ lệ tham chiếu từ counter thời gian GC; nó không luôn tương đương chính xác phần trăm thời gian ứng dụng bị pause, đặc biệt với concurrent/parallel collector. Khi cần số liệu pause chính xác, dùng GC log hoặc JFR.

Nếu @@YGC@@ tăng nhanh nhưng @@YGCT@@ tăng rất ít, các collection có thể ngắn. Nếu @@FGC@@ tăng thường xuyên và @@FGCT@@ tăng đáng kể, hãy điều tra nguyên nhân Full GC, mức sử dụng Old Space, allocation/promotion và GC log.

### 5.3. Tính tốc độ theo từng khoảng

Với hai sample có timestamp @@t1@@ và @@t2@@:

\[
\text{GC events/sec} =
\frac{YGC_2 - YGC_1}{t_2 - t_1}
\]

\[
\text{Average Young GC duration} =
\frac{YGCT_2 - YGCT_1}{YGC_2 - YGC_1}
\]

Công thức thứ hai chỉ có ý nghĩa khi số Young GC tăng trong khoảng đó. Nếu delta bằng 0, không có event để tính thời gian trung bình.

Không so sánh trực tiếp counter tích lũy của hai JVM khác nhau hoặc hai phiên JVM đã restart. Khi PID/VMID đổi hoặc JVM khởi động lại, hãy bắt đầu một chuỗi sample mới.

## 6. Thực hành: lấy mẫu GC của một JVM đang chạy

Ví dụ này tạo một JVM Java 17+ có cấp phát object liên tục để dễ quan sát Eden và GC. Đây là workload thử nghiệm; không dùng cấu hình heap nhỏ này làm mặc định cho production.

Tạo file @@JstatWorkload.java@@:

~~~java
public final class JstatWorkload {
    private static final byte[][] retained = new byte[128][];

    public static void main(String[] args) throws Exception {
        System.out.println("JstatWorkload ready");
        long end = System.nanoTime() + 30_000_000_000L;
        int index = 0;
        long checksum = 0;

        while (System.nanoTime() < end) {
            byte[] block = new byte[64 * 1024];
            block[0] = (byte) index;
            retained[index++ & (retained.length - 1)] = block;
            checksum += block[0];

            if ((index & 127) == 0) {
                Thread.sleep(1);
            }
        }

        System.out.println("checksum=" + checksum);
    }
}
~~~

Biên dịch và chạy ở terminal thứ nhất:

~~~bash
javac --release 17 JstatWorkload.java
java -Xms32m -Xmx64m -XX:+UseSerialGC JstatWorkload
~~~

Stdout đầu tiên chính xác:

~~~text
JstatWorkload ready
~~~

Chương trình tiếp tục chạy khoảng 30 giây. Ở terminal thứ hai, tìm VMID:

~~~bash
jps -l
~~~

Thay @@12345@@ bằng VMID thật rồi lấy mẫu:

~~~bash
jstat -gcutil -t -h 5 12345 250ms 20
~~~

Lệnh này lấy 20 sample, mỗi sample cách nhau khoảng 250 ms, có timestamp và lặp header sau mỗi 5 dòng.

Để xem dung lượng thực tế:

~~~bash
jstat -gc -t 12345 1s 10
~~~

Để xem nguyên nhân GC:

~~~bash
jstat -gccause -t 12345 1s 10
~~~

Để quan sát class loading/JIT:

~~~bash
jstat -class 12345 1s 10
jstat -compiler 12345 1s 10
~~~

Trên Windows PowerShell, có thể lưu output vào file:

~~~powershell
jstat -gcutil -t -h 5 12345 250ms 20 |
    Tee-Object -FilePath .\gc-samples.txt
~~~

Khi count hoàn tất, @@jstat@@ tự kết thúc. Nếu đang theo dõi không giới hạn, nhấn @@Ctrl+C@@ ở terminal thứ hai; dừng ứng dụng demo ở terminal thứ nhất khi đã hoàn tất.

## 7. Lưu và phân tích sample

Một phiên theo dõi nên lưu được:

- Tên ứng dụng/instance và VMID/PID.
- Thời điểm bắt đầu, phiên bản JDK và GC đang sử dụng.
- Option @@jstat@@, interval và count.
- Output đầy đủ, gồm header và timestamp.
- Bối cảnh tải: test case, request rate hoặc sự kiện triển khai.

Ví dụ lưu một chuỗi GC sample:

~~~bash
jstat -gcutil -t -h 10 12345 1s 300 > gc-samples.txt
~~~

Trong 300 sample, interval 1 giây tạo khoảng 5 phút theo dõi. Thời lượng thực tế có thể dài hơn do scheduling và thời gian thực hiện lệnh.

Để đọc file:

1. Xác định header và hiểu từng cột.
2. Dùng timestamp để chia các khoảng cần phân tích.
3. Tính delta cho các counter tích lũy.
4. So sánh mức sử dụng vùng trước và sau GC.
5. Đánh dấu khoảng có FGC, YGC tăng nhanh hoặc Old Space tăng liên tục.
6. Đối chiếu với log ứng dụng, request rate, metrics và GC log.

Không chỉ giữ vài dòng cuối cùng nếu mục tiêu là phân tích một spike. Cần có sample trước, trong và sau sự kiện để hiểu điều gì thay đổi.

## 8. Giới hạn của jstat và cách dùng cùng công cụ khác

### 8.1. Output không phải giao diện ổn định cho automation

Oracle cảnh báo không nên viết script phụ thuộc vào việc parse output của @@jstat@@ vì định dạng có thể thay đổi giữa các release. Nếu tổ chức vẫn cần parse:

- Pin JDK/vendor/version trong môi trường chạy.
- Kiểm thử parser khi nâng JDK.
- Không giả định thứ tự cột luôn cố định.
- Xử lý cột bổ sung, cột bị thiếu hoặc giá trị @@-@@.
- Lưu output thô để có thể phân tích lại.

Với automation mới, cân nhắc JMX/Micrometer, JFR hoặc metrics pipeline có schema rõ ràng thay vì parse bảng CLI.

### 8.2. Collector và phiên bản ảnh hưởng cách diễn giải

Tên cột như Eden, Survivor và Old phản ánh mô hình generation của các collector generational. Không phải mọi collector đều có cấu trúc giống nhau. Một số cột có thể hiển thị @@-@@, bằng 0 hoặc không phản ánh chính xác cấu trúc heap của collector đang dùng.

Trước khi phân tích:

1. Xác định collector và JDK bằng cấu hình khởi chạy hoặc diagnostic command phù hợp.
2. Đọc header thực tế của @@jstat@@.
3. Đối chiếu tài liệu JDK/vendor và collector.
4. Dùng GC log/JFR nếu cần thông tin chi tiết theo phase.

### 8.3. jstat không thay thế GC log hoặc JFR

@@jstat@@ cho snapshot của counter và xu hướng tổng quát. Nó không cung cấp đầy đủ nguyên nhân, phase, pause duration từng event hoặc call path cấp phát object.

- GC log: phân tích từng GC event, pause, phase, heap trước/sau và nguyên nhân.
- JFR: theo dõi event theo thời gian, allocation, GC, lock và nhiều hoạt động JVM khác.
- JDK Mission Control: phân tích file JFR và các chỉ số theo timeline.
- @@jcmd@@: truy vấn heap info, thread dump, VM flags, system properties và điều khiển JFR.

Dùng @@jstat@@ để nhận biết thời điểm hoặc xu hướng cần điều tra; dùng công cụ chuyên sâu để xác định nguyên nhân.

## 9. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| @@jstat@@ không được nhận diện | JDK @@bin@@ không nằm trong @@PATH@@ hoặc chỉ cài runtime image | Kiểm tra @@where.exe jstat@@ trên Windows hoặc @@which jstat@@ trên Linux/macOS |
| Không tìm thấy VMID | Sai PID/lvmid hoặc JVM đã kết thúc | Chạy lại @@jps -l@@ và xác nhận process |
| Không thấy JVM trong Docker | JVM ở PID namespace/container khác | Chạy @@jps@@/@@jstat@@ trong đúng container |
| Không đọc được performance data | Quyền truy cập, perfdata bị tắt hoặc JVM không hỗ trợ instrumentation mong đợi | Kiểm tra user, runtime, JVM flags và cấu hình @@UsePerfData@@ |
| Một số cột hiển thị @@-@@ | Collector không cung cấp counter đó hoặc counter không áp dụng | Xác định GC collector và đọc tài liệu đúng JDK |
| Không thấy GC trong vài sample | Tải thấp, interval quá ngắn hoặc không có collection trong cửa sổ quan sát | Tăng thời gian quan sát hoặc dùng workload kiểm thử có kiểm soát |
| E tăng rồi giảm mạnh | Eden được cấp phát rồi thu hồi sau Young GC | Đối chiếu @@YGC@@ và @@YGCT@@ |
| O tăng qua nhiều sample | Promotion hoặc object sống lâu; có thể có pressure | Xem xu hướng sau GC, @@FGC@@, GC log và heap |
| Counter giảm đột ngột | JVM restart, VMID đổi hoặc chuỗi sample đã chuyển sang process khác | Xác minh PID, start time và phiên JVM |
| Header khó đọc trong file dài | Header chỉ in ở đầu | Dùng @@-h n@@ để lặp header |
| Script parse sai sau khi nâng JDK | Output format/cột đã thay đổi | Kiểm tra @@jstat -options@@ và cập nhật parser có kiểm thử |

## 10. Quy trình sampling thực tế

1. Xác định đúng JVM bằng @@jps -l@@ hoặc công cụ hệ điều hành.
2. Xác nhận JDK, collector và quyền đọc performance data.
3. Chạy @@jstat -options@@ để biết stat option có sẵn.
4. Bắt đầu với @@-gcutil@@ ở interval khoảng 1 giây và count hữu hạn.
5. Nếu cần hiểu dung lượng, bổ sung @@-gc@@; nếu cần nguyên nhân, dùng @@-gccause@@.
6. Thêm @@-t@@ để so sánh theo thời gian và @@-h n@@ để file dễ đọc.
7. Tính delta của counter tích lũy giữa các sample.
8. Đánh dấu vùng có GC tăng nhanh, Full GC, Old Space tăng hoặc Metaspace bất thường.
9. Lấy GC log/JFR khi cần phân tích event và phase chi tiết.
10. Lưu output cùng phiên bản JDK, interval, count và bối cảnh tải.

## 11. Checklist trước khi kết luận

- [ ] Đúng VMID và đúng instance.
- [ ] Đúng JDK/vendor và collector.
- [ ] Đã kiểm tra option có sẵn bằng @@jstat -options@@.
- [ ] Đã ghi lại interval, count và timestamp.
- [ ] Không nhầm counter tích lũy với mức sử dụng tức thời.
- [ ] Đã tính delta giữa các sample cùng một phiên JVM.
- [ ] Đã xem cả used và capacity khi đánh giá heap.
- [ ] Không kết luận memory leak chỉ từ một giá trị Old Space cao.
- [ ] Không kết luận GC pressure chỉ từ một sample Eden gần 100%.
- [ ] Đã đối chiếu GC log/JFR khi cần nguyên nhân hoặc pause time chính xác.
- [ ] Không phụ thuộc parser CLI mà chưa kiểm thử theo JDK.

## 12. Ghi nhớ

Interval sampling với @@jstat@@ giúp theo dõi cách JVM thay đổi qua thời gian. @@interval@@ quyết định tần suất lấy mẫu, @@count@@ quyết định số sample, @@-t@@ thêm thời gian đã trôi qua từ khi JVM khởi chạy và @@-h n@@ lặp lại header để output dễ đọc.

Dùng @@-gcutil@@ để xem phần trăm sử dụng, @@-gc@@ để xem dung lượng và mức dùng, @@-gccause@@ để xem nguyên nhân GC, rồi so sánh các dòng liên tiếp. Các counter như @@YGC@@, @@YGCT@@, @@FGC@@ và @@GCT@@ là số liệu tích lũy; hãy tính delta theo từng khoảng thay vì chỉ nhìn tổng từ lúc JVM bắt đầu. Xem @@jstat@@ như công cụ quan sát xu hướng và dùng GC log/JFR để xác định nguyên nhân sâu hơn.

Tài liệu tham khảo:

- [The jstat Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstat.html)
- [The jps Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jps.html)
- [The jstatd Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstatd.html)
- [Java SE 21 Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-guide.pdf)