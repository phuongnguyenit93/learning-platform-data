# G1 với các vùng heap và mục tiêu độ trễ trong Java 17

## 1. G1 là gì và vì sao heap được chia thành region?

**G1 (Garbage-First Garbage Collector)** là bộ thu gom rác theo vùng (*region-based collector*) của HotSpot JVM. Thay vì coi heap là một vùng Young và một vùng Old liên tục, G1 chia heap thành nhiều **region có kích thước bằng nhau**. Mỗi region có thể được dùng cho một vai trò khác nhau trong vòng đời thu gom rác.

Thiết kế này giúp G1 chọn một tập region để thu gom trong mỗi lần dừng ứng dụng (*GC pause*). Bộ thu gom ưu tiên các region có nhiều dung lượng có thể thu hồi, từ đó cố gắng đáp ứng mục tiêu thời gian tạm dừng do ứng dụng đặt ra.

Trên các cấu hình server-class, G1 là garbage collector mặc định trong Java 17. Bạn có thể chỉ định rõ bằng:

~~~text
java -XX:+UseG1GC -jar app.jar
~~~

G1 hướng tới sự cân bằng giữa thông lượng (*throughput*) và thời gian tạm dừng (*latency*). Nó phù hợp với nhiều ứng dụng server có heap lớn và cần các khoảng dừng tương đối có thể kiểm soát. Tuy nhiên, G1 **không phải bộ thu gom thời gian thực cứng**: một pause vẫn có thể dài hơn mục tiêu đã đặt.

Trong bài này, ta tập trung vào mô hình region, các vai trò Young/Old/Humongous, cách G1 thu gom và mục tiêu độ trễ bằng những tùy chọn còn dùng trong Java 17.

## 2. Mô hình region của G1

### 2.1. Heap là tập hợp các region

G1 chia Java heap thành nhiều region có kích thước bằng nhau. Region size được JVM chọn khi khởi động dựa trên kích thước heap; thông thường nó là lũy thừa của 2 trong khoảng 1 MB đến 32 MB, nhằm tạo ra xấp xỉ vài nghìn region trên heap.

Ví dụ minh họa với heap 4 GB và region 2 MB:

~~~text
Java Heap (minh họa)
+------------------------------------------------------+
| R0 | R1 | R2 | R3 | R4 | R5 | R6 | R7 | ...          |
+------------------------------------------------------+
  Mỗi ô là một region cùng kích thước

Tại một thời điểm, region có thể mang vai trò:
  Eden | Survivor | Old | Humongous | Free
~~~

Số lượng và vai trò region trong hình chỉ nhằm giải thích khái niệm; JVM tự quản lý chúng trong lúc chạy.

Một region không bị gắn vĩnh viễn với Young hay Old. Sau khi các object còn sống được di chuyển khỏi một region, region nguồn có thể trở thành free region và được dùng lại cho vai trò khác.

### 2.2. Region size được chọn lúc khởi động

G1 chọn region size dựa trên kích thước heap tối đa. Mục tiêu là cân bằng giữa:

- **Region nhỏ:** có độ hạt mịn hơn khi chọn collection set, nhưng cần quản lý nhiều region và nhiều metadata hơn.
- **Region lớn:** giảm số lượng region, nhưng mỗi region chiếm dung lượng lớn hơn; một object lớn có thể chiếm nhiều dung lượng không dùng hết trong region cuối.

Có thể xem region size thực tế qua log khởi động GC:

~~~text
-Xlog:gc+heap=info
~~~

Hoặc đặt tường minh bằng:

~~~text
-XX:G1HeapRegionSize=4m
~~~

Tùy chọn này yêu cầu giá trị hợp lệ theo quy tắc của G1, thông thường là lũy thừa của 2 trong khoảng 1 MB đến 32 MB. Region size được cố định cho heap trong lần chạy JVM đó; nó không liên tục đổi kích thước khi ứng dụng hoạt động.

Không nên thay region size chỉ vì muốn giảm số lượng Humongous Object. Việc tăng region size cũng thay đổi độ hạt mịn của collection set và lượng không gian có thể bị lãng phí. Hãy đo trước khi điều chỉnh.

### 2.3. Vai trò region thay đổi theo chu kỳ GC

G1 dùng các vai trò chính:

| Vai trò | Ý nghĩa |
|---|---|
| **Eden** | Region nhận phần lớn object mới được cấp phát trong Young Generation. |
| **Survivor** | Region chứa object sống sót qua một hoặc nhiều lần Young GC. |
| **Old** | Region chứa object đã được thăng cấp hoặc được cấp phát trực tiếp vào Old Generation. |
| **Humongous** | Region dành cho object có kích thước lớn theo ngưỡng của G1. |
| **Free** | Region chưa chứa object đang được sử dụng và có thể cấp phát cho vai trò khác. |

Eden và Survivor không phải hai vùng liên tục cố định như cách mô tả đơn giản của một số collector khác. Chúng là các vai trò được gán cho những region trong heap.

## 3. Young, Survivor và Old trong G1

G1 vẫn là collector generational: nó tận dụng quan sát rằng nhiều object có vòng đời ngắn. Tuy nhiên, các generation được cấu thành từ region thay vì các vùng địa chỉ cố định.

### 3.1. Young Generation

Object mới thường được cấp phát trong Eden region. Khi Eden region được sử dụng hết hoặc điều kiện thu gom phù hợp xảy ra, G1 thực hiện **Young GC pause**:

1. Tạm dừng các luồng ứng dụng trong một khoảng thời gian (*stop-the-world pause*).
2. Xác định các object còn sống trong các region thuộc collection set.
3. Copy object còn sống sang Survivor region hoặc Old region phù hợp.
4. Thu hồi các region nguồn sau khi quá trình evacuation thành công.

Sơ đồ đơn giản:

~~~text
Trước Young GC
+------------------+------------------+------------------+
| Eden R1          | Eden R2          | Survivor R3      |
| object mới       | object mới       | object sống sót  |
+------------------+------------------+------------------+

              Young GC (pause)
                     |
                     v

Sau evacuation
+------------------+------------------+------------------+
| Free region      | Free region      | Survivor / Old   |
| đã thu hồi       | đã thu hồi       | object còn sống  |
+------------------+------------------+------------------+
~~~

Hình minh họa rút gọn; trong thực tế, object còn sống có thể được copy vào nhiều region đích và các region nguồn được giải phóng khi an toàn.

### 3.2. Survivor và promotion

Object sống qua một Young GC có thể được chuyển vào Survivor region. Khi object tiếp tục sống hoặc đạt điều kiện tuổi/khả năng chứa của Survivor, nó có thể được **promote** sang Old Generation.

Không nên xem tuổi object là điều kiện duy nhất quyết định promotion. G1 còn phải cân nhắc kích thước object, khả năng chứa của Survivor và trạng thái heap.

### 3.3. Old Generation

Old region chứa object có vòng đời dài hơn. G1 không nhất thiết thu gom toàn bộ Old Generation trong mỗi pause. Sau chu kỳ concurrent marking, nó có thể chọn một số Old region có nhiều rác để thu gom cùng các Young region trong **Mixed GC**.

Đây là điểm cốt lõi của tên Garbage-First: G1 ưu tiên region có khả năng thu hồi nhiều dung lượng so với chi phí thu gom, trong giới hạn mục tiêu pause.

## 4. Humongous Object và Humongous Region

Một object được coi là **humongous** khi kích thước của nó bằng hoặc lớn hơn một nửa region size.

Ví dụ, nếu region size là 4 MB:

- Object nhỏ hơn 2 MB không thuộc nhóm humongous chỉ dựa trên ngưỡng kích thước này.
- Object có kích thước từ 2 MB trở lên được xử lý theo cơ chế humongous.

G1 cấp phát humongous object trực tiếp vào một hoặc nhiều region liền kề. Các region đó được đánh dấu là Humongous region; phần cuối của vùng cấp phát có thể không được dùng hết nếu kích thước object không chia hết cho region size.

~~~text
Region size = 4 MB
Humongous object = 9 MB (minh họa)

+----------+----------+----------+
| Region A | Region B | Region C |
| 4 MB     | 4 MB     | 1 MB dùng|
| object   | object   | + phần   |
|          |          | còn trống|
+----------+----------+----------+
~~~

Humongous allocation có một số hệ quả:

- Có thể cần nhiều region liền kề.
- Phần dư ở region cuối có thể bị lãng phí.
- Các object rất lớn có thể làm tăng áp lực cấp phát và ảnh hưởng đến chu kỳ marking/thu gom.
- G1 có một số cơ chế thu hồi humongous object không còn được tham chiếu, nhưng việc cấp phát liên tục các object rất lớn vẫn cần được theo dõi.

Nếu ứng dụng thường xuyên tạo byte array lớn, ảnh, buffer hoặc payload lớn, hãy xem lại thiết kế dữ liệu: streaming, chia chunk, tái sử dụng buffer hoặc tránh giữ nhiều bản sao có thể giảm áp lực lên heap.

Đừng tăng `G1HeapRegionSize` chỉ để đẩy ngưỡng humongous lên cao mà chưa đo. Region lớn hơn có thể giảm số lượng humongous object nhưng cũng làm thay đổi cách G1 chọn region và có thể tăng lãng phí ở các allocation khác.

## 5. Remembered Set và tham chiếu giữa các region

Vì object được phân bố trên nhiều region, G1 cần biết một region có được tham chiếu từ region khác hay không. Nếu phải quét toàn bộ heap để tìm các tham chiếu đi vào collection set trong mỗi pause, thời gian tạm dừng sẽ tăng.

G1 dùng **Remembered Set (RSet)** cho mỗi region để ghi nhận các tham chiếu từ bên ngoài đi vào region đó. Cơ chế này kết hợp với card table và write barrier:

1. Khi ứng dụng ghi một tham chiếu object vào field, write barrier ghi nhận vùng nhớ liên quan.
2. Thông tin card được xử lý/refine để cập nhật remembered set tương ứng.
3. Khi một region nằm trong collection set, G1 có thể dùng remembered set để tìm các tham chiếu đi vào từ những vùng khác mà không phải quét toàn heap.

~~~text
Region A                         Region B
+------------------+             +------------------+
| object X         | --reference->| object Y         |
| field -> Y       |             |                  |
+------------------+             +------------------+
        |                                 ^
        | write barrier / card tracking   |
        +------ remembered set của B -----+
~~~

Remembered set giúp G1 thu gom từng tập region. Tuy nhiên, số lượng tham chiếu chéo region lớn có thể làm tăng chi phí cập nhật RSet và chi phí quét root trong pause. Vì vậy, pause time không chỉ phụ thuộc số byte rác được thu hồi; nó còn chịu ảnh hưởng của object graph và mật độ tham chiếu giữa các region.

## 6. Collection Set và cách G1 chọn region

**Collection Set (CSet)** là tập region được chọn để thu gom trong một GC pause. G1 thực hiện evacuation trên các object còn sống trong những region này.

Một CSet có thể bao gồm:

- Các Eden region và Survivor region trong Young GC.
- Các Young region cùng một số Old region trong Mixed GC.

G1 theo dõi thông tin về lượng object sống và chi phí dự kiến để thu gom region. Khi chọn Old region cho Mixed GC, nó ưu tiên các region có nhiều dung lượng có thể thu hồi, phù hợp với ngân sách pause.

~~~text
Heap regions
+------+------+------+------+------+------+------+
| Eden | Eden | Old  | Old  | Old  | Free | Old  |
+------+------+------+------+------+------+------+
           \       \      /
            \       \    /
             +-------------+
             | Collection  |
             | Set (CSet)  |
             +-------------+
                    |
                    v
          Evacuate live objects
          Reclaim source regions
~~~

Không phải tất cả Old region đều được chọn trong một lần Mixed GC. Việc chọn từng phần giúp G1 chia công việc thu gom Old Generation thành nhiều pause nhỏ hơn, thay vì buộc ứng dụng chờ một lần thu gom toàn bộ Old.

## 7. Các pha chính của G1

G1 có hai nhóm pause quan trọng:

- **Young-only phase:** thu gom Young Generation.
- **Space-reclamation phase:** sau khi đánh dấu Old Generation, kết hợp thu gom Young region và các Old region được chọn; các pause trong giai đoạn này thường được gọi là Mixed GC.

Một chu kỳ tổng quát:

~~~text
Young-only collections
        |
        | Old occupancy / IHOP threshold
        v
Concurrent marking cycle
        |
        +--> Initial Mark (gắn với một Young GC pause)
        |
        +--> Root Region Scan
        |
        +--> Concurrent Mark
        |
        +--> Remark (STW)
        |
        +--> Cleanup (có phần STW)
        |
        v
Mixed collections
        |
        v
Quay lại Young-only collections
~~~

Tên và chi tiết phase trong log có thể thay đổi theo phiên bản/đường đi của GC; sơ đồ mô tả luồng khái niệm trong G1 Java 17.

### 7.1. Initial Mark

Initial Mark xác định các GC root và trạng thái ban đầu cho quá trình đánh dấu. Trong G1, công việc này được gắn vào một Young GC pause, vì vậy nó không nhất thiết tạo thêm một pause độc lập.

### 7.2. Root Region Scan

G1 quét các region gốc liên quan, đặc biệt là các vùng Survivor, để xác định tham chiếu đi vào object graph cần đánh dấu. Công việc này diễn ra đồng thời với ứng dụng nhưng phải hoàn tất trước một số Young GC tiếp theo theo giao thức của collector.

### 7.3. Concurrent Mark

G1 đánh dấu object còn sống trong Old Generation trong khi ứng dụng tiếp tục chạy. G1 sử dụng cơ chế **Snapshot-At-The-Beginning (SATB)** để duy trì tính đúng đắn của tập object được coi là sống tại thời điểm bắt đầu marking.

Concurrent không có nghĩa là không tốn tài nguyên: marking vẫn sử dụng CPU và băng thông bộ nhớ, có thể ảnh hưởng throughput của ứng dụng.

### 7.4. Remark

Remark là một stop-the-world pause ngắn để hoàn tất việc đánh dấu, xử lý các thay đổi tham chiếu cần thiết theo SATB và xác định chính xác tập object sống.

### 7.5. Cleanup

Cleanup hoàn tất một số công việc sau marking, cập nhật thông tin region và chuẩn bị các ứng viên cho Mixed GC. Một số region hoàn toàn rỗng có thể được thu hồi ngay trong giai đoạn này.

### 7.6. Mixed GC

Sau khi có thông tin về mức độ sống của Old region, G1 có thể bắt đầu các Mixed GC pause. Mỗi pause thu gom Young region cùng một tập con Old region. G1 tiếp tục chọn các region phù hợp theo mục tiêu pause và lượng công việc còn lại.

Khi các region Old có khả năng thu hồi đã được xử lý hoặc điều kiện kết thúc space-reclamation phase được đáp ứng, G1 quay lại chu kỳ Young-only.

## 8. Mục tiêu độ trễ: MaxGCPauseMillis

G1 cho phép ứng dụng chỉ định mục tiêu thời gian tạm dừng tối đa mong muốn bằng:

~~~text
-XX:MaxGCPauseMillis=200
~~~

Trong Java 17, giá trị mặc định thường là 200 milliseconds. Đây là **mục tiêu mềm (soft goal)**, không phải cam kết rằng mọi GC pause đều kết thúc trong 200 ms.

G1 dùng mục tiêu này để điều chỉnh công việc trong mỗi pause, ví dụ:

- Điều chỉnh kích thước Young Generation.
- Ước lượng số region có thể thu gom trong một pause.
- Chọn tập Old region cho Mixed GC.
- Cân bằng lượng công việc cần hoàn thành với ngân sách pause.

Nếu ứng dụng đặt mục tiêu thấp hơn, G1 có xu hướng giảm lượng công việc trong mỗi pause và có thể tăng số lần pause. Điều đó có thể làm tăng chi phí GC tổng thể và giảm throughput.

Nếu mục tiêu đặt quá cao, mỗi pause có thể xử lý nhiều region hơn, nhưng ứng dụng có thể phải chờ lâu hơn trong một lần thu gom.

### 8.1. Mục tiêu pause không phải giới hạn cứng

Ví dụ:

~~~text
-XX:MaxGCPauseMillis=50
~~~

không bảo đảm mọi pause nhỏ hơn hoặc bằng 50 ms. Một số nguyên nhân có thể khiến pause vượt mục tiêu:

- Có quá nhiều object sống cần copy trong collection set.
- Remembered set lớn hoặc có nhiều tham chiếu chéo region.
- Số lượng GC root cần quét lớn.
- Heap chịu áp lực cấp phát và còn ít free region.
- Công việc trong pause có biến động mà mô hình dự đoán chưa phản ánh đầy đủ.
- Hệ điều hành hoặc CPU bị tranh chấp tài nguyên.

Do đó, hãy xem `MaxGCPauseMillis` như mục tiêu để G1 tối ưu, rồi đo phân phối pause thực tế bằng GC log và metrics.

### 8.2. Độ trễ và throughput có sự đánh đổi

| Thay đổi | Tác động có thể xảy ra |
|---|---|
| Hạ mục tiêu pause | Mỗi pause có thể ngắn hơn, nhưng GC có thể chạy thường xuyên hơn và giảm throughput. |
| Nâng mục tiêu pause | G1 có thể gom nhiều region hơn trong mỗi pause, tăng hiệu quả thu gom nhưng pause có thể dài hơn. |
| Tăng heap hợp lý | Có thể tạo thêm khoảng trống để allocation và GC hoạt động; cũng làm tăng footprint bộ nhớ và có thể kéo dài một số pha. |
| Giảm allocation rate | Giảm áp lực lên Eden và tần suất Young GC. |
| Giảm lượng object sống | Giảm lượng dữ liệu phải copy trong evacuation và có thể giúp pause ngắn hơn. |

Không có một giá trị pause target đúng cho mọi ứng dụng. Hãy bắt đầu từ mục tiêu latency thực tế của dịch vụ, đo p95/p99 request latency và pause duration, rồi điều chỉnh có kiểm soát.

## 9. Các tùy chọn G1 thường dùng trong Java 17

Các tùy chọn dưới đây là những tùy chọn hiện hành có thể dùng để cấu hình hoặc quan sát G1 trong Java 17.

| Tùy chọn | Mục đích |
|---|---|
| `-XX:+UseG1GC` | Chọn G1 rõ ràng. |
| `-Xms<size>` | Kích thước heap ban đầu/tối thiểu. |
| `-Xmx<size>` | Giới hạn heap tối đa. |
| `-XX:MaxGCPauseMillis=<ms>` | Mục tiêu pause mềm cho G1. |
| `-XX:G1HeapRegionSize=<size>` | Đặt region size khi có lý do đo đạc cụ thể. |
| `-XX:InitiatingHeapOccupancyPercent=<percent>` | Ngưỡng occupancy khởi đầu cho concurrent marking khi adaptive IHOP không được dùng. |
| `-XX:+UseAdaptiveIHOP` | Cho G1 tự điều chỉnh ngưỡng bắt đầu marking dựa trên hành vi ứng dụng. |
| `-XX:G1ReservePercent=<percent>` | Dành một phần heap làm vùng dự trữ để giảm nguy cơ thiếu không gian trong evacuation. |

Không cần đặt tất cả các tùy chọn ngay từ đầu. G1 có ergonomics để tự điều chỉnh nhiều thông số; hãy chỉ thay đổi một tùy chọn khi log hoặc benchmark chỉ ra một vấn đề cụ thể.

### 9.1. Heap size

Ví dụ cấu hình:

~~~text
java -Xms2g -Xmx2g -XX:+UseG1GC -jar app.jar
~~~

Đặt `-Xms` và `-Xmx` bằng nhau có thể tránh một số lần heap phải mở rộng/thu hẹp, nhưng cũng giữ trước lượng bộ nhớ lớn hơn. Hãy chọn heap dựa trên giới hạn container/máy chủ, nhu cầu ứng dụng và bộ nhớ còn dành cho metaspace, thread stack, direct buffer, code cache và native memory.

`-Xmx` chỉ giới hạn Java heap, không giới hạn toàn bộ RSS của tiến trình.

### 9.2. InitiatingHeapOccupancyPercent và Adaptive IHOP

G1 cần bắt đầu concurrent marking đủ sớm để có thể thu hồi Old region trước khi heap thiếu free region. Ngưỡng occupancy có liên quan đến thời điểm bắt đầu chu kỳ marking.

`-XX:InitiatingHeapOccupancyPercent` cung cấp giá trị ngưỡng ban đầu/cố định theo cấu hình tương ứng. Với Adaptive IHOP, G1 dựa vào dữ liệu về tốc độ cấp phát và thời gian marking để điều chỉnh thời điểm khởi động chu kỳ.

Không nên hạ ngưỡng một cách tùy tiện: marking sớm hơn có thể làm tăng công việc concurrent; marking quá muộn có thể khiến G1 thiếu thời gian thu gom trước khi Old Generation chịu áp lực lớn. Hãy xem log về concurrent cycle và tình trạng heap trước khi thay đổi.

### 9.3. G1ReservePercent

G1 cần free region để copy object còn sống trong evacuation. `-XX:G1ReservePercent` dành một tỷ lệ heap làm vùng dự trữ nhằm giảm nguy cơ không còn đủ region đích.

Tăng reserve có thể giúp giảm rủi ro evacuation failure trong một số workload, nhưng cũng làm giảm phần heap có thể sử dụng cho allocation thông thường. Đây không phải cách thay thế cho việc chọn heap đủ lớn hoặc giảm allocation/live set.

## 10. Những điều không nên ép buộc khi dùng G1

G1 dựa vào khả năng tự điều chỉnh kích thước Young Generation để cân bằng pause target. Vì vậy, không nên áp dụng các thiết lập generation cố định theo thói quen từ collector khác nếu chưa hiểu tác động.

Ví dụ, tránh đặt `-Xmn` hoặc ép tỷ lệ Young Generation bằng các tùy chọn như `NewRatio` trong cấu hình G1 thông thường. Việc cố định kích thước Young có thể hạn chế khả năng G1 điều chỉnh số region thu gom để đạt mục tiêu pause.

Đồng thời:

- Không thay đổi hàng loạt GC flags chỉ dựa trên một lần pause dài.
- Không tăng heap vô hạn khi live set hoặc allocation rate là nguyên nhân gốc.
- Không dùng `System.gc()` như cách điều khiển G1 trong luồng nghiệp vụ.
- Không coi một flag tuning là giải pháp thay thế cho việc giảm object allocation không cần thiết.
- Không dùng các collector/flag đã lỗi thời trong tài liệu cũ làm hướng dẫn cho Java 17.

Nếu một flag không có trong tài liệu Java 17 hoặc không được hỗ trợ trên build/runtime đang triển khai, hãy xác minh trước khi đưa vào production. Tùy chọn nội bộ của HotSpot có thể thay đổi theo bản phát hành.

## 11. Theo dõi G1 bằng Unified JVM Logging

Java 17 dùng Unified Logging để ghi log GC. Cách phổ biến là bật log khi khởi chạy:

~~~text
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

Có thể giới hạn kích thước và số file luân phiên:

~~~text
java -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Một số nhóm log hữu ích:

| Cấu hình | Nội dung |
|---|---|
| `-Xlog:gc` | Thông tin GC tổng quát. |
| `-Xlog:gc+heap=info` | Thông tin heap và region ở mức info. |
| `-Xlog:gc+phases=debug` | Chi tiết các phase trong pause/cycle. |
| `-Xlog:safepoint` | Thông tin safepoint và thời gian dừng liên quan. |

Ví dụ log có thể chứa các dòng dạng:

~~~text
[...][info][gc] GC(12) Pause Young (Normal) (G1 Evacuation Pause) 512M->180M(2G) 18.4ms
[...][info][gc] GC(18) Pause Young (Mixed) (G1 Evacuation Pause) 640M->260M(2G) 32.1ms
~~~

Các con số trên chỉ minh họa cách đọc:

- `512M` là mức heap trước GC trong dòng log ví dụ.
- `180M` là mức heap sau GC.
- `(2G)` là capacity heap được hiển thị trong log.
- `18.4ms` hoặc `32.1ms` là thời gian pause.
- `Pause Young (Mixed)` cho biết pause có thu gom Young cùng Old region được chọn.

Định dạng log chi tiết có thể khác tùy build và cấu hình logging; hãy dùng log thực tế của JDK 17 để phân tích.

### 11.1. Những câu hỏi cần trả lời khi đọc GC log

1. Pause dài là Young, Mixed, Remark hay một loại pause khác?
2. Heap giảm bao nhiêu sau mỗi pause?
3. Tần suất Young GC có tăng đột biến không?
4. Concurrent marking bắt đầu đủ sớm không?
5. Có nhiều Humongous allocation không?
6. Có dấu hiệu evacuation failure hoặc Full GC không?
7. Pause dài do copy object sống, scan remembered set, root processing hay phase khác?
8. GC có tiêu tốn CPU concurrent nhiều đến mức ảnh hưởng throughput không?

Đừng chỉ nhìn một dòng pause. Hãy quan sát một khoảng thời gian đủ dài và liên hệ với allocation rate, request latency, CPU, heap occupancy và lưu lượng ứng dụng.

## 12. Full GC và Evacuation Failure

G1 cố gắng thu gom heap theo từng region để tránh một lần dừng toàn bộ quá lâu. Tuy nhiên, trong tình huống thiếu free region hoặc không thể hoàn thành evacuation theo kế hoạch, JVM có thể cần đường xử lý dự phòng tốn kém hơn.

### 12.1. Evacuation Failure

Evacuation failure xảy ra khi G1 không có đủ vùng đích để copy các object còn sống ra khỏi collection set. Đây là dấu hiệu heap đang chịu áp lực lớn hoặc reserve/free regions không đủ cho lượng dữ liệu phải di chuyển.

Hậu quả có thể gồm:

- Pause dài hơn dự kiến.
- Một số region không được thu hồi như kế hoạch.
- Tăng nguy cơ cần Full GC nếu JVM không thể tiếp tục thu gom bình thường.

Hướng điều tra:

- Kiểm tra live set có tăng bất thường không.
- Kiểm tra heap có đủ headroom so với allocation rate không.
- Xem tỷ lệ object sống trong Young/Old collection set.
- Kiểm tra Humongous allocation.
- Xem concurrent marking có bắt đầu đủ sớm không.
- Đo xem `G1ReservePercent` có cần điều chỉnh hay không sau khi đã hiểu nguyên nhân.

### 12.2. Full GC

Full GC của G1 là tình huống cần tránh trong ứng dụng có yêu cầu latency chặt vì nó thường tạo pause stop-the-world dài. Nó có thể xảy ra khi G1 không thể thu gom/evacuate theo cách bình thường hoặc khi ứng dụng yêu cầu GC toàn cục theo cơ chế tương ứng.

Khi thấy Full GC trong log:

1. Xác định nguyên nhân ngay trước Full GC.
2. Xem heap trước và sau Full GC, đặc biệt live data còn lại.
3. Kiểm tra allocation rate và kích thước object lớn.
4. Xác định có rò rỉ tham chiếu hoặc cache không giới hạn không.
5. Kiểm tra thời điểm concurrent marking và free region.
6. Chỉ thay đổi flags sau khi đã xác định giả thuyết và có cách đo xác nhận.

Nếu Full GC chỉ giải phóng rất ít heap, có thể live set đang chiếm phần lớn heap hoặc ứng dụng đang giữ object lâu hơn dự kiến. Tăng heap có thể trì hoãn vấn đề nhưng không sửa được một memory leak.

## 13. Quy trình điều chỉnh G1 theo mục tiêu độ trễ

Một quy trình thực tế nên bắt đầu bằng đo đạc thay vì chọn một bộ flags mẫu.

### Bước 1 — Xác định SLO của ứng dụng

Xác định request latency mục tiêu, chẳng hạn p95/p99, và khoảng pause mà hệ thống có thể chấp nhận. GC pause là một thành phần của request latency, không phải toàn bộ độ trễ.

### Bước 2 — Ghi lại cấu hình hiện tại

Thu thập:

- JDK vendor và phiên bản Java 17 cụ thể.
- Heap `-Xms`/`-Xmx`.
- Collector thực tế từ GC log khởi động.
- Các GC flags đang bật.
- Giới hạn container và CPU.

### Bước 3 — Bật GC logging

Dùng Unified Logging với file rotation để thu thập pause, heap occupancy, phase và safepoint trong tải thực tế.

### Bước 4 — Phân loại nguyên nhân

Phân biệt:

- Allocation rate cao gây nhiều Young GC.
- Live set lớn khiến evacuation copy nhiều object.
- Concurrent marking khởi động muộn.
- Humongous allocation gây áp lực region.
- Remembered set hoặc root scanning làm pause dài.
- CPU contention làm cả GC và ứng dụng chậm.

### Bước 5 — Thay đổi từng yếu tố

Có thể thử điều chỉnh:

- Heap size trong giới hạn bộ nhớ máy/container.
- `MaxGCPauseMillis` dựa trên latency objective.
- `G1ReservePercent` khi có bằng chứng thiếu evacuation headroom.
- IHOP/adaptive marking khi concurrent cycle bắt đầu không phù hợp.
- Region size chỉ khi có dữ liệu về humongous allocation và trade-off.
- Code để giảm allocation hoặc rút ngắn thời gian giữ tham chiếu.

### Bước 6 — Đo lại bằng cùng workload

So sánh:

- p50/p95/p99 GC pause.
- p95/p99 request latency.
- Throughput.
- CPU time dành cho GC.
- Allocation rate.
- Heap occupancy sau GC và live set.
- Số lần Full GC/evacuation failure.

Chỉ giữ thay đổi khi kết quả cải thiện mục tiêu tổng thể mà không tạo hồi quy đáng kể ở chỉ số khác.

## 14. Ví dụ cấu hình G1 cơ bản cho ứng dụng Java 17

Một cấu hình bắt đầu đơn giản:

~~~text
java \
  -Xms2g \
  -Xmx2g \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 \
  -Xlog:gc*:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
~~~

Đây là cấu hình minh họa để quan sát G1, không phải cấu hình tối ưu phổ quát. Hãy chọn heap theo giới hạn thực tế và mục tiêu pause theo SLO. Nếu JVM 17 trên server-class đã dùng G1 mặc định, `-XX:+UseG1GC` có thể không cần thiết, nhưng viết rõ giúp cấu hình dễ đọc khi chuyển môi trường.

Không thêm `-Xmn`, `NewRatio` hoặc các giới hạn Young Generation cố định vào cấu hình ban đầu nếu không có lý do đo đạc rõ ràng; để G1 tự điều chỉnh generation thường giúp nó theo đuổi pause target tốt hơn.

## 15. Bài tập thực hành

### Bài tập 1 — Quan sát region size

Chạy một chương trình Java với heap nhỏ và bật `-Xlog:gc+heap=info`. Tìm thông tin region size trong log. Thử chạy với một heap lớn hơn và so sánh cách JVM chọn region size.

### Bài tập 2 — Quan sát Young GC

Tạo một vòng lặp cấp phát nhiều object tạm thời, giữ lại một phần nhỏ rồi quan sát Young GC. Ghi lại heap trước/sau GC và thời gian pause.

### Bài tập 3 — Phân biệt Young và Mixed GC

Chạy workload giữ lại một số object lâu dài. Quan sát log sau concurrent marking để tìm Mixed GC. Giải thích vì sao Mixed GC có thể thu gom cả Young và một phần Old region.

### Bài tập 4 — Humongous allocation

Thử tạo byte array có kích thước gần hoặc vượt một nửa region size. Quan sát log allocation/heap. Thử thay đổi kích thước object và giải thích vì sao object lớn được cấp phát theo cơ chế humongous.

### Bài tập 5 — Thử pause target

Chạy cùng workload hai lần với `-XX:MaxGCPauseMillis=100` và `-XX:MaxGCPauseMillis=300`. So sánh pause duration, số lần GC và throughput. Không kết luận chỉ từ một lần chạy; hãy lặp lại với dữ liệu đại diện.

### Bài tập 6 — Đọc Full GC

Tìm một log có Full GC hoặc tạo workload làm heap chịu áp lực. Xác định live set trước/sau, allocation rate, humongous region và dấu hiệu evacuation failure nếu có.

## 16. Các nguyên tắc cần ghi nhớ

- G1 chia heap thành các region bằng nhau; region size được chọn lúc JVM khởi động và giữ ổn định trong lần chạy đó.
- Region có thể mang vai trò Eden, Survivor, Old, Humongous hoặc Free; vai trò thay đổi khi object được di chuyển và region được thu hồi.
- Young GC copy object sống sang region đích rồi giải phóng region nguồn; Mixed GC thu gom Young cùng một số Old region được chọn.
- Humongous object có kích thước ít nhất bằng một nửa region size và cần một hoặc nhiều region liền kề.
- Remembered Set giúp G1 tìm tham chiếu đi vào region đang thu gom mà không quét toàn heap.
- Concurrent marking xác định object sống ở Old Generation; sau đó G1 chọn Old region phù hợp cho Mixed GC.
- `-XX:MaxGCPauseMillis` là mục tiêu mềm, không phải cam kết thời gian pause tối đa.
- Hạ pause target có thể làm tăng tần suất GC và giảm throughput; hãy cân bằng theo SLO.
- G1 tự điều chỉnh Young Generation; tránh cố định kích thước Young nếu chưa đo được lợi ích.
- Dùng Unified Logging để quan sát pause, phase, heap và safepoint trước khi tuning.
- Full GC và evacuation failure là dấu hiệu cần điều tra live set, allocation rate, free regions, humongous objects và thời điểm marking.
- Không có bộ GC flags tối ưu cho mọi ứng dụng; thay đổi từng yếu tố và benchmark bằng workload thực tế.

### Tài liệu tham khảo

- [Oracle Java 17 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector.html).
- [Oracle Java 17 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/17/gctuning/).
- [Java SE 17 HotSpot VM Options — G1 Options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248).
